"""사이클 H Red — 20:10 일일 리포트 metrics `portfolio_risk_snapshot` 배선 + graceful.

명세: `_workspace/cycleH_portfolio_risk_phase1_spec.md` §3 + §TDD (d).
Red 메모: `_workspace/red/cycleH_portfolio_risk.md`.

계약 (구현 전 Red 고정):
- `generate_daily_log_report` 가 산출하는 metrics dict 에 **`portfolio_risk_snapshot`** 키 추가.
- 스냅샷 빌드 실패 시 graceful — 키 값 None + 리포트 INSERT 는 보존 (사이클 88 G-REJECT).
- 기존 키(strategy_funnel / strategy_funnel_stages 등) 병존 (회귀 0).

seam: backend-dev 는 log_analysis_engine 에 async 헬퍼 `_build_portfolio_risk_snapshot(_now_kst)`
를 두고, `generate_daily_log_report` 가 이를 try/except 로 감싸 metrics 에 주입한다
(실패 → None). 본 테스트는 그 헬퍼를 monkeypatch 로 성공/예외 주입.

패턴: `test_cycle199_metrics_integration.py` 답습 — 외부(openai/DB) 전부 stub, metrics 분기만 검증.

RED 상태: `generate_daily_log_report` 가 metrics 에 `portfolio_risk_snapshot` 키를 넣지 않음 +
`_build_portfolio_risk_snapshot` 헬퍼 부재 → assert 실패 / AttributeError.
"""
from __future__ import annotations

import pytest

from src.engine import log_analysis_engine as lae
from src.engine import log_metrics_collector as collector  # cycle259 카드 ⑦ — 이동처

pytestmark = pytest.mark.unit


def _stub_common(monkeypatch, captured: dict):
    """openai/DB/funnel 전부 stub — metrics 산출 분기만 노출."""
    async def _fake_fetch_logs(*_a, **_kw):
        return []

    async def _fake_get_trades(*_a, **_kw):
        return []

    from src.engine.log_analysis_engine import _OpenAIMeta

    async def _fake_call_openai(client, metrics, model):
        captured["metrics"] = metrics
        return ({"summary": "ok", "findings": []}, _OpenAIMeta())

    async def _fake_insert(*_a, **_kw):
        captured["insert_metrics"] = _kw.get("metrics")
        return {"id": "row-H"}

    async def _coarse() -> dict:
        return {"volatility_breakout": {"signals": 0, "orders": 0, "fills": 0}}

    async def _stages(_target_date) -> dict:
        return {}

    monkeypatch.setattr(collector, "_fetch_logs_in_range", _fake_fetch_logs)
    monkeypatch.setattr(collector, "get_trades_in_range", _fake_get_trades)
    monkeypatch.setattr(lae, "_call_openai", _fake_call_openai)
    monkeypatch.setattr(lae, "insert_log_report", _fake_insert)
    monkeypatch.setattr(lae.settings, "openai_api_key", "dummy-key")
    monkeypatch.setattr(collector, "_collect_strategy_funnel", _coarse)
    monkeypatch.setattr(collector, "_collect_strategy_funnel_stages", _stages, raising=False)

    async def _no_pyramid_shadow(_target_date):
        return None

    # cycle351 — 셰도 진입점 대역(DB·30초 상한 무접촉). Green 전에는 속성이 없어 raising=False.
    monkeypatch.setattr(collector, "_collect_pyramid_shadow", _no_pyramid_shadow, raising=False)


# ===========================================================================
# (d) 정상 — metrics 에 portfolio_risk_snapshot 키 + 기존 키 병존
# ===========================================================================
@pytest.mark.asyncio
async def test_metrics_includes_portfolio_risk_snapshot(monkeypatch):
    captured: dict = {}
    _stub_common(monkeypatch, captured)

    fake_snapshot = {
        "total_notional_won": 380_000,
        "total_open_risk_won": 31_400,
        "open_risk_pct_of_net": 3.14,
        "concurrent_positions": 4,
        "by_strategy": {},
        "by_sector": {},
        "top_sector": {"sector": "반도체", "risk_won": 18_000, "risk_share_pct": 57.32},
    }

    async def _fake_build(_now_kst=None):
        return fake_snapshot

    monkeypatch.setattr(collector, "_build_portfolio_risk_snapshot", _fake_build, raising=False)

    row = await lae.generate_daily_log_report()
    assert row == {"id": "row-H"}

    metrics = captured.get("metrics")
    assert metrics is not None
    assert "portfolio_risk_snapshot" in metrics, "metrics 에 portfolio_risk_snapshot 키 누락"
    assert metrics["portfolio_risk_snapshot"] == fake_snapshot

    # INSERT 에 전달된 metrics 도 동일 키 보유 (영속 검증)
    assert "portfolio_risk_snapshot" in captured.get("insert_metrics", {})

    # 기존 키 병존 (회귀 0)
    assert "strategy_funnel" in metrics
    assert "strategy_funnel_stages" in metrics


# ===========================================================================
# (d) graceful — 스냅샷 빌드 예외 시 키 None + 리포트 INSERT 보존
# ===========================================================================
@pytest.mark.asyncio
async def test_snapshot_build_exception_keeps_report(monkeypatch):
    captured: dict = {}
    _stub_common(monkeypatch, captured)

    async def _raising_build(_now_kst=None):
        raise RuntimeError("get_balance / registry 일시 장애")

    monkeypatch.setattr(collector, "_build_portfolio_risk_snapshot", _raising_build, raising=False)

    row = await lae.generate_daily_log_report()
    # 리포트 INSERT 보존 (스냅샷 실패가 리포트 생성 막지 않음)
    assert row == {"id": "row-H"}

    metrics = captured.get("metrics")
    assert metrics is not None
    assert "portfolio_risk_snapshot" in metrics, "실패 시에도 키는 존재 (None)"
    assert metrics["portfolio_risk_snapshot"] is None, "빌드 실패 → 키 값 None (graceful)"
