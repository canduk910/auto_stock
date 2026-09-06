"""cycle262 Red (AST) — 09:00 직후 매수 보류의 **구조적 계약** 봉인.

자문 정본 = `_workspace/consult/2026-09-06_open_entry_hold.md`
행위 가드 = `tests/unit/engine/strategies/test_cycle262_open_entry_hold.py`

**Red 단계 — 테스트만. `src/` 미변경.** 행위 테스트로는 잡히지 않는 것만 정적으로 고정한다.

| # | 가드 | 지키는 것 |
|---|---|---|
| G-262-1 | `open_entry_hold_secs` ∉ `PARAM_RANGES`/`INT_PARAMS` (런타임 dict + **소스 리터럴** 이중) | C11 — 진입 정체성 상수의 AI 자동 튜닝 차단 |
| G-262-2 | 키는 **VB·LTV 두 파일에만**(전략 glob 전수), 값 90, `DEFAULT_PARAMS` 안 | C1 + 범위 봉인 |
| G-262-3 | 보류 참조가 `_prev_price` **쓰기보다 뒤** (VB 는 계좌 게이트 호출보다도 뒤) | C4·C6 — 최상단 배치 뮤테이션 검출 |
| G-262-4 | 보류 참조 함수에 naive `datetime.now()` 0건 ∧ tz-aware `datetime.now(tz)` ≥1 | C3 — 컨테이너 `TZ` 의존 차단(cycle229 G-1 답습) |
| G-262-5 | 보류 참조 함수에 보드 리터럴·`tradable_boards` 토큰 0건 | C5 — 시간창 단독 판정 |
| G-262-6 | cap 은 `KstDailyEmitCap` 재사용 — **신규 cap 클래스 정의 0**, `now` 키워드 전용 | C9 |
| G-262-7a/b/c | 마커 2종 존재 ∧ emit 사이트가 `Try` 하위 ∧ **흡수기가 bare `except Exception`** ∧ `write_log` 0건 | C10 — 관측 실패가 매수 판정을 못 바꾼다 |
| G-262-7d | 두 emit 모두 **peek → 로그 → mark** 순서(lineno 부등식) | cycle226 D-3 — 로그 자기실패 1회가 그날의 관측을 지우지 않는다 |
| G-262-7e | config cap 키가 **값-민감**(f-string 보간, 상수 문자열 금지) | 장중 PUT 롤백 확인 채널 보존(cycle245 R1 사각) |
| G-262-8 | `check_exit_signal`·`calc_buy_quantity` 에 보류 토큰 0건 | 청산·수량 축 무오염 |
| G-262-9 | 두 전략 파일이 서로를 import 하지 않는다 | 파일 간 결합 회피(cycle229 G-4 답습) |

## 비-공허성

G-3/4/5/6/7 은 전부 "보류 토큰을 참조하는 함수" 를 기준선으로 잡고, **그 함수가 하나도
없으면 명시 FAIL** 시킨다(사이클 224 의 vacuous PASS 재발 차단 — 그 가드는 기준선을
검사 대상 자신에서 유도해 뮤테이션 전후 모두 통과했다). 따라서 Green 이전에는 전부 RED 다.

7d 는 마커 emit 을 담은 함수가 **2개 미만이면 FAIL**(config·blocked 두 지점), 7e 는
config 마커를 싣는 함수가 정확히 1개가 아니면 FAIL 이다 — 기준선이 사라지면 조용히
통과하지 않는다.

## 2026-09-06 적대 검증 반영

`_has_try_ancestor` 만 보던 7b 는 **핸들러를 좁히는** 뮤테이션(`except Exception` →
`except ZeroDivisionError`)을 통과시켰다. 7b 가 이제 `ast.ExceptHandler.type` 까지 보고,
7d·7e 는 그때 함께 ESCAPED 였던 mark/log 순서·cap 키 값-민감성을 정적으로 봉인한다.
셋 다 행위 가드(`test_c10_4` · `test_c7_7`/`test_c8_6` · `test_c7_6`)와 짝이다.

## `ast.dump` sha 핀을 쓰지 않는 이유

파이썬 3.12(CI)와 3.13(로컬)의 `ast.dump` 출력이 달라 로컬 초록·CI 실패가 난다
(cycle256 G-250-5 · cycle259 S4a 실측). 이 파일은 구조 술어만 검사하고 sha 를 핀하지 않는다.
소스 스캔에 `git grep`/`git ls-files` 도 쓰지 않는다 — 추적 파일만 보므로 Green 이 새로
만든 미추적 파일을 로컬에서 놓친다(cycle259 S4b). 전부 `Path.rglob` + AST 다.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from tests.unit.ast._ast_helpers import read_module_source as _read

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parents[3]
_STRATEGY_DIR = _ROOT / "src" / "engine" / "strategies"
_RECO = _ROOT / "src" / "engine" / "recommendation_engine.py"

KEY = "open_entry_hold_secs"
_MARKERS = ("[open_entry_hold_config]", "[open_entry_hold_blocked]")
_HOLD_TOKENS = (KEY, "open_entry_hold")

_VB = "src/engine/strategies/volatility_breakout.py"
_LTV = "src/engine/strategies/long_tail_volatility.py"
_TARGETS = {"vb": _VB, "ltv": _LTV}
_IDS = list(_TARGETS)
_RELS = [_TARGETS[k] for k in _IDS]

_BOARD_LITERALS = {"main", "pre_nxt", "post_nxt", "krx_open", "krx_after"}


# ---------------------------------------------------------------------------
# 헬퍼
# ---------------------------------------------------------------------------
def _tree(rel: str) -> tuple[ast.Module, str]:
    src = _read(_ROOT / rel)
    return ast.parse(src), src


def _funcs(tree: ast.Module) -> list[ast.FunctionDef | ast.AsyncFunctionDef]:
    return [
        n for n in ast.walk(tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]


def _func(tree: ast.Module, name: str):
    for n in _funcs(tree):
        if n.name == name:
            return n
    return None


def _mentions_hold(node: ast.AST) -> bool:
    """노드 하위에 보류 토큰(문자열 상수 또는 식별자)이 있는가."""
    for sub in ast.walk(node):
        if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
            if any(tok in sub.value for tok in _HOLD_TOKENS):
                return True
        elif isinstance(sub, ast.Name) and any(tok in sub.id for tok in _HOLD_TOKENS):
            return True
        elif isinstance(sub, ast.Attribute) and any(tok in sub.attr for tok in _HOLD_TOKENS):
            return True
    return False


def _hold_funcs(tree: ast.Module) -> list:
    """보류 토큰을 참조하는 함수 목록 — 이 파일 모든 가드의 기준선."""
    return [f for f in _funcs(tree) if _mentions_hold(f)]


def _require_hold_funcs(rel: str, tree: ast.Module) -> list:
    fns = _hold_funcs(tree)
    assert fns, (
        f"{rel} 에 `{KEY}` 를 참조하는 함수가 하나도 없다 — cycle262 미구현(RED) 또는 "
        "키 이름이 계약과 다르다. 이 가드는 기준선 부재를 조용한 PASS 로 넘기지 않는다"
    )
    return fns


def _first_lineno(node: ast.AST, predicate) -> int | None:
    hits = [sub.lineno for sub in ast.walk(node)
            if predicate(sub) and hasattr(sub, "lineno")]
    return min(hits) if hits else None


def _is_prev_price_write(sub: ast.AST) -> bool:
    """`self._prev_price[t][board] = current_price` 형태의 대입 여부."""
    if not isinstance(sub, ast.Assign):
        return False
    for tgt in sub.targets:
        for inner in ast.walk(tgt):
            if isinstance(inner, ast.Attribute) and inner.attr == "_prev_price":
                return True
    return False


def _is_datetime_now(node: ast.AST) -> bool:
    if not isinstance(node, ast.Call):
        return False
    fn = node.func
    if not isinstance(fn, ast.Attribute) or fn.attr not in ("now", "today"):
        return False
    base = fn.value
    if isinstance(base, ast.Name) and base.id == "datetime":
        return True
    return isinstance(base, ast.Attribute) and base.attr == "datetime"


def _is_naive_now(node: ast.AST) -> bool:
    return _is_datetime_now(node) and not node.args and not node.keywords


def _is_tz_now(node: ast.AST) -> bool:
    return _is_datetime_now(node) and bool(node.args or node.keywords)


def _is_display_only_now(node: ast.AST, table: dict[int, ast.AST]) -> bool:
    """`datetime.now().strftime(...)` = 표시 전용 — 이 가드의 범위 밖.

    VB `:910` / LTV `:705` 의 `buy_signals["time"]` 표기가 그 형태이고, cycle229 G-1 도
    같은 이유로 명시 제외했다. 그 줄까지 건드리면 이번 사이클이 **표시 행위**를 바꾸게 되고
    그건 명세에 없다. 나머지 naive 용법(비교·`.time()`·`.date()`)은 전부 잡힌다.
    """
    parent = table.get(id(node))
    return isinstance(parent, ast.Attribute) and parent.attr == "strftime"


def _parents(tree: ast.AST) -> dict[int, ast.AST]:
    table: dict[int, ast.AST] = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            table[id(child)] = parent
    return table


def _nearest_try(node: ast.AST, table: dict[int, ast.AST], stop: ast.AST):
    """`node` 를 감싸는 가장 안쪽 `ast.Try` (없으면 None). `stop` 함수 경계에서 멈춘다."""
    cur = node
    while id(cur) in table:
        cur = table[id(cur)]
        if isinstance(cur, ast.Try):
            return cur
        if cur is stop:
            return None
    return None


def _has_try_ancestor(node: ast.AST, table: dict[int, ast.AST], stop: ast.AST) -> bool:
    return _nearest_try(node, table, stop) is not None


def _catches_bare_exception(node: ast.Try) -> bool:
    """핸들러 중 `except Exception:`(또는 `except:`)가 있는가 = **모든** 예외 흡수."""
    for h in node.handlers:
        if h.type is None:
            return True
        if isinstance(h.type, ast.Name) and h.type.id == "Exception":
            return True
        if isinstance(h.type, ast.Tuple) and any(
            isinstance(e, ast.Name) and e.id == "Exception" for e in h.type.elts
        ):
            return True
    return False


def _marker_log_linenos(fn: ast.AST) -> list[int]:
    """마커 리터럴을 **인자로 싣는 호출**의 라인 목록."""
    out = []
    for n in ast.walk(fn):
        if not isinstance(n, ast.Call):
            continue
        if any(
            isinstance(a, ast.Constant) and isinstance(a.value, str)
            and any(m in a.value for m in _MARKERS)
            for a in n.args
        ):
            out.append(n.lineno)
    return out


def _cap_call_linenos(fn: ast.AST, attr: str) -> list[int]:
    """`<cap>.should_emit(...)` / `<cap>.mark_emitted(...)` 호출 라인 목록."""
    return [
        n.lineno for n in ast.walk(fn)
        if isinstance(n, ast.Call) and getattr(n.func, "attr", None) == attr
    ]


def _strategy_files() -> list[Path]:
    return sorted(p for p in _STRATEGY_DIR.glob("*.py") if p.name != "__init__.py")


def _default_params_value(tree: ast.Module, key: str):
    """클래스 본문의 `DEFAULT_PARAMS = {...}` 안에서 key 의 리터럴 값."""
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(t, ast.Name) and t.id == "DEFAULT_PARAMS" for t in node.targets):
            continue
        if not isinstance(node.value, ast.Dict):
            continue
        for k, v in zip(node.value.keys, node.value.values):
            if isinstance(k, ast.Constant) and k.value == key:
                return v
    return None


# ===========================================================================
# G-262-1 — AI 자동 튜닝 화이트리스트 미편입 (런타임 dict + 소스 리터럴 이중)
# ===========================================================================
def test_g262_1a_runtime_dicts_exclude_key() -> None:
    """G-262-1a: 런타임 dict 축.

    `_validate_recommendations` 가 `PARAM_RANGES` 화이트리스트 밖 키를 버리므로 미편입이
    곧 자동 적용 차단이다. 최근 손실을 목적함수로 삼는 튜너는 n≤20 에 과적합해
    "최근 손실 거래를 지우는 값" 으로 수렴한다(cycle223 선례).
    """
    from src.engine.recommendation_engine import INT_PARAMS, PARAM_RANGES

    assert KEY not in PARAM_RANGES
    assert KEY not in INT_PARAMS


def test_g262_1b_source_literal_excludes_key() -> None:
    """G-262-1b: 소스 리터럴 축 — dict 리터럴 안에 키 문자열이 아예 없어야 한다.

    런타임 dict 만 보면 조건부 편입(`if ...: PARAM_RANGES[KEY] = ...`)을 놓친다.
    cycle242 G-242-1 · cycle245 G-245-1 이 확립한 이중 검사 패턴 그대로.
    """
    tree, src = _tree("src/engine/recommendation_engine.py")
    assert _RECO.exists()

    hits: list[int] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value == KEY:
            hits.append(node.lineno)
    assert hits == [], (
        f"`recommendation_engine.py` 소스에 `{KEY}` 리터럴 (lines {hits}) — "
        "진입 정체성 상수는 자문/자동적용 경로에 등장하면 안 된다"
    )


# ===========================================================================
# G-262-2 — 키 스코프 = VB·LTV 두 파일 (전략 glob 전수)
# ===========================================================================
def test_g262_2_key_scope_is_exactly_vb_and_ltv() -> None:
    """G-262-2 (RED): 키는 두 전략 파일에만, `DEFAULT_PARAMS` 안에, 값 90.

    glob 전수라 (a) 미구현이면 RED (b) 8번째 전략이나 다른 전략이 무단 편입하면 RED.
    보류는 `[7]` 오염 경로를 타는 두 전략만의 지혈이다 — donchian 은 REST(KRX) `stck_oprc`,
    kojiro 는 매수창이 09:05~09:30 로 이미 창 밖, BFB/VCP 는 시그니처만이라 범위 밖이다.
    """
    with_key: dict[str, ast.AST | None] = {}
    for path in _strategy_files():
        tree = ast.parse(_read(path))
        val = _default_params_value(tree, KEY)
        rel = f"src/engine/strategies/{path.name}"
        if val is not None:
            with_key[rel] = val
        elif KEY in _read(path):
            with_key[rel] = None   # 파일엔 있는데 DEFAULT_PARAMS 밖 = 계약 위반

    assert set(with_key) == {_VB, _LTV}, (
        f"`{KEY}` 를 `DEFAULT_PARAMS` 에 가진 전략 파일 = {sorted(with_key)} "
        f"(기대 {sorted({_VB, _LTV})})"
    )
    for rel, val in with_key.items():
        assert isinstance(val, ast.Constant) and val.value == 90, (
            f"{rel}: `{KEY}` 기본값이 리터럴 90 이 아니다 ({ast.dump(val) if val else None})"
        )


# ===========================================================================
# G-262-3 — 판정 자리 (최상단 배치 뮤테이션 검출)
# ===========================================================================
def _blocked_marker_lineno(fn: ast.AST) -> int | None:
    """`[open_entry_hold_blocked]` 리터럴의 첫 등장 라인 = **판정 자리의 증거**.

    보류 판정 지점에서만 emit 되는 마커라 위치가 곧 게이트 위치다. `[open_entry_hold_config]`
    (카나리아)와 파라미터 읽기는 **의도적으로 제외** — config 는 "09:00 이후 첫 평가" 계약이라
    함수 최상단에 둘 수도 있고, 그 자유를 이 가드가 뺏으면 안 된다.
    """
    hits = [
        n.lineno for n in ast.walk(fn)
        if isinstance(n, ast.Constant) and isinstance(n.value, str)
        and "[open_entry_hold_blocked]" in n.value
    ]
    return min(hits) if hits else None


@pytest.mark.parametrize("rel", _RELS, ids=_IDS)
def test_g262_3a_hold_comes_after_baseline_write(rel: str) -> None:
    """G-262-3a (RED): 보류 판정(= blocked 마커)이 `_prev_price` **쓰기보다 뒤**.

    기준선(`_prev_price` 대입 라인)은 보류 코드 위치와 **독립**이라 공허하지 않다.
    보류를 그 위로 올리면 부등식이 즉시 뒤집힌다 — cycle233 C233-F1 이 계좌 게이트를
    최상단에서 내린 그 이유이자, 행위 가드 `test_c6_1` 의 정적 짝이다.
    """
    tree, _ = _tree(rel)
    fn = _func(tree, "check_buy_signal")
    assert fn is not None, f"{rel}: `check_buy_signal` 부재 — rig 전제 붕괴"

    baseline = _first_lineno(fn, _is_prev_price_write)
    assert baseline is not None, (
        f"{rel}: `check_buy_signal` 안 `_prev_price` 대입 부재 — 기준선이 사라졌다"
    )
    hold_line = _blocked_marker_lineno(fn)
    assert hold_line is not None, (
        f"{rel}: `check_buy_signal` 안에 `[open_entry_hold_blocked]` 0건 — 미구현(RED)이거나 "
        "판정이 함수 밖으로 나갔다(그러면 baseline 순서를 정적으로 보증할 수 없다)"
    )
    assert hold_line > baseline, (
        f"{rel}: 보류 판정(line {hold_line})이 `_prev_price` 갱신(line {baseline})보다 "
        "앞이다 — 보류 구간에 baseline 이 동결돼 해제 후 첫 틱이 거짓 돌파가 된다"
    )


def test_g262_3b_vb_hold_comes_after_account_gate() -> None:
    """G-262-3b (RED): VB 는 `_account_soft_gate_blocked` **바로 뒤**가 자리다.

    순서가 뒤집히면 `[open_entry_hold_blocked]`(would_buy 정본)가 계좌 차단 사건까지
    would_buy 로 기록해 이 사이클의 **핵심 산출물**이 오염된다.
    LTV 는 계좌 게이트가 함수 최상단이라(`:634-635`) 이 부등식이 자동 성립 — VB 만 검사한다.
    """
    tree, _ = _tree(_VB)
    fn = _func(tree, "check_buy_signal")
    gate = _first_lineno(fn, lambda s: (
        isinstance(s, ast.Call)
        and getattr(s.func, "attr", None) == "_account_soft_gate_blocked"
    ))
    assert gate is not None, "VB `check_buy_signal` 에 계좌 게이트 호출 부재 — 기준선 붕괴"

    hold_line = _blocked_marker_lineno(fn)
    assert hold_line is not None, (
        "VB `check_buy_signal` 안에 `[open_entry_hold_blocked]` 0건 (미구현 = RED)"
    )
    assert hold_line > gate, (
        f"VB: 보류 판정(line {hold_line})이 계좌 게이트(line {gate})보다 앞이다"
    )


# ===========================================================================
# G-262-4 — tz-aware 강제 (naive 0건 + 양성 짝)
# ===========================================================================
@pytest.mark.parametrize("rel", _RELS, ids=_IDS)
def test_g262_4_hold_time_is_tz_aware(rel: str) -> None:
    """G-262-4 (RED): 보류 참조 함수에 naive `datetime.now()` 0건 ∧ tz-aware ≥1.

    `TZ=Asia/Seoul` 이 깨지는 순간(도커 이미지 변경·CI·로컬) 창이 통째로 9시간 어긋나
    **막아야 할 때 열고, 열어야 할 때 막는다**. BFB `:929`/VCP `:1045` 의 naive 는
    P2-6 등재 결함이지 선례가 아니다 — 선례는 kojiro `:796` `datetime.now(KST).time()`.
    """
    tree, _ = _tree(rel)
    table = _parents(tree)
    fns = _require_hold_funcs(rel, tree)
    for fn in fns:
        naive = [
            n.lineno for n in ast.walk(fn)
            if _is_naive_now(n) and not _is_display_only_now(n, table)
        ]
        assert naive == [], (
            f"{rel}::{fn.name} 에 naive `datetime.now()` (lines {naive}) — "
            "컨테이너 TZ 의존. cycle229 AST 가드가 잡는 그 결함이다"
        )
    # 양성 짝은 **집합 존재**로 잰다 — 파라미터 리더 같은 순수 헬퍼가 시계를 안 보는 것은
    # 정상이므로 함수별로 강제하면 구현을 한 덩어리로 몰아넣게 된다.
    assert any(_is_tz_now(n) for fn in fns for n in ast.walk(fn)), (
        f"{rel}: 보류 참조 함수 어디에도 tz-aware `datetime.now(<tz>)` 가 없다 — "
        "시각 판정이 어디서 오는지 정적으로 확인되지 않는다"
    )


# ===========================================================================
# G-262-5 — 보드 무관 (시간창 단독)
# ===========================================================================
@pytest.mark.parametrize("rel", _RELS, ids=_IDS)
def test_g262_5_hold_has_no_board_coupling(rel: str) -> None:
    """G-262-5 (RED): 보류 참조 함수에 보드 리터럴·`tradable_boards` 토큰 0건.

    09:00:00~09:00:30 은 세션 트래커 30초 주기 탓에 보드가 `pre_nxt` 로 잡힐 수 있는데
    그건 stale 캐시 산물이다. 보드로 분기하면 그 30초가 통째로 구멍이 된다.
    `risk.py` 프리장 게이트가 "보드가 아니라 명시 상수로 판정" 을 AST 로 못 박은 것과 동형.

    ⚠️ `check_buy_signal` 은 착수 시점 보드 문자열 리터럴이 0건이다(보드는
    `_resolve_active_board()` 반환값으로만 흐른다) — 이 가드는 그 성질을 보존한다.
    """
    tree, _ = _tree(rel)
    for fn in _require_hold_funcs(rel, tree):
        lits = sorted({
            (n.lineno, n.value) for n in ast.walk(fn)
            if isinstance(n, ast.Constant) and n.value in _BOARD_LITERALS
        })
        assert lits == [], (
            f"{rel}::{fn.name} 에 보드 리터럴 {lits} — 보류는 **시간창 단독** 판정이다"
        )
        boards = [
            n.lineno for n in ast.walk(fn)
            if (isinstance(n, ast.Constant) and n.value == "tradable_boards")
            or (isinstance(n, ast.Name) and n.id == "tradable_boards")
            or (isinstance(n, ast.Attribute) and n.attr == "tradable_boards")
        ]
        assert boards == [], (
            f"{rel}::{fn.name} 에 `tradable_boards` 참조 (lines {boards}) — "
            "매수 목적 보드 설정이 보류 창을 바꾸는 커플링은 금지다"
        )


# ===========================================================================
# G-262-6 — cap 재사용 (`KstDailyEmitCap`), 신규 cap 클래스 금지
# ===========================================================================
@pytest.mark.parametrize("rel", _RELS, ids=_IDS)
def test_g262_6a_reuses_kst_daily_emit_cap(rel: str) -> None:
    """G-262-6a (RED): cap 은 `KstDailyEmitCap`(cycle258) 재사용 — 새 cap 클래스 금지.

    날짜 키 자기 리셋을 손으로 다시 짜면 `_reset_daily_state` 훅 의존/`_x_day` 필드
    누락 같은 22곳 반복 결함이 되살아난다.
    """
    tree, src = _tree(rel)
    _require_hold_funcs(rel, tree)

    assert "KstDailyEmitCap" in src, (
        f"{rel}: `KstDailyEmitCap` 미사용 — cycle258 표준 진입점을 재사용해야 한다"
    )
    homemade = [
        n.name for n in ast.walk(tree)
        if isinstance(n, ast.ClassDef) and "EmitCap" in n.name
    ]
    assert homemade == [], f"{rel}: 신규 cap 클래스 정의 {homemade} — 표준 클래스를 쓴다"


@pytest.mark.parametrize("rel", _RELS, ids=_IDS)
def test_g262_6b_now_is_keyword_only(rel: str) -> None:
    """G-262-6b (RED): `should_emit`/`mark_emitted` 는 위치 인자 1개(키) 뿐.

    `now` 는 `KstDailyEmitCap` 에서 **키워드 전용**이다 — 위치로 넘기면 TypeError 가
    관측 try 안에서 흡수돼 그날 관측이 통째로 사라진다(무증상).
    """
    tree, _ = _tree(rel)
    _require_hold_funcs(rel, tree)
    bad = []
    for n in ast.walk(tree):
        if not isinstance(n, ast.Call):
            continue
        name = getattr(n.func, "attr", None)
        if name in ("should_emit", "mark_emitted") and len(n.args) > 1:
            bad.append((n.lineno, name, len(n.args)))
    assert bad == [], f"{rel}: cap 호출에 위치 인자 2개 이상 {bad} — `now=` 는 키워드 전용"


# ===========================================================================
# G-262-7 — 마커 + 관측 실패 격리 (행위는 cap 밖)
# ===========================================================================
@pytest.mark.parametrize("rel", _RELS, ids=_IDS)
def test_g262_7a_markers_present(rel: str) -> None:
    """G-262-7a (RED): 마커 2종이 소스에 리터럴로 존재.

    `[open_entry_hold_blocked]` 는 이 사이클의 **핵심 산출물**이다 — 보류는 "무엇을 살
    뻔했는가" 를 지우므로 이 마커가 유일한 복원 수단이다(자문 §4.2). 없으면 지혈만 하고
    증거를 잃는다.
    """
    _, src = _tree(rel)
    missing = [m for m in _MARKERS if m not in src]
    assert missing == [], f"{rel}: 마커 부재 {missing}"


@pytest.mark.parametrize("rel", _RELS, ids=_IDS)
def test_g262_7b_emit_sites_are_inside_try(rel: str) -> None:
    """G-262-7b (RED): 마커를 싣는 모든 호출이 `Try` 하위.

    관측 예외가 `check_buy_signal` 을 뚫으면 `risk.on_tick` 이 그 종목의 나머지 평가를
    잃는다 — 관측 시정이 아니라 결함 주입이다(cycle237 TE-2 실증).
    """
    tree, _ = _tree(rel)
    table = _parents(tree)
    for fn in _require_hold_funcs(rel, tree):
        for node in ast.walk(fn):
            if not isinstance(node, ast.Call):
                continue
            carries = any(
                isinstance(a, ast.Constant) and isinstance(a.value, str)
                and any(m in a.value for m in _MARKERS)
                for a in node.args
            )
            if not carries:
                continue
            enclosing = _nearest_try(node, table, fn)
            assert enclosing is not None, (
                f"{rel}::{fn.name}:{node.lineno} 마커 emit 이 try 밖이다 — "
                "관측 실패가 매수 판정을 바꾼다"
            )
            # ⚠️ try 존재만 보면 **핸들러를 좁히는** 뮤테이션을 못 잡는다(적대 검증
            # HIGH — `except Exception` → `except ZeroDivisionError` 가 전 스위트를
            # 통과했다). 관측기가 던질 수 있는 예외는 로깅 핸들러 · `%` 서식 · cap
            # 내부까지 열려 있어 **열거가 불가능**하므로 흡수는 bare 여야 한다.
            assert _catches_bare_exception(enclosing), (
                f"{rel}::{fn.name}:{node.lineno} 의 흡수기가 좁은 예외 타입이다 "
                f"(line {enclosing.lineno}) — `except Exception:` 이어야 한다. "
                "좁히면 미열거 예외가 `check_buy_signal` 을 뚫고 `risk.on_tick`(전략별 "
                "try 없음) → `handler.py` re-raise → WS 재연결 폭주로 이어진다"
            )


@pytest.mark.parametrize("rel", _RELS, ids=_IDS)
def test_g262_7c_no_db_write_in_hold_path(rel: str) -> None:
    """G-262-7c (RED): 보류 경로에 `write_log`/`await` 0건.

    `check_buy_signal` 은 동기 순수 계산이고 `risk.on_tick` 의 hot path 다. DB 쓰기를
    끼우면 틱마다 I/O 가 붙고, `execute_buy` 의 원자성 전제(`calc_buy_quantity` ↔
    `pending_buys.add` 사이 await 0건)와 같은 계열의 계약을 깬다.
    """
    tree, _ = _tree(rel)
    for fn in _require_hold_funcs(rel, tree):
        if isinstance(fn, ast.AsyncFunctionDef):
            continue   # prepare 등 비동기 경로는 이 가드의 대상이 아니다
        writes = [
            n.lineno for n in ast.walk(fn)
            if isinstance(n, ast.Call)
            and (getattr(n.func, "attr", None) == "write_log"
                 or getattr(n.func, "id", None) == "write_log")
        ]
        assert writes == [], f"{rel}::{fn.name} 에 `write_log` (lines {writes})"
        awaits = [n.lineno for n in ast.walk(fn) if isinstance(n, ast.Await)]
        assert awaits == [], f"{rel}::{fn.name} 에 `await` (lines {awaits})"


@pytest.mark.parametrize("rel", _RELS, ids=_IDS)
def test_g262_7d_peek_log_mark_order(rel: str) -> None:
    """G-262-7d (RED): 두 emit 모두 **peek(`should_emit`) → 로그 → mark** 순서다.

    cycle226 D-3 계약. `mark_emitted` 를 `logger.info` **앞**으로 옮기는 뮤테이션은
    정상 경로에서 완전히 무증상이라(적대 검증 MEDIUM — config·blocked 양쪽 ESCAPED)
    행위 가드(`test_c7_7`/`test_c8_6`)와 **함께** 정적으로도 못 박는다.

    깨지면: 로깅 핸들러가 그날 한 번 실패하는 순간 cap 이 이미 소진돼 그날의 관측이
    **영영 0행**이 된다 — config 면 "보류가 켜졌는지 꺼졌는지 모르는" 침묵(자문 §2.5),
    blocked 면 그 종목 would_buy 정본의 하루치 소실(이 사이클의 핵심 산출물).
    """
    tree, _ = _tree(rel)
    checked = 0
    for fn in _require_hold_funcs(rel, tree):
        logs = _marker_log_linenos(fn)
        if not logs:
            continue
        peeks = _cap_call_linenos(fn, "should_emit")
        marks = _cap_call_linenos(fn, "mark_emitted")
        assert peeks, f"{rel}::{fn.name}: 마커 emit 이 있는데 `should_emit` 이 없다 (cap 미적용)"
        assert marks, f"{rel}::{fn.name}: 마커 emit 이 있는데 `mark_emitted` 가 없다 (cap 미소진)"
        assert min(peeks) < min(logs), (
            f"{rel}::{fn.name}: peek(line {min(peeks)})이 로그(line {min(logs)}) 뒤다 — "
            "cap 이 사후 판정이면 폭주를 못 막는다"
        )
        assert min(marks) > min(logs), (
            f"{rel}::{fn.name}: `mark_emitted`(line {min(marks)})가 `logger.info`"
            f"(line {min(logs)})보다 **앞**이다 — 로그 자기실패 1회가 그날의 관측을 지운다"
        )
        checked += 1
    assert checked >= 2, (
        f"{rel}: 마커 emit 을 담은 함수가 {checked}개뿐 — config·blocked 두 지점이어야 한다 "
        "(기준선 부재를 조용한 PASS 로 넘기지 않는다)"
    )


@pytest.mark.parametrize("rel", _RELS, ids=_IDS)
def test_g262_7e_config_cap_key_is_value_sensitive(rel: str) -> None:
    """G-262-7e (RED): config cap 키가 **값-민감**(적용값 보간)이다.

    `key = f"cfg|{hold_secs}"` → `key = "cfg"` 로 상수화하는 뮤테이션이 전 스위트를
    통과했다(적대 검증 MEDIUM). 값-비민감이면 그날 첫 틱이 cap 을 소진해 **장중 PUT
    롤백 후 바뀐 값을 확인할 마커가 0개**가 된다(cycle245 R1 이 겪은 사각). 행위 가드
    `test_c7_6` 의 정적 짝이고, 리터럴 상수화 회귀를 정적으로도 막는다.
    """
    tree, _ = _tree(rel)
    fns = [
        fn for fn in _require_hold_funcs(rel, tree)
        if any(
            isinstance(n, ast.Constant) and isinstance(n.value, str)
            and "[open_entry_hold_config]" in n.value
            for n in ast.walk(fn)
        )
    ]
    assert len(fns) == 1, (
        f"{rel}: `[open_entry_hold_config]` 를 싣는 함수가 {len(fns)}개 — 1개여야 한다"
    )
    fn = fns[0]

    interpolated = [
        f for j in ast.walk(fn) if isinstance(j, ast.JoinedStr)
        for f in j.values
        if isinstance(f, ast.FormattedValue) and isinstance(f.value, ast.Name)
        and "hold" in f.value.id
    ]
    assert interpolated, (
        f"{rel}::{fn.name}: cap 키에 적용값 보간(f-string `{{hold_secs}}`)이 없다 — "
        "값-비민감 키면 장중 롤백 확인 채널이 사라진다"
    )

    for n in ast.walk(fn):
        if isinstance(n, ast.Call) and getattr(n.func, "attr", None) == "should_emit":
            arg = n.args[0] if n.args else None
            assert not (isinstance(arg, ast.Constant) and isinstance(arg.value, str)), (
                f"{rel}::{fn.name}:{n.lineno} — `should_emit` 인자가 상수 문자열 "
                f"{arg.value!r} 이다(값-비민감)"
            )


# ===========================================================================
# G-262-8 — 청산·수량 축 무오염
# ===========================================================================
@pytest.mark.parametrize("rel", _RELS, ids=_IDS)
def test_g262_8_exit_and_qty_untouched(rel: str) -> None:
    """G-262-8 (보존→봉인): `check_exit_signal`·`calc_buy_quantity` 에 보류 토큰 0건.

    보류는 **신규 매수 신호** 축이다. 청산에 새면 개장 90초 손절이 멈추고, 수량에 새면
    `_apply_budget_limit` 관문 계약(A-PURE/A-GATE)과 축이 섞인다.
    """
    tree, _ = _tree(rel)
    for name in ("check_exit_signal", "calc_buy_quantity", "check_force_clear"):
        fn = _func(tree, name)
        if fn is None:
            continue
        assert not _mentions_hold(fn), (
            f"{rel}::{name} 에 보류 토큰이 새어 들어갔다 — 보류는 매수 신호 전용이다"
        )


# ===========================================================================
# G-262-9 — 두 전략 파일 상호 import 금지
# ===========================================================================
@pytest.mark.parametrize("rel", _RELS, ids=_IDS)
def test_g262_9_no_cross_strategy_import(rel: str) -> None:
    """G-262-9 (보존): VB ↔ LTV 상호 import 0 (cycle229 G-4 답습).

    "같은 키니까 상수를 한쪽에서 import 하자" 는 두 전략을 결합시키고, LTV 단독 롤백
    (자문 §5 — 키가 전략별이라 VB 90 유지 · LTV 0 이 가능)을 코드 레벨에서 막는다.
    """
    tree, _ = _tree(rel)
    other = "long_tail_volatility" if rel == _VB else "volatility_breakout"
    hits: list[int] = []
    for n in ast.walk(tree):
        if isinstance(n, ast.ImportFrom) and other in (n.module or ""):
            hits.append(n.lineno)
        elif isinstance(n, ast.Import):
            hits += [n.lineno for a in n.names if other in a.name]
    assert hits == [], f"{rel} 이 `{other}` 를 import 한다 (lines {hits})"
