"""사이클 98 G-AST1 — AST 영구 가드: `FID_RANK_SORT_CLS_CODE` 1자리 영속 + 다자리 영구 차단 (HIGH).

명세 (`_workspace/red/cycle98_fid_rank_sort_cls_code_fix.md`):

- KIS chk_fluctuation.py main 호출 영역 정본 = `fid_rank_sort_cls_code="0"` (1자리)
- 사이클 97 영역 = `"FID_RANK_SORT_CLS_CODE": "0000"` (4자리, docstring 거짓 안내 인용 결함)
- AST 정적 가드 = scanner.py source 전수 grep + ast 검증

검증 패턴 (사이클 81 `bfdy_clpr` + 사이클 97 H-5 답습):
- scanner.py source 영역 `"FID_RANK_SORT_CLS_CODE": "0"` (1자리) ≥1건 영속 (KIS 정본 정합)
- scanner.py source 영역 `"FID_RANK_SORT_CLS_CODE": "0000"` (4자리) 영구 차단
- scanner.py source 영역 `"FID_RANK_SORT_CLS_CODE": "00"` 또는 `"000"` 또는 다른 다자리 영구 차단

Red 상태 (사이클 98): production `"0000"` 영속 → FAIL.

영속 의무:
- 사이클 81 `bfdy_clpr` AST 가드 답습 (silent 결함 영구 차단 패턴)
- 사이클 88 G-REJECT 답습 (외부 LLM 정적 검증 패턴)
- 사이클 97 H-5 답습 (volume_rank URL/TR_ID 영구 차단 패턴 확장)
- KIS 정본 영역 영구 정합 (chk_fluctuation.py main 호출 영역)
- silent 결함 영구 차단 20 회 누적
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit


def _scanner_module_path() -> Path:
    """scanner.py 모듈 절대 경로."""
    import src.engine.scanner as scanner_mod
    return Path(scanner_mod.__file__)


def _scanner_module_source() -> str:
    """scanner.py source text."""
    return _scanner_module_path().read_text(encoding="utf-8")


@pytest.mark.xfail(
    strict=False,
    reason=(
        "사이클 101 Q68=A — `_fetch_fluctuation` 함수 자체 영구 폐기 "
        "(fluctuation API → market_cap FHPST01740000 전환). "
        "FID_RANK_SORT_CLS_CODE 는 fluctuation 파라미터로 market_cap API 에서 불필요. "
        "사이클 98 시점 AST 가드 의도 영속 보존 (사이클 66 K-2 패턴 답습)."
    ),
)
def test_g_ast1_rank_sort_cls_code_one_digit_required_and_multi_digit_forbidden():
    """G-AST1: scanner.py source 영역 `FID_RANK_SORT_CLS_CODE` 1자리 영속 + 다자리 영구 차단.

    KIS chk_fluctuation.py main 호출 영역 정본:
        fid_rank_sort_cls_code="0"      # ← 1자리 영역

    검증 영역 (3 단계):
    1. `"FID_RANK_SORT_CLS_CODE": "0"` 영역 ≥1건 영속 (1자리, KIS 정본 정합)
    2. `"FID_RANK_SORT_CLS_CODE": "0000"` (4자리) 영구 차단 (사이클 97 영역 결함)
    3. `"FID_RANK_SORT_CLS_CODE": "00"` / `"000"` / `"00000"` 다자리 영구 차단

    AST + raw text grep 패턴 (사이클 81 / 97 답습):
    - regex pattern 영역 = "FID_RANK_SORT_CLS_CODE" 영역 quoted value 매칭
    - re.findall 영역 모든 value 수집
    - 1자리 "0" 영역 ≥1건 + 다자리 영역 0건 검증

    Red 상태 (사이클 98): production 영역 `"0000"` (4자리) 영속 → FAIL.

    Green (backend-dev): `src/engine/scanner.py:1529` 1줄 시정
        `"FID_RANK_SORT_CLS_CODE": "0000"` → `"FID_RANK_SORT_CLS_CODE": "0"`
        → 1자리 ≥1건 + 다자리 0건 PASS.

    영속 의무:
    - 사이클 81 silent 결함 영구 차단 패턴 답습
    - KIS 정본 영역 영구 정합
    - 미래 회귀 silent 결함 영구 차단 (4자리 영역 재도입 시 즉시 FAIL)
    """
    source = _scanner_module_source()

    # value 영역 전수 추출 (regex 영역 = key:value 패턴)
    pattern = r'"FID_RANK_SORT_CLS_CODE"\s*:\s*"([^"]*)"'
    matches = re.findall(pattern, source)

    assert matches, (
        f"\n사이클 98 G-AST1 위반 — scanner.py source 영역 `FID_RANK_SORT_CLS_CODE` 영역 부재:\n"
        f"  패턴: {pattern!r}\n"
        f"  KIS 정본: chk_fluctuation.py main 영역 `fid_rank_sort_cls_code=\"0\"`\n"
        f"  사이클 97 영역 = `_fetch_fluctuation` (FHPST01700000) 영속 의무"
    )

    one_digit = [v for v in matches if v == "0"]
    multi_digit = [v for v in matches if v != "0"]

    # (1) 1자리 "0" 영역 ≥1건 영속 (KIS 정본 정합)
    assert one_digit, (
        f"\n사이클 98 G-AST1 위반 — `FID_RANK_SORT_CLS_CODE` 1자리 \"0\" 영역 영속 결함:\n"
        f"  발견 value 영역: {matches}\n"
        f"  기대: ['0', ...] (1자리 ≥1건, KIS chk_fluctuation.py main 정본 영속)\n"
        f"  KIS 정본 인용: chk_fluctuation.py main 호출 영역 `fid_rank_sort_cls_code=\"0\"`\n"
        f"  시정 영역: src/engine/scanner.py:1529 → `\"FID_RANK_SORT_CLS_CODE\": \"0\"`"
    )

    # (2) 다자리 ("0000" / "00" / "000" / 등) 영구 차단
    assert not multi_digit, (
        f"\n사이클 98 G-AST1 위반 — `FID_RANK_SORT_CLS_CODE` 다자리 영역 영속 영구 차단:\n"
        f"  잔존 다자리 영역: {multi_digit}\n"
        f"  영구 차단 영역: 모든 다자리 value (사이클 97 영역 `\"0000\"` 거짓 안내 인용 결함)\n"
        f"  운영 실증: OPSQ2002 INVALID INPUT_FILED_SIZE [FID_RANK_SORT_CLS_CODE] [4]\n"
        f"  KIS 정본: chk_fluctuation.py main 영역 `fid_rank_sort_cls_code=\"0\"` (1자리만 허용)\n"
        f"  시정 영역: src/engine/scanner.py:1529 → `\"FID_RANK_SORT_CLS_CODE\": \"0\"`\n"
        f"  silent 결함 영구 차단 20 회 누적 (사이클 60~81 + 98)"
    )
