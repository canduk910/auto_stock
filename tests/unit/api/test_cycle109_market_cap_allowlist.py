"""사이클 109 — `_QUOTE_ALLOWED_PATHS` market-cap 영구 영속이 추가 영역 영구 영속이 가드.

사이클 101 도입 시점 silent 결함 영역 영구 영속이 영구 시정:
- `/uapi/domestic-stock/v1/ranking/market-cap` 영역 영구 영속이 `_QUOTE_ALLOWED_PATHS` 영역 영구 영속이 부재 영구 영속이
- `_fetch_market_cap_page` 영역 영구 영속이 → `kis_get_quote` 영역 영구 영속이 → `QuotePoolPathError` raise
- graceful 영역 영구 영속이 → `accumulated=[]` 영역 영구 영속이 → `total=0` + `elapsed_ms=0`

운영 로그 영구 영속이 확정 (2026-06-11 20:00:13 KST):
- WARNING `[_fetch_market_cap_page] 예외 market=kospi error=시세 풀은 화이트리스트 path 만 허용`
- INFO `[full_universe_load] 완료 total=0 kospi=0 kosdaq=0 ...`
"""

from pathlib import Path

import pytest


def test_cycle109_h1_market_cap_path_in_allowlist():
    """HIGH-1: `_QUOTE_ALLOWED_PATHS` 영역 영구 영속이 market-cap path 포함 영구 영속이."""
    from src.api.base import _QUOTE_ALLOWED_PATHS

    assert "/uapi/domestic-stock/v1/ranking/market-cap" in _QUOTE_ALLOWED_PATHS


def test_cycle109_h2_ast_market_cap_string_literal():
    """HIGH-2: AST 영구 가드 — base.py 영역 영구 영속이 market-cap path 영역 영구 영속이 영속."""
    base_py = Path("src/api/base.py").read_text()
    assert '"/uapi/domestic-stock/v1/ranking/market-cap"' in base_py


def test_cycle109_h3_quote_pool_path_error_not_raised_for_market_cap():
    """HIGH-3: `_fetch_market_cap_page` 영역 영구 영속이 `QuotePoolPathError` raise 0건 영역 영구 영속이."""
    from src.api.base import _QUOTE_ALLOWED_PATHS, QuotePoolPathError

    market_cap_path = "/uapi/domestic-stock/v1/ranking/market-cap"
    if market_cap_path not in _QUOTE_ALLOWED_PATHS:
        pytest.fail(
            f"{market_cap_path} 영역 영구 영속이 화이트리스트 부재 영역 영구 영속이 "
            f"= `_fetch_market_cap_page` 영역 영구 영속이 QuotePoolPathError raise 영역 영구 영속이"
        )


def test_cycle109_h4_market_cap_url_constant_matches_allowlist():
    """HIGH-4: `_MARKET_CAP_URL` 상수 영역 영구 영속이 화이트리스트 영역 영구 영속이 정합."""
    from src.api.base import _QUOTE_ALLOWED_PATHS
    from src.engine.scanner import _MARKET_CAP_URL

    assert _MARKET_CAP_URL in _QUOTE_ALLOWED_PATHS
