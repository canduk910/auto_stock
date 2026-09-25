"""cycle363 Red — ①′ 6전략 prepare 가 「직전 영업일」을 일봉 어댑터에 넘긴다.

지시서(정본) = `_workspace/red/cycle363_business_day_freshness_spec.md` §2.5 · §3.1 (18).
설계 = `_workspace/domain_consult/cycle360_boot_reprepare_4a_proposal.md` §1.5 · §3 표 ①′.

────────────────────────────────────────────────────────────────────────────
Green 이 맞춰야 하는 계약
────────────────────────────────────────────────────────────────────────────
1) `StrategyBase._resolve_expected_daily_head(self) -> date | None` (async 인스턴스 메서드)
   = `trading_calendar.previous_trading_day(today_kst())`. 호출 시점에
   `src.engine.trading_calendar.previous_trading_day` 를 **모듈 속성으로** 찾는다(지연 import —
   R1 이 그 이름을 패치한다). never-raise(예외 → None).
   INFO 1행 `[prepare_expected_head] strategy=<id> expected_head=<YYYY-MM-DD|None>`.
2) 6전략 prepare(VB·LTV·donchian·BFB·VCP·kojiro)가 **gather 전에 1회** 그 메서드를 await 하고,
   `_fetch_one` 안의 `get_recent_daily_normalized(..., expected_head=expected_head)` 로 넘긴다
   (종목마다 조회 금지). 휴장일 모름이면 `expected_head=None` 을 **명시해서** 넘긴다.
3) 범위 밖(현행 달력 판정 유지): `kojiro.recompute_held_atr` · `llm_buy_gate` · `tools/`.
   momentum 은 일봉 미사용 — 무접촉.

prepare 구동 대역 = cycle180 `_run_prepare` 답습(`_scan_universe`·`_apply_master_block_filter_in_prepare`
·어댑터·`asyncio.sleep` 패치). 어댑터는 빈 봉을 돌려 이후 가공은 전건 조기 탈락한다 —
이 파일이 재는 것은 **어댑터로 넘어간 인자**뿐이다.

Red 유효성: `_resolve_expected_daily_head` 부재 → `patch.object(..., create=True)` 로 심어도
prepare 가 부르지 않음 → await 횟수 0 / 어댑터 kwargs 에 `expected_head` 부재 → AssertionError.
R 계열 = 메서드 부재 AttributeError.
"""

from __future__ import annotations

import logging
import re
from datetime import date
from unittest.mock import AsyncMock, patch

import pytest
from freezegun import freeze_time

from src.engine.strategies.bull_flag_breakout import BullFlagBreakoutStrategy
from src.engine.strategies.donchian_swing import DonchianSwingStrategy
from src.engine.strategies.kojiro import KojiroStrategy
from src.engine.strategies.long_tail_volatility import LongTailVolatilityStrategy
from src.engine.strategies.vcp_breakout import VcpBreakoutStrategy
from src.engine.strategies.volatility_breakout import VolatilityBreakoutStrategy
from src.engine.strategy_base import StrategyBase, StrategyConfig

pytestmark = pytest.mark.unit

_WED_0923 = date(2026, 9, 23)
_TICKERS = ["005930", "000660", "035420"]
_EXPECTED_MARKER = "[prepare_expected_head] "

_STRATEGIES = {
    "volatility_breakout": VolatilityBreakoutStrategy,
    "long_tail_volatility": LongTailVolatilityStrategy,
    "donchian_swing": DonchianSwingStrategy,
    "bull_flag_breakout": BullFlagBreakoutStrategy,
    "vcp_breakout": VcpBreakoutStrategy,
    "kojiro": KojiroStrategy,
}


def _make(sid: str):
    return _STRATEGIES[sid](StrategyConfig(strategy_id=sid, name=sid, params={}, enabled=True))


async def _run_prepare(strategy, resolver: AsyncMock) -> AsyncMock:
    """prepare 1회 — 반환 = 어댑터 mock (호출 kwargs 검사용)."""
    adapter = AsyncMock(return_value=[])
    with patch.object(
        type(strategy), "_resolve_expected_daily_head", resolver, create=True,
    ), patch.object(
        strategy, "_scan_universe", new=AsyncMock(return_value=list(_TICKERS)),
    ), patch.object(
        strategy, "_apply_master_block_filter_in_prepare",
        new=AsyncMock(return_value=(list(_TICKERS), [])),
    ), patch(
        "src.db.stock_master_daily.get_recent_daily_normalized", new=adapter,
    ), patch(
        # VB RS 관측 훅의 KODEX200(069500) 직접 읽기 — DB 격리 (어댑터 경유 아님)
        "src.db.stock_master_daily.get_recent_daily", new=AsyncMock(return_value=[]),
    ), patch("asyncio.sleep", new=AsyncMock(return_value=None)):
        await strategy.prepare()
    return adapter


# ══════════════════════════════════════════════════════════════════════
# P. 6전략 배선 (18)
# ══════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("sid", list(_STRATEGIES))
async def test_P1_prepare_passes_previous_trading_day_to_adapter(sid):
    """(18) 어댑터 호출마다 `expected_head=<직전 영업일>` (M5 — 넘기지 않으면 붉어진다)."""
    strategy = _make(sid)
    resolver = AsyncMock(return_value=_WED_0923)
    adapter = await _run_prepare(strategy, resolver)

    assert adapter.await_count == len(_TICKERS), f"{sid}: 종목당 어댑터 1회 (실측 {adapter.await_count})"
    heads = [c.kwargs.get("expected_head", "<missing>") for c in adapter.await_args_list]
    assert heads == [_WED_0923] * len(_TICKERS), (
        f"{sid}: 어댑터에 expected_head=2026-09-23 전달 의무 (실측 {heads})"
    )


@pytest.mark.parametrize("sid", list(_STRATEGIES))
async def test_P2_resolved_once_per_prepare_not_per_ticker(sid):
    """(18) 직전 영업일은 prepare 당 1회 계산 — 종목마다 조회 금지."""
    strategy = _make(sid)
    resolver = AsyncMock(return_value=_WED_0923)
    await _run_prepare(strategy, resolver)
    assert resolver.await_count == 1, (
        f"{sid}: `_resolve_expected_daily_head` prepare 당 1회 (실측 {resolver.await_count})"
    )


@pytest.mark.parametrize("sid", list(_STRATEGIES))
async def test_P3_calendar_unknown_passes_explicit_none(sid):
    """(18) 휴장일 모름 → `expected_head=None` 을 명시해 넘긴다 = 어댑터 현행 달력 판정."""
    strategy = _make(sid)
    resolver = AsyncMock(return_value=None)
    adapter = await _run_prepare(strategy, resolver)
    assert adapter.await_count == len(_TICKERS)
    for call in adapter.await_args_list:
        assert "expected_head" in call.kwargs, f"{sid}: expected_head kw 명시 의무"
        assert call.kwargs["expected_head"] is None


@pytest.mark.parametrize("sid", list(_STRATEGIES))
async def test_P4_other_adapter_kwargs_unchanged(sid):
    """행위 보존 — `days`·`min_required` 는 그대로 (cycle173 명세값, donchian 63 하향 금지)."""
    expected_min = {
        "volatility_breakout": 22,
        "long_tail_volatility": 22,
        "donchian_swing": 63,
        "bull_flag_breakout": 35,
        "vcp_breakout": 100,
        "kojiro": None,  # KOJIRO_MIN_REQUIRED 상수 — 아래에서 모듈 값으로 비교
    }[sid]
    if sid == "kojiro":
        from src.engine.strategies.kojiro import KOJIRO_MIN_REQUIRED

        expected_min = KOJIRO_MIN_REQUIRED
    strategy = _make(sid)
    adapter = await _run_prepare(strategy, AsyncMock(return_value=_WED_0923))
    for call in adapter.await_args_list:
        assert call.kwargs.get("min_required") == expected_min, (
            f"{sid}: min_required 변경 금지 (실측 {call.kwargs.get('min_required')!r})"
        )


# ══════════════════════════════════════════════════════════════════════
# R. StrategyBase._resolve_expected_daily_head
# ══════════════════════════════════════════════════════════════════════
def _field(line: str, key: str) -> str | None:
    m = re.search(rf"\b{re.escape(key)}=([^\s]+)", line)
    return m.group(1) if m else None


def _expected_head_lines(caplog) -> list[str]:
    return [
        r.getMessage() for r in caplog.records
        if r.levelno >= logging.INFO and r.getMessage().startswith(_EXPECTED_MARKER)
    ]


async def test_R0_base_method_exists_and_is_coroutine():
    import inspect

    fn = getattr(StrategyBase, "_resolve_expected_daily_head", None)
    assert fn is not None, "StrategyBase._resolve_expected_daily_head 부재"
    assert inspect.iscoroutinefunction(fn), "async 메서드 의무"


async def test_R1_uses_previous_trading_day_of_today_kst(caplog):
    """09-28 아침 → `previous_trading_day(2026-09-28)` 결과(09-23) + INFO 1행."""
    strategy = _make("volatility_breakout")
    prev = AsyncMock(return_value=_WED_0923)
    with freeze_time("2026-09-28T07:46:00+09:00"), patch(
        "src.engine.trading_calendar.previous_trading_day", prev,
    ), caplog.at_level(logging.INFO):
        got = await strategy._resolve_expected_daily_head()
    assert got == _WED_0923
    assert prev.await_count == 1
    call = prev.await_args
    today_arg = call.args[0] if call.args else call.kwargs.get("today")
    assert today_arg == date(2026, 9, 28), f"today = KST 오늘 (실측 {call!r})"
    lines = _expected_head_lines(caplog)
    assert len(lines) == 1, f"INFO 1행 계약 (실측 {lines})"
    assert _field(lines[0], "strategy") == "volatility_breakout", lines[0]
    assert _field(lines[0], "expected_head") == "2026-09-23", lines[0]


async def test_R2_leaf_exception_returns_none_never_raises(caplog):
    strategy = _make("kojiro")
    prev = AsyncMock(side_effect=RuntimeError("leaf bug"))
    with patch("src.engine.trading_calendar.previous_trading_day", prev), caplog.at_level(
        logging.INFO
    ):
        got = await strategy._resolve_expected_daily_head()
    assert got is None, "예외 → None (prepare 를 끊지 않는다)"
    lines = _expected_head_lines(caplog)
    assert len(lines) == 1, f"INFO 1행 계약 (실측 {lines})"
    assert _field(lines[0], "strategy") == "kojiro", lines[0]
    assert _field(lines[0], "expected_head") == "None", lines[0]


async def test_R3_neutralized_calendar_gives_none():
    """전역 중립화(`_lookup_open` → None) 아래 기존 prepare 테스트가 보는 세계 = None."""
    strategy = _make("donchian_swing")
    with freeze_time("2026-09-28T07:46:00+09:00"):
        assert await strategy._resolve_expected_daily_head() is None


async def test_R4_real_leaf_with_fake_calendar_gives_0923(monkeypatch):
    """leaf 실로직 통합 — 09-28 아침, 추석(09-24·25) → 09-23."""
    holidays = {date(2026, 9, 24), date(2026, 9, 25)}

    async def _cal(d):
        return d.weekday() < 5 and d not in holidays

    monkeypatch.setattr("src.engine.trading_calendar._lookup_open", _cal)
    strategy = _make("vcp_breakout")
    with freeze_time("2026-09-28T07:46:00+09:00"):
        assert await strategy._resolve_expected_daily_head() == _WED_0923
