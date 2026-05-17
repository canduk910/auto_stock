"""사이클 7-A (2026-05-17) — `/api/integrations/quote-accounts/*` 컨트랙트 테스트.

보조 KIS 시세 수신 계좌 등록/조회/관리 라우트 검증.

자금 안전 원칙 검증:
- 모든 응답에서 app_secret 평문 절대 노출 안 함 (마스킹 확인).
- label UNIQUE 위반 409.
- 빈 값 422.
- 미존재 ID 404.
"""
from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.contract


@pytest.fixture
def client(monkeypatch):
    """DB 헬퍼 일괄 monkeypatch → 인메모리 dict 시뮬레이션."""
    from src.db import kis_quote_accounts as kqa
    from src.models.kis_quote_account import KisQuoteAccount, mask_secret

    state: dict[str, dict] = {}  # id -> raw row dict (app_secret 평문 포함, 내부 only)

    def _to_account(row: dict) -> KisQuoteAccount:
        return KisQuoteAccount(
            id=row["id"],
            label=row["label"],
            app_key=row["app_key"],
            app_secret_masked=mask_secret(row["app_secret"]),
            kis_env=row["kis_env"],
            active=row["active"],
            created_at=row["created_at"],
            updated_at=row.get("updated_at"),
        )

    async def fake_list(active_only: bool = False):
        rows = list(state.values())
        if active_only:
            rows = [r for r in rows if r["active"]]
        return [_to_account(r) for r in sorted(rows, key=lambda r: r["created_at"])]

    async def fake_get(account_id):
        row = state.get(str(account_id))
        return _to_account(row) if row else None

    async def fake_get_by_label(label):
        for r in state.values():
            if r["label"] == label:
                return _to_account(r)
        return None

    async def fake_insert(label, app_key, app_secret, kis_env):
        label = (label or "").strip()
        app_key = (app_key or "").strip()
        app_secret = (app_secret or "").strip()
        if not label or not app_key or not app_secret:
            raise ValueError("빈 값")
        if kis_env not in ("real", "vts"):
            raise ValueError("kis_env 부적합")
        # label 충돌 검사
        for r in state.values():
            if r["label"] == label:
                raise kqa.LabelConflictError(f"이미 등록된 label: {label}")
        new_id = str(uuid4())
        row = {
            "id": new_id,
            "label": label,
            "app_key": app_key,
            "app_secret": app_secret,
            "kis_env": kis_env,
            "active": True,
            "created_at": datetime.now(),
            "updated_at": None,
        }
        state[new_id] = row
        return _to_account(row)

    async def fake_update(account_id, *, active=None, label=None):
        row = state.get(str(account_id))
        if row is None:
            return None
        if label is not None:
            new_label = label.strip()
            if not new_label:
                raise ValueError("label 빈 값")
            if new_label != row["label"]:
                for r in state.values():
                    if r["label"] == new_label and r["id"] != row["id"]:
                        raise kqa.LabelConflictError(f"이미 등록된 label: {new_label}")
                row["label"] = new_label
        if active is not None:
            row["active"] = bool(active)
        row["updated_at"] = datetime.now()
        return _to_account(row)

    async def fake_delete(account_id):
        aid = str(account_id)
        if aid in state:
            del state[aid]
            return True
        return False

    monkeypatch.setattr(kqa, "list_accounts", fake_list, raising=False)
    monkeypatch.setattr(kqa, "get_account", fake_get, raising=False)
    monkeypatch.setattr(kqa, "get_account_by_label", fake_get_by_label, raising=False)
    monkeypatch.setattr(kqa, "insert_account", fake_insert, raising=False)
    monkeypatch.setattr(kqa, "update_account", fake_update, raising=False)
    monkeypatch.setattr(kqa, "delete_account", fake_delete, raising=False)

    from src.main import app
    return SimpleNamespace(client=TestClient(app), state=state)


# ---------------------------------------------------------------------------
# A: GET 빈 목록
# ---------------------------------------------------------------------------
def test_get_quote_accounts_empty_returns_empty_list(client):
    resp = client.client.get("/api/integrations/quote-accounts")
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["data"] == {"accounts": []}


# ---------------------------------------------------------------------------
# B: POST 정상 → 201 + 마스킹 응답
# ---------------------------------------------------------------------------
def test_post_quote_account_success_returns_201_with_masked_secret(client):
    resp = client.client.post(
        "/api/integrations/quote-accounts",
        json={
            "label": "quote-1",
            "app_key": "appkey-1234567890",
            "app_secret": "secret-abcdef1234",
            "kis_env": "real",
        },
    )
    assert resp.status_code == 201
    data = resp.json()["data"]
    assert data["label"] == "quote-1"
    assert data["app_key"] == "appkey-1234567890"
    # 평문 노출 절대 금지 — 마스킹 확인
    assert data["app_secret_masked"] == "****1234"
    assert "app_secret" not in data  # 평문 키 자체가 응답에 없음
    assert data["kis_env"] == "real"
    assert data["active"] is True


# ---------------------------------------------------------------------------
# C: POST label 중복 → 409
# ---------------------------------------------------------------------------
def test_post_quote_account_duplicate_label_returns_409(client):
    client.client.post(
        "/api/integrations/quote-accounts",
        json={
            "label": "quote-dup",
            "app_key": "k1",
            "app_secret": "secret-aaaa1111",
            "kis_env": "real",
        },
    )
    resp = client.client.post(
        "/api/integrations/quote-accounts",
        json={
            "label": "quote-dup",
            "app_key": "k2",
            "app_secret": "secret-bbbb2222",
            "kis_env": "vts",
        },
    )
    assert resp.status_code == 409


# ---------------------------------------------------------------------------
# D: POST 빈 값 → 422
# ---------------------------------------------------------------------------
def test_post_quote_account_empty_label_returns_422(client):
    resp = client.client.post(
        "/api/integrations/quote-accounts",
        json={
            "label": "",
            "app_key": "k1",
            "app_secret": "secret-aaaa1111",
            "kis_env": "real",
        },
    )
    assert resp.status_code == 422


def test_post_quote_account_empty_appkey_returns_422(client):
    resp = client.client.post(
        "/api/integrations/quote-accounts",
        json={
            "label": "quote-x",
            "app_key": "",
            "app_secret": "secret-aaaa1111",
            "kis_env": "real",
        },
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# E: GET 목록 → 마스킹 보존
# ---------------------------------------------------------------------------
def test_get_quote_accounts_list_preserves_masking(client):
    client.client.post(
        "/api/integrations/quote-accounts",
        json={
            "label": "quote-e1",
            "app_key": "k-e1",
            "app_secret": "secret-cccc3333",
            "kis_env": "real",
        },
    )
    client.client.post(
        "/api/integrations/quote-accounts",
        json={
            "label": "quote-e2",
            "app_key": "k-e2",
            "app_secret": "secret-dddd4444",
            "kis_env": "vts",
        },
    )
    resp = client.client.get("/api/integrations/quote-accounts")
    accounts = resp.json()["data"]["accounts"]
    assert len(accounts) == 2
    for a in accounts:
        assert "app_secret_masked" in a
        assert a["app_secret_masked"].startswith("****")
        assert "app_secret" not in a


# ---------------------------------------------------------------------------
# F: PUT active 토글
# ---------------------------------------------------------------------------
def test_put_quote_account_active_toggle(client):
    create_resp = client.client.post(
        "/api/integrations/quote-accounts",
        json={
            "label": "quote-f",
            "app_key": "k-f",
            "app_secret": "secret-eeee5555",
            "kis_env": "real",
        },
    )
    account_id = create_resp.json()["data"]["id"]

    resp = client.client.put(
        f"/api/integrations/quote-accounts/{account_id}",
        json={"active": False},
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["active"] is False

    # 다시 활성화
    resp2 = client.client.put(
        f"/api/integrations/quote-accounts/{account_id}",
        json={"active": True},
    )
    assert resp2.status_code == 200
    assert resp2.json()["data"]["active"] is True


# ---------------------------------------------------------------------------
# G: DELETE → 목록에서 사라짐
# ---------------------------------------------------------------------------
def test_delete_quote_account_then_gone_from_list(client):
    create_resp = client.client.post(
        "/api/integrations/quote-accounts",
        json={
            "label": "quote-g",
            "app_key": "k-g",
            "app_secret": "secret-ffff6666",
            "kis_env": "vts",
        },
    )
    account_id = create_resp.json()["data"]["id"]

    del_resp = client.client.delete(f"/api/integrations/quote-accounts/{account_id}")
    assert del_resp.status_code == 200
    assert del_resp.json()["data"]["deleted"] is True

    list_resp = client.client.get("/api/integrations/quote-accounts")
    assert all(a["label"] != "quote-g" for a in list_resp.json()["data"]["accounts"])


# ---------------------------------------------------------------------------
# H: PUT 미등록 ID → 404
# ---------------------------------------------------------------------------
def test_put_unknown_id_returns_404(client):
    random_id = str(uuid4())
    resp = client.client.put(
        f"/api/integrations/quote-accounts/{random_id}",
        json={"active": False},
    )
    assert resp.status_code == 404


def test_delete_unknown_id_returns_404(client):
    random_id = str(uuid4())
    resp = client.client.delete(f"/api/integrations/quote-accounts/{random_id}")
    assert resp.status_code == 404
