"""조건검색 API 모듈 — 등락률 순위 + 개별 종목 시세 조회.

1단계: 등락률 순위 API로 당일 급등 종목(15%+) 후보 확보
2단계: 각 종목의 현재가 시세 API로 시총/거래대금 조회 → 필터링

모의투자(VTS)에서는 등락률 순위 API를 지원하지 않으므로 테스트 종목으로 대체.
현재가 시세 API(FHKST01010100)는 모의/실전 동일 TR_ID로 양쪽 모두 동작.
"""

import asyncio
import logging

from src.api.base import KisApiError, kis_get
from src.config import settings

logger = logging.getLogger(__name__)

FLUCTUATION_RANK_URL = "/uapi/domestic-stock/v1/ranking/fluctuation"
STOCK_PRICE_URL = "/uapi/domestic-stock/v1/quotations/inquire-price"
DAILY_PRICE_URL = "/uapi/domestic-stock/v1/quotations/inquire-daily-price"

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
    data = await kis_get(FLUCTUATION_RANK_URL, "FHPST01700000", params)
    return data.get("output", [])


async def fetch_stock_detail(ticker: str) -> dict:
    """개별 종목의 현재가/시총/거래대금을 조회한다.

    FHKST01010100은 모의/실전 동일 TR_ID.
    """
    params = {
        "fid_cond_mrkt_div_code": "J",
        "fid_input_iscd": ticker,
    }
    data = await kis_get(STOCK_PRICE_URL, "FHKST01010100", params)
    return data.get("output", {})


async def fetch_daily_candles(ticker: str, days: int = 21) -> list[dict]:
    """KIS 일봉 API로 최근 N일 일봉 데이터를 조회한다.

    반환: [{"stck_bsop_date", "stck_oprc"(시가), "stck_hgpr"(고가),
            "stck_lwpr"(저가), "stck_clpr"(종가), ...}, ...]
    """
    from datetime import date, timedelta

    end_date = date.today().strftime("%Y%m%d")
    start_date = (date.today() - timedelta(days=days + 10)).strftime("%Y%m%d")  # 여유분

    params = {
        "fid_cond_mrkt_div_code": "J",
        "fid_input_iscd": ticker,
        "fid_input_date_1": start_date,
        "fid_input_date_2": end_date,
        "fid_period_div_code": "D",
        "fid_org_adj_prc": "0",
    }
    data = await kis_get(DAILY_PRICE_URL, settings.get_tr_id("FHKST01010400"), params)
    output = data.get("output", [])
    # 최근 N일만 반환 (API가 최신순으로 내려줌)
    return output[:days]


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
