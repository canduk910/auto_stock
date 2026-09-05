"""cycle245 Red (AST) — 랏 명목 ρ축 상한 `max_lot_ratio_mult` 구조 계약 봉인.

명세 `_workspace/red/cycle245_ratio_notional_cap_spec.md` §4.2. 행위 테스트로는
잡히지 않는 **구조적 계약**만 정적으로 고정한다.

- G-245-1  `max_lot_ratio_mult` ∉ PARAM_RANGES/INT_PARAMS (런타임 dict + 소스 리터럴 이중).
- G-245-2  A-PURE 확장 — 신규 헬퍼 7 전부 `await`/DB/HTTP 0. 함수 부재 = FAIL.
- G-245-3  관문 순서 = 폴백 → 잔여 클램프 → K축 캡 → `[oversized_fallback]` → **ρ캡** → return.
           ρ캡을 K축 캡 **앞**에 두면 `final<1` 조기탈출로 cycle242 마커가 통째로 사라지고,
           `[oversized_fallback]` **앞**에 두면 차단 사건의 ρ 관측이 사라진다.
- G-245-4  ρ캡 본체 = fail-open `except Exception` + 판정기/리더 호출 + `position_ratio` 축 +
           **K축 수식 혼입 금지**(`compute_unit_qty`/`fraction=`/`atr` 토큰 0) + 경계 비교 방향.
- G-245-5  peek → 로그 → mark (cycle226 D-3).
- G-245-6  `strategies/*.py` **glob 전수**가 `DEFAULT_PARAMS` 에 키를 갖고 값이 모듈 상수와
           동치 — 신규 8번째 전략이 무방비로 편입되는 것까지 막는다.
- G-245-7  캡 로직은 관문 안에만 — 전략 사이징 함수에 `max_lot_ratio_mult` 토큰 0 + A-GATE.
- G-245-8  판정기 `_lot_units_cap_governs` = read-only · **무음**(logger 0) · cycle242 와 동일 소스.
- G-245-9  마커 4종 문자열 + emit 사이트 `Try` 하위 + `write_log` 0 + **cap 인스턴스 분리**.
- G-245-10 `[oversized_fallback]` 포맷 문자열 byte 불변 + 호출이 ρ캡보다 앞.

기존 가드(`test_budget_limit_ast.py` · `test_cycle242_ast_fallback_notional_cap.py`)는
재작성하지 않는다 — 표적 실행에 포함만 한다.
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

KEY = "max_lot_ratio_mult"
GATE = "_apply_budget_limit"
RHO_CAP = "_apply_ratio_notional_cap"
GOVERNS = "_lot_units_cap_governs"
K_CAP = "_apply_lot_units_cap"

_NEW_FUNCS = (
    RHO_CAP,
    "_read_max_lot_ratio_mult",
    GOVERNS,
    "_emit_ratio_notional_blocked",
    "_emit_ratio_cap_skipped",
    "_emit_ratio_cap_config",
    "_emit_ratio_cap_clamped",
)
_NEW_EMITS = (
    "_emit_ratio_notional_blocked",
    "_emit_ratio_cap_skipped",
    "_emit_ratio_cap_config",
    "_emit_ratio_cap_clamped",
)
_MARKERS = (
    "[ratio_notional_blocked]",
    "[ratio_cap_skipped]",
    "[ratio_cap_config]",
    "[ratio_cap_clamped]",
)

TURTLE_SIZING_FUNCS = {
    "donchian_swing.py": "_turtle_buy_quantity",
    "kojiro.py": "calc_buy_quantity",
    "vcp_breakout.py": "_turtle_buy_quantity",
    "bull_flag_breakout.py": "_turtle_buy_quantity",
}

_OVERSIZED_FMT = (
    "[oversized_fallback] ticker=%s strategy=%s qty=%d notional=%d cap=%d "
    "ratio=%.2f — 1주 폴백이 notional 상한 초과 (관측 전용) units=%s"
)


# ---------------------------------------------------------------------------
# 헬퍼 (cycle242 답습 — 로컬 복제, 타 테스트 모듈 import 금지)
# ---------------------------------------------------------------------------
def _strategy_files() -> list[Path]:
    return sorted(
        p for p in _STRATEGY_DIR.glob("*.py") if p.name != "__init__.py"
    )


def _func_node(source: str, name: str) -> ast.AST:
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    raise AssertionError(f"{name} 함수를 찾지 못했습니다 (cycle245 미구현 또는 개명)")


def _sb_source() -> str:
    return inspect.getsource(StrategyBase)


def _calls_named(fn: ast.AST, name: str) -> list[ast.Call]:
    hits = []
    for node in ast.walk(fn):
        if isinstance(node, ast.Call):
            fname = getattr(node.func, "attr", None) or getattr(node.func, "id", None)
            if fname == name:
                hits.append(node)
    return hits


def _logger_calls(fn: ast.AST) -> list[ast.Call]:
    return [
        n for n in ast.walk(fn)
        if isinstance(n, ast.Call)
        and getattr(n.func, "attr", None) in ("info", "warning", "error", "debug")
        and getattr(getattr(n.func, "value", None), "id", None) == "logger"
    ]


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


def _default_params_literal(path: Path) -> dict:
    tree = ast.parse(path.read_text(encoding="utf-8"))
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


# ---------------------------------------------------------------------------
# G-245-1 — AI 자문 화이트리스트 편입 금지
# ---------------------------------------------------------------------------
def test_g245_1_runtime_param_ranges_excludes_key():
    assert KEY not in rec_mod.PARAM_RANGES, (
        f"{KEY} 는 리스크 정체성 상수 — AI 자문이 매일 밤 흔들면 안 된다"
    )
    assert KEY not in rec_mod.INT_PARAMS


def test_g245_1_source_literals_exclude_key():
    src = _RECO.read_text(encoding="utf-8")
    for name in ("PARAM_RANGES", "INT_PARAMS"):
        keys = _collect_named_literal_str_keys(src, name)
        assert keys, f"{name} 리터럴 파싱 실패 (탐지기 무효)"
        assert KEY not in keys, f"{name} 리터럴에 '{KEY}' 편입 금지"


def test_g245_1_detector_self_test():
    """탐지기 self-test — 실제 존재하는 키는 검출된다 (공허한 PASS 차단)."""
    src = _RECO.read_text(encoding="utf-8")
    assert "volume_multiplier" in _collect_named_literal_str_keys(src, "PARAM_RANGES")
    assert "long_ma_period" in _collect_named_literal_str_keys(src, "INT_PARAMS")


# ---------------------------------------------------------------------------
# G-245-2 — A-PURE 확장 (신규 헬퍼 7 전부 await/DB/HTTP 0, 부재 = FAIL)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("name", _NEW_FUNCS)
def test_g245_2_new_helpers_are_pure_sync(name):
    src = _sb_source()
    fn = _func_node(src, name)   # 부재 = FAIL (헬퍼로 빼면서 가드를 비우는 우회 차단)

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
# G-245-3 — 관문 호출 순서 + 결과 대입 + 정확 1회
# ---------------------------------------------------------------------------
def test_g245_3_gate_call_order_and_assignment():
    src = _sb_source()
    fn = _func_node(src, GATE)

    fb = _calls_named(fn, "_fallback_one_share")
    clamp = _calls_named(fn, "_emit_budget_clamp")
    kcap = _calls_named(fn, K_CAP)
    over = _calls_named(fn, "_emit_oversized_fallback")
    rho = _calls_named(fn, RHO_CAP)
    assert fb and clamp and kcap and over, "관문의 기존 호출 4종이 사라졌습니다"
    assert len(rho) == 1, (
        f"{RHO_CAP} 호출은 정확히 1회여야 합니다 (실제 {len(rho)}) — 중복/누락 모두 계약 위반"
    )
    assert (
        min(f.lineno for f in fb)
        < min(c.lineno for c in clamp)
        < kcap[0].lineno
        < min(o.lineno for o in over)
        < rho[0].lineno
    ), (
        "ρ캡 위치 계약 위반 — K축 캡 앞이면 cycle242 마커가, `[oversized_fallback]` "
        "앞이면 차단 랏의 ρ 관측이 `final<1` 조기탈출로 사라진다"
    )
    returns = [n for n in ast.walk(fn) if isinstance(n, ast.Return)]
    assert max(r.lineno for r in returns) > rho[0].lineno

    assigned = [
        n for n in ast.walk(fn)
        if isinstance(n, ast.Assign)
        and isinstance(n.value, ast.Call)
        and getattr(n.value.func, "attr", None) == RHO_CAP
        and any(isinstance(t, ast.Name) and t.id == "final" for t in n.targets)
    ]
    assert assigned, f"{RHO_CAP} 결과가 `final` 에 대입되지 않았습니다 (호출만 하고 버림)"


# ---------------------------------------------------------------------------
# G-245-4 — ρ캡 본체 구조 (fail-open · 축 혼입 금지 · 경계 비교 방향)
# ---------------------------------------------------------------------------
def test_g245_4_rho_cap_body_structure():
    src = _sb_source()
    fn = _func_node(src, RHO_CAP)

    tries = [
        n for n in fn.body
        if isinstance(n, ast.Try)
        and any(
            h.type is None or (isinstance(h.type, ast.Name) and h.type.id == "Exception")
            for h in n.handlers
        )
    ]
    assert tries, (
        f"{RHO_CAP} 최상위에 `except Exception` fail-open 이 없습니다 — "
        "캡 산출 예외가 매수 수량 산출로 전파되면 P0-1 재현 경로"
    )
    assert _calls_named(fn, GOVERNS), "K축 심사 여부 판정기를 호출하지 않습니다 (이중 캡 위험)"
    assert _calls_named(fn, "_read_max_lot_ratio_mult"), "K_ρ 리더를 호출하지 않습니다"
    assert any(
        isinstance(n, ast.Constant) and n.value == "position_ratio"
        for n in ast.walk(fn)
    ), "ρ축(`position_ratio × 예산`) 상수가 없습니다 — 축이 바뀌었습니다"


def test_g245_4_no_k_axis_formula_leak():
    """K축(ATR) 수식이 ρ캡 안으로 새면 두 캡의 상호배타 계약이 무너진다."""
    fn = _func_node(_sb_source(), RHO_CAP)
    assert not _calls_named(fn, "compute_unit_qty"), "ρ캡 안에서 터틀 유닛 수식을 씁니다"
    for node in ast.walk(fn):
        if isinstance(node, ast.Call):
            for kw in node.keywords:
                assert kw.arg != "fraction", "ρ캡 안에 `fraction=` kwarg (K축 수식 혼입)"
        if isinstance(node, ast.Constant) and node.value in ("atr", "atr14"):
            pytest.fail("ρ캡 안에 ATR 키 상수 — 축 혼입 금지")


def test_g245_4_cutoff_boundary_is_inclusive_structurally():
    """경계 비교는 `final <= cap_qty`(통과) 또는 `notional > cutoff`(차단) 만 허용.

    `<`/`>=` 로 뒤집는 뮤테이션은 F-2 가 행위로도 잡지만, 구조로도 핀한다.
    """
    fn = _func_node(_sb_source(), RHO_CAP)
    boundary = [
        n for n in ast.walk(fn)
        if isinstance(n, ast.Compare)
        and any(
            isinstance(x, ast.Name) and x.id in ("cap_qty", "cutoff")
            for x in [n.left, *n.comparators]
        )
    ]
    assert boundary, "경계 비교식(cap_qty/cutoff)을 찾지 못했습니다 (탐지기 무효)"
    ops = {type(op).__name__ for n in boundary for op in n.ops}
    assert ops <= {"LtE", "Gt"}, (
        f"경계 비교 연산자가 {ops} — `final <= cap_qty` 또는 `notional > cutoff` 만 "
        "허용됩니다(경계 포함 통과 = 계약)"
    )


# ---------------------------------------------------------------------------
# G-245-5 — peek → 로그 → mark (cycle226 D-3)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("name", _NEW_EMITS + ("_emit_oversized_fallback",))
def test_g245_5_mark_emitted_after_logger(name):
    fn = _func_node(_sb_source(), name)
    should = _calls_named(fn, "should_emit")
    mark = _calls_named(fn, "mark_emitted")
    log = _logger_calls(fn)
    assert should, f"{name} 에 should_emit(peek) 가 없습니다"
    assert mark, f"{name} 에 mark_emitted 가 없습니다"
    assert log, f"{name} 에 logger 호출이 없습니다"
    assert max(s.lineno for s in should) < min(l.lineno for l in log), (
        f"{name}: should_emit(peek) 이 로그보다 뒤에 있습니다"
    )
    assert min(m.lineno for m in mark) > max(l.lineno for l in log), (
        f"{name}: mark_emitted 가 로그보다 앞에 있습니다 — 로그 자기실패가 "
        "그날 관측을 통째로 지웁니다 (cycle226 D-3)"
    )


# ---------------------------------------------------------------------------
# G-245-6 — 모듈 상수 + 전략 파일 glob 전수 키 존재/동치
# ---------------------------------------------------------------------------
def test_g245_6_module_constants():
    assert sb_mod._MAX_LOT_RATIO_MULT_MIN == pytest.approx(1.0), (
        "하한 1.0 은 주 분기(정상 비중 랏) 무접촉의 수학적 전제 — 낮추면 전면 무매매"
    )
    assert sb_mod._MAX_LOT_RATIO_MULT_MAX == pytest.approx(20.0)
    assert sb_mod._MAX_LOT_RATIO_MULT_DEFAULT == pytest.approx(2.5)
    assert (
        sb_mod._MAX_LOT_RATIO_MULT_MIN
        <= sb_mod._MAX_LOT_RATIO_MULT_DEFAULT
        <= sb_mod._MAX_LOT_RATIO_MULT_MAX
    )


def test_g245_6_strategy_file_glob_is_non_vacuous():
    files = _strategy_files()
    assert len(files) >= 7, f"전략 파일 glob 이 {len(files)}개 — 탐지기가 무효화됐습니다"


@pytest.mark.parametrize("path", _strategy_files(), ids=lambda p: p.name)
def test_g245_6_every_strategy_declares_key(path):
    """신규 8번째 전략이 **키 없이**(= ρ캡 OFF) 태어나는 것까지 막는다."""
    params = _default_params_literal(path)
    assert params, f"{path.name} DEFAULT_PARAMS 리터럴을 찾지 못했습니다"
    assert KEY in params, (
        f"{path.name} DEFAULT_PARAMS 에 {KEY} 가 없습니다 — 키 부재 = 캡 OFF 라 "
        "이 전략의 1주 폴백이 무제한이 됩니다"
    )
    assert params[KEY] == pytest.approx(sb_mod._MAX_LOT_RATIO_MULT_DEFAULT), (
        f"{path.name} 의 {KEY} 가 모듈 상수와 다릅니다 (정본 이원화)"
    )


# ---------------------------------------------------------------------------
# G-245-7 — 캡 로직 전략 누출 금지 + A-GATE 재확인
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("path", _strategy_files(), ids=lambda p: p.name)
def test_g245_7_no_cap_tokens_in_strategy_sizing(path):
    src = path.read_text(encoding="utf-8")
    targets = {"calc_buy_quantity"}
    if path.name in TURTLE_SIZING_FUNCS:
        targets.add(TURTLE_SIZING_FUNCS[path.name])
    for name in targets:
        try:
            fn = _func_node(src, name)
        except AssertionError:
            continue
        for node in ast.walk(fn):
            if isinstance(node, ast.Constant) and node.value == KEY:
                pytest.fail(f"{path.name}::{name} 에 {KEY} 토큰 — 캡은 관문 안에만")

    fn = _func_node(src, "calc_buy_quantity")
    gated = 0
    for node in ast.walk(fn):
        if not isinstance(node, ast.Return) or node.value is None:
            continue
        if isinstance(node.value, ast.Constant) and node.value.value == 0:
            continue
        assert isinstance(node.value, ast.Call), (
            f"{path.name}:{node.lineno} 관문 미경유 return"
        )
        assert getattr(node.value.func, "attr", None) == GATE
        gated += 1
    assert gated >= 1


# ---------------------------------------------------------------------------
# G-245-8 — 판정기는 read-only · 무음 · cycle242 와 동일 소스
# ---------------------------------------------------------------------------
def test_g245_8_governs_is_read_only_and_silent():
    fn = _func_node(_sb_source(), GOVERNS)

    for node in ast.walk(fn):
        if isinstance(node, (ast.Assign, ast.AugAssign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for t in targets:
                if isinstance(t, ast.Subscript):
                    seg = ast.unparse(t)
                    assert "_candidates" not in seg and "cands" not in seg, (
                        f"{GOVERNS} 가 후보 dict 에 씁니다: {seg}"
                    )
        if isinstance(node, ast.Call):
            fname = getattr(node.func, "attr", None)
            if fname in ("setdefault", "pop", "update", "__setitem__", "clear"):
                recv = ast.unparse(node.func.value) if hasattr(node.func, "value") else ""
                assert "_candidates" not in recv and "cands" not in recv, (
                    f"{GOVERNS} 가 후보 dict 를 변경합니다: {fname}"
                )

    assert not _logger_calls(fn), (
        f"{GOVERNS} 가 로그를 냅니다 — 판정기는 랏마다 도는 무음 경로여야 한다"
        "(관측은 `[ratio_cap_config]` 카나리아 담당)"
    )


def test_g245_8_governs_uses_same_sources_as_cycle242():
    src = _sb_source()
    fn = _func_node(src, GOVERNS)
    consts = {n.value for n in ast.walk(fn)
              if isinstance(n, ast.Constant) and isinstance(n.value, str)}
    assert "turtle" in consts, "`sizing_mode == \"turtle\"` 판정이 없습니다"
    assert "risk_pct" in consts, "risk_pct 조건이 없습니다 (cycle242 4조건 동일 소스)"
    assert _calls_named(fn, "_resolve_sizing_atr"), (
        "ATR 해석을 cycle242 와 같은 함수로 하지 않습니다 — 판정이 드리프트합니다"
    )
    assert any(
        isinstance(n, ast.Attribute) and n.attr == "total_investment"
        for n in ast.walk(fn)
    ), "예산 조건이 없습니다"


# ---------------------------------------------------------------------------
# G-245-9 — 마커 문자열 · Try 하위 · write_log 0 · cap 인스턴스 분리
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("marker", _MARKERS)
def test_g245_9_marker_literal_present(marker):
    tree = ast.parse(_SB.read_text(encoding="utf-8"))
    hits = [
        n for n in ast.walk(tree)
        if isinstance(n, ast.Constant) and isinstance(n.value, str)
        and n.value.startswith(marker)
    ]
    assert hits, f"{marker} 문자열 상수가 strategy_base.py 에 없습니다"


@pytest.mark.parametrize("name", _NEW_EMITS)
def test_g245_9_emit_wrapped_in_try(name):
    fn = _func_node(_sb_source(), name)
    tries = [
        n for n in ast.walk(fn)
        if isinstance(n, ast.Try)
        and any(
            h.type is None or (isinstance(h.type, ast.Name) and h.type.id == "Exception")
            for h in n.handlers
        )
    ]
    assert tries, f"{name} 에 `except Exception` 흡수가 없습니다 (관측 실패가 매수를 깨뜨림)"
    logs = _logger_calls(fn)
    assert logs, f"{name} 에 logger 호출이 없습니다"
    for call in logs:
        assert any(call in list(ast.walk(t)) for t in tries), (
            f"{name} 의 logger 호출이 try 밖에 있습니다"
        )


@pytest.mark.parametrize("name", _NEW_FUNCS)
def test_g245_9_no_write_log_double_insert(name):
    """cycle72 규약 — 관문 계열 관측은 logger 만 (system_logs 이중 INSERT 금지)."""
    fn = _func_node(_sb_source(), name)
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


@pytest.mark.parametrize("name", _NEW_EMITS)
def test_g245_9_cap_instance_is_separate(name):
    """cycle245 마커는 `_ratio_cap_logged` 를 쓴다 — cycle242 cap 과 공유 금지(cycle236 선례)."""
    fn = _func_node(_sb_source(), name)
    attrs = {n.attr for n in ast.walk(fn) if isinstance(n, ast.Attribute)}
    assert "_ratio_cap_logged" in attrs, f"{name} 이 cycle245 전용 cap 을 쓰지 않습니다"
    assert "_lot_cap_logged" not in attrs, (
        f"{name} 이 cycle242 cap 인스턴스를 공유합니다 — 한쪽의 키 폭주·날짜 리셋이 "
        "다른 사이클 관측을 지웁니다"
    )
    # 사이클 258 카드 #4 재조준 — `_ratio_cap_day` 수동 날짜 필드는 `KstDailyEmitCap`
    # 이 자기 리셋을 내장하며 소멸했다(문자열 속성 검사 불가). 날짜 자기 리셋
    # 존재는 이제 **cap 이 KstDailyEmitCap 타입인가** 런타임 확인으로 갈음한다.
    from src.engine.daily_emit_cap import KstDailyEmitCap
    from src.engine.strategy_base import StrategyBase

    class _Probe(StrategyBase):
        async def prepare(self):  # pragma: no cover
            return None

        def check_buy_signal(self, ticker, current_price, open_price):
            return None

        def check_exit_signal(self, ticker, current_price, open_price):
            return None

        def calc_buy_quantity(self, current_price, ticker=None):
            return 0

    from src.engine.strategy_base import StrategyConfig

    probe = _Probe(StrategyConfig(strategy_id="probe", name="probe"))
    assert isinstance(probe._ratio_cap_logged, KstDailyEmitCap), (
        f"{name} 이 참조하는 `_ratio_cap_logged` 가 `KstDailyEmitCap` 이 아닙니다 — "
        "날짜 자기 리셋을 잃습니다"
    )


# ---------------------------------------------------------------------------
# G-245-10 — `[oversized_fallback]` 서식 byte 불변 + 배치 순서
# ---------------------------------------------------------------------------
def test_g245_10_oversized_format_literal_is_byte_stable():
    fn = _func_node(_sb_source(), "_emit_oversized_fallback")
    fmts = [
        n.args[0].value for n in _logger_calls(fn)
        if n.args and isinstance(n.args[0], ast.Constant)
        and isinstance(n.args[0].value, str)
    ]
    assert _OVERSIZED_FMT in fmts, (
        "`[oversized_fallback]` 포맷 문자열이 변조됐습니다 — cycle233 형 검사"
        f'("3.10" in message)와 grep 이력 호환이 깨집니다. 실제: {fmts}'
    )


def test_g245_10_observation_precedes_rho_cap():
    fn = _func_node(_sb_source(), GATE)
    over = _calls_named(fn, "_emit_oversized_fallback")
    rho = _calls_named(fn, RHO_CAP)
    assert over and rho
    assert max(o.lineno for o in over) < rho[0].lineno, (
        "ρ캡이 관측보다 앞이면 차단된 랏(`final=0`)의 `[oversized_fallback]` 이 "
        "통째로 사라져 R7 자기검증 불변식이 성립하지 않는다"
    )
