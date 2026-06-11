"""사이클 99 G-DOC1 — `_fetch_fluctuation` docstring KIS API 본질 한계 영구 명문화 (MEDIUM).

명세 (`_workspace/red/cycle99_pagination_removal_60_ticker_persistence.md`):

- KIS API 본질 한계 영구 확정 (운영 실증 사이클 96 + 사이클 98)
- 사이클 99 = docstring 영역 본질 한계 + 60 ticker 영구 영속 명문화 의무

영속 영역 매트릭스 (≥1건 영구 영속):
- "KIS API" + "페이징" + ("미지원" or "영구") 영역 명문화
- "60 ticker" 또는 "단일 페이지" 영역 명문화 (KIS 영역 본질 한계 영구 수용)
- "chk_fluctuation.py" 영역 KIS 정본 인용 영속 (사이클 98 G-DOC1 영속)

Red 상태 (사이클 99): 사이클 97 영역 docstring 페이징 영역 명문화 부재 → FAIL.

Green (backend-dev): docstring 영역 KIS 영역 본질 한계 명문화 추가 → PASS.

영속 의무:
- 사이클 98 G-DOC1 답습 (KIS chk_*.py 정본 인용 의무 영구 가드)
- 사이클 99 패턴 신설 = KIS API 본질 한계 영구 영속 명문화
- 미래 backend-dev 가 KIS 영역 페이징 영역 재도입 silent 결함 영구 차단
- silent 결함 영구 차단 21 회 누적
"""
from __future__ import annotations

import inspect

import pytest

pytestmark = pytest.mark.unit


def _fetch_fluctuation_docstring() -> str:
    """`_fetch_fluctuation` docstring 추출."""
    import src.engine.scanner as scanner_mod
    try:
        doc = inspect.getdoc(scanner_mod._fetch_fluctuation)
        if doc is None:
            pytest.fail(
                "\n사이클 99 G-DOC1 Red 상태 — `_fetch_fluctuation` docstring 부재.\n"
                "  사이클 97 영역 = docstring 영속 의무"
            )
        return doc
    except AttributeError:
        pytest.fail(
            "\n사이클 99 G-DOC1 Red 상태 — `_fetch_fluctuation` 함수 부재.\n"
            "  사이클 97 영역 = `_fetch_fluctuation` 신규 함수 영속 의무"
        )


@pytest.mark.xfail(
    strict=False,
    reason=(
        "사이클 101 Q68=A — `_fetch_fluctuation` 함수 자체 영구 폐기 "
        "(fluctuation API → market_cap FHPST01740000 전환). "
        "사이클 99 시점 docstring 영역 명문화 검증 의도 영속 보존 (사이클 66 K-2 패턴 답습)."
    ),
)
def test_g_doc1_kis_api_pagination_unsupported_documented_persistence():
    """G-DOC1: `_fetch_fluctuation` docstring 영역 KIS API 본질 한계 영구 명문화.

    영속 영역 매트릭스 (≥1건 영구 영속):

    1. KIS API 페이징 미지원 영구 영속 명문화 (영역 키워드 매트릭스):
       - 그룹 A: "KIS API" 또는 "KIS"
       - 그룹 B: "페이징" 또는 "pagination" 또는 "tr_cont"
       - 그룹 C: "미지원" 또는 "영구" 또는 "본질 한계" 또는 "무용"
       - 영구 영속 조건: A ∩ B ∩ C 의 키워드 영역 ≥1건

    2. 60 ticker 또는 단일 페이지 영역 명문화 (KIS 본질 한계 영구 수용):
       - "60 ticker" 또는 "단일 페이지" 또는 "30 한도" 영역 ≥1건

    3. KIS chk_*.py 정본 인용 영속 (사이클 98 G-DOC1 영속):
       - "chk_fluctuation.py" 영역 ≥1건

    Red 상태 (사이클 99): 사이클 97 영역 docstring = 페이징 영역 명문화 부재 → FAIL.

    Green (backend-dev): docstring 영역 KIS API 본질 한계 명문화 추가 의무.
        - "KIS API 페이징 미지원 영구 확정" (사이클 99 신규 영역)
        - "60 ticker 영구 영속 수용 (KOSPI 30 + KOSDAQ 30)" (사이클 99 신규 영역)
        - "chk_fluctuation.py main 호출 영역 정본 영속" (사이클 98 G-DOC1 영속)

    영속 의무:
    - 미래 backend-dev 가 KIS 영역 페이징 영역 재도입 silent 결함 영구 차단
    - 사이클 98 G-DOC1 패턴 답습 (KIS 정본 인용 의무 영구 가드)
    - 사이클 99 패턴 신설 = KIS API 본질 한계 영구 영속 명문화
    """
    doc = _fetch_fluctuation_docstring()
    doc_lower = doc.lower()

    violations: list[str] = []

    # 가드 1: KIS API 페이징 미지원 영구 영속 명문화 (그룹 A ∩ B ∩ C)
    group_a_kis = ["KIS API", "KIS"]
    group_b_pagination = ["페이징", "pagination", "tr_cont"]
    group_c_unsupported = ["미지원", "영구", "본질 한계", "무용"]

    has_group_a = any(kw in doc for kw in group_a_kis)
    has_group_b = any(kw.lower() in doc_lower for kw in group_b_pagination)
    has_group_c = any(kw in doc for kw in group_c_unsupported)

    if not (has_group_a and has_group_b and has_group_c):
        violations.append(
            f"  - KIS API 페이징 미지원 영구 영속 명문화 영역 부재:\n"
            f"    그룹 A (KIS API/KIS) = {has_group_a}\n"
            f"    그룹 B (페이징/pagination/tr_cont) = {has_group_b}\n"
            f"    그룹 C (미지원/영구/본질 한계/무용) = {has_group_c}\n"
            f"    Green: docstring 영역 = 'KIS API 페이징 미지원 영구 확정' 명문화 의무"
        )

    # 가드 2: 60 ticker 또는 단일 페이지 영역 명문화 (KIS 본질 한계 영구 수용)
    has_60_ticker = "60 ticker" in doc or "단일 페이지" in doc or "30 한도" in doc
    if not has_60_ticker:
        violations.append(
            f"  - 60 ticker 또는 단일 페이지 영역 명문화 부재:\n"
            f"    영속 영역: '60 ticker' / '단일 페이지' / '30 한도' (≥1건)\n"
            f"    Green: docstring 영역 = '60 ticker 영구 영속 수용 (KOSPI 30 + KOSDAQ 30)' 명문화 의무"
        )

    # 가드 3: KIS chk_*.py 정본 인용 영속 (사이클 98 G-DOC1 영속)
    has_chk_citation = "chk_fluctuation.py" in doc or "chk_fluctuation" in doc
    if not has_chk_citation:
        violations.append(
            f"  - KIS chk_fluctuation.py 정본 인용 영역 부재 (사이클 98 G-DOC1 영속 위반):\n"
            f"    영속 영역: 'chk_fluctuation.py' (≥1건)\n"
            f"    Green: docstring 영역 = 'chk_fluctuation.py main 호출 영역 정본 영속' 영속 의무"
        )

    assert not violations, (
        f"\n사이클 99 G-DOC1 위반 — `_fetch_fluctuation` docstring 영역 KIS API 본질 한계 영구 영속 명문화 위반:\n"
        + "\n".join(violations)
        + "\n\n"
        f"  현재 docstring 영역 (앞 200자):\n    {doc[:200]!r}\n\n"
        f"  KIS API 본질 한계 영구 확정 매트릭스 (사이클 96 + 사이클 98 운영 실증):\n"
        f"    - volume_rank (FHPST01710000) = tr_cont 'M' 영구 비반환\n"
        f"    - fluctuation (FHPST01700000) = tr_cont 'M' 영구 비반환\n"
        f"    - KIS API 전체 영역 = 페이징 미지원 영구 확정\n"
        f"  사이클 99 영역 영구 영속:\n"
        f"    - 60 ticker 영구 영속 수용 (KOSPI 30 + KOSDAQ 30)\n"
        f"    - 페이징 영역 영구 폐기 (사이클 91~98 모든 시정 영구 무용)\n"
        f"    - docstring 영역 영구 명문화 = 미래 backend-dev 재도입 silent 결함 영구 차단\n"
        f"  명세 영속: `_workspace/red/cycle99_pagination_removal_60_ticker_persistence.md`\n"
        f"  silent 결함 영구 차단 21 회 누적 (사이클 60~98 + 99)"
    )
