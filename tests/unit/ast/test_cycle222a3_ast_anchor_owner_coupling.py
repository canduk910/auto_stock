"""cycle222-a3 G-5 — 앵커 **절대 대입** ↔ 채택 제외 집합 커플링 가드.

## 결함

`risk._DAY_HIGH_ANCHOR_EXCLUDED_STRATEGIES` 의 멤버십 전제는
**"앵커(`high_since_buy`)에 외부 소유자의 절대 대입이 있는 전략"** 이다.
조사 결과 현재 그런 곳은 `scheduler._execute_next_day_clear` 의

    pos.high_since_buy = today_open        # ← max() 가 아니라 절대 대입

하나(LTV 한정)뿐이다. 그런데 후속 사이클에서 그 대입을 **다른 전략으로 넓히면
제외 집합은 자동으로 따라오지 않는다** — 그리고 이를 잡는 테스트가 0건이었다.
그 순간 `day_high` 채택이 새 소유자의 대입을 되돌려도 아무 것도 FAIL 하지 않는다.

## 시정 계약

`src/` 전수에서 `high_since_buy` 대입을 AST 로 찾아, 각 대입이 아래 셋 중
하나임을 강제한다:

1. **올리기 전용 `max(...)`** — `max` 의 피연산자에 **이전 앵커가 포함된** 형태
   (`<obj>.high_since_buy = max(..., <같은 obj>.high_since_buy, ...)`, 또는 같은
   함수 안에서 그 속성으로 **단 한 번** 바인딩된 지역 별칭). 자동 통과.
2. `_KNOWN_ABSOLUTE_ASSIGNS` 화이트리스트 — 생성 초기화 / 직전 가드로 올리기 전용이
   보장된 것 / 소유 전략이 **제외 집합에 등재된** 것
3. 그 외 → **FAIL** (무엇을 해야 하는지 실패 메시지가 설명한다)

## ⚠️ `max(...)` 라는 사실만으로는 올리기 전용이 아니다 (cycle222-a "H-1" 시정)

1차 구현은 `value.func.id == "max"` 만 보고 **무조건** 통과시켰고, docstring 도
"`max(...)` 형태 — 올리기 전용이라 자동 통과" 라고 단정했다. **거짓이다.**
`max()` 가 앵커를 올리기만 하는 것은 **이전 앵커가 피연산자일 때뿐**이다.

    pos.high_since_buy = max(current_price, 0)   # ← max 인데 앵커가 **내려간다**

실증(주입→원복): 위 형태는 구 가드를 **무경고 통과**했다. 이건 이 가드가 막으려던
"두 번째 writer 가 앵커를 되돌린다" 클래스 그 자체다 — 가격이 고점에서 하락하면
앵커가 같이 따라 내려가 **트레일링 기준점이 소멸**한다(2026-08-06 H-1 사이클이
`high_since_buy` 영속화로 고친 결함과 동일 축: 기준점이 매일 매수가로 리셋되면
샹들리에가 하드손절과 구분되지 않았다).

그래서 자동 통과 조건을 **"이전 앵커가 피연산자에 포함될 때"** 로 좁힌다.
포함되지 않으면 절대 대입과 동일하게 취급한다(화이트리스트/제외 집합 검사 대상).

`owner` 분류는 한 걸음 더 간다 — 선언한 소유 전략이
`_DAY_HIGH_ANCHOR_EXCLUDED_STRATEGIES` 에 실재해야 하고, 대입을 감싸는 `if` 조건에
그 전략 id 문자열이 **여전히** 있어야 한다. 그래야 같은 함수 안에 다른 전략용
절대 대입이 새로 생겨도 화이트리스트가 그것까지 덮어주지 않는다.

⚠️ DB 컬럼 write(`db/positions.py` 의 SQL 문자열)와 생성자 kwarg
   (`boot_manager` 의 `Position(high_since_buy=...)`)는 **메모리 앵커 대입이
   아니므로** 탐지 대상이 아니다(AST 상 `Assign`→`Attribute` 가 아니다).
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SRC = _REPO_ROOT / "src"

_ANCHOR_ATTR = "high_since_buy"

# (상대경로, 대입이 속한 함수명) → (분류, 소유 전략 id 또는 None, 근거)
#
#   "init"       — 객체 생성 시 초기화. 외부 소유자가 아니다.
#   "raise_only" — 직전 가드(`candidate <= pos.high_since_buy: return`)로 실질
#                  올리기 전용. `max()` 와 동치라 두 번째 writer 문제가 없다.
#   "owner"      — 진짜 외부 소유자(절대 대입). 소유 전략은 반드시 채택 제외 집합에.
_KNOWN_ABSOLUTE_ASSIGNS: dict[tuple[str, str], tuple[str, str | None, str]] = {
    ("src/engine/strategy_base.py", "__post_init__"): (
        "init", None,
        "Position 생성 시 `high_since_buy == 0` 이면 buy_price 로 초기화",
    ),
    ("src/engine/strategy.py", "__post_init__"): (
        "init", None,
        "구 Position dataclass 생성 초기화 (동형)",
    ),
    ("src/engine/strategy_base.py", "_apply_high_since_buy_from_candles"): (
        "raise_only", None,
        "`candidate <= pos.high_since_buy` 면 return — H-1 복구는 올리기 전용",
    ),
    ("src/engine/scheduler.py", "_execute_next_day_clear"): (
        "owner", "long_tail_volatility",
        "사이클 142 — 익일 트레일링 기준점을 today_open 으로 **덮어쓰는** 절대 대입. "
        "08:00:30 근방(TIME_PRE_NXT_OPEN + NEXT_DAY_STABILIZE_SECS) 1회. "
        "⚠️ 방향은 보장되지 않는다 — 진입 조건이 `buy_price` 대비 gap_rate 라 "
        "`high_since_buy` 와 비교하지 않으므로, 연속 갭업이면 today_open 이 직전 "
        "앵커보다 **높아 올릴 수도** 있다. 화이트리스트 근거는 '내린다' 가 아니라 "
        "'외부 소유자가 있다' 이다.",
    ),
}


def _anchor_targets(node) -> list[ast.Attribute]:
    """대입 노드에서 `<obj>.high_since_buy` 타깃만 골라낸다."""
    if isinstance(node, ast.Assign):
        targets = node.targets
    elif isinstance(node, (ast.AugAssign, ast.AnnAssign)):
        targets = [node.target]
    else:
        targets = []
    return [
        t for t in targets
        if isinstance(t, ast.Attribute) and t.attr == _ANCHOR_ATTR
    ]


def _iter_anchor_assigns():
    """`src/**/*.py` 전수에서 `<obj>.high_since_buy = <expr>` 대입을 수집.

    yield: `(상대경로, 함수명, 대입 노드, 조상 if 조건의 문자열 리터럴, 함수 노드)`
    — 함수 노드는 `_is_raising_max_call` 의 **지역 별칭 해석**에 쓰인다.
    """
    for path in sorted(_SRC.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:  # pragma: no cover
            pytest.fail(f"{path} 파싱 실패 — 탐지기가 조용히 비어버린다")
        parent: dict[ast.AST, ast.AST] = {}
        for node in ast.walk(tree):
            for child in ast.iter_child_nodes(node):
                parent[child] = node
        for node in ast.walk(tree):
            if not isinstance(node, (ast.Assign, ast.AugAssign, ast.AnnAssign)):
                continue
            if not _anchor_targets(node):
                continue
            rel = path.relative_to(_REPO_ROOT).as_posix()
            # 감싸는 함수명 + 조상 `if` 조건의 문자열 리터럴 수집
            fname = "<module>"
            fnode: ast.AST = tree
            guard_strings: set[str] = set()
            cur: ast.AST = node
            while cur in parent:
                cur = parent[cur]
                if isinstance(cur, ast.If):
                    guard_strings |= {
                        n.value for n in ast.walk(cur.test)
                        if isinstance(n, ast.Constant) and isinstance(n.value, str)
                    }
                if isinstance(cur, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    fname = cur.name
                    fnode = cur
                    break
            yield rel, fname, node, guard_strings, fnode


def _single_binding_anchor_aliases(fnode: ast.AST, owner_dumps: set[str]) -> set[str]:
    """함수 안에서 `<name> = <owner>.high_since_buy` 로 **단 한 번** 묶인 지역 이름.

    `risk.on_tick` 의

        prev_anchor = pos.high_since_buy
        pos.high_since_buy = max(prev_anchor, current_price, eff_day_high)

    처럼 이전 앵커를 지역 변수로 받아 쓰는 형태를 "이전 앵커가 피연산자" 로 인정하기
    위한 것이다. **단 한 번만 바인딩된 이름**으로 제한하는 이유 = 중간에 재대입되면
    별칭이 스테일해져 `max` 가 실제로는 앵커를 안 볼 수 있기 때문이다(그 경우는
    자동 통과시키지 않고 화이트리스트 검사로 보낸다 = fail-closed).
    """
    store_counts: dict[str, int] = {}
    for n in ast.walk(fnode):
        if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store):
            store_counts[n.id] = store_counts.get(n.id, 0) + 1
    argnames: set[str] = set()
    if isinstance(fnode, (ast.FunctionDef, ast.AsyncFunctionDef)):
        a = fnode.args
        for x in [*a.posonlyargs, *a.args, *a.kwonlyargs]:
            argnames.add(x.arg)
        if a.vararg:
            argnames.add(a.vararg.arg)
        if a.kwarg:
            argnames.add(a.kwarg.arg)

    aliases: set[str] = set()
    for n in ast.walk(fnode):
        if not (isinstance(n, ast.Assign) and len(n.targets) == 1):
            continue
        target, value = n.targets[0], n.value
        if not (isinstance(target, ast.Name) and isinstance(value, ast.Attribute)):
            continue
        if value.attr != _ANCHOR_ATTR or ast.dump(value.value) not in owner_dumps:
            continue
        if target.id in argnames or store_counts.get(target.id, 0) != 1:
            continue
        aliases.add(target.id)
    return aliases


def _direct_max_args(call: ast.Call) -> list[ast.AST]:
    """`max(...)` 의 **직접 위치 인자**만 편다. 중첩 `max` 는 그 인자까지 재귀 전개.

    서브트리 전체(`ast.walk`)를 뒤지면 앵커를 **변형해** 넣은 형태가 통과한다 —
    `max(pos.high_since_buy - 100, x)` 는 매 틱 100 씩 내려가는데도 "앵커가
    들어있다" 는 이유로 올리기 전용으로 오판된다(실측 확인). 직접 인자로 좁혀야
    `new >= old` 가 실제로 보장된다.

    제외 대상:
    - `default=` 키워드 — `max(seq, default=anchor)` 는 seq 가 **비었을 때만**
      앵커를 돌려주므로 올리기 전용이 아니다.
    - `*args` 언팩 — 정적 판정 불가.
    둘 다 여기서 빠지므로 호출부에서 자동 통과하지 못한다(fail-closed).
    """
    out: list[ast.AST] = []
    for a in call.args:
        if isinstance(a, ast.Starred):
            continue
        if isinstance(a, ast.Call) and isinstance(a.func, ast.Name) and a.func.id == "max":
            out.extend(_direct_max_args(a))
        else:
            out.append(a)
    return out


def _is_raising_max_call(node, fnode: ast.AST) -> bool:
    """`max(...)` 이면서 **이전 앵커가 직접 피연산자**인가.

    `max(...)` 라는 사실만으로는 올리기 전용이 아니다 — `max(current_price, 0)` 은
    가격이 내리면 앵커를 **같이 내린다**(= 트레일링 기준점 소멸). 이전 앵커가
    피연산자여야만 `new >= old` 가 구조적으로 보장된다. 판정 불가는 **미통과**
    (화이트리스트 검사로 보냄) = fail-closed.

    ⚠️ "포함" 이 아니라 **직접 인자**여야 한다(`_direct_max_args`). 앵커를 산술·
       조건식으로 감싼 형태(`max(anchor - 100, x)` / `max(anchor if f else 0, x)`)는
       앵커가 서브트리에 있어도 올리기 전용이 아니다.
    """
    value = getattr(node, "value", None)
    if not (
        isinstance(value, ast.Call)
        and isinstance(value.func, ast.Name)
        and value.func.id == "max"
    ):
        return False
    owner_dumps = {ast.dump(t.value) for t in _anchor_targets(node)}
    if not owner_dumps:
        return False
    aliases = _single_binding_anchor_aliases(fnode, owner_dumps)
    for sub in _direct_max_args(value):
        if (
            isinstance(sub, ast.Attribute)
            and sub.attr == _ANCHOR_ATTR
            and ast.dump(sub.value) in owner_dumps
        ):
            return True
        if isinstance(sub, ast.Name) and sub.id in aliases and isinstance(sub.ctx, ast.Load):
            return True
    return False


def test_g5_detector_is_not_vacuous():
    """탐지기가 실제로 무언가를 찾는다 — 0건이면 가드가 조용히 죽은 것이다."""
    found = list(_iter_anchor_assigns())
    assert len(found) >= 5, (
        f"`{_ANCHOR_ATTR}` 대입을 {len(found)}건밖에 못 찾았다 — 탐지기 스테일. "
        "속성명이 바뀌었거나 대입 형태가 달라졌다면 이 가드를 먼저 고쳐라"
    )


def test_g5_every_absolute_anchor_assign_is_accounted_for():
    """★ 새 **절대 대입**이 생기면 제외 집합과 함께 재검토하도록 FAIL 한다."""
    from src.engine.risk import _DAY_HIGH_ANCHOR_EXCLUDED_STRATEGIES as EXCLUDED

    unaccounted: list[str] = []
    for rel, fname, node, guard_strings, fnode in _iter_anchor_assigns():
        if _is_raising_max_call(node, fnode):
            continue  # 이전 앵커가 피연산자인 max — 구조적으로 올리기 전용
        entry = _KNOWN_ABSOLUTE_ASSIGNS.get((rel, fname))
        if entry is None:
            unaccounted.append(f"{rel}:{node.lineno} ({fname})")
            continue
        kind, owner, _why = entry
        if kind != "owner":
            continue
        assert owner in EXCLUDED, (
            f"{rel}:{node.lineno} ({fname}) 는 전략 `{owner}` 의 앵커에 **절대 "
            f"대입**을 하는 외부 소유자로 선언돼 있는데, 그 전략이 "
            "`_DAY_HIGH_ANCHOR_EXCLUDED_STRATEGIES` 에 없다.\n"
            "on_tick 의 day_high 채택이 두 번째 writer 가 되어 소유자의 대입을 "
            "되돌린다 — 제외 집합에 추가하거나, 왜 불필요한지 근거를 상수 주석에 남겨라."
        )
        assert owner in guard_strings, (
            f"{rel}:{node.lineno} ({fname}) 의 절대 대입이 더 이상 "
            f"`{owner}` 조건 안에 있지 않다.\n"
            "화이트리스트는 (파일, 함수) 단위라 같은 함수에 **다른 전략용** 절대 "
            "대입이 새로 생기면 그것까지 덮어준다. 소유 전략 조건이 사라졌다면 "
            "`_KNOWN_ABSOLUTE_ASSIGNS` 항목과 제외 집합을 함께 재검토하라."
        )

    assert unaccounted == [], (
        "앵커(`high_since_buy`)에 **새로운 절대 대입**이 생겼다: "
        f"{unaccounted}\n"
        "\n무엇을 해야 하나:\n"
        "  1) 그 대입이 특정 전략의 앵커를 **덮어쓰는** 것이라면, 그 전략을 "
        "`risk._DAY_HIGH_ANCHOR_EXCLUDED_STRATEGIES` 에 추가하라. 안 그러면 "
        "on_tick 의 day_high 채택이 두 번째 writer 가 되어 다음 틱에 그 대입을 "
        "되돌린다(사이클 142 LTV 사례와 동일 클래스).\n"
        "  2) 제외가 **불필요**하다면(예: 올리기 전용이거나 생성 초기화라면) "
        "`_KNOWN_ABSOLUTE_ASSIGNS` 에 분류와 **근거**를 명시해 등재하라.\n"
        "  3) 어느 쪽도 아니면 **이전 앵커를 피연산자로 포함한** `max(...)` 형태"
        "(`pos.high_since_buy = max(pos.high_since_buy, ...)`)로 바꿔 올리기 전용으로 "
        "만들어라. ⚠️ `max(...)` 라는 것만으로는 부족하다 — `max(current_price, 0)` 은 "
        "가격이 내리면 앵커를 같이 내려 트레일링 기준점을 소멸시킨다."
    )


def test_g5_whitelist_has_no_stale_entries():
    """화이트리스트 항목이 실제 코드에 존재한다 — 유령 면제 금지."""
    live = {(rel, fname) for rel, fname, _n, _g, _f in _iter_anchor_assigns()}
    stale = sorted(set(_KNOWN_ABSOLUTE_ASSIGNS) - live)
    assert stale == [], (
        f"`_KNOWN_ABSOLUTE_ASSIGNS` 에 코드에 없는 항목이 남아 있다: {stale} — "
        "면제가 스테일하면 다음에 같은 위치에 생기는 진짜 절대 대입을 통과시킨다"
    )


def test_g5_owner_entries_match_the_exclusion_set_exactly():
    """선언된 소유 전략 집합 == 제외 집합 — 한쪽만 늘어나는 드리프트 차단."""
    from src.engine.risk import _DAY_HIGH_ANCHOR_EXCLUDED_STRATEGIES as EXCLUDED

    owners = {
        owner for kind, owner, _why in _KNOWN_ABSOLUTE_ASSIGNS.values()
        if kind == "owner" and owner
    }
    assert owners == set(EXCLUDED), (
        f"소유자 선언 {sorted(owners)} 와 제외 집합 {sorted(EXCLUDED)} 가 다르다.\n"
        "제외 집합이 더 크면 근거 없는 제외(= 그 전략만 blind 복구를 잃는다)이고, "
        "더 작으면 소유자의 절대 대입이 day_high 채택에 되돌려진다.\n"
        "⚠️ 근거가 '절대 대입' 이 아닌 다른 축(예: 귀인)으로 제외를 유지하려면 "
        "이 가드를 그 축으로 다시 쓰고 상수 주석에 근거를 남겨라."
    )


# ===========================================================================
# cycle222-a "H-1" — `max(...)` 자동 통과 조건의 자기 검증
# ===========================================================================
#
# 구 `_is_max_call` 은 `func.id == "max"` 만 봤고 본 테스트가 즉시 `continue` 했다.
# 그래서 `pos.high_since_buy = max(x, 0)` — **이전 앵커를 뺀** max — 가 무경고로
# 통과했다(주입 실증). 아래 두 테스트가 그 구멍을 합성 코드로 못박는다.
# 합성이라 `src/` 를 실제로 뮤테이션하지 않고도 회귀가 잡힌다.

def _parse_one_anchor_assign(code: str):
    """합성 코드에서 앵커 대입 1건과 그 감싸는 함수 노드를 뽑는다."""
    tree = ast.parse(code)
    parent: dict[ast.AST, ast.AST] = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parent[child] = node
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Assign, ast.AugAssign, ast.AnnAssign)):
            continue
        if not _anchor_targets(node):
            continue
        fnode: ast.AST = tree
        cur: ast.AST = node
        while cur in parent:
            cur = parent[cur]
            if isinstance(cur, (ast.FunctionDef, ast.AsyncFunctionDef)):
                fnode = cur
                break
        return node, fnode
    raise AssertionError("합성 코드에 앵커 대입이 없다")


_RAISING_FORMS = {
    "direct_operand": """
def f(pos, current_price):
    pos.high_since_buy = max(pos.high_since_buy, current_price)
""",
    "nested_operand": """
def f(pos, a, b):
    pos.high_since_buy = max(a, max(b, pos.high_since_buy))
""",
    # `risk.on_tick` 실제 형태 — 이전 앵커를 지역 변수로 받아 쓴다
    "single_binding_alias": """
def f(pos, current_price, eff_day_high):
    prev_anchor = pos.high_since_buy
    pos.high_since_buy = max(prev_anchor, current_price, eff_day_high)
""",
}

_NOT_RAISING_FORMS = {
    # ★ 주입 실증했던 바로 그 형태 — max 인데 앵커가 **내려간다**
    "max_without_anchor": """
def f(pos, x):
    pos.high_since_buy = max(x, 0)
""",
    "max_of_other_prices": """
def f(pos, current_price, open_price):
    pos.high_since_buy = max(current_price, open_price)
""",
    # ★ H-1 2차 — 앵커를 **변형해** 넣은 형태. 서브트리 탐색이면 통과했다.
    "arithmetic_on_anchor": """
def f(pos, x):
    pos.high_since_buy = max(pos.high_since_buy - 100, x)
""",
    "conditional_anchor": """
def f(pos, x, flag):
    pos.high_since_buy = max(pos.high_since_buy if flag else 0, x)
""",
    # seq 가 비었을 때만 앵커를 돌려준다 = 올리기 전용 아님
    "max_default_keyword": """
def f(pos, seq):
    pos.high_since_buy = max(seq, default=pos.high_since_buy)
""",
    # 정적 판정 불가 → fail-closed
    "starred_args": """
def f(pos, xs):
    pos.high_since_buy = max(*xs)
""",
    # 다른 객체의 앵커는 이 객체의 이전 앵커가 아니다
    "other_object_anchor": """
def f(pos, other):
    pos.high_since_buy = max(other.high_since_buy, 0)
""",
    # 별칭이 중간에 재대입되면 스테일 가능 → 자동 통과 금지(fail-closed)
    "rebound_alias": """
def f(pos, x):
    prev = pos.high_since_buy
    prev = 0
    pos.high_since_buy = max(prev, x)
""",
    "absolute_assign": """
def f(pos, today_open):
    pos.high_since_buy = today_open
""",
}


@pytest.mark.parametrize("name", sorted(_RAISING_FORMS))
def test_h1_raising_max_forms_are_auto_passed(name):
    node, fnode = _parse_one_anchor_assign(_RAISING_FORMS[name])
    assert _is_raising_max_call(node, fnode) is True, (
        f"{name}: 이전 앵커가 피연산자인데 자동 통과되지 않는다 — "
        "탐지기가 과도하게 좁아져 현 트리 3건이 화이트리스트를 요구하게 된다"
    )


@pytest.mark.parametrize("name", sorted(_NOT_RAISING_FORMS))
def test_h1_max_without_previous_anchor_is_not_auto_passed(name):
    """★ H-1 구멍 재현 — `max()` 라는 사실만으로 통과시키면 안 된다.

    `pos.high_since_buy = max(x, 0)` 은 가격이 고점에서 내려오면 앵커를 **같이**
    내린다 = 트레일링 기준점 소멸(2026-08-06 H-1 사이클이 고친 결함의 재발 축).
    구 `_is_max_call` 은 이 형태를 무경고 통과시켰다.
    """
    node, fnode = _parse_one_anchor_assign(_NOT_RAISING_FORMS[name])
    assert _is_raising_max_call(node, fnode) is False, (
        f"{name}: 이전 앵커 없는 대입이 '올리기 전용' 으로 자동 통과됐다 — "
        "두 번째 writer 가 앵커를 되돌려도 이 가드가 침묵한다"
    )


def test_h1_live_max_assigns_are_all_anchor_raising():
    """현 트리의 `max(...)` 앵커 갱신 3건이 **전부** 이전 앵커를 피연산자로 갖는다.

    (LTV `:741` / momentum `:193` = 직접 피연산자, `risk.on_tick` = `prev_anchor`
    단일 바인딩 별칭.) 라이브 결함이 없다는 판정의 근거를 코드로 고정한다.
    """
    max_assigns = [
        (rel, node.lineno, _is_raising_max_call(node, fnode))
        for rel, _fname, node, _g, fnode in _iter_anchor_assigns()
        if isinstance(getattr(node, "value", None), ast.Call)
        and isinstance(node.value.func, ast.Name)
        and node.value.func.id == "max"
    ]
    assert len(max_assigns) == 3, (
        f"`max(...)` 앵커 갱신이 3건이 아니다: {max_assigns} — 늘었다면 새 건이 "
        "이전 앵커를 피연산자로 갖는지 확인하고 이 핀을 갱신하라"
    )
    bad = [(rel, ln) for rel, ln, ok in max_assigns if not ok]
    assert bad == [], (
        f"이전 앵커를 피연산자로 갖지 않는 `max(...)` 앵커 갱신: {bad} — "
        "가격 하락 시 앵커가 같이 내려가 트레일링 기준점이 소멸한다"
    )
