"""사이클 199 (E-1) — metrics dict 통합 검증 (배선 회귀).

(6) metrics 포함 + coarse 병존:
  `generate_daily_log_report` 가 산출하는 metrics dict 에
  "strategy_funnel_stages" 키가 존재 + 기존 "strategy_funnel" (coarse
  signals/orders/fills) 불변.

기존 `test_log_analysis_metrics.py` / `test_log_analysis_funnel_crosscheck.py`
패턴 답습 — 모든 외부 호출(openai/DB) stub, metrics 산출 분기만 검증.

**Red 상태**: 현재 `generate_daily_log_report` 는 metrics dict 에
"strategy_funnel_stages" 키를 넣지 않음 → KeyError/assert 실패.
기존 "strategy_funnel" coarse 키는 이미 있으므로 병존 단언은 회귀 가드.
"""

from __future__ import annotations

import pytest

from src.engine import log_analysis_engine as lae
from src.engine import log_metrics_collector as collector  # cycle259 카드 ⑦ — 이동처

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_metrics_includes_funnel_stages_and_coarse_coexist(monkeypatch):
    """metrics 에 strategy_funnel_stages 신규 키 + 기존 strategy_funnel 병존."""
    captured: dict = {}

    async def _fake_fetch_logs(*_a, **_kw):
        return []

    async def _fake_get_trades(*_a, **_kw):
        return []

    from src.engine.log_analysis_engine import _OpenAIMeta

    async def _fake_call_openai(client, metrics, model):
        captured["metrics"] = metrics
        return ({"summary": "ok", "findings": []}, _OpenAIMeta())

    async def _fake_insert(*_a, **_kw):
        return {"id": "row-199"}

    monkeypatch.setattr(collector, "_fetch_logs_in_range", _fake_fetch_logs)
    monkeypatch.setattr(collector, "get_trades_in_range", _fake_get_trades)
    monkeypatch.setattr(lae, "_call_openai", _fake_call_openai)
    monkeypatch.setattr(lae, "insert_log_report", _fake_insert)
    monkeypatch.setattr(lae.settings, "openai_api_key", "dummy-key")

    # coarse funnel stub (기존 병존 확인용)
    async def _coarse() -> dict:
        return {"volatility_breakout": {"signals": 0, "orders": 0, "fills": 0}}

    monkeypatch.setattr(collector, "_collect_strategy_funnel", _coarse)

    # 신규 stages stub — verdict 포함 dict 반환
    async def _stages(_target_date) -> dict:
        return {
            "bull_flag_breakout": {
                "steps": [
                    {"step_no": 5, "step_name": "폴 검출", "survived_count": 2, "excluded_count": 0},
                    {"step_no": 6, "step_name": "플래그 형성", "survived_count": 0, "excluded_count": 2},
                ],
                "peak_survived": 2,
                "final_prepared": 0,
                "drop_step": {"step_no": 6, "step_name": "플래그 형성"},
                "verdict": "패턴희소",
            }
        }

    monkeypatch.setattr(collector, "_collect_strategy_funnel_stages", _stages, raising=False)

    row = await lae.generate_daily_log_report()
    assert row == {"id": "row-199"}

    metrics = captured.get("metrics")
    assert metrics is not None

    # 신규 키 존재 + verdict 노출
    assert "strategy_funnel_stages" in metrics, "E-1: strategy_funnel_stages 키 누락"
    assert metrics["strategy_funnel_stages"]["bull_flag_breakout"]["verdict"] == "패턴희소"

    # 기존 coarse 키 병존 (회귀 0)
    assert "strategy_funnel" in metrics, "coarse strategy_funnel 키 병존 의무"
    assert metrics["strategy_funnel"]["volatility_breakout"] == {
        "signals": 0,
        "orders": 0,
        "fills": 0,
    }


@pytest.mark.asyncio
async def test_metrics_funnel_stages_receives_target_date(monkeypatch):
    """_collect_strategy_funnel_stages 가 target_date 인자로 호출된다 (freezegun 회피)."""
    captured: dict = {}

    async def _fake_fetch_logs(*_a, **_kw):
        return []

    async def _fake_get_trades(*_a, **_kw):
        return []

    from src.engine.log_analysis_engine import _OpenAIMeta

    async def _fake_call_openai(client, metrics, model):
        return ({"summary": "ok", "findings": []}, _OpenAIMeta())

    async def _fake_insert(*_a, **_kw):
        return {"id": "row-199b"}

    async def _coarse() -> dict:
        return {}

    async def _stages(target_date) -> dict:
        captured["target_date"] = target_date
        return {}

    monkeypatch.setattr(collector, "_fetch_logs_in_range", _fake_fetch_logs)
    monkeypatch.setattr(collector, "get_trades_in_range", _fake_get_trades)
    monkeypatch.setattr(lae, "_call_openai", _fake_call_openai)
    monkeypatch.setattr(lae, "insert_log_report", _fake_insert)
    monkeypatch.setattr(lae.settings, "openai_api_key", "dummy-key")
    monkeypatch.setattr(collector, "_collect_strategy_funnel", _coarse)
    monkeypatch.setattr(collector, "_collect_strategy_funnel_stages", _stages, raising=False)

    from datetime import datetime

    fixed = datetime(2026, 7, 9, 20, 10, tzinfo=lae.KST)
    await lae.generate_daily_log_report(_now_kst=fixed)

    from datetime import date

    assert captured.get("target_date") == date(2026, 7, 9), (
        "target_date 는 인자 주입 (now_kst.date())"
    )
