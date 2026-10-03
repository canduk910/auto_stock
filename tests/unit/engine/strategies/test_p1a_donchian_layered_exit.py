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

## ⚠️ cycle405 — 깡토식 청산으로 대체 (명세 `_workspace/red/cycle405_donchian_kkangto_spec.md` §2)

샹들리에(A-1·A-6) · 1.5N 승격(A-3) · −9% 받침선·미스탬프 −7%·돌파 실패 시간 청산(A-5)은 없어졌다.
그 단언 테스트는 지웠다(새 계약 = `test_cycle405_donchian_kk_exit.py`). A-3 은 3R 본전, A-4 는
「3R 무장 뒤에만 채널」 로 고쳐 남겼다. A-2(돌파선 재도출)·채널 데이터 소스 계약은 그대로다.

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
    # 사이클 223 의미 전환 — 재도출이 **신호일 봉(prior[0])을 제외**하도록 시정되면서
    # prior 최소 길이가 period → period+1 이 됐다(19봉으로 20일 신고가를 만드는 조용한
    # 과소 표본 차단). 픽스처를 20봉 → 21봉으로 늘린다. 창(`prior[1:21]`) 안에 있는
    # 0720 = 130,000 이 여전히 최고가라 **기대값은 불변**이다.
    pre = [(f"202607{d:02d}", 130_000 if d == 20 else 120_000, 115_000, 118_000)
           for d in range(26, 5, -1)]  # 21봉 DESC, 0726..0706
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
def test_A3_breakeven_is_3r_not_1_5n():
    """cycle405 — 본전 승격 = 고점 ≥ E + 3R. E=117,300 · N=5,300 → R = max(9,384, 7,950) = 9,384.

    옛 1.5N 승격 고점(126,000)에서는 손절선이 E − R(107,916) 그대로라 117,200 은 NONE.
    고점 145,452(= E + 3R) 부터 손절선 = E → 117,300 에서 STOP_LOSS.
    """
    s = _mk()
    s.state.positions["096770"] = _pos(buy_price=117_300, high_since_buy=126_000)
    s._entry_atr["096770"] = 5_300.0
    assert s.check_exit_signal("096770", 117_200, 117_300) == Signal.NONE
    s.state.positions["096770"].high_since_buy = 145_452
    assert s.check_exit_signal("096770", 117_300, 117_300) == Signal.STOP_LOSS


# ─────────────────────────────────────────────────────────────────────────
# A-4 — 10일 저가 채널 이탈 → TRAILING_STOP (channel_exit_period=10)
# ─────────────────────────────────────────────────────────────────────────
def test_A4_channel_exit_fires_below_10day_low_only_after_3r():
    """cycle405 — 현재가 < 10일 저가 → TRAILING_STOP 은 **3R 무장 뒤에만**(무장 고점 145,452)."""
    s = _mk(channel_exit_period=10)
    s.state.positions["096770"] = _pos(buy_price=117_300, high_since_buy=117_300)
    s._entry_atr["096770"] = 5_300.0
    s._channel_low["096770"] = 120_000   # 인메모리 사전 세팅 (prepare/recompute 산출 가정)
    assert s.check_exit_signal("096770", 119_000, 117_300) == Signal.NONE
    s.state.positions["096770"].high_since_buy = 145_452
    assert s.check_exit_signal("096770", 119_000, 117_300) == Signal.TRAILING_STOP


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
