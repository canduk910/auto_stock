"""cycle242 G0-ⓑ Red — 터틀 전략 랏당 최대 유닛 상한 `max_lot_units`(K=2.0).

명세: `_workspace/red/cycle242_fallback_notional_cap_spec.md`
근거: `_workspace/domain_consult/pyramiding_deep_review_20260903.md` §0.0 · §1.2 · §4.3(G0)
      + `_workspace/domain_consult/cycle242_fallback_notional_cap.md`

## 고칠 결함 (한 문장)

터틀 사이징이 이론 유닛 <1주를 내면 `StrategyBase._apply_budget_limit` 이
`_fallback_one_share` 로 **1주를 산다**. 고가 종목에선 그 1주가 터틀 유닛의 수 배
(donchian 실측 평균 **4.94**·최대 **15.61** = 086280 1주, kojiro 1.52)라
`risk_pct 0.5%` 리스크 통제가 **진입 시점에 이미 무력**하다. 120일 BUY 226건 중
1주 폴백이 170건(75.2%)이고, 그 스택이 −30% 갭을 맞으면 계좌 8.83%가 날아간다.

## 시정 (사용자 결정 ⓑ — 2026-09-03 "결정 분기 권고대로 처리")

`sizing_mode == "turtle"` 전략의 **모든 랏**(터틀·position_ratio 낙하·1주 폴백)을
`floor(K × 예산 × risk_pct ÷ ATR)` 주 이하로 자르고, 0 이면 **매수하지 않는다**.
K = `max_lot_units` = 2.0 — 리스크 정체성 상수(PARAM_RANGES/INT_PARAMS 편입 금지,
읽는 쪽 `[1.0, 20.0]` 클램프). 고정%손절 5전략은 `position_ratio` 가 이미 리스크
균등이라(strategies/CLAUDE.md 함정 #1) **범위 밖**.

## 이 파일이 봉인하는 것

- F-1  현행에서 "이론 유닛 0.29주 · 1주 = 유닛의 3.43배"인 입력이 **1주를 반환**한다
       (시정 후 **0**). 이것이 결함의 직접 실증이자 이번 사이클의 핵심 Red.
- F-3  스코프 ii — 폴백뿐 아니라 **position_ratio 낙하 랏**(donchian 124500 2주 =
       3.71유닛)도 잘린다. 스코프 i(폴백만)면 G0 가 종결되지 않는다.
- F-4/F-6 정상 터틀 랏(T 경로)과 비터틀 5전략은 **한 건도 안 건드린다**.
- F-5  결측·모호·예외는 **fail-open**(현행 수량 유지 + LOUD). fail-closed 구현은
       P0-1(유령 키 → 전략 전 기간 체결 0건) 재현 경로라 FAIL 이 계약이다.
- F-16 항등식 — 모든 경로에서 `랏 유닛 ≤ K`.

## 명세 문언 정합 메모 (Red 작성 중 발견)

명세 §4.1 F-5 는 "(a) `_candidates` 속성 없음 … reason=no_atr×(a~e)" 로 적었으나,
같은 명세의 참조 구현(§2.4 `_resolve_sizing_atr`)·fail-open 경계표(§2.8)·F-6(c) 는
**속성 자체 부재 = `no_candidates`** 로 일치한다(사유별 대응이 갈린다 — 속성 부재는
"전략에 터틀을 잘못 주입"이고 값 결손은 "ATR 배관 결함"이다). 본 파일은 다수 정본
쪽(`no_candidates`)을 채택했다. Green 이 반대로 구현하면 F-5-A 가 FAIL 한다.
"""

from __future__ import annotations

import logging
import math

import pytest
from freezegun import freeze_time

from src.engine import strategy_base as sb_mod
from src.engine.strategy_base import Signal, StrategyBase, StrategyConfig
from src.engine.turtle_sizing import compute_unit_qty_guarded

pytestmark = pytest.mark.unit

# ── 실측 예산 (2026-09-03 net 2,582,132 재정규화) ──
KOJIRO_BUDGET = 774_640
DONCHIAN_BUDGET = 387_320
RISK = 0.005

CAPPED = "[fallback_notional_capped]"
SKIPPED = "[fallback_cap_skipped]"
CONFIG = "[fallback_cap_config]"
OVERSIZED = "[oversized_fallback]"
CLAMP = "[budget_clamp]"
LOT_CLAMPED = "[fallback_cap_clamped]"   # 라운드 1 — 결함 #4 시정 (max_lot_units 클램프 가시화)


# ---------------------------------------------------------------------------
# 픽스처 — cycle233 `_MiniStrategy` 패턴 (StrategyBase 직접 상속, DEFAULT_PARAMS 미병합)
# ---------------------------------------------------------------------------
class _MiniStrategy(StrategyBase):
    """관문 테스트용 최소 구현 (cycle233 `test_cycle233_oversized_fallback` 답습)."""

    async def prepare(self):  # pragma: no cover
        return None

    def check_buy_signal(self, ticker, current_price, open_price):
        return Signal.NONE

    def check_exit_signal(self, ticker, current_price, open_price):
        return Signal.NONE

    def calc_buy_quantity(self, current_price: int, ticker: str | None = None) -> int:
        return self._apply_budget_limit(0, current_price, ticker)


def _mini(
    strategy_id: str = "kojiro",
    *,
    budget: int = KOJIRO_BUDGET,
    ratio: float | None = 0.166,
    sizing_mode: str | None = "turtle",
    risk_pct: float | None = RISK,
    candidates: dict | None = None,
    set_candidates: bool = True,
    **extra,
) -> _MiniStrategy:
    params: dict = {"exchange": "KRX", **extra}
    if ratio is not None:
        params["position_ratio"] = ratio
    if sizing_mode is not None:
        params["sizing_mode"] = sizing_mode
    if risk_pct is not None:
        params["risk_pct"] = risk_pct
    s = _MiniStrategy(
        StrategyConfig(strategy_id=strategy_id, name=strategy_id, params=params)
    )
    s.state.total_investment = budget
    if set_candidates:
        s._candidates = dict(candidates or {})
    return s


def _dc(*, turtle: bool = True, budget: int = DONCHIAN_BUDGET, **extra):
    from src.engine.strategies.donchian_swing import DonchianSwingStrategy

    params = {"sizing_mode": "turtle" if turtle else "position_ratio", **extra}
    s = DonchianSwingStrategy(
        StrategyConfig(strategy_id="donchian_swing", name="도치안", weight=0.2,
                       params=params)
    )
    s.state.total_investment = budget
    return s


def _kj(*, turtle: bool = True, budget: int = KOJIRO_BUDGET, **extra):
    from src.engine.strategies.kojiro import KojiroStrategy

    params = {"sizing_mode": "turtle" if turtle else "position_ratio", **extra}
    s = KojiroStrategy(
        StrategyConfig(strategy_id="kojiro", name="고지로", weight=0.3, params=params)
    )
    s.state.total_investment = budget
    return s


def _vcp(*, turtle: bool = True, budget: int = 100_000_000, **extra):
    from src.engine.strategies.vcp_breakout import VcpBreakoutStrategy

    params = {"sizing_mode": "turtle" if turtle else "position_ratio", **extra}
    s = VcpBreakoutStrategy(
        StrategyConfig(strategy_id="vcp_breakout", name="VCP", weight=0.1,
                       params=params)
    )
    s.state.total_investment = budget
    return s


def _bfb(*, turtle: bool = True, budget: int = 100_000_000, **extra):
    from src.engine.strategies.bull_flag_breakout import BullFlagBreakoutStrategy

    params = {"sizing_mode": "turtle" if turtle else "position_ratio", **extra}
    s = BullFlagBreakoutStrategy(
        StrategyConfig(strategy_id="bull_flag_breakout", name="BFB", weight=0.15,
                       params=params)
    )
    s.state.total_investment = budget
    return s


def _msgs(caplog, marker: str) -> list[str]:
    return [r.getMessage() for r in caplog.records if marker in r.getMessage()]


def _recs(caplog, marker: str) -> list[logging.LogRecord]:
    return [r for r in caplog.records if marker in r.getMessage()]


# ===========================================================================
# F-1 — 현행 FAIL 핵심: 이론 유닛 0.29주인데 1주를 산다
# ===========================================================================
@freeze_time("2026-09-03 10:00:00+09:00")
def test_f242_1_kojiro_000815_fallback_capped_to_zero(caplog):
    """000815 실측 — 405,500원 1주 = 터틀 유닛 3.43배 ⇒ 시정 후 **0주**.

    B=774,640 · r=0.5% ⇒ 유닛 예산 3,873.2원. ATR 13,300 ⇒ u* = 0.291주.
    K=2 ⇒ cap = floor(0.582) = **0** ⇒ 매수 스킵.
    현행 구현은 `_fallback_one_share` 가 1 을 돌려주고 아무도 자르지 않으므로 FAIL.
    """
    s = _mini(candidates={"000815": {"atr": 13300}})
    with caplog.at_level(logging.INFO):
        qty = s._apply_budget_limit(0, 405_500, "000815")

    assert qty == 0, (
        "1주 폴백이 터틀 유닛 3.43배인데 그대로 매수됐다 — cycle242 캡 미적용"
    )
    hits = _msgs(caplog, CAPPED)
    assert len(hits) == 1, f"[fallback_notional_capped] 1행 기대, 실제 {len(hits)}"
    assert hits[0] == (
        "[fallback_notional_capped] ticker=000815 strategy=kojiro path=fallback "
        "price=405500 atr=13300 unit_qty=0.291 k=2.00 req_qty=1 capped_qty=0 "
        "units_before=3.43 units_after=0.00 budget=774640 risk_pct=0.0050"
    )
    assert _recs(caplog, CAPPED)[0].levelno == logging.INFO
    # 캡 → 0 이면 `_emit_oversized_fallback` 은 final<1 로 자연 침묵 (차단 사실은 신규 마커 담당)
    assert not _msgs(caplog, OVERSIZED)
    assert not _msgs(caplog, SKIPPED)


# ===========================================================================
# F-2 — 통과 + 이중 척도(ρ 축 `[oversized_fallback]` 과 K 축 병존)
# ===========================================================================
@freeze_time("2026-09-03 10:00:00+09:00")
def test_f242_2_within_cap_keeps_one_share_and_dual_scale(caplog):
    """004690 — ATR 4,290 ⇒ u*=0.903 ⇒ cap=floor(1.806)=1 ⇒ 1주 유지.

    같은 랏이 ρ 축(`position_ratio × 예산` = 128,590)은 넘으므로
    `[oversized_fallback]` 은 계속 찍힌다 = **의미 반전**(비제로가 정상).
    """
    s = _mini(candidates={"004690": {"atr": 4290}})
    with caplog.at_level(logging.INFO):
        qty = s._apply_budget_limit(0, 130_000, "004690")

    assert qty == 1
    assert not _msgs(caplog, CAPPED), "cap 이내인데 캡 마커가 찍혔다"
    over = _msgs(caplog, OVERSIZED)
    assert len(over) == 1
    assert "ratio=1.01" in over[0]
    assert over[0].endswith("units=1.11"), f"units= 필드 누락/오값: {over[0]}"


# ===========================================================================
# F-3 — 현행 FAIL 핵심 2: 스코프 ii (position_ratio 낙하 랏도 잘린다)
# ===========================================================================
@freeze_time("2026-09-03 10:00:00+09:00")
def test_f242_3_donchian_pr_path_lot_clamped(caplog):
    """124500 — 터틀 0주 낙하 후 PR 2주(=3.71유닛)를 K=2 로 1주로 자른다.

    스코프 i(폴백 분기 안에만 캡)로 구현하면 이 경로를 못 건드려 donchian 최대 랏이
    3.71유닛에 고정된다 → G0 미종결. `_entry_atr` 미스탬프 규약은 불변이어야 한다.
    """
    s = _dc()
    s._candidates["124500"] = {
        "prev_close": 38000, "atr": 3593, "ema60": 0, "donchian_high": 0,
    }
    with caplog.at_level(logging.INFO):
        qty = s.calc_buy_quantity(38_000, "124500")

    assert qty == 1, "PR 낙하 랏(2주=3.71유닛)이 K=2 로 잘리지 않았다"
    hits = _msgs(caplog, CAPPED)
    assert len(hits) == 1
    assert hits[0] == (
        "[fallback_notional_capped] ticker=124500 strategy=donchian_swing path=sized "
        "price=38000 atr=3593 unit_qty=0.539 k=2.00 req_qty=2 capped_qty=1 "
        "units_before=3.71 units_after=1.86 budget=387320 risk_pct=0.0050"
    )
    # 터틀이 0 을 반환한 경로이므로 entry_atr 미스탬프(= % 손절 경로) 규약 불변
    assert "124500" not in s._entry_atr


# ===========================================================================
# F-4 — T 경로(정상 터틀 랏) 무접촉
# ===========================================================================
_T_PRICES = (5_000, 20_000, 60_000, 250_000)
_T_ATR_PCTS = (0.01, 0.025, 0.05, 0.10)


@freeze_time("2026-09-03 10:00:00+09:00")
@pytest.mark.parametrize("maker", ["donchian", "kojiro"])
def test_f242_4_turtle_path_untouched(maker, caplog):
    """K ≥ 1 이면 정상 터틀 수량(≤ u*)은 어떤 (B,r,ATR,P) 에서도 캡에 안 걸린다."""
    budget = 100_000_000
    with caplog.at_level(logging.INFO):
        for price in _T_PRICES:
            for pct in _T_ATR_PCTS:
                atr = int(price * pct)
                s = _dc(budget=budget) if maker == "donchian" else _kj(budget=budget)
                key = "atr"
                s._candidates["005930"] = {
                    "prev_close": price, key: atr, "ema60": 0, "donchian_high": 0,
                }
                expected = compute_unit_qty_guarded(
                    budget, float(atr), price, RISK,
                    remaining_budget=budget, min_vol_pct=1.0, position_ratio=0.20,
                )
                assert expected > 0, "픽스처 오류 — T 경로가 아니다"
                qty = s.calc_buy_quantity(price, "005930")
                assert qty == expected, (
                    f"{maker} price={price} atr={atr}: 정상 터틀 랏이 변조됐다 "
                    f"({qty} != {expected})"
                )
                if maker == "donchian":
                    assert s._entry_atr["005930"] == float(atr)
    assert not _msgs(caplog, CAPPED), "T 경로에서 캡이 발동했다"


@freeze_time("2026-09-03 10:00:00+09:00")
def test_f242_4b_sub_one_k_is_clamped_so_turtle_path_survives(caplog):
    """하한 클램프 1.0 실증 — `max_lot_units=0.5` 주입도 T 경로를 반토막 내지 못한다.

    `_MAX_LOT_UNITS_MIN` 을 0.5 로 낮추는 뮤테이션(m15) 검출용.
    """
    budget = 100_000_000
    s = _dc(budget=budget, max_lot_units=0.5)
    s._candidates["005930"] = {
        "prev_close": 60000, "atr": 3000, "ema60": 0, "donchian_high": 0,
    }
    expected = compute_unit_qty_guarded(
        budget, 3000.0, 60000, RISK,
        remaining_budget=budget, min_vol_pct=1.0, position_ratio=0.20,
    )
    with caplog.at_level(logging.INFO):
        qty = s.calc_buy_quantity(60_000, "005930")
    assert qty == expected == 166
    assert not _msgs(caplog, CAPPED)


# ===========================================================================
# F-5 — fail-open (P0-1 유령 키 재현 방지). 수량 0 이면 FAIL 이 계약.
# ===========================================================================
@freeze_time("2026-09-03 10:00:00+09:00")
def test_f242_5a_missing_candidates_attr_is_fail_open(caplog):
    """`_candidates` 속성 자체 부재 → `no_candidates` + 현행 수량."""
    s = _mini(set_candidates=False)
    assert not hasattr(s, "_candidates")
    with caplog.at_level(logging.INFO):
        qty = s._apply_budget_limit(0, 405_500, "000815")
    assert qty == 1, "fail-closed 구현 — P0-1 재현 경로"
    hits = _recs(caplog, SKIPPED)
    assert len(hits) == 1
    assert hits[0].levelno == logging.WARNING
    assert hits[0].getMessage().startswith(
        "[fallback_cap_skipped] ticker=000815 strategy=kojiro reason=no_candidates "
        "qty=1 price=405500"
    )


@freeze_time("2026-09-03 10:00:00+09:00")
@pytest.mark.parametrize("cands", [
    {},
    {"000815": {}},
    {"000815": {"atr": 0}},
    {"000815": {"atr": "abc"}},
    {"000815": {"atr": -1}},
    {"000815": {"atr": float("inf")}},
    {"000815": {"atr": True}},
])
def test_f242_5b_atr_missing_or_invalid_is_fail_open(cands, caplog):
    """ATR 결측/0/비수치/음수/비유한/bool → `no_atr` + 현행 수량 유지."""
    s = _mini(candidates=cands)
    with caplog.at_level(logging.INFO):
        qty = s._apply_budget_limit(0, 405_500, "000815")
    assert qty == 1, f"fail-closed 구현 (cands={cands})"
    hits = _recs(caplog, SKIPPED)
    assert len(hits) == 1
    assert hits[0].levelno == logging.WARNING
    assert "reason=no_atr " in hits[0].getMessage()


@freeze_time("2026-09-03 10:00:00+09:00")
@pytest.mark.parametrize("risk", [0, 0.0, None, "x", -0.01])
def test_f242_5c_risk_pct_missing_is_fail_open(risk, caplog):
    """`risk_pct` 0/None/비수치 → `no_risk_pct` + 현행 수량 유지."""
    s = _mini(risk_pct=risk, candidates={"000815": {"atr": 13300}})
    with caplog.at_level(logging.INFO):
        qty = s._apply_budget_limit(0, 405_500, "000815")
    assert qty == 1
    hits = _recs(caplog, SKIPPED)
    assert len(hits) == 1
    assert hits[0].levelno == logging.WARNING
    assert "reason=no_risk_pct " in hits[0].getMessage()


@freeze_time("2026-09-03 10:00:00+09:00")
def test_f242_5d_ambiguous_atr_is_fail_open(caplog):
    """`atr` 과 `atr14` 가 다른 값으로 동시 존재 → 불채택(현행 수량)."""
    s = _mini(candidates={"000815": {"atr": 13300, "atr14": 9000}})
    with caplog.at_level(logging.INFO):
        qty = s._apply_budget_limit(0, 405_500, "000815")
    assert qty == 1
    hits = _recs(caplog, SKIPPED)
    assert len(hits) == 1
    assert "reason=ambiguous_atr " in hits[0].getMessage()


@freeze_time("2026-09-03 10:00:00+09:00")
def test_f242_5e_cap_computation_exception_is_fail_open(monkeypatch, caplog):
    """캡 산출이 던져도 예외 전파 0 + 현행 수량 유지 + `reason=exception`."""
    s = _mini(candidates={"000815": {"atr": 13300}})

    def _boom(*a, **k):
        raise RuntimeError("boom")

    monkeypatch.setattr(sb_mod, "compute_unit_qty", _boom, raising=False)
    with caplog.at_level(logging.INFO):
        try:
            qty = s._apply_budget_limit(0, 405_500, "000815")
        except RuntimeError:
            pytest.fail("캡 산출 예외가 매수 수량 산출로 전파됨")
    assert qty == 1
    hits = _recs(caplog, SKIPPED)
    assert len(hits) == 1
    assert "reason=exception " in hits[0].getMessage()
    assert hits[0].levelno == logging.WARNING


# ===========================================================================
# F-6 — 비터틀 byte 동일 (cycle233 계약이 position_ratio 모드에서 유효)
# ===========================================================================
@freeze_time("2026-09-03 10:00:00+09:00")
@pytest.mark.parametrize("mode", [None, "position_ratio"])
def test_f242_6a_non_turtle_mode_byte_identical(mode, caplog):
    """`sizing_mode` 부재/position_ratio → 캡 off, cycle233 계약 그대로."""
    s = _mini(sizing_mode=mode, budget=789_130,
              candidates={"000815": {"atr": 13300}})
    with caplog.at_level(logging.INFO):
        qty = s._apply_budget_limit(0, 405_500, "000815")
    assert qty == 1
    assert not _msgs(caplog, CAPPED)
    assert not _msgs(caplog, SKIPPED)
    over = _msgs(caplog, OVERSIZED)
    assert len(over) == 1 and "3.10" in over[0]
    cfg = _msgs(caplog, CONFIG)
    assert len(cfg) == 1 and "cap=off" in cfg[0]


@freeze_time("2026-09-03 10:00:00+09:00")
@pytest.mark.parametrize("module,cls_name", [
    ("momentum", "MomentumStrategy"),
    ("volatility_breakout", "VolatilityBreakoutStrategy"),
    ("long_tail_volatility", "LongTailVolatilityStrategy"),
])
def test_f242_6c_fixed_stop_strategies_have_no_candidates(module, cls_name, caplog):
    """momentum/VB/LTV 에 turtle 을 주입해도 수량 동일 — 캡 정의 자체가 불가.

    세 전략은 `_candidates` 속성이 없다(grep 실측) → `no_candidates` fail-open.
    """
    import importlib

    mod = importlib.import_module(f"src.engine.strategies.{module}")
    cls = getattr(mod, cls_name)

    def _make(extra: dict):
        s = cls(StrategyConfig(strategy_id=module, name=module,
                               params=dict(extra)))
        s.state.total_investment = KOJIRO_BUDGET
        return s

    baseline = _make({}).calc_buy_quantity(405_500, "000815")
    s = _make({"sizing_mode": "turtle", "risk_pct": RISK})
    assert not hasattr(s, "_candidates"), f"{module} 에 _candidates 가 생겼다"
    with caplog.at_level(logging.INFO):
        qty = s.calc_buy_quantity(405_500, "000815")
    assert qty == baseline, "고정%손절 전략의 수량이 바뀌었다 (범위 밖 계약 위반)"
    hits = _recs(caplog, SKIPPED)
    assert len(hits) == 1
    assert "reason=no_candidates " in hits[0].getMessage()


@freeze_time("2026-09-03 10:00:00+09:00")
@pytest.mark.parametrize("maker", ["donchian", "vcp", "bfb"])
def test_f242_6d_turtle_strategy_empty_candidates_fail_open(maker, caplog):
    """터틀 4전략이라도 후보가 비면 `no_atr` fail-open — 수량 동일."""
    make = {"donchian": _dc, "vcp": _vcp, "bfb": _bfb}[maker]
    baseline = make(turtle=False, budget=KOJIRO_BUDGET).calc_buy_quantity(
        405_500, "000815")
    s = make(turtle=True, budget=KOJIRO_BUDGET)
    with caplog.at_level(logging.INFO):
        qty = s.calc_buy_quantity(405_500, "000815")
    assert qty == baseline
    hits = _recs(caplog, SKIPPED)
    assert len(hits) == 1
    assert "reason=no_atr " in hits[0].getMessage()


# ===========================================================================
# F-7 — ticker None 은 조용히 off (터틀 분기와 동일 조건)
# ===========================================================================
@freeze_time("2026-09-03 10:00:00+09:00")
def test_f242_7_ticker_none_silently_off(caplog):
    s = _dc(budget=DONCHIAN_BUDGET)
    with caplog.at_level(logging.INFO):
        qty = s.calc_buy_quantity(38_000)
    assert qty == int(DONCHIAN_BUDGET * 0.20) // 38_000
    assert not _msgs(caplog, CAPPED)
    assert not _msgs(caplog, SKIPPED)
    assert len(_msgs(caplog, CONFIG)) == 1


# ===========================================================================
# F-8 — cap 규약 (1회/(전략,ticker)/일 · 인스턴스 격리 · 날짜 키 자기 리셋)
# ===========================================================================
@freeze_time("2026-09-03 10:00:00+09:00")
def test_f242_8a_capped_marker_once_per_ticker_per_day(caplog):
    s = _mini(candidates={"000815": {"atr": 13300}, "086280": {"atr": 9000}})
    with caplog.at_level(logging.INFO):
        s._apply_budget_limit(0, 405_500, "000815")
        s._apply_budget_limit(0, 405_500, "000815")
        s._apply_budget_limit(0, 300_000, "086280")
    hits = _msgs(caplog, CAPPED)
    assert len(hits) == 2, f"ticker 별 1행 기대, 실제 {len(hits)}"
    assert sum("ticker=000815" in m for m in hits) == 1
    assert sum("ticker=086280" in m for m in hits) == 1


@freeze_time("2026-09-03 10:00:00+09:00")
def test_f242_8b_skipped_marker_keyed_by_ticker_and_reason(caplog):
    s = _mini(candidates={"000815": {"atr": 0}})
    with caplog.at_level(logging.INFO):
        s._apply_budget_limit(0, 405_500, "000815")   # no_atr
        s._apply_budget_limit(0, 405_500, "000815")   # 같은 사유 → 억제
        s._candidates["000815"] = {"atr": 13300, "atr14": 9000}
        s._apply_budget_limit(0, 405_500, "000815")   # ambiguous_atr → 새 키
    hits = _msgs(caplog, SKIPPED)
    assert len(hits) == 2
    assert sum("reason=no_atr " in m for m in hits) == 1
    assert sum("reason=ambiguous_atr " in m for m in hits) == 1


@freeze_time("2026-09-03 10:00:00+09:00")
def test_f242_8c_cap_is_instance_scoped(caplog):
    a = _mini(candidates={"000815": {"atr": 13300}})
    b = _mini(candidates={"000815": {"atr": 13300}})
    with caplog.at_level(logging.INFO):
        a._apply_budget_limit(0, 405_500, "000815")
        b._apply_budget_limit(0, 405_500, "000815")
    assert len(_msgs(caplog, CAPPED)) == 2


def test_f242_8d_cap_resets_on_kst_date_change(caplog):
    """날짜 키 자기 리셋 — `_reset_daily_state` 훅에 의존하지 않는다."""
    s = _mini(candidates={"000815": {"atr": 13300}})
    with caplog.at_level(logging.INFO):
        with freeze_time("2026-09-03 10:00:00+09:00"):
            s._apply_budget_limit(0, 405_500, "000815")
        with freeze_time("2026-09-04 10:00:00+09:00"):
            s._apply_budget_limit(0, 405_500, "000815")
    assert len(_msgs(caplog, CAPPED)) == 2
    assert len(_msgs(caplog, CONFIG)) == 2


@freeze_time("2026-09-03 10:00:00+09:00")
def test_f242_8e_config_marker_once_per_strategy_per_day(caplog):
    s = _mini(candidates={"000815": {"atr": 13300}, "004690": {"atr": 4290}})
    with caplog.at_level(logging.INFO):
        s._apply_budget_limit(0, 405_500, "000815")
        s._apply_budget_limit(0, 130_000, "004690")
        s._apply_budget_limit(0, 130_000, "004690")
    assert len(_msgs(caplog, CONFIG)) == 1


# ===========================================================================
# F-9 — peek → 로그 → mark, 그리고 행위는 cap 밖
# ===========================================================================
def _raising_info(monkeypatch, marker: str):
    """`marker` 를 포함한 포맷 문자열에 대해서만 raise 하는 logger 주입."""
    original_info = sb_mod.logger.info
    original_warning = sb_mod.logger.warning

    def _info(msg, *a, **k):
        if marker in str(msg):
            raise RuntimeError("logger down")
        return original_info(msg, *a, **k)

    def _warning(msg, *a, **k):
        if marker in str(msg):
            raise RuntimeError("logger down")
        return original_warning(msg, *a, **k)

    monkeypatch.setattr(sb_mod.logger, "info", _info)
    monkeypatch.setattr(sb_mod.logger, "warning", _warning)


@freeze_time("2026-09-03 10:00:00+09:00")
@pytest.mark.parametrize("marker,setup", [
    (CAPPED, "capped"),
    (SKIPPED, "skipped"),
    (CONFIG, "config"),
])
def test_f242_9_peek_log_mark_and_behaviour_outside_cap(
    marker, setup, monkeypatch, caplog
):
    """로그가 던져도 (a) 수량 불변 (b) 예외 전파 0 (c) 복구 후 재발화."""
    if setup == "skipped":
        s = _mini(candidates={"000815": {"atr": 0}})
        expected = 1
    else:
        s = _mini(candidates={"000815": {"atr": 13300}})
        expected = 0

    with monkeypatch.context() as mp:
        _raising_info(mp, marker)
        try:
            first = s._apply_budget_limit(0, 405_500, "000815")
        except RuntimeError:
            pytest.fail(f"{marker} 로그 실패가 매수 수량 산출로 전파됨")
    assert first == expected, "관측 실패가 행위를 바꿨다 (행위는 cap 밖이 계약)"

    with caplog.at_level(logging.INFO):
        second = s._apply_budget_limit(0, 405_500, "000815")
    assert second == expected
    assert len(_msgs(caplog, marker)) == 1, (
        f"{marker} 가 재발화하지 않았다 — 로그 실패 전에 mark 를 찍었다"
    )


# ===========================================================================
# F-10 — 파라미터 클램프 (읽는 쪽 [1.0, 20.0])
# ===========================================================================
@pytest.mark.parametrize("raw,expected", [
    (0, 2.0),
    (-1, 2.0),
    ("abc", 2.0),
    (None, 2.0),
    (True, 2.0),
    (False, 2.0),
    (0.99, 2.0),
    (float("inf"), 2.0),
    (float("nan"), 2.0),
    (999, 20.0),
    (1.0, 1.0),
    (20.0, 20.0),
    (2.5, 2.5),
    ("2.5", 2.5),
])
def test_f242_10a_read_max_lot_units_clamp(raw, expected):
    s = _mini(max_lot_units=raw)
    assert s._read_max_lot_units() == pytest.approx(expected)


def test_f242_10b_default_when_key_absent():
    s = _mini()
    assert s._read_max_lot_units() == pytest.approx(sb_mod._MAX_LOT_UNITS_DEFAULT)


@freeze_time("2026-09-03 10:00:00+09:00")
def test_f242_10c_rollback_dial_k20_restores_current_behaviour(caplog):
    """K=20 = 롤백 다이얼 — 000815 가 다시 1주로 통과한다."""
    s = _mini(max_lot_units=20.0, candidates={"000815": {"atr": 13300}})
    with caplog.at_level(logging.INFO):
        qty = s._apply_budget_limit(0, 405_500, "000815")
    assert qty == 1
    assert not _msgs(caplog, CAPPED)


@freeze_time("2026-09-03 10:00:00+09:00")
def test_f242_10d_k1_is_option_a_equivalent(caplog):
    """K=1.0 = ⓐ('<1주면 스킵') 등가 — 004690 도 0 이 된다."""
    s = _mini(max_lot_units=1.0, candidates={"004690": {"atr": 4290}})
    with caplog.at_level(logging.INFO):
        qty = s._apply_budget_limit(0, 130_000, "004690")
    assert qty == 0
    assert len(_msgs(caplog, CAPPED)) == 1


@freeze_time("2026-09-03 10:00:00+09:00")
def test_f242_10e_k_zero_is_not_total_blockade(caplog):
    """K=0 은 전면 매수 차단이 아니라 기본 2.0 으로 클램프된다."""
    blocked = _mini(max_lot_units=0, candidates={"000815": {"atr": 13300}})
    passing = _mini(max_lot_units=0, candidates={"004690": {"atr": 4290}})
    with caplog.at_level(logging.INFO):
        assert blocked._apply_budget_limit(0, 405_500, "000815") == 0
        assert passing._apply_budget_limit(0, 130_000, "004690") == 1


# ===========================================================================
# F-11 — DEFAULT_PARAMS · DB 병합(롤백 경로 전제)
# ===========================================================================
_TURTLE_STRATEGY_MODULES = [
    ("donchian_swing", "DonchianSwingStrategy"),
    ("kojiro", "KojiroStrategy"),
    ("vcp_breakout", "VcpBreakoutStrategy"),
    ("bull_flag_breakout", "BullFlagBreakoutStrategy"),
]
_NON_TURTLE_STRATEGY_MODULES = [
    ("momentum", "MomentumStrategy"),
    ("volatility_breakout", "VolatilityBreakoutStrategy"),
    ("long_tail_volatility", "LongTailVolatilityStrategy"),
]


def _strategy_cls(module: str, cls_name: str):
    import importlib

    return getattr(importlib.import_module(f"src.engine.strategies.{module}"), cls_name)


@pytest.mark.parametrize("module,cls_name", _TURTLE_STRATEGY_MODULES)
def test_f242_11a_turtle_defaults_carry_max_lot_units(module, cls_name):
    cls = _strategy_cls(module, cls_name)
    assert cls.DEFAULT_PARAMS.get("max_lot_units") == pytest.approx(2.0)
    assert cls.DEFAULT_PARAMS["max_lot_units"] == pytest.approx(
        sb_mod._MAX_LOT_UNITS_DEFAULT
    )


@pytest.mark.parametrize("module,cls_name", _NON_TURTLE_STRATEGY_MODULES)
def test_f242_11b_fixed_stop_defaults_omit_max_lot_units(module, cls_name):
    cls = _strategy_cls(module, cls_name)
    assert "max_lot_units" not in cls.DEFAULT_PARAMS, (
        "고정%손절 전략에 키가 있으면 '적용 대상'으로 오독된다 (범위 밖 계약)"
    )


def test_f242_11c_db_merge_idiom_reaches_reader():
    """`scheduler._load_strategy_config` 병합 관용구(`if key in params`)로 20.0 주입."""
    s = _dc()
    assert "max_lot_units" in s.config.params, "DB 병합의 전제 = 키가 존재해야 한다"
    for key, val in {"max_lot_units": 20.0}.items():
        if key in s.config.params:
            s.config.params[key] = val
    assert s._read_max_lot_units() == pytest.approx(20.0)


# ===========================================================================
# F-12 — `[oversized_fallback] units=` 확장 (접두 byte 보존)
# ===========================================================================
@freeze_time("2026-09-03 10:00:00+09:00")
def test_f242_12a_units_dash_when_atr_unknown(caplog):
    """터틀 모드라도 ATR 을 못 읽으면 `units=-`."""
    s = _mini(candidates={})
    with caplog.at_level(logging.INFO):
        s._apply_budget_limit(0, 405_500, "000815")
    over = _msgs(caplog, OVERSIZED)
    assert len(over) == 1
    assert over[0].endswith("units=-")


@freeze_time("2026-09-03 10:00:00+09:00")
def test_f242_12b_cycle233_prefix_is_byte_preserved(caplog):
    """cycle233 계약(`"3.10" in message` + 접두 문구) 보존 + 꼬리에만 units 추가."""
    s = _mini(sizing_mode=None, risk_pct=None, budget=789_130,
              candidates={"000815": {"atr": 13300}})
    with caplog.at_level(logging.INFO):
        qty = s._apply_budget_limit(0, 405_500, "000815")
    assert qty == 1
    over = _msgs(caplog, OVERSIZED)
    assert len(over) == 1
    assert "3.10" in over[0]
    assert (
        "[oversized_fallback] ticker=000815 strategy=kojiro qty=1 notional=405500 "
        "cap=130995 ratio=3.10 — 1주 폴백이 notional 상한 초과 (관측 전용)"
    ) in over[0]
    assert over[0].endswith("units=-")


# ===========================================================================
# F-13 — config 마커 (캡이 조용히 꺼진 채 매수하는 사고 감지)
# ===========================================================================
@freeze_time("2026-09-03 10:00:00+09:00")
def test_f242_13a_config_marker_turtle_on(caplog):
    s = _mini(candidates={"004690": {"atr": 4290}})
    with caplog.at_level(logging.INFO):
        s._apply_budget_limit(0, 130_000, "004690")
    cfg = _msgs(caplog, CONFIG)
    assert len(cfg) == 1
    assert cfg[0] == (
        "[fallback_cap_config] strategy=kojiro sizing_mode=turtle cap=on k=2.00 "
        "budget=774640 risk_pct=0.0050 atr_max=7746"
    )
    assert _recs(caplog, CONFIG)[0].levelno == logging.INFO


@freeze_time("2026-09-03 10:00:00+09:00")
def test_f242_13b_config_marker_position_ratio_off(caplog):
    s = _mini(sizing_mode="position_ratio", candidates={"004690": {"atr": 4290}})
    with caplog.at_level(logging.INFO):
        s._apply_budget_limit(0, 130_000, "004690")
    cfg = _msgs(caplog, CONFIG)
    assert len(cfg) == 1
    assert "sizing_mode=position_ratio" in cfg[0] and "cap=off" in cfg[0]


@freeze_time("2026-09-03 10:00:00+09:00")
@pytest.mark.parametrize("price,budget", [(0, KOJIRO_BUDGET), (405_500, 100_000)])
def test_f242_13c_no_config_when_final_below_one(price, budget, caplog):
    """`final < 1`(가격 0 / 잔여 부족) 에서는 어떤 마커도 찍지 않는다."""
    s = _mini(budget=budget, candidates={"000815": {"atr": 13300}})
    with caplog.at_level(logging.INFO):
        qty = s._apply_budget_limit(0, price, "000815")
    assert qty == 0
    assert not _msgs(caplog, CONFIG)
    assert not _msgs(caplog, CAPPED)
    assert not _msgs(caplog, SKIPPED)


# ===========================================================================
# F-14 — 캡 ATR = 사이징 ATR (소스 동일성)
# ===========================================================================
@freeze_time("2026-09-03 10:00:00+09:00")
def test_f242_14a_donchian_resolver_matches_stamped_entry_atr():
    s = _dc(budget=100_000_000)
    s._candidates["005930"] = {
        "prev_close": 60000, "atr": 3000, "ema60": 0, "donchian_high": 0,
    }
    s.calc_buy_quantity(60_000, "005930")
    assert s._entry_atr["005930"] == 3000.0
    assert s._resolve_sizing_atr("005930") == (3000.0, "ok")


@freeze_time("2026-09-03 10:00:00+09:00")
@pytest.mark.parametrize("maker,key", [("vcp", "atr14"), ("bfb", "atr14")])
def test_f242_14b_vcp_bfb_resolver_reads_native_key(maker, key):
    s = {"vcp": _vcp, "bfb": _bfb}[maker](budget=100_000_000)
    s._candidates["005930"] = {key: 3000}
    s.calc_buy_quantity(60_000, "005930")
    assert s._entry_atr["005930"] == 3000.0
    assert s._resolve_sizing_atr("005930") == (3000.0, "ok")


@freeze_time("2026-09-03 10:00:00+09:00")
def test_f242_14c_kojiro_resolver_matches_sizing_atr():
    s = _kj(budget=100_000_000)
    s._candidates["005930"] = {"atr": 3000}
    qty = s.calc_buy_quantity(60_000, "005930")
    assert qty == compute_unit_qty_guarded(
        100_000_000, 3000.0, 60_000, RISK,
        remaining_budget=100_000_000, min_vol_pct=1.0, position_ratio=0.20,
    )
    assert s._resolve_sizing_atr("005930") == (3000.0, "ok")


@pytest.mark.parametrize("info,expected", [
    ({"atr": 3000, "atr14": 3200}, (None, "ambiguous_atr")),
    ({"atr": 3000, "atr14": 3000}, (3000.0, "ok")),
    ({"atr": 3000, "atr14": 0}, (3000.0, "ok")),
    ({"atr14": 3200}, (3200.0, "ok")),
    ({"atr": 0, "atr14": 0}, (None, "no_atr")),
    ({}, (None, "no_atr")),
])
def test_f242_14d_resolver_matrix(info, expected):
    s = _mini(candidates={"T": info})
    assert s._resolve_sizing_atr("T") == expected


def test_f242_14e_resolver_no_ticker_and_no_dict():
    s = _mini(candidates={"T": {"atr": 3000}})
    assert s._resolve_sizing_atr(None) == (None, "no_ticker")
    assert s._resolve_sizing_atr("") == (None, "no_ticker")
    assert s._resolve_sizing_atr("MISSING") == (None, "no_atr")
    s2 = _mini(set_candidates=False)
    assert s2._resolve_sizing_atr("T") == (None, "no_candidates")


def test_f242_14f_sizing_atr_keys_contract():
    assert StrategyBase._SIZING_ATR_KEYS == ("atr", "atr14")


# ===========================================================================
# F-15 — `_candidates` read-only
# ===========================================================================
def test_f242_15_resolver_is_read_only():
    import copy

    s = _mini(candidates={"T": {"atr": 3000, "ema60": 5}, "U": {}})
    before = copy.deepcopy(s._candidates)
    s._resolve_sizing_atr("T")
    s._resolve_sizing_atr("U")
    s._resolve_sizing_atr("MISSING")
    s._resolve_sizing_atr(None)
    assert s._candidates == before
    assert "MISSING" not in s._candidates


# ===========================================================================
# F-16 — 항등식: 모든 경로에서 랏 유닛 ≤ K
# ===========================================================================
@freeze_time("2026-09-03 10:00:00+09:00")
def test_f242_16_lot_units_never_exceed_k():
    budgets = (387_320, 774_640, 5_000_000)
    ratios = (0.166, 0.20, 0.25)
    ks = (1.0, 2.0, 2.5, 20.0)
    atrs = (500, 1_500, 4_000, 13_300, 40_000)
    prices = (3_000, 20_000, 60_000, 130_000, 500_000)

    checked = 0
    binding = 0
    for budget in budgets:
        for ratio in ratios:
            for k in ks:
                s = _mini(budget=budget, ratio=ratio, max_lot_units=k,
                          candidates={"T": {"atr": atrs[0]}})
                for atr in atrs:
                    s._candidates["T"] = {"atr": atr}
                    unit_budget = budget * RISK
                    for price in prices:
                        pr_qty = int(budget * ratio) // price
                        for q in (0, pr_qty):
                            final = s._apply_budget_limit(q, price, "T")
                            checked += 1
                            assert final >= 0
                            if final >= 1:
                                units = final * atr / unit_budget
                                assert units <= k + 1e-9, (
                                    f"budget={budget} ratio={ratio} k={k} atr={atr} "
                                    f"price={price} q={q} → final={final} "
                                    f"units={units:.3f} > K"
                                )
                                if units > k - 1.0:
                                    binding += 1
    assert checked > 1_000
    assert binding > 0, "그리드가 상한 근처를 전혀 밟지 않았다 (공허한 단언)"


# ===========================================================================
# F-18 — order_engine 오귀인 근거 (읽기만, 8영역 무접촉)
# ===========================================================================
def test_f242_18_low_funds_cooldown_regression_exists():
    """캡→0 은 `execute_buy` 의 수량 0 경로로 흘러 900s cooldown 을 건다(오귀인).

    그 경로의 기존 회귀가 존재함을 확인만 한다 — 8영역(order_engine) 무접촉.
    """
    from pathlib import Path

    root = Path(__file__).resolve().parents[3]
    target = root / "tests" / "unit" / "engine" / "test_order_engine_buy.py"
    assert target.exists()
    assert "block_low_funds" in target.read_text(encoding="utf-8")


# ===========================================================================
# F-19 — `_emit_budget_clamp` mark-before-log 동행 시정 (§2.6)
# ===========================================================================
@freeze_time("2026-09-03 10:00:00+09:00")
def test_f242_19_budget_clamp_marks_after_log(monkeypatch, caplog):
    """로그가 던진 날의 관측이 통째로 지워지면 안 된다 (cycle226 D-3 규약)."""
    s = _mini(sizing_mode="position_ratio", budget=100_000, ratio=0.20)
    with monkeypatch.context() as mp:
        _raising_info(mp, CLAMP)
        try:
            first = s._apply_budget_limit(10, 30_000, "005930")
        except RuntimeError:
            pytest.fail("[budget_clamp] 로그 실패가 매수 수량 산출로 전파됨")
    assert first == 3

    with caplog.at_level(logging.INFO):
        second = s._apply_budget_limit(10, 30_000, "005930")
    assert second == 3
    assert len(_msgs(caplog, CLAMP)) == 1, (
        "[budget_clamp] 가 재발화하지 않았다 — mark 가 로그보다 앞에 있다"
    )


# ===========================================================================
# 사후 정합 — 캡 산출은 turtle_sizing.compute_unit_qty 재사용 (새 수식 금지)
# ===========================================================================
@freeze_time("2026-09-03 10:00:00+09:00")
def test_f242_20_cap_equals_compute_unit_qty_with_fraction_k():
    """`cap_qty == compute_unit_qty(budget, atr, risk_pct, fraction=K)` 동치."""
    from src.engine.turtle_sizing import compute_unit_qty

    for atr, price in ((13300, 405_500), (4290, 130_000), (3593, 38_000)):
        for k in (1.0, 2.0, 2.5):
            s = _mini(max_lot_units=k, candidates={"T": {"atr": atr}})
            expected_cap = compute_unit_qty(KOJIRO_BUDGET, float(atr), RISK,
                                            fraction=k)
            assert expected_cap == math.floor(KOJIRO_BUDGET * RISK / atr * k)
            got = s._apply_budget_limit(999_999, price, "T")
            remaining_cap = KOJIRO_BUDGET // price
            assert got == min(expected_cap, remaining_cap)


# ===========================================================================
# 라운드 1 — tester 적대적 검증 확증 결함 시정 회귀 (2026-09-03)
#
# 명세: `_workspace/red/cycle242_fallback_notional_cap_spec.md` §11
#
# R1/R2 (MEDIUM #1·#2 통합) — `_apply_lot_units_cap` 의 `except Exception` 흡수
#   경로에서 `logger.debug` 가 관측 emit 과 **같은 inner try** 밖에 있어, 로거가
#   죽으면 예외가 관문 밖(→ `calc_buy_quantity` → `order_engine.execute_buy`)
#   으로 전파됐다. §3 불변계약 9("행위는 cap 밖 — 관측 성패와 무관")가 관측
#   *시도* 에도 적용됨을 명시적으로 봉인한다.
# R3 (MEDIUM #3) — PR 경로(`path=sized`) 랏이 `ambiguous_atr`/`no_atr` 로
#   fail-open 스킵되면 K 초과 사실이 어떤 마커에도 안 남던 사각을 `atr=`/
#   `units=` 진단 필드로 메운다(캡 산출 자체는 무변경 — 순수 관측 확장).
# R4 (MEDIUM #4) — `max_lot_units` 클램프가 "키 부재(기본값)"와 "PUT 무효
#   값"을 구별 없이 흡수해 `[fallback_cap_config] k=2.00` 만으로는 운영자가
#   둘을 못 갈랐다. `[fallback_cap_clamped]` 를 **키가 명시적으로 존재할
#   때만** 발화시킨다.
# R7 (tester 발견 뮤테이션 escape m5b) — `_apply_lot_units_cap` 외곽
#   `except Exception` 이 `final==1` 픽스처(F-5e)로만 봉인돼 있어
#   `return final` → `return 1` 뮤턴트가 검출되지 않았다. `final>1` 경로
#   (잔여 클램프로 도달한 큰 수량)로 대조한다.
# ===========================================================================
@freeze_time("2026-09-03 10:00:00+09:00")
def test_f242_r1_debug_logger_failure_does_not_propagate(monkeypatch, caplog):
    """캡 예외 흡수 경로에서 `logger.debug` 도 죽어도 관문 밖으로 전파되지 않는다.

    시정 전에는 `logger.debug` 가 `_emit_fallback_cap_skipped` 호출과 별도의
    무방비 지점이라, 이 재현이 `RuntimeError: debug logger down` 을 관문
    밖으로 던졌다(재현: compute_unit_qty 를 raise 로, logger.debug 도 raise
    로 동시 패치 → `_apply_budget_limit` 호출).
    """
    s = _mini(candidates={"000815": {"atr": 13300}})

    def _boom(*a, **k):
        raise RuntimeError("compute boom")

    def _debug_boom(*a, **k):
        raise RuntimeError("debug logger down")

    monkeypatch.setattr(sb_mod, "compute_unit_qty", _boom, raising=False)
    monkeypatch.setattr(sb_mod.logger, "debug", _debug_boom)
    with caplog.at_level(logging.INFO):
        try:
            qty = s._apply_budget_limit(0, 405_500, "000815")
        except RuntimeError:
            pytest.fail("logger.debug 실패가 관문 밖으로 전파됨 (R1/R2 회귀)")
    assert qty == 1, "fail-open 이 깨졌다 — 현행 수량(1주) 유지가 계약"
    hits = _recs(caplog, SKIPPED)
    assert len(hits) == 1
    assert "reason=exception " in hits[0].getMessage()


@freeze_time("2026-09-03 10:00:00+09:00")
def test_f242_r3_ambiguous_atr_pr_path_now_visible(caplog):
    """finding #3 재현 — donchian PR 경로가 ambiguous_atr 로 fail-open 스킵될 때
    이전에는 K 초과 사실이 마커에 전혀 안 남았다(`[oversized_fallback]` 도
    notional ≤ ρ×예산 이라 미발화). `atr=`/`units=` 진단 필드가 이제 그
    사실(units 3.71/3.72 > K=2.00)을 노출한다. 행위(qty 그대로 통과)는
    fail-open 계약대로 **불변**이다 — 이 테스트는 관측 확장만 검증한다.
    """
    s = _mini(
        strategy_id="donchian_swing", budget=DONCHIAN_BUDGET, ratio=0.20,
        candidates={"124500": {"atr": 3593, "atr14": 3600}},
    )
    with caplog.at_level(logging.INFO):
        qty = s._apply_budget_limit(2, 38_000, "124500")

    assert qty == 2, "ambiguous_atr fail-open 은 현행 수량을 바꾸지 않는다"
    over = _msgs(caplog, OVERSIZED)
    assert not over, "ρ 축 상한은 이 랏에서 원래 발화하지 않는다(76,000 ≤ 77,464)"
    hits = _recs(caplog, SKIPPED)
    assert len(hits) == 1
    msg = hits[0].getMessage()
    assert "reason=ambiguous_atr " in msg
    assert "atr=atr=3593|atr14=3600 " in msg, f"진단 atr= 필드 누락/오값: {msg}"
    assert "units=3.71|3.72 " in msg, f"진단 units= 필드 누락/오값: {msg}"


@freeze_time("2026-09-03 10:00:00+09:00")
def test_f242_r3_skip_diagnostics_dash_when_no_candidate_values(caplog):
    """진단값이 하나도 없으면 `atr=-`/`units=-` (never-raise 계약)."""
    s = _mini(set_candidates=False)
    with caplog.at_level(logging.INFO):
        s._apply_budget_limit(0, 405_500, "000815")
    hits = _recs(caplog, SKIPPED)
    assert len(hits) == 1
    msg = hits[0].getMessage()
    assert "atr=- " in msg
    assert "units=- " in msg


@freeze_time("2026-09-03 10:00:00+09:00")
def test_f242_r4_clamp_marker_on_explicit_invalid_value(caplog):
    """명시적 무효 값(PUT/DB)이 클램프될 때만 `[fallback_cap_clamped]` 가 뜬다.

    raw=0.5 는 MIN(1.0) 미만이라 **DEFAULT(2.0)** 로 클램프된다(§2.8 계약 —
    <MIN 은 DEFAULT 로, MIN 자체로 클램프되지 않는다). 실효 K=2.0 이므로
    수량은 F-1 과 동일 시나리오(000815/774,640/13,300)라 0 이 된다 — 이
    테스트의 초점은 수량이 아니라 클램프 마커 발화다.
    """
    s = _mini(max_lot_units=0.5, candidates={"000815": {"atr": 13300}})
    with caplog.at_level(logging.INFO):
        qty = s._apply_budget_limit(0, 405_500, "000815")
    assert qty == 0
    hits = _msgs(caplog, LOT_CLAMPED)
    assert len(hits) == 1
    assert "raw=0.5" in hits[0]
    assert "clamped_to=2.00" in hits[0]
    assert "strategy=kojiro" in hits[0]


@freeze_time("2026-09-03 10:00:00+09:00")
def test_f242_r4_no_clamp_marker_when_key_absent(caplog):
    """키 부재(코드 기본값 사용)는 클램프가 아니므로 무발화."""
    s = _mini(candidates={"000815": {"atr": 13300}})
    assert "max_lot_units" not in s.config.params
    with caplog.at_level(logging.INFO):
        s._apply_budget_limit(0, 405_500, "000815")
    assert not _msgs(caplog, LOT_CLAMPED)


@freeze_time("2026-09-03 10:00:00+09:00")
def test_f242_r4_no_clamp_marker_when_key_valid(caplog):
    """키가 존재하되 유효 범위 내(`[MIN, MAX]`)면 클램프가 아니므로 무발화."""
    s = _mini(max_lot_units=2.5, candidates={"000815": {"atr": 13300}})
    with caplog.at_level(logging.INFO):
        s._apply_budget_limit(0, 405_500, "000815")
    assert not _msgs(caplog, LOT_CLAMPED)
    assert s._read_max_lot_units() == pytest.approx(2.5)


@pytest.mark.parametrize("raw", [1.0, 20.0])
def test_f242_r4_no_clamp_marker_at_exact_boundaries(raw, caplog):
    """정확히 MIN(1.0)/MAX(20.0) 경계값은 클램프가 아니다 (off-by-one 방지)."""
    s = _mini(max_lot_units=raw, candidates={"000815": {"atr": 13300}})
    with freeze_time("2026-09-03 10:00:00+09:00"), caplog.at_level(logging.INFO):
        s._apply_budget_limit(0, 405_500, "000815")
    assert not _msgs(caplog, LOT_CLAMPED)


def test_f242_r4_clamp_marker_once_per_strategy_per_day(caplog):
    """1회/전략/일 cap — `_lot_cap_logged` 공유 상태의 `"clamp"` 키가 분리돼 있다."""
    s = _mini(
        max_lot_units=0.5,
        candidates={"000815": {"atr": 13300}, "004690": {"atr": 4290}},
    )
    with freeze_time("2026-09-03 10:00:00+09:00"), caplog.at_level(logging.INFO):
        s._apply_budget_limit(0, 405_500, "000815")
        s._apply_budget_limit(0, 130_000, "004690")
    assert len(_msgs(caplog, LOT_CLAMPED)) == 1


@freeze_time("2026-09-03 10:00:00+09:00")
def test_f242_r7_cap_exception_preserves_large_final_qty(monkeypatch, caplog):
    """뮤테이션 escape m5b 봉인 — `except: return final` 을 `return 1` 로 바꾸는
    변조는 F-5e(폴백 1주, `final==1`)만으로는 검출되지 않는다(상수 1 과
    구별 불가). 여기는 잔여 클램프 경로(`final=50`)로 대조한다.
    """
    s = _mini(budget=100_000_000, candidates={"005930": {"atr": 3000}})

    def _boom(*a, **k):
        raise RuntimeError("boom")

    monkeypatch.setattr(sb_mod, "compute_unit_qty", _boom, raising=False)
    with caplog.at_level(logging.INFO):
        qty = s._apply_budget_limit(50, 60_000, "005930")
    assert qty == 50, (
        "캡 예외 fail-open 이 final 을 상수로 덮어썼다 (m5b 뮤테이션 미검출 경로)"
    )
    hits = _recs(caplog, SKIPPED)
    assert len(hits) == 1
    assert "reason=exception " in hits[0].getMessage()
