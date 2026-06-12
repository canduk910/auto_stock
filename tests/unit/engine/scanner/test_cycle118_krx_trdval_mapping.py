"""사이클 118 — KRX ACC_TRDVAL (원) → KIS acml_tr_pbmn (원, 동일) 거래대금 매핑.

근본 원인 (사이클 117 운영 실측, 2026-06-12 16:14 KST):
- stock_master total = 2,697 ticker (사이클 117 KRX 1차 정상화 영구 확정)
- hts_avls_present = 99.85% (사이클 116 환산 정상)
- acml_tr_pbmn_present = 2.85% (사이클 117 누락 영역 영구 확정)

영향: 사이클 108 list_by_filter(min_trade_amount=...) 영역에서 acml_tr_pbmn 키 검사
→ 2.85% 만 통과 → DEFAULT 임계 적용 시 donchian/VCP 신호 -90~95% 폭축 위험.

시정 (사용자 결정 C, 사이클 116 답습 패턴):
_full_universe_load_krx_primary 영역에서 ACC_TRDVAL → acml_tr_pbmn 매핑 추가.
원 단위 동일 (KRX/KIS 양쪽 모두 원 단위) → 직접 매핑 (환산 없음).

사이클 119+ 후속 카드:
- Plan Phase B donchian/VCP stock_master 전환 (acml_tr_pbmn_present 99%+ 정상화 후)
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_SCANNER_PY = Path(__file__).resolve().parents[4] / "src" / "engine" / "scanner.py"


def _simulate_krx_raw_merge(trd_row: dict) -> dict:
    """`_full_universe_load_krx_primary` 의 raw merge 영역 정밀 재현 (사이클 118 영역 포함)."""
    krx_raw: dict = {}
    # bydd_trd raw merge (사이클 115 영역)
    for key in ("MKTCAP", "ACC_TRDVAL", "LIST_SHRS", "TDD_CLSPRC", "TDD_OPNPRC",
                "TDD_HGPRC", "TDD_LWPRC", "ACC_TRDVOL", "FLUC_RT", "MKT_NM",
                "SECT_TP_NM"):
        if key in trd_row:
            krx_raw[key] = trd_row[key]
    # 사이클 116 영역 (MKTCAP → hts_avls)
    if "MKTCAP" in trd_row:
        try:
            mktcap_won = int(str(trd_row["MKTCAP"]).replace(",", "") or 0)
            if mktcap_won > 0:
                krx_raw["hts_avls"] = mktcap_won // 1_000_000
        except (ValueError, TypeError):
            pass
    # 사이클 118 영역 (ACC_TRDVAL → acml_tr_pbmn, 원 단위 동일)
    if "ACC_TRDVAL" in trd_row:
        try:
            trdval_won = int(str(trd_row["ACC_TRDVAL"]).replace(",", "") or 0)
            if trdval_won > 0:
                krx_raw["acml_tr_pbmn"] = trdval_won
        except (ValueError, TypeError):
            pass
    return krx_raw


def test_h1_krx_trdval_to_acml_tr_pbmn_mapping():
    """HIGH-1: KRX ACC_TRDVAL (원) → KIS acml_tr_pbmn (원, 동일) 매핑.

    예: 삼성전자 거래대금 500억원 = 50_000_000_000 원 → acml_tr_pbmn = 50_000_000_000 (원 동일).
    """
    trd_row = {"ISU_CD": "005930", "ACC_TRDVAL": "50000000000"}
    raw = _simulate_krx_raw_merge(trd_row)
    assert raw["acml_tr_pbmn"] == 50_000_000_000  # 500억원 원 단위 동일
    assert raw["ACC_TRDVAL"] == "50000000000"  # KRX raw 영속


def test_h2_list_by_filter_compatibility_via_acml_tr_pbmn():
    """HIGH-2: 사이클 108 list_by_filter 호환성 — acml_tr_pbmn ≥ min_trade_amount.

    예: min_trade_amount=10억원 (10_000_000_000 원) 필터 →
    삼성전자 acml_tr_pbmn=50_000_000_000 ≥ 10_000_000_000 → 통과.
    """
    trd_row = {"ACC_TRDVAL": "50000000000"}  # 500억원
    raw = _simulate_krx_raw_merge(trd_row)
    # 사이클 108 list_by_filter 영역 재현
    acml = int(raw.get("acml_tr_pbmn") or 0)
    min_trade_amount = 10_000_000_000  # 10억원
    assert acml >= min_trade_amount


def test_h3_graceful_trdval_invalid_value():
    """HIGH-3: ACC_TRDVAL 잘못된 값 graceful (raw ACC_TRDVAL 유지 + acml_tr_pbmn 부재)."""
    cases = [
        {"ACC_TRDVAL": ""},
        {"ACC_TRDVAL": "N/A"},
        {"ACC_TRDVAL": None},
        {"ACC_TRDVAL": "0"},  # 0 (>0 가드)
    ]
    for trd_row in cases:
        raw = _simulate_krx_raw_merge(trd_row)
        assert "acml_tr_pbmn" not in raw, f"부적절 입력 {trd_row}: acml_tr_pbmn 부재 의무"


def test_m1_trdval_comma_separator_handling():
    """MEDIUM-1: KRX 응답 영역 comma 영역 (예: '50,000,000,000') graceful."""
    trd_row = {"ACC_TRDVAL": "50,000,000,000"}
    raw = _simulate_krx_raw_merge(trd_row)
    assert raw["acml_tr_pbmn"] == 50_000_000_000


def test_m2_combined_mktcap_and_trdval_mapping():
    """MEDIUM-2: 사이클 116 + 사이클 118 양쪽 매핑 동시 적용 (시총 + 거래대금)."""
    trd_row = {
        "ISU_CD": "005930",
        "MKTCAP": "500000000000000",  # 500조원
        "ACC_TRDVAL": "50000000000",  # 500억원
    }
    raw = _simulate_krx_raw_merge(trd_row)
    # 사이클 116: MKTCAP → hts_avls (백만원)
    assert raw["hts_avls"] == 500_000_000
    # 사이클 118: ACC_TRDVAL → acml_tr_pbmn (원 동일)
    assert raw["acml_tr_pbmn"] == 50_000_000_000


def test_g_ast1_source_code_mapping_present():
    """AST 정적 가드 — scanner.py 영역에 ACC_TRDVAL → acml_tr_pbmn 매핑 코드 영구 영속이.

    미래 시정 누락 영구 차단 (사이클 78/79/108/116 G-AST 패턴 답습).
    """
    source = _SCANNER_PY.read_text(encoding="utf-8")
    assert 'krx_raw["acml_tr_pbmn"]' in source, (
        "ACC_TRDVAL → acml_tr_pbmn 매핑 영역 부재 (사이클 118 시정 회귀)"
    )
    assert "trdval_won" in source, "trdval_won 변수 부재"
    # 사이클 118 영역 주석 영속
    assert "사이클 118" in source, "사이클 118 영역 주석 부재 (의도 영속 회귀)"


def test_g_ast2_no_unit_conversion_for_trdval():
    """AST 영구 가드: ACC_TRDVAL 영역은 단위 환산 부재 (원 단위 동일).

    사이클 116 MKTCAP 영역과 달리 ACC_TRDVAL = 원 단위 동일 → // 1_000_000 환산 금지.
    """
    source = _SCANNER_PY.read_text(encoding="utf-8")
    # trdval_won 영역에 // 1_000_000 또는 * 1_000_000 영역 부재 확인
    # (실제 코드 영역 정합 — comment 영역의 1_000_000 영역은 사이클 116 MKTCAP 영역)
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.BinOp):
            # FloorDiv (//) 영역에서 trdval 영역 검사
            if (isinstance(node.op, ast.FloorDiv) and
                isinstance(node.left, ast.Name) and
                node.left.id == "trdval_won"):
                pytest.fail(
                    "trdval_won 영역에 // 환산 발견 — KRX ACC_TRDVAL는 원 단위 동일, 환산 금지"
                )
