"""프리마켓 매도 거부 msg1 의 이중 매칭 — 분류 우선순위 계약 고정 (2026-08-06).

라이브 실측 msg1 = "장운영시간이 아닙니다.([프리마켓] 시장가 매매 불가 시간)"
은 `_MARKET_CLOSED_KEYWORDS`("장운영시간") 와
`_MARKET_ORDER_DISALLOWED_KEYWORDS`("시장가 매매 불가") 에 **동시 매칭**된다.
종전 docstring 의 "상호 배타" 는 이 입력에서 거짓이었다.

`execute_sell` 은 market_closed 를 먼저 검사하므로 이중 매칭 = 보류(포지션
보존 + 다음 09:00 TTL). **이것이 의도된 계약이다** — 프리장은 왜곡 시세라
지정가 폴백 즉시 매도보다 09:00 KRX 보류가 안전하다(사용자 결정). 누군가
"폴백이 안 타네?" 라며 검사 순서를 뒤집으면 프리장 왜곡가 매도가 부활한다.
"""

from __future__ import annotations

import inspect

import pytest

from src.api.balance import (
    is_insufficient_cash,
    is_insufficient_quantity,
    is_market_closed_rejection,
    is_market_order_disallowed,
)
from src.api.base import KisApiError

pytestmark = pytest.mark.unit

_PRE_MARKET_MSG = "장운영시간이 아닙니다.([프리마켓] 시장가 매매 불가 시간)"


def _err(msg1: str) -> KisApiError:
    try:
        return KisApiError(msg_cd="APBK0918", msg1=msg1)
    except TypeError:
        e = KisApiError.__new__(KisApiError)
        e.msg_cd, e.msg1 = "APBK0918", msg1
        return e


def test_pre_market_msg_double_matches_both_classifiers():
    """이중 매칭 실재를 계약으로 고정 — 어느 한쪽 키워드를 빼서 '해결'하면 안 된다.

    market_closed 쪽을 빼면 보류가 사라져 프리장 지정가 매도가 부활하고,
    disallowed 쪽을 빼면 애프터마켓(APBK3013) 폴백 인식이 흔들린다.
    """
    e = _err(_PRE_MARKET_MSG)
    assert is_market_closed_rejection(e) is True
    assert is_market_order_disallowed(e) is True
    # 자금/수량 부족 2종과는 상호 배타 유지
    assert is_insufficient_cash(e) is False
    assert is_insufficient_quantity(e) is False


def test_execute_sell_checks_market_closed_before_disallowed():
    """검사 순서 = market_closed 먼저. 이중 매칭 입력이 '보류' 로 떨어지는 근거."""
    from src.engine.order_engine import OrderEngine

    src = inspect.getsource(OrderEngine.execute_sell)
    i_closed = src.find("is_market_closed_rejection")
    i_disallowed = src.find("is_market_order_disallowed")
    assert 0 < i_closed < i_disallowed, (
        "순서 반전 금지 — 프리장 이중 매칭이 지정가 폴백으로 흘러 왜곡가 매도 부활"
    )


def test_after_market_msg_is_not_double_matched():
    """애프터마켓 APBK3013 은 market_closed 미매칭 → 지정가 폴백이 정상 경로."""
    e = _err("[애프터마켓]지정가 및 최유리/최우선지정가 주문만 가능합니다.")
    assert is_market_closed_rejection(e) is False
    assert is_market_order_disallowed(e) is True
