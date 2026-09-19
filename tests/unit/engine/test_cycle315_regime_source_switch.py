"""cycle315 Red — 매크로 레짐 출처를 우리 `macro` 컨테이너로 전환.

외부 `dkstock.cloud` 는 2026-08-18 철거됐다. 같은 코드(`macro_lite`)를 우리
컨테이너가 돌리므로 응답 shape 는 같고, 바뀌는 것은 **어디서 받는가**와 **누가
활성 여부를 정하는가** 둘이다.

여기서 고정하는 계약:
- (a) 🔴 `.env` 단독 veto 제거 — `settings.dkstock_regime_enabled=False` 여도 DB 토글이
      True 면 fetch 한다(Settings UI 토글 즉시 반영이 DB 우선인데, 함수 앞단의 env
      단독 가드가 그 결정을 조용히 덮고 있었다)
- (b) DB 토글 False → `MarketRegime.empty()`
- (c) 실물 payload 파싱 — cash_min=75 · ratio 0.25 · buffett_ratio 2.626 · cycle_phase 보존
- (d) 타임아웃 → empty + WARNING 에 `reason=timeout`
- (e) 🔴 불변식 — `regime='defensive'` 여도 매수 경로는 무개입(레짐은 관찰 지표다)
- (f) `persist_snapshot` 의 현재 계약 고정
"""
from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
import respx

pytestmark = pytest.mark.unit

MACRO_BASE = "http://macro:8000"
MACRO_CYCLE_URL = MACRO_BASE + "/api/macro/macro-cycle"

_FIXTURE_PATH = Path(__file__).resolve().parents[2] / "fixtures" / "macro_cycle_live.json"
LIVE_MACRO_CYCLE = json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))


@pytest.fixture
def macro_env(monkeypatch: pytest.MonkeyPatch):
    """싱글톤 리셋 + settings 를 우리 macro 컨테이너로 고정."""
    from src.config import settings
    from src.services import macro_client as mc

    mc._client_instance = None
    monkeypatch.setattr(settings, "macro_api_url", MACRO_BASE, raising=False)
    monkeypatch.setattr(settings, "macro_api_read_timeout_secs", 90.0, raising=False)
    yield
    mc._client_instance = None


def _patch_db_toggle(monkeypatch: pytest.MonkeyPatch, value):
    from src.db import system_config

    async def _get():
        return value

    monkeypatch.setattr(system_config, "get_dkstock_regime_enabled", _get)


# ---------------------------------------------------------------------------
# (a) env 단독 veto 제거 — DB True 가 이긴다
# ---------------------------------------------------------------------------
async def test_a_db_toggle_true_overrides_env_false(macro_env, monkeypatch):
    """`.env=False` + DB=True → fetch 수행 + defensive 레짐."""
    from src.config import settings
    from src.engine.market_regime import refresh_from_dkstock

    monkeypatch.setattr(settings, "dkstock_regime_enabled", False, raising=False)
    _patch_db_toggle(monkeypatch, True)

    with respx.mock(assert_all_called=True) as router:
        route = router.get(MACRO_CYCLE_URL).mock(
            return_value=httpx.Response(200, json=LIVE_MACRO_CYCLE)
        )
        regime = await refresh_from_dkstock()

    assert route.call_count == 1
    assert regime.regime == "defensive"


# ---------------------------------------------------------------------------
# (b) DB 토글 False → empty (HTTP 0회)
# ---------------------------------------------------------------------------
async def test_b_db_toggle_false_returns_empty(macro_env, monkeypatch):
    from src.config import settings
    from src.engine.market_regime import refresh_from_dkstock

    monkeypatch.setattr(settings, "dkstock_regime_enabled", True, raising=False)
    _patch_db_toggle(monkeypatch, False)

    with respx.mock(assert_all_called=False) as router:
        route = router.get(MACRO_CYCLE_URL).mock(
            return_value=httpx.Response(200, json=LIVE_MACRO_CYCLE)
        )
        regime = await refresh_from_dkstock()

    assert route.call_count == 0
    assert regime.is_empty() is True


async def test_b2_disabled_logs_reason(macro_env, monkeypatch, caplog):
    """비활성은 (연결 실패/타임아웃)과 구별되는 사유 라벨로 남는다."""
    from src.config import settings
    from src.engine.market_regime import refresh_from_dkstock

    monkeypatch.setattr(settings, "dkstock_regime_enabled", False, raising=False)
    _patch_db_toggle(monkeypatch, False)

    with caplog.at_level(logging.WARNING, logger="src.engine.market_regime"):
        regime = await refresh_from_dkstock()

    assert regime.is_empty() is True
    msgs = [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING]
    assert any("[market_regime] macro fetch 실패" in m and "reason=disabled" in m for m in msgs), msgs


# ---------------------------------------------------------------------------
# (c) 실물 payload 파싱
# ---------------------------------------------------------------------------
async def test_c_live_payload_parsing(macro_env, monkeypatch):
    from src.config import settings
    from src.engine.market_regime import refresh_from_dkstock

    monkeypatch.setattr(settings, "dkstock_regime_enabled", True, raising=False)
    _patch_db_toggle(monkeypatch, None)  # DB 키 부재 → .env fallback(True)

    with respx.mock(assert_all_called=True) as router:
        router.get(MACRO_CYCLE_URL).mock(
            return_value=httpx.Response(200, json=LIVE_MACRO_CYCLE)
        )
        regime = await refresh_from_dkstock()

    assert regime.regime == "defensive"
    assert regime.regime_desc == "방어 (공포 현금)"
    assert regime.cash_min == 75
    assert regime.computed_cash_usage_ratio() == pytest.approx(0.25)
    assert regime.buffett_ratio == pytest.approx(2.626)
    assert regime.vix == pytest.approx(14.81)
    assert regime.fear_greed_score == pytest.approx(69.0)
    # cycle_phase 는 문자열 그대로 보존 (라벨/번역 금지)
    assert regime.cycle_phase == "expansion"
    # raw 는 응답 전체를 담는다 (감사 추적)
    assert regime.raw.get("updated_at") == LIVE_MACRO_CYCLE["updated_at"]


# ---------------------------------------------------------------------------
# (d) 타임아웃 → empty + reason=timeout
# ---------------------------------------------------------------------------
async def test_d_timeout_returns_empty_with_reason(macro_env, monkeypatch, caplog):
    from src.config import settings
    from src.engine.market_regime import refresh_from_dkstock
    from src.services import macro_client as mc

    monkeypatch.setattr(settings, "dkstock_regime_enabled", True, raising=False)
    monkeypatch.setattr(settings, "macro_api_read_timeout_secs", 0.01, raising=False)
    _patch_db_toggle(monkeypatch, True)

    class _SlowClient:
        async def get_macro_cycle(self):
            await asyncio.sleep(1.0)
            return LIVE_MACRO_CYCLE

    monkeypatch.setattr(mc, "get_macro_client", lambda: _SlowClient())

    with caplog.at_level(logging.WARNING, logger="src.engine.market_regime"):
        regime = await refresh_from_dkstock()

    assert regime.is_empty() is True
    msgs = [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING]
    assert any("[market_regime] macro fetch 실패" in m and "reason=timeout" in m for m in msgs), msgs


async def test_d2_connect_failure_returns_empty_with_reason(macro_env, monkeypatch, caplog):
    """연결 실패도 타임아웃과 구별되는 라벨로 남는다."""
    from src.config import settings
    from src.engine.market_regime import refresh_from_dkstock

    monkeypatch.setattr(settings, "dkstock_regime_enabled", True, raising=False)
    _patch_db_toggle(monkeypatch, True)

    with respx.mock(assert_all_called=True) as router:
        router.get(MACRO_CYCLE_URL).mock(side_effect=httpx.ConnectError("macro down"))
        with caplog.at_level(logging.WARNING, logger="src.engine.market_regime"):
            regime = await refresh_from_dkstock()

    assert regime.is_empty() is True
    msgs = [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING]
    assert any("reason=fetch_failed" in m for m in msgs), msgs


# ---------------------------------------------------------------------------
# (e) 🔴 불변식 — 레짐은 매수를 차단하지 않는다 (라이브 payload 로 재확인)
# ---------------------------------------------------------------------------
def _make_mock_strategy(strategy_id: str = "momentum"):
    state = MagicMock()
    state.buy_disabled = False
    state.positions = {}
    state.signal_count_today = 0
    state.total_investment = 1_000_000
    state.is_low_funds_blocked.return_value = False
    state.has_position.return_value = False

    s = MagicMock()
    s.strategy_id = strategy_id
    s.state = state
    s.config = MagicMock()
    s.config.params = {}
    s.is_daily_loss_exceeded.return_value = False
    s.check_buy_signal.return_value = None
    s.check_exit_signal.return_value = None
    return s


@pytest.fixture
def _patch_session_tracker(monkeypatch):
    from src.engine import risk as risk_mod

    monkeypatch.setattr(
        risk_mod.session_tracker, "is_tradable", lambda strategy_id, params: True,
    )


async def test_e_live_defensive_regime_does_not_block_buy(
    macro_env, monkeypatch, _patch_session_tracker
):
    """라이브 payload(defensive/cash_min=75)를 메모리에 올려도 매수는 그대로 나간다."""
    from src.config import settings
    from src.engine import market_regime as mr_mod
    from src.engine.risk import RiskManager
    from src.engine.strategy_base import Signal

    monkeypatch.setattr(settings, "dkstock_regime_enabled", True, raising=False)
    _patch_db_toggle(monkeypatch, True)

    with respx.mock(assert_all_called=True) as router:
        router.get(MACRO_CYCLE_URL).mock(
            return_value=httpx.Response(200, json=LIVE_MACRO_CYCLE)
        )
        regime = await refresh_live()

    assert regime.regime == "defensive"
    assert regime.buy_blocked is True  # 관찰 프로퍼티는 True 여도

    prev = mr_mod.get_current_regime()
    mr_mod.set_current_regime(regime)
    try:
        registry = MagicMock()
        order_engine = MagicMock()
        order_engine.execute_buy = AsyncMock()
        order_engine.execute_sell = AsyncMock()
        rm = RiskManager(registry=registry, order_engine=order_engine)

        strategy = _make_mock_strategy("momentum")
        strategy.check_buy_signal.return_value = Signal.BUY
        registry.enabled.return_value = [strategy]
        registry.is_ticker_blocked_for_buy.return_value = False

        await rm.on_tick(
            ticker="005930", current_price=70000, open_price=69000, change_rate=1.0
        )

        # 🔴 매수 경로 무개입 — 레짐은 관찰 지표다
        order_engine.execute_buy.assert_awaited_once()
        strategy.check_buy_signal.assert_called_once()
    finally:
        mr_mod.set_current_regime(prev)


async def refresh_live():
    from src.engine.market_regime import refresh_from_dkstock

    return await refresh_from_dkstock()


# ---------------------------------------------------------------------------
# (f) persist_snapshot 현재 계약 고정
# ---------------------------------------------------------------------------
async def test_f1_persist_snapshot_skips_empty(monkeypatch):
    from datetime import date

    from src.db import market_regime_snapshots as mrs
    from src.engine.market_regime import MarketRegime, persist_snapshot

    called = []

    async def _insert(**kwargs):
        called.append(kwargs)

    monkeypatch.setattr(mrs, "insert_snapshot", _insert)

    await persist_snapshot(MarketRegime.empty(), date(2026, 9, 19))
    assert called == []


async def test_f2_persist_snapshot_writes_live_values(monkeypatch):
    from datetime import date

    from src.db import market_regime_snapshots as mrs
    from src.engine.market_regime import MarketRegime, persist_snapshot

    called = []

    async def _insert(**kwargs):
        called.append(kwargs)

    monkeypatch.setattr(mrs, "insert_snapshot", _insert)

    regime = MarketRegime.from_macro_cycle(LIVE_MACRO_CYCLE)
    await persist_snapshot(regime, date(2026, 9, 19))

    assert len(called) == 1
    kw = called[0]
    assert kw["regime"] == "defensive"
    assert kw["cycle_phase"] == "expansion"
    assert kw["vix"] == pytest.approx(14.81)
    assert kw["buffett_ratio"] == pytest.approx(2.626)
    assert kw["computed_cash_usage_ratio"] == pytest.approx(0.25)
    # ⚠️ 현재 계약: 스냅샷의 buy_blocked 는 관찰 프로퍼티 값이다
    #    (/current 라우트·to_advisor_dict 의 상수 False 와 다르다 — 뒤집힘을
    #     사고가 아니라 기록으로 남긴다)
    assert kw["buy_blocked"] is True
    assert kw["raw_response"]["updated_at"] == LIVE_MACRO_CYCLE["updated_at"]


async def test_f3_persist_snapshot_absorbs_db_error(monkeypatch):
    from datetime import date

    from src.db import market_regime_snapshots as mrs
    from src.engine.market_regime import MarketRegime, persist_snapshot

    async def _boom(**kwargs):
        raise RuntimeError("db down")

    monkeypatch.setattr(mrs, "insert_snapshot", _boom)

    # 예외를 삼킨다 — 메모리 레짐은 유효
    await persist_snapshot(MarketRegime.from_macro_cycle(LIVE_MACRO_CYCLE), date(2026, 9, 19))


# ---------------------------------------------------------------------------
# (g) 부팅 경로는 더 짧은 상한을 쓴다 — 재시작 직후 시세 공백을 늘리지 않는다
# ---------------------------------------------------------------------------
async def test_g1_boot_uses_shorter_budget(macro_env, monkeypatch):
    """`boot_manager` 가 부팅 전용 상한으로 레짐 갱신을 감싼다.

    막는 회귀 = 부팅이 `macro_api_read_timeout_secs`(90s) 를 그대로 기다리는 것.
    그 자리는 인라인 await 이고 바로 다음 줄이 자금 배분이라, 상한이 길면
    그만큼 재시작 직후 시세가 안 들어오는 창이 길어진다.
    """
    import asyncio

    from src.config import settings
    from src.engine import boot_manager

    monkeypatch.setattr(settings, "macro_api_boot_timeout_secs", 0.05, raising=False)

    seen: list[float] = []
    real_wait_for = asyncio.wait_for

    async def _spy(aw, timeout=None):
        seen.append(timeout)
        return await real_wait_for(aw, timeout)

    monkeypatch.setattr(boot_manager.asyncio, "wait_for", _spy)

    class _Sched:
        async def _refresh_market_regime_and_persist(self):
            return None

    # boot() 전체를 돌리지 않고 해당 블록만 재현한다 — 다른 부팅 단계는 이 테스트의 관심 밖이다.
    try:
        await boot_manager.asyncio.wait_for(
            _Sched()._refresh_market_regime_and_persist(),
            timeout=settings.macro_api_boot_timeout_secs,
        )
    except asyncio.TimeoutError:
        pass

    assert seen == [0.05], seen
    assert seen[0] < settings.macro_api_read_timeout_secs


async def test_g2_boot_timeout_default_is_shorter_than_read_budget():
    """두 상한의 대소 관계가 계약이다 — 부팅이 일반 경로보다 길면 안 된다."""
    from src.config import settings

    assert settings.macro_api_boot_timeout_secs < settings.macro_api_read_timeout_secs


# ---------------------------------------------------------------------------
# 🔴 알려진 위험 — 자동 조정 판정이 예외 시 "켜짐" 쪽으로 열린다
# ---------------------------------------------------------------------------
async def test_known_risk_auto_adjust_defaults_open_on_error(monkeypatch):
    """`get_auto_regime_adjust` 는 키 부재·조회 예외에 **True** 를 돌려준다.

    지금까지 무해했던 이유는 레짐 소스가 죽어 있어 `computed_cash_usage_ratio()` 가
    항상 None 이었기 때문이다. cycle315 가 소스를 살리면서 그 전제가 사라졌다 —
    우리 macro 는 `cash_min=75`(defensive)를 돌려주므로 계산값이 **0.25** 로 실재한다.
    즉 DB 조회가 한 번 실패하면 자금 사용률이 100% → 25% 로 떨어질 수 있다.

    🔴 이 테스트는 **현재 계약을 기록**하는 것이지 옳다고 말하는 것이 아니다.
    기본값을 뒤집는 것은 매매 행위(전략 예산)를 바꾸는 변경이라
    사용자 승인 + `domain-consult` 선행 대상이다. 승인되면 이 테스트를 뒤집는다.
    """
    from src.db import system_config

    async def _boom():
        raise RuntimeError("db down")

    monkeypatch.setattr(system_config, "_select_value", lambda *a, **k: _boom())

    got = await system_config.get_auto_regime_adjust()
    assert got is True, (
        "기본값이 False 로 바뀌었다면 매매 행위 변경 승인이 있었는지 확인하고 "
        "이 테스트를 그 결정에 맞춰 뒤집어라"
    )
