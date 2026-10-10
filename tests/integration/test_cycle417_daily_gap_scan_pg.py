"""cycle417 Red (통합) — 일봉 구멍 판정 SQL (`stock_master_daily.earliest_missing_bas_dd`) 실 Postgres.

계약 = `_workspace/red/cycle417/gap_fill_contract.md` §2.

## 판정
- 시장 달력 = `bas_dd < before` 인 날짜 중 **그날 행 수 >= min_rows**(기본 300)인 날의
  **최근 horizon 개**(기본 100). KIS 휴장 API 를 부르지 않고 우리 DB 로 만든다.
- 종목마다 「첫 행(`min(bas_dd)`) **이후** 달력 날짜 중 그 종목 행이 없는 가장 이른 날」.
  첫 행 이전은 구멍이 아니다(신규 상장). 마지막 행 뒤의 달력 날짜는 구멍이다
  (대상 밖에 있다 돌아온 종목 — 이번 결함의 본체).
- 반환 = `{ticker: date}` — 구멍 있는 요청 종목만. 요청하지 않은 종목·DB 에 없는 종목은 없다.
- 쿼리 수는 종목 수와 무관한 상수(1~2).

## 왜 실 Postgres 인가
판정 전부가 SQL 안의 집계(GROUP BY·HAVING·LIMIT)와 반조인에 있다. mock 은 SQL 을 실행하지 않는다.

## HEAD 기준
전부 RED — 헬퍼 부재. docker/`DATABASE_URL_TEST` 가 없으면 skip(통합은 옵셔널).
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.slow]

_HELPER = "earliest_missing_bas_dd"

# 평일 6일 + 「오늘」
D1, D2, D3, D4, D5, D6 = (date(2026, 9, 14), date(2026, 9, 15), date(2026, 9, 16),
                          date(2026, 9, 17), date(2026, 9, 18), date(2026, 9, 21))
ALL6 = (D1, D2, D3, D4, D5, D6)
TODAY = date(2026, 9, 22)
BG = ("900001", "900002", "900003")     # 달력을 세우는 배경 종목 (min_rows=3)

_INSERT = "INSERT INTO stock_master_daily (ticker, bas_dd) VALUES ($1, $2)"


async def _seed(pg, pairs) -> None:
    await pg.executemany(_INSERT, list(pairs))


async def _seed_bg(pg, dates) -> None:
    await _seed(pg, [(t, d) for d in dates for t in BG])


async def _call(tickers, **kw):
    from src.db import stock_master_daily as smd
    return await getattr(smd, _HELPER)(tickers, **kw)


# ══════════════════════════════════════════════════════════════════════
# 1 — 달력 = 행 수 >= 300 인 날만 (기본 상수로 경계를 잰다)
# ══════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_i1_calendar_uses_dates_with_at_least_300_rows(clean_stock_master_daily):
    """P(09-18)=300행 → 달력 · Q(09-16)=299행 → 달력 아님.

    X 는 09-14 에만 행이 있다 → 가장 이른 빈 날 = P. `> 300` 이면 {} · 임계 무시면 Q 가 나온다.
    """
    pg = clean_stock_master_daily
    p, q, e = date(2026, 9, 18), date(2026, 9, 16), date(2026, 9, 14)
    bg = [f"8{i:05d}" for i in range(300)]
    await _seed(pg, [(t, p) for t in bg])            # 300행
    await _seed(pg, [(t, q) for t in bg[:299]])      # 299행
    await _seed(pg, [("000010", e)])

    got = await _call(["000010", bg[0], bg[299]], before=TODAY)

    assert got == {"000010": p}, (
        f"달력 경계(>= 300) 위반 — 실측 {got}. "
        f"{bg[0]}(첫 행 Q, P 보유)·{bg[299]}(첫 행 P) 는 구멍이 없어야 한다"
    )


# ══════════════════════════════════════════════════════════════════════
# 2 — 첫 행 이전은 구멍이 아니다 (신규 상장)
# ══════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_i2_dates_before_first_row_are_not_gaps(clean_stock_master_daily):
    pg = clean_stock_master_daily
    await _seed_bg(pg, ALL6)
    await _seed(pg, [("000020", d) for d in (D4, D5, D6)])   # D4 상장, 빈 날 없음
    await _seed(pg, [("000021", d) for d in (D4, D6)])       # D4 상장, D5 빔

    got = await _call(["000020", "000021"], before=TODAY, min_rows=3)

    assert got == {"000021": D5}, (
        f"첫 행 이전(D1~D3)을 구멍으로 셌다 — 실측 {got}"
    )


# ══════════════════════════════════════════════════════════════════════
# 3 — 가장 이른 빈 날 · 구멍 없음 · DB 에 없음 · 요청 밖
# ══════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_i3_earliest_missing_and_absent_cases(clean_stock_master_daily):
    pg = clean_stock_master_daily
    await _seed_bg(pg, ALL6)
    await _seed(pg, [("000030", d) for d in (D1, D2, D4, D6)])   # D3·D5 빔 → D3
    await _seed(pg, [("000031", d) for d in ALL6])               # 구멍 없음
    await _seed(pg, [("000033", d) for d in (D1, D6)])           # 구멍 있지만 요청 밖

    got = await _call(["000030", "000031", "000032"], before=TODAY, min_rows=3)

    assert got == {"000030": D3}, f"실측 {got}"
    assert all(isinstance(k, str) for k in got)
    assert type(got["000030"]) is date, (
        f"값은 `datetime.date` — 실측 {type(got['000030'])!r}"
    )


# ══════════════════════════════════════════════════════════════════════
# 4 — 마지막 행 뒤의 달력 날짜도 구멍 (대상 밖에 있다 돌아온 종목 = 이번 결함)
# ══════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_i4_dates_after_last_row_are_gaps(clean_stock_master_daily):
    """D2 뒤 대상에서 빠졌다 돌아온 종목 — 가장 이른 빈 날 = D3."""
    pg = clean_stock_master_daily
    await _seed_bg(pg, ALL6)
    await _seed(pg, [("003200", d) for d in (D1, D2)])

    got = await _call(["003200"], before=TODAY, min_rows=3)

    assert got == {"003200": D3}, f"실측 {got}"


# ══════════════════════════════════════════════════════════════════════
# 5 — 달력 = 「before 이전」 의 「최근」 horizon 개
# ══════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_i5_horizon_is_most_recent_dates_strictly_before(clean_stock_master_daily):
    """horizon=3 → 달력 = {D4, D5, D6}. 오늘(before) 행은 달력이 아니다.

    - 000050: D2·D3 빔(지평 밖) + 오늘 없음 → 구멍 없음 (가장 오래된 3개로 잡으면 D2 가 나온다)
    - 000051: D5 빔 → D5
    - 000052: 오늘만 없음 → 구멍 없음 (`<=` 로 잡으면 오늘이 나온다)
    """
    pg = clean_stock_master_daily
    await _seed_bg(pg, ALL6 + (TODAY,))
    await _seed(pg, [("000050", d) for d in (D1, D4, D5, D6)])
    await _seed(pg, [("000051", d) for d in (D1, D2, D3, D4, D6)])
    await _seed(pg, [("000052", d) for d in ALL6])

    got = await _call(["000050", "000051", "000052"], before=TODAY, horizon=3, min_rows=3)

    assert got == {"000051": D5}, f"실측 {got}"


# ══════════════════════════════════════════════════════════════════════
# 6 — 쿼리 수 = 종목 수와 무관한 상수 (<= 2)
# ══════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_i6_query_count_is_constant(clean_stock_master_daily, monkeypatch):
    pg = clean_stock_master_daily
    await _seed_bg(pg, ALL6)
    many = [f"1{i:05d}" for i in range(40)]
    await _seed(pg, [(t, D1) for t in many])          # 40종목 전부 D2 부터 빔

    calls = {"n": 0}
    for name in ("fetch", "fetchrow", "fetchval", "execute", "executemany"):
        orig = getattr(pg, name)

        def _spy(*a, _orig=orig, **k):
            calls["n"] += 1
            return _orig(*a, **k)

        monkeypatch.setattr(pg, name, _spy)

    calls["n"] = 0
    small = await _call(many[:2], before=TODAY, min_rows=3)
    n_small = calls["n"]

    calls["n"] = 0
    big = await _call(many, before=TODAY, min_rows=3)
    n_big = calls["n"]

    assert small == {t: D2 for t in many[:2]}
    assert big == {t: D2 for t in many}
    assert n_small == n_big, f"쿼리 수가 종목 수를 따라 변한다 — 2종목 {n_small} / 40종목 {n_big}"
    assert 1 <= n_big <= 2, f"쿼리 1~2회 계약 — 실측 {n_big}"


# ══════════════════════════════════════════════════════════════════════
# 7 — cycle437(카드 #10 ③) `calendar_size` — `earliest_missing_bas_dd` 와 같은 달력
# ══════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_i7_calendar_size_matches_earliest_missing_calendar(clean_stock_master_daily):
    """`cal` CTE 행 수 — 행 수 >= min_rows 인 날만, horizon 개 상한, `before` 미포함."""
    from src.db import stock_master_daily as smd

    pg = clean_stock_master_daily
    p, q = date(2026, 9, 18), date(2026, 9, 16)   # P=300행 달력 포함 / Q=299행 제외
    bg = [f"8{i:05d}" for i in range(300)]
    await _seed(pg, [(t, p) for t in bg])
    await _seed(pg, [(t, q) for t in bg[:299]])

    got = await smd.calendar_size(TODAY)
    assert got == 1, f"행 수 >= 300 인 날만 달력 — 실측 {got}"


@pytest.mark.asyncio
async def test_i8_calendar_size_capped_at_horizon(clean_stock_master_daily):
    """달력 일수가 horizon 을 넘으면 horizon 에서 멈춘다 — `earliest_missing_bas_dd` 와 동치."""
    from src.db import stock_master_daily as smd

    pg = clean_stock_master_daily
    dates = [date(2026, 1, 1) + timedelta(days=i) for i in range(5)]
    await _seed_bg(pg, dates)   # BG = 3종목 — min_rows=3 으로 호출

    got = await smd.calendar_size(TODAY, horizon=3, min_rows=3)
    assert got == 3, f"horizon=3 상한 — 실측 {got}"


@pytest.mark.asyncio
async def test_i9_calendar_size_empty_table_is_zero(clean_stock_master_daily):
    """빈 테이블 = 0(예외 아님)."""
    from src.db import stock_master_daily as smd

    got = await smd.calendar_size(TODAY)
    assert got == 0
