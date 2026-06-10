"""사이클 100 G-REG1 — 사이클 55 R-1 `SellRejectionTracker` 영속 (MEDIUM, NXT 시간대 적시 청산 영역).

명세 (`_workspace/red/cycle100_ui_prefix_fix_market_branching_persistence.md`):

**영역 2 = 사이클 55 R-1 영속 확정 (변경 0, 영속 가드만)**:
- `src/engine/order_engine.py::execute_sell` L505 영역 `self._sell_rejection.is_blocked(ticker, now_kst)` 진입 게이트 = 사이클 55 R-1 영속
- KRX 메인 5분 TTL / NXT 시간대 다음 KST 09:00 TTL / `market_order_disallowed` 30초 TTL
- NXT 폴백 실패 시 `_pending_next_day_clear` 익일 청산 자동 전환 영속

**Phase 1 진단 영속 영역 (사이클 100 Phase 1)**:
- 사용자 보고 "08:00:00 APBK0918 매도 거부 = 적시 청산주문 놓칠 수 있다 우려" 영역 = 사이클 55 R-1 영속이 정확히 해당 결함 영구 차단

검증 매트릭스:
- AST 정적 검증 — `execute_sell` 본체 영역 `self._sell_rejection.is_blocked` 진입 게이트 호출 영속
- AST 정적 검증 — `register_market_closed` 호출 영속 (NXT 시간대 다음 09:00 TTL)
- AST 정적 검증 — `_sell_rejection.reset_daily()` 위임 영속 (`OrderEngine.reset_daily_state` 영역)

**Red 상태**: 영역 영속 확인 가드 — 사이클 55 R-1 silent 삭제 가설 영구 차단.

**Green**: 사이클 55 R-1 영속 = production 변경 0 → 영속 가드 PASS.

영속 의무:
- 사이클 55 R-1 영속 (SellRejectionTracker 진입 게이트 + 4 분류 통합)
- 사이클 57 V-1 영속 (폭주 알람 hook, 10분 윈도우 5건 초과 CRITICAL)
- 매매 안전성 영역 영향 0 (영속 가드만 추가)
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit


def _order_engine_module_path() -> Path:
    """order_engine.py 모듈 절대 경로."""
    import src.engine.order_engine as oe_mod
    return Path(oe_mod.__file__)


def _order_engine_module_source() -> str:
    """order_engine.py source text."""
    return _order_engine_module_path().read_text(encoding="utf-8")


def test_g_reg1_sell_rejection_tracker_is_blocked_gate_persistence():
    """G-REG1-A: AST 정적 가드 — `execute_sell` 진입 게이트 `is_blocked` 영속 (MEDIUM).

    검증 매트릭스 (사이클 55 R-1 영속):
    - `execute_sell` 본체 영역 `self._sell_rejection.is_blocked(ticker, now_kst)` 호출 영속
    - 진입 게이트 = NXT 시간대 매도 거부 영역 적시 청산 영구 차단

    Red 상태 (사이클 100): 영역 영속 확인 가드 — 사이클 55 R-1 silent 삭제 가설 영구 차단.

    Green: 사이클 55 R-1 영속 = production 변경 0 → 영속 가드 PASS.
    """
    source = _order_engine_module_source()
    tree = ast.parse(source)

    execute_sell_body = None
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "execute_sell":
            execute_sell_body = ast.get_source_segment(source, node)
            break

    assert execute_sell_body is not None, (
        "\n사이클 100 G-REG1-A Red 상태 — `execute_sell` 함수 부재.\n"
        "  영속 의무: src/engine/order_engine.py::execute_sell 영속"
    )

    # 가드: `self._sell_rejection.is_blocked` 호출 영속 (사이클 55 R-1)
    assert "self._sell_rejection.is_blocked" in execute_sell_body, (
        f"\n사이클 100 G-REG1-A 위반 — `execute_sell` 영역 `self._sell_rejection.is_blocked` 진입 게이트 영속 위반:\n"
        f"  기대: execute_sell 본체 영역 `self._sell_rejection.is_blocked(ticker, now_kst)` 호출 영속 (사이클 55 R-1)\n"
        f"  실제: execute_sell 본체 영역 호출 0건\n"
        f"  결함 가설: 사이클 55 R-1 SellRejectionTracker 진입 게이트 silent 삭제\n"
        f"           → NXT 시간대 매도 거부 영역 적시 청산 영구 차단 무효화\n"
        f"           → 사용자 보고 '08:00:00 APBK0918 매도 거부 = 적시 청산주문 놓칠 수 있다' 영역 재발\n"
        f"  영속 의무: src/engine/order_engine.py::execute_sell L505 영역 영속\n"
        f"  명세 영속: _workspace/red/cycle100_ui_prefix_fix_market_branching_persistence.md"
    )


def test_g_reg1_register_market_closed_persistence():
    """G-REG1-B: AST 정적 가드 — `register_market_closed` 호출 영속 (MEDIUM).

    검증 매트릭스 (사이클 55 R-1 영속):
    - `execute_sell` 본체 영역 또는 `_handle_*` 영역 `register_market_closed(ticker, _now_kst, in_krx_main_hours=...)` 호출 영속
    - 2단계 TTL 등록 영역 (KRX 메인 5분 / NXT 시간대 다음 09:00)
    """
    source = _order_engine_module_source()

    # 가드: `register_market_closed` 호출 영속 (사이클 55 R-1)
    assert "register_market_closed" in source, (
        f"\n사이클 100 G-REG1-B 위반 — `register_market_closed` 호출 영속 위반:\n"
        f"  기대: src/engine/order_engine.py 영역 register_market_closed 호출 ≥1건 영속 (사이클 55 R-1)\n"
        f"  실제: 호출 0건\n"
        f"  결함 가설: 사이클 55 R-1 NXT 시간대 다음 KST 09:00 TTL 등록 silent 삭제\n"
        f"           → 매도 거부 재시도 폭주 + 적시 청산 영구 차단 무효화\n"
        f"  영속 의무: src/engine/sell_rejection.py::SellRejectionTracker.register_market_closed 영역 영속\n"
        f"  명세 영속: _workspace/red/cycle100_ui_prefix_fix_market_branching_persistence.md"
    )


def test_g_reg1_reset_daily_delegation_persistence():
    """G-REG1-C: AST 정적 가드 — `_sell_rejection.reset_daily()` 위임 영속 (MEDIUM).

    검증 매트릭스 (사이클 55 R-1 영속):
    - `OrderEngine.reset_daily_state` 영역 `self._sell_rejection.reset_daily()` 위임 영속
    - `scheduler._reset_daily_state()` → `OrderEngine.reset_daily_state()` 동행 위임 영속
    """
    source = _order_engine_module_source()
    tree = ast.parse(source)

    reset_daily_state_body = None
    for node in ast.walk(tree):
        if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)) and node.name == "reset_daily_state":
            reset_daily_state_body = ast.get_source_segment(source, node)
            break

    assert reset_daily_state_body is not None, (
        "\n사이클 100 G-REG1-C Red 상태 — `reset_daily_state` 메서드 부재.\n"
        "  영속 의무: src/engine/order_engine.py::OrderEngine.reset_daily_state 영속"
    )

    # 가드: `_sell_rejection.reset_daily()` 위임 영속 (사이클 55 R-1 + 사이클 57 V-1)
    assert "_sell_rejection.reset_daily" in reset_daily_state_body, (
        f"\n사이클 100 G-REG1-C 위반 — `_sell_rejection.reset_daily()` 위임 영속 위반:\n"
        f"  기대: OrderEngine.reset_daily_state 영역 self._sell_rejection.reset_daily() 위임 영속 (사이클 55 R-1)\n"
        f"  실제: reset_daily_state 본체 영역 위임 0건\n"
        f"  결함 가설: 사이클 55 R-1 reset_daily 위임 silent 삭제 → 다음 영업일 TTL 영역 stale 잔존\n"
        f"  영속 의무: src/engine/sell_rejection.py::SellRejectionTracker.reset_daily 영역 영속\n"
        f"  명세 영속: _workspace/red/cycle100_ui_prefix_fix_market_branching_persistence.md"
    )
