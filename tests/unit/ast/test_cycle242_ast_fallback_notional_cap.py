"""cycle242 Red (AST) — 랏당 최대 유닛 상한 `max_lot_units` 구조 계약 봉인.

명세 §4.2. 행위 테스트로는 잡히지 않는 **구조적 계약**만 정적으로 고정한다.

- G-242-1 `max_lot_units` ∉ PARAM_RANGES/INT_PARAMS (런타임 dict + 소스 리터럴 이중).
          ⚠️ 종전 터틀 키 6종은 기계 가드 없이 문서 주장뿐이었다 — 이 가드가 정본.
- G-242-2 A-PURE 확장 — 신규 헬퍼 6 + 기존 관측기 4 전부 `await`/DB/HTTP 0.
          함수 부재 = FAIL (헬퍼로 빼면서 가드를 비우는 우회 차단).
- G-242-3 관문 분기 순서 = 폴백 → 잔여 클램프 → **캡** → 관측 → return.
          캡 결과는 `final` 에 대입되고 호출은 정확히 1회.
- G-242-4 캡 본체 = `sizing_mode == "turtle"` 게이트 + `compute_unit_qty(fraction=)`
          재사용(새 수식 금지) + 외곽 `except Exception`(fail-open).
- G-242-5 peek → 로그 → mark (cycle226 D-3 / cycle233 F4). `_emit_budget_clamp`
          동행 시정 포함.
- G-242-6 기본값 동치 — 4 터틀 전략 리터럴 == `_MAX_LOT_UNITS_DEFAULT`, 비터틀 3전략 부재,
          하한 1.0 / 상한 20.0.
- G-242-7 캡 로직은 관문 안에만 — 전략 파일 사이징 함수에 `max_lot_units`/`fraction=` 토큰 0.
- G-242-8 `_resolve_sizing_atr` read-only + ATR 키 집합이 터틀 블록이 읽는 키와 동일.
- G-242-9 마커 3종 문자열 존재 + emit 사이트가 `Try` 하위 + `write_log` 이중 INSERT 0.

## 라운드 1 (tester 적대적 검증 확증 결함 시정, 2026-09-03) 추가분

- G-242-10 `_emit_fallback_cap_clamped`(신규, 결함 #4 시정)도 A-PURE(G-242-2)·
          peek→log→mark(G-242-5)·`Try` 하위 로그(G-242-9 동형)·마커 문자열 존재를
          같은 강도로 받는다 — 새 헬퍼가 가드망 밖에서 태어나지 않게.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

from src.engine import recommendation_engine as rec_mod
from src.engine import strategy_base as sb_mod
from src.engine.strategy_base import StrategyBase

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parents[3]
_STRATEGY_DIR = _ROOT / "src" / "engine" / "strategies"
_RECO = _ROOT / "src" / "engine" / "recommendation_engine.py"
_SB = _ROOT / "src" / "engine" / "strategy_base.py"

GATE = "_apply_budget_limit"
CAP = "_apply_lot_units_cap"

TURTLE_FILES = {
    "donchian_swing.py": "_turtle_buy_quantity",
    "kojiro.py": "calc_buy_quantity",
    "vcp_breakout.py": "_turtle_buy_quantity",
    "bull_flag_breakout.py": "_turtle_buy_quantity",
}
NON_TURTLE_FILES = [
    "momentum.py",
    "volatility_breakout.py",
    "long_tail_volatility.py",
]
STRATEGY_FILES = list(TURTLE_FILES) + NON_TURTLE_FILES

_CAP_MARKERS = (
    "[fallback_notional_capped]",
    "[fallback_cap_skipped]",
    "[fallback_cap_config]",
    "[fallback_cap_clamped]",   # 라운드 1 — 결함 #4 시정 (G-242-10)
)
_EMIT_FUNCS = (
    "_emit_fallback_notional_capped",
    "_emit_fallback_cap_skipped",
    "_emit_fallback_cap_config",
    "_emit_oversized_fallback",
    "_emit_budget_clamp",
    "_emit_fallback_cap_clamped",   # 라운드 1 — 결함 #4 시정 (G-242-10)
)
_PURE_FUNCS = (
    GATE,
    CAP,
    "_read_max_lot_units",
    "_resolve_sizing_atr",
    "_emit_fallback_notional_capped",
    "_emit_fallback_cap_skipped",
    "_emit_fallback_cap_config",
    "_fallback_one_share",
    "_emit_oversized_fallback",
    "_emit_budget_clamp",
    "_emit_fallback_cap_clamped",         # 라운드 1 — 결함 #4 시정 (G-242-10)
    "_describe_lot_cap_diagnostics",      # 라운드 1 — 결함 #3 시정 (G-242-10)
)


# ---------------------------------------------------------------------------
# 헬퍼
# ---------------------------------------------------------------------------
def _func_node(source: str, name: str) -> ast.AST:
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    raise AssertionError(f"{name} 함수를 찾지 못했습니다 (cycle242 미구현 또는 개명)")


def _sb_source() -> str:
    return inspect.getsource(StrategyBase)


def _strategy_src(filename: str) -> str:
    return (_STRATEGY_DIR / filename).read_text(encoding="utf-8")


def _collect_named_literal_str_keys(src: str, name: str) -> list[str]:
    """`name = {...}` (Assign/AnnAssign) 할당의 dict/set 리터럴 str 키 (cycle212 답습)."""
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
            for k in value.keys:
                if isinstance(k, ast.Constant) and isinstance(k.value, str):
                    keys.append(k.value)
        elif isinstance(value, ast.Set):
            for e in value.elts:
                if isinstance(e, ast.Constant) and isinstance(e.value, str):
                    keys.append(e.value)
    return keys


def _default_params_literal(filename: str) -> dict:
    tree = ast.parse(_strategy_src(filename))
    out: dict = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        for stmt in node.body:
            if not (
                isinstance(stmt, ast.Assign)
                and any(getattr(t, "id", "") == "DEFAULT_PARAMS" for t in stmt.targets)
                and isinstance(stmt.value, ast.Dict)
            ):
                continue
            for k, v in zip(stmt.value.keys, stmt.value.values):
                key = getattr(k, "value", None)
                if not isinstance(key, str):
                    continue
                try:
                    out[key] = ast.literal_eval(v)
                except Exception:
                    out[key] = None
    return out


def _calls_named(fn: ast.AST, name: str) -> list[ast.Call]:
    hits = []
    for node in ast.walk(fn):
        if isinstance(node, ast.Call):
            fname = getattr(node.func, "attr", None) or getattr(node.func, "id", None)
            if fname == name:
                hits.append(node)
    return hits


# ---------------------------------------------------------------------------
# G-242-1 — AI 자문 화이트리스트 편입 금지
# ---------------------------------------------------------------------------
def test_g242_1_runtime_param_ranges_excludes_max_lot_units():
    assert "max_lot_units" not in rec_mod.PARAM_RANGES, (
        "max_lot_units 는 리스크 정체성 상수 — AI 자문이 매일 밤 흔들면 안 된다"
    )
    assert "max_lot_units" not in rec_mod.INT_PARAMS


def test_g242_1_source_literals_exclude_max_lot_units():
    src = _RECO.read_text(encoding="utf-8")
    for name in ("PARAM_RANGES", "INT_PARAMS"):
        keys = _collect_named_literal_str_keys(src, name)
        assert keys, f"{name} 리터럴 파싱 실패 (탐지기 무효)"
        assert "max_lot_units" not in keys, (
            f"{name} 리터럴에 'max_lot_units' 편입 금지"
        )


def test_g242_1_detector_self_test():
    """탐지기 self-test — 실제 존재하는 키는 검출된다 (공허한 PASS 차단)."""
    src = _RECO.read_text(encoding="utf-8")
    assert "volume_multiplier" in _collect_named_literal_str_keys(src, "PARAM_RANGES")
    assert "long_ma_period" in _collect_named_literal_str_keys(src, "INT_PARAMS")


# ---------------------------------------------------------------------------
# G-242-2 — A-PURE 확장 (신규 헬퍼 포함 전 함수 await/DB/HTTP 0)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("name", _PURE_FUNCS)
def test_g242_2_gate_helpers_are_pure_sync(name):
    src = _sb_source()
    fn = _func_node(src, name)  # 부재 = FAIL (가드 우회 차단)

    assert not [n for n in ast.walk(fn) if isinstance(n, ast.Await)], (
        f"{name} 안에 await 가 있습니다 — execute_buy 원자성 파괴 (A-ATOMIC 전제)"
    )
    forbidden = ("src.db", "httpx", "requests", "asyncio", "aiohttp")
    for node in ast.walk(fn):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert not alias.name.startswith(forbidden), (
                    f"{name} 금지 import: {alias.name}"
                )
        elif isinstance(node, ast.ImportFrom):
            assert not (node.module or "").startswith(forbidden), (
                f"{name} 금지 import: {node.module}"
            )


# ---------------------------------------------------------------------------
# G-242-3 — 관문 분기 순서 + 캡 결과 대입
# ---------------------------------------------------------------------------
def test_g242_3_gate_branch_order_and_assignment():
    src = _sb_source()
    fn = _func_node(src, GATE)

    fb = _calls_named(fn, "_fallback_one_share")
    clamp = _calls_named(fn, "_emit_budget_clamp")
    cap = _calls_named(fn, CAP)
    over = _calls_named(fn, "_emit_oversized_fallback")
    assert fb and clamp and over, "관문의 기존 호출 3종이 사라졌습니다"
    assert len(cap) == 1, (
        f"{CAP} 호출은 정확히 1회여야 합니다 (실제 {len(cap)}) — 중복/누락 모두 계약 위반"
    )

    assert min(fb_.lineno for fb_ in fb) < min(c.lineno for c in clamp) < cap[0].lineno, (
        "캡이 폴백/잔여 클램프보다 앞에 있습니다 — 스코프 ii 계약 위반"
    )
    assert cap[0].lineno < min(o.lineno for o in over), (
        "캡이 `[oversized_fallback]` 관측보다 뒤에 있습니다 — 관측기가 캡 이전 수량을 재게 됩니다"
    )
    returns = [n for n in ast.walk(fn) if isinstance(n, ast.Return)]
    assert max(r.lineno for r in returns) > cap[0].lineno

    assigned = [
        n for n in ast.walk(fn)
        if isinstance(n, ast.Assign)
        and isinstance(n.value, ast.Call)
        and getattr(n.value.func, "attr", None) == CAP
        and any(isinstance(t, ast.Name) and t.id == "final" for t in n.targets)
    ]
    assert assigned, f"{CAP} 결과가 `final` 에 대입되지 않았습니다 (호출만 하고 버림)"


# ---------------------------------------------------------------------------
# G-242-4 — 캡 본체 구조 (turtle 게이트 · compute_unit_qty 재사용 · fail-open try)
# ---------------------------------------------------------------------------
def test_g242_4_cap_body_structure():
    src = _sb_source()
    fn = _func_node(src, CAP)

    turtle_literals = [
        n for n in ast.walk(fn)
        if isinstance(n, ast.Constant) and n.value == "turtle"
    ]
    assert turtle_literals, (
        "`sizing_mode == \"turtle\"` 게이트가 없습니다 — 고정%손절 5전략까지 잘립니다"
    )
    compares = [
        n for n in ast.walk(fn)
        if isinstance(n, ast.Compare)
        and any(isinstance(c, ast.Constant) and c.value == "turtle" for c in n.comparators)
    ]
    assert compares, "turtle 리터럴이 비교식에 쓰이지 않았습니다"

    unit_calls = _calls_named(fn, "compute_unit_qty")
    assert len(unit_calls) == 1, (
        f"`compute_unit_qty` 호출은 정확히 1회 (실제 {len(unit_calls)}) — 새 수식 금지"
    )
    assert any(kw.arg == "fraction" for kw in unit_calls[0].keywords), (
        "`compute_unit_qty(..., fraction=K)` 로 재사용해야 합니다"
    )

    assert not _calls_named(fn, "floor"), "유닛 수량을 직접 floor 로 계산하고 있습니다"
    assert not _calls_named(fn, "round"), "유닛 수량을 round 로 계산하면 상향 반올림 사고"
    assert not [
        n for n in ast.walk(fn)
        if isinstance(n, ast.BinOp) and isinstance(n.op, ast.FloorDiv)
    ], "유닛 수량을 `//` 로 직접 계산하고 있습니다 (compute_unit_qty 재사용 규약 위반)"

    tries = [n for n in ast.walk(fn) if isinstance(n, ast.Try)]
    broad = [
        t for t in tries
        if any(
            h.type is None
            or (isinstance(h.type, ast.Name) and h.type.id == "Exception")
            for h in t.handlers
        )
    ]
    assert broad, f"{CAP} 에 `except Exception` fail-open 이 없습니다"
    guarded = any(unit_calls[0] in list(ast.walk(t)) for t in broad)
    assert guarded, "`compute_unit_qty` 호출이 fail-open try 밖에 있습니다"

    assert _calls_named(fn, "_resolve_sizing_atr"), (
        "캡 ATR 을 사이징과 같은 소스에서 읽지 않습니다"
    )


# ---------------------------------------------------------------------------
# G-242-5 — peek → 로그 → mark
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("name", _EMIT_FUNCS)
def test_g242_5_mark_emitted_after_logger(name):
    src = _sb_source()
    fn = _func_node(src, name)

    should = _calls_named(fn, "should_emit")
    mark = _calls_named(fn, "mark_emitted")
    log = [
        n for n in ast.walk(fn)
        if isinstance(n, ast.Call)
        and getattr(n.func, "attr", None) in ("info", "warning", "error")
        and getattr(getattr(n.func, "value", None), "id", None) == "logger"
    ]
    assert should, f"{name} 에 should_emit(peek) 가 없습니다"
    assert mark, f"{name} 에 mark_emitted 가 없습니다"
    assert log, f"{name} 에 logger 호출이 없습니다"

    # `max`/`min` 을 뒤집어 쓰면 "로그 앞에 mark 를 하나 더 끼워넣는" 뮤테이션이
    # 뒤쪽 정상 mark 에 가려 통과한다 — **모든** mark 가 **모든** 로그보다 뒤여야 한다.
    assert max(s.lineno for s in should) < min(l.lineno for l in log), (
        f"{name}: should_emit(peek) 이 로그보다 뒤에 있습니다"
    )
    assert min(m.lineno for m in mark) > max(l.lineno for l in log), (
        f"{name}: mark_emitted 가 로그보다 앞에 있습니다 — 로그 자기실패가 "
        "그날 관측을 통째로 지웁니다 (cycle226 D-3)"
    )


# ---------------------------------------------------------------------------
# G-242-6 — 기본값 동치 / 스코프 / 클램프 경계
# ---------------------------------------------------------------------------
def test_g242_6_module_constants():
    assert sb_mod._MAX_LOT_UNITS_MIN == pytest.approx(1.0), (
        "하한 1.0 은 T 경로(정상 터틀 랏 ≤ u*) 무접촉의 수학적 전제다"
    )
    assert sb_mod._MAX_LOT_UNITS_MAX == pytest.approx(20.0)
    assert (
        sb_mod._MAX_LOT_UNITS_MIN
        <= sb_mod._MAX_LOT_UNITS_DEFAULT
        <= sb_mod._MAX_LOT_UNITS_MAX
    )
    assert sb_mod._MAX_LOT_UNITS_DEFAULT == pytest.approx(2.0)


@pytest.mark.parametrize("filename", sorted(TURTLE_FILES))
def test_g242_6_turtle_defaults_match_module_constant(filename):
    params = _default_params_literal(filename)
    assert "max_lot_units" in params, (
        f"{filename} DEFAULT_PARAMS 에 max_lot_units 가 없습니다 — DB 병합/롤백 다이얼 전제"
    )
    assert params["max_lot_units"] == pytest.approx(sb_mod._MAX_LOT_UNITS_DEFAULT)


@pytest.mark.parametrize("filename", NON_TURTLE_FILES)
def test_g242_6_fixed_stop_defaults_absent(filename):
    params = _default_params_literal(filename)
    assert "max_lot_units" not in params, (
        f"{filename} 에 키가 있으면 '적용 대상'으로 오독된다 (고정%손절 = 범위 밖)"
    )


# ---------------------------------------------------------------------------
# G-242-7 — 캡 로직 전략 누출 금지 + A-GATE 재확인
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("filename", STRATEGY_FILES)
def test_g242_7_no_cap_tokens_in_strategy_sizing(filename):
    src = _strategy_src(filename)
    tree = ast.parse(src)
    targets = ["calc_buy_quantity"]
    if filename in TURTLE_FILES:
        targets.append(TURTLE_FILES[filename])
    for name in set(targets):
        try:
            fn = _func_node(src, name)
        except AssertionError:
            continue
        for node in ast.walk(fn):
            if isinstance(node, ast.Constant) and node.value == "max_lot_units":
                pytest.fail(f"{filename}::{name} 에 max_lot_units 토큰 — 캡은 관문 안에만")
            if isinstance(node, ast.Call):
                for kw in node.keywords:
                    assert kw.arg != "fraction", (
                        f"{filename}::{name} 에 fraction= kwarg — 캡 로직 누출"
                    )
    # A-GATE 재확인 (관문 우회 return 0건)
    fn = _func_node(src, "calc_buy_quantity")
    gated = 0
    for node in ast.walk(fn):
        if not isinstance(node, ast.Return) or node.value is None:
            continue
        if isinstance(node.value, ast.Constant) and node.value.value == 0:
            continue
        assert isinstance(node.value, ast.Call), (
            f"{filename}:{node.lineno} 관문 미경유 return"
        )
        assert getattr(node.value.func, "attr", None) == GATE
        gated += 1
    assert gated >= 1
    assert isinstance(tree, ast.Module)


# ---------------------------------------------------------------------------
# G-242-8 — resolver read-only + ATR 키 집합 동일성
# ---------------------------------------------------------------------------
def test_g242_8_resolver_is_read_only():
    src = _sb_source()
    fn = _func_node(src, "_resolve_sizing_atr")

    for node in ast.walk(fn):
        if isinstance(node, (ast.Assign, ast.AugAssign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for t in targets:
                if isinstance(t, ast.Subscript):
                    seg = ast.unparse(t)
                    assert "_candidates" not in seg and "cands" not in seg, (
                        f"_resolve_sizing_atr 가 후보 dict 에 씁니다: {seg}"
                    )
        if isinstance(node, ast.Call):
            fname = getattr(node.func, "attr", None)
            if fname in ("setdefault", "pop", "update", "__setitem__", "clear"):
                recv = ast.unparse(node.func.value) if hasattr(node.func, "value") else ""
                assert "_candidates" not in recv and "cands" not in recv, (
                    f"_resolve_sizing_atr 가 후보 dict 를 변경합니다: {fname}"
                )


def test_g242_8_sizing_atr_keys_runtime():
    assert StrategyBase._SIZING_ATR_KEYS == ("atr", "atr14")


@pytest.mark.parametrize("filename", sorted(TURTLE_FILES))
def test_g242_8_turtle_block_atr_keys_are_subset(filename):
    """터틀 블록이 후보 dict 에서 읽는 ATR 키 ⊆ `_SIZING_ATR_KEYS`.

    캡 ATR 과 사이징 ATR 이 같은 키 집합을 보지 않으면 "같은 소스" 계약이 깨진다.
    """
    src = _strategy_src(filename)
    fn = _func_node(src, TURTLE_FILES[filename])
    found: set[str] = set()
    for node in ast.walk(fn):
        if not (isinstance(node, ast.Call) and getattr(node.func, "attr", None) == "get"):
            continue
        if not node.args or not isinstance(node.args[0], ast.Constant):
            continue
        key = node.args[0].value
        if not isinstance(key, str):
            continue
        recv = ast.unparse(node.func.value)
        if "_candidates" in recv or recv == "info":
            found.add(key)
    assert found, f"{filename} 터틀 블록에서 후보 dict ATR 키를 찾지 못했습니다 (탐지기 무효)"
    assert found <= set(StrategyBase._SIZING_ATR_KEYS), (
        f"{filename} 터틀 블록이 {found - set(StrategyBase._SIZING_ATR_KEYS)} 키를 "
        "읽습니다 — `_SIZING_ATR_KEYS` 와 소스가 갈립니다"
    )


# ---------------------------------------------------------------------------
# G-242-9 — 마커 문자열 · Try 하위 · write_log 이중 INSERT 0
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("marker", _CAP_MARKERS)
def test_g242_9_marker_literal_present(marker):
    src = _SB.read_text(encoding="utf-8")
    tree = ast.parse(src)
    hits = [
        n for n in ast.walk(tree)
        if isinstance(n, ast.Constant) and isinstance(n.value, str)
        and n.value.startswith(marker)
    ]
    assert hits, f"{marker} 문자열 상수가 strategy_base.py 에 없습니다"


@pytest.mark.parametrize("name", (
    "_emit_fallback_notional_capped",
    "_emit_fallback_cap_skipped",
    "_emit_fallback_cap_config",
    "_emit_fallback_cap_clamped",   # 라운드 1 — 결함 #4 시정 (G-242-10)
))
def test_g242_9_emit_wrapped_in_try(name):
    src = _sb_source()
    fn = _func_node(src, name)
    tries = [
        n for n in ast.walk(fn)
        if isinstance(n, ast.Try)
        and any(
            h.type is None or (isinstance(h.type, ast.Name) and h.type.id == "Exception")
            for h in n.handlers
        )
    ]
    assert tries, f"{name} 에 `except Exception` 흡수가 없습니다 (관측 실패가 매수를 깨뜨림)"
    logs = [
        n for n in ast.walk(fn)
        if isinstance(n, ast.Call)
        and getattr(n.func, "attr", None) in ("info", "warning")
        and getattr(getattr(n.func, "value", None), "id", None) == "logger"
    ]
    assert logs, f"{name} 에 logger 호출이 없습니다"
    for call in logs:
        assert any(call in list(ast.walk(t)) for t in tries), (
            f"{name} 의 logger 호출이 try 밖에 있습니다"
        )


@pytest.mark.parametrize("name", _PURE_FUNCS)
def test_g242_9_no_write_log_double_insert(name):
    """cycle72 규약 — 관문 계열 관측은 logger 만 (system_logs 이중 INSERT 금지).

    ⚠️ 파일 전역이 아니라 **관문 계열 함수 안**만 본다 — `_apply_high_since_buy_from_candles`
    (boot 훅, async)는 정당한 `write_log` 소비처다.
    """
    src = _sb_source()
    fn = _func_node(src, name)
    offenders = [
        n.lineno for n in ast.walk(fn)
        if (isinstance(n, ast.Call)
            and (getattr(n.func, "id", None) == "write_log"
                 or getattr(n.func, "attr", None) == "write_log"))
        or (isinstance(n, ast.ImportFrom) and (n.module or "").endswith("system_logs"))
    ]
    assert not offenders, (
        f"{name} 에 write_log 유입(라인 {offenders}) — 관문은 hot path 이고 "
        "DB 접근은 A-PURE 위반 + system_logs 이중 INSERT"
    )
