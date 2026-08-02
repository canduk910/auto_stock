"""사이클 H Red — `GET /api/portfolio/risk` 라우트 스키마 + graceful 200.

명세: `_workspace/cycleH_portfolio_risk_phase1_spec.md` §2 + §TDD (c).
Red 메모: `_workspace/red/cycleH_portfolio_risk.md`.

대상: `src.routes.portfolio.get_portfolio_risk() -> ApiResponse`.
- 핸들러: `trading_scheduler.registry.all()` + `get_balance()` summary.net_asset +
  전략별 `extract_hard_stop_pct` + 보유 ticker 합집합 → stock_master master_raw →
  `_kojiro_sector_key` sector_of 빌드 → `compute_portfolio_risk_snapshot` → ApiResponse.
- graceful: get_balance/stock_master 실패 → net_asset=0 / 섹터 미분류로 **200 + 스냅샷**
  (500 금지 — 관찰성 실패가 운영 화면 죽이면 안 됨).

검증 패턴: TestClient 지양, 라우트 함수 직접 await (사이클 127 anyio portal hang 차단).
라우트가 소비하는 seam(get_balance / trading_scheduler / stock_master)을 라우트 모듈
네임스페이스에서 monkeypatch — backend-dev 는 이 이름들을 module-level 로 import 할 것.

RED 상태: `src.routes.portfolio` 모듈 부재 → ImportError 로 전 케이스 실패.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.engine.strategy_base import Position, StrategyState

pytestmark = pytest.mark.unit


def _pos(ticker: str, buy_price: int, quantity: int, strategy_id: str) -> Position:
    return Position(
        ticker=ticker,
        buy_price=buy_price,
        quantity=quantity,
        order_no=f"ORD-{ticker}",
        strategy_id=strategy_id,
    )


def _strategy(strategy_id: str, params: dict, positions: list[Position]):
    """registry.all() 원소 대역 — config.params + params 양쪽 노출(호출측 규약 미결정 대비)."""
    state = StrategyState(strategy_id=strategy_id)
    for p in positions:
        state.positions[p.ticker] = p
    config = SimpleNamespace(strategy_id=strategy_id, params=params)
    return SimpleNamespace(
        strategy_id=strategy_id,
        params=params,
        config=config,
        state=state,
    )


def _install_fakes(monkeypatch, *, balance_raises=False, net_asset=1_000_000,
                   stock_master_raises=False):
    """라우트 모듈 seam 을 fake 로 교체. 반환: portfolio 라우트 모듈."""
    from src.routes import portfolio as pf

    strategies = [
        _strategy(
            "donchian_swing",
            {"stop_loss_rate": -7.0, "turtle_backstop_pct": -9.0},
            [_pos("005930", 10_000, 10, "donchian_swing")],
        ),
        _strategy(
            "kojiro",
            {"hard_stop_pct": -8.0},
            [_pos("051910", 40_000, 2, "kojiro")],
        ),
        _strategy("momentum", {"stop_loss_rate": -7.5}, []),
    ]

    fake_registry = SimpleNamespace(all=lambda: strategies)
    monkeypatch.setattr(
        pf, "trading_scheduler", SimpleNamespace(registry=fake_registry), raising=False
    )

    async def _fake_get_balance(afhr_flpr: str = "N"):
        if balance_raises:
            raise RuntimeError("KIS 잔고 조회 일시 장애")
        return ([], SimpleNamespace(net_asset=net_asset))

    monkeypatch.setattr(pf, "get_balance", _fake_get_balance, raising=False)

    async def _fake_master_get(ticker: str):
        if stock_master_raises:
            raise RuntimeError("stock_master 조회 실패")
        return None  # master_raw 미확보 → _kojiro_sector_key 가 미분류-{ticker}

    monkeypatch.setattr(
        pf, "stock_master", SimpleNamespace(get=_fake_master_get), raising=False
    )
    return pf


# ===========================================================================
# (c) 정상 응답 스키마
# ===========================================================================
@pytest.mark.asyncio
async def test_route_returns_snapshot_schema(monkeypatch):
    pf = _install_fakes(monkeypatch, net_asset=1_000_000)

    resp = await pf.get_portfolio_risk()

    assert resp.success is True
    data = resp.data
    assert isinstance(data, dict)
    for key in (
        "total_notional_won",
        "total_open_risk_won",
        "open_risk_pct_of_net",
        "concurrent_positions",
        "by_strategy",
        "by_sector",
        "top_sector",
    ):
        assert key in data, f"스냅샷 스키마 키 누락: {key}"

    # 보유 2건 (donchian 1 + kojiro 1), momentum 0 포지션
    assert data["concurrent_positions"] == 2
    # by_strategy 는 0 포지션 전략도 포함
    assert set(data["by_strategy"].keys()) == {"donchian_swing", "kojiro", "momentum"}
    assert data["by_strategy"]["momentum"]["positions"] == 0


# ===========================================================================
# (c) graceful 200 — get_balance 실패
# ===========================================================================
@pytest.mark.asyncio
async def test_route_graceful_when_balance_fails(monkeypatch):
    """get_balance 실패 → net_asset=0 로 200 + 스냅샷 (500 금지)."""
    pf = _install_fakes(monkeypatch, balance_raises=True)

    resp = await pf.get_portfolio_risk()

    assert resp.success is True, "get_balance 실패해도 success=True (graceful)"
    data = resp.data
    assert isinstance(data, dict)
    # net_asset 미확보 → pct 0.0
    assert data["open_risk_pct_of_net"] == 0.0
    # 스냅샷 자체는 여전히 빌드 (리스크/보유 집계 보존)
    assert data["concurrent_positions"] == 2


# ===========================================================================
# (c) graceful 200 — stock_master 실패 (섹터 미분류 폴백)
# ===========================================================================
@pytest.mark.asyncio
async def test_route_graceful_when_stock_master_fails(monkeypatch):
    """stock_master.get 실패 → 섹터 미분류 폴백으로 200 (섹터 분류 실패가 화면 죽이면 안 됨)."""
    pf = _install_fakes(monkeypatch, stock_master_raises=True, net_asset=1_000_000)

    resp = await pf.get_portfolio_risk()

    assert resp.success is True
    data = resp.data
    assert data["concurrent_positions"] == 2
    # 미분류 폴백 — by_sector 는 미분류 섹터로 채워짐 (거짓 클러스터 인플레 차단)
    assert all(k.startswith("미분류-") for k in data["by_sector"].keys()), (
        "stock_master 실패 시 전 섹터 미분류-{ticker} 폴백"
    )


# ===========================================================================
# (c) 빈 registry / 보유 0 → 0 스냅샷 200
# ===========================================================================
@pytest.mark.asyncio
async def test_route_empty_registry_zero_snapshot(monkeypatch):
    from src.routes import portfolio as pf

    monkeypatch.setattr(
        pf, "trading_scheduler",
        SimpleNamespace(registry=SimpleNamespace(all=lambda: [])),
        raising=False,
    )

    async def _fake_get_balance(afhr_flpr: str = "N"):
        return ([], SimpleNamespace(net_asset=1_000_000))

    monkeypatch.setattr(pf, "get_balance", _fake_get_balance, raising=False)

    async def _fake_master_get(ticker: str):
        return None

    monkeypatch.setattr(
        pf, "stock_master", SimpleNamespace(get=_fake_master_get), raising=False
    )

    resp = await pf.get_portfolio_risk()
    assert resp.success is True
    data = resp.data
    assert data["concurrent_positions"] == 0
    assert data["total_open_risk_won"] == 0
    assert data["top_sector"] is None
