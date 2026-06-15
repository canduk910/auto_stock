"""사이클 98 G-DOC1 — AST 영구 가드: KIS 정본 영역 `chk_*.py main 호출 영역` 인용 의무 (HIGH, **신규 패턴**).

명세 (`_workspace/red/cycle98_fid_rank_sort_cls_code_fix.md`):

**미래 silent 결함 영구 차단 패턴 신설**

사이클 97 backend-dev Green 단계 silent 결함 영역 root cause:
1. KIS fluctuation.py docstring 영역 `(0000: 등락률순)` 거짓 안내 인용 (1차 영역 거짓)
2. KIS chk_fluctuation.py main 호출 영역 `fid_rank_sort_cls_code="0"` (1자리 실측) 영역 미인용

**KIS 정본 영역 위계**:
- KIS chk_*.py main 호출 영역 = **실측 영역** (운영 영역 정합 보장)
- KIS *.py docstring 영역 = 참고 영역 (간헐적 거짓 안내 영역 존재 영구 확정 = 사이클 97)

검증 패턴:
- `_fetch_fluctuation` (또는 KIS API 통합 함수) docstring 영역
- `chk_fluctuation.py` 또는 `chk_*.py main` 또는 `chk_` 인용 주석 영역 ≥1건 영속
- 미래 backend-dev 가 docstring 거짓 안내 영역 인용 영역 영구 차단

Red 상태 (사이클 98): docstring 영역 chk 인용 부재 → FAIL.

영속 의무:
- 사이클 65 H1 답습 (KIS 정본 100% 인용 의무 silent 결함 영역 답습)
- 사이클 81 silent 결함 영구 차단 패턴 답습
- 사이클 88 G-REJECT 답습 (외부 LLM 영구 차단 정적 검증)
- 사이클 97 H-5 답습 (silent 결함 영역 영구 차단 패턴 확장)
- 미래 영구 차단 패턴 신설 (사이클 98+ KIS API 통합 영역 영구 가드)
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from tests.unit.ast._ast_helpers import find_function_def, read_module_source

pytestmark = pytest.mark.unit


def _scanner_module_path() -> Path:
    """scanner.py 모듈 절대 경로."""
    import src.engine.scanner as scanner_mod
    return Path(scanner_mod.__file__)


def _scanner_module_source() -> str:
    """scanner.py source text."""
    return read_module_source(_scanner_module_path())


def _get_fetch_fluctuation_docstring() -> str | None:
    """`_fetch_fluctuation` 함수 docstring 영역 추출 (AST FunctionDef / AsyncFunctionDef)."""
    source = _scanner_module_source()
    node = find_function_def(source, "_fetch_fluctuation")
    if node is None:
        return None
    return ast.get_docstring(node)


@pytest.mark.xfail(
    strict=False,
    reason=(
        "사이클 101 Q68=A — `_fetch_fluctuation` 함수 자체 영구 폐기 "
        "(fluctuation API → market_cap FHPST01740000 전환). "
        "사이클 98 시점 chk 인용 의무 AST 가드 의도 영속 보존 (사이클 66 K-2 패턴 답습)."
    ),
)
def test_g_doc1_chk_citation_required_in_fetch_fluctuation_docstring():
    """G-DOC1: `_fetch_fluctuation` docstring 영역 `chk_fluctuation.py` 영역 인용 의무.

    KIS 정본 영역 위계:
    - KIS chk_*.py main 호출 영역 = **실측 영역** (운영 정합 보장)
    - KIS *.py docstring 영역 = 참고 영역 (간헐적 거짓 안내 영역 존재, 사이클 97 확정)

    사이클 97 영역 결함 = KIS fluctuation.py docstring `(0000: 등락률순)` 인용
    → KIS 거부 (OPSQ2002 INVALID INPUT_FILED_SIZE [FID_RANK_SORT_CLS_CODE] [4])

    사이클 98 영역 시정 = KIS chk_fluctuation.py main 호출 영역 `"0"` 인용
    → KIS 정본 영구 정합

    검증 영역 (AST docstring 추출 + 인용 키워드 검출):
    - `_fetch_fluctuation` 함수 docstring 영역 추출
    - 다음 인용 패턴 중 ≥1건 영속:
      * "chk_fluctuation.py" 영역
      * "chk_fluctuation" 영역 (확장자 무관)
      * "chk_*.py main" 영역 (일반 패턴)
      * "chk main" 영역 (단축 패턴)
    - 미래 backend-dev 영역 docstring 거짓 안내 영역 인용 영구 차단

    Red 상태 (사이클 98 Red): docstring 영역 chk 인용 부재 → FAIL.

    Green (backend-dev): docstring 영역 다음 영역 추가
        '''
        ...
        영역 정본 인용: KIS chk_fluctuation.py main 호출 영역
            fid_rank_sort_cls_code="0"      # ← 1자리 ✓ (KIS 정본)
        영역 거짓 안내: KIS fluctuation.py docstring 영역
            (0000: 등락률순)  # ← 4자리 ✗ (사이클 97 영역 결함)
        '''
        → PASS.

    영속 의무 (미래 영구 차단 패턴 신설):
    - 사이클 98+ KIS API 통합 영역 신규 함수 영역 docstring 영역 chk 인용 의무
    - silent 결함 영구 차단 패턴 신설 (사이클 98 영역 첫 도입)
    - KIS 정본 영역 영구 위계 명시
    """
    docstring = _get_fetch_fluctuation_docstring()

    assert docstring is not None, (
        "\n사이클 98 G-DOC1 위반 — `_fetch_fluctuation` 함수 docstring 영역 부재:\n"
        "  영역 위치: src/engine/scanner.py `_fetch_fluctuation` 함수\n"
        "  KIS 정본 영역 인용 의무 (chk_fluctuation.py main 호출 영역)"
    )

    # 영역 정밀화 (사이클 98 G-DOC1 본의):
    # 사이클 97 영역 docstring 에 이미 `chk_fluctuation.py COLUMN_MAPPING` 인용 영속 (응답 키 영역)
    # 그러나 결함 영역 (`FID_RANK_SORT_CLS_CODE` 4자리) docstring 영역 동행 인용 부재
    # → G-DOC1 영역 = `FID_RANK_SORT_CLS_CODE` 영역 영속 + chk 인용 동시 검증 (정밀)

    # (1) FID_RANK_SORT_CLS_CODE 영역 docstring 인용 영속 검증
    has_fid_rank = "FID_RANK_SORT_CLS_CODE" in docstring
    assert has_fid_rank, (
        f"\n사이클 98 G-DOC1 위반 — docstring 영역 `FID_RANK_SORT_CLS_CODE` 영역 영속 부재:\n"
        f"  영역 위치: src/engine/scanner.py `_fetch_fluctuation` docstring\n"
        f"  사이클 97 영역 영속: docstring `FID_RANK_SORT_CLS_CODE = ...` 영역 영구 영속 의무"
    )

    # (2) FID_RANK_SORT_CLS_CODE 영역 docstring value 영역 = "0" 영속 검증 (1자리)
    # docstring 영역 = `FID_RANK_SORT_CLS_CODE = "0000"` (사이클 97 결함) → `"0"` (사이클 98 시정)
    import re
    docstring_value_match = re.search(
        r'FID_RANK_SORT_CLS_CODE\s*=\s*"([^"]+)"',
        docstring,
    )
    if docstring_value_match:
        docstring_value = docstring_value_match.group(1)
        assert docstring_value == "0", (
            f"\n사이클 98 G-DOC1 위반 — docstring `FID_RANK_SORT_CLS_CODE` value 영역 결함:\n"
            f"  기대: '0' (1자리, KIS chk_fluctuation.py main 정본 영속)\n"
            f"  실제 docstring: 'FID_RANK_SORT_CLS_CODE = \"{docstring_value}\"'\n"
            f"  사이클 97 영역 docstring (`\"0000\"`) = KIS fluctuation.py docstring 거짓 안내 인용 결함\n"
            f"  사이클 98 영역 시정 = docstring `FID_RANK_SORT_CLS_CODE = \"0\"` 영속 의무\n"
            f"  Green (backend-dev): src/engine/scanner.py L1497 docstring 영역\n"
            f"      `FID_RANK_SORT_CLS_CODE = \"0000\"` → `FID_RANK_SORT_CLS_CODE = \"0\"`"
        )

    # (3) 인용 키워드 패턴 (chk_*.py main 호출 영역 인용 의무) — 영역 명시
    # `FID_RANK_SORT_CLS_CODE` 영역 ±10줄 영역 내 chk 인용 영속 검증 (영역 정밀)
    docstring_lines = docstring.splitlines()
    fid_rank_line_idx = next(
        (i for i, line in enumerate(docstring_lines) if "FID_RANK_SORT_CLS_CODE" in line),
        None,
    )

    if fid_rank_line_idx is not None:
        # ±10 줄 윈도우 내 chk 인용 영속 검증
        start = max(0, fid_rank_line_idx - 10)
        end = min(len(docstring_lines), fid_rank_line_idx + 11)
        window = "\n".join(docstring_lines[start:end])

        citation_keywords = [
            "chk_fluctuation.py",
            "chk_fluctuation",
            "chk_*.py main",
            "chk main",
            "chk_*.py",
        ]

        window_matched = [kw for kw in citation_keywords if kw in window]
        assert window_matched, (
            f"\n사이클 98 G-DOC1 위반 — docstring `FID_RANK_SORT_CLS_CODE` 영역 ±10줄 영역 chk 인용 부재:\n"
            f"  영역 위치: src/engine/scanner.py `_fetch_fluctuation` docstring\n"
            f"  기대 인용 영역 (≥1건, ±10줄 윈도우): {citation_keywords}\n"
            f"  실제 윈도우 영역 ({end - start}줄):\n"
            f"    {window!r}\n"
            f"\n"
            f"  G-DOC1 본의: `FID_RANK_SORT_CLS_CODE` 영역 결함 영역에 KIS 정본 인용 동행 의무\n"
            f"  사이클 97 영역 결함 = docstring 영역 `\"0000\"` 인용 (chk 인용 부재)\n"
            f"  사이클 98 영역 시정 = docstring 영역 `\"0\"` + chk 인용 동행 영속 의무\n"
            f"\n"
            f"  Green (backend-dev): docstring 영역 다음 영역 추가\n"
            f"      FID_RANK_SORT_CLS_CODE = \"0\"  (KIS chk_fluctuation.py main 호출 영역 정본)\n"
        )

    # (4) 기존 영역 (응답 키 영역) chk 인용 영속 (사이클 97 영속)
    citation_keywords = [
        "chk_fluctuation.py",
        "chk_fluctuation",
        "chk_*.py main",
        "chk main",
    ]

    matched_keywords = [kw for kw in citation_keywords if kw in docstring]

    assert matched_keywords, (
        f"\n사이클 98 G-DOC1 위반 — `_fetch_fluctuation` docstring 영역 KIS 정본 인용 부재:\n"
        f"  영역 위치: src/engine/scanner.py `_fetch_fluctuation` docstring\n"
        f"  기대 인용 영역 (≥1건): {citation_keywords}\n"
        f"  실제 docstring 영역 ({len(docstring)} 문자):\n"
        f"    {docstring[:500]!r}{'...' if len(docstring) > 500 else ''}\n"
        f"\n"
        f"  미래 silent 결함 영구 차단 패턴 신설:\n"
        f"  - KIS chk_*.py main 호출 영역 = 실측 영역 (운영 정합 보장)\n"
        f"  - KIS *.py docstring 영역 = 참고 영역 (간헐적 거짓 안내 영역 존재, 사이클 97 확정)\n"
        f"\n"
        f"  Green 의무 (backend-dev): docstring 영역 다음 영역 추가\n"
        f"      KIS 정본 인용: chk_fluctuation.py main 호출 영역\n"
        f"          fid_rank_sort_cls_code=\"0\"      # 1자리 ✓ (KIS 정본)\n"
        f"\n"
        f"  사이클 영역 패턴 답습:\n"
        f"  - 사이클 65 H1 (KIS 정본 100% 인용 의무)\n"
        f"  - 사이클 81 (bfdy_clpr 1줄 silent 결함 영구 시정)\n"
        f"  - 사이클 97 영역 (KIS docstring 거짓 안내 인용 silent 결함 발견)\n"
        f"  - 사이클 98 (G-DOC1 영구 차단 패턴 신설)"
    )
