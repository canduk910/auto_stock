"""테스트 쪽 전략 명부 — `src/engine/strategies/` 를 직접 읽는다. 전략 이름을 적은 목록을 두지 않는다.

왜 있나(리팩토링 카드 #1 · `_workspace/refactor/2026-09-27_strategy_add_remove_structure.md` §6):
안전 가드(A-GATE·C-DEFAULT·cycle233 게이트 위치·예산 관문 행위·카탈로그 대조)가 7개 고정 목록을
돌아서, 여덟째 전략 파일은 **아무도 보지 않은 채** 통과했다(관문을 안 거치는 매수 수량 · 비중 곱
2.0 · 게이트 없는 매수 신호가 전부 초록). 반대로 「정확히 7파일」 단언은 규약을 지킨 복사를 붉혔다.
가드는 이 명부를 돌고, 새 전략은 파일을 두는 순간 모든 가드의 대상이 된다.

- **파일 명부** — 디렉터리의 `*.py` 전부(`__init__.py` 와 `NON_STRATEGY_FILES` 제외), 파일 이름순.
  AST 만 쓰므로 이 모듈을 import 해도 전략 모듈은 로드되지 않는다.
- **클래스 명부** — `strategy_classes()` 를 부를 때만 import 한다.
- 규약: **전략 id == 파일 stem**. 지금 7개 모두 성립하고, 카탈로그 대조
  (`test_cycle278_param_catalog.py`)가 `param_catalog.STRATEGY_IDS` 와 같은지 잰다.
- **등록 명부와는 다른 축이다.** 「등록된 전략 전부」가 필요한 테스트(엔드포인트·계약)는
  `trading_scheduler.registry.all()` 을 쓴다 — 파일만 두고 등록하지 않은 전략이 거기서 붉으면 거짓 붉음이다.
- 등록 순서(= 매수 우선순위)는 이 명부가 다루지 않는다. 순서가 계약인 곳은 `param_catalog.STRATEGY_IDS` 를 돈다.

소스 스캔은 `Path.glob` + AST 다 — `git ls-files` 는 미추적 새 파일을 로컬에서 못 본다(cycle259 S4b).
자기검사 = `tests/unit/ast/test_strategy_census.py`.
"""

from __future__ import annotations

import ast
import importlib
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STRATEGIES_DIR = ROOT / "src" / "engine" / "strategies"
STRATEGIES_REL = "src/engine/strategies"

#: 전략 디렉터리에 둔 「전략이 아닌」 `.py`. 헬퍼 모듈을 두면 여기에 파일 이름을 적는다 —
#: 자기검사가 `StrategyBase` 서브클래스가 정확히 1개가 아닌 파일을 이 목록으로 보낸다.
#: 전략은 여기 넣을 수 없다 — 다른 전략을 상속한 클래스도 전략이고, C0-3 이 import 로 잰다.
NON_STRATEGY_FILES: frozenset[str] = frozenset()

#: 탐지기 무효화 방지 하한(G-245-6·cycle324·cycle384 A12 의 `>= 7` 관례). 경로가 틀려 명부가
#: 비면 소비자 parametrize 가 0건이 되어 **조용히 skip** 된다 — 그래서 명부가 이 하한보다 작으면
#: 이 모듈이 import 단계에서 실패하고, 소비자 전부가 수집 오류로 붉다(파일 하나만 돌려도).
#: 전략을 빼는 사이클은 이 값을 같이 내린다. 등록 축 하한(`test_cycleF_te_endpoint.py`)도 이 값을 쓴다.
MIN_STRATEGIES = 7


def _scan(directory: Path) -> tuple[str, ...]:
    return tuple(sorted(
        p.name for p in directory.glob("*.py")
        if p.name != "__init__.py" and p.name not in NON_STRATEGY_FILES
    ))


#: 전략 파일 이름(`momentum.py` …), 파일 이름순.
STRATEGY_FILES: tuple[str, ...] = _scan(STRATEGIES_DIR)
if len(STRATEGY_FILES) < MIN_STRATEGIES:
    # assert 가 아니라 raise — `python -O` 에서도 꺼지지 않는다.
    raise RuntimeError(
        f"전략 명부 {len(STRATEGY_FILES)}개 < 하한 {MIN_STRATEGIES} ({STRATEGIES_DIR}): {STRATEGY_FILES}. "
        "명부가 비면 명부를 도는 가드가 붉지 않고 조용히 skip 된다. 경로가 틀렸으면 고치고, "
        "전략을 뺀 사이클이면 tests/_strategy_census.py 의 MIN_STRATEGIES 를 같이 내려라"
    )
#: 전략 id(= 파일 stem), `STRATEGY_FILES` 와 같은 순서.
STRATEGY_IDS: tuple[str, ...] = tuple(Path(f).stem for f in STRATEGY_FILES)
#: 리포 루트 기준 상대경로(`src/engine/strategies/momentum.py` …) — 닫힌 세계 판정용.
STRATEGY_RELS: frozenset[str] = frozenset(f"{STRATEGIES_REL}/{f}" for f in STRATEGY_FILES)


def _base_is_strategy_base(base: ast.expr) -> bool:
    return (isinstance(base, ast.Name) and base.id == "StrategyBase") or (
        isinstance(base, ast.Attribute) and base.attr == "StrategyBase"
    )


#: 명부 추출기가 0개를 셀 때 덧붙이는 안내. AST 추출기는 **직접** 상속만 세므로, 다른 전략을
#: 상속한 전략은 0개로 보인다 — 그것을 헬퍼로 오인해 `NON_STRATEGY_FILES` 에 숨기지 않게 한다.
INDIRECT_STRATEGY_HINT = (
    "다른 전략 클래스를 상속한 클래스도 전략이다(이 추출기는 StrategyBase 직접 상속만 센다) — "
    "NON_STRATEGY_FILES 에 넣지 말고 StrategyBase 를 직접 상속하게 하라. 명부를 도는 AST 가드는 "
    "그 파일의 소스만 읽으므로 물려받은 calc_buy_quantity 등을 보지 못한다"
)


def strategy_class_names_ast(fname: str) -> list[str]:
    """그 파일 최상위에서 `StrategyBase` 를 직접 상속하는 클래스 이름들(AST)."""
    tree = ast.parse((STRATEGIES_DIR / fname).read_text(encoding="utf-8"))
    return [
        n.name for n in tree.body
        if isinstance(n, ast.ClassDef) and any(_base_is_strategy_base(b) for b in n.bases)
    ]


def strategy_class_name_ast(fname: str) -> str:
    """전략 클래스 이름 하나. 0개·2개 이상이면 명부 문제로 즉시 실패한다."""
    names = strategy_class_names_ast(fname)
    assert len(names) == 1, (
        f"{STRATEGIES_REL}/{fname}: StrategyBase 서브클래스 {names} — 전략 파일은 정확히 1개를 정의한다. "
        f"{INDIRECT_STRATEGY_HINT}. "
        "전략이 아닌 헬퍼면 tests/_strategy_census.py 의 NON_STRATEGY_FILES 에 파일 이름을 적어라"
    )
    return names[0]


def strategy_classes_defined_in(mod) -> list[type]:
    """그 모듈에 **정의된**(`__module__` 일치) `StrategyBase` 서브클래스 — 간접 상속 포함(import 판정).

    다른 모듈에서 import 해 온 전략 클래스(재노출)는 세지 않는다.
    """
    from src.engine.strategy_base import StrategyBase

    return [
        v for v in vars(mod).values()
        if isinstance(v, type) and issubclass(v, StrategyBase)
        and v is not StrategyBase and v.__module__ == mod.__name__
    ]


@lru_cache(maxsize=1)
def strategy_classes() -> dict[str, type]:
    """`{전략 id: 클래스}` — 명부 순서. 부를 때만 전략 모듈을 import 한다.

    명부 문제(클래스 0개·2개 이상)는 소비자 테스트의 실패로 위장하지 않고 여기서 바로 실패한다.
    """
    out: dict[str, type] = {}
    for sid in STRATEGY_IDS:
        mod = importlib.import_module(f"src.engine.strategies.{sid}")
        found = strategy_classes_defined_in(mod)
        assert len(found) == 1, (
            f"{STRATEGIES_REL}/{sid}.py: 이 모듈에 정의된 StrategyBase 서브클래스 "
            f"{[c.__name__ for c in found]} — 정확히 1개여야 한다. 전략이 아니면 NON_STRATEGY_FILES 에 적어라"
        )
        out[sid] = found[0]
    return out
