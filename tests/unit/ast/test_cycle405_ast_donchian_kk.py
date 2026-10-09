"""cycle405 Red — donchian 깡토식 청산·사이징 구조 봉인 (명세 §9-11 G-405-1~6 + 보조 G-405-7~9).

명세 정본 = `_workspace/red/cycle405_donchian_kkangto_spec.md` §9-11

| # | 봉인 |
|---|---|
| G-405-1 | 새 키 7개 + `risk_pct`·`max_positions`·`sizing_mode` ∉ `PARAM_RANGES`·`INT_PARAMS`·`_CONSERVATIVE_KEYS` (런타임 + 소스 리터럴). `position_ratio` 는 전 전략 공용 PARAM_RANGES 키라 범위 밖(team-leader 확인 요청함) |
| G-405-2 | 청산 3함수 + `check_buy_signal`(그리고 donchian 클래스 안에서 그들이 부르는 메서드 전부)에 `await`·DB·HTTP 심볼 0 · 청산 경로에 시장 유닛 토큰 0 · `check_force_clear` 계열에 시세 저장소 토큰 0 |
| G-405-3 | donchian 청산·사이징·신호 함수(같은 폐포)가 끄는 키 7개를 문자열로 읽지 않는다 |
| G-405-4 | `check_exit_signal` 과 `get_effective_stop_price` 가 같은 헬퍼를 부르고, R·무장 키는 그 헬퍼에만 있다 |
| G-405-5 | `DEFAULT_PARAMS` 리터럴에 `buy_paused: False` · `position_ratio × max_positions ≤ 1.0` |
| G-405-6 | (cycle419 에서 걷음 — 8영역·`scheduler.py` 파일 sha 는 정본 `test_cycle222a3_ast_followup_fixes.py::_APPROVED_CONTENT_SHA` 한 곳) |
| G-405-7 | `calc_buy_quantity` 의 모든 return = 상수 `0` 또는 `self._apply_budget_limit(...)` · `_fallback_one_share` 직접 호출 0 |
| G-405-8 | `StrategyBase._apply_budget_limit` 소스 세그먼트 sha256 불변(관문 무접촉) |
| G-405-9 | `_position_atr` 신설 금지(R 은 매수 시점 값으로만 정한다 — 명세 §1) |

스캔 규약(가드 설계 금기 2026-09-05): `Path.read_text` + AST, `git grep`/`git diff` 금지, `ast.dump` sha 핀 금지
(핀은 파일 바이트 sha256 또는 `ast.get_source_segment` sha256).
"""
from __future__ import annotations

import ast
import hashlib
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
DC = SRC / "engine" / "strategies" / "donchian_swing.py"
SB = SRC / "engine" / "strategy_base.py"
RECO = SRC / "engine" / "recommendation_engine.py"

NEW_KEYS = ("kk_r_floor_pct", "kk_r_atr_mult", "kk_breakeven_r", "kk_time_exit_bars",
            "kk_time_exit_min_r", "kk_max_hold_bars", "max_daily_entries")
CHANGED_KEYS_NOT_TUNABLE = ("risk_pct", "max_positions", "sizing_mode")
OFF_KEYS = ("stop_atr", "atr_trail_mult", "breakeven_promote_atr", "breakout_fail_n_days",
            "turtle_backstop_pct", "stop_loss_rate", "min_vol_floor_pct")
EXIT_ROOTS = ("check_exit_signal", "get_effective_stop_price", "check_force_clear")
SIZING_ROOTS = ("calc_buy_quantity", "check_buy_signal")
IO_TOKENS = ("write_log", "pg", "fetch_", "kis_", "httpx", "aiohttp", "create_task",
             "get_recent_daily", "requests", "urlopen", "asyncio")
QUOTE_TOKENS = ("ticker_prices", "ticker_last_tick", "scanner")


def _tree(p: Path) -> ast.Module:
    return ast.parse(p.read_text(encoding="utf-8"))


def _class(tree: ast.Module, name: str) -> ast.ClassDef:
    for n in tree.body:
        if isinstance(n, ast.ClassDef) and n.name == name:
            return n
    raise AssertionError(f"{name} 클래스 없음")


def _methods(cls: ast.ClassDef) -> dict[str, ast.FunctionDef]:
    return {n.name: n for n in cls.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}


def _self_calls(fn) -> set[str]:
    out = set()
    for n in ast.walk(fn):
        if (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                and isinstance(n.func.value, ast.Name) and n.func.value.id == "self"):
            out.add(n.func.attr)
    return out


def _closure(roots) -> dict[str, ast.FunctionDef]:
    """donchian 클래스 안에서 roots 가 (전이적으로) 부르는 메서드 — 다른 클래스는 따라가지 않는다."""
    ms = _methods(_class(_tree(DC), "DonchianSwingStrategy"))
    seen: dict[str, ast.FunctionDef] = {}
    todo = [r for r in roots]
    while todo:
        name = todo.pop()
        if name in seen or name not in ms:
            continue
        seen[name] = ms[name]
        todo.extend(_self_calls(ms[name]))
    missing = [r for r in roots if r not in seen]
    assert missing == [], f"donchian 에 {missing} 정의 없음"
    return seen


def _strip_docstring(fn):
    body = fn.body
    if body and isinstance(body[0], ast.Expr) and isinstance(getattr(body[0], "value", None), ast.Constant) \
            and isinstance(body[0].value.value, str):
        return body[1:]
    return body


def _str_consts(fn) -> set[str]:
    out = set()
    for stmt in _strip_docstring(fn):
        for n in ast.walk(stmt):
            if isinstance(n, ast.Constant) and isinstance(n.value, str):
                out.add(n.value)
    return out


def _identifiers(fn) -> set[str]:
    out = set()
    for stmt in _strip_docstring(fn):
        for n in ast.walk(stmt):
            if isinstance(n, ast.Name):
                out.add(n.id)
            elif isinstance(n, ast.Attribute):
                out.add(n.attr)
            elif isinstance(n, ast.alias):
                out.add(n.name)
                out.update(n.name.split("."))
            elif isinstance(n, ast.ImportFrom) and n.module:
                out.update(n.module.split("."))
    return out


def _named_literal_str_keys(tree: ast.Module, name: str) -> set[str]:
    out: set[str] = set()
    for n in ast.walk(tree):
        tgt = None
        if isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name):
            tgt, val = n.targets[0].id, n.value
        elif isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name) and n.value is not None:
            tgt, val = n.target.id, n.value
        if tgt != name:
            continue
        for c in ast.walk(val):
            if isinstance(c, ast.Constant) and isinstance(c.value, str):
                out.add(c.value)
    return out


def _default_params(tree: ast.Module) -> dict:
    cls = _class(tree, "DonchianSwingStrategy")
    for n in cls.body:
        if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "DEFAULT_PARAMS" for t in n.targets):
            assert isinstance(n.value, ast.Dict)
            return {k.value: v for k, v in zip(n.value.keys, n.value.values) if isinstance(k, ast.Constant)}
    raise AssertionError("DEFAULT_PARAMS 리터럴 없음")


# ===========================================================================
# G-405-1
# ===========================================================================
@pytest.mark.parametrize("key", NEW_KEYS + CHANGED_KEYS_NOT_TUNABLE)
def test_g405_1_identity_keys_not_ai_tunable(key):
    from src.engine import recommendation_engine as rec

    assert key not in rec.PARAM_RANGES
    assert key not in rec.INT_PARAMS
    assert key not in rec._CONSERVATIVE_KEYS
    tree = _tree(RECO)
    for name in ("PARAM_RANGES", "INT_PARAMS", "_CONSERVATIVE_KEYS"):
        assert key not in _named_literal_str_keys(tree, name), f"{name} 리터럴에 {key} 편입 금지"


def test_g405_1_detector_self_test():
    tree = _tree(RECO)
    assert "volume_multiplier" in _named_literal_str_keys(tree, "PARAM_RANGES")
    assert "long_ma_period" in _named_literal_str_keys(tree, "INT_PARAMS")


def test_g405_1_new_keys_exist_in_default_params_literal():
    d = _default_params(_tree(DC))
    assert [k for k in NEW_KEYS if k not in d] == [], "[Red] DEFAULT_PARAMS 에 새 키 없음"


# ===========================================================================
# G-405-2
# ===========================================================================
def test_g405_2_exit_and_signal_paths_have_no_await_or_io():
    bad = []
    for name, fn in _closure(EXIT_ROOTS + SIZING_ROOTS).items():
        if isinstance(fn, ast.AsyncFunctionDef):
            bad.append(f"{name}: async def")
        for stmt in _strip_docstring(fn):
            for n in ast.walk(stmt):
                if isinstance(n, (ast.Await, ast.AsyncFor, ast.AsyncWith)):
                    bad.append(f"{name}: await")
        ids = _identifiers(fn)
        for tok in IO_TOKENS:
            hit = [i for i in ids if i == tok or (tok.endswith("_") and i.startswith(tok))]
            if hit:
                bad.append(f"{name}: {hit}")
    assert bad == [], bad


def test_g405_2_exit_path_has_no_market_unit_tokens():
    bad = []
    for name, fn in _closure(EXIT_ROOTS).items():
        toks = {i for i in _identifiers(fn) if "market_unit" in i}
        toks |= {c for c in _str_consts(fn) if "market_unit" in c}
        if toks:
            bad.append(f"{name}: {sorted(toks)}")
    assert bad == [], f"cycle382 A07 — 청산 경로에 시장 유닛 금지: {bad}"


def test_g405_2_force_clear_reads_no_quotes():
    bad = []
    for name, fn in _closure(("check_force_clear",)).items():
        hit = sorted(_identifiers(fn) & set(QUOTE_TOKENS))
        if hit:
            bad.append(f"{name}: {hit}")
    assert bad == [], f"15:20 판정은 시세를 읽지 않는다: {bad}"


def test_g405_2_force_clear_is_overridden_and_signal_is_time_exit():
    ms = _methods(_class(_tree(DC), "DonchianSwingStrategy"))
    assert "force_clear_signal" in ms, "[Red] force_clear_signal 덮어쓰기 없음"
    attrs = {n.attr for n in ast.walk(ms["force_clear_signal"]) if isinstance(n, ast.Attribute)}
    assert "TIME_EXIT" in attrs


# ===========================================================================
# G-405-3
# ===========================================================================
def test_g405_3_off_keys_not_read_by_exit_sizing_or_signal():
    bad = []
    for name, fn in _closure(EXIT_ROOTS + SIZING_ROOTS).items():
        hit = sorted(_str_consts(fn) & set(OFF_KEYS))
        if hit:
            bad.append(f"{name}: {hit}")
    assert bad == [], f"끄는 키를 donchian 청산·사이징이 읽는다: {bad}"


def test_g405_3_detector_self_test():
    """탐지기 공허 PASS 차단 — `prepare` 는 `donchian_period` 를 읽는다."""
    ms = _methods(_class(_tree(DC), "DonchianSwingStrategy"))
    assert "donchian_period" in _str_consts(ms["prepare"])


# ===========================================================================
# G-405-4
# ===========================================================================
def test_g405_4_exit_and_mirror_share_one_helper_holding_the_r_formula():
    clo_exit = _closure(("check_exit_signal",))
    clo_mirror = _closure(("get_effective_stop_price",))
    common = (set(clo_exit) & set(clo_mirror)) - {"check_exit_signal", "get_effective_stop_price"}
    need = {"kk_r_floor_pct", "kk_breakeven_r"}
    holders = [n for n in common
               if need <= set().union(*(_str_consts(f) for f in _closure((n,)).values()))]
    assert holders, f"[Red] 두 경로가 같은 R·무장 헬퍼를 부르지 않는다 — 공통 {sorted(common)}"
    ms = _methods(_class(_tree(DC), "DonchianSwingStrategy"))
    for root in ("check_exit_signal", "get_effective_stop_price"):
        dup = _str_consts(ms[root]) & {"kk_r_floor_pct", "kk_r_atr_mult", "kk_breakeven_r"}
        assert not dup, f"{root} 가 산식 키를 직접 읽는다(산식 이중화): {dup}"


# ===========================================================================
# G-405-5
# ===========================================================================
def test_g405_5_buy_paused_and_budget_invariant_in_literal():
    d = _default_params(_tree(DC))
    assert isinstance(d.get("buy_paused"), ast.Constant) and d["buy_paused"].value is False
    pr, mp = d["position_ratio"], d["max_positions"]
    assert isinstance(pr, ast.Constant) and isinstance(mp, ast.Constant)
    assert pr.value * mp.value <= 1.0 + 1e-12


# ===========================================================================
# G-405-7
# ===========================================================================
def test_g405_7_calc_returns_are_zero_or_budget_gate():
    fn = _methods(_class(_tree(DC), "DonchianSwingStrategy"))["calc_buy_quantity"]
    bad = []
    for n in ast.walk(fn):
        if not isinstance(n, ast.Return):
            continue
        v = n.value
        if isinstance(v, ast.Constant) and v.value == 0:
            continue
        if (isinstance(v, ast.Call) and isinstance(v.func, ast.Attribute)
                and v.func.attr == "_apply_budget_limit"):
            continue
        bad.append(ast.unparse(n))
    assert bad == [], f"A-GATE — 허용되지 않은 return: {bad}"
    assert "_fallback_one_share" not in _identifiers(fn)


def test_g405_7_no_ratio_fallthrough_in_calc():
    """옛 `amount = total_investment × position_ratio; return gate(amount // price)` 낙하 경로가 없다.

    설계 랏의 명목 상한(`int(B × m × position_ratio) // P`)은 `min` 안에서만 쓰인다 — 그것 하나로
    관문에 넘기는 return 이 남아 있으면 「터틀→비중 낙하」 다.
    """
    fn = _methods(_class(_tree(DC), "DonchianSwingStrategy"))["calc_buy_quantity"]
    assert "_turtle_buy_quantity" not in _self_calls(fn), "옛 터틀 유닛 경로(폴백 낙하 동반) 호출 금지"


# ===========================================================================
# G-405-8
# ===========================================================================
def test_g405_8_budget_gate_segment_unchanged():
    src = SB.read_text(encoding="utf-8")
    seg = None
    for n in ast.walk(ast.parse(src)):
        if isinstance(n, ast.FunctionDef) and n.name == "_apply_budget_limit":
            seg = ast.get_source_segment(src, n)
    assert seg is not None
    assert hashlib.sha256(seg.encode("utf-8")).hexdigest() == (
        "fe40eea083f894925c93dabf538c4fe045624b9db4c1ea5fd75ed50a16a3ac09"
    ), "관문 `_apply_budget_limit` 본문은 이 사이클에서 무접촉"


# ===========================================================================
# G-405-9
# ===========================================================================
def test_g405_9_no_position_atr_dict():
    ids = set()
    for n in ast.walk(_tree(DC)):
        if isinstance(n, ast.Attribute):
            ids.add(n.attr)
    assert "_position_atr" not in ids
