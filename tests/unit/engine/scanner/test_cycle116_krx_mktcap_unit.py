"""사이클 116 → 166 — KRX MKTCAP (원 단위) → KIS hts_avls (억원 단위) 환산 매핑 가드.

사이클 115 통합 KRX 1차 분기 활성 시 사이클 108 `list_by_filter` 정합 의무.
사이클 166 의미 전환: KIS 경로 hts_avls 가 억원 단위로 확정 (운영 DB 실측 + KIS 정본)
→ KRX 폴백도 억원으로 통일 (단위 혼재 silent 결함 제거).
사이클 108 영역: `hts_avls × 100_000_000 ≥ min_market_cap` (억원 단위, 사이클 166 정정).
KRX `MKTCAP` 영역: 원 단위 직접 → 변환 없이 그대로 사용 시 100,000,000배 왜곡.

시정: `_full_universe_load_krx_primary` 영역에서 KRX `MKTCAP // 100_000_000` → `hts_avls` 키.
사이클 81 G-AST1 영속: KRX 1차 시점에 KIS market-cap 호출 0건 → KIS `hts_avls` 부재 → 덮어쓰기 충돌 0.
"""
from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_SCANNER_PY = Path(__file__).resolve().parents[4] / "src" / "engine" / "scanner.py"


def _simulate_krx_raw_merge(trd_row: dict) -> dict:
    """`_full_universe_load_krx_primary` 의 raw merge 영역 정밀 재현 (사이클 116→166 영역 포함).

    실제 함수 호출 대신 핵심 로직만 추출 (테스트 격리).
    """
    krx_raw: dict = {}
    # bydd_trd raw merge (사이클 115 영역)
    for key in ("MKTCAP", "ACC_TRDVAL", "LIST_SHRS", "TDD_CLSPRC", "TDD_OPNPRC",
                "TDD_HGPRC", "TDD_LWPRC", "ACC_TRDVOL", "FLUC_RT", "MKT_NM",
                "SECT_TP_NM"):
        if key in trd_row:
            krx_raw[key] = trd_row[key]
    # 사이클 116 → 166 영역 (원 → 억원)
    if "MKTCAP" in trd_row:
        try:
            mktcap_won = int(str(trd_row["MKTCAP"]).replace(",", "") or 0)
            if mktcap_won > 0:
                krx_raw["hts_avls"] = mktcap_won // 100_000_000
        except (ValueError, TypeError):
            pass
    return krx_raw


def test_h1_krx_mktcap_to_hts_avls_conversion():
    """HIGH-1: KRX MKTCAP (원) → hts_avls (억원) 환산 정합 (사이클 166 정정).

    예: 삼성전자 시가총액 500조원 = 500_000_000_000_000 원 → hts_avls = 5_000_000 (억원).
    """
    trd_row = {"ISU_CD": "005930", "ISU_NM": "삼성전자", "MKTCAP": "500000000000000"}
    raw = _simulate_krx_raw_merge(trd_row)
    assert raw["hts_avls"] == 5_000_000  # 500조원 → 5,000,000 (억원 단위)
    assert raw["MKTCAP"] == "500000000000000"  # 원 단위 raw 영속


def test_h2_list_by_filter_compatibility_via_hts_avls():
    """HIGH-2: 사이클 108 list_by_filter 호환성 — hts_avls × 100_000_000 영역 (사이클 166).

    예: min_market_cap=100조원 (100_000_000_000_000 원) 필터 →
    삼성전자 hts_avls=5_000_000 × 100_000_000 = 500조원 ≥ 100조원 → 통과.
    """
    trd_row = {"MKTCAP": "500000000000000"}  # 500조원
    raw = _simulate_krx_raw_merge(trd_row)
    # 사이클 108 → 166 list_by_filter 영역 재현 (억원 단위)
    hts_avls = int(raw.get("hts_avls") or 0)
    min_market_cap = 100_000_000_000_000  # 100조원
    assert hts_avls * 100_000_000 >= min_market_cap


def test_h3_graceful_mktcap_invalid_value():
    """HIGH-3: MKTCAP 잘못된 값 graceful (raw MKTCAP 유지 + hts_avls 부재).

    KRX 응답 abnormal 시 (빈 문자열 / 비숫자 / None) → graceful skip.
    """
    cases = [
        {"MKTCAP": ""},  # 빈 문자열
        {"MKTCAP": "N/A"},  # 비숫자
        {"MKTCAP": None},  # None
        {"MKTCAP": "0"},  # 0 (>0 가드)
    ]
    for trd_row in cases:
        raw = _simulate_krx_raw_merge(trd_row)
        assert "hts_avls" not in raw, f"부적절한 입력 {trd_row}: hts_avls 부재 의무"


def test_m1_mktcap_comma_separator_handling():
    """MEDIUM-1: KRX 응답 영역 comma 영역 (예: '500,000,000') graceful.

    KRX 응답 일부 영역 천 단위 콤마 포함 가능성 — replace(',', '') 정합.
    """
    trd_row = {"MKTCAP": "500,000,000,000,000"}
    raw = _simulate_krx_raw_merge(trd_row)
    assert raw["hts_avls"] == 5_000_000  # 억원 단위 (사이클 166)


def test_m2_mktcap_persistence_no_overwrite():
    """MEDIUM-2: 사이클 81 G-AST1 영속 — KRX 1차 시점에 KIS hts_avls 부재 보장.

    `_full_universe_load_krx_primary` 영역 진입 = KIS market-cap 호출 0건 영구 확정.
    즉 KRX `hts_avls` 변환 영역이 KIS `hts_avls` 영역과 충돌 0.
    """
    trd_row = {"MKTCAP": "1000000000000"}  # 1조원
    raw = _simulate_krx_raw_merge(trd_row)
    # KRX 영역 단독 → hts_avls 단일 출처 (KIS 부재)
    assert "hts_avls" in raw
    assert raw["hts_avls"] == 10_000  # 1조원 // 100_000_000 = 10,000 (억원, 사이클 166)


def test_g_ast1_source_code_conversion_present():
    """AST 정적 가드 — scanner.py 영역에 KRX MKTCAP → hts_avls 환산 코드 영구 영속.

    사이클 166 정정: 억원 단위 (`// 100_000_000`) 의무.
    미래 시정 누락 영구 차단 (사이클 78/79/108 G-AST 패턴 답습).
    """
    source = _SCANNER_PY.read_text(encoding="utf-8")
    # 환산 영역 핵심 패턴 (`mktcap_won // 100_000_000` + `krx_raw["hts_avls"]`, 사이클 166)
    assert "// 100_000_000" in source, "MKTCAP → hts_avls 억원 환산 영역 부재 (사이클 166 시정 회귀)"
    assert "hts_avls" in source, "hts_avls 키 매핑 부재"
    # 백만원 가정 잔재 차단 (사이클 166)
    assert "mktcap_won // 1_000_000" not in source, (
        "KRX MKTCAP 환산에 // 1_000_000 (백만원) 잔존 — 사이클 166 억원 통일 위반"
    )
    # 사이클 116 주석 영역 영속 (의도 보존)
    assert "사이클 116" in source, "사이클 116 영역 주석 부재 (의도 영속 회귀)"
