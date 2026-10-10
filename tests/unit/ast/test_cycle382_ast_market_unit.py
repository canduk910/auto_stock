"""cycle382 Red — 시장 유닛 AST 가드 (A01~A12).

명세 = `_workspace/red/cycle382_market_unit_spec.md` §3 · §5.4 · §6 · §9 · §10 · §11.3

스캔 = 파일 읽기 + AST(호출·정의·대입만 — 주석·docstring 제외). `git grep`/`git ls-files` 금지
(미추적 새 파일을 로컬에서 못 본다 — 가드 설계 금기). 본체 무변경 핀은 `ast.get_source_segment` sha256
(`ast.dump` sha 금지 — 3.12/3.13 출력이 다르다).

영구 가드다(사이클 한정 아님). A12 의 관문 sha 는 관문을 **의도적으로** 바꾸는 사이클이 값만 재핀한다.
Red 유효성: leaf·헬퍼·DEFAULT_PARAMS 키·카탈로그 행이 없어 실패한다. A03·A04 의 음성 단언
(편입 0 · 3전략/8영역 토큰 0)과 A06·A12 관문 sha 는 지금도 초록이다 — 구현이 깨면 붉어지는 몫.
"""
from __future__ import annotations

import ast
import hashlib
import inspect
import sys
from pathlib import Path

import pytest

from src.engine import recommendation_engine as rec_mod
from src.engine.strategy_base import StrategyBase

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parents[3]
_ENGINE = _ROOT / "src" / "engine"
_LEAF = _ENGINE / "market_unit.py"
_SB = _ENGINE / "strategy_base.py"
_STRATS = _ENGINE / "strategies"
_RECO = _ENGINE / "recommendation_engine.py"

TURTLE_FILES = {
    "kojiro.py": "kojiro",
    "donchian_swing.py": "donchian_swing",
    "bull_flag_breakout.py": "bull_flag_breakout",
    "vcp_breakout.py": "vcp_breakout",
}
#: 터틀 블록 함수 (cycle242 G-242-8 과 같은 표)
_TURTLE_BLOCK = {
    "kojiro.py": "calc_buy_quantity",
    "donchian_swing.py": "_turtle_buy_quantity",
    "bull_flag_breakout.py": "_turtle_buy_quantity",
    "vcp_breakout.py": "_turtle_buy_quantity",
}
OTHER_FILES = ("momentum.py", "volatility_breakout.py", "long_tail_volatility.py")
#: 8영역 정본 = tests/unit/ast/test_cycle222a3_ast_followup_fixes.py::_EIGHT_AREAS
_EIGHT_AREAS = (
    "src/engine/risk.py", "src/engine/order_engine.py", "src/engine/scanner.py",
    "src/engine/session.py", "src/engine/strategy_registry.py", "src/api/order.py",
    "src/realtime", "src/auth",
)
_EIGHT_AREA_MODULES = (
    "src.engine.risk", "src.engine.order_engine", "src.engine.session", "src.engine.scanner",
    "src.engine.strategy_registry", "src.api.order", "src.realtime", "src.auth",
)
_SYNC_HELPERS = (
    "_market_unit_view", "_market_unit_lots", "_market_unit_skip_reason",
    "_market_unit_sizing", "_market_unit_blocks_entry", "_market_unit_tally_roll",
)
_FORBIDDEN_IMPORTS = ("src.db", "httpx", "requests", "asyncio", "aiohttp")
_STATE_NAMES = ("up_rising", "up_falling", "down_rising", "down_falling")


# ===========================================================================
# 헬퍼
# ===========================================================================
def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def _leaf_src() -> str:
    if not _LEAF.exists():
        pytest.fail("[Red] src/engine/market_unit.py 미존재 — cycle382 미구현")
    return _read(_LEAF)


def _func(src: str, name: str, *, cls: str | None = None) -> ast.AST:
    tree = ast.parse(src)
    scope = tree
    if cls is not None:
        found = [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef) and n.name == cls]
        assert found, f"클래스 {cls} 없음"
        scope = found[0]
    for node in ast.walk(scope):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    pytest.fail(f"[Red] {name} 함수 없음 — cycle382 미구현 또는 개명")


def _calls(node: ast.AST, name: str) -> list[ast.Call]:
    out = []
    for n in ast.walk(node):
        if isinstance(n, ast.Call):
            f = n.func
            nm = f.attr if isinstance(f, ast.Attribute) else f.id if isinstance(f, ast.Name) else None
            if nm == name:
                out.append(n)
    return out


def _walk_no_nested(fn: ast.AST):
    """fn 본문을 걷되 중첩 def/lambda 안으로는 들어가지 않는다."""
    stack = list(ast.iter_child_nodes(fn))
    while stack:
        n = stack.pop()
        yield n
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)):
            continue
        stack.extend(ast.iter_child_nodes(n))


def _docstring_nodes(tree: ast.AST) -> set[int]:
    ids = set()
    for n in ast.walk(tree):
        if isinstance(n, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = getattr(n, "body", [])
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
                    and isinstance(body[0].value.value, str):
                ids.add(id(body[0].value))
    return ids


def _token_hits(src: str, needle: str) -> list[str]:
    """식별자·속성·import·(docstring 아닌) 문자열 상수 안의 `needle` — 주석·docstring 제외."""
    tree = ast.parse(src)
    docs = _docstring_nodes(tree)
    hits = []
    for n in ast.walk(tree):
        if isinstance(n, ast.Name) and needle in n.id:
            hits.append(f"{n.lineno}:Name {n.id}")
        elif isinstance(n, ast.Attribute) and needle in n.attr:
            hits.append(f"{n.lineno}:Attr {n.attr}")
        elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and needle in n.name:
            hits.append(f"{n.lineno}:def {n.name}")
        elif isinstance(n, ast.alias) and needle in (n.name or ""):
            hits.append(f"alias {n.name}")
        elif isinstance(n, ast.ImportFrom) and needle in (n.module or ""):
            hits.append(f"{n.lineno}:from {n.module}")
        elif isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in docs \
                and needle in n.value:
            hits.append(f"{n.lineno}:str {n.value[:40]!r}")
    return hits


def _imports(node: ast.AST) -> list[str]:
    out = []
    for n in ast.walk(node):
        if isinstance(n, ast.Import):
            out.extend(a.name for a in n.names)
        elif isinstance(n, ast.ImportFrom):
            out.append(n.module or "")
    return out


def _collect_named_literal_str_keys(src: str, name: str) -> list[str]:
    """`name = {...}` (Assign/AnnAssign) dict/set 리터럴의 str 키 (cycle242 G-242-1 탐지기 동형)."""
    tree = ast.parse(src)
    keys: list[str] = []
    for node in ast.walk(tree):
        value = None
        if isinstance(node, ast.Assign):
            if any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
                value = node.value
        elif isinstance(node, ast.AnnAssign):
            if isinstance(node.target, ast.Name) and node.target.id == name:
                value = node.value
        if isinstance(value, ast.Dict):
            keys.extend(k.value for k in value.keys if isinstance(k, ast.Constant) and isinstance(k.value, str))
        elif isinstance(value, ast.Set):
            keys.extend(e.value for e in value.elts if isinstance(e, ast.Constant) and isinstance(e.value, str))
    return keys


def _turtle_block_keys(src: str, fn_name: str) -> set[str]:
    """cycle242 G-242-8 탐지기 — 터틀 블록이 후보 dict(`_candidates…`/`info`)에서 읽는 str 키."""
    fn = _func(src, fn_name)
    found: set[str] = set()
    for node in ast.walk(fn):
        if not (isinstance(node, ast.Call) and getattr(node.func, "attr", None) == "get"):
            continue
        if not node.args or not isinstance(node.args[0], ast.Constant) or not isinstance(node.args[0].value, str):
            continue
        recv = ast.unparse(node.func.value)
        if "_candidates" in recv or recv == "info":
            found.add(node.args[0].value)
    return found


# ===========================================================================
# A01 — leaf 순수성 · import 경계
# ===========================================================================
def test_a01_leaf_pure_functions_and_import_boundary():
    src = _leaf_src()
    tree = ast.parse(src)
    for name in ("classify", "normalize_mode"):
        fn = _func(src, name)
        assert isinstance(fn, ast.FunctionDef), f"{name} 는 동기 함수여야 한다"
        assert not [n for n in ast.walk(fn) if isinstance(n, ast.Await)], f"{name} 에 await"
        assert not _imports(fn), f"{name} 안에 import"
    top = []
    for stmt in tree.body:
        if isinstance(stmt, (ast.Import, ast.ImportFrom)):
            top.extend(_imports(stmt))
    bad_top = [m for m in top if m.split(".")[0] not in sys.stdlib_module_names]
    assert bad_top == [], f"최상위 import 는 표준 라이브러리만 — {bad_top}"
    every = _imports(tree)
    banned = _EIGHT_AREA_MODULES + ("src.engine.scheduler", "src.engine.boot_manager",
                                    "src.engine.market_regime")
    offenders = [m for m in every if m.startswith(banned)]
    assert offenders == [], f"leaf 가 금지 모듈을 import 한다 — {offenders}"
    lazy = [m for m in every if m.startswith("src.")]
    assert set(lazy) <= {"src.db", "src.db.stock_master_daily", "src.engine", "src.engine.trading_calendar"}, lazy


def test_a01_leaf_logger_name_is_module_name():
    src = _leaf_src()
    calls = [c for c in _calls(ast.parse(src), "getLogger")]
    assert calls, "leaf 에 logging.getLogger 가 없다"
    args = [ast.unparse(c.args[0]) if c.args else "" for c in calls]
    assert any(a in ("__name__", "'src.engine.market_unit'", '"src.engine.market_unit"') for a in args), args


# ===========================================================================
# A02 — 배수·창 상수는 leaf 한 곳에만
# ===========================================================================
def test_a02_constants_defined_once_in_leaf():
    src = _leaf_src()
    tree = ast.parse(src)
    assigned = [
        t.id for stmt in tree.body if isinstance(stmt, (ast.Assign, ast.AnnAssign))
        for t in (stmt.targets if isinstance(stmt, ast.Assign) else [stmt.target])
        if isinstance(t, ast.Name)
    ]
    for name in ("MA_WINDOW", "SLOPE_LOOKBACK", "MULTIPLIERS", "MIN_ROWS"):
        assert assigned.count(name) == 1, f"leaf 모듈 최상위에 {name} 정의가 정확히 1개여야 한다"


@pytest.mark.parametrize("path", [_SB] + [_STRATS / f for f in TURTLE_FILES], ids=lambda p: p.name)
def test_a02_no_redefinition_outside_leaf(path):
    src = _read(path)
    tree = ast.parse(src)
    for n in ast.walk(tree):
        if isinstance(n, (ast.Assign, ast.AnnAssign)):
            targets = n.targets if isinstance(n, ast.Assign) else [n.target]
            for t in targets:
                nm = t.id if isinstance(t, ast.Name) else t.attr if isinstance(t, ast.Attribute) else ""
                assert nm not in ("MA_WINDOW", "SLOPE_LOOKBACK", "MULTIPLIERS", "MIN_ROWS"), (
                    f"{path.name}:{n.lineno} {nm} 재정의 — 상수는 market_unit.py 한 곳에만(A02)"
                )
        if isinstance(n, ast.Constant) and isinstance(n.value, float) and n.value == 0.75:
            pytest.fail(f"{path.name}:{n.lineno} 배수 리터럴 0.75 — MULTIPLIERS 를 읽어라")
        if isinstance(n, ast.Constant) and isinstance(n.value, str) and n.value in _STATE_NAMES:
            pytest.fail(f"{path.name}:{n.lineno} 상태 이름 리터럴 {n.value!r} — leaf 가 정본이다")


def test_a02_base_helpers_hold_no_window_or_multiplier_literals():
    src = inspect.getsource(StrategyBase)
    for name in _SYNC_HELPERS + ("_refresh_market_unit",):
        fn = _func(src, name)
        bad = [
            (n.lineno, n.value) for n in ast.walk(fn)
            if isinstance(n, ast.Constant) and not isinstance(n.value, bool)
            and isinstance(n.value, (int, float)) and n.value in (0.75, 0.5, 60, 20, 80, 120)
        ]
        assert bad == [], f"{name} 에 창·배수 리터럴 {bad} — leaf 상수를 읽어라"


# ===========================================================================
# A03 — AI 자문 자동 적용 경로 편입 금지
# ===========================================================================
def test_a03_runtime_param_ranges_excludes_key():
    assert "market_unit_mode" not in rec_mod.PARAM_RANGES
    assert "market_unit_mode" not in rec_mod.INT_PARAMS


def test_a03_source_literals_exclude_key():
    src = _read(_RECO)
    for name in ("PARAM_RANGES", "INT_PARAMS"):
        keys = _collect_named_literal_str_keys(src, name)
        assert keys, f"{name} 리터럴 파싱 실패 (탐지기 무효)"
        assert "market_unit_mode" not in keys


def test_a03_detector_self_test():
    src = _read(_RECO)
    assert "position_ratio" in _collect_named_literal_str_keys(src, "PARAM_RANGES")
    assert "long_ma_period" in _collect_named_literal_str_keys(src, "INT_PARAMS")


def test_a03_catalog_marks_key_not_auto_tunable():
    from src.engine import param_catalog as pc

    spec = pc.get_spec("market_unit_mode")
    assert spec is not None, "[Red] param_catalog 에 market_unit_mode 행 없음"
    assert spec.auto_tunable is False
    assert "market_unit_mode" not in pc.auto_tunable_keys()


# ===========================================================================
# A04 — 3전략 · 8영역 · scheduler 무접촉
# ===========================================================================
@pytest.mark.parametrize("fname", OTHER_FILES)
def test_a04_other_three_strategies_have_no_market_unit_token(fname):
    hits = _token_hits(_read(_STRATS / fname), "market_unit")
    assert hits == [], f"{fname} 에 market_unit 토큰 {hits} — 당일·익일 3전략은 범위 밖"


def _eight_area_files() -> list[Path]:
    out: list[Path] = []
    for rel in _EIGHT_AREAS:
        p = _ROOT / rel
        out.extend(sorted(p.rglob("*.py")) if p.is_dir() else [p])
    out.append(_ENGINE / "scheduler.py")
    out.append(_ENGINE / "boot_manager.py")
    return out


@pytest.mark.parametrize("path", _eight_area_files(), ids=lambda p: str(p.relative_to(_ROOT)))
def test_a04_eight_areas_scheduler_boot_have_no_market_unit_token(path):
    hits = _token_hits(_read(path), "market_unit")
    assert hits == [], f"{path.relative_to(_ROOT)} 에 market_unit 토큰 {hits} — 8영역·scheduler·boot_manager 무접촉"


def test_a04_leaf_exists_so_the_negative_scans_are_not_vacuous():
    """위 두 음성 스캔은 leaf 가 생긴 뒤에만 의미가 있다(공허한 PASS 차단)."""
    _leaf_src()
    assert _token_hits(_read(_SB), "market_unit"), "strategy_base 에 시장 유닛 헬퍼가 없다(탐지기 자기시험)"


# ===========================================================================
# A05 — 새 동기 헬퍼 6개 순수성 · refresh 는 async
# ===========================================================================
@pytest.mark.parametrize("name", _SYNC_HELPERS)
def test_a05_sync_helpers_are_pure(name):
    src = inspect.getsource(StrategyBase)
    fn = _func(src, name)
    assert isinstance(fn, ast.FunctionDef), f"{name} 는 동기 함수여야 한다(A-ATOMIC 구간 안에서 불린다)"
    assert not [n for n in ast.walk(fn) if isinstance(n, ast.Await)], f"{name} 에 await"
    bad = [m for m in _imports(fn) if m.startswith(_FORBIDDEN_IMPORTS)]
    assert bad == [], f"{name} 금지 import {bad}"


def test_a05_refresh_is_async():
    fn = _func(inspect.getsource(StrategyBase), "_refresh_market_unit")
    assert isinstance(fn, ast.AsyncFunctionDef)


# ===========================================================================
# A06 — 전략 코드는 total_investment 에 대입하지 않는다
# ===========================================================================
@pytest.mark.parametrize("path", [_STRATS / f for f in TURTLE_FILES], ids=lambda p: p.name)
def test_a06_no_total_investment_assignment_in_turtle_strategies(path):
    tree = ast.parse(_read(path))
    for n in ast.walk(tree):
        targets = []
        if isinstance(n, ast.Assign):
            targets = n.targets
        elif isinstance(n, (ast.AugAssign, ast.AnnAssign)):
            targets = [n.target]
        for t in targets:
            assert not (isinstance(t, ast.Attribute) and t.attr == "total_investment"), (
                f"{path.name}:{n.lineno} total_investment 대입 — 시장 유닛은 예산을 건드리지 않는다"
            )


def test_a06_market_unit_helpers_do_not_assign_total_investment():
    src = inspect.getsource(StrategyBase)
    for name in _SYNC_HELPERS + ("_refresh_market_unit",):
        fn = _func(src, name)
        for n in ast.walk(fn):
            if isinstance(n, (ast.Assign, ast.AugAssign, ast.AnnAssign)):
                targets = n.targets if isinstance(n, ast.Assign) else [n.target]
                assert not any(isinstance(t, ast.Attribute) and t.attr == "total_investment" for t in targets), name


# ===========================================================================
# A07 — 청산 계열은 시장 유닛을 읽지 않는다 · refresh 는 보유 청산 입력을 읽지 않는다
# ===========================================================================
_EXIT_FUNCS = ("check_exit_signal", "get_effective_stop_price", "_position_stop_price",
               "_effective_setup", "_effective_atr", "check_force_clear")


@pytest.mark.parametrize("fname", list(TURTLE_FILES))
def test_a07_exit_paths_do_not_reference_market_unit(fname):
    src = _read(_STRATS / fname)
    tree = ast.parse(src)
    seen = 0
    for n in ast.walk(tree):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name in _EXIT_FUNCS:
            seen += 1
            hits = _token_hits(ast.unparse(n), "_market_unit")
            assert hits == [], f"{fname}::{n.name} 가 시장 유닛을 읽는다 {hits} — 보유분 무접촉"
    assert seen >= 2, f"{fname} 청산 함수 탐지 실패(탐지기 무효)"


def test_a07_refresh_touches_no_held_exit_inputs():
    fn = _func(inspect.getsource(StrategyBase), "_refresh_market_unit")
    forbidden = {"_candidates", "positions", "_entry_atr", "_position_setup", "_position_atr",
                 "_breakout_high"}
    hits = []
    for n in ast.walk(fn):
        if isinstance(n, ast.Attribute) and n.attr in forbidden:
            hits.append(n.attr)
        if isinstance(n, ast.Constant) and isinstance(n.value, str) and n.value in forbidden:
            hits.append(n.value)
    assert hits == [], f"_refresh_market_unit 가 PV-1 입력을 참조한다 {hits}"


# ===========================================================================
# A08 — 4전략 prepare: refresh 정확히 1회, resolve 뒤 · 첫 return 앞 · 유니버스 스캔 앞
# ===========================================================================
@pytest.mark.parametrize("fname", list(TURTLE_FILES))
def test_a08_prepare_calls_refresh_once_before_any_return(fname):
    src = _read(_STRATS / fname)
    fn = _func(src, "prepare")
    refresh = _calls(fn, "_refresh_market_unit")
    assert len(refresh) == 1, f"{fname} prepare 의 _refresh_market_unit 호출 {len(refresh)}회(정확히 1회)"
    call = refresh[0]
    awaited = [n for n in ast.walk(fn) if isinstance(n, ast.Await) and n.value is call]
    assert awaited, f"{fname} _refresh_market_unit 를 await 하지 않았다"
    kw = {k.arg: ast.unparse(k.value) for k in call.keywords}
    assert kw == {"as_of_date": "as_of_date", "preview": "preview"}, (
        f"{fname} refresh 인자는 _resolve_prepare_as_of 결과 그대로여야 한다 — {kw}"
    )
    resolve = _calls(fn, "_resolve_prepare_as_of")
    assert resolve and resolve[0].lineno < call.lineno, f"{fname} refresh 가 as_of 해석보다 앞"
    returns = [n.lineno for n in _walk_no_nested(fn) if isinstance(n, ast.Return)]
    assert returns and call.lineno < min(returns), f"{fname} refresh 가 첫 return({min(returns)}) 뒤"
    scans = _calls(fn, "_scan_universe")
    assert scans and call.lineno < min(s.lineno for s in scans), (
        f"{fname} refresh 가 유니버스 스캔(0건 재시도 루프 포함)보다 뒤"
    )


# ===========================================================================
# A09 — ATR 키 = 터틀 블록이 읽는 키
# ===========================================================================
@pytest.mark.parametrize(
    "fname", [f for f in TURTLE_FILES if f != "donchian_swing.py"]
)
def test_a09_market_unit_atr_key_matches_turtle_block(fname):
    from tests.unit.engine._cycle382_support import strategy_class

    cls = strategy_class(TURTLE_FILES[fname])
    key = getattr(cls, "_MARKET_UNIT_ATR_KEY", None)
    assert key is not None, f"[Red] {cls.__name__}._MARKET_UNIT_ATR_KEY 없음"
    assert key in StrategyBase._SIZING_ATR_KEYS
    found = _turtle_block_keys(_read(_STRATS / fname), _TURTLE_BLOCK[fname])
    assert found, f"{fname} 터틀 블록 ATR 키 탐지 실패(탐지기 무효)"
    assert found == {key}, f"{fname} 터틀 블록 키 {found} ≠ _MARKET_UNIT_ATR_KEY {key!r}"


def test_a09_donchian_atr_key_still_valid():
    """donchian 은 `_turtle_buy_quantity` 가 cycle405 후속 L5 로 제거돼 위 교차검증
    대상에서 빠졌다(죽은 코드 — 운영 코드 호출처 0 확인). `_MARKET_UNIT_ATR_KEY` 자체는
    여전히 유효해야 한다 — 실사용처는 `_kk_design_lot`(R 기반 설계 랏)이고, 거기서는
    `info.get(self._MARKET_UNIT_ATR_KEY)` 처럼 속성 참조로 읽어 AST 리터럴 탐지기
    패턴에 걸리지 않는다(그래서 교체 대상이 없다)."""
    from tests.unit.engine._cycle382_support import strategy_class

    cls = strategy_class(TURTLE_FILES["donchian_swing.py"])
    key = getattr(cls, "_MARKET_UNIT_ATR_KEY", None)
    assert key is not None, f"[Red] {cls.__name__}._MARKET_UNIT_ATR_KEY 없음"
    assert key in StrategyBase._SIZING_ATR_KEYS


def test_a09_base_default_is_none():
    assert getattr(StrategyBase, "_MARKET_UNIT_ATR_KEY", "missing") is None, (
        "[Red] StrategyBase._MARKET_UNIT_ATR_KEY 기본값(None) 없음"
    )


# ===========================================================================
# A10 — calc 앞머리: _market_unit_sizing 1회 · 첫 문장 뒤 · 기존 사이징 앞 · 관문 계약 유지
# ===========================================================================
@pytest.mark.parametrize("fname", list(TURTLE_FILES))
def test_a10_calc_calls_market_unit_sizing_first(fname):
    src = _read(_STRATS / fname)
    fn = _func(src, "calc_buy_quantity")
    hits = _calls(fn, "_market_unit_sizing")
    assert len(hits) == 1, f"{fname} calc_buy_quantity 의 _market_unit_sizing 호출 {len(hits)}회"
    line = hits[0].lineno
    top_level = [s for s in fn.body if any(c is hits[0] for c in ast.walk(s))]
    assert top_level, f"{fname} _market_unit_sizing 가 calc 본문 최상위 문장이 아니다(분기 안에 숨었다)"
    assert fn.body[0].lineno < line, f"{fname} 첫 문장(가격 ≤ 0 가드)보다 앞"
    existing = [c.lineno for nm in ("_turtle_buy_quantity", "compute_unit_qty_guarded") for c in _calls(fn, nm)]
    existing += [
        n.lineno for n in ast.walk(fn)
        if isinstance(n, ast.Constant) and n.value in ("position_ratio", "sizing_mode")
    ]
    if fname == "donchian_swing.py":
        # cycle405 — donchian 사이징은 깡토식 설계 랏(헬퍼)이라 calc 본문에 옛 사이징 토큰이 없다.
        # 대신 시장 유닛 호출이 가격 가드 바로 다음 최상위 문장이어야 한다(첫 줄 규약).
        stmts = [b for b in fn.body
                 if not (isinstance(b, ast.Expr) and isinstance(getattr(b, "value", None), ast.Constant)
                         and isinstance(b.value.value, str))]          # docstring 제외
        assert stmts[1] is top_level[0], f"{fname} _market_unit_sizing 가 가격 가드 바로 다음이 아니다"
        assert all(line < m for m in existing), f"{fname} 기존 사이징 코드보다 뒤에 있다"
    else:
        assert existing and line < min(existing), f"{fname} 기존 사이징 코드보다 뒤에 있다"
    for n in ast.walk(fn):
        if isinstance(n, ast.Call):
            assert all(k.arg != "fraction" for k in n.keywords), f"{fname} fraction= (M11 · G-242-7)"
        if isinstance(n, ast.Return) and n.value is not None:
            if isinstance(n.value, ast.Constant) and n.value.value == 0:
                continue
            assert isinstance(n.value, ast.Call) and getattr(n.value.func, "attr", None) == "_apply_budget_limit", (
                f"{fname}:{n.lineno} 관문 미경유 return (A-GATE)"
            )


# ===========================================================================
# A11 — 신호 필터 1회 · 자리
# ===========================================================================
def _bought_add_lines(fn) -> list[int]:
    return [
        c.lineno for c in _calls(fn, "add")
        if isinstance(c.func, ast.Attribute) and ast.unparse(c.func.value).endswith("_bought_today")
    ]


def _filter_call(src: str, fname: str) -> tuple[ast.AST, ast.Call]:
    tree = ast.parse(src)
    hits = [(fn, c) for fn in ast.walk(tree) if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef))
            for c in _calls(fn, "_market_unit_blocks_entry")
            if fn.name in ("check_buy_signal", "_evaluate_vol_gate")]
    total = len(_calls(tree, "_market_unit_blocks_entry"))
    assert total == 1 and len(hits) == 1, f"{fname} 신호 필터 호출 {total}회(정확히 1회, 신호 함수 안)"
    return hits[0]


def _returns_none_under_if(fn, call) -> bool:
    for n in ast.walk(fn):
        if isinstance(n, ast.If) and any(c is call for c in ast.walk(n.test)):
            return any(
                isinstance(s, ast.Return) and s.value is not None and ast.unparse(s.value) == "Signal.NONE"
                for s in n.body
            )
    return False


@pytest.mark.parametrize("fname", ["kojiro.py", "donchian_swing.py"])
def test_a11_swing_filter_sits_right_before_buy_commit(fname):
    src = _read(_STRATS / fname)
    fn, call = _filter_call(src, fname)
    assert fn.name == "check_buy_signal"
    assert _returns_none_under_if(fn, call), f"{fname} 필터가 `if …: return Signal.NONE` 모양이 아니다"
    gate = _calls(fn, "_account_soft_gate_blocked")
    assert gate and gate[0].lineno < call.lineno
    commit = max(_bought_add_lines(fn))
    assert call.lineno < commit, f"{fname} 필터가 매수 확정 `_bought_today.add` 뒤(M18)"
    if fname == "kojiro.py":
        passes = [c.lineno for c in _calls(fn, "observe_gap")
                  if len(c.args) >= 2 and isinstance(c.args[1], ast.Constant) and c.args[1].value == "pass"]
        assert passes and passes[0] < call.lineno, "kojiro 필터가 `observe_gap(…,'pass')` 앞 — 갭 코호트가 흔들린다"
        for attr in ("_position_atr", "_position_sectors"):
            stamps = [n.lineno for n in ast.walk(fn) if isinstance(n, ast.Subscript)
                      and isinstance(n.ctx, ast.Store) and ast.unparse(n.value).endswith(attr)]
            assert stamps and call.lineno < min(stamps), f"kojiro 필터가 {attr} 스탬프 뒤"
    else:
        ext = [n.lineno for n in ast.walk(fn) if isinstance(n, ast.Constant) and isinstance(n.value, str)
               and "[donchian_extension_skip]" in n.value]
        assert ext and ext[0] < call.lineno, "donchian 필터가 추격 상한 블록 앞"
        stamps = [n.lineno for n in ast.walk(fn) if isinstance(n, ast.Subscript)
                  and isinstance(n.ctx, ast.Store) and ast.unparse(n.value).endswith("_breakout_high")]
        assert stamps and call.lineno < min(stamps), "donchian 필터가 `_breakout_high` 스탬프 뒤"


@pytest.mark.parametrize("fname", ["bull_flag_breakout.py", "vcp_breakout.py"])
def test_a11_breakout_filter_sits_in_vol_gate_before_latch_pop(fname):
    src = _read(_STRATS / fname)
    fn, call = _filter_call(src, fname)
    assert fn.name == "_evaluate_vol_gate", f"{fname} 필터는 `_evaluate_vol_gate` 안(`_prev_price` 갱신 뒤)"
    assert _returns_none_under_if(fn, call)
    reject = [n.lineno for n in ast.walk(fn) if isinstance(n, ast.Constant) and isinstance(n.value, str)
              and n.value == "reject_ext"]
    assert reject and reject[0] < call.lineno, f"{fname} 필터가 추격 상한 거부 블록 앞"
    age = [n.lineno for n in ast.walk(fn) if isinstance(n, ast.Assign)
           and any(isinstance(t, ast.Name) and t.id == "latch_age_sec" for t in n.targets)]
    assert age and call.lineno < min(age), f"{fname} 필터가 `latch_age_sec = 0` 뒤"
    pops = [c.lineno for c in _calls(fn, "pop") if ast.unparse(c.func.value).endswith("_vol_latch")]
    assert pops and call.lineno < min(pops), f"{fname} 필터가 `_vol_latch.pop` 뒤 — 래치를 해제한다"
    assert call.lineno < min(_bought_add_lines(fn))


# ===========================================================================
# A12 — 관문 본문 무변경 · DEFAULT_PARAMS · 카탈로그
# ===========================================================================
#: 🔁 cycle382 착수 시점(HEAD 9a0af9e3) `ast.get_source_segment` sha256. 시장 유닛은 관문 **앞**에서
#:   0 을 돌려줄 뿐 관문을 건드리지 않는다(명세 §5.4 · §9). 관문을 의도적으로 바꾸는 사이클이 값만 재핀한다.
_GATE_SHA = {
    "_apply_budget_limit": "fe40eea083f894925c93dabf538c4fe045624b9db4c1ea5fd75ed50a16a3ac09",
    "_fallback_one_share": "6795f4bf9dffb6c44eca8bc8c6f04250e6ed3a8822c153f1927ce0ff5ea7ae29",
    # cycle436(2026-10-10, 사용자 승인) — `sum(pending_buy_amounts.values())` 가
    # `self.state.total_pending_buy_amount()` 단일 진입점 호출로 바뀌었다(카드 E).
    # 순수 교체 — 계산 결과는 그대로다.
    "_calc_used_funds": "e56e749d32290033439a73e3c42291e392ad9c4302b4281b6f8ec427e2ca0936",
    "_apply_lot_units_cap": "993b6c0c59fdf183527fddcbb23423910f6f79527e2b1122433d2cf8b0d461a9",
    "_apply_ratio_notional_cap": "15fd15c74f8d9282751b095a89d0ded8de248e9bd5ea1dcb2c9f25fa30fa99a8",
}


@pytest.mark.parametrize("name", sorted(_GATE_SHA))
def test_a12_budget_gate_bodies_unchanged(name):
    src = _read(_SB)
    fns = [n for n in ast.walk(ast.parse(src))
           if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name]
    assert len(fns) == 1, f"{name} 정의 {len(fns)}개"
    seg = ast.get_source_segment(src, fns[0])
    assert hashlib.sha256(seg.encode("utf-8")).hexdigest() == _GATE_SHA[name], (
        f"{name} 본문이 바뀌었다 — cycle382 는 관문을 건드리지 않는다(allow_fallback 키워드 추가 금지)"
    )


@pytest.mark.parametrize("sid", sorted(TURTLE_FILES.values()))
def test_a12_turtle_defaults_are_shadow(sid):
    from tests.unit.engine._cycle382_support import strategy_class

    assert strategy_class(sid).DEFAULT_PARAMS.get("market_unit_mode") == "shadow"


@pytest.mark.parametrize("sid", ["momentum", "volatility_breakout", "long_tail_volatility"])
def test_a12_other_three_have_no_key(sid):
    from tests.unit.engine._cycle382_support import strategy_class

    assert "market_unit_mode" not in strategy_class(sid).DEFAULT_PARAMS


def test_a12_catalog_row():
    from src.engine import param_catalog as pc

    spec = pc.get_spec("market_unit_mode")
    assert spec is not None, "[Red] param_catalog 에 market_unit_mode 행 없음"
    assert spec.type == "enum" and spec.range_src == "enum"
    assert {c.value for c in spec.choices} == {"off", "shadow", "enforce"}
    assert spec.risk == "identity" and spec.auto_tunable is False
    # cycle403 — `_TURTLE4` 를 `_TURTLE_SIZED`(5전략, etf_trend 추가)로 개명.
    assert spec.applies_to == pc._TURTLE_SIZED
    assert spec.editable is True, "킬스위치 = PUT — 편집 가능해야 한다"
    assert "market_unit_mode" in pc.identity_keys()
    # 🔁 cycle384 재핀 — buy_paused 공통 파라미터(사용자 결정 09-27 「돈키언 신규매수 중지」) — 카탈로그 버전 cycle382.1 → cycle384.1.
    # 🔁 cycle399 재핀 — 공통 섀도 모드 shadow_mode(사용자 승인 10-02 R1) — 카탈로그 버전 cycle384.1 → cycle399.1.
    # 🔁 cycle403 재핀 — ETF 추세 전략(etf_trend) 신설 — 카탈로그 버전 cycle399.1 → cycle403.1.
    # 🔁 cycle405 재핀 — donchian 깡토식 청산·사이징 신규 7키 — 카탈로그 버전 cycle403.2 → cycle405.
    assert pc.CATALOG_VERSION == "cycle405"
