"""cycle423 리팩토링 카드 #5 — Red.

정본 = `_workspace/refactor/2026-10-09_review.md` 「카드 #5」. `GET /api/strategies/monitor` 의
`_monitor_market_unit`(`src/routes/strategies.py`)이 시장 유닛 표시 대상을 손으로 적은 리터럴
(`_MONITOR_MU_SIDS`)로 들고 있었다 — `strategy_manifest.MARKET_UNIT_SCALE_IDS`(등록 명부의
`market_unit_policy=="scale"` 파생)와 같은 사실을 두 번 적은 것이다. 새 전략이 명부에
`market_unit_policy="scale"` 로 들어와도 이 라우트가 리터럴을 따로 고치지 않으면 화면에서
그 전략의 `market_unit` 이 조용히 `null` 로 빠진다.

| # | 계약 |
|---|---|
| M1 | 행위 동일 — 지금 명부의 5전략(kojiro·donchian_swing·vcp_breakout·bull_flag_breakout·etf_trend)은
     그대로 `market_unit` 을 내고, 그 밖(momentum 등)은 그대로 `None` |
| M2 | **출처가 명부다** — `strategy_manifest.MARKET_UNIT_SCALE_IDS` 를 바꿔 끼우면(monkeypatch)
     `_monitor_market_unit` 의 판정이 **라우트 코드를 고치지 않고** 그 값을 따라간다. 하드코딩
     리터럴이면 이 테스트는 Red(패치가 무시된다) |
"""
from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.unit


class _FakeStrategy:
    def __init__(self, strategy_id: str, params: dict | None = None, snaps: dict | None = None):
        self.strategy_id = strategy_id
        self.config = SimpleNamespace(params=params or {})
        self._market_unit_snaps = snaps or {}


def _call(strategy_id: str, today=date(2026, 10, 9)):
    from src.routes.strategies import _monitor_market_unit

    return _monitor_market_unit(_FakeStrategy(strategy_id), today)


def test_m1_scale_strategies_still_get_market_unit():
    from src.engine.strategy_manifest import MARKET_UNIT_SCALE_IDS

    for sid in MARKET_UNIT_SCALE_IDS:
        assert _call(sid) is not None, f"{sid} — 명부 scale 대상인데 null"


def test_m1_non_scale_strategies_still_null():
    for sid in ("momentum", "volatility_breakout", "long_tail_volatility"):
        assert _call(sid) is None, f"{sid} — scale 대상이 아닌데 값이 나온다"


def test_m2_source_is_manifest_not_hardcoded_literal(monkeypatch):
    """명부를 패치하면 라우트 판정이 따라와야 한다 — 하드코딩 리터럴이면 무시된다(Red)."""
    import src.engine.strategy_manifest as sm

    # 모멘텀을 유닛 대상으로, 돈키언을 대상 밖으로 뒤집어 본다.
    monkeypatch.setattr(sm, "MARKET_UNIT_SCALE_IDS", ("momentum",))
    assert _call("momentum") is not None, "패치된 명부를 반영하지 않는다 — 하드코딩 의심"
    assert _call("donchian_swing") is None, "패치된 명부를 반영하지 않는다 — 하드코딩 의심"
