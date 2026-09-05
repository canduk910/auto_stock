"""cycle254 Red — 터틀 랏에도 ρ축 상한을 `min` 으로 후심사 (결정 ⑦ 개정).

명세: `_workspace/specs/cycle254_ratio_cap_min_composition.md` §3
자문: `_workspace/domain_consult/cycle254_turtle_fallback_rho_exposure.md` §3·§6·§9

## 고칠 결함 (한 문장)

cycle245 의 결정 ⑦("두 캡은 상호배타")은 `_apply_ratio_notional_cap` 안에서
`if governs: return final` 조기탈출로 구현됐다. 그래서 **K축(`max_lot_units`)이
심사한 랏은 명목에 천장이 없다** — K축은 유닛 축(`floor(K×B×r÷ATR)`)이라 저ATR
종목일수록 상한이 커지고, 1주 폴백 랏(`P > B×ρ`)이 `ATR ≤ K×B×r` 이면 그대로
통과한다. 구조적 천장은 donchian **390,300원(= 그 전략 예산 전부, 순자산 15.0%)** ·
kojiro **500,000원(19.2%)** 이고, 이는 `position_ratio 0.20 × max_positions 5` 라는
분산 계약을 한 종목이 통째로 먹는 것을 허용한다(자문 §2.1·§2.5).

## 시정 (사용자 결정 2026-09-05 "D3 권고 B")

조기탈출을 **판정 실패 fail-open 한 갈래로만** 좁힌다.

    if governs and gov_reason == "probe_error":
        self._emit_ratio_cap_skipped(ticker, "k_axis_probe_error", final, current_price)
        return final

`_lot_units_cap_governs` **호출은 남는다**(G-245-4 가 호출 존재를 핀 + `probe_error`
fail-open 이 F-10d 계약). 그 아래 `cap<=0` 스킵·`cap_qty = cutoff // price`·
`final <= cap_qty` 통과·`_emit_ratio_notional_blocked`·`return cap_qty` 는 byte 동일.

## 이 파일이 봉인하는 것 (명세 §3)

- F-9a  donchian 1주 폴백 300,000원(ρ 상한 195,150 의 3.84배) → **0주** + BLOCKED 1행.
- F-9b  사이즈드 터틀 랏 무접촉 — `compute_unit_qty_guarded` 의 notional 상한
        (`min(qty, int(B×ρ)//P)`) 때문에 명목이 항등적으로 `≤ B×ρ ≤ K_ρ×B×ρ` 다.
- F-9c  격자 차분 == `(HEAD수량 == 1) ∧ (P > int(K_ρ × int(B×ρ)))` 정확 일치 +
        **수량 증가 0**. 자문 §3.3 의 "차이 122 = 전부 1주 폴백·전부 축소" 를 회귀로 고정.
- F-9d  `probe_error` fail-open 유지(F-10d 계약을 이 사이클 파일에도 1건 고정).
- F-9e  K축(cycle242) 결과 불변 — `[fallback_notional_capped]` 발화 조건·수량 byte 동일.
- F-9f  경계 — `final × P == cutoff` 통과 / `+1원` 차단(폴백 경로).
- F-9g  kojiro 1주 폴백 400,000원(cutoff 323,952) → 0 + BLOCKED 1행.

## HEAD 경로 재현 방식 (F-9b/F-9c)

`_head_early_exit(s)` 컨텍스트가 인스턴스 메서드 `_apply_ratio_notional_cap` 을
"governs 면 `final` 그대로 반환" 하는 래퍼로 덮어 **결정 ⑦ 의 조기탈출을 복원**한다.
HEAD 에서는 진짜 구현이 이미 같은 일을 하므로 래퍼가 no-op 이고(= 차분 0),
Green 이후에는 이 래퍼만이 옛 행위를 재현한다. 비교 대상은 **수량뿐**이다 —
래퍼는 `[ratio_cap_config]` 카나리아를 찍지 않으므로 마커 수는 비교하지 않는다.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager

import pytest
from freezegun import freeze_time

# 픽스처 재사용 — cycle239→233 · cycle250→233/239 선례(테스트 모듈 간 헬퍼 import).
from tests.unit.engine.test_cycle245_ratio_notional_cap import (
    BLOCKED,
    CAPPED,
    K_RHO,
    OVERSIZED,
    RCONFIG,
    RSKIP,
    _dc,
    _kj,
    _msgs,
    _recs,
)

pytestmark = pytest.mark.unit

# ── donchian 라이브 기준선 (순자산 2,602,038 × weight 0.15) ──
DC_BUDGET = 390_300
DC_RATIO = 0.20
DC_CAP = 78_060             # int(390,300 × 0.20)
DC_CUTOFF = 195_150         # int(2.5 × 78,060)

# ── kojiro 라이브 기준선 (순자산 × weight 0.30, ρ 는 08-08 지혈값 0.166) ──
KJ_BUDGET = 780_611
KJ_RATIO = 0.166
KJ_CAP = 129_581            # int(780,611 × 0.166)
KJ_CUTOFF = 323_952         # int(2.5 × 129,581)


# ---------------------------------------------------------------------------
# HEAD(결정 ⑦) 조기탈출 복원 — 격자 차분의 대조군
# ---------------------------------------------------------------------------
@contextmanager
def _head_early_exit(strategy):
    """`if governs: return final` (cycle245 결정 ⑦) 을 인스턴스에 되돌린다.

    Green 이후에도 이 래퍼가 옛 행위를 재현하므로 차분 격자가 성립한다.
    `probe_error` 갈래는 HEAD 도 같은 위치에서 fail-open 하므로 동일하게 재현한다.
    """
    real = strategy._apply_ratio_notional_cap

    def _head(final, current_price, ticker, *, via_fallback):
        if final >= 1 and current_price > 0:
            governs, gov_reason = strategy._lot_units_cap_governs(ticker)
            if governs:
                if gov_reason == "probe_error":
                    strategy._emit_ratio_cap_skipped(
                        ticker, "k_axis_probe_error", final, current_price,
                    )
                return final
        return real(final, current_price, ticker, via_fallback=via_fallback)

    strategy._apply_ratio_notional_cap = _head
    try:
        yield
    finally:
        del strategy._apply_ratio_notional_cap


def _quote(strategy, price: int, ticker: str, atr: float | None):
    """`_candidates` 를 세팅하고 매수 수량을 뽑는다 (atr=None → 배관 끊김)."""
    strategy._candidates = {} if atr is None else {ticker: {"atr": float(atr)}}
    return strategy.calc_buy_quantity(price, ticker)


# ===========================================================================
# F-9a — 핵심 Red: K축을 통과한 터틀 1주 폴백 랏이 ρ 상한의 3.84배로 나간다
# ===========================================================================
@freeze_time("2026-09-05 10:00:00+09:00")
def test_c254_f9a_turtle_fallback_over_rho_cutoff_is_blocked(caplog):
    """donchian B=390,300 · ATR 3,000 · P 300,000 ⇒ **0주** + BLOCKED 1행.

    경로: 터틀 사이징 0(유닛 0.65 < 1) → PR 낙하 0(78,060 // 300,000) →
    1주 폴백 → K축 cap_qty=1 통과(ATR 3,000 ≤ K×B×r = 3,903) → ρ축이 받는다.
    그 1주의 명목 300,000 은 전략 예산 390,300 의 77% 이고 ρ 상한의 3.84배다.

    HEAD 는 `if governs: return final` 로 이 랏을 그대로 통과시킨다(FAIL).
    """
    s = _dc()
    caplog.clear()
    with caplog.at_level(logging.INFO):
        qty = _quote(s, 300_000, "000815", 3_000)

    assert qty == 0, (
        "K축이 심사한 1주 폴백 랏(명목 300,000 = ρ 상한 195,150 의 3.84배)이 "
        "그대로 통과했다 — cycle254 min 합성 미적용"
    )
    hits = _msgs(caplog, BLOCKED)
    assert len(hits) == 1, f"{BLOCKED} 1행 기대, 실제 {len(hits)}: {hits}"
    assert hits[0] == (
        "[ratio_notional_blocked] ticker=000815 strategy=donchian_swing "
        "path=fallback price=300000 cap=78060 cutoff=195150 k=2.50 ratio=3.84 "
        "req_qty=1 capped_qty=0 budget=390300 pos_ratio=0.2000"
    )
    assert _recs(caplog, BLOCKED)[0].levelno == logging.INFO
    assert len(_msgs(caplog, OVERSIZED)) == 1, (
        "차단된 랏도 `[oversized_fallback]` 1행이 남아야 한다 (관측이 ρ캡 **앞**)"
    )
    cfg = _msgs(caplog, RCONFIG)
    assert len(cfg) == 1 and " cap=on " in cfg[0], (
        f"터틀 행 라벨이 `on` 으로 통일되지 않았다: {cfg}"
    )
    assert not _msgs(caplog, RSKIP), f"정상 차단 경로인데 {RSKIP} 가 찍혔다"
    assert not _msgs(caplog, CAPPED), "K축은 이 랏을 자르지 않는다(cap_qty=1 ≥ final=1)"


# ===========================================================================
# F-9b — 사이즈드 터틀 랏 무접촉 (항등식: 명목 ≤ B×ρ ≤ K_ρ×B×ρ)
# ===========================================================================
_F9B_PRICES = (5_000, 10_000, 20_000, 50_000)
_F9B_ATR_PCTS = (1.0, 2.0, 4.0, 8.0)
_F9B_BUDGETS = (390_300, 1_000_000)


@freeze_time("2026-09-05 10:00:00+09:00")
@pytest.mark.parametrize("maker,ratio", [(_dc, DC_RATIO), (_kj, KJ_RATIO)])
def test_c254_f9b_sized_turtle_lots_are_untouched(maker, ratio):
    """`compute_unit_qty_guarded` 가 만든 랏은 `min` 합성 전후 **수량 동일**.

    근거는 관측이 아니라 항등식이다 — 그 함수가 `min(qty, int(B×ρ)//P)` 를
    **무조건** 적용하므로 명목이 `B×ρ` 이하이고, `K_ρ ≥ 1` 이라 `cutoff ≥ B×ρ` 다.
    PR 낙하 랏 `int(B×ρ)//P` 도 정의상 같다.
    """
    sized_cells = 0
    for budget in _F9B_BUDGETS:
        cap = int(budget * ratio)
        cutoff = int(K_RHO * cap)
        s = maker(budget=budget, position_ratio=ratio)
        for price in _F9B_PRICES:
            for atr_pct in _F9B_ATR_PCTS:
                atr = price * atr_pct / 100.0
                with _head_early_exit(s):
                    head_qty = _quote(s, price, "000815", atr)
                new_qty = _quote(s, price, "000815", atr)
                cell = (budget, price, atr_pct)
                assert new_qty == head_qty, (
                    f"사이즈드 터틀 랏이 ρ캡에 잘렸다 {cell}: "
                    f"HEAD={head_qty} → cycle254={new_qty}"
                )
                assert new_qty * price <= cutoff, (
                    f"항등식 위반 {cell}: 명목 {new_qty * price} > cutoff {cutoff} "
                    "— compute_unit_qty_guarded 의 notional 상한이 깨졌다"
                )
                if new_qty >= 2:
                    sized_cells += 1
    assert sized_cells >= 8, (
        f"수량 ≥2 인 사이즈드 랏이 {sized_cells} 개뿐 — 격자가 폴백만 재고 있어 "
        "이 봉인은 공허하다(탐지기 무효)"
    )


# ===========================================================================
# F-9c — 격자 차분 회귀 (차이 집합 정확 일치 + 수량 증가 0)
# ===========================================================================
_F9C_BUDGETS = (390_300, 780_611, 1_000_000)
_F9C_PRICES = (
    5_000, 20_000, 50_000, 100_000, 130_000, 195_150,
    195_151, 250_000, 300_000, 323_952, 400_000, 500_000,
)
# None = `_candidates` 결측(ATR 배관 끊김) ⇒ `governs=False` = 백스톱 경로.
# 0.5% = 변동성 floor 미달 ⇒ 터틀 사이징 0 → PR/폴백 낙하(ATR 은 해석 가능).
_F9C_ATR_PCTS = (None, 0.5, 1.0, 2.0, 3.0, 5.0, 8.0)


@freeze_time("2026-09-05 10:00:00+09:00")
def test_c254_f9c_grid_diff_is_exactly_the_fallback_over_cutoff_set():
    """자문 §3.3(1,728 조합 / 차이 122 / 불일치 0)을 결정적 격자로 회귀 고정.

    예측식 = `(HEAD수량 == 1) ∧ (P > int(K_ρ × int(B × ρ)))`.
    사이즈드·PR 낙하 랏은 명목이 정의상 cutoff 이하라 이 식에 걸릴 수 없고,
    `governs=False` 셀은 HEAD 도 이미 ρ캡을 통과시켰으므로 차이가 없다.
    """
    grid: list[tuple] = []
    head: dict[tuple, int] = {}
    new: dict[tuple, int] = {}
    cutoffs: dict[tuple, int] = {}

    for label, maker, ratio in (
        ("donchian_swing", _dc, DC_RATIO),
        ("kojiro", _kj, KJ_RATIO),
    ):
        for budget in _F9C_BUDGETS:
            s = maker(budget=budget, position_ratio=ratio)
            cutoff = int(K_RHO * int(budget * ratio))
            for price in _F9C_PRICES:
                for atr_pct in _F9C_ATR_PCTS:
                    atr = None if atr_pct is None else price * atr_pct / 100.0
                    cell = (label, budget, price, atr_pct)
                    with _head_early_exit(s):
                        head[cell] = _quote(s, price, "000815", atr)
                    new[cell] = _quote(s, price, "000815", atr)
                    cutoffs[cell] = cutoff
                    grid.append(cell)

    assert len(grid) >= 500, f"격자 {len(grid)} 조합 — 명세 §3 은 최소 500 을 요구한다"

    actual_diff = {c for c in grid if head[c] != new[c]}
    expected_diff = {
        c for c in grid if head[c] == 1 and c[2] > cutoffs[c]
    }
    assert actual_diff == expected_diff, (
        "차분 집합이 예측식과 다르다 — "
        f"예측만: {sorted(expected_diff - actual_diff)[:5]} / "
        f"실제만: {sorted(actual_diff - expected_diff)[:5]}"
    )
    assert actual_diff, (
        "격자에 차이가 한 건도 없다 — 1주 폴백 셀이 없어 탐지기가 무효다"
    )
    increased = [c for c in grid if new[c] > head[c]]
    assert not increased, f"`min` 합성이 수량을 늘렸다: {increased[:5]}"
    assert all(new[c] == 0 for c in actual_diff), (
        "1주는 쪼갤 수 없다 — 차단은 축소가 아니라 0주(미매수)여야 한다"
    )


# ===========================================================================
# F-9d — `probe_error` fail-open 은 남는다 (F-10d 계약을 이 파일에도 고정)
# ===========================================================================
@freeze_time("2026-09-05 10:00:00+09:00")
def test_c254_f9d_probe_error_still_fails_open(caplog, monkeypatch):
    """판정기 **내부** 예외 → 수량 불변(1) + `[ratio_cap_skipped] reason=k_axis_probe_error`.

    조기탈출을 **블록째** 지우면 이 경로가 사라진다(자문 §3.2 ⚠️). fail-closed 로
    뒤집으면(`!=`) 판정 실패 랏이 차단돼 P0-1 유령 키 재현 방향이 된다.
    """
    s = _dc()
    s._candidates = {"000815": {"atr": 3_000.0}}

    def _boom(*a, **k):
        raise RuntimeError("atr resolver down")

    monkeypatch.setattr(s, "_resolve_sizing_atr", _boom)
    caplog.clear()
    with caplog.at_level(logging.INFO):
        qty = s.calc_buy_quantity(300_000, "000815")

    assert qty == 1, "판정 실패가 매수를 막았다 (fail-open 방향 위반)"
    hits = _msgs(caplog, RSKIP)
    assert len(hits) == 1 and "reason=k_axis_probe_error " in hits[0], hits
    assert _recs(caplog, RSKIP)[0].levelno == logging.WARNING
    assert not _msgs(caplog, BLOCKED), "probe_error 랏을 차단했다 (fail-closed)"


# ===========================================================================
# F-9e — K축(cycle242) 결과 불변 (`[fallback_notional_capped]` byte 동일)
# ===========================================================================
@freeze_time("2026-09-05 10:00:00+09:00")
@pytest.mark.parametrize("price,atr,expected_qty,expected_msg", [
    # (a) PR 낙하 3주 → K축 1주. 그 1주의 명목 20,000 ≤ cutoff 195,150 ⇒ ρ 무접촉.
    pytest.param(
        20_000, 3_000, 1,
        "[fallback_notional_capped] ticker=000815 strategy=donchian_swing path=sized "
        "price=20000 atr=3000 unit_qty=0.650 k=2.00 req_qty=3 capped_qty=1 "
        "units_before=4.61 units_after=1.54 budget=390300 risk_pct=0.0050",
        id="k_axis_cuts_3_to_1",
    ),
    # (b) PR 낙하 3주 → K축 0주(미매수). `final<1` 이라 ρ캡은 마커도 안 찍는다.
    pytest.param(
        20_000, 5_000, 0,
        "[fallback_notional_capped] ticker=000815 strategy=donchian_swing path=sized "
        "price=20000 atr=5000 unit_qty=0.390 k=2.00 req_qty=3 capped_qty=0 "
        "units_before=7.69 units_after=0.00 budget=390300 risk_pct=0.0050",
        id="k_axis_cuts_3_to_0",
    ),
])
def test_c254_f9e_k_axis_result_is_byte_identical(price, atr, expected_qty,
                                                  expected_msg, caplog):
    """cycle254 는 K축 코드·수식·마커를 건드리지 않는다.

    `[fallback_notional_capped]` 건수가 변하면 K축을 접촉한 것 = 즉시 롤백
    (명세 §6 D+1 서명 4).
    """
    s = _dc()
    caplog.clear()
    with caplog.at_level(logging.INFO):
        qty = _quote(s, price, "000815", atr)

    assert qty == expected_qty
    hits = _msgs(caplog, CAPPED)
    assert len(hits) == 1, f"{CAPPED} 1행 기대, 실제 {len(hits)}: {hits}"
    assert hits[0] == expected_msg


@freeze_time("2026-09-05 10:00:00+09:00")
def test_c254_f9e_kojiro_k_axis_zero_lot_has_no_rho_markers(caplog):
    """kojiro 000815(cycle242 픽스처) — K축이 0 으로 자르면 ρ 마커는 **전무**.

    `final < 1` 조기탈출이 ρ캡의 첫 줄이라 `[ratio_cap_config]` 카나리아도 안 찍힌다
    (cycle245 F-16c 계약). cycle254 가 이 순서를 건드리면 여기서 붉어진다.
    """
    s = _kj(budget=774_640, position_ratio=0.166)
    caplog.clear()
    with caplog.at_level(logging.INFO):
        qty = _quote(s, 405_500, "000815", 13_300)

    assert qty == 0, "cycle242 결과가 바뀌었다 — cycle254 는 K축 행위를 건드리지 않는다"
    hits = _msgs(caplog, CAPPED)
    assert len(hits) == 1 and " path=fallback " in hits[0], hits
    assert " req_qty=1 capped_qty=0 " in hits[0], hits
    assert not _msgs(caplog, BLOCKED)
    assert not _msgs(caplog, RCONFIG), "final<1 이면 ρ캡은 config 도 찍지 않는다"


# ===========================================================================
# F-9f — 경계 (`final × P == cutoff` 통과 / `+1원` 차단, 폴백 경로)
# ===========================================================================
@freeze_time("2026-09-05 10:00:00+09:00")
@pytest.mark.parametrize("price,expected", [
    (DC_CUTOFF, 1),         # 195,150 × 1 == cutoff → 경계 포함 통과
    (DC_CUTOFF + 1, 0),     # 195,151 → 차단
])
def test_c254_f9f_turtle_fallback_cutoff_boundary_is_inclusive(price, expected, caplog):
    """`final <= cap_qty` 를 `<` 로 뒤집는 뮤테이션은 앞 케이스에서 잡힌다.

    두 케이스 모두 터틀 1주 폴백(K축 cap_qty=1 통과)이라 cycle254 의 새 경로를
    정확히 밟는다 — HEAD 는 뒤 케이스를 1 로 통과시킨다.
    """
    s = _dc()
    caplog.clear()
    with caplog.at_level(logging.INFO):
        qty = _quote(s, price, "000815", 3_000)

    assert qty == expected, f"price={price} 경계 판정 오류 (cutoff={DC_CUTOFF})"
    assert len(_msgs(caplog, BLOCKED)) == (0 if expected else 1)


# ===========================================================================
# F-9g — kojiro 1주 폴백 (cutoff 323,952)
# ===========================================================================
@freeze_time("2026-09-05 10:00:00+09:00")
def test_c254_f9g_kojiro_fallback_over_cutoff_is_blocked(caplog):
    """kojiro B=780,611 · ρ=0.166 · ATR 3,000 · P 400,000 ⇒ **0주** + BLOCKED 1행.

    ATR 0.75%(변동성 floor 미달) → 터틀 사이징 0 → PR 낙하 0 → 1주 폴백 →
    K축 cap_qty=2 통과 → ρ축 cutoff 323,952 // 400,000 = 0 → 차단.
    잔여 노출 "kojiro 3.86배"(= `price_filter_max` 500,000 천장)를 닫는 표본이다.
    """
    s = _kj(budget=KJ_BUDGET, position_ratio=KJ_RATIO)
    caplog.clear()
    with caplog.at_level(logging.INFO):
        qty = _quote(s, 400_000, "000815", 3_000)

    assert qty == 0, (
        "kojiro 1주 폴백 400,000원(ρ 상한 129,581 의 3.09배)이 통과했다"
    )
    hits = _msgs(caplog, BLOCKED)
    assert len(hits) == 1, f"{BLOCKED} 1행 기대, 실제 {len(hits)}: {hits}"
    assert hits[0] == (
        "[ratio_notional_blocked] ticker=000815 strategy=kojiro path=fallback "
        "price=400000 cap=129581 cutoff=323952 k=2.50 ratio=3.09 "
        "req_qty=1 capped_qty=0 budget=780611 pos_ratio=0.1660"
    )
    cfg = _msgs(caplog, RCONFIG)
    assert len(cfg) == 1 and " cutoff_price=323952" in cfg[0], (
        f"운영자 아침 판독 근거(cutoff_price)가 명세 §6 서명 2 와 다르다: {cfg}"
    )
    assert " cap=on " in cfg[0], f"터틀 행 라벨이 `on` 으로 통일되지 않았다: {cfg[0]}"
