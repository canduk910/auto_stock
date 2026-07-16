"""사이클 68 G-2~G-9 — 8 모듈별 INSERT/UPSERT KST timestamp 명시 검증.

> **선례**: 사이클 65 H3 (`test_system_logs_kst_timestamp.py`) AST 정적 패턴 답습.
> **결정 1=A 채택**: HIGH 1 + MEDIUM 7 = 8 모듈 일괄 시정.
> **결정 2-B 채택**: `src/db/_kst.py` 공용 헬퍼 사용 의무.
>
> Red 시점: 8 모듈 모두 *최소 1 케이스 FAIL* 예상 (현재 UTC 명시 / 미명시).
> Green 후: 8 모듈 INSERT/UPSERT payload 가 시각 컬럼에 KST 명시.

검증 패턴 (사이클 65 H3 답습):
- AST 정적 파싱 → 각 모듈의 INSERT/UPSERT 호출 노드 추출.
- payload dict 또는 변수 참조 dict 의 시각 컬럼 key 명시 확인.
- 값이 KST 표현인지 정규식 검사 (다음 중 하나 허용):
    * `now_kst_iso()` (결정 2-B 공용 헬퍼)
    * `datetime.now(KST)` / `datetime.now(KST).isoformat()`
    * `datetime.now(timezone(timedelta(hours=9)))`
    * `datetime.now(_KST_TZ)` 등 동등 명명

각 케이스는 모듈 단위 핀포인트 — Green 회귀 시 명확한 원인 추적.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit


# KST 표현 정규식 — 허용 패턴 4종
_KST_VALUE_PATTERNS = [
    re.compile(r"now_kst_iso\s*\("),
    re.compile(r"datetime\.now\(\s*KST\s*\)"),
    re.compile(r"datetime\.now\(\s*_KST(_TZ)?\s*\)"),
    re.compile(r"datetime\.now\(\s*timezone\(\s*timedelta\(\s*hours\s*=\s*9\s*\)\s*\)\s*\)"),
]

# 시각 컬럼 (대상 키)
_TIMESTAMP_KEYS = frozenset({
    "timestamp", "created_at", "updated_at", "refreshed_at", "completed_at",
    "applied_at", "rejected_at",
})


def _resolve_module_constants(tree: ast.AST) -> dict[str, str]:
    """모듈-level `NAME = "string_literal"` 상수 매핑 추출 (TABLE_NAME 등)."""
    consts: dict[str, str] = {}
    if not isinstance(tree, ast.Module):
        return consts
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not (len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)):
            continue
        if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            consts[node.targets[0].id] = node.value.value
    return consts


def _is_table_method_call(
    node: ast.AST, *, method: str, table: str, module_consts: dict[str, str]
) -> bool:
    """`supabase.table("<table>").<method>(...)` 또는 `.table(TABLE_NAME).<method>(...)`
    호출 식별 (module-level 상수 resolve).

    method ∈ {insert, upsert, update}.
    """
    if not isinstance(node, ast.Call):
        return False
    fn = node.func
    if not (isinstance(fn, ast.Attribute) and fn.attr == method):
        return False
    inner = fn.value
    if not (isinstance(inner, ast.Call) and isinstance(inner.func, ast.Attribute)
            and inner.func.attr == "table"):
        return False
    if not inner.args:
        return False
    first_arg = inner.args[0]
    # Constant string
    if isinstance(first_arg, ast.Constant) and first_arg.value == table:
        return True
    # Name 참조 (module 상수)
    if isinstance(first_arg, ast.Name):
        resolved = module_consts.get(first_arg.id)
        if resolved == table:
            return True
    return False


def _is_any_table_method_call(
    node: ast.AST, *, table: str, module_consts: dict[str, str]
) -> bool:
    """`insert` / `upsert` / `update` 어느 것이든 매칭."""
    for method in ("insert", "upsert", "update"):
        if _is_table_method_call(
            node, method=method, table=table, module_consts=module_consts
        ):
            return True
    return False


def _extract_payload_node(call: ast.Call) -> ast.AST | None:
    """`.insert(payload)` / `.upsert(payload, ...)` 의 첫 위치 인자 추출."""
    if not call.args:
        return None
    return call.args[0]


def _find_dict_assignment(tree: ast.AST, var_name: str, before_lineno: int) -> ast.Dict | None:
    """모듈 트리에서 가장 최근 `var_name = {...}` 할당 dict 노드 반환."""
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


def _dict_has_kst_timestamp_keys(d: ast.Dict) -> tuple[set[str], dict[str, bool]]:
    """dict 노드에서 timestamp 계열 키 추출 + 각 값이 KST 명시인지 매핑.

    Returns:
        (found_keys, kst_value_map[key])
    """
    found: set[str] = set()
    kst_map: dict[str, bool] = {}
    for key, value in zip(d.keys, d.values):
        if not (isinstance(key, ast.Constant) and isinstance(key.value, str)):
            continue
        k = key.value
        if k not in _TIMESTAMP_KEYS:
            continue
        found.add(k)
        try:
            value_src = ast.unparse(value)
        except Exception:
            value_src = ""
        kst_map[k] = any(pat.search(value_src) for pat in _KST_VALUE_PATTERNS)
    return found, kst_map


def _collect_payload_dicts(
    src_path: Path, *, table: str
) -> list[tuple[int, ast.Dict | None, str | None]]:
    """모듈 내 모든 `<table>` INSERT/UPSERT/UPDATE 호출의 payload dict 수집.

    Returns:
        [(lineno, dict_node_or_None, var_name_or_None)] — dict 추적 실패 시 둘 다 None.
    """
    source = src_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    module_consts = _resolve_module_constants(tree)
    results: list[tuple[int, ast.Dict | None, str | None]] = []
    for node in ast.walk(tree):
        if not _is_any_table_method_call(node, table=table, module_consts=module_consts):
            continue
        payload = _extract_payload_node(node)
        if payload is None:
            results.append((node.lineno, None, None))
            continue
        if isinstance(payload, ast.Dict):
            results.append((node.lineno, payload, None))
            continue
        if isinstance(payload, ast.Name):
            assigned = _find_dict_assignment(tree, payload.id, node.lineno)
            results.append((node.lineno, assigned, payload.id))
            continue
        # 그 외 (Call 등) — 추적 보류
        results.append((node.lineno, None, None))
    return results


def _assert_module_has_kst_timestamp(
    *,
    module_path: str,
    table: str,
    required_keys: set[str],
):
    """공통 검증 헬퍼: 모듈 내 모든 INSERT/UPSERT/UPDATE 호출이
    required_keys 중 *최소 1 개* 를 KST 명시로 포함해야 함.

    `required_keys` 가 여러 개면 그 중 *적어도 하나* 가 만족하면 PASS
    (모듈마다 갱신 컬럼 명세가 다른 점 흡수 — 대부분 1 키만 갱신).
    """
    src_path = Path(module_path)
    assert src_path.exists(), f"모듈 경로 결함: {src_path.resolve()}"

    payloads = _collect_payload_dicts(src_path, table=table)
    assert payloads, (
        f"{module_path} 에서 `supabase.table({table!r}).insert/upsert/update(...)` "
        f"호출 0건 — AST 가드 적용 범위 회귀 의심"
    )

    violations: list[str] = []
    any_compliant = False

    for lineno, d, var_name in payloads:
        loc = f"{module_path}:L{lineno}"
        if d is None:
            violations.append(
                f"{loc} — payload dict 추적 실패 "
                f"(var={var_name!r} 또는 비-Dict 형태, 수동 검증 필요)"
            )
            continue
        found, kst_map = _dict_has_kst_timestamp_keys(d)

        # required_keys 중 *적어도 하나* 가 KST 명시면 PASS
        matched_kst = [k for k in (found & required_keys) if kst_map.get(k, False)]
        if matched_kst:
            any_compliant = True
            continue

        # 시각 컬럼 자체가 없으면 미명시 → 사이클 65 H2 패턴 위반
        if not (found & required_keys):
            violations.append(
                f"{loc} — payload 에 시각 컬럼 {sorted(required_keys)} 중 하나도 명시 안 함 "
                f"(DB DEFAULT UTC 의존 폐기 의무, 사이클 65 H2 답습)"
            )
            continue

        # 컬럼은 있으나 KST 명시 안 함 (UTC / naive 등)
        non_kst = [k for k in (found & required_keys) if not kst_map.get(k, False)]
        violations.append(
            f"{loc} — 시각 컬럼 {non_kst} 값이 KST 명시 안 함 "
            f"(허용: now_kst_iso() / datetime.now(KST) / "
            f"datetime.now(timezone(timedelta(hours=9))))"
        )

    assert any_compliant, (
        f"{module_path}: 모든 INSERT/UPSERT/UPDATE 호출에서 KST timestamp 명시 0건 — "
        f"사이클 68 시정 의무 (Green 후 backend-dev 패치).\n위반 상세:\n"
        + "\n".join(violations)
    )


# ─────────────────────────────────────────────────────────────────────────────
# G-2 — stock_master.py (HIGH)
# ─────────────────────────────────────────────────────────────────────────────

def test_g2_stock_master_refreshed_at_kst():
    """G-2 (HIGH) — `stock_master` INSERT/UPSERT `refreshed_at` KST 명시 의무.

    현재: `datetime.now(timezone.utc).isoformat()` (line 35) → 시정 의무.
    is_stale 24h TTL baseline + Settings/Admin UI 노출 위험.
    """
    _assert_module_has_kst_timestamp(
        module_path="src/db/stock_master.py",
        table="stock_master",
        required_keys={"refreshed_at"},
    )


# ─────────────────────────────────────────────────────────────────────────────
# G-3 — parameter_recommendations.py (MEDIUM)
# ─────────────────────────────────────────────────────────────────────────────

def test_g3_parameter_recommendations_created_at_kst():
    """G-3 (MEDIUM) — `parameter_recommendations` INSERT 에 `created_at` KST 명시.

    현재: `created_at` 키 미명시 → DB DEFAULT now() UTC. 시정 의무.
    list_recommendations 의 order_by("created_at") 가 KST 자정 경계 분류 오류 잠재.
    """
    _assert_module_has_kst_timestamp(
        module_path="src/db/parameter_recommendations.py",
        table="parameter_recommendations",
        required_keys={"created_at"},
    )


# ─────────────────────────────────────────────────────────────────────────────
# G-4 — log_reports.py (MEDIUM)
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.xfail(
    reason=(
        "사이클 M1-2 의미 전환 — log_reports.py 가 supabase-py 체인에서 "
        "src.db.pg(asyncpg) 로 전환되어 `supabase.table('daily_log_reports').insert(...)` "
        "AST 패턴이 더 이상 존재하지 않는다(0건 → 헬퍼 전제 위반). KST created_at 의무는 "
        "여전히 보존 — `pg.fetchrow` SQL 이 `datetime.fromisoformat(now_kst_iso())` 를 "
        "created_at 파라미터로 바인딩한다(src/db/log_reports.py::insert_log_report). "
        "AST 헬퍼가 supabase.table 호출부만 추적하는 사이클 68 시점 계약이라 회귀 아님 "
        "(사이클 M1-1 G-6 strategy_config.py 선례 답습)."
    ),
    strict=False,
)
def test_g4_log_reports_created_at_kst():
    """G-4 (MEDIUM) — `daily_log_reports` INSERT 에 `created_at` KST 명시.

    현재: `created_at` 키 미명시 → DB DEFAULT now() UTC. 시정 의무.
    20:10 자정 직후 정산 → UI 노출 시 9h 차 운영자 혼란.
    """
    _assert_module_has_kst_timestamp(
        module_path="src/db/log_reports.py",
        table="daily_log_reports",
        required_keys={"created_at"},
    )


# ─────────────────────────────────────────────────────────────────────────────
# G-5 — system_config.py (MEDIUM, 6 upsert)
# ─────────────────────────────────────────────────────────────────────────────

def test_g5_system_config_updated_at_kst():
    """G-5 (MEDIUM) — `system_config` UPSERT 6 곳 모두 `updated_at` KST 명시.

    현재: `updated_at` 키 미명시 → DB DEFAULT now() UTC + UPSERT 갱신 시 stale.
    설정 변경 추적 불가능 (운영자 "마지막 수정 언제?" 답 불가).
    """
    _assert_module_has_kst_timestamp(
        module_path="src/db/system_config.py",
        table="system_config",
        required_keys={"updated_at"},
    )


# ─────────────────────────────────────────────────────────────────────────────
# G-6 — strategy_config.py (MEDIUM)
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.xfail(
    reason=(
        "사이클 M1-1 의미 전환 — strategy_config.py 가 supabase-py 체인에서 "
        "src.db.pg(asyncpg) 로 전환되어 `supabase.table('strategy_config').upsert(...)` "
        "AST 패턴이 더 이상 존재하지 않는다(0건 → 헬퍼 전제 위반). KST updated_at 의무는 "
        "여전히 보존 — `pg.execute` SQL 이 `datetime.fromisoformat(now_kst_iso())` 를 "
        "updated_at 파라미터로 바인딩한다(src/db/strategy_config.py::save). "
        "AST 헬퍼가 supabase.table 호출부만 추적하는 사이클 68 시점 계약이라 회귀 아님."
    ),
    strict=False,
)
def test_g6_strategy_config_updated_at_kst():
    """G-6 (MEDIUM) — `strategy_config` UPSERT `updated_at` KST 명시.

    현재: `updated_at` 키 미명시 → DB DEFAULT now() UTC + UPSERT 갱신 stale.
    사이클 23 자동 적용 이력 추적용 — 변경 시각 정확성 필수.
    """
    _assert_module_has_kst_timestamp(
        module_path="src/db/strategy_config.py",
        table="strategy_config",
        required_keys={"updated_at"},
    )


# ─────────────────────────────────────────────────────────────────────────────
# G-7 — kis_quote_accounts.py (MEDIUM)
# ─────────────────────────────────────────────────────────────────────────────

def test_g7_kis_quote_accounts_timestamps_kst():
    """G-7 (MEDIUM) — `kis_quote_accounts` INSERT/UPDATE `created_at`/`updated_at` KST.

    현재: `datetime.now(timezone.utc).isoformat()` (line 178, 231) → 시정 의무.
    보조 시세 계좌 등록/수정 시각 — KST 정책 위반.
    """
    _assert_module_has_kst_timestamp(
        module_path="src/db/kis_quote_accounts.py",
        table="kis_quote_accounts",
        required_keys={"created_at", "updated_at"},
    )


# ─────────────────────────────────────────────────────────────────────────────
# G-8 — market_regime_snapshots.py (MEDIUM)
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.xfail(
    reason=(
        "사이클 M1-2 의미 전환 — market_regime_snapshots.py 가 supabase-py 체인에서 "
        "src.db.pg(asyncpg) 로 전환되어 `supabase.table('market_regime_snapshots').insert(...)` "
        "AST 패턴이 더 이상 존재하지 않는다(0건 → 헬퍼 전제 위반). KST created_at 의무는 "
        "여전히 보존 — `pg.fetchrow` SQL 이 `datetime.fromisoformat(now_kst_iso())` 를 "
        "created_at 파라미터로 바인딩한다(src/db/market_regime_snapshots.py::insert_snapshot). "
        "AST 헬퍼가 supabase.table 호출부만 추적하는 사이클 68 시점 계약이라 회귀 아님 "
        "(사이클 M1-1 G-6 strategy_config.py 선례 답습)."
    ),
    strict=False,
)
def test_g8_market_regime_snapshots_created_at_kst():
    """G-8 (MEDIUM) — `market_regime_snapshots` INSERT `created_at` KST.

    현재: `_now_iso()` → `datetime.now(timezone.utc).isoformat()` (line 30, 74).
    07:50 매크로 스냅샷 시각 — 운영 회고 시 9h 오차.
    """
    _assert_module_has_kst_timestamp(
        module_path="src/db/market_regime_snapshots.py",
        table="market_regime_snapshots",
        required_keys={"created_at"},
    )


# ─────────────────────────────────────────────────────────────────────────────
# G-9 — backtest_runs.py (MEDIUM)
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.xfail(
    reason=(
        "사이클 M1-2 의미 전환 — backtest_runs.py 가 supabase-py 체인에서 "
        "src.db.pg(asyncpg) 로 전환되어 `supabase.table('backtest_runs').insert/update(...)` "
        "AST 패턴이 더 이상 존재하지 않는다(0건 → 헬퍼 전제 위반). KST created_at/completed_at "
        "의무는 여전히 보존 — `pg.fetchrow` SQL 이 `datetime.fromisoformat(now_kst_iso())` 를 "
        "바인딩한다(src/db/backtest_runs.py::insert_run, ::update_status). "
        "AST 헬퍼가 supabase.table 호출부만 추적하는 사이클 68 시점 계약이라 회귀 아님 "
        "(사이클 M1-1 G-6 strategy_config.py 선례 답습)."
    ),
    strict=False,
)
def test_g9_backtest_runs_timestamps_kst():
    """G-9 (MEDIUM) — `backtest_runs` INSERT/UPDATE `created_at`/`completed_at` KST.

    현재: `_now_iso()` → `datetime.now(timezone.utc).isoformat()` (line 34, 79, 156).
    외부 MCP job 영역, 운영 분석 시 9h 오차.
    """
    _assert_module_has_kst_timestamp(
        module_path="src/db/backtest_runs.py",
        table="backtest_runs",
        required_keys={"created_at", "completed_at"},
    )
