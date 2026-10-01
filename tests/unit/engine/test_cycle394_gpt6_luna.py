"""cycle394 — LLM 기본 모델을 `gpt-6-luna` 로 전환 (사용자 요청 10-02).

사용자 원문 = 「우리 AI사용 때는 gpt-6-luna를 사용하자」.

소비처 셋이 모델 키 둘을 읽는다:
- 20:00 AI 자문 `recommendation_engine._call_openai` ← `settings.openai_recommend_model`
- 21:30 일일 로그 분석 `log_analysis_engine` ← 같은 키
- AI 매수평가 shadow `llm_buy_gate` ← `settings.openai_buy_gate_model`

비용 단가 정본은 `log_analysis_engine._OPENAI_PRICING` 하나다(USD / 1K 토큰).
`gpt-6-luna` = 입력 $0.10/1M · 출력 $0.50/1M → `(0.0001, 0.0005)`.
표에 없으면 21:30 분석은 `cost_estimate_usd=None` + `[openai_pricing_miss]` WARNING,
매수평가는 `cost_usd=-1.0` 이 되어 **전환한 날부터 비용 기록이 끊긴다** — 이 파일이 그것을 막는다.

⚠️ 기본값은 `Settings.model_fields[...].default` 로 잰다 — `settings` 인스턴스는 `.env`
값이 이기므로 로컬 `.env` 유무에 따라 결과가 갈린다.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.config import Settings
from src.engine import llm_buy_gate as gate
from src.engine import log_analysis_engine as lae

_NEW_MODEL = "gpt-6-luna"
_MODEL_KEYS = ("openai_recommend_model", "openai_buy_gate_model")


@pytest.mark.parametrize("key", _MODEL_KEYS)
def test_config_default_model_when_env_absent_then_gpt6_luna(key: str) -> None:
    assert Settings.model_fields[key].default == _NEW_MODEL


@pytest.mark.parametrize("key", _MODEL_KEYS)
def test_config_default_model_when_any_key_then_has_pricing_row(key: str) -> None:
    """기본 모델이 단가표에 없으면 비용 기록이 조용히 None/-1.0 이 된다 — 기본값과 표를 묶는다."""
    default = Settings.model_fields[key].default
    assert default in lae._OPENAI_PRICING, (
        f"`{key}` 기본값 {default!r} 의 단가가 `_OPENAI_PRICING` 에 없다"
    )


def test_pricing_when_gpt6_luna_then_unit_price_per_1k() -> None:
    assert lae._OPENAI_PRICING[_NEW_MODEL] == (0.0001, 0.0005)


def test_compute_cost_when_gpt6_luna_then_exact_decimal() -> None:
    # 1000 입력 · 500 출력 ⇒ 0.0001 + 0.00025 = 0.00035
    assert lae._compute_cost_usd(_NEW_MODEL, 1000, 500) == Decimal("0.000350")
    # 21:30 분석 실측 규모(in 7302 · out 1572) ⇒ 0.0007302 + 0.000786 = 0.0015162 → 6자리 반올림
    assert lae._compute_cost_usd(_NEW_MODEL, 7302, 1572) == Decimal("0.001516")


def test_compute_cost_when_old_model_then_row_kept_for_rollback() -> None:
    """gpt-5.6-luna 행은 지우지 않는다 — 과거 행 비용 재계산 · `.env` 롤백용."""
    assert lae._compute_cost_usd("gpt-5.6-luna", 1000, 500) is not None


def test_buy_gate_cost_when_gpt6_luna_then_not_unknown_sentinel() -> None:
    # 1000 입력 · 100 출력 ⇒ 0.0001 + 0.00005 = 0.00015 (−1.0 = 「모른다」 아님)
    assert gate._cost_usd(_NEW_MODEL, 1000, 100) == pytest.approx(0.00015, abs=1e-12)


@pytest.mark.asyncio
async def test_log_analysis_call_when_gpt6_luna_then_no_pricing_miss_warning(caplog) -> None:
    usage = MagicMock(prompt_tokens=7302, completion_tokens=1572, total_tokens=8874)
    choice = MagicMock()
    choice.message.content = '{"summary": "ok", "findings": []}'
    response = MagicMock(choices=[choice], usage=usage)
    client = AsyncMock()
    client.chat.completions.create = AsyncMock(return_value=response)

    with caplog.at_level(logging.WARNING, logger="src.engine.log_analysis_engine"):
        result, meta = await lae._call_openai(client, {}, _NEW_MODEL)

    assert result == {"summary": "ok", "findings": []}
    assert client.chat.completions.create.await_args.kwargs["model"] == _NEW_MODEL
    assert meta.cost_estimate_usd == Decimal("0.001516")
    misses = [
        r for r in caplog.records
        if r.levelno >= logging.WARNING and r.getMessage().startswith("[openai_pricing_miss] ")
    ]
    assert misses == [], [r.getMessage() for r in misses]
