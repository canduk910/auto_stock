"""회귀 가드 (결함 1, HIGH) — `_subscribe_market_operation_tickers` 함수-로컬 import 오류.

프로덕션 로그분석(2026-07-24): `[src.engine.scheduler] _subscribe_market_operation_tickers 실패`
ERROR 가 매 `_scan_loop`(5분) 사이클마다 발화 → 07-24 종일 117건(일일 ERROR의 94%).
cycle 214 배포(07-15) 직후부터 만성.

근본 원인: 함수 첫 줄
    from src.realtime.websocket import kis_ws, kis_ws_pool
`kis_ws_pool` 은 `src.realtime.websocket_pool` 에만 정의(websocket.py 에는 정의/재노출 0건)돼
매 호출 `ImportError: cannot import name 'kis_ws_pool' from 'src.realtime.websocket'` 를 던진다.
함수 첫 줄이라 이후 HIGH/LOW 구독 루프·per-ticker 로그·`[market_op_subscribe_summary]` INFO
전부 미실행 → cycle 214 의 H0UNMKO0(장운영정보) 종목별 구독이 07-15 이래 100% 사망.

주의 — 기존 `tests/unit/engine/test_cycle214_h0unmko0_pool.py::_patch_ws` 는
`monkeypatch.setattr("src.realtime.websocket.kis_ws_pool", ...)` 로 websocket 모듈 네임스페이스에
`kis_ws_pool` 을 **주입**한다. 그 결과 결함이 있는 import 가 테스트 안에서만 성공 → 결함이 가려졌다.
이 회귀 가드는 그 주입을 하지 않고(오히려 delattr 로 부재를 강제하여) 프로덕션 조건을 재현한다.

Red: 현재 코드 호출 시 ImportError → FAIL.
Green: import 를 두 줄로 분리(`websocket` 은 `kis_ws` 만, `kis_ws_pool` 은 `websocket_pool` 에서)
       → ImportError 없이 함수가 끝까지 실행되어 LOW 후보가 풀 구독되고 summary INFO 를 emit.
"""

from __future__ import annotations

import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.api.market_operation import MARKET_OP_TR_ID
from src.engine.scheduler import TradingScheduler


def _make_scheduler(*, positions: set[str], pending: set[str]) -> TradingScheduler:
    """subscribe 함수만 태우기 위한 최소 스케줄러 인스턴스."""
    sched = TradingScheduler.__new__(TradingScheduler)
    strat = SimpleNamespace(
        state=SimpleNamespace(positions={t: object() for t in positions})
    )
    registry = MagicMock()
    registry.all.return_value = [strat]
    sched.registry = registry
    sched._pending_next_day_clear = {(t, "some_strategy") for t in pending}
    return sched


@pytest.mark.asyncio
async def test_subscribe_market_op_does_not_raise_importerror(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """결함 1 핵심 — 함수 호출이 ImportError 를 던지지 않고 끝까지 실행되어야 한다.

    프로덕션 조건 재현: `src.realtime.websocket` 에는 `kis_ws_pool` 이 없다.
    (기존 cycle214 테스트가 주입하던 attr 을 명시적으로 제거해 결함 마스킹을 차단.)
    """
    # 메인 세션 kis_ws = truthy `_ws` + AsyncMock subscribe (조기 return 회피).
    fake_ws = MagicMock()
    fake_ws._ws = object()
    fake_ws.subscribe = AsyncMock(return_value=None)

    # 풀 kis_ws_pool = 올바른 소스 모듈(websocket_pool)에 격리.
    fake_pool = MagicMock()
    fake_pool.subscribe = AsyncMock(return_value="quote-1")

    monkeypatch.setattr("src.realtime.websocket.kis_ws", fake_ws, raising=False)
    monkeypatch.setattr(
        "src.realtime.websocket_pool.kis_ws_pool", fake_pool, raising=False
    )
    # 결함 마스킹 차단 — websocket 모듈에서 kis_ws_pool 부재를 강제(프로덕션과 동일).
    monkeypatch.delattr("src.realtime.websocket.kis_ws_pool", raising=False)

    sched = _make_scheduler(positions=set(), pending=set())
    candidates = {"111111", "222222"}

    with caplog.at_level(logging.INFO, logger="src.engine.scheduler"):
        try:
            result = await sched._subscribe_market_operation_tickers(candidates)
        except ImportError as exc:  # noqa: PT017 — 정확한 Red 사유 캡처
            pytest.fail(
                "결함 1 — 함수 첫 줄 import 가 ImportError 를 던짐 "
                f"(kis_ws_pool 은 websocket_pool 에서 import 해야 함): {exc}"
            )

    # import 를 통과하면 LOW 후보가 풀 구독으로 흘러 함수가 끝까지 실행된다.
    assert result == len(candidates)
    assert fake_pool.subscribe.await_count == len(candidates)
    for call in fake_pool.subscribe.await_args_list:
        args, kwargs = call
        assert args[0] == MARKET_OP_TR_ID
        assert kwargs.get("priority") == "LOW"
    # 프로덕션에서 emit 0건이던 summary INFO 가 실제로 발화해야 한다.
    assert "[market_op_subscribe_summary]" in caplog.text
