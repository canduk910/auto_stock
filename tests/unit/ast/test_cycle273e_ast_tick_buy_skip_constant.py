"""cycle273e Red (AST) — F-3 의 **구조 계약**: 명시 상수 · 판정 축 · 삽입 위치.

명세 = `_workspace/red/cycle273e_kojiro_gap_gate_spec.md`
자문 = `_workspace/domain_consult/cycle273_kojiro_gap_gate_20260910.md` §3.6·§4(R9/R10)
행위 가드 = `test_cycle273e_risk_kojiro_skip_buy.py`

| # | 가드 | 지키는 것 | HEAD |
|---|---|---|---|
| R10-a | `_TICK_BUY_EVAL_SKIP_STRATEGIES` 가 **모듈 상수 frozenset** 이고 멤버 = {donchian_swing, kojiro} (런타임) | 세 번째 멤버가 조용히 들어오는 것 차단 | **RED** |
| R10-b | 같은 사실을 **소스 리터럴**로도 확인 (런타임 dict 조작 우회 차단) | cycle262 G-262-1 의 이중 확인 관례 | **RED** |
| R9 | skip 판정이 **`strategy_id` 문자열만** 쓴다 — `tradable_boards`/`sizing_mode`/`config.params` 참조 0건 | 설정 하나가 매수 평가 경로를 바꾸는 커플링 차단(청산 축 AST 금기와 동형) | **RED** |
| R-pos | skip 이 `is_ticker_blocked_for_buy` **뒤** · `check_buy_signal` **바로 앞** | `[tradable_skip]`·`[risk_silent_skip]` 카운터 드리프트 차단(자문 §3.6 ⚠️) | **RED** |
| R-sep | `_PRE_MARKET_EXIT_EVAL_STRATEGIES`(청산 축) 는 **무접촉** — kojiro 미포함 | 두 목록은 다른 축이다(UB §1.4) | GREEN(영구) |
| R-kill | `DEFAULT_PARAMS` 신규 키 0개 — 킬스위치 파라미터 금지 | 자문 §3.3 | GREEN(영구) |

## 규약
`ast.dump` sha 핀 금지(3.12 CI ↔ 3.13 로컬 출력 상이 — cycle256 G-250-5) ·
`git grep`/`git ls-files` 금지(미추적 파일 실종 — cycle259 S4b) ·
기준선 소실은 명시 FAIL(vacuous PASS 차단, 사이클 224).
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

import src as _src_pkg
from src.engine import risk as risk_mod

pytestmark = pytest.mark.unit

_SRC = Path(_src_pkg.__file__).resolve().parent
_RISK = _SRC / "engine" / "risk.py"

_CONST = "_TICK_BUY_EVAL_SKIP_STRATEGIES"
_EXPECTED = frozenset({"donchian_swing", "kojiro"})
_EXIT_CONST = "_PRE_MARKET_EXIT_EVAL_STRATEGIES"

_FORBIDDEN_TOKENS = ("tradable_boards", "sizing_mode", "params", "config")


def _tree() -> ast.Module:
    return ast.parse(_RISK.read_text(encoding="utf-8"))


def _func(tree: ast.AST, name: str):
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    return None


def _module_assign(tree: ast.Module, name: str) -> ast.Assign | None:
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == name for t in node.targets
        ):
            return node
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) \
                and node.target.id == name:
            return node  # type: ignore[return-value]
    return None


def _calls_named(node: ast.AST, name: str) -> list[ast.Call]:
    out = []
    for sub in ast.walk(node):
        if not isinstance(sub, ast.Call):
            continue
        fn = sub.func
        label = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", None)
        if label == name:
            out.append(sub)
    return out


def _skip_if(fn: ast.AST) -> ast.If | None:
    """`on_tick` 안에서 `_TICK_BUY_EVAL_SKIP_STRATEGIES` 를 참조하는 `If` 노드.

    (가) 리터럴 확장안을 채택했다면 상수가 없으므로 None 이 되고 R10 이 먼저 붉어진다.
    """
    for node in ast.walk(fn):
        if not isinstance(node, ast.If):
            continue
        names = {sub.id for sub in ast.walk(node.test) if isinstance(sub, ast.Name)}
        if _CONST in names:
            return node
    return None


# ---------------------------------------------------------------------------
# R10 — 명시 상수 + 멤버 동결 (런타임 · 소스 이중)
# ---------------------------------------------------------------------------
def test_r10a_constant_exists_and_members_frozen_runtime():
    """RED (HEAD) — 오늘은 `strategy.strategy_id == "donchian_swing"` 리터럴 비교뿐이다."""
    value = getattr(risk_mod, _CONST, None)
    assert value is not None, (
        f"`risk.{_CONST}` 미존재 — 자문 §3.6 권고 = 명시 상수(나안). "
        f"`{_EXIT_CONST}`(:79) 관례와 동형"
    )
    assert isinstance(value, frozenset), f"{_CONST} 는 frozenset 이어야 한다 (실측 {type(value)})"
    assert value == _EXPECTED, (
        f"{_CONST} 멤버가 {sorted(value)} — 기대 {sorted(_EXPECTED)}. "
        f"세 번째 전략이 조용히 들어오면 그 전략의 WS 매수가 통째로 죽는다"
    )


def test_r10b_constant_literal_in_source():
    """RED (HEAD) — 소스 리터럴로도 확인(런타임 조작 우회 차단, cycle262 G-262-1 관례)."""
    tree = _tree()
    node = _module_assign(tree, _CONST)
    assert node is not None, f"모듈 레벨 `{_CONST}` 대입이 소스에 없다"

    call = node.value
    assert isinstance(call, ast.Call) and getattr(call.func, "id", None) == "frozenset", (
        f"{_CONST} 는 `frozenset({{...}})` 리터럴이어야 한다"
    )
    members: set[str] = set()
    for arg in call.args:
        for sub in ast.walk(arg):
            if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
                members.add(sub.value)
    assert members == _EXPECTED, f"소스 리터럴 멤버 {sorted(members)} ≠ {sorted(_EXPECTED)}"


# ---------------------------------------------------------------------------
# R9 — 판정 축은 strategy_id 문자열 하나
# ---------------------------------------------------------------------------
def test_r9_skip_decision_uses_strategy_id_only():
    """RED (HEAD) — 기준선(상수 참조 If)이 아직 없다.

    청산 축 금기(`tradable_boards` 로 청산을 게이팅 금지 — 매수 설정이 청산 규약을
    바꾸는 커플링)의 **반대 방향** 동형이다. 매수 평가 경로가 설정 값으로 갈리면
    DB 토글 하나가 전략의 매수 배관을 바꾼다.
    """
    fn = _func(_tree(), "on_tick")
    assert fn is not None, "기준선 소실 — RiskManager.on_tick 을 찾지 못했다"

    node = _skip_if(fn)
    assert node is not None, (
        f"`on_tick` 안에 `{_CONST}` 를 보는 skip 분기가 없다"
    )

    tokens: set[str] = set()
    for sub in ast.walk(node.test):
        if isinstance(sub, ast.Name):
            tokens.add(sub.id)
        elif isinstance(sub, ast.Attribute):
            tokens.add(sub.attr)
        elif isinstance(sub, ast.Constant) and isinstance(sub.value, str):
            tokens.add(sub.value)

    assert "strategy_id" in tokens, "판정이 `strategy.strategy_id` 를 쓰지 않는다"
    banned = sorted(t for t in tokens if t in _FORBIDDEN_TOKENS)
    assert banned == [], (
        f"skip 판정이 설정 값을 참조한다 — {banned}. 판정은 strategy_id 문자열만 쓴다"
    )


# ---------------------------------------------------------------------------
# R-pos — 삽입 위치 (관측 지표 드리프트 차단)
# ---------------------------------------------------------------------------
def test_rpos_skip_sits_between_blocked_guard_and_buy_signal():
    """RED (HEAD) — 기준선(상수 참조 If) 부재.

    앞으로 옮기면 `[tradable_skip]`·`[risk_silent_skip]` 카운터와
    `is_ticker_blocked_for_buy` 호출 횟수가 바뀐다(= 행위 변경 범위 확대, 자문 §3.6).
    행위 가드 R4/R5 와 짝이다.
    """
    fn = _func(_tree(), "on_tick")
    assert fn is not None, "기준선 소실 — on_tick 부재"

    node = _skip_if(fn)
    assert node is not None, f"`{_CONST}` 참조 skip 분기 부재"

    blocked = _calls_named(fn, "is_ticker_blocked_for_buy")
    buy = _calls_named(fn, "check_buy_signal")
    assert blocked and buy, (
        f"기준선 소실 — on_tick 안 is_ticker_blocked_for_buy={len(blocked)} "
        f"check_buy_signal={len(buy)}"
    )

    assert node.lineno > max(c.lineno for c in blocked), (
        "skip 이 중복 매수 가드보다 앞에 있다 — 호출 횟수가 조용히 줄어든다"
    )
    assert node.lineno < min(c.lineno for c in buy), (
        "skip 이 `check_buy_signal` 뒤에 있다 — 매수 평가를 막지 못한다"
    )

    exit_calls = _calls_named(fn, "check_exit_signal")
    assert exit_calls, "기준선 소실 — on_tick 안 check_exit_signal 부재"
    assert node.lineno > max(c.lineno for c in exit_calls), (
        "🔴 skip 이 청산 평가보다 앞에 있다 — kojiro 손절이 죽는다(R2/R3 와 짝)"
    )


# ---------------------------------------------------------------------------
# R-sep / R-kill — 청산 축 무접촉 · 킬스위치 파라미터 금지
# ---------------------------------------------------------------------------
def test_rsep_exit_whitelist_untouched():
    """GREEN(영구) — 매수 skip 과 프리장 **청산** 보류 화이트리스트는 다른 축이다.

    kojiro 를 `_PRE_MARKET_EXIT_EVAL_STRATEGIES` 에 넣는 것은 F-3 과 **무관한**
    청산 규약 변경이며 별도 결정 사항이다(UB §1.4 혼동 주의).
    """
    value = getattr(risk_mod, _EXIT_CONST, None)
    assert value is not None, f"기준선 소실 — `{_EXIT_CONST}` 부재"
    assert value == frozenset({"long_tail_volatility"}), (
        f"청산 축 화이트리스트가 바뀌었다 — {sorted(value)}"
    )


def test_rkill_no_killswitch_param_key():
    """GREEN(영구) — 킬스위치를 `DEFAULT_PARAMS` 키로 두지 않는다(자문 §3.3).

    8영역 `risk.py` 가 전략 `params` 를 읽어 매수 경로를 분기하게 되는 순간
    청산 축 AST 금기와 동형의 커플링이 생긴다. 롤백은 1행 revert 로 충분하다
    (kojiro 매수 창은 09:05~09:30 뿐 — 장중 롤백 수요가 구조적으로 없다).
    """
    src = _RISK.read_text(encoding="utf-8")
    for token in ("tick_buy_eval_enabled", "tick_buy_skip_enabled", "kojiro_tick_buy"):
        assert token not in src, f"킬스위치 파라미터 후보 `{token}` 가 risk.py 에 들어왔다"

    strategies_dir = _SRC / "engine" / "strategies"
    for path in strategies_dir.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "tick_buy_eval_enabled" not in text, (
            f"{path.name} 의 DEFAULT_PARAMS 에 킬스위치 키가 들어왔다"
        )
