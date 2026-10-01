"""cycle392 — 매도 장부 주문 누적 구조 가드 (A2~A7).

명세 = 세션 scratchpad `c392/spec.md` §6.2 · 행위 짝 = `tests/unit/engine/test_cycle392_sell_book_cumulative.py`

행위 테스트는 **무엇이 기록되는가**를 잰다. 이 파일은 표본 밖에서 놓치는 **순서·원자성·범위**를 잰다 —
「누적이 첫 `await` 뒤로 밀렸다」 「장부 쓰기가 `await` 뒤에 누적기를 다시 읽는다」 는 특정 경합
순서에서만 드러나서 표본을 늘려도 같은 누락에 노출된다(cycle328 `test_g328_3b` 선례).

- A1 = 기존 `test_cycle385_ast_b7.py::test_ar3_realized_pnl_still_counts_every_filled_share` 를
  **수정 없이** 그대로 쓴다(`profit_loss` 대입 1개 · 곱셈 피연산자 `quantity`). 여기서 복제하지 않는다.
- A5 는 base `9df058d` 의 `_handle_buy_fill` 소스 세그먼트 sha 핀이다 — 처음부터 초록이 정상이고,
  매수 쪽을 건드리면(공백 한 줄이라도) 붉어진다. `ast.dump` sha 금지(3.12↔3.13 출력 차이).

🔴 소스는 `Path.read_text` + AST 로만 읽는다. 주석·docstring 은 세지 않는다.
🔴 A5·A6 만 git 을 쓴다(변경 범위·커밋 여부는 git 만 안다) — **둘 다 cycle392 가 커밋되면 스스로
   skip 한다**(HEAD 의 `order_engine.py` 에 `_sell_fill_book` 이 있으면 이 사이클은 끝난 것이다).
   bare `git diff HEAD` 영구 가드가 커밋 직후 공허해지고 다음 편집에서 붉어지는 사고(cycle240
   A11b·cycle252 G-252-5b)를 피하는 장치다. A5 를 A6 과 같은 정책으로 묶은 이유(cycle392 검토
   지적 #4) = 커밋 뒤에도 영구 핀으로 남으면 §12-2(매수 다건 통보) 같은 정당한 매수 쪽 후속
   수정마다 이 핀을 다시 잡아야 하고, 그때 실패 문구 「cycle392 는 매수 쪽을 건드리지 않는다」가
   오해를 부른다. TODO(cycle392 커밋 후): A5·A6 을 삭제해도 된다.
"""
from __future__ import annotations

import ast
import hashlib
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parents[3]
_OE_REL = "src/engine/order_engine.py"
_OE = _ROOT / _OE_REL

#: base `9df058d` 의 `_handle_buy_fill` 세그먼트 sha256(`ast.get_source_segment`) — 매수 쪽 바이트 동일(I8).
_BUY_FILL_SEGMENT_SHA = "74451232a3190f471799efd228455135f74753cc6d53e70b9840a0371257319b"

#: 장부 쓰기 네 곳 — `update_trade_status`(COMPLETED·PARTIAL) · `_update_trade_status_by_order_no`(강제) ·
#: `TradeRecord(...)`(보정 INSERT 의 행).
_WRITE_FUNCS = ("update_trade_status", "_update_trade_status_by_order_no", "TradeRecord")

_BOOK = "_sell_fill_book"


def _git(*args: str) -> str:
    res = subprocess.run(["git", *args], cwd=_ROOT, capture_output=True, text=True)
    if res.returncode != 0:
        raise AssertionError(
            f"git {' '.join(args)} 실패 (rc={res.returncode}) — fail-closed. "
            f"stderr: {(res.stderr or '').strip()}"
        )
    return res.stdout


def _cycle_committed() -> bool:
    """HEAD 의 `order_engine.py` 에 이미 `_sell_fill_book` 이 있으면 cycle392 는 커밋된 것이다.

    A5·A6 가 공유하는 단일 판정(§검토 지적 #4·#5) — 둘 다 이 함수가 True 를 돌려주면 skip 한다.
    """
    return _BOOK in _git("show", f"HEAD:{_OE_REL}")


def _load() -> tuple[str, ast.Module]:
    src = _OE.read_text(encoding="utf-8")
    return src, ast.parse(src)


def _class(tree: ast.AST, name: str) -> ast.ClassDef:
    hits = [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef) and n.name == name]
    assert len(hits) == 1, f"class `{name}` {len(hits)}개"
    return hits[0]


def _method(cls: ast.ClassDef, name: str):
    hits = [
        n for n in cls.body
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name
    ]
    assert len(hits) == 1, f"`{cls.name}.{name}` {len(hits)}개"
    return hits[0]


def _sell_fill(tree):
    return _method(_class(tree, "OrderEngine"), "_handle_sell_fill")


def _write_calls(fn: ast.AST) -> list[ast.Call]:
    return sorted(
        (
            n for n in ast.walk(fn)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
            and n.func.id in _WRITE_FUNCS
        ),
        key=lambda c: c.lineno,
    )


def _kw(call: ast.Call, name: str):
    for k in call.keywords:
        if k.arg == name:
            return k.value
    return None


def _is_book(node: ast.AST) -> bool:
    return isinstance(node, ast.Attribute) and node.attr == _BOOK


def _sync_window(fn: ast.AST) -> tuple[int, int]:
    """(`daily_realized_pnl +=` 줄, 그 뒤 첫 `await` 줄)."""
    augs = [
        n for n in ast.walk(fn)
        if isinstance(n, ast.AugAssign) and isinstance(n.target, ast.Attribute)
        and n.target.attr == "daily_realized_pnl"
    ]
    assert len(augs) == 1, f"`daily_realized_pnl +=` {len(augs)}개 (기대 1 — I1)"
    aug = augs[0].lineno
    after = sorted(n.lineno for n in ast.walk(fn) if isinstance(n, ast.Await) and n.lineno > aug)
    assert after, "`daily_realized_pnl +=` 뒤에 await 가 없다(구조 전제 붕괴)"
    return aug, after[0]


def _assigned_names(target: ast.AST) -> list[str]:
    if isinstance(target, ast.Name):
        return [target.id]
    if isinstance(target, (ast.Tuple, ast.List)):
        out: list[str] = []
        for e in target.elts:
            out += _assigned_names(e)
        return out
    if isinstance(target, ast.Starred):
        return _assigned_names(target.value)
    return []


def _assign_lines(fn: ast.AST, name: str) -> list[int]:
    lines: list[int] = []
    for n in ast.walk(fn):
        if isinstance(n, ast.Assign):
            if any(name in _assigned_names(t) for t in n.targets):
                lines.append(n.lineno)
        elif isinstance(n, (ast.AnnAssign, ast.AugAssign)):
            if name in _assigned_names(n.target):
                lines.append(n.lineno)
        elif isinstance(n, ast.NamedExpr) and n.target.id == name:
            lines.append(n.lineno)
        elif isinstance(n, (ast.For, ast.AsyncFor, ast.comprehension)):
            if name in _assigned_names(n.target):
                lines.append(getattr(n, "lineno", 0) or 0)
    return sorted(lines)


def _book_value_names(fn: ast.AST) -> tuple[str, str]:
    """장부 쓰기 네 곳의 `price=`·`profit_loss=` 값 이름(A2 가 모양을 보증한 뒤 호출)."""
    calls = _write_calls(fn)
    prices = {_kw(c, "price").id for c in calls}
    pnls = {_kw(c, "profit_loss").id for c in calls}
    assert len(prices) == 1 and len(pnls) == 1, (prices, pnls)
    return prices.pop(), pnls.pop()


# ---------------------------------------------------------------------------
# A2 — 장부 쓰기 네 곳이 통보 증분(`profit_loss`)·통보 체결가(`price`)를 쓰지 않는다
# ---------------------------------------------------------------------------
def test_a2_book_writes_use_order_cumulative_locals_not_notice_increment():
    """네 곳의 `price=`·`profit_loss=` 값은 이름(동기 영역에서 잡은 로컬)이고 `price`·`profit_loss` 가 아니다.

    네 곳이 같은 이름을 쓴다 — 한 곳만 증분으로 남으면(M7 보정 INSERT) 그 경로에서만 덮어쓰기가 산다.
    """
    _, tree = _load()
    fn = _sell_fill(tree)
    calls = _write_calls(fn)
    names = [c.func.id for c in calls]
    assert sorted(names) == sorted(
        ["update_trade_status", "update_trade_status", "_update_trade_status_by_order_no", "TradeRecord"]
    ), f"`_handle_sell_fill` 장부 쓰기 {names} (기대 4곳: COMPLETED·PARTIAL UPDATE · 강제 UPDATE · 보정 INSERT 행)"
    bad = []
    for c in calls:
        for kw in ("price", "profit_loss"):
            v = _kw(c, kw)
            if v is None:
                bad.append(f"L{c.lineno} {c.func.id}: `{kw}=` 없음")
            elif not isinstance(v, ast.Name):
                bad.append(f"L{c.lineno} {c.func.id}: `{kw}={ast.unparse(v)}` — 동기 영역 로컬 이름이어야 한다")
            elif v.id in ("price", "profit_loss"):
                bad.append(f"L{c.lineno} {c.func.id}: `{kw}={v.id}` — 통보 1건 값(덮어쓰기 결함)")
    assert bad == [], "\n".join(bad)
    _book_value_names(fn)


def test_a2b_no_book_read_after_first_await_except_pop():
    """I5 — 첫 `await` 뒤에는 누적기를 읽지 않는다(종료 분기 `.pop(order_no, …)` 만 예외).

    `await` 뒤에 다시 읽으면 같은 주문의 다음 통보가 끼어든 값(또는 종료 분기가 pop 한 빈 값)이 섞인다.
    """
    _, tree = _load()
    fn = _sell_fill(tree)
    _, first_await = _sync_window(fn)
    parents = {}
    for p in ast.walk(fn):
        for ch in ast.iter_child_nodes(p):
            parents[ch] = p
    bad = []
    for n in ast.walk(fn):
        if _is_book(n) and n.lineno > first_await:
            p = parents.get(n)
            ok = (
                isinstance(p, ast.Attribute) and p.attr == "pop"
                and isinstance(parents.get(p), ast.Call) and parents[p].func is p
            )
            if not ok:
                bad.append(f"L{n.lineno}: {ast.unparse(p) if p is not None else _BOOK}")
    assert bad == [], f"첫 await(L{first_await}) 뒤 누적기 읽기: {bad}"


# ---------------------------------------------------------------------------
# A3 — 누적은 동기 영역에서(I4)
# ---------------------------------------------------------------------------
def test_a3_accumulate_and_book_locals_in_the_sync_window():
    """`daily_realized_pnl +=` < 누적기 갱신 · 장부 로컬 확정 < 그 뒤 첫 `await`.

    - 누적기 갱신 = `self._sell_fill_book[order_no] = …` — 모듈 전체에 **정확히 1**, `_handle_sell_fill` 안,
      키는 raw `order_no`(`_odno_key` 정규화 금지 — `_filled_qty` 와 같은 키 체계)
    - 장부 로컬 = A2 의 `price=`·`profit_loss=` 이름 — 함수 안의 **모든** 대입이 창 안
    """
    _, tree = _load()
    fn = _sell_fill(tree)
    aug, first_await = _sync_window(fn)

    stores = [
        n for n in ast.walk(tree)
        if isinstance(n, (ast.Assign, ast.AugAssign, ast.AnnAssign))
        and any(
            isinstance(t, ast.Subscript) and _is_book(t.value)
            for t in (n.targets if isinstance(n, ast.Assign) else [n.target])
        )
    ]
    assert len(stores) == 1, f"`{_BOOK}[...] =` {len(stores)}곳 (기대 1)"
    st = stores[0]
    assert fn.lineno <= st.lineno <= fn.end_lineno, "누적기 갱신이 `_handle_sell_fill` 밖이다"
    tgt = (st.targets[0] if isinstance(st, ast.Assign) else st.target)
    assert isinstance(tgt.slice, ast.Name) and tgt.slice.id == "order_no", (
        f"누적기 키 = `{ast.unparse(tgt.slice)}` (기대 raw `order_no`)"
    )
    assert aug < st.lineno < first_await, (
        f"누적기 갱신 L{st.lineno} 이 창(L{aug}, L{first_await}) 밖"
    )

    price_name, pnl_name = _book_value_names(fn)
    for name in (price_name, pnl_name):
        lines = _assign_lines(fn, name)
        assert lines, f"`{name}` 대입이 없다"
        outside = [ln for ln in lines if not (aug < ln < first_await)]
        assert outside == [], (
            f"`{name}` 대입 L{outside} 이 동기 창(L{aug}, L{first_await}) 밖 — await 뒤 재계산 금지(I4·I5)"
        )


# ---------------------------------------------------------------------------
# A4 — 수명: 주문 종료 pop · 일일 clear · 생성
# ---------------------------------------------------------------------------
def test_a4_book_lifecycle_init_pop_clear():
    _, tree = _load()
    cls = _class(tree, "OrderEngine")

    init = _method(cls, "__init__")
    inits = [
        n for n in ast.walk(init)
        if isinstance(n, (ast.Assign, ast.AnnAssign))
        and any(_is_book(t) for t in (n.targets if isinstance(n, ast.Assign) else [n.target]))
    ]
    assert len(inits) == 1, f"`__init__` 의 `self.{_BOOK} = …` {len(inits)}개"
    v = inits[0].value
    assert isinstance(v, ast.Dict) and not v.keys, f"초기값 `{ast.unparse(v)}` (기대 `{{}}`)"

    fn = _sell_fill(tree)
    ends = [
        n for n in ast.walk(fn)
        if isinstance(n, ast.If) and ast.unparse(n.test).replace(" ", "") == "total_filled>=ordered_qty"
    ]
    assert len(ends) == 1, f"주문 종료 분기 `if total_filled >= ordered_qty:` {len(ends)}개"
    body = ends[0].body

    def _pop_stmt(owner: str):
        for i, s in enumerate(body):
            if (
                isinstance(s, ast.Expr) and isinstance(s.value, ast.Call)
                and isinstance(s.value.func, ast.Attribute) and s.value.func.attr == "pop"
                and isinstance(s.value.func.value, ast.Attribute) and s.value.func.value.attr == owner
                and s.value.args and isinstance(s.value.args[0], ast.Name)
                and s.value.args[0].id == "order_no"
            ):
                return i, s
        return None, None

    fi, _ = _pop_stmt("_filled_qty")
    bi, bs = _pop_stmt(_BOOK)
    assert fi is not None, "종료 분기 `self._filled_qty.pop(order_no, …)` 가 없다(구조 전제)"
    assert bi is not None, f"종료 분기 직속 문장에 `self.{_BOOK}.pop(order_no, …)` 가 없다"
    writes = [c.lineno for c in _write_calls(ast.Module(body=body, type_ignores=[]))]
    assert writes and bs.lineno > max(writes), (
        f"pop L{bs.lineno} 이 장부 쓰기 L{writes} 보다 앞이다(§4.4 — `_filled_qty` pop 과 한 묶음)"
    )

    reset = _method(cls, "reset_daily_state")
    clears = [
        n for n in ast.walk(reset)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "clear"
        and _is_book(n.func.value)
    ]
    assert len(clears) == 1, f"`reset_daily_state` 의 `self.{_BOOK}.clear()` {len(clears)}개"


# ---------------------------------------------------------------------------
# A5 — 매수 쪽 바이트 동일(I8) (사이클 한정 · 커밋되면 skip — A6 과 같은 정책, 검토 지적 #4)
# ---------------------------------------------------------------------------
def test_a5_handle_buy_fill_segment_is_byte_identical_to_base():
    if _cycle_committed():
        pytest.skip(
            "cycle392 가 커밋됨 — 매수 세그먼트 바이트 동일성은 커밋 전 범위 한정 가드였다"
            "(TODO: 이 테스트 삭제, §12-2 같은 정당한 매수 쪽 후속 수정이 이 핀에 막히지 않게)"
        )
    src, tree = _load()
    fn = _method(_class(tree, "OrderEngine"), "_handle_buy_fill")
    seg = ast.get_source_segment(src, fn)
    got = hashlib.sha256(seg.encode("utf-8")).hexdigest()
    assert got == _BUY_FILL_SEGMENT_SHA, (
        f"`_handle_buy_fill` 세그먼트 sha {got} ≠ base — cycle392 는 매수 쪽을 건드리지 않는다(§2.2)"
    )


# ---------------------------------------------------------------------------
# A6 — 범위: 보호 대상(trade_history.py·scheduler.py·migrations) 무변경 (사이클 한정 · 커밋되면 skip)
# ---------------------------------------------------------------------------
#: cycle392 가 손대면 안 되는 파일 — §2.2·§7 (order_engine.py 자신은 당연히 제외)
_FORBIDDEN_PATHS = (
    "src/db/trade_history.py",
    "src/engine/scheduler.py",
)


def test_a6_production_change_is_order_engine_only_while_cycle_open():
    """이 사이클은 `order_engine.py` 안에서 끝난다 — `trade_history.py`·`scheduler.py`·
    `supabase/migrations/` 는 무변경(§2.2·§7). HEAD 에 이미 `_sell_fill_book` 이 있으면 사이클이
    커밋된 것이라 skip.

    **검토 지적 #5 시정** — 예전 판정("`src/` 변경 집합 == `{order_engine.py}` 단독")은 이 작업
    트리에 c393(`stale_watcher_core.py`)·c394(`config.py` 등) 처럼 **무관한 다른 사이클의 변경이
    섞이면 거짓 경보**로 붉어졌다. 지금은 "보호 대상에 손대지 않았나"만 보므로 다른 사이클이 같은
    트리에 있어도 영향이 없다 — 진짜로 지켜야 할 것(§2.2 가 금지한 trade_history.py·scheduler.py·
    스키마)만 본다.
    """
    if _cycle_committed():
        pytest.skip("cycle392 가 커밋됨 — 사이클 한정 범위 가드 해제(TODO: 이 테스트 삭제)")
    tracked = _git("diff", "HEAD", "--name-only").split()
    untracked = _git("ls-files", "--others", "--exclude-standard").split()
    changed = set(tracked) | set(untracked)
    hits = sorted(
        p for p in changed
        if p in _FORBIDDEN_PATHS or p.startswith("supabase/migrations/")
    )
    assert hits == [], (
        f"cycle392 범위 밖 변경 {hits} (trade_history.py·scheduler.py·supabase/migrations 무접촉)"
    )
    assert _OE_REL in changed, f"{_OE_REL} 변경이 없다 — 이 사이클이 아직 시작되지 않았다"


# ---------------------------------------------------------------------------
# A7 — 동기 창 안에서 부르는 헬퍼는 순수(await·DB·HTTP 0)
# ---------------------------------------------------------------------------
_IMPURE_MARKERS = ("src.db", "httpx", "aiohttp", "asyncpg")


def test_a7_helpers_called_in_the_sync_window_are_pure():
    """창(`daily_realized_pnl +=` ~ 첫 `await`) 안에서 부르는 이 모듈의 함수·`self.` 메서드는
    동기 정의이고 본문에 `await`·`src.db`/`httpx` import·`pg.` 접근이 없다(누적 헬퍼 순수성, §4.2)."""
    _, tree = _load()
    cls = _class(tree, "OrderEngine")
    fn = _sell_fill(tree)
    aug, first_await = _sync_window(fn)

    module_defs = {
        n.name: n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    methods = {
        n.name: n for n in cls.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    targets: dict[str, ast.AST] = {}
    for n in ast.walk(fn):
        if not isinstance(n, ast.Call) or not (aug <= n.lineno < first_await):
            continue
        f = n.func
        if isinstance(f, ast.Name) and f.id in module_defs:
            targets[f.id] = module_defs[f.id]
        elif (
            isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name)
            and f.value.id == "self" and f.attr in methods
        ):
            targets[f"self.{f.attr}"] = methods[f.attr]

    bad = []
    for label, d in sorted(targets.items()):
        if isinstance(d, ast.AsyncFunctionDef):
            bad.append(f"{label}: async def")
            continue
        for x in ast.walk(d):
            if isinstance(x, ast.Await):
                bad.append(f"{label}: await L{x.lineno}")
            elif isinstance(x, ast.ImportFrom) and (x.module or "").startswith(_IMPURE_MARKERS):
                bad.append(f"{label}: from {x.module} import L{x.lineno}")
            elif isinstance(x, ast.Import) and any(a.name.startswith(_IMPURE_MARKERS) for a in x.names):
                bad.append(f"{label}: import L{x.lineno}")
            elif isinstance(x, ast.Attribute) and isinstance(x.value, ast.Name) and x.value.id == "pg":
                bad.append(f"{label}: pg.{x.attr} L{x.lineno}")
    assert bad == [], f"동기 창 헬퍼 비순수: {bad}"
