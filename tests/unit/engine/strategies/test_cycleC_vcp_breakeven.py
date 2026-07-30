"""사이클 C Red — VCP 브레이크이븐 승격 (default-off + live-ATR 래치).

명세: `_workspace/red/_behaviors_cycleC_breakeven_20260730.md` 행위 C-V1~C-V5.
자문: `_workspace/domain_consult/cycle_breakeven_promotion_rollout.md` (Q2 live ATR 래치 필수).
선례: `src/engine/strategies/donchian_swing.py` P1-A (check_exit_signal L1028 브레이크이븐 승격
      + recompute_high_since_buy / _apply_high_since_buy_from_candles).

## 왜 donchian 을 그대로 이식하면 안 되나 (자문 Q2)

donchian 은 `entry_atr` *스냅샷*(진입 시 원자 고정)을 써서 승격 조건 `high >= buy + N×entry_atr`
가 자연 래치된다. VCP 는 `_candidates[ticker]["atr14"]` 의 **live ATR**(매일 prepare 로 갱신)을
쓰므로, 승격 후 변동성이 커져 ATR 이 팽창하면 `buy + N×atr_live` 가 `high` 위로 올라가
**조건이 다시 거짓** → 본전으로 올려놨던 손절선이 풀린다(un-latch 병리). 따라서 boolean
래치 `_breakeven_latched: set[str]` 가 **필수 구현 가드**다 — 최초 관측 시 add, 이후 ATR 무관 유지.

## 인터페이스 계약 (tdd-engineer 확정 — backend-dev 구현 대상)

- 신규 인스턴스 필드 `self._breakeven_latched: set[str]` (`__init__`).
- 신규 DEFAULT_PARAMS `breakeven_promote_atr = 0.0` (**0 = 비활성 기본, default-off 배포**).
  PARAM_RANGES / INT_PARAMS **미편입** (청산 정체성 상수, 사이클 208/209/212 선례).
- `check_exit_signal` 승격 로직 (`breakeven_promote_atr > 0` 일 때만):
    1. 래치: `ticker not in _breakeven_latched` 이고 live atr>0 이고
       `high_since_buy >= buy_price + mult×atr` → `_breakeven_latched.add(ticker)`.
    2. 승격 발화: `ticker in _breakeven_latched` 이고 `current_price <= buy_price`
       → STOP_LOSS (로그 prefix `[vcp_breakeven_promote]`). tighten-only — buy 위에서 미발화.
- `recompute_high_since_buy()` 이식 (donchian 패턴): 매수일 < bsop_date < today 일봉 high max
  보정, 메서드 내부에서 `from src.api.condition import fetch_daily_candles` import,
  기존값 초과 시에만 갱신. (재시작 시 high 동결 → 래치 미형성 예방)
- `on_position_closed(ticker)` 에서 `_breakeven_latched.discard(ticker)` (재진입 stale 차단).
"""

from __future__ import annotations

import datetime as _dt
from datetime import date
from unittest.mock import AsyncMock, patch

import pytest

from src.engine.strategies.vcp_breakout import VcpBreakoutStrategy
from src.engine.strategy_base import Position, Signal, StrategyConfig
from src.engine.recommendation_engine import PARAM_RANGES, INT_PARAMS

pytestmark = pytest.mark.unit
KST = _dt.timezone(_dt.timedelta(hours=9))


def _mk(**params):
    cfg = StrategyConfig(strategy_id="vcp_breakout", name="VCP", weight=0.2,
                         params=dict(params))
    s = VcpBreakoutStrategy(cfg)
    s.state.total_investment = 100_000_000
    return s


def _pos(ticker="000660", buy_price=100_000, high_since_buy=0, buy_date=None):
    p = Position(ticker=ticker, buy_price=buy_price, quantity=10, order_no="O",
                 strategy_id="vcp_breakout", buy_date=buy_date or date(2026, 7, 29))
    p.high_since_buy = high_since_buy
    return p


def _isolating_info(atr14=2_000, base_low=90_000):
    """승격 외 청산(하드손절/base_low/트레일링/ema50)을 모두 비발화로 격리하는 _candidates 정보."""
    return {"atr14": atr14, "base_low": base_low, "ema50": 0}


def _candles_desc(dates_ohlc):
    """dates_ohlc = [(yyyymmdd, high, low, close), ...] DESC (idx0=최신)."""
    return [{"stck_bsop_date": d, "stck_hgpr": str(h), "stck_lwpr": str(lo), "stck_clpr": str(c)}
            for d, h, lo, c in dates_ohlc]


# ─────────────────────────────────────────────────────────────────────────
# C-V1 (HIGH) — live-ATR 래치 병리 재현: ATR 팽창해도 승격 유지
# ─────────────────────────────────────────────────────────────────────────
def test_CV1_latch_persists_after_atr_expansion():
    """고점이 buy+1.5×ATR 도달 → 래치. 이후 ATR 팽창으로 조건이 산술상 거짓이 돼도 승격 유지.

    tick1: atr=2000, high=103000 = buy(100000)+1.5×2000 → 래치 성립 (가격 103000 > buy → 미발화).
    tick2: atr 10000 으로 팽창 → buy+1.5×10000=115000 > high(103000) = 조건 거짓.
           그럼에도 래치 유지 → 현재가 100000(=buy) ≤ buy → STOP_LOSS.
    현행: 래치 필드 부재 → `_breakeven_latched` AttributeError 또는 승격 무발화 → RED.
    """
    s = _mk(breakeven_promote_atr=1.5)
    s.state.positions["000660"] = _pos(buy_price=100_000, high_since_buy=103_000)
    s._candidates["000660"] = _isolating_info(atr14=2_000)

    # tick1 — 래치 성립 (가격 고점, 미발화)
    assert s.check_exit_signal("000660", 103_000, 0) == Signal.NONE
    assert "000660" in s._breakeven_latched, "C-V1: 최초 관측 시 래치 add 되어야 함"

    # ATR 팽창 (un-latch 병리 트리거) — 조건 산술상 거짓화
    s._candidates["000660"]["atr14"] = 10_000

    # tick2 — 래치 유지 → buy 도달 시 STOP_LOSS
    sig = s.check_exit_signal("000660", 100_000, 0)
    assert sig == Signal.STOP_LOSS, (
        f"C-V1: ATR 팽창 후에도 래치 유지 → buy 도달 STOP_LOSS 기대, got {sig}"
    )


def test_CV1_no_latch_before_threshold_reached():
    """고점이 buy+1.5×ATR 미달이면 래치 미형성 (경계 정확성)."""
    s = _mk(breakeven_promote_atr=1.5)
    # high 102000 < buy+1.5×2000=103000 → 미달
    s.state.positions["000660"] = _pos(buy_price=100_000, high_since_buy=102_000)
    s._candidates["000660"] = _isolating_info(atr14=2_000)
    assert s.check_exit_signal("000660", 102_000, 0) == Signal.NONE
    assert "000660" not in s._breakeven_latched


# ─────────────────────────────────────────────────────────────────────────
# C-V2 — 승격 발화 (래치된 ticker 현재가 ≤ buy → STOP_LOSS, tighten-only)
# ─────────────────────────────────────────────────────────────────────────
def test_CV2_promotion_fires_at_buy_price():
    """래치된 ticker 현재가 = buy_price → STOP_LOSS (하드손절 -7% 미달·base_low 위여도 승격 발화)."""
    s = _mk(breakeven_promote_atr=1.5)
    s.state.positions["000660"] = _pos(buy_price=100_000, high_since_buy=103_000)
    s._candidates["000660"] = _isolating_info(atr14=2_000)
    s._breakeven_latched.add("000660")  # 직접 래치 (현행 코드엔 필드 부재 → AttributeError RED)
    assert s.check_exit_signal("000660", 100_000, 0) == Signal.STOP_LOSS


def test_CV2_promotion_tighten_only_no_fire_above_buy():
    """tighten-only — 래치돼도 현재가가 buy 위면 승격 미발화 (손절선이 buy 위로 넓어지는 케이스 0)."""
    s = _mk(breakeven_promote_atr=1.5)
    s.state.positions["000660"] = _pos(buy_price=100_000, high_since_buy=103_000)
    s._candidates["000660"] = _isolating_info(atr14=2_000)
    s._breakeven_latched.add("000660")
    # 현재가 100500 > buy → 승격 미발화 + 다른 청산도 미해당 → NONE
    assert s.check_exit_signal("000660", 100_500, 0) == Signal.NONE


# ─────────────────────────────────────────────────────────────────────────
# C-V3 (HIGH) — default-off 회귀 0 (기본 breakeven_promote_atr=0.0)
# ─────────────────────────────────────────────────────────────────────────
def test_CV3_default_param_is_off():
    """DEFAULT_PARAMS breakeven_promote_atr 기본값 = 0.0 (default-off 배포)."""
    assert VcpBreakoutStrategy.DEFAULT_PARAMS.get("breakeven_promote_atr") == 0.0


def test_CV3_disabled_no_latch_no_promotion():
    """기본(off) 이면 고점이 임계 도달해도 래치/승격 분기 완전 무발화 — 기존 청산 스택 불변.

    high=103000 은 atr=2000 기준 승격 임계(buy+1.5×2000=103000)를 만족하지만 default-off →
    래치 미형성 + buy 도달해도 STOP_LOSS 미발화 (기존 -7%/base_low/트레일링만 유효).
    """
    s = _mk()  # breakeven_promote_atr 미지정 → 기본 0.0
    s.state.positions["000660"] = _pos(buy_price=100_000, high_since_buy=103_000)
    s._candidates["000660"] = _isolating_info(atr14=2_000)
    assert s.check_exit_signal("000660", 100_000, 0) == Signal.NONE
    assert not getattr(s, "_breakeven_latched", set()), "off 상태에서 래치 add 금지"


def test_CV3_existing_exit_stack_preserved_when_off():
    """default-off 에서 기존 청산 발화 케이스 보존 (하드손절 -7% / base_low).

    high_since_buy=0 으로 ATR 트레일링을 격리 (미실현 고점 없음) → 하드손절/base_low 만 검증.
    """
    s = _mk()
    # 하드손절 -7% 정확 (트레일링 격리 = high_since_buy 0)
    s.state.positions["000660"] = _pos(buy_price=100_000, high_since_buy=0)
    s._candidates["000660"] = {"atr14": 2_000, "base_low": 80_000, "ema50": 0}
    assert s.check_exit_signal("000660", 93_000, 0) == Signal.STOP_LOSS   # -7%
    assert s.check_exit_signal("000660", 93_100, 0) == Signal.NONE        # -6.9%
    # base_low 이탈 (-6% 로 하드손절 미달, base_low 95000 하회로 STOP_LOSS)
    s.state.positions["005930"] = _pos(ticker="005930", buy_price=100_000, high_since_buy=0)
    s._candidates["005930"] = {"atr14": 2_000, "base_low": 95_000, "ema50": 0}
    assert s.check_exit_signal("005930", 94_000, 0) == Signal.STOP_LOSS


# ─────────────────────────────────────────────────────────────────────────
# C-V4 — recompute_high_since_buy 이식 (donchian 패턴)
# ─────────────────────────────────────────────────────────────────────────
def test_CV4_vcp_has_recompute_high_since_buy():
    """VCP 에 recompute_high_since_buy 메서드 이식 (현행 부재 → RED)."""
    s = _mk()
    assert hasattr(s, "recompute_high_since_buy"), (
        "C-V4: VCP 에 recompute_high_since_buy 이식 필요 (재시작 시 high 동결 → 래치 미형성 예방)"
    )


async def test_CV4_recompute_corrects_stale_high_since_buy():
    """매수일 < bsop_date < today 일봉 high max 로 high_since_buy 보정 (기존값 초과 시에만).

    buy_date=2026-07-20, today=2026-07-29. 그 사이 일봉 최고가 112000 → stale high 105000 갱신.
    현행: 메서드 부재 → AttributeError → RED.
    """
    s = _mk()
    buy_date = date(2026, 7, 20)
    pos = _pos(buy_price=100_000, high_since_buy=105_000, buy_date=buy_date)
    s.state.positions["000660"] = pos
    # 매수일 이후 봉 (0728 high=112000 최대) DESC
    candles = _candles_desc([
        ("20260729", 130_000, 120_000, 125_000),  # today — 경계 밖(제외)
        ("20260728", 112_000, 108_000, 110_000),  # 보정 대상 최대
        ("20260724", 109_000, 104_000, 107_000),
        ("20260723", 108_000, 103_000, 106_000),
        ("20260722", 106_000, 102_000, 104_000),
        ("20260721", 104_000, 100_000, 103_000),
        ("20260720", 102_000, 99_000, 101_000),   # 매수일 당일 — 경계 밖(제외)
    ])
    with patch("src.api.condition.fetch_daily_candles", new=AsyncMock(return_value=candles)), \
         patch("src.engine.strategies.vcp_breakout.datetime") as _dtmock, \
         patch("src.db.positions.update_high", new=AsyncMock()), \
         patch("src.db.system_logs.write_log", new=AsyncMock()):
        _dtmock.now.return_value = _dt.datetime(2026, 7, 29, 8, 0, tzinfo=KST)
        await s.recompute_high_since_buy()
    assert pos.high_since_buy == 112_000, (
        f"C-V4: 매수일~전영업일 high max(112000) 보정 기대, got {pos.high_since_buy}"
    )


async def test_CV4_recompute_does_not_lower_high():
    """보정 후보가 기존 high 이하면 갱신 안 함 (max-only, 하향 금지)."""
    s = _mk()
    buy_date = date(2026, 7, 20)
    pos = _pos(buy_price=100_000, high_since_buy=200_000, buy_date=buy_date)  # 이미 높음
    s.state.positions["000660"] = pos
    candles = _candles_desc([
        ("20260728", 112_000, 108_000, 110_000),
        ("20260722", 106_000, 102_000, 104_000),
    ])
    with patch("src.api.condition.fetch_daily_candles", new=AsyncMock(return_value=candles)), \
         patch("src.engine.strategies.vcp_breakout.datetime") as _dtmock, \
         patch("src.db.positions.update_high", new=AsyncMock()), \
         patch("src.db.system_logs.write_log", new=AsyncMock()):
        _dtmock.now.return_value = _dt.datetime(2026, 7, 29, 8, 0, tzinfo=KST)
        await s.recompute_high_since_buy()
    assert pos.high_since_buy == 200_000


# ─────────────────────────────────────────────────────────────────────────
# C-V5 — on_position_closed 래치 정리 (재진입 stale 차단)
# ─────────────────────────────────────────────────────────────────────────
def test_CV5_on_position_closed_discards_latch():
    """전량 청산 시 _breakeven_latched 에서 discard (기존 쿨다운 등록과 동행)."""
    s = _mk(breakeven_promote_atr=1.5)
    s._breakeven_latched.add("000660")
    s.on_position_closed("000660")
    assert "000660" not in s._breakeven_latched, (
        "C-V5: on_position_closed 가 _breakeven_latched 를 정리해야 함 (재진입 stale 차단)"
    )


# ─────────────────────────────────────────────────────────────────────────
# 신규 파라미터 PARAM_RANGES / INT_PARAMS 제외 (정체성 상수, AI 자동튜닝 차단)
# ─────────────────────────────────────────────────────────────────────────
def test_breakeven_key_excluded_from_param_ranges():
    assert "breakeven_promote_atr" not in PARAM_RANGES, (
        "breakeven_promote_atr 는 PARAM_RANGES 편입 금지 (청산 정체성 상수)"
    )


def test_breakeven_key_excluded_from_int_params():
    assert "breakeven_promote_atr" not in INT_PARAMS, (
        "breakeven_promote_atr 는 INT_PARAMS 편입 금지 (float 임계, 정체성 상수)"
    )


# ─────────────────────────────────────────────────────────────────────────
# C-V6 — recompute_high_since_buy 스케줄러 배선 (dead code 방지)
# 부팅 훅 `_eager_refresh_stock_master_for_held_positions` 가 donchian/kojiro
# recompute_held_atr 만 순회하면 VCP 신규 메서드는 호출처 0 = 재시작 복구 미실현.
# ─────────────────────────────────────────────────────────────────────────
def test_CV6_scheduler_boot_hook_wires_vcp_recompute():
    """스케줄러 부팅 recompute 훅 소스에 vcp recompute_high_since_buy 배선 존재."""
    import inspect
    from src.engine.scheduler import TradingScheduler

    src = inspect.getsource(
        TradingScheduler._eager_refresh_stock_master_for_held_positions
    )
    assert "recompute_high_since_buy" in src, (
        "C-V6: 부팅 훅이 vcp recompute_high_since_buy 를 호출해야 함 (dead code 방지)"
    )
    assert "vcp_breakout" in src, (
        "C-V6: vcp_breakout 전략을 대상으로 배선해야 함"
    )
