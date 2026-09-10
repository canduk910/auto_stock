"""cycle274 — VB·LTV 매수 신호 LLM 평가 게이트(shadow) leaf. **행위 변경 0.**

정본 = `_workspace/domain_consult/cycle274_llm_buy_gate_20260910.md`
(§5.2 `observe_signal` · §5.3 `_evaluate` · §5.4 자원 상한 · §6.2 키 · §6.4 출력 검증 ·
§7.1 마커 4종 · §7.2 `slip_bp`)

`check_buy_signal` 의 `return Signal.BUY` 직전에서 신호 1건을 동기로 접수해
`asyncio.create_task` 로 던지고 즉시 리턴한다. LLM 점수는 **기록만** 한다 — 이
사이클에 `enforce` 는 구현되지 않았고, `shadow` 외 모든 값은 `off` 로 낙하한다.

## leaf 계약
- `observe_signal` — 동기·never-raise·`await`/DB/HTTP 0·반환 항상 `None`.
- `_evaluate` — async 본체. 세마포어 2 → 일봉 캐시(60봉 fetch, 오늘봉 폐기, 30봉만
  프롬프트에 싣는다) → LLM 호출(`asyncio.wait_for` 타임아웃) → 출력 검증(클램프 금지).
- `src.*` import 는 §10 허용 목록(`daily_emit_cap`·`observer_trace`·`llm_features`·
  `config`·`db.stock_master_daily`)으로 한정 — **모듈 최상단**에서만. `scanner`·
  `tick_volume`·`log_analysis_engine` 은 전부 함수 내 **지연 import**(순환 차단 ·
  §10 허용 목록 밖이라 최상단에 나타나면 안 된다).
- 실패는 전부 `[llm_buy_score_failed] reason=` 9종 어휘 중 하나로 남긴다:
  timeout / api_error / parse_error / schema_error / no_bars / no_key /
  cap_exceeded / disabled_model / payload_error(검증 라운드2 파인딩 #10 —
  자문 §6.1/§7.1 의 8종 밖 확장, `spec_disagreements` 등재).
"""

from __future__ import annotations

import asyncio
import json
import logging
import time as _wall_clock

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

# 실패 사유 전체 어휘(자문 §7.1 ②) — `[llm_buy_score_failed] reason=` 이 쓰는
# 8종 + 검증 라운드2 파인딩 #10 이 추가한 `payload_error`. `cap_exceeded` 는
# **이 사이클의 실제 차단 경로가 아니다** — 일일 cap 도달은 `[llm_gate_daily_cap]`
# WARNING 으로 별도 표시한다(§7.1 ④, C7 계약). 이 값은 향후 "호출까지는 갔는데
# 그 뒤 다른 동시성 상한에 막힌" 사유가 생길 때를 위해 어휘를 미리 예약해 둔다 —
# 20:10 리포트의 실패 분포 파서가 그 값을 몰라서 "미지 사유"로 뭉뚱그리지 않도록.
#
# `payload_error` — **자문 §6.1/§7.1 이 정의한 8종 밖의 확장**(spec_disagreements
# 등재). 프롬프트 조립 실패(`build_messages`, `json.dumps` 포함)를 LLM 출력
# 검증 실패(`schema_error` — "모델이 스키마를 벗어났다")와 같은 어휘로 뭉개면
# "우리 코드가 페이로드를 못 만든다"와 "모델이 이상한 걸 준다"를 20:10 리포트가
# 구별할 수 없다(검증 파인딩 #10). `_evaluate` 는 `build_messages` 실패를
# **이 값으로만** 분류한다 — LLM 응답 파싱/검증 실패는 여전히 `schema_error`다.
_FAILURE_REASONS = (
    "timeout", "api_error", "parse_error", "schema_error",
    "no_bars", "no_key", "cap_exceeded", "disabled_model",
    "payload_error",
)

_DEFAULT_MODE = "shadow"
_DEFAULT_MIN_SCORE = 70
_DEFAULT_DAILY_CAP = 20
_DEFAULT_TIMEOUT = 20

_BARS_CACHE_MAX = 400
_BARS_FETCH_DAYS = 60
_BARS_MIN_REQUIRED = 30
_PROMPT_BAR_COUNT = 30
_MAX_COMPLETION_TOKENS = 400

# 세마포어 2 — 09:01:30 해제 순간 다수 종목이 동시 돌파할 수 있다(실측 09-08
# 09:01:34/09:01:42 8초 간격 2건). 2면 8초 안에 4건을 소화한다(자문 §5.4).
_SEM = asyncio.Semaphore(2)

# 진행 중 task 강참조 — asyncio 는 참조가 사라지면 GC 한다.
_tasks: set = set()

# 래치 = KstDailyEmitCap[(strategy_id, ticker)] **별도 인스턴스**(cycle236 '별개
# cap' 계약 — emit cap 과 슬롯을 다투지 않는다).
_latch: "KstDailyEmitCap[tuple[str, str]]" = KstDailyEmitCap()

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
    """래치·cap·일봉 캐시 일괄 초기화(테스트·운영 훅 — cycle264/268 선례)."""
    global _latch, _daily_cap_warned, _config_canary_latch, _bars_cache
    global _call_count_day, _call_count, _tasks
    _latch = KstDailyEmitCap()
    _daily_cap_warned = KstDailyEmitCap()
    _config_canary_latch = KstDailyEmitCap()
    _bars_cache = {}
    _call_count_day = ""
    _call_count = {}
    _tasks = set()


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
    try:
        if strategy_id == "volatility_breakout":
            return float(params.get("stop_loss_rate", -3.0) or 0)
        if strategy_id == "long_tail_volatility":
            return float(params.get("intraday_stop_loss", -3.0) or 0)
    except Exception:
        pass
    return 0.0


def _read_exit_rule(strategy_id, params) -> str:
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
    except Exception:
        pass
    return ""


def _mins_from_open(now_kst) -> int:
    try:
        anchor = now_kst.replace(hour=9, minute=0, second=0, microsecond=0)
        return int((now_kst - anchor).total_seconds() // 60)
    except Exception:
        return 0


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


def observe_signal(
    *,
    strategy_id, ticker, name, board, price_won, board_open_won,
    target_won, target_offset_won, k, prev_price_won, prdy_close_won,
    market_cap_eok, trade_amount_eok, budget_won, params_snapshot, now_kst,
) -> None:
    """동기 접수 — 비용 순서(자문 §5.2): mode → 래치 peek → cap peek → 값 복사 →
    래치 mark + cap 증가 → `create_task` → return None. **never-raise.**
    """
    try:
        params = params_snapshot if isinstance(params_snapshot, dict) else {}
        mode = _read_mode(params)
        min_score = _read_min_score(params)
        daily_cap = _read_daily_cap(params)
        timeout_s = _read_timeout(params)
        model = str(getattr(settings, "openai_buy_gate_model", "") or "")

        # 카나리아는 mode==off 로 낙하하는 return **앞**이다 — 롤백이 먹었는지
        # 확인할 유일한 채널이 여기서 사라지면 안 된다(§7.1 ③).
        _emit_config_canary(strategy_id, mode, min_score, daily_cap, timeout_s, model, now_kst)

        if mode != "shadow":
            return None

        latch_key = (str(strategy_id), str(ticker))
        if not _latch.should_emit(latch_key, now=now_kst):
            return None

        if _peek_call_count(strategy_id, now_kst) >= daily_cap:
            if _daily_cap_warned.should_emit(str(strategy_id), now=now_kst):
                logger.warning("%s strategy=%s daily_cap=%d", MARKER_DAILY_CAP, strategy_id, daily_cap)
                _daily_cap_warned.mark_emitted(str(strategy_id), now=now_kst)
            return None

        # --- 값 복사만(전략 객체·_targets·config.params 참조 금지, C17) --------
        signal_kst = now_kst.strftime("%H:%M:%S") if hasattr(now_kst, "strftime") else ""
        price_i = int(price_won or 0)
        board_open_i = int(board_open_won or 0)
        prdy_close_i = int(prdy_close_won or 0)
        payload = {
            "strategy_id": str(strategy_id),
            "strategy": str(strategy_id),
            "ticker": str(ticker),
            "name": name,
            "board": str(board),
            "signal_kst": signal_kst,
            "mins_from_krx_open": _mins_from_open(now_kst),
            "price_won": price_i,
            "board_open_won": board_open_i,
            "target_won": int(target_won or 0),
            "target_offset_won": int(target_offset_won or 0),
            "k": float(k or 0),
            "breakout_excess_bp": _excess_bp(price_won, target_won),
            "prev_price_won": int(prev_price_won or 0),
            "prdy_close_won": prdy_close_i,
            # §3.3 B군 — 검증 파인딩 #2 시정. prdy_ctrt_pct/intraday_ctrt_pct 는
            # 이미 확보한 원시값만으로 순수 계산(llm_features.pct_change).
            # acml_vol_shares 는 tick_volume leaf 관측(없으면 None, 0 위장 금지).
            "prdy_ctrt_pct": pct_change(price_i, prdy_close_i),
            "intraday_ctrt_pct": pct_change(price_i, board_open_i),
            "acml_vol_shares": _read_acml_vol_shares(ticker),
            "market_cap_eok": market_cap_eok,
            "trade_amount_eok": trade_amount_eok,
            "budget_won": int(budget_won or 0),
            "position_ratio": _read_position_ratio(params),
            "stop_loss_pct": _read_stop_loss_pct(strategy_id, params),
            "exit_rule": _read_exit_rule(strategy_id, params),
            "min_score": min_score,
            "daily_cap": daily_cap,
            "timeout_s": timeout_s,
            "model": model,
            "mode": mode,
            "now_kst": now_kst,
        }

        _latch.mark_emitted(latch_key, now=now_kst)
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
            trace_observer_failure("[llm_buy_gate]", str(ticker or "-"), None, now=now_kst)
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


def _clean_line_field(s, limit: int) -> str:
    if not isinstance(s, str):
        return ""
    cleaned = s.replace("\r", "").replace("\n", "").replace("|", "")
    return cleaned[:limit]


def _read_slip_bp(ticker, signal_price):
    """§7.2 — 판정 도착 순간 `scanner.ticker_prices` 대비 신호가 이동폭(bp). read-only."""
    try:
        from src.engine.scanner import ticker_prices as _ticker_prices
        entry = _ticker_prices.get(ticker)
        if not isinstance(entry, dict):
            return 0, None
        price = entry.get("current_price")
        if price is None:
            return 0, None
        verdict_price = int(price)
        if not signal_price:
            return verdict_price, None
        return verdict_price, (verdict_price - signal_price) / signal_price * 10000.0
    except Exception:
        return 0, None


def _emit_failed(payload: dict, reason: str, t_start: float) -> None:
    try:
        try:
            latency_ms = int((_monotonic() - t_start) * 1000)
        except Exception:
            latency_ms = 0
        model = str(payload.get("model") or "")
        logger.info(
            "%s strategy=%s ticker=%s reason=%s latency_ms=%d model=%s",
            MARKER_FAILED, payload.get("strategy_id"), payload.get("ticker"),
            reason, latency_ms, model,
        )
    except Exception:
        try:
            trace_observer_failure(MARKER_FAILED, str(payload.get("ticker") or "-"), None)
        except Exception:  # pragma: no cover — 2차 예외도 흡수
            pass


def _emit_score(payload: dict, tech: dict, score: int, rationale, tokens_in: int,
                 tokens_out: int, t_start: float, latency_ms: int, bars_count: int) -> None:
    """`latency_ms`(LLM 호출 구간만, 호출자가 `_monotonic()` 두 지점으로 잰다)와
    `verdict_lag_ms`(신호 접수→판정 도착 전체, 세마포어 대기·DB fetch 포함 —
    `t_start` 기준 여기서 다시 잰다)는 **서로 다른 값이어야 한다**(검증 파인딩
    #4 — 종전 구현은 `t_start` 를 두 번 읽어 로그의 두 필드가 항상 동일했다)."""
    try:
        min_score = payload.get("min_score", _DEFAULT_MIN_SCORE)
        signal_price = payload.get("price_won", 0)
        target = payload.get("target_won", 0)
        would_block = bool(score < min_score)

        verdict_price, slip_bp = _read_slip_bp(payload.get("ticker"), signal_price)
        try:
            verdict_lag_ms = int((_monotonic() - t_start) * 1000)
        except Exception:
            verdict_lag_ms = 0

        cost_usd = _cost_usd(payload.get("model", ""), tokens_in, tokens_out)

        tech = tech if isinstance(tech, dict) else {}
        rsi14 = tech.get("rsi14")
        pos_ch20 = tech.get("pos_in_ch20_pct")
        volr = tech.get("vol_ratio_time_norm")

        slip_disp = "none" if slip_bp is None else f"{slip_bp:.1f}"
        rsi_disp = "-" if rsi14 is None else f"{rsi14:.1f}"
        pos_disp = "-" if pos_ch20 is None else f"{pos_ch20:.1f}"
        volr_disp = "-" if volr is None else f"{volr:.2f}"
        # 검증 파인딩 #5 — rationale 은 이미 `_clean_line_field` 로 정제되는데
        # name 만 원문 그대로 로깅됐다. 개행이 든 이름 하나가 `[llm_buy_score]`
        # 한 행을 둘로 쪼개 위조 로그 행을 만들 수 있다(§7.3 SQL 파서가 이
        # 마커를 정규식으로 긁는다). 같은 헬퍼로 통일한다.
        name_disp = _clean_line_field(payload.get("name", ""), 20)

        logger.info(
            "%s strategy=%s ticker=%s name=%s board=%s mode=%s "
            "score=%d min_score=%d would_block=%s "
            "signal_price=%d target=%d excess_bp=%.1f k=%.4f "
            "signal_kst=%s mins_from_open=%d "
            "verdict_price=%d slip_bp=%s verdict_lag_ms=%d "
            "latency_ms=%d model=%s tokens_in=%d tokens_out=%d cost_usd=%.6f "
            "bars=%d rsi14=%s pos_ch20=%s volr=%s "
            "rationale='%s'",
            MARKER_SCORE, payload.get("strategy_id"), payload.get("ticker"),
            name_disp, payload.get("board"), payload.get("mode"),
            int(score), int(min_score), would_block,
            int(signal_price), int(target), float(payload.get("breakout_excess_bp", 0.0)),
            float(payload.get("k", 0.0)),
            payload.get("signal_kst", ""), int(payload.get("mins_from_krx_open", 0)),
            verdict_price, slip_disp, verdict_lag_ms,
            int(latency_ms), payload.get("model", ""), int(tokens_in), int(tokens_out), cost_usd,
            int(bars_count), rsi_disp, pos_disp, volr_disp,
            # 검증 라운드 2 LOW — 실측 1행 562자 > `_DbLogHandler` 500자 컷. 구조화 필드는
            # rationale 앞(≈454자)이라 살지만 rationale 이 잘리므로 120→60 으로 조인다.
            _clean_line_field(rationale, 60),
        )
    except Exception:
        try:
            trace_observer_failure(MARKER_SCORE, str(payload.get("ticker") or "-"), None)
        except Exception:  # pragma: no cover — 2차 예외도 흡수
            pass


async def _evaluate(payload: dict) -> None:
    """§5.3 — 세마포어 → 일봉 캐시 → 프롬프트 조립 → LLM 호출(타임아웃) → 검증 → 관측."""
    ticker = payload.get("ticker")
    now_kst = payload.get("now_kst")
    t_start = _monotonic()
    try:
        async with _SEM:
            try:
                bars = await _bars_cached(ticker, now_kst=now_kst)
            except asyncio.CancelledError:
                raise
            except Exception:
                bars = None

            if not bars or len(bars) < _BARS_MIN_REQUIRED:
                _emit_failed(payload, "no_bars", t_start)
                return None

            client = _get_client()
            if client is None:
                _emit_failed(payload, "no_key", t_start)
                return None

            model = str(payload.get("model") or "").strip()
            if not model:
                _emit_failed(payload, "disabled_model", t_start)
                return None

            try:
                tech = compute_technicals(
                    bars, current_price=payload.get("price_won", 0),
                    today_open_won=payload.get("board_open_won", 0),
                )
            except Exception:
                tech = {}

            # §3.3 B군 — vol_ratio_vs_avg20/vol_ratio_time_norm 은 A군의
            # `vol_avg20_shares`(일봉에서만 산출)가 나온 **뒤**라야 계산할 수
            # 있다. `payload` 는 `observe_signal` 이 만든 이 task 전용 값 복사본
            # 이라(전역 상태 아님) 여기서 채워 넣어도 C17 read-only 계약과
            # 무관하다(검증 파인딩 #2).
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

            try:
                messages = build_messages(payload, tech, bars[:_PROMPT_BAR_COUNT])
            except Exception:
                # 검증 파인딩 #1/#10 — 프롬프트 조립(json.dumps 포함) 실패는
                # LLM 출력 검증 실패(schema_error)와 **다른 사유**로 남긴다.
                _emit_failed(payload, "payload_error", t_start)
                return None

            timeout_s = payload.get("timeout_s", _DEFAULT_TIMEOUT)
            # 검증 파인딩 #4 — `latency_ms`(LLM 호출만)는 세마포어 대기·DB
            # fetch·프롬프트 조립이 끝난 **이 지점**부터 잰다. `t_start`(신호
            # 접수 시각) 재사용 금지 — 그러면 두 필드가 항상 같은 값이 된다.
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
                return None
            except Exception:
                _emit_failed(payload, "api_error", t_start)
                return None
            latency_ms = int((_monotonic() - t_call) * 1000)

            try:
                content = resp.choices[0].message.content
            except Exception:
                content = None

            score, rationale, _risks, _invalids, reason = _parse_score_response(content)
            if reason is not None:
                _emit_failed(payload, reason, t_start)
                return None

            try:
                usage = getattr(resp, "usage", None)
                tokens_in = int(getattr(usage, "prompt_tokens", 0) or 0) if usage is not None else 0
                tokens_out = int(getattr(usage, "completion_tokens", 0) or 0) if usage is not None else 0
            except Exception:
                tokens_in, tokens_out = 0, 0

            _emit_score(payload, tech, score, rationale, tokens_in, tokens_out, t_start, latency_ms, len(bars))
            return None
    except asyncio.CancelledError:
        raise
    except Exception:
        try:
            trace_observer_failure("[llm_buy_gate_evaluate]", str(ticker or "-"), None, now=now_kst)
        except Exception:  # pragma: no cover — 2차 예외도 흡수
            pass
        return None
