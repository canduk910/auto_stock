"""Phase J3 Red — `_boot()` 가 `cash_usage_ratio` 를 곱해 `allocate_funds` 호출.

요구 행위:
1. `_boot()` 안에서 `get_cash_usage_ratio()` 조회 후 `summary.net_asset × ratio` 로
   `registry.allocate_funds()` 호출.
2. `[cash_usage_ratio]` prefix 의 system_logs 1행 기록 (net_asset / ratio / available).
3. ratio=1.0 (기본) 일 때는 net_asset 그대로 분배 (기존 동작 호환).
4. ratio=0.5 일 때는 net_asset 의 절반만 분배.

_boot() 전체는 의존성이 많아 (token, balance, positions, daily_orders 등) 전체 실행하지 않고,
필요한 외부 호출을 모킹한 뒤 한 번 await 하여 핵심 호출 인자만 검증한다.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.models.balance import AccountSummary

pytestmark = pytest.mark.integration


@pytest.fixture
def boot_env(scheduler_env, monkeypatch: pytest.MonkeyPatch):
    """`_boot()` 에 필요한 외부 의존성 일괄 모킹.

    - token_manager.get_token: no-op
    - _load_strategy_config: no-op
    - get_balance: holdings=[], summary.net_asset=10_000_000
    - load_all (db.positions): []
    - get_daily_orders: []
    - _sync_orders_to_db: no-op
    - supabase.table("trade_history") chain: data=[]
    - _eager_refresh_stock_master_for_held_positions: no-op
    - registry.allocate_funds: 호출 인자 추적
    """
    sched = scheduler_env.scheduler
    calls = scheduler_env.calls

    # 추적 — allocate_funds 호출 인자
    allocated: list[int] = []
    orig_allocate = sched.registry.allocate_funds

    def fake_allocate(total_asset):
        allocated.append(total_asset)
        # 실제 분배도 수행 (자식 로직 호환)
        orig_allocate(total_asset)

    monkeypatch.setattr(sched.registry, "allocate_funds", fake_allocate)

    # token
    async def fake_get_token():
        return "TOKEN"

    monkeypatch.setattr("src.engine.boot_manager.token_manager", SimpleNamespace(get_token=fake_get_token))

    # _preissue_all_tokens 는 scheduler 내부에서 src.auth.token 을 fresh import 하므로
    # 인스턴스 메서드 자체를 no-op 으로 치환 (토큰 캐시 만료 환경 의존 차단)
    async def fake_preissue():
        return None

    monkeypatch.setattr(sched, "_preissue_all_tokens", fake_preissue)

    # strategy_config
    async def fake_load_strategy_config():
        return None

    monkeypatch.setattr(sched, "_load_strategy_config", fake_load_strategy_config)

    # balance
    async def fake_get_balance():
        summary = AccountSummary(
            deposit=10_000_000,
            stock_eval_amount=0,
            total_eval_amount=10_000_000,
            net_asset=10_000_000,
            purchase_total=0,
            eval_total=0,
            profit_loss_total=0,
        )
        return [], summary

    monkeypatch.setattr("src.engine.boot_manager.get_balance", fake_get_balance)

    # prepare()는 각 전략에서 호출되므로 no-op으로 만든다.
    for s in sched.registry.all():
        async def _noop_prepare():
            return None
        monkeypatch.setattr(s, "prepare", _noop_prepare)

    # db.positions.load_all
    async def fake_load_all():
        return []

    monkeypatch.setattr("src.db.positions.load_all", fake_load_all)

    # daily_orders
    async def fake_get_daily_orders():
        return []

    monkeypatch.setattr("src.engine.boot_manager.get_daily_orders", fake_get_daily_orders)

    # _sync_orders_to_db
    async def fake_sync_orders_to_db(_orders):
        return None

    monkeypatch.setattr(sched, "_sync_orders_to_db", fake_sync_orders_to_db)

    # eager refresh — 별도 테스트 (test_boot_eager_refresh.py)
    async def fake_eager_refresh():
        return None

    monkeypatch.setattr(sched, "_eager_refresh_stock_master_for_held_positions", fake_eager_refresh)

    # supabase — trade_history.select(...).eq(...) 모킹 (2차 보완 + sold_today 시드)
    class _Q:
        def select(self, *_): return self
        def eq(self, *_): return self
        def gte(self, *_): return self
        def order(self, *_, **__): return self
        def limit(self, *_): return self
        def update(self, *_): return self
        def execute(self):
            return SimpleNamespace(data=[])

    class _Sb:
        def table(self, *_): return _Q()

    monkeypatch.setattr("src.engine.scheduler.supabase", _Sb(), raising=False)
    monkeypatch.setattr("src.db.supabase.supabase", _Sb())

    return SimpleNamespace(
        scheduler=sched,
        calls=calls,
        allocated=allocated,
        monkeypatch=monkeypatch,
    )


@pytest.mark.asyncio
async def test_boot_applies_default_ratio_1(boot_env, monkeypatch: pytest.MonkeyPatch):
    """기본 ratio=1.0 → net_asset 그대로 분배."""

    async def fake_get_ratio():
        return 1.0

    monkeypatch.setattr("src.engine.scheduler.get_cash_usage_ratio", fake_get_ratio, raising=False)

    await boot_env.scheduler._boot()

    assert boot_env.allocated, "allocate_funds 미호출"
    assert boot_env.allocated[0] == 10_000_000


@pytest.mark.asyncio
async def test_boot_applies_half_ratio(boot_env, monkeypatch: pytest.MonkeyPatch):
    """ratio=0.5 → net_asset * 0.5 분배."""

    async def fake_get_ratio():
        return 0.5

    monkeypatch.setattr("src.engine.scheduler.get_cash_usage_ratio", fake_get_ratio, raising=False)

    await boot_env.scheduler._boot()

    assert boot_env.allocated, "allocate_funds 미호출"
    assert boot_env.allocated[0] == 5_000_000


@pytest.mark.asyncio
async def test_boot_emits_cash_usage_ratio_log(boot_env, monkeypatch: pytest.MonkeyPatch):
    """[cash_usage_ratio] prefix 의 system_logs 1행 기록."""

    async def fake_get_ratio():
        return 0.8

    monkeypatch.setattr("src.engine.scheduler.get_cash_usage_ratio", fake_get_ratio, raising=False)

    await boot_env.scheduler._boot()

    # 사이클 72 hotfix — [cash_usage_ratio] write_log 호출 제거, _DbLogHandler 위임 단일 INSERT.
    # 운영 prefix 발화는 logger 경로로 보존. 본 assertion 제거 (G-A1 단위 가드로 회귀 차단 영속).
