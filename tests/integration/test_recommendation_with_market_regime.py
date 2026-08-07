"""사이클 4 (2026-05-17) — 매크로 레짐 → AI 자문 통합 회귀 가드.

`_call_openai()` 가 모듈 싱글톤 `get_current_regime()` 에서 매크로 정보를 가져와
user_payload 에 `market_regime` 키를 추가하는지 통합 검증.

3 케이스:
- A: regime 비활성 (DKSTOCK_REGIME_ENABLED=false 시뮬레이션 — empty regime) → 자문 정상
- B: regime 활성 + defensive → user_payload market_regime 포함
- C: regime fetch 실패 (empty + None 분기) → graceful (자문 정상 진행)

명세: `_workspace/cycle4_market_regime_advisor_payload.md`
"""
from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def _reset_market_regime_singleton():
    """매 테스트 후 모듈 싱글톤을 empty 로 복귀 — 모듈 글로벌 오염 차단."""
    from src.engine.market_regime import MarketRegime, set_current_regime

    yield
    set_current_regime(MarketRegime.empty())


def _make_captured_openai_client(captured: dict[str, Any]):
    fake_msg = SimpleNamespace(content=json.dumps({"recommended_params": {}}))
    fake_choice = SimpleNamespace(message=fake_msg)
    fake_response = SimpleNamespace(choices=[fake_choice])

    async def _create(**kwargs):
        captured["kwargs"] = kwargs
        return fake_response

    fake_completions = SimpleNamespace(create=_create)
    fake_chat = SimpleNamespace(completions=fake_completions)
    client = SimpleNamespace(chat=fake_chat)
    return MagicMock(return_value=client)


def _extract_user_payload(captured: dict[str, Any]) -> dict:
    msgs = captured["kwargs"]["messages"]
    user_content = msgs[1]["content"]
    json_start = user_content.find("{")
    assert json_start >= 0
    return json.loads(user_content[json_start:])


# ---------------------------------------------------------------------------
# Case A — DKSTOCK_REGIME_ENABLED=false 시나리오 (empty regime) → 자문 정상
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_a_dkstock_disabled_advisor_works(monkeypatch):
    """empty regime 전달 시 자문이 시기존 8 필드만 가지고 정상 호출."""
    from src.engine import recommendation_engine
    from src.engine.market_regime import MarketRegime, set_current_regime

    set_current_regime(MarketRegime.empty())

    captured: dict[str, Any] = {}
    fake_factory = _make_captured_openai_client(captured)
    monkeypatch.setattr("openai.AsyncOpenAI", fake_factory, raising=False)
    monkeypatch.setattr(
        recommendation_engine.settings, "openai_api_key", "test-key", raising=False
    )
    monkeypatch.setattr(
        recommendation_engine.settings,
        "openai_recommend_model",
        "gpt-test",
        raising=False,
    )

    result = await recommendation_engine._call_openai(
        strategy_name="모멘텀",
        strategy_description="모멘텀 설명",
        current_params={"buy_threshold": 29.0},
        metrics={"trades_count": 5},
    )
    # JSON 응답 정상 파싱
    assert result == {"recommended_params": {}}
    payload = _extract_user_payload(captured)
    assert "market_regime" not in payload


# ---------------------------------------------------------------------------
# Case B — 활성 + defensive → market_regime 포함, defensive 시그널 OpenAI 에 전달
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_b_active_defensive_market_regime_payload(monkeypatch):
    from src.engine import recommendation_engine
    from src.engine.market_regime import MarketRegime, set_current_regime

    regime = MarketRegime(
        regime="defensive",
        regime_desc="방어 (공포 현금)",
        cycle_phase="contraction",
        vix=28.0,
        fear_greed_score=18.0,
        buffett_ratio=220.0,
        cash_min=75,
        raw={"regime": {"params": {"stock_max": 25}}},
    )
    set_current_regime(regime)

    captured: dict[str, Any] = {}
    fake_factory = _make_captured_openai_client(captured)
    monkeypatch.setattr("openai.AsyncOpenAI", fake_factory, raising=False)
    monkeypatch.setattr(
        recommendation_engine.settings, "openai_api_key", "test-key", raising=False
    )
    monkeypatch.setattr(
        recommendation_engine.settings,
        "openai_recommend_model",
        "gpt-test",
        raising=False,
    )

    result = await recommendation_engine._call_openai(
        strategy_name="모멘텀",
        strategy_description="모멘텀 설명",
        current_params={"buy_threshold": 29.0, "stop_loss_rate": -7.5},
        metrics={"trades_count": 5},
        current_weight=0.2,
        peer_weights={"volatility_breakout": 0.3},
        peer_metrics={"volatility_breakout": {"trades_count": 10}},
    )
    assert result == {"recommended_params": {}}

    payload = _extract_user_payload(captured)
    assert "market_regime" in payload
    mr = payload["market_regime"]
    assert mr["regime"] == "defensive"
    assert mr["vix_level"] == "elevated"
    assert mr["fear_greed_label"] == "공포"
    # [의미 전환 2026-08-07] 관찰 전용 — 레짐은 매수를 차단하지 않는다(사이클 I).
    # 자문 payload buy_blocked 는 defensive 여도 False (block_reason 은 관찰용 유지).
    assert mr["buy_blocked"] is False
    # 사이클 1 의 8 필드도 함께 보존
    for key in (
        "strategy_name",
        "strategy_description",
        "current_params",
        "metrics",
        "param_ranges",
        "current_weight",
        "peer_weights",
        "peer_metrics",
    ):
        assert key in payload


# ---------------------------------------------------------------------------
# Case C — regime 모듈 싱글톤이 None (fetch 실패 후 reset 시뮬레이션) → graceful
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_c_regime_fetch_failure_graceful(monkeypatch):
    """get_current_regime() 가 None 반환해도 자문 정상 진행."""
    from src.engine import recommendation_engine

    monkeypatch.setattr(
        recommendation_engine, "get_current_regime", lambda: None, raising=False
    )

    captured: dict[str, Any] = {}
    fake_factory = _make_captured_openai_client(captured)
    monkeypatch.setattr("openai.AsyncOpenAI", fake_factory, raising=False)
    monkeypatch.setattr(
        recommendation_engine.settings, "openai_api_key", "test-key", raising=False
    )
    monkeypatch.setattr(
        recommendation_engine.settings,
        "openai_recommend_model",
        "gpt-test",
        raising=False,
    )

    result = await recommendation_engine._call_openai(
        strategy_name="모멘텀",
        strategy_description="모멘텀 설명",
        current_params={"buy_threshold": 29.0},
        metrics={"trades_count": 5},
    )
    assert result == {"recommended_params": {}}
    payload = _extract_user_payload(captured)
    assert "market_regime" not in payload
