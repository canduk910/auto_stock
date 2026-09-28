"""cycle386 Red (통합 G1) — 「잠정 봉」 판정 SQL 의 경계 + `updated_at` 불변식 + 부팅 확정 왕복 (실 Postgres).

명세 = `_workspace/domain_consult/cycle386_daily_close_after_market.md` §8-3 (판정) · §8-8 (1회 복구) · §8-9 G1.

## 판정 (§8-3)
`T` = 오늘(KST), `P` = 헤드, `T06` = T 06:00 KST.
- 헤드(`bas_dd = P`): `updated_at < T06` 이면 잠정 — 주말·연휴 중 쓰기(금요일 봉을 토요일에 받음)도 잠정.
- 그 밖(`bas_dd < P`): `updated_at < (bas_dd + 1) 06:00 KST` 이면 잠정.
- 창: `since ≤ bas_dd ≤ P`. 오늘 봉은 대상이 아니다.

실측 근거(§4-2): D 20:30 · D 23:09~23:12 은 가짜(26/30) · D+1 05:28 은 거의 확정(10/11) · D+1 07:56 은 확정(25/25).

## 왜 실 Postgres 인가
경계가 SQL 안의 날짜 산술·시간대 변환(`(bas_dd + 1)::timestamp AT TIME ZONE 'Asia/Seoul' + 6h`)에 있다. mock 은 SQL 을
실행하지 않는다. 그리고 같은 SQL 을 **세션 시간대 UTC** 연결로 다시 돌려 결과가 같아야 한다 — 풀의
`server_settings` 에 기대는 판정은 연결이 재사용될 때 `Etc/UTC` 로 돌아간 사고(`src/db/pg.py::_init_conn`)를 다시 만든다.

## 돌연변이
M1(헤드도 `(bas_dd+1) 06:00`) → 토요일 쓰기 행이 빠진다 · M2(`+6h` 제거 = 자정 경계) → D+1 05:59 행이 빠진다 ·
시간대 누락 → UTC 연결 비교가 갈린다.

## HEAD 기준
전부 RED — `list_provisional_rows`·leaf 부재. docker/`DATABASE_URL_TEST` 가 없으면 skip(통합은 옵셔널).
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.slow, pytest.mark.real_daily_bar_finalize]

KST = timezone(timedelta(hours=9))


def _kst(y, m, d, hh, mm, ss=0) -> datetime:
    return datetime(y, m, d, hh, mm, ss, tzinfo=KST)


async def _insert(pg, ticker: str, bas_dd: date, updated_at: datetime, *, close: int = 1000,
                  high: int = 1100, low: int = 900, open_: int = 950) -> None:
    raw = {"stck_bsop_date": bas_dd.strftime("%Y%m%d"), "stck_clpr": str(close), "stck_hgpr": str(high),
           "stck_lwpr": str(low), "stck_oprc": str(open_)}
    await pg.execute(
        """
        INSERT INTO stock_master_daily (ticker, bas_dd, open_price, high_price, low_price, close_price,
                                        volume, trade_value, change_rate, flng_cls_code, prtt_rate, raw, updated_at)
        VALUES ($1, $2, $3, $4, $5, $6, 1000, 1000000, 0, '00', 0, $7::jsonb, $8)
        """,
        ticker, bas_dd, open_, high, low, close, raw, updated_at,
    )


# 시나리오 A — T=09-29(화), P=09-28(월), since=09-08
_T_A = date(2026, 9, 29)
_P_A = date(2026, 9, 28)
_D = date(2026, 9, 23)     # 헤드가 아닌 봉
_ROWS_A = [
    # (ticker, bas_dd, updated_at, 잠정인가)
    ("000010", _D, _kst(2026, 9, 23, 20, 30), True),     # D 20:30 정기 적재
    ("000020", _D, _kst(2026, 9, 23, 23, 12), True),     # D 23:12 수동 적재(C묶음 가짜)
    ("000030", _D, _kst(2026, 9, 24, 5, 59), True),      # D+1 05:59 — 경계 1분 전(M2 가 여기서 죽는다)
    ("000040", _D, _kst(2026, 9, 24, 6, 0), False),      # D+1 06:00 — 경계 포함 아님(`<`)
    ("000050", _D, _kst(2026, 9, 24, 7, 46), False),     # D+1 07:46 이 설계가 덮은 행
    ("000060", _P_A, _kst(2026, 9, 28, 20, 30), True),   # 헤드 20:30
    ("000070", _P_A, _kst(2026, 9, 29, 5, 59), True),    # 헤드, 오늘 05:59
    ("000080", _P_A, _kst(2026, 9, 29, 6, 0), False),    # 헤드, 오늘 06:00
    ("000100", date(2026, 9, 16), _kst(2026, 9, 16, 20, 31), True),   # 유니버스 이탈로 남은 가짜 봉
    ("000110", date(2026, 9, 7), _kst(2026, 9, 7, 20, 30), False),    # since(09-08) 전 — 창 밖
    ("000111", date(2026, 9, 8), _kst(2026, 9, 8, 20, 30), True),     # since 당일 — 창 안
    ("000120", _T_A, _kst(2026, 9, 29, 7, 50), False),   # 오늘 봉 — 대상 아님
    ("000130", date(2026, 9, 22), _kst(2026, 9, 22, 20, 30), True),
    ("000130", _D, _kst(2026, 9, 24, 7, 46), False),
    ("000130", _P_A, _kst(2026, 9, 28, 20, 30), True),
]


def _args_a() -> dict:
    return dict(since=_T_A - timedelta(days=21), head=_P_A,
                today_boundary=datetime.combine(_T_A, time(6, 0), tzinfo=KST))


@pytest.mark.asyncio
async def test_g1_1_boundaries(clean_stock_master_daily):
    from src.db import stock_master_daily as smd

    pg = clean_stock_master_daily
    for t, d, ts, _ in _ROWS_A:
        await _insert(pg, t, d, ts)

    rows = await smd.list_provisional_rows(**_args_a())

    got = {(r["ticker"], r["bas_dd"]) for r in rows}
    want = {(t, d) for t, d, _, prov in _ROWS_A if prov}
    assert got == want, (
        f"잠정 판정이 틀렸다 — 빠진 것 {sorted(want - got)} / 더 들어온 것 {sorted(got - want)}"
    )
    r0 = next(r for r in rows if r["ticker"] == "000010")
    for k in ("open_price", "high_price", "low_price", "close_price"):
        assert k in r0, f"비교에 쓸 `{k}` 를 돌려주지 않는다"


@pytest.mark.asyncio
async def test_g1_2_head_uses_today_six_even_for_a_weekend_write(clean_stock_master_daily):
    """T=09-28(월), P=09-25(금). 헤드를 토요일 10:00 에 손으로 다시 받았다 → 여전히 잠정(M1)."""
    from src.db import stock_master_daily as smd

    pg = clean_stock_master_daily
    fri, mon = date(2026, 9, 25), date(2026, 9, 28)
    await _insert(pg, "000090", fri, _kst(2026, 9, 26, 10, 0))     # 토요일 10:00
    await _insert(pg, "000091", fri, _kst(2026, 9, 28, 7, 46))     # 월요일 아침 확정

    rows = await smd.list_provisional_rows(
        since=mon - timedelta(days=21), head=fri,
        today_boundary=datetime.combine(mon, time(6, 0), tzinfo=KST),
    )

    assert {r["ticker"] for r in rows} == {"000090"}, (
        "비영업일 쓰기의 헤드를 확정으로 봤다 — KIS 야간 처리가 주말에도 도는지 모른다(§8-3)"
    )


@pytest.mark.asyncio
async def test_g1_3_result_does_not_depend_on_the_session_time_zone(clean_stock_master_daily, pg_migrated, monkeypatch):
    """같은 SQL·같은 인자를 세션 시간대 UTC 연결로 다시 돌려도 결과가 같다."""
    import asyncpg

    import src.db.pg as pgmod
    from src.db import stock_master_daily as smd

    pg = clean_stock_master_daily
    for t, d, ts, _ in _ROWS_A:
        await _insert(pg, t, d, ts)

    captured: list[tuple[str, tuple]] = []
    real_fetch = pgmod.fetch

    async def _spy(sql, *args):
        captured.append((sql, args))
        return await real_fetch(sql, *args)

    monkeypatch.setattr(pgmod, "fetch", _spy)
    rows = await smd.list_provisional_rows(**_args_a())
    assert len(captured) == 1, "대상 조회는 pg.fetch 1회"
    sql, args = captured[0]

    conn = await asyncpg.connect(pg_migrated, server_settings={"timezone": "UTC"})
    try:
        tz = await conn.fetchval("SHOW timezone")
        assert tz.upper() in ("UTC", "ETC/UTC")
        utc_rows = await conn.fetch(sql, *args)
    finally:
        await conn.close()

    assert {(r["ticker"], r["bas_dd"]) for r in utc_rows} == {(r["ticker"], r["bas_dd"]) for r in rows}, (
        "세션 시간대에 따라 잠정 판정이 갈린다 — SQL 안 날짜 경계에 'Asia/Seoul' 을 명시하라"
    )


# ===========================================================================
# updated_at 불변식 — 쓰는 순간을 찍는다 · 트리거 없음
# ===========================================================================
@pytest.mark.asyncio
async def test_g1_4_upsert_restamps_updated_at_on_conflict(clean_stock_master_daily, monkeypatch):
    from src.db import stock_master_daily as smd

    pg = clean_stock_master_daily
    await _insert(pg, "394800", date(2026, 9, 23), _kst(2026, 9, 23, 20, 30), close=5520)
    monkeypatch.setattr(smd, "now_kst_iso", lambda: "2026-09-28T07:46:30+09:00")

    n = await smd.upsert_batch("394800", [{
        "stck_bsop_date": "20260923", "stck_oprc": "5700", "stck_hgpr": "6100",
        "stck_lwpr": "5280", "stck_clpr": "5800", "acml_vol": "3785681",
    }])

    assert n == 1
    row = await pg.fetchrow("SELECT close_price, updated_at FROM stock_master_daily WHERE ticker='394800'")
    assert row["close_price"] == 5800
    assert row["updated_at"] == _kst(2026, 9, 28, 7, 46, 30), (
        f"다시 받아 쓴 행의 updated_at 이 옛 시각이다 — 영원히 잠정으로 남는다: {row['updated_at']!r}"
    )


@pytest.mark.asyncio
async def test_g1_5_no_trigger_rewrites_updated_at(clean_stock_master_daily):
    """트리거가 updated_at 을 바꾸면 「KIS 값을 받아 쓴 시각」 이라는 뜻이 무너진다."""
    pg = clean_stock_master_daily
    n = await pg.fetchval(
        "SELECT count(*) FROM pg_trigger WHERE tgrelid = 'stock_master_daily'::regclass AND NOT tgisinternal"
    )
    assert n == 0, f"stock_master_daily 에 트리거 {n}개"


# ===========================================================================
# 부팅 확정 왕복 — 실 SQL 대상 조회 + 실 upsert + 실 system_config/positions, KIS 만 가짜
# ===========================================================================
@pytest.mark.asyncio
async def test_g1_6_finalize_round_trip_then_same_day_restart_is_noop(
    clean_stock_master_daily, clean_positions, monkeypatch, caplog,
):
    import logging

    import src.api.condition as cond
    from src.db import stock_master_daily as smd
    from src.engine import daily_bar_finalize as dbf

    pg = clean_stock_master_daily
    await pg.execute("DELETE FROM system_config WHERE key = 'daily_bar_finalize_mode'")
    P, T = date(2026, 9, 23), date(2026, 9, 28)
    # 앞 봉(확정) + 헤드(20:30 가짜)
    await _insert(pg, "394800", date(2026, 9, 22), _kst(2026, 9, 23, 7, 50), close=5600)
    await _insert(pg, "394800", P, _kst(2026, 9, 23, 20, 30), close=5520, high=6100, low=5280, open_=5700)
    # 유니버스 이탈로 남은 옛 가짜 봉
    await _insert(pg, "012320", date(2026, 9, 14), _kst(2026, 9, 14, 20, 30), close=52300, high=53400)

    truth = {
        "394800": [
            {"stck_bsop_date": "20260923", "stck_oprc": "5700", "stck_hgpr": "6100", "stck_lwpr": "5280",
             "stck_clpr": "5800", "acml_vol": "3785681"},
            {"stck_bsop_date": "20260922", "stck_oprc": "5500", "stck_hgpr": "5700", "stck_lwpr": "5400",
             "stck_clpr": "5600", "acml_vol": "1000000"},
        ],
        "012320": [
            {"stck_bsop_date": "20260914", "stck_oprc": "50000", "stck_hgpr": "51600", "stck_lwpr": "49800",
             "stck_clpr": "50400", "acml_vol": "10000"},
        ],
    }

    async def _fetch(ticker, start, end):
        return {"stck_prdy_clpr": "5800"}, [dict(b) for b in truth[ticker]]

    monkeypatch.setattr(cond, "fetch_daily_chart_ranged_with_summary", _fetch, raising=False)
    monkeypatch.setattr(smd, "now_kst_iso", lambda: "2026-09-28T07:46:30+09:00")
    caplog.set_level(logging.INFO)

    await dbf.finalize_once(now_kst=_kst(2026, 9, 28, 7, 46), phase="boot")

    c = await pg.fetchval("SELECT close_price FROM stock_master_daily WHERE ticker='394800' AND bas_dd=$1", P)
    assert c == 5800, "헤드 봉 종가가 정규장 종가로 바뀌지 않았다"
    h = await pg.fetchval("SELECT high_price FROM stock_master_daily WHERE ticker='012320' AND bas_dd=$1",
                          date(2026, 9, 14))
    assert h == 51600, "유니버스 이탈로 남은 옛 가짜 봉(§4-3)이 고쳐지지 않았다"
    left = await smd.list_provisional_rows(
        since=T - timedelta(days=21), head=P, today_boundary=datetime.combine(T, time(6, 0), tzinfo=KST),
    )
    assert left == [], f"확정 뒤에도 잠정 행이 남았다 — {left}"
    first = [r for r in caplog.records if r.getMessage().startswith("[daily_bar_finalize] ")]
    assert len(first) == 1 and "result=ok" in first[0].getMessage(), [r.getMessage() for r in first]

    caplog.clear()
    await dbf.finalize_once(now_kst=_kst(2026, 9, 28, 8, 10), phase="boot")
    again = [r.getMessage() for r in caplog.records if r.getMessage().startswith("[daily_bar_finalize] ")]
    assert len(again) == 1 and "result=noop" in again[0], f"같은 날 재기동이 다시 받는다 — {again}"


# ===========================================================================
# F1+F2 — 헤드 `P = max(bas_dd) WHERE bas_dd < T` (실 SQL)
# ===========================================================================
@pytest.mark.asyncio
async def test_g1_7_head_is_the_latest_bar_strictly_before_today(
    clean_stock_master_daily, clean_positions, monkeypatch, caplog,
):
    """F1+F2 — 옛 사후 클램프(`head >= today → today − 1`)는 걷혔고, 「헤드는 오늘 앞」 보장은
    이제 `max_bas_dd_before` 의 `bas_dd < $1` 하나뿐이다. 단위 하네스는 그 SQL 을 가짜로 두므로
    실 SQL 로만 잰다 — DB 에 오늘(T)·미래 날짜 행이 있어도 헤드는 T 앞 최신 봉이고, 확정은 그 헤드로
    교차검증하며 오늘 행에는 닿지 않는다.

    돌연변이: `bas_dd <= $1`(오늘 행이 헤드가 된다 → P 봉이 교차검증 없이 쓰이고 `head=` 가 오늘) ·
    조건 제거(미래 행이 헤드).
    """
    import logging

    import src.api.condition as cond
    from src.db import stock_master_daily as smd
    from src.engine import daily_bar_finalize as dbf

    pg = clean_stock_master_daily
    await pg.execute("DELETE FROM system_config WHERE key = 'daily_bar_finalize_mode'")
    P, T = date(2026, 9, 23), date(2026, 9, 28)
    await _insert(pg, "394800", date(2026, 9, 22), _kst(2026, 9, 23, 7, 50), close=5600)
    await _insert(pg, "394800", P, _kst(2026, 9, 23, 20, 30), close=5520, high=6100, low=5280, open_=5700)
    await _insert(pg, "394800", T, _kst(2026, 9, 28, 7, 50), close=5900)          # 오늘 봉(껍데기)
    await _insert(pg, "000660", date(2026, 9, 29), _kst(2026, 9, 28, 7, 50), close=1)   # 미래 날짜 행

    assert await smd.max_bas_dd_before(T) == P, "헤드가 오늘 이상이다 — §8-3 `bas_dd < T` 가 무너졌다"
    assert await smd.max_bas_dd_before(P) == date(2026, 9, 22)

    calls: list[tuple[str, str, str]] = []

    async def _fetch(ticker, start, end):
        calls.append((ticker, str(start), str(end)))
        return {"stck_prdy_clpr": "5800"}, [
            {"stck_bsop_date": "20260923", "stck_oprc": "5700", "stck_hgpr": "6100", "stck_lwpr": "5280",
             "stck_clpr": "5800", "acml_vol": "3785681"},
            {"stck_bsop_date": "20260922", "stck_oprc": "5500", "stck_hgpr": "5700", "stck_lwpr": "5400",
             "stck_clpr": "5600", "acml_vol": "1000000"},
        ]

    monkeypatch.setattr(cond, "fetch_daily_chart_ranged_with_summary", _fetch, raising=False)
    monkeypatch.setattr(smd, "now_kst_iso", lambda: "2026-09-28T07:46:30+09:00")
    caplog.set_level(logging.INFO)

    await dbf.finalize_once(now_kst=_kst(2026, 9, 28, 7, 46), phase="boot")

    ms = [r.getMessage() for r in caplog.records if r.getMessage().startswith("[daily_bar_finalize] ")]
    assert len(ms) == 1, ms
    assert f"head={P.isoformat()} " in ms[0], f"헤드가 직전 거래일이 아니다 — {ms[0]}"
    assert "verified=1 " in ms[0], f"헤드 봉을 교차검증하지 않고 썼다 — {ms[0]}"
    assert calls and all(e.replace("-", "")[:8] <= "20260923" for _, _, e in calls), (
        f"받는 구간의 끝이 헤드(P)를 넘었다 — {calls}"
    )
    c = await pg.fetchval("SELECT close_price FROM stock_master_daily WHERE ticker='394800' AND bas_dd=$1", P)
    assert c == 5800
    today_close = await pg.fetchval(
        "SELECT close_price FROM stock_master_daily WHERE ticker='394800' AND bas_dd=$1", T,
    )
    assert today_close == 5900, "오늘 봉에 손댔다"
