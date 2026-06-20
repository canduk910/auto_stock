"""사이클 129 — `_stock_master_master_load_once()` Red 회귀 가드.

배경:
- domain-consult 의제 2 (시총 단위 환산) + 의제 4 (hot path 키 선별) 채택
- 시총 환산: master_raw.prdy_avls_scal (억) × 100 = raw.hts_avls (백만원)
  - 1 억 원 = 100,000,000 원 = 100 백만원 → × 100
  - 사이클 129 Q12 시정 (사용자 verbatim 정합 검증 후 정정 영속).
  - 결함 사유: team-leader 자체 자문 영역 "× 10,000" 단위 곱셈 결함 → "× 100" 정합.
- 정합 검증 임계: ±5% OK / ±20% WARNING / 초과 ERROR

회귀 가드 (G-ML1/G-ML2 활성 / G-ML3~G-ML5 = 사이클 167 폐기로 xfail):
- G-ML1: _stock_master_master_load_once() 정상 (KOSPI + KOSDAQ 통합)
- G-ML2: force=True 영속 (사이클 120 패턴)
- G-ML3: [사이클 167 폐기 — xfail] market_cap_master_to_millions dead code 제거 (callsite 0건).
  헬퍼 존재 계약을 xfail 로 박제 (의미 전환, 사이클 66 K-2). 시총 환산 명세는 역사적 기록.
- G-ML4: [사이클 167 폐기 — xfail] validate_market_cap_consistency dead code 제거 (callsite 0건).
- G-ML5: [사이클 167 폐기 — xfail] validate_market_cap_consistency dead code 제거 (정합 검증 skip 분기).

재도입 차단은 AST 가드 tests/unit/ast/test_cycle167_ast_no_dead_market_cap_funcs.py 로 이관.
"""
from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_g_ml1_master_load_once_kospi_kosdaq(monkeypatch):
    """G-ML1: _stock_master_master_load_once() 정상 (KOSPI + KOSDAQ 통합)."""
    from src.engine import scanner

    assert hasattr(scanner, "_stock_master_master_load_once"), (
        "G-ML1: scanner._stock_master_master_load_once() 함수 부재"
    )

    # 다운로드 함수 mock (실제 KIS 호출 0건)
    async def _mock_download_kospi():
        return [
            {"mksc_shrn_iscd": "005930", "hts_kor_isnm": "삼성전자", "trht_yn": "N"},
        ]

    async def _mock_download_kosdaq():
        return [
            {"mksc_shrn_iscd": "086520", "hts_kor_isnm": "에코프로", "trht_yn": "N"},
        ]

    # upsert_master_raw mock
    upserted = []

    # 사이클 153 K-2 의미 전환 — upsert_master_raw 시그너처에 is_kospi200 / is_kosdaq150 추가.
    async def _mock_upsert(ticker, master_raw, *, is_kospi200=False, is_kosdaq150=False):
        upserted.append((ticker, master_raw))

    from src.api import kis_master as _kis_master
    from src.db import stock_master as _stock_master

    monkeypatch.setattr(_kis_master, "download_kospi_master", _mock_download_kospi)
    monkeypatch.setattr(_kis_master, "download_kosdaq_master", _mock_download_kosdaq)
    monkeypatch.setattr(_stock_master, "upsert_master_raw", _mock_upsert)

    result = await scanner._stock_master_master_load_once()

    # 반환 dict 영역 = kospi_count + kosdaq_count + total 영역
    assert isinstance(result, dict), (
        f"G-ML1: 반환 dict 영역 위반 (result={result!r})"
    )
    assert result.get("kospi_count", 0) >= 1, "G-ML1: kospi_count 영역 부재"
    assert result.get("kosdaq_count", 0) >= 1, "G-ML1: kosdaq_count 영역 부재"
    assert len(upserted) >= 2, "G-ML1: upsert 호출 영역 부재 (KOSPI 1 + KOSDAQ 1)"


@pytest.mark.asyncio
async def test_g_ml2_force_true_persistence(monkeypatch):
    """G-ML2: force=True 영속 영역 (사이클 120 패턴 답습)."""
    import inspect

    from src.engine import scanner

    sig = inspect.signature(scanner._stock_master_master_load_once)
    assert "force" in sig.parameters, (
        "G-ML2: force 인자 영역 부재 (사이클 120 패턴 위반)"
    )
    # 디폴트 = True 영역 (사이클 120 force 영속 디폴트)
    assert sig.parameters["force"].default is True, (
        "G-ML2: force 디폴트 True 영역 위반 — 사이클 120 영속 답습 위반"
    )


@pytest.mark.xfail(
    reason="사이클 167 — market_cap_master_to_millions dead code 폐기 (callsite 0건). "
    "사이클 129 시점 헬퍼 존재 계약 영속 보존 (의미 전환, 사이클 66 K-2 패턴).",
    strict=False,
)
def test_g_ml3_market_cap_conversion_helper():
    """G-ML3: 시총 환산 헬퍼 정확 — 마스터 (억) × 100 = raw (백만원).

    [사이클 167 폐기 — xfail] market_cap_master_to_millions 는 production callsite 0건
    dead code 로 제거됨. 아래 환산 명세는 사이클 129 도입 당시 계약의 *역사적 기록* 이며
    현재 헬퍼는 부재 (의미 전환, 사이클 66 K-2). 시총 필터 본체는 list_by_filter /
    list_paged_by_filter 가 직접 수행 (사이클 166 억원 정합).

    환산 영역 (사이클 129 Q12 시정 — 역사적 기록):
    - 1 억 원 = 100,000,000 원 = 100 백만원 → × 100
    - 사용자 verbatim "× 100" 정합 검증 후 정정 영속.
    - 결함 사유: team-leader 자체 자문 "× 10,000" 단위 곱셈 결함 차단.

    예 시나리오:
    - 삼성전자 시총 ~500조원 = master_raw 5,000,000 (억) × 100 = 500,000,000 (백만원)
    - 1조원 = 10,000 (억) × 100 = 1,000,000 (백만원)
    - 100억원 = 100 (억) × 100 = 10,000 (백만원)
    - 1억원 = 1 (억) × 100 = 100 (백만원)
    """
    from src.engine import scanner

    assert hasattr(scanner, "market_cap_master_to_millions"), (
        "G-ML3: market_cap_master_to_millions 헬퍼 부재"
    )

    # 삼성전자 시총 ~500조원 = 5,000,000 억 × 100 = 500,000,000 백만원
    result = scanner.market_cap_master_to_millions(5_000_000)
    assert result == 500_000_000, (
        f"G-ML3: 시총 환산 결함 (5,000,000 억 → {result} 백만원, 기대 500,000,000)"
    )

    # 1조원 = 10,000 억 × 100 = 1,000,000 백만원
    result_1trillion = scanner.market_cap_master_to_millions(10_000)
    assert result_1trillion == 1_000_000, (
        f"G-ML3: 1조원 환산 결함 ({result_1trillion} != 1,000,000)"
    )

    # 100억원 = 100 억 × 100 = 10,000 백만원
    result_small = scanner.market_cap_master_to_millions(100)
    assert result_small == 10_000, (
        f"G-ML3: 100억원 환산 결함 ({result_small} != 10,000)"
    )

    # 1억원 = 1 억 × 100 = 100 백만원 (단위 정합 영구 영속)
    result_one_eok = scanner.market_cap_master_to_millions(1)
    assert result_one_eok == 100, (
        f"G-ML3: 1억원 환산 결함 ({result_one_eok} != 100) — × 100 정합 영구 영속"
    )


@pytest.mark.xfail(
    reason="사이클 167 — validate_market_cap_consistency dead code 폐기 (callsite 0건). "
    "사이클 129 시점 헬퍼 존재 계약 영속 보존 (의미 전환, 사이클 66 K-2 패턴).",
    strict=False,
)
def test_g_ml4_consistency_validation_thresholds():
    """G-ML4: 정합 검증 임계 ±5% OK / ±20% WARNING / 초과 ERROR.

    [사이클 167 폐기 — xfail] validate_market_cap_consistency 는 production callsite 0건
    dead code 로 제거됨. 아래 임계 명세는 역사적 기록 (의미 전환, 사이클 66 K-2).

    domain-consult 의제 2 채택 — 정합 검증 임계 영역.
    환산 영역 (Q12 시정 — 역사적 기록): 100 억 × 100 = 10,000 백만원.
    """
    from src.engine import scanner

    assert hasattr(scanner, "validate_market_cap_consistency"), (
        "G-ML4: validate_market_cap_consistency 헬퍼 부재"
    )

    # 시나리오 1: 완벽 정합 (마스터 100 억 × 100 = 10,000 백만원, raw 10,000 백만원)
    grade, diff = scanner.validate_market_cap_consistency(100, 10_000)
    assert grade == "OK", f"G-ML4: 완벽 정합 OK 위반 (grade={grade!r}, diff={diff})"

    # 시나리오 2: ±3% 정합 (마스터 100 억 = 10,000, raw 10,300) → OK
    grade2, _ = scanner.validate_market_cap_consistency(100, 10_300)
    assert grade2 == "OK", f"G-ML4: ±3% OK 위반 (grade={grade2!r})"

    # 시나리오 3: ±10% (마스터 100 억 = 10,000, raw 11,000) → WARNING
    grade3, _ = scanner.validate_market_cap_consistency(100, 11_000)
    assert grade3 == "WARNING", f"G-ML4: ±10% WARNING 위반 (grade={grade3!r})"

    # 시나리오 4: ±50% (마스터 100 억 = 10,000, raw 15,000) → ERROR
    grade4, _ = scanner.validate_market_cap_consistency(100, 15_000)
    assert grade4 == "ERROR", f"G-ML4: ±50% ERROR 위반 (grade={grade4!r})"


@pytest.mark.xfail(
    reason="사이클 167 — validate_market_cap_consistency dead code 폐기 (callsite 0건). "
    "사이클 129 시점 헬퍼 존재 계약 영속 보존 (의미 전환, 사이클 66 K-2 패턴).",
    strict=False,
)
def test_g_ml5_consistency_validation_skip_zero():
    """G-ML5: 0/비결정 영역 회피 — 정합 검증 skip = OK 반환.

    [사이클 167 폐기 — xfail] validate_market_cap_consistency 는 production callsite 0건
    dead code 로 제거됨. 아래 skip 명세는 역사적 기록 (의미 전환, 사이클 66 K-2).

    domain-consult 의제 2 채택 — master_raw 0 또는 raw 0 영역 = 정합 검증 skip.
    """
    from src.engine import scanner

    # master_raw 0 → skip
    grade, diff = scanner.validate_market_cap_consistency(0, 10_000)
    assert grade == "OK", f"G-ML5: master 0 skip 위반 (grade={grade!r})"

    # raw 0 → skip
    grade2, diff2 = scanner.validate_market_cap_consistency(100, 0)
    assert grade2 == "OK", f"G-ML5: raw 0 skip 위반 (grade={grade2!r})"

    # 양쪽 0 → skip
    grade3, diff3 = scanner.validate_market_cap_consistency(0, 0)
    assert grade3 == "OK", f"G-ML5: 양쪽 0 skip 위반 (grade={grade3!r})"
