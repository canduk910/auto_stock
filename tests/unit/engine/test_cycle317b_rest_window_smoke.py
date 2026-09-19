"""cycle317b — 휴식 창 시각을 **고정한 채** 주문 경로가 도는지 본다.

## 왜 필요한가

cycle317 이 세운 메타 가드는 **바닥선**이다. 「휴식 컷을 검증하는 파일은 옵트아웃 마커를
들어야 한다」를 키워드로 탐색하는데, 표현이 다르면 놓친다 — 실측으로
`test_cycle287_exchange_routing.py` 가 판정 이름도 마커 이름도 안 쓰고
「cycle295 컷」이라는 한글 표현만 써서 빠져나갔고, **전체 스위트에서야** 드러났다(59→5→1건).

그리고 더 큰 문제는 **재현이 하루 30분에 묶여 있다**는 것이다. 15:30~16:00 밖에서 돌리면
전부 초록이라, 「고쳤다」는 확신이 그 창에 들어가 봐야만 생긴다.

이 파일은 그 둘을 함께 닫는다 — `freeze_time` 으로 **휴식 창 한복판을 고정**하고
주문 경로를 실제로 태운다. 시각과 무관하게 언제 돌려도 같은 답이 나온다.

## 무엇을 재는가

1. **중립화가 실제로 먹는가** — 창 안 시각에서도 주문이 나간다(픽스처 덕).
2. **옵트아웃하면 컷이 산다** — 같은 시각에서 주문이 막힌다(cycle295 기능 보존).

⚠️ freezegun 은 이 저장소에서 `_wait_until` 계열에 hang 을 만든 선례가 있다
(동결된 monotonic + `asyncio.sleep` 루프). 여기서는 **판정 함수만** 부르고 대기 루프에
들어가지 않으므로 그 함정과 무관하다 — 스케줄러 경로로 넓히지 마라.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from freezegun import freeze_time

pytestmark = pytest.mark.unit

_KST = timezone(timedelta(hours=9))

#: 🔴 **`freeze_time` 문자열에 tz 를 반드시 명시한다.**
#: naive 문자열을 주면 freezegun 이 그것을 **UTC 로 해석**해서, 프로덕션이 쓰는
#: `datetime.now(_KST_TZ)` 가 **9시간 앞선 값**을 돌려준다(실측:
#: `freeze_time("2026-09-21 15:45:00")` → `now(KST) == 2026-09-22 00:45`).
#: 그러면 「휴식 창을 고정했다」고 믿는 테스트가 실제로는 **자정 45분**을 보게 된다.
#: `datetime.now()`(tz 없음)만 쓰는 테스트는 이 함정에 안 걸리므로
#: `conftest.kst_clock` 의 「그냥 KST 문자열을 넘긴다」 주석은 그쪽 기준이다.
#:
#: ⚠️ **이 저장소의 기존 관례는 「UTC 문자열을 주고 KST 로 변환되게 하는 것」이다**
#: (실측 25파일). 예 = `test_cycle287_exchange_routing.py` 가 `"2026-09-14 07:05:00"` 로
#: KST 16:05 를 만든다. 그 방식도 맞게 동작하지만 읽을 때 +9 암산이 필요하고,
#: 무엇보다 **naive 문자열이 KST 라고 착각하기 쉽다**. 새로 쓸 때는 여기처럼 tz 를 명시한다.
#:
#: 휴식 창 한복판. 월요일을 고른 이유 = 주말이면 그 표 자체가 다른 답을 낼 수 있다.
_INSIDE = "2026-09-21 15:45:00+09:00"
#: 같은 날 정규장 — 대조군.
_OUTSIDE = "2026-09-21 11:00:00+09:00"


def _blocked_now() -> tuple[bool, str]:
    """프로덕션이 하는 그대로 — 벽시계를 읽어 판정에 넘긴다."""
    from src.engine import order_engine as oe

    return oe._market_rest_now(datetime.now(_KST))


def test_inside_window_is_neutralized_by_default() -> None:
    """휴식 창 한복판에 시계를 고정해도 **주문 경로가 막히지 않는다**.

    막는 회귀 = cycle317 중립화 픽스처를 지우는 것. 그러면 하루 30분 동안
    주문 경로 테스트 59건이 붉어지고 **CI 가 그 창에서 배포를 막는다**.
    """
    with freeze_time(_INSIDE):
        blocked, reason = _blocked_now()
    assert not blocked, (
        f"휴식 창({_INSIDE})에서 컷이 살아 있다 (reason={reason}) — "
        "중립화 픽스처가 사라졌다. 주문 경로 테스트가 실행 시각에 묶인다."
    )


def test_outside_window_is_also_open() -> None:
    """정규장 시각은 원래도 열려 있다 — 대조군이다.

    이게 없으면 위 테스트가 「중립화 덕」인지 「원래 안 막히는 시각」인지 구별되지 않는다.
    """
    with freeze_time(_OUTSIDE):
        blocked, _ = _blocked_now()
    assert not blocked


@pytest.mark.real_market_rest
def test_inside_window_actually_cuts_without_neutralization() -> None:
    """옵트아웃하면 **같은 시각에서 컷이 산다**.

    🔴 이 테스트가 이 파일의 핵심이다. 위 둘만 있으면 「컷 기능이 사라졌는데도 초록」인
    상태와 구별되지 않는다. 중립화는 **테스트의 시각 의존만** 없앤 것이지
    cycle295 의 기능을 없앤 것이 아니라는 증거다.
    """
    with freeze_time(_INSIDE):
        blocked, reason = _blocked_now()
    assert blocked, (
        f"휴식 창({_INSIDE})인데 컷이 안 걸린다 — cycle295 가 깨졌다."
    )
    assert reason == "market_rest", reason


@pytest.mark.real_market_rest
def test_outside_window_is_not_over_blocked() -> None:
    """정규장을 막지 않는가 — 과잉 차단 회귀 가드."""
    with freeze_time(_OUTSIDE):
        blocked, reason = _blocked_now()
    assert not blocked, f"정규장 11:00 을 막는다 (reason={reason}) — 과잉 차단이다"


@pytest.mark.real_market_rest
@pytest.mark.parametrize(
    "moment,expect_blocked",
    [
        ("2026-09-21 15:29:59+09:00", False),  # 창 직전
        ("2026-09-21 15:30:00+09:00", True),   # 경계 — 시작
        ("2026-09-21 15:59:59+09:00", True),   # 창 끝
        ("2026-09-21 16:00:00+09:00", False),  # 경계 — 애프터마켓 개시
    ],
    ids=["before", "start", "last-second", "after"],
)
def test_window_boundaries(moment: str, expect_blocked: bool) -> None:
    """창 경계가 표대로인가.

    `market_state` 표가 정본이고 이 값들은 거기서 나온다 — 경계가 흔들리면
    15:30 직전 손절이 막히거나 16:00 애프터마켓 청산이 30분 늦는다.
    """
    with freeze_time(moment):
        blocked, _ = _blocked_now()
    assert blocked is expect_blocked, f"{moment}: blocked={blocked}, 기대={expect_blocked}"
