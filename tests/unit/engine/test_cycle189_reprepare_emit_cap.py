"""사이클 189 (2026-07-02) Red — `_reprepare_breakout_if_empty` WARNING DailyEmitCap.

출처: 7/1 daily_log_reports finding F1 — BFB/VCP "후보 비어있음 재 prepare" WARNING
101건×4/일. `scheduler.py::_reprepare_breakout_if_empty` 가 5분 scan_loop 마다 빈
전략별 무제한 발화 (logger.warning + write_log DB INSERT) → 하루 ~400행. 후보 0건은
정상 장세 가능 (VCP 0/65 일상).

시정: `DailyEmitCap[str]` (사이클 31 R6 / 158 momentum 패턴 답습) 로 **로그 emit 만**
1회/전략/일 cap. **`strategy.prepare()` 재시도 행위 자체는 불변** (사이클 48 회복
메커니즘 절대 보존) — cap 은 logger.warning + write_log 두 줄만 감쌈. `_reset_daily_state()`
에 `reset_daily()` 동행 배선 (다음 영업일 재발화).

Red 유효성 (현재 코드 = cap 미존재):
- C-1/C-2/C-4/C-5 cap 케이스: FAIL — 매 호출 무제한 emit.
- C-3 (SAFETY) prepare 매 호출 실행: PASS (불변식, 현재도 매 호출 prepare).

설계 메모: `_workspace/red/cycle189_db_read_retry_expand_and_reprepare_cap.md` 영역 B.
"""

from __future__ import annotations

import contextlib
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.engine.scheduler import TradingScheduler

pytestmark = pytest.mark.unit

_SCHED_LOGGER = "src.engine.scheduler"
_REPREPARE_TARGETS = (
    "volatility_breakout",
    "long_tail_volatility",
    "bull_flag_breakout",
    "vcp_breakout",
)


def _make_empty_strategy(sid: str) -> MagicMock:
    """후보 비어있는 (get_scanned_tickers=[]) 전략 mock — prepare 성공 AsyncMock."""
    strategy = MagicMock(name=f"strategy-{sid}")
    strategy.config = MagicMock()
    strategy.config.enabled = True
    strategy.strategy_id = sid
    strategy.get_scanned_tickers = MagicMock(return_value=[])
    strategy.prepare = AsyncMock(return_value=None)
    return strategy


@contextlib.contextmanager
def _arm(sched: TradingScheduler, mapping: dict[str, MagicMock]):
    """registry.get → mapping (미매핑 sid=None) + write_log AsyncMock patch.

    Yields:
        write_log AsyncMock (호출 검증용).
    """
    write_log_mock = AsyncMock(return_value=None)
    with patch.object(sched.registry, "get", side_effect=lambda s: mapping.get(s)), \
         patch("src.engine.scheduler.write_log", write_log_mock):
        yield write_log_mock


def _warn_records(caplog) -> list:
    """"재 prepare 시도" WARNING 레코드만 필터."""
    return [
        r
        for r in caplog.records
        if r.levelname == "WARNING" and "재 prepare 시도" in r.getMessage()
    ]


def _warn_write_log_calls(write_log_mock: AsyncMock) -> list:
    """write_log("WARNING", "... 재 prepare 시도") 호출만 필터 (ERROR 분기 제외)."""
    return [
        c
        for c in write_log_mock.call_args_list
        if c.args and c.args[0] == "WARNING" and "재 prepare 시도" in str(c.args[1:])
    ]


# ---------------------------------------------------------------------------
# C-1 — 동일 sid 2회 연속 호출 → WARNING logger 1회만 (caplog). Red 핵심.
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_C1_same_sid_warning_capped_once(caplog):
    """동일 sid 2회 reprepare → logger.warning "재 prepare 시도" 1회만.

    현행 (cap 미존재) = 매 호출 무제한 emit → 2회 (Red FAIL).
    """
    sched = TradingScheduler()
    vb = _make_empty_strategy("volatility_breakout")
    mapping = {"volatility_breakout": vb}

    with _arm(sched, mapping):
        with caplog.at_level("WARNING", logger=_SCHED_LOGGER):
            await sched._reprepare_breakout_if_empty()
            await sched._reprepare_breakout_if_empty()

    warns = _warn_records(caplog)
    assert len(warns) == 1, (
        f"동일 sid WARNING 1회 cap 기대, 실제 {len(warns)}회 (현행 무제한 = Red FAIL)"
    )


# ---------------------------------------------------------------------------
# C-2 — 동일 sid 2회 연속 호출 → write_log 1회만 (DB INSERT cap)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_C2_same_sid_write_log_capped_once(caplog):
    """동일 sid 2회 reprepare → write_log("WARNING", ...) 1회만 (DB INSERT 폭주 차단).

    현행 (cap 미존재) = 매 호출 write_log → 2회 (Red FAIL).
    """
    sched = TradingScheduler()
    vb = _make_empty_strategy("volatility_breakout")
    mapping = {"volatility_breakout": vb}

    with _arm(sched, mapping) as write_log_mock:
        with caplog.at_level("WARNING", logger=_SCHED_LOGGER):
            await sched._reprepare_breakout_if_empty()
            await sched._reprepare_breakout_if_empty()

    calls = _warn_write_log_calls(write_log_mock)
    assert len(calls) == 1, (
        f"동일 sid write_log 1회 cap 기대, 실제 {len(calls)}회 (현행 무제한 = Red FAIL)"
    )


# ---------------------------------------------------------------------------
# C-3 (SAFETY) — cap 발동 중에도 prepare() 는 매 호출 실행 (재시도 행위 불변). 불변식.
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_C3_prepare_always_invoked_even_when_capped(caplog):
    """동일 sid 2회 reprepare → prepare() 2회 실행 (cap 은 log 만, 회복 메커니즘 보존).

    사이클 48 회복 메커니즘 절대 보존 — cap 이 prepare 재시도를 억제하면 안 됨.
    현재도 PASS (불변식) — Green 후에도 prepare 매 호출 유지 영구 가드.
    """
    sched = TradingScheduler()
    vb = _make_empty_strategy("volatility_breakout")
    mapping = {"volatility_breakout": vb}

    with _arm(sched, mapping):
        with caplog.at_level("WARNING", logger=_SCHED_LOGGER):
            await sched._reprepare_breakout_if_empty()
            await sched._reprepare_breakout_if_empty()

    assert vb.prepare.await_count == 2, (
        "prepare() 는 cap 무관 매 호출 실행 의무 (사이클 48 회복 메커니즘 보존)"
    )


# ---------------------------------------------------------------------------
# C-4 — sid 별 독립 cap (bfb 1회 + vcp 1회 각각 cap, 서로 격리)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_C4_per_sid_independent_cap(caplog):
    """bfb + vcp 둘 다 비어있음 → 2회 reprepare → 각 sid WARNING 1회씩 (독립 cap).

    현행 (cap 미존재) = 각 sid 2회씩 emit (Red FAIL). Green = sid별 1회씩.
    """
    sched = TradingScheduler()
    bfb = _make_empty_strategy("bull_flag_breakout")
    vcp = _make_empty_strategy("vcp_breakout")
    mapping = {"bull_flag_breakout": bfb, "vcp_breakout": vcp}

    with _arm(sched, mapping):
        with caplog.at_level("WARNING", logger=_SCHED_LOGGER):
            await sched._reprepare_breakout_if_empty()
            await sched._reprepare_breakout_if_empty()

    bfb_warns = [r for r in _warn_records(caplog) if "bull_flag_breakout" in r.getMessage()]
    vcp_warns = [r for r in _warn_records(caplog) if "vcp_breakout" in r.getMessage()]
    assert len(bfb_warns) == 1, f"bfb WARNING 1회 cap 기대, 실제 {len(bfb_warns)}회 (Red FAIL)"
    assert len(vcp_warns) == 1, f"vcp WARNING 1회 cap 기대, 실제 {len(vcp_warns)}회 (Red FAIL)"


# ---------------------------------------------------------------------------
# C-5 — _reset_daily_state() 후 재발화 가능 (reset 배선)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_C5_reset_daily_state_rearms_cap():
    """reprepare(emit) → reprepare(capped) → _reset_daily_state() → reprepare(재emit).

    총 WARNING 2회 (emit1 + 재emit) 기대 — 중간 capped 1회 + reset 재발화 배선 검증.
    현행 (cap 미존재 + reset 배선 없음) = 매 호출 emit → 3회 (Red FAIL).
    """
    sched = TradingScheduler()
    vb = _make_empty_strategy("volatility_breakout")
    mapping = {"volatility_breakout": vb}

    # `_reset_daily_state` registry 순회/order_engine/purge 격리 (cycle61/185 답습)
    reset_ctx = (
        patch.object(sched.registry, "all", return_value=[]),
        patch.object(
            sched,
            "order_engine",
            MagicMock(
                _selling=set(),
                _filled_qty={},
                _order_qty={},
                _order_strategy={},
                _order_ticker={},
                _pending_buy_orders={},
                _pending_cancel_tasks={},
                reset_daily_state=MagicMock(),
            ),
        ),
        patch.object(sched, "risk_manager", MagicMock(reset_daily_state=MagicMock())),
        patch(
            "src.db.pending_next_day_clear.purge_pending_ndc_before",
            new=AsyncMock(return_value=None),
        ),
    )

    warn_mock = MagicMock()

    with _arm(sched, mapping):
        with patch.object(
            __import__("src.engine.scheduler", fromlist=["logger"]).logger,
            "warning",
            warn_mock,
        ):
            await sched._reprepare_breakout_if_empty()   # emit 1
            await sched._reprepare_breakout_if_empty()   # capped (Green)
            with contextlib.ExitStack() as stack:
                for cm in reset_ctx:
                    stack.enter_context(cm)
                sched._reset_daily_state()               # cap 재발화 배선
            await sched._reprepare_breakout_if_empty()   # 재 emit (Green)

    reprepare_warns = [
        c for c in warn_mock.call_args_list
        if c.args and "재 prepare 시도" in str(c.args[0])
    ]
    assert len(reprepare_warns) == 2, (
        f"reset 후 재발화 = 총 WARNING 2회 기대, 실제 {len(reprepare_warns)}회 "
        "(현행 cap+reset 배선 부재 = 3회 = Red FAIL)"
    )
