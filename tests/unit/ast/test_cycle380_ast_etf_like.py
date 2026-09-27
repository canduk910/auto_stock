"""cycle380 Red — ETF 판정 단일 출처 구조 가드 (AST · 주석/docstring 제외 · 미추적 파일 포함).

명세 = `_workspace/red/cycle380_etf_group_code.md` §5.

| # | 계약 |
|---|---|
| G1 | `ETF_KEYWORDS` 를 순회(comprehension·for)하는 코드는 `src/engine/etf_like.py`(폴백 본체)와 `src/db/stock_master.py`(SQL 이름 폴백 빌더) 두 곳뿐이다 — 이름만 보는 판정이 다른 자리에서 되살아나지 않게 |
| G2 | `src/engine/strategies/*.py` 는 `ETF_KEYWORDS` 를 참조조차 하지 않는다(import 포함) — 전략은 헬퍼만 쓴다 |
| G3 | 6 전략 `_scan_universe` 가 `is_etf_like(...)` 를 호출한다 |
| G4 | `src/engine/strategies/*.py` 의 **모든** `list_by_filter(...)` 호출이 `exclude_etf_like=True`(상수)를 넘긴다 — 새 전략도 LIMIT 전 제외를 잊지 않게. ETF 전용 전략이 생기면 그 파일을 여기 허용 목록에 이유와 함께 올린다 |
| G5 | momentum 스캔 `scanner.scan_stocks` 가 `is_etf_like(...)` 를 호출한다(원천 행에 코드가 없어 결과는 이름 폴백과 같다 — 판정 자리만 하나로 모은다) |
| G6 | `stock_master.py` 는 `src.engine.etf_like` 에서 가져다 쓰고, 그룹 코드("EF"/"EN"/"FE")·키워드 문자열을 **다시 적지 않는다**(두 출처가 갈라지는 것을 막는다) |
| G7 | `order_engine._observe_after_exit_etp`(8영역, 이번 사이클 무접촉)의 코드 집합이 `ETF_GROUP_CODES` 와 같다 — 읽기 전용 표류 감시 |

소스 스캔은 `Path.rglob` — `git ls-files` 는 Green 이 새로 만든 미추적 파일을 못 본다(가드 설계 금기).

## HEAD 기준

G1(7곳 순회) · G2(6파일 import) · G3 · G4 · G5 · G6(leaf 부재) · G7(leaf 부재) 전부 RED.
"""
from __future__ import annotations

import ast
from functools import lru_cache
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parents[3]
_SRC = _ROOT / "src"
_LEAF_REL = "src/engine/etf_like.py"
_SM_REL = "src/db/stock_master.py"
_SCANNER_REL = "src/engine/scanner.py"
_OE_REL = "src/engine/order_engine.py"
_STRAT_DIR = _SRC / "engine" / "strategies"

_ITERATION_ALLOWED = {_LEAF_REL, _SM_REL}
# ETF 전용 전략 등 SQL 제외를 끄는 것이 맞는 파일만 이유와 함께 올린다. 지금은 없다.
_LIST_BY_FILTER_EXEMPT: dict[str, str] = {}

_SIX = {
    "volatility_breakout.py": "VolatilityBreakoutStrategy",
    "long_tail_volatility.py": "LongTailVolatilityStrategy",
    "donchian_swing.py": "DonchianSwingStrategy",
    "bull_flag_breakout.py": "BullFlagBreakoutStrategy",
    "vcp_breakout.py": "VcpBreakoutStrategy",
    "kojiro.py": "KojiroStrategy",
}


@lru_cache(maxsize=None)
def _tree(rel: str) -> ast.Module:
    return ast.parse((_ROOT / rel).read_text(encoding="utf-8"))


def _rel(p: Path) -> str:
    return p.relative_to(_ROOT).as_posix()


def _is_etf_keywords(node: ast.AST) -> bool:
    return (isinstance(node, ast.Name) and node.id == "ETF_KEYWORDS") or (
        isinstance(node, ast.Attribute) and node.attr == "ETF_KEYWORDS"
    )


def _calls_named(node: ast.AST, name: str) -> list[ast.Call]:
    out = []
    for n in ast.walk(node):
        if isinstance(n, ast.Call):
            f = n.func
            if (isinstance(f, ast.Name) and f.id == name) or (
                isinstance(f, ast.Attribute) and f.attr == name
            ):
                out.append(n)
    return out


def _method(tree: ast.Module, cls: str, name: str):
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == cls:
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name == name:
                    return item
    return None


def _function(tree: ast.Module, name: str):
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    return None


# ---------------------------------------------------------------------------
def test_g1_keyword_iteration_only_in_leaf_and_sql_builder():
    offenders: list[str] = []
    for path in sorted(_SRC.rglob("*.py")):
        rel = _rel(path)
        if rel in _ITERATION_ALLOWED:
            continue
        tree = _tree(rel)
        for node in ast.walk(tree):
            if isinstance(node, ast.comprehension) and _is_etf_keywords(node.iter):
                offenders.append(f"{rel}:{node.iter.lineno}")
            elif isinstance(node, (ast.For, ast.AsyncFor)) and _is_etf_keywords(node.iter):
                offenders.append(f"{rel}:{node.lineno}")
    assert offenders == [], (
        "이름 키워드만으로 ETF 를 판정하는 자리가 남았다 — is_etf_like 로 바꾼다:\n  "
        + "\n  ".join(offenders)
    )


def test_g2_strategies_do_not_reference_keywords():
    offenders: list[str] = []
    for path in sorted(_STRAT_DIR.glob("*.py")):
        rel = _rel(path)
        for node in ast.walk(_tree(rel)):
            if _is_etf_keywords(node):
                offenders.append(f"{rel}:{node.lineno}")
            elif isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    if alias.name == "ETF_KEYWORDS":
                        offenders.append(f"{rel}:{node.lineno} (import)")
    assert offenders == [], "전략은 ETF_KEYWORDS 대신 is_etf_like 만 쓴다:\n  " + "\n  ".join(offenders)


@pytest.mark.parametrize("fname,cls", sorted(_SIX.items()))
def test_g3_six_scan_universe_call_helper(fname, cls):
    rel = f"src/engine/strategies/{fname}"
    fn = _method(_tree(rel), cls, "_scan_universe")
    assert fn is not None, f"{cls}._scan_universe 가 없다"
    calls = _calls_named(fn, "is_etf_like")
    assert calls, f"{cls}._scan_universe 가 is_etf_like 를 부르지 않는다"
    for c in calls:
        assert len(c.args) + len(c.keywords) == 2, "is_etf_like(raw, name) 두 인자"


def test_g4_every_strategy_list_by_filter_excludes_etf_like():
    seen = 0
    offenders: list[str] = []
    for path in sorted(_STRAT_DIR.glob("*.py")):
        rel = _rel(path)
        if path.name in _LIST_BY_FILTER_EXEMPT:
            continue
        for call in _calls_named(_tree(rel), "list_by_filter"):
            seen += 1
            kw = {k.arg: k.value for k in call.keywords if k.arg}
            v = kw.get("exclude_etf_like")
            if not (isinstance(v, ast.Constant) and v.value is True):
                offenders.append(f"{rel}:{call.lineno}")
    assert seen >= 6, f"전략의 list_by_filter 호출이 {seen}개뿐 — 스캔이 비었다"
    assert offenders == [], (
        "list_by_filter(exclude_etf_like=True) 가 빠진 호출 — LIMIT 전에 걸러야 한다:\n  "
        + "\n  ".join(offenders)
    )


def test_g5_momentum_scan_stocks_calls_helper():
    fn = _function(_tree(_SCANNER_REL), "scan_stocks")
    assert fn is not None, "scanner.scan_stocks 가 없다"
    assert _calls_named(fn, "is_etf_like"), "scan_stocks 가 is_etf_like 를 부르지 않는다"


def test_g6_stock_master_single_source():
    tree = _tree(_SM_REL)
    imports_leaf = any(
        isinstance(n, ast.ImportFrom) and n.module == "src.engine.etf_like"
        for n in ast.walk(tree)
    ) or any(
        isinstance(n, ast.Import) and any(a.name == "src.engine.etf_like" for a in n.names)
        for n in ast.walk(tree)
    )
    assert imports_leaf, "stock_master.py 가 src.engine.etf_like 를 쓰지 않는다"

    from src.engine.etf_like import ETF_GROUP_CODES, ETF_KEYWORDS

    banned = set(ETF_GROUP_CODES) | set(ETF_KEYWORDS)
    doc_nodes = {
        id(n.body[0].value)
        for n in ast.walk(tree)
        if isinstance(n, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        and n.body and isinstance(n.body[0], ast.Expr)
        and isinstance(n.body[0].value, ast.Constant)
    }
    retyped = sorted(
        f"{n.lineno}:{n.value!r}"
        for n in ast.walk(tree)
        if isinstance(n, ast.Constant) and isinstance(n.value, str)
        and id(n) not in doc_nodes and n.value.strip() in banned
    )
    assert retyped == [], f"stock_master.py 가 코드·키워드를 다시 적었다: {retyped}"


def test_g7_order_engine_etp_codes_match_group_codes():
    from src.engine.etf_like import ETF_GROUP_CODES

    fn = _method(_tree(_OE_REL), "OrderEngine", "_observe_after_exit_etp")
    assert fn is not None
    sets = []
    for n in ast.walk(fn):
        if isinstance(n, ast.Compare) and any(isinstance(op, ast.In) for op in n.ops):
            for comp in n.comparators:
                if isinstance(comp, (ast.Tuple, ast.Set, ast.List)) and all(
                    isinstance(e, ast.Constant) and isinstance(e.value, str) for e in comp.elts
                ):
                    sets.append(frozenset(e.value for e in comp.elts))
    assert sets, "_observe_after_exit_etp 의 코드 집합을 찾지 못했다"
    assert all(s == ETF_GROUP_CODES for s in sets), (
        f"order_engine 관측 집합 {sets} 이 ETF_GROUP_CODES {set(ETF_GROUP_CODES)} 와 갈라졌다"
    )
