"""cycle364 S1 round 2 Red — R1: PV-1 을 BFB·VCP 로 넓히고 「자기 것만 보존 · 보호 종목 전부 건너뜀」.

설계 정본 = `_workspace/domain_consult/cycle364_a1_as_of_design.md` §2.1 PV-1 (round-1 적대 검토
trading-safety medium · time-and-data low 반영 — 메인 세션 결정 R1, 사용자 승인 D3 범위).

왜 BFB·VCP 도인가: 설계 §1.2 는 「BFB 청산은 `_candidates` 를 읽지 않는다」고 적었지만 틀렸다.
두 전략의 `_effective_setup` 은 **live `_candidates[t]` 를 우선**하고 stamp(`_position_setup`)
에서는 구조 키(BFB `flag_low`·`flag_high`·`pole_high`·`pole_start` / VCP `base_low`)만 덮는다.
그래서 21:00 미리보기가 `_candidates = {}` 를 하면 보유 종목의 `atr14`(샹들리에·BFB 래치)와
VCP `ema50` 이 stamp 값이나 D 종가 재계산 값으로 바뀐다 — 21:30 `portfolio_risk`·잔고 화면
손절선이 움직이고, 21:00~21:30 틱 하나면 미리보기 상태로 청산이 발사된다(round-1 재현:
VCP 10,300 틱 NONE → TRAILING_STOP, 실효 손절선 9,600 → 10,400).

────────────────────────────────────────────────────────────────────────────
Green 이 맞춰야 하는 계약 (donchian · kojiro · BFB · VCP, `as_of > 오늘` = 미리보기일 때만)
────────────────────────────────────────────────────────────────────────────
- **보존 집합(keep)** = 자기 `state.positions` ∪ **자기** 익일청산대기 — 익일청산대기는
  `src.engine.scheduler.trading_scheduler._pending_next_day_clear` 의 `(ticker, strategy_id)`
  중 `strategy_id == self.strategy_id` 인 것. 시작부 와이프(재시도 경로 포함)는 keep 엔트리만
  **같은 객체로** 남긴다. 다른 전략의 보유·익일청산 종목 엔트리는 남기지 않는다 — kojiro
  `held_only`(step 99)·donchian `get_targets_status` 가 남의 보유로 오염된다(round-1 low).
- **건너뜀 집합(skip)** = 보호 종목 전부 = 자기 `state.positions` ∪
  `scanner._collect_protected_tickers_for_scanner()`(전 전략 보유 ∪ 익일청산). 종목 루프에서
  fetch 결과를 버리고 `continue` — `_candidates`·`ticker_prev_close`·`_held_stage3`·관측 원자료
  어느 것도 쓰지 않는다. 🔴 자기 보유는 헬퍼가 ∅ 를 돌려줘도(조회 실패는 헬퍼가 조용히 삼킨다)
  건너뛴다 = **합집합**이다(round-1 tester 생존 돌연변이 Y2).
- BFB·VCP 미리보기 `_scanned_tickers` 는 이번 실행이 만든 후보만 — 보존한 보유 엔트리는 뺀다
  (donchian §2.1 규약과 같다. 평시 부팅 준비는 보유 복구 전이라 보유가 목록에 들지 않는다 —
  보존 엔트리를 넣으면 21:00 의 D+1 step 99 행이 「내일 후보가 아닌 보유」를 후보로 적는다).
  🔶 이 한 줄은 설계 문서가 BFB·VCP 에 대해 명시하지 않아 tdd-engineer 가 donchian 규약을
  따라 고정했다.
- 비미리보기(`as_of=오늘`)는 현행 그대로 와이프·재구성한다(대조군 — 이 대조군이 초록이라는
  것이 PV-1 이 무엇을 막는지의 증거다).

시나리오(「052710 형」 = BFB `position_ratio` 보유, `_entry_atr` 스탬프 없음 → −5% 경로 +
live ATR 샹들리에): 매수 10,000 · 고점 11,000 · 아침 live 후보 atr14=700(VCP ema50=9,000) ·
stamp atr14=300(VCP ema50=9,500). 미리보기 전 실효 손절선 9,600, 10,300 틱 = NONE.
- `requalifies` — 보유가 D 종가 기준으로도 셋업을 다시 통과(좁은 봉폭 → 재계산 ATR ≈ 100).
  루프 건너뜀이 없으면 새 엔트리로 교체된다.
- `drops_out` — 보유가 셋업에서 빠짐. 보존이 없으면 와이프 → stamp 폴백.

Red 유효성: 현행 BFB·VCP 는 미리보기에서도 `_candidates = {}` 로 지우고 보유를 재구성한다 →
실효 손절선·`_effective_setup`·10,300 틱 신호가 바뀐다. donchian·kojiro 는 keep 에 남의 보유를
넣는다 → 「남의 보유 엔트리 제거」 단언에서 붉다.
"""

from __future__ import annotations

from contextlib import ExitStack
from datetime import date
from unittest.mock import patch

import pytest
from freezegun import freeze_time

from src.engine.strategy_base import Position, Signal
from tests.unit.engine.strategies import _cycle364_harness as H
from tests.unit.engine.strategies.test_cycle364_preview_held_guard import (
    _donchian_cands,
    _kojiro_enrich_override,
)

pytestmark = pytest.mark.unit

_D = date(2026, 9, 22)
_D_NEXT = date(2026, 9, 23)
_EVENING = "2026-09-22T21:00:00+09:00"
_TICK_AT = "2026-09-22T21:05:00+09:00"
_HOLIDAYS = {date(2026, 9, 24), date(2026, 9, 25)}

_BUY, _HIGH, _TICK = 10_000, 11_000, 10_300
_OTHER = H.T_UP        # 다른 전략이 보유한 종목 — 이 전략의 아침 후보였다
_NDC_OWN = "990107"    # 이 전략의 익일청산대기(보유 행은 이미 없다 — 가장 좁은 경우)
_NDC_OTHER = "990108"  # 다른 전략의 익일청산대기


def _fake_calendar(monkeypatch):
    async def _cal(d):
        return d.weekday() < 5 and d not in _HOLIDAYS

    monkeypatch.setattr("src.engine.trading_calendar._lookup_open", _cal)


def _pending_ndc(monkeypatch, entries):
    import src.engine.scheduler as sched_mod

    monkeypatch.setattr(sched_mod.trading_scheduler, "_pending_next_day_clear", set(entries))


def _held_series() -> list[dict]:
    """좁은 봉폭(고가 +40 · 저가 −60) 상승 140봉 — 재계산 ATR ≈ 100. 종가 끝자리 1(다른 합성
    종목과 겹치지 않는다 — `close_to_date` 식별)."""
    return H.trend_series(_D, 140, base=9_001, step=10, hi=40, lo=60, growth=1.0)


def _position(sid: str) -> Position:
    return Position(
        ticker=H.HELD, buy_price=_BUY, quantity=9, order_no="O-052710", strategy_id=sid,
        buy_date=date(2026, 9, 21), high_since_buy=_HIGH,
    )


# ──────────────────────────── BFB · VCP 보유 셋업 ────────────────────────────

def _seed_bfb(s) -> dict:
    s.state.positions[H.HELD] = _position(s.strategy_id)
    s._position_setup[H.HELD] = {
        "flag_low": 9_000, "flag_high": 10_200, "pole_high": 10_500, "pole_start": 8_500,
        "atr14": 300,
    }
    live = {
        "pole_start": 8_500, "pole_high": 10_500, "flag_high": 10_200, "flag_low": 9_000,
        "flag_avg_volume": 50_000, "pole_len": 5, "flag_len": 3, "atr14": 700, "prev_close": 10_450,
    }
    s._candidates[H.HELD] = live
    return live


def _seed_vcp(s) -> dict:
    s.state.positions[H.HELD] = _position(s.strategy_id)
    s._position_setup[H.HELD] = {"base_low": 9_000, "atr14": 300, "ema50": 9_500}
    live = {
        "base_high": 10_200, "base_low": 9_000, "last_pullback_pct": 0.05, "atr14": 700,
        "ema50": 9_000, "ema150": 8_800, "ema200": 8_500, "prev_close": 10_450,
        "avg_volume_20": 50_000,
    }
    s._candidates[H.HELD] = live
    return live


_SEED = {"bull_flag_breakout": _seed_bfb, "vcp_breakout": _seed_vcp}


def _closes_of(cands: dict, tickers) -> dict[int, str]:
    out: dict[int, str] = {}
    for t in tickers:
        for c in cands.get(t) or []:
            out[int(c["stck_clpr"])] = t
    return out


def _detection_override(stack: ExitStack, s, cands: dict, *, passing: set[str], failing: set[str]):
    """보유/지정 종목만 셋업 검출 결과를 고정한다 — 나머지는 실검출 그대로(wraps).

    `passing` = 셋업 통과(새 엔트리가 생긴다), `failing` = 셋업 탈락."""
    owner = _closes_of(cands, passing | failing)

    def _who(candles):
        if not candles:
            return None
        return owner.get(int(candles[0]["stck_clpr"]))

    if s.strategy_id == "bull_flag_breakout":
        real = s._detect_pole_and_flag_detailed

        def _det(candles):
            t = _who(candles)
            if t in passing:
                return ({
                    "pole_start": 8_600, "pole_high": 10_700, "flag_high": 10_500,
                    "flag_low": 10_150, "flag_avg_volume": 40_000, "pole_len": 5, "flag_len": 3,
                }, "", {"best_return": 24.4})
            if t in failing:
                return (None, "pole_return", {"best_return": 3.0})
            return real(candles)

        stack.enter_context(patch.object(s, "_detect_pole_and_flag_detailed", _det))
        return

    real_trend, real_base = s._check_trend_filter, s._detect_base
    real_pull, real_vol = s._check_pullback_sequence, s._check_volume_contraction

    def _trend(candles, *a, **k):
        t = _who(candles)
        if t in passing:
            return {"ema50": 10_350, "ema150": 10_000, "ema200": 9_800}
        if t in failing:
            return None
        return real_trend(candles, *a, **k)

    def _base(candles, *a, **k):
        if _who(candles) in passing:
            return {"high": 10_600, "low": 10_100, "avg_volume_20": 40_000,
                    "last_pullback_pct": 0.05, "last_pullback_count": 2}
        return real_base(candles, *a, **k)

    def _pull(candles, base, *a, **k):
        return True if _who(candles) in passing else real_pull(candles, base, *a, **k)

    def _vol(candles, base, *a, **k):
        return True if _who(candles) in passing else real_vol(candles, base, *a, **k)

    stack.enter_context(patch.object(s, "_check_trend_filter", _trend))
    stack.enter_context(patch.object(s, "_detect_base", _base))
    stack.enter_context(patch.object(s, "_check_pullback_sequence", _pull))
    stack.enter_context(patch.object(s, "_check_volume_contraction", _vol))


def _exit_view(s) -> dict:
    """청산 입력 3면 — 리졸버 · 실효 손절선 미러 · 10,300 틱 신호 (21:05 KST 에서 잰다)."""
    with freeze_time(_TICK_AT):
        return {
            "setup": dict(s._effective_setup(H.HELD, observe=False)),
            "stop": s.get_effective_stop_price(H.HELD),
            "signal": s.check_exit_signal(H.HELD, _TICK, _TICK),
        }


async def _run_bfb_vcp(monkeypatch, sid, *, variant, as_of, protected=(H.HELD,)):
    _fake_calendar(monkeypatch)
    s = H.make_strategy(sid)
    live = _SEED[sid](s)
    cands = H.universe(_D)
    cands[H.HELD] = _held_series()
    before = _exit_view(s)
    passing = {H.HELD} if variant == "requalifies" else set()
    failing = {H.HELD} if variant == "drops_out" else set()
    with freeze_time(_EVENING):
        _, prev_close = await H.run_prepare(
            s, cands, as_of=as_of, protected=protected,
            extra=lambda st: _detection_override(st, s, cands, passing=passing, failing=failing),
        )
    after = _exit_view(s)
    return s, live, before, after, prev_close


_BFB_VCP = ("bull_flag_breakout", "vcp_breakout")
_VARIANTS = ("requalifies", "drops_out")


def test_r1_0_scenario_premise_before_preview_stop_9600_and_tick_none():
    """시나리오 전제 — 미리보기 전 실효 손절선 9,600(live atr 700 샹들리에), 10,300 틱 = NONE."""
    for sid in _BFB_VCP:
        s = H.make_strategy(sid)
        _SEED[sid](s)
        v = _exit_view(s)
        assert v["stop"] == 9_600 and v["signal"] == Signal.NONE, (sid, v)
        assert v["setup"]["atr14"] == 700, (sid, v["setup"])


# ══════════════════════════════════════════════════════════════════════
# R1-a — BFB·VCP 미리보기는 보유 청산 입력을 바꾸지 않는다
# ══════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("variant", _VARIANTS)
@pytest.mark.parametrize("sid", _BFB_VCP)
async def test_r1_a_preview_when_held_position_then_exit_inputs_identical(monkeypatch, sid, variant):
    s, live, before, after, prev_close = await _run_bfb_vcp(
        monkeypatch, sid, variant=variant, as_of=_D_NEXT,
    )
    assert s._candidates.get(H.HELD) is live, (
        f"{sid}/{variant}: 미리보기가 보유 `_candidates` 엔트리를 지우거나 교체했다 — "
        "`_effective_setup` 은 live 엔트리를 우선한다 (R1)"
    )
    assert after["setup"] == before["setup"], f"{sid}/{variant}: 리졸버 값이 바뀌었다 {before['setup']} → {after['setup']}"
    assert after["stop"] == before["stop"] == 9_600, (
        f"{sid}/{variant}: 실효 손절선 {before['stop']} → {after['stop']} — 21:30 portfolio_risk·"
        "잔고 화면 손절선이 미리보기 값으로 움직였다 (R1)"
    )
    assert after["signal"] == Signal.NONE, (
        f"{sid}/{variant}: 미리보기 직후 10,300 틱이 {after['signal']} — 장외 계산이 야간 청산을 만들었다 (R1)"
    )
    assert H.HELD not in prev_close, f"{sid}/{variant}: 미리보기가 보유 종목 ticker_prev_close 를 썼다"


@pytest.mark.parametrize("variant", _VARIANTS)
@pytest.mark.parametrize("sid", _BFB_VCP)
async def test_r1_a_control_non_preview_when_held_position_then_exit_inputs_rewritten(monkeypatch, sid, variant):
    """대조군(as_of=오늘) — 현행대로 와이프·재구성 → 손절선이 올라가 10,300 틱이 TRAILING_STOP.
    이 대조군이 초록이라는 것이 R1 이 막는 것의 증거다."""
    s, live, before, after, _ = await _run_bfb_vcp(monkeypatch, sid, variant=variant, as_of=_D)
    assert s._candidates.get(H.HELD) is not live
    assert after["stop"] != before["stop"] and after["stop"] > _TICK, (sid, variant, before, after)
    assert after["signal"] == Signal.TRAILING_STOP, (sid, variant, after)


@pytest.mark.parametrize("sid", _BFB_VCP)
async def test_r1_a_preview_when_run_then_scanned_lists_only_this_run(monkeypatch, sid):
    """🔶 donchian §2.1 규약 — 미리보기 `_scanned_tickers` 에 보존한 보유 엔트리를 넣지 않는다."""
    s, _, _, _, _ = await _run_bfb_vcp(monkeypatch, sid, variant="drops_out", as_of=_D_NEXT)
    assert H.HELD not in s.get_scanned_tickers(), (
        f"{sid}: 셋업에서 빠진 보유가 D+1 목록에 올랐다 — 21:00 step 99 가 보유를 내일 후보로 적는다"
    )


@pytest.mark.parametrize("sid", _BFB_VCP)
async def test_r1_a_preview_retry_when_universe_empty_then_held_entry_survives(monkeypatch, sid):
    """유니버스 0 → 30초×3 재시도 경로의 와이프도 보유 엔트리를 남긴다."""
    _fake_calendar(monkeypatch)
    s = H.make_strategy(sid)
    live = _SEED[sid](s)
    with freeze_time(_EVENING):
        await H.run_prepare(s, {}, as_of=_D_NEXT, protected=(H.HELD,))
    assert s._candidates.get(H.HELD) is live, f"{sid}: 재시도 와이프가 보유 엔트리를 지웠다"


# ══════════════════════════════════════════════════════════════════════
# R1-b — 자기 보유는 헬퍼가 ∅ 여도 지킨다(합집합, Y2)
# ══════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("sid", _BFB_VCP)
async def test_r1_b_bfb_vcp_preview_when_protected_helper_empty_then_own_position_still_guarded(monkeypatch, sid):
    s, live, before, after, prev_close = await _run_bfb_vcp(
        monkeypatch, sid, variant="requalifies", as_of=_D_NEXT, protected=(),
    )
    assert s._candidates.get(H.HELD) is live, (
        f"{sid}: 헬퍼(전 전략 보유 조회)가 ∅ 를 돌려주자 자기 보유를 재구성했다 — 보호 집합은 "
        "자기 positions ∪ 헬퍼의 합집합이어야 한다 (Y2)"
    )
    assert after == before and H.HELD not in prev_close


@pytest.mark.parametrize("sid", ["donchian_swing", "kojiro"])
async def test_r1_b_donchian_kojiro_preview_when_protected_helper_empty_then_own_position_still_guarded(monkeypatch, sid):
    """round-1 tester 제안 Y2 영구화 — 헬퍼 ∅ 에서도 자기 보유 엔트리·stage3 스탬프 보존, 야간 청산 0."""
    _fake_calendar(monkeypatch)
    s = H.make_strategy(sid)
    seeded = H.seed_held(s, as_of_day=_D)
    cands = _donchian_cands() if sid == "donchian_swing" else H.universe(_D)
    spies: dict = {}
    extra = (lambda st: _kojiro_enrich_override(st, cands, spies)) if sid == "kojiro" else None
    with freeze_time(_EVENING):
        _, prev_close = await H.run_prepare(s, cands, as_of=_D_NEXT, protected=(), extra=extra)
    assert s._candidates.get(H.HELD) is seeded["candidate"], f"{sid}: 헬퍼 ∅ 에서 자기 보유 엔트리가 바뀌었다 (Y2)"
    assert H.HELD not in prev_close
    if sid == "kojiro":
        assert s._held_stage3.get(H.HELD) is seeded["stage3"], "헬퍼 ∅ 에서 stage3 가 다시 찍혔다 (Y2)"
        with freeze_time(_TICK_AT):
            assert s.check_exit_signal(H.HELD, 54_000, 54_000) == Signal.NONE


# ══════════════════════════════════════════════════════════════════════
# R1-c — 남의 보유는 보존하지 않고(목록 오염 차단) 재구성도 하지 않는다
# ══════════════════════════════════════════════════════════════════════
def _seed_own(s):
    if s.strategy_id in _SEED:
        return _SEED[s.strategy_id](s)
    return H.seed_held(s, as_of_day=_D)["candidate"]


def _stale_other_entry(s) -> dict:
    """아침에 이 전략의 후보였던 `_OTHER` 엔트리(그 뒤 다른 전략이 샀다)."""
    entry = dict(next(iter(s._candidates.values())))
    entry["prev_close"] = 12_345
    s._candidates[_OTHER] = entry
    return entry


def _universe_for(sid: str) -> dict:
    cands = _donchian_cands() if sid == "donchian_swing" else H.universe(_D)
    if sid in _SEED:
        cands[H.HELD] = _held_series()
    return cands


async def _run_other(monkeypatch, sid, *, as_of, ndc=()):
    _fake_calendar(monkeypatch)
    _pending_ndc(monkeypatch, ndc)
    s = H.make_strategy(sid)
    own = _seed_own(s)
    stale = _stale_other_entry(s)
    cands = _universe_for(sid)
    protected = {H.HELD, _OTHER} | {t for (t, _sid) in ndc}
    spies: dict = {}

    def _extra(st):
        if sid == "kojiro":
            _kojiro_enrich_override(st, cands, spies)   # T_UP(=_OTHER) 이 내일 후보 자격을 얻는다
        elif sid in _SEED:
            _detection_override(st, s, cands, passing={_OTHER}, failing={H.HELD})

    with freeze_time(_EVENING):
        _, prev_close = await H.run_prepare(s, cands, as_of=as_of, protected=protected, extra=_extra)
    return s, own, stale, prev_close


_FOUR = ("donchian_swing", "kojiro", "bull_flag_breakout", "vcp_breakout")


@pytest.mark.parametrize("sid", _FOUR)
async def test_r1_c_preview_when_other_strategy_holds_ticker_then_not_kept_not_rebuilt(monkeypatch, sid):
    s, own, stale, prev_close = await _run_other(monkeypatch, sid, as_of=_D_NEXT)
    assert s._candidates.get(H.HELD) is own, f"{sid}: 자기 보유 엔트리는 같은 객체로 남아야 한다"
    assert _OTHER not in s._candidates, (
        f"{sid}: 다른 전략의 보유 종목 엔트리를 보존했거나 다시 만들었다 — kojiro held_only · "
        "donchian get_targets_status 가 남의 보유로 오염된다 (R1)"
    )
    assert _OTHER not in s.get_scanned_tickers(), f"{sid}: 남의 보유가 D+1 목록(step 99)에 올랐다"
    assert _OTHER not in prev_close, f"{sid}: 미리보기가 남의 보유 종목 ticker_prev_close 를 썼다 (skip all)"


async def test_r1_c_donchian_preview_when_other_strategy_holds_ticker_then_targets_status_clean(monkeypatch):
    s, _, _, _ = await _run_other(monkeypatch, "donchian_swing", as_of=_D_NEXT)
    assert _OTHER not in s.get_targets_status(), "donchian 대시보드 목록이 남의 보유로 오염됐다 (R1)"


@pytest.mark.parametrize("sid", _FOUR)
async def test_r1_c_control_non_preview_when_other_ticker_qualifies_then_rebuilt(monkeypatch, sid):
    """대조군(as_of=오늘) — 현행대로 남의 보유 종목도 후보로 재구성된다(매수는 registry 가 막는다).
    미리보기의 「건너뜀」이 어디서 오는지 보여 준다."""
    s, _, stale, _ = await _run_other(monkeypatch, sid, as_of=_D)
    assert _OTHER in s._candidates and s._candidates[_OTHER] is not stale, (
        f"{sid}: 시나리오 전제 — 비미리보기에서는 _OTHER 가 내일 후보로 재구성돼야 한다"
    )


# ══════════════════════════════════════════════════════════════════════
# R1-d — 익일청산대기: 자기 것만 보존
# ══════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("sid", _FOUR)
async def test_r1_d_preview_when_next_day_clear_pending_then_only_own_entry_kept(monkeypatch, sid):
    _fake_calendar(monkeypatch)
    s = H.make_strategy(sid)
    _pending_ndc(monkeypatch, {(_NDC_OWN, sid), (_NDC_OTHER, "long_tail_volatility")})
    own_ndc = {"prev_close": 1, "atr": 1}  # 아침 recompute 가 남긴 자기 익일청산대기 엔트리(모양 무관 — 동일성만 본다)
    s._candidates[_NDC_OWN] = own_ndc
    s._candidates[_NDC_OTHER] = {"prev_close": 2}
    with freeze_time(_EVENING):
        await H.run_prepare(
            s, H.universe(_D), as_of=_D_NEXT, protected=(_NDC_OWN, _NDC_OTHER),
        )
    assert s._candidates.get(_NDC_OWN) is own_ndc, (
        f"{sid}: 자기 익일청산대기 엔트리를 지웠다 — keep = 자기 보유 ∪ 자기 익일청산대기 (R1)"
    )
    assert _NDC_OTHER not in s._candidates, f"{sid}: 남의 익일청산대기 엔트리를 보존했다 (R1)"
