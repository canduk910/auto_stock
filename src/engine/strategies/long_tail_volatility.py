"""롱테일 변동성 돌파 전략.

변동성 돌파 진입 + 상한가 도달 시 익일 청산으로 롱테일(긴 우측 보상) 추구.
- 대상: 시총/거래대금 필터 + 연속상한가 제외
- 매수: 시가 + (전일Range × K) 돌파 시 (변동성 돌파 방식)
- 당일 상한가 미도달: 당일 손절(-3%) + 15:20 강제 청산
- 당일 상한가 도달(+29%): 익일 청산 모드 전환 — 손절(-5%), 갭상승 +10% 트레일링/-2%
"""

import logging
from datetime import datetime

from src.engine.strategy_base import Signal, StrategyBase, StrategyConfig

logger = logging.getLogger(__name__)


class LongTailVolatilityStrategy(StrategyBase):
    """롱테일 변동성 돌파 전략."""

    DEFAULT_PARAMS = {
        # 진입 조건
        "k_period": 20,
        "min_prdy_rate": 5.0,                        # 전일대비 최소 등락률
        # 종목 필터
        "min_market_cap": 100_000_000_000,            # 시총 1,000억
        "min_trade_amount": 20_000_000_000,           # 거래대금 200억
        "max_scan_stocks": 100,
        "exclude_consecutive_limit": 2,               # 연속 상한가 N일 이상 제외
        # 당일 청산 (상한가 미도달)
        "intraday_stop_loss": -3.0,
        # 익일 청산 (상한가 도달)
        "limit_up_threshold": 29.0,                   # 이 이상 → 익일 청산 모드
        "overnight_stop_loss": -5.0,
        "gap_up_threshold": 10.0,
        "trailing_stop_rate": -2.0,
        # 자금 관리
        "position_ratio": 0.15,
        "max_positions": 6,
        "daily_loss_limit": -5.0,
    }

    def __init__(self, config: StrategyConfig):
        merged = {**self.DEFAULT_PARAMS, **config.params}
        config.params = merged
        super().__init__(config)
        # VB와 동일 — 종목별 타겟 가격/K값
        self._targets: dict[str, dict] = {}
        self._open_confirmed: dict[str, bool] = {}
        self._prev_price: dict[str, int] = {}
        self._scanned_tickers: list[str] = []
        # 상한가 도달 → 익일 청산 모드 종목
        self._limit_up_reached: set[str] = set()
        # 익일 청산 시가 안정화 대기 플래그
        self._next_day_clear_pending = False

    async def prepare(self) -> None:
        """장 시작 전: 종목 스캔 → K값 계산 → 연속상한가 필터링."""
        from src.api.condition import fetch_daily_candles

        tickers = await self._scan_universe()
        k_period = self.config.params["k_period"]
        consecutive_limit = self.config.params["exclude_consecutive_limit"]
        prepared = 0

        for ticker in tickers:
            try:
                candles = await fetch_daily_candles(ticker, days=k_period + 1)
                if len(candles) < 2:
                    continue

                # 연속상한가 체크 (최근 N일 연속 +25% 이상이면 제외)
                if consecutive_limit > 0 and self._is_consecutive_limit_up(candles, consecutive_limit):
                    logger.debug("연속상한가 제외: %s (%d일 이상)", ticker, consecutive_limit)
                    continue

                # 노이즈 비율 계산 (VB와 동일)
                noise_list = []
                for c in candles[1:]:
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
                prev = candles[0]
                prev_high = int(prev.get("stck_hgpr", "0"))
                prev_low = int(prev.get("stck_lwpr", "0"))
                prev_range = prev_high - prev_low

                self._targets[ticker] = {
                    "k": round(k, 4),
                    "prev_range": prev_range,
                    "target_offset": int(prev_range * k),
                    "target_price": 0,
                    "open_price": 0,
                }
                self._open_confirmed[ticker] = False

                # 09:30 scan_stocks() 이전에도 등락률 필터(min_prdy_rate)가 동작하도록 전일종가 사전 등록
                from src.engine.scanner import ticker_prev_close
                prev_close = int(prev.get("stck_clpr", "0"))
                if prev_close > 0:
                    ticker_prev_close[ticker] = prev_close

                prepared += 1

            except Exception as e:
                logger.warning("롱테일 변동성 돌파 prepare 실패: %s — %s", ticker, e)
                continue

        self._scanned_tickers = list(self._targets.keys())
        logger.info("롱테일 변동성 돌파 준비 완료: %d/%d종목", prepared, len(tickers))

    @staticmethod
    def _is_consecutive_limit_up(candles: list[dict], threshold: int) -> bool:
        """최근 N일 연속 상한가(+25% 이상) 여부를 판별한다.

        candles[0]이 가장 최근일.
        """
        count = 0
        for c in candles[:threshold]:
            close_p = int(c.get("stck_clpr", "0"))
            open_p = int(c.get("stck_oprc", "0"))
            if open_p <= 0:
                break
            rate = (close_p - open_p) / open_p * 100
            if rate >= 25.0:
                count += 1
            else:
                break
        return count >= threshold

    async def _scan_universe(self) -> list[str]:
        """시총/거래대금 조건으로 종목을 스캔한다 (VB와 동일 로직).

        거래량순위 API 응답의 prdy_vol/lstn_stcn/stck_prpr/prdy_vrss를 직접 활용해
        시총·전일 거래대금을 산출한다. 개별 inquire-price 호출 없음 →
        휴장 직후 첫 영업일이나 장 시작 전에도 시간 의존 없이 일관된 결과를 보장한다.
        """
        from src.api.base import kis_get, KisApiError
        from src.db.system_logs import write_log
        from src.engine.scanner import ticker_names, ETF_KEYWORDS

        min_mcap = self.config.params["min_market_cap"]
        min_trade = self.config.params["min_trade_amount"]
        max_stocks = self.config.params["max_scan_stocks"]

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
                logger.warning("롱테일 변동성 돌파 거래량순위 조회 실패")

        logger.info("롱테일 변동성 돌파 유니버스 후보: %d종목", len(rank_items))

        filtered: list[str] = []
        for item in rank_items:
            if len(filtered) >= max_stocks:
                break
            ticker = item.get("mksc_shrn_iscd", "")
            if not ticker:
                continue
            try:
                price = int(item.get("stck_prpr", "0"))
                listed = int(item.get("lstn_stcn", "0"))
                prdy_vol = int(item.get("prdy_vol", "0"))
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

        logger.info("롱테일 변동성 돌파 유니버스 확정: %d종목", len(filtered))

        if not filtered:
            if not rank_items:
                msg = "롱테일 변동성 돌파 유니버스 0종목 — 거래량순위 API 응답이 비어있음"
            else:
                msg = (
                    f"롱테일 변동성 돌파 유니버스 0종목 — 후보 {len(rank_items)}종목 중 "
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
        """종목별 타겟 가격 정보를 반환한다 (VB와 동일한 형식)."""
        return {
            ticker: {
                "k": info["k"],
                "target_price": info["target_price"],
                "open_price": info["open_price"],
                "target_offset": info["target_offset"],
                "open_confirmed": self._open_confirmed.get(ticker, False),
                "limit_up_reached": ticker in self._limit_up_reached,
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
        """변동성 돌파 방식 매수: 현재가 >= Target Price 돌파 순간."""
        from src.engine.scanner import t, ticker_names, ticker_prev_close

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

        # 전일대비 등락률 필터
        prev_close = ticker_prev_close.get(ticker, 0)
        if prev_close > 0:
            prdy_rate = (current_price - prev_close) / prev_close * 100
            min_rate = self.config.params["min_prdy_rate"]
            if prdy_rate < min_rate:
                return Signal.NONE

        prev = self._prev_price.get(ticker, 0)
        self._prev_price[ticker] = current_price

        if prev == 0:
            return Signal.NONE

        # 돌파 순간 감지
        if prev < target and current_price >= target:
            logger.info(
                "롱테일 변동성 돌파 매수 신호: %s 현재가(%d) >= 목표가(%d), K=%.4f",
                t(ticker), current_price, target, info["k"],
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
        """2단계 청산: 당일 모드(손절 -3%) / 익일 모드(손절 -5% + 트레일링)."""
        from src.engine.scanner import t, ticker_prev_close

        pos = self.state.positions.get(ticker)
        if not pos:
            return Signal.NONE

        loss_rate = (current_price - pos.buy_price) / pos.buy_price * 100

        # --- 익일 청산 모드 (상한가 도달 후 전환된 종목) ---
        if ticker in self._limit_up_reached:
            if pos.is_next_day:
                # 시가 안정화 대기 중에는 청산 판단 억제
                if self._next_day_clear_pending:
                    # 손절만 유지
                    if loss_rate <= self.config.params["overnight_stop_loss"]:
                        logger.info("롱테일VB 익일 손절: %s %.1f%%", t(ticker), loss_rate)
                        return Signal.STOP_LOSS
                    return Signal.NONE

                gap_threshold = self.config.params["gap_up_threshold"]
                trailing_rate = self.config.params["trailing_stop_rate"]
                gap_rate = (open_price - pos.buy_price) / pos.buy_price * 100 if pos.buy_price > 0 else 0

                if gap_rate < gap_threshold:
                    logger.info("롱테일VB 익일 즉시 청산: %s 갭률 %.1f%%", t(ticker), gap_rate)
                    return Signal.NEXT_DAY_CLEAR

                # 갭상승 → 트레일링 스탑
                pos.high_since_buy = max(pos.high_since_buy, current_price)
                drop_rate = (current_price - pos.high_since_buy) / pos.high_since_buy * 100
                if drop_rate <= trailing_rate:
                    logger.info("롱테일VB 트레일링 스탑: %s 고점(%d) 대비 %.1f%%", t(ticker), pos.high_since_buy, drop_rate)
                    return Signal.TRAILING_STOP
                return Signal.NONE

            # 당일 (상한가 도달 후) — overnight 손절만 적용
            if loss_rate <= self.config.params["overnight_stop_loss"]:
                logger.info("롱테일VB 손절(상한가 모드): %s %.1f%%", t(ticker), loss_rate)
                return Signal.STOP_LOSS
            return Signal.NONE

        # --- 당일 모드 (상한가 미도달) ---
        # 손절
        if loss_rate <= self.config.params["intraday_stop_loss"]:
            logger.info("롱테일VB 당일 손절: %s %.1f%%", t(ticker), loss_rate)
            return Signal.STOP_LOSS

        # 상한가 도달 체크 → 모드 전환
        prev_close = ticker_prev_close.get(ticker, 0)
        if prev_close > 0:
            prdy_rate = (current_price - prev_close) / prev_close * 100
            threshold = self.config.params["limit_up_threshold"]
            if prdy_rate >= threshold:
                self._limit_up_reached.add(ticker)
                logger.info(
                    "롱테일VB 상한가 모드 전환: %s 등락률 %.1f%% >= %.1f%%",
                    t(ticker), prdy_rate, threshold,
                )

        return Signal.NONE

    def check_force_clear(self) -> list[str]:
        """15:20 강제 청산 대상 — 상한가 모드가 아닌 종목만."""
        return [
            ticker for ticker in self.state.positions
            if ticker not in self._limit_up_reached
        ]

    def calc_buy_quantity(self, current_price: int) -> int:
        ratio = self.config.params["position_ratio"]
        amount = int(self.state.total_investment * ratio)
        return amount // current_price if current_price > 0 else 0
