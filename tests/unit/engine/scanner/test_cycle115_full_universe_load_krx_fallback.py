"""사이클 115 (2026-06-12) — _full_universe_load_once Q3=C 폴백 패턴 회귀 가드.

Red 명세: `_workspace/red/cycle115_krx_endpoint_integration.md`

HIGH-3 (3 sub) — Q3=C 폴백 패턴:
- (a) KRX 1차 성공 → source="krx" + KIS 호출 0건
- (b) KrxApiError 시 KIS 폴백 호출 + source="kis_fallback"
- (c) KIS도 실패 시 raise 전파 (사이클 110 graceful 영역 영속)

HIGH-4 — Rate Limit 50ms sleep (4 KRX 호출 사이 3건 발화)

영속 의무:
- 사이클 38 명문화 (scanner 매수 진입 전용)
- 사이클 81 G-AST1 (KIS bfdy_clpr / hts_avls 덮어쓰기 0)
- 사이클 88 G-REJECT (KrxApiError graceful 폴백)
- 사이클 101 영속 (24h TTL idempotency)
- 사이클 107/108 영속 (raw 보강 의존성)
- 사이클 109 영속 (KIS market-cap 영역 폴백)
- 사이클 110 영속 (graceful 시정 패턴)
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_h3a_krx_primary_success_no_kis_fallback(monkeypatch):
    """HIGH-3.a: KRX 1차 성공 → source="krx" + KIS 폴백 호출 0건."""
    from src.engine import scanner as _scanner

    # KRX 1차 함수 mock — 정상 응답
    krx_called = []

    async def _fake_krx_primary(**_kw):
        krx_called.append(True)
        return {
            "total": 100,
            "kospi": 50,
            "kosdaq": 50,
            "securities": 100,
            "etf": 0,
            "fetched": 100,
            "skipped_ttl": 0,
            "failed": 0,
            "elapsed_ms": 1000,
        }

    # KIS 폴백 함수 mock — 호출 안 됨 검증
    kis_called = []

    async def _fake_kis_fallback(**_kw):
        kis_called.append(True)
        return {"total": 0}  # 호출되면 결함

    monkeypatch.setattr(_scanner, "_full_universe_load_krx_primary", _fake_krx_primary)
    monkeypatch.setattr(_scanner, "_full_universe_load_kis_fallback", _fake_kis_fallback)

    summary = await _scanner._full_universe_load_once()

    # KRX 1차 성공 검증
    assert len(krx_called) == 1
    assert summary["source"] == "krx"
    assert summary["total"] == 100

    # KIS 폴백 호출 0건 검증 (Q3=C 영속)
    assert len(kis_called) == 0, "KRX 성공 시 KIS 폴백 호출 0건 영속 위반"


@pytest.mark.asyncio
async def test_h3b_krx_error_triggers_kis_fallback(monkeypatch):
    """HIGH-3.b: KrxApiError 시 KIS 폴백 호출 + source="kis_fallback"."""
    from src.api.krx import KrxApiError
    from src.engine import scanner as _scanner

    # KRX 1차 함수 — KrxApiError raise
    krx_called = []

    async def _fake_krx_primary(**_kw):
        krx_called.append(True)
        raise KrxApiError("KRX 401 unauthorized")

    # KIS 폴백 함수 — 정상 응답
    kis_called = []

    async def _fake_kis_fallback(**_kw):
        kis_called.append(True)
        return {
            "total": 2800,
            "kospi": 1400,
            "kosdaq": 1400,
            "securities": 2800,
            "etf": 0,
            "fetched": 2800,
            "skipped_ttl": 0,
            "failed": 0,
            "elapsed_ms": 300000,
        }

    monkeypatch.setattr(_scanner, "_full_universe_load_krx_primary", _fake_krx_primary)
    monkeypatch.setattr(_scanner, "_full_universe_load_kis_fallback", _fake_kis_fallback)

    summary = await _scanner._full_universe_load_once()

    # KRX 1차 시도 → KrxApiError → KIS 폴백 호출 검증
    assert len(krx_called) == 1
    assert len(kis_called) == 1
    assert summary["source"] == "kis_fallback"
    assert summary["total"] == 2800


@pytest.mark.asyncio
async def test_h3c_kis_fallback_failure_propagates(monkeypatch):
    """HIGH-3.c: KRX + KIS 양쪽 실패 시 KIS 예외 전파 (사이클 110 graceful 영역).

    KrxApiError 흡수 후 KIS 호출. KIS RuntimeError 등 예외는 호출자 (scheduler) 가
    `_full_universe_load_task_loop` graceful try/except 로 처리 (사이클 106 영속).
    """
    from src.api.krx import KrxApiError
    from src.engine import scanner as _scanner

    async def _fake_krx_primary(**_kw):
        raise KrxApiError("KRX 비활성")

    async def _fake_kis_fallback(**_kw):
        raise RuntimeError("KIS market_cap API 5xx")

    monkeypatch.setattr(_scanner, "_full_universe_load_krx_primary", _fake_krx_primary)
    monkeypatch.setattr(_scanner, "_full_universe_load_kis_fallback", _fake_kis_fallback)

    # KIS 예외 그대로 전파 (호출자 graceful 의무)
    with pytest.raises(RuntimeError, match="KIS"):
        await _scanner._full_universe_load_once()


@pytest.mark.asyncio
async def test_h4_rate_limit_50ms_sleep_between_calls(monkeypatch):
    """HIGH-4: KRX 4 호출 사이 50ms sleep 3건 발화 (KIS LMS chain 안전 마진 답습)."""
    from src.engine import scanner as _scanner

    sleep_calls = []

    async def _capture_sleep(secs):
        sleep_calls.append(secs)

    # 4 KRX endpoint 함수 mock
    # 사이클 117 시정 영속: bydd_trd 가 빈 list 시 재시도 → KrxApiError raise.
    # H4 의도 = 정상 흐름 50ms sleep 3건 발화 검증 → bydd_trd 1건 반환으로 break.
    async def _fake_bydd_trd(date):
        # 정상 흐름: 첫 시도에 데이터 1건 반환 → 재시도 영역 미진입
        return [{"ISU_CD": "999999", "ISU_NM": "테스트", "MKTCAP": "1000000000000"}]

    async def _fake_info(date):
        return []  # info 영역 비어도 정상 흐름 (upsert loop 별개 영역)

    monkeypatch.setattr("src.api.krx.fetch_stk_bydd_trd", _fake_bydd_trd)
    monkeypatch.setattr("src.api.krx.fetch_ksq_bydd_trd", _fake_bydd_trd)
    monkeypatch.setattr("src.api.krx.fetch_stk_isu_base_info", _fake_info)
    monkeypatch.setattr("src.api.krx.fetch_ksq_isu_base_info", _fake_info)

    # 사이클 117 시정 영속: Supabase 호출 회피 — _sm_is_stale=False (TTL skip 분기)
    async def _fake_is_stale(ticker, **kwargs):
        return False

    monkeypatch.setattr("src.db.stock_master.is_stale", _fake_is_stale)

    # asyncio.sleep patch (scanner.py 의 _asyncio.sleep 영역)
    monkeypatch.setattr(_scanner._asyncio, "sleep", _capture_sleep)

    # today_kst patch (정합)
    from src.db import _kst as _kst_mod
    from datetime import date as _date
    monkeypatch.setattr(_kst_mod, "today_kst", lambda: _date(2026, 6, 12))

    summary = await _scanner._full_universe_load_krx_primary()

    # 50ms sleep 3건 발화 확인 (KRX 호출 1+2+3, 마지막 호출 후 sleep 없음).
    # 사이클 117 시정 영속: 첫 시도 데이터 확보 → 재시도 영역 미진입 → 50ms sleep 3건 영역.
    fifty_ms_sleeps = [s for s in sleep_calls if s == 0.05]
    assert len(fifty_ms_sleeps) == 3, (
        f"HIGH-4 위반: KRX 호출 사이 50ms sleep 3건 발화 영속 위반 "
        f"(실제 {len(fifty_ms_sleeps)}건). KIS LMS chain 안전 마진 답습 의무 영역."
    )

    # 응답 형식 검증 (사이클 117 시정 영속: 데이터 1건 mock + TTL skip → skipped_ttl=2, total=2)
    assert summary["total"] == 2  # KOSPI 1 + KOSDAQ 1
    assert summary["kospi"] == 1
    assert summary["kosdaq"] == 1
    assert summary["skipped_ttl"] == 2  # _sm_is_stale=False (TTL fresh)


@pytest.mark.asyncio
async def test_medium1_stock_master_upsert_with_krx_raw_merge(monkeypatch):
    """MEDIUM-1: stock_master upsert 정합 (KRX raw JSONB merge, 사이클 81 G-AST1 영속).

    KRX `bydd_trd` 응답 → raw 추가: MKTCAP / ACC_TRDVAL / LIST_SHRS / TDD_CLSPRC
    KRX `isu_base_info` 응답 → raw 추가: LIST_DD / SECUGRP_NM / KIND_STKCERT_TP_NM
    사이클 81 G-AST1 영속: KIS bfdy_clpr / hts_avls 덮어쓰기 0 (KRX 응답에는 키 부재)
    """
    from src.engine import scanner as _scanner

    bydd_sample = [
        {
            "ISU_CD": "005930",
            "ISU_NM": "삼성전자",
            "MKT_NM": "KOSPI",
            "MKTCAP": "418000000000000",
            "ACC_TRDVAL": "500000000000",
            "LIST_SHRS": "5969782550",
            "TDD_CLSPRC": "70000",
            "TDD_OPNPRC": "69800",
            "TDD_HGPRC": "70500",
            "TDD_LWPRC": "69500",
            "ACC_TRDVOL": "10000000",
            "FLUC_RT": "0.43",
            "SECT_TP_NM": "유가증권",
        }
    ]
    info_sample = [
        {
            "ISU_SRT_CD": "005930",
            "ISU_NM": "삼성전자보통주",
            "LIST_DD": "1975/06/11",
            "MKT_TP_NM": "유가증권시장",
            "SECUGRP_NM": "주권",
            "KIND_STKCERT_TP_NM": "보통주",
            "ISU_ABBRV": "삼성전자",
            "ISU_ENG_NM": "Samsung Electronics",
            "PARVAL": "100",
        }
    ]

    async def _fake_stk_bydd(date):
        return bydd_sample

    async def _fake_ksq_bydd(date):
        return []

    async def _fake_stk_info(date):
        return info_sample

    async def _fake_ksq_info(date):
        return []

    # is_stale → True (upsert 진입)
    async def _fake_is_stale(ticker, max_age_hours=24):
        return True

    captured_upsert = []

    async def _capture_upsert(basics):
        captured_upsert.append(basics)

    monkeypatch.setattr("src.api.krx.fetch_stk_bydd_trd", _fake_stk_bydd)
    monkeypatch.setattr("src.api.krx.fetch_ksq_bydd_trd", _fake_ksq_bydd)
    monkeypatch.setattr("src.api.krx.fetch_stk_isu_base_info", _fake_stk_info)
    monkeypatch.setattr("src.api.krx.fetch_ksq_isu_base_info", _fake_ksq_info)
    monkeypatch.setattr("src.db.stock_master.is_stale", _fake_is_stale)
    monkeypatch.setattr("src.db.stock_master.upsert_one", _capture_upsert)

    async def _no_sleep(secs):
        pass

    monkeypatch.setattr(_scanner._asyncio, "sleep", _no_sleep)

    from src.db import _kst as _kst_mod
    from datetime import date as _date
    monkeypatch.setattr(_kst_mod, "today_kst", lambda: _date(2026, 6, 12))

    summary = await _scanner._full_universe_load_krx_primary()

    assert summary["fetched"] == 1
    assert len(captured_upsert) == 1

    basics = captured_upsert[0]
    assert basics.ticker == "005930"
    # KRX bydd_trd raw 키 영역 포함
    assert basics.raw["MKTCAP"] == "418000000000000"
    assert basics.raw["ACC_TRDVAL"] == "500000000000"
    assert basics.raw["LIST_SHRS"] == "5969782550"
    assert basics.raw["TDD_CLSPRC"] == "70000"
    # KRX isu_base_info raw 키 영역 보강
    assert basics.raw["LIST_DD"] == "1975/06/11"
    assert basics.raw["SECUGRP_NM"] == "주권"
    assert basics.raw["KIND_STKCERT_TP_NM"] == "보통주"
    # 사이클 119 의미 전환: bfdy_clpr = KRX TDD_CLSPRC 매핑 값 (basDd=어제 종가 = 오늘 전일 종가).
    # KIS CTPF1002R 호출 부재 → 사이클 119 매핑 추가 → 사용자 보고 "내용 안 채워짐" 해소.
    # 사이클 81 G-AST1 정합 영속: KIS market-cap 호출 0건 → 충돌 0 (KRX → KIS 정합 키 매핑).
    assert basics.raw["bfdy_clpr"] == 70_000, (
        "사이클 119 TDD_CLSPRC → bfdy_clpr 매핑 정합 (basDd=어제 종가 = 오늘 전일 종가)"
    )
    # 사이클 116 → 166 의미 전환: hts_avls = KRX MKTCAP 원 단위 → 억원 환산 값
    # 사이클 108 list_by_filter (hts_avls × 100_000_000 ≥ min_market_cap) 정합 의무.
    assert basics.raw["hts_avls"] == 418_000_000_000_000 // 100_000_000, (
        "사이클 166 MKTCAP → hts_avls 억원 환산 정합 (418조원 // 100_000_000 = 4,180,000 억원)"
    )
