"""사이클 179 — 정적 가드: 거래량순위(volume-rank, FHPST01710000) dead code 영구 폐기.

사이클 108 (2026-06-11) 에서 VB/LTV/BFB `_scan_universe` 가 거래량순위 API →
`stock_master.list_by_filter` (DB) 로 전환되며 거래량순위 TR 호출이 **0건 dead** 가 됐다.
사이클 179 = `src/api/base.py` 시세 풀 화이트리스트(`_QUOTE_ALLOWED_PATHS`)에 잔존하던
volume-rank path 폐기 + 재도입 영구 차단.

사이클 109 `test_cycle109_market_cap_allowlist.py` (live path 존재 단언) 의 역방향 가드.
사이클 167 dead code 폐기 + 영구 가드 패턴 답습.

가드는 **데이터 구조(`_QUOTE_ALLOWED_PATHS` frozenset 항목)** 만 검사한다 — source 텍스트
전수 스캔(주석/설명 false positive, 사이클 167 교훈)이 아니라 실제 화이트리스트 엔트리만.

- G-179-1: `_QUOTE_ALLOWED_PATHS` 에 volume-rank path 정확 부재 (재도입 차단)
- G-179-2: 화이트리스트 어떤 엔트리도 "volume-rank" 미포함 (변형 철자 차단)
- G-179-3: 회귀 보존 — live path (market-cap / inquire-ccnl / fluctuation) 영속
"""

from __future__ import annotations

_VOLUME_RANK_PATH = "/uapi/domestic-stock/v1/quotations/volume-rank"


def test_volume_rank_path_absent_from_quote_allowlist():
    """G-179-1: 시세 풀 화이트리스트에 거래량순위 path 정확 부재 (dead code 폐기)."""
    from src.api.base import _QUOTE_ALLOWED_PATHS

    assert _VOLUME_RANK_PATH not in _QUOTE_ALLOWED_PATHS, (
        "거래량순위(volume-rank) path 가 _QUOTE_ALLOWED_PATHS 에 재등장함 — "
        "사이클 108 DB 전환으로 호출처 0건 dead. 사이클 179 폐기 계약 위반."
    )


def test_no_allowlist_entry_contains_volume_rank():
    """G-179-2: 화이트리스트 어떤 엔트리도 'volume-rank' 미포함 (변형 철자 재도입 차단)."""
    from src.api.base import _QUOTE_ALLOWED_PATHS

    offending = [p for p in _QUOTE_ALLOWED_PATHS if "volume-rank" in p]
    assert not offending, (
        f"_QUOTE_ALLOWED_PATHS 에 volume-rank 변형 path 잔존: {offending} — "
        "사이클 179 dead code 폐기 위반."
    )


def test_live_quote_paths_preserved():
    """G-179-3: 회귀 보존 — 사이클 109 market-cap + inquire-ccnl + fluctuation live path 영속."""
    from src.api.base import _QUOTE_ALLOWED_PATHS

    assert "/uapi/domestic-stock/v1/ranking/market-cap" in _QUOTE_ALLOWED_PATHS
    assert "/uapi/domestic-stock/v1/quotations/inquire-ccnl" in _QUOTE_ALLOWED_PATHS
    assert "/uapi/domestic-stock/v1/ranking/fluctuation" in _QUOTE_ALLOWED_PATHS
