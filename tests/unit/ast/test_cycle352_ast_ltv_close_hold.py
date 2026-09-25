"""cycle352 — LTV 15:20 상한가 유지 확인 구조 가드 (G1~G6).

정본 명세 = `_workspace/domain_consult/cycle352_ltv_limit_up_trailing.md` §5.6.

- G1: `limit_up_close_hold_mode` ∉ `PARAM_RANGES`·`INT_PARAMS`(런타임 dict + 소스
  리터럴 이중) — 청산 규약 킬스위치라 AI 자동 튜닝이 건드리면 안 된다.
- G2: 새 헬퍼(`_limit_up_close_hold_extra_clears`/`_evaluate_limit_up_close_hold`)
  안에 `await`·`Await`·DB/HTTP import 0 — 동기 순수 판정이어야 한다.
- G3: `check_force_clear` 안 숫자 리터럴 0 — 임계는 파라미터에서만 읽는다. G3b —
  `check_force_clear` 는 위임만 해 리터럴이 없는 게 당연하므로(독립 검증 nit),
  실제 비교가 있는 `_evaluate_limit_up_close_hold` 의 `prdy` 비교 우변이 리터럴이
  아니라 `threshold` 변수인지까지 스캔 범위를 넓힌다.
- G4: `check_exit_signal` 소스 세그먼트 sha **불변** — 이번 변경이 장중 청산을
  건드리지 않았음을 못 박는다.
- G5: 새 판정이 `try/except Exception` 안에 있다 — never-raise 구조 가드
  (cycle328 교훈 — 행위 테스트만으로는 좁히기 돌연변이가 초록으로 샌다).
- G6: `param_catalog` 스펙 존재 · `type="enum"` · `auto_tunable=False`.
"""

from __future__ import annotations

import ast
import hashlib
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parents[3]
_LTV = _ROOT / "src" / "engine" / "strategies" / "long_tail_volatility.py"

_NEW_KEY = "limit_up_close_hold_mode"


def _src() -> str:
    return _LTV.read_text(encoding="utf-8")


def _tree() -> ast.Module:
    return ast.parse(_src())


def _class_body(cls_name: str = "LongTailVolatilityStrategy") -> tuple[str, ast.ClassDef]:
    src = _src()
    tree = ast.parse(src)
    cls = next(
        n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == cls_name
    )
    return src, cls


def _method(name: str, cls_name: str = "LongTailVolatilityStrategy"):
    src, cls = _class_body(cls_name)
    for node in cls.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return src, node
    raise AssertionError(f"`{cls_name}.{name}` 를 찾지 못했다")


def _method_sha(name: str, cls_name: str = "LongTailVolatilityStrategy") -> str:
    src, node = _method(name, cls_name)
    seg = ast.get_source_segment(src, node)
    assert seg, f"`{name}` 세그먼트 추출 실패"
    return hashlib.sha256(seg.encode()).hexdigest()


def _collect_named_literal_str_keys(src: str, name: str) -> list[str]:
    """`name = {...}` (Assign/AnnAssign) 할당의 dict/set 리터럴 str 키 (cycle212 답습)."""
    tree = ast.parse(src)
    keys: list[str] = []
    for node in ast.walk(tree):
        value = None
        if isinstance(node, ast.Assign):
            if any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
                value = node.value
        elif isinstance(node, ast.AnnAssign):
            if isinstance(node.target, ast.Name) and node.target.id == name:
                value = node.value
        if isinstance(value, ast.Dict):
            for k in value.keys:
                if isinstance(k, ast.Constant) and isinstance(k.value, str):
                    keys.append(k.value)
        elif isinstance(value, ast.Set):
            for e in value.elts:
                if isinstance(e, ast.Constant) and isinstance(e.value, str):
                    keys.append(e.value)
    return keys


# ===========================================================================
# G1 — AI 자문 자동 튜닝 화이트리스트 편입 금지
# ===========================================================================
def test_g1_runtime_param_ranges_and_int_params_exclude_new_key():
    from src.engine import recommendation_engine as rec_mod

    assert _NEW_KEY not in rec_mod.PARAM_RANGES, (
        f"{_NEW_KEY} 는 청산 규약 킬스위치 — AI 자문이 매일 밤 흔들면 안 된다"
    )
    assert _NEW_KEY not in rec_mod.INT_PARAMS


def test_g1_source_literals_exclude_new_key():
    from src.engine import recommendation_engine as rec_mod

    src = Path(rec_mod.__file__).read_text(encoding="utf-8")
    for name in ("PARAM_RANGES", "INT_PARAMS"):
        keys = _collect_named_literal_str_keys(src, name)
        assert keys, f"{name} 리터럴 파싱 실패 (탐지기 무효)"
        assert _NEW_KEY not in keys, f"{name} 리터럴에 {_NEW_KEY!r} 편입 금지"


def test_g1_detector_self_test():
    """탐지기 self-test — 실제 존재하는 키는 검출된다 (공허한 PASS 차단)."""
    from src.engine import recommendation_engine as rec_mod

    src = Path(rec_mod.__file__).read_text(encoding="utf-8")
    assert "volume_multiplier" in _collect_named_literal_str_keys(src, "PARAM_RANGES")


# ===========================================================================
# G2 — 새 헬퍼는 순수 동기 판정 (await/DB/HTTP 0)
# ===========================================================================
@pytest.mark.parametrize(
    "name", ["_limit_up_close_hold_extra_clears", "_evaluate_limit_up_close_hold",
             "check_force_clear"],
)
def test_g2_new_helpers_have_no_await(name: str):
    _src_text, node = _method(name)
    for n in ast.walk(node):
        assert not isinstance(n, (ast.Await, ast.AsyncFunctionDef)), (
            f"`{name}` 안에 await/async 구조 — 동기 순수 판정 계약 위반"
        )


def test_g2_new_helpers_have_no_db_http_imports():
    _src_text, node = _method("_limit_up_close_hold_extra_clears")
    seg = ast.get_source_segment(_src_text, node)
    for token in ("httpx", "asyncpg", "pg.fetch", "pg.execute", "kis_request"):
        assert token not in seg, f"`_limit_up_close_hold_extra_clears` 에 `{token}` 토큰 — 순수 판정 위반"


# ===========================================================================
# G3 — `check_force_clear` 안 숫자 리터럴 0 (임계는 파라미터에서만)
# ===========================================================================
def test_g3_check_force_clear_has_no_numeric_literal():
    _src_text, node = _method("check_force_clear")
    hits = [
        n.value for n in ast.walk(node)
        if isinstance(n, ast.Constant) and isinstance(n.value, (int, float))
        and not isinstance(n.value, bool)
    ]
    assert hits == [], f"`check_force_clear` 에 숫자 리터럴 {hits} — 임계는 파라미터에서만 읽는다"


def test_g3b_evaluate_helper_threshold_compare_uses_variable_not_literal():
    """G3 확장 — `check_force_clear` 는 위임만 하므로 리터럴이 없는 게 당연해 원래
    가드가 무의미했다(독립 검증 nit). 실제 `prdy < threshold` 비교가 있는
    `_evaluate_limit_up_close_hold` 까지 스캔 범위를 넓혀, 그 비교의 우변이
    리터럴이 아니라 `threshold` 매개변수(파라미터에서 읽은 값)인지 확인한다
    — M6(`29.0` 하드코딩) 이 여기서도 구조적으로 잡힌다.
    """
    _src_text, node = _method("_evaluate_limit_up_close_hold")
    compares = [
        n for n in ast.walk(node)
        if isinstance(n, ast.Compare)
        and isinstance(n.left, ast.Name) and n.left.id == "prdy"
    ]
    assert compares, "`_evaluate_limit_up_close_hold` 에 `prdy` 비교가 없다 (탐지기 무효)"
    for cmp_node in compares:
        for comparator in cmp_node.comparators:
            assert isinstance(comparator, ast.Name) and comparator.id == "threshold", (
                f"`prdy` 비교 대상이 리터럴이거나 `threshold` 가 아니다: {ast.dump(comparator)}"
            )


# ===========================================================================
# G4 — `check_exit_signal` 소스 세그먼트 sha 불변 (장중 청산 무접촉 증명)
# ===========================================================================
_CHECK_EXIT_SIGNAL_SHA = "c8b0e6a8c8705d49bb6f12f82f505d426a5bdeb81413f8b2e0276eabb7dd9cad"


def test_g4_check_exit_signal_is_byte_identical():
    got = _method_sha("check_exit_signal")
    assert got == _CHECK_EXIT_SIGNAL_SHA, (
        f"`check_exit_signal` 이 바뀌었다 — cycle352 는 15:20 강제청산 경로만 건드린다. "
        f"got={got}"
    )


# ===========================================================================
# G5 — 새 판정이 try/except Exception 안에 있다 (never-raise 구조 가드)
# ===========================================================================
def test_g5_check_force_clear_wraps_new_logic_in_try_except():
    _src_text, node = _method("check_force_clear")
    tries = [n for n in ast.walk(node) if isinstance(n, ast.Try)]
    assert tries, "`check_force_clear` 안에 try 블록이 없다 — never-raise 계약 위반"

    found = False
    for tr in tries:
        has_bare_or_exception_handler = any(
            h.type is None
            or (isinstance(h.type, ast.Name) and h.type.id == "Exception")
            for h in tr.handlers
        )
        if not has_bare_or_exception_handler:
            continue
        calls_new_helper = any(
            isinstance(n, ast.Call)
            and (
                (isinstance(n.func, ast.Attribute) and n.func.attr == "_limit_up_close_hold_extra_clears")
                or (isinstance(n.func, ast.Name) and n.func.id == "_limit_up_close_hold_extra_clears")
            )
            for stmt in tr.body
            for n in ast.walk(stmt)
        )
        if calls_new_helper:
            found = True
            break
    assert found, (
        "`check_force_clear` 의 `try/except Exception` 이 새 헬퍼 호출을 감싸지 않는다"
    )


def test_g5_evaluate_helper_is_never_raise_top_level_try():
    """`_evaluate_limit_up_close_hold` 전체가 하나의 try/except Exception 이다."""
    _src_text, node = _method("_evaluate_limit_up_close_hold")
    body = node.body
    # docstring 을 뺀 첫 실행문이 Try 여야 한다.
    stmts = [s for s in body if not (isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant))]
    assert len(stmts) == 1 and isinstance(stmts[0], ast.Try), (
        "`_evaluate_limit_up_close_hold` 는 최상위가 단일 try 여야 한다(전체 감싸기)"
    )
    tr = stmts[0]
    assert any(
        h.type is None or (isinstance(h.type, ast.Name) and h.type.id == "Exception")
        for h in tr.handlers
    ), "`_evaluate_limit_up_close_hold` 의 handler 가 Exception 이 아니다"


# ===========================================================================
# G6 — param_catalog 등재
# ===========================================================================
def test_g6_param_catalog_spec_exists_as_enum_non_auto_tunable():
    from src.engine import param_catalog as pc

    spec = pc.SPEC_BY_KEY.get(_NEW_KEY)
    assert spec is not None, f"`param_catalog` 에 {_NEW_KEY!r} 스펙이 없다"
    assert spec.type == "enum"
    assert spec.auto_tunable is False
    assert spec.applies_to == ("long_tail_volatility",)
    assert {c.value for c in spec.choices} == {"enforce", "off"}
