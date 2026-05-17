"""사이클 7-A (2026-05-17) — `src/auth/token.py` multi-account 단위 테스트.

보조 시세 수신 계좌 토큰 매니저 분리/격리/싱글톤 검증.

자금 안전 원칙 검증:
- 메인 매니저(`token_manager`) 호출 흐름 100% 보존.
- 보조 매니저는 독립 캐시 파일 + 독립 access_token (메인과 격리).
- 미등록 label 호출 → ValueError raise (메인 영향 0).
"""
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def reset_managers(monkeypatch: pytest.MonkeyPatch, tmp_path):
    """각 테스트 전 보조 매니저 dict 초기화 + 캐시 경로 격리."""
    from src.auth import token as token_mod

    # 메인 캐시 격리
    monkeypatch.setattr(token_mod, "_TOKEN_CACHE_PATH", tmp_path / ".token_cache.json")
    # 보조 캐시 prefix 격리 (CWD 오염 방지)
    monkeypatch.setattr(
        token_mod, "_QUOTE_TOKEN_CACHE_PREFIX",
        str(tmp_path / ".token_cache_quote_"),
    )

    # 보조 캐시 파일명 생성도 tmp_path 사용하도록 monkeypatch
    def _safe(label: str) -> Path:
        safe_label = "".join(
            ch if (ch.isalnum() or ch in ("-", "_")) else "_" for ch in label
        )
        return tmp_path / f".token_cache_quote_{safe_label}.json"

    monkeypatch.setattr(token_mod, "_safe_cache_filename", _safe)

    token_mod.reset_quote_token_managers()
    yield
    token_mod.reset_quote_token_managers()


@pytest.mark.asyncio
async def test_get_token_manager_none_returns_main_instance():
    """A: label=None → 메인 매니저 (기존 token_manager 동일 인스턴스)."""
    from src.auth.token import get_token_manager, token_manager

    main = await get_token_manager(None)
    assert main is token_manager


@pytest.mark.asyncio
async def test_get_token_manager_with_label_loads_credentials_from_db(
    monkeypatch: pytest.MonkeyPatch,
):
    """B: label 지정 → DB 에서 자격증명 로드 후 새 매니저 생성."""
    from src.auth import token as token_mod
    from src.db import kis_quote_accounts as kqa

    async def fake_creds(label):
        if label == "quote-1":
            return {
                "app_key": "quote-key-1",
                "app_secret": "quote-secret-1",
                "kis_env": "vts",
            }
        return None

    monkeypatch.setattr(
        kqa, "get_credentials_for_token_manager", fake_creds, raising=False,
    )

    mgr = await token_mod.get_token_manager("quote-1")
    assert mgr.label == "quote-1"
    assert mgr.app_key == "quote-key-1"
    assert mgr.app_secret == "quote-secret-1"
    # vts → openapivts 도메인
    assert "openapivts" in mgr.base_url


@pytest.mark.asyncio
async def test_same_label_returns_singleton_instance(
    monkeypatch: pytest.MonkeyPatch,
):
    """C: 같은 label 두 번 호출 → 동일 인스턴스 (싱글톤)."""
    from src.auth import token as token_mod
    from src.db import kis_quote_accounts as kqa

    call_count = {"n": 0}

    async def fake_creds(label):
        call_count["n"] += 1
        return {"app_key": "k", "app_secret": "s", "kis_env": "real"}

    monkeypatch.setattr(
        kqa, "get_credentials_for_token_manager", fake_creds, raising=False,
    )

    mgr1 = await token_mod.get_token_manager("quote-shared")
    mgr2 = await token_mod.get_token_manager("quote-shared")
    assert mgr1 is mgr2
    # DB 호출은 1회만 (캐시 후 재호출 없음)
    assert call_count["n"] == 1


@pytest.mark.asyncio
async def test_unregistered_label_raises_value_error(
    monkeypatch: pytest.MonkeyPatch,
):
    """D: 미등록 label → ValueError. 메인 매니저 영향 0."""
    from src.auth import token as token_mod
    from src.db import kis_quote_accounts as kqa

    async def fake_creds(label):
        return None  # 항상 미존재

    monkeypatch.setattr(
        kqa, "get_credentials_for_token_manager", fake_creds, raising=False,
    )

    with pytest.raises(ValueError, match="미등록"):
        await token_mod.get_token_manager("quote-missing")


@pytest.mark.asyncio
async def test_quote_manager_isolated_from_main_manager(
    monkeypatch: pytest.MonkeyPatch,
):
    """E: 보조 매니저 토큰 발급/만료 흐름이 메인과 완전 격리."""
    from src.auth import token as token_mod
    from src.db import kis_quote_accounts as kqa

    async def fake_creds(label):
        return {"app_key": "k-q", "app_secret": "s-q", "kis_env": "real"}

    monkeypatch.setattr(
        kqa, "get_credentials_for_token_manager", fake_creds, raising=False,
    )

    main = await token_mod.get_token_manager(None)
    quote = await token_mod.get_token_manager("quote-iso")

    # 메인에 가짜 토큰 세팅
    main.access_token = "MAIN-TOKEN-XYZ"
    main.token_expired = datetime.now() + timedelta(hours=1)

    # 보조에 다른 토큰 세팅
    quote.access_token = "QUOTE-TOKEN-ABC"
    quote.token_expired = datetime.now() + timedelta(hours=1)

    # 두 매니저 격리 확인
    assert main.access_token == "MAIN-TOKEN-XYZ"
    assert quote.access_token == "QUOTE-TOKEN-ABC"
    assert main is not quote
    # 자격증명 격리
    assert main.app_key != quote.app_key
    assert main.app_secret != quote.app_secret


def test_main_manager_existing_flow_preserved():
    """F: 기존 메인 매니저 인스턴스가 그대로 노출됨 (회귀)."""
    from src.auth.token import token_manager, TokenManager

    # 기존 인스턴스 보존 — `token_manager` 가 TokenManager 인스턴스
    assert isinstance(token_manager, TokenManager)
    # label=None 인스턴스 (메인 식별자)
    assert token_manager.label is None
    # build_headers 가 기존 시그니처 그대로 동작
    token_manager.access_token = "test"
    headers = token_manager.build_headers("TTTC0012U")
    assert headers["authorization"] == "Bearer test"
    assert "appkey" in headers
    assert "appsecret" in headers
