"""사이클 C1 — base.py `_QUOTE_ALLOWED_PATHS` finance 5 path 화이트리스트 Red 가드.

Red 명세: `_workspace/red/cycleC1_financial_infra.md`
`tests/unit/api/test_cycle109_market_cap_allowlist.py` 답습 (frozenset 엔트리 + AST).

배경: finance.py 5 TR fetch 는 시세성 풀(`kis_get_quote` → `_request_via_quote_pool`)
경유. 5 finance path 가 `_QUOTE_ALLOWED_PATHS` 화이트리스트에 부재하면 `QuotePoolPathError`
raise (사이클 109 선례 — market-cap 누락 시 _fetch_market_cap_page total=0 폭주).

가드:
- 5 finance path 전수 frozenset 엔트리 존재
- 누락 시 QuotePoolPathError 재도입 방지 (AST/source 텍스트)
- 자금 안전: 매매/잔고/체결 path 는 절대 화이트리스트 추가 안 함 (분리 유지)

production base.py 미수정 → 5 path 부재로 전부 FAIL (Red).
매매 안전성 무영향 (시세성 read 경로 한정, 사이클 38).
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit


_FINANCE_PATHS = [
    "/uapi/domestic-stock/v1/finance/income-statement",
    "/uapi/domestic-stock/v1/finance/balance-sheet",
    "/uapi/domestic-stock/v1/finance/profit-ratio",
    "/uapi/domestic-stock/v1/finance/stability-ratio",
    "/uapi/domestic-stock/v1/finance/other-major-ratios",
]


# ---------------------------------------------------------------------------
# G-C1-ALLOW-1 — 5 finance path frozenset 엔트리 (사이클 109 답습)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("path", _FINANCE_PATHS)
def test_finance_path_in_allowlist(path):
    """_QUOTE_ALLOWED_PATHS 에 finance 5 path 각각 포함."""
    from src.api.base import _QUOTE_ALLOWED_PATHS

    assert path in _QUOTE_ALLOWED_PATHS, (
        f"{path} 화이트리스트 부재 — kis_get_quote → QuotePoolPathError raise "
        f"(사이클 109 market-cap 누락 선례 재현 위험)."
    )


# ---------------------------------------------------------------------------
# G-C1-ALLOW-2 — 5 path 전수 (개수 정합)
# ---------------------------------------------------------------------------
def test_all_five_finance_paths_present():
    """finance 5 path 전수 존재 (부분 누락 = 그 TR silent QuotePoolPathError)."""
    from src.api.base import _QUOTE_ALLOWED_PATHS

    missing = [p for p in _FINANCE_PATHS if p not in _QUOTE_ALLOWED_PATHS]
    assert not missing, f"finance 화이트리스트 누락: {missing}"


# ---------------------------------------------------------------------------
# G-C1-ALLOW-3 — QuotePoolPathError raise 0건 (finance path 진입 안전)
# ---------------------------------------------------------------------------
def test_quote_pool_path_error_not_raised_for_finance():
    """finance path 가 화이트리스트에 있어 QuotePoolPathError 미발생 (사이클 109 H3 답습)."""
    from src.api.base import _QUOTE_ALLOWED_PATHS, QuotePoolPathError  # noqa: F401

    for path in _FINANCE_PATHS:
        if path not in _QUOTE_ALLOWED_PATHS:
            pytest.fail(
                f"{path} 화이트리스트 부재 = _request_via_quote_pool QuotePoolPathError raise. "
                f"finance.py 5 TR fetch 가 total=0 silent (사이클 109 선례)."
            )


# ---------------------------------------------------------------------------
# G-C1-ALLOW-4 — AST/source 텍스트 (5 path 문자열 존재, 재도입/누락 영구 방지)
# ---------------------------------------------------------------------------
def test_ast_finance_path_literals_in_base_py():
    """src/api/base.py source 에 finance 5 path 문자열 리터럴 존재 (사이클 109 H2 답습)."""
    base_py = Path("src/api/base.py").read_text(encoding="utf-8")
    for path in _FINANCE_PATHS:
        assert f'"{path}"' in base_py, (
            f"base.py 에 finance path 리터럴 '{path}' 부재 — 화이트리스트 직접 등록 의무."
        )


# ---------------------------------------------------------------------------
# G-C1-ALLOW-5 — 자금 안전: 매매/잔고/체결 path 절대 미추가 (분리 유지)
# ---------------------------------------------------------------------------
def test_trading_paths_never_in_allowlist():
    """finance 추가로 매매/잔고/체결 path 가 화이트리스트에 오염되지 않았는지 (자금 안전)."""
    from src.api.base import _QUOTE_ALLOWED_PATHS

    forbidden = [
        "/uapi/domestic-stock/v1/trading/order-cash",
        "/uapi/domestic-stock/v1/trading/order-rvsecncl",
        "/uapi/domestic-stock/v1/trading/inquire-balance",
        "/uapi/domestic-stock/v1/trading/inquire-psbl-order",
        "/uapi/domestic-stock/v1/trading/inquire-daily-ccld",
    ]
    leaked = [p for p in forbidden if p in _QUOTE_ALLOWED_PATHS]
    assert not leaked, (
        f"매매/잔고/체결 path 가 시세 풀 화이트리스트에 오염: {leaked} — 자금 안전 정책 위반."
    )
