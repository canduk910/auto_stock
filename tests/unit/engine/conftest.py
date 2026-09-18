"""`tests/unit/engine/` 공용 픽스처.

여기 있는 픽스처는 **opt-in** 이다(autouse 아님) — 디렉토리 전체의 행위를 바꾸지
않는다. 쓰려면 모듈에서 명시한다::

    pytestmark = [pytest.mark.unit, pytest.mark.usefixtures("no_real_kis")]
"""
from __future__ import annotations

import pytest


class RealKisCallEscaped(BaseException):
    """테스트에서 실 KIS 호출이 새어 나갔다는 신호.

    🔴 `Exception` 이 아니라 `BaseException` 파생인 것이 계약이다. KIS 호출 경로는
    graceful 이 겹겹이라(`condition.fetch_daily_candles_backfill` 의 윈도우별
    `except Exception` → `scanner._stock_master_daily_load_once` 의 ticker 별
    `except Exception`) 일반 예외를 던지면 **조용히 `failed++` 로 흡수**되어
    모킹 누락이 여전히 안 보인다. `BaseException` 파생은 그 두 관문을 통과해
    테스트를 즉시 붉게 만든다.
    """


@pytest.fixture
def no_real_kis(monkeypatch: pytest.MonkeyPatch):
    """이 모듈의 어떤 테스트도 실 KIS 를 때리지 않는다 (cycle304).

    고치는 것 = cycle302 가 일봉 backfill 게이트를 `existing_count < 225` **하나**로
    넓히자, `condition.fetch_daily_candles`(단일 호출)만 모킹하던 테스트들이
    `condition.fetch_daily_candles_backfill` 분기로 새어 **실제 KIS 서버**
    (`openapivts.koreainvestment.com`)를 호출한 사고다. CI 로그에 남은 것은
    `httpx.HTTPStatusError: 500` 뿐이었고, 그마저 graceful 에 흡수돼 실패 원인이
    "모킹 누락" 이라고 말해 주지 않았다.

    `src.api.condition` 의 KIS 함수는 **전부** 모듈 전역 `kis_get_quote` 를 거치므로
    (`fetch_daily_candles` · `fetch_daily_candles_ranged` ← `fetch_daily_candles_backfill`
    포함) 그 이름 하나만 막으면 어느 fetch 분기로 새든 네트워크 대신 즉시 실패가 된다.
    """

    async def _blocked(*args, **kwargs):
        raise RealKisCallEscaped(
            "실 KIS 호출이 테스트에서 새어 나갔다 — 모킹 누락이다. "
            "일봉 적재는 fetch 분기가 둘(`fetch_daily_candles` / "
            f"`fetch_daily_candles_backfill`)이니 양쪽을 다 모킹하라. args={args!r}"
        )

    monkeypatch.setattr("src.api.condition.kis_get_quote", _blocked)
