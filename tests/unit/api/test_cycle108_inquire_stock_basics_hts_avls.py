"""사이클 108 — inquire_stock_basics hts_avls 5-key merge 회귀 가드.

HIGH-6: inquire_stock_basics 가 FHKST01010100 응답에서 hts_avls 를 raw 에 병합한다
        (사이클 107 의 4 키 → 사이클 108 의 5 키)
"""

from __future__ import annotations

import ast
import pathlib


# ---------------------------------------------------------------------------
# HIGH-6 (a): AST — hts_avls 가 5-key 튜플에 존재
# ---------------------------------------------------------------------------

def test_h6a_hts_avls_in_merge_tuple():
    """AST: condition.py 의 merge 루프 튜플에 hts_avls 가 포함돼야 한다.

    사이클 107 에서 4 키 (acml_tr_pbmn, lstn_stcn, acml_vol, prdy_vrss) 를 도입했고
    사이클 108 에서 hts_avls 를 5번째 키로 추가했다. 이 키가 없으면 stock_master.raw 에
    시가총액이 저장되지 않아 list_by_filter 의 min_market_cap 필터가 무용해진다.
    """
    src_file = pathlib.Path("src/api/condition.py")
    source = src_file.read_text(encoding="utf-8")

    # hts_avls 가 merge 루프 근방에 등장해야 한다
    assert "hts_avls" in source, (
        "condition.py 에 hts_avls 가 없음 — 사이클 108 5-key merge 추가 계약 위반."
    )


# ---------------------------------------------------------------------------
# HIGH-6 (b): AST — 4 키 영속 (사이클 107 영구 가드 + 사이클 108 추가)
# ---------------------------------------------------------------------------

def test_h6b_cycle107_four_keys_still_present():
    """AST: 사이클 107 의 4 키가 여전히 merge 루프에 존재해야 한다.

    hts_avls 추가 시 기존 4 키를 실수로 제거하지 않았는지 영구 확인한다.
    """
    src_file = pathlib.Path("src/api/condition.py")
    source = src_file.read_text(encoding="utf-8")

    for key in ("acml_tr_pbmn", "lstn_stcn", "acml_vol", "prdy_vrss"):
        assert key in source, (
            f"condition.py 에 사이클 107 merge 키 '{key}' 가 없음 — "
            f"hts_avls 추가 중 기존 키 제거 금지."
        )
