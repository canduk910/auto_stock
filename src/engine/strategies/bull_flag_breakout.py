"""눌림목 돌파(Bull Flag Breakout) 전략.

강한 상승(폴, flag pole) 직후 짧은 횡보·완만 조정(플래그) → 플래그 상단 재돌파 시 매수.
모멘텀(+29% 폭발) 전략의 후속 정리 후 2차 상승 진입로.

진입:
- 폴: 직전 3~10영업일 누적 +15% 이상, 음봉 비율 ≤ 45% (사이클 48 — DEFAULT_PARAMS
  pole_min_return=15.0 / pole_max_red_ratio=0.45. 한국 ±30% 환경에서 +20%/음봉 30% 교집합 0 차단)
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

import asyncio
import logging
from datetime import date, datetime, time, timedelta, timezone

from src.api.condition import add_business_days
from src.engine.strategy_base import FunnelStage, Signal, StrategyBase, StrategyConfig

KST = timezone(timedelta(hours=9))
logger = logging.getLogger(__name__)


# 사이클 47 (2026-05-22, refactor-review 카드 #3) — Funnel 단계 정의 모듈 상수.
# `prepare()` 의 `_record_funnel_pipeline_step(FUNNEL_STAGES[i-1], ...)` 위임 헬퍼와 결합.
# step_conditions 는 runtime 평가 (f-string) — 호출 시점 별도 인자 전달.
FUNNEL_STAGES: tuple[FunnelStage, ...] = (
    FunnelStage(1, "유니버스 후보"),
    FunnelStage(2, "유니버스 필터 통과 (시총·거래대금)"),
    # 사이클 157 (2026-06-17) — 1단계 진입 차단 13건 step 신규 영구 영속 → 9단계.
    FunnelStage(3, "1단계 진입 차단 13건 통과 (거래정지/관리/단기과열/투자유의 등)"),
    FunnelStage(4, "일봉 fetch 성공"),
    FunnelStage(5, "폴(Pole) 자동 검출"),
    FunnelStage(6, "플래그(Flag) 자동 검출"),
    FunnelStage(7, "거래량 수축"),
    FunnelStage(8, "ATR(14) > 0"),
    FunnelStage(9, "최종 prepared"),
)


def _empty_scan_stats() -> dict:
    return {
        # 2026-08-08 확대 — 전체 상장 합집합 (시총·거래대금 컷 *전* 원천, VCP/kojiro 정합)
        "universe_union": 0,
        "universe_candidates": 0,
        "universe_filtered": 0,
        "candle_fetch_ok": 0,
        "pole_pass": 0,
        "flag_pass": 0,
        "volume_contraction_pass": 0,
        "atr_pass": 0,
        "final_prepared": 0,
        "min_trade_amount_failed": 0,  # 사이클 23 P1-2 — 거래대금 미달 카운터
        # cycle228 (A6) — 실게이트 카운터. cycle227 의 `vol_gate_observe_*` 는
        # **은퇴**했다(같은 would_pass 의 매매 귀결이 "안 샀다"→"샀다" 로 반전되므로
        # 키를 유지하면 과거 집계와 뒤섞인다). 로그는 cap 이 걸리지만 이 카운터는
        # cap 과 무관하게 매 사건 누적된다(총량은 API 로 관측).
        "vol_gate_pass": 0,
        "vol_gate_reject_ext": 0,
        "vol_gate_no_data": 0,
        "latch_armed_count": 0,
        # cycle228 (A5) — 감지/후퇴 진동 총량 (8/26 실측 473행/일 → 로그는 cap,
        # 규모 측정은 이 카운터가 담당)
        "breakout_seen_count": 0,
        "breakout_retreat_count": 0,
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
        # 폴 (사이클 48, 2026-05-27 — Pole 검출 0건 결함 완화)
        "pole_lookback_min": 3,
        "pole_lookback_max": 10,
        "pole_min_return": 15.0,    # 사이클 48 — 20.0→15.0. 한국 ±30% 환경 + 음봉 45% 와 교집합 0 차단
        "pole_max_red_ratio": 0.45,  # 사이클 48 — 0.30→0.45. 강한 폴도 1~2일 음봉 정상
        # 플래그
        "flag_lookback_min": 2,  # 사이클 198 — 3→2. 한국 급등주 얕은 2일 눌림 포착 (flag_volume_ratio 안전장치 보전)
        "flag_lookback_max": 10,
        "flag_retracement_max": 0.5,  # 사이클 211 — 0.382→0.5. 폴+플래그 통과 3.3배 (funnel 병목 완화, flag_volume_ratio 안전장치 절대 불변)
        "flag_volume_ratio": 0.60,
        # 매수
        "breakout_volume_mult": 2.0,
        "entry_start": "09:05",
        "entry_end": "13:00",
        # cycle228 (A4) — 추격 상한. 래치는 돌파 시점이 아니라 **거래량 충족 시점**에
        # 사므로, 그사이 급등한 종목을 추격하지 않도록 current_price 기준 상한을 건다.
        # 트레이더 규칙 한 줄 = "손절선이 돌파선 위로 올라가는 가격에서는 사지 않는다"
        # (stop −5% → entry ≤ flag_high/0.95 = +5.26% → 보수적 내림 5.0).
        # ⚠️ **리터럴 고정** — stop_loss_rate 는 PARAM_RANGES 멤버라 런타임 도출이면
        # AI 야간 튜닝에 캡이 함께 끌려간다. 도출 관계는 `_check_extension_cap_invariant`
        # 가 부팅 시 관찰만 한다. PARAM_RANGES/INT_PARAMS 편입 금지(진입 정체성 상수).
        "max_breakout_extension_pct": 5.0,
        "position_ratio": 0.25,
        "max_positions": 4,
        # 청산
        "stop_loss_rate": -5.0,
        "atr_period": 14,
        "atr_trail_mult": 2.0,
        # 사이클 C (2026-07-30) — 브레이크이븐 승격 (default-off 배포, VCP 동형 live ATR 래치).
        # 0.0 = 비활성 기본. PARAM_RANGES/INT_PARAMS 미편입 (청산 정체성 상수).
        "breakeven_promote_atr": 0.0,
        "max_hold_days": 5,
        "reentry_cooldown_days": 3,
        # ── 터틀 유닛 sizing + 하드손절 ATR화 (B-2 게이트 2 미러, 2026-08-03) ──
        # VCP(`vcp_breakout.py`)와 정확히 동형 이식. **다크런치**: 기본 position_ratio →
        # 배포 시 행위 byte 동일. DB 토글로만 활성. 게이트는 `sizing_mode` 가 아니라
        # `_entry_atr` 스탬프 존재 — position_ratio 매수는 미스탬프라 기존 −5% 경로를
        # 그대로 탄다. `turtle_backstop_pct`/`turtle_min_stop_pct` 는 VCP 대비 완화값
        # (BFB 기존 하드손절이 −5%로 VCP −7%보다 이미 타이트해서 밴드도 동행 축소).
        # 전 키 PARAM_RANGES/INT_PARAMS 미편입 (사이징/청산 정체성 상수).
        "sizing_mode": "position_ratio",
        "risk_pct": 0.005,
        "stop_atr": 2.0,
        "turtle_backstop_pct": -7.0,
        "min_vol_floor_pct": 1.0,
        "turtle_min_stop_pct": -4.0,
        # 유니버스 (2026-08-08 확대 — BFB 는 이미 지수 무제약. 거래대금 20억→15억(도메인 권고 —
        # 장중 돌파 추격이라 kojiro 10억까지는 슬리피지 위험, 완만한 15억 하향으로 유동성 바닥
        # 보존) + max_scan 100→4000(전체 filtered 커버, refreshed_at DESC 임의 절단 소멸).
        # 시총 하한 = 100억(사용자 결정 — 라이브 DB 값 유지, 소형주 포함. 거래대금 15억이 방어).
        "min_market_cap": 10_000_000_000,
        "min_trade_amount": 1_500_000_000,
        "max_scan_stocks": 4000,
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
        # 사이클 C — 브레이크이븐 승격 boolean 래치 (live ATR 팽창 un-latch 병리 방지)
        self._breakeven_latched: set[str] = set()
        # B-2 게이트 2 미러 — 터틀 진입 ATR 스냅샷. 존재 = ATR 하드손절 활성 (자연 게이트).
        self._entry_atr: dict[str, float] = {}
        # P1 (2026-08-06) — 청산 파라미터 영속 맵 (VCP 동형). `_candidates` 는
        # `prepare()` 마다 와이프되고 **보유 종목은 셋업이 무너져 후보 자격을 잃는 게
        # 정상**이라, 청산이 거기 단독 의존하면 T+1 아침부터 §2 flag_low·
        # §3 measured-move 익절·§4 트레일링이 통째로 침묵하고 고정 손절만 남는다.
        #   - `flag_low`/`pole_start`/`pole_high`/`flag_high` = 구조 레벨 → BUY 직전
        #     stamp 후 **불변**
        #   - `atr14` = 지표 → boot 훅이 **이미 fetch 하는 일봉으로 매일 갱신**
        # ⚠️ `_reset_daily_state` 에서 clear 금지 — 멀티데이 보유가 밤새 소멸한다.
        self._position_setup: dict[str, dict] = {}
        # cycle228 (A5/A6) — 게이트·래치·진동 로그 emit cap: (ticker, 종류) 1회/일.
        # 날짜 키 자기 리셋(`_reset_daily_state` 훅 미의존 — scheduler.py diff 0
        # 이 설계 목표). cap 키에 종류를 넣는 이유 = cycle225 교훈(ticker 단독이면
        # 먼저 난 사건이 나중 사건을 삼킨다).
        self._gate_emit_capped: set[tuple[str, str]] = set()
        self._gate_emit_day: date | None = None
        # cycle228 (A2) — 충족 래치. "오늘 retention 을 이미 통과했다" 만 기억한다.
        # 엔트리 = {armed_at, armed_date, flag_high, flag_low}: 레벨을 박제해 두고
        # live 레벨이 이동하면 해제한다(무장 근거 소멸 — prepare 장중 재실행 대비).
        # 날짜 키 자기 리셋(어제 래치는 읽는 순간 무효).
        self._vol_latch: dict[str, dict] = {}
        # cycle228 (A4) — 부팅 불변식 WARNING 1회만(재-prepare 스팸 방지). "첫
        # prepare() 시 1회" 명세 — 인스턴스 수명 동안 1회로 고정.
        self._extension_cap_invariant_checked: bool = False

    # ------------------------------------------------------------------
    # prepare — 일봉 fetch → 폴/플래그 자동 검출
    # ------------------------------------------------------------------
    async def prepare(self) -> None:
        import asyncio

        # 사이클 173 (2026-06-22) — 일봉 source KIS → DB 어댑터 전환 (행위 보존).
        from src.db.stock_master_daily import get_recent_daily_normalized

        # cycle228 (A4/G-7) — 추격 상한 ↔ 손절 도출 관계 부팅 관찰 (VCP 동형 직접
        # 호출 — 위반 시 prepare 마다 재경고되는 것이 오히려 옳다, fail-open).
        # `prepare()` 본체는 DB/KIS 호출이라 단위 테스트로 못 돌리므로 헬퍼를 직접
        # 검증하고 배선만 AST 가드(G-7)가 확인한다(cycle224 hoist 조합).
        self._check_extension_cap_invariant()

        params = self.config.params
        pole_max = params["pole_lookback_max"]
        flag_max = params["flag_lookback_max"]
        atr_period = params["atr_period"]
        fetch_days = pole_max + flag_max + atr_period + 10  # 여유

        self._candidates = {}
        stats = _empty_scan_stats()
        self._scan_stats = stats
        # 사이클 39 (2026-05-22) — 단계별 ticker 캡처 reset
        self._reset_funnel_steps(FUNNEL_STAGES)

        # 사이클 163 (2026-06-18) — stock_master 0건 race 자동 재시도 hook (cap 3회 + sleep 30s).
        # 6/18 08:24:25 운영 사고 영구 차단 (사이클 158 VB 패턴 답습).
        tickers = await self._scan_universe()
        for retry_attempt in range(3):
            if tickers:
                break
            logger.warning(
                "[bfb_prepare_retry] stock_master 0건 — %d초 후 재시도 (cap=%d/3)",
                30, retry_attempt + 1,
            )
            await asyncio.sleep(30)
            self._candidates = {}
            stats = _empty_scan_stats()
            self._scan_stats = stats
            self._reset_funnel_steps(FUNNEL_STAGES)
            tickers = await self._scan_universe()
        # 사이클 39 — 1단계: 유니버스 후보 + 2단계: 유니버스 필터 (시총·거래대금 컷 통과)
        # `_scan_universe` 내부에서 ranked → filtered 분리. `_scan_stats` 가 이미 양쪽 카운트.
        # 단계별 ticker 정확 캡처는 `_scan_universe` 가 후보 리스트와 통과 리스트 둘 다 반환해야
        # 가능. 현재는 통과 리스트만 반환 → 1단계는 통과 카운트 (raw ranked 는 미보유).
        # 사이클 47 (2026-05-22, refactor-review 카드 #3) — FUNNEL_STAGES 위임
        # 사이클 170 카드 C — step_conditions 구버전 등락률 순위 문구 → 실제 소스 정합.
        # 사이클 108 부터 stock_master.list_by_filter 기반 (KIS 거래량순위 API 폐기).
        # 2026-08-08 확대 — step0=union(컷 전 전체상장)/step1=trade(시총·거래대금 컷 통과)
        # 배선 (kojiro/VCP 패턴). 이전엔 둘 다 survived=tickers 라 step0/step1 collapse.
        stage_counts = getattr(self, "_scan_stage_counts", None) or {}
        union_tickers = stage_counts.get("union_tickers", tickers)
        trade_tickers = stage_counts.get("trade_tickers", tickers)
        self._record_funnel_pipeline_step(
            FUNNEL_STAGES[0],
            survived=union_tickers,
            step_conditions="전체 상장 (지수 무제약) 원천 유니버스 후보 (시총·거래대금 컷 전)",
        )
        self._record_funnel_pipeline_step(
            FUNNEL_STAGES[1],
            survived=trade_tickers,
            step_conditions=(
                f"시총 ≥ {params['min_market_cap']/100_000_000:.0f}억 "
                f"+ 거래대금 ≥ {params['min_trade_amount']/100_000_000:.0f}억"
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
            logger.info("눌림목 돌파 유니버스 0종목")
            self._scanned_tickers = []
            stats["last_run_at"] = datetime.now(KST).isoformat()
            return

        today_str = datetime.now(KST).strftime("%Y%m%d")

        # 사이클 173 — DB 우선 어댑터 (락/신선도/부족 시 KIS 폴백). min_required=35 명시 (자문 §4).
        async def _fetch_one(ticker: str):
            try:
                return ticker, await get_recent_daily_normalized(
                    ticker, days=fetch_days, min_required=35,
                )
            except Exception as e:
                logger.warning("눌림목 일봉 fetch 실패: %s — %s", ticker, e)
                return ticker, None

        fetched = await asyncio.gather(*[_fetch_one(t) for t in tickers])

        # 사이클 39 — 단계별 ticker 캡처 (회귀 가드 — 결과 무변경)
        # 사이클 41 (2026-05-22) — 탈락 사유 (수치 포함) 캡처 추가
        candle_fetch_ok_tickers: list[str] = []
        pole_pass_tickers: list[str] = []
        # 사이클 50 (2026-06-01) — 플래그/거래량수축 단계별 생존 추적 (계측 정밀화)
        flag_pass_tickers: list[str] = []
        atr_pass_tickers: list[str] = []
        final_prepared_tickers: list[str] = []
        # 사이클 41 — 단계별 탈락 sample (수치 포함)
        candle_fetch_excluded: list[dict] = []
        pole_excluded: list[dict] = []
        atr_excluded: list[dict] = []
        # 사이클 50 — 폴 검출 4 sub-condition 을 funnel step 4/5/6 에 정밀 분배
        flag_excluded: list[dict] = []           # step 5 (플래그 조정폭)
        volume_contraction_excluded: list[dict] = []  # step 6 (거래량 수축)

        for ticker, candles in fetched:
            from src.engine.strategy_base import _resolve_ticker_name
            ticker_name = _resolve_ticker_name(ticker)
            if candles is None or not candles:
                # 사이클 41 — 일봉 fetch 실패 사유 캡처
                candle_fetch_excluded.append({
                    "ticker": ticker, "name": ticker_name,
                    "reason": "KIS 일봉 응답 빈/None",
                })
                continue
            try:
                # 부분봉 가드 — candles[0] 이 오늘이면 [1] 부터 사용
                prev_idx = 1 if candles[0].get("stck_bsop_date") == today_str else 0
                required_len = prev_idx + pole_max + flag_max + 2
                if len(candles) <= required_len:
                    candle_fetch_excluded.append({
                        "ticker": ticker, "name": ticker_name,
                        "reason": f"일봉 길이 {len(candles)} < 필요 {required_len+1}",
                    })
                    continue
                if prev_idx:
                    candles = candles[prev_idx:]
                stats["candle_fetch_ok"] += 1
                candle_fetch_ok_tickers.append(ticker)  # 사이클 39

                # 사이클 50 (2026-06-01) — 단계별 실패 사유 계측. 검출 결과(result) 무변경,
                # fail_stage/detail 로 funnel step 4/5/6 정밀 분배 (근본 원인 3 시정).
                result, fail_stage, detail = self._detect_pole_and_flag_detailed(candles)
                if not result:
                    if fail_stage == "flag_retracement":
                        # step 5 (플래그 조정폭) 바인딩 — 폴(상승률+음봉)은 통과
                        stats["pole_pass"] += 1
                        pole_pass_tickers.append(ticker)
                        flag_excluded.append({
                            "ticker": ticker, "name": ticker_name,
                            "reason": (
                                f"플래그 조정 폭 {detail.get('retracement', 0)*100:.1f}% > "
                                f"폴 폭 × {params['flag_retracement_max']*100:.1f}% "
                                f"(폴 +{detail.get('best_return', 0):.1f}%)"
                            ),
                        })
                    elif fail_stage == "volume_contraction":
                        # step 6 (거래량 수축) 바인딩 — 폴+플래그조정 모두 통과,
                        # 거래량만 미수축. 06/01 운영 가설 (거래량순위 = 폭발 ⊥ 수축).
                        stats["pole_pass"] += 1
                        stats["flag_pass"] += 1
                        pole_pass_tickers.append(ticker)
                        flag_pass_tickers.append(ticker)
                        volume_contraction_excluded.append({
                            "ticker": ticker, "name": ticker_name,
                            "reason": (
                                f"거래량 수축 미달 — 플래그/폴 평균 거래량 비율 "
                                f"{detail.get('vol_ratio', 0)*100:.0f}% ≥ "
                                f"임계 {params['flag_volume_ratio']*100:.0f}% "
                                f"(폴 +{detail.get('best_return', 0):.1f}%, "
                                f"수축 조건은 비율 < 임계 요구)"
                            ),
                        })
                    else:
                        # step 4 (폴 상승률/음봉비율) 바인딩 또는 no_candle
                        if fail_stage == "pole_red_ratio":
                            reason = (
                                f"폴 음봉 비율 {detail.get('red_ratio', 0)*100:.0f}% > "
                                f"임계 {params['pole_max_red_ratio']*100:.0f}% "
                                f"(폴 상승률 +{detail.get('best_return', 0):.1f}%)"
                            )
                        elif fail_stage == "pole_return":
                            reason = (
                                f"폴 상승률 +{detail.get('best_return', 0):.1f}% < "
                                f"임계 +{params['pole_min_return']:.0f}%"
                            )
                        else:
                            reason = detail.get("reason", "폴 검출 실패 (유효 조합 없음)")
                        pole_excluded.append({
                            "ticker": ticker, "name": ticker_name,
                            "reason": reason,
                        })
                    continue
                stats["pole_pass"] += 1
                stats["flag_pass"] += 1
                pole_pass_tickers.append(ticker)  # 사이클 39
                flag_pass_tickers.append(ticker)  # 사이클 50

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
                    atr_excluded.append({
                        "ticker": ticker, "name": ticker_name,
                        "reason": "ATR 계산 실패 (값 ≤ 0)",
                    })
                    continue
                stats["atr_pass"] += 1
                atr_pass_tickers.append(ticker)  # 사이클 39

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
                final_prepared_tickers.append(ticker)  # 사이클 39
            except Exception as e:
                logger.warning("눌림목 prepare 실패: %s — %s", ticker, e)
                continue

        # 사이클 47 + 157 — FUNNEL_STAGES 위임 (사이클 157 step 3 master block 후 인덱스 +1)
        self._record_funnel_pipeline_step(
            FUNNEL_STAGES[3],
            survived=candle_fetch_ok_tickers, excluded=candle_fetch_excluded,
            step_conditions=f"KIS 일봉 ≥ {pole_max + flag_max + 3}일",
        )
        self._record_funnel_pipeline_step(
            FUNNEL_STAGES[4],
            survived=pole_pass_tickers, excluded=pole_excluded,
            step_conditions=(
                f"3~10영업일 누적 +{params['pole_min_return']:.0f}%↑ + "
                f"음봉 비율 ≤ {params['pole_max_red_ratio']*100:.0f}%"
            ),
        )
        # 사이클 50 (2026-06-01) — step 5(플래그 조정폭)/6(거래량 수축) 정밀 분배.
        # 기존엔 둘 다 survived=pole_pass_tickers + excluded=None 이라 어느 조건이
        # 바인딩인지 계측 불가 (근본 원인 3). 이제 단계별 생존/탈락 분리.
        # step 6 거래량 수축 생존 = 검출 완전 통과 종목 (flag_pass 중 수축 탈락 제외).
        vol_excluded_set = {e["ticker"] for e in volume_contraction_excluded}
        volume_contraction_pass_tickers = [
            t for t in flag_pass_tickers if t not in vol_excluded_set
        ]
        self._record_funnel_pipeline_step(
            FUNNEL_STAGES[5],
            survived=flag_pass_tickers, excluded=flag_excluded,
            step_conditions=f"3~10영업일 조정 폭 ≤ 폴 폭 × {params['flag_retracement_max']*100:.1f}%",
        )
        self._record_funnel_pipeline_step(
            FUNNEL_STAGES[6],
            survived=volume_contraction_pass_tickers,
            excluded=volume_contraction_excluded,
            step_conditions=f"플래그 평균 거래량 < 폴 평균 × {params['flag_volume_ratio']*100:.0f}%",
        )
        self._record_funnel_pipeline_step(
            FUNNEL_STAGES[7],
            survived=atr_pass_tickers, excluded=atr_excluded,
            step_conditions="ATR(14) > 0 (변동성 측정 가능)",
        )
        self._record_funnel_pipeline_step(
            FUNNEL_STAGES[8],
            survived=final_prepared_tickers,
            step_conditions="모든 단계 통과 — 매수 후보 등록",
        )

        self._scanned_tickers = list(self._candidates.keys())
        self._bought_today.clear()
        stats["last_run_at"] = datetime.now(KST).isoformat()
        logger.info(
            "눌림목 돌파 준비 완료: %d/%d종목 — pole=%d flag=%d vol_cnt=%d atr=%d",
            stats["final_prepared"], len(tickers),
            stats["pole_pass"], stats["flag_pass"],
            stats["volume_contraction_pass"], stats["atr_pass"],
        )

    # 사이클 50 (2026-06-01) — 단계별 실패 사유 우선순위 (멀리 도달할수록 큰 값).
    # `_detect_pole_and_flag_detailed` 가 "가장 멀리 도달한" 조합의 바인딩 단계를
    # 보고하는 데 사용 (funnel step 4/5/6 사유 분배의 근거).
    _FAIL_STAGE_ORDER = {
        "": 99,                    # 통과 (어떤 fail 보다 우선)
        "no_candle": 0,            # 일봉 파싱/길이 실패
        "pole_return": 1,          # 폴 상승률 임계 미달
        "pole_red_ratio": 2,       # 음봉 비율 초과
        "flag_retracement": 3,     # 플래그 조정 폭 초과
        "volume_contraction": 4,   # 거래량 수축 미달
    }

    def _detect_pole_and_flag(self, candles: list[dict]) -> dict | None:
        """일봉(최신순) → 폴/플래그 자동 검출 (기존 계약 유지 — dict | None).

        사이클 50 (2026-06-01): 내부 구현을 `_detect_pole_and_flag_detailed` 로 위임하고
        result 만 반환하는 thin wrapper. 모든 기존 호출처/테스트 계약 무변경 (행위 보존).
        """
        result, _fail_stage, _detail = self._detect_pole_and_flag_detailed(candles)
        return result

    def _detect_pole_and_flag_detailed(
        self, candles: list[dict]
    ) -> tuple[dict | None, str, dict]:
        """폴/플래그 자동 검출 + 단계별 실패 사유 계측 (사이클 50, 2026-06-01).

        candles[0] 이 가장 최근 영업일. flag 종료 = candles[0:flag_len],
        그 이전 = pole 구간 (candles[flag_len:flag_len+pole_len]).
        다양한 (pole_len, flag_len) 조합을 시도해 처음 통과하는 셋업을 반환.

        근본 원인 3 (진단 인프라 결함) 시정 — 실패 시 `None` 만 반환하던 기존 동작을
        "가장 멀리 도달한 sub-condition" + 측정 수치 보고로 확장. 사이클 49 VCP
        `last_pullback_pct 항상 기록` 동일 계열. 검출 결과(result) 자체는 무변경.

        Returns:
            (result, fail_stage, detail)
            - result: 통과 시 dict (기존과 동일), 실패 시 None
            - fail_stage: 통과 시 "" / 실패 시 가장 멀리 도달한 조합의 바인딩 단계
              ("pole_return"/"pole_red_ratio"/"flag_retracement"/"volume_contraction"
               /"no_candle")
            - detail: 가장 멀리 도달한 조합의 측정 수치 dict
              (best_return / red_ratio / retracement / vol_ratio / pole_len / flag_len)
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
            return None, "no_candle", {"reason": "일봉 파싱 실패"}

        # 가장 멀리 도달한 실패 조합 추적 (사이클 50 — 바인딩 단계 계측)
        best_fail_stage = "no_candle"
        best_fail_detail: dict = {"reason": "유효한 (pole_len, flag_len) 조합 없음"}
        best_fail_rank = -1

        def _note_fail(stage: str, detail: dict) -> None:
            nonlocal best_fail_stage, best_fail_detail, best_fail_rank
            rank = self._FAIL_STAGE_ORDER.get(stage, 0)
            if rank > best_fail_rank:
                best_fail_rank = rank
                best_fail_stage = stage
                best_fail_detail = detail

        # 다양한 (flag_len, pole_len) 조합 시도
        # 가장 짧은 셋업 우선 (최근 신호)
        for flag_len in range(flag_min, flag_max + 1):
            if flag_len > len(candles):
                break
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

                # (1) 폴 상승률
                pole_return_pct = (pole_high - pole_start) / pole_start * 100
                if pole_return_pct < min_return:
                    _note_fail("pole_return", {
                        "best_return": round(pole_return_pct, 1),
                        "min_return": min_return,
                        "pole_len": pole_len, "flag_len": flag_len,
                    })
                    continue

                # (2) 음봉 비율
                red_count = sum(
                    1
                    for o, c in zip(pole_slice_opens, pole_slice_closes)
                    if o > 0 and c < o
                )
                red_ratio = red_count / pole_len if pole_len > 0 else 1.0
                if red_ratio > max_red_ratio:
                    _note_fail("pole_red_ratio", {
                        "best_return": round(pole_return_pct, 1),
                        "red_ratio": round(red_ratio, 2),
                        "max_red_ratio": max_red_ratio,
                        "pole_len": pole_len, "flag_len": flag_len,
                    })
                    continue

                # (3) 플래그 조정 폭 ≤ 폴 폭의 retracement_max
                pole_width = pole_high - pole_start
                if pole_width <= 0:
                    continue
                actual_retracement = (pole_high - flag_low) / pole_width
                if actual_retracement > retracement_max:
                    _note_fail("flag_retracement", {
                        "best_return": round(pole_return_pct, 1),
                        "retracement": round(actual_retracement, 3),
                        "retracement_max": retracement_max,
                        "pole_len": pole_len, "flag_len": flag_len,
                    })
                    continue

                # (4) 거래량 수축
                pole_avg_volume = sum(pole_slice_vols) / pole_len if pole_len > 0 else 0
                if pole_avg_volume <= 0:
                    continue
                vol_ratio = flag_avg_volume / pole_avg_volume if pole_avg_volume > 0 else 99.0
                if flag_avg_volume >= pole_avg_volume * flag_vol_ratio:
                    _note_fail("volume_contraction", {
                        "best_return": round(pole_return_pct, 1),
                        "vol_ratio": round(vol_ratio, 2),
                        "flag_volume_ratio": flag_vol_ratio,
                        "pole_len": pole_len, "flag_len": flag_len,
                    })
                    continue

                # 통과
                return (
                    {
                        "pole_start": pole_start,
                        "pole_high": pole_high,
                        "flag_high": flag_high,
                        "flag_low": flag_low,
                        "flag_avg_volume": int(flag_avg_volume),
                        "pole_len": pole_len,
                        "flag_len": flag_len,
                    },
                    "",
                    {
                        "best_return": round(pole_return_pct, 1),
                        "red_ratio": round(red_ratio, 2),
                        "retracement": round(actual_retracement, 3),
                        "vol_ratio": round(vol_ratio, 2),
                        "pole_len": pole_len, "flag_len": flag_len,
                    },
                )

        return None, best_fail_stage, best_fail_detail

    async def _scan_universe(self) -> list[str]:
        """stock_master DB 기반으로 시총·거래대금 조건 종목을 스캔한다 (사이클 108).

        사이클 108 (Plan Phase A) — 사전 적재된 stock_master (~2,800종목,
        사이클 101/106 _full_universe_load_task_loop) 를 DB 필터링으로 대체한다.
        사이클 48 도입 이유였던 "acml_vol=0 시간 의존 결함" 은 stock_master DB 조회로
        근본 해소된다 (DB는 24h TTL 갱신 기반으로 시간 의존이 없음).
        KIS API 직접 호출 0건.
        hts_avls (시가총액, 백만원 단위) 는 사이클 108 inquire_stock_basics 5-key merge 에서
        stock_master.raw 에 적재됨.
        """
        from src.db import stock_master as _sm_mod
        from src.engine.scanner import ETF_KEYWORDS, ticker_names

        p = self.config.params
        min_mcap = p.get("min_market_cap", 10_000_000_000)  # DEFAULT_PARAMS 정합 (2026-08-08 확대, 이전 500억 스테일)
        min_trade = p.get("min_trade_amount", 1_500_000_000)
        max_stocks = p.get("max_scan_stocks", 4000)

        # 사이클 156 Q0 — nxt_tradable 강제 필터 제거 (주문 시점 분기용으로만 활용).
        # 2026-08-08 확대 — return_stage_counts 로 합집합(union) 노출 (VCP/kojiro 정합).
        # BFB 는 이미 지수 무제약(is_kospi200/is_kosdaq150 미전달 = None)이라 소스는 전체 상장.
        try:
            rows, stage = await _sm_mod.list_by_filter(
                min_market_cap=min_mcap,
                min_trade_amount=min_trade,
                limit=max_stocks,
                return_stage_counts=True,
            )
        except Exception:
            # 2026-08-08 — VCP 와 graceful 대칭 (이전 BFB 는 미포장 → prepare 로 전파)
            logger.exception(
                "BFB stock_master.list_by_filter 호출 실패 graceful — 빈 list 반환"
            )
            self._scan_stage_counts = {}
            self._scan_stats["universe_union"] = 0
            self._scan_stats["universe_candidates"] = 0
            self._scan_stats["universe_filtered"] = 0
            self._scan_stats["last_run_at"] = datetime.now(KST).isoformat()
            return []

        # 2026-08-08 확대 — 합집합(union) 노출 (시총·거래대금 컷 *전* 원천)
        self._scan_stage_counts = stage
        self._scan_stats["universe_union"] = len(stage.get("union_tickers", rows))
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

        self._scan_stats["universe_filtered"] = len(filtered)
        self._scan_stats["last_run_at"] = datetime.now(KST).isoformat()

        if not filtered:
            from src.db.system_logs import write_log

            msg = (
                f"눌림목 돌파 유니버스 0종목 — stock_master {len(rows)}건 중 "
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

    _PREPARE_LOG_LABEL = "bfb"  # refactor-review A1·A2 — base 위임 로그 접두사

    # ------------------------------------------------------------------
    # 외부 노출 (사전 구독, 깔때기, 대시보드)
    # ------------------------------------------------------------------
    def get_scanned_tickers(self) -> list[str]:
        return self._scanned_tickers

    def get_scan_stats(self) -> dict:
        return dict(self._scan_stats)

    def get_targets_status(self) -> dict[str, dict]:
        """대시보드 후보 그리드용 — "왜 안 사는가" 진단 필드 포함 (P3a, 2026-08-06).

        BFB 특유의 `breakout_seen_at`(retention 대기)이 핵심이다 — 첫 돌파 감지 후
        `breakout_retention_minutes` 동안 `Signal.NONE` 을 돌려주며 대기하는데,
        지금은 로그에만 남아 "돌파했는데 왜 안 샀나"에 화면으로 답할 수 없었다.

        ⚠️ VB 호환 5키는 `scheduler._confirm_breakout_open_prices`(8영역) 소비
        계약 — **제거 금지, 추가만**.
        """
        from src.engine.scanner import resolve_ticker_name

        today = datetime.now(KST).date()
        mult = self.config.params["breakout_volume_mult"]
        retention = self.config.params["breakout_retention_minutes"]
        out: dict[str, dict] = {}
        for ticker, info in self._candidates.items():
            flag_high = info.get("flag_high", 0)
            pole_width = info.get("pole_high", 0) - info.get("pole_start", 0)
            seen = self._breakout_first_seen.get(ticker)
            cd = self._cooldown_until.get(ticker)
            out[ticker] = {
                "pole_start": info.get("pole_start", 0),
                "pole_high": info.get("pole_high", 0),
                "flag_high": flag_high,
                "flag_low": info.get("flag_low", 0),
                "atr14": info.get("atr14", 0),
                # 진단 필드
                "name": resolve_ticker_name(ticker),
                "prev_close": info.get("prev_close", 0),
                "stop_line": info.get("flag_low", 0),          # 이탈 시 STOP_LOSS
                "measured_target": (flag_high + pole_width) if (pole_width > 0 and flag_high > 0) else 0,
                "volume_threshold": int(info.get("flag_avg_volume", 0) * mult),
                "bought_today": ticker in self._bought_today,
                "in_cooldown": bool(cd and cd > today),
                "cooldown_until": cd.isoformat() if cd else None,
                "breakout_seen_at": seen.isoformat() if seen else None,
                "retention_minutes": retention,
                # VB 호환 (제거 금지)
                "k": 0.0,
                "target_price": flag_high,
                "open_price": 0,
                "target_offset": 0,
                "open_confirmed": True,
            }
        return out

    def _roll_gate_day_if_needed(self) -> None:
        """cycle228 — 날짜 전환 시 emit cap + `_breakout_first_seen` 자기 리셋.

        `_vol_latch` 는 entry 별 `armed_date` 로 이미 자기 무효화된다(`_latch_entry`).
        `_breakout_first_seen` 는 그런 개별 타임스탬프 검증이 없어, 날짜를 넘기면
        "어제 감지"가 오늘 retention 완주로 오인되어 SEEN 로그 없이 곧장 게이트로
        떨어질 수 있다 — 여기서 함께 정리한다. `_reset_daily_state`(scheduler 훅)
        에 의존하지 않는다(scheduler.py diff 0 설계 목표, cycle227 tick_volume 패턴).
        """
        today = datetime.now(KST).date()
        if self._gate_emit_day != today:
            # ⚠️ `_breakout_first_seen` 정리는 **진짜 날짜 전환**(어제→오늘)에만 —
            # 첫 호출 초기화(None→오늘)까지 지우면 부팅 직전/테스트가 심어 둔
            # 정당한 대기 상태를 삼킨다(정산 리셋과 같은 의미의 자기 방어일 뿐,
            # 초기화는 리셋이 아니다).
            if self._gate_emit_day is not None:
                self._breakout_first_seen.clear()
            self._gate_emit_day = today
            self._gate_emit_capped.clear()

    def _gate_should_emit(self, ticker: str, kind: str) -> bool:
        """cycle228 — 게이트·래치·진동 로그 cap: (ticker, kind) 1회/일.

        P1-3 실측(8/26 감지+후퇴 473행/일, 고유 종목 4개)이 cap 의 근거다.
        `_scan_stats` 카운터는 이 cap 과 무관하게 매 사건 누적된다(총량은 API 로
        관측). 날짜 롤오버는 `_roll_gate_day_if_needed`(check_buy_signal 최상단)
        가 담당 — 호출자가 그보다 먼저 호출됐음을 전제한다.
        """
        key = (ticker, kind)
        if key in self._gate_emit_capped:
            return False
        self._gate_emit_capped.add(key)
        return True

    def _latch_entry(self, ticker: str) -> dict | None:
        """cycle228 (A2) — 오늘자 래치 엔트리. 날짜가 지났으면 읽는 순간 무효."""
        ent = self._vol_latch.get(ticker)
        if ent is None:
            return None
        if ent.get("armed_date") != datetime.now(KST).date():
            self._vol_latch.pop(ticker, None)
            return None
        return ent

    def _arm_latch(self, ticker: str, flag_high: int, flag_low: int) -> None:
        """cycle228 (A2) — 충족 래치 무장. **이미 무장돼 있으면 호출하지 마라**
        (armed_at 이 리셋되면 `latch_age_sec` 측정이 무너진다 — 호출부 계약)."""
        now_kst = datetime.now(KST)
        self._scan_stats["latch_armed_count"] += 1
        self._vol_latch[ticker] = {
            "armed_at": now_kst,
            "armed_date": now_kst.date(),
            "flag_high": flag_high,
            "flag_low": flag_low,
        }
        if self._gate_should_emit(ticker, "latch_armed"):
            logger.info(
                "[bfb_latch_armed] ticker=%s flag_high=%d flag_low=%d — retention "
                "통과·거래량 대기(재평가는 flag_high 이상 틱에서만)",
                ticker, flag_high, flag_low,
            )

    def _release_latch(self, ticker: str, reason: str) -> None:
        self._vol_latch.pop(ticker, None)
        if self._gate_should_emit(ticker, "latch_released"):
            logger.info("[bfb_latch_released] ticker=%s reason=%s", ticker, reason)

    def _check_extension_cap_invariant(self) -> None:
        """cycle228 (A4) — 추격 상한 리터럴 ↔ 손절 도출 관계 관찰 (fail-open).

        캡의 도출식 = `(1/(1+stop/100) − 1)×100` ("손절선이 돌파선 위로 가면 추격").
        값은 리터럴로 못박았으므로(AI 튜닝 비노출) 여기서는 **관계만 관찰**한다:
        - `derived < cap` = 실질 위반(최대 확장 진입의 손절선이 돌파선 위)
        - `derived − cap > 1.0` = 도출 스테일(AI 가 stop 을 넓혀 캡이 상대적으로 3배
          타이트해지는 류 — 값 자동 보정은 금지, 운영자 실측 근거 보존)
        """
        try:
            cap = float(self.config.params.get("max_breakout_extension_pct", 0.0))
            stop = float(self.config.params.get("stop_loss_rate", 0.0))
            if cap <= 0 or stop >= 0:
                return
            derived = (1.0 / (1.0 + stop / 100.0) - 1.0) * 100.0
            if derived < cap - 1e-9 or (derived - cap) > 1.0:
                logger.warning(
                    "[extension_cap_invariant] cap=%.1f stop_loss_rate=%.1f "
                    "derived=%.2f — 리터럴 캡과 손절 도출값이 어긋났다(자동 보정 "
                    "금지 — 사람이 판단)",
                    cap, stop, derived,
                )
        except Exception:
            return  # 관찰기 자기실패가 prepare 를 막으면 안 된다

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
        flag_low = info.get("flag_low", 0)
        if flag_high <= 0 or current_price <= 0:
            return Signal.NONE

        # cycle228 — 날짜 전환 시 emit cap + `_breakout_first_seen` 자기 리셋.
        # `_vol_latch` 는 entry 별 `armed_date` 로 이미 자기 무효화되지만(`_latch_entry`),
        # `_breakout_first_seen` 는 그런 개별 타임스탬프 검증이 없어 날짜를 넘기면
        # "어제 감지"가 오늘 retention 완주로 오인될 수 있다. `_reset_daily_state`
        # (scheduler 훅)에 의존하지 않는다(scheduler.py diff 0 설계 목표).
        self._roll_gate_day_if_needed()

        # cycle228 (A2) — 충족 래치 재평가. retention 상태 기계보다 **앞선다** —
        # 래치는 "오늘 retention 을 이미 통과했다"만 기억하므로, 무장 중엔 edge-
        # crossing 상태 기계로 돌아가지 않는다(재무장/오탐 방지).
        latch = self._latch_entry(ticker) if ticker in self._vol_latch else None
        if latch is not None:
            if latch["flag_high"] != flag_high or latch["flag_low"] != flag_low:
                # 무장 당시 레벨이 라이브에서 이동 — `prepare()` 장중 재실행으로
                # 골대가 옮겨졌으니 무장 근거가 사라졌다(자문 Q1 "못박을 것 2").
                self._release_latch(ticker, "level_moved")
                return Signal.NONE
            if flag_low > 0 and current_price < flag_low:
                # 베이스 소멸 — `flag_low` 이탈은 §2 손절선과 동일 정의다. 돌파할
                # 대상이 없어졌으니 이 셋업은 오늘 끝이다.
                self._release_latch(ticker, "stop_line")
                return Signal.NONE
            if current_price < flag_high:
                # 플래그 안 — 래치는 유지하되 아무것도 안 한다(가격 조건 우회 금지).
                return Signal.NONE
            # flag_high 이상 틱에서만 거래량 게이트 재평가.
            return self._evaluate_vol_gate(ticker, info, current_price, flag_high, latch)

        # 사이클 23 P2-1 — breakout_retention_minutes 유지시간 가드 (기존 상태
        # 기계, cycle228 변경 0 — 명세 A2 "edge-crossing 등 기존 진입 로직 무변경".
        # ⚠️ `_prev_price` 는 **이 fresh 경로에서만** read-then-write 한다 — 래치
        # 재평가 경로(위)에서 건드리면 "붕괴가 만든 거래량으로 죽은 셋업을 사는"
        # 역선택이 미관측 재무장으로 되살아난다(001450 회귀, flag_low 이탈 후
        # 되돌아온 가격은 **진짜 edge-crossing 없이는** 재평가되지 않아야 한다).
        prev = self._prev_price.get(ticker, 0)
        self._prev_price[ticker] = current_price
        now_kst = datetime.now(KST)
        retention_min = int(self.config.params.get("breakout_retention_minutes", 3))

        first_seen = self._breakout_first_seen.get(ticker)
        if first_seen is not None:
            # 이미 돌파 대기 중
            if current_price < flag_high:
                # 후퇴 — 대기 종료. cycle228 (A5) — 한글 문구 byte 보존, emit 만 cap.
                self._breakout_first_seen.pop(ticker, None)
                self._scan_stats["breakout_retreat_count"] += 1
                if self._gate_should_emit(ticker, "retreat"):
                    logger.info("BFB 돌파 후퇴(retention 대기 종료): %s", ticker)
                return Signal.NONE
            elapsed = (now_kst - first_seen).total_seconds()
            if elapsed < retention_min * 60:
                # 아직 대기 중
                return Signal.NONE
            # retention 충족 — 정상 흐름 (거래량 게이트로 진행)
            self._breakout_first_seen.pop(ticker, None)
        else:
            # 첫 돌파 감지 여부 확인 (prev<flag_high AND now>=flag_high)
            if not (prev < flag_high <= current_price):
                return Signal.NONE
            if retention_min > 0:
                # 첫 돌파 감지 → 대기 등록 + NONE. cycle228 (A5) — 한글 문구 byte
                # 보존, emit 만 cap(8/26 실측 247행/일 → cap 이후 ~수행).
                self._breakout_first_seen[ticker] = now_kst
                self._scan_stats["breakout_seen_count"] += 1
                if self._gate_should_emit(ticker, "seen"):
                    logger.info(
                        "BFB 돌파 1차 감지(retention 대기 시작): %s flag_high(%d) retention=%d분",
                        ticker, flag_high, retention_min,
                    )
                return Signal.NONE
            # retention_min == 0 이면 즉시 진행 (기존 동작 회귀)

        # retention 완주(또는 retention_min==0 즉시 진행) — 최초 거래량 게이트 평가.
        return self._evaluate_vol_gate(ticker, info, current_price, flag_high, None)

    def _evaluate_vol_gate(
        self, ticker: str, info: dict, current_price: int, flag_high: int, latch: dict | None,
    ) -> Signal:
        """cycle228 (A1/A4) — 실측 거래량 게이트 + 추격 상한. **소스 = `tick_volume` 뿐.**

        `latch` 가 `None` 이면 이번 호출이 최초 평가(retention 완주 직후)이고,
        dict 면 이미 무장된 래치의 재평가다(`latch_age_sec` 계산에 사용).

        미관측(`None`) = fail-closed. `0` sentinel 금지 계약은 `tick_volume` 자체가
        보장한다(cycle227). `tick_volume.get_observed_acml_vol` 은 **호출 시점**
        모듈 참조로 불러야 관측기 자기실패 경로를 테스트로 재현할 수 있다.
        """
        from src.engine import tick_volume

        vol_threshold = int(
            info["flag_avg_volume"] * self.config.params["breakout_volume_mult"]
        )
        try:
            observed = tick_volume.get_observed_acml_vol(ticker)
        except Exception:
            # team-leader 판정(미결 2) — 읽기 실패는 미관측(no_data)과 동일 취급한다.
            # fail-closed 유지 + 예외가 check_buy_signal 밖으로 새는 것을 차단한다
            # (P1-5 류 — on_tick 이 죽으면 그 종목의 청산 평가까지 멈춘다).
            logger.debug(
                "[bfb_vol_gate_read_failed] ticker=%s 관측 읽기 실패 — no_data 로 처리",
                ticker, exc_info=True,
            )
            observed = None

        if observed is None:
            self._scan_stats["vol_gate_no_data"] += 1
            if self._gate_should_emit(ticker, "no_data"):
                logger.warning(
                    "[bfb_vol_gate_no_data] ticker=%s threshold=%d — 미관측 fail-closed",
                    ticker, vol_threshold,
                )
            if latch is None:
                self._arm_latch(ticker, flag_high, info.get("flag_low", 0))
            return Signal.NONE

        if observed < vol_threshold:
            if latch is None:
                self._arm_latch(ticker, flag_high, info.get("flag_low", 0))
            return Signal.NONE

        # 거래량 충족 — 추격 상한 검사(A4). 판정은 `current_price` 단독
        # (`daily_high`/`ticker_prices` 금지 — donchian 이식 시 그 커플링이 딸려온다).
        cap = float(self.config.params.get("max_breakout_extension_pct", 0) or 0)
        ext_pct = (current_price - flag_high) / flag_high * 100 if flag_high > 0 else 0.0
        if cap > 0 and ext_pct > cap:
            self._scan_stats["vol_gate_reject_ext"] += 1
            if self._gate_should_emit(ticker, "reject_ext"):
                logger.info(
                    "[bfb_vol_gate_reject] ticker=%s reason=extension current_price=%d "
                    "flag_high=%d ext_pct=%.2f cap=%.1f",
                    ticker, current_price, flag_high, ext_pct, cap,
                )
            if latch is None:
                self._arm_latch(ticker, flag_high, info.get("flag_low", 0))
            return Signal.NONE

        latch_age_sec = 0
        if latch is not None:
            latch_age_sec = int((datetime.now(KST) - latch["armed_at"]).total_seconds())
        self._vol_latch.pop(ticker, None)

        # 진입 확정
        self._bought_today.add(ticker)
        # P1 — 청산 파라미터 영속화(당일 매수분). 내일 아침 prepare 가 `_candidates`
        # 를 와이프해도 §2 flag_low / §3 measured-move / §4 트레일링이 살아남는다.
        self._position_setup[ticker] = {
            "flag_low": info.get("flag_low", 0),
            "flag_high": info.get("flag_high", 0),
            "pole_high": info.get("pole_high", 0),
            "pole_start": info.get("pole_start", 0),
            "atr14": info.get("atr14", 0),
        }
        self._scan_stats["vol_gate_pass"] += 1
        logger.info(
            "[bfb_vol_gate_pass] ticker=%s observed=%d threshold=%d latch_age_sec=%d",
            ticker, observed, vol_threshold, latch_age_sec,
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

    # cycle228-B — 구조 레벨(진입 시점 확정 후 **불변**) 키. 지표(atr14)는 여기 없다.
    _STRUCTURE_KEYS = ("flag_low", "flag_high", "pole_high", "pole_start")

    def _effective_setup(self, ticker: str) -> dict:
        """청산 파라미터 리졸버 — 구조 레벨 stamp 우선 + 지표 live 우선 (cycle228-B).

        P1 계약("구조 레벨은 BUY 직전 stamp 후 불변, 지표만 매일 갱신")을 리졸버
        자신의 live 통째 우선이 우회하던 결함 시정 — `prepare()` 는 보유 종목을
        후보에서 제외하지 않으므로, 보유 중 새 폴/플래그가 재검출되면 §2 손절선이
        새 `flag_low`(진입가보다 높을 수 있다)로 갈아타 상승 포지션을 조기
        손절시키고 §3 측정된 이동 타겟도 진입 근거와 무관해진다.

        병합 규약 = live 사본 위에 stamp 의 구조 키만 덮는다(stamp 의 `0` 결손도
        그대로 — live 로 메우면 결함이 부분 부활한다, §2 는 결손 시 미발화가 계약).
        stamp 부재(재시작 직후 등)는 기존 live 폴백 그대로. 미지 종목은 빈 dict.
        구조 레벨이 실제로 어긋난 빈도는 `[setup_structure_conflict]` 로 관측한다
        (1회/(ticker)/일 — cycle228-A 래치와 같은 날 배포라 D+1 귀인 분리 목적).
        """
        candidate = self._candidates.get(ticker)
        stamp = self._position_setup.get(ticker)
        if candidate and stamp:
            merged = dict(candidate)
            conflict = False
            for key in self._STRUCTURE_KEYS:
                if key in stamp:
                    if key in merged and merged[key] != stamp[key]:
                        conflict = True
                    merged[key] = stamp[key]
            if conflict:
                self._roll_gate_day_if_needed()
                if self._gate_should_emit(ticker, "setup_conflict"):
                    logger.info(
                        "[setup_structure_conflict] ticker=%s — 보유 중 재검출된 "
                        "live 구조 레벨이 진입 stamp 와 다르다(§2/§3 은 stamp 사용). "
                        "stamp=%s live=%s",
                        ticker,
                        {k: stamp.get(k) for k in self._STRUCTURE_KEYS},
                        {k: candidate.get(k) for k in self._STRUCTURE_KEYS},
                    )
            return merged
        if candidate:
            return candidate
        return stamp or {}

    def check_exit_signal(self, ticker, current_price, open_price) -> Signal:
        pos = self.state.positions.get(ticker)
        if not pos:
            return Signal.NONE

        params = self.config.params
        loss_rate = (
            (current_price - pos.buy_price) / pos.buy_price * 100
            if pos.buy_price > 0 else 0
        )
        # P1 — `_candidates` 단독 의존 폐기. 와이프돼도 영속 셋업으로 청산이 산다.
        info = self._effective_setup(ticker)

        # 1) 하드 손절 — `_entry_atr` 스탬프 존재가 ATR 손절의 자연 게이트 (VCP 답습).
        #    `sizing_mode` 로 게이팅하면 DB 토글 하나로 **기보유 포지션의 손절 규약**이
        #    바뀌므로 금지 (donchian 2A-2 원칙). 미스탬프 = position_ratio 매수 →
        #    기존 -5% 경로 byte 동일.
        entry_atr = self._entry_atr.get(ticker, 0.0)
        if entry_atr > 0 and pos.buy_price > 0:
            stop_atr = float(params.get("stop_atr", 2.0))
            base_stop = pos.buy_price - stop_atr * entry_atr
            # 최소 폭 밴드 — 저ATR 종목에서 2ATR 이 기존 -5% 보다 타이트해지는 과도 조임 방지.
            min_stop_pct = float(params.get("turtle_min_stop_pct", 0.0) or 0.0)
            if min_stop_pct < 0:
                base_stop = min(base_stop, pos.buy_price * (1 + min_stop_pct / 100.0))
            # 브레이크이븐 승격 — entry_atr 스냅샷 기준. tighten-only (max 로만 이동).
            breakeven_mult = float(params.get("breakeven_promote_atr", 0) or 0)
            if (
                breakeven_mult > 0
                and pos.high_since_buy >= pos.buy_price + breakeven_mult * entry_atr
            ):
                base_stop = max(base_stop, float(pos.buy_price))
            if base_stop > 0 and current_price <= base_stop:
                logger.info(
                    "[bfb_turtle_stop] %s 손절선(%d) = 매수가(%d) − %.1f×entry_atr(%.1f)",
                    ticker, int(base_stop), pos.buy_price, stop_atr, entry_atr,
                )
                return Signal.STOP_LOSS
            # % backstop — 고ATR 종목의 손절 폭 최대 캡 (ATR 손절 미발화 구간 방어).
            backstop = float(params.get("turtle_backstop_pct", 0.0) or 0.0)
            if backstop < 0 and loss_rate <= backstop:
                logger.info(
                    "[bfb_turtle_backstop] %s 매수가(%d) 대비 %.1f%% ≤ %.1f%%",
                    ticker, pos.buy_price, loss_rate, backstop,
                )
                return Signal.STOP_LOSS
        else:
            stop_loss = params["stop_loss_rate"]
            if loss_rate <= stop_loss:
                logger.info(
                    "눌림목 손절: %s 매수가(%d) 대비 %.1f%%",
                    ticker, pos.buy_price, loss_rate,
                )
                return Signal.STOP_LOSS

        # 1.5) 브레이크이븐 승격 (사이클 C, default-off — live ATR 래치, tighten-only)
        # 터틀 스탬프 포지션은 위 §1 의 스냅샷 승격이 담당 → `entry_atr <= 0` 로 게이팅해
        # 두 tighten 메커니즘 공존을 차단한다 (VCP 답습). position_ratio 경로는 행위 변화 0.
        # VCP C-V1 동형 — `_candidates[ticker]["atr14"]` live ATR 사용, 승격 후 ATR 팽창
        # 시 조건이 다시 거짓이 되는 un-latch 병리 방지를 위한 boolean 래치.
        if entry_atr <= 0:
            breakeven_mult = float(params.get("breakeven_promote_atr", 0) or 0)
            if breakeven_mult > 0:
                atr_live = info.get("atr14", 0) if info else 0
                if (
                    ticker not in self._breakeven_latched
                    and atr_live > 0
                    and pos.high_since_buy >= pos.buy_price + breakeven_mult * atr_live
                ):
                    self._breakeven_latched.add(ticker)
                    logger.info(
                        "[bfb_breakeven_promote] %s 고점(%d) ≥ 매수가(%d)+%.1f×ATR(%d) → 래치",
                        ticker, pos.high_since_buy, pos.buy_price, breakeven_mult, int(atr_live),
                    )
                if ticker in self._breakeven_latched and current_price <= pos.buy_price:
                    logger.info(
                        "[bfb_breakeven_promote] %s 래치 승격 발화 — 현재가(%d) ≤ 매수가(%d)",
                        ticker, current_price, pos.buy_price,
                    )
                    return Signal.STOP_LOSS

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
            # `.get()` 방어 — 영속 셋업이 부분 재채움된 경우 직접 인덱싱은 KeyError 로
            # `check_exit_signal` 전체를 죽인다. 키 결손 시엔 **미발화**가 계약이다
            # (임의 기본값으로 익절을 쏘면 과잉 청산).
            pole_high = info.get("pole_high", 0) or 0
            pole_start = info.get("pole_start", 0) or 0
            flag_high = info.get("flag_high", 0) or 0
            pole_width = pole_high - pole_start
            measured_target = flag_high + pole_width if (pole_width > 0 and flag_high > 0) else 0
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

    def calc_buy_quantity(self, current_price: int, ticker: str | None = None) -> int:
        """할당 자금의 position_ratio 비중. 예산 잔여로 클램프(`_apply_budget_limit`).

        B-2 게이트 2 미러 — `sizing_mode="turtle"` + ticker 지정 시 터틀 유닛 sizing 우선.
        터틀이 0(변동성 floor / 잔여 부족 / 예외) 반환 시 position_ratio 낙하 =
        `_entry_atr` 미스탬프 = 기존 % 손절 경로 유지.
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
        """터틀 유닛 수량 + `_entry_atr` 원자 스탬프 (VCP `_turtle_buy_quantity` 답습).

        `_candidates[ticker]["atr14"]`(prepare 시점 ATR)를 sizing 과 하드손절 entry_atr
        양쪽에 **동일 사용** — 이 구조적 동일성이 리스크 커플링 불변식의 열쇠다.
        `compute_unit_qty_guarded` 의 notional 상한(`position_ratio × 예산`) 덕분에
        터틀 수량 ≤ 비중 수량이 항상 성립 = 전환은 순수 축소 방향.
        0 반환 시 호출자가 position_ratio 로 낙하 = 미스탬프.
        """
        try:
            from src.engine.turtle_sizing import compute_unit_qty_guarded

            info = self._candidates.get(ticker) or {}
            atr = float(info.get("atr14") or 0)
            budget = int(self.state.total_investment)
            qty = compute_unit_qty_guarded(
                budget, atr, current_price,
                float(self.config.params.get("risk_pct") or 0),
                remaining_budget=max(0, budget - self._calc_used_funds()),
                min_vol_pct=float(self.config.params.get("min_vol_floor_pct", 1.0)),
                position_ratio=float(self.config.params.get("position_ratio") or 0),
            )
            if qty > 0:
                self._entry_atr[ticker] = atr
                return qty
        except Exception:
            logger.debug("[bfb_turtle_sizing_fallback] %s — position_ratio 낙하",
                         ticker, exc_info=True)
        return 0

    def register_cooldown_after_exit(self, ticker: str) -> None:
        """청산 완료 후 호출 — 쿨다운 1단계 즉시 등록 (사이클 191 영업일 2단계).

        1단계: 즉시 달력일 근사(days + 2)로 세팅 → 재매수 공백 0 보장.
        2단계: _refine_cooldown_business_days 가 async KIS 호출로 정확한 N영업일로 정정.
        OrderEngine.on_position_closed 훅에서 호출 (사이클 185 배선 영속).
        """
        days = self.config.params["reentry_cooldown_days"]
        today = datetime.now(KST).date()
        self._cooldown_until[ticker] = today + timedelta(days=days + 2)
        # 사이클 23 P2-1 — 청산 후 retention 대기 상태 정리
        self._breakout_first_seen.pop(ticker, None)
        # 매수 1회 가드도 함께 해제 (당일 매도 set 이 차단하므로 영향 없음)

    def _reset_daily_state(self) -> None:
        """사이클 23 P2-1 — 일일 초기화 시 _breakout_first_seen 정리.

        ⚠️ `_position_setup` / `_entry_atr` 는 **절대 clear 하지 마라** — BFB 는
        `max_hold_days` 까지 실질 멀티데이 보유라 청산 규약이 밤새 소멸한다.
        """
        self._breakout_first_seen.clear()

    # ── P1.5 (2026-08-06) — 재시작 복구 ──────────────────────────────────────
    #
    # BFB 는 `_execute_next_day_clear` 대상도 `_force_clear_main_only` 대상도 아니고
    # `check_force_clear()==[]` 라 **최대 `max_hold_days`+2 달력일 실질 멀티데이
    # 보유**다. 종전 문서의 "BFB 는 익일 청산이라 재시작 복구 불필요"는 거짓이었고,
    # 그 전제 위에서 복구 배선이 통째로 생략돼 있었다.
    #
    # 재시작 시 `_entry_atr` 소실 → ATR 하드손절이 고정 −5% 로 무단 강등되고,
    # `high_since_buy` 는 `_boot()` 이 DB row 로 Position 을 재생성하며 매수가로
    # 리셋된다(H-1 과 동일 병리).
    #
    # 배선은 `boot_manager` 가 담당한다 — `_SWING_POLL_STRATEGIES` 에 BFB 를 넣으면
    # 그 상수가 매수 폴루프·구독에도 쓰여 **매수 행위가 바뀐다**(절대 금지).

    _HIGH_RECOVER_LABEL = "눌림목"
    _ENTRY_ATR_REDERIVE_LABEL = "bfb"
    _COOLDOWN_LOG_LABEL = "[bfb]"  # refactor-review A3 — base 위임 로그 접두사

    _SETUP_LEVEL_KEYS = ("flag_low", "flag_high", "pole_high", "pole_start")

    def _refresh_position_setup_from_candles(self, ticker: str, pos, candles: list[dict]) -> None:
        """보유 종목의 청산 파라미터를 최신 일봉으로 정비한다 (VCP 동형).

        - **지표** (`atr14`) → 매번 재계산.
        - **구조 레벨** (`flag_low`/`flag_high`/`pole_high`/`pole_start`) → 진입 시점
          셋업에서 확정된 값이라 **이미 있으면 건드리지 않는다**. 없을 때만
          (=프로세스 재시작으로 소실) `_candidates` 보강 → 그것도 없으면 **매수일
          *이전* 봉으로 폴/플래그 재검출**을 시도한다. 실패 시 미복구로 남긴다 —
          잘못된 레벨로 손절·익절선을 긋느니 §1 하드손절/§5 시간청산에 맡긴다
          (fail-safe, 절대 현행보다 나빠지지 않는다).

        어떤 실패도 흡수 — 갱신 실패 시 기존 값이 남아 청산은 계속 산다.
        """
        if not candles:
            return
        try:
            highs = [int(c.get("stck_hgpr", "0") or 0) for c in candles]
            lows = [int(c.get("stck_lwpr", "0") or 0) for c in candles]
            closes = [int(c.get("stck_clpr", "0") or 0) for c in candles]
            atr = self._atr(highs, lows, closes, self.config.params["atr_period"])

            cur = dict(self._position_setup.get(ticker) or {})
            live = self._candidates.get(ticker) or {}
            for k in self._SETUP_LEVEL_KEYS:
                if not cur.get(k) and live.get(k):
                    cur[k] = live[k]
            if any(not cur.get(k) for k in self._SETUP_LEVEL_KEYS):
                for k, v in self._rederive_setup_levels(ticker, pos, candles).items():
                    if not cur.get(k) and v:
                        cur[k] = v
            if atr > 0:
                cur["atr14"] = int(atr)
            if cur:
                self._position_setup[ticker] = cur
        except Exception:
            logger.exception("[bfb_setup_refresh] 청산 셋업 갱신 실패 fail-open: %s", ticker)

    def _rederive_setup_levels(self, ticker: str, pos, candles: list[dict]) -> dict:
        """매수일 **이전** 봉만으로 폴/플래그를 재검출한다 (실패 시 빈 dict).

        매수일 당일/이후 봉을 섞으면 돌파 이후 구간이 플래그에 포함돼 레벨이
        왜곡된다. 검출은 진입 시점 조건(`pole_min_return` 등)에 민감해 재현되지
        않을 수 있고, 그 경우 **빈 dict** 를 돌려 호출자가 미복구로 남긴다.
        """
        try:
            if pos is None or not getattr(pos, "buy_date", None):
                return {}
            buy_dd = pos.buy_date.strftime("%Y%m%d")
            prior = [c for c in candles if str(c.get("stck_bsop_date", "")) < buy_dd]
            p = self.config.params
            if len(prior) < p["pole_lookback_min"] + p["flag_lookback_min"]:
                return {}
            det = self._detect_pole_and_flag(prior)
            if not det:
                return {}
            out = {k: det.get(k, 0) for k in self._SETUP_LEVEL_KEYS}
            logger.info("[bfb_setup_rederive] %s flag_low=%s flag_high=%s (매수일 이전 봉 재검출)",
                        ticker, out.get("flag_low"), out.get("flag_high"))
            return out
        except Exception:
            logger.exception("[bfb_setup_rederive] 구조 레벨 재검출 실패: %s", ticker)
            return {}

    async def recompute_high_since_buy(self) -> None:
        """보유 종목의 재시작 복구 — `_entry_atr` 재도출 + 청산 지표 갱신 + 고점 복구.

        VCP `recompute_high_since_buy` 이식. 종목별 sequential await (KIS Rate Limit
        안전 — `asyncio.gather` 금지). 일봉 fetch 예외/빈 응답은 해당 종목만 skip.

        고점 복구는 `StrategyBase._apply_high_since_buy_from_candles` **단일 진실원**
        에 위임한다 (전략별 복사본 금지).
        """
        from src.api.condition import fetch_daily_candles

        params = self.config.params
        atr_period = params["atr_period"]
        pole_max = params["pole_lookback_max"]
        flag_max = params["flag_lookback_max"]
        today = datetime.now(KST).date()

        for ticker in list(self.state.positions.keys()):
            pos = self.state.positions.get(ticker)
            if not pos:
                continue
            if pos.buy_date >= today:
                if pos.buy_date > today:
                    logger.warning(
                        "눌림목 high_since_buy 보정 skip — buy_date 비정상(미래): "
                        "%s buy_date=%s today=%s",
                        ticker, pos.buy_date, today,
                    )
                continue

            days_held = (today - pos.buy_date).days
            fetch_days = max(days_held + 5, pole_max + flag_max + atr_period + 10, 10)
            try:
                candles = await fetch_daily_candles(ticker, days=fetch_days)
            except Exception:
                logger.exception("눌림목 재시작 복구 일봉 fetch 실패: %s", ticker)
                continue
            if not candles:
                continue
            # in-memory 스탬프가 살아 있으면(당일 매수·미재시작) 그게 정확한 진입 ATR.
            if ticker not in self._entry_atr:
                self._rederive_entry_atr(ticker, pos, candles, atr_period)
            self._refresh_position_setup_from_candles(ticker, pos, candles)
            await self._apply_high_since_buy_from_candles(pos, candles, today)

    def on_position_closed(self, ticker: str) -> None:
        """사이클 185 — 포지션 청산 시 partial_exit 보유결합 상태 정리 + 재진입 쿨다운 등록 (사이클 191).

        사이클 C (C-B4) — 브레이크이븐 래치 정리 동행 (재진입 stale 차단).
        B-2 게이트 2 미러 — 터틀 entry_atr 정리 동행 (재진입 stale 스냅샷 차단).
        """
        self._partial_exit.pop(ticker, None)
        self._breakeven_latched.discard(ticker)
        self._entry_atr.pop(ticker, None)
        # P1 — 영속 청산 셋업 정리 (재진입 시 stale 구조 레벨로 손절하는 것 차단).
        self._position_setup.pop(ticker, None)
        self.register_cooldown_after_exit(ticker)
        coro = self._refine_cooldown_business_days(ticker)
        try:
            asyncio.create_task(coro)
        except RuntimeError:
            coro.close()  # 이벤트 루프 없는 환경 — coroutine 명시적 닫기, 근사값 유지
