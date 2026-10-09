"""cycle414 Red — `GET /api/strategies/monitor` 순수성 AST (명세 §3.1·§3.3 · §8.1 R2).

범위 = `src/routes/strategies.py` 의 핸들러 `get_strategies_monitor` + 이름이 `_monitor` 로 시작하는 모듈 함수
(그 안의 중첩 함수·람다·컴프리헨션 포함). 선례 = `test_cycle412_g1_purity.py`(exit-lines G1).

이 라우트는 5~10초마다 화면이 부르는 **운영 엔진 메모리 창**이다. 호출 하나가 래치를 pop 하거나
(`_latch_entry`) 캡의 날짜를 넘기거나(`should_emit`·`count_matching` → `_sync_day`) 시장 유닛 미계산
경보를 남기면(`_market_unit_view`), 화면을 여는 것만으로 매수·손절 판정이 바뀐다.

| # | 계약 |
|---|---|
| M1 | `@router.get("/monitor")` 핸들러 `get_strategies_monitor` 는 `async def` · 범위 안 `await`/`async for`/`async with` 0 |
| M2 | 허용 호출만 — 내장 읽기 함수 · `_monitor*` · 명세 §3.3 「불러도 되는 것」 · 문자열/날짜 읽기 메서드 |
| M3 | 금지 호출 0 — `_market_unit_view`·`_latch_entry`·`should_emit`·`mark_emitted`·`count_matching`·`get_targets_status`·`check_*`·`on_*`·`calc_*`·`prepare`·`_apply_budget_limit`·`_market_unit_*`·`_record_*`·`_emit_*`·`_roll_gate_day_if_needed` · 변이 메서드 · `setattr`·`vars`… |
| M4 | `_kk` 는 리터럴 5키 집합(`kk_breakeven_r`·`kk_time_exit_bars`·`kk_time_exit_min_r`·`kk_max_hold_bars`·`max_daily_entries`)으로만 |
| M5 | 대입·증분대입 대상은 이름(튜플)만 · `del` 0 · `__dict__` 0 · `nonlocal` 0 · `global` 은 `_monitor_cache` 만 |
| M6 | 직렬화(`json.dumps(..., default=str)`)와 조립(`_monitor*` 호출)은 핸들러의 같은 `try` 본문 안 · 그 `try` 는 예외를 받는다 |
| M7 | 이 파일 최상단의 8영역·`scheduler` import 는 기존 `from src.engine.scheduler import trading_scheduler` 하나뿐(새로 늘리지 않는다) · 범위 안 함수 import 는 허용 모듈만 |
| M8 | 로그는 `debug` 만 — 폴링 엔드포인트가 INFO 이상을 쌓지 않는다(위 M2 허용 목록에 `info`·`warning`·`error`·`exception` 이 없다) |

`ast.dump` sha 를 핀하지 않는다(3.12/3.13 출력 차이 — 가드 설계 금기).
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parents[3]
_STRATEGIES = _ROOT / "src" / "routes" / "strategies.py"
_HANDLER = "get_strategies_monitor"

_ALLOWED_NAMES = {
    # 내장 — 읽기·조립만
    "getattr", "hasattr", "isinstance", "callable", "list", "dict", "tuple", "set", "frozenset", "sorted",
    "int", "float", "str", "bool", "len", "round", "max", "min", "abs", "sum", "any", "all", "enumerate",
    "zip", "range", "reversed", "iter", "next",
    # 수학 읽기
    "ceil", "floor", "isfinite",
    # 응답
    "Response", "JSONResponse", "ApiResponse", "now_kst_iso",
    # exit-lines 의 순수 헬퍼 재사용(무장가) — cycle412 G1 순수성 가드가 지킨다
    "_exit_lines_kk",
}
_ALLOWED_ATTRS = {
    # 컨테이너·레지스트리 읽기
    "get", "items", "keys", "values", "all", "copy",
    # 시각·문자열 읽기
    "now", "date", "isoformat", "astimezone", "total_seconds", "strftime", "monotonic",
    "startswith", "endswith", "split", "rsplit", "partition", "rpartition", "strip", "lower", "upper",
    "join", "format",
    # 직렬화·로그(debug 만)
    "dumps", "debug",
    # 수학 모듈 경유
    "ceil", "floor", "isfinite",
    # 명세 §3.3 「불러도 되는 것」(순수 확인됨)
    "get_effective_stop_price",
    "_cluster_blocked", "_pure_turtle_qty", "_sizing_mode_ok",          # etf
    "hard_stop", "stop_line", "gap_skip_reason",                        # etf_trend_core
    "_business_days_held", "_kk_exit_lines", "_kk_r", "_kk_design_lot", "_kk",  # donchian
    "breakout_event_summary",                                           # VCP
    "get_observed_acml_vol",                                            # tick_volume
    "normalize_mode",                                                   # market_unit 모드 정규화(순수)
}
_MUTATORS = {"pop", "popitem", "clear", "update", "setdefault", "sort", "append", "extend", "remove",
             "insert", "add", "discard", "reset_daily", "record_acml_vol"}
_FORBIDDEN_EXACT = {
    "_market_unit_view", "_latch_entry", "should_emit", "mark_emitted", "count_matching", "_sync_day",
    "get_targets_status", "prepare", "_apply_budget_limit", "_roll_gate_day_if_needed",
    "_kk_daily_cap_blocks", "_kk_lot_zero_blocks", "_kk_signal_m", "_observe_breakout_tick",
    "_gate_should_emit", "_effective_setup",
    "vars", "setattr", "delattr", "exec", "eval", "__import__", "open",
}
_FORBIDDEN_PREFIX = ("check_", "on_", "calc_", "_market_unit_", "_record_", "_emit_", "_arm_", "_release_",
                     "_reset_")
_KK_KEYS = {"kk_breakeven_r", "kk_time_exit_bars", "kk_time_exit_min_r", "kk_max_hold_bars", "max_daily_entries"}

_EIGHT = ("src.engine.risk", "src.engine.order_engine", "src.engine.session", "src.engine.scanner",
          "src.engine.strategy_registry", "src.engine.scheduler", "src.api.order", "src.realtime", "src.auth")
#: 범위 안 함수 import 허용 — (모듈, 이름) · 이름 None = `import 모듈` 또는 모듈 자체
_ALLOWED_LOCAL_IMPORTS = {
    ("src.engine.scheduler", "trading_scheduler"),
    ("src.engine", "scanner"), ("src.engine", "tick_volume"), ("src.engine", "etf_trend_core"),
    ("src.engine", "market_unit"),
    ("src.engine.strategy_manifest", "MARKET_UNIT_SCALE_IDS"),
    ("src.engine.scanner", "ticker_last_tick"),
    ("src.engine.tick_volume", "get_observed_acml_vol"),
    ("src.engine.market_unit", "normalize_mode"), ("src.engine.market_unit", "MODE_KEY"),
    ("src.engine.etf_trend_core", "hard_stop"), ("src.engine.etf_trend_core", "stop_line"),
    ("src.engine.etf_trend_core", "gap_skip_reason"),
    ("src.routes.balance", "_exit_lines_kk"),
    ("json", None), ("math", None), ("math", "ceil"), ("math", "isfinite"), ("math", "floor"),
}


def _tree():
    return ast.parse(_STRATEGIES.read_text(encoding="utf-8"))


def _scope():
    fns = [n for n in _tree().body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
           and (n.name == _HANDLER or n.name.startswith("_monitor"))]
    names = {f.name for f in fns}
    assert _HANDLER in names, f"핸들러 `{_HANDLER}` 가 `src/routes/strategies.py` 에 없다(명세 §3.1)"
    assert any(n.startswith("_monitor") and n not in ("_monitor_clock",) for n in names), (
        "조립 함수는 `_monitor*` 이름으로 둔다 — 이 가드의 범위가 이름으로 정해진다")
    return fns


def _handler():
    return next(f for f in _scope() if f.name == _HANDLER)


def _call_name(node: ast.Call) -> tuple[str, str]:
    f = node.func
    if isinstance(f, ast.Name):
        return "name", f.id
    if isinstance(f, ast.Attribute):
        return "attr", f.attr
    return "other", type(f).__name__


def _calls():
    for fn in _scope():
        for node in ast.walk(fn):
            if isinstance(node, ast.Call):
                yield fn.name, node


def test_m1_handler_async_get_monitor_without_await():
    h = _handler()
    assert isinstance(h, ast.AsyncFunctionDef), "핸들러는 async def(이벤트 루프 안에서 한 번에 읽는다)"
    assert any(isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute) and d.func.attr == "get"
               and d.args and isinstance(d.args[0], ast.Constant) and d.args[0].value == "/monitor"
               for d in h.decorator_list), '@router.get("/monitor")'
    for fn in _scope():
        bad = [type(n).__name__ for n in ast.walk(fn) if isinstance(n, (ast.Await, ast.AsyncFor, ast.AsyncWith))]
        assert bad == [], f"{fn.name}: {bad} — 조립 중 양보점이 생기면 엔진 상태가 반쯤 바뀐 순간을 읽는다"


def _local_defs() -> set[str]:
    """범위 안에서 정의한 중첩 함수 이름 — 그 본문도 `ast.walk` 로 같은 검사를 받으므로 불러도 된다."""
    return {n.name for fn in _scope() for n in ast.walk(fn)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n is not fn}


def test_m2_only_allowed_calls():
    bad = []
    local = _local_defs()
    for fname, c in _calls():
        kind, name = _call_name(c)
        ok = ((kind == "name" and (name in _ALLOWED_NAMES or name.startswith("_monitor") or name in local))
              or (kind == "attr" and (name in _ALLOWED_ATTRS or name.startswith("_monitor"))))
        if not ok:
            bad.append(f"{fname}:{c.lineno} {kind} {name}")
    assert bad == [], bad


def test_m3_forbidden_calls_absent():
    bad = []
    for fname, c in _calls():
        _, name = _call_name(c)
        if name in _FORBIDDEN_EXACT or name.startswith(_FORBIDDEN_PREFIX) or name in _MUTATORS:
            bad.append(f"{fname}:{c.lineno} {name}")
    assert bad == [], bad


def test_m4_kk_only_with_literal_whitelisted_keys():
    for _, c in _calls():
        if _call_name(c) != ("attr", "_kk"):
            continue
        assert len(c.args) == 1 and not c.keywords, ast.dump(c)
        arg = c.args[0]
        assert isinstance(arg, ast.Constant) and arg.value in _KK_KEYS, (
            f"`_kk` 는 리터럴 5키로만 — 그 밖 키는 잘못된 파라미터일 때 WARNING·캡 기록이 남는다: {ast.dump(arg)}")


def _targets(node):
    if isinstance(node, (ast.Tuple, ast.List)):
        for e in node.elts:
            yield from _targets(e)
    elif isinstance(node, ast.Starred):
        yield from _targets(node.value)
    else:
        yield node


def test_m5_assignment_targets_are_names_only():
    bad = []
    for fn in _scope():
        for node in ast.walk(fn):
            tgts = []
            if isinstance(node, ast.Assign):
                tgts = node.targets
            elif isinstance(node, (ast.AugAssign, ast.AnnAssign)):
                tgts = [node.target]
            elif isinstance(node, ast.NamedExpr):
                tgts = [node.target]
            elif isinstance(node, (ast.For, ast.comprehension)):
                tgts = [node.target]
            elif isinstance(node, ast.Delete):
                bad.append(f"{fn.name}:{node.lineno} del")
            elif isinstance(node, ast.Attribute) and node.attr == "__dict__":
                bad.append(f"{fn.name}:{node.lineno} __dict__")
            elif isinstance(node, ast.Global) and set(node.names) - {"_monitor_cache"}:
                bad.append(f"{fn.name}:{node.lineno} global {node.names}")
            elif isinstance(node, ast.Nonlocal):
                bad.append(f"{fn.name}:{node.lineno} nonlocal")
            for t in tgts:
                for leaf in _targets(t):
                    if not isinstance(leaf, ast.Name):
                        bad.append(f"{fn.name}:{getattr(node, 'lineno', '?')} 대입 대상 {type(leaf).__name__}")
    assert bad == [], bad


def test_m6_serialize_and_assemble_inside_handler_try():
    h = _handler()
    found = False
    for t in (n for n in ast.walk(h) if isinstance(n, ast.Try)):
        body_calls = [c for s in t.body for c in ast.walk(s) if isinstance(c, ast.Call)]
        dumps = [c for c in body_calls if _call_name(c) == ("attr", "dumps")]
        if not dumps:
            continue
        found = True
        assert t.handlers, "직렬화 try 에 except 가 없다 — 실패는 HTTP 200 success=false"
        assert any(kw.arg == "default" and isinstance(kw.value, ast.Name) and kw.value.id == "str"
                   for c in dumps for kw in c.keywords), "json.dumps(..., default=str)"
        assert any(_call_name(c)[1].startswith("_monitor") and _call_name(c)[1] != "_monitor_clock"
                   for c in body_calls), "조립(`_monitor*`)도 같은 try 안에서"
    assert found, "json.dumps 가 핸들러의 try 본문 안에 없다"


def test_m7_imports_top_level_and_local():
    top = []
    for node in _tree().body:
        if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith(_EIGHT):
            top.extend((node.module, a.name) for a in node.names)
        if isinstance(node, ast.Import):
            top.extend((a.name, None) for a in node.names if a.name.startswith(_EIGHT))
    assert set(top) <= {("src.engine.scheduler", "trading_scheduler")}, (
        f"최상단 8영역 import 를 늘리지 않는다 — 함수 안에서 얻는다(G1 A7 관례): {top}")

    bad = []
    for fn in _scope():
        for node in ast.walk(fn):
            if isinstance(node, ast.ImportFrom):
                for a in node.names:
                    if (node.module, a.name) not in _ALLOWED_LOCAL_IMPORTS:
                        bad.append(f"{fn.name}:{node.lineno} from {node.module} import {a.name}")
            elif isinstance(node, ast.Import):
                for a in node.names:
                    if (a.name, None) not in _ALLOWED_LOCAL_IMPORTS:
                        bad.append(f"{fn.name}:{node.lineno} import {a.name}")
    assert bad == [], bad
