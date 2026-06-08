"""사이클 78 G-AST1 — AST 영구 가드: `record_*` collector 도입 시 `flush_*` 호출 사이트 의무.

미래 신규 collector 추가 시 flush 호출 사이트 누락 silent 결함 영구 차단.

Red 단계: `record_swing_rest_poll` / `record_stale_watcher_check` 정의된 모듈에서
정의된 `flush_*` 함수의 호출 사이트가 `src/engine/scheduler.py` 어디에도 없으면 FAIL.

Green 단계: backend-dev 가 호출 사이트 (5분 주기 task + lifecycle hook) 추가 후 PASS.

검증 규칙:
- `flush_swing_rest_poll_collector` (`src/engine/scheduler.py` 정의) 의 호출 사이트
  `src/engine/scheduler.py` 어디에 ≥ 1건 존재
- `flush_stale_watcher_collector` (`src/engine/stale_watcher_core.py` 정의) 의 호출 사이트
  `src/engine/scheduler.py` 어디에 ≥ 1건 존재

영속 의무:
- 사이클 72/73/74/75/76 AST 패턴 답습 (AST 기반 정적 검증)
- 사이클 17 KIS LMS chain / 사이클 38 명문화 / 매매 안전성 영향 0
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit


_SRC_ROOT = Path(__file__).resolve().parents[3] / "src"
_SCHEDULER_PY = _SRC_ROOT / "engine" / "scheduler.py"
_STALE_WATCHER_CORE_PY = _SRC_ROOT / "engine" / "stale_watcher_core.py"


def _has_function_def(source: str, name: str) -> bool:
    """`source` 모듈에 `name` 함수 정의 존재 여부."""
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
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
# G-AST1: record_* 도입 모듈의 flush_* 호출 사이트 ≥ 1건 영구 가드
# ===========================================================================
def test_g_ast1_record_collector_requires_flush_call_site():
    """G-AST1: `record_*` collector 정의된 모듈에서 대응 `flush_*` 함수의 호출 사이트
    `src/engine/scheduler.py` 어디에 ≥ 1건 존재 (영구 가드, 미래 신규 collector 차단).

    검증 매트릭스:
    - `record_swing_rest_poll` 정의 (scheduler.py) → `flush_swing_rest_poll_collector`
      호출 사이트 (scheduler.py) ≥ 1건
    - `record_stale_watcher_check` 정의 (stale_watcher_core.py) → `flush_stale_watcher_collector`
      호출 사이트 (scheduler.py) ≥ 1건

    Red: 호출 사이트 0건 → FAIL
    Green: ≥ 1건 → PASS
    """
    scheduler_source = _SCHEDULER_PY.read_text(encoding="utf-8")
    stale_source = _STALE_WATCHER_CORE_PY.read_text(encoding="utf-8")

    # 사전 조건: record/flush 함수 정의 존재 확인 (사이클 74 영속)
    assert _has_function_def(scheduler_source, "record_swing_rest_poll"), (
        "G-AST1 사전조건: `record_swing_rest_poll` 함수 정의 (scheduler.py) 미존재 — "
        "사이클 74 영속 영역 침범"
    )
    assert _has_function_def(scheduler_source, "flush_swing_rest_poll_collector"), (
        "G-AST1 사전조건: `flush_swing_rest_poll_collector` 함수 정의 (scheduler.py) 미존재"
    )
    assert _has_function_def(stale_source, "record_stale_watcher_check"), (
        "G-AST1 사전조건: `record_stale_watcher_check` 함수 정의 (stale_watcher_core.py) 미존재"
    )
    assert _has_function_def(stale_source, "flush_stale_watcher_collector"), (
        "G-AST1 사전조건: `flush_stale_watcher_collector` 함수 정의 (stale_watcher_core.py) 미존재"
    )

    # 본 가드: scheduler.py 모듈 어디에서든 flush 호출 사이트 ≥ 1건
    swing_flush_calls = _count_calls_to(scheduler_source, "flush_swing_rest_poll_collector")
    stale_flush_calls = _count_calls_to(scheduler_source, "flush_stale_watcher_collector")

    missing: list[str] = []
    if swing_flush_calls < 1:
        missing.append(
            f"  - `flush_swing_rest_poll_collector` 호출 사이트 (scheduler.py): "
            f"{swing_flush_calls} 건 (≥ 1 필요)"
        )
    if stale_flush_calls < 1:
        missing.append(
            f"  - `flush_stale_watcher_collector` 호출 사이트 (scheduler.py): "
            f"{stale_flush_calls} 건 (≥ 1 필요)"
        )

    assert not missing, (
        f"\n사이클 78 G-AST1 위반 — `record_*` collector 도입된 모듈의 대응 `flush_*` "
        f"호출 사이트 누락 (silent 메모리 leak 결함):\n"
        + "\n".join(missing)
        + "\n\n  사이클 74 commit (0017fe0) = record/flush 함수 정의 완료\n"
        f"  사이클 78 silent 결함 = 호출 사이트 도입 누락\n"
        f"  메모리 leak: swing 720 + stale 360 = 1,080 dict / day 누적\n\n"
        f"  시정 옵션 1 (권고): `_api_recovered_collector_loop` 본체에 추가:\n"
        f"    from src.engine.stale_watcher_core import flush_stale_watcher_collector\n"
        f"    try: flush_swing_rest_poll_collector()\n"
        f"    except: logger.exception(...)\n"
        f"    try: flush_stale_watcher_collector()\n"
        f"    except: logger.exception(...)\n\n"
        f"  영구 가드 — 미래 신규 `record_*` collector 추가 시 대응 `flush_*` 호출 사이트 누락 "
        f"silent 결함 즉시 FAIL."
    )
