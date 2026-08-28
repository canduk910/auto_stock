"""사이클 229 Red — `[단일가매매]` 변형 거부 분류기 편입 (명세 W3).

명세 정본 `_workspace/red/cycle229_buy_cutoff_spec.md` W3 /
자문 정본 `_workspace/domain_consult/cycle229_vb_1530_single_price.md` §5 /
행위 분해 `_workspace/red/cycle229_behaviors.md` §3.

**Red 단계 — 실패 테스트만. 프로덕션 미변경.** Green = backend-dev.

## 결함

실측 msg1 (APBK3013, 8/20~8/27 15:30:0x~2x ×9):

    [단일가매매] 지정가 주문(신규/정정/취소) 및 최유리/최우선 취소 주문만 가능합니다

기존 키워드 `"지정가 및 최유리"` 는 이 문장에서 **중간 삽입어 `(신규/정정/취소)`** 때문에
연속 부분문자열로 성립하지 않는다. 또 하나의 기존 키워드 `"최유리/최우선지정가 주문만"` 도
이 문장의 `"최유리/최우선 취소 주문만"` 과 다르다. 그래서 `is_market_order_disallowed`
가 **False** 로 떨어지고, 매수 측에선 `execute_buy` 미분류 `raise` → `[callback_exception]`
→ WS 재연결, 매도 측에선 3회 재시도 후 **TTL 미등록 무기록 포기**가 된다.

8/26 15:40 의 `[애프터마켓]지정가 및 최유리/최우선지정가 주문만 가능합니다.` 변형은
기존 키워드에 매칭돼 정상 폴백했다 — **변형별로 갈렸다**는 것이 이 결함의 실증이다.

## Green 계약 (명세 W3)

- `_MARKET_ORDER_DISALLOWED_KEYWORDS` 에 **연속 부분문자열** `"단일가매매"` 추가.
- **분류 순서 계약 불변** — `execute_sell` 은 `is_market_closed_rejection` 을 먼저 검사한다
  (2026-08-06 프리마켓 이중 매칭 계약). 이 변형은 장운영 키워드가 없어 교차하지 않는다는 것을
  테스트로 고정한다.
- `is_insufficient_cash` / `is_insufficient_quantity` 와는 상호 배타 유지.

## 주 실익은 매수가 아니라 **매도**다

W1/W2 시간 게이트가 VB·momentum 을 닫으면 매수 축 잔여 경로는 LTV 야간
(`nxt_tradable=False` 다운그레이드 → KRX 시간외단일가)뿐이고, 거기서는 지정가 폴백이
전략 의도에 부합한다(시간외단일가는 지정가만 받고, LTV 는 야간 매수 전략이며 익일 청산이다).
매도 축에선 랜덤엔드 창의 손절/트레일링 거부가 어느 분류에도 안 걸려 **기록조차 안 되고**
있었다 — 편입 시 `step_down` 지정가 폴백 + 30초 TTL 경로를 얻는다.
"""

from __future__ import annotations

import pytest

from src.api.balance import (
    _MARKET_ORDER_DISALLOWED_KEYWORDS,
    is_insufficient_cash,
    is_insufficient_quantity,
    is_market_closed_rejection,
    is_market_order_disallowed,
)
from src.api.base import KisApiError

pytestmark = pytest.mark.unit


# 실측 msg1 **전문** — 임의 축약·정규화 금지 (중간 삽입어가 결함의 직접 원인이다)
SINGLE_PRICE_MSG = (
    "[단일가매매] 지정가 주문(신규/정정/취소) 및 최유리/최우선 취소 주문만 가능합니다"
)
# 8/26 15:40 변형 — 기존 키워드로 정상 매칭되던 쪽 (회귀 보존 대조군)
AFTERMARKET_MSG = "[애프터마켓]지정가 및 최유리/최우선지정가 주문만 가능합니다."
# 2026-05-11 계양전기(012200) APBK1943
APBK1943_MSG = "시장가호가불가로 주문이 불가합니다."
# 2026-08-06 프리마켓 이중 매칭 계약 (closed·disallowed 양쪽 True)
PRE_MARKET_MSG = "장운영시간이 아닙니다.([프리마켓] 시장가 매매 불가 시간)"


def _err(msg1: str, msg_cd: str = "APBK3013") -> KisApiError:
    try:
        return KisApiError(rt_cd="1", msg_cd=msg_cd, msg1=msg1)
    except TypeError:  # pragma: no cover — 시그니처 변경 방어 (기존 파일 패턴 답습)
        e = KisApiError.__new__(KisApiError)
        e.msg_cd, e.msg1 = msg_cd, msg1
        return e


# ===========================================================================
# B3-1 — [RED] 실측 msg1 전문 → `is_market_order_disallowed` True
# ===========================================================================
def test_b3_1_single_price_msg_is_market_order_disallowed() -> None:
    """B3-1 (RED): 이 한 줄이 15:30 WS 재연결 체인과 무기록 매도 포기의 분기점이다.

    현재 FAIL = 어느 기존 키워드에도 안 걸림.
    """
    assert is_market_order_disallowed(_err(SINGLE_PRICE_MSG)) is True, (
        "실측 `[단일가매매]` 변형이 미분류 — 매수는 `raise` 로 WS 재연결, "
        "매도는 3회 재시도 후 TTL 미등록 무기록 포기가 된다"
    )


# ===========================================================================
# B3-8 — [보존] 기존 키워드 2종으로는 **구조적으로** 못 잡는다 (B3-1 의 짝)
# ===========================================================================
def test_b3_8_existing_keywords_structurally_cannot_match_single_price_msg() -> None:
    """B3-8: B3-1 을 '기존 키워드 느슨화' 로 통과시키는 우회 경로를 차단한다.

    실측 msg1 은 기존 2 키워드 어느 것도 연속 부분문자열로 포함하지 않는다.
    따라서 B3-1 이 통과했다면 그것은 반드시 **신규 키워드**의 공로다.
    반대로 기존 키워드를 넓혀서 통과시키면 이 케이스가 깨지며, 그 넓힘은
    정상 안내 문구까지 오탐할 위험을 동반한다(B3-10 참조).
    """
    assert "지정가 및 최유리" not in SINGLE_PRICE_MSG, (
        "중간 삽입어 `(신규/정정/취소)` 로 이 키워드가 깨진 것이 결함의 직접 원인이다"
    )
    assert "최유리/최우선지정가 주문만" not in SINGLE_PRICE_MSG, (
        "실측 문장은 `최유리/최우선 취소 주문만` — 애프터마켓 변형과 다르다"
    )


# ===========================================================================
# B3-9 — [RED] 신규 키워드가 연속 부분문자열 `"단일가매매"`
# ===========================================================================
def test_b3_9_new_keyword_is_contiguous_substring() -> None:
    """B3-9 (RED): 키워드 선택 자체를 계약으로 고정한다.

    `"지정가 및 최유리"` 가 삽입구 하나에 깨진 것이 이번 결함이므로, 신규 키워드는
    다시 깨지지 않을 **연속 부분문자열**이어야 한다. 자문 §9-6 이 `"단일가매매"` 단독을
    지목했다 — 대괄호 태그 안에 붙어 있어 삽입어가 끼어들 자리가 없다.
    """
    assert "단일가매매" in _MARKET_ORDER_DISALLOWED_KEYWORDS, (
        "`_MARKET_ORDER_DISALLOWED_KEYWORDS` 에 `단일가매매` 미편입"
    )
    assert "단일가매매" in SINGLE_PRICE_MSG  # 연속 부분문자열 자기 검증


# ===========================================================================
# B3-2 — [보존] 순서 계약 무교차: market_closed 는 False
# ===========================================================================
def test_b3_2_single_price_msg_is_not_market_closed() -> None:
    """B3-2 (보존): 이 변형은 장운영 키워드가 없어 `is_market_closed_rejection` 과 교차하지 않는다.

    `execute_sell` 은 market_closed 를 **먼저** 검사한다(프리마켓 이중 매칭이 '보류' 로
    떨어지게 하는 의도된 계약). 만약 이 변형이 양쪽에 걸리면 신규 폴백이 보류에 가려
    아무 효과가 없다. 교차 없음을 여기서 못 박는다.
    """
    assert is_market_closed_rejection(_err(SINGLE_PRICE_MSG)) is False


# ===========================================================================
# B3-3 / B3-4 — [보존] 자금·수량 부족 2종과 상호 배타
# ===========================================================================
def test_b3_3_single_price_msg_is_not_insufficient_cash() -> None:
    """B3-3 (보존): 자금 락(`block_buy` 900s)이 잘못 걸리면 매수가 15분 정지한다."""
    assert is_insufficient_cash(_err(SINGLE_PRICE_MSG)) is False


def test_b3_4_single_price_msg_is_not_insufficient_quantity() -> None:
    """B3-4 (보존): 보유부족으로 오분류되면 **메모리·DB positions 가 삭제**된다 — 좀비 포지션."""
    assert is_insufficient_quantity(_err(SINGLE_PRICE_MSG)) is False


# ===========================================================================
# B3-5 / B3-6 — [보존] 기존 변형 회귀
# ===========================================================================
def test_b3_5_aftermarket_variant_still_matches() -> None:
    """B3-5 (보존): 8/26 15:40 변형은 기존 키워드로 계속 매칭돼야 한다 (Phase H1 회귀)."""
    assert is_market_order_disallowed(_err(AFTERMARKET_MSG)) is True


def test_b3_6_apbk1943_variant_still_matches() -> None:
    """B3-6 (보존): 2026-05-11 계양전기 APBK1943 회귀."""
    assert is_market_order_disallowed(_err(APBK1943_MSG, msg_cd="APBK1943")) is True


# ===========================================================================
# B3-7 — [보존] 프리마켓 이중 매칭 계약 불변
# ===========================================================================
def test_b3_7_pre_market_double_match_preserved() -> None:
    """B3-7 (보존): 신규 키워드 추가가 2026-08-06 이중 매칭 계약을 흔들지 않는다.

    프리마켓 msg1 은 closed·disallowed **양쪽 True** 이고, `execute_sell` 의 검사 순서가
    그것을 '보류(포지션 보존 + 다음 09:00 TTL)' 로 떨어뜨린다. 프리장은 왜곡 시세라
    지정가 폴백 즉시 매도보다 09:00 KRX 보류가 안전하다는 사용자 결정이 근거다.
    """
    e = _err(PRE_MARKET_MSG, msg_cd="APBK0918")
    assert is_market_closed_rejection(e) is True
    assert is_market_order_disallowed(e) is True
    assert is_insufficient_cash(e) is False
    assert is_insufficient_quantity(e) is False


# ===========================================================================
# B3-10 — [보존] 정상 안내 문구 오탐 없음
# ===========================================================================
@pytest.mark.parametrize(
    "benign",
    [
        "지정가 주문이 정상적으로 접수되었습니다.",
        "주문이 체결되었습니다.",
        "",
    ],
    ids=["limit_accepted", "filled", "empty"],
)
def test_b3_10_benign_messages_not_classified(benign: str) -> None:
    """B3-10 (보존): 신규 키워드가 정상 응답을 시장가 거부로 오탐하면 안 된다.

    오탐하면 정상 접수된 주문에 대해 불필요한 지정가 폴백이 한 번 더 나간다(중복 주문).
    기존 주석의 경고("`지정가` 단독은 정상 안내와 충돌하므로 금지")와 같은 축이다.
    """
    assert is_market_order_disallowed(_err(benign, msg_cd="0")) is False
