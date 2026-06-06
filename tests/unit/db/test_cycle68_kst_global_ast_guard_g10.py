"""사이클 68 G-10 — `src/` 전체 rglob AST 정적 가드 (결정 3-B).

> **선례**: 사이클 65 H3 (`test_system_logs_kst_timestamp.py`) 답습 + 범위 확장.
> **결정 3-B 채택**: `src/` 전체 rglob (`src/main.py::_insert_log_to_db` 같은
>   위임 경로 포함 — 사이클 65 H2-bis 패턴).
>
> Red 시점:
>   - G-10a: `datetime.utcnow()` 호출 검색 → 현재 0건이면 PASS, 1건이라도 있으면 FAIL.
>   - G-10b: `src/db/*.py` payload 영역에 `datetime.now(timezone.utc)` 호출 검색 →
>     현재 6+건 (stock_master / kis_quote_accounts / market_regime_snapshots /
>     backtest_runs `_now_iso` 등) → **FAIL** 의무.
>
> Green 후: backend-dev 가 8 모듈 일괄 시정 → G-10b PASS.

목적: 향후 silent 결함 영구 차단 + 사이클 65 H2-bis 패턴 (위임 경로) 보호.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit


# 본 가드 적용 예외 파일 (테스트 자체 / 호환 layer / KST 비교 baseline 등)
_G10_EXEMPT_FILES: frozenset[str] = frozenset({
    # 향후 예외 추가 시 명시 — 현 사이클 68 = 0건 예외
})


def _is_exempt(rel_path: Path) -> bool:
    return str(rel_path) in _G10_EXEMPT_FILES


def test_g10a_no_utcnow_in_src():
    """G-10a — `src/` 전체에 `datetime.utcnow()` 사용 0건 의무.

    Python 3.12 `datetime.utcnow()` deprecation 대비 + naive datetime 영구 차단.
    현재: `grep -rn 'datetime\\.utcnow' src/` 결과 0건이면 PASS (검증 가드).
    """
    src_root = Path("src")
    assert src_root.exists(), f"src/ 경로 결함: {src_root.resolve()}"

    pattern = re.compile(r"\bdatetime\.utcnow\s*\(")
    violations: list[str] = []

    for py_file in src_root.rglob("*.py"):
        rel = py_file.relative_to(src_root)
        if _is_exempt(rel):
            continue
        try:
            source = py_file.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for lineno, line in enumerate(source.splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if pattern.search(line):
                violations.append(f"{rel}:L{lineno} — {stripped}")

    assert not violations, (
        f"`datetime.utcnow()` 사용 금지 — naive UTC 결함 영구 차단 의무. "
        f"위반 {len(violations)}건:\n" + "\n".join(violations)
    )


def test_g10b_no_utc_aware_in_db_insert_payload():
    """G-10b — `src/db/*.py` INSERT/UPSERT payload 영역에
    `datetime.now(timezone.utc)` 호출 0건 의무.

    현재 6+건 잔존 — 사이클 68 시정 의무 가시화 (Green 후 PASS 전환):
    - src/db/stock_master.py:35   `_to_row::refreshed_at`
    - src/db/kis_quote_accounts.py:178  `insert_account::created_at/updated_at`
    - src/db/kis_quote_accounts.py:231  `update_account::updated_at`
    - src/db/market_regime_snapshots.py:30  `_now_iso`
    - src/db/backtest_runs.py:34  `_now_iso`

    검증 방식: `src/db/*.py` 의 module-level + function-level 에서 `datetime.now(...)`
    호출이 `timezone.utc` 인자를 받는 경우 위반. AST 기반.

    예외: `src/db/*.py` 내 *조회 영역* 또는 *비교 영역* (e.g. `stock_master.is_stale`
    내부 `datetime.now(timezone.utc) - refreshed_at` 비교) 은 본 가드 대상 외.
    → G-11 별도 가드 (`stock_master.is_stale` KST 비교 통일).
    본 G-10b 는 *INSERT/UPSERT/UPDATE 호출 인접* `datetime.now(timezone.utc)` 만 검출.
    """
    src_db_root = Path("src/db")
    assert src_db_root.exists(), f"src/db/ 경로 결함: {src_db_root.resolve()}"

    violations: list[str] = []
    files_scanned = 0

    for py_file in src_db_root.rglob("*.py"):
        if py_file.name == "__init__.py":
            continue
        rel = py_file.relative_to(Path("src"))
        if _is_exempt(rel):
            continue
        files_scanned += 1
        try:
            source = py_file.read_text(encoding="utf-8")
            tree = ast.parse(source)
        except (UnicodeDecodeError, SyntaxError):
            continue

        # 함수 단위 분석 — INSERT/UPSERT/UPDATE 호출이 함수 안에 있는 경우,
        # 같은 함수 안에 `datetime.now(timezone.utc)` 호출이 있으면 위반.
        # 또한 module-level helper (`_now_iso` 등) 도 검출.
        for func_node in ast.walk(tree):
            if not isinstance(func_node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            # 함수 내부에 supabase.table(...).insert/upsert/update 호출이 있는가?
            has_dml = False
            for n in ast.walk(func_node):
                if not isinstance(n, ast.Call):
                    continue
                fn = n.func
                if not (isinstance(fn, ast.Attribute)
                        and fn.attr in ("insert", "upsert", "update")):
                    continue
                inner = fn.value
                if (isinstance(inner, ast.Call) and isinstance(inner.func, ast.Attribute)
                        and inner.func.attr == "table"):
                    has_dml = True
                    break

            # `_now_iso` 류 helper 도 검사 대상 (반환값이 payload 에 쓰임)
            is_now_helper = func_node.name in (
                "_now_iso", "_now_kst_iso", "_to_row",
            )

            if not (has_dml or is_now_helper):
                continue

            # 함수 내부에서 datetime.now(timezone.utc) 호출 검출
            for n in ast.walk(func_node):
                if not isinstance(n, ast.Call):
                    continue
                fn = n.func
                if not (isinstance(fn, ast.Attribute) and fn.attr == "now"):
                    continue
                inner_val = fn.value
                if not (isinstance(inner_val, ast.Name) and inner_val.id == "datetime"):
                    continue
                # 인자 검사 — timezone.utc 면 위반
                for arg in n.args:
                    try:
                        arg_src = ast.unparse(arg)
                    except Exception:
                        arg_src = ""
                    if re.search(r"\btimezone\.utc\b", arg_src):
                        violations.append(
                            f"{rel}:L{n.lineno} — `{func_node.name}()` 내 "
                            f"`datetime.now(timezone.utc)` (INSERT/UPSERT payload 의존, "
                            f"사이클 68 시정 의무 — KST 로 교체)"
                        )

    assert files_scanned > 0, "src/db/ 스캔 파일 0건 — 가드 적용 범위 회귀 의심"
    assert not violations, (
        f"DB INSERT/UPSERT payload 영역 `datetime.now(timezone.utc)` "
        f"사용 금지 — 사이클 68 시정 의무 (Green 후 backend-dev 패치).\n"
        f"위반 {len(violations)}건:\n" + "\n".join(violations)
    )
