"""cycle382 Red — 시장 유닛: 4전략 `prepare()` 갱신 · 미리보기 · 보존 규칙 · 일일 요약 · 모드 경로 (R41~R50).

명세 = `_workspace/red/cycle382_market_unit_spec.md` §3.3 · §4 · §7 · §8 · §11.2(refresh·라우트·자문)

계약 요약:
- 4전략 `prepare()` 가 `_resolve_prepare_as_of` 바로 뒤에서 `_refresh_market_unit(as_of_date=, preview=)` 를
  **정확히 1회** 부른다 — 유니버스 0 조기 return 보다 앞이다. 모드가 `off` 여도 계산한다
  (그래야 `enforce` PUT 이 재시작 없이 먹는다).
- 스냅샷은 전략 객체에 **거래일별로** 둔다. 미리보기는 다음 거래일 칸만 쓰고 오늘 칸을 건드리지 않는다.
  같은 날 ok 스냅샷을 실패가 덮지 않는다(`kept=1`). 오늘보다 과거 키는 지운다.
- `[market_unit_state]`(INFO, 조합당 1회) · `[market_unit_unavailable]`(WARNING) · `[market_unit_daily]`
  (INFO, 거래일마다 전략당 1줄 — 보통 그날 21:00 미리보기가 낸다).
- `market_unit_mode` 는 4전략 `DEFAULT_PARAMS` 기본 `shadow` · PUT 으로 `off|shadow|enforce` · `PARAM_RANGES`
  (AI 자동 적용 경로) 편입 0.

Red 유효성: leaf·헬퍼 부재 → `[Red]` 로 실패. R50 은 지금도 초록이다(화이트리스트 밖 키 — 회귀 가드).
"""
from __future__ import annotations

import copy
import logging
from contextlib import ExitStack
from datetime import date

import pytest
from freezegun import freeze_time

from tests.unit.engine._cycle382_support import (
    DAY, F2, F3, F4, HEAD, NEXT, T, TURTLE4, Seams, field, fnum, lines, make, mu, need_base,
    open_info, rows_for, seed,
)
from tests.unit.engine.strategies import _cycle364_harness as H

pytestmark = pytest.mark.unit

_BOOT = "2026-09-28T07:50:00+09:00"
_EVENING = "2026-09-28T21:05:00+09:00"


def _prev_day(d: date) -> date:
    """합성 달력 — 09-28 → 09-23(추석) · 09-29 → 09-28 · 09-30 → 09-29."""
    return {DAY: HEAD, NEXT: DAY, date(2026, 9, 30): NEXT}[d]


async def _prepare(s, *, as_of=None, seams: Seams, cands=None):
    def _extra(stack: ExitStack) -> None:
        for p in seams.patchers():
            stack.enter_context(p)

    kw = {} if as_of is None else {"as_of": as_of}
    await H.run_prepare(s, cands or {}, extra=_extra, **kw)


def _spy_refresh(monkeypatch, s) -> list[dict]:
    need_base()
    calls: list[dict] = []
    orig = s._refresh_market_unit

    async def _spy(*a, **k):
        calls.append(dict(k))
        return await orig(*a, **k)

    monkeypatch.setattr(s, "_refresh_market_unit", _spy)
    return calls


# ===========================================================================
# R41 — 4전략 prepare 가 1회 부른다 (유니버스 0 조기 return 에서도)
# ===========================================================================
@freeze_time(_BOOT)
@pytest.mark.parametrize("sid", TURTLE4)
async def test_r41_prepare_refreshes_once_even_when_universe_empty(monkeypatch, caplog, sid):
    open_info(caplog)
    s = make(sid, mode="shadow")
    calls = _spy_refresh(monkeypatch, s)
    seams = Seams(rows_for(F2, HEAD), prev_day=_prev_day)
    await _prepare(s, seams=seams)                                    # 유니버스 0 → 조기 return
    assert calls == [{"as_of_date": DAY, "preview": False}], calls
    snap = s._market_unit_snaps.get(DAY)
    assert snap is not None and snap.ok is True
    assert (snap.state, float(snap.m), snap.bar_date) == ("up_falling", 0.75, HEAD)
    state_lines = lines(caplog, "[market_unit_state]")
    assert len(state_lines) == 1 and field(state_lines[0], "strategy") == sid


@freeze_time(_BOOT)
async def test_r41_four_strategies_agree_on_state_from_one_seam():
    need_base()
    seams = Seams(rows_for(F3, HEAD), prev_day=_prev_day)
    got = {}
    for sid in TURTLE4:
        s = make(sid)
        await _prepare(s, seams=seams)
        snap = s._market_unit_snaps[DAY]
        got[sid] = (snap.state, float(snap.m))
    assert set(got.values()) == {("down_rising", 0.5)}, got
    assert all(c == ("069500", c[1]) and c[1] >= 80 for c in seams.daily_calls), seams.daily_calls


@freeze_time(_BOOT)
@pytest.mark.parametrize("sid", ("momentum", "volatility_breakout", "long_tail_volatility"))
async def test_r41_other_three_strategies_never_compute(monkeypatch, sid):
    """VB·LTV·momentum 은 속성만 물려받고 한 번도 부르지 않는다(명세 §3.2 · AST A04).

    ⚠️ `069500` 조회 여부로 재지 않는다 — VB 의 RS 관찰 훅이 같은 종목(KODEX200 벤치마크)을 읽는다.
    """
    need_base()
    s = make(sid)
    calls = _spy_refresh(monkeypatch, s)
    seams = Seams(rows_for(F3, HEAD), prev_day=_prev_day)
    if sid == "momentum":                                 # prepare = 빈 stub (하네스의 `_scan_universe` 패치 불가)
        seams.install(monkeypatch)
        await s.prepare()
    else:
        await _prepare(s, seams=seams)
    assert calls == []
    assert s._market_unit_snaps == {}
    assert "market_unit_mode" not in s.config.params


# ===========================================================================
# R42 — 모드 off 여도 계산 · enforce PUT 즉시 반영
# ===========================================================================
@freeze_time(_BOOT)
@pytest.mark.parametrize("sid", TURTLE4)
async def test_r42_off_still_computes_and_enforce_applies_without_reprepare(caplog, sid):
    open_info(caplog)
    s = make(sid, mode="off")
    need_base()
    await _prepare(s, seams=Seams(rows_for(F2, HEAD), prev_day=_prev_day))
    assert DAY in s._market_unit_snaps
    ln = lines(caplog, "[market_unit_state]")[0]
    assert field(ln, "mode") == "off"
    v = s._market_unit_view()
    assert (v.mode, float(v.m), v.reason) == ("off", 1.0, "off")
    s.config.params["market_unit_mode"] = "enforce"                  # PUT 과 같은 in-memory 덮기
    v = s._market_unit_view()
    assert (v.mode, float(v.m), v.state) == ("enforce", 0.75, "up_falling")
    s.config.params["market_unit_mode"] = "shadow"
    assert float(s._market_unit_view().m) == 0.75


@freeze_time(_BOOT)
@pytest.mark.parametrize("raw", ["on", 1, True, "enforced"])
def test_r42_invalid_mode_is_off_with_one_config_warning(caplog, raw):
    open_info(caplog)
    s = make("kojiro", mode="enforce")
    seed(s, 0.0)
    s.config.params["market_unit_mode"] = raw
    for _ in range(3):
        v = s._market_unit_view()
        assert (v.mode, float(v.m)) == ("off", 1.0)
    warns = lines(caplog, "[market_unit_config]", min_level=logging.WARNING)
    assert len(warns) == 1, warns
    assert field(warns[0], "strategy") == "kojiro"


@freeze_time(_BOOT)
def test_r42_missing_key_is_off_without_warning(caplog):
    open_info(caplog)
    s = make("donchian_swing")
    seed(s, 0.0)
    s.config.params.pop("market_unit_mode", None)
    v = s._market_unit_view()
    assert (v.mode, float(v.m)) == ("off", 1.0)
    assert lines(caplog, "[market_unit_config]", min_level=logging.WARNING) == []


# ===========================================================================
# R43 — 미리보기는 오늘을 안 바꾼다 · 다음 거래일 칸 · PV-1 입력 불변
# ===========================================================================
_PV1 = ("_candidates", "_entry_atr", "_position_setup", "_position_atr", "_breakout_high",
        "_held_stage3", "_stop_floor", "_position_sectors")


def _pv1(s) -> dict:
    out = {"positions": {t: (p.buy_price, p.quantity, p.high_since_buy) for t, p in s.state.positions.items()}}
    for name in _PV1:
        if hasattr(s, name):
            out[name] = copy.deepcopy(getattr(s, name))
    return out


@pytest.mark.parametrize("sid", TURTLE4)
async def test_r43_preview_writes_next_day_only(monkeypatch, sid):
    from src.engine.strategy_base import Position

    need_base()
    s = make(sid, mode="shadow")
    with freeze_time(_BOOT):
        await _prepare(s, seams=Seams(rows_for(F3, HEAD), prev_day=_prev_day))
    s.state.positions[T] = Position(ticker=T, buy_price=40_000, quantity=3, order_no="O",
                                     strategy_id=sid, buy_date=DAY, high_since_buy=41_000)
    s._candidates[T] = {"prev_close": 40_000, "atr": 900, "atr14": 900, "stage": 2}
    for name, val in (("_entry_atr", {T: 900.0}), ("_position_atr", {T: 900.0}),
                      ("_position_setup", {T: {"flag_low": 38_000, "base_low": 38_000, "atr14": 900}}),
                      ("_breakout_high", {T: 39_000})):
        if hasattr(s, name):
            getattr(s, name).update(val)
    today_snap = s._market_unit_snaps[DAY]
    before = _pv1(s)
    with freeze_time(_EVENING):
        Seams(rows_for(F4, DAY), prev_day=_prev_day).install(monkeypatch)
        await s._refresh_market_unit(as_of_date=NEXT, preview=True)
        assert s._market_unit_snaps[DAY] is today_snap, "미리보기가 오늘 스냅샷을 바꿨다"
        assert float(s._market_unit_view().m) == 0.5, "오늘 view 가 미리보기 값을 읽었다(M21)"
        nxt = s._market_unit_snaps[NEXT]
        assert (nxt.preview, nxt.ok, nxt.state, float(nxt.m)) == (True, True, "down_falling", 0.0)
        assert nxt.bar_date == DAY
    assert _pv1(s) == before, "미리보기 refresh 가 보유 청산 입력(PV-1)을 건드렸다"
    with freeze_time("2026-09-29T09:05:00+09:00"):
        v = s._market_unit_view()
        assert (v.state, float(v.m)) == ("down_falling", 0.0), "다음 날 view 가 미리보기 값을 쓰지 않는다"


@pytest.mark.parametrize("sid", TURTLE4)
async def test_r43_full_preview_prepare_also_keeps_today(monkeypatch, sid):
    need_base()
    s = make(sid, mode="shadow")
    with freeze_time(_BOOT):
        await _prepare(s, seams=Seams(rows_for(F3, HEAD), prev_day=_prev_day))
    today_snap = s._market_unit_snaps[DAY]
    calls = _spy_refresh(monkeypatch, s)
    with freeze_time(_EVENING):
        await _prepare(s, as_of=NEXT, seams=Seams(rows_for(F4, DAY), prev_day=_prev_day))
    assert calls == [{"as_of_date": NEXT, "preview": True}]
    assert s._market_unit_snaps[DAY] is today_snap
    assert set(s._market_unit_snaps) == {DAY, NEXT}


@pytest.mark.parametrize("sid", TURTLE4)
async def test_r43_past_keys_are_pruned(monkeypatch, sid):
    need_base()
    s = make(sid, mode="shadow")
    with freeze_time(_BOOT):
        await _prepare(s, seams=Seams(rows_for(F3, HEAD), prev_day=_prev_day))
    with freeze_time(_EVENING):
        await _prepare(s, as_of=NEXT, seams=Seams(rows_for(F4, DAY), prev_day=_prev_day))
    with freeze_time("2026-09-29T07:50:00+09:00"):
        await _prepare(s, seams=Seams(rows_for(F2, DAY), prev_day=_prev_day))
    assert set(s._market_unit_snaps) <= {NEXT, date(2026, 9, 30)}, "과거(09-28) 키가 남았다"
    assert DAY not in s._market_unit_snaps


# ===========================================================================
# R44 — 보존 규칙 (같은 날 ok 를 실패가 덮지 않는다)
# ===========================================================================
@freeze_time(_BOOT)
@pytest.mark.parametrize("sid", TURTLE4)
async def test_r44_failure_does_not_overwrite_ok_same_day(monkeypatch, caplog, sid):
    open_info(caplog)
    need_base()
    s = make(sid, mode="enforce")
    Seams(rows_for(F2, HEAD), prev_day=_prev_day).install(monkeypatch)
    await s._refresh_market_unit(as_of_date=DAY, preview=False)
    good = s._market_unit_snaps[DAY]
    Seams(rows_for(F2[:10], HEAD), prev_day=_prev_day).install(monkeypatch)        # rows_short
    await s._refresh_market_unit(as_of_date=DAY, preview=False)
    assert s._market_unit_snaps[DAY] is good, "실패가 같은 날 ok 스냅샷을 덮었다(M20)"
    assert float(s._market_unit_view().m) == 0.75
    warns = lines(caplog, "[market_unit_unavailable]", min_level=logging.WARNING)
    assert len(warns) == 1 and field(warns[0], "kept") == "1" and field(warns[0], "reason") == "rows_short"
    # 새 ok 는 항상 덮는다
    Seams(rows_for(F3, HEAD), prev_day=_prev_day).install(monkeypatch)
    await s._refresh_market_unit(as_of_date=DAY, preview=False)
    assert float(s._market_unit_snaps[DAY].m) == 0.5


@pytest.mark.parametrize("sid", TURTLE4)
async def test_r44_failure_on_other_day_is_recorded_as_m1(monkeypatch, caplog, sid):
    open_info(caplog)
    need_base()
    s = make(sid, mode="enforce")
    with freeze_time(_BOOT):
        Seams(rows_for(F2, HEAD), prev_day=_prev_day).install(monkeypatch)
        await s._refresh_market_unit(as_of_date=DAY, preview=False)
    with freeze_time(_EVENING):
        Seams([], prev_day=_prev_day).install(monkeypatch)
        await s._refresh_market_unit(as_of_date=NEXT, preview=True)
        nxt = s._market_unit_snaps[NEXT]
        assert (nxt.ok, float(nxt.m), nxt.reason) == (False, 1.0, "rows_short")
        warns = lines(caplog, "[market_unit_unavailable]", min_level=logging.WARNING)
        assert field(warns[-1], "kept") == "0" and field(warns[-1], "preview") in ("1", "True")
    with freeze_time("2026-09-29T09:05:00+09:00"):
        v = s._market_unit_view()
        assert (float(v.m), v.state) == (1.0, "unavailable"), "실패를 m=0 으로 닫았다(M07)"


# ===========================================================================
# §8 롤 규칙 — `_market_unit_tally_roll` 은 tally 날짜보다 **늦은** 날짜에서만 연다.
# ===========================================================================
@freeze_time(_BOOT)
async def test_tally_roll_earlier_or_same_date_does_not_reroll(monkeypatch, caplog):
    """미리보기(NEXT)가 tally 를 연 뒤, 같은 저녁 안에 더 이른 날짜(DAY) 또는 같은
    날짜(NEXT)로 refresh 가 다시 불려도 `[market_unit_daily]` 추가 줄이 나오지
    않고 NEXT 쪽에 쌓인 누적 카운트도 리셋되지 않는다(§8 — `tally.date < day` 일
    때만 연다. 돌연변이: `tally.date != day` 로 되돌리면 이 케이스가 잡는다).
    """
    open_info(caplog)
    need_base()
    s = make("donchian_swing", mode="enforce")
    Seams(rows_for(F2, HEAD), prev_day=_prev_day).install(monkeypatch)
    await s._refresh_market_unit(as_of_date=DAY, preview=False)          # tally 열림 @DAY
    assert s._market_unit_tally["date"] == DAY
    assert lines(caplog, "[market_unit_daily]") == []

    with freeze_time(_EVENING):
        Seams(rows_for(F4, DAY), prev_day=_prev_day).install(monkeypatch)
        await s._refresh_market_unit(as_of_date=NEXT, preview=True)      # 늦은 날짜 → 롤 1회(DAY 줄)
        daily = lines(caplog, "[market_unit_daily]")
        assert len(daily) == 1 and field(daily[0], "date") == "2026-09-28"
        assert s._market_unit_tally["date"] == NEXT

        s._market_unit_tally["calc_attempts"] = 7                        # NEXT tally 인위 누적

        # 같은 저녁 안에 더 이른 날짜(DAY)로 다시 refresh — 롤되면 안 된다.
        Seams(rows_for(F2, HEAD), prev_day=_prev_day).install(monkeypatch)
        await s._refresh_market_unit(as_of_date=DAY, preview=False)
        assert lines(caplog, "[market_unit_daily]") == daily, "이른 날짜 refresh 가 추가 줄을 냈다"
        assert s._market_unit_tally["date"] == NEXT, "이른 날짜 refresh 가 tally 를 되돌렸다"
        assert s._market_unit_tally["calc_attempts"] == 7, "이른 날짜 refresh 가 누적 카운트를 리셋했다"

        # 같은 날짜(NEXT)로 다시 refresh — 여전히 롤 없음.
        Seams(rows_for(F4, DAY), prev_day=_prev_day).install(monkeypatch)
        await s._refresh_market_unit(as_of_date=NEXT, preview=True)
        assert lines(caplog, "[market_unit_daily]") == daily
        assert s._market_unit_tally["date"] == NEXT
        assert s._market_unit_tally["calc_attempts"] == 7


# ===========================================================================
# R45 — never-raise (compute_snapshot 자체가 던져도)
# ===========================================================================
@freeze_time(_BOOT)
async def test_r45_compute_snapshot_raising_never_breaks_prepare(monkeypatch, caplog):
    open_info(caplog)
    need_base()
    lf = mu()
    hits: list = []

    async def _boom(*a, **k):
        hits.append((a, k))
        raise RuntimeError("leaf exploded")

    monkeypatch.setattr(lf, "compute_snapshot", _boom)
    s = H.make_strategy("donchian_swing")
    s.config.params["market_unit_mode"] = "enforce"
    s.state.total_investment = 1_000_000
    await _prepare(s, seams=Seams(rows_for(F4, HEAD), prev_day=_prev_day),
                   cands=H.universe(HEAD))
    assert hits, "prepare 가 `market_unit.compute_snapshot`(모듈 속성)을 부르지 않았다"
    assert H.T_UP in s._candidates, "시장 유닛 실패가 후보 준비를 끊었다"
    v = s._market_unit_view()
    assert float(v.m) == 1.0 and v.state == "unavailable"
    warns = lines(caplog, "[market_unit_unavailable]", min_level=logging.WARNING)
    assert warns and field(warns[0], "reason") == "exception"


# ===========================================================================
# R46 — 일일 요약 1줄 (다음 날 미리보기가 낸다)
# ===========================================================================
async def test_r46_daily_summary_once_per_trading_day(monkeypatch, caplog):
    open_info(caplog)
    need_base()
    s = make("donchian_swing", mode="enforce", sizing_mode="turtle", risk_pct=0.01,
             position_ratio=0.2, max_positions=5)
    with freeze_time(_BOOT):
        await _prepare(s, seams=Seams(rows_for(F3, HEAD), prev_day=_prev_day))      # m=0.5
    with freeze_time("2026-09-28T09:15:00+09:00"):
        for t, atr in (("990001", 500), ("990002", 500), ("990003", None)):
            s._candidates[t] = {"prev_close": 10_000, "atr": atr, "ema60": 9_000, "donchian_high": 10_000}
        # cycle405 — donchian 깡토식 설계 랏: floor(1M×m×0.01 / 800) = 12 → 6
        assert s.calc_buy_quantity(10_000, "990001") == 6                             # 12 → 6
        assert s.calc_buy_quantity(10_000, "990002") == 6                             # 12 → 6
        assert s.calc_buy_quantity(10_000, "990003") == 0                             # no_fallback
        for t in ("990004", "990005"):
            s._candidates[t] = {"prev_close": 10_000, "atr": 0, "ema60": 9_000, "donchian_high": 10_000}
            assert s._market_unit_blocks_entry(t, 10_000) is True
        assert s._market_unit_blocks_entry("990004", 10_000) is True                  # 같은 종목 재평가
    assert lines(caplog, "[market_unit_daily]") == [], "요약이 그날이 끝나기 전에 나왔다"
    with freeze_time(_EVENING):
        await _prepare(s, as_of=NEXT, seams=Seams(rows_for(F4, DAY), prev_day=_prev_day))
        await _prepare(s, as_of=NEXT, seams=Seams(rows_for(F4, DAY), prev_day=_prev_day))
    daily = lines(caplog, "[market_unit_daily]")
    assert len(daily) == 1, daily
    ln = daily[0]
    assert field(ln, "strategy") == "donchian_swing" and field(ln, "date") == "2026-09-28"
    assert (field(ln, "state"), fnum(ln, "m")) == ("down_rising", 0.5)
    assert (field(ln, "calc_attempts"), field(ln, "would_skip"), field(ln, "reduced"),
            field(ln, "signal_skips")) == ("3", "1", "2", "2")
    assert (field(ln, "lot_before_sum"), field(ln, "lot_after_sum")) == ("24", "12")


async def test_r46_without_evening_preview_next_boot_emits_the_line(caplog):
    """미리보기가 없던 날 — 다음 날 07:50 부팅(라이브 as_of)이 전날 줄을 낸다(명세 §8)."""
    open_info(caplog)
    need_base()
    s = make("kojiro", mode="shadow", sizing_mode="turtle", risk_pct=0.005, position_ratio=0.166,
             max_positions=6, budget=2_000_000)
    with freeze_time(_BOOT):
        await _prepare(s, seams=Seams(rows_for(F2, HEAD), prev_day=_prev_day))      # m=0.75
    with freeze_time("2026-09-28T09:10:00+09:00"):
        s._candidates[T] = {"stage": 1, "prev_close": 50_000, "atr": 1_000.0}
        assert s.calc_buy_quantity(50_000, T) == 6                                    # shadow: 6 (설계 4)
    with freeze_time("2026-09-29T07:50:00+09:00"):
        await _prepare(s, seams=Seams(rows_for(F2, DAY), prev_day=_prev_day))
    daily = lines(caplog, "[market_unit_daily]")
    assert len(daily) == 1, daily
    ln = daily[0]
    assert field(ln, "date") == "2026-09-28" and field(ln, "state") == "up_falling"
    assert (field(ln, "calc_attempts"), field(ln, "reduced"), field(ln, "would_skip")) == ("1", "1", "0")
    assert (field(ln, "lot_before_sum"), field(ln, "lot_after_sum")) == ("6", "4")


# ===========================================================================
# R47 — `[market_unit_state]` 손계산 일치 · 조합당 1줄
# ===========================================================================
@freeze_time(_BOOT)
async def test_r47_state_line_matches_hand_calculation(monkeypatch, caplog):
    """F2: close 12,500 · sum60 691,590(SMA60 11,526.50) · sum60_prev 702,300(11,705.00) → 위·하락 ¾."""
    open_info(caplog)
    need_base()
    s = make("kojiro", mode="shadow")
    Seams(rows_for(F2, HEAD), prev_day=_prev_day).install(monkeypatch)
    for _ in range(3):
        await s._refresh_market_unit(as_of_date=DAY, preview=False)
    ls = lines(caplog, "[market_unit_state]")
    assert len(ls) == 1, ls
    ln = ls[0]
    assert field(ln, "strategy") == "kojiro" and field(ln, "as_of") == "2026-09-28"
    assert field(ln, "preview") == "0" and field(ln, "source") == "069500"
    assert field(ln, "bar") == "2026-09-23" and field(ln, "expected_head") == "2026-09-23"
    assert fnum(ln, "close") == 12_500
    assert abs(fnum(ln, "sma60") - 11_526.50) < 0.006
    assert abs(fnum(ln, "sma60_prev") - 11_705.00) < 0.006
    assert (field(ln, "above"), field(ln, "rising")) == ("1", "0")
    assert (field(ln, "state"), fnum(ln, "m"), field(ln, "mode")) == ("up_falling", 0.75, "shadow")
    assert int(field(ln, "rows")) >= 80
    assert sum(F2[20:80]) == 691_590 and sum(F2[0:60]) == 702_300        # 손계산 자기검산


# ===========================================================================
# R48 — DB 덮기 (`_load_strategy_config`)
# ===========================================================================
@pytest.mark.parametrize("sid", TURTLE4)
async def test_r48_db_without_key_keeps_code_default_shadow(sid):
    from unittest.mock import AsyncMock, patch

    from src.engine.scheduler import TradingScheduler

    sched = TradingScheduler()
    strategy = sched.registry.get(sid)
    with patch("src.db.strategy_config.load_all",
               AsyncMock(return_value={sid: {"enabled": True, "weight": 0.1, "params": {}}})):
        await sched._load_strategy_config()
    assert strategy.config.params.get("market_unit_mode") == "shadow"


async def test_r48_db_value_wins_when_present():
    from unittest.mock import AsyncMock, patch

    from src.engine.scheduler import TradingScheduler

    sched = TradingScheduler()
    db = {"kojiro": {"enabled": True, "weight": 0.4, "params": {"market_unit_mode": "enforce"}}}
    with patch("src.db.strategy_config.load_all", AsyncMock(return_value=db)):
        await sched._load_strategy_config()
    assert sched.registry.get("kojiro").config.params["market_unit_mode"] == "enforce"


# ===========================================================================
# R49 — 파라미터 검증 (PUT 의 관문 = `validate_params`, 순수 함수)
# ===========================================================================
@pytest.mark.parametrize("sid", TURTLE4)
@pytest.mark.parametrize("value", ["off", "shadow", "enforce"])
def test_r49_turtle_put_accepts_three_modes(sid, value):
    from src.engine.param_validation import validate_params
    from tests.unit.engine._cycle382_support import strategy_class

    current = dict(strategy_class(sid).DEFAULT_PARAMS)
    res = validate_params(sid, current, {"market_unit_mode": value})
    assert [e.code for e in res.errors] == [], res.errors
    assert res.accepted == {"market_unit_mode": value}


def test_r49_invalid_choice_is_rejected_not_saved():
    from src.engine.param_validation import validate_params
    from tests.unit.engine._cycle382_support import strategy_class

    current = dict(strategy_class("kojiro").DEFAULT_PARAMS)
    res = validate_params("kojiro", current, {"market_unit_mode": "on"})
    assert [e.code for e in res.errors] == ["not_in_choices"]
    assert res.accepted == {}


def test_r49_other_strategies_reject_the_key_as_unknown():
    from src.engine.param_validation import validate_params
    from tests.unit.engine._cycle382_support import strategy_class

    current = dict(strategy_class("volatility_breakout").DEFAULT_PARAMS)
    res = validate_params("volatility_breakout", current, {"market_unit_mode": "enforce"})
    assert [e.code for e in res.errors] == ["unknown_key"]


# ===========================================================================
# R50 — AI 자문 적용 경로 편입 0
# ===========================================================================
def test_r50_recommendation_validator_drops_market_unit_mode():
    from src.engine import recommendation_engine as rec

    current = {"market_unit_mode": "shadow", "stop_loss_rate": -7.0}
    params, *_ = rec._validate_recommendations(
        {"recommended_params": {"market_unit_mode": "enforce", "stop_loss_rate": -6.0},
         "reasoning": "r"},
        current,
    )
    assert "market_unit_mode" not in params
    assert params.get("stop_loss_rate") == -6.0, "탐지기 자기시험 — 허용 키는 통과해야 한다"
