"""사이클 100 G-MKT1 — `_strategy_exchange_async` 매수 영역 호출 영속 (HIGH, 사이클 13 영속).

명세 (`_workspace/red/cycle100_ui_prefix_fix_market_branching_persistence.md`):

**영역 2 = 사이클 13 영속 확정 (변경 0, 영속 가드만)**:
- `src/engine/order_engine.py::_strategy_exchange_async` (L128~197) = 사이클 13 (Phase G) 영속
- 매수 진입 직전 호출 (`execute_buy` 영역)
- `stock_master.get(ticker).nxt_tradable=False` → NXT/SOR → KRX 강제 다운그레이드 + `[nxt_downgrade]` WARNING

**Phase 1 진단 영속 영역 (사이클 100 Phase 1)**:
- 사이클 13 (Phase G) 영속 = 매수 진입 전 NXT 사전 차단
- 사이클 54 (2026-06-03) `_nxt_downgrade_logged_today` ticker별 1회/일 cap

검증 매트릭스:
- mock `stock_master.get(ticker)` = `StockBasics(nxt_tradable=False)` 반환
- `_strategy_exchange_async("volatility_breakout", ticker="005930")` 결과 = `"KRX"`
- AST 정적 검증 — `execute_buy` 본체 또는 매수 hot path 영역 `_strategy_exchange_async` 호출 영속

**Red 상태**: 영역 영속 확인 가드 — 사이클 13 silent 삭제 가설 영구 차단.

**Green**: 사이클 13 영속 = production 변경 0 → 영속 가드 PASS.

영속 의무:
- 사이클 13 Phase G 영속 (매수 hot path 영역)
- 사이클 54 1회/일 cap 영속
- 매매 안전성 영역 영향 0 (영속 가드만 추가)
"""
from __future__ import annotations

import ast
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = pytest.mark.unit


def _order_engine_module_path() -> Path:
    """order_engine.py 모듈 절대 경로."""
    import src.engine.order_engine as oe_mod
    return Path(oe_mod.__file__)


def _order_engine_module_source() -> str:
    """order_engine.py source text."""
    return _order_engine_module_path().read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_g_mkt1_strategy_exchange_async_returns_krx_when_nxt_not_tradable():
    """G-MKT1-A: `_strategy_exchange_async` NXT 거래 불가 영역 KRX 강제 다운그레이드 영속 (HIGH).

    검증 매트릭스 (사이클 13 Phase G 영속):
    - mock `stock_master.get("005930")` = `StockBasics(nxt_tradable=False)` 반환
    - 전략 기본 exchange = "NXT" (또는 SOR)
    - `_strategy_exchange_async("test_strategy", ticker="005930")` 결과 = "KRX"

    Red 상태 (사이클 100): 영역 영속 확인 가드 — 사이클 13 silent 삭제 가설 영구 차단.

    Green: 사이클 13 Phase G 영속 = production 변경 0 → 영속 가드 PASS.
    """
    from src.engine.order_engine import OrderEngine
    from src.models.stock import StockBasics

    # mock 전략 registry
    mock_strategy = MagicMock()
    mock_strategy.config.params = {"exchange": "NXT"}  # NXT 기본 (사이클 13 분기 진입)
    mock_registry = MagicMock()
    mock_registry.get.return_value = mock_strategy

    engine = OrderEngine(registry=mock_registry)

    # mock stock_master.get → nxt_tradable=False
    fake_basics = StockBasics(
        ticker="005930",
        name="삼성전자",
        excg_dvsn_cd="01",
        nxt_tradable=False,  # 사이클 13 분기 진입
        krx_halted=False,
        admin_item=False,
        raw={},
    )

    with patch("src.db.stock_master.get", new=AsyncMock(return_value=fake_basics)):
        with patch("src.db.stock_master.is_stale", new=AsyncMock(return_value=False)):
            result = await engine._strategy_exchange_async(
                "test_strategy", ticker="005930"
            )

    # 가드: NXT 거래 불가 → KRX 강제 다운그레이드 영속 (사이클 13 Phase G)
    assert result == "KRX", (
        f"\n사이클 100 G-MKT1-A 위반 — NXT 거래 불가 KRX 강제 다운그레이드 영속 위반:\n"
        f"  기대: 'KRX' (사이클 13 Phase G 영속 — nxt_tradable=False → KRX 강제)\n"
        f"  실제: '{result}'\n"
        f"  결함 가설: 사이클 13 Phase G silent 삭제 가설 → NXT 잔존 → KIS 거부 chain\n"
        f"  영속 의무: src/engine/order_engine.py::_strategy_exchange_async (L128~197) 영속\n"
        f"  명세 영속: _workspace/red/cycle100_ui_prefix_fix_market_branching_persistence.md"
    )


def test_g_mkt1_strategy_exchange_async_called_in_execute_buy():
    """G-MKT1-B: AST 정적 가드 — `execute_buy` 또는 매수 hot path 영역에 `_strategy_exchange_async` 호출 영속 (HIGH).

    Red 상태 (사이클 100): 영역 영속 확인 가드 — 사이클 13 silent 삭제 가설 영구 차단.

    Green: 사이클 13 Phase G 영속 = production 변경 0 → 영속 가드 PASS.

    영속 의무:
    - `_strategy_exchange_async` 정의 영속 (사이클 13)
    - `execute_buy` 본체 영역 호출 영속
    - 미래 backend-dev 가 매수 영역 호출 silent 삭제 영구 차단
    """
    source = _order_engine_module_source()

    # 가드 1: `_strategy_exchange_async` 정의 영속 (사이클 13)
    tree = ast.parse(source)
    found_definition = False
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "_strategy_exchange_async":
            found_definition = True
            break
    assert found_definition, (
        "\n사이클 100 G-MKT1-B Red 상태 — `_strategy_exchange_async` 함수 부재.\n"
        "  Green: 사이클 13 Phase G 영속 = src/engine/order_engine.py::_strategy_exchange_async (L128~197) 영속 의무.\n"
        "  명세 영속: _workspace/red/cycle100_ui_prefix_fix_market_branching_persistence.md"
    )

    # 가드 2: `execute_buy` 본체 영역에 `_strategy_exchange_async` 호출 영속 영역 grep
    execute_buy_body = None
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "execute_buy":
            execute_buy_body = ast.get_source_segment(source, node)
            break

    assert execute_buy_body is not None, (
        "\n사이클 100 G-MKT1-B Red 상태 — `execute_buy` 함수 부재.\n"
        "  영속 의무: src/engine/order_engine.py::execute_buy 영속"
    )

    # `execute_buy` 본체 또는 매수 hot path 영역에 `_strategy_exchange_async` 호출 ≥1건 영속
    # (사이클 13 영속 = `_strategy_exchange_async(strategy_id, ticker=ticker)` 영역 영속)
    assert "_strategy_exchange_async" in execute_buy_body, (
        f"\n사이클 100 G-MKT1-B 위반 — `execute_buy` 본체 영역 `_strategy_exchange_async` 호출 영속 위반:\n"
        f"  기대: execute_buy 본체 영역 _strategy_exchange_async 호출 ≥1건 영속 (사이클 13 영속)\n"
        f"  실제: execute_buy 본체 영역 호출 0건\n"
        f"  결함 가설: 사이클 13 Phase G silent 삭제 → 매수 진입 영역 NXT 사전 차단 무효화\n"
        f"  영속 의무: src/engine/order_engine.py::execute_buy 매수 hot path 영역 영속\n"
        f"  명세 영속: _workspace/red/cycle100_ui_prefix_fix_market_branching_persistence.md"
    )
