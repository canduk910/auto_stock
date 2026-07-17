"""고지로(小次郎) 대순환 스윙 전략 (EMA 5/20/40 대순환 스테이지 + ATR 손절/트레일링).

추세추종 계열. donchian_swing 의 직계 확장 — "질서정연한 추세"를 EMA 정렬 상태로 포착.

진입 (strict `evaluate_entry`, 조기진입 Phase1 OFF):
- 현재 스테이지 1 (단기>중기>장기)
- 최근 `stage1_freshness`(3)영업일 내 6→1 전환 (갓 진입한 신선한 스테이지 1)
- EMA 5/20/40 모두 우상향
- 전일 종가 > EMA5
- (유니버스 게이트) ATR/종가 밴드 1.0~4.5% (대순환/변동성 판별, 비협상)
- 다음 영업일 09:05~09:30 시장가 (갭업≥5% / 갭다운≤-4% / 장중 붕괴 스킵)

청산 (우선순위 고정):
1. 고정 % 하드손절 (`hard_stop_pct`, ATR 독립 backstop)
2. 2ATR 하드손절 (`buy_price - stop_atr*ATR`, tighten-only floor)
3. 스테이지3 진입 (추세 종료, 익일 아침 발화)
4. 2.5ATR 샹들리에 트레일링 (`high_since_buy - trail_atr*ATR`)
- 시간 손절 / 15:20 강제 청산 없음 (멀티데이, 추세 끝까지 보유).

Phase 1: 자금관리 = position_ratio (터틀 유닛 sizing/피라미딩/조기진입 = Phase 2).
"""

from __future__ import annotations

import logging
from datetime import datetime, time, timezone, timedelta

import pandas as pd

from src.engine.kojiro_indicators import KojiroIndicatorConfig, enrich
from src.engine.strategy_base import FunnelStage, Signal, StrategyBase, StrategyConfig

KST = timezone(timedelta(hours=9))

# 일봉 로드 상수 — 단일 진실원 (data-H mismatch 방지).
# days=100: DB get_recent_daily 100 하드클램프 + KIS 폴백 100 한도 ("≥120봉" 목표 폐기).
# min_required=80: EMA40 seed 잔여가중 <~2% 보장선.
KOJIRO_FETCH_DAYS = 100
KOJIRO_MIN_REQUIRED = 80

logger = logging.getLogger(__name__)


FUNNEL_STAGES: tuple[FunnelStage, ...] = (
    FunnelStage(1, "코스피200+코스닥150 합집합"),
    FunnelStage(2, "시총+거래대금 컷 통과"),
    FunnelStage(3, "1단계 진입 차단 통과 (거래정지/관리/단기과열/투자유의 등)"),
    FunnelStage(4, "일봉 fetch + 전일종가>0 + 워밍업봉 충족"),
    # ★ 대순환/변동성 판별 1차 필터 (도메인 (b) 비협상) — verdict 키워드 '변동성'/'ATR'/'밴드'
    FunnelStage(5, "ATR/종가 변동성 밴드 통과 (1.0~4.5%)"),
    FunnelStage(6, "스테이지 판별 가능 (EMA 동가 제외)"),
    FunnelStage(7, "스테이지1 + 3선 우상향"),
    FunnelStage(8, "6→1 전환 인접 + 종가>EMA5 (대순환 진입 확정)"),
    FunnelStage(9, "최종 후보"),
)


def _empty_scan_stats() -> dict:
    return {
        "universe_union": 0,
        "universe_candidates": 0,
        "universe_filtered": 0,
        "candle_fetch_ok": 0,
        "band_pass": 0,
        "stage_valid_pass": 0,
        "stage1_uptrend_pass": 0,
        "strict_entry_pass": 0,
        "final_prepared": 0,
        "last_run_at": None,
    }


def _stage_recently(stages: list, from_stage: int, to_stage: int, within: int = 3) -> bool:
    """최근 within봉 내 from→to 스테이지 인접 전환이 있었는지. (레퍼런스 strategy.py 포팅)"""
    st = [s for s in stages[-(within + 1):]]
    for a, b in zip(st, st[1:]):
        if a == from_stage and b == to_stage:
            return True
    return False


class KojiroStrategy(StrategyBase):
    """고지로 대순환 스윙 전략 (멀티데이 보유)."""

    # 멀티데이 스윙 — KRX 메인 단독 (donchian 동형, NXT 무관).
    DEFAULT_TRADABLE_BOARDS = ("main",)

    DEFAULT_PARAMS = {
        "tradable_boards": list(DEFAULT_TRADABLE_BOARDS),
        "exchange": "KRX",
        # ── 대순환 지표 (전략 정체성 상수 — PARAM_RANGES 제외, AI 튜닝 금지) ──
        "ema_short": 5,
        "ema_mid": 20,
        "ema_long": 40,
        "macd_signal": 9,
        "atr_period": 20,
        "slope_lookback": 1,
        "stage1_freshness": 3,       # 6→1 전환 인접 판정 봉수 (신선도)
        # ── ATR/종가 변동성 밴드 (비협상 필수, 정체성 상수) ──
        "atr_ratio_min": 0.01,       # 1.0%
        "atr_ratio_max": 0.045,      # 4.5%
        # ── 손절/트레일 배수 (kojiro 고유명 — atr_trail_mult 재사용 금지, PARAM_RANGES 제외) ──
        "stop_atr": 2.0,             # 2ATR 하드손절
        "trail_atr": 2.5,            # 2.5ATR 샹들리에 트레일링
        "hard_stop_pct": -8.0,       # 고정 % 하드손절 (ATR 독립 backstop)
        # ── 진입 게이트 (정체성 상수, PARAM_RANGES 제외) ──
        "gap_up_skip_pct": 5.0,      # 갭업 ≥5% 스킵
        "gap_down_skip_pct": -4.0,   # 갭다운 ≤-4% 스킵
        # ── 유니버스/사이징 (donchian 동형 — 자동튜닝 수용) ──
        "min_market_cap": 50_000_000_000,    # 500억
        "min_trade_amount": 1_000_000_000,   # 10억
        "max_scan_stocks": 200,
        "exclude_tickers": [],
        "nxt_tradable": None,
        "position_ratio": 0.20,
        "max_positions": 5,
        "daily_loss_limit": -8.0,
        # ── 터틀 유닛 sizing (Phase 2A-1, PARAM_RANGES 제외 = AI 자동튜닝 금지) ──
        # sizing_mode='turtle' opt-in 시 unit=floor(전략예산×risk_pct/ATR). 기본 position_ratio.
        # risk_pct 0.5% = 도메인 권장(KR 갭리스크). max_units 2/10 은 2B/2C 선등록(2A-1 미사용).
        "sizing_mode": "position_ratio",
        "risk_pct": 0.005,
        "max_units_per_stock": 2,
        "max_units_total": 10,
    }

    def __init__(self, config: StrategyConfig):
        merged = {**self.DEFAULT_PARAMS, **config.params}
        config.params = merged
        super().__init__(config)
        # ★ ATR/stage 단일 진실원 — prepare 재생성 + recompute_held_atr 가 held 재채움.
        #   {prev_close, atr(float, ewm20), stage, ema_s, ema_m, ema_l, atr_ratio}
        self._candidates: dict[str, dict] = {}
        # 보유종목 스테이지3 precompute 플래그 (prepare/recompute 에서만 세팅) — 익일 아침 발화.
        self._held_stage3: dict[str, bool] = {}
        # 2ATR 하드손절 tighten-only floor (변동성 팽창 loosen 차단, restart-H3).
        self._stop_floor: dict[str, int] = {}
        self._scanned_tickers: list[str] = []
        self._bought_today: set[str] = set()
        self._scan_stats: dict = _empty_scan_stats()
        self._scan_stage_counts: dict[str, list[str]] = {}
        self._ind_cfg = KojiroIndicatorConfig(
            ema_short=merged["ema_short"], ema_mid=merged["ema_mid"],
            ema_long=merged["ema_long"], macd_signal=merged["macd_signal"],
            atr_period=merged["atr_period"], slope_lookback=merged["slope_lookback"],
        )

    # ────────────────────────── prepare ──────────────────────────

    async def prepare(self) -> None:
        """장 시작 전: 유니버스 스캔 → 일봉 fetch → 대순환 스테이지/ATR 밴드/strict entry 검증."""
        import asyncio

        from src.db.stock_master_daily import get_recent_daily_normalized

        self._candidates = {}
        stats = _empty_scan_stats()
        self._scan_stats = stats
        self._reset_funnel_steps(FUNNEL_STAGES)

        # stock_master 0건 race 자동 재시도 (donchian 사이클 163 답습)
        tickers = await self._scan_universe()
        for retry_attempt in range(3):
            if tickers:
                break
            logger.warning(
                "[kojiro_prepare_retry] stock_master 0건 — 30초 후 재시도 (cap=%d/3)",
                retry_attempt + 1,
            )
            await asyncio.sleep(30)
            self._candidates = {}
            stats = _empty_scan_stats()
            self._scan_stats = stats
            self._reset_funnel_steps(FUNNEL_STAGES)
            tickers = await self._scan_universe()

        params = self.config.params
        min_mcap_billion = params["min_market_cap"] / 100_000_000
        min_trade_billion = params["min_trade_amount"] / 100_000_000
        stage_counts = getattr(self, "_scan_stage_counts", None) or {}
        union_tickers = stage_counts.get("union_tickers", tickers)
        trade_tickers = stage_counts.get("trade_tickers", tickers)
        self._record_funnel_pipeline_step(
            FUNNEL_STAGES[0], survived=union_tickers,
            step_conditions="코스피200 + 코스닥150 합집합 (필터 전 원천 유니버스)",
        )
        self._record_funnel_pipeline_step(
            FUNNEL_STAGES[1], survived=trade_tickers,
            step_conditions=(
                f"시총 ≥ {min_mcap_billion:.0f}억 + 거래대금 ≥ {min_trade_billion:.0f}억 컷 통과"
            ),
        )

        tickers, master_block_excluded = await self._apply_master_block_filter_in_prepare(tickers)
        self._record_funnel_pipeline_step(
            FUNNEL_STAGES[2], survived=tickers,
            step_conditions="1단계 진입 차단 (거래정지/관리/단기과열/투자유의/공매도과열/이상급등 등)",
            excluded=master_block_excluded[:20],
        )

        if not tickers:
            logger.info("고지로 대순환 유니버스 0종목")
            self._scanned_tickers = []
            stats["last_run_at"] = datetime.now(KST).isoformat()
            return

        today_str = datetime.now(KST).strftime("%Y%m%d")

        async def _fetch_one(ticker: str):
            try:
                return ticker, await get_recent_daily_normalized(
                    ticker, days=KOJIRO_FETCH_DAYS, min_required=KOJIRO_MIN_REQUIRED,
                )
            except Exception as e:
                logger.warning("고지로 일봉 fetch 실패: %s — %s", ticker, e)
                return ticker, None

        fetched = await asyncio.gather(*[_fetch_one(t) for t in tickers])

        from src.engine.strategy_base import _resolve_ticker_name

        # 단계별 생존/탈락 캡처
        fetch_ok_t: list[str] = []
        band_t: list[str] = []
        stage_valid_t: list[str] = []
        stage1_up_t: list[str] = []
        strict_t: list[str] = []
        final_t: list[str] = []
        fetch_ex: list[dict] = []
        band_ex: list[dict] = []
        stage_valid_ex: list[dict] = []
        stage1_up_ex: list[dict] = []
        strict_ex: list[dict] = []

        prepared = 0
        held_marked = 0
        for ticker, candles in fetched:
            name = _resolve_ticker_name(ticker)
            if candles is None:
                fetch_ex.append({"ticker": ticker, "name": name, "reason": "일봉 응답 None"})
                continue
            try:
                # candles DESC (idx0=최신). 오늘 부분봉이면 드롭.
                prev_idx = 1 if candles[0].get("stck_bsop_date") == today_str else 0
                usable = candles[prev_idx:]
                if len(usable) < KOJIRO_MIN_REQUIRED:
                    fetch_ex.append({
                        "ticker": ticker, "name": name,
                        "reason": f"워밍업봉 부족 {len(usable)} < {KOJIRO_MIN_REQUIRED}",
                    })
                    continue
                # ASC 역순 (oldest→newest) → DataFrame → enrich → last(iloc[-1]) = D-1 완성봉
                asc = list(reversed(usable))
                df = self._build_ohlc_df(asc)
                enriched = enrich(df, self._ind_cfg)
                last = enriched.iloc[-1]
                stages_series = enriched["stage"].tolist()

                prev_close = int(last["close"])
                if prev_close <= 0:
                    continue
                stats["candle_fetch_ok"] += 1
                fetch_ok_t.append(ticker)

                atr_val = float(last["atr"])
                # ★ step5: ATR/종가 변동성 밴드 (대순환 판별 1차 필터)
                atr_ratio = atr_val / prev_close if prev_close > 0 else 0.0
                if not (params["atr_ratio_min"] <= atr_ratio <= params["atr_ratio_max"]):
                    band_ex.append({
                        "ticker": ticker, "name": name,
                        "reason": (
                            f"ATR/종가 {atr_ratio * 100:.2f}% ∉ "
                            f"[{params['atr_ratio_min'] * 100:.1f}%, {params['atr_ratio_max'] * 100:.1f}%]"
                        ),
                    })
                    continue
                stats["band_pass"] += 1
                band_t.append(ticker)

                # step6: 스테이지 판별 가능 (EMA 동가 → None 제외)
                stage = last["stage"]
                if stage is None or (isinstance(stage, float) and pd.isna(stage)):
                    stage_valid_ex.append({
                        "ticker": ticker, "name": name, "reason": "EMA 동가 → 스테이지 None",
                    })
                    continue
                stage = int(stage)
                stats["stage_valid_pass"] += 1
                stage_valid_t.append(ticker)

                ema_s = float(last["ema_s"])
                ema_m = float(last["ema_m"])
                ema_l = float(last["ema_l"])
                all_up = bool(last["ema_s_up"] and last["ema_m_up"] and last["ema_l_up"])

                # 보유 종목이면 stage3 precompute 플래그 세팅 (진입 게이트와 무관하게 청산용)
                if self.state.has_position(ticker):
                    self._candidates[ticker] = {
                        "prev_close": prev_close, "atr": atr_val, "stage": stage,
                        "ema_s": ema_s, "ema_m": ema_m, "ema_l": ema_l, "atr_ratio": atr_ratio,
                    }
                    self._held_stage3[ticker] = (stage == 3)
                    held_marked += 1

                # step7: 스테이지1 + 3선 우상향
                if not (stage == 1 and all_up):
                    stage1_up_ex.append({
                        "ticker": ticker, "name": name,
                        "reason": f"스테이지 {stage} / 3선우상향 {all_up}",
                    })
                    continue
                stats["stage1_uptrend_pass"] += 1
                stage1_up_t.append(ticker)

                # step8: 6→1 전환 인접 + 종가 > EMA5
                fresh_61 = _stage_recently(stages_series, 6, 1, within=int(params["stage1_freshness"]))
                if not (fresh_61 and prev_close > ema_s):
                    strict_ex.append({
                        "ticker": ticker, "name": name,
                        "reason": (
                            f"6→1 인접 {fresh_61} / 종가>EMA5 {prev_close > ema_s} "
                            f"(종가 {prev_close:,} EMA5 {int(ema_s):,})"
                        ),
                    })
                    continue
                stats["strict_entry_pass"] += 1
                strict_t.append(ticker)

                from src.engine.scanner import ticker_prev_close
                ticker_prev_close[ticker] = prev_close

                self._candidates[ticker] = {
                    "prev_close": prev_close, "atr": atr_val, "stage": stage,
                    "ema_s": ema_s, "ema_m": ema_m, "ema_l": ema_l, "atr_ratio": atr_ratio,
                }
                prepared += 1
                final_t.append(ticker)
            except Exception as e:
                logger.warning("고지로 prepare 실패: %s — %s", ticker, e)
                continue

        self._record_funnel_pipeline_step(
            FUNNEL_STAGES[3], survived=fetch_ok_t, excluded=fetch_ex,
            step_conditions=f"일봉 ≥ {KOJIRO_MIN_REQUIRED}봉 + 전일 종가 > 0",
        )
        self._record_funnel_pipeline_step(
            FUNNEL_STAGES[4], survived=band_t, excluded=band_ex,
            step_conditions=(
                f"ATR/종가 ∈ [{params['atr_ratio_min'] * 100:.1f}%, "
                f"{params['atr_ratio_max'] * 100:.1f}%]"
            ),
        )
        self._record_funnel_pipeline_step(
            FUNNEL_STAGES[5], survived=stage_valid_t, excluded=stage_valid_ex,
            step_conditions="EMA 5/20/40 동가 아님 (스테이지 판별 가능)",
        )
        self._record_funnel_pipeline_step(
            FUNNEL_STAGES[6], survived=stage1_up_t, excluded=stage1_up_ex,
            step_conditions="스테이지 1 + EMA 5/20/40 모두 우상향",
        )
        self._record_funnel_pipeline_step(
            FUNNEL_STAGES[7], survived=strict_t, excluded=strict_ex,
            step_conditions=f"최근 {params['stage1_freshness']}봉 내 6→1 전환 + 전일 종가 > EMA5",
        )
        self._record_funnel_pipeline_step(
            FUNNEL_STAGES[8], survived=final_t,
            step_conditions="모든 단계 통과 — 멀티데이 대순환 매수 후보",
        )

        self._scanned_tickers = list(self._candidates.keys())
        self._bought_today.clear()
        stats["final_prepared"] = prepared
        stats["last_run_at"] = datetime.now(KST).isoformat()
        logger.info(
            "고지로 대순환 준비 완료: %d/%d종목 (strict entry) — "
            "fetch_ok=%d band=%d stage_valid=%d stage1_up=%d strict=%d held_marked=%d",
            prepared, len(tickers), stats["candle_fetch_ok"], stats["band_pass"],
            stats["stage_valid_pass"], stats["stage1_uptrend_pass"],
            stats["strict_entry_pass"], held_marked,
        )

    @staticmethod
    def _build_ohlc_df(asc_candles: list[dict]) -> pd.DataFrame:
        """ASC(oldest→newest) KIS 일봉 dict 리스트 → enrich 입력 DataFrame."""
        opens, highs, lows, closes, vols = [], [], [], [], []
        for c in asc_candles:
            close = int(c.get("stck_clpr", "0"))
            opens.append(int(c.get("stck_oprc", c.get("stck_clpr", "0")) or close))
            highs.append(int(c.get("stck_hgpr", "0")))
            lows.append(int(c.get("stck_lwpr", "0")))
            closes.append(close)
            vols.append(int(c.get("acml_vol", "0")))
        return pd.DataFrame({
            "open": opens, "high": highs, "low": lows, "close": closes, "volume": vols,
        })

    # ────────────────────────── 유니버스/필터 (donchian 복사) ──────────────────────────

    async def _scan_universe(self) -> list[str]:
        """KOSPI200∪KOSDAQ150 지수고정 유니버스 (donchian 동형, list_by_filter 단일 조회)."""
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
            rows, stage = await _sm_mod.list_by_filter(
                min_market_cap=min_mcap, min_trade_amount=min_trade,
                exclude_tickers=exclude_tickers, nxt_tradable=nxt_tradable_param,
                is_kospi200=True, is_kosdaq150=True,
                limit=max_stocks, return_stage_counts=True,
            )
            self._scan_stage_counts = stage
        except Exception:
            logger.exception("고지로 stock_master.list_by_filter 실패 graceful — 빈 list")
            self._scan_stats["universe_union"] = 0
            self._scan_stats["universe_candidates"] = 0
            self._scan_stats["universe_filtered"] = 0
            self._scan_stats["last_run_at"] = datetime.now(KST).isoformat()
            self._scan_stage_counts = {}
            return []

        self._scan_stats["universe_union"] = len(stage.get("union_tickers", rows))
        self._scan_stats["universe_candidates"] = len(rows)

        filtered: list[str] = []
        for row in rows:
            ticker = row.get("ticker", "")
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

        if not filtered:
            msg = (
                f"고지로 유니버스 0종목 — stock_master {len(rows)}건 중 시총 "
                f"{min_mcap // 100_000_000}억+ / 거래대금 {min_trade // 100_000_000}억+ / ETF 제외 후 없음"
            )
            logger.error(msg)
            try:
                await write_log("ERROR", msg)
            except Exception:
                logger.exception("system_logs 기록 실패")

        filtered = await self._apply_price_filter_in_prepare(filtered)
        return filtered

    async def _apply_master_block_filter_in_prepare(
        self, tickers: list[str]
    ) -> tuple[list[str], list[dict]]:
        """1단계 진입 차단 hook (donchian 동형, scanner.apply_master_block_filter 위임)."""
        from src.engine import scanner as _scanner_mod

        protected: set[str] = set()
        try:
            protected = _scanner_mod._collect_protected_tickers_for_scanner()
        except Exception:
            logger.debug("[kojiro_master_block_prepare] protected 조회 실패 graceful", exc_info=True)
        return await _scanner_mod.apply_master_block_filter(tickers, protected_tickers=protected)

    async def _apply_price_filter_in_prepare(self, tickers: list[str]) -> list[str]:
        """가격 필터 후처리 (donchian 동형, PriceFilter 단일 source + 보유 절대 보호)."""
        from src.db import stock_master as _sm_mod
        from src.db.system_config import get_price_filter

        pf = await get_price_filter()
        if not pf.is_active:
            return tickers

        protected: set[str] = set()
        try:
            from src.engine import scanner as _scanner_mod
            protected = _scanner_mod._collect_protected_tickers_for_scanner()
        except Exception:
            logger.debug("[kojiro_price_filter_prepare] protected 조회 실패 graceful", exc_info=True)

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
                logger.debug("[kojiro_price_filter_prepare] stock_master 조회 실패: %s", ticker, exc_info=True)

            if prdy_clpr <= 0:
                survivors.append(ticker)
                continue
            below_min = pf.min_price > 0 and prdy_clpr < pf.min_price
            above_max = pf.max_price > 0 and prdy_clpr > pf.max_price
            if not (below_min or above_max):
                survivors.append(ticker)
        return survivors

    # ────────────────────────── 재계산 (보유종목, boot/저녁 훅) ──────────────────────────

    async def recompute_held_atr(self) -> None:
        """보유 종목의 ATR/stage/stage3 를 최신 일봉으로 재계산 (_candidates 재채움).

        prepare 는 _boot positions 복구 *전* 실행 → 복구 후 별도 호출로 held 채움.
        ATR = enrich Wilder ewm20 (get_atr 재사용 금지, 진입 ATR 정의 일관).
        실패/stale/lock → fail-open (_held_stage3=False, 고정%+2ATR 손절 유지) + WARNING.
        """
        from src.db.stock_master_daily import get_recent_daily_normalized

        today = datetime.now(KST).date()
        today_str = today.strftime("%Y%m%d")

        for ticker in list(self.state.positions.keys()):
            pos = self.state.positions.get(ticker)
            try:
                candles = await get_recent_daily_normalized(
                    ticker, days=KOJIRO_FETCH_DAYS, min_required=KOJIRO_MIN_REQUIRED,
                )
            except Exception:
                logger.warning("[kojiro_recompute] 일봉 fetch 실패 fail-open: %s", ticker, exc_info=True)
                self._held_stage3[ticker] = False
                continue
            if not candles:
                logger.warning("[kojiro_recompute] 일봉 응답 없음 fail-open: %s", ticker)
                self._held_stage3[ticker] = False
                continue
            try:
                prev_idx = 1 if candles[0].get("stck_bsop_date") == today_str else 0
                usable = candles[prev_idx:]
                if len(usable) < KOJIRO_MIN_REQUIRED:
                    self._held_stage3[ticker] = False
                    continue
                asc = list(reversed(usable))
                enriched = enrich(self._build_ohlc_df(asc), self._ind_cfg)
                last = enriched.iloc[-1]
                atr_val = float(last["atr"])
                stage = last["stage"]
                stage_int = None if (stage is None or (isinstance(stage, float) and pd.isna(stage))) else int(stage)
                prev_close = int(last["close"])
                if atr_val > 0 and prev_close > 0:
                    self._candidates[ticker] = {
                        "prev_close": prev_close, "atr": atr_val,
                        "stage": stage_int if stage_int is not None else 0,
                        "ema_s": float(last["ema_s"]), "ema_m": float(last["ema_m"]),
                        "ema_l": float(last["ema_l"]),
                        "atr_ratio": atr_val / prev_close,
                    }
                    # tighten-only floor 갱신
                    base = int(pos.buy_price - self.config.params["stop_atr"] * atr_val) if pos else 0
                    if base > 0:
                        self._stop_floor[ticker] = max(self._stop_floor.get(ticker, base), base)
                # stage3 플래그 (None → fail-open False)
                self._held_stage3[ticker] = (stage_int == 3)
                logger.info(
                    "[kojiro_recompute] %s ATR=%.1f stage=%s stage3=%s",
                    ticker, atr_val, stage_int, self._held_stage3[ticker],
                )
            except Exception:
                logger.warning("[kojiro_recompute] 계산 실패 fail-open: %s", ticker, exc_info=True)
                self._held_stage3[ticker] = False

    # ────────────────────────── 진입 ──────────────────────────

    def check_buy_signal(self, ticker: str, current_price: int, open_price: int) -> Signal:
        """09:05~09:30 창 시장가 진입 (strict entry 후보, 갭업/갭다운/붕괴 스킵, 1회만).

        _candidates 멤버십 = prepare 에서 strict entry 4조건(스테이지1+6→1인접+3선우상향+종가>EMA5)
        + ATR밴드 확정. 여기선 시간창 + 갭 게이트만.
        """
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
        # 보유 재채움 stage 데이터(stage != 1)는 매수 후보 아님 — strict entry 통과분만 매수.
        if not info or info.get("stage") != 1:
            return Signal.NONE

        # 시간 가드: 09:05 ~ 09:30 (KST-aware 명시, naive 금지)
        now_t = datetime.now(KST).time()
        if now_t < time(9, 5) or now_t > time(9, 30):
            return Signal.NONE

        prev_close = info["prev_close"]
        # 갭업/갭다운 스킵 (당일 영구 스킵)
        if open_price > 0 and prev_close > 0:
            gap_rate = (open_price - prev_close) / prev_close * 100
            gap_up = self.config.params["gap_up_skip_pct"]
            gap_down = self.config.params["gap_down_skip_pct"]
            if gap_rate >= gap_up:
                logger.info("고지로 갭업 스킵: %s 갭률 %.1f%% ≥ %.1f%%", ticker, gap_rate, gap_up)
                self._bought_today.add(ticker)
                return Signal.NONE
            if gap_rate <= gap_down:
                logger.info("고지로 갭다운 스킵: %s 갭률 %.1f%% ≤ %.1f%%", ticker, gap_rate, gap_down)
                self._bought_today.add(ticker)
                return Signal.NONE

        # 장중 비붕괴 확인 (지금 무너지고 있지 않음) — transient NONE (창 내 재시도)
        if open_price > 0 and current_price < open_price:
            return Signal.NONE

        self._bought_today.add(ticker)
        logger.info(
            "고지로 매수 신호: %s 현재가(%d) — 스테이지1(6→1) + EMA정배열 + ATR(%.1f)",
            ticker, current_price, info["atr"],
        )
        self.state.buy_signals.append({
            "ticker": ticker, "name": "", "price": current_price,
            "stage": info["stage"], "atr": int(info["atr"]), "change_rate": 0,
            "time": datetime.now(KST).strftime("%H:%M:%S"),
        })
        if len(self.state.buy_signals) > 20:
            self.state.buy_signals.pop(0)
        return Signal.BUY

    # ────────────────────────── 청산 (dict read only, hot-path) ──────────────────────────

    def check_exit_signal(self, ticker: str, current_price: int, open_price: int) -> Signal:
        """우선순위 고정: 고정%backstop → 2ATR → 스테이지3 → 2.5ATR 트레일. 일봉fetch/enrich 0건."""
        pos = self.state.positions.get(ticker)
        if not pos:
            return Signal.NONE

        params = self.config.params

        # 1) 고정 % 하드손절 (ATR 독립 backstop — restart/ATR=0 무손절 차단)
        if pos.buy_price > 0:
            loss_rate = (current_price - pos.buy_price) / pos.buy_price * 100
            if loss_rate <= params["hard_stop_pct"]:
                logger.info("[kojiro_hard_stop] %s 매수가(%d) 대비 %.1f%% ≤ %.1f%%",
                            ticker, pos.buy_price, loss_rate, params["hard_stop_pct"])
                return Signal.STOP_LOSS

        info = self._candidates.get(ticker)
        atr = float(info["atr"]) if info else 0.0

        # 2) 2ATR 하드손절 (tighten-only floor — 변동성 팽창 loosen 차단)
        if atr > 0 and pos.buy_price > 0:
            base = int(pos.buy_price - params["stop_atr"] * atr)
            floor = self._stop_floor.get(ticker)
            eff = base if floor is None else max(base, floor)
            self._stop_floor[ticker] = eff
            if eff > 0 and current_price <= eff:
                logger.info("[kojiro_atr_stop] %s 손절선(%d) = 매수가(%d) - %.1f×ATR(%.1f)",
                            ticker, eff, pos.buy_price, params["stop_atr"], atr)
                return Signal.STOP_LOSS

        # 3) 스테이지3 진입 (추세 종료, 익일 아침 발화 — precompute 플래그)
        if self._held_stage3.get(ticker):
            logger.info("[kojiro_stage3_exit] %s 스테이지3 진입 (추세 종료)", ticker)
            return Signal.TRAILING_STOP

        # 4) 2.5ATR 샹들리에 트레일링
        if atr > 0 and pos.high_since_buy > 0:
            chandelier = pos.high_since_buy - atr * params["trail_atr"]
            if current_price <= chandelier:
                logger.info("[kojiro_trailing] %s 고점(%d) - %.1f×ATR(%.1f) = %d / 현재가 %d",
                            ticker, pos.high_since_buy, params["trail_atr"], atr,
                            int(chandelier), current_price)
                return Signal.TRAILING_STOP

        return Signal.NONE

    def check_force_clear(self) -> list[str]:
        """15:20 강제 청산 대상 — 멀티데이 스윙은 강제 청산 없음."""
        return []

    def on_position_closed(self, ticker: str) -> None:
        """전량 청산 시 per-ticker 보유결합 상태 정리 (재진입 stale 차단)."""
        self._held_stage3.pop(ticker, None)
        self._stop_floor.pop(ticker, None)

    def calc_buy_quantity(self, current_price: int, ticker: str | None = None) -> int:
        """터틀 유닛(sizing_mode='turtle') 또는 position_ratio(기본). 어떤 실패든 fail-open."""
        if current_price <= 0:
            return 0
        params = self.config.params
        # ── 터틀 유닛 sizing (opt-in) — 실패 시 아래 position_ratio 로 fail-open ──
        if params.get("sizing_mode") == "turtle" and ticker is not None:
            try:
                from src.engine.turtle_sizing import compute_unit_qty
                atr = float(getattr(self, "_candidates", {}).get(ticker, {}).get("atr") or 0)
                unit_qty = compute_unit_qty(
                    int(self.state.total_investment), atr, float(params.get("risk_pct") or 0),
                )
                if unit_qty > 0:
                    # 전략예산 잔여 클램프 (사이클 8 soft_multiplier 이후 max_buy_qty 이중 안전망)
                    remaining = max(0, self.state.total_investment - self._calc_used_funds())
                    budget_qty = remaining // current_price
                    qty = min(unit_qty, budget_qty) if budget_qty > 0 else unit_qty
                    if qty > 0:
                        return qty
            except Exception:
                logger.debug("[kojiro_turtle_sizing_fallback] %s — position_ratio 낙하", ticker, exc_info=True)
            # atr/budget 0 또는 예외 → position_ratio 낙하 (fail-open)
        # ── position_ratio (기본, 바이트 동일 회귀 경로) ──
        ratio = params["position_ratio"]
        amount = int(self.state.total_investment * ratio)
        qty = amount // current_price
        if qty > 0:
            return qty
        return self._fallback_one_share(current_price)

    # ────────────────────────── 대시보드/구독 ──────────────────────────

    def get_scanned_tickers(self) -> list[str]:
        return self._scanned_tickers

    def get_scan_stats(self) -> dict:
        return dict(self._scan_stats)

    def get_targets_status(self) -> dict[str, dict]:
        return {
            ticker: {
                "prev_close": info["prev_close"], "atr": int(info["atr"]),
                "stage": info.get("stage", 0),
                "ema_s": int(info.get("ema_s", 0)), "ema_m": int(info.get("ema_m", 0)),
                "ema_l": int(info.get("ema_l", 0)),
                "target_price": info["prev_close"], "open_price": 0,
                "target_offset": 0, "open_confirmed": True, "k": 0.0,
            }
            for ticker, info in self._candidates.items()
        }
