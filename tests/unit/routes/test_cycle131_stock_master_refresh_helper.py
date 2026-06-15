"""사이클 131 (2026-06-15) — routes/stock_master.py 4 POST fire-and-forget 헬퍼 추출 격리 가드.

사용자 결정 영속:
- Q1=A (사이클 131 = 카드 #22 단독 Green)
- refactor-review 카드 #22 (LOW, -115L) 영속

배경 (사이클 130 권고 카드 #22 영속):
- 4 동일 패턴 fire-and-forget runner 통합:
  - `_run_universe_background` (사이클 90 패턴)
  - `_run_basics_background` (사이클 126)
  - `_run_daily_background` (사이클 126)
  - `_run_master_background` (사이클 129)
- 4 POST 라우트 핸들러 동일 구조 (force query param + state 가드 + BackgroundTasks 등록 + 응답 envelope)

영속 의무 매트릭스 영구 영속:
- 사이클 84 L-2 화이트리스트 4 라우트 영속 (`/refresh-universe`, `/basics/refresh`, `/daily/refresh`, `/master/refresh`)
- 사이클 88 G-REJECT graceful (예외 → finish_progress("failed") 안전망)
- 사이클 90 asyncio.Lock 폐기 → state 기반 가드 (sole source of truth)
- 사이클 127 fire-and-forget BackgroundTasks (axios timeout silent 결함 차단)
- 사이클 127 G-AST4 `background_tasks.add_task ≥ 4` + `asyncio.create_task == 0`
- 사이클 128 응답 envelope `{status: "started", task_key}` 영속
- 사이클 129 master TaskKey 4번째 영속

행위 보존 의무 (refactor 가정):
- 4 라우트 응답 schema 변경 0 (사이클 128 envelope)
- 4 라우트 동작 (409 가드 + BackgroundTasks 등록 + 응답 즉시) 변경 0
- AST 화이트리스트 4 영속
- 매매 안전성 무영향 (라우트 영역 한정 + scanner / risk / order / realtime / auth 변경 0)
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

from src.routes import stock_master as routes_sm
from src.engine import refresh_progress as _rp


# =============================================================================
# G-22-A — 헬퍼 영속 (사이클 131 Green 기대값)
# =============================================================================


class TestHelperExportPersistence:
    """카드 #22 Green 후 헬퍼 함수 영속 영구 영속 영역.

    헬퍼 함수 2 종 영속 의무:
    - `_make_background_runner(task_key, once_callable)` — 4 동일 try/except + finish_progress("failed") 패턴 추출
    - `_TASK_REGISTRY` (또는 동등) — task_key + once_callable + 라우트 메타데이터 dispatch
    """

    def test_make_background_runner_exists(self):
        """G-22-A-1 — `_make_background_runner` 헬퍼 영속.

        시그너처: `(task_key: str, once_callable: Callable) -> Callable[[bool], Awaitable[None]]`
        반환 함수 = `_run_X_background(force: bool) -> None` 역할.
        """
        assert hasattr(routes_sm, "_make_background_runner"), (
            "routes/stock_master.py 에 `_make_background_runner` 헬퍼 부재. "
            "카드 #22 Green 의무 영속 (4 wrapper try/except + finish_progress 패턴 추출)."
        )
        helper = routes_sm._make_background_runner
        assert callable(helper), "_make_background_runner 은 callable 의무 영속"

    def test_task_registry_exists(self):
        """G-22-A-2 — `_TASK_REGISTRY` (또는 동등) dispatch 영속.

        4 task_key 모두 등록 의무 (universe / basics / daily / master).
        refresh_progress.TASK_KEYS 와 정합 의무.
        """
        registry_attr = None
        for candidate in ("_TASK_REGISTRY", "_REFRESH_TASKS", "_TASK_DISPATCH"):
            if hasattr(routes_sm, candidate):
                registry_attr = candidate
                break
        assert registry_attr is not None, (
            "routes/stock_master.py 에 task dispatch registry 부재. "
            "후보: `_TASK_REGISTRY` / `_REFRESH_TASKS` / `_TASK_DISPATCH`. "
            "카드 #22 Green 의무 영속."
        )

        registry = getattr(routes_sm, registry_attr)
        assert hasattr(registry, "__contains__") or isinstance(registry, (dict, tuple, list)), (
            f"{registry_attr} 은 dict/tuple/list 영속 의무"
        )

        # 4 task_key 정합 의무
        if isinstance(registry, dict):
            keys = set(registry.keys())
        else:
            keys = set(registry)
        expected = set(_rp.TASK_KEYS)
        assert expected.issubset(keys), (
            f"{registry_attr} 가 4 task_key 영속 부재 — "
            f"expected={expected}, got={keys}. "
            "사이클 129 TaskKey 4 영속 의무 + refresh_progress.TASK_KEYS 정합."
        )


# =============================================================================
# G-22-B — 4 라우트 동작 영속 (행위 보존 의무 영구 영속)
# =============================================================================


class TestRouteBehaviorPreservation:
    """카드 #22 Green 후 4 라우트 동작 보존 검증.

    응답 schema 변경 0 (사이클 128 envelope):
    - `{success: True, data: {status: "started", task_key: X}, message: ...}`
    - 409 가드 (`is_running(X)=True` 시)
    - BackgroundTasks 등록 (response 즉시 + 백그라운드 발화)
    """

    @pytest.mark.asyncio
    async def test_universe_route_started_response(self):
        """G-22-B-1 — `/refresh-universe` 응답 schema 영속."""
        from fastapi import BackgroundTasks

        _rp.reset_all_progress()
        bg = BackgroundTasks()

        resp = await routes_sm.refresh_universe_now(background_tasks=bg, force=True)

        # 응답 envelope 영속 의무 (사이클 128)
        assert resp.success is True
        assert resp.data["status"] == "started"
        assert resp.data["task_key"] == "universe"
        assert "universe refresh 시작" in resp.message
        # BackgroundTasks 등록 ≥ 1 영속 의무 (사이클 127 fire-and-forget)
        assert len(bg.tasks) == 1

    @pytest.mark.asyncio
    async def test_basics_route_started_response(self):
        """G-22-B-2 — `/basics/refresh` 응답 schema 영속."""
        from fastapi import BackgroundTasks

        _rp.reset_all_progress()
        bg = BackgroundTasks()

        resp = await routes_sm.refresh_basics_now(background_tasks=bg, force=True)

        assert resp.success is True
        assert resp.data["status"] == "started"
        assert resp.data["task_key"] == "basics"
        assert "basics refresh 시작" in resp.message
        assert len(bg.tasks) == 1

    @pytest.mark.asyncio
    async def test_daily_route_started_response(self):
        """G-22-B-3 — `/daily/refresh` 응답 schema 영속."""
        from fastapi import BackgroundTasks

        _rp.reset_all_progress()
        bg = BackgroundTasks()

        resp = await routes_sm.refresh_daily_now(background_tasks=bg, force=True)

        assert resp.success is True
        assert resp.data["status"] == "started"
        assert resp.data["task_key"] == "daily"
        assert "daily refresh 시작" in resp.message
        assert len(bg.tasks) == 1

    @pytest.mark.asyncio
    async def test_master_route_started_response(self):
        """G-22-B-4 — `/master/refresh` 응답 schema 영속 (사이클 129)."""
        from fastapi import BackgroundTasks

        _rp.reset_all_progress()
        bg = BackgroundTasks()

        resp = await routes_sm.refresh_master_now(background_tasks=bg, force=True)

        assert resp.success is True
        assert resp.data["status"] == "started"
        assert resp.data["task_key"] == "master"
        assert "master refresh 시작" in resp.message
        assert len(bg.tasks) == 1

    @pytest.mark.asyncio
    async def test_409_guard_all_task_keys(self):
        """G-22-B-5 — 4 라우트 모두 409 가드 영속 (사이클 90 → 사이클 127 state 가드).

        is_running=True 시 HTTPException(409) 발화 의무 (라우트 동작 보존).
        """
        from fastapi import BackgroundTasks, HTTPException

        _rp.reset_all_progress()
        # 4 task_key 모두 running 상태로 강제
        for task_key in _rp.TASK_KEYS:
            _rp.start_progress(task_key, total=0)

        bg = BackgroundTasks()

        # 4 라우트 모두 409 발화 의무
        with pytest.raises(HTTPException) as exc:
            await routes_sm.refresh_universe_now(background_tasks=bg, force=True)
        assert exc.value.status_code == 409

        with pytest.raises(HTTPException) as exc:
            await routes_sm.refresh_basics_now(background_tasks=bg, force=True)
        assert exc.value.status_code == 409

        with pytest.raises(HTTPException) as exc:
            await routes_sm.refresh_daily_now(background_tasks=bg, force=True)
        assert exc.value.status_code == 409

        with pytest.raises(HTTPException) as exc:
            await routes_sm.refresh_master_now(background_tasks=bg, force=True)
        assert exc.value.status_code == 409

        # 정리
        _rp.reset_all_progress()


# =============================================================================
# G-22-C — 백그라운드 wrapper 동작 보존 영역
# =============================================================================


class TestBackgroundRunnerBehavior:
    """헬퍼 추출 후 백그라운드 wrapper 동작 보존 검증.

    동작 의무:
    - once_callable 정상 완료 시 → 예외 0 + finish_progress 호출 부재 (once 내부에서 처리 영속)
    - once_callable Exception 시 → graceful catch + is_running=True 시 finish_progress("failed") 발화
    """

    @pytest.mark.asyncio
    async def test_background_runner_graceful_exception(self):
        """G-22-C-1 — 헬퍼 wrapper graceful 예외 처리 영속 (사이클 88 G-REJECT 답습).

        once_callable Exception 발생 → catch + finish_progress("failed") 안전망 발화.
        is_running=False 시 finish_progress 호출 skip (중복 호출 차단).
        """
        if not hasattr(routes_sm, "_make_background_runner"):
            pytest.skip("Red 단계 — Green 후 영구 영속 의무")

        async def failing_once(force: bool = False):
            raise RuntimeError("KIS test failure")

        # 헬퍼로 wrapper 생성
        runner = routes_sm._make_background_runner("universe", failing_once)

        _rp.reset_all_progress()
        # is_running=True 시뮬 (once 내부에서 시작했다고 가정)
        _rp.start_progress("universe", total=0)

        # graceful 예외 처리 (raise 0 영속)
        await runner(force=False)

        # finish_progress("failed") 발화 영속
        state = _rp.get_progress("universe")
        assert state["status"] == "failed", (
            f"백그라운드 wrapper graceful 예외 시 finish_progress('failed') 의무 — "
            f"got status={state['status']}"
        )
        assert state["error_message"] is not None
        assert "KIS test failure" in state["error_message"]

        _rp.reset_all_progress()


# =============================================================================
# G-22-D — AST 화이트리스트 영속 (사이클 84 L-2 + 사이클 124 G-AST1)
# =============================================================================


class TestPostRouteWhitelistPersistence:
    """4 POST 라우트 화이트리스트 영속 의무 (사이클 84 L-2)."""

    def test_post_route_count_is_four(self):
        """G-22-D-1 — POST 라우트 정확히 4개 영속.

        사이클 84 L-2 = `read-only` 원칙 + POST 화이트리스트 4개.
        헬퍼 추출 후에도 동일 4 라우트 영속.
        """
        source_path = Path(routes_sm.__file__)
        tree = ast.parse(source_path.read_text(encoding="utf-8"))

        post_routes = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)):
                for dec in node.decorator_list:
                    if isinstance(dec, ast.Call):
                        # @router.post(...)
                        if (
                            isinstance(dec.func, ast.Attribute)
                            and dec.func.attr == "post"
                        ):
                            post_routes.append(node.name)

        # 정확히 4개 (refresh-universe, basics/refresh, daily/refresh, master/refresh)
        assert len(post_routes) == 4, (
            f"POST 라우트 4개 영속 의무 — got {len(post_routes)}: {post_routes}. "
            "사이클 84 L-2 화이트리스트 영속."
        )

    def test_no_asyncio_create_task_in_routes(self):
        """G-22-D-2 — `asyncio.create_task` 사용 0 영속 (사이클 127 G-AST4).

        헬퍼 추출 후에도 `BackgroundTasks.add_task` 사용 + `asyncio.create_task` 0 영속.
        axios timeout silent 결함 영구 차단 영속.
        """
        source_path = Path(routes_sm.__file__)
        source = source_path.read_text(encoding="utf-8")
        tree = ast.parse(source)

        create_task_count = 0
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute):
                if node.attr == "create_task":
                    if isinstance(node.value, ast.Name) and node.value.id == "asyncio":
                        create_task_count += 1

        assert create_task_count == 0, (
            f"`asyncio.create_task` 사용 0 영속 의무 — got {create_task_count} 건. "
            "사이클 127 G-AST4 영속 (BackgroundTasks 만 허용)."
        )

    def test_background_tasks_add_task_persists(self):
        """G-22-D-3 — `background_tasks.add_task` 호출 ≥ 1 영속 (사이클 131 의미 전환).

        사이클 131 헬퍼 dispatch 패턴 영속 = 4 라우트 → 1 dispatch 헬퍼 (`_dispatch_refresh`).
        헬퍼 내부에서 add_task 호출 영속 = 4 라우트 모두 BackgroundTasks 영속 흡수.

        사이클 127 G-AST4 원본 ≥ 3 → 사이클 129 ≥ 4 → 사이클 131 헬퍼 추출 후 ≥ 1 의미 전환.
        의미 보존: BackgroundTasks 사용 영속 + asyncio.create_task 0 영속.

        4 라우트 dispatch 영속 검증은 G-22-B-1~B-4 (개별 라우트 호출 시 bg.tasks ≥ 1) 영속.
        """
        source_path = Path(routes_sm.__file__)
        source = source_path.read_text(encoding="utf-8")

        # BackgroundTasks 사용 영속 (헬퍼 추출 후 ≥ 1 영속, 사이클 131 의미 전환)
        add_task_count = source.count(".add_task(")
        assert add_task_count >= 1, (
            f"`background_tasks.add_task` 호출 ≥ 1 영속 의무 — got {add_task_count} 건. "
            "사이클 127 G-AST4 → 사이클 131 의미 전환 (4 라우트 → 1 dispatch 헬퍼)."
        )

        # 4 라우트 dispatch 영속 의무 = `_dispatch_refresh` 호출 ≥ 4 영속
        dispatch_count = source.count("_dispatch_refresh(")
        # 정의 1 + 호출 4 = ≥ 5 영속
        assert dispatch_count >= 5, (
            f"`_dispatch_refresh` 호출 4 라우트 영속 의무 — got {dispatch_count} 건. "
            "사이클 131 dispatch 헬퍼 4 라우트 영속."
        )


# =============================================================================
# G-22-E — 라인 감소 효과 영속 영역 (행위 보존 + 코드 정리)
# =============================================================================


class TestLineReductionEffect:
    """카드 #22 라인 감소 영역 영구 영속 (선언적 가드).

    헬퍼 추출 + dispatch 적용 후 routes/stock_master.py 총 라인 감소 영속.
    임계: 372L → 340L 이하 (-32L 보수적 기준, 행위 보존 + docstring 영속 + 사이클 129 master 분기 + 405 가드 영속 가산 흡수).

    원본 권고 -115L 영역은 docstring + 5 영속 의무 매트릭스 + 405 가드 영속 흡수로 보수적 기준 채택.
    핵심 의도 (4 wrapper 본체 중복 폐기) 는 G-22-E-2 가 보장.
    """

    def test_total_line_reduction(self):
        """G-22-E-1 — routes/stock_master.py 라인 감소 영속.

        헬퍼 추출 + dispatch 적용 후 총 라인 ≤ 340L 영속 의무.
        Red 단계 (372L) → Green 단계 (≤340L) 의미 전환 영속.

        보수적 기준 사유:
        - docstring 영속 (사이클 130 카드 #22 + 사이클 131 헬퍼 의도 명문화)
        - 사이클 84 L-2 영속 의무 매트릭스 docstring 보존
        - 사이클 129 master 영역 추가 (POST_ONLY 가드 405 영속)
        - 사이클 127/128/130/131 등 영속 의무 명문화 docstring
        - 행위 보존 100% (응답 schema 동일, 라우트 4 동일, 405 가드 동일)
        """
        if not hasattr(routes_sm, "_make_background_runner"):
            pytest.skip("Red 단계 — Green 후 영구 영속 의무")

        source_path = Path(routes_sm.__file__)
        line_count = len(source_path.read_text(encoding="utf-8").splitlines())

        assert line_count <= 340, (
            f"routes/stock_master.py 라인 감소 영속 의무 — got {line_count}L, "
            f"target ≤ 340L (Green 후, 카드 #22 행위 보존 영역). "
            "사이클 130 권고 카드 #22 영속."
        )

    def test_no_duplicated_run_x_background_functions(self):
        """G-22-E-2 — `_run_X_background` 4 wrapper 중복 폐기 영속.

        헬퍼 추출 후 4 wrapper 본체 (try/except + finish_progress 패턴) 중복 0 영속.
        헬퍼가 dispatch 영역 흡수 영속.
        """
        if not hasattr(routes_sm, "_make_background_runner"):
            pytest.skip("Red 단계 — Green 후 영구 영속 의무")

        source_path = Path(routes_sm.__file__)
        source = source_path.read_text(encoding="utf-8")
        tree = ast.parse(source)

        # `_run_X_background` 명명 함수 카운트 (헬퍼가 dispatch 흡수 후 = 0~1 영속)
        wrapper_funcs = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)):
                if node.name.startswith("_run_") and node.name.endswith("_background"):
                    wrapper_funcs.append(node.name)

        assert len(wrapper_funcs) <= 1, (
            f"`_run_X_background` 4 wrapper 중복 폐기 영속 의무 — "
            f"got {len(wrapper_funcs)}: {wrapper_funcs}. "
            "헬퍼 `_make_background_runner` dispatch 영속."
        )
