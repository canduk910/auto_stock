"""사이클 127 AST 영구 가드 — progress hook + fire-and-forget 영속.

회귀 가드 6 케이스:
- G-AST1: scanner.py `_full_universe_load_once` 본체 start_progress("universe" + finish_progress
- G-AST2: scanner.py `_stock_master_basics_refresh_once` 본체 start_progress("basics" + finish_progress
- G-AST3: scanner.py `_stock_master_daily_load_once` 본체 start_progress("daily" + finish_progress
- G-AST4: routes/stock_master.py asyncio.create_task 호출 3개
- G-AST5: _refresh_*_lock asyncio.Lock 모듈 전역 변수 영구 폐기 (state 기반 전환)
- G-AST6: GET /refresh-progress 라우트 영속 (사이클 84 L-2 READ-ONLY GET 정합)
"""
from __future__ import annotations

from pathlib import Path

_SCANNER_SRC = Path(__file__).resolve().parents[3] / "src/engine/scanner.py"
_ROUTES_SRC = Path(__file__).resolve().parents[3] / "src/routes/stock_master.py"
_PROGRESS_SRC = Path(__file__).resolve().parents[3] / "src/engine/refresh_progress.py"


# 사이클 136 (2026-06-15) — 카드 #25 AST DRY 헬퍼 모듈 영역 영구 영속 마이그레이션.
from tests.unit.ast._ast_helpers import read_module_source as _read


def test_g_ast1_universe_progress_hooks():
    """G-AST1: _full_universe_load_once 본체에 universe start/finish progress 호출."""
    src = _read(_SCANNER_SRC)
    # 함수 본체 추출
    start_idx = src.find("async def _full_universe_load_once(")
    assert start_idx >= 0, "_full_universe_load_once 함수 미존재"
    end_idx = src.find("\nasync def ", start_idx + 1)
    if end_idx == -1:
        end_idx = len(src)
    body = src[start_idx:end_idx]

    assert 'start_progress("universe"' in body, (
        "G-AST1: _full_universe_load_once 본체에 start_progress(\"universe\" 호출 부재"
    )
    assert 'finish_progress(\n            "universe"' in body or 'finish_progress("universe"' in body, (
        "G-AST1: _full_universe_load_once 본체에 finish_progress(\"universe\" 호출 부재"
    )


def test_g_ast2_basics_progress_hooks():
    """G-AST2: _stock_master_basics_refresh_once 본체에 basics start/finish progress 호출."""
    src = _read(_SCANNER_SRC)
    start_idx = src.find("async def _stock_master_basics_refresh_once(")
    assert start_idx >= 0
    end_idx = src.find("\nasync def ", start_idx + 1)
    if end_idx == -1:
        end_idx = len(src)
    body = src[start_idx:end_idx]

    assert 'start_progress("basics"' in body, "G-AST2: basics start_progress 부재"
    assert 'finish_progress(\n        "basics"' in body or 'finish_progress("basics"' in body, (
        "G-AST2: basics finish_progress 부재"
    )


def test_g_ast3_daily_progress_hooks():
    """G-AST3: _stock_master_daily_load_once 본체에 daily start/finish progress 호출."""
    src = _read(_SCANNER_SRC)
    start_idx = src.find("async def _stock_master_daily_load_once(")
    assert start_idx >= 0
    end_idx = src.find("\nasync def ", start_idx + 1)
    if end_idx == -1:
        end_idx = len(src)
    body = src[start_idx:end_idx]

    assert 'start_progress("daily"' in body, "G-AST3: daily start_progress 부재"
    assert 'finish_progress(\n            "daily"' in body or 'finish_progress(\n        "daily"' in body or 'finish_progress("daily"' in body, (
        "G-AST3: daily finish_progress 부재"
    )


def test_g_ast4_background_tasks_3_routes():
    """G-AST4: routes/stock_master.py 에 BackgroundTasks.add_task 호출 ≥ 1 영속 + dispatch helper 영속.

    사이클 127 — FastAPI BackgroundTasks 사용 (response 전송 후 schedule).
    사이클 131 의미 전환 (카드 #22 — refactor-review 권고 채택) — 사이클 66 K-2 패턴 답습:
    - Red 시점 ≥ 3 (3 wrapper 각각 add_task 호출)
    - Green 시점 ≥ 1 (헬퍼 `_dispatch_refresh` 단일 add_task 호출, 4 라우트가 dispatch 공유)
    - 핵심 의도 보존: BackgroundTasks 사용 영속 + asyncio.create_task 0 영속.
    - 4 라우트 dispatch 영속 검증은 `_dispatch_refresh` 호출 ≥ 5 (정의 1 + 호출 4) 영역.

    asyncio.create_task + TestClient anyio portal hang silent 결함 영구 차단.
    """
    src = _read(_ROUTES_SRC)
    add_task_count = src.count("background_tasks.add_task(")
    # 사이클 131 의미 전환 — 헬퍼 dispatch 후 ≥ 1 영속 (카드 #22)
    assert add_task_count >= 1, (
        f"G-AST4: background_tasks.add_task 호출 {add_task_count} < 1 — fire-and-forget 영속 위반"
    )
    # 4 라우트 dispatch 영속 영역 (`_dispatch_refresh` 정의 1 + 호출 4 = ≥ 5)
    dispatch_count = src.count("_dispatch_refresh(")
    assert dispatch_count >= 5, (
        f"G-AST4: `_dispatch_refresh` 호출 {dispatch_count} < 5 — 사이클 131 헬퍼 dispatch 4 라우트 영속 위반"
    )
    # asyncio.create_task 라우트 본체 잔존 0건 — TestClient hang 회귀 영구 차단
    create_task_in_routes = src.count("asyncio.create_task(")
    assert create_task_in_routes == 0, (
        f"G-AST4: routes/stock_master.py 에 asyncio.create_task 잔존 {create_task_in_routes} — "
        "사이클 127 BackgroundTasks 전환 위반 (TestClient hang 영구 차단)"
    )


def test_g_ast5_lock_purged():
    """G-AST5: _refresh_*_lock asyncio.Lock 모듈 전역 변수 영구 폐기.

    사이클 127 = state 기반 가드 (refresh_progress.is_running) 전환.
    asyncio.Lock 영역 영구 폐기 의무.
    """
    src = _read(_ROUTES_SRC)
    assert "_refresh_universe_lock = asyncio.Lock()" not in src, (
        "G-AST5: _refresh_universe_lock 폐기 위반 — state 기반 전환 의무"
    )
    assert "_refresh_basics_lock = asyncio.Lock()" not in src, (
        "G-AST5: _refresh_basics_lock 폐기 위반"
    )
    assert "_refresh_daily_lock = asyncio.Lock()" not in src, (
        "G-AST5: _refresh_daily_lock 폐기 위반"
    )


def test_g_ast6_get_refresh_progress_route():
    """G-AST6: GET /refresh-progress 라우트 영속 + is_running 가드 영속 (사이클 84 L-2 READ-ONLY GET 정합).

    사이클 131 의미 전환 (카드 #22) — 사이클 66 K-2 패턴 답습:
    - Red 시점 = 인라인 `_rp.is_running("X")` 4 회 (4 라우트 각각)
    - Green 시점 = 헬퍼 `_dispatch_refresh` 내부 `_rp.is_running(task_key)` 단일 호출 + `_TASK_REGISTRY` 4 task_key 영속
    - 핵심 의도 보존: 4 라우트 모두 409 가드 발화 영속 (헬퍼 dispatch 내부에서 흡수).

    가드 방식 의미 전환:
    - 인라인 호출 `_rp.is_running("X")` → 헬퍼 호출 `_rp.is_running(task_key)` + `_TASK_REGISTRY` dispatch.
    """
    src = _read(_ROUTES_SRC)
    assert '@router.get("/refresh-progress")' in src, (
        "G-AST6: GET /refresh-progress 라우트 부재 — 5초 폴링 영역 위반"
    )

    # 사이클 131 의미 전환 — is_running 가드 영속 (인라인 또는 헬퍼 dispatch 흡수)
    # 헬퍼 dispatch 영속 = `_TASK_REGISTRY` 4 task_key + `_rp.is_running(task_key)` 단일 호출
    has_dispatch = "_TASK_REGISTRY" in src and "_rp.is_running(task_key)" in src
    has_inline = (
        '_rp.is_running("universe")' in src
        and '_rp.is_running("basics")' in src
        and '_rp.is_running("daily")' in src
    )
    assert has_dispatch or has_inline, (
        "G-AST6: is_running 가드 부재 — 인라인 호출 (사이클 127) 또는 "
        "헬퍼 dispatch + _TASK_REGISTRY 4 task_key (사이클 131 의미 전환) 영속 의무 위반"
    )

    # 4 task_key dispatch registry 영속 의무 (헬퍼 영역 진입 시)
    if has_dispatch:
        for task_key in ("universe", "basics", "daily", "master"):
            assert f'"{task_key}":' in src or f"'{task_key}':" in src, (
                f"G-AST6: _TASK_REGISTRY 에 task_key={task_key!r} 영속 부재 — 사이클 131 4 라우트 영속"
            )


def test_g_ast_progress_module_exists():
    """refresh_progress 모듈 존재 + 핵심 함수 export 영속."""
    assert _PROGRESS_SRC.exists(), "src/engine/refresh_progress.py 모듈 부재"
    src = _read(_PROGRESS_SRC)
    assert "def start_progress(" in src
    assert "def update_progress(" in src
    assert "def finish_progress(" in src
    assert "def get_progress(" in src
    assert "def get_all_progress(" in src
    assert "def is_running(" in src
    # KST 영속 (사이클 68 G-10b)
    assert "from src.db._kst import now_kst_iso" in src
    # threading.Lock 영속 (race 차단)
    assert "threading.Lock" in src


def test_g_ast_post_only_paths_refresh_progress_added():
    """사이클 127 — refresh-progress 가 POST only 경로 가드 미적용 (GET 정상)."""
    src = _read(_ROUTES_SRC)
    # _POST_ONLY_PATHS 영역에 refresh-progress 가 *있어야* 함 (동적 {ticker} 영역에서 GET 차단)
    # 사이클 124 영역 = /{ticker}/daily 와 /{ticker} 두 영역에서 POST only path 차단 영속
    post_only_lines = [
        line for line in src.splitlines()
        if "_POST_ONLY_PATHS" in line and "=" in line
    ]
    for line in post_only_lines:
        assert "refresh-progress" in line, (
            "G-AST: refresh-progress 가 _POST_ONLY_PATHS 영역 미포함 — "
            "동적 {ticker} 라우팅 충돌 위험"
        )
