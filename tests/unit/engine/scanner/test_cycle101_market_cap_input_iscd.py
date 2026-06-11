"""사이클 101 G-MC2 — `_MARKET_CAP_INPUT_ISCD` AST + KIS 정본 정합 (HIGH).

명세 (`_workspace/red/cycle101_market_cap_full_universe_load.md`):

**KIS 정본 (chk_market_cap.py main 호출 영역) 영속**:
- `fid_input_iscd` = "0000" 전체 / "0001" 거래소 (KOSPI) / "1001" 코스닥 / "2001" 코스피200
- 사이클 101 Q67=B + Q68=A: KOSPI ("0001") + KOSDAQ ("1001") 분리 호출

검증 매트릭스:
- G-MC2-A: `_MARKET_CAP_INPUT_ISCD` 모듈 전역 dict 영속 (AST 정적)
- G-MC2-B: {"kospi": "0001", "kosdaq": "1001"} 매핑 정확 영속 (KIS 정본 정합)

Red 상태: 신규 dict 부재 → AttributeError.
Green (backend-dev): scanner.py 모듈 전역에 dict 정의 영속.

영속 의무:
- 사이클 95 unknown=0 영속 (KOSPI/KOSDAQ 명시 분리 = unknown 분류 불필요)
- 사이클 98 G-DOC1 영속 (chk_market_cap.py 정본 인용 의무)
- 매매 hot path 영향 0 (scanner 단계 영역)
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit


def _scanner_source() -> str:
    """scanner.py source text."""
    import src.engine.scanner as scanner_mod
    return Path(scanner_mod.__file__).read_text(encoding="utf-8")


def test_g_mc2_a_market_cap_input_iscd_exists() -> None:
    """G-MC2-A: `_MARKET_CAP_INPUT_ISCD` 모듈 전역 dict 영속 (HIGH).

    Red 상태: dict 부재 → AttributeError.
    Green (backend-dev): scanner.py 모듈 전역 정의 의무.
    """
    from src.engine import scanner

    assert hasattr(scanner, "_MARKET_CAP_INPUT_ISCD"), (
        "\n사이클 101 G-MC2-A Red 상태 — `_MARKET_CAP_INPUT_ISCD` 부재.\n"
        "  Green (backend-dev): scanner.py 모듈 전역 dict 정의 의무.\n"
        "  KIS 정본: fid_input_iscd 0001=KOSPI / 1001=KOSDAQ"
    )


def test_g_mc2_b_market_cap_input_iscd_mapping_correct() -> None:
    """G-MC2-B: KIS 정본 매핑 정확 영속 (HIGH).

    검증 매트릭스 (KIS chk_market_cap.py main 호출 영역 정본 정합):
    - "kospi" → "0001" (거래소 / KOSPI)
    - "kosdaq" → "1001" (코스닥)

    Red 상태: 잘못된 매핑 (예: "0002" KOSDAQ 코스피업종) → 운영 데이터 오염.
    Green (backend-dev): 정본 매핑 영속.
    """
    from src.engine import scanner

    if not hasattr(scanner, "_MARKET_CAP_INPUT_ISCD"):
        pytest.fail(
            "사이클 101 G-MC2-B Red — `_MARKET_CAP_INPUT_ISCD` 부재 (G-MC2-A 영속).\n"
            "  Green: scanner.py 모듈 전역 dict 정의 의무"
        )

    mapping = scanner._MARKET_CAP_INPUT_ISCD

    assert mapping.get("kospi") == "0001", (
        f"\n사이클 101 G-MC2-B 위반 — KOSPI input_iscd 잘못:\n"
        f"  기대: 'kospi' → '0001' (KIS 정본 거래소 코드)\n"
        f"  실제: 'kospi' → {mapping.get('kospi')!r}\n"
        f"  Red 결함 가설: KIS 정본 chk_market_cap.py 미인용\n"
        f"  Green (backend-dev): chk_market_cap.py main 영역 정본 인용 의무"
    )

    assert mapping.get("kosdaq") == "1001", (
        f"\n사이클 101 G-MC2-B 위반 — KOSDAQ input_iscd 잘못:\n"
        f"  기대: 'kosdaq' → '1001' (KIS 정본 코스닥 코드)\n"
        f"  실제: 'kosdaq' → {mapping.get('kosdaq')!r}\n"
        f"  Red 결함 가설: '0002' KOSDAQ 코스피업종 코드 혼동 (fluctuation 영역과 차별)\n"
        f"  Green (backend-dev): market_cap 정본 = '1001' (KOSDAQ)"
    )


def test_g_mc2_c_market_cap_input_iscd_ast_literal() -> None:
    """G-MC2-C: AST 정적 가드 — dict literal 영속 (사이클 81 silent 결함 영구 차단 패턴).

    Red 상태: dict literal 부재 또는 매핑 silent 변경.
    Green (backend-dev): scanner.py AST 영역에 `_MARKET_CAP_INPUT_ISCD = {...}` literal 영속.
    """
    source = _scanner_source()
    tree = ast.parse(source)

    found_dict = None
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if (
                    isinstance(target, ast.Name)
                    and target.id == "_MARKET_CAP_INPUT_ISCD"
                ):
                    found_dict = node.value
                    break
        elif isinstance(node, ast.AnnAssign):
            if (
                isinstance(node.target, ast.Name)
                and node.target.id == "_MARKET_CAP_INPUT_ISCD"
            ):
                found_dict = node.value
                break

    assert found_dict is not None, (
        "\n사이클 101 G-MC2-C Red 상태 — `_MARKET_CAP_INPUT_ISCD` AST 정적 미발견.\n"
        "  Green (backend-dev): scanner.py 모듈 전역 dict literal 정의 의무.\n"
        "  AST 영구 가드 = 미래 silent 삭제 영역 영구 차단 (사이클 81 패턴 답습)"
    )

    assert isinstance(found_dict, ast.Dict), (
        f"\n사이클 101 G-MC2-C 위반 — `_MARKET_CAP_INPUT_ISCD` dict literal 아님:\n"
        f"  실제 AST 타입: {type(found_dict).__name__}\n"
        f"  Green: dict literal {{'kospi': '0001', 'kosdaq': '1001'}} 영속"
    )
