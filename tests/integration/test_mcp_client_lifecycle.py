"""Phase 2 Red — FastAPI lifespan 의 MCP 클라이언트 정리 검증.

Phase 1 에서 보류된 작업:
- `src/main.py` lifespan `yield` 종료 블록에서 `await get_mcp_client().close()` 호출 의무.
- 서버 종료 시 httpx.AsyncClient 가 정상 종료되어야 함 (커넥션 누수 방지).

검증 방법:
- TestClient 로 lifespan 시작/종료 사이클 실행
- 종료 후 `_client_instance._http` 가 None 으로 리셋되어 있는지 확인
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration


def test_lifespan_closes_mcp_client_on_shutdown(monkeypatch):
    """앱 시작 시 MCP 클라이언트가 생성되지 않아도 종료 시 close 호출이 안전해야 한다.

    호출 시나리오 1: lifespan 진입 → MCP 호출 없음 → 종료 — close 가 호출돼도 NoOp.
    """
    # 토큰 발급 / DB 초기 로드 차단 (lifespan 비핵심 분기 격리)
    from src.auth import token as token_mod

    async def _fake_token() -> str:
        return "fake-token"

    monkeypatch.setattr(token_mod.token_manager, "get_token", _fake_token)
    monkeypatch.setattr(token_mod.token_manager, "revoke", _fake_token)

    # supabase 호출도 차단
    import src.main as main_mod  # noqa: F401  (ensure import-time wiring)

    from fastapi.testclient import TestClient

    from src.services import mcp_client as mc

    # 초기 상태: 싱글톤 없음
    mc._client_instance = None

    # 실제 호출 1번이라도 발생시켜 인스턴스 생성을 강제
    client = mc.get_mcp_client()
    # 단순 close 호출이 lifespan 종료에서 안전한지 확인하기 위해 _http 만 모킹
    import httpx

    # AsyncClient mock — close 가 정상 await 되는지 확인 가능
    closed_flag = {"closed": False}

    class _FakeHttpx:
        def __init__(self) -> None:
            self.is_closed = False

        async def aclose(self) -> None:
            closed_flag["closed"] = True
            self.is_closed = True

    client._http = _FakeHttpx()  # type: ignore[assignment]

    with TestClient(main_mod.app):
        # lifespan startup 완료. 별도 요청 없이도 yield → shutdown 진입 보장.
        pass

    # shutdown 블록에서 close 가 호출되었어야 한다
    assert closed_flag["closed"] is True, (
        "lifespan shutdown 에서 await get_mcp_client().close() 미호출 — Phase 1 보류 작업"
    )
    # 싱글톤은 close 후 _http=None 유지
    inst = mc._client_instance
    assert inst is not None
    assert inst._http is None


def test_lifespan_close_does_not_raise_when_client_never_initialized(monkeypatch):
    """초기화 안 된 상태에서 lifespan shutdown 이 close 시도해도 안전 (예외 0)."""
    from src.auth import token as token_mod

    async def _fake_token() -> str:
        return "fake-token"

    monkeypatch.setattr(token_mod.token_manager, "get_token", _fake_token)
    monkeypatch.setattr(token_mod.token_manager, "revoke", _fake_token)

    from src.services import mcp_client as mc

    mc._client_instance = None

    import src.main as main_mod  # noqa: F401
    from fastapi.testclient import TestClient

    # 예외 없이 정상 종료되어야 한다 (close 가 _http=None 상태에서 NoOp)
    with TestClient(main_mod.app):
        pass

    # 싱글톤은 lifespan 안에서 만들어졌을 수도 / 안 만들어졌을 수도 있다.
    # 핵심은 예외 없이 종료된다는 점.
