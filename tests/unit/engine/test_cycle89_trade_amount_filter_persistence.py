"""사이클 89 M-5 — 사이클 65 `_apply_trade_amount_filter` 영속 정합.

명세 (`_workspace/red/cycle89_stock_master_500_universe.md`):

domain-expert 자문 영속:
- 사이클 65 trade_amount_filter 영속
- 500 universe 적재 후 trade_amount 임계 정확 작동
- 사이클 65 디폴트 = 0 (비활성), 운영자 1억/5억/10억 권장값 영속

기대 동작 (Green, 사이클 90):
- `_apply_trade_amount_filter()` 헬퍼 영속 (사이클 65 시그너처)
- 사이클 89 시정해도 사이클 65 영역 변경 0

Red 상태 (사이클 89): 사이클 65 헬퍼 부재 시 FAIL (영속 위반).

영속 의무:
- 사이클 65 영속 (스캐너 가격필터/거래대금필터 시정 영역)
- 사이클 81 bfdy_clpr 키 시정 영속 (정합 영역)
- 매매 안전성 영향 0 (scanner 단계 영역)
"""
from __future__ import annotations

import inspect

import pytest

pytestmark = pytest.mark.unit


def test_m5_cycle65_trade_amount_filter_helper_persists():
    """M-5: 사이클 65 `_apply_trade_amount_filter` 헬퍼 영속.

    검증 매트릭스:
    - `src/engine/scanner.py::_apply_trade_amount_filter` 영속
    - 사이클 89 시정해도 사이클 65 헬퍼 본체 무변경

    Red 상태 (사이클 89): 헬퍼 부재 시 FAIL (사이클 65 영속 위반).

    Green (사이클 90): backend-dev 가 사이클 89 시정해도 사이클 65 영역 무변경 → PASS.

    영속 의무:
    - 사이클 65 trade_amount_filter 영속
    - 사이클 81 bfdy_clpr 키 시정 영속 (정합 영역)
    """
    try:
        from src.engine.scanner import _apply_trade_amount_filter
    except ImportError:
        pytest.fail(
            "\n사이클 89 M-5 위반 — 사이클 65 `_apply_trade_amount_filter` 헬퍼 부재:\n"
            "  영속 의무: 사이클 89 시정해도 사이클 65 헬퍼 영역 무변경\n"
            "  - `src/engine/scanner.py::_apply_trade_amount_filter` 영속\n"
            "  - 디폴트 = 0 (비활성), 운영자 1억/5억/10억 권장값 영속"
        )

    # 함수 호출 가능
    assert callable(_apply_trade_amount_filter), (
        "\n사이클 89 M-5 위반 — `_apply_trade_amount_filter` callable 아님\n"
        "  영속 의무: 사이클 65 헬퍼 시그너처 영속"
    )

    # 사이클 89 시정 영역이 사이클 65 헬퍼 본체 침범 0
    source = inspect.getsource(_apply_trade_amount_filter)
    forbidden_in_helper = [
        "fetch_top_500_universe",
        "_universe_eager_refresh",
        "stock_master_metrics",
    ]
    for ident in forbidden_in_helper:
        assert ident not in source, (
            f"\n사이클 89 M-5 위반 — 사이클 65 헬퍼 본체 침범 발견:\n"
            f"  `{ident}` 식별자가 `_apply_trade_amount_filter` 본체에 포함\n"
            f"  영속 의무: 사이클 89 시정해도 사이클 65 영역 무변경"
        )
