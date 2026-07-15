"""사이클 214 (2026-07-15) — AST/SAFETY 영구 가드.

H0UNMKO0 후보 구독 풀 분산 (LOW `kis_ws_pool` + HIGH `kis_ws` 메인 직접).

- G-214-3 (SAFETY): `_EXECUTION_NOTICE_TR_IDS == {"H0STCNI0","H0STCNI9"}` 불변
  (H0UNMKO0 미포함 = 보조 분산 허용 + 체결통보 메인 단일 강제 영속).
- G-214-5 (AST/SAFETY): `_subscribe_market_operation_tickers` LOW 루프는
  `kis_ws_pool` 사용 + HIGH 루프는 `kis_ws`(메인 직접) 유지.
- 매매 안전성 8영역 diff 0 (scheduler.py = 8영역 밖, realtime/ 미변경).

domain 자문: `_workspace/domain_consult/cycle214_h0unmko0_cap.md` (판정 (b))
Red memo: `_workspace/red/cycle214_h0unmko0_pool.md`
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


def test_G_214_5_low_uses_pool_high_uses_main() -> None:
    """G-214-5 (AST/SAFETY) — LOW 풀 분산 + HIGH 메인 직접.

    `_subscribe_market_operation_tickers` 함수 본체에서:
    - `kis_ws_pool` 참조 존재 (LOW 후보 풀 분산 경유)
    - `kis_ws` 참조 존재 (HIGH 보유/익일청산 메인 직접 유지)

    현재 production 은 LOW 도 `kis_ws` 직접 → `kis_ws_pool` 참조 0건 → FAIL (Red).
    """
    tree = ast.parse(_SCHEDULER_PATH.read_text(encoding="utf-8"))
    fn = _get_function_node(tree, "_subscribe_market_operation_tickers")
    names = _collect_names(fn)

    assert "kis_ws_pool" in names, (
        "LOW 후보 H0UNMKO0 는 kis_ws_pool.subscribe(priority='LOW') 풀 분산 경유 의무"
    )
    assert "kis_ws" in names, (
        "HIGH 보유/익일청산 H0UNMKO0 는 kis_ws.subscribe(bypass_limit=True) 메인 직접 유지 의무"
    )


def test_G_214_5b_high_bypass_true_persists() -> None:
    """G-214-5 보강 — HIGH 루프의 bypass_limit=True 키워드 인자 영속.

    cycle 32 R4 보유/익일청산 절대 보호 = HIGH 구독은 bypass_limit=True 명시.
    """
    tree = ast.parse(_SCHEDULER_PATH.read_text(encoding="utf-8"))
    fn = _get_function_node(tree, "_subscribe_market_operation_tickers")

    has_bypass_true = False
    for node in ast.walk(fn):
        if isinstance(node, ast.Call):
            for kw in node.keywords:
                if kw.arg == "bypass_limit" and isinstance(kw.value, ast.Constant):
                    if kw.value.value is True:
                        has_bypass_true = True
    assert has_bypass_true, "HIGH H0UNMKO0 구독은 bypass_limit=True 명시 의무 (cycle 32 R4)"


def test_G_214_5c_pool_priority_low_keyword() -> None:
    """G-214-5 보강 — LOW 후보 풀 subscribe 는 priority='LOW' 키워드 명시.

    현재 production 은 pool.subscribe 호출 자체가 없음 → FAIL (Red).
    """
    tree = ast.parse(_SCHEDULER_PATH.read_text(encoding="utf-8"))
    fn = _get_function_node(tree, "_subscribe_market_operation_tickers")

    has_pool_low = False
    for node in ast.walk(fn):
        if isinstance(node, ast.Call):
            # kis_ws_pool.subscribe(...) 형태
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr == "subscribe":
                val = func.value
                if isinstance(val, ast.Name) and val.id == "kis_ws_pool":
                    for kw in node.keywords:
                        if (
                            kw.arg == "priority"
                            and isinstance(kw.value, ast.Constant)
                            and kw.value.value == "LOW"
                        ):
                            has_pool_low = True
    assert has_pool_low, (
        "LOW 후보는 kis_ws_pool.subscribe(priority='LOW') 풀 분산 경유 의무"
    )
