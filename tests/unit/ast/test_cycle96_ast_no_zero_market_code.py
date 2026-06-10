"""사이클 96 H-5 — AST 영구 가드: `"0000"` 시장코드 영역 영구 차단 (HIGH).

명세 (`_workspace/red/cycle96_resurrect_industry_code_with_pagination.md`):

- 사이클 94 `"0000"` 단일화 silent 결함 (KIS 응답 30 한도 + 페이징 미지원) 미래 회귀 영구 차단
- 사이클 89 영역 복원 = `"0001"` (KOSPI) / `"0002"` (KOSDAQ) 영속 (운영 실측 정합)
- AST 정적 가드 = `_MARKET_INPUT_ISCD` dict literal value 영역

검증 패턴 (`_MARKET_INPUT_ISCD` dict literal 정적 grep + AST 분석):
- `_MARKET_INPUT_ISCD` value 영역에 `"0000"` 부재 (사이클 94 영역 회귀 영구 차단)
- `_MARKET_INPUT_ISCD` value 영역에 `"0001"` 영속 (사이클 96 영역 복원)
- `_MARKET_INPUT_ISCD` value 영역에 `"0002"` 영속 (사이클 96 영역 복원)

Red 상태 (사이클 96): production 코드 `"0000"` 영속 → FAIL.

영속 의무:
- 사이클 81 `bfdy_clpr` AST 답습 (silent 결함 영구 차단 패턴)
- 사이클 88 G-REJECT 답습 (외부 LLM 영구 차단 정적 검증)
- 사이클 91 페이징 AST 답습 (운영 영속 의무)
- 사이클 94 H-6 영역 의미 전환 (xfail) — 사이클 66 K-2 패턴 영속
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit


def _scanner_module_path() -> Path:
    """scanner.py 모듈 절대 경로."""
    import src.engine.scanner as scanner_mod
    return Path(scanner_mod.__file__)


def _extract_market_input_iscd_values() -> list[str]:
    """`_MARKET_INPUT_ISCD` dict literal 의 모든 value 추출 (AST 정적)."""
    source = _scanner_module_path().read_text(encoding="utf-8")
    tree = ast.parse(source)

    values: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.AnnAssign | ast.Assign):
            continue
        targets = (
            [node.target] if isinstance(node, ast.AnnAssign) else node.targets
        )
        for target in targets:
            if not isinstance(target, ast.Name) or target.id != "_MARKET_INPUT_ISCD":
                continue
            value_node = node.value
            if not isinstance(value_node, ast.Dict):
                continue
            for v in value_node.values:
                if isinstance(v, ast.Constant) and isinstance(v.value, str):
                    values.append(v.value)
    return values


def test_h5_no_zero_market_code_0000():
    """H-5.a: `_MARKET_INPUT_ISCD` value 영역에 `"0000"` 영속 부재.

    KIS 운영 실측 silent 결함 ("0000" 30 한도 + 페이징 미지원) 회귀 영구 차단.
    """
    values = _extract_market_input_iscd_values()

    assert values, (
        "\n사이클 96 H-5.a 위반 — `_MARKET_INPUT_ISCD` dict literal 부재:\n"
        "  src/engine/scanner.py 에 `_MARKET_INPUT_ISCD: dict[str, str] = {...}` 영속 의무"
    )

    assert "0000" not in values, (
        f"\n사이클 96 H-5.a 위반 — '0000' 시장코드 영속 결함:\n"
        f"  발견 value: {values}\n"
        f"  결함 인과:\n"
        f"    - '0000' = KIS docstring 영역 (운영 실측 30 한도 + 페이징 미지원)\n"
        f"    - 사이클 94 단일화 silent 결함 영역\n"
        f"    - 사이클 96 영역 복원 = '0001'/'0002' 영속\n"
        f"  미래 회귀 영구 차단 의무"
    )


def test_h5_industry_code_0001_present():
    """H-5.b: `_MARKET_INPUT_ISCD` value 영역에 `"0001"` 영속.

    KIS KOSPI 업종코드 (운영 실측 페이징 정상) 영구 가드.
    """
    values = _extract_market_input_iscd_values()

    assert values, (
        "\n사이클 96 H-5.b 위반 — `_MARKET_INPUT_ISCD` dict literal 부재"
    )

    assert "0001" in values, (
        f"\n사이클 96 H-5.b 위반 — '0001' KOSPI 업종코드 부재:\n"
        f"  발견 value: {values}\n"
        f"  사이클 89 영역 복원 의무:\n"
        f"    - '0001' = KIS KOSPI 업종 (운영 실측 17 페이지 페이징 정상)\n"
        f"    - 사이클 91 페이징 영역 결합"
    )


def test_h5_industry_code_0002_present():
    """H-5.c: `_MARKET_INPUT_ISCD` value 영역에 `"0002"` 영속.

    KIS KOSDAQ 업종코드 영구 가드.
    """
    values = _extract_market_input_iscd_values()

    assert values, (
        "\n사이클 96 H-5.c 위반 — `_MARKET_INPUT_ISCD` dict literal 부재"
    )

    assert "0002" in values, (
        f"\n사이클 96 H-5.c 위반 — '0002' KOSDAQ 업종코드 부재:\n"
        f"  발견 value: {values}\n"
        f"  사이클 89 영역 복원 의무"
    )
