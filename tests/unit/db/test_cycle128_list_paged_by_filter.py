"""사이클 128 P1-2 — list_paged_by_filter() 신규 메서드 회귀 가드.

신규 메서드 명세:
- 시그너처: list_paged_by_filter(*, market, min_market_cap, min_trade_amount, name_substr, limit, offset)
- 반환: {"items": list[dict], "total": int, "limit": int, "offset": int}
- 정렬: refreshed_at DESC 영속 (기존 list_all 답습)
- 필터: 모두 optional. 빈 필터 = 전체 (list_all 동등) 회귀 가드 의무 (T-1)
- market: "KOSPI" | "KOSDAQ" | None
- min_market_cap: int (원 단위) | 0 (무필터)
- min_trade_amount: int (원 단위) | 0 (무필터)
- name_substr: str | None (대소문자 무시 substring)

영속 의무:
- 사이클 84 GET 영역 영속
- 사이클 108 list_by_filter (scanner 전용) 와 분리 — UI list 신규 별개 함수
- 사이클 126 count="exact" 답습 (total 정확)
"""
from __future__ import annotations

import re
from unittest.mock import AsyncMock, patch

import pytest

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# 사이클 M2b (Supabase→RDS asyncpg 전환) — pg.fetchval/fetch 경유.
# list_paged_by_filter 는 WHERE 절 predicate (`<col> = $N` / `<col> ILIKE $N` /
# `<col> >= $N` / LIMIT $N OFFSET $M) 를 SQL 텍스트로 발화하고 args 를 append 순서로
# 바인딩한다. placeholder ↔ arg 매핑으로 (col, val) 을 복원해 seen 에 기록.
# ---------------------------------------------------------------------------
def _record_clauses(sql: str, args: tuple, seen: dict) -> None:
    for m in re.finditer(r"(\w+)\s*>=\s*\$(\d+)", sql):
        col, idx = m.group(1), int(m.group(2))
        if 1 <= idx <= len(args):
            seen.setdefault("gte", []).append((col, args[idx - 1]))
    for m in re.finditer(r"(\w+)\s+ILIKE\s+\$(\d+)", sql, re.IGNORECASE):
        col, idx = m.group(1), int(m.group(2))
        if 1 <= idx <= len(args):
            seen.setdefault("ilike", []).append((col, args[idx - 1]))
    for m in re.finditer(r"(\w+)\s*=\s*\$(\d+)", sql):
        col, idx = m.group(1), int(m.group(2))
        if 1 <= idx <= len(args):
            seen.setdefault("eq", []).append((col, args[idx - 1]))
    lm = re.search(r"LIMIT\s+\$(\d+)\s+OFFSET\s+\$(\d+)", sql, re.IGNORECASE)
    if lm:
        li, oi = int(lm.group(1)), int(lm.group(2))
        if 1 <= li <= len(args) and 1 <= oi <= len(args):
            seen["range"] = (args[oi - 1], args[oi - 1] + args[li - 1] - 1)


async def _run(total_count: int, rows: list[dict], **kwargs):
    """pg.fetchval(count) + pg.fetch(rows) 경유 실행. (result, seen) 반환."""
    from src.db import stock_master

    seen: dict = {"eq": [], "ilike": [], "gte": []}

    async def _fetchval(sql, *args):
        _record_clauses(sql, args, seen)
        return total_count

    async def _fetch(sql, *args):
        _record_clauses(sql, args, seen)
        return rows

    with patch.object(stock_master, "pg", create=True) as pg_mod:
        pg_mod.fetchval = AsyncMock(side_effect=_fetchval)
        pg_mod.fetch = AsyncMock(side_effect=_fetch)
        result = await stock_master.list_paged_by_filter(**kwargs)
    return result, seen


@pytest.mark.asyncio
async def test_g_list1_empty_filter_equals_list_all():
    """G-LIST1: 빈 필터 = list_all 동등 (T-1 영속). items/total/limit/offset 반환."""
    sample_rows = [
        {"ticker": f"00000{i}", "name": f"종목{i}", "refreshed_at": "2026-06-13T10:00:00+09:00"}
        for i in range(10)
    ]
    result, _seen = await _run(2697, sample_rows, limit=100, offset=0)

    assert "items" in result and "total" in result and "limit" in result and "offset" in result
    assert result["limit"] == 100
    assert result["offset"] == 0
    assert result["total"] == 2697
    assert result["items"] == sample_rows


@pytest.mark.asyncio
async def test_g_list2_market_kospi_filter_applies_excg_dvsn_eq():
    """G-LIST2: market="KOSPI" 시 excg_dvsn_cd="02" eq 필터 적용."""
    result, seen = await _run(
        800, [{"ticker": "005930", "excg_dvsn_cd": "02"}], market="KOSPI", limit=50, offset=0,
    )

    assert ("excg_dvsn_cd", "02") in set(seen["eq"]), (
        f"KOSPI → excg_dvsn_cd='02' eq 필터 의무. 실제 eq: {seen['eq']}"
    )
    assert result["total"] == 800


@pytest.mark.asyncio
async def test_g_list3_market_kosdaq_filter_applies_excg_dvsn_eq():
    """G-LIST3: market="KOSDAQ" 시 excg_dvsn_cd="03" eq 필터 적용."""
    _result, seen = await _run(1500, [], market="KOSDAQ", limit=50, offset=0)

    assert ("excg_dvsn_cd", "03") in set(seen["eq"])


@pytest.mark.asyncio
async def test_g_list4_name_substr_ilike_applies():
    """G-LIST4: name_substr 지정 시 name ILIKE "%삼성%" 필터 적용."""
    result, seen = await _run(
        12, [{"ticker": "005930", "name": "삼성전자"}], name_substr="삼성", limit=50, offset=0,
    )

    assert any(
        col == "name" and "삼성" in pat and pat.startswith("%") and pat.endswith("%")
        for col, pat in seen["ilike"]
    ), f"name_substr → name ILIKE '%삼성%' 의무. 실제: {seen['ilike']}"
    assert result["total"] == 12


@pytest.mark.asyncio
async def test_g_list5_offset_and_total_propagate():
    """G-LIST5: offset / limit / total 정합 — 응답에 포함되어야 한다 (range→LIMIT/OFFSET)."""
    rows = [{"ticker": f"00000{i}"} for i in range(50)]
    result, seen = await _run(500, rows, limit=50, offset=100)

    assert result["limit"] == 50
    assert result["offset"] == 100
    assert result["total"] == 500
    # LIMIT/OFFSET 바인딩 = offset 100 + limit 50 → range (100, 149)
    assert seen.get("range") == (100, 149)


@pytest.mark.asyncio
async def test_g_list6_min_market_cap_filter_applies():
    """G-LIST6: min_market_cap > 0 시 생성 컬럼 hts_avls_eok gte 필터 적용 (사이클 166/168).

    raw.hts_avls 단위는 억원 → min_market_cap (원) / 100_000_000 환산 후 비교.
    예: min_market_cap=1_000_000_000_000 (1조 원) → hts_avls_eok >= 10_000 (억원).
    """
    _result, seen = await _run(50, [], min_market_cap=1_000_000_000_000, limit=50, offset=0)

    hts_filter_applied = any("avls" in str(col).lower() for col, _ in seen["gte"])
    assert hts_filter_applied, (
        f"min_market_cap → hts_avls_eok 영역 gte 필터 의무. 실제 gte: {seen['gte']}"
    )


@pytest.mark.asyncio
async def test_g_list7_min_trade_amount_filter_applies():
    """G-LIST7: min_trade_amount > 0 시 생성 컬럼 acml_tr_pbmn_won gte 필터 (사이클 168)."""
    _result, seen = await _run(30, [], min_trade_amount=10_000_000_000, limit=50, offset=0)

    pbmn_applied = any("acml_tr_pbmn" in str(c) for c, _ in seen["gte"])
    assert pbmn_applied, (
        f"min_trade_amount → acml_tr_pbmn_won 영역 gte 필터 의무. 실제 gte: {seen['gte']}"
    )
