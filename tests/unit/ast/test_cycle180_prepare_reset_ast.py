"""사이클 180 — VB/LTV `prepare()` 시작부 3-dict 리셋 AST 정적 가드 (C + D 그룹).

명세: `_workspace/red/cycle180_vb_ltv_prepare_reset.md`
영속 의무: 사이클 167 (source 텍스트 스캔 false-positive 교훈) → **AST 토큰 기반** 탐지.
주석/docstring/문자열 리터럴 매칭 금지 — `ast` 모듈로 함수 본문을 파싱해
`self.<attr>.clear()` Call 노드를 직접 탐지한다.

가드 ID taxonomy (domain-expert §7 정합):
- G-180-AST-CLEAR-PRESENT (C.7, Red — 현재 FAIL): prepare AST 에 3 dict clear 각 ≥1건.
- G-180-AST-FORBIDDEN-ABSENT (C.8, 현재 PASS — 미래 가드): `_limit_up_reached.clear()` +
  `_next_day_clear_pending` 재할당이 prepare AST 에 0건.
- G-180-AST-CLEAR-POSITION (C.9, Red — 현재 FAIL): 3 clear 가 첫 `_scan_universe()` await *전*.
- G-180-AST-EXIT-NO-SIDE-EFFECT (D.10, 현재 PASS — SAFETY): check_exit_signal/check_force_clear
  본체에 신규 clear/funnel hook 0건 + risk/order_engine import 0건.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from tests.unit.ast._ast_helpers import find_function_def, read_module_source

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[3]
_STRAT_DIR = REPO_ROOT / "src" / "engine" / "strategies"
_VB_PY = _STRAT_DIR / "volatility_breakout.py"
_LTV_PY = _STRAT_DIR / "long_tail_volatility.py"

# clear 대상 3-dict (시정 명세)
_RESET_DICTS = ("_targets", "_open_confirmed", "_prev_price")
# 절대 clear/리셋 금지 (제외 명세)
_FORBIDDEN_RESET = ("_limit_up_reached", "_next_day_clear_pending")

_STRATEGY_FILES = {
    "volatility_breakout": _VB_PY,
    "long_tail_volatility": _LTV_PY,
}


# ---------------------------------------------------------------------------
# AST 탐지 헬퍼 — self.<attr>.clear() Call 노드 (문자열/주석 무시)
# ---------------------------------------------------------------------------
def _count_self_attr_clear(node: ast.AST, attr: str) -> int:
    """서브트리에서 `self.<attr>.clear()` Call 노드 개수.

    매칭: Call(func=Attribute(attr='clear', value=Attribute(attr=<attr>, value=Name('self')))).
    docstring / 주석 / 문자열 리터럴은 AST Call 노드가 아니므로 자연 무시 (사이클 167 교훈).
    """
    count = 0
    for sub in ast.walk(node):
        if not isinstance(sub, ast.Call):
            continue
        f = sub.func
        if not (isinstance(f, ast.Attribute) and f.attr == "clear"):
            continue
        inner = f.value
        if (
            isinstance(inner, ast.Attribute)
            and inner.attr == attr
            and isinstance(inner.value, ast.Name)
            and inner.value.id == "self"
        ):
            count += 1
    return count


def _self_attr_clear_linenos(node: ast.AST, attr: str) -> list[int]:
    """`self.<attr>.clear()` Call 노드의 lineno 목록."""
    linenos: list[int] = []
    for sub in ast.walk(node):
        if not isinstance(sub, ast.Call):
            continue
        f = sub.func
        if not (isinstance(f, ast.Attribute) and f.attr == "clear"):
            continue
        inner = f.value
        if (
            isinstance(inner, ast.Attribute)
            and inner.attr == attr
            and isinstance(inner.value, ast.Name)
            and inner.value.id == "self"
        ):
            linenos.append(sub.lineno)
    return linenos


def _first_scan_universe_lineno(node: ast.AST) -> int | None:
    """서브트리에서 첫 `self._scan_universe()` Call 노드의 최소 lineno."""
    linenos: list[int] = []
    for sub in ast.walk(node):
        if not isinstance(sub, ast.Call):
            continue
        f = sub.func
        if (
            isinstance(f, ast.Attribute)
            and f.attr == "_scan_universe"
            and isinstance(f.value, ast.Name)
            and f.value.id == "self"
        ):
            linenos.append(sub.lineno)
    return min(linenos) if linenos else None


def _count_self_attr_reset(node: ast.AST, attr: str) -> int:
    """`self.<attr> = ...` 재할당 + `self.<attr>.clear()` 합산 (금지 리셋 탐지).

    `_next_day_clear_pending` 처럼 bool 필드는 `.clear()` 가 아니라 `= False` 재할당으로
    리셋될 수 있으므로 Assign(target=Attribute(value=Name('self'), attr=<attr>)) 도 포착.
    """
    count = _count_self_attr_clear(node, attr)
    for sub in ast.walk(node):
        if not isinstance(sub, ast.Assign):
            continue
        for target in sub.targets:
            if (
                isinstance(target, ast.Attribute)
                and target.attr == attr
                and isinstance(target.value, ast.Name)
                and target.value.id == "self"
            ):
                count += 1
    return count


def _count_calls_in_node(node: ast.AST, name: str) -> int:
    """서브트리에서 `name(...)` / `obj.name(...)` Call 노드 개수."""
    count = 0
    for sub in ast.walk(node):
        if not isinstance(sub, ast.Call):
            continue
        f = sub.func
        if isinstance(f, ast.Name) and f.id == name:
            count += 1
        elif isinstance(f, ast.Attribute) and f.attr == name:
            count += 1
    return count


# ===========================================================================
# C.7 — clear 3줄 존재 (G-180-AST-CLEAR-PRESENT) — 현재 FAIL (Red)
# ===========================================================================
@pytest.mark.parametrize("strat,path", list(_STRATEGY_FILES.items()))
@pytest.mark.parametrize("attr", _RESET_DICTS)
def test_g_180_ast_clear_present(strat, path, attr):
    """prepare AST 에 `self.<attr>.clear()` Call 노드 ≥ 1건 (3 dict 각각).

    현재 코드(미시정) = clear 0건 → FAIL (Red). 시정 후 = ≥1건 → PASS.
    """
    source = read_module_source(path)
    node = find_function_def(source, "prepare")
    assert node is not None, f"{strat} prepare 함수 정의 부재"

    n = _count_self_attr_clear(node, attr)
    assert n >= 1, (
        f"{strat} prepare 에 `self.{attr}.clear()` {n}건 — ≥1건 의무 위반 "
        f"(전일 stale 누적 차단 = 시정 명세 3줄 중 1줄)"
    )


# ===========================================================================
# C.8 — 금지 clear/리셋 부재 (G-180-AST-FORBIDDEN-ABSENT)
#       현재 PASS — 미래 Green/리팩터 실수 영구 차단 가드.
# ===========================================================================
@pytest.mark.parametrize("strat,path", list(_STRATEGY_FILES.items()))
@pytest.mark.parametrize("attr", _FORBIDDEN_RESET)
def test_g_180_ast_forbidden_reset_absent(strat, path, attr):
    """prepare AST 에 `self._limit_up_reached.clear()` / `_next_day_clear_pending` 재할당 0건.

    domain-expert §의제2 — clear 시 상한가 익일청산/익일청산 race 가드 파괴.
    현재 코드 = 0건 PASS. Green 이 실수로 추가하면 즉시 FAIL → 영구 차단.

    주의: `__init__` 의 `self._next_day_clear_pending = False` 초기화는 prepare 범위 밖이므로
    무관 (본 가드는 prepare 노드 한정).
    """
    source = read_module_source(path)
    node = find_function_def(source, "prepare")
    assert node is not None, f"{strat} prepare 함수 정의 부재"

    n = _count_self_attr_reset(node, attr)
    assert n == 0, (
        f"{strat} prepare 에 `self.{attr}` 리셋(clear/재할당) {n}건 — 0건 의무 위반 "
        f"(상한가 익일청산/익일청산 race 안전성 파괴 = 절대 제외 명세 위반)"
    )


# ===========================================================================
# C.9 — clear 위치 = 첫 `_scan_universe()` 호출 *전* (G-180-AST-CLEAR-POSITION)
#       현재 FAIL (Red, clear 부재 → lineno 없음).
# ===========================================================================
@pytest.mark.parametrize("strat,path", list(_STRATEGY_FILES.items()))
def test_g_180_ast_clear_before_scan_universe(strat, path):
    """3 dict clear 가 모두 첫 `self._scan_universe()` await *전* (시작부 보장).

    누적 차단의 의미 = 첫 스캔/재할당 전에 비워야 stale 종목이 _scanned_tickers 로 새지 않음.
    현재 코드 = clear 부재 → lineno 없음 → FAIL (Red).
    """
    source = read_module_source(path)
    node = find_function_def(source, "prepare")
    assert node is not None, f"{strat} prepare 함수 정의 부재"

    scan_lineno = _first_scan_universe_lineno(node)
    assert scan_lineno is not None, f"{strat} prepare 에 self._scan_universe() 호출 부재 (전제 위반)"

    for attr in _RESET_DICTS:
        linenos = _self_attr_clear_linenos(node, attr)
        assert linenos, (
            f"{strat} prepare 에 `self.{attr}.clear()` 부재 — "
            f"첫 _scan_universe() 전 시작부 clear 의무 위반 (Red)"
        )
        assert max(linenos) < scan_lineno, (
            f"{strat} `self.{attr}.clear()` (line {linenos}) 가 첫 _scan_universe() "
            f"(line {scan_lineno}) *이후* — 시작부 clear 의무 위반 (stale 누적 차단 의미 소실)"
        )


# ===========================================================================
# D.10 — 청산 경로 무영향 (G-180-AST-EXIT-NO-SIDE-EFFECT)
#        현재 PASS — 사이클 38/143/170 SAFETY 답습.
# ===========================================================================
@pytest.mark.parametrize("strat,path", list(_STRATEGY_FILES.items()))
@pytest.mark.parametrize("fn_name", ["check_exit_signal", "check_force_clear"])
def test_g_180_ast_exit_path_no_reset_no_funnel(strat, path, fn_name):
    """check_exit_signal/check_force_clear 본체에 신규 3-dict clear + funnel hook 0건.

    시정 = 매수 진입 *전* (prepare) 한정. 청산 경로는 변경 0 (사이클 38 명문화).
    """
    source = read_module_source(path)
    node = find_function_def(source, fn_name)
    assert node is not None, f"{strat} {fn_name} 함수 정의 부재"

    for attr in _RESET_DICTS:
        assert _count_self_attr_clear(node, attr) == 0, (
            f"{strat} {fn_name} 본체에 `self.{attr}.clear()` 발견 — 청산 경로 변경 금지 (사이클 38)"
        )
    for hook in ("_record_funnel_step", "_record_funnel_pipeline_step", "_reset_funnel_steps"):
        assert _count_calls_in_node(node, hook) == 0, (
            f"{strat} {fn_name} 본체에 `{hook}` 호출 발견 — 매도 hot path funnel 적재 금지 "
            f"(사이클 143/170 SAFETY)"
        )


@pytest.mark.parametrize("strat,path", list(_STRATEGY_FILES.items()))
def test_g_180_ast_no_risk_order_import(strat, path):
    """전략 모듈에 risk / order_engine import 0건 (매수 진입 전 격리, 사이클 173 SAFETY 답습)."""
    source = read_module_source(path)
    assert "from src.engine.risk import" not in source, f"{strat} risk import 금지"
    assert "from src.engine.order_engine import" not in source, (
        f"{strat} order_engine import 금지"
    )
