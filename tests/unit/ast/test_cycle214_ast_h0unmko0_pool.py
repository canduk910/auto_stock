"""사이클 214 (2026-07-15) → **cycle221 (2026-08-20) 의미 전환** AST 가드.

## 원래 계약

- G-214-3 (SAFETY): `_EXECUTION_NOTICE_TR_IDS == {"H0STCNI0","H0STCNI9"}` 불변. **유지**.
- G-214-5 (AST): LOW 는 `kis_ws_pool` 경유 + HIGH 는 `kis_ws` 메인 직접 + bypass_limit=True.

## 전환 (cycle221)

08-19 OPSP0008 117건(시세 7건 = 매수 직후 보유 4종목 tick blind)의 근본은 VI 관찰 채널이
메인 41 슬롯을 tick 과 경쟁한 것이다. `bypass_limit=True` 는 **로컬 가드만** 우회하고 KIS
서버 한도는 못 넘는다 → 초과분이 OPSP0008.

- G-214-5b **정확히 반전**: 함수 본체 `bypass_limit=True` 리터럴 **0건** 의무.
- G-214-5c **폐기**: `priority="LOW"` 키워드 소멸. `_ticker_to_session` 이 `tr_key` 단일
  키라 VI 가 풀 API 를 경유하면 TICK drop 종목이 quote-N 으로 고착 → TICK 영구 미구독(F-P).
  대체 가드 = `test_cycle221_ast_market_op_no_main.py::test_no_pool_subscribe_unsubscribe_calls`.
- G-214-5 **재정의**: `kis_ws_pool` 참조는 `_quotes` **읽기** 목적으로만 잔존하고,
  `kis_ws` 참조는 구독이 아니라 **점유 계측**(`get_subscribed_tickers`/`_subscriptions`) 목적.

봉인 정본은 `tests/unit/ast/test_cycle221_ast_market_op_no_main.py`.
"""

from __future__ import annotations

import ast
from pathlib import Path


_ROOT = Path(__file__).resolve().parents[3]
_SCHEDULER_PATH = _ROOT / "src" / "engine" / "scheduler.py"
_POOL_PATH = _ROOT / "src" / "realtime" / "websocket_pool.py"


def _get_function_node(tree: ast.AST, name: str) -> ast.AST:
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    raise AssertionError(f"함수 {name} 미발견")


def test_G_214_3_execution_notice_tr_ids_unchanged() -> None:
    """G-214-3 (SAFETY) — `_EXECUTION_NOTICE_TR_IDS` 불변.

    체결통보 2종만 보조 세션 차단 → H0UNMKO0 는 미포함 = 풀 분산 허용.
    이 frozenset 이 바뀌면 체결통보 메인 단일 강제(cycle 자금 안전 절대 원칙)가
    깨지므로 영구 가드. (회귀 가드 — 현재도 PASS)
    """
    from src.realtime import websocket_pool

    assert websocket_pool._EXECUTION_NOTICE_TR_IDS == frozenset(
        {"H0STCNI0", "H0STCNI9"}
    )
    # H0UNMKO0 는 절대 포함되면 안 된다 (풀 분산 대상).
    from src.api.market_operation import MARKET_OP_TR_ID

    assert MARKET_OP_TR_ID not in websocket_pool._EXECUTION_NOTICE_TR_IDS


def _collect_names(node: ast.AST) -> set[str]:
    return {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}


def test_G_214_5_pool_referenced_for_quote_sessions_only() -> None:
    """[의미 전환 G-214-5] 참조는 남되 **의미가 다르다**.

    - `kis_ws_pool` = 보조 세션 리스트(`_quotes`) **읽기** 소스 (subscribe 경유 아님).
    - `kis_ws` = 메인 **점유 계측**(`get_subscribed_tickers`/`_subscriptions`) 소스 +
      소켓 OPEN 가드. 구독 SEND 는 0건(cycle221 AST 가드가 별도 봉인).
    """
    tree = ast.parse(_SCHEDULER_PATH.read_text(encoding="utf-8"))
    fn = _get_function_node(tree, "_subscribe_market_operation_tickers")
    names = _collect_names(fn)

    assert "kis_ws_pool" in names, (
        "보조 세션(_quotes) 을 읽으려면 kis_ws_pool 참조가 필요하다"
    )
    assert "kis_ws" in names, (
        "메인 점유 계측(main_tick/main_total/main_over) + 소켓 OPEN 가드용 참조 의무"
    )

    quotes_read = any(
        isinstance(n, ast.Attribute) and n.attr == "_quotes"
        for n in ast.walk(fn)
    ) or any(
        isinstance(n, ast.Constant) and n.value == "_quotes" for n in ast.walk(fn)
    )
    assert quotes_read, "VI 는 보조 세션 리스트(_quotes) 를 직접 읽어 라운드로빈 배치한다"


def test_G_214_5b_bypass_true_is_now_forbidden() -> None:
    """[의미 전환 G-214-5b, 정확히 반전] `bypass_limit=True` 리터럴 **0건**.

    원래는 "cycle 32 R4 절대보호 = HIGH 는 bypass_limit=True 명시 의무" 였다.
    그러나 R4 의 보호 대상은 **시세(tick)** 이고, VI 관찰 채널이 그 계약을 빌려 쓰면
    메인이 서버 한도 41 을 넘겨 OPSP0008 로 **tick 이 밀린다**(08-19 실증).
    """
    tree = ast.parse(_SCHEDULER_PATH.read_text(encoding="utf-8"))
    fn = _get_function_node(tree, "_subscribe_market_operation_tickers")

    offenders = []
    for node in ast.walk(fn):
        if isinstance(node, ast.Call):
            for kw in node.keywords:
                if (
                    kw.arg == "bypass_limit"
                    and isinstance(kw.value, ast.Constant)
                    and kw.value.value is True
                ):
                    offenders.append(node.lineno)
    assert offenders == [], (
        "VI(H0UNMKO0) 구독은 bypass_limit=True 금지 — 서버 한도 41 우회 불가. "
        f"위반 라인: {offenders}"
    )


# [폐기] test_G_214_5c_pool_priority_low_keyword
# `kis_ws_pool.subscribe(priority="LOW")` 경로 자체가 소멸했다 — `_ticker_to_session` 이
# `tr_key` 단일 키라 VI 가 경유하면 TICK drop 종목이 quote-N 으로 기록돼 TICK 이 영구히
# 안 붙는다(F-P). 대체 가드:
#   tests/unit/ast/test_cycle221_ast_market_op_no_main.py::test_no_pool_subscribe_unsubscribe_calls
