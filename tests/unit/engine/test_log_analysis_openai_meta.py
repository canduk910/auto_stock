"""사이클 58 V-2 — log_analysis_engine OpenAI 메타 수집 회귀 가드 (8 케이스).

RED 작성 기준:
- _compute_cost_usd: gpt-5.4 정확도 / 미등록 모델 / 0 토큰 / 6 모델 dict 존재
- _call_openai: 정상 응답 5 필드 / usage 없음 / 예외 / 미등록 모델 경고
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# 지연 import 헬퍼 — 모듈은 테스트 실행 후에 GREEN 상태가 됨
# ---------------------------------------------------------------------------

def _import_engine():
    import importlib
    import src.engine.log_analysis_engine as mod
    importlib.reload(mod)
    return mod


# ============================================================
# 케이스 1: _compute_cost_usd — gpt-5.4 정확도
# input 1000 / output 500 → (1000/1000 * 0.005) + (500/1000 * 0.015)
#                          = 0.005 + 0.0075 = 0.0125
# ============================================================
def test_compute_cost_usd_gpt54_accuracy():
    mod = _import_engine()
    result = mod._compute_cost_usd("gpt-5.4", input_tokens=1000, output_tokens=500)
    assert result == Decimal("0.012500"), f"기대 0.012500, 실제 {result}"


# ============================================================
# 케이스 1-bis: _compute_cost_usd — gpt-5.6-luna 정확도 (2026-07-29 자문 모델 전환)
# input 1000 / output 500 → (1000/1000 * 0.001) + (500/1000 * 0.006)
#                          = 0.001 + 0.003 = 0.004
# ============================================================
def test_compute_cost_usd_gpt56_luna_accuracy():
    mod = _import_engine()
    result = mod._compute_cost_usd("gpt-5.6-luna", input_tokens=1000, output_tokens=500)
    assert result == Decimal("0.004000"), f"기대 0.004000, 실제 {result}"


# ============================================================
# 케이스 2: _compute_cost_usd — 미등록 모델 → None
# ============================================================
def test_compute_cost_usd_unknown_model_returns_none():
    mod = _import_engine()
    result = mod._compute_cost_usd("unknown-model-xyz", input_tokens=1000, output_tokens=500)
    assert result is None


# ============================================================
# 케이스 3: _call_openai — 정상 응답 시 meta 5 필드 모두 채워짐
# ============================================================
@pytest.mark.asyncio
async def test_call_openai_normal_response_meta_filled():
    mod = _import_engine()

    # OpenAI 응답 mock
    mock_usage = MagicMock()
    mock_usage.prompt_tokens = 800
    mock_usage.completion_tokens = 300
    mock_usage.total_tokens = 1100

    mock_choice = MagicMock()
    mock_choice.message.content = '{"summary": "정상", "findings": []}'

    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    mock_response.usage = mock_usage

    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

    model = "gpt-4o"
    metrics = {"test": "data"}

    result, meta = await mod._call_openai(mock_client, metrics, model)

    assert meta.input_tokens == 800
    assert meta.output_tokens == 300
    assert meta.total_tokens == 1100
    assert meta.latency_ms is not None
    assert meta.latency_ms >= 0
    assert meta.cost_estimate_usd is not None
    # gpt-4o: (800/1000 * 0.0025) + (300/1000 * 0.010) = 0.002 + 0.003 = 0.005
    assert meta.cost_estimate_usd == Decimal("0.005000")


# ============================================================
# 케이스 4: _call_openai — usage 없는 응답 → tokens None + latency_ms 채워짐
# ============================================================
@pytest.mark.asyncio
async def test_call_openai_no_usage_tokens_none_latency_set():
    mod = _import_engine()

    mock_choice = MagicMock()
    mock_choice.message.content = '{"summary": "응답", "findings": []}'

    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    mock_response.usage = None  # usage 없음

    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

    result, meta = await mod._call_openai(mock_client, {}, "gpt-4o")

    assert meta.input_tokens is None
    assert meta.output_tokens is None
    assert meta.total_tokens is None
    assert meta.cost_estimate_usd is None
    assert meta.latency_ms is not None
    assert meta.latency_ms >= 0


# ============================================================
# 케이스 5: _call_openai — 예외 발생 → result=None + latency_ms 채워짐 + tokens None
# ============================================================
@pytest.mark.asyncio
async def test_call_openai_exception_result_none_latency_set():
    mod = _import_engine()

    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(
        side_effect=RuntimeError("OpenAI 연결 오류")
    )

    result, meta = await mod._call_openai(mock_client, {}, "gpt-4o")

    assert result is None
    assert meta.input_tokens is None
    assert meta.output_tokens is None
    assert meta.total_tokens is None
    assert meta.cost_estimate_usd is None
    assert meta.latency_ms is not None
    assert meta.latency_ms >= 0


# ============================================================
# 케이스 6: _call_openai — 미등록 모델 → cost_estimate_usd=None + WARNING 로그
# ============================================================
@pytest.mark.asyncio
async def test_call_openai_unknown_model_cost_none_warning_logged(caplog):
    mod = _import_engine()

    mock_usage = MagicMock()
    mock_usage.prompt_tokens = 500
    mock_usage.completion_tokens = 200
    mock_usage.total_tokens = 700

    mock_choice = MagicMock()
    mock_choice.message.content = '{"summary": "ok", "findings": []}'

    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    mock_response.usage = mock_usage

    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

    with caplog.at_level(logging.WARNING, logger="src.engine.log_analysis_engine"):
        result, meta = await mod._call_openai(mock_client, {}, "gpt-unknown-999")

    assert meta.cost_estimate_usd is None
    assert any("[openai_pricing_miss]" in r.message for r in caplog.records)


# ============================================================
# 케이스 7: _compute_cost_usd — 0 토큰 → Decimal('0.000000')
# ============================================================
def test_compute_cost_usd_zero_tokens():
    mod = _import_engine()
    result = mod._compute_cost_usd("gpt-4o", input_tokens=0, output_tokens=0)
    assert result == Decimal("0.000000")


# ============================================================
# 케이스 8: _OPENAI_PRICING dict 7 모델 존재 확인 (회귀 가드)
# ============================================================
def test_openai_pricing_dict_has_all_required_models():
    mod = _import_engine()
    required = {
        "gpt-5.6-luna",
        "gpt-5.4",
        "gpt-4o",
        "gpt-4o-mini",
        "gpt-4-turbo",
        "gpt-4",
        "gpt-3.5-turbo",
    }
    missing = required - set(mod._OPENAI_PRICING.keys())
    assert not missing, f"_OPENAI_PRICING 에서 누락된 모델: {missing}"

    # 각 항목이 (input_per_1k, output_per_1k) 양수 tuple인지 확인
    for model, pricing in mod._OPENAI_PRICING.items():
        assert isinstance(pricing, tuple) and len(pricing) == 2, f"{model} 단가 형식 오류"
        assert pricing[0] > 0 and pricing[1] > 0, f"{model} 단가 비정상: {pricing}"
