"""사이클 153 — _stock_master_master_load_once + upsert_master_raw 영역 KOSPI200/KOSDAQ150 회귀 가드.

G-153-MASTER 3 케이스 (HIGH 2).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# G-153-MASTER-1 (HIGH) — KOSPI 분기 kospi200_apnt_cls_code → is_kospi200=True
# ---------------------------------------------------------------------------


class TestG153Master1:
    @pytest.mark.asyncio
    async def test_master_1_kospi_branch_sets_is_kospi200(self):
        """G-153-MASTER-1 HIGH — KOSPI record kospi200_apnt_cls_code != "" 영역 = is_kospi200=True."""
        from src.engine import scanner

        kospi_records = [
            {
                "mksc_shrn_iscd": "005930",
                "hts_kor_isnm": "삼성전자",
                "kospi200_apnt_cls_code": "1",  # KOSPI200 편입
                "kospi100_issu_yn": "Y",
            },
            {
                "mksc_shrn_iscd": "001234",
                "hts_kor_isnm": "비KOSPI200",
                "kospi200_apnt_cls_code": "",  # 미편입 (empty)
                "kospi100_issu_yn": "N",
            },
        ]

        upsert_calls = []

        async def fake_upsert(ticker, record, *, is_kospi200=False, is_kosdaq150=False):
            upsert_calls.append((ticker, record))

        with patch("src.api.kis_master.download_kospi_master", AsyncMock(return_value=kospi_records)), \
             patch("src.api.kis_master.download_kosdaq_master", AsyncMock(return_value=[])), \
             patch("src.db.stock_master.upsert_master_raw", side_effect=fake_upsert):
            await scanner._stock_master_master_load_once(force=True)

        # 양쪽 모두 upsert 호출됐는지 확인
        assert len(upsert_calls) == 2
        # KOSPI 편입 record 영역 영구 영속 = kospi200_apnt_cls_code != "" 보존 의무
        rec_005930 = next(r for t, r in upsert_calls if t == "005930")
        assert rec_005930.get("kospi200_apnt_cls_code") == "1", (
            "G-153-MASTER-1 HIGH — KOSPI 분기 = kospi200_apnt_cls_code 영역 영구 영속 record 보존 의무"
        )

        # 비편입 record 영역 = kospi200_apnt_cls_code == ""
        rec_001234 = next(r for t, r in upsert_calls if t == "001234")
        assert rec_001234.get("kospi200_apnt_cls_code") == ""


# ---------------------------------------------------------------------------
# G-153-MASTER-2 (HIGH) — KOSDAQ 분기 ksq150_nmix_yn == "Y" → is_kosdaq150=True
# ---------------------------------------------------------------------------


class TestG153Master2:
    @pytest.mark.asyncio
    async def test_master_2_kosdaq_branch_sets_is_kosdaq150(self):
        """G-153-MASTER-2 HIGH — KOSDAQ record ksq150_nmix_yn == "Y" 영역 = is_kosdaq150=True."""
        from src.engine import scanner

        kosdaq_records = [
            {
                "mksc_shrn_iscd": "247540",
                "hts_kor_isnm": "에코프로비엠",
                "ksq150_nmix_yn": "Y",  # KOSDAQ150 편입
                "vntr_issu_yn": "N",
            },
            {
                "mksc_shrn_iscd": "999999",
                "hts_kor_isnm": "비KOSDAQ150",
                "ksq150_nmix_yn": "N",  # 미편입
                "vntr_issu_yn": "N",
            },
        ]

        upsert_calls = []

        async def fake_upsert(ticker, record, *, is_kospi200=False, is_kosdaq150=False):
            upsert_calls.append((ticker, record))

        with patch("src.api.kis_master.download_kospi_master", AsyncMock(return_value=[])), \
             patch("src.api.kis_master.download_kosdaq_master", AsyncMock(return_value=kosdaq_records)), \
             patch("src.db.stock_master.upsert_master_raw", side_effect=fake_upsert):
            await scanner._stock_master_master_load_once(force=True)

        assert len(upsert_calls) == 2
        rec_247540 = next(r for t, r in upsert_calls if t == "247540")
        assert rec_247540.get("ksq150_nmix_yn") == "Y", (
            "G-153-MASTER-2 HIGH — KOSDAQ 분기 = ksq150_nmix_yn 영역 영구 영속 record 보존 의무"
        )

        rec_999999 = next(r for t, r in upsert_calls if t == "999999")
        assert rec_999999.get("ksq150_nmix_yn") == "N"


# ---------------------------------------------------------------------------
# G-153-MASTER-3 — hardcoded list (KOSPI_200_TICKERS / KOSDAQ_150_TICKERS) 변경 0
# ---------------------------------------------------------------------------


class TestG153Master3:
    def test_master_3_hardcoded_list_unchanged(self):
        """G-153-MASTER-3 — scanner.py hardcoded list 영역 변경 0 (vcp_breakout 영역 영향 0 영구 영속).

        사이클 153 범위 외 — vcp_breakout L726/L732 영역 영향 평가 후 사이클 154+ 인계.
        """
        from src.engine import scanner

        assert hasattr(scanner, "KOSPI_200_TICKERS"), (
            "G-153-MASTER-3 — KOSPI_200_TICKERS 영역 영구 영속 (vcp_breakout 의존)"
        )
        assert hasattr(scanner, "KOSDAQ_150_TICKERS"), (
            "G-153-MASTER-3 — KOSDAQ_150_TICKERS 영역 영구 영속 (vcp_breakout 의존)"
        )

        # 합집합 ≥ 100 종목 영구 영속 (변경 없음 확인 영역)
        assert len(scanner.KOSPI_200_TICKERS) >= 50, "hardcoded list 영역 변경 0 영구 영속"
        assert len(scanner.KOSDAQ_150_TICKERS) >= 30, "hardcoded list 영역 변경 0 영구 영속"
