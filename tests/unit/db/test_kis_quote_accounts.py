"""사이클 7-A (2026-05-17) — `src/db/kis_quote_accounts.py` 단위 테스트.

보조 KIS 시세 수신 계좌 풀 CRUD 검증.

자금 안전 원칙 검증:
- 본 모듈 응답은 항상 app_secret 마스킹된 모델 반환 (평문 노출 차단).
- label UNIQUE / kis_env CHECK / 빈 값 거부 — DB 제약 + 사전 검사 이중 안전망.
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_insert_then_list_returns_account_with_masked_secret(
    monkeypatch: pytest.MonkeyPatch,
    fake_supabase,
):
    """A: insert → list 가 1건 반환, app_secret 마스킹 적용."""
    from src.db import kis_quote_accounts as kqa

    monkeypatch.setattr(kqa, "supabase", fake_supabase)

    inserted = await kqa.insert_account(
        label="quote-1",
        app_key="appkey-abc",
        app_secret="secret-abcdef1234",
        kis_env="real",
    )
    assert inserted.label == "quote-1"
    assert inserted.app_key == "appkey-abc"
    # 마스킹 확인 — 평문 노출 절대 금지
    assert inserted.app_secret_masked == "****1234"
    assert inserted.kis_env == "real"
    assert inserted.active is True

    accounts = await kqa.list_accounts()
    assert len(accounts) == 1
    assert accounts[0].label == "quote-1"
    assert accounts[0].app_secret_masked == "****1234"


@pytest.mark.asyncio
async def test_list_active_only_filter_excludes_inactive(
    monkeypatch: pytest.MonkeyPatch,
    fake_supabase,
):
    """B: active_only=True 면 비활성 계좌 제외."""
    from src.db import kis_quote_accounts as kqa

    monkeypatch.setattr(kqa, "supabase", fake_supabase)

    a1 = await kqa.insert_account("quote-1", "k1", "secret-aaaa1111", "real")
    a2 = await kqa.insert_account("quote-2", "k2", "secret-bbbb2222", "vts")

    # quote-2 비활성화
    await kqa.update_account(a2.id, active=False)

    all_acc = await kqa.list_accounts()
    assert len(all_acc) == 2

    active_only = await kqa.list_accounts(active_only=True)
    labels = [a.label for a in active_only]
    assert "quote-1" in labels
    assert "quote-2" not in labels


@pytest.mark.asyncio
async def test_get_by_id_and_get_by_label(
    monkeypatch: pytest.MonkeyPatch,
    fake_supabase,
):
    """C: ID/label 단건 조회 둘 다 동작."""
    from src.db import kis_quote_accounts as kqa

    monkeypatch.setattr(kqa, "supabase", fake_supabase)

    inserted = await kqa.insert_account("quote-3", "k3", "secret-cccc3333", "vts")

    by_id = await kqa.get_account(inserted.id)
    assert by_id is not None
    assert by_id.label == "quote-3"

    by_label = await kqa.get_account_by_label("quote-3")
    assert by_label is not None
    assert str(by_label.id) == str(inserted.id)

    # 미존재
    not_found_label = await kqa.get_account_by_label("nonexistent")
    assert not_found_label is None


@pytest.mark.asyncio
async def test_update_account_active_false_then_filtered_out(
    monkeypatch: pytest.MonkeyPatch,
    fake_supabase,
):
    """D: active=False 갱신 후 active_only 목록에서 제외."""
    from src.db import kis_quote_accounts as kqa

    monkeypatch.setattr(kqa, "supabase", fake_supabase)

    inserted = await kqa.insert_account("quote-4", "k4", "secret-dddd4444", "real")
    updated = await kqa.update_account(inserted.id, active=False)
    assert updated is not None
    assert updated.active is False

    active_only = await kqa.list_accounts(active_only=True)
    assert all(a.label != "quote-4" for a in active_only)


@pytest.mark.asyncio
async def test_delete_account_then_removed_from_list(
    monkeypatch: pytest.MonkeyPatch,
    fake_supabase,
):
    """E: 삭제 후 목록에서 사라짐."""
    from src.db import kis_quote_accounts as kqa

    monkeypatch.setattr(kqa, "supabase", fake_supabase)

    inserted = await kqa.insert_account("quote-5", "k5", "secret-eeee5555", "vts")
    deleted = await kqa.delete_account(inserted.id)
    assert deleted is True

    all_acc = await kqa.list_accounts()
    assert all(a.label != "quote-5" for a in all_acc)

    # 두 번째 삭제는 False
    deleted_again = await kqa.delete_account(inserted.id)
    assert deleted_again is False


@pytest.mark.asyncio
async def test_insert_duplicate_label_raises_label_conflict_error(
    monkeypatch: pytest.MonkeyPatch,
    fake_supabase,
):
    """F: 동일 label 두 번째 등록 → LabelConflictError."""
    from src.db import kis_quote_accounts as kqa

    monkeypatch.setattr(kqa, "supabase", fake_supabase)

    await kqa.insert_account("quote-dup", "k1", "secret-aaaa1111", "real")

    with pytest.raises(kqa.LabelConflictError):
        await kqa.insert_account("quote-dup", "k2", "secret-bbbb2222", "vts")


@pytest.mark.asyncio
async def test_insert_invalid_kis_env_raises_value_error(
    monkeypatch: pytest.MonkeyPatch,
    fake_supabase,
):
    """G: kis_env 가 'real'/'vts' 외 → ValueError."""
    from src.db import kis_quote_accounts as kqa

    monkeypatch.setattr(kqa, "supabase", fake_supabase)

    with pytest.raises(ValueError):
        await kqa.insert_account("quote-bad-env", "k1", "secret-aaaa1111", "prod")


@pytest.mark.asyncio
async def test_insert_empty_label_or_appkey_raises_value_error(
    monkeypatch: pytest.MonkeyPatch,
    fake_supabase,
):
    """H: 빈 label / app_key / app_secret → ValueError."""
    from src.db import kis_quote_accounts as kqa

    monkeypatch.setattr(kqa, "supabase", fake_supabase)

    with pytest.raises(ValueError):
        await kqa.insert_account("", "k1", "secret-aaaa1111", "real")

    with pytest.raises(ValueError):
        await kqa.insert_account("quote-x", "", "secret-aaaa1111", "real")

    with pytest.raises(ValueError):
        await kqa.insert_account("quote-x", "k1", "", "real")
