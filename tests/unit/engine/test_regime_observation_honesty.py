"""레짐 관찰 전용 정직화 — 자문 payload + buffett_ratio 파싱 (2026-08-07).

## 배경

사이클 I(2026-08-03)가 레짐 매수 게이트를 risk.py/scheduler 에서 전면 제거하고
"레짐은 관찰 전용, 대응은 cash_usage_ratio 로만" 을 채택했다. `/current` 라우트는
`buy_blocked=False` 로 정직화됐으나 **자문 계층(`to_advisor_dict`)만 여전히 레거시
`buy_blocked=True`(defensive → block_reason → True)를 방출**한다.

그 결과 매일 20:00 AI 자문이 SYSTEM_PROMPT 의 거짓 등가("buy_blocked=True =
모든 전략 매수 차단 → 매수 튜닝 무용")를 먹고 **매수 파라미터 권고를 통째로
스킵**한다. 엔진은 100% 자유 투입 중인데(2026-08-07 실측: buy_block_mode=OFF,
cash_usage_ratio=1.0) AI 에겐 "전면 차단" 이라 거짓말하고 있었다.

## buffett_ratio 파싱 버그 (F1)

`from_macro_cycle` 이 buffett_ratio 를 `params.pbr_max`(PBR 상한, 라이브 0=비활성)
에서 읽는다 — 완전히 다른 필드다. 실제 `regime.buffett_ratio=1.45`(방어 권고의
핵심 근거)는 `regime_obj.get("buffett_ratio")` 에 있는데 안 읽어, /current·자문·
스냅샷 전 계층에서 buffett_ratio 가 null 이었다.

## 방향 = A (관찰 전용 확정, 사용자 결정 2026-08-07)

행위(100% 투입)는 그대로. 표시/자문/문서의 거짓만 닫는다. `block_reason` 은
"레짐 경보 사유(관찰)" 로 유지(dkstock 권고 기록). buy_blocked 프로퍼티 자체는
감사 스냅샷·is_buy_allowed 동기 API 가 쓰므로 유지하되, **자문 payload 에서만
False 로 정직화**(/current 접근과 동일).
"""

from __future__ import annotations

import inspect

import pytest

from src.engine.market_regime import MarketRegime

pytestmark = pytest.mark.unit


# 2026-08-07 라이브 dkstock 응답 스키마 (실측)
def _live_macro():
    return {
        "cycle": {"phase": "expansion", "phase_label": "확장기", "confidence": 25},
        "regime": {
            "regime": "defensive",
            "regime_desc": "방어 (공포 현금)",
            "vix": 15.94,
            "fear_greed_score": 79.0,
            "buffett_ratio": 1.45,       # ← 방어 권고 핵심 근거
            "buffett_level": "high",
            "params": {"cash_min": 75, "stock_max": 25, "pbr_max": 0},  # pbr_max=0 비활성
        },
        "errors": [],
    }


# ---------------------------------------------------------------------------
# F1 — buffett_ratio 를 올바른 필드에서 파싱
# ---------------------------------------------------------------------------

def test_buffett_ratio_parsed_from_regime_field_not_pbr_max():
    """라이브: regime.buffett_ratio=1.45, params.pbr_max=0(비활성).

    버그는 pbr_max 를 buffett 로 읽어 전 계층 null 이었다.
    """
    mr = MarketRegime.from_macro_cycle(_live_macro())
    assert mr.buffett_ratio == 1.45, "regime.buffett_ratio 를 읽어야 한다 (pbr_max 아님)"


def test_buffett_ratio_none_when_field_absent():
    """buffett_ratio 필드 부재 → None (graceful, pbr_max 로 폴백하지 않는다)."""
    macro = _live_macro()
    del macro["regime"]["buffett_ratio"]
    mr = MarketRegime.from_macro_cycle(macro)
    assert mr.buffett_ratio is None


def test_live_regime_fields_all_parsed():
    """라이브 응답 전 필드 정합 (매핑 깨짐 재발 방지)."""
    mr = MarketRegime.from_macro_cycle(_live_macro())
    assert mr.regime == "defensive"          # raw.regime.regime (cycle.phase 아님)
    assert mr.cycle_phase == "expansion"     # raw.cycle.phase
    assert mr.vix == 15.94
    assert mr.fear_greed_score == 79.0
    assert mr.cash_min == 75


# ---------------------------------------------------------------------------
# 자문 payload 정직화 — buy_blocked=False, block_reason 유지
# ---------------------------------------------------------------------------

def _defensive_regime():
    return MarketRegime.from_macro_cycle(_live_macro())


def test_advisor_dict_buy_blocked_is_false():
    """레짐은 매수를 차단하지 않는다 (사이클 I). 자문 payload 도 /current 와 정합."""
    d = _defensive_regime().to_advisor_dict()
    assert d["buy_blocked"] is False, (
        "defensive 여도 자문에 buy_blocked=True 를 방출하면 AI 가 매수 튜닝을 스킵한다"
    )


def test_advisor_dict_keeps_block_reason_for_observation():
    """block_reason 은 '레짐 경보 사유' 관찰용으로 유지 — AI 가 보수적 톤 참고 가능."""
    d = _defensive_regime().to_advisor_dict()
    assert d["block_reason"] is not None
    assert "defensive" in d["block_reason"]


def test_advisor_dict_exposes_live_buffett():
    """buffett_ratio 버그 시정이 자문 계층까지 전파."""
    d = _defensive_regime().to_advisor_dict()
    assert d["buffett_ratio"] == 1.45


# ---------------------------------------------------------------------------
# SYSTEM_PROMPT 거짓 등가 제거
# ---------------------------------------------------------------------------

def test_system_prompt_no_false_buy_block_equivalence():
    """'buy_blocked=True = 모든 전략 매수 차단' 거짓 등가가 프롬프트에서 사라진다."""
    from src.engine import recommendation_engine as re_mod

    prompt = re_mod.SYSTEM_PROMPT
    assert "모든 전략 매수 차단" not in prompt, (
        "사이클 I 이후 레짐은 매수를 차단하지 않는다 — AI 에 거짓 전제를 주면 안 됨"
    )


def test_system_prompt_states_regime_does_not_block_buys():
    """레짐이 매수를 차단하지 않는다는 사실을 프롬프트가 명시한다."""
    from src.engine import recommendation_engine as re_mod

    prompt = re_mod.SYSTEM_PROMPT
    assert "관찰" in prompt or "차단하지 않" in prompt or "미개입" in prompt


# ---------------------------------------------------------------------------
# 안전성 — 행위 무변경 (관찰 전용 방향 A)
# ---------------------------------------------------------------------------

def test_buy_blocked_property_unchanged_for_audit():
    """buy_blocked 프로퍼티 자체는 유지 (스냅샷 감사 기록·is_buy_allowed 동기 API).

    자문 payload 에서만 False 로 정직화한 것이지, 프로퍼티 의미를 바꾼 게 아니다.
    """
    mr = _defensive_regime()
    assert mr.buy_blocked is True          # defensive → block_reason → True (레거시 의미 보존)
    assert mr.block_reason is not None


def test_no_trading_hot_path_touched():
    """market_regime.py 는 매매 hot path(risk/order_engine)를 import 하지 않는다."""
    from src.engine import market_regime as mr_mod

    src = inspect.getsource(mr_mod)
    assert "from src.engine.risk" not in src
    assert "from src.engine.order_engine" not in src
