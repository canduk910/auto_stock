"""종목 필터링 모듈.

등락률 순위 API 결과에서 당일 급등 종목(15%+ 상승)을 필터링하고,
시총/거래대금 조건을 추가 적용한 뒤 WebSocket 실시간 시세 구독을 등록한다.

매수 조건이 시가 대비 +29.5%이므로, 이미 15% 이상 상승 중인 종목을
후보군으로 잡아 29.5% 도달을 감시한다.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from src.api.condition import MIN_CHANGE_RATE, fetch_rising_stocks
from src.realtime.websocket import kis_ws
from src.realtime.websocket_pool import kis_ws_pool

logger = logging.getLogger(__name__)

# KST 타임존 (ticker_last_tick 갱신용 — 프로젝트 컨벤션상 각 모듈 로컬 정의)
KST_TZ = timezone(timedelta(hours=9))

# 스캔 결과 캐시
_last_scan_result: list[str] = []
_last_scan_time: str | None = None

# 종목코드 → 종목명 매핑 (스캔 시 갱신)
ticker_names: dict[str, str] = {}

# 종목코드 → 최신 시세 (on_tick에서 갱신)
ticker_prices: dict[str, dict] = {}
# { "current_price": int, "open_price": int, "change_rate": float, "prev_close": int }

# 종목코드 → 전일종가 (스캔 시 개별시세 API에서 저장)
ticker_prev_close: dict[str, int] = {}

# 종목코드 → 시총/거래대금 (스캔 시 저장, 억 단위)
ticker_market_info: dict[str, dict] = {}
# { "market_cap": int(억), "trade_amount": int(억) }

# 종목코드 → 마지막 tick 수신 KST datetime (on_tick에서 갱신, Phase D 가시성 보강)
# scheduler._report_tick_coverage 가 5분 주기로 미수신 종목 카운트를 노출한다.
# 2026-05-11 운영 사고(VB/LTV 종일 시세 무수신) 후속 가시성 결함 보완.
ticker_last_tick: dict[str, datetime] = {}

# 사이클 21 — 모멘텀 단계별 깔때기 카운트 dict (7 키).
# MomentumStrategy 는 prepare() 가 비어 있고 실시간 scan_stocks() 기반.
# scan_stocks() 가 각 단계별로 본 dict 를 누적 → MomentumStrategy.get_scan_stats() 가
# 사본 반환 → ScanMonitor 깔때기 시각화.
scan_filter_stats: dict = {
    "universe_candidates": 0,    # fetch_rising_stocks() raw 응답 수
    "rate_pass": 0,              # 등락률 15%+ 통과
    "mcap_pass": 0,              # 시총 1000억+ 통과
    "trade_amount_pass": 0,      # 거래대금 200억+ 통과
    "limit_up_excluded": 0,      # 상한가 (+30%) 제외 카운트
    "final_prepared": 0,         # 최종 _last_scan_result 길이
    "last_run_at": None,
}

# 추가 필터 조건
MIN_MARKET_CAP = 100_000_000_000      # 시총 1000억 이상
MIN_TRADE_AMOUNT = 20_000_000_000     # 거래대금 200억 이상
MAX_STOCKS = 40                        # 최대 구독 종목 수

# Breakout(VB/LTV) 후순위 슬롯 cap (2026-05-13 작업 2 — momentum 보호).
# 2026-05-13 08:57:39 운영 로그에서 vb=30+ltv=30 → dedup 28 breakout 점유 후
# 09:30 momentum 발화 시 41 한도 초과 → momentum drop 위험 노출. breakout 을
# 25개로 cap 해 잔여 슬롯을 momentum 에 보장한다.
# 명세: `_workspace/00_leader_trading_rules.md` (2026-05-13) 작업 2.
BREAKOUT_LOW_CAP = 25

# ETF/ETN 제외 키워드
ETF_KEYWORDS = ("KODEX", "TIGER", "KBSTAR", "KOSEF", "ARIRANG", "SOL", "ACE",
                "RISE", "KoAct", "PLUS", "TIMEFOLIO", "WOORI", "FOCUS",
                "HANARO", "히어로즈", "마이티", "BNK", "MASTER", "WON",
                "ETN", "선물", "인버스", "레버리지", "채권", "혼합")

# 실시간 체결가 TR_ID — 사이클 26 (2026-05-20): 시간대별 채널 분리
# - PRE/POST NXT 시간대: H0NXCNT0 (NXT 전용 체결가)
# - KRX MAIN 시간대: H0STCNT0 (KRX 전용 체결가)
# 기존 H0UNCNT0 (통합) 상수는 하위 호환용으로 보존 (scheduler._execute_next_day_clear 등 직접 참조)
TICK_TR_ID = "H0UNCNT0"  # (deprecated: 사이클 26 이후 get_active_tick_tr_ids() 사용)
TICK_TR_ID_KRX = "H0STCNT0"   # KRX 메인 전용 (09:00~15:39:59)
TICK_TR_ID_NXT = "H0NXCNT0"   # NXT 프리/애프터 전용 (08:00~08:59:59, 15:40~20:00)

# 시간 경계 상수 (사이클 26 — get_active_tick_tr_ids 내부 사용)
from datetime import time as _time

_TIME_PRE_NXT_START = _time(8, 0)
_TIME_KRX_PRESUBSCRIBE = _time(8, 59, 10)   # KRX 채널 사전 구독 시작 마진
_TIME_KRX_MAIN_START = _time(9, 0)
_TIME_KRX_MAIN_END = _time(15, 30)
_TIME_NXT_PRESUBSCRIBE = _time(15, 39, 10)  # NXT 채널 사전 구독 시작 마진
_TIME_POST_NXT_START = _time(15, 40)
_TIME_POST_NXT_END = _time(20, 0)


def get_active_tick_tr_ids(now_t: "_time | None" = None) -> "set[str]":
    """현재 KST 시각 기준 활성 시세 채널 TR_ID set 반환.

    사이클 26 (2026-05-20) — 시세 채널 시간대별 분리:

    | 구간                      | TR_ID                        | 설명           |
    |---------------------------|------------------------------|----------------|
    | 08:00~08:59:09            | {H0NXCNT0}                   | NXT 프리       |
    | 08:59:10~08:59:59         | {H0NXCNT0, H0STCNT0}         | KRX 사전 마진  |
    | 09:00:00~15:29:59         | {H0STCNT0}                   | KRX 메인       |
    | 15:30:00~15:39:09         | {H0STCNT0}                   | 종가 흡수 마진 |
    | 15:39:10~15:39:59         | {H0STCNT0, H0NXCNT0}         | NXT 사전 마진  |
    | 15:40:00~19:59:59         | {H0NXCNT0}                   | NXT 애프터     |

    사전 마진 50초 구간에서는 두 채널 동시 활성 — 종목별 원자 전환 진행 중
    (_board_transition_loop) + on_tick 중복 호출 안전 (scanner.ticker_prices 마지막 값 채택).

    Returns:
        set[str]: 활성 TR_ID 집합. 장 외 시간이면 빈 집합.
    """
    from datetime import datetime, timezone, timedelta

    if now_t is None:
        kst = timezone(timedelta(hours=9))
        now_t = datetime.now(kst).time()

    # PRE_NXT 구간: 08:00~08:59:09
    if _TIME_PRE_NXT_START <= now_t < _TIME_KRX_PRESUBSCRIBE:
        return {TICK_TR_ID_NXT}

    # KRX 사전 마진: 08:59:10~08:59:59
    if _TIME_KRX_PRESUBSCRIBE <= now_t < _TIME_KRX_MAIN_START:
        return {TICK_TR_ID_NXT, TICK_TR_ID_KRX}

    # KRX 메인 + 종가 흡수 마진: 09:00~15:39:09
    if _TIME_KRX_MAIN_START <= now_t < _TIME_NXT_PRESUBSCRIBE:
        return {TICK_TR_ID_KRX}

    # NXT 사전 마진: 15:39:10~15:39:59
    if _TIME_NXT_PRESUBSCRIBE <= now_t < _TIME_POST_NXT_START:
        return {TICK_TR_ID_KRX, TICK_TR_ID_NXT}

    # POST_NXT: 15:40~19:59:59
    if _TIME_POST_NXT_START <= now_t < _TIME_POST_NXT_END:
        return {TICK_TR_ID_NXT}

    # 장 외 (08:00 이전, 20:00 이후)
    return set()


async def scan_stocks() -> list[str]:
    """당일 급등 종목을 스캔하여 매수 후보를 반환한다.

    1. 등락률 순위 API로 15%+ 상승 종목 조회
    2. ETF/ETN 제외
    3. 시총 1,000억 이상, 거래대금 200억 이상 필터
    4. 등락률 30%+ (상한가) 제외 — momentum 매수 신호 차단과 일관 (사이클 21)
    5. 최대 40종목 제한

    사이클 21 — 단계별 카운트는 `scan_filter_stats` 모듈 전역 dict 에 누적.
    MomentumStrategy.get_scan_stats() 가 그 사본을 반환 → ScanMonitor 깔때기.
    """
    raw_list = await fetch_rising_stocks()
    filtered: list[str] = []

    # 사이클 21 — 카운트 초기화
    scan_filter_stats["universe_candidates"] = len(raw_list)
    scan_filter_stats["rate_pass"] = 0
    scan_filter_stats["mcap_pass"] = 0
    scan_filter_stats["trade_amount_pass"] = 0
    scan_filter_stats["limit_up_excluded"] = 0
    scan_filter_stats["final_prepared"] = 0

    for item in raw_list:
        # 등락률 순위 API 필드명: stck_shrn_iscd (거래량 순위는 mksc_shrn_iscd)
        ticker = item.get("stck_shrn_iscd") or item.get("mksc_shrn_iscd", "")
        name = item.get("hts_kor_isnm", "")
        change_rate = float(item.get("prdy_ctrt", "0"))
        price = int(item.get("stck_prpr", "0"))
        listed_shares = int(item.get("lstn_stcn", "0"))
        trade_amount = int(item.get("acml_tr_pbmn", "0"))

        # 종목코드 형식 검증 — 6자리 숫자만 허용 (ETF·ETN·신주인수권 등 알파벳 포함 코드 차단)
        if not (len(ticker) == 6 and ticker.isdigit()):
            continue

        # 등락률 15% 미만 제외
        if change_rate < MIN_CHANGE_RATE:
            continue
        # 사이클 21 — 등락률 통과 단독 카운트
        scan_filter_stats["rate_pass"] += 1

        # ETF/ETN 제외
        if any(kw in name for kw in ETF_KEYWORDS):
            continue

        # 시총/거래대금 필터 (데이터 없으면 = 거래량 순위에 미포함 = 소형주 → 제외)
        market_cap = price * listed_shares
        mcap_ok = market_cap >= MIN_MARKET_CAP
        trade_ok = trade_amount >= MIN_TRADE_AMOUNT
        # 사이클 21 — 시총/거래대금 단독 통과 카운트 (분리)
        if mcap_ok:
            scan_filter_stats["mcap_pass"] += 1
        if trade_ok:
            scan_filter_stats["trade_amount_pass"] += 1

        if not mcap_ok:
            continue
        if not trade_ok:
            continue

        # 사이클 21 — 상한가 (등락률 30%+) 제외. momentum 매수 신호 차단(check_buy_signal:73)과 일관.
        if change_rate >= 30.0:
            scan_filter_stats["limit_up_excluded"] += 1
            continue

        filtered.append(ticker)
        if name:
            ticker_names[ticker] = name
        ticker_market_info[ticker] = {
            "market_cap": round(market_cap / 1e8),
            "trade_amount": round(trade_amount / 1e8),
        }

        logger.debug(
            "스캔 통과: %s 등락률=+%.1f%% 시총=%.0f억 거래대금=%.0f억",
            name or ticker, change_rate, market_cap / 1e8, trade_amount / 1e8,
        )

        if len(filtered) >= MAX_STOCKS:
            break

    global _last_scan_result, _last_scan_time
    _last_scan_result = filtered
    _last_scan_time = datetime.now().strftime("%H:%M:%S")

    # 사이클 21 — 최종 카운트 + last_run_at
    scan_filter_stats["final_prepared"] = len(filtered)
    scan_filter_stats["last_run_at"] = datetime.now(KST_TZ).isoformat()

    logger.info(
        "급등종목 스캔: %d종목 통과 (전체 %d종목, 15%%+ 상승 기준)",
        len(filtered), len(raw_list),
    )
    return filtered


def get_scan_status() -> dict:
    """스캔 현황을 반환한다. 모멘텀 + 구독 중인 모든 종목의 데이터를 포함.

    **사이클 11 (2026-05-18) — 풀 전체 카운트**: 메인 세션(`kis_ws._subscriptions`)
    단독이 아니라 `kis_ws_pool.get_subscribed_tickers()` / `get_acked_tickers()` 합집합
    으로 카운트한다. 보조 세션(quote-N) 에 분배된 종목도 가시화 — 운영자가 ScanMonitor
    에서 "subscribed_count=0 / tick_coverage_total=0" 표시를 보던 결함 (2026-05-18
    09:00 KRX 진입 시 31 종목 보조 세션 구독에도 0 표시) 차단.
    """
    subscribed_set = kis_ws_pool.get_subscribed_tickers()
    subscribed = sorted(subscribed_set)
    # 모멘텀 스캔 + 구독 종목 합집합 (VB 종목도 포함)
    all_relevant = set(_last_scan_result) | subscribed_set

    # G3 (2026-05-12) — tick_coverage 4종 카운트 노출.
    # 운영자가 status 단일 호출로 SEND/ACK/fresh/stale 격차 즉시 인지.
    acked_set = kis_ws_pool.get_acked_tickers()
    # G3: 60s 임계는 Phase D `_report_tick_coverage` 와 동일 — 운영 일관성
    now = datetime.now(KST_TZ)
    threshold = timedelta(seconds=60)
    _min_dt = datetime.min.replace(tzinfo=KST_TZ)
    fresh_count = sum(
        1 for t in subscribed_set
        if (now - ticker_last_tick.get(t, _min_dt)) <= threshold
    )
    stale_count = len(subscribed_set) - fresh_count

    return {
        "filtered_tickers": _last_scan_result,
        "filtered_count": len(_last_scan_result),
        "subscribed_tickers": subscribed,
        "subscribed_count": len(subscribed),
        "last_scan_time": _last_scan_time,
        "ticker_names": {k: v for k, v in ticker_names.items() if k in all_relevant},
        "ticker_prices": {k: v for k, v in ticker_prices.items() if k in all_relevant},
        "ticker_market_info": {k: v for k, v in ticker_market_info.items() if k in all_relevant},
        # G3 — 운영자 가시화용 보조 카운트
        "tick_coverage_total": len(subscribed_set),
        "tick_coverage_acked": len(acked_set),
        "tick_coverage_fresh": fresh_count,
        "tick_coverage_stale": stale_count,
    }


def t(ticker: str) -> str:
    """종목코드를 '종목명(코드)' 형태로 반환한다."""
    name = ticker_names.get(ticker)
    return f"{name}({ticker})" if name else ticker


def resolve_ticker_name(ticker: str | None) -> str:
    """종목명 단일 lookup — 사이클 44 (2026-05-22, refactor-review 카드 #7).

    기존 4 경로 (ticker_names / STATIC_TICKER_NAMES / strategy_base._resolve_ticker_name / t())
    통합. 단일 진입점 — 폴백 순서 고정:

    1. `ticker_names` (동적, WS 시세 수신 시 갱신) — 1순위
    2. `STATIC_TICKER_NAMES` (정적, scanner.py 자기 파일 정규식 파싱) — 2순위
    3. `""` (빈 문자열, lookup miss — 예외 전파 금지, graceful)

    Args:
        ticker: 6자리 종목코드 (또는 None/빈 문자열 — graceful).

    Returns:
        종목명 또는 빈 문자열 (lookup miss).

    Note:
        본 함수는 lookup only — `ticker_names` 갱신은 WebSocket `_handle_raw` 또는
        `subscribe_filtered_stocks` 가 담당. 호출 시 dict snapshot 보장 안 됨
        (동시성 무해 — 빈 문자열 폴백).
    """
    if not ticker:
        return ""
    try:
        # 1차: 동적 매핑 (WS 시세 수신 시 갱신)
        name = ticker_names.get(ticker)
        if name:
            return name
        # 2차: 정적 매핑 (scanner.py 모듈 시드)
        return STATIC_TICKER_NAMES.get(ticker, "") or ""
    except (AttributeError, TypeError):
        # graceful — dict 접근 예외 (모듈 import 순서 / mock 등)
        return ""


# KOSPI 200 대표 종목 (하드코딩, 향후 API 조회로 변경 가능) — 시총 상위 위주
KOSPI_200_TICKERS = [
    "005930",  # 삼성전자
    "000660",  # SK하이닉스
    "373220",  # LG에너지솔루션
    "207940",  # 삼성바이오로직스
    "005380",  # 현대차
    "000270",  # 기아
    "005935",  # 삼성전자우
    "068270",  # 셀트리온
    "005490",  # POSCO홀딩스
    "035420",  # NAVER
    "006400",  # 삼성SDI
    "051910",  # LG화학
    "105560",  # KB금융
    "055550",  # 신한지주
    "012330",  # 현대모비스
    "028260",  # 삼성물산
    "035720",  # 카카오
    "086790",  # 하나금융지주
    "032830",  # 삼성생명
    "138040",  # 메리츠금융지주
    "066570",  # LG전자
    "017670",  # SK텔레콤
    "316140",  # 우리금융지주
    "015760",  # 한국전력
    "003670",  # 포스코퓨처엠
    "010130",  # 고려아연
    "024110",  # 기업은행
    "034730",  # SK
    "030200",  # KT
    "009150",  # 삼성전기
    "011200",  # HMM
    "018260",  # 삼성에스디에스
    "033780",  # KT&G
    "010950",  # S-Oil
    "096770",  # SK이노베이션
    "267260",  # HD현대일렉트릭
    "267250",  # HD현대
    "329180",  # HD현대중공업
    "010140",  # 삼성중공업
    "042660",  # 한화오션
    "004020",  # 현대제철
    "086280",  # 현대글로비스
    "000810",  # 삼성화재
    "402340",  # SK스퀘어
    "012450",  # 한화에어로스페이스
    "079550",  # LIG넥스원
    "047810",  # 한국항공우주
    "272210",  # 한화시스템
    "352820",  # 하이브
    "041510",  # 에스엠
    "035900",  # JYP Ent.
    "377300",  # 카카오페이
    "323410",  # 카카오뱅크
    "259960",  # 크래프톤
    "036570",  # 엔씨소프트
    "251270",  # 넷마블
    "180640",  # 한진칼
    "003490",  # 대한항공
    "002350",  # 넥센타이어
    "161390",  # 한국타이어앤테크놀로지
    "271560",  # 오리온
    "097950",  # CJ제일제당
    "271940",  # 일동홀딩스
    "139480",  # 이마트
    "069960",  # 현대백화점
    "023530",  # 롯데쇼핑
    "282330",  # BGF리테일
    "007310",  # 오뚜기
    "004990",  # 롯데지주
    "001040",  # CJ
    "078930",  # GS
    "000720",  # 현대건설
    "375500",  # DL이앤씨
    "047040",  # 대우건설
    "028050",  # 삼성엔지니어링
    "302440",  # SK바이오사이언스
    "326030",  # SK바이오팜
    "003550",  # LG
    "034220",  # LG디스플레이
    "011070",  # LG이노텍
]

# KOSDAQ 150 대표 종목 (하드코딩, 향후 API 조회로 변경 가능)
KOSDAQ_150_TICKERS = [
    "247540",  # 에코프로비엠
    "091990",  # 셀트리온헬스케어
    "086520",  # 에코프로
    "263750",  # 펄어비스
    "293490",  # 카카오게임즈
    "328130",  # 루닛
    "145020",  # 휴젤
    "196170",  # 알테오젠
    "067160",  # 아프리카TV
    "041510",  # 에스엠
    "112040",  # 위메이드
    "068270",  # 셀트리온제약
    "035720",  # 카카오
    "035420",  # NAVER
    "051910",  # LG화학
    "253450",  # 스튜디오드래곤
    "357780",  # 솔브레인
    "058470",  # 리노공업
    "214150",  # 클래시스
    "277810",  # 레인보우로보틱스
    "039030",  # 이오테크닉스
    "078600",  # 대주전자재료
    "095340",  # ISC
    "240810",  # 원익IPS
    "141080",  # 레고켐바이오
    "131970",  # 테스나
    "137310",  # 에스디바이오센서
    "140410",  # 메지온
    "060310",  # 3S
    "383220",  # F&F
    "403870",  # HPSP
    "041190",  # 우리기술투자
    "336260",  # 두산테스나
    "108860",  # 셀바스AI
    "222080",  # 씨아이에스
    "089030",  # 테크윙
    "009520",  # 포스코엠텍
    "234080",  # JW생명과학
    "036930",  # 주성엔지니어링
    "330860",  # 네이처셀
]


def scan_kosdaq150() -> list[str]:
    """KOSDAQ 150 종목 리스트를 반환한다."""
    return list(KOSDAQ_150_TICKERS)


def scan_kospi200() -> list[str]:
    """KOSPI 200 종목 리스트를 반환한다."""
    return list(KOSPI_200_TICKERS)


# 정적 종목명 dict — KOSPI_200_TICKERS / KOSDAQ_150_TICKERS의 인라인 코멘트(`# 종목명`)를
# 모듈 import 시 1회 정규식으로 추출. KIS API가 hts_kor_isnm을 빈 문자열로 응답하는 케이스
# (예: 일부 종목, 모의/실전 차이)에서 프론트가 "KOSPI200(005930)" 같은 시장명 표시로
# 떨어지지 않도록 ticker_names의 fallback으로 사용.
import os as _os
import re as _re

_STATIC_TICKER_NAME_RE = _re.compile(r'"(\d{6})",\s*#\s*([^\n]+)')


def _parse_static_ticker_names() -> dict[str, str]:
    try:
        with open(_os.path.abspath(__file__), encoding="utf-8") as f:
            src = f.read()
        return {m.group(1): m.group(2).strip() for m in _STATIC_TICKER_NAME_RE.finditer(src)}
    except Exception:
        return {}


STATIC_TICKER_NAMES: dict[str, str] = _parse_static_ticker_names()
# ticker_names의 시드 — KIS 응답이 비면 이 값이 그대로 노출됨. KIS 정상 응답 시 덮어씀.
ticker_names.update(STATIC_TICKER_NAMES)


async def subscribe_filtered_stocks(
    tickers: list[str],
    extra_tickers: list[str] | None = None,
    source_counts: dict[str, int] | None = None,
    *,
    priority_groups: dict[str, list[str]] | None = None,
) -> None:
    """필터링된 종목들에 대해 WebSocket 실시간 시세 구독을 등록한다.

    모멘텀 후보 + 추가 종목(변동성돌파 등)의 합집합을 구독한다.

    `source_counts` 가 주어지면 출처별 카운터를 로그에 노출한다 (Phase B, 2026-05-12):
        [scanner] 실시간 시세 구독 완료: total=N (vb=A, ltv=B, swing=C, momentum=D, positions=E)
    - 출처별 카운트는 합집합 *전* 원본 개수 (중복 가능)
    - total 은 합집합(dedupe) 후 실제 구독 종목 수
    - 영문 라벨 유지 (Grafana/Loki 쿼리 안정성)
    - dict 가 None 이면 기존 "(모멘텀: X, 기타: Y)" fallback (외부 호출자 호환)
    - 누락 키는 0 으로 처리

    `priority_groups` 가 주어지면 우선순위 큐로 변환해 구독한다 (E1, 2026-05-12 + G안 2026-05-12):
        positions → next_day_clear → breakout → momentum → swing (HIGH → LOW)
    - positions / next_day_clear 는 `bypass_limit=True` 로 한도(MAX_SUBSCRIPTIONS=41) 무시 — 절대 보장
    - LOW 순서 재정렬 (G안, 2026-05-12): 슬롯 부족 시 swing 이 가장 먼저 잘려도 안전.
      donchian_swing 은 Pull 폴링(_swing_buy_poll_loop)으로 매수 평가하므로 LOW 슬롯 잃어도 OK.
      변동성 돌파(VB/LTV) 후보를 우선 보장해 일중 매매 기회 확보.
    - 후순위(breakout/momentum/swing)는 잔여 슬롯만큼만 add
    - 중복 종목은 HIGH 순위로 1회만 subscribe (후순위에서는 skip, drop 카운트에도 미포함)
    - drop>0 발생 시 INFO 로그 1행 + WARNING system_logs 영구 저장 (가설 A — 가시성):
      `[priority_drop] breakout=X momentum=Y swing=Z total_subscribed=N max=41 high_count=H low_remaining=R`
    - HIGH 단독 합계가 한도 초과 시 ERROR 로그 + system_logs 기록 (운영자 경보)
    - `priority_groups=None` 이면 기존 평탄 처리 (외부 호환). `source_counts` 로그는 priority_groups 와 무관하게 보존
    - 어제·오늘 donchian_swing 조기 손절 사건(보유 종목 시세 누락) 루트 원인 차단
    """
    extra = extra_tickers or []
    all_tickers = list(dict.fromkeys(tickers + extra))  # 순서 유지 중복 제거

    if priority_groups is not None:
        # 우선순위 큐: HIGH → LOW
        positions = list(dict.fromkeys(priority_groups.get("positions") or []))
        next_day_clear = list(dict.fromkeys(priority_groups.get("next_day_clear") or []))
        swing = list(dict.fromkeys(priority_groups.get("swing") or []))
        momentum = list(dict.fromkeys(priority_groups.get("momentum") or []))
        breakout = list(dict.fromkeys(priority_groups.get("breakout") or []))

        from src.realtime.websocket import MAX_SUBSCRIPTIONS

        # HIGH 단독 한도 초과 — 이상 케이스 (운영자 경보)
        high_total = len(positions) + len(next_day_clear)
        if high_total > MAX_SUBSCRIPTIONS:
            logger.error(
                "HIGH 우선순위 구독 한도 초과: positions=%d next_day_clear=%d limit=%d",
                len(positions), len(next_day_clear), MAX_SUBSCRIPTIONS,
            )
            try:
                from src.db.system_logs import write_log
                await write_log(
                    "ERROR",
                    f"[priority] HIGH 구독 한도 초과: positions={len(positions)} "
                    f"next_day_clear={len(next_day_clear)} limit={MAX_SUBSCRIPTIONS}",
                )
            except Exception:
                # DB 로깅 실패는 흡수 — 실제 구독 흐름은 계속
                logger.debug("HIGH 한도 초과 system_logs 기록 실패", exc_info=True)

        already: set[str] = set()
        # 사이클 15-A (2026-05-19) — 이미 풀에 구독 중인 LOW 종목은 SEND skip (KIS 정상 패턴).
        # HIGH 종목 (positions / next_day_clear) 은 always 호출 — 풀의 _select_session 이
        # promote (보조→메인 이동) 또는 noop 판단. 사전에 skip 하면 promote 차단됨.
        already_in_pool: set[str] = set(kis_ws_pool.get_subscribed_tickers())
        # 사이클 7-C — 풀로 위임. priority="HIGH"/"LOW" + bypass_limit 명시 전달.
        # 보조 세션 0개 시 풀이 메인으로 fallback (회귀 0).
        # 1) positions — priority='HIGH', bypass_limit=True (절대 보장, promote 보존)
        for t in positions:
            if t in already:
                continue
            already.add(t)
            await kis_ws_pool.subscribe(
                TICK_TR_ID, t, priority="HIGH", bypass_limit=True,
            )
        # 2) next_day_clear — priority='HIGH', bypass_limit=True (절대 보장)
        for t in next_day_clear:
            if t in already:
                continue
            already.add(t)
            await kis_ws_pool.subscribe(
                TICK_TR_ID, t, priority="HIGH", bypass_limit=True,
            )

        # 3~5) 후순위 — 2-pass 슬롯 흡수 (PR-E P1, 2026-05-15)
        # LOW 순서 (G안, 2026-05-12): breakout → momentum → swing.
        # donchian_swing 은 Pull 폴링으로 매수 평가하므로 슬롯 손실 안전.
        #
        # PR-E (P1, 2026-05-15) — 2-pass 슬롯 흡수:
        #   1차: positions(bypass) → next_day_clear(bypass) → breakout[:cap] → momentum → swing
        #   2차: 잔여 슬롯 (MAX - len(_subscriptions)) > 0 이면
        #        breakout cap 초과분(overflow) 에서 추가 add
        #   최종 drop = max(0, len(overflow) - actually_added_in_2nd_pass)
        # 결함 (운영 로그 2026-05-15 07:55:08):
        #   [priority_drop] breakout=3 ... total_subscribed=30 max=41 ... low_remaining=11
        #   → 11 슬롯 미사용인데도 breakout overflow 3 종목이 silently drop 되어 운영 슬롯 낭비.
        # 2-pass 로 잔여 슬롯에 overflow 를 흡수해 슬롯 낭비 + 부당 drop 동시 차단.
        drop_counts: dict[str, int] = {"breakout": 0, "momentum": 0, "swing": 0}

        # 작업 2 (2026-05-13): breakout cap 25 — momentum 슬롯 보호.
        # 1차에서는 cap 만 add, overflow 는 2차에서 잔여 슬롯에 흡수.
        breakout_primary: list[str]
        breakout_overflow: list[str]
        if len(breakout) > BREAKOUT_LOW_CAP:
            breakout_primary = breakout[:BREAKOUT_LOW_CAP]
            breakout_overflow = breakout[BREAKOUT_LOW_CAP:]
        else:
            breakout_primary = breakout
            breakout_overflow = []

        # 1-pass: cap 적용된 breakout + momentum + swing 순서로 add
        # 사이클 7-C — 풀로 위임. priority='LOW' (보조 세션 라운드로빈 우선, 메인 fallback).
        # 사이클 15-A — 이미 풀에 있는 LOW 종목은 SEND skip (KIS 정상 패턴 준수).
        for label, candidates in (
            ("breakout", breakout_primary),
            ("momentum", momentum),
            ("swing", swing),
        ):
            for t in candidates:
                if t in already:
                    # 중복 제거 — drop 카운트에 포함하지 않음 (이미 구독했으므로)
                    continue
                if t in already_in_pool:
                    # 사이클 15-A: 이미 풀에 LOW 로 구독 중 — KIS SEND skip
                    already.add(t)
                    continue
                remaining = MAX_SUBSCRIPTIONS - len(kis_ws._subscriptions)
                if remaining <= 0:
                    drop_counts[label] += 1
                    continue
                already.add(t)
                await kis_ws_pool.subscribe(
                    TICK_TR_ID, t, priority="LOW", bypass_limit=False,
                )

        # 2-pass: breakout overflow 잔여 슬롯 흡수
        # 흡수에 성공한 만큼 drop 에서 차감. 흡수 실패분만 최종 drop["breakout"] 에 합산.
        # Codex P2 / Copilot (2026-05-15) — 중복(이미 구독된 종목) skip 분리 카운트:
        # `t in already` 로 skip 된 ticker 는 실제로 다른 그룹에 의해 이미 구독 중이라
        # drop 아님. `skipped_already` 카운터로 분리해 최종 drop 계산에서 차감.
        # 미차감 시 false `[priority_drop] breakout=...` 영구 WARNING 발생.
        absorbed_overflow = 0
        skipped_already = 0
        for t in breakout_overflow:
            if t in already:
                # 다른 그룹(positions/next_day_clear/breakout_primary/momentum/swing)
                # 이 이미 구독한 종목 — drop 아닌 중복
                skipped_already += 1
                continue
            if t in already_in_pool:
                # 사이클 15-A: 이미 풀에 LOW 로 구독 중 — KIS SEND skip (drop 아님)
                already.add(t)
                skipped_already += 1
                continue
            remaining = MAX_SUBSCRIPTIONS - len(kis_ws._subscriptions)
            if remaining <= 0:
                # 잔여 0 — 더 이상 흡수 불가
                break
            already.add(t)
            absorbed_overflow += 1
            # 사이클 7-C — overflow 도 LOW priority 로 풀에 위임
            await kis_ws_pool.subscribe(
                TICK_TR_ID, t, priority="LOW", bypass_limit=False,
            )
        # 흡수 못 한 overflow 만 최종 drop 에 합산 (중복 skip 차감).
        drop_counts["breakout"] += max(
            0, len(breakout_overflow) - absorbed_overflow - skipped_already
        )

        total_dropped = sum(drop_counts.values())
        if total_dropped > 0:
            # 확장 형식 (가설 A 가시성): total_subscribed/max/high_count/low_remaining 추가.
            # Copilot P2 (2026-05-12): `low_remaining` 으로 의미 명확화(LOW 그룹 잔여 슬롯) +
            # HIGH bypass 시 음수 노출 차단(`max(0, ...)`) — 대시보드 해석 혼동 방지.
            total_subscribed = len(kis_ws._subscriptions)
            high_count = len(set(positions) | set(next_day_clear))
            low_remaining = max(0, MAX_SUBSCRIPTIONS - total_subscribed)
            drop_log = (
                f"[priority_drop] breakout={drop_counts['breakout']} "
                f"momentum={drop_counts['momentum']} swing={drop_counts['swing']} "
                f"total_subscribed={total_subscribed} max={MAX_SUBSCRIPTIONS} "
                f"high_count={high_count} low_remaining={low_remaining}"
            )
            logger.info(drop_log)
            # drop 발생은 운영 가시화 대상 — WARNING 영구 저장 (가설 A)
            try:
                from src.db.system_logs import write_log
                await write_log("WARNING", drop_log)
            except Exception:
                logger.debug("[priority_drop] write_log 실패", exc_info=True)
    else:
        # 기존 평탄 처리 (외부 호환 fallback)
        for ticker in all_tickers:
            await kis_ws.subscribe(TICK_TR_ID, ticker)

    if source_counts is not None:
        vb = int(source_counts.get("vb", 0))
        ltv = int(source_counts.get("ltv", 0))
        bfb = int(source_counts.get("bfb", 0))
        vcp = int(source_counts.get("vcp", 0))
        swing_c = int(source_counts.get("swing", 0))
        momentum_c = int(source_counts.get("momentum", 0))
        positions_c = int(source_counts.get("positions", 0))
        logger.info(
            "실시간 시세 구독 완료: total=%d "
            "(vb=%d, ltv=%d, bfb=%d, vcp=%d, swing=%d, momentum=%d, positions=%d)",
            len(all_tickers), vb, ltv, bfb, vcp, swing_c, momentum_c, positions_c,
        )
    else:
        logger.info("실시간 시세 구독 완료: %d종목 (모멘텀: %d, 기타: %d)",
                    len(all_tickers), len(tickers), len(extra))


async def unsubscribe_all() -> None:
    """모든 종목 구독을 해제한다 (메인 + 보조 세션 전체)."""
    # 사이클 13-E-1 리뷰 ③ — 실패 카운터 + 조건부 로그 레벨.
    # 일부 구독 해제 실패 시 INFO "완료" 로그가 운영자에게 잘못된 신호를 보내지 않도록
    # 실패 개수를 집계해 WARNING 으로 격상 + 성공은 무실패 시에만 INFO.
    pool_failures = 0
    main_failures = 0

    # WebsocketPool 위임 — _ticker_to_session 추적까지 일괄 정리
    try:
        await kis_ws_pool.unsubscribe_all()
    except Exception:
        logger.warning("[scanner_unsubscribe_all] pool.unsubscribe_all 실패", exc_info=True)
        pool_failures = 1

    # 보강: pool 분배 추적에 없는 메인 직접 구독 (체결통보 제외 TICK) 잔존 정리
    for tr_id, tr_key in list(kis_ws._subscriptions):
        if tr_id == TICK_TR_ID:
            try:
                await kis_ws.unsubscribe(tr_id, tr_key)
            except Exception:
                logger.debug("[scanner_unsubscribe_all] main 잔여 해제 실패", exc_info=True)
                main_failures += 1

    total_failures = pool_failures + main_failures
    if total_failures > 0:
        logger.warning(
            "[scanner_unsubscribe_all] 일부 구독 해제 실패 — pool=%d, main=%d",
            pool_failures, main_failures,
        )
    else:
        logger.info("모든 시세 구독 해제 완료")
