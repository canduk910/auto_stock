"""전략 명부(`tests/_strategy_census.py`) 자기검사 — 리팩토링 카드 #1.

명부를 도는 가드는 명부가 틀리면 같이 틀린다. 그래서 명부 자체를 잰다.

- **C0-1** 명부가 비지 않았다(`>= MIN_STRATEGIES`). 경로가 틀려 명부가 비면 소비자 parametrize 가
  0건이 되어 **붉지 않고 조용히 skip** 된다. 1차 방어는 명부 모듈 자신이다 — 하한 미달이면 import 에서
  `RuntimeError` 를 내 소비자 전부가 수집 오류로 붉다(소비자 파일 하나만 돌려도). 이 테스트는 그 하한과
  세 명부의 길이 정합을 다시 잰다.
- **C0-2** 명부의 파일마다 `StrategyBase` 를 **직접** 상속한 클래스가 정확히 1개다. 헬퍼 모듈을 전략
  디렉터리에 두면 여기서 붉고, 메시지가 「`NON_STRATEGY_FILES` 에 적어라」 를 말한다. 다른 전략을 상속한
  전략도 여기서 0개로 붉는데, 메시지가 그것은 헬퍼가 아니라 전략이라고 말한다.
- **C0-3** `NON_STRATEGY_FILES` 에 적힌 파일이 실재하고 `StrategyBase` 서브클래스를 정의하지 않는다 —
  전략을 예외 목록에 숨겨 가드를 피하는 것을 막는다. **import 로 잰다**(간접 상속 포함) — AST 직접 상속
  판정이면 다른 전략을 상속한 전략이 0개로 보여 그대로 숨는다(카드 #1 검증 D-1 실측: 숨긴 뒤 371 passed).
- **C0-4** import 로 찾은 클래스 = AST 로 찾은 클래스(추출기 자기 검증).
- **C0-6** 카드 #1 이 명부로 바꾼 파일에 「전략 전부」 를 적은 리터럴 목록이 다시 생기지 않는다 —
  새 전략이 붉힌 가드를 「목록에 한 줄 추가」 로 끄면 다음 전략이 또 조용히 통과한다.

카탈로그 등재 대조(명부 = `param_catalog.STRATEGY_IDS`)는 `tests/unit/engine/test_cycle278_param_catalog.py` 에 있다.
"""

from __future__ import annotations

import ast
import importlib
import types

import pytest

from tests import _strategy_census as census

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# C0-1 — 명부가 비지 않았다
# ---------------------------------------------------------------------------
def test_census_when_scanned_then_not_vacuous():
    assert census.STRATEGIES_DIR.is_dir(), f"전략 디렉터리가 없다: {census.STRATEGIES_DIR}"
    assert len(census.STRATEGY_FILES) >= census.MIN_STRATEGIES, (
        f"명부 {len(census.STRATEGY_FILES)}개 < 하한 {census.MIN_STRATEGIES} — {census.STRATEGY_FILES}. "
        "경로가 틀렸으면 고치고, 전략을 뺀 사이클이면 tests/_strategy_census.py 의 MIN_STRATEGIES 를 같이 내려라"
    )
    assert len(census.STRATEGY_IDS) == len(census.STRATEGY_FILES) == len(census.STRATEGY_RELS)


# ---------------------------------------------------------------------------
# C0-2 — 파일마다 전략 클래스 정확히 1개
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("fname", census.STRATEGY_FILES)
def test_census_when_file_listed_then_defines_exactly_one_strategy(fname):
    names = census.strategy_class_names_ast(fname)
    assert len(names) == 1, (
        f"{census.STRATEGIES_REL}/{fname}: StrategyBase 직접 서브클래스 {names}. 전략 파일은 정확히 1개를 정의한다. "
        f"{census.INDIRECT_STRATEGY_HINT}. "
        "전략이 아닌 헬퍼면 tests/_strategy_census.py 의 NON_STRATEGY_FILES 에 파일 이름을 적어라 "
        "— 그러면 명부를 도는 가드(A-GATE·C-DEFAULT 등)가 그 파일을 돌지 않는다"
    )


# ---------------------------------------------------------------------------
# C0-3 — 예외 목록은 전략을 숨기지 못한다
# ---------------------------------------------------------------------------
def _strategy_violations(mod) -> list[str]:
    """C0-3 판정 — 그 모듈에 정의된 `StrategyBase` 서브클래스 이름(간접 상속 포함). 비어야 통과."""
    return sorted(c.__name__ for c in census.strategy_classes_defined_in(mod))


def test_census_when_non_strategy_listed_then_exists_and_defines_no_strategy():
    for fname in sorted(census.NON_STRATEGY_FILES):
        path = census.STRATEGIES_DIR / fname
        assert path.is_file(), f"NON_STRATEGY_FILES 의 {fname} 가 없다 — 지운 파일이면 목록에서도 지워라"
        mod = importlib.import_module(f"src.engine.strategies.{path.stem}")
        names = _strategy_violations(mod)
        assert not names, (
            f"{fname} 는 StrategyBase 서브클래스 {names} 를 정의한다(간접 상속 포함) — 전략은 "
            "NON_STRATEGY_FILES 에 넣을 수 없다(넣으면 안전 가드가 그 전략을 보지 않는다). "
            "NON_STRATEGY_FILES 에서 빼고, 다른 전략을 상속했다면 StrategyBase 를 직접 상속하게 하라"
        )
    assert not (set(census.STRATEGY_FILES) & census.NON_STRATEGY_FILES)


def test_census_meta_c03_detector_when_fed_indirect_subclass_then_flags():
    """C0-3 자기 검증 — 다른 전략을 상속한 클래스를 잡고, 재노출·비전략 클래스는 잡지 않는다.

    D-1 재현형(`class ProbeSubStrategy(<명부 전략>)` 을 헬퍼로 위장)을 합성 모듈로 만든다 — 전략
    디렉터리에 파일을 쓰지 않는다.
    """
    from src.engine.strategy_base import StrategyBase

    some_strategy = next(iter(census.strategy_classes().values()))
    mod = types.ModuleType("src.engine.strategies._c03_meta_probe")
    mod.ReExported = some_strategy  # 다른 모듈에서 가져온 전략 — 세지 않는다
    mod.Helper = type("Helper", (), {"__module__": mod.__name__})
    assert _strategy_violations(mod) == [], "재노출·비전략 클래스를 전략으로 잘못 셌다"

    mod.ProbeSubStrategy = type("ProbeSubStrategy", (some_strategy,), {"__module__": mod.__name__})
    assert _strategy_violations(mod) == ["ProbeSubStrategy"], "간접 상속 전략을 놓쳤다(D-1 구멍)"

    mod.ProbeDirect = type("ProbeDirect", (StrategyBase,), {"__module__": mod.__name__})
    assert _strategy_violations(mod) == ["ProbeDirect", "ProbeSubStrategy"]


# ---------------------------------------------------------------------------
# C0-4 — import 결과 = AST 결과
# ---------------------------------------------------------------------------
def test_census_when_imported_then_classes_match_ast():
    classes = census.strategy_classes()
    assert tuple(classes) == census.STRATEGY_IDS
    for sid, cls in classes.items():
        assert [cls.__name__] == census.strategy_class_names_ast(f"{sid}.py"), (
            f"{sid}: import 로 찾은 클래스 {cls.__name__} ≠ AST {census.strategy_class_names_ast(f'{sid}.py')} "
            "— 명부 추출기 결함"
        )


# ---------------------------------------------------------------------------
# C0-6 — 명부로 바꾼 파일에 「전략 전부」 리터럴 목록이 되살아나지 않는다
# ---------------------------------------------------------------------------
#: 카드 #1 이 명부로 바꾼 파일. 원형별 부분집합(5개·2개 등)은 정당한 범위라 허용하고,
#: **명부 전부**를 담은 리터럴 컨테이너만 잡는다.
_CONVERTED_FILES: tuple[str, ...] = (
    "tests/_strategy_census.py",
    "tests/unit/ast/test_strategy_census.py",
    "tests/unit/ast/test_budget_limit_ast.py",
    "tests/unit/ast/test_cycle233_ast_account_risk.py",
    "tests/unit/engine/test_budget_limit_gate.py",
    "tests/unit/engine/test_cycle278_param_catalog.py",
    "tests/unit/ast/test_cycle274_ast_llm_gate.py",
    "tests/unit/ast/test_cycle276_ast_order_hook.py",
    "tests/unit/ast/test_cycle297_ast_scope.py",
    "tests/unit/ast/test_cycle222a3_ast_anchor_owner_coupling.py",
    "tests/unit/routes/test_cycleF_te_endpoint.py",
    "tests/contract/conftest.py",
    "tests/unit/ast/test_cycle384_ast_buy_paused.py",
)


def _as_strategy_id(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    for sid in census.STRATEGY_IDS:
        if value in (sid, f"{sid}.py", f"{census.STRATEGIES_REL}/{sid}.py"):
            return sid
    return None


def _container_elements(node: ast.AST) -> list[object]:
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        out: list[object] = []
        for e in node.elts:
            if isinstance(e, ast.Constant):
                out.append(e.value)
            elif isinstance(e, ast.Tuple) and e.elts and isinstance(e.elts[0], ast.Constant):
                out.append(e.elts[0].value)  # (sid, cls) · (sid, 파일, 클래스) 꼴
        return out
    if isinstance(node, ast.Dict):
        return [k.value for k in node.keys if isinstance(k, ast.Constant)]
    return []


def _full_census_literals(text: str) -> list[int]:
    lines = []
    for node in ast.walk(ast.parse(text)):
        ids = {_as_strategy_id(v) for v in _container_elements(node)} - {None}
        if ids and set(census.STRATEGY_IDS) <= ids:
            lines.append(node.lineno)
    return lines


def test_census_meta_detector_when_fed_full_literal_then_flags():
    """C0-6 자기 검증 — 탐지기가 세 표기(id·파일 이름·상대경로)를 모두 잡는다(공허 방지)."""
    ids = list(census.STRATEGY_IDS)
    assert _full_census_literals(f"X = {ids!r}\n") == [1]
    assert _full_census_literals(f"X = {tuple(f'{s}.py' for s in ids)!r}\n") == [1]
    assert _full_census_literals(
        f"X = {set(f'{census.STRATEGIES_REL}/{s}.py' for s in ids)!r}\n") == [1]
    assert _full_census_literals(f"X = {[(s, 0) for s in ids]!r}\n") == [1]
    assert _full_census_literals(f"X = {ids[:-1]!r}\n") == [], "부분집합은 허용한다"


@pytest.mark.parametrize("rel", _CONVERTED_FILES)
def test_census_when_converted_file_scanned_then_no_full_strategy_literal(rel):
    path = census.ROOT / rel
    assert path.is_file(), f"{rel} 가 없다 — 옮겼으면 이 목록을 고쳐라"
    lines = _full_census_literals(path.read_text(encoding="utf-8"))
    assert not lines, (
        f"{rel}:{lines} 에 전략 전부를 적은 리터럴 목록이 있다 — 새 전략이 그 목록을 조용히 빠져나간다. "
        "tests/_strategy_census.py 의 STRATEGY_FILES·STRATEGY_IDS·STRATEGY_RELS·strategy_classes() 를 써라"
    )
