"""사이클 100 G-MKT2 — `_strategy_exchange_async` 매도 영역 호출 영속 (HIGH, 사이클 13 영속).

명세 (`_workspace/red/cycle100_ui_prefix_fix_market_branching_persistence.md`):

**영역 2 = 사이클 13 영속 확정 (변경 0, 영속 가드만)**:
- `src/engine/order_engine.py::execute_sell` L543 영역 `target_exchange = await self._strategy_exchange_async(...)` = 사이클 13 (Phase G) 영속
- 시장가 매도 영역 NXT 사전 차단 영속 (KIS 거부 chain 차단)
- `limit_price > 0` 분기 (NXT 익일청산 지정가) = `target_exchange = "NXT"` 우회 영역 영속

**Phase 1 진단 영속 영역 (사이클 100 Phase 1)**:
- 사이클 13 (Phase G) 영속 = 매도 진입 전 NXT 사전 차단
- 적시 청산 영역 영속 (시장가 매도 = NXT 사전 차단 영속)

검증 매트릭스:
- AST 정적 검증 — `execute_sell` 본체 영역 `_strategy_exchange_async` 호출 ≥1건 영속
- `limit_price > 0` 분기 (지정가 매도) = `target_exchange = "NXT"` 우회 영역 영속
- 시장가 매도 (`limit_price == 0`) = `_strategy_exchange_async(strategy_id, ticker=ticker)` 호출 영속

**Red 상태**: 영역 영속 확인 가드 — 사이클 13 매도 영역 silent 삭제 가설 영구 차단.

**Green**: 사이클 13 영속 = production 변경 0 → 영속 가드 PASS.

영속 의무:
- 사이클 13 Phase G 영속 (매도 hot path 영역)
- 사이클 55 R-1 영속 (SellRejectionTracker 진입 게이트 영역 호환)
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


def test_g_mkt2_execute_sell_calls_strategy_exchange_async():
    """G-MKT2: AST 정적 가드 — `execute_sell` 본체 영역 `_strategy_exchange_async` 호출 영속 (HIGH).

    검증 매트릭스 (사이클 13 Phase G 영속):
    - `execute_sell` 함수 정의 영속
    - `execute_sell` 본체 영역에 `_strategy_exchange_async` 호출 ≥1건 영속
    - 시장가 매도 영역 (`limit_price == 0`) NXT 사전 차단 영속
    - 지정가 매도 영역 (`limit_price > 0`) `target_exchange = "NXT"` 우회 영역 영속

    Red 상태 (사이클 100): 영역 영속 확인 가드 — 사이클 13 매도 영역 silent 삭제 가설 영구 차단.

    Green: 사이클 13 Phase G 영속 = production 변경 0 → 영속 가드 PASS.

    영속 의무:
    - `_strategy_exchange_async` 정의 영속 (사이클 13)
    - `execute_sell` 본체 영역 호출 영속 (L543 영역)
    - 미래 backend-dev 가 매도 영역 호출 silent 삭제 영구 차단
    """
    source = _order_engine_module_source()
    tree = ast.parse(source)

    # 가드 1: `execute_sell` 함수 정의 영속
    execute_sell_body = None
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "execute_sell":
            execute_sell_body = ast.get_source_segment(source, node)
            break

    assert execute_sell_body is not None, (
        "\n사이클 100 G-MKT2 Red 상태 — `execute_sell` 함수 부재.\n"
        "  영속 의무: src/engine/order_engine.py::execute_sell 영속\n"
        "  명세 영속: _workspace/red/cycle100_ui_prefix_fix_market_branching_persistence.md"
    )

    # 가드 2: `execute_sell` 본체 영역에 `_strategy_exchange_async` 호출 ≥1건 영속
    assert "_strategy_exchange_async" in execute_sell_body, (
        f"\n사이클 100 G-MKT2 위반 — `execute_sell` 본체 영역 `_strategy_exchange_async` 호출 영속 위반:\n"
        f"  기대: execute_sell 본체 영역 _strategy_exchange_async 호출 ≥1건 영속 (사이클 13 영속 L543)\n"
        f"  실제: execute_sell 본체 영역 호출 0건\n"
        f"  결함 가설: 사이클 13 Phase G 매도 영역 silent 삭제 → 시장가 매도 NXT 사전 차단 무효화\n"
        f"  → KIS 거부 chain (NXT 시간대 사이클 55 R-1 진입 게이트 트리거)\n"
        f"  영속 의무: src/engine/order_engine.py::execute_sell L543 영역 영속\n"
        f"  명세 영속: _workspace/red/cycle100_ui_prefix_fix_market_branching_persistence.md"
    )

    # 가드 3: 지정가 매도 영역 (`limit_price > 0`) `target_exchange = "NXT"` 우회 영역 영속
    # 사이클 13 영속 매트릭스: 지정가 NXT 청산은 거래소도 NXT 로 강제 (전략 기본 exchange 무관)
    assert "limit_price > 0" in execute_sell_body or "limit_price>0" in execute_sell_body or "limit_price > 0:" in execute_sell_body, (
        f"\n사이클 100 G-MKT2 위반 — `execute_sell` 영역 `limit_price > 0` 분기 영속 위반:\n"
        f"  기대: execute_sell 영역 지정가 분기 (`limit_price > 0`) 영속 (사이클 13 영속)\n"
        f"  결함 가설: 지정가 NXT 청산 영역 silent 삭제 → 익일청산 NXT 지정가 영역 무효화\n"
        f"  영속 의무: src/engine/order_engine.py::execute_sell limit_price > 0 분기 영속\n"
        f"  명세 영속: _workspace/red/cycle100_ui_prefix_fix_market_branching_persistence.md"
    )

    # 가드 4: 시장가 매도 분기 영역 `target_exchange = await self._strategy_exchange_async(...)` 영속
    # 본체 영역에 `target_exchange = await` 패턴 영속 (호출 사이트 영역 정합)
    has_await_call = (
        "target_exchange = await self._strategy_exchange_async" in execute_sell_body
        or "await self._strategy_exchange_async" in execute_sell_body
    )
    assert has_await_call, (
        f"\n사이클 100 G-MKT2 위반 — `execute_sell` 영역 `await self._strategy_exchange_async` 호출 영속 위반:\n"
        f"  기대: execute_sell 영역 `target_exchange = await self._strategy_exchange_async(...)` 영속 (사이클 13 L543)\n"
        f"  결함 가설: await 호출 패턴 silent 변경 → 동기 호출 race 또는 사전 차단 무효화\n"
        f"  영속 의무: src/engine/order_engine.py::execute_sell L543 영역 영속\n"
        f"  명세 영속: _workspace/red/cycle100_ui_prefix_fix_market_branching_persistence.md"
    )
