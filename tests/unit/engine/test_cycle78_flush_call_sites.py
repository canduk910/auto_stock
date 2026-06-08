"""사이클 78 의제 1 — flush 호출 사이트 존재 검증 (사이클 74 도입 누락 silent 결함 시정).

Red 단계: `flush_swing_rest_poll_collector` + `flush_stale_watcher_collector` 가
스케줄러 task 또는 lifecycle hook 어디에서도 호출되지 않음 → G-FL1~FL4 모두 FAIL.

Green 단계: backend-dev 가 옵션 1 (`_api_recovered_collector_loop` 본체에 swing/stale
flush 추가) 또는 옵션 2 (신규 `_summary_collector_loop` task) 도입 후 모두 PASS.

C 진단 결과 (필수 정독):
- 사이클 74 commit (`0017fe0`) = collector + 위임 함수 도입 완료
- 누락 = flush 호출 사이트 (5분 주기 task 또는 lifecycle hook) 0건
- Supabase 측정 (2026-06-07 22:56 ~ 현재):
  - `[swing_rest_poll_summary]` 0건 영구 (배포 후 emit 0건)
  - `[stale_watcher_summary]` 0건 영구
- 메모리 leak 위험: `_swing_rest_poll_collector` / `_stale_watcher_collector`
  무한 누적 (720 + 360 = 1,080 dict / day)

영속 의무:
- 사이클 17 KIS LMS chain 차단
- 사이클 38 명문화 (tradable_boards 매수 진입 전용)
- 사이클 42 `[ws_heartbeat]` 5분 통계 답습 패턴
- 사이클 55 R-1 / 66 / 67 매매 안전성 영역 영향 0 (로깅 영역 시정만)
- 사이클 74 record/flush 함수 시그너처 영속 (호출 사이트만 신규 추가)
- 사이클 76 `_api_recovered_collector_loop` 본체 패턴 답습
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit


_SRC_ROOT = Path(__file__).resolve().parents[3] / "src"
_SCHEDULER_PY = _SRC_ROOT / "engine" / "scheduler.py"


# ===========================================================================
# 공통 AST 헬퍼
# ===========================================================================
def _all_function_nodes(source: str) -> list[ast.FunctionDef | ast.AsyncFunctionDef]:
    """모듈 전체에서 (Async)FunctionDef 노드 모두 수집."""
    tree = ast.parse(source)
    nodes: list[ast.FunctionDef | ast.AsyncFunctionDef] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            nodes.append(node)
    return nodes


def _find_calls_to(name: str, root: ast.AST) -> list[int]:
    """`root` AST 서브트리에서 `name(...)` 호출 사이트의 line_no 목록 반환.

    매칭 대상:
    - `name(...)` 단순 호출
    - `module.name(...)` 속성 호출 (attribute 마지막 부분 매칭)
    """
    sites: list[int] = []
    for sub in ast.walk(root):
        if not isinstance(sub, ast.Call):
            continue
        func = sub.func
        if isinstance(func, ast.Name) and func.id == name:
            sites.append(sub.lineno)
        elif isinstance(func, ast.Attribute) and func.attr == name:
            sites.append(sub.lineno)
    return sites


def _find_function_containing_call(
    source: str, target_name: str
) -> list[tuple[str, int]]:
    """`target_name(...)` 호출이 들어있는 모든 함수의 (이름, line_no) 목록 반환."""
    hits: list[tuple[str, int]] = []
    for node in _all_function_nodes(source):
        sites = _find_calls_to(target_name, node)
        if sites:
            hits.append((node.name, sites[0]))
    return hits


# ===========================================================================
# G-FL1: `flush_swing_rest_poll_collector` 호출 사이트 ≥ 1건 (스케줄러 task or lifecycle)
# ===========================================================================
def test_g_fl1_flush_swing_rest_poll_collector_call_site_exists():
    """G-FL1: `src/engine/scheduler.py` 에서 `flush_swing_rest_poll_collector(...)`
    호출 사이트 ≥ 1건 존재 — 5분 주기 task 또는 lifecycle hook.

    사이클 74 = 함수 도입 완료, 사이클 78 = 호출 사이트 도입.
    Red: 0건 → FAIL
    Green: ≥ 1건 → PASS

    옵션 1: `_api_recovered_collector_loop` 본체에 추가 (사이클 76 task 재사용)
    옵션 2: 신규 `_summary_collector_loop` task 별도 도입
    옵션 권고: 옵션 1 (단순 + 추가 task 미도입)
    """
    source = _SCHEDULER_PY.read_text(encoding="utf-8")
    sites = _find_function_containing_call(source, "flush_swing_rest_poll_collector")
    assert len(sites) >= 1, (
        f"\n사이클 78 G-FL1 위반 — `flush_swing_rest_poll_collector(...)` 호출 사이트 0건.\n"
        f"  사이클 74 commit (0017fe0) = 함수 도입 완료\n"
        f"  사이클 78 silent 결함 = 호출 사이트 도입 누락\n"
        f"  메모리 leak: `_swing_rest_poll_collector` 무한 누적 (720 dict/day)\n"
        f"  Supabase 측정: `[swing_rest_poll_summary]` 0건 영구\n\n"
        f"  시정 옵션 1 (권고): `_api_recovered_collector_loop` 본체에 추가:\n"
        f"    while self._running:\n"
        f"        await asyncio.sleep(_API_RECOVERED_COLLECTOR_WINDOW)\n"
        f"        if not self._running: break\n"
        f"        try: await _flush_api_recovered_collector()\n"
        f"        except: ...\n"
        f"        # 사이클 78 hotfix:\n"
        f"        try: flush_swing_rest_poll_collector()\n"
        f"        except: ...\n"
        f"        try: flush_stale_watcher_collector()\n"
        f"        except: ...\n"
        f"  시정 옵션 2: 신규 `_summary_collector_loop` task 도입"
    )


# ===========================================================================
# G-FL2: `flush_stale_watcher_collector` 호출 사이트 ≥ 1건
# ===========================================================================
def test_g_fl2_flush_stale_watcher_collector_call_site_exists():
    """G-FL2: `src/engine/scheduler.py` 에서 `flush_stale_watcher_collector(...)`
    호출 사이트 ≥ 1건 존재.

    Red: 0건 → FAIL
    Green: ≥ 1건 → PASS
    """
    source = _SCHEDULER_PY.read_text(encoding="utf-8")
    sites = _find_function_containing_call(source, "flush_stale_watcher_collector")
    assert len(sites) >= 1, (
        f"\n사이클 78 G-FL2 위반 — `flush_stale_watcher_collector(...)` 호출 사이트 0건.\n"
        f"  사이클 74 commit (0017fe0) = 함수 도입 완료\n"
        f"  사이클 78 silent 결함 = 호출 사이트 도입 누락\n"
        f"  메모리 leak: `_stale_watcher_collector` 무한 누적 (360 dict/day)\n"
        f"  Supabase 측정: `[stale_watcher_summary]` 0건 영구\n\n"
        f"  시정: `flush_swing_rest_poll_collector` 와 동일 함수 본체에 추가 (옵션 1)\n"
        f"  import: `from src.engine.stale_watcher_core import flush_stale_watcher_collector`"
    )


# ===========================================================================
# G-FL3: `stop()` 또는 lifecycle 종료 직전 마지막 flush 1회 호출 (Q5)
# ===========================================================================
def test_g_fl3_lifecycle_shutdown_flush_call_site_exists():
    """G-FL3: `stop()` (lifecycle 종료) 함수 본체 또는 그로부터 도달 가능한 함수 본체에서
    `flush_swing_rest_poll_collector` 와 `flush_stale_watcher_collector` 모두 호출.

    Q5 (사이클 74 G-SP4 답습) = 잔여 카운터 손실 방지 — 정산 *직전* 데이터 보존.
    5 미만 잔존 케이스 (운영 종료 직전 부분 누적) 가 영구 유실되는 silent 결함 차단.

    Red: `stop()` 본체에 flush 호출 0건 → FAIL
    Green: `stop()` 본체에 양쪽 flush 호출 ≥ 1건 → PASS
    """
    source = _SCHEDULER_PY.read_text(encoding="utf-8")
    nodes = _all_function_nodes(source)

    stop_node = next((n for n in nodes if n.name == "stop"), None)
    assert stop_node is not None, (
        "사이클 78 G-FL3: `stop()` 함수 미존재 — scheduler 라이프사이클 경로 확인 필요"
    )

    swing_sites = _find_calls_to("flush_swing_rest_poll_collector", stop_node)
    stale_sites = _find_calls_to("flush_stale_watcher_collector", stop_node)

    missing: list[str] = []
    if not swing_sites:
        missing.append("flush_swing_rest_poll_collector")
    if not stale_sites:
        missing.append("flush_stale_watcher_collector")

    assert not missing, (
        f"\n사이클 78 G-FL3 위반 — `stop()` (lifecycle 종료) 본체에 누락 flush: {missing}\n"
        f"  사이클 74 G-SP4 (Q5 옵션 A) 답습 의무 — 잔여 카운터 손실 방지\n"
        f"  운영 시나리오: 5 미만 잔존 (운영 종료 직전 부분 누적) → 영구 유실\n\n"
        f"  시정: `stop()` 본체에 `unsubscribe_all()` 호출 직전 추가:\n"
        f"    # 사이클 78 hotfix: 잔존 collector 마지막 flush (Q5)\n"
        f"    try: flush_swing_rest_poll_collector()\n"
        f"    except: logger.exception(...)\n"
        f"    try: flush_stale_watcher_collector()\n"
        f"    except: logger.exception(...)"
    )


# ===========================================================================
# G-FL4: 5분 주기 task 가 swing + stale collector 모두 flush (정적 + 함수 단위)
# ===========================================================================
def test_g_fl4_periodic_task_flushes_both_collectors():
    """G-FL4: 동일한 5분 주기 task 함수 (또는 신규 task) 본체에서 양쪽 flush 모두 호출.

    옵션 1: `_api_recovered_collector_loop` 본체에 양쪽 flush 추가
    옵션 2: 신규 task 본체에 양쪽 flush 도입

    공통 의무: 동일 함수 본체 내에서 양쪽 flush 호출 ≥ 1건 (영구 가드).

    Red: G-FL1 + G-FL2 가 같은 함수 본체에 모이지 않음 → FAIL
    Green: 동일 함수 (예: `_api_recovered_collector_loop` 또는 `_summary_collector_loop`)
           본체에 양쪽 flush 호출 모두 존재 → PASS
    """
    source = _SCHEDULER_PY.read_text(encoding="utf-8")
    nodes = _all_function_nodes(source)

    # 동일 함수에 양쪽 flush 모두 들어있는 후보 검색
    co_located_functions: list[str] = []
    for node in nodes:
        swing_sites = _find_calls_to("flush_swing_rest_poll_collector", node)
        stale_sites = _find_calls_to("flush_stale_watcher_collector", node)
        if swing_sites and stale_sites:
            co_located_functions.append(node.name)

    # `stop()` 단독 만족은 lifecycle 가드 (G-FL3), 5분 주기 task 가드 별도 의무.
    # `stop()` 제외 후 ≥ 1 개 함수가 양쪽 flush 보유해야 함 (= 주기 task).
    periodic_candidates = [n for n in co_located_functions if n != "stop"]

    assert len(periodic_candidates) >= 1, (
        f"\n사이클 78 G-FL4 위반 — 5분 주기 task 함수에 양쪽 flush 모두 호출하는 함수 0건.\n"
        f"  현재 co-located 함수 (stop 제외): {periodic_candidates}\n"
        f"  사이클 76 `_api_recovered_collector_loop` 패턴 답습 의무\n\n"
        f"  시정: `_api_recovered_collector_loop` 본체에 5분 주기로 양쪽 flush 호출:\n"
        f"    async def _api_recovered_collector_loop(self) -> None:\n"
        f"        while self._running:\n"
        f"            await asyncio.sleep(_API_RECOVERED_COLLECTOR_WINDOW)\n"
        f"            if not self._running: break\n"
        f"            try: await _flush_api_recovered_collector()\n"
        f"            except: ...\n"
        f"            try: await _flush_quote_recovered_collector()\n"
        f"            except: ...\n"
        f"            # 사이클 78 hotfix:\n"
        f"            try: flush_swing_rest_poll_collector()\n"
        f"            except: logger.exception(...)\n"
        f"            try: flush_stale_watcher_collector()\n"
        f"            except: logger.exception(...)"
    )
