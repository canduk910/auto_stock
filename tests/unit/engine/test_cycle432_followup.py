"""cycle432 — cycle428(F-422-1) 후속 LOW 2건.

(a) `selling_reconcile.reconcile_selling_unknown_one` — 180초 뒤 그 종목이
    이미 `order_engine._selling` 에 없으면(체결통보가 먼저 풀었음) 판정하지
    않는다. `result=already_released` 로 마커 1행만 남기고 반환한다. KIS
    조회도 하지 않는다. 지금까지는 이 경우 `not_accepted` 로 잘못 기록됐다
    (조회까지 한 뒤에).

(b) `order_engine.SELL_UNKNOWN_RECONCILE_DELAY_S` 와
    `selling_reconcile.SELLING_RECONCILE_MIN_AGE_S` 는 **값**이 같다(180.0).
    `order_engine.py` 가 `selling_reconcile` 을 모듈 최상단에서 import 하면
    "top-level src import 증가분은 `llm_buy_gate` 1건뿐" 구조 가드 4종
    (cycle276·286·287·291 사본)이 붉어지므로 object identity 가 아니라 값
    동일성으로 묶는다. `scheduler.py` 의 같은 이름 상수도 이번 사이클 승인
    범위 밖이라 별도 리터럴이다 — 세 곳 모두 180 이면 값이 맞다.
"""
from __future__ import annotations

import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

pytestmark = pytest.mark.unit

_T = "005930"
_SID = "kojiro"


def _recs(caplog, level: int, prefix: str) -> list[str]:
    return [
        r.getMessage() for r in caplog.records
        if r.levelno == level and r.getMessage().startswith(prefix)
    ]


# ---------------------------------------------------------------------------
# (a) already_released — 0 조회
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_already_released_skips_kis_query_entirely(monkeypatch, caplog):
    import src.api.balance as bal
    from src.engine.selling_reconcile import reconcile_selling_unknown_one

    caplog.set_level(logging.DEBUG, logger="src.engine.scheduler")
    get_balance = AsyncMock(side_effect=AssertionError("KIS 조회 — 호출되면 안 된다"))
    get_daily_orders = AsyncMock(side_effect=AssertionError("KIS 조회 — 호출되면 안 된다"))
    monkeypatch.setattr(bal, "get_balance", get_balance)
    monkeypatch.setattr(bal, "get_daily_orders", get_daily_orders)

    eng = SimpleNamespace(_selling=set(), _selling_since={})  # 이미 체결통보가 풀었다

    result = await reconcile_selling_unknown_one(eng, _T, _SID, min_age_s=180.0)

    assert result == "already_released"
    get_balance.assert_not_called()
    get_daily_orders.assert_not_called()
    rows = _recs(caplog, logging.WARNING, "[sell_send_unknown_resolved] ")
    assert rows == [
        f"[sell_send_unknown_resolved] ticker={_T} strategy={_SID} result=already_released"
    ]


@pytest.mark.asyncio
async def test_still_selling_goes_through_normal_lookup(monkeypatch, caplog):
    """대조 — `_selling` 에 아직 있으면 평소대로 조회한다(변경 없음)."""
    import src.api.balance as bal
    from src.engine.selling_reconcile import reconcile_selling_unknown_one

    caplog.set_level(logging.DEBUG, logger="src.engine.scheduler")
    get_balance = AsyncMock(return_value=([], SimpleNamespace(net_asset=0)))
    get_daily_orders = AsyncMock(return_value=[])
    monkeypatch.setattr(bal, "get_balance", get_balance)
    monkeypatch.setattr(bal, "get_daily_orders", get_daily_orders)

    eng = SimpleNamespace(_selling={_T}, _selling_since={})

    result = await reconcile_selling_unknown_one(eng, _T, _SID, min_age_s=180.0)

    assert result == "closed"  # 보유 0 → held_zero → closed
    get_balance.assert_awaited_once()
    get_daily_orders.assert_awaited_once()


# ---------------------------------------------------------------------------
# (b) 두 상수는 값이 같다(top-level import 증가분 가드 때문에 identity 는
#     쓰지 않는다 — 위 모듈 docstring 참조)
# ---------------------------------------------------------------------------
def test_order_engine_delay_equals_selling_reconcile_min_age_by_value():
    from src.engine import order_engine, selling_reconcile

    assert order_engine.SELL_UNKNOWN_RECONCILE_DELAY_S == selling_reconcile.SELLING_RECONCILE_MIN_AGE_S
    assert order_engine.SELL_UNKNOWN_RECONCILE_DELAY_S == 180.0
    assert selling_reconcile.SELLING_RECONCILE_MIN_AGE_S == 180.0


def test_order_engine_has_no_new_top_level_import_of_selling_reconcile():
    """🔴 cycle432 — `selling_reconcile` 을 `order_engine.py` 최상단 import 에
    더하지 않는다(이미 함수 안 지연 import 로 쓰고 있다). 더하면
    `test_cycle276_ast_order_hook.py::test_c4_2_order_engine_src_imports_delta_is_one`
    외 cycle286·287·291 사본이 붉어진다."""
    import ast
    from pathlib import Path

    src = Path("src/engine/order_engine.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    top_level_modules = set()
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("src."):
            top_level_modules.add(node.module)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("src."):
                    top_level_modules.add(alias.name)
    assert "src.engine.selling_reconcile" not in top_level_modules, (
        "selling_reconcile 이 order_engine.py 최상단 import 에 들어갔다 — "
        "top-level src import 증가분 가드가 붉어진다"
    )
