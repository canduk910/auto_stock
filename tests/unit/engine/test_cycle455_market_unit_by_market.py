"""cycle455 — 시장 유닛 종목 소속 시장별 판정 + 원천 = 종합지수.

명세 = `_workspace/red/cycle455_market_unit_by_market_spec.md` §2·§4·§5·§7.

| # | 계약 |
|---|---|
| L1 | `compute_snapshot(market=)` 가 `domestic_index.get_recent_closes` 를 그 시장 지수 코드로 부른다(기본 = 코스피 `0001`) · 069500 미참조 |
| L2 | `market_of` 순수(미상·`None`·지도 아님 = 코스피) · `load_market_map` = `"03"` → 코스닥, 그 밖 → 코스피, 예외 = `{}` |
| V1~V6 | view 결측 규칙 — 제 시장 ok · 코스닥 결측 → 코스피 배수 · 코스피 결측 → 코스닥 배수 · 둘 다 결측 → 1.0 · 지도 미상 → 코스피 · `ticker=None` → 코스피 |
| V7 | 같은 전략·같은 날 코스피 종목 m=0 · 코스닥 종목 m=1.0 동시 — `_market_unit_blocks_entry` 는 코스피 종목만 True |
| R1 | refresh 가 두 시장을 각각 저장하고, 미리보기(다음 거래일) 칸이 오늘 칸과 시장별로 섞이지 않는다 |
| R2 | refresh 가 비어 온 지도로 기존 지도를 지우지 않는다 |
"""
from __future__ import annotations

import logging
from datetime import date

import pytest
from freezegun import freeze_time

from tests.unit.engine._cycle382_support import (
    DAY, F2, F3, F4, HEAD, NEXT, Seams, field, lines, make, mu, need_base, open_info, rows_for, seed,
)

pytestmark = pytest.mark.unit

KS, KQ = "111111", "222222"
_BOOT = "2026-09-28T07:50:00+09:00"


def _mapped(s):
    s._market_unit_market_map = {KS: "kospi", KQ: "kosdaq"}
    return s


# ── L1 · L2 ───────────────────────────────────────────────────────────────────
@freeze_time(_BOOT)
async def test_l1_compute_snapshot_reads_index_code_per_market(monkeypatch):
    lf = mu()
    seams = Seams(rows_for(F2, HEAD), prev_day=HEAD, kq_rows=rows_for(F3, HEAD)).install(monkeypatch)
    ks = await lf.compute_snapshot(DAY, preview=False)
    kq = await lf.compute_snapshot(DAY, preview=False, market="kosdaq")
    assert [c[0] for c in seams.daily_calls] == ["0001", "1001"]
    assert (ks.market, ks.state, ks.m) == ("kospi", "up_falling", 0.75)
    assert (kq.market, kq.state, kq.m) == ("kosdaq", "down_rising", 0.5)
    unknown = await lf.compute_snapshot(DAY, preview=False, market="nyse")
    assert unknown.market == "kospi", "모르는 시장 = 코스피"


def test_l1b_leaf_no_longer_names_kodex200():
    from pathlib import Path

    src = Path("src/engine/market_unit.py").read_text(encoding="utf-8")
    assert "069500" not in src and "SOURCE_TICKER" not in src


def test_l2_market_of_is_pure_and_defaults_to_kospi():
    lf = mu()
    m = {KS: "kospi", KQ: "kosdaq", "333333": "weird"}
    assert lf.market_of(KQ, m) == "kosdaq"
    assert lf.market_of(KS, m) == "kospi"
    assert lf.market_of("333333", m) == "kospi"
    assert lf.market_of("999999", m) == "kospi"
    assert lf.market_of(None, m) == "kospi"
    assert lf.market_of(KQ, None) == "kospi"


async def test_l2b_load_market_map_maps_excg_and_never_raises(monkeypatch):
    lf = mu()

    async def ok():
        return {KS: "02", KQ: "03", "444444": "", "": "03"}

    monkeypatch.setattr("src.db.stock_master.get_market_map", ok)
    assert await lf.load_market_map() == {KS: "kospi", KQ: "kosdaq", "444444": "kospi"}

    async def boom():
        raise RuntimeError("db down")

    monkeypatch.setattr("src.db.stock_master.get_market_map", boom)
    assert await lf.load_market_map() == {}


# ── V1~V7 ─────────────────────────────────────────────────────────────────────
@freeze_time(_BOOT)
def test_v1_own_market_snapshot_wins():
    need_base()
    s = _mapped(make("kojiro", mode="enforce"))
    seed(s, 0.0, DAY)
    seed(s, 0.75, DAY, market="kosdaq")
    v_ks, v_kq = s._market_unit_view(KS), s._market_unit_view(KQ)
    assert (v_ks.m, v_ks.market, v_ks.fallback) == (0.0, "kospi", "-")
    assert (v_kq.m, v_kq.market, v_kq.fallback) == (0.75, "kosdaq", "-")


@freeze_time(_BOOT)
def test_v2_kosdaq_missing_uses_kospi_multiplier():
    need_base()
    s = _mapped(make("kojiro", mode="enforce"))
    seed(s, 0.0, DAY)
    seed(s, 1.0, DAY, market="kosdaq", ok=False, reason="stale_head")
    v = s._market_unit_view(KQ)
    assert (v.m, v.market, v.fallback, v.state) == (0.0, "kosdaq", "other_market", "down_falling")


@freeze_time(_BOOT)
def test_v3_kospi_missing_uses_kosdaq_multiplier():
    need_base()
    s = _mapped(make("kojiro", mode="enforce"))
    seed(s, 0.5, DAY, market="kosdaq")
    v = s._market_unit_view(KS)                    # 코스피 칸 자체가 없다
    assert (v.m, v.market, v.fallback) == (0.5, "kospi", "other_market")


@freeze_time(_BOOT)
def test_v4_both_missing_is_one(caplog):
    need_base()
    open_info(caplog)
    s = _mapped(make("kojiro", mode="enforce"))
    seed(s, 1.0, DAY, ok=False, reason="rows_short")
    seed(s, 1.0, DAY, market="kosdaq", ok=False, reason="rows_short")
    v = s._market_unit_view(KS)
    assert (v.m, v.state, v.fallback) == (1.0, "unavailable", "none")
    s2 = _mapped(make("kojiro", mode="enforce"))
    v2 = s2._market_unit_view(KQ)                  # 둘 다 아직 계산 전 → not_computed 경보 1줄
    assert (v2.m, v2.reason, v2.fallback) == (1.0, "not_computed", "none")
    warns = lines(caplog, "[market_unit_unavailable]", min_level=logging.WARNING)
    assert warns and field(warns[-1], "where") == "view"


@freeze_time(_BOOT)
def test_v5_v6_unknown_ticker_and_none_are_kospi():
    need_base()
    s = _mapped(make("kojiro", mode="enforce"))
    seed(s, 0.0, DAY)
    seed(s, 1.0, DAY, market="kosdaq")
    assert s._market_unit_view("999999").m == 0.0
    assert s._market_unit_view().m == 0.0
    assert s._market_unit_view(None).market == "kospi"


@freeze_time(_BOOT)
def test_v7_same_strategy_same_day_two_markets_block_only_kospi():
    need_base()
    s = _mapped(make("kojiro", mode="enforce"))
    seed(s, 0.0, DAY)
    seed(s, 1.0, DAY, market="kosdaq")
    assert s._market_unit_blocks_entry(KS, 10_000) is True
    assert s._market_unit_blocks_entry(KQ, 10_000) is False
    assert s._market_unit_sizing(10_000, KQ) is None, "코스닥 m=1 → 수량 무접촉"


# ── R1 · R2 ───────────────────────────────────────────────────────────────────
@freeze_time("2026-09-28T21:05:00+09:00")
async def test_r1_refresh_stores_each_market_and_preview_does_not_mix(monkeypatch):
    need_base()
    s = make("donchian_swing", mode="enforce")
    Seams(rows_for(F2, HEAD), prev_day=HEAD, kq_rows=rows_for(F3, HEAD),
          market_map={KS: "02", KQ: "03"}).install(monkeypatch)
    await s._refresh_market_unit(as_of_date=DAY, preview=False)
    assert (s._market_unit_snaps[DAY].m, s._market_unit_snaps_kq[DAY].m) == (0.75, 0.5)
    assert s._market_unit_market_map == {KS: "kospi", KQ: "kosdaq"}
    Seams(rows_for(F4, DAY), prev_day=DAY, kq_rows=rows_for(F2, DAY)).install(monkeypatch)
    await s._refresh_market_unit(as_of_date=NEXT, preview=True)
    assert (s._market_unit_snaps[DAY].m, s._market_unit_snaps_kq[DAY].m) == (0.75, 0.5), "오늘 칸 불변"
    assert (s._market_unit_snaps[NEXT].m, s._market_unit_snaps_kq[NEXT].m) == (0.0, 0.75)
    assert s._market_unit_view(KQ).m == 0.5 and s._market_unit_view(KS).m == 0.75


@freeze_time(_BOOT)
async def test_r2_empty_map_keeps_previous_map(monkeypatch):
    need_base()
    s = make("vcp_breakout", mode="shadow")
    s._market_unit_market_map = {KQ: "kosdaq"}
    Seams(rows_for(F2, HEAD), prev_day=HEAD, market_map={}).install(monkeypatch)
    await s._refresh_market_unit(as_of_date=DAY, preview=False)
    assert s._market_unit_market_map == {KQ: "kosdaq"}


@freeze_time(_BOOT)
async def test_r3_state_lines_carry_market_and_index_code(monkeypatch, caplog):
    need_base()
    open_info(caplog)
    s = make("kojiro", mode="shadow")
    Seams(rows_for(F2, HEAD), prev_day=HEAD, kq_rows=rows_for(F3, HEAD)).install(monkeypatch)
    await s._refresh_market_unit(as_of_date=DAY, preview=False)
    ls = lines(caplog, "[market_unit_state]")
    got = {field(ln, "market"): (field(ln, "source"), field(ln, "state")) for ln in ls}
    assert got == {"kospi": ("0001", "up_falling"), "kosdaq": ("1001", "down_rising")}
