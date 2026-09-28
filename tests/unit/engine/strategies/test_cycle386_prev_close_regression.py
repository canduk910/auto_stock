"""cycle386 Red (G8) — 잠정 봉 확정이 매매 판정을 실측값대로 되돌리는가.

명세 = `_workspace/domain_consult/cycle386_daily_close_after_market.md` §2-3 · §7 · §8-9 G8 · §8-12.

## 실측(09-28 · 09-15) — 정규장 종가 기준이면 조건을 넘지 못한 매수 3건
| 종목 | 전략 | 쓴 전일종가(가짜) | 정규장 종가 | 틱 | 가짜 기준 | 정규장 기준 |
|---|---|---:|---:|---:|---:|---:|
| 394800 쓰리빌리언 | momentum `buy_threshold=29` | 5,520 | **5,800** | 7,120→7,130 | 28.99→29.17% BUY | 22.76→22.93% NONE |
| 393210 | momentum | 3,715 | **4,060** | 4,790→4,825 | 28.94→29.88% BUY | 17.98→18.84% NONE |
| 441270 | LTV `min_prdy_rate=5` | 8,950 | **9,210** | 9,570 | 6.93% 통과 | 3.91% 차단 |
그리고 VB 목표가의 `prev_range` 는 가짜 고저(애프터 포함)로 부풀었다 — 323350 `1,660 → 1,050`.

## 이 파일이 재는 흐름 (실제 코드 경로)
가짜 DB(메모리 `stock_master_daily`) → `daily_bar_finalize.finalize_once`(실제) → `upsert_batch`(실제, `pg.executemany`
만 가짜) → VB/LTV `prepare`(실제, `get_recent_daily_normalized` 실제 — `get_recent_daily`·`max_bas_dd_before` 만 가짜 표를 읽는다)
→ `scanner.ticker_prev_close` → momentum/LTV `check_buy_signal`(실제).
`list_provisional_rows` 는 §8-3 조건의 파이썬 판본(SQL 자체는 `tests/integration/test_cycle386_provisional_predicate_pg.py`
가 실 Postgres 로 잰다). 나머지 합성값(4종목의 앞 봉·시가·일부 고저)은 합성이고, 표의 수치만 실측이다.

## HEAD 기준
`test_g8_0_*` 대조군은 HEAD 에서 **초록** — 결함 재현(가짜 봉 → BUY)이다. 나머지는 leaf 부재로 RED.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from freezegun import freeze_time

from src.engine.strategy_base import Signal, StrategyConfig

pytestmark = [pytest.mark.unit, pytest.mark.real_daily_bar_finalize]

KST = timezone(timedelta(hours=9))
T = date(2026, 9, 28)
P = date(2026, 9, 23)
NOW = datetime(2026, 9, 28, 7, 46, tzinfo=KST)
_PROV_TS = datetime(2026, 9, 23, 20, 30, 40, tzinfo=KST)
_COLS = ("ticker", "bas_dd", "open_price", "high_price", "low_price", "close_price", "volume",
         "trade_value", "change_rate", "flng_cls_code", "prtt_rate", "raw", "updated_at")

# (가짜 P 봉 O,H,L,C) · (확정 P 봉 O,H,L,C)
_SPEC = {
    "394800": ((5700, 6100, 5280, 5520), (5700, 6100, 5280, 5800)),
    "393210": ((3900, 4300, 3650, 3715), (3900, 4300, 3800, 4060)),
    "441270": ((9000, 9400, 8800, 8950), (9000, 9400, 8900, 9210)),
    "323350": ((9500, 10580, 8920, 10200), (9500, 9970, 8920, 9970)),
}


def _ymd(d: date) -> str:
    return d.strftime("%Y%m%d")


def _bar(d: date, o: int, h: int, l: int, c: int, v: int = 2_000_000) -> dict:
    return {
        "stck_bsop_date": _ymd(d), "stck_oprc": str(o), "stck_hgpr": str(h),
        "stck_lwpr": str(l), "stck_clpr": str(c), "acml_vol": str(v),
        "acml_tr_pbmn": str(v * c), "flng_cls_code": "00", "prtt_rate": "0.00",
        "prdy_vrss": "0", "prdy_vrss_sign": "3", "mod_yn": "N",
    }


def _ymd_any(v) -> str:
    """구현이 'YYYYMMDD' 문자열을 넘기든 date 를 넘기든 같은 뜻으로 읽는다."""
    if isinstance(v, (date, datetime)):
        return v.strftime("%Y%m%d")
    return str(v).replace("-", "")[:8]


def _trading_days_back(end: date, n: int) -> list[date]:
    out, d = [], end
    while len(out) < n:
        if d.weekday() < 5 and d not in (date(2026, 9, 24), date(2026, 9, 25)):
            out.append(d)
        d -= timedelta(days=1)
    return out


def _truth(ticker: str) -> list[dict]:
    """확정 봉 30개(내림차순). P 봉만 §2-3 실측값, 앞 봉은 합성."""
    _, (o, h, l, c) = _SPEC[ticker]
    days = _trading_days_back(P, 30)
    bars = [_bar(days[0], o, h, l, c)]
    for i, d in enumerate(days[1:], start=1):
        cc = int(o * 0.97) - i * 3
        bars.append(_bar(d, cc - 15, cc + 60, cc - 70, cc))
    return bars


class FakeDaily:
    """메모리 `stock_master_daily` — 쓰기는 실제 `_UPSERT_DAILY_SQL` 인자 배열을 그대로 받는다."""

    def __init__(self):
        self.rows: dict[tuple[str, date], dict] = {}

    def seed(self, ticker: str, bar: dict, updated_at: datetime) -> None:
        import src.db.stock_master_daily as smd

        row = smd._candle_to_row(ticker, bar)
        row["updated_at"] = updated_at
        self.rows[(ticker, row["bas_dd"])] = row

    async def executemany(self, sql: str, args_list) -> None:
        assert "stock_master_daily" in sql, f"예상 밖 쓰기 — {sql[:80]}"
        for a in args_list:
            row = dict(zip(_COLS, a))
            self.rows[(row["ticker"], row["bas_dd"])] = row

    async def get_recent_daily(self, ticker: str, days: int = 20) -> list[dict]:
        rs = sorted((r for (t, _), r in self.rows.items() if t == ticker),
                    key=lambda r: r["bas_dd"], reverse=True)
        return [dict(r) for r in rs[: max(1, days)]]

    async def max_bas_dd(self, ticker=None):
        ds = [d for (t, d) in self.rows if ticker is None or t == ticker]
        return max(ds) if ds else None

    async def max_bas_dd_before(self, today):
        """§8-3 헤드 SQL 파이썬 판본 — `bas_dd < today` 인 최댓값 (F1+F2)."""
        ds = [d for (_t, d) in self.rows if d < today]
        return max(ds) if ds else None

    async def list_provisional_rows(self, *, since, head, today_boundary):
        """§8-3 파이썬 판본 — 헤드는 오늘 06:00, 그 밖은 봉 다음 날 06:00 KST 전에 쓴 행."""
        out = []
        for (t, d), r in sorted(self.rows.items()):
            if d < since or d > head:
                continue
            if d == head:
                prov = r["updated_at"] < today_boundary
            else:
                prov = r["updated_at"] < datetime.combine(d + timedelta(days=1), time(6, 0), tzinfo=KST)
            if prov:
                out.append({k: r[k] for k in ("ticker", "bas_dd", "open_price", "high_price",
                                               "low_price", "close_price")})
        return out

    def close_of(self, ticker: str, d: date) -> int:
        return int(self.rows[(ticker, d)]["close_price"])


@pytest.fixture
def world(monkeypatch):
    import src.api.condition as cond
    import src.db.pg as pg
    import src.db.positions as pos
    import src.db.stock_master_daily as smd
    from src.engine import scanner

    db = FakeDaily()
    for t, (fake, _final) in _SPEC.items():
        truth = _truth(t)
        for b in truth[1:]:
            d = date(int(b["stck_bsop_date"][:4]), int(b["stck_bsop_date"][4:6]), int(b["stck_bsop_date"][6:]))
            db.seed(t, b, datetime.combine(d + timedelta(days=1), time(7, 56), tzinfo=KST))
        o, h, l, c = fake
        db.seed(t, _bar(P, o, h, l, c), _PROV_TS)

    kis_fallbacks: list[str] = []

    async def _fetch_ranged(ticker, start, end):
        s, e = _ymd_any(start), _ymd_any(end)
        bars = [dict(b) for b in _truth(ticker) if s <= b["stck_bsop_date"] <= e]
        return {"stck_prdy_clpr": str(_SPEC[ticker][1][3])}, bars

    async def _no_fallback(ticker, days=100, **_k):
        kis_fallbacks.append(ticker)
        raise AssertionError("prepare 가 DB 를 버리고 KIS 폴백으로 갔다 — 이 테스트는 DB 경로를 잰다")

    async def _pg_fetch(sql, *args):
        return []

    async def _pg_none(sql, *args):
        return None

    monkeypatch.setattr(smd, "get_recent_daily", db.get_recent_daily)
    monkeypatch.setattr(smd, "max_bas_dd", db.max_bas_dd)
    monkeypatch.setattr(smd, "max_bas_dd_before", db.max_bas_dd_before, raising=False)
    monkeypatch.setattr(smd, "list_provisional_rows", db.list_provisional_rows, raising=False)
    monkeypatch.setattr(smd, "now_kst_iso", lambda: "2026-09-28T07:46:30+09:00")
    monkeypatch.setattr(pg, "executemany", db.executemany)
    monkeypatch.setattr(pg, "fetch", _pg_fetch)
    monkeypatch.setattr(pg, "fetchrow", _pg_none)
    monkeypatch.setattr(pg, "fetchval", _pg_none)
    monkeypatch.setattr(pos, "load_all", AsyncMock(return_value=[]))
    monkeypatch.setattr(cond, "fetch_daily_chart_ranged_with_summary", _fetch_ranged, raising=False)
    monkeypatch.setattr(cond, "fetch_daily_candles", _no_fallback)
    monkeypatch.setattr(scanner, "ticker_prev_close", {})
    monkeypatch.setattr(scanner, "ticker_names", {t: t for t in _SPEC})
    db.kis_fallbacks = kis_fallbacks
    return db


async def _finalize():
    from src.engine import daily_bar_finalize

    await daily_bar_finalize.finalize_once(now_kst=NOW, phase="boot")


def _vb():
    from src.engine.strategies.volatility_breakout import VolatilityBreakoutStrategy

    return VolatilityBreakoutStrategy(StrategyConfig(
        strategy_id="volatility_breakout", name="변동성돌파", weight=0.2, enabled=True,
        params={"k_period": 20, "exchange": "KRX"},
    ))


def _ltv():
    from src.engine.strategies.long_tail_volatility import LongTailVolatilityStrategy

    return LongTailVolatilityStrategy(StrategyConfig(
        strategy_id="long_tail_volatility", name="롱테일", weight=0.2, enabled=True,
        params={"k_period": 20, "exchange": "KRX", "min_prdy_rate": 5.0},
    ))


async def _prepare(strategy, tickers: list[str]) -> None:
    strategy._scan_universe = AsyncMock(return_value=list(tickers))
    strategy._apply_master_block_filter_in_prepare = AsyncMock(return_value=(list(tickers), []))
    strategy._resolve_expected_daily_head = AsyncMock(return_value=P)
    await strategy.prepare()


def _momentum():
    from src.engine.strategies.momentum import MomentumStrategy

    return MomentumStrategy(StrategyConfig(strategy_id="momentum", name="모멘텀", weight=0.2))


def _momentum_signal(ticker: str, prime: int, cross: int) -> Signal:
    mo = _momentum()
    assert mo.config.params["buy_threshold"] == 29.0, "전제 — 운영 DB 와 같은 임계 29"
    with freeze_time("2026-09-28 00:03:52"):   # KST 09:03:52 (실측 매수 시각)
        assert mo.check_buy_signal(ticker, prime, prime) == Signal.NONE   # 첫 틱은 기록만
        return mo.check_buy_signal(ticker, cross, prime)


def _ltv_signal(ltv, ticker: str, monkeypatch) -> Signal:
    from src.engine.session import MarketBoard, session_tracker

    monkeypatch.setattr(session_tracker, "_active", frozenset({MarketBoard("main")}))
    info = ltv._targets[ticker]
    off = int(info["target_offset_base"] * ltv.config.params["k_value_krx_main"])
    open_p = 9560 - off                         # 목표가 = 9,560 → 9,550 아래, 9,570 위
    ltv.on_open_price_confirmed(ticker, open_p, board="main", source="rest")
    with freeze_time("2026-09-28 00:45:00"):   # KST 09:45 (09-15 실측 09:45:07)
        ltv.check_buy_signal(ticker, 9550, open_p)
        return ltv.check_buy_signal(ticker, 9570, open_p)


# ===========================================================================
# 대조군 — 결함 재현 (HEAD 초록): 가짜 봉 그대로 prepare → 조건을 넘는다
# ===========================================================================
@pytest.mark.asyncio
async def test_g8_0a_control_fake_head_bar_makes_momentum_buy(world):
    from src.engine import scanner

    await _prepare(_vb(), ["394800", "393210"])
    assert world.kis_fallbacks == []
    assert scanner.ticker_prev_close["394800"] == 5520, "전제 — 가짜 종가(19:59 애프터 체결가)가 전일종가가 된다"
    assert _momentum_signal("394800", 7120, 7130) == Signal.BUY, "결함 재현: +22.9% 지점을 +29% 돌파로 읽는다"
    assert scanner.ticker_prev_close["393210"] == 3715
    assert _momentum_signal("393210", 4790, 4825) == Signal.BUY


@pytest.mark.asyncio
async def test_g8_0b_control_fake_close_lets_ltv_pass_min_prdy_rate(world, monkeypatch):
    ltv = _ltv()
    await _prepare(ltv, ["441270"])
    from src.engine import scanner

    assert scanner.ticker_prev_close["441270"] == 8950
    assert _ltv_signal(ltv, "441270", monkeypatch) == Signal.BUY, "결함 재현: 3.91% 를 6.93% 로 읽어 통과시킨다"


@pytest.mark.asyncio
async def test_g8_0c_control_fake_high_inflates_vb_prev_range(world):
    vb = _vb()
    await _prepare(vb, ["323350"])
    assert vb._targets["323350"]["prev_range"] == 1660


# ===========================================================================
# 치료 — 부팅이 prepare 전에 확정한다 (HEAD RED)
# ===========================================================================
@pytest.mark.asyncio
async def test_g8_1_394800_after_finalize_momentum_does_not_buy(world):
    from src.engine import scanner

    await _finalize()
    await _prepare(_vb(), ["394800"])

    assert world.kis_fallbacks == []
    assert scanner.ticker_prev_close["394800"] == 5800, "확정 뒤 전일종가 = 정규장 종가 5,800"
    assert _momentum_signal("394800", 7120, 7130) == Signal.NONE, (
        "7,130 은 정규장 기준 +22.93% — momentum `buy_threshold=29` 를 넘지 않는다"
    )


@pytest.mark.asyncio
async def test_g8_2_393210_after_finalize_momentum_does_not_buy(world):
    from src.engine import scanner

    await _finalize()
    await _prepare(_vb(), ["393210"])

    assert scanner.ticker_prev_close["393210"] == 4060
    assert _momentum_signal("393210", 4790, 4825) == Signal.NONE, "4,825 는 정규장 기준 +18.84%"


@pytest.mark.asyncio
async def test_g8_3_441270_after_finalize_ltv_is_blocked_by_min_prdy_rate(world, monkeypatch):
    from src.engine import scanner

    await _finalize()
    ltv = _ltv()
    await _prepare(ltv, ["441270"])

    assert scanner.ticker_prev_close["441270"] == 9210
    assert _ltv_signal(ltv, "441270", monkeypatch) == Signal.NONE, "9,570 은 정규장 기준 +3.91% < 5%"


@pytest.mark.asyncio
async def test_g8_4_323350_after_finalize_vb_prev_range_is_regular_session(world):
    await _finalize()
    vb = _vb()
    await _prepare(vb, ["323350"])

    assert vb._targets["323350"]["prev_range"] == 1050, "정규장 고저(9,970 − 8,920) — 애프터 고가 10,580 이 빠져야 한다"


@pytest.mark.asyncio
async def test_g8_5_db_is_final_and_a_same_day_restart_has_nothing_to_do(world, caplog):
    """확정 뒤 DB 의 P 봉은 정규장 값이고, 같은 날 재기동의 대상은 0 이다(§8-3 사례표 마지막 줄)."""
    import logging

    await _finalize()
    for t, (_fake, final) in _SPEC.items():
        assert world.close_of(t, P) == final[3], f"{t} P 봉 종가가 확정값이 아니다"
    left = await world.list_provisional_rows(
        since=T - timedelta(days=21), head=P,
        today_boundary=datetime.combine(T, time(6, 0), tzinfo=KST),
    )
    assert left == [], f"확정 뒤에도 잠정 행이 남았다 — {left}"

    caplog.clear()
    caplog.set_level(logging.INFO)
    await _finalize()
    lines = [r.getMessage() for r in caplog.records if r.getMessage().startswith("[daily_bar_finalize] ")]
    assert len(lines) == 1 and "result=noop" in lines[0], f"같은 날 재기동이 다시 받는다 — {lines}"
