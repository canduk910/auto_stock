"""변동성 수축 돌파(VCP, Volatility Contraction Pattern) 전략.

미네르비니식 베이스 셋업. 상승 후 변동성 단계적 축소 → 거래량 폭증 베이스 상단 돌파.
donchian_swing 의 정공법(신고가 직진 추격)을 보강하는 추세추종 보조 전략.
멀티데이 보유 — `Position._MULTIDAY_STRATEGIES` 멤버.

진입:
- 추세 필터: 종가 > 단기EMA > 중기EMA > 장기EMA, 장기EMA 1개월 우상향
  (미너비니 Trend Template 원설계 50/150/200. `daily_fetch_depth_mode` 기본값
  "cap100" 에서는 `effective_ema_long` 가드로 장기선이 축소된다 — VCP 절 참조)
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

import asyncio
import logging
from datetime import date, datetime, time, timedelta, timezone

from src.api.condition import add_business_days
from src.engine.daily_emit_cap import KstDailyEmitCap
from src.engine.strategy_base import FunnelStage, Signal, StrategyBase, StrategyConfig

# vcp_breakout 은 멀티데이 — `Position._MULTIDAY_STRATEGIES` 리터럴에 정적 선언됨
# (2026-07: 과거 import 시점 동적 변형 side-effect 제거, strategy_base 단일 진실원).

KST = timezone(timedelta(hours=9))
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# cycle300 — 일봉 읽기 깊이 스위치 `daily_fetch_depth_mode`
# ---------------------------------------------------------------------------
# `"cap100"`(기본) = 현행. `prepare` 가 100봉만 요청하므로 이 값에서는 배포 전후 행위가
#   byte 동일하다.
# `"full"`          = `ema_long + base_max_days + 10` 봉을 요청한다. DB 에 있는 만큼만
#   오므로 `effective_ema_long = min(ema_long, 보유 − uptrend_days − 5)` 가 실제 보유
#   깊이를 따라간다. 운영 DB(50/150/200)에서 보유 100봉이면 실효 정렬이 50/65/75 로
#   잘리고(중기↔장기 간격 10 = 정배열이 동전던지기), 225봉에서 비로소 50/150/200 이 산다.
#
# 🔴 `PARAM_RANGES`/`INT_PARAMS` 편입 금지 — 읽기 깊이는 추세 필터의 실효 EMA 를 통째로
#    바꾸는 진입 정체성 축이라 AI 야간 튜닝 대상이 아니다(가드 G-300-5).
# 판정은 대소문자·공백 무시 정확 일치이고, 미지 값·결측·비문자열·예외는 전부 기본값으로
# 낙하한다 — 이 스위치의 안전 방향은 '현행 보존' 이다.
DAILY_DEPTH_MODE_CAP100 = "cap100"
DAILY_DEPTH_MODE_FULL = "full"
_DAILY_DEPTH_MODE_DEFAULT = DAILY_DEPTH_MODE_CAP100


def resolve_daily_depth_mode(params) -> str:
    """`daily_fetch_depth_mode` 해석 — `"full"` 정확 일치만 열고 나머지는 전부 기본값."""
    try:
        raw = params.get("daily_fetch_depth_mode", _DAILY_DEPTH_MODE_DEFAULT)
        if isinstance(raw, str) and raw.strip().lower() == DAILY_DEPTH_MODE_FULL:
            return DAILY_DEPTH_MODE_FULL
    except Exception:
        return _DAILY_DEPTH_MODE_DEFAULT
    return _DAILY_DEPTH_MODE_DEFAULT


# 사이클 47 (2026-05-22, refactor-review 카드 #3) — Funnel 단계 정의 모듈 상수.
FUNNEL_STAGES: tuple[FunnelStage, ...] = (
    FunnelStage(1, "전체 상장 유니버스 (시총/거래대금 컷 전)"),
    FunnelStage(2, "시총·거래대금 컷 통과"),
    # 사이클 157 (2026-06-17) — 1단계 진입 차단 13건 step 신규 영구 영속 → 9단계.
    FunnelStage(3, "1단계 진입 차단 13건 통과 (거래정지/관리/단기과열/투자유의 등)"),
    FunnelStage(4, "일봉 fetch + 추세필터"),
    # 사이클 48 — config 50/60/120 (기존 50/150/200). PR #15 ①: 장기EMA(120) 는 KIS 100일
    # 한도 가드로 런타임 effective ~75 로 캡됨 → 실효 정렬 50/60/~75. step_conditions 에 명시.
    FunnelStage(5, "단기/중기/장기 EMA 정렬"),
    FunnelStage(6, "베이스 자동 검출"),
    FunnelStage(7, "Pullback 점진 수축"),
    FunnelStage(8, "거래량 수축"),
    FunnelStage(9, "최종 prepared"),
)


def _empty_scan_stats() -> dict:
    return {
        # 사이클 175 — 코스피200∪코스닥150 합집합 (시총 컷 *전* 원천, ScanMonitor "합집합" 정합)
        "universe_union": 0,
        "universe_candidates": 0,
        "universe_filtered": 0,
        "mcap_pass": 0,  # 사이클 23 P1-3 — 시총 컷 통과 카운터
        "candle_fetch_ok": 0,
        "trend_filter_pass": 0,
        "base_pass": 0,
        "pullback_pass": 0,
        "volume_contraction_pass": 0,
        "final_prepared": 0,
        # cycle228 (A6) — 실게이트 카운터. cycle227 의 `vol_gate_observe_*` 는
        # **은퇴**했다(같은 would_pass 의 매매 귀결이 "안 샀다"→"샀다" 로 반전되므로
        # 키를 유지하면 과거 집계와 뒤섞인다). 로그는 cap 이 걸리지만 이 카운터는
        # cap 과 무관하게 매 사건 누적된다(총량은 API 로 관측).
        "vol_gate_pass": 0,
        "vol_gate_reject_ext": 0,
        "vol_gate_no_data": 0,
        "latch_armed_count": 0,
        # cycle228 (A5) — BFB 와 키 집합 통일(카운터 소비처 단일 스키마). VCP 는
        # retention 이 없어 항상 0 이지만 키 부재는 소비처 분기를 낳는다.
        "breakout_seen_count": 0,
        "breakout_retreat_count": 0,
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
        # 추세 필터 (cycle301, 2026-09-18 — 사용자 승인 D3·D4 + 운영 DB 실측 정합)
        # 50/150/200 이 미너비니 Trend Template 원설계다. cycle299(일봉 적재 깊이
        # 225영업일)·cycle300(읽기 클램프 400 + daily_fetch_depth_mode)이 KIS 단일호출
        # 100일 한도를 걷어냈으므로 코드 기본값을 원설계 값으로 되돌린다 — 지금까지는
        # 운영 DB(150/200)가 맞고 코드(60/120)가 낡아 있었다. `daily_fetch_depth_mode`
        # 기본값 "cap100"(100봉)에서는 `_check_trend_filter` 가 받는
        # `effective_ema_long = min(ema_long, 보유행수-uptrend_days-5)` 가드(`prepare()`
        # 참조)로 장기선이 여전히 축소된다 — 원설계 50/150/200 정렬을 실제로 쓰려면
        # `daily_fetch_depth_mode="full"` 로 전환한다(`strategies/CLAUDE.md` VCP 절).
        "ema_short": 50,
        "ema_mid": 150,
        "ema_long": 200,
        "long_ema_uptrend_days": 20,
        # cycle300 — 일봉 읽기 깊이 스위치. 기본 "cap100" = 현행 100봉(행위 byte 동일).
        # "full" 이면 ema_long + base_max_days + 10 봉을 요청해 실효 장기선이 보유 깊이를
        # 따라간다. 장중 전환·롤백 = `PUT /api/strategies/vcp_breakout/params`(즉시 반영,
        # SQL UPDATE 는 다음 재시작에서만 — cycle232 D6). PARAM_RANGES/INT_PARAMS 편입 금지.
        "daily_fetch_depth_mode": "cap100",
        # 베이스
        "base_min_days": 25,
        "base_max_days": 75,
        "base_depth_pct": 0.30,
        # 조정 시퀀스
        "pullback_count_min": 2,
        "pullback_count_max": 4,
        "last_pullback_max": 0.12,  # 사이클 48 — 0.08→0.12. 한국 중소형주 변동성 현실화
        # ATR threshold swing 검출. 베이스 ATR × min_swing_atr_mult 미만 변동은 노이즈로 무시.
        # cycle301(2026-09-18, 사용자 승인 D3·D4 + 운영 DB 실측 정합) — 0.5 는 임계가 너무
        # 낮아 ZigZag 반전 회수가 2~4배로 불어나 상한 pullback_count_max=4 를 넘기고
        # 점진 수축 strict 단조(통과율 1/n!)가 무너져 Pullback 단계가 사실상 막히는
        # 결함이었다. 1.0 으로 올려 노이즈성 반전을 더 넓게 걸러낸다.
        "min_swing_atr_mult": 1.0,
        # 거래량 수축
        "volume_contraction_ratio": 0.70,
        # 매수
        "breakout_volume_mult": 1.5,
        "entry_start": "09:05",
        "entry_end": "14:30",
        # cycle228 (A4) — 추격 상한. 래치는 돌파 시점이 아니라 **거래량 충족 시점**에
        # 사므로, 그사이 급등한 종목을 추격하지 않도록 current_price 기준 상한을 건다.
        # 트레이더 규칙 한 줄 = "손절선이 돌파선 위로 올라가는 가격에서는 사지 않는다"
        # (stop −7% → entry ≤ base_high/0.93 = +7.53% → 보수적 내림 7.5).
        # ⚠️ **리터럴 고정** — stop_loss_rate 는 PARAM_RANGES 멤버라 런타임 도출이면
        # AI 야간 튜닝에 캡이 함께 끌려간다. 도출 관계는 `_check_extension_cap_invariant`
        # 가 부팅 시 관찰만 한다. PARAM_RANGES/INT_PARAMS 편입 금지(진입 정체성 상수).
        "max_breakout_extension_pct": 7.5,
        "position_ratio": 0.20,
        "max_positions": 5,
        # 청산
        "stop_loss_rate": -7.0,
        "atr_period": 14,
        "atr_trail_mult": 2.0,
        # 사이클 C (2026-07-30) — 브레이크이븐 승격 (default-off 배포, live ATR 래치 필수).
        # 0.0 = 비활성 기본. 활성값 1.5 는 donchian D+1 실측 게이트 통과 후 DB 주입.
        # PARAM_RANGES/INT_PARAMS 미편입 (청산 정체성 상수).
        "breakeven_promote_atr": 0.0,
        "reentry_cooldown_days": 7,
        # ── 터틀 유닛 sizing + 하드손절 ATR화 (B-2 게이트 2, 2026-08-03) ──
        # **다크런치**: 기본 position_ratio → 배포 시 행위 byte 동일. DB 토글로만 활성.
        # 사이징만 ATR 로 바꾸면 리스크 정규화가 오히려 깨지므로(고정% 손절 + 비율 사이징은
        # 이미 종목 무관 상수 리스크) 하드손절 ATR화와 **한 커밋에** 묶는다.
        # 게이트는 `sizing_mode` 가 아니라 `_entry_atr` 스탬프 존재 —
        # position_ratio 매수는 미스탬프라 기존 −7% 경로를 그대로 탄다.
        # ⚠️ VCP 는 수축 셋업이라 진입 ATR 이 국소 최소 → 2ATR 이 −3% 로 과도하게
        #    조여질 수 있다. `turtle_min_stop_pct` 밴드가 유일한 방어선이며 실제 활성화는
        #    외부 MCP 백테스트 스윕 통과 후. 전 키 PARAM_RANGES/INT_PARAMS 미편입.
        "sizing_mode": "position_ratio",
        "risk_pct": 0.005,
        "stop_atr": 2.0,
        "turtle_backstop_pct": -9.0,
        "min_vol_floor_pct": 1.0,
        "turtle_min_stop_pct": -5.0,
        "max_lot_units": 2.0,   # cycle242 — 랏당 최대 유닛(K). 터틀 모드 모든 랏 ≤ K유닛, floor(K×u*)==0 이면 미매수. PARAM_RANGES 미편입. 롤백 = DB 20.0
        # 유니버스
        # 2026-08-08 확대 유니버스 — 지수(KOSPI200∪KOSDAQ150) 제약 제거(전체 상장) + 거래대금
        # 10억 필터 신설(현재 min_trade_amount=0 하드코딩이라 미사용이던 것을 실사용) + max_scan
        # 200→4000. 시총 하한 = 100억(사용자 결정 — kojiro 500억보다 낮게 유지해 미네르비니
        # 중소형 성장주 서식지를 더 넓게 포착. 라이브 DB 값 100억 정합). 거래량 ×1.5 돌파 +
        # 거래량 수축이 소형주 작전 신호를 이중 방어.
        "min_market_cap": 10_000_000_000,
        "min_trade_amount": 1_000_000_000,
        "max_scan_stocks": 4000,
        # 일반
        "daily_loss_limit": -8.0,
        "max_lot_ratio_mult": 2.5,   # cycle245 — 랏 명목 ρ축 상한(K_ρ). 명목 ≤ K_ρ×position_ratio×예산, 1주도 못 사면 미매수. 터틀 모드에선 K축(max_lot_units)이 우선하고 그것이 fail-open 할 때만 백스톱. PARAM_RANGES 미편입. 롤백 = DB 20.0
        # cycle290 (2026-09-13) — 장중 킬스위치 등재. 값은 코드 상수와 **같은 값**이라
        # 등재 자체의 매매 행위 변경은 0 이다(`order_engine._ORDER_EXCHANGE_CLOCK_MODE_DEFAULT`
        # ·`_AFTER_EXIT_DIVISION_DEFAULT`). `PARAM_RANGES`/`INT_PARAMS` 편입 금지 —
        # AI 자문이 청산 수단을 끄는 스위치를 뒤집으면 안 된다. 장중 롤백은 PUT 뿐
        # (SQL UPDATE 는 다음 재시작에서만, cycle232 D6). 사고 중 조작 순서 =
        # `_workspace/00_leader_trading_rules.md` 「거래소 라우팅」 절.
        "order_exchange_clock_mode": "enforce",
        "after_market_exit_division": "44",
        # cycle297 (2026-09-17) — 5전략 LLM 매수평가 shadow 확대(사용자 결정 "결정 2
        # 진행"). **기록만** 한다 — `enforce` 는 미구현이라 `shadow` 외 전부 `off` 로
        # 낙하한다(leaf `llm_buy_gate._read_mode`). 돈을 쓰는 기능이라 `llm_gate_mode`/
        # `llm_gate_daily_call_cap` 키 부재는 **off/0**(cycle245 `max_lot_ratio_mult`
        # 관례와 같은 방향, cycle272 `open_price_scope_mode` 부재=enforce 와는 반대).
        # PARAM_RANGES/INT_PARAMS 편입 금지(4키 전부, AST 런타임+소스 이중 가드).
        # 장중 롤백 = `PUT /api/strategies/{id}/params {"llm_gate_mode":"off"}`.
        "llm_gate_mode": "shadow",
        "llm_gate_min_score": 70,
        "llm_gate_daily_call_cap": 20,
        "llm_gate_timeout_secs": 20,
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
        # 사이클 C — 브레이크이븐 승격 boolean 래치 (live ATR 팽창 un-latch 병리 방지)
        self._breakeven_latched: set[str] = set()
        # B-2 게이트 2 — 터틀 진입 ATR 스냅샷. 존재 = ATR 하드손절 활성 (자연 게이트).
        self._entry_atr: dict[str, float] = {}
        # P1 (2026-08-06) — 청산 파라미터 영속 맵. `_candidates` 는 `prepare()` 마다
        # 와이프되고 **보유 종목은 셋업이 무너져 후보 자격을 잃는 게 정상**이라,
        # 청산이 거기 단독 의존하면 T+1 아침부터 §2 base_low·§3 트레일링·§4 ema50 이
        # 통째로 침묵한다(2026-08-04 kojiro 삼영무역과 동일 클래스).
        #   - `base_low` = 진입 시점 구조 레벨 → BUY 직전 stamp 후 **불변**
        #   - `atr14`/`ema50` = 지표 → boot 훅이 **이미 fetch 하는 일봉으로 매일 갱신**
        #     (스냅샷 박제 시 상승 추세에서 ema50 이 뒤처져 이탈 청산이 늦어진다)
        # ⚠️ `_reset_daily_state` 에서 clear 금지 — 멀티데이 보유가 밤새 소멸한다.
        self._position_setup: dict[str, dict] = {}
        # cycle228 (A5/A6) — 게이트·래치 로그 emit cap: (ticker, 종류) 1회/일.
        # 날짜 키 자기 리셋(`_reset_daily_state` 훅 미의존 — scheduler.py diff 0
        # 이 설계 목표). cap 키에 종류를 넣는 이유 = cycle225 교훈.
        self._gate_emit_capped: set[tuple[str, str]] = set()
        self._gate_emit_day: date | None = None
        # cycle228 (A3) — 충족 래치. VCP 는 retention 이 없으므로 **edge-crossing
        # 순간**이 무장 트리거다(retention 신설 금지 — 진입 임계 신설은 표본 보호와
        # 충돌, 자문 Q4). 엔트리 = {armed_at, armed_date, base_high, base_low}.
        self._vol_latch: dict[str, dict] = {}
        # cycle349 — ① 오전 후보별 돌파선 거리 관측(D2/D4) 하루 1회 cap(전략 인스턴스
        # 소유, 모듈 전역 금지) + ③ 하루 돌파 사건 watch(E1). 관측 전용 — 매매 행위 0.
        self._breakout_distance_cap: KstDailyEmitCap = KstDailyEmitCap()
        self._breakout_watch: dict | None = None
        # cycle349 F3 — run 요약 줄 「직전과 같으면 생략」 비교 키. (kst_date, content_key).
        self._breakout_summary_last: tuple | None = None

    # ------------------------------------------------------------------
    # prepare — 일봉 100일(prepare cap) → 추세/베이스/pullback/거래량 수축 자동 검출
    # ------------------------------------------------------------------
    async def prepare(self) -> None:
        import asyncio

        # 사이클 173 (2026-06-22) — 일봉 source KIS → DB 어댑터 전환 (행위 보존).
        # cycle300 — 읽기를 막던 클램프 두 겹 중 DB 쪽(`get_recent_daily` 의 100행)은
        #   열렸고, 여기 남은 겹은 `daily_fetch_depth_mode` 스위치가 연다. 적재 깊이는
        #   cycle299 가 이미 확보했다(backfill target 225영업일 · retention 390달력일
        #   ≈261영업일). 기본값 "cap100" 이라 배포 시점 행위는 byte 동일하고, "full" 로
        #   켜야 그 깊이가 실효 장기선에 닿는다.
        from src.db.stock_master_daily import get_recent_daily_normalized

        p = self.config.params
        # cycle228 (A4) — 추격 상한 리터럴 ↔ 손절 도출 관계 부팅 관찰 (fail-open).
        self._check_extension_cap_invariant()
        ema_long = p["ema_long"]
        base_max = p["base_max_days"]
        # 사이클 33 (2026-05-21) — KIS `fetch_daily_candles` 단일 호출 최대 100일 한도
        # (`src/api/CLAUDE.md` 명시). 기존 `fetch_days = ema_long + base_max + 10 = 285`
        # 요청 시 KIS 가 100일만 반환 → `len(candles) <= prev_idx + ema_long + 5 = 205`
        # 항상 True → 113→0 candle_fetch_ok 결함 (5/21 운영 사고).
        # 시정: KIS 한도 인식 cap + 가용 길이 기반 effective ema_long 자동 조정.
        # ema_long 파라미터 DB 값 (200) 변경 없음 — 런타임 가드만 추가.
        #
        # cycle300 — 그 100봉 cap 을 `daily_fetch_depth_mode` 가 연다. 사이클 33 의 사고
        # (285 요청 → KIS 가 100 만 반환 → 길이 게이트 전건 탈락)는 **KIS 단일 호출** 한도
        # 이야기였다. 지금 일봉의 정본은 DB(`get_recent_daily_normalized`)이고 DB 는
        # cycle299 로 225영업일 이상을 들고 있으므로, full 요청은 "있는 만큼" 을 돌려받고
        # 모자라면 아래 `effective_ema_long` 가드가 그대로 받아 낸다. KIS 폴백 경로는
        # 여전히 한 호출 100봉이 상한이라 `min_required` 는 100 으로 둔다(올리면 DB 가
        # 100~224봉인 구간에서 더 얕은 KIS 응답으로 바뀐다 = 퇴보).
        KIS_DAILY_CANDLES_MAX = 100
        full_depth = resolve_daily_depth_mode(p) == DAILY_DEPTH_MODE_FULL
        if full_depth:
            fetch_days = ema_long + base_max + 10
        else:
            fetch_days = min(ema_long + base_max + 10, KIS_DAILY_CANDLES_MAX)

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
                "[vcp_prepare_retry] stock_master 0건 — %d초 후 재시도 (cap=%d/3)",
                30, retry_attempt + 1,
            )
            await asyncio.sleep(30)
            self._candidates = {}
            stats = _empty_scan_stats()
            self._scan_stats = stats
            self._reset_funnel_steps(FUNNEL_STAGES)
            tickers = await self._scan_universe()
        # 사이클 47 (2026-05-22, refactor-review 카드 #3) — FUNNEL_STAGES 위임
        # 사이클 170 카드 C — step_conditions "고정 유니버스" → 실제 소스 정합.
        # 사이클 157 부터 stock_master.list_by_filter(is_kospi200, is_kosdaq150) 기반.
        # 2026-08-08 확대 — step0=union(컷 전 전체상장)/step1=trade(시총·거래대금 컷 통과)
        # 배선 (kojiro 패턴). 이전엔 둘 다 survived=tickers(컷 후)라 step0/step1 카운트
        # collapse → "컷 전" 라벨이 실카운트와 모순. stage_counts 로 실제 union/trade 노출.
        stage_counts = getattr(self, "_scan_stage_counts", None) or {}
        union_tickers = stage_counts.get("union_tickers", tickers)
        trade_tickers = stage_counts.get("trade_tickers", tickers)
        self._record_funnel_pipeline_step(
            FUNNEL_STAGES[0],
            survived=union_tickers,
            step_conditions="전체 상장 (지수 무제약) 원천 유니버스 후보 (시총/거래대금 컷 전)",
        )
        self._record_funnel_pipeline_step(
            FUNNEL_STAGES[1],
            survived=trade_tickers,
            step_conditions=(
                f"시총 ≥ {p['min_market_cap']/100_000_000:.0f}억 "
                f"+ 거래대금 ≥ {p['min_trade_amount']/100_000_000:.0f}억"
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
            logger.info("VCP 유니버스 0종목")
            self._scanned_tickers = []
            stats["last_run_at"] = datetime.now(KST).isoformat()
            try:
                self._observe_breakout_distance({})
            except Exception:
                logger.debug("[vcp_breakout_distance_failed] 관측 실패 graceful", exc_info=True)
            return

        today_str = datetime.now(KST).strftime("%Y%m%d")

        # 사이클 173 — DB 우선 어댑터. days=fetch_days + min_required=100.
        # cycle300 — `daily_fetch_depth_mode` 가 `fetch_days` 를 정한다: 기본 "cap100" 이면
        # 100(행위 보존, G-VCP-1), "full" 이면 ema_long + base_max + 10. `min_required` 는
        # 두 모드 다 100 이다 — KIS 폴백은 한 호출 100봉이 상한이라 문턱을 올리면 DB 가
        # 100~224봉인 구간에서 더 얕은 응답으로 바뀐다.
        async def _fetch_one(ticker: str):
            try:
                return ticker, await get_recent_daily_normalized(
                    ticker, days=fetch_days, min_required=100,
                )
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
        # 사이클 41 (2026-05-22) — 탈락 사유 캡처 (Pullback 9→0 새 결함 진단)
        candle_fetch_ok_tickers: list[str] = []
        trend_filter_pass_tickers: list[str] = []
        base_pass_tickers: list[str] = []
        pullback_pass_tickers: list[str] = []
        volume_contraction_pass_tickers: list[str] = []
        final_prepared_tickers: list[str] = []
        # 사이클 41 — 탈락 사유
        candle_fetch_excluded: list[dict] = []
        trend_filter_excluded: list[dict] = []
        base_excluded: list[dict] = []
        pullback_excluded: list[dict] = []
        volume_contraction_excluded: list[dict] = []
        # cycle349 — ① 오전 후보별 돌파선 거리 관측용 참조(D5, read-only). 새 계산·
        # 새 I/O 0 — `_candidates[ticker]=...` 대입 직후 candles/base 참조만 담는다.
        _dist_refs: dict[str, dict] = {}

        from src.engine.strategy_base import _resolve_ticker_name

        for ticker, candles in fetched:
            ticker_name = _resolve_ticker_name(ticker)
            if candles is None or not candles:
                candle_fetch_excluded.append({
                    "ticker": ticker, "name": ticker_name,
                    "reason": "KIS 일봉 응답 빈/None",
                })
                continue
            try:
                prev_idx = 1 if candles[0].get("stck_bsop_date") == today_str else 0
                # 사이클 33 — KIS 한도 대응: 가용 길이 기반 effective ema_long
                available_len = len(candles) - prev_idx
                effective_ema_long = min(ema_long, available_len - uptrend_days - 5)
                if effective_ema_long < 30:
                    candle_fetch_excluded.append({
                        "ticker": ticker, "name": ticker_name,
                        "reason": f"가용 EMA 길이 {effective_ema_long} < 30 (KIS 한도)",
                    })
                    continue
                if available_len < effective_ema_long + uptrend_days + 5:
                    candle_fetch_excluded.append({
                        "ticker": ticker, "name": ticker_name,
                        "reason": (
                            f"일봉 길이 {available_len} < 필요 "
                            f"{effective_ema_long + uptrend_days + 5}"
                        ),
                    })
                    continue
                if prev_idx:
                    candles = candles[prev_idx:]
                stats["candle_fetch_ok"] += 1
                candle_fetch_ok_tickers.append(ticker)  # 사이클 39

                trend = self._check_trend_filter(candles, effective_ema_long=effective_ema_long)
                if not trend:
                    trend_filter_excluded.append({
                        "ticker": ticker, "name": ticker_name,
                        "reason": (
                            f"EMA 정렬 미충족 (종가 / {p['ema_short']}EMA / "
                            f"{p['ema_mid']}EMA / {effective_ema_long}EMA 정렬 또는 "
                            f"{uptrend_days}일 우상향)"
                        ),
                    })
                    continue
                stats["trend_filter_pass"] += 1
                trend_filter_pass_tickers.append(ticker)  # 사이클 39

                base = self._detect_base(candles)
                if not base:
                    base_excluded.append({
                        "ticker": ticker, "name": ticker_name,
                        "reason": (
                            f"베이스 자동 검출 실패 "
                            f"(길이 {p['base_min_days']}~{p['base_max_days']}일 + "
                            f"깊이 ≤ {p['base_depth_pct']*100:.0f}%)"
                        ),
                    })
                    continue
                stats["base_pass"] += 1
                base_pass_tickers.append(ticker)  # 사이클 39

                pullbacks_ok = self._check_pullback_sequence(candles, base)
                if not pullbacks_ok:
                    # 사이클 41 — Pullback 9→0 새 결함 진단용 정밀 사유 (사용자 5/22 보고)
                    # 사이클 49 — pull_count=0 (평탄 베이스 swing 미검출) 분기 (운영자 혼동 차단)
                    last_pct = base.get("last_pullback_pct", 0)
                    last_count = base.get("last_pullback_count", 0)
                    cond_prefix = (
                        f"Pullback 점진 수축 미충족 "
                        f"(회수 {p['pullback_count_min']}~{p['pullback_count_max']}회 + "
                        f"직전 대비 폭 감소 + 마지막 폭 ≤ {p['last_pullback_max']*100:.0f}%)"
                    )
                    if last_count == 0:
                        reason = (
                            f"{cond_prefix} — 베이스 평탄, swing 미검출 "
                            f"(변동성 < min_swing_atr_mult × ATR)"
                        )
                    else:
                        reason = (
                            f"{cond_prefix} — 회수 {last_count}회, "
                            f"마지막 폭 ≈ {last_pct*100:.1f}%"
                        )
                    pullback_excluded.append({
                        "ticker": ticker, "name": ticker_name,
                        "reason": reason,
                    })
                    continue
                stats["pullback_pass"] += 1
                pullback_pass_tickers.append(ticker)  # 사이클 39

                vol_ok = self._check_volume_contraction(candles, base)
                if not vol_ok:
                    volume_contraction_excluded.append({
                        "ticker": ticker, "name": ticker_name,
                        "reason": (
                            f"거래량 수축 미충족 (마지막 5일 평균 < "
                            f"베이스 직전 20일 평균 × {p['volume_contraction_ratio']*100:.0f}%)"
                        ),
                    })
                    continue
                stats["volume_contraction_pass"] += 1
                volume_contraction_pass_tickers.append(ticker)  # 사이클 39

                # 사이클 125 — DB ATR 우선 + ±10% 일치 검증 + KIS 캔들 fallback
                # (사이클 123 donchian/VB 답습. _atr()·get_atr() 모두 SMA(단순평균) 평활 —
                #  SMA vs SMA 동종비교라 ±10% 검증 무해. 진짜 Wilder 평활은 kojiro_indicators.atr 만)
                from src.db.stock_master_daily import get_atr as _get_db_atr
                kis_atr = self._atr(
                    [int(c.get("stck_hgpr", "0")) for c in candles],
                    [int(c.get("stck_lwpr", "0")) for c in candles],
                    [int(c.get("stck_clpr", "0")) for c in candles],
                    p["atr_period"],
                )
                db_atr = await _get_db_atr(ticker, days=14)
                if db_atr is not None and db_atr > 0:
                    if kis_atr > 0:
                        diff_pct = abs(db_atr - kis_atr) / kis_atr * 100
                        if diff_pct <= 10.0:
                            atr = db_atr
                            stats.setdefault("db_atr_hit", 0)
                            stats["db_atr_hit"] += 1
                        else:
                            logger.warning(
                                "[vcp_atr_mismatch] ticker=%s db_atr=%d kis_atr=%d"
                                " diff_pct=%.2f%% > 10%% (KIS fallback)",
                                ticker, int(db_atr), int(kis_atr), diff_pct,
                            )
                            atr = kis_atr
                            stats.setdefault("db_atr_mismatch", 0)
                            stats["db_atr_mismatch"] += 1
                    else:
                        atr = db_atr
                        stats.setdefault("db_atr_hit", 0)
                        stats["db_atr_hit"] += 1
                else:
                    atr = kis_atr
                    stats.setdefault("db_atr_miss", 0)
                    stats["db_atr_miss"] += 1
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
                # cycle349 (D5) — read-only 참조만 담는다. `_candidates` 엔트리에
                # 키를 추가하지 않는다(UI get_targets_status 등으로 새는 것 방지).
                _dist_refs[ticker] = {"candles": candles, "base": base}
                stats["final_prepared"] += 1
                final_prepared_tickers.append(ticker)  # 사이클 39
            except Exception as e:
                logger.warning("VCP prepare 실패: %s — %s", ticker, e)
                continue

        # 사이클 47 + 157 — FUNNEL_STAGES 위임 (사이클 157 step 3 master block 후 인덱스 +1)
        self._record_funnel_pipeline_step(
            FUNNEL_STAGES[3],
            survived=candle_fetch_ok_tickers, excluded=candle_fetch_excluded,
            step_conditions=(
                f"일봉 ≥ effective_ema_long"
                f"(config {ema_long}, 읽기 {fetch_days}봉 기준 ~{min(ema_long, fetch_days - uptrend_days - 5)} 캡) "
                f"+ 우상향 {uptrend_days}일 + 5"
            ),
        )
        # PR #15 (사이클 48) copilot 재리뷰 ① — 표기 정직화. config ema_long 은 읽기 깊이
        # 가드로 런타임 effective 가 캡된다 (예: 100봉 응답 → min(120,100-20-5)=75).
        # funnel/step_conditions 가 config 값만 박으면 실제와 불일치 → 캡을 명시.
        # cycle300 — 기준을 `KIS_DAILY_CANDLES_MAX` 리터럴이 아니라 그날 실제 요청한
        # `fetch_days` 로 잡는다. 안 그러면 `daily_fetch_depth_mode="full"` 에서 라벨만
        # 100봉 세계에 남아 화면이 거짓말을 한다.
        _eff_long_label = min(
            ema_long, fetch_days - uptrend_days - 5
        )
        self._record_funnel_pipeline_step(
            FUNNEL_STAGES[4],
            survived=trend_filter_pass_tickers, excluded=trend_filter_excluded,
            step_conditions=(
                f"종가 > {p['ema_short']}EMA > {p['ema_mid']}EMA > "
                f"장기EMA(config {ema_long}, 읽기 {fetch_days}봉 기준 effective ~{_eff_long_label}) + "
                f"effective 장기EMA {uptrend_days}일 우상향"
            ),
        )
        self._record_funnel_pipeline_step(
            FUNNEL_STAGES[5],
            survived=base_pass_tickers, excluded=base_excluded,
            step_conditions=f"베이스 길이 {p['base_min_days']}~{p['base_max_days']}일 + 깊이 ≤ {p['base_depth_pct']*100:.0f}%",
        )
        self._record_funnel_pipeline_step(
            FUNNEL_STAGES[6],
            survived=pullback_pass_tickers, excluded=pullback_excluded,
            step_conditions=(
                f"{p['pullback_count_min']}~{p['pullback_count_max']}회 회수 + "
                f"직전 대비 폭 감소 + 마지막 폭 ≤ {p['last_pullback_max']*100:.0f}%"
            ),
        )
        self._record_funnel_pipeline_step(
            FUNNEL_STAGES[7],
            survived=volume_contraction_pass_tickers, excluded=volume_contraction_excluded,
            step_conditions=f"마지막 5일 평균 < 베이스 직전 20일 평균 × {p['volume_contraction_ratio']*100:.0f}%",
        )
        self._record_funnel_pipeline_step(
            FUNNEL_STAGES[8],
            survived=final_prepared_tickers,
            step_conditions="모든 단계 통과 — 매수 후보 등록 (base_high 돌파 대기)",
        )

        self._scanned_tickers = list(self._candidates.keys())
        self._bought_today.clear()
        stats["last_run_at"] = datetime.now(KST).isoformat()
        logger.info(
            "VCP 준비 완료: %d/%d종목 — trend=%d base=%d pullback=%d vol_cnt=%d",
            stats["final_prepared"], len(tickers),
            stats["trend_filter_pass"], stats["base_pass"],
            stats["pullback_pass"], stats["volume_contraction_pass"],
        )
        try:
            self._observe_breakout_distance(_dist_refs)
        except Exception:
            logger.debug("[vcp_breakout_distance_failed] 관측 실패 graceful", exc_info=True)

    def _check_trend_filter(self, candles: list[dict], *,
                             effective_ema_long: int | None = None) -> dict | None:
        """추세 필터: 종가 > 단기EMA > 중기EMA > 장기EMA + 장기EMA 우상향 1개월.

        사이클 48 (2026-05-27) — KIS 100일 한도 내 계산 가능하도록 EMA 기간을
        50/60/120 으로 하향 (기존 50/150/200). 리턴 dict 키 `ema150`/`ema200` 은
        레거시 명칭으로 유지 (실제 값은 ema_mid/ema_long. funnel 표시/테스트 호환 — rename 보류).

        사이클 33 (2026-05-21) — KIS 한도 대응: `effective_ema_long` 파라미터로
        가용 길이 기반 자동 축소 가능. None 이면 params["ema_long"] 사용.
        ema_mid 도 effective_ema_long 보다 크면 자동 축소.

        PR #15 (사이클 48) copilot 재리뷰 ① — **실측 표기 정직화**: config ema_long=120 은
        KIS 단일호출 100일 한도 가드(`prepare()` 의 `effective_ema_long =
        min(ema_long, available_len - uptrend_days - 5)`)로 런타임에는 ~75 로 캡된다
        (100일 응답 + uptrend_days=20 → min(120, 100-20-5)=75). 즉 실제 장기선은 ~75EMA,
        ema_mid=60 < 75 라 중기선 자동축소(`ema_mid >= ema_long`)는 발동 안 함 → 실효 정렬은
        50/60/~75. "진짜 120/200EMA" 는 분할 fetch 인프라(운영 1주 후 별도 검토, 사용자 승인
        대기) 가 있어야 계산 가능. 본 PR 은 config 값(120)·매매 동작(진입 빈도) 무변경, 표기만
        실측과 일치(방향 c). uptrend(20일 우상향) 판정은 그대로라 중장기 추세 추종 의도 보존.
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

        # 키 ema150/ema200 은 레거시 명칭 (실제 ema_mid/ema_long=60/120). funnel 표시/테스트
        # 호환 위해 rename 보류 (사이클 48) — 값은 현재 EMA 기간 기준.
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

        사이클 49 (2026-05-31) — "마지막 폭 0.0%" 결함 시정:
        - **ATR threshold swing 검출** (ZigZag 변형). 베이스 ATR × `min_swing_atr_mult` 미만
          변동은 노이즈로 무시. 한국 KRX 우량주 평탄 구간의 1원 단위 미세 swing 폭주 차단.
        - **마지막 swing 미완성 포함**: 마지막 swing high 확정 후 현재까지 진행 중인 pullback 도
          "마지막 pullback" 으로 포함. 기존 단순 검출은 chrono 끝이 rising 이면 마지막 swing 누락
          → `base["last_pullback_pct"]` 미설정 → funnel reason "0.0%" 디폴트 표시 결함.
        - **strict 점진 수축**: `curr < prev` (등호 제거, 동일 폭 거부).
        - **마지막 폭 항상 기록**: False 반환 경로에서도 `base["last_pullback_pct"]` 에 실제 계산값
          (마지막 swing 폭 또는 0) 기록 → funnel reason 정확성 보장.

        운영 결함 (5/26~5/29 33/33 종목 "0.0%" 사유 탈락) 대응. 자세한 root cause 는
        `_workspace/00_leader_trading_rules.md` 6-F 사이클 49 참조.
        """
        p = self.config.params
        last_pullback_max = p["last_pullback_max"]
        pull_min = p["pullback_count_min"]
        pull_max = p["pullback_count_max"]
        min_swing_mult = p.get("min_swing_atr_mult", 0.5)

        try:
            closes = [int(c.get("stck_clpr", "0")) for c in candles[: base["length"]]]
            highs = [int(c.get("stck_hgpr", "0")) for c in candles[: base["length"]]]
            lows = [int(c.get("stck_lwpr", "0")) for c in candles[: base["length"]]]
        except (TypeError, ValueError, KeyError):
            base["last_pullback_pct"] = 0.0
            base["last_pullback_count"] = 0
            return False
        if not closes:
            base["last_pullback_pct"] = 0.0
            base["last_pullback_count"] = 0
            return False

        # 시간순(과거→현재) 으로 reverse
        chrono = list(reversed(closes))
        n = len(chrono)

        # 베이스 ATR 계산 (노이즈 임계) — 베이스 구간 평균 일중 변동폭의 단순 근사
        # full ATR(14) 는 _atr() 헬퍼가 14봉 한정이라 베이스 전체 평균이 더 안정적.
        if highs and lows and len(highs) == len(lows):
            ranges = [h - l for h, l in zip(highs, lows) if h > 0 and l > 0 and h >= l]
            base_atr = (sum(ranges) / len(ranges)) if ranges else 0
        else:
            base_atr = 0
        # ATR 산출 실패 시 종가 평균의 0.3% 폴백 (의미 있는 변동만 인정)
        if base_atr <= 0:
            avg_close = sum(chrono) / n if n > 0 else 0
            base_atr = max(1, int(avg_close * 0.003))
        min_swing_threshold = max(1, base_atr * min_swing_mult)

        # ZigZag 변형 — running_max/min 추적 + threshold 이상 반전 시 swing 확정
        pullbacks: list[float] = []
        # state: 'up' = 상승 추세 추적 중 (running_max 갱신), 'down' = 하락 추세 (running_min 갱신)
        # 초기 방향은 첫 두 봉 비교로 결정
        if n < 2:
            base["last_pullback_pct"] = 0.0
            base["last_pullback_count"] = 0
            return False

        running_max = chrono[0]
        running_min = chrono[0]
        # 초기 방향: 'undefined' — 첫 의미 있는 변동에서 결정
        state = "undefined"
        last_pivot_high: int | None = None  # 직전 확정된 swing high

        for i in range(1, n):
            price = chrono[i]
            if state == "undefined":
                if price - running_min >= min_swing_threshold:
                    state = "up"
                    running_max = price
                elif running_max - price >= min_swing_threshold:
                    state = "down"
                    last_pivot_high = running_max  # 첫 swing high 확정
                    running_min = price
                else:
                    # 임계 미만 — running_max/min 갱신만
                    running_max = max(running_max, price)
                    running_min = min(running_min, price)
            elif state == "up":
                if price >= running_max:
                    running_max = price
                elif running_max - price >= min_swing_threshold:
                    # swing high 확정 → 'down' 진입
                    last_pivot_high = running_max
                    state = "down"
                    running_min = price
            elif state == "down":
                if price <= running_min:
                    running_min = price
                elif price - running_min >= min_swing_threshold:
                    # swing low 확정 → pullback 기록 + 'up' 진입
                    if last_pivot_high is not None and last_pivot_high > running_min:
                        pullbacks.append(
                            (last_pivot_high - running_min) / last_pivot_high
                        )
                    state = "up"
                    running_max = price
                    last_pivot_high = None

        # 마지막 swing 미완성 처리:
        # 1) state='down' 중 끝남 → 마지막 pullback (last_pivot_high → running_min) 진행 중
        # 2) state='up' 중 끝남 → 직전에 확정된 swing low 이후 회복 중 → 추가 pullback 없음
        if state == "down" and last_pivot_high is not None and last_pivot_high > running_min:
            pullbacks.append((last_pivot_high - running_min) / last_pivot_high)

        # 결함 시정 핵심: 결과와 무관하게 마지막 pullback 폭 + 검출 회수 기록
        # (funnel reason 정확성 — pull_count=0 은 "평탄 베이스 swing 미검출" 의미)
        base["last_pullback_pct"] = pullbacks[-1] if pullbacks else 0.0
        base["last_pullback_count"] = len(pullbacks)

        pull_count = len(pullbacks)
        if pull_count < pull_min or pull_count > pull_max:
            return False

        # 점진 수축 (strict — 등호 제거. 동일 폭 거부)
        for prev_pb, curr_pb in zip(pullbacks, pullbacks[1:]):
            if curr_pb >= prev_pb:
                return False

        # 마지막 pullback ≤ last_pullback_max
        if pullbacks[-1] > last_pullback_max:
            return False

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

    async def _scan_universe(self) -> list[str]:
        """stock_master DB 기반 확대 유니버스 (2026-08-08 — kojiro 동일 필터).

        2026-08-08 확대 — 지수(KOSPI200∪KOSDAQ150) 제약 제거 → 전체 상장 ∩ 시총≥500억
        ∩ 거래대금≥10억 (kojiro `_scan_universe` 정합). 미네르비니 VCP 셋업은 대형 지수주가
        아니라 중소형 성장주에서 나오므로 지수 제약이 서식지를 배제해 왔다. 신설 거래대금
        필터가 저유동성 소형주 슬리피지를 방어. 일봉 데이터는 이미 존재(daily-load 유니버스
        = 지수∪500억/10억 = 확대 상위집합, 실측 비지수 자격 641종목 중 95.8%가 ≥100일 적재).

        사이클 157 (2026-06-17) — KOSPI_200_TICKERS/KOSDAQ_150_TICKERS hardcoded list
        + fetch_stock_detail (124 KIS 호출/일) 폐기. KIS API 호출 0건 (사이클 17 LMS chain).
        """
        from src.db import stock_master as _sm_mod
        from src.engine.scanner import ETF_KEYWORDS, ticker_names

        p = self.config.params
        min_mcap = p["min_market_cap"]
        min_trade = p["min_trade_amount"]
        max_stocks = p["max_scan_stocks"]

        try:
            # 2026-08-08 확대 — kojiro 동일 (전체 상장 ∩ 시총 ∩ 거래대금)
            # 사이클 175 — return_stage_counts 로 합집합(union) 노출 (ScanMonitor "합집합" 정합)
            rows, stage = await _sm_mod.list_by_filter(
                min_market_cap=min_mcap,
                min_trade_amount=min_trade,  # 2026-08-08 확대 — 거래대금 필터 신설 (kojiro 동일)
                is_kospi200=None,
                is_kosdaq150=None,
                limit=max_stocks,
                return_stage_counts=True,
            )
        except Exception:
            logger.exception(
                "VCP stock_master.list_by_filter 호출 실패 graceful — 빈 list 반환"
            )
            self._scan_stage_counts = {}
            self._scan_stats["universe_union"] = 0
            self._scan_stats["universe_candidates"] = 0
            self._scan_stats["universe_filtered"] = 0
            return []

        # 사이클 175 — 합집합(union) 노출 (시총 컷 전 원천)
        # 2026-08-08 확대 — funnel step0(union)/step1(trade) 배선용 stage 보관 (kojiro 패턴)
        self._scan_stage_counts = stage
        self._scan_stats["universe_union"] = len(stage.get("union_tickers", rows))
        self._scan_stats["universe_candidates"] = len(rows)
        self._scan_stats["mcap_pass"] = len(rows)  # 사이클 23 P1-3 (list_by_filter 가 이미 mcap 컷)

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
        logger.info(
            "VCP 유니버스 확정: %d/%d종목 (stock_master DB 확대, 전체상장 ∩ 시총 %d억+ ∩ 거래대금 %d억+)",
            len(filtered), len(rows), min_mcap // 100_000_000, min_trade // 100_000_000,
        )

        # 사이클 151 — PriceFilter 후처리 (사이클 148 VB 영역 답습, Q2=C 단일 source 영속)
        filtered = await self._apply_price_filter_in_prepare(filtered)

        return filtered

    _PREPARE_LOG_LABEL = "vcp"  # refactor-review A1·A2 — base 위임 로그 접두사

    def get_scanned_tickers(self) -> list[str]:
        return self._scanned_tickers

    def get_scan_stats(self) -> dict:
        return dict(self._scan_stats)

    def get_targets_status(self) -> dict[str, dict]:
        """대시보드 후보 그리드용 — "왜 안 사는가" 진단 필드 포함 (P3a, 2026-08-06).

        ⚠️ VB 호환 5키(`k`/`target_price`/`open_price`/`target_offset`/
        `open_confirmed`)는 `scheduler._confirm_breakout_open_prices`(8영역)가
        소비한다 — **제거 금지, 추가만**. `strategy_registry` 는 덕타이핑 제네릭이라
        키를 얹으면 registry·route 수정 0 으로 프론트까지 전달된다(kojiro 선례).
        """
        from src.engine.scanner import resolve_ticker_name

        today = datetime.now(KST).date()
        mult = self.config.params["breakout_volume_mult"]
        out: dict[str, dict] = {}
        for ticker, info in self._candidates.items():
            base_high = info.get("base_high", 0)
            cd = self._cooldown_until.get(ticker)
            out[ticker] = {
                "base_high": base_high,
                "base_low": info.get("base_low", 0),
                "atr14": info.get("atr14", 0),
                "ema50": info.get("ema50", 0),
                # 진단 필드
                "name": resolve_ticker_name(ticker),
                "prev_close": info.get("prev_close", 0),
                "stop_line": info.get("base_low", 0),          # 이탈 시 STOP_LOSS
                "volume_threshold": int(info.get("avg_volume_20", 0) * mult),
                "bought_today": ticker in self._bought_today,
                "in_cooldown": bool(cd and cd > today),
                "cooldown_until": cd.isoformat() if cd else None,
                # VB 호환 (제거 금지)
                "k": 0.0,
                "target_price": base_high,
                "open_price": 0,
                "target_offset": 0,
                "open_confirmed": True,
            }
        return out

    def _roll_gate_day_if_needed(self) -> None:
        """cycle228 — 날짜 전환 시 emit cap 자기 리셋 (BFB 동형, VCP 는
        `_breakout_first_seen` 이 없어 cap 만 정리한다). `_vol_latch` 는 entry 별
        `armed_date` 로 이미 자기 무효화된다(`_latch_entry`)."""
        today = datetime.now(KST).date()
        if self._gate_emit_day != today:
            self._gate_emit_day = today
            self._gate_emit_capped.clear()

    def _gate_should_emit(self, ticker: str, kind: str) -> bool:
        """cycle228 — 게이트·래치 로그 cap: (ticker, kind) 1회/일.

        VCP 는 edge-crossing 재트리거로 게이트 이벤트가 다발 가능해 cap 이 필수다.
        `_scan_stats` 카운터는 이 cap 과 무관하게 매 사건 누적된다. 날짜 롤오버는
        `_roll_gate_day_if_needed`(check_buy_signal 최상단)가 담당한다.
        """
        key = (ticker, kind)
        if key in self._gate_emit_capped:
            return False
        self._gate_emit_capped.add(key)
        return True

    def _latch_entry(self, ticker: str) -> dict | None:
        """cycle228 (A3) — 오늘자 래치 엔트리. 날짜가 지났으면 읽는 순간 무효."""
        ent = self._vol_latch.get(ticker)
        if ent is None:
            return None
        if ent.get("armed_date") != datetime.now(KST).date():
            self._vol_latch.pop(ticker, None)
            return None
        return ent

    def _arm_latch(self, ticker: str, base_high: int, base_low: int) -> None:
        """cycle228 (A3) — 충족 래치 무장. **이미 무장돼 있으면 호출하지 마라**
        (armed_at 이 리셋되면 `latch_age_sec` 측정이 무너진다 — 호출부 계약)."""
        now_kst = datetime.now(KST)
        self._scan_stats["latch_armed_count"] += 1
        self._vol_latch[ticker] = {
            "armed_at": now_kst,
            "armed_date": now_kst.date(),
            "base_high": base_high,
            "base_low": base_low,
        }
        if self._gate_should_emit(ticker, "latch_armed"):
            logger.info(
                "[vcp_latch_armed] ticker=%s base_high=%d base_low=%d — 돌파 감지·"
                "거래량 대기(재평가는 base_high 이상 틱에서만)",
                ticker, base_high, base_low,
            )

    def _release_latch(self, ticker: str, reason: str) -> None:
        self._vol_latch.pop(ticker, None)
        # tester D-3 — cap 키에 reason 포함(cycle225 교훈, BFB 동형). 2행/(ticker)/일.
        if self._gate_should_emit(ticker, f"latch_released:{reason}"):
            logger.info("[vcp_latch_released] ticker=%s reason=%s", ticker, reason)

    def _check_extension_cap_invariant(self) -> None:
        """cycle228 (A4) — 추격 상한 리터럴 ↔ 손절 도출 관계 관찰 (fail-open).

        BFB 동형. 캡 도출식 = `(1/(1+stop/100) − 1)×100` — VCP 는 stop −7% →
        +7.53% → 보수적 내림 7.5. 값 자동 보정 금지(운영자 실측 근거 보존).
        """
        try:
            cap = float(self.config.params.get("max_breakout_extension_pct", 0.0))
            stop = float(self.config.params.get("stop_loss_rate", 0.0))
            if cap <= 0 or stop >= 0:
                return
            derived = (1.0 / (1.0 + stop / 100.0) - 1.0) * 100.0
            if derived < cap - 1e-9 or (derived - cap) > 1.0:
                # tester D-2 — 재-prepare 스팸 방지 1회/일 cap (BFB 동형).
                if self._gate_should_emit("_invariant_", "ext_cap_warn"):
                    logger.warning(
                        "[extension_cap_invariant] cap=%.1f stop_loss_rate=%.1f "
                        "derived=%.2f — 리터럴 캡과 손절 도출값이 어긋났다(자동 보정 "
                        "금지 — 사람이 판단)",
                        cap, stop, derived,
                    )
        except Exception:
            return  # 관찰기 자기실패가 prepare 를 막으면 안 된다

    # ------------------------------------------------------------------
    # cycle349 — VCP 관측 3종(①③, ② 보류). 관측 전용 — 매매 행위 0.
    # 명세 = `_workspace/red/cycle349_vcp_observe_spec.md`.
    # ------------------------------------------------------------------
    def _observe_breakout_distance(self, refs: dict[str, dict]) -> None:
        """① D1~D5 — 오전 후보별 돌파선 거리 + run 요약 + ③ E1 watch 교체.

        예외 경계(D6) — 본체 전체를 감싸는 try 는 없다. 종목 단위 계산과 요약 줄은
        각자 try 라 한 종목 실패는 그 줄만 생략된다. 그 밖(파라미터 읽기·watch 교체)
        에서 난 예외는 호출부 2곳(prepare 정상 끝 · `if not tickers:` 조기 반환)의
        자기 try 가 흡수한다 — prepare 는 어느 경우에도 확장 전과 같은 상태로 끝난다.
        `refs[ticker] = {"candles":…, "base":…}` 는 `_candidates[ticker]=…` 대입
        직후 담은 read-only 참조다(D5) — 여기서 `_candidates`/`_scanned_tickers`/
        `_scan_stats`/`_funnel_steps`/`_bought_today`/`scanner.ticker_prev_close`
        어느 것도 쓰지 않는다.
        `box_high_ago` 는 1부터 센다(전일 봉 = 1). cycle347 탐침의 `high_age` 는
        0부터(전일 = 0)라 두 값을 비교할 때는 1을 뺀다.
        """
        p = self.config.params
        now_dt = datetime.now()
        entry_end = _parse_time_hhmm(p["entry_end"])
        if now_dt.time() > entry_end:
            # D1 — 창 끝을 넘은 prepare(16:20 저녁 재준비 등)는 줄도 watch 도 무접촉.
            return
        run_at = now_dt.strftime("%H:%M:%S")

        tickers_order = list(self._candidates.keys())
        dist_values: list[float] = []
        within5 = 0
        over10 = 0

        for ticker in tickers_order:
            try:
                cand = self._candidates.get(ticker) or {}
                base_high = int(cand.get("base_high", 0))
                prev_close = int(cand.get("prev_close", 0))

                ref = refs.get(ticker) if isinstance(refs, dict) else None
                base = ref["base"]
                candles = ref["candles"]
                base_low = int(base.get("low", 0))
                base_len = int(base.get("length", 0))

                box_high_date: str = "na"
                box_high_ago: object = "na"
                for idx, c in enumerate(candles[:base_len]):
                    try:
                        if int(c.get("stck_hgpr", "0")) == base_high:
                            box_high_date = c.get("stck_bsop_date") or "na"
                            box_high_ago = idx + 1
                            break
                    except Exception:
                        continue

                dist_str = "na"
                dist_val: float | None = None
                if prev_close > 0:
                    dist_val = (base_high - prev_close) / prev_close * 100
                    dist_str = f"{dist_val:+.2f}"

                cap_key = (ticker, base_high, prev_close)
                if self._breakout_distance_cap.should_emit(cap_key):
                    logger.warning(
                        "[vcp_breakout_distance] run=%s ticker=%s base_high=%d "
                        "prev_close=%d dist_pct=%s box_high_date=%s box_high_ago=%s "
                        "base_low=%d base_len=%d",
                        run_at, ticker, base_high, prev_close, dist_str,
                        box_high_date, box_high_ago, base_low, base_len,
                    )
                    self._breakout_distance_cap.mark_emitted(cap_key)

                if dist_val is not None:
                    dist_values.append(dist_val)
                    if dist_val <= 5.0:
                        within5 += 1
                    if dist_val > 10.0:
                        over10 += 1
            except Exception:
                continue  # D6 — 한 종목 계산 실패는 그 줄만 생략, 요약은 남는다

        n = len(tickers_order)
        if dist_values:
            srt = sorted(dist_values)
            m = len(srt)
            median = (
                srt[m // 2] if m % 2 == 1
                else (srt[m // 2 - 1] + srt[m // 2]) / 2
            )
            median_str = f"{median:.2f}"
        else:
            median_str = "na"
        tickers_str = ",".join(tickers_order) if tickers_order else "-"

        try:
            # F3 — 「직전」 요약 1개와만 비교한다(하루 전체 dedupe 금지, A→B→A = 3줄).
            # 날짜가 키에 있어 KST 날짜가 바뀌면 같은 내용도 그날 첫 줄로 다시 찍힌다.
            summary_key = (
                datetime.now(KST).date(),
                (n, median_str, within5, over10, tickers_str),
            )
            if summary_key != self._breakout_summary_last:
                logger.warning(
                    "[vcp_breakout_distance_summary] run=%s n=%d median_pct=%s "
                    "within5=%d over10=%d tickers=%s",
                    run_at, n, median_str, within5, over10, tickers_str,
                )
                self._breakout_summary_last = summary_key  # peek→로그→mark
        except Exception:
            pass

        # ③ E1 — 오전 prepare 가 끝날 때(조기 반환 포함) watch 를 통째로 교체한다.
        watch_tickers: dict[str, dict] = {}
        for ticker in tickers_order:
            try:
                base_high_val = int((self._candidates.get(ticker) or {}).get("base_high", 0))
            except Exception:
                base_high_val = 0
            watch_tickers[ticker] = {
                "base_high": base_high_val, "max": 0, "ticks": 0, "first_cross_at": None,
                "first_tick_at": None, "last_tick_at": None,
            }
        self._breakout_watch = {
            "date": datetime.now(KST).date(),
            "run_at": run_at,
            "tickers": watch_tickers,
        }

    def _observe_breakout_tick(self, ticker: str, current_price: int) -> None:
        """③ E2 — 틱 관측 훅. watch 만 읽고 쓴다(never-raise, 반환값 없음).

        `check_buy_signal` 의 계좌 SOFT 게이트(첫 문장) 바로 다음 한 줄로 불린다
        — 그 뒤의 어떤 매수 게이트(buy_disabled/보유/쿨다운 등)보다 앞이라
        `_prev_price`/`_vol_latch`/`_bought_today`/`_scan_stats`/`_gate_emit_capped`
        /`_candidates`/`state` 는 절대 건드리지 않는다.
        `first_tick_at`/`last_tick_at` 은 창 안 첫·마지막 틱 시각(게이트와 같은 naive
        시계)이다 — 관측이 창의 어느 구간을 덮었는지(중간에 끊겼는지) 읽는 근거다.
        """
        try:
            watch = self._breakout_watch
            if not watch:
                return
            tickers_map = watch.get("tickers", {})
            if ticker not in tickers_map:
                return
            if watch.get("date") != datetime.now(KST).date():
                return
            if current_price <= 0:
                return
            p = self.config.params
            now_t = datetime.now().time()
            entry_start = _parse_time_hhmm(p["entry_start"])
            entry_end = _parse_time_hhmm(p["entry_end"])
            if now_t < entry_start or now_t > entry_end:
                return
            ent = tickers_map[ticker]
            now_s = now_t.strftime("%H:%M:%S")
            ent["ticks"] += 1
            if ent.get("first_tick_at") is None:
                ent["first_tick_at"] = now_s
            ent["last_tick_at"] = now_s
            if current_price > ent["max"]:
                ent["max"] = current_price
            if ent["first_cross_at"] is None and current_price >= ent["base_high"]:
                ent["first_cross_at"] = now_s
        except Exception:
            return

    def breakout_event_summary(self, target_date: date) -> dict:
        """③ E3 — 하루 돌파 사건 요약(순수 읽기, never-raise).

        status — `ok`(그날 watch 가 있다) · `no_watch`(오늘(또는 그 뒤) 날짜인데 watch 가
        없다 = 그날 관측 대상이 없어 모른다) · `not_retained`(지난 날짜인데 이
        프로세스가 그날 watch 를 갖고 있지 않다 — 관측됐는지도 모른다. 그날 값의
        정본은 그날 `daily_log_reports.metrics`) · `error`.
        """
        try:
            watch = self._breakout_watch
            if not watch or watch.get("date") != target_date:
                if target_date < datetime.now(KST).date():
                    return {"status": "not_retained", "date": target_date.isoformat()}
                return {"status": "no_watch", "date": target_date.isoformat()}

            p = self.config.params
            entry_start_raw = p.get("entry_start", "")
            entry_end_raw = p.get("entry_end", "")
            run_at = watch.get("run_at", "")

            partial = False
            try:
                run_at_t = datetime.strptime(run_at, "%H:%M:%S").time()
                entry_start_t = _parse_time_hhmm(entry_start_raw)
                partial = run_at_t > entry_start_t
            except Exception:
                partial = False

            tickers_map = watch.get("tickers", {})
            candidates_n = len(tickers_map)
            observed = 0
            crossed_tickers: list[str] = []
            unobserved_tickers: list[str] = []
            per_ticker: dict[str, dict] = {}

            for ticker, ent in tickers_map.items():
                base_high = ent.get("base_high", 0)
                max_val = ent.get("max", 0)
                ticks = ent.get("ticks", 0)
                first_cross_at = ent.get("first_cross_at")
                if ticks > 0:
                    observed += 1
                    gap_pct = (
                        round((max_val - base_high) / base_high * 100, 2)
                        if base_high else None
                    )
                    if base_high and max_val >= base_high:
                        crossed_tickers.append(ticker)
                else:
                    unobserved_tickers.append(ticker)
                    gap_pct = None
                per_ticker[ticker] = {
                    "base_high": base_high, "max": max_val, "gap_pct": gap_pct,
                    "ticks": ticks, "first_cross_at": first_cross_at,
                    "first_tick_at": ent.get("first_tick_at"),
                    "last_tick_at": ent.get("last_tick_at"),
                }

            return {
                "status": "ok",
                "date": target_date.isoformat(),
                "run_at": run_at,
                "window": f"{entry_start_raw}-{entry_end_raw}",
                "partial": partial,
                "candidates": candidates_n,
                "observed": observed,
                "crossed": len(crossed_tickers),
                "crossed_tickers": crossed_tickers,
                "unobserved_tickers": unobserved_tickers,
                "per_ticker": per_ticker,
            }
        except Exception:
            try:
                return {"status": "error", "date": target_date.isoformat()}
            except Exception:
                return {"status": "error", "date": ""}

    # ------------------------------------------------------------------
    # 신호 평가
    # ------------------------------------------------------------------
    def check_buy_signal(self, ticker, current_price, open_price) -> Signal:
        # cycle233 — 계좌 SOFT Σ상한 순간 게이트 (다크런치·fail-open, 신규 매수만)
        if self._account_soft_gate_blocked(ticker):
            return Signal.NONE
        # cycle349 (E2) — 틱 관측 훅. 계좌 게이트 바로 다음, 다른 매수 게이트보다 앞.
        self._observe_breakout_tick(ticker, current_price)
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
        base_low = info.get("base_low", 0)
        if base_high <= 0 or current_price <= 0:
            return Signal.NONE

        # cycle228 — 날짜 전환 시 emit cap 자기 리셋 (scheduler.py diff 0 설계).
        self._roll_gate_day_if_needed()

        # cycle228 (A3) — 충족 래치 재평가. edge-crossing 상태 기계보다 **앞선다**.
        # ⚠️ 이 경로는 `_prev_price` 를 갱신하지 않는다(BFB 동형) — 해제 후 재무장은
        #    **진짜 edge-crossing**(base_high 아래로 내려갔다 재접근)이 있어야 한다.
        latch = self._latch_entry(ticker) if ticker in self._vol_latch else None
        if latch is not None:
            if latch["base_high"] != base_high or latch["base_low"] != base_low:
                # 무장 당시 레벨이 라이브에서 이동 — 무장 근거 소멸(자문 Q1).
                self._release_latch(ticker, "level_moved")
                return Signal.NONE
            if base_low > 0 and current_price < base_low:
                # 베이스 소멸 — `base_low` 이탈은 §2 손절선과 동일 정의다.
                self._release_latch(ticker, "stop_line")
                return Signal.NONE
            if current_price < base_high:
                # 베이스 안 — 래치는 유지하되 아무것도 안 한다(가격 조건 우회 금지).
                return Signal.NONE
            return self._evaluate_vol_gate(ticker, info, current_price, base_high, latch)

        prev = self._prev_price.get(ticker, 0)
        self._prev_price[ticker] = current_price
        if not (prev < base_high <= current_price):
            return Signal.NONE

        # edge-crossing = VCP 의 게이트 최초 평가 지점 (retention 없음 — 자문 Q4,
        # retention 신설은 진입 임계 신설이라 표본 보호와 충돌).
        return self._evaluate_vol_gate(ticker, info, current_price, base_high, None)

    def _evaluate_vol_gate(
        self, ticker: str, info: dict, current_price: int, base_high: int, latch: dict | None,
    ) -> Signal:
        """cycle228 (A1/A4) — 실측 거래량 게이트 + 추격 상한. **소스 = `tick_volume` 뿐.**

        BFB `_evaluate_vol_gate` 동형 + VCP 고유 거울 정합 1건: 구 게이트가
        `if vol_threshold > 0 and acml_vol < vol_threshold` 라 **임계 0 이면 관측과
        무관하게 통과**시켰다 — 그 의미론을 보존한다(임계 0 = 관측 자체가 무의미
        하므로 no_data fail-closed 보다 앞선다).
        """
        avg20 = info.get("avg_volume_20", 0)
        vol_threshold = int(avg20 * self.config.params["breakout_volume_mult"])

        observed: int | None = None
        if vol_threshold > 0:
            try:
                from src.engine import tick_volume

                observed = tick_volume.get_observed_acml_vol(ticker)
            except Exception:
                # team-leader 판정(미결 2) — 읽기 실패 = 미관측(no_data) 취급.
                # fail-closed 유지 + 예외가 on_tick 밖으로 새는 것 차단(P1-5 류).
                logger.debug(
                    "[vcp_vol_gate_read_failed] ticker=%s 관측 읽기 실패 — no_data 처리",
                    ticker, exc_info=True,
                )
                observed = None

            if observed is None:
                self._scan_stats["vol_gate_no_data"] += 1
                if self._gate_should_emit(ticker, "no_data"):
                    logger.warning(
                        "[vcp_vol_gate_no_data] ticker=%s threshold=%d — 미관측 fail-closed",
                        ticker, vol_threshold,
                    )
                if latch is None:
                    self._arm_latch(ticker, base_high, info.get("base_low", 0))
                return Signal.NONE

            if observed < vol_threshold:
                if latch is None:
                    self._arm_latch(ticker, base_high, info.get("base_low", 0))
                return Signal.NONE

        # 거래량 충족(또는 임계 0) — 추격 상한 검사(A4). 판정은 `current_price` 단독.
        cap = float(self.config.params.get("max_breakout_extension_pct", 0) or 0)
        ext_pct = (current_price - base_high) / base_high * 100 if base_high > 0 else 0.0
        if cap > 0 and ext_pct > cap:
            self._scan_stats["vol_gate_reject_ext"] += 1
            if self._gate_should_emit(ticker, "reject_ext"):
                logger.info(
                    "[vcp_vol_gate_reject] ticker=%s reason=extension current_price=%d "
                    "base_high=%d ext_pct=%.2f cap=%.1f",
                    ticker, current_price, base_high, ext_pct, cap,
                )
            if latch is None:
                self._arm_latch(ticker, base_high, info.get("base_low", 0))
            return Signal.NONE

        latch_age_sec = 0
        if latch is not None:
            latch_age_sec = int((datetime.now(KST) - latch["armed_at"]).total_seconds())
        self._vol_latch.pop(ticker, None)

        self._bought_today.add(ticker)
        # P1 — 청산 파라미터 영속화(당일 매수분). 내일 아침 prepare 가 `_candidates`
        # 를 와이프해도 §2 base_low / §3 트레일링 / §4 ema50 이 살아남는다.
        self._position_setup[ticker] = {
            "base_low": info.get("base_low", 0),
            "atr14": info.get("atr14", 0),
            "ema50": info.get("ema50", 0),
        }
        self._scan_stats["vol_gate_pass"] += 1
        logger.info(
            "[vcp_vol_gate_pass] ticker=%s observed=%d threshold=%d latch_age_sec=%d",
            ticker, -1 if observed is None else observed, vol_threshold, latch_age_sec,
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

    # cycle228-B — 구조 레벨(진입 시점 확정 후 **불변**) 키. 지표(atr14/ema50)는 여기 없다.
    _STRUCTURE_KEYS = ("base_low",)

    def _effective_setup(self, ticker: str, *, observe: bool = True) -> dict:
        """청산 파라미터 리졸버 — 구조 레벨 stamp 우선 + 지표 live 우선 (cycle228-B).

        BFB `_effective_setup` 동형(상세 사유는 그쪽 docstring). VCP 구조 레벨은
        `base_low` 하나 — 보유 중 새 베이스 재검출 시 §2 손절선이 새 `base_low`
        (진입가보다 높을 수 있다)로 갈아타는 것을 차단한다. `atr14`/`ema50` 은
        지표라 live 우선 유지(박제 시 상승 추세에서 §4 ema50 이탈 청산이 늦어진다).

        `observe=False` (cycle233 적대 검증 F1) — read-only 소비처(실효 손절선
        미러 → watcher/라우트/20:10 리포트) 전용. `[setup_structure_conflict]`
        발화·cap 소비를 건너뛰어 cycle228-B 마커의 "청산 평가 문맥" D+1 귀인을
        보존한다(watcher 가 cap 을 선소비하면 당일 청산 경로 발화가 억제된다).
        병합 결과는 observe 무관 동일 — 관측 부작용만 분기.
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
            if conflict and observe:
                self._roll_gate_day_if_needed()
                if self._gate_should_emit(ticker, "setup_conflict"):
                    logger.info(
                        "[setup_structure_conflict] ticker=%s — 보유 중 재검출된 "
                        "live 구조 레벨이 진입 stamp 와 다르다(§2 는 stamp 사용). "
                        "stamp=%s live=%s",
                        ticker,
                        {k: stamp.get(k) for k in self._STRUCTURE_KEYS},
                        {k: candidate.get(k) for k in self._STRUCTURE_KEYS},
                    )
            return merged
        if candidate:
            return candidate
        return self._position_setup.get(ticker) or {}

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

        # 1) 하드 손절 — `_entry_atr` 스탬프 존재가 ATR 손절의 자연 게이트.
        #    `sizing_mode` 로 게이팅하면 DB 토글 하나로 **기보유 포지션의 손절 규약**이
        #    바뀌므로 금지 (donchian 2A-2 원칙). 미스탬프 = position_ratio 매수 →
        #    기존 -7% 경로 byte 동일.
        entry_atr = self._entry_atr.get(ticker, 0.0)
        if entry_atr > 0 and pos.buy_price > 0:
            stop_atr = float(params.get("stop_atr", 2.0))
            base_stop = pos.buy_price - stop_atr * entry_atr
            # 최소 폭 밴드 — VCP 는 수축 셋업이라 진입 ATR 이 국소 최소다. 2ATR 이 -3%
            # 수준으로 조여지면 정상 흔들림에도 털린다. 더 낮은(=느슨한) 쪽을 채택.
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
                    "[vcp_turtle_stop] %s 손절선(%d) = 매수가(%d) − %.1f×entry_atr(%.1f)",
                    ticker, int(base_stop), pos.buy_price, stop_atr, entry_atr,
                )
                return Signal.STOP_LOSS
            # % backstop — 고ATR 종목의 손절 폭 최대 캡 (ATR 손절 미발화 구간 방어).
            backstop = float(params.get("turtle_backstop_pct", 0.0) or 0.0)
            if backstop < 0 and loss_rate <= backstop:
                logger.info(
                    "[vcp_turtle_backstop] %s 매수가(%d) 대비 %.1f%% ≤ %.1f%%",
                    ticker, pos.buy_price, loss_rate, backstop,
                )
                return Signal.STOP_LOSS
        else:
            stop_loss = params["stop_loss_rate"]
            if loss_rate <= stop_loss:
                logger.info(
                    "VCP 손절: %s 매수가(%d) 대비 %.1f%%",
                    ticker, pos.buy_price, loss_rate,
                )
                return Signal.STOP_LOSS

        # 1.5) 브레이크이븐 승격 (사이클 C, default-off — live ATR 래치, tighten-only)
        # 터틀 스탬프 포지션은 위 §1 의 스냅샷 승격이 담당 → `entry_atr <= 0` 로 게이팅해
        # 두 tighten 메커니즘 공존을 차단한다. position_ratio 경로는 행위 변화 0.
        # VCP 는 `_candidates[ticker]["atr14"]` live ATR 을 쓰므로 승격 후 ATR 이 팽창하면
        # `buy+mult×atr` 조건이 다시 거짓이 되는 un-latch 병리가 생긴다 (donchian 의
        # entry_atr 스냅샷과 다름) — boolean 래치로 최초 관측 후 ATR 무관 유지.
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
                        "[vcp_breakeven_promote] %s 고점(%d) ≥ 매수가(%d)+%.1f×ATR(%d) → 래치",
                        ticker, pos.high_since_buy, pos.buy_price, breakeven_mult, int(atr_live),
                    )
                if ticker in self._breakeven_latched and current_price <= pos.buy_price:
                    logger.info(
                        "[vcp_breakeven_promote] %s 래치 승격 발화 — 현재가(%d) ≤ 매수가(%d)",
                        ticker, current_price, pos.buy_price,
                    )
                    return Signal.STOP_LOSS

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

    def get_effective_stop_price(self, ticker: str) -> int | None:
        """실효 손절선 read-only 미러 (cycle233 척도 병기).

        `check_exit_signal` 가격선들의 max — §1 터틀 3단 밴드(또는 미스탬프 −7%),
        §1.5 래치 승격선(래치 **읽기만** — 신규 래치 금지), §2 base_low, §3 샹들리에,
        §4 ema50. 로그 무발화·상태 무변조.
        """
        pos = self.state.positions.get(ticker)
        if not pos or pos.buy_price <= 0:
            return None
        try:
            params = self.config.params
            info = self._effective_setup(ticker, observe=False)
            lines: list[float] = []
            entry_atr = self._entry_atr.get(ticker, 0.0)
            if entry_atr > 0:
                stop_atr = float(params.get("stop_atr", 2.0))
                base_stop = pos.buy_price - stop_atr * entry_atr
                min_stop_pct = float(params.get("turtle_min_stop_pct", 0.0) or 0.0)
                if min_stop_pct < 0:
                    base_stop = min(base_stop, pos.buy_price * (1 + min_stop_pct / 100.0))
                be_mult = float(params.get("breakeven_promote_atr", 0) or 0)
                if (be_mult > 0
                        and pos.high_since_buy >= pos.buy_price + be_mult * entry_atr):
                    base_stop = max(base_stop, float(pos.buy_price))
                if base_stop > 0:
                    lines.append(base_stop)
                backstop = float(params.get("turtle_backstop_pct", 0.0) or 0.0)
                if backstop < 0:
                    lines.append(pos.buy_price * (1 + backstop / 100.0))
            else:
                stop_loss = float(params["stop_loss_rate"])
                lines.append(pos.buy_price * (1 + stop_loss / 100.0))
                # §1.5 live ATR 래치 — 이미 래치된 종목만 승격선(read-only)
                be_mult = float(params.get("breakeven_promote_atr", 0) or 0)
                if be_mult > 0 and ticker in self._breakeven_latched:
                    lines.append(float(pos.buy_price))
            base_low = (info.get("base_low") or 0) if info else 0
            if base_low:
                lines.append(float(base_low))
            if info and pos.high_since_buy > 0:
                atr = info.get("atr14", 0)
                if atr > 0:
                    mult = float(params["atr_trail_mult"])
                    lines.append(pos.high_since_buy - atr * mult)
            ema50 = (info.get("ema50", 0) or 0) if info else 0
            if ema50 > 0:
                lines.append(float(ema50))
            positives = [line for line in lines if line > 0]
            return int(max(positives)) if positives else None
        except Exception:
            return None  # fail-open — 프록시 폴백

    def check_force_clear(self) -> list[str]:
        """멀티데이 — 15:20 강제 청산 없음."""
        return []

    def calc_buy_quantity(self, current_price: int, ticker: str | None = None) -> int:
        """할당 자금의 position_ratio 비중. 예산 잔여로 클램프(`_apply_budget_limit`).

        B-2 게이트 2: `sizing_mode="turtle"` + ticker 지정 시 터틀 유닛 sizing 우선.
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
        """터틀 유닛 수량 + `_entry_atr` 원자 스탬프 (donchian `_turtle_buy_quantity` 답습).

        `_candidates[ticker]["atr14"]`(prepare D-1 ATR)를 sizing 과 하드손절 entry_atr
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
            logger.debug("[vcp_turtle_sizing_fallback] %s — position_ratio 낙하",
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

    async def recompute_high_since_buy(self) -> None:
        """보유 종목의 `high_since_buy` 를 매수일~전영업일 일봉 high max 로 보정.

        사이클 C (C-V4) — donchian_swing `recompute_high_since_buy` 패턴 이식. 재시작 시
        시세 미수신이 누적되어 `high_since_buy` 가 매수가 부근에 동결되면 브레이크이븐
        래치(C-V1)가 형성되지 않는 결함을 예방한다.

        sequential await — KIS Rate Limit 안전(`asyncio.gather` 등 병렬 금지). 일봉
        fetch 예외/빈 응답은 해당 종목만 skip, 다른 포지션은 계속.
        """
        from src.api.condition import fetch_daily_candles

        params = self.config.params
        ema_long = params["ema_long"]
        base_max = params["base_max_days"]
        today = datetime.now(KST).date()

        for ticker in list(self.state.positions.keys()):
            pos = self.state.positions.get(ticker)
            if not pos:
                continue
            if pos.buy_date >= today:
                if pos.buy_date > today:
                    logger.warning(
                        "VCP high_since_buy 보정 skip — buy_date 비정상(미래): "
                        "%s buy_date=%s today=%s",
                        ticker, pos.buy_date, today,
                    )
                continue

            days_held = (today - pos.buy_date).days
            fetch_days = max(days_held + 5, ema_long + 5, base_max + 5, 10)
            try:
                candles = await fetch_daily_candles(ticker, days=fetch_days)
            except Exception:
                logger.exception("VCP high_since_buy 보정 일봉 fetch 실패: %s", ticker)
                continue
            if not candles:
                continue
            # B-2 게이트 2 — 터틀 entry_atr 재시작 재도출. **같은 fetch 응답 재사용**이라
            # 추가 KIS 호출 0 + scheduler 배선 변경 0. in-memory 스탬프가 남아 있으면
            # (당일 매수 · 미재시작) 정확한 진입 ATR 이므로 미접촉.
            # cycle355 — 스탬프가 없으면 **turtle 로 사는 전략일 때만** 되살린다
            # (position_ratio 랏은 처음부터 미스탬프 — 되살리면 −7% 고정 손절이 바뀐다).
            if ticker not in self._entry_atr and self._entry_atr_rederive_allowed(ticker):
                self._rederive_entry_atr(ticker, pos, candles, params["atr_period"])
            # P1 — 청산 지표(atr14/ema50) 일일 갱신. **같은 candles 재사용**이라
            # KIS 추가 호출 0 + scheduler 배선 변경 0.
            self._refresh_position_setup_from_candles(ticker, pos, candles)
            await self._apply_high_since_buy_from_candles(pos, candles, today)

    def _refresh_position_setup_from_candles(self, ticker: str, pos, candles: list[dict]) -> None:
        """보유 종목의 청산 파라미터를 최신 일봉으로 정비한다.

        필드 성격에 따라 규약이 다르다:

        - **지표** (`atr14` / `ema50`) → 매번 재계산. 매일 변하는 값이라 진입 시점
          스냅샷을 박제하면 상승 추세에서 `ema50` 이 뒤처져 §4 이탈 청산이 늦어진다.
        - **구조 레벨** (`base_low`) → 진입 시점 베이스에서 확정된 값이라 **이미 있으면
          건드리지 않는다**. 없을 때만(=프로세스 재시작으로 소실) `_candidates` 보강 →
          그것도 없으면 **매수일 *이전* 봉으로 베이스 재검출**을 시도한다. 재검출
          실패 시엔 미복구로 남긴다 — 잘못된 레벨로 손절선을 긋느니 §1 하드손절에
          맡기는 편이 낫다(fail-safe, 절대 현행보다 나빠지지 않는다).

        어떤 실패도 흡수한다 — 갱신 실패 시 기존 값이 남아 청산은 계속 산다.
        """
        if not candles:
            return
        try:
            params = self.config.params
            highs = [int(c.get("stck_hgpr", "0") or 0) for c in candles]
            lows = [int(c.get("stck_lwpr", "0") or 0) for c in candles]
            closes = [int(c.get("stck_clpr", "0") or 0) for c in candles]
            atr = self._atr(highs, lows, closes, params["atr_period"])
            period = int(params["ema_short"])
            # `_atr` 는 KIS 최신순, `_ema` 는 시간순을 기대한다 (prepare 와 동일 규약).
            chrono = list(reversed(closes))
            ema50 = self._ema(chrono[-period:], period) if len(chrono) >= period else 0.0

            cur = dict(self._position_setup.get(ticker) or {})
            live = self._candidates.get(ticker) or {}
            if not cur.get("base_low"):
                if live.get("base_low"):
                    cur["base_low"] = live["base_low"]
                else:
                    rederived = self._rederive_base_low(ticker, pos, candles)
                    if rederived:
                        cur["base_low"] = rederived
            if atr > 0:
                cur["atr14"] = int(atr)
            if ema50 > 0:
                cur["ema50"] = int(ema50)
            if cur:
                self._position_setup[ticker] = cur
        except Exception:
            logger.exception("[vcp_setup_refresh] 청산 셋업 갱신 실패 fail-open: %s", ticker)

    def _rederive_base_low(self, ticker: str, pos, candles: list[dict]) -> int:
        """매수일 **이전** 봉만으로 베이스를 재검출해 `base_low` 를 복원한다.

        매수일 당일/이후 봉을 섞으면 돌파 이후 구간이 박스에 포함돼 베이스가
        왜곡된다. 재검출이 실패하면 **0** — 호출자가 미복구로 남긴다.
        """
        try:
            if pos is None or not getattr(pos, "buy_date", None):
                return 0
            buy_dd = pos.buy_date.strftime("%Y%m%d")
            prior = [c for c in candles if str(c.get("stck_bsop_date", "")) < buy_dd]
            if len(prior) < self.config.params["base_min_days"]:
                return 0
            base = self._detect_base(prior)
            low = int((base or {}).get("low", 0) or 0)
            if low > 0:
                logger.info("[vcp_setup_rederive] %s base_low=%d (매수일 이전 봉 재검출)",
                            ticker, low)
            return low
        except Exception:
            logger.exception("[vcp_setup_rederive] base_low 재검출 실패: %s", ticker)
            return 0

    # `_apply_high_since_buy_from_candles` 는 `StrategyBase` 로 승격(H-1, 2026-08-06).
    # 아래 라벨이 추출 전 로그 리터럴("VCP high_since_buy 보정")을 byte 단위로 보존한다.
    _HIGH_RECOVER_LABEL = "VCP"
    _ENTRY_ATR_REDERIVE_LABEL = "vcp"
    _COOLDOWN_LOG_LABEL = "[vcp]"  # refactor-review A3 — base 위임 로그 접두사

    def on_position_closed(self, ticker: str) -> None:
        """사이클 191 — 포지션 청산 시 재진입 쿨다운 등록 (VCP override, BFB 패턴 답습).

        사이클 C (C-V5) — 브레이크이븐 래치 정리 동행 (재진입 stale 차단).
        B-2 게이트 2 — 터틀 entry_atr 정리 동행 (재진입 stale 스냅샷 차단).
        """
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
