"""사이클 172 (2026-06-22) — fetch_daily_candles_ranged + fetch_daily_candles_backfill 회귀 가드.

분할 fetch (날짜 윈도우 100건 경계) + 220일 backfill (3 윈도우 병합 dedupe).
KIS MCP 정본 FHKST03010100 (국내주식기간별시세) — 호출당 최대 100건.

회귀 가드 매트릭스:
- RANGE-1: fetch_daily_candles_ranged 100건 경계 (정본 params 정합 + output2 파싱)
- RANGE-2: FID_ORG_ADJ_PRC="0" 기존 정합 (173 동등성 게이트 보장)
- RANGE-3: FID_INPUT_DATE_1/2 start/end 전달
- RANGE-4: 6자리 ticker 가드 + graceful 빈 응답
- BACKFILL-1: 3 윈도우 호출 (T-230~T-130 / T-130~T-30 / T-30~T)
- BACKFILL-2: 중복 bas_dd dedupe (윈도우 경계 겹침 → 유니크)
- BACKFILL-3: bas_dd DESC 병합 정렬
- BACKFILL-4: fetch_daily_candles 변경 0 (memcache/single-flight 영속 AST)

영속 의무:
- 사이클 14 fetch_daily_candles 재사용 (별도 함수, 변경 0)
- 사이클 17 KIS LMS chain (kis_get_quote 경유 Rate Limit + 윈도우 간 sleep)
- 사이클 38 명문화 (scanner 매수 진입 전 영역)
- 사이클 88 G-REJECT graceful
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

pytestmark = pytest.mark.unit


def _candle(bas_dd: str, close: int = 70000) -> dict:
    return {
        "stck_bsop_date": bas_dd,
        "stck_clpr": str(close),
        "stck_oprc": str(close - 500),
        "stck_hgpr": str(close + 500),
        "stck_lwpr": str(close - 1000),
        "acml_vol": "12345678",
        "acml_tr_pbmn": "876543210000",
        "flng_cls_code": "",
        "prtt_rate": "0",
    }


# ---------------------------------------------------------------------------
# RANGE-1 — fetch_daily_candles_ranged 단일 윈도우 호출 + output2 파싱
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_range1_single_window_parse(monkeypatch):
    """fetch_daily_candles_ranged — 단일 KIS 호출 + output2 파싱 + placeholder 제거."""
    from src.api import condition

    mock_get = AsyncMock(
        return_value={
            "output2": [
                _candle("20260620"),
                _candle("20260619"),
                {"stck_bsop_date": "", "stck_clpr": "0"},  # placeholder 제거 대상
            ]
        }
    )
    monkeypatch.setattr(condition, "kis_get_quote", mock_get)

    rows = await condition.fetch_daily_candles_ranged("005930", "20260601", "20260620")

    assert mock_get.await_count == 1, "단일 윈도우 = KIS 1회 호출"
    # placeholder (빈 bas_dd) 제거
    assert all(r.get("stck_bsop_date") for r in rows), "빈 bas_dd placeholder 제거"
    assert len(rows) == 2
    assert {r["stck_bsop_date"] for r in rows} == {"20260620", "20260619"}


# ---------------------------------------------------------------------------
# RANGE-2 — FID_ORG_ADJ_PRC="0" 기존 정합 (173 동등성 게이트)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_range2_org_adj_prc_zero(monkeypatch):
    """FID_ORG_ADJ_PRC="0" (수정주가) — 기존 fetch_daily_candles 정합."""
    from src.api import condition

    captured = {}

    async def fake_get(url, tr_id, params):
        captured["url"] = url
        captured["tr_id"] = tr_id
        captured["params"] = params
        return {"output2": [_candle("20260620")]}

    monkeypatch.setattr(condition, "kis_get_quote", fake_get)

    await condition.fetch_daily_candles_ranged("005930", "20260601", "20260620")

    assert captured["tr_id"] == "FHKST03010100", "KIS MCP 정본 TR_ID"
    assert captured["params"]["FID_ORG_ADJ_PRC"] == "0", \
        "기존 fetch_daily_candles 와 동일 '0' (수정주가) — 173 동등성 게이트 보장"
    assert captured["params"]["FID_PERIOD_DIV_CODE"] == "D"
    assert captured["params"]["FID_COND_MRKT_DIV_CODE"] == "J"


# ---------------------------------------------------------------------------
# RANGE-3 — FID_INPUT_DATE_1/2 start/end 전달
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_range3_date_range_passed(monkeypatch):
    """FID_INPUT_DATE_1=start / FID_INPUT_DATE_2=end 전달."""
    from src.api import condition

    captured = {}

    async def fake_get(url, tr_id, params):
        captured.update(params)
        return {"output2": [_candle("20260620")]}

    monkeypatch.setattr(condition, "kis_get_quote", fake_get)

    await condition.fetch_daily_candles_ranged("005930", "20251101", "20260210")

    assert captured["FID_INPUT_DATE_1"] == "20251101"
    assert captured["FID_INPUT_DATE_2"] == "20260210"
    assert captured["FID_INPUT_ISCD"] == "005930"


# ---------------------------------------------------------------------------
# RANGE-4 — 6자리 ticker 가드 + graceful 빈 응답
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_range4_ticker_guard_and_empty(monkeypatch):
    """6자리 미준수 ticker → ValueError. 빈 응답 → 빈 list graceful."""
    from src.api import condition

    # 6자리 가드
    with pytest.raises(ValueError):
        await condition.fetch_daily_candles_ranged("ABC", "20260601", "20260620")

    # 빈 응답 graceful
    mock_get = AsyncMock(return_value={"output2": []})
    monkeypatch.setattr(condition, "kis_get_quote", mock_get)
    rows = await condition.fetch_daily_candles_ranged("005930", "20260601", "20260620")
    assert rows == []


# ---------------------------------------------------------------------------
# BACKFILL-1 — 3 윈도우 호출 (220일 = 100 ×3)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_backfill1_three_windows(monkeypatch):
    """fetch_daily_candles_backfill — 220일 = 100일 윈도우 ×3 순차 호출."""
    from src.api import condition

    calls: list[tuple[str, str]] = []

    async def fake_ranged(ticker, start, end):
        calls.append((start, end))
        # 각 윈도우 별 고유 bas_dd (겹침 없음 가정)
        base = {"0": "2025", "1": "2026"}
        return [_candle(f"2026{len(calls):02d}01")]

    monkeypatch.setattr(condition, "fetch_daily_candles_ranged", fake_ranged)
    # 윈도우 간 sleep graceful (실제 대기 회피)
    monkeypatch.setattr(condition.asyncio, "sleep", AsyncMock())

    rows = await condition.fetch_daily_candles_backfill("005930", total_days=220, window=100)

    assert len(calls) == 3, "ceil(220/100) = 3 윈도우 호출"
    assert len(rows) == 3


# ---------------------------------------------------------------------------
# BACKFILL-2 — 중복 bas_dd dedupe (윈도우 경계 겹침)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_backfill2_dedupe_overlap(monkeypatch):
    """윈도우 경계 겹침 시 동일 bas_dd 중복 제거."""
    from src.api import condition

    async def fake_ranged(ticker, start, end):
        # 모든 윈도우가 동일 bas_dd 일부 반환 (경계 겹침 시뮬)
        return [_candle("20260620"), _candle("20260619")]

    monkeypatch.setattr(condition, "fetch_daily_candles_ranged", fake_ranged)
    monkeypatch.setattr(condition.asyncio, "sleep", AsyncMock())

    rows = await condition.fetch_daily_candles_backfill("005930", total_days=220, window=100)

    bas_dds = [r["stck_bsop_date"] for r in rows]
    assert len(bas_dds) == len(set(bas_dds)), "중복 bas_dd dedupe"
    assert set(bas_dds) == {"20260620", "20260619"}


# ---------------------------------------------------------------------------
# BACKFILL-3 — bas_dd DESC 병합 정렬
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_backfill3_desc_sort(monkeypatch):
    """병합 결과 bas_dd DESC (최신순) 정렬."""
    from src.api import condition

    windows = [
        [_candle("20251201"), _candle("20251130")],  # 오래된 윈도우
        [_candle("20260115"), _candle("20260114")],  # 중간 윈도우
        [_candle("20260310"), _candle("20260309")],  # 최신 윈도우
    ]
    call_idx = [0]

    async def fake_ranged(ticker, start, end):
        result = windows[call_idx[0]]
        call_idx[0] += 1
        return result

    monkeypatch.setattr(condition, "fetch_daily_candles_ranged", fake_ranged)
    monkeypatch.setattr(condition.asyncio, "sleep", AsyncMock())

    rows = await condition.fetch_daily_candles_backfill("005930", total_days=220, window=100)

    bas_dds = [r["stck_bsop_date"] for r in rows]
    assert bas_dds == sorted(bas_dds, reverse=True), "bas_dd DESC 최신순 정렬"
    assert bas_dds[0] == "20260310"
    assert bas_dds[-1] == "20251130"


# ---------------------------------------------------------------------------
# BACKFILL-4 — fetch_daily_candles 변경 0 (memcache/single-flight 영속)
# ---------------------------------------------------------------------------
def test_backfill4_fetch_daily_candles_unchanged():
    """기존 fetch_daily_candles 는 별도 함수 — memcache/single-flight 영속."""
    from src.api import condition

    src = inspect.getsource(condition.fetch_daily_candles)
    # 기존 캐시/single-flight 패턴 영속
    assert "_candle_cache" in src, "fetch_daily_candles memcache 영속"
    assert "_inflight_candle" in src, "fetch_daily_candles single-flight 영속"
    assert "asyncio.shield" in src, "fetch_daily_candles shield 패턴 영속"

    # 신규 함수는 별도 — fetch_daily_candles 본체가 backfill/ranged 를 호출하지 않음
    assert "fetch_daily_candles_backfill" not in src
    assert "fetch_daily_candles_ranged" not in src


def test_backfill4_ast_ranged_no_memcache():
    """fetch_daily_candles_ranged 는 backfill 전용 — memcache 미사용 (AST)."""
    from src.api import condition

    src = inspect.getsource(condition.fetch_daily_candles_ranged)
    # 별도 함수 = 캐시 부재 (backfill 전용, 16:00 task만 호출)
    assert "_candle_cache" not in src, \
        "fetch_daily_candles_ranged 는 별도 캐시 미사용 (backfill 전용)"
