"""사이클 79 Red — `stop()` task cancel 목록에 `_api_recovered_collector_task` 포함 검증.

명세 (`_workspace/red/cycle79_task_cancel_guard.md`):

사이클 78 부차 발견 (commit `e03a13b` 보고서 인용):
> "stop() task cancel 목록 (L860~865) 에 _api_recovered_collector_task 가 여전히
> 누락되어 있습니다. ... 운영 중 _running = False → loop 종료 → task 자연 종료가
> 보장되므로 즉각 위험은 낮습니다."

근본 원인:
- 사이클 76 commit (`0d633a8`) = `_api_recovered_collector_task = asyncio.create_task(
  self._api_recovered_collector_loop())` 도입 (L486~488) 했으나 `stop()` cancel
  목록 (L860~865) 추가 누락.
- `finally` 블록 (L737~742, `run_daily` 비정상 종료 경로) 도 동일 누락.
- 즉각 위험 낮음 (`_running=False` 시 loop 자연 종료) — 그러나 영구 가드 도입으로
  *미래 silent 결함* 영구 차단 (사이클 42 `_heartbeat_metrics_loop` 좀비 task 패턴
  답습).

기대 동작 (Green):
- `stop()` 의 task cancel 목록에 `_api_recovered_collector_task` 추가:
  - `task.cancel()` 호출 ≥ 1건
  - `await self._api_recovered_collector_task` (cancel 후 정리) ≥ 1건

Red 단계:
- 현재 `stop()` 의 `task_attrs` 튜플 (L860~865) 에 `_api_recovered_collector_task` 미존재
  → 정적 grep `_api_recovered_collector_task` 호출/포함 사이트 0건 → G-CC1/G-CC2 FAIL.

안전 가드 (CLAUDE.md):
- WebSocket 4중 안전망 호출 시점/횟수 0
- 매도 안전성 / 사이클 38 명문화 / 사이클 17 KIS LMS chain 영향 0
- 운영 영향 0 (lifecycle 영역 정리만, 매매 hot path 무관)
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit


_SCHEDULER_PY = (
    Path(__file__).resolve().parents[3] / "src" / "engine" / "scheduler.py"
)

_COLLECTOR_TASK_ATTR = "_api_recovered_collector_task"


def _get_stop_function_source() -> str:
    """`src/engine/scheduler.py::TradingScheduler.stop` 함수 본문 소스 반환."""
    source = _SCHEDULER_PY.read_text(encoding="utf-8")
    tree = ast.parse(source)
    for cls in ast.walk(tree):
        if not isinstance(cls, ast.ClassDef) or cls.name != "TradingScheduler":
            continue
        for fn in cls.body:
            if (
                isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef))
                and fn.name == "stop"
            ):
                return ast.unparse(fn)
    raise AssertionError("TradingScheduler.stop 함수 정의 미발견")


# ===========================================================================
# G-CC1: `stop()` 본문에 `_api_recovered_collector_task` 포함 (cancel 대상)
# ===========================================================================
def test_g_cc1_stop_includes_api_recovered_collector_task_for_cancel():
    """G-CC1: `stop()` 함수 본문에 `_api_recovered_collector_task` 참조 ≥ 1건.

    검증: `stop()` 함수 본문 (AST unparse) 에 `_api_recovered_collector_task`
    이름 등장 ≥ 1건. 사이클 13-E-1 패턴 (task_attrs 튜플) 답습 시 자연 충족.

    Red: 현재 `stop()` task_attrs 튜플 (L860~865) 에 `_api_recovered_collector_task`
    없음 → 본문 grep 0건 → FAIL.

    Green: backend-dev 가 `task_attrs` 튜플에 `_api_recovered_collector_task` 추가
    → grep ≥ 1건 → PASS.
    """
    stop_source = _get_stop_function_source()
    occurrences = stop_source.count(_COLLECTOR_TASK_ATTR)

    assert occurrences >= 1, (
        f"\n사이클 79 G-CC1 위반 — `stop()` 함수 본문에 "
        f"`{_COLLECTOR_TASK_ATTR}` 참조 0건:\n"
        f"  현재 등장 횟수: {occurrences} (≥ 1 필요)\n\n"
        f"  사이클 76 commit (0d633a8) = `{_COLLECTOR_TASK_ATTR}` 도입 (L486~488)\n"
        f"  사이클 78 부차 발견 = `stop()` cancel 목록 (L860~865) 추가 누락\n\n"
        f"  시정 (Green): `stop()` 의 `task_attrs` 튜플에 항목 추가:\n"
        f"    for task_attr in (\n"
        f"        ..., \"_api_recovered_collector_task\",  # 사이클 79 추가\n"
        f"    ):\n\n"
        f"  사이클 42 `_heartbeat_metrics_loop` 좀비 task 패턴 답습 (영구 가드)."
    )


# ===========================================================================
# G-CC2: `stop()` 본문에 `_api_recovered_collector_task` cancel + await 정리 호출
# ===========================================================================
def test_g_cc2_stop_cancels_and_awaits_api_recovered_collector_task():
    """G-CC2: `stop()` 본문이 `_api_recovered_collector_task` 를 task_attrs 튜플
    (사이클 13-E-1 통합 루프) 에 포함 → 자동으로 cancel() + await + setattr None.

    검증 매트릭스:
    - `stop()` 함수 본문 AST 분석에서 `task_attr in (...)` 튜플 내에 문자열
      리터럴 `"_api_recovered_collector_task"` 포함 ≥ 1건.
    - 사이클 13-E-1 통합 루프 답습이 강제됨 (별도 cancel/await 블록 분기 금지).

    Red: 현재 `task_attrs` 튜플에 미포함 → 0건 → FAIL.

    Green: backend-dev 가 `task_attrs` 튜플에 추가 → ≥ 1건 → PASS.
    """
    source = _SCHEDULER_PY.read_text(encoding="utf-8")
    tree = ast.parse(source)

    # TradingScheduler.stop 함수의 for-loop 의 iter 가 튜플인 경우 그 안에서
    # `"_api_recovered_collector_task"` 문자열 상수를 찾는다.
    found_in_tuple = False
    for cls in ast.walk(tree):
        if not isinstance(cls, ast.ClassDef) or cls.name != "TradingScheduler":
            continue
        for fn in cls.body:
            if (
                not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef))
                or fn.name != "stop"
            ):
                continue
            for node in ast.walk(fn):
                if not isinstance(node, ast.For):
                    continue
                iter_node = node.iter
                if not isinstance(iter_node, ast.Tuple):
                    continue
                for elt in iter_node.elts:
                    if (
                        isinstance(elt, ast.Constant)
                        and isinstance(elt.value, str)
                        and elt.value == _COLLECTOR_TASK_ATTR
                    ):
                        found_in_tuple = True
                        break
                if found_in_tuple:
                    break
            break

    assert found_in_tuple, (
        f"\n사이클 79 G-CC2 위반 — `stop()` 의 `task_attr in (...)` 튜플에 "
        f"`\"{_COLLECTOR_TASK_ATTR}\"` 문자열 리터럴 미포함:\n\n"
        f"  사이클 13-E-1 통합 루프 패턴 (cancel + await + setattr None) 답습 필수.\n"
        f"  별도 cancel/await 블록 분기 금지 (DRY + 회귀 가드 단일 진입점).\n\n"
        f"  시정 (Green):\n"
        f"    async def stop(self) -> None:\n"
        f"        ...\n"
        f"        for task_attr in (\n"
        f"            \"_next_day_task\", \"_session_task\", \"_stale_watcher_task\",\n"
        f"            \"_session_health_task\",\n"
        f"            \"_swing_poll_task\", \"_swing_rest_poll_task\",\n"
        f"            \"_5xx_dedupe_summary_task\",\n"
        f"            \"_api_recovered_collector_task\",  # 사이클 79 추가\n"
        f"            \"_ws_task\", \"_scan_task\",\n"
        f"        ):\n"
        f"            task = getattr(self, task_attr, None)\n"
        f"            if task and not task.done():\n"
        f"                task.cancel()\n"
        f"                try: await task\n"
        f"                except (asyncio.CancelledError, Exception): pass\n"
        f"            setattr(self, task_attr, None)\n\n"
        f"  사이클 42 좀비 task 패턴 영속."
    )


# ===========================================================================
# G-CC3 (참고): `finally` 블록 (비정상 종료 경로) 동일 검증
# ===========================================================================
def test_g_cc3_finally_block_includes_api_recovered_collector_task():
    """G-CC3: `run_daily` 의 `finally` 블록 (L737~742) 도 동일하게
    `_api_recovered_collector_task` 를 task_attrs 튜플에 포함해야 한다.

    `stop()` 과 `finally` 양쪽 모두 task cancel 통일 패턴 (사이클 13-E-2 명세):
    > 비정상 종료 경로에서도 좀비 task 방지 — `finally` 와 `stop()` 동일한
    > task 목록 통일.

    검증: scheduler.py 전체 소스에서 `"_api_recovered_collector_task"` 문자열 리터럴
    등장 ≥ 2건 (`stop()` 1건 + `finally` 1건).

    Red: 현재 0건 (양쪽 모두 누락) → FAIL.
    Green: ≥ 2건 → PASS.
    """
    source = _SCHEDULER_PY.read_text(encoding="utf-8")

    # 문자열 리터럴 등장 (코드 자체의 attribute 정의/생성 등은 따옴표 없는 식별자)
    quoted_occurrences = source.count(f'"{_COLLECTOR_TASK_ATTR}"')

    assert quoted_occurrences >= 2, (
        f"\n사이클 79 G-CC3 위반 — `\"{_COLLECTOR_TASK_ATTR}\"` 문자열 리터럴 "
        f"등장 횟수: {quoted_occurrences} (≥ 2 필요).\n\n"
        f"  `stop()` (L860~865) 와 `finally` 블록 (L737~742) 양쪽 모두 task_attrs\n"
        f"  튜플에 포함되어야 함 — 사이클 13-E-2 명세 (양쪽 동일 목록 통일).\n\n"
        f"  사이클 76 도입 시 양쪽 모두 누락 (silent 결함, 사이클 78 부차 발견)."
    )
