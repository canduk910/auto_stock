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
"""

from __future__ import annotations

import ast
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]
_SCHEDULER_PATH = _ROOT / "src" / "engine" / "scheduler.py"
_EIGHT_AREA_PATHS = (
    _ROOT / "src" / "realtime" / "websocket.py",
    _ROOT / "src" / "realtime" / "websocket_pool.py",
    _ROOT / "src" / "engine" / "scanner.py",
)

_FN = "_subscribe_market_operation_tickers"


def _get_function_node(tree: ast.AST, name: str) -> ast.AST:
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    raise AssertionError(f"함수 {name} 미발견")


def _vi_hook() -> ast.AST:
    tree = ast.parse(_SCHEDULER_PATH.read_text(encoding="utf-8"))
    return _get_function_node(tree, _FN)


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
    calls = _attr_calls(_vi_hook(), "kis_ws", {"subscribe"})
    assert calls == [], (
        "VI(H0UNMKO0) 는 메인 세션 구독 금지 — 08-19 OPSP0008(시세 7건) 재발 원인"
    )


def test_no_bypass_limit_true_literal() -> None:
    """(2) VI 훅 본체에 `bypass_limit=True` 키워드 0건.

    bypass 는 tick HIGH(손절 생명선)의 계약이다. 관찰 채널이 빌려 쓰면 안 된다.
    """
    offenders = []
    for node in ast.walk(_vi_hook()):
        if not isinstance(node, ast.Call):
            continue
        for kw in node.keywords:
            if (
                kw.arg == "bypass_limit"
                and isinstance(kw.value, ast.Constant)
                and kw.value.value is True
            ):
                offenders.append(node.lineno)
    assert offenders == [], (
        f"VI 구독은 bypass_limit=True 금지 (서버 한도 41 우회 불가). 위반 라인: {offenders}"
    )


def test_no_pool_subscribe_unsubscribe_calls() -> None:
    """(3) VI 훅에 `kis_ws_pool.subscribe/unsubscribe` 호출 0건 (F-P 영구 봉인).

    `websocket_pool._ticker_to_session` 은 `(tr_id, tr_key)` 가 아니라 `tr_key` 단일
    키라, VI 가 풀 API 를 경유하면
      - 이미 TICK 이 붙은 종목 → 중복 분기로 SEND 자체가 안 나가고
      - TICK drop 종목 → VI 때문에 quote-N 으로 기록돼 **TICK 이 영구히 안 붙는다.**
    구조 정정(복합키)은 8영역이라 후속 사이클 — 이번엔 **호출을 안 하는 것**으로 우회한다.
    """
    calls = _attr_calls(_vi_hook(), "kis_ws_pool", {"subscribe", "unsubscribe"})
    assert calls == [], (
        "VI 는 보조 세션 객체를 직접 호출한다 — 풀 API 경유 시 TICK 라우팅 맵 오염"
    )


def test_socket_state_guard_persists() -> None:
    """(승계) 2026-08-07 소켓 OPEN 가드 + `ConnectionClosedError` 핸들러 존치."""
    src = _SCHEDULER_PATH.read_text(encoding="utf-8")
    fn = _vi_hook()
    fn_src = ast.get_source_segment(src, fn) or ""

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
    from src.engine import scheduler as sched_mod

    assert not hasattr(sched_mod, "_MARKET_OP_QUOTE_RESERVE"), (
        "예약 슬롯 재도입 금지 — 만석 근처에서 보유 종목 VI 가 조용히 0 이 된다(F1)"
    )
    tree = ast.parse(_SCHEDULER_PATH.read_text(encoding="utf-8"))
    offenders = [
        n.lineno for n in ast.walk(tree)
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
