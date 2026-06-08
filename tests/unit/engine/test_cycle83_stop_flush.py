"""사이클 83 G-FL1 — `stop()` 시점 마지막 flush 1회 보장 (사이클 78 답습).

명세 (`_workspace/red/cycle83_scan_pool_eager_refresh.md`):

운영 종료 직전 부분 누적된 eager refresh 통계 collector 잔존 카운터를 1행으로
emit 보장. 사이클 78 hotfix 패턴 답습 (`stop()` lifecycle hook 마지막 flush 1회).

기대 동작 (Green, 사이클 84):
- `stop()` 호출 시 `_flush_scan_pool_eager_refresh_collector()` 1회 호출
- try/except 로 graceful (예외 발화 시 stop() 본체 흐름 보호)

Red 단계 (사이클 83):
- 신규 collector flush 함수 미존재 + stop() lifecycle hook 미추가 → FAIL.

검증:
- scheduler.py::stop() AST unparse 결과에 `flush_scan_pool_eager_refresh_collector`
  호출 ≥ 1건

영속:
- 사이클 78 G-FL1~FL4 패턴 답습 (`stop()` lifecycle hook + 5분 주기 task
  본체 양쪽 flush 호출)
- 사이클 74 sampling/aggregation 패턴 답습
- 매매 안전성 영향 0 (lifecycle 정리)
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit


_SCHEDULER_PY = (
    Path(__file__).resolve().parents[3] / "src" / "engine" / "scheduler.py"
)

_FLUSH_FUNC_NAME = "flush_scan_pool_eager_refresh_collector"


def _get_function_source(class_name: str, func_name: str) -> str:
    """클래스 내 특정 함수 본문 ast.unparse 반환."""
    source = _SCHEDULER_PY.read_text(encoding="utf-8")
    tree = ast.parse(source)
    for cls in ast.walk(tree):
        if not isinstance(cls, ast.ClassDef) or cls.name != class_name:
            continue
        for fn in cls.body:
            if (
                isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef))
                and fn.name == func_name
            ):
                return ast.unparse(fn)
    raise AssertionError(f"{class_name}.{func_name} 함수 정의 미발견")


# ===========================================================================
# G-FL1: stop() 본문에 flush_scan_pool_eager_refresh_collector 호출 ≥ 1건
# ===========================================================================
def test_g_fl1_stop_includes_eager_refresh_collector_flush():
    """G-FL1: `stop()` 함수 본문에 `flush_scan_pool_eager_refresh_collector`
    호출 ≥ 1건 (사이클 78 답습).

    검증: `stop()` 함수 본문 (AST unparse) 에 `flush_scan_pool_eager_refresh_collector`
    호출 ≥ 1건 존재.

    Red (사이클 83): 신규 함수 미존재 + stop() lifecycle hook 미추가 → 0건 → FAIL.

    Green (사이클 84):
    - 신규 함수 `flush_scan_pool_eager_refresh_collector` 도입 (scanner.py 모듈 전역)
    - `stop()` lifecycle hook 에 try/except 로 호출 추가:
      ```
      try:
          from src.engine.scanner import flush_scan_pool_eager_refresh_collector
          flush_scan_pool_eager_refresh_collector()
      except Exception:
          logger.exception("[scan_pool_eager_refresh_collector] shutdown flush 실패")
      ```

    영속 의무:
    - 사이클 78 G-FL3 패턴 답습 (`stop()` 시점 잔존 카운터 손실 방지)
    - 사이클 74 sampling/aggregation 패턴 영속
    """
    stop_source = _get_function_source("TradingScheduler", "stop")
    occurrences = stop_source.count(_FLUSH_FUNC_NAME)

    assert occurrences >= 1, (
        f"\n사이클 83 G-FL1 위반 — `stop()` 본문에 "
        f"`{_FLUSH_FUNC_NAME}` 호출 0건:\n"
        f"  현재 등장 횟수: {occurrences} (≥ 1 필요)\n\n"
        f"  사이클 83 카드 #82-A 옵션 1 = 신규 collector 도입 → stop() 시점\n"
        f"  마지막 flush 1회 보장 (사이클 78 G-FL3 패턴 답습).\n\n"
        f"  Green 시정 예시 (scheduler.py::stop() 의 unsubscribe_all() 직전):\n"
        f"    try:\n"
        f"        from src.engine.scanner import {_FLUSH_FUNC_NAME}\n"
        f"        {_FLUSH_FUNC_NAME}()\n"
        f"    except Exception:\n"
        f"        logger.exception(\"[scan_pool_eager_refresh_collector] shutdown flush 실패\")\n\n"
        f"  사이클 78 G-FL3 명세: 운영 종료 직전 잔존 카운터 손실 방지\n"
        f"  (Q5 사이클 74 답습)."
    )
