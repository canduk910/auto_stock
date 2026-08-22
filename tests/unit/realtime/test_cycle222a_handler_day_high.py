"""cycle222-a — `_handle_tick` 이 `[8] 고가(STCK_HGPR)` 를 콜백에 전달 (RED).

`handler.py` 는 payload 구조를 `[8] 고가(STCK_HGPR)` 로 **문서화까지 해 놓고**
(`_handle_tick` docstring) `current_price/open_price/change_rate` 만 콜백에 넘긴다.
그 결과 당일 고가 관측이 매 틱 버려지고, 트레일링 앵커는 "수신된 틱들의 러닝 max"
로 퇴화한다(blind 구간 고점 영구 유실).

## 계약

- `len(fields) < 10` 가드 **이후** 에서만 `fields[8]` 을 읽는다
  → 기존 silent-drop 계약(`_silent_drop_count`) byte 보존.
- `fields[8]` 파싱 실패는 **`0` 폴백** — 예외를 던지거나 틱 전체를 버리면 안 된다.
  (가격 파싱 실패는 기존대로 drop, 고가 파싱 실패는 drop 아님.)
- 콜백 전달은 **키워드 인자 + 기본값**(`day_high: int = 0`) — 기존 호출자 호환.

## cycle222-a2 동반 갱신 (의미 전환 1건)

재설계로 `_parse_day_high` 가 `[27] HGPR_HOUR` 를 **먼저** 읽어 KRX MAIN 창
(`090000 <= h < 154000`) 밖 고가를 0 으로 강등한다. 이 파일의 `_payload()` 는
10 필드만 만들어 `[27]` 이 **부재**했으므로, 새 계약에서는
`test_handle_tick_forwards_field8_as_day_high` 가 0 을 받는 게 정답이 되어 버린다
(짧은 payload → 판별 불가 → fail-closed).

그래서 헬퍼를 KIS 정본 **46 컬럼**으로 올리고 `hgpr_hour` 기본값을 MAIN 시각
(`093000`)으로 준다 — 이 파일이 지키는 계약(`[8]` 전달 / silent-drop 보존 /
고가 파싱 실패 0 폴백 / 콜백 예외 재-raise)은 **하나도 바뀌지 않는다**.
창 필터 자체의 계약은 `test_cycle222a2_handler_hgpr_hour.py` 가 전담한다.
(구 docstring 의 "41 컬럼" 표기도 정본 46 컬럼으로 동반 정정 — `handler.py`.)
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from src.realtime import handler

pytestmark = pytest.mark.unit


_FIELD_COUNT = 46  # KIS 정본 `ccnl_total` / H0UNCNT0


def _payload(
    *, current="80000", open_="75800", high="86500", hgpr_hour="093000", n=_FIELD_COUNT,
) -> str:
    """정본 46 컬럼 payload. `n` 을 주면 앞에서 n 개만 잘라 짧은 payload 를 만든다.

    `hgpr_hour` 기본값은 **MAIN 창 안**(09:30:00) — 이 파일의 관심사는 창 필터가
    아니라 `[8]` 전달·drop 계약이므로, 필터를 항상 통과시켜 두고 그 아래 계약만 본다.
    """
    fields = ["0"] * _FIELD_COUNT
    fields[0] = "005180"    # [0]  종목코드 MKSC_SHRN_ISCD
    fields[1] = "093000"    # [1]  체결시간 STCK_CNTG_HOUR
    fields[2] = current     # [2]  현재가 STCK_PRPR
    fields[3] = "2"         # [3]  전일대비구분
    fields[4] = "4200"      # [4]  전일대비
    fields[5] = "5.54"      # [5]  등락률
    fields[6] = "79000"     # [6]  가중평균
    fields[7] = open_       # [7]  시가 STCK_OPRC
    fields[8] = high        # [8]  고가 STCK_HGPR
    fields[9] = "75000"     # [9]  저가 STCK_LWPR
    fields[24] = "090000"   # [24] 시가시간 OPRC_HOUR
    fields[27] = hgpr_hour  # [27] 최고가시간 HGPR_HOUR (cycle222-a2 판별자)
    fields[33] = "20260821"  # [33] 영업일자 BSOP_DATE
    return "^".join(fields[:n])


def _day_high_of(call) -> int:
    """키워드 우선, 폴백으로 5번째 positional."""
    if "day_high" in call.kwargs:
        return call.kwargs["day_high"]
    assert len(call.args) >= 5, (
        f"콜백에 day_high 가 전달되지 않았다 — args={call.args} kwargs={call.kwargs}"
    )
    return call.args[4]


@pytest.fixture
def spy():
    original = handler._on_tick
    s = AsyncMock()
    handler.register_tick_handler(s)
    handler._silent_drop_count.clear()
    yield s
    handler._on_tick = original
    handler._silent_drop_count.clear()


# ---------------------------------------------------------------------------
# H-1 — fields[8] 이 콜백에 전달된다
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_handle_tick_forwards_field8_as_day_high(spy):
    await handler._handle_tick(_payload(high="86500"))
    spy.assert_awaited_once()
    call = spy.await_args
    assert call.args[0] == "005180"
    assert call.args[1] == 80_000
    assert _day_high_of(call) == 86_500, (
        "payload [8] STCK_HGPR 가 콜백까지 흘러야 한다 — 지금은 파싱조차 안 한다"
    )


@pytest.mark.asyncio
async def test_day_high_is_passed_as_keyword(spy):
    """키워드 전달 = 기존 4-positional 호출 계약을 깨지 않는 유일한 방식."""
    await handler._handle_tick(_payload())
    assert "day_high" in spy.await_args.kwargs, (
        "day_high 는 키워드 인자로 전달돼야 한다 (기존 콜백 시그니처 호환)"
    )


# ---------------------------------------------------------------------------
# H-2 — 기존 silent-drop 계약 byte 보존 (len(fields) < 10)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_short_payload_still_silent_drops(spy):
    """9 필드 payload 는 기존대로 drop + `_silent_drop_count` 누적.

    `fields[8]` 을 가드 **앞**에서 읽으면 IndexError 로 계약이 깨진다.
    """
    await handler._handle_tick(_payload(n=9))
    spy.assert_not_awaited()
    assert handler._silent_drop_count.get("005180") == 1


@pytest.mark.asyncio
async def test_price_parse_failure_still_silent_drops(spy):
    """현재가 파싱 실패는 기존대로 drop (고가 파싱과 무관)."""
    await handler._handle_tick(_payload(current="ABC"))
    spy.assert_not_awaited()
    assert handler._silent_drop_count.get("005180") == 1


# ---------------------------------------------------------------------------
# H-3 — 고가 파싱 실패는 틱 전체를 버리지 않는다 (0 폴백)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize("bad", ["", "ABC", "-", "8.65e4"], ids=["empty", "alpha", "dash", "sci"])
async def test_day_high_parse_failure_falls_back_to_zero_without_dropping(spy, bad):
    await handler._handle_tick(_payload(high=bad))
    assert spy.await_count == 1, "고가 파싱 실패로 틱 전체를 버리면 안 된다"
    assert _day_high_of(spy.await_args) == 0
    assert handler._silent_drop_count.get("005180") is None, (
        "고가 파싱 실패는 silent drop 카운터 대상이 아니다 (틱은 정상 처리)"
    )


@pytest.mark.asyncio
async def test_day_high_parse_failure_does_not_raise(spy):
    """예외를 던지면 사이클 88 G-REJECT-1 재연결 trigger 가 오발화한다."""
    await handler._handle_tick(_payload(high="ABC"))  # raise 하면 여기서 터진다
    spy.assert_awaited_once()


# ---------------------------------------------------------------------------
# H-4 — 콜백 예외 계약 영속 (사이클 102 G-CALLBACK1)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_callback_exception_still_raises():
    original = handler._on_tick
    try:
        async def _boom(*a, **k):
            raise RuntimeError("boom")
        handler.register_tick_handler(_boom)
        with pytest.raises(RuntimeError):
            await handler._handle_tick(_payload())
    finally:
        handler._on_tick = original
        handler._silent_drop_count.clear()
