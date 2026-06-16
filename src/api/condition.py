"""조건검색 API 모듈 — 등락률 순위 + 개별 종목 시세 조회.

1단계: 등락률 순위 API로 당일 급등 종목(15%+) 후보 확보
2단계: 각 종목의 현재가 시세 API로 시총/거래대금 조회 → 필터링

모의투자(VTS)에서는 등락률 순위 API를 지원하지 않으므로 테스트 종목으로 대체.
현재가 시세 API(FHKST01010100)는 모의/실전 동일 TR_ID로 양쪽 모두 동작.
"""

import asyncio
import logging
import re
import time

from src.api.base import KisApiError, kis_get_quote
from src.config import settings

logger = logging.getLogger(__name__)


# 사이클 155 (2026-06-16) — FHKST01010100 merge 키 (5 → 35 키 확장).
# 사이클 107 5 키 + 사이클 155 HIGH 23 + MEDIUM 7 = 35.
# KIS 정본: inquire_price COLUMN_MAPPING 88 컬럼.
_FHKST_MERGE_KEYS: tuple[str, ...] = (
    # 사이클 107~108 (5)
    "acml_tr_pbmn", "lstn_stcn", "acml_vol", "prdy_vrss", "hts_avls",
    # 사이클 155 HIGH (23)
    "per", "pbr",                                                              # 밸류에이션
    "hts_frgn_ehrt", "frgn_ntby_qty",                                          # 외국인
    "stck_mxpr", "stck_llam",                                                  # 상하한가
    "vol_tnrt", "prdy_vrss_vol_rate",                                          # 거래량
    "w52_hgpr", "w52_lwpr", "w52_hgpr_date", "d250_hgpr", "d250_lwpr",         # 신고가
    "mrkt_warn_cls_code", "invt_caful_yn", "short_over_yn", "sltr_yn",         # 진입 차단 (FHKST)
    "iscd_stat_cls_code", "temp_stop_yn",
    "new_hgpr_lwpr_cls_code",                                                  # 신고가 코드
    "eps", "bps", "whol_loan_rmnd_rate",                                       # 실적/신용
    # 사이클 155 MEDIUM (7)
    "ssts_yn", "last_ssts_cntg_qty",
    "vi_cls_code", "ovtm_vi_cls_code",
    "bstp_kor_isnm",
)

# 사이클 145 답습 — 0 값 응답 시 기존 raw 키 보존 (장 시작 전 보호).
# 사이클 155 — 14 키 확장 (per/pbr/vol_tnrt/외국인/신고가/eps/bps/whol_loan).
# 비숫자 키 (vi_cls_code / w52_hgpr_date / iscd_stat_cls_code 등) 는 정상 merge.
_ZERO_VALUE_SKIP_KEYS: frozenset[str] = frozenset({
    "acml_tr_pbmn", "acml_vol",                                  # 사이클 145
    "per", "pbr",                                                # 사이클 155 밸류에이션
    "vol_tnrt", "prdy_vrss_vol_rate",                            # 거래량
    "hts_frgn_ehrt", "frgn_ntby_qty",                            # 외국인
    "w52_hgpr", "w52_lwpr", "d250_hgpr", "d250_lwpr",            # 신고가
    "eps", "bps", "whol_loan_rmnd_rate",                         # 실적/신용
})


# 사이클 144 — graceful_failed 카운터 (카드 #27 LOW).
# inquire_stock_basics FHKST01010100 호출 실패 가시화.
# 매매 안전성 무영향 (logging + 카운터 한정).
_graceful_failed_counter: dict[str, int] = {
    "fhkst01010100_failed": 0,
}
_graceful_failed_lock = asyncio.Lock()


async def _record_graceful_failed(reason: str) -> None:
    """graceful 분기 fail 카운터 증가. 등록 키 외 무시."""
    async with _graceful_failed_lock:
        if reason in _graceful_failed_counter:
            _graceful_failed_counter[reason] += 1


def get_graceful_failed_counts() -> dict[str, int]:
    """카운터 스냅샷 사본 반환."""
    return dict(_graceful_failed_counter)


def reset_graceful_failed_counts() -> None:
    """task 시작 시 카운터 reset."""
    for key in _graceful_failed_counter:
        _graceful_failed_counter[key] = 0


def _drain_task_exception(task: "asyncio.Task") -> None:
    """inflight Task 종료 시 예외 회수 — "Task exception was never retrieved" 차단.

    PR-C2 보강 (Copilot, 2026-05-14): `asyncio.shield(task)` joiner 가 전부 cancel 된
    상황에서 inflight task 가 예외로 종료되면 회수되지 않아 이벤트 루프가 운영 잡음
    경고를 남긴다. `add_done_callback` 으로 예외만 조용히 회수 — 취소는 무시.
    """
    if task.cancelled():
        return
    exc = task.exception()
    if exc is not None:
        logger.debug("[condition_cache] inflight task exception (drained): %r", exc)


# ---------------------------------------------------------------------------
# PR-C (2026-05-14) — 시세/일봉 TTL 캐시.
#
# 운영 metrics(2026-05-13) 에서 inquire-price 17건 + inquire-daily-itemchartprice
# 10건이 5xx 재시도로 잡혔다. 동일 ticker 반복 조회 추정. 짧은 TTL 캐시로
# 외부 부하 감소 + 5xx 노출 면적 축소.
#
# 사용 범위 (안전 가드):
#   - 스캐닝/조건검사 한정 (fetch_rising_stocks, prepare, _scan_loop 등)
#   - `execute_buy/execute_sell` 의 체결가/주문가 결정 경로는 절대 사용 금지
#     (현재가는 WebSocket tick 또는 최신 직접 호출)
#
# 무효화: TTL 자동 만료 + `_reset_daily_state()` 가 호출하는 `clear_caches()`
#
# PR-C2 (2026-05-14) — Copilot 리뷰 8건 재설계:
#   1) Future → asyncio.Task + joiner 는 asyncio.shield(task) 로 await
#      → joiner cancel 전파로 inflight 깨지는 결함 차단 (InvalidStateError)
#   2) `asyncio.get_event_loop()` 미사용 — Task 패턴은 loop 직접 참조 불필요
#      (Py 3.12+ deprecation 회피)
#   3) `except CancelledError` 분리 처리 — Task 기반에선 CancelledError 가
#      Exception 분기로 잘못 흡수될 여지 자체 제거 (helper 안에 except 없음)
#   4) `clear_caches()` 가 `_cache_epoch` bump — fetch 완료 시 epoch 일치
#      검증한 경우만 cache write. 이전 영업일 inflight 결과가 새 영업일
#      캐시에 stale write 되는 결함 차단
# ---------------------------------------------------------------------------
_PRICE_CACHE_TTL = 5.0       # seconds — 5초. swing pull(1분 주기) 매 호출 신선
_CANDLE_CACHE_TTL = 300.0    # 5분 — 일봉은 장중 분 단위 갱신, 전략 시뮬레이션 정확도 영향 없음

# (ticker) -> (output_dict, expires_at_monotonic)
_price_cache: dict[str, tuple[dict, float]] = {}
# (ticker, days) -> (output_list, expires_at_monotonic)
_candle_cache: dict[tuple[str, int], tuple[list[dict], float]] = {}

# race 보호 — 캐시 read/write 는 동기 영역에서만 일어나도록 lock. KIS 호출은
# lock 밖에서. single-flight 가 필요한 동시 호출은 `_inflight_*` Task dict 가
# 동일 키 진행 중 호출을 첫 호출의 결과로 합류시킨다.
# joiner 는 `asyncio.shield(task)` 로 await — 자기 task 가 cancel 돼도 inflight
# task 자체는 영향 없음 (다른 joiner 와 fetch 담당 모두 정상 진행).
_cache_lock = asyncio.Lock()
_inflight_price: dict[str, "asyncio.Task[dict]"] = {}
_inflight_candle: dict[tuple[str, int], "asyncio.Task[list[dict]]"] = {}

# 캐시 epoch — `clear_caches()` 호출 시 +1. fetch helper 가 완료 시점 epoch 가
# 시작 시점과 일치할 때만 cache write. clear 후 stale inflight 결과가 새 영업일
# 캐시에 누수되는 결함 차단 (Copilot 리뷰 #4).
_cache_epoch: int = 0


def clear_caches() -> None:
    """일일 정산 reset 등 외부 트리거에서 호출 — 캐시 비우기 + epoch bump.

    `scheduler._reset_daily_state()` 가 매일 20:10 정산 후 호출해 야간 누적 방지.

    PR-C2 (2026-05-14): `_cache_epoch` 를 증가시켜 진행 중 inflight fetch 가
    완료 시점에 캐시 write 를 skip 하도록 강제 (fetch 결과는 정상 반환). inflight
    task 자체는 cancel 안 함 — 진행 중 fetch 는 이미 호출자가 await 중이라 cancel
    시 호출자에게 unexpected CancelledError 전파 위험. 캐시 write 만 막아 다음
    호출부터 새 fetch 발생.
    """
    global _cache_epoch
    _cache_epoch += 1
    _price_cache.clear()
    _candle_cache.clear()
    logger.info("[condition_cache] cleared (epoch=%d)", _cache_epoch)

# Phase G2 (2026-05-13): KIS 표준코드(12자리, 예 "00000A000100") 마지막
# 6자리 = KRX 단축코드(상장변경/병합 시 prefix 만 바뀜). stock_master 캐시
# 의 PK 는 운영 시스템 전체와 동일한 6자리 KRX 코드로 통일한다.
_TICKER_TAIL_RE = re.compile(r"([A-Za-z0-9]{6})$")


def _normalize_ticker(pdno: str | None) -> str:
    """KIS 표준코드(`00000A000100`)에서 KRX 6자리 단축코드 추출.

    - 6자리 영숫자 입력: 변환 없이 그대로 보존 (KRX REIT/ETN/신주인수권 등 영문자 가능 — `scheduler._eager_refresh_stock_master_for_held_positions` 가드와 일관)
    - 12자리 표준코드: 마지막 6자리(영숫자) 추출
    - None / 빈 문자열 / 6자리 영숫자 미포함: 빈 문자열 반환

    결함 배경 (Phase G2, 2026-05-13):
    - 운영 DB stock_master.ticker = `00000A000100` (KIS pdno 그대로)
    - positions.ticker = `000100` (KRX 6자리)
    - `stock_master.get(ticker)` 항상 miss → Phase G NXT 사전 차단 무력화

    Codex P2 (2026-05-13):
    - 초기 구현은 `(\\d{6})$` 라 `K12345` 같은 6자리 영숫자 ticker 가 빈 문자열로 변환되어 동일 결함 재발 위험. 6자리 영숫자 단락 + 정규식 영숫자 확장으로 차단.
    """
    if not pdno:
        return ""
    s = str(pdno).strip()
    if not s:
        return ""
    # 이미 6자리 영숫자 ticker 면 그대로 보존
    if len(s) == 6 and s.isalnum():
        return s
    m = _TICKER_TAIL_RE.search(s)
    return m.group(1) if m else ""

FLUCTUATION_RANK_URL = "/uapi/domestic-stock/v1/ranking/fluctuation"
STOCK_PRICE_URL = "/uapi/domestic-stock/v1/quotations/inquire-price"
# `inquire-daily-price`(FHKST01010400)는 약 30일치만 반환되는 제약이 있어 60일 EMA 등
# 장기 일봉이 필요한 사용처에서 부족하다. 100일까지 응답하는 기간별 시세 API를 사용.
DAILY_PRICE_URL = "/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice"
HOLIDAY_URL = "/uapi/domestic-stock/v1/quotations/chk-holiday"
# CTPF1002R — 주식기본조회 (Phase G, 2026-05-11). NXT 거래종목여부/정지여부 사전 조회.
STOCK_BASICS_URL = "/uapi/domestic-stock/v1/quotations/search-stock-info"

# 사이클 101 — StockBasics 모듈 공개 re-export (테스트 + 호출자 직접 import 호환)
from src.models.stock import StockBasics  # noqa: E402, F401


async def is_market_open(target_date) -> bool:
    """KIS 휴장일 API로 해당 일자의 주식시장 개장 여부를 반환한다.

    target_date: datetime.date
    Returns True (개장일, opnd_yn=Y) or False (휴장).
    조회 실패 시 안전을 위해 True 반환 (영업일 가정 후 후속 단계에서 매매 검증).
    """
    yyyymmdd = target_date.strftime("%Y%m%d")
    try:
        # 사이클 7-C — 시세성 호출 풀로 위임 (보조 계좌 라운드로빈 + 메인 fallback)
        data = await kis_get_quote(
            HOLIDAY_URL,
            "CTCA0903R",
            {"BASS_DT": yyyymmdd, "CTX_AREA_NK": "", "CTX_AREA_FK": ""},
        )
        for row in data.get("output", []):
            if row.get("bass_dt") == yyyymmdd:
                return row.get("opnd_yn") == "Y"
        logger.warning("휴장일 응답에 %s 항목 없음", yyyymmdd)
        return True
    except Exception:
        logger.exception("휴장일 조회 실패: %s — 영업일로 가정", yyyymmdd)
        return True


async def next_trading_day(after_date) -> "date":
    """after_date 다음 개장일을 반환한다 (최대 14일 탐색).

    KIS chk-holiday 응답이 약 30일치를 한 번에 주므로 1회 호출로 충분.
    실패 시 단순히 다음날 반환 (안전 fallback).
    """
    from datetime import timedelta
    yyyymmdd = (after_date + timedelta(days=1)).strftime("%Y%m%d")
    try:
        # 사이클 7-C — 시세성 호출 풀
        data = await kis_get_quote(
            HOLIDAY_URL,
            "CTCA0903R",
            {"BASS_DT": yyyymmdd, "CTX_AREA_NK": "", "CTX_AREA_FK": ""},
        )
        from datetime import date as _date
        for row in data.get("output", []):
            if row.get("opnd_yn") == "Y":
                d = row.get("bass_dt", "")
                if len(d) == 8:
                    return _date(int(d[:4]), int(d[4:6]), int(d[6:8]))
    except Exception:
        logger.exception("다음 영업일 조회 실패")
    return after_date + timedelta(days=1)

# 스캔 최소 등락률 — 29% 매수 조건의 후보군
MIN_CHANGE_RATE = 15.0

# 모의투자용 테스트 종목
VTS_TEST_TICKERS = [
    {"stck_shrn_iscd": "005930", "hts_kor_isnm": "삼성전자",
     "stck_prpr": "65000", "prdy_ctrt": "18.5",
     "lstn_stcn": "5969782550", "acml_tr_pbmn": "500000000000"},
    {"stck_shrn_iscd": "000660", "hts_kor_isnm": "SK하이닉스",
     "stck_prpr": "180000", "prdy_ctrt": "22.3",
     "lstn_stcn": "728002365", "acml_tr_pbmn": "400000000000"},
    {"stck_shrn_iscd": "373220", "hts_kor_isnm": "LG에너지솔루션",
     "stck_prpr": "370000", "prdy_ctrt": "16.8",
     "lstn_stcn": "234000000", "acml_tr_pbmn": "300000000000"},
    {"stck_shrn_iscd": "207940", "hts_kor_isnm": "삼성바이오로직스",
     "stck_prpr": "800000", "prdy_ctrt": "19.1",
     "lstn_stcn": "71174000", "acml_tr_pbmn": "250000000000"},
    {"stck_shrn_iscd": "005490", "hts_kor_isnm": "POSCO홀딩스",
     "stck_prpr": "350000", "prdy_ctrt": "15.5",
     "lstn_stcn": "84571230", "acml_tr_pbmn": "200000000000"},
]


async def _fetch_fluctuation_rank() -> list[dict]:
    """등락률 순위 API — 상승률 상위 종목 조회."""
    params = {
        "fid_cond_mrkt_div_code": "J",
        "fid_cond_scr_div_code": "20170",
        "fid_input_iscd": "0000",
        "fid_rank_sort_cls_code": "0",
        "fid_input_cnt_1": "0",
        "fid_prc_cls_code": "0",
        "fid_input_price_1": "",
        "fid_input_price_2": "",
        "fid_vol_cnt": "",
        "fid_trgt_cls_code": "0",
        "fid_trgt_exls_cls_code": "0",
        "fid_div_cls_code": "0",
        "fid_rsfl_rate1": "",
        "fid_rsfl_rate2": "",
    }
    # 사이클 7-C — 시세성 호출 풀
    data = await kis_get_quote(FLUCTUATION_RANK_URL, "FHPST01700000", params)
    return data.get("output", [])


async def inquire_stock_basics(pdno: str) -> "StockBasics":
    """KIS CTPF1002R(주식기본조회) + FHKST01010100(주식현재가) 통합 — 종목 마스터 보강.

    NXT 사전 판별 핵심 필드 (CTPF1002R 영속):
    - `cptt_trad_tr_psbl_yn`  NXT 거래종목여부 (Y/N)
    - `nxt_tr_stop_yn`        NXT 거래정지여부 (Y/N)
    파생값: `nxt_tradable = (cptt=='Y') AND (nxt_stop=='N')`.

    사이클 107 (2026-06-11) — FHKST01010100 추가 호출 영역:
    - CTPF1002R 응답 = 종목 식별/상장/관리 영역 (bfdy_clpr 등 67 컬럼 영속)
    - FHKST01010100 응답 = 시세/거래 영역 (acml_tr_pbmn + lstn_stcn + acml_vol)
    - raw JSONB merge = stock_master = 마스터 + 시세 통합 영구 영속
    - Rate Limit: 50ms sleep (CTPF1002R → FHKST01010100 순차 호출 보호)
    - KIS chk_inquire_price.py 정본 인용:
        TR_ID = FHKST01010100, URL = /uapi/domestic-stock/v1/quotations/inquire-price
        FID_COND_MRKT_DIV_CODE = "J" (주식), FID_INPUT_ISCD = 종목코드

    KIS 응답 검증 (KIS MCP 2026-05-11):
    - CTPF1002R 응답 output 은 dict (single-item) — list 가 아님.
    - 모의/실전 동일 TR_ID (CTPF/FH 접두사 양쪽 모두 동일).
    - FHKST01010100 응답 output 은 dict (single-item).
    """
    from src.models.stock import StockBasics

    params = {
        "PRDT_TYPE_CD": "300",  # 300=국내주식 (KIS CTPF1002R 명세 기본값)
        "PDNO": pdno,
    }
    # 사이클 7-C — 시세성 호출 풀 (CTPF1002R 1차 호출)
    data = await kis_get_quote(STOCK_BASICS_URL, "CTPF1002R", params)
    ctpf_output = data.get("output") or {}

    # 사이클 107 — FHKST01010100 추가 호출 (Rate Limit 50ms sleep 영속)
    await asyncio.sleep(0.05)

    try:
        price_data_raw = await kis_get_quote(
            STOCK_PRICE_URL,
            "FHKST01010100",
            {
                "fid_cond_mrkt_div_code": "J",
                "fid_input_iscd": pdno,
            },
        )
        # FHKST01010100 응답 output 은 dict (single-item)
        price_data = price_data_raw.get("output", {}) if price_data_raw else {}
    except Exception:
        logger.exception(
            "[inquire_stock_basics] FHKST01010100 호출 실패 graceful pdno=%s", pdno
        )
        # 사이클 144 — graceful_failed 카운터 (카드 #27 LOW).
        try:
            await _record_graceful_failed("fhkst01010100_failed")
        except Exception:
            logger.debug("[_record_graceful_failed] 카운터 갱신 실패 graceful", exc_info=True)
        price_data = {}

    # 사이클 155 — raw merge (CTPF1002R 67 + FHKST01010100 35 키 = 총합).
    # CTPF 우선, FHKST 35 키만 추가 (기존 키 덮어쓰기 금지).
    # 사이클 145 — _ZERO_VALUE_SKIP_KEYS 의 0 값 응답은 skip → 기존 raw 키 보존
    # (장 시작 전 acml_tr_pbmn=0 등의 덮어쓰기로 인한 silent 결함 차단).
    merged_raw = dict(ctpf_output)
    for key in _FHKST_MERGE_KEYS:
        if key in price_data:
            value = price_data[key]
            if key in _ZERO_VALUE_SKIP_KEYS:
                try:
                    numeric_value = float(str(value).replace(",", "") or 0)
                    if numeric_value == 0.0:
                        continue
                except (ValueError, TypeError):
                    pass  # 비숫자는 정상 merge
            merged_raw[key] = value

    cptt = (ctpf_output.get("cptt_trad_tr_psbl_yn") or "").strip().upper()
    nxt_stop = (ctpf_output.get("nxt_tr_stop_yn") or "").strip().upper()
    krx_stop = (ctpf_output.get("tr_stop_yn") or "").strip().upper()
    admn = (ctpf_output.get("admn_item_yn") or "").strip().upper()

    return StockBasics(
        # Phase G2 (2026-05-13): KIS pdno 는 12자리 표준코드("00000A000100").
        # KRX 6자리 단축코드로 정규화 후 모델에 저장 — stock_master PK 정합성 보장.
        ticker=_normalize_ticker(ctpf_output.get("pdno") or pdno),
        name=ctpf_output.get("prdt_abrv_name") or ctpf_output.get("prdt_name") or "",
        excg_dvsn_cd=ctpf_output.get("excg_dvsn_cd") or "",
        nxt_tradable=(cptt == "Y" and nxt_stop == "N"),
        krx_halted=(krx_stop == "Y"),
        admin_item=(admn == "Y"),
        raw=merged_raw,
    )


async def _fetch_stock_detail_and_cache(ticker: str, epoch_at_start: int) -> dict:
    """KIS 호출 + epoch 일치 시 캐시 write + inflight 정리.

    PR-C2 (2026-05-14):
    - epoch_at_start 와 현재 `_cache_epoch` 가 다르면(`clear_caches` 호출됨) 캐시
      write 를 skip — stale inflight 결과 누수 차단. 결과는 호출자(joiner) 에게
      정상 반환해 caller 동작은 보존.
    - finally 절에서 inflight 정리 — `_inflight_price[ticker]` 가 자기 task 일
      때만 pop (다른 task 가 같은 ticker 로 이미 등록한 경우는 보존).
    - 예외 처리(`except`) 는 두지 않음 — 호출자(joiner) 가 `await shield(task)` 로
      예외를 정상 회수. CancelledError 분리 분기 불필요(Copilot 리뷰 #2/3 동시 차단).
    """
    try:
        params = {
            "fid_cond_mrkt_div_code": "J",
            "fid_input_iscd": ticker,
        }
        # 사이클 7-C — 시세성 호출 풀 (보조 라운드로빈 + 메인 fallback)
        data = await kis_get_quote(STOCK_PRICE_URL, "FHKST01010100", params)
        output = data.get("output", {})
        async with _cache_lock:
            if _cache_epoch == epoch_at_start:
                _price_cache[ticker] = (output, time.monotonic() + _PRICE_CACHE_TTL)
            # else: clear_caches 가 호출됨 → cache write skip (stale 차단)
        return output
    finally:
        # inflight 정리 — race 안전: 자기 task 일 때만 pop
        current = _inflight_price.get(ticker)
        try:
            if current is asyncio.current_task():
                _inflight_price.pop(ticker, None)
        except RuntimeError:
            # current_task() 가 None 이거나 호출 불가한 컨텍스트 — best effort cleanup
            _inflight_price.pop(ticker, None)


async def fetch_stock_detail(ticker: str) -> dict:
    """개별 종목의 현재가/시총/거래대금을 조회한다.

    FHKST01010100은 모의/실전 동일 TR_ID.

    PR-C (2026-05-14): TTL 캐시 (`_PRICE_CACHE_TTL=5s`) + single-flight. 스캐닝
    경로 한정 — 체결가/주문가 결정에는 사용 금지(`execute_buy/sell` 은 WebSocket
    tick 또는 직접 호출 사용). 5초 TTL 은 swing pull(1분 주기) 매 호출 신선.
    동시 호출 N 회 시 첫 호출만 KIS fetch, 나머지는 같은 task 결과 공유.

    PR-C2 (2026-05-14): Future → asyncio.Task 로 전환 + joiner 는
    `asyncio.shield(task)` 로 await — joiner cancel 시 inflight 자체는 보호되어
    다른 joiner 가 영향 받지 않음. epoch 가드로 `clear_caches()` race 차단.
    """
    now = time.monotonic()
    # double-check cache (lock 밖) — fast path
    cached = _price_cache.get(ticker)
    if cached is not None and cached[1] > now:
        return cached[0]

    async with _cache_lock:
        # double-check cache (lock 안)
        cached = _price_cache.get(ticker)
        if cached is not None and cached[1] > time.monotonic():
            return cached[0]

        # inflight 검사 — 진행 중 task 가 없으면 새로 발화
        task = _inflight_price.get(ticker)
        if task is None or task.done():
            epoch_at_start = _cache_epoch
            task = asyncio.create_task(
                _fetch_stock_detail_and_cache(ticker, epoch_at_start)
            )
            # PR-C2 보강: joiner 0명 종료 시 예외 회수 (Task exception 경고 차단)
            task.add_done_callback(_drain_task_exception)
            _inflight_price[ticker] = task

    # joiner 는 shield 로 await — 자기 task cancel 시 inflight 보호
    return await asyncio.shield(task)


async def _fetch_daily_candles_and_cache(
    ticker: str, days: int, epoch_at_start: int
) -> list[dict]:
    """KIS 일봉 호출 + epoch 일치 시 캐시 write + inflight 정리.

    PR-C2 (2026-05-14): `_fetch_stock_detail_and_cache` 와 동일 패턴.
    """
    from datetime import datetime, timedelta, timezone

    cache_key = (ticker, days)
    _KST_TZ = timezone(timedelta(hours=9))
    try:
        # PR-C2 보강 (Copilot, 2026-05-14): `date.today()` 를 한 번만 호출 — 두 번
        # 호출 시 자정 경계 race 로 end_date/start_date 가 서로 다른 날짜 기준이 될 수 있음.
        # 사이클 68 G-12 — `date.today()` UTC naive 폐기, KST 명시
        today = datetime.now(_KST_TZ).date()
        end_date = today.strftime("%Y%m%d")
        # 달력일 ≈ 영업일 × 7/5 + 안전 마진 (휴일/공휴일 + 신규상장 일자 부족 등)
        window_calendar_days = days + (days // 2) + 10
        start_date = (today - timedelta(days=window_calendar_days)).strftime("%Y%m%d")

        params = {
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_INPUT_ISCD": ticker,
            "FID_INPUT_DATE_1": start_date,
            "FID_INPUT_DATE_2": end_date,
            "FID_PERIOD_DIV_CODE": "D",
            "FID_ORG_ADJ_PRC": "0",
        }
        # FHKST03010100은 모의/실전 동일 TR_ID (FH 접두사 시세 API 공통)
        # 사이클 7-C — 시세성 호출 풀
        data = await kis_get_quote(DAILY_PRICE_URL, "FHKST03010100", params)
        output = data.get("output2") or data.get("output") or []
        output = [c for c in output if c.get("stck_bsop_date")]
        result = output[:days]

        async with _cache_lock:
            if _cache_epoch == epoch_at_start:
                _candle_cache[cache_key] = (result, time.monotonic() + _CANDLE_CACHE_TTL)
        return result
    finally:
        current = _inflight_candle.get(cache_key)
        try:
            if current is asyncio.current_task():
                _inflight_candle.pop(cache_key, None)
        except RuntimeError:
            _inflight_candle.pop(cache_key, None)


async def fetch_daily_candles(ticker: str, days: int = 21) -> list[dict]:
    """KIS 기간별시세 API로 최근 N영업일 일봉 데이터를 조회한다.

    반환: [{"stck_bsop_date", "stck_oprc"(시가), "stck_hgpr"(고가),
            "stck_lwpr"(저가), "stck_clpr"(종가), "acml_vol", ...}, ...]
    최신순(idx=0이 가장 최근일).

    구현: `/quotations/inquire-daily-itemchartprice` (FHKST03010100) 사용.
    이전에는 `inquire-daily-price`(FHKST01010400)를 사용했으나 응답이 약 30일로
    제한되는 KIS 동작이 있어, 60일 EMA처럼 장기 일봉이 필요한 사용처에서
    `len(candles) < 61` 컷에 모두 탈락하던 결함이 있었다.
    FHKST03010100은 단일 호출당 최대 100일 응답 → days=65 사용처도 충분.

    PR-C (2026-05-14): TTL 캐시 (`_CANDLE_CACHE_TTL=300s`) + single-flight.
    캐시 키는 `(ticker, days)` — days 별 분리 보관(donchian 60일 vs 다른
    사용처 21일 등). 일봉은 장중 분 단위 갱신, 5분 지연은 일봉 기반 전략
    (donchian/momentum 시뮬레이션) 정확도에 영향 없음.

    PR-C2 (2026-05-14): Future → asyncio.Task + asyncio.shield 패턴 + epoch 가드.
    """
    cache_key = (ticker, days)
    now = time.monotonic()
    cached = _candle_cache.get(cache_key)
    if cached is not None and cached[1] > now:
        return cached[0]

    async with _cache_lock:
        cached = _candle_cache.get(cache_key)
        if cached is not None and cached[1] > time.monotonic():
            return cached[0]

        task = _inflight_candle.get(cache_key)
        if task is None or task.done():
            epoch_at_start = _cache_epoch
            task = asyncio.create_task(
                _fetch_daily_candles_and_cache(ticker, days, epoch_at_start)
            )
            # PR-C2 보강: joiner 0명 종료 시 예외 회수 (Task exception 경고 차단)
            task.add_done_callback(_drain_task_exception)
            _inflight_candle[cache_key] = task

    return await asyncio.shield(task)


async def fetch_rising_stocks() -> list[dict]:
    """당일 급등 종목을 등락률 순위로 조회하고, 개별 시세로 시총/거래대금을 보강한다."""
    if not settings.is_production:
        logger.info("모의투자 환경: 테스트 종목 %d개 사용", len(VTS_TEST_TICKERS))
        return VTS_TEST_TICKERS

    try:
        rising = await _fetch_fluctuation_rank()
    except KisApiError as e:
        logger.warning("등락률순위 API 실패 (%s), 테스트 종목으로 대체", e.msg_cd)
        return VTS_TEST_TICKERS

    # 15% 이상 종목만 추려서 개별 시세 조회 (Rate Limit 고려)
    candidates = []
    for item in rising:
        rate = float(item.get("prdy_ctrt", "0"))
        if rate >= MIN_CHANGE_RATE:
            candidates.append(item)

    logger.info("등락률 15%%+ 종목: %d개 → 개별 시세 조회 시작", len(candidates))

    # 개별 시세 조회로 시총/거래대금/전일종가 보강 (순차 호출, Rate Limit 자동 적용)
    from src.engine.scanner import ticker_prev_close

    enriched = []
    for item in candidates:
        ticker = item.get("stck_shrn_iscd", "")
        try:
            detail = await fetch_stock_detail(ticker)
            merged = {**item}
            merged["lstn_stcn"] = detail.get("lstn_stcn", "0")
            merged["acml_tr_pbmn"] = detail.get("acml_tr_pbmn", "0")
            # 전일종가 저장 (실시간 등락률 계산용)
            prev_close = int(detail.get("stck_sdpr", "0"))
            if prev_close > 0:
                ticker_prev_close[ticker] = prev_close
            enriched.append(merged)
        except Exception:
            logger.warning("종목 시세 조회 실패: %s", ticker)
            continue

    return enriched
