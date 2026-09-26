"""cycle364 S1 Red — LOCK AST: 라이브 prepare 는 wrapper 한 곳에서만 부른다 + leaf 경계.

설계 정본 = `_workspace/domain_consult/cycle364_a1_as_of_design.md` §4.4 · §6.2 LOCK.

- 호출부 전수(현재 5곳) → 전부 `funnel_capture.live_prepare_one/_many` 경유:
  `boot_manager.py`(부팅) · `scheduler.py` 07:59 사전 구독 직전 VB/LTV·스윙 재준비 2곳 ·
  `_reprepare_breakout_if_empty` · 저녁(→ leaf 로 이동).
- 가드: `src/engine/**/*.py` 에서 `strategies/**` 와 wrapper 파일(`funnel_capture.py`)을 뺀
  곳의 `X.prepare(` 직접 호출 0 · `getattr(X, "prepare"…)` 0 (현행 저녁 본체가 getattr 로 부른다).
- leaf `funnel_capture.py`: 8영역(risk·order_engine·session·scanner·strategy_registry·
  api.order·realtime·auth) import 0 · naive 벽시계(`datetime.now()` 인자 없음·`date.today()`) 0.

스캔 = `Path.rglob("*.py")` + AST(호출·정의만 — 주석·docstring 제외). `git grep`/`git ls-files`
금지(미추적 새 파일을 로컬에서 못 본다 — 가드 설계 금기).
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parents[3]
_ENGINE = _ROOT / "src" / "engine"
_LEAF = _ENGINE / "funnel_capture.py"
_WRAPPERS = {"live_prepare_one", "live_prepare_many"}
_EIGHT_AREA_MODULES = (
    "src.engine.risk", "src.engine.order_engine", "src.engine.session", "src.engine.scanner",
    "src.engine.strategy_registry", "src.api.order", "src.realtime", "src.auth",
)


def _direct_prepare_calls(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    hits = []
    for n in ast.walk(tree):
        if not isinstance(n, ast.Call):
            continue
        f = n.func
        if isinstance(f, ast.Attribute) and f.attr == "prepare":
            hits.append(f"{path.relative_to(_ROOT)}:{n.lineno} .prepare(")
        if (
            isinstance(f, ast.Name) and f.id == "getattr" and len(n.args) >= 2
            and isinstance(n.args[1], ast.Constant) and n.args[1].value == "prepare"
        ):
            hits.append(f"{path.relative_to(_ROOT)}:{n.lineno} getattr(…, 'prepare')")
    return hits


def _wrapper_calls(path: Path) -> int:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    count = 0
    for n in ast.walk(tree):
        if isinstance(n, ast.Call):
            f = n.func
            name = f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else None
            if name in _WRAPPERS:
                count += 1
    return count


def test_lock_1_engine_when_scanned_then_no_direct_prepare_call_outside_strategies_and_wrapper():
    hits: list[str] = []
    for py in sorted(_ENGINE.rglob("*.py")):
        rel = py.relative_to(_ENGINE)
        if rel.parts[0] == "strategies" or py == _LEAF:
            continue
        hits.extend(_direct_prepare_calls(py))
    assert hits == [], (
        "라이브 prepare 는 `funnel_capture.live_prepare_one/_many` 로만 부른다 — 잠금·meta 기록·"
        f"예외 격리가 한 곳이어야 한다 (§4.4). 직접 호출: {hits}"
    )


@pytest.mark.parametrize("fname,at_least", [("boot_manager.py", 1), ("scheduler.py", 3)])
def test_lock_2_call_sites_when_scanned_then_route_through_wrapper(fname, at_least):
    n = _wrapper_calls(_ENGINE / fname)
    assert n >= at_least, (
        f"{fname}: live_prepare_* 호출 {n}곳 (기대 ≥{at_least} — 부팅 1 / 사전 구독 2 + 5분 재준비 1)"
    )


def test_lock_3_leaf_when_exists_then_no_eight_area_import():
    assert _LEAF.exists(), "src/engine/funnel_capture.py 미구현 (Red — cycle364 §2.2)"
    tree = ast.parse(_LEAF.read_text(encoding="utf-8"))
    bad = []
    for n in ast.walk(tree):
        mods: list[str] = []
        if isinstance(n, ast.Import):
            mods = [a.name for a in n.names]
        elif isinstance(n, ast.ImportFrom) and n.module:
            mods = [n.module] + [f"{n.module}.{a.name}" for a in n.names]
        for m in mods:
            if any(m == e or m.startswith(e + ".") for e in _EIGHT_AREA_MODULES):
                bad.append(f"{n.lineno}:{m}")
    assert bad == [], f"leaf 가 8영역을 import 한다 (지연 import 포함): {bad}"


def test_lock_4_leaf_when_exists_then_no_naive_wall_clock():
    assert _LEAF.exists(), "src/engine/funnel_capture.py 미구현 (Red — cycle364 §2.2)"
    tree = ast.parse(_LEAF.read_text(encoding="utf-8"))
    bad = []
    for n in ast.walk(tree):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute):
            if n.func.attr == "now" and not n.args and not n.keywords:
                bad.append(f"{n.lineno}: now()")
            if n.func.attr == "today" and isinstance(n.func.value, ast.Name) and n.func.value.id == "date":
                bad.append(f"{n.lineno}: date.today()")
    assert bad == [], f"leaf 에 naive 벽시계 호출: {bad} — KST 명시(`_now_kst()` seam)"


def test_lock_5_scheduler_evening_body_when_moved_then_thin_delegate():
    """§4.6 — `_evening_funnel_capture_once` 본체는 leaf 로 가고 scheduler 에는 위임만 남는다
    (라인 상한 <3,900 · 순감 약 35줄). 본체가 남아 있으면 count_all 폴링도 남는다(M5)."""
    src = (_ENGINE / "scheduler.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    fn = next(
        n for n in ast.walk(tree)
        if isinstance(n, ast.AsyncFunctionDef) and n.name == "_evening_funnel_capture_once"
    )
    body = [s for s in fn.body if not (isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant))]
    names = {
        (c.func.attr if isinstance(c.func, ast.Attribute) else getattr(c.func, "id", None))
        for c in ast.walk(fn) if isinstance(c, ast.Call)
    }
    assert "evening_capture_once" in names, "scheduler 저녁 once 가 leaf `evening_capture_once` 로 위임하지 않는다"
    assert "count_all" not in names, "저녁 경로에 count_all 폴링이 남았다 (M5)"
    assert len(body) <= 4, f"위임 본체는 몇 줄이어야 한다 (실측 문장 {len(body)}개)"


# ══════════════════════════════════════════════════════════════════════
# 🔁 round 2 — R7 죽은 except 제거 · leaf docstring 정직화
# ══════════════════════════════════════════════════════════════════════
def _dead_try_sites(path: Path) -> list[str]:
    """본문이 `await …live_prepare_one/_many(…)` 한 문장뿐인 `try:` — wrapper 가 never-raise 라
    그 except 는 영원히 안 돈다(옛 실패 문구가 그 안에 갇혀 grep 에서 사라진다)."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out = []
    for n in ast.walk(tree):
        if not isinstance(n, ast.Try) or len(n.body) != 1:
            continue
        stmt = n.body[0]
        if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Await):
            call = stmt.value.value
            if isinstance(call, ast.Call):
                f = call.func
                name = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", None)
                if name in _WRAPPERS:
                    out.append(f"{path.relative_to(_ROOT)}:{n.lineno}")
    return out


@pytest.mark.parametrize("fname", ["boot_manager.py", "scheduler.py"])
def test_lock_6_call_sites_when_wrapper_never_raises_then_no_dead_except(fname):
    dead = _dead_try_sites(_ENGINE / fname)
    assert dead == [], (
        f"never-raise wrapper 를 감싼 죽은 try/except (R7): {dead} — 실패 문구는 wrapper 의 "
        "`[live_prepare]` 행이 옛 문구(「전략 prepare 실패」/「재 prepare 실패」)를 담아 남긴다"
    )


def test_lock_7_leaf_module_docstring_when_read_then_states_real_contract():
    """R7 — 운영 leaf 의 docstring 이 「스크래치 전용 참조 Green」이라고 적혀 있으면 다음 사람이
    지워도 되는 발판으로 읽는다(지우면 scheduler 모듈 import 가 실패해 기동이 안 된다)."""
    assert _LEAF.exists()
    doc = ast.get_docstring(ast.parse(_LEAF.read_text(encoding="utf-8"))) or ""
    for bad in ("스크래치", "참조 Green"):
        assert bad not in doc, f"leaf docstring 이 여전히 `{bad}` 라고 적는다: {doc[:120]!r}"
    for token in ("21:00", "20:30", "21:15", "never-raise", "_live_prepare_meta", "PV-1", "8영역", "S2"):
        assert token in doc, f"leaf docstring 에 계약 `{token}` 가 없다 (R7)"
