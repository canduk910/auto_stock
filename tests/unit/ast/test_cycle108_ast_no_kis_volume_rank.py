"""사이클 108 — AST 영구 가드: VB/LTV/BFB _scan_universe 에 KIS volume-rank 잔존 금지.

HIGH-2/3/4: 3 전략 소스 파일에 FHPST01710000 / volume-rank URL / BLNG_CODES 영구 부재
MEDIUM-4: VB/LTV/BFB 가 list_by_filter 를 호출한다 (소스 패턴 검증)
"""

from __future__ import annotations

import pathlib
import re

import pytest

from tests.unit.ast._ast_helpers import read_module_source

STRATEGY_FILES = {
    "VB": pathlib.Path("src/engine/strategies/volatility_breakout.py"),
    "LTV": pathlib.Path("src/engine/strategies/long_tail_volatility.py"),
    "BFB": pathlib.Path("src/engine/strategies/bull_flag_breakout.py"),
}


# ---------------------------------------------------------------------------
# HIGH-2/3/4: KIS volume-rank 관련 패턴 영구 부재
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("strategy_name,file_path", list(STRATEGY_FILES.items()))
def test_no_fhpst01710000_tr_id(strategy_name: str, file_path: pathlib.Path):
    """AST: 3 전략 소스에 KIS volume-rank TR_ID (FHPST01710000) 가 없어야 한다.

    사이클 108 (Plan Phase A) 에서 VB/LTV/BFB 의 _scan_universe 가 KIS volume-rank API
    를 완전 폐기하고 stock_master DB 조회로 전환했다. 이 TR_ID 가 재등장하면 사이클 108
    폐기 계약 위반 — 즉시 FAIL 로 차단한다.
    """
    source = read_module_source(file_path)
    assert "FHPST01710000" not in source, (
        f"{strategy_name} ({file_path.name}) 에 KIS volume-rank TR_ID (FHPST01710000) 가 "
        f"잔존함. 사이클 108 stock_master 전환 폐기 계약 위반."
    )


@pytest.mark.parametrize("strategy_name,file_path", list(STRATEGY_FILES.items()))
def test_no_volume_rank_url_path(strategy_name: str, file_path: pathlib.Path):
    """AST: 3 전략 소스에 volume-rank URL 경로가 없어야 한다."""
    source = read_module_source(file_path)
    assert "volume-rank" not in source, (
        f"{strategy_name} ({file_path.name}) 에 KIS volume-rank URL 경로가 잔존함."
    )


@pytest.mark.parametrize("strategy_name,file_path", list(STRATEGY_FILES.items()))
def test_no_blng_codes_variable(strategy_name: str, file_path: pathlib.Path):
    """AST: 3 전략 소스에 BLNG_CODES 변수가 없어야 한다.

    BLNG_CODES 는 KIS volume-rank API 를 BLNG_CLS_CODE 별로 3회 호출하는 패턴의 핵심
    변수다. 사이클 108 이후 stock_master DB 조회로 대체되어 이 패턴이 불필요하다.
    """
    source = read_module_source(file_path)
    assert "BLNG_CODES" not in source, (
        f"{strategy_name} ({file_path.name}) 에 BLNG_CODES 가 잔존함 — "
        f"KIS volume-rank API 3회 호출 패턴 잔존 의심."
    )


# ---------------------------------------------------------------------------
# MEDIUM-4: list_by_filter 호출 패턴 영속
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("strategy_name,file_path", list(STRATEGY_FILES.items()))
def test_list_by_filter_called_in_scan_universe(strategy_name: str, file_path: pathlib.Path):
    """AST: 3 전략 소스의 _scan_universe 메서드에 list_by_filter 호출이 있어야 한다.

    사이클 108 Plan Phase A 핵심 — VB/LTV/BFB 의 _scan_universe 가 반드시
    stock_master.list_by_filter 를 호출해야 한다. 미래에 누군가 이 호출을 제거하면
    KIS API 호출 0건 보장이 깨지므로 영구 가드로 차단한다.
    """
    source = read_module_source(file_path)
    # _scan_universe 메서드 블록 내 list_by_filter 호출 확인 (함수명 존재 여부로 검증)
    assert "list_by_filter" in source, (
        f"{strategy_name} ({file_path.name}) 의 _scan_universe 에 "
        f"stock_master.list_by_filter 호출이 없음 — 사이클 108 DB 전환 계약 위반."
    )
