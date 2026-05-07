"""20일 신고가 스윙 돌파 전략 (Donchian + 추세필터 + ATR 트레일링).

추세추종 계열. 시스템 최초의 멀티데이 스윙 전략(평균 5~15 영업일 보유).

진입:
- 일봉 종가가 최근 20일 최고가 돌파
- 60일 EMA 우상향 + 종가 > 60일 EMA
- 거래대금이 20일 평균의 1.5배 이상
- 다음 영업일 09:05 시장가 (갭 +3%↑ 시 스킵)

청산:
- ATR(14) × 2 트레일링: high_since_buy - ATR×2 이탈 시 매도
- 하드 손절 -7%
- 시간 손절 / 15:20 강제 청산 모두 없음 (추세 끝까지 보유)
"""

import logging
from datetime import datetime, time, timezone, timedelta

from src.engine.strategy_base import Signal, StrategyBase, StrategyConfig

KST = timezone(timedelta(hours=9))


def _empty_scan_stats() -> dict:
    return {
        "universe_candidates": 0,
        "universe_filtered": 0,
        "candle_fetch_ok": 0,
        "donchian_pass": 0,
        "ema_uptrend_pass": 0,
        "volume_pass": 0,
        "atr_pass": 0,
        "final_prepared": 0,
        "last_run_at": None,
    }

logger = logging.getLogger(__name__)


class DonchianSwingStrategy(StrategyBase):
    """20일 신고가 스윙 돌파 전략."""

    DEFAULT_PARAMS = {
        "donchian_period": 20,
        "long_ma_period": 60,
        "volume_period": 20,
        "volume_multiplier": 1.5,
        "atr_period": 14,
        "atr_trail_mult": 2.0,
        "min_market_cap": 300_000_000_000,
        "min_trade_amount": 5_000_000_000,
        "max_scan_stocks": 200,
        "gap_skip_threshold": 3.0,
        "stop_loss_rate": -7.0,
        "position_ratio": 0.20,
        "max_positions": 5,
        "daily_loss_limit": -8.0,
    }

    def __init__(self, config: StrategyConfig):
        merged = {**self.DEFAULT_PARAMS, **config.params}
        config.params = merged
        super().__init__(config)
        self._candidates: dict[str, dict] = {}  # ticker -> {prev_close, atr, ...}
        self._scanned_tickers: list[str] = []
        self._bought_today: set[str] = set()  # 당일 진입 시도 종목 (중복 방지)
        # 단계별 탈락 통계 — prepare() 실행 시마다 갱신, 프론트 깔때기 시각화용
        self._scan_stats: dict = _empty_scan_stats()

    async def prepare(self) -> None:
        """장 시작 전: 유니버스 스캔 → 종목별 일봉 fetch → 신고가/MA/ATR/거래량 검증."""
        from src.api.condition import fetch_daily_candles

        params = self.config.params
        donchian_period = params["donchian_period"]
        long_ma_period = params["long_ma_period"]
        volume_period = params["volume_period"]
        volume_mult = params["volume_multiplier"]
        atr_period = params["atr_period"]

        # 매번 prepare 시 단계별 카운트 초기화 (universe_* 는 _scan_universe에서 채움)
        self._candidates = {}
        stats = _empty_scan_stats()
        self._scan_stats = stats

        tickers = await self._scan_universe()
        if not tickers:
            logger.info("도치안 스윙 유니버스 0종목")
            self._scanned_tickers = []
            stats["last_run_at"] = datetime.now(KST).isoformat()
            return

        # 60일 + 여유 = 65일 일봉 fetch
        fetch_days = max(long_ma_period + 5, donchian_period + 5)
        prepared = 0

        for ticker in tickers:
            try:
                candles = await fetch_daily_candles(ticker, days=fetch_days)
                if len(candles) < long_ma_period + 1:
                    continue

                # candles[0]이 가장 최근일(전일). closes[0]이 가장 최근.
                closes = [int(c.get("stck_clpr", "0")) for c in candles]
                highs = [int(c.get("stck_hgpr", "0")) for c in candles]
                lows = [int(c.get("stck_lwpr", "0")) for c in candles]
                vols = [int(c.get("acml_vol", "0")) for c in candles]

                prev_close = closes[0]
                if prev_close <= 0:
                    continue
                stats["candle_fetch_ok"] += 1

                # 1) 20일 신고가 돌파 검증 — 어제 종가가 그 이전 20일 최고가 초과
                prior_high = max(highs[1: donchian_period + 1])
                if prev_close <= prior_high:
                    continue
                stats["donchian_pass"] += 1

                # 2) 60일 EMA 우상향 + 종가 > EMA
                ema_today = self._ema(list(reversed(closes[:long_ma_period])), long_ma_period)
                ema_yesterday = self._ema(list(reversed(closes[1: long_ma_period + 1])), long_ma_period)
                if ema_today <= ema_yesterday:
                    continue
                if prev_close <= ema_today:
                    continue
                stats["ema_uptrend_pass"] += 1

                # 3) 거래량(거래대금 근사 = 종가×거래량) 20일 평균의 1.5배 이상
                today_turnover = closes[0] * vols[0]
                avg_turnover = sum(closes[i] * vols[i] for i in range(1, volume_period + 1)) / volume_period
                if avg_turnover <= 0 or today_turnover < avg_turnover * volume_mult:
                    continue
                stats["volume_pass"] += 1

                # 4) ATR(14) — Wilder 단순화: 평균 True Range
                atr = self._atr(highs, lows, closes, atr_period)
                if atr <= 0:
                    continue
                stats["atr_pass"] += 1

                # scanner.ticker_prev_close 사전 등록 (등락률 필터 등)
                from src.engine.scanner import ticker_prev_close
                ticker_prev_close[ticker] = prev_close

                self._candidates[ticker] = {
                    "prev_close": prev_close,
                    "atr": int(atr),
                    "ema60": int(ema_today),
                    "donchian_high": prior_high,
                }
                prepared += 1
            except Exception as e:
                logger.warning("도치안 스윙 prepare 실패: %s — %s", ticker, e)
                continue

        self._scanned_tickers = list(self._candidates.keys())
        self._bought_today.clear()
        stats["final_prepared"] = prepared
        stats["last_run_at"] = datetime.now(KST).isoformat()
        logger.info(
            "도치안 스윙 준비 완료: %d/%d종목 (신고가 + 추세 + 거래량) — "
            "fetch_ok=%d donchian=%d ema=%d volume=%d atr=%d",
            prepared, len(tickers),
            stats["candle_fetch_ok"], stats["donchian_pass"],
            stats["ema_uptrend_pass"], stats["volume_pass"], stats["atr_pass"],
        )

    @staticmethod
    def _ema(values: list[int], period: int) -> float:
        """단순화된 EMA — 전체 평균을 계산하여 SMA에 가까움. 추세 방향 판정용."""
        if not values:
            return 0.0
        # 진정한 EMA 가중치
        k = 2 / (period + 1)
        ema = float(values[0])
        for v in values[1:]:
            ema = v * k + ema * (1 - k)
        return ema

    @staticmethod
    def _atr(highs: list[int], lows: list[int], closes: list[int], period: int) -> float:
        """ATR(period) — 최근 period일의 True Range 평균.

        highs/lows/closes 모두 최신순(idx=0이 어제). closes[i+1]이 직전일 종가.
        """
        if len(highs) <= period or len(lows) <= period or len(closes) <= period + 1:
            return 0.0
        trs = []
        for i in range(period):
            tr = max(
                highs[i] - lows[i],
                abs(highs[i] - closes[i + 1]),
                abs(lows[i] - closes[i + 1]),
            )
            trs.append(tr)
        return sum(trs) / period

    async def _scan_universe(self) -> list[str]:
        """코스피200 + 코스닥150 고정 유니버스 + 시총 사후 컷.

        추세추종 스윙은 일중 거래량 순위(단기 회전 종목 편향)와 정합성이 낮다.
        거래대금 컷은 prepare()의 volume_multiplier 1.5×에서 일원화되므로 여기선
        시총만 검사 — `acml_tr_pbmn`(당일 누적 거래대금)이 장 시작 전 0이라
        모든 종목이 탈락하던 시점 의존성을 제거한다.
        """
        from src.api.condition import fetch_stock_detail
        from src.db.system_logs import write_log
        from src.engine.scanner import KOSDAQ_150_TICKERS, KOSPI_200_TICKERS

        min_mcap = self.config.params["min_market_cap"]
        max_stocks = self.config.params["max_scan_stocks"]

        all_tickers = list(dict.fromkeys(list(KOSPI_200_TICKERS) + list(KOSDAQ_150_TICKERS)))
        logger.info("도치안 스윙 유니버스 후보(코스피200+코스닥150): %d종목", len(all_tickers))
        self._scan_stats["universe_candidates"] = len(all_tickers)

        filtered: list[str] = []
        for ticker in all_tickers:
            if len(filtered) >= max_stocks:
                break
            try:
                detail = await fetch_stock_detail(ticker)
                price = int(detail.get("stck_prpr", "0"))
                listed = int(detail.get("lstn_stcn", "0"))
                mcap = price * listed
                name = detail.get("hts_kor_isnm", "") or detail.get("rprs_mrkt_kor_name", "")
                if name:
                    from src.engine.scanner import ticker_names
                    ticker_names[ticker] = name
                if mcap >= min_mcap:
                    filtered.append(ticker)
            except Exception:
                continue

        self._scan_stats["universe_filtered"] = len(filtered)
        logger.info("도치안 스윙 유니버스 확정: %d종목 (시총 %d억+)",
                    len(filtered), min_mcap // 1e8)
        if not filtered:
            await write_log(
                "ERROR",
                f"도치안 스윙 유니버스 0종목 확정 (후보 {len(all_tickers)}종목 — 시총 컷 모두 탈락)",
            )
        return filtered

    async def recompute_held_atr(self) -> None:
        """보유 중 종목의 ATR을 재계산해 _candidates에 추가 (멀티데이 트레일링 유지용).

        prepare()는 _boot에서 positions 복구 전에 실행되므로,
        positions 복구 후 별도로 호출해 보유 종목 ATR을 채워둔다.
        """
        from src.api.condition import fetch_daily_candles

        params = self.config.params
        fetch_days = max(params["long_ma_period"] + 5, params["donchian_period"] + 5)
        atr_period = params["atr_period"]

        for ticker in list(self.state.positions.keys()):
            if ticker in self._candidates:
                continue  # 오늘 신호 종목과 겹치면 그대로 사용
            try:
                candles = await fetch_daily_candles(ticker, days=fetch_days)
                if len(candles) < atr_period + 2:
                    continue
                highs = [int(c.get("stck_hgpr", "0")) for c in candles]
                lows = [int(c.get("stck_lwpr", "0")) for c in candles]
                closes = [int(c.get("stck_clpr", "0")) for c in candles]
                atr = self._atr(highs, lows, closes, atr_period)
                if atr > 0:
                    self._candidates[ticker] = {
                        "prev_close": closes[0],
                        "atr": int(atr),
                        "ema60": 0,
                        "donchian_high": 0,
                    }
                    logger.info("도치안 스윙 보유종목 ATR 재계산: %s ATR=%d", ticker, int(atr))
            except Exception:
                logger.exception("도치안 스윙 보유종목 ATR 실패: %s", ticker)

    def get_scanned_tickers(self) -> list[str]:
        """WebSocket 사전 구독용."""
        return self._scanned_tickers

    def get_scan_stats(self) -> dict:
        """단계별 스캔/탈락 통계 — 프론트 깔때기 시각화용."""
        return dict(self._scan_stats)

    def get_targets_status(self) -> dict[str, dict]:
        """대시보드 노출용 — Donchian/EMA/ATR 정보."""
        return {
            ticker: {
                "prev_close": info["prev_close"],
                "atr": info["atr"],
                "ema60": info["ema60"],
                "donchian_high": info["donchian_high"],
                # VB와 호환되는 필드 (대시보드 공용 표 활용 가능)
                "k": 0.0,
                "target_price": info["donchian_high"],
                "open_price": 0,
                "target_offset": 0,
                "open_confirmed": True,
            }
            for ticker, info in self._candidates.items()
        }

    def check_buy_signal(
        self, ticker: str, current_price: int, open_price: int,
    ) -> Signal:
        """09:05 ~ 09:30 사이에 _candidates 종목 진입 (갭 +3%↑ 스킵, 1회만)."""
        if self.state.buy_disabled:
            return Signal.NONE
        if self.state.has_position(ticker) or self.state.is_buy_pending(ticker):
            return Signal.NONE
        if self.state.is_sold_today(ticker):
            return Signal.NONE
        if ticker in self._bought_today:
            return Signal.NONE
        if self.is_max_positions():
            return Signal.NONE
        if self.is_daily_loss_exceeded():
            return Signal.NONE

        info = self._candidates.get(ticker)
        if not info:
            return Signal.NONE

        # 시간 가드: 09:05 ~ 09:30
        now_t = datetime.now().time()
        if now_t < time(9, 5) or now_t > time(9, 30):
            return Signal.NONE

        # 갭 +X% 이상이면 스킵
        if open_price > 0 and info["prev_close"] > 0:
            gap_rate = (open_price - info["prev_close"]) / info["prev_close"] * 100
            gap_skip = self.config.params["gap_skip_threshold"]
            if gap_rate >= gap_skip:
                logger.info("도치안 스윙 갭 스킵: %s 갭률 %.1f%% ≥ %.1f%%",
                            ticker, gap_rate, gap_skip)
                self._bought_today.add(ticker)
                return Signal.NONE

        self._bought_today.add(ticker)
        logger.info(
            "도치안 스윙 매수 신호: %s 현재가(%d) — 신고가(%d) 돌파 + EMA60(%d) 위 + ATR(%d)",
            ticker, current_price, info["donchian_high"], info["ema60"], info["atr"],
        )
        self.state.buy_signals.append({
            "ticker": ticker,
            "name": "",
            "price": current_price,
            "donchian_high": info["donchian_high"],
            "atr": info["atr"],
            "change_rate": 0,
            "time": datetime.now().strftime("%H:%M:%S"),
        })
        if len(self.state.buy_signals) > 20:
            self.state.buy_signals.pop(0)
        return Signal.BUY

    def check_exit_signal(
        self, ticker: str, current_price: int, open_price: int,
    ) -> Signal:
        """ATR 트레일링 + 하드 손절. 시간/익일 청산 없음 — 추세 끝까지 보유."""
        pos = self.state.positions.get(ticker)
        if not pos:
            return Signal.NONE

        # 1) 하드 손절
        loss_rate = (current_price - pos.buy_price) / pos.buy_price * 100 if pos.buy_price > 0 else 0
        stop_loss = self.config.params["stop_loss_rate"]
        if loss_rate <= stop_loss:
            logger.info("도치안 스윙 손절: %s 매수가(%d) 대비 %.1f%%",
                        ticker, pos.buy_price, loss_rate)
            return Signal.STOP_LOSS

        # 2) ATR 트레일링 — high_since_buy 기준 (RiskManager가 매 tick 갱신)
        info = self._candidates.get(ticker)
        atr = info["atr"] if info else 0
        if atr > 0 and pos.high_since_buy > 0:
            mult = self.config.params["atr_trail_mult"]
            chandelier = pos.high_since_buy - atr * mult
            if current_price <= chandelier:
                logger.info(
                    "도치안 스윙 트레일링: %s 고점(%d) - ATR×%.1f = %d / 현재가 %d",
                    ticker, pos.high_since_buy, mult, int(chandelier), current_price,
                )
                return Signal.TRAILING_STOP

        return Signal.NONE

    def check_force_clear(self) -> list[str]:
        """15:20 강제 청산 대상 — 스윙 전략은 강제 청산 없음."""
        return []

    def calc_buy_quantity(self, current_price: int) -> int:
        ratio = self.config.params["position_ratio"]
        amount = int(self.state.total_investment * ratio)
        return amount // current_price if current_price > 0 else 0
