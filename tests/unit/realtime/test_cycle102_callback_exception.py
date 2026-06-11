"""사이클 102 영역 2-C — 콜백 예외 가시화 + raise 영속 (Red).

G-CALLBACK1 — `_on_tick` 예외 발생 시 `_handle_tick` 가 `[callback_exception]` ERROR +
**raise 영속** (사이클 88 G-REJECT-1 재연결 trigger 영속).

영역 2-C = 외부 의견 callback 예외 가시화 신규 (사이클 88 G-REJECT-1 영속).

Red: production 영역 부재 → callback 예외 시 `[callback_exception]` prefix 미발화 → FAIL.
Green: backend-dev 시정 후 PASS.

영속 의무 핵심:
- **사이클 88 G-REJECT-1 영구 영속**: `_on_tick` 예외 시 `raise` 영속 = `_receive_loop`
  정지 + 재연결 trigger 영속 (단일 restore 도입 차단 영속)
- 사이클 88 G-REJECT-2/3 영속 (변경 0)
- 매매 안전성 영향 0 (가시화 영역 한정, raise 영속 = 사이클 88 영구 영역)
"""
from __future__ import annotations

import logging
from unittest.mock import AsyncMock

import pytest

from src.realtime import handler as _handler_mod


pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# G-CALLBACK1 — `_on_tick` 예외 시 [callback_exception] ERROR + raise 영속
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_g_callback1_on_tick_exception_logs_and_raises(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """G-CALLBACK1 (HIGH): `_on_tick` 예외 발생 시 `_handle_tick` 가
    `[callback_exception] handler=_on_tick ticker=...` ERROR + **raise 영속**.

    사이클 88 G-REJECT-1 영구 영속:
    - `raise` 영속 = `_receive_loop` 정지 + 재연결 trigger 영속
    - 단일 restore 도입 차단 영구 영속 (외부 의견 R4 반려 영속)

    Red: production 미시정 → 예외 silent 흡수 또는 prefix 미발화 → FAIL.
    Green: backend-dev `try/except` + `logger.exception("[callback_exception] ...")` + `raise` 추가 → PASS.

    검증 매트릭스:
    - 예외 발생 → `[callback_exception]` ERROR 1행 emit 영속
    - `handler=_on_tick` + `ticker=005930` payload 영속
    - `raise` 영속 (pytest.raises 로 확정 검증)
    """
    # Arrange — `_on_tick` 가 RuntimeError 발생하도록 mock
    original_on_tick = _handler_mod._on_tick
    failing_callback = AsyncMock(
        side_effect=RuntimeError("simulated downstream failure (사이클 102 G-CALLBACK1)"),
    )
    _handler_mod._on_tick = failing_callback
    caplog.clear()
    caplog.set_level(logging.ERROR, logger=_handler_mod.logger.name)

    try:
        # Act — payload 영속 (사이클 88 G-REJECT-2 종목별 영속)
        # 10+ fields + parsed 유효 (current_price > 0 + open_price > 0)
        valid_payload = (
            "005930^140000^70000^5^500^0.7^69800^69500^70500^69400"
        )

        # Assert — RuntimeError raise 영속 (사이클 88 G-REJECT-1 재연결 trigger 영속)
        with pytest.raises(RuntimeError) as exc_info:
            await _handler_mod._handle_tick(valid_payload)

        assert "simulated downstream failure" in str(exc_info.value), (
            f"G-CALLBACK1 위반 — `raise` 영속 결함 (사이클 88 G-REJECT-1 영역 침범): "
            f"{exc_info.value}"
        )

        # Assert — `[callback_exception]` ERROR 1행 emit 영속
        matching = [
            rec for rec in caplog.records
            if "[callback_exception]" in rec.getMessage()
            and rec.levelno >= logging.ERROR
        ]
        assert len(matching) >= 1, (
            f"G-CALLBACK1 위반 — `[callback_exception]` ERROR 1행 emit 영속 결함 "
            f"(실측 {len(matching)}행):\n"
            + "\n".join(f"  - [{rec.levelname}] {rec.getMessage()}" for rec in caplog.records)
            + "\n\n  시정: `_handle_tick` 영역 콜백 호출 부에:\n"
            f"    if _on_tick:\n"
            f"        try:\n"
            f"            await _on_tick(ticker, current_price, open_price, change_rate)\n"
            f"        except Exception:\n"
            f"            logger.exception(\n"
            f"                '[callback_exception] handler=_on_tick ticker=%s', ticker,\n"
            f"            )\n"
            f"            raise  # 사이클 88 G-REJECT-1 재연결 trigger 영속\n"
        )

        # prefix 영역 정합성 영속 (handler=_on_tick + ticker)
        msg = matching[0].getMessage()
        assert "handler=_on_tick" in msg, (
            f"G-CALLBACK1 위반 — `handler=_on_tick` prefix 영역 결함: {msg}"
        )
        assert "005930" in msg, (
            f"G-CALLBACK1 위반 — ticker=005930 영역 결함 (사이클 88 G-REJECT-2 종목별 영속): {msg}"
        )

        # 콜백이 실제로 호출됐는지 영속 (mock 호출 영속)
        failing_callback.assert_called_once()

    finally:
        # 격리: 테스트 후 원상 복구
        _handler_mod._on_tick = original_on_tick
