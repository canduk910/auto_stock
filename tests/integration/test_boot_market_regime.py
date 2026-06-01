"""사이클 2 — `_boot()` 가 매크로 fetch + snapshot INSERT + cash_usage_ratio 자동 조정.

요구 행위:
1. `_boot()` 안에서 `refresh_from_dkstock()` 호출 → `set_current_regime()` 갱신.
2. defensive regime + auto_regime_adjust=true 시 `cash_usage_ratio = 0.25` 자동 갱신.
3. 자동 갱신된 ratio 로 `registry.allocate_funds(net_asset × ratio)` 호출.
4. `market_regime_snapshots` INSERT 호출 (UNIQUE 충돌은 graceful).
5. `auto_regime_adjust=false` 면 운영자 수동 ratio 그대로 사용.
6. dkstock fetch 실패 시 empty regime → 수동 ratio 그대로.

기존 `test_boot_cash_usage_ratio.py` 패턴 재사용.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.models.balance import AccountSummary

pytestmark = pytest.mark.integration


@pytest.fixture
def boot_env_regime(scheduler_env, monkeypatch: pytest.MonkeyPatch):
    """`_boot()` 핵심 의존성 모킹 (test_boot_cash_usage_ratio 와 동일 구조)."""
    sched = scheduler_env.scheduler

    allocated: list[int] = []
    orig_allocate = sched.registry.allocate_funds

    def fake_allocate(total_asset):
        allocated.append(total_asset)
        orig_allocate(total_asset)

    monkeypatch.setattr(sched.registry, "allocate_funds", fake_allocate)

    async def fake_get_token():
        return "TOKEN"

    monkeypatch.setattr(
        "src.engine.boot_manager.token_manager", SimpleNamespace(get_token=fake_get_token)
    )

    # _preissue_all_tokens 는 src.auth.token 을 fresh import 하므로
    # 인스턴스 메서드 자체를 no-op 으로 치환 (토큰 캐시 만료 환경 의존 차단)
    async def fake_preissue():
        return None

    monkeypatch.setattr(sched, "_preissue_all_tokens", fake_preissue)

    async def fake_load_strategy_config():
        return None

    monkeypatch.setattr(sched, "_load_strategy_config", fake_load_strategy_config)

    async def fake_get_balance():
        summary = AccountSummary(
            deposit=10_000_000, stock_eval_amount=0, total_eval_amount=10_000_000,
            net_asset=10_000_000, purchase_total=0, eval_total=0, profit_loss_total=0,
        )
        return [], summary

    monkeypatch.setattr("src.engine.boot_manager.get_balance", fake_get_balance)

    for s in sched.registry.all():
        async def _noop_prepare():
            return None
        monkeypatch.setattr(s, "prepare", _noop_prepare)

    async def fake_load_all():
        return []

    monkeypatch.setattr("src.db.positions.load_all", fake_load_all)

    async def fake_get_daily_orders():
        return []

    monkeypatch.setattr("src.engine.boot_manager.get_daily_orders", fake_get_daily_orders)

    async def fake_sync_orders_to_db(_orders):
        return None

    monkeypatch.setattr(sched, "_sync_orders_to_db", fake_sync_orders_to_db)

    async def fake_eager_refresh():
        return None

    monkeypatch.setattr(sched, "_eager_refresh_stock_master_for_held_positions", fake_eager_refresh)

    class _Q:
        def select(self, *_): return self
        def eq(self, *_): return self
        def gte(self, *_): return self
        def order(self, *_, **__): return self
        def limit(self, *_): return self
        def update(self, *_): return self
        def execute(self):
            return SimpleNamespace(data=[])

    class _Tbl:
        def __init__(self, *_): pass
        def select(self, *_): return _Q()
        def eq(self, *_): return _Q()
        def update(self, *_): return _Q()
        def insert(self, *_): return _Q()
        def upsert(self, *_, **__): return _Q()

    monkeypatch.setattr(
        "src.db.trade_history.supabase",
        SimpleNamespace(table=lambda _name: _Tbl()),
    )
    # market_regime_snapshots INSERT 도 graceful no-op
    snapshot_calls: list[dict] = []

    async def fake_persist_snapshot(regime, target_date):
        snapshot_calls.append(
            {
                "regime": regime.regime,
                "date": target_date,
                "buy_blocked": regime.buy_blocked,
            }
        )

    monkeypatch.setattr(
        "src.engine.market_regime.persist_snapshot", fake_persist_snapshot
    )

    return SimpleNamespace(
        scheduler=sched, allocated=allocated, snapshot_calls=snapshot_calls,
    )


@pytest.mark.asyncio
async def test_boot_defensive_regime_auto_adjusts_cash_usage_ratio(
    boot_env_regime, monkeypatch
):
    """B5-A: defensive regime + auto_regime_adjust=true 시 ratio 자동 갱신.

    cash_min=75 → ratio=0.25. allocate_funds(10_000_000 × 0.25 = 2_500_000) 호출 확인.
    """
    from src.engine.market_regime import MarketRegime

    sched = boot_env_regime.scheduler

    # refresh_from_dkstock 가 defensive regime 반환
    async def fake_refresh():
        return MarketRegime(
            regime="defensive",
            regime_desc="방어 (공포 현금)",
            cycle_phase="expansion",
            vix=18.43,
            fear_greed_score=76.0,
            buffett_ratio=254.2,
            cash_min=75,
            raw={"regime": {"regime": "defensive"}},
        )

    monkeypatch.setattr("src.engine.market_regime.refresh_from_dkstock", fake_refresh)

    # auto_regime_adjust=True (기본)
    async def fake_get_auto():
        return True
    monkeypatch.setattr("src.db.system_config.get_auto_regime_adjust", fake_get_auto)

    # cash_usage_ratio 운영자 수동값 (사용 안 됨 — 자동 갱신이 우선)
    async def fake_get_ratio():
        return 1.0
    monkeypatch.setattr("src.engine.scheduler.get_cash_usage_ratio", fake_get_ratio)

    # set_cash_usage_ratio 호출 추적 (DB 저장 시뮬)
    set_calls: list[float] = []
    async def fake_set_ratio(r):
        set_calls.append(r)
    monkeypatch.setattr("src.db.system_config.set_cash_usage_ratio", fake_set_ratio)

    await sched._boot()

    # allocate_funds 인자 = 10_000_000 × 0.25 = 2_500_000
    assert boot_env_regime.allocated == [2_500_000]
    # DB 저장도 동일 비율
    assert any(abs(v - 0.25) < 0.01 for v in set_calls)
    # snapshot INSERT 호출됨
    assert len(boot_env_regime.snapshot_calls) == 1
    assert boot_env_regime.snapshot_calls[0]["regime"] == "defensive"
    assert boot_env_regime.snapshot_calls[0]["buy_blocked"] is True


@pytest.mark.asyncio
async def test_boot_auto_adjust_false_preserves_manual_ratio(
    boot_env_regime, monkeypatch
):
    """B5-B: auto_regime_adjust=false 시 레짐 무관 수동 ratio 사용."""
    from src.engine.market_regime import MarketRegime

    sched = boot_env_regime.scheduler

    async def fake_refresh():
        return MarketRegime(regime="defensive", cash_min=75, vix=20.0, fear_greed_score=50.0)
    monkeypatch.setattr("src.engine.market_regime.refresh_from_dkstock", fake_refresh)

    async def fake_get_auto():
        return False  # 수동 모드
    monkeypatch.setattr("src.db.system_config.get_auto_regime_adjust", fake_get_auto)

    async def fake_get_ratio():
        return 0.7  # 운영자 수동값
    monkeypatch.setattr("src.engine.scheduler.get_cash_usage_ratio", fake_get_ratio)

    set_calls: list[float] = []
    async def fake_set_ratio(r):
        set_calls.append(r)
    monkeypatch.setattr("src.db.system_config.set_cash_usage_ratio", fake_set_ratio)

    await sched._boot()

    # 수동값 0.7 적용 → 7_000_000
    assert boot_env_regime.allocated == [7_000_000]
    # 자동 갱신 호출 없음
    assert set_calls == []


@pytest.mark.asyncio
async def test_boot_dkstock_fetch_failure_uses_manual_ratio(
    boot_env_regime, monkeypatch
):
    """B5-C: dkstock fetch 실패 (empty regime) 시 수동 ratio 그대로."""
    from src.engine.market_regime import MarketRegime

    sched = boot_env_regime.scheduler

    async def fake_refresh():
        return MarketRegime.empty()  # 외부 실패 폴백
    monkeypatch.setattr("src.engine.market_regime.refresh_from_dkstock", fake_refresh)

    async def fake_get_auto():
        return True
    monkeypatch.setattr("src.db.system_config.get_auto_regime_adjust", fake_get_auto)

    async def fake_get_ratio():
        return 0.85
    monkeypatch.setattr("src.engine.scheduler.get_cash_usage_ratio", fake_get_ratio)

    set_calls: list[float] = []
    async def fake_set_ratio(r):
        set_calls.append(r)
    monkeypatch.setattr("src.db.system_config.set_cash_usage_ratio", fake_set_ratio)

    await sched._boot()

    # 수동값 0.85 → 8_500_000
    assert boot_env_regime.allocated == [8_500_000]
    # 자동 갱신 호출 없음 (empty 레짐 → computed_cash_usage_ratio() None)
    assert set_calls == []
    # snapshot INSERT 호출되었으나 empty regime 은 persist_snapshot 내부에서 skip
    # (monkeypatch 대체된 fake_persist_snapshot 은 모든 호출 추적)
    # → fake_persist_snapshot 호출 1번이지만 regime.regime is None
    assert len(boot_env_regime.snapshot_calls) == 1
    assert boot_env_regime.snapshot_calls[0]["regime"] is None
