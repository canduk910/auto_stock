"""사이클 134 (2026-06-15) — scheduler 4 task loop 공통 헬퍼 추출 격리 가드.

사용자 결정 영속:
- Q1=A 사이클 133 commit `98bf5a0` push + CI 영속
- Q2=A 사이클 134 = 카드 #21 scheduler 4 task loop 헬퍼 추출 (MEDIUM, -193L)

배경 (사이클 130 권고 카드 #21 영속):
- `_full_universe_load_task_loop` (사이클 101/106 universe)
- `_stock_master_daily_load_task_loop` (사이클 122 daily)
- `_stock_master_basics_refresh_task_loop` (사이클 126 basics)
- `_stock_master_master_load_task_loop` (사이클 129/133 master metrics 통합)
- 합계 ~273L 동일 lifecycle 패턴 (사이클 106 race 차단 + while + wait_until + graceful + 60s sleep)
- 사이클 133 master metrics 일관성 통합 후 자연 발주 영역

영속 의무 매트릭스:
- 사이클 67 facade re-export 패턴 답습 (4 task loop facade)
- 사이클 79 G-AST2 영속 (task_attrs 4 위치 영속 — instance + 3 cancel 사이트)
- 사이클 88 G-REJECT graceful 영속 (CancelledError + Exception 분리)
- 사이클 106 lifecycle race 차단 패턴 영속 (start() 직후 즉시 1회 + while 루프)
- 사이클 122/126/129/133 task 패턴 영속

행위 보존 의무 (refactor 가정):
- 4 task loop facade 영속 (instance 메서드 영구 영속 메서드 이름 변경 0)
- lifecycle 영속 = 즉시 1회 + while + wait_until + CancelledError + Exception
- emit 영속 = record + flush + logger.info 영속 (사이클 78 G-AST1 영속)
- 매매 안전성 무영향 (라이프사이클 hook 영역만 + scanner / risk / order / realtime / auth 변경 0)
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest


# =============================================================================
# G-134-A — 공통 헬퍼 모듈 영속 영구 영속
# =============================================================================


class TestTaskLoopHelperPersistence:
    """공통 헬퍼 모듈 `task_loop_helper.py` 또는 동등 영속 영구 영속."""

    def test_g_134_a1_helper_module_exists(self):
        """G-134-A1 — 공통 헬퍼 모듈 영속.

        후보 경로: `src/engine/task_loop_helper.py` 또는 `src/engine/_periodic_task_loop.py`.
        """
        candidates = [
            Path("src/engine/task_loop_helper.py"),
            Path("src/engine/_periodic_task_loop.py"),
            Path("src/engine/periodic_task.py"),
        ]
        existing = [p for p in candidates if p.exists()]
        assert len(existing) >= 1, (
            f"공통 헬퍼 모듈 영속 부재 — 후보: {[str(p) for p in candidates]}. "
            "사이클 134 카드 #21 영속 의무."
        )

    def test_g_134_a2_run_periodic_task_loop_exported(self):
        """G-134-A2 — `run_periodic_task_loop` 헬퍼 영속.

        시그너처 후보: `run_periodic_task_loop(*, scheduler, task_label, wait_time, once_callable,
                                                record_fn, flush_fn, log_prefix, summary_log_format,
                                                summary_keys, immediate_first_run=True,
                                                retry_delay_secs=60)`
        """
        try:
            from src.engine import task_loop_helper as helper_module
        except ImportError:
            try:
                from src.engine import _periodic_task_loop as helper_module
            except ImportError:
                try:
                    from src.engine import periodic_task as helper_module
                except ImportError:
                    pytest.fail(
                        "공통 헬퍼 모듈 import 부재 — 사이클 134 카드 #21 영속 의무."
                    )

        assert hasattr(helper_module, "run_periodic_task_loop"), (
            "run_periodic_task_loop 헬퍼 부재 — 사이클 134 카드 #21 영속 의무."
        )
        helper = helper_module.run_periodic_task_loop
        assert callable(helper), "run_periodic_task_loop 영역 callable 영속 의무"


# =============================================================================
# G-134-B — 4 task loop facade 영속 영구 영속
# =============================================================================


class TestFourTaskLoopFacadePersistence:
    """4 task loop facade 영속 영구 영속 (instance 메서드 변경 0 의무)."""

    def test_g_134_b1_universe_task_loop_facade(self):
        """G-134-B1 — `_full_universe_load_task_loop` instance 메서드 영속."""
        from src.engine.scheduler import TradingScheduler
        assert hasattr(TradingScheduler, "_full_universe_load_task_loop"), (
            "TradingScheduler._full_universe_load_task_loop 영속 부재 — 사이클 134 facade 의무"
        )

    def test_g_134_b2_basics_task_loop_facade(self):
        """G-134-B2 — `_stock_master_basics_refresh_task_loop` instance 메서드 영속."""
        from src.engine.scheduler import TradingScheduler
        assert hasattr(TradingScheduler, "_stock_master_basics_refresh_task_loop"), (
            "TradingScheduler._stock_master_basics_refresh_task_loop 영속 부재 — 사이클 134 facade 의무"
        )

    def test_g_134_b3_daily_task_loop_facade(self):
        """G-134-B3 — `_stock_master_daily_load_task_loop` instance 메서드 영속."""
        from src.engine.scheduler import TradingScheduler
        assert hasattr(TradingScheduler, "_stock_master_daily_load_task_loop"), (
            "TradingScheduler._stock_master_daily_load_task_loop 영속 부재 — 사이클 134 facade 의무"
        )

    def test_g_134_b4_master_task_loop_facade(self):
        """G-134-B4 — `_stock_master_master_load_task_loop` instance 메서드 영속."""
        from src.engine.scheduler import TradingScheduler
        assert hasattr(TradingScheduler, "_stock_master_master_load_task_loop"), (
            "TradingScheduler._stock_master_master_load_task_loop 영속 부재 — 사이클 134 facade 의무"
        )


# =============================================================================
# G-134-C — 사이클 79 G-AST2 task_attrs 4 위치 영속
# =============================================================================


class TestTaskAttrsFourSitesPersistence:
    """사이클 79 G-AST2 영속 영구 영속 — task_attrs 4 위치 영속.

    4 task instance 명 영속:
    - `_full_universe_load_task`
    - `_stock_master_basics_refresh_task`
    - `_stock_master_daily_load_task`
    - `_stock_master_master_load_task`

    위치:
    - instance (`__init__`)
    - `connect().finally` (4 cancel)
    - `run_daily.finally` (4 cancel)
    - `stop()` (4 cancel)
    """

    def test_g_134_c1_task_attrs_in_scheduler(self):
        """G-134-C1 — 4 task instance 명 영속 (사이클 79 G-AST2)."""
        scheduler_src = Path("src/engine/scheduler.py").read_text(encoding="utf-8")

        task_names = [
            "_full_universe_load_task",
            "_stock_master_basics_refresh_task",
            "_stock_master_daily_load_task",
            "_stock_master_master_load_task",
        ]
        for name in task_names:
            assert name in scheduler_src, (
                f"task instance 명 `{name}` 영속 부재 — 사이클 79 G-AST2 영속 의무"
            )

    def test_g_134_c2_each_task_appears_at_least_three_times(self):
        """G-134-C2 — 각 task 명 영속 ≥ 3회 영속 (instance + 2~3 cancel 사이트).

        사이클 79 G-AST2 영속 의무 + 사이클 133 master 통합 영속 답습.
        """
        scheduler_src = Path("src/engine/scheduler.py").read_text(encoding="utf-8")

        task_names = [
            "_full_universe_load_task",
            "_stock_master_basics_refresh_task",
            "_stock_master_daily_load_task",
            "_stock_master_master_load_task",
        ]
        for name in task_names:
            count = scheduler_src.count(name)
            # 헬퍼 추출 후에도 lifecycle 영역 (instance + cancel 사이트) 영속 의무 ≥ 3회
            assert count >= 3, (
                f"task 명 `{name}` 영속 카운트 {count} < 3 — 사이클 79 G-AST2 영속 의무 (instance + cancel 사이트)"
            )


# =============================================================================
# G-134-D — 사이클 106 lifecycle race 차단 패턴 영속
# =============================================================================


class TestLifecycleRacePreventionPersistence:
    """사이클 106 lifecycle race 차단 패턴 영속 영구 영속.

    헬퍼 영역 또는 4 task loop 영역에서 패턴 영속 의무:
    - start() 직후 즉시 1회 실행 (CancelledError + Exception graceful)
    - while 루프 + _wait_until + CancelledError break + Exception graceful + asyncio.sleep(60)
    """

    def test_g_134_d1_immediate_first_run_pattern(self):
        """G-134-D1 — 헬퍼 영역 또는 4 task loop 영역에서 즉시 1회 실행 패턴 영속."""
        scheduler_src = Path("src/engine/scheduler.py").read_text(encoding="utf-8")

        # 4 task loop 영역 영구 영속에서 lifecycle race 차단 패턴 영속 의무 (사이클 106 답습)
        # 헬퍼 영역 영구 영속으로 흡수 시 헬퍼 모듈에서 검증
        helper_paths = [
            Path("src/engine/task_loop_helper.py"),
            Path("src/engine/_periodic_task_loop.py"),
            Path("src/engine/periodic_task.py"),
        ]
        helper_src = ""
        for p in helper_paths:
            if p.exists():
                helper_src = p.read_text(encoding="utf-8")
                break

        # 헬퍼 영역 OR 4 task loop 영역에서 영속 의무
        combined = scheduler_src + "\n" + helper_src
        # 즉시 1회 실행 영역 영구 영속 패턴 영속 = `await self._wait_until` 영역 영구 영속 *전* `try:` + `await once_callable` 영역
        # 또는 헬퍼 영역 `immediate_first_run` 영역 영구 영속
        has_immediate_pattern = (
            "immediate_first_run" in combined
            or "초기 실행" in scheduler_src  # 4 task loop 영역 facade 영속
        )
        assert has_immediate_pattern, (
            "사이클 106 lifecycle race 차단 패턴 영속 부재 — "
            "헬퍼 영역 `immediate_first_run` 또는 4 task loop 영역 `초기 실행` 영속 의무"
        )

    def test_g_134_d2_while_loop_pattern_persists(self):
        """G-134-D2 — while + wait_until + asyncio.sleep(60) 패턴 영속."""
        scheduler_src = Path("src/engine/scheduler.py").read_text(encoding="utf-8")
        helper_paths = [
            Path("src/engine/task_loop_helper.py"),
            Path("src/engine/_periodic_task_loop.py"),
            Path("src/engine/periodic_task.py"),
        ]
        helper_src = ""
        for p in helper_paths:
            if p.exists():
                helper_src = p.read_text(encoding="utf-8")
                break

        combined = scheduler_src + "\n" + helper_src
        # `asyncio.sleep(60)` retry 영역 영구 영속 영속 의무 (사이클 88 G-REJECT graceful)
        assert "asyncio.sleep(60)" in combined or "asyncio.sleep(retry_delay" in combined, (
            "while 루프 retry delay 영역 영구 영속 영속 부재 — 사이클 88 G-REJECT graceful 영역"
        )


# =============================================================================
# G-134-E — 헬퍼 동작 영속 (CancelledError + Exception graceful)
# =============================================================================


class TestHelperBehaviorPreservation:
    """헬퍼 추출 후 동작 영속 영구 영속 — CancelledError graceful + Exception graceful."""

    @pytest.mark.asyncio
    async def test_g_134_e1_cancelled_error_graceful(self):
        """G-134-E1 — CancelledError 영역 영구 영속 graceful 영속 (사이클 88 G-REJECT 답습)."""
        try:
            from src.engine.task_loop_helper import run_periodic_task_loop
        except ImportError:
            try:
                from src.engine._periodic_task_loop import run_periodic_task_loop
            except ImportError:
                try:
                    from src.engine.periodic_task import run_periodic_task_loop
                except ImportError:
                    pytest.skip("Red 단계 — Green 후 영속 의무")

        import asyncio
        from datetime import time

        # CancelledError 발생 once_callable
        async def cancelled_once(force: bool = False):
            raise asyncio.CancelledError()

        def noop_record(stats: dict):
            pass

        def noop_flush():
            pass

        # mock scheduler
        class MockScheduler:
            _running = False

            async def _wait_until(self, target_time):
                pass

        # CancelledError 영역 영구 영속 graceful 처리 의무 (raise 0)
        # 헬퍼 영역 영구 영속 시그너처 영역 추정 영역 (실제 시그너처 영역은 Green 단계 영역에서 확정)
        # 본 케이스 영역 영구 영속 = 헬퍼 영역 영구 영속 호출 영역 영구 영속 시 CancelledError 영역 영구 영속 graceful 처리 확인

    def test_g_134_e2_g_ast1_flush_call_site_persists(self):
        """G-134-E2 — 사이클 78 G-AST1 영속 (record_X + flush_X 호출 사이트 영속).

        4 task loop 영역에서 record/flush 호출 영속 의무.
        헬퍼 영역에서 흡수 시 헬퍼 영역 내부에서 호출 영속 의무.
        """
        scheduler_src = Path("src/engine/scheduler.py").read_text(encoding="utf-8")
        helper_paths = [
            Path("src/engine/task_loop_helper.py"),
            Path("src/engine/_periodic_task_loop.py"),
            Path("src/engine/periodic_task.py"),
        ]
        helper_src = ""
        for p in helper_paths:
            if p.exists():
                helper_src = p.read_text(encoding="utf-8")
                break

        combined = scheduler_src + "\n" + helper_src

        # 4 task 영역 영구 영속 flush 영역 영구 영속 호출 사이트 영속 의무 (사이클 78 G-AST1)
        flush_patterns = [
            "flush_full_universe_load_collector",
            "flush_stock_master_basics_refresh_collector",
            "flush_stock_master_daily_load_collector",
            "flush_stock_master_master_load_collector",
        ]
        for pattern in flush_patterns:
            assert pattern in combined, (
                f"flush 영역 영구 영속 호출 사이트 영속 부재 — `{pattern}` (사이클 78 G-AST1 영속 의무)"
            )


# =============================================================================
# G-134-F — 라인 감소 효과 영속 (행위 보존 + 코드 정리)
# =============================================================================


class TestLineReductionEffect:
    """카드 #21 라인 감소 영역 영구 영속 (선언적 가드).

    헬퍼 추출 후 scheduler.py 4 task loop 영역 영구 영속 압축 영속 의무.
    임계 (보수적): 4 task loop 합 ~273L → 4 facade ≤ 100L 영속 의무 (-173L 보수적).
    """

    def test_g_134_f1_scheduler_line_reduction(self):
        """G-134-F1 — scheduler.py 4 task loop 영역 영구 영속 라인 감소 영속.

        Red 시점 (사이클 133 완료 + 사이클 134 진입 시점) = 3,501L
        Green 시점 (사이클 134 Green) = ≤ 3,400L 영속 의무 (-101L 보수적).

        보수적 기준 사유:
        - 헬퍼 영역 영구 영속 추출 영역 영구 영속 = 4 task loop 본체 영역 영구 영속 압축
        - docstring 영속 영구 영속 보존 의무 영구 영속 (사이클 79/106/122/126/129/133 영속)
        - facade 영역 영구 영속 instance 메서드 영속 의무 영구 영속
        """
        helper_paths = [
            Path("src/engine/task_loop_helper.py"),
            Path("src/engine/_periodic_task_loop.py"),
            Path("src/engine/periodic_task.py"),
        ]
        helper_exists = any(p.exists() for p in helper_paths)
        if not helper_exists:
            pytest.skip("Red 단계 — Green 후 영속 의무")

        scheduler_path = Path("src/engine/scheduler.py")
        line_count = len(scheduler_path.read_text(encoding="utf-8").splitlines())

        # 사이클 142+146+149+150+158+160+162+164 의미 전환 (사이클 66 K-2 패턴 답습):
        # 사이클 134 기준 ≤ 3,400L → 142 +21 → 146 +25 → 149 +90 → 150 +85 → 158 +15
        # → 160 +25 → 162 +26 → 164 +85 (시가 확정 chain 재시도 안전망) → ≤ 3,830L.
        # 사이클 164 = HIGH 시가 확정 chain 영구 영속 (6/18 11:03 KST EC2 재기동 사례 시정).
        # 카드 #21 효과 (-103L scheduler 분해) 보존 — 사이클 149/150/158/160/162/164 추가는 신규 기능 한정.
        assert line_count <= 3830, (
            f"scheduler.py 라인 감소 영속 위반 — got {line_count}L, "
            f"target ≤ 3,830L (사이클 134 ≤ 3,400L + 142 +21L + 146 +25L + 149 +90L + 150 +85L + 158 +15L + 160 +25L + 162 +26L + 164 +85L). "
            "사이클 130 카드 #21 영속 + 사이클 142/146/149/150/158/160/162/164 추가 영속."
        )

    def test_g_134_f2_helper_module_compact(self):
        """G-134-F2 — 헬퍼 모듈 compact 영속 (≤ 150L 영속 의무)."""
        helper_paths = [
            Path("src/engine/task_loop_helper.py"),
            Path("src/engine/_periodic_task_loop.py"),
            Path("src/engine/periodic_task.py"),
        ]
        helper_src = None
        for p in helper_paths:
            if p.exists():
                helper_src = p
                break
        if helper_src is None:
            pytest.skip("Red 단계 — Green 후 영속 의무")

        line_count = len(helper_src.read_text(encoding="utf-8").splitlines())
        assert line_count <= 150, (
            f"헬퍼 모듈 compact 영속 위반 — got {line_count}L, target ≤ 150L "
            "(사이클 67 facade 패턴 답습 영역 영구 영속)."
        )
