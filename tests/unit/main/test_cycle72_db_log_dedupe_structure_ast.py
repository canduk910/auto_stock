"""사이클 72 G-7 — `_DbLogHandler` dedupe 캐시 구조 AST 정적 검증 (Red 단계).

옵션 D (사용자 결정): `_DbLogHandler.emit` 내부에 500ms TTL dedupe 캐시 영구 도입.

검증 항목 (정적 분석):
- `src/main.py` 에 `_DEDUPE_TTL_SECS = 0.5` 모듈 상수 또는 클래스 상수 존재
- `_DbLogHandler` 클래스에 `_dedupe_cache: dict[str, float]` 인스턴스 변수 초기화
  (`__init__` 또는 클래스 본문)
- `_DbLogHandler.emit` 본체에 `time.monotonic()` 호출 (TTL 비교 로직)

Red 단계 = 미구현 → 3 항목 모두 부재 → FAIL.
Green 단계 = backend-dev 가 옵션 D 구현 → PASS.

본 가드 = 사이클 56-E 60s TTL 캐시 패턴 답습이지만 ms 단위 단축 (500ms).
- 사이클 56-E: `_get_price_filter_for_scanner` 모듈 전역 60s TTL — 분당 1회 DB 조회
- 사이클 72: `_DbLogHandler._dedupe_cache` 인스턴스 500ms TTL — 동일 메시지 dedupe
"""
from __future__ import annotations

import ast
import re
from pathlib import Path


_MAIN_PATH = Path(__file__).resolve().parents[3] / "src" / "main.py"


def _read_main() -> str:
    return _MAIN_PATH.read_text(encoding="utf-8")


def test_g_7_db_log_dedupe_structure_ast() -> None:
    """G-7: src/main.py `_DbLogHandler` dedupe 캐시 구조 정적 검증.

    필수 3 요소:
    1. `_DEDUPE_TTL_SECS = 0.5` 상수 정의
    2. `_dedupe_cache` dict 인스턴스 변수 (또는 모듈 전역) 존재
    3. `_DbLogHandler.emit` 본체에 `time.monotonic()` 호출
    """
    source = _read_main()
    tree = ast.parse(source)

    # 1. _DEDUPE_TTL_SECS = 0.5 상수
    has_ttl_constant = False
    ttl_value: float | None = None
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "_DEDUPE_TTL_SECS":
                    has_ttl_constant = True
                    if isinstance(node.value, ast.Constant) and isinstance(
                        node.value.value, (int, float)
                    ):
                        ttl_value = float(node.value.value)
        if isinstance(node, ast.AnnAssign):
            if (
                isinstance(node.target, ast.Name)
                and node.target.id == "_DEDUPE_TTL_SECS"
            ):
                has_ttl_constant = True
                if (
                    node.value is not None
                    and isinstance(node.value, ast.Constant)
                    and isinstance(node.value.value, (int, float))
                ):
                    ttl_value = float(node.value.value)

    assert has_ttl_constant, (
        "src/main.py 에 `_DEDUPE_TTL_SECS` 상수 미정의 — 사이클 72 옵션 D 미구현"
    )
    assert ttl_value == 0.5, (
        f"`_DEDUPE_TTL_SECS={ttl_value}`, 기대 0.5 (500ms — 사이클 71 dup 차단 임계)"
    )

    # 2. `_dedupe_cache` 존재 (regex — __init__ 내부 self._dedupe_cache 또는 모듈 전역)
    assert re.search(
        r"_dedupe_cache\s*[:=]", source
    ), (
        "src/main.py 에 `_dedupe_cache` 변수 미정의 — "
        "옵션 D dedupe 캐시 dict 미구현"
    )

    # 3. _DbLogHandler.emit 본체에 time.monotonic() 호출
    db_handler_class = None
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "_DbLogHandler":
            db_handler_class = node
            break
    assert db_handler_class is not None, (
        "src/main.py 에 `_DbLogHandler` 클래스 미정의 — 구조 결함"
    )

    emit_method = None
    for node in db_handler_class.body:
        if isinstance(node, ast.FunctionDef) and node.name == "emit":
            emit_method = node
            break
    assert emit_method is not None, (
        "`_DbLogHandler.emit` 메서드 미정의"
    )

    # emit 본체에 time.monotonic() Call 검출
    has_monotonic = False
    for sub in ast.walk(emit_method):
        if isinstance(sub, ast.Call):
            func = sub.func
            # time.monotonic() 또는 monotonic() (from time import monotonic)
            if isinstance(func, ast.Attribute) and func.attr == "monotonic":
                if isinstance(func.value, ast.Name) and func.value.id == "time":
                    has_monotonic = True
                    break
            elif isinstance(func, ast.Name) and func.id == "monotonic":
                has_monotonic = True
                break

    assert has_monotonic, (
        "`_DbLogHandler.emit` 본체에 `time.monotonic()` 호출 부재 — "
        "TTL 비교 로직 미구현 (옵션 D dedupe 캐시 핵심)"
    )
