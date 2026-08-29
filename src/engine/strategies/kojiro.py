"""고지로(小次郎) 대순환 스윙 전략 (EMA 5/20/40 대순환 스테이지 + ATR 손절/트레일링).

추세추종 계열. donchian_swing 의 직계 확장 — "질서정연한 추세"를 EMA 정렬 상태로 포착.

진입 (strict `evaluate_entry`, 조기진입 Phase1 OFF):
- 현재 스테이지 1 (단기>중기>장기)
- 최근 `stage1_freshness`(5)영업일 내 6→1 전환 (갓 진입한 신선한 스테이지 1)
- EMA 5/20/40 모두 우상향
- 전일 종가 > EMA5
- (유니버스 게이트) ATR/종가 밴드 1.0~6.0% (대순환/변동성 판별, 비협상)
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
from datetime import date, datetime, time, timezone, timedelta

import pandas as pd

from src.engine.daily_emit_cap import DailyEmitCap
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
    FunnelStage(1, "전체 상장 유니버스 (시총/거래대금 컷 전)"),
    FunnelStage(2, "시총+거래대금 컷 통과"),
    FunnelStage(3, "1단계 진입 차단 통과 (거래정지/관리/단기과열/투자유의 등)"),
    FunnelStage(4, "일봉 fetch + 전일종가>0 + 워밍업봉 충족"),
    # ★ 대순환/변동성 판별 1차 필터 (도메인 (b) 비협상) — verdict 키워드 '변동성'/'ATR'/'밴드'
    FunnelStage(5, "ATR/종가 변동성 밴드 통과 (1.0~6.0%)"),
    FunnelStage(6, "스테이지 판별 가능 (EMA 동가 제외)"),
    FunnelStage(7, "스테이지1 + 3선 우상향"),
    FunnelStage(8, "6→1 전환 인접 + 종가>EMA5 (대순환 진입 확정)"),
    FunnelStage(9, "최종 후보"),
)


# 섹터/테마 동시보유 캡용 — KRX 산업지수 플래그(프로그램 basket = 실 상관구조).
_KOJIRO_KRX_SECTOR_FLAGS: tuple[tuple[str, str], ...] = (
    ("krx_smcn_yn", "반도체"), ("krx_car_yn", "자동차"), ("krx_bio_yn", "바이오"),
    ("krx_bank_yn", "은행"), ("krx_scrt_yn", "증권"), ("krx_insu_yn", "보험"),
    ("krx_enrg_chms_yn", "에너지화학"), ("krx_stel_yn", "철강"),
    ("krx_medi_cmnc_yn", "미디어통신"), ("krx_cnst_yn", "건설"),
    ("krx_ship_yn", "조선"), ("krx_trnp_yn", "운송"),
)


def _kojiro_sector_key(master_raw: dict | None, ticker: str) -> str:
    """섹터/테마 캡용 섹터 키 (측정 Phase 1 로직과 동일).

    KRX 산업지수 플래그(주) → 업종 대분류(bstp_larg_div_code ≠"0000") →
    중분류(≠"0000") → `미분류-{ticker}`(독립, 클러스터 미포함 = fail-open).
    "0000" catch-all 은 독립 취급 (거짓 클러스터 인플레 차단). bstp_smal 은 전량 "0000"이라 미사용.
    """
    if isinstance(master_raw, dict) and master_raw:
        for key, name in _KOJIRO_KRX_SECTOR_FLAGS:
            if str(master_raw.get(key, "")).strip().upper() == "Y":
                return name
        larg = str(master_raw.get("bstp_larg_div_code", "") or "").strip()
        if larg and larg != "0000":
            return f"업종-{larg}"
        medm = str(master_raw.get("bstp_medm_div_code", "") or "").strip()
        if medm and medm != "0000":
            return f"중분류-{medm}"
    return f"미분류-{ticker}"


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


# 후보 점수 랭킹 (원설계 §9④) — MACD3 기울기·띠폭 확장률 계산 봉 수 (노이즈 억제).
_RANK_LOOKBACK = 3


def _stage_transition_distance(stages: list, from_stage: int, to_stage: int, within: int) -> int | None:
    """최근 within봉 내 from→to 인접 전환의 마지막 봉 기준 거리(봉). 없으면 None.

    거리 0 = 마지막 봉으로 전환(가장 신선). `_stage_recently` 의 거리 반환 버전.
    """
    st = [s for s in stages[-(within + 1):]]
    last = len(st) - 1
    best: int | None = None
    for j in range(len(st) - 1):
        if st[j] == from_stage and st[j + 1] == to_stage:
            best = last - (j + 1)   # j 증가 → 더 최근 → best 덮어써 최소 거리
    return best


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
        "stage1_freshness": 5,       # 6→1 전환 인접 판정 봉수 (2026-07-20 백테스트: 3→5 PF 1.60→1.75)
        # ── ATR/종가 변동성 밴드 (비협상 필수, 정체성 상수) ──
        "atr_ratio_min": 0.01,       # 1.0%
        "atr_ratio_max": 0.06,       # 6.0% (2026-07-20 백테스트: 0.045→0.06 PF 0.86→1.60)
        # ── 손절/트레일 배수 (kojiro 고유명 — atr_trail_mult 재사용 금지, PARAM_RANGES 제외) ──
        "stop_atr": 2.0,             # 2ATR 하드손절
        "trail_atr": 2.5,            # 2.5ATR 샹들리에 트레일링
        "hard_stop_pct": -8.0,       # 고정 % 하드손절 (ATR 독립 backstop)
        "breakeven_promote_atr": 0.0,   # 브레이크이븐 승격 임계 (0=비활성 다크런치, 활성 시 1.5 권장 — donchian P1 선례)
        # ── 진입 게이트 (정체성 상수, PARAM_RANGES 제외) ──
        "gap_up_skip_pct": 5.0,      # 갭업 ≥5% 스킵
        "gap_down_skip_pct": -4.0,   # 갭다운 ≤-4% 스킵
        # ── 유니버스/사이징 (donchian 동형 — 자동튜닝 수용) ──
        "min_market_cap": 50_000_000_000,    # 500억
        "min_trade_amount": 1_000_000_000,   # 10억
        # 2026-07 — 전체 상장 전환. 지수(348) 제거 후 유니버스 = 전체상장 ∩ 필터 ≈ 979.
        # limit 이 union/후보 쿼리 상한 → FUNNEL step1(전체상장 union) 실수치(≈3577) 노출
        # 위해 전체 상장 종목수 이상(4000)으로 설정. 후보(979)·이하 단계는 무영향
        # (mcap/trade 필터가 실제 상한). union fetch 는 prepare 시점 off-peak 1회.
        "max_scan_stocks": 4000,
        "exclude_tickers": [],
        "nxt_tradable": None,
        "position_ratio": 0.20,
        "max_positions": 5,
        "daily_loss_limit": -8.0,
        # 섹터/테마 동시보유 캡 (동일섹터 ≤ N, 매수 게이트 전용·fail-open). domain-consult:
        # 대순환은 섹터 단위 정렬 → 5종목 한 섹터 집중 → 테마 붕괴 시 동시 청산불가(±30% 하한가 락).
        # 0=off. PARAM_RANGES 제외(리스크 정체성 상수, AI 튜닝 금지). Phase 1 측정 = 활성일 ~17% 바인딩.
        "max_positions_per_sector": 2,
        # Σ 오픈리스크 캡 (매수 게이트 전용, 예산 대비 %). 0 = 비활성.
        # 개수 캡(max_positions)은 **유지하고 추가**한다 — 터틀의 유닛 캡이 통제하려던
        # 대상은 Σ 리스크이고 유닛 개수는 프록시일 뿐이다. 프록시는 "1유닛 = 상수
        # 리스크" 일 때만 정확한데, (1)소액 계좌 수량 절삭 (2)atr_ratio>4% 에서
        # hard_stop_pct −8% 가 2ATR 을 자름 (3)flip 이전 position_ratio 포지션 혼재
        # 때문에 헐거워진다. 08-04 실측 = "6포지션(=6유닛)" 이 실제로는 3.2유닛
        # (총리스크 22,390원 = 예산 3.2%), 포지션별 편차 8.3배.
        # 4.5% = 4.5유닛 상당. max_positions 6 × 유닛 1.0% = 6.0% 보다 낮게 잡아,
        # 리스크가 작은 포지션은 6개까지 허용하되 full-size 유닛은 4~5개에서 멈춘다
        # (터틀 유닛 캡의 본래 의미). PARAM_RANGES 제외 = 리스크 정체성 상수.
        "max_open_risk_pct": 4.5,
        # ── 후보 점수 랭킹 (원설계 §9④, PARAM_RANGES 제외 = 정체성 상수) ──
        # 후보 > 슬롯/섹터캡 경합 시 최적 셋업 우선. 이미 계산되나 dormant 였던 enrich
        # 지표(macd3 기울기·band_width 확장) + 6→1 신선도를 후보풀 min-max 정규화 가중합.
        # 매수 후보 정렬만 조정 — 자격/청산 무변경. 합≠1 이면 자동 정규화.
        "rank_w_macd3": 0.4,
        "rank_w_band": 0.3,
        "rank_w_fresh": 0.3,
        # ── 터틀 유닛 sizing (Phase 2A-1, PARAM_RANGES 제외 = AI 자동튜닝 금지) ──
        # sizing_mode='turtle' opt-in 시 unit=floor(전략예산×risk_pct/ATR). 기본 position_ratio.
        # risk_pct 0.5% = 도메인 권장(KR 갭리스크).
        # ⚠️ max_units_per_stock / max_units_total 은 **소비처 0건 = 미사용 상태**이며
        #    현재 어떤 것도 강제하지 않는다(안전장치 아님). 피라미딩(2C) 도입 전까지는
        #    1포지션 = 1유닛이 항등이라 max_units_total 은 max_positions 와 동치이고,
        #    max_units_per_stock=2 는 도달 자체가 불가능한 상한이다. 피라미딩 검토 시
        #    배선할 예정 — 그 전까지 이 키를 리스크 한도로 오인하지 말 것
        #    (실효 한도는 max_positions + max_open_risk_pct + 예산 클램프 삼중).
        # min_vol_floor_pct — `compute_unit_qty_guarded` 변동성 floor (donchian 동일 규약).
        # 유닛 명목 비중 = risk_pct ÷ (ATR/price) 라 저변동 종목일수록 폭증한다
        # (atr_ratio 1% → 예산의 50% 단일종목 집중). floor + notional 상한이 이를 차단.
        "sizing_mode": "position_ratio",
        "risk_pct": 0.005,
        "min_vol_floor_pct": 1.0,
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
        # cycle231 (P2-5) — 값 = `(판정 수행일 KST, stage==3)`. §3 는 유일하게 가격을
        # 안 보는 청산이라 **오늘 판정만** 소비한다(프로세스가 며칠 상주해 인메모리
        # bool 이 일 경계를 넘던 stale True 청산 차단 — `:649` fail-open 계약을
        # prepare 경로까지 통일). 판정 수행일이다(봉 날짜 아님 — 연휴 무효화 정합).
        self._held_stage3: dict[str, tuple[date, bool]] = {}
        # cycle231 — `[kojiro_stage3_stale_skip]` cap 1회/ticker/일 (날짜 키 자기
        # 리셋 — `_reset_daily_state` override 신설 금지 봉인).
        self._stage3_stale_logged: set[str] = set()
        self._stage3_stale_log_day: date | None = None
        # 2ATR 하드손절 tighten-only floor (변동성 팽창 loosen 차단, restart-H3).
        self._stop_floor: dict[str, int] = {}
        # 섹터 캡 held 집계 영속 맵(_candidates 와이프 독립, 포지션 수명 동안 생존) — 안 A.
        self._position_sectors: dict[str, str] = {}
        # 보유 종목 ATR 정본 — `_candidates` 와이프(prepare)·ATR 밴드/유니버스 이탈과
        # 독립. 이게 없으면 2ATR 하드손절이 조용히 사라진다(2026-08-04 삼영무역 실증).
        # 사이클 J `_position_sectors` 와 동일 패턴 — 포지션 수명 동안 생존.
        # ⚠️ `_reset_daily_state` override 로 clear 금지 (멀티데이 held 밤샘 소멸).
        self._position_atr: dict[str, float] = {}
        # Σ 오픈리스크 캡 로그 폭주 차단 — 보유 종목수 단위 1회 (매 틱 emit 방지).
        # 포지션이 늘거나 줄면 다시 1회 emit 되어 상태 변화는 추적된다.
        self._open_risk_cap_logged: DailyEmitCap[str] = DailyEmitCap[str]()
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
            step_conditions="전체 상장 종목 (시총/거래대금 필터 전 원천 유니버스)",
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
        rank_raw: dict[str, tuple] = {}   # 후보 랭킹 raw 3성분 (2-pass: 루프 stash → 후 정규화)
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
                        "name": name,
                    }
                    # cycle231 — (판정 수행일, 플래그) 튜플 (오늘 판정만 §3 소비)
                    self._held_stage3[ticker] = (datetime.now(KST).date(), stage == 3)
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
                    "sector": await self._fetch_sector(ticker),  # 섹터/테마 캡용
                    "name": name,
                }
                rank_raw[ticker] = self._rank_candidate_components(
                    enriched, stages_series, int(params["stage1_freshness"]))
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

        # ① 후보 점수 랭킹 (원설계 §9④): 후보 > 슬롯/섹터캡 경합 시 최적 셋업 우선.
        # get_scanned_tickers 순서 = 매수 폴루프 처리 순서 = 우선순위. 매수 정렬만 조정.
        scores = self._score_candidates(rank_raw, params)
        for _t, _sc in scores.items():
            if _t in self._candidates:
                self._candidates[_t]["score"] = _sc
        ranked_final = sorted(rank_raw.keys(), key=lambda t: scores.get(t, 0.0), reverse=True)
        held_only = [t for t in self._candidates.keys() if t not in rank_raw]  # 보유전용(청산 감시)
        self._scanned_tickers = ranked_final + held_only
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
        """전체 상장 유니버스 (시총/거래대금 필터만, 지수 고정 없음).

        2026-07 — KOSPI200∪KOSDAQ150 지수 필터 제거 (사용자 결정). is_kospi200/
        is_kosdaq150=None → 전체 상장 ∩ (min_market_cap/min_trade_amount). 실제 후보 =
        전체상장 3577 ∩ 시총500억/거래10억 ≈ 979 (필터가 상한 — 지수 348 아님).
        일봉 커버리지는 scanner._is_daily_load_universe(500억/10억)가 이 979 전량 적재.
        지수 종속 donchian 은 무관(is_kospi200/is_kosdaq150=True 유지).
        VCP 는 2026-08-08 전체 상장 전환(is_kospi200/is_kosdaq150=None) — kojiro 만 시총 500억.
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
            rows, stage = await _sm_mod.list_by_filter(
                min_market_cap=min_mcap, min_trade_amount=min_trade,
                exclude_tickers=exclude_tickers, nxt_tradable=nxt_tradable_param,
                is_kospi200=None, is_kosdaq150=None,
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

    async def _fetch_sector(self, ticker: str) -> str:
        """종목 섹터 키 산출 (master_raw). 실패 시 미분류(독립) — fail-open (섹터 캡 미차단)."""
        try:
            from src.db import stock_master as _sm_mod
            mr = await _sm_mod.get_master_raw(ticker)
            return _kojiro_sector_key(mr if isinstance(mr, dict) else None, ticker)
        except Exception:
            logger.debug("[kojiro_sector] get_master_raw 실패 graceful: %s", ticker, exc_info=True)
            return f"미분류-{ticker}"

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

    def _emit_stage3_stale_skip(self, ticker: str, judged_on: date, today_kst: date) -> None:
        """cycle231 — stale 스테이지3 True 억제 관측. cap 1회/ticker/일.

        age 1일 = INFO(정상적 하루 지연 후보) / 2일 이상 = WARNING(재판정이 이틀째
        안 돌고 있다 = 배관 열화 신호. debug 단독은 `_DbLogHandler` INFO 컷에 막혀
        `system_logs` 미도달 — cycle225 교훈). 날짜 키 자기 리셋(`_reset_daily_state`
        override 신설 금지 봉인).
        """
        if self._stage3_stale_log_day != today_kst:
            self._stage3_stale_log_day = today_kst
            self._stage3_stale_logged.clear()
        if ticker in self._stage3_stale_logged:
            return
        self._stage3_stale_logged.add(ticker)
        age_days = (today_kst - judged_on).days
        emit = logger.info if age_days <= 1 else logger.warning
        emit(
            "[kojiro_stage3_stale_skip] ticker=%s judged_on=%s age_days=%d — 오늘 "
            "재판정 없는 스테이지3 판정은 소비하지 않는다(§1·§2·§4 청산은 유지)",
            ticker, judged_on, age_days,
        )

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
                self._held_stage3[ticker] = (today, False)  # cycle231 — 오늘 판정 fail-open
                continue
            if not candles:
                logger.warning("[kojiro_recompute] 일봉 응답 없음 fail-open: %s", ticker)
                self._held_stage3[ticker] = (today, False)  # cycle231 — 오늘 판정 fail-open
                continue

            # H-1 (2026-08-06) — 트레일링 기준점 재시작 복구.
            # `risk.on_tick` 은 `high_since_buy` 를 메모리에서만 올리고 kojiro 는 DB 에
            # 되쓰는 경로가 없었다. `_boot()` 이 매 영업일 07:55 DB row 로 Position 을
            # 재생성하므로 2.5ATR 샹들리에 기준점이 **매일 아침 매수가로 리셋**됐다
            # (08-06 실측: 보유 7종목 전부 DB high == buy_price).
            #
            # 위치가 계약이다 — 아래 ATR/stage 블록보다 **앞**. 워밍업 봉 부족
            # (`len(usable) < KOJIRO_MIN_REQUIRED`)으로 그 블록이 `continue` 해도 고점
            # 복구는 수행돼야 한다(donchian E3 가 `pos_needs_high_recover` 를 ATR 필요
            # 여부와 독립 계산하는 이유와 동일).
            #
            # 이미 fetch 한 `candles` 재사용 = KIS 추가 호출 0 + **scheduler(8영역)
            # diff 0** — `recompute_held_atr` 는 `_SWING_POLL_STRATEGIES` 루프가 이미
            # 호출한다. VCP 전용 훅은 하드코딩 `_vcp` 라 거기 끼우면 8영역을 건드린다.
            if pos is not None and not isinstance(pos.buy_date, date):
                # cycle231 (W3, cycle226 L-2 동형 방어) — 비교가 try 밖이라 비정상
                # buy_date 1건의 예외가 **뒤 보유 종목의 ATR/stage3/floor 재계산까지
                # 통째로 유실**시키던 잠복 경로. 해당 종목 보정만 skip 하고 계속 간다.
                logger.warning(
                    "[kojiro_recompute] buy_date 비정상(type=%s) — high_since_buy "
                    "보정 skip, ATR/stage 재계산은 계속: %s",
                    type(pos.buy_date).__name__, ticker,
                )
            elif pos is not None and pos.buy_date < today:
                try:
                    await self._apply_high_since_buy_from_candles(pos, candles, today)
                except Exception:
                    logger.warning(
                        "[kojiro_recompute] high_since_buy 보정 실패 fail-open: %s",
                        ticker, exc_info=True,
                    )
            elif pos is not None and pos.buy_date > today:
                logger.warning(
                    "[kojiro_recompute] high_since_buy 보정 skip — buy_date 비정상(미래): "
                    "%s buy_date=%s today=%s", ticker, pos.buy_date, today,
                )

            try:
                prev_idx = 1 if candles[0].get("stck_bsop_date") == today_str else 0
                usable = candles[prev_idx:]
                if len(usable) < KOJIRO_MIN_REQUIRED:
                    self._held_stage3[ticker] = (today, False)  # cycle231 — 오늘 판정 fail-open
                    continue
                asc = list(reversed(usable))
                enriched = enrich(self._build_ohlc_df(asc), self._ind_cfg)
                last = enriched.iloc[-1]
                atr_val = float(last["atr"])
                stage = last["stage"]
                stage_int = None if (stage is None or (isinstance(stage, float) and pd.isna(stage))) else int(stage)
                prev_close = int(last["close"])
                if atr_val > 0 and prev_close > 0:
                    from src.engine.scanner import resolve_ticker_name
                    sector = await self._fetch_sector(ticker)  # 섹터 캡 카운트용(보유)
                    self._candidates[ticker] = {
                        "prev_close": prev_close, "atr": atr_val,
                        "stage": stage_int if stage_int is not None else 0,
                        "ema_s": float(last["ema_s"]), "ema_m": float(last["ema_m"]),
                        "ema_l": float(last["ema_l"]),
                        "atr_ratio": atr_val / prev_close,
                        "sector": sector,
                        "name": resolve_ticker_name(ticker),
                    }
                    # held 정본 소스 — _candidates 와이프(ATR 밴드/유니버스 이탈)와 독립 영속.
                    self._position_sectors[ticker] = sector
                    self._position_atr[ticker] = atr_val
                    # tighten-only floor 갱신
                    base = int(pos.buy_price - self.config.params["stop_atr"] * atr_val) if pos else 0
                    if base > 0:
                        self._stop_floor[ticker] = max(self._stop_floor.get(ticker, base), base)
                    # 브레이크이븐 플로어 재도출 (다크런치, breakeven_promote_atr=0 → 미진입)
                    be_mult = float(self.config.params.get("breakeven_promote_atr", 0) or 0)
                    if (be_mult > 0 and atr_val > 0 and pos and pos.buy_price > 0
                            and pos.high_since_buy >= pos.buy_price + be_mult * atr_val):
                        prev_floor = self._stop_floor.get(ticker, 0)
                        self._stop_floor[ticker] = max(prev_floor, int(pos.buy_price))
                # stage3 플래그 (None → fail-open False)
                self._held_stage3[ticker] = (today, stage_int == 3)  # cycle231
                logger.info(
                    "[kojiro_recompute] %s ATR=%.1f stage=%s stage3=%s",
                    ticker, atr_val, stage_int, self._held_stage3[ticker],
                )
            except Exception:
                logger.warning("[kojiro_recompute] 계산 실패 fail-open: %s", ticker, exc_info=True)
                self._held_stage3[ticker] = (today, False)  # cycle231 — 오늘 판정 fail-open

    # ────────────────────────── 진입 ──────────────────────────

    def check_buy_signal(self, ticker: str, current_price: int, open_price: int) -> Signal:
        """09:05~09:30 창 시장가 진입 (strict entry 후보, 갭업/갭다운/붕괴 스킵, 1회만).

        _candidates 멤버십 = prepare 에서 strict entry 4조건(스테이지1+6→1인접+3선우상향+종가>EMA5)
        + ATR밴드 확정. 여기선 시간창 + 갭 게이트만.
        """
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
        # Σ 오픈리스크 캡 — 개수 캡과 **병존**(대체 아님). 매수 게이트 전용이며
        # 청산/손절/트레일링은 절대 차단하지 않는다. 계산 실패는 fail-open.
        if self._is_open_risk_capped():
            return Signal.NONE

        info = self._candidates.get(ticker)
        # 보유 재채움 stage 데이터(stage != 1)는 매수 후보 아님 — strict entry 통과분만 매수.
        if not info or info.get("stage") != 1:
            return Signal.NONE

        # 섹터/테마 동시보유 캡 (매수 게이트 전용 — 청산/손절/트레일링/익일청산 절대 미차단).
        # 동일섹터 보유(positions ∪ pending_buys) ≥ cap 이면 3번째+ 스킵. fail-open:
        # sector 결측/미분류(독립 키) → 카운트 0 → 미차단. cap=0 → 비활성.
        sector_cap = int(self.config.params.get("max_positions_per_sector", 0) or 0)
        if sector_cap > 0:
            cand_sector = info.get("sector")
            if cand_sector and not str(cand_sector).startswith("미분류"):
                held_pending = set(self.state.positions.keys()) | set(self.state.pending_buys)
                same = sum(
                    1 for t in held_pending
                    if ((self._candidates.get(t) or {}).get("sector")
                        or self._position_sectors.get(t)) == cand_sector
                )
                if same >= sector_cap:
                    logger.info("[kojiro_sector_cap] %s 섹터=%s 동시보유 %d ≥ %d — 매수 스킵",
                                ticker, cand_sector, same, sector_cap)
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
        # 당일 매수분 ATR 영속화 — 재-prepare 와이프 후에도 2ATR 손절이 살아 있어야 한다.
        try:
            if (_entry_atr := float(info.get("atr") or 0)) > 0:
                self._position_atr[ticker] = _entry_atr
        except (TypeError, ValueError):
            pass
        if cand_sector := info.get("sector"):
            # 당일 매수분 영속화 — 재-prepare _candidates 와이프에도 다음 후보 카운트 반영.
            self._position_sectors[ticker] = cand_sector
        logger.info(
            "고지로 매수 신호: %s 현재가(%d) — 스테이지1(6→1) + EMA정배열 + ATR(%.1f)",
            ticker, current_price, info["atr"],
        )
        from src.engine.scanner import resolve_ticker_name
        self.state.buy_signals.append({
            "ticker": ticker,
            "name": self._candidates.get(ticker, {}).get("name") or resolve_ticker_name(ticker),
            "price": current_price,
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

        atr = self._effective_atr(ticker)

        # 2) 2ATR 하드손절 (tighten-only floor — 변동성 팽창 loosen 차단)
        #    ATR 이 전무해도 `_stop_floor`(과거 확정 손절선)만으로 판정한다 —
        #    구 구현은 `atr > 0` 블록 안에서만 floor 를 읽어, `_candidates` 가
        #    사라지면 저장된 손절선까지 함께 무시됐다.
        floor = self._stop_floor.get(ticker)
        eff = 0
        if atr > 0 and pos.buy_price > 0:
            base = int(pos.buy_price - params["stop_atr"] * atr)
            eff = base if floor is None else max(base, floor)
            self._stop_floor[ticker] = eff
        elif floor is not None:
            eff = floor

        # 2.5) 브레이크이븐 플로어 승격 (다크런치, breakeven_promote_atr=0 → 미진입)
        be_mult = float(params.get("breakeven_promote_atr", 0) or 0)
        if (be_mult > 0 and atr > 0 and pos.buy_price > 0
                and pos.high_since_buy >= pos.buy_price + be_mult * atr):
            promoted = max(eff, int(pos.buy_price))
            if promoted != eff:
                logger.info(
                    "[kojiro_breakeven_promote] %s 고점(%d) ≥ 매수가(%d)+%.1f×ATR(%.1f) → 손절선 %d→%d",
                    ticker, pos.high_since_buy, pos.buy_price, be_mult, atr, eff, promoted,
                )
            eff = promoted
            self._stop_floor[ticker] = eff

        if eff > 0 and current_price <= eff:
            logger.info("[kojiro_atr_stop] %s 손절선(%d) = 매수가(%d) - %.1f×ATR(%.1f)",
                        ticker, eff, pos.buy_price, params["stop_atr"], atr)
            return Signal.STOP_LOSS

        # 3) 스테이지3 진입 (추세 종료, 익일 아침 발화 — precompute 플래그)
        # cycle231 (P2-5) — **오늘 판정만** 소비한다. §3 는 유일하게 가격을 안 보는
        # 청산이라 "오늘 데이터임"이 보장될 때만 정당하다(`recompute` 의 fail-open
        # 계약을 소비 축까지 통일). stale True 는 억제 + 관측만 — §1/§2/§4 가 방어하고
        # §3 는 원래 익일 아침 발화라 하루 지연이 설계에 내장돼 있다. 억제 시 값은
        # **보존**한다(덮어쓰면 재판정 성공 여부와 억제 이력이 구분 불가).
        _s3 = self._held_stage3.get(ticker)
        if isinstance(_s3, tuple) and len(_s3) == 2:
            _judged_on, _flagged = _s3
            _today_kst = datetime.now(KST).date()
            if _flagged and _judged_on == _today_kst:
                logger.info(
                    "[kojiro_stage3_exit] %s 스테이지3 진입 (추세 종료) judged_on=%s",
                    ticker, _judged_on,
                )
                return Signal.TRAILING_STOP
            if _flagged and isinstance(_judged_on, date) and _judged_on < _today_kst:
                self._emit_stage3_stale_skip(ticker, _judged_on, _today_kst)

        # 4) 2.5ATR 샹들리에 트레일링
        if atr > 0 and pos.high_since_buy > 0:
            chandelier = pos.high_since_buy - atr * params["trail_atr"]
            if current_price <= chandelier:
                logger.info("[kojiro_trailing] %s 고점(%d) - %.1f×ATR(%.1f) = %d / 현재가 %d",
                            ticker, pos.high_since_buy, params["trail_atr"], atr,
                            int(chandelier), current_price)
                return Signal.TRAILING_STOP

        return Signal.NONE

    def _is_open_risk_capped(self) -> bool:
        """Σ 오픈리스크가 `max_open_risk_pct × 예산` 이상이면 True (매수 차단).

        `0` 또는 예산 미배분(0) 이면 비활성. 어떤 예외도 흡수해 **통과**시킨다 —
        리스크 계산 실패로 전략이 통째로 마비되는 것이 더 나쁘다(사이클 88 G-REJECT).
        """
        try:
            cap_pct = float(self.config.params.get("max_open_risk_pct", 0) or 0)
            budget = int(self.state.total_investment)
            if cap_pct <= 0 or budget <= 0:
                return False
            limit = budget * cap_pct / 100.0
            risk = self._open_risk_won()
            if risk < limit:
                return False
            if self._open_risk_cap_logged.should_emit(str(len(self.state.positions))):
                self._open_risk_cap_logged.mark_emitted(str(len(self.state.positions)))
                logger.info(
                    "[kojiro_open_risk_cap] Σ오픈리스크 %d원 ≥ 상한 %d원 "
                    "(예산 %d × %.1f%%) — 보유 %d종목, 매수 스킵",
                    risk, int(limit), budget, cap_pct, len(self.state.positions),
                )
            return True
        except Exception:
            logger.debug("[kojiro_open_risk_cap] 계산 실패 — fail-open", exc_info=True)
            return False

    def _effective_atr(self, ticker: str) -> float:
        """손절 판정용 ATR — `_candidates` live 우선, 부재 시 `_position_atr` 정본.

        `_candidates` 는 `prepare()` 마다 `{}` 로 와이프되고 held 재채움은 ATR 밴드·
        유니버스 컷에 걸리면 보장되지 않는다. 이에 의존하면 **보유 종목의 2ATR 손절이
        조용히 사라진다** — 2026-08-04 실측(삼영무역 002810: `_candidates` 부재로
        손절선 21,674 를 관통한 21,550 에서 미발화, −8% backstop 만 잔존).

        live 우선은 설계 의도(변동성 변화 반영 + tighten-only floor) 보존이고,
        폴백은 사이클 J `_position_sectors` 와 동일한 포지션 수명 영속 맵이다.
        """
        info = self._candidates.get(ticker)
        if info:
            try:
                live = float(info.get("atr") or 0)
                if live > 0:
                    return live
            except (TypeError, ValueError):
                pass
        try:
            return float(self._position_atr.get(ticker) or 0)
        except (TypeError, ValueError):
            return 0.0

    def _position_stop_price(self, ticker: str, pos) -> int:
        """포지션의 **현재 실효 손절선** = `max(고정% backstop, 2ATR floor, 2.5ATR 샹들리에, 브레이크이븐)`.

        `check_exit_signal` 의 네 가격선(브레이크이븐 포함)과 동일 산식·동일 ATR 소스
        (`_effective_atr`)다. 넷은 우선순위대로 검사되지만 전부 같은 tick 의 가격 임계라,
        실제로 먼저 발화하는 선 = 그중 **가장 높은** 가격이다. (스테이지3 청산은 가격
        조건이 아니라 모델링 대상이 아니며, 그 방향은 조기 청산 = 리스크 과대계상 쪽이라
        안전하다.)

        **샹들리에 포함은 H-1(2026-08-06) 이후의 필수 조건이다.** 그 전에는 `_boot()` 이
        매일 아침 `high_since_buy` 를 매수가로 리셋해 매수창(09:05~09:30) 시점의 샹들리에가
        항상 두 선보다 낮았고, 그래서 `max(pct, atr)` 만으로도 정확했다. H-1 이 고점을
        복구하면서 샹들리에가 `buy_price` 를 **넘어설 수 있게** 됐다(실측 슈프리마
        51,203 > 매수가 48,200). 제외하면 **이미 이익이 확정된 포지션을 만액 리스크로
        계상**해 Σ오픈리스크 캡이 근거 없이 신규 매수를 잠근다.

        ⚠️ 샹들리에는 앞 두 선과 달리 **tighten-only 가 아니다** — 고점은 고정이지만 ATR 이
        팽창하면 선이 내려간다. 따라서 이 값은 "재기 어려운 최악"이 아니라 **평가 시점의
        실제 손절선**이고, `_is_open_risk_capped` 가 매수 시도마다 재평가하므로 그게 맞다.

        `_stop_floor` 를 **쓰기만 하고 갱신하지 않는다** — 이 메서드는 매수 게이트에서
        호출되는 읽기 전용 추정기이고, 여기서 floor 를 올리면 청산 규약이 매수 경로의
        부작용으로 바뀐다.

        ATR 결측(재시작 직후 등) 이면 고정% 선만으로 추정 — fail-open.
        """
        params = self.config.params
        pct_line = int(pos.buy_price * (1 + float(params["hard_stop_pct"]) / 100.0))
        atr = self._effective_atr(ticker)          # check_exit_signal 과 동일 소스
        floor = self._stop_floor.get(ticker)
        atr_line = 0
        if atr > 0:
            atr_line = int(pos.buy_price - float(params["stop_atr"]) * atr)
            if floor is not None:
                atr_line = max(atr_line, floor)
        elif floor is not None:
            atr_line = floor
        # 2.5ATR 샹들리에 — check_exit_signal §4 와 동일 조건/동일 산식.
        # int() 절삭은 정수 가격에서 부동소수 비교와 동치이고, 어긋나도 낮은 쪽
        # (= 리스크 과대계상 = 보수적)으로만 어긋난다.
        trail_line = 0
        if atr > 0 and pos.high_since_buy > 0:
            trail_line = int(pos.high_since_buy - float(params["trail_atr"]) * atr)
        # 브레이크이븐 라인 — check_exit_signal §2.5 와 동일 조건/산식 (read-only 미러).
        be_mult = float(params.get("breakeven_promote_atr", 0) or 0)
        be_line = 0
        if (be_mult > 0 and atr > 0 and pos.buy_price > 0
                and pos.high_since_buy >= pos.buy_price + be_mult * atr):
            be_line = int(pos.buy_price)
        return max(pct_line, atr_line, trail_line, be_line)

    def _open_risk_won(self) -> int:
        """보유 포지션의 Σ 오픈리스크(원) = Σ qty × (매수가 − 실효 손절선).

        터틀의 유닛 캡이 실제로 통제하려던 값. 개수(`max_positions`)는 "1유닛 =
        상수 리스크" 가 성립할 때만 이것의 프록시인데, 수량 절삭·`hard_stop_pct` 캡·
        사이징 혼재 때문에 우리 구현에선 프록시가 헐거워 직접 잰다.

        `stop >= buy_price` 인 포지션(트레일링이 매수가 위로 올라간 이익 확정분)은
        **0 으로 계상**한다 — 음수를 더하면 한 종목의 확정 이익이 다른 종목의 실제
        손실 노출을 상쇄해 캡이 조용히 무력화된다.
        """
        total = 0
        for ticker, pos in self.state.positions.items():
            if pos.buy_price <= 0 or pos.quantity <= 0:
                continue
            stop = self._position_stop_price(ticker, pos)
            if stop > 0 and stop < pos.buy_price:
                total += pos.quantity * (pos.buy_price - stop)
        return total

    def get_effective_stop_price(self, ticker: str) -> int | None:
        """실효 손절선 read-only 미러 (cycle233 척도 병기) — `_position_stop_price` 위임.

        Σ오픈리스크 캡·척도 병기 양쪽이 **동일 산식**(4선 max)을 보게 하는 단일 진실원.
        """
        pos = self.state.positions.get(ticker)
        if not pos or pos.buy_price <= 0:
            return None
        try:
            stop = self._position_stop_price(ticker, pos)
            return int(stop) if stop > 0 else None
        except Exception:
            return None  # fail-open — 프록시 폴백

    def check_force_clear(self) -> list[str]:
        """15:20 강제 청산 대상 — 멀티데이 스윙은 강제 청산 없음."""
        return []

    def on_position_closed(self, ticker: str) -> None:
        """전량 청산 시 per-ticker 보유결합 상태 정리 (재진입 stale 차단)."""
        self._held_stage3.pop(ticker, None)
        self._stop_floor.pop(ticker, None)
        self._position_sectors.pop(ticker, None)
        self._position_atr.pop(ticker, None)

    def calc_buy_quantity(self, current_price: int, ticker: str | None = None) -> int:
        """터틀 유닛(sizing_mode='turtle') 또는 position_ratio(기본). 어떤 실패든 fail-open."""
        if current_price <= 0:
            return 0
        params = self.config.params
        # ── 터틀 유닛 sizing (opt-in) — 실패 시 아래 position_ratio 로 fail-open ──
        if params.get("sizing_mode") == "turtle" and ticker is not None:
            try:
                from src.engine.turtle_sizing import compute_unit_qty_guarded
                # donchian `_turtle_buy_quantity` 와 동일한 3중 가드(변동성 floor /
                # 잔여 예산 / notional 상한). unguarded `compute_unit_qty` 를 쓰면
                # 저변동 종목에서 단일종목 명목이 예산의 50%까지 치솟는다.
                # notional 상한이 `position_ratio × 예산` 이라 **터틀 수량 ≤ 비중 수량**
                # 이 항상 성립 = 전환은 순수 축소 방향(함정 #1 구조적 차단).
                atr = float(getattr(self, "_candidates", {}).get(ticker, {}).get("atr") or 0)
                budget = int(self.state.total_investment)
                qty = compute_unit_qty_guarded(
                    budget, atr, current_price,
                    float(params.get("risk_pct") or 0),
                    remaining_budget=max(0, budget - self._calc_used_funds()),
                    min_vol_pct=float(params.get("min_vol_floor_pct", 1.0)),
                    position_ratio=float(params.get("position_ratio") or 0),
                )
                if qty > 0:
                    return self._apply_budget_limit(qty, current_price, ticker)
            except Exception:
                logger.debug("[kojiro_turtle_sizing_fallback] %s — position_ratio 낙하", ticker, exc_info=True)
            # atr/budget 0 또는 예외 → position_ratio 낙하 (fail-open)
        # ── position_ratio (기본, 바이트 동일 회귀 경로) ──
        ratio = params["position_ratio"]
        amount = int(self.state.total_investment * ratio)
        return self._apply_budget_limit(amount // current_price, current_price, ticker)

    # ────────────────────────── 대시보드/구독 ──────────────────────────

    def _rank_candidate_components(self, enriched, stages_series: list, within: int) -> tuple[float, float, float]:
        """후보 랭킹 raw 3성분 (원설계 §9④): (macd3 기울기, 띠폭 확장률, 신선도).

        enrich 가 이미 계산한 macd3/band_width(dormant) 배선. 컬럼 부재(테스트 스텁) →
        신선도만 산출 + macd3/band=0 (fail-safe, no crash).
        """
        dist = _stage_transition_distance(stages_series, 6, 1, within)
        fresh = float(within - dist) if dist is not None else 0.0
        try:
            m3 = enriched["macd3"]
            bw = enriched["band_width"]
        except (KeyError, TypeError):
            return (0.0, 0.0, fresh)
        li = len(m3) - 1
        pi = max(0, li - _RANK_LOOKBACK)
        macd3_slope = float(m3.iloc[li] - m3.iloc[pi])
        prev_bw = float(bw.iloc[pi])
        band_expansion = (float(bw.iloc[li]) - prev_bw) / (abs(prev_bw) + 1e-9)
        return (macd3_slope, band_expansion, fresh)

    def _score_candidates(self, rank_raw: dict[str, tuple], params: dict) -> dict[str, float]:
        """후보 풀 min-max 정규화 + 가중합 → {ticker: score∈[0,1]}.

        단일후보/동일값 성분 → 0.5 중립. 가중치 합≠1 → 자동 정규화.
        """
        if not rank_raw:
            return {}
        tickers = list(rank_raw.keys())
        cols = list(zip(*(rank_raw[t] for t in tickers)))   # 3 성분별 값 튜플
        w = [
            float(params.get("rank_w_macd3", 0.4) or 0.0),
            float(params.get("rank_w_band", 0.3) or 0.0),
            float(params.get("rank_w_fresh", 0.3) or 0.0),
        ]
        wsum = sum(w) or 1.0
        w = [x / wsum for x in w]

        def _mm(vals):
            lo, hi = min(vals), max(vals)
            if hi - lo < 1e-12:
                return [0.5] * len(vals)   # 동일/단일 → 중립
            return [(v - lo) / (hi - lo) for v in vals]

        norm = [_mm(c) for c in cols]
        return {
            t: w[0] * norm[0][i] + w[1] * norm[1][i] + w[2] * norm[2][i]
            for i, t in enumerate(tickers)
        }

    def get_scanned_tickers(self) -> list[str]:
        return self._scanned_tickers

    def get_scan_stats(self) -> dict:
        return dict(self._scan_stats)

    def get_targets_status(self) -> dict[str, dict]:
        from src.engine.scanner import resolve_ticker_name
        return {
            ticker: {
                "name": info.get("name") or resolve_ticker_name(ticker),  # 저장값 우선, 미저장 시 실시간 폴백
                "prev_close": info["prev_close"], "atr": int(info["atr"]),
                "stage": info.get("stage", 0),
                "ema_s": int(info.get("ema_s", 0)), "ema_m": int(info.get("ema_m", 0)),
                "ema_l": int(info.get("ema_l", 0)),
                # 대시보드 ATR 변동성 밴드 게이지용 (atr/prev_close, 밴드 판별 정확값).
                "atr_ratio": round(float(info.get("atr_ratio", 0) or 0), 4),
                "sector": info.get("sector", ""),  # 섹터/테마 캡 대시보드 노출

                "target_price": info["prev_close"], "open_price": 0,
                "target_offset": 0, "open_confirmed": True, "k": 0.0,
            }
            for ticker, info in self._candidates.items()
        }
