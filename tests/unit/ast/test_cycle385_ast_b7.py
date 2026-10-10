"""cycle385 B7 · J-2 · J-1 — 구조 가드 (A1~A10).

명세 = `_workspace/red/cycle385_b7_partial_sell_spec.md` §l-5
행위 짝 = `tests/unit/engine/test_cycle385_b7_partial_sell.py` ·
          `tests/unit/engine/test_cycle385_reorder_requery.py` ·
          `tests/unit/routes/test_cycle385_manual_sell_selling.py`

행위 테스트는 **무엇이 되는가**를 잰다. 이 파일은 행위 테스트가 표본 밖에서 놓치는
**순서·원자성**을 잰다 — 「발사 수량을 발사 뒤 다시 읽는다」 「재조회와 발사 사이에
양보점이 끼었다」 「보유 차감이 첫 DB await 뒤로 밀렸다」는 특정 경합 순서에서만
드러나서 표본을 늘려도 같은 누락에 노출된다(cycle328 `test_g328_3b` 선례).

🔴 소스는 `Path.read_text` + AST 로만 읽는다(git 금지 — 미추적 파일·커밋 직후 공허).
🔴 주석·docstring 은 호출로 세지 않는다 — A7 만 **의도적으로** 주석을 읽는다(J-1 은 주석 정정).
"""
from __future__ import annotations

import ast
import textwrap
from pathlib import Path
from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parents[3]
_OE = _ROOT / "src" / "engine" / "order_engine.py"
_ROUTE = _ROOT / "src" / "routes" / "trading.py"


def _src(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def _func(tree: ast.AST, name: str):
    hits = [
        n for n in ast.walk(tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name
    ]
    assert len(hits) <= 1, f"`{name}` 정의가 {len(hits)}개"
    return hits[0] if hits else None


def _call_name(call: ast.Call) -> str:
    f = call.func
    if isinstance(f, ast.Name):
        return f.id
    if isinstance(f, ast.Attribute):
        return f.attr
    return ""


def _calls(node: ast.AST, name: str) -> list[ast.Call]:
    return [n for n in ast.walk(node) if isinstance(n, ast.Call) and _call_name(n) == name]


def _awaits(node: ast.AST) -> list[int]:
    return sorted(n.lineno for n in ast.walk(node) if isinstance(n, ast.Await))


def _kw(call: ast.Call, name: str):
    for k in call.keywords:
        if k.arg == name:
            return k.value
    return None


def _catches_exception(tr: ast.Try) -> bool:
    for h in tr.handlers:
        t = h.type
        if t is None:
            return True
        names = t.elts if isinstance(t, ast.Tuple) else [t]
        if any(isinstance(x, ast.Name) and x.id in ("Exception", "BaseException")
               for x in names):
            return True
    return False


def _parents(tree: ast.AST) -> dict:
    par: dict = {}
    for p in ast.walk(tree):
        for c in ast.iter_child_nodes(p):
            par[c] = p
    return par


def _full_fill_ifs(fn: ast.AST) -> list[ast.If]:
    out = []
    for n in ast.walk(fn):
        if not isinstance(n, ast.If) or not isinstance(n.test, ast.Compare):
            continue
        t = n.test
        if (isinstance(t.left, ast.Name) and t.left.id == "total_filled"
                and len(t.ops) == 1 and isinstance(t.ops[0], ast.GtE)
                and isinstance(t.comparators[0], ast.Name)
                and t.comparators[0].id == "ordered_qty"):
            out.append(n)
    return out


def _qty_stores(fn: ast.AST) -> list[ast.AST]:
    """`<name>.quantity = …` / `<name>.quantity -= …` 대입문."""
    out = []
    for n in ast.walk(fn):
        targets = []
        if isinstance(n, ast.Assign):
            targets = n.targets
        elif isinstance(n, (ast.AugAssign, ast.AnnAssign)):
            targets = [n.target]
        for tg in targets:
            if isinstance(tg, ast.Attribute) and tg.attr == "quantity" \
                    and isinstance(tg.value, ast.Name):
                out.append(n)
    return out


# 부록 R4 D2 — 「안 걸렸다」 판정에 쓰는 `src.api.balance` 분류기 셋. `_sell_not_placed_reason` 만 부른다.
_NOT_PLACED_CLASSIFIERS = (
    "is_sell_qty_exceeded", "is_market_closed_rejection", "is_market_order_disallowed",
)


@pytest.fixture(scope="module")
def oe():
    src = _src(_OE)
    return src, ast.parse(src)


# ════════════════════════════════════════════════════════════════════════════
# A1 — 주문 축 If 는 문자 그대로 · 1개 · 함수 본문 최상위
# ════════════════════════════════════════════════════════════════════════════
def test_a1_order_axis_if_is_literal_single_and_top_level(oe):
    """🔴 A1 — `if total_filled >= ordered_qty:` 가 `_handle_sell_fill` 에 **정확히 1개**,
    본문 **최상위** 문장이다.

    `test_cycle273a_ast_partial_optin_and_timer::_full_fill_if` 가 그 문자 그대로의
    If 안에서 타이머 해제·order_no 게이트를 찾는다. `if order_done:` 로 바꾸면 그
    가드가 기준선을 잃고, 두 개로 늘리면 첫 번째만 검사된다.
    """
    _, tree = oe
    fn = _func(tree, "_handle_sell_fill")
    assert fn is not None
    ifs = _full_fill_ifs(fn)
    assert len(ifs) == 1, f"주문 축 If 가 {len(ifs)}개 (기대 1) — L{[i.lineno for i in ifs]}"
    assert ifs[0] in fn.body, "주문 축 If 가 함수 본문 최상위가 아니다(다른 분기 안에 묻혔다)"


# ════════════════════════════════════════════════════════════════════════════
# A2 — save_position 은 except Exception 을 가진 Try 안
# ════════════════════════════════════════════════════════════════════════════
def test_a2_save_position_is_guarded_by_broad_except(oe):
    """🔴 A2 — `_handle_sell_fill` 의 `save_position` 호출이 존재하고, 전부
    `except Exception` 핸들러를 가진 `Try` 의 **본문** 안에 있다.

    체결통보 콜백의 예외는 WS 재연결을 부른다(`handler.py`). 저장 실패가 그 사슬을
    타면 한 건의 DB 오류가 시세·체결통보 전체를 끊는다.
    """
    _, tree = oe
    fn = _func(tree, "_handle_sell_fill")
    saves = _calls(fn, "save_position")
    assert saves, "`_handle_sell_fill` 에 `save_position` 호출이 없다 — 차감이 DB 에 안 남는다"
    par = _parents(fn)
    for call in saves:
        node, guarded = call, False
        while node in par:
            p = par[node]
            if isinstance(p, ast.Try) and node in p.body and _catches_exception(p):
                guarded = True
                break
            node = p
        assert guarded, f"L{call.lineno} `save_position` 이 `except Exception` 밖에 있다"


# ════════════════════════════════════════════════════════════════════════════
# A3 — execute_sell 발사 수량 고정 send_qty
# ════════════════════════════════════════════════════════════════════════════
def test_a3_execute_sell_uses_fixed_send_qty_everywhere(oe):
    """🔴 A3 — 발사·매핑·PENDING 의 수량이 전부 `send_qty` 이고, 각 `await place_order`
    와 그 경로의 PENDING 헬퍼 호출 사이에 `pos.quantity` 읽기가 0 이다.

    B7 뒤로는 발사 창에 착지한 통보가 `pos.quantity` 를 **await 도중에** 줄인다.
    발사 뒤 다시 읽으면 깎인 값이 매핑·PENDING 에 적혀 다음 통보가 overrun 클램프에
    잘리고 유령 보유가 남는다(§a-2).

    🔴 B4-3(cycle424) — 폴백 경로(블록 ⑰)가 `_handle_sell_market_disallowed` 로
    뽑혔다. 주 경로 1(`execute_sell`) + 폴백 1(추출 메서드) = 합산 2, `quantity=`
    인자 이름은 두 곳 다 `send_qty` 그대로다(기준선 =
    `_workspace/refactor/2026-10-09_execute_sell_baseline.md` 가드 표).
    """
    _, tree = oe
    fn_main = _func(tree, "execute_sell")
    fn_fallback = _func(tree, "_handle_sell_market_disallowed")
    assert fn_fallback is not None, "B4-3 추출 메서드 `_handle_sell_market_disallowed` 가 없다"

    all_places: list[ast.Call] = []
    all_qty_maps: list[ast.Assign] = []
    all_helpers: list[ast.Call] = []

    for fn in (fn_main, fn_fallback):
        places = _calls(fn, "place_order")
        assert len(places) == 1, f"{fn.name} `place_order` {len(places)}곳 (기대 1)"
        for c in places:
            q = _kw(c, "quantity")
            assert isinstance(q, ast.Name) and q.id == "send_qty", (
                f"L{c.lineno} `place_order(quantity=…)` 가 `send_qty` 가 아니다: "
                f"{ast.unparse(q) if q is not None else None}"
            )
        all_places.extend(places)

        qty_maps = [
            n for n in ast.walk(fn)
            if isinstance(n, ast.Assign) and len(n.targets) == 1
            and isinstance(n.targets[0], ast.Subscript)
            and isinstance(n.targets[0].value, ast.Attribute)
            and n.targets[0].value.attr == "_order_qty"
        ]
        assert len(qty_maps) == 1, f"{fn.name} `_order_qty[...] =` {len(qty_maps)}곳 (기대 1)"
        for n in qty_maps:
            assert isinstance(n.value, ast.Name) and n.value.id == "send_qty", (
                f"L{n.lineno} `_order_qty[...] = {ast.unparse(n.value)}` — `send_qty` 여야 한다"
            )
        all_qty_maps.extend(qty_maps)

        helpers = _calls(fn, "_persist_sell_pending_after_send")
        assert len(helpers) == 1, f"{fn.name} PENDING 헬퍼 {len(helpers)}곳 (기대 1)"
        for c in helpers:
            q = _kw(c, "quantity")
            assert isinstance(q, ast.Name) and q.id == "send_qty", (
                f"L{c.lineno} PENDING 수량이 `send_qty` 가 아니다: "
                f"{ast.unparse(q) if q is not None else None}"
            )
        all_helpers.extend(helpers)

        pos_qty_reads = sorted(
            n.lineno for n in ast.walk(fn)
            if isinstance(n, ast.Attribute) and n.attr == "quantity"
            and isinstance(n.value, ast.Name) and n.value.id == "pos"
            and isinstance(n.ctx, ast.Load)
        )
        for pc, hc in zip(sorted(c.lineno for c in places), sorted(c.lineno for c in helpers)):
            between = [ln for ln in pos_qty_reads if pc <= ln <= hc]
            assert not between, (
                f"{fn.name}: `await place_order`(L{pc}) ~ PENDING 헬퍼(L{hc}) 사이에 "
                f"`pos.quantity` 읽기: {between} — 발사 창 체결이 그 값을 이미 깎았을 수 있다"
            )

    assert len(all_places) == 2, (
        f"execute_sell + 추출 메서드 합산 `place_order` {len(all_places)}곳 (기대 2)"
    )
    assert len(all_qty_maps) == 2, f"합산 `_order_qty[...] =` {len(all_qty_maps)}곳 (기대 2)"
    assert len(all_helpers) == 2, f"합산 PENDING 헬퍼 {len(all_helpers)}곳 (기대 2)"

    # 🔴 B4-3 관문 3 보강(cycle424) — 추출 메서드 안의 이름 `send_qty` 만 보면 호출부가
    # 무엇을 넘기는지는 안 보인다. `execute_sell` 의 호출이 `send_qty=pos.quantity` 로
    # 바뀌면(돌연변이 M1) 위 단언은 전부 초록인 채 폴백이 회차 상한(`sell_cap`)을 무시하고
    # 추적 전량을 낸다. 호출부 키워드 값과 메서드 매개변수 이름까지 묶는다.
    params = {a.arg for a in fn_fallback.args.args + fn_fallback.args.kwonlyargs}
    assert "send_qty" in params, (
        f"`_handle_sell_market_disallowed` 매개변수에 `send_qty` 가 없다: {sorted(params)}"
    )
    fb_calls = _calls(fn_main, "_handle_sell_market_disallowed")
    assert len(fb_calls) == 1, (
        f"execute_sell 의 `_handle_sell_market_disallowed` 호출 {len(fb_calls)}곳 (기대 1)"
    )
    sq = _kw(fb_calls[0], "send_qty")
    assert isinstance(sq, ast.Name) and sq.id == "send_qty", (
        f"L{fb_calls[0].lineno} `_handle_sell_market_disallowed(send_qty=…)` 가 그 회차 "
        f"`send_qty` 가 아니다: {ast.unparse(sq) if sq is not None else None}"
    )


def test_a3b_send_qty_is_taken_from_loop_top_requery(oe):
    """🔴 A3b (= AR5, 부록 R-2 개정) — 루프 안 `send_qty` 대입은 **정확히 2개**다.

    첫째 `send_qty = pos.quantity`(루프 상단 재조회 값), 둘째 `if sell_cap is not None:` 본문의
    `send_qty = min(send_qty, sell_cap)`(F-3 회차 상한 — 줄이기만 한다). 둘 다 루프 상단 재조회
    (`pos = strategy.state.positions.get(ticker)`) **뒤** · 첫 `place_order` **앞**이다.

    루프 밖에서 한 번만 잡으면 #1.5 재대조(`pos.quantity = target_qty; continue`)가 고친 수량을
    다음 시도가 못 본다. 상한을 `send_qty = sell_cap` 으로 쓰면(MR20) 대기 중 체결로 추적이
    상한보다 작아졌을 때 추적보다 큰 수량을 낸다.
    """
    _, tree = oe
    fn = _func(tree, "execute_sell")
    loops = [n for n in ast.walk(fn) if isinstance(n, ast.For)]
    assert loops, "execute_sell 재시도 루프가 없다"
    loop = max(loops, key=lambda n: len(list(ast.walk(n))))
    requery = [
        n.lineno for n in ast.walk(loop)
        if isinstance(n, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "pos" for t in n.targets)
    ]
    assigns = sorted(
        (
            n for n in ast.walk(loop)
            if isinstance(n, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "send_qty" for t in n.targets)
        ),
        key=lambda n: n.lineno,
    )
    assert len(assigns) == 2, f"`send_qty` 대입이 루프 안에 {len(assigns)}개 (기대 2 — 부록 R-2)"
    a, b = assigns
    assert isinstance(a.value, ast.Attribute) and a.value.attr == "quantity" \
        and isinstance(a.value.value, ast.Name) and a.value.value.id == "pos", (
            f"`send_qty = {ast.unparse(a.value)}` — 루프 상단에서 재조회한 `pos.quantity` 여야 한다"
        )
    assert ast.unparse(b.value).replace(" ", "") in (
        "min(send_qty,sell_cap)", "min(sell_cap,send_qty)",
    ), f"둘째 `send_qty = {ast.unparse(b.value)}` — `min(send_qty, sell_cap)` 여야 한다(줄이기만)"
    par = _parents(loop)
    guard = par.get(b)
    assert isinstance(guard, ast.If) and b in guard.body, "상한 적용이 If 본문 안이 아니다"
    assert ast.unparse(guard.test).replace(" ", "") == "sell_capisnotNone", (
        f"상한 적용 조건 `{ast.unparse(guard.test)}` — `sell_cap is not None` 이어야 한다"
    )
    first_place = min(c.lineno for c in _calls(loop, "place_order"))
    assert requery and min(requery) < a.lineno < b.lineno < first_place, (
        f"`send_qty`(L{a.lineno}, L{b.lineno}) 가 재조회(L{requery}) 뒤 · 첫 발사(L{first_place}) "
        "앞이 아니다"
    )


# ════════════════════════════════════════════════════════════════════════════
# A4 — J-2 재조회 위치와 원자성
# ════════════════════════════════════════════════════════════════════════════
def test_a4_reorder_requery_sits_after_last_await_before_send(oe):
    """🔴 A4 — `_cancel_and_reorder` 의 `_reorder_requery` 호출이 CANCELLED 장부 await
    **뒤**에 있고, 그 호출 ~ `place_order` 사이 `Await` 0, `place_order` 는 1개다.

    재조회와 발사 사이에 양보점이 끼면 그 사이 체결이 재조회를 무효로 만든다. 재조회를
    `cancel_order` 앞에 두면 취소 왕복 중의 체결을 못 본다(M25).
    """
    _, tree = oe
    fn = _func(tree, "_cancel_and_reorder")
    rq = _calls(fn, "_reorder_requery")
    assert len(rq) == 1, f"`_reorder_requery` 호출 {len(rq)}개 (기대 1)"
    places = _calls(fn, "place_order")
    assert len(places) == 1, "`_cancel_and_reorder` 의 `place_order` 는 정확히 1개(G-295-C4)"
    cancelled = [
        c for c in _calls(fn, "update_trade_status")
        if any(isinstance(a, ast.Attribute) and a.attr == "CANCELLED" for a in c.args)
    ]
    assert len(cancelled) == 1
    cancels = _calls(fn, "cancel_order")
    assert rq[0].lineno > cancelled[0].lineno > min(c.lineno for c in cancels), (
        f"재조회(L{rq[0].lineno})가 취소(L{[c.lineno for c in cancels]})·CANCELLED "
        f"장부(L{cancelled[0].lineno}) 뒤가 아니다"
    )
    between = [ln for ln in _awaits(fn) if rq[0].lineno < ln < places[0].lineno]
    assert not between, (
        f"재조회(L{rq[0].lineno}) ~ `place_order`(L{places[0].lineno}) 사이 await: {between}"
    )


def test_a4b_requery_result_is_what_gets_fired_and_mapped(oe):
    """🔴 A4b — 재조회 결과 변수가 `place_kwargs` 의 `quantity=` 이고
    재주문 `_order_qty[...]` 의 값이다(계산만 하고 버리는 구현 차단)."""
    _, tree = oe
    fn = _func(tree, "_cancel_and_reorder")
    targets = [
        n.targets[0].id for n in ast.walk(fn)
        if isinstance(n, ast.Assign) and len(n.targets) == 1
        and isinstance(n.targets[0], ast.Name) and isinstance(n.value, ast.Call)
        and _call_name(n.value) == "_reorder_requery"
    ]
    assert len(targets) == 1, "`<이름> = self._reorder_requery(...)` 대입이 1개여야 한다"
    fire = targets[0]
    dict_calls = [c for c in _calls(fn, "dict") if _kw(c, "quantity") is not None]
    assert len(dict_calls) == 1
    q = _kw(dict_calls[0], "quantity")
    assert isinstance(q, ast.Name) and q.id == fire, (
        f"`place_kwargs` 의 quantity = {ast.unparse(q)} — 재조회 결과 `{fire}` 여야 한다"
    )
    qty_maps = [
        n for n in ast.walk(fn)
        if isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Subscript)
        and isinstance(n.targets[0].value, ast.Attribute)
        and n.targets[0].value.attr == "_order_qty"
    ]
    assert len(qty_maps) == 1
    assert isinstance(qty_maps[0].value, ast.Name) and qty_maps[0].value.id == fire


# ════════════════════════════════════════════════════════════════════════════
# A5 — 신규 헬퍼 2개는 동기 · await 0 · never-raise · registry 전수
# ════════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("name", ["_ticker_holders", "_reorder_requery"])
def test_a5_new_helpers_are_sync_and_never_raise(oe, name):
    """🔴 A5 — `_ticker_holders`·`_reorder_requery` 는 동기 `def` · 본문 `Await` 0 ·
    본문 최상위에 `except Exception` 을 가진 `Try`.

    동기여야 재조회 ~ 보유 차감 / 재조회 ~ 발사가 한 덩어리로 원자적이다.
    """
    _, tree = oe
    fn = _func(tree, name)
    assert fn is not None, f"`{name}` 가 없다"
    assert isinstance(fn, ast.FunctionDef), f"`{name}` 는 동기 def 여야 한다"
    assert not _awaits(fn), f"`{name}` 본문에 await"
    tops = [s for s in fn.body if isinstance(s, ast.Try) and _catches_exception(s)]
    assert tops, f"`{name}` 본문 최상위에 `try/except Exception` 이 없다(never-raise)"


def test_a5b_ticker_holders_scans_registry_all_not_get_or_enabled(oe):
    """🔴 A5b — `_ticker_holders` 는 `registry.all()` 을 부르고 `registry.get`·
    `registry.enabled` 를 부르지 않는다.

    `get(strategy_id)` 는 `"momentum"` 기본값 함정, `enabled()` 는 꺼진 전략의 실보유를
    놓친다(루트 금기 「보유 전략 끄기」와 같은 이유).
    """
    _, tree = oe
    fn = _func(tree, "_ticker_holders")
    assert fn is not None
    reg_calls = [
        c.func.attr for c in ast.walk(fn)
        if isinstance(c, ast.Call) and isinstance(c.func, ast.Attribute)
        and isinstance(c.func.value, ast.Attribute) and c.func.value.attr == "registry"
    ]
    assert "all" in reg_calls, f"registry 전수 조회가 없다: {reg_calls}"
    assert "get" not in reg_calls and "enabled" not in reg_calls, reg_calls


def test_a5c_reorder_requery_delegates_to_ticker_holders(oe):
    """🔴 A5c — `_reorder_requery` 는 `_ticker_holders` 를 쓴다(판정 한 곳)."""
    _, tree = oe
    fn = _func(tree, "_reorder_requery")
    assert fn is not None and _calls(fn, "_ticker_holders")


# ════════════════════════════════════════════════════════════════════════════
# A6 — _handle_sell_fill 소유 해석
# ════════════════════════════════════════════════════════════════════════════
def test_a6_sell_fill_resolves_owner_via_holders_without_momentum_default(oe):
    """🔴 A6 — `_handle_sell_fill` 이 `_ticker_holders` 를 부르고,
    `_order_strategy.get(order_no, "momentum")` 는 0건(G147 교차)."""
    _, tree = oe
    fn = _func(tree, "_handle_sell_fill")
    assert _calls(fn, "_ticker_holders"), "소유 해석에 registry 전수 조회가 없다"
    bad = [
        c for c in _calls(fn, "get")
        if isinstance(c.func, ast.Attribute)
        and isinstance(c.func.value, ast.Attribute) and c.func.value.attr == "_order_strategy"
        and len(c.args) >= 2 and isinstance(c.args[1], ast.Constant)
        and c.args[1].value == "momentum"
    ]
    assert not bad, "`_order_strategy.get(order_no, \"momentum\")` 기본값 함정이 돌아왔다"


# ════════════════════════════════════════════════════════════════════════════
# A7 — J-1 주석 정정
# ════════════════════════════════════════════════════════════════════════════
def test_a7_j1_false_recovery_promise_is_gone(oe):
    """🔴 A7 — 「`cancel_remaining` 또는 `risk.on_tick` 재평가에 위임」 약속은 거짓이다.

    `risk.on_tick` 은 걸린 주문을 취소하지 않는다. 정본 = `src/engine/CLAUDE.md` 규칙 3.
    이 가드는 주석을 **의도적으로** 읽는다(J-1 은 주석 정정이다).

    cycle440 — 호출자가 0 이고 배선하면 매수 주문번호를 취소하는 함정이던
    `cancel_remaining` 자체는 삭제됐다(카드 #9).
    """
    src, tree = oe
    assert "`cancel_remaining` 또는 `risk.on_tick` 재평가에 위임" not in src, (
        "order_engine.py 에 거짓 회수 약속 주석이 남아 있다(J-1)"
    )
    fn = _func(tree, "_cancel_and_reorder")
    seg = ast.get_source_segment(src, fn) or ""
    assert "거두는 경로는 없다" in seg, (
        "`_cancel_and_reorder` 쌍 게이트 주석에 「그 잔량을 우리가 거두는 경로는 없다」가 "
        "없다 — 명세 §f-4 원문으로 바꾼다"
    )


# ════════════════════════════════════════════════════════════════════════════
# A8 — manual-sell `_selling` 은 발사 앞
# ════════════════════════════════════════════════════════════════════════════
def test_a8_manual_sell_marks_selling_before_send():
    """🔴 A8 — `manual_sell` 의 `_selling.add` 와 `_selling_since[...] =` 가
    `place_order` await **앞**에 있다."""
    src = _src(_ROUTE)
    tree = ast.parse(src)
    fn = _func(tree, "manual_sell")
    assert fn is not None
    places = _calls(fn, "place_order")
    assert len(places) == 1
    adds = [
        c for c in _calls(fn, "add")
        if isinstance(c.func, ast.Attribute)
        and isinstance(c.func.value, ast.Attribute) and c.func.value.attr == "_selling"
    ]
    assert adds, "manual_sell 에 `_selling.add` 가 없다"
    assert all(a.lineno < places[0].lineno for a in adds), (
        f"`_selling.add`(L{[a.lineno for a in adds]}) 가 `place_order`(L{places[0].lineno}) "
        "뒤에 있다 — 선행 체결이 해제한 뒤 다시 세워 좀비가 된다"
    )
    since = [
        n.lineno for n in ast.walk(fn)
        if isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Subscript)
        and isinstance(n.targets[0].value, ast.Attribute)
        and n.targets[0].value.attr == "_selling_since"
    ]
    assert since and min(since) < places[0].lineno, "`_selling_since` 기록이 발사 앞에 없다"


# ════════════════════════════════════════════════════════════════════════════
# A9 · A10 — 보유 차감의 위치
# ════════════════════════════════════════════════════════════════════════════
def test_a9_holding_decrement_precedes_first_await_after_owner_resolution(oe):
    """🔴 A9 — 보유 차감(`<pos>.quantity = …`)이 소유 해석(마지막 `_ticker_holders`)
    **뒤** · 그 다음 첫 `Await` **앞**에 있다.

    그 사이에 양보점이 끼면 `execute_sell` 루프 상단 재조회·J-2 재조회가 차감 전
    수량을 읽는다(M30).
    """
    _, tree = oe
    fn = _func(tree, "_handle_sell_fill")
    holders = _calls(fn, "_ticker_holders")
    assert holders, "소유 해석(`_ticker_holders`)이 없다"
    last_h = max(c.lineno for c in holders)
    after = [ln for ln in _awaits(fn) if ln > last_h]
    first_await = min(after) if after else 10**9
    stores = [n.lineno for n in _qty_stores(fn)]
    assert stores, "`_handle_sell_fill` 에 보유 차감 대입이 없다"
    assert any(last_h < ln < first_await for ln in stores), (
        f"보유 차감(L{stores})이 소유 해석(L{last_h}) 뒤 · 첫 await(L{first_await}) 앞이 아니다"
    )


def test_a10_holding_decrement_has_no_source_gate(oe):
    """🔴 A10 — 보유 차감이 `qty_src` 를 보는 If 안에 있지 않다(cycle329 금기).

    출처 게이트를 걸면 payload 가 없는 수동 전량 매도가 유보돼 유령 보유 +
    `_selling` 좀비 = 손절 마비가 된다.
    """
    _, tree = oe
    fn = _func(tree, "_handle_sell_fill")
    par = _parents(fn)
    stores = _qty_stores(fn)
    assert stores
    for st in stores:
        node = st
        while node in par and node is not fn:
            p = par[node]
            if isinstance(p, ast.If) and any(
                isinstance(x, ast.Name) and x.id == "qty_src" for x in ast.walk(p.test)
            ):
                pytest.fail(f"L{st.lineno} 보유 차감이 `qty_src` 게이트(L{p.lineno}) 안에 있다")
            node = p


# ════════════════════════════════════════════════════════════════════════════
# 부록 R — AR2 · AR3 · AR4b · AR8 ~ AR13 (명세 부록 R-8). AR5 = 위 A3b 개정.
# 부록 R2-13 이 AR1·AR4 → AR2-5, AR6 → AR2-1, AR7·AR10b → AR2-2 로 대체했다(파일 끝).
#
# 행위 짝 = `tests/unit/engine/test_cycle385r_recount_credit.py` (TR1~TR12) ·
#           `tests/unit/engine/test_cycle385r_partial_locked_sell.py` (TR13~TR19) ·
#           `tests/unit/engine/test_cycle385_reorder_requery.py` (TR22~TR26) ·
#           `tests/unit/routes/test_cycle385_manual_sell_selling.py` (TR20 · TR23 · TQ15 · TQ25) ·
#           `tests/unit/engine/test_cycle385r2_round2.py` (TQ1~TQ25)
# ════════════════════════════════════════════════════════════════════════════
_POSITIONS = _ROOT / "src" / "db" / "positions.py"
_BALANCE = _ROOT / "src" / "api" / "balance.py"


def _await_calls(fn: ast.AST, name: str) -> list[ast.Await]:
    return [
        n for n in ast.walk(fn)
        if isinstance(n, ast.Await) and isinstance(n.value, ast.Call)
        and _call_name(n.value) == name
    ]


def _attr_calls(fn: ast.AST, owner: str, method: str) -> list[ast.Call]:
    """`self.<owner>.<method>(...)` / `<x>.<owner>.<method>(...)` 호출."""
    return [
        c for c in ast.walk(fn)
        if isinstance(c, ast.Call) and isinstance(c.func, ast.Attribute)
        and c.func.attr == method and isinstance(c.func.value, ast.Attribute)
        and c.func.value.attr == owner
    ]


def _subscript_stores(fn: ast.AST, owner: str) -> list[ast.Assign]:
    return [
        n for n in ast.walk(fn)
        if isinstance(n, ast.Assign) and len(n.targets) == 1
        and isinstance(n.targets[0], ast.Subscript)
        and isinstance(n.targets[0].value, ast.Attribute)
        and n.targets[0].value.attr == owner
    ]


def _pos_qty_assigns(fn: ast.AST, value_name: str | None = None) -> list[ast.Assign]:
    out = []
    for n in ast.walk(fn):
        if isinstance(n, ast.Assign) and len(n.targets) == 1:
            t = n.targets[0]
            if isinstance(t, ast.Attribute) and t.attr == "quantity" \
                    and isinstance(t.value, ast.Name) and t.value.id == "pos":
                if value_name is None or (
                    isinstance(n.value, ast.Name) and n.value.id == value_name
                ):
                    out.append(n)
    return out


def test_ar2_notice_ledger_and_credit_precede_the_holding_decrement(oe):
    """🔴 AR2 (R-1-5) — `_handle_sell_fill`: `_sell_notice_seen[...]` 기록과
    `_sell_reflected_credit` 읽기가 보유 차감(`pos.quantity = …`)보다 앞이고, 소유 해석 뒤
    첫 `Await` 보다도 앞이다(A9 확장). 차감식 우변은 `hold_dec` 를 쓴다(흡수 뒤 초과분만).
    """
    _, tree = oe
    fn = _func(tree, "_handle_sell_fill")
    stores = _qty_stores(fn)
    assert len(stores) == 1, f"보유 차감 대입 {len(stores)}개 (기대 1)"
    dec = stores[0]
    assert any(isinstance(x, ast.Name) and x.id == "hold_dec" for x in ast.walk(dec.value)), (
        f"보유 차감 `{ast.unparse(dec)}` 이 `hold_dec` 를 쓰지 않는다 — 크레딧 흡수분까지 뺀다"
    )
    seen = _subscript_stores(fn, "_sell_notice_seen")
    assert seen, "`_sell_notice_seen[...] =` 원장 기록이 없다"
    credit_reads = [
        n.lineno for n in ast.walk(fn)
        if isinstance(n, ast.Attribute) and n.attr == "_sell_reflected_credit"
    ]
    assert credit_reads, "`_sell_reflected_credit` 를 읽지 않는다"
    holders = _calls(fn, "_ticker_holders")
    last_h = max(c.lineno for c in holders)
    after = [ln for ln in _awaits(fn) if ln > last_h]
    first_await = min(after) if after else 10**9
    assert max(s.lineno for s in seen) < dec.lineno < first_await
    assert min(credit_reads) < dec.lineno


def test_ar3_realized_pnl_still_counts_every_filled_share(oe):
    """🔴 AR3 — `profit_loss` 곱셈 피연산자는 `quantity`(체결 증분)다. 흡수분도 실제로 판
    주식이고 재대조는 손익을 적지 않았다 — `hold_dec` 로 바꾸면(MR14) 손익이 빠진다."""
    _, tree = oe
    fn = _func(tree, "_handle_sell_fill")
    pls = [
        n for n in ast.walk(fn)
        if isinstance(n, ast.Assign) and len(n.targets) == 1
        and isinstance(n.targets[0], ast.Name) and n.targets[0].id == "profit_loss"
    ]
    assert len(pls) == 1
    v = pls[0].value
    assert isinstance(v, ast.BinOp) and isinstance(v.op, ast.Mult)
    names = {x.id for x in (v.left, v.right) if isinstance(x, ast.Name)}
    assert names == {"quantity"}, f"`profit_loss = {ast.unparse(v)}` — 곱셈 피연산자가 `quantity` 가 아니다"


def test_ar4b_full_lock_marks_the_freeze_before_return(oe):
    """🔴 AR4b (R-2-2) — `[sell_qty_locked]`(sellable == 0 ∧ held > 0) return 앞에도 동결 표식.

    B4-4(cycle439) — 이 분기는 `OrderEngine._handle_sell_qty_exceeded` 로 옮겨졌다
    (행위 보존 추출, `execute_sell` 은 그 메서드를 부를 뿐이다).
    """
    src, tree = oe
    fn = _func(tree, "_handle_sell_qty_exceeded")
    hits = [
        n for n in ast.walk(fn)
        if isinstance(n, ast.If) and "[sell_qty_locked]" in (ast.get_source_segment(src, n) or "")
        and ast.unparse(n.test).replace(" ", "").startswith("sellable==0")
    ]
    hits = [h for h in hits if "held_qty>0" in ast.unparse(h.test).replace(" ", "")]
    assert len(hits) == 1, f"`sellable == 0 and held_qty > 0` 분기 {len(hits)}개"
    body = ast.Module(body=hits[0].body, type_ignores=[])
    rets = [n.lineno for n in ast.walk(body) if isinstance(n, ast.Return)]
    waits = [c.lineno for c in _attr_calls(body, "_selling_locked_wait", "add")]
    assert rets and waits and min(waits) < max(rets)


def test_ar8_route_marks_manual_orders_in_the_mapping_block():
    """🔴 AR8 (R-4-2) — `manual_sell`: `_manual_sell_orders[result.order_no] = _added` 가
    `place_order` await 뒤 · `insert_trade` await 앞, 그 사이 `Await` 0(매핑 3종과 같은 동기 구간).
    라우트가 표식을 안 적으면(MR28) J-2 가 운영자 주문 잔여를 `gone` 으로 버린다."""
    rsrc = _src(_ROUTE)
    fn = _func(ast.parse(rsrc), "manual_sell")
    marks = _subscript_stores(fn, "_manual_sell_orders")
    assert len(marks) == 1, f"`_manual_sell_orders[...] =` {len(marks)}개 (기대 1)"
    m = marks[0]
    assert isinstance(m.value, ast.Name) and m.value.id == "_added", ast.unparse(m.value)
    assert ast.unparse(m.targets[0].slice).replace(" ", "") == "result.order_no"
    place = _await_calls(fn, "place_order")
    ins = _await_calls(fn, "insert_trade")
    assert len(place) == 1 and ins
    assert place[0].end_lineno < m.lineno < min(i.lineno for i in ins)
    between = [ln for ln in _awaits(fn) if place[0].end_lineno < ln < m.lineno]
    assert not between, f"발사 await ~ manual 표식 사이 await: {between}"


def test_ar9_reorder_requery_reads_the_mark_not_the_strategy(oe):
    """🔴 AR9 (R-4-2) — `_reorder_requery` 는 `_manual_sell_orders` 를 읽고, 본문에 상수
    `"momentum"` 도 이름 `strategy_id` 도 없다(manual 을 전략 id 로 추론하지 않는다 — MR30)."""
    _, tree = oe
    fn = _func(tree, "_reorder_requery")
    assert fn is not None
    assert any(
        isinstance(n, ast.Attribute) and n.attr == "_manual_sell_orders" for n in ast.walk(fn)
    ), "`_reorder_requery` 가 manual 표식을 읽지 않는다"
    assert not [
        n for n in ast.walk(fn) if isinstance(n, ast.Constant) and n.value == "momentum"
    ], "`_reorder_requery` 에 \"momentum\" 상수"
    assert not [
        n for n in ast.walk(fn) if isinstance(n, ast.Name) and n.id == "strategy_id"
    ], "`_reorder_requery` 가 `strategy_id` 를 본다"
    rq = _calls(_func(tree, "_cancel_and_reorder"), "_reorder_requery")
    assert len(rq) == 1 and len(rq[0].args) + len(rq[0].keywords) == 3, (
        "`_reorder_requery(ticker, order_no, remaining)` 서명이 바뀌었다(전략 id 를 넘기지 않는다)"
    )


@pytest.mark.parametrize("name", [
    "_sell_fills_by_order", "_odno_key", "_sell_pending_dec",
    "_ord_datetime", "_sell_orders_placed_before", "_sell_not_placed_reason",
])
def test_ar10_r_helpers_are_sync_and_await_free(oe, name):
    """🔴 AR10 (부록 R2-13 목록 교체 · 부록 R3-8 에서 둘 · 부록 R4 에서 하나 추가) — 순수 헬퍼는 동기 `def` · 본문 `Await`
    0. 판정·계산이 한 덩어리로 원자적이어야 한다(검사와 그 행동 사이에 양보점 금지)."""
    _, tree = oe
    fn = _func(tree, name)
    assert fn is not None, f"`{name}` 가 없다"
    assert isinstance(fn, ast.FunctionDef), f"`{name}` 는 동기 def 여야 한다"
    assert not _awaits(fn), f"`{name}` 본문에 await"


_R_DAILY = (
    "_sell_notice_seen", "_sell_reflected_credit", "_sell_blind_credit",
    "_manual_sell_orders", "_selling_locked_wait",
)


def test_ar11_reset_daily_state_clears_every_r_structure(oe):
    """🔴 AR11 — `reset_daily_state` 가 부록 R 의 다섯 구조를 `clear()` 한다(주문번호는 하루
    단위로만 유일). `_sell_orders_done` 은 부록 R2 가 주인 규칙과 함께 지웠다(AR2-2).
    부록 R3-8 확장 — 원장(`_sell_notice_seen`)을 비우는 자리에서 원장 시작 시각도 다시 선다
    (`self._sell_ledger_since = datetime.now(_KST_TZ)` — AR3-1)."""
    _, tree = oe
    fn = _func(tree, "reset_daily_state")
    cleared = {
        c.func.value.attr for c in ast.walk(fn)
        if isinstance(c, ast.Call) and isinstance(c.func, ast.Attribute)
        and c.func.attr == "clear" and isinstance(c.func.value, ast.Attribute)
    }
    missing = [n for n in _R_DAILY if n not in cleared]
    assert not missing, f"`reset_daily_state` 가 비우지 않는다: {missing}"
    since = [ast.unparse(v).replace(" ", "") for _, v in _ledger_since_assigns(fn)]
    assert since == ["datetime.now(_KST_TZ)"], (
        f"`reset_daily_state` 의 `self._sell_ledger_since = …` {since} "
        "(기대 정확히 1 · `datetime.now(_KST_TZ)`) — 원장을 비우면서 시작 시각을 두면 다음 날 모든 "
        "주문이 「뒤」로 읽혀 전날 체결까지 pending 에 센다"
    )


def test_ar12_stale_notice_docstring_is_gone(oe):
    """🔴 AR12 (R-5 a) — 「매도: 체결 수량만큼 손익 계산, 포지션 제거」 는 B7 뒤 사실이 아니다
    (보유가 0 이 될 때만 제거). `handle_execution_notice` docstring 을 R-5 문구로 바꾼다."""
    src, tree = oe
    assert "매도: 체결 수량만큼 손익 계산, 포지션 제거" not in src
    doc = ast.get_docstring(_func(tree, "handle_execution_notice")) or ""
    assert "보유가 0 이 될 때만 포지션 제거" in doc, doc


def test_ar13_blank_name_and_pdno_contracts():
    """🔴 AR13 (R-5 d · R-1-7) — `save_position` SQL 에 `NULLIF(EXCLUDED.ticker_name, '')` ·
    `get_daily_orders` 에 keyword-only `pdno` 기본 `""`."""
    ptree = ast.parse(_src(_POSITIONS))
    sp = _func(ptree, "save_position")
    sqls = [
        n.value for n in ast.walk(sp)
        if isinstance(n, ast.Constant) and isinstance(n.value, str) and "INSERT INTO positions" in n.value
    ]
    assert len(sqls) == 1
    assert "NULLIF(EXCLUDED.ticker_name, '')" in sqls[0], "빈 종목명 upsert 가 저장된 이름을 덮는다"

    btree = ast.parse(_src(_BALANCE))
    gd = _func(btree, "get_daily_orders")
    kwonly = {a.arg: d for a, d in zip(gd.args.kwonlyargs, gd.args.kw_defaults)}
    assert "pdno" in kwonly, "get_daily_orders 에 keyword-only `pdno` 가 없다"
    d = kwonly["pdno"]
    assert isinstance(d, ast.Constant) and d.value == ""


# ════════════════════════════════════════════════════════════════════════════
# 부록 R2 — AR2-1 ~ AR2-8 (명세 부록 R2-13)
#
# 행위 짝 = `tests/unit/engine/test_cycle385r2_round2.py` (TQ1~TQ25).
# 판정식은 모양이 아니라 **뜻**으로 잰다 — If 테스트를 떼어 허용된 이름만 넣고 평가한다
# (다른 이름을 읽으면 `NameError` 로 붉다 = 「해제 판정이 무엇을 읽는가」 의 가드).
# ════════════════════════════════════════════════════════════════════════════
def _is_self_attr_call(c: ast.AST, owner: str, method: str) -> bool:
    return (
        isinstance(c, ast.Call) and isinstance(c.func, ast.Attribute) and c.func.attr == method
        and isinstance(c.func.value, ast.Attribute) and c.func.value.attr == owner
        and isinstance(c.func.value.value, ast.Name) and c.func.value.value.id == "self"
    )


def _is_stmt_call(stmt: ast.AST, owner: str, method: str, arg: str) -> bool:
    """문장이 정확히 `self.<owner>.<method>(<arg>)` 인가."""
    return (
        isinstance(stmt, ast.Expr) and _is_self_attr_call(stmt.value, owner, method)
        and len(stmt.value.args) == 1 and not stmt.value.keywords
        and isinstance(stmt.value.args[0], ast.Name) and stmt.value.args[0].id == arg
    )


def _bound_names(fn: ast.AST) -> list[tuple[str, int]]:
    """함수 안에서 **이름**에 값을 묶는 자리(대입·for·with·walrus·except as). 첨자·속성 대입은 제외."""
    out: list[tuple[str, int]] = []

    def names(t):
        if isinstance(t, ast.Name):
            out.append((t.id, t.lineno))
        elif isinstance(t, (ast.Tuple, ast.List)):
            for e in t.elts:
                names(e)
        elif isinstance(t, ast.Starred):
            names(t.value)

    for n in ast.walk(fn):
        if isinstance(n, ast.Assign):
            for t in n.targets:
                names(t)
        elif isinstance(n, (ast.AugAssign, ast.AnnAssign)):
            names(n.target)
        elif isinstance(n, (ast.For, ast.AsyncFor, ast.comprehension)):
            names(n.target)
        elif isinstance(n, (ast.With, ast.AsyncWith)):
            for it in n.items:
                if it.optional_vars is not None:
                    names(it.optional_vars)
        elif isinstance(n, ast.NamedExpr):
            names(n.target)
        elif isinstance(n, ast.ExceptHandler) and n.name:
            out.append((n.name, n.lineno))
    return out


def _stmt_in_list(par: dict, node: ast.AST):
    """`node` 를 품은 **문장**과 그 문장이 든 목록(body/orelse/finalbody)."""
    while True:
        p = par[node]
        for field in ("body", "orelse", "finalbody"):
            lst = getattr(p, field, None)
            if isinstance(lst, list) and node in lst:
                return node, lst
        node = p


def _eval_test(test: ast.AST, env: dict):
    return eval(compile(ast.Expression(body=test), "<guard>", "eval"), {"__builtins__": {}}, env)


def _ancestors(par: dict, node: ast.AST, stop: ast.AST) -> list[ast.AST]:
    """`node` 의 조상(바로 위부터, `stop` 은 제외)."""
    out = []
    while node in par:
        node = par[node]
        if node is stop:
            break
        out.append(node)
    return out


def _close_release_if(fn: ast.AST) -> ast.If:
    closes = [
        n for n in ast.walk(fn)
        if isinstance(n, ast.If) and isinstance(n.test, ast.Name) and n.test.id == "close_position"
        and _calls(n, "on_position_closed")
    ]
    assert len(closes) == 1, (
        f"`on_position_closed` 를 부르는 `if close_position:`(닫기 묶음) {len(closes)}개 (기대 1)"
    )
    hits = [
        n for n in ast.walk(closes[0])
        if isinstance(n, ast.If) and n is not closes[0]
        and any(_is_stmt_call(s, "_selling", "discard", "ticker") for s in n.body)
    ]
    assert len(hits) == 1, (
        f"닫기 묶음 안 `_selling.discard(ticker)` 를 가진 If {len(hits)}개 (기대 1 — 부록 R2-5)"
    )
    return closes[0], hits[0]


def test_ar2_1_order_end_release_reads_nothing_captured_before_an_await(oe):
    """🔴 AR2-1 (H1) — 주문 축 종료의 `_selling` 해제는 **판정이 없다**. 판정할 값이 없으니 통보
    시작 시점의 `qty_src` 나 첫 await 전에 잡은 `holders`·`owner`·`pos` 를 읽을 수도 없다.

    (가) 주문 축 If 의 첫 두 문장 = `self._selling.discard(ticker)` · `self._selling_locked_wait.
         discard(ticker)`, 그 If 의 첫 `Await` 앞.
    (나) 주문 축 If 안에서 `_selling.discard` 를 감싸는 다른 If 가 없다.
    (다) `_handle_sell_fill` 의 어느 `_selling.discard` 도 `qty_src` 를 읽는 If(또는 `qty_src` 를
         인자로 받는 호출을 테스트로 쓰는 If) 안에 있지 않다 — 범위 밖 = 전략 미등록 오류 경로.
    (라) 닫기 묶음 해제(R2-5) If 테스트는 `ticker`·`self._selling_locked_wait` 만 읽는다.
    (마) `ticker`·`order_no` 에 값을 다시 묶지 않는다(해제 대상이 통보의 종목·주문 그대로).
    되살아나면(`if qty_src == "map":` 게이트 — MQ1) 발사 창에서 시작해 DB await 에서 멈춘 우리
    통보가 REST 응답 뒤 재개될 때 좀비가 된다(p4a·p4b·p4c·money A2).
    """
    _, tree = oe
    fn = _func(tree, "_handle_sell_fill")
    ifs = _full_fill_ifs(fn)
    assert len(ifs) == 1
    oa = ifs[0]
    assert len(oa.body) >= 2 and _is_stmt_call(oa.body[0], "_selling", "discard", "ticker") \
        and _is_stmt_call(oa.body[1], "_selling_locked_wait", "discard", "ticker"), (
            "주문 축 If 의 첫 두 문장이 `self._selling.discard(ticker)` · "
            "`self._selling_locked_wait.discard(ticker)` 가 아니다(무조건 해제 — 부록 R2-2): "
            f"{[ast.unparse(x)[:60] for x in oa.body[:2]]}"
        )
    oa_awaits = _awaits(oa)
    assert oa_awaits and oa.body[1].lineno < min(oa_awaits), "해제가 주문 축 첫 await 뒤에 있다"

    par = _parents(fn)
    for d in _attr_calls(oa, "_selling", "discard"):
        wrapping = [a for a in _ancestors(par, d, oa) if isinstance(a, ast.If)]
        assert not wrapping, (
            f"L{d.lineno} 주문 축 `_selling.discard` 가 If(L{[w.lineno for w in wrapping]}) 안에 있다 "
            "— 종료 해제에 판정을 되살렸다(H1)"
        )

    def _reads_qty_src(test: ast.AST) -> bool:
        if any(isinstance(x, ast.Name) and x.id == "qty_src" for x in ast.walk(test)):
            return True
        return False

    for d in _attr_calls(fn, "_selling", "discard"):
        ifs_up = [a for a in _ancestors(par, d, fn) if isinstance(a, ast.If)]
        if any(ast.unparse(a.test).replace(" ", "") == "notstrategy" for a in ifs_up):
            continue  # 전략 미등록 오류 경로(명세 범위 밖)
        for a in ifs_up:
            assert not _reads_qty_src(a.test), (
                f"L{d.lineno} `_selling.discard` 가 `qty_src` 를 읽는 If(L{a.lineno}) 안에 있다 — "
                "통보 시작 시점 값으로 해제를 가른다(H1)"
            )

    _, rel = _close_release_if(fn)
    allowed_names = {n.id for n in ast.walk(rel.test) if isinstance(n, ast.Name)}
    allowed_attrs = {n.attr for n in ast.walk(rel.test) if isinstance(n, ast.Attribute)}
    assert allowed_names <= {"ticker", "self"} and allowed_attrs <= {"_selling_locked_wait"}, (
        f"닫기 묶음 해제 If `{ast.unparse(rel.test)}` 가 `ticker`·`self._selling_locked_wait` "
        "밖의 값을 읽는다"
    )

    rebound = [(n, ln) for n, ln in _bound_names(fn) if n in ("ticker", "order_no")]
    assert not rebound, f"`_handle_sell_fill` 이 `ticker`/`order_no` 를 다시 묶는다: {rebound}"


def test_ar2_2_r3_owner_rule_symbols_are_gone(oe):
    """🔴 AR2-2 (R2-2) — `order_engine.py`·`routes/trading.py` 에 `_sell_placed` ·
    `_sell_end_releases_selling` · `_sell_orders_done`(정의·호출·속성) 0, 로그 문자열
    `[selling_kept]` · `[selling_released_after_window]` 0. 주석은 세지 않는다(AST).
    부록 R 소유 규칙의 잔재가 남으면 AR2-1 을 우회하는 판정 헬퍼가 되살아날 자리가 된다."""
    banned = {"_sell_placed", "_sell_end_releases_selling", "_sell_orders_done"}
    markers = ("[selling_kept]", "[selling_released_after_window]")
    for path in (_OE, _ROUTE):
        tree = ast.parse(_src(path))
        hits = []
        for n in ast.walk(tree):
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name in banned:
                hits.append((n.name, n.lineno))
            elif isinstance(n, ast.Attribute) and n.attr in banned:
                hits.append((n.attr, n.lineno))
            elif isinstance(n, ast.Name) and n.id in banned:
                hits.append((n.id, n.lineno))
            elif isinstance(n, ast.Constant) and isinstance(n.value, str) \
                    and any(m in n.value for m in markers):
                hits.append((n.value[:40], n.lineno))
        assert not hits, f"{path.name}: 부록 R-3 소유 규칙 잔재 {hits}"


def test_ar2_3_reorder_releases_selling_only_when_nothing_of_ours_rests(oe):
    """🔴 AR2-3 (H5 · 부록 R3 K2·K3 · 부록 R4 D2 개정) — `_cancel_and_reorder`:
    - 최상위 `Try` **앞**에서 `_cancel_ok = False` · `_place_state = "none"`(`_cancel_ok = False` 는 1곳).
    - `place_order` await 는 `except KisApiError as <n>:` 핸들러를 가진 `Try` 안이고, 그 본문은 맨 끝이
      bare `raise`(그 밖의 raise·await 0) · `_sell_not_placed_reason(<n>)` 호출 정확히 1 · 그 결과가
      None 이 아닐 때만 `_place_state = "rejected"`(본문을 실행해 잰다 — R4 D2: APBK0400 · 시장가 불가 ·
      장운영시간 외만 「안 걸렸다」. `_request` 는 주문 POST 도 재시도하므로 그 밖의 거부는 앞 시도가
      접수됐을 수 있다). 분류기 셋(`is_sell_qty_exceeded`·`is_market_closed_rejection`·
      `is_market_order_disallowed`)을 이 함수가 직접 부르지 않는다(판정은 한 곳). 그 `Try` 앞(같은 본문,
      사이 await 0)에 `_place_state = "sending"`. 해제 로그 문구에 `reject=` 칸.
    - 최상위 `Try` 의 `finally` 에 `self._selling.discard(ticker)` 를 가진 If 가 있고, 그 테스트는
      `_cancel_ok`·`_place_state`·`ticker`·`order_no`·`self` 만 읽어 **취소 성공 ∧ (none ∨ rejected) ∧
      (동결 표식 ∨ 주인)** 일 때만 참이다(`sending`·`accepted` 는 유지 — 나갔을 수 있다 · K3 — 동결
      표식이 서 있으면 손님 manual 의 재주문 거부도 푼다).
    - `finally` 안 `Await` 0.
    """
    _, tree = oe
    fn = _func(tree, "_cancel_and_reorder")
    top_tries = [i for i, st in enumerate(fn.body) if isinstance(st, ast.Try)]
    assert top_tries, "`_cancel_and_reorder` 최상위 Try 가 없다"
    ti = top_tries[0]
    top = fn.body[ti]
    pre = {ast.unparse(st).replace(" ", "") for st in fn.body[:ti]}
    assert "_cancel_ok=False" in pre and "_place_state='none'" in pre, (
        f"최상위 Try 앞에 `_cancel_ok = False` · `_place_state = \"none\"` 초기화가 없다: {pre}"
    )
    resets = [
        n for n in ast.walk(fn)
        if isinstance(n, ast.Assign) and ast.unparse(n).replace(" ", "") == "_cancel_ok=False"
    ]
    assert len(resets) == 1, f"`_cancel_ok = False` {len(resets)}곳 (기대 1 — 위로 올렸다)"

    par = _parents(fn)
    places = _await_calls(fn, "place_order")
    assert len(places) == 1
    tr = next(a for a in _ancestors(par, places[0], fn) if isinstance(a, ast.Try))
    kis = [
        h for h in tr.handlers
        if isinstance(h.type, ast.Name) and h.type.id == "KisApiError"
    ]
    assert kis, "`place_order` 를 감싼 Try 에 `except KisApiError:` 가 없다"
    h = kis[0]
    assert h.name, "`except KisApiError as <n>:` — 거부 코드를 읽을 이름이 없다(부록 R3 K2)"
    hb = h.body
    assert hb and isinstance(hb[-1], ast.Raise) and hb[-1].exc is None and hb[-1].cause is None, (
        f"`except KisApiError as {h.name}:` 본문 {[ast.unparse(x)[:60] for x in hb]} — 맨 끝이 bare "
        "`raise` 여야 한다(그 예외는 바깥 `except Exception` 이 기록한다)"
    )
    hmod = ast.Module(body=hb, type_ignores=[])
    assert not _awaits(hmod), "재주문 거부 핸들러 안에 await — 판정과 상태 기록 사이에 양보점"
    assert sum(isinstance(n, ast.Raise) for n in ast.walk(hmod)) == 1, "핸들러 안 raise 가 둘 이상"
    npr = _calls(hmod, "_sell_not_placed_reason")
    assert len(npr) == 1 and isinstance(npr[0].func, ast.Name) and not npr[0].keywords \
        and len(npr[0].args) == 1 and isinstance(npr[0].args[0], ast.Name) \
        and npr[0].args[0].id == h.name, (
            f"핸들러의 `_sell_not_placed_reason({h.name})` 호출 {[ast.unparse(c) for c in npr]} — "
            "정확히 1(부록 R4 D2 — 판정은 한 곳)"
        )
    for _nm in _NOT_PLACED_CLASSIFIERS:
        assert not _calls(fn, _nm), (
            f"`_cancel_and_reorder` 가 `{_nm}` 를 직접 부른다 — 판정은 `_sell_not_placed_reason` 한 곳"
            "(부록 R4 D2)"
        )
    _code = compile(ast.fix_missing_locations(ast.Module(body=hb[:-1], type_ignores=[])),
                    "<reorder_place_handler>", "exec")
    for _ret, _want in ((None, "sending"), ("qty_exceeded", "rejected"),
                        ("market_closed", "rejected"), ("market_order_disallowed", "rejected")):
        _ns = {h.name: object(), "_sell_not_placed_reason": (lambda _e, _r=_ret: _r),
               "_place_state": "sending"}
        exec(_code, _ns)
        assert _ns["_place_state"] == _want, (
            f"판정 결과 {_ret!r} → `_place_state` {_ns['_place_state']!r} (기대 {_want!r}) — "
            "None 이면 「전송 중」 유지, 이유가 있으면 「rejected」(부록 R4 D2)"
        )
    _, seq = _stmt_in_list(par, tr)
    idx = seq.index(tr)
    sending = [
        i for i, st in enumerate(seq[:idx])
        if ast.unparse(st).replace(" ", "") == "_place_state='sending'"
    ]
    assert sending, "`place_order` Try 앞에 `_place_state = \"sending\"` 가 없다"
    between = [ln for st in seq[sending[-1] + 1:idx] for ln in _awaits(st)]
    assert not between, f"`_place_state = \"sending\"` ~ 발사 Try 사이 await: {between}"

    assert top.finalbody, "최상위 Try 에 finally 가 없다"
    fin = ast.Module(body=top.finalbody, type_ignores=[])
    assert not _awaits(fin), "finally 안에 await — 교체 취소 중에 양보한다"
    rel = [
        n for n in ast.walk(fin)
        if isinstance(n, ast.If) and any(_is_stmt_call(s, "_selling", "discard", "ticker") for s in n.body)
    ]
    assert len(rel) == 1, f"finally 의 `_selling.discard(ticker)` If {len(rel)}개 (기대 1)"
    _marks = [
        c for c in ast.walk(rel[0])
        if isinstance(c, ast.Constant) and isinstance(c.value, str)
        and c.value.startswith("[reorder_selling_released]")
    ]
    assert len(_marks) == 1 and " reject=" in _marks[0].value, (
        f"`[reorder_selling_released]` 문구 {[m.value for m in _marks]} — 분류 칸 `reject=` (부록 R4 D2)"
    )
    test = rel[0].test

    def ev(ok, state, marks, frozen):
        return bool(_eval_test(test, {
            "_cancel_ok": ok, "_place_state": state, "ticker": "T", "order_no": "O",
            "self": SimpleNamespace(_selling={"T"}, _manual_sell_orders=marks,
                                    _selling_locked_wait={"T"} if frozen else set()),
        }))

    for ok in (True, False):
        for state in ("none", "sending", "accepted", "rejected"):
            for marks, owner in (({}, True), ({"O": True}, True), ({"O": False}, False)):
                for frozen in (True, False):
                    want = ok and state in ("none", "rejected") and (frozen or owner)
                    assert ev(ok, state, marks, frozen) is want, (
                        f"H5 해제 판정 `{ast.unparse(test)}` — cancel_ok={ok} place={state} "
                        f"marks={marks} frozen={frozen}: {not want} (기대 {want})"
                    )


def test_ar2_4_ticker_credit_accumulates(oe):
    """🔴 AR2-4 (H2) — `_handle_sell_qty_exceeded`(B4-4, cycle439 — 전에는 `execute_sell`
    안이었다)의 `self._sell_blind_credit[ticker]` 대입은 전부 누적
    (`self._sell_blind_credit.get(ticker, 0) + _blind` 또는 `+= _blind`)이고, 맨 `_blind` 대입 0.
    덮어쓰면 소진 전 첫 몫의 통보가 보유를 다시 뺀다(과소 추적 — money A3)."""
    _, tree = oe
    fn = _func(tree, "_handle_sell_qty_exceeded")
    stores = _subscript_stores(fn, "_sell_blind_credit")
    augs = [
        n for n in ast.walk(fn)
        if isinstance(n, ast.AugAssign) and isinstance(n.target, ast.Subscript)
        and isinstance(n.target.value, ast.Attribute) and n.target.value.attr == "_sell_blind_credit"
    ]
    assert stores or augs, "`_handle_sell_qty_exceeded` 에 종목 크레딧 기록이 없다"
    for n in stores:
        v = ast.unparse(n.value).replace(" ", "")
        assert v in (
            "self._sell_blind_credit.get(ticker,0)+_blind",
            "_blind+self._sell_blind_credit.get(ticker,0)",
        ), f"L{n.lineno} `{ast.unparse(n)}` — 종목 크레딧은 누적한다(부록 R2-7)"
    for n in augs:
        assert isinstance(n.op, ast.Add) and ast.unparse(n.value) == "_blind", ast.unparse(n)


def test_ar2_5_f3_and_reconcile_share_one_query_then_recheck_then_eff(oe):
    """🔴 AR2-5 (H3 — AR1·AR4 대체) — `_handle_sell_qty_exceeded`(B4-4, cycle439 —
    전에는 `execute_sell` 안이었다):
    - `await self._sell_orders_snapshot(ticker)` 정확히 1개, `await get_balance()` 뒤.
    - 그 문장의 바로 다음 문장 = `if strategy.state.positions.get(ticker) is not pos:`(동일성 재검증).
    - 그 뒤 ~ `pos.quantity = target_qty` · `return SellQtyExceededOutcome.RETRY, fire` 사이 `Await` 0.
    - F-3 If 테스트 = `held_qty >= eff`(1개). 본문: `pos.quantity` 대입 0 ·
      `return SellQtyExceededOutcome.RETRY, fire` 1 · `return` 앞 `_selling_locked_wait.add`.
    - `eff` 우변에 `pos.quantity - pending` · `fire` 우변(또는 감싼 If)에 `fills is not None` 조건.
    분기 술어를 `held_qty >= pos.quantity` 로 되돌리면(MQ5) 오늘 주문으로 설명되는 차이를 재대조가
    받아들여 운영자 몫을 추적에 싣는다.
    """
    _, tree = oe
    fn = _func(tree, "_handle_sell_qty_exceeded")
    snaps = [
        n for n in ast.walk(fn)
        if isinstance(n, ast.Await) and isinstance(n.value, ast.Call)
        and isinstance(n.value.func, ast.Attribute)
        and n.value.func.attr == "_sell_orders_snapshot"
        and isinstance(n.value.func.value, ast.Name) and n.value.func.value.id == "self"
    ]
    assert len(snaps) == 1, f"`await self._sell_orders_snapshot(...)` {len(snaps)}개 (기대 1)"
    sn = snaps[0]
    assert [ast.unparse(a) for a in sn.value.args] == ["ticker"] and not sn.value.keywords
    bal = _await_calls(fn, "get_balance")
    assert bal and min(b.lineno for b in bal) < sn.lineno, "주문 조회가 잔고 조회 뒤가 아니다(R-1-6)"

    par = _parents(fn)
    stmt, seq = _stmt_in_list(par, sn)
    nxt = seq[seq.index(stmt) + 1]
    assert isinstance(nxt, ast.If) and ast.unparse(nxt.test).replace(" ", "") == \
        "strategy.state.positions.get(ticker)isnotpos", (
            f"주문 조회 바로 다음 문장이 동일성 재검증 If 가 아니다: {ast.unparse(nxt)[:80]}"
        )

    tgt = _pos_qty_assigns(fn, "target_qty")
    assert len(tgt) == 1, f"`pos.quantity = target_qty` {len(tgt)}개 (기대 1)"
    # B4-4(cycle439) — 「`sell_cap = fire`」 는 `return SellQtyExceededOutcome.RETRY, fire`
    # 가 됐다(이 메서드가 더는 `execute_sell` 의 `sell_cap` 지역변수를 직접 대입하지 않고,
    # 새 값을 호출부에 돌려준다).
    caps = [
        n for n in ast.walk(fn)
        if isinstance(n, ast.Return) and isinstance(n.value, ast.Tuple)
        and len(n.value.elts) == 2
        and ast.unparse(n.value.elts[0]).replace(" ", "") == "SellQtyExceededOutcome.RETRY"
        and isinstance(n.value.elts[1], ast.Name) and n.value.elts[1].id == "fire"
    ]
    assert len(caps) == 1, (
        f"`return SellQtyExceededOutcome.RETRY, fire` {len(caps)}개 (기대 1)"
    )
    for end in (tgt[0].lineno, caps[0].lineno):
        between = [ln for ln in _awaits(fn) if sn.lineno < ln < end]
        assert not between, f"주문 조회(L{sn.lineno}) ~ 행동(L{end}) 사이 await: {between}"

    f3 = [
        n for n in ast.walk(fn)
        if isinstance(n, ast.If) and ast.unparse(n.test).replace(" ", "") == "held_qty>=eff"
    ]
    assert len(f3) == 1, f"`if held_qty >= eff:` {len(f3)}개 (기대 1 — 부록 R2-8 분기 술어)"
    assert not [
        n for n in ast.walk(fn)
        if isinstance(n, ast.If) and ast.unparse(n.test).replace(" ", "").find("held_qty>=pos.quantity") >= 0
    ], "`held_qty >= pos.quantity` 분기가 남았다(분기 술어는 eff)"
    body = ast.Module(body=f3[0].body, type_ignores=[])
    assert not _pos_qty_assigns(body), "F-3 분기가 추적 수량(`pos.quantity`)을 바꾼다"
    assert caps[0] in list(ast.walk(body)), (
        "`return SellQtyExceededOutcome.RETRY, fire` 가 F-3 분기 밖에 있다"
    )
    rets = [n.lineno for n in ast.walk(body) if isinstance(n, ast.Return)]
    waits = [c.lineno for c in _attr_calls(body, "_selling_locked_wait", "add")]
    assert rets and waits and min(waits) < max(rets), "F-3 동결 return 앞에 동결 표식이 없다"

    effs = [
        n for n in ast.walk(fn)
        if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "eff"
                                             for t in n.targets)
    ]
    assert len(effs) == 1 and "pos.quantity-pending" in ast.unparse(effs[0].value).replace(" ", ""), (
        f"`eff = …` {[ast.unparse(e) for e in effs]} — 우변에 `pos.quantity - pending`"
    )
    fires = [
        n for n in ast.walk(fn)
        if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "fire"
                                             for t in n.targets)
    ]
    assert fires
    for fa in fires:
        ctx = ast.unparse(fa.value).replace(" ", "") + "".join(
            ast.unparse(a.test).replace(" ", "") for a in _ancestors(par, fa, fn) if isinstance(a, ast.If)
        )
        assert "fillsisnotNone" in ctx, (
            f"L{fa.lineno} `{ast.unparse(fa)}` — 조회 실패(`fills is None`)면 발사 0 이어야 한다(H3)"
        )


def test_ar2_6_order_snapshot_is_bounded_scoped_and_page_unaware(oe):
    """🔴 AR2-6 (H6 · XT-K · cycle432 로 H7「쪽 크기 환경 분기」 제거) —
    `_sell_orders_snapshot`(async): 유일한 await = `asyncio.wait_for(…,
    timeout=SELL_ORDERS_QUERY_TIMEOUT)` · 그 안 `get_daily_orders` 인자 =
    정확히 `exchange="ALL"`·`pdno=ticker`. `_sell_fills_by_order` 서명
    `(rows, ticker)` 기본값 없음 · 모듈에 쪽 크기 상수·`page_full` 리터럴 0."""
    src, tree = oe
    fn = _func(tree, "_sell_orders_snapshot")
    assert isinstance(fn, ast.AsyncFunctionDef), "`_sell_orders_snapshot` 는 async def"
    aws = [n for n in ast.walk(fn) if isinstance(n, ast.Await)]
    assert len(aws) == 1, f"`_sell_orders_snapshot` await {len(aws)}개 (기대 1 = wait_for)"
    wf = aws[0].value
    assert isinstance(wf, ast.Call) and isinstance(wf.func, ast.Attribute) \
        and wf.func.attr == "wait_for" and isinstance(wf.func.value, ast.Name) \
        and wf.func.value.id == "asyncio", f"await 대상이 `asyncio.wait_for` 가 아니다: {ast.unparse(wf)}"
    to = _kw(wf, "timeout")
    assert isinstance(to, ast.Name) and to.id == "SELL_ORDERS_QUERY_TIMEOUT", ast.unparse(wf)
    gd = _calls(wf, "get_daily_orders")
    assert len(gd) == 1 and not gd[0].args, f"wait_for 안 `get_daily_orders` 호출: {ast.unparse(wf)}"
    kw = {k.arg: ast.unparse(k.value) for k in gd[0].keywords}
    assert kw == {"exchange": "'ALL'", "pdno": "ticker"}, (
        f"주문 조회 인자 {kw} — 정확히 `exchange=\"ALL\", pdno=ticker`(KRX 만 보면 NXT/SOR 체결을 놓친다)"
    )
    assert not any(
        isinstance(n, ast.Attribute) and n.attr == "is_production"
        and isinstance(n.value, ast.Name) and n.value.id == "settings"
        for n in ast.walk(fn)
    ), "cycle432 이후 `_sell_orders_snapshot` 가 쪽 크기를 환경으로 고르면 안 된다(page_full 제거)"

    parser = _func(tree, "_sell_fills_by_order")
    a = parser.args
    assert [x.arg for x in a.args] == ["rows", "ticker"] and not a.defaults \
        and not a.kwonlyargs, (
            f"`_sell_fills_by_order` 서명 {[x.arg for x in a.args]} · 기본값 {len(a.defaults)} "
            "(cycle432 — page_size 인자 제거)"
        )
    consts = {
        t.id: n.value.value for n in tree.body if isinstance(n, ast.Assign)
        for t in n.targets if isinstance(t, ast.Name) and isinstance(n.value, ast.Constant)
    }
    assert consts.get("SELL_ORDERS_QUERY_TIMEOUT") == 2.0
    assert "_DAILY_ORDERS_PAGE_REAL" not in consts, "cycle432 — 쪽 크기 상수가 남아 있다"
    assert "_DAILY_ORDERS_PAGE_VTS" not in consts, "cycle432 — 쪽 크기 상수가 남아 있다"
    # 설명 주석(docstring)의 어휘는 제외하고, 코드가 쓰는 문자열 리터럴에서만 확인한다.
    str_consts = {
        n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str)
    }
    assert "page_full" not in str_consts, "cycle432 — `page_full` 문자열 리터럴이 코드에 남아 있다"


def test_ar2_7_freeze_released_when_guarded_holding_closes(oe):
    """🔴 AR2-7 (R2-5) — 닫기 묶음(`if close_position:`) 안 `self._selling.discard(ticker)` 는
    `ticker in self._selling_locked_wait` 에서만 참인 If 안이고, 그 묶음의 첫 `Await` 앞 ·
    `on_position_closed` 앞이다. 무조건 풀면(MQ21) 우리 주문이 걸린 채 외부 체결이 보유를 0 으로
    만든 경우에도 풀린다(T6)."""
    _, tree = oe
    fn = _func(tree, "_handle_sell_fill")
    close, rel = _close_release_if(fn)
    for inside, want in ((True, True), (False, False)):
        got = bool(_eval_test(rel.test, {
            "ticker": "T", "self": SimpleNamespace(_selling_locked_wait={"T"} if inside else set()),
        }))
        assert got is want, f"`{ast.unparse(rel.test)}` 동결 표식 {inside} → {got} (기대 {want})"
    first_await = min(_awaits(close) or [10**9])
    assert rel.lineno < first_await, "동결 닫힘 해제가 닫기 묶음 첫 await 뒤에 있다"
    hooks = _calls(close, "on_position_closed")
    assert hooks and rel.lineno < min(h.lineno for h in hooks), "해제가 `on_position_closed` 뒤에 있다"


def test_ar2_8_pending_reads_ledger_and_order_credit_not_ticker_credit(oe):
    """🔴 AR2-8 (H3) — `_sell_pending_dec` 는 동기 `def` · `Await` 0 · `_sell_notice_seen`·
    `_sell_reflected_credit` 를 읽고 `_sell_blind_credit` 는 **읽지 않는다**(종목 크레딧에는 유실
    통보가 섞일 수 있어, 빼면 eff 가 커져 운영자 몫을 판다 — MQ8)."""
    _, tree = oe
    fn = _func(tree, "_sell_pending_dec")
    assert fn is not None and isinstance(fn, ast.FunctionDef), "`_sell_pending_dec` 는 동기 def"
    assert not _awaits(fn)
    attrs = {n.attr for n in ast.walk(fn) if isinstance(n, ast.Attribute)}
    assert {"_sell_notice_seen", "_sell_reflected_credit"} <= attrs, attrs
    assert "_sell_blind_credit" not in attrs, "pending 이 종목 크레딧을 읽는다(보수 위반)"


# ════════════════════════════════════════════════════════════════════════════
# 부록 R3 — AR3-1 ~ AR3-7 (명세 부록 R3-8). AR2-3 · AR10 · AR11 은 위에서 개정·확장했다.
#
# 행위 짝 = `tests/unit/engine/test_cycle385r3_round3.py` (TK1~TK13) ·
#           `tests/unit/routes/test_cycle385_manual_sell_selling.py` (TK11a · TK11b)
# 판정식은 AR2-* 와 같이 **뜻**으로 잰다(If 테스트를 떼어 허용된 이름만 넣고 평가).
# ════════════════════════════════════════════════════════════════════════════
def _ledger_since_assigns(fn: ast.AST) -> list[tuple[ast.AST, ast.AST]]:
    """`self._sell_ledger_since = …`(주석 대입 포함) — (문장, 우변)."""
    out = []
    for n in ast.walk(fn):
        if isinstance(n, ast.Assign):
            targets, value = n.targets, n.value
        elif isinstance(n, ast.AnnAssign) and n.value is not None:
            targets, value = [n.target], n.value
        elif isinstance(n, ast.AugAssign):
            targets, value = [n.target], n.value
        else:
            continue
        for t in targets:
            if isinstance(t, ast.Attribute) and t.attr == "_sell_ledger_since" \
                    and isinstance(t.value, ast.Name) and t.value.id == "self":
                out.append((n, value))
    return out


def test_ar3_1_ledger_since_is_set_where_the_ledger_starts(oe):
    """🔴 AR3-1 (R3-1-2) — `OrderEngine.__init__` 에 `self._sell_ledger_since = datetime.now(_KST_TZ)`
    (주석 대입 허용) 정확히 1 · `reset_daily_state` 에 같은 대입 정확히 1 · 모듈의 다른 어디에도 대입 0.

    뜻 = 「`_sell_notice_seen` 은 이 시각 **뒤**에 처리한 매도 통보를 빠짐없이 담는다」. 원장이 비는
    자리(프로세스 시작 · 21:30 정산 리셋) 말고 다른 곳에서 옮기면 그 뜻이 깨진다.
    🔴 벽시계 게이트가 아니다 — 판정은 이 기록값과 주문의 접수 시각의 비교다(AR3-2 · MK17).
    """
    _, tree = oe
    for name in ("__init__", "reset_daily_state"):
        fn = _func(tree, name)
        assert fn is not None, f"`{name}` 가 없다"
        got = [ast.unparse(v).replace(" ", "") for _, v in _ledger_since_assigns(fn)]
        assert got == ["datetime.now(_KST_TZ)"], (
            f"`{name}` 의 `self._sell_ledger_since = …` {got} (기대 정확히 1 · `datetime.now(_KST_TZ)`)"
        )
    all_sites = sorted(n.lineno for n, _ in _ledger_since_assigns(tree))
    assert len(all_sites) == 2, (
        f"`self._sell_ledger_since` 대입 {len(all_sites)}곳 L{all_sites} (기대 2 — 엔진 생성·일일 리셋)"
    )


def _return_tuples(v: ast.AST) -> list[ast.AST]:
    if isinstance(v, ast.IfExp):
        return _return_tuples(v.body) + _return_tuples(v.orelse)
    return [v]


def test_ar3_2_order_snapshot_returns_the_pre_ledger_set(oe):
    """🔴 AR3-2 (R3-1-4, cycle432 로 실패 셋으로 축소 — `page_full` 제거) —
    `_sell_orders_snapshot` 의 모든 `Return` 값이 3-튜플.
    실패 셋(`timeout`·`error`·`bad_row` — 첫째 `None`)의 셋째 = `frozenset()` ·
    정상(둘째 `"ok"`) 1개의 셋째 = `_sell_orders_placed_before(rows, ticker, self._sell_ledger_since)`.
    분류 기준을 벽시계(`datetime.now(...)`)로 바꾸면(MK17) 재시작 전 주문이 전부 「뒤」가 된다."""
    _, tree = oe
    fn = _func(tree, "_sell_orders_snapshot")
    assert fn is not None
    vals = [t for r in ast.walk(fn) if isinstance(r, ast.Return) for t in _return_tuples(r.value)]
    assert vals, "`_sell_orders_snapshot` 에 return 이 없다"
    bad = [ast.unparse(v) for v in vals if not (isinstance(v, ast.Tuple) and len(v.elts) == 3)]
    assert not bad, f"3-튜플이 아닌 반환 {bad}"
    reasons, ok = set(), []
    for v in vals:
        first, second, third = v.elts
        if isinstance(first, ast.Constant) and first.value is None:
            assert isinstance(second, ast.Constant), ast.unparse(v)
            reasons.add(second.value)
            assert ast.unparse(third).replace(" ", "") == "frozenset()", (
                f"실패 반환 `{ast.unparse(v)}` — 셋째는 `frozenset()`"
            )
        else:
            ok.append(v)
    assert reasons == {"timeout", "error", "bad_row"}, reasons
    assert len(ok) == 1, f"정상 반환 {len(ok)}개 (기대 1): {[ast.unparse(v) for v in ok]}"
    _, second, third = ok[0].elts
    assert isinstance(second, ast.Constant) and second.value == "ok"
    assert isinstance(third, ast.Call) and isinstance(third.func, ast.Name) \
        and third.func.id == "_sell_orders_placed_before" and not third.keywords \
        and [ast.unparse(a) for a in third.args] == ["rows", "ticker", "self._sell_ledger_since"], (
            f"정상 반환 셋째 `{ast.unparse(third)}` — "
            "`_sell_orders_placed_before(rows, ticker, self._sell_ledger_since)` 여야 한다"
        )


def test_ar3_3_pending_excludes_pre_and_clamps_per_order(oe):
    """🔴 AR3-3 (R3-1-4 · K4 구조판) — `_sell_pending_dec(self, fills, pre)`(기본값 없음) · return 1개 =
    `sum(<생성식>)` · 원소 = `max(0, …)` 호출(바깥 `max(0, sum(…))` 아님 — 합 뒤 clamp 면 표 지연
    주문의 음수가 다른 주문의 대기분을 지운다, XF3c · MK16) · 생성식 조건 = `<주문키> not in pre`."""
    _, tree = oe
    fn = _func(tree, "_sell_pending_dec")
    assert fn is not None
    a = fn.args
    assert [x.arg for x in a.args] == ["self", "fills", "pre"] and not a.defaults \
        and not a.kwonlyargs, f"`_sell_pending_dec` 서명 {[x.arg for x in a.args]}"
    rets = [n for n in ast.walk(fn) if isinstance(n, ast.Return)]
    assert len(rets) == 1, f"return {len(rets)}개 (기대 1)"
    v = rets[0].value
    assert isinstance(v, ast.Call) and isinstance(v.func, ast.Name) and v.func.id == "sum" \
        and len(v.args) == 1 and not v.keywords and isinstance(v.args[0], ast.GeneratorExp), (
            f"반환 `{ast.unparse(v)[:80]}` — `sum(<생성식>)` 여야 한다(바깥 clamp 금지)"
        )
    gen = v.args[0]
    elt = gen.elt
    assert isinstance(elt, ast.Call) and isinstance(elt.func, ast.Name) and elt.func.id == "max" \
        and len(elt.args) == 2 and isinstance(elt.args[0], ast.Constant) and elt.args[0].value == 0, (
            f"생성식 원소 `{ast.unparse(elt)[:80]}` — 주문별 `max(0, …)` 여야 한다(K4)"
        )
    assert len(gen.generators) == 1
    comp = gen.generators[0]
    tgt = comp.target
    key = tgt.elts[0].id if isinstance(tgt, ast.Tuple) and isinstance(tgt.elts[0], ast.Name) else None
    assert key, f"생성식 대상 `{ast.unparse(tgt)}` — (주문키, 체결) 튜플"
    assert ast.unparse(comp.iter).replace(" ", "") == "fills.items()", ast.unparse(comp.iter)
    conds = [ast.unparse(c).replace(" ", "") for c in comp.ifs]
    assert conds == [f"{key}notinpre"], (
        f"생성식 조건 {conds} — `{key} not in pre` 하나(원장 시작 전 주문은 pending 에 세지 않는다)"
    )


@pytest.mark.parametrize("name", ["_ord_datetime", "_sell_orders_placed_before"])
def test_ar3_4_classifier_helpers_are_module_level_and_never_raise(oe, name):
    """🔴 AR3-4 (R3-1-3) — 분류 파서 둘은 **모듈 수준** 동기 `def` · `Await` 0 · 본문(docstring 제외)
    = `except Exception` 을 가진 `Try` 하나(never-raise — 못 읽는 행 하나가 매도 경로를 끊지 않는다)."""
    _, tree = oe
    top = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
           and n.name == name]
    assert len(top) == 1, f"모듈 수준 `{name}` {len(top)}개 (기대 1)"
    fn = top[0]
    assert isinstance(fn, ast.FunctionDef), f"`{name}` 는 동기 def"
    assert not _awaits(fn)
    body = fn.body[1:] if ast.get_docstring(fn) is not None else fn.body
    assert len(body) == 1 and isinstance(body[0], ast.Try) and _catches_exception(body[0]), (
        f"`{name}` 본문 {[type(x).__name__ for x in body]} — `try: … except Exception:` 하나여야 한다"
    )


def _loop_skip_test(loop: ast.For) -> str | None:
    """`for k, … in fills.items():` 의 맨 앞 `if <cond>: continue` 조건(공백 제거) — 없으면 None."""
    if not (isinstance(loop.target, ast.Tuple) and isinstance(loop.target.elts[0], ast.Name)):
        return None
    if ast.unparse(loop.iter).replace(" ", "") != "fills.items()":
        return None
    first = loop.body[0] if loop.body else None
    if isinstance(first, ast.If) and len(first.body) == 1 and isinstance(first.body[0], ast.Continue) \
            and not first.orelse:
        return ast.unparse(first.test).replace(" ", "").replace(loop.target.elts[0].id, "<k>", 1)
    return None


def test_ar3_5_recount_credit_caps_pre_ledger_orders(oe):
    """🔴 AR3-5 (R3-1-4 · R3-1-5) — `_handle_sell_qty_exceeded`(B4-4, cycle439 —
    전에는 `execute_sell` 안이었다):
    - 주문 조회 대입 대상 = `fills, _reason, _pre` · `self._sell_pending_dec(fills, _pre)` 정확히 1.
    - 재대조 블록: `_old_credit` 대입 1(우변이 `_sell_reflected_credit`·`_sell_blind_credit` 를 읽는다)이
      첫 `self._sell_reflected_credit[...] =` 저장보다 **앞**(덮어쓰기 전에 센다 — MK21).
    - `for k, … in fills.items():` 가 둘 — 맨 앞 `if k in _pre: continue`(원장 시작 뒤 주문 = 정확한
      크레딧) 뒤에 `_pre_cap` 대입(우변에 `pos.quantity - target_qty - _post_credit + _old_credit`),
      그 뒤에 `if k not in _pre: continue` 루프.
    - `min(…, _pre_cap)` 은 정확히 1 · 그 `if k not in _pre: continue` 루프 안에만.
    """
    _, tree = oe
    fn = _func(tree, "_handle_sell_qty_exceeded")
    par = _parents(fn)

    snaps = [
        n for n in ast.walk(fn)
        if isinstance(n, ast.Await) and isinstance(n.value, ast.Call)
        and isinstance(n.value.func, ast.Attribute) and n.value.func.attr == "_sell_orders_snapshot"
    ]
    assert len(snaps) == 1
    asg = par[snaps[0]]
    assert isinstance(asg, ast.Assign) and len(asg.targets) == 1 \
        and ast.unparse(asg.targets[0]).replace(" ", "") in ("fills,_reason,_pre", "(fills,_reason,_pre)"), (
            f"주문 조회 대입 `{ast.unparse(asg)[:80]}` — `fills, _reason, _pre = await …`"
        )
    pds = [c for c in _calls(fn, "_sell_pending_dec")]
    assert len(pds) == 1 and [ast.unparse(x) for x in pds[0].args] == ["fills", "_pre"] \
        and not pds[0].keywords, f"`_sell_pending_dec` 호출 {[ast.unparse(c) for c in pds]}"

    olds = [
        n for n in ast.walk(fn)
        if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "_old_credit"
                                             for t in n.targets)
    ]
    assert len(olds) == 1, f"`_old_credit = …` {len(olds)}개 (기대 1)"
    old_attrs = {x.attr for x in ast.walk(olds[0].value) if isinstance(x, ast.Attribute)}
    assert {"_sell_reflected_credit", "_sell_blind_credit"} <= old_attrs, (
        f"`_old_credit` 우변 `{ast.unparse(olds[0].value)}` — 남은 주문별·종목 크레딧 합이어야 한다"
    )
    stores = _subscript_stores(fn, "_sell_reflected_credit")
    assert stores and olds[0].lineno < min(n.lineno for n in stores), (
        f"`_old_credit`(L{olds[0].lineno}) 가 첫 크레딧 저장(L{min(n.lineno for n in stores)}) 뒤 — "
        "덮어쓴 뒤 세면 남은 크레딧이 0 이 된다(TK4b)"
    )

    caps = [
        n for n in ast.walk(fn)
        if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "_pre_cap"
                                             for t in n.targets)
        and any(isinstance(x, ast.Name) and x.id == "_old_credit" for x in ast.walk(n.value))
    ]
    assert len(caps) == 1, f"`_pre_cap = …(_old_credit …)` {len(caps)}개 (기대 1)"
    assert "pos.quantity-target_qty-_post_credit+_old_credit" in \
        ast.unparse(caps[0].value).replace(" ", ""), ast.unparse(caps[0].value)

    loops = [n for n in ast.walk(fn) if isinstance(n, ast.For)]
    post = [lp for lp in loops if _loop_skip_test(lp) == "<k>in_pre"]
    pre = [lp for lp in loops if _loop_skip_test(lp) == "<k>notin_pre"]
    assert len(post) == 1 and len(pre) == 1, (
        f"`if k in _pre: continue` 루프 {len(post)} · `if k not in _pre: continue` 루프 {len(pre)} "
        "(기대 각 1)"
    )
    assert post[0].end_lineno < caps[0].lineno < pre[0].lineno, (
        "순서가 「뒤 주문 크레딧 루프 → `_pre_cap` → 앞 주문 루프」 가 아니다"
    )
    mins = [c for c in _calls(fn, "min")
            if any(isinstance(x, ast.Name) and x.id == "_pre_cap" for x in c.args)]
    assert len(mins) == 1, f"`min(…, _pre_cap)` {len(mins)}개 (기대 1)"
    assert pre[0] in _ancestors(par, mins[0], fn), (
        "`min(…, _pre_cap)` 이 `if k not in _pre: continue` 루프 밖에 있다 — 상한은 원장 시작 전 주문에만"
    )


def test_ar3_6_hold_label_splits_on_whether_anything_rests(oe):
    """🔴 AR3-6 (R3-1-6) — F-3 If(`held_qty >= eff`) 본문의 보류 경로: `if held_qty > sellable:` 본문에
    `[sell_qty_partial_locked]` · orelse 에 `[sell_qty_unnoticed_fills]` · 그 If 바로 뒤
    `self._selling_locked_wait.add(ticker)` → `return`. `_handle_sell_qty_exceeded`(B4-4, cycle439 —
    전에는 `execute_sell` 안이었다) 안 `[sell_qty_partial_locked]`
    문자열은 그 If 본문에만(걸린 매도가 없는데 「외부 부분 매도주문 잠김」 을 쓰지 않는다 — MK8)."""
    _, tree = oe
    fn = _func(tree, "_handle_sell_qty_exceeded")

    def _marker_consts(node, prefix):
        return [n for n in ast.walk(node)
                if isinstance(n, ast.Constant) and isinstance(n.value, str) and n.value.startswith(prefix)]

    f3 = [n for n in ast.walk(fn)
          if isinstance(n, ast.If) and ast.unparse(n.test).replace(" ", "") == "held_qty>=eff"]
    assert len(f3) == 1
    splits = [(i, st) for i, st in enumerate(f3[0].body)
              if isinstance(st, ast.If) and ast.unparse(st.test).replace(" ", "") == "held_qty>sellable"]
    assert len(splits) == 1, (
        f"F-3 본문의 `if held_qty > sellable:` {len(splits)}개 (기대 1 — 걸림 여부로 문구를 가른다)"
    )
    i, sp = splits[0]
    body = ast.Module(body=sp.body, type_ignores=[])
    orelse = ast.Module(body=sp.orelse, type_ignores=[])
    assert _marker_consts(body, "[sell_qty_partial_locked]"), "걸린 쪽 본문에 `[sell_qty_partial_locked]` 가 없다"
    assert not _marker_consts(body, "[sell_qty_unnoticed_fills]")
    assert _marker_consts(orelse, "[sell_qty_unnoticed_fills]"), "안 걸린 쪽에 `[sell_qty_unnoticed_fills]` 가 없다"
    assert not _marker_consts(orelse, "[sell_qty_partial_locked]")
    tail = f3[0].body[i + 1:i + 3]
    assert len(tail) == 2 and _is_stmt_call(tail[0], "_selling_locked_wait", "add", "ticker") \
        and isinstance(tail[1], ast.Return), (
            f"문구 분기 뒤 {[ast.unparse(x)[:50] for x in tail]} — `self._selling_locked_wait.add(ticker)` "
            "→ `return`(동작은 부록 R2 그대로)"
        )
    everywhere = _marker_consts(fn, "[sell_qty_partial_locked]")
    inside = set(map(id, _marker_consts(body, "[sell_qty_partial_locked]")))
    assert all(id(c) in inside for c in everywhere), (
        f"`[sell_qty_partial_locked]` 가 `held_qty > sellable` 본문 밖 L{[c.lineno for c in everywhere]}"
    )


def _path_conditions(par: dict, node: ast.AST, stop: ast.AST) -> list[tuple[ast.AST, bool]]:
    """`node` 에 닿으려면 참/거짓이어야 하는 If 테스트들((테스트, 본문쪽인가)) — `stop` 까지."""
    out = []
    child, cur = node, par[node]
    while cur is not stop:
        if isinstance(cur, ast.If):
            if child in cur.body:
                out.append((cur.test, True))
            elif child in cur.orelse:
                out.append((cur.test, False))
        child, cur = cur, par[cur]
    return out


class _LogRec:
    """`logger` 대역 — (레벨, 서식 적용된 문구)를 모은다."""

    def __init__(self) -> None:
        self.records: list[tuple[str, str]] = []

    def _add(self, level, fmt, *args, **kw):
        self.records.append((level, fmt % args if args else fmt))

    def debug(self, fmt, *a, **k):
        self._add("debug", fmt, *a)

    def info(self, fmt, *a, **k):
        self._add("info", fmt, *a)

    def warning(self, fmt, *a, **k):
        self._add("warning", fmt, *a)

    def error(self, fmt, *a, **k):
        self._add("error", fmt, *a)

    def exception(self, fmt, *a, **k):
        self._add("error", fmt, *a)


def test_ar3_7_manual_route_rolls_back_only_on_not_placed_rejection():
    """🔴 AR3-7 (R3-2-4 · K2 라우트 · 부록 R4 D2 개정) — `routes/trading.py::manual_sell` 의
    `except Exception as e:` 핸들러를 **실행해** 잰다(판정 함수는 대역):
    - `engine._selling.discard(req.ticker)` 정확히 1 · `_selling_since.pop(req.ticker, None)` 은 그 문장 목록.
    - 되돌림(`_selling`·`_selling_since` 비움) ⇔ **`_added ∧ ¬_sent ∧ _sell_not_placed_reason(e) is not None`**.
    - `[manual_sell_selling_kept]` WARNING(모듈에 정확히 1) ⇔ **`_added ∧ ¬_sent ∧ 판정 None`**.
    - 실패 줄 `수동 매도 실패: …` 1행 · 끝 칸 `selling_released=<되돌렸으면 이유, 아니면 ->`.
    - 판정은 `src.engine.order_engine._sell_not_placed_reason` 한 곳(함수 안 import) — 핸들러가 그것을
      정확히 1번 부르고, `manual_sell` 은 분류기 셋을 직접 부르지 않는다(키워드 판정을 두 곳에 두지 않는다).
    """
    rsrc = _src(_ROUTE)
    rtree = ast.parse(rsrc)
    fn = _func(rtree, "manual_sell")
    assert fn is not None
    par = _parents(fn)
    places = _await_calls(fn, "place_order")
    assert len(places) == 1
    tr = next(a for a in _ancestors(par, places[0], fn) if isinstance(a, ast.Try))
    hs = [h for h in tr.handlers if isinstance(h.type, ast.Name) and h.type.id == "Exception" and h.name]
    assert len(hs) == 1, "발사 Try 에 `except Exception as <n>:` 가 없다"
    h = hs[0]

    discards = [
        c for c in ast.walk(h)
        if isinstance(c, ast.Call) and isinstance(c.func, ast.Attribute) and c.func.attr == "discard"
        and isinstance(c.func.value, ast.Attribute) and c.func.value.attr == "_selling"
    ]
    assert len(discards) == 1, f"핸들러 안 `_selling.discard` {len(discards)}개 (기대 1)"
    d_stmt, d_list = _stmt_in_list(par, discards[0])
    assert any(
        ast.unparse(s).replace(" ", "").endswith("._selling_since.pop(req.ticker,None)") for s in d_list
    ), "`_selling_since.pop(req.ticker, None)` 이 discard 와 같은 자리에 없다"
    assert sum(
        1 for n in ast.walk(rtree)
        if isinstance(n, ast.Constant) and isinstance(n.value, str)
        and n.value.startswith("[manual_sell_selling_kept]")
    ) == 1

    assert len(_calls(h, "_sell_not_placed_reason")) == 1, (
        "핸들러가 `_sell_not_placed_reason(e)` 를 정확히 1번 부르지 않는다(부록 R4 D2 — 판정은 한 곳)"
    )
    for _nm in _NOT_PLACED_CLASSIFIERS:
        assert not _calls(fn, _nm), f"`manual_sell` 이 `{_nm}` 를 직접 부른다(부록 R4 D2 — 판정은 한 곳)"
    assert any(
        isinstance(n, ast.ImportFrom) and n.module == "src.engine.order_engine"
        and any(a.name == "_sell_not_placed_reason" and a.asname is None for a in n.names)
        for n in ast.walk(fn)
    ), "`manual_sell` 이 `src.engine.order_engine` 의 `_sell_not_placed_reason` 를 가져오지 않는다"

    body_src = ast.unparse(ast.Module(body=h.body, type_ignores=[]))
    code = compile("def _h():\n" + textwrap.indent(body_src, "    ") + "\n",
                   "<manual_sell_handler>", "exec")

    class _E(Exception):
        def __init__(self, reason):
            super().__init__(f"err-{reason}")
            self.reason = reason

    for added in (True, False):
        for sent in (True, False):
            for reason in (None, "qty_exceeded", "market_closed", "market_order_disallowed"):
                log = _LogRec()
                eng = SimpleNamespace(_selling={"T"}, _selling_since={"T": 1})
                g = {
                    "_added": added, "_sent": sent, h.name: _E(reason), "engine": eng,
                    "req": SimpleNamespace(ticker="T"), "logger": log,
                    "ApiResponse": lambda **k: SimpleNamespace(**k),
                    "_sell_not_placed_reason": lambda e: getattr(e, "reason", None),
                }
                exec(code, g)
                g["_h"]()
                want_rb = added and not sent and reason is not None
                want_kept = added and not sent and reason is None
                tag = f"added={added} sent={sent} reason={reason!r}"
                assert ("T" not in eng._selling) is want_rb, f"되돌림 {tag}: 기대 {want_rb}"
                assert ("T" not in eng._selling_since) is want_rb, f"`_selling_since` {tag}: 기대 {want_rb}"
                kept = [m for lv, m in log.records
                        if lv == "warning" and m.startswith("[manual_sell_selling_kept]")]
                assert len(kept) == (1 if want_kept else 0), f"`[manual_sell_selling_kept]` {tag}: {kept}"
                fails = [m for lv, m in log.records if lv == "error" and m.startswith("수동 매도 실패:")]
                want_tag = f"selling_released={reason if want_rb else '-'}"
                assert len(fails) == 1 and fails[0].endswith(want_tag), (
                    f"실패 줄 {tag}: {fails} (기대 끝 칸 `{want_tag}`)"
                )



# ════════════════════════════════════════════════════════════════════════════
# 부록 R4 — AR4-1 · AR4-2
# ════════════════════════════════════════════════════════════════════════════
def test_ar4_1_not_placed_reason_composes_existing_classifiers_only(oe):
    """🔴 AR4-1 (부록 R4 D2) — `_sell_not_placed_reason` = 모듈 수준 동기 `def` · Await 0 · 본문(docstring
    뒤) = 최상위 `Try(except Exception)` 하나(never-raise). 부르는 것은 `isinstance(<x>, KisApiError)` 와
    `src.api.balance` 분류기 셋뿐 · 속성 읽기 0(`msg1`·`msg_cd` 를 직접 맞추지 않는다 — 키워드 재구현 금지) ·
    docstring 밖 문자열 상수 = 이유 셋(`qty_exceeded`·`market_closed`·`market_order_disallowed`)뿐.
    분류기 셋은 모듈이 `src.api.balance` 에서 가져온 것이다."""
    _, tree = oe
    tops = [n for n in tree.body
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == "_sell_not_placed_reason"]
    assert len(tops) == 1, "모듈 수준 `_sell_not_placed_reason` 가 없다(부록 R4 D2)"
    fn = tops[0]
    assert isinstance(fn, ast.FunctionDef) and not _awaits(fn)
    body = fn.body
    doc_node = None
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
            and isinstance(body[0].value.value, str):
        doc_node, body = body[0].value, body[1:]
    assert len(body) == 1 and isinstance(body[0], ast.Try) and _catches_exception(body[0]), (
        "본문이 `try: … except Exception:` 하나가 아니다(never-raise)"
    )
    fbody = ast.Module(body=fn.body, type_ignores=[])       # 서명 주석(`-> "str | None"`) 제외
    called = [_call_name(c) for c in ast.walk(fbody) if isinstance(c, ast.Call)]
    assert set(called) == {"isinstance", *_NOT_PLACED_CLASSIFIERS}, f"부르는 것 {sorted(set(called))}"
    inst = [c for c in ast.walk(fbody) if isinstance(c, ast.Call) and _call_name(c) == "isinstance"]
    assert inst and all(
        len(c.args) == 2 and isinstance(c.args[1], ast.Name) and c.args[1].id == "KisApiError" for c in inst
    ), "`isinstance(<x>, KisApiError)` 가 아니다"
    attrs = sorted({n.attr for n in ast.walk(fbody) if isinstance(n, ast.Attribute)})
    assert not attrs, f"속성을 직접 읽는다 {attrs} — 분류는 `src.api.balance` 판정 함수에 맡긴다"
    consts = {
        n.value for n in ast.walk(fbody)
        if isinstance(n, ast.Constant) and isinstance(n.value, str) and n is not doc_node
    }
    assert consts == {"qty_exceeded", "market_closed", "market_order_disallowed"}, sorted(consts)
    imported = {
        a.name for n in tree.body if isinstance(n, ast.ImportFrom) and n.module == "src.api.balance"
        for a in n.names
    }
    assert set(_NOT_PLACED_CLASSIFIERS) <= imported, f"`src.api.balance` 에서 가져온 것 {sorted(imported)}"


def test_ar4_2_query_failure_hold_does_not_use_the_unnoticed_fills_label(oe):
    """🔴 AR4-2 (부록 R4 D4) — `_handle_sell_qty_exceeded`(B4-4, cycle439 — 전에는
    `execute_sell` 안이었다) F-3 If(`held_qty >= eff`) 안에서:
    `[sell_qty_hold_orders_unavailable]`(1) 에 닿는 조건 = **걸린 매도 없음 ∧ `fills is None`**,
    `[sell_qty_unnoticed_fills]`(1) 에 닿는 조건 = **걸린 매도 없음 ∧ `fills is not None`**(조건을 실행해
    잰다 — 이름 `fire`·`held_qty`·`sellable`·`fills`·`eff`·`pending`). 조회 실패 보류 문구는 `orders=%s`
    칸에 조회 결과 이유(`_reason`)를 싣는다."""
    _, tree = oe
    fn = _func(tree, "_handle_sell_qty_exceeded")
    par = _parents(fn)
    f3 = [n for n in ast.walk(fn)
          if isinstance(n, ast.If) and ast.unparse(n.test).replace(" ", "") == "held_qty>=eff"]
    assert len(f3) == 1

    def consts(prefix):
        return [n for n in ast.walk(fn)
                if isinstance(n, ast.Constant) and isinstance(n.value, str) and n.value.startswith(prefix)]

    hou = consts("[sell_qty_hold_orders_unavailable]")
    unf = consts("[sell_qty_unnoticed_fills]")
    assert len(hou) == 1, f"`[sell_qty_hold_orders_unavailable]` {len(hou)}곳 (기대 1)"
    assert len(unf) == 1, f"`[sell_qty_unnoticed_fills]` {len(unf)}곳 (기대 1)"
    for node in hou + unf:
        assert f3[0] in _ancestors(par, node, fn), "보류 문구가 F-3 If 밖에 있다"

    def reach(node, env):
        return all(bool(_eval_test(t, env)) is want for t, want in _path_conditions(par, node, f3[0]))

    for held, sellable in ((5, 5), (6, 5)):
        for fills in (None, {"1": 1}):
            env = {"fire": 0, "eff": 5, "held_qty": held, "sellable": sellable, "fills": fills,
                   "pending": None if fills is None else 0}
            nothing_rests = held == sellable
            assert reach(hou[0], env) is (nothing_rests and fills is None), (
                f"조회 실패 보류 문구 도달 held={held} sellable={sellable} fills={fills}"
            )
            assert reach(unf[0], env) is (nothing_rests and fills is not None), (
                f"`[sell_qty_unnoticed_fills]` 도달 held={held} sellable={sellable} fills={fills} — "
                "조회가 실패했으면 「거래소가 확인한 미통보 체결」을 주장하지 않는다(부록 R4 D4)"
            )
    call = par[hou[0]]
    assert isinstance(call, ast.Call) and "orders=%s" in hou[0].value and any(
        isinstance(a, ast.Name) and a.id == "_reason" for a in call.args
    ), "조회 실패 보류 문구에 `orders=%s` ← `_reason` 칸이 없다"
