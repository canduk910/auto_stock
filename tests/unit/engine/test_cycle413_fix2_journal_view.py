"""cycle413 보완 2차 Red — 거래일지 카드 조립 leaf `src/engine/journal_view.py::build_card` 결함 회귀.

판정 원문 = scratchpad `c413/fix/{screens,trader}` 재검증 N1(공통 결함) — 체결 조회 실패(`fills=None`)
경로에서 비용 칸이 「모름 ≠ 0」 원칙을 어긴다.

| # | 결함 → 계약 |
|---|---|
| N1 | 체결 조회 실패(`fills=None`)면 그 페어의 청산분(수량·비용)을 전혀 모른다. 그런데 `_build_costs` 는
|    | 진입 수수료만으로 `paid_total` 을 내 부분합을 전체인 척 보여주고, 보유 중 카드의 `expected_exit` 는
|    | `entry_qty=0 → total_buy_qty=1` 폴백 때문에 `ratio_remaining` 이 진짜 비율이 아니라 보유수량 그
|    | 자체가 되어 음수로 왜곡된다(screens·trader 재현 스크립트 실측: expected_exit ≈ −17,877). 수정 =
|    | fills_failed 면 paid_total·expected_exit 를 lookup_failed 로 낸다(0 도 왜곡값도 내지 않는다) |
"""

from __future__ import annotations

import importlib

import pytest

from tests.unit.engine.test_cycle413_journal_view import _a_kw, _a_pair, _c_kw, _c_pair

pytestmark = pytest.mark.unit


@pytest.fixture(scope="module")
def jv():
    return importlib.import_module("src.engine.journal_view")


def test_n1_fills_failed_paid_total_is_lookup_failed_not_partial_sum(jv):
    """진입 수수료만으로 「합계」를 내지 않는다 — 청산분을 몰라 부분합이 전체인 척하면 안 된다."""
    card = jv.build_card(_c_pair(), **_c_kw(fills=None))
    co = card["costs"]
    assert co["paid_total"] is None, (
        f"체결 조회 실패인데 paid_total={co['paid_total']!r} — 진입 수수료만으로 합계를 냈다"
        "(청산분을 몰라 부분합을 전체인 척 보여준다)"
    )


def test_n1_fills_failed_expected_exit_is_lookup_failed_not_distorted(jv):
    """entry_qty=0 폴백으로 ratio_remaining 이 왜곡돼 예상 청산비용이 음수로 나오면 안 된다."""
    card = jv.build_card(_c_pair(), **_c_kw(fills=None))
    co = card["costs"]
    assert co["expected_exit"] is None, (
        f"체결 조회 실패인데 expected_exit={co['expected_exit']!r} — "
        "entry_qty=0 폴백이 ratio_remaining 을 왜곡시켰다(음수 비용 위험)"
    )
    assert co["expected_exit_na"] == "lookup_failed"


def test_n1_fills_ok_expected_exit_unaffected(jv):
    """fills 가 정상이면(기존 F10 경로) 예상 청산비용 계산은 그대로 동작한다 — 회귀 없음."""
    card = jv.build_card(_c_pair(), **_c_kw())
    co = card["costs"]
    assert co["expected_exit"] is not None
    assert co["expected_exit"] > 0, "실측 전제(C_COSTS 양수 수수료·세금) 하에서는 음수가 나올 수 없다"


def test_n2_fills_failed_entry_reason_na_is_lookup_failed_not_unknown(jv):
    """screens 재검증 N2 — order_no 를 몰라 일지 행을 찾아보지도 못한 것과, 찾아봤는데
    없는 것(「unknown」)은 다르다. fills_failed 면 전자이므로 lookup_failed 로 낸다."""
    card = jv.build_card(_a_pair(), **_a_kw(fills=None))
    r = card["entry"]["reason"]
    assert r["na"] == "lookup_failed", f"na={r['na']!r} — 기록이 없는 것처럼(unknown) 보이면 안 된다"


def test_n2_fills_ok_entry_reason_na_unaffected(jv):
    """fills 가 정상이면(order_no 를 안다) 기존 `_record_na` 판정 그대로 — 회귀 없음."""
    card = jv.build_card(_a_pair(), **_a_kw())
    assert card["entry"]["reason"]["na"] is None
    assert card["entry"]["reason"]["code"] == "ENTRY"
