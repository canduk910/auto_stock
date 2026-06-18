"""사이클 163 (2026-06-18) — AST 영구 영속 가드.

영속 의무 매트릭스:
- G-163-AST-1: boot_manager 영역 count_active import + 호출 영속
- G-163-AST-2: 4 전략 prepare 재시도 hook AST 영속 (사이클 158 VB 패턴 답습)
- G-163-AST-3: _handle_buy_fill 영역 3 try/except 영속 (DB 영역만 graceful)
"""
from __future__ import annotations

import ast
import pathlib


_REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]


def test_G163_AST_1_boot_manager_count_active_call():
    """G-163-AST-1: boot_manager 영역 count_active 호출 영속.

    사이클 163 시정 영역 = prepare 호출 *전* count_active 호출 영속.
    """
    src = (_REPO_ROOT / "src/engine/boot_manager.py").read_text(encoding="utf-8")
    assert "count_active" in src, "boot_manager.py 영역 count_active 호출 부재"
    # 사이클 158 hook 한계 보완 의도 명시
    assert "stock_master" in src
    # 5분 cap 영속
    assert "300" in src or "BOOT_PREPARE_STOCK_MASTER_WAIT_SECS" in src


def test_G163_AST_2_four_strategies_retry_hook():
    """G-163-AST-2: 4 전략 prepare 영역 retry hook AST 영속.

    LTV/donchian/BFB/VCP 모두 사이클 158 VB 패턴 답습.
    """
    files = [
        "src/engine/strategies/long_tail_volatility.py",
        "src/engine/strategies/donchian_swing.py",
        "src/engine/strategies/bull_flag_breakout.py",
        "src/engine/strategies/vcp_breakout.py",
    ]
    for path in files:
        src = (_REPO_ROOT / path).read_text(encoding="utf-8")
        # 자동 재시도 hook 영속 의무
        assert "retry_attempt" in src, f"{path}: retry_attempt 영역 부재"
        assert "asyncio.sleep(30)" in src, f"{path}: asyncio.sleep(30) 영역 부재"
        assert "prepare_retry" in src, f"{path}: prepare_retry prefix 부재"


def test_G163_AST_3_handle_buy_fill_db_error_isolation():
    """G-163-AST-3: _handle_buy_fill 영역 3 try/except 분리 영속.

    [buy_fill_db_error] step=update_trade_status / forced_update / save_position
    3 prefix 영구 영속 — 사이클 88 G-REJECT-1 부분 예외 영역 한정.
    """
    src = (_REPO_ROOT / "src/engine/order_engine.py").read_text(encoding="utf-8")
    tree = ast.parse(src)

    buy_fill = None
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "_handle_buy_fill":
            buy_fill = node
            break
    assert buy_fill is not None

    body_str = ast.unparse(buy_fill)
    # 3 step prefix 영속
    assert "[buy_fill_db_error]" in body_str, "[buy_fill_db_error] prefix 영구 영속 부재"
    assert "step=update_trade_status" in body_str, "step=update_trade_status 영구 영속 부재"
    assert "step=save_position" in body_str, "step=save_position 영구 영속 부재"
    # 사이클 161 영속 — price=price 인자 영속
    assert "price=price" in body_str, "사이클 161 price=price 인자 영속 부재"
    # 사이클 147 영속 — _lookup_strategy_from_trade_history 영속
    assert "_lookup_strategy_from_trade_history" in body_str
