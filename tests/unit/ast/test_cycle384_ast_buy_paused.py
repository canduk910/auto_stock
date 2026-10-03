"""cycle384 Red — `buy_paused` 구조 봉인 (A01~A15) + 카탈로그·픽스처 (R06 · F01).

명세 정본 = `_workspace/red/cycle384_buy_paused_spec.md` §2 · §7 · §8 · §9.7

| # | 봉인 |
|---|---|
| A01 | J25 그대로 — 게이트 첫 문장 = `if self._status_buy_blocked(ticker): return True` |
| A02 | 두 번째 문장 = `if self._buy_paused_blocked(ticker): return True`(orelse 없음), 세 번째 = 기존 `Try` |
| A03 | 헬퍼 4개 = 동기 · `await`/`write_log`/`kis_*`/`fetch_*`/`create_task`/`pg.` 0 · 모듈 최상위 import 추가 0 |
| A04 | 문자열 `"buy_paused"`(정확히 그 값) = strategy_base 1 · 전략 명부 파일 각 1(`DEFAULT_PARAMS` 키) · param_catalog 1 · 그 밖 src 0 |
| A05 | `BUY_PAUSED_KEY` 참조 = 정의 + `_buy_paused_blocked` 안뿐 |
| A06 | `_buy_paused_blocked` 호출 = src 전체 1곳(게이트) · 게이트 호출 = 전략 명부 파일마다 `check_buy_signal` 안 1곳 · `_clear_entry_latches_on_pause` 호출 = 멈춤 헬퍼 1곳(상태 차단 경로 무변경) |
| A07 | 캐시 금지 — `self.<…paused…>` 대입은 `__init__` 의 `_buy_paused_logged` 하나 · `self.config.params` 사슬 존재 |
| A08 | 헬퍼에 `buy_disabled`·`enabled`·`weight`·`pending_buys`·`_bought_today`·`low_funds`·`calc_buy_quantity`·`total_investment` 0 |
| A09 | `_PAUSE_ENTRY_LATCH_ATTRS` 리터럴 튜플 · 정리는 `.pop(ticker, None)` 만 · `_clear_edge_baseline_on_block` 무변경(래치 토큰 0) |
| A10 | `if ticker:` 안 호출 순서 = `_clear_edge_baseline_on_block` → `_clear_entry_latches_on_pause` |
| A11 | `buy_paused` ∉ `PARAM_RANGES`·`INT_PARAMS`·`_CONSERVATIVE_KEYS` — 런타임 + 소스 리터럴 |
| A12 | glob `strategies/*.py` — `DEFAULT_PARAMS` 를 가진 모든 파일에 `"buy_paused": False` |
| A13 | `[buy_paused_` 마커를 내는 함수에 `write_log` 0 |
| A14 | 8영역 · `scheduler.py` · `boot_manager.py` 에 `buy_paused` 토큰 0 |
| A15 | `[buy_paused_skip]` 은 `logger.info` 로만 |

## 스캔 규약 (가드 설계 금기 2026-09-05)

`Path.read_text` + AST(호출·정의·상수 — 주석 제외, docstring 은 명시적으로 뺀다). `git grep`/`git ls-files`
금지(미추적 신규 파일을 못 본다). `ast.dump` sha 핀 금지.

## 전략 명부 (리팩토링 카드 #1)

A04·A06·A07 의 「전략 파일」 은 7개 고정 목록이 아니라 전략 명부(`tests/_strategy_census.py` — 전략
디렉터리의 파일 전부)다. 고정 목록일 때는 규약을 지켜 복사한 여덟째 전략(키·게이트 다 있음)이 A04·A06
에서 거짓으로 붉었고, 게이트가 없는 여덟째 전략은 A06 을 조용히 지나갔다. 이제 새 전략 파일은 두는
순간 이 가드들의 대상이고, 빠진 것이 있으면 메시지가 무엇을 넣을지 말한다.
"""
from __future__ import annotations

import ast
import importlib.util
import json
from pathlib import Path

import pytest

from tests import _strategy_census as census

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
SB = SRC / "engine" / "strategy_base.py"
CATALOG = SRC / "engine" / "param_catalog.py"
RECO = SRC / "engine" / "recommendation_engine.py"
STRATEGY_DIR = SRC / "engine" / "strategies"
#: 전략 명부 — 전략 디렉터리의 파일 전부(파일 이름순). 새 전략 파일은 두는 순간 A04·A06·A07 대상이다.
STRATEGY_FILES = census.STRATEGY_FILES
KEY = "buy_paused"
HELPERS = ("_buy_paused_blocked", "_clear_entry_latches_on_pause",
           "_emit_buy_paused_config", "_emit_buy_paused_skip")

EIGHT_AREA_FILES = [
    SRC / "engine" / "risk.py",
    SRC / "engine" / "order_engine.py",
    SRC / "engine" / "session.py",
    SRC / "engine" / "scanner.py",
    SRC / "engine" / "strategy_registry.py",
    SRC / "api" / "order.py",
]
EIGHT_AREA_DIRS = [SRC / "realtime", SRC / "auth"]
UNTOUCHED = EIGHT_AREA_FILES + [SRC / "engine" / "scheduler.py", SRC / "engine" / "boot_manager.py"]


# ===========================================================================
# 공용
# ===========================================================================
def _tree(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"))


def _cls(tree: ast.AST, name: str) -> ast.ClassDef:
    for n in ast.walk(tree):
        if isinstance(n, ast.ClassDef) and n.name == name:
            return n
    raise AssertionError(f"class {name} 부재")


def _method(tree: ast.AST, name: str, cls: str = "StrategyBase"):
    for n in _cls(tree, cls).body:
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name:
            return n
    raise AssertionError(f"[Red] {cls}.{name} 부재 — cycle384 미구현")


def _body_wo_docstring(fn) -> list[ast.stmt]:
    body = list(fn.body)
    if body and isinstance(body[0], ast.Expr) and isinstance(getattr(body[0], "value", None), ast.Constant) \
            and isinstance(body[0].value.value, str):
        body = body[1:]
    return body


def _docstring_nodes(tree: ast.AST) -> set[int]:
    out: set[int] = set()
    for n in ast.walk(tree):
        if isinstance(n, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            b = getattr(n, "body", [])
            if b and isinstance(b[0], ast.Expr) and isinstance(b[0].value, ast.Constant) \
                    and isinstance(b[0].value.value, str):
                out.add(id(b[0].value))
    return out


def _tokens(node: ast.AST) -> set[str]:
    out: set[str] = set()
    for n in ast.walk(node):
        if isinstance(n, ast.Name):
            out.add(n.id)
        elif isinstance(n, ast.Attribute):
            out.add(n.attr)
    return out


def _call_name(call: ast.Call) -> str:
    f = call.func
    if isinstance(f, ast.Name):
        return f.id
    if isinstance(f, ast.Attribute):
        return f.attr
    return ""


def _src_files() -> list[Path]:
    return sorted(p for p in SRC.rglob("*.py") if "__pycache__" not in p.parts)


def _is_self_call(call: ast.AST, attr: str) -> bool:
    return (isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute)
            and call.func.attr == attr and isinstance(call.func.value, ast.Name)
            and call.func.value.id == "self")


# ===========================================================================
# A01 · A02 — 게이트 문장 순서
# ===========================================================================
def _gate_body() -> list[ast.stmt]:
    fn = _method(_tree(SB), "_account_soft_gate_blocked")
    return _body_wo_docstring(fn)


def _is_if_self_call_return_true(stmt: ast.stmt, attr: str) -> bool:
    if not isinstance(stmt, ast.If) or stmt.orelse:
        return False
    call = stmt.test
    if not _is_self_call(call, attr):
        return False
    if not (len(call.args) == 1 and isinstance(call.args[0], ast.Name) and call.args[0].id == "ticker"):
        return False
    if len(stmt.body) != 1 or not isinstance(stmt.body[0], ast.Return):
        return False
    ret = stmt.body[0].value
    return isinstance(ret, ast.Constant) and ret.value is True


def test_a01_status_block_stays_first_statement():
    body = _gate_body()
    assert body and _is_if_self_call_return_true(body[0], "_status_buy_blocked"), (
        "게이트 첫 문장이 `if self._status_buy_blocked(ticker): return True` 가 아니다(J25 — M02)"
    )


def test_a02_pause_is_second_statement_then_account_try():
    body = _gate_body()
    assert len(body) >= 3, body
    assert _is_if_self_call_return_true(body[1], "_buy_paused_blocked"), (
        "게이트 두 번째 문장이 `if self._buy_paused_blocked(ticker): return True` 가 아니다(M03)"
    )
    assert isinstance(body[2], ast.Try), "세 번째 문장이 기존 계좌 SOFT `try` 가 아니다"
    toks = _tokens(body[2])
    assert "is_soft_gated" in toks and "account_risk_watcher" in toks, "계좌 SOFT 본문이 바뀌었다(J25b)"
    assert "_buy_paused_blocked" not in toks, "멈춤 판정이 계좌 게이트 안으로 들어갔다(M03)"


# ===========================================================================
# A03 — 헬퍼 순수성 · 최상위 import 추가 0
# ===========================================================================
@pytest.mark.parametrize("name", HELPERS)
def test_a03_helpers_are_sync_and_io_free(name):
    fn = _method(_tree(SB), name)
    assert isinstance(fn, ast.FunctionDef), f"{name} 는 동기 함수여야 한다(check_buy_signal 은 동기)"
    bad = []
    for n in ast.walk(fn):
        if isinstance(n, (ast.Await, ast.AsyncFor, ast.AsyncWith, ast.AsyncFunctionDef)):
            bad.append(type(n).__name__)
        if isinstance(n, ast.Call):
            cn = _call_name(n)
            if cn in ("write_log", "safe_write_log", "create_task", "ensure_future", "run_coroutine_threadsafe") \
                    or cn.startswith("kis_") or cn.startswith("fetch_"):
                bad.append(f"call {cn}")
        if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id == "pg":
            bad.append("pg")
        if isinstance(n, (ast.Import, ast.ImportFrom)):
            bad.append("import")
    assert not bad, f"{name}: hot path 에 I/O·await·import — {bad} (A-PURE)"


_TOP_IMPORTS = {
    "logging", "math", "abc", "dataclasses", "datetime", "enum", "typing",
    "src.engine.daily_emit_cap", "src.engine.observer_trace", "src.engine.turtle_sizing",
}


def test_a03_no_new_top_level_import():
    got = set()
    for node in _tree(SB).body:
        if isinstance(node, ast.Import):
            got.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            got.add(node.module or "")
    assert got == _TOP_IMPORTS, f"strategy_base 최상위 import 가 바뀌었다: +{got - _TOP_IMPORTS} -{_TOP_IMPORTS - got}"


# ===========================================================================
# A04 · A05 — 키 문자열·상수의 위치
# ===========================================================================
def _key_constants(tree: ast.AST) -> list[ast.Constant]:
    return [n for n in ast.walk(tree) if isinstance(n, ast.Constant) and n.value == KEY]


def _default_params_dict(tree: ast.AST) -> ast.Dict | None:
    for n in ast.walk(tree):
        if isinstance(n, ast.ClassDef):
            for st in n.body:
                tgt = None
                if isinstance(st, ast.Assign) and len(st.targets) == 1:
                    tgt = st.targets[0]
                elif isinstance(st, ast.AnnAssign):
                    tgt = st.target
                if isinstance(tgt, ast.Name) and tgt.id == "DEFAULT_PARAMS" and isinstance(st.value, ast.Dict):
                    return st.value
    return None


#: 새 전략 파일에 키가 빠졌을 때 무엇을 하라는 안내(A04 두 가드 공용).
_ADD_KEY_HINT = (
    "새 전략이면 클래스 본문 `DEFAULT_PARAMS = {...}` dict 리터럴에 `\"buy_paused\": False,` 한 줄을 넣어라"
    "(기존 전략 파일과 같은 모양 — 멈춤 판정은 공통 게이트가 하므로 전략 파일에는 키만 둔다)"
)


def test_a04_key_string_appears_only_where_expected():
    where: dict[str, int] = {}
    for p in _src_files():
        n = len(_key_constants(_tree(p)))
        if n:
            where[str(p.relative_to(ROOT))] = n
    expected = {"src/engine/strategy_base.py": 1, "src/engine/param_catalog.py": 1}
    expected.update({f"src/engine/strategies/{f}": 1 for f in STRATEGY_FILES})
    missing = sorted(f for f in STRATEGY_FILES if f"src/engine/strategies/{f}" not in where)
    assert where == expected, (
        f"`\"buy_paused\"` 문자열 위치가 명세와 다르다 — 전략 파일에 멈춤 판정을 넣었거나(M26·M29) "
        f"라우트·스케줄러가 키를 읽는다: {where}"
        + (f" · 키가 없는 파일 {missing} — {_ADD_KEY_HINT}" if missing else "")
    )


@pytest.mark.parametrize("fname", STRATEGY_FILES)
def test_a04_strategy_file_key_lives_in_default_params_only(fname):
    tree = _tree(STRATEGY_DIR / fname)
    d = _default_params_dict(tree)
    assert d is not None, f"{fname}: DEFAULT_PARAMS dict 리터럴 부재"
    hits = [(k, v) for k, v in zip(d.keys, d.values) if isinstance(k, ast.Constant) and k.value == KEY]
    assert len(hits) == 1, f"[Red] {fname}: DEFAULT_PARAMS 에 `buy_paused` 키 {len(hits)}개 — {_ADD_KEY_HINT}"
    v = hits[0][1]
    assert isinstance(v, ast.Constant) and v.value is False, f"{fname}: 값이 상수 False 가 아니다(M10)"


def test_a05_buy_paused_key_constant_referenced_only_in_gate_helper():
    refs: list[str] = []
    defined = 0
    for p in _src_files():
        tree = _tree(p)
        for n in ast.walk(tree):
            if isinstance(n, ast.alias) and (n.name == "BUY_PAUSED_KEY" or n.asname == "BUY_PAUSED_KEY"):
                refs.append(f"{p.name}:import")
        if p == SB:
            for n in tree.body:
                if isinstance(n, (ast.Assign, ast.AnnAssign)):
                    tg = n.targets[0] if isinstance(n, ast.Assign) else n.target
                    if isinstance(tg, ast.Name) and tg.id == "BUY_PAUSED_KEY":
                        defined += 1
                        assert isinstance(n.value, ast.Constant) and n.value.value == KEY
            helper = _method(tree, "_buy_paused_blocked")
            inside = {id(x) for x in ast.walk(helper)}
            for n in ast.walk(tree):
                if isinstance(n, ast.Name) and n.id == "BUY_PAUSED_KEY" and isinstance(n.ctx, ast.Load):
                    if id(n) not in inside:
                        refs.append(f"{p.name}:{n.lineno}")
        else:
            for n in ast.walk(tree):
                if isinstance(n, ast.Name) and n.id == "BUY_PAUSED_KEY":
                    refs.append(f"{p.name}:{n.lineno}")
    assert defined == 1, "[Red] strategy_base 모듈 상수 BUY_PAUSED_KEY 정의 부재"
    assert refs == [], f"BUY_PAUSED_KEY 가 게이트 헬퍼 밖에서 쓰인다: {refs}"


# ===========================================================================
# A06 — 호출 위치
# ===========================================================================
def _enclosing_functions(tree: ast.AST) -> dict[int, str]:
    owner: dict[int, str] = {}

    def visit(node, fname):
        for ch in ast.iter_child_nodes(node):
            nf = ch.name if isinstance(ch, (ast.FunctionDef, ast.AsyncFunctionDef)) else fname
            owner[id(ch)] = nf
            visit(ch, nf)

    visit(tree, "<module>")
    return owner


def test_a06_pause_helper_called_only_from_gate():
    sites = []
    for p in _src_files():
        tree = _tree(p)
        owner = _enclosing_functions(tree)
        for n in ast.walk(tree):
            if isinstance(n, ast.Call) and _call_name(n) == "_buy_paused_blocked":
                sites.append((p.name, owner.get(id(n))))
    assert sites == [("strategy_base.py", "_account_soft_gate_blocked")], (
        f"`_buy_paused_blocked` 호출이 게이트 한 곳이 아니다: {sites}"
    )


def test_a06_gate_called_only_from_seven_check_buy_signal():
    """공통 게이트 호출부 = 전략 명부 파일마다 `check_buy_signal` 안 1곳(이름의 「seven」 은 7전략 시절 그대로).

    게이트 호출이 없는 새 전략은 여기서 붉다 — 그 전략은 종목상태 차단(J25)·`buy_paused`·계좌 SOFT 를
    전부 건너뛰고 매수 신호를 낸다.
    """
    sites = []
    for p in _src_files():
        tree = _tree(p)
        owner = _enclosing_functions(tree)
        for n in ast.walk(tree):
            if isinstance(n, ast.Call) and _call_name(n) == "_account_soft_gate_blocked":
                sites.append((p.name, owner.get(id(n))))
    missing = sorted(f for f in STRATEGY_FILES if (f, "check_buy_signal") not in sites)
    assert sorted(sites) == sorted((f, "check_buy_signal") for f in STRATEGY_FILES), (
        f"공통 게이트 호출부가 전략 명부의 check_buy_signal 이 아니다(청산 경로 혼입 금지): {sites}"
        + (f" · 게이트 호출이 없는 전략 {missing} — check_buy_signal 에 "
           "`if self._account_soft_gate_blocked(ticker): return Signal.NONE` 을 넣어라. 자리는 "
           "tests/unit/ast/test_cycle233_ast_account_risk.py 의 원형 목록을 따른다(GATE_FIRST_FILES = 첫 문장 · "
           "GATE_PRE_BUY_FILES = baseline 갱신 뒤·BUY 직전)" if missing else "")
    )


def test_a06_latch_clear_called_only_from_pause_helper():
    """상태 차단(cycle369) 경로는 기준가만 비우고 래치는 비우지 않는다 — 이 사이클은 그 경로를 바꾸지
    않는다(명세 §13 「비대칭(의도)」 · §16 후속). 래치 정리는 멈춤 헬퍼 한 곳에서만 부른다."""
    sites = []
    for p in _src_files():
        tree = _tree(p)
        owner = _enclosing_functions(tree)
        for n in ast.walk(tree):
            if isinstance(n, ast.Call) and _call_name(n) == "_clear_entry_latches_on_pause":
                sites.append((p.name, owner.get(id(n))))
    assert sites == [("strategy_base.py", "_buy_paused_blocked")], (
        f"`_clear_entry_latches_on_pause` 호출이 멈춤 헬퍼 한 곳이 아니다(상태 차단 경로 행위 변경 금지): {sites}"
    )


# ===========================================================================
# A07 — 캐시 금지
# ===========================================================================
def test_a07_no_cached_pause_attribute():
    hits = []
    for p in [SB] + [STRATEGY_DIR / f for f in STRATEGY_FILES]:
        tree = _tree(p)
        owner = _enclosing_functions(tree)
        for n in ast.walk(tree):
            targets = []
            if isinstance(n, ast.Assign):
                targets = n.targets
            elif isinstance(n, (ast.AnnAssign, ast.AugAssign)):
                targets = [n.target]
            for tg in targets:
                for t in ast.walk(tg):
                    if isinstance(t, ast.Attribute) and isinstance(t.value, ast.Name) \
                            and t.value.id == "self" and "paused" in t.attr.lower():
                        hits.append((p.name, owner.get(id(n)), t.attr))
    assert hits == [("strategy_base.py", "__init__", "_buy_paused_logged")], (
        f"멈춤 값을 인스턴스에 캐시했다 — PUT 이 다음 재시작까지 안 먹는다(M07): {hits}"
    )


def test_a07_gate_helper_reads_config_params_each_call():
    fn = _method(_tree(SB), "_buy_paused_blocked")
    chain = [n for n in ast.walk(fn) if isinstance(n, ast.Attribute) and n.attr == "params"
             and isinstance(n.value, ast.Attribute) and n.value.attr == "config"
             and isinstance(n.value.value, ast.Name) and n.value.value.id == "self"]
    assert chain, "`_buy_paused_blocked` 가 `self.config.params` 를 읽지 않는다(M25 — DEFAULT_PARAMS 에서 읽음)"
    assert "DEFAULT_PARAMS" not in _tokens(fn), "클래스 기본값에서 읽는다 — PUT 이 안 먹는다(M25)"


# ===========================================================================
# A08 — 다른 축으로 구현 금지
# ===========================================================================
_FORBIDDEN_TOKENS = ("buy_disabled", "enabled", "weight", "pending_buys", "_bought_today",
                     "calc_buy_quantity", "total_investment")


@pytest.mark.parametrize("name", HELPERS)
def test_a08_helpers_do_not_touch_other_axes(name):
    fn = _method(_tree(SB), name)
    toks = _tokens(fn)
    bad = sorted({t for t in toks if t in _FORBIDDEN_TOKENS or "low_funds" in t})
    assert not bad, f"{name}: 멈춤을 다른 축(일일손실 래치·enabled·비중·수량·쿨다운)으로 구현했다(M05·M06): {bad}"


# ===========================================================================
# A09 · A10 — 래치 정리 범위 · 순서
# ===========================================================================
def test_a09_latch_attrs_literal_tuple():
    tree = _tree(SB)
    vals = []
    for n in tree.body:
        if isinstance(n, (ast.Assign, ast.AnnAssign)):
            tg = n.targets[0] if isinstance(n, ast.Assign) else n.target
            if isinstance(tg, ast.Name) and tg.id == "_PAUSE_ENTRY_LATCH_ATTRS":
                vals.append(n.value)
    assert len(vals) == 1, "[Red] `_PAUSE_ENTRY_LATCH_ATTRS` 모듈 상수 부재"
    v = vals[0]
    assert isinstance(v, ast.Tuple) and [getattr(e, "value", None) for e in v.elts] == [
        "_breakout_first_seen", "_vol_latch"], "래치 목록은 이 두 이름의 리터럴 튜플이어야 한다(M16)"
    from src.engine import strategy_base as sb

    assert sb._PAUSE_ENTRY_LATCH_ATTRS == ("_breakout_first_seen", "_vol_latch")


def test_a09_latch_clear_only_pops_ticker():
    fn = _method(_tree(SB), "_clear_entry_latches_on_pause")
    pops = []
    for n in ast.walk(fn):
        if isinstance(n, ast.Delete):
            raise AssertionError("래치 정리에 del 문 — `.pop(ticker, None)` 만 허용")
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute):
            if n.func.attr in ("clear", "popitem", "update", "setdefault", "__delitem__", "discard", "remove"):
                raise AssertionError(f"래치 정리에 `.{n.func.attr}()` — 종목 하나만 pop 해야 한다")
            if n.func.attr == "pop":
                pops.append(n)
    assert pops, "래치 정리가 pop 하지 않는다"
    for c in pops:
        assert len(c.args) == 2 and isinstance(c.args[0], ast.Name) and c.args[0].id == "ticker" \
            and isinstance(c.args[1], ast.Constant) and c.args[1].value is None, (
            "`.pop(ticker, None)` 모양이 아니다"
        )
    toks = _tokens(fn) | {n.value for n in ast.walk(fn) if isinstance(n, ast.Constant) and isinstance(n.value, str)}
    for exit_state in ("_position_setup", "_entry_atr", "_breakout_watch", "_cooldown_until",
                       "_breakeven_latched", "_prev_price", "_bought_today"):
        assert exit_state not in toks, f"래치 정리가 `{exit_state}` 를 건드린다(M14·M16)"


def test_a09_status_baseline_helper_does_not_touch_latches():
    fn = _method(_tree(SB), "_clear_edge_baseline_on_block")
    docs = _docstring_nodes(fn)
    strs = {n.value for n in ast.walk(fn)
            if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in docs}
    toks = _tokens(fn) | strs
    assert not ({"_vol_latch", "_breakout_first_seen"} & toks), (
        "상태 차단(cycle369) 헬퍼가 래치를 비운다 — 상태 차단 경로 행위가 바뀐다(명세 §2.3)"
    )


def test_a10_pause_branch_clears_baseline_then_latches():
    fn = _method(_tree(SB), "_buy_paused_blocked")
    branches = [n for n in ast.walk(fn) if isinstance(n, ast.If)
                and isinstance(n.test, ast.Name) and n.test.id == "ticker"]
    assert len(branches) == 1, "`if ticker:` 분기가 정확히 하나여야 한다"
    order = [(_call_name(c), c.lineno, c.col_offset) for c in ast.walk(branches[0])
             if isinstance(c, ast.Call) and _call_name(c) in ("_clear_edge_baseline_on_block",
                                                             "_clear_entry_latches_on_pause")]
    order.sort(key=lambda x: (x[1], x[2]))
    assert [o[0] for o in order] == ["_clear_edge_baseline_on_block", "_clear_entry_latches_on_pause"], (
        f"멈춤 분기의 정리 순서/존재가 다르다(M13 · M15): {order}"
    )


# ===========================================================================
# A11 — AI 자문 경로 편입 금지
# ===========================================================================
def _named_literal_str_keys(tree: ast.Module, name: str) -> set[str]:
    out: set[str] = set()
    for n in tree.body:
        tg = None
        if isinstance(n, ast.Assign) and len(n.targets) == 1:
            tg = n.targets[0]
        elif isinstance(n, ast.AnnAssign):
            tg = n.target
        if isinstance(tg, ast.Name) and tg.id == name and n.value is not None:
            for c in ast.walk(n.value):
                if isinstance(c, ast.Constant) and isinstance(c.value, str):
                    out.add(c.value)
    return out


def test_a11_not_in_param_ranges_int_params_or_auto_apply():
    from src.engine import recommendation_engine as rec

    assert KEY not in rec.PARAM_RANGES, "AI 자문이 멈춤을 켜고 끈다(M12)"
    assert KEY not in rec.INT_PARAMS
    assert KEY not in rec._CONSERVATIVE_KEYS
    tree = _tree(RECO)
    for name in ("PARAM_RANGES", "INT_PARAMS", "_CONSERVATIVE_KEYS"):
        assert KEY not in _named_literal_str_keys(tree, name), f"{name} 리터럴에 buy_paused 편입 금지"
    # 탐지기 self-test — 공허한 PASS 차단
    assert "volume_multiplier" in _named_literal_str_keys(tree, "PARAM_RANGES")
    assert "long_ma_period" in _named_literal_str_keys(tree, "INT_PARAMS")


# ===========================================================================
# A12 — glob 전수: DEFAULT_PARAMS 를 가진 모든 전략 파일
# ===========================================================================
def test_a12_every_strategy_file_with_default_params_has_the_key():
    seen, missing = [], []
    for p in sorted(STRATEGY_DIR.glob("*.py")):
        d = _default_params_dict(_tree(p))
        if d is None:
            continue
        seen.append(p.name)
        vals = [v for k, v in zip(d.keys, d.values) if isinstance(k, ast.Constant) and k.value == KEY]
        if not (len(vals) == 1 and isinstance(vals[0], ast.Constant) and vals[0].value is False):
            missing.append(p.name)
    assert len(seen) >= 7, f"탐지기 무효 — DEFAULT_PARAMS 파일 {seen}"
    assert missing == [], f"[Red] `\"buy_paused\": False` 없는 전략 파일(8번째 전략 포함): {missing}"


# ===========================================================================
# A13 · A15 — 마커 방출 규약
# ===========================================================================
def _marker_functions() -> list[tuple[str, ast.FunctionDef]]:
    out = []
    for p in _src_files():
        tree = _tree(p)
        for fn in ast.walk(tree):
            if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if any(isinstance(c, ast.Constant) and isinstance(c.value, str) and c.value.startswith("[buy_paused_")
                       for c in ast.walk(fn)):
                    out.append((p.name, fn))
    return out


def test_a13_marker_functions_have_no_write_log_pair():
    fns = _marker_functions()
    names = {f.name for _, f in fns}
    assert {"_emit_buy_paused_config", "_emit_buy_paused_skip"} <= names, (
        f"[Red] 마커 방출 함수 부재: {sorted(names)}"
    )
    bad = [(p, f.name) for p, f in fns
           for c in ast.walk(f) if isinstance(c, ast.Call) and _call_name(c) in ("write_log", "safe_write_log")]
    assert bad == [], f"`[buy_paused_` 마커를 write_log 로도 쓴다 — 루트 핸들러와 이중 영속(M24): {bad}"


def _logger_calls(fn, marker: str) -> list[ast.Call]:
    """`logger.<level>("<marker> …", …)` 호출만 — `trace_observer_failure("<marker>", …)` 는 뺀다."""
    return [c for c in ast.walk(fn) if isinstance(c, ast.Call) and isinstance(c.func, ast.Attribute)
            and isinstance(c.func.value, ast.Name) and c.func.value.id == "logger" and c.args
            and isinstance(c.args[0], ast.Constant) and isinstance(c.args[0].value, str)
            and c.args[0].value.startswith(marker)]


def test_a15_skip_marker_is_info_only():
    fn = _method(_tree(SB), "_emit_buy_paused_skip")
    calls = _logger_calls(fn, "[buy_paused_skip]")
    assert calls, "`[buy_paused_skip]` 방출 호출 부재"
    assert {_call_name(c) for c in calls} == {"info"}, "skip 은 logger.info 로만(M23 — 21:30 상위 WARNING 오염)"
    warn = [c for c in ast.walk(fn) if isinstance(c, ast.Call) and isinstance(c.func, ast.Attribute)
            and isinstance(c.func.value, ast.Name) and c.func.value.id == "logger" and c.func.attr == "warning"]
    assert warn == [], "skip 방출 함수에 logger.warning"


def test_a15_config_marker_uses_named_level_calls_not_logger_log():
    """`logger.log(level, …)` 금지 — cycle258 로거-사망 계측이 두 이름(info·warning)을 죽인다."""
    fn = _method(_tree(SB), "_emit_buy_paused_config")
    names = [_call_name(c) for c in _logger_calls(fn, "[buy_paused_config]")]
    assert "warning" in names and "info" in names, names
    assert "log" not in names


# ===========================================================================
# A14 — 무접촉 영역
# ===========================================================================
def _untouched_files() -> list[Path]:
    files = list(UNTOUCHED)
    for d in EIGHT_AREA_DIRS:
        files += sorted(p for p in d.rglob("*.py") if "__pycache__" not in p.parts)
    return files


def test_a14_untouched_areas_have_no_pause_tokens():
    hits = []
    for p in _untouched_files():
        tree = _tree(p)
        docs = _docstring_nodes(tree)
        for n in ast.walk(tree):
            s = None
            if isinstance(n, ast.Name):
                s = n.id
            elif isinstance(n, ast.Attribute):
                s = n.attr
            elif isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in docs:
                s = n.value
            elif isinstance(n, ast.alias):
                s = n.name
            if s and "buy_paused" in s:
                hits.append(f"{p.relative_to(ROOT)}:{getattr(n, 'lineno', '?')}")
    assert len(_untouched_files()) >= 10, "탐지기 무효 — 대상 파일 목록"
    assert hits == [], f"8영역·scheduler·boot_manager 가 buy_paused 를 안다: {hits}"


# ===========================================================================
# R06 — 카탈로그
# ===========================================================================
def test_r06_catalog_row_and_counts():
    from src.engine import param_catalog as pc

    spec = pc.get_spec(KEY)
    assert spec is not None, "[Red] param_catalog 에 buy_paused 행 없음"
    assert spec.type == "bool" and spec.range_src == "enum"
    assert (spec.min, spec.max, spec.step) == (None, None, None)
    assert spec.editable is True, "PUT 이 멈춤의 유일한 조작 경로 — 편집 가능해야 한다"
    assert spec.risk == "identity" and spec.auto_tunable is False and spec.deprecated is False
    assert spec.group == "entry"
    assert tuple(spec.applies_to) == tuple(pc.STRATEGY_IDS), "7전략 공통"
    assert spec.deprecated_for == ()
    assert spec.label_ko and spec.help, "한글 라벨·도움말 필수"
    assert KEY in pc.identity_keys()
    # 🔁 cycle399 재핀 — 공통 섀도 모드 shadow_mode(사용자 승인 10-02 R1) — 105→106 · identity 18→19 · cycle384.1→cycle399.1.
    assert len(pc.PARAM_SPECS) == 125 and len(pc.SPEC_BY_KEY) == 125
    assert len(pc.identity_keys()) == 26
    # 🔁 cycle403 재핀 — ETF 추세 전략(etf_trend) 신설, 신규 키 12개(atr_band_period 는 MED-3 에서 제거) — cycle399.1 → cycle403.1.
    assert pc.CATALOG_VERSION == "cycle405", "카탈로그 버전 미갱신(M27)"


def test_r06_catalog_help_is_honest_about_exits():
    from src.engine import param_catalog as pc

    spec = pc.get_spec(KEY)
    assert spec is not None, "[Red] param_catalog 에 buy_paused 행 없음"
    for word in ("신규 매수", "손절", "트레일링"):
        assert word in spec.help, f"도움말에 「{word}」 가 없다 — 끄기(enabled)와 다르다는 사실을 말해야 한다"


# ===========================================================================
# F01 — 생성 픽스처(프론트·e2e)가 카탈로그를 따른다
# ===========================================================================
_FIXTURES = (
    ROOT / "frontend" / "src" / "test" / "fixtures" / "paramSchema.fixture.ts",
    ROOT / "e2e" / "fixtures" / "param-schema.fixture.ts",
)
_MARK = "export const PARAM_SCHEMA_FIXTURE: ParamSchemaData = "


def _fixture_json(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    assert _MARK in text, f"{path.name}: 픽스처 본문 표지 부재"
    body = text.split(_MARK, 1)[1]
    end = body.index("\n}\n") + 2
    return json.loads(body[:end])


def _generator():
    gen = ROOT / "tools" / "test_fixtures" / "gen_param_schema_fixture.py"
    spec = importlib.util.spec_from_file_location("_gen_param_schema_fixture_c384", gen)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.parametrize("path", _FIXTURES, ids=["frontend", "e2e"])
def test_f01_generated_fixture_carries_buy_paused(path):
    from src.engine import param_catalog as pc

    data = _fixture_json(path)
    assert data["catalog_version"] == pc.CATALOG_VERSION, (
        f"{path.name}: 픽스처가 카탈로그 {pc.CATALOG_VERSION} 로 재생성되지 않았다 "
        "(tools/test_fixtures/gen_param_schema_fixture.py)"
    )
    rows = [p for p in data["params"] if p["key"] == KEY]
    assert len(rows) == 1, f"[Red] {path.name}: buy_paused 스펙 행 {len(rows)}"
    spec = pc.get_spec(KEY)
    assert rows[0] == _generator().spec_to_json(spec), "손으로 고친 픽스처 — 생성기 산출물과 다르다"
    for s in data["strategies"]:
        assert KEY in s["keys"], s["strategy_id"]
        assert s["defaults"][KEY] is False and s["params"][KEY] is False, s["strategy_id"]
    # 🔁 cycle399 재핀 — 공통 섀도 모드 shadow_mode(사용자 승인 10-02 R1) — 105→106.
    assert len(data["params"]) == 125
