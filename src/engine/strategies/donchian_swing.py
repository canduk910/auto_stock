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
from datetime import date, datetime, time, timezone, timedelta

from src.engine.daily_emit_cap import KstDailyEmitCap
from src.engine.observer_trace import trace_observer_failure
from src.engine.strategy_base import FunnelStage, Signal, StrategyBase, StrategyConfig

KST = timezone(timedelta(hours=9))

# 사이클 225 J-1 — `_rederive_breakout_high` 가 **호출조차 되지 않은** 사유들.
# 2·3층(`insufficient_prior` / `zero_high`)은 재도출이 돌았으나 미복구인 반면,
# 아래 사유들은 게이트가 falsy 라 함수 진입 자체가 없었다 = 4층. note 문구가 갈린다.
_REDERIVE_NOT_CALLED_REASONS = frozenset(
    {"no_candles", "no_buy_date", "no_position", "not_called"}
)


# 사이클 47 (2026-05-22, refactor-review 카드 #3) — Funnel 단계 정의 모듈 상수.
# step_name 은 정적 — 동적 값 (donchian_period, long_ma_period 등) 은 step_conditions 통해 노출.
FUNNEL_STAGES: tuple[FunnelStage, ...] = (
    FunnelStage(1, "코스피200+코스닥150 합집합"),
    # 사이클 170 카드 A — step2 = 시총+거래대금 컷 통과 (거래대금 attrition 노출).
    # list_by_filter 단일 호출 union→mcap→trade 단계 중 trade (최종 filtered) 노출.
    FunnelStage(2, "시총+거래대금 컷 통과"),
    # 사이클 157 (2026-06-17) — 1단계 진입 차단 13건 step 신규 영구 영속 → 9단계.
    FunnelStage(3, "1단계 진입 차단 13건 통과 (거래정지/관리/단기과열/투자유의 등)"),
    FunnelStage(4, "일봉 fetch + 전일종가>0"),
    FunnelStage(5, "신고가 돌파"),
    FunnelStage(6, "EMA 우상향 + 종가>EMA"),
    FunnelStage(7, "거래대금 평균 대비 통과"),
    FunnelStage(8, "ATR(14) > 0"),
    FunnelStage(9, "최종 후보"),
)


def _empty_scan_stats() -> dict:
    return {
        # 사이클 175 — 코스피200∪코스닥150 합집합 (시총/거래대금 컷 *전* 원천).
        # ScanMonitor "합집합" 단계 = DB funnel step1(union_tickers) 정합.
        "universe_union": 0,
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
        # 2026-07 — 200→400. index 합집합(KOSPI200∪KOSDAQ150)=348 인데 limit=200 이
        # union 쿼리까지 잘라 117종목 누락(실측 자격 317). 400 = 348 전체 커버 + 마진.
        "max_scan_stocks": 400,
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
        # 사이클 209 (2026-07-14) — 0.5(AI 과튜닝)→4.0 복원. 후보=전일 이미 신고가
        # 돌파라 오늘 기준가 위 시작 → 0.5%는 상시 스킵. 4.0≥gap_skip(3.0) 불변식.
        "max_breakout_extension_pct": 4.0,
        # Phase 2A-2 (게이트 1) — 터틀 유닛 sizing opt-in. sizing_mode="turtle" 시
        # sizing(compute_unit_qty)+하드손절(2ATR)이 entry_atr 존재로 원자 결합.
        # 기본 "position_ratio" = 미전환(하드손절 -7%, byte 동일). 정체성 상수 =
        # PARAM_RANGES 미편입 (AI 자동튜닝 제외, 사이클 208/209/212 선례).
        "sizing_mode": "position_ratio",
        "risk_pct": 0.005,        # 유닛당 리스크 = 예산 0.5% (stop_atr 2.0 → 실효 1.0%)
        "stop_atr": 2.0,          # 하드손절 = buy - stop_atr×entry_atr (=atr_trail_mult, dead code 방지)
        "turtle_backstop_pct": -9.0,   # ATR독립 최후 방어 (info=None/재시작/ATR=0, 2ATR보다 넓게)
        "min_vol_floor_pct": 1.0,      # 터틀 sizing 변동성 floor (atr/price<1% → position_ratio fallback)
        "max_lot_units": 2.0,   # cycle242 — 랏당 최대 유닛(K). 터틀 모드 모든 랏 ≤ K유닛, floor(K×u*)==0 이면 미매수. PARAM_RANGES 미편입. 롤백 = DB 20.0
        # P1-A (2026-07-29, 사이클 A) — 레이어드 청산 신규 2키. 전략 정체성 상수 —
        # PARAM_RANGES/INT_PARAMS 미편입 (AI 자동튜닝 제외, 사이클 208/209/212 선례).
        "breakeven_promote_atr": 1.5,   # 고점이 buy+1.5×entry_atr 도달 시 손절선 buy_price 로 승격
        "channel_exit_period": 10,      # 10일 저가 채널 이탈 청산 (0=비활성)
        "max_lot_ratio_mult": 2.5,   # cycle245 — 랏 명목 ρ축 상한(K_ρ). 명목 ≤ K_ρ×position_ratio×예산, 1주도 못 사면 미매수. 터틀 모드에선 K축(max_lot_units)이 우선하고 그것이 fail-open 할 때만 백스톱. PARAM_RANGES 미편입. 롤백 = DB 20.0
    }

    def __init__(self, config: StrategyConfig):
        merged = {**self.DEFAULT_PARAMS, **config.params}
        config.params = merged
        super().__init__(config)
        self._candidates: dict[str, dict] = {}  # ticker -> {prev_close, atr, ...}
        self._scanned_tickers: list[str] = []
        self._bought_today: set[str] = set()  # 당일 진입 시도 종목 (중복 방지)
        # Phase 2A-2 (게이트 1) — 터틀 진입 시점 ATR 스냅샷 (하드손절 = buy - stop_atr×entry_atr).
        # calc_buy_quantity 터틀 분기에서 sizing 과 동일 값으로 스탬프(원자 결합) +
        # recompute_held_atr 가 재시작 시 buy_date 기준으로 재도출(loosen 차단, 영속 대체).
        # 존재 여부가 ATR손절 게이트 = position_ratio 매수는 미스탬프 → % 손절 byte 동일.
        self._entry_atr: dict[str, float] = {}
        # 사이클 23 P2-2 — ticker -> 진입 시 돌파선 (20일 신고가)
        self._breakout_high: dict[str, int] = {}
        # P1-A (2026-07-29, 사이클 A-4) — ticker -> 최근 channel_exit_period 영업일 최저가
        # (당일 제외). recompute_held_atr 가 재도출(재시작/후보이탈 견고성). _entry_atr/
        # _breakout_high 선례 답습 — _candidates 와 독립, on_tick KIS 신규 호출 금지.
        self._channel_low: dict[str, int] = {}
        # 단계별 탈락 통계 — prepare() 실행 시마다 갱신, 프론트 깔때기 시각화용
        self._scan_stats: dict = _empty_scan_stats()
        # 사이클 170 카드 A — list_by_filter 단계별 생존 ticker (관찰성 전용).
        # {"union_tickers", "mcap_tickers", "trade_tickers"} — prepare step1/step2 노출.
        self._scan_stage_counts: dict[str, list[str]] = {}
        # 사이클 223 (S3, 2026-08-21) — KRX 거래일 캐시. 시간청산 `days_held` 를
        # 달력일이 아니라 **영업일**로 세기 위한 유일한 데이터 소스.
        # prepare/recompute_held_atr 가 **이미 fetch 한** 일봉의 거래일로 union 갱신한다
        # (KIS 신규 호출 0 · 종목마다 fetch 창이 달라 와이프 금지).
        # check_exit_signal 은 hot path 라 KIS `add_business_days`(async) 를 쓸 수 없다.
        self._trading_days: set[date] = set()
        # 사이클 223 F4 (2026-08-21) — 거래일 캐시 열화(weekday 폴백) 가시성 cap.
        # 폴백 사실이 **시간청산 발화 시에만** 로그에 남으면, 폴백 상태로 미발화가
        # 계속되는 동안 열화가 영원히 안 보인다(리뷰 F4). 발화 여부와 무관하게
        # 1회/ticker/일 emit 한다. 날짜 키 자기 리셋 — `KstDailyEmitCap`(사이클 258
        # 카드 #4)이 내부에서 KST 롤오버를 자체 처리한다(수동 `_x_day` 필드 소멸).
        self._days_held_fallback_logged: "KstDailyEmitCap[str]" = KstDailyEmitCap[str]()
        # 사이클 224 (2026-08-22) — 시간청산 보유일 **상시 관측** cap.
        # 폴백 cap 과 **별개 필드**여야 한다: 같은 필드를 쓰면 폴백이 선 날 관측이
        # 침묵하고(그 반대도) 서로 다른 두 사실이 한 슬롯을 다툰다(OB-11).
        # 날짜 키 자기 리셋(KstDailyEmitCap 내장).
        self._days_held_observe_logged: "KstDailyEmitCap[str]" = KstDailyEmitCap[str]()
        # 사이클 225 A (2026-08-24) — `recompute_held_atr` 게이트 skip 관측 cap.
        # 사이클 223/224 의 두 cap 과 **별개 필드**여야 한다: 같은 필드를 공유하면
        # 한 사실이 다른 사실을 침묵시킨다(OB-11). 날짜 키 자기 리셋(KstDailyEmitCap 내장).
        self._held_recompute_skip_logged: "KstDailyEmitCap[str]" = KstDailyEmitCap[str]()
        # 사이클 225 B (2026-08-24) — `_rederive_breakout_high` 조용한 실패 사유 cap.
        # 위 A cap 과도 별개 — A(재도출 미호출)와 B(재도출 호출됐으나 미복구)는
        # 서로 다른 사실이라 한 슬롯을 다투면 안 된다.
        self._breakout_high_rederive_skip_logged: "KstDailyEmitCap[str]" = KstDailyEmitCap[str]()
        # 사이클 226 D-1 (2026-08-25) — `prepare()` 돌파선 0 (데이터 품질 사고) cap.
        # 위 네 cap 과 **별개 필드** — 같은 슬롯을 공유하면 한 사실이 다른 사실을
        # 침묵시킨다(OB-11). 날짜 키 자기리셋(`_reset_daily_state` 훅 비의존).
        self._zero_breakout_line_logged: "KstDailyEmitCap[str]" = KstDailyEmitCap[str]()
        # 사이클 237 (2026-09-02) — 청산 계열 **로그 폭주** cap 2종.
        # 실측: `[donchian_breakeven_promote]` 가 08-31 11,453건 / 09-01 9,027건
        # (각각 그날 `system_logs` 의 36.9% / 51.0%, 전부 **단일 종목 192820**).
        # 근본은 래칫 부재다 — kojiro 는 승격 결과를 `_stop_floor` 에 영속해 다음 틱
        # `promoted == eff` 로 자연 1회지만, donchian 은 `base_stop` 을 매 틱
        # `buy - stop_atr×entry_atr` 로 재계산하므로 `promoted != base` 가 **영원히 참**이다.
        # 승격 자체는 매 틱 올바르게 일어난다(결과 동일) — 잘못된 건 로그뿐이다.
        # 시간청산은 신호를 반환하므로 정상 흐름에선 1회지만, 매도가 거부되면
        # (034020 = 프리마켓 APBK0918) 포지션이 살아남아 매 틱 재발화한다.
        # ⚠️ 두 cap 모두 **로그에만** 건다 — 승격 계산과 `return Signal.STOP_LOSS` 는
        # cap 밖이다(cap 이 청산 재시도를 끊으면 관측 시정이 아니라 결함 주입).
        # 위 다섯 cap 과 **별개 필드**(OB-11 — 한 사실이 다른 사실을 침묵시키지 않는다).
        self._breakeven_promote_logged: "KstDailyEmitCap[str]" = KstDailyEmitCap[str]()
        self._time_exit_logged: "KstDailyEmitCap[str]" = KstDailyEmitCap[str]()

    def _emit_breakeven_promote(self, ticker: str, high: int, buy_price: int,
                                mult: float, atr: float, before: int, after: int) -> None:
        """`[donchian_breakeven_promote]` 1회/ticker/일 cap (사이클 237).

        ## 왜

        승격 조건(`high_since_buy ≥ buy + mult×ATR`)은 한 번 참이 되면 그 포지션이
        살아 있는 동안 계속 참이고, donchian 은 승격 결과를 영속하지 않으므로
        `promoted_stop != base_stop` 도 계속 참이다 ⇒ **틱마다 같은 문장**.
        실측 최대 11,453건/일(단일 종목). 승격은 상태 **전이**라 하루 1행이면 족하다.

        ## 계약

        - 호출자는 이 메서드의 성패와 무관하게 `base_stop = promoted_stop` 을 수행한다.
          여기서 무엇이 터져도 손절선 승격은 일어난다.
        - peek → 로그 → mark (cycle226 D-3) — 로그가 던지면 cap 이 소비되지 않아
          그 종목이 종일 봉인되지 않는다.
        - 메시지 서식은 사이클 220 원본과 **byte 동일**(운영 grep 연속성).
        """
        try:
            if not self._breakeven_promote_logged.should_emit(ticker):
                return
            logger.info(
                "[donchian_breakeven_promote] %s 고점(%d) ≥ 매수가(%d)+%.1f×ATR(%d) → 손절선 %d→%d",
                ticker, int(high), int(buy_price), mult,
                int(atr), int(before), int(after),
            )
            self._breakeven_promote_logged.mark_emitted(ticker)
        except Exception:
            # 관측 실패가 승격·손절을 막지 않는다. 흔적은 `observer_trace`(사이클
            # 258 카드 #5 — 옛 `_trace_observer_failure` 메서드를 승격한 모듈
            # 함수)로 — `logger.debug` 단독은 `_DbLogHandler`(INFO 컷)를 못 넘어
            # `system_logs` 에 도달하지 않아 **도입 이전 무음과 구별되지 않는다**
            # (적대 검증 C237-L2-1).
            trace_observer_failure(
                "[donchian_breakeven_promote_failed]", ticker,
                self._breakeven_promote_logged, dest_logger=logger,
            )

    def _emit_time_exit(self, ticker: str, days_held: int, n_days: int,
                        current_price: int, breakout_high: int, suffix: str) -> None:
        """`도치안 시간 기반 청산` 1회/ticker/일 cap (사이클 237).

        ## 왜

        이 로그는 `Signal.STOP_LOSS` 와 짝이라 정상 흐름에선 1회다. 그런데 매도가
        거부되면(프리마켓 시장가 불가 APBK0918 등) 포지션이 그대로 남아 다음 틱에
        같은 분기가 다시 발화한다 — 034020 이 09-02 **08:00:00~08:00:29 사이 67건**을
        찍었다(DB 세션 TZ=Asia/Seoul 실측 확인 — 표기 시각이 곧 KST 다).

        **매도 실패 사실은 클래스별 거부 로그가 기록한다** — 장운영시간 외 WARNING
        (`order_engine` 이 매 거부마다) / 시장가+지정가 폴백 모두 거부 WARNING / 최종 실패
        CRITICAL. **이들에는 cap 이 없다.** `[market_closed_blocked]` 는 그중 *진입 게이트에
        걸린 분*만 찍는 1회/ticker/일 **보조** 신호다(적대 검증 C237-L2-4 — 종전 서술은
        결론은 옳았으나 이유가 부정확했다). 그래서 여기에 cap 을 걸어도 "청산하려 했는데
        못 했다"는 관측은 여러 경로로 그대로 남는다.

        ## ⚠️ 판독법 — 첫 발화 시각이 09:00 이전이면 프리장 게이트 이상 신호

        cap 은 그날 **첫** 발화를 남긴다. donchian 은 `risk._PRE_MARKET_EXIT_EVAL_STRATEGIES`
        화이트리스트 **밖**이라 PRE_NXT 단독 구간에는 청산 평가가 보류돼야 하므로,
        이 로그의 타임스탬프가 09:00 이전이면 그 자체가 게이트 미적용의 증거다.
        실제로 09-02 실측이 그랬다 — 시간청산 첫 발화 **08:00:00** vs
        `[pre_market_exit_deferred] donchian_swing` 첫 발화 **08:00:29** = **~29초 구멍**
        (`_session_loop` 30초 주기라 08:00 정각엔 `active` 에 PRE_NXT 가 아직 없다 →
        게이트가 fail-open). 그 창에서 실제 매도 주문이 나갔고 APBK0918 로 거부됐다.
        **이건 사이클 237 범위 밖의 독립 결함**이었고 **사이클 238 (2026-09-02) 이
        시정**했다(`risk._defers_pre_market_exit` 에 `boards_at` 시각 폴백 OR 결합).
        cap 이 이 신호를 지우지 않는다는 것이 여기 적힌 이유다(버스트 크기는 잃지만
        **시각은 남는다**) — 시정 후에도 09:00 이전 첫 발화는 게이트 회귀의 증거다.

        ## 계약

        - ⚠️ 호출자는 이 메서드 **뒤에서 무조건** `return Signal.STOP_LOSS` 한다.
          cap 이 신호까지 삼키면 매도 거부 후 재시도가 끊겨 포지션이 청산되지 못한
          채 잔존한다 = 매매 결함 주입. cap 은 **로그 전용**이다.
        - peek → 로그 → mark, 예외 흡수 + debug 흔적 (위 헬퍼와 동형).
        - 메시지 서식은 사이클 223 원본과 **byte 동일**.
        """
        try:
            if not self._time_exit_logged.should_emit(ticker):
                return
            logger.info(
                "도치안 시간 기반 청산: %s 보유 %d영업일 ≥ %d, 현재가(%d) < 돌파선(%d)%s",
                ticker, days_held, n_days, current_price, breakout_high, suffix,
            )
            self._time_exit_logged.mark_emitted(ticker)
        except Exception:
            trace_observer_failure(
                "[donchian_time_exit_log_failed]", ticker,
                self._time_exit_logged, dest_logger=logger,
            )

    async def prepare(self) -> None:
        """장 시작 전: 유니버스 스캔 → 종목별 일봉 fetch → 신고가/MA/ATR/거래량 검증."""
        import asyncio

        # 사이클 173 (2026-06-22) — 일봉 source KIS → DB 어댑터 전환 (행위 보존).
        # 신고가/EMA/거래대금 모두 어댑터 candles 단일 source (락 종목 혼재 차단, 자문 §249).
        from src.db.stock_master_daily import get_recent_daily_normalized

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
        # 사이클 170 카드 B — FUNNEL_STAGES 0-시드 (조기반환 시 stale step 잔존 차단)
        self._reset_funnel_steps(FUNNEL_STAGES)

        # 사이클 163 (2026-06-18) — stock_master 0건 race 자동 재시도 hook (cap 3회 + sleep 30s).
        # 6/18 08:24:24 운영 사고 영구 차단 (사이클 158 VB 패턴 답습).
        tickers = await self._scan_universe()
        for retry_attempt in range(3):
            if tickers:
                break
            logger.warning(
                "[donchian_prepare_retry] stock_master 0건 — %d초 후 재시도 (cap=%d/3)",
                30, retry_attempt + 1,
            )
            await asyncio.sleep(30)
            self._candidates = {}
            stats = _empty_scan_stats()
            self._scan_stats = stats
            self._reset_funnel_steps(FUNNEL_STAGES)
            tickers = await self._scan_universe()
        # 사이클 47 (2026-05-22, refactor-review 카드 #3) — FUNNEL_STAGES 위임
        # 사이클 170 카드 A — step1=union (필터 전 원천 유니버스), step2=trade (거래대금컷 후).
        # _scan_stage_counts 가 list_by_filter(return_stage_counts=True) attrition 보관.
        # donchian step1/step2 collapse (둘 다 survived=tickers) 영구 차단.
        min_mcap_billion = params["min_market_cap"] / 100_000_000
        min_trade_billion = params["min_trade_amount"] / 100_000_000
        # getattr 방어 — _scan_universe 가 mock 으로 교체되어 _scan_stage_counts 미설정 시
        # tickers 로 폴백 (관찰성 graceful, 매매 영향 0).
        stage_counts = getattr(self, "_scan_stage_counts", None) or {}
        union_tickers = stage_counts.get("union_tickers", tickers)
        trade_tickers = stage_counts.get("trade_tickers", tickers)
        self._record_funnel_pipeline_step(
            FUNNEL_STAGES[0],
            survived=union_tickers,
            step_conditions="코스피200 + 코스닥150 합집합 (필터 전 원천 유니버스)",
        )
        self._record_funnel_pipeline_step(
            FUNNEL_STAGES[1],
            survived=trade_tickers,
            step_conditions=(
                f"시총 ≥ {min_mcap_billion:.0f}억 + 거래대금 ≥ {min_trade_billion:.0f}억 컷 통과 "
                f"(시총 {len(stage_counts.get('mcap_tickers', tickers))} → "
                f"거래대금 {len(trade_tickers)})"
            ),
        )

        # 사이클 157 — step 3: 1단계 진입 차단 13건 (master_raw 7 + raw 6)
        tickers, master_block_excluded = await self._apply_master_block_filter_in_prepare(tickers)
        self._record_funnel_pipeline_step(
            FUNNEL_STAGES[2],
            survived=tickers,
            step_conditions=(
                "1단계 진입 차단 13건 (거래정지/관리/단기과열/투자유의/공매도과열/이상급등 등)"
            ),
            excluded=master_block_excluded[:20],
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
        # 사이클 173 — DB 우선 어댑터 (락/신선도/부족 시 KIS 폴백). min_required=63 명시
        # (필수 lookback 61 = long_ma 60 + 1, 자문 §4 — 절대 하향 금지 silent 왜곡 차단).
        async def _fetch_one(ticker: str):
            try:
                return ticker, await get_recent_daily_normalized(
                    ticker, days=fetch_days, min_required=63,
                )
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
            # 사이클 223 (S3) — 거래일 캐시 union. 시간청산 영업일 계산 소스이며
            # 이미 fetch 한 일봉을 재사용하므로 KIS 신규 호출 0.
            self._update_trading_days(candles)
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
                # 사이클 173 (2026-06-22) — 신고가 = 어댑터 candles 단일 source.
                #   사이클 123 별도 DB 신고가 헬퍼 호출 폐기 (자문 §249 혼재 차단):
                #   candles 가 이미 어댑터 (DB 우선 + 락/신선도 KIS 폴백) 경유 → candles 의
                #   신고가가 곧 일관된 source. 락 종목은 신고가/EMA 둘 다 KIS (폴백 candles)
                #   → 혼재 영구 차단. 정상 종목은 candles=DB → 사이클 123 신고가 동일 (행위 보존).
                prior_high = max(highs[1: donchian_period + 1])
                # 사이클 226 D-1 (2026-08-25) — 돌파선 0 후보 **거부**.
                # `prior_high == 0` 은 "20일 신고가를 계산하지 못했다" 는 뜻이지
                # "돌파했다" 가 아니다. 그런데 아래 `prev_close <= prior_high` 는
                # 0 을 **아무 양수 종가나 통과**시켜, 돌파를 검증하지 않은 후보를
                # 만든다. 이어서 `check_buy_signal` 이 `info["donchian_high"]` 를
                # 무조건 대입하므로 `_breakout_high[t] = 0` 이 박히고 시간청산이
                # 영구 미발화한다(사이클 225 K-1 이 가리킨 상태의 상류 원인).
                # 도달 경로 = 일봉 고가 결손 row(`_extract_raw` 의 raw 부재 폴백 등).
                # 방향은 **매수를 줄이는 쪽**이다 — 거짓 신호 차단이지 확대가 아니다.
                # ⚠️ 순서 계약 = 기존 `prev_close <= 0` 가드보다 **뒤**. 종가 결손은
                #    지금도 `candle_fetch_ok` 미계상으로 빠지고, 그 사실을 새 마커로
                #    덮으면 "고가 결손" 과 "종가 결손" 이 한 신호로 뭉개진다.
                if prior_high <= 0:
                    # 캡처가 emit **보다 먼저** — 관측기가 터져도 탈락은 남는다.
                    donchian_excluded.append({
                        "ticker": ticker, "name": ticker_name,
                        "reason": (
                            f"직전 {donchian_period}일 신고가 산출 실패 "
                            f"(돌파선 0 — 일봉 고가 결손 의심, 돌파 미검증)"
                        ),
                    })
                    self._emit_zero_breakout_line(
                        ticker, prior_high, prev_close, donchian_period,
                    )
                    continue
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

        # 사이클 47 + 157 — FUNNEL_STAGES 위임 (사이클 157 step 3 master block 후 인덱스 +1).
        # step_name 은 정적 (FUNNEL_STAGES 상수), 동적 파라미터 (donchian_period 등) 는 step_conditions 노출.
        self._record_funnel_pipeline_step(
            FUNNEL_STAGES[3],
            survived=candle_fetch_ok_tickers, excluded=candle_fetch_excluded,
            step_conditions=f"KIS 일봉 ≥ {long_ma_period + 1}일 + 전일 종가 > 0",
        )
        self._record_funnel_pipeline_step(
            FUNNEL_STAGES[4],
            survived=donchian_pass_tickers, excluded=donchian_excluded,
            step_conditions=f"전일 종가 > 직전 {donchian_period}일 최고가",
        )
        self._record_funnel_pipeline_step(
            FUNNEL_STAGES[5],
            survived=ema_uptrend_pass_tickers, excluded=ema_excluded,
            step_conditions=f"{long_ma_period}일 EMA 우상향 + 전일 종가 > EMA",
        )
        self._record_funnel_pipeline_step(
            FUNNEL_STAGES[6],
            survived=volume_pass_tickers, excluded=volume_excluded,
            step_conditions=f"당일 거래대금 ≥ {volume_period}일 평균 × {volume_mult:.1f}",
        )
        self._record_funnel_pipeline_step(
            FUNNEL_STAGES[7],
            survived=atr_pass_tickers, excluded=atr_excluded,
            step_conditions="ATR(14) > 0 (변동성 측정 가능)",
        )
        self._record_funnel_pipeline_step(
            FUNNEL_STAGES[8],
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
            # 사이클 153 — KOSPI200 + KOSDAQ150 합집합 필터 영구 영속 (Q1=A + Q2=A 영속).
            # FUNNEL_STAGES[0] step_name "코스피200+코스닥150 합집합" 영속 의무 정합.
            # 사이클 121 silent 결함 영구 영속 시정 = 인자 부재로 KOSPI200/KOSDAQ150 필터 누락.
            # 사이클 170 카드 A — return_stage_counts=True 로 attrition 노출 (union/mcap/trade).
            rows, stage = await _sm_mod.list_by_filter(
                min_market_cap=min_mcap,
                min_trade_amount=min_trade,
                exclude_tickers=exclude_tickers,
                nxt_tradable=nxt_tradable_param,
                is_kospi200=True,
                is_kosdaq150=True,
                limit=max_stocks,
                return_stage_counts=True,
            )
            self._scan_stage_counts = stage
        except Exception:
            logger.exception(
                "도치안 스윙 stock_master.list_by_filter 호출 실패 graceful — 빈 list 반환"
            )
            self._scan_stats["universe_union"] = 0
            self._scan_stats["universe_candidates"] = 0
            self._scan_stats["universe_filtered"] = 0
            self._scan_stats["last_run_at"] = datetime.now(KST).isoformat()
            self._scan_stage_counts = {}
            return []

        # 사이클 175 — 합집합(union) 노출 (DB funnel step1 정합, ScanMonitor "합집합" 단계)
        self._scan_stats["universe_union"] = len(stage.get("union_tickers", rows))
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

    _PREPARE_LOG_LABEL = "dc"  # refactor-review A1·A2 — base 위임 로그 접두사

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
                # 사이클 225 A (2026-08-24) — 침묵 1층. 이 `continue` 는 fetch **앞**이라
                # 아래 `_rederive_breakout_high` 까지 도달하지 못한다 = 무장 미복구가
                # 아무 흔적 없이 종일 지속된다(실측 192820). 관측 전용 —
                # 호출을 fetch 뒤로 옮기면 매수 당일 종목마다 KIS 일봉 호출이 새로
                # 생긴다(게이트가 fetch 앞에 있는 이유가 그것이다).
                # 발화 조건(무장 여부 = `_breakout_high` **값 > 0**) 판정은 **emitter 내부**
                # try 안에서 한다 — 여기서 읽으면 그 읽기가 try 밖이라 관측이
                # recompute 루프를 죽일 수 있다.
                self._emit_held_recompute_skip(
                    ticker, pos, need_atr, pos_needs_high_recover,
                )
                continue

            try:
                candles = await fetch_daily_candles(ticker, days=fetch_days)
            except Exception:
                logger.exception("도치안 스윙 보유종목 일봉 fetch 실패: %s", ticker)
                continue

            # 사이클 223 (S3) — 거래일 캐시 union (`_trading_days`). prepare 가 후보
            # 종목만 훑는 데 반해 여기는 보유 종목이라, 둘을 합쳐야 매수일까지 닿는다.
            self._update_trading_days(candles)

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

            # P1-A (2026-07-29, A-2) — _breakout_high 재도출 (재시작 후 보유 종목 소실 복구).
            # 시간 기반 청산(check_exit_signal 2.5) 의 breakout_high 기준선이 재시작으로
            # 소실되면 분기가 영구 침묵 — buy_date 이전 20일 신고가로 재현. 이미 fetch한
            # candles 재사용 (KIS 신규 호출 0). in-memory 무장(당일 매수 미재시작) 시 미접촉.
            #
            # 사이클 226 D-2 (2026-08-25) — 진입 게이트를 **멤버십 → 값 기준**으로.
            # `ticker not in self._breakout_high` 는 `_breakout_high[t] == 0` 을
            # "무장됨" 으로 판정해 복구를 **시도조차 하지 않았다**. 그런데 시간청산
            # 게이트(`check_exit_signal` §2.5 의 `breakout_high > 0`)와 사이클 224/225
            # 관측기는 전부 **값**으로 본다 — 이 게이트만 멤버십이라 값 0 포지션이
            # 영구 미복구로 남았다(= 시간청산 영구 미발화). 값 0 의 도달 경로는
            # 고가 결손 일봉으로 만들어진 후보이며, 상류는 사이클 226 D-1 이 막았다.
            # ⚠️ 이건 **복구 전용** 변경이다 — 매수를 만들지 않고 0(무효)을 실제 값으로
            #    되돌릴 뿐이며, fetch 는 게이트 **앞**에서 이미 일어나므로 호출 횟수도
            #    불변이다. 무장값(>0)은 여전히 미접촉(loosen 금지).
            # ⚠️ L-2 — `int(...)` 를 여기서 부르면 **try 밖 예외 지점**이 새로 생긴다.
            #    이 루프에서 try 로 감싼 것은 fetch 하나뿐이라, 여기서 던지면
            #    뒤 보유 종목의 `_channel_low`·`_entry_atr`·고점 보정이 통째로
            #    유실돼 **청산 분기가 조용히 약해진다**. `isinstance` 는 던지지 않는다.
            #    (현행 writer 2곳이 모두 int 를 넣어 도달 불가하나, 같은 파일이
            #     "관측·판정이 루프를 죽여 뒤 종목 복구를 유실시키는 것" 을 1급
            #     위험으로 반복해 다뤄왔으므로 같은 기준을 여기에도 적용한다.)
            _bh_raw = self._breakout_high.get(ticker, 0)
            _armed = _bh_raw if isinstance(_bh_raw, int) else 0
            if (
                pos and pos.buy_date and candles
                and not _armed
            ):
                self._rederive_breakout_high(ticker, pos, candles, params["donchian_period"])
            else:
                # 사이클 225 J-1 (2026-08-24) — **침묵 4층**. 이 게이트가 falsy 면
                # `_rederive_breakout_high` 가 **호출조차 되지 않아** 2·3층 로그(B)가
                # 안 찍히고, 이 지점은 이미 상위 게이트(`need_atr`/`needs_high_recover`)
                # 를 통과한 뒤라 1층 로그(A)도 없다 ⇒ **완전 무음**.
                # ⚠️ 여기엔 A 의 '자가 치유' 논증이 성립하지 않는다 — 상위 게이트를
                # 통과했다는 건 `buy_date < today`(또는 후보 이탈)라는 뜻이라 `days_held`
                # 가 계속 자라 `breakout_fail_n_days` 를 넘기는데, 시간청산은
                # `breakout_high > 0` 에 막혀 **영구 미발화**한다.
                # 실측 경로: `fetch_daily_candles` 는 KIS `rt_cd=0` + 빈 `output2` 시
                # 예외 없이 `[]` 를 돌려주고 그 `[]` 를 5분 TTL 캐시에 저장한다
                # (`src/api/condition.py`) ⇒ `candles` falsy 가 조용히 반복된다.
                # 관측 전용 — 재도출을 억지로 호출하지 않는다(행위 변경 0). 사유 판정과
                # 무장 여부 확인은 **emitter 내부 try** 에서 한다(A 의 C-12a 계약 동형).
                self._emit_breakout_high_rederive_not_called(ticker, pos, candles)

            # P1-A (2026-07-29, A-4) — _channel_low 산출 (10일 채널 청산 데이터 소스).
            # _candidates 와 독립 dict — 후보 이탈/재시작 후에도 견고. on_tick KIS 호출
            # 금지 — 여기서 이미 fetch 한 candles 재사용.
            channel_period = int(params.get("channel_exit_period", 0) or 0)
            if pos and candles and channel_period > 0:
                self._recompute_channel_low(ticker, candles, channel_period)

            # Phase 2A-2 (게이트 1) — 터틀 entry_atr 재도출 (재시작 복구).
            # 진입 시점(buy_date 이전) ATR 재현 → 현재 팽창 ATR 로 손절선 loosen 차단.
            # in-memory _entry_atr 존재(당일 매수 미재시작) 시 미접촉 = 정확 스탬프 보존.
            if (
                params.get("sizing_mode") == "turtle" and pos and pos.buy_date
                and ticker not in self._entry_atr and candles
            ):
                self._rederive_entry_atr(ticker, pos, candles, atr_period)

    def _update_trading_days(self, candles: list) -> None:
        """이미 fetch 한 일봉의 거래일을 `_trading_days` 캐시에 **union** 한다.

        사이클 223 (S3). KIS 신규 호출 0 — `_breakout_high`/`_channel_low` 재도출과
        같은 candles 를 재사용한다. 날짜 추출은 `StrategyBase._candle_trade_date` 위임
        (KIS 원본 `stck_bsop_date` / 정규화 컬럼 `bas_dd` 양쪽 수용 — 어댑터가 raw JSONB
        없는 row 를 row 자체로 돌려주는 경로 대응. 3번째 파서 복사본 금지).

        종목마다 fetch 창이 다르므로 **와이프 금지** — 합집합이어야 휴장일 판별이 는다.
        """
        if not candles:
            return
        for c in candles:
            try:
                bd = self._candle_trade_date(c)
            except Exception:
                continue
            if bd is not None:
                self._trading_days.add(bd)

    @staticmethod
    def _prev_weekday(d: date) -> date:
        """`d` **직전**의 weekday(월~금). 최대 3회 순회 — hot path 안전.

        사이클 223 F1/G/G2. 쓰임은 **`used_fallback` 판정 하나뿐**이다 — 계상에는
        관여하지 않는다(G 에서 갭 메움을 걷어냈다). 공휴일 달력이 없으므로 weekday
        근사이고, 그래서 **양방향으로 틀린다**. 사이클 223 G2 이전 이 docstring 은
        오탐 한쪽만 인정하고 "한 방향" 이라고 적었는데, 그 주장은 **거짓**이었다.

        **오탐(false positive) — 값은 맞고 로그만 한 줄 더**
          직전 weekday 가 공휴일이면 캐시에 없는 게 정상인데도 플래그가 선다. 값은
          그 경우에도 정확하다(갭 = 오늘 하루 → 휴장일 미계상). **연 12~15회 캘린더
          이벤트**(설·추석·개천절·한글날·성탄절 직후 첫 거래일)에서 예정된 것이고,
          운영자는 로그의 `cached_days`/`cache_max` 로 진짜 열화와 구분한다.
          = 정당한 신호.

        **거짓 음성(false negative) — 값이 틀린데 플래그가 안 선다** (실재 2경로)
          1. `today` 자신이 **평일 공휴일**일 때: `cache_max == _prev_weekday(today)`
             라 플래그 False 인데, 갭 보정 `+1` 이 그 휴장일을 세어 **과다** 계상된다.
             (주말 `today` 는 사이클 223 G1 이 `today.weekday() < 5` 가드로 막았고,
             평일 공휴일은 달력 없이 코드로 가를 수 없다.)
          2. 저녁 구간(15:40~20:00): 16:20 funnel prepare 가 **오늘 봉**을 캐시에
             넣으므로 `cache_max == today` 가 되어, 캐시 **중간 결손**이 있어도
             플래그가 서지 않는다. 값은 과소(= 청산 지연 = 보유 연장, 안전 방향).

        즉 이 플래그는 "캐시가 직전 weekday 까지 닿았다"는 **필요조건 관찰**일 뿐
        정확성 보증이 아니다. 플래그 False 를 "값이 맞다"로 읽지 말 것.
        """
        cur = d - timedelta(days=1)
        while cur.weekday() >= 5:
            cur -= timedelta(days=1)
        return cur

    def _business_days_held(self, buy_date: date, today: date) -> tuple[int, bool]:
        """매수일 이후 경과 **영업일** 수. 반환 `(일수, 폴백_사용_여부)`.

        사이클 223 (S3). ⚠️ **동기 순수함수 · I/O 0** — `check_exit_signal` 은
        `risk.on_tick` 이 초당 수십~수백 회 호출하는 hot path 라 신규 `await`/DB/HTTP 가
        금지된다. `StrategyBase._refine_cooldown_business_days` 가 쓰는 KIS 영업일
        조회 TR(CTCA0903R) 래퍼는 async 라 여기서 호출할 수 없다 — 그래서 캐시를 쓴다.
        (그 헬퍼 이름을 여기 적지 않는 것도 계약이다: AST 가드 G-223-6 이
        `check_exit_signal`/`_business_days_held` 본문의 I/O 심볼 유입을 문자열로 검사한다.)

        ## 산식 (사이클 223 G — F1 일반화 철회 + 가시성 유지)

            cache_max = max(cache)
            held = |{d ∈ cache : buy_date < d ≤ today}|              # 캐시가 정본
                 + (1 if today > buy_date and today ∉ cache          # 갭 기여는
                        and today.weekday() < 5 else 0)              #  **오늘 하루**
            used_fallback = cache_max < _prev_weekday(today)         # 가시성 전용

        **왜 갭을 오늘 하루로 한정하는가.** 이 함수가 평가되는 시점은 통상 활성
        세션이다(`on_tick` = 시세 수신 중, `_swing_rest_poll_loop` = 09:30~15:20 창)
        — 즉 **오늘이 영업일이라고 가정**한다. ⚠️ 사이클 223 G2 — 이것은 **보장이
        아니라 가정**이다. 깨지는 실제 경로가 둘 있다:

          1. `routes/trading.py` 의 `POST /api/trading/start` · `/restart` 에 휴장·주말
             가드가 없다(`run_daily` 의 skip 은 자동 경로 전용). 수동 시작하면 폴 루프가
             `datetime.now().time()` 만 보고 날짜는 안 봐서 주말·휴장에도 돈다.
          2. `scheduler.py` 의 `except Exception: "휴장일 체크 실패 — 영업일로 가정하고
             진행"` fail-open.

        전제가 깨질 때 오차의 방향은 **과다 계상 = 조기 청산**(이 사이클이 가장 비싸다고
        규정한 방향)이라, 코드로 가를 수 있는 절반은 막았다 — 주말은 `today.weekday() < 5`
        가드로 배제한다(사이클 223 G1: 없으면 전면 폴백 분기와 **같은 함수 안에서 달력이
        갈린다**). 평일 공휴일은 달력 없이 불가하므로 잔여 오차로 남으며, 그 크기는
        **하루(+1)** 이고 `used_fallback` 플래그는 이 경우 서지 않는다(`_prev_weekday`
        docstring 의 거짓 음성 #1).

        한편 `cache_max` 와 `today` **사이의 나머지 날들**은 휴장인지 스테일인지
        구분할 수 없어 애초에 세지 않는다. 그리고 라이브 세션 중
        `cache_max` 는 구조적으로 직전 거래일이다: `_update_trading_days` 호출부가
        `prepare`(부팅·개장 전) 와 `recompute_held_atr`(부팅/저녁) 뿐이라 장중엔
        오늘 봉이 캐시에 없다. 따라서 갭이 벌어졌다면 **원인은 대개 휴장**이다.

        F1 은 그 갭을 weekday 로 메웠고, 그것은 "갭의 원인은 항상 스테일"이라는
        가정이었다. 공휴일 다음 첫 거래일마다 휴장일을 영업일로 세어 **과다 계상**한다:

            금 08-14 공휴일 → 월 08-17      : 메움 5   진실 4   (+1)
            월 08-17 공휴일 → 화 08-18      : 메움 5   진실 4   (+1)
            연휴 3일(08-12~14) → 월 08-17   : 메움 5   진실 2   (+3)

        드문 열화가 아니라 **연 12~15회 되풀이되는 캘린더 이벤트**이고, 방향이 S2/S3
        가 잡으려던 과대발화와 같아 시정 효과를 부분 상쇄한다. 그래서 G 에서 계상은
        되돌리고 **가시성(`used_fallback` 플래그 + `[days_held_fallback]` 로그)만**
        남긴다 — 원래 F1 지적의 본질은 "무음"이었지 "값"이 아니었다.

        ## 오차의 방향

        - **정상일** (`cache_max` = 직전 거래일): 갭 = 오늘 하나 → **정확**, 플래그 False
        - **공휴일 직후** (`cache_max` = 휴장 전 거래일): 갭 = 오늘 하나 → **정확**
          (휴장일 미계상). 플래그만 True = 예정된 오탐(`_prev_weekday` docstring)
        - **주말 `today`** (수동 시작·fail-open): 갭 미계상 → **정확**, 전면 폴백 분기와
          동일 값(사이클 223 G1)
        - **평일 공휴일 `today`** (수동 시작·fail-open): 갭 +1 → **과다 하루**. 코드로
          가를 수 없는 잔여이고 플래그도 안 선다 — 알려진 한계로 남긴다
        - **스테일 캐시**: 과소 계상. 청산을 **늦춘다 = 보유 연장**이고, 이는 H-1
          사이클의 *"남는 오차는 과소 한 방향뿐이고 그 방향은 청산을 늦춘다"* 원칙과
          일치한다. 과다 계상(조기 청산)은 승자를 자르는 방향이라 훨씬 비싸다.
          그리고 무음이 아니다 — `used_fallback=True` 로 드러난다(F1 의 본래 지적).
        - **전면 폴백** (캐시 부재 = 재시작 직후 prepare 전 / `min(cache) > buy_date`):
          `(buy_date, today]` 의 weekday 수. 공휴일을 영업일로 세므로 약간 과다 계상
          이지만, 주말까지 세던 기존 달력일보다는 엄격히 낫다. 캐시가 매수일에 못
          닿을 때 캐시 경로를 쓰면 **조용한 과소 계상**이 되므로 폴백이 의무다.

        `used_fallback=True` 는 값의 정확성 주장이 아니라 **캐시가 직전 영업일까지
        못 닿았다**는 사실을 로그로 흘리기 위한 관찰 신호다.
        """
        cache = self._trading_days
        if cache and min(cache) <= buy_date:
            cache_max = max(cache)
            held = sum(1 for d in cache if buy_date < d <= today)
            # 갭(`cache_max` < d ≤ `today`) 기여는 **오늘 하루뿐** — 나머지 날은
            # 휴장/스테일 구분 불가라 세지 않는다. weekday 로 메우면 공휴일 다음
            # 첫 거래일마다 과다 계상 = 조기 청산(사이클 223 G).
            #
            # 사이클 223 G1 — `today.weekday() < 5` 가드. 이게 없으면 아래 전면 폴백
            # 분기(`cursor.weekday() < 5`)와 **한 함수 안에서 달력이 갈린다**:
            # buy=금 08-14 · today=토 08-15 → 캐시 1 / 폴백 0 (진실 0). 주말 today 는
            # `/api/trading/start` 수동 시작(휴장 가드 없음)과 휴장체크 fail-open 으로
            # 실재하고, 방향이 과다 계상 = 조기 청산이라 가장 비싸다.
            if today > buy_date and today not in cache and today.weekday() < 5:
                held += 1
            return held, cache_max < self._prev_weekday(today)

        held = 0
        cursor = buy_date + timedelta(days=1)
        while cursor <= today:
            if cursor.weekday() < 5:
                held += 1
            cursor += timedelta(days=1)
        return held, True

    def _emit_days_held_fallback(self, ticker: str, days_held: int, n_days: int,
                                 breakout_high: int = 0) -> None:
        """`[days_held_fallback]` 관측 로그 — 1회/ticker/일 cap (사이클 223 F4).

        발화 여부와 **무관하게** 방출한다. 폴백은 "거래일 캐시가 직전 영업일까지 못
        닿았다" = prepare/recompute 열화 신호이고, 그 상태에서 미발화가 이어지면
        기존(발화 시에만 로그) 방식으로는 영원히 안 보인다.

        사이클 223 G4 — 호출부 게이트가 `breakout_high > 0` 안에 있던 탓에 **시간청산
        기준선 자체가 미복구인 최악 상태**에서 정확히 침묵했다. 호출부를 `pos.buy_date`
        레벨로 올렸고, 그 상태를 구분할 수 있게 `breakout_high` 를 함께 싣는다
        (`breakout_high=0` = 재도출 실패로 시간청산 **무장 해제** 상태).

        사이클 223 G — 사유 문구는 **경로를 과잉 주장하지 않는다**. 플래그가 서는
        경우는 셋이고 계상 방식이 서로 다르다: 전면 폴백(캐시 부재/매수일 미도달)만
        weekday 환산이고, 캐시 경로는 갭을 오늘 하루로 한정하며, 공휴일 직후는
        플래그만 서고 값은 정확하다. 셋을 구분하는 단서는 `cached_days`/`cache_max`
        이므로 그 둘을 함께 싣는다 (`cached_days=0` = 전면 폴백).
        어떤 실패도 흡수 — 관측이 청산 판정을 막지 않는다.
        """
        try:
            if self._days_held_fallback_logged.should_emit(ticker):
                self._days_held_fallback_logged.mark_emitted(ticker)
                cache_max = max(self._trading_days) if self._trading_days else None
                logger.info(
                    "[days_held_fallback] ticker=%s strategy=%s days_held=%d n_days=%d"
                    " cached_days=%d cache_max=%s breakout_high=%d"
                    " reason='거래일 캐시가 직전 영업일 미도달(스테일 또는 공휴일 직후)"
                    " → 근사 계상'",
                    ticker, self.strategy_id, days_held, n_days,
                    len(self._trading_days), cache_max, int(breakout_high or 0),
                )
        except Exception:
            # 관측 실패가 청산을 막지 않는다 — 단 **무흔적 흡수는 금지**(사이클 258
            # C258-T3, 카드 #5 잔여 A 형태 시정). debug 스택 + WARNING 1회/ticker/일
            # (`system_logs` 도달) — 조용히 삼키면 이 관측이 영구 침묵해도 사이클
            # 223 이전의 무음과 구별되지 않는다(C237-L2-1). never-raise.
            trace_observer_failure(
                "[days_held_fallback_failed]", ticker,
                self._days_held_fallback_logged, dest_logger=logger,
            )

    def _emit_days_held_observation(self, ticker: str, pos, current_price: int) -> None:
        """`[days_held_observe]` 상시 관측 로그 — 1회/ticker/일 cap (사이클 224).

        ## 왜 (사각)

        사이클 223 S3 가 시간청산 보유일을 달력일 → **영업일**로 바꿨는데, 그 변경이
        라이브에서 무엇을 하는지 볼 수단이 없었다. `days_held` 가 로그에 남는 경로는
        둘뿐이었다 — (a) `used_fallback=True` 인 폴백 로그, (b) 시간청산이 **실제로
        발화**했을 때. 즉 **시간 기반 청산인데 발화할 때만 보유일이 보인다** =
        "얼마나 근접했나"를 영영 못 본다.

        실측 시나리오가 그 사각을 그대로 드러낸다. 금 매수 · `n_days=2` · 캐시 최신일이
        매수일과 같은 월요일은 `days_held=1`(달력 3) 이라 게이트 미충족이고,
        `cache_max == _prev_weekday(today)` 라 폴백 플래그도 서지 않는다 ⇒ **완전 무음**.
        그 무음은 "S3 가 잘 돌았다"와 "가격 조건 미충족"과 "다른 분기 선발화"를 구분하지
        못한다. 임시방편이 아니라 상시 관측성 결함이다.

        ## 계약

        - 호출 위치 = `check_exit_signal` **최상단**(포지션 확인 직후) ⇒ §1 하드손절을
          포함해 **어떤 청산 분기보다 앞**이다.
          ⚠️ F1 (적대적 검증 발견) — 처음엔 §2.5 시간청산 블록 안에 뒀는데, 그러면
          §1 하드손절이 그날 첫 평가에서 발화할 때 이 줄에 **도달조차 못 한다**.
          donchian 보유가 한 종목뿐인 날이면 그날 관측 목적이 통째로 소멸하고,
          더 나쁜 변형으로 하드손절 후 매도가 거부돼(APBK0918) 포지션이 살아남으면
          매 틱 §1 에서 return 하므로 관측이 **영구 억제**된다.
          그래서 인자를 `(ticker, pos, current_price)` 로만 받고 나머지(오늘·보유일·
          임계·돌파선)는 **내부에서** 구한다 — 호출부가 어떤 사전 계산도 요구하지
          않아야 최상단으로 올릴 수 있다.
        - `days_held`(영업일) 와 `calendar_days`(달력일) 를 **같은 한 줄**에 나란히
          싣는 것이 이 로그의 존재 이유다. `days_held=1 calendar_days=3` 한 줄이
          곧 S3 의 직접 확인이다.
        - `days_ok` / `price_ok` 를 **각각** 싣는다. AND 결과 하나만으론 어느 조건이
          막고 있는지 못 가린다.
        - `breakout_high=0` = 재도출 실패 = 시간청산 **무장 해제** 상태 (사이클 223 G4
          가 폴백 로그에 세운 "가장 필요한 때 침묵 금지" 원칙을 그대로 승계).
        - cap 은 폴백 cap 과 **별개 필드**(`_days_held_observe_logged`).
        - ⚠️ F2 — cap 키는 ticker 단독이 아니라 **`ticker|armed` / `ticker|disarmed`** 다.
          ticker 단독이면 그날 **첫 평가 스냅샷이 박제**된다: 장중 재시작 시 포지션
          복구가 `recompute_held_atr`(→`_rederive_breakout_high`)보다 앞서므로 첫
          호출이 `breakout_high=0` 으로 잡히고, 수 초 뒤 재도출이 성공해 시간청산이
          정상 무장돼도 그날 두 번째 행이 없어 운영자는 **종일 무장 해제**로 오독한다.
          키를 무장 여부로 나누면 최대 2행/종목/일이고 **무장 행은 반드시 한 번 나온다**.
        - 어떤 실패도 흡수 — 관측이 청산 판정을 막지 않는다. 단 ⚠️ F3 — **무흔적
          흡수는 금지**다. 조용히 삼키면 이 기능이 영구 침묵해도 사이클 224 이전의
          무음과 구별되지 않는다(`_turtle_buy_quantity` 의 debug 흔적 선례를 따른다).
          사이클 258(C258-T3)부터 흔적은 `observer_trace.trace_observer_failure`
          (debug 스택 + `[days_held_observe_failed] observer_failed key=` WARNING
          1회/ticker/일) — debug 로거 자신이 죽어도 2차 예외가 새지 않는다.

        hot path 라 cap 조회(set)를 **먼저** 하고, 보유일 계산은 그 뒤에만 한다.
        `await`/DB/HTTP 는 없다.
        """
        try:
            buy_date = getattr(pos, "buy_date", None)
            if not buy_date:
                return
            today = datetime.now(KST).date()
            bh = int(self._breakout_high.get(ticker, 0) or 0)
            cap_key = f"{ticker}|{'armed' if bh > 0 else 'disarmed'}"
            if not self._days_held_observe_logged.should_emit(cap_key):
                return
            self._days_held_observe_logged.mark_emitted(cap_key)
            n_days = int(self.config.params.get("breakout_fail_n_days", 5))
            days_held, _ = self._business_days_held(buy_date, today)
            logger.info(
                "[days_held_observe] ticker=%s strategy=%s buy_date=%s"
                " days_held=%d calendar_days=%d n_days=%d"
                " breakout_high=%d current_price=%d days_ok=%s price_ok=%s",
                ticker, self.strategy_id, buy_date,
                days_held, (today - buy_date).days, n_days,
                bh, int(current_price),
                days_held >= n_days,
                bh > 0 and current_price < bh,
            )
        except Exception:
            # F3 — 흡수하되 흔적은 남긴다. 조용히 삼키면 이 관측이 영구 침묵해도
            # 사이클 224 이전의 무음과 구별되지 않는다.
            # 사이클 258 C258-T3 — 무가드 `logger.debug`(카드 #5 B 형태)는 debug
            # 자체가 죽으면 2차 예외가 `check_exit_signal` 밖으로 샜다(400/400
            # RAISED 실측). `trace_observer_failure` 는 never-raise 이고 WARNING
            # 1회/ticker/일 로 `system_logs` 에도 도달한다(C237-L2-1).
            trace_observer_failure(
                "[days_held_observe_failed]", ticker,
                self._days_held_observe_logged, dest_logger=logger,
            )

    def _emit_zero_breakout_line(self, ticker: str, prior_high: int,
                                 prev_close: int, period: int) -> None:
        """`[donchian_zero_breakout_line]` — 돌파선 0 거부 관측 (사이클 226 D-1).

        ## 왜 WARNING 인가

        `prior_high == 0` 은 시장 사실이 아니라 **데이터 품질 사고**다 — 일봉 고가가
        전 구간 결손이라는 뜻이고, 그 상태로 `prepare` 가 돌면 20일 신고가 돌파를
        검증하지 않은 후보가 만들어진다. `src/main.py` 의 `_DbLogHandler` 는 **INFO
        이상만** `system_logs` 로 적재하므로 debug 는 20:10 일일 로그 리포트와
        대시보드에 도달하지 못한다. 사고를 조용히 거르면 시정 자체가 무의미해지므로
        WARNING 으로 올린다.

        ## 무엇을 싣나

        `prior_high`(=0) 단독으로는 "고가만 결손" 과 "봉 전체가 비었다" 를 못 가른다.
        `prev_close` 를 함께 실으면 **종가는 살아 있다** 는 사실이 한 줄에 남아
        부분 결손 row(= `_extract_raw` 의 raw 부재 폴백)로 좁혀진다. `period` 는
        창 길이가 파라미터로 바뀔 수 있어 사후 재현에 필요하다.

        ## cap

        사이클 223/224/225 의 네 cap 과 **별개 인스턴스 필드** — 같은 슬롯을 다투면
        한 사실이 다른 사실을 침묵시킨다(OB-11). 날짜 키 자기리셋.

        어떤 실패도 흡수하되 **흔적을 남긴다**(`[donchian_zero_breakout_line_failed]`).
        ⚠️ 기존 `except Exception: logger.warning("도치안 스윙 prepare 실패 …")` 로
        새면 관측기 결함이 일봉 파싱 결함으로 오독되므로, 여기서 전부 가둔다.
        """
        try:
            if not self._zero_breakout_line_logged.should_emit(ticker):
                return
            self._zero_breakout_line_logged.mark_emitted(ticker)
            logger.warning(
                "[donchian_zero_breakout_line] ticker=%s strategy=%s period=%d"
                " prior_high=%d prev_close=%d"
                " note='직전 %d일 신고가 산출 실패(돌파선 0) — 일봉 고가 결손 의심."
                " 돌파 미검증 후보로 새지 않도록 제외했다(데이터 품질 사고).'",
                ticker, self.strategy_id, int(period),
                int(prior_high or 0), int(prev_close or 0), int(period),
            )
        except Exception:
            trace_observer_failure(
                "[donchian_zero_breakout_line_failed]", ticker,
                self._zero_breakout_line_logged, dest_logger=logger,
            )

    def _emit_held_recompute_skip(self, ticker: str, pos, need_atr: bool,
                                  needs_high_recover: bool) -> None:
        """`[held_recompute_skip]` 관측 로그 — 1회/ticker/일 cap (사이클 225 A).

        ## 왜 (침묵 1층)

        `recompute_held_atr` 루프의 게이트

            need_atr = ticker not in self._candidates
            if not need_atr and not pos_needs_high_recover: continue

        는 fetch **앞**에 있고 무로그다. 두 축이 모두 False 인 종목은 그 아래
        `_rederive_breakout_high` 에 **도달조차 못 한다** — 즉 재도출이 실패한 게
        아니라 호출되지 않는다. 2026-08-24 15:58 장중 재배포 직후 192820 이 정확히
        그 상태였고(`buy_date == today` + `_candidates` 잔류), `_breakout_high` 가
        종일 0 인 채였는데 그 사실을 가리키는 로그가 시스템 어디에도 없었다.

        ## ⚠️ 이 로그는 "위험" 을 주장하지 않는다

        이 구멍의 발생 조건이 `buy_date == today` 라서 `_business_days_held` 는
        **항상 0** 이고, `breakout_fail_n_days` 는 라이브 2 · 기본 5 다(사이클 223 S1
        이 `PARAM_RANGES` 에서 제외해 AI 가 못 낮춘다). 시간청산 게이트는
        `breakout_high > 0 and days_held >= n_days and 현재가 < breakout_high` 이므로
        `days_held(0) >= n_days(>=2)` 가 어차피 거짓 = **게이트가 닫혀 있다**.
        게다가 대개 **자가 치유**된다 — (a) 다음 영업일 부팅이면 `buy_date < today` 로
        `needs_high_recover=True`, (b) 후보 이탈이면 `need_atr=True` 로 게이트를
        통과한다. `days_held` 가 임계에 닿기 전에 재시도가 걸린다.
        ⚠️ K-4 — 다만 **재시도이지 재무장 보장이 아니다**. 게이트를 통과해도 그 뒤
        `candles` 가 비면(`fetch_daily_candles` 는 빈 `output2` 에 예외 없이 `[]` 를
        돌려주고 5분 캐시에 박는다) `_rederive_breakout_high` 진입 자체가 막힌다 —
        그 경로는 `_emit_breakout_high_rederive_not_called(reason=no_candles)` 가
        따로 잡는다. 한때 여기 "반드시 재무장된다" 고 적혀 있었으나 그 단정은
        같은 사이클의 J-1 이 스스로 반증했다.
        그래서 이 사이클은 **행위를 바꾸지 않는다** — 게이트 앞에서 재도출을 억지로
        부르면 매수 당일 종목마다 KIS 일봉 fetch 가 새로 생기는데 이득이 0이다.

        ## 계약

        - **발화 조건 = 무장 미복구**(`_breakout_high` 값이 0 이거나 키 부재)일 때만.
          이미 무장돼 있으면 그 skip 은 무해하고, 정상 경로를 매일 찍으면 진짜 신호가
          희석된다. ⚠️ 판정 축은 **멤버십이 아니라 값**이다(사이클 225 K-1) —
          시간청산 게이트가 `breakout_high > 0` 으로 보기 때문이다.
        - 그 조건 판정은 **이 메서드 안**(try 내부)에서 한다. 호출부에서
          `_breakout_high` 를 읽으면 그 읽기가 try 밖이라 관측이 `recompute_held_atr`
          루프를 죽여 **뒤 종목의 복구까지 유실**시킬 수 있다.
        - cap 은 사이클 223 `_days_held_fallback_logged` / 224
          `_days_held_observe_logged` 와 **별개 필드**. 날짜 키 자기리셋.
        - 어떤 실패도 흡수하되 **흔적을 남긴다**(`[held_recompute_skip_failed]` debug).
          무흔적 흡수는 금지 — 조용히 삼키면 이 관측이 영구 침묵해도 도입 이전 무음과
          구별되지 않는다(사이클 224 F3 계약).

        hot path 는 아니지만(부팅 · 스윙 폴 주기) 무장 여부 · cap 조회를 **먼저** 하고
        문자열 구성은 그 뒤에만 한다. `await`/DB/HTTP 는 없다.
        """
        try:
            today = datetime.now(KST).date()
            # K-1 (적대적 검증) — 무장 판정은 **멤버십이 아니라 값**이다.
            # 시간청산 게이트(`check_exit_signal`)가 `breakout_high > 0` 로 보고,
            # 같은 파일 `_emit_days_held_observation` 도 값으로 본다. 여기만 멤버십이면
            # `_breakout_high[t] == 0`(고가 결손 일봉으로 매수 시 도달 가능 —
            # `check_buy_signal` 이 `info["donchian_high"]` 를 무조건 대입한다)인
            # 포지션이 "무장됨"으로 오판돼 **흔적 없이** 침묵한다.
            # ⚠️ 사이클 226 D-2 정정 — 사이클 225 는 여기에 "재도출 진입 게이트는
            #    무변경이라 값 0 이면 재도출이 여전히 막힌다" 고 적어뒀다. 그 서술은
            #    이제 **거짓**이다: D-2 가 그 게이트도 값 기준으로 바꿔 값 0 포지션은
            #    재도출을 **시도**한다(자가 치유). 이 로그는 그 시도조차 도달하지 못하는
            #    상위 게이트 skip(1층)만 남는다.
            armed = int(self._breakout_high.get(ticker, 0) or 0) > 0
            if armed:
                return
            if not self._held_recompute_skip_logged.should_emit(ticker):
                return
            self._held_recompute_skip_logged.mark_emitted(ticker)
            logger.info(
                "[held_recompute_skip] ticker=%s strategy=%s buy_date=%s today=%s"
                " need_atr=%s in_candidates=%s needs_high_recover=%s"
                " breakout_high_armed=%s"
                " note='재도출 미호출 — 무장 미복구. 다음 영업일 부팅 또는 후보"
                " 이탈 시 재시도되나 재무장은 보장이 아니다(일봉 fetch 성공 의존).'",
                ticker, self.strategy_id, getattr(pos, "buy_date", None), today,
                bool(need_atr), ticker in self._candidates,
                bool(needs_high_recover), armed,
            )
        except Exception:
            # 흡수하되 흔적은 남긴다 (사이클 224 F3 + 사이클 225 J-3).
            # debug 단독은 `_DbLogHandler`(INFO 이상만 적재)를 통과하지 못해
            # `system_logs` 에 도달하지 않는다 ⇒ WARNING 1행/ticker/일 병행.
            trace_observer_failure(
                "[held_recompute_skip_failed]", ticker,
                self._held_recompute_skip_logged, dest_logger=logger,
            )

    def _emit_breakout_high_rederive_not_called(self, ticker: str, pos,
                                                candles) -> None:
        """침묵 **4층** 관측 — 재도출 게이트가 falsy 라 호출 자체가 없었던 경우 (사이클 225 J-1).

        `recompute_held_atr` 의

            if pos and pos.buy_date and candles and not <무장값>:
                self._rederive_breakout_high(...)

        가 거짓일 때의 `else` 에서 호출된다. 이 경로는 `_rederive_breakout_high` 에
        **진입조차 하지 않으므로** 2·3층 로그(B)가 없고, 상위 게이트를 이미 통과했으므로
        1층 로그(A)도 없다 = 완전 무음이었다.

        ## A(1층)와 달리 '자가 치유' 가 성립하지 않는다

        상위 게이트를 통과했다는 것은 `buy_date < today` 또는 후보 이탈이라는 뜻이다.
        그러면 `days_held` 가 계속 자라 `breakout_fail_n_days` 를 넘기는데, 시간청산은
        `breakout_high > 0` 조건에 막혀 **영구 미발화**한다. A 로그가 "다음 영업일 부팅에
        재무장된다" 고 약속한 바로 그 경로가 여기다 — 그 약속이 깨지는 지점.

        ## 발화 금지 = 이미 무장된 경우

        게이트가 거짓인 **정상** 사유가 `ticker in self._breakout_high`(당일 매수 후
        미재시작 등)다. 그 경로를 매일 찍으면 진짜 신호가 희석된다 ⇒ 무장돼 있으면
        아무것도 하지 않는다. 남는 것은 "게이트 거짓 **이면서** 여전히 미복구" 뿐이다.

        ## 판정을 이 안(try 내부)에서 하는 이유

        호출부에서 사유를 계산하면 그 계산(`pos.buy_date` 접근 등)이 try 밖이라 관측이
        `recompute_held_atr` 루프를 죽여 **뒤 종목의 복구까지 유실**시킬 수 있다
        (A emitter 의 C-12a 계약 동형). 무장 확인 · 사유 판정 전부 try 안이다.

        행위 변경 0 — 재도출을 억지로 호출하지 않는다. 순수 관찰.
        """
        try:
            # K-1 — 값 기준 무장 판정(A emitter 동형). 상세는 그쪽 주석.
            if int(self._breakout_high.get(ticker, 0) or 0) > 0:
                return
            if not pos:
                # ⚠️ K-3 — 이 사유는 "직접 호출 전용 방어" 가 **아니다**. 루프에서
                #    실제로 도달한다: `state.positions` 가 `keys()` 에는 있고
                #    `get()` 은 None 인 레이스(청산 직후)면 상위 게이트를
                #    `need_atr=True` 로 통과해 여기까지 온다. 정상 범주의 관측이다.
                #    (반면 `no_buy_date` 는 상위 `pos.buy_date < today` 가 먼저
                #     TypeError 를 내므로 루프 도달 불가 = 직접 호출 방어용.)
                reason = "no_position"
            elif not getattr(pos, "buy_date", None):
                reason = "no_buy_date"
            elif not candles:
                reason = "no_candles"
            else:
                # 게이트 4축이 모두 참인데 여기 왔다 = 호출부 구조가 바뀐 것. 방어 기록.
                # ⚠️ 사이클 226 D-2 — 이 사유는 한때 **실제로 도달했다**. 게이트
                #    마지막 축이 멤버십(`ticker not in self._breakout_high`)이던 시절,
                #    `_breakout_high[t] == 0` 인 포지션은 나머지 3축이 전부 참인데도
                #    게이트가 거짓이라 여기로 떨어졌다(= "이론상 도달 불가" 라던 주석
                #    자체가 멤버십 게이트의 부작용을 증언하고 있었다). D-2 가 그 축을
                #    값 기준으로 바꾼 뒤로 다시 도달 불가 = 순수 방어 기록이다.
                reason = "not_called"
            self._emit_breakout_high_rederive_skip(ticker, pos, reason)
        except Exception:
            trace_observer_failure(
                "[donchian_breakout_high_rederive_skip_failed]", ticker,
                self._breakout_high_rederive_skip_logged, dest_logger=logger,
            )

    def _emit_breakout_high_rederive_skip(self, ticker: str, pos, reason: str,
                                          prior_len: int | None = None,
                                          need: int | None = None) -> None:
        """`[donchian_breakout_high_rederive_skip]` — 1회/**(ticker, 사유)**/일 cap.

        `_breakout_high` 가 **무장되지 않은 채 남는** 모든 조용한 경로에 사유를 남긴다.

            # 재도출이 돌았으나 미복구 (사이클 225 B)
            reason=insufficient_prior  — `len(prior) < donchian_period + 1` (침묵 2층)
            reason=zero_high           — 계산 결과 `breakout_high <= 0`     (침묵 3층)
            # 재도출이 **호출조차 안 됨** (사이클 225 J-1, 침묵 4층)
            reason=no_candles          — `candles` falsy (KIS 빈 output2 → `[]` 5분 캐시)
            reason=no_buy_date         — `pos.buy_date` falsy
            reason=no_position         — `pos` 자체가 없음
            reason=not_called          — 그 외 (사이클 226 D-2 이후 도달 불가, 방어.
                                          D-2 이전엔 값 0 포지션이 여기로 떨어졌다)

        ## cap 키 = `ticker|reason` (사이클 225 J-2)

        키가 ticker 단독이면 같은 날 같은 종목의 `insufficient_prior` 가 뒤따르는
        `zero_high` 를 **침묵시킨다**(실증). 사유를 나눈 이유가 "대응이 갈리기
        때문"(봉 부족 = 일봉 백필 / 값 0 = KIS 데이터 품질 / 게이트 falsy = 캐시된 빈
        응답)인데 cap 이 그 구분을 지우면 분리 자체가 무의미해진다. A cap
        (`_held_recompute_skip_logged`)은 사유가 하나뿐이라 ticker 단독 유지.

        ## 필드는 **사유에 의미 있는 것만** 싣는다 (사이클 225 J-4)

        단일 포맷으로 전 사유에 `need=` 를 실으면 `reason=zero_high prior=25 need=21`
        같은 줄이 나온다. 운영자는 "25 ≥ 21 인데 왜 실패?" 로 읽고 길이 가드 회귀
        (사이클 223 S2)를 의심해 엉뚱한 곳을 판다 — 실제 원인은 KIS 고가 필드 결손이다.
        ⇒ `need=` 는 `insufficient_prior` 전용, `prior=` 는 재도출이 실제로 돈 2·3층
        전용(4층엔 `prior` 개념 자체가 없다), 4층 `no_candles` 는 `candles=0` 만 적는다.

        기존 성공 로그 `[donchian_breakout_high_rederive]` 와 기존
        `except Exception: logger.exception("도치안 breakout_high 재도출 실패")` 는
        **무변경**이다.

        ⚠️ 실패는 **이 메서드의 자기 try** 안에서 흡수한다. 호출부(`_rederive_breakout_high`)
        의 except 로 새면 운영자가 "재도출 실패" = 데이터 문제로 읽는데 실제로는
        관측기 결함이다(원인 오독). 흔적 마커
        `[donchian_breakout_high_rederive_skip_failed]` — debug 스택 + WARNING 1행
        (사이클 225 J-3, `system_logs` 도달용).
        """
        try:
            cap_key = f"{ticker}|{reason}"
            if not self._breakout_high_rederive_skip_logged.should_emit(cap_key):
                return
            self._breakout_high_rederive_skip_logged.mark_emitted(cap_key)
            # 사유별 유효 필드만. 숫자는 여기서 치환 완료 — 포맷 문자열에 `%` 미유입.
            if reason == "insufficient_prior":
                extra = " prior=%d need=%d" % (int(prior_len or 0), int(need or 0))
            elif reason == "zero_high":
                extra = " prior=%d" % int(prior_len or 0)
            elif reason == "no_candles":
                extra = " candles=0"
            else:
                extra = ""
            if reason in _REDERIVE_NOT_CALLED_REASONS:
                note = ("재도출 미호출(게이트 falsy) — 무장 미복구가 지속되면 "
                        "시간청산이 breakout_high>0 에 막혀 영구 미발화한다")
            else:
                note = "재도출 미복구 — 시간청산 기준선이 무장되지 않은 상태"
            logger.info(
                "[donchian_breakout_high_rederive_skip] ticker=%s strategy=%s"
                " buy_date=%s reason=%s" + extra + " note='%s'",
                ticker, self.strategy_id, getattr(pos, "buy_date", None),
                reason, note,
            )
        except Exception:
            # 흡수하되 흔적은 남긴다 — 기존 '재도출 실패' 로그로 새면 원인이 오독된다.
            trace_observer_failure(
                "[donchian_breakout_high_rederive_skip_failed]", ticker,
                self._breakout_high_rederive_skip_logged, dest_logger=logger,
            )

    def _rederive_breakout_high(self, ticker: str, pos, candles: list, donchian_period: int) -> None:
        """재시작 복구 — buy_date 이전 일봉으로 진입 시점 20일 신고가(`_breakout_high`) 재현.

        P1-A (2026-07-29, A-2). 시간 기반 청산(check_exit_signal 2.5) 의 breakout_high
        기준선이 재시작 후 소실되는 결함 차단. `_rederive_entry_atr` 선례 답습 — buy_date
        *이전* 봉만 남겨 donchian_period 개의 최고가를 취한다. 봉 부족 시 미복구.

        사이클 223 (S2, 2026-08-21) — off-by-one 시정. candles 는 DESC 이므로
        `prior[0]` 은 매수일 직전 봉 = **신호일(돌파일) 봉**이다. 신호일은 정의상 20일
        신고가를 돌파한 날이라 이 봉을 포함하면 재도출선이 라이브 매수 경로
        (`prepare`: `max(highs[1: donchian_period + 1])`) 보다 **항상 높거나 같다**
        (실측 19/19, 중앙값 +5.3%). 그 결과 시간청산이 "돌파 실패"가 아니라 "돌파일
        장중 고가 미탈환"을 판정해 과대발화했다 (판정 반전 8/19, 승자 5건 전부 포함).
        창을 `prior[1: donchian_period + 1]` 로 옮기고 길이 가드도 `donchian_period + 1`
        로 동반 조정한다 — 안 하면 IndexError 가 아니라 19봉으로 20일 신고가를 만드는
        **조용한 과소 표본**이 된다.
        근거: `_workspace/domain_consult/donchian_exit_retune.md` §2-6 / C0.
        """
        try:
            buy_dd = pos.buy_date.strftime("%Y%m%d")
            prior = [c for c in candles if str(c.get("stck_bsop_date", "")) < buy_dd]
            # ⚠️ 길이 가드는 **리터럴 `len(prior) < donchian_period + 1`** 로 둔다 —
            # 사이클 223 AST 가드(test_cycle223_ast_donchian_exit_fix::
            # test_g223_3_rederive_window_excludes_signal_day)가 이 표현식을 소스에서
            # 직접 찾는다. 지역 변수로 뽑으면 S2 off-by-one 회귀 가드가 무력화된다.
            if len(prior) < donchian_period + 1:
                # 사이클 225 B — 침묵 2층. 사이클 223 S2 가 길이 가드를 period → period+1
                # 로 올려 **미복구 확률이 올라간** 경로다. 사유·필요 봉 수를 남긴다.
                self._emit_breakout_high_rederive_skip(
                    ticker, pos, "insufficient_prior", len(prior), donchian_period + 1,
                )
                return
            highs = [
                int(c.get("stck_hgpr", "0") or 0)
                for c in prior[1: donchian_period + 1]
            ]
            breakout_high = max(highs) if highs else 0
            if breakout_high > 0:
                self._breakout_high[ticker] = breakout_high
                logger.info(
                    "[donchian_breakout_high_rederive] %s buy_date=%s breakout_high=%d",
                    ticker, pos.buy_date, breakout_high,
                )
            else:
                # 사이클 225 B — 침묵 3층. 봉은 충분한데 계산 결과가 0 (KIS 고가 필드
                # 결손 등). 2층과 **사유가 달라야** 대응이 갈린다 (봉 부족 = 백필 /
                # 값 0 = 데이터 품질).
                self._emit_breakout_high_rederive_skip(
                    ticker, pos, "zero_high", len(prior), donchian_period + 1,
                )
        except Exception:
            logger.exception("도치안 breakout_high 재도출 실패: %s", ticker)

    def _recompute_channel_low(self, ticker: str, candles: list, channel_period: int) -> None:
        """최근 channel_period 영업일 저가(당일 제외) 산출 — 10일 채널 청산 데이터 소스.

        P1-A (2026-07-29, A-4). `candles[0]` 이 오늘 부분봉일 수 있어 당일을 제외한
        최근 channel_period 개 봉의 최저 저가를 취한다. 봉 부족 시 미갱신(기존 값 보존).
        """
        try:
            today_str = datetime.now(KST).strftime("%Y%m%d")
            relevant = [c for c in candles if str(c.get("stck_bsop_date", "")) != today_str]
            if len(relevant) < channel_period:
                return
            lows = [int(c.get("stck_lwpr", "0") or 0) for c in relevant[:channel_period]]
            channel_low = min(lows) if lows else 0
            if channel_low > 0:
                self._channel_low[ticker] = channel_low
        except Exception:
            logger.exception("도치안 channel_low 산출 실패: %s", ticker)

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

    # `_apply_high_since_buy_from_candles` 는 `StrategyBase` 로 승격(H-1, 2026-08-06) —
    # VCP 에 로그 접두사만 다른 byte-identical 복사본이 있었고 kojiro 가 3번째가 될
    # 참이라 단일 진실원으로 추출했다. 호출 계약(pos, candles, today)은 그대로다.
    # 아래 라벨이 추출 전 로그 리터럴("도치안 스윙 high_since_buy 보정")을 보존한다 —
    # 운영자가 과거 인시던트를 한글 표기로 grep 하는 경로가 끊기지 않게.
    _HIGH_RECOVER_LABEL = "도치안 스윙"
    _ENTRY_ATR_REDERIVE_LABEL = "donchian"

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
        # cycle233 — 계좌 SOFT Σ상한 순간 게이트 (다크런치·fail-open, 신규 매수만)
        if self._account_soft_gate_blocked(ticker):
            return Signal.NONE
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

        # 사이클 224 (F1) — 보유일 관측은 **어떤 청산 분기보다 앞**이다.
        # 아래 §1 하드손절이 그날 첫 평가에서 발화하면 시간청산 블록에 도달조차
        # 못 해 그 종목의 그날 보유일이 영영 기록되지 않는다. 순수 관찰이라
        # 반환 시그널에 어떤 영향도 주지 않고, hot path 비용은 emitter 안의
        # cap 조회가 그날 1~2회로 한정한다.
        self._emit_days_held_observation(ticker, pos, current_price)

        # 1) 하드 손절
        loss_rate = (current_price - pos.buy_price) / pos.buy_price * 100 if pos.buy_price > 0 else 0
        # Phase 2A-2 (게이트 1) — entry_atr 존재 = 터틀 매수 → 2ATR 하드손절(지배) + % backstop
        # (info=None/재시작/ATR=0 최후 방어). 미존재(position_ratio 매수/미스탬프) = 기존 % 손절
        # (byte 동일 — sizing_mode 로 게이팅하지 않음, entry_atr 존재가 자연 게이트).
        entry_atr = self._entry_atr.get(ticker, 0)
        if entry_atr > 0:
            stop_atr = float(self.config.params.get("stop_atr", 2.0))
            base_stop = pos.buy_price - stop_atr * entry_atr
            # P1-A (2026-07-29, A-3) — 브레이크이븐 승격: 고점이 매수가 + 1.5×entry_atr
            # 이상 도달한 이력이 있으면 하드손절선을 매수가로 승격 (tighten-only, entry_atr
            # 존재 시에만). 손절선을 넓히는 방향은 절대 없음(max 연산).
            breakeven_mult = float(self.config.params.get("breakeven_promote_atr", 0) or 0)
            if breakeven_mult > 0 and pos.high_since_buy >= pos.buy_price + breakeven_mult * entry_atr:
                promoted_stop = max(base_stop, pos.buy_price)
                if promoted_stop != base_stop:
                    # 사이클 237 — 로그만 1회/ticker/일 cap. 승격 대입은 cap 밖(아래 줄).
                    self._emit_breakeven_promote(
                        ticker, pos.high_since_buy, pos.buy_price, breakeven_mult,
                        entry_atr, base_stop, promoted_stop,
                    )
                base_stop = promoted_stop
            if base_stop > 0 and current_price <= base_stop:
                logger.info("[donchian_turtle_stop] %s 매수가(%d) - %.1f×ATR(%d) = %d / 현재가 %d",
                            ticker, pos.buy_price, stop_atr, int(entry_atr), int(base_stop), current_price)
                return Signal.STOP_LOSS
            backstop = float(self.config.params.get("turtle_backstop_pct", -9.0))
            if loss_rate <= backstop:
                logger.info("[donchian_turtle_backstop] %s 매수가(%d) 대비 %.1f%% ≤ %.1f%%",
                            ticker, pos.buy_price, loss_rate, backstop)
                return Signal.STOP_LOSS
        else:
            stop_loss = self.config.params["stop_loss_rate"]
            if loss_rate <= stop_loss:
                logger.info("도치안 스윙 손절: %s 매수가(%d) 대비 %.1f%%",
                            ticker, pos.buy_price, loss_rate)
                return Signal.STOP_LOSS

        # 2.5) 사이클 23 P2-2 — 시간 기반 청산 (멀티데이 약한 이탈 빠른 정리)
        # 기존 ATR 트레일링/하드 손절 보존, 추가 분기만 삽입
        # 사이클 223 (S3, 2026-08-21) — 달력일 → **영업일**. `(today - buy_date).days` 는
        # 주말·휴장을 보유일로 세어, n_days=2 라이브 값과 결합하면 금요일 매수가 월요일에
        # `3 >= 2` 로 **실거래 1일** 만에 청산 자격을 얻었다(실측 13건 중 7건이 금요일 매수,
        # 6건이 이 경로 = 상시 경로). 매매 규칙 정본도 "보유 N**영업일**"이라 계약 불일치였다
        # (`_workspace/refactor/2026-06-27_full_review.md` strat-6 CONFIRMED 미시정).
        # n_days 값(2)은 불변 — 이번 사이클은 **세는 방법만** 고친다.
        n_days = int(self.config.params.get("breakout_fail_n_days", 5))
        breakout_high = self._breakout_high.get(ticker, 0)
        # 사이클 223 G4 — 관측 게이트를 `pos.buy_date` 레벨로 올린다. 종전엔
        # `breakout_high > 0` 안에 있어서 **재시작 + `_breakout_high` 미복구 + 빈 캐시**
        # = 관측이 가장 필요한 최악 상태에서 로그가 정확히 0건이었다(S2 의 길이 가드
        # 강화 `period` → `period+1` 이 미복구 확률을 올렸다). 청산 조건은 그대로 —
        # 발화는 여전히 `breakout_high > 0` 을 요구한다(아래 if).
        if pos.buy_date:
            today = datetime.now(KST).date()
            days_held, used_fallback = self._business_days_held(pos.buy_date, today)
            if used_fallback:
                # 사이클 223 F4 — 폴백 사용 자체를 발화 여부와 무관하게 드러낸다.
                # hot path 폭주는 DailyEmitCap(1회/ticker/일)이 막는다.
                self._emit_days_held_fallback(ticker, days_held, n_days, breakout_high)
            if breakout_high > 0 and days_held >= n_days and current_price < breakout_high:
                # 사이클 223 G — 캐시 경로/전면 폴백을 한 문구로 덮되 과잉 주장 금지
                # (전면 폴백만 weekday 환산, 캐시 경로는 갭을 오늘 하루로 한정).
                suffix = " [폴백: 거래일 캐시 직전 영업일 미도달 → 근사 계상]" if used_fallback else ""
                # 사이클 237 — 로그만 1회/ticker/일 cap. 신호 반환은 cap 밖(아래 줄) —
                # 매도 거부 시 재시도가 끊기면 포지션이 청산되지 못한 채 잔존한다.
                self._emit_time_exit(
                    ticker, days_held, n_days, current_price, breakout_high, suffix,
                )
                return Signal.STOP_LOSS

        # 2.6) P1-A (2026-07-29, A-4) — 10일 저가 채널 이탈 청산 (시간청산 뒤, ATR 트레일링 앞).
        # 데이터 소스는 recompute_held_atr 가 prepare/recompute 시점 일봉으로 산출 —
        # on_tick KIS 신규 호출 없음. channel_exit_period=0 이면 비활성(opt-out).
        channel_period = int(self.config.params.get("channel_exit_period", 0) or 0)
        channel_low = self._channel_low.get(ticker, 0)
        if channel_period > 0 and channel_low > 0 and current_price < channel_low:
            logger.info(
                "[donchian_channel_exit] %s 현재가(%d) < 최근 %d일 채널 저가(%d)",
                ticker, current_price, channel_period, channel_low,
            )
            return Signal.TRAILING_STOP

        # 2) ATR 트레일링 — high_since_buy 기준 (RiskManager가 매 tick 갱신)
        # P1-A (2026-07-29, A-1) — _candidates miss(후보 이탈) 시 _entry_atr 폴백.
        # _candidates 는 매일 prepare 가 재구성 → 보유 종목이 20일 신고가 후보에서
        # 이탈하면 info=None → atr=0 → 트레일링 영구 침묵하던 결함 시정.
        info = self._candidates.get(ticker)
        atr = info["atr"] if info else self._entry_atr.get(ticker, 0)
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

    def get_effective_stop_price(self, ticker: str) -> int | None:
        """실효 손절선 read-only 미러 (cycle233 척도 병기).

        `check_exit_signal` 의 **가격선**들과 동일 산식·동일 상태 소스의 max —
        §1 터틀(2ATR base + 브레이크이븐 승격 + backstop 선) 또는 미스탬프 고정%,
        §2.6 채널 저가, §2 샹들리에. 시간청산(§2.5)은 가격 무관이라 모델 제외
        (kojiro `_position_stop_price` stage3 제외 선례 — 조기 청산 방향 = 보수).
        read-only — 로그 무발화·상태 무변조 (승격 로그는 check_exit 전용).
        """
        pos = self.state.positions.get(ticker)
        if not pos or pos.buy_price <= 0:
            return None
        try:
            params = self.config.params
            lines: list[float] = []
            entry_atr = self._entry_atr.get(ticker, 0)
            if entry_atr > 0:
                stop_atr = float(params.get("stop_atr", 2.0))
                base_stop = pos.buy_price - stop_atr * entry_atr
                be_mult = float(params.get("breakeven_promote_atr", 0) or 0)
                if (be_mult > 0
                        and pos.high_since_buy >= pos.buy_price + be_mult * entry_atr):
                    base_stop = max(base_stop, float(pos.buy_price))
                if base_stop > 0:
                    lines.append(base_stop)
                backstop = float(params.get("turtle_backstop_pct", -9.0))
                lines.append(pos.buy_price * (1 + backstop / 100.0))
            else:
                stop_loss = float(params["stop_loss_rate"])
                lines.append(pos.buy_price * (1 + stop_loss / 100.0))
            channel_period = int(params.get("channel_exit_period", 0) or 0)
            channel_low = self._channel_low.get(ticker, 0)
            if channel_period > 0 and channel_low > 0:
                lines.append(float(channel_low))
            info = self._candidates.get(ticker)
            atr = info["atr"] if info else self._entry_atr.get(ticker, 0)
            if atr > 0 and pos.high_since_buy > 0:
                mult = float(params["atr_trail_mult"])
                lines.append(pos.high_since_buy - atr * mult)
            positives = [line for line in lines if line > 0]
            return int(max(positives)) if positives else None
        except Exception:
            return None  # fail-open — 프록시 폴백

    def check_force_clear(self) -> list[str]:
        """15:20 강제 청산 대상 — 스윙 전략은 강제 청산 없음."""
        return []

    def calc_buy_quantity(self, current_price: int, ticker: str | None = None) -> int:
        """할당 자금의 position_ratio 비중. 비중 기준 0주여도 잔여 자금이 1주 살 수 있으면 1주.

        Phase 2A-2 (게이트 1): sizing_mode="turtle" + ticker 지정 시 터틀 유닛 sizing
        (변동성 정규화) 우선. 터틀이 0(변동성 floor/잔여부족) 반환 시 position_ratio 낙하.
        """
        if current_price <= 0:
            return 0
        params = self.config.params
        if params.get("sizing_mode") == "turtle" and ticker is not None:
            turtle_qty = self._turtle_buy_quantity(current_price, ticker)
            if turtle_qty > 0:
                return self._apply_budget_limit(turtle_qty, current_price, ticker)
        ratio = params["position_ratio"]
        amount = int(self.state.total_investment * ratio)
        return self._apply_budget_limit(amount // current_price, current_price, ticker)

    def _turtle_buy_quantity(self, current_price: int, ticker: str) -> int:
        """터틀 유닛 수량 + entry_atr 원자 스탬프 (Phase 2A-2 게이트 1).

        `_candidates[ticker]["atr"]`(prepare D-1 ATR)를 sizing 과 하드손절 entry_atr
        양쪽에 동일 사용(불변식 성립 열쇠). 갭/변동성 가드는 `compute_unit_qty_guarded`.
        0 반환(저변동/잔여부족/예외) 시 호출자가 position_ratio 로 낙하 = entry_atr 미스탬프.
        """
        try:
            from src.engine.turtle_sizing import compute_unit_qty_guarded

            info = self._candidates.get(ticker) or {}
            atr = float(info.get("atr") or 0)
            budget = int(self.state.total_investment)
            remaining = max(0, budget - self._calc_used_funds())
            qty = compute_unit_qty_guarded(
                budget, atr, current_price,
                float(self.config.params.get("risk_pct") or 0),
                remaining_budget=remaining,
                min_vol_pct=float(self.config.params.get("min_vol_floor_pct", 1.0)),
                position_ratio=float(self.config.params.get("position_ratio") or 0),
            )
            if qty > 0:
                # sizing 과 동일 ATR 값으로 하드손절 entry_atr 스탬프 (원자 결합)
                self._entry_atr[ticker] = atr
                return qty
        except Exception:
            logger.debug("[donchian_turtle_sizing_fallback] %s — position_ratio 낙하",
                         ticker, exc_info=True)
        return 0

    def on_position_closed(self, ticker: str) -> None:
        """전량 청산 시 터틀 entry_atr + 채널 저가 정리 (재진입 stale 스냅샷 차단)."""
        self._entry_atr.pop(ticker, None)
        # P1-A (2026-07-29, A-4) — _channel_low 는 보유 중에만 유효한 멀티데이 상태.
        # 전량 청산 시 정리 (일일 리셋 아님 — 재진입 시 recompute_held_atr 재산출).
        self._channel_low.pop(ticker, None)
