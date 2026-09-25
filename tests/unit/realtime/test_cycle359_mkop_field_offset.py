"""cycle359 (2026-09-25) — `H0UNMKO0` 필드 한 칸 밀림 결함 재현 (Red).

## 결함 (cycle368 에서 수정됨 — 아래는 수정 전 동작의 기록이다)

라이브 `H0UNMKO0` 프레임은 **첫 칸이 종목코드**다(KRX `H0STMKO0` · NXT `H0NXMKO0` 표의
`[0] MKSC_SHRN_ISCD` 와 같은 모양). 그런데 cycle368 이전의
`src/api/market_operation.py::parse_market_op_payload` 와 `src/realtime/handler.py::_handle_market_op`
은 통합 표(`docs/kis/domestic-stock-realtime.md` 「장운영정보 (통합)」 — 종목코드 칸 없음)를
그대로 따라 `fields[0]` 을 `TRHT_YN` 으로 읽었다. 그래서 모든 칸이 한 칸씩 앞으로 당겨졌다.

| 라이브 위치 | 실제 의미 (ticker-first) | 실측 값 | cycle368 이전 파서가 넣던 곳 |
|---|---|---|---|
| [0] | 종목코드 | `100840` | `trht_yn` → 거래정지 판정이 **영원히 거짓** |
| [3] | MKOP_CLS_CODE | `AB1` | `antc_mkop_cls_code` |
| [7] | ISCD_STAT_CLS_CODE | `55`/`57` (신용가능/증거금100%) | `vi_cls_code` → **가짜 VI** |
| [8] | VI_CLS_CODE | `N`/`Y` | `ovtm_vi_cls_code` |

가짜 VI 는 `_vi_active_tickers` 에 들어갔고, `55`/`57` 은 장중에 바뀌지 않으므로
`[market_op_vi_release]` 가 한 번도 안 나왔다. 그 결과 K stale watcher 와 5분 우선 재구독이
**보유 종목**을 그날 21:30 정산까지 건너뛰었다(`[stale_skip_market_op]`).

## 두 번째 덫 (칸만 고치면 안 된다)

칸을 바로 읽으면 `55`/`57` 이 `iscd_stat_cls_code` 로 간다. 그런데 cycle368 이전에는 종목상태를
`_is_code_active`(당시 비활성 집합 `{"", "0", "N", "n"}`)로 판정했으므로 `55`·`57`·`00`(그 외 종목)
이 전부 「종목상태 이상」 = **거래정지 취급**이 됐다. 칸만 고쳤다면 가짜 VI 가 가짜 거래정지로 이름만
바뀌고 재구독 skip 은 그대로였을 것이다 — cycle368 은 그래서 정지 판정을 명시 집합 `{58}` 로 바꿨다.
이 파일은 **파싱 값**과 함께 **최종 행위**(`is_ticker_stale_excluded` · 재구독 여부)를 단언한다.

## 프레임 출처 (EC2 `~/auto_stock/logs/auto_stock.log.<날짜>`, `[H0UNMKO0] tr_key=… payload=…` INFO 원문)

3일간 수신 17건이 **전부 10칸 · 첫 칸 = tr_key** 였다(09-21 10건 · 09-22 2건 · 09-23 5건).

## 마커 규약 (cycle368 — xfail 제거)

cycle359 에서는 수정 전 실패를 `xfail(strict=True, raises=AssertionError)` 로 묶어 두었다.
cycle368(2026-09-25 사용자 결정 — 칸 수정 · 종목상태 정지 판정 `{58}` 한정 · handler 8영역 승인)
이 수정을 착지시키면서 **13건 모두 마커를 걷었다** — 지금은 평범한 회귀 가드다(수정 전 코드에서는
붉었다). 같은 하네스의 **대조군**(A1·A2·C5·E1)은 수정 전후 모두 초록이다.
결정 반영 테스트(정지 판정 · VI·거래정지 10분 자동해제 · 표시용 종목상태 집계 · null 토큰)는
`tests/unit/realtime/test_cycle368_market_op_decisions.py` 에 있다.

자문·조사 메모: `_workspace/domain_consult/cycle359_mkop_field_offset.md`
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.api.market_operation import MarketOpEvent, parse_market_op_payload
from src.engine import market_operation_monitor as mom
from src.realtime import handler

pytestmark = pytest.mark.unit

KST = timezone(timedelta(hours=9))

# ---------------------------------------------------------------------------
# 라이브 프레임 원문 (EC2 파일 로그 verbatim — 한 글자도 고치지 않는다)
# ---------------------------------------------------------------------------
#: 2026-09-22 11:13:06 — 100840 (BFB 보유). 이 한 건이 그날 15:31~19:40 skip 36회를 만들었다.
FRAME_100840_0922 = "100840^N^(null)^AB1^112^^^55^N^"
#: 2026-09-23 10:56:32 — 011170 (kojiro 보유). 그날 15:31~19:55 skip 104회.
FRAME_011170_0923 = "011170^N^(null)^AB1^112^^^57^N^"
#: 2026-09-21 09:40:51 — 003160. 3일 17건 중 **유일하게 [8]=Y** (진짜 VI 발동으로 읽히는 칸).
FRAME_003160_VI_ON = "003160^N^(null)^AB1^311^^^55^Y^"
#: 2026-09-21 09:42:16 — 003160 같은 종목의 다음 프레임. [8]=N (VI 해제).
FRAME_003160_VI_OFF = "003160^N^(null)^AB1^112^^^55^N^"

@pytest.fixture(autouse=True)
def _reset_market_op_state():
    mom.reset_market_op_state()
    saved_board = handler._on_board
    handler._on_board = None
    yield
    mom.reset_market_op_state()
    handler._on_board = saved_board


# ===========================================================================
# A. 증거 고정 — 지금도 초록이어야 한다 (우리 수신 파이프라인 스스로가 첫 칸을 종목코드로 쓴다)
# ===========================================================================
@pytest.mark.asyncio
async def test_A1_websocket_layer_takes_tr_key_from_first_payload_field() -> None:
    """`KisWebSocket._handle_raw` 는 `tr_key = payload.split("^")[0]` 로 종목코드를 뽑는다.

    운영 로그의 `[market_op_vi_active] ticker=100840` 이 바로 이 값이다. 즉 **첫 칸이
    종목코드라는 사실은 우리 코드가 이미 전제하고 있다** — cycle368 이전 파서가 같은 칸을
    `TRHT_YN` 으로 다시 읽은 것이 모순이었다. 이 테스트는 그 전제를 고정한다(수정 전후 모두 초록).
    """
    from src.realtime.websocket import KisWebSocket

    captured: list[tuple[str, str, str, bool]] = []

    async def _capture(tr_id: str, tr_key: str, payload: str, encrypted: bool) -> None:
        captured.append((tr_id, tr_key, payload, encrypted))

    ws = KisWebSocket()
    ws._on_message = _capture
    await ws._handle_raw("0|H0UNMKO0|001|" + FRAME_100840_0922)

    assert captured == [("H0UNMKO0", "100840", FRAME_100840_0922, False)]


def test_A2_live_frames_have_ten_fields_and_ticker_first() -> None:
    """실측 프레임 모양 고정 — 10칸, 첫 칸 = 6자리 종목코드, [1]∈{Y,N}, [8]∈{Y,N}.

    [7] 이 55/57 = `ISCD_STAT_CLS_CODE` 의 값 범위(51~59, 00) 이고 [8] 이 Y/N =
    `VI_CLS_CODE` 의 값 범위라는 것이 ticker-first 배치의 의미 검증이다.
    """
    for frame in (FRAME_100840_0922, FRAME_011170_0923, FRAME_003160_VI_ON, FRAME_003160_VI_OFF):
        fields = frame.split("^")
        assert len(fields) == 10
        assert fields[0].isdigit() and len(fields[0]) == 6
        assert fields[1] in ("Y", "N")
        assert fields[7] in ("55", "57")
        assert fields[8] in ("Y", "N")


# ===========================================================================
# B. 파서 칸 배치 — cycle368 이전 코드에서는 실패했다
# ===========================================================================
def test_B1_trht_yn_is_second_field_not_ticker() -> None:
    """거래정지 여부는 [1] 이다. cycle368 이전에는 [0](종목코드)이 들어가 거래정지 판정이 영원히 거짓이었다."""
    event = parse_market_op_payload("100840", FRAME_100840_0922)
    assert event.trht_yn == "N", f"trht_yn={event.trht_yn!r} — 종목코드가 거래정지 칸에 들어갔다"


def test_B2_all_fields_follow_ticker_first_layout() -> None:
    """KRX/NXT 표(11칸, [0]=MKSC_SHRN_ISCD)와 같은 배치로 읽어야 한다. 라이브는 10칸(EXCH 없음).

    cycle368 F4 — 정지 사유 칸의 KIS null 토큰 `(null)` 은 파서가 `""` 로 정규화한다
    (cycle359 의 기대값은 `"(null)"` 이었다). 칸 배치 검증은 그대로다 — [2] 의 `(null)` 이 사유 칸으로
    가고 `AB1` 이 장운영 코드 제자리에 온다.
    """
    event = parse_market_op_payload("100840", FRAME_100840_0922)
    got = (
        event.trht_yn, event.tr_susp_reas_cntt, event.mkop_cls_code,
        event.antc_mkop_cls_code, event.mrkt_trtm_cls_code, event.divi_app_cls_code,
        event.iscd_stat_cls_code, event.vi_cls_code, event.ovtm_vi_cls_code,
        event.exch_cls_code,
    )
    assert got == ("N", "", "AB1", "112", "", "", "55", "N", "", ""), got


def test_B3_vi_code_is_not_credit_status() -> None:
    """VI 칸에 종목상태(55 신용가능)가 들어가면 안 된다 — 운영 `[market_op_vi_active] vi_code=55` 의 원인이었다."""
    event = parse_market_op_payload("011170", FRAME_011170_0923)
    assert event.vi_cls_code in ("Y", "N"), f"vi_cls_code={event.vi_cls_code!r}"


# ===========================================================================
# C. 최종 행위 — 보유 종목이 가짜 VI/가짜 거래정지로 재구독 안전망에서 빠지면 안 된다
# ===========================================================================
@pytest.mark.parametrize(
    "ticker, frame",
    [("100840", FRAME_100840_0922), ("011170", FRAME_011170_0923)],
    ids=["100840_credit55", "011170_margin57"],
)
def test_C1_live_frame_without_vi_is_not_stale_excluded(ticker: str, frame: str) -> None:
    """VI=N · 거래정지=N · 종목상태 55/57 → stale 회피 대상이 아니다.

    ⚠️ 칸만 고치고 종목상태를 `_is_code_active` 로 판정하면 55/57 이 「종목상태 이상」으로 읽혀
    이 테스트는 **여전히 실패**한다(가짜 VI → 가짜 거래정지로 이름만 바뀜) — 정지 판정이 `{58}` 인 이유.
    """
    mom.record_market_op_event(parse_market_op_payload(ticker, frame))
    assert mom.is_ticker_stale_excluded(ticker) is False, (
        f"vi={sorted(mom.get_vi_active_tickers())} halt={sorted(mom.get_halt_active_tickers())}"
    )


def test_C2_vi_on_then_off_releases() -> None:
    """[8]=Y 프레임 → VI 활성, 다음 [8]=N 프레임 → 해제. cycle368 이전에는 55 로 활성된 뒤 **영원히 안 풀렸다**."""
    mom.record_market_op_event(parse_market_op_payload("003160", FRAME_003160_VI_ON))
    assert "003160" in mom.get_vi_active_tickers()        # cycle368 이전에도 참이었다 — 단 이유가 틀렸다(55)
    mom.record_market_op_event(parse_market_op_payload("003160", FRAME_003160_VI_OFF))
    assert "003160" not in mom.get_vi_active_tickers(), "VI 해제 프레임을 받고도 VI 활성 유지"
    assert mom.is_ticker_stale_excluded("003160") is False


def test_C3_halt_frame_is_detected_as_halt_not_vi() -> None:
    """거래정지 프레임(라이브 모양 + [1]=Y, [7]=58)은 **거래정지**로 잡혀야 한다.

    ⚠️ 합성 프레임이다 — 3일 실측에 거래정지 프레임은 없었다. 모양만 라이브를 따른다.
    cycle368 이전에는 [1]=Y 가 `tr_susp_reas_cntt` 로 가고 58 이 VI 칸으로 가서 「VI」로 오분류됐다.
    """
    frame = "005930^Y^(null)^AB1^112^^^58^N^"
    mom.record_market_op_event(parse_market_op_payload("005930", frame))
    assert "005930" in mom.get_halt_active_tickers()
    assert "005930" not in mom.get_vi_active_tickers()


@pytest.mark.parametrize("iscd_stat", ["00", "55", "57"])
def test_C4_normal_iscd_stat_codes_are_not_halt(iscd_stat: str) -> None:
    """파서와 무관한 두 번째 덫 — 올바로 읽힌 이벤트라도 00/55/57 은 거래정지가 아니다.

    `00` = 그 외 종목(정상), `55` = 당사 신용가능, `57` = 당사 증거금률 100.
    (KIS H0STMKO0 `ISCD_STAT_CLS_CODE` 값 표 — `docs/kis/domestic-stock-realtime.md` KRX 절)
    """
    event = MarketOpEvent(
        ticker="100840", trht_yn="N", tr_susp_reas_cntt="(null)",
        mkop_cls_code="AB1", antc_mkop_cls_code="112",
        mrkt_trtm_cls_code="", divi_app_cls_code="",
        iscd_stat_cls_code=iscd_stat, vi_cls_code="N", ovtm_vi_cls_code="",
        exch_cls_code="", received_at=datetime.now(KST),
    )
    mom.record_market_op_event(event)
    assert mom.is_ticker_stale_excluded("100840") is False


def test_C5_halt_status_58_still_excluded_control() -> None:
    """대조군(수정 전후 초록) — 58 = 거래정지 지정 종목은 stale 회피 대상이다(수명 600초 안에서, cycle368)."""
    event = MarketOpEvent(
        ticker="100840", trht_yn="N", tr_susp_reas_cntt="",
        mkop_cls_code="", antc_mkop_cls_code="",
        mrkt_trtm_cls_code="", divi_app_cls_code="",
        iscd_stat_cls_code="58", vi_cls_code="N", ovtm_vi_cls_code="",
        exch_cls_code="", received_at=datetime.now(KST),
    )
    mom.record_market_op_event(event)
    assert mom.is_ticker_stale_excluded("100840") is True


# ===========================================================================
# D. 수신부터 끝까지 — raw 프레임 → websocket → handler → parser → monitor
# ===========================================================================
@pytest.mark.asyncio
async def test_D1_raw_frame_end_to_end_does_not_mark_held_ticker_stale_excluded() -> None:
    """운영 경로 그대로: `0|H0UNMKO0|001|<frame>` 한 줄이 보유 종목을 재구독 안전망에서 빼면 안 된다."""
    from src.realtime.websocket import KisWebSocket

    ws = KisWebSocket()
    ws._on_message = handler.dispatch_message
    await ws._handle_raw("0|H0UNMKO0|001|" + FRAME_100840_0922)

    assert mom.get_last_event("100840") is not None        # 수신은 됐다(하네스 확인)
    assert mom.is_ticker_stale_excluded("100840") is False


@pytest.mark.asyncio
async def test_D2_board_callback_receives_real_mkop_code() -> None:
    """`_on_board` 에 넘기는 장운영 코드는 [3] 이다. cycle368 이전에는 [2](거래정지 사유 `(null)`)가 갔다.

    수정 위치가 `src/realtime/handler.py` = **8영역**이다 — 2026-09-25 사용자 승인(cycle368).
    handler 는 칸을 직접 세지 않고 파싱된 `event.mkop_cls_code` 를 넘긴다(칸 계산 한 곳).
    세션 행위 영향은 **조건부로 0** 이다 — 라이브 종목별 MKOP 가 `AB1` 인 동안(2026-09-21~23 실측
    17/17 프레임)은 `session.is_call_auction_now` 가 110/121 에만 반응하므로 고쳐도 같은 분기다(메모 §4,
    증명은 cycle368 파일 H4). KIS 가 종목별 프레임에 110/121 을 실어 보내면 cycle182 가 설계한 그
    코드 분기가 그날부터 실제로 켜진다(cycle368 파일 I4).
    """
    captured: list[tuple[str, str, str]] = []

    async def _capture(tr_key: str, mkop: str, payload: str) -> None:
        captured.append((tr_key, mkop, payload))

    handler.register_board_handler(_capture)
    await handler._handle_market_op("H0UNMKO0", "100840", FRAME_100840_0922)

    assert captured and captured[0][1] == "AB1", captured


# ===========================================================================
# E. 재구독 안전망 — 보유(HIGH) 종목이 stale 이면 5분 우선 재구독이 그 종목을 다시 등록해야 한다
# ===========================================================================
def _make_scheduler_with_held(ticker: str, monkeypatch):
    from src.engine import scheduler as sch_mod
    from src.engine.scheduler import TradingScheduler
    import src.engine.scanner as scanner_mod
    import src.realtime.websocket_pool as wp_mod

    sched = TradingScheduler.__new__(TradingScheduler)
    sched._stale_retry_count = {}
    sched._stale_last_resubscribe_at = {}
    sched._pending_next_day_clear = set()
    sched._running = True

    strategy = MagicMock()
    strategy.state.positions = {ticker: object()}
    sched.registry = MagicMock()
    sched.registry.all = MagicMock(return_value=[strategy])

    old = datetime.now(KST) - timedelta(seconds=600)
    monkeypatch.setattr(scanner_mod, "ticker_last_tick", {ticker: old})

    pool_mock = MagicMock()
    pool_mock.subscribe = AsyncMock(return_value="main")
    pool_mock.unsubscribe_in_pool = AsyncMock(return_value=None)
    pool_mock.get_subscribed_tickers = MagicMock(return_value={ticker})
    pool_mock._ticker_to_tr_id = {ticker: "H0STCNT0"}
    monkeypatch.setattr(wp_mod, "kis_ws_pool", pool_mock)

    async def _wl(*a, **kw):
        return None
    monkeypatch.setattr(sch_mod, "write_log", _wl)
    return sched, pool_mock


@pytest.mark.asyncio
async def test_E1_control_held_stale_ticker_is_resubscribed(monkeypatch) -> None:
    """대조군(수정 전후 초록) — 장운영 프레임이 없으면 stale 보유 종목은 HIGH 로 재구독된다.

    이 하네스가 초록이었기에 cycle368 이전 E2 의 실패가 「하네스 고장」이 아니라 「가짜 VI skip」 때문임이 섰다.
    """
    sched, pool = _make_scheduler_with_held("100840", monkeypatch)
    resubscribed = await sched._resubscribe_stale_priority(cap=10)
    assert resubscribed == ["100840"]
    kwargs = pool.subscribe.await_args.kwargs
    assert kwargs["priority"] == "HIGH" and kwargs["bypass_limit"] is True


@pytest.mark.asyncio
async def test_E2_live_frame_does_not_block_held_ticker_resubscribe(monkeypatch) -> None:
    """운영 사고 재현 — 09-22 100840: 11:13 프레임 1건 뒤 15:31~19:40 재구독 skip 36회.

    VI 도 거래정지도 아닌 프레임(신용가능 55)을 받은 보유 종목이 stale 이면 재구독돼야 한다
    (cycle368 이전 코드에서는 붉었다).
    """
    sched, _pool = _make_scheduler_with_held("100840", monkeypatch)
    mom.record_market_op_event(parse_market_op_payload("100840", FRAME_100840_0922))

    resubscribed = await sched._resubscribe_stale_priority(cap=10)
    assert resubscribed == ["100840"], (
        f"보유 종목 재구독 skip — vi={sorted(mom.get_vi_active_tickers())} "
        f"halt={sorted(mom.get_halt_active_tickers())}"
    )
