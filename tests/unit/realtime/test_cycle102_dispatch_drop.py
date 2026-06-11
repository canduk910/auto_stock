"""사이클 102 영역 2-B — `_silent_drop_count` ticker별 가시화 신규 (Red).

G-DISPATCH1 + G-DISPATCH2 + G-DISPATCH3 — `_handle_tick` graceful drop 분기에서
ticker별 누적 + 5분 collector flush emit + 함수 import 가능 검증.

영역 2-B = 외부 의견 dispatch 누락 silent drop 영역 가시화 신규 (사이클 74 답습).

Red: production 영역 부재 → 3 케이스 모두 FAIL.
Green: backend-dev 시정 후 3 PASS.

영속 의무:
- 사이클 88 G-REJECT-2 영속 (종목별 영속 패턴 답습)
- 사이클 74 collector 패턴 답습 (5분 윈도우 emit + clear)
- 사이클 78 import 패턴 답습 (`from src.realtime.handler import flush_silent_drop_count`)
- 매매 안전성 영향 0 (가시화 영역 한정)
"""
from __future__ import annotations

import logging

import pytest

from src.realtime import handler as _handler_mod


pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# G-DISPATCH1 — `_handle_tick` graceful drop 분기에서 ticker별 누적
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_g_dispatch1_silent_drop_count_increment_per_ticker():
    """G-DISPATCH1 (HIGH): `_handle_tick` 영역 `len(fields) < 10` 또는 `parsed is None`
    분기 진입 시 `_silent_drop_count[ticker]` +1 영속 (사이클 88 G-REJECT-2 종목별 영속 답습).

    Red: production 미시정 → `_silent_drop_count` 모듈 전역 부재 또는 누적 영역 부재 → FAIL.
    Green: backend-dev 시정 후 PASS.

    검증 매트릭스:
    - 모듈 전역 `_silent_drop_count: dict[str, int]` 신규
    - `_handle_tick(payload)` `len(fields) < 10` 진입 시 ticker별 +1
    - `_handle_tick(payload)` `parsed is None` 진입 시 ticker별 +1
    - 다중 ticker 격리 영속
    """
    # 사전 조건: 모듈 전역 신규 영역 영속
    assert hasattr(_handler_mod, "_silent_drop_count"), (
        "G-DISPATCH1 위반 — `_silent_drop_count` 모듈 전역 신규 영역 부재.\n"
        "  시정: `src/realtime/handler.py` 영역에\n"
        "  `_silent_drop_count: dict[str, int] = {}` 추가 (사이클 88 G-REJECT-2 답습)."
    )
    # 사전 조건: dict 타입 영속
    assert isinstance(_handler_mod._silent_drop_count, dict), (
        f"G-DISPATCH1 위반 — `_silent_drop_count` 타입 결함: "
        f"{type(_handler_mod._silent_drop_count).__name__}"
    )

    # Arrange — collector clear (테스트 격리)
    _handler_mod._silent_drop_count.clear()

    # Act 1: `len(fields) < 10` 분기 진입 (ticker = "005930" 1회)
    short_payload = "005930^140000^70000"  # 3 fields (< 10)
    await _handler_mod._handle_tick(short_payload)

    # Act 2: `len(fields) < 10` 동일 ticker 1회 더
    await _handler_mod._handle_tick(short_payload)

    # Act 3: 다른 ticker (000660) 1회
    short_payload_2 = "000660^140000^50000"
    await _handler_mod._handle_tick(short_payload_2)

    # Assert — ticker별 누적 영속
    assert _handler_mod._silent_drop_count.get("005930", 0) == 2, (
        f"G-DISPATCH1 위반 — `005930` 누적 결함: "
        f"{_handler_mod._silent_drop_count.get('005930')} (2 영속)\n"
        f"  시정: `_handle_tick` 영역 `if len(fields) < 10:` 진입 시\n"
        f"  `_silent_drop_count[ticker] = _silent_drop_count.get(ticker, 0) + 1` 추가\n"
        f"  (ticker = `fields[0] if len(fields) >= 1 else \"_unknown\"`)"
    )
    assert _handler_mod._silent_drop_count.get("000660", 0) == 1, (
        f"G-DISPATCH1 위반 — `000660` 누적 결함: "
        f"{_handler_mod._silent_drop_count.get('000660')} (1 영속)"
    )


# ---------------------------------------------------------------------------
# G-DISPATCH2 — `flush_silent_drop_count` 5분 emit + collector clear 영속
# ---------------------------------------------------------------------------
def test_g_dispatch2_flush_silent_drop_count_emit_summary(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """G-DISPATCH2 (MEDIUM): `flush_silent_drop_count()` 호출 시
    `[dispatch_drop_summary] window=300s drops_total=N by_ticker={...}` 1행 emit +
    collector clear 영속 (사이클 74 collector 패턴 답습).

    Red: production 미시정 → 함수 부재 또는 emit 영역 부재 → FAIL.
    Green: backend-dev 시정 후 PASS.

    검증 매트릭스:
    - `flush_silent_drop_count` 함수 존재 영속
    - 호출 시 `[dispatch_drop_summary]` 1행 emit 영속
    - drops_total 집계 정확성 영속
    - emit 후 collector empty 영속 (사이클 74 패턴)
    """
    assert hasattr(_handler_mod, "flush_silent_drop_count"), (
        "G-DISPATCH2 위반 — `flush_silent_drop_count` 함수 신규 영역 부재.\n"
        "  시정: `src/realtime/handler.py` 영역에 함수 추가:\n"
        "    def flush_silent_drop_count() -> None:\n"
        "        if not _silent_drop_count: return\n"
        "        drops_total = sum(_silent_drop_count.values())\n"
        "        by_ticker = dict(_silent_drop_count)\n"
        "        logger.info('[dispatch_drop_summary] window=300s drops_total=%d "
        "by_ticker=%s', drops_total, by_ticker)\n"
        "        _silent_drop_count.clear()"
    )

    # Arrange — collector 적재
    _handler_mod._silent_drop_count.clear()
    _handler_mod._silent_drop_count["005930"] = 3
    _handler_mod._silent_drop_count["000660"] = 1
    caplog.clear()
    caplog.set_level(logging.INFO, logger=_handler_mod.logger.name)

    # Act
    _handler_mod.flush_silent_drop_count()

    # Assert — emit 1행 영속
    matching = [
        rec for rec in caplog.records
        if "[dispatch_drop_summary]" in rec.getMessage()
    ]
    assert len(matching) == 1, (
        f"G-DISPATCH2 위반 — `[dispatch_drop_summary]` 1행 emit 영속 결함 "
        f"(실측 {len(matching)}행):\n"
        + "\n".join(f"  - {rec.getMessage()}" for rec in caplog.records)
    )
    msg = matching[0].getMessage()
    assert "window=300s" in msg, f"G-DISPATCH2 위반 — window 영역 결함: {msg}"
    assert "drops_total=4" in msg, f"G-DISPATCH2 위반 — drops_total 집계 결함: {msg}"
    assert "by_ticker=" in msg, f"G-DISPATCH2 위반 — by_ticker 영역 결함: {msg}"

    # collector clear 영속 (사이클 74 패턴)
    assert _handler_mod._silent_drop_count == {}, (
        f"G-DISPATCH2 위반 — flush 후 collector clear 영속 결함 "
        f"(사이클 74 영속 영역 침범): {_handler_mod._silent_drop_count}"
    )


# ---------------------------------------------------------------------------
# G-DISPATCH3 — empty collector 시 emit 0 (no-op) + 함수 import 가능
# ---------------------------------------------------------------------------
def test_g_dispatch3_empty_collector_no_emit_and_importable(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """G-DISPATCH3 (HIGH): empty collector 상태에서 `flush_silent_drop_count` 호출 시
    emit 0 영속 + `from src.realtime.handler import flush_silent_drop_count` import 가능
    영속 (사이클 78 scheduler import 패턴 영역).

    Red: production 미시정 → ImportError 또는 empty 시 emit 발화 → FAIL.
    Green: backend-dev 시정 후 PASS.
    """
    # 함수 import 가능 영속 (scheduler 의존 영역)
    from src.realtime.handler import flush_silent_drop_count  # noqa: F401

    # Arrange — empty collector
    _handler_mod._silent_drop_count.clear()
    caplog.clear()
    caplog.set_level(logging.INFO, logger=_handler_mod.logger.name)

    # Act
    _handler_mod.flush_silent_drop_count()

    # Assert — emit 0 영속 (Q2 빈 윈도우 skip 영속)
    matching = [
        rec for rec in caplog.records
        if "[dispatch_drop_summary]" in rec.getMessage()
    ]
    assert len(matching) == 0, (
        f"G-DISPATCH3 위반 — empty collector flush 시 emit 0 영속 결함:\n"
        f"  실측 {len(matching)}행 (≥ 1 발화 = 사이클 74 Q2 영역 침범):\n"
        + "\n".join(f"  - {rec.getMessage()}" for rec in matching)
    )
