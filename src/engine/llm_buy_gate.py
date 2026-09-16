"""cycle276 — AI 매수평가(LLM shadow) **주문 시점** leaf. **매매 행위 변경 0.**

정본 = `_workspace/red/cycle276_order_time_llm_eval_spec.md` §6 (C17~C30) ·
cycle274 자문 `_workspace/domain_consult/cycle274_llm_buy_gate_20260910.md`
(§5.3 `_evaluate` · §5.4 자원 상한 · §6.2 키 · §6.4 출력 검증).

`order_engine.execute_buy` 가 `place_order` 에 성공한 **직후**(매핑 등록 뒤 · PENDING
INSERT 앞)에서 주문 1건을 동기로 접수해 `asyncio.create_task` 로 던지고 즉시 리턴한다.
주문은 이미 KIS 에 접수됐고 이 leaf 는 **기록만** 한다 — 주문을 막지도, 늦추지도,
바꾸지도 않는다. `enforce` 는 이 사이클에 미구현이고 `shadow` 외 모든 값은 `off` 낙하다.

## cycle274 와 무엇이 다른가 (시각 의미 이동 — **배포 전후 로그 합산 금지**)
- 진입점이 `observe_signal`(신호 시점) → **`observe_order`(주문 접수 시점)** 으로 옮겼다.
  cycle274 는 신호 10건 중 5건만 주문이 돼 점수 절반이 실현손익에 붙지 않았다.
- 래치 키가 `(전략, 종목)/일` → **주문번호**다. 같은 종목을 하루 두 번 사면 두 번 평가한다.
- 표류 필드가 **`post_order_drift_bp`** 로 개명됐다(구 이름과 부호 **의미**가 반대다 —
  이제 + 는 주문 뒤 상승 = 이득). `signal_kst`/`signal_price` → `order_kst`/`order_price`.
- 평가 결과를 로그뿐 아니라 **DB(`llm_buy_evaluations`)에도 1행** 남긴다(성공·실패 모두).

## leaf 계약
- `observe_order` — 동기·never-raise·`await`/DB/HTTP 0·반환 항상 `None`.
- `_evaluate` — async 진입. `_evaluate_core` 의 outcome 을 받아 **단 1곳**에서
  `_persist_evaluation` 한다(C24).
- `_evaluate_core` — 세마포어 2 → 일봉 캐시(60봉 fetch, 오늘봉 폐기, 30봉만 프롬프트에
  싣는다) → LLM 호출(`asyncio.wait_for` 타임아웃) → 출력 검증(클램프 금지) → outcome.
- `src.*` import 는 §10 허용 목록(`daily_emit_cap`·`observer_trace`·`llm_features`·
  `config`·`db.stock_master_daily`)으로 한정 — **모듈 최상단**에서만. `scanner`·
  `tick_volume`·`log_analysis_engine`·`db.llm_buy_evaluations` 는 전부 함수 내
  **지연 import**(순환 차단 · §10 허용 목록 밖이라 최상단에 나타나면 안 된다).
- 보드는 세션 트래커가 아니라 **시계**로 푼다(`_board_by_clock`) — leaf 는 8영역 모듈을
  참조하지 않고(C22), 트래커의 활성 보드는 30초 stale 이라 09:00:0x 에 `pre_nxt` 로
  굳는다(cycle264 실증).
- 실패는 전부 `[llm_buy_score_failed] reason=` 10종 어휘 중 하나로 남긴다:
  timeout / api_error / parse_error / schema_error / no_bars / no_key /
  cap_exceeded / disabled_model / payload_error(검증 라운드2 파인딩 #10 —
  자문 §6.1/§7.1 의 8종 밖 확장, `spec_disagreements` 등재) /
  truncated(09-11 운영 실측 — 추론 토큰이 출력 한도를 먹어 `content=""`).
  그 행에는 `finish=`(OpenAI `finish_reason` 원문, LLM 호출 전 실패는 `-`)도 실린다.
  `empty_order_no` 는 **평가 어휘가 아니라 persist 어휘**다(C21/C28) — persist 사유를
  평가 실패 분포에 섞으면 20:10 리포트의 실패 분류가 오염된다. `cap_exceeded` 도
  persist 채널에서만 발화한다(평가를 시작하지 않은 주문, 검증 라운드 3 #3).
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time as _wall_clock
from datetime import datetime, timedelta, timezone
from decimal import Decimal as _Decimal

from src.config import settings
from src.db.stock_master_daily import get_recent_daily_normalized
from src.engine.daily_emit_cap import KstDailyEmitCap
from src.engine.llm_features import (
    build_messages,
    compute_technicals,
    normalize_volume_ratio,
    pct_change,
    safe_ratio,
)
from src.engine.observer_trace import trace_observer_failure

logger = logging.getLogger(__name__)


def _monotonic() -> float:
    """`time.monotonic()` 래퍼 — 테스트가 **이 이름만** monkeypatch 하도록 분리한다
    (검증 라운드2 파인딩 #4 회귀 가드). 전역 `time.monotonic` 을 직접 패치하면
    asyncio 이벤트루프 내부 타이머까지 오염된다(`open_price_rest._monotonic` 선례
    — cycle272 `src/engine/open_price_rest.py:456`)."""
    return _wall_clock.monotonic()

MARKER_SCORE = "[llm_buy_score]"
MARKER_FAILED = "[llm_buy_score_failed]"
MARKER_CONFIG = "[llm_gate_config]"
MARKER_DAILY_CAP = "[llm_gate_daily_cap]"
# cycle276 — DB 기록의 성공/실패를 남기는 **유일한 채널**. 이 마커가 없으면
# "평가 안 함" 과 "기록 실패" 가 구별되지 않는다(C25).
MARKER_PERSIST = "[llm_eval_persist]"

# KST — leaf 는 `scanner.KST_TZ` 를 끌어오지 않는다(순환 차단, 모듈 로컬 정의 관례).
_KST_TZ = timezone(timedelta(hours=9))

# 실패 사유 전체 어휘(자문 §7.1 ②) — `[llm_buy_score_failed] reason=` 이 쓰는
# 8종 + 검증 라운드2 파인딩 #10 이 추가한 `payload_error`. `cap_exceeded` 는
# `[llm_buy_score_failed]`(평가 실패) 어휘로는 **여전히 발화하지 않는다** — 일일 cap
# 도달은 평가를 시작하지도 않기 때문이다. 대신 검증 라운드 3 #3 이 지적한 주문 단위
# 복원 불가를 막기 위해 `[llm_eval_persist] result=error reason=cap_exceeded` 로
# 주문마다 1행을 남긴다(마커가 다르므로 20:10 리포트의 실패 분포는 섞이지 않는다).
# 전략 단위 요약은 종전대로 `[llm_gate_daily_cap]` WARNING 1회/전략/일이다(§7.1 ④, C7).
#
# `payload_error` — **자문 §6.1/§7.1 이 정의한 8종 밖의 확장**(spec_disagreements
# 등재). 프롬프트 조립 실패(`build_messages`, `json.dumps` 포함)를 LLM 출력
# 검증 실패(`schema_error` — "모델이 스키마를 벗어났다")와 같은 어휘로 뭉개면
# "우리 코드가 페이로드를 못 만든다"와 "모델이 이상한 걸 준다"를 20:10 리포트가
# 구별할 수 없다(검증 파인딩 #10). `_evaluate` 는 `build_messages` 실패를
# **이 값으로만** 분류한다 — LLM 응답 파싱/검증 실패는 여전히 `schema_error`다.
#
# `truncated` — **추론 모델의 출력 한도 소진**(cycle276 후속, 09-11 운영 실측). 추론
# 토큰이 `max_completion_tokens` 를 같이 먹으므로 한도가 모자라면 `finish_reason="length"`
# + `content=""` 가 와서 파싱이 실패한다. 그것을 `schema_error`("모델이 스키마를
# 벗어났다")로 뭉개면 20:10 리포트가 "모델 출력이 이상하다" 와 "우리가 한도를 너무
# 낮게 줬다" 를 구별할 수 없다 — 전자는 프롬프트 문제, 후자는 상수 한 줄 문제다.
_FAILURE_REASONS = (
    "timeout", "api_error", "parse_error", "schema_error",
    "no_bars", "no_key", "cap_exceeded", "disabled_model",
    "payload_error", "truncated",
)

_DEFAULT_MODE = "shadow"
_DEFAULT_MIN_SCORE = 70
_DEFAULT_DAILY_CAP = 20
_DEFAULT_TIMEOUT = 20

_BARS_CACHE_MAX = 400
_BARS_FETCH_DAYS = 60
_BARS_MIN_REQUIRED = 30
_PROMPT_BAR_COUNT = 30
# `gpt-5.6-luna` 는 **추론 모델**이라 추론 토큰이 `max_completion_tokens` 를 함께
# 소비한다. 09-11 운영 컨테이너 실측(같은 프롬프트, 한도만 바꿔 재현) —
#
#   한도   finish_reason   content 길이   reasoning_tokens   결과
#   3000   stop            218            202                score 43 정상
#    400   stop            270            203                score 44 정상(여유 30)
#    250   length            0            250                빈 문자열 → 실패
#    150   length            0            150                빈 문자열 → 실패
#
# 400 은 실측 여유가 30 토큰뿐이라 추론이 조금만 길어지면 전건 실패한다(09-11 09:0x
# 실전 2건이 `reason=schema_error latency_ms=10047/5514` 로 끝난 그 경로). 2000 은
# 실측 최대 소비(≈470)의 4배 여유다.
#
# ⚠️ **비용은 오르지 않는다** — 과금은 실제 사용 토큰이고 이 상수는 상한일 뿐이다.
# 한도를 올려도 모델이 더 쓰지 않는다(위 표의 3000 행이 218자·202 추론토큰).
_MAX_COMPLETION_TOKENS = 2000

# 세마포어 2 — 09:01:30 해제 순간 다수 종목이 동시 돌파할 수 있다(실측 09-08
# 09:01:34/09:01:42 8초 간격 2건). 2면 8초 안에 4건을 소화한다(자문 §5.4).
_SEM = asyncio.Semaphore(2)

# 진행 중 task 강참조 — asyncio 는 참조가 사라지면 GC 한다.
_tasks: set = set()

# 래치 = KstDailyEmitCap[order_no] **별도 인스턴스**(cycle236 '별개 cap' 계약 —
# emit cap 과 슬롯을 다투지 않는다). cycle276 에서 키가 `(전략, 종목)/일` → **주문번호**
# 로 바뀌었다: 같은 종목을 하루 두 번 사면 주문이 둘이므로 두 번 평가한다(09-10 000990
# 처럼 12:06 첫 신호의 점수가 15:13 주문에 붙던 사고가 옛 키에서 나왔다).
_latch: "KstDailyEmitCap[str]" = KstDailyEmitCap()

# 일일 cap 도달 WARNING 은 1회/전략/일.
_daily_cap_warned: "KstDailyEmitCap[str]" = KstDailyEmitCap()

# `[llm_gate_config]` 카나리아 — 1회/(전략, mode, min_score)/일.
_config_canary_latch: "KstDailyEmitCap[tuple]" = KstDailyEmitCap()

# 일봉 캐시 — (ticker, KST 날짜문자열) → filtered rows. 일봉은 하루 안에 변하지
# 않으므로 종목당 DB 1회/일이 계약이다(§3.1). 상한 400 종목, 초과 시 FIFO 축출.
_bars_cache: "dict[tuple[str, str], list]" = {}

# 일일 호출 카운트(전략별) — (day, count) 자기 리셋.
_call_count_day: str = ""
_call_count: "dict[str, int]" = {}

# OpenAI 클라이언트 싱글톤(모듈 전역, hot path 커넥션 재사용).
_client_singleton = None


def reset_llm_buy_gate_state() -> None:
    """래치·cap·일봉 캐시·전략별 prompt_version 캐시 일괄 초기화(테스트·운영 훅 — cycle264/268 선례)."""
    global _latch, _daily_cap_warned, _config_canary_latch, _bars_cache
    global _call_count_day, _call_count, _tasks, _prompt_version_cache
    _latch = KstDailyEmitCap()
    _daily_cap_warned = KstDailyEmitCap()
    _config_canary_latch = KstDailyEmitCap()
    _bars_cache = {}
    _call_count_day = ""
    _call_count = {}
    _tasks = set()
    _prompt_version_cache = {}


# ---------------------------------------------------------------------------
# 파라미터 읽기 — 결측/파싱 실패의 낙하값이 키마다 다르다(§6.2). 클램프 없이
# 그냥 삼키면 P0-1 유령 키 재현 경로이므로 개별 try/except 로 방어한다.
# ---------------------------------------------------------------------------


def _read_mode(params) -> str:
    try:
        raw = params.get("llm_gate_mode")
    except Exception:
        return "off"
    try:
        norm = str(raw).strip().lower() if raw is not None else ""
    except Exception:
        return "off"
    return "shadow" if norm == "shadow" else "off"


def _read_min_score(params) -> int:
    try:
        raw = params.get("llm_gate_min_score")
    except Exception:
        return _DEFAULT_MIN_SCORE
    if raw is None:
        return _DEFAULT_MIN_SCORE
    try:
        val = int(raw)
    except Exception:
        return _DEFAULT_MIN_SCORE
    return val if 1 <= val <= 100 else _DEFAULT_MIN_SCORE


def _read_daily_cap(params) -> int:
    """키 부재 = **0**(= 호출 안 함) — 돈을 쓰는 기능은 설정 없으면 안 한다."""
    try:
        raw = params.get("llm_gate_daily_call_cap")
    except Exception:
        return 0
    if raw is None:
        return 0
    try:
        val = int(raw)
    except Exception:
        return 0
    return max(0, min(200, val))


def _read_timeout(params) -> int:
    try:
        raw = params.get("llm_gate_timeout_secs")
    except Exception:
        return _DEFAULT_TIMEOUT
    if raw is None:
        return _DEFAULT_TIMEOUT
    try:
        val = int(raw)
    except Exception:
        return _DEFAULT_TIMEOUT
    return max(1, min(60, val))


def _read_position_ratio(params) -> float:
    try:
        return float(params.get("position_ratio", 0) or 0)
    except Exception:
        return 0.0


def _read_acml_vol_shares(ticker):
    """§3.3 B군 — 실측 누적거래량(주). `tick_volume` 은 §10 leaf 허용 import
    목록 밖이라 **함수 내 지연 import** 로 읽는다(검증 파인딩 #2, `scanner` 와
    같은 지연 import 패턴 — leaf 모듈 최상단에는 나타나지 않는다). 미관측은
    `None`(sentinel 계약 — `tick_volume.py` — `0` 으로 위장 금지)."""
    try:
        from src.engine.tick_volume import get_observed_acml_vol
        return get_observed_acml_vol(str(ticker))
    except Exception:
        return None


def _cost_usd(model: str, tokens_in: int, tokens_out: int) -> float:
    """모델별 단가로 비용 추정. 정본 = `log_analysis_engine._OPENAI_PRICING`
    (중복 금지 — 검증 파인딩 #9, 모델을 바꾸면 그 표 하나만 갱신하면 된다).
    미등록 모델·조회 실패는 **-1.0**(모른다를 정직하게 남긴다 — 하드코딩된
    잘못된 단가로 비용을 조용히 틀리게 찍지 않는다). 함수 내 지연 import —
    leaf 는 그 모듈을 §10 허용 목록에 두지 않았다."""
    try:
        from src.engine.log_analysis_engine import _OPENAI_PRICING
        pricing = _OPENAI_PRICING.get(str(model))
        if pricing is None:
            return -1.0
        input_per_1k, output_per_1k = pricing
        return (float(tokens_in) / 1000.0 * input_per_1k) + (float(tokens_out) / 1000.0 * output_per_1k)
    except Exception:
        return -1.0


def _read_stop_loss_pct(strategy_id, params) -> float:
    """§3.3 — 관측 시점(ATR 재해석 **전**) 손절폭. 7전략 전부 `< 0`(cycle297 §1.2 F6 —
    0.0 은 SYSTEM_PROMPT 판단 기준 4 를 항상 발동시키는 거짓말이다)."""
    try:
        if strategy_id == "volatility_breakout":
            return float(params.get("stop_loss_rate", -3.0) or 0)
        if strategy_id == "long_tail_volatility":
            return float(params.get("intraday_stop_loss", -3.0) or 0)
        if strategy_id == "momentum":
            return float(params.get("stop_loss_rate", -7.5) or 0)
        if strategy_id == "donchian_swing":
            return float(params.get("stop_loss_rate", -7.0) or 0)
        if strategy_id == "bull_flag_breakout":
            return float(params.get("stop_loss_rate", -5.0) or 0)
        if strategy_id == "vcp_breakout":
            return float(params.get("stop_loss_rate", -7.0) or 0)
        if strategy_id == "kojiro":
            return float(params.get("hard_stop_pct", -8.0) or 0)
    except Exception:
        pass
    return 0.0


# cycle297 검증 — `_resolve_stop_loss_pct` 가 `_evaluate_core` 에서 재해석을 하려면
# 그 시점에 **원시 params** 가 필요하다. `payload` 는 `observe_order` 가 만든 task 전용
# 값 복사본이므로 여기에 최소 키만 실어 보낸다(전략 객체·`config.params` 원본 참조 금지,
# C23 — 값 복사만). 목록을 좁게 둔 이유 = 넓히면 그만큼 payload 표면이 커지고, 이 dict 는
# `_PAYLOAD_EXCLUDED_KEYS` 로 `input_payload` 에서 떨어지므로 감사 가치도 없다(재해석
# 결과 `stop_loss_pct` 와 `tech.atr14_pct` 가 이미 `input_payload` 에 남아 검산된다).
_STOP_PARAM_KEYS = (
    "sizing_mode", "stop_atr", "turtle_backstop_pct", "turtle_min_stop_pct",
    "hard_stop_pct", "stop_loss_rate", "intraday_stop_loss",
)


def _read_stop_params(params) -> dict:
    """`_resolve_stop_loss_pct` 가 쓸 최소 키만 값 복사. never-raise."""
    try:
        p = params if isinstance(params, dict) else {}
        return {k: p.get(k) for k in _STOP_PARAM_KEYS if k in p}
    except Exception:
        return {}


def _resolve_stop_loss_pct(strategy_id, params, tech) -> float:
    """§3.3 — ATR 손절 전략의 재해석. `_read_stop_loss_pct` 관측값을 그 시점 `atr14_pct`
    로 다시 읽는다. **항상 음수**(0.0/양수 위장 금지 — G1-9c).

    - kojiro: sizing_mode 무관, 항상 `max(hard_stop_pct, -(stop_atr×atr))`.
    - donchian_swing: `sizing_mode=="turtle"` 일 때만 `max(-(stop_atr×atr), turtle_backstop_pct)`
      (타이트한 쪽 — 느슨한 쪽을 고르면 "손절이 잡음보다 넓다" 는 거짓을 모델에 먹인다).
    - bull_flag_breakout/vcp_breakout: `sizing_mode=="turtle"` 일 때만
      `clamp(-(stop_atr×atr), turtle_backstop_pct, turtle_min_stop_pct)`.
    - 그 밖(momentum/VB/LTV, 비-터틀) — 고정 `_read_stop_loss_pct` 값 그대로.
    - `atr14_pct` 결측/비수치는 고정값으로 fail-open(0.0 위장 금지).
    """
    p = params if isinstance(params, dict) else {}
    t = tech if isinstance(tech, dict) else {}
    fixed = _read_stop_loss_pct(strategy_id, p)
    if not (fixed < 0.0):
        fixed = -0.01

    try:
        raw_atr = t.get("atr14_pct")
        atr = (
            float(raw_atr)
            if isinstance(raw_atr, (int, float)) and not isinstance(raw_atr, bool)
            else None
        )
    except Exception:
        atr = None

    try:
        if strategy_id == "kojiro":
            hard = float(p.get("hard_stop_pct", -8.0) or -8.0)
            if not (hard < 0.0):
                hard = -0.01
            if atr is None:
                return hard
            stop_atr = float(p.get("stop_atr", 2.0) or 2.0)
            got = max(hard, -(stop_atr * atr))
            return got if got < 0.0 else -0.01

        if strategy_id == "donchian_swing" and p.get("sizing_mode") == "turtle" and atr is not None:
            stop_atr = float(p.get("stop_atr", 2.0) or 2.0)
            backstop = float(p.get("turtle_backstop_pct", -9.0) or -9.0)
            got = max(-(stop_atr * atr), backstop)
            return got if got < 0.0 else -0.01

        if (
            strategy_id in ("bull_flag_breakout", "vcp_breakout")
            and p.get("sizing_mode") == "turtle"
            and atr is not None
        ):
            stop_atr = float(p.get("stop_atr", 2.0) or 2.0)
            backstop = float(p.get("turtle_backstop_pct", -9.0) or -9.0)
            min_stop = float(p.get("turtle_min_stop_pct", -4.0) or -4.0)
            got = max(backstop, min(-(stop_atr * atr), min_stop))
            return got if got < 0.0 else -0.01
    except Exception:
        return fixed

    return fixed


def _read_exit_rule(strategy_id, params) -> str:
    """§3.3 — 라이브 params 값을 인용하는 청산 규약 문구. 하드코딩 금지(test_f3_10 답습) —
    값이 바뀌면 문구도 따라 변해야 한다(G1-8c)."""
    try:
        if strategy_id == "volatility_breakout":
            sl = params.get("stop_loss_rate", -3.0)
            return (
                f"손절 {sl}%. 익절·트레일링 없음. "
                "당일 15:20 전량 시장가 청산(오버나잇 없음)."
            )
        if strategy_id == "long_tail_volatility":
            sl = params.get("intraday_stop_loss", -3.0)
            limit_up = params.get("limit_up_threshold", 29.0)
            overnight = params.get("overnight_stop_loss", -5.0)
            gap_up = params.get("gap_up_threshold", 10.0)
            trailing = params.get("trailing_stop_rate", -2.0)
            return (
                f"상한가(+{limit_up}%) 미도달 = 당일 {sl}%·15:20 청산 / "
                f"상한가 도달 = 익일 청산 모드(오버나잇 {overnight}%, "
                f"갭업 +{gap_up}% 청산, 트레일 {trailing}%)"
            )
        if strategy_id == "momentum":
            sl = params.get("stop_loss_rate", -7.5)
            gap = params.get("gap_up_threshold", 10.0)
            trail = params.get("trailing_stop_rate", -2.0)
            return (
                f"손절 {sl}%. 상한가를 못 잠그면 익일 시가 청산 — "
                f"갭 +{gap}% 이상이면 트레일링 {trail}%, 아니면 즉시 매도."
            )
        if strategy_id == "donchian_swing":
            mult = params.get("atr_trail_mult", 2.0)
            stop_atr = params.get("stop_atr", 2.0)
            backstop = params.get("turtle_backstop_pct", -9.0)
            fail_n = params.get("breakout_fail_n_days", 5)
            ch_period = params.get("channel_exit_period", 10)
            return (
                f"ATR×{mult} 샹들리에 트레일링. 하드손절 = 진입ATR×{stop_atr} 또는 "
                f"{backstop}% 백스톱(터틀 모드, 타이트한 쪽) / 비율 모드는 고정 손절. "
                f"{fail_n}영업일 돌파 실패 청산, {ch_period}일 저가 채널 이탈 청산. "
                "시간·15:20 청산 없음(멀티데이 보유). "
                "입력의 stop_loss_pct 는 ATR(14) 기준 근사다(실제는 진입 시점 ATR)."
            )
        if strategy_id == "bull_flag_breakout":
            sl = params.get("stop_loss_rate", -5.0)
            mult = params.get("atr_trail_mult", 2.0)
            hold = params.get("max_hold_days", 5)
            return (
                f"손절 {sl}%. flag_low 이탈 또는 측정 이동(flag_high+폴 높이) 도달 시 "
                f"청산. ATR×{mult} 트레일링, {hold}영업일 시간 청산. "
                "입력의 stop_loss_pct 는 ATR(14) 기준 근사다."
            )
        if strategy_id == "vcp_breakout":
            sl = params.get("stop_loss_rate", -7.0)
            mult = params.get("atr_trail_mult", 2.0)
            return (
                f"손절 {sl}%. base_low 이탈 또는 50일 EMA 이탈 시 청산. "
                f"ATR×{mult} 트레일링. 시간 청산 없음(멀티데이). "
                "입력의 stop_loss_pct 는 ATR(14) 기준 근사다."
            )
        if strategy_id == "kojiro":
            hard = params.get("hard_stop_pct", -8.0)
            stop_atr = params.get("stop_atr", 2.0)
            trail_atr = params.get("trail_atr", 2.5)
            return (
                f"고정 {hard}% 백스톱 → 진입가-{stop_atr}×ATR(20) 하드손절(tighten-only) "
                f"→ 스테이지3 진입 → 고점-{trail_atr}×ATR 샹들리에 트레일링. "
                "시간 청산 없음(추세 끝까지 보유). "
                "입력의 stop_loss_pct 는 ATR(14) 기준 근사다(실제 하드손절은 ATR(20))."
            )
    except Exception:
        pass
    return ""


def _mins_from_open(now_kst) -> int:
    try:
        anchor = now_kst.replace(hour=9, minute=0, second=0, microsecond=0)
        return int((now_kst - anchor).total_seconds() // 60)
    except Exception:
        return 0


# cycle297 검증 — 전략별 **돌파선**(모델이 "판단 기준 1 = 돌파의 질" 로 읽는 기준선) 키.
#
# 🔴 `buy_signals` 의 `target_price` 는 전략마다 뜻이 다르다. VB·LTV 의 `target_price` 는
# `보드시가 + K×전일레인지` = **돌파선**이지만, BFB 의 `target_price` 는
# `flag_high + (pole_high - pole_start)` = **측정 이동 목표가**(청산 목표)이고 돌파선은
# 별도 키 `flag_high` 다(`bull_flag_breakout.py` `buy_signals.append`). 그래서 전 전략에
# `target_price` 를 읽으면 BFB 의 `breakout_excess_bp` 가 항상 큰 음수로 나가고, VB 에서
# "+bp = 추격" 이던 잣대가 BFB 에서는 뒤집힌다 — 이 사이클이 없애려던 잣대 오염이다.
#
# donchian(`donchian_high`)·VCP(`base_high`)도 돌파선을 이미 `buy_signals` 에 싣고 있다.
# 전략 파일은 byte 동일로 두고 **읽는 쪽**에서 키를 고른다. 키 부재로 우연히 맞는 폴백
# 순서(`or` 체인)를 쓰지 않는 이유 = 나중에 어느 전략이 같은 이름의 키를 추가하면 조용히
# 뜻이 바뀐다. 전략별 명시 매핑만이 그 경로를 원천 차단한다.
_BREAKOUT_LINE_KEYS: "dict[str, tuple[str, ...]]" = {
    "volatility_breakout": ("target_price",),
    "long_tail_volatility": ("target_price",),
    "bull_flag_breakout": ("flag_high",),
    "donchian_swing": ("donchian_high",),
    "vcp_breakout": ("base_high",),
    # momentum·kojiro 는 돌파선 개념이 없다(`prev_close`/`stage` 뿐) — 빈 튜플 =
    # `target_won` 이 `None` 이고 `_SNAPSHOT_NA_KEYS` 가 그 키를 아예 뺀다.
    "momentum": (),
    "kojiro": (),
}


def _read_breakout_line(strategy_id, sig) -> "int | None":
    """그 전략의 돌파선 값(원). 미등록 전략은 `target_price` 로 폴백한다(신규 전략이
    추가돼도 종전 동작을 유지). never-raise."""
    try:
        keys = _BREAKOUT_LINE_KEYS.get(str(strategy_id), ("target_price",))
        for key in keys:
            got = _opt_int(sig.get(key))
            if got:
                return got
    except Exception:
        return None
    return None


def _excess_bp(price_won, target_won) -> float:
    try:
        p, t = float(price_won), float(target_won)
        if t == 0:
            return 0.0
        return (p / t - 1.0) * 10000.0
    except Exception:
        return 0.0


def _peek_call_count(strategy_id, now_kst) -> int:
    global _call_count_day, _call_count
    try:
        today = now_kst.strftime("%Y%m%d") if hasattr(now_kst, "strftime") else ""
    except Exception:
        today = ""
    if today and _call_count_day != today:
        _call_count_day = today
        _call_count = {}
    return _call_count.get(str(strategy_id), 0)


def _increment_call_count(strategy_id) -> None:
    key = str(strategy_id)
    _call_count[key] = _call_count.get(key, 0) + 1


def _emit_config_canary(strategy_id, mode, min_score, daily_cap, timeout_s, model, now_kst) -> None:
    """§7.1 ③ — 종일 카나리아. 값이 키다(장중 PUT 롤백 확인 채널). never-raise."""
    try:
        key = (str(strategy_id), mode, min_score)
        if not _config_canary_latch.should_emit(key, now=now_kst):
            return
        is_default = (
            mode == _DEFAULT_MODE and min_score == _DEFAULT_MIN_SCORE
            and daily_cap == _DEFAULT_DAILY_CAP and timeout_s == _DEFAULT_TIMEOUT
        )
        src = "default" if is_default else "override"
        logger.info(
            "%s strategy=%s mode=%s min_score=%d daily_cap=%d timeout_s=%d model=%s src=%s",
            MARKER_CONFIG, strategy_id, mode, min_score, daily_cap, timeout_s, model, src,
        )
        _config_canary_latch.mark_emitted(key, now=now_kst)
    except Exception:
        try:
            trace_observer_failure(MARKER_CONFIG, str(strategy_id or "-"), None, now=now_kst)
        except Exception:  # pragma: no cover — 2차 예외도 흡수
            pass


def _get_client():
    """모듈 전역 싱글톤. 키 부재/공백은 None(→ `reason=no_key`)."""
    global _client_singleton
    try:
        key = str(getattr(settings, "openai_api_key", "") or "").strip()
        if not key:
            return None
        if _client_singleton is None:
            from openai import AsyncOpenAI
            _client_singleton = AsyncOpenAI(api_key=key, max_retries=0)
        return _client_singleton
    except Exception:
        return None


def _opt_int(value):
    """`int` 강제 — 실패는 `None`(0 위장 금지)."""
    if value is None:
        return None
    try:
        return int(value)
    except Exception:
        return None


def _opt_float(value):
    if value is None:
        return None
    try:
        return float(value)
    except Exception:
        return None


def _read_scanner_snapshot(ticker):
    """scanner 값 복사(read-only) — `(name, market_cap_eok, trade_amount_eok,
    prdy_close_won, board_open_won)`.

    `scanner` 는 §10 leaf 허용 import 목록 밖이라 **함수 내 지연 import** 다(순환 차단).
    어떤 실패도 값으로 흡수한다 — 관측이 주문 경로를 깨면 안 된다.
    """
    name = ""
    market_cap_eok = None
    trade_amount_eok = None
    prdy_close = 0
    board_open = 0
    try:
        from src.engine.scanner import (
            ticker_market_info,
            ticker_names,
            ticker_prev_close,
            ticker_prices,
        )
        try:
            name = ticker_names.get(ticker, "") or ""
        except Exception:
            name = ""
        try:
            info = ticker_market_info.get(ticker) or {}
            market_cap_eok = info.get("market_cap")
            trade_amount_eok = info.get("trade_amount")
        except Exception:
            pass
        try:
            prdy_close = int(ticker_prev_close.get(ticker, 0) or 0)
        except Exception:
            prdy_close = 0
        try:
            entry = ticker_prices.get(ticker)
            if isinstance(entry, dict):
                board_open = int(entry.get("open_price") or 0)
        except Exception:
            board_open = 0
    except Exception:
        pass
    return name, market_cap_eok, trade_amount_eok, prdy_close, board_open


def _board_by_clock(order_kst) -> str:
    """주문 접수 KST 시각만으로 파생하는 보드.

    세션 트래커의 활성 보드를 쓰지 않는다 — 그 값은 30초 stale 이라 09:00:0x 에
    `pre_nxt` 로 굳고(cycle264 실증), leaf 는 8영역 모듈을 참조하지 않는다(C22).
    경계는 `[시작, 끝)` 반열림이다. 이상 입력은 예외가 아니라 값으로 흡수한다.
    """
    try:
        secs = order_kst.hour * 3600 + order_kst.minute * 60 + order_kst.second
    except Exception:
        return "off_hours"
    if 8 * 3600 <= secs < 9 * 3600:
        return "pre_nxt"
    if 9 * 3600 <= secs < 15 * 3600 + 30 * 60:
        return "main"
    if 15 * 3600 + 30 * 60 <= secs < 20 * 3600:
        return "post_nxt"
    return "off_hours"


def _match_signal(buy_signals_tail, ticker):
    """`state.buy_signals` 꼬리에서 같은 종목의 **최신 1건**을 값 복사로 찾는다.

    없으면 `None` — 호출부는 그때 `signal_matched=False` 로 정직하게 남긴다. 없는
    값을 0 으로 위장하면 회고분석이 "목표가 0원 돌파" 를 실제로 세게 된다(§14-4).
    """
    try:
        rows = list(buy_signals_tail or [])
    except Exception:
        return None
    for row in reversed(rows):
        try:
            if not isinstance(row, dict):
                continue
            if str(row.get("ticker") or "") == str(ticker or ""):
                return dict(row)   # 원본을 나중에 변조해도 payload 가 흔들리지 않게
        except Exception:
            continue
    return None


_JSON_SAFE_MAX_DEPTH = 6


def _json_safe(obj, _depth: int = 0):
    """JSON 직렬화 안전 사영 — datetime→isoformat · Decimal→float · set→list.

    payload 는 `order_kst_dt`(datetime)를 담고 있다. 사영을 빼먹으면 JSONB 바인딩이
    터지고, 그 실패가 **관측을 관측이 막는** 형태가 된다(C35). 재귀 깊이 상한 6.
    """
    if _depth > _JSON_SAFE_MAX_DEPTH:
        try:
            return str(obj)
        except Exception:
            return None
    if obj is None or isinstance(obj, (bool, int, float, str)):
        return obj
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            try:
                out[str(k)] = _json_safe(v, _depth + 1)
            except Exception:
                out[str(k)] = None
        return out
    if isinstance(obj, (list, tuple, set, frozenset)):
        try:
            return [_json_safe(v, _depth + 1) for v in obj]
        except Exception:
            return []
    if isinstance(obj, datetime):
        try:
            return obj.isoformat()
        except Exception:
            return str(obj)
    if isinstance(obj, _Decimal):
        try:
            return float(obj)
        except Exception:
            return str(obj)
    try:
        return str(obj)
    except Exception:
        return None


_prompt_version_cache: "dict[str, str]" = {}
_feature_version_cache: "str | None" = None


def _prompt_version(strategy_id) -> str:
    """SYSTEM 프롬프트 + user 템플릿 + **전략별 user payload 스키마**의 sha256 앞 12자
    (§7-1, C30 → cycle297 §3.4 전략별 확대).

    프롬프트가 바뀐 뒤의 행과 그 전의 행을 **섞어서 회귀하면 안 된다**. 사용자가 원하는
    재귀 개선의 단위가 전략이므로(명세 §3.4) 버전 축도 **전략별**이다 — kojiro 컨텍스트를
    고쳐도 donchian 표본까지 버전이 갈리면 회고가 매주 리셋된다. 전략별로 1회 계산해
    캐시하고, 계산 실패는 `""` (fail-open — 버전 문자열 하나 때문에 평가가 멈추면 관측이
    관측을 막는 셈이다).

    해시 blob 에 `snapshot_keys_for(sid)`(구 `_SNAPSHOT_KEYS` 전체 — 검증 라운드 3 #4)와
    `_STRATEGY_META.get(sid)`(cycle297 신규)를 포함하는 이유 — 모델이 실제로 읽는 것은
    SYSTEM 문장만이 아니라 **user 메시지 payload 의 키 집합·전략 컨텍스트 문구**다. 이를
    빼면 스냅샷 키/META 문구만 바꾼 사이클이 *같은* `prompt_version` 으로 다른 내용의
    행을 만들어, §7-1 이 금지한 "프롬프트 바뀐 전후 행을 섞은 회귀" 가 조용히 가능해진다.
    지표 키 집합은 `_feature_version` 이 따로 잰다(둘은 서로 다른 축이다).
    """
    sid = str(strategy_id)
    if sid in _prompt_version_cache:
        return _prompt_version_cache[sid]
    try:
        from src.engine import llm_features as _lf
        blob = (
            str(_lf.SYSTEM_PROMPT)
            + str(_lf._USER_PREAMBLE)
            + "|".join(_lf.snapshot_keys_for(sid))
            + json.dumps(_lf._STRATEGY_META.get(sid, {}), sort_keys=True, ensure_ascii=False)
        ).encode("utf-8")
        _prompt_version_cache[sid] = hashlib.sha256(blob).hexdigest()[:12]
    except Exception:
        _prompt_version_cache[sid] = ""
    return _prompt_version_cache[sid]


def _feature_version() -> str:
    """`compute_technicals` 출력 **키 집합**의 sha256 앞 12자 (§7-1, C30).

    지표 목록이 바뀌면 그 전후 행의 회귀를 섞으면 안 된다. 값이 아니라 키 집합을
    잰다 — 키가 같으면 같은 특징 공간이다. 계산 실패는 `""` (fail-open).
    """
    global _feature_version_cache
    if _feature_version_cache is not None:
        return _feature_version_cache
    try:
        keys = sorted(compute_technicals([], current_price=0).keys())
        _feature_version_cache = hashlib.sha256("|".join(keys).encode("utf-8")).hexdigest()[:12]
    except Exception:
        _feature_version_cache = ""
    return _feature_version_cache


def _emit_persist(order_no, result: str, reason=None) -> None:
    """`[llm_eval_persist]` — 평가 1건이 DB 행이 됐는지를 남기는 **유일한 채널**(C25).

    `result=ok` = 1행 저장 · `result=error reason=<예외명>` = 저장 실패 ·
    `reason=empty_order_no`(C21) / `reason=cap_exceeded`(검증 라운드 3 #3) = 평가를
    시작하지 않아 담을 outcome 이 없는 주문(둘 다 DB 행 0).

    기록 전용 스위치를 따로 두지 않는 이유이기도 하다: 스위치가 늘면 "설정이 없으면
    관측이 사라지는" P0-1 계열 경로가 하나 더 생긴다. never-raise.
    """
    try:
        ono = str(order_no or "-") or "-"
        if reason:
            logger.info("%s order_no=%s result=%s reason=%s",
                        MARKER_PERSIST, ono, result, reason)
        else:
            logger.info("%s order_no=%s result=%s", MARKER_PERSIST, ono, result)
    except Exception:  # pragma: no cover — 관측 실패는 흡수
        pass


def observe_order(
    *,
    strategy_id, ticker, order_no, order_kst,
    order_price_won, ordered_qty, order_division, order_path, exchange,
    current_price_won,
    budget_total_won, budget_remaining_after_won, open_positions_n,
    params_snapshot, buy_signals_tail,
) -> None:
    """주문 접수 직후 동기 접수 (§6.1). **never-raise · 반환 항상 `None`.**

    비용 순서(C19) = mode 읽기 → `[llm_gate_config]` 카나리아 → `order_no` 유효성 →
    래치 peek → 일일 cap peek → 값 복사 → 래치 mark + cap 증가 → `create_task` → None.

    주문은 이미 KIS 에 접수됐다. 이 호출은 기록만 하며 주문을 막지도, 늦추지도,
    바꾸지도 않는다 — 호출부는 반환값을 쓰지 않는 `ast.Expr` statement 다.
    """
    try:
        params = params_snapshot if isinstance(params_snapshot, dict) else {}
        mode = _read_mode(params)
        min_score = _read_min_score(params)
        daily_cap = _read_daily_cap(params)
        timeout_s = _read_timeout(params)
        model = str(getattr(settings, "openai_buy_gate_model", "") or "")

        # 카나리아는 mode==off 로 낙하하는 return **앞**이다 — 롤백이 먹었는지 확인할
        # 유일한 채널이 여기서 사라지면 안 된다(§7.1 ③). 4키가 없는 5전략에서도
        # `mode=off` 로 1행 발화한다(로그 표면만 넓어지고 행위·비용은 0, C16).
        _emit_config_canary(strategy_id, mode, min_score, daily_cap, timeout_s, model, order_kst)

        if mode != "shadow":
            return None

        ono = str(order_no or "").strip()
        if not ono:
            # 자문 R2 — 무음 금지. "평가 안 함" 과 "주문번호를 못 받았다" 를 구별한다.
            _emit_persist("-", "error", "empty_order_no")
            return None

        if not _latch.should_emit(ono, now=order_kst):
            return None

        if _peek_call_count(strategy_id, order_kst) >= daily_cap:
            # `[llm_gate_daily_cap]` 은 1회/전략/일이라 **어느 주문**이 평가를 못 받았는지
            # 남기지 못한다 — 그러면 나중에 "cap 때문에 평가 안 함" 과 "게이트가 off 였다"
            # 를 주문 단위로 구별할 수 없고, 평가 유무 쪽에 선택 편향이 생긴다(검증 라운드
            # 3 #3). C21 `empty_order_no` 선례대로 persist 채널에 주문번호와 함께 1행.
            # DB 행은 없다(평가를 시작하지 않았으므로 담을 outcome 도 없다).
            _emit_persist(ono, "error", "cap_exceeded")
            if _daily_cap_warned.should_emit(str(strategy_id), now=order_kst):
                logger.warning("%s strategy=%s daily_cap=%d", MARKER_DAILY_CAP, strategy_id, daily_cap)
                _daily_cap_warned.mark_emitted(str(strategy_id), now=order_kst)
            return None

        # --- 값 복사만(전략 객체·_targets·config.params 원본 참조 금지, C23) -------
        tkr = str(ticker)
        name, market_cap_eok, trade_amount_eok, prdy_close_i, board_open_i = (
            _read_scanner_snapshot(tkr)
        )
        board = _board_by_clock(order_kst)
        order_kst_s = order_kst.strftime("%H:%M:%S") if hasattr(order_kst, "strftime") else ""
        order_price_i = int(order_price_won or 0)
        qty_i = _opt_int(ordered_qty)

        # `signal_time_local` — 전략이 `buy_signals` 에 넣은 시각 문자열("HH:MM:SS")
        # **그대로**다. 6전략은 `datetime.now()`(tz 인자 없음), kojiro 만
        # `datetime.now(KST)` 라 값은 EC2 컨테이너의 `TZ=Asia/Seoul` 전제에서만 KST 와
        # 같다 — **KST 를 보장하지 않는다**. 그래서 이름에 `_kst` 를 쓰지 않는다.
        # 이 사이클은 원천(전략 7파일)을 byte 동일로 동결하므로 여기서 정규화하지도
        # 않는다(모르는 tz 를 KST 로 단정하는 것이 더 나쁜 거짓말이다).
        sig = _match_signal(buy_signals_tail, tkr)
        if sig is None:
            # §14-4 — 매칭이 없으면 파생 5필드는 전부 `None` 이다(0 위장 금지).
            signal_matched = False
            signal_price_won = None
            signal_time_local = None
            strategy_board = None
            target_won = None
            k_val = None
            excess_bp = None
        else:
            signal_matched = True
            signal_price_won = _opt_int(sig.get("price"))
            signal_time_local = sig.get("time")
            strategy_board = sig.get("board")
            target_won = _read_breakout_line(strategy_id, sig)
            k_val = _opt_float(sig.get("k"))
            excess_bp = _excess_bp(order_price_i, target_won) if target_won else None

        payload = {
            "strategy_id": str(strategy_id),
            "strategy": str(strategy_id),
            "ticker": tkr,
            "name": name,
            "board": board,
            "order_no": ono,
            "order_kst": order_kst_s,
            "order_kst_dt": order_kst,
            "mins_from_krx_open": _mins_from_open(order_kst),
            "order_price_won": order_price_i,
            "current_price_won": _opt_int(current_price_won),
            "ordered_qty": qty_i,
            "order_notional_won": order_price_i * int(qty_i or 0),
            "order_division": str(order_division or ""),
            "order_path": str(order_path or ""),
            "exchange": exchange,
            "board_open_won": board_open_i,
            "signal_matched": signal_matched,
            "signal_price_won": signal_price_won,
            "signal_time_local": signal_time_local,
            "strategy_board": strategy_board,
            "target_won": target_won,
            "k": k_val,
            "breakout_excess_bp": excess_bp,
            "prdy_close_won": prdy_close_i,
            # §3.3 B군 — 이미 확보한 원시값만으로 순수 계산(llm_features.pct_change).
            # acml_vol_shares 는 tick_volume leaf 관측(없으면 None, 0 위장 금지).
            "prdy_ctrt_pct": pct_change(order_price_i, prdy_close_i),
            "intraday_ctrt_pct": pct_change(order_price_i, board_open_i),
            "acml_vol_shares": _read_acml_vol_shares(tkr),
            "market_cap_eok": market_cap_eok,
            "trade_amount_eok": trade_amount_eok,
            "budget_won": int(budget_total_won or 0),
            "budget_total_won": _opt_int(budget_total_won),
            "budget_remaining_after_won": _opt_int(budget_remaining_after_won),
            "open_positions_n": _opt_int(open_positions_n),
            "position_ratio": _read_position_ratio(params),
            # 관측 시점(ATR 재해석 **전**) 값. `_evaluate_core` 가 일봉에서
            # `atr14_pct` 를 얻은 뒤 `_resolve_stop_loss_pct` 로 덮는다(§3.3).
            "stop_loss_pct": _read_stop_loss_pct(strategy_id, params),
            "exit_rule": _read_exit_rule(strategy_id, params),
            # §3.3 배선용 — 모델에는 실리지 않고(`snapshot_keys_for` 화이트리스트)
            # `input_payload` 에도 남지 않는다(`_PAYLOAD_EXCLUDED_KEYS`).
            "_stop_params": _read_stop_params(params),
            "min_score": min_score,
            "daily_cap": daily_cap,
            "timeout_s": timeout_s,
            "model": model,
            "mode": mode,
            # 계좌는 leaf 가 `settings` 에서 읽는다 — order_engine 은 계좌를 모른다
            # (8영역 import 표면을 넓히지 않는다, C10). `input_payload` 에는 싣지
            # 않는다(C40) — PK 열로 충분하고, 리포터 스코프 키가 GET/HEAD 를 경로
            # 무관 통과시키므로 응답 표면에 원문이 실릴 경로를 원천 차단한다.
            "account_no": str(getattr(settings, "kis_account_no", "") or ""),
            "account_product": str(getattr(settings, "kis_account_product", "") or ""),
            "now_kst": order_kst,
        }

        _latch.mark_emitted(ono, now=order_kst)
        _increment_call_count(strategy_id)

        # `create_task` 가 실패(무루프·monkeypatch 등)하면 이미 만들어진 코루틴
        # 객체를 명시적으로 닫는다 — 닫지 않으면 GC 시점에 "coroutine was never
        # awaited" RuntimeWarning 이 나고, pytest 의 unraisable-exception 훅이
        # 그걸 테스트 실패로 승격시킨다(never-raise 계약과는 별개의 자원 정리).
        coro = _evaluate(payload)
        try:
            task = asyncio.create_task(coro)
        except Exception:
            try:
                coro.close()
            except Exception:
                pass
            raise
        _tasks.add(task)
        task.add_done_callback(_tasks.discard)
        return None
    except Exception:
        try:
            trace_observer_failure("[llm_buy_gate]", str(ticker or "-"), None, now=order_kst)
        except Exception:  # pragma: no cover — 2차 예외도 흡수
            pass
        return None


# ---------------------------------------------------------------------------
# 일봉 캐시
# ---------------------------------------------------------------------------


def _discard_today_bar(rows, today: str) -> list:
    if not today:
        return list(rows or [])
    out = []
    for r in rows or []:
        try:
            if str(r.get("stck_bsop_date")) == today:
                continue
        except Exception:
            pass
        out.append(r)
    return out


async def _bars_cached(ticker: str, *, now_kst) -> list:
    try:
        today = now_kst.strftime("%Y%m%d") if hasattr(now_kst, "strftime") else ""
    except Exception:
        today = ""

    # 계약(§5.3) = "(ticker, KST date) 키 dict, 날짜 바뀌면 **통째 폐기**". 종전
    # 구현은 날짜를 키에만 넣고 옛 날짜 항목을 지우지 않아 다중 날짜가 누적됐다
    # (정확성 영향은 없다 — 옛 날짜 키는 다시 조회되지 않는다 — 그러나 계약과
    # 코드가 어긋나면 다음 사이클이 "폐기된다"는 전제로 얹인다, 검증 파인딩 #8).
    # `today` 가 확보될 때마다 다른 날짜의 잔여 키를 일괄 제거한다.
    if today:
        stale_keys = [k for k in _bars_cache if k[1] != today]
        for k in stale_keys:
            _bars_cache.pop(k, None)

    key = (str(ticker), today)
    if key in _bars_cache:
        return _bars_cache[key]

    rows = await get_recent_daily_normalized(ticker, _BARS_FETCH_DAYS, min_required=_BARS_MIN_REQUIRED)
    filtered = _discard_today_bar(rows, today)

    if key not in _bars_cache and len(_bars_cache) >= _BARS_CACHE_MAX:
        try:
            _bars_cache.pop(next(iter(_bars_cache)))
        except Exception:
            pass
    _bars_cache[key] = filtered
    return filtered


# ---------------------------------------------------------------------------
# 출력 검증 (§6.4) — **클램프 금지**
# ---------------------------------------------------------------------------


def _parse_score_response(content):
    """`(score, rationale, key_risks, invalidations, reason)` — reason=None 이면 유효."""
    if content is None:
        return None, None, None, None, "schema_error"
    if isinstance(content, str) and content.strip() == "":
        return None, None, None, None, "schema_error"
    try:
        obj = json.loads(content)
    except Exception:
        return None, None, None, None, "parse_error"
    if not isinstance(obj, dict):
        return None, None, None, None, "schema_error"
    if "score" not in obj:
        return None, None, None, None, "schema_error"
    raw_score = obj["score"]
    if isinstance(raw_score, bool):
        return None, None, None, None, "schema_error"
    try:
        score_val = int(raw_score)
    except Exception:
        return None, None, None, None, "schema_error"
    if not (1 <= score_val <= 100):
        return None, None, None, None, "schema_error"
    return score_val, obj.get("rationale"), obj.get("key_risks"), obj.get("invalidations"), None


def _is_truncated(finish_reason) -> bool:
    """`finish_reason == "length"`(대소문자·공백 무시) 이면 출력 한도 소진이다.

    OpenAI 는 추론 토큰까지 `max_completion_tokens` 에서 차감하므로 한도가 모자라면
    본문 없이(`content == ""`) `length` 로 끝난다. 예외·미지 값은 **False**(fail-open
    = 종전 어휘 유지) — 판별에 실패했다고 실패 사유를 새로 만들지 않는다.
    """
    try:
        return str(finish_reason or "").strip().lower() == "length"
    except Exception:
        return False


def _clean_line_field(s, limit: int) -> str:
    if not isinstance(s, str):
        return ""
    cleaned = s.replace("\r", "").replace("\n", "").replace("|", "")
    return cleaned[:limit]


def _read_drift(ticker, order_price_won):
    """§7.2(개명) — 판정 도착 순간 `scanner.ticker_prices` 대비 **주문가** 이동폭.

    반환 `(drift_price, drift_bp, tick_age_s)`. read-only 지연 import.

    ⚠️ 부호 **의미**가 cycle274 의 구 필드와 반대다 — 그때는 "신호 뒤 올랐다 = 나쁜
    체결" 이었고 지금은 "주문 뒤 올랐다 = 이득" 이다. 산식은 같지만 두 이름의 값을
    절대 합산하지 말 것(cycle228 `would_pass` · cycle263 `skipped_fresh` 계열 사고).

    `tick_age_s` = 그 현재가 틱의 나이(초). 무송출 종목(nxt_tradable=false, cycle252)은
    고정값이 실려 "표류 0" 으로 오독되므로 판독 시 stale 행을 제외하는 근거로 쓴다.
    """
    try:
        from src.engine.scanner import ticker_last_tick as _last_tick
        from src.engine.scanner import ticker_prices as _ticker_prices
        entry = _ticker_prices.get(ticker)
        if not isinstance(entry, dict):
            return 0, None, None
        price = entry.get("current_price")
        if price is None:
            return 0, None, None
        drift_price = int(price)

        tick_age_s = None
        try:
            last = _last_tick.get(ticker)
            if last is not None:
                tick_age_s = round(
                    (datetime.now(_KST_TZ) - last).total_seconds(), 2
                )
        except Exception:
            tick_age_s = None

        if not order_price_won:
            return drift_price, None, tick_age_s
        return (
            drift_price,
            (drift_price - order_price_won) / order_price_won * 10000.0,
            tick_age_s,
        )
    except Exception:
        return 0, None, None


def _emit_failed(payload: dict, reason: str, t_start: float, *, finish=None) -> None:
    """`finish=` 는 OpenAI `finish_reason` 원문(없으면 `-`).

    `reason=truncated` 를 사후에 판독하려면 "모델이 왜 멈췄나" 가 같은 행에 있어야
    한다 — `length` 면 한도 소진, `stop` 이면 우리 파서 쪽 문제다. LLM 호출 이전에
    끝난 실패(`no_key`·`no_bars`·`payload_error` 등)는 아직 `finish_reason` 이
    존재하지 않으므로 `-` 다(0/`stop` 위장 금지).
    """
    try:
        try:
            latency_ms = int((_monotonic() - t_start) * 1000)
        except Exception:
            latency_ms = 0
        model = str(payload.get("model") or "")
        finish_disp = "-" if finish is None or finish == "" else str(finish)
        logger.info(
            "%s strategy=%s ticker=%s order_no=%s reason=%s finish=%s latency_ms=%d model=%s",
            MARKER_FAILED, payload.get("strategy_id"), payload.get("ticker"),
            payload.get("order_no", "-"), reason, finish_disp, latency_ms, model,
        )
    except Exception:
        try:
            trace_observer_failure(MARKER_FAILED, str(payload.get("ticker") or "-"), None)
        except Exception:  # pragma: no cover — 2차 예외도 흡수
            pass


def _emit_score(payload: dict, tech: dict, outcome: dict) -> None:
    """`[llm_buy_score]` 1행. **서식은 20:10 리포트 정규식 파서의 기준선**이다.

    cycle276 변경 = `order_no=` 추가 · `signal_price=`→`order_price=` ·
    `signal_kst=`→`order_kst=` · 표류 필드 개명(`post_order_drift_bp=`).
    `key_risks`/`invalidations` 는 **로그에 싣지 않는다**(C29) — DB 에만 남긴다.

    `latency_ms`(LLM 호출 구간만)와 `verdict_lag_ms`(접수→판정 전체, 세마포어 대기·
    DB fetch 포함)는 **서로 다른 값이어야 한다**(검증 파인딩 #4).
    """
    try:
        score = int(outcome.get("score") or 0)
        min_score = payload.get("min_score", _DEFAULT_MIN_SCORE)
        order_price = payload.get("order_price_won", 0)
        target = payload.get("target_won") or 0
        would_block = bool(score < min_score)

        drift_bp = outcome.get("post_order_drift_bp")
        drift_disp = "none" if drift_bp is None else f"{drift_bp:.1f}"

        tech = tech if isinstance(tech, dict) else {}
        rsi14 = tech.get("rsi14")
        pos_ch20 = tech.get("pos_in_ch20_pct")
        volr = tech.get("vol_ratio_time_norm")
        rsi_disp = "-" if rsi14 is None else f"{rsi14:.1f}"
        pos_disp = "-" if pos_ch20 is None else f"{pos_ch20:.1f}"
        volr_disp = "-" if volr is None else f"{volr:.2f}"
        # 검증 파인딩 #5 — name 을 원문 그대로 로깅하면 개행이 든 이름 하나가
        # `[llm_buy_score]` 한 행을 둘로 쪼개 위조 로그 행을 만들 수 있다(§7.3 SQL
        # 파서가 이 마커를 정규식으로 긁는다). rationale 과 같은 헬퍼로 통일한다.
        name_disp = _clean_line_field(payload.get("name", ""), 20)

        logger.info(
            "%s strategy=%s ticker=%s order_no=%s name=%s board=%s mode=%s "
            "score=%d min_score=%d would_block=%s "
            "order_price=%d target=%d excess_bp=%.1f k=%.4f "
            "order_kst=%s mins_from_open=%d "
            "drift_price=%d post_order_drift_bp=%s verdict_lag_ms=%d "
            "latency_ms=%d model=%s tokens_in=%d tokens_out=%d cost_usd=%.6f "
            "bars=%d rsi14=%s pos_ch20=%s volr=%s "
            "rationale='%s'",
            MARKER_SCORE, payload.get("strategy_id"), payload.get("ticker"),
            payload.get("order_no", "-"),
            name_disp, payload.get("board"), payload.get("mode"),
            score, int(min_score), would_block,
            int(order_price), int(target),
            float(payload.get("breakout_excess_bp") or 0.0),
            float(payload.get("k") or 0.0),
            payload.get("order_kst", ""), int(payload.get("mins_from_krx_open", 0)),
            int(outcome.get("drift_price_won") or 0), drift_disp,
            int(outcome.get("verdict_lag_ms") or 0),
            int(outcome.get("latency_ms") or 0), payload.get("model", ""),
            int(outcome.get("tokens_in") or 0), int(outcome.get("tokens_out") or 0),
            float(outcome.get("cost_usd") if outcome.get("cost_usd") is not None else -1.0),
            int(outcome.get("bars_count") or 0), rsi_disp, pos_disp, volr_disp,
            # 검증 라운드 2 LOW — 실측 1행 562자 > `_DbLogHandler` 500자 컷. 구조화
            # 필드는 rationale 앞(≈454자)이라 살지만 rationale 이 잘리므로 60 으로 조인다.
            _clean_line_field(outcome.get("rationale"), 60),
        )
    except Exception:
        try:
            trace_observer_failure(MARKER_SCORE, str(payload.get("ticker") or "-"), None)
        except Exception:  # pragma: no cover — 2차 예외도 흡수
            pass


def _verdict_lag_ms(t_start: float) -> int:
    try:
        return int((_monotonic() - t_start) * 1000)
    except Exception:
        return 0


def _eval_to_order_lag_ms(payload: dict, evaluated_at):
    """`evaluated_at - order_kst`(ms). enforce(선평가)로 가면 "얼마나 묵은 점수로
    샀는지" 를 재야 하므로 지금부터 기록한다."""
    try:
        ordered = payload.get("order_kst_dt")
        if not isinstance(ordered, datetime) or not isinstance(evaluated_at, datetime):
            return None
        return int((evaluated_at - ordered).total_seconds() * 1000)
    except Exception:
        return None


def _failed_outcome(payload: dict, reason: str, t_start: float, *,
                    tech=None, bars30=None, raw_content=None,
                    drift=(0, None, None)) -> dict:
    """실패 outcome — 점수는 **`None`** 이다(0 위장 금지: 분포가 0 근처로 왜곡된다)."""
    evaluated_at = datetime.now(_KST_TZ)
    drift_price, drift_bp, tick_age_s = drift
    return {
        "result": "failed",
        "reason": reason,
        "score": None,
        "would_block": None,
        "rationale": None,
        "key_risks": None,
        "invalidations": None,
        "tokens_in": None,
        "tokens_out": None,
        "cost_usd": None,
        "latency_ms": None,
        "verdict_lag_ms": _verdict_lag_ms(t_start),
        "evaluated_at": evaluated_at,
        "eval_to_order_lag_ms": _eval_to_order_lag_ms(payload, evaluated_at),
        "bars_count": len(bars30) if bars30 else 0,
        "tech": tech if isinstance(tech, dict) else {},
        "bars30": list(bars30) if bars30 else [],
        "raw_content": raw_content,
        "post_order_drift_bp": drift_bp,
        "drift_price_won": drift_price,
        "tick_age_s": tick_age_s,
    }


async def _evaluate(payload: dict) -> None:
    """평가 진입점 — `_evaluate_core` 의 outcome 을 받아 **단 1곳**에서 기록한다(C24).

    성공(점수 산출)이든 실패(9종 사유)든 `llm_buy_evaluations` 에 1행이 남는다.
    침묵하면 "평가 안 함" 과 "평가 실패" 가 구별되지 않는다(브리프 §3.4).
    """
    t_start = _monotonic()
    outcome = None
    try:
        outcome = await _evaluate_core(payload, t_start)
    except asyncio.CancelledError:
        raise
    except Exception:
        try:
            trace_observer_failure(
                "[llm_buy_gate_evaluate]", str(payload.get("ticker") or "-"), None,
                now=payload.get("now_kst"),
            )
        except Exception:  # pragma: no cover — 2차 예외도 흡수
            pass
    if outcome is not None:
        await _persist_evaluation(payload, outcome)
    return None


async def _evaluate_core(payload: dict, t_start: float):
    """§5.3 — 세마포어 → 일봉 캐시 → 프롬프트 조립 → LLM 호출(타임아웃) → 검증 → outcome.

    `asyncio.CancelledError` 만 전파한다(cycle272 `open_price_rest` 계약). 그 밖의
    실패는 전부 outcome 으로 내려보내 **기록될 기회**를 잃지 않게 한다.
    """
    ticker = payload.get("ticker")
    now_kst = payload.get("now_kst")
    async with _SEM:
        try:
            bars = await _bars_cached(ticker, now_kst=now_kst)
        except asyncio.CancelledError:
            raise
        except Exception:
            bars = None

        if not bars or len(bars) < _BARS_MIN_REQUIRED:
            _emit_failed(payload, "no_bars", t_start)
            return _failed_outcome(payload, "no_bars", t_start)

        client = _get_client()
        if client is None:
            _emit_failed(payload, "no_key", t_start)
            return _failed_outcome(payload, "no_key", t_start)

        model = str(payload.get("model") or "").strip()
        if not model:
            _emit_failed(payload, "disabled_model", t_start)
            return _failed_outcome(payload, "disabled_model", t_start)

        try:
            tech = compute_technicals(
                bars, current_price=payload.get("order_price_won", 0),
                today_open_won=payload.get("board_open_won", 0),
            )
        except Exception:
            tech = {}

        # §3.3 B군 — vol_ratio_* 는 A군의 `vol_avg20_shares`(일봉에서만 산출)가 나온
        # **뒤**라야 계산할 수 있다. `payload` 는 `observe_order` 가 만든 이 task 전용
        # 값 복사본이라(전역 상태 아님) 여기서 채워 넣어도 read-only 계약과 무관하다.
        try:
            vol_avg20 = tech.get("vol_avg20_shares") if isinstance(tech, dict) else None
            acml = payload.get("acml_vol_shares")
            payload["vol_ratio_vs_avg20"] = safe_ratio(acml, vol_avg20)
            payload["vol_ratio_time_norm"] = normalize_volume_ratio(
                acml, vol_avg20, now_kst=now_kst, board=payload.get("board"),
            )
        except Exception:
            payload["vol_ratio_vs_avg20"] = None
            payload["vol_ratio_time_norm"] = None

        # §3.3 — ATR 손절 전략(donchian/BFB/VCP 터틀 · kojiro)의 `stop_loss_pct` 를
        # **이 시점의 `atr14_pct`** 로 다시 읽는다. 여기가 유일한 배선 지점이다 —
        # `observe_order` 시점에는 일봉이 없어 ATR 을 모른다. 덮는 대상은 task 전용
        # 값 복사본이라 read-only 계약과 무관하다(`vol_ratio_*` 와 같은 자리).
        # 배선이 빠지면 turtle 라이브인 donchian·kojiro 가 실제 손절과 다른 고정값으로
        # 채점되고 SYSTEM_PROMPT 판단 기준 4(손절폭 vs `atr14_pct`)가 틀린 수치로
        # 발동한다 — 이 사이클이 없애려던 「잣대 오류」 그 자체다.
        try:
            payload["stop_loss_pct"] = _resolve_stop_loss_pct(
                payload.get("strategy_id"), payload.get("_stop_params") or {}, tech,
            )
        except Exception:
            pass  # 관측값(`_read_stop_loss_pct`) 그대로 — 0.0 위장 금지

        bars30 = bars[:_PROMPT_BAR_COUNT]
        try:
            messages = build_messages(payload, tech, bars30)
        except Exception:
            # 검증 파인딩 #1/#10 — 프롬프트 조립(json.dumps 포함) 실패는 LLM 출력
            # 검증 실패(schema_error)와 **다른 사유**로 남긴다.
            _emit_failed(payload, "payload_error", t_start)
            return _failed_outcome(payload, "payload_error", t_start, tech=tech, bars30=bars30)

        timeout_s = payload.get("timeout_s", _DEFAULT_TIMEOUT)
        # 검증 파인딩 #4 — `latency_ms`(LLM 호출만)는 세마포어 대기·DB fetch·프롬프트
        # 조립이 끝난 **이 지점**부터 잰다. `t_start`(접수 시각) 재사용 금지.
        t_call = _monotonic()
        try:
            resp = await asyncio.wait_for(
                client.chat.completions.create(
                    model=model,
                    messages=messages,
                    response_format={"type": "json_object"},
                    max_completion_tokens=_MAX_COMPLETION_TOKENS,
                ),
                timeout=timeout_s,
            )
        except asyncio.CancelledError:
            raise
        except asyncio.TimeoutError:
            _emit_failed(payload, "timeout", t_start)
            return _failed_outcome(payload, "timeout", t_start, tech=tech, bars30=bars30)
        except Exception:
            _emit_failed(payload, "api_error", t_start)
            return _failed_outcome(payload, "api_error", t_start, tech=tech, bars30=bars30)
        latency_ms = int((_monotonic() - t_call) * 1000)

        try:
            content = resp.choices[0].message.content
        except Exception:
            content = None
        try:
            finish_reason = resp.choices[0].finish_reason
        except Exception:
            finish_reason = None

        score, rationale, key_risks, invalidations, reason = _parse_score_response(content)
        if reason is not None and _is_truncated(finish_reason):
            # 출력 한도 소진은 **파싱이 실패한 경우에만** 재분류한다. 한도에 닿았어도
            # 완전한 JSON 이 왔다면 그 점수는 유효하므로 실패로 바꾸지 않는다.
            reason = "truncated"
        if reason is not None:
            _emit_failed(payload, reason, t_start, finish=finish_reason)
            return _failed_outcome(
                payload, reason, t_start, tech=tech, bars30=bars30, raw_content=content,
            )

        try:
            usage = getattr(resp, "usage", None)
            tokens_in = int(getattr(usage, "prompt_tokens", 0) or 0) if usage is not None else 0
            tokens_out = int(getattr(usage, "completion_tokens", 0) or 0) if usage is not None else 0
        except Exception:
            tokens_in, tokens_out = 0, 0

        drift_price, drift_bp, tick_age_s = _read_drift(
            ticker, payload.get("order_price_won", 0),
        )
        evaluated_at = datetime.now(_KST_TZ)
        min_score = payload.get("min_score", _DEFAULT_MIN_SCORE)
        outcome = {
            "result": "ok",
            "reason": None,
            "score": int(score),
            "would_block": bool(int(score) < int(min_score)),
            # C29 — cycle274 는 `_risks, _invalids` 로 **버렸다**. 그 둘이 회고분석에서
            # "무엇을 걱정했는데 실제로 무엇이 터졌나" 를 볼 유일한 텍스트다.
            "rationale": rationale,
            "key_risks": key_risks,
            "invalidations": invalidations,
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "cost_usd": _cost_usd(payload.get("model", ""), tokens_in, tokens_out),
            "latency_ms": latency_ms,
            "verdict_lag_ms": _verdict_lag_ms(t_start),
            "evaluated_at": evaluated_at,
            "eval_to_order_lag_ms": _eval_to_order_lag_ms(payload, evaluated_at),
            "bars_count": len(bars),
            "tech": tech,
            "bars30": bars30,
            "raw_content": content,
            "post_order_drift_bp": drift_bp,
            "drift_price_won": drift_price,
            "tick_age_s": tick_age_s,
        }
        _emit_score(payload, tech, outcome)
        return outcome


# `input_payload` 에서 제외하는 키 — 계좌번호는 PK 열로 충분하고, 리포터 스코프 키가
# GET/HEAD 를 경로 무관 통과시키므로 응답 표면에 원문이 실릴 경로를 원천 차단한다(C40).
# `_stop_params`(cycle297 §3.3 배선용 원시 params)도 뺀다 — 재해석 **결과**인
# `stop_loss_pct` 와 `tech.atr14_pct` 가 이미 담겨 검산이 되고, 넣으면 VB·LTV 의
# `input_payload` 키 집합이 배포 전후로 갈려 §7 D+1 대조가 무너진다.
_PAYLOAD_EXCLUDED_KEYS = frozenset({"account_no", "account_product", "_stop_params"})


async def _persist_evaluation(payload: dict, outcome: dict) -> None:
    """평가 1행 upsert — **never-raise**. 결과는 `[llm_eval_persist]` 1행으로 남긴다.

    `src.db.llm_buy_evaluations` 는 §10 leaf 허용 import 목록 밖이라 **함수 내 지연
    import** 다(그 목록 자체를 건드리지 않는다).
    """
    order_no = payload.get("order_no", "")
    try:
        from src.db.llm_buy_evaluations import upsert_evaluation

        safe_payload = _json_safe(
            {k: v for k, v in payload.items() if k not in _PAYLOAD_EXCLUDED_KEYS}
        )
        # C36 — `build_messages` 의 세 인자 그대로(요약·절단 금지). 프롬프트가 아직
        # 조립되지 못한 실패는 확보한 만큼만 담는다. 훗날 다른 모델·다른 프롬프트로
        # 같은 거래를 오프라인 재채점하는 유일한 다리다.
        input_payload = {
            "payload": safe_payload,
            "tech": _json_safe(outcome.get("tech") or {}),
            "bars30": _json_safe(outcome.get("bars30") or []),
        }
        raw_content = outcome.get("raw_content")
        raw_response = {"content": raw_content} if raw_content is not None else None

        order_kst_dt = payload.get("order_kst_dt")
        trade_date = order_kst_dt.date() if isinstance(order_kst_dt, datetime) else None

        await upsert_evaluation(
            trade_date=trade_date,
            account_no=payload.get("account_no", ""),
            ticker=payload.get("ticker", ""),
            order_no=order_no,
            eval_kind="order",
            account_product=payload.get("account_product") or None,
            strategy_id=payload.get("strategy_id", ""),
            mode=payload.get("mode", ""),
            result=outcome.get("result", ""),
            reason=outcome.get("reason"),
            score=outcome.get("score"),
            min_score=int(payload.get("min_score", _DEFAULT_MIN_SCORE)),
            would_block=outcome.get("would_block"),
            rationale=outcome.get("rationale"),
            key_risks=outcome.get("key_risks"),
            invalidations=outcome.get("invalidations"),
            model=payload.get("model") or None,
            tokens_in=outcome.get("tokens_in"),
            tokens_out=outcome.get("tokens_out"),
            cost_usd=outcome.get("cost_usd"),
            latency_ms=outcome.get("latency_ms"),
            verdict_lag_ms=outcome.get("verdict_lag_ms"),
            eval_to_order_lag_ms=outcome.get("eval_to_order_lag_ms"),
            order_kst=order_kst_dt,
            evaluated_at=outcome.get("evaluated_at"),
            order_price_won=int(payload.get("order_price_won") or 0),
            ordered_qty=int(payload.get("ordered_qty") or 0),
            order_notional_won=int(payload.get("order_notional_won") or 0),
            order_division=payload.get("order_division", ""),
            order_path=payload.get("order_path", ""),
            exchange=payload.get("exchange"),
            board=payload.get("board", ""),
            current_price_won=payload.get("current_price_won"),
            signal_matched=bool(payload.get("signal_matched")),
            signal_price_won=payload.get("signal_price_won"),
            signal_time_local=payload.get("signal_time_local"),
            strategy_board=payload.get("strategy_board"),
            target_won=payload.get("target_won"),
            k=payload.get("k"),
            breakout_excess_bp=payload.get("breakout_excess_bp"),
            post_order_drift_bp=outcome.get("post_order_drift_bp"),
            drift_price_won=outcome.get("drift_price_won"),
            tick_age_s=outcome.get("tick_age_s"),
            budget_total_won=payload.get("budget_total_won"),
            budget_remaining_after_won=payload.get("budget_remaining_after_won"),
            open_positions_n=payload.get("open_positions_n"),
            prompt_version=_prompt_version(payload.get("strategy_id", "")),
            feature_version=_feature_version(),
            bars_count=outcome.get("bars_count"),
            input_payload=input_payload,
            raw_response=raw_response,
        )
        _emit_persist(order_no, "ok")
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        _emit_persist(order_no, "error", type(exc).__name__)
    return None
