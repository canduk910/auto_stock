"""사이클 89 M-7 — `[stock_master_bulk_refresh]` + `[stock_master_universe_summary]` 1행 emit.

명세 (`_workspace/red/cycle89_stock_master_500_universe.md`):

domain-expert 자문 A6 권고:
- `[stock_master_bulk_refresh] universe=500 kospi=250 kosdaq=250 securities=480
  etf_excluded=15 fetched=N elapsed_ms=M` 개장 전 1회 INFO
- `[stock_master_universe_summary] total=500 fresh=N stale=M held=K next_day=L`
  5분 주기 1행 (사이클 74 collector 패턴 답습)

기대 동작 (Green, 사이클 90):
- 신규 모듈 `src/engine/stock_master_metrics.py` 도입
- `record_universe_refresh(stats)` + `flush_universe_collector()` 헬퍼
- 5분 윈도우 누적 + emit 1행

Red 단계 (사이클 89): 신규 모듈 미존재 → ImportError → FAIL.

영속 의무:
- 사이클 74 collector 패턴 직답습 (record/flush)
- 사이클 78 G-AST1 flush 호출 사이트 영속
- 매매 안전성 영향 0 (로깅 영역)
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit


def test_m7_stock_master_metrics_module_exists():
    """M-7: `src/engine/stock_master_metrics.py` 신규 모듈 도입 + 헬퍼 함수 export.

    검증 매트릭스:
    - `src/engine/stock_master_metrics.py` 모듈 import 가능
    - `record_universe_refresh(stats)` + `flush_universe_collector()` 함수 export

    Red 상태 (사이클 89): 모듈 미존재 → ImportError → FAIL.

    Green (사이클 90): backend-dev 가 신규 모듈 도입 → PASS.

    영속 의무:
    - 사이클 74 collector 패턴 답습
    - A6 권고 영속 (2 신규 prefix 도입)
    """
    try:
        from src.engine import stock_master_metrics  # noqa: F401
    except ImportError:
        pytest.fail(
            "\n사이클 89 M-7 Red 상태 — `src/engine/stock_master_metrics.py` 모듈 부재:\n"
            "  Green (사이클 90): backend-dev 가 신규 모듈 도입 의무.\n"
            "  - `src/engine/stock_master_metrics.py` (~50L)\n"
            "  - record_universe_refresh(stats: dict)\n"
            "  - flush_universe_collector()\n"
            "  - emit prefix 2종:\n"
            "    * [stock_master_bulk_refresh] (개장 전 1회 INFO)\n"
            "    * [stock_master_universe_summary] (5분 주기)\n"
            "  - 사이클 74 collector 패턴 답습"
        )

    # 헬퍼 함수 export 확인
    try:
        from src.engine.stock_master_metrics import (  # noqa: F401
            flush_universe_collector,
            record_universe_refresh,
        )
    except ImportError as e:
        pytest.fail(
            f"\n사이클 89 M-7 위반 — 신규 모듈 헬퍼 함수 export 누락:\n"
            f"  {type(e).__name__}: {e}\n\n"
            f"  Green 의무:\n"
            f"  - record_universe_refresh(stats: dict) 함수 정의\n"
            f"  - flush_universe_collector() 함수 정의\n"
            f"  - 사이클 74 collector 패턴 답습"
        )

    # 함수 호출 가능 (스모크)
    assert callable(record_universe_refresh), (
        "\n사이클 89 M-7 위반 — `record_universe_refresh` callable 아님\n"
        "  사이클 74 collector 패턴 답습 의무"
    )
    assert callable(flush_universe_collector), (
        "\n사이클 89 M-7 위반 — `flush_universe_collector` callable 아님\n"
        "  사이클 74 collector 패턴 답습 의무"
    )
