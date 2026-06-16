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

from __future__ import annotations

import logging
from datetime import datetime, time, timezone, timedelta

from src.engine.strategy_base import FunnelStage, Signal, StrategyBase, StrategyConfig

KST = timezone(timedelta(hours=9))


# 사이클 47 (2026-05-22, refactor-review 카드 #3) — Funnel 단계 정의 모듈 상수.
# step_name 은 정적 — 동적 값 (donchian_period, long_ma_period 등) 은 step_conditions 통해 노출.
FUNNEL_STAGES: tuple[FunnelStage, ...] = (
    FunnelStage(1, "코스피200+코스닥150 합집합"),
    FunnelStage(2, "시총 컷 통과"),
    FunnelStage(3, "일봉 fetch + 전일종가>0"),
    FunnelStage(4, "신고가 돌파"),
    FunnelStage(5, "EMA 우상향 + 종가>EMA"),
    FunnelStage(6, "거래대금 평균 대비 통과"),
    FunnelStage(7, "ATR(14) > 0"),
    FunnelStage(8, "최종 후보"),
)


def _empty_scan_stats() -> dict:
    return {
        "universe_candidates": 0,
        "universe_filtered": 0,
        "candle_fetch_ok": 0,
        "donchian_pass": 0,
        "ema_uptrend_pass": 0,
        "volume_pass": 0,
        "atr_pass": 0,
        "box_contraction_pass": 0,  # 사이클 23 P2-4 — 박스 수축 통과 카운터
        "final_prepared": 0,
        "last_run_at": None,
    }

logger = logging.getLogger(__name__)


class DonchianSwingStrategy(StrategyBase):
    """20일 신고가 스윙 돌파 전략."""

    # 매매 가능 보드 (Phase 8) — 추세추종은 일중 변동성 필요. KRX 메인만
    DEFAULT_TRADABLE_BOARDS = ("main",)

    DEFAULT_PARAMS = {
        "tradable_boards": list(DEFAULT_TRADABLE_BOARDS),
        "exchange": "KRX",
        "donchian_period": 20,
        "long_ma_period": 60,
        "volume_period": 20,
        "volume_multiplier": 1.5,
        "atr_period": 14,
        "atr_trail_mult": 2.0,
        # 사이클 119 (2026-06-12) — Q2=D 임시 완화 (사이클 118 ACC_TRDVAL 매핑 시정
        # 효과 검증 *전* 안전 영역). 사이클 121+ D+3/D+7/D+14 점진 복원 권고:
        #   Step 1 (D+3): min_market_cap 500억 → 1,000억
        #   Step 2 (D+7): min_trade_amount 10억 → 30억
        #   Step 3 (D+14): 2,000억 / 30억 정착 (KOSPI200+KOSDAQ150 ~350종목 원본 임계 영역은
        #     stock_master ~2,800 영역에서 후보 풀 폭축 위험)
        "min_market_cap": 50_000_000_000,    # 500억 (Q2=D 임시 완화, 원본 3,000억)
        "min_trade_amount": 1_000_000_000,   # 10억 (Q2=D 임시 완화, 원본 50억)
        "max_scan_stocks": 200,
        # 사이클 119 (2026-06-12) — Plan Phase C UI 운영자 필터링 호환 영역
        "exclude_tickers": [],
        # 사이클 119 (2026-06-12) — Q5=A donchian MAIN 단독 (사이클 26 DEFAULT_TRADABLE_BOARDS
        # =("main",) 영속 + NXT 의존성 0). None=전체 (KRX 메인 영역 단독 매매).
        "nxt_tradable": None,
        "gap_skip_threshold": 3.0,
        "stop_loss_rate": -7.0,
        "position_ratio": 0.20,
        "max_positions": 5,
        "daily_loss_limit": -8.0,
        # 사이클 23 P2-2 — 시간 기반 청산 (멀티데이 약한 이탈 빠른 정리)
        "breakout_fail_n_days": 5,
        # 사이클 23 P2-3 — 돌파폭 과열 상한 (추격 금지)
        "max_breakout_extension_pct": 3.0,
        # 사이클 23 P2-4 — 박스 수축 보조 필터
        "box_contraction_period": 10,
        "max_box_volatility_pct": 5.0,
    }

    def __init__(self, config: StrategyConfig):
        merged = {**self.DEFAULT_PARAMS, **config.params}
        config.params = merged
        super().__init__(config)
        self._candidates: dict[str, dict] = {}  # ticker -> {prev_close, atr, ...}
        self._scanned_tickers: list[str] = []
        self._bought_today: set[str] = set()  # 당일 진입 시도 종목 (중복 방지)
        # 사이클 23 P2-2 — ticker -> 진입 시 돌파선 (20일 신고가)
        self._breakout_high: dict[str, int] = {}
        # 단계별 탈락 통계 — prepare() 실행 시마다 갱신, 프론트 깔때기 시각화용
        self._scan_stats: dict = _empty_scan_stats()

    async def prepare(self) -> None:
        """장 시작 전: 유니버스 스캔 → 종목별 일봉 fetch → 신고가/MA/ATR/거래량 검증."""
        import asyncio

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
        # 사이클 39 (2026-05-22) — 단계별 ticker 캡처 reset
        self._reset_funnel_steps()

        tickers = await self._scan_universe()
        # 사이클 47 (2026-05-22, refactor-review 카드 #3) — FUNNEL_STAGES 위임
        min_mcap_billion = params["min_market_cap"] / 100_000_000
        self._record_funnel_pipeline_step(
            FUNNEL_STAGES[0],
            survived=tickers,
            step_conditions="코스피200 + 코스닥150 고정 유니버스",
        )
        self._record_funnel_pipeline_step(
            FUNNEL_STAGES[1],
            survived=tickers,
            step_conditions=f"시총 ≥ {min_mcap_billion:.0f}억",
        )

        if not tickers:
            logger.info("도치안 스윙 유니버스 0종목")
            self._scanned_tickers = []
            stats["last_run_at"] = datetime.now(KST).isoformat()
            return

        # 60일 + 여유 = 65일 일봉 fetch (+1: candles[0]=오늘 부분봉 케이스 폴백 여유)
        fetch_days = max(long_ma_period + 5, donchian_period + 5) + 1
        today_str = datetime.now(KST).strftime("%Y%m%d")
        prepared = 0
        short_candles_logged = False  # 길이 부족 시 첫 1건만 system_logs에 기록

        # 일봉 fetch 병렬화 — KIS Rate Limit(20/sec)는 base.py Semaphore에서 직렬화되므로
        # asyncio.gather로 안전하게 묶을 수 있음. 100+ 종목 순차 호출(5~10초) → 1~2초로 단축
        async def _fetch_one(ticker: str):
            try:
                return ticker, await fetch_daily_candles(ticker, days=fetch_days)
            except Exception as e:
                logger.warning("도치안 일봉 fetch 실패: %s — %s", ticker, e)
                return ticker, None

        fetched = await asyncio.gather(*[_fetch_one(t) for t in tickers])

        # 사이클 39 — 단계별 ticker 캡처 (회귀 가드 — 결과 무변경)
        # 사이클 41 (2026-05-22) — 탈락 사유 캡처 (H-4 시장 자연 vs 코드 결함 진단)
        candle_fetch_ok_tickers: list[str] = []
        donchian_pass_tickers: list[str] = []
        ema_uptrend_pass_tickers: list[str] = []
        volume_pass_tickers: list[str] = []
        atr_pass_tickers: list[str] = []
        final_prepared_tickers: list[str] = []
        # 사이클 41 — 탈락 사유
        candle_fetch_excluded: list[dict] = []
        donchian_excluded: list[dict] = []
        ema_excluded: list[dict] = []
        volume_excluded: list[dict] = []
        atr_excluded: list[dict] = []

        from src.engine.strategy_base import _resolve_ticker_name

        for ticker, candles in fetched:
            ticker_name = _resolve_ticker_name(ticker)
            if candles is None:
                candle_fetch_excluded.append({
                    "ticker": ticker, "name": ticker_name,
                    "reason": "KIS 일봉 응답 None",
                })
                continue
            try:
                # candles 변수는 fetch 결과를 그대로 사용 (await 제거)
                pass
                if len(candles) < long_ma_period + 1:
                    if not short_candles_logged:
                        from src.db.system_logs import write_log
                        msg = (
                            f"도치안 일봉 길이 부족 — {ticker}: "
                            f"received {len(candles)}, required {long_ma_period + 1} "
                            f"(요청 {fetch_days}일). KIS 응답 불충분 가능"
                        )
                        logger.warning(msg)
                        try:
                            await write_log("WARNING", msg)
                        except Exception:
                            pass
                        short_candles_logged = True
                    continue

                # candles[0]의 거래일이 오늘이면 "오늘 부분봉"이므로 candles[1]을 전일로 사용
                # (VB/LTV에 적용한 prev_idx 분기와 동일 — 장중 prepare 시 candles[0]이 5/8 일중
                # 데이터로 들어와 5/7 종가 vs 직전 20일 최고가 비교가 어긋나던 결함 차단)
                prev_idx = 1 if candles[0].get("stck_bsop_date") == today_str else 0
                if len(candles) <= prev_idx + long_ma_period:
                    continue
                # prev_idx 적용 — 이후 슬라이스는 모두 candles[prev_idx:]가 "전일" 기준
                if prev_idx:
                    candles = candles[prev_idx:]

                # candles[0]이 가장 최근일(전일). closes[0]이 가장 최근.
                closes = [int(c.get("stck_clpr", "0")) for c in candles]
                highs = [int(c.get("stck_hgpr", "0")) for c in candles]
                lows = [int(c.get("stck_lwpr", "0")) for c in candles]
                vols = [int(c.get("acml_vol", "0")) for c in candles]

                prev_close = closes[0]
                if prev_close <= 0:
                    continue
                stats["candle_fetch_ok"] += 1
                candle_fetch_ok_tickers.append(ticker)  # 사이클 39

                # 1) 20일 신고가 돌파 검증 — 어제 종가가 그 이전 20일 최고가 초과
                # 사이클 123 — get_donchian_high DB 헬퍼 우선 + KIS 캔들 fallback (사이클 14 영속)
                from src.db.stock_master_daily import get_donchian_high
                db_high = await get_donchian_high(ticker, days=donchian_period)
                kis_high = max(highs[1: donchian_period + 1])
                if db_high is not None and db_high > 0:
                    prior_high = db_high
                    stats.setdefault("db_high_hit", 0)
                    stats["db_high_hit"] += 1
                else:
                    prior_high = kis_high  # 사이클 14 영속 (fetch_daily_candles 활용)
                    stats.setdefault("db_high_miss", 0)
                    stats["db_high_miss"] += 1
                if prev_close <= prior_high:
                    # 사이클 41 — 신고가 미달 사유 (수치 포함, H-4 진단)
                    donchian_excluded.append({
                        "ticker": ticker, "name": ticker_name,
                        "reason": (
                            f"전일 종가 {prev_close:,} ≤ "
                            f"직전 {donchian_period}일 신고가 {prior_high:,}"
                        ),
                    })
                    continue
                stats["donchian_pass"] += 1
                donchian_pass_tickers.append(ticker)  # 사이클 39

                # 2) 60일 EMA 우상향 + 종가 > EMA
                ema_today = self._ema(list(reversed(closes[:long_ma_period])), long_ma_period)
                ema_yesterday = self._ema(list(reversed(closes[1: long_ma_period + 1])), long_ma_period)
                if ema_today <= ema_yesterday:
                    ema_excluded.append({
                        "ticker": ticker, "name": ticker_name,
                        "reason": (
                            f"{long_ma_period}일 EMA 우상향 미충족 "
                            f"(오늘 {int(ema_today):,} ≤ 어제 {int(ema_yesterday):,})"
                        ),
                    })
                    continue
                if prev_close <= ema_today:
                    ema_excluded.append({
                        "ticker": ticker, "name": ticker_name,
                        "reason": (
                            f"전일 종가 {prev_close:,} ≤ {long_ma_period}일 EMA "
                            f"{int(ema_today):,}"
                        ),
                    })
                    continue
                stats["ema_uptrend_pass"] += 1
                ema_uptrend_pass_tickers.append(ticker)  # 사이클 39

                # 3) 거래량(거래대금 근사 = 종가×거래량) 20일 평균의 1.5배 이상
                today_turnover = closes[0] * vols[0]
                avg_turnover = sum(closes[i] * vols[i] for i in range(1, volume_period + 1)) / volume_period
                if avg_turnover <= 0 or today_turnover < avg_turnover * volume_mult:
                    if avg_turnover > 0:
                        ratio = today_turnover / avg_turnover
                        volume_excluded.append({
                            "ticker": ticker, "name": ticker_name,
                            "reason": (
                                f"거래대금 비율 {ratio:.2f}× < 임계 {volume_mult:.1f}×"
                            ),
                        })
                    else:
                        volume_excluded.append({
                            "ticker": ticker, "name": ticker_name,
                            "reason": f"{volume_period}일 평균 거래대금 = 0",
                        })
                    continue
                stats["volume_pass"] += 1
                volume_pass_tickers.append(ticker)  # 사이클 39

                # 4) ATR(14) — Wilder 단순화: 평균 True Range
                atr = self._atr(highs, lows, closes, atr_period)
                if atr <= 0:
                    atr_excluded.append({
                        "ticker": ticker, "name": ticker_name,
                        "reason": "ATR 계산 실패 (값 ≤ 0)",
                    })
                    continue
                stats["atr_pass"] += 1
                atr_pass_tickers.append(ticker)  # 사이클 39

                # 사이클 23 P2-4 — 박스 수축 보조 필터 (변동성 축소 후 돌파 패턴 강화)
                box_period = int(self.config.params.get("box_contraction_period", 10))
                max_box_vol = float(self.config.params.get("max_box_volatility_pct", 5.0))
                if len(candles) > box_period:
                    box_highs = highs[1: box_period + 1]
                    box_lows = lows[1: box_period + 1]
                    box_closes = closes[1: box_period + 1]
                    if box_highs and box_lows and box_closes:
                        box_range = max(box_highs) - min(box_lows)
                        box_mean = sum(box_closes) / len(box_closes)
                        if box_mean > 0:
                            vol_pct = box_range / box_mean * 100
                            if vol_pct > max_box_vol:
                                continue  # 박스 수축 실패 (변동성 너무 큼)
                            stats["box_contraction_pass"] += 1
                        else:
                            continue

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
                final_prepared_tickers.append(ticker)  # 사이클 39
            except Exception as e:
                logger.warning("도치안 스윙 prepare 실패: %s — %s", ticker, e)
                continue

        # 사이클 47 — FUNNEL_STAGES 위임 (사이클 39+41 hook 동작 동일).
        # step_name 은 정적 (FUNNEL_STAGES 상수), 동적 파라미터 (donchian_period 등) 는 step_conditions 노출.
        self._record_funnel_pipeline_step(
            FUNNEL_STAGES[2],
            survived=candle_fetch_ok_tickers, excluded=candle_fetch_excluded,
            step_conditions=f"KIS 일봉 ≥ {long_ma_period + 1}일 + 전일 종가 > 0",
        )
        self._record_funnel_pipeline_step(
            FUNNEL_STAGES[3],
            survived=donchian_pass_tickers, excluded=donchian_excluded,
            step_conditions=f"전일 종가 > 직전 {donchian_period}일 최고가",
        )
        self._record_funnel_pipeline_step(
            FUNNEL_STAGES[4],
            survived=ema_uptrend_pass_tickers, excluded=ema_excluded,
            step_conditions=f"{long_ma_period}일 EMA 우상향 + 전일 종가 > EMA",
        )
        self._record_funnel_pipeline_step(
            FUNNEL_STAGES[5],
            survived=volume_pass_tickers, excluded=volume_excluded,
            step_conditions=f"당일 거래대금 ≥ {volume_period}일 평균 × {volume_mult:.1f}",
        )
        self._record_funnel_pipeline_step(
            FUNNEL_STAGES[6],
            survived=atr_pass_tickers, excluded=atr_excluded,
            step_conditions="ATR(14) > 0 (변동성 측정 가능)",
        )
        self._record_funnel_pipeline_step(
            FUNNEL_STAGES[7],
            survived=final_prepared_tickers,
            step_conditions="모든 단계 통과 — 멀티데이 보유 매수 후보",
        )

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
        """stock_master DB 기반으로 시총·거래대금 조건 종목을 스캔한다 (사이클 119).

        사이클 119 (Plan Phase B Step 1) — 사전 적재된 stock_master (~2,800종목,
        사이클 101/106 _full_universe_load_task_loop) 를 DB 필터링으로 대체한다.
        KIS API 직접 호출 0건 (기존 fetch_stock_detail 350 호출/일 → 0 호출/일,
        사이클 17 OPSP0002 backoff + KIS LMS chain 안전 영역 강화).

        사이클 108 답습 패턴 (VB/LTV/BFB stock_master 베이스 전환) 100% 영구 영속.
        hts_avls (시가총액, 백만원 단위) + acml_tr_pbmn (거래대금) 은 사이클 107
        inquire_stock_basics 5-key merge + 사이클 118 ACC_TRDVAL 매핑 시정으로
        stock_master.raw 에 자동 적재된다.

        donchian 특수성 (사이클 119 자문):
          - 멀티데이 보유 (5~15 영업일) → 사이클 32 R4 universe guard 영속
            (보유/익일청산 절대 보호) = scanner 영역 시정 영향 0
          - Q2=D 임시 완화 임계 (500억 / 10억) — 사이클 121+ 점진 복원 권고
          - nxt_tradable=None — donchian MAIN 단독 (사이클 26 영속)
        """
        from src.db import stock_master as _sm_mod
        from src.db.system_logs import write_log
        from src.engine.scanner import ETF_KEYWORDS, ticker_names

        p = self.config.params
        min_mcap = p.get("min_market_cap", 50_000_000_000)
        min_trade = p.get("min_trade_amount", 1_000_000_000)
        exclude_tickers = p.get("exclude_tickers") or []
        nxt_tradable_param = p.get("nxt_tradable", None)
        max_stocks = p.get("max_scan_stocks", 200)

        try:
            rows = await _sm_mod.list_by_filter(
                min_market_cap=min_mcap,
                min_trade_amount=min_trade,
                exclude_tickers=exclude_tickers,
                nxt_tradable=nxt_tradable_param,
                limit=max_stocks,
            )
        except Exception:
            logger.exception(
                "도치안 스윙 stock_master.list_by_filter 호출 실패 graceful — 빈 list 반환"
            )
            self._scan_stats["universe_candidates"] = 0
            self._scan_stats["universe_filtered"] = 0
            self._scan_stats["last_run_at"] = datetime.now(KST).isoformat()
            return []

        self._scan_stats["universe_candidates"] = len(rows)

        filtered: list[str] = []
        for row in rows:
            ticker = row.get("ticker", "")
            # 종목코드 형식 검증 — ETF·ETN·신주인수권 등 알파벳 포함 코드 차단 (사이클 89 영속)
            if not ticker or not (len(ticker) == 6 and ticker.isdigit()):
                continue
            name = row.get("name", "") or (row.get("raw") or {}).get("prdt_abrv_name", "")
            if any(kw in name for kw in ETF_KEYWORDS):
                continue
            if name:
                ticker_names[ticker] = name
            filtered.append(ticker)

        self._scan_stats["universe_filtered"] = len(filtered)
        self._scan_stats["last_run_at"] = datetime.now(KST).isoformat()
        logger.info(
            "도치안 스윙 유니버스 확정: %d/%d종목 (stock_master DB, 시총 %d억+, 거래대금 %d억+)",
            len(filtered), len(rows), min_mcap // 100_000_000, min_trade // 100_000_000,
        )

        if not filtered:
            msg = (
                f"도치안 스윙 유니버스 0종목 — stock_master {len(rows)}건 중 "
                f"시총 {min_mcap // 100_000_000}억+ / 거래대금 "
                f"{min_trade // 100_000_000}억+ / ETF 제외 후 통과 없음"
            )
            logger.error(msg)
            try:
                await write_log("ERROR", msg)
            except Exception:
                logger.exception("system_logs 기록 실패")

        # 사이클 151 — PriceFilter 후처리 (사이클 148 VB 영역 답습, Q2=C 단일 source 영속)
        filtered = await self._apply_price_filter_in_prepare(filtered)

        return filtered

    async def _apply_price_filter_in_prepare(self, tickers: list[str]) -> list[str]:
        """donchian_swing prepare 영역 가격 필터 후처리 (사이클 151, 사이클 148 VB 답습).

        사이클 64 scanner `_apply_price_filter` 패턴 답습 + PriceFilter 단일 source.
        보유 종목 절대 보호 (사이클 32 R4 답습) + raw.bfdy_clpr miss graceful 통과.

        - PriceFilter 비활성 (min=0, max=0) → 전체 통과 (회귀 보존)
        - 보유 종목 → 무조건 통과 (사이클 30 005935 매매 안전성 영속)
        - raw.bfdy_clpr miss → graceful 통과 (사이클 64 답습)
        - min_price > 0 + bfdy_clpr < min_price → 차단
        - max_price > 0 + bfdy_clpr > max_price → 차단
        """
        from src.db import stock_master as _sm_mod
        from src.db.system_config import get_price_filter

        pf = await get_price_filter()
        if not pf.is_active:
            return tickers

        # 보유 종목 절대 보호 (사이클 32 R4 + 사이클 64 답습)
        protected: set[str] = set()
        try:
            from src.engine import scanner as _scanner_mod
            protected = _scanner_mod._collect_protected_tickers_for_scanner()
        except Exception:
            logger.debug(
                "[dc_price_filter_prepare] protected_tickers 조회 실패 graceful",
                exc_info=True,
            )

        survivors: list[str] = []
        for ticker in tickers:
            if ticker in protected:
                survivors.append(ticker)
                continue
            prdy_clpr = 0
            try:
                basics = await _sm_mod.get(ticker)
                if basics and basics.raw:
                    raw_val = basics.raw.get("bfdy_clpr", 0)
                    if raw_val:
                        prdy_clpr = int(raw_val)
            except Exception:
                logger.debug(
                    "[dc_price_filter_prepare] stock_master 조회 실패 graceful: %s",
                    ticker, exc_info=True,
                )

            if prdy_clpr <= 0:
                # graceful 통과 (사이클 64 Q2 답습 — 신규 상장 영구 차단 방지)
                survivors.append(ticker)
                continue

            below_min = pf.min_price > 0 and prdy_clpr < pf.min_price
            above_max = pf.max_price > 0 and prdy_clpr > pf.max_price
            if not (below_min or above_max):
                survivors.append(ticker)

        return survivors

    async def recompute_held_atr(self) -> None:
        """보유 중 종목의 ATR을 재계산해 _candidates에 추가 (멀티데이 트레일링 유지용).

        prepare()는 _boot에서 positions 복구 전에 실행되므로,
        positions 복구 후 별도로 호출해 보유 종목 ATR을 채워둔다.

        E3 (2026-05-12): 같은 일봉 fetch 응답으로 `high_since_buy` 일봉 폴백 보정도
        동시 수행 — fetch 비용 절반. 시세 미수신 누적으로 chandelier 트레일링이
        매수가 부근에 동결되는 결함 차단.
        """
        from src.api.condition import fetch_daily_candles

        params = self.config.params
        fetch_days = max(params["long_ma_period"] + 5, params["donchian_period"] + 5)
        atr_period = params["atr_period"]
        today = datetime.now(KST).date()

        for ticker in list(self.state.positions.keys()):
            # high_since_buy 보정 사전 가드 (당일/미래는 fetch 호출도 생략)
            pos = self.state.positions.get(ticker)
            pos_needs_high_recover = bool(pos and pos.buy_date < today)
            if pos and pos.buy_date > today:
                logger.warning(
                    "도치안 스윙 high_since_buy 보정 skip — buy_date 비정상(미래): %s buy_date=%s today=%s",
                    ticker, pos.buy_date, today,
                )

            # ATR 재계산은 _candidates 미존재 시에만, high_since_buy 보정은 buy_date<today일 때
            need_atr = ticker not in self._candidates
            if not need_atr and not pos_needs_high_recover:
                continue

            try:
                candles = await fetch_daily_candles(ticker, days=fetch_days)
            except Exception:
                logger.exception("도치안 스윙 보유종목 일봉 fetch 실패: %s", ticker)
                continue

            # ATR 재계산
            if need_atr and len(candles) >= atr_period + 2:
                try:
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
                    logger.exception("도치안 스윙 보유종목 ATR 계산 실패: %s", ticker)

            # high_since_buy 일봉 폴백 보정 (E3)
            if pos_needs_high_recover and candles:
                await self._apply_high_since_buy_from_candles(pos, candles, today)

    async def recompute_high_since_buy(self) -> None:
        """보유 종목의 `high_since_buy` 를 매수일~전영업일 KIS 일봉 high max 로 보정.

        시세 미수신이 누적되어 `high_since_buy` 가 매수가 부근에 동결되는 결함을 회복.
        매수일 당일/미래일 포지션은 보정하지 않음 (당일은 buy_price 가 진실).

        sequential await — KIS Rate Limit 안전(`asyncio.gather` 등 병렬 금지).
        일봉 fetch 예외/빈 응답은 해당 종목만 skip, 다른 포지션은 계속.

        E3 (2026-05-12) — donchian_swing 전용. 다른 전략 확장은 별도 단계.
        """
        from src.api.condition import fetch_daily_candles

        params = self.config.params
        atr_long = params["long_ma_period"]
        atr_donchian = params["donchian_period"]
        today = datetime.now(KST).date()

        for ticker in list(self.state.positions.keys()):
            pos = self.state.positions.get(ticker)
            if not pos:
                continue
            if pos.buy_date >= today:
                if pos.buy_date > today:
                    logger.warning(
                        "도치안 스윙 high_since_buy 보정 skip — buy_date 비정상(미래): "
                        "%s buy_date=%s today=%s",
                        ticker, pos.buy_date, today,
                    )
                continue

            days_held = (today - pos.buy_date).days
            fetch_days = max(days_held + 5, atr_long + 5, atr_donchian + 5, 10)
            try:
                candles = await fetch_daily_candles(ticker, days=fetch_days)
            except Exception:
                logger.exception("도치안 스윙 high_since_buy 보정 일봉 fetch 실패: %s", ticker)
                continue
            if not candles:
                continue
            await self._apply_high_since_buy_from_candles(pos, candles, today)

    async def _apply_high_since_buy_from_candles(self, pos, candles: list[dict], today) -> None:
        """일봉 응답에서 매수일 < bsop_date < today 범위 high max 를 추출해 보정.

        보정값이 기존 high_since_buy 초과일 때만 갱신 + DB UPDATE + system_logs 1행.
        """
        from datetime import date as _date
        eligible_highs: list[int] = []
        for c in candles:
            bsop = c.get("stck_bsop_date") or ""
            if len(bsop) != 8 or not bsop.isdigit():
                continue
            try:
                bd = _date(int(bsop[:4]), int(bsop[4:6]), int(bsop[6:8]))
            except (ValueError, KeyError):
                continue
            # 경계 엄격: 매수일 당일/오늘 모두 제외
            if not (pos.buy_date < bd < today):
                continue
            try:
                hi = int(c.get("stck_hgpr", "0"))
            except (TypeError, ValueError):
                continue
            if hi > 0:
                eligible_highs.append(hi)

        if not eligible_highs:
            return
        candidate = max(eligible_highs)
        if candidate <= pos.high_since_buy:
            return

        prev = pos.high_since_buy
        pos.high_since_buy = candidate
        logger.info(
            "도치안 스윙 high_since_buy 보정: %s %d → %d "
            "(매수일 %s 이후 %d영업일 일별 high max)",
            pos.ticker, prev, candidate, pos.buy_date, len(eligible_highs),
        )
        # DB 영속화 + system_logs (fire-and-forget — 실패해도 메모리 보정은 유지)
        try:
            from src.db.positions import update_high
            await update_high(pos.ticker, candidate)
        except Exception:
            logger.exception("도치안 스윙 high_since_buy DB UPDATE 실패: %s", pos.ticker)
        try:
            from src.db.system_logs import write_log
            await write_log(
                "INFO",
                f"[high_since_buy_recover] ticker={pos.ticker} prev={prev} "
                f"new={candidate} days={len(eligible_highs)} buy_date={pos.buy_date}",
            )
        except Exception:
            pass

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

        # 사이클 23 P2-3 — 돌파폭 과열 상한 가드 (추격 금지)
        donchian_high = info["donchian_high"]
        if donchian_high > 0:
            max_ext = float(self.config.params.get("max_breakout_extension_pct", 3.0))
            from src.engine.scanner import ticker_prices as _ticker_prices
            price_info = _ticker_prices.get(ticker, {})
            daily_high = max(
                int(price_info.get("stck_hgpr", 0) or 0),
                int(price_info.get("high_price", 0) or 0),
                current_price,
                open_price,
            )
            if daily_high > donchian_high:
                ext_pct = (daily_high - donchian_high) / donchian_high * 100
                if ext_pct > max_ext:
                    logger.info(
                        "[donchian_extension_skip] ticker=%s daily_high=%d donchian_high=%d"
                        " ext_pct=%.2f > %.2f",
                        ticker, daily_high, donchian_high, ext_pct, max_ext,
                    )
                    return Signal.NONE

        self._bought_today.add(ticker)
        # 사이클 23 P2-2 — 매수 신호 발사 시 진입 돌파선 등록
        self._breakout_high[ticker] = info["donchian_high"]
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

        # 2.5) 사이클 23 P2-2 — 시간 기반 청산 (멀티데이 약한 이탈 빠른 정리)
        # 기존 ATR 트레일링/하드 손절 보존, 추가 분기만 삽입
        n_days = int(self.config.params.get("breakout_fail_n_days", 5))
        breakout_high = self._breakout_high.get(ticker, 0)
        if breakout_high > 0 and pos.buy_date:
            today = datetime.now(KST).date()
            days_held = (today - pos.buy_date).days
            if days_held >= n_days and current_price < breakout_high:
                logger.info(
                    "도치안 시간 기반 청산: %s 보유 %d일 ≥ %d, 현재가(%d) < 돌파선(%d)",
                    ticker, days_held, n_days, current_price, breakout_high,
                )
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
        """할당 자금의 position_ratio 비중. 비중 기준 0주여도 잔여 자금이 1주 살 수 있으면 1주."""
        if current_price <= 0:
            return 0
        ratio = self.config.params["position_ratio"]
        amount = int(self.state.total_investment * ratio)
        qty = amount // current_price
        if qty > 0:
            return qty
        return self._fallback_one_share(current_price)
