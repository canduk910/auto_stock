"""cycle364 S1 Red — PV-1(🔴 크리티컬 가드 1) · P3: 저녁 미리보기는 보유 종목의 청산 입력을 바꾸지 않는다.

설계 정본 = `_workspace/domain_consult/cycle364_a1_as_of_design.md` §0-2 · §1.2 · §2.1 PV-1/P3 ·
§6.2 PV-1a/PV-1b/P3 · 돌연변이 M1/M2. 사용자 결정 카드1 (가).

왜 🔴 인가 (§0-2): 지금 코드에 `as_of` 만 넣으면 kojiro 가 보유 종목에
`_held_stage3 = (오늘, 내일 판정)` 을 찍는다. `check_exit_signal` §3 은 `_judged_on == 오늘`
이면 **가격을 보지 않고** `TRAILING_STOP` 이다. 20:00 뒤에도 stale watcher 가 보유를 HIGH 로
재구독하므로 틱 하나면 야간 청산 주문이 나간다. donchian 은 보유 ATR 엔트리가 지워져
21:30 포트폴리오 리스크 손절선이 매수시점 ATR 로 떨어진다.

────────────────────────────────────────────────────────────────────────────
Green 이 맞춰야 하는 계약 (donchian·kojiro, `as_of > 오늘` = 미리보기일 때만)
────────────────────────────────────────────────────────────────────────────
- 🔁 round 2(R1) — 두 집합을 나눈다(정본 = `test_cycle364_preview_keep_own_skip_all.py` 머리말):
  **보존** = 자기 `state.positions` ∪ 자기 익일청산대기 / **건너뜀** = 자기 `state.positions` ∪
  `scanner._collect_protected_tickers_for_scanner()`(전 전략 보유 ∪ 익일청산). 이 파일의 시나리오는
  보유가 자기 것이라 두 집합이 같다(헬퍼가 그 보유를 돌려주도록 패치한다). BFB·VCP 도 같은 규칙.
- 시작부 `self._candidates = {}` → 미리보기에서는 보존 엔트리만 **같은 객체로** 남긴다.
  재시도 경로(유니버스 0 → 30초 재시도)의 와이프도 같다.
- 종목 루프에서 건너뜀 종목은 fetch 결과를 버리고 `continue` — `_candidates`·`_held_stage3`·
  `ticker_prev_close`·관측 원자료·거래일 캐시(`_trading_days`) 어느 것도 쓰지 않는다.
- donchian `_scanned_tickers` 는 이번 실행이 만든 후보만(보존 보유 제외). kojiro `held_only`
  에는 보존 엔트리가 그대로 들어간다(step 99 계약).
- 🔴 금기: 미리보기에서 `_held_stage3` 를 as_of 날짜로 찍는 절충도 쓰지 않는다.
- P3: 미리보기에서 kojiro `observe_band`·`observe_macd`·`observe_macd_stage6` 호출 0,
  VCP `_observe_breakout_distance` 호출 0(`_breakout_watch` 동일성 유지 — 휴장일 낮 비상 대비).
  funnel 단계 기록과 VB 퀀트·RS/RSI(7~9단계)는 **생략하지 않는다**(미리보기의 산출물).
- 비미리보기(인자 없음·`as_of=오늘`)는 현행 그대로 재표시·와이프한다(대조군).

Red 유효성: 현행 prepare 는 `as_of` 를 받지 않는다 → TypeError. 대조군 중 인자 없는 호출은
지금 **초록**(현행 위험 행위를 문서화)이다.
"""

from __future__ import annotations

from contextlib import ExitStack
from datetime import date, datetime
from unittest.mock import MagicMock, patch

import pytest
from freezegun import freeze_time

from src.engine.strategy_base import Signal
from tests.unit.engine.strategies import _cycle364_harness as H

pytestmark = pytest.mark.unit

_D = date(2026, 9, 22)
_D_NEXT = date(2026, 9, 23)
_EVENING = "2026-09-22T21:00:00+09:00"
_HOLIDAYS = {date(2026, 9, 24), date(2026, 9, 25)}


def _fake_calendar(monkeypatch):
    async def _cal(d):
        return d.weekday() < 5 and d not in _HOLIDAYS

    monkeypatch.setattr("src.engine.trading_calendar._lookup_open", _cal)


def _kojiro_enrich_override(stack: ExitStack, cands: dict, spies: dict):
    """실 enrich 위에 마지막 봉만 덮는다 — 보유(HELD)=스테이지 2→3(D 종가에 스테이지3 진입),
    T_UP=6→1 신선 + 3선 우상향 + 종가>EMA5 + ATR 2%(미리보기가 만드는 새 후보). 나머지는 실값."""
    import src.engine.strategies.kojiro as kmod

    real = kmod.enrich
    held_closes = set(H.close_to_date(cands[H.HELD]))
    up_closes = set(H.close_to_date(cands[H.T_UP]))

    def _enrich(df, cfg):
        out = real(df, cfg).copy()
        last_close = int(out["close"].iloc[-1])
        idx = out.index
        out["stage"] = out["stage"].astype(object)
        if last_close in held_closes:
            out.loc[idx[-2], "stage"] = 2
            out.loc[idx[-1], "stage"] = 3
        elif last_close in up_closes:
            out.loc[idx[-1], "atr"] = last_close * 0.02   # ATR 밴드(1~6%) 안으로
            out.loc[idx[-2], "stage"] = 6
            out.loc[idx[-1], "stage"] = 1
            for col in ("ema_s_up", "ema_m_up", "ema_l_up"):
                out.loc[idx[-1], col] = True
            out.loc[idx[-1], "ema_s"] = float(last_close) - 1.0
        return out

    stack.enter_context(patch.object(kmod, "enrich", _enrich))
    for name in ("observe_band", "observe_macd", "observe_macd_stage6"):
        spies[name] = stack.enter_context(patch.object(kmod, name, MagicMock(return_value=None)))


async def _kojiro_run(monkeypatch, *, as_of):
    _fake_calendar(monkeypatch)
    k = H.make_strategy("kojiro")
    seeded = H.seed_held(k, as_of_day=_D)
    cands = H.universe(_D)
    spies: dict = {}
    with freeze_time(_EVENING):
        _, prev_close = await H.run_prepare(
            k, cands, as_of=as_of, protected=(H.HELD,),
            extra=lambda st: _kojiro_enrich_override(st, cands, spies),
        )
    return k, seeded, prev_close, spies


# ══════════════════════════════════════════════════════════════════════
# PV-1a — kojiro: 미리보기가 stage3 청산 트리거를 만들지 않는다 (M1)
# ══════════════════════════════════════════════════════════════════════
async def test_pv1a_kojiro_preview_when_held_hits_stage3_at_d_close_then_flag_and_entry_untouched(monkeypatch):
    k, seeded, prev_close, spies = await _kojiro_run(monkeypatch, as_of=_D_NEXT)

    assert k._held_stage3.get(H.HELD) is seeded["stage3"], (
        f"미리보기가 보유 stage3 플래그를 다시 찍었다: {k._held_stage3.get(H.HELD)!r} — "
        "(오늘, 내일 판정) 스탬프는 21:00~21:30 틱 하나로 가격 무관 야간 청산이 된다 (M1)"
    )
    assert k._candidates.get(H.HELD) is seeded["candidate"], (
        "미리보기가 보유 `_candidates` 엔트리를 교체했다 — 청산 ATR 소스가 바뀐다 (PV-1)"
    )
    assert H.HELD not in prev_close, "미리보기가 보유 종목 `ticker_prev_close` 를 썼다"
    for name in ("observe_band", "observe_macd"):
        for call in spies[name].call_args_list:
            raw = call.args[0] if call.args else {}
            assert H.HELD not in (raw or {}), f"보유 종목 관측 원자료가 {name} 로 나갔다 (PV-1)"


async def test_pv1a_kojiro_preview_when_tick_arrives_after_then_no_night_exit(monkeypatch):
    """§6.2 PV-1a 결정 단언 — 미리보기 직후 보유 틱 → `check_exit_signal` = NONE (야간 청산 0)."""
    k, _, _, _ = await _kojiro_run(monkeypatch, as_of=_D_NEXT)
    with freeze_time("2026-09-22T21:05:00+09:00"):
        sig = k.check_exit_signal(H.HELD, 54_000, 54_000)
    assert sig == Signal.NONE, (
        f"미리보기 직후 보유 틱이 {sig} — 장외 계산이 가격 무관 청산을 만들었다 (🔴 크리티컬 가드 1, M1)"
    )


async def test_pv1a_kojiro_preview_when_run_then_held_kept_in_step99_and_new_candidate_listed(monkeypatch):
    k, _, prev_close, _ = await _kojiro_run(monkeypatch, as_of=_D_NEXT)
    scanned = k.get_scanned_tickers()
    assert H.HELD in scanned, "kojiro 미리보기 held_only 에는 보존 엔트리가 그대로 들어간다(step 99 계약)"
    assert H.T_UP in scanned, f"미리보기가 다음 거래일 후보(T_UP)를 만들지 못했다: {scanned}"
    assert k._candidates[H.T_UP]["prev_close"] == int(H.universe(_D)[H.T_UP][0]["stck_clpr"]), (
        "미리보기 후보의 전일 종가는 D 종가여야 한다 (오늘 봉 포함)"
    )
    assert prev_close.get(H.T_UP) == k._candidates[H.T_UP]["prev_close"]


@pytest.mark.parametrize("as_of", [H._NO_ARG, _D], ids=["no_arg", "as_of_today"])
async def test_pv1a_control_non_preview_when_held_hits_stage3_then_restamped_and_exit_fires(monkeypatch, as_of):
    """대조군 — 비미리보기는 현행대로 (오늘, True) 재표시 → 가격 무관 TRAILING_STOP.
    이 테스트가 초록이라는 것이 PV-1a 가 무엇을 막는지의 증거다."""
    k, seeded, _, _ = await _kojiro_run(monkeypatch, as_of=as_of)
    assert k._held_stage3.get(H.HELD) == (_D, True), k._held_stage3.get(H.HELD)
    with freeze_time("2026-09-22T21:05:00+09:00"):
        assert k.check_exit_signal(H.HELD, 54_000, 54_000) == Signal.TRAILING_STOP


# ══════════════════════════════════════════════════════════════════════
# PV-1b — donchian: 미리보기가 보유 ATR 엔트리를 지우지도 덮지도 않는다 (M2)
# ══════════════════════════════════════════════════════════════════════
def _donchian_cands() -> dict:
    """보유(HELD)도 내일 후보 자격을 충족하도록 T_UP 과 같은 모양(단, 종가 대역·길이 다름).

    130봉 — 다른 종목(110봉)보다 20영업일 더 오래된 날짜를 가진다(거래일 캐시 오염 탐지용).
    """
    cands = H.universe(_D)
    cands[H.HELD] = H.trend_series(_D, 130, base=60_001, step=50, hi=30, lo=60)
    return cands


async def _donchian_run(monkeypatch, *, as_of, cands=None):
    _fake_calendar(monkeypatch)
    d = H.make_strategy("donchian_swing")
    seeded = H.seed_held(d, as_of_day=_D)
    cands = cands if cands is not None else _donchian_cands()
    with freeze_time(_EVENING):
        stop_before = d.get_effective_stop_price(H.HELD)
        _, prev_close = await H.run_prepare(d, cands, as_of=as_of, protected=(H.HELD,))
        stop_after = d.get_effective_stop_price(H.HELD)
    return d, seeded, prev_close, cands, stop_before, stop_after


async def test_pv1b_donchian_preview_when_held_qualifies_tomorrow_then_entry_and_stop_line_unchanged(monkeypatch):
    d, seeded, prev_close, cands, stop_before, stop_after = await _donchian_run(monkeypatch, as_of=_D_NEXT)
    assert d._candidates.get(H.HELD) is seeded["candidate"], (
        "미리보기가 보유 ATR 엔트리(아침 recompute 의 「오늘 ATR」)를 지우거나 덮었다 (M2)"
    )
    assert stop_after == stop_before, (
        f"미리보기 전후 실효 손절선이 {stop_before} → {stop_after} — 21:30 portfolio_risk 가 "
        "매수시점 ATR 로 떨어진다 (M2)"
    )
    assert H.HELD not in prev_close, "미리보기가 보유 종목 ticker_prev_close 를 D 종가로 덮었다"
    assert H.HELD not in d.get_scanned_tickers(), (
        "donchian 미리보기 `_scanned_tickers` 는 이번 실행이 만든 후보만 — 보존한 보유 엔트리 제외"
    )


async def test_pv1b_donchian_preview_when_run_then_trading_day_cache_ignores_held_candles(monkeypatch):
    d, _, _, cands, _, _ = await _donchian_run(monkeypatch, as_of=_D_NEXT)
    others = {
        datetime.strptime(c["stck_bsop_date"], "%Y%m%d").date()
        for t, rows in cands.items() if t != H.HELD and rows for c in rows
    }
    held_only = {
        datetime.strptime(c["stck_bsop_date"], "%Y%m%d").date() for c in cands[H.HELD]
    } - others
    assert held_only, "시나리오 전제: 보유 봉에만 있는 날짜가 있어야 한다"
    leaked = held_only & set(d._trading_days)
    assert not leaked, f"미리보기가 보유 종목 봉으로 거래일 캐시를 채웠다: {sorted(leaked)[:3]}…"


async def test_pv1b_donchian_preview_when_run_then_new_candidates_listed_from_d_bar(monkeypatch):
    d, _, prev_close, cands, _, _ = await _donchian_run(monkeypatch, as_of=_D_NEXT)
    scanned = d.get_scanned_tickers()
    assert H.T_UP in scanned, f"미리보기가 다음 거래일 후보를 만들지 못했다: {scanned}"
    assert d._candidates[H.T_UP]["prev_close"] == int(cands[H.T_UP][0]["stck_clpr"]), (
        "미리보기 후보의 전일 종가 = D 종가"
    )


@pytest.mark.parametrize("as_of", [H._NO_ARG, _D], ids=["no_arg", "as_of_today"])
async def test_pv1b_control_non_preview_when_held_qualifies_then_entry_replaced(monkeypatch, as_of):
    """대조군 — 비미리보기는 현행대로 `_candidates = {}` 후 재구성(보유 엔트리 교체)."""
    d, seeded, _, _, stop_before, stop_after = await _donchian_run(monkeypatch, as_of=as_of)
    assert d._candidates.get(H.HELD) is not seeded["candidate"]
    assert stop_after != stop_before


# ══════════════════════════════════════════════════════════════════════
# PV-1 — 유니버스 0 재시도 경로도 보유 엔트리를 지우지 않는다
# ══════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("sid", ["donchian_swing", "kojiro"])
async def test_pv1_retry_preview_when_universe_empty_then_held_entries_survive_retry_wipes(monkeypatch, sid):
    """21:00 에 stock_master 가 0건이면 30초×3 재시도 경로가 `_candidates = {}` 를 다시 한다 —
    미리보기에서는 그 와이프도 보유 엔트리를 남겨야 한다."""
    _fake_calendar(monkeypatch)
    s = H.make_strategy(sid)
    seeded = H.seed_held(s, as_of_day=_D)
    with freeze_time(_EVENING):
        await H.run_prepare(s, {}, as_of=_D_NEXT, protected=(H.HELD,))
    assert s._candidates.get(H.HELD) is seeded["candidate"], f"{sid}: 재시도 와이프가 보유 엔트리를 지웠다"
    if sid == "kojiro":
        assert s._held_stage3.get(H.HELD) is seeded["stage3"]


# ══════════════════════════════════════════════════════════════════════
# P3 — 미리보기는 관측 전용 부수 로그를 남기지 않는다 (funnel 은 남긴다)
# ══════════════════════════════════════════════════════════════════════
async def test_p3_kojiro_preview_when_run_then_no_observe_calls(monkeypatch):
    _, _, _, spies = await _kojiro_run(monkeypatch, as_of=_D_NEXT)
    counts = {n: m.call_count for n, m in spies.items()}
    assert counts == {"observe_band": 0, "observe_macd": 0, "observe_macd_stage6": 0}, (
        f"미리보기가 kojiro 관측 로그를 남겼다 {counts} — `bar` 는 「D-1 완성봉」 계약이고 "
        "하루 cap 을 소비해 D 표본을 오염시킨다 (P3)"
    )


async def test_p3_kojiro_control_non_preview_when_run_then_observers_called(monkeypatch):
    _, _, _, spies = await _kojiro_run(monkeypatch, as_of=H._NO_ARG)
    assert all(m.call_count >= 1 for m in spies.values()), {n: m.call_count for n, m in spies.items()}


def _vcp_setup(monkeypatch):
    _fake_calendar(monkeypatch)
    v = H.make_strategy("vcp_breakout")
    sentinel = {"date": date(2026, 9, 23), "run_at": "09:31:00", "tickers": {"990199": {"max": 1}}}
    v._breakout_watch = sentinel
    return v, sentinel


async def test_p3_vcp_preview_on_holiday_daytime_when_run_then_breakout_watch_identity_kept(monkeypatch):
    """휴장일 낮(09-25 추석) 미리보기(as_of=09-28) — D1 가드(`now > entry_end`)가 못 막는 창."""
    v, sentinel = _vcp_setup(monkeypatch)
    box: dict = {}

    def _extra(stack):
        box["obs"] = stack.enter_context(patch.object(
            v, "_observe_breakout_distance", wraps=v._observe_breakout_distance,
        ))

    with freeze_time("2026-09-25T10:00:00+09:00"):
        await H.run_prepare(v, H.universe(date(2026, 9, 23)), as_of=date(2026, 9, 28), extra=_extra)
    assert box["obs"].call_count == 0, "미리보기가 VCP 돌파 거리 관측을 불렀다 (P3)"
    assert v._breakout_watch is sentinel, "미리보기가 그날 돌파 관측(watch)을 교체했다 (P3)"


async def test_p3_vcp_control_non_preview_when_run_then_watch_replaced(monkeypatch):
    v, sentinel = _vcp_setup(monkeypatch)
    with freeze_time("2026-09-25T10:00:00+09:00"):
        await H.run_prepare(v, H.universe(date(2026, 9, 23)))
    assert v._breakout_watch is not sentinel


@pytest.mark.parametrize("sid", H.SIDS)
async def test_p3_preview_when_run_then_funnel_stage_structure_same_as_non_preview(monkeypatch, sid):
    """funnel 단계 기록은 미리보기의 산출물 — 생략하면 저녁 캡처가 빈 행을 쓴다.
    VB 퀀트·RS/RSI(7~9단계) 포함 같은 단계 집합이어야 하고 1단계는 비어 있지 않다."""
    _fake_calendar(monkeypatch)
    a = H.make_strategy(sid)
    b = H.make_strategy(sid)
    with freeze_time(_EVENING):
        await H.run_prepare(a, H.universe(_D))
        await H.run_prepare(b, H.universe(_D), as_of=_D_NEXT)
    steps_a = sorted(s["step_no"] for s in a._funnel_steps)
    steps_b = sorted(s["step_no"] for s in b._funnel_steps)
    assert steps_b == steps_a, f"{sid}: 미리보기 funnel 단계 {steps_b} ≠ 비미리보기 {steps_a}"
    first = min(b._funnel_steps, key=lambda s: s["step_no"])
    assert first["survived_count"] > 0 or sid in ("volatility_breakout", "long_tail_volatility"), (
        f"{sid}: 미리보기 1단계가 비었다"
    )
    if sid == "volatility_breakout":
        by = {s["step_no"]: s for s in b._funnel_steps}
        for n in (7, 8, 9):
            assert by[n]["survived_count"] > 0, f"VB 미리보기 {n}단계(퀀트·RS/RSI 관찰)가 비었다 (P3 생략 금지)"
