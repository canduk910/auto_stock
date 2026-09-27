"""cycle382 Red — 시장 유닛(단계형) 공용 지원. 이 모듈은 테스트가 아니다(`test_` 로 시작하지 않는다).

명세 정본 = `_workspace/red/cycle382_market_unit_spec.md` (이하 「명세」)
설계 정본 = `_workspace/domain_consult/cycle376_market_unit.md` §6.3 · §7.3 · §10

## Red 가 못박는 표면 (명세 §3.1 · §3.2)

새 leaf ``src/engine/market_unit.py`` (최상위 import = 표준 라이브러리만):

| 이름 | 계약 |
|---|---|
| ``SOURCE_TICKER="069500"`` · ``MA_WINDOW=60`` · ``SLOPE_LOOKBACK=20`` · ``MIN_ROWS=80`` · ``FETCH_ROWS=120`` · ``STALE_FALLBACK_MAX_CALENDAR_DAYS=10`` | 상수 |
| ``MULTIPLIERS`` | ``MappingProxyType`` — ``up_rising 1.0 · up_falling 0.75 · down_rising 0.5 · down_falling 0.0`` |
| ``MODE_KEY="market_unit_mode"`` · ``MODES=("off","shadow","enforce")`` | 상수 |
| ``normalize_mode(raw) -> (mode, valid)`` | 순수 |
| ``classify(closes) -> (Classification | None, reason)`` | 순수 — Classification 은 ``state``·``m``·``above``·``rising`` 속성을 갖는다 |
| ``Snapshot`` | frozen dataclass — ``as_of preview ok state m reason bar_date expected_head rows close sma60 sma60_prev above rising`` |
| ``async compute_snapshot(as_of_date, *, preview) -> Snapshot`` | never-raise. seam = ``src.db.stock_master_daily.get_recent_daily`` · ``src.engine.trading_calendar.previous_trading_day`` (호출 시점 모듈 속성) |
| 로거 | ``logging.getLogger("src.engine.market_unit")`` — **모든** 시장 유닛 마커가 이 로거로 나간다 |

``StrategyBase`` (관문 ``_apply_budget_limit`` 본문 byte 무변경):
``_MARKET_UNIT_ATR_KEY`` · ``_market_unit_snaps: dict[date, Snapshot]`` ·
``async _refresh_market_unit(*, as_of_date, preview)`` · ``_market_unit_view() -> (mode, m, state, reason)`` ·
``_market_unit_lots(current_price, ticker, m)`` (필드 ``path atr design_before design_after lot_before
lot_after remaining_qty fallback``) · ``_market_unit_skip_reason(m, lots)`` · ``_market_unit_sizing(price, ticker)`` ·
``_market_unit_blocks_entry(ticker, price)`` · ``_market_unit_tally_roll(day)``.

## 시계

- aware(`datetime.now(KST)`) 만 쓰는 코드 — freezegun 에 KST 문자열(`"2026-09-28T09:10:00+09:00"`).
- naive(`datetime.now()`) 시간 가드(donchian 09:05~09:30 · BFB/VCP 진입창) — freezegun 에 naive 문자열
  (`"2026-09-28 10:00:00"` = naive 10:00 · KST 19:00 **같은 날짜**). 시장 유닛은 KST **날짜**만 본다.
- 둘 다 필요한 곳(스윙 폴 루프 × donchian) — `kst_naive_datetime_class()` 로 전략 모듈의 `datetime`
  이름을 **freeze 안에서** 바꾸고 **freeze 안에서** 되돌린다(`monkeypatch.context()`). freezegun 1.5.5 는
  naive·aware 를 동시에 KST 로 줄 수 없고, 모듈 속성 캐시 때문에 freeze 시작 때 그 이름을 FakeDatetime
  으로 다시 덮는다 — freeze 전에 꽂으면 앞선 freeze 가 캐시를 만든 뒤(같은 파일 다른 테스트)에만 깨진다.
"""
from __future__ import annotations

import datetime as _dt_mod
import logging
from datetime import date, datetime, timedelta, timezone

import pytest

KST = timezone(timedelta(hours=9))
MU_LOGGER = "src.engine.market_unit"
DAY = date(2026, 9, 28)        # 월 — 추석(09-24~26) 뒤 첫 거래일
NEXT = date(2026, 9, 29)       # 화
HEAD = date(2026, 9, 23)       # 09-28 부팅의 D−1 봉(수)
CHUSEOK = frozenset({date(2026, 9, 24), date(2026, 9, 25)})
T = "990382"                   # 합성 종목 — 실종목·정적 이름표와 겹치지 않는다

TURTLE4 = ("kojiro", "donchian_swing", "bull_flag_breakout", "vcp_breakout")
OTHER3 = ("momentum", "volatility_breakout", "long_tail_volatility")

_CLASSES = {
    "kojiro": ("src.engine.strategies.kojiro", "KojiroStrategy"),
    "donchian_swing": ("src.engine.strategies.donchian_swing", "DonchianSwingStrategy"),
    "bull_flag_breakout": ("src.engine.strategies.bull_flag_breakout", "BullFlagBreakoutStrategy"),
    "vcp_breakout": ("src.engine.strategies.vcp_breakout", "VcpBreakoutStrategy"),
    "momentum": ("src.engine.strategies.momentum", "MomentumStrategy"),
    "volatility_breakout": ("src.engine.strategies.volatility_breakout", "VolatilityBreakoutStrategy"),
    "long_tail_volatility": ("src.engine.strategies.long_tail_volatility", "LongTailVolatilityStrategy"),
}

#: 각 전략 터틀 블록이 실제로 읽는 후보 ATR 키 (명세 §3.2 · AST A09)
ATR_KEY = {
    "kojiro": "atr",
    "donchian_swing": "atr",
    "bull_flag_breakout": "atr14",
    "vcp_breakout": "atr14",
}

#: m → (state, above, rising) — 명세 §1.3
STATE_BY_M = {
    1.0: ("up_rising", True, True),
    0.75: ("up_falling", True, False),
    0.5: ("down_rising", False, True),
    0.0: ("down_falling", False, False),
}

# ── 명세 §11.1 판정 고정 시계열 (오름차순) — 합으로 재검산함 ─────────────────────
F1 = [10000 + 10 * i for i in range(80)]                       # up_rising 1.0
F2 = [12000 - 10 * i for i in range(79)] + [12500]             # up_falling 0.75
F3 = [10000 + 10 * i for i in range(79)] + [9000]              # down_rising 0.5
F4 = list(reversed(F1))                                        # down_falling 0.0
T2 = [9000] * 20 + [10000] * 60                                # 종가=SMA60 동률 → 0.5
T3 = [10000] * 20 + [9000] * 40 + [10000] * 20                 # 기울기 동률 → 0.75
TF = [10000] * 80                                              # 이중 동률 → 0.0
D1 = [50000] + [10000] * 60 + [10010] * 20                     # 81개, up_rising (lookback 21/창 과거 이동 → 0.75)
D3 = [10000] * 60 + [20000] + [9990] * 19                      # down_rising (lookback 19 → 0.0)
D2 = [10000] * 20 + [10100] + [10000] * 59 + [10001]           # 81개, up_falling (MA 61 → 0.5)
D4 = [10000] * 20 + [20000] + [10000] * 58 + [10100]           # down_rising (MA 59 → 0.75)
SERIES_BY_M = {1.0: F1, 0.75: F2, 0.5: F3, 0.0: F4}


# ===========================================================================
# Red 관문 — 새 표면이 없으면 사유를 밝히고 실패한다(skip 금지)
# ===========================================================================
def mu():
    try:
        from src.engine import market_unit
    except ImportError as exc:  # pragma: no cover — Red 단계
        pytest.fail(f"[Red] src/engine/market_unit.py 미존재 — {exc}")
    return market_unit


def need(obj, *names: str) -> None:
    missing = [n for n in names if not hasattr(obj, n)]
    if missing:
        who = getattr(obj, "__name__", type(obj).__name__)
        pytest.fail(f"[Red] {who} 에 {missing} 없음 — cycle382 미구현")


def need_base() -> None:
    from src.engine.strategy_base import StrategyBase

    need(
        StrategyBase,
        "_refresh_market_unit", "_market_unit_view", "_market_unit_lots",
        "_market_unit_skip_reason", "_market_unit_sizing", "_market_unit_blocks_entry",
        "_market_unit_tally_roll",
    )


# ===========================================================================
# 전략 · 스냅샷
# ===========================================================================
def strategy_class(sid: str):
    import importlib

    mod_name, cls_name = _CLASSES[sid]
    return getattr(importlib.import_module(mod_name), cls_name)


def strategy_module(sid: str):
    import importlib

    return importlib.import_module(_CLASSES[sid][0])


def make(sid: str, *, budget: int = 1_000_000, mode: str | None = None, **params):
    """전략 인스턴스. ``mode`` 가 주어지면 ``market_unit_mode`` 를 그 값으로 둔다."""
    from src.engine.strategy_base import StrategyConfig

    p = {"exchange": "KRX", **params}
    if mode is not None:
        p["market_unit_mode"] = mode
    s = strategy_class(sid)(StrategyConfig(strategy_id=sid, name=sid, params=p))
    s.state.total_investment = budget
    return s


def snapshot(m: float, day: date = DAY, *, ok: bool = True, preview: bool = False,
             reason: str | None = None):
    """``market_unit.Snapshot`` 한 칸 (명세 §3.1 필드 전부 키워드)."""
    lf = mu()
    if ok:
        state, above, rising = STATE_BY_M[m]
        mm, rs = m, (reason or "ok")
    else:
        state, above, rising, mm, rs = "unavailable", None, None, 1.0, (reason or "rows_short")
    return lf.Snapshot(
        as_of=day, preview=preview, ok=ok, state=state, m=mm, reason=rs,
        bar_date=day - timedelta(days=1) if ok else None,
        expected_head=day - timedelta(days=1), rows=80 if ok else 0,
        close=10000 if ok else None, sma60=10000.0 if ok else None,
        sma60_prev=10000.0 if ok else None, above=above, rising=rising,
    )


def seed(s, m: float, day: date = DAY, **kw) -> None:
    """오늘(또는 ``day``) 스냅샷을 전략 객체에 직접 심는다 — calc·신호 테스트를 leaf 판정과 분리."""
    need_base()
    s._market_unit_snaps[day] = snapshot(m, day, **kw)


# ===========================================================================
# 일봉 seam
# ===========================================================================
def weekdays_desc(head: date, n: int, *, holidays=CHUSEOK) -> list[date]:
    out: list[date] = []
    d = head
    while len(out) < n:
        if d.weekday() < 5 and d not in holidays:
            out.append(d)
        d -= timedelta(days=1)
    return out


def rows_for(closes_asc: list, head: date = HEAD, *, extra_desc: list[dict] | None = None) -> list[dict]:
    """``get_recent_daily`` 모양(bas_dd **DESC**) — 마지막 종가가 ``head`` 봉이다."""
    dates = weekdays_desc(head, len(closes_asc))           # DESC
    closes_desc = list(reversed(closes_asc))
    rows = [
        {"ticker": "069500", "bas_dd": d, "close_price": c, "open_price": c, "high_price": c,
         "low_price": c, "volume": 1000, "trade_value": 0, "change_rate": 0.0, "raw": {}}
        for d, c in zip(dates, closes_desc)
    ]
    return (extra_desc or []) + rows


class Seams:
    """``get_recent_daily`` · ``previous_trading_day`` 대역. 호출 인자를 기록한다."""

    def __init__(self, rows=None, prev_day=HEAD, *, rows_by_ticker=None) -> None:
        self.rows = rows if rows is not None else rows_for(F2)
        self.prev_day = prev_day
        self.rows_by_ticker = rows_by_ticker or {}
        self.daily_calls: list[tuple] = []
        self.cal_calls: list[date] = []
        self.daily_exc: BaseException | None = None
        self.cal_exc: BaseException | None = None

    async def get_recent_daily(self, ticker, days=20, *a, **k):
        self.daily_calls.append((ticker, days))
        if self.daily_exc is not None:
            raise self.daily_exc
        if ticker == "069500":
            return [dict(r) for r in self.rows]
        return list(self.rows_by_ticker.get(ticker, []))

    async def previous_trading_day(self, d):
        self.cal_calls.append(d)
        if self.cal_exc is not None:
            raise self.cal_exc
        if callable(self.prev_day):
            return self.prev_day(d)
        return self.prev_day

    def install(self, monkeypatch) -> "Seams":
        monkeypatch.setattr("src.db.stock_master_daily.get_recent_daily", self.get_recent_daily)
        monkeypatch.setattr("src.engine.trading_calendar.previous_trading_day", self.previous_trading_day)
        return self

    def patchers(self):
        """``unittest.mock.patch`` 두 개 — ExitStack(prepare 하네스 ``extra``)용."""
        from unittest.mock import patch

        return (
            patch("src.db.stock_master_daily.get_recent_daily", new=self.get_recent_daily),
            patch("src.engine.trading_calendar.previous_trading_day", new=self.previous_trading_day),
        )


# ===========================================================================
# 로그 판독 — 전부 로거 `src.engine.market_unit` (명세 §7)
# ===========================================================================
def open_info(caplog) -> None:
    caplog.set_level(logging.INFO, logger=MU_LOGGER)


def lines(caplog, marker: str, *, min_level: int = logging.INFO, logger: str = MU_LOGGER) -> list[str]:
    return [
        r.getMessage()
        for r in caplog.records
        if r.name == logger and r.levelno >= min_level and r.getMessage().startswith(marker + " ")
    ]


def field(line: str, key: str) -> str:
    token = f"{key}="
    for part in line.split():
        if part.startswith(token):
            return part[len(token):]
    raise AssertionError(f"`{key}=` 없음: {line}")


def fnum(line: str, key: str) -> float:
    return float(field(line, key))


# ===========================================================================
# 시계 — naive 도 KST 벽시계를 따르는 datetime (freeze **안에서** 꽂고 freeze 안에서 되돌린다)
# ===========================================================================
def kst_naive_datetime_class():
    real = _dt_mod.datetime

    class _KstNaive(real):
        @classmethod
        def now(cls, tz=None):  # noqa: D401
            aware = _dt_mod.datetime.now(KST)      # freeze 중에는 FakeDatetime → 고정 KST
            if tz is None:
                return aware.replace(tzinfo=None)
            return aware.astimezone(tz)

    return _KstNaive


def kst(h: int, m: int = 0, s: int = 0, *, day: date = DAY) -> str:
    return datetime(day.year, day.month, day.day, h, m, s, tzinfo=KST).isoformat()
