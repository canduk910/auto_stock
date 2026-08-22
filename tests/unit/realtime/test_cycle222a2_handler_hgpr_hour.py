"""cycle222-a2 — `[27] HGPR_HOUR` 로 당일고가를 **KRX 정규장 창으로 스코프 필터** (RED).

## 왜 필요한가 — F2 는 추측이 아니라 실측이다

통합 시세 채널 `H0UNCNT0` 의 일-스코프 필드(`[8] STCK_HGPR`)는 **09:00 에 리셋되지
않는다**. 2026-08-21 000250(삼천당제약) 라이브 실측:

    MAIN 구간 통합 틱의 일-스코프 시가 = 182,800
    같은 날 KRX 일봉 O/H/L/C     = 177,500 / 177,500 / 166,000 / 168,700

182,800 은 KRX 당일고가를 +3.0% 초과하고 **전일 종가와 정확히 일치**하는
08:00~09:00 NXT 프리장 기준가 체결이다. 이 값을 그대로 트레일링 앵커
(`Position.high_since_buy`)에 먹이면 프리장 왜곡 고점이 샹들리에 기준점을 부풀려
**청산이 조기 발화**한다 — CLAUDE.md 의 프리장 청산 평가 보류 게이트(2026-08-06)가
막으려던 것과 같은 종류의 오염이 다른 문으로 들어오는 셈이다.

cycle222-a 1차 구현은 이걸 `risk.py` 쪽 **매일 baseline 재설정**으로 회피했지만,
그 방식은 "오늘의 blind 고점" 을 통째로 버린다(사용자 반대: *"당일로 쪼개버리면
기간중 최고점에서 야금야금 하락했을 때 익절을 못한다"*). 그래서 방어를 **소스로
내린다** — payload 안에 이미 결정적 판별자가 있다.

## 판별자 — `[27] HGPR_HOUR`

KIS 공식 정본(`ccnl_total`, H0UNCNT0) **46 컬럼** 중 `[27] HGPR_HOUR`(최고가 시간,
HHMMSS 6자리). 0-index 검증됨:

    [7] STCK_OPRC  [8] STCK_HGPR  [9] STCK_LWPR  ...
    [24] OPRC_HOUR [25] OPRC_VRSS_PRPR_SIGN [26] OPRC_VRSS_PRPR
    [27] HGPR_HOUR [28] HGPR_VRSS_PRPR_SIGN  ...  [33] BSOP_DATE

⚠️ 기존 `test_cycle222a_handler_day_high.py` 의 docstring "41 컬럼" 은 **스테일**이다.
   [27] 을 채우려면 최소 28 필드가 필요하므로 이 파일은 46 컬럼 헬퍼를 쓴다.

## 계약 (`_parse_day_high(fields)`)

1. `[27]` 을 int 파싱. 실패(짧은 payload=IndexError / 빈 문자열 / 비숫자) → **0(fail-closed)**
2. `090000 <= hour <= 153000` 이 아니면 → **0**
3. 통과 시에만 `[8]` 을 파싱해 반환. `[8]` 파싱 실패 → 0

## cycle222-a3 F-A — 상한 154000 → 153000(포함) 의미 전환

1차 상한은 `session._BOARD_SCHEDULE` 의 MAIN 구간(09:00~15:40, 배타)에서 왔는데
그 **15:40 은 보드 전환 갭 마진이지 거래시간이 아니다**(session.py 주석이
"15:30~15:40 갭 마진 포함" 이라고 자백한다). KRX 정규장은 15:30 에 끝난다 —
`scanner._TIME_KRX_MAIN_END = 15:30` / `scheduler.TIME_KRX_MAIN_CLOSE = 15:30` /
`sell_rejection.is_nxt_session_hours` 가 15:30~20:00 을 NXT 로 본다.

즉 **15:30:00~15:39:59 에 새 당일고가가 생기려면 NXT 애프터 체결뿐**인데 구 상한은
그걸 10분간 통과시켰다(실증: `_parse_day_high(hgpr_hour=153100, high=95000) -> 95000`).

상한을 **포함(<=)** 으로 두는 이유 = 장마감 동시호가(15:20~15:30) 체결이 `153000`
에 프린트되므로 정당한 KRX 고가다. `153001` 부터는 NXT 애프터.

⚠️ **틱을 버리지 않는다.** 고가는 부가 관측이라 0 으로 강등할 뿐, 예외를 던지거나
   `return` 으로 틱을 drop 하면 사이클 88 G-REJECT-1 재연결 trigger 가 오발화하고
   손절 평가 자체가 멈춘다. 기존 `len(fields) < 10` silent-drop 가드와 그 앞의
   가격 파싱 실패 분기는 **byte 보존**한다.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from src.realtime import handler

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# payload 헬퍼 — H0UNCNT0 정본 46 컬럼
# ---------------------------------------------------------------------------

def _fields46(*, current="80000", open_="75800", high="86500", hgpr_hour="093015") -> list[str]:
    """KIS 정본 46 컬럼 체결가 payload 필드 배열.

    인덱스 주석은 정본 순서 그대로다 — [8]/[27] 의 위치가 이 사이클의 전부이므로
    중간 필드도 자리를 정확히 채운다(잘라 쓰면 [27] 이 밀려 테스트가 거짓 통과한다).
    """
    return [
        "000250",       # [0]  종목코드 MKSC_SHRN_ISCD
        "093015",       # [1]  체결시간 STCK_CNTG_HOUR
        current,        # [2]  현재가 STCK_PRPR
        "2",            # [3]  전일대비구분 PRDY_VRSS_SIGN
        "4200",         # [4]  전일대비 PRDY_VRSS
        "5.54",         # [5]  등락률 PRDY_CTRT
        "79000",        # [6]  가중평균 WGHN_AVRG_STCK_PRC
        open_,          # [7]  시가 STCK_OPRC
        high,           # [8]  고가 STCK_HGPR       ← 채택 대상
        "75000",        # [9]  저가 STCK_LWPR
        "80100",        # [10] 매도호가1 ASKP1
        "80000",        # [11] 매수호가1 BIDP1
        "10",           # [12] 체결거래량 CNTG_VOL
        "123456",       # [13] 누적거래량 ACML_VOL
        "9876543210",   # [14] 누적거래대금 ACML_TR_PBMN
        "100",          # [15] 매도체결건수 SELN_CNTG_CSNU
        "120",          # [16] 매수체결건수 SHNU_CNTG_CSNU
        "20",           # [17] 순매수체결건수 NTBY_CNTG_CSNU
        "1.20",         # [18] 체결강도 CTTR
        "5000",         # [19] 총매도수량 SELN_CNTG_SMTN
        "6000",         # [20] 총매수수량 SHNU_CNTG_SMTN
        "1",            # [21] 체결구분 CCLD_DVSN
        "54.5",         # [22] 매수비율 SHNU_RATE
        "110.0",        # [23] 전일거래량대비등락율 PRDY_VOL_VRSS_ACML_VOL
        "090000",       # [24] 시가시간 OPRC_HOUR
        "2",            # [25] 시가대비구분 OPRC_VRSS_PRPR_SIGN
        "1000",         # [26] 시가대비 OPRC_VRSS_PRPR
        hgpr_hour,      # [27] 최고가시간 HGPR_HOUR  ← 이번 사이클의 판별자
        "5",            # [28] 고가대비구분 HGPR_VRSS_PRPR_SIGN
        "-6500",        # [29] 고가대비 HGPR_VRSS_PRPR
        "091200",       # [30] 최저가시간 LWPR_HOUR
        "2",            # [31] 저가대비구분 LWPR_VRSS_PRPR_SIGN
        "5000",         # [32] 저가대비 LWPR_VRSS_PRPR
        "20260821",     # [33] 영업일자 BSOP_DATE
        "50",           # [34] 신 장운영구분코드 NEW_MKOP_CLS_CODE
        "N",            # [35] 거래정지여부 TRHT_YN
        "300",          # [36] 매도호가잔량1 ASKP_RSQN1
        "400",          # [37] 매수호가잔량1 BIDP_RSQN1
        "12000",        # [38] 총매도호가잔량 TOTAL_ASKP_RSQN
        "15000",        # [39] 총매수호가잔량 TOTAL_BIDP_RSQN
        "0.85",         # [40] 거래량회전율 VOL_TNRT
        "90000",        # [41] 전일동시간누적거래량 PRDY_SMNS_HOUR_ACML_VOL
        "137.2",        # [42] 전일동시간누적거래량비율 PRDY_SMNS_HOUR_ACML_VOL_RATE
        "0",            # [43] 시간구분코드 HOUR_CLS_CODE
        "0",            # [44] 임의종료구분코드 MRKT_TRTM_CLS_CODE
        "0",            # [45] 정적VI발동기준가 VI_STND_PRC
    ]


def _payload(*, n: int | None = None, **kw) -> str:
    """`^` 결합 payload. `n` 을 주면 앞에서 n 개만 잘라 **짧은 payload** 를 만든다."""
    fields = _fields46(**kw)
    if n is not None:
        fields = fields[:n]
    return "^".join(fields)


def _day_high_of(call) -> int:
    """키워드 우선, 폴백으로 5번째 positional (기존 파일과 동일 규약)."""
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


async def _day_high_via_handler(spy, **kw) -> int:
    """`_handle_tick` 을 실제로 통과시킨 뒤 콜백이 받은 day_high 를 돌려준다.

    내부 헬퍼(`_parse_day_high`)를 직접 부르지 않고 **실제 seam** 으로 검증한다 —
    가드 순서(`len(fields) < 10` → 가격 파싱 → 고가 파싱)까지 함께 잠긴다.
    """
    await handler._handle_tick(_payload(**kw))
    spy.assert_awaited_once()
    return _day_high_of(spy.await_args)


# ===========================================================================
# G-1 — KRX 정규장 창(09:00~15:30, 양끝 포함) 안의 고가만 채택 (cycle222-a3 F-A)
# ===========================================================================

@pytest.mark.asyncio
async def test_main_window_hour_forwards_day_high(spy):
    """정상 케이스 — 09:30:15 에 찍힌 고가는 KRX 실거래라 그대로 흐른다."""
    assert await _day_high_via_handler(spy, hgpr_hour="093015", high="86500") == 86_500


@pytest.mark.asyncio
async def test_premarket_hour_downgrades_day_high_to_zero(spy):
    """★ 핵심 — 08:30:12 고가는 NXT 프리장이므로 **0(미관측)** 으로 강등한다.

    000250 실측(2026-08-21): 통합 틱의 일-스코프 값이 KRX 당일고가를 +3.0% 초과하고
    전일 종가와 일치했다 = 09:00 리셋 없음이 확증. 이 값이 앵커에 들어가면
    샹들리에 기준점이 부풀어 **없던 고점 기준으로 청산**한다.
    """
    assert await _day_high_via_handler(spy, hgpr_hour="083012", high="86500") == 0, (
        "프리장(08:00~09:00) 고가시간이면 day_high 를 채택하면 안 된다 — "
        "현행 구현은 [27] 을 아예 읽지 않아 프리장 왜곡가가 그대로 앵커로 흐른다"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "hour, expected",
    [
        ("090000", 86_500),  # 하한 경계 — 포함 (개장 첫 체결)
        ("085959", 0),       # 하한 직전 1초 — 배제
        ("152959", 86_500),  # 정규장 마지막 1초 — 포함
        ("153000", 86_500),  # 상한 경계 — **포함** (장마감 동시호가 체결 프린트)
        ("153001", 0),       # 상한 직후 1초 — NXT 애프터
        ("153100", 0),       # ★ F-A 실증 — 구 상한(154000 배타)이 통과시키던 구간
        ("153959", 0),       # 구 "MAIN 마지막 1초" — 실제로는 NXT 애프터
        ("154000", 0),       # 구 _BOARD_SCHEDULE MAIN 종료 — 여전히 배제
        ("163000", 0),       # 애프터 NXT — 배제
        ("193000", 0),       # 야간 NXT — 배제
    ],
    ids=["open_incl", "pre_excl", "close_last_incl", "close_incl", "after_1s",
         "fa_leak_1531", "old_1539", "old_1540", "after", "night"],
)
async def test_window_boundaries_are_inclusive_on_both_ends(spy, hour, expected):
    """`090000 <= hour <= 153000` — 하한/상한 **모두 포함** (cycle222-a3 F-A).

    의미 전환: 구 계약은 `< 154000`(배타)이라 15:30:00~15:39:59 의 **NXT 애프터
    체결**을 KRX 고가로 채택했다. `_BOARD_SCHEDULE` 의 MAIN 15:40 은 보드 전환
    갭 마진일 뿐 거래시간이 아니다.
    """
    assert await _day_high_via_handler(spy, hgpr_hour=hour, high="86500") == expected


def test_window_bounds_track_krx_regular_session():
    """상한/하한의 **출처** 를 KRX 정규장(09:00~15:30)에 못박는다 (F-A 의미 전환).

    구 계약은 출처를 `session._BOARD_SCHEDULE` MAIN(09:00~15:40)에 걸었다. 그
    15:40 은 보드 전환 갭 마진이라 **거래시간이 아니고**, 그 결과 NXT 애프터
    체결 10분이 KRX 고가로 새어 들어왔다. 이제 출처는 정규장 종료 상수다.
    """
    from datetime import time as _time

    from src.engine.scanner import _TIME_KRX_MAIN_END

    assert _TIME_KRX_MAIN_END == _time(15, 30), (
        "KRX 정규장 종료 상수가 바뀌었다 — handler 의 고가시간 상한도 함께 갱신하라"
    )
    assert handler._HGPR_HOUR_MAIN_START == 90000
    assert handler._HGPR_HOUR_MAIN_END == (
        _TIME_KRX_MAIN_END.hour * 10000 + _TIME_KRX_MAIN_END.minute * 100
    ), "고가시간 상한이 KRX 정규장 종료와 어긋났다"


def test_window_end_intentionally_differs_from_board_schedule_main():
    """`_BOARD_SCHEDULE` MAIN 종료(15:40)와 **다름** 이 계약이다.

    누군가 "일관성" 을 이유로 다시 15:40 에 맞추면 F-A 결함이 그대로 재발한다.
    두 값은 서로 다른 축이다 — `_BOARD_SCHEDULE` 는 구독/보드 전환 축이고
    여기는 "그 체결이 어느 시장에서 났나" 축이다.
    """
    from src.engine.session import MarketBoard, _BOARD_SCHEDULE

    main = [
        (start, end) for start, end, boards in _BOARD_SCHEDULE
        if boards == frozenset({MarketBoard.MAIN})
    ]
    assert len(main) == 1, f"MAIN 구간이 유일하지 않다: {main}"
    _start, end = main[0]
    board_end = end.hour * 10000 + end.minute * 100
    assert board_end == 154000, (
        "_BOARD_SCHEDULE MAIN 종료가 바뀌었다 — 이 가드의 전제를 재검토하라"
    )
    assert handler._HGPR_HOUR_MAIN_END != board_end, (
        "고가시간 상한이 보드 스케줄 MAIN 종료(15:40)로 되돌아갔다 — "
        "15:30~15:40 은 NXT 애프터 체결 구간이라 KRX 당일고가가 아니다(F-A)"
    )


# ===========================================================================
# G-2 — HGPR_HOUR 파싱 실패는 fail-closed (0)
#
# 방향이 비대칭인 이유: 잘못 채택하면 **없던 고점으로 조기 청산**(돌이킬 수 없는
# 실현손실)이고, 잘못 버리면 앵커가 기존과 동일한 "러닝 max" 로 남는다(현상 유지).
# 그래서 판별이 안 되면 무조건 버린다.
# ===========================================================================

@pytest.mark.asyncio
@pytest.mark.parametrize(
    "bad",
    ["", "  ", "ABC", "09:30:15", "9.3e4"],
    ids=["empty", "spaces", "alpha", "colon", "sci"],
)
async def test_unparseable_hour_is_fail_closed(spy, bad):
    """빈 문자열·비숫자 고가시간 → `int()` 예외 → 0. 판별 불가 = 채택 불가.

    cycle222-a3 F-H — 구 파라미터에 있던 `"-093015"` 는 여기서 **제거**했다.
    `int("-093015")` 는 예외가 아니라 `-93015` 로 **성공**하므로 이 테스트가
    검증한다고 주장하던 파싱 fail-closed 경로를 타지 않는다(뮤테이션 M5 에서
    이 케이스만 살아남았다). 실제로는 창 필터가 잡으므로 아래 창-필터
    테스트로 재분류했다.
    """
    assert await _day_high_via_handler(spy, hgpr_hour=bad, high="86500") == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "hour",
    ["-093015", "-1", "999999", "240000"],
    ids=["negative-hhmmss", "negative-small", "six-nines", "midnight-overflow"],
)
async def test_numeric_but_out_of_window_hour_is_rejected_by_the_window_filter(spy, hour):
    """`int()` 는 성공하지만 창 밖인 값 — **창 필터** 가 잡는다 (F-H 재분류).

    이름이 검증 경로를 정확히 가리켜야 뮤테이션 테스트가 의미를 갖는다.
    `int()` 성공 여부를 실제로 확인해 두어, 나중에 누가 이 케이스를 다시
    "파싱 실패" 로 오분류하지 못하게 막는다.
    """
    int(hour)  # 파싱은 성공한다 — 실패 경로가 아니다
    assert await _day_high_via_handler(spy, hgpr_hour=hour, high="86500") == 0


@pytest.mark.asyncio
async def test_zero_hour_means_no_trade_yet(spy):
    """`000000` = 당일 체결 없음(고가시간 미형성) → 0.

    이 값은 MAIN 창 밖이라 하한 비교만으로도 걸러지지만, **의도** 를 남긴다:
    체결이 없는데 [8] 에 남아 있는 값은 전일/프리장 잔재다.
    """
    assert await _day_high_via_handler(spy, hgpr_hour="000000", high="86500") == 0


@pytest.mark.asyncio
async def test_short_payload_missing_field27_is_zero_and_tick_survives(spy):
    """20 필드 payload — `[27]` 부재(IndexError)여도 **틱은 살아야 한다**.

    `len(fields) < 10` 가드는 통과하므로 on_tick 은 호출된다. 여기서 예외가 새거나
    `return` 으로 빠지면 손절/트레일링 평가가 통째로 멈춘다(사이클 88 G-REJECT-1
    재연결 오발화 + 손절 사각).
    """
    await handler._handle_tick(_payload(n=20, current="80000", open_="75800"))

    spy.assert_awaited_once()  # 틱 자체는 정상 전달
    call = spy.await_args
    assert call.args[0] == "000250"
    assert call.args[1] == 80_000       # 현재가 정상
    assert call.args[2] == 75_800       # 시가 정상
    assert _day_high_of(call) == 0, (
        "[27] 이 없는 payload 는 스코프 판별 불가 → fail-closed 0"
    )
    assert handler._silent_drop_count.get("000250") is None, (
        "고가 스코프 판별 실패는 silent drop 대상이 아니다 (틱은 정상 처리)"
    )


@pytest.mark.asyncio
async def test_missing_hour_field_does_not_raise(spy):
    """예외를 던지면 handler 의 `raise` 계약을 타고 WS 재연결이 오발화한다."""
    await handler._handle_tick(_payload(n=20))  # raise 하면 여기서 터진다
    spy.assert_awaited_once()


@pytest.mark.asyncio
async def test_valid_hour_but_unparseable_high_is_zero(spy):
    """시각은 MAIN 인데 `[8]` 이 깨진 경우 — 기존 0 폴백 계약 유지."""
    assert await _day_high_via_handler(spy, hgpr_hour="093015", high="ABC") == 0
    assert handler._silent_drop_count.get("000250") is None


# ===========================================================================
# G-3 — 기존 계약 비회귀 (스코프 필터가 drop 경로를 바꾸지 않는다)
# ===========================================================================

@pytest.mark.asyncio
async def test_short_payload_under_10_still_silent_drops(spy):
    """9 필드는 기존대로 drop + `_silent_drop_count` 누적.

    `[27]`(또는 `[8]`)을 가드 **앞** 에서 읽으면 IndexError 로 이 계약이 깨진다.
    """
    await handler._handle_tick(_payload(n=9))
    spy.assert_not_awaited()
    assert handler._silent_drop_count.get("000250") == 1


@pytest.mark.asyncio
async def test_price_parse_failure_still_silent_drops(spy):
    """현재가 파싱 실패는 기존대로 drop — 고가 시각 필터가 이 경로를 바꾸지 않는다."""
    await handler._handle_tick(_payload(current="ABC", hgpr_hour="093015"))
    spy.assert_not_awaited()
    assert handler._silent_drop_count.get("000250") == 1


@pytest.mark.asyncio
async def test_day_high_still_passed_as_keyword(spy):
    """키워드 전달 = 기존 4-positional 콜백 계약을 깨지 않는 유일한 방식 (A-9)."""
    await handler._handle_tick(_payload(hgpr_hour="093015"))
    assert "day_high" in spy.await_args.kwargs
