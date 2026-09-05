"""계좌 통합 리스크 감시자 (cycle233, G3′ 패키지 — SOFT Σ상한 순간 게이트).

자문 정본 = `_workspace/domain_consult/cycle232_risk_control_review.md` §2.5-γ.
배선 = `boot_manager.boot()` 부팅 직후 동기 1회 + `ensure_watch_loop` 가 스폰하는
**자기 종료 루프**(`watch_loop`, 5분 — `_running` False 시 ≤60s 자연 종료라
cancel 목록/task_attrs 불요). scheduler.py 는 무접촉(라인 상한 가드 <4,000L 존중).

계약 (사용자 결정 D1·D2, 2026-08-29):
- **Σ상한 = 순간 게이트** — 평가마다 재계산(양방향). 전략별 일일손실 플래그와
  **이원화**되어 있어 이 모듈은 전략 state 의 어떤 필드도 쓰지 않는다(AST G-4 가
  해당 필드명 토큰 0 을 봉인 — risk.py 가 세운 차단을 지우는 회귀의 구조적 차단).
  소비처는 `StrategyBase._account_soft_gate_blocked`(check_buy_signal 최상단) 뿐
  — **청산·손절 경로는 구조적으로 차단 불가능**하다.
- **fail-open + LOUD**: 평가 실패 시 게이트 False + `[account_risk_watch_failed]`
  WARNING. 조용히 닫히면 "도입 이전 무음과 구별 불가"(D2).
- 다크런치: `system_config.get_account_risk_block_pct()` 기본 None → level 은
  warn 까지만 도달 가능. 활성화 = DB `account_risk_block_pct` 한 줄(권고 6.0).
- 리스크 척도 = **실효 손절선 병기 값**(`portfolio_risk` stop_price_of 주입) —
  프록시 단독으로 임계를 걸면 "잰 적 없는 값에 상한"(자문 §정정 2).

**cycle239 — 게이트 신선도(stale → fail-open, 활성화 선결 시정)**: `is_soft_gated()`
가 종전엔 `_gate_active` 만 돌려줘 감시 루프(`watch_loop`, 5분)가 죽거나 hang 하면
마지막 판정이 그대로 **동결**됐다(block 로 얼면 신규 매수 영구 차단). 시정 =
monotonic 단일 소스 `_evaluated_mono`(성공·실패 공통 스탬프, 판정은 `_now_mono`
seam 경유·ISO 재파싱/벽시계 금지) 를 `_GATE_STALE_MAX_SECS`(=3×주기, 900s) 와
비교해 **초과(stale)·None·판정 예외 전부 fail-open**(False) — 감시 루프 사멸을
"매수 영구 차단"이 아니라 "게이트 해제"로 안전 방향 흡수한다. `get_gate_state()`
는 `stale`/`age_secs`/`stale_max_secs`/`effective_gated` 4키를 더하되 `level` 은
**마지막 평가값 그대로 보존**(사실과 행위를 나란히 — "동결됐다가 fail-open 으로
풀린 상태"의 서명 = `level=block ∧ stale=true ∧ effective_gated=false`) + 무발화
(대시보드 폴링이 cap 을 선소비하면 안 됨). `run_account_risk_watch_once` 는 양
분기(성공/실패)에서 `_gate_active` 대입과 같은 동기 블록에서 `_evaluated_mono`
스탬프(양쪽 사이 await 0 — "새 판정 + 낡은 스탬프" 조합 관측 불가). `ensure_watch_loop`
은 `add_done_callback`(`_on_watch_loop_done`) 으로 루프 사멸/종료를 LOUD 하게
남긴다(0 행위 — "Task exception was never retrieved" 무음만 제거, 재스폰은 후속).
단일 기록자 = `run_account_risk_watch_once`(read 함수는 `global` 금지).
상세 = `_workspace/red/cycle239_gate_freshness_spec.md`.

**cycle239-R1 (적대 검증 확증 시정, 2026-09-02)** — 활성화 선결 착수 직후 반박자
3렌즈+tester 가 독립 수렴: 기록자(`run_account_risk_watch_once`)의 `was_active`
를 최초엔 `is_soft_gated()`(fresh-aware)로 읽었는데, 이러면 **기록자가 소비자용
stale WARNING/cap 을 선소비**한다 — 정상 일일 라이프사이클(20:10 `_running=False`
→ 루프 정상 종료 → 밤새 `_gate_active` 잔존 → 익일 07:55 부팅 동기 평가)에서
**매 아침** `released reason=stale`(사멸 의심 WARNING)이 거짓 발화하고, 그 cap
소비가 그날 장중 진짜 hang 이 나도 소비자 경로의 stale WARNING 을 침묵시켰다
(D2 'fail-open+LOUD' 의 LOUD 절반이 가장 현실적인 순서에서 빠짐). 시정 = 기록자의
`was_active` 를 **원시 `_gate_active`** 로 되돌린다(read-only 계약은 불변 — 기록자
자신의 대입이라 위반 아님) — 기록자는 `is_soft_gated()`/`_emit_stale_release` 를
전혀 호출하지 않으므로 `gate_stale` cap 을 건드리지 않는다. **대가** = 재개 시점의
전이 로그가 항상 raw 값 기준(`entered`/`reconfirm`/`released` 그대로)이라 "stale
로 풀렸다가 재폐쇄"의 세밀한 구분(구 설계의 `entered` 강제)은 사라지지만, 그 사건은
여전히 **소비자 경로**(전략 on_tick·대시보드가 `is_soft_gated()` 를 직접 부를 때)의
stale WARNING 이 1회/일 cap 으로 포착한다 — 탐지 채널이 기록자에서 소비자로 옮겨갔을
뿐 소실은 아니다. `gate_stale` cap 키는 `gate_block`/`watch_failed` 와 절대 공유
금지(회귀 가드 x3).

**cycle250 — 평가 타임아웃(hang 근본, cycle239 후속 A, 2026-09-05)**: cycle239 는
*소비자* 쪽(`is_soft_gated()`)에 신선도 fail-open 을 넣어 "동결된 게이트가 매수를
영구 차단"하는 피해만 막았다. 감시 루프(`watch_loop`) 자체가 `run_account_risk_watch_once`
를 **무기한** await 하는 문제는 그대로였다 — 안의 `balance_mod.get_balance()`(KIS
세마포어)·`system_config.get_*`(asyncpg `pool.acquire()`) 둘 다 시간 상한이 없어
한 번 hang 하면 루프가 영원히 그 자리에 서고, hang 은 예외가 아니라서 `_watch_task`
가 done 이 되지 않아 `[account_risk_watch_loop_died]` 조차 찍히지 않는다(죽은 게
아니라 멈춘 것). 부팅 동기 1회(`boot_manager.py`)도 같은 hang 에 부팅이 막힌다.
시정 = `run_account_risk_watch_once_guarded(scheduler)` — `asyncio.wait_for(
run_account_risk_watch_once(scheduler), timeout=_EVAL_TIMEOUT_SECS)`. **타임아웃 후처리는
wrapper 가 소유한다** — `wait_for` 의 타임아웃은 내부 코루틴을 **취소**로 끝내고,
취소(`CancelledError`, `BaseException` 상속)는 `run_account_risk_watch_once` 의
`except Exception`을 지나가지 않으므로 내부 함수는 자기 취소를 후처리할 수 없다.
그래서 `asyncio.TimeoutError` 핸들러가 **기존 실패 분기와 동일한 후처리**(원시
`was_active` → `_gate_active=False` fail-open → `_evaluated_mono` 스탬프(같은
동기 블록, await 0 = G-239-5 동형) → `_gate_state` level=error/reasons=["timeout"]
→ 활성이었으면 `released reason=eval_timeout` WARNING(cap 밖) →
`[account_risk_eval_timeout]` WARNING 1회/일 cap, 일 카운터는 cap 과 무관하게
증가)를 직접 수행한다. **다른 예외는 잡지 않는다** — `TimeoutError` 만 catch 해야
내부 함수의 기존 실패 분기와 이중 기록이 안 되고, 내부가 못 잡은 진짜 배선 오류가
조용히 삼켜지지 않는다. 호출부 2곳(`watch_loop`/`boot_manager`)만 guarded 로
교체하고 `run_account_risk_watch_once` 본체는 **무변경**(AST 가드가 HEAD 대비
ast.dump 동일을 봉인). 계약 `0 < _EVAL_TIMEOUT_SECS <= _WATCH_INTERVAL_SECS
< _GATE_STALE_MAX_SECS` — 타임아웃 후 다음 평가가 stale 이전에 온다.

로그 (cap 은 날짜 키 자기 리셋 — scheduler 훅 미의존. **전이 로그는 cap 밖**:
희소 사건이고 flapping 자체가 관측해야 할 신호다 — 적대 검증 F5):
- `[account_risk_gate] transition=entered` WARNING = block 진입 전이(cap 밖) /
  `transition=reconfirm` WARNING 1회/일 = 지속 재확인 / `released` INFO = 해제 전이
  (평가 실패로 인한 해제는 `released reason=eval_failure` WARNING, cap 밖 /
  **cycle239** — 소비자 경로(`is_soft_gated()` 직접 호출)가 신선도 초과를
  관측하면 `released reason=stale` WARNING, cap 키 `gate_stale` 1회/일 — F5
  명시 예외: read 경로라 전이 엣지가 없어 cap 이 필요하다. **cycle239-R1** —
  기록자(`run_account_risk_watch_once`)는 이 경로를 타지 않는다(원시
  `_gate_active` 사용, 위 상세 참조) — `gate_stale` 은 소비자 전용 채널).
- `[account_risk_watch] level=warn` WARNING 1회/일 — 관측 경보(기본 4%).
- `[account_risk_watch]` INFO 1회/일 — 요약(pct·coverage·over_cap).
- `[account_risk_watch_failed]` WARNING 1회/일 — 평가 실패(fail-open).
- **cycle239** — `[account_risk_watch_loop_died]` WARNING = 루프 사멸(예외) +
  복구 안내(`/api/trading/restart`) / `[account_risk_watch_loop_exit]` INFO =
  루프 정상 종료(`reason=running_false`, 매일 1건) / 취소(`reason=cancelled`).
- **cycle250** — `[account_risk_eval_timeout] timeout_secs=… count=…` WARNING
  1회/일(cap 키 `eval_timeout`, `gate_stale`/`gate_block`/`watch_failed` 와
  별개) — hang 이 타임아웃으로 끝날 때마다. 일 카운터(`_eval_timeout_count()`)는
  cap 과 무관하게 매 타임아웃마다 증가(폭주해도 "몇 번 멈췄나"는 안 지워진다).
  활성 게이트였으면 `[account_risk_gate] released reason=eval_timeout` WARNING
  (cap 밖, `reason=eval_failure`/`stale` 와 동형).
관측 순서 규약 = **peek → 로그 → mark** (cycle226 D-3 — 관측기 자기실패가
관측 대상을 지우면 안 된다: 로그가 던져도 cap 은 미소비라 다음 평가가 재시도).
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime
from typing import Any, Optional

from src.db._kst import KST
from src.engine.daily_emit_cap import KstDailyEmitCap
from src.engine.observer_trace import trace_observer_failure

# 운영 grep 연속성 — 감시자 로그는 scheduler 네임스페이스로 (stale_manager 선례)
logger = logging.getLogger("src.engine.scheduler")

# ── 모듈 상태 (uvicorn 단일 워커 전제 — refresh_progress 선례) ──────────────
_gate_active: bool = False
_gate_state: dict = {"level": "ok", "reasons": [], "open_risk_pct": None,
                     "evaluated_at": None}
_emit_cap: "KstDailyEmitCap[str]" = KstDailyEmitCap[str]()

# cycle239 — 마지막 평가의 monotonic 스탬프(성공·실패 공통). None = 미평가.
_evaluated_mono: Optional[float] = None


_WATCH_INTERVAL_SECS = 300  # 5분 주기 (collector flush 케이던스 정합)
# cycle239 — 신선도 임계 = 주기의 3배(연속 2회 완전 결측). 리터럴 900 금지
# (AST G-239-1) — 주기 변경 시 조용히 어긋나는 것을 차단한다.
_GATE_STALE_MAX_SECS = _WATCH_INTERVAL_SECS * 3  # = 900
# cycle250 — 평가 타임아웃(초). 계약 = 0 < _EVAL_TIMEOUT_SECS <= _WATCH_INTERVAL_SECS
# < _GATE_STALE_MAX_SECS (타임아웃 후 다음 평가가 stale 이전에 온다). 리터럴은
# 이 한 곳(AST G-250-3b 가 모듈 내 다른 위치의 그림자 리터럴을 봉인).
_EVAL_TIMEOUT_SECS = 300
_watch_task = None  # asyncio.Task — 중복 스폰 방지 참조 (boot 는 매 영업일 재실행)

# cycle250 — 일일 타임아웃 발생 횟수(사실). cap 과 독립 — 로그가 눌려도 셈은 유지.
_eval_timeout_count_today: int = 0
_eval_timeout_count_day: str = ""


async def watch_loop(scheduler: Any) -> None:
    """자기 종료 감시 루프 — `scheduler._running` False 면 스스로 끝난다.

    scheduler.py 라인 상한 가드(재비대 방지 < 4,000L)를 존중해 주기 배선을
    scheduler 밖에 둔다 — cancel 목록·task_attrs 등록 불요(자연 종료 ≤ 60s).
    스폰은 `ensure_watch_loop`(boot_manager) 단일 지점, 중복 스폰 방지 내장.
    """
    while getattr(scheduler, "_running", False):
        await run_account_risk_watch_once_guarded(scheduler)
        for _ in range(_WATCH_INTERVAL_SECS // 60):
            if not getattr(scheduler, "_running", False):
                break
            await asyncio.sleep(60)


def ensure_watch_loop(scheduler: Any) -> None:
    """감시 루프 스폰 (idempotent) — 살아있는 루프가 있으면 no-op.

    boot() 가 매 영업일 07:55 재실행되므로 중복 스폰 가드가 필수다.
    cycle239 — `add_done_callback` 로 루프 사멸/종료를 LOUD 하게 남긴다(0 행위,
    "Task exception was never retrieved" 무음 제거. 재스폰은 후속 등재).
    """
    global _watch_task
    if _watch_task is not None and not _watch_task.done():
        return
    _watch_task = asyncio.create_task(watch_loop(scheduler))
    _watch_task.add_done_callback(_on_watch_loop_done)


def _on_watch_loop_done(task: "asyncio.Task") -> None:
    """cycle239 — 감시 루프 종료 콜백 (0 행위, LOUD 관측 전용).

    예외 사망은 WARNING(+ 복구 안내), 정상 종료(`scheduler._running=False`)는
    매일 1건 발생하는 공짜 liveness 데이터포인트로 INFO, 취소는 프로세스 종료
    시 정상 경로라 INFO. `watch_loop` 본문·재스폰 로직은 무접촉(G-6 구조 보존).
    """
    try:
        if task.cancelled():
            logger.info("[account_risk_watch_loop_exit] reason=cancelled")
            return
        exc = task.exception()
        if exc is not None:
            logger.warning(
                "[account_risk_watch_loop_died] %s: %s — 감시 정지. 게이트는 "
                "≤%ds 후 stale fail-open. 복구 = POST /api/trading/restart",
                type(exc).__name__, str(exc)[:150], _GATE_STALE_MAX_SECS,
            )
        else:
            logger.info("[account_risk_watch_loop_exit] reason=running_false")
    except Exception:
        pass


def _now_mono() -> float:
    """cycle239 — 테스트 seam. `time.monotonic()` 위임(monkeypatch 로 고정 가능).

    freezegun 이 이 프로젝트에서 `time.monotonic` 도 동결하므로(cycle187) 신선도
    판정 시각은 이 seam 으로만 결정적으로 움직인다.
    """
    return time.monotonic()


def _gate_age_secs() -> Optional[float]:
    """cycle239 — 마지막 평가로부터 경과(초). 미평가(`_evaluated_mono is None`)면 None.

    read-only(단일 기록자 계약, AST G-239-4) — `_now_mono` seam 만 경유하고
    ISO 재파싱/벽시계는 쓰지 않는다(hot path 비용 + NTP 점프 취약, AST G-239-3).
    """
    if _evaluated_mono is None:
        return None
    return max(0.0, _now_mono() - _evaluated_mono)


def _is_stale(age: Optional[float]) -> bool:
    """cycle239 — `age > _GATE_STALE_MAX_SECS`(초과) 만 stale. 900.0 정각은 fresh."""
    return age is None or age > _GATE_STALE_MAX_SECS


def _emit_stale_release(age: Optional[float]) -> None:
    """cycle239 — `[account_risk_gate] released reason=stale` WARNING 1회/일.

    cap 키 `gate_stale`(F5 명시 예외 — read 경로는 전이 엣지가 없다). 순서 =
    peek → 로그 → mark(cycle226 D-3 동형) — 로그가 던져도 cap 은 미소비(다음
    호출 재시도) **이고** 이 함수 실패는 `is_soft_gated()` 의 반환값에 영향 0
    (관측 실패 ≠ 행위 변화, 전체 try/except 로 흡수).
    """
    try:
        if not _peek_emit("gate_stale"):
            return
        logger.warning(
            "[account_risk_gate] released reason=stale age_secs=%s max_secs=%d "
            "evaluated_at=%s level=%s — 최근 평가 갱신 없음(임계 초과), "
            "fail-open(신규 매수 게이트만 해제 · 청산·손절 무관). 전일 마감 후 "
            "첫 부팅 직후 1건은 정상 — 장중 지속·반복 시 감시 루프 점검",
            age, _GATE_STALE_MAX_SECS, _gate_state.get("evaluated_at"),
            _gate_state.get("level"),
        )
        _mark_emitted("gate_stale")
    except Exception:
        trace_observer_failure(
            "[account_risk_gate_stale_failed]", "gate_stale", _emit_cap,
        )


def is_soft_gated() -> bool:
    """SOFT Σ상한 순간 게이트 상태 — True 면 신규 매수 신호만 차단.

    cycle239 — 신선도 판정 동반: 마지막 평가(`_evaluated_mono`)가
    `_GATE_STALE_MAX_SECS`(=3×주기, 900s) 를 넘거나(stale) 스탬프가 없거나
    판정 자체가 예외를 내면 **fail-open**(False) — 감시 루프가 죽거나 hang 해도
    마지막 판정이 그대로 동결(영구 매수 차단)되지 않는다. 첫 문장 fast path
    (`_gate_active` False 면 즉시 반환)는 hot path 비용 상한 계약(AST G-239-2)
    — 7전략 per-tick 경로에서 시각 계산이 0회다.
    """
    if not _gate_active:
        return False
    try:
        age = _gate_age_secs()
    except Exception:
        age = None
    if _is_stale(age):
        _emit_stale_release(age)
        return False
    return True


def get_gate_state() -> dict:
    """관측용 상태 사본 (대시보드/진단).

    cycle239 — `stale`/`age_secs`/`stale_max_secs`/`effective_gated` 4키 추가.
    `level` 등 기존 키는 **마지막 평가값 그대로 보존**(재작성 금지) — stale 시
    `level=block ∧ effective_gated=false ∧ stale=true` 가 "동결됐다가 fail-open
    으로 풀린 상태"의 서명이다. **무발화**(대시보드 폴링이 `is_soft_gated()` 의
    cap 을 선소비하면 안 된다 — cycle233 F1 동형).
    """
    snap = dict(_gate_state)
    try:
        age = _gate_age_secs()
    except Exception:
        age = None
    stale = _is_stale(age)
    snap["age_secs"] = None if age is None else int(age)
    snap["stale"] = stale
    snap["stale_max_secs"] = _GATE_STALE_MAX_SECS
    snap["effective_gated"] = bool(_gate_active and not stale)
    return snap


def get_gate_snapshot() -> dict:
    """`get_gate_state()` 8키 + `eval_timeouts_today` — 두 소비자 단일 소유 스냅샷.

    cycle259 리팩토링 카드 ⑥ — 20:10 리포트 빌더(`log_metrics_collector.
    _build_portfolio_risk_snapshot`)와 `routes/portfolio.py::get_portfolio_risk`
    가 각자 `dict(get_gate_state()) + _eval_timeout_count()` 를 조립하던 것을
    단일 소유로 흡수한다. 무발화(read-only) — `get_gate_state()`/
    `_eval_timeout_count()` 에 **위임**한다(로직 복제 금지: 복제하면 이 두 접근자를
    patch 해 graceful 을 검증하는 기존 계약이 무음으로 깨진다). 반환은 항상
    dict 의 **복사본**(watcher 내부 `_gate_state` 를 그대로 노출하지 않는다).
    """
    snap = dict(get_gate_state())
    snap["eval_timeouts_today"] = _eval_timeout_count()
    return snap


def reset_state_for_test() -> None:
    """테스트 전용 — 모듈 상태 초기화."""
    global _gate_active, _gate_state, _emit_cap, _evaluated_mono
    global _eval_timeout_count_today, _eval_timeout_count_day
    _gate_active = False
    _gate_state = {"level": "ok", "reasons": [], "open_risk_pct": None,
                   "evaluated_at": None}
    _emit_cap = KstDailyEmitCap[str]()
    _evaluated_mono = None
    _eval_timeout_count_today = 0
    _eval_timeout_count_day = ""


def _bump_eval_timeout_count() -> int:
    """cycle250 — 오늘 타임아웃 발생 횟수를 1 증가시키고 반환한다.

    cap(`_peek_emit`) 과 독립 — 로그가 눌려도(1회/일) 이 셈은 매 타임아웃마다
    증가한다("몇 번 멈췄나"가 지워지면 안 된다, 명세 5-T2).
    """
    global _eval_timeout_count_today, _eval_timeout_count_day
    today = datetime.now(KST).date().isoformat()
    if _eval_timeout_count_day != today:
        _eval_timeout_count_day = today
        _eval_timeout_count_today = 0
    _eval_timeout_count_today += 1
    return _eval_timeout_count_today


def _eval_timeout_count() -> int:
    """cycle250 — 오늘 타임아웃 발생 횟수 조회(명세 5-T2 접근자, `reset_state_for_test`
    가 0 으로 되돌린다)."""
    return _eval_timeout_count_today


def _peek_emit(key: str) -> bool:
    """1회/(key)/일 cap 의 **판정만** — mark 는 로그 성공 후 `_mark_emitted`.

    mark-before-log 는 로그 자기실패가 그날 관측을 지운다(cycle226 D-3 동형,
    적대 검증 F4). 날짜 키 자기 리셋은 `KstDailyEmitCap`(사이클 258 카드 #4)이
    내부에서 처리한다 — 이 함수는 더 이상 수동 `_emit_day` 비교를 하지 않는다.
    `run_account_risk_watch_once`/`run_account_risk_watch_once_guarded` 의
    호출부(`if _peek_emit(...): logger.warning(...); _mark_emitted(...)`)는
    이 함수의 이름·시그니처가 그대로이므로 사이클258 무접촉이다(G-250-5 sha 핀).

    이 함수 자신의 실패(예: cap 내부 예외)는 흡수하고 흔적을 남긴 뒤 False 를
    반환한다 — "이번 관측은 건너뛴다"이지 호출부(그 함수의 넓은 except)로
    전파해 그 사이클의 평가 전체를 실패로 만들지 않는다.
    """
    try:
        return _emit_cap.should_emit(key)
    except Exception:
        trace_observer_failure("[account_risk_watch_emit_failed]", key, None)
        return False


def _mark_emitted(key: str) -> None:
    try:
        _emit_cap.mark_emitted(key)
    except Exception:
        trace_observer_failure("[account_risk_watch_emit_failed]", key, None)


async def run_account_risk_watch_once(scheduler: Any) -> Optional[dict]:
    """계좌 Σ오픈리스크 1회 평가 → 순간 게이트 갱신 + 관측 로그.

    실패는 **fail-open** — 게이트 False + WARNING 후 None 반환 (매매 지속).

    cycle239 — 양 분기(성공/실패)에서 `_gate_active` 대입과 같은 동기 블록
    (await 0, AST G-239-5)으로 `_evaluated_mono` 스탬프를 남긴다 — "루프 생존
    중 평가 실패"와 "루프 사멸"을 신선도로 구분하기 위해서다. `was_active` 는
    **원시 `_gate_active`**(AST G-239-5b, cycle239-R1) — 기록자가 fresh-aware
    `is_soft_gated()` 를 부르면 소비자용 `gate_stale` WARNING/cap 을 매 아침
    부팅 평가에서 선소비한다(모듈 docstring cycle239-R1 참조). 전이 로그는
    raw 기준 그대로(`entered`/`reconfirm`/`released`), stale 관측은 소비자 전용.
    """
    global _gate_active, _gate_state, _evaluated_mono
    try:
        from src.api import balance as balance_mod
        from src.db import system_config
        from src.engine import portfolio_risk
        from src.engine.account_risk_guard import evaluate_soft_gate

        strategies = list(scheduler.registry.all())

        _holdings, summary = await balance_mod.get_balance()
        net_asset = int(getattr(summary, "net_asset", 0) or 0)

        hard_stop_pcts: dict[str, float] = {}
        strat_by_id: dict[str, Any] = {}
        for s in strategies:
            sid = getattr(s, "strategy_id", None) or "unknown"
            strat_by_id[sid] = s
            params = getattr(getattr(s, "config", None), "params", None)
            hard_stop_pcts[sid] = portfolio_risk.extract_hard_stop_pct(params)

        def _stop_of(sid: str, ticker: str) -> Optional[int]:
            strat = strat_by_id.get(sid)
            fn = getattr(strat, "get_effective_stop_price", None)
            if not callable(fn):
                return None
            try:
                return fn(ticker)
            except Exception:
                return None

        snapshot = portfolio_risk.compute_portfolio_risk_snapshot(
            strategies,
            net_asset=net_asset,
            hard_stop_pcts=hard_stop_pcts,
            sector_of={},
            stop_price_of=_stop_of,
        )
        effective = snapshot.get("effective") or {}
        eff_pct = effective.get("open_risk_effective_pct_of_net")
        coverage = effective.get("coverage") or {}

        over_cap = portfolio_risk.compute_over_cap_positions(strategies)

        warn_pct = await system_config.get_account_risk_warn_pct()
        block_pct = await system_config.get_account_risk_block_pct()
        verdict = evaluate_soft_gate(eff_pct, warn_pct=warn_pct, block_pct=block_pct)
        level = verdict["level"]

        was_active = _gate_active  # cycle239-R1 — 원시값(기록자는 stale 관측을 선소비 안 함)
        _gate_active = level == "block"
        _evaluated_mono = _now_mono()  # cycle239 — 성공 스탬프(대입과 같은 동기 블록)
        _gate_state = {
            "level": level,
            "reasons": list(verdict.get("reasons") or []),
            "open_risk_pct": eff_pct,
            "open_risk_proxy_pct": snapshot.get("open_risk_pct_of_net"),
            "net_asset": net_asset,
            "coverage": coverage,
            "over_cap_count": len(over_cap),
            "warn_pct": warn_pct,
            "block_pct": block_pct,
            "evaluated_at": datetime.now(KST).isoformat(),
        }

        if _gate_active:
            if not was_active:
                # 전이는 cap 밖 — 희소 사건이고 flapping 자체가 관측 신호(F5)
                logger.warning(
                    "[account_risk_gate] level=block transition=entered eff_pct=%s "
                    "block_pct=%s reasons=%s — 신규 매수 신호만 차단(청산·손절 무관)",
                    eff_pct, block_pct, verdict.get("reasons"),
                )
            elif _peek_emit("gate_block"):
                logger.warning(
                    "[account_risk_gate] level=block transition=reconfirm eff_pct=%s "
                    "block_pct=%s — 지속 중 (1회/일 재확인)",
                    eff_pct, block_pct,
                )
                _mark_emitted("gate_block")
        elif was_active:
            logger.info(
                "[account_risk_gate] released — eff_pct=%s < block_pct=%s",
                eff_pct, block_pct,
            )
        elif level == "warn":
            if _peek_emit("watch_warn"):
                logger.warning(
                    "[account_risk_watch] level=warn eff_pct=%s warn_pct=%s "
                    "proxy_pct=%s — 설계 천장(스윙 3.55%%) 밖 사건 관측",
                    eff_pct, warn_pct, snapshot.get("open_risk_pct_of_net"),
                )
                _mark_emitted("watch_warn")
        else:
            if _peek_emit("watch_summary"):
                logger.info(
                    "[account_risk_watch] level=ok eff_pct=%s proxy_pct=%s "
                    "coverage=%s/%s over_cap=%d net=%d",
                    eff_pct, snapshot.get("open_risk_pct_of_net"),
                    coverage.get("effective_positions"),
                    coverage.get("total_positions"),
                    len(over_cap), net_asset,
                )
                _mark_emitted("watch_summary")
        return _gate_state
    except Exception as exc:
        was_active = _gate_active  # cycle239-R1 — 원시값(성공 분기와 동일 규약)
        _gate_active = False  # fail-open — 판정 실패가 매수를 막지 않는다
        _evaluated_mono = _now_mono()  # cycle239 — 실패도 '살아 있음'(연속 실패≠stale)
        _gate_state = {"level": "error", "reasons": [str(exc)[:150]],
                       "open_risk_pct": None,
                       "evaluated_at": datetime.now(KST).isoformat()}
        try:
            if was_active:
                # 실패로 인한 해제 전이도 명시 (F5 — 무음 해제 금지, cap 밖)
                logger.warning(
                    "[account_risk_gate] released reason=eval_failure — "
                    "평가 실패로 fail-open 해제. %s", type(exc).__name__,
                )
            if _peek_emit("watch_failed"):
                logger.warning(
                    "[account_risk_watch_failed] 평가 실패 — fail-open(게이트 해제 상태 유지). "
                    "%s: %s", type(exc).__name__, str(exc)[:150],
                )
                _mark_emitted("watch_failed")
        except Exception:
            pass
        return None


async def run_account_risk_watch_once_guarded(scheduler: Any) -> Optional[dict]:
    """cycle250 — hang 방어 wrapper. `run_account_risk_watch_once` 를
    `_EVAL_TIMEOUT_SECS` 로 감싸 타임아웃 시 기존 실패 분기와 동일한 후처리를
    수행한다. 상세 근거(왜 wrapper 가 후처리를 소유하는지)는 모듈 docstring
    cycle250 절 참조 — 여기서는 재서술하지 않는다(AST G-250-5 가 `run_account_risk_watch_once`
    본체를 HEAD 대비 봉인하므로 이 함수의 docstring 은 자유롭다).

    `TimeoutError` 만 잡는다 — 다른 예외는 내부 함수의 기존 `except Exception`
    이 이미 fail-open + 관측을 마쳤으므로 여기서 다시 잡으면 이중 기록이 된다.
    """
    global _gate_active, _gate_state, _evaluated_mono
    try:
        return await asyncio.wait_for(
            run_account_risk_watch_once(scheduler), timeout=_EVAL_TIMEOUT_SECS,
        )
    except asyncio.TimeoutError:
        was_active = _gate_active  # cycle250 — 원시값(cycle239-R1 동형 규약)
        _gate_active = False  # fail-open — hang 이 매수를 영구 차단하면 안 된다
        _evaluated_mono = _now_mono()  # 타임아웃도 '살아 있음'(루프 생존 중 타임아웃)
        _gate_state = {
            "level": "error",
            "reasons": ["timeout"],
            "open_risk_pct": None,
            "evaluated_at": datetime.now(KST).isoformat(),
        }
        try:
            if was_active:
                # 무음 해제 금지(F5 동형) — cap 밖, `reason=eval_failure`/`stale` 와 동형
                logger.warning(
                    "[account_risk_gate] released reason=eval_timeout — "
                    "평가 타임아웃(%ss)으로 fail-open 해제",
                    _EVAL_TIMEOUT_SECS,
                )
            count = _bump_eval_timeout_count()
            if _peek_emit("eval_timeout"):
                logger.warning(
                    "[account_risk_eval_timeout] timeout_secs=%s count=%d — "
                    "계좌 리스크 평가 타임아웃(hang 의심). 게이트 fail-open 유지, "
                    "감시 루프는 다음 주기부터 계속. 지속 시 KIS/DB 응답 지연 점검",
                    _EVAL_TIMEOUT_SECS, count,
                )
                _mark_emitted("eval_timeout")
        except Exception:
            pass
        return None
