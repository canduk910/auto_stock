"""사이클 89 M-4 — 사이클 64 `_collect_protected_tickers_for_scanner` 영속 정합.

명세 (`_workspace/red/cycle89_stock_master_500_universe.md`):

domain-expert 자문 영속:
- 사이클 64 Q1 옵션 D 3중 안전망 영속
- 보유 ticker 가격필터 graceful 통과 영속
- 500 universe 적재해도 사이클 64 영역 변경 0

기대 동작 (Green, 사이클 90):
- `_collect_protected_tickers_for_scanner()` 헬퍼 영속 (사이클 64 시그너처)
- 보유 + 익일청산 + sold_today ticker 통합 반환

Red 상태 (사이클 89): 사이클 64 헬퍼 부재 시 FAIL (영속 위반).

영속 의무:
- 사이클 64 영속 (3중 안전망: 헬퍼 + early-return + AST keyword 가드)
- 사이클 81 bfdy_clpr 키 시정 영속 (보유 ticker graceful 통과 정합)
- 매매 안전성 영향 0 (scanner 단계 영역)
"""
from __future__ import annotations

import inspect

import pytest

pytestmark = pytest.mark.unit


def test_m4_cycle64_protected_tickers_helper_persists():
    """M-4: 사이클 64 `_collect_protected_tickers_for_scanner` 헬퍼 영속.

    검증 매트릭스:
    - `src/engine/scanner.py::_collect_protected_tickers_for_scanner` 영속
    - 함수 시그너처 = `() -> set[str]` 영속
    - 사이클 89 시정해도 사이클 64 헬퍼 본체 무변경

    Red 상태 (사이클 89): 헬퍼 부재 시 FAIL (사이클 64 영속 위반).

    Green (사이클 90): backend-dev 가 사이클 89 시정해도 사이클 64 영역 무변경 → PASS.

    영속 의무:
    - 사이클 64 Q1 옵션 D 3중 안전망 영속
    - 사이클 81 bfdy_clpr 키 시정 영속
    """
    try:
        from src.engine.scanner import _collect_protected_tickers_for_scanner
    except ImportError:
        pytest.fail(
            "\n사이클 89 M-4 위반 — 사이클 64 `_collect_protected_tickers_for_scanner` "
            "헬퍼 부재:\n"
            "  영속 의무: 사이클 89 시정해도 사이클 64 헬퍼 영역 무변경\n"
            "  - `src/engine/scanner.py::_collect_protected_tickers_for_scanner` 영속\n"
            "  - Q1 옵션 D 3중 안전망 (헬퍼 + early-return + AST 가드) 영속"
        )

    # 함수 호출 가능 + return 타입 = set
    assert callable(_collect_protected_tickers_for_scanner), (
        "\n사이클 89 M-4 위반 — `_collect_protected_tickers_for_scanner` callable 아님\n"
        "  영속 의무: 사이클 64 헬퍼 시그너처 영속"
    )

    # 실제 호출 → set 반환
    result = _collect_protected_tickers_for_scanner()
    assert isinstance(result, set), (
        f"\n사이클 89 M-4 위반 — return 타입 결함:\n"
        f"  기대: set\n"
        f"  실제: {type(result).__name__}\n"
        f"  영속 의무: 사이클 64 시그너처 `-> set[str]`"
    )

    # 사이클 89 시정 영역이 사이클 64 헬퍼 본체 침범 0
    source = inspect.getsource(_collect_protected_tickers_for_scanner)
    # 사이클 89 신규 식별자 침범 검증
    forbidden_in_helper = [
        "fetch_top_500_universe",
        "_universe_eager_refresh",
        "stock_master_metrics",
    ]
    for ident in forbidden_in_helper:
        assert ident not in source, (
            f"\n사이클 89 M-4 위반 — 사이클 64 헬퍼 본체 침범 발견:\n"
            f"  `{ident}` 식별자가 `_collect_protected_tickers_for_scanner` 본체에 포함\n"
            f"  영속 의무: 사이클 89 시정해도 사이클 64 영역 무변경"
        )
