"""사이클 223-G Red — 공휴일 다음 첫 거래일 **과다 계상** (검증 신규 발견, MEDIUM).

## 결함

F1 이 도입한 일반화는 캐시 최신일 이후 구간을 weekday 로 메운다:

    held = |{d ∈ cache : buy < d ≤ today}|
         + |{weekday d : max(cache_max, buy) < d ≤ today}|      ← 갭을 weekday 로 메움

이 메움은 **"캐시 밖 갭의 원인은 항상 스테일"** 을 가정한다. 그러나 라이브 세션 중
`cache_max` 는 **구조적으로 직전 거래일**이다 — `_update_trading_days` 호출부가
`prepare`(부팅·개장 전) 와 `recompute_held_atr`(부팅/저녁) 뿐이라 장중엔 오늘 봉이
캐시에 없다. 따라서 **weekday 공휴일이 끼면 갭의 원인은 스테일이 아니라 휴장**인데
메움이 그 휴장일을 영업일로 세어 **과다 계상 → 시간청산 조기 발화**가 된다.

    금 08-14 공휴일 → 월 08-17 :  F1 (5,True)  진실 4    +1
    월 08-17 공휴일 → 화 08-18 :  F1 (5,True)  진실 4    +1
    연휴 3일(08-12~14) → 월 08-17: F1 (5,True)  진실 2    +3

빈도는 드문 열화가 아니라 **연 12~15회 되풀이되는 캘린더 이벤트**(설·추석·개천절·
한글날·성탄절 직후 첫 거래일)이고, 방향은 이번 사이클 S2/S3 가 잡으려던 과대발화와
**같은 방향**이라 시정 효과를 부분 상쇄한다.

## 시정 계약 — 갭 기여를 `today` 하루로 한정

`check_exit_signal` 이 평가되는 시점은 항상 **활성 세션**(`on_tick` = 시세 수신 중,
스윙 REST 폴 = 09:05~15:20 창)이라 **오늘은 영업일임이 보장**된다. 반면 `cache_max` 와
`today` 사이의 나머지 날들은 휴장인지 스테일인지 **구분할 수 없다**.

    held = |{d ∈ cache : buy < d ≤ today}| + (1 if today > buy and today ∉ cache else 0)
    used_fallback = cache_max < _prev_weekday(today)          ← 가시성은 유지

- 정상일(cache_max = 직전 거래일): 갭 = 오늘 하나 → **정확**, `used_fallback=False`
- 공휴일 직후(cache_max = 휴장 전 거래일): 갭 = 오늘 하나 → **정확**(휴장일 미계상)
- 스테일 캐시: 과소 계상이지만 `used_fallback=True` 로 **드러난다**

과소 계상은 청산을 **늦춘다 = 보유 연장**이고, H-1 사이클의 *"남는 오차는 과소 한
방향뿐이고 그 방향은 청산을 늦춘다"* 원칙과 일치한다. 과다 계상(조기 청산)은 승자를
자르는 방향이라 훨씬 비싸다. 즉 **F1 의 계상 변경은 되돌리고 가시성 변경은 유지**한다
— 원래 F1 지적의 본질은 "무음"이었지 "값"이 아니었다.
"""

from __future__ import annotations

import ast
import datetime as _dt
import logging
from pathlib import Path

import pytest
from freezegun import freeze_time

from src.engine.strategies.donchian_swing import DonchianSwingStrategy
from src.engine.strategy_base import Position, Signal, StrategyConfig

pytestmark = pytest.mark.unit
_LOGGER = "src.engine.strategies.donchian_swing"
D = _dt.date

_REPO_ROOT = Path(__file__).resolve().parents[4]
_DONCHIAN = _REPO_ROOT / "src" / "engine" / "strategies" / "donchian_swing.py"


def _mk(n_days: int = 2, **params) -> DonchianSwingStrategy:
    cfg = StrategyConfig(
        strategy_id="donchian_swing", name="도치안", weight=0.2,
        params={"sizing_mode": "position_ratio", "breakout_fail_n_days": n_days, **params},
    )
    s = DonchianSwingStrategy(cfg)
    s.state.total_investment = 100_000_000
    return s


def _arm(s, ticker="005930", buy_date=None, buy_price=10_000, breakout_high=11_000):
    pos = Position(ticker=ticker, buy_price=buy_price, quantity=10, order_no="O",
                   strategy_id="donchian_swing", buy_date=buy_date)
    pos.high_since_buy = buy_price
    s.state.positions[ticker] = pos
    s._candidates[ticker] = {"prev_close": buy_price, "atr": 0, "ema60": 0,
                             "donchian_high": breakout_high}
    s._breakout_high[ticker] = breakout_high
    return pos


# 2026-08 달력: 10(월) 11(화) 12(수) 13(목) 14(금) / 17(월) 18(화) 19(수) 20(목) 21(금)
_MON, _TUE, _WED, _THU, _FRI = (D(2026, 8, d) for d in (10, 11, 12, 13, 14))
_MON2, _TUE2, _WED2, _THU2 = (D(2026, 8, d) for d in (17, 18, 19, 20))


# ===========================================================================
# G-1 ~ G-3 — 공휴일 직후 첫 거래일: 진실값을 돌려준다 (F1 은 +1 / +3 과다)
# ===========================================================================
def test_g1_holiday_friday_then_monday_counts_truth():
    """금 08-14 **공휴일** → 월 08-17. 캐시 max=08-13(휴장 전 마지막 거래일).

    buy=08-10 → 진실 4 (08-11·12·13·17). F1 은 갭(08-14·08-17)을 weekday 로 메워 5.
    """
    s = _mk()
    s._trading_days = {_MON, _TUE, _WED, _THU}          # 08-14 는 공휴일이라 부재
    days, used_fallback = s._business_days_held(_MON, _MON2)
    assert days == 4, (
        f"G: 공휴일(08-14)을 영업일로 세면 안 된다 — 진실 4 (08-11·12·13·17), got {days}"
    )
    assert used_fallback is True, "가시성은 유지 — 캐시가 직전 weekday 에 미도달"


def test_g2_holiday_monday_then_tuesday_counts_truth():
    """월 08-17 **공휴일** → 화 08-18. 캐시 max=08-14.

    buy=08-11 → 진실 4 (08-12·13·14·18). F1 은 갭(08-17·08-18)을 메워 5.
    """
    s = _mk()
    s._trading_days = {_MON, _TUE, _WED, _THU, _FRI}
    days, used_fallback = s._business_days_held(_TUE, _TUE2)
    assert days == 4, (
        f"G: 공휴일(08-17)을 영업일로 세면 안 된다 — 진실 4 (08-12·13·14·18), got {days}"
    )
    assert used_fallback is True


def test_g3_three_day_holiday_then_monday_counts_truth():
    """연휴 3일(08-12·13·14 휴장) → 월 08-17. 캐시 max=08-11.

    buy=08-10 → 진실 2 (08-11·08-17). F1 은 갭 4일(12·13·14·17)을 메워 5 = **+3**.
    """
    s = _mk()
    s._trading_days = {_MON, _TUE}
    days, used_fallback = s._business_days_held(_MON, _MON2)
    assert days == 2, (
        f"G: 연휴 3일을 영업일로 세면 안 된다 — 진실 2 (08-11·08-17), got {days}"
    )
    assert used_fallback is True


@freeze_time("2026-08-17 10:00:00+09:00")
def test_g3b_three_day_holiday_does_not_fire_early():
    """같은 상황에서 `n_days=3` 청산이 **조기 발화하지 않는다** (진실 2 < 3).

    F1 은 5 를 세어 발화 = 승자를 자르는 방향의 과다 계상.
    """
    s = _mk(n_days=3)
    s._trading_days = {_MON, _TUE}
    _arm(s, buy_date=_MON)
    assert s.check_exit_signal("005930", 9_800, 9_900) == Signal.NONE, (
        "G: 공휴일 과다 계상으로 시간청산이 1영업일(연휴면 3영업일) 일찍 발화하면 안 된다"
    )


# ===========================================================================
# G-4 — 정상일(cache_max = 직전 거래일): 정확 + used_fallback=False
# ===========================================================================
@pytest.mark.parametrize(
    "cache,buy,today,expected",
    [
        # 캐시 D-1(금 08-14) · 오늘 월 08-17 → 갭 = 오늘 하나
        ([_MON, _TUE, _WED, _THU, _FRI], _FRI, _MON2, 1),
        # 캐시 D-1(수 08-19) · 오늘 목 08-20
        ([_FRI, _MON2, _TUE2, _WED2], _TUE2, _THU2, 2),
        # 캐시 D-1(목 08-13) · 오늘 금 08-14
        ([_MON, _TUE, _WED, _THU], _MON, _FRI, 4),
    ],
)
def test_g4_normal_day_is_exact_without_fallback(cache, buy, today, expected):
    s = _mk()
    s._trading_days = set(cache)
    assert s._business_days_held(buy, today) == (expected, False)


# ===========================================================================
# G-5 — 스테일 캐시: 과소 계상이지만 가시성(`used_fallback=True`)은 보존
# ===========================================================================
def test_g5_stale_cache_underreports_but_is_visible():
    """캐시 max=08-14 · buy=08-14 · today=08-20 (진실 4).

    스테일과 휴장을 **구분할 수 없으므로** 갭은 오늘 하루만 센다 → 1 (과소).
    과소 = 청산을 늦춘다 = 보유 연장(H-1 원칙)이고, `used_fallback=True` 가 드러낸다.
    """
    s = _mk()
    s._trading_days = {_MON, _TUE, _WED, _THU, _FRI}
    days, used_fallback = s._business_days_held(_FRI, _THU2)
    assert days == 1, f"G: 갭 기여는 오늘 하루뿐 — got {days}"
    assert used_fallback is True, (
        "G: 과소 계상은 허용하되 **무음은 금지** — F1 지적의 본질은 값이 아니라 무음이었다"
    )


@freeze_time("2026-08-20 10:00:00+09:00")
def test_g5b_stale_cache_emits_fallback_log(caplog):
    """스테일 캐시에서 폴백 로그가 실제로 남는다 (미발화 틱에서도)."""
    caplog.set_level(logging.INFO, logger=_LOGGER)
    s = _mk(n_days=2)
    s._trading_days = {_MON, _TUE, _WED, _THU, _FRI}
    _arm(s, buy_date=_FRI)
    assert s.check_exit_signal("005930", 9_800, 9_900) == Signal.NONE
    assert any("days_held_fallback" in r.getMessage() for r in caplog.records), (
        "G: 과소 계상 상태가 로그로 드러나야 한다"
    )


# ===========================================================================
# G-6 ~ G-8 — 경계 회귀
# ===========================================================================
def test_g6_same_day_buy_is_zero():
    """매수 당일 → 0 (갭 보정이 매수일 자신을 세면 안 된다)."""
    s = _mk()
    s._trading_days = {_MON, _TUE, _WED, _THU, _FRI, _MON2}
    days, _fb = s._business_days_held(_MON2, _MON2)
    assert days == 0


def test_g6b_same_day_buy_zero_even_when_today_absent_from_cache():
    """캐시에 오늘이 없어도 매수 당일은 0 (`today > buy` 가드)."""
    s = _mk()
    s._trading_days = {_MON, _TUE, _WED, _THU}
    days, _fb = s._business_days_held(_FRI, _FRI)
    assert days == 0


def test_g7_today_already_in_cache_is_not_double_counted():
    """캐시가 `today` 를 이미 포함하면 갭 보정 없음 (이중 계상 차단)."""
    s = _mk()
    s._trading_days = {_MON, _TUE, _WED, _THU, _FRI, _MON2, _TUE2, _WED2, _THU2}
    assert s._business_days_held(_TUE2, _THU2) == (2, False)


def test_g7b_holiday_gap_inside_cache_is_authoritative():
    """캐시 **안쪽** 휴장 갭은 캐시가 정본 — 추석(10-01~10-05) 09-30 매수 → 10-06 = 1."""
    s = _mk()
    s._trading_days = {D(2026, 9, 25), D(2026, 9, 28), D(2026, 9, 29),
                       D(2026, 9, 30), D(2026, 10, 6)}
    assert s._business_days_held(D(2026, 9, 30), D(2026, 10, 6)) == (1, False)


def test_g8_future_buy_date_is_graceful():
    """미래 매수일(시계 스큐·수동 DB 편집) → 음수/예외 없이 0."""
    s = _mk()
    s._trading_days = {_MON, _TUE, _WED, _THU, _FRI}
    days, _fb = s._business_days_held(D(2026, 8, 25), _THU2)
    assert days == 0, f"미래 buy_date 는 graceful 0 — got {days}"


def test_g8b_future_buy_date_graceful_on_fallback_path():
    """캐시 부재(전면 폴백) 경로도 미래 매수일에 graceful 0."""
    s = _mk()
    s._trading_days = set()
    days, used_fallback = s._business_days_held(D(2026, 8, 25), _THU2)
    assert days == 0
    assert used_fallback is True


def test_g9_full_fallback_path_preserved():
    """`min(cache) > buy_date` / 빈 캐시 = 전면 weekday 폴백 (S3-6 회귀 보존)."""
    s = _mk()
    s._trading_days = {_WED2, _THU2}
    assert s._business_days_held(_FRI, _THU2) == (4, True)
    s._trading_days = set()
    assert s._business_days_held(_FRI, _MON2) == (1, True)


# ===========================================================================
# G-10 (AST) — hot path 계약 유지: await / DB / HTTP 0
# ===========================================================================
def _func(tree: ast.Module, name: str):
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    return None


def test_g10_helper_stays_sync_and_io_free():
    tree = ast.parse(_DONCHIAN.read_text(encoding="utf-8"))
    fn = _func(tree, "_business_days_held")
    assert fn is not None and not isinstance(fn, ast.AsyncFunctionDef)
    assert not [n for n in ast.walk(fn) if isinstance(n, ast.Await)]
    body = ast.unparse(fn)
    for banned in ("fetch_daily_candles", "get_recent_daily_normalized", "add_business_days",
                   "pg.fetch", "pg.execute", "write_log", "httpx", "kis_request",
                   "kis_get_quote", "asyncio"):
        assert banned not in body, f"G: `_business_days_held` 에 I/O `{banned}` 금지"


def test_g10b_prev_weekday_only_feeds_fallback_flag():
    """`_prev_weekday` 는 **`used_fallback` 판정 전용** — 갭 메움에 쓰이지 않는다.

    갭 메움 제거의 구조적 봉인: 캐시 분기에 weekday 순회 루프가 남아 있으면
    공휴일 과다 계상이 되살아난다.
    """
    src = _DONCHIAN.read_text(encoding="utf-8")
    fn = _func(ast.parse(src), "_business_days_held")
    stmts = list(fn.body)
    if (stmts and isinstance(stmts[0], ast.Expr)
            and isinstance(stmts[0].value, ast.Constant)):
        stmts = stmts[1:]                      # docstring 제외 — 결함 서술은 허용
    # 캐시 분기(= `return ..., cache_max ...` 를 품은 If) 안에는 순회 루프가 없어야 한다
    cache_branch = None
    for node in stmts:
        if isinstance(node, ast.If) and "cache_max" in ast.unparse(node):
            cache_branch = node
            break
    assert cache_branch is not None, "캐시 분기를 찾지 못했다 (탐지기 결함)"
    loops = [n for n in ast.walk(cache_branch)
             if isinstance(n, (ast.While, ast.For)) or isinstance(n, ast.comprehension)]
    # 캐시 순회 comprehension 1 개(= `sum(1 for d in cache ...)`)만 허용
    assert len([n for n in loops if isinstance(n, (ast.While, ast.For))]) == 0, (
        "G: 캐시 분기의 weekday 순회 루프 = 공휴일 과다 계상 재발 — 갭은 오늘 하루뿐"
    )
