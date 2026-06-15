"""사이클 136 (2026-06-15) — AST 가드 49 파일 공통 헬퍼 모듈 (카드 #25 영속).

배경:
- `tests/unit/ast/` 49 파일 누적 (사이클 84/124/127/129/131/135 화이트리스트 다수).
- 48 파일 read 패턴 / 34 파일 ast.parse / 8 파일 헬퍼 함수 직접 정의.
- 동일 패턴 반복 영역 영구 영속 = DRY 위반.

사이클 130 refactor-review 권고 카드 #25 LOW (-1,500L 추정).
점진 마이그레이션: 사이클 136 = 헬퍼 신규 + ≥ 5 파일 마이그레이션 / 사이클 137+ = 10 파일/사이클.

영속 의무 매트릭스:
- 사이클 38 명문화 (테스트 영역 한정 = production 영향 0)
- 사이클 67 facade re-export 패턴 답습 (헬퍼 모듈 = re-export only)
- 사이클 89 G-AST1 의미 전환 패턴 답습 (`has_function_def` = 함수 정의 OR 모듈 export 영역 흡수)
- 사이클 133 master metrics 일관성 영속 (사이클 89 `_has_function_def` 의미 전환 답습)

매매 안전성 영향 0 (테스트 영역 한정 + production 영향 0).
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Optional, Union

FunctionLikeNode = Union[ast.FunctionDef, ast.AsyncFunctionDef]


def read_module_source(module_path: Union[Path, str]) -> str:
    """모듈 source 영역 UTF-8 영역 영구 영속 read.

    Args:
        module_path: Path 또는 str 영역 모듈 경로.

    Returns:
        source 영역 영구 영속 (UTF-8 디코딩 영속).
    """
    if isinstance(module_path, str):
        module_path = Path(module_path)
    return module_path.read_text(encoding="utf-8")


def has_function_def(source: str, name: str) -> bool:
    """함수 정의 OR 모듈-레벨 export 영역 영구 영속 존재 여부.

    사이클 89 G-AST1 의미 전환 패턴 답습 (사이클 133 영속) — 사이클 66 K-2 답습:
    - Red 시점 = `def name(...)` 또는 `async def name(...)` 함수 정의
    - Green 시점 = `make_factory()` 팩토리 반환값을 모듈-레벨 tuple unpacking 으로 할당 영속.
      예: `(record_X, flush_X, _collector) = make_factory(...)`.

    Args:
        source: 모듈 source.
        name: 함수 또는 변수 이름.

    Returns:
        True: 함수 정의 OR 모듈-레벨 할당 영역 영구 영속 존재.
    """
    tree = ast.parse(source)
    for node in ast.walk(tree):
        # 패턴 1 — 함수 정의 (사이클 89 Red 시점)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return True
        # 패턴 2 — 모듈-레벨 Assign 영역 영구 영속 tuple unpacking 또는 단일 할당 (사이클 133 Green 시점)
        if isinstance(node, ast.Assign):
            for target in node.targets:
                # 단일 할당: name = ...
                if isinstance(target, ast.Name) and target.id == name:
                    return True
                # tuple unpacking: (name, ...) = ...
                if isinstance(target, ast.Tuple):
                    for elt in target.elts:
                        if isinstance(elt, ast.Name) and elt.id == name:
                            return True
    return False


def count_function_calls(source: str, name: str) -> int:
    """함수 호출 사이트 개수 영역 영구 영속.

    매칭:
    - `name(...)` 단순 호출.
    - `module.name(...)` 속성 호출.
    - `await name(...)` / `await module.name(...)` 영역 영구 영속 (사이클 101 답습).

    ast.walk 영역 영구 영속 = ast.Await 영역 영구 영속 traversal 시 내부 ast.Call 영역 영구 영속 도달.
    중복 카운트 영구 영속 차단 영역 영구 영속 = ast.Call 영역 영구 영속 단일 traversal 영속.

    Args:
        source: 모듈 source.
        name: 함수 이름.

    Returns:
        호출 사이트 개수.
    """
    tree = ast.parse(source)
    count = 0
    for sub in ast.walk(tree):
        if not isinstance(sub, ast.Call):
            continue
        func = sub.func
        if isinstance(func, ast.Name) and func.id == name:
            count += 1
        elif isinstance(func, ast.Attribute) and func.attr == name:
            count += 1
    return count


def find_function_def(source: str, name: str) -> Optional[FunctionLikeNode]:
    """함수 정의 node 영역 영구 영속 반환 (FunctionDef 또는 AsyncFunctionDef).

    Args:
        source: 모듈 source.
        name: 함수 이름.

    Returns:
        ast.FunctionDef 또는 ast.AsyncFunctionDef 또는 None.
    """
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    return None


def count_function_calls_in_node(node: ast.AST, name: str) -> int:
    """노드 서브트리 영역 영구 영속 함수 호출 사이트 개수 (사이클 102 답습).

    `count_function_calls(source, name)` 영역 = 전체 source 영역 영구 영속 = ast.parse 영역 내부 영속.
    본 함수 영역 영구 영속 = 이미 파싱된 ast.AST 서브트리 영역 영구 영속 (사이클 102 답습).

    Args:
        node: ast.AST 서브트리 (예: 특정 함수 정의 노드).
        name: 함수 이름.

    Returns:
        호출 사이트 개수.
    """
    count = 0
    for sub in ast.walk(node):
        if not isinstance(sub, ast.Call):
            continue
        func = sub.func
        if isinstance(func, ast.Name) and func.id == name:
            count += 1
        elif isinstance(func, ast.Attribute) and func.attr == name:
            count += 1
    return count


def count_imports_from(source: str, module: str, name: Optional[str] = None) -> int:
    """`from {module} import {name}` 영역 영구 영속 카운트.

    Args:
        source: 모듈 source.
        module: import 영역 영구 영속 module 이름 (예: `src.engine.scanner`).
        name: 특정 import name (None = module level 전체 카운트).

    Returns:
        해당 import 사이트 개수.
    """
    tree = ast.parse(source)
    count = 0
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom):
            continue
        if node.module != module:
            continue
        if name is None:
            count += 1
        else:
            for alias in node.names:
                if alias.name == name:
                    count += 1
                    break
    return count


__all__ = [
    "read_module_source",
    "has_function_def",
    "count_function_calls",
    "count_function_calls_in_node",
    "find_function_def",
    "count_imports_from",
]
