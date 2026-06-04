"""사이클 58 V-2 — log_reports.py OpenAI 메타 keyword 전달 회귀 가드 (2 케이스).

케이스 9: insert_log_report 5 메타 keyword 전달 시 payload 에 정확 포함
케이스 10: insert_log_report 메타 None (default) → payload 에 NULL INSERT 정상
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _import_log_reports():
    import importlib
    import src.db.log_reports as mod
    importlib.reload(mod)
    return mod


# ============================================================
# 케이스 9: 5 메타 keyword 전달 → payload 포함
# ============================================================
@pytest.mark.asyncio
async def test_insert_log_report_meta_included_in_payload():
    mod = _import_log_reports()

    captured_payload: dict = {}

    async def fake_to_thread(fn):
        # lambda 가 반환하는 실행 결과를 흉내냄
        # fn() 호출 시 supabase chain이 실행되는데 우리는 payload만 캡처
        return MagicMock(data=[{"id": "test-uuid"}])

    # supabase.table(...).insert(...).execute() 체인 mock
    mock_execute = MagicMock(return_value=MagicMock(data=[{"id": "test-uuid"}]))
    mock_insert = MagicMock()
    mock_insert.execute = mock_execute
    mock_table = MagicMock()
    mock_table.insert = MagicMock(side_effect=lambda payload: (captured_payload.update(payload) or mock_insert))

    with patch("src.db.log_reports.supabase") as mock_supa, \
         patch("asyncio.to_thread", new=fake_to_thread):
        mock_supa.table.return_value = mock_table

        # asyncio.to_thread 가 lambda 를 실행하지 않으므로
        # 실제 payload 는 캡처 안 됨 → to_thread mock 을 직접 실행하도록 교체
        pass

    # --- 더 직접적인 방법: asyncio.to_thread 를 실제 실행하는 mock 으로 교체 ---
    async def execute_fn(fn):
        return fn()

    mock_execute2 = MagicMock(return_value=MagicMock(data=[{"id": "uuid-1"}]))
    mock_insert2 = MagicMock()
    mock_insert2.execute = mock_execute2

    mock_table2 = MagicMock()
    def capture_insert(payload):
        captured_payload.clear()
        captured_payload.update(payload)
        return mock_insert2
    mock_table2.insert = MagicMock(side_effect=capture_insert)

    with patch("src.db.log_reports.supabase") as mock_supa2, \
         patch("asyncio.to_thread", side_effect=execute_fn):
        mock_supa2.table.return_value = mock_table2

        result = await mod.insert_log_report(
            target_date=date(2026, 6, 4),
            summary="테스트 요약",
            findings=[],
            metrics={"key": "val"},
            model="gpt-4o",
            input_tokens=1000,
            output_tokens=500,
            total_tokens=1500,
            latency_ms=1234,
            cost_estimate_usd=Decimal("0.012500"),
        )

    # payload 에 5 메타 필드가 모두 포함되어야 함
    assert captured_payload.get("input_tokens") == 1000, f"input_tokens 누락: {captured_payload}"
    assert captured_payload.get("output_tokens") == 500
    assert captured_payload.get("total_tokens") == 1500
    assert captured_payload.get("latency_ms") == 1234
    # Decimal → 직렬화 시 float 또는 Decimal 모두 허용
    cost = captured_payload.get("cost_estimate_usd")
    assert cost is not None, "cost_estimate_usd 누락"
    assert float(cost) == pytest.approx(0.012500, rel=1e-6)


# ============================================================
# 케이스 10: 메타 None (default) → payload 에 NULL INSERT 정상
# ============================================================
@pytest.mark.asyncio
async def test_insert_log_report_meta_none_defaults_to_null():
    mod = _import_log_reports()

    captured_payload: dict = {}

    async def execute_fn(fn):
        return fn()

    mock_execute = MagicMock(return_value=MagicMock(data=[{"id": "uuid-2"}]))
    mock_insert = MagicMock()
    mock_insert.execute = mock_execute

    mock_table = MagicMock()
    def capture_insert(payload):
        captured_payload.clear()
        captured_payload.update(payload)
        return mock_insert
    mock_table.insert = MagicMock(side_effect=capture_insert)

    with patch("src.db.log_reports.supabase") as mock_supa, \
         patch("asyncio.to_thread", side_effect=execute_fn):
        mock_supa.table.return_value = mock_table

        result = await mod.insert_log_report(
            target_date=date(2026, 6, 4),
            summary="기본 요약",
            findings=[],
            metrics={},
            model="gpt-4o",
            # 5 메타 keyword 미전달 (기본값 None)
        )

    # None 기본값이면 payload 에 키가 있고 값이 None (NULL INSERT)
    assert "input_tokens" in captured_payload, "input_tokens 키 누락"
    assert captured_payload["input_tokens"] is None
    assert "output_tokens" in captured_payload
    assert captured_payload["output_tokens"] is None
    assert "total_tokens" in captured_payload
    assert captured_payload["total_tokens"] is None
    assert "latency_ms" in captured_payload
    assert captured_payload["latency_ms"] is None
    assert "cost_estimate_usd" in captured_payload
    assert captured_payload["cost_estimate_usd"] is None
