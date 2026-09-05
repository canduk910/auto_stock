"""cycle258 tester 시정 — `account_risk_watcher` 관측기 사이트 가드 (C258-T1 · C258-T2).

근거: cycle258 적대 검증 뮤테이션 escape 2건(`mutate.py` M22/M23 — 표적 98 PASS).

## 왜 escape 였나 (M23)

M23 은 모듈 전역 `_emit_cap` 초기화를 날짜 무리셋 `DailyEmitCap` 으로 되돌렸는데,
cycle239/250/233/251 의 autouse 픽스처가 매 테스트 `reset_state_for_test()` 를 불러
`_emit_cap = KstDailyEmitCap[str]()` 로 **덮어쓴다** — 즉 프로덕션이 실제로 쓰는
모듈 초기값은 어떤 런타임 테스트도 관측하지 못한다(cycle239 F-4(a) 롤오버 테스트가
있는데도 escape 한 이유). 그래서 런타임 롤오버(T1-a)에 **소스 AST 가드**(T1-b — 모듈
전역 초기화 + `reset_state_for_test` 양쪽이 `KstDailyEmitCap` 생성자)를 동반한다
(G-245-9 재조준 방식 동형).

## 봉인하는 것

- T1-a `_gate_active=True ∧ _evaluated_mono=None`(스탬프 부재 = stale) 로
       `is_soft_gated()` — D1 2회(WARNING 1) → **KST** D2 07:56(= UTC D1 22:56) 1회
       → WARNING 2. UTC 날짜 판정이면 D2 07:56 KST 는 아직 전날이라 재발화 없음.
- T1-b 소스: `_emit_cap` 의 모듈 전역 초기화와 `reset_state_for_test` 안 재대입이
       둘 다 `KstDailyEmitCap` 생성자(M23 직접 검출).
- T2-a `src.engine.scheduler` 로거 `warning` 사망 시 stale `is_soft_gated()` =
       **False 불변** ∧ `[account_risk_gate_stale_failed]` exc_info debug ≥1 ∧ 같은
       마커 `observer_failed` WARNING 1(=`system_logs` 도달 채널) ∧ 정상 키
       `gate_stale` **미소비**(로그 실패 = 다음 호출 재시도, cycle226 D-3).
- T2-b 두 로거(`scheduler` + `observer_trace`) 전부 사망해도 False 반환 + 무전파.
"""

from __future__ import annotations

import ast
import logging
from pathlib import Path

import pytest
from freezegun import freeze_time

from src.engine import account_risk_watcher as watcher
from src.engine import observer_trace as ot_mod
from src.engine.daily_emit_cap import KstDailyEmitCap

pytestmark = pytest.mark.unit

_LOGGER = "src.engine.scheduler"
_SRC = Path(__file__).resolve().parents[3] / "src" / "engine" / "account_risk_watcher.py"
_STALE_FAILED = "[account_risk_gate_stale_failed]"


@pytest.fixture(autouse=True)
def _reset_watcher_state():
    watcher.reset_state_for_test()
    watcher._watch_task = None
    yield
    watcher.reset_state_for_test()
    watcher._watch_task = None


def _arm_stale_gate() -> None:
    """`_gate_active=True ∧ _evaluated_mono=None` — 스탬프 부재 = stale(fail-open) 경로.

    `_now_mono` 는 호출되지 않는다(`_gate_age_secs` 가 None 스탬프에서 먼저 반환)
    — freezegun 의 monotonic 동결과 무관하게 결정적이다.
    """
    watcher._gate_active = True
    watcher._evaluated_mono = None


def _stale_records(caplog):
    return [r for r in caplog.records
            if "[account_risk_gate]" in r.getMessage() and "reason=stale" in r.getMessage()]


# ===========================================================================
# T1-a — KST 롤오버 재발화 (런타임)
# ===========================================================================
def test_t1a_gate_stale_warning_refires_after_kst_rollover(caplog):
    _arm_stale_gate()
    caplog.clear()
    with caplog.at_level(logging.INFO, logger=_LOGGER):
        with freeze_time("2026-09-05 10:00:00+09:00"):
            assert watcher.is_soft_gated() is False
            assert watcher.is_soft_gated() is False          # 같은 날 = cap
        assert len(_stale_records(caplog)) == 1, "D1 2회 호출은 WARNING 1행이어야 한다"
        # KST 익일 07:56 = UTC 로는 아직 D1 22:56 — UTC 날짜 판정이면 재발화가 없다.
        with freeze_time("2026-09-06 07:56:00+09:00"):
            assert watcher.is_soft_gated() is False
    assert len(_stale_records(caplog)) == 2, (
        "KST 날짜가 바뀌었는데 `released reason=stale` 가 재발화하지 않았다 — "
        "`_emit_cap` 이 날짜 무리셋 cap 이면 프로세스 수명당 1회로 퇴화한다(M23)"
    )
    assert isinstance(watcher._emit_cap, KstDailyEmitCap), (
        f"`_emit_cap` 타입 {type(watcher._emit_cap).__name__} — KST 자기 리셋 cap 이어야 한다"
    )


# ===========================================================================
# T1-b — 소스 AST: 모듈 전역 초기화 + reset_state_for_test 양쪽 KstDailyEmitCap
# ===========================================================================
def _ctor_name(value) -> str | None:
    """`KstDailyEmitCap[str]()` / `KstDailyEmitCap()` / `x.DailyEmitCap[str]()` 의 생성자 이름."""
    if not isinstance(value, ast.Call):
        return None
    f = value.func
    if isinstance(f, ast.Subscript):
        f = f.value
    return getattr(f, "id", None) or getattr(f, "attr", None)


def _assign_targets(node) -> list[str]:
    if isinstance(node, ast.AnnAssign):
        return [node.target.id] if isinstance(node.target, ast.Name) else []
    if isinstance(node, ast.Assign):
        return [t.id for t in node.targets if isinstance(t, ast.Name)]
    return []


def test_t1b_emit_cap_initializer_is_kst_daily_emit_cap_in_source():
    tree = ast.parse(_SRC.read_text(encoding="utf-8"))

    module_inits = [
        _ctor_name(n.value) for n in tree.body
        if isinstance(n, (ast.Assign, ast.AnnAssign)) and "_emit_cap" in _assign_targets(n)
    ]
    assert module_inits == ["KstDailyEmitCap"], (
        f"모듈 전역 `_emit_cap` 초기화 생성자 = {module_inits} — 프로덕션은 "
        "`reset_state_for_test` 를 부르지 않으므로 이 한 줄이 실제 cap 이다. "
        "`DailyEmitCap` 이면 `gate_stale`/`eval_timeout` WARNING 이 프로세스 수명당 1회로 퇴화(M23)"
    )

    reset_fn = next(
        (n for n in tree.body
         if isinstance(n, ast.FunctionDef) and n.name == "reset_state_for_test"),
        None,
    )
    assert reset_fn is not None, "`reset_state_for_test` 부재"
    reset_inits = [
        _ctor_name(n.value) for n in ast.walk(reset_fn)
        if isinstance(n, (ast.Assign, ast.AnnAssign)) and "_emit_cap" in _assign_targets(n)
    ]
    assert reset_inits == ["KstDailyEmitCap"], (
        f"`reset_state_for_test` 의 `_emit_cap` 재대입 생성자 = {reset_inits} — "
        "픽스처가 프로덕션과 다른 cap 타입을 심으면 런타임 테스트 전체가 허상을 잰다"
    )


# ===========================================================================
# T2-a — `_emit_stale_release` 로거 사망: 행위 불변 + 흔적 + 정상 키 미소비
# ===========================================================================
def test_t2a_stale_release_logger_death_leaves_trace_and_keeps_behavior(monkeypatch, caplog):
    _arm_stale_gate()

    def _boom(*a, **k):
        raise RuntimeError("scheduler logger warning down (인위)")

    monkeypatch.setattr(watcher.logger, "warning", _boom)

    caplog.clear()
    with caplog.at_level(logging.DEBUG):
        with freeze_time("2026-09-05 10:00:00+09:00"):
            result = watcher.is_soft_gated()

    # (a) 행위 불변 — 관측 실패 ≠ 게이트 판정 변화
    assert result is False, "로거 사망이 fail-open 판정을 바꿨다"
    # 탐지기 self-test — 정상 WARNING 은 로거 사망으로 나오지 않았어야 한다
    assert not _stale_records(caplog), "로거 사망 전제가 성립하지 않았다(정상 WARNING 발화)"

    # (b) 흔적 — exc_info 실린 debug ≥1 + DB 도달용 WARNING 1
    dbg = [r for r in caplog.records
           if r.levelno == logging.DEBUG and r.exc_info and _STALE_FAILED in r.getMessage()]
    assert dbg, (
        f"`{_STALE_FAILED}` exc_info debug 흔적이 없다 — 무흔적 `pass`(M22)면 "
        "stale 관측기가 항구적으로 깨져도 아무도 모른다"
    )
    warns = [r for r in caplog.records
             if r.levelno == logging.WARNING and _STALE_FAILED in r.getMessage()
             and "observer_failed" in r.getMessage()]
    assert len(warns) == 1, (
        f"`{_STALE_FAILED} observer_failed` WARNING {len(warns)}행 — 1행이어야 "
        "`_DbLogHandler`(INFO 컷)를 넘어 `system_logs` 에 도달한다(C237-L2-1)"
    )

    # (c) 정상 키 미소비 — 로그가 던지면 mark 미도달(peek→로그→mark, cycle226 D-3)
    assert watcher._emit_cap.should_emit("gate_stale") is True, (
        "로그 실패에도 `gate_stale` 가 소비됐다 — 로거 복구 후 그날 stale WARNING 이 영영 안 나온다"
    )


# ===========================================================================
# T2-b — 두 로거 전부 사망: False + 무전파
# ===========================================================================
def test_t2b_both_loggers_dead_still_false_and_never_raises(monkeypatch):
    _arm_stale_gate()

    def _boom(*a, **k):
        raise RuntimeError("logger down (인위)")

    monkeypatch.setattr(watcher.logger, "warning", _boom)
    monkeypatch.setattr(ot_mod.logger, "debug", _boom)
    monkeypatch.setattr(ot_mod.logger, "warning", _boom)

    with freeze_time("2026-09-05 10:00:00+09:00"):
        try:
            result = watcher.is_soft_gated()
        except Exception as exc:  # noqa: BLE001
            pytest.fail(f"관측기 2차 예외가 `is_soft_gated` 밖으로 샜다: {exc!r}")
    assert result is False
    assert watcher._emit_cap.should_emit("gate_stale") is True
