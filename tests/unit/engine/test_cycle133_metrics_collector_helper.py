"""사이클 133 (2026-06-15) — metrics 3 모듈 공통 헬퍼 추출 + master metrics 신규 격리 가드.

사용자 결정 영속:
- Q1=A commit `c7ace5a` push + CI success 4분 23초 영속
- Q2=B 사이클 133 = 카드 #24 metrics 3 모듈 공통 헬퍼 추출 (LOW, -218L)

배경 (사이클 130 권고 카드 #24 영속):
- `stock_master_metrics.py` 146L (사이클 89 universe collector)
- `stock_master_basics_metrics.py` 74L (사이클 126 basics collector)
- `stock_master_daily_metrics.py` 78L (사이클 122 daily collector)
- 합계 298L, 3 모듈 동일 record/flush 페어 패턴 (사이클 74 답습)
- 사이클 129 master_load_once 영역 metrics collector 부재 = 일관성 결함

영속 의무 매트릭스:
- 사이클 67 facade re-export only 패턴 답습 (`__all__` 영속)
- 사이클 74 collector 패턴 영속 (record/flush 페어 + 빈 윈도우 skip 사이클 76 Q2)
- 사이클 78 G-AST1 영속 (flush 호출 사이트 ≥ 1 영속 의무)
- 사이클 68 KST 영속 (`now_kst_iso` / `KST` import 영속 + L-3 가드)
- 사이클 88 G-REJECT graceful 영역 단위
- 매매 안전성 영향 0 (로깅 영역 한정)

행위 보존 의무 (refactor 가정):
- 4 collector 모두 호출자 영역 변경 0 (`from src.engine.X_metrics import record_X, flush_X_collector` 영속)
- emit prefix 영속 (`[stock_master_universe_summary]` / `[full_universe_load_summary]` /
  `[stock_master_basics_refresh_flushed]` / `[stock_master_daily_load_summary]` + 신규 master)
- summary 키 영속 (각 collector 별 영구 영속)
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest


# =============================================================================
# G-133-A — 공통 헬퍼 모듈 영속 영구 영속
# =============================================================================


class TestMetricsCollectorHelperPersistence:
    """공통 헬퍼 모듈 `metrics_collector.py` (또는 동등) 영속 영구 영속."""

    def test_g_133_a1_helper_module_exists(self):
        """G-133-A1 — 공통 헬퍼 모듈 영속.

        후보 경로: `src/engine/metrics_collector.py` 또는 `src/engine/_metrics_helpers.py`.
        """
        candidates = [
            Path("src/engine/metrics_collector.py"),
            Path("src/engine/_metrics_helpers.py"),
        ]
        existing = [p for p in candidates if p.exists()]
        assert len(existing) >= 1, (
            f"공통 헬퍼 모듈 영속 부재 — 후보: {[str(p) for p in candidates]}. "
            "사이클 133 카드 #24 영속 의무."
        )

    def test_g_133_a2_make_collector_helper_exported(self):
        """G-133-A2 — `make_metrics_collector` (또는 동등 팩토리) 영속.

        시그너처 후보: `make_metrics_collector(prefix: str, *, mode: str = "single") -> (record_fn, flush_fn)`
        또는 `MetricsCollector` 클래스 영속.
        """
        try:
            from src.engine import metrics_collector as helper_module
        except ImportError:
            try:
                from src.engine import _metrics_helpers as helper_module
            except ImportError:
                pytest.fail(
                    "공통 헬퍼 모듈 import 부재 — 사이클 133 카드 #24 영속 의무."
                )

        # 팩토리 함수 또는 클래스 영속 의무
        has_factory = hasattr(helper_module, "make_metrics_collector")
        has_class = hasattr(helper_module, "MetricsCollector")
        assert has_factory or has_class, (
            "make_metrics_collector 팩토리 함수 또는 MetricsCollector 클래스 영속 부재 — "
            "사이클 133 카드 #24 영속 의무."
        )


# =============================================================================
# G-133-B — 4 facade 모듈 영속 영구 영속 (master metrics 신규 포함)
# =============================================================================


class TestFourMetricsFacadePersistence:
    """4 metrics facade 모듈 영속 영구 영속 — universe / basics / daily / master."""

    def test_g_133_b1_universe_metrics_facade_persists(self):
        """G-133-B1 — `stock_master_metrics.py` facade 영속 + 4 헬퍼 export."""
        from src.engine import stock_master_metrics as m

        # 사이클 89/101 헬퍼 4 영속 의무 (사이클 67 facade re-export 패턴 답습)
        assert hasattr(m, "record_universe_refresh")
        assert hasattr(m, "flush_universe_collector")
        assert hasattr(m, "record_full_universe_load_summary")
        assert hasattr(m, "flush_full_universe_load_collector")

    def test_g_133_b2_basics_metrics_facade_persists(self):
        """G-133-B2 — `stock_master_basics_metrics.py` facade 영속 + 헬퍼 2 export."""
        from src.engine import stock_master_basics_metrics as m

        # 사이클 126 헬퍼 2 영속 의무
        assert hasattr(m, "record_stock_master_basics_refresh")
        assert hasattr(m, "flush_stock_master_basics_refresh_collector")

    def test_g_133_b3_daily_metrics_facade_persists(self):
        """G-133-B3 — `stock_master_daily_metrics.py` facade 영속 + 헬퍼 2 export."""
        from src.engine import stock_master_daily_metrics as m

        # 사이클 122 헬퍼 2 영속 의무
        assert hasattr(m, "record_stock_master_daily_load")
        assert hasattr(m, "flush_stock_master_daily_load_collector")

    def test_g_133_b4_master_metrics_facade_persists_newly(self):
        """G-133-B4 — `stock_master_master_metrics.py` facade 신규 영속 + 헬퍼 2 export.

        사이클 129 master_load_once 영역 metrics collector 일관성 결함 해소 영구 영속.
        """
        try:
            from src.engine import stock_master_master_metrics as m
        except ImportError:
            pytest.fail(
                "src/engine/stock_master_master_metrics.py 신규 모듈 영속 부재 — "
                "사이클 133 카드 #24 master metrics 일관성 결함 해소 영속 의무."
            )

        # 사이클 129 master 헬퍼 2 영속 의무 (4 collector 일관성)
        assert hasattr(m, "record_stock_master_master_load"), (
            "record_stock_master_master_load 영속 부재 — 사이클 133 일관성 영속 의무"
        )
        assert hasattr(m, "flush_stock_master_master_load_collector"), (
            "flush_stock_master_master_load_collector 영속 부재 — 사이클 133 일관성 영속 의무"
        )


# =============================================================================
# G-133-C — 헬퍼 동작 영속 (record/flush 페어 + 빈 윈도우 skip)
# =============================================================================


class TestCollectorBehaviorPreservation:
    """공통 헬퍼 동작 영속 영구 영속 — record/flush + 빈 윈도우 skip + emit prefix."""

    def test_g_133_c1_basics_record_and_flush(self, caplog):
        """G-133-C1 — basics record + flush emit prefix 영속 (사이클 126 행위 보존)."""
        import logging
        from src.engine import stock_master_basics_metrics as m

        # 초기화 (격리)
        m.flush_stock_master_basics_refresh_collector()  # 빈 윈도우 skip 의무

        # record + flush
        with caplog.at_level(logging.INFO, logger="src.engine.scheduler"):
            m.record_stock_master_basics_refresh({
                "total": 2697,
                "updated": 2697,
                "skipped": 0,
                "failed": 0,
                "elapsed_ms": 825000,
            })
            m.flush_stock_master_basics_refresh_collector()

        # emit prefix 영속 의무 (사이클 126 영속)
        log_text = "\n".join(r.getMessage() for r in caplog.records)
        assert "[stock_master_basics_refresh_flushed]" in log_text, (
            f"basics emit prefix 영속 위반 — got logs={log_text!r}"
        )
        assert "total=2697" in log_text
        assert "updated=2697" in log_text

    def test_g_133_c2_daily_record_and_flush(self, caplog):
        """G-133-C2 — daily record + flush emit prefix 영속 (사이클 122 행위 보존)."""
        import logging
        from src.engine import stock_master_daily_metrics as m

        m.flush_stock_master_daily_load_collector()  # 빈 윈도우 skip

        with caplog.at_level(logging.INFO, logger="src.engine.scheduler"):
            m.record_stock_master_daily_load({
                "total": 2697,
                "fetched": 2697,
                "upserted_rows": 269700,
                "skipped_fresh": 0,
                "failed": 0,
                "elapsed_ms": 270000,
                "mode": "incremental",
            })
            m.flush_stock_master_daily_load_collector()

        log_text = "\n".join(r.getMessage() for r in caplog.records)
        assert "[stock_master_daily_load_summary]" in log_text, (
            f"daily emit prefix 영속 위반 — got logs={log_text!r}"
        )
        assert "mode=incremental" in log_text

    def test_g_133_c3_master_record_and_flush_newly(self, caplog):
        """G-133-C3 — master record + flush emit prefix 영속 (사이클 129 master_load_once 일관성).

        사이클 133 신규 일관성 결함 해소 영역 영구 영속.
        """
        import logging

        try:
            from src.engine import stock_master_master_metrics as m
        except ImportError:
            pytest.skip("Red 단계 — Green 후 영속 의무")

        m.flush_stock_master_master_load_collector()  # 빈 윈도우 skip

        with caplog.at_level(logging.INFO, logger="src.engine.scheduler"):
            m.record_stock_master_master_load({
                "kospi_count": 940,
                "kosdaq_count": 1759,
                "total": 2699,
                "updated": 2699,
                "failed": 0,
                "elapsed_ms": 25000,
            })
            m.flush_stock_master_master_load_collector()

        log_text = "\n".join(r.getMessage() for r in caplog.records)
        assert "[stock_master_master_load_summary]" in log_text, (
            f"master emit prefix 영속 위반 — got logs={log_text!r}"
        )

    def test_g_133_c4_empty_window_skip_pattern(self, caplog):
        """G-133-C4 — 빈 윈도우 skip 패턴 영속 (사이클 76 Q2 영속 답습)."""
        import logging
        from src.engine import stock_master_basics_metrics as m

        # 초기 flush — 비어있어야 emit 0건 영속
        m.flush_stock_master_basics_refresh_collector()  # 초기화

        with caplog.at_level(logging.INFO, logger="src.engine.scheduler"):
            # 두 번째 flush — 빈 윈도우, emit 0건 영속 의무
            m.flush_stock_master_basics_refresh_collector()

        log_text = "\n".join(r.getMessage() for r in caplog.records)
        assert "[stock_master_basics_refresh_flushed]" not in log_text, (
            f"빈 윈도우 skip 영속 위반 — got logs={log_text!r}. 사이클 76 Q2 영속."
        )


# =============================================================================
# G-133-D — AST 영구 가드 (사이클 78 G-AST1 답습 + 단방향 의존)
# =============================================================================


class TestAstStaticGuards:
    """사이클 78 G-AST1 영속 + 단방향 의존 + facade re-export only AST 가드."""

    def test_g_133_d1_facade_re_export_only_pattern(self):
        """G-133-D1 — 4 facade 모듈 모두 헬퍼 위임 또는 동등 패턴 영속.

        사이클 67 facade re-export only 패턴 답습 (`__all__` 또는 헬퍼 호출 영속).
        """
        from src.engine import (
            stock_master_metrics,
            stock_master_basics_metrics,
            stock_master_daily_metrics,
        )

        # 4 facade 모듈 모두 동일 logger 영속 의무 (사이클 60 I1 영속)
        for module in (
            stock_master_metrics,
            stock_master_basics_metrics,
            stock_master_daily_metrics,
        ):
            assert hasattr(module, "logger"), (
                f"{module.__name__} logger 영속 위반 — 사이클 60 I1 영속 의무"
            )
            assert module.logger.name == "src.engine.scheduler", (
                f"{module.__name__} logger 영속 위반 — got name={module.logger.name!r}"
            )

    def test_g_133_d2_g_ast1_flush_call_site_persists(self):
        """G-133-D2 — 사이클 78 G-AST1 영속 (`record_X` 정의 모듈은 대응 `flush_X` 호출 사이트 ≥ 1).

        4 collector 모두 lifecycle hook 또는 task loop 영역에서 flush 호출 영속 의무.
        scheduler.py 영역에서 검증.
        """
        # refactor-review B1 (2026-08-09) — task loop 본체(flush 호출)는 data_load_tasks.py 위임 이관.
        scheduler_src = Path("src/engine/scheduler.py").read_text(encoding="utf-8") + (
            Path("src/engine/data_load_tasks.py").read_text(encoding="utf-8")
        )

        # 4 flush 호출 사이트 ≥ 1 영속 의무 (사이클 78 G-AST1 영속)
        flush_call_patterns = [
            "flush_full_universe_load_collector",
            "flush_stock_master_basics_refresh_collector",
            "flush_stock_master_daily_load_collector",
        ]
        for pattern in flush_call_patterns:
            assert pattern in scheduler_src, (
                f"scheduler.py 영역에 `{pattern}` 호출 영속 부재 — "
                "사이클 78 G-AST1 영속 의무 위반"
            )

    def test_g_133_d3_master_flush_call_site_newly(self):
        """G-133-D3 — 사이클 133 신규 master flush 호출 사이트 영속.

        사이클 129 master_load_once task loop 영역에서 master metrics flush 호출 영속 의무.
        """
        scheduler_src = Path("src/engine/scheduler.py").read_text(encoding="utf-8")

        # master metrics 영역 import 영속
        has_import = (
            "stock_master_master_metrics" in scheduler_src
            or "record_stock_master_master_load" in scheduler_src
        )
        if not has_import:
            pytest.skip("Red 단계 — Green 후 영속 의무 (master metrics 미통합)")

        assert "flush_stock_master_master_load_collector" in scheduler_src, (
            "scheduler.py 영역 master flush 호출 사이트 영속 부재 — "
            "사이클 133 일관성 영속 의무"
        )


# =============================================================================
# G-133-E — 라인 감소 효과 영속 영역 (행위 보존 + 코드 정리)
# =============================================================================


class TestLineReductionEffect:
    """카드 #24 라인 감소 영역 영구 영속 (선언적 가드).

    헬퍼 추출 + facade 전환 후 3 기존 모듈 + 1 신규 master 총 라인 감소 영속.

    임계 (보수적):
    - 기존 3 모듈 합 298L → ≤ 200L 영속 의무 (-98L 보수적 기준)
    - master 신규 ≤ 40L 영속 의무 (facade re-export)
    - 합 (3 기존 + 1 master + 헬퍼 모듈) ≤ 360L 영속 의무 (원본 298L + 헬퍼 + 신규 ≈ 360L 보수적)
    """

    def test_g_133_e1_three_facade_line_reduction(self):
        """G-133-E1 — 3 기존 facade 모듈 라인 감소 영속.

        원본 합 298L → ≤ 200L 영속 의무 (-98L 보수적).
        """
        try:
            from src.engine import metrics_collector  # noqa: F401
        except ImportError:
            try:
                from src.engine import _metrics_helpers  # noqa: F401
            except ImportError:
                pytest.skip("Red 단계 — Green 후 영속 의무")

        paths = [
            Path("src/engine/stock_master_metrics.py"),
            Path("src/engine/stock_master_basics_metrics.py"),
            Path("src/engine/stock_master_daily_metrics.py"),
        ]
        total = sum(len(p.read_text(encoding="utf-8").splitlines()) for p in paths)

        assert total <= 200, (
            f"3 facade 모듈 라인 감소 영속 위반 — got {total}L, target ≤ 200L "
            "(원본 298L -98L 보수적). 사이클 130 카드 #24 영속."
        )

    def test_g_133_e2_master_metrics_facade_compact(self):
        """G-133-E2 — master metrics facade 모듈 compact 영속.

        ≤ 40L 영속 의무 (facade re-export only 패턴).
        """
        master_path = Path("src/engine/stock_master_master_metrics.py")
        if not master_path.exists():
            pytest.skip("Red 단계 — Green 후 영속 의무")

        line_count = len(master_path.read_text(encoding="utf-8").splitlines())
        assert line_count <= 40, (
            f"master metrics facade 모듈 compact 영속 위반 — got {line_count}L, "
            f"target ≤ 40L. 사이클 67 facade re-export 패턴 답습 영속 의무."
        )
