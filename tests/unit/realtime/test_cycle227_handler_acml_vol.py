"""cycle227 W1 (RED) — `_handle_tick` 이 `[13] 누적거래량(ACML_VOL)` 을 콜백에 전달.

## 왜 이 파일이 존재하는가

`bull_flag_breakout` / `vcp_breakout` 의 매수 최종 관문이
`scanner.ticker_prices[t]["acml_vol"]` 를 읽는데 **그 키를 쓰는 코드가 전체 소스에 없다**.
`0 < vol_threshold` 가 항상 참이라 두 전략은 **구조적으로 `Signal.BUY` 를 반환할 수 없었고**,
실제로 전 기간 체결 0건이다(`_workspace/00_URGENT_WORKLIST.md` P0-1).

그런데 누적거래량은 **payload 에 이미 실려 온다** — 사이클 222-a 가 `[8] STCK_HGPR` 에서
정확히 같은 결함("문서화까지 해 놓고 버림")을 시정한 바로 그 자리다.

## 계약 (`_workspace/red/cycle227_acml_vol_stage0_spec.md` W1)

- `_parse_acml_vol(fields) -> int` — `fields[13]`(ACML_VOL, KIS 정본 46 컬럼 3채널 동일).
- 폴백 sentinel 은 **`-1`**. ⚠️ **`0` 금지** — `0` 이 바로 P0 결함의 그 값이고,
  "미수신"과 "진짜 거래량 0"을 구별 불가로 만든다(자문 §5).
- `len(fields) < 14` / 파싱 실패 / 음수 응답 → `-1`.
- **`len(fields) < 10` 가드는 상향 금지** — `< 15` 로 올리면 필드 10~14개 payload 가
  통째로 drop 되어 그 틱으로 돌던 손절·트레일링이 조용히 죽는다(자문 §9.3).
- 콜백 전달은 **키워드 인자**(`acml_vol=`) — 사이클 222-a `day_high` 선례.
- 파싱 실패가 틱을 죽이지 않는다(fail-open). 예외를 던지면 사이클 88 G-REJECT-1
  재연결 trigger 가 오발화한다.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from src.realtime import handler

pytestmark = pytest.mark.unit


_FIELD_COUNT = 46  # KIS 정본 `ccnl_total` / H0UNCNT0


def _fields(*, current="80000", open_="75800", high="86500", hgpr_hour="093000",
            acml_vol="1234567") -> list[str]:
    f = ["0"] * _FIELD_COUNT
    f[0] = "005180"      # [0]  종목코드 MKSC_SHRN_ISCD
    f[1] = "093000"      # [1]  체결시간 STCK_CNTG_HOUR
    f[2] = current       # [2]  현재가 STCK_PRPR
    f[3] = "2"           # [3]  전일대비구분
    f[4] = "4200"        # [4]  전일대비
    f[5] = "5.54"        # [5]  등락률 PRDY_CTRT
    f[6] = "79000"       # [6]  가중평균 WGHN_AVRG_STCK_PRC
    f[7] = open_         # [7]  시가 STCK_OPRC
    f[8] = high          # [8]  고가 STCK_HGPR
    f[9] = "75000"       # [9]  저가 STCK_LWPR
    f[13] = acml_vol     # [13] 누적거래량 ACML_VOL  ← cycle227
    f[14] = "98765432100"  # [14] 누적거래대금 ACML_TR_PBMN
    f[24] = "090000"     # [24] 시가시간 OPRC_HOUR
    f[27] = hgpr_hour    # [27] 최고가시간 HGPR_HOUR
    f[33] = "20260825"   # [33] 영업일자 BSOP_DATE
    return f


def _payload(*, n: int = _FIELD_COUNT, **kw) -> str:
    return "^".join(_fields(**kw)[:n])


def _kw_acml_vol(call) -> int:
    assert "acml_vol" in call.kwargs, (
        "콜백에 `acml_vol` 키워드가 전달되지 않았다 — payload [13] ACML_VOL 이 "
        f"또 버려지고 있다. args={call.args} kwargs={call.kwargs}"
    )
    return call.kwargs["acml_vol"]


@pytest.fixture
def spy():
    original = handler._on_tick
    s = AsyncMock()
    handler.register_tick_handler(s)
    handler._silent_drop_count.clear()
    yield s
    handler._on_tick = original
    handler._silent_drop_count.clear()


# ===========================================================================
# W1-1 / W1-5 — fields[13] 파싱 + 키워드 전달
# ===========================================================================

def test_parse_acml_vol_when_field13_present_then_int():
    """W1-1 — `_parse_acml_vol` 이 `fields[13]` 을 int 로 돌려준다."""
    assert hasattr(handler, "_parse_acml_vol"), (
        "`_parse_acml_vol` 부재 — 누적거래량이 payload 에 실려 오는데도 파싱조차 안 한다"
    )
    assert handler._parse_acml_vol(_fields(acml_vol="1234567")) == 1_234_567


@pytest.mark.asyncio
async def test_handle_tick_when_field13_present_then_forwards_as_keyword(spy):
    """W1-5 — 콜백에 `acml_vol=` 키워드로 흘러야 한다 (기존 positional 계약 보존)."""
    await handler._handle_tick(_payload(acml_vol="1234567"))
    spy.assert_awaited_once()
    call = spy.await_args
    assert call.args[0] == "005180"
    assert call.args[1] == 80_000
    assert _kw_acml_vol(call) == 1_234_567


@pytest.mark.asyncio
async def test_handle_tick_when_forwarding_acml_vol_then_day_high_still_forwarded(spy):
    """W1-9 — cycle222-a `day_high` 계약 동시 유지 (회귀 차단)."""
    await handler._handle_tick(_payload(high="86500", acml_vol="1234567"))
    call = spy.await_args
    assert call.kwargs.get("day_high") == 86_500, (
        "acml_vol 배관을 넣으면서 day_high 전달을 깨뜨렸다 (cycle222-a 회귀)"
    )
    assert _kw_acml_vol(call) == 1_234_567


# ===========================================================================
# W1-2 / W1-7 — 짧은 payload → -1 sentinel, 단 틱은 살린다
# ===========================================================================

@pytest.mark.parametrize("n", [14 - 1, 12, 10], ids=["13fields", "12fields", "10fields"])
def test_parse_acml_vol_when_fields_shorter_than_14_then_minus_one(n):
    """W1-2 — `len(fields) < 14` → `-1`. **`0` 이면 안 된다.**"""
    got = handler._parse_acml_vol(_fields()[:n])
    assert got == -1, (
        f"짧은 payload({n}필드) sentinel 이 {got!r} 이다. `-1` 이어야 한다 — "
        "`0` 은 '진짜 거래량 0' 과 구별 불가라 P0 결함(조용한 fail-closed)을 재생산한다"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("n", [13, 12, 10], ids=["13fields", "12fields", "10fields"])
async def test_handle_tick_when_10_to_13_fields_then_tick_survives_with_minus_one(spy, n):
    """W1-7 — 10~13 필드 payload 는 **여전히 정상 틱**이고 acml_vol 만 `-1`.

    `len(fields) < 10` 가드를 `< 14` 로 올리면 이 틱들이 통째로 drop 되고
    그 틱으로 돌던 손절·트레일링이 조용히 죽는다(자문 §9.3).
    """
    await handler._handle_tick(_payload(n=n))
    assert spy.await_count == 1, (
        f"{n}필드 payload 가 drop 됐다 — 가드 상향은 매매 안전성 퇴행이다"
    )
    assert _kw_acml_vol(spy.await_args) == -1
    assert handler._silent_drop_count.get("005180") is None


# ===========================================================================
# W1-3 / W1-4 / W1-8 — 파싱 실패 · 음수 → -1, 그리고 틱은 산다
# ===========================================================================

@pytest.mark.parametrize(
    "bad", ["", "ABC", "1.5", "1,234", "1e6", " "],
    ids=["empty", "alpha", "float", "comma", "sci", "space"],
)
def test_parse_acml_vol_when_unparsable_then_minus_one(bad):
    """W1-3 — 파싱 실패 → `-1` (예외 전파 금지)."""
    assert handler._parse_acml_vol(_fields(acml_vol=bad)) == -1


@pytest.mark.parametrize("neg", ["-1", "-100"], ids=["minus1", "minus100"])
def test_parse_acml_vol_when_negative_then_minus_one(neg):
    """W1-4 — 음수 응답은 미수신과 동일 취급 (`-1`).

    `record_acml_vol` 이 음수를 무시하므로 어차피 기록되지 않지만,
    sentinel 을 한 값으로 모아야 소비처가 `>= 0` 한 번으로 판정할 수 있다.
    """
    assert handler._parse_acml_vol(_fields(acml_vol=neg)) == -1


@pytest.mark.asyncio
async def test_handle_tick_when_acml_vol_unparsable_then_tick_survives(spy):
    """W1-3 — 거래량 파싱 실패가 틱 전체를 버리면 안 된다 (fail-open)."""
    await handler._handle_tick(_payload(acml_vol="ABC"))
    assert spy.await_count == 1
    assert _kw_acml_vol(spy.await_args) == -1
    assert handler._silent_drop_count.get("005180") is None, (
        "거래량 파싱 실패는 silent drop 대상이 아니다 (틱은 정상 처리)"
    )


@pytest.mark.asyncio
async def test_handle_tick_when_acml_vol_unparsable_then_does_not_raise(spy):
    """W1-8 — 예외를 던지면 사이클 88 G-REJECT-1 재연결 trigger 가 오발화한다."""
    await handler._handle_tick(_payload(acml_vol="ABC"))  # raise 하면 여기서 터진다
    spy.assert_awaited_once()


# ===========================================================================
# W1-6 — `len(fields) < 10` 가드 불변 (현행 보존 검증 · 즉시 PASS 예상)
# ===========================================================================

@pytest.mark.asyncio
async def test_handle_tick_when_9_fields_then_still_silent_drops(spy):
    """W1-6 — 9필드는 기존대로 drop + `_silent_drop_count` 누적.

    `fields[13]` 을 가드 **앞**에서 읽으면 IndexError 로 이 계약이 깨진다.
    """
    await handler._handle_tick(_payload(n=9))
    spy.assert_not_awaited()
    assert handler._silent_drop_count.get("005180") == 1


@pytest.mark.asyncio
async def test_handle_tick_when_price_unparsable_then_still_silent_drops(spy):
    """W1-6 — 현재가 파싱 실패는 기존대로 drop (거래량 파싱과 무관)."""
    await handler._handle_tick(_payload(current="ABC"))
    spy.assert_not_awaited()
    assert handler._silent_drop_count.get("005180") == 1


# ===========================================================================
# W1-10 — 다중 레코드 프레임 (자문 §9.5 — 인지된 노이즈원을 계약으로 고정)
# ===========================================================================

@pytest.mark.asyncio
async def test_handle_tick_when_multi_record_frame_then_reads_first_record(spy):
    """W1-10 — KIS 프레임 건수 N>1 이면 payload 는 46×N 필드다.

    `websocket.py` 가 건수를 버리므로 `fields[13]` 은 **배치 중 가장 오래된(첫)
    레코드**의 누적거래량을 읽는다. 과소 계상 방향이라 fail-closed 쪽으로 안전하지만,
    관측 해석 시 노이즈원으로 인지해야 하므로 **계약으로 못박는다**.
    """
    first = _fields(current="80000", acml_vol="1000")
    second = _fields(current="80100", acml_vol="9999999")
    await handler._handle_tick("^".join(first + second))
    assert _kw_acml_vol(spy.await_args) == 1_000, (
        "다중 레코드 프레임에서 fields[13] 은 첫 레코드 값이다 — 이 사실이 바뀌면 "
        "관측 통계 해석이 통째로 달라지므로 여기서 고정한다"
    )
