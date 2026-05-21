"""눌림목 돌파(Bull Flag Breakout) 전략.

강한 상승(폴, flag pole) 직후 짧은 횡보·완만 조정(플래그) → 플래그 상단 재돌파 시 매수.
모멘텀(+29% 폭발) 전략의 후속 정리 후 2차 상승 진입로.

진입:
- 폴: 직전 3~10영업일 누적 +20% 이상, 음봉 비율 ≤ 30%
- 플래그: 폴 종료 후 3~10영업일, 조정 폭 ≤ 폴 폭의 38.2%, 거래량 < 폴 평균의 60%
- 매수: 플래그 상단 돌파 + 당일 거래량 ≥ 플래그 평균 × 2
- 시간대: 09:05~13:00 KRX 메인 (`tradable_boards=("main",)`)

청산:
- 하드 손절 -5% / 플래그 하단 이탈
- 측정된 이동 도달 → 절반 익절 (1차 구현은 전량 청산)
- 잔여 ATR(14)×2 트레일링
- 진입 후 5영업일 경과 시 잔량 시장가

매수 회전:
- 종목당 1회 (`_bought_today` set)
- 청산 후 3영업일 쿨다운 (`_cooldown_until` dict)

명세: `_workspace/00_leader_trading_rules.md` 6-E
"""

from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta, timezone

from src.engine.strategy_base import Signal, StrategyBase, StrategyConfig

KST = timezone(timedelta(hours=9))
logger = logging.getLogger(__name__)


def _empty_scan_stats() -> dict:
    return {
        "universe_candidates": 0,
        "universe_filtered": 0,
        "candle_fetch_ok": 0,
        "pole_pass": 0,
        "flag_pass": 0,
        "volume_contraction_pass": 0,
        "atr_pass": 0,
        "final_prepared": 0,
        "min_trade_amount_failed": 0,  # 사이클 23 P1-2 — 거래대금 미달 카운터
        "last_run_at": None,
    }


def _parse_time_hhmm(s: str) -> time:
    """`"09:05"` → `time(9, 5)` (간단한 HH:MM 파서)."""
    if not s or ":" not in s:
        return time(0, 0)
    h, m = s.split(":")
    return time(int(h), int(m))


class BullFlagBreakoutStrategy(StrategyBase):
    """눌림목 돌파 (Bull Flag) — KRX 메인 한정."""

    DEFAULT_TRADABLE_BOARDS = ("main",)

    DEFAULT_PARAMS = {
        "tradable_boards": list(DEFAULT_TRADABLE_BOARDS),
        "exchange": "KRX",
        # 폴
        "pole_lookback_min": 3,
        "pole_lookback_max": 10,
        "pole_min_return": 20.0,
        "pole_max_red_ratio": 0.30,
        # 플래그
        "flag_lookback_min": 3,
        "flag_lookback_max": 10,
        "flag_retracement_max": 0.382,
        "flag_volume_ratio": 0.60,
        # 매수
        "breakout_volume_mult": 2.0,
        "entry_start": "09:05",
        "entry_end": "13:00",
        "position_ratio": 0.25,
        "max_positions": 4,
        # 청산
        "stop_loss_rate": -5.0,
        "atr_period": 14,
        "atr_trail_mult": 2.0,
        "max_hold_days": 5,
        "reentry_cooldown_days": 3,
        # 유니버스
        "min_market_cap": 50_000_000_000,
        "min_trade_amount": 2_000_000_000,
        "max_scan_stocks": 100,
        # 일반
        "daily_loss_limit": -6.0,
        # 사이클 23 P2-1 — 돌파 유지시간 조건 (가짜 돌파 차단)
        "breakout_retention_minutes": 3,
    }

    def __init__(self, config: StrategyConfig):
        merged = {**self.DEFAULT_PARAMS, **config.params}
        config.params = merged
        super().__init__(config)
        self._candidates: dict[str, dict] = {}
        self._scanned_tickers: list[str] = []
        self._bought_today: set[str] = set()
        # ticker -> 직전 틱 가격 (돌파 순간 감지용)
        self._prev_price: dict[str, int] = {}
        # ticker -> 측정된 이동 도달 여부 (절반 익절 후 ATR 트레일링 분기)
        self._partial_exit: dict[str, bool] = {}
        # ticker -> 쿨다운 만료일(이날 이전엔 재진입 금지)
        self._cooldown_until: dict[str, date] = {}
        # 사이클 23 P2-1 — ticker -> 첫 돌파 감지 시각 (retention 대기용)
        self._breakout_first_seen: dict[str, datetime] = {}
        self._scan_stats: dict = _empty_scan_stats()

    # ------------------------------------------------------------------
    # prepare — 일봉 fetch → 폴/플래그 자동 검출
    # ------------------------------------------------------------------
    async def prepare(self) -> None:
        import asyncio

        from src.api.condition import fetch_daily_candles

        params = self.config.params
        pole_max = params["pole_lookback_max"]
        flag_max = params["flag_lookback_max"]
        atr_period = params["atr_period"]
        fetch_days = pole_max + flag_max + atr_period + 10  # 여유

        self._candidates = {}
        stats = _empty_scan_stats()
        self._scan_stats = stats

        tickers = await self._scan_universe()
        if not tickers:
            logger.info("눌림목 돌파 유니버스 0종목")
            self._scanned_tickers = []
            stats["last_run_at"] = datetime.now(KST).isoformat()
            return

        today_str = datetime.now(KST).strftime("%Y%m%d")

        async def _fetch_one(ticker: str):
            try:
                return ticker, await fetch_daily_candles(ticker, days=fetch_days)
            except Exception as e:
                logger.warning("눌림목 일봉 fetch 실패: %s — %s", ticker, e)
                return ticker, None

        fetched = await asyncio.gather(*[_fetch_one(t) for t in tickers])

        for ticker, candles in fetched:
            if candles is None or not candles:
                continue
            try:
                # 부분봉 가드 — candles[0] 이 오늘이면 [1] 부터 사용
                prev_idx = 1 if candles[0].get("stck_bsop_date") == today_str else 0
                if len(candles) <= prev_idx + pole_max + flag_max + 2:
                    continue
                if prev_idx:
                    candles = candles[prev_idx:]
                stats["candle_fetch_ok"] += 1

                result = self._detect_pole_and_flag(candles)
                if not result:
                    continue
                stats["pole_pass"] += 1
                stats["flag_pass"] += 1

                # 거래량 수축 확인은 _detect_pole_and_flag 내부에서 통과한 것
                stats["volume_contraction_pass"] += 1

                # ATR
                atr = self._atr(
                    [int(c.get("stck_hgpr", "0")) for c in candles],
                    [int(c.get("stck_lwpr", "0")) for c in candles],
                    [int(c.get("stck_clpr", "0")) for c in candles],
                    atr_period,
                )
                if atr <= 0:
                    continue
                stats["atr_pass"] += 1

                from src.engine.scanner import ticker_prev_close
                prev_close = int(candles[0].get("stck_clpr", "0"))
                if prev_close > 0:
                    ticker_prev_close[ticker] = prev_close

                self._candidates[ticker] = {
                    **result,
                    "atr14": int(atr),
                    "prev_close": prev_close,
                }
                stats["final_prepared"] += 1
            except Exception as e:
                logger.warning("눌림목 prepare 실패: %s — %s", ticker, e)
                continue

        self._scanned_tickers = list(self._candidates.keys())
        self._bought_today.clear()
        stats["last_run_at"] = datetime.now(KST).isoformat()
        logger.info(
            "눌림목 돌파 준비 완료: %d/%d종목 — pole=%d flag=%d vol_cnt=%d atr=%d",
            stats["final_prepared"], len(tickers),
            stats["pole_pass"], stats["flag_pass"],
            stats["volume_contraction_pass"], stats["atr_pass"],
        )

    def _detect_pole_and_flag(self, candles: list[dict]) -> dict | None:
        """일봉(최신순) → 폴/플래그 자동 검출.

        candles[0] 이 가장 최근 영업일. flag 종료 = candles[0:flag_len],
        그 이전 = pole 구간 (candles[flag_len:flag_len+pole_len]).

        다양한 (pole_len, flag_len) 조합을 시도해 처음 통과하는 셋업을 반환.
        반환 dict: pole_start / pole_high / flag_high / flag_low / flag_avg_volume
        """
        p = self.config.params
        pole_min, pole_max = p["pole_lookback_min"], p["pole_lookback_max"]
        flag_min, flag_max = p["flag_lookback_min"], p["flag_lookback_max"]
        min_return = p["pole_min_return"]
        max_red_ratio = p["pole_max_red_ratio"]
        retracement_max = p["flag_retracement_max"]
        flag_vol_ratio = p["flag_volume_ratio"]

        try:
            closes = [int(c.get("stck_clpr", "0")) for c in candles]
            highs = [int(c.get("stck_hgpr", "0")) for c in candles]
            lows = [int(c.get("stck_lwpr", "0")) for c in candles]
            opens = [int(c.get("stck_oprc", "0")) for c in candles]
            vols = [int(c.get("acml_vol", "0")) for c in candles]
        except (TypeError, ValueError):
            return None

        # 다양한 (flag_len, pole_len) 조합 시도
        # 가장 짧은 셋업 우선 (최근 신호)
        for flag_len in range(flag_min, flag_max + 1):
            if flag_len > len(candles):
                break
            flag_slice_closes = closes[:flag_len]
            flag_slice_highs = highs[:flag_len]
            flag_slice_lows = lows[:flag_len]
            flag_slice_vols = vols[:flag_len]
            if not flag_slice_highs or not flag_slice_lows:
                continue
            flag_high = max(flag_slice_highs)
            flag_low = min(flag_slice_lows)
            flag_avg_volume = sum(flag_slice_vols) / flag_len if flag_len > 0 else 0
            if flag_avg_volume <= 0:
                continue

            for pole_len in range(pole_min, pole_max + 1):
                if flag_len + pole_len > len(candles):
                    break
                pole_slice_closes = closes[flag_len: flag_len + pole_len]
                pole_slice_highs = highs[flag_len: flag_len + pole_len]
                pole_slice_opens = opens[flag_len: flag_len + pole_len]
                pole_slice_vols = vols[flag_len: flag_len + pole_len]
                if not pole_slice_closes:
                    continue

                pole_start = pole_slice_closes[-1]  # 폴 구간 가장 옛날 종가
                pole_high = max(pole_slice_highs)
                if pole_start <= 0 or pole_high <= 0:
                    continue
                pole_return_pct = (pole_high - pole_start) / pole_start * 100
                if pole_return_pct < min_return:
                    continue

                red_count = sum(
                    1
                    for o, c in zip(pole_slice_opens, pole_slice_closes)
                    if o > 0 and c < o
                )
                red_ratio = red_count / pole_len if pole_len > 0 else 1.0
                if red_ratio > max_red_ratio:
                    continue

                # 플래그 조정 폭 ≤ 폴 폭의 retracement_max
                pole_width = pole_high - pole_start
                if pole_width <= 0:
                    continue
                actual_retracement = (pole_high - flag_low) / pole_width
                if actual_retracement > retracement_max:
                    continue

                # 거래량 수축
                pole_avg_volume = sum(pole_slice_vols) / pole_len if pole_len > 0 else 0
                if pole_avg_volume <= 0:
                    continue
                if flag_avg_volume >= pole_avg_volume * flag_vol_ratio:
                    continue

                # 통과
                return {
                    "pole_start": pole_start,
                    "pole_high": pole_high,
                    "flag_high": flag_high,
                    "flag_low": flag_low,
                    "flag_avg_volume": int(flag_avg_volume),
                    "pole_len": pole_len,
                    "flag_len": flag_len,
                }
        return None

    @staticmethod
    def _atr(highs, lows, closes, period: int) -> float:
        """ATR(period). highs/lows/closes 최신순(idx=0 이 어제)."""
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
        """KRX 전체에서 시총·거래대금 컷.

        1차 구현: 모멘텀 등락률 순위 API + 시총 사후 컷.
        VTS 호환을 위해 fetch_stock_detail 으로 1종목씩 검증.
        """
        from src.api.condition import _fetch_fluctuation_rank, fetch_stock_detail
        from src.engine.scanner import STATIC_TICKER_NAMES, ticker_names

        p = self.config.params
        min_mcap = p["min_market_cap"]
        min_trade = p["min_trade_amount"]
        max_stocks = p["max_scan_stocks"]

        try:
            ranked = await _fetch_fluctuation_rank()
        except Exception as e:
            logger.warning("눌림목 유니버스 스캔 실패: %s", e)
            return []

        filtered: list[str] = []
        all_count = 0
        for item in ranked:
            ticker = (item.get("mksc_shrn_iscd") or item.get("stck_shrn_iscd") or "").strip()
            if not ticker or not ticker.isdigit() or len(ticker) != 6:
                continue
            name = (item.get("hts_kor_isnm") or "").strip()
            # ETF/ETN 키워드 제외
            if any(kw in name for kw in (
                "KODEX", "TIGER", "RISE", "KoAct", "PLUS", "TIMEFOLIO", "WOORI", "FOCUS",
                "인버스", "레버리지",
            )):
                continue
            all_count += 1
            if len(filtered) >= max_stocks:
                break
            try:
                detail = await fetch_stock_detail(ticker)
                price = int(detail.get("stck_prpr", "0"))
                listed = int(detail.get("lstn_stcn", "0"))
                mcap = price * listed
                # 사이클 33 (2026-05-21) — KIS FHKST01010100 응답에 `prdy_vol` 필드 없음.
                # `acml_vol` (당일 누적거래량) 사용 — 5/21 funnel 30→0 사고 원인 (전일거래량 항상 0).
                # KIS 정본 응답 필드: stck_prpr, lstn_stcn, acml_vol, prdy_vrss_vol_rate (전일대비 비율, 거래량 아님)
                acml_vol = int(detail.get("acml_vol", "0"))
                trade_amt = acml_vol * price
                if mcap < min_mcap:
                    continue
                if trade_amt < min_trade:
                    # 사이클 23 P1-2 — 거래대금 미달 카운터 (시총 통과 후 거래대금 미달)
                    self._scan_stats["min_trade_amount_failed"] += 1
                    continue
                if not name:
                    name = (detail.get("hts_kor_isnm") or "").strip() or STATIC_TICKER_NAMES.get(ticker, "")
                if name:
                    ticker_names[ticker] = name
                filtered.append(ticker)
            except Exception:
                continue

        self._scan_stats["universe_candidates"] = all_count
        self._scan_stats["universe_filtered"] = len(filtered)
        return filtered

    # ------------------------------------------------------------------
    # 외부 노출 (사전 구독, 깔때기, 대시보드)
    # ------------------------------------------------------------------
    def get_scanned_tickers(self) -> list[str]:
        return self._scanned_tickers

    def get_scan_stats(self) -> dict:
        return dict(self._scan_stats)

    def get_targets_status(self) -> dict[str, dict]:
        """대시보드 노출용."""
        return {
            ticker: {
                "pole_start": info["pole_start"],
                "pole_high": info["pole_high"],
                "flag_high": info["flag_high"],
                "flag_low": info["flag_low"],
                "atr14": info["atr14"],
                "k": 0.0,
                "target_price": info["flag_high"],
                "open_price": 0,
                "target_offset": 0,
                "open_confirmed": True,
            }
            for ticker, info in self._candidates.items()
        }

    # ------------------------------------------------------------------
    # 신호 평가
    # ------------------------------------------------------------------
    def check_buy_signal(self, ticker, current_price, open_price) -> Signal:
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

        # 시간 가드
        now_t = datetime.now().time()
        entry_start = _parse_time_hhmm(self.config.params["entry_start"])
        entry_end = _parse_time_hhmm(self.config.params["entry_end"])
        if now_t < entry_start or now_t > entry_end:
            return Signal.NONE

        # 쿨다운
        today = datetime.now(KST).date()
        cd_until = self._cooldown_until.get(ticker)
        if cd_until and cd_until >= today:
            return Signal.NONE

        flag_high = info["flag_high"]
        if flag_high <= 0 or current_price <= 0:
            return Signal.NONE

        # 사이클 23 P2-1 — breakout_retention_minutes 유지시간 가드
        prev = self._prev_price.get(ticker, 0)
        self._prev_price[ticker] = current_price
        now_kst = datetime.now(KST)
        retention_min = int(self.config.params.get("breakout_retention_minutes", 3))

        first_seen = self._breakout_first_seen.get(ticker)
        if first_seen is not None:
            # 이미 돌파 대기 중
            if current_price < flag_high:
                # 후퇴 — 대기 종료
                self._breakout_first_seen.pop(ticker, None)
                logger.info("BFB 돌파 후퇴(retention 대기 종료): %s", ticker)
                return Signal.NONE
            elapsed = (now_kst - first_seen).total_seconds()
            if elapsed < retention_min * 60:
                # 아직 대기 중
                return Signal.NONE
            # retention 충족 — 정상 흐름 (거래량 컷 등 다음 가드로 진행)
            self._breakout_first_seen.pop(ticker, None)
        else:
            # 첫 돌파 감지 여부 확인 (prev<flag_high AND now>=flag_high)
            if not (prev < flag_high <= current_price):
                return Signal.NONE
            if retention_min > 0:
                # 첫 돌파 감지 → 대기 등록 + NONE
                self._breakout_first_seen[ticker] = now_kst
                logger.info(
                    "BFB 돌파 1차 감지(retention 대기 시작): %s flag_high(%d) retention=%d분",
                    ticker, flag_high, retention_min,
                )
                return Signal.NONE
            # retention_min == 0 이면 즉시 진행 (기존 동작 회귀)

        # 거래량 컷
        from src.engine.scanner import ticker_prices
        info_price = ticker_prices.get(ticker, {})
        acml_vol = int(info_price.get("acml_vol", 0) or 0)
        vol_threshold = int(info["flag_avg_volume"] * self.config.params["breakout_volume_mult"])
        if acml_vol < vol_threshold:
            return Signal.NONE

        # 진입 확정
        self._bought_today.add(ticker)
        logger.info(
            "눌림목 돌파 매수 신호: %s 현재가(%d) — flag_high(%d) 돌파 + 거래량(%d≥%d)",
            ticker, current_price, flag_high, acml_vol, vol_threshold,
        )
        self.state.buy_signals.append({
            "ticker": ticker,
            "name": "",
            "price": current_price,
            "flag_high": flag_high,
            "target_price": flag_high + (info["pole_high"] - info["pole_start"]),
            "atr": info["atr14"],
            "change_rate": 0,
            "time": datetime.now().strftime("%H:%M:%S"),
        })
        if len(self.state.buy_signals) > 20:
            self.state.buy_signals.pop(0)
        return Signal.BUY

    def check_exit_signal(self, ticker, current_price, open_price) -> Signal:
        pos = self.state.positions.get(ticker)
        if not pos:
            return Signal.NONE

        # 1) 하드 손절 -5%
        loss_rate = (
            (current_price - pos.buy_price) / pos.buy_price * 100
            if pos.buy_price > 0 else 0
        )
        stop_loss = self.config.params["stop_loss_rate"]
        if loss_rate <= stop_loss:
            logger.info(
                "눌림목 손절: %s 매수가(%d) 대비 %.1f%%",
                ticker, pos.buy_price, loss_rate,
            )
            return Signal.STOP_LOSS

        info = self._candidates.get(ticker)

        # 2) 플래그 하단 이탈
        if info and info.get("flag_low") and current_price < info["flag_low"]:
            logger.info(
                "눌림목 플래그 하단 이탈: %s 현재가(%d) < flag_low(%d)",
                ticker, current_price, info["flag_low"],
            )
            return Signal.STOP_LOSS

        # 3) 측정된 이동 (measured move) 도달 — 절반 익절 (1차 구현은 마킹만, 전량 청산은 호출자 책임)
        # 마킹 후 잔여는 ATR 트레일링으로 처리
        if info:
            pole_width = info["pole_high"] - info["pole_start"]
            measured_target = info["flag_high"] + pole_width if pole_width > 0 else 0
            already_partial = self._partial_exit.get(ticker, False)
            if measured_target > 0 and current_price >= measured_target and not already_partial:
                self._partial_exit[ticker] = True
                logger.info(
                    "눌림목 측정된 이동 도달: %s 현재가(%d) ≥ 타겟(%d) — 익절 신호",
                    ticker, current_price, measured_target,
                )
                # 1차 구현: 전량 청산 신호 (부분 매도 헬퍼는 향후 도입)
                return Signal.TRAILING_STOP

        # 4) ATR×2 트레일링
        if info and pos.high_since_buy > 0:
            atr = info.get("atr14", 0)
            mult = self.config.params["atr_trail_mult"]
            if atr > 0:
                chandelier = pos.high_since_buy - atr * mult
                if current_price <= chandelier:
                    logger.info(
                        "눌림목 ATR 트레일링: %s 고점(%d) - ATR×%.1f = %d / 현재 %d",
                        ticker, pos.high_since_buy, mult, int(chandelier), current_price,
                    )
                    return Signal.TRAILING_STOP

        # 5) 시간 청산 (max_hold_days 영업일 초과)
        max_hold = self.config.params["max_hold_days"]
        today = datetime.now(KST).date()
        # 단순 캘린더일 + 2일 보정 — 영업일 정확도 미흡하지만 1차 구현
        if pos.buy_date and (today - pos.buy_date).days > max_hold + 2:
            logger.info(
                "눌림목 시간 청산: %s buy_date=%s today=%s 보유일수 초과",
                ticker, pos.buy_date, today,
            )
            return Signal.TRAILING_STOP

        return Signal.NONE

    def check_force_clear(self) -> list[str]:
        """15:20 강제 청산 없음 — max_hold_days 시간 청산은 check_exit_signal 에서 처리."""
        return []

    def calc_buy_quantity(self, current_price: int) -> int:
        if current_price <= 0:
            return 0
        ratio = self.config.params["position_ratio"]
        amount = int(self.state.total_investment * ratio)
        qty = amount // current_price
        if qty > 0:
            return qty
        return self._fallback_one_share(current_price)

    def register_cooldown_after_exit(self, ticker: str) -> None:
        """청산 완료 후 호출 — 쿨다운 등록.

        OrderEngine.execute_sell 체결 처리 또는 RiskManager 매도 완료 시 호출 가능.
        1차 구현은 메모리만, 향후 DB 영속화 가능.
        """
        days = self.config.params["reentry_cooldown_days"]
        today = datetime.now(KST).date()
        self._cooldown_until[ticker] = today + timedelta(days=days)
        # 사이클 23 P2-1 — 청산 후 retention 대기 상태 정리
        self._breakout_first_seen.pop(ticker, None)
        # 매수 1회 가드도 함께 해제 (당일 매도 set 이 차단하므로 영향 없음)

    def _reset_daily_state(self) -> None:
        """사이클 23 P2-1 — 일일 초기화 시 _breakout_first_seen 정리."""
        self._breakout_first_seen.clear()
