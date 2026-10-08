"""cycle411 3차 LOW 보완 Red — `cost_overlay.py` 경고 중복·dedupe 키 결함 (항목 8).

계약 정본 = 메인 세션 작업 지시(3차 검증 LOW #8).

| # | 계약 |
|---|---|
| L8a | 체결이 하나도 없는 (trad_dt, pdno) 정산 행에 세금이 잡히면 경고는 **한 줄**만 남는다
       (`[cost_overlay_unmatched_cost]`) — 짝 없음과 매도세 미배분이 같은 사실을 가리킬 때
       `[cost_overlay_tax_unallocated]` 를 중복으로 더 내지 않는다. |
| L8b | 경고 dedupe 키에서 「오늘 날짜」 를 뺀다 — `(kind, trad_dt, pdno)` 당 **프로세스 수명**
       동안 한 번만(날짜가 바뀌어도 다시 경고하지 않는다). `_reset_cache_for_tests()` 로만 풀린다. |

F5b/F5c/F6a/F6c(짝 없는 정산 행 단독 · 정상 행 무경고 · 같은 날 1회) 는 그대로 보존한다 —
`test_cycle411c_cost_overlay_engine_fixes2.py` 의 해당 테스트가 이미 지킨다. `test_f6b_...`
(「다음 날 다시 경고」)는 이 사이클이 뒤집는 대상이라 그 파일에서 함께 갈아 끼운다.
"""

from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal

from freezegun import freeze_time

from src.engine import cost_overlay

D2 = date(2026, 10, 7)
RATES = {"fee_rate": 0.00142, "tax_rate": 0.00199, "source": "default"}
DAY1 = "2026-10-07T03:00:00Z"  # 2026-10-07 12:00 KST
DAY2 = "2026-10-08T03:00:00Z"  # 2026-10-08 12:00 KST


def _cost(pdno, trad_dt, **over) -> dict:
    row = {
        "trad_dt": trad_dt, "pdno": pdno, "prdt_name": "",
        "buy_qty": Decimal(0), "buy_amt": Decimal(0), "sll_qty": Decimal(0),
        "sll_amt": Decimal(0), "rlzt_pfls": Decimal(0), "fee": Decimal(0),
        "tl_tax": Decimal(0), "row_count": 1, "raw": [],
    }
    row.update({k: Decimal(str(v)) for k, v in over.items()})
    return row


def _warns(caplog, prefix: str) -> list[logging.LogRecord]:
    return [r for r in caplog.records
            if r.levelno >= logging.WARNING and r.getMessage().startswith(prefix)]


def _all_cost_overlay_warns(caplog) -> list[logging.LogRecord]:
    return [r for r in caplog.records
            if r.levelno >= logging.WARNING and r.getMessage().startswith("[cost_overlay_")]


def test_l8a_tax_row_with_no_fill_at_all_warns_exactly_once(caplog):
    """짝 체결이 전혀 없는 정산 행에 세금이 잡히면 경고가 한 줄만 남는다 (중복 제거)."""
    trades: list[dict] = []  # 이 (trad_dt, pdno) 에 체결이 하나도 없다
    rows = [_cost("300010", D2, sll_amt=500_000, fee=70, tl_tax=995)]
    with caplog.at_level(logging.DEBUG):
        cost_overlay.trade_costs(rows, trades, RATES)
    warns = _all_cost_overlay_warns(caplog)
    assert len(warns) == 1, [r.getMessage() for r in warns]
    assert warns[0].getMessage().startswith("[cost_overlay_unmatched_cost]"), warns[0].getMessage()
    assert not _warns(caplog, "[cost_overlay_tax_unallocated] ")


def test_l8b_warning_dedupe_survives_kst_day_change(caplog):
    """L8b — dedupe 키에 날짜가 없다: 다음 KST 날짜에도 같은 키는 다시 경고하지 않는다."""
    cost_overlay._reset_cache_for_tests()
    trades = [{
        "id": 1, "trade_date": D2, "ticker": "300020", "ticker_name": "가나",
        "trade_type": "BUY", "strategy": "kojiro", "price": Decimal("100000"),
        "quantity": 3, "profit_loss": Decimal(0), "order_price": None, "status": "COMPLETED",
    }]
    rows = [_cost("300020", D2, buy_amt=300_000, fee=40, tl_tax=50)]
    try:
        with freeze_time(DAY1) as fr, caplog.at_level(logging.DEBUG):
            cost_overlay.trade_costs(rows, trades, RATES)
            assert len(_warns(caplog, "[cost_overlay_tax_unallocated] ")) == 1
            fr.move_to(DAY2)
            cost_overlay.trade_costs(rows, trades, RATES)
        # 날짜가 바뀌었어도 두 번째 경고가 늘지 않는다 — 프로세스 수명 동안 1회.
        assert len(_warns(caplog, "[cost_overlay_tax_unallocated] ")) == 1
    finally:
        cost_overlay._reset_cache_for_tests()


def test_l8c_reset_hook_allows_warning_again(caplog):
    """`_reset_cache_for_tests()` 는 여전히 dedupe 를 비운다(테스트 격리 용도로 보존)."""
    trades = [{
        "id": 1, "trade_date": D2, "ticker": "300030", "ticker_name": "가나",
        "trade_type": "BUY", "strategy": "kojiro", "price": Decimal("100000"),
        "quantity": 3, "profit_loss": Decimal(0), "order_price": None, "status": "COMPLETED",
    }]
    rows = [_cost("300030", D2, buy_amt=300_000, fee=40, tl_tax=50)]
    with caplog.at_level(logging.DEBUG):
        cost_overlay.trade_costs(rows, trades, RATES)
        cost_overlay._reset_cache_for_tests()
        cost_overlay.trade_costs(rows, trades, RATES)
    assert len(_warns(caplog, "[cost_overlay_tax_unallocated] ")) == 2
