"""사이클 176 — 거래대금 장전 보존 *end-to-end* 정밀 검증.

기존 `test_cycle176_basics_refresh_raw_merge.py` 5건은 `inquire_stock_basics` 를
통째 mock → scanner 머지만 격리 검증. 본 파일은 **실제 `inquire_stock_basics`
(KIS `kis_get_quote` 응답만 mock) + scanner `_stock_master_basics_refresh_once`
머지를 통째로 태워**, cycle 145 `_ZERO_VALUE_SKIP_KEYS` 0-skip ↔ scanner 머지의
*연결고리*를 검증한다. (오늘 6/26 장중 재시작은 FHKST 실값이라 보존 미트리거 →
장전 FHKST=0 시나리오를 코드로 재현해 정밀 확인.)

검증 시나리오:
- 장전(FHKST acml_tr_pbmn="0") + 기존 DB raw 에 거래대금 존재 → 보존 (핵심).
- 장중(FHKST 실값) → 신값 덮어씀 (보존 아님).
- 비-skip 키(hts_avls) → 항상 FHKST 덮어씀.
- 신규 ticker(기존 raw 부재) → 크래시 0.
- 엣지: FHKST None → 기존 덮어씀(현행 동작 = 잠재 갭, FHKST 는 장전 "0" 반환).
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

pytestmark = pytest.mark.unit

# CTPF1002R 응답 (식별/상장/관리 — 거래대금 키 부재. 사이클 107 정본)
_CTPF = {
    "pdno": "005930",
    "prdt_abrv_name": "삼성전자",
    "excg_dvsn_cd": "1",
    "cptt_trad_tr_psbl_yn": "Y",
    "nxt_tr_stop_yn": "N",
    "tr_stop_yn": "N",
    "admn_item_yn": "N",
    "bfdy_clpr": "70000",
}

# 어제 적재된 기존 DB raw (거래대금/거래량 보유)
_EXISTING_RAW = {
    "acml_tr_pbmn": "5000000",   # 어제 거래대금
    "acml_vol": "800",           # 어제 거래량
    "hts_avls": "2999999",       # 어제 시총
    "per": "9.9",
    "bfdy_clpr": "69000",
}


def _make_kis_mock(fhkst_output: dict):
    """tr_id 기반 kis_get_quote mock (CTPF → 식별, FHKST → 시세)."""
    async def fake_kis_get_quote(url, tr_id, params, **kw):
        if tr_id == "CTPF1002R":
            return {"output": dict(_CTPF)}
        if tr_id == "FHKST01010100":
            return {"output": dict(fhkst_output)}
        return {}
    return fake_kis_get_quote


async def _run_refresh(fhkst_output: dict, *, existing_raw=_EXISTING_RAW):
    """실제 inquire_stock_basics + scanner 머지를 통째로 실행하고 upsert 된 raw 반환."""
    from src.engine import scanner

    async def fake_list_all(limit=100, offset=0):
        if offset == 0:
            row = {"ticker": "005930"}
            if existing_raw is not None:
                row["raw"] = dict(existing_raw)
            return [row]
        return []

    upsert_mock = AsyncMock(return_value=None)
    # inquire_stock_basics 는 *실제* 호출 (KIS 계층만 mock) → cycle 145 가드 실동작
    with patch("src.db.stock_master.list_all", side_effect=fake_list_all), \
         patch("src.api.condition.kis_get_quote", side_effect=_make_kis_mock(fhkst_output)), \
         patch("src.db.stock_master.upsert_one", upsert_mock):
        await scanner._stock_master_basics_refresh_once()

    assert upsert_mock.await_count == 1, "upsert_one 1회 호출 기대"
    return upsert_mock.await_args.args[0].raw


@pytest.mark.asyncio
async def test_e2e_premarket_preserves_trade_amount():
    """핵심 — 장전 FHKST acml_tr_pbmn="0"/acml_vol="0" → 기존 거래대금/거래량 보존 (end-to-end)."""
    # 장전: 거래대금/거래량 0, 시총(hts_avls)은 실값
    fhkst = {"acml_tr_pbmn": "0", "acml_vol": "0", "hts_avls": "3000000"}
    raw = await _run_refresh(fhkst)

    # ★ cycle 145 가 "0" skip → scanner 머지가 기존값 보존
    assert raw.get("acml_tr_pbmn") == "5000000", "장전 거래대금 보존 실패 (결손 재발)"
    assert raw.get("acml_vol") == "800", "장전 거래량 보존 실패"
    # 비-skip 키(시총)는 FHKST 실값으로 덮어씀
    assert raw.get("hts_avls") == "3000000", "비-skip 키(시총) FHKST 덮어쓰기 실패"
    # CTPF 식별 키도 정상 merge (bfdy_clpr CTPF 우선)
    assert raw.get("bfdy_clpr") == "70000"


@pytest.mark.asyncio
async def test_e2e_premarket_preserves_empty_string():
    """장전 FHKST acml_tr_pbmn="" (빈 문자열) → 0 취급 skip → 기존 보존."""
    fhkst = {"acml_tr_pbmn": "", "acml_vol": ""}
    raw = await _run_refresh(fhkst)
    assert raw.get("acml_tr_pbmn") == "5000000", "빈 문자열 → 0 skip → 보존 실패"
    assert raw.get("acml_vol") == "800"


@pytest.mark.asyncio
async def test_e2e_market_hours_overrides_with_real_value():
    """장중 FHKST acml_tr_pbmn 실값(콤마 포함) → 기존값 덮어씀 (보존 아님)."""
    fhkst = {"acml_tr_pbmn": "8,000,000", "acml_vol": "1200"}
    raw = await _run_refresh(fhkst)
    assert raw.get("acml_tr_pbmn") == "8,000,000", "장중 실값 덮어쓰기 실패"
    assert raw.get("acml_vol") == "1200"


@pytest.mark.asyncio
async def test_e2e_new_ticker_no_existing_raw():
    """신규 ticker(기존 raw 부재) → 크래시 0, basics.raw 그대로."""
    fhkst = {"acml_tr_pbmn": "0", "acml_vol": "0", "hts_avls": "3000000"}
    raw = await _run_refresh(fhkst, existing_raw=None)
    # 기존 거래대금 없음 → 장전 0 skip 되어 키 자체 부재 (보존할 것 없음, 정상)
    assert "acml_tr_pbmn" not in raw or raw.get("acml_tr_pbmn") in (None, "0", "")
    assert raw.get("hts_avls") == "3000000"


@pytest.mark.asyncio
async def test_e2e_fhkst_none_preserves_existing():
    """사이클 177 하드닝 — FHKST acml_tr_pbmn=None(비숫자) → skip → 기존 거래대금 보존.

    cycle 145 가드 except 분기가 `pass`(merge) → `continue`(skip) 전환 (177).
    skip-키는 전부 숫자 필드라 None/비숫자=junk → 덮어쓰지 않고 기존값 보존.
    (FHKST 는 장전에 "0" 반환이 정상이나, 만약 null 반환 시에도 거래대금 소실 차단.)
    """
    fhkst = {"acml_tr_pbmn": None, "acml_vol": "0"}
    raw = await _run_refresh(fhkst)
    # 177 하드닝: None → skip → 기존 보존 (종전 None-override 갭 시정)
    assert raw.get("acml_tr_pbmn") == "5000000", "None → skip → 기존 거래대금 보존 (cycle 177)"
    assert raw.get("acml_vol") == "800", "acml_vol='0' 도 보존"
