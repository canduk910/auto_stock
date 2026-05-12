"""P0 Red — APBK0918 + '장운영시간/매매 불가 시간' 분류 가드.

운영 회고(2026-05-09 좀비 포지션):
- KIS는 NXT 프리(08:00) 시점에 KRX 단독 종목 매도 시도 시 `APBK0918` + "장운영시간이 아닙니다"
  계열 응답을 보낸다.
- 기존 `is_insufficient_quantity()`는 msg_cd만 보고 `APBK0918`을 *True*(보유 부족)로 분류했고,
  `execute_sell` 호출부에서 메모리·DB positions를 즉시 삭제했다.
- 결과: 실제 잔고는 정상이지만 시스템은 좀비 상태(positions 비어있음 + 손절 감시 불가).

요구 행위:
1. `APBK0918` 응답이라도 msg1에 "장운영시간"/"매매 불가 시간" 키워드가 있으면
   `is_insufficient_quantity()` 는 *False* 를 반환한다 (= 보유 부족 아님 → positions 보존).
2. `is_insufficient_cash()` 역시 같은 키워드면 *False* 를 반환한다 (= 자금 락 걸지 않음).
3. msg_cd 가 명시적 보유부족(APBK1234) 이거나, msg1 에 보유부족 키워드("매도가능"/"보유수량"/"잔고")가 있으면
   여전히 True 를 반환한다.
4. msg_cd 가 명시적 현금부족(APBK0919) 이면 여전히 True 를 반환한다.

P2 Red 추가 — `is_market_order_disallowed` (2026-05-11 계양전기 "시장가매매불가" 거부):
- KIS 가 매수 시장가 주문에 "시장가매매불가" 류 msg1 을 돌려보낼 때를 식별하는 새 분류 헬퍼.
- 기존 3종(`is_market_closed_rejection`/`is_insufficient_cash`/`is_insufficient_quantity`)과
  **상호 배타** — 시장가 거부 키워드 변형(`"시장가매매불가"`/`"시장가 매매 불가"`/
  `"시장가 주문 불가"`/`"시장가 호가 불가"`)에서 기존 3종은 모두 False 를 반환해야 한다.
- 반대로 기존 3종이 True 인 msg1(장운영시간/예수금 부족/보유수량 부족)에서
  `is_market_order_disallowed` 는 False.
"""

from __future__ import annotations

import pytest

from src.api.balance import (
    is_insufficient_cash,
    is_insufficient_quantity,
    is_market_closed_rejection,
    is_market_order_disallowed,
)
from src.api.base import KisApiError

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# is_insufficient_quantity — APBK0918 가드
# ---------------------------------------------------------------------------
def test_is_insufficient_quantity_when_apbk0918_with_market_closed_then_false():
    """APBK0918 + '장운영시간이 아닙니다' → 보유 부족 아님."""
    err = KisApiError(rt_cd="1", msg_cd="APBK0918", msg1="장운영시간이 아닙니다.")
    assert is_insufficient_quantity(err) is False


def test_is_insufficient_quantity_when_apbk0918_with_not_tradable_time_then_false():
    """APBK0918 + '매매 불가 시간' → 보유 부족 아님."""
    err = KisApiError(rt_cd="1", msg_cd="APBK0918", msg1="매매 불가 시간입니다.")
    assert is_insufficient_quantity(err) is False


def test_is_insufficient_quantity_when_apbk0918_with_market_session_keyword_then_false():
    """APBK0918 + '장시간' 키워드 (변형) → 보유 부족 아님."""
    err = KisApiError(rt_cd="1", msg_cd="APBK0918", msg1="현재 시각은 장운영시간 외입니다.")
    assert is_insufficient_quantity(err) is False


def test_is_insufficient_quantity_when_apbk1234_then_true():
    """APBK1234 (진짜 보유 부족) → True 유지."""
    err = KisApiError(rt_cd="1", msg_cd="APBK1234", msg1="매도가능수량이 부족합니다.")
    assert is_insufficient_quantity(err) is True


def test_is_insufficient_quantity_when_apbk0918_with_holding_keyword_then_true():
    """APBK0918 이라도 msg1 이 보유 부족이면 True (오버로드 케이스 보존)."""
    err = KisApiError(rt_cd="1", msg_cd="APBK0918", msg1="매도가능수량 부족")
    assert is_insufficient_quantity(err) is True


def test_is_insufficient_quantity_when_holding_keyword_only_then_true():
    """msg_cd 가 화이트리스트 밖이어도 msg1 키워드만으로 True."""
    err = KisApiError(rt_cd="1", msg_cd="EGW00000", msg1="보유수량 부족입니다.")
    assert is_insufficient_quantity(err) is True


# ---------------------------------------------------------------------------
# is_insufficient_cash — APBK0918 가드 (매수 락 오발동 방지)
# ---------------------------------------------------------------------------
def test_is_insufficient_cash_when_apbk0918_with_market_closed_then_false():
    """APBK0918 + '장운영시간' → 현금 부족 아님 → 매수 락 걸리면 안 됨."""
    err = KisApiError(rt_cd="1", msg_cd="APBK0918", msg1="장운영시간이 아닙니다.")
    assert is_insufficient_cash(err) is False


def test_is_insufficient_cash_when_apbk0918_with_not_tradable_time_then_false():
    err = KisApiError(rt_cd="1", msg_cd="APBK0918", msg1="매매 불가 시간입니다.")
    assert is_insufficient_cash(err) is False


def test_is_insufficient_cash_when_apbk0919_then_true():
    """APBK0919 (진짜 예수금 부족) → True 유지."""
    err = KisApiError(rt_cd="1", msg_cd="APBK0919", msg1="주문가능금액이 부족합니다.")
    assert is_insufficient_cash(err) is True


def test_is_insufficient_cash_when_apbk0918_with_cash_keyword_then_true():
    """APBK0918 이라도 msg1 에 현금 부족 키워드 있으면 True."""
    err = KisApiError(rt_cd="1", msg_cd="APBK0918", msg1="주문가능금액 부족")
    assert is_insufficient_cash(err) is True


# ---------------------------------------------------------------------------
# is_market_order_disallowed — 시장가 거부 키워드 식별 (P2 Red)
# ---------------------------------------------------------------------------
# msg_cd 는 운영 trace 누적 후 화이트리스트화 예정 — 현재는 미상이라
# 의도적으로 "UNKNOWN" 으로 고정해 msg1 키워드만으로 분류한다는 점을 명시한다.
_MARKET_ORDER_DISALLOWED_MSGS = (
    "시장가매매불가",
    "시장가 매매 불가",
    "시장가 주문 불가",
    "시장가 호가 불가",
    # 2026-05-11 계양전기(012200) 매도 거부 — APBK1943, msg1 "시장가호가불가로 주문이 불가합니다."
    # 띄어쓰기 없는 변형 — 매수/매도 양쪽 폴백 분기에서 인식되어야 한다.
    "시장가호가불가",
)


# Phase C Red — APBK1943 실제 msg1 (계양전기 매도 거부 사고 원문 검증)
def test_is_market_order_disallowed_when_kyungyang_apbk1943_then_true():
    """2026-05-11 계양전기 09:00:21 매도 거부 원문(APBK1943) → True."""
    err = KisApiError(
        rt_cd="1",
        msg_cd="APBK1943",
        msg1="시장가호가불가로 주문이 불가합니다.",
    )
    assert is_market_order_disallowed(err) is True
    # 상호 배타 — 기존 3종은 False
    assert is_market_closed_rejection(err) is False
    assert is_insufficient_cash(err) is False
    assert is_insufficient_quantity(err) is False


@pytest.mark.parametrize("msg1", _MARKET_ORDER_DISALLOWED_MSGS)
def test_is_market_order_disallowed_when_market_order_keyword_then_true(msg1):
    """'시장가매매불가' 변형 msg1 → True."""
    err = KisApiError(rt_cd="1", msg_cd="UNKNOWN", msg1=msg1)
    assert is_market_order_disallowed(err) is True


@pytest.mark.parametrize("msg1", _MARKET_ORDER_DISALLOWED_MSGS)
def test_is_market_closed_rejection_when_market_order_keyword_then_false(msg1):
    """'시장가매매불가'는 장운영시간 거부가 아니다 — 상호 배타."""
    err = KisApiError(rt_cd="1", msg_cd="UNKNOWN", msg1=msg1)
    assert is_market_closed_rejection(err) is False


@pytest.mark.parametrize("msg1", _MARKET_ORDER_DISALLOWED_MSGS)
def test_is_insufficient_cash_when_market_order_keyword_then_false(msg1):
    """'시장가매매불가'는 예수금 부족이 아니다 — 매수 락 걸리면 안 됨."""
    err = KisApiError(rt_cd="1", msg_cd="UNKNOWN", msg1=msg1)
    assert is_insufficient_cash(err) is False


@pytest.mark.parametrize("msg1", _MARKET_ORDER_DISALLOWED_MSGS)
def test_is_insufficient_quantity_when_market_order_keyword_then_false(msg1):
    """'시장가매매불가'는 보유수량 부족이 아니다 — positions 삭제하면 안 됨."""
    err = KisApiError(rt_cd="1", msg_cd="UNKNOWN", msg1=msg1)
    assert is_insufficient_quantity(err) is False


@pytest.mark.parametrize(
    "msg_cd,msg1",
    [
        # 장운영시간 거부 — `is_market_closed_rejection` True
        ("APBK0918", "장운영시간이 아닙니다."),
        ("APBK0918", "매매 불가 시간입니다."),
        # 예수금 부족 — `is_insufficient_cash` True
        ("APBK0919", "주문가능금액이 부족합니다."),
        ("APBK0918", "주문가능금액 부족"),
        # 보유수량 부족 — `is_insufficient_quantity` True
        ("APBK1234", "매도가능수량이 부족합니다."),
        ("EGW00000", "보유수량 부족입니다."),
    ],
)
def test_is_market_order_disallowed_when_other_rejection_then_false(msg_cd, msg1):
    """기존 3종이 True 를 돌려주는 msg1 에서는 `is_market_order_disallowed` 가 False — 상호 배타."""
    err = KisApiError(rt_cd="1", msg_cd=msg_cd, msg1=msg1)
    assert is_market_order_disallowed(err) is False
