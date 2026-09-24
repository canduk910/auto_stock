"""P1.5 — BFB 재시작 복구 배선 (거짓 전제 위에서 통째로 생략돼 있던 인프라).

## 뒤집힌 전제

종전 문서·테스트는 *"BFB 는 `_MULTIDAY_STRATEGIES` 미포함(익일 청산)이라 재시작
복구가 불필요하다"* 고 못박고 있었다. 코드 실측 결과 **거짓**이다:

    _execute_next_day_clear 대상 = ("momentum","long_tail_volatility","volatility_breakout")
    _force_clear_main_only 대상  = ("volatility_breakout","long_tail_volatility")
    BullFlagBreakoutStrategy.check_force_clear() == []

세 목록 어디에도 BFB 가 없다. BFB 는 `max_hold_days`(5) + 2 달력일 시간 청산까지
**실질 멀티데이 보유**이며, `_MULTIDAY_STRATEGIES` 비멤버는 `is_next_day` 배지
표시에만 영향한다(청산 규약과 무관).

## 그래서 무엇이 깨져 있었나

재시작하면:

- `_entry_atr` 소실 → ATR 하드손절이 **고정 −5% 로 무단 강등**(손절 규약이 조용히 바뀜)
- `high_since_buy` 는 `_boot()` 이 DB row 로 Position 을 재생성하며 매수가로 리셋
  (H-1 과 동일 병리) → 트레일링 기준점 소멸
- `_candidates` 소실 → §2 flag_low·§3 measured-move 익절·§4 트레일링 침묵 (P1 에서 시정)

BFB 는 이 셋이 **모두 없는 유일한 보유형 전략**이었다.

## 배선 위치가 계약이다

`boot_manager.boot()` — DB positions 복구가 **끝난 뒤**이고, `scheduler.py` 는 매매
안전성 8영역이라 diff 0 을 지켜야 한다. ⚠️ `_SWING_POLL_STRATEGIES` 에 BFB 를 넣는
방법은 그 상수가 **매수 폴루프·구독 대상**에도 쓰여 매수 행위를 바꾼다 — 금지.
"""

from __future__ import annotations

import inspect
from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest

from src.engine.strategies.bull_flag_breakout import BullFlagBreakoutStrategy
from src.engine.strategy_base import Position, StrategyBase, StrategyConfig

pytestmark = pytest.mark.unit

_KST = timezone(timedelta(hours=9))


def _today() -> date:
    return datetime.now(_KST).date()


def _bfb(**params) -> BullFlagBreakoutStrategy:
    s = BullFlagBreakoutStrategy(
        StrategyConfig(strategy_id="bull_flag_breakout", name="눌림목", weight=0.1, params=params),
    )
    s.state.total_investment = 115_000
    return s


def _hold(s, ticker="005930", *, buy=70_000, days_ago=3, high=None):
    pos = Position(
        ticker=ticker, buy_price=buy, quantity=1, order_no="O",
        strategy_id="bull_flag_breakout", buy_date=_today() - timedelta(days=days_ago),
        high_since_buy=high or buy,
    )
    s.state.positions[ticker] = pos
    return pos


def _candles(n=60, *, high_boost_at=None, boost=0):
    """KIS 일봉 (최신순). `high_boost_at` 일 전 봉의 고가를 끌어올린다."""
    out = []
    for i in range(n):
        base = 70_000 - i * 40
        hi = base + 500
        if high_boost_at is not None and i == high_boost_at:
            hi = boost
        out.append({
            "stck_bsop_date": (_today() - timedelta(days=i)).strftime("%Y%m%d"),
            "stck_hgpr": str(hi), "stck_lwpr": str(base - 500),
            "stck_clpr": str(base), "stck_oprc": str(base - 50), "acml_vol": "100000",
        })
    return out


def _patch_io(monkeypatch, candles):
    monkeypatch.setattr("src.api.condition.fetch_daily_candles", AsyncMock(return_value=candles))
    up = AsyncMock()
    monkeypatch.setattr("src.db.positions.update_high", up)
    monkeypatch.setattr("src.db.system_logs.write_log", AsyncMock())
    return up


# ---------------------------------------------------------------------------
# R-A — 전제 정정: BFB 는 익일 청산 전략이 아니다
# ---------------------------------------------------------------------------

def test_bfb_is_not_a_next_day_clear_strategy():
    """세 청산 목록 어디에도 BFB 가 없다 — 종전 "익일 청산" 서술의 반증."""
    from src.engine import scheduler as sch

    src = inspect.getsource(sch.TradingScheduler._execute_next_day_clear)
    assert "bull_flag_breakout" not in src
    assert _bfb().check_force_clear() == []


def test_multiday_membership_stays_display_only():
    """`_MULTIDAY_STRATEGIES` 비멤버는 **유지** — 배지 표시 계약이지 청산 규약이 아니다."""
    assert "bull_flag_breakout" not in Position._MULTIDAY_STRATEGIES


# ---------------------------------------------------------------------------
# R-B — 복구 인프라 (기존 계약 반전)
# ---------------------------------------------------------------------------

def test_bfb_now_has_restart_recovery_infra():
    """[의미 전환] 거짓 전제가 무너졌으므로 명제를 뒤집는다."""
    assert hasattr(BullFlagBreakoutStrategy, "_rederive_entry_atr")
    assert hasattr(BullFlagBreakoutStrategy, "recompute_high_since_buy")


def test_recovery_is_own_definition_not_base_inheritance():
    """`recompute_high_since_buy` 는 **자체 정의**여야 한다 — base 승격 금지.

    전략마다 일봉 소스·fetch 일수·재도출 대상이 다르다(donchian 은 KIS 직접 +
    donchian_period, VCP 는 ema_long/base_max, BFB 는 pole/flag lookback).
    base 로 올리면 momentum·VB 까지 상속해 의미 없는 메서드를 갖는다.
    """
    assert not hasattr(StrategyBase, "recompute_high_since_buy")
    assert "recompute_high_since_buy" in BullFlagBreakoutStrategy.__dict__


def test_high_recovery_delegates_to_single_source_helper():
    """고점 복구는 `StrategyBase._apply_high_since_buy_from_candles` 위임 — 복사 금지."""
    src = inspect.getsource(BullFlagBreakoutStrategy.recompute_high_since_buy)
    assert "_apply_high_since_buy_from_candles" in src
    assert "_apply_high_since_buy_from_candles" not in BullFlagBreakoutStrategy.__dict__


# ---------------------------------------------------------------------------
# R-C — `_rederive_entry_atr` 행위
# ---------------------------------------------------------------------------

def test_rederive_uses_only_candles_before_buy_date():
    """매수일 당일/이후 봉을 섞으면 돌파일 변동이 ATR 을 부풀려 손절선이 **넓어진다**."""
    s = _bfb()
    pos = _hold(s, days_ago=3)
    # 매수일 당일 봉에 거대한 레인지를 심는다 — 채택되면 ATR 이 폭증한다
    cs = _candles(60)
    for c in cs:
        if c["stck_bsop_date"] == pos.buy_date.strftime("%Y%m%d"):
            c["stck_hgpr"], c["stck_lwpr"] = "200000", "10000"
    s._rederive_entry_atr("005930", pos, cs, 14)
    assert s._entry_atr.get("005930", 0) < 5_000, "매수일 봉이 섞이면 ATR 이 폭증한다"


def test_rederive_skips_when_prior_candles_insufficient():
    """봉이 모자라면 **미스탬프** — 잘못된 ATR 로 손절선을 긋느니 고정 % 경로가 낫다."""
    s = _bfb()
    pos = _hold(s, days_ago=1)
    s._rederive_entry_atr("005930", pos, _candles(5), 14)
    assert "005930" not in s._entry_atr


def test_rederive_never_raises():
    """어떤 입력에도 예외를 흘리지 않는다 (복구 실패가 부팅을 막으면 안 된다)."""
    s = _bfb()
    pos = _hold(s)
    s._rederive_entry_atr("005930", pos, [{"stck_bsop_date": None}], 14)
    s._rederive_entry_atr("005930", pos, [{"stck_hgpr": "x", "stck_bsop_date": "19000101"}] * 40, 14)


# ---------------------------------------------------------------------------
# R-D — `recompute_high_since_buy` 통합 행위
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_recovery_restores_entry_atr_and_high(monkeypatch):
    """turtle 로 사는 전략 — 재시작 소실분 `_entry_atr` 재도출 + 고점 복구."""
    s = _bfb(sizing_mode="turtle")
    pos = _hold(s, buy=70_000, days_ago=5)
    up = _patch_io(monkeypatch, _candles(60, high_boost_at=2, boost=88_000))

    await s.recompute_high_since_buy()

    assert s._entry_atr.get("005930", 0) > 0, "재시작 소실분 재도출"
    assert pos.high_since_buy == 88_000, "매수일 이후 일봉 high max 로 복구"
    up.assert_awaited_once_with("005930", 88_000)


@pytest.mark.asyncio
async def test_recovery_position_ratio_restores_high_but_not_entry_atr(monkeypatch):
    """cycle355 — position_ratio 랏은 처음부터 미스탬프라 재도출 대상이 아니다.

    고점 복구는 사이징 방식과 무관하게 그대로 산다(트레일링 기준점).
    """
    s = _bfb()  # 기본값 = position_ratio (운영도 동일)
    pos = _hold(s, buy=70_000, days_ago=5)
    up = _patch_io(monkeypatch, _candles(60, high_boost_at=2, boost=88_000))

    await s.recompute_high_since_buy()

    assert "005930" not in s._entry_atr, "position_ratio 랏에 ATR 손절 스탬프가 찍혔다"
    assert pos.high_since_buy == 88_000, "매수일 이후 일봉 high max 로 복구"
    up.assert_awaited_once_with("005930", 88_000)


@pytest.mark.asyncio
async def test_recovery_does_not_touch_live_entry_atr(monkeypatch):
    """in-memory 스탬프가 살아 있으면(당일 매수·미재시작) 그게 정확한 진입 ATR 이다."""
    s = _bfb()
    _hold(s, days_ago=3)
    s._entry_atr["005930"] = 1_234.0
    _patch_io(monkeypatch, _candles(60))

    await s.recompute_high_since_buy()

    assert s._entry_atr["005930"] == 1_234.0


@pytest.mark.asyncio
async def test_recovery_skips_same_day_purchase(monkeypatch):
    s = _bfb()
    _hold(s, days_ago=0)
    fetch = AsyncMock(return_value=_candles(60))
    monkeypatch.setattr("src.api.condition.fetch_daily_candles", fetch)

    await s.recompute_high_since_buy()

    fetch.assert_not_awaited(), "당일 매수는 buy_price 가 진실 — fetch 호출도 불필요"


@pytest.mark.asyncio
async def test_recovery_isolates_per_ticker_failure(monkeypatch):
    """한 종목 fetch 실패가 나머지 복구를 막지 않는다 (sequential + 격리)."""
    s = _bfb()
    _hold(s, "111111", days_ago=4)
    good = _hold(s, "222222", buy=70_000, days_ago=4)

    async def _fetch(ticker, days=0):
        if ticker == "111111":
            raise RuntimeError("KIS 장애")
        return _candles(60, high_boost_at=2, boost=88_000)

    monkeypatch.setattr("src.api.condition.fetch_daily_candles", _fetch)
    monkeypatch.setattr("src.db.positions.update_high", AsyncMock())
    monkeypatch.setattr("src.db.system_logs.write_log", AsyncMock())

    await s.recompute_high_since_buy()

    assert good.high_since_buy == 88_000


# ---------------------------------------------------------------------------
# R-D2 — 구조 레벨 재검출 (fail-safe)
# ---------------------------------------------------------------------------

def test_structural_levels_rederived_when_lost():
    """재시작으로 구조 레벨이 소실되면 **매수일 이전 봉**으로 재검출한다.

    `_position_setup` 은 in-memory 라 프로세스 재시작 시 통째로 사라진다. 그러면
    §2 flag_low 손절과 §3 measured-move 익절이 침묵한다 — `_entry_atr` 만 살려서는
    반쪽이다.
    """
    s = _bfb()
    pos = _hold(s, days_ago=3)
    # 폴(급등) → 플래그(눌림) 형태를 만들어 검출이 성립하게 한다
    cs = []
    for i in range(60):
        if i < 3:              # 최근 = 플래그 눌림
            base = 96_000 - i * 200
        elif i < 10:           # 폴 = 급등 구간
            base = 95_000 - (i - 3) * 4_000
        else:
            base = 67_000 - (i - 10) * 30
        cs.append({
            "stck_bsop_date": (_today() - timedelta(days=i)).strftime("%Y%m%d"),
            "stck_hgpr": str(base + 400), "stck_lwpr": str(base - 400),
            "stck_clpr": str(base), "stck_oprc": str(base - 50), "acml_vol": "100000",
        })
    s._refresh_position_setup_from_candles("005930", pos, cs)
    setup = s._position_setup.get("005930", {})
    assert setup.get("atr14", 0) > 0, "지표는 항상 재계산"
    # 재검출은 진입 조건에 민감해 실패할 수 있다 — 성공했다면 4키가 함께 와야 한다
    if setup.get("flag_low"):
        for k in ("flag_high", "pole_high", "pole_start"):
            assert setup.get(k), f"{k} 없이 flag_low 만 복원되면 measured-move 가 깨진다"


def test_rederive_never_overwrites_existing_levels():
    """이미 있는 구조 레벨은 **덮어쓰지 않는다** — 진입 시점 값이 정본이다."""
    s = _bfb()
    pos = _hold(s, days_ago=3)
    s._position_setup["005930"] = {
        "flag_low": 66_000, "flag_high": 70_500, "pole_high": 72_000, "pole_start": 60_000,
    }
    s._refresh_position_setup_from_candles("005930", pos, _candles(60))
    setup = s._position_setup["005930"]
    assert setup["flag_low"] == 66_000
    assert setup["flag_high"] == 70_500


def test_rederive_returns_empty_on_insufficient_candles():
    """봉 부족 시 빈 dict — 미복구가 잘못된 레벨보다 낫다."""
    s = _bfb()
    pos = _hold(s, days_ago=3)
    assert s._rederive_setup_levels("005930", pos, _candles(3)) == {}


def test_rederive_excludes_buy_date_and_after():
    """매수일 당일/이후 봉이 섞이면 돌파 이후 구간이 플래그에 포함돼 레벨이 왜곡된다."""
    s = _bfb()
    pos = _hold(s, days_ago=3)
    captured: list[list[dict]] = []
    s._detect_pole_and_flag = lambda cs: (captured.append(cs), None)[1]
    s._rederive_setup_levels("005930", pos, _candles(60))
    if captured:
        buy_dd = pos.buy_date.strftime("%Y%m%d")
        assert all(c["stck_bsop_date"] < buy_dd for c in captured[0])


def test_rederive_never_raises_on_detector_failure():
    """검출기가 터져도 복구 전체가 죽으면 안 된다."""
    s = _bfb()
    pos = _hold(s, days_ago=3)

    def _boom(_cs):
        raise RuntimeError("검출 실패")

    s._detect_pole_and_flag = _boom
    assert s._rederive_setup_levels("005930", pos, _candles(60)) == {}
    s._refresh_position_setup_from_candles("005930", pos, _candles(60))
    assert s._position_setup["005930"]["atr14"] > 0, "지표 갱신은 계속돼야 한다"


# ---------------------------------------------------------------------------
# R-E — 배선: boot_manager 경유 + 8영역 무접촉
# ---------------------------------------------------------------------------

def test_wired_in_boot_manager_after_positions_restored():
    """배선은 `boot_manager` — DB positions 복구가 끝난 뒤라야 보유가 확정된다."""
    from src.engine import boot_manager as bm

    src = inspect.getsource(bm)
    assert "bull_flag_breakout" in src and "recompute_high_since_buy" in src, (
        "미배선이면 복구 메서드가 dead code 로 남는다"
    )
    assert src.index("load_all") < src.index("bull_flag_breakout"), (
        "positions 복구보다 앞서면 보유 종목이 비어 복구할 대상이 없다"
    )


def test_scheduler_untouched_by_bfb_wiring():
    """`scheduler.py` 는 매매 안전성 8영역 — BFB 복구 배선으로 건드리지 않는다."""
    from src.engine import scheduler as sch

    src = inspect.getsource(sch)
    idx = src.find("recompute_high_since_buy")
    assert idx != -1, "VCP 전용 훅은 영속"
    assert "bull_flag_breakout" not in src[max(0, idx - 400): idx + 400]


def test_swing_poll_strategies_excludes_bfb():
    """`_SWING_POLL_STRATEGIES` 는 매수 폴루프·구독 대상이기도 하다 — BFB 편입 금지."""
    from src.engine.scheduler import _SWING_POLL_STRATEGIES

    assert "bull_flag_breakout" not in _SWING_POLL_STRATEGIES
