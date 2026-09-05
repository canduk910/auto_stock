"""cycle258 Red — `observer_trace.trace_observer_failure` (리팩토링 카드 #5).

명세: 스크래치패드 `spec_cycle258_emit_cap_observer_trace.md` §1 (신규 leaf)
근거: `_workspace/refactor/2026-09-05_review.md` 카드 #5 (형태 4종 / 16 사이트 실측)

## 고칠 것 (한 문장)

관측기 **자기 실패**의 처리 정책이 4가지로 갈라져 있다 —
A. 무흔적 `pass`(`strategy_base.py` 11 + `account_risk_watcher` 2) ·
B. `logger.debug` 단독(`stale_watcher_core` · `api_auth`) ·
C. debug 스택 + WARNING 1회/일(`donchian_swing._trace_observer_failure`) ·
D. wrapper 안 `pass`. cycle237 적대 검증 C237-L2-1 이 "debug 단독은 `_DbLogHandler`
INFO 컷에 걸려 **DB 에 도달하지 못하고 도입 이전 무음과 구별 불가**" 라고 확정했는데
그 결론이 C 한 파일에만 반영됐다. C 를 모듈 함수로 승격해 정책을 하나로 만든다.

## 이 파일이 봉인하는 것

- T-1 `logger.debug(..., exc_info=True)` **항상** (cap 유무 무관).
- T-2 cap 이 있으면 WARNING **1회/(key)/일** — 두 번째 호출은 debug 만.
- T-3 `cap=None` 경로 — WARNING 0, debug 1, never-raise.
- T-4 **2차 예외 흡수** — 이미 `except` 안에서 불리므로 여기서 던지면 관측이
      매매 경로를 죽인다(donchian J-3 "가장 안쪽은 어떤 경우에도 조용히 통과").
- T-5 key 분리 + KST 날짜 롤오버 재발화.
- T-6 WARNING 문자열에 marker · `observer_failed` · `key=` 가 있다(운영 grep 축).
- T-7 실패 흔적 키가 **정상 관측 키를 삼키지 않는다**(donchian J-3 계약 승계).
- T-8 leaf 계약 — `src.engine.daily_emit_cap` 외 `src.*` import 0, `write_log` 0.
- T-9 동명 이함수 충돌 해소 — `api_auth` 판은 `_trace_auth_observer_failure`
      로 개명되고 engine 모듈을 import 하지 않는다(인증 경로 격리).
- T-10 (tester 시정 C258-T4) 실패 흔적 cap 키는 **(marker, key)** — 같은 cap 을
      공유하며 같은 key 를 쓰는 두 관측기(strategy_base `_lot_cap_logged` 의
      config/clamped 는 둘 다 key=strategy_id)가 같은 날 각각 죽으면 **둘 다** WARNING.

## Red 판정 기준

`src/engine/observer_trace.py` 미구현 상태에서 T-1~T-8 FAIL, T-9 FAIL(개명 전).
"""

from __future__ import annotations

import ast
import importlib
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from src.engine import daily_emit_cap as dec_mod

pytestmark = pytest.mark.unit

_KST = timezone(timedelta(hours=9))
_ROOT = Path(__file__).resolve().parents[3]
_TRACE_SRC = _ROOT / "src" / "engine" / "observer_trace.py"
_API_AUTH_SRC = _ROOT / "src" / "middleware" / "api_auth.py"

MARKER = "[lot_cap_emit_failed]"


# ---------------------------------------------------------------------------
# 헬퍼 (로컬 — 타 테스트 모듈 import 금지)
# ---------------------------------------------------------------------------
def _mod():
    """`src.engine.observer_trace` 해석. 미구현이면 그 자리에서 RED."""
    try:
        return importlib.import_module("src.engine.observer_trace")
    except ImportError as exc:
        pytest.fail(
            f"`src/engine/observer_trace.py` 미구현 — 카드 #5 의 관측기 자기실패 "
            f"정책 단일화 지점이 없습니다 ({exc})"
        )


def _trace():
    fn = getattr(_mod(), "trace_observer_failure", None)
    if fn is None:
        pytest.fail("`trace_observer_failure` 가 `observer_trace` 에 없습니다")
    return fn


def _cap():
    cls = getattr(dec_mod, "KstDailyEmitCap", None)
    if cls is None:
        pytest.fail("`KstDailyEmitCap` 미구현 — 카드 #4 선행")
    return cls()


def _dt(y: int, m: int, d: int) -> datetime:
    return datetime(y, m, d, 10, 0, tzinfo=_KST)


def _call(fn, *a, **kw):
    """실제 사용처와 동형 — 살아있는 예외 컨텍스트 안에서 호출한다."""
    try:
        raise RuntimeError("관측기 내부 인위 예외")
    except RuntimeError:
        return fn(*a, **kw)


def _debugs(caplog):
    return [r for r in caplog.records if r.levelno == logging.DEBUG]


def _warns(caplog):
    return [r for r in caplog.records if r.levelno == logging.WARNING]


# ===========================================================================
# T-1 — debug 스택은 항상
# ===========================================================================
def test_t1_debug_stack_is_always_emitted(caplog):
    fn = _trace()
    caplog.clear()
    with caplog.at_level(logging.DEBUG):
        _call(fn, MARKER, "005930")
    dbg = _debugs(caplog)
    assert dbg, "debug 흔적이 없습니다 — 스택트레이스는 항상 남는 것이 계약"
    assert any(r.exc_info for r in dbg), (
        "`exc_info=True` 가 빠졌습니다 — 스택 없는 한 줄은 원인 규명에 무용"
    )
    assert any(MARKER in r.getMessage() for r in dbg), (
        f"debug 행에 마커 {MARKER} 가 없습니다 — 어떤 관측기가 죽었는지 못 찾습니다"
    )


def test_t1b_debug_emitted_with_cap_too(caplog):
    """cap 이 있어도 debug 는 매번 — WARNING 만 cap 대상이다."""
    fn, cap = _trace(), _cap()
    caplog.clear()
    with caplog.at_level(logging.DEBUG):
        _call(fn, MARKER, "005930", cap, now=_dt(2026, 9, 5))
        _call(fn, MARKER, "005930", cap, now=_dt(2026, 9, 5))
    assert len(_debugs(caplog)) == 2, (
        "debug 가 cap 에 걸렸습니다 — 스택은 매 실패마다 남아야 원인 분포를 봅니다"
    )


# ===========================================================================
# T-2 — WARNING 1회/(key)/일
# ===========================================================================
def test_t2_warning_is_capped_once_per_key_per_day(caplog):
    fn, cap = _trace(), _cap()
    d = _dt(2026, 9, 5)
    caplog.clear()
    with caplog.at_level(logging.DEBUG):
        for _ in range(5):
            _call(fn, MARKER, "005930", cap, now=d)
    assert len(_warns(caplog)) == 1, (
        f"WARNING {len(_warns(caplog))}행 — 1회/(key)/일 cap 이 안 걸렸습니다 "
        "(관측기 자기실패가 종목 수만큼 곱해집니다)"
    )


def test_t2b_warning_reaches_db_level_not_debug(caplog):
    """레벨이 WARNING 이어야 `_DbLogHandler`(INFO 이상)를 통과해 `system_logs` 에 닿는다."""
    fn, cap = _trace(), _cap()
    caplog.clear()
    with caplog.at_level(logging.DEBUG):
        _call(fn, MARKER, "005930", cap, now=_dt(2026, 9, 5))
    assert _warns(caplog), (
        "요약 1행이 WARNING 이 아닙니다 — debug 단독은 `src/main.py::_DbLogHandler` "
        "의 INFO 컷에 막혀 DB 기반 도구(20:10 리포트·대시보드)에서 무음과 동일합니다"
    )


# ===========================================================================
# T-3 — cap=None 경로
# ===========================================================================
def test_t3_cap_none_emits_debug_only(caplog):
    fn = _trace()
    caplog.clear()
    with caplog.at_level(logging.DEBUG):
        _call(fn, MARKER, "005930")
        _call(fn, MARKER, "005930", None)
    assert len(_debugs(caplog)) == 2
    assert _warns(caplog) == [], (
        "cap 없이 WARNING 을 냈습니다 — cap 없는 호출부는 폭주 차단 수단이 없습니다"
    )


# ===========================================================================
# T-4 — 2차 예외 흡수 (never-raise)
# ===========================================================================
@pytest.mark.parametrize("dead", ["debug", "warning", "both"])
def test_t4_secondary_failure_never_propagates(monkeypatch, dead):
    """이 함수는 **이미 `except` 안**에서 불린다 — 여기서 던지면 매매 경로가 죽는다."""
    mod, fn, cap = _mod(), _trace(), _cap()

    def _boom(*a, **k):
        raise RuntimeError(f"{dead} logger down")

    if dead in ("debug", "both"):
        monkeypatch.setattr(mod.logger, "debug", _boom)
    if dead in ("warning", "both"):
        monkeypatch.setattr(mod.logger, "warning", _boom)

    try:
        _call(fn, MARKER, "005930", cap, now=_dt(2026, 9, 5))
    except Exception as exc:  # noqa: BLE001
        pytest.fail(
            f"2차 예외가 전파됐습니다({dead}): {exc!r} — 가장 안쪽은 어떤 경우에도 "
            "조용히 통과한다(donchian J-3)"
        )


def test_t4b_broken_cap_object_never_propagates():
    """cap 이 깨진 객체여도(should_emit 가 폭발) 호출부로 안 샌다."""
    fn = _trace()

    class _BrokenCap:
        def should_emit(self, key, **kw):
            raise RuntimeError("cap down")

        def mark_emitted(self, key):
            raise RuntimeError("cap down")

    try:
        _call(fn, MARKER, "005930", _BrokenCap())
    except Exception as exc:  # noqa: BLE001
        pytest.fail(f"cap 자기실패가 전파됐습니다: {exc!r}")


# ===========================================================================
# T-5 — key 분리 + KST 날짜 롤오버
# ===========================================================================
def test_t5_keys_are_independent_and_roll_over(caplog):
    fn, cap = _trace(), _cap()
    d1, d2 = _dt(2026, 9, 5), _dt(2026, 9, 6)
    caplog.clear()
    with caplog.at_level(logging.DEBUG):
        _call(fn, MARKER, "005930", cap, now=d1)
        _call(fn, MARKER, "000660", cap, now=d1)
        _call(fn, MARKER, "005930", cap, now=d1)   # cap
        _call(fn, MARKER, "005930", cap, now=d2)   # 익일 재발화
    msgs = [r.getMessage() for r in _warns(caplog)]
    assert len(msgs) == 3, (
        f"key 분리/날짜 롤오버가 어긋났습니다 — WARNING {len(msgs)}행: {msgs}"
    )


# ===========================================================================
# T-6 — WARNING 문자열 (운영 grep 축)
# ===========================================================================
def test_t6_warning_contains_marker_and_key(caplog):
    fn, cap = _trace(), _cap()
    caplog.clear()
    with caplog.at_level(logging.DEBUG):
        _call(fn, MARKER, "005930", cap, now=_dt(2026, 9, 5))
    msg = _warns(caplog)[0].getMessage()
    assert MARKER in msg, f"마커 부재: {msg!r}"
    assert "observer_failed" in msg, (
        f"`observer_failed` 토큰 부재 — 전 마커 공통 grep 축이 없어집니다: {msg!r}"
    )
    assert "key=005930" in msg, f"`key=` 필드 부재: {msg!r}"


# ===========================================================================
# T-7 — 실패 흔적 키가 정상 관측 키를 삼키지 않는다 (donchian J-3 승계)
# ===========================================================================
def test_t7_failure_key_does_not_swallow_normal_key(caplog):
    """실패 1건이 그날의 정상 관측을 통째로 침묵시키면 안 된다."""
    fn, cap = _trace(), _cap()
    d = _dt(2026, 9, 5)
    caplog.clear()
    with caplog.at_level(logging.DEBUG):
        _call(fn, MARKER, "005930", cap, now=d)
    assert cap.should_emit("005930", now=d) is True, (
        "흔적이 정상 관측 키(`005930`)를 소비했습니다 — 같은 cap 을 쓰되 키는 "
        "분리하는 것이 계약(donchian `ticker|__observer_failed__` 선례)"
    )


# ===========================================================================
# T-8 — leaf 계약 (import 범위 · write_log 0)
# ===========================================================================
def test_t8_is_a_leaf_module():
    assert _TRACE_SRC.exists(), "`src/engine/observer_trace.py` 가 없습니다"
    tree = ast.parse(_TRACE_SRC.read_text(encoding="utf-8"))
    src_imports: set[str] = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.ImportFrom) and (n.module or "").startswith("src."):
            src_imports.add(n.module)
        elif isinstance(n, ast.Import):
            for a in n.names:
                if a.name.startswith("src."):
                    src_imports.add(a.name)
    assert src_imports <= {"src.engine.daily_emit_cap"}, (
        f"leaf 계약 위반 — 허용 밖 `src.*` import: {sorted(src_imports)}. "
        "이 모듈은 hot path(strategy_base 관문)에서 불리므로 순환/무거운 의존 금지"
    )
    offenders = [
        n.lineno for n in ast.walk(tree)
        if isinstance(n, ast.Call)
        and (getattr(n.func, "id", None) == "write_log"
             or getattr(n.func, "attr", None) == "write_log")
    ]
    assert not offenders, (
        f"`write_log` 유입(라인 {offenders}) — A-PURE 위반 + system_logs 이중 INSERT"
    )


# ===========================================================================
# T-9 — 동명 이함수 충돌 해소 (`api_auth` 는 engine 을 import 하지 않는다)
# ===========================================================================
def test_t9_api_auth_helper_is_renamed_and_stays_isolated():
    src = _API_AUTH_SRC.read_text(encoding="utf-8")
    tree = ast.parse(src)
    names = {
        n.name for n in ast.walk(tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert "_trace_auth_observer_failure" in names, (
        "`api_auth._trace_observer_failure` 가 개명되지 않았습니다 — donchian "
        "메서드(4인자)와 **다른 계약**의 동명 함수가 남습니다"
    )
    assert "_trace_observer_failure" not in names, (
        "구 이름이 남아 있습니다 — 개명은 치환이지 추가가 아닙니다"
    )
    engine_imports = {
        n.module for n in ast.walk(tree)
        if isinstance(n, ast.ImportFrom) and (n.module or "").startswith("src.engine")
    }
    assert not engine_imports, (
        f"인증 미들웨어가 engine 을 import 합니다: {sorted(engine_imports)} — "
        "`api_auth` 는 `src.db`/`src.engine` 무의존 leaf 라는 cycle243 계약 위반"
    )


# ===========================================================================
# T-10 — (C258-T4) 같은 cap · 같은 key 의 두 관측기 실패는 각각 WARNING
# ===========================================================================
def test_t10_distinct_markers_sharing_cap_and_key_both_warn(caplog):
    """cap 키가 key 단독이면 두 번째 관측기의 사망은 debug 만 남고 WARNING 이 침묵한다
    — 20:10 리포트(WARNING↑ 집계)에서 그날 보이지 않는다."""
    fn, cap = _trace(), _cap()
    d = _dt(2026, 9, 5)
    caplog.clear()
    with caplog.at_level(logging.DEBUG):
        _call(fn, "[fallback_cap_config]", "kojiro", cap, now=d)
        _call(fn, "[fallback_cap_clamped]", "kojiro", cap, now=d)   # 같은 key, 다른 marker
        _call(fn, "[fallback_cap_config]", "kojiro", cap, now=d)    # 같은 (marker, key) = cap
    msgs = [r.getMessage() for r in _warns(caplog)]
    assert len(msgs) == 2, (
        f"WARNING {len(msgs)}행 — (marker, key) 별 1회여야 한다(key 단독 cap 이면 1행): {msgs}"
    )
    assert any("[fallback_cap_config]" in m for m in msgs)
    assert any("[fallback_cap_clamped]" in m for m in msgs)
    assert cap.should_emit("kojiro", now=d) is True, "정상 관측 키(`kojiro`)를 소비했다"
