"""사이클 81 (2026-06-08) Red — G 카테고리: 운영 실데이터 회귀 (1 케이스).

> **선행 명세**: `_workspace/red/cycle81_price_filter_key_fix.md` (§G-1)
> **자문 응답**: domain-expert (stock_master 67 키 검증 = prdy_clpr ✗ / bfdy_clpr ✓)

요구 행위:
- G-1: 005930 raw 67 키 fixture → `bfdy_clpr` 정본 키 존재 PASS + `prdy_clpr` 미존재 PASS
       → `_apply_price_filter` 가 정본 키 추출하여 평가 의무 검증

위험 등급 MEDIUM (운영 실데이터 회귀 차단).
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# 005930 raw 67 키 fixture — domain-expert 자문 확정 CTPF1002R 응답 키 매트릭스
# ---------------------------------------------------------------------------
# 핵심: bfdy_clpr 존재 (정본) + prdy_clpr 미존재 (CTPF1002R 응답에 없음)
SAMSUNG_RAW_67KEYS = {
    "pdno": "005930",
    "prdt_type_cd": "300",
    "prdt_name": "삼성전자보통주",
    "prdt_name120": "삼성전자보통주",
    "prdt_abrv_name": "삼성전자",
    "prdt_eng_name": "Samsung Electronics Co.,Ltd",
    "prdt_eng_name120": "Samsung Electronics Co.,Ltd",
    "prdt_eng_abrv_name": "Samsung Electronics",
    "std_pdno": "KR7005930003",
    "shtn_pdno": "005930",
    "prdt_sale_stat_cd": "01",
    "prdt_risk_grade_cd": "",
    "prdt_clsf_cd": "201",
    "prdt_clsf_name": "코스피",
    "sale_strt_dt": "19750611",
    "sale_end_dt": "99991231",
    "wrap_asst_type_cd": "",
    "ivst_prdt_type_cd": "501",
    "ivst_prdt_type_cd_name": "주식",
    "frst_erlm_dt": "19750611",
    "scts_mket_lstg_dt": "19750611",
    "scts_mket_lstg_abol_dt": "",
    "kosdaq_mket_lstg_dt": "",
    "kosdaq_mket_lstg_abol_dt": "",
    "frbd_mket_lstg_dt": "",
    "frbd_mket_lstg_abol_dt": "",
    "reits_kind_cd": "",
    "etf_dvsn_cd": "0",
    "oilf_fund_yn": "N",
    "idx_bztp_lcls_cd": "001",
    "idx_bztp_mcls_cd": "001",
    "idx_bztp_scls_cd": "013",
    "stck_kind_cd": "101",
    "mfnd_opng_dt": "",
    "mfnd_end_dt": "",
    "dpsi_erlm_cncl_dt": "",
    "etf_cu_qty": "",
    "prdt_name_oend": "",
    "etf_txtn_type_cd": "",
    "etf_type_cd": "",
    "lstg_abol_dt": "",
    "nwst_odst_dvsn_cd": "01",
    "sbst_pric": "60360",
    "thco_sbst_pric": "60360",
    "thco_sbst_pric_chng_dt": "20251013",
    "tr_stop_yn": "N",
    "admn_item_yn": "N",
    "thdt_clpr": "76300",
    "bfdy_clpr": "75500",            # ← 정본 키 (전일 종가)
    "clpr_chng_dt": "20251010",
    "std_idst_clsf_cd": "C26110",
    "std_idst_clsf_cd_name": "반도체",
    "idx_bztp_lcls_cd_name": "유가증권",
    "idx_bztp_mcls_cd_name": "전기.전자",
    "idx_bztp_scls_cd_name": "반도체와반도체장비",
    "ocr_no": "",
    "crfd_item_yn": "N",
    "elec_scty_yn": "Y",
    "issu_istt_cd": "00000",
    "etf_chas_erng_rt_dbnb": "",
    "etf_etn_ivst_heed_item_yn": "N",
    "stln_int_rt_dvsn_cd": "0",
    "frnr_psnl_lmt_rt": "0.000",
    "lstg_rqsr_issu_istt_cd": "",
    "lstg_rqsr_item_cd": "",
    "trst_istt_issu_istt_cd": "",
    "nxt_tr_stop_yn": "N",
}
# 명시 의도: `prdy_clpr` 키 부재 검증 (CTPF1002R 응답에 없음)
assert "prdy_clpr" not in SAMSUNG_RAW_67KEYS
assert "bfdy_clpr" in SAMSUNG_RAW_67KEYS


def _make_basics_from_raw(ticker: str, raw: dict):
    """StockBasics mock — 운영 실데이터 raw fixture 적용."""
    from src.models.stock import StockBasics
    return StockBasics(
        ticker=ticker, name=raw.get("prdt_abrv_name", ""),
        excg_dvsn_cd="1", nxt_tradable=True,
        krx_halted=False, admin_item=False,
        raw=raw,
    )


def _make_pf(min_price=0, max_price=0):
    from src.db.system_config import PriceFilter
    return PriceFilter(min_price=min_price, max_price=max_price)


# ---------------------------------------------------------------------------
# 사이클 183 — 캐시 격리 (stale-4 전환 후 모듈 캐시 오염 차단, 의미 전환 0)
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _isolate_price_filter_cache_g1():
    """_apply_price_filter 캐시 격리 — 테스트 간 TTL 캐시 오염 차단."""
    from src.engine import scanner
    if hasattr(scanner, "invalidate_price_filter_cache_scanner"):
        scanner.invalidate_price_filter_cache_scanner()
    yield
    if hasattr(scanner, "invalidate_price_filter_cache_scanner"):
        scanner.invalidate_price_filter_cache_scanner()



# ---------------------------------------------------------------------------
# G-1: 005930 운영 실데이터 → bfdy_clpr 추출 + above_max 차단
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_G1_real_005930_raw_extracts_bfdy_clpr(monkeypatch):
    """G-1: 005930 운영 실데이터 raw 67 키 fixture →
    `_apply_price_filter` 가 `bfdy_clpr=75500` 정본 키 추출 → max=50,000 → above_max 차단.

    `prdy_clpr` 키 부재 사전 검증 (CTPF1002R 응답 정합성).

    Red 상태: prdy_clpr 미존재 → graceful 통과 → 차단 안 됨 = FAIL.
    Green 상태: bfdy_clpr=75500 추출 → max=50000 → above_max 차단 = PASS.
    """
    from src.engine import scanner

    candidates = ["005930"]
    pf = _make_pf(min_price=0, max_price=50_000)  # bfdy_clpr=75500 > 50000 → above_max
    basics = _make_basics_from_raw("005930", SAMSUNG_RAW_67KEYS)

    with patch("src.engine.scanner.get_price_filter", AsyncMock(return_value=pf)), \
         patch("src.db.stock_master.get", AsyncMock(return_value=basics)), \
         patch("src.db.system_logs.write_log", AsyncMock()), \
         patch("src.db.strategy_funnel.insert_snapshot", AsyncMock()):
        result = await scanner._apply_price_filter(candidates, protected_tickers=set())

    assert result == [], (
        "G-1: 005930 운영 실데이터 raw → bfdy_clpr=75500 추출 → max=50000 above_max 차단 의무. "
        f"실제 {result} — `prdy_clpr` 키 조회 잔존으로 미확보 0 graceful 통과 결함."
    )
