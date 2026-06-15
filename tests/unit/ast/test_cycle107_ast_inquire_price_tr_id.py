"""사이클 107 AST 영구 가드 — inquire_stock_basics 내 FHKST01010100 사용 영속.

HIGH-4:
- condition.py 에 FHKST01010100 TR_ID 가 소스 코드에 존재해야 한다.
- condition.py 에 inquire-price URL 이 소스 코드에 존재해야 한다.

사이클 98 G-DOC1 패턴 답습:
- KIS chk_inquire_price.py main 호출 영역 = 실측 정본 (운영 정합)
- TR_ID FHKST01010100 + URL inquire-price 동행 의무
- 미래 TR_ID/URL 변경 시 이 테스트가 즉시 실패 → silent 결함 영구 차단

경계 조건:
- STOCK_PRICE_URL 상수 자체가 이미 inquire-price 를 포함하므로
  kis_get_quote 호출 시 해당 상수를 참조하는 것으로 충분히 커버
"""

from __future__ import annotations

import ast
import pathlib

import pytest

from tests.unit.ast._ast_helpers import read_module_source

pytestmark = pytest.mark.unit

_CONDITION_PY = (
    pathlib.Path(__file__).parent.parent.parent.parent
    / "src"
    / "api"
    / "condition.py"
)


def _load_source() -> str:
    return read_module_source(_CONDITION_PY)


def _load_tree() -> ast.Module:
    return ast.parse(_load_source())


# ---------------------------------------------------------------------------
# HIGH-4-A: FHKST01010100 TR_ID 가 condition.py 소스에 존재해야 한다
# ---------------------------------------------------------------------------


def test_high4_fhkst01010100_present_in_condition() -> None:
    """HIGH-4: condition.py 에 'FHKST01010100' 문자열이 존재해야 한다.

    이 TR_ID 가 삭제되면 사이클 107 시정 전체가 무효화된다.
    """
    source = _load_source()
    assert "FHKST01010100" in source, (
        "condition.py 에 FHKST01010100 TR_ID 가 없습니다. "
        "사이클 107 inquire_stock_basics merge 가 제거되었을 수 있습니다."
    )


# ---------------------------------------------------------------------------
# HIGH-4-B: inquire-price URL 이 condition.py 소스에 존재해야 한다
# ---------------------------------------------------------------------------


def test_high4_inquire_price_url_present_in_condition() -> None:
    """HIGH-4: condition.py 에 'inquire-price' URL 경로가 존재해야 한다.

    STOCK_PRICE_URL 상수 = '/uapi/domestic-stock/v1/quotations/inquire-price'.
    사이클 32 영속 + base.py 화이트리스트 영속.
    """
    source = _load_source()
    assert "inquire-price" in source, (
        "condition.py 에 inquire-price URL 이 없습니다. "
        "STOCK_PRICE_URL 상수 또는 kis_get_quote 호출 경로가 변경되었을 수 있습니다."
    )


# ---------------------------------------------------------------------------
# HIGH-4-C: inquire_stock_basics 함수 내에 FHKST01010100 가 사용되어야 한다
# ---------------------------------------------------------------------------


def test_high4_fhkst_used_inside_inquire_stock_basics() -> None:
    """HIGH-4: inquire_stock_basics 함수 본체 ±30줄 내에 FHKST01010100 가 있어야 한다.

    사이클 98 G-DOC1 패턴 (±10줄 윈도우) 답습 + 함수 규모 반영하여 ±30줄 윈도우.
    미래에 FHKST01010100 를 함수 밖으로 이동/제거하면 즉시 검출.
    """
    source = _load_source()
    lines = source.splitlines()

    # inquire_stock_basics 함수 시작 줄 찾기
    func_start = None
    for i, line in enumerate(lines):
        if "async def inquire_stock_basics" in line:
            func_start = i
            break

    assert func_start is not None, "inquire_stock_basics 함수를 찾을 수 없습니다."

    # 함수 시작 후 60줄 내에 FHKST01010100 가 있어야 함
    window = "\n".join(lines[func_start : func_start + 60])
    assert "FHKST01010100" in window, (
        f"inquire_stock_basics 함수 내 (L{func_start+1} 기준 60줄 윈도우) "
        "에 FHKST01010100 가 없습니다. "
        "사이클 107 merge 호출이 제거되었을 수 있습니다."
    )


# ---------------------------------------------------------------------------
# HIGH-4-D: merged_raw 에 FHKST 3 키 merge 로직이 소스에 존재해야 한다
# ---------------------------------------------------------------------------


def test_high4_merge_keys_present_in_source() -> None:
    """HIGH-4: condition.py 에 acml_tr_pbmn / lstn_stcn / acml_vol merge 로직 영속.

    이 3 키가 소스에서 삭제되면 stock_master 시세 보강 전체가 무효화된다.
    """
    source = _load_source()
    for key in ("acml_tr_pbmn", "lstn_stcn", "acml_vol"):
        assert key in source, (
            f"condition.py 에 '{key}' 가 없습니다. "
            "사이클 107 raw merge 로직이 제거되었을 수 있습니다."
        )
