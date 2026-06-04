"""PR-B (2026-05-14) — log_analysis_engine 메트릭 확장 검증.

`metrics.next_day_clear.{deferred, drained_success, drained_fail}` 노출.
`metrics.api_metrics.retry_recovered / retry_exhausted` 노출 (api/base 의 get_request_metrics 위임).
"""

from __future__ import annotations

import pytest

from src.engine import log_analysis_engine as lae

pytestmark = pytest.mark.unit


def _log(level: str, message: str) -> dict:
    return {"timestamp": "2026-05-14T09:30:00+09:00", "log_level": level, "message": message}


# ---------------------------------------------------------------------------
# 1. _aggregate_next_day_clear — prefix 카운트
# ---------------------------------------------------------------------------
def test_aggregate_next_day_clear_counts_prefixes():
    logs = [
        _log("INFO", "[next_day_clear_deferred] ticker=012200 strategy=momentum reason=nxt_not_tradable"),
        _log("INFO", "[next_day_clear_deferred] ticker=005930 strategy=momentum reason=nxt_open_missing"),
        _log("INFO", "[next_day_clear_drained] ticker=012200 strategy=momentum result=success elapsed_ms=123"),
        _log("WARNING", "[next_day_clear_drained] ticker=005930 strategy=momentum result=fail elapsed_ms=45"),
        _log("INFO", "정상 매매 로그 — 무관"),
    ]

    result = lae._aggregate_next_day_clear(logs)

    assert result == {
        "deferred": 2,
        "drained_success": 1,
        "drained_fail": 1,
    }


def test_aggregate_next_day_clear_empty_when_no_prefix():
    logs = [
        _log("INFO", "WebSocket 시세 구독 완료"),
        _log("WARNING", "포지션 불일치 감지"),
    ]
    result = lae._aggregate_next_day_clear(logs)
    assert result == {"deferred": 0, "drained_success": 0, "drained_fail": 0}


# ---------------------------------------------------------------------------
# 2. metrics 구조 — generate_daily_log_report 에서 next_day_clear 키 노출
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_generate_daily_log_report_exposes_next_day_clear_in_metrics(monkeypatch):
    """generate_daily_log_report 가 metrics dict 에 `next_day_clear` 노출.

    OpenAI/Supabase 호출은 모두 stub — metrics 산출 분기만 검증.
    """
    captured: dict = {}

    # supabase 조회: prefix 메시지 포함 logs 반환
    fake_logs = [
        _log("INFO", "[next_day_clear_deferred] ticker=012200 strategy=momentum reason=nxt_not_tradable"),
        _log("INFO", "[next_day_clear_drained] ticker=012200 strategy=momentum result=success elapsed_ms=80"),
    ]

    async def _fake_fetch(*_args, **_kwargs):
        return fake_logs

    async def _fake_get_trades(*_args, **_kwargs):
        return []

    from src.engine.log_analysis_engine import _OpenAIMeta

    async def _fake_call_openai(client, metrics, model):
        captured["metrics"] = metrics
        return ({"summary": "test", "findings": []}, _OpenAIMeta())

    async def _fake_insert(*_args, **_kwargs):
        return {"id": "row-1"}

    monkeypatch.setattr(lae, "_fetch_logs_in_range", _fake_fetch)
    monkeypatch.setattr(lae, "get_trades_in_range", _fake_get_trades)
    monkeypatch.setattr(lae, "_call_openai", _fake_call_openai)
    monkeypatch.setattr(lae, "insert_log_report", _fake_insert)
    monkeypatch.setattr(lae.settings, "openai_api_key", "dummy-key")

    # _collect_strategy_funnel 도 무력화 — registry 없는 환경에서도 통과
    # PR-D (2026-05-14): async 변환 — coroutine 반환 필요
    async def _empty_funnel() -> dict:
        return {}
    monkeypatch.setattr(lae, "_collect_strategy_funnel", _empty_funnel)

    await lae.generate_daily_log_report()

    metrics = captured.get("metrics")
    assert metrics is not None
    assert "next_day_clear" in metrics
    assert metrics["next_day_clear"]["deferred"] == 1
    assert metrics["next_day_clear"]["drained_success"] == 1
    assert metrics["next_day_clear"]["drained_fail"] == 0


# ---------------------------------------------------------------------------
# 3. api_metrics — recovered/exhausted 키 노출 (위임 검증)
# ---------------------------------------------------------------------------
def test_api_metrics_exposes_retry_recovered_and_exhausted():
    """get_request_metrics 가 retry_recovered / retry_exhausted 키 포함."""
    from src.api import base as _base

    _base.reset_request_metrics()
    _base._request_metrics["retry_recovered"] = 5
    _base._request_metrics["retry_exhausted"] = 2

    snapshot = _base.get_request_metrics()
    assert snapshot["retry_recovered"] == 5
    assert snapshot["retry_exhausted"] == 2

    _base.reset_request_metrics()
