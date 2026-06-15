"""사이클 89 L-1 (G-AST1) — AST 영구 가드: `record_universe_refresh` 도입 시 `flush_universe_collector` 호출 사이트 의무.

사이클 78 G-AST1 패턴 직답습. 미래 신규 collector 추가 시 flush 호출 사이트 누락 silent
결함 영구 차단.

Red 단계: `record_universe_refresh` 정의된 모듈에서 `flush_universe_collector` 함수의
호출 사이트가 `src/engine/scheduler.py` 또는 `src/engine/scanner.py` 어디에도 없으면 FAIL.

Green 단계: backend-dev 가 호출 사이트 (개장 전 task body + lifecycle hook) 추가 후 PASS.

검증 규칙:
- `flush_universe_collector` (`src/engine/stock_master_metrics.py` 정의) 의 호출 사이트
  `src/engine/scheduler.py` 또는 `src/engine/scanner.py` 어디에 ≥ 1건 존재

영속 의무:
- 사이클 78 G-AST1 패턴 답습 (AST 기반 정적 검증)
- 사이클 74 collector 패턴 답습
- 매매 안전성 영향 0 (로깅 영역 정적 검증만)
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit


_SRC_ROOT = Path(__file__).resolve().parents[3] / "src"
_SCHEDULER_PY = _SRC_ROOT / "engine" / "scheduler.py"
_SCANNER_PY = _SRC_ROOT / "engine" / "scanner.py"
_STOCK_MASTER_METRICS_PY = _SRC_ROOT / "engine" / "stock_master_metrics.py"


def _has_function_def(source: str, name: str) -> bool:
    """`source` 모듈에 `name` 함수 정의 OR 모듈-레벨 export 존재 여부.

    사이클 133 의미 전환 (카드 #24 — refactor-review 권고 채택) — 사이클 66 K-2 패턴 답습:
    - Red 시점 (사이클 89) = `def name(...)` 또는 `async def name(...)` 함수 정의
    - Green 시점 (사이클 133) = `make_metrics_collector` 팩토리 반환값을 모듈-레벨 tuple unpacking 으로 할당 영속.
      예: `(record_universe_refresh, flush_universe_collector, _collector) = make_metrics_collector(...)`.
    - 핵심 의도 보존: 모듈-레벨에서 `name` 영역 영속 (정의 또는 export 영속).
    """
    tree = ast.parse(source)
    for node in ast.walk(tree):
        # 패턴 1 (사이클 89 Red 시점) — 함수 정의
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return True
        # 패턴 2 (사이클 133 Green 시점) — 모듈-레벨 Assign 영역 tuple unpacking 또는 단일 할당
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


def _count_calls_to(source: str, name: str) -> int:
    """`source` 모듈 전체에서 `name(...)` 호출 사이트 개수.

    매칭: `name(...)` 단순 호출 + `module.name(...)` 속성 호출
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


# ===========================================================================
# L-1 (G-AST1): record_universe_refresh 도입 모듈의 flush_universe_collector
#                호출 사이트 ≥ 1건 영구 가드 (사이클 78 답습)
# ===========================================================================
def test_l1_record_universe_refresh_requires_flush_call_site():
    """L-1 (G-AST1): `record_universe_refresh` collector 정의된 모듈에서 대응
    `flush_universe_collector` 함수의 호출 사이트 `src/engine/scheduler.py` 또는
    `src/engine/scanner.py` 어디에 ≥ 1건 존재 (영구 가드, 미래 신규 collector 차단).

    검증 매트릭스:
    - `src/engine/stock_master_metrics.py` 모듈 존재 (Red 사전조건)
    - `record_universe_refresh` 정의 (stock_master_metrics.py)
    - `flush_universe_collector` 정의 (stock_master_metrics.py)
    - `flush_universe_collector` 호출 사이트 (scheduler.py 또는 scanner.py) ≥ 1건

    Red: 모듈 부재 또는 호출 사이트 0건 → FAIL
    Green: ≥ 1건 → PASS

    영속 의무:
    - 사이클 78 G-AST1 패턴 답습 (record/flush 페어링)
    - 사이클 74 collector 패턴 답습
    - 매매 안전성 영역 0
    """
    # 사전조건 1: stock_master_metrics.py 모듈 존재
    if not _STOCK_MASTER_METRICS_PY.exists():
        pytest.fail(
            "\n사이클 89 L-1 (G-AST1) Red 상태 — `src/engine/stock_master_metrics.py` "
            "모듈 부재:\n"
            "  Green (사이클 90): backend-dev 가 신규 모듈 도입 의무.\n"
            "  - 사이클 74 collector 패턴 답습\n"
            "  - record_universe_refresh + flush_universe_collector 정의"
        )

    metrics_source = _STOCK_MASTER_METRICS_PY.read_text(encoding="utf-8")

    # 사전조건 2: record/flush 함수 정의 존재
    assert _has_function_def(metrics_source, "record_universe_refresh"), (
        "L-1 (G-AST1) 사전조건: `record_universe_refresh` 함수 정의 "
        "(stock_master_metrics.py) 미존재 — 사이클 89 시정 영역 침범"
    )
    assert _has_function_def(metrics_source, "flush_universe_collector"), (
        "L-1 (G-AST1) 사전조건: `flush_universe_collector` 함수 정의 "
        "(stock_master_metrics.py) 미존재 — 사이클 89 시정 영역 침범"
    )

    # 본 가드: scheduler.py 또는 scanner.py 어디에서든 flush 호출 사이트 ≥ 1건
    scheduler_source = _SCHEDULER_PY.read_text(encoding="utf-8")
    scanner_source = _SCANNER_PY.read_text(encoding="utf-8")
    scheduler_flush_calls = _count_calls_to(scheduler_source, "flush_universe_collector")
    scanner_flush_calls = _count_calls_to(scanner_source, "flush_universe_collector")
    total_calls = scheduler_flush_calls + scanner_flush_calls

    assert total_calls >= 1, (
        f"\n사이클 89 L-1 (G-AST1) 위반 — `record_universe_refresh` collector 도입된 "
        f"모듈의 대응 `flush_universe_collector` 호출 사이트 누락 (silent 메모리 leak 결함):\n"
        f"  - scheduler.py 호출 사이트: {scheduler_flush_calls} 건\n"
        f"  - scanner.py 호출 사이트: {scanner_flush_calls} 건\n"
        f"  - 합계: {total_calls} 건 (≥ 1 필요)\n\n"
        f"  사이클 78 G-AST1 패턴 답습 — `record_*` 도입 시 `flush_*` 호출 사이트 의무\n\n"
        f"  시정 옵션 (권고):\n"
        f"  1) `_universe_eager_refresh_loop` 본체 (개장 전 task) 에 flush 호출\n"
        f"  2) `_api_recovered_collector_loop` 본체 (사이클 76/78 영속) 에 flush 호출\n"
        f"  3) `stop()` lifecycle hook 마지막 flush 1회 (사이클 78 답습)\n\n"
        f"  영구 가드 — 미래 신규 `record_*` collector 추가 시 대응 `flush_*` 호출 사이트 "
        f"누락 silent 결함 즉시 FAIL."
    )
