"""사이클 4 (2026-05-17) — 매크로 레짐 → AI 자문 user_payload 통합.

`recommendation_engine._call_openai()` 의 user_payload 에 `market_regime` 키를 추가.
`MarketRegime.to_advisor_dict()` 가 11+1 키 dict 를 반환하며,
empty/None 레짐은 graceful skip (회귀 보존).
SYSTEM_PROMPT 에 매크로 컨텍스트 활용 가이드 1 문단 포함.

자세한 명세는 `_workspace/cycle4_market_regime_advisor_payload.md` 참조.
"""
from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# autouse fixture — 모듈 싱글톤 set_current_regime 으로 다른 테스트 오염 방지
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _reset_market_regime_singleton():
    """매 테스트 후 모듈 싱글톤을 empty 로 복귀 — risk_on_tick 등 후속 테스트의
    buy_blocked 가드 결함 차단 (전역 mutable 모듈 싱글톤 격리 보호)."""
    from src.engine.market_regime import MarketRegime, set_current_regime

    yield
    set_current_regime(MarketRegime.empty())


# ---------------------------------------------------------------------------
# 헬퍼 — _call_openai monkeypatch 로 user_payload 캡처
# ---------------------------------------------------------------------------
def _make_captured_openai_client(captured: dict[str, Any]):
    """openai.AsyncOpenAI mock factory. 호출 시 captured 에 user_msg 저장."""
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
    """captured kwargs 의 messages 두 번째(user) content 에서 JSON payload 만 파싱."""
    msgs = captured["kwargs"]["messages"]
    user_content = msgs[1]["content"]
    # user_msg 는 한국어 설명 + JSON dump 의 합. JSON 시작 위치 부터 파싱
    json_start = user_content.find("{")
    assert json_start >= 0, "user_msg 에 JSON payload 없음"
    return json.loads(user_content[json_start:])


def _make_regime(
    *,
    regime: str = "defensive",
    regime_desc: str = "방어 (공포 현금)",
    cycle_phase: str = "contraction",
    vix: float = 28.0,
    fear_greed_score: float = 18.0,
    buffett_ratio: float = 220.0,
    cash_min: int = 75,
    raw: dict | None = None,
):
    from src.engine.market_regime import MarketRegime

    return MarketRegime(
        regime=regime,
        regime_desc=regime_desc,
        cycle_phase=cycle_phase,
        vix=vix,
        fear_greed_score=fear_greed_score,
        buffett_ratio=buffett_ratio,
        cash_min=cash_min,
        raw=raw or {},
    )


# ---------------------------------------------------------------------------
# Case A — regime.empty() 시 market_regime 키 없음 (회귀 보존)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_a_empty_regime_no_market_regime_key(monkeypatch):
    from src.engine import recommendation_engine
    from src.engine.market_regime import MarketRegime

    monkeypatch.setattr(
        recommendation_engine, "set_current_regime", lambda r: None, raising=False
    )
    # set_current_regime 으로 모듈 싱글톤 갱신
    from src.engine.market_regime import set_current_regime

    set_current_regime(MarketRegime.empty())

    captured: dict[str, Any] = {}
    fake_factory = _make_captured_openai_client(captured)
    # AsyncOpenAI 자체를 가짜로 치환 — _call_openai 내 import 가 monkeypatch 가능하도록
    monkeypatch.setattr(
        "openai.AsyncOpenAI", fake_factory, raising=False
    )
    monkeypatch.setattr(
        recommendation_engine.settings, "openai_api_key", "test-key", raising=False
    )
    monkeypatch.setattr(
        recommendation_engine.settings,
        "openai_recommend_model",
        "gpt-test",
        raising=False,
    )

    await recommendation_engine._call_openai(
        strategy_name="모멘텀",
        strategy_description="모멘텀 설명",
        current_params={"buy_threshold": 29.0},
        metrics={"trades_count": 5},
    )

    payload = _extract_user_payload(captured)
    assert "market_regime" not in payload


# ---------------------------------------------------------------------------
# Case B — regime 이 None (싱글톤 미설정 케이스) 도 graceful
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_b_none_regime_no_market_regime_key(monkeypatch):
    """get_current_regime() 가 None 반환하도록 monkeypatch."""
    from src.engine import recommendation_engine

    monkeypatch.setattr(
        recommendation_engine, "get_current_regime", lambda: None, raising=False
    )

    captured: dict[str, Any] = {}
    fake_factory = _make_captured_openai_client(captured)
    monkeypatch.setattr(
        "openai.AsyncOpenAI", fake_factory, raising=False
    )
    monkeypatch.setattr(
        recommendation_engine.settings, "openai_api_key", "test-key", raising=False
    )
    monkeypatch.setattr(
        recommendation_engine.settings,
        "openai_recommend_model",
        "gpt-test",
        raising=False,
    )

    await recommendation_engine._call_openai(
        strategy_name="모멘텀",
        strategy_description="모멘텀 설명",
        current_params={"buy_threshold": 29.0},
        metrics={"trades_count": 5},
    )

    payload = _extract_user_payload(captured)
    assert "market_regime" not in payload


# ---------------------------------------------------------------------------
# Case C — defensive 레짐 활성 시 user_payload["market_regime"] dict 포함
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_c_active_defensive_regime_included(monkeypatch):
    from src.engine import recommendation_engine
    from src.engine.market_regime import set_current_regime

    regime = _make_regime(
        regime="defensive", vix=28.0, fear_greed_score=18.0, cash_min=75
    )
    set_current_regime(regime)

    captured: dict[str, Any] = {}
    fake_factory = _make_captured_openai_client(captured)
    monkeypatch.setattr(
        "openai.AsyncOpenAI", fake_factory, raising=False
    )
    monkeypatch.setattr(
        recommendation_engine.settings, "openai_api_key", "test-key", raising=False
    )
    monkeypatch.setattr(
        recommendation_engine.settings,
        "openai_recommend_model",
        "gpt-test",
        raising=False,
    )

    await recommendation_engine._call_openai(
        strategy_name="모멘텀",
        strategy_description="모멘텀 설명",
        current_params={"buy_threshold": 29.0},
        metrics={"trades_count": 5},
    )

    payload = _extract_user_payload(captured)
    assert "market_regime" in payload
    mr = payload["market_regime"]
    assert mr["regime"] == "defensive"
    assert mr["vix"] == 28.0
    # [의미 전환 2026-08-07] 사이클 I 이후 레짐은 매수를 차단하지 않는다(관찰 전용).
    # 자문 payload 도 /current 와 정합해 defensive 여도 buy_blocked=False —
    # AI 가 거짓 "전면 차단" 전제로 매수 튜닝을 스킵하던 것을 막는다.
    assert mr["buy_blocked"] is False
    assert mr["block_reason"] is not None   # 방어 '권고' 사유는 관찰용으로 유지


# ---------------------------------------------------------------------------
# Case D — to_advisor_dict() 키 11+1 = 12 검증
# ---------------------------------------------------------------------------
def test_d_to_advisor_dict_keys():
    regime = _make_regime(
        regime="defensive",
        regime_desc="방어 (공포 현금)",
        cycle_phase="contraction",
        vix=28.0,
        fear_greed_score=18.0,
        buffett_ratio=220.0,
        cash_min=75,
        raw={"regime": {"params": {"stock_max": 25}}},
    )
    d = regime.to_advisor_dict()

    expected_keys = {
        "regime",
        "regime_desc",
        "cycle_phase",
        "vix",
        "vix_level",
        "fear_greed_score",
        "fear_greed_label",
        "buffett_ratio",
        "buy_blocked",
        "block_reason",
        "cash_min_recommended",
        "stock_max_recommended",
    }
    assert set(d.keys()) == expected_keys
    assert d["regime"] == "defensive"
    assert d["regime_desc"] == "방어 (공포 현금)"
    assert d["cycle_phase"] == "contraction"
    assert d["vix"] == 28.0
    assert d["fear_greed_score"] == 18.0
    assert d["buffett_ratio"] == 220.0
    assert d["cash_min_recommended"] == 75
    assert d["stock_max_recommended"] == 25
    # [의미 전환 2026-08-07] 관찰 전용 — 자문 buy_blocked 항상 False (block_reason 유지)
    assert d["buy_blocked"] is False
    assert d["block_reason"] is not None


# ---------------------------------------------------------------------------
# Case E — _classify_vix() 임계 (15 / 25 / 35)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "vix, expected",
    [
        (10.0, "low"),
        (14.99, "low"),
        (15.0, "normal"),
        (24.99, "normal"),
        (25.0, "elevated"),
        (34.99, "elevated"),
        (35.0, "high"),
        (50.0, "high"),
    ],
)
def test_e_classify_vix(vix, expected):
    regime = _make_regime(vix=vix)
    assert regime._classify_vix() == expected


def test_e_classify_vix_none():
    """vix=None 이면 None 반환."""
    regime = _make_regime()
    regime.vix = None
    assert regime._classify_vix() is None


# ---------------------------------------------------------------------------
# Case F — _classify_fear_greed() 임계 (15 / 35 / 65 / 85)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "fg, expected",
    [
        (10.0, "극공포"),
        (14.99, "극공포"),
        (15.0, "공포"),
        (34.99, "공포"),
        (35.0, "중립"),
        (64.99, "중립"),
        (65.0, "탐욕"),
        (84.99, "탐욕"),
        (85.0, "극탐욕"),
        (95.0, "극탐욕"),
    ],
)
def test_f_classify_fear_greed(fg, expected):
    regime = _make_regime(fear_greed_score=fg)
    assert regime._classify_fear_greed() == expected


def test_f_classify_fear_greed_none():
    regime = _make_regime()
    regime.fear_greed_score = None
    assert regime._classify_fear_greed() is None


# ---------------------------------------------------------------------------
# Case G — to_advisor_dict() 가 raw / raw_response 같은 대용량 필드 제외
# ---------------------------------------------------------------------------
def test_g_to_advisor_dict_excludes_raw():
    """raw, cash_min(원본), raw_response 같은 내부/대용량 필드는 advisor dict 에서 제외."""
    big_raw = {"regime": {"params": {"stock_max": 25}}, "huge_payload": "x" * 5000}
    regime = _make_regime(raw=big_raw)
    d = regime.to_advisor_dict()

    # 민감/대용량 필드 제외
    assert "raw" not in d
    assert "raw_response" not in d
    # cash_min 원본 키는 advisor 용 키명 cash_min_recommended 로 대체
    assert "cash_min" not in d
    # advisor 키는 노출
    assert "cash_min_recommended" in d


# ---------------------------------------------------------------------------
# Case H — SYSTEM_PROMPT 에 매크로 가이드 키워드 포함
# ---------------------------------------------------------------------------
def test_h_system_prompt_includes_regime_guide():
    from src.engine.recommendation_engine import SYSTEM_PROMPT

    # 필수 키워드 (영문 키 + 한국어 정책 명사)
    must_have = [
        "market_regime",
        "defensive",
        "aggressive",
        "buy_blocked",
    ]
    for kw in must_have:
        assert kw in SYSTEM_PROMPT, f"SYSTEM_PROMPT 에 '{kw}' 누락"


# ---------------------------------------------------------------------------
# Case I — regime 비활성 시 user_payload 가 사이클 1 의 8 필드 그대로 (회귀 보존)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_i_regime_inactive_payload_preserves_cycle1_keys(monkeypatch):
    """DKSTOCK_REGIME_ENABLED=false 운영 상태 시뮬레이션 — 사이클 1 8 필드 보존."""
    from src.engine import recommendation_engine
    from src.engine.market_regime import MarketRegime, set_current_regime

    set_current_regime(MarketRegime.empty())

    captured: dict[str, Any] = {}
    fake_factory = _make_captured_openai_client(captured)
    monkeypatch.setattr(
        "openai.AsyncOpenAI", fake_factory, raising=False
    )
    monkeypatch.setattr(
        recommendation_engine.settings, "openai_api_key", "test-key", raising=False
    )
    monkeypatch.setattr(
        recommendation_engine.settings,
        "openai_recommend_model",
        "gpt-test",
        raising=False,
    )

    await recommendation_engine._call_openai(
        strategy_name="모멘텀",
        strategy_description="모멘텀 설명",
        current_params={"buy_threshold": 29.0},
        metrics={"trades_count": 5},
        current_weight=0.2,
        peer_weights={"volatility_breakout": 0.3},
        peer_metrics={"volatility_breakout": {"trades_count": 10}},
    )

    payload = _extract_user_payload(captured)
    expected_keys = {
        "strategy_name",
        "strategy_description",
        "current_params",
        "metrics",
        "param_ranges",
        "current_weight",
        "peer_weights",
        "peer_metrics",
    }
    assert set(payload.keys()) == expected_keys
    assert "market_regime" not in payload
