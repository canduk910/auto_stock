"""변동성 돌파 전략 (래리 윌리엄스).

- 대상: 코스피+코스닥 전체에서 시총/거래대금 조건 필터
- prepare(): 조건 충족 종목의 21일 일봉으로 K값(노이즈 비율 기반) 계산 → Target Price 설정
- 매수: 당일 현재가 >= Target Price (시가 + 전일 Range * K)
- 손절: 매수가 대비 -3%
- 강제 청산: 15:20 전량 청산
- 비중: 할당 자금의 10%
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timedelta, timezone

from src.api.condition import add_business_days
from src.engine.strategy_base import FunnelStage, Signal, StrategyBase, StrategyConfig

KST = timezone(timedelta(hours=9))

logger = logging.getLogger(__name__)


# 사이클 143 (2026-06-15) — VB 5단계 funnel hook (사이클 140 자문 영속)
# 사이클 157 (2026-06-17) — 1단계 진입 차단 13건 step 추가 영구 영속 → 6단계.
# 사이클 C3 (2026-07-15) — 퀀트 재무 게이트(관찰) step 추가 → 7단계 (관찰 전용, 배제 0).
# 사이클 39+41 BFB/VCP/donchian 8단계 답습 = VB 단순 영역 = 7단계 적정 영역 영구 영속.
# 사이클 47 FUNNEL_STAGES 위임 패턴 답습 (`_record_funnel_pipeline_step(VB_FUNNEL_STAGES[i-1], ...)`).
VB_FUNNEL_STAGES: tuple[FunnelStage, ...] = (
    FunnelStage(1, "거래량순위 + stock_master 기반 후보"),
    FunnelStage(2, "시총 + 거래대금 필터 통과"),
    FunnelStage(3, "1단계 진입 차단 13건 통과 (거래정지/관리/단기과열/투자유의 등)"),
    FunnelStage(4, "일봉 fetch 통과"),
    FunnelStage(5, "전일 Range > 0 + noise 계산 통과"),
    FunnelStage(6, "K값 계산 + target_offset > 0"),
    FunnelStage(7, "퀀트 재무 게이트(관찰) — F-Score/마법공식 스코어 기록, 배제 0"),
)


def _empty_scan_stats() -> dict:
    """사이클 21 — VB 단계별 깔때기 카운트 dict (9 키).

    donchian_swing._empty_scan_stats 와 일관된 패턴. 운영자가 ScanMonitor 의
    `유니버스 → 가격 필수 → 시총 → 거래대금 → 일봉 fetch → K값` 단계별 통과 수를
    추적해 "왜 신호 0건인지" 즉시 진단.
    """
    return {
        "universe_candidates": 0,    # blng 0/1/3 합집합 dedupe
        "universe_filtered": 0,      # 시총+거래대금 동시 통과 (== filtered)
        "price_filtered": 0,         # 가격/listed/prdy_vol/prdy_close 모두 > 0
        "mcap_pass": 0,              # 시총 ≥ min_market_cap 단독
        "trade_amount_pass": 0,      # 거래대금 ≥ min_trade_amount 단독
        "candle_fetch_ok": 0,        # 일봉 fetch 응답 정상
        "k_value_computed": 0,       # noise + prev_range > 0 + target_offset > 0 → _targets 등록
        "final_prepared": 0,         # _scanned_tickers 길이
        "last_run_at": None,
    }


class VolatilityBreakoutStrategy(StrategyBase):
    """변동성 돌파 전략."""

    # 매매 가능 보드 — MAIN(09:00~15:20) 만 활성 (사이클 26, 2026-05-20: KRX ONLY).
    # 결정 (2026-05-20, 사이클 26): VB 신규매수 KRX ONLY 정책.
    # - PRE_NXT(08:00~09:00) 매수 제거: NXT 프리 OVERNIGHT 위험 차단 + SK하이닉스 시가 결함 해소.
    # - POST_NXT(15:30~20:00) 매수 제거 유지: VB 당일 15:20 일괄매도 정책 보존.
    # 매도(손절/트레일링/익일청산)는 보드 가드 무관 — risk.on_tick check_exit_signal 직접 평가.
    DEFAULT_TRADABLE_BOARDS = ("main",)

    DEFAULT_PARAMS = {
        "tradable_boards": list(DEFAULT_TRADABLE_BOARDS),
        "stop_loss_rate": -3.0,
        "position_ratio": 0.10,
        "max_positions": 10,
        "daily_loss_limit": -5.0,
        "k_period": 20,
        # 보드별 K값 곱 (Phase 5 Q1=C: 보드별 분리). 기본 동일값으로 시작 후 운영 데이터로 튜닝
        "k_value_krx_main": 1.0,
        "k_value_nxt_pre": 1.0,
        "k_value_nxt_post": 1.0,
        # 거래소 라우팅 (Phase 4): KRX / NXT / SOR. 미설정 시 KRX
        "exchange": "KRX",
        # 종목 스캔 조건 (Settings에서 변경 가능)
        "min_market_cap": 100_000_000_000,   # 시총 1,000억 이상
        "min_trade_amount": 20_000_000_000,  # 거래대금 200억 이상
        "max_scan_stocks": 100,              # 최대 스캔 종목 수
        # 재진입 쿨다운 (사이클 201, BFB 3 / VCP 7 과 구분 — VB 당일청산 특성상 2영업일)
        "reentry_cooldown_days": 2,
        # 사이클 C3 — 퀀트 재무필터 관찰 훅 (Phase 1, 기본 OFF = 배제 0, 스코어 계산/funnel 노출만).
        # PARAM_RANGES 미편입 (AI 자동튜닝 금지, 진입 정체성 상수 — 사이클 198/208/212 선례).
        "quant_filter_enabled": False,
        "quant_min_f_score": 0,
        "quant_max_mf_rank": 0,
    }

    def __init__(self, config: StrategyConfig):
        merged = {**self.DEFAULT_PARAMS, **config.params}
        config.params = merged
        super().__init__(config)
        # ticker -> {target_offset_base, k, prev_range, boards: {board: {open_price, target_price, target_offset}}}
        self._targets: dict[str, dict] = {}
        # ticker -> {board: bool} — 보드별 시가 확정 여부 (Phase 5 분리)
        self._open_confirmed: dict[str, dict[str, bool]] = {}
        # ticker -> 보드별 이전 틱 가격 (보드별 돌파 순간 감지용)
        self._prev_price: dict[str, dict[str, int]] = {}
        # 익일 청산 안전망 (2026-05-15, 결함 D 잔여) — `_execute_next_day_clear` 의
        # 30s 시가 안정화 중 on_tick 청산 race 차단용 플래그. momentum 패턴과 동일.
        # VB 정책은 당일 15:20 일괄 매도지만 그게 누락되면 본 플래그 + check_exit_signal
        # 익일 청산 분기로 다음 영업일 NXT 프리 청산 안전망 발동.
        self._next_day_clear_pending = False
        # 스캔된 종목 리스트 (subscribe용)
        self._scanned_tickers: list[str] = []
        # 사이클 170 카드 C — _scan_universe 가 보관한 원천 유니버스 후보 (필터 전).
        # funnel step1 noise 0 placeholder 제거 — 실제 후보 노출.
        self._universe_candidate_tickers: list[str] = []
        # 사이클 21 — 단계별 카운트 (ScanMonitor 깔때기)
        self._scan_stats: dict = _empty_scan_stats()
        # 사이클 201 — ticker -> 쿨다운 만료일(이날 이전엔 재진입 금지). multi-day 상태 —
        # _reset_daily_state/prepare 리셋 절대 금지 (G-VB-NO-DAILY-RESET, BFB 사이클 191 답습).
        self._cooldown_until: dict[str, date] = {}

    async def prepare(self) -> None:
        """장 시작 전: 시총/거래대금 조건 종목 스캔 → 21일 일봉으로 K값/Target 계산.

        사이클 143 (2026-06-15) — 사이클 140 자문 영속 VB 5단계 funnel hook 추가.
        사이클 39+41 BFB/VCP/donchian 패턴 답습. 매매 안전성 무영향 (사이클 38 명문화 영속).

        사이클 158 Q2 (2026-06-17) — stock_master 0건 race 자동 재시도 hook.
        운영 사례 = 2026-06-17 08:13~08:16 KST EC2 재시작 직후 _full_universe_load_task_loop
        적재 ~3분 소요 영역에서 _boot prepare 진입 → 0건 silent. cap 3회 + sleep 30초.
        """
        import asyncio

        # 사이클 173 (2026-06-22) — 일봉 source KIS → DB 어댑터 전환 (행위 보존).
        from src.db.stock_master_daily import get_recent_daily_normalized

        # 사이클 21 — 매 prepare 마다 카운트 초기화 (_scan_universe 가 직접 갱신)
        stats = _empty_scan_stats()
        self._scan_stats = stats
        # 사이클 143 — 단계별 ticker 캡처 reset (사이클 39 답습)
        self._reset_funnel_steps(VB_FUNNEL_STAGES)
        # 사이클 180 — 전일 stale 종목 누적 차단 (장수 싱글톤, prepare 가 유일 rebuild 지점). _limit_up_reached/_next_day_clear_pending 는 청산 모드 경로용이라 절대 미포함.
        self._targets.clear()
        self._open_confirmed.clear()
        self._prev_price.clear()

        # 사이클 158 Q2 — stock_master 0건 race 자동 재시도 hook (cap 3회 + sleep 30s).
        # 초기 1회 + 재시도 cap 3회 = 최대 4회 호출 영역.
        tickers = await self._scan_universe()
        for retry_attempt in range(3):
            if tickers:
                break
            logger.warning(
                "[vb_prepare_retry] stock_master 0건 — %d초 후 재시도 (cap=%d/3)",
                30, retry_attempt + 1,
            )
            await asyncio.sleep(30)
            # 사이클 21 카운트 재초기화 (재시도마다 _scan_universe 가 갱신)
            stats = _empty_scan_stats()
            self._scan_stats = stats
            self._reset_funnel_steps(VB_FUNNEL_STAGES)
            tickers = await self._scan_universe()
        # 사이클 143 — step 1+2 funnel hook (사이클 140 자문 영속)
        params = self.config.params
        min_mcap_billion = params.get("min_market_cap", 100_000_000_000) / 100_000_000
        min_trade_billion = params.get("min_trade_amount", 20_000_000_000) / 100_000_000
        # step 1: 원천 유니버스 후보 (필터 전) — 사이클 170 카드 C placeholder 제거
        self._record_funnel_pipeline_step(
            VB_FUNNEL_STAGES[0],
            survived=self._universe_candidate_tickers,
            step_conditions=(
                f"stock_master.list_by_filter 원천 유니버스 후보 "
                f"(limit={params.get('max_scan_stocks', 100)})"
            ),
        )
        # step 2: 시총 + 거래대금 필터 통과 (사이클 41 답습 — survived list[str] 자동 dict 변환)
        self._record_funnel_pipeline_step(
            VB_FUNNEL_STAGES[1],
            survived=tickers,
            step_conditions=(
                f"시총 ≥ {min_mcap_billion:.0f}억 + 거래대금 ≥ {min_trade_billion:.0f}억"
            ),
        )

        # 사이클 157 — step 3: 1단계 진입 차단 13건 (master_raw 7 + raw 6)
        tickers, master_block_excluded = await self._apply_master_block_filter_in_prepare(tickers)
        self._record_funnel_pipeline_step(
            VB_FUNNEL_STAGES[2],
            survived=tickers,
            step_conditions=(
                "1단계 진입 차단 13건 (거래정지/관리/단기과열/투자유의/공매도과열/이상급등 등)"
            ),
            excluded=master_block_excluded[:20],
        )

        k_period = self.config.params["k_period"]
        today_str = datetime.now(timezone(timedelta(hours=9))).date().strftime("%Y%m%d")
        prepared = 0

        # 일봉 fetch 병렬화 (KIS Rate Limit semaphore가 자동 직렬화)
        # 사이클 173 — DB 우선 어댑터 (락/신선도/부족 시 KIS 폴백). min_required 명시 (자문 §4).
        async def _fetch_one(ticker: str):
            try:
                return ticker, await get_recent_daily_normalized(
                    ticker, days=k_period + 2, min_required=22,
                )
            except Exception as e:
                logger.warning("변동성돌파 일봉 fetch 실패: %s — %s", ticker, e)
                return ticker, None

        fetched = await asyncio.gather(*[_fetch_one(t) for t in tickers])

        # 사이클 21 — 일봉 fetch 성공 카운트
        stats["candle_fetch_ok"] = sum(1 for _, c in fetched if c is not None)

        # 사이클 143 — 단계별 ticker 캡처 (사이클 39+41 답습)
        candle_fetch_ok_tickers: list[str] = []
        range_pass_tickers: list[str] = []
        final_prepared_tickers: list[str] = []
        candle_fetch_excluded: list[dict] = []
        range_excluded: list[dict] = []
        target_excluded: list[dict] = []

        for ticker, candles in fetched:
            if candles is None:
                candle_fetch_excluded.append({"ticker": ticker, "reason": "fetch 실패"})
                continue
            candle_fetch_ok_tickers.append(ticker)
            try:
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
                    range_excluded.append({"ticker": ticker, "reason": "noise 영역 0"})
                    continue

                k = sum(noise_list) / len(noise_list)

                # 전일 Range
                prev = candles[prev_idx]
                prev_high = int(prev.get("stck_hgpr", "0"))
                prev_low = int(prev.get("stck_lwpr", "0"))
                prev_range = prev_high - prev_low
                if prev_range <= 0:
                    range_excluded.append({"ticker": ticker, "reason": f"prev_range={prev_range} ≤ 0"})
                    logger.debug(
                        "변동성돌파 prev_range=0 skip: %s (date=%s)",
                        ticker, prev.get("stck_bsop_date"),
                    )
                    continue
                range_pass_tickers.append(ticker)

                target_offset = int(prev_range * k)
                if target_offset <= 0:
                    target_excluded.append({
                        "ticker": ticker,
                        "reason": f"target_offset={target_offset} ≤ 0 (k={k:.4f})",
                    })
                    logger.debug(
                        "변동성돌파 target_offset=0 skip: %s (k=%.4f, range=%d)",
                        ticker, k, prev_range,
                    )
                    continue
                final_prepared_tickers.append(ticker)

                self._targets[ticker] = {
                    "k": round(k, 4),
                    "prev_range": prev_range,
                    "target_offset_base": target_offset,  # k_value_* 곱 전 기본값
                    # backwards-compat (단일 보드 운영 시)
                    "target_offset": target_offset,
                    "target_price": 0,
                    "open_price": 0,
                    # 보드별 시가/타겟 (Phase 5 Q1=C 분리)
                    "boards": {},
                }
                # 보드별 confirmed 플래그
                self._open_confirmed[ticker] = {}

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
        # 사이클 21 — K값/최종 카운트 + last_run_at
        stats["k_value_computed"] = prepared
        stats["final_prepared"] = len(self._scanned_tickers)
        stats["last_run_at"] = datetime.now(KST).isoformat()

        # 사이클 143 + 157 — step 4+5+6 funnel hook (사이클 157 step 3 master block 후 인덱스 +1)
        self._record_funnel_pipeline_step(
            VB_FUNNEL_STAGES[3],
            survived=candle_fetch_ok_tickers,
            step_conditions=f"KIS fetch_daily_candles 정상 응답 ({k_period}일)",
            excluded=candle_fetch_excluded,
        )
        self._record_funnel_pipeline_step(
            VB_FUNNEL_STAGES[4],
            survived=range_pass_tickers,
            step_conditions="전일 Range > 0 + noise 영역 계산 통과",
            excluded=range_excluded,
        )
        self._record_funnel_pipeline_step(
            VB_FUNNEL_STAGES[5],
            survived=final_prepared_tickers,
            step_conditions="K값 노이즈 비율 + target_offset > 0",
            excluded=target_excluded,
        )

        # 사이클 C3 — step 7: 퀀트 재무 게이트 (관찰 전용, quant_filter_enabled=False 기본 → 배제 0).
        # master_block(step3) 다음 단계 삽입 원칙에 맞춰 prepare 파이프라인 최종 단계로 호출.
        await self._apply_quant_filter_in_prepare(final_prepared_tickers)

        logger.info("변동성돌파 전략 준비 완료: %d/%d종목 (K값 계산)", prepared, len(tickers))

    async def _scan_universe(self) -> list[str]:
        """stock_master DB 기반으로 시총·거래대금 조건 종목을 스캔한다 (사이클 108).

        사이클 108 (Plan Phase A) — 사전 적재된 stock_master (~2,800종목,
        사이클 101/106 _full_universe_load_task_loop) 를 DB 필터링으로 대체한다.
        KIS API 직접 호출 0건.
        hts_avls (시가총액, 백만원 단위) 는 사이클 108 inquire_stock_basics 5-key merge 에서
        stock_master.raw 에 적재됨.

        사이클 148 (2026-06-16) — PriceFilter 후처리 추가 (사이클 64 scanner 정합).
        사용자 결정 Q2=C: system_config price_filter_min/max 단일 source 키 재사용.
        사이클 32 R4 답습 — 보유 종목 절대 보호. 매매 안전성 무영향 (사이클 38 명문화).
        """
        from src.db import stock_master as _sm_mod
        from src.engine.scanner import ETF_KEYWORDS, ticker_names

        p = self.config.params
        min_mcap = p.get("min_market_cap", 100_000_000_000)
        min_trade = p.get("min_trade_amount", 20_000_000_000)
        max_stocks = p.get("max_scan_stocks", 100)

        # 사이클 156 Q0 — nxt_tradable 강제 필터 제거.
        # nxt_tradable 값은 주문 시점 NXT/KRX 분기용 (사이클 54 _strategy_exchange_async).
        # 유니버스 스캔 영역에서 강제 적용은 후보 풀 83% 영구 축소 silent 결함이었음.
        rows = await _sm_mod.list_by_filter(
            min_market_cap=min_mcap,
            min_trade_amount=min_trade,
            limit=max_stocks,
        )

        # 사이클 21 — 후보 수
        self._scan_stats["universe_candidates"] = len(rows)

        filtered: list[str] = []
        for row in rows:
            ticker = row.get("ticker", "")
            # 종목코드 형식 검증 — ETF·ETN·신주인수권 등 알파벳 포함 코드 차단
            if not ticker or not (len(ticker) == 6 and ticker.isdigit()):
                continue
            name = row.get("name", "") or (row.get("raw") or {}).get("prdt_abrv_name", "")
            if any(kw in name for kw in ETF_KEYWORDS):
                continue
            if name:
                ticker_names[ticker] = name
            filtered.append(ticker)

        # 사이클 148 — PriceFilter 후처리 (PriceFilter 단일 source, Q2=C 영속)
        filtered = await self._apply_price_filter_in_prepare(filtered)

        # 사이클 170 카드 C — 원천 유니버스 후보 보관 (funnel step1 노출)
        self._universe_candidate_tickers = list(filtered)

        logger.info(
            "변동성돌파 유니버스 확정: %d/%d종목 (stock_master DB, 시총 %d억+, 거래대금 %d억+)",
            len(filtered), len(rows), min_mcap // 100_000_000, min_trade // 100_000_000,
        )
        # 사이클 21 — 최종 universe 필터 통과 카운트
        self._scan_stats["universe_filtered"] = len(filtered)
        self._scan_stats["last_run_at"] = datetime.now(KST).isoformat()

        if not filtered:
            from src.db.system_logs import write_log

            msg = (
                f"변동성돌파 유니버스 0종목 — stock_master {len(rows)}건 중 "
                f"시총 {min_mcap // 100_000_000}억+ / 거래대금 "
                f"{min_trade // 100_000_000}억+ / ETF 제외 후 통과 없음"
            )
            logger.error(msg)
            try:
                await write_log("ERROR", msg)
            except Exception:
                logger.exception("system_logs 기록 실패")

        return filtered

    async def _apply_master_block_filter_in_prepare(
        self, tickers: list[str]
    ) -> tuple[list[str], list[dict]]:
        """VB prepare 영역 1단계 진입 차단 13건 hook (사이클 157 Q2).

        사이클 32 R4 보유/익일청산 절대 보호 + scanner.apply_master_block_filter 위임.

        Returns:
            (survived, excluded). excluded = [{ticker, name, reason}] (사이클 41 답습).
        """
        from src.engine import scanner as _scanner_mod

        protected: set[str] = set()
        try:
            protected = _scanner_mod._collect_protected_tickers_for_scanner()
        except Exception:
            logger.debug(
                "[vb_master_block_prepare] protected_tickers 조회 실패 graceful",
                exc_info=True,
            )
        return await _scanner_mod.apply_master_block_filter(
            tickers, protected_tickers=protected
        )

    async def _apply_price_filter_in_prepare(self, tickers: list[str]) -> list[str]:
        """VB prepare 영역 가격 필터 후처리 (사이클 148).

        사이클 64 scanner `_apply_price_filter` 패턴 답습 + PriceFilter 단일 source.
        보유 종목 절대 보호 (사이클 32 R4 답습) + raw.bfdy_clpr miss graceful 통과.

        - PriceFilter 비활성 (min=0, max=0) → 전체 통과 (회귀 보존)
        - 보유 종목 → 무조건 통과 (사이클 30 005935 매매 안전성 영속)
        - raw.bfdy_clpr miss → graceful 통과 (사이클 64 답습)
        - min_price > 0 + bfdy_clpr < min_price → 차단
        - max_price > 0 + bfdy_clpr > max_price → 차단 (운영 실증 6/16)
        """
        from src.db import stock_master as _sm_mod
        from src.db.system_config import get_price_filter

        pf = await get_price_filter()
        if not pf.is_active:
            return tickers

        # 보유 종목 절대 보호 (사이클 32 R4 + 사이클 64 Q1 옵션 D 답습)
        protected: set[str] = set()
        try:
            from src.engine import scanner as _scanner_mod
            protected = _scanner_mod._collect_protected_tickers_for_scanner()
        except Exception:
            logger.debug(
                "[vb_price_filter_prepare] protected_tickers 조회 실패 graceful",
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
                    "[vb_price_filter_prepare] stock_master 조회 실패 graceful: %s",
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

    async def _apply_quant_filter_in_prepare(self, tickers: list[str]) -> list[str]:
        """VB prepare 영역 퀀트 재무 게이트 (사이클 C3, 관찰 전용 Phase 1).

        `_apply_price_filter_in_prepare`(사이클 148) 미러. `quant_filter_enabled`
        (기본 False)일 때는 스코어 계산 + funnel step(step_no=7) 기록만 수행하고
        **어떤 종목도 배제하지 않는다** (관찰 모드, 입력==출력).

        보유 종목 절대 보호 (사이클 32 R4 답습) — 활성 모드에서도 무조건 통과.
        결측(재무 시계열 2기 부족/조회 예외) → fail-open 통과 (사이클 88 G-REJECT 답습).

        Phase 2(C4, 배제 활성)는 유의성 검정 통과 시에만 발주 — 본 메서드는
        `quant_filter_enabled=True` 여도 아직 배제 로직을 구현하지 않는다
        (관찰 스코어 기록만, Red 메모 명시).
        """
        from src.db import stock_master as _sm_mod
        from src.db import stock_master_financial as _smf_mod
        from src.engine import quant_score as _qs_mod

        # 보유 종목 절대 보호 (사이클 32 R4 답습)
        protected: set[str] = set()
        try:
            from src.engine import scanner as _scanner_mod
            protected = _scanner_mod._collect_protected_tickers_for_scanner()
        except Exception:
            logger.debug(
                "[vb_quant_filter_prepare] protected_tickers 조회 실패 graceful",
                exc_info=True,
            )

        f_scores: dict[str, int | None] = {}
        series_by_ticker: dict[str, dict] = {}
        mktcap_by_ticker: dict[str, float] = {}

        for ticker in tickers:
            if ticker in protected:
                continue
            try:
                series = await _smf_mod.get_financial_series(ticker, div_cls="0", limit=2)
            except Exception:
                logger.debug(
                    "[vb_quant_filter_prepare] get_financial_series 실패 graceful: %s",
                    ticker, exc_info=True,
                )
                series = []

            if len(series) < 2:
                f_scores[ticker] = None
                continue

            curr, prev = series[0], series[1]
            try:
                f_scores[ticker] = _qs_mod.compute_f_score_7(curr, prev)
            except Exception:
                logger.debug(
                    "[vb_quant_filter_prepare] compute_f_score_7 실패 graceful: %s",
                    ticker, exc_info=True,
                )
                f_scores[ticker] = None
            series_by_ticker[ticker] = curr

            try:
                basics = await _sm_mod.get(ticker)
                if basics and getattr(basics, "raw", None):
                    raw_val = basics.raw.get("hts_avls_eok") or basics.raw.get("hts_avls")
                    if raw_val:
                        mktcap_by_ticker[ticker] = float(raw_val)
            except Exception:
                logger.debug(
                    "[vb_quant_filter_prepare] stock_master.get 실패 graceful: %s",
                    ticker, exc_info=True,
                )

        mf_by_ticker: dict[str, dict] = {}
        if series_by_ticker:
            try:
                mf_by_ticker = _qs_mod.compute_magic_formula(series_by_ticker, mktcap_by_ticker)
            except Exception:
                logger.debug(
                    "[vb_quant_filter_prepare] compute_magic_formula 실패 graceful",
                    exc_info=True,
                )
                mf_by_ticker = {}

        # funnel step 7 기록 (관찰 — 스코어만 기록, 배제 0)
        survived_detail = [
            {
                "ticker": ticker,
                "f_score": f_scores.get(ticker),
                "mf_rank": (mf_by_ticker.get(ticker) or {}).get("mf_rank"),
            }
            for ticker in tickers
        ]
        self._record_funnel_pipeline_step(
            VB_FUNNEL_STAGES[6],
            survived=survived_detail,
            step_conditions=(
                f"관찰 전용(quant_filter_enabled={self.config.params.get('quant_filter_enabled', False)}) "
                "— F-Score/마법공식 스코어 기록, 배제 0"
            ),
        )

        # 관찰 모드(및 Phase 1 전체) — 배제 0, 입력 그대로 반환
        return list(tickers)

    def get_scanned_tickers(self) -> list[str]:
        """스캔된 종목 리스트를 반환한다 (WebSocket 구독용)."""
        return self._scanned_tickers

    def get_scan_stats(self) -> dict:
        """사이클 21 — 단계별 스캔 통계 (ScanMonitor 깔때기 시각화용).

        donchian_swing.get_scan_stats() 와 동일 시그니처.
        외부 수정 격리를 위해 사본 반환.
        """
        return dict(self._scan_stats)

    def get_targets_status(self) -> dict[str, dict]:
        """종목별 타겟 가격 정보를 반환한다 (활성 보드 필터링, 2026-05-13 작업 1).

        - 활성 보드(`session_tracker.active`) ∩ 전략 `tradable_boards` 에 속하는 보드만 노출
        - 교집합 공집합 → `boards={}` + top-level 0 + `open_confirmed={}`
        - 노출 보드 있음 → 우선순위(main → post_nxt → pre_nxt) 첫 보드 기준 top-level 값
        - session 모듈 import/접근 예외 → fallback: 기존 모든 보드 노출 (외부 호환 + 운영자 시야 보존)

        Phase 5 응답 스키마 보존 — `boards` 빈 dict 허용, 키 자체는 제거하지 않는다.
        """
        # 활성 보드 ∩ tradable_boards = 노출 보드 집합
        visible: set[str] | None
        try:
            from src.engine.session import session_tracker, parse_tradable_boards

            active = session_tracker.active  # frozenset[MarketBoard]
            tradable_raw = self.config.params.get("tradable_boards")
            tradable = parse_tradable_boards(tradable_raw) if tradable_raw else None
            if not tradable:
                # 기본 tradable_boards fallback (전략 클래스 상수)
                tradable = parse_tradable_boards(list(self.DEFAULT_TRADABLE_BOARDS))
            visible = {b.value for b in (active & tradable)}
        except Exception:
            # session 모듈 장애 시 모든 보드 노출 (운영자 시야 보존)
            visible = None

        # 우선순위: main → post_nxt → pre_nxt
        _BOARD_PRIORITY = ("main", "post_nxt", "pre_nxt")

        result = {}
        for ticker, info in self._targets.items():
            board_states = self._open_confirmed.get(ticker, {})
            all_boards = info.get("boards", {})

            if visible is None:
                # fallback — 기존 모든 보드 노출
                exposed_boards = {
                    board: {
                        "open_price": b.get("open_price", 0),
                        "target_price": b.get("target_price", 0),
                        "target_offset": b.get("target_offset", 0),
                        "confirmed": board_states.get(board, False),
                    }
                    for board, b in all_boards.items()
                }
                result[ticker] = {
                    "k": info.get("k", 0),
                    "target_price": info.get("target_price", 0),
                    "open_price": info.get("open_price", 0),
                    "target_offset": info.get("target_offset", 0),
                    "boards": exposed_boards,
                    "open_confirmed": board_states,
                }
                continue

            # 노출 보드만 추출 (visible 으로 필터)
            exposed_boards = {
                board: {
                    "open_price": b.get("open_price", 0),
                    "target_price": b.get("target_price", 0),
                    "target_offset": b.get("target_offset", 0),
                    "confirmed": board_states.get(board, False),
                }
                for board, b in all_boards.items()
                if board in visible
            }
            exposed_confirmed = {b: v for b, v in board_states.items() if b in visible}

            if not exposed_boards:
                # 교집합 공집합 — top-level 도 0 으로 가린다
                result[ticker] = {
                    "k": info.get("k", 0),
                    "target_price": 0,
                    "open_price": 0,
                    "target_offset": 0,
                    "boards": {},
                    "open_confirmed": {},
                }
                continue

            # top-level: 노출 보드 중 우선순위 첫 보드 — confirmed 우선
            top_board: str | None = None
            for cand in _BOARD_PRIORITY:
                if cand in exposed_boards and exposed_boards[cand]["confirmed"]:
                    top_board = cand
                    break
            if top_board is None:
                for cand in _BOARD_PRIORITY:
                    if cand in exposed_boards:
                        top_board = cand
                        break
            # exposed_boards 비어있지 않으므로 top_board 는 반드시 결정됨
            top = exposed_boards[top_board] if top_board else {}

            result[ticker] = {
                "k": info.get("k", 0),
                "target_price": top.get("target_price", 0),
                "open_price": top.get("open_price", 0),
                "target_offset": top.get("target_offset", 0),
                "boards": exposed_boards,
                "open_confirmed": exposed_confirmed,
            }
        return result

    _BOARD_K_KEY = {
        "main": "k_value_krx_main",
        "pre_nxt": "k_value_nxt_pre",
        "post_nxt": "k_value_nxt_post",
    }

    def _resolve_active_board(self) -> str | None:
        """현재 활성 보드 중 전략의 tradable_boards에 포함된 첫 보드를 반환.

        우선순위 main → post_nxt → pre_nxt — KRX 메인 활성 시 그것을 우선.
        """
        from src.engine.session import session_tracker, MarketBoard

        active = session_tracker.active
        if not active:
            return None
        allowed = self.config.params.get("tradable_boards") or list(self.DEFAULT_TRADABLE_BOARDS)
        for candidate in ("main", "post_nxt", "pre_nxt"):
            if candidate in allowed and MarketBoard(candidate) in active:
                return candidate
        return None

    def on_open_price_confirmed(self, ticker: str, open_price: int, board: str = "main") -> None:
        """보드별 시가 확정 — Target Price를 보드별로 계산한다."""
        info = self._targets.get(ticker)
        if not info or open_price <= 0:
            return

        base = info.get("target_offset_base", info.get("target_offset", 0))
        k_key = self._BOARD_K_KEY.get(board, "k_value_krx_main")
        k_mult = float(self.config.params.get(k_key, 1.0))
        target_offset = max(int(base * k_mult), 0)

        info.setdefault("boards", {})[board] = {
            "open_price": open_price,
            "target_price": open_price + target_offset,
            "target_offset": target_offset,
        }
        self._open_confirmed.setdefault(ticker, {})[board] = True

        # backwards-compat: 첫 확정된 보드의 값을 top-level에도 (대시보드/AI자문 호환)
        if not info.get("open_price"):
            info["open_price"] = open_price
            info["target_price"] = open_price + target_offset
            info["target_offset"] = target_offset

    def check_buy_signal(
        self, ticker: str, current_price: int, open_price: int,
    ) -> Signal:
        """현재 활성 보드의 Target Price 돌파 시 매수."""
        if self.state.buy_disabled:
            return Signal.NONE
        if self.state.has_position(ticker) or self.state.is_buy_pending(ticker) or self.state.is_sold_today(ticker):
            return Signal.NONE

        # 사이클 201 — 재진입 쿨다운 (청산 후 2영업일, BFB 사이클 191 패턴 답습)
        today = datetime.now(KST).date()
        cd_until = self._cooldown_until.get(ticker)
        if cd_until and cd_until >= today:
            return Signal.NONE

        if self.is_max_positions():
            return Signal.NONE
        if self.is_daily_loss_exceeded():
            return Signal.NONE

        info = self._targets.get(ticker)
        if not info:
            return Signal.NONE

        board = self._resolve_active_board()
        if board is None:
            return Signal.NONE

        # 시가 미확정 시 현재가를 보드 시가로 사용하여 즉시 확정
        confirmed = self._open_confirmed.get(ticker, {}).get(board, False)
        if not confirmed and open_price > 0:
            self.on_open_price_confirmed(ticker, open_price, board=board)

        board_info = info.get("boards", {}).get(board)
        if not board_info:
            return Signal.NONE

        target = board_info.get("target_price", 0)
        if target <= 0:
            return Signal.NONE

        prev = self._prev_price.setdefault(ticker, {}).get(board, 0)
        self._prev_price[ticker][board] = current_price

        # 보드별 첫 틱은 기록만, 돌파 순간만 감지
        if prev == 0:
            return Signal.NONE

        if prev < target and current_price >= target:
            from src.engine.scanner import t, ticker_names
            board_open = board_info.get("open_price", 0)
            change_rate = round((current_price - board_open) / board_open * 100, 1) if board_open > 0 else 0
            logger.info(
                "변동성돌파 매수 신호 [%s]: %s 현재가(%d) >= 목표가(%d), 이전가(%d), K=%.4f",
                board, t(ticker), current_price, target, prev, info["k"],
            )
            self.state.buy_signals.append({
                "ticker": ticker,
                "name": ticker_names.get(ticker, ""),
                "price": current_price,
                "target_price": target,
                "k": info["k"],
                "board": board,
                "change_rate": change_rate,
                "time": datetime.now().strftime("%H:%M:%S"),
            })
            if len(self.state.buy_signals) > 20:
                self.state.buy_signals.pop(0)
            return Signal.BUY

        return Signal.NONE

    @staticmethod
    def _get_stop_loss_for_board(params: dict, board: str | None) -> float:
        """보드별 손절 임계 우선순위 조회 (사이클 3, 2026-05-17).

        우선순위:
          1. `params[f"stop_loss_{board}"]` — 음수면 채택 (보드별 차별화)
          2. `params["stop_loss_rate"]` — top-level fallback

        `board` 가 None 이면(테스트 환경 / SessionTracker 미동작) 보드별 키 건너뛰고
        top-level fallback. 운영자가 5/15 운영값(`stop_loss_rate=-3.5`) 그대로 두면
        보드별 키 부재 → top-level 적용 → 동작 회귀 보존.

        Args:
          params: 전략 params (DEFAULT_PARAMS 머지 후 dict)
          board: 활성 보드 문자열 ("main"/"pre_nxt"/"post_nxt") 또는 None

        Returns:
          음수 손절 임계값(예: -3.5). 모든 후보 부재 시 0.0(손절 분기 skip).
        """
        if board:
            board_key = f"stop_loss_{board}"
            board_val = params.get(board_key)
            if board_val is not None:
                try:
                    bv = float(board_val)
                except (TypeError, ValueError):
                    bv = 0.0
                if bv < 0:
                    return bv
                # 양수/0 은 무의미 — top-level fallback 으로
        # top-level fallback
        top = params.get("stop_loss_rate")
        if top is None:
            return 0.0
        try:
            tv = float(top)
        except (TypeError, ValueError):
            return 0.0
        return tv if tv < 0 else 0.0

    def check_exit_signal(
        self, ticker: str, current_price: int, open_price: int,
    ) -> Signal:
        """손절: 보드별 손절 임계 우선 (사이클 3, 2026-05-17) — 활성 보드의
        `stop_loss_{board}` 키 있으면 그것, 부재/None 이면 top-level `stop_loss_rate`.

        익일 보유 종목은 NEXT_DAY_CLEAR 안전망 발동.

        VB 정책상 당일 15:20 일괄 청산이 정상 경로 — 본 함수의 익일 청산 분기는
        15:20 청산이 누락된 비상 상황(POST_NXT 설정 오류, 시세 미수신, 시장가 거부,
        프로세스 재시작 race 등)에서만 발동. 2026-05-15 결함 D 잔여.
        """
        pos = self.state.positions.get(ticker)
        if not pos:
            return Signal.NONE

        # 1. 손절 — 가장 우선. 익일 청산 대기 중에도 손절은 즉시 발동.
        loss_rate = (current_price - pos.buy_price) / pos.buy_price * 100
        # 사이클 3 — 활성 보드별 손절 임계. SessionTracker 미동작 시(테스트 환경)
        # `_resolve_active_board()` 가 None 반환 → top-level fallback.
        try:
            active_board = self._resolve_active_board()
        except Exception:
            active_board = None
        stop_loss = self._get_stop_loss_for_board(self.config.params, active_board)
        if loss_rate <= stop_loss:
            from src.engine.scanner import t
            logger.info(
                "변동성돌파 손절: %s 매수가(%d) 대비 %.1f%% (현재가: %d)",
                t(ticker), pos.buy_price, loss_rate, current_price,
            )
            return Signal.STOP_LOSS

        # 2. 익일 청산 안전망 (2026-05-15, 결함 D 잔여) — 전일 매수 종목이 남아 있으면
        # 즉시 청산 신호. 단 scheduler 가 시가 안정화 중(_next_day_clear_pending=True)
        # 이면 보류 — scheduler 가 직접 처리 중이라 race 차단.
        #
        # 사이클 10 (2026-05-18 hot fix) — 무한 신호 발사 차단:
        # scheduler 가 `_pending_next_day_clear` 미등록(08:00 정각 재시작 race 등)이면
        # 본 분기가 매 on_tick(1초) NEXT_DAY_CLEAR 발사 → OrderEngine NXT/SOR 시장가 →
        # KIS KIOK0320 거부 → positions 보존 → 다음 on_tick 또 발사 무한 루프.
        # 신호 return 직전에 영구 set 하여 idempotent 보장. LTV/momentum 패턴과 일관.
        # 부수효과: 09:00 KRX 자동 청산은 못 함 — 15:20 `_force_clear_main_only` 가 흡수.
        if pos.is_next_day and not self._next_day_clear_pending:
            from src.engine.scanner import t
            logger.warning(
                "변동성돌파 익일 청산 안전망 발동: %s (매수일: %s, 정상은 당일 15:20 청산)",
                t(ticker), pos.buy_date,
            )
            self._next_day_clear_pending = True
            return Signal.NEXT_DAY_CLEAR

        return Signal.NONE

    def check_force_clear(self) -> list[str]:
        """15:20 강제 청산 대상 종목 리스트를 반환한다."""
        return list(self.state.positions.keys())

    def calc_buy_quantity(self, current_price: int, ticker: str | None = None) -> int:
        """할당 자금의 position_ratio 비중으로 매수 수량 계산.

        비중 기준 0주이지만 신호가 이미 발생한 상태에서 잔여 자금이 1주는 살 수 있으면
        1주 매수 — 매수 기회 누락 방지(고가 종목이라 비중 가드에 막혀도 신호 우선).
        StrategyBase._fallback_one_share 공통 헬퍼 — 4개 전략 동일.
        """
        if current_price <= 0:
            return 0
        ratio = self.config.params["position_ratio"]
        amount = int(self.state.total_investment * ratio)
        qty = amount // current_price
        if qty > 0:
            return qty
        return self._fallback_one_share(current_price)

    def register_cooldown_after_exit(self, ticker: str) -> None:
        """청산 완료 후 호출 — 쿨다운 1단계 즉시 등록 (사이클 201, BFB 191 패턴 답습).

        1단계: 즉시 달력일 근사(days + 2)로 세팅 → 재매수 공백 0 보장.
        2단계: _refine_cooldown_business_days 가 async KIS 호출로 정확한 N영업일로 정정.
        OrderEngine.on_position_closed 훅에서 호출 (사이클 185 배선 영속).
        """
        days = self.config.params["reentry_cooldown_days"]
        today = datetime.now(KST).date()
        self._cooldown_until[ticker] = today + timedelta(days=days + 2)

    async def _refine_cooldown_business_days(self, ticker: str) -> None:
        """쿨다운을 정확한 N영업일로 정정 (사이클 201, BFB 191 2단계 패턴 답습).

        KIS chk-holiday CTCA0903R 1회 호출 → opnd_yn=="Y" n번째 날로 교체.
        실패 시 1단계 근사값 유지 (graceful).
        """
        days = self.config.params["reentry_cooldown_days"]
        today = datetime.now(KST).date()
        try:
            accurate = await add_business_days(today, days)
            self._cooldown_until[ticker] = accurate
        except Exception:
            logger.warning("[vb] 영업일 정정 실패 (ticker=%s) — 근사값 유지", ticker)

    def on_position_closed(self, ticker: str) -> None:
        """사이클 201 — 포지션 청산 시 재진입 쿨다운 등록 (BFB 사이클 191 패턴 답습)."""
        self.register_cooldown_after_exit(ticker)
        coro = self._refine_cooldown_business_days(ticker)
        try:
            asyncio.create_task(coro)
        except RuntimeError:
            coro.close()  # 이벤트 루프 없는 환경 — coroutine 명시적 닫기, 근사값 유지
