"""cycle399 Red — 공통 섀도 모드 `shadow_mode` 구조 봉인 (S01~S13).

명세 정본 = `_workspace/red/cycle399_shadow_mode.md` §2 · §3

| # | 봉인 |
|---|---|
| S01 | 전략 명부 파일마다 `Signal.BUY` 는 `return Signal.BUY` 로만, 그 Return 의 같은 문장 목록 앞쪽 형제에 섀도 관문 `if self._shadow_buy_intercepted(...): return Signal.NONE` 이 있고 그 사이에 다른 `return`/`raise` 가 없다 |
| S02 | 섀도 관문 호출 = 파일마다 정확히 1곳(= BUY 반환 수) · `check_buy_signal` 안 · src 의 그 밖 호출 0 |
| S03 | 관문은 앞 거름 뒤 — `_account_soft_gate_blocked` 와 (있으면) `_market_unit_blocks_entry` 가 섀도 관문보다 앞 줄 |
| S04 | 섀도 헬퍼 = 동기 · I/O 0 · 주문·예산·화면·켜짐 축 이름 0 |
| S05 | 문자열 `"shadow_mode"` = strategy_base 1 · 전략 명부 파일 각 1(`DEFAULT_PARAMS`) · param_catalog 1 · 그 밖 src 0 |
| S06 | `SHADOW_MODE_KEY` 참조 = 정의 + 읽는 함수 2곳(`shadow_mode_on` · `_shadow_buy_intercepted`)뿐 — 캐시 금지 |
| S07 | `shadow_mode` ∉ `PARAM_RANGES`·`INT_PARAMS`·`_CONSERVATIVE_KEYS` (런타임 + 소스 리터럴) |
| S08 | 전략 명부 = 등록 명부(`STRATEGY_MANIFEST`) · 명부 파일마다 `DEFAULT_PARAMS["shadow_mode"] = False` |
| S09 | 8영역 `strategy_registry.update_weights` 의 `enabled` 대입은 정확히 `weight > 0 or (was_enabled and StrategyBase.shadow_mode_on(s))` 하나 |
| S10 | 8영역(registry 제외)·`scheduler.py`·`boot_manager.py` 에 섀도 토큰 0 · registry 는 `shadow_mode_on` 1회 |
| S11 | `[shadow_buy]` 는 `logger.info` 로만 · `[shadow_mode_config]` 는 `logger.warning` 로만 · `write_log` 0 |
| S12 | 카탈로그 행(bool · identity · 8전략 · 자동튜닝 아님) · 118키(cycle403) · identity 19 · `cycle403.1` |
| S13 | 생성 픽스처(프론트·e2e)가 카탈로그를 따른다 |

스캔 규약(가드 설계 금기 2026-09-05) — `Path.read_text` + AST. `git grep`/`git ls-files` 금지, `ast.dump` sha 핀
금지(같은 인터프리터 안의 `ast.dump` **비교**는 무해 — S09).
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
REG = SRC / "engine" / "strategy_registry.py"
CATALOG = SRC / "engine" / "param_catalog.py"
RECO = SRC / "engine" / "recommendation_engine.py"
STRATEGY_DIR = census.STRATEGIES_DIR
STRATEGY_FILES = census.STRATEGY_FILES
KEY = "shadow_mode"
GATE = "_shadow_buy_intercepted"
PROBE = "shadow_mode_on"
HELPERS = (GATE, PROBE, "_emit_shadow_mode_config", "_emit_shadow_buy")
SHADOW_TOKENS = ("shadow_mode", "SHADOW_MODE_KEY", PROBE, GATE, "_shadow_logged", "shadow_buy")

UNTOUCHED = [
    SRC / "engine" / "risk.py",
    SRC / "engine" / "order_engine.py",
    SRC / "engine" / "session.py",
    SRC / "engine" / "scanner.py",
    SRC / "api" / "order.py",
    SRC / "engine" / "scheduler.py",
    SRC / "engine" / "boot_manager.py",
]
UNTOUCHED_DIRS = [SRC / "realtime", SRC / "auth"]


# ===========================================================================
# 공용
# ===========================================================================
def _tree(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"))


def _docstring_ids(tree: ast.AST) -> set[int]:
    out: set[int] = set()
    for n in ast.walk(tree):
        if isinstance(n, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = getattr(n, "body", [])
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
                    and isinstance(body[0].value.value, str):
                out.add(id(body[0].value))
    return out


def _fn(tree: ast.AST, name: str):
    for n in ast.walk(tree):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name:
            return n
    raise AssertionError(f"{name} 정의 없음")


def _is_signal(node: ast.AST, attr: str) -> bool:
    return isinstance(node, ast.Attribute) and node.attr == attr and \
        isinstance(node.value, ast.Name) and node.value.id == "Signal"


def _is_self_call(node: ast.AST, name: str) -> bool:
    return isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and \
        node.func.attr == name and isinstance(node.func.value, ast.Name) and node.func.value.id == "self"


def _is_shadow_if(stmt: ast.stmt) -> bool:
    return (
        isinstance(stmt, ast.If) and _is_self_call(stmt.test, GATE) and not stmt.orelse
        and len(stmt.body) == 1 and isinstance(stmt.body[0], ast.Return)
        and stmt.body[0].value is not None and _is_signal(stmt.body[0].value, "NONE")
    )


def _stmt_lists(tree: ast.AST):
    """(부모 노드, 문장 목록) 전부."""
    for n in ast.walk(tree):
        for fld in ("body", "orelse", "finalbody", "handlers"):
            v = getattr(n, fld, None)
            if isinstance(v, list) and v and isinstance(v[0], ast.stmt):
                yield n, v


def _src_files() -> list[Path]:
    return sorted(p for p in SRC.rglob("*.py") if "__pycache__" not in p.parts)


def _str_consts(path: Path, value: str) -> list[int]:
    tree = _tree(path)
    docs = _docstring_ids(tree)
    return [n.lineno for n in ast.walk(tree)
            if isinstance(n, ast.Constant) and n.value == value and id(n) not in docs]


# ===========================================================================
# S01 · S02 · S03 — 모든 BUY 반환이 섀도 관문을 지난다
# ===========================================================================
@pytest.mark.parametrize("fname", STRATEGY_FILES)
def test_s01_every_buy_return_is_preceded_by_shadow_gate(fname):
    tree = _tree(STRATEGY_DIR / fname)
    any_buy = [n for n in ast.walk(tree) if isinstance(n, ast.Attribute) and n.attr == "BUY"]
    assert all(_is_signal(n, "BUY") for n in any_buy), (
        f"{fname}: `Signal` 이 아닌 이름의 `.BUY` {[(n.lineno, ast.unparse(n)) for n in any_buy]} — "
        "별칭 import(`Signal as _S`)는 이 가드를 우회한다. 전략 파일은 `Signal` 이름 그대로 쓴다"
    )
    buys = [n for n in ast.walk(tree) if _is_signal(n, "BUY")]
    assert buys, f"{fname}: Signal.BUY 가 없다 — 탐지기 무효"
    returns = [n for n in ast.walk(tree) if isinstance(n, ast.Return) and n.value is not None
               and _is_signal(n.value, "BUY")]
    assert len(returns) == len(buys), (
        f"{fname}: Signal.BUY 가 `return Signal.BUY` 밖에서 쓰였다 — 변수에 담아 돌려주면 섀도 관문을 우회한다"
    )
    for ret in returns:
        found = False
        for _parent, lst in _stmt_lists(tree):
            if not any(s is ret for s in lst):
                continue
            idx = next(i for i, s in enumerate(lst) if s is ret)
            gates = [i for i in range(idx) if _is_shadow_if(lst[i])]
            assert gates, (
                f"[Red] {fname}:{ret.lineno} `return Signal.BUY` 앞(같은 블록)에 "
                f"`if self.{GATE}(...): return Signal.NONE` 이 없다 — 섀도 전략이 실제로 산다"
            )
            g = gates[-1]
            between = [x for s in lst[g + 1:idx] for x in ast.walk(s)
                       if isinstance(x, (ast.Return, ast.Raise))]
            assert not between, (
                f"{fname}:{ret.lineno} 섀도 관문과 BUY 반환 사이에 return/raise "
                f"{[x.lineno for x in between]} — 섀도는 마지막 거름 뒤여야 기록=실전 판단이 된다"
            )
            found = True
        assert found, f"{fname}:{ret.lineno} 문장 목록 탐색 실패"


def _funcs(tree: ast.AST) -> list:
    return [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]


def _owner(tree: ast.AST, node: ast.AST):
    """`node` 를 품은 가장 안쪽 함수."""
    best = None
    for fn in _funcs(tree):
        if any(x is node for x in ast.walk(fn)):
            if best is None or fn.lineno >= best.lineno:
                best = fn
    return best


@pytest.mark.parametrize("fname", STRATEGY_FILES)
def test_s02_shadow_gate_called_once_in_the_buy_returning_function(fname):
    tree = _tree(STRATEGY_DIR / fname)
    calls = [n for n in ast.walk(tree) if _is_self_call(n, GATE)]
    rets = [n for n in ast.walk(tree) if isinstance(n, ast.Return) and n.value is not None
            and _is_signal(n.value, "BUY")]
    assert len(calls) == len(rets) == 1, (
        f"[Red] {fname}: 섀도 관문 호출 {len(calls)}곳 · BUY 반환 {len(rets)}곳 — 둘 다 1곳이어야 한다"
    )
    owner = _owner(tree, calls[0])
    assert owner is _owner(tree, rets[0]), f"{fname}: 섀도 관문과 BUY 반환이 다른 함수에 있다"
    cbs = _fn(tree, "check_buy_signal")
    if owner is not cbs:
        # BFB·VCP — BUY 는 `check_buy_signal` 이 부르는 헬퍼 안에서 난다. 그 헬퍼는
        # `check_buy_signal` 에서만 불려야 앞 관문(종목상태·buy_paused·계좌 SOFT)을 지난다.
        callers = {_owner(tree, n).name for n in ast.walk(tree) if _is_self_call(n, owner.name)}
        assert callers == {"check_buy_signal"}, f"{fname}: {owner.name} 를 부르는 곳 {callers}"


def test_s02_shadow_gate_not_called_elsewhere_in_src():
    allowed = {STRATEGY_DIR / f for f in STRATEGY_FILES}
    hits = []
    for p in _src_files():
        if p in allowed:
            continue
        for n in ast.walk(_tree(p)):
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == GATE:
                hits.append(f"{p.relative_to(ROOT)}:{n.lineno}")
    assert hits == [], f"섀도 관문이 전략 밖에서 불린다: {hits}"


@pytest.mark.parametrize("fname", STRATEGY_FILES)
def test_s03_shadow_gate_after_soft_gate_and_market_unit(fname):
    tree = _tree(STRATEGY_DIR / fname)
    gate = [n for n in ast.walk(tree) if _is_self_call(n, GATE)]
    assert gate, f"[Red] {fname}: 섀도 관문 없음"
    owner = _owner(tree, gate[0])
    cbs = _fn(tree, "check_buy_signal")
    soft = [n.lineno for n in ast.walk(cbs) if _is_self_call(n, "_account_soft_gate_blocked")]
    assert soft, f"{fname}: check_buy_signal 에 계좌 SOFT·buy_paused 관문이 없다"
    if owner is cbs:
        assert max(soft) < gate[0].lineno, f"{fname}: 계좌 SOFT·buy_paused 관문이 섀도보다 앞이 아니다"
    else:
        into = [n.lineno for n in ast.walk(cbs) if _is_self_call(n, owner.name)]
        assert into and max(soft) < min(into), (
            f"{fname}: {owner.name} 진입이 계좌 SOFT·buy_paused 관문보다 앞이다"
        )
    mu = [n.lineno for n in ast.walk(owner) if _is_self_call(n, "_market_unit_blocks_entry")]
    if mu:
        assert max(mu) < gate[0].lineno, f"{fname}: 시장 유닛 거름이 섀도 관문보다 뒤 — 거른 종목이 섀도 기록이 된다"


# ===========================================================================
# S04 — 헬퍼 순수성
# ===========================================================================
_FORBIDDEN_NAMES = {
    "write_log", "create_task", "ensure_future", "pg", "calc_buy_quantity", "_apply_budget_limit",
    "pending_buys", "pending_buy_amounts", "total_investment", "buy_signals", "_bought_today",
    "buy_disabled", "enabled", "weight", "signal_count_today", "execute_buy",
}


@pytest.mark.parametrize("name", HELPERS)
def test_s04_helpers_sync_and_side_effect_free(name):
    fn = _fn(_tree(SB), name)
    assert isinstance(fn, ast.FunctionDef), f"[Red] {name} 는 동기 함수여야 한다(A-ATOMIC 전제)"
    bad = []
    for n in ast.walk(fn):
        if isinstance(n, (ast.Await, ast.AsyncFor, ast.AsyncWith)):
            bad.append(f"await@{n.lineno}")
        s = n.id if isinstance(n, ast.Name) else n.attr if isinstance(n, ast.Attribute) else None
        if s and (s in _FORBIDDEN_NAMES or s.startswith("kis_") or s.startswith("fetch_")):
            bad.append(f"{s}@{n.lineno}")
    assert bad == [], f"{name}: 주문·예산·화면·켜짐 축 또는 I/O 에 닿는다 {bad}"


# ===========================================================================
# S05 · S06 — 키 문자열 · 상수 참조
# ===========================================================================
def test_s05_key_string_appears_only_where_expected():
    expected = {SB: 1, CATALOG: 1, **{STRATEGY_DIR / f: 1 for f in STRATEGY_FILES}}
    got = {}
    for p in _src_files():
        n = len(_str_consts(p, KEY))
        if n or p in expected:
            got[p] = n
    assert got == expected, (
        "[Red] \"shadow_mode\" 문자열 위치가 다르다 — "
        + str({str(k.relative_to(ROOT)): v for k, v in got.items()})
    )


def test_s06_key_constant_referenced_only_by_two_readers():
    tree = _tree(SB)
    readers = set()
    for fn in ast.walk(tree):
        if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if any(isinstance(n, ast.Name) and n.id == "SHADOW_MODE_KEY" for n in ast.walk(fn)):
                readers.add(fn.name)
    assert readers == {PROBE, GATE}, f"[Red] SHADOW_MODE_KEY 를 읽는 함수 {readers}"
    stores = [n for n in ast.walk(tree) if isinstance(n, ast.Attribute) and isinstance(n.ctx, ast.Store)
              and n.attr.startswith("_shadow")]
    assert [n.attr for n in stores] == ["_shadow_logged"], (
        f"섀도 값 캐시 금지 — self._shadow* 대입은 __init__ 의 cap 하나: {[n.attr for n in stores]}"
    )


# ===========================================================================
# S07 — AI 자문 경로 편입 금지
# ===========================================================================
def _named_literal_str_keys(tree: ast.Module, name: str) -> set[str]:
    out: set[str] = set()
    for n in ast.walk(tree):
        if isinstance(n, (ast.Assign, ast.AnnAssign)):
            targets = n.targets if isinstance(n, ast.Assign) else [n.target]
            if any(isinstance(t, ast.Name) and t.id == name for t in targets) and n.value is not None:
                for c in ast.walk(n.value):
                    if isinstance(c, ast.Constant) and isinstance(c.value, str):
                        out.add(c.value)
    return out


def test_s07_not_in_param_ranges_int_params_or_auto_apply():
    from src.engine import recommendation_engine as rec

    assert KEY not in rec.PARAM_RANGES and KEY not in rec.INT_PARAMS and KEY not in rec._CONSERVATIVE_KEYS
    tree = _tree(RECO)
    for name in ("PARAM_RANGES", "INT_PARAMS", "_CONSERVATIVE_KEYS"):
        assert KEY not in _named_literal_str_keys(tree, name)
    assert "volume_multiplier" in _named_literal_str_keys(tree, "PARAM_RANGES"), "탐지기 무효"


# ===========================================================================
# S08 — 명부 전수
# ===========================================================================
def test_s08_census_equals_registration_manifest():
    from src.engine.strategy_manifest import STRATEGY_MANIFEST

    assert {e.strategy_id for e in STRATEGY_MANIFEST} == set(census.STRATEGY_IDS), (
        "등록 명부와 전략 파일 명부가 다르다 — 섀도 가드가 등록 전략 하나를 못 본다"
    )


#: cycle403 — ETF 추세(etf_trend)만 섀도 시작(S1, 비중 0 과 이중 안전) 명시 예외(L3).
_SHADOW_DEFAULT_TRUE_EXCEPTIONS = frozenset({"etf_trend.py"})
_SHADOW_DEFAULT_TRUE_EXCEPTIONS_BY_SID = frozenset({"etf_trend"})


def _shadow_mode_literal(fname: str):
    tree = _tree(STRATEGY_DIR / fname)
    found = None
    for n in ast.walk(tree):
        if isinstance(n, (ast.Assign, ast.AnnAssign)):
            targets = n.targets if isinstance(n, ast.Assign) else [n.target]
            if any(isinstance(t, ast.Name) and t.id == "DEFAULT_PARAMS" for t in targets) \
                    and isinstance(n.value, ast.Dict):
                for k, v in zip(n.value.keys, n.value.values):
                    if isinstance(k, ast.Constant) and k.value == KEY:
                        found = v
    return found


@pytest.mark.parametrize("fname", [f for f in STRATEGY_FILES if f not in _SHADOW_DEFAULT_TRUE_EXCEPTIONS])
def test_s08_default_params_has_shadow_mode_false(fname):
    found = _shadow_mode_literal(fname)
    assert found is not None, f"[Red] {fname}: DEFAULT_PARAMS 에 \"shadow_mode\" 없음"
    assert isinstance(found, ast.Constant) and found.value is False, f"{fname}: 기본값이 False 리터럴이 아니다"


@pytest.mark.parametrize("fname", sorted(_SHADOW_DEFAULT_TRUE_EXCEPTIONS))
def test_s08_shadow_default_true_exceptions_are_explicit(fname):
    """cycle403 — etf_trend 만 `shadow_mode=True` 명시 예외(S1 섀도 시작, L3)."""
    found = _shadow_mode_literal(fname)
    assert found is not None, f"[Red] {fname}: DEFAULT_PARAMS 에 \"shadow_mode\" 없음"
    assert isinstance(found, ast.Constant) and found.value is True, f"{fname}: 기본값이 True 리터럴이 아니다"


# ===========================================================================
# S09 · S10 — 8영역 한 줄 + 무접촉
# ===========================================================================
def test_s09_update_weights_single_enabled_assignment():
    fn = _fn(_tree(REG), "update_weights")
    assigns = [n for n in ast.walk(fn) if isinstance(n, ast.Assign)
               and any(isinstance(t, ast.Attribute) and t.attr == "enabled" for t in n.targets)]
    assert len(assigns) == 1, f"enabled 대입 {len(assigns)}곳"
    want = ast.parse("weight > 0 or (was_enabled and StrategyBase.shadow_mode_on(s))", mode="eval").body
    assert ast.dump(assigns[0].value) == ast.dump(want), (
        "[Red] update_weights 의 enabled 대입이 승인된 한 줄과 다르다 — "
        + ast.unparse(assigns[0].value)
    )
    pre = [n for n in ast.walk(fn) if isinstance(n, ast.Assign)
           and any(isinstance(t, ast.Name) and t.id == "was_enabled" for t in n.targets)]
    assert len(pre) == 1 and pre[0].lineno < assigns[0].lineno, "was_enabled 는 대입 전에 읽어야 한다"


def _tokens(path: Path) -> list[tuple[str, int]]:
    tree = _tree(path)
    docs = _docstring_ids(tree)
    out = []
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
        elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            s = n.name
        if s and any(t in s for t in SHADOW_TOKENS):
            out.append((s, getattr(n, "lineno", 0)))
    return out


def test_s10_untouched_areas_have_no_shadow_tokens():
    files = list(UNTOUCHED) + [p for d in UNTOUCHED_DIRS for p in sorted(d.rglob("*.py"))]
    assert len(files) >= 10, "탐지기 무효 — 대상 파일 목록"
    hits = [f"{p.relative_to(ROOT)}:{ln}:{s}" for p in files for s, ln in _tokens(p)]
    assert hits == [], f"8영역·scheduler·boot_manager 가 섀도를 안다: {hits}"


def test_s10_registry_knows_shadow_only_once():
    toks = _tokens(REG)
    assert [s for s, _ in toks] == [PROBE], f"[Red] strategy_registry 섀도 토큰 {toks} — 승인 범위는 한 줄"


# ===========================================================================
# S11 — 마커 수준 · write_log 0
# ===========================================================================
def _log_calls(fn) -> list[tuple[str, str]]:
    out = []
    for n in ast.walk(fn):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and \
                isinstance(n.func.value, ast.Name) and n.func.value.id == "logger" and n.args and \
                isinstance(n.args[0], ast.Constant) and isinstance(n.args[0].value, str):
            out.append((n.func.attr, n.args[0].value))
    return out


def test_s11_marker_levels():
    tree = _tree(SB)
    buy = [(lvl, m) for lvl, m in _log_calls(_fn(tree, "_emit_shadow_buy")) if m.startswith("[shadow_buy]")]
    cfg = [(lvl, m) for lvl, m in _log_calls(_fn(tree, "_emit_shadow_mode_config"))
           if m.startswith("[shadow_mode_config]")]
    assert buy and {lvl for lvl, _ in buy} == {"info"}, f"[shadow_buy] 수준 {buy}"
    assert cfg and {lvl for lvl, _ in cfg} == {"warning"}, f"[shadow_mode_config] 수준 {cfg}"
    for name in HELPERS:
        assert not any(isinstance(n, ast.Name) and n.id == "write_log" for n in ast.walk(_fn(tree, name)))


# ===========================================================================
# S12 · S13 — 카탈로그 · 생성 픽스처
# ===========================================================================
def test_s12_catalog_row_and_counts():
    from src.engine import param_catalog as pc

    spec = pc.get_spec(KEY)
    assert spec is not None, "[Red] param_catalog 에 shadow_mode 행 없음 — PUT 이 unknown_key 422"
    assert spec.type == "bool" and spec.range_src == "enum"
    assert (spec.min, spec.max, spec.step) == (None, None, None)
    assert spec.editable is True and spec.risk == "identity"
    assert spec.auto_tunable is False and spec.deprecated is False
    assert spec.group == "entry"
    assert tuple(spec.applies_to) == tuple(pc.STRATEGY_IDS)
    for word in ("신규 매수", "손절", "주문"):
        assert word in spec.help, f"도움말에 「{word}」 없음"
    assert KEY in pc.identity_keys()
    assert len(pc.PARAM_SPECS) == 118 and len(pc.SPEC_BY_KEY) == 118
    assert len(pc.identity_keys()) == 19
    # 🔁 cycle403 재핀 — ETF 추세 전략(etf_trend) 신설, 신규 키 12개(atr_band_period 는 MED-3 에서 제거) — cycle399.1 → cycle403.1.
    assert pc.CATALOG_VERSION == "cycle403.2"


_FIXTURES = (
    ROOT / "frontend" / "src" / "test" / "fixtures" / "paramSchema.fixture.ts",
    ROOT / "e2e" / "fixtures" / "param-schema.fixture.ts",
)
_MARK = "export const PARAM_SCHEMA_FIXTURE: ParamSchemaData = "


def _fixture_json(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    body = text.split(_MARK, 1)[1]
    end = body.index("\n}\n") + 2
    return json.loads(body[:end])


def _generator():
    gen = ROOT / "tools" / "test_fixtures" / "gen_param_schema_fixture.py"
    spec = importlib.util.spec_from_file_location("_gen_param_schema_fixture_c399", gen)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.parametrize("path", _FIXTURES, ids=["frontend", "e2e"])
def test_s13_generated_fixture_carries_shadow_mode(path):
    from src.engine import param_catalog as pc

    data = _fixture_json(path)
    assert data["catalog_version"] == pc.CATALOG_VERSION, f"{path.name}: 픽스처 미재생성"
    rows = [p for p in data["params"] if p["key"] == KEY]
    assert len(rows) == 1, f"[Red] {path.name}: shadow_mode 스펙 행 {len(rows)}"
    assert rows[0] == _generator().spec_to_json(pc.get_spec(KEY)), "손으로 고친 픽스처"
    for s in data["strategies"]:
        if s["strategy_id"] in _SHADOW_DEFAULT_TRUE_EXCEPTIONS_BY_SID:
            assert s["defaults"][KEY] is True and s["params"][KEY] is True, s["strategy_id"]
            continue
        assert s["defaults"][KEY] is False and s["params"][KEY] is False, s["strategy_id"]
