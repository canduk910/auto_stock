"""사이클 96 M-3 — `_universe_eager_refresh_loop` chain 영속 (MEDIUM).

명세 (`_workspace/red/cycle96_resurrect_industry_code_with_pagination.md`):

- 사이클 93 호출 chain 영속 = `fetch_top_500_universe()` → `_universe_eager_refresh_loop(tickers)`
- 사이클 96 영역 복원 영역에서도 chain 시그너처 변경 0
- `_universe_eager_refresh_loop(candidates)` 단일 인자 영속

기대 동작 (Green, backend-dev 인계):
- `_universe_eager_refresh_loop` 시그너처 = `(candidates: list[str])` 영속
- 사이클 89 본체 행위 영속 (24h TTL fresh skip + 50ms Rate Limit + graceful)

영속 의무:
- 사이클 93 호출 chain 변경 0
- 사이클 89 본체 변경 0
- 매매 안전성 영향 0
"""
from __future__ import annotations

import inspect

import pytest

pytestmark = pytest.mark.unit


@pytest.mark.xfail(
    strict=False,
    reason=(
        "사이클 101 Q69=B — `_universe_eager_refresh_loop` 영구 폐기 "
        "(scanner.py + scheduler.py 양쪽). "
        "사이클 96 시점 시그너처 영속 검증 의도 영속 보존 (사이클 66 K-2 패턴 답습)."
    ),
)
def test_m3_universe_eager_refresh_loop_signature_unchanged():
    """M-3.a: `_universe_eager_refresh_loop` 시그너처 = `(candidates)` 영속.

    검증 매트릭스:
    - 시그너처 파라미터 영역 = `['candidates']`
    - 사이클 93 chain 변경 0

    영속 의무: 사이클 96 영역 복원 시 chain 변경 0.
    """
    from src.engine import scanner

    sig = inspect.signature(scanner._universe_eager_refresh_loop)
    params = list(sig.parameters.keys())

    assert params == ["candidates"], (
        f"\n사이클 96 M-3.a 위반 — `_universe_eager_refresh_loop` 시그너처 변경:\n"
        f"  기대: ['candidates'] (사이클 89/93 영속)\n"
        f"  실제: {params}\n"
        f"  영속 의무: 사이클 93 호출 chain 변경 0"
    )


@pytest.mark.xfail(
    strict=False,
    reason=(
        "사이클 101 Q68=A+Q69=B — `fetch_top_500_universe` 영구 폐기. "
        "사이클 96 시점 시그너처 영속 검증 의도 영속 보존 (사이클 66 K-2 패턴 답습)."
    ),
)
def test_m3_fetch_top_500_universe_signature_unchanged():
    """M-3.b: `fetch_top_500_universe()` 시그너처 영속 (인자 없음).

    검증 매트릭스:
    - 시그너처 파라미터 영역 = 빈 list (인자 없음)
    - 반환 타입 = list[str]

    영속 의무: 외부 호출자 (사이클 93 chain) 변경 0.
    """
    from src.engine import scanner

    sig = inspect.signature(scanner.fetch_top_500_universe)
    params = list(sig.parameters.keys())

    assert params == [], (
        f"\n사이클 96 M-3.b 위반 — `fetch_top_500_universe` 시그너처 변경:\n"
        f"  기대: [] (인자 없음, 사이클 89 영속)\n"
        f"  실제: {params}\n"
        f"  영속 의무: 외부 호출자 chain 변경 0"
    )
