"""cycle364 (S1 — A1 `prepare(as_of=)`) 전략 prepare 구동 하네스 — 테스트 모듈이 아니다.

`test_cycle364_prepare_as_of.py` · `test_cycle364_preview_held_guard.py` 가 공유한다.
골든(`fixtures/cycle364_prepare_golden.json`)은 **변경 전 코드**(HEAD 3cf032a, 2026-09-26)
에서 이 하네스로 한 번 떠 둔 것이다 — `prepare()` 인자 없음 경로가 A1 이후에도 바이트
동일하다는 계약(A1-1)의 기준이다. 골든을 다시 뜨는 것은 「행위가 바뀌었다」는 뜻이므로
사유 없이 재생성하지 않는다.

외부 의존 격리 (벽시계·DB·KIS 0):
- 시각 = freezegun (호출자가 감싼다) · 휴장일 = conftest 전역 중립화(None) 또는 호출자 패치
- 유니버스 = `_scan_universe` / 마스터 차단 = 항등 패치
- 일봉 = `get_recent_daily_normalized` 를 종목별 합성 봉으로 (호출 kwargs 는 반환 mock 에 남는다)
- VB 퀀트·RS/RSI 훅, VCP DB ATR, kojiro 섹터 조회 = DB 읽기 패치(빈 값)
- 모듈 전역 `scanner.ticker_prev_close` · `scanner.ticker_names` = 테스트마다 새 dict
  (다른 테스트가 채운 이름·전일종가가 골든에 새지 않게)
- 보호 종목(보유 ∪ 익일청산) = `scanner._collect_protected_tickers_for_scanner` 를 호출자가
  준 집합으로 — 운영에서 그 헬퍼가 돌려주는 값과 같은 모양이다
"""

from __future__ import annotations

import copy
import json
from contextlib import ExitStack
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

from src.engine.strategies.bull_flag_breakout import BullFlagBreakoutStrategy
from src.engine.strategies.donchian_swing import DonchianSwingStrategy
from src.engine.strategies.kojiro import KojiroStrategy
from src.engine.strategies.long_tail_volatility import LongTailVolatilityStrategy
from src.engine.strategies.vcp_breakout import VcpBreakoutStrategy
from src.engine.strategies.volatility_breakout import VolatilityBreakoutStrategy
from src.engine.strategy_base import Position, StrategyConfig

KST = timezone(timedelta(hours=9))

GOLDEN_PATH = Path(__file__).resolve().parent / "fixtures" / "cycle364_prepare_golden.json"

STRATEGIES = {
    "volatility_breakout": VolatilityBreakoutStrategy,
    "long_tail_volatility": LongTailVolatilityStrategy,
    "donchian_swing": DonchianSwingStrategy,
    "bull_flag_breakout": BullFlagBreakoutStrategy,
    "vcp_breakout": VcpBreakoutStrategy,
    "kojiro": KojiroStrategy,
}
SIDS = tuple(STRATEGIES)

# 합성 종목코드 — 실종목·정적 이름표(`STATIC_TICKER_NAMES`)와 겹치지 않는다.
T_UP = "990101"        # 완만한 상승 + 거래량 기하 증가 (donchian 전 단계 통과)
T_DOWN = "990102"      # 하락
T_ZERO = "990103"      # 머리 봉 고가=저가 (VB/LTV prev_range 0)
T_SHORT = "990104"     # 10봉 (길이 부족)
T_NONE = "990105"      # 어댑터 None (fetch 실패)
T_WIDE = "990106"      # 넓은 변동폭 상승 (kojiro ATR 밴드 통과) — 보유 시나리오의 보유 종목
HELD = T_WIDE

_NO_ARG = object()


def make_strategy(sid: str):
    return STRATEGIES[sid](StrategyConfig(strategy_id=sid, name=sid, params={}, enabled=True))


def weekdays_desc(head: date, n: int) -> list[date]:
    """`head` 부터 거꾸로 평일 n 개 (DESC). 휴장일은 모른다 — 합성 봉이라 무관."""
    out: list[date] = []
    d = head
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d -= timedelta(days=1)
    return out


def _bar(d: date, o: int, h: int, lo: int, c: int, v: int) -> dict:
    return {
        "stck_bsop_date": d.strftime("%Y%m%d"),
        "stck_oprc": str(o),
        "stck_hgpr": str(h),
        "stck_lwpr": str(lo),
        "stck_clpr": str(c),
        "acml_vol": str(v),
        "acml_tr_pbmn": str(c * v),
        "prdy_ctrt": "0.50",
    }


def trend_series(
    head: date, n: int, *, base: int, step: int, hi: int, lo: int,
    vol0: int = 100_000, growth: float = 1.08,
) -> list[dict]:
    """DESC(최신 먼저) 합성 일봉. 오래된 봉부터 종가가 `step` 씩 움직이고 거래량이 기하 증가."""
    dates = list(reversed(weekdays_desc(head, n)))  # ASC
    rows = []
    for k, d in enumerate(dates):
        close = base + step * k
        rows.append(_bar(d, close - 20, close + hi, close - lo, close, int(vol0 * (growth ** k))))
    return list(reversed(rows))


def universe(head: date) -> dict[str, list[dict] | None]:
    """골든·A1 시나리오 공용 종목 묶음 (결정론)."""
    zero = trend_series(head, 110, base=20_000, step=40, hi=30, lo=60)
    zero[0] = dict(zero[0])
    c = zero[0]["stck_clpr"]
    zero[0].update({"stck_oprc": c, "stck_hgpr": c, "stck_lwpr": c})
    return {
        T_UP: trend_series(head, 110, base=10_000, step=50, hi=30, lo=60),
        T_DOWN: trend_series(head, 110, base=40_000, step=-60, hi=40, lo=50, growth=1.0),
        T_ZERO: zero,
        T_SHORT: trend_series(head, 10, base=30_000, step=10, hi=20, lo=20),
        T_NONE: None,
        T_WIDE: trend_series(head, 110, base=50_003, step=45, hi=500, lo=520, growth=1.03),
    }


def close_to_date(candles: list[dict]) -> dict[int, str]:
    """종가 → 봉 날짜. 합성 봉은 종가가 봉마다·종목마다 유일하다(기준가·보폭을 서로 소로 골랐다 —
    T_UP 10,000+50k · T_ZERO 20,000+40k · T_SHORT 30,000+10k · T_DOWN 40,000−60k · T_WIDE 50,003+45k)."""
    return {int(c["stck_clpr"]): c["stck_bsop_date"] for c in candles}


def seed_held(strategy, *, as_of_day: date) -> dict:
    """보유 시나리오 공통 사전 상태 — 아침 recompute 가 만든 것과 같은 모양.

    반환 = 호출자가 identity 를 확인할 원본 객체들.
    """
    sid = strategy.strategy_id
    strategy.state.positions[HELD] = Position(
        ticker=HELD, buy_price=52_000, quantity=10, order_no="O-364",
        strategy_id=sid, buy_date=date(2026, 9, 15), high_since_buy=55_000,
    )
    seeded: dict = {}
    if sid == "donchian_swing":
        entry = {"prev_close": 54_800, "atr": 900, "ema60": 0, "donchian_high": 0}
        strategy._candidates[HELD] = entry
        seeded["candidate"] = entry
    elif sid == "kojiro":
        entry = {
            "prev_close": 54_800, "atr": 1_000.0, "stage": 2, "ema_s": 54_700.0,
            "ema_m": 54_750.0, "ema_l": 54_500.0, "atr_ratio": 1_000.0 / 54_800, "name": "",
        }
        strategy._candidates[HELD] = entry
        stamp = (as_of_day, False)
        strategy._held_stage3[HELD] = stamp
        seeded["candidate"] = entry
        seeded["stage3"] = stamp
    return seeded


def run_prepare_patches(stack: ExitStack, strategy, cands: dict, *, protected=()):
    """prepare 1회 구동에 필요한 패치를 `stack` 에 건다. 반환 = 어댑터 mock."""
    import src.engine.scanner as scanner_mod

    tickers = list(cands)

    async def _adapter(ticker, *args, **kwargs):
        rows = cands.get(ticker)
        return copy.deepcopy(rows) if rows is not None else None

    adapter = AsyncMock(side_effect=_adapter)
    stack.enter_context(patch.object(strategy, "_scan_universe", new=AsyncMock(return_value=tickers)))
    stack.enter_context(patch.object(
        strategy, "_apply_master_block_filter_in_prepare",
        new=AsyncMock(side_effect=lambda t: (list(t), [])),
    ))
    stack.enter_context(patch("src.db.stock_master_daily.get_recent_daily_normalized", new=adapter))
    stack.enter_context(patch("src.db.stock_master_daily.get_recent_daily", new=AsyncMock(return_value=[])))
    stack.enter_context(patch("src.db.stock_master_daily.get_atr", new=AsyncMock(return_value=None)))
    stack.enter_context(patch(
        "src.db.stock_master_financial.get_financial_series", new=AsyncMock(return_value=[]),
    ))
    stack.enter_context(patch("src.db.stock_master.get", new=AsyncMock(return_value=None)))
    stack.enter_context(patch("src.db.stock_master.get_master_raw", new=AsyncMock(return_value=None)))
    stack.enter_context(patch("src.db.system_logs.write_log", new=AsyncMock(return_value=None)))
    stack.enter_context(patch("asyncio.sleep", new=AsyncMock(return_value=None)))
    stack.enter_context(patch.object(scanner_mod, "ticker_prev_close", {}))
    stack.enter_context(patch.object(scanner_mod, "ticker_names", {}))
    prot = set(protected)
    stack.enter_context(patch.object(
        scanner_mod, "_collect_protected_tickers_for_scanner", new=lambda: set(prot),
    ))
    return adapter


async def run_prepare(strategy, cands: dict, *, as_of=_NO_ARG, protected=(), extra=None):
    """prepare 1회. 반환 = (어댑터 mock, prepare 직후 `scanner.ticker_prev_close` 사본)."""
    import src.engine.scanner as scanner_mod

    with ExitStack() as stack:
        adapter = run_prepare_patches(stack, strategy, cands, protected=protected)
        if extra is not None:
            extra(stack)
        if as_of is _NO_ARG:
            await strategy.prepare()
        else:
            await strategy.prepare(as_of=as_of)
        prev_close = dict(scanner_mod.ticker_prev_close)
    return adapter, prev_close


# ──────────────────────────── 정규화 스냅샷 ────────────────────────────

_STATE_ATTRS = (
    "_targets", "_open_confirmed", "_prev_price", "_failed_breakout_count",
    "_candidates", "_bought_today", "_held_stage3", "_breakout_watch",
    "_breakout_summary_last", "_trading_days", "_universe_candidate_tickers",
    "_scan_stage_counts",
)


_EXACT = [False]


def canon(obj):
    """JSON 직렬화 가능한 결정론 형태로. set → 정렬 리스트, date → iso, numpy → 파이썬."""
    if isinstance(obj, dict):
        return {str(k): canon(v) for k, v in sorted(obj.items(), key=lambda kv: str(kv[0]))}
    if isinstance(obj, (list, tuple)):
        return [canon(v) for v in obj]
    if isinstance(obj, (set, frozenset)):
        items = [canon(v) for v in obj]
        return sorted(items, key=lambda x: json.dumps(x, sort_keys=True, ensure_ascii=False))
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if obj is None or isinstance(obj, (bool, str)):
        return obj
    if isinstance(obj, int):
        return int(obj)
    if isinstance(obj, float):
        # 골든은 로컬(macOS·3.13)에서 뜨고 CI(Linux·3.12)가 대조한다 — pandas/numpy 부동소수
        # 끝자리(ULP) 차이로 붉어지지 않게 소수 6자리로 자른다. 같은 프로세스 안의 두 경로
        # 대조(`prepare()` vs `prepare(as_of=오늘)`)는 `canon(..., exact=True)` 로 자르지 않는다.
        return float(obj) if _EXACT[0] else round(float(obj), 6)
    item = getattr(obj, "item", None)
    if callable(item):
        return canon(item())
    return repr(obj)


def snapshot(strategy, prev_close: dict, tickers, *, exact: bool = False) -> dict:
    snap: dict = {
        "funnel_steps": strategy._funnel_steps,
        "scanned": list(strategy.get_scanned_tickers()),
        "scan_stats": strategy._scan_stats,
        "ticker_prev_close": {t: prev_close.get(t) for t in tickers},
    }
    for attr in _STATE_ATTRS:
        if hasattr(strategy, attr):
            snap[attr] = getattr(strategy, attr)
    _EXACT[0] = exact
    try:
        return canon(snap)
    finally:
        _EXACT[0] = False


def dumps(snap: dict) -> str:
    return json.dumps(snap, sort_keys=True, ensure_ascii=False)


SCENARIOS = {
    # 부팅 아침 — DB 헤드 = 전 영업일, 오늘 봉 없음 (prev_idx 0)
    "boot_morning": {"now": "2026-09-22T07:50:00+09:00", "head": date(2026, 9, 21), "held": False},
    # 장중 재준비 — 오늘 부분봉이 머리 (prev_idx 1)
    "intraday_today_bar": {"now": "2026-09-22T10:00:00+09:00", "head": date(2026, 9, 22), "held": False},
    # 저녁 비미리보기(as_of=오늘) — 보유가 있고 오늘 봉이 완성봉으로 머리 (현행 재표시 경로)
    "evening_held_today": {"now": "2026-09-22T21:00:00+09:00", "head": date(2026, 9, 22), "held": True},
}


async def scenario_snapshot(sid: str, scenario: str, *, as_of=_NO_ARG, exact: bool = False) -> dict:
    """freezegun 은 호출자가 건다(`SCENARIOS[scenario]["now"]`)."""
    spec = SCENARIOS[scenario]
    strategy = make_strategy(sid)
    held = ()
    if spec["held"]:
        seed_held(strategy, as_of_day=date(2026, 9, 22))
        held = (HELD,)
    cands = universe(spec["head"])
    _, prev_close = await run_prepare(strategy, cands, as_of=as_of, protected=held)
    return snapshot(strategy, prev_close, list(cands), exact=exact)
