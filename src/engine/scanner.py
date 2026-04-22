"""종목 필터링 모듈.

등락률 순위 API 결과에서 당일 급등 종목(15%+ 상승)을 필터링하고,
시총/거래대금 조건을 추가 적용한 뒤 WebSocket 실시간 시세 구독을 등록한다.

매수 조건이 시가 대비 +29.5%이므로, 이미 15% 이상 상승 중인 종목을
후보군으로 잡아 29.5% 도달을 감시한다.
"""

import logging
from datetime import datetime

from src.api.condition import MIN_CHANGE_RATE, fetch_rising_stocks
from src.realtime.websocket import kis_ws

logger = logging.getLogger(__name__)

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

# 추가 필터 조건
MIN_MARKET_CAP = 100_000_000_000      # 시총 1000억 이상
MIN_TRADE_AMOUNT = 20_000_000_000     # 거래대금 200억 이상
MAX_STOCKS = 40                        # 최대 구독 종목 수

# ETF/ETN 제외 키워드
ETF_KEYWORDS = ("KODEX", "TIGER", "KBSTAR", "KOSEF", "ARIRANG", "SOL", "ACE",
                "ETN", "선물", "인버스", "레버리지")

# 실시간 체결가 TR_ID
TICK_TR_ID = "H0STCNT0"


async def scan_stocks() -> list[str]:
    """당일 급등 종목을 스캔하여 매수 후보를 반환한다.

    1. 등락률 순위 API로 15%+ 상승 종목 조회
    2. ETF/ETN 제외
    3. 시총 1,000억 이상, 거래대금 200억 이상 필터
    4. 최대 40종목 제한
    """
    raw_list = await fetch_rising_stocks()
    filtered: list[str] = []

    for item in raw_list:
        # 등락률 순위 API 필드명: stck_shrn_iscd (거래량 순위는 mksc_shrn_iscd)
        ticker = item.get("stck_shrn_iscd") or item.get("mksc_shrn_iscd", "")
        name = item.get("hts_kor_isnm", "")
        change_rate = float(item.get("prdy_ctrt", "0"))
        price = int(item.get("stck_prpr", "0"))
        listed_shares = int(item.get("lstn_stcn", "0"))
        trade_amount = int(item.get("acml_tr_pbmn", "0"))

        # 등락률 15% 미만 제외
        if change_rate < MIN_CHANGE_RATE:
            continue

        # ETF/ETN 제외
        if any(kw in name for kw in ETF_KEYWORDS):
            continue

        # 시총/거래대금 필터 (데이터 없으면 = 거래량 순위에 미포함 = 소형주 → 제외)
        market_cap = price * listed_shares
        if market_cap < MIN_MARKET_CAP:
            continue
        if trade_amount < MIN_TRADE_AMOUNT:
            continue

        filtered.append(ticker)
        if name:
            ticker_names[ticker] = name
        ticker_market_info[ticker] = {
            "market_cap": round(market_cap / 1e8),
            "trade_amount": round(trade_amount / 1e8),
        }

        logger.debug(
            "스캔 통과: %s 등락률=+%.1f%% 시총=%,.0f억 거래대금=%,.0f억",
            name or ticker, change_rate, market_cap / 1e8, trade_amount / 1e8,
        )

        if len(filtered) >= MAX_STOCKS:
            break

    global _last_scan_result, _last_scan_time
    _last_scan_result = filtered
    _last_scan_time = datetime.now().strftime("%H:%M:%S")

    logger.info(
        "급등종목 스캔: %d종목 통과 (전체 %d종목, 15%%+ 상승 기준)",
        len(filtered), len(raw_list),
    )
    return filtered


def get_scan_status() -> dict:
    """스캔 현황을 반환한다."""
    subscribed = [
        tr_key for tr_id, tr_key in kis_ws._subscriptions
        if tr_id == TICK_TR_ID
    ]
    return {
        "filtered_tickers": _last_scan_result,
        "filtered_count": len(_last_scan_result),
        "subscribed_tickers": subscribed,
        "subscribed_count": len(subscribed),
        "last_scan_time": _last_scan_time,
        "ticker_names": {k: v for k, v in ticker_names.items() if k in _last_scan_result},
        "ticker_prices": {k: v for k, v in ticker_prices.items() if k in _last_scan_result},
        "ticker_market_info": {k: v for k, v in ticker_market_info.items() if k in _last_scan_result},
    }


def t(ticker: str) -> str:
    """종목코드를 '종목명(코드)' 형태로 반환한다."""
    name = ticker_names.get(ticker)
    return f"{name}({ticker})" if name else ticker


async def subscribe_filtered_stocks(tickers: list[str]) -> None:
    """필터링된 종목들에 대해 WebSocket 실시간 시세 구독을 등록한다."""
    for ticker in tickers:
        await kis_ws.subscribe(TICK_TR_ID, ticker)
    logger.info("실시간 시세 구독 완료: %d종목", len(tickers))


async def unsubscribe_all() -> None:
    """모든 종목 구독을 해제한다."""
    for tr_id, tr_key in list(kis_ws._subscriptions):
        if tr_id == TICK_TR_ID:
            await kis_ws.unsubscribe(tr_id, tr_key)
    logger.info("모든 시세 구독 해제 완료")
