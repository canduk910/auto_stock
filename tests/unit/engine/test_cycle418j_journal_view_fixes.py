"""cycle418-J Red — 거래일지 화면 사소한 결함 4건(backend 몫) 회귀.

원문 = 메인 세션 scratchpad `c418/journal_verdict.md` 「새 결함 (모두 하)」 A·B·D + 「워크리스트
후속」 1(#5 남은 몫)·8(BFB 「전량 익절」 문구와 already_partial 불일치). 결함 C(띄어쓰기)·A 의
프론트 몫은 frontend vitest 가 담당한다(`History.journal.fix3.cycle418j.test.tsx`).

| # | 결함 → 계약 |
|---|---|
| #5 남은 몫 | exit line 에 `stop_kind` 를 싣는다(신호의 `stop_kind` 그대로) — 화면이 hard_pct 근사를 보일 수 있게 |
| B | 체결 조회 실패(`fills=None`)면 카드에 `exits_na="lookup_failed"` 를 싣는다(exits=[] 와 구분) |
| 8 | BFB 측정 목표 도달(`TAKE_PROFIT`) 청산 뒤 보유가 남으면(`status="open"`) 「부분 익절」,
|   | 전량(`status="closed"`) 이면 기존처럼 「전량 익절」 |
| D | 매수 비용 일부가 비용 맵에 없으면(`entry_fee=None`, F10) `expected_exit` 를 `fee_total` 로만
|   | 추정해 채우지 않는다 — `None`(`expected_exit_na="pending"`) 그대로 |

이 파일과 `test_cycle413_journal_view.py`/`test_cycle413_fix1_journal_view.py` 의 헬퍼가 갈리면
이 파일이 정본이다.
"""

from __future__ import annotations

import importlib
from datetime import date

import pytest

from tests.unit.engine.test_cycle413_journal_view import (
    C_COSTS,
    C_S1,
    _a_kw,
    _a_pair,
    _c_kw,
    _c_pair,
    _exit,
    _fill,
    _kw,
    _order,
    _pair_from,
)

pytestmark = pytest.mark.unit


@pytest.fixture(scope="module")
def jv():
    return importlib.import_module("src.engine.journal_view")


# ════════════════════════════════════════════════════════════════════════════
# #5 남은 몫 — exit line 이 stop_kind 를 싣는다
# ════════════════════════════════════════════════════════════════════════════
def test_5_exit_line_carries_stop_kind_effective(jv):
    x = _exit(jv, "vcp_breakout", code="TRAILING_STOP", eff=60000, signal={"stop_kind": "effective"})
    assert x["stop_kind"] == "effective"


def test_5_exit_line_carries_stop_kind_hard_pct(jv):
    x = _exit(jv, "momentum", code="TRAILING_STOP", eff=9500, signal={"stop_kind": "hard_pct"})
    assert x["stop_kind"] == "hard_pct"
    # 값 자체는 지우지 않는다(값은 그대로, 근사 표시는 화면 몫 — cycle413 보완 1차 F5 와 같은 전제).
    assert x["effective_line"] == 9500 and x["fired_line"] is None


def test_5_exit_line_stop_kind_is_none_when_orders_failed(jv):
    card = jv.build_card(_a_pair(), **_a_kw(orders=None))
    assert card["exits"][0]["stop_kind"] is None


# ════════════════════════════════════════════════════════════════════════════
# B — 체결 조회 실패면 카드에 exits_na="lookup_failed"
# ════════════════════════════════════════════════════════════════════════════
def test_b_exits_na_is_lookup_failed_when_fills_failed(jv):
    card = jv.build_card(_a_pair(), **_a_kw(fills=None))
    assert card["exits"] == []
    assert card["exits_na"] == "lookup_failed", "체결 조회 실패를 exits=[] 로만 내 「청산 없음」 과 구분이 안 된다"


def test_b_exits_na_is_none_when_fills_ok(jv):
    card = jv.build_card(_a_pair(), **_a_kw())
    assert card["exits"]
    assert card["exits_na"] is None


def test_b_exits_na_is_none_for_open_card_without_any_sell(jv):
    """가드 — 매도가 실제로 없는(아직 안 팔린) 보유 카드는 exits_na 가 서지 않는다."""
    card = jv.build_card(_c_pair(), **_c_kw())
    assert card["exits_na"] is None


# ════════════════════════════════════════════════════════════════════════════
# 8 — BFB 측정 목표 도달 문구는 보유 축으로 전량/부분을 가른다
# ════════════════════════════════════════════════════════════════════════════
def test_8_bfb_take_profit_closed_position_says_full(jv):
    """가드 — 전량 매도(기존 cycle413 scenario A)는 문구가 바뀌지 않는다."""
    x = _exit(jv, "bull_flag_breakout", code="TAKE_PROFIT",
              signal={"phrase": "bfb_measured_target", "current_price": 13460, "target": 13450}, eff=12350)
    assert x["reason"]["text"] == "측정 목표 13,450 도달 — 전량 익절 (현재가 13,460)"


def test_8_bfb_take_profit_open_position_says_partial(jv):
    buy_id, sell_id = "b18b18b1-0000-4000-8000-000000000001", "b18b18b1-0000-4000-8000-000000000002"
    fills = [
        _fill(buy_id, "BUY", "2026-10-05T09:12:03", 12350, 40, order_no="B1", order_price=12340),
        _fill(sell_id, "SELL", "2026-10-08T14:31:20", 13450, 20, order_no="S1", order_price=13450, pl=22000),
    ]
    row = _order(date(2026, 10, 8), "S1", "SELL", "bull_flag_breakout", "247540", reason_code="TAKE_PROFIT",
                 eff=12350,
                 signal={"signal_name": "TAKE_PROFIT", "phrase": "bfb_measured_target",
                         "current_price": 13460, "target": 13450})
    pair = _pair_from(fills, "bull_flag_breakout", "247540", "에코프로비엠")
    assert pair["status"] == "open", "이 테스트 전제(보유 잔량) 가 깨졌다"
    card = jv.build_card(pair, **_kw(pair, fills, orders=[row]))
    x = card["exits"][0]
    assert x["reason"]["text"] == "측정 목표 13,450 도달 — 부분 익절 (현재가 13,460)"


# ════════════════════════════════════════════════════════════════════════════
# D — entry_fee 를 모르면 expected_exit 를 fee_total 로만 때려 맞추지 않는다
# ════════════════════════════════════════════════════════════════════════════
def test_d_expected_exit_stays_pending_when_entry_fee_unknown(jv):
    """D — cycle413 보완 2차 N1 가드(`and costs_block["entry_fee"] is not None`)의 회귀 테스트.

    이 조건을 되돌리면(지우면) `entry_fee=None` 을 0 으로 쳐서 fee_total 전체를 「남은 비율」
    추정에 써 `expected_exit` 가 숫자로 나온다 — 이 테스트가 그걸 잡는다.
    """
    costs = {C_S1: dict(C_COSTS[C_S1])}  # 매수 두 건(B1·B2) 비용 모름 → entry_fee=None
    card = jv.build_card(_c_pair(), **_c_kw(costs=costs))
    co = card["costs"]
    assert co["entry_fee"] is None
    assert co["fee_total"] is not None and co["tax_total"] is not None, "이 전제가 깨지면 가드 의미가 없다"
    assert co["expected_exit"] is None, "모르는 entry_fee 를 0 으로 섞어 expected_exit 를 계산했다"
    assert co["expected_exit_na"] == "pending"
