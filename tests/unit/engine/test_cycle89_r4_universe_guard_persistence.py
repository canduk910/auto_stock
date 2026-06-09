"""사이클 89 M-3 — 사이클 32 R4 universe guard 영속 검증.

명세 (`_workspace/red/cycle89_stock_master_500_universe.md`):

domain-expert 자문 A4 권고 영속:
- 사이클 32 R4 universe guard = `_evaluate_universe_guard`
- 보유 / 익일청산 ticker 절대 보호 (positives only)
- stale>5 + today_volume<10,000 → 자동 unsubscribe (보유/익일청산 제외)
- 사이클 89 500 universe 적재 = R4 평가 영역 확장 (positives only)
- `_universe_excluded_today` 등록 + `[universe_excluded]` INFO 영속

기대 동작 (Green, 사이클 90):
- 500 universe 적재해도 R4 영역 영향 0 (DB upsert 영역만)
- 보유/익일청산 ticker 절대 보호 (영속 매트릭스)

Red 단계 (사이클 89): production 영역 변경 검증 영역 (R4 함수 영역 무변경)
→ R4 영속 함수 부재 시 FAIL (영속 확인 의무).

영속 의무:
- 사이클 32 R4 영속 (`src/engine/stale_universe_guard.py::_evaluate_universe_guard`)
- 사이클 67 stale_manager 분해 영속 (영역 분리)
- 매매 안전성 영향 0 (보유/익일청산 절대 보호)
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit


def test_m3_cycle32_r4_universe_guard_persists_after_cycle89():
    """M-3: 사이클 32 R4 universe guard 함수 영역 영속 (사이클 89 변경 0 확인).

    검증 매트릭스:
    - `src/engine/stale_universe_guard.py::_evaluate_universe_guard` 영속
    - 사이클 67 분해 영속 (영역 분리)
    - 사이클 89 시정 영역 영향 0

    Red 상태 (사이클 89): R4 함수 부재 시 FAIL (사이클 32 영속 위반).

    Green (사이클 90): backend-dev 가 사이클 89 시정해도 R4 영역 무변경 → PASS.

    영속 의무:
    - 사이클 32 R4 영속
    - 사이클 67 stale_manager 분해 영속 (영역 분리)
    """
    # 사이클 32 R4 = stale_universe_guard 모듈 영속
    try:
        from src.engine.stale_universe_guard import (  # noqa: F401
            evaluate_universe_guard,
        )
    except ImportError:
        pytest.fail(
            "\n사이클 89 M-3 위반 — 사이클 32 R4 `evaluate_universe_guard` 함수 부재:\n"
            "  영속 의무: 사이클 89 시정해도 사이클 32 R4 영역 무변경\n"
            "  - `src/engine/stale_universe_guard.py` (사이클 67 분해 영속) 영속 의무\n"
            "  - 보유/익일청산 절대 보호 영속"
        )

    # 사이클 67 분해 영속: stale_manager facade re-export 영속 영역
    try:
        from src.engine.stale_manager import (  # noqa: F401
            evaluate_universe_guard as _re_export,
        )
    except ImportError:
        pytest.fail(
            "\n사이클 89 M-3 위반 — 사이클 67 stale_manager facade re-export 영속 위반:\n"
            "  영속 의무: 사이클 89 시정해도 사이클 67 facade 영역 무변경\n"
            "  - `src/engine/stale_manager.py` re-export 영속"
        )

    # 사이클 89 시정 영역 = scanner / scheduler / stock_master_metrics
    # = R4 영역과 분리 영속 확인
    # (사이클 89 신규 코드가 stale_universe_guard 영역 침범 0)
    import inspect
    from src.engine import stale_universe_guard
    source = inspect.getsource(stale_universe_guard)
    # 사이클 89 신규 식별자 (universe_eager_refresh / stock_master_metrics) 가
    # stale_universe_guard 본체에 침범 0
    forbidden_identifiers = [
        "universe_eager_refresh",
        "stock_master_metrics",
        "fetch_top_500_universe",
    ]
    for ident in forbidden_identifiers:
        assert ident not in source, (
            f"\n사이클 89 M-3 위반 — 사이클 32 R4 영역 침범 발견:\n"
            f"  `{ident}` 식별자가 `src/engine/stale_universe_guard.py` 에 포함\n"
            f"  영속 의무: 사이클 89 시정해도 사이클 32 R4 영역 무변경\n"
            f"  - 영역 분리 영속 (사이클 67 패턴)"
        )
