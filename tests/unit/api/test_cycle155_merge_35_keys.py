"""사이클 155 — inquire_stock_basics FHKST01010100 merge 5 → 35 키 확장 회귀 가드.

사용자 결정 영속:
- Q1=B (HIGH+MEDIUM 일괄, 40 키 통합 — FHKST raw merge 30 + master_raw 활용 영역)
- Q2=A (raw JSONB merge, 사이클 107 답습)
- Q3=A (FHKST01010100 단일 source, 5 → 35 키)
- Q4=A (16:10 task 동행)
- Q5=A (TDD 정공)

영속 의무:
- 사이클 81 G-AST1 raw 영역 보호 (기존 5 키 영역 영구 영속 보존)
- 사이클 88 G-REJECT graceful (FHKST 호출 실패 영역)
- 사이클 107 inquire_stock_basics merge 패턴 영속
- 사이클 144 graceful 카운터 영역
- 사이클 145 0 값 영역 영구 영속 보호 (per/pbr/vol_tnrt 영역 동일)
- 사이클 149 VI 영역 영구 영속 정합
"""

from __future__ import annotations

import ast
from pathlib import Path
from unittest.mock import patch

import pytest

pytestmark = pytest.mark.unit


_CONDITION_PY = Path(__file__).resolve().parents[3] / "src" / "api" / "condition.py"


class TestCycle155Merge35Keys:
    """G-155-MERGE-1~7: FHKST01010100 merge 영역 35 키 확장 영구 영속."""

    @pytest.mark.asyncio
    async def test_g_155_merge_1_thirty_five_keys_total(self):
        """G-155-MERGE-1 (HIGH): 35 키 영역 영구 영속 정합 — 사이클 107 5 키 + 사이클 155 30 키."""
        from src.api import condition

        # 정상 FHKST 응답 영역 (35 키 모두 비-0 정상값)
        async def _mock_kis_get_quote(url, tr_id, params, **kwargs):
            if tr_id == "CTPF1002R":
                return {
                    "output": {
                        "pdno": "005930",
                        "prdt_abrv_name": "삼성전자",
                        "cptt_trad_tr_psbl_yn": "Y",
                        "nxt_tr_stop_yn": "N",
                    }
                }
            elif tr_id == "FHKST01010100":
                return {
                    "output": {
                        # 사이클 107 5 키
                        "acml_tr_pbmn": "500000000000",
                        "acml_vol": "10000000",
                        "lstn_stcn": "5969782550",
                        "prdy_vrss": "1500",
                        "hts_avls": "5000000",
                        # 사이클 155 HIGH 23
                        "per": "12.50",
                        "pbr": "1.80",
                        "hts_frgn_ehrt": "53.42",
                        "frgn_ntby_qty": "100000",
                        "stck_mxpr": "98000",
                        "stck_llam": "52000",
                        "vol_tnrt": "1.50",
                        "prdy_vrss_vol_rate": "120.00",
                        "w52_hgpr": "95000",
                        "w52_lwpr": "55000",
                        "w52_hgpr_date": "20260120",
                        "d250_hgpr": "95000",
                        "d250_lwpr": "55000",
                        "mrkt_warn_cls_code": "00",
                        "invt_caful_yn": "N",
                        "short_over_yn": "N",
                        "sltr_yn": "N",
                        "iscd_stat_cls_code": "55",
                        "temp_stop_yn": "N",
                        "new_hgpr_lwpr_cls_code": "0",
                        # 사이클 155 MEDIUM 7
                        "eps": "5500.00",
                        "bps": "45000.00",
                        "whol_loan_rmnd_rate": "0.50",
                        "ssts_yn": "Y",
                        "last_ssts_cntg_qty": "50000",
                        "vi_cls_code": "0",
                        "ovtm_vi_cls_code": "0",
                        "bstp_kor_isnm": "전기.전자",
                    }
                }
            return {"output": {}}

        with patch("src.api.condition.kis_get_quote", side_effect=_mock_kis_get_quote):
            basics = await condition.inquire_stock_basics("005930")

        # 사이클 107 5 키 영속
        assert basics.raw.get("acml_tr_pbmn") == "500000000000"
        assert basics.raw.get("acml_vol") == "10000000"
        assert basics.raw.get("hts_avls") == "5000000"
        # 사이클 155 HIGH 핵심 키
        assert basics.raw.get("per") == "12.50"
        assert basics.raw.get("pbr") == "1.80"
        assert basics.raw.get("hts_frgn_ehrt") == "53.42"
        assert basics.raw.get("stck_mxpr") == "98000"
        assert basics.raw.get("stck_llam") == "52000"
        assert basics.raw.get("vol_tnrt") == "1.50"
        assert basics.raw.get("w52_hgpr") == "95000"
        assert basics.raw.get("w52_hgpr_date") == "20260120"
        assert basics.raw.get("d250_hgpr") == "95000"
        # 사이클 155 진입 차단 6 영역
        assert basics.raw.get("mrkt_warn_cls_code") == "00"
        assert basics.raw.get("invt_caful_yn") == "N"
        assert basics.raw.get("short_over_yn") == "N"
        assert basics.raw.get("iscd_stat_cls_code") == "55"
        assert basics.raw.get("temp_stop_yn") == "N"
        # 사이클 155 MEDIUM 7 영역
        assert basics.raw.get("eps") == "5500.00"
        assert basics.raw.get("bps") == "45000.00"
        assert basics.raw.get("whol_loan_rmnd_rate") == "0.50"
        assert basics.raw.get("ssts_yn") == "Y"
        assert basics.raw.get("vi_cls_code") == "0"
        assert basics.raw.get("ovtm_vi_cls_code") == "0"
        assert basics.raw.get("bstp_kor_isnm") == "전기.전자"

    @pytest.mark.asyncio
    async def test_g_155_merge_2_zero_value_preserve(self):
        """G-155-MERGE-2 (HIGH): 0 값 응답 영역 → 기존 raw 키 영역 보존 (사이클 145 패턴 답습).

        장 시작 전 영역 영구 영속 = per/pbr/vol_tnrt 등 0 응답 → merge skip.
        기존 raw 키 보존 의무 (전일 영업일 영역 영구 영속 값 영역 영구 영속 보존).
        """
        from src.api import condition

        async def _mock_kis_get_quote(url, tr_id, params, **kwargs):
            if tr_id == "CTPF1002R":
                # 기존 raw 영역에 전일 영업일 값 영역 영구 영속 (모의 영역)
                return {
                    "output": {
                        "pdno": "005930",
                        "prdt_abrv_name": "삼성전자",
                        # CTPF1002R 영역에는 per/pbr 부재 — 사이클 107 정본 영구 영속
                    }
                }
            elif tr_id == "FHKST01010100":
                # 장 시작 전 = 0 값 응답
                return {
                    "output": {
                        "per": "0.00",  # 0 값 → skip
                        "pbr": "0",  # 0 값 → skip
                        "vol_tnrt": "0",  # 0 값 → skip
                        "acml_tr_pbmn": "0",  # 사이클 145 영역 영속
                        "acml_vol": "0",  # 사이클 145 영역 영속
                        "hts_avls": "5000000",  # 정상 값 → merge
                        "iscd_stat_cls_code": "55",  # 비숫자 → merge (정상)
                        "vi_cls_code": "0",  # 비숫자 영역 (0 값 영역 의미 있음 — vi 미발동) → merge
                    }
                }
            return {"output": {}}

        with patch("src.api.condition.kis_get_quote", side_effect=_mock_kis_get_quote):
            basics = await condition.inquire_stock_basics("005930")

        # 0 값 영역 → skip → raw 영역 미포함 (CTPF 부재 + FHKST 0 = 키 자체 부재)
        assert "per" not in basics.raw or basics.raw.get("per") in (None, "")
        assert "pbr" not in basics.raw or basics.raw.get("pbr") in (None, "")
        assert "vol_tnrt" not in basics.raw or basics.raw.get("vol_tnrt") in (None, "")
        # 정상 값 → merge
        assert basics.raw.get("hts_avls") == "5000000"
        # 비숫자 영역 (iscd_stat_cls_code) → 정상 merge (0 값 영역 영구 영속 의미 없음)
        assert basics.raw.get("iscd_stat_cls_code") == "55"
        # vi_cls_code 영역 = _ZERO_VALUE_SKIP_KEYS 영역 미포함 → 정상 merge ("0" = vi 미발동 의미)
        assert basics.raw.get("vi_cls_code") == "0"

    @pytest.mark.asyncio
    async def test_g_155_merge_3_graceful_on_fhkst_fail(self):
        """G-155-MERGE-3 (MEDIUM): FHKST01010100 호출 실패 → graceful + 사이클 144 카운터 증가."""
        from src.api import condition

        condition.reset_graceful_failed_counts()

        async def _mock_kis_get_quote(url, tr_id, params, **kwargs):
            if tr_id == "CTPF1002R":
                return {"output": {"pdno": "005930", "prdt_abrv_name": "삼성전자"}}
            elif tr_id == "FHKST01010100":
                raise RuntimeError("KIS SESSION FULL OPSQ1002")
            return {"output": {}}

        with patch("src.api.condition.kis_get_quote", side_effect=_mock_kis_get_quote):
            basics = await condition.inquire_stock_basics("005930")

        # CTPF 영역 단독 반환 — raw 영역 영구 영속에 ctpf 키만
        assert basics.ticker == "005930"
        assert basics.raw.get("pdno") == "005930"
        # 사이클 155 신규 키 = 부재 (FHKST 실패 graceful)
        assert "per" not in basics.raw
        assert "stck_mxpr" not in basics.raw
        # 사이클 144 카운터 영역 영구 영속 = 증가
        counts = condition.get_graceful_failed_counts()
        assert counts["fhkst01010100_failed"] >= 1

    @pytest.mark.asyncio
    async def test_g_155_merge_4_entry_block_6_keys(self):
        """G-155-MERGE-4 (HIGH): 진입 차단 6 영역 키 정합 (None/공백 graceful)."""
        from src.api import condition

        async def _mock_kis_get_quote(url, tr_id, params, **kwargs):
            if tr_id == "CTPF1002R":
                return {"output": {"pdno": "005930", "prdt_abrv_name": "삼성전자"}}
            elif tr_id == "FHKST01010100":
                # 진입 차단 6 영역 = 정상값
                return {
                    "output": {
                        "mrkt_warn_cls_code": "01",  # 시장경고 — 차단 영역
                        "invt_caful_yn": "Y",  # 투자유의 — 차단
                        "short_over_yn": "Y",  # 단기과열 — 차단
                        "sltr_yn": "Y",  # 정리매매 — 차단
                        "iscd_stat_cls_code": "51",  # 비정상 — 차단
                        "temp_stop_yn": "Y",  # 임시 정지 — 차단
                    }
                }
            return {"output": {}}

        with patch("src.api.condition.kis_get_quote", side_effect=_mock_kis_get_quote):
            basics = await condition.inquire_stock_basics("005930")

        # 6 키 모두 raw 영역 영구 영속에 적재
        assert basics.raw.get("mrkt_warn_cls_code") == "01"
        assert basics.raw.get("invt_caful_yn") == "Y"
        assert basics.raw.get("short_over_yn") == "Y"
        assert basics.raw.get("sltr_yn") == "Y"
        assert basics.raw.get("iscd_stat_cls_code") == "51"
        assert basics.raw.get("temp_stop_yn") == "Y"

    @pytest.mark.asyncio
    async def test_g_155_merge_5_high_low_5_keys(self):
        """G-155-MERGE-5 (MEDIUM): 신고가 5 (w52_* + d250_*) 정합."""
        from src.api import condition

        async def _mock_kis_get_quote(url, tr_id, params, **kwargs):
            if tr_id == "CTPF1002R":
                return {"output": {"pdno": "005930", "prdt_abrv_name": "삼성전자"}}
            elif tr_id == "FHKST01010100":
                return {
                    "output": {
                        "w52_hgpr": "95000",
                        "w52_lwpr": "55000",
                        "w52_hgpr_date": "20260120",
                        "d250_hgpr": "95000",
                        "d250_lwpr": "55000",
                    }
                }
            return {"output": {}}

        with patch("src.api.condition.kis_get_quote", side_effect=_mock_kis_get_quote):
            basics = await condition.inquire_stock_basics("005930")

        assert basics.raw.get("w52_hgpr") == "95000"
        assert basics.raw.get("w52_lwpr") == "55000"
        assert basics.raw.get("w52_hgpr_date") == "20260120"
        assert basics.raw.get("d250_hgpr") == "95000"
        assert basics.raw.get("d250_lwpr") == "55000"

    @pytest.mark.asyncio
    async def test_g_155_merge_6_foreign_2_keys(self):
        """G-155-MERGE-6 (MEDIUM): 외국인 2 (hts_frgn_ehrt / frgn_ntby_qty) 정합."""
        from src.api import condition

        async def _mock_kis_get_quote(url, tr_id, params, **kwargs):
            if tr_id == "CTPF1002R":
                return {"output": {"pdno": "005930", "prdt_abrv_name": "삼성전자"}}
            elif tr_id == "FHKST01010100":
                return {
                    "output": {
                        "hts_frgn_ehrt": "53.42",
                        "frgn_ntby_qty": "-100000",  # 순매도 음수 영역
                    }
                }
            return {"output": {}}

        with patch("src.api.condition.kis_get_quote", side_effect=_mock_kis_get_quote):
            basics = await condition.inquire_stock_basics("005930")

        assert basics.raw.get("hts_frgn_ehrt") == "53.42"
        assert basics.raw.get("frgn_ntby_qty") == "-100000"

    @pytest.mark.asyncio
    async def test_g_155_merge_7_vi_2_keys(self):
        """G-155-MERGE-7 (LOW): VI 2 (vi_cls_code / ovtm_vi_cls_code) 사이클 149 정합."""
        from src.api import condition

        async def _mock_kis_get_quote(url, tr_id, params, **kwargs):
            if tr_id == "CTPF1002R":
                return {"output": {"pdno": "005930", "prdt_abrv_name": "삼성전자"}}
            elif tr_id == "FHKST01010100":
                return {
                    "output": {
                        "vi_cls_code": "1",  # 정규장 VI 발동
                        "ovtm_vi_cls_code": "0",
                    }
                }
            return {"output": {}}

        with patch("src.api.condition.kis_get_quote", side_effect=_mock_kis_get_quote):
            basics = await condition.inquire_stock_basics("005930")

        assert basics.raw.get("vi_cls_code") == "1"
        assert basics.raw.get("ovtm_vi_cls_code") == "0"
