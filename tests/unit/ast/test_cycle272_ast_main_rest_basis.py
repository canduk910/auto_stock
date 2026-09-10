"""cycle272 Red (AST) — 구조·라인·파라미터 계약 봉인. 계약 C5·C7·C10·C24·C26·C27·C28.

명세 정본 = `_workspace/red/cycle272_rest_open_basis_spec.md`
자문 정본 = `_workspace/domain_consult/cycle272_rest_open_basis_20260910.md`
행위 가드 = `tests/unit/engine/strategies/test_cycle272_main_rest_basis.py`(게이트) ·
            `tests/unit/engine/test_cycle272_open_price_rest_leaf.py`(leaf)

**Red 단계 — 테스트만. `src/` 미변경.** 행위 테스트로 잡히지 않는 것만 정적으로 고정한다.

| # | 가드 | 지키는 것 |
|---|---|---|
| G-272-5 | 게이트의 두 조기반환이 **모든 `Try`·`params` 접근보다 앞** | REST 경로의 구조적 면역(P0-1 계열 사고 차단) |
| G-272-7 | cycle264 `_STRATEGY_PINS` 6개 sha **전부 불변** — **갱신 금지가 계약** | 무접촉 6종의 기계적 증거 |
| G-272-10 | 시그니처 `(self, ticker, open_price, board="main", *, source="ws")` · 신뢰 목록 `("rest",)` | WS 3 호출부 무변경 계약 |
| G-272-24 | `start()` 에서 `_drain_pending_next_day_clear` 가 confirm(board="main") **직후** | 호출 순서 불변(익일청산 앞당김은 부수 효과이지 순서 변경이 아니다) |
| G-272-26 | REST 폴백 호출**만** `source="rest"` 명시, 나머지 3곳은 미명시 | 기본 `"ws"` 의존이 계약 |
| G-272-27 | `scheduler.py ≤ 3,899` ∧ cycle257 리터럴과 대조 | 라인 예산(느슨한 자체 가드 재발 차단) |
| G-272-28 | 키 ∉ `PARAM_RANGES`/`INT_PARAMS` · glob 전수 {VB,LTV} · 8영역 diff 0 · 문서 2곳 | 진입 정체성 상수 + 접촉 범위 |

## ⚠️ 사이클 한정 — **커밋 후 삭제 의무**

- `test_g272_28d_untouchable_areas_untouched`
- `test_g272_28e_other_strategy_files_untouched`

두 가드는 `git diff HEAD` 로 **워킹트리 범위**를 잰다. 커밋 직후 공허해지고 다음 편집에서
무조건 RED 가 된다(cycle240 A11b · cycle252 G-252-5b · cycle262 C12 의 고아 가드 사고).
**cycle272 커밋 직후 이 두 테스트를 삭제한다.** 8영역의 **영구** 가드는
`tests/unit/ast/test_cycle222a3_ast_followup_fixes.py` 가 계속 들고 있으므로 잃는 커버리지는 없다.
나머지 가드는 전부 영구다.

## 비-공허성

모든 구조 가드는 **기준선(대상 함수/호출부)이 없으면 명시 FAIL** 한다 —
사이클 224 의 vacuous PASS(기준선을 검사 대상 자신에서 유도해 뮤테이션 전후 모두 통과)
재발 차단. 따라서 Green 이전에는 전부 RED 다.

## `ast.dump` sha 핀을 쓰지 않는 이유

3.12(CI)와 3.13(로컬)의 `ast.dump` 출력이 달라 로컬 초록·CI 실패가 난다
(cycle256 G-250-5 · cycle259 S4a 실측). 코드 핀은 `ast.get_source_segment` 의 sha256 이다.
소스 스캔에 `git grep`/`git ls-files` 도 쓰지 않는다 — 추적 파일만 보므로 Green 이 새로
만든 미추적 파일을 로컬에서 놓친다(cycle259 S4b). 전부 `Path.rglob` + AST 다.
"""

from __future__ import annotations

import ast
import hashlib
import re
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parents[3]
_SRC = _ROOT / "src"
_STRATEGY_DIR = _SRC / "engine" / "strategies"
_LEAF = _SRC / "engine" / "open_price_rest.py"
_SCHEDULER = _SRC / "engine" / "scheduler.py"
_RECO = _SRC / "engine" / "recommendation_engine.py"

KEY = "open_price_scope_mode"
_GATE_FN = "reject_untrusted_main_basis"
_SETTER = "on_open_price_confirmed"

_VB_REL = "src/engine/strategies/volatility_breakout.py"
_LTV_REL = "src/engine/strategies/long_tail_volatility.py"

_MARKERS = (
    "[main_rest_basis_config]", "[main_rest_basis_round]",
    "[main_rest_basis_confirmed]", "[main_rest_basis_unresolved]",
)

# 8영역 (루트 CLAUDE.md 정본, 9경로)
_UNTOUCHABLE_FILES = (
    "src/engine/risk.py",
    "src/engine/order_engine.py",
    "src/engine/session.py",
    "src/engine/scanner.py",
    "src/engine/strategy_registry.py",
    "src/api/order.py",
)
_UNTOUCHABLE_DIRS = ("src/auth/", "src/realtime/")

_OTHER_STRATEGY_FILES = (
    "src/engine/strategies/momentum.py",
    "src/engine/strategies/donchian_swing.py",
    "src/engine/strategies/kojiro.py",
    "src/engine/strategies/vcp_breakout.py",
    "src/engine/strategies/bull_flag_breakout.py",
)


# ---------------------------------------------------------------------------
# 헬퍼
# ---------------------------------------------------------------------------
def _tree(path: Path) -> tuple[ast.Module, str]:
    src = path.read_text(encoding="utf-8")
    return ast.parse(src), src


def _func(tree: ast.Module, name: str):
    for n in ast.walk(tree):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name:
            return n
    return None


def _method(tree: ast.Module, cls_name: str, name: str):
    for cls in ast.walk(tree):
        if isinstance(cls, ast.ClassDef) and cls.name == cls_name:
            for n in cls.body:
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name:
                    return n
    return None


def _git(*args: str) -> str:
    res = subprocess.run(["git", *args], cwd=_ROOT, capture_output=True, text=True)
    assert res.returncode == 0, f"git {' '.join(args)} 실패: {res.stderr}"
    return res.stdout


def _changed_paths() -> list[str]:
    return [p for p in _git("diff", "--name-only", "HEAD").splitlines() if p.strip()]


# ===========================================================================
# G-272-5 — 게이트 조기반환 순서 (안전 계약)
# ===========================================================================

def _gate_fn():
    assert _LEAF.exists(), (
        f"{_LEAF.relative_to(_ROOT)} 가 없다 — cycle272 미구현(Red). "
        "행위 leaf 는 `src/engine/open_price_rest.py` 가 정본이다"
    )
    tree, src = _tree(_LEAF)
    fn = _func(tree, _GATE_FN)
    assert fn is not None, (
        f"`{_GATE_FN}` 함수가 없다 — 이 가드는 기준선 부재를 조용한 PASS 로 넘기지 않는다"
    )
    return fn, src


def test_g272_5a_first_statement_is_board_scope_guard():
    """C5 ① — 첫 문장은 `board != "main"` 조기반환이다(순수 비교, 예외 불가).

    비-main 보드(LTV 08:00 프리장 등)가 게이트의 어떤 실패에도 영향받지 않게 하는
    구조적 보장이다.
    """
    fn, _src = _gate_fn()
    first = fn.body[0]
    assert isinstance(first, ast.If), f"첫 문장이 If 가 아니다 — {type(first).__name__}"
    assert any(isinstance(n, ast.Return) for n in ast.walk(first)), "조기반환이 없다"
    tokens = {
        n.value for n in ast.walk(first)
        if isinstance(n, ast.Constant) and isinstance(n.value, str)
    } | {
        n.id for n in ast.walk(first) if isinstance(n, ast.Name)
    }
    assert ("main" in tokens) or ("_MAIN_BOARD" in tokens), (
        f"첫 문장이 board 스코프 판정으로 보이지 않는다 — 토큰 {sorted(map(str, tokens))}"
    )


def test_g272_5b_second_statement_is_trusted_source_guard():
    """C5 ② — 둘째 문장은 `source in _TRUSTED_MAIN_SOURCES` 조기반환이다."""
    fn, _src = _gate_fn()
    assert len(fn.body) >= 2, "게이트 본체가 2문장 미만이다"
    second = fn.body[1]
    assert isinstance(second, ast.If), f"둘째 문장이 If 가 아니다 — {type(second).__name__}"
    assert any(isinstance(n, ast.Return) for n in ast.walk(second)), "조기반환이 없다"
    names = {n.id for n in ast.walk(second) if isinstance(n, ast.Name)}
    assert "source" in names, f"둘째 문장이 `source` 를 보지 않는다 — {sorted(names)}"
    assert any(
        isinstance(cmp, ast.Compare) and any(isinstance(op, ast.In) for op in cmp.ops)
        for cmp in ast.walk(second)
    ), "신뢰 목록 멤버십(`in`) 검사가 아니다"


def test_g272_5c_early_returns_precede_every_try_and_params_access():
    """C5 — **②가 ③보다 앞**이라는 것이 안전 계약이다.

    이 순서 덕분에 게이트가 무슨 이유로 터지든 REST 경로는 구조적으로 면역이고,
    "게이트 고장 = 종일 목표가 0" 이라는 P0-1 계열 사고가 성립하지 않는다.
    조기반환 순서를 뒤집는 뮤테이션이 여기서 KILL 된다.
    """
    fn, _src = _gate_fn()
    guard_end = max(
        getattr(fn.body[0], "end_lineno", fn.body[0].lineno),
        getattr(fn.body[1], "end_lineno", fn.body[1].lineno),
    )

    tries = [n.lineno for n in ast.walk(fn) if isinstance(n, ast.Try)]
    assert tries, "게이트에 `try` 가 하나도 없다 — 모드 해석 흡수기가 빠졌다"
    assert min(tries) > guard_end, (
        f"`try` 블록(line {min(tries)})이 조기반환(≤{guard_end})보다 앞이다 — "
        "REST 경로가 게이트 예외에 노출된다"
    )

    params_arg = fn.args.args[0].arg if fn.args.args else "params"
    accesses = [
        n.lineno for n in ast.walk(fn)
        if isinstance(n, ast.Name) and n.id == params_arg
    ]
    assert accesses, f"게이트가 `{params_arg}` 를 한 번도 읽지 않는다(모드 해석 부재)"
    assert min(accesses) > guard_end, (
        f"`{params_arg}` 접근(line {min(accesses)})이 조기반환(≤{guard_end})보다 앞이다"
    )


def test_g272_5d_gate_has_no_await_or_db_or_write_log():
    """C5 — 게이트는 **순수 판정**이다. `await`/DB/`write_log` 금지.

    이 함수는 `risk.on_tick` → `check_buy_signal` 인라인 경로에서 **매 틱** 불린다.
    A-PURE(cycle242 G-242-2/G-242-10) 계열 계약을 그대로 승계한다.
    """
    fn, src = _gate_fn()
    assert not any(isinstance(n, (ast.Await, ast.AsyncFor, ast.AsyncWith)) for n in ast.walk(fn)), (
        "게이트에 `await` 가 있다 — 틱 경로의 순수 판정이어야 한다"
    )
    seg = ast.get_source_segment(src, fn) or ""
    for banned in ("write_log", "pg.", "supabase"):
        assert banned not in seg, f"게이트에 `{banned}` 가 있다"


# ===========================================================================
# G-272-7 — cycle264 sha 핀 6개 전부 불변 (갱신 금지가 계약)
# ===========================================================================

# cycle264 가 2026-09-06 HEAD 에서 뜬 값 그대로. **cycle272 는 갱신하지 않는다** —
# `source` 기본값을 `"ws"`(불신)로 둔 덕에 `check_*`/`calc_*` 는 한 글자도 안 바뀐다.
# 6/6 불변이 곧 "여섯 가지 무접촉"(비중·position_ratio·max_positions·랏 캡·
# open_entry_hold_secs·LTV 청산 규약)의 기계적 증거다.
_FROZEN_PINS = {
    ("volatility_breakout", "VolatilityBreakoutStrategy", "check_buy_signal"):
        "e620ae0d14a71f916550ee13f57edff12e1b84c12b8a4712b29583b44b56f20a",
    ("volatility_breakout", "VolatilityBreakoutStrategy", "check_exit_signal"):
        "86593b038e4cf8121ae47069fb368346edc50d9692b29db4cbdcc8897421b72e",
    ("volatility_breakout", "VolatilityBreakoutStrategy", "calc_buy_quantity"):
        "6d24ef3f3afd211ae6123623075b08320cdc08c9cd48a6db965355305ad4e732",
    ("long_tail_volatility", "LongTailVolatilityStrategy", "check_buy_signal"):
        "fb1e7460e5d6906aacd9dd6cbc1037fb7327759c24ca4df055773ba1f22cac2a",
    ("long_tail_volatility", "LongTailVolatilityStrategy", "check_exit_signal"):
        "c8b0e6a8c8705d49bb6f12f82f505d426a5bdeb81413f8b2e0276eabb7dd9cad",
    ("long_tail_volatility", "LongTailVolatilityStrategy", "calc_buy_quantity"):
        "1149ecc8ea37fb1ba164cc1fd88e6525111d5142168ca879f1026c7890905b81",
}


def _method_sha(module: str, cls_name: str, method: str) -> str:
    path = _STRATEGY_DIR / f"{module}.py"
    src = path.read_text(encoding="utf-8")
    tree = ast.parse(src)
    fn = _method(tree, cls_name, method)
    assert fn is not None, f"{module}.{cls_name}.{method} 를 찾지 못했다"
    seg = ast.get_source_segment(src, fn) or ""
    return hashlib.sha256(seg.encode("utf-8")).hexdigest()


@pytest.mark.parametrize("key", sorted(_FROZEN_PINS))
def test_g272_7a_entry_exit_qty_methods_unchanged(key):
    """C7 — 진입·청산·수량 6메서드는 cycle272 전후 **문자 그대로 동결**이다."""
    module, cls_name, method = key
    actual = _method_sha(module, cls_name, method)
    assert actual == _FROZEN_PINS[key], (
        f"{module}.{cls_name}.{method} 가 바뀌었다 — cycle272 의 계약은 '매매 행위를 "
        f"한 글자도 바꾸지 않는다'(무접촉 6종). 실측 sha={actual}"
    )


def test_g272_7b_cycle264_pins_are_not_rewritten():
    """C7 — cycle264 `_STRATEGY_PINS` 자체가 **갱신되지 않았다**.

    자문 §9 O-I — cycle264 docstring 과 U3 §0-C 는 "cycle265/272 가 이 핀 2개를 갱신한다"
    고 예고했다. 이 설계는 접촉이 그보다 좁아 **6/6 불변**이므로 **예고 문장 쪽을 정정**한다.
    누군가 핀을 재산출해 맞추면(= 행위가 바뀐 것을 초록으로 덮으면) 이 가드가 잡는다.
    """
    from tests.unit.ast.test_cycle264_scope_and_pins import _STRATEGY_PINS

    assert _STRATEGY_PINS == _FROZEN_PINS, (
        "cycle264 `_STRATEGY_PINS` 가 재산출됐다 — cycle272 는 그 여섯을 건드리지 않는다"
    )


def test_g272_7c_cycle264_docstring_no_longer_promises_pin_update():
    """C7 — cycle264 파일의 "cycle265 가 이 핀을 갱신한다" **예고 문장만** 정정한다.

    테스트 자체·핀 값은 삭제/갱신하지 않는다(자문 §6-a, O-E 최소 편집 권고).
    """
    text = (_ROOT / "tests" / "unit" / "ast" / "test_cycle264_scope_and_pins.py").read_text(
        encoding="utf-8",
    )
    stale = [
        i for i, line in enumerate(text.splitlines(), 1)
        if "핀을 갱신한다" in line or "이 핀을 갱신" in line
    ]
    assert not stale, (
        f"cycle264 파일 {stale} 줄이 여전히 '핀 갱신'을 예고한다 — cycle272 는 6/6 을 "
        "불변으로 남긴다(자문 §9 O-I). 예고 문장을 정정하라"
    )


# ===========================================================================
# G-272-10 — 시그니처 · 신뢰 목록 리터럴
# ===========================================================================

@pytest.mark.parametrize("rel,cls_name", [
    (_VB_REL, "VolatilityBreakoutStrategy"),
    (_LTV_REL, "LongTailVolatilityStrategy"),
])
def test_g272_10a_setter_signature_literals(rel, cls_name):
    """C10 — `(self, ticker, open_price, board="main", *, source="ws")`.

    기본값 리터럴이 **`"ws"`(불신)** 여야 WS 3 호출부(스케줄러 1차 폴링 · VB·LTV 인라인)
    가 **한 글자도 안 바뀌고** 거부된다 = `check_buy_signal` byte 동일 = 핀 6개 불변.
    """
    tree, _src = _tree(_ROOT / rel)
    fn = _method(tree, cls_name, _SETTER)
    assert fn is not None, f"{rel}: `{_SETTER}` 를 찾지 못했다"

    pos = [a.arg for a in fn.args.args]
    assert pos == ["self", "ticker", "open_price", "board"], f"{rel}: 위치 인자 {pos}"
    kwonly = [a.arg for a in fn.args.kwonlyargs]
    assert kwonly == ["source"], (
        f"{rel}: `source` 는 **키워드 전용**이어야 한다 — 실측 kwonly={kwonly}"
    )
    assert fn.args.defaults and isinstance(fn.args.defaults[-1], ast.Constant) \
        and fn.args.defaults[-1].value == "main", f"{rel}: board 기본값이 'main' 이 아니다"
    kwd = fn.args.kw_defaults[0]
    assert isinstance(kwd, ast.Constant) and kwd.value == "ws", (
        f"{rel}: source 기본값 리터럴이 'ws' 가 아니다 — 실측 "
        f"{getattr(kwd, 'value', kwd)!r}. 기본값이 'rest' 면 게이트가 아무것도 막지 않는다"
    )


def test_g272_10b_trusted_sources_literal_is_rest_only():
    """C10 — `_TRUSTED_MAIN_SOURCES = ("rest",)`.

    채널 분리(P1-7 B) 뒤 `"ws_krx"` 를 꽂을 seam 이다. 지금 `"ws"` 가 들어가면
    이 사이클이 통째로 무효가 된다(뮤테이션 M1: `("rest",)` → `("rest","ws")`).
    """
    assert _LEAF.exists(), f"{_LEAF.relative_to(_ROOT)} 가 없다 — cycle272 미구현(Red)"
    module_tree, _ = _tree(_LEAF)
    found = None
    for node in module_tree.body:
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == "_TRUSTED_MAIN_SOURCES":
                    found = node.value
    assert found is not None, "`_TRUSTED_MAIN_SOURCES` 모듈 상수를 찾지 못했다"
    assert isinstance(found, ast.Tuple), "튜플 리터럴이어야 한다(리스트는 런타임 변조 가능)"
    values = [e.value for e in found.elts if isinstance(e, ast.Constant)]
    assert values == ["rest"], f"실측 {values}"


def test_g272_10c_strategies_do_not_import_each_other():
    """C10 — VB·LTV 는 서로를 import 하지 않는다(cycle262 G-262-9 답습).

    같은 키를 **각자의** `DEFAULT_PARAMS` 에 두는 이유가 부분 롤백("VB 만 off")이다.
    한쪽이 다른 쪽을 참조하면 그 독립성이 조용히 사라진다.
    """
    for rel, other in ((_VB_REL, "long_tail_volatility"), (_LTV_REL, "volatility_breakout")):
        tree, _src = _tree(_ROOT / rel)
        hits = [
            n.module for n in ast.walk(tree)
            if isinstance(n, ast.ImportFrom) and n.module and other in n.module
        ]
        assert not hits, f"{rel} 가 {other} 를 import 한다 — {hits}"


# ===========================================================================
# G-272-24 / G-272-26 — scheduler 호출부
# ===========================================================================

def _setter_calls_in(tree: ast.AST) -> list[ast.Call]:
    return [
        n for n in ast.walk(tree)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
        and n.func.attr == _SETTER
    ]


def test_g272_24a_drain_next_day_clear_immediately_follows_main_confirm():
    """C24 — `start()` 의 호출 **순서는 불변**이다.

    익일청산이 09:00:14 → 09:00:05 로 앞당겨지는 것은 `owns_board` 가 confirm 의 **소요**를
    0 으로 만든 **부수 효과**이지 순서 변경이 아니다. 순서를 손대면 개장 직후 시장가
    청산이 시가 확정 전에 나가는 다른 사고가 된다.
    """
    tree, _src = _tree(_SCHEDULER)
    fn = _method(tree, "TradingScheduler", "start")
    assert fn is not None, "`TradingScheduler.start` 를 찾지 못했다"

    def _is_main_confirm(stmt) -> bool:
        if not (isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Await)):
            return False
        call = stmt.value.value
        if not (isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute)
                and call.func.attr == "_confirm_breakout_open_prices"):
            return False
        return any(
            kw.arg == "board" and isinstance(kw.value, ast.Constant)
            and kw.value.value == "main" for kw in call.keywords
        )

    def _is_drain(stmt) -> bool:
        return (
            isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Await)
            and isinstance(stmt.value.value, ast.Call)
            and isinstance(stmt.value.value.func, ast.Attribute)
            and stmt.value.value.func.attr == "_drain_pending_next_day_clear"
        )

    pairs = 0
    for node in ast.walk(fn):
        body = getattr(node, "body", None)
        if not isinstance(body, list):
            continue
        for a, b in zip(body, body[1:]):
            if _is_main_confirm(a):
                assert _is_drain(b), (
                    "`_confirm_breakout_open_prices(board='main')` 바로 뒤가 "
                    f"`_drain_pending_next_day_clear` 가 아니다 — {ast.dump(b)[:120]}"
                )
                pairs += 1
    assert pairs == 1, (
        f"`start()` 안 board='main' confirm 호출을 정확히 1개 찾아야 한다 — 실측 {pairs}"
    )


def test_g272_26a_only_rest_fallback_declares_source():
    """C26 — `scheduler.py` 의 두 setter 호출 중 **REST 폴백만** `source="rest"` 를 명시한다.

    1차 WS 폴링(`:1662`)이 `source=` 를 붙이면 오염된 WS 캐시가 그대로 통과한다.
    기본값 `"ws"` 에 기대는 것이 계약이다.
    """
    tree, _src = _tree(_SCHEDULER)
    calls = _setter_calls_in(tree)
    assert len(calls) == 2, (
        f"scheduler.py 의 `{_SETTER}` 호출은 2곳(1차 WS 폴링 · 2차 REST 폴백)이어야 한다 — "
        f"실측 {len(calls)}곳"
    )
    with_source = [
        c for c in calls
        if any(kw.arg == "source" and isinstance(kw.value, ast.Constant)
               and kw.value.value == "rest" for kw in c.keywords)
    ]
    assert len(with_source) == 1, (
        f"`source=\"rest\"` 를 명시한 호출이 정확히 1곳이어야 한다 — 실측 {len(with_source)}곳"
    )
    without = [c for c in calls if c not in with_source]
    assert all(not any(kw.arg == "source" for kw in c.keywords) for c in without), (
        "1차 WS 폴링 호출이 `source=` 를 명시했다 — 기본 'ws'(불신) 의존이 계약이다"
    )


@pytest.mark.parametrize("rel", [_VB_REL, _LTV_REL])
def test_g272_26b_inline_confirm_does_not_declare_source(rel):
    """C26 — 전략 인라인 확정(`check_buy_signal` 안)은 `source=` 를 **명시하지 않는다**.

    명시하면 그 순간 `check_buy_signal` 이 바뀌어 cycle264 sha 핀 6개 중 2개가 깨진다
    = 무접촉 6종의 기계적 증거가 사라진다.
    """
    tree, _src = _tree(_ROOT / rel)
    inline = [
        c for c in _setter_calls_in(tree)
        if isinstance(c.func.value, ast.Name) and c.func.value.id == "self"
    ]
    assert inline, f"{rel}: 인라인 `self.{_SETTER}(...)` 호출을 찾지 못했다(기준선 부재)"
    for c in inline:
        assert not any(kw.arg == "source" for kw in c.keywords), (
            f"{rel} line {c.lineno}: 인라인 호출이 `source=` 를 명시했다"
        )


# ===========================================================================
# G-272-27 — scheduler 라인 예산
# ===========================================================================

def test_g272_27a_scheduler_line_cap():
    """C27 — `scheduler.py ≤ 3,899L`.

    cycle257 이 3,864L 로 내리고 **< 3,900** 을 영구 가드로 박았다. cycle264 가 순증 +34,
    cycle269 +2 를 먹어 현재 3,898 이고, cycle272 는 **순증 +1** 만 쓴다
    (본체는 전부 leaf `open_price_rest.py` 위임 — cycle233/259/264 패턴 답습).
    """
    lines = _SCHEDULER.read_text(encoding="utf-8").count("\n") + 1
    assert lines < 3900, (
        f"scheduler.py {lines}L — 상한 3,900L 초과. 새 코드는 leaf 로 민다"
    )


def test_g272_27b_line_cap_matches_cycle257_guard():
    """C27 — 이 파일의 상한 리터럴이 cycle257 영구 가드보다 **느슨하지 않다**.

    자체 가드가 리포의 실제 예산보다 느슨해 위반을 초록으로 덮던 결함(cycle264 적대 검증
    HIGH)의 재발 차단. 두 수가 갈라지면 항상 **더 조인 쪽**이 정본이다.
    """
    mine = set(re.findall(r"assert lines < (\d+)", Path(__file__).read_text(encoding="utf-8")))
    theirs = set(re.findall(
        r"assert count < (\d+)",
        (_ROOT / "tests" / "unit" / "ast"
         / "test_cycle257_ast_dead_code_removed.py").read_text(encoding="utf-8"),
    ))
    assert mine, "cycle272 라인 상한 단언을 찾지 못했다"
    assert theirs, "cycle257 라인 상한 단언을 찾지 못했다"
    assert min(int(c) for c in mine) <= min(int(c) for c in theirs), (
        f"cycle272 상한({sorted(mine)})이 cycle257({sorted(theirs)})보다 느슨하다"
    )


# ===========================================================================
# G-272-28 — 파라미터 · 범위 · 문서
# ===========================================================================

def test_g272_28a_runtime_dicts_exclude_key():
    """C28 — `PARAM_RANGES`/`INT_PARAMS` **미편입**(진입 정체성 상수).

    `_validate_recommendations` 가 화이트리스트 밖 키를 버리므로 미편입이 곧 AI 자동
    튜닝 차단이다. "KRX 시가를 쓸지 말지" 는 **자문이 흔들 값이 아니다.**
    """
    from src.engine.recommendation_engine import INT_PARAMS, PARAM_RANGES

    assert KEY not in PARAM_RANGES
    assert KEY not in INT_PARAMS


def test_g272_28b_recommendation_engine_source_has_no_key_literal():
    """C28 — 런타임 dict 만 보면 조건부 편입(`if ...: PARAM_RANGES[KEY] = ...`)을 놓친다."""
    text = _RECO.read_text(encoding="utf-8")
    hits = [i for i, line in enumerate(text.splitlines(), 1) if KEY in line]
    assert not hits, (
        f"`recommendation_engine.py` 소스에 `{KEY}` 리터럴(lines {hits}) — "
        "AI 자문 자동 적용 경로 편입 금지"
    )


def test_g272_28c_key_lives_in_exactly_vb_and_ltv_default_params():
    """C28 — 전략 `*.py` glob 전수에서 이 키를 `DEFAULT_PARAMS` 에 가진 파일은
    **정확히 {VB, LTV}** 이고 값 리터럴은 `"enforce"` 다.

    이것이 "키 부재 = 새 행위"(P0-1 역방향) 위험의 봉인이다 — DB 오버레이는
    라우트·`_load_strategy_config` 둘 다 `if key in params` 라 **알려진 키만** 덮으므로
    운영에서 키가 사라지는 경로는 **소스 삭제뿐**이고 그건 이 가드가 붉어진다.
    """
    owners: dict[str, object] = {}
    for path in _STRATEGY_DIR.rglob("*.py"):
        tree, _src = _tree(path)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Assign):
                continue
            if not any(isinstance(t, ast.Name) and t.id == "DEFAULT_PARAMS"
                       for t in node.targets):
                continue
            if not isinstance(node.value, ast.Dict):
                continue
            for k, v in zip(node.value.keys, node.value.values):
                if isinstance(k, ast.Constant) and k.value == KEY:
                    owners[path.relative_to(_ROOT).as_posix()] = getattr(v, "value", v)

    assert set(owners) == {_VB_REL, _LTV_REL}, (
        f"`{KEY}` 를 DEFAULT_PARAMS 에 둔 전략 파일이 {{VB, LTV}} 가 아니다 — 실측 {sorted(owners)}"
    )
    assert set(owners.values()) == {"enforce"}, (
        f"기본값 리터럴이 'enforce' 가 아니다 — 실측 {owners}"
    )


def test_g272_28c2_cycle264_killswitch_ban_drops_only_this_name():
    """C28 — cycle264 금지 목록에서 **`open_price_scope_mode` 하나만** 뺀다.

    `open_scope_observe_enabled`·`open_source_compare_enabled` 금지는 **유지**한다
    (관측은 끄고 켤 대상이 아니라는 계약 보존). 테스트 자체는 삭제하지 않는다.
    """
    text = (_ROOT / "tests" / "unit" / "ast" / "test_cycle264_scope_and_pins.py").read_text(
        encoding="utf-8",
    )
    tree = ast.parse(text)
    fn = _func(tree, "test_c7_no_killswitch_param_introduced")
    assert fn is not None, "cycle264 킬스위치 금지 테스트가 사라졌다 — 삭제 금지 계약"
    banned = {
        n.value for n in ast.walk(fn)
        if isinstance(n, ast.Constant) and isinstance(n.value, str)
        and n.value.endswith(("_mode", "_enabled"))
    }
    assert KEY not in banned, (
        f"cycle264 금지 목록에 아직 `{KEY}` 가 있다 — cycle272 킬스위치가 그 이름을 쓴다"
    )
    assert {"open_scope_observe_enabled", "open_source_compare_enabled"} <= banned, (
        f"관측 킬스위치 금지가 함께 사라졌다 — 실측 {sorted(banned)}"
    )


def test_g272_28d_untouchable_areas_untouched():
    """C28 — 8영역 9경로 **diff 0**.

    ⚠️ **사이클 한정 — cycle272 커밋 직후 이 테스트를 삭제한다.**
    `git diff HEAD` 는 커밋 뒤 공허해지고 다음 편집에서 무조건 RED 가 된다
    (cycle240 A11b · cycle252 G-252-5b · cycle262 C12). 영구 가드는
    `test_cycle222a3_ast_followup_fixes.py` 가 들고 있다.

    leaf 는 `scanner.ticker_prices` 를 **읽기만** 하므로 이 사이클의 8영역 접촉은 0 이고,
    따라서 **자매 sha 핀 4곳도 손대지 않는다**.
    """
    changed = _changed_paths()
    offenders = sorted(
        p for p in changed
        if p in _UNTOUCHABLE_FILES or p.startswith(_UNTOUCHABLE_DIRS)
    )
    assert not offenders, (
        f"8영역이 변경됐다: {offenders} — cycle272 의 계약은 접촉 0 이다. "
        "정말 필요하면 사용자 승인 + 자매 sha 핀 4곳 등록 절차를 따른다"
    )


def test_g272_28e_other_strategy_files_untouched():
    """C28 — 전략 7파일 중 VB·LTV 외 **5파일 diff 0**.

    ⚠️ **사이클 한정 — cycle272 커밋 직후 삭제.**
    """
    changed = set(_changed_paths())
    offenders = sorted(set(_OTHER_STRATEGY_FILES) & changed)
    assert not offenders, f"VB·LTV 외 전략 파일이 변경됐다: {offenders}"


def test_g272_28f_docs_declare_the_new_key():
    """C28 — 정본 문서 2곳에 새 키가 기재된다(cycle254 G-254-4 문서 가드 패턴).

    `DEFAULT_PARAMS` 변경 시 `_workspace/00_leader_trading_rules.md` 동기화는 루트
    CLAUDE.md 의 명문 의무이고, `src/engine/strategies/CLAUDE.md` 는 전략 계약의 진실의
    원천이다. 문서에 없으면 다음 사이클이 이 키의 존재를 모른 채 기본값을 뒤집는다.
    """
    missing = [
        rel for rel in (
            "_workspace/00_leader_trading_rules.md",
            "src/engine/strategies/CLAUDE.md",
        )
        if KEY not in (_ROOT / rel).read_text(encoding="utf-8")
    ]
    assert not missing, f"정본 문서에 `{KEY}` 기재 누락: {missing}"


def test_g272_28g_markers_live_only_in_allowed_files():
    """C28 — cycle272 마커 4종이 접촉 범위 밖으로 새지 않는다.

    소스 스캔은 `rglob`(미추적 파일 포함) — `git grep` 은 Green 이 새로 만든 파일을
    로컬에서 놓친다(cycle259 S4b).
    """
    allowed = {"src/engine/open_price_rest.py", _VB_REL, _LTV_REL}
    offenders: dict[str, list[str]] = {}
    for path in _SRC.rglob("*.py"):
        rel = path.relative_to(_ROOT).as_posix()
        if rel in allowed:
            continue
        text = path.read_text(encoding="utf-8")
        hits = [m for m in _MARKERS if m in text]
        if hits:
            offenders[rel] = hits
    assert not offenders, f"cycle272 마커가 접촉 범위 밖으로 샜다: {offenders}"


def test_g272_28h_leaf_uses_shared_cap_and_trace_helpers():
    """C28 — 관측 cap 은 `KstDailyEmitCap`, 자기 실패 흔적은 `observer_trace` 를 쓴다.

    cycle258 이 4방언으로 갈라져 있던 것을 하나로 모은 규약이다. 신규 cap 클래스 정의
    금지 + 무흔적 `pass` 금지.
    """
    assert _LEAF.exists(), f"{_LEAF.relative_to(_ROOT)} 가 없다 — cycle272 미구현(Red)"
    tree, src = _tree(_LEAF)
    assert "KstDailyEmitCap" in src, "cap 은 `KstDailyEmitCap` 재사용이 계약이다"
    assert "trace_observer_failure" in src, (
        "관측기 자기 실패는 `observer_trace.trace_observer_failure` 로 흔적을 남긴다"
    )
    new_caps = [
        n.name for n in ast.walk(tree)
        if isinstance(n, ast.ClassDef) and "Cap" in n.name
    ]
    assert not new_caps, f"신규 cap 클래스 정의 금지 — {new_caps}"
    assert "write_log" not in src, (
        "leaf 는 `logger` 만 쓴다(20:10 리포트가 `system_logs` 를 파싱한다)"
    )


def test_g272_28i_leaf_does_not_write_scanner_state():
    """C28/C20 — leaf 는 `scanner` 의 어떤 전역도 **대입하지 않는다**(8영역 read-only).

    `ticker_prices[...] = ...` / `scanner.X = ...` 형태의 쓰기를 정적으로 막는다.
    """
    assert _LEAF.exists(), f"{_LEAF.relative_to(_ROOT)} 가 없다 — cycle272 미구현(Red)"
    tree, _src = _tree(_LEAF)
    bad: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Assign, ast.AugAssign)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        for t in targets:
            if isinstance(t, ast.Subscript):
                base = t.value
                name = getattr(base, "id", None) or getattr(base, "attr", None)
                if name in ("ticker_prices", "ticker_names", "ticker_prev_close"):
                    bad.append(f"line {node.lineno}: {name}[...] 대입")
            if isinstance(t, ast.Attribute) and isinstance(t.value, ast.Name) \
                    and t.value.id == "scanner":
                bad.append(f"line {node.lineno}: scanner.{t.attr} 대입")
    assert not bad, f"leaf 가 scanner 상태를 쓴다(8영역 read-only 위반): {bad}"
