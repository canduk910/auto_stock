"""cycle396 — 매도 장부 가중평균 헬퍼의 구조 가드.

- `_vwap_2dp`(소수 둘째 자리 반올림, cycle392)는 없고 `_vwap_floor` 가 있다
- `_handle_sell_fill` 의 장부 가격 `book_price` 는 `_vwap_floor(...)` 로만 만든다
- 헬퍼 본문에 반올림 흔적(`ROUND_HALF_UP`·`quantize`·`round(`·`float(`)이 없다 — 소수가
  장부로 새는 길을 막는다. 동기 순수성은 cycle392 A7 이 본다
"""
from __future__ import annotations

import ast
from pathlib import Path

_OE = Path(__file__).resolve().parents[3] / "src" / "engine" / "order_engine.py"


def _tree():
    return ast.parse(_OE.read_text(encoding="utf-8"))


def _module_fn(tree, name):
    for n in tree.body:
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name:
            return n
    return None


def test_g396_1_floor_helper_replaces_two_decimal_helper():
    tree = _tree()
    assert _module_fn(tree, "_vwap_2dp") is None, "`_vwap_2dp` 가 남아 있다 — cycle396 이 `_vwap_floor` 로 바꿨다"
    fn = _module_fn(tree, "_vwap_floor")
    assert isinstance(fn, ast.FunctionDef), "`_vwap_floor` 동기 함수가 없다"


def test_g396_2_helper_has_no_rounding_or_float():
    fn = _module_fn(_tree(), "_vwap_floor")
    assert fn is not None, "`_vwap_floor` 가 없다"
    bad = []
    for n in ast.walk(fn):
        if isinstance(n, ast.Name) and n.id in {"ROUND_HALF_UP", "ROUND_HALF_EVEN", "ROUND_CEILING", "ROUND_UP"}:
            bad.append(f"L{n.lineno} {n.id}")
        elif isinstance(n, ast.alias) and n.name in {"ROUND_HALF_UP", "ROUND_HALF_EVEN", "ROUND_CEILING", "ROUND_UP"}:
            bad.append(f"import {n.name}")
        elif isinstance(n, ast.Attribute) and n.attr == "quantize":
            bad.append(f"L{n.lineno} .quantize")
        elif isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in {"round", "float"}:
            bad.append(f"L{n.lineno} {n.func.id}(")
    assert bad == [], f"`_vwap_floor` 안의 반올림/실수 흔적: {bad}"


def test_g396_3_book_price_is_built_by_floor_helper():
    tree = _tree()
    hits = []
    for n in ast.walk(tree):
        if isinstance(n, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "book_price" for t in n.targets
        ):
            hits.append(n)
    assert len(hits) == 1, f"`book_price =` {len(hits)}곳 (기대 1)"
    v = hits[0].value
    assert isinstance(v, ast.Call) and isinstance(v.func, ast.Name) and v.func.id == "_vwap_floor", (
        f"`book_price = {ast.unparse(v)}` — `_vwap_floor(...)` 여야 한다"
    )
