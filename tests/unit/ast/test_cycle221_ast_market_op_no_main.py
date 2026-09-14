"""cycle221 (2026-08-20) AST/SAFETY 영구 가드 — VI 채널(H0UNMKO0) 메인 퇴출 봉인.

08-19 OPSP0008 117건(그중 시세 H0UNCNT0 7건 = 매수 직후 보유 4종목 tick blind)의
근본은 **관찰 채널(VI)이 생명선 채널(tick)과 같은 메인 41 슬롯을 놓고 경쟁**한 것이다.
`bypass_limit=True` 는 로컬 가드만 우회할 뿐 KIS 서버 한도 41 은 못 넘고, 초과분은
OPSP0008 로 되돌아온다.

이 가드는 시정이 **정적으로** 되돌려지지 않도록 4가지를 봉인한다.

1. VI 훅이 메인 세션 `kis_ws.subscribe` 를 호출하지 않는다.
2. VI 훅에 `bypass_limit=True` 리터럴이 없다.
3. VI 훅이 `kis_ws_pool.subscribe/unsubscribe` 를 호출하지 않는다
   (`_ticker_to_session` 은 `tr_key` 단일 키라 VI 가 경유하면 TICK 라우팅이 오염된다 — F-P).
4. 8영역(`realtime/websocket.py`, `realtime/websocket_pool.py`, `engine/scanner.py`)에
   VI 구독 호출이 새로 생기지 않는다 (이번 사이클 diff 0 절대 조건).
5. **(정정 F1)** 보조 세션 예약 슬롯 상수 `_MARKET_OP_QUOTE_RESERVE` 가 **부재**한다.
   예약선(41-8=33)은 후보 VI 70건이 tick 을 밀어낼까 봐 둔 것인데, 후보 VI 배치 자체가
   삭제되면서(F2) 존재 이유가 사라졌다. 남겨두면 08-19 실측 조건(보조 6세션 ≈40.8/41)
   에서 **보유 종목 VI 가 전량 skip** 되어 변경 전보다 퇴행하고, 뮤테이션 검증에서 8→0
   으로 바꿔도 아무 테스트도 실패하지 않았다(M3 생존) = 값이 가드되지 않았다.

승계: 2026-08-07 소켓 OPEN 가드 + `ConnectionClosedError` 핸들러 / cycle214
`_EXECUTION_NOTICE_TR_IDS` 불변.

🔴 **cycle292 (2026-09-14) 재조준** — VI 훅 본체가 `scheduler.py` 에서
`src/engine/market_op_subscribe.py::subscribe_market_operation_tickers` 로 **이동**했다
(라인 상한 3,900 예산 확보, 행위 변경 0 · 본체 라인 단위 동일). `scheduler` 에는 5줄
위임 wrapper 만 남는다. 위 다섯 봉인은 **본체가 있는 곳**을 검사해야 의미가 있으므로
`_vi_hook()` 의 소스를 leaf 로 옮겼다. 그리고 봉인 1·2·3 은 전부 "…가 0건" 이라는
**부정 단언**이라 검사 대상이 사라져도 조용히 초록이 된다(wrapper 노드를 재면 실제로
그렇게 된다) — 그래서 이 사이클에서 **각 테스트에 양성 대조군(anti-vacuity)을 추가**했다.
현행 본체가 이미 만족하므로 느슨해지는 게 아니라 **조이는** 변경이다. wrapper 쪽 봉인은
`tests/unit/ast/test_cycle292_ast_market_op_leaf.py::G-292-3`(위임 실재 + 본체 재인라인
금지)이 맡는다 — wrapper 에 부정 단언을 걸면 그 자체가 공허해진다.

🔴 **cycle292 적대 검증 후속 — 이름 기반 봉인의 별칭 우회를 닫았다.** 봉인 1 은 호출 owner
이름(`kis_ws`)으로 판정하므로 배치 루프의 `ws = quotes[...]` 를 `ws = kis_ws` 로 한 줄 바꾸면
AST 4파일이 **전부 초록**이고(실측) 행위 테스트 20건만 붉어진다. 같은 계열로 `quotes.append(kis_ws)`
도 메인을 라운드로빈 대상에 끼운다. 그래서 `test_main_session_is_never_aliased_or_collected`
(값 흐름 금지: 바인딩·컨테이너 수집·순회)와 `test_subscribe_owner_provably_comes_from_the_quote_pool`
(양성 축: `ws` ← `quotes[...]` ← `kis_ws_pool._quotes`)을 더했다. 이 선재 구멍은 HEAD 에도
있었고(HEAD 가드 + 같은 뮤테이션 = 7 passed) cycle292 가 닫은 것이다. 여전히 **이름 기반**이지
도달성 기반은 아니다 — 최종 방어는 행위 테스트 20건이다.
"""

from __future__ import annotations

import ast
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]
_SCHEDULER_PATH = _ROOT / "src" / "engine" / "scheduler.py"
# cycle292 — 본체가 사는 곳. 봉인은 wrapper 가 아니라 이 파일을 재야 한다.
_BODY_PATH = _ROOT / "src" / "engine" / "market_op_subscribe.py"
_EIGHT_AREA_PATHS = (
    _ROOT / "src" / "realtime" / "websocket.py",
    _ROOT / "src" / "realtime" / "websocket_pool.py",
    _ROOT / "src" / "engine" / "scanner.py",
)

_FN = "_subscribe_market_operation_tickers"  # scheduler 위임 wrapper
_BODY_FN = "subscribe_market_operation_tickers"  # cycle292 leaf 본체


def _get_function_node(tree: ast.AST, name: str) -> ast.AST:
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    raise AssertionError(f"함수 {name} 미발견")


def _vi_hook() -> ast.AST:
    """VI 구독 **본체** 노드 (cycle292 부터 leaf 파일)."""
    assert _BODY_PATH.exists(), (
        f"본체 leaf 부재: {_BODY_PATH} — 기준선 소실은 명시 FAIL(공허 초록 차단)"
    )
    tree = ast.parse(_BODY_PATH.read_text(encoding="utf-8"))
    return _get_function_node(tree, _BODY_FN)


def _attr_call_count(fn: ast.AST, owner: str, attrs: set[str]) -> int:
    return len(_attr_calls(fn, owner, attrs))


def _name_ids(fn: ast.AST) -> set[str]:
    return {n.id for n in ast.walk(fn) if isinstance(n, ast.Name)}


def _attr_calls(fn: ast.AST, owner: str, attrs: set[str]) -> list[ast.Call]:
    out: list[ast.Call] = []
    for node in ast.walk(fn):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if (
            isinstance(func, ast.Attribute)
            and func.attr in attrs
            and isinstance(func.value, ast.Name)
            and func.value.id == owner
        ):
            out.append(node)
    return out


def test_no_main_subscribe_in_vi_hook() -> None:
    """(1) VI 훅에 `kis_ws.subscribe(...)` 호출 0건 — 메인 tick 슬롯 절대 미접촉.

    `kis_ws` 참조 자체는 계측(`get_subscribed_tickers()` / `_subscriptions`) 목적으로
    남아도 되지만, **구독 SEND** 는 한 건도 없어야 한다.
    """
    fn = _vi_hook()
    calls = _attr_calls(fn, "kis_ws", {"subscribe"})
    assert calls == [], (
        "VI(H0UNMKO0) 는 메인 세션 구독 금지 — 08-19 OPSP0008(시세 7건) 재발 원인"
    )
    # cycle292 양성 대조군 — 구독 SEND 가 통째로 사라져도 위 단언은 초록이다.
    # 보조 세션 객체 직접 호출(`ws.subscribe(...)`)이 살아 있어야 "메인이 아닌 곳에
    # 붙는다" 가 증명된다. 0 건이면 이 가드는 아무것도 재고 있지 않다.
    direct = _attr_call_count(fn, "ws", {"subscribe"})
    assert direct >= 1, (
        "보조 세션 직접 구독(`ws.subscribe`)이 0건 — 구독 경로가 사라졌거나 owner 가 "
        "바뀌었다. 이 가드가 공허해진 상태이므로 시끄럽게 실패시킨다"
    )


_MAIN_SESSION_NAMES = frozenset({"kis_ws", "kis_ws_pool"})
_COLLECT_METHODS = frozenset({"append", "extend", "insert", "add", "update"})


def _is_main_name(node: ast.AST) -> bool:
    return isinstance(node, ast.Name) and node.id in _MAIN_SESSION_NAMES


def test_main_session_is_never_aliased_or_collected() -> None:
    """(1-b = **G-292-9a**, cycle292) 메인 세션을 **다른 이름에 담는 것**도 금지.

    ⚠️ 위 `test_no_main_subscribe_in_vi_hook` 은 **owner 이름 기반**이라 별칭 한 줄로
    우회된다 — 배치 루프의 `ws = quotes[...]` 를 `ws = kis_ws` 로 바꾸면 호출 owner 가
    `ws` 라 `_attr_calls(fn, "kis_ws", …)` 가 `[]` 이고, cycle292 가 넣은 `ws.subscribe >= 1`
    양성 대조군마저 별칭으로 충족된다(실측: AST 4파일 전부 초록 / 행위 테스트 20건만 red).
    같은 계열로 `quotes.append(kis_ws)` 도 메인을 라운드로빈 대상에 끼워 넣는다.

    그래서 여기서는 **값 흐름**을 막는다 — `kis_ws`/`kis_ws_pool` 은 읽기(`getattr(...)`,
    `is None` 비교, `.get_subscribed_tickers()`) 에만 쓰이고 **다른 이름에 바인딩되거나
    컨테이너에 수집될 수 없다**. 완전한 도달성 분석은 아니고(행위 테스트 20건이 최종
    방어다), 실제로 관측된 우회 형태를 닫는다.
    """
    fn = _vi_hook()
    offenders: list[str] = []

    def _flag(lineno: int, what: str) -> None:
        offenders.append(f"L{lineno}: {what}")

    for node in ast.walk(fn):
        # ① 대입 — `ws = kis_ws` / `ws: X = kis_ws` / `(ws := kis_ws)` / `a = (kis_ws, …)`
        value = None
        if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign, ast.NamedExpr)):
            value = node.value
        if value is not None:
            if _is_main_name(value):
                _flag(node.lineno, "메인 세션을 지역 이름에 바인딩")
            if isinstance(value, (ast.Tuple, ast.List, ast.Set)):
                if any(_is_main_name(e) for e in value.elts):
                    _flag(node.lineno, "메인 세션을 컨테이너 리터럴에 담음")
        # ② 순회 — `for ws in (kis_ws, …)` / `[… for ws in [kis_ws]]`
        it = None
        if isinstance(node, (ast.For, ast.AsyncFor)):
            it = node.iter
        elif isinstance(node, ast.comprehension):
            it = node.iter
        if it is not None:
            if _is_main_name(it):
                _flag(getattr(it, "lineno", -1), "메인 세션을 직접 순회")
            if isinstance(it, (ast.Tuple, ast.List, ast.Set)) and any(
                _is_main_name(e) for e in it.elts
            ):
                _flag(getattr(it, "lineno", -1), "메인 세션을 순회 대상에 포함")
        # ③ 수집 — `quotes.append(kis_ws)` 류
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr in _COLLECT_METHODS and any(
                _is_main_name(a) for a in node.args
            ):
                _flag(node.lineno, f"메인 세션을 `.{node.func.attr}()` 로 수집")

    assert offenders == [], (
        "메인 세션(`kis_ws`/`kis_ws_pool`)을 다른 이름·컨테이너로 옮기면 owner 이름 기반 "
        f"봉인이 통째로 우회된다 — 08-19 OPSP0008 재발 경로. 위반: {offenders}"
    )


def test_subscribe_owner_provably_comes_from_the_quote_pool() -> None:
    """(1-c = **G-292-9b**, cycle292) 구독 owner `ws` 의 **출처가 보조 세션 목록**임을 구조로 증명한다.

    위 (1-b) 가 "메인이 새지 않는다" 는 부정 축이라면, 이쪽은 "SEND 가 나가는 객체는
    `kis_ws_pool._quotes` 에서 왔다" 는 **양성 축**이다. 둘이 함께 있어야 "메인 0건" 이
    이름 우연이 아니라 구조가 된다.
    """
    fn = _vi_hook()

    ws_assigns = [
        n for n in ast.walk(fn)
        if isinstance(n, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "ws" for t in n.targets)
    ]
    assert ws_assigns, "구독 owner `ws` 대입이 0건 — 배치 루프가 사라졌다"
    for node in ws_assigns:
        assert isinstance(node.value, ast.Subscript) and isinstance(
            node.value.value, ast.Name
        ) and node.value.value.id == "quotes", (
            f"L{node.lineno}: `ws` 는 `quotes[...]` 에서만 나와야 한다 — "
            "다른 출처면 메인 세션이 owner 가 될 수 있다"
        )

    quotes_assigns = [
        n for n in ast.walk(fn)
        if isinstance(n, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "quotes" for t in n.targets)
    ]
    assert quotes_assigns, "`quotes` 대입이 0건 — 보조 세션 목록 확보 경로가 사라졌다"
    for node in quotes_assigns:
        names = {n.id for n in ast.walk(node.value) if isinstance(n, ast.Name)}
        consts = {
            n.value for n in ast.walk(node.value)
            if isinstance(n, ast.Constant) and isinstance(n.value, str)
        }
        assert "kis_ws_pool" in names and "_quotes" in consts, (
            f"L{node.lineno}: `quotes` 는 `kis_ws_pool._quotes` 에서만 나와야 한다 "
            f"(참조 {sorted(names)} / 문자열 {sorted(consts)})"
        )


def test_no_bypass_limit_true_literal() -> None:
    """(2) VI 훅 본체에 `bypass_limit=True` 키워드 0건.

    bypass 는 tick HIGH(손절 생명선)의 계약이다. 관찰 채널이 빌려 쓰면 안 된다.
    """
    fn = _vi_hook()
    offenders = []
    present = 0
    for node in ast.walk(fn):
        if not isinstance(node, ast.Call):
            continue
        for kw in node.keywords:
            if kw.arg != "bypass_limit":
                continue
            present += 1
            if isinstance(kw.value, ast.Constant) and kw.value.value is True:
                offenders.append(node.lineno)
    assert offenders == [], (
        f"VI 구독은 bypass_limit=True 금지 (서버 한도 41 우회 불가). 위반 라인: {offenders}"
    )
    # cycle292 양성 대조군 — 키워드 자체가 사라지면(기본값 의존) 위 단언은 공허하다.
    # 현행 본체는 `bypass_limit=False` 를 **명시**한다(1건). 명시가 계약이다.
    assert present >= 1, (
        "`bypass_limit` 키워드가 0건 — 명시 False 가 사라졌다. 기본값에 의존하면 "
        "realtime 쪽 기본값 변경이 조용히 VI 를 메인 한도 우회로 되돌린다"
    )


def test_no_pool_subscribe_unsubscribe_calls() -> None:
    """(3) VI 훅에 `kis_ws_pool.subscribe/unsubscribe` 호출 0건 (F-P 영구 봉인).

    `websocket_pool._ticker_to_session` 은 `(tr_id, tr_key)` 가 아니라 `tr_key` 단일
    키라, VI 가 풀 API 를 경유하면
      - 이미 TICK 이 붙은 종목 → 중복 분기로 SEND 자체가 안 나가고
      - TICK drop 종목 → VI 때문에 quote-N 으로 기록돼 **TICK 이 영구히 안 붙는다.**
    구조 정정(복합키)은 8영역이라 후속 사이클 — 이번엔 **호출을 안 하는 것**으로 우회한다.
    """
    fn = _vi_hook()
    calls = _attr_calls(fn, "kis_ws_pool", {"subscribe", "unsubscribe"})
    assert calls == [], (
        "VI 는 보조 세션 객체를 직접 호출한다 — 풀 API 경유 시 TICK 라우팅 맵 오염"
    )
    # cycle292 양성 대조군 — `kis_ws_pool` 참조가 통째로 사라지면 보조 세션 목록
    # (`_quotes`) 을 못 읽어 VI 가 아예 안 붙는데, 위 단언은 그때도 초록이다.
    assert "kis_ws_pool" in _name_ids(fn), (
        "`kis_ws_pool` 참조 0건 — 보조 세션 목록(_quotes) 확보 경로가 사라졌다"
    )


def test_socket_state_guard_persists() -> None:
    """(승계) 2026-08-07 소켓 OPEN 가드 + `ConnectionClosedError` 핸들러 존치."""
    src = _BODY_PATH.read_text(encoding="utf-8")  # cycle292 — 본체는 leaf
    fn = _vi_hook()
    fn_src = ast.get_source_segment(src, fn) or ""
    assert fn_src, "본체 소스 세그먼트 추출 실패 — 부분문자열 단언이 공허해진다"

    assert "State.OPEN" in fn_src, "닫힌 소켓 send 레이스 가드(2026-08-07) 제거 금지"

    handlers = [n for n in ast.walk(fn) if isinstance(n, ast.ExceptHandler)]
    names = set()
    for h in handlers:
        for n in ast.walk(h.type) if h.type is not None else []:
            if isinstance(n, ast.Name):
                names.add(n.id)
    assert "ConnectionClosedError" in names, (
        "루프 중 ConnectionClosedError → break + WARNING 1행 계약 유지"
    )


def test_quote_reserve_constant_absent() -> None:
    """(5, 정정 F1) `_MARKET_OP_QUOTE_RESERVE` 상수 부재 — 예약선 재도입 차단.

    코드 노드만 검사한다(`sector_naming` 선례) — docstring 의 역사 서술은 허용하고
    실제 식별자(대입/참조) 재등장만 막는다.
    """
    from src.engine import market_op_subscribe as leaf_mod
    from src.engine import scheduler as sched_mod

    # cycle292 — 본체가 leaf 로 갔으므로 검사 면적도 **본체를 따라간다**(둘 다 본다).
    # scheduler 단독으로 두면 leaf 안 예약선 재도입을 아무도 못 잡는다.
    for mod in (sched_mod, leaf_mod):
        assert not hasattr(mod, "_MARKET_OP_QUOTE_RESERVE"), (
            f"예약 슬롯 재도입 금지({mod.__name__}) — 만석 근처에서 보유 종목 VI 가 "
            "조용히 0 이 된다(F1)"
        )
    offenders: list[str] = []
    for path in (_SCHEDULER_PATH, _BODY_PATH):
        assert path.exists(), f"스캔 대상 부재: {path}"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        offenders += [
            f"{path.name}:{n.lineno}" for n in ast.walk(tree)
            if isinstance(n, ast.Name) and n.id == "_MARKET_OP_QUOTE_RESERVE"
        ]
    assert offenders == [], f"예약선 상수 재등장 금지. 위반 라인: {offenders}"


def test_execution_notice_tr_ids_unchanged() -> None:
    """(승계, cycle214 G-214-3) 체결통보 메인 단일 강제 + H0UNMKO0 보조 허용 명시."""
    from src.api.market_operation import MARKET_OP_TR_ID
    from src.realtime import websocket_pool

    assert websocket_pool._EXECUTION_NOTICE_TR_IDS == frozenset(
        {"H0STCNI0", "H0STCNI9"}
    )
    assert MARKET_OP_TR_ID not in websocket_pool._EXECUTION_NOTICE_TR_IDS


def test_eight_areas_untouched() -> None:
    """(4) 8영역 3파일에 VI 구독 **호출** 부재 — 주석/docstring 문자열은 허용.

    `sector_naming` 선례 방식 = 코드 노드만 검사. 이번 사이클은 8영역 diff 0 이
    절대 조건이므로(롤백이 매매 hot path 를 흔들면 안 된다) 정적으로 봉인한다.
    """
    offenders: list[str] = []
    for path in _EIGHT_AREA_PATHS:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if not (isinstance(func, ast.Attribute) and func.attr in {"subscribe", "unsubscribe"}):
                continue
            for arg in node.args:
                if isinstance(arg, ast.Name) and arg.id == "MARKET_OP_TR_ID":
                    offenders.append(f"{path.relative_to(_ROOT)}:{node.lineno}")
                if isinstance(arg, ast.Constant) and arg.value == "H0UNMKO0":
                    offenders.append(f"{path.relative_to(_ROOT)}:{node.lineno}")
    assert offenders == [], (
        "8영역(realtime/**, scanner) 에 VI 구독 호출 금지 — diff 0 절대 조건. 위반: "
        + ", ".join(offenders)
    )
