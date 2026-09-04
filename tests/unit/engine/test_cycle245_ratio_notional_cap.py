"""cycle245 Red — 비터틀 랏 명목 ρ축 상한 `max_lot_ratio_mult`(K_ρ=2.5).

명세: `_workspace/red/cycle245_ratio_notional_cap_spec.md` §4.1
근거: `_workspace/review_0904_intraday.md` §5 + `_workspace/domain_consult/cycle245_ratio_notional_cap.md`

## 고칠 결함 (한 문장)

cycle242 의 랏 상한은 **ATR 축(K)** 이라 `sizing_mode == "turtle"` 전략만 심사한다.
비터틀 5전략(momentum·VB·LTV·BFB·VCP)은 `risk_pct`·진입 ATR 스탬프가 아예 없어
캡이 `cap=off` 로 지나가고, `_fallback_one_share` 의 1주가 **그 종목 주가 그대로**
랏이 된다 — 09-04 LTV 000500 은 220,000원 1주 = 설계 랏(`position_ratio × 예산`
= 52,040)의 **4.23배**였고 09:32 손절 −11,000원 = 그날 최대 단일 손실이었다.

## 시정 (사용자 결정 2026-09-04 "K=2.0 유지하고 cycle245 도 진행해줘")

관문 `_apply_budget_limit` 안에서 **K축이 이 랏을 실제로 심사하지 못한 모든 랏**에
`min(final, int(K_ρ × int(예산 × position_ratio)) // 현재가)` 를 적용하고, 1주도 못
사면 매수하지 않는다. K_ρ = `max_lot_ratio_mult` = 2.5 — 리스크 정체성 상수
(PARAM_RANGES/INT_PARAMS 편입 금지, 읽는 쪽 `[1.0, 20.0]` 클램프, 키 부재 = OFF).

## 이 파일이 봉인하는 것

- F-1  현행에서 09-04 000500 재현 입력이 **1주를 반환**한다(시정 후 **0**). 핵심 Red.
- F-4/F-5 K_ρ ≥ 1 이면 주 분기(정상 비중 랏)는 **한 건도 안 건드린다** — 항등식.
- F-6  키 부재 = OFF. **fail-closed(키 없으면 차단)는 P0-1 유령 키 재현 경로**라 금지.
- F-7/F-8 두 캡은 **상호배타** — K축이 심사하면 ρ축은 손대지 않고(정상 터틀 랏 보호),
       터틀인데 ATR 배관이 끊긴 랏은 ρ축이 **백스톱**으로 받는다.
- F-10 결측·모호·예외는 전부 fail-open(현행 수량 유지 + LOUD). 수량 0 이면 FAIL.
- F-12/F-13 행위는 cap 밖 · peek→로그→mark(cycle237/cycle226 D-3 계약).

## 명세 문언 정합 메모 (Red 작성 중 발견 — Green 은 참조 구현 §2.4 를 따른다)

1. **F-8 픽스처 정정** — 명세 F-8 은 donchian `B=390,300` + `price 405,500` 을 쓰는데
   그 조합은 `_fallback_one_share` 의 잔여 검사(`390,300 < 405,500`)에서 **먼저 0** 이
   되어 ρ캡이 발화할 수 없다(`final < 1` 조기탈출). 백스톱 경로를 실제로 밟도록
   `price = 300,000`(cutoff 195,150 초과, 잔여 이내)으로 교체했다. 검증 의도 불변.
2. **F-7 마커 정정** — 명세 F-7 은 "`[ratio_cap_config] cap=backstop` 1행"을 kojiro
   000815(=cycle242 가 **0** 으로 자르는 랏)에서 기대하지만, `final < 1` 이면 ρ캡은
   config 도 찍지 않는다(명세 F-16 의 "final<1 미발화"와 자기모순). 그래서 F-7 을
   (a) K축이 0 으로 자르는 랏 = ρ 마커 **전무** (b) K축을 통과했지만 ρ 상한을 넘는
   터틀 랏 = **수량 불변 + `cap=backstop`** 두 케이스로 갈랐다. (b) 가 "정상 터틀 랏을
   ρ 로 자르지 않는다"는 결정 ⑤·⑦의 직접 증거다.
3. **F-10(d) 경로 정정** — `_lot_units_cap_governs` **자체**를 raise 로 monkeypatch 하면
   참조 구현에서는 바깥 try 가 잡아 `reason=exception` 이 된다(`k_axis_probe_error` 는
   판정기 **내부** 예외 전용). 그래서 (d)는 `_resolve_sizing_atr` 을 raise 시켜
   판정기 내부에서 터뜨린다. 두 사유 모두 fail-open 이라 행위는 동일하다.
4. **"행위는 cap 밖"의 경계** — 이 계약(§3-9)이 지키는 것은 **cap 소진**(F-12a)과
   **로그 자기실패**(F-13a)뿐이다. 둘 다 emit **내부** try 가 흡수하므로 차단은 그대로
   수행된다. 반면 emit **메서드 자체**가 던지면 `_apply_ratio_notional_cap` 의 바깥
   fail-open try 가 잡아 **캡 이전 수량**이 반환된다(F-10f) — 두 방향을 한 테스트로
   뭉치면 "fail-open" 과 "cap 밖 행위" 가 서로를 지운다.
"""

from __future__ import annotations

import inspect
import logging
import math
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from freezegun import freeze_time

from src.engine import strategy_base as sb_mod
from src.engine.strategy_base import Signal, StrategyBase, StrategyConfig

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parents[3]

# ── 결정적 기준선 (09-04 LTV 실측 예산 260,203 을 260,200 으로 라운드) ──
LTV_BUDGET = 260_200
LTV_RATIO = 0.20
LTV_CAP = 52_040            # int(260,200 × 0.20)
LTV_CUTOFF = 130_100        # int(2.5 × 52,040)  ⚠️ 자문 §9.1 의 130,103 은 오산(정수 절삭 2회)
K_RHO = 2.5

# cycle233 000815 픽스처 (ρ=0.166 · B=789,130 → cap 130,995)
KJ_BUDGET = 789_130
KJ_RATIO = 0.166
KJ_CAP = 130_995

DONCHIAN_BUDGET = 390_300   # ρ=0.20 → cap 78,060 → cutoff 195,150
DONCHIAN_CAP = 78_060
DONCHIAN_CUTOFF = 195_150
RISK = 0.005

# cycle245 신규 마커
BLOCKED = "[ratio_notional_blocked]"
RSKIP = "[ratio_cap_skipped]"
RCONFIG = "[ratio_cap_config]"
RCLAMP = "[ratio_cap_clamped]"
# 기존 마커 (cycle233 / cycle242)
OVERSIZED = "[oversized_fallback]"
CAPPED = "[fallback_notional_capped]"
FSKIP = "[fallback_cap_skipped]"
FCONFIG = "[fallback_cap_config]"


# ---------------------------------------------------------------------------
# 픽스처 — cycle233/cycle242 `_MiniStrategy` 패턴 (StrategyBase 직접 상속)
# ---------------------------------------------------------------------------
class _MiniStrategy(StrategyBase):
    """관문 테스트용 최소 구현 (DEFAULT_PARAMS 병합을 타지 않는다)."""

    async def prepare(self):  # pragma: no cover
        return None

    def check_buy_signal(self, ticker, current_price, open_price):
        return Signal.NONE

    def check_exit_signal(self, ticker, current_price, open_price):
        return Signal.NONE

    def calc_buy_quantity(self, current_price: int, ticker: str | None = None) -> int:
        return self._apply_budget_limit(0, current_price, ticker)


def _mini(
    strategy_id: str = "long_tail_volatility",
    *,
    budget: int = LTV_BUDGET,
    ratio: float | None = LTV_RATIO,
    k: float | None = K_RHO,
    sizing_mode: str | None = None,
    risk_pct: float | None = None,
    candidates: dict | None = None,
    set_candidates: bool = True,
    **extra,
) -> _MiniStrategy:
    params: dict = {"exchange": "KRX", **extra}
    if ratio is not None:
        params["position_ratio"] = ratio
    if k is not None:
        params["max_lot_ratio_mult"] = k
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
    """실전략 donchian (DEFAULT_PARAMS 병합 = Green 이후 `max_lot_ratio_mult` 보유)."""
    from src.engine.strategies.donchian_swing import DonchianSwingStrategy

    params = {"sizing_mode": "turtle" if turtle else "position_ratio", **extra}
    s = DonchianSwingStrategy(
        StrategyConfig(strategy_id="donchian_swing", name="도치안", weight=0.2,
                       params=params)
    )
    s.state.total_investment = budget
    return s


def _kj(*, turtle: bool = True, budget: int = 774_640, **extra):
    from src.engine.strategies.kojiro import KojiroStrategy

    params = {"sizing_mode": "turtle" if turtle else "position_ratio", **extra}
    s = KojiroStrategy(
        StrategyConfig(strategy_id="kojiro", name="고지로", weight=0.3, params=params)
    )
    s.state.total_investment = budget
    return s


def _real(strategy_id: str, *, budget: int, **extra):
    """7 전략 실클래스 인스턴스 (DEFAULT_PARAMS 병합 경로)."""
    import importlib

    mapping = {
        "momentum": ("momentum", "MomentumStrategy"),
        "volatility_breakout": ("volatility_breakout", "VolatilityBreakoutStrategy"),
        "long_tail_volatility": ("long_tail_volatility", "LongTailVolatilityStrategy"),
        "bull_flag_breakout": ("bull_flag_breakout", "BullFlagBreakoutStrategy"),
        "vcp_breakout": ("vcp_breakout", "VcpBreakoutStrategy"),
        "donchian_swing": ("donchian_swing", "DonchianSwingStrategy"),
        "kojiro": ("kojiro", "KojiroStrategy"),
    }
    mod_name, cls_name = mapping[strategy_id]
    cls = getattr(importlib.import_module(f"src.engine.strategies.{mod_name}"), cls_name)
    s = cls(StrategyConfig(strategy_id=strategy_id, name=strategy_id, weight=0.2,
                           params=dict(extra)))
    s.state.total_investment = budget
    return s


def _msgs(caplog, marker: str) -> list[str]:
    return [r.getMessage() for r in caplog.records if marker in r.getMessage()]


def _recs(caplog, marker: str) -> list[logging.LogRecord]:
    return [r for r in caplog.records if marker in r.getMessage()]


ALL_STRATEGY_IDS = (
    "momentum", "volatility_breakout", "long_tail_volatility",
    "bull_flag_breakout", "vcp_breakout", "donchian_swing", "kojiro",
)
NON_TURTLE_IDS = (
    "momentum", "volatility_breakout", "long_tail_volatility",
    "bull_flag_breakout", "vcp_breakout",
)


# ===========================================================================
# F-1 — 현행 FAIL 핵심: 09-04 000500 재현 (설계 랏의 4.23배가 그대로 매수됐다)
# ===========================================================================
@freeze_time("2026-09-04 08:12:03+09:00")
def test_f245_1_ltv_000500_fallback_blocked_to_zero(caplog):
    """LTV 000500 220,000원 1주 = 설계 랏(52,040)의 4.23배 ⇒ 시정 후 **0주**.

    현행 구현은 `_fallback_one_share` 가 1 을 돌려주고 아무도 자르지 않으므로 FAIL.
    `[oversized_fallback]` 은 ρ캡 **앞**에서 그대로 1행 — 의미가 "실제로 산 랏" →
    "사려 했던 랏" 으로 전환된다(§2.5).
    """
    s = _mini()
    with caplog.at_level(logging.INFO):
        qty = s._apply_budget_limit(0, 220_000, "000500")

    assert qty == 0, (
        "1주 폴백이 설계 랏의 4.23배(220,000 > 130,100)인데 그대로 매수됐다 "
        "— cycle245 ρ캡 미적용"
    )
    hits = _msgs(caplog, BLOCKED)
    assert len(hits) == 1, f"{BLOCKED} 1행 기대, 실제 {len(hits)}"
    assert hits[0] == (
        "[ratio_notional_blocked] ticker=000500 strategy=long_tail_volatility "
        "path=fallback price=220000 cap=52040 cutoff=130100 k=2.50 ratio=4.23 "
        "req_qty=1 capped_qty=0 budget=260200 pos_ratio=0.2000"
    )
    assert _recs(caplog, BLOCKED)[0].levelno == logging.INFO
    over = _msgs(caplog, OVERSIZED)
    assert len(over) == 1, "차단된 랏도 `[oversized_fallback]` 1행이 남아야 한다(관측 앞 배치)"
    assert "ratio=4.23" in over[0]
    assert not _msgs(caplog, RSKIP), f"정상 경로인데 {RSKIP} 가 찍혔다"


# ===========================================================================
# F-2 — 경계 (`final × price > cutoff` 가 차단 조건 = 경계 포함 통과)
# ===========================================================================
@freeze_time("2026-09-04 10:00:00+09:00")
@pytest.mark.parametrize("price,expected", [(LTV_CUTOFF, 1), (LTV_CUTOFF + 1, 0)])
def test_f245_2_cutoff_boundary_is_inclusive(price, expected, caplog):
    """130,100 = 통과 / 130,101 = 차단. `>=` 로 구현하면 앞 케이스가 FAIL."""
    s = _mini()
    with caplog.at_level(logging.INFO):
        qty = s._apply_budget_limit(0, price, "000500")
    assert qty == expected
    assert len(_msgs(caplog, BLOCKED)) == (0 if expected else 1)


# ===========================================================================
# F-3 — 09-04 실측 시리즈 (자문 §2.3 차단 표를 그대로 고정)
# ===========================================================================
@freeze_time("2026-09-04 10:00:00+09:00")
@pytest.mark.parametrize("price,expected", [
    (220_000, 0),   # 09-04 000500 LTV — 4.23배 (그날 최대 손실 −11,000)
    (190_300, 0),
    (171_700, 0),   # 08-31 161890 LTV — 3.30배
    (144_800, 0),   # 08-28 010950 LTV — 2.78배. ⚠️ **승리 랏도 차단**된다(비용 봉인)
    (129_100, 1),
    (128_600, 1),
    (109_600, 1),
    (86_900, 1),    # 09-03 042660 LTV — 1.67배 → 통과
    (21_050, 1),
])
def test_f245_3_live_series_matches_consult_table(price, expected):
    s = _mini()
    assert s._apply_budget_limit(0, price, "T") == expected


# ===========================================================================
# F-4 — 주 분기(정상 비중 랏) 무접촉. K_ρ ≥ 1 이면 정의상 걸리지 않는다.
# ===========================================================================
_G_PRICES = (1_000, 5_000, 20_000, 60_000, 250_000, 500_000)
_G_RATIOS = (0.05, 0.10, 0.166, 0.20, 0.25, 0.35, 0.50)
_G_KS = (1.0, 2.5, 20.0)
_G_BUDGETS = (130_000, 260_000, 390_000, 780_000, 5_000_000)


@freeze_time("2026-09-04 10:00:00+09:00")
def test_f245_4a_sized_branch_single_case_untouched(caplog):
    """cap 52,040 짜리 전략도 비중 수량 1주(40,000)는 그대로 통과한다."""
    s = _mini()
    with caplog.at_level(logging.INFO):
        assert s._apply_budget_limit(1, 40_000, "T") == 1
    assert not _msgs(caplog, BLOCKED)


@freeze_time("2026-09-04 10:00:00+09:00")
def test_f245_4b_sized_branch_grid_equals_head_behaviour():
    """결정적 그리드 414 케이스 — 주 분기 결과가 HEAD(= min(qty, 잔여//price))와 동일."""
    checked = 0
    for price in _G_PRICES:
        for ratio in _G_RATIOS:
            for k in _G_KS:
                for budget in _G_BUDGETS:
                    qty = int(budget * ratio) // price
                    if qty <= 0:
                        continue
                    s = _mini(budget=budget, ratio=ratio, k=k)
                    got = s._apply_budget_limit(qty, price, "T")
                    expected = min(qty, budget // price)   # HEAD 산식
                    assert got == expected, (
                        f"주 분기 변조: price={price} ratio={ratio} k={k} "
                        f"budget={budget} → {got} != {expected}"
                    )
                    checked += 1
    assert checked == 414, f"그리드 전제가 바뀌었다 (검사 {checked}건)"


# ===========================================================================
# F-4c — 관문 반환은 **항상 `int`** (뮤테이션 escape M9b 봉인, 라운드 1)
# ===========================================================================
@freeze_time("2026-09-04 10:00:00+09:00")
@pytest.mark.parametrize("budget,ratio,req,price,expected", [
    # ⚠️ **캡이 실제로 바인딩되고 0 이 아닌 값을 돌려주는 조합이 필수**다.
    # 비바인딩 조합은 `_fallback_one_share`/`min()` 이 int 를 그대로 돌려주므로
    # `cutoff = int(k*cap)` 의 정수 절삭을 지워도 통과해 버린다(공허).
    (10_000_000, 0.01, 10, 100_000, 2),     # cap 100,000 · cutoff 250,000 → 축소
    (LTV_BUDGET, LTV_RATIO, 3, 60_000, 2),  # cutoff 130,100 → 2주
    (LTV_BUDGET, LTV_RATIO, 0, 220_000, 0),  # 폴백 차단 경로
    (LTV_BUDGET, LTV_RATIO, 1, 40_000, 1),  # 비바인딩(대조군)
])
def test_f245_4c_gate_return_is_always_int(budget, ratio, req, price, expected):
    """`cutoff = int(k * cap)` 의 정수 절삭을 지우면 **값은 같고 타입만 float** 이 된다.

    `_apply_budget_limit` ~ `order_engine.pending_buys.add` 사이에 `int()` 강제 변환
    지점이 **0** 이고 `api/order.py` 가 `"ORD_QTY": str(quantity)` 로 그대로
    문자열화하므로, 그 뮤테이션은 KIS 주문 바디에 `ORD_QTY="2.0"` 을 태운다.
    값 검사로는 원리적으로 못 잡으므로 **타입을 계약으로 고정**한다.
    """
    s = _mini(budget=budget, ratio=ratio)
    result = s._apply_budget_limit(req, price, "T")
    assert result == expected
    assert type(result) is int, (
        f"관문이 {type(result).__name__} 을 반환했다 — 캡 산술의 정수 절삭이 사라지면 "
        f"KIS 주문 바디에 ORD_QTY='2.0' 이 나간다(M9b)"
    )


# ===========================================================================
# F-5 — 항등식(스코프 계약): 관문을 통과한 **모든** 랏이 ρ 상한 이하
# ===========================================================================
@freeze_time("2026-09-04 10:00:00+09:00")
def test_f245_5_notional_identity_over_all_lots():
    """`final ≥ 1 ⇒ final × price ≤ int(K × int(예산 × ratio))` — 폴백 랏 포함."""
    for price in _G_PRICES:
        for ratio in _G_RATIOS:
            for k in _G_KS:
                for budget in _G_BUDGETS:
                    limit = int(k * int(budget * ratio))
                    sized = int(budget * ratio) // price
                    for req in {0, sized}:
                        s = _mini(budget=budget, ratio=ratio, k=k)
                        final = s._apply_budget_limit(req, price, "T")
                        if final >= 1:
                            assert final * price <= limit, (
                                f"항등식 위반: req={req} price={price} ratio={ratio} "
                                f"k={k} budget={budget} → {final * price} > {limit}"
                            )


@freeze_time("2026-09-04 10:00:00+09:00")
@pytest.mark.parametrize("req,expected", [(10, 2), (3, 2), (2, 2)])
def test_f245_5b_sized_lot_is_capped_too(req, expected):
    """**스코프 계약(§3-7)**: 캡은 폴백 랏뿐 아니라 관문을 지나는 **모든** 랏에 적용된다.

    F-5 의 그리드는 `req ∈ {0, sized}` 만 도는데 `sized` 랏은 K_ρ≥1 이면 정의상
    캡에 안 걸린다(F-4 항등식). 즉 **캡이 실제로 바인딩되는 non-fallback 랏이
    커버리지에 0 건**이었고, 캡을 `via_fallback` 전용으로 좁히는 뮤테이션(M13)이
    표적 스위트를 통째로 통과했다.

    현행 7 전략 호출부는 `qty` 를 `int(예산×ratio)//price` 로 도출하고 터틀도
    `compute_unit_qty_guarded` 가 같은 상한을 강제하므로 **프로덕션 도달은 없다**
    (F-4 무접촉 항등식 유효). 이 테스트가 지키는 것은 장래 회귀 — 새 사이징 경로가
    주 분기에 큰 `qty` 를 넣었을 때 캡이 조용히 비켜서지 않게 한다.
    """
    s = _mini(budget=10_000_000, ratio=0.01)   # cap 100,000 · cutoff 250,000
    assert s._apply_budget_limit(req, 100_000, "T") == expected


@freeze_time("2026-09-04 10:00:00+09:00")
def test_f245_5c_blocked_marker_path_sized_for_sized_lot(caplog):
    """축소(`capped_qty > 0`) 경로의 마커 서식 — `path=sized` 가 폴백과 갈린다."""
    s = _mini(budget=10_000_000, ratio=0.01)
    with caplog.at_level(logging.INFO):
        assert s._apply_budget_limit(10, 100_000, "T") == 2
    hits = _msgs(caplog, BLOCKED)
    assert len(hits) == 1
    assert (
        "path=sized " in hits[0]
        and " req_qty=10 capped_qty=2 " in hits[0]
        and " cutoff=250000 " in hits[0]
    ), hits[0]


# ===========================================================================
# F-6 — 키 부재 = OFF (fail-closed 구현은 P0-1 유령 키 재현 경로)
# ===========================================================================
@freeze_time("2026-09-04 10:00:00+09:00")
def test_f245_6_missing_key_disables_cap(caplog):
    """cycle233/242 픽스처(키 없음)는 **1주 그대로** — 0 이면 FAIL 이 계약이다."""
    s = _mini("kojiro", budget=KJ_BUDGET, ratio=KJ_RATIO, k=None)
    assert "max_lot_ratio_mult" not in s.config.params
    with caplog.at_level(logging.INFO):
        qty = s._apply_budget_limit(0, 405_500, "000815")

    assert qty == 1, (
        "키 부재를 fail-closed(차단)로 구현했다 — 설정이 없을 때 매수를 막는 것은 "
        "P0-1(유령 키 → 전 기간 체결 0) 재현 경로다"
    )
    assert not _msgs(caplog, BLOCKED)
    cfg = _msgs(caplog, RCONFIG)
    assert len(cfg) == 1
    assert " cap=off k=- " in cfg[0], f"키 부재 카나리아 누락: {cfg[0]}"
    assert not _msgs(caplog, RCLAMP), "키 부재는 클램프가 아니다(무발화)"


# ===========================================================================
# F-7 — 터틀 무접촉 (K축이 심사하면 ρ축은 관여하지 않는다 = 상호배타)
# ===========================================================================
@freeze_time("2026-09-04 10:00:00+09:00")
def test_f245_7a_turtle_capped_by_k_axis_has_no_rho_markers(caplog):
    """kojiro 000815 — cycle242 K축이 0 으로 자른다. ρ 마커는 **전무**(final<1)."""
    s = _kj(budget=774_640, position_ratio=0.166, risk_pct=RISK)
    s._candidates = {"000815": {"atr": 13300}}
    with caplog.at_level(logging.INFO):
        qty = s.calc_buy_quantity(405_500, "000815")

    assert qty == 0, "cycle242 결과가 바뀌었다 — cycle245 는 K축 행위를 건드리지 않는다"
    assert len(_msgs(caplog, CAPPED)) == 1, "cycle242 마커가 사라졌다"
    assert not _msgs(caplog, BLOCKED)
    assert not _msgs(caplog, RCONFIG), "final<1 이면 ρ캡은 config 도 찍지 않는다"


@freeze_time("2026-09-04 10:00:00+09:00")
def test_f245_7b_turtle_over_rho_cutoff_is_not_cut(caplog):
    """K축을 통과한 터틀 랏은 ρ 상한(195,150)을 넘어도 **자르지 않는다**.

    donchian B=390,300 · ATR 3,000 ⇒ K축 cap_qty = 1 ≥ final(1) → 통과.
    같은 랏의 명목 300,000 은 ρ 상한의 3.84배지만 결정 ⑦(상호배타)에 따라 불변이다.
    여기서 자르면 kojiro 000815 3.13배·donchian 3.50배 같은 **정상 터틀 랏**이
    ρ 로 잘려 자문 §2.5 의 목적이 뒤집힌다.
    """
    s = _dc()
    s._candidates = {"000815": {
        "prev_close": 300000, "atr": 3000, "ema60": 0, "donchian_high": 0,
    }}
    with caplog.at_level(logging.INFO):
        qty = s.calc_buy_quantity(300_000, "000815")

    assert qty == 1, "K축이 심사한 랏을 ρ축이 잘랐다 (이중 캡 금지 — 결정 ⑦)"
    assert not _msgs(caplog, BLOCKED)
    cfg = _msgs(caplog, RCONFIG)
    assert len(cfg) == 1
    assert " cap=backstop " in cfg[0], f"터틀 모드 카나리아 라벨 오류: {cfg[0]}"
    assert len(_msgs(caplog, OVERSIZED)) == 1, "ρ 초과 관측(cycle233)은 그대로 남는다"


# ===========================================================================
# F-8 — 터틀 백스톱 (K축이 fail-open 한 랏은 ρ축이 받는다)
# ===========================================================================
@freeze_time("2026-09-04 10:00:00+09:00")
@pytest.mark.parametrize("variant", ["no_atr", "no_risk_pct", "not_turtle"])
def test_f245_8_turtle_fail_open_lot_is_backstopped(variant, caplog):
    """양축 무방비 사각을 닫는다 — 결과는 **비터틀 baseline 과 동일**.

    cycle242 F-6c/F-6d 가 `baseline == turtle 주입` 을 단언하므로, ρ캡을
    `sizing_mode != "turtle"` 로 게이팅하면 그 4건이 깨진다(명세 §0 정정 ①).
    """
    baseline = _dc(turtle=False)
    baseline._candidates = {}
    base_qty = baseline.calc_buy_quantity(300_000, "000815")
    assert base_qty == 0, "baseline 전제 — 비터틀 랏은 ρ캡에 잘려 0 이어야 한다"

    if variant == "no_atr":
        s = _dc(turtle=True)
        s._candidates = {}
    elif variant == "no_risk_pct":
        s = _dc(turtle=True, risk_pct=0)
        s._candidates = {"000815": {"atr": 9000}}
    else:
        s = _dc(turtle=False)
        s._candidates = {}

    # ⚠️ `baseline.calc_buy_quantity` 는 `caplog.at_level` **밖**이지만 caplog 핸들러는
    # 테스트 전 구간을 수집한다 — 앞선 테스트가 `src.engine.strategy_base` 로거를
    # INFO 로 올려둔 상태(전체 스위트/`--log-level=INFO`)에서는 baseline 의
    # `[ratio_notional_blocked]` 까지 섞여 `len(hits) == 2` 가 된다. 표적 실행에서만
    # 통과하는 순서 의존 결함이라 캡처 시작 직전에 비운다(cycle240 F-8 동형).
    caplog.clear()
    with caplog.at_level(logging.INFO):
        qty = s.calc_buy_quantity(300_000, "000815")

    assert qty == base_qty == 0, "K축이 심사하지 못한 랏이 무방비로 통과했다"
    hits = _msgs(caplog, BLOCKED)
    assert len(hits) == 1
    assert (
        f"cutoff={DONCHIAN_CUTOFF} " in hits[0]
        and f"cap={DONCHIAN_CAP} " in hits[0]
    ), hits[0]
    if variant != "not_turtle":
        assert len(_msgs(caplog, FSKIP)) == 1, "cycle242 fail-open 마커가 사라졌다"


# ===========================================================================
# F-9 — ticker None (K축이 조용히 off 하는 구간을 ρ축이 받는다)
# ===========================================================================
@freeze_time("2026-09-04 10:00:00+09:00")
def test_f245_9a_ticker_none_still_capped(caplog):
    s = _mini("kojiro", budget=KJ_BUDGET, ratio=KJ_RATIO)
    with caplog.at_level(logging.INFO):
        qty = s._apply_budget_limit(0, 405_500, None)
    assert qty == 0, "ticker 미지정 랏이 캡을 우회했다"
    hits = _msgs(caplog, BLOCKED)
    assert len(hits) == 1
    assert hits[0].startswith("[ratio_notional_blocked] ticker=- "), hits[0]


@freeze_time("2026-09-04 10:00:00+09:00")
def test_f245_9b_turtle_ticker_none_within_cutoff_unchanged(caplog):
    """donchian B=387,320 → cutoff 193,660. 2주 × 38,000 = 76,000 ≤ cutoff → 불변."""
    s = _dc(budget=387_320)
    s._candidates = {}
    with caplog.at_level(logging.INFO):
        qty = s.calc_buy_quantity(38_000)
    assert qty == int(387_320 * 0.20) // 38_000 == 2, "cycle242 F-7 결과가 바뀌었다"
    assert not _msgs(caplog, BLOCKED)


# ===========================================================================
# F-10 — fail-open 전수 (수량 0 이면 FAIL = P0-1 재현 방지 가드)
# ===========================================================================
@freeze_time("2026-09-04 10:00:00+09:00")
@pytest.mark.parametrize("ratio", [0, None, "abc", -0.2])
def test_f245_10a_bad_position_ratio_is_fail_open(ratio, caplog):
    s = _mini(ratio=None) if ratio is None else _mini(ratio=ratio)
    if ratio is None:
        s.config.params["position_ratio"] = None
    with caplog.at_level(logging.INFO):
        qty = s._apply_budget_limit(0, 220_000, "000500")
    assert qty == 1, "position_ratio 결측/무효인데 매수를 막았다 (fail-closed = 계약 위반)"
    hits = _recs(caplog, RSKIP)
    assert len(hits) == 1
    assert hits[0].levelno == logging.WARNING
    assert hits[0].getMessage() == (
        "[ratio_cap_skipped] ticker=000500 strategy=long_tail_volatility "
        "reason=no_ratio qty=1 price=220000 — ρ캡 미적용(현행 수량 유지, fail-open)"
    )


@freeze_time("2026-09-04 10:00:00+09:00")
def test_f245_10b_zero_budget_is_fail_open(caplog):
    """예산 0 은 관문 앞단(`_fallback_one_share` 잔여 검사)에서 이미 0 이 되므로
    헬퍼를 직접 호출해 `no_budget` 분기를 실증한다."""
    s = _mini(budget=0)
    with caplog.at_level(logging.INFO):
        qty = s._apply_ratio_notional_cap(1, 220_000, "000500", via_fallback=True)
    assert qty == 1
    hits = _msgs(caplog, RSKIP)
    assert len(hits) == 1 and "reason=no_budget " in hits[0], hits


@freeze_time("2026-09-04 10:00:00+09:00")
def test_f245_10c_zero_cap_is_fail_open(caplog):
    """`int(예산 × ratio) == 0`(초소액) → 상한 정의 불가 → 현행 수량."""
    s = _mini(budget=100, ratio=0.001)
    with caplog.at_level(logging.INFO):
        qty = s._apply_budget_limit(0, 50, "T")
    assert qty == 1
    hits = _msgs(caplog, RSKIP)
    assert len(hits) == 1 and "reason=no_cap " in hits[0], hits


@freeze_time("2026-09-04 10:00:00+09:00")
def test_f245_10d_governs_probe_error_is_fail_open(caplog, monkeypatch):
    """판정기 **내부** 예외 → `k_axis_probe_error` + 현행 수량 (fail-open 방향)."""
    s = _dc(turtle=True)
    s._candidates = {"000815": {"atr": 3000}}

    def _boom(*a, **k):
        raise RuntimeError("atr resolver down")

    monkeypatch.setattr(s, "_resolve_sizing_atr", _boom)
    with caplog.at_level(logging.INFO):
        qty = s.calc_buy_quantity(300_000, "000815")
    assert qty == 1, "판정 실패가 매수를 막았다 (fail-open 방향 위반)"
    hits = _msgs(caplog, RSKIP)
    assert len(hits) == 1 and "reason=k_axis_probe_error " in hits[0], hits


@freeze_time("2026-09-04 10:00:00+09:00")
def test_f245_10e_cap_exception_is_fail_open(caplog, monkeypatch):
    """캡 산출 예외 → `exception` + 현행 수량 + 예외 전파 0."""
    s = _mini()

    def _boom(*a, **k):
        raise RuntimeError("params down")

    monkeypatch.setattr(s, "_read_max_lot_ratio_mult", _boom)
    with caplog.at_level(logging.INFO):
        qty = s._apply_budget_limit(0, 220_000, "000500")
    assert qty == 1
    hits = _msgs(caplog, RSKIP)
    assert len(hits) == 1 and "reason=exception " in hits[0], hits


@freeze_time("2026-09-04 10:00:00+09:00")
def test_f245_10f_emit_method_failure_never_propagates(caplog, monkeypatch):
    """관측기 **메서드 자체**가 던져도 예외는 관문 밖으로 나가지 않는다.

    ⚠️ 이 경로의 수량은 **캡 이전 값**(fail-open)이다 — 바깥 try 가 잡는 지점이라
    차단이 취소된다. "행위는 cap 밖"(cycle237) 계약이 지키는 것은 **cap 소진**
    (F-12a)과 **로그 자기실패**(F-13a)이고, 이 둘은 emit 내부 try 가 흡수하므로
    차단이 그대로 수행된다. 셋을 한 테스트로 뭉치면 fail-open 방향과 cap 계약이
    서로를 지운다.
    """
    s = _mini()
    monkeypatch.setattr(
        s, "_emit_ratio_notional_blocked",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    try:
        with caplog.at_level(logging.INFO):
            qty = s._apply_budget_limit(0, 220_000, "000500")
    except RuntimeError:
        pytest.fail("관측 예외가 매수 수량 산출로 전파됨")
    assert qty == 1, "예외 경로의 방향은 fail-open(캡 이전 수량)이 계약이다"
    hits = _msgs(caplog, RSKIP)
    assert len(hits) == 1 and "reason=exception " in hits[0], hits


# ===========================================================================
# F-11 — 읽는 쪽 클램프 `[1.0, 20.0]` + 롤백 다이얼
# ===========================================================================
@freeze_time("2026-09-04 10:00:00+09:00")
def test_f245_11a_missing_key_returns_none_without_marker(caplog):
    s = _mini(k=None)
    with caplog.at_level(logging.INFO):
        assert s._read_max_lot_ratio_mult() is None, "키 부재는 None(=OFF)이 계약"
    assert not _msgs(caplog, RCLAMP)


@freeze_time("2026-09-04 10:00:00+09:00")
@pytest.mark.parametrize("raw", [0, -1, 0.99, "abc", None, True, math.inf, math.nan])
def test_f245_11b_invalid_values_clamp_to_default(raw, caplog):
    s = _mini(k=1.0)
    s.config.params["max_lot_ratio_mult"] = raw
    with caplog.at_level(logging.INFO):
        got = s._read_max_lot_ratio_mult()
    assert got == pytest.approx(sb_mod._MAX_LOT_RATIO_MULT_DEFAULT)
    hits = _recs(caplog, RCLAMP)
    assert len(hits) == 1 and hits[0].levelno == logging.WARNING
    assert f"raw={raw!r}" in hits[0].getMessage()


@freeze_time("2026-09-04 10:00:00+09:00")
def test_f245_11c_above_max_clamps_to_max(caplog):
    s = _mini(k=999)
    with caplog.at_level(logging.INFO):
        assert s._read_max_lot_ratio_mult() == pytest.approx(20.0)
    assert len(_msgs(caplog, RCLAMP)) == 1


@freeze_time("2026-09-04 10:00:00+09:00")
@pytest.mark.parametrize("raw", [1.0, 2.5, 20.0])
def test_f245_11d_in_range_values_pass_through(raw, caplog):
    s = _mini(k=raw)
    with caplog.at_level(logging.INFO):
        assert s._read_max_lot_ratio_mult() == pytest.approx(raw)
    assert not _msgs(caplog, RCLAMP), "정상 범위 값에 클램프 마커가 찍혔다"


@freeze_time("2026-09-04 10:00:00+09:00")
def test_f245_11e_rollback_dial_and_tight_dial_behaviour():
    """K=20 = 사실상 현행 복귀 / K=1 = 설계 랏 상한 그 자체."""
    s = _mini("kojiro", budget=KJ_BUDGET, ratio=KJ_RATIO, k=20.0)
    assert s._apply_budget_limit(0, 405_500, "000815") == 1
    s = _mini(k=1.0)
    assert s._apply_budget_limit(0, 129_100, "T") == 0


# ===========================================================================
# F-12 — cap 규약 (1회/키/일 · 인스턴스 격리 · 날짜 자기 리셋) + 행위는 cap 밖
# ===========================================================================
@freeze_time("2026-09-04 10:00:00+09:00")
def test_f245_12a_blocked_marker_once_but_behaviour_every_call(caplog):
    s = _mini()
    with caplog.at_level(logging.INFO):
        first = s._apply_budget_limit(0, 220_000, "000500")
        second = s._apply_budget_limit(0, 220_000, "000500")
        third = s._apply_budget_limit(0, 190_300, "161890")
    assert first == second == third == 0, (
        "cap 소진 후 차단 행위가 사라졌다 — 행위는 cap 밖이 계약(cycle237)"
    )
    hits = _msgs(caplog, BLOCKED)
    assert len(hits) == 2
    assert sum("ticker=000500" in m for m in hits) == 1
    assert sum("ticker=161890" in m for m in hits) == 1


@freeze_time("2026-09-04 10:00:00+09:00")
def test_f245_12b_skipped_keyed_by_ticker_and_reason(caplog):
    s = _mini(ratio=0)
    with caplog.at_level(logging.INFO):
        s._apply_budget_limit(0, 220_000, "000500")
        s._apply_budget_limit(0, 220_000, "000500")
        s._apply_budget_limit(0, 220_000, "161890")
    hits = _msgs(caplog, RSKIP)
    assert len(hits) == 2, f"(ticker,reason) 별 1행 기대, 실제 {len(hits)}"


@freeze_time("2026-09-04 10:00:00+09:00")
def test_f245_12c_config_and_clamped_once_per_strategy_per_day(caplog):
    s = _mini(k=999)
    with caplog.at_level(logging.INFO):
        s._apply_budget_limit(0, 220_000, "000500")
        s._apply_budget_limit(0, 220_000, "161890")
    assert len(_msgs(caplog, RCONFIG)) == 1
    assert len(_msgs(caplog, RCLAMP)) == 1


@freeze_time("2026-09-04 10:00:00+09:00")
def test_f245_12d_instances_are_isolated(caplog):
    a, b = _mini(), _mini()
    with caplog.at_level(logging.INFO):
        a._apply_budget_limit(0, 220_000, "000500")
        b._apply_budget_limit(0, 220_000, "000500")
    assert len(_msgs(caplog, BLOCKED)) == 2


def test_f245_12e_day_key_self_resets(caplog):
    s = _mini()
    with caplog.at_level(logging.INFO):
        with freeze_time("2026-09-04 15:00:00+09:00"):
            s._apply_budget_limit(0, 220_000, "000500")
        with freeze_time("2026-09-05 09:10:00+09:00"):
            s._apply_budget_limit(0, 220_000, "000500")
    assert len(_msgs(caplog, BLOCKED)) == 2, "KST 날짜 경계에서 cap 자기 리셋이 안 됐다"


@freeze_time("2026-09-04 10:00:00+09:00")
def test_f245_12f_cycle242_cap_instance_is_separate(caplog):
    """cycle242 `_lot_cap_logged` 가 같은 키로 소진돼도 cycle245 마커는 발화한다."""
    s = _mini()
    for key in ("blk|000500", "cfg", "clamp", "skip|000500|no_cap"):
        s._lot_cap_logged.mark_emitted(key)
    with caplog.at_level(logging.INFO):
        qty = s._apply_budget_limit(0, 220_000, "000500")
    assert qty == 0
    assert len(_msgs(caplog, BLOCKED)) == 1, "cap 인스턴스를 공유하고 있다(cycle236 계약 위반)"
    assert len(_msgs(caplog, RCONFIG)) == 1


# ===========================================================================
# F-13 — peek → 로그 → mark (로그 자기실패가 그날 관측을 지우지 않는다)
# ===========================================================================
def _raise_on(marker: str, original):
    def _wrapped(fmt, *args, **kwargs):
        if isinstance(fmt, str) and marker in fmt:
            raise RuntimeError(f"logger down for {marker}")
        return original(fmt, *args, **kwargs)
    return _wrapped


@freeze_time("2026-09-04 10:00:00+09:00")
def test_f245_13a_blocked_log_failure_keeps_behaviour_and_retries(caplog, monkeypatch):
    s = _mini()
    monkeypatch.setattr(
        sb_mod.logger, "info", _raise_on(BLOCKED, sb_mod.logger.info),
    )
    with caplog.at_level(logging.INFO):
        first = s._apply_budget_limit(0, 220_000, "000500")
        second = s._apply_budget_limit(0, 220_000, "000500")
    assert first == second == 0, "로그 실패가 차단 행위를 취소시켰다"
    monkeypatch.undo()
    with caplog.at_level(logging.INFO):
        s._apply_budget_limit(0, 220_000, "000500")
    assert len(_msgs(caplog, BLOCKED)) == 1, (
        "로그 실패 시 mark 가 먼저 찍혀 그날 관측이 통째로 사라졌다 (cycle226 D-3)"
    )


@freeze_time("2026-09-04 10:00:00+09:00")
@pytest.mark.parametrize("marker,level", [
    (RSKIP, "warning"), (RCONFIG, "info"), (RCLAMP, "warning"),
])
def test_f245_13b_other_markers_absorb_log_failure(marker, level, caplog, monkeypatch):
    s = _mini(ratio=0, k=999)          # skipped(no_ratio) + config + clamped 동시 경로
    monkeypatch.setattr(
        sb_mod.logger, level, _raise_on(marker, getattr(sb_mod.logger, level)),
    )
    with caplog.at_level(logging.INFO):
        qty = s._apply_budget_limit(0, 220_000, "000500")
    assert qty == 1, "관측 실패가 fail-open 수량을 바꿨다"
    monkeypatch.undo()
    with caplog.at_level(logging.INFO):
        s._apply_budget_limit(0, 220_000, "000500")
    assert len(_msgs(caplog, marker)) == 1, f"{marker}: mark-before-log"


# ===========================================================================
# F-14 — 폴백 헬퍼 반환값 유통 (기존 A-FALLBACK 계약 승계)
# ===========================================================================
@freeze_time("2026-09-04 10:00:00+09:00")
def test_f245_14a_fallback_return_flows_through_when_cap_not_binding():
    s = _mini()
    with patch.object(StrategyBase, "_fallback_one_share", return_value=1) as helper:
        result = s._apply_budget_limit(0, 100_000, "T")
    assert result == 1
    helper.assert_called_once_with(100_000)


@freeze_time("2026-09-04 10:00:00+09:00")
def test_f245_14b_fallback_return_is_capped_when_binding():
    """`_fallback_one_share` 안에 캡을 넣으면(§0 정정 ④) 이 테스트가 patch 로 우회된다."""
    s = _mini()
    with patch.object(StrategyBase, "_fallback_one_share", return_value=42) as helper:
        result = s._apply_budget_limit(0, 100_000_000, "T")
    assert result == 0, "캡이 `_fallback_one_share` 안에 있어 patch 로 우회됐다"
    helper.assert_called_once_with(100_000_000)


# ===========================================================================
# F-15 — DEFAULT_PARAMS · DB 병합 · 롤백 다이얼 전제
# ===========================================================================
@pytest.mark.parametrize("strategy_id", ALL_STRATEGY_IDS)
def test_f245_15a_default_params_carry_the_key(strategy_id):
    s = _real(strategy_id, budget=1_000_000)
    assert "max_lot_ratio_mult" in s.config.params, (
        f"{strategy_id} DEFAULT_PARAMS 에 키가 없다 — DB 병합 관용구가 "
        "`if key in params` 라 키 없는 전략은 롤백 다이얼조차 못 돌린다"
    )
    assert s.config.params["max_lot_ratio_mult"] == pytest.approx(
        sb_mod._MAX_LOT_RATIO_MULT_DEFAULT
    )
    assert sb_mod._MAX_LOT_RATIO_MULT_DEFAULT == pytest.approx(2.5)


@freeze_time("2026-09-04 10:00:00+09:00")
def test_f245_15b_db_merge_idiom_applies_rollback_dial():
    """scheduler `_load_strategy_config` 병합 관용구(`if key in params`) 재현."""
    s = _real("long_tail_volatility", budget=LTV_BUDGET)
    for key, val in {"max_lot_ratio_mult": 20.0}.items():
        if key in s.config.params:
            s.config.params[key] = val
    assert s._read_max_lot_ratio_mult() == pytest.approx(20.0)


@pytest.mark.parametrize("strategy_id,cap_notional", [
    ("long_tail_volatility", 52_040),
    ("volatility_breakout", 136_606),
    ("bull_flag_breakout", 97_576),
    ("vcp_breakout", 52_040),
    ("momentum", 32_525),
])
def test_f245_15c_max_dial_exceeds_price_filter(strategy_id, cap_notional):
    """K=20 컷오프가 5 비터틀 전략 전부 `price_filter_max`(500,000) 초과 = 현행 복귀."""
    assert int(sb_mod._MAX_LOT_RATIO_MULT_MAX * cap_notional) > 500_000


def test_f245_15d_module_constants():
    assert sb_mod._MAX_LOT_RATIO_MULT_MIN == pytest.approx(1.0), (
        "하한 1.0 은 주 분기 무접촉의 수학적 전제 — 1 미만이면 정상 비중 랏까지 잘려 전면 무매매"
    )
    assert sb_mod._MAX_LOT_RATIO_MULT_MAX == pytest.approx(20.0)
    assert (
        sb_mod._MAX_LOT_RATIO_MULT_MIN
        <= sb_mod._MAX_LOT_RATIO_MULT_DEFAULT
        <= sb_mod._MAX_LOT_RATIO_MULT_MAX
    )


# ===========================================================================
# F-16 — `[ratio_cap_config]` 카나리아 (cutoff_price 필수 · final<1 미발화)
# ===========================================================================
@freeze_time("2026-09-04 10:00:00+09:00")
def test_f245_16a_config_marker_exact_for_non_turtle(caplog):
    s = _mini()
    with caplog.at_level(logging.INFO):
        s._apply_budget_limit(0, 220_000, "000500")
    hits = _msgs(caplog, RCONFIG)
    assert len(hits) == 1
    assert hits[0] == (
        "[ratio_cap_config] strategy=long_tail_volatility sizing_mode=None cap=on "
        "k=2.50 budget=260200 pos_ratio=0.2000 cap_notional=52040 cutoff_price=130100"
    ), "운영자 아침 판독 근거(cutoff_price)가 빠졌거나 서식이 다르다"


@freeze_time("2026-09-04 10:00:00+09:00")
def test_f245_16b_config_marker_backstop_label(caplog):
    s = _dc(turtle=True)
    s._candidates = {"000815": {"prev_close": 300000, "atr": 3000,
                                "ema60": 0, "donchian_high": 0}}
    with caplog.at_level(logging.INFO):
        s.calc_buy_quantity(300_000, "000815")
    hits = _msgs(caplog, RCONFIG)
    assert len(hits) == 1
    assert hits[0] == (
        "[ratio_cap_config] strategy=donchian_swing sizing_mode=turtle cap=backstop "
        "k=2.50 budget=390300 pos_ratio=0.2000 cap_notional=78060 cutoff_price=195150"
    )


@freeze_time("2026-09-04 10:00:00+09:00")
def test_f245_16c_config_silent_when_no_lot(caplog):
    """`final < 1` / `price ≤ 0` 은 캡 판단 자체가 없으므로 카나리아도 무발화."""
    s = _mini()
    with caplog.at_level(logging.INFO):
        assert s._apply_budget_limit(0, 0, "000500") == 0
        assert s._apply_budget_limit(0, 900_000, "000500") == 0   # 잔여 부족 → 폴백 0
    assert not _msgs(caplog, RCONFIG)


@freeze_time("2026-09-04 10:00:00+09:00")
def test_f245_16d_config_marker_refires_when_k_changes(caplog):
    """**공식 롤백(§8)을 확인할 채널** — `cfg` 가 단일 키면 이 재발화가 사라진다.

    `PUT /api/strategies/{id}/params` 는 `if key in params: params[key] = value` 로
    in-memory 를 **즉시** 덮어쓴다. 단일 키였을 때는 그날 첫 랏이 cap 을 소진해
    변경 후 새 k 를 확인할 마커가 0 개였다(차단이 사라지면 blocked 도 안 나온다).
    """
    s = _mini()
    with caplog.at_level(logging.INFO):
        s._apply_budget_limit(0, 220_000, "000500")          # k=2.5 · cutoff 130,100
        s.config.params["max_lot_ratio_mult"] = 20.0         # 롤백 다이얼 PUT
        assert s._apply_budget_limit(0, 220_000, "000500") == 1
    hits = _msgs(caplog, RCONFIG)
    assert len(hits) == 2, f"K 변경이 카나리아에 안 남았다: {hits}"
    assert " k=2.50 " in hits[0] and " cutoff_price=130100" in hits[0]
    assert " k=20.00 " in hits[1] and " cutoff_price=1040800" in hits[1]


@freeze_time("2026-09-04 10:00:00+09:00")
def test_f245_16e_config_marker_refires_when_budget_changes(caplog):
    """`weight` PUT → `allocate_funds` 재분배로 `cutoff_price` 가 바뀌는 경로."""
    s = _mini()
    with caplog.at_level(logging.INFO):
        s._apply_budget_limit(0, 220_000, "000500")
        s.state.total_investment = 520_400                   # 예산 2배 재분배
        s._apply_budget_limit(0, 220_000, "000500")
    hits = _msgs(caplog, RCONFIG)
    assert len(hits) == 2, "cutoff_price 가 stale 인 채 하루가 지난다"
    assert " cutoff_price=260200" in hits[1]


@freeze_time("2026-09-04 10:00:00+09:00")
def test_f245_16f_clamped_marker_refires_per_raw_value(caplog):
    """`clamp` 단일 키면 같은 날 **두 번째 범위밖 값이 무음 클램프**된다.

    09:30 에 `0.5`(→2.5) 를 넣고 13:00 에 `25.0`(→20.0, 비활성 의도) 을 넣으면
    로그엔 `raw=0.5` 만 남아 운영자가 현재 K 를 2.50 으로 오판한다(실제 20.0).
    """
    s = _mini(k=0.5)
    with caplog.at_level(logging.INFO):
        s._apply_budget_limit(0, 220_000, "000500")
        s.config.params["max_lot_ratio_mult"] = 25.0
        s._apply_budget_limit(0, 220_000, "000500")
    hits = _msgs(caplog, RCLAMP)
    assert len(hits) == 2, f"두 번째 범위밖 값이 무음 클램프됐다: {hits}"
    assert "raw=0.5 clamped_to=2.50" in hits[0]
    assert "raw=25.0 clamped_to=20.00" in hits[1]
    # 같은 값 반복은 여전히 1행 (폭주 없음)
    caplog.clear()
    with caplog.at_level(logging.INFO):
        s._apply_budget_limit(0, 220_000, "161890")
    assert not _msgs(caplog, RCLAMP)


# ===========================================================================
# F-17 — `[oversized_fallback]` 의미 전환 + R7 자기검증 불변식
# ===========================================================================
@freeze_time("2026-09-04 10:00:00+09:00")
def test_f245_17a_oversized_format_is_byte_stable(caplog):
    """cycle233 형 검사(`"3.10" in message`) 호환 — 서식은 손대지 않는다."""
    s = _mini("kojiro", budget=KJ_BUDGET, ratio=KJ_RATIO, k=None)
    with caplog.at_level(logging.INFO):
        s._apply_budget_limit(0, 405_500, "000815")
    hits = _msgs(caplog, OVERSIZED)
    assert len(hits) == 1
    assert "3.10" in hits[0]
    assert "1주 폴백이 notional 상한 초과 (관측 전용)" in hits[0]
    assert hits[0].startswith(
        "[oversized_fallback] ticker=000815 strategy=kojiro qty=1 notional=405500 "
        "cap=130995 ratio=3.10"
    )


@freeze_time("2026-09-04 10:00:00+09:00")
def test_f245_17b_r7_invariant_survivors_never_exceed_k(caplog):
    """R7 — ρ캡이 켜진 전략에서 **살아남은** 랏의 `[oversized_fallback] ratio` ≤ K_ρ."""
    with caplog.at_level(logging.INFO):
        for price in (60_000, 86_900, 109_600, 129_100, 130_100, 144_800, 220_000):
            s = _mini()
            final = s._apply_budget_limit(0, price, f"T{price}")
            if final < 1:
                continue
            hits = _msgs(caplog, OVERSIZED)
            for msg in [m for m in hits if f"ticker=T{price} " in m]:
                ratio = float(msg.split("ratio=")[1].split(" ")[0])
                assert ratio <= K_RHO + 1e-9, (
                    f"살아남은 랏이 ρ 상한을 넘었다: {msg}"
                )


# ===========================================================================
# F-18 — cycle242 마커 생존 (배치를 앞으로 옮기는 뮤테이션 검출)
# ===========================================================================
@freeze_time("2026-09-04 10:00:00+09:00")
@pytest.mark.parametrize("maker", ["donchian", "kojiro"])
def test_f245_18_cycle242_markers_still_emitted(maker, caplog):
    if maker == "donchian":
        s = _dc(turtle=True, budget=774_640)
        s._candidates = {"000815": {"atr": 13300}}
    else:
        s = _kj(budget=774_640, position_ratio=0.166, risk_pct=RISK)
        s._candidates = {"000815": {"atr": 13300}}
    with caplog.at_level(logging.INFO):
        s.calc_buy_quantity(405_500, "000815")
    assert len(_msgs(caplog, FCONFIG)) == 1, "cycle242 카나리아가 사라졌다"
    assert len(_msgs(caplog, CAPPED)) == 1, (
        "ρ캡을 `_apply_lot_units_cap` **앞**에 두면 final<1 조기탈출로 "
        "cycle242 마커가 통째로 사라진다"
    )


# ===========================================================================
# F-19 — 기존 회귀 (7 전략 정상 경로 · 관문 시그니처)
# ===========================================================================
@freeze_time("2026-09-04 10:00:00+09:00")
@pytest.mark.parametrize("strategy_id", ALL_STRATEGY_IDS)
def test_f245_19a_normal_sized_lot_unchanged_for_all_strategies(strategy_id):
    s = _real(strategy_id, budget=1_000_000)
    ratio = s.config.params["position_ratio"]
    expected = int(1_000_000 * ratio) // 10_000
    assert expected > 0, "테스트 전제: 비중 수량 > 0"
    assert s.calc_buy_quantity(10_000, "005930") == expected


def test_f245_19b_gate_signature_unchanged():
    sig = inspect.signature(StrategyBase._apply_budget_limit)
    assert list(sig.parameters) == ["self", "qty", "current_price", "ticker"], (
        "관문 시그니처가 바뀌었다 — A-FALLBACK/A-GATE 계약 위반"
    )


# ===========================================================================
# F-20 — order_engine 오귀인 근거 (읽기만, 8영역 무접촉)
# ===========================================================================
def test_f245_20_low_funds_cooldown_regression_exists():
    """수량 0 폭주 차단은 이미 `order_engine` 이 900s 로 한다 — ρ캡에 래치 신설 금지."""
    guard = _ROOT / "tests" / "integration" / "test_buy_block_low_funds.py"
    assert guard.exists(), "저수량 cooldown 회귀 가드가 사라졌다"
    text = guard.read_text(encoding="utf-8")
    assert "block_low_funds" in text
    engine = (_ROOT / "src" / "engine" / "order_engine.py").read_text(encoding="utf-8")
    assert "LOW_FUNDS_COOLDOWN = 900.0" in engine, (
        "cooldown 상수가 바뀌었다 — cycle245 차단 랏의 재시도 폭주 귀인이 달라진다"
    )


# ===========================================================================
# F-21 — 롤백 경로의 **반영 시점** (라운드 2 확증 #2/#3)
#
# §8 롤백 문안이 "DB UPDATE **또는** PUT — 코드 재배포 불필요" 로 두 수단을 동등하게
# 적는데 전파 의미가 다르다. 이 그룹은 그 차이를 코드 사실로 못박는다.
#   - SQL   : `_load_strategy_config` 이 `_config_loaded` 프로세스당 1회 가드라
#             **백엔드 재시작에서만** 반영된다 (07:55 `_boot` 재호출은 no-op).
#   - PUT   : in-memory 를 즉시 덮으므로 **즉시** 반영 — 단 **키가 이미 있을 때만**.
#             배포 **전**(구코드 DEFAULT_PARAMS 에 키 부재)에는 값을 조용히 버리고
#             `success=true` 를 돌려주며, `save_params` 가 params JSONB 를 통째로
#             덮어써 **먼저 넣어둔 SQL 값까지 지운다**.
# 두 사실이 §7.1(배포 전 필수 조치)의 경로 선택을 결정한다.
# ===========================================================================
async def test_f245_21a_sql_rollback_takes_effect_only_on_restart():
    """SQL 롤백은 재시작 전까지 안 먹는다 — 07:55 `_boot` 재호출은 DB 를 읽지도 않는다.

    cycle232 D6(보유 포지션이 있으면 09:00~15:30 재시작 금지)과 겹치면 **장중에는
    SQL 롤백을 쓸 수 없다**. R1/R2 는 장중 트리거이므로 그때의 실효 수단은 PUT 뿐이다.
    이 단언이 깨지면(= 재로드 경로가 생기면) §7.1·§8·§9 문안을 함께 갱신하라.
    """
    from src.engine.scheduler import TradingScheduler

    sched = TradingScheduler()
    ltv = sched.registry.get("long_tail_volatility")
    assert ltv is not None
    assert ltv.config.params["max_lot_ratio_mult"] == pytest.approx(K_RHO)

    clean = {"long_tail_volatility": {"enabled": True, "weight": 0.01, "params": {}}}
    first = AsyncMock(return_value=clean)
    with patch("src.db.strategy_config.load_all", first):
        await sched._load_strategy_config()
    assert first.await_count == 1, "첫 로드는 DB 를 읽는다 (테스트 전제)"

    # 운영자가 장중 SQL 로 20.0 주입 → 다음 07:55 `_boot` 이 같은 프로세스에서 재호출
    rolled = {"long_tail_volatility": {
        "enabled": True, "weight": 0.01, "params": {"max_lot_ratio_mult": 20.0},
    }}
    second = AsyncMock(return_value=rolled)
    with patch("src.db.strategy_config.load_all", second):
        await sched._load_strategy_config()

    assert second.await_count == 0, (
        "`_config_loaded` 가드가 사라졌다 — SQL 롤백의 반영 시점이 바뀌었으니 "
        "§7.1·§8·§9 의 '재시작 필요' 문안을 갱신하라"
    )
    assert ltv.config.params["max_lot_ratio_mult"] == pytest.approx(K_RHO), (
        "07:55 _boot 재호출이 SQL 값을 반영했다 (현행 계약과 다름)"
    )


def test_f245_21a2_config_loaded_has_no_reset_or_extra_reload_path():
    """`_config_loaded` 리셋 지점 0 · `_load_strategy_config` 호출자 = 부팅 2곳뿐.

    "SQL 은 재시작에서만" 이 참인 **구조적 근거**다. 재로드 경로가 새로 생기면
    이 가드가 붉어지고, 그때 문서(§7.1·§8·§9)를 함께 고치게 된다.
    """
    src_dir = _ROOT / "src"
    reset_sites: list[str] = []
    callers: set[str] = set()
    for path in sorted(src_dir.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        rel = str(path.relative_to(_ROOT))
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("self._config_loaded = False"):
                reset_sites.append(rel)
            if "_load_strategy_config(" in stripped and not stripped.startswith("async def"):
                callers.add(rel)

    assert reset_sites == ["src/engine/scheduler.py"], (
        f"`_config_loaded = False` 대입 위치가 바뀌었다: {reset_sites} "
        "(현행은 __init__ 1곳 — 리셋이 생기면 롤백 문안 갱신)"
    )
    assert callers == {"src/main.py", "src/engine/boot_manager.py"}, (
        f"`_load_strategy_config` 호출자가 바뀌었다: {sorted(callers)}"
    )


async def test_f245_21b_put_before_deploy_drops_key_and_overwrites_db(monkeypatch):
    """배포 **전** PUT 은 무음 실패다 — 키를 버리고 `success=true` + DB 덮어쓰기.

    §7.1 이 배포 전 조치로 SQL 을 지시하고 PUT 을 대안으로 병기했으나, 구코드의
    in-memory `params` 에는 `max_lot_ratio_mult` 가 없어 라우트의
    `if key in strategy.config.params` 필터가 값을 조용히 버린다. 그 뒤
    `save_params(…, strategy.config.params)` 가 params JSONB 를 **통째로** 덮으므로
    (`save` 의 `params = EXCLUDED.params`) 먼저 넣어둔 SQL 값까지 사라진다.
    """
    from types import SimpleNamespace

    from src.routes import strategies as routes_mod

    pre_deploy = _real("long_tail_volatility", budget=LTV_BUDGET)
    del pre_deploy.config.params["max_lot_ratio_mult"]      # 구코드 DEFAULT_PARAMS 재현

    monkeypatch.setattr(routes_mod, "trading_scheduler", SimpleNamespace(
        registry=SimpleNamespace(
            get=lambda sid: pre_deploy,
            get_strategies_status=lambda: {},
        ),
    ))
    saved: dict = {}

    async def _fake_save(strategy_id, params):
        saved["strategy_id"] = strategy_id
        saved["params"] = dict(params)

    monkeypatch.setattr("src.db.strategy_config.save_params", _fake_save)

    resp = await routes_mod.update_params(
        "long_tail_volatility",
        routes_mod.ParamsRequest(params={"max_lot_ratio_mult": 20.0}),
    )

    assert resp.success is True, "라우트가 미지 키를 거부하지 않는다 (현행 계약)"
    assert "max_lot_ratio_mult" not in pre_deploy.config.params, (
        "미지 키가 in-memory 에 들어갔다 — 라우트 필터가 바뀌었으니 §7.1 갱신"
    )
    assert "max_lot_ratio_mult" not in saved["params"], (
        "배포 전 PUT 이 DB 에 키를 남긴다면 §7.1 의 'SQL 단일 경로' 지시를 완화해도 된다"
    )


async def test_f245_21b2_put_after_deploy_applies_immediately(monkeypatch):
    """배포 **후** PUT 은 in-memory 를 즉시 덮는다 = 장중 실효 롤백 수단."""
    from types import SimpleNamespace

    from src.routes import strategies as routes_mod

    live = _real("long_tail_volatility", budget=LTV_BUDGET)
    assert live.config.params["max_lot_ratio_mult"] == pytest.approx(K_RHO)

    monkeypatch.setattr(routes_mod, "trading_scheduler", SimpleNamespace(
        registry=SimpleNamespace(
            get=lambda sid: live,
            get_strategies_status=lambda: {},
        ),
    ))
    saved: dict = {}

    async def _fake_save(strategy_id, params):
        saved["params"] = dict(params)

    monkeypatch.setattr("src.db.strategy_config.save_params", _fake_save)

    resp = await routes_mod.update_params(
        "long_tail_volatility",
        routes_mod.ParamsRequest(params={"max_lot_ratio_mult": 20.0}),
    )

    assert resp.success is True
    assert live.config.params["max_lot_ratio_mult"] == pytest.approx(20.0)
    assert saved["params"]["max_lot_ratio_mult"] == pytest.approx(20.0)
    assert live._read_max_lot_ratio_mult() == pytest.approx(20.0), (
        "PUT 직후 다음 랏부터 즉시 K=20 (재시작 불필요)"
    )
