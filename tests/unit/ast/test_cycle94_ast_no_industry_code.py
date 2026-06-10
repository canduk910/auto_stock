"""사이클 94 H-6 — AST 영구 가드: `_MARKET_INPUT_ISCD` 업종코드 사이클 94 이후 영속 부재 (HIGH).

명세 (`_workspace/red/cycle94_fid_input_iscd_fix.md`):

- 사이클 89/91 silent 결함 (`"0001"` / `"0002"` 업종코드) 미래 회귀 영구 차단
- KIS 정본 = `"0000"` 전체 영역만 영속

검증 패턴 (`_MARKET_INPUT_ISCD` dict literal 정적 grep + AST 분석):
- `_MARKET_INPUT_ISCD` value 영역에 `"0001"` 부재
- `_MARKET_INPUT_ISCD` value 영역에 `"0002"` 부재
- `_MARKET_INPUT_ISCD` value 영역에 `"0000"` 영속 (단일화 가드)

Red 상태 (사이클 94): production 코드 `"0001"` / `"0002"` 영속 → FAIL.

영속 의무:
- 사이클 81 `bfdy_clpr` AST 답습 (silent 결함 영구 차단 패턴)
- 사이클 88 G-REJECT 답습 (외부 LLM 영구 차단 정적 검증)
- 사이클 91 페이징 AST 답습 (운영 영속 의무)
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
    """`_MARKET_INPUT_ISCD` dict literal 의 모든 value 추출 (AST 정적).

    AST 분석 - assign target name == "_MARKET_INPUT_ISCD" + value 가 Dict literal 인 경우.
    """
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


@pytest.mark.xfail(
    strict=False,
    reason=(
        "사이클 96 Q50=D — 사이클 89 영역 복원 (`'0001'` KOSPI 영속). "
        "사이클 94 H-6.a 영역 (업종코드 0001 부재 AST 가드) 폐기 계약 = 사이클 96 영역 복원 후 '0001' 영속 정상. "
        "사이클 66 K-2 의미 전환 패턴."
    ),
)
def test_h6_no_industry_code_0001():
    """H-6.a: `_MARKET_INPUT_ISCD` value 영역에 `"0001"` 영속 부재.

    KIS 업종코드 (단일 페이지 30건 한도) 회귀 영구 차단.
    """
    values = _extract_market_input_iscd_values()

    assert values, (
        "\n사이클 94 H-6.a 위반 — `_MARKET_INPUT_ISCD` dict literal 부재:\n"
        "  src/engine/scanner.py 에 `_MARKET_INPUT_ISCD: dict[str, str] = {...}` 영속 의무"
    )

    assert "0001" not in values, (
        f"\n사이클 94 H-6.a 위반 — '0001' 업종코드 영속 결함:\n"
        f"  발견 value: {values}\n"
        f"  결함 인과:\n"
        f"    - '0001' = KIS KOSPI 업종코드 (페이징 미지원, 30건 한도)\n"
        f"    - 사이클 89/91 silent 결함 영역\n"
        f"    - 사이클 94 시정 = '0000' 전체 영역 단일화\n"
        f"  미래 회귀 영구 차단 의무"
    )


@pytest.mark.xfail(
    strict=False,
    reason=(
        "사이클 96 Q50=D — 사이클 89 영역 복원 (`'0002'` KOSDAQ 영속). "
        "사이클 94 H-6.b 영역 (업종코드 0002 부재 AST 가드) 폐기 계약 = 사이클 96 영역 복원 후 '0002' 영속 정상. "
        "사이클 66 K-2 의미 전환 패턴."
    ),
)
def test_h6_no_industry_code_0002():
    """H-6.b: `_MARKET_INPUT_ISCD` value 영역에 `"0002"` 영속 부재.

    KIS KOSDAQ 업종코드 회귀 영구 차단.
    """
    values = _extract_market_input_iscd_values()

    assert values, (
        "\n사이클 94 H-6.b 위반 — `_MARKET_INPUT_ISCD` dict literal 부재"
    )

    assert "0002" not in values, (
        f"\n사이클 94 H-6.b 위반 — '0002' 업종코드 영속 결함:\n"
        f"  발견 value: {values}\n"
        f"  결함 인과:\n"
        f"    - '0002' = KIS KOSDAQ 업종코드 (페이징 미지원, 30건 한도)\n"
        f"    - 사이클 89/91 silent 결함 영역\n"
        f"    - 사이클 94 시정 = '0000' 전체 영역 단일화"
    )


@pytest.mark.xfail(
    strict=False,
    reason=(
        "사이클 96 Q50=D — 사이클 89 영역 복원 ('0000' 부재 영속). "
        "사이클 94 H-6.c 영역 ('0000' 영속 AST 가드) 폐기 계약 = 사이클 96 영역 복원 후 '0000' 부재 영속 정상. "
        "KIS 운영 실측 '0000' = 단일 페이지 30 한도 + 페이징 미지원 silent 결함. "
        "사이클 66 K-2 의미 전환 패턴."
    ),
)
def test_h6_market_input_iscd_contains_0000():
    """H-6.c: `_MARKET_INPUT_ISCD` value 영역에 `"0000"` 영속.

    KIS 정본 = 전체 영역 (페이징 17+ 페이지 정상) 영구 가드.
    """
    values = _extract_market_input_iscd_values()

    assert values, (
        "\n사이클 94 H-6.c 위반 — `_MARKET_INPUT_ISCD` dict literal 부재"
    )

    assert "0000" in values, (
        f"\n사이클 94 H-6.c 위반 — '0000' KIS 정본 코드 부재:\n"
        f"  발견 value: {values}\n"
        f"  KIS MCP 정본 영속:\n"
        f"    - '0000' = 전체 (페이징 17+ 페이지 정상 = 500 ticker 영속)\n"
        f"    - 사이클 94 시정 의무"
    )
