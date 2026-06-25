"""사이클 176 — _stock_master_basics_refresh_once 기존 raw 머지 보존 회귀 가드.

거래대금 결손 시정 (사이클 B):
- 근본원인: `inquire_stock_basics` 가 `merged_raw = dict(ctpf_output)` 로 raw 를
  CTPF 에서 신규 빌드 (기존 DB raw 미read). 개장 전 FHKST `acml_tr_pbmn=0` →
  사이클 145 `_ZERO_VALUE_SKIP_KEYS` 가드가 `continue` skip → merged_raw 거래대금
  부재. `stock_master.upsert_one` 이 `upsert(on_conflict="ticker")` 로 raw 통째
  교체 → 거래대금 영구 소멸 (사이클 145 "기존 raw 보존" 은 read-merge 부재로 무효).
  부팅 전 basics refresh 가 매일 전 종목 거래대금 삭제 → VB/LTV/donchian/BFB
  universe 0 (운영 실측 거래대금 보유 6/3573).
- 시정: `_stock_master_basics_refresh_once` 가 이미 `list_all` 로 로드한 기존 row
  의 raw 를 보관 → upsert 전 `{**existing_raw, **basics.raw}` 머지 → cycle 145 가
  skip 한 키 (거래대금/거래량 등) 를 기존 값에서 보존. 새 키는 우선.
- blast radius 최소 (scanner refresh 한정, upsert_one 전역 의미 변경 회피).
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from src.models.stock import StockBasics

pytestmark = pytest.mark.unit


def _basics(ticker: str, raw: dict) -> StockBasics:
    return StockBasics(
        ticker=ticker, name="", excg_dvsn_cd="",
        nxt_tradable=False, krx_halted=False, admin_item=False, raw=raw,
    )


@pytest.mark.asyncio
async def test_g176_merge1_preserves_existing_pbmn_when_new_lacks():
    """G-176-MERGE-1: 기존 raw 거래대금 존재 + 새 basics.raw 부재(개장 전 0 skip) → 보존."""
    from src.engine import scanner

    async def fake_list_all(limit=100, offset=0):
        if offset == 0:
            return [{
                "ticker": "005930",
                "raw": {"acml_tr_pbmn": "1000000", "acml_vol": "500", "hts_avls": "999"},
            }]
        return []

    # 개장 전 FHKST=0 skip 시뮬: 새 raw 에 거래대금 없음, 다른 키만
    new_basics = _basics("005930", {"hts_avls": "1234", "bfdy_clpr": "70000"})
    upsert_mock = AsyncMock(return_value=None)

    with patch("src.db.stock_master.list_all", side_effect=fake_list_all), \
         patch("src.api.condition.inquire_stock_basics", AsyncMock(return_value=new_basics)), \
         patch("src.db.stock_master.upsert_one", upsert_mock):
        await scanner._stock_master_basics_refresh_once()

    assert upsert_mock.await_count == 1
    saved = upsert_mock.await_args.args[0]
    # 기존 거래대금/거래량 보존 (silent 결함 시정)
    assert saved.raw.get("acml_tr_pbmn") == "1000000"
    assert saved.raw.get("acml_vol") == "500"
    # 새 키 반영
    assert saved.raw.get("hts_avls") == "1234"
    assert saved.raw.get("bfdy_clpr") == "70000"


@pytest.mark.asyncio
async def test_g176_merge2_new_value_overrides_existing():
    """G-176-MERGE-2: 새 basics.raw 에 거래대금 신값(장후 FHKST>0) → 신값 우선."""
    from src.engine import scanner

    async def fake_list_all(limit=100, offset=0):
        if offset == 0:
            return [{"ticker": "005930", "raw": {"acml_tr_pbmn": "1000000"}}]
        return []

    new_basics = _basics("005930", {"acml_tr_pbmn": "2000000", "hts_avls": "1234"})
    upsert_mock = AsyncMock(return_value=None)

    with patch("src.db.stock_master.list_all", side_effect=fake_list_all), \
         patch("src.api.condition.inquire_stock_basics", AsyncMock(return_value=new_basics)), \
         patch("src.db.stock_master.upsert_one", upsert_mock):
        await scanner._stock_master_basics_refresh_once()

    saved = upsert_mock.await_args.args[0]
    assert saved.raw.get("acml_tr_pbmn") == "2000000"  # 신값 우선 (보존 아님)


@pytest.mark.asyncio
async def test_g176_merge3_new_ticker_no_existing_raw():
    """G-176-MERGE-3: 기존 raw 부재(신규 ticker, raw 키 없음) → basics.raw 그대로 (크래시 0)."""
    from src.engine import scanner

    async def fake_list_all(limit=100, offset=0):
        if offset == 0:
            return [{"ticker": "005930"}]  # raw 키 없음
        return []

    new_basics = _basics("005930", {"hts_avls": "1234"})
    upsert_mock = AsyncMock(return_value=None)

    with patch("src.db.stock_master.list_all", side_effect=fake_list_all), \
         patch("src.api.condition.inquire_stock_basics", AsyncMock(return_value=new_basics)), \
         patch("src.db.stock_master.upsert_one", upsert_mock):
        summary = await scanner._stock_master_basics_refresh_once()

    assert summary["updated"] == 1
    saved = upsert_mock.await_args.args[0]
    assert saved.raw.get("hts_avls") == "1234"


@pytest.mark.asyncio
async def test_g176_preserve_all_zero_skip_keys():
    """G-176-PRESERVE-ALL: cycle 145 _ZERO_VALUE_SKIP_KEYS 15키 전부 보존."""
    from src.engine import scanner
    from src.api.condition import _ZERO_VALUE_SKIP_KEYS

    existing = {k: "100" for k in _ZERO_VALUE_SKIP_KEYS}
    existing["hts_avls"] = "999"

    async def fake_list_all(limit=100, offset=0):
        if offset == 0:
            return [{"ticker": "005930", "raw": dict(existing)}]
        return []

    # 새 raw 는 skip 키 전부 부재 (개장 전 0 skip)
    new_basics = _basics("005930", {"hts_avls": "1234"})
    upsert_mock = AsyncMock(return_value=None)

    with patch("src.db.stock_master.list_all", side_effect=fake_list_all), \
         patch("src.api.condition.inquire_stock_basics", AsyncMock(return_value=new_basics)), \
         patch("src.db.stock_master.upsert_one", upsert_mock):
        await scanner._stock_master_basics_refresh_once()

    saved = upsert_mock.await_args.args[0]
    for k in _ZERO_VALUE_SKIP_KEYS:
        assert saved.raw.get(k) == "100", f"{k} 보존 실패 (거래대금 결손 재발)"


@pytest.mark.asyncio
async def test_g176_ast_merge_present_in_refresh():
    """G-176-AST: refresh 함수에 기존 raw 머지 로직 정적 존재 (silent 회귀 영구 차단)."""
    import ast
    import inspect
    from src.engine import scanner

    src = inspect.getsource(scanner._stock_master_basics_refresh_once)
    tree = ast.parse(src)
    # existing_raw_by_ticker 식별자 + dict 언패킹 머지 ({**a, **b}) 존재
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    assert "existing_raw_by_ticker" in names, "기존 raw 보관 dict 부재"
    has_dict_merge = any(
        isinstance(n, ast.Dict) and any(k is None for k in n.keys)
        for n in ast.walk(tree)
    )
    assert has_dict_merge, "raw 머지 ({**existing, **new}) 패턴 부재"
