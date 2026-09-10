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
from datetime import date, datetime, time, timedelta, timezone

from src.api.condition import add_business_days
from src.engine import open_price_rest
from src.engine.daily_emit_cap import KstDailyEmitCap
from src.engine.observer_trace import trace_observer_failure
from src.engine.strategy_base import FunnelStage, Signal, StrategyBase, StrategyConfig

KST = timezone(timedelta(hours=9))

# cycle229 (P1-5, 2026-08-28) — 매수 컷오프 15:20 KST. **모듈 상수 = DB override 불가**
# (VB 는 15:20 강제청산 후 신규 매수가 곧 오버나잇이라, OVERNIGHT 금지는 토글로
# 뚫리면 안 되는 규칙이다). 15:20~15:30 은 KRX 장후 동시호가(종가 단일가)로 시장가
# 호가가 **접수**되므로(강제청산 시장가 매도가 작동 중인 것이 방증) 거부라는 우연한
# 안전판이 없고, 15:30 랜덤엔드 확정 종가 1틱은 15:19 마지막 연속체결가 대비 점프해
# 허위 edge-crossing 을 만든다(8/20~8/27 실측 9건 → APBK3013 [단일가매매] 거부 →
# 예외 전파 → 매일 WS 재연결). 자문 = cycle229_vb_1530_single_price.md.
# DEFAULT_PARAMS/PARAM_RANGES 편입 금지.
BUY_CUTOFF_KST = time(15, 20)

# cycle262 (2026-09-06) — 09:00 직후 진입 보류 창의 시작(KRX 개장)과 읽는 쪽 상한.
# 창 폭 자체는 `open_entry_hold_secs` 파라미터다(장중에 끌 수 있어야 하는 임시
# 조치이므로 — 자문 §2.4). 시작 시각과 상한만 상수다: 시작은 KRX 개장이라 튜닝
# 대상이 아니고, 600 은 오타 방어(그 이상은 오전 전체가 무매매다).
OPEN_ENTRY_HOLD_START_HOUR = 9
OPEN_ENTRY_HOLD_MAX_SECS = 600

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
    # 사이클 G Part B — RS/RSI 진입 품질 관찰 (배제 0, 실배제는 유의성 게이트 후 별도 사이클)
    FunnelStage(8, "상대강도 RS 관찰 — 지수(KODEX200) 대비 강세 스코어 기록, 배제 0"),
    FunnelStage(9, "RSI 관찰 — 과매수 극단(>rsi_extreme_max) 스코어 기록, 배제 0"),
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
        # 사이클 G Part A — 실패 돌파 조기청산 (C2, avg_loss↓). default-off = byte-identical.
        # 돌파선(target_price) 아래 buffer% 로 confirm_ticks 연속 재이탈 시 −3% 손절 대기 없이
        # 조기 청산. PARAM_RANGES 미편입 (청산 정체성 상수 — 사이클 198/208/212 선례).
        "failed_breakout_exit_enabled": False,
        "failed_breakout_buffer_pct": -0.5,
        "failed_breakout_confirm_ticks": 2,
        # 사이클 G Part B — RS/RSI 진입 품질 관찰 훅 (기본 OFF = 배제 0, 스코어 계산/funnel 노출만).
        # PARAM_RANGES 미편입 (AI 자동튜닝 금지, 진입 정체성 상수). RSI 는 극단(>85) 관찰만
        # (단순 >70 과매수 컷 금지 — 강세 돌파는 정상적으로 RSI 高, 오닐 반증).
        "rs_filter_enabled": False,
        "rsi_filter_enabled": False,
        "rsi_extreme_max": 85,
        "max_lot_ratio_mult": 2.5,   # cycle245 — 랏 명목 ρ축 상한(K_ρ). 명목 ≤ K_ρ×position_ratio×예산, 1주도 못 사면 미매수. 터틀 모드에선 K축(max_lot_units)이 우선하고 그것이 fail-open 할 때만 백스톱. PARAM_RANGES 미편입. 롤백 = DB 20.0
        # cycle262 (2026-09-06) — KRX 09:00 개장 후 이 초 동안 신규 매수 신호를
        # 발사하지 않는다(0 = OFF = 현행 행위). 목표가의 기준가가 KRX 09:00 시가가
        # 아니라 통합 채널 H0UNCNT0 `fields[7]`(세션 시가 = 프리장 체결이 있었으면
        # 프리장 시가)라, 09:00~09:01:30 진입 20/20 이 '체결가 ≥ KRX시가+offset' 을
        # 위반했다(이후 구간 53/93, Fisher p=6.4e-5). **지혈이지 근본 시정이 아니다**
        # — 오염된 `[7]` 은 일-스코프 상수라 90초 뒤에도 값이 그대로다. 근본은 `[7]`
        # 에 `[24] OPRC_HOUR` 스코프 필터(`src/realtime/**` = 8영역, 별도 승인 + 자문).
        # 진입 정체성 상수 = PARAM_RANGES/INT_PARAMS 편입 금지(cycle223 선례 — 최근
        # 손실을 목적함수로 삼는 튜너는 n≤20 에 과적합한다). 장중 롤백 = PUT 0.
        "open_entry_hold_secs": 90,
        # cycle272 (2026-09-10) — 사용자 결정 D1: `main` 기준가는 KRX REST
        # `stck_oprc` 단일 출처. `"off"` 만 롤백값(대소문자·공백 무시 정확 일치),
        # 그 외 모든 값·부재·예외는 `enforce`. 진입 정체성 상수 —
        # PARAM_RANGES/INT_PARAMS 편입 금지(AST G-272-28a/b). 장중 롤백 =
        # `PUT /api/strategies/{id}/params {"open_price_scope_mode":"off"}`.
        "open_price_scope_mode": "enforce",
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
        # cycle229 (P1-5) — `[vb_buy_cutoff]` 1회/일 관측 cap (날짜 키 자기 리셋)
        self._buy_cutoff_logged_day: date | None = None
        # 사이클 G Part A — ticker -> 돌파선 재이탈 연속 카운트 (조기청산 confirm_ticks 용).
        # transient 상태 — prepare 에서 clear + on_position_closed 에서 pop.
        self._failed_breakout_count: dict[str, int] = {}
        # cycle262 — 09:00 직후 진입 보류 관측 cap 2종. **별개 인스턴스가 계약**이다
        # (같은 슬롯을 다투면 config 1행이 그날의 blocked 표본을 통째로 침묵시킨다 —
        # cycle236 '별개 cap 가드' / donchian OB-11 선례). 날짜 키 자기 리셋은
        # `KstDailyEmitCap`(cycle258) 내장 — `_reset_daily_state` 훅에 의존하면
        # 서브클래스 override 하나로 관측이 영구 침묵한다.
        self._open_entry_hold_config_logged: "KstDailyEmitCap[str]" = KstDailyEmitCap[str]()
        self._open_entry_hold_blocked_logged: "KstDailyEmitCap[str]" = KstDailyEmitCap[str]()

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
        self._failed_breakout_count.clear()  # 사이클 G Part A — 전일 stale 재이탈 카운터 차단

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
        # 사이클 G Part B — step 8/9: RS/RSI 진입 품질 관찰 (배제 0, 스코어/funnel 기록만).
        await self._apply_rs_rsi_observe_in_prepare(final_prepared_tickers)

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

    _PREPARE_LOG_LABEL = "vb"  # refactor-review A1·A2 — base 위임 로그 접두사
    _COOLDOWN_LOG_LABEL = "[vb]"  # refactor-review A3 — base 위임 로그 접두사

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

    async def _apply_rs_rsi_observe_in_prepare(self, tickers: list[str]) -> list[str]:
        """VB prepare 영역 RS/RSI 진입 품질 관찰 훅 (사이클 G Part B, 관찰 전용).

        `_apply_quant_filter_in_prepare`(사이클 C3) 미러. `rs_filter_enabled`/
        `rsi_filter_enabled`(기본 False)일 때는 상대강도(RS)·RSI 스코어를 계산 +
        funnel step(step_no=8/9) 기록만 수행하고 **어떤 종목도 배제하지 않는다**
        (관찰 모드, 입력==출력). Phase 1 은 enabled=True 여도 실배제 미구현 —
        2주 관찰로 증거 축적 후 유의성 게이트 → 별도 사이클에서 실배제.

        - RS 벤치마크 = KODEX200(069500) 일봉 (지수 대비 초과수익률 %p).
        - RSI = 종목 일봉 Wilder RSI. 관찰 대상 = 극단(>rsi_extreme_max=85).
        - 일봉 = `stock_master_daily.get_recent_daily`(DESC → ASC 역순 변환).
        - 보유 종목 절대 보호 (사이클 32 R4) + 결측/예외 fail-open (사이클 88 G-REJECT).
        """
        from src.db import stock_master_daily as _smd_mod
        from src.engine.ta_indicators import relative_strength, rsi as _rsi

        _INDEX_TICKER = "069500"  # KODEX200 (RS 벤치마크)

        # 보유 종목 절대 보호 (사이클 32 R4 답습)
        protected: set[str] = set()
        try:
            from src.engine import scanner as _scanner_mod
            protected = _scanner_mod._collect_protected_tickers_for_scanner()
        except Exception:
            logger.debug(
                "[vb_rs_rsi_observe] protected_tickers 조회 실패 graceful",
                exc_info=True,
            )

        def _closes_asc(rows) -> list[float]:
            """get_recent_daily(DESC) → ASC 종가 시리즈. 결측/비정상 → []."""
            if not rows:
                return []
            out: list[float] = []
            for row in reversed(rows):  # DESC(최신 먼저) → ASC(과거 먼저)
                try:
                    out.append(float(row.get("close_price")))
                except (TypeError, ValueError, AttributeError):
                    return []
            return out

        # 지수(KODEX200) 일봉 1회 조회 — 미수신 시 RS None (배제 0)
        index_closes: list[float] = []
        try:
            index_rows = await _smd_mod.get_recent_daily(_INDEX_TICKER, days=30)
            index_closes = _closes_asc(index_rows)
        except Exception:
            logger.debug(
                "[vb_rs_rsi_observe] 지수(%s) 일봉 조회 실패 graceful",
                _INDEX_TICKER, exc_info=True,
            )

        rs_scores: dict[str, float | None] = {}
        rsi_scores: dict[str, float | None] = {}

        for ticker in tickers:
            if ticker in protected:
                continue
            try:
                rows = await _smd_mod.get_recent_daily(ticker, days=30)
            except Exception:
                logger.debug(
                    "[vb_rs_rsi_observe] get_recent_daily 실패 graceful: %s",
                    ticker, exc_info=True,
                )
                rows = []

            stock_closes = _closes_asc(rows)
            rsi_scores[ticker] = _rsi(stock_closes) if stock_closes else None
            rs_scores[ticker] = (
                relative_strength(stock_closes, index_closes)
                if (stock_closes and index_closes) else None
            )

        # funnel step 8 (RS 관찰) + step 9 (RSI 관찰) — 스코어만 기록, 배제 0
        rs_extreme_max = self.config.params.get("rsi_extreme_max", 85)
        self._record_funnel_pipeline_step(
            VB_FUNNEL_STAGES[7],
            survived=[
                {"ticker": t, "rs": rs_scores.get(t)} for t in tickers
            ],
            step_conditions=(
                f"관찰 전용(rs_filter_enabled={self.config.params.get('rs_filter_enabled', False)}) "
                f"— 지수(KODEX200 {_INDEX_TICKER}) 대비 상대강도 스코어 기록, 배제 0"
            ),
        )
        self._record_funnel_pipeline_step(
            VB_FUNNEL_STAGES[8],
            survived=[
                {"ticker": t, "rsi": rsi_scores.get(t)} for t in tickers
            ],
            step_conditions=(
                f"관찰 전용(rsi_filter_enabled={self.config.params.get('rsi_filter_enabled', False)}) "
                f"— RSI 과매수 극단(>{rs_extreme_max}) 스코어 기록, 배제 0"
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

    def on_open_price_confirmed(
        self, ticker: str, open_price: int, board: str = "main", *, source: str = "ws",
    ) -> None:
        """보드별 시가 확정 — Target Price를 보드별로 계산한다.

        cycle272 (2026-09-10) — `board=="main"` 확정은 `source` 가 신뢰 목록
        (`("rest",)`)에 있을 때만 통과한다(`open_price_scope_mode` 기본
        `enforce`). `source` 기본값이 불신 `"ws"` 이므로 이 함수를 부르는 세
        경로(스케줄러 1차 WS 폴링·전략 인라인 확정·그 밖의 미래 호출부)는
        **한 글자도 안 바뀐다** — `check_buy_signal`/`check_exit_signal`/
        `calc_buy_quantity` byte 동일이 그 증거다(cycle264 `_STRATEGY_PINS`
        6개 불변). 비-`main` 보드(`pre_nxt`/`post_nxt`)는 게이트 스코프 밖이라
        전면 무접촉(LTV 08:00 프리장 등).
        """
        if open_price_rest.reject_untrusted_main_basis(
            self.config.params, board, source,
            strategy_id=self.strategy_id, ticker=ticker,
            tick_open=open_price, dest_logger=logger,
        ):
            return
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
        # cycle229 (P1-5) — 15:20 매수 컷. **최상단·`_prev_price` 갱신 이전**이 계약:
        # 뒤에 두면 종가/예상체결가가 baseline 이 되어 장중 재시작 시 거짓 미돌파를
        # 만든다(컷 틱은 어떤 상태도 갱신하지 않는다). 반드시 KST 명시(naive 금지 —
        # 컨테이너 TZ 의존은 P2-6 등재 결함).
        _now_kst = datetime.now(KST)
        if _now_kst.time() >= BUY_CUTOFF_KST:
            if self._buy_cutoff_logged_day != _now_kst.date():
                # 1회/일 관측 — 발화 없이 조용히 막으면 "왜 안 사나"를 영영 못 본다
                # (사이클 224 교훈). 날짜 키 자기 리셋(_reset_daily_state 훅 미의존).
                self._buy_cutoff_logged_day = _now_kst.date()
                logger.info(
                    "[vb_buy_cutoff] 15:20 이후 매수 신호 차단 — ticker=%s "
                    "(장후 동시호가·확정 종가 틱은 진입 대상이 아니다)",
                    ticker,
                )
            return Signal.NONE
        # cycle262 — 09:00 직후 진입 보류. 여기서는 **읽고 관측만** 한다 (차단 판정은
        # 아래 발사점). 카나리아를 발사점에 두면 돌파가 없는 날 한 줄도 안 남아
        # '보류가 조용히 꺼진' 상태를 볼 수 없다(자문 §2.5 침묵 차단) — 그래서
        # 카나리아(매 평가)와 판정(발사점)을 일부러 분리했다.
        _hold_secs = self._read_open_entry_hold_secs()
        self._emit_open_entry_hold_config(_hold_secs, _now_kst)
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
            # cycle233 — 계좌 SOFT Σ상한 게이트는 **발사 직전**이다 (다크런치·fail-open).
            # 최상단에 두면 block 구간 동안 `_prev_price` baseline 갱신이 동결돼,
            # 순간 게이트(양방향)가 장중 해제된 뒤 첫 틱이 stale baseline 대비
            # **거짓 돌파**로 읽힌다(적대 검증 C233-F1 — VB 는 추격 상한이 없어
            # 진입가 상한 없는 추격 매수가 된다). baseline 은 위에서 이미 갱신됐고
            # 여기서는 신호만 막는다 = "신규 매수 신호만 차단" 계약의 정확한 구현.
            if self._account_soft_gate_blocked(ticker):
                return Signal.NONE
            # cycle262 — 09:00 직후 N초 진입 보류 (기준가 오염 지혈, 자문 §2.3).
            # **이 자리가 계약이다.** 최상단으로 올리면 (a) 보류 구간 동안
            # `_prev_price` baseline 이 동결돼 해제 후 첫 틱이 stale baseline 대비
            # 거짓 돌파로 읽히고(cycle233 C233-F1 — VB 는 추격 상한이 없어 그대로
            # 진입가 상한 없는 추격 매수가 된다) (b) 목표가도 baseline 도 안 잡혀
            # **무엇을 살 뻔했는지**를 기록할 수 없다 = 결함의 증거를 스스로 지운다.
            # baseline 은 위에서 이미 갱신됐고 여기서는 신호만 막는다.
            # 보드로 분기하지 않는다(시간창 단독) — 09:00:00~09:00:30 은 세션 트래커
            # 30초 주기 탓에 보드가 아직 pre_nxt 로 잡힐 수 있는데 그건 설계 의도가
            # 아니라 stale 캐시 산물이라, 보드로 나누면 그 30초가 통째로 구멍이 된다.
            _hold_elapsed = self._open_entry_hold_elapsed(_now_kst, _hold_secs)
            if _hold_elapsed is not None:
                # 관측은 **행위 밖**이다 — emit 이 어떻게 터지든 아래 return 은 그대로
                # 수행된다(관측 예외가 check_buy_signal 을 뚫으면 risk.on_tick 이 그
                # 종목의 나머지 평가를 잃는다, cycle237 TE-2).
                try:
                    from src.engine.scanner import ticker_prev_close
                    _key = ticker or "-"
                    if self._open_entry_hold_blocked_logged.should_emit(_key, now=_now_kst):
                        logger.info(
                            "[open_entry_hold_blocked] ticker=%s board=%s "
                            "current_price=%d target=%d board_open=%d prev=%d "
                            "k=%.4f offset=%d elapsed_secs=%d prdy_close=%d "
                            "note='09:00 직후 %d초 진입 보류 — would_buy 정본'",
                            _key, board, current_price, target,
                            int(board_info.get("open_price", 0) or 0), prev,
                            float(info.get("k") or 0),
                            int(board_info.get("target_offset", 0) or 0),
                            _hold_elapsed,
                            int(ticker_prev_close.get(ticker, 0) or 0),
                            _hold_secs,
                        )
                        self._open_entry_hold_blocked_logged.mark_emitted(_key, now=_now_kst)
                except Exception:
                    try:
                        trace_observer_failure(
                            "[open_entry_hold_blocked]", ticker or "-",
                            self._open_entry_hold_blocked_logged, dest_logger=logger,
                        )
                    except Exception:  # pragma: no cover — 2차 예외까지 흡수
                        pass
                return Signal.NONE
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

    # ────────── cycle262 — 09:00 직후 진입 보류 (`open_entry_hold_secs`) ──────────
    #
    # 지혈이지 근본 시정이 아니다. 목표가의 기준가가 KRX 09:00 시가가 아니라 통합 채널
    # H0UNCNT0 `fields[7]`(세션 시가)이고, 그 값은 **일-스코프 상수**라 90초 뒤에도
    # 그대로다 — 근본은 `[7]` 에 `[24] OPRC_HOUR` 스코프 필터를 거는 것이고
    # `src/realtime/**` = 8영역이라 별도 승인 + 별도 자문 사안이다.

    def _read_open_entry_hold_secs(self) -> int:
        """`open_entry_hold_secs` 읽기 + `[0, 600]` 클램프. **결측·무효 = 0 = OFF**.

        키 부재·None·빈 문자열·파싱 실패는 전부 0(보류 없음 = 현행 행위)이다.
        **fail-open 이 계약**이고 반대 방향은 금지다 — "설정이 없으면 막는다" 는
        P0-1 유령 키(`ticker_prices["acml_vol"]` 대입부 0)가 BFB/VCP 를 전 기간
        체결 0건으로 만든 바로 그 경로다. 코드 기본값 90 은 `DEFAULT_PARAMS` 가
        제공하므로 런타임에 키가 없는 경우는 사실상 없고(`_load_strategy_config` ·
        `PUT /params` 둘 다 **코드에 이미 있는 키만** 덮는 오버레이다), 폴백 0 은
        그 전제가 깨졌을 때 매수를 조용히 막지 않겠다는 선언이다.

        상한 클램프가 필요한 이유 = `PUT /api/strategies/{id}/params` 가 화이트리스트
        없이 기존 키를 덮으므로 검증은 **읽는 쪽**에 있어야 한다. 오타 하나(`10000`)가
        오전 전체를 무매매로 만드는 것을 막는다.

        `except Exception` 이 계약이다(cycle262 적대 검증 HIGH). 좁은 튜플
        `(TypeError, ValueError)` 는 **자기 docstring 을 어긴다** — `1e400` 은 표준
        유효 JSON 이라 starlette/pydantic 파서가 `inf` 로 만들고 `int(inf)` 는
        `OverflowError`(∉ 튜플)를 던진다. 그 예외는 `check_buy_signal` 최상단에서
        전파돼 `risk.on_tick`(전략별 try 없음) → `handler.py` `[callback_exception]`
        → **재연결 re-raise** 로 이어진다(= 틱마다 WS 재연결 = 손절 사각). 여기는
        관측이 아니라 **행위 입력**이라 C10 의 관측 try/except 로 덮이지 않는다 —
        읽는 쪽에서 닫는다.
        """
        try:
            secs = int(self.config.params.get("open_entry_hold_secs", 0) or 0)
        except Exception:
            return 0
        if secs < 0:
            return 0
        return min(secs, OPEN_ENTRY_HOLD_MAX_SECS)

    def _open_entry_hold_elapsed(self, now: datetime, hold_secs: int) -> int | None:
        """보류 창 안이면 09:00:00 이후 경과 초, 창 밖이면 `None`. 순수 계산.

        창 = KST `[09:00:00, 09:00:00 + hold_secs)` — **하한 포함 · 상한 배타**.
        `hold_secs <= 0` 이면 항상 `None`(= OFF = 현행 행위).

        `now` 는 **tz-aware KST** 여야 한다. naive 벽시계는 컨테이너 `TZ` 가 깨지는
        순간 창을 9시간 옮겨 *막아야 할 때 열고 열어야 할 때 막는다*(cycle229 G-1 이
        AST 로 잡는 그 결함). 보드가 아니라 시각으로만 판정하는 이유는 호출부 주석 참조.
        """
        if hold_secs <= 0:
            return None
        start = now.replace(
            hour=OPEN_ENTRY_HOLD_START_HOUR, minute=0, second=0, microsecond=0,
        )
        if not (start <= now < start + timedelta(seconds=hold_secs)):
            return None
        return int((now - start).total_seconds())

    def _emit_open_entry_hold_config(self, hold_secs: int, now: datetime) -> None:
        """`[open_entry_hold_config]` — 그날 실제 적용값 카나리아. INFO, 1회/(전략, 값)/일.

        **fail-open 이 침묵과 짝이 되면 안 된다**(자문 §2.5). 키가 사라져 보류가 꺼진
        날에도 `hold_secs=0` 한 줄이 남아야 운영자가 그 사실을 본다 —
        `[ratio_cap_config]`(cycle245) 선례 그대로다.

        cap 키가 **값-민감**(`cfg|<초>`)인 이유 = 장중 유일 롤백 수단인
        `PUT /api/strategies/{id}/params` 는 in-memory `config.params` 를 즉시 덮는데,
        단일 키면 그날 첫 틱이 이미 cap 을 소진해 **바뀐 값을 확인할 마커가 0 개**가
        된다(cycle245 R1 이 겪은 사각). 정상 운영에선 값이 안 바뀌므로 1행/일이고,
        실제로 바꾼 날에만 1행이 늘어 롤백 확인이 회복된다.

        09:00 이전에는 발화하지 않는다 — 이 사이클은 KRX 개장 이후 창만 다루고,
        LTV 의 08:00~09:00 프리장 매수는 **무접촉**이기 때문이다(그 구간의 `[7]` 은
        그 보드의 올바른 기준가다 — 오염이 아니다, 자문 §2.1).

        ⚠️ `source` 는 **출처가 아니라 값 동등성 추론**이다(적대 검증 LOW, 명시 한계).
        적용값이 `DEFAULT_PARAMS[KEY]` 와 같으면 `default`, 다르면 `db` 다. 그래서
        운영자가 `PUT {"open_entry_hold_secs": 90}` 으로 **90 을 명시 재확정한** 날에도
        라벨은 `default` 다. 진짜 출처 판정은 이 파일에서 관측 불가하다 —
        `_load_strategy_config`(scheduler) 도 `update_params`(routes) 도 병합된
        `config.params[key]` 를 **제자리에서 덮어써** 출처 흔적을 남기지 않고, 그 둘은
        cycle262 C12 의 무접촉 대상이다(후속 티켓). 그래서 "값이 바뀌었나" 의 정본은
        `source` 가 아니라 **`hold_secs=` 자체 + 값-민감 cap 이 만드는 2행째**다.

        어떤 실패도 흡수한다(관측은 행위 밖). 흔적은 `observer_trace` 규약을 따른다.
        """
        try:
            start = now.replace(
                hour=OPEN_ENTRY_HOLD_START_HOUR, minute=0, second=0, microsecond=0,
            )
            if now < start:
                return
            key = f"cfg|{hold_secs}"
            if not self._open_entry_hold_config_logged.should_emit(key, now=now):
                return
            until = (start + timedelta(seconds=hold_secs)).strftime("%H:%M:%S")
            source = (
                "default"
                if hold_secs == self.DEFAULT_PARAMS.get("open_entry_hold_secs")
                else "db"
            )
            logger.info(
                "[open_entry_hold_config] strategy=%s hold_secs=%d until=%s "
                "source=%s note='09:00 직후 진입 보류 — 0 이면 OFF(현행 행위). "
                "라벨은 코드 기본값과의 값 동등성 추론이다(출처 아님)'",
                self.strategy_id, hold_secs, until, source,
            )
            self._open_entry_hold_config_logged.mark_emitted(key, now=now)
        except Exception:
            try:
                trace_observer_failure(
                    "[open_entry_hold_config]", self.strategy_id,
                    self._open_entry_hold_config_logged, dest_logger=logger,
                )
            except Exception:  # pragma: no cover — 2차 예외까지 흡수
                pass

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

        # 1.5 사이클 G Part A — 실패 돌파 조기청산 (C2, avg_loss↓). default-off = byte-identical.
        # 돌파선(target_price) 아래 buffer% 로 confirm_ticks 연속 재이탈 시 −3% 손절 대기 없이
        # 조기 청산 → |avg_loss| 직접 축소. 승자(target 위 유지)는 카운터 리셋으로 미간섭.
        # enabled=False(기본) 면 분기 미진입 = byte-identical.
        if self.config.params.get("failed_breakout_exit_enabled", False):
            info = self._targets.get(ticker)
            target_price = 0
            if info:
                boards = info.get("boards") or {}
                board_info = boards.get(active_board) if active_board else None
                if board_info and board_info.get("target_price"):
                    target_price = int(board_info["target_price"])
                elif info.get("target_price"):
                    target_price = int(info["target_price"])
            if target_price > 0:
                buffer_pct = float(self.config.params.get("failed_breakout_buffer_pct", -0.5))
                threshold = target_price * (1 + buffer_pct / 100)
                if current_price < threshold:
                    cnt = self._failed_breakout_count.get(ticker, 0) + 1
                    self._failed_breakout_count[ticker] = cnt
                    confirm = int(self.config.params.get("failed_breakout_confirm_ticks", 2))
                    if cnt >= confirm:
                        from src.engine.scanner import t
                        logger.info(
                            "[vb_failed_breakout_exit] %s 돌파선 재이탈 %d회 연속 "
                            "(현재가 %d < 돌파선 %d × %.2f%% = %.1f) — 조기청산",
                            t(ticker), cnt, current_price, target_price, buffer_pct, threshold,
                        )
                        return Signal.STOP_LOSS
                else:
                    # 회복(돌파선 위) → 카운터 리셋 (연속 확인 요구 보존)
                    self._failed_breakout_count[ticker] = 0

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
        StrategyBase._apply_budget_limit 공통 관문 — 7 전략 동일 (0주 시 1주 폴백 위임).
        """
        if current_price <= 0:
            return 0
        ratio = self.config.params["position_ratio"]
        amount = int(self.state.total_investment * ratio)
        return self._apply_budget_limit(amount // current_price, current_price, ticker)

    def register_cooldown_after_exit(self, ticker: str) -> None:
        """청산 완료 후 호출 — 쿨다운 1단계 즉시 등록 (사이클 201, BFB 191 패턴 답습).

        1단계: 즉시 달력일 근사(days + 2)로 세팅 → 재매수 공백 0 보장.
        2단계: _refine_cooldown_business_days 가 async KIS 호출로 정확한 N영업일로 정정.
        OrderEngine.on_position_closed 훅에서 호출 (사이클 185 배선 영속).
        """
        days = self.config.params["reentry_cooldown_days"]
        today = datetime.now(KST).date()
        self._cooldown_until[ticker] = today + timedelta(days=days + 2)

    def on_position_closed(self, ticker: str) -> None:
        """사이클 201 — 포지션 청산 시 재진입 쿨다운 등록 (BFB 사이클 191 패턴 답습)."""
        self._failed_breakout_count.pop(ticker, None)  # 사이클 G Part A — 재진입 stale 카운터 차단
        self.register_cooldown_after_exit(ticker)
        coro = self._refine_cooldown_business_days(ticker)
        try:
            asyncio.create_task(coro)
        except RuntimeError:
            coro.close()  # 이벤트 루프 없는 환경 — coroutine 명시적 닫기, 근사값 유지
