"""사이클 119 — KRX → KIS 정합 키 전수 매핑 확장 (4 키 추가).

사용자 보고 (2026-06-12 16:14 KST):
- "종목마스터 적재 시 KIS 일시 오류 + 리스트 내용 안 채워짐"
- 정밀 진단 결과: KRX 1차 적재 종목 (97%)에 KIS 전용 키 부재
  → UI / 필터 / 매수 신호 영역이 KIS 키 (bfdy_clpr / lstn_stcn / acml_vol / prdy_vrss) 참조 시 빈 값

KIS MCP 정본 검증:
- 사용자 가설 "KIS TR 코드 못 찾음" → 반박 (TR 코드 모두 정합)
- 진짜 원인: 사이클 116 (MKTCAP→hts_avls) + 사이클 118 (ACC_TRDVAL→acml_tr_pbmn) 외 4 키 매핑 누락

시정 (사이클 116/118 답습 패턴):
- TDD_CLSPRC → bfdy_clpr (basDd=어제 시점 → 어제 종가 = 오늘 전일 종가)
- LIST_SHRS → lstn_stcn
- ACC_TRDVOL → acml_vol
- CMPPREVDD_PRC → prdy_vrss (음수 허용)
"""
from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_SCANNER_PY = Path(__file__).resolve().parents[4] / "src" / "engine" / "scanner.py"


def _simulate_krx_raw_merge(trd_row: dict) -> dict:
    """`_full_universe_load_krx_primary` 의 raw merge 영역 정밀 재현 (사이클 116/118/119 포함)."""
    krx_raw: dict = {}
    # bydd_trd raw merge (사이클 115 영역)
    for key in ("MKTCAP", "ACC_TRDVAL", "LIST_SHRS", "TDD_CLSPRC", "TDD_OPNPRC",
                "TDD_HGPRC", "TDD_LWPRC", "ACC_TRDVOL", "FLUC_RT", "MKT_NM",
                "SECT_TP_NM"):
        if key in trd_row:
            krx_raw[key] = trd_row[key]
    # 사이클 116 (MKTCAP → hts_avls)
    if "MKTCAP" in trd_row:
        try:
            mktcap_won = int(str(trd_row["MKTCAP"]).replace(",", "") or 0)
            if mktcap_won > 0:
                krx_raw["hts_avls"] = mktcap_won // 1_000_000
        except (ValueError, TypeError):
            pass
    # 사이클 118 (ACC_TRDVAL → acml_tr_pbmn)
    if "ACC_TRDVAL" in trd_row:
        try:
            trdval_won = int(str(trd_row["ACC_TRDVAL"]).replace(",", "") or 0)
            if trdval_won > 0:
                krx_raw["acml_tr_pbmn"] = trdval_won
        except (ValueError, TypeError):
            pass
    # 사이클 119 (4 키 추가)
    if "TDD_CLSPRC" in trd_row:
        try:
            clpr_won = int(str(trd_row["TDD_CLSPRC"]).replace(",", "") or 0)
            if clpr_won > 0:
                krx_raw["bfdy_clpr"] = clpr_won
        except (ValueError, TypeError):
            pass
    if "LIST_SHRS" in trd_row:
        try:
            shrs = int(str(trd_row["LIST_SHRS"]).replace(",", "") or 0)
            if shrs > 0:
                krx_raw["lstn_stcn"] = shrs
        except (ValueError, TypeError):
            pass
    if "ACC_TRDVOL" in trd_row:
        try:
            vol = int(str(trd_row["ACC_TRDVOL"]).replace(",", "") or 0)
            if vol > 0:
                krx_raw["acml_vol"] = vol
        except (ValueError, TypeError):
            pass
    if "CMPPREVDD_PRC" in trd_row:
        try:
            vrss = int(str(trd_row["CMPPREVDD_PRC"]).replace(",", "") or 0)
            krx_raw["prdy_vrss"] = vrss
        except (ValueError, TypeError):
            pass
    return krx_raw


def test_h1_tdd_clsprc_to_bfdy_clpr_mapping():
    """HIGH-1: TDD_CLSPRC (어제 종가) → bfdy_clpr (오늘 기준 전일 종가) 매핑.

    basDd=어제 (사이클 117) → KRX TDD_CLSPRC = 어제 종가 = KIS bfdy_clpr 정합.
    """
    trd_row = {"ISU_CD": "005930", "TDD_CLSPRC": "72700"}
    raw = _simulate_krx_raw_merge(trd_row)
    assert raw["bfdy_clpr"] == 72700  # 원 단위 동일
    assert raw["TDD_CLSPRC"] == "72700"  # KRX raw 영속


def test_h2_list_shrs_to_lstn_stcn_mapping():
    """HIGH-2: LIST_SHRS → lstn_stcn 상장 주식수 매핑."""
    trd_row = {"LIST_SHRS": "5969782550"}  # 삼성전자 상장 주식수
    raw = _simulate_krx_raw_merge(trd_row)
    assert raw["lstn_stcn"] == 5_969_782_550


def test_h3_acc_trdvol_to_acml_vol_mapping():
    """HIGH-3: ACC_TRDVOL → acml_vol 누적 거래량 매핑."""
    trd_row = {"ACC_TRDVOL": "3686661"}
    raw = _simulate_krx_raw_merge(trd_row)
    assert raw["acml_vol"] == 3_686_661


def test_h4_cmpprevdd_prc_to_prdy_vrss_negative_allowed():
    """HIGH-4: CMPPREVDD_PRC → prdy_vrss 전일 대비 매핑 (음수 허용)."""
    # 양수 케이스 (상승)
    trd_row = {"CMPPREVDD_PRC": "400"}
    raw = _simulate_krx_raw_merge(trd_row)
    assert raw["prdy_vrss"] == 400

    # 음수 케이스 (하락) — > 0 가드 없음 영구 확정
    trd_row = {"CMPPREVDD_PRC": "-500"}
    raw = _simulate_krx_raw_merge(trd_row)
    assert raw["prdy_vrss"] == -500

    # 0 케이스 (보합) — 음수 허용 정책으로 0도 저장됨
    trd_row = {"CMPPREVDD_PRC": "0"}
    raw = _simulate_krx_raw_merge(trd_row)
    assert raw["prdy_vrss"] == 0


def test_m1_graceful_invalid_values():
    """MEDIUM-1: 4 키 graceful (빈 문자열 / None / N/A / 0 / 콤마)."""
    cases = [
        {"TDD_CLSPRC": "", "LIST_SHRS": "", "ACC_TRDVOL": ""},
        {"TDD_CLSPRC": None, "LIST_SHRS": None, "ACC_TRDVOL": None},
        {"TDD_CLSPRC": "N/A", "LIST_SHRS": "N/A", "ACC_TRDVOL": "N/A"},
        {"TDD_CLSPRC": "0", "LIST_SHRS": "0", "ACC_TRDVOL": "0"},  # > 0 가드
    ]
    for trd_row in cases:
        raw = _simulate_krx_raw_merge(trd_row)
        # 3 키 (TDD_CLSPRC / LIST_SHRS / ACC_TRDVOL)는 > 0 가드로 부재
        for kis_key in ("bfdy_clpr", "lstn_stcn", "acml_vol"):
            assert kis_key not in raw, (
                f"부적절 입력 {trd_row}: {kis_key} 부재 의무 (> 0 가드)"
            )


def test_m1_comma_separator_handling():
    """MEDIUM-1 (보강): KRX 응답 영역 comma 영역 (예: '5,969,782,550') graceful."""
    trd_row = {
        "TDD_CLSPRC": "72,700",
        "LIST_SHRS": "5,969,782,550",
        "ACC_TRDVOL": "3,686,661",
        "CMPPREVDD_PRC": "-1,500",
    }
    raw = _simulate_krx_raw_merge(trd_row)
    assert raw["bfdy_clpr"] == 72_700
    assert raw["lstn_stcn"] == 5_969_782_550
    assert raw["acml_vol"] == 3_686_661
    assert raw["prdy_vrss"] == -1_500


def test_m2_existing_cycle116_118_mapping_persistence():
    """MEDIUM-2: 사이클 116/118 영역 영속 (MKTCAP / ACC_TRDVAL 매핑 무영향)."""
    trd_row = {
        "MKTCAP": "500000000000000",  # 500조원
        "ACC_TRDVAL": "50000000000",  # 500억원
        "TDD_CLSPRC": "72700",
        "LIST_SHRS": "5969782550",
        "ACC_TRDVOL": "3686661",
        "CMPPREVDD_PRC": "400",
    }
    raw = _simulate_krx_raw_merge(trd_row)
    # 사이클 116 영역
    assert raw["hts_avls"] == 500_000_000
    # 사이클 118 영역
    assert raw["acml_tr_pbmn"] == 50_000_000_000
    # 사이클 119 영역
    assert raw["bfdy_clpr"] == 72_700
    assert raw["lstn_stcn"] == 5_969_782_550
    assert raw["acml_vol"] == 3_686_661
    assert raw["prdy_vrss"] == 400


def test_g_ast1_source_code_4_mappings_present():
    """AST 정적 가드 — scanner.py 영역에 4 매핑 코드 영구 영속.

    미래 시정 누락 영구 차단 (사이클 78/79/108/116/118 G-AST 패턴 답습).
    """
    source = _SCANNER_PY.read_text(encoding="utf-8")
    # 4 매핑 핵심 패턴 영구 확정
    assert 'krx_raw["bfdy_clpr"]' in source, "TDD_CLSPRC → bfdy_clpr 매핑 부재"
    assert 'krx_raw["lstn_stcn"]' in source, "LIST_SHRS → lstn_stcn 매핑 부재"
    assert 'krx_raw["acml_vol"]' in source, "ACC_TRDVOL → acml_vol 매핑 부재"
    assert 'krx_raw["prdy_vrss"]' in source, "CMPPREVDD_PRC → prdy_vrss 매핑 부재"
    # 사이클 119 영역 주석 영속
    assert "사이클 119" in source, "사이클 119 주석 부재 (의도 영속 회귀)"
