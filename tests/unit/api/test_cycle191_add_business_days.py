"""사이클 191 Red — `condition.add_business_days(base_date, n)` 영업일 전진 헬퍼.

작업 지시서 `_workspace/red/cycle191_reentry_cooldown_wiring.md` §1 +
자문 `_workspace/domain_consult/cycle191_reentry_cooldown_wiring.md` 의제 3.

**Red 단계 — 실패 테스트만. production 미변경.** Green = backend-dev.

`add_business_days` 신규 함수 (미구현) → import 시 ImportError = B-1~4 전부 FAIL.

계약 (`next_trading_day` 패턴 답습):
- CTCA0903R 1회 호출 → 응답 output(~30일치)에서 `opnd_yn=="Y"` row 를
  순서대로 세어 n번째 개장일 `date` 반환.
- KIS 실패 / 개장일 부족(<n) → fallback `base_date + timedelta(days=n + 2)` + graceful.
"""

from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import AsyncMock

import pytest

import src.api.base as base_mod
import src.api.condition as cond_mod
from src.api.condition import add_business_days

pytestmark = [pytest.mark.unit, pytest.mark.asyncio]


def _patch_quote(monkeypatch: pytest.MonkeyPatch, response) -> AsyncMock:
    """`kis_get_quote` 를 AsyncMock 으로 교체 (성공/예외 양쪽)."""
    if isinstance(response, Exception):
        spy = AsyncMock(side_effect=response)
    else:
        spy = AsyncMock(return_value=response)
    monkeypatch.setattr(base_mod, "kis_get_quote", spy, raising=False)
    monkeypatch.setattr(cond_mod, "kis_get_quote", spy, raising=False)
    return spy


def _holiday_rows(pairs: list[tuple[str, str]]) -> dict:
    """(yyyymmdd, opnd_yn) 리스트 → CTCA0903R output 응답."""
    return {"output": [{"bass_dt": d, "opnd_yn": y} for d, y in pairs]}


# base = 2026-07-02 (목). base+1 = 07-03(금) 부터 응답 (next_trading_day 패턴).
# 07-03 금 Y / 07-04 토 N / 07-05 일 N / 07-06 월 Y / 07-07 화 Y / 07-08 수 Y ...
_BASE = date(2026, 7, 2)
_ROWS_30D = _holiday_rows(
    [
        ("20260703", "Y"),  # 1번째 개장일 (금)
        ("20260704", "N"),  # 토
        ("20260705", "N"),  # 일
        ("20260706", "Y"),  # 2번째 개장일 (월)
        ("20260707", "Y"),  # 3번째 개장일 (화)
        ("20260708", "Y"),  # 4번째 개장일 (수)
        ("20260709", "Y"),  # 5
        ("20260710", "Y"),  # 6
        ("20260711", "N"),  # 토
        ("20260712", "N"),  # 일
        ("20260713", "Y"),  # 7번째 개장일 (월)
        ("20260714", "Y"),  # 8
        ("20260715", "Y"),  # 9
    ]
)


# ---------------------------------------------------------------------------
# B-1 — n=3 (BFB) 정확한 3번째 개장일 (주말 스킵)
# ---------------------------------------------------------------------------
async def test_B1_n3_skips_weekend_returns_third_trading_day(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """add_business_days(목, 3) → 화(07-07). 주말(토/일) 미계수 검증."""
    _patch_quote(monkeypatch, _ROWS_30D)
    result = await add_business_days(_BASE, 3)
    assert result == date(2026, 7, 7), (
        f"3번째 개장일 = 07-07(화) 기대, 실제 {result} (주말 스킵 실패)"
    )


# ---------------------------------------------------------------------------
# B-2 — n=7 (VCP) 정확성
# ---------------------------------------------------------------------------
async def test_B2_n7_vcp_seventh_trading_day(monkeypatch: pytest.MonkeyPatch) -> None:
    """add_business_days(목, 7) → 다음주 월(07-13). 30일 응답으로 n=7 충분."""
    _patch_quote(monkeypatch, _ROWS_30D)
    result = await add_business_days(_BASE, 7)
    assert result == date(2026, 7, 13), (
        f"7번째 개장일 = 07-13(월) 기대, 실제 {result}"
    )


# ---------------------------------------------------------------------------
# B-3 — KIS 실패 → fallback base + n + 2 달력일
# ---------------------------------------------------------------------------
async def test_B3_kis_failure_falls_back_to_calendar(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """kis_get_quote 예외 → fallback = base + (n + 2) 달력일 graceful."""
    _patch_quote(monkeypatch, RuntimeError("KIS down"))
    result = await add_business_days(_BASE, 3)
    assert result == _BASE + timedelta(days=3 + 2), (
        f"실패 시 fallback = base + n + 2 = {_BASE + timedelta(days=5)} 기대, 실제 {result}"
    )


# ---------------------------------------------------------------------------
# B-4 — 응답 개장일 부족(<n) → fallback
# ---------------------------------------------------------------------------
async def test_B4_insufficient_open_days_falls_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """개장일 2건뿐인데 n=7 요청 → 부족 → fallback base + n + 2."""
    short = _holiday_rows([("20260703", "Y"), ("20260706", "Y")])  # 개장일 2건
    _patch_quote(monkeypatch, short)
    result = await add_business_days(_BASE, 7)
    assert result == _BASE + timedelta(days=7 + 2), (
        f"개장일 부족 → fallback = base + n + 2 = {_BASE + timedelta(days=9)} 기대, 실제 {result}"
    )
