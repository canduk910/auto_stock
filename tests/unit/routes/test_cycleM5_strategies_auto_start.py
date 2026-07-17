"""사이클 M5 (Red) — routes/strategies.py auto_start 전환 (supabase 직접 접근 → system_config 헬퍼).

승인 계획: `~/.claude/plans/partitioned-kindling-lollipop.md` (Supabase→RDS 이전, 누락 사이트).

routes/strategies.py L8/L114/L124 가 `from src.db.supabase import supabase` 로 Supabase system_config
를 직접 읽고/쓴다 → M0~M3 가 RDS(pg) 로 전환한 system_config 와 split-brain.

전환:
- get_auto_start 라우트 → `system_config.get_auto_start()` (M3b 헬퍼). 반환 {auto_start: bool} 보존.
- set_auto_start 라우트 → `system_config.set_auto_start(enabled)` (M5 신규). 응답 메시지 보존.

검증 패턴: 라우트 함수 직접 await (TestClient anyio hang 회피, 사이클 127 답습).

Red 유효성: production 라우트가 여전히 supabase.table() → system_config 헬퍼 미호출 → FAIL.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

pytestmark = pytest.mark.unit

_REPO = Path(__file__).resolve().parents[3]


# ---------------------------------------------------------------------------
# 소스 텍스트 가드 — routes/strategies.py 에서 supabase 직접 접근 제거
# ---------------------------------------------------------------------------
def test_strategies_route_no_supabase_import():
    """routes/strategies.py L8 `from src.db.supabase import supabase` 제거."""
    body = (_REPO / "src" / "routes" / "strategies.py").read_text(encoding="utf-8")
    assert "from src.db.supabase import" not in body, (
        "routes/strategies.py 는 supabase 직접 import 금지 — system_config 헬퍼 경유 (split-brain 해소)."
    )
    assert "supabase.table(" not in body, (
        "routes/strategies.py 는 supabase.table() 직접 호출 0건 (system_config 헬퍼로 전환)."
    )


# ---------------------------------------------------------------------------
# GET /system/auto-start → system_config.get_auto_start()
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_get_auto_start_delegates_to_system_config():
    """get_auto_start 라우트 → system_config.get_auto_start() 위임. 응답 {auto_start: bool} 보존."""
    from src.routes import strategies as strat

    with patch("src.db.system_config.get_auto_start", new=AsyncMock(return_value=True)) as g:
        resp = await strat.get_auto_start()

    g.assert_awaited_once()
    assert resp.success is True
    assert resp.data == {"auto_start": True}, "응답 {auto_start: bool} 계약 보존."


@pytest.mark.asyncio
async def test_get_auto_start_false():
    from src.routes import strategies as strat

    with patch("src.db.system_config.get_auto_start", new=AsyncMock(return_value=False)):
        resp = await strat.get_auto_start()

    assert resp.data == {"auto_start": False}


# ---------------------------------------------------------------------------
# PUT /system/auto-start → system_config.set_auto_start()
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_set_auto_start_delegates_to_system_config():
    """set_auto_start 라우트 → system_config.set_auto_start(enabled) 위임 + 메시지 보존."""
    from src.routes import strategies as strat

    req = strat.AutoStartRequest(enabled=True)
    with patch("src.db.system_config.set_auto_start", new=AsyncMock()) as s:
        resp = await strat.set_auto_start(req)

    s.assert_awaited_once_with(True)
    assert resp.success is True
    assert "활성화" in resp.message, "응답 메시지 계약 보존 (활성화)."


@pytest.mark.asyncio
async def test_set_auto_start_disable_message():
    from src.routes import strategies as strat

    req = strat.AutoStartRequest(enabled=False)
    with patch("src.db.system_config.set_auto_start", new=AsyncMock()) as s:
        resp = await strat.set_auto_start(req)

    s.assert_awaited_once_with(False)
    assert "비활성화" in resp.message, "응답 메시지 계약 보존 (비활성화)."


# ---------------------------------------------------------------------------
# 왕복 불변식 — routes set → routes get 동일 값 (split-brain 해소)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_auto_start_roundtrip_via_routes():
    """set_auto_start(True) 후 get_auto_start() == True — 동일 DB(RDS) 소스 왕복."""
    from src.routes import strategies as strat
    from src.db import system_config as sc

    store: dict = {}

    async def _fake_upsert(key, value):
        store["value"] = value

    async def _fake_select(key):
        return store.get("value", sc._MISSING)

    with patch.object(sc, "_upsert_value", new=_fake_upsert), \
         patch.object(sc, "_select_value", new=_fake_select):
        await strat.set_auto_start(strat.AutoStartRequest(enabled=True))
        resp = await strat.get_auto_start()

    assert resp.data == {"auto_start": True}, (
        "routes set → routes get 왕복 = 동일 소스(RDS) — split-brain 해소 핵심 불변식."
    )
