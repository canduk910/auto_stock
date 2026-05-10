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
"""

from __future__ import annotations

import pytest

from src.api.balance import is_insufficient_cash, is_insufficient_quantity
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
