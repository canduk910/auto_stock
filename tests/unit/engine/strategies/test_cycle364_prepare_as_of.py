"""cycle364 S1 Red — A1 `prepare(*, as_of=None)` 기준일 주입 (저녁 미리보기의 본체).

설계 정본 = `_workspace/domain_consult/cycle364_a1_as_of_design.md` §2.1 · §2.3 · §6.2 (A1-1~A1-4).
사용자 결정 2026-09-25 「D3 카드는 모두 권고대로」 = 카드1~5 (가), S1 만.

────────────────────────────────────────────────────────────────────────────
Green 이 맞춰야 하는 계약
────────────────────────────────────────────────────────────────────────────
1) 7전략 + 추상 선언: `async def prepare(self, *, as_of: date | None = None) -> None`
   (키워드 전용, 기본 None). momentum 은 인자만 받는다(`pass`).
2) `as_of is None` → **현행 바이트 동일** (A1-1 골든 = 변경 전 코드에서 뜬 스냅샷).
   `as_of == 오늘` → None 과 같은 계산(미리보기 아님 — 보유 재표시·와이프 현행 그대로).
   `as_of > 오늘` → 미리보기: `today_str = as_of.strftime("%Y%m%d")` 라 오늘 봉을 자르지
   않는다(D 봉이 「전일」), `expected_head = previous_trading_day(as_of)`.
   `as_of < 오늘` → `ValueError` — **상태를 건드리기 전에**(라이브 목록을 지운 뒤 던지면
   거부된 호출이 후보를 날린다).
3) 공용 헬퍼(`strategy_base`): `_resolve_prepare_as_of(as_of) -> (as_of_date, preview: bool)`
   (StrategyBase 메서드 또는 모듈 함수 — 테스트는 둘 다 찾는다) ·
   `_resolve_expected_daily_head(as_of_date: date | None = None)` — 인자 없으면 `today_kst()`
   (cycle363 호출부·테스트 무변경), 있으면 `previous_trading_day(as_of_date)`. INFO 1행
   `[prepare_expected_head] strategy=<id> expected_head=<YYYY-MM-DD|None>` 형식 불변.

골든 기준 = `fixtures/cycle364_prepare_golden.json` (HEAD 3cf032a 에서 `_cycle364_harness`
로 1회 생성). 부동소수는 소수 6자리로 자른다(로컬↔CI ULP 차이 흡수). 같은 프로세스 안의
두 경로 대조(A1-1c)는 자르지 않은 **정확 일치**다.

Red 유효성: 현행 prepare 는 `as_of` 키워드를 받지 않는다 → TypeError. 헬퍼 부재 →
AttributeError/assert. `prepare()` 골든 대조(A1-1a)·A1-3 은 지금 **초록**이어야 한다
(변경 전 행위의 봉인 — 붉으면 하네스가 틀린 것이다).
"""

from __future__ import annotations

import inspect
import json
import logging
import re
from contextlib import ExitStack
from datetime import date
from unittest.mock import AsyncMock, patch

import pytest
from freezegun import freeze_time

from src.engine.strategies.momentum import MomentumStrategy
from src.engine.strategy_base import StrategyBase, StrategyConfig
from tests.unit.engine.strategies import _cycle364_harness as H

pytestmark = pytest.mark.unit

_D = date(2026, 9, 22)          # 화 — 거래일 D
_D_NEXT = date(2026, 9, 23)     # 수 — D+1
_D_PREV = date(2026, 9, 21)     # 월 — D-1
_EVENING = "2026-09-22T21:00:00+09:00"
_HOLIDAYS = {date(2026, 9, 24), date(2026, 9, 25)}   # 추석


def _golden() -> dict:
    return json.loads(H.GOLDEN_PATH.read_text(encoding="utf-8"))


def _fake_calendar(monkeypatch, holidays=_HOLIDAYS):
    """휴장일 seam 명시 — conftest 전역 중립화(None)보다 뒤에 걸려 이긴다."""
    async def _cal(d):
        return d.weekday() < 5 and d not in holidays

    monkeypatch.setattr("src.engine.trading_calendar._lookup_open", _cal)


def _resolve_as_of_fn(strategy):
    fn = getattr(strategy, "_resolve_prepare_as_of", None)
    if fn is None:
        import src.engine.strategy_base as sb

        fn = getattr(sb, "_resolve_prepare_as_of", None)
    assert callable(fn), (
        "`_resolve_prepare_as_of` 미구현 (Red — cycle364 §2.1). StrategyBase 메서드 또는 "
        "strategy_base 모듈 함수 `(as_of) -> (as_of_date, preview)`"
    )
    return fn


# ══════════════════════════════════════════════════════════════════════
# A1-1 — prepare() / prepare(as_of=오늘) 바이트 동일 (골든 = 변경 전 코드)
# ══════════════════════════════════════════════════════════════════════
_CASES = [(scen, sid) for scen in H.SCENARIOS for sid in H.SIDS]


@pytest.mark.parametrize("scenario,sid", _CASES)
async def test_a1_1a_prepare_no_arg_when_run_then_matches_pre_change_golden(scenario, sid):
    """as_of=None 경로 = 변경 전 코드와 바이트 동일. **지금 초록**이어야 한다(Green 뒤에도)."""
    with freeze_time(H.SCENARIOS[scenario]["now"]):
        got = await H.scenario_snapshot(sid, scenario)
    want = _golden()[scenario][sid]
    assert H.dumps(got) == H.dumps(want), (
        f"{scenario}/{sid}: prepare() 결과가 변경 전 골든과 다르다 — as_of=None 경로의 "
        "바이트 동일 계약(§2.1) 위반"
    )


@pytest.mark.parametrize("scenario,sid", _CASES)
async def test_a1_1b_prepare_as_of_today_when_run_then_matches_pre_change_golden(scenario, sid):
    """as_of=오늘 = 미리보기 아님 → 변경 전 prepare() 와 바이트 동일 (보유 재표시 포함)."""
    today = date.fromisoformat(H.SCENARIOS[scenario]["now"][:10])
    with freeze_time(H.SCENARIOS[scenario]["now"]):
        got = await H.scenario_snapshot(sid, scenario, as_of=today)
    want = _golden()[scenario][sid]
    assert H.dumps(got) == H.dumps(want), (
        f"{scenario}/{sid}: prepare(as_of=오늘) 이 변경 전 prepare() 와 다르다 — 오늘 기준일은 "
        "미리보기가 아니다(§2.1)"
    )


@pytest.mark.parametrize("scenario,sid", _CASES)
async def test_a1_1c_prepare_as_of_today_when_same_process_then_exactly_equals_no_arg(scenario, sid):
    """두 경로를 같은 프로세스에서 **자르지 않고** 대조 — 부동소수 끝자리까지 같다."""
    today = date.fromisoformat(H.SCENARIOS[scenario]["now"][:10])
    with freeze_time(H.SCENARIOS[scenario]["now"]):
        a = await H.scenario_snapshot(sid, scenario, exact=True)
    with freeze_time(H.SCENARIOS[scenario]["now"]):
        b = await H.scenario_snapshot(sid, scenario, as_of=today, exact=True)
    assert H.dumps(a) == H.dumps(b), f"{scenario}/{sid}: prepare() ≠ prepare(as_of=오늘) (정확 대조)"


# ══════════════════════════════════════════════════════════════════════
# 시그니처 — 7전략 + 추상 선언
# ══════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize(
    "cls", [StrategyBase, MomentumStrategy, *H.STRATEGIES.values()],
    ids=lambda c: c.__name__,
)
def test_a1_sig_prepare_when_inspected_then_keyword_only_as_of_default_none(cls):
    sig = inspect.signature(cls.prepare)
    p = sig.parameters.get("as_of")
    assert p is not None, f"{cls.__name__}.prepare 에 `as_of` 인자가 없다 (Red — cycle364 §2.1)"
    assert p.kind is inspect.Parameter.KEYWORD_ONLY, (
        f"{cls.__name__}.prepare `as_of` 는 키워드 전용이어야 한다 (실측 {p.kind})"
    )
    assert p.default is None, f"{cls.__name__}.prepare `as_of` 기본값은 None (실측 {p.default!r})"
    positional = [
        n for n, q in sig.parameters.items()
        if n != "self" and q.kind in (q.POSITIONAL_ONLY, q.POSITIONAL_OR_KEYWORD)
    ]
    assert positional == [], f"{cls.__name__}.prepare 위치 인자 추가 금지 (호출 형태 보존): {positional}"


async def test_a1_sig_momentum_when_as_of_passed_then_accepts_without_side_effect():
    m = MomentumStrategy(StrategyConfig(strategy_id="momentum", name="m", params={}, enabled=True))
    with freeze_time(_EVENING):
        await m.prepare(as_of=_D)
        await m.prepare(as_of=_D_NEXT)
    assert m._funnel_steps == [], "momentum prepare 는 funnel 을 채우지 않는다(cycle132)"


# ══════════════════════════════════════════════════════════════════════
# 공용 헬퍼 — `_resolve_prepare_as_of` · `_resolve_expected_daily_head(as_of_date)`
# ══════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize(
    "arg,want",
    [(None, (_D, False)), (_D, (_D, False)), (_D_NEXT, (_D_NEXT, True)),
     (date(2026, 9, 28), (date(2026, 9, 28), True))],
    ids=["none", "today", "tomorrow", "after_holidays"],
)
def test_a1_helper_resolve_prepare_as_of_when_called_then_date_and_preview(arg, want):
    s = H.make_strategy("volatility_breakout")
    fn = _resolve_as_of_fn(s)
    with freeze_time(_EVENING):
        got = fn(arg)
    assert tuple(got) == want, f"_resolve_prepare_as_of({arg!r}) = {got!r} (기대 {want!r})"


def test_a1_helper_resolve_prepare_as_of_when_past_then_value_error():
    s = H.make_strategy("volatility_breakout")
    fn = _resolve_as_of_fn(s)
    with freeze_time(_EVENING), pytest.raises(ValueError):
        fn(_D_PREV)


async def test_a1_helper_expected_head_when_as_of_date_given_then_previous_trading_day_of_it(caplog):
    """저녁 미리보기(as_of=09-28)와 09-28 부팅이 같은 기대 헤드(09-23)를 쓴다 (§2.3)."""
    s = H.make_strategy("kojiro")
    prev = AsyncMock(return_value=date(2026, 9, 23))
    caplog.set_level(logging.INFO)
    with freeze_time("2026-09-23T21:00:00+09:00"), patch(
        "src.engine.trading_calendar.previous_trading_day", prev,
    ):
        got = await s._resolve_expected_daily_head(date(2026, 9, 28))
    assert got == date(2026, 9, 23)
    arg = prev.await_args.args[0] if prev.await_args.args else prev.await_args.kwargs.get("today")
    assert arg == date(2026, 9, 28), f"기준일(as_of)의 직전 영업일이어야 한다 — 벽시계 오늘 금지 (실측 {arg!r})"
    lines = [
        r.getMessage() for r in caplog.records
        if r.getMessage().startswith("[prepare_expected_head] ")
    ]
    assert lines == ["[prepare_expected_head] strategy=kojiro expected_head=2026-09-23"], lines


async def test_a1_helper_expected_head_when_no_arg_then_today_kst_unchanged():
    """cycle363 호출 형태 보존 — 인자 없으면 벽시계 오늘(KST)의 직전 영업일."""
    s = H.make_strategy("donchian_swing")
    prev = AsyncMock(return_value=_D_PREV)
    with freeze_time("2026-09-22T07:46:00+09:00"), patch(
        "src.engine.trading_calendar.previous_trading_day", prev,
    ):
        got = await s._resolve_expected_daily_head()
    assert got == _D_PREV
    arg = prev.await_args.args[0] if prev.await_args.args else prev.await_args.kwargs.get("today")
    assert arg == _D


# ══════════════════════════════════════════════════════════════════════
# A1-2 / A1-3 — 미리보기는 D 봉이 「전일」, 벽시계(as_of=None)는 D 봉을 자른다
# ══════════════════════════════════════════════════════════════════════
def _spy_extra(sid: str, strategy, box: dict):
    """BFB·VCP·kojiro 는 절단 뒤 봉을 받는 첫 계산 지점을 엿본다(행위 무변경 wraps)."""
    def _extra(stack: ExitStack):
        if sid == "bull_flag_breakout":
            box["spy"] = stack.enter_context(patch.object(
                strategy, "_detect_pole_and_flag_detailed",
                wraps=strategy._detect_pole_and_flag_detailed,
            ))
        elif sid == "vcp_breakout":
            box["spy"] = stack.enter_context(patch.object(
                strategy, "_check_trend_filter", wraps=strategy._check_trend_filter,
            ))
        elif sid == "kojiro":
            import src.engine.strategies.kojiro as kmod

            real = kmod.enrich
            seen: list = []

            def _enrich(df, cfg):
                seen.append(int(df["close"].iloc[-1]))
                return real(df, cfg)

            box["closes"] = seen
            stack.enter_context(patch.object(kmod, "enrich", _enrich))
    return _extra


def _prev_bar_date_of_t_up(sid, strategy, prev_close: dict, box: dict, cands) -> str | None:
    """T_UP 종목에서 전략이 「전일」로 쓴 봉의 날짜 (YYYYMMDD)."""
    c2d = {}
    for rows in cands.values():
        if rows:
            c2d.update(H.close_to_date(rows))
    up_closes = set(H.close_to_date(cands[H.T_UP]))
    if sid in ("volatility_breakout", "long_tail_volatility"):
        pc = prev_close.get(H.T_UP)
        return c2d.get(pc) if pc else None
    if sid == "donchian_swing":
        info = strategy._candidates.get(H.T_UP)
        return c2d.get(info["prev_close"]) if info else None
    if sid in ("bull_flag_breakout", "vcp_breakout"):
        for call in box["spy"].call_args_list:
            rows = call.args[0]
            head_close = int(rows[0]["stck_clpr"])
            if head_close in up_closes:
                return c2d[head_close]
        return None
    if sid == "kojiro":
        for close in box["closes"]:
            if close in up_closes:
                return c2d[close]
        return None
    raise AssertionError(sid)


async def _run_prev_bar(sid, monkeypatch, *, as_of):
    _fake_calendar(monkeypatch)
    strategy = H.make_strategy(sid)
    cands = H.universe(_D)  # 머리 = D 완성봉 (20:30 적재 뒤 세계)
    box: dict = {}
    with freeze_time(_EVENING):
        adapter, prev_close = await H.run_prepare(
            strategy, cands, as_of=as_of, extra=_spy_extra(sid, strategy, box),
        )
    return strategy, adapter, prev_close, box, cands


@pytest.mark.parametrize("sid", H.SIDS)
async def test_a1_2_preview_when_as_of_next_day_then_d_bar_is_previous_and_head_d(sid, monkeypatch):
    """D 21:00, as_of=D+1 → D 봉을 자르지 않는다(prev_idx 0) + expected_head=D (M3·M4)."""
    strategy, adapter, prev_close, box, cands = await _run_prev_bar(sid, monkeypatch, as_of=_D_NEXT)
    got = _prev_bar_date_of_t_up(sid, strategy, prev_close, box, cands)
    assert got == _D.strftime("%Y%m%d"), (
        f"{sid}: 미리보기(as_of={_D_NEXT})가 「전일」로 {got} 을 썼다 — D({_D}) 봉이어야 한다. "
        "today_str 를 벽시계로 두면 D 봉이 잘린다 (M3)"
    )
    heads = {c.kwargs.get("expected_head", "<missing>") for c in adapter.await_args_list}
    assert heads == {_D}, (
        f"{sid}: 어댑터 expected_head={heads} — previous_trading_day(as_of={_D_NEXT}) = {_D} 여야 "
        "한다. 벽시계 기준이면 D-1 이 된다 (M4)"
    )


@pytest.mark.parametrize("sid", H.SIDS)
async def test_a1_3_no_arg_when_evening_d_then_d_bar_is_cut_and_head_d_minus_1(sid, monkeypatch):
    """짝 — 같은 시각·같은 봉, as_of=None 은 현행대로 D 봉을 자른다(D-1 이 「전일」). 지금 초록."""
    strategy, adapter, prev_close, box, cands = await _run_prev_bar(sid, monkeypatch, as_of=H._NO_ARG)
    got = _prev_bar_date_of_t_up(sid, strategy, prev_close, box, cands)
    assert got == _D_PREV.strftime("%Y%m%d"), f"{sid}: 현행 절단이 깨졌다 (실측 {got})"
    heads = {c.kwargs.get("expected_head", "<missing>") for c in adapter.await_args_list}
    assert heads == {_D_PREV}, f"{sid}: 벽시계 경로 expected_head={heads} (기대 {_D_PREV})"


# ══════════════════════════════════════════════════════════════════════
# A1-4 — as_of < 오늘 = 프로그래밍 오류, 상태 무접촉
# ══════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("sid", H.SIDS)
async def test_a1_4_prepare_when_as_of_in_past_then_value_error_before_touching_state(sid):
    strategy = H.make_strategy(sid)
    sentinel_steps = [{"step_no": 1, "step_name": "sentinel"}]
    strategy._funnel_steps = sentinel_steps
    strategy._scanned_tickers = ["SENTINEL"]
    cands = H.universe(_D)
    with freeze_time(_EVENING):
        with pytest.raises(ValueError):
            await H.run_prepare(strategy, cands, as_of=_D_PREV)
    assert strategy._funnel_steps is sentinel_steps, f"{sid}: 거부된 호출이 funnel 을 지웠다"
    assert strategy._scanned_tickers == ["SENTINEL"], f"{sid}: 거부된 호출이 후보 목록을 지웠다"


def test_a1_4_marker_prepare_expected_head_format_regex_unchanged():
    """관측 형식 불변 — 기존 cycle363 grep(`strategy=… expected_head=…`) 이 계속 맞는다."""
    import src.engine.strategy_base as sb

    src = inspect.getsource(sb)
    assert re.search(
        r'"\[prepare_expected_head\] strategy=%s expected_head=%s"', src,
    ), "`[prepare_expected_head]` 로그 형식 문자열이 바뀌었다 (§2.1 형식 불변)"
