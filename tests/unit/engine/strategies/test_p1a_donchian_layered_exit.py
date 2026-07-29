"""P1-A Red — donchian 청산 상태 견고성 + 레이어드 청산.

명세: `_workspace/red/_behaviors_p1_20260729.md` 사이클 A / 자문:
`_workspace/domain_consult/cycle_weekly_review_20260729.md`.

## 근본 결함 (team-leader 진단)

`check_exit_signal` 의 ATR 트레일링(L995-1006)이 트레일링 폭 ATR 을
`self._candidates.get(ticker)["atr"]` 에서만 읽는다. `_candidates` 는 매일 prepare 가
새 20일 신고가 후보로 재구성 → 보유 종목이 후보 이탈하면 `info=None` → `atr=0` →
트레일링 분기 영구 침묵. 하드손절만 `_entry_atr` 폴백 보유 → 관측된 "백스톱만 발화"
(096770 +15.8% → -9% 반납 / 017670 +7.5% → -9.1%).

## 행위 (RED — 신규 구현 필요)

- A-1 (버그픽스, HIGH): 트레일링 ATR 은 `_candidates` miss 시 `_entry_atr` 폴백.
- A-2 (버그픽스): `_breakout_high` 재시작 후 보유 종목 재도출.
- A-3 (신규): 브레이크이븐 승격 (high ≥ buy+1.5×entry_atr 이력 후 손절선 max(기존, buy)).
- A-4 (신규): 10일 저가 채널 이탈 → TRAILING_STOP (`channel_exit_period=10`, 0=off).
- A-5 (회귀 0): 기존 백스톱/2ATR/시간청산/-7% 케이스 보존.
- A-6 (자문 검증): 096770 시나리오 — 트레일링/채널 청산이 백스톱 이전에 발화.

## 인터페이스 계약 (tdd-engineer 확정 — backend-dev 구현 대상)

- A-4 채널 데이터는 `_candidates` 와 독립인 전용 dict `self._channel_low: dict[str, int]`
  (`_entry_atr`/`_breakout_high` 선례) 에 prepare/recompute 시점 저장. on_tick KIS 호출 금지.
- A-2 `_breakout_high` 재도출은 `recompute_held_atr` (boot/저녁 훅) 에서 buy_date 이전
  일봉의 20일 신고가로 수행 (`_rederive_entry_atr` 선례).
- 신규 DEFAULT_PARAMS: `breakeven_promote_atr=1.5` / `channel_exit_period=10`
  (PARAM_RANGES 미편입 — 전략 정체성 상수).
"""

from __future__ import annotations

import datetime as _dt
from unittest.mock import AsyncMock, patch

import pytest

from src.engine.strategies.donchian_swing import DonchianSwingStrategy
from src.engine.strategy_base import Position, Signal, StrategyConfig
from src.engine.recommendation_engine import PARAM_RANGES

pytestmark = pytest.mark.unit
KST = _dt.timezone(_dt.timedelta(hours=9))


def _mk(sizing_mode="turtle", **params):
    cfg = StrategyConfig(strategy_id="donchian_swing", name="도치안", weight=0.2,
                         params={"sizing_mode": sizing_mode, **params})
    s = DonchianSwingStrategy(cfg)
    s.state.total_investment = 100_000_000
    return s


def _pos(ticker="096770", buy_price=117_300, high_since_buy=0, buy_date=None):
    p = Position(ticker=ticker, buy_price=buy_price, quantity=10, order_no="O",
                 strategy_id="donchian_swing", buy_date=buy_date or _dt.date(2026, 7, 27))
    p.high_since_buy = high_since_buy
    return p


def _candles_desc(dates_ohlc):
    """dates_ohlc = [(yyyymmdd, high, low, close), ...] DESC (idx0=최신)."""
    return [{"stck_bsop_date": d, "stck_hgpr": str(h), "stck_lwpr": str(lo), "stck_clpr": str(c)}
            for d, h, lo, c in dates_ohlc]


# ─────────────────────────────────────────────────────────────────────────
# A-1 (HIGH) — 트레일링 ATR 은 _candidates miss 시 _entry_atr 폴백
# ─────────────────────────────────────────────────────────────────────────
def test_A1_trailing_uses_entry_atr_when_candidates_miss():
    """보유 종목이 _candidates 에서 이탈(당일 후보 아님)했으나 _entry_atr 스탬프는 남아있다.

    현행: _candidates miss → atr=0 → 트레일링 분기 침묵 → NONE (결함).
    기대: _entry_atr(5300) 폴백 → chandelier = 135800 - 2×5300 = 125200,
          현재가 125000 ≤ 125200 → TRAILING_STOP.
    (base_stop=117300-10600=106700 / backstop -9%=@106743 모두 하회 안 함 → 트레일링만 발화)
    """
    s = _mk()
    s.state.positions["096770"] = _pos(high_since_buy=135_800)
    s._entry_atr["096770"] = 5_300.0
    # _candidates 에 없음 (후보 이탈 재현) — 결함 트리거
    assert "096770" not in s._candidates
    sig = s.check_exit_signal("096770", 125_000, 117_300)
    assert sig == Signal.TRAILING_STOP, (
        f"A-1: _candidates miss + _entry_atr 폴백 트레일링 기대 TRAILING_STOP, got {sig}"
    )


def test_A1_trailing_entry_atr_fallback_holds_above_chandelier():
    """폴백 트레일링선 위에서는 발화하지 않음 (경계 정확성)."""
    s = _mk()
    s.state.positions["096770"] = _pos(high_since_buy=135_800)
    s._entry_atr["096770"] = 5_300.0
    # 125_300 > chandelier 125_200 → 트레일 없음, 하드손절/백스톱도 아님 → NONE
    assert s.check_exit_signal("096770", 125_300, 117_300) == Signal.NONE


# ─────────────────────────────────────────────────────────────────────────
# A-2 — _breakout_high 재시작 후 보유 종목 재도출 (recompute_held_atr 훅)
# ─────────────────────────────────────────────────────────────────────────
async def test_A2_breakout_high_rederived_on_recompute():
    """재시작 시 _breakout_high 소실 → recompute_held_atr 가 buy_date 이전 20일 신고가로 재도출.

    현행: recompute_held_atr 는 _breakout_high 를 채우지 않음 → 시간청산(L984) breakout_high=0
          분기 영구 침묵 (결함).
    기대: buy_date(2026-07-27) 이전 봉의 20일 최고가로 _breakout_high 재도출.
    """
    s = _mk()
    buy_date = _dt.date(2026, 7, 27)
    s.state.positions["096770"] = _pos(buy_date=buy_date)
    # 재시작 재현 — _breakout_high 비어있음
    assert "096770" not in s._breakout_high
    # buy_date 이전(<0727) 봉: 20일 최고가 = 130000, 매수 후 봉은 재도출에서 제외되어야 함
    pre = [(f"202607{d:02d}", 130_000 if d == 20 else 120_000, 115_000, 118_000)
           for d in range(26, 6, -1)]  # 20봉 DESC, 0726..0707
    post = [(f"202607{d:02d}", 140_000, 130_000, 135_000) for d in (28, 27)]  # 매수 당일/이후
    candles = _candles_desc(post + pre)
    with patch("src.api.condition.fetch_daily_candles", new=AsyncMock(return_value=candles)), \
         patch("src.engine.strategies.donchian_swing.datetime") as _dtmock:
        _dtmock.now.return_value = _dt.datetime(2026, 7, 29, 8, 0, tzinfo=KST)
        s._apply_high_since_buy_from_candles = AsyncMock()
        await s.recompute_held_atr()
    assert s._breakout_high.get("096770", 0) == 130_000, (
        f"A-2: buy_date 이전 20일 신고가(130000) 재도출 기대, got {s._breakout_high.get('096770')}"
    )


# ─────────────────────────────────────────────────────────────────────────
# A-3 — 브레이크이븐 승격 (high ≥ buy+1.5×entry_atr 이력 → 손절선 max(기존, buy))
# ─────────────────────────────────────────────────────────────────────────
def test_A3_breakeven_promotion_triggers_stop_at_buy_price():
    """high_since_buy 가 buy+1.5×entry_atr 도달 이력 → 손절선 buy_price 로 승격.

    현행: 하드손절 base=buy-2×entry_atr(106700), 현재가 buy-1틱 → 손절 안 됨 → NONE (결함).
    기대: high(126000) ≥ buy(117300)+1.5×5300(125250) 이력 → 손절선 max(106700, 117300)=117300
          → 현재가 117200(buy-1틱) ≤ 117300 → STOP_LOSS.
    """
    s = _mk()
    # high_since_buy = 126000 (승격 트리거 이력 성립)
    s.state.positions["096770"] = _pos(buy_price=117_300, high_since_buy=126_000)
    s._entry_atr["096770"] = 5_300.0
    s._candidates["096770"] = {"atr": 5_300}  # 트레일링 경로 영향 배제 (high-2atr=115400<117200)
    sig = s.check_exit_signal("096770", 117_200, 117_300)
    assert sig == Signal.STOP_LOSS, (
        f"A-3: 브레이크이븐 승격 후 buy-1틱 STOP_LOSS 기대, got {sig}"
    )


def test_A3_breakeven_not_promoted_without_history():
    """승격 이력 미성립(high < buy+1.5×entry_atr) → 손절선 승격 안 함 (회귀 보존).

    high(120000) < 125250 → 승격 없음 → 현재가 117200 은 base_stop(106700) 위 → NONE.
    """
    s = _mk()
    s.state.positions["096770"] = _pos(buy_price=117_300, high_since_buy=120_000)
    s._entry_atr["096770"] = 5_300.0
    s._candidates["096770"] = {"atr": 5_300}
    assert s.check_exit_signal("096770", 117_200, 117_300) == Signal.NONE


# ─────────────────────────────────────────────────────────────────────────
# A-4 — 10일 저가 채널 이탈 → TRAILING_STOP (channel_exit_period=10)
# ─────────────────────────────────────────────────────────────────────────
def test_A4_channel_exit_fires_below_10day_low():
    """현재가 < 최근 10영업일 최저가 → TRAILING_STOP (터틀 정본 채널 청산).

    격리: high_since_buy=buy(무이익) → ATR 트레일선 = buy-2×atr=106700, 현재가 119000 위 → 트레일 없음.
          _breakout_high 미설정 → 시간청산 skip.
    기대: _channel_low(120000) > 현재가 119000 → 채널 이탈 → TRAILING_STOP.
    현행: 채널 로직 부재 → NONE.
    """
    s = _mk(channel_exit_period=10)
    s.state.positions["096770"] = _pos(buy_price=117_300, high_since_buy=117_300)
    s._entry_atr["096770"] = 5_300.0
    s._channel_low["096770"] = 120_000   # 인메모리 사전 세팅 (prepare/recompute 산출 가정)
    sig = s.check_exit_signal("096770", 119_000, 117_300)
    assert sig == Signal.TRAILING_STOP, (
        f"A-4: 10일 채널 이탈 TRAILING_STOP 기대, got {sig}"
    )


def test_A4_channel_exit_off_when_period_zero():
    """channel_exit_period=0 → 채널 청산 비활성 (opt-out 회귀 보존)."""
    s = _mk(channel_exit_period=0)
    s.state.positions["096770"] = _pos(buy_price=117_300, high_since_buy=117_300)
    s._entry_atr["096770"] = 5_300.0
    s._channel_low["096770"] = 120_000
    # period=0 → 채널 분기 미진입, 다른 청산도 미해당 → NONE
    assert s.check_exit_signal("096770", 119_000, 117_300) == Signal.NONE


def test_A4_channel_exit_holds_above_10day_low():
    """현재가 ≥ 10일 저가 → 채널 청산 안 함 (경계)."""
    s = _mk(channel_exit_period=10)
    s.state.positions["096770"] = _pos(buy_price=117_300, high_since_buy=117_300)
    s._entry_atr["096770"] = 5_300.0
    s._channel_low["096770"] = 120_000
    assert s.check_exit_signal("096770", 120_500, 117_300) == Signal.NONE


# ─────────────────────────────────────────────────────────────────────────
# A-5 (회귀 0) — 기존 발화 케이스 보존 (대표 케이스 재확인)
# ─────────────────────────────────────────────────────────────────────────
def test_A5_regression_turtle_2atr_hard_stop_preserved():
    """터틀 2ATR 하드손절 보존 (사이클 P2A2)."""
    s = _mk()
    s.state.positions["005930"] = _pos(ticker="005930", buy_price=60_000)
    s._entry_atr["005930"] = 3_000.0            # base = 60000 - 2×3000 = 54000
    s._candidates["005930"] = {"atr": 3_000}
    assert s.check_exit_signal("005930", 53_900, 60_000) == Signal.STOP_LOSS


def test_A5_regression_backstop_preserved():
    """터틀 -9% backstop 보존 (naked ATR 손절 최후 방어)."""
    s = _mk()
    s.state.positions["005930"] = _pos(ticker="005930", buy_price=60_000)
    s._entry_atr["005930"] = 40_000.0           # base <0 → ATR손절 skip
    s._candidates["005930"] = {"atr": 40_000}
    assert s.check_exit_signal("005930", 54_000, 60_000) == Signal.STOP_LOSS  # -10% ≤ -9%


def test_A5_regression_position_ratio_percent_stop_byte_identical():
    """position_ratio 매수(entry_atr 미스탬프) -7% 손절 byte 동일."""
    s = _mk(sizing_mode="position_ratio")
    s.state.positions["005930"] = _pos(ticker="005930", buy_price=60_000)
    s._candidates["005930"] = {"atr": 3_000}
    assert s.check_exit_signal("005930", 55_800, 60_000) == Signal.STOP_LOSS   # -7% 정확
    assert s.check_exit_signal("005930", 56_000, 60_000) == Signal.NONE        # -6.7% > -7%


def test_A5_regression_time_based_exit_preserved():
    """시간 기반 청산(011200 시나리오) 보존 — 보유 N일 + 현재가 < 돌파선."""
    s = _mk(sizing_mode="position_ratio")
    buy_date = _dt.date(2026, 7, 20)
    s.state.positions["011200"] = _pos(ticker="011200", buy_price=60_000, buy_date=buy_date)
    s._breakout_high["011200"] = 62_000
    with patch("src.engine.strategies.donchian_swing.datetime") as _dtmock:
        _dtmock.now.return_value = _dt.datetime(2026, 7, 29, 10, 0, tzinfo=KST)  # 9일 보유 ≥ 5
        # 현재가 61000 < 돌파선 62000, -1.7% (하드손절 -7% 미달) → 시간청산 STOP_LOSS
        sig = s.check_exit_signal("011200", 61_000, 60_000)
    assert sig == Signal.STOP_LOSS


# ─────────────────────────────────────────────────────────────────────────
# A-6 — 096770 실데이터 근사 시나리오 (트레일링이 백스톱 이전에 발화 = 승자 전환)
# ─────────────────────────────────────────────────────────────────────────
def test_A6_096770_trailing_fires_before_backstop():
    """096770: 매수 117300 → 고점 135800 → 하락. 트레일링이 -9% 백스톱 이전에 발화.

    승자 전환 = -9% 전량 반납(@106743) 대신 트레일링선(@125200) 에서 익절.
    현행: _candidates miss → atr=0 → 트레일 침묵 → -9% 백스톱까지 방치 (관측된 결함).
    """
    s = _mk()
    s.state.positions["096770"] = _pos(buy_price=117_300, high_since_buy=135_800)
    s._entry_atr["096770"] = 5_300.0
    assert "096770" not in s._candidates  # 후보 이탈 재현
    backstop_price = int(117_300 * 0.91)  # ≈106743
    trail_price = 135_800 - 2 * 5_300     # 125200
    assert trail_price > backstop_price   # 트레일선이 백스톱보다 훨씬 위
    # 트레일선 도달 시점(125000)에 발화해야 함 — 백스톱(106743)까지 방치 금지
    assert s.check_exit_signal("096770", 125_000, 117_300) == Signal.TRAILING_STOP


# ─────────────────────────────────────────────────────────────────────────
# 신규 파라미터 PARAM_RANGES 제외 (정체성 상수, AI 자동튜닝 차단)
# ─────────────────────────────────────────────────────────────────────────
def test_new_layered_exit_keys_excluded_from_param_ranges():
    for key in ("breakeven_promote_atr", "channel_exit_period"):
        assert key not in PARAM_RANGES, f"{key} 는 PARAM_RANGES 편입 금지 (정체성 상수)"


def test_new_layered_exit_keys_in_default_params():
    """신규 DEFAULT_PARAMS 키 존재 + 기본값 (구현 계약)."""
    assert DonchianSwingStrategy.DEFAULT_PARAMS.get("breakeven_promote_atr") == 1.5
    assert DonchianSwingStrategy.DEFAULT_PARAMS.get("channel_exit_period") == 10
