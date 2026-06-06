"""사이클 65 hotfix H3 — system_logs INSERT timestamp KST 영구 가드 (AST 정적).

> **선례**: 사이클 53 B-4 KST `+09:00` 패턴 / 사이클 60·64 hotfix AST 가드.
> **결함 배경**:
>   - `src/db/system_logs.py::write_log` 는 timestamp 필드 명시 없이 INSERT →
>     DB default = PostgreSQL `now()` = UTC 저장. 사이클 53 KST `+09:00`
>     컨벤션 미준수.
>   - `src/main.py::_insert_log_to_db` 도 동일 결함 — `_DbLogHandler` 가
>     `logger.info()` 호출을 fire-and-forget 으로 위임할 때 timestamp 미명시
>     → UTC 저장. (system_logs INSERT 두 번째 경로).
>   - UTC 저장 → `from_date`/`to_date` KST 필터 (`+09:00` suffix) 와 9시간
>     어긋남 → 자정 ~ 09:00 KST 로그가 *어제* 영업일에 묶여 조회 누락 (silent 결함).
>
> 요구 행위 (Red 시점 — H2 hotfix 적용 후 PASS):
>   - src/ 전체 `supabase.table("system_logs").insert(...)` 호출이 모두 `timestamp`
>     키를 포함하고, 값이 KST 명시 (`datetime.now(KST)` 또는 `timezone(timedelta(hours=9))`).
>
> 위험 등급 HIGH — silent 결함화 (UTC 저장 + KST 필터 어긋남 자정~09:00 로그 누락).

검증 방법:
- AST 정적 파싱: `src/` 전체 `*.py` 스캔.
- `supabase.table("system_logs").insert(...)` 패턴 매칭 (Call 노드).
- INSERT data dict 의 키에 `"timestamp"` 포함 검증.
- timestamp 값이 KST 표현인지 정규식 검증 (`datetime.now(KST)` /
  `datetime.now(timezone(timedelta(hours=9)))`).
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit


# KST 표현 정규식 — 두 가지 표기 모두 허용
_KST_VALUE_PATTERNS = [
    re.compile(r"datetime\.now\(\s*KST\s*\)"),
    re.compile(r"datetime\.now\(\s*timezone\(\s*timedelta\(\s*hours\s*=\s*9\s*\)\s*\)\s*\)"),
]


def _is_system_logs_insert_call(node: ast.AST) -> bool:
    """`supabase.table("system_logs").insert(...)` 호출 노드 식별.

    AST 구조:
        Call(func=Attribute(attr='insert',
                            value=Call(func=Attribute(attr='table'),
                                       args=[Constant(value='system_logs')])))
    """
    if not isinstance(node, ast.Call):
        return False
    fn = node.func
    if not (isinstance(fn, ast.Attribute) and fn.attr == "insert"):
        return False
    inner = fn.value
    if not (isinstance(inner, ast.Call) and isinstance(inner.func, ast.Attribute)
            and inner.func.attr == "table"):
        return False
    # 첫 인자가 "system_logs" Constant
    if not inner.args:
        return False
    first_arg = inner.args[0]
    if isinstance(first_arg, ast.Constant) and first_arg.value == "system_logs":
        return True
    return False


def _extract_insert_data_node(insert_call: ast.Call) -> ast.AST | None:
    """`.insert(data)` 의 첫 위치 인자(data) 노드 추출.

    `data` 는 dict literal 일 수도, Name 변수 참조일 수도 있다.
    """
    if not insert_call.args:
        return None
    return insert_call.args[0]


def _find_dict_assignment(tree: ast.AST, var_name: str, before_lineno: int) -> ast.Dict | None:
    """모듈 트리에서 `var_name = {...}` 형태 dict 할당을 찾아 dict 노드 반환.

    `before_lineno` 이전 라인의 가장 최근 할당만 (단순 휴리스틱).
    """
    found: ast.Dict | None = None
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        if node.lineno >= before_lineno:
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == var_name:
                if isinstance(node.value, ast.Dict):
                    found = node.value
    return found


def _dict_has_kst_timestamp(d: ast.Dict) -> tuple[bool, bool]:
    """dict 노드가 `"timestamp"` 키를 포함하고, 값이 KST 표현인지 검사.

    Returns:
        (has_timestamp_key, value_is_kst)
    """
    for key, value in zip(d.keys, d.values):
        if not (isinstance(key, ast.Constant) and key.value == "timestamp"):
            continue
        # value 를 소스로 unparse 한 뒤 정규식 검사
        value_src = ast.unparse(value)
        is_kst = any(pat.search(value_src) for pat in _KST_VALUE_PATTERNS)
        return True, is_kst
    return False, False


def test_all_system_logs_inserts_must_include_kst_timestamp():
    """src/ 전체 `supabase.table("system_logs").insert(...)` 호출은
    timestamp 키 + KST 명시 의무 (사이클 65 hotfix H2 영구 가드).

    검증 대상:
    - `src/db/system_logs.py::write_log` (사이클 65 H2 hotfix 핵심)
    - `src/main.py::_insert_log_to_db` (_DbLogHandler 위임 경로 — 같은 결함)
    - 미래 추가될 다른 호출처도 자동 보호
    """
    src_root = Path("src")
    assert src_root.exists() and src_root.is_dir(), (
        f"src/ 경로 결함: {src_root.resolve()}"
    )

    violations: list[str] = []
    call_count = 0

    for py_file in src_root.rglob("*.py"):
        try:
            source = py_file.read_text(encoding="utf-8")
            tree = ast.parse(source)
        except SyntaxError:
            continue

        for node in ast.walk(tree):
            if not _is_system_logs_insert_call(node):
                continue
            call_count += 1
            data_node = _extract_insert_data_node(node)
            loc = f"{py_file}:L{node.lineno}"

            if data_node is None:
                violations.append(f"{loc} — `.insert(...)` 인자 누락")
                continue

            # data 가 dict literal 인 경우
            if isinstance(data_node, ast.Dict):
                has_ts, is_kst = _dict_has_kst_timestamp(data_node)
                if not has_ts:
                    violations.append(
                        f"{loc} — insert data dict 에 `\"timestamp\"` 키 누락 "
                        f"(DB default UTC 저장 위험 — 사이클 53 KST 컨벤션 위반)"
                    )
                elif not is_kst:
                    violations.append(
                        f"{loc} — `\"timestamp\"` 값이 KST 명시 안 함 "
                        f"(허용: `datetime.now(KST)` 또는 "
                        f"`datetime.now(timezone(timedelta(hours=9)))`)"
                    )
                continue

            # data 가 Name 참조인 경우 — 변수 할당 dict 추적
            if isinstance(data_node, ast.Name):
                assigned_dict = _find_dict_assignment(tree, data_node.id, node.lineno)
                if assigned_dict is None:
                    violations.append(
                        f"{loc} — `.insert({data_node.id})` 변수 할당 dict 추적 실패 "
                        f"(수동 검증 필요)"
                    )
                    continue
                has_ts, is_kst = _dict_has_kst_timestamp(assigned_dict)
                if not has_ts:
                    violations.append(
                        f"{loc} — `{data_node.id}` dict 에 `\"timestamp\"` 키 누락 "
                        f"(DB default UTC 저장 위험)"
                    )
                elif not is_kst:
                    violations.append(
                        f"{loc} — `{data_node.id}[\"timestamp\"]` 값이 KST 명시 안 함"
                    )
                continue

            # 그 외 형태 (lambda 등) — 보수적으로 violation 처리하지 않음
            # (필요 시 후속 사이클에서 확장)

    assert call_count >= 2, (
        f"system_logs INSERT 호출이 {call_count}건만 발견 — 최소 2건 "
        f"(write_log + _insert_log_to_db) 기대. 본 AST 가드 적용 범위 회귀 의심"
    )

    assert not violations, (
        f"system_logs INSERT 호출 {len(violations)}건이 KST timestamp 가드 위반 "
        f"(사이클 65 hotfix H2 영구 가드 / 사이클 53 KST 컨벤션):\n"
        + "\n".join(violations)
    )


def test_write_log_function_uses_kst_timestamp():
    """`src/db/system_logs.py::write_log` 함수 단독 핀포인트 가드.

    위 통합 가드와 중복되지만, write_log 가 메인 진입점이므로
    회귀 시 명확한 원인 추적을 위해 별도 케이스 유지.
    """
    src_path = Path("src/db/system_logs.py")
    assert src_path.exists(), f"system_logs.py 경로 결함: {src_path.resolve()}"
    source = src_path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    write_log_fn: ast.AsyncFunctionDef | None = None
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "write_log":
            write_log_fn = node
            break

    assert write_log_fn is not None, "write_log 비동기 함수 미존재"

    body_src = ast.unparse(write_log_fn)
    # ast.unparse 는 single quote 를 우선 사용 → 'timestamp' 와 "timestamp" 모두 허용
    has_timestamp_key = ("'timestamp'" in body_src) or ('"timestamp"' in body_src)
    assert has_timestamp_key, (
        f"write_log data 에 `timestamp` 키 누락 — 사이클 65 H2 hotfix 위반:\n"
        f"{body_src}"
    )
    assert any(pat.search(body_src) for pat in _KST_VALUE_PATTERNS), (
        f"write_log timestamp 값이 KST 명시 안 함 — 사이클 53 KST 컨벤션 위반:\n"
        f"{body_src}"
    )
