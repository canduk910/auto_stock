"""변동성 돌파 전략 (래리 윌리엄스).

- 대상: 코스피+코스닥 전체에서 시총/거래대금 조건 필터
- prepare(): 조건 충족 종목의 21일 일봉으로 K값(노이즈 비율 기반) 계산 → Target Price 설정
- 매수: 당일 현재가 >= Target Price (시가 + 전일 Range * K)
- 손절: 매수가 대비 -3%
- 강제 청산: 15:20 전량 청산
- 비중: 할당 자금의 10%
"""

import logging
from datetime import date, datetime

from src.engine.strategy_base import Signal, StrategyBase, StrategyConfig

logger = logging.getLogger(__name__)


class VolatilityBreakoutStrategy(StrategyBase):
    """변동성 돌파 전략."""

    DEFAULT_PARAMS = {
        "stop_loss_rate": -3.0,
        "position_ratio": 0.10,
        "max_positions": 10,
        "daily_loss_limit": -5.0,
        "k_period": 20,
        # 종목 스캔 조건 (Settings에서 변경 가능)
        "min_market_cap": 100_000_000_000,   # 시총 1,000억 이상
        "min_trade_amount": 20_000_000_000,  # 거래대금 200억 이상
        "max_scan_stocks": 100,              # 최대 스캔 종목 수
    }

    def __init__(self, config: StrategyConfig):
        merged = {**self.DEFAULT_PARAMS, **config.params}
        config.params = merged
        super().__init__(config)
        # ticker -> {"target_price": int, "k": float, "open_price": int}
        self._targets: dict[str, dict] = {}
        # ticker -> 시가 확정 여부
        self._open_confirmed: dict[str, bool] = {}
        # ticker -> 이전 틱 가격 (돌파 순간 감지용)
        self._prev_price: dict[str, int] = {}
        # 스캔된 종목 리스트 (subscribe용)
        self._scanned_tickers: list[str] = []

    async def prepare(self) -> None:
        """장 시작 전: 시총/거래대금 조건 종목 스캔 → 21일 일봉으로 K값/Target 계산."""
        from src.api.condition import fetch_daily_candles

        tickers = await self._scan_universe()
        k_period = self.config.params["k_period"]
        today_str = date.today().strftime("%Y%m%d")
        prepared = 0

        for ticker in tickers:
            try:
                # candles[0]이 "오늘 부분봉"인 경우를 고려해 +2 여유분 확보
                candles = await fetch_daily_candles(ticker, days=k_period + 2)
                if len(candles) < 2:
                    continue

                # candles[0]의 거래일이 오늘이면 candles[1]을 "전일"로 사용 (장 시작 전 빈/부분봉 방어)
                prev_idx = 1 if candles[0].get("stck_bsop_date") == today_str else 0
                if len(candles) <= prev_idx + 1:
                    continue

                # 노이즈 비율 계산: prev 기준 그 이전 k_period일
                noise_list = []
                for c in candles[prev_idx + 1 :]:
                    high = int(c.get("stck_hgpr", "0"))
                    low = int(c.get("stck_lwpr", "0"))
                    open_p = int(c.get("stck_oprc", "0"))
                    close_p = int(c.get("stck_clpr", "0"))
                    rng = high - low
                    if rng > 0:
                        noise = 1 - abs(close_p - open_p) / rng
                        noise_list.append(noise)

                if not noise_list:
                    continue

                k = sum(noise_list) / len(noise_list)

                # 전일 Range
                prev = candles[prev_idx]
                prev_high = int(prev.get("stck_hgpr", "0"))
                prev_low = int(prev.get("stck_lwpr", "0"))
                prev_range = prev_high - prev_low
                if prev_range <= 0:
                    logger.debug(
                        "변동성돌파 prev_range=0 skip: %s (date=%s)",
                        ticker, prev.get("stck_bsop_date"),
                    )
                    continue

                target_offset = int(prev_range * k)
                if target_offset <= 0:
                    logger.debug(
                        "변동성돌파 target_offset=0 skip: %s (k=%.4f, range=%d)",
                        ticker, k, prev_range,
                    )
                    continue

                self._targets[ticker] = {
                    "k": round(k, 4),
                    "prev_range": prev_range,
                    "target_offset": target_offset,
                    "target_price": 0,
                    "open_price": 0,
                }
                self._open_confirmed[ticker] = False

                # 09:30 scan_stocks() 이전에도 등락률 필터가 동작하도록 전일종가 사전 등록
                from src.engine.scanner import ticker_prev_close
                prev_close = int(prev.get("stck_clpr", "0"))
                if prev_close > 0:
                    ticker_prev_close[ticker] = prev_close

                prepared += 1

            except Exception as e:
                logger.warning("변동성돌파 prepare 실패: %s — %s", ticker, e)
                continue

        self._scanned_tickers = list(self._targets.keys())
        logger.info("변동성돌파 전략 준비 완료: %d/%d종목 (K값 계산)", prepared, len(tickers))

    async def _scan_universe(self) -> list[str]:
        """시총/거래대금 조건으로 코스피+코스닥 종목을 스캔한다.

        거래량순위 API 응답에 포함된 prdy_vol/lstn_stcn/stck_prpr/prdy_vrss로
        시총·전일 거래대금을 직접 산출한다 (개별 inquire-price 호출 없음).

        prdy_vol·prdy_close는 KIS 영업일 기준이므로 휴장 직후 첫 영업일이나
        장 시작 전이라도 시간 의존 없이 일관된 결과를 보장한다.
        """
        from src.api.base import kis_get, KisApiError
        from src.db.system_logs import write_log
        from src.engine.scanner import ticker_names, ETF_KEYWORDS

        min_mcap = self.config.params["min_market_cap"]
        min_trade = self.config.params["min_trade_amount"]
        max_stocks = self.config.params["max_scan_stocks"]

        # 거래량순위 API로 전체 시장 상위 종목 확보 ("J"가 코스피+코스닥 전체)
        rank_items: list[dict] = []
        for market in ["J"]:
            try:
                params = {
                    "FID_COND_MRKT_DIV_CODE": market,
                    "FID_COND_SCR_DIV_CODE": "20171",
                    "FID_INPUT_ISCD": "0000",
                    "FID_DIV_CLS_CODE": "0",
                    "FID_BLNG_CLS_CODE": "0",
                    "FID_TRGT_CLS_CODE": "111111111",
                    "FID_TRGT_EXLS_CLS_CODE": "000000",
                    "FID_INPUT_PRICE_1": "0",
                    "FID_INPUT_PRICE_2": "0",
                    "FID_VOL_CNT": "0",
                    "FID_INPUT_DATE_1": "0",
                }
                data = await kis_get(
                    "/uapi/domestic-stock/v1/quotations/volume-rank",
                    "FHPST01710000",
                    params,
                )
                for item in data.get("output", []):
                    name = item.get("hts_kor_isnm", "")
                    if any(kw in name for kw in ETF_KEYWORDS):
                        continue
                    rank_items.append(item)
            except KisApiError:
                logger.warning("변동성돌파 거래량순위 조회 실패: market=%s", market)

        logger.info("변동성돌파 유니버스 후보: %d종목", len(rank_items))

        # 거래량순위 응답 데이터로 시총·전일 거래대금 추정 → 필터
        filtered: list[str] = []
        for item in rank_items:
            if len(filtered) >= max_stocks:
                break
            ticker = item.get("mksc_shrn_iscd", "")
            if not ticker:
                continue
            # 종목코드 형식 검증 — ETF·ETN·신주인수권 등 알파벳 포함 코드 차단
            if not (len(ticker) == 6 and ticker.isdigit()):
                continue
            try:
                price = int(item.get("stck_prpr", "0"))
                listed = int(item.get("lstn_stcn", "0"))
                prdy_vol = int(item.get("prdy_vol", "0"))
                # KIS prdy_vrss는 부호 포함 정수 (상승=+, 하락=-)
                prdy_vrss = int(item.get("prdy_vrss", "0"))
                prdy_close = price - prdy_vrss
            except (ValueError, TypeError):
                continue

            if price <= 0 or listed <= 0 or prdy_vol <= 0 or prdy_close <= 0:
                continue

            mcap = price * listed
            prdy_trade_amt = prdy_vol * prdy_close
            if mcap >= min_mcap and prdy_trade_amt >= min_trade:
                name = item.get("hts_kor_isnm", "")
                if name:
                    ticker_names[ticker] = name
                filtered.append(ticker)

        logger.info("변동성돌파 유니버스 확정: %d종목 (시총 %d억+, 거래대금 %d억+)",
                     len(filtered), min_mcap // 100_000_000, min_trade // 100_000_000)

        if not filtered:
            if not rank_items:
                msg = "변동성돌파 유니버스 0종목 — 거래량순위 API 응답이 비어있음"
            else:
                msg = (
                    f"변동성돌파 유니버스 0종목 — 후보 {len(rank_items)}종목 중 "
                    f"시총 {min_mcap // 100_000_000}억+ / 거래대금 "
                    f"{min_trade // 100_000_000}억+ 필터 통과 없음"
                )
            logger.error(msg)
            try:
                await write_log("ERROR", msg)
            except Exception:
                logger.exception("system_logs 기록 실패")

        return filtered

    def get_scanned_tickers(self) -> list[str]:
        """스캔된 종목 리스트를 반환한다 (WebSocket 구독용)."""
        return self._scanned_tickers

    def get_targets_status(self) -> dict[str, dict]:
        """종목별 타겟 가격 정보를 반환한다."""
        return {
            ticker: {
                "k": info["k"],
                "target_price": info["target_price"],
                "open_price": info["open_price"],
                "target_offset": info["target_offset"],
                "open_confirmed": self._open_confirmed.get(ticker, False),
            }
            for ticker, info in self._targets.items()
        }

    def on_open_price_confirmed(self, ticker: str, open_price: int) -> None:
        """시가 확정 시 Target Price를 계산한다."""
        info = self._targets.get(ticker)
        if not info:
            return
        info["open_price"] = open_price
        info["target_price"] = open_price + info["target_offset"]
        self._open_confirmed[ticker] = True

    def check_buy_signal(
        self, ticker: str, current_price: int, open_price: int,
    ) -> Signal:
        """현재가 >= Target Price 시 매수."""
        if self.state.buy_disabled:
            return Signal.NONE
        if self.state.has_position(ticker) or self.state.is_buy_pending(ticker) or self.state.is_sold_today(ticker):
            return Signal.NONE
        if self.is_max_positions():
            return Signal.NONE
        if self.is_daily_loss_exceeded():
            return Signal.NONE

        info = self._targets.get(ticker)
        if not info:
            return Signal.NONE

        # 시가 미확정 시 현재가를 시가로 사용하여 확정
        if not self._open_confirmed.get(ticker, False) and open_price > 0:
            self.on_open_price_confirmed(ticker, open_price)

        target = info.get("target_price", 0)
        if target <= 0:
            return Signal.NONE

        prev = self._prev_price.get(ticker, 0)
        self._prev_price[ticker] = current_price

        # 돌파 순간만 감지: 이전 틱이 타겟 미만 → 현재 틱이 타겟 이상
        if prev == 0:
            # 첫 틱은 기록만 하고 건너뜀
            return Signal.NONE

        if prev < target and current_price >= target:
            from src.engine.scanner import t, ticker_names
            logger.info(
                "변동성돌파 매수 신호: %s 현재가(%d) >= 목표가(%d), 이전가(%d), K=%.4f",
                t(ticker), current_price, target, prev, info["k"],
            )
            self.state.buy_signals.append({
                "ticker": ticker,
                "name": ticker_names.get(ticker, ""),
                "price": current_price,
                "target_price": target,
                "k": info["k"],
                "change_rate": round((current_price - info["open_price"]) / info["open_price"] * 100, 1) if info["open_price"] > 0 else 0,
                "time": datetime.now().strftime("%H:%M:%S"),
            })
            if len(self.state.buy_signals) > 20:
                self.state.buy_signals.pop(0)
            return Signal.BUY

        return Signal.NONE

    def check_exit_signal(
        self, ticker: str, current_price: int, open_price: int,
    ) -> Signal:
        """손절: 매수가 대비 -3%."""
        pos = self.state.positions.get(ticker)
        if not pos:
            return Signal.NONE

        loss_rate = (current_price - pos.buy_price) / pos.buy_price * 100
        stop_loss = self.config.params["stop_loss_rate"]
        if loss_rate <= stop_loss:
            from src.engine.scanner import t
            logger.info(
                "변동성돌파 손절: %s 매수가(%d) 대비 %.1f%% (현재가: %d)",
                t(ticker), pos.buy_price, loss_rate, current_price,
            )
            return Signal.STOP_LOSS

        return Signal.NONE

    def check_force_clear(self) -> list[str]:
        """15:20 강제 청산 대상 종목 리스트를 반환한다."""
        return list(self.state.positions.keys())

    def calc_buy_quantity(self, current_price: int) -> int:
        """할당 자금의 10% 비중으로 매수 수량 계산."""
        ratio = self.config.params["position_ratio"]
        amount = int(self.state.total_investment * ratio)
        return amount // current_price if current_price > 0 else 0
