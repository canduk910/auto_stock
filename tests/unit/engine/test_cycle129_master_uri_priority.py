"""사이클 129 — scanner 진입 차단 영역 master_raw 우선 분기 Red 회귀 가드.

배경:
- domain-consult 의제 3 (키별 우선순위) 채택 — 1단계 차단 7건 master_raw 우선
- 1단계 차단 7건:
  - trht_yn (거래정지)
  - sltr_yn (정리매매)
  - mang_issu_yn (관리종목)
  - ssts_hot_yn (공매도과열)
  - stange_runup_yn (이상급등)
  - mrkt_alrm_cls_code >= "02" (시장경고 경고/위험)
  - invt_alrm_yn (KOSDAQ 투자주의환기)

회귀 가드 (G-UP1/G-UP2 활성 / G-UP3 = 사이클 167 폐기로 xfail):
- G-UP1: 1단계 차단 7건 매수 진입 차단 분기
- G-UP2: master_raw 부재 시 raw 폴백 chain (nxt_tradable 영역)
- G-UP3: [사이클 167 폐기 — xfail] get_market_cap_millions dead code 제거 (callsite 0건).
  헬퍼 존재 계약을 xfail 로 박제 (의미 전환, 사이클 66 K-2). 재도입 차단은 AST 가드
  tests/unit/ast/test_cycle167_ast_no_dead_market_cap_funcs.py 로 이관.
"""
from __future__ import annotations

import pytest


def test_g_up1_block_for_entry_7_keys():
    """G-UP1: 1단계 차단 7건 매수 진입 차단 분기.

    domain-consult 의제 4 1단계 = 필수 차단 7건.
    """
    from src.engine import scanner

    assert hasattr(scanner, "_is_master_blocked_for_entry"), (
        "G-UP1: _is_master_blocked_for_entry 헬퍼 부재"
    )

    # 각 1단계 차단 7건 검증
    block_cases = [
        ({"trht_yn": "Y"}, "거래정지"),
        ({"sltr_yn": "Y"}, "정리매매"),
        ({"mang_issu_yn": "Y"}, "관리종목"),
        ({"ssts_hot_yn": "Y"}, "공매도과열"),
        ({"stange_runup_yn": "Y"}, "이상급등"),
        ({"mrkt_alrm_cls_code": "02"}, "시장경고"),  # 경고
        ({"mrkt_alrm_cls_code": "03"}, "시장경고"),  # 위험
        ({"invt_alrm_yn": "Y"}, "투자주의환기"),  # KOSDAQ
    ]

    for master_raw, expected_reason_substr in block_cases:
        blocked, reason = scanner._is_master_blocked_for_entry(master_raw)
        assert blocked is True, (
            f"G-UP1: 차단 영역 위반 master_raw={master_raw!r}"
        )
        assert expected_reason_substr in reason, (
            f"G-UP1: 차단 사유 영역 위반 (master_raw={master_raw!r}, reason={reason!r}, "
            f"expected substr {expected_reason_substr!r})"
        )

    # 정상 영역 (1단계 차단 0건) = 통과
    safe_master = {
        "trht_yn": "N", "sltr_yn": "N", "mang_issu_yn": "N",
        "ssts_hot_yn": "N", "stange_runup_yn": "N",
        "mrkt_alrm_cls_code": "00", "invt_alrm_yn": "N",
    }
    blocked, reason = scanner._is_master_blocked_for_entry(safe_master)
    assert blocked is False, (
        f"G-UP1: 정상 영역 차단 위반 (reason={reason!r})"
    )


def test_g_up2_master_absent_raw_fallback_nxt():
    """G-UP2: master_raw 부재 시 raw 폴백 chain (nxt_tradable 영역).

    domain-consult 의제 3 (키별 우선순위 표):
    - nxt_tradable = raw 영속 (마스터 미존재 영역)
    """
    from src.engine import scanner

    # 빈 master_raw (마스터 미수집) = 차단 결정 없음 → 통과 (raw 폴백 영역)
    empty_master = {}
    blocked, reason = scanner._is_master_blocked_for_entry(empty_master)
    assert blocked is False, (
        f"G-UP2: 빈 master_raw 차단 위반 — raw 폴백 chain 영역 (reason={reason!r})"
    )


@pytest.mark.xfail(
    reason="사이클 167 — get_market_cap_millions dead code 폐기 (callsite 0건). "
    "사이클 129 시점 헬퍼 존재 계약 영속 보존 (의미 전환, 사이클 66 K-2 패턴).",
    strict=False,
)
def test_g_up3_market_cap_master_first_raw_fallback():
    """G-UP3: 시총 영역 master_raw 우선 + raw 폴백.

    [사이클 167 폐기 — xfail] get_market_cap_millions 는 production callsite 0건
    dead code 로 제거됨. 아래 우선순위/환산 명세는 역사적 기록 (의미 전환, 사이클 66 K-2).
    시총 필터 본체는 list_by_filter / list_paged_by_filter 가 직접 수행 (사이클 166 억원 정합).

    domain-consult 의제 2 채택 — master_raw.prdy_avls_scal (억) 우선,
    부재 시 raw.hts_avls (백만원) 폴백. 사이클 116 패턴 답습.
    환산 영역 (Q12 시정 — 역사적 기록): 100 억 × 100 = 10,000 백만원.
    """
    from src.engine import scanner

    assert hasattr(scanner, "get_market_cap_millions"), (
        "G-UP3: get_market_cap_millions 통합 헬퍼 부재 (master 우선 + raw 폴백)"
    )

    # 시나리오 1: master_raw 있음 → 우선 사용 (억 × 100 = 백만원)
    master_present = {"prdy_avls_scal": "100"}  # 100 억
    raw_with_diff = {"hts_avls": "999_999"}  # raw 다른 값 — master 우선이므로 무시
    result1 = scanner.get_market_cap_millions(master_present, raw_with_diff)
    assert result1 == 10_000, (
        f"G-UP3: master 우선 영역 위반 (result={result1}, 기대 10,000 = 100억 × 100)"
    )

    # 시나리오 2: master_raw 부재 → raw 폴백
    empty_master = {}
    raw_only = {"hts_avls": "500000"}  # 500,000 백만원
    result2 = scanner.get_market_cap_millions(empty_master, raw_only)
    assert result2 == 500_000, (
        f"G-UP3: raw 폴백 영역 위반 (result={result2}, 기대 500,000)"
    )

    # 시나리오 3: 양쪽 부재 → 0 (graceful)
    result3 = scanner.get_market_cap_millions({}, {})
    assert result3 == 0, (
        f"G-UP3: 양쪽 부재 graceful 위반 (result={result3})"
    )
