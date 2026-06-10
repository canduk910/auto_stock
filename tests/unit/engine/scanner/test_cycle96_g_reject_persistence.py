"""사이클 96 L-1 — 사이클 88 G-REJECT-1/2/3 영속 (LOW).

명세 (`_workspace/red/cycle96_resurrect_industry_code_with_pagination.md`):

- 사이클 88 G-REJECT (외부 LLM 영구 차단 AST 가드 3) 영속 + 답습
- 사이클 96 영역 복원 영역 무영향 확인

기대 동작 (Green, backend-dev 인계):
- 사이클 88 G-REJECT-1/2/3 패턴이 사이클 96 영역에서도 영속 (영향 0)
- 외부 LLM 거부 응답 영구 차단 패턴 답습

영속 의무:
- 사이클 88 G-REJECT 패턴 답습
- 사이클 96 영역 복원 영역 무영향
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = [
    pytest.mark.unit,
    pytest.mark.xfail(
        strict=False,
        reason=(
            "사이클 97 Q53=A — `_fetch_volume_rank` 영역 전수 폐기. "
            "사이클 96 G-REJECT 영역 = 사이클 97 L-1 가드로 영역 흡수 + 확장. "
            "사이클 66 K-2 의미 전환 패턴 영속."
        ),
    ),
]


def _scanner_module_path() -> Path:
    import src.engine.scanner as scanner_mod
    return Path(scanner_mod.__file__)


def test_l1_g_reject_pattern_no_external_llm_call_in_scanner():
    """L-1.a: scanner.py 본문에 외부 LLM 호출 패턴 부재 영속 (사이클 88 답습).

    검증 매트릭스:
    - scanner.py source 에 `openai.` / `anthropic.` / `claude_api` 호출 패턴 부재
    - 사이클 96 영역 복원 시 무영향 확인

    영속 의무: 사이클 88 외부 LLM 거부 응답 영구 차단 패턴 답습.
    """
    source = _scanner_module_path().read_text(encoding="utf-8")

    forbidden_patterns = ["openai.", "anthropic.", "from openai", "from anthropic"]
    found = [p for p in forbidden_patterns if p in source]

    assert not found, (
        f"\n사이클 96 L-1.a 위반 — scanner.py 본문에 외부 LLM 호출 영역 결함:\n"
        f"  금지 패턴 발견: {found}\n"
        f"  사이클 88 G-REJECT 영속 의무"
    )


def test_l1_g_reject_pattern_market_input_iscd_dict_literal_only():
    """L-1.b: `_MARKET_INPUT_ISCD` 가 dict literal 직접 정의 (외부 함수 호출 없음).

    검증 매트릭스:
    - AST 분석 = `_MARKET_INPUT_ISCD` value = ast.Dict literal 직접
    - 외부 함수 호출 (`_load_*` / `fetch_*`) 없음

    영속 의무: 사이클 88 G-REJECT 패턴 답습 (정적 값 영속).
    """
    source = _scanner_module_path().read_text(encoding="utf-8")
    tree = ast.parse(source)

    found_literal = False
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
            if isinstance(value_node, ast.Dict):
                found_literal = True
                break

    assert found_literal, (
        "\n사이클 96 L-1.b 위반 — `_MARKET_INPUT_ISCD` dict literal 직접 정의 부재:\n"
        "  사이클 88 정적 값 영속 의무 (외부 호출 없음)"
    )
