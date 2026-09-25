"""롱테일 변동성 돌파 전략.

변동성 돌파 진입 + 상한가 도달 시 익일 청산으로 롱테일(긴 우측 보상) 추구.
- 대상: 시총/거래대금 필터 + 연속상한가 제외
- 매수: 시가 + (전일Range × K) 돌파 시 (변동성 돌파 방식)
- 당일 상한가 미도달: 당일 손절(-3%) + 15:20 강제 청산
- 당일 상한가 도달(+29%): 익일 청산 모드 전환 — 손절(-5%), 갭상승 +10% 트레일링/-2%
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

# cycle262 (2026-09-06) — 09:00 직후 진입 보류 창의 시작(KRX 개장)과 읽는 쪽 상한.
# 창 폭 자체는 `open_entry_hold_secs` 파라미터다(장중에 끌 수 있어야 하는 임시
# 조치이므로 — 자문 §2.4). VB 와 값이 같아도 상수를 공유하지 않는다(파일 간 결합
# 금지 — 한쪽만 바꾸려는 미래의 변경이 다른 쪽을 조용히 끌고 간다, cycle229 G-4).
OPEN_ENTRY_HOLD_START_HOUR = 9
OPEN_ENTRY_HOLD_MAX_SECS = 600

# cycle286 (2026-09-12, C2-a) — `main` 보드 신규 매수 컷 15:20 KST.
# **모듈 상수 = DB override 불가** (DEFAULT_PARAMS/PARAM_RANGES/INT_PARAMS 편입 금지).
# 이유: (a) KRX 연속체결은 15:20 에 끝난다(market_state K3.end) — LTV 의 돌파 판정이
# 유효한 가격형성이 그 시각에 소멸한다. (b) 15:20~15:30 종가 단일가(K4)는 00/01 을
# **접수**하므로 거부라는 우연한 안전판이 없고, 15:20 `_force_clear_main_only` 는 이미
# 지나가 있어 그 체결은 **당일 모드 그대로 오버나이트로 남는다**(익일청산·갭가드·
# 트레일링이 전부 `_limit_up_reached` 전용). 오버나이트 금지는 DB 토글로 뚫려선 안 되는
# 규칙이다(cycle229 G-2 동일 논거). (c) 15:30~15:40 은 KRX 가 종가 고정(K5, 06 전용)이고
# NXT 는 애프터 단일가(N5)라 그 구간의 "돌파"는 확정 종가 1틱 또는 타 시장 가격이다.
# 값은 scheduler.TIME_KRX_MAIN_BUY_STOP / VB·momentum BUY_CUTOFF_KST 와 같으나 상수는
# **전략별 소유**(cycle229 G-4 — 파일 간 결합 금지, scheduler import 는 순환).
# 이름에 MAIN 을 넣은 이유 = LTV 는 VB 와 달리 **보드 스코프 컷**이다(post_nxt 15:40~19:50
# 매수는 무접촉). 롤백 = 1커밋 revert, 장중 긴급 = PUT tradable_boards 에서 "main" 제거.
MAIN_BUY_CUTOFF_KST = time(15, 20)

logger = logging.getLogger(__name__)


# 사이클 143 (2026-06-15) — LTV 6단계 funnel hook (사이클 140 자문 영속)
# 사이클 157 (2026-06-17) — 1단계 진입 차단 13건 step 추가 영구 영속 → 7단계.
# VB 6단계 + 연속 상한가 필터 (LTV 특화 영역 영구 영속).
# 사이클 47 FUNNEL_STAGES 위임 패턴 답습 (`_record_funnel_pipeline_step(LTV_FUNNEL_STAGES[i-1], ...)`).
LTV_FUNNEL_STAGES: tuple[FunnelStage, ...] = (
    FunnelStage(1, "거래량순위 + stock_master 기반 후보"),
    FunnelStage(2, "시총 + 거래대금 필터 통과"),
    FunnelStage(3, "1단계 진입 차단 13건 통과 (거래정지/관리/단기과열/투자유의 등)"),
    FunnelStage(4, "일봉 fetch 통과"),
    FunnelStage(5, "전일 Range > 0 + noise 계산 통과"),
    FunnelStage(6, "연속 상한가 필터 통과"),
    FunnelStage(7, "K값 계산 + target_offset > 0"),
)


def _empty_scan_stats() -> dict:
    """사이클 21 — LTV 단계별 깔때기 카운트 dict (10 키).

    VB 의 9 키 + `consecutive_limit_pass` (연속상한가 제외 통과) 추가.
    """
    return {
        "universe_candidates": 0,
        "universe_filtered": 0,
        "price_filtered": 0,
        "mcap_pass": 0,
        "trade_amount_pass": 0,
        "candle_fetch_ok": 0,
        "consecutive_limit_pass": 0,  # LTV 전용 — 연속상한가 N일 미해당 통과
        "k_value_computed": 0,
        "final_prepared": 0,
        "last_run_at": None,
    }


class LongTailVolatilityStrategy(StrategyBase):
    """롱테일 변동성 돌파 전략."""

    # 매매 가능 보드 — PRE_NXT + MAIN + POST_NXT 3보드 (사이클 38, 2026-05-22: 사용자 의도 복원).
    #
    # 사이클 26 (2026-05-20): KRX ONLY 변경 (`("main",)`) — SK하이닉스 시가 결함 추적 중 도입.
    # 사이클 38 (2026-05-22): 사용자 운영 의도 복원 — LTV 연속 상한가 익일 청산 모드 + 야간 매수.
    # - PRE_NXT(08:00~09:00) 매수 가능: 야간 NXT 프리 진입 (사용자 운영 정책).
    # - MAIN(09:00~15:20) 매수 가능: KRX 메인 시간대.
    # - POST_NXT(15:40~19:50) 매수 가능: 연속 상한가 종목 익일 청산 모드 진입.
    #
    # `tradable_boards` 는 **매수 진입 전용** — 매도/손절/Trailing/익일청산/상한가 손절 모니터링은
    # 어떤 시간대에서도 보드 가드 *없이* 항상 작동 (`risk.on_tick` 의 `check_exit_signal` 분기).
    DEFAULT_TRADABLE_BOARDS = ("pre_nxt", "main", "post_nxt")

    DEFAULT_PARAMS = {
        "tradable_boards": list(DEFAULT_TRADABLE_BOARDS),
        # 진입 조건
        "k_period": 20,
        "min_prdy_rate": 5.0,                        # 전일대비 최소 등락률
        # 보드별 K값 곱 (Phase 5 Q1=C: 보드별 분리)
        "k_value_krx_main": 1.0,
        "k_value_nxt_pre": 1.0,
        "k_value_nxt_post": 1.0,
        "exchange": "KRX",
        # 종목 필터
        "min_market_cap": 100_000_000_000,            # 시총 1,000억
        "min_trade_amount": 20_000_000_000,           # 거래대금 200억
        "max_scan_stocks": 100,
        "exclude_consecutive_limit": 2,               # 연속 상한가 N일 이상 제외
        "reentry_cooldown_days": 2,                    # 사이클 213 — 재진입 쿨다운 (당일 모드 손절, VB 동형)
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
        "max_lot_ratio_mult": 2.5,   # cycle245 — 랏 명목 ρ축 상한(K_ρ). 명목 ≤ K_ρ×position_ratio×예산, 1주도 못 사면 미매수. 터틀 모드에선 K축(max_lot_units)이 우선하고 그것이 fail-open 할 때만 백스톱. PARAM_RANGES 미편입. 롤백 = DB 20.0
        # cycle262 (2026-09-06) — KRX 09:00 개장 후 이 초 동안 신규 매수 신호를
        # 발사하지 않는다(0 = OFF = 현행 행위). LTV 는 08:00~09:00 pre_nxt 에서
        # **그 보드의 올바른 시가**로 정상 판정하지만, 09:00 에 보드가 main 으로
        # 넘어가면 `_open_confirmed['main']` 이 False 라 **같은 프리장 시가로 main
        # 목표가를 다시 굳힌다** — 프리장 목표가를 KRX 목표가로 이름만 바꿔 다시
        # 거는 셈이고, `min_prdy_rate` 필터 탓에 갭업이 클수록 통과가 쉬워진다
        # (09:35 스탬프 실측 3/3 불일치). **지혈이지 근본 시정이 아니다** — 근본은
        # `[7]` 에 `[24] OPRC_HOUR` 스코프 필터(`src/realtime/**` = 8영역, 별도 승인).
        # 진입 정체성 상수 = PARAM_RANGES/INT_PARAMS 편입 금지. 장중 롤백 = PUT 0
        # (키가 전략별이라 VB 90 을 유지한 채 LTV 만 끌 수 있다).
        "open_entry_hold_secs": 90,
        # cycle272 (2026-09-10) — 사용자 결정 D1: `main` 기준가는 KRX REST
        # `stck_oprc` 단일 출처. `"off"` 만 롤백값(대소문자·공백 무시 정확 일치),
        # 그 외 모든 값·부재·예외는 `enforce`. 진입 정체성 상수 —
        # PARAM_RANGES/INT_PARAMS 편입 금지(AST G-272-28a/b). `pre_nxt`/
        # `post_nxt` 보드는 게이트 스코프 밖이라 08:00~09:00 프리장 매수·야간
        # 매수는 무접촉. 장중 롤백 = `PUT /api/strategies/{id}/params
        # {"open_price_scope_mode":"off"}`.
        "open_price_scope_mode": "enforce",
        # cycle274 (2026-09-11) — VB·LTV 매수 신호 LLM 평가 게이트(shadow). 값은
        # **기록만** 한다 — `enforce` 는 이 사이클에 미구현이라 `shadow` 외 전부
        # `off` 로 낙하한다(leaf `llm_buy_gate._read_mode`). 돈을 쓰는 기능이라
        # `llm_gate_mode`/`llm_gate_daily_call_cap` 키 부재는 **off/0**(cycle245
        # `max_lot_ratio_mult` 관례와 같은 방향, cycle272 `open_price_scope_mode`
        # 부재=enforce 와는 반대). PARAM_RANGES/INT_PARAMS 편입 금지(4키 전부,
        # AST 런타임+소스 이중 가드). 장중 롤백 =
        # `PUT /api/strategies/{id}/params {"llm_gate_mode":"off"}`.
        "llm_gate_mode": "shadow",
        "llm_gate_min_score": 70,
        "llm_gate_daily_call_cap": 20,
        "llm_gate_timeout_secs": 20,
        # cycle290 (2026-09-13) — 장중 킬스위치 등재. 값은 코드 상수와 **같은 값**이라
        # 등재 자체의 매매 행위 변경은 0 이다(`order_engine._ORDER_EXCHANGE_CLOCK_MODE_DEFAULT`
        # ·`_AFTER_EXIT_DIVISION_DEFAULT`). `PARAM_RANGES`/`INT_PARAMS` 편입 금지 —
        # AI 자문이 청산 수단을 끄는 스위치를 뒤집으면 안 된다. 장중 롤백은 PUT 뿐
        # (SQL UPDATE 는 다음 재시작에서만, cycle232 D6). 사고 중 조작 순서 =
        # `_workspace/00_leader_trading_rules.md` 「거래소 라우팅」 절.
        "order_exchange_clock_mode": "enforce",
        "after_market_exit_division": "44",
        # cycle352 (2026-09-25) — 15:20 상한가 유지 확인. 사용자 결정 D5 F3①
        # (`_workspace/domain_consult/cycle352_ltv_limit_up_trailing.md`). 실측 —
        # 실현손실은 이미 overnight_stop_loss 에서 멈추고(모집단 373건 중 15%
        # 이상 되밀림은 2%), 이름 그대로의 당일 트레일링은 폭을 얼마로 잡아도
        # 평균 수익을 깎는다(7~15% 폭 전부 A 대비 열위). 가장 싸게 같은 걱정을
        # 닫는 것은 "15:20 에 아직 상한가 근처인가" 한 번만 묻는 것 —
        # 아니면 그날 종가에 판다(평균 수익 거의 그대로, −5% 이하 손실
        # 표본은 절반으로 준다). `"off"` 만 롤백값(대소문자·공백 무시 정확
        # 일치), 그 밖의 값·부재·비문자열은 전부 `enforce`(`open_price_scope_mode`
        # 와 같은 규약 — 배포 즉시 켜진다). `PARAM_RANGES`/`INT_PARAMS` 편입
        # 금지(청산 규약 킬스위치). 장중 롤백 =
        # `PUT /api/strategies/long_tail_volatility/params
        # {"limit_up_close_hold_mode":"off"}` 즉시.
        "limit_up_close_hold_mode": "enforce",
    }

    def __init__(self, config: StrategyConfig):
        merged = {**self.DEFAULT_PARAMS, **config.params}
        config.params = merged
        super().__init__(config)
        # VB와 동일 — 종목별 타겟 가격/K값 (Phase 5: 보드별 분리)
        self._targets: dict[str, dict] = {}
        self._open_confirmed: dict[str, dict[str, bool]] = {}
        self._prev_price: dict[str, dict[str, int]] = {}
        self._scanned_tickers: list[str] = []
        # 사이클 170 카드 C — _scan_universe 가 보관한 원천 유니버스 후보 (필터 전).
        # funnel step1 noise 0 placeholder 제거 — 실제 후보 노출.
        self._universe_candidate_tickers: list[str] = []
        # 상한가 도달 → 익일 청산 모드 종목
        self._limit_up_reached: set[str] = set()
        # 사이클 213 — 재진입 쿨다운 (ticker -> 쿨다운 만료일, 당일 모드 손절만 등록)
        self._cooldown_until: dict[str, date] = {}
        # 익일 청산 시가 안정화 대기 플래그
        self._next_day_clear_pending = False
        # 사이클 21 — 단계별 카운트 (ScanMonitor 깔때기)
        self._scan_stats: dict = _empty_scan_stats()
        # cycle262 — 09:00 직후 진입 보류 관측 cap 2종. **별개 인스턴스가 계약**이다
        # (같은 슬롯을 다투면 config 1행이 그날의 blocked 표본을 통째로 침묵시킨다 —
        # cycle236 '별개 cap 가드' / donchian OB-11 선례). 날짜 키 자기 리셋은
        # `KstDailyEmitCap`(cycle258) 내장 — `_reset_daily_state` 훅에 의존하면
        # 서브클래스 override 하나로 관측이 영구 침묵한다.
        self._open_entry_hold_config_logged: "KstDailyEmitCap[str]" = KstDailyEmitCap[str]()
        self._open_entry_hold_blocked_logged: "KstDailyEmitCap[str]" = KstDailyEmitCap[str]()
        # cycle286 (C2-a) — `main` 15:20 매수 컷 관측 cap. cycle262 cap 과 **별개
        # 인스턴스**(같은 슬롯을 다투면 config 1행이 그날의 blocked 표본을 통째로
        # 침묵시킨다 — cycle236 '별개 cap 가드' / donchian OB-11 선례). 1회/ticker/일.
        self._main_buy_cutoff_logged: "KstDailyEmitCap[str]" = KstDailyEmitCap[str]()
        # cycle352 — 15:20 상한가 유지 확인 관측 cap 2종. 기존 cap 들과 **별개
        # 인스턴스**(같은 슬롯을 다투면 config 1행이 그날의 표본을 침묵시킨다 —
        # cycle236 '별개 cap 가드' 선례).
        self._limit_up_close_config_logged: "KstDailyEmitCap[str]" = KstDailyEmitCap[str]()
        self._limit_up_close_decision_logged: "KstDailyEmitCap[str]" = KstDailyEmitCap[str]()

    def register_cooldown_after_exit(self, ticker: str) -> None:
        """청산 완료 후 호출 — 쿨다운 1단계 즉시 등록 (사이클 213, VB 201 패턴 답습).

        1단계: 즉시 달력일 근사(days + 2)로 세팅 → 재매수 공백 0 보장.
        2단계: _refine_cooldown_business_days 가 async KIS 호출로 정확한 N영업일로 정정.
        on_position_closed 훅에서 호출 (당일 모드 손절만 — 상한가 모드는 면제).
        """
        days = self.config.params["reentry_cooldown_days"]
        today = datetime.now(KST).date()
        self._cooldown_until[ticker] = today + timedelta(days=days + 2)

    def on_position_closed(self, ticker: str) -> None:
        """사이클 185 — 포지션 청산 시 상한가 모드 보유결합 상태 정리.

        사이클 213 — 재진입 쿨다운 등록 (당일 모드 손절만, 상한가 모드는 면제).
        was_limit_up 판정은 discard *전* — discard 먼저면 항상 False 가 되어
        상한가 모드 종목까지 쿨다운에 걸리는 면제 붕괴가 발생한다 (순서 고정 의무).
        """
        was_limit_up = ticker in self._limit_up_reached
        self._limit_up_reached.discard(ticker)
        if not was_limit_up:
            self.register_cooldown_after_exit(ticker)
            coro = self._refine_cooldown_business_days(ticker)
            try:
                asyncio.create_task(coro)
            except RuntimeError:
                coro.close()  # 이벤트 루프 없는 환경 — coroutine 명시적 닫기, 근사값 유지

    async def prepare(self) -> None:
        """장 시작 전: 종목 스캔 → K값 계산 → 연속상한가 필터링.

        사이클 143 (2026-06-15) — 사이클 140 자문 영속 LTV 6단계 funnel hook 추가.
        VB 5단계 + 연속 상한가 필터 (LTV 특화 영역 영구 영속).

        사이클 163 (2026-06-18) — stock_master 0건 race 자동 재시도 hook.
        6/18 08:24:24 운영 사고 영역 영구 차단 (cap 3회 + sleep 30초). 사이클 158 VB 패턴 답습.
        """
        import asyncio

        # 사이클 173 (2026-06-22) — 일봉 source KIS → DB 어댑터 전환 (행위 보존).
        from src.db.stock_master_daily import get_recent_daily_normalized

        # 사이클 21 — 매 prepare 마다 카운트 초기화
        stats = _empty_scan_stats()
        self._scan_stats = stats
        # 사이클 143 — 단계별 ticker 캡처 reset (사이클 39 답습)
        self._reset_funnel_steps(LTV_FUNNEL_STAGES)
        # 사이클 180 — 전일 stale 종목 누적 차단 (장수 싱글톤, prepare 가 유일 rebuild 지점). _limit_up_reached/_next_day_clear_pending 는 청산 모드 경로용이라 절대 미포함.
        self._targets.clear()
        self._open_confirmed.clear()
        self._prev_price.clear()

        # 사이클 163 — stock_master 0건 race 자동 재시도 hook (cap 3회 + sleep 30s).
        # 초기 1회 + 재시도 cap 3회 = 최대 4회 호출 영역.
        tickers = await self._scan_universe()
        for retry_attempt in range(3):
            if tickers:
                break
            logger.warning(
                "[ltv_prepare_retry] stock_master 0건 — %d초 후 재시도 (cap=%d/3)",
                30, retry_attempt + 1,
            )
            await asyncio.sleep(30)
            # 사이클 21 카운트 재초기화 (재시도마다 _scan_universe 가 갱신)
            stats = _empty_scan_stats()
            self._scan_stats = stats
            self._reset_funnel_steps(LTV_FUNNEL_STAGES)
            tickers = await self._scan_universe()
        # 사이클 143 — step 1+2 funnel hook (사이클 140 자문 영속)
        params = self.config.params
        min_mcap_billion = params.get("min_market_cap", 100_000_000_000) / 100_000_000
        min_trade_billion = params.get("min_trade_amount", 20_000_000_000) / 100_000_000
        # step 1: 원천 유니버스 후보 (필터 전) — 사이클 170 카드 C placeholder 제거
        self._record_funnel_pipeline_step(
            LTV_FUNNEL_STAGES[0],
            survived=self._universe_candidate_tickers,
            step_conditions=(
                f"stock_master.list_by_filter 원천 유니버스 후보 ("
                f"limit={params.get('max_scan_stocks', 100)})"
            ),
        )
        # step 2: 시총 + 거래대금 필터 통과
        self._record_funnel_pipeline_step(
            LTV_FUNNEL_STAGES[1],
            survived=tickers,
            step_conditions=(
                f"시총 ≥ {min_mcap_billion:.0f}억 + 거래대금 ≥ {min_trade_billion:.0f}억"
            ),
        )

        # 사이클 157 — step 3: 1단계 진입 차단 13건 (master_raw 7 + raw 6)
        tickers, master_block_excluded = await self._apply_master_block_filter_in_prepare(tickers)
        self._record_funnel_pipeline_step(
            LTV_FUNNEL_STAGES[2],
            survived=tickers,
            step_conditions=(
                "1단계 진입 차단 13건 (거래정지/관리/단기과열/투자유의/공매도과열/이상급등 등)"
            ),
            excluded=master_block_excluded[:20],
        )

        k_period = self.config.params["k_period"]
        consecutive_limit = self.config.params["exclude_consecutive_limit"]
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
                logger.warning("롱테일 일봉 fetch 실패: %s — %s", ticker, e)
                return ticker, None

        fetched = await asyncio.gather(*[_fetch_one(t) for t in tickers])

        # 사이클 21 — 일봉 fetch 성공 카운트
        stats["candle_fetch_ok"] = sum(1 for _, c in fetched if c is not None)

        # 사이클 143 — 단계별 ticker 캡처 (사이클 39+41 답습)
        candle_fetch_ok_tickers: list[str] = []
        range_pass_tickers: list[str] = []
        consecutive_limit_pass_tickers: list[str] = []
        final_prepared_tickers: list[str] = []
        candle_fetch_excluded: list[dict] = []
        range_excluded: list[dict] = []
        consecutive_limit_excluded: list[dict] = []
        target_excluded: list[dict] = []

        for ticker, candles in fetched:
            if candles is None:
                candle_fetch_excluded.append({"ticker": ticker, "reason": "fetch 실패"})
                continue
            candle_fetch_ok_tickers.append(ticker)
            try:
                if len(candles) < 2:
                    continue

                # candles[0]의 거래일이 오늘이면 candles[1]을 "전일"로 사용
                prev_idx = 1 if candles[0].get("stck_bsop_date") == today_str else 0
                if len(candles) <= prev_idx + 1:
                    continue

                # 노이즈 비율 계산 (전일 이전 k_period일)
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
                        "롱테일 prev_range=0 skip: %s (date=%s)",
                        ticker, prev.get("stck_bsop_date"),
                    )
                    continue
                range_pass_tickers.append(ticker)

                # 연속상한가 체크 (전일 기준 최근 N일 연속 +25% 이상이면 제외)
                # 사이클 143 — funnel 영역 영구 영속 단계 5 ↔ 단계 4/6 사이 영역 (도메인 정합 영구 영속)
                if consecutive_limit > 0 and self._is_consecutive_limit_up(
                    candles, consecutive_limit, start=prev_idx,
                ):
                    consecutive_limit_excluded.append({
                        "ticker": ticker,
                        "reason": f"연속 상한가 {consecutive_limit}일 이상",
                    })
                    logger.debug("연속상한가 제외: %s (%d일 이상)", ticker, consecutive_limit)
                    continue
                # 사이클 21 — 연속상한가 통과 카운트 (탈락 종목은 미증가)
                stats["consecutive_limit_pass"] += 1
                consecutive_limit_pass_tickers.append(ticker)

                target_offset = int(prev_range * k)
                if target_offset <= 0:
                    target_excluded.append({
                        "ticker": ticker,
                        "reason": f"target_offset={target_offset} ≤ 0 (k={k:.4f})",
                    })
                    logger.debug(
                        "롱테일 target_offset=0 skip: %s (k=%.4f, range=%d)",
                        ticker, k, prev_range,
                    )
                    continue
                final_prepared_tickers.append(ticker)

                self._targets[ticker] = {
                    "k": round(k, 4),
                    "prev_range": prev_range,
                    "target_offset_base": target_offset,
                    # backwards-compat
                    "target_offset": target_offset,
                    "target_price": 0,
                    "open_price": 0,
                    # 보드별 시가/타겟 (Phase 5)
                    "boards": {},
                }
                self._open_confirmed[ticker] = {}

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
        # 사이클 21 — K값/최종 카운트 + last_run_at
        stats["k_value_computed"] = prepared
        stats["final_prepared"] = len(self._scanned_tickers)
        stats["last_run_at"] = datetime.now(KST).isoformat()

        # 사이클 143 + 157 — step 4+5+6+7 funnel hook (사이클 157 step 3 master block 후 인덱스 +1)
        self._record_funnel_pipeline_step(
            LTV_FUNNEL_STAGES[3],
            survived=candle_fetch_ok_tickers,
            step_conditions=f"KIS fetch_daily_candles 정상 응답 ({k_period}일)",
            excluded=candle_fetch_excluded,
        )
        self._record_funnel_pipeline_step(
            LTV_FUNNEL_STAGES[4],
            survived=range_pass_tickers,
            step_conditions="전일 Range > 0 + noise 영역 계산 통과",
            excluded=range_excluded,
        )
        self._record_funnel_pipeline_step(
            LTV_FUNNEL_STAGES[5],
            survived=consecutive_limit_pass_tickers,
            step_conditions=f"연속 상한가 {consecutive_limit}일 미만 통과",
            excluded=consecutive_limit_excluded,
        )
        self._record_funnel_pipeline_step(
            LTV_FUNNEL_STAGES[6],
            survived=final_prepared_tickers,
            step_conditions="K값 노이즈 비율 + target_offset > 0",
            excluded=target_excluded,
        )

        logger.info("롱테일 변동성 돌파 준비 완료: %d/%d종목", prepared, len(tickers))

    @staticmethod
    def _is_consecutive_limit_up(candles: list[dict], threshold: int, start: int = 0) -> bool:
        """start 인덱스부터 N일 연속 상한가(+25% 이상) 여부를 판별한다.

        start는 "전일"을 가리키는 인덱스(보통 0 또는 1). 오늘 부분봉이 [0]에 끼면 start=1로 호출.
        """
        if start >= len(candles):
            return False
        count = 0
        for c in candles[start : start + threshold]:
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
        """stock_master DB 기반으로 시총·거래대금 조건 종목을 스캔한다 (사이클 108).

        사이클 108 (Plan Phase A) — 사전 적재된 stock_master (~2,800종목,
        사이클 101/106 _full_universe_load_task_loop) 를 DB 필터링으로 대체한다.
        LTV 전용 consecutive_limit_pass 카운터는 prepare() 에서 관리하므로
        _scan_universe 는 VB 와 동일 구조로 단순화한다.
        KIS API 직접 호출 0건.
        """
        from src.db import stock_master as _sm_mod
        from src.engine.scanner import ETF_KEYWORDS, ticker_names

        min_mcap = self.config.params.get("min_market_cap", 100_000_000_000)
        min_trade = self.config.params.get("min_trade_amount", 20_000_000_000)
        max_stocks = self.config.params.get("max_scan_stocks", 100)

        # 사이클 156 Q0 — nxt_tradable 강제 필터 제거 (주문 시점 분기용으로만 활용).
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

        logger.info(
            "롱테일 변동성 돌파 유니버스 확정: %d/%d종목 (stock_master DB, 시총 %d억+, 거래대금 %d억+)",
            len(filtered), len(rows), min_mcap // 100_000_000, min_trade // 100_000_000,
        )
        # 사이클 21 — universe 필터 통과
        self._scan_stats["universe_filtered"] = len(filtered)

        if not filtered:
            from src.db.system_logs import write_log

            msg = (
                f"롱테일 변동성 돌파 유니버스 0종목 — stock_master {len(rows)}건 중 "
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

        # 사이클 170 카드 C — 원천 유니버스 후보 보관 (funnel step1 노출)
        self._universe_candidate_tickers = list(filtered)

        return filtered

    _PREPARE_LOG_LABEL = "ltv"  # refactor-review A1·A2 — base 위임 로그 접두사
    _COOLDOWN_LOG_LABEL = "[ltv]"  # refactor-review A3 — base 위임 로그 접두사

    def get_scanned_tickers(self) -> list[str]:
        """스캔된 종목 리스트를 반환한다 (WebSocket 구독용)."""
        return self._scanned_tickers

    def get_scan_stats(self) -> dict:
        """사이클 21 — 단계별 스캔 통계 (ScanMonitor 깔때기).

        donchian_swing.get_scan_stats() 와 동일 시그니처.
        외부 수정 격리를 위해 사본 반환.
        """
        return dict(self._scan_stats)

    def get_targets_status(self) -> dict[str, dict]:
        """종목별 타겟 가격 정보 (활성 보드 필터링 — VB와 동일 형식 + `limit_up_reached`).

        2026-05-13 작업 1: 활성 보드(`session_tracker.active`) ∩ 전략 `tradable_boards` 에
        속하는 보드만 노출. 교집합 공집합 → `boards={}` + top-level 0. session 모듈
        장애 시 fallback → 모든 보드 노출 (외부 호환 + 운영자 시야 보존).
        `limit_up_reached` 키는 필터링과 무관하게 항상 보존.
        """
        # 활성 보드 ∩ tradable_boards = 노출 보드 집합
        visible: set[str] | None
        try:
            from src.engine.session import session_tracker, parse_tradable_boards

            active = session_tracker.active  # frozenset[MarketBoard]
            tradable_raw = self.config.params.get("tradable_boards")
            tradable = parse_tradable_boards(tradable_raw) if tradable_raw else None
            if not tradable:
                tradable = parse_tradable_boards(list(self.DEFAULT_TRADABLE_BOARDS))
            visible = {b.value for b in (active & tradable)}
        except Exception:
            visible = None

        _BOARD_PRIORITY = ("main", "post_nxt", "pre_nxt")

        result = {}
        for ticker, info in self._targets.items():
            board_states = self._open_confirmed.get(ticker, {})
            all_boards = info.get("boards", {})
            limit_up = ticker in self._limit_up_reached

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
                    "limit_up_reached": limit_up,
                    "boards": exposed_boards,
                    "open_confirmed": board_states,
                }
                continue

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
                result[ticker] = {
                    "k": info.get("k", 0),
                    "target_price": 0,
                    "open_price": 0,
                    "target_offset": 0,
                    "limit_up_reached": limit_up,
                    "boards": {},
                    "open_confirmed": {},
                }
                continue

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
            top = exposed_boards[top_board] if top_board else {}

            result[ticker] = {
                "k": info.get("k", 0),
                "target_price": top.get("target_price", 0),
                "open_price": top.get("open_price", 0),
                "target_offset": top.get("target_offset", 0),
                "limit_up_reached": limit_up,
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
        from src.engine.session import session_tracker, MarketBoard

        active = session_tracker.active
        if not active:
            return None
        allowed = self.config.params.get("tradable_boards") or list(self.DEFAULT_TRADABLE_BOARDS)
        for candidate in ("main", "post_nxt", "pre_nxt"):
            if candidate in allowed and MarketBoard(candidate) in active:
                return candidate
        return None

    def _main_buy_cutoff_blocked(self, board: str, now: datetime) -> bool:
        """`main` 보드 신규 매수 컷 판정 (cycle286 C2-a).

        `main` 이외 보드(`pre_nxt`/`post_nxt`)와 컷 이전 시각은 항상 `False` —
        `post_nxt`(15:40~19:50) 야간 매수·`pre_nxt`(08:00~08:50) 프리장 매수는
        스코프 밖이다. `now` 는 호출부가 이미 들고 있는 tz-aware KST 를 그대로
        받는다(헬퍼가 스스로 시계를 읽지 않는다 — cycle262 `G-262-4` 동형 계약).
        """
        from src.engine.session import MarketBoard

        return board == MarketBoard.MAIN.value and now.time() >= MAIN_BUY_CUTOFF_KST

    def on_open_price_confirmed(
        self, ticker: str, open_price: int, board: str = "main", *, source: str = "ws",
    ) -> None:
        """보드별 시가 확정 + Target 계산.

        cycle272 (2026-09-10) — VB `on_open_price_confirmed` 와 동형(상호
        import 금지, 각자의 `DEFAULT_PARAMS["open_price_scope_mode"]` 가
        부분 롤백 독립성을 보장한다). `source` 기본값이 불신 `"ws"` 라
        `check_buy_signal`/`check_exit_signal`/`calc_buy_quantity` 는 한 글자도
        안 바뀐다(cycle264 `_STRATEGY_PINS` 6개 불변).
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
        if not info.get("open_price"):
            info["open_price"] = open_price
            info["target_price"] = open_price + target_offset
            info["target_offset"] = target_offset

    def check_buy_signal(
        self, ticker: str, current_price: int, open_price: int,
    ) -> Signal:
        """현재 활성 보드의 Target Price 돌파 시 매수."""
        # cycle233 — 계좌 SOFT Σ상한 순간 게이트 (다크런치·fail-open, 신규 매수만)
        # ⚠️ **`check_buy_signal` 의 첫 문장이 계약**이다(cycle233 M6 — LTV 는
        # `GATE_FIRST_FILES` 멤버, AST 가드
        # `test_cycle233_ast_account_risk.py::test_gate_first_strategies_have_gate_as_first_statement`).
        # 부작용(로그 emit 포함)·상태 갱신은 **이 게이트 뒤**에 온다. cycle262 적대
        # 검증이 "카나리아를 게이트 앞으로" 권고했으나 그 이동은 이 가드를 RED 로
        # 만든다 — 게이트 활성일에 LTV config 카나리아가 0행인 것은 **알려진 한계**로
        # 문서화했다(`_workspace/00_leader_trading_rules.md` §5 · 후속 티켓 F-6).
        if self._account_soft_gate_blocked(ticker):
            return Signal.NONE
        # cycle262 — 09:00 직후 진입 보류. 여기서는 **읽고 관측만** 한다 (차단 판정은
        # 아래 발사점). 카나리아를 발사점에 두면 돌파가 없는 날 한 줄도 안 남아
        # '보류가 조용히 꺼진' 상태를 볼 수 없다(자문 §2.5 침묵 차단) — 그래서
        # 카나리아(매 평가)와 판정(발사점)을 일부러 분리했다. 계좌 게이트가 이
        # 전략에선 함수 최상단이라(cycle233 M6) 배치가 VB 와 다르다.
        _now_kst = datetime.now(KST)
        _hold_secs = self._read_open_entry_hold_secs()
        self._emit_open_entry_hold_config(_hold_secs, _now_kst)
        from src.engine.scanner import t, ticker_names, ticker_prev_close

        if self.state.buy_disabled:
            return Signal.NONE
        if self.state.has_position(ticker) or self.state.is_buy_pending(ticker) or self.state.is_sold_today(ticker):
            return Signal.NONE

        # 사이클 213 — 재진입 쿨다운 (청산 후 2영업일, VB 사이클 201 패턴 답습)
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

        confirmed = self._open_confirmed.get(ticker, {}).get(board, False)
        if not confirmed and open_price > 0:
            self.on_open_price_confirmed(ticker, open_price, board=board)

        board_info = info.get("boards", {}).get(board)
        if not board_info:
            return Signal.NONE

        target = board_info.get("target_price", 0)
        if target <= 0:
            return Signal.NONE

        # 전일대비 등락률 필터 (보드 무관)
        prev_close = ticker_prev_close.get(ticker, 0)
        if prev_close > 0:
            prdy_rate = (current_price - prev_close) / prev_close * 100
            min_rate = self.config.params["min_prdy_rate"]
            if prdy_rate < min_rate:
                return Signal.NONE

        prev = self._prev_price.setdefault(ticker, {}).get(board, 0)
        self._prev_price[ticker][board] = current_price

        if prev == 0:
            return Signal.NONE

        # 돌파 순간 감지
        if prev < target and current_price >= target:
            # cycle262 — 09:00 직후 N초 진입 보류 (기준가 오염 지혈, 자문 §2.3).
            # **이 자리가 계약이다.** 최상단으로 올리면 (a) 보류 구간 동안
            # `_prev_price` baseline 이 동결돼 해제 후 첫 틱이 stale baseline 대비
            # 거짓 돌파로 읽히고(cycle233 C233-F1) (b) 목표가도 baseline 도 안 잡혀
            # **무엇을 살 뻔했는지**를 기록할 수 없다 = 결함의 증거를 스스로 지운다.
            # baseline 은 위에서 이미 갱신됐고 여기서는 신호만 막는다.
            # 보드로 분기하지 않는다(시간창 단독) — 09:00:00~09:00:30 은 세션 트래커
            # 30초 주기 탓에 보드가 아직 pre_nxt 로 잡힐 수 있는데 그건 설계 의도가
            # 아니라 stale 캐시 산물이라, 보드로 나누면 그 30초가 통째로 구멍이 된다.
            # 08:00~09:00 진짜 프리장 매수는 창 밖이라 **무접촉**이다.
            _hold_elapsed = self._open_entry_hold_elapsed(_now_kst, _hold_secs)
            if _hold_elapsed is not None:
                # 관측은 **행위 밖**이다 — emit 이 어떻게 터지든 아래 return 은 그대로
                # 수행된다(관측 예외가 check_buy_signal 을 뚫으면 risk.on_tick 이 그
                # 종목의 나머지 평가를 잃는다, cycle237 TE-2).
                try:
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

            # cycle286 (C2-a) — `main` 보드 15:20 신규 매수 컷. **이 자리가 계약이다.**
            # 최상단은 불가(계좌 SOFT 게이트가 첫 문장 — cycle233 M6)이고, board 해소
            # 뒤여야 보드 스코프가 성립하며, baseline 갱신 뒤여야 동결이 없다
            # (cycle233 C233-F1). 발사점이라야 **무엇을 살 뻔했는지**가 남는다.
            # cycle262 hold 블록과 창이 서로소(09:00~09:01:30 vs ≥15:20)라 순서 무관.
            if self._main_buy_cutoff_blocked(board, _now_kst):
                try:
                    _key = ticker or "-"
                    if self._main_buy_cutoff_logged.should_emit(_key, now=_now_kst):
                        logger.info(
                            "[ltv_main_buy_cutoff] ticker=%s board=%s cutoff=%s "
                            "now=%s current_price=%d target=%d board_open=%d prev=%d "
                            "k=%.4f offset=%d prdy_close=%d "
                            "note='15:20 이후 신규 매수 차단 — would_buy 정본 "
                            "(연속체결 종료·종가단일가 체결은 진입 대상이 아니다)'",
                            _key, board, MAIN_BUY_CUTOFF_KST.strftime("%H:%M"),
                            # 적대 검증 LOW-3(behavior) — 자매 마커 `[nxt_post_reinforce]`
                            # 는 `now=` 를 싣는데 이 마커는 상수 `cutoff=` 뿐이라
                            # "now>=15:20" 을 행마다 기계 판독할 수 없었다. 로그
                            # prefix 타임스탬프로 유도 가능했으나 grep 정합을 위해
                            # 명시 필드로 병기한다.
                            _now_kst.strftime("%H:%M:%S"),
                            current_price, target,
                            int(board_info.get("open_price", 0) or 0), prev,
                            float(info.get("k") or 0),
                            int(board_info.get("target_offset", 0) or 0),
                            int(ticker_prev_close.get(ticker, 0) or 0),
                        )
                        self._main_buy_cutoff_logged.mark_emitted(_key, now=_now_kst)
                except Exception:
                    try:
                        trace_observer_failure(
                            "[ltv_main_buy_cutoff]", ticker or "-",
                            self._main_buy_cutoff_logged, dest_logger=logger,
                        )
                    except Exception:  # pragma: no cover — 2차 예외까지 흡수
                        pass
                return Signal.NONE

            board_open = board_info.get("open_price", 0)
            change_rate = round((current_price - board_open) / board_open * 100, 1) if board_open > 0 else 0
            logger.info(
                "롱테일 변동성 돌파 매수 신호 [%s]: %s 현재가(%d) >= 목표가(%d), K=%.4f",
                board, t(ticker), current_price, target, info["k"],
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

    # ────────── cycle352 — 15:20 상한가 유지 확인 (`limit_up_close_hold_mode`) ──────────
    #
    # 실측 = `_workspace/domain_consult/cycle352_ltv_limit_up_trailing.md`. 상한가
    # 모드 종목이 15:20 시점에 `limit_up_threshold` 아래로 되밀렸으면 그날 종가
    # 부근(15:20 강제청산 경로)에서 판다 — 밤을 넘길 자격(강한 마감)을 잃었다고
    # 보는 것이다. 한 번 찍고 풀린 뒤에도 `limit_up_threshold` 이상을 유지 중이면
    # 그대로 보유(현행 익일청산 경로).

    def _read_limit_up_close_hold_mode(self) -> str:
        """`limit_up_close_hold_mode` 읽기 — `"off"` 만 롤백, 그 외 전부 enforce.

        `open_price_scope_mode` 와 같은 규약(대소문자·앞뒤 공백 무시 정확 일치만
        `off`) — 부재·비문자열·오타·예외는 전부 `enforce` 다(배포 즉시 켜진다).
        """
        try:
            raw = self.config.params.get("limit_up_close_hold_mode", "enforce")
            if isinstance(raw, str) and raw.strip().lower() == "off":
                return "off"
        except Exception:
            pass
        return "enforce"

    def _emit_limit_up_close_config(
        self, mode: str, threshold: float, limit_up_same_day: int,
    ) -> None:
        """`[ltv_limit_up_close_config]` — 하루 1회, 보유 0 에서도 발화."""
        self._limit_up_close_config_logged.emit_once(
            "cfg",
            logger.info,
            "[ltv_limit_up_close_config] mode=%s threshold=%.1f limit_up_same_day=%d",
            mode, threshold, limit_up_same_day,
        )

    def _emit_limit_up_close_decision(
        self, ticker: str, decision: str, threshold: float,
        prdy: float | None, price: int | None, prev_close: int | None,
        tick_age_s: int | None, reason: str,
    ) -> None:
        """`[ltv_limit_up_close_decision]` — 상한가 모드 당일 종목마다 1행."""
        self._limit_up_close_decision_logged.emit_once(
            f"decision|{ticker}",
            logger.info,
            "[ltv_limit_up_close_decision] ticker=%s decision=%s prdy=%s "
            "threshold=%.1f price=%s prev_close=%s tick_age_s=%s reason=%s",
            ticker, decision,
            f"{prdy:.2f}" if prdy is not None else "-",
            threshold,
            price if price is not None else "-",
            prev_close if prev_close is not None else "-",
            tick_age_s if tick_age_s is not None else "-",
            reason,
        )

    def _evaluate_limit_up_close_hold(
        self, ticker: str, threshold: float,
    ) -> tuple[str, str, float | None, int | None, int | None, int | None]:
        """가격 조회 + 판정. 반환 = (decision, reason, prdy, price, prev_close, tick_age_s).

        decision ∈ `exit|hold|hold_unknown`. **판정 불가면 보유**(가격 없음·0
        이하·전일종가 없음·예외) — 잠긴 상한가는 체결이 드물어 틱이 오래될 수
        있는데 그때 마지막 가격은 상한가라 보유가 맞다. 신선도 게이트는 두지
        않고 `tick_age_s` 로 나이만 남긴다. **전체가 try/except 안**이라
        never-raise 다 — 이 함수가 던지면 안 된다(호출부가 여러 종목을
        순회하므로 한 종목의 실패가 나머지 종목 판정을 막으면 안 된다).
        """
        try:
            from src.engine.scanner import ticker_prices, ticker_prev_close, ticker_last_tick

            tick_age_s: int | None = None
            try:
                last_tick = ticker_last_tick.get(ticker)
                if last_tick is not None:
                    tick_age_s = int((datetime.now(KST) - last_tick).total_seconds())
            except Exception:
                tick_age_s = None

            price_info = ticker_prices.get(ticker) or {}
            price = price_info.get("current_price", 0) if isinstance(price_info, dict) else 0
            if not price or price <= 0:
                return "hold_unknown", "no_price", None, (price or 0), None, tick_age_s

            prev_close = ticker_prev_close.get(ticker, 0)
            if not prev_close or prev_close <= 0:
                return "hold_unknown", "no_prev_close", None, price, (prev_close or 0), tick_age_s

            # `risk.on_tick` 의 `prdy_ctrt` 와 같은 반올림(소수 둘째 자리) — 부동소수
            # 표현 오차(`0.29` 는 이진수로 정확히 표현되지 않는다)로 정확히 +29.00%
            # 가 28.999999999999996 이 되어 「경계는 보유(>=)」 계약이 깨지는 것을 막는다.
            prdy = round((price - prev_close) / prev_close * 100, 2)
            if prdy < threshold:
                return "exit", "-", prdy, price, prev_close, tick_age_s
            return "hold", "-", prdy, price, prev_close, tick_age_s
        except Exception:
            return "hold_unknown", "error", None, None, None, None

    def _limit_up_close_hold_extra_clears(self) -> list[str]:
        """상한가 모드 당일 종목 중 15:20 가격이 임계 미만인 종목 목록.

        `check_force_clear` 가 이 메서드 호출을 통째로 `try/except` 로 감싼다 —
        여기가 예외를 던져도 당일 모드 종목의 15:20 청산은 지켜져야 한다.
        """
        try:
            threshold = float(self.config.params.get("limit_up_threshold", 29.0))
        except Exception:
            threshold = 29.0
        mode = self._read_limit_up_close_hold_mode()
        limit_up_same_day = [
            ticker for ticker in self.state.positions
            if ticker in self._limit_up_reached
            and not self.state.positions[ticker].is_next_day
        ]
        self._emit_limit_up_close_config(mode, threshold, len(limit_up_same_day))
        if mode != "enforce":
            return []
        result: list[str] = []
        for ticker in limit_up_same_day:
            decision, reason, prdy, price, prev_close, tick_age_s = (
                self._evaluate_limit_up_close_hold(ticker, threshold)
            )
            self._emit_limit_up_close_decision(
                ticker, decision, threshold, prdy, price, prev_close, tick_age_s, reason,
            )
            if decision == "exit":
                result.append(ticker)
        return result

    def check_force_clear(self) -> list[str]:
        """15:20 강제 청산 대상.

        현행 = 당일 모드(상한가 미도달) 종목 전부. cycle352 추가 = 상한가 모드
        ∧ 당일 매수(`not pos.is_next_day`) ∧ `limit_up_close_hold_mode="enforce"`
        ∧ 15:20 가격의 전일대비 등락률이 `limit_up_threshold` 미만인 종목(그날
        종가 부근에서 판다). 🔴 새 판정은 **never-raise 가 계약**이다 —
        `scheduler._force_clear_main_only` 가 이 메서드를 try 없이 부르므로,
        새 분기가 예외를 던지면 당일 모드 종목까지 15:20 청산을 못 하고 밤을
        넘긴다. 실패하면 현행 목록만 반환한다.
        """
        base = [
            ticker for ticker in self.state.positions
            if ticker not in self._limit_up_reached
        ]
        try:
            extra = self._limit_up_close_hold_extra_clears()
        except Exception:
            extra = []
        return base + extra

    def calc_buy_quantity(self, current_price: int, ticker: str | None = None) -> int:
        """할당 자금의 position_ratio 비중. 예산 잔여로 클램프(`_apply_budget_limit`).

        비중 기준 0주면 관문이 `_fallback_one_share` 로 위임 — 잔여가 1주를 감당하면 1주.
        """
        if current_price <= 0:
            return 0
        ratio = self.config.params["position_ratio"]
        amount = int(self.state.total_investment * ratio)
        return self._apply_budget_limit(amount // current_price, current_price, ticker)
