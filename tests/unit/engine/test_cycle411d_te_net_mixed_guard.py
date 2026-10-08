"""cycle411 3차 LOW 보완 Red — `te_metrics.compute_te_rr` 페어별 폴백이 세전·세후를
섞지 않게 (항목 4의 te_metrics 부분, 메인 세션 작업 지시 3차 검증 LOW).

배경 — `_net_rate`/`_net_pl` 은 페어에 `net_profit_rate`/`net_profit_loss` 가 없으면
그 페어만 세전 값으로 폴백한다(사용자 결정 Q2, 구 입력 전체가 net 필드를 안 가진 경우를
위한 설계 — `test_q4_pairs_without_net_fields_fall_back_to_gross` 가 그 경우를 지킨다).
그런데 `overlay_pairs` 가 루프 중간에 예외로 끝나면(코드 결함) **일부 페어만** net 필드를
갖고 나머지는 없는 상태로 `costs_available=False` 와 함께 `compute_te_rr` 에 들어올 수
있다 — 이때 `realized_net_sum_krw`/`fee_sum`/`tax_sum` 합산이 net 값과 세전 폴백 값을
한 합계 안에서 섞는다. 한 페어라도 비용 계산이 안 됐으면(costs_available=False 이거나,
population 안에 net 필드가 있는 페어와 없는 페어가 **섞여** 있으면) 그 전략의 세후 칸
(realized_net_sum_krw·fee_sum·tax_sum) 전체를 None 으로 둔다.

기존 보존 대상(수정 금지로 취급) —
`tests/unit/engine/test_cycle411_te_net.py::test_q3_realized_sums_gross_net_fee_tax`
(전부 net 필드 있음) · `test_q4_pairs_without_net_fields_fall_back_to_gross`(전부 없음) ·
`test_cycle411c_cost_overlay_engine_fixes2.py::test_b4_...`(costs_available=False).
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timedelta, timezone

import pytest

from src.engine.te_metrics import compute_te_rr

pytestmark = pytest.mark.unit

KST = timezone(timedelta(hours=9))
NOW = datetime(2026, 10, 8, 20, 0, tzinfo=KST)


def _pair(i, rate, pl, *, net_rate=None, net_pl=None, fee=None, tax=None):
    p = {
        "status": "closed", "sell_date": "2026-10-01", "profit_rate": rate, "profit_loss": pl,
        "strategy": "momentum", "pair_key": f"momentum:005930:O{i}",
    }
    if net_rate is not None:
        p.update({"net_profit_rate": net_rate, "net_profit_loss": net_pl, "fee": fee, "tax": tax})
    return p


def _mixed_population(n=20):
    """반은 net 필드가 있고 반은 없다 — `overlay_pairs` 가 루프 중간에 멈춘 모양."""
    with_net = [
        _pair(i, 0.1, 700, net_rate=-0.38, net_pl=-2660, fee=1960, tax=1400)
        for i in range(n // 2)
    ]
    without_net = [_pair(i, 0.1, 700) for i in range(n // 2, n)]
    return with_net + without_net


def test_l4_mixed_net_population_nulls_net_sums_even_when_costs_available_true():
    """일부 페어만 net 필드를 가진 혼재 상태면(costs_available=True 라도) 세후 합을 None 으로."""
    d = asdict(compute_te_rr(_mixed_population(), now=NOW, strategy_id="momentum",
                              costs_available=True))
    for k in ("realized_net_sum_krw", "fee_sum", "tax_sum"):
        assert d[k] is None, (k, d[k])


def test_l4b_all_net_present_still_computes_normally():
    """가드 — 전부 net 필드가 있으면(혼재 아님) 기존처럼 정상 계산한다."""
    pairs = [_pair(i, 0.1, 700, net_rate=-0.38, net_pl=-2660, fee=1960, tax=1400)
             for i in range(20)]
    d = asdict(compute_te_rr(pairs, now=NOW, strategy_id="momentum", costs_available=True))
    assert d["realized_net_sum_krw"] == pytest.approx(-2660 * 20)
    assert d["fee_sum"] == pytest.approx(1960 * 20)
    assert d["tax_sum"] == pytest.approx(1400 * 20)


def test_l4c_none_have_net_still_falls_back_to_gross():
    """가드 — 전부 net 필드가 없으면(기존 q4) 혼재가 아니라 균일 폴백 — None 으로 바뀌지 않는다."""
    pairs = [_pair(i, 1.0, 1000) for i in range(20)]
    d = asdict(compute_te_rr(pairs, now=NOW, strategy_id="momentum", costs_available=True))
    assert d["realized_net_sum_krw"] == pytest.approx(d["realized_sum_krw"])
