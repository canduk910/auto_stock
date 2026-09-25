"""cycle368 (2026-09-25) — 장운영정보(`H0UNMKO0`) 사용자 결정 4건 Red.

cycle359 가 찾은 결함(라이브 프레임 첫 칸 = 종목코드인데 파서가 `TRHT_YN` 으로 읽어
모든 칸이 한 칸씩 밀림)의 수정 사이클이다. 칸 배치 자체의 Red 는
`test_cycle359_mkop_field_offset.py` 에 있고, 이 파일은 **2026-09-25 사용자 결정**을 고정한다.

| 묶음 | 결정 | 무엇을 막나 |
|---|---|---|
| P | 칸 기준점 = `fields[0] in ("Y","N")` 이면 문서 모양, 아니면 라이브 모양 | 판별자를 `tr_key == fields[0]`·`startswith`·길이로 바꾸는 것 |
| S | 거래정지 판정 = 종목상태 **`58` 하나** + `trht_yn=="Y"` | 51·55·57·59·00 을 정지로 읽는 두 번째 덫 |
| V | VI 활성은 마지막 `Y` 프레임 뒤 **600초**에 자동 해제(해제 프레임이 안 와도) | 해제 프레임 누락 → 그날 21:30 까지 재구독 안전망 밖 |
| D | 요약 `iscd_stat_active_count` = 표시 집합 {51,52,53,54,58,59} | 55·57·00 을 「종목상태 이상」으로 세는 것 |
| H | handler 는 파싱된 `event.mkop_cls_code` 를 넘긴다(칸 계산은 파서 한 곳) — **8영역, 사용자 승인** | `fields[2]`(거래정지 사유)를 장운영 코드로 넘기는 것 · 세션 행위 변화 |
| E | 보유 종목 stale 재구독 안전망(K watcher 120초 · 5분 우선) 회복 | 가짜 VI 로 보유 종목이 재구독에서 빠지는 운영 사고 |

**적대적 검토 뒤 메인 세션 결정 F1~F4 (사용자 승인 범위 안)**

| 묶음 | 결정 | 무엇을 막나 |
|---|---|---|
| I (F1) | handler 의 두 import 는 각자의 try **안**에 둔다(HEAD 도 import 가 try 안이었다 — 그 격리 유지) — import 실패도 흡수하고 보드 콜백은 항상 부른다 | 모듈 import 실패가 `_handle_market_op` 밖으로 새어 보드 전환까지 죽는 것 |
| L (F2) | 거래정지도 VI 와 같은 수명 원칙 — 마지막 정지 프레임 뒤 **600초** 자동 해제(VI 타이머와 별개 dict). 시각 없이 활성 집합에 있는 종목은 발견 시각을 찍고 600초 뒤 푼다(T 묶음) | 해제 프레임이 안 온 정지 종목이 그날 21:30 까지 재구독 안전망 밖에 남는 것 |
| R (F3) | `record_market_op_event` 첫머리에서 만료 sweep — 만료 뒤 새 활성 프레임은 새 에피소드 | 만료된 에피소드의 TTL 해제 로그 누락 · 새 활성 로그 누락 |
| N (F4) | KIS null 토큰 `(null)` = 빈 값 — VI 칸 비활성, 정지 사유 칸 `""` 정규화 | `(null)` 을 VI 활성으로 · 정지 사유 표본에 `(null)` |

⚠️ V8·V9 는 거래정지 수명(F2)을 전제로 한다 — 정지도 600초 뒤 풀린다.

**범위 밖**(cycle369, 도메인 자문 선행): 종목상태 51·59 보유 종목 청산·신규매수 차단. 여기서 만들지 않는다.

시계: VI 수명 테스트는 `freezegun.freeze_time` 으로 시각을 옮긴다(벽시계 의존 0). 비동기
테스트는 `real_asyncio=True` 로 이벤트 루프 시계를 건드리지 않는다. 구현이 `datetime.now`·
`time.time`·`time.monotonic`·`event.received_at` 중 무엇을 쓰든 같은 결과가 나오도록 이벤트도
얼린 시각 안에서 만든다.

자문·조사 메모: `_workspace/domain_consult/cycle359_mkop_field_offset.md` §5~§8
"""

from __future__ import annotations

import ast
import logging
import sys
import types
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from freezegun import freeze_time

import src.api.market_operation as mo
from src.api.market_operation import MarketOpEvent, is_event_blocking, parse_market_op_payload
from src.engine import market_operation_monitor as mom
from src.realtime import handler

pytestmark = pytest.mark.unit

KST = timezone(timedelta(hours=9))
_REPO = Path(__file__).resolve().parents[3]
_MON_LOGGER = "src.engine.market_operation_monitor"
_RELEASE_PREFIX = "[market_op_vi_release] "

#: 휴장 직후 첫 영업일 장중 — 동시호가·애프터 창 밖(시각 게이트 영향 0).
T0 = datetime(2026, 9, 28, 10, 0, 0, tzinfo=KST)

# 라이브 프레임 원문 (EC2 로그 verbatim — cycle359 메모 §3.1)
FRAME_100840_LIVE = "100840^N^(null)^AB1^112^^^55^N^"
FRAME_003160_VI_ON = "003160^N^(null)^AB1^311^^^55^Y^"

#: 종목상태 값 표 (KIS H0STMKO0 `ISCD_STAT_CLS_CODE` — docs/kis/domestic-stock-realtime.md KRX 절)
#: 51 관리 · 52 투자위험 · 53 투자경고 · 54 투자주의 · 55 신용가능 · 57 증거금100% · 58 거래정지 · 59 단기과열 · 00 그 외
_NOT_HALT_CODES = ["51", "52", "53", "54", "55", "57", "59", "00", "0", ""]
_DISPLAY_CODES = ["51", "52", "53", "54", "58", "59"]
_NON_DISPLAY_CODES = ["55", "57", "00", "0", ""]


def _event(
    ticker: str,
    *,
    trht_yn: str = "N",
    iscd: str = "",
    vi: str = "N",
    ovtm_vi: str = "",
    reason: str = "",
    mkop: str = "AB1",
) -> MarketOpEvent:
    """파싱을 거치지 않은 이벤트. `received_at` 은 호출 시점(얼린 시각 안이면 얼린 시각).

    종목상태 기본값은 빈칸이다 — 수정 전 코드도 빈칸은 「이상」으로 안 읽으므로, V 묶음(VI 수명)이
    두 번째 덫(00/55 → 가짜 정지)이 아니라 **수명 규칙 하나 때문에만** 붉어진다. 00·55 등은 S 묶음이 본다.
    """
    return MarketOpEvent(
        ticker=ticker, trht_yn=trht_yn, tr_susp_reas_cntt=reason,
        mkop_cls_code=mkop, antc_mkop_cls_code="112",
        mrkt_trtm_cls_code="", divi_app_cls_code="",
        iscd_stat_cls_code=iscd, vi_cls_code=vi, ovtm_vi_cls_code=ovtm_vi,
        exch_cls_code="", received_at=datetime.now(KST),
    )


def _release_records(caplog, ticker: str) -> list[logging.LogRecord]:
    """`[market_op_vi_release] ticker=<t>` INFO 행만 — 레벨·로거·prefix 로 한정(CI 루트 DEBUG 대비)."""
    head = f"{_RELEASE_PREFIX}ticker={ticker}"
    out = []
    for r in caplog.records:
        if r.name != _MON_LOGGER or r.levelno != logging.INFO:
            continue
        msg = r.getMessage()
        if msg == head or msg.startswith(head + " "):
            out.append(r)
    return out


@pytest.fixture(autouse=True)
def _reset_state():
    mom.reset_market_op_state()
    saved_board = handler._on_board
    handler._on_board = None
    yield
    mom.reset_market_op_state()
    handler._on_board = saved_board


# ===========================================================================
# P. 칸 기준점 — 두 모양을 값으로 가른다
# ===========================================================================
def test_P1_document_shape_keeps_original_layout() -> None:
    """가드(수정 전후 초록) — 문서 모양(종목코드 없음, [0]=TRHT_YN)은 종전 배치 그대로.

    [2]≠[3] 인 프레임을 써서 handler/파서가 [3] 을 읽는 변이까지 잡는다.
    """
    e = parse_market_op_payload("005930", "N^^121^112^0^0^0^0^0^KRX")
    assert (e.trht_yn, e.mkop_cls_code, e.antc_mkop_cls_code, e.exch_cls_code) == (
        "N", "121", "112", "KRX",
    )


def test_P2_document_shape_even_when_tr_key_equals_first_field() -> None:
    """가드 — 판별자는 `tr_key == fields[0]` 이 아니다(메모 §6 M-1).

    websocket 은 `tr_key = payload.split("^")[0]` 로 뽑으므로 운영 경로에서는 그 등식이
    **항상 참**이다. 문서 모양 프레임이 그 경로로 오면 `tr_key="N"` 이 되고, 등식 판별자는
    이것을 라이브 모양으로 오판해 한 칸 밀린다.
    """
    e = parse_market_op_payload("N", "N^^110^110^0^0^0^1^0^KRX")
    assert (e.trht_yn, e.mkop_cls_code, e.vi_cls_code, e.exch_cls_code) == ("N", "110", "1", "KRX")


@pytest.mark.parametrize("synthetic_ticker", ["N00001", "Y12345"])
def test_P3_ticker_starting_with_y_or_n_is_still_live_shape(synthetic_ticker: str) -> None:
    """판별은 **칸 전체가 정확히** `Y`/`N` 인가다 — 접두 비교(`startswith`)면 밀린다.

    ⚠️ 합성 종목코드다(현재 상장 코드에는 없음). 판별 규칙의 경계만 고정한다.
    """
    e = parse_market_op_payload(synthetic_ticker, f"{synthetic_ticker}^N^(null)^AB1^112^^^55^N^")
    assert (e.trht_yn, e.mkop_cls_code, e.iscd_stat_cls_code, e.vi_cls_code) == ("N", "AB1", "55", "N")


def test_P4_live_shape_with_exchange_column_maps_exch() -> None:
    """KRX/NXT 표 모양(11칸, 끝 `EXCH_CLS_CODE`)이 오면 거래소 칸이 제자리에 들어간다.

    라이브 통합 프레임은 10칸(끝 칸 없음)이었다 — 11칸이 와도 밀리지 않는지 고정한다.
    """
    e = parse_market_op_payload("100840", "100840^N^(null)^AB1^112^^^55^N^^KRX")
    assert (e.iscd_stat_cls_code, e.vi_cls_code, e.ovtm_vi_cls_code, e.exch_cls_code) == (
        "55", "N", "", "KRX",
    )


# ===========================================================================
# S. 거래정지 판정 = 종목상태 58 하나 + TRHT_YN=Y
# ===========================================================================
def test_S1_blocking_set_is_exactly_58() -> None:
    blocking = getattr(mo, "ISCD_STAT_BLOCKING", None)
    assert blocking == frozenset({"58"}), f"ISCD_STAT_BLOCKING={blocking!r} — 사용자 결정은 {{'58'}} 하나"


@pytest.mark.parametrize(
    "code, expected",
    [("58", True)] + [(c, False) for c in _NOT_HALT_CODES] + [(None, False)],
)
def test_S2_is_iscd_stat_blocking(code, expected: bool) -> None:
    fn = getattr(mo, "is_iscd_stat_blocking", None)
    assert callable(fn), "src.api.market_operation.is_iscd_stat_blocking 부재"
    assert fn(code) is expected, f"is_iscd_stat_blocking({code!r}) != {expected}"


@pytest.mark.parametrize("code", _NOT_HALT_CODES)
def test_S3_non_58_status_is_neither_halt_nor_excluded(code: str) -> None:
    """51(관리)·59(단기과열) 포함 — 정지로 읽지 않는다. 이들의 청산/매수차단은 cycle369 범위."""
    mom.record_market_op_event(_event("100840", iscd=code))
    assert "100840" not in mom.get_halt_active_tickers()
    assert mom.is_ticker_stale_excluded("100840") is False
    assert is_event_blocking(_event("100840", iscd=code)) is False


def test_S4_status_58_is_halt() -> None:
    mom.record_market_op_event(_event("100840", iscd="58"))
    assert "100840" in mom.get_halt_active_tickers()
    assert mom.is_ticker_stale_excluded("100840") is True
    assert is_event_blocking(_event("100840", iscd="58")) is True


def test_S5_trht_yn_y_is_halt_even_with_normal_status() -> None:
    """`TRHT_YN=Y` 는 종목상태와 무관하게 거래정지 — 라이브 모양 합성 프레임으로 파서까지 통과."""
    e = parse_market_op_payload("005930", "005930^Y^매매거래정지^AB1^112^^^00^N^")
    assert e.trht_yn == "Y"
    mom.record_market_op_event(e)
    assert "005930" in mom.get_halt_active_tickers()
    assert "005930" not in mom.get_vi_active_tickers()
    assert is_event_blocking(e) is True


def test_S6_halt_58_released_by_normal_status_frame() -> None:
    mom.record_market_op_event(_event("100840", iscd="58"))
    mom.record_market_op_event(_event("100840", iscd="55"))
    assert "100840" not in mom.get_halt_active_tickers()
    assert mom.is_ticker_stale_excluded("100840") is False


def test_S7_five_held_tickers_with_55_do_not_raise_circuit_breaker() -> None:
    """메모 §7-1 — 칸만 고치면 보유 5종목이 55 프레임을 받는 날 halt 비율 100% → 가짜 CB 의심."""
    for i in range(6):
        mom.record_market_op_event(_event(f"{100000 + i:06d}", iscd="55"))
    state = mom.get_circuit_breaker_state()
    assert state["halted"] == 0 and state["suspected"] is False, state


# ===========================================================================
# V. VI 수명 — 마지막 Y 뒤 600초 자동 해제
# ===========================================================================
@pytest.mark.parametrize("field", ["vi", "ovtm_vi"])
def test_V1_vi_expires_600s_after_last_active_frame(field: str) -> None:
    with freeze_time(T0) as frozen:
        mom.record_market_op_event(_event("003160", **{field: "Y"}))
        assert mom.is_ticker_stale_excluded("003160") is True

        frozen.move_to(T0 + timedelta(seconds=599))
        assert mom.is_ticker_stale_excluded("003160") is True, "600초 전에 풀렸다"
        assert "003160" in mom.get_vi_active_tickers()

        frozen.move_to(T0 + timedelta(seconds=600))
        assert mom.is_ticker_stale_excluded("003160") is False, "600초가 지나도 VI 가 안 풀린다"
        assert "003160" not in mom.get_vi_active_tickers()
        assert "003160" not in mom.get_market_op_active_tickers()


def test_V2_second_active_frame_refreshes_lifetime() -> None:
    """마지막 Y 기준 — 두 번째 Y(t0+300)가 수명을 t0+900 으로 늘린다(첫 Y 기준이면 t0+600 에 풀림)."""
    with freeze_time(T0) as frozen:
        mom.record_market_op_event(_event("003160", vi="Y"))
        frozen.move_to(T0 + timedelta(seconds=300))
        mom.record_market_op_event(_event("003160", vi="Y"))

        frozen.move_to(T0 + timedelta(seconds=800))
        assert mom.is_ticker_stale_excluded("003160") is True, "두 번째 Y 가 수명을 갱신하지 않았다"
        frozen.move_to(T0 + timedelta(seconds=899))
        assert mom.is_ticker_stale_excluded("003160") is True
        frozen.move_to(T0 + timedelta(seconds=900))
        assert mom.is_ticker_stale_excluded("003160") is False


def test_V3_release_frame_releases_immediately_and_no_ttl_log_later(caplog) -> None:
    caplog.set_level(logging.INFO, logger=_MON_LOGGER)
    with freeze_time(T0) as frozen:
        mom.record_market_op_event(_event("003160", vi="Y"))
        frozen.move_to(T0 + timedelta(seconds=60))
        mom.record_market_op_event(_event("003160", vi="N"))
        assert mom.is_ticker_stale_excluded("003160") is False

        frozen.move_to(T0 + timedelta(seconds=700))
        assert mom.is_ticker_stale_excluded("003160") is False
        mom.get_market_op_state_summary()

    recs = _release_records(caplog, "003160")
    assert len(recs) == 1, [r.getMessage() for r in recs]
    assert "reason=ttl" not in recs[0].getMessage(), "프레임 해제를 TTL 해제로 기록했다"


def test_V4_reactivation_after_release_starts_new_lifetime() -> None:
    """Y(t0) → N(t0+60) → Y(t0+500): 새 수명은 t0+1100 까지. 첫 Y 시각을 남겨 두면(setdefault) 즉시 풀린다."""
    with freeze_time(T0) as frozen:
        mom.record_market_op_event(_event("003160", vi="Y"))
        frozen.move_to(T0 + timedelta(seconds=60))
        mom.record_market_op_event(_event("003160", vi="N"))
        frozen.move_to(T0 + timedelta(seconds=500))
        mom.record_market_op_event(_event("003160", vi="Y"))

        frozen.move_to(T0 + timedelta(seconds=1000))
        assert mom.is_ticker_stale_excluded("003160") is True
        frozen.move_to(T0 + timedelta(seconds=1100))
        assert mom.is_ticker_stale_excluded("003160") is False


def test_V5_lifetime_is_per_ticker() -> None:
    with freeze_time(T0) as frozen:
        mom.record_market_op_event(_event("003160", vi="Y"))
        frozen.move_to(T0 + timedelta(seconds=300))
        mom.record_market_op_event(_event("078350", vi="Y"))

        frozen.move_to(T0 + timedelta(seconds=600))
        assert mom.is_ticker_stale_excluded("003160") is False
        assert mom.is_ticker_stale_excluded("078350") is True, "다른 종목의 Y 에 수명이 묶였다"
        frozen.move_to(T0 + timedelta(seconds=900))
        assert mom.is_ticker_stale_excluded("078350") is False


def test_V6_ttl_release_logged_once_with_reason(caplog) -> None:
    caplog.set_level(logging.INFO, logger=_MON_LOGGER)
    with freeze_time(T0) as frozen:
        mom.record_market_op_event(_event("003160", vi="Y"))
        frozen.move_to(T0 + timedelta(seconds=599))
        mom.is_ticker_stale_excluded("003160")
        assert _release_records(caplog, "003160") == [], "만료 전에 해제 로그"

        frozen.move_to(T0 + timedelta(seconds=601))
        for _ in range(3):
            mom.is_ticker_stale_excluded("003160")
        mom.get_vi_active_tickers()
        mom.get_market_op_state_summary()
        mom.get_market_op_active_tickers()

    recs = _release_records(caplog, "003160")
    assert len(recs) == 1, f"TTL 해제 로그 {len(recs)}행 — 1행이어야 한다"
    assert "reason=ttl" in recs[0].getMessage(), recs[0].getMessage()


def test_V7_summary_stops_counting_expired_vi() -> None:
    with freeze_time(T0) as frozen:
        mom.record_market_op_event(_event("003160", vi="Y"))
        s = mom.get_market_op_state_summary()
        assert s["vi_active_count"] == 1 and "003160" in s["vi_active_sample"]

        frozen.move_to(T0 + timedelta(seconds=600))
        s = mom.get_market_op_state_summary()
        assert s["vi_active_count"] == 0, s
        assert "003160" not in s["vi_active_sample"]


@pytest.mark.asyncio
async def test_V8_route_details_drop_expired_vi_and_expired_halt() -> None:
    """RealtimeHealth 카드 경로 — 만료된 VI·거래정지는 「활성」으로 표시되지 않는다.

    거래정지도 마지막 정지 프레임 뒤 600초 수명이다(F2) — 정지를 t0+300 에 기록해 t0+600 에는
    VI 만 만료·정지는 유지, t0+900 에는 둘 다 사라짐을 본다.
    """
    from src.routes.realtime import get_market_operation

    with freeze_time(T0, real_asyncio=True) as frozen:
        mom.record_market_op_event(_event("003160", vi="Y"))
        frozen.move_to(T0 + timedelta(seconds=300))
        mom.record_market_op_event(_event("000020", iscd="58"))

        frozen.move_to(T0 + timedelta(seconds=600))
        resp = await get_market_operation()

        frozen.move_to(T0 + timedelta(seconds=900))
        resp_late = await get_market_operation()

    tickers = [row["ticker"] for row in resp.data["details"]]
    assert tickers == ["000020"], tickers
    assert resp.data["vi_active_count"] == 0
    assert resp.data["halt_active_count"] == 1

    assert resp_late.data["details"] == [], resp_late.data["details"]
    assert resp_late.data["halt_active_count"] == 0, "정지 프레임 뒤 600초가 지나도 정지 표시가 남는다"


@pytest.mark.parametrize(
    "reader",
    ["is_ticker_stale_excluded", "get_vi_active_tickers", "get_market_op_active_tickers", "summary"],
)
def test_V12_every_reader_sees_expiry_on_its_own(reader: str) -> None:
    """만료 뒤 **첫 조회**가 어느 읽기 함수든 만료를 반영한다(지연 평가가 한 함수에만 걸린 변이 차단).

    V1·V7 은 여러 함수를 차례로 불러 앞선 호출이 만료를 대신 처리해 줄 수 있다 — 여기선 하나만 부른다.
    """
    with freeze_time(T0) as frozen:
        mom.record_market_op_event(_event("003160", vi="Y"))
        frozen.move_to(T0 + timedelta(seconds=600))
        if reader == "is_ticker_stale_excluded":
            assert mom.is_ticker_stale_excluded("003160") is False
        elif reader == "get_vi_active_tickers":
            assert "003160" not in mom.get_vi_active_tickers()
        elif reader == "get_market_op_active_tickers":
            assert "003160" not in mom.get_market_op_active_tickers()
        else:
            s = mom.get_market_op_state_summary()
            assert s["vi_active_count"] == 0 and "003160" not in s["vi_active_sample"], s


def test_V9_halt_has_the_same_lifetime() -> None:
    """메인 세션 결정(F2): 거래정지도 VI 와 같은 수명 원칙(마지막 정지 프레임 뒤 600초). 근거 = 600초 뒤의
    행위는 cycle368 이전과 같다(라이브 프레임으로 정지가 발화한 적이 없었다) — 그래서 더 안전한 쪽으로만
    움직이고, 진짜 정지 종목은 상한 걸린 stale 재구독 SEND 를 다시 받을 뿐이다. 경계는 L 묶음이 본다.
    """
    with freeze_time(T0) as frozen:
        mom.record_market_op_event(_event("000020", iscd="58"))
        frozen.move_to(T0 + timedelta(seconds=3600))
        assert "000020" not in mom.get_halt_active_tickers(), "정지가 해제 프레임 없이 1시간째 유지"
        assert mom.is_ticker_stale_excluded("000020") is False


def test_V10_live_vi_frame_through_parser_expires() -> None:
    """라이브 프레임 원문(09-21 003160, [8]=Y) → 파서 → 모니터 → 600초 뒤 해제."""
    with freeze_time(T0) as frozen:
        mom.record_market_op_event(parse_market_op_payload("003160", FRAME_003160_VI_ON))
        assert mom.is_ticker_stale_excluded("003160") is True
        frozen.move_to(T0 + timedelta(seconds=600))
        assert mom.is_ticker_stale_excluded("003160") is False


def test_V11_rest_seed_also_expires_600s_after_seed() -> None:
    """⚠️ 해석 항목 — 부팅 REST 시드(`seed_vi_active_from_rest`)도 해제 프레임 없는 VI 다.

    시드는 「오늘 VI 가 있었던」 종목 목록이라 장중 재기동이면 이미 풀린 종목까지 들어온다.
    수명을 안 주면 그 보유 종목이 그날 21:30 까지 재구독 안전망 밖에 남는다(이번 결함과 같은 모양).
    시드 시각을 마지막 활성 시각으로 본다. 결정에서 빼기로 하면 이 테스트만 지운다.
    """
    with freeze_time(T0) as frozen:
        mom.seed_vi_active_from_rest({"003160"})
        frozen.move_to(T0 + timedelta(seconds=599))
        assert mom.is_ticker_stale_excluded("003160") is True
        frozen.move_to(T0 + timedelta(seconds=600))
        assert mom.is_ticker_stale_excluded("003160") is False


# ===========================================================================
# D. 요약 집계 — 표시 집합 {51,52,53,54,58,59}
# ===========================================================================
def test_D1_iscd_stat_active_count_uses_display_set() -> None:
    for i, code in enumerate(_DISPLAY_CODES + _NON_DISPLAY_CODES):
        mom.record_market_op_event(_event(f"{200000 + i:06d}", iscd=code))
    s = mom.get_market_op_state_summary()
    assert s["iscd_stat_active_count"] == len(_DISPLAY_CODES), (
        f"count={s['iscd_stat_active_count']} — 55/57/00 을 세면 안 된다"
    )


@pytest.mark.parametrize("code", _DISPLAY_CODES)
def test_D2_each_display_code_counts_alone(code: str) -> None:
    mom.record_market_op_event(_event("100840", iscd=code))
    assert mom.get_market_op_state_summary()["iscd_stat_active_count"] == 1


@pytest.mark.parametrize("code", _NON_DISPLAY_CODES)
def test_D3_non_display_code_counts_zero(code: str) -> None:
    mom.record_market_op_event(_event("100840", iscd=code))
    assert mom.get_market_op_state_summary()["iscd_stat_active_count"] == 0


# ===========================================================================
# H. handler — 파싱된 이벤트의 장운영 코드를 넘긴다 (8영역, 2026-09-25 사용자 승인)
# ===========================================================================
@pytest.mark.asyncio
async def test_H1_session_callback_receives_parsed_mkop_code_from_live_frame() -> None:
    from src.engine.session import SessionTracker

    tracker = SessionTracker()
    handler.register_board_handler(tracker.on_h0nxmko0)
    await handler._handle_market_op("H0UNMKO0", "100840", FRAME_100840_LIVE)
    assert tracker.last_nxt_mkop_code == "AB1", f"got {tracker.last_nxt_mkop_code!r}"


@pytest.mark.asyncio
async def test_H2_document_shape_frame_still_delivers_its_mkop_code() -> None:
    """가드 — 문서 모양 합성 프레임은 종전대로 [2] 가 코드다. [2]≠[3] 으로 [3] 오독 변이를 잡는다."""
    captured: list[tuple[str, str, str]] = []

    async def _capture(tr_key: str, mkop: str, payload: str) -> None:
        captured.append((tr_key, mkop, payload))

    handler.register_board_handler(_capture)
    payload = "N^^121^112^0^0^0^0^0^KRX"
    await handler._handle_market_op("H0UNMKO0", "005930", payload)
    assert captured == [("005930", "121", payload)], captured


@pytest.mark.asyncio
async def test_H3_record_receives_correctly_parsed_live_event(monkeypatch) -> None:
    got: list[MarketOpEvent] = []
    monkeypatch.setattr(mom, "record_market_op_event", lambda e: got.append(e))
    await handler._handle_market_op("H0UNMKO0", "100840", FRAME_100840_LIVE)

    assert len(got) == 1
    e = got[0]
    assert (e.ticker, e.trht_yn, e.mkop_cls_code, e.antc_mkop_cls_code,
            e.iscd_stat_cls_code, e.vi_cls_code) == ("100840", "N", "AB1", "112", "55", "N"), e


@pytest.mark.asyncio
async def test_H4_session_behaviour_unchanged_by_fix() -> None:
    """대조군(수정 전후 초록) — **라이브 종목별 코드가 `AB1` 인 동안** 행위 차이 0 의 증명.

    수정 전 세션이 받던 값 `(null)` 과 수정 후 받는 값 `AB1` 이 모든 시각에서 같은
    `is_call_auction_now` 를 낸다(세션은 110/121 에만 반응). 그리고 110 을 실은 프레임은
    여전히 110 창(08:25~09:05, 시간 폴백 밖인 08:27)에서 참을 낸다 = 코드 경로가 살아 있다.
    ⚠️ 그래서 KIS 가 종목별 프레임에 110/121 을 싣는 날에는 cycle182 가 설계한 코드 분기가
    **실제로 켜진다** — 그날부터는 「차이 0」이 아니다(F1 — handler docstring 이 이 조건을 적는다, I4 가 본다).
    """
    from src.engine.session import SessionTracker

    fixed = SessionTracker()
    handler.register_board_handler(fixed.on_h0nxmko0)
    await handler._handle_market_op("H0UNMKO0", "100840", FRAME_100840_LIVE)

    before = SessionTracker()
    await before.on_h0nxmko0("100840", "(null)", FRAME_100840_LIVE)

    day = datetime(2026, 9, 28, tzinfo=KST)
    for hh, mm in [(8, 0), (8, 27), (8, 45), (9, 2), (10, 0), (15, 17), (15, 25), (15, 32), (16, 30), (19, 59)]:
        t = day.replace(hour=hh, minute=mm)
        assert fixed.is_call_auction_now(t) == before.is_call_auction_now(t), f"{hh:02d}:{mm:02d} 에서 행위가 달라졌다"

    doc = SessionTracker()
    handler.register_board_handler(doc.on_h0nxmko0)
    await handler._handle_market_op("H0UNMKO0", "005930", "N^^110^110^0^0^0^0^0^KRX")
    assert doc.is_call_auction_now(day.replace(hour=8, minute=27)) is True


@pytest.mark.asyncio
async def test_H5_handler_log_carries_real_mkop_code(caplog) -> None:
    """운영 로그 `[H0UNMKO0] tr_key=…, mkop_cls_code=(null)` 이 틀렸던 값 — 바로잡힌다."""
    caplog.set_level(logging.INFO, logger="src.realtime.handler")
    await handler._handle_market_op("H0UNMKO0", "100840", FRAME_100840_LIVE)
    msgs = [
        r.getMessage() for r in caplog.records
        if r.name == "src.realtime.handler" and r.levelno == logging.INFO
        and r.getMessage().startswith("[H0UNMKO0] tr_key=100840,")
    ]
    assert len(msgs) == 1, msgs
    assert "mkop_cls_code=AB1," in msgs[0], msgs[0]


_PARSE_FAILED_PREFIX = "[market_op_parse_failed] "
_RECORD_FAILED_PREFIX = "[market_op_record_failed] "


def _handler_error_lines(caplog, prefix: str) -> list[str]:
    """handler 로거의 ERROR 이상 `<prefix>` 행만 — 레벨·로거·prefix 로 한정(CI 루트 DEBUG 대비)."""
    return [
        r.getMessage() for r in caplog.records
        if r.name == "src.realtime.handler" and r.levelno >= logging.ERROR
        and r.getMessage().startswith(prefix)
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("broken", ["parse", "record"])
async def test_H6_board_callback_survives_parse_or_record_failure(monkeypatch, caplog, broken: str) -> None:
    """가드(수정 전후 초록) — 파싱·기록이 터져도 보드 콜백은 불린다(cycle149 graceful 계약).

    handler 가 `event` 를 쓰게 되면서 파싱을 try 밖으로 빼는 변이를 잡는다.
    파싱이 깨지면 기록은 **불리지 않는다** — `record_market_op_event(None)` 을 부르는 변이(MF1h)는
    진짜 기록 함수가 `None.ticker` 에서 터져 `[market_op_record_failed]` 가 한 줄 더 생기는 것으로 드러난다.
    기록이 깨진 경우는 파싱이 멀쩡하므로 파싱 실패 로그가 0이다.
    """
    caplog.set_level(logging.INFO, logger="src.realtime.handler")

    def _boom(*_a, **_kw):
        raise RuntimeError("boom")

    if broken == "parse":
        monkeypatch.setattr(mo, "parse_market_op_payload", _boom)
    else:
        monkeypatch.setattr(mom, "record_market_op_event", _boom)

    calls: list[tuple[str, str, str]] = []

    async def _capture(tr_key: str, mkop: str, payload: str) -> None:
        calls.append((tr_key, mkop, payload))

    handler.register_board_handler(_capture)
    await handler._handle_market_op("H0UNMKO0", "100840", FRAME_100840_LIVE)
    assert len(calls) == 1 and calls[0][0] == "100840" and isinstance(calls[0][1], str), calls

    parse_failed = _handler_error_lines(caplog, _PARSE_FAILED_PREFIX)
    record_failed = _handler_error_lines(caplog, _RECORD_FAILED_PREFIX)
    if broken == "parse":
        assert len(parse_failed) == 1, parse_failed
        assert record_failed == [], f"파싱이 깨졌는데 기록을 불렀다(None 전달): {record_failed}"
        assert "100840" not in mom._market_op_last_event
    else:
        assert parse_failed == [], parse_failed
        assert len(record_failed) == 1, record_failed


def _handle_market_op_node() -> ast.AsyncFunctionDef:
    tree = ast.parse((_REPO / "src/realtime/handler.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "_handle_market_op":
            return node
    raise AssertionError("handler._handle_market_op 정의 소실")


def test_H7_handler_does_not_count_columns_itself() -> None:
    """칸 계산은 파서 한 곳(사용자 결정 「parsed event 사용」) — handler 본문에 `.split(` 호출 0,
    `parse_market_op_payload(` 호출 ≥1. 두 곳이 각자 칸을 세면 이번 결함처럼 한쪽만 고쳐진다.
    """
    fn = _handle_market_op_node()
    calls = [n for n in ast.walk(fn) if isinstance(n, ast.Call)]
    splits = [c.lineno for c in calls if isinstance(c.func, ast.Attribute) and c.func.attr == "split"]
    parses = [
        c.lineno for c in calls
        if (isinstance(c.func, ast.Name) and c.func.id == "parse_market_op_payload")
        or (isinstance(c.func, ast.Attribute) and c.func.attr == "parse_market_op_payload")
    ]
    assert splits == [], f"_handle_market_op 가 직접 split 한다 — 행 {splits}"
    assert parses, "_handle_market_op 가 parse_market_op_payload 를 부르지 않는다"


# ===========================================================================
# E. 재구독 안전망 — 보유 stale 종목
# ===========================================================================
def _held_scheduler(ticker: str, monkeypatch, *, stale_age_secs: int = 600):
    """보유 1종목·stale 상태의 최소 scheduler + pool mock (cycle359 E 하네스와 같은 모양)."""
    from src.engine import scheduler as sch_mod
    from src.engine.scheduler import TradingScheduler
    import src.engine.scanner as scanner_mod
    import src.realtime.websocket_pool as wp_mod

    sched = TradingScheduler.__new__(TradingScheduler)
    sched._stale_retry_count = {}
    sched._stale_last_resubscribe_at = {}
    sched._stale_force_retry_history = {}
    sched._pending_next_day_clear = set()
    sched._running = True

    strategy = MagicMock()
    strategy.state.positions = {ticker: MagicMock()}
    sched.registry = MagicMock()
    sched.registry.all = MagicMock(return_value=[strategy])

    monkeypatch.setattr(
        sch_mod, "kis_ws", MagicMock(get_subscribed_tickers=lambda: {ticker}), raising=False,
    )
    old = datetime.now(KST) - timedelta(seconds=stale_age_secs)
    monkeypatch.setattr(scanner_mod, "ticker_last_tick", {ticker: old})

    pool = MagicMock()
    pool.subscribe = AsyncMock(return_value="main")
    pool.unsubscribe_in_pool = AsyncMock(return_value=None)
    pool.get_subscribed_tickers = MagicMock(return_value={ticker})
    pool._ticker_to_tr_id = {ticker: "H0STCNT0"}
    monkeypatch.setattr(wp_mod, "kis_ws_pool", pool)

    async def _wl(*a, **kw):
        return None

    monkeypatch.setattr(sch_mod, "write_log", _wl)
    return sched, pool


def _assert_high_resubscribed(pool: MagicMock, ticker: str) -> None:
    assert pool.subscribe.await_count >= 1, "보유 stale 종목을 재구독하지 않았다"
    args = pool.subscribe.await_args
    assert args.args[1] == ticker
    assert args.kwargs["priority"] == "HIGH" and args.kwargs["bypass_limit"] is True


@pytest.mark.asyncio
async def test_E1_control_k_watcher_resubscribes_held_stale_ticker(monkeypatch) -> None:
    """대조군(수정 전후 초록) — 장운영 프레임이 없으면 K watcher 가 보유 stale 종목을 HIGH 로 재구독."""
    sched, pool = _held_scheduler("100840", monkeypatch)
    await sched._check_and_resubscribe_stale()
    _assert_high_resubscribed(pool, "100840")


@pytest.mark.asyncio
async def test_E2_k_watcher_resubscribes_held_ticker_after_status55_frame(monkeypatch) -> None:
    """09-22 100840 재현을 K watcher(120초) 경로로 — cycle359 E2 는 5분 우선 경로다.

    두 경로가 같은 `is_ticker_stale_excluded` 를 부르지만 운영 skip 258줄은 둘 다에서 났다.
    """
    sched, pool = _held_scheduler("100840", monkeypatch)
    mom.record_market_op_event(parse_market_op_payload("100840", FRAME_100840_LIVE))
    await sched._check_and_resubscribe_stale()
    _assert_high_resubscribed(pool, "100840")


@pytest.mark.asyncio
async def test_E3_priority_resubscribe_resumes_after_vi_lifetime(monkeypatch) -> None:
    """진짜 VI(Y) 뒤 해제 프레임이 없어도 600초가 지나면 5분 우선 재구독이 보유 종목을 되살린다."""
    with freeze_time(T0, real_asyncio=True) as frozen:
        sched, pool = _held_scheduler("003160", monkeypatch)
        mom.record_market_op_event(_event("003160", vi="Y"))

        frozen.move_to(T0 + timedelta(seconds=300))
        assert await sched._resubscribe_stale_priority(cap=10) == [], "VI 활성 중에는 skip 이 설계"

        frozen.move_to(T0 + timedelta(seconds=601))
        resubscribed = await sched._resubscribe_stale_priority(cap=10)

    assert resubscribed == ["003160"], f"VI 수명 만료 뒤에도 재구독 skip — {resubscribed}"
    _assert_high_resubscribed(pool, "003160")


@pytest.mark.asyncio
async def test_E4_priority_resubscribe_resumes_after_halt_lifetime(monkeypatch) -> None:
    """F2 의 행위 결과 — 보유 종목에 정지(58) 프레임 뒤 해제 프레임이 없어도 600초 뒤 재구독이 되살아난다.

    진짜 정지 종목이면 체결이 없어 stale 이 계속되고, 재구독은 상한(HIGH 300초 케이던스) 안에서만 다시 나간다
    — 메인 세션이 받아들인 비용이다.
    """
    with freeze_time(T0, real_asyncio=True) as frozen:
        sched, pool = _held_scheduler("000020", monkeypatch)
        mom.record_market_op_event(_event("000020", iscd="58"))

        frozen.move_to(T0 + timedelta(seconds=300))
        assert await sched._resubscribe_stale_priority(cap=10) == [], "정지 활성 중에는 skip 이 설계"

        frozen.move_to(T0 + timedelta(seconds=601))
        resubscribed = await sched._resubscribe_stale_priority(cap=10)

    assert resubscribed == ["000020"], f"정지 수명 만료 뒤에도 재구독 skip — {resubscribed}"
    _assert_high_resubscribed(pool, "000020")


async def _k_watcher_skips_until_lifetime_ends(monkeypatch, ticker: str, **frame) -> MagicMock:
    """K watcher(120초 주기) 경로 — 활성 프레임 뒤 599초엔 skip(SEND 0), 600초엔 HIGH 재구독."""
    with freeze_time(T0, real_asyncio=True) as frozen:
        sched, pool = _held_scheduler(ticker, monkeypatch)
        mom.record_market_op_event(_event(ticker, **frame))

        frozen.move_to(T0 + timedelta(seconds=599))
        await sched._check_and_resubscribe_stale()
        assert pool.subscribe.await_count == 0, "활성 중(599초)에는 skip 이 설계"

        frozen.move_to(T0 + timedelta(seconds=600))
        await sched._check_and_resubscribe_stale()
    return pool


@pytest.mark.asyncio
async def test_E5_k_watcher_resumes_held_ticker_after_vi_lifetime(monkeypatch) -> None:
    """E3 의 K watcher 판 — 5분 우선 경로와 120초 경로는 같은 판정을 부르지만 운영 skip 은 둘 다에서 났다."""
    pool = await _k_watcher_skips_until_lifetime_ends(monkeypatch, "003160", vi="Y")
    _assert_high_resubscribed(pool, "003160")


@pytest.mark.asyncio
async def test_E6_k_watcher_resumes_held_ticker_after_halt_lifetime(monkeypatch) -> None:
    """E4 의 K watcher 판 — 정지(58) 뒤 해제 프레임이 없어도 600초에 HIGH 재구독이 돌아온다."""
    pool = await _k_watcher_skips_until_lifetime_ends(monkeypatch, "000020", iscd="58")
    _assert_high_resubscribed(pool, "000020")


# ===========================================================================
# 공통 — 모니터 로그 행 추출 (묶음 L·R·T 가 쓴다)
# ===========================================================================
_VI_ACTIVE_PREFIX = "[market_op_vi_active] "
_HALT_ACTIVE_PREFIX = "[market_op_halt_active] "
_HALT_RELEASE_PREFIX = "[market_op_halt_release] "
_HANDLER_LOGGER = "src.realtime.handler"


def _mon_lines(caplog, prefix: str, ticker: str) -> list[str]:
    """모니터 로거의 `<prefix>ticker=<t>` 행(INFO 이상)만 — 로거·prefix·종목으로 한정(CI 루트 DEBUG 대비)."""
    head = f"{prefix}ticker={ticker}"
    out: list[str] = []
    for r in caplog.records:
        if r.name != _MON_LOGGER or r.levelno < logging.INFO:
            continue
        msg = r.getMessage()
        if msg == head or msg.startswith(head + " "):
            out.append(msg)
    return out


def _ttl(lines: list[str]) -> list[str]:
    return [m for m in lines if "reason=ttl" in m]


# ===========================================================================
# I. (F1) handler import 실패 격리 — 보드 콜백은 항상 불린다
# ===========================================================================
class _ExplodingModule(types.ModuleType):
    """`from <mod> import <name>` 의 속성 조회에서 RuntimeError — import 가 ImportError 가 아닌 예외로 깨지는 경우.

    그 밖의 이름(`__path__` 등 import 기계가 묻는 것)은 평범한 AttributeError 로 답해 import 기계는 정상 진행한다.
    """

    def __init__(self, name: str, target: str) -> None:
        super().__init__(name)
        self._target = target

    def __getattr__(self, attr: str):
        if attr == object.__getattribute__(self, "_target"):
            raise RuntimeError(f"boom on import of {attr}")
        raise AttributeError(attr)


_IMPORT_TARGETS = {
    # key: (sys.modules 키, from-import 이름, 콜백이 받아야 할 장운영 코드, 흡수 로그 마커)
    "parse": ("src.api.market_operation", "parse_market_op_payload", "", "[market_op_parse_failed] "),
    "record": ("src.engine.market_operation_monitor", "record_market_op_event", "AB1", "[market_op_record_failed] "),
}


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["module_missing", "attr_raises"])
@pytest.mark.parametrize("target", ["parse", "record"])
async def test_I1_import_failure_is_absorbed_and_board_callback_still_runs(
    monkeypatch, caplog, target: str, mode: str,
) -> None:
    """F1 — 파서 import 는 파싱 try 안, 기록 import 는 기록 try 안(HEAD 와 같은 격리 수준 유지).

    - `module_missing`: `sys.modules[mod] = None` → `ModuleNotFoundError`
    - `attr_raises`: 이름 조회에서 `RuntimeError` → except 를 `ImportError` 로 좁히는 변이까지 잡는다
    - `record` 가 깨져도 파싱은 산다 → 콜백은 **`AB1`** 을 받는다(두 import 를 한 try 에 묶는 변이 차단)
    - 흡수는 조용하지 않다 → 그 경로의 마커가 ERROR 1행
    - 다른 경로의 마커는 0행 — 파싱이 깨지면 기록은 불리지 않는다(`None` 을 넘기는 변이 MF1h 는
      기록 함수가 `None.ticker` 에서 터져 `[market_op_record_failed]` 가 생기는 것으로 드러난다)
    """
    mod_key, name, expected_code, marker = _IMPORT_TARGETS[target]
    replacement = None if mode == "module_missing" else _ExplodingModule(mod_key, name)
    monkeypatch.setitem(sys.modules, mod_key, replacement)
    caplog.set_level(logging.INFO, logger=_HANDLER_LOGGER)

    calls: list[tuple[str, str, str]] = []

    async def _capture(tr_key: str, mkop: str, payload: str) -> None:
        calls.append((tr_key, mkop, payload))

    handler.register_board_handler(_capture)
    try:
        await handler._handle_market_op("H0UNMKO0", "100840", FRAME_100840_LIVE)
    except Exception as exc:  # noqa: BLE001 — 새면 그것이 곧 결함
        pytest.fail(f"{target} import 실패가 _handle_market_op 밖으로 샜다: {exc!r}")

    assert calls == [("100840", expected_code, FRAME_100840_LIVE)], calls
    absorbed = _handler_error_lines(caplog, marker)
    assert len(absorbed) == 1, f"{marker.strip()} 흡수 로그 {len(absorbed)}행 — import 실패를 조용히 삼켰다"

    other = _RECORD_FAILED_PREFIX if target == "parse" else _PARSE_FAILED_PREFIX
    stray = _handler_error_lines(caplog, other)
    assert stray == [], f"{target} 만 깨졌는데 {other.strip()} 가 나왔다(파싱 실패 뒤 기록에 None 전달 등): {stray}"


@pytest.mark.asyncio
async def test_I2_record_import_failure_leaves_monitor_state_untouched(monkeypatch) -> None:
    """F1 — 기록 모듈 import 가 깨지면 상태 갱신은 없다(파싱만 된다). 콜백 이후 예외 0."""
    monkeypatch.setitem(sys.modules, "src.engine.market_operation_monitor", None)
    await handler._handle_market_op("H0UNMKO0", "003160", FRAME_003160_VI_ON)
    assert "003160" not in mom._vi_active_tickers
    assert "003160" not in mom._market_op_last_event


def test_I3_imports_live_inside_their_own_try() -> None:
    """F1 구조 가드 — 두 `from … import` 가 함수 최상위 문장이 아니라 각자 다른 `try` 본문 안에 있다.

    I1 은 행위로 잡고, 이 가드는 「두 import 를 한 try 에 넣는」 모양을 이름으로 못박는다.
    """
    fn = _handle_market_op_node()
    top_level_imports = [n.lineno for n in fn.body if isinstance(n, ast.ImportFrom)]
    assert top_level_imports == [], f"함수 최상위 import 가 남았다 — 행 {top_level_imports}"

    owner: dict[str, int] = {}
    for node in ast.walk(fn):
        if isinstance(node, ast.Try):
            for inner in ast.walk(ast.Module(body=node.body, type_ignores=[])):
                if isinstance(inner, ast.ImportFrom):
                    for alias in inner.names:
                        owner.setdefault(alias.name, id(node))
    assert "parse_market_op_payload" in owner, "parse_market_op_payload import 가 try 본문 안에 없다"
    assert "record_market_op_event" in owner, "record_market_op_event import 가 try 본문 안에 없다"
    assert owner["parse_market_op_payload"] != owner["record_market_op_event"], (
        "두 import 가 같은 try 에 있다 — 기록 모듈 실패가 파싱까지 죽인다"
    )


def test_I4_docstring_states_the_conditional_session_claim() -> None:
    """F1 문서 정정 가드 — 「세션 행위 영향 0」은 **라이브 종목별 코드가 AB1 인 동안**만 참이다.

    근거 수치(17/17 프레임, 2026-09-21~23)와 조건(KIS 가 110/121 을 실으면 cycle182 코드 분기가 켜진다)을
    docstring 이 함께 말해야 한다.
    """
    doc = ast.get_docstring(_handle_market_op_node()) or ""
    for token in ("AB1", "17/17", "110", "121", "cycle182", "is_call_auction_now"):
        assert token in doc, f"_handle_market_op docstring 에 {token!r} 없음 — 조건부 서술로 정정되지 않았다"


# ===========================================================================
# L. (F2) 거래정지 수명 — 마지막 정지 프레임 뒤 600초 자동 해제
# ===========================================================================
_HALT_CAUSES = {
    "iscd58": {"iscd": "58"},
    "trht_y": {"trht_yn": "Y"},
    "both": {"trht_yn": "Y", "iscd": "58"},
}


@pytest.mark.parametrize("cause", list(_HALT_CAUSES))
def test_L1_halt_expires_600s_after_last_halt_frame_and_logs_once(caplog, cause: str) -> None:
    """정지(58 · TRHT_YN=Y · 둘 다) → 599초까지 유지, 600초에 해제 + `reason=ttl` 1행(여러 읽기 함수에도 1행)."""
    caplog.set_level(logging.INFO, logger=_MON_LOGGER)
    with freeze_time(T0) as frozen:
        mom.record_market_op_event(_event("000020", **_HALT_CAUSES[cause]))
        assert mom.is_ticker_stale_excluded("000020") is True

        frozen.move_to(T0 + timedelta(seconds=599))
        assert mom.is_ticker_stale_excluded("000020") is True, "600초 전에 풀렸다"
        assert "000020" in mom.get_halt_active_tickers()
        assert _mon_lines(caplog, _HALT_RELEASE_PREFIX, "000020") == [], "만료 전에 해제 로그"

        frozen.move_to(T0 + timedelta(seconds=600))
        assert mom.is_ticker_stale_excluded("000020") is False, "정지 프레임 뒤 600초가 지나도 안 풀린다"
        assert "000020" not in mom.get_halt_active_tickers()
        assert "000020" not in mom.get_market_op_active_tickers()
        for _ in range(3):
            mom.is_ticker_stale_excluded("000020")
        mom.get_market_op_state_summary()
        mom.get_circuit_breaker_state()

    lines = _mon_lines(caplog, _HALT_RELEASE_PREFIX, "000020")
    assert len(lines) == 1, f"정지 TTL 해제 로그 {len(lines)}행 — 1행이어야 한다: {lines}"
    assert "reason=ttl" in lines[0], lines[0]


def test_L2_second_halt_frame_refreshes_lifetime() -> None:
    """마지막 정지 프레임 기준 — 두 번째 58(t0+300)이 수명을 t0+900 으로 늘린다."""
    with freeze_time(T0) as frozen:
        mom.record_market_op_event(_event("000020", iscd="58"))
        frozen.move_to(T0 + timedelta(seconds=300))
        mom.record_market_op_event(_event("000020", iscd="58"))

        frozen.move_to(T0 + timedelta(seconds=800))
        assert mom.is_ticker_stale_excluded("000020") is True, "두 번째 정지 프레임이 수명을 갱신하지 않았다"
        frozen.move_to(T0 + timedelta(seconds=899))
        assert mom.is_ticker_stale_excluded("000020") is True
        frozen.move_to(T0 + timedelta(seconds=900))
        assert mom.is_ticker_stale_excluded("000020") is False


@pytest.mark.parametrize(
    "first, second",
    [
        ({"trht_yn": "Y", "iscd": "58"}, {"trht_yn": "N", "iscd": "58"}),
        ({"trht_yn": "Y"}, {"trht_yn": "N", "iscd": "58"}),
        ({"iscd": "58"}, {"trht_yn": "Y"}),
    ],
    ids=["Y58_then_N58", "Y_then_N58", "58_then_Y"],
)
def test_L3_halt_frame_of_either_cause_refreshes(first: dict, second: dict) -> None:
    """검토자 시퀀스 — (TRHT Y, 58) 뒤 (TRHT N, 58): 58 이 남아 정지 유지, 수명은 **마지막** 정지 프레임부터.

    원인이 바뀌어도(TRHT ↔ 58) 정지 프레임이면 갱신한다 — 한 원인에서만 스탬프하는 변이를 잡는다.
    """
    with freeze_time(T0) as frozen:
        mom.record_market_op_event(_event("000020", **first))
        frozen.move_to(T0 + timedelta(seconds=300))
        mom.record_market_op_event(_event("000020", **second))
        assert "000020" in mom.get_halt_active_tickers(), "두 번째 프레임도 정지인데 해제됐다"

        frozen.move_to(T0 + timedelta(seconds=600))
        assert mom.is_ticker_stale_excluded("000020") is True, "첫 정지 프레임 기준으로 풀렸다"
        frozen.move_to(T0 + timedelta(seconds=899))
        assert mom.is_ticker_stale_excluded("000020") is True
        frozen.move_to(T0 + timedelta(seconds=900))
        assert mom.is_ticker_stale_excluded("000020") is False


@pytest.mark.parametrize(
    "halt, release",
    [({"iscd": "58"}, {"iscd": "55"}), ({"trht_yn": "Y"}, {"trht_yn": "N"})],
    ids=["58_then_55", "Y_then_N"],
)
def test_L4_explicit_non_halt_frame_releases_immediately(caplog, halt: dict, release: dict) -> None:
    """정지 아닌 프레임은 TTL 을 기다리지 않고 즉시 해제(현행 그대로) — 그 뒤 TTL 해제 로그는 없다."""
    caplog.set_level(logging.INFO, logger=_MON_LOGGER)
    with freeze_time(T0) as frozen:
        mom.record_market_op_event(_event("000020", **halt))
        frozen.move_to(T0 + timedelta(seconds=60))
        mom.record_market_op_event(_event("000020", **release))
        assert "000020" not in mom.get_halt_active_tickers()
        assert mom.is_ticker_stale_excluded("000020") is False

        frozen.move_to(T0 + timedelta(seconds=700))
        mom.is_ticker_stale_excluded("000020")
        mom.get_market_op_state_summary()

    lines = _mon_lines(caplog, _HALT_RELEASE_PREFIX, "000020")
    assert len(lines) == 1, lines
    assert "reason=ttl" not in lines[0], "프레임 해제를 TTL 해제로 기록했다"


def test_L5a_vi_and_halt_timers_do_not_share_an_anchor() -> None:
    """VI Y(t0) 뒤 정지 58 프레임(t0+300): 정지 수명은 t0+300 기준이다(VI 의 t0 에 묶이지 않는다).

    ⚠️ 해석: 모든 프레임은 VI 칸도 싣는다 — t0+300 정지 프레임의 VI 칸 `N` 이 VI 를 **그 자리에서** 해제한다.
    그래서 t0+600 의 「VI 해제」는 TTL 이 아니라 프레임 해제이고, 이 테스트가 보는 것은 정지 수명의 기준점이다.
    진짜 두 타이머 독립(한쪽이 TTL 로 풀리고 다른 쪽이 남는 것)은 프레임만으로는 만들 수 없어 L5b 가 REST 시드로 본다.
    """
    with freeze_time(T0) as frozen:
        mom.record_market_op_event(_event("003160", vi="Y"))
        frozen.move_to(T0 + timedelta(seconds=300))
        mom.record_market_op_event(_event("003160", vi="N", iscd="58"))
        assert "003160" in mom.get_halt_active_tickers()
        assert "003160" not in mom.get_vi_active_tickers()

        frozen.move_to(T0 + timedelta(seconds=600))
        assert "003160" not in mom.get_vi_active_tickers()
        assert "003160" in mom.get_halt_active_tickers(), "정지가 VI 의 t0 기준으로 풀렸다"
        assert mom.is_ticker_stale_excluded("003160") is True

        frozen.move_to(T0 + timedelta(seconds=899))
        assert mom.is_ticker_stale_excluded("003160") is True
        frozen.move_to(T0 + timedelta(seconds=900))
        assert "003160" not in mom.get_halt_active_tickers()
        assert "003160" not in mom.get_vi_active_tickers()
        assert mom.is_ticker_stale_excluded("003160") is False


def test_L5b_halt_ttl_expiry_keeps_later_vi_and_vice_versa() -> None:
    """두 타이머 독립 — 정지 58(t0, VI 칸 N) 뒤 REST 시드 VI(t0+300).

    t0+600: 정지만 TTL 해제, VI 는 남아 여전히 stale 회피. t0+900: VI 도 해제 → 회피 끝.
    한 dict 를 나눠 쓰면(시드가 정지 시각까지 t0+300 으로 밀어) t0+600 에 정지가 안 풀리고,
    정지 sweep 이 VI 까지 지우면 t0+600 에 VI 가 사라진다.
    """
    with freeze_time(T0) as frozen:
        mom.record_market_op_event(_event("000020", iscd="58"))
        frozen.move_to(T0 + timedelta(seconds=300))
        mom.seed_vi_active_from_rest({"000020"})

        frozen.move_to(T0 + timedelta(seconds=600))
        assert "000020" not in mom.get_halt_active_tickers(), "정지 수명이 VI 시드 시각에 끌려갔다"
        assert "000020" in mom.get_vi_active_tickers(), "정지 만료가 VI 까지 지웠다"
        assert mom.is_ticker_stale_excluded("000020") is True

        frozen.move_to(T0 + timedelta(seconds=899))
        assert mom.is_ticker_stale_excluded("000020") is True
        frozen.move_to(T0 + timedelta(seconds=900))
        assert mom.is_ticker_stale_excluded("000020") is False
        assert "000020" not in mom.get_vi_active_tickers()


def test_L5c_same_frame_vi_and_halt_both_log_their_own_ttl_release(caplog) -> None:
    """한 프레임이 VI·정지를 함께 켜면 둘이 같은 시각에 만료된다 — 각자 `reason=ttl` 을 1행씩 남긴다.

    VI sweep 이 정지까지 조용히 지우는 변이(M20b)는 이 경우에만 관측된다 — VI 가 먼저 sweep 되면
    정지 해제 로그가 사라진다. (프레임만으로는 VI 가 먼저 TTL 만료되고 정지가 남는 상태를 만들 수 없다 — L5a.)
    """
    caplog.set_level(logging.INFO, logger=_MON_LOGGER)
    with freeze_time(T0) as frozen:
        mom.record_market_op_event(_event("000020", vi="Y", iscd="58"))
        frozen.move_to(T0 + timedelta(seconds=600))
        assert mom.is_ticker_stale_excluded("000020") is False

    vi_rel = _mon_lines(caplog, _RELEASE_PREFIX, "000020")
    halt_rel = _mon_lines(caplog, _HALT_RELEASE_PREFIX, "000020")
    assert len(_ttl(vi_rel)) == 1 and len(vi_rel) == 1, vi_rel
    assert len(_ttl(halt_rel)) == 1 and len(halt_rel) == 1, halt_rel


@pytest.mark.parametrize(
    "reader",
    ["is_ticker_stale_excluded", "get_halt_active_tickers", "get_market_op_active_tickers",
     "summary", "circuit_breaker_state"],
)
def test_L6_every_halt_reader_sees_expiry_on_its_own(reader: str) -> None:
    """만료 뒤 **첫 조회**가 어느 읽기 함수든 정지 만료를 반영한다(지연 평가가 한 함수에만 걸린 변이 차단)."""
    with freeze_time(T0) as frozen:
        mom.record_market_op_event(_event("000020", iscd="58"))
        frozen.move_to(T0 + timedelta(seconds=600))
        if reader == "is_ticker_stale_excluded":
            assert mom.is_ticker_stale_excluded("000020") is False
        elif reader == "get_halt_active_tickers":
            assert "000020" not in mom.get_halt_active_tickers()
        elif reader == "get_market_op_active_tickers":
            assert "000020" not in mom.get_market_op_active_tickers()
        elif reader == "summary":
            s = mom.get_market_op_state_summary()
            assert s["halt_active_count"] == 0 and "000020" not in s["halt_active_sample"], s
            assert s["circuit_breaker"]["halted"] == 0, s["circuit_breaker"]
        else:
            assert mom.get_circuit_breaker_state()["halted"] == 0


def test_L7_circuit_breaker_keyword_suspicion_clears_with_halt_lifetime() -> None:
    """CB 의심(사유 키워드)도 정지 수명을 따른다 — 해제 프레임이 없다고 하루 종일 「CB 의심」이 남지 않는다."""
    with freeze_time(T0) as frozen:
        mom.record_market_op_event(_event("005930", trht_yn="Y", reason="서킷브레이커 발동 매매거래중단"))
        assert mom.get_circuit_breaker_state()["suspected"] is True

        frozen.move_to(T0 + timedelta(seconds=600))
        st = mom.get_circuit_breaker_state()
    assert st["suspected"] is False, st
    assert st["halted"] == 0 and st["halt_reasons_sample"] == [], st


def test_L8a_vi_timestamps_hold_only_active_tickers() -> None:
    """위생 가드 — VI 수명 dict 는 활성 종목만 담는다: 프레임 해제·TTL 해제·일일 초기화 뒤 비어 있다.

    행위로는 드러나지 않는 생존 변이 M14(N 프레임이 시각을 남김)·M18b(TTL 이 시각을 남김)·
    M21d(초기화가 시각을 남김)를 잡는다 — 남은 시각은 다음 Y 가 덮어써 행위가 같지만 dict 가 종일 자란다.
    """
    with freeze_time(T0) as frozen:
        mom.record_market_op_event(_event("003160", vi="Y"))
        assert "003160" in mom._vi_last_active_at
        mom.record_market_op_event(_event("003160", vi="N"))
        assert "003160" not in mom._vi_last_active_at, "해제 프레임 뒤 VI 시각이 남았다"

        mom.record_market_op_event(_event("078350", vi="Y"))
        frozen.move_to(T0 + timedelta(seconds=600))
        mom.is_ticker_stale_excluded("078350")
        assert "078350" not in mom._vi_last_active_at, "TTL 해제 뒤 VI 시각이 남았다"

        mom.record_market_op_event(_event("005930", vi="Y"))
        mom.reset_market_op_state()
        assert mom._vi_last_active_at == {}, "일일 초기화가 VI 시각을 남겼다"


def test_L8b_halt_timestamps_hold_only_active_tickers() -> None:
    """F2 위생 — 정지 수명 dict `_halt_last_active_at`(VI 와 **별개** dict)도 같은 규칙. 초기화가 비운다."""
    assert isinstance(getattr(mom, "_halt_last_active_at", None), dict), (
        "market_operation_monitor._halt_last_active_at(dict) 부재 — 정지 수명은 VI 와 다른 dict 에 둔다"
    )
    assert mom._halt_last_active_at is not mom._vi_last_active_at
    with freeze_time(T0) as frozen:
        mom.record_market_op_event(_event("000020", iscd="58"))
        assert "000020" in mom._halt_last_active_at
        assert "000020" not in mom._vi_last_active_at, "정지 프레임이 VI 수명 dict 에 적혔다"
        mom.record_market_op_event(_event("000020", iscd="55"))
        assert "000020" not in mom._halt_last_active_at, "해제 프레임 뒤 정지 시각이 남았다"

        mom.record_market_op_event(_event("000030", trht_yn="Y"))
        frozen.move_to(T0 + timedelta(seconds=600))
        mom.is_ticker_stale_excluded("000030")
        assert "000030" not in mom._halt_last_active_at, "TTL 해제 뒤 정지 시각이 남았다"

        mom.record_market_op_event(_event("000040", iscd="58"))
        mom.reset_market_op_state()
        assert mom._halt_last_active_at == {}, "일일 초기화가 정지 시각을 남겼다"
        assert mom.is_ticker_stale_excluded("000040") is False


@pytest.mark.parametrize("shortened", ["VI", "HALT"])
def test_L9_each_lifetime_reads_its_own_constant(monkeypatch, shortened: str) -> None:
    """두 수명 상수는 서로 독립이다 — 한쪽만 60초로 줄여도 다른 쪽은 599초 유지·600초 해제(MF2v).

    두 상수가 지금은 같은 값(600)이라 정지 sweep 이 `VI_ACTIVE_TTL_SECONDS` 를 읽거나 그 반대여도
    다른 테스트는 전부 초록이다. 한쪽 상수를 줄이면 잘못 읽는 쪽이 60초에 풀려 드러난다.
    줄인 쪽 종목이 60초에 풀리는 것은 패치가 실제로 먹었다는 하네스 확인이다(공허한 초록 차단).
    """
    monkeypatch.setattr(mom, f"{shortened}_ACTIVE_TTL_SECONDS", 60.0)
    vi_t, halt_t = "003160", "000020"
    short_t, long_t = (vi_t, halt_t) if shortened == "VI" else (halt_t, vi_t)

    def _active(t: str) -> bool:
        return t in (mom.get_vi_active_tickers() if t == vi_t else mom.get_halt_active_tickers())

    with freeze_time(T0) as frozen:
        mom.record_market_op_event(_event(vi_t, vi="Y"))
        mom.record_market_op_event(_event(halt_t, iscd="58"))
        assert _active(vi_t) and _active(halt_t)

        frozen.move_to(T0 + timedelta(seconds=60))
        assert not _active(short_t), f"{shortened}_ACTIVE_TTL_SECONDS=60 패치가 먹지 않았다 — 하네스 확인"
        assert _active(long_t), f"{shortened} 상수를 줄였는데 다른 쪽({long_t})이 60초에 풀렸다"

        frozen.move_to(T0 + timedelta(seconds=599))
        assert mom.is_ticker_stale_excluded(long_t) is True, f"{long_t} 가 600초 전에 풀렸다"
        frozen.move_to(T0 + timedelta(seconds=600))
        assert mom.is_ticker_stale_excluded(long_t) is False, f"{long_t} 가 600초에 안 풀렸다"


# ===========================================================================
# R. (F3) 기록 시점 sweep — 만료 뒤 새 활성 프레임은 새 에피소드
# ===========================================================================
def test_R1_vi_frame_after_expiry_starts_new_episode(caplog) -> None:
    """Y(t0) → (읽기 없음) → Y(t0+700): 첫 에피소드는 TTL 해제 1행, 두 번째는 새 활성 1행.

    상태만으로는 「갱신」과 「새 에피소드」가 구별되지 않아(둘 다 t0+700 기준 수명) 로그로 본다.
    """
    caplog.set_level(logging.INFO, logger=_MON_LOGGER)
    with freeze_time(T0) as frozen:
        mom.record_market_op_event(_event("003160", vi="Y"))
        frozen.move_to(T0 + timedelta(seconds=700))
        mom.record_market_op_event(_event("003160", vi="Y"))
        assert "003160" in mom._vi_active_tickers

        frozen.move_to(T0 + timedelta(seconds=1299))
        assert mom.is_ticker_stale_excluded("003160") is True
        frozen.move_to(T0 + timedelta(seconds=1300))
        assert mom.is_ticker_stale_excluded("003160") is False

    rel = _mon_lines(caplog, _RELEASE_PREFIX, "003160")
    act = _mon_lines(caplog, _VI_ACTIVE_PREFIX, "003160")
    assert len(act) == 2, f"활성 로그 {len(act)}행 — 만료 뒤 Y 가 새 에피소드로 기록되지 않았다: {act}"
    assert len(rel) == 2 and len(_ttl(rel)) == 2, f"에피소드마다 TTL 해제 1행이어야 한다: {rel}"


def test_R2_halt_frame_after_expiry_starts_new_episode(caplog) -> None:
    """58(t0) → (읽기 없음) → 58(t0+700): 정지도 같은 규칙 — TTL 해제 1행 + 새 활성 1행."""
    caplog.set_level(logging.INFO, logger=_MON_LOGGER)
    with freeze_time(T0) as frozen:
        mom.record_market_op_event(_event("000020", iscd="58"))
        frozen.move_to(T0 + timedelta(seconds=700))
        mom.record_market_op_event(_event("000020", iscd="58"))
        assert "000020" in mom._halt_active_tickers

    rel = _mon_lines(caplog, _HALT_RELEASE_PREFIX, "000020")
    act = _mon_lines(caplog, _HALT_ACTIVE_PREFIX, "000020")
    assert len(act) == 2, f"정지 활성 로그 {len(act)}행: {act}"
    assert rel == [m for m in rel if "reason=ttl" in m] and len(rel) == 1, rel


def test_R3_release_frame_after_expiry_is_attributed_to_ttl(caplog) -> None:
    """Y(t0) → (읽기 없음) → N(t0+700): 에피소드는 t0+600 에 TTL 로 끝났다 — 해제 로그는 1행, `reason=ttl`.

    sweep 이 기록 **앞**에 있다는 것의 행위 서명이다(뒤에 두면 N 프레임이 먼저 풀어 프레임 해제로 적힌다).
    """
    caplog.set_level(logging.INFO, logger=_MON_LOGGER)
    with freeze_time(T0) as frozen:
        mom.record_market_op_event(_event("003160", vi="Y"))
        frozen.move_to(T0 + timedelta(seconds=700))
        mom.record_market_op_event(_event("003160", vi="N"))

    rel = _mon_lines(caplog, _RELEASE_PREFIX, "003160")
    assert len(rel) == 1 and "reason=ttl" in rel[0], rel


# ===========================================================================
# T. 시각 없는 활성 종목 — 발견 시각을 찍고 600초 뒤 해제 (영구 유지 금지)
# ===========================================================================
_UNSTAMPED = {
    # kind: (활성 집합 이름, 수명 dict 이름, 해제 로그 prefix)
    "vi": ("_vi_active_tickers", "_vi_last_active_at", _RELEASE_PREFIX),
    "halt": ("_halt_active_tickers", "_halt_last_active_at", _HALT_RELEASE_PREFIX),
}


@pytest.mark.parametrize("discovered_after", [0, 100], ids=["found_at_insert", "found_100s_later"])
@pytest.mark.parametrize("kind", list(_UNSTAMPED))
def test_T1_unstamped_active_ticker_is_stamped_at_discovery_and_expires(
    caplog, kind: str, discovered_after: int,
) -> None:
    """방어적 분기 규칙 — 활성 집합에 있는데 수명 dict 에 시각이 없는 종목은 **발견 시각**을 찍고
    그로부터 600초 뒤 풀린다. 시각이 없다고 영구히 활성으로 두면(종전 `continue`) 그 종목은 그날
    21:30 까지 재구독 안전망 밖에 남는다 — cycle368 이 없애려는 바로 그 모양이다.

    정상 경로(프레임·REST 시드)는 항상 시각을 남기므로 이 상태는 집합에 직접 넣어 만든다.
    - `found_at_insert`: 넣은 그 시각에 첫 조회 → 599초 유지 · 600초 해제
    - `found_100s_later`: t0 에 넣고 t0+100 에 첫 조회 → 기준점은 **발견 시각** t0+100(699초 유지 · 700초 해제).
      넣은 시각은 알 수 없으므로 기준점이 될 수 없다
    발견 즉시 푸는 것(시각 없음 = 만료)도 틀렸다 — 첫 조회는 활성을 돌려준다.
    """
    set_name, stamp_name, release_prefix = _UNSTAMPED[kind]
    active: set[str] = getattr(mom, set_name)
    stamps: dict = getattr(mom, stamp_name)
    ticker = "000050"
    caplog.set_level(logging.INFO, logger=_MON_LOGGER)

    with freeze_time(T0) as frozen:
        active.add(ticker)
        assert ticker not in stamps  # 전제: 시각 없음

        found = T0 + timedelta(seconds=discovered_after)
        frozen.move_to(found)
        assert mom.is_ticker_stale_excluded(ticker) is True, "시각 없는 활성 종목을 발견 즉시 풀었다"
        assert ticker in active

        frozen.move_to(found + timedelta(seconds=599))
        assert mom.is_ticker_stale_excluded(ticker) is True, "발견 뒤 600초 전에 풀렸다"
        assert _mon_lines(caplog, release_prefix, ticker) == [], "만료 전에 해제 로그"

        frozen.move_to(found + timedelta(seconds=600))
        assert mom.is_ticker_stale_excluded(ticker) is False, (
            "시각 없는 활성 종목이 발견 뒤 600초가 지나도 안 풀린다 — 영구 유지"
        )
        assert ticker not in active
        assert ticker not in stamps, "TTL 해제 뒤 수명 시각이 남았다"

    rel = _mon_lines(caplog, release_prefix, ticker)
    assert len(rel) == 1 and "reason=ttl" in rel[0], rel


# ===========================================================================
# N. (F4) KIS null 토큰 `(null)` = 빈 값
# ===========================================================================
def test_N1_null_token_is_inactive_code() -> None:
    assert "(null)" in mo._INACTIVE_VALUES, "_INACTIVE_VALUES 에 KIS null 토큰 '(null)' 없음"
    assert mo._is_code_active("(null)") is False


@pytest.mark.parametrize(
    "frame",
    ["100840^N^(null)^AB1^112^^^55^(null)^", "100840^N^(null)^AB1^112^^^55^N^(null)"],
    ids=["vi_null", "ovtm_vi_null"],
)
def test_N2_null_vi_column_is_not_vi_active(frame: str) -> None:
    """VI·시간외VI 칸이 `(null)` 인 라이브 프레임 → VI 활성 아님, stale 회피 아님."""
    e = parse_market_op_payload("100840", frame)
    assert is_event_blocking(e) is False
    mom.record_market_op_event(e)
    assert "100840" not in mom.get_vi_active_tickers()
    assert mom.is_ticker_stale_excluded("100840") is False


@pytest.mark.parametrize(
    "tr_key, payload",
    [("100840", FRAME_100840_LIVE), ("005930", "N^(null)^121^112^0^0^0^0^0^KRX")],
    ids=["live_shape", "document_shape"],
)
def test_N3_null_suspension_reason_is_normalised_to_empty(tr_key: str, payload: str) -> None:
    """정지 사유 칸(TR_SUSP_REAS_CNTT) `(null)` → `""`. 두 모양 모두."""
    assert parse_market_op_payload(tr_key, payload).tr_susp_reas_cntt == ""


def test_N4_real_suspension_reason_text_is_kept() -> None:
    """가드 — 정규화는 칸 전체가 정확히 `(null)` 일 때만. 부분 문자열 치환(`.replace`)이면 실제 사유가 깎인다."""
    reason = "매매거래정지 (null) 표기 포함"
    e = parse_market_op_payload("005930", f"005930^Y^{reason}^AB1^112^^^58^N^")
    assert e.tr_susp_reas_cntt == reason


def test_N5_null_reason_does_not_enter_halt_reason_sample() -> None:
    """정지 프레임의 사유가 `(null)` 이면 CB 사유 표본(`halt_reasons_sample`)에 들어가지 않는다."""
    mom.record_market_op_event(parse_market_op_payload("005930", "005930^Y^(null)^AB1^112^^^58^N^"))
    st = mom.get_circuit_breaker_state()
    assert st["halted"] == 1
    assert st["halt_reasons_sample"] == [], st["halt_reasons_sample"]


@pytest.mark.parametrize("code", ["(null)", "Y", "N"])
def test_N6_halt_status_stays_an_explicit_set(code: str) -> None:
    """가드 — 종목상태 정지 판정은 `_INACTIVE_VALUES` 가 아니라 명시 집합 {"58"} 멤버십이다."""
    assert mo.is_iscd_stat_blocking(code) is False
    assert mo.ISCD_STAT_BLOCKING == frozenset({"58"})
