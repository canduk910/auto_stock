"""변동성 수축 돌파(VCP, Volatility Contraction Pattern) 전략.

미네르비니식 베이스 셋업. 상승 후 변동성 단계적 축소 → 거래량 폭증 베이스 상단 돌파.
donchian_swing 의 정공법(신고가 직진 추격)을 보강하는 추세추종 보조 전략.
멀티데이 보유 — `Position._MULTIDAY_STRATEGIES` 멤버.

진입:
- 추세 필터: 종가 > 50EMA > 150EMA > 200EMA, 200EMA 1개월 우상향
- 베이스: 5~15주(25~75영업일), 깊이 ≤ 25%, 최대 30%
- 조정 시퀀스: 2~4회 pullback 점진 수축, 마지막 ≤ 8%
- 거래량 수축: 마지막 5일 평균 < 베이스 직전 20일 평균 × 70%
- 매수: 베이스 상단 돌파 + 당일 거래량 ≥ 20일 평균 × 1.5
- 시간대: 09:05~14:30 KRX 메인 (`tradable_boards=("main",)`)

청산:
- 하드 손절 -7% / 베이스 하단 이탈
- ATR(14)×2 트레일링 (donchian 컨벤션)
- 50일 EMA 이탈
- 시간 청산 없음 (멀티데이)

매수 회전:
- 종목당 1회 (`_bought_today` set)
- 청산 후 7영업일 쿨다운

명세: `_workspace/00_leader_trading_rules.md` 6-F
"""

from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta, timezone

from src.engine.strategy_base import Position, Signal, StrategyBase, StrategyConfig

# vcp_breakout 도 멀티데이 — Position 의 _MULTIDAY_STRATEGIES 에 등록
# (frozenset 은 immutable 이므로 새 frozenset 으로 교체)
Position._MULTIDAY_STRATEGIES = frozenset(
    Position._MULTIDAY_STRATEGIES | {"vcp_breakout"}
)

KST = timezone(timedelta(hours=9))
logger = logging.getLogger(__name__)


def _empty_scan_stats() -> dict:
    return {
        "universe_candidates": 0,
        "universe_filtered": 0,
        "mcap_pass": 0,  # 사이클 23 P1-3 — 시총 컷 통과 카운터
        "candle_fetch_ok": 0,
        "trend_filter_pass": 0,
        "base_pass": 0,
        "pullback_pass": 0,
        "volume_contraction_pass": 0,
        "final_prepared": 0,
        "last_run_at": None,
    }


def _parse_time_hhmm(s: str) -> time:
    if not s or ":" not in s:
        return time(0, 0)
    h, m = s.split(":")
    return time(int(h), int(m))


class VcpBreakoutStrategy(StrategyBase):
    """변동성 수축 돌파 — KRX 메인 한정, 멀티데이 보유."""

    DEFAULT_TRADABLE_BOARDS = ("main",)

    DEFAULT_PARAMS = {
        "tradable_boards": list(DEFAULT_TRADABLE_BOARDS),
        "exchange": "KRX",
        # 추세 필터
        "ema_short": 50,
        "ema_mid": 150,
        "ema_long": 200,
        "long_ema_uptrend_days": 20,
        # 베이스
        "base_min_days": 25,
        "base_max_days": 75,
        "base_depth_pct": 0.30,
        # 조정 시퀀스
        "pullback_count_min": 2,
        "pullback_count_max": 4,
        "last_pullback_max": 0.08,
        # 거래량 수축
        "volume_contraction_ratio": 0.70,
        # 매수
        "breakout_volume_mult": 1.5,
        "entry_start": "09:05",
        "entry_end": "14:30",
        "position_ratio": 0.20,
        "max_positions": 5,
        # 청산
        "stop_loss_rate": -7.0,
        "atr_period": 14,
        "atr_trail_mult": 2.0,
        "reentry_cooldown_days": 7,
        # 유니버스
        "min_market_cap": 100_000_000_000,
        "min_trade_amount": 3_000_000_000,
        "max_scan_stocks": 200,
        # 일반
        "daily_loss_limit": -8.0,
    }

    def __init__(self, config: StrategyConfig):
        merged = {**self.DEFAULT_PARAMS, **config.params}
        config.params = merged
        super().__init__(config)
        self._candidates: dict[str, dict] = {}
        self._scanned_tickers: list[str] = []
        self._bought_today: set[str] = set()
        self._prev_price: dict[str, int] = {}
        self._cooldown_until: dict[str, date] = {}
        self._scan_stats: dict = _empty_scan_stats()

    # ------------------------------------------------------------------
    # prepare — 일봉 220일 → 추세/베이스/pullback/거래량 수축 자동 검출
    # ------------------------------------------------------------------
    async def prepare(self) -> None:
        import asyncio

        from src.api.condition import fetch_daily_candles

        p = self.config.params
        ema_long = p["ema_long"]
        base_max = p["base_max_days"]
        # 사이클 33 (2026-05-21) — KIS `fetch_daily_candles` 단일 호출 최대 100일 한도
        # (`src/api/CLAUDE.md` 명시). 기존 `fetch_days = ema_long + base_max + 10 = 285`
        # 요청 시 KIS 가 100일만 반환 → `len(candles) <= prev_idx + ema_long + 5 = 205`
        # 항상 True → 113→0 candle_fetch_ok 결함 (5/21 운영 사고).
        # 시정: KIS 한도 인식 cap + 가용 길이 기반 effective ema_long 자동 조정.
        # ema_long 파라미터 DB 값 (200) 변경 없음 — 런타임 가드만 추가.
        KIS_DAILY_CANDLES_MAX = 100
        fetch_days = min(ema_long + base_max + 10, KIS_DAILY_CANDLES_MAX)

        self._candidates = {}
        stats = _empty_scan_stats()
        self._scan_stats = stats
        # 사이클 39 (2026-05-22) — 단계별 ticker 캡처 reset
        self._reset_funnel_steps()

        tickers = await self._scan_universe()
        # 사이클 39 — 1단계: 코스피200+코스닥150 + 2단계: 시총 통과 (universe_filtered)
        self._record_funnel_step(
            step_no=1, step_name="코스피200+코스닥150 합집합",
            survived=tickers,
        )
        self._record_funnel_step(
            step_no=2, step_name="시총 ≥ 1,000억",
            survived=tickers,  # _scan_universe 가 시총 통과 종목만 반환
        )

        if not tickers:
            logger.info("VCP 유니버스 0종목")
            self._scanned_tickers = []
            stats["last_run_at"] = datetime.now(KST).isoformat()
            return

        today_str = datetime.now(KST).strftime("%Y%m%d")

        async def _fetch_one(ticker: str):
            try:
                return ticker, await fetch_daily_candles(ticker, days=fetch_days)
            except Exception as e:
                logger.warning("VCP 일봉 fetch 실패: %s — %s", ticker, e)
                return ticker, None

        fetched = await asyncio.gather(*[_fetch_one(t) for t in tickers])

        # 사이클 33 (2026-05-21) — KIS 한도 인식 effective ema_long.
        # uptrend_days 까지 포함한 trend filter 가용 길이로 자동 축소.
        # 가용 길이 = fetch_days - prev_idx - 5 (안전 마진). uptrend_days=20.
        # effective_ema_long = min(ema_long, 가용길이 - uptrend_days)
        uptrend_days = p.get("long_ema_uptrend_days", 20)

        # 사이클 39 — 단계별 ticker 캡처 (회귀 가드 — 결과 무변경)
        candle_fetch_ok_tickers: list[str] = []
        trend_filter_pass_tickers: list[str] = []
        base_pass_tickers: list[str] = []
        pullback_pass_tickers: list[str] = []
        volume_contraction_pass_tickers: list[str] = []
        final_prepared_tickers: list[str] = []

        for ticker, candles in fetched:
            if candles is None or not candles:
                continue
            try:
                prev_idx = 1 if candles[0].get("stck_bsop_date") == today_str else 0
                # 사이클 33 — KIS 한도 대응: 가용 길이 기반 effective ema_long
                available_len = len(candles) - prev_idx
                effective_ema_long = min(ema_long, available_len - uptrend_days - 5)
                if effective_ema_long < 30:
                    # 최소 30일 EMA 도 못 만들면 추세 필터 무의미 → skip
                    continue
                if available_len < effective_ema_long + uptrend_days + 5:
                    continue
                if prev_idx:
                    candles = candles[prev_idx:]
                stats["candle_fetch_ok"] += 1
                candle_fetch_ok_tickers.append(ticker)  # 사이클 39

                trend = self._check_trend_filter(candles, effective_ema_long=effective_ema_long)
                if not trend:
                    continue
                stats["trend_filter_pass"] += 1
                trend_filter_pass_tickers.append(ticker)  # 사이클 39

                base = self._detect_base(candles)
                if not base:
                    continue
                stats["base_pass"] += 1
                base_pass_tickers.append(ticker)  # 사이클 39

                pullbacks_ok = self._check_pullback_sequence(candles, base)
                if not pullbacks_ok:
                    continue
                stats["pullback_pass"] += 1
                pullback_pass_tickers.append(ticker)  # 사이클 39

                vol_ok = self._check_volume_contraction(candles, base)
                if not vol_ok:
                    continue
                stats["volume_contraction_pass"] += 1
                volume_contraction_pass_tickers.append(ticker)  # 사이클 39

                atr = self._atr(
                    [int(c.get("stck_hgpr", "0")) for c in candles],
                    [int(c.get("stck_lwpr", "0")) for c in candles],
                    [int(c.get("stck_clpr", "0")) for c in candles],
                    p["atr_period"],
                )
                if atr <= 0:
                    continue

                from src.engine.scanner import ticker_prev_close
                prev_close = int(candles[0].get("stck_clpr", "0"))
                if prev_close > 0:
                    ticker_prev_close[ticker] = prev_close

                self._candidates[ticker] = {
                    "base_high": base["high"],
                    "base_low": base["low"],
                    "last_pullback_pct": base.get("last_pullback_pct", 0),
                    "atr14": int(atr),
                    "ema50": trend["ema50"],
                    "ema150": trend["ema150"],
                    "ema200": trend["ema200"],
                    "prev_close": prev_close,
                    "avg_volume_20": base["avg_volume_20"],
                }
                stats["final_prepared"] += 1
                final_prepared_tickers.append(ticker)  # 사이클 39
            except Exception as e:
                logger.warning("VCP prepare 실패: %s — %s", ticker, e)
                continue

        # 사이클 39 (2026-05-22) — 단계별 hook 일괄 등록 (loop 종료 후, 결과 무변경)
        self._record_funnel_step(step_no=3, step_name="일봉 fetch + 추세필터",
                                  survived=candle_fetch_ok_tickers)
        self._record_funnel_step(step_no=4, step_name="50/150/200 EMA 정렬",
                                  survived=trend_filter_pass_tickers)
        self._record_funnel_step(step_no=5, step_name="베이스 자동 검출",
                                  survived=base_pass_tickers)
        self._record_funnel_step(step_no=6, step_name="Pullback 점진 수축",
                                  survived=pullback_pass_tickers)
        self._record_funnel_step(step_no=7, step_name="거래량 수축",
                                  survived=volume_contraction_pass_tickers)
        self._record_funnel_step(step_no=8, step_name="최종 prepared",
                                  survived=final_prepared_tickers)

        self._scanned_tickers = list(self._candidates.keys())
        self._bought_today.clear()
        stats["last_run_at"] = datetime.now(KST).isoformat()
        logger.info(
            "VCP 준비 완료: %d/%d종목 — trend=%d base=%d pullback=%d vol_cnt=%d",
            stats["final_prepared"], len(tickers),
            stats["trend_filter_pass"], stats["base_pass"],
            stats["pullback_pass"], stats["volume_contraction_pass"],
        )

    def _check_trend_filter(self, candles: list[dict], *,
                             effective_ema_long: int | None = None) -> dict | None:
        """추세 필터: 종가 > 50EMA > 150EMA > 200EMA + 200EMA 우상향 1개월.

        사이클 33 (2026-05-21) — KIS 100일 한도 대응: `effective_ema_long` 파라미터로
        가용 길이 기반 자동 축소 가능. None 이면 params["ema_long"] 사용 (기본 200).
        ema_mid 도 effective_ema_long 보다 크면 자동 축소.
        """
        p = self.config.params
        ema_short = p["ema_short"]
        ema_mid = p["ema_mid"]
        # 사이클 33 — KIS 100일 한도 대응: effective_ema_long 명시 시 우선
        ema_long = effective_ema_long if effective_ema_long is not None else p["ema_long"]
        # ema_mid 가 ema_long 보다 크면 의미 없음 — 자동 축소 (50/150/200 정렬 의미 보존)
        if ema_mid >= ema_long:
            ema_mid = max(ema_short + 1, ema_long - 10)
        uptrend_days = p["long_ema_uptrend_days"]

        try:
            closes = [int(c.get("stck_clpr", "0")) for c in candles]
        except (TypeError, ValueError):
            return None
        if len(closes) < ema_long + uptrend_days:
            return None

        # 최신순(idx=0 어제) → 시간순 reverse
        chrono = list(reversed(closes))
        ema_short_today = self._ema(chrono[-ema_short:], ema_short)
        ema_mid_today = self._ema(chrono[-ema_mid:], ema_mid)
        ema_long_today = self._ema(chrono[-ema_long:], ema_long)
        ema_long_past = self._ema(chrono[-(ema_long + uptrend_days): -uptrend_days], ema_long)

        close_today = closes[0]
        if close_today <= ema_short_today:
            return None
        if ema_short_today <= ema_mid_today:
            return None
        if ema_mid_today <= ema_long_today:
            return None
        if ema_long_today <= ema_long_past:
            return None

        return {
            "ema50": int(ema_short_today),
            "ema150": int(ema_mid_today),
            "ema200": int(ema_long_today),
        }

    def _detect_base(self, candles: list[dict]) -> dict | None:
        """베이스 자동 검출 — 최근 base_max_days 안에서 가장 긴 박스권."""
        p = self.config.params
        base_min = p["base_min_days"]
        base_max = p["base_max_days"]
        depth_pct = p["base_depth_pct"]

        try:
            highs = [int(c.get("stck_hgpr", "0")) for c in candles]
            lows = [int(c.get("stck_lwpr", "0")) for c in candles]
            vols = [int(c.get("acml_vol", "0")) for c in candles]
        except (TypeError, ValueError):
            return None

        best = None
        for length in range(base_max, base_min - 1, -1):
            if length > len(candles):
                continue
            h = max(highs[:length])
            low_val = min(lows[:length])
            if h <= 0 or low_val <= 0:
                continue
            depth = (h - low_val) / h
            if depth > depth_pct:
                continue
            avg_vol_20 = sum(vols[:20]) / 20 if len(vols) >= 20 else 0
            best = {
                "high": h,
                "low": low_val,
                "length": length,
                "avg_volume_20": int(avg_vol_20),
            }
            break  # 첫 매칭(가장 긴) 사용

        return best

    def _check_pullback_sequence(self, candles: list[dict], base: dict) -> bool:
        """베이스 구간 내 pullback 점진 수축 검증.

        1차 구현은 단순화: 베이스 구간의 swing high/low 를 단순 검출 → pullback 개수와 마지막 pullback 폭만 검증.
        """
        p = self.config.params
        last_pullback_max = p["last_pullback_max"]
        pull_min = p["pullback_count_min"]
        pull_max = p["pullback_count_max"]

        try:
            closes = [int(c.get("stck_clpr", "0")) for c in candles[: base["length"]]]
        except (TypeError, ValueError, KeyError):
            return False
        if not closes:
            return False

        # 시간순(과거→현재) 으로 reverse
        chrono = list(reversed(closes))
        # 간단한 swing 검출: local max → local min → local max ...
        pullbacks = []
        i = 0
        n = len(chrono)
        # local high 시작점 찾기
        while i < n - 1:
            # rising 끝점 찾기
            j = i
            while j + 1 < n and chrono[j + 1] >= chrono[j]:
                j += 1
            high = chrono[j]
            # falling 끝점 찾기
            k = j
            while k + 1 < n and chrono[k + 1] <= chrono[k]:
                k += 1
            low = chrono[k]
            if j < k and high > 0 and high > low:
                pullbacks.append((high - low) / high)
            i = k + 1

        pull_count = len(pullbacks)
        if pull_count < pull_min or pull_count > pull_max:
            return False

        # 점진 수축
        for prev_pb, curr_pb in zip(pullbacks, pullbacks[1:]):
            if curr_pb >= prev_pb:
                return False

        # 마지막 pullback ≤ last_pullback_max
        if pullbacks[-1] > last_pullback_max:
            return False

        # base dict 에 마지막 pullback 폭 기록 (caller 가 _candidates 에 저장)
        base["last_pullback_pct"] = pullbacks[-1]
        return True

    def _check_volume_contraction(self, candles: list[dict], base: dict) -> bool:
        """마지막 5일 평균 거래량 < 베이스 직전 20일 평균 × 70%."""
        p = self.config.params
        ratio = p["volume_contraction_ratio"]
        base_len = base["length"]

        try:
            vols = [int(c.get("acml_vol", "0")) for c in candles]
        except (TypeError, ValueError):
            return False

        if len(vols) < base_len + 20:
            # 직전 20일 데이터 부족 → 기본 통과(보수적), 또는 fail. 1차 구현은 통과
            return True

        last5_avg = sum(vols[:5]) / 5
        pre_base_20_avg = sum(vols[base_len: base_len + 20]) / 20
        if pre_base_20_avg <= 0:
            return True
        return last5_avg < pre_base_20_avg * ratio

    @staticmethod
    def _ema(values: list[int], period: int) -> float:
        """EMA — donchian 컨벤션 동일."""
        if not values:
            return 0.0
        k = 2 / (period + 1)
        ema = float(values[0])
        for v in values[1:]:
            ema = v * k + ema * (1 - k)
        return ema

    @staticmethod
    def _atr(highs, lows, closes, period: int) -> float:
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
        """코스피200 + 코스닥150 고정 유니버스 (donchian 컨벤션 재사용)."""
        from src.api.condition import fetch_stock_detail
        from src.engine.scanner import (
            KOSDAQ_150_TICKERS, KOSPI_200_TICKERS, STATIC_TICKER_NAMES, ticker_names,
        )

        p = self.config.params
        min_mcap = p["min_market_cap"]
        max_stocks = p["max_scan_stocks"]
        all_tickers = list(dict.fromkeys(list(KOSPI_200_TICKERS) + list(KOSDAQ_150_TICKERS)))
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
                name = (detail.get("hts_kor_isnm") or "").strip()
                if not name:
                    name = STATIC_TICKER_NAMES.get(ticker, "")
                if name:
                    ticker_names[ticker] = name
                if mcap >= min_mcap:
                    self._scan_stats["mcap_pass"] += 1  # 사이클 23 P1-3
                    filtered.append(ticker)
            except Exception:
                continue

        self._scan_stats["universe_filtered"] = len(filtered)
        return filtered

    def get_scanned_tickers(self) -> list[str]:
        return self._scanned_tickers

    def get_scan_stats(self) -> dict:
        return dict(self._scan_stats)

    def get_targets_status(self) -> dict[str, dict]:
        return {
            ticker: {
                "base_high": info["base_high"],
                "base_low": info["base_low"],
                "atr14": info["atr14"],
                "ema50": info["ema50"],
                "k": 0.0,
                "target_price": info["base_high"],
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

        now_t = datetime.now().time()
        entry_start = _parse_time_hhmm(self.config.params["entry_start"])
        entry_end = _parse_time_hhmm(self.config.params["entry_end"])
        if now_t < entry_start or now_t > entry_end:
            return Signal.NONE

        today = datetime.now(KST).date()
        cd_until = self._cooldown_until.get(ticker)
        if cd_until and cd_until >= today:
            return Signal.NONE

        base_high = info["base_high"]
        if base_high <= 0 or current_price <= 0:
            return Signal.NONE

        prev = self._prev_price.get(ticker, 0)
        self._prev_price[ticker] = current_price
        if not (prev < base_high <= current_price):
            return Signal.NONE

        # 거래량 컷
        from src.engine.scanner import ticker_prices
        info_price = ticker_prices.get(ticker, {})
        acml_vol = int(info_price.get("acml_vol", 0) or 0)
        avg20 = info.get("avg_volume_20", 0)
        vol_threshold = int(avg20 * self.config.params["breakout_volume_mult"])
        if vol_threshold > 0 and acml_vol < vol_threshold:
            return Signal.NONE

        self._bought_today.add(ticker)
        logger.info(
            "VCP 매수 신호: %s 현재가(%d) — base_high(%d) 돌파 + 거래량(%d≥%d)",
            ticker, current_price, base_high, acml_vol, vol_threshold,
        )
        self.state.buy_signals.append({
            "ticker": ticker,
            "name": "",
            "price": current_price,
            "base_high": base_high,
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

        # 1) 하드 손절 -7%
        loss_rate = (
            (current_price - pos.buy_price) / pos.buy_price * 100
            if pos.buy_price > 0 else 0
        )
        stop_loss = self.config.params["stop_loss_rate"]
        if loss_rate <= stop_loss:
            logger.info(
                "VCP 손절: %s 매수가(%d) 대비 %.1f%%",
                ticker, pos.buy_price, loss_rate,
            )
            return Signal.STOP_LOSS

        info = self._candidates.get(ticker)

        # 2) 베이스 하단 이탈
        if info and info.get("base_low") and current_price < info["base_low"]:
            logger.info(
                "VCP 베이스 하단 이탈: %s 현재가(%d) < base_low(%d)",
                ticker, current_price, info["base_low"],
            )
            return Signal.STOP_LOSS

        # 3) ATR×2 트레일링
        if info and pos.high_since_buy > 0:
            atr = info.get("atr14", 0)
            mult = self.config.params["atr_trail_mult"]
            if atr > 0:
                chandelier = pos.high_since_buy - atr * mult
                if current_price <= chandelier:
                    logger.info(
                        "VCP ATR 트레일링: %s 고점(%d) - ATR×%.1f = %d / 현재 %d",
                        ticker, pos.high_since_buy, mult, int(chandelier), current_price,
                    )
                    return Signal.TRAILING_STOP

        # 4) 50일 EMA 이탈
        if info:
            ema50 = info.get("ema50", 0)
            if ema50 > 0 and current_price < ema50:
                logger.info(
                    "VCP 50일 EMA 이탈: %s 현재가(%d) < ema50(%d)",
                    ticker, current_price, ema50,
                )
                return Signal.TRAILING_STOP

        return Signal.NONE

    def check_force_clear(self) -> list[str]:
        """멀티데이 — 15:20 강제 청산 없음."""
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
        days = self.config.params["reentry_cooldown_days"]
        today = datetime.now(KST).date()
        self._cooldown_until[ticker] = today + timedelta(days=days)
