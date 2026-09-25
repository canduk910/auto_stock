"""cycle351 Red — 셰도 어댑터 `build_pyramid_shadow` + 콜렉터 끝 키 `"pyramid_shadow"`.

명세(정본) = `_workspace/red/cycle351_pyramid_shadow_spec.md` §2(어댑터·콜렉터) · §4-1(골든) · §4-3(A1~A12).

## 골든 — 매매·기존 집계 무변경의 증거 (§4-1)

`tests/fixtures/cycle351/collector_golden_head.json` 은 **확장 전 코드**(HEAD `0a7752a`)로
`_golden_collect()`(이 모듈)를 한 번 돌려 얻은 기존 10키다. 생성 방법:

    # base sha 0a7752a 워킹트리(프로덕션 무변경)에서
    python <scratchpad>/gen_cycle351_golden.py
    #  = tests.conftest 를 import(환경 기본값) → MonkeyPatch 한 벌로 `_golden_collect(mp)` 를
    #    asyncio.run → "pyramid_shadow" 를 뺀 dict 를
    #    {"base_sha", "generated_by", "target_date", "frozen_utc", "metrics"} 로 감싸
    #    json.dumps(ensure_ascii=False, indent=2) 로 쓴다.

스크립트는 세션 스크래치패드(커밋 안 됨)에 있었다 — 위 세 줄이 그 전부라 다시 만들 수 있다.
골든을 다시 뽑아야 하는 경우는 **기존 10키 계약이 정당하게 바뀐 사이클뿐**이고, 그때는 그 사이클의
base sha 로 이 docstring 을 고친다. Green 뒤에는 같은 입력의 결과에서 `pyramid_shadow` 를 뺀
10키가 골든과 **완전히 같아야** 하고(`test_golden_*`), 셰도는 같은 입력에서 실제로 돌아야 한다
(골든 입력에 kojiro·donchian 페어와 일봉을 넣어 둔 이유 — 셰도가 다른 키를 건드리면 여기서 붉다).

## 격리

- DB 는 `src.db.trade_history.get_trade_pairs` · `src.db.stock_master_daily.get_recent_daily` 를
  **정의 모듈 속성**으로 갈아 끼운다(leaf 는 함수 안 지연 import 라 호출 시점에 이 속성을 읽는다).
- 시계 = freezegun(UTC 로 넣는다). ⚠️ 시간 상한 테스트(A10)는 freezegun 을 쓰지 않는다 —
  동결된 monotonic 이 asyncio 타이머를 멈춘다.
- 모듈 전역 `KstDailyEmitCap`(leaf 의 `[pyramid_shadow_close]` · 콜렉터의 `[vcp_breakout_events]`)은
  autouse 픽스처가 테스트마다 새 인스턴스로 바꾼다(타입으로 찾는다 — cycle349 F2 선례).
"""
from __future__ import annotations

import asyncio
import json
import logging
import math
import re
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from freezegun import freeze_time

import src.engine.log_metrics_collector as collector

pytestmark = pytest.mark.unit

KST = timezone(timedelta(hours=9))
ROOT = Path(__file__).resolve().parents[3]
GOLDEN_PATH = ROOT / "tests" / "fixtures" / "cycle351" / "collector_golden_head.json"
GOLDEN_BASE_SHA = "0a7752a"

#: 확장 전 10키(cycle249 C-1 · cycle259 L3 · cycle349 가 잠근 순서).
HEAD_METRIC_KEYS = [
    "target_date", "logs", "trades", "api_metrics", "strategy_funnel",
    "strategy_funnel_stages", "next_day_clear", "portfolio_risk_snapshot", "tick_blind",
    "vcp_breakout_events",
]
EXPECTED_METRIC_KEYS = HEAD_METRIC_KEYS + ["pyramid_shadow", "report_accuracy"]

#: §2-3 레코드 키 순서(고정).
RECORD_KEYS = [
    "strategy", "ticker", "buy_date", "entry_price", "n_entry", "r_unit", "status",
    "exit_date", "exit_price", "exit_time", "bars_through", "final", "actual_R", "virtual_R",
    "delta_R", "tranches", "add_dates", "add_prices", "set_stop", "fixed_stop", "v_exit_date",
    "v_exit_kind", "killed", "tranche_shares", "eligible", "add_stage", "add_macd",
    "params_source", "error",
]
#: §2-4 반환·요약 키 순서.
RESULT_KEYS = ["version", "target_date", "ladder", "summary", "records", "_note"]
#: minor — 21:30 LLM 프롬프트가 이 metrics 키를 실매매로 오독하지 않게 하는 설명.
SHADOW_NOTE = "가상 기록(피라미딩 셰도) — 실매매 아님. 매매 행위에 영향 없음."
SUMMARY_KEYS = [
    "open_n", "closed_n", "closed_final_n", "closed_nonfinal_n", "killed_n", "eligible_n",
    "delta_R_mean_closed_final", "extra_notional_won", "gap_stress_won", "errors_n", "truncated",
]
#: §2-5 마커 필드 순서.
MARKER = "[pyramid_shadow_close]"
MARKER_FIELDS = [
    "strategy", "ticker", "buy_date", "exit_date", "v_exit_kind", "actual_R", "virtual_R",
    "delta_R", "tranches", "add_dates", "set_stop", "fixed_stop", "killed", "tranche_shares",
    "eligible", "add_stage", "add_macd",
]

TWO_THIRDS = 2.0 / 3.0

# ---------------------------------------------------------------------------
# 달력 — T = 2026-10-19(월). D0 = 10-12(월) … D4 = 10-16(금) · D5 = T.
# 추가가 일어나는 D1·D2 가 금요일이 아니게 골랐다(어댑터가 날짜로 `no_add_flags` 를 만든다).
# ---------------------------------------------------------------------------
T = date(2026, 10, 19)
D = [date(2026, 10, 12) + timedelta(days=i) for i in range(5)] + [T]   # D0..D5
T_PREV = D[4]                                                             # 10-16(금)


def _utc_of(kst: datetime) -> str:
    return (kst - timedelta(hours=9)).strftime("%Y-%m-%d %H:%M:%S")


FROZEN_T_2130_UTC = _utc_of(datetime(2026, 10, 19, 21, 30))


def _prior_bdays(before: date, n: int) -> list[date]:
    out: list[date] = []
    d = before - timedelta(days=1)
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d -= timedelta(days=1)
    return sorted(out)


def _row(ticker: str, d: date, o, h, lo, c) -> dict:
    return {
        "ticker": ticker, "bas_dd": d,
        "open_price": o, "high_price": h, "low_price": lo, "close_price": c,
        "volume": 100_000, "trade_value": 0, "change_rate": 0.0, "raw": {},
    }


#: 매수일 이후 봉 — 코어 C1 과 같은 경로(D1 10,500 · D2 11,000 추가, D4 본전 승격, D5 종가 11,700).
C1_POST = [
    (10_000, 10_100, 9_900, 10_000),
    (10_100, 10_500, 10_050, 10_400),
    (10_450, 11_000, 10_400, 10_900),
    (10_950, 11_500, 10_900, 11_400),
    (11_400, 11_600, 11_300, 11_500),
    (11_500, 11_800, 11_400, 11_700),
]
#: kojiro 매수일 봉은 변동폭 3,000(TR 3,000) — 진입 N 에 넣으면 Wilder 가 500 → 625 로 뛴다(M10).
KOJIRO_POST = [
    (10_000, 11_500, 8_500, 10_000),
    (10_000, 10_200, 9_900, 10_100),
    (10_100, 10_300, 10_000, 10_200),
    (10_200, 10_400, 10_100, 10_300),
    (10_300, 10_450, 10_200, 10_350),
    (10_350, 10_480, 10_300, 10_400),
]


def _series(ticker: str, prior_ranges: list[int], post, *, rising: bool = True,
            post_dates: list[date] | None = None) -> list[dict]:
    """매수일(D0) 앞 봉 + D0.. 봉. 앞 봉은 종가 중심 ±range/2, 전일 종가가 늘 [저가,고가] 안이라
    TR = 고가 − 저가 그대로다(손계산이 쉽다). `rising` 이면 종가를 봉당 +20 씩 올려 EMA 가 갈라지게 한다."""
    post_dates = post_dates or D[: len(post)]
    prior_dates = _prior_bdays(post_dates[0], len(prior_ranges))
    rows: list[dict] = []
    n = len(prior_ranges)
    for i, (d, r) in enumerate(zip(prior_dates, prior_ranges)):
        c = 10_000 - 20 * (n - i) if rising else 10_000
        hi = c + (r + 1) // 2
        lo = hi - r
        rows.append(_row(ticker, d, c, hi, lo, c))
    for d, (o, h, lo, c) in zip(post_dates, post):
        rows.append(_row(ticker, d, o, h, lo, c))
    return rows


def _pair(strategy: str, ticker: str, buy_date: date, buy_price: float, *, status: str = "open",
          sell_date: date | None = None, sell_price: float | None = None,
          sell_time: str | None = None) -> dict:
    return {
        "buy_date": buy_date.isoformat(), "buy_time": "09:10:00",
        "sell_date": sell_date.isoformat() if sell_date else None,
        "sell_time": sell_time,
        "ticker": ticker, "ticker_name": f"T{ticker}",
        "buy_price": float(buy_price), "buy_qty": 3,
        "sell_price": float(sell_price) if sell_price is not None else None,
        "sell_qty": 3 if status == "closed" else None,
        "profit_loss": None, "profit_rate": None, "status": status, "strategy": strategy,
        "buy_order_nos": [f"B{ticker}"], "sell_order_nos": [f"S{ticker}"] if status == "closed" else [],
        "pair_key": f"{strategy}:{ticker}:B{ticker}",
    }


class _FakeDB:
    """`get_trade_pairs` · `get_recent_daily` 대역. 정의 모듈 속성을 갈아 끼운다."""

    def __init__(self, pairs: list[dict], daily: dict[str, list[dict]], *,
                 raise_pairs: bool = False, raise_daily_for: set[str] | None = None):
        self.pairs = pairs
        self.daily = daily
        self.raise_pairs = raise_pairs
        self.raise_daily_for = raise_daily_for or set()
        self.pair_calls: list = []
        self.daily_calls: list = []

    async def get_trade_pairs(self, strategy=None, ticker=None):
        self.pair_calls.append(strategy)
        if self.raise_pairs:
            raise RuntimeError("get_trade_pairs boom (cycle351 test)")
        return [dict(p) for p in self.pairs
                if (strategy is None or p["strategy"] == strategy)
                and (ticker is None or p["ticker"] == ticker)]

    async def get_recent_daily(self, ticker, days=20):
        self.daily_calls.append((ticker, days))
        if ticker in self.raise_daily_for:
            raise RuntimeError(f"daily boom {ticker} (cycle351 test)")
        rows = sorted(self.daily.get(ticker, []), key=lambda r: r["bas_dd"], reverse=True)
        return [dict(r) for r in rows[: max(1, min(int(days), 400))]]

    def install(self, mp) -> "_FakeDB":
        mp.setattr("src.db.trade_history.get_trade_pairs", self.get_trade_pairs)
        mp.setattr("src.db.stock_master_daily.get_recent_daily", self.get_recent_daily)
        return self


def _ps():
    try:
        from src.engine import pyramid_shadow  # noqa: PLC0415 — Red 경로 보존
    except ImportError as exc:  # pragma: no cover - Red 경로
        pytest.fail(
            "Red — `src/engine/pyramid_shadow.py` 미구현 (cycle351 §2). "
            f"`async build_pyramid_shadow(target_date, *, params_by_sid, budget_by_sid, now_kst=None)` 필요: {exc}"
        )
    return pyramid_shadow


async def _build(target_date: date, *, params_by_sid=None, budget_by_sid=None, held_by_sid=None) -> dict:
    ps = _ps()
    out = await ps.build_pyramid_shadow(
        target_date,
        params_by_sid={} if params_by_sid is None else params_by_sid,
        budget_by_sid={} if budget_by_sid is None else budget_by_sid,
        held_by_sid=held_by_sid,
    )
    assert isinstance(out, dict), type(out)
    return out


def _rec(result: dict, strategy: str, ticker: str) -> dict:
    found = [r for r in result["records"] if r["strategy"] == strategy and r["ticker"] == ticker]
    assert len(found) == 1, (strategy, ticker, [(r["strategy"], r["ticker"]) for r in result["records"]])
    return found[0]


def _approx(x):
    return pytest.approx(x, abs=1e-4)


def _marker_lines(caplog) -> list[str]:
    return [r.getMessage() for r in caplog.records
            if r.levelno >= logging.WARNING and r.getMessage().startswith(MARKER + " ")]


def _field(msg: str, key: str) -> str | None:
    m = re.search(rf"(?:^|\s){re.escape(key)}=(\S+)", msg)
    return m.group(1) if m else None


def _walk_numbers(obj):
    if isinstance(obj, bool):
        return
    if isinstance(obj, (int, float)):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from _walk_numbers(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            yield from _walk_numbers(v)


# ---------------------------------------------------------------------------
# 표준 시나리오
# ---------------------------------------------------------------------------
PRIOR_500 = [500] * 30


def _donchian_open_901() -> tuple[dict, list[dict]]:
    """donchian 보유 900201 — N = SMA14(500) = 500 · r_unit 1,000 · 코어 C1 경로(앵커 없음)."""
    return (_pair("donchian_swing", "900201", D[0], 10_000),
            _series("900201", PRIOR_500, C1_POST))


def _donchian_closed_902(sell_time: str = "10:30:00") -> tuple[dict, list[dict]]:
    """donchian 청산 900202 — T 에 11,700 청산(앵커). 봉은 900201 과 같다."""
    return (_pair("donchian_swing", "900202", D[0], 10_000, status="closed",
                  sell_date=T, sell_price=11_700, sell_time=sell_time),
            _series("900202", PRIOR_500, C1_POST))


def _kojiro_open_101(prior: list[int] | None = None) -> tuple[dict, list[dict]]:
    """kojiro 보유 900101 — 앞 봉 TR 전부 500 → Wilder 500 · 매수일 TR 3,000(넣으면 625)."""
    return (_pair("kojiro", "900101", D[0], 10_000),
            _series("900101", prior or [500] * 120, KOJIRO_POST))


# ---------------------------------------------------------------------------
# 픽스처
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _fresh_caps(monkeypatch):
    """leaf·콜렉터의 모듈 전역 `KstDailyEmitCap` 을 테스트마다 새 인스턴스로(타입으로 찾는다)."""
    from src.engine.daily_emit_cap import KstDailyEmitCap

    for n, v in list(vars(collector).items()):
        if isinstance(v, KstDailyEmitCap):
            monkeypatch.setattr(collector, n, KstDailyEmitCap())
    try:
        from src.engine import pyramid_shadow as ps  # noqa: PLC0415
    except ImportError:
        return  # Red — 각 테스트가 `_ps()` 에서 실패한다
    names = [n for n, v in vars(ps).items() if isinstance(v, KstDailyEmitCap)]
    assert names, "pyramid_shadow 모듈 전역에 KstDailyEmitCap 이 없다 — §2-5 cap 소실"
    for n in names:
        monkeypatch.setattr(ps, n, KstDailyEmitCap())
    ps.reset_finalized_pairs_for_test()  # 늦은 확정 dedup(§2-1 확장) 테스트 격리


class _FakeStrat:
    def __init__(self, sid: str, params: dict | None = None, total_investment=0, summary=None,
                 held_tickers=()):
        self.strategy_id = sid
        self.config = SimpleNamespace(params=dict(params or {}), enabled=True, weight=0.2)
        self.state = SimpleNamespace(
            total_investment=total_investment,
            positions={t: {"buy_price": 0.0} for t in held_tickers},
            pending_buys=set(), pending_buy_amounts={},
        )
        self._summary = summary

    def breakout_event_summary(self, target_date):
        if self._summary is not None:
            return dict(self._summary)
        return {"status": "no_watch", "date": target_date.isoformat()}


def _install_registry(monkeypatch, strategies: list) -> SimpleNamespace:
    from src.engine import scheduler as sched_mod

    by_id = {s.strategy_id: s for s in strategies}
    reg = SimpleNamespace(get=lambda sid: by_id.get(sid), all=lambda: list(strategies))
    monkeypatch.setattr(sched_mod, "trading_scheduler", SimpleNamespace(registry=reg))
    return reg


KOJIRO_REG_PARAMS = {"stop_atr": 2.0, "hard_stop_pct": -8.0, "breakeven_promote_atr": 1.5,
                     "atr_period": 20, "risk_pct": 0.005, "max_positions": 6}
DONCHIAN_REG_PARAMS = {"stop_atr": 2.0, "turtle_backstop_pct": -9.0, "breakeven_promote_atr": 1.5,
                       "atr_period": 14, "risk_pct": 0.01, "max_positions": 5}


# ===========================================================================
# 골든 입력 — 이 함수가 골든 JSON 의 **유일한** 입력 정의다(생성 스크립트도 이것을 부른다).
# ===========================================================================
GOLDEN_LOGS = [
    {"timestamp": "2026-10-19T07:45:03.000000+09:00", "log_level": "INFO",
     "message": "[tick_blind_boot] downtime_secs=120 market_blind_secs=30 last_alive=2026-10-19T07:43"},
    {"timestamp": "2026-10-19T08:00:31.000000+09:00", "log_level": "WARNING",
     "message": "[next_day_clear_deferred] ticker=005930 strategy=kojiro reason=nxt_underthreshold"},
    {"timestamp": "2026-10-19T09:00:06.000000+09:00", "log_level": "INFO",
     "message": "[next_day_clear_drained] ticker=005930 strategy=kojiro result=success elapsed_ms=120"},
    {"timestamp": "2026-10-19T09:31:00.000000+09:00", "log_level": "WARNING",
     "message": "[budget_clamp] ticker=000660 qty 12 -> 3 remaining=450000"},
    {"timestamp": "2026-10-19T10:15:00.000000+09:00", "log_level": "ERROR",
     "message": "[buy_post_send_error] ticker=035420 order_no=0000123456 strategy=kojiro path=market qty=3 price=150000"},
    {"timestamp": "2026-10-19T14:00:00.000000+09:00", "log_level": "INFO",
     "message": "평범한 INFO 12345"},
]
GOLDEN_HIGH = [
    GOLDEN_LOGS[4],
    {"timestamp": "2026-10-19T16:30:00.000000+09:00", "log_level": "CRITICAL",
     "message": "[after_exit_giveup] ticker=035420 fails=5 next_day_clear=1"},
]
GOLDEN_TRADES = [
    {"strategy": "kojiro", "trade_type": "BUY", "status": "COMPLETED", "ticker": "035420",
     "timestamp": "2026-10-19T09:10:00+09:00", "profit_loss": None},
    {"strategy": "donchian_swing", "trade_type": "SELL", "status": "COMPLETED", "ticker": "000660",
     "timestamp": "2026-10-19T10:30:00+09:00", "profit_loss": 12345.0},
    {"strategy": "momentum", "trade_type": "SELL", "status": "COMPLETED", "ticker": "005930",
     "timestamp": "2026-10-19T09:00:30+09:00", "profit_loss": -4321},
    {"strategy": "kojiro", "trade_type": "BUY", "status": "PENDING", "ticker": "000270",
     "timestamp": "2026-10-19T09:20:00+09:00"},
    {"strategy": "vcp_breakout", "trade_type": "BUY", "status": "CANCELLED", "ticker": "068270",
     "timestamp": "2026-10-19T11:00:00+09:00"},
]
GOLDEN_VCP_SUMMARY = {
    "status": "ok", "date": "2026-10-19", "run_at": "07:45:00", "window": "09:05-14:30",
    "partial": False, "candidates": 3, "observed": 2, "crossed": 1,
    "crossed_tickers": ["900002"], "unobserved_tickers": ["900003"], "per_ticker": {},
}


def install_golden_inputs(mp) -> _FakeDB:
    """골든 입력 — 수집 하위 호출 전부 + 레지스트리(vcp·kojiro·donchian) + 셰도 DB 대역."""

    async def _fetch(start, end, limit=None):
        return [dict(r) for r in GOLDEN_LOGS]

    async def _high(start, end, *a, **k):
        return [dict(r) for r in GOLDEN_HIGH]

    async def _count(start, end):
        return {"INFO": 3, "WARNING": 2, "ERROR": 1, "CRITICAL": 1}

    async def _trades(d1, d2):
        return [dict(t) for t in GOLDEN_TRADES]

    async def _funnel():
        return {"kojiro": {"signals": 3, "orders": 2, "fills": 1},
                "donchian_swing": {"signals": 1, "orders": 1, "fills": 1}}

    async def _stages(target_date):
        return {"vcp_breakout": {
            "steps": [{"step_no": 1, "step_name": "유니버스", "survived_count": 8, "excluded_count": 0}],
            "peak_survived": 8, "final_prepared": 2, "drop_step": None, "verdict": "후보준비완료",
        }}

    async def _snapshot(now=None):
        return {"open_risk_pct_of_net": 1.23,
                "by_strategy": {"kojiro": {"open_risk": 1000.0, "positions": 1}},
                "account_gate": {"level": "ok", "stale": False}}

    mp.setattr(collector, "_fetch_logs_in_range", _fetch)
    mp.setattr(collector, "_fetch_high_severity_logs", _high)
    mp.setattr(collector, "_count_logs_by_level", _count)
    mp.setattr(collector, "get_trades_in_range", _trades)
    mp.setattr(collector, "get_request_metrics",
               lambda: {"total": 1234, "errors_5xx": 2, "by_path_5xx": {"/uapi/x": 2}})
    mp.setattr(collector, "_collect_strategy_funnel", _funnel)
    mp.setattr(collector, "_collect_strategy_funnel_stages", _stages)
    mp.setattr(collector, "_build_portfolio_risk_snapshot", _snapshot)

    _install_registry(mp, [
        _FakeStrat("vcp_breakout", {"entry_end": "14:30"}, 500_000, summary=GOLDEN_VCP_SUMMARY),
        _FakeStrat("kojiro", KOJIRO_REG_PARAMS, 1_980_000, held_tickers=("900101",)),
        _FakeStrat("donchian_swing", DONCHIAN_REG_PARAMS, 740_000, held_tickers=("900201",)),
    ])

    k_pair, k_rows = _kojiro_open_101()
    d1_pair, d1_rows = _donchian_open_901()
    d2_pair, d2_rows = _donchian_closed_902()
    return _FakeDB([k_pair, d1_pair, d2_pair],
                   {"900101": k_rows, "900201": d1_rows, "900202": d2_rows}).install(mp)


async def _golden_collect(mp) -> dict:
    """골든 입력으로 `collect_daily_log_metrics(T)` 를 T 21:30 KST 동결 시계에서 돈다."""
    install_golden_inputs(mp)
    with freeze_time(FROZEN_T_2130_UTC):
        return await collector.collect_daily_log_metrics(
            T, now_kst=datetime(2026, 10, 19, 21, 30, tzinfo=KST))


def _load_golden() -> dict:
    assert GOLDEN_PATH.exists(), f"골든 부재 — {GOLDEN_PATH} (docstring 의 생성 방법 참조)"
    payload = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
    assert payload.get("base_sha") == GOLDEN_BASE_SHA, payload.get("base_sha")
    return payload


#: 골든(0a7752a) 이후 끝에 더해진 키들 — `_ten()` 이 골든 byte 비교에서 제외한다.
#: cycle351 이 "pyramid_shadow" 하나로 시작했고, cycle366 이 "report_accuracy" 를
#: 더했다(§P6). 새 키를 더하는 사이클은 이 집합에 이름만 보태면 된다 — 기존 10키의
#: byte 계약은 그대로 유지된다.
_NON_GOLDEN_KEYS = ("pyramid_shadow", "report_accuracy")


def _ten(metrics: dict) -> dict:
    return json.loads(json.dumps(
        {k: v for k, v in metrics.items() if k not in _NON_GOLDEN_KEYS}, ensure_ascii=False))


# ===========================================================================
# 골든 (§4-1)
# ===========================================================================
async def test_golden_existing_ten_keys_byte_identical_to_head(monkeypatch):
    """확장 전(0a7752a) 기존 10키와 **값·순서까지 완전 일치** — 셰도 추가가 매매·기존 집계를 바꾸지 않았다.

    HEAD 에서 초록(골든이 HEAD 산출물이므로)이고 Green 뒤에도 초록이어야 한다.
    """
    golden = _load_golden()
    metrics = await _golden_collect(monkeypatch)
    ten = _ten(metrics)
    assert list(ten) == HEAD_METRIC_KEYS, list(ten)
    assert list(golden["metrics"]) == HEAD_METRIC_KEYS
    assert json.dumps(ten, ensure_ascii=False) == json.dumps(golden["metrics"], ensure_ascii=False)


async def test_golden_input_appends_pyramid_shadow_last_and_it_actually_ran(monkeypatch):
    """A11 — 같은 입력에서 키는 기존 10키 + `"pyramid_shadow"`(맨 끝), 그리고 셰도가 **실제로** 돌았다
    (값이 None 이면 「키만 있고 셰도는 죽은」 상태를 초록으로 통과시킨다)."""
    metrics = await _golden_collect(monkeypatch)
    assert list(metrics) == EXPECTED_METRIC_KEYS, list(metrics)
    shadow = metrics["pyramid_shadow"]
    assert isinstance(shadow, dict), shadow
    assert shadow["version"] == 1
    assert shadow["target_date"] == T.isoformat()
    assert {(r["strategy"], r["ticker"]) for r in shadow["records"]} == {
        ("kojiro", "900101"), ("donchian_swing", "900201"), ("donchian_swing", "900202"),
    }
    json.dumps(metrics, allow_nan=False)


# ===========================================================================
# 반환 모양 (§2-3 · §2-4)
# ===========================================================================
async def test_result_shape_and_ladder(monkeypatch):
    pair, rows = _donchian_open_901()
    _FakeDB([pair], {"900201": rows}).install(monkeypatch)
    out = await _build(T)
    assert list(out) == RESULT_KEYS, list(out)
    assert out["_note"] == SHADOW_NOTE, "minor — LLM 프롬프트가 이 값을 가상 기록으로 읽어야 한다"
    assert out["version"] == 1
    assert out["target_date"] == "2026-10-19"
    assert out["ladder"] == {"step_n": 1.0, "sizes": [0.6667, 0.6667, 0.6667], "gap_skip_mult": 1.05}
    assert list(out["summary"]) == SUMMARY_KEYS, list(out["summary"])
    assert list(out["records"][0]) == RECORD_KEYS, list(out["records"][0])


# ===========================================================================
# A1 · A2 — 진입 N
# ===========================================================================
async def test_a1_kojiro_entry_n_is_wilder_of_prior_bars_only(monkeypatch):
    """A1 — 매수일 **이전** 봉만의 Wilder ATR(20). 앞 봉 TR 이 전부 500 → N = 500 · r_unit = 1,000.

    매수일 봉(TR 3,000)을 넣으면(M10) 0.95×500 + 0.05×3,000 = 625 가 된다.
    """
    pair, rows = _kojiro_open_101()
    _FakeDB([pair], {"900101": rows}).install(monkeypatch)
    rec = _rec(await _build(T), "kojiro", "900101")
    assert rec["error"] is None
    assert rec["n_entry"] == _approx(500.0)
    assert rec["r_unit"] == _approx(1_000.0)
    assert rec["fixed_stop"] == _approx(9_000.0)


async def test_a1b_kojiro_entry_n_window_is_at_most_100_prior_bars(monkeypatch):
    """A1 — 창은 매수일 이전 **최대 100봉**(KOJIRO_FETCH_DAYS). 앞 50봉 TR 5,000 · 뒤 100봉 TR 500.

    100봉 창 = 시드부터 전부 500 → N = 500. 150봉 전부를 쓰면 500 + 4,500 × 0.95^100 ≈ 526.6.
    """
    pair, rows = _kojiro_open_101(prior=[5_000] * 50 + [500] * 100)
    _FakeDB([pair], {"900101": rows}).install(monkeypatch)
    rec = _rec(await _build(T), "kojiro", "900101")
    assert rec["error"] is None
    assert rec["n_entry"] == _approx(500.0)


async def test_a2_donchian_entry_n_is_sma14_of_prior_bars_truncated(monkeypatch):
    """A2 — donchian N = `StrategyBase._atr`(최신순 SMA14) → `float(int(·))`.

    앞 봉 30개: 오래된 16개 TR 900 · 그다음 1개 TR 507 · 최근 13개 TR 500.
    최신 14개 = 500×13 + 507 → 500.5 → int → **500.0**.
    오래된 순으로 넘기면 900, 매수일 봉(TR 200)을 넣으면 (200 + 500×13)/14 = 478.57 → 478.
    """
    prior = [900] * 16 + [507] + [500] * 13
    pair = _pair("donchian_swing", "900203", D[0], 10_000)
    rows = _series("900203", prior, C1_POST, rising=False)
    _FakeDB([pair], {"900203": rows}).install(monkeypatch)
    rec = _rec(await _build(T), "donchian_swing", "900203")
    assert rec["error"] is None
    assert rec["n_entry"] == 500.0
    assert rec["r_unit"] == _approx(1_000.0)


# ===========================================================================
# A3 — 범위
# ===========================================================================
async def test_a3_scope_is_open_pairs_and_pairs_closed_on_target_date(monkeypatch):
    """A3 — 넣는 것 = 보유(buy_date ≤ T) + T 에 청산. 빼는 것 = lookback(7일) 밖의 옛 청산(M11) ·
    T 이후 매수 · 다른 전략. lookback **안**의 미확정 옛 청산(§2-1 확장)은 별도
    `test_late_finalize_*` 가 다룬다 — 여기서는 그 확장의 경계(lookback 밖) 만 본다."""
    k_open, k_rows = _kojiro_open_101()
    k_closed_today = _pair("kojiro", "900111", D[0], 10_000, status="closed",
                           sell_date=T, sell_price=10_400, sell_time="11:00:00")
    k_closed_old = _pair("kojiro", "900112", D[0], 10_000, status="closed",
                         sell_date=T - timedelta(days=10), sell_price=10_350, sell_time="11:00:00")
    k_open_future = _pair("kojiro", "900113", T + timedelta(days=1), 10_000)
    d_open, d_rows = _donchian_open_901()
    mom_open = _pair("momentum", "900301", D[0], 10_000)
    daily = {t: _series(t, [500] * 120, KOJIRO_POST) for t in ("900111", "900112", "900113", "900301")}
    daily.update({"900101": k_rows, "900201": d_rows})
    _FakeDB([k_open, k_closed_today, k_closed_old, k_open_future, d_open, mom_open], daily).install(monkeypatch)

    out = await _build(T)
    assert {(r["strategy"], r["ticker"]) for r in out["records"]} == {
        ("kojiro", "900101"), ("kojiro", "900111"), ("donchian_swing", "900201"),
    }


async def test_a3b_bars_after_target_date_are_ignored(monkeypatch):
    """`bas_dd ≤ target_date` 만 쓴다 — T 다음 날 폭락 봉이 있어도 T 종가(11,700)로 평가한다."""
    pair, rows = _donchian_open_901()
    rows = rows + [_row("900201", T + timedelta(days=1), 11_000, 11_000, 5_000, 5_000)]
    _FakeDB([pair], {"900201": rows}).install(monkeypatch)
    rec = _rec(await _build(T), "donchian_swing", "900201")
    assert rec["bars_through"] == "2026-10-19"
    assert rec["v_exit_kind"] == "open"
    assert rec["virtual_R"] == _approx(2.4)


# ===========================================================================
# A4 — final · 레코드 값
# ===========================================================================
async def test_a4_open_record_values(monkeypatch):
    """보유 900201 — 코어 C1 경로, 앵커 없이 T 종가 11,700 평가.

    actual_R = 1,700 ÷ 1,000 = 1.7 · virtual_R = 2/3 × (1,700 + 1,200 + 700) ÷ 1,000 = 2.4 · delta 0.7.
    """
    pair, rows = _donchian_open_901()
    _FakeDB([pair], {"900201": rows}).install(monkeypatch)
    rec = _rec(await _build(T), "donchian_swing", "900201")

    assert list(rec) == RECORD_KEYS
    assert rec["buy_date"] == "2026-10-12"
    assert rec["entry_price"] == _approx(10_000.0)
    assert rec["status"] == "open"
    assert rec["exit_date"] is None and rec["exit_price"] is None and rec["exit_time"] is None
    assert rec["bars_through"] == "2026-10-19"
    assert rec["final"] == 0
    assert rec["actual_R"] == _approx(1.7)
    assert rec["virtual_R"] == _approx(2.4)
    assert rec["delta_R"] == _approx(0.7)
    assert rec["tranches"] == 3
    assert rec["add_dates"] == ["2026-10-13", "2026-10-14"]
    assert [round(float(p), 4) for p in rec["add_prices"]] == [10_500.0, 11_000.0]
    assert rec["set_stop"] == _approx(10_000.0)
    assert rec["fixed_stop"] == _approx(9_000.0)
    assert rec["v_exit_date"] == "2026-10-19"
    assert rec["v_exit_kind"] == "open"
    assert rec["killed"] == 0
    assert rec["error"] is None


async def test_a4_closed_final_uses_anchor(monkeypatch):
    """A4 — T 봉이 있으면 final=1 · 앵커(11,700) 적용 → v_exit_kind=anchor. actual_R = (11,700 − 10,000) ÷ 1,000."""
    pair, rows = _donchian_closed_902()
    _FakeDB([pair], {"900202": rows}).install(monkeypatch)
    rec = _rec(await _build(T), "donchian_swing", "900202")
    assert rec["status"] == "closed"
    assert rec["exit_date"] == "2026-10-19"
    assert rec["exit_price"] == _approx(11_700.0)
    assert rec["exit_time"] == "10:30:00"
    assert rec["bars_through"] == "2026-10-19"
    assert rec["final"] == 1
    assert rec["v_exit_kind"] == "anchor"
    assert rec["v_exit_date"] == "2026-10-19"
    assert rec["actual_R"] == _approx(1.7)
    assert rec["virtual_R"] == _approx(2.4)
    assert rec["delta_R"] == _approx(0.7)


async def test_a4b_closed_without_sell_date_bar_is_not_final_and_has_no_anchor(monkeypatch):
    """A4 — T 봉이 아직 없으면(20:30 적재 전) 앵커 없이 마지막 봉(D4 종가 11,500)까지 · final=0.

    virtual_R = 2/3 × (1,500 + 1,000 + 500) ÷ 1,000 = 2.0 · actual_R 는 그대로 매도가 기준 1.7.
    독립 검증 지적 #19 — final=0 이면 기준 시점이 갈려 delta_R 은 None(계산하지 않는다).
    """
    pair, rows = _donchian_closed_902()
    rows = [r for r in rows if r["bas_dd"] != T]
    _FakeDB([pair], {"900202": rows}).install(monkeypatch)
    rec = _rec(await _build(T), "donchian_swing", "900202")
    assert rec["bars_through"] == "2026-10-16"
    assert rec["final"] == 0
    assert rec["v_exit_kind"] == "open"
    assert rec["actual_R"] == _approx(1.7)
    assert rec["virtual_R"] == _approx(2.0)
    assert rec["delta_R"] is None


@pytest.mark.parametrize("sell_time,tranches", [
    ("09:29:59", 1),
    ("09:30:00", 2),
    ("14:00:00", 2),
])
async def test_a4c_anchor_add_allowed_from_sell_time(monkeypatch, sell_time, tranches):
    """`anchor_add_allowed = sell_time ≥ "09:30:00"`. 앵커 날(T) 고가 10,600 ≥ 첫 눈금 10,500."""
    post = [(10_000, 10_100, 9_900, 10_000), (10_100, 10_600, 10_050, 10_550)]
    pair = _pair("donchian_swing", "900204", T_PREV, 10_000, status="closed",
                 sell_date=T, sell_price=10_550, sell_time=sell_time)
    rows = _series("900204", PRIOR_500, post, post_dates=[T_PREV, T])
    _FakeDB([pair], {"900204": rows}).install(monkeypatch)
    rec = _rec(await _build(T), "donchian_swing", "900204")
    assert rec["final"] == 1
    assert rec["tranches"] == tranches
    assert rec["v_exit_kind"] == "anchor"


# ===========================================================================
# A5 — [pyramid_shadow_close] WARNING
# ===========================================================================
async def test_a5_marker_once_per_position_per_day_with_field_order(monkeypatch, caplog):
    """A5 — final=1 ∧ T == 오늘 → WARNING 1줄. 같은 날 두 번째 호출(20:20·21:30 재호출)은 0줄."""
    pair, rows = _donchian_closed_902()
    _FakeDB([pair], {"900202": rows}).install(monkeypatch)
    with freeze_time(FROZEN_T_2130_UTC):
        await _build(T)
        await _build(T)
    lines = _marker_lines(caplog)
    assert len(lines) == 1, lines
    msg = lines[0]
    assert re.findall(r"(?:^|\s)(\w+)=", msg) == MARKER_FIELDS, msg
    assert _field(msg, "strategy") == "donchian_swing"
    assert _field(msg, "ticker") == "900202"
    assert _field(msg, "buy_date") == "2026-10-12"
    assert _field(msg, "exit_date") == "2026-10-19"
    assert _field(msg, "v_exit_kind") == "anchor"
    assert _field(msg, "tranches") == "3"
    assert _field(msg, "killed") == "0"

    ps = _ps()
    from src.engine.daily_emit_cap import KstDailyEmitCap
    caps = [v for v in vars(ps).values() if isinstance(v, KstDailyEmitCap)]
    assert any("donchian_swing:900202:2026-10-12" in c for c in caps), "cap 키 = strategy:ticker:buy_date"


async def test_a5b_marker_one_line_per_position(monkeypatch, caplog):
    """cap 키가 포지션 단위라 두 포지션이 같은 날 확정되면 2줄 — 세 번 불러도 2줄."""
    p1, r1 = _donchian_closed_902()
    p2 = _pair("kojiro", "900111", D[0], 10_000, status="closed",
               sell_date=T, sell_price=10_400, sell_time="11:00:00")
    r2 = _series("900111", [500] * 120, KOJIRO_POST)
    _FakeDB([p1, p2], {"900202": r1, "900111": r2}).install(monkeypatch)
    with freeze_time(FROZEN_T_2130_UTC):
        for _ in range(3):
            await _build(T)
    lines = _marker_lines(caplog)
    assert sorted(_field(m, "ticker") for m in lines) == ["900111", "900202"], lines


async def test_a5c_marker_not_for_past_date_final0_or_open(monkeypatch, caplog):
    """과거 날짜 호출(수동 재실행) · final=0 · 보유 중 = 0줄 — 그리고 cap 을 소비하지 않는다."""
    past_pair = _pair("donchian_swing", "900205", D[0], 10_000, status="closed",
                      sell_date=T_PREV, sell_price=11_500, sell_time="10:00:00")
    past_rows = _series("900205", PRIOR_500, C1_POST[:5])
    closed_today, rows_today = _donchian_closed_902()
    rows_not_loaded = [r for r in rows_today if r["bas_dd"] != T]
    open_pair, open_rows = _donchian_open_901()
    db = _FakeDB([past_pair, closed_today, open_pair],
                 {"900205": past_rows, "900202": rows_not_loaded, "900201": open_rows}).install(monkeypatch)

    with freeze_time(FROZEN_T_2130_UTC):
        past = await _build(T_PREV)
        today = await _build(T)
    assert _rec(past, "donchian_swing", "900205")["final"] == 1
    assert _rec(today, "donchian_swing", "900202")["final"] == 0
    assert _marker_lines(caplog) == []

    # 20:30 적재 뒤(21:30) 같은 날 다시 부르면 그때 처음 확정된 한 줄이 나온다.
    db.daily["900202"] = rows_today
    with freeze_time(FROZEN_T_2130_UTC):
        await _build(T)
    lines = _marker_lines(caplog)
    assert len(lines) == 1 and _field(lines[0], "ticker") == "900202", lines


# ===========================================================================
# A6 — never-raise (레코드 단위)
# ===========================================================================
async def test_a6_one_ticker_daily_exception_errors_only_that_record(monkeypatch, caplog):
    """A6 — 한 종목 일봉 예외 → 그 레코드만 error, 나머지는 정상. 실패 흔적은 DEBUG `[pyramid_shadow_error]`
    (데이터 마커 `[pyramid_shadow_close]` 를 쓰지 않는다 — cycle349 선례)."""
    ok_pair, ok_rows = _donchian_open_901()
    bad_pair = _pair("donchian_swing", "900206", D[0], 10_000)
    _FakeDB([ok_pair, bad_pair], {"900201": ok_rows}, raise_daily_for={"900206"}).install(monkeypatch)
    caplog.set_level(logging.DEBUG)
    with freeze_time(FROZEN_T_2130_UTC):
        out = await _build(T)
    bad = _rec(out, "donchian_swing", "900206")
    assert list(bad) == RECORD_KEYS
    assert isinstance(bad["error"], str) and bad["error"]
    ok = _rec(out, "donchian_swing", "900201")
    assert ok["error"] is None
    assert ok["virtual_R"] == _approx(2.4)
    assert out["summary"]["errors_n"] == 1
    msgs = [r.getMessage() for r in caplog.records]
    assert [m for m in msgs if m.startswith("[pyramid_shadow_error] ")], "실패 흔적 무음"
    assert not [m for m in _marker_lines(caplog) if "900206" in m]


async def test_a6b_missing_entry_bar_and_zero_atr_are_record_errors(monkeypatch):
    """§2-2 — 매수일 봉 없음 = `no_entry_bar` · N ≤ 0 = `no_atr`(그 레코드만, 계속한다)."""
    no_bar = _pair("donchian_swing", "900207", D[0], 10_000)
    no_bar_rows = [r for r in _series("900207", PRIOR_500, C1_POST) if r["bas_dd"] != D[0]]
    flat = _pair("donchian_swing", "900208", D[0], 10_000)
    flat_rows = _series("900208", [0] * 30, C1_POST, rising=False)   # 앞 봉 고=저=종 → ATR 0
    short = _pair("donchian_swing", "900209", D[0], 10_000)
    short_rows = _series("900209", [500] * 5, C1_POST)                  # period+2 미만 → `_atr` 0
    k_flat = _pair("kojiro", "900121", D[0], 10_000)
    k_flat_rows = _series("900121", [0] * 120, KOJIRO_POST, rising=False)
    ok_pair, ok_rows = _donchian_open_901()
    _FakeDB([no_bar, flat, short, k_flat, ok_pair],
            {"900207": no_bar_rows, "900208": flat_rows, "900209": short_rows,
             "900121": k_flat_rows, "900201": ok_rows}).install(monkeypatch)
    out = await _build(T)
    assert _rec(out, "donchian_swing", "900207")["error"] == "no_entry_bar"
    assert _rec(out, "donchian_swing", "900208")["error"] == "no_atr"
    assert _rec(out, "donchian_swing", "900209")["error"] == "no_atr"
    assert _rec(out, "kojiro", "900121")["error"] == "no_atr"
    assert _rec(out, "donchian_swing", "900201")["error"] is None
    assert out["summary"]["errors_n"] == 4


# ===========================================================================
# A7 — JSON (allow_nan=False)
# ===========================================================================
async def test_a7_json_dumps_allow_nan_false_with_degenerate_inputs(monkeypatch):
    """A7 — 퇴화 봉(ATR 0 · 가격 0 · NaN · inf)을 섞어도 `json.dumps(allow_nan=False)` 성공(M12).

    `daily_log_reports.metrics` 는 JSONB 라 NaN 하나가 21:30 리포트 INSERT 전체를 깨뜨린다.
    """
    zero_pair = _pair("kojiro", "900131", D[0], 10_000)
    zero_rows = [_row("900131", d, 0, 0, 0, 0) for d in _prior_bdays(D[0], 120) + D]   # 가격 0 봉
    nan_close = _pair("kojiro", "900132", D[0], 10_000)
    nan_rows = _series("900132", [500] * 120, KOJIRO_POST[:5] + [(10_350, 10_480, 10_300, float("nan"))])
    inf_high = _pair("donchian_swing", "900210", D[0], 10_000)
    inf_rows = _series("900210", PRIOR_500, C1_POST[:2] + [(10_450, float("inf"), 10_400, 10_900)] + C1_POST[3:])
    nan_sell = _pair("donchian_swing", "900211", D[0], 10_000, status="closed",
                     sell_date=T, sell_price=float("nan"), sell_time="10:30:00")
    nan_sell_rows = _series("900211", PRIOR_500, C1_POST)
    zero_entry = _pair("donchian_swing", "900212", D[0], 0.0)
    zero_entry_rows = _series("900212", PRIOR_500, C1_POST)
    ok_pair, ok_rows = _donchian_open_901()
    _FakeDB([zero_pair, nan_close, inf_high, nan_sell, zero_entry, ok_pair],
            {"900131": zero_rows, "900132": nan_rows, "900210": inf_rows,
             "900211": nan_sell_rows, "900212": zero_entry_rows, "900201": ok_rows}).install(monkeypatch)

    out = await _build(T)
    json.dumps(out, allow_nan=False)
    bad = [x for x in _walk_numbers(out) if isinstance(x, float) and not math.isfinite(x)]
    assert not bad, bad
    for sid, t in (("kojiro", "900131"), ("kojiro", "900132"), ("donchian_swing", "900210"),
                   ("donchian_swing", "900211"), ("donchian_swing", "900212"),
                   ("donchian_swing", "900201")):
        _rec(out, sid, t)


# ===========================================================================
# A8 — 적격
# ===========================================================================
@pytest.mark.parametrize("budget,shares,eligible", [
    (2_000_000, 13, 1),    # floor(2/3 × 2,000,000 × 0.005 ÷ 500) = floor(13.33)
    (330_000, 2, 1),       # floor(2.2) = 2 → 사다리 선다(경계 ≥ 2)
    (240_000, 1, 0),       # floor(1.6) = 1 → 사다리 없음(1주 랏)
    (None, None, None),    # 예산 모름
    (0, None, None),       # 0 이하 = 모름
])
async def test_a8_tranche_shares_and_eligibility(monkeypatch, budget, shares, eligible):
    """A8 — `tranche_shares = floor(sizes[0] × 예산 × risk_pct ÷ N)`, ≥2 → eligible 1(kojiro 폴백 risk 0.005)."""
    pair, rows = _kojiro_open_101()
    _FakeDB([pair], {"900101": rows}).install(monkeypatch)
    rec = _rec(await _build(T, budget_by_sid={"kojiro": budget}), "kojiro", "900101")
    assert rec["tranche_shares"] == shares
    assert rec["eligible"] == eligible


async def test_a8b_virtual_r_does_not_depend_on_eligibility(monkeypatch):
    """§2-3 — `virtual_R` 은 적격과 무관하게 계산한다(S0 Δ 와 부호 비교가 성립하려면 같아야 한다)."""
    pair, rows = _donchian_open_901()
    _FakeDB([pair], {"900201": rows}).install(monkeypatch)
    rich = _rec(await _build(T, budget_by_sid={"donchian_swing": 740_000}), "donchian_swing", "900201")
    poor = _rec(await _build(T, budget_by_sid={"donchian_swing": 50_000}), "donchian_swing", "900201")
    assert rich["eligible"] == 1 and poor["eligible"] == 0
    assert rich["virtual_R"] == poor["virtual_R"] == _approx(2.4)
    assert rich["tranches"] == poor["tranches"] == 3


# ===========================================================================
# A9 — 파라미터
# ===========================================================================
async def test_a9_registry_params_take_precedence(monkeypatch):
    """A9 — 레지스트리 값 우선: donchian stop_atr 3.0 → r_unit 1,500 · 고정선 8,500 / kojiro risk 0.01 → 26주."""
    d_pair, d_rows = _donchian_open_901()
    k_pair, k_rows = _kojiro_open_101()
    _FakeDB([d_pair, k_pair], {"900201": d_rows, "900101": k_rows}).install(monkeypatch)
    out = await _build(
        T,
        params_by_sid={
            "donchian_swing": {**DONCHIAN_REG_PARAMS, "stop_atr": 3.0},
            "kojiro": {**KOJIRO_REG_PARAMS, "risk_pct": 0.01},
        },
        budget_by_sid={"kojiro": 2_000_000},
    )
    d = _rec(out, "donchian_swing", "900201")
    assert d["r_unit"] == _approx(1_500.0)
    assert d["fixed_stop"] == _approx(8_500.0)
    assert d["params_source"] != "fallback"
    k = _rec(out, "kojiro", "900101")
    assert k["tranche_shares"] == 26     # floor(2/3 × 2,000,000 × 0.01 ÷ 500) = floor(26.67)
    assert k["params_source"] != "fallback"


@pytest.mark.parametrize("params_by_sid", [{}, {"donchian_swing": None, "kojiro": None}])
async def test_a9b_absent_params_use_fallback_constants(monkeypatch, params_by_sid):
    """A9 — 부재 → 폴백 상수(donchian stop_atr 2.0 · kojiro risk_pct 0.005) + `params_source="fallback"`."""
    d_pair, d_rows = _donchian_open_901()
    k_pair, k_rows = _kojiro_open_101()
    _FakeDB([d_pair, k_pair], {"900201": d_rows, "900101": k_rows}).install(monkeypatch)
    out = await _build(T, params_by_sid=params_by_sid, budget_by_sid={"kojiro": 2_000_000})
    d = _rec(out, "donchian_swing", "900201")
    assert d["r_unit"] == _approx(1_000.0)
    assert d["params_source"] == "fallback"
    k = _rec(out, "kojiro", "900101")
    assert k["tranche_shares"] == 13
    assert k["params_source"] == "fallback"


# ===========================================================================
# 요약 · 상한
# ===========================================================================
async def test_summary_counts_and_won_fields(monkeypatch):
    """§2-4 요약 — donchian 보유 900201(3트랜치, 9주) · donchian 청산 900202(final) · kojiro 보유 900101(1트랜치, 13주).

    - extra_notional_won = 보유 ∧ 2트랜치 이후 추가분 명목 = 9 × (10,500 + 11,000) = 193,500
    - gap_stress_won = (9 × 3 × 11,700 + 13 × 1 × 10,400) × 10% = (315,900 + 135,200) × 0.1 = 45,110
    - delta_R_mean_closed_final = 900202 의 0.7
    tranche_shares: donchian floor(2/3 × 740,000 × 0.01 ÷ 500) = floor(9.87) = 9 ·
    kojiro floor(2/3 × 2,000,000 × 0.005 ÷ 500) = 13.
    """
    d1, r1 = _donchian_open_901()
    d2, r2 = _donchian_closed_902()
    k1, rk = _kojiro_open_101()
    _FakeDB([d1, d2, k1], {"900201": r1, "900202": r2, "900101": rk}).install(monkeypatch)
    out = await _build(T, budget_by_sid={"donchian_swing": 740_000, "kojiro": 2_000_000})
    assert _rec(out, "donchian_swing", "900201")["tranche_shares"] == 9
    s = out["summary"]
    assert s["open_n"] == 2
    assert s["closed_n"] == 1
    assert s["closed_final_n"] == 1
    assert s["killed_n"] == 0
    assert s["eligible_n"] == 3
    assert s["delta_R_mean_closed_final"] == _approx(0.7)
    assert s["extra_notional_won"] == pytest.approx(193_500, abs=1)
    assert s["gap_stress_won"] == pytest.approx(45_110, abs=1)
    assert s["errors_n"] == 0
    assert s["truncated"] == 0


async def test_minor22_gap_stress_and_extra_notional_exclude_already_exited_shadow(monkeypatch):
    """지적(minor) #22 — 가상 사다리가 이미 세트선으로 나간(`v_exit_kind != "open"`) 보유
    레코드는 지금 사다리 명목이 0 인데도 `extra_notional_won`·`gap_stress_won` 에 더해지면
    안 된다. 기존 `test_summary_counts_and_won_fields` 와 같은 두 보유(900201·900101)에
    세트선으로 이미 청산된 보유(900225, 예산 충분·적격)를 하나 더해도 합계가 그대로여야
    한다(추가분이 0 이라는 뜻).
    """
    d1, r1 = _donchian_open_901()
    k1, rk = _kojiro_open_101()
    killed_pair = _pair("donchian_swing", "900225", D[0], 10_000)
    killed_rows = _series("900225", PRIOR_500, [
        (10_000, 10_100, 9_900, 10_000),
        (10_100, 10_500, 10_050, 10_400),   # 추가 10,500
        (10_300, 10_350, 9_400, 9_600),     # 저가 9,400 ≤ 9,500(세트선) → killed
    ])
    _FakeDB([d1, k1, killed_pair], {"900201": r1, "900101": rk, "900225": killed_rows}).install(monkeypatch)
    out = await _build(T, budget_by_sid={"donchian_swing": 740_000, "kojiro": 2_000_000})
    killed_rec = _rec(out, "donchian_swing", "900225")
    assert killed_rec["v_exit_kind"] == "set_line"
    assert killed_rec["killed"] == 1
    assert killed_rec["eligible"] == 1  # 예산은 충분 — 적격과 무관하게 제외돼야 한다
    s = out["summary"]
    assert s["extra_notional_won"] == pytest.approx(193_500, abs=1), "이미 청산된 사다리가 더해졌다"
    assert s["gap_stress_won"] == pytest.approx(45_110, abs=1), "이미 청산된 사다리가 더해졌다"


async def test_minor22b_gap_stress_and_extra_notional_exclude_ineligible(monkeypatch):
    """지적(minor) #22 — 1주 폴백 랏(비적격)도 `extra_notional_won`·`gap_stress_won` 에서
    빠져야 한다(설계상 사다리가 없는 랏의 「가상 사다리 명목」은 의미가 없다)."""
    d1, r1 = _donchian_open_901()
    ineligible_pair = _pair("kojiro", "900226", D[0], 10_000)
    ineligible_rows = _series("900226", [500] * 120, KOJIRO_POST)
    _FakeDB([d1, ineligible_pair], {"900201": r1, "900226": ineligible_rows}).install(monkeypatch)
    out = await _build(T, budget_by_sid={"donchian_swing": 740_000, "kojiro": 200_000})
    ineligible_rec = _rec(out, "kojiro", "900226")
    assert ineligible_rec["eligible"] == 0
    s = out["summary"]
    assert s["extra_notional_won"] == pytest.approx(193_500, abs=1)
    assert s["gap_stress_won"] == pytest.approx(31_590, abs=1), "900201 단독분 = 9×3×11,700×0.1"


async def test_summary_delta_mean_is_null_without_closed_final(monkeypatch):
    pair, rows = _donchian_open_901()
    _FakeDB([pair], {"900201": rows}).install(monkeypatch)
    out = await _build(T)
    assert out["summary"]["delta_R_mean_closed_final"] is None
    assert out["summary"]["closed_final_n"] == 0


async def test_records_capped_at_50_with_truncated_flag(monkeypatch):
    """§2-3 — 레코드 상한 50개, 넘으면 앞 50개 + `summary.truncated=1`."""
    pairs, daily = [], {}
    for i in range(55):
        t = f"95{i:04d}"
        p, rows = _pair("donchian_swing", t, D[0], 10_000), _series(t, PRIOR_500, C1_POST)
        pairs.append(p)
        daily[t] = rows
    _FakeDB(pairs, daily).install(monkeypatch)
    out = await _build(T)
    assert len(out["records"]) == 50
    assert out["summary"]["truncated"] == 1
    json.dumps(out, allow_nan=False)


# ===========================================================================
# 추가 시점 기록 — add_stage / add_macd (§2-3, 기록만)
# ===========================================================================
async def test_add_stage_and_macd_are_recorded_from_previous_completed_bar(monkeypatch):
    """추가 체결일 d 마다 **d−1 완성봉**의 kojiro 스테이지 · MACD3 상태(gc/up/dn).

    오라클 = 명세가 지정한 `kojiro_indicators.enrich`(기본 설정)를 그 종목 전 봉(≤ T)에 한 번 돌린 값.
    900201 의 추가일은 D1·D2 → 읽는 봉은 D0·D1.
    """
    import pandas as pd

    from src.engine.kojiro_indicators import KojiroIndicatorConfig, enrich

    pair, rows = _donchian_open_901()
    _FakeDB([pair], {"900201": rows}).install(monkeypatch)
    rec = _rec(await _build(T), "donchian_swing", "900201")

    asc = sorted(rows, key=lambda r: r["bas_dd"])
    df = pd.DataFrame({
        "open": [float(r["open_price"]) for r in asc], "high": [float(r["high_price"]) for r in asc],
        "low": [float(r["low_price"]) for r in asc], "close": [float(r["close_price"]) for r in asc],
        "volume": [float(r["volume"]) for r in asc],
    }, index=[r["bas_dd"] for r in asc])
    en = enrich(df, KojiroIndicatorConfig())
    idx = {r["bas_dd"]: i for i, r in enumerate(asc)}

    def _stage(i):
        v = en["stage"].iloc[i]
        return None if v is None or (isinstance(v, float) and math.isnan(v)) else int(v)

    def _macd(i):
        m, s = en["macd3"].iloc[i], en["macd3_sig"].iloc[i]
        pm, psg = en["macd3"].iloc[i - 1], en["macd3_sig"].iloc[i - 1]
        if pm <= psg and m > s:
            return "gc"
        return "up" if m > s else "dn"

    prev_bars = [idx[D[0]], idx[D[1]]]
    assert rec["add_stage"] == [_stage(i) for i in prev_bars]
    assert rec["add_macd"] == [_macd(i) for i in prev_bars]


# ===========================================================================
# 늦은 확정 — 매도일 봉이 판 날 없어도 최근 N일 안에 다시 확정한다 (독립 검증 지적 #1·#18)
# ===========================================================================
LATE_SELL_DATE = D[3]        # 2026-10-15(목) — T(10-19) 로부터 4 달력일 전, lookback(7) 안
LATE_SELL_ROWS = C1_POST[:4]  # D0..D3 4봉, D3 종가 11,400 = 매도가와 일치


def _late_finalize_pair(ticker: str = "900220"):
    pair = _pair("donchian_swing", ticker, D[0], 10_000, status="closed",
                 sell_date=LATE_SELL_DATE, sell_price=11_400, sell_time="10:30:00")
    rows = _series(ticker, PRIOR_500, LATE_SELL_ROWS)
    return pair, rows


async def test_late_finalize_scope_excludes_missing_sell_bar_then_includes_once_loaded(monkeypatch):
    """판 날(D3) 21:30 에는 그 봉이 없어 final=0 · scope 는 sell_date==target_date 뿐이라 포함.

    이후(T, 4일 뒤) 그 봉이 적재되면(§20:30 D+1 7일 증분 보정) 최근 N일 재확인 창이 이 청산을
    다시 집어 확정한다 — final=1 · 마커 발화.
    """
    pair, rows = _late_finalize_pair()
    rows_missing = [r for r in rows if r["bas_dd"] != LATE_SELL_DATE]
    db = _FakeDB([pair], {"900220": rows_missing}).install(monkeypatch)

    out_sell_day = await _build(LATE_SELL_DATE)
    rec0 = _rec(out_sell_day, "donchian_swing", "900220")
    assert rec0["final"] == 0
    assert out_sell_day["summary"]["closed_nonfinal_n"] == 1

    db.daily["900220"] = rows  # D+1 증분 보정으로 매도일 봉이 이제 있다
    with freeze_time(_utc_of(datetime(2026, 10, 19, 21, 30))):
        out_t = await _build(T)
    rec1 = _rec(out_t, "donchian_swing", "900220")
    assert rec1["final"] == 1
    assert rec1["exit_date"] == LATE_SELL_DATE.isoformat()
    assert out_t["summary"]["closed_nonfinal_n"] == 0


async def test_late_finalize_marker_fires_once_on_the_night_it_resolves(monkeypatch):
    """확정된 밤 하루만 마커가 뜬다 — 그날 재호출은 기존 cap 이, 다음 날부터는 새 dedup 이 막는다."""
    from src.engine import pyramid_shadow as ps

    pair, rows = _late_finalize_pair()
    rows_missing = [r for r in rows if r["bas_dd"] != LATE_SELL_DATE]
    db = _FakeDB([pair], {"900220": rows_missing}).install(monkeypatch)
    with freeze_time(_utc_of(datetime(2026, 10, 15, 21, 30))):
        await _build(LATE_SELL_DATE)  # 봉 없음 — final=0, 마커 없음

    db.daily["900220"] = rows
    caplog_marker_dates: list[str] = []
    import logging as _logging

    logger_ = _logging.getLogger(ps.__name__)
    handler = _logging.Handler()
    records: list[str] = []
    handler.emit = lambda r: records.append(r.getMessage())  # type: ignore[method-assign]
    logger_.addHandler(handler)
    try:
        with freeze_time(_utc_of(datetime(2026, 10, 19, 21, 30))):
            await _build(T)          # 확정되는 첫 밤 — 마커 1줄
            await _build(T)          # 같은 밤 재호출 — 기존 cap 이 억제(0줄 추가)
        with freeze_time(_utc_of(datetime(2026, 10, 20, 21, 30))):
            out_next = await _build(T + timedelta(days=1))   # 다음 날 — dedup 이 scope 에서 제외
    finally:
        logger_.removeHandler(handler)

    marker_lines = [m for m in records if m.startswith(MARKER + " ")]
    assert len(marker_lines) == 1, marker_lines
    assert {(r["strategy"], r["ticker"]) for r in out_next["records"]} == set(), out_next["records"]


async def test_late_finalize_lookback_window_gives_up_after_n_days(monkeypatch):
    """lookback(7 달력일) 밖의 청산은 봉이 나중에 생겨도 다시 집지 않는다(영구 결손)."""
    pair, rows = _late_finalize_pair()
    rows_missing = [r for r in rows if r["bas_dd"] != LATE_SELL_DATE]
    _FakeDB([pair], {"900220": rows}).install(monkeypatch)  # 봉은 있지만 창 밖
    far_future = LATE_SELL_DATE + timedelta(days=30)
    out = await _build(far_future)
    assert {(r["strategy"], r["ticker"]) for r in out["records"]} == set()


async def test_no_adds_record_empty_add_lists(monkeypatch):
    pair, rows = _kojiro_open_101()
    _FakeDB([pair], {"900101": rows}).install(monkeypatch)
    rec = _rec(await _build(T), "kojiro", "900101")
    assert rec["tranches"] == 1
    assert rec["add_dates"] == [] and rec["add_prices"] == []
    assert rec["set_stop"] is None
    # kojiro 보유: actual_R = (10,400 − 10,000) ÷ 1,000 = 0.4 · virtual_R = 2/3 × 0.4
    assert rec["actual_R"] == _approx(0.4)
    assert rec["virtual_R"] == _approx(TWO_THIRDS * 0.4)


# ===========================================================================
# F5 — 어댑터가 실제 달력에서 만든 no_add 가 금요일에도 적용된다
# ===========================================================================
async def test_f5_adapter_blocks_add_on_friday_and_defers_to_next_business_day(monkeypatch):
    """F5 — D 배열의 D[4]=2026-10-16(금) 에 추가 눈금(10,500)이 걸려도 그날 사지 않고,
    다음 영업일 T=2026-10-19(월) 에 산다. `no_add = [False]*len(dates)` 로 배선이 끊기면
    금요일(D4) 에 10,500 에 사서 add_dates 가 하루 당겨진다.
    """
    post = [
        (10_000, 10_100, 9_900, 10_000),   # D0(월)
        (10_050, 10_100, 9_950, 10_050),   # D1(화)
        (10_050, 10_150, 10_000, 10_100),  # D2(수)
        (10_100, 10_200, 10_050, 10_150),  # D3(목)
        (10_150, 10_600, 10_100, 10_550),  # D4(금) — 고가 10,600 ≥ 10,500 이지만 no_add
        (10_550, 10_700, 10_500, 10_650),  # T(월) — 여기서 10,550 에 체결
    ]
    pair = _pair("donchian_swing", "900221", D[0], 10_000)
    rows = _series("900221", PRIOR_500, post)
    _FakeDB([pair], {"900221": rows}).install(monkeypatch)
    rec = _rec(await _build(T), "donchian_swing", "900221")
    assert rec["error"] is None
    assert rec["tranches"] == 2
    assert rec["add_dates"] == [T.isoformat()], "금요일(D4) 에 사면 안 된다"
    assert rec["add_prices"] == [10_550.0]


# ===========================================================================
# R9 — 콜렉터가 donchian_swing 을 정확한 이름으로 레지스트리 조회한다
# ===========================================================================
async def test_r9_collector_wires_donchian_swing_registry_params_and_budget(monkeypatch):
    """R9 — 콜렉터의 대상 sid 튜플에 `"donchian_swing"` 오타(`"donchian"`)가 있으면
    `registry.get("donchian")` 이 None 이라 donchian 은 params·budget 을 못 받고
    `params_source="fallback"` · `tranche_shares=None` 으로 떨어진다. 골든 입력(레지스트리에
    `donchian_swing` 으로 등록)으로 정상 배선을 고정한다.
    """
    metrics = await _golden_collect(monkeypatch)
    rec = _rec(metrics["pyramid_shadow"], "donchian_swing", "900201")
    assert rec["params_source"] == "registry", "sid 오타면 fallback 으로 떨어진다"
    assert rec["tranche_shares"] == 9, "budget(740,000) 이 안 실리면 tranche_shares 가 None 이 된다"
    assert rec["eligible"] == 1


# ===========================================================================
# S4 — donchian 이 `turtle_backstop_pct` 키로 backstop 을 읽는다(항상 hard_stop_pct −8 아님)
# ===========================================================================
async def test_s4_donchian_backstop_uses_turtle_backstop_pct_not_hardcoded_hard_stop_pct(monkeypatch):
    """S4·S5 — donchian 레지스트리 `turtle_backstop_pct=-1.0`(매우 타이트)을 실제로 쓰면
    backstop(10,147.5)이 세트선(9,500)보다 훨씬 조여 저가 9,950 에서 청산된다. `hard_stop_pct`
    키(donchian 엔 없음)로 잘못 읽거나 코어가 −8% 를 하드코딩하면 backstop 이 9,430 으로
    느슨해져 세트선(9,500)이 이기고, 저가 9,950 은 무사히 통과한다(정답과 반대).
    """
    post = [
        (10_000, 10_100, 9_900, 10_000),   # D0
        (10_100, 10_500, 10_200, 10_400),  # D1 — 추가 10,500 → avg 10,250, 저가 10,200 은 무사
        (10_200, 10_300, 9_950, 10_100),   # D2 — 저가 9,950 ≤ 10,147.5(backstop) → 청산
        (10_100, 10_150, 10_050, 10_100),
        (10_100, 10_150, 10_050, 10_100),
        (10_100, 10_150, 10_050, 10_100),
    ]
    pair = _pair("donchian_swing", "900223", D[0], 10_000)
    rows = _series("900223", PRIOR_500, post)
    _FakeDB([pair], {"900223": rows}).install(monkeypatch)
    out = await _build(
        T,
        params_by_sid={"donchian_swing": {**DONCHIAN_REG_PARAMS, "turtle_backstop_pct": -1.0}},
    )
    rec = _rec(out, "donchian_swing", "900223")
    assert rec["error"] is None
    assert rec["tranches"] == 2
    assert rec["v_exit_kind"] == "avg_backstop"
    assert rec["set_stop"] == _approx(9_500.0)


# ===========================================================================
# B7 — 어댑터가 `breakeven_promote_atr` 레지스트리 값을 실제로 넘긴다
# ===========================================================================
async def test_b7_adapter_wires_breakeven_promote_atr_from_registry(monkeypatch):
    """B7 — 레지스트리 `breakeven_promote_atr=1.0`(기본 1.5 아님)을 어댑터가 실제로 전달하면
    임계가 avg+1.0N(10,750)이 되어 그 경계에서 armed. 값을 안 넘기고 항상 1.5 를 쓰면(하드코딩)
    임계가 11,000 이라 이 시나리오에서 armed 되지 않는다.
    """
    post = [
        (10_000, 10_100, 9_900, 10_000),
        (10_100, 10_500, 10_050, 10_400),   # 추가 10,500 → avg 10,250
        (10_400, 10_750, 10_350, 10_700),   # hsb → 10,750 = avg+1.0N
        (10_700, 10_750, 10_200, 10_300),   # 저가 10,200 ≤ 10,250(armed)
    ]
    pair = _pair("donchian_swing", "900222", D[0], 10_000)  # 보유 중(앵커 없음) — override 회피
    rows = _series("900222", PRIOR_500, post)
    _FakeDB([pair], {"900222": rows}).install(monkeypatch)
    out = await _build(
        D[3],
        params_by_sid={"donchian_swing": {**DONCHIAN_REG_PARAMS, "breakeven_promote_atr": 1.0}},
    )
    rec = _rec(out, "donchian_swing", "900222")
    assert rec["error"] is None
    assert rec["v_exit_kind"] == "avg_breakeven"
    assert rec["v_exit_date"] == D[3].isoformat()


# ===========================================================================
# N8·N9 — kojiro 어댑터가 조립한 live be_atr 시퀀스가 명세대로 정렬돼 있다
# ===========================================================================
def _bdays_from(start: date, n: int) -> list[date]:
    out: list[date] = []
    d = start
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


#: N8·N9 — D1..D3 는 TR=3,000 으로 live ATR 을 500→~800 대로 밀어올리되 고가를 추가 레벨
#: 아래로 눌러 둔다. D4·D6 에서 2·3번째 트랜치가 다 차 avg=10,500 이 된 뒤(더 이상 추가
#: 슬롯이 없다 — 이후 고가가 얼마든 3번째 이상은 없다), be_mult=2.0(레지스트리 override)에서
#: `fallback N=500` 임계(11,500)와 `live ATR≈803` 임계(≈12,100) 사이(D7 hsb 11,800)에 걸리게
#: 설계했다 — be_atr 가 None 이거나(N9) 한 칸 밀리면(N8) D8 에서 엉뚱하게 armed 된다.
N8N9_POST = [
    (10_000, 10_100, 9_900, 10_000),      # D0 진입
    (10_000, 10_400, 7_400, 9_000),       # D1 TR=3,000(추가 레벨 아래 억제)
    (9_000, 10_400, 7_400, 9_500),        # D2 TR=3,000
    (9_500, 10_400, 7_400, 9_800),        # D3 TR=3,000
    (9_800, 10_600, 9_700, 10_500),       # D4 추가① 10,500 → avg 10,250
    (10_500, 10_650, 10_400, 10_600),     # D5
    (10_600, 11_100, 10_550, 11_000),     # D6 추가② 11,000 → avg 10,500(슬롯 소진)
    (11_100, 11_800, 11_050, 11_700),     # D7 — hsb → 11,800(두 임계 사이)
    (11_700, 11_750, 10_400, 10_500),     # D8 — 저가 10,400, armed 이면 avg_breakeven 청산
]
N8N9_BE_MULT = 2.0


async def test_n9_kojiro_adapter_be_atr_matches_independent_oracle(monkeypatch):
    """N9 — `KOJIRO_POST` 표준 시나리오는 추가가 한 번도 없어(§2-2) 어댑터가 조립한
    `be_atr` 시퀀스가 실전에서 한 번도 안 쓰인다. `N8N9_POST`(+`breakeven_promote_atr=2.0`
    레지스트리 override)는 live ATR(~803)과 fallback N(500)의 본전 임계가 hsb(D7, 11,800)를
    사이에 두고 갈리게 설계했다 — be_atr 가 None 으로 떨어지면(N9) D8 에서 엉뚱하게 armed
    되어 청산이 난다(N8 오프셋 시프트는 이 표본에서 판별력이 없다 — 아래 별도 테스트).

    같은 조립 규칙(§2-2: 매수일 이전 최대 100봉 + 매수일부터 시퀀스,
    `n_entry=series.iloc[len(window)-1]` · `be_seq=series.iloc[len(window):]`)을
    **독립적으로** 재구현한 오라클로 이 픽스처가 실제로 갈리는지 먼저 자체 검증한다.
    """
    import pandas as pd

    from src.engine.kojiro_indicators import atr as kojiro_atr

    start = D[0] + timedelta(days=30)  # 다른 테스트 날짜와 겹치지 않는 별도 달력
    dates = _bdays_from(start, len(N8N9_POST))
    target = dates[-1]
    pair = _pair("kojiro", "900141", dates[0], 10_000)
    rows = _series("900141", [500] * 120, N8N9_POST, post_dates=dates)
    _FakeDB([pair], {"900141": rows}).install(monkeypatch)

    asc = sorted(rows, key=lambda r: r["bas_dd"])
    entry_i = next(i for i, r in enumerate(asc) if r["bas_dd"] == dates[0])
    window = asc[max(0, entry_i - 100):entry_i]
    combined = window + asc[entry_i:]
    df = pd.DataFrame({
        "high": [float(r["high_price"]) for r in combined],
        "low": [float(r["low_price"]) for r in combined],
        "close": [float(r["close_price"]) for r in combined],
    })
    series = kojiro_atr(df, 20)
    n_entry_oracle = float(series.iloc[len(window) - 1])
    be_seq_oracle = [float(x) for x in series.iloc[len(window):].tolist()]

    ps = _ps()
    sim_bars = [
        (r["bas_dd"], float(r["open_price"]), float(r["high_price"]),
         float(r["low_price"]), float(r["close_price"]))
        for r in asc[entry_i:]
    ]
    no_add = ps.no_add_flags([b[0] for b in sim_bars])
    oracle_live = ps.overlay_ladder(
        sim_bars, 0, 10_000.0, n_entry_oracle,
        cfg=ps.LADDER_C, stop_atr=2.0, hard_stop_pct=-8.0, be_mult=N8N9_BE_MULT,
        be_atr=be_seq_oracle, no_add=no_add, anchor_idx=None, anchor_price=None,
        anchor_add_allowed=True,
    )
    oracle_fallback = ps.overlay_ladder(
        sim_bars, 0, 10_000.0, n_entry_oracle,
        cfg=ps.LADDER_C, stop_atr=2.0, hard_stop_pct=-8.0, be_mult=N8N9_BE_MULT,
        be_atr=None, no_add=no_add, anchor_idx=None, anchor_price=None,
        anchor_add_allowed=True,
    )
    assert oracle_live["exit_kind"] != oracle_fallback["exit_kind"], (
        "이 픽스처는 live ATR 유무로 결과가 안 갈린다 — 판별력이 없다"
    )

    rec = _rec(
        await _build(
            target,
            params_by_sid={"kojiro": {**KOJIRO_REG_PARAMS, "breakeven_promote_atr": N8N9_BE_MULT}},
        ),
        "kojiro", "900141",
    )
    assert rec["error"] is None
    assert rec["tranches"] >= 2, "이 시나리오는 최소 1회 추가가 있어야 be_atr 경로가 실제로 쓰인다"
    assert rec["n_entry"] == _approx(n_entry_oracle)
    assert rec["virtual_R"] == _approx(oracle_live["virtual_R"]), (
        "어댑터가 조립한 be_atr 가 독립 오라클(live ATR)과 달라 배선이 의심된다"
    )
    assert rec["v_exit_kind"] == oracle_live["exit_kind"]


#: N8 — 진입 직후(D1) 첫 추가, 이어지는 TR 스파이크(D2, 세트선 위에 저가를 눌러 두어 조기
#: 청산을 피한다)로 live ATR 이 빠르게 변한다(D1→D2 값 485.75→531.2). D3 의 본전 임계는
#: `be_atr[d-1]`(정답 = be_seq[2]=531.2 → 임계 11,046.8)과 한 칸 밀린 값(be_seq[1]=485.75 →
#: 임계 10,978.6)이 hsb(D0..D2 최고가 10,995)를 사이에 두고 갈린다.
N8_POST = [
    (10_000, 10_100, 9_900, 10_000),      # D0 진입
    (10_100, 10_500, 10_050, 10_400),     # D1 추가① 10,500 → avg 10,250
    (10_400, 10_995, 9_600, 10_900),      # D2 TR 스파이크(저가 9,600 은 세트선 9,500 위)
    (10_900, 10_950, 10_200, 10_300),     # D3 — 저가 10,200, armed 이면 avg_breakeven 청산
]


async def test_n8_kojiro_adapter_be_atr_offset_matches_independent_oracle(monkeypatch):
    """N8 — `_compute_entry_atr` 가 조립하는 `be_seq` 가 §2-2 그대로(`series.iloc[len(window):]`,
    매수일부터 시퀀스)인지, 인덱스가 하루 밀린 시퀀스와 결과가 갈리는 픽스처로 확인한다.
    """
    import pandas as pd

    from src.engine.kojiro_indicators import atr as kojiro_atr

    start = D[0] + timedelta(days=60)  # 다른 테스트 날짜와 겹치지 않는 별도 달력
    dates = _bdays_from(start, len(N8_POST))
    target = dates[-1]
    pair = _pair("kojiro", "900142", dates[0], 10_000)
    rows = _series("900142", [500] * 120, N8_POST, post_dates=dates)
    _FakeDB([pair], {"900142": rows}).install(monkeypatch)

    asc = sorted(rows, key=lambda r: r["bas_dd"])
    entry_i = next(i for i, r in enumerate(asc) if r["bas_dd"] == dates[0])
    window = asc[max(0, entry_i - 100):entry_i]
    combined = window + asc[entry_i:]
    df = pd.DataFrame({
        "high": [float(r["high_price"]) for r in combined],
        "low": [float(r["low_price"]) for r in combined],
        "close": [float(r["close_price"]) for r in combined],
    })
    series = kojiro_atr(df, 20)
    n_entry_oracle = float(series.iloc[len(window) - 1])
    be_seq_oracle = [float(x) for x in series.iloc[len(window):].tolist()]
    be_seq_shifted = [n_entry_oracle] + be_seq_oracle[:-1]   # N8 이 만드는 한 칸 밀린 시퀀스

    ps = _ps()
    sim_bars = [
        (r["bas_dd"], float(r["open_price"]), float(r["high_price"]),
         float(r["low_price"]), float(r["close_price"]))
        for r in asc[entry_i:]
    ]
    no_add = ps.no_add_flags([b[0] for b in sim_bars])
    oracle_correct = ps.overlay_ladder(
        sim_bars, 0, 10_000.0, n_entry_oracle,
        cfg=ps.LADDER_C, stop_atr=2.0, hard_stop_pct=-8.0, be_mult=1.5,
        be_atr=be_seq_oracle, no_add=no_add, anchor_idx=None, anchor_price=None,
        anchor_add_allowed=True,
    )
    oracle_shifted = ps.overlay_ladder(
        sim_bars, 0, 10_000.0, n_entry_oracle,
        cfg=ps.LADDER_C, stop_atr=2.0, hard_stop_pct=-8.0, be_mult=1.5,
        be_atr=be_seq_shifted, no_add=no_add, anchor_idx=None, anchor_price=None,
        anchor_add_allowed=True,
    )
    assert oracle_correct["exit_kind"] != oracle_shifted["exit_kind"], (
        "이 픽스처는 오프셋 시프트로 결과가 안 갈린다 — 판별력이 없다"
    )

    rec = _rec(
        await _build(target, params_by_sid={"kojiro": KOJIRO_REG_PARAMS}),
        "kojiro", "900142",
    )
    assert rec["error"] is None
    assert rec["tranches"] >= 2
    assert rec["v_exit_kind"] == oracle_correct["exit_kind"], (
        "어댑터의 be_seq 오프셋이 한 칸 밀렸을 가능성 — 오라클(정렬)과 다르다"
    )


# ===========================================================================
# minor — 확정 못 한 청산(final=0)의 delta_R 기준 시점 불일치 (독립 검증 지적 #19)
# ===========================================================================
async def test_minor19_delta_r_is_none_when_not_final(monkeypatch):
    """지적 #19 — final=0 인 청산은 `actual_R`(실현 매도가 기준)과 `virtual_R`(앵커 없이
    마지막 봉 종가 기준)의 시점이 달라 `delta_R` 이 일봉 재현 오차와 사다리 효과를 뒤섞는다.
    final=0 이면 `delta_R=None` 으로 둔다(같은 기준 시점이 없을 때의 가장 단순하고 안전한 값)."""
    pair, rows = _donchian_closed_902()
    rows = [r for r in rows if r["bas_dd"] != T]  # 매도일 봉 없음 → final=0
    _FakeDB([pair], {"900202": rows}).install(monkeypatch)
    rec = _rec(await _build(T), "donchian_swing", "900202")
    assert rec["final"] == 0
    assert rec["delta_R"] is None
    assert rec["actual_R"] == _approx(1.7)      # 값 자체는 계속 계산(참고용)
    assert rec["virtual_R"] == _approx(2.0)


async def test_minor19_delta_r_still_set_when_final(monkeypatch):
    """대조군 — final=1(매도일 봉 확보)이면 delta_R 은 그대로 계산된다."""
    pair, rows = _donchian_closed_902()
    _FakeDB([pair], {"900202": rows}).install(monkeypatch)
    rec = _rec(await _build(T), "donchian_swing", "900202")
    assert rec["final"] == 1
    assert rec["delta_R"] == _approx(0.7)


# ===========================================================================
# minor — 보유(open) 판정을 실보유와 대조한다 (독립 검증 지적 #20)
# ===========================================================================
async def test_minor20_open_record_excluded_when_not_in_held_by_sid(monkeypatch):
    """지적 #20 — `get_trade_pairs` 의 순수량 open 페어가 실제 보유(`state.positions`)와
    어긋날 수 있다(부분체결·`momentum` 폴백 오귀속 등). 콜렉터가 넘기는 `held_by_sid` 에
    그 종목이 없으면 유령 open 레코드로 보고 제외한다. `held_by_sid` 를 아예 안 주면(그
    전략 키 자체가 없으면) 판정 불가로 보고 fail-open — 종전처럼 포함한다."""
    pair, rows = _donchian_open_901()
    _FakeDB([pair], {"900201": rows}).install(monkeypatch)

    excluded = await _build(T, held_by_sid={"donchian_swing": set()})
    assert {(r["strategy"], r["ticker"]) for r in excluded["records"]} == set()

    included_known = await _build(T, held_by_sid={"donchian_swing": {"900201"}})
    assert {(r["strategy"], r["ticker"]) for r in included_known["records"]} == {
        ("donchian_swing", "900201"),
    }

    included_unknown_sid = await _build(T, held_by_sid={"kojiro": set()})
    assert {(r["strategy"], r["ticker"]) for r in included_unknown_sid["records"]} == {
        ("donchian_swing", "900201"),
    }

    included_default = await _build(T)  # held_by_sid=None — 완전 fail-open
    assert {(r["strategy"], r["ticker"]) for r in included_default["records"]} == {
        ("donchian_swing", "900201"),
    }


async def test_minor20_closed_records_are_not_filtered_by_held_by_sid(monkeypatch):
    """청산 페어는 정의상 이제 보유가 아니므로 `held_by_sid` 필터 대상이 아니다(open 전용)."""
    pair, rows = _donchian_closed_902()
    _FakeDB([pair], {"900202": rows}).install(monkeypatch)
    out = await _build(T, held_by_sid={"donchian_swing": set()})
    assert {(r["strategy"], r["ticker"]) for r in out["records"]} == {
        ("donchian_swing", "900202"),
    }


# ===========================================================================
# D4 — summary.eligible_n 은 1주 랏(eligible=0)을 세지 않는다
# ===========================================================================
async def test_d4_eligible_n_excludes_one_share_lots(monkeypatch):
    """D4 — kojiro 예산 200,000 이면 `floor(2/3×200,000×0.005÷500)=1` → eligible=0. `eligible_n`
    은 이 레코드를 빼고 세야 한다(`eligible is not None` 로 재면 0 도 세어 2가 된다).
    """
    d_pair, d_rows = _donchian_open_901()
    k_pair, k_rows = _kojiro_open_101()
    _FakeDB([d_pair, k_pair], {"900201": d_rows, "900101": k_rows}).install(monkeypatch)
    out = await _build(T, budget_by_sid={"donchian_swing": 740_000, "kojiro": 200_000})
    assert _rec(out, "kojiro", "900101")["eligible"] == 0
    assert _rec(out, "donchian_swing", "900201")["eligible"] == 1
    assert out["summary"]["eligible_n"] == 1


# ===========================================================================
# R5 — 레코드 단위 compute 예외는 그 레코드만 격리한다(재전파 금지)
# ===========================================================================
async def test_r5_compute_exception_is_isolated_to_that_record_only(monkeypatch):
    """R5 — 레지스트리 파라미터가 비수치(`stop_atr: "x"`)면 `_build_record` 내부에서
    `float("x")` 가 TypeError/ValueError 를 던진다. 이 예외가 밖으로 새면(재전파) 한 종목
    때문에 셰도 전체가 날아간다 — 그 레코드만 `error` 로 남고 다른 레코드는 정상이어야 한다.
    """
    bad_pair, bad_rows = _kojiro_open_101()
    ok_pair, ok_rows = _donchian_open_901()
    _FakeDB([bad_pair, ok_pair], {"900101": bad_rows, "900201": ok_rows}).install(monkeypatch)
    out = await _build(T, params_by_sid={"kojiro": {**KOJIRO_REG_PARAMS, "stop_atr": "x"}})
    bad = _rec(out, "kojiro", "900101")
    assert isinstance(bad["error"], str) and bad["error"].startswith("compute_error:")
    ok = _rec(out, "donchian_swing", "900201")
    assert ok["error"] is None
    assert ok["virtual_R"] == _approx(2.4)
    assert out["summary"]["errors_n"] == 1


# ===========================================================================
# X9 — add_stage/add_macd 룩어헤드 금지(d 당일이 아니라 d−1 완성봉)
# ===========================================================================
def test_x9_add_stage_and_macd_use_d_minus_1_offset(monkeypatch):
    """X9 — `_compute_add_stage_macd` 가 읽는 오프셋은 `entry_idx_full + d_rel − 1`(전날
    완성봉) 이다. `kojiro_indicators.enrich` 를 인덱스마다 서로 다른(합성) 값으로 대체해
    정확히 그 인덱스를 읽는지 직접 확인한다 — 룩어헤드(§2-3 계약 위반)면 `pos` 가 하나씩
    밀려 여기서 잡힌다.
    """
    import pandas as pd

    import src.engine.kojiro_indicators as ki

    ps = _ps()
    n = 6
    fake_en = pd.DataFrame({
        "stage": list(range(n)),                    # 인덱스 = 값 그대로 — 오프셋 판별용
        "macd3": [float(i % 2) for i in range(n)],
        "macd3_sig": [0.5] * n,
    })
    monkeypatch.setattr(ki, "enrich", lambda df, cfg: fake_en)

    full_asc_rows = [{"high_price": 1, "low_price": 1, "close_price": 1} for _ in range(n)]
    entry_idx_full = 2
    add_fills = [(1, 100.0, 1.0), (2, 100.0, 1.0)]   # d_rel=1,2 → 정답 pos=2,3
    stages, macds = ps._compute_add_stage_macd(full_asc_rows, entry_idx_full, add_fills)
    assert stages == [2, 3], (
        f"오프셋이 entry_idx_full+d_rel−1(=[2,3]) 이 아니라 {stages} — 룩어헤드(당일 봉) 의심"
    )
    assert len(macds) == 2


# ===========================================================================
# X15 — 레코드 50개 상한은 "앞" 50개를 남긴다(뒤 50개 아님)
# ===========================================================================
async def test_x15_records_cap_keeps_the_first_fifty_not_the_last(monkeypatch):
    """X15 — 55개 입력 중 950000~950049(앞 50개) 가 남고 950050~950054(뒤 5개) 는 빠진다."""
    pairs, daily = [], {}
    for i in range(55):
        t = f"95{i:04d}"
        p, rows = _pair("donchian_swing", t, D[0], 10_000), _series(t, PRIOR_500, C1_POST)
        pairs.append(p)
        daily[t] = rows
    _FakeDB(pairs, daily).install(monkeypatch)
    out = await _build(T)
    tickers = sorted(r["ticker"] for r in out["records"])
    assert len(tickers) == 50
    assert tickers == sorted(f"95{i:04d}" for i in range(50)), tickers
    assert all(f"95{i:04d}" not in tickers for i in range(50, 55))


# ===========================================================================
# 콜렉터 배선 (§2-6) — A6 · A10 · A12
# ===========================================================================
def _install_fake_leaf(monkeypatch, fn):
    """leaf 의 `build_pyramid_shadow` 를 갈아 끼운다 — 콜렉터가 어떤 형태로 import 하든 잡히게 양쪽에."""
    ps = _ps()
    monkeypatch.setattr(ps, "build_pyramid_shadow", fn)
    monkeypatch.setattr(collector, "build_pyramid_shadow", fn, raising=False)


async def test_a6_get_trade_pairs_exception_nulls_only_the_shadow_key(monkeypatch):
    """A6 — `get_trade_pairs` 예외 → `"pyramid_shadow"` 만 None, 기존 10키는 골든과 같다(never-raise)."""
    golden = _load_golden()
    db = install_golden_inputs(monkeypatch)
    db.raise_pairs = True
    with freeze_time(FROZEN_T_2130_UTC):
        metrics = await collector.collect_daily_log_metrics(
            T, now_kst=datetime(2026, 10, 19, 21, 30, tzinfo=KST))
    assert "pyramid_shadow" in metrics, list(metrics)
    assert metrics["pyramid_shadow"] is None
    assert json.dumps(_ten(metrics), ensure_ascii=False) == json.dumps(golden["metrics"], ensure_ascii=False)


async def test_a6b_leaf_exception_nulls_only_the_shadow_key(monkeypatch):
    install_golden_inputs(monkeypatch)

    async def _boom(*a, **k):
        raise RuntimeError("leaf boom (cycle351 test)")

    _install_fake_leaf(monkeypatch, _boom)
    metrics = await collector.collect_daily_log_metrics(
        date(2026, 10, 16), now_kst=datetime(2026, 10, 16, 21, 30, tzinfo=KST))
    assert list(metrics) == EXPECTED_METRIC_KEYS
    assert metrics["pyramid_shadow"] is None
    assert metrics["api_metrics"] == {"total": 1234, "errors_5xx": 2, "by_path_5xx": {"/uapi/x": 2}}


async def test_minor_shadow_top_level_failure_emits_warning_once_per_day(monkeypatch, caplog):
    """지적(minor) — 셰도 전체 실패/타임아웃이 DEBUG 뿐이면 21:30 파이프라인이 그 밤 통째로
    `pyramid_shadow=None` 인 사실이 아무 데도 안 남는다. `observer_trace` 규약대로 WARNING
    1줄/일(같은 날 반복 실패는 추가 발화 없음)을 더한다 — DEBUG 흔적은 그대로 유지."""
    install_golden_inputs(monkeypatch)

    async def _boom(*a, **k):
        raise RuntimeError("leaf boom (cycle351 test)")

    _install_fake_leaf(monkeypatch, _boom)
    caplog.set_level(logging.DEBUG)
    d = date(2026, 10, 16)
    now = datetime(2026, 10, 16, 21, 30, tzinfo=KST)
    await collector.collect_daily_log_metrics(d, now_kst=now)
    await collector.collect_daily_log_metrics(d, now_kst=now)   # 같은 날 재호출 — 추가 WARNING 없음

    warn_lines = [r.getMessage() for r in caplog.records
                  if r.levelno >= logging.WARNING and "[pyramid_shadow_error]" in r.getMessage()]
    debug_lines = [r.getMessage() for r in caplog.records
                   if r.levelno == logging.DEBUG and r.getMessage().startswith("[pyramid_shadow_error]")]
    assert len(warn_lines) == 1, warn_lines
    assert len(debug_lines) == 2, "DEBUG 흔적은 매 실패마다(호출마다) 남아야 한다"


def test_a10_timeout_constant_is_30_seconds():
    """A10 — 21:30 파이프라인(LLM·INSERT)을 셰도가 붙잡지 못하게 하는 상한.

    ⚠️ 명세는 상수 이름을 정하지 않았다 — 테스트가 상한을 줄일 수 있게 `_PYRAMID_SHADOW_TIMEOUT_SECS`
    로 정했다(Red 보고에 적었다).
    """
    assert hasattr(collector, "_PYRAMID_SHADOW_TIMEOUT_SECS"), (
        "Red — log_metrics_collector 에 `_PYRAMID_SHADOW_TIMEOUT_SECS = 30.0` 부재 (§2-6)"
    )
    assert collector._PYRAMID_SHADOW_TIMEOUT_SECS == 30.0


async def test_a10b_slow_leaf_times_out_to_none_without_blocking(monkeypatch):
    """A10 — leaf 가 상한을 넘기면 그 키만 None. 상한을 0.05초로 줄여 빠르게 잰다(freezegun 금지)."""
    assert hasattr(collector, "_PYRAMID_SHADOW_TIMEOUT_SECS"), "Red — 상한 상수 부재 (§2-6)"
    install_golden_inputs(monkeypatch)
    started = asyncio.Event()

    async def _slow(*a, **k):
        started.set()
        await asyncio.sleep(10)
        return {"version": 1}

    _install_fake_leaf(monkeypatch, _slow)
    monkeypatch.setattr(collector, "_PYRAMID_SHADOW_TIMEOUT_SECS", 0.05)
    t0 = time.monotonic()
    metrics = await collector.collect_daily_log_metrics(
        date(2026, 10, 16), now_kst=datetime(2026, 10, 16, 21, 30, tzinfo=KST))
    elapsed = time.monotonic() - t0
    assert started.is_set(), "leaf 가 불리지 않았다"
    assert metrics["pyramid_shadow"] is None
    assert elapsed < 3.0, elapsed
    assert list(metrics) == EXPECTED_METRIC_KEYS


async def test_a12_collector_passes_copies_and_leaves_registry_untouched(monkeypatch):
    """A12 — 콜렉터는 `dict(config.params)` **사본**과 `int(total_investment)` 만 넘긴다(읽기만).

    가짜 leaf 가 받은 사본을 망가뜨려도 레지스트리의 params·state 는 호출 전과 같아야 한다.

    M2·M3 — `before_state = dict(vars(state))` 는 **얕은 복사**라 `positions`/`pending_buys`
    가 같은 객체를 가리켜, 콜렉터가 그 컨테이너를 제자리 변경(`state.pending_buys.add(...)`
    · `state.positions[...] = None`)해도 `dict(vars(state)) == before_state` 가 항상 참이었다
    (스칼라 재대입만 잡혔다). `copy.deepcopy` 로 뜨고 컨테이너 내용을 직접 단언한다.
    """
    import copy

    install_golden_inputs(monkeypatch)
    k_params = {"stop_atr": 2.0, "risk_pct": 0.005, "atr_period": 20}
    kojiro = _FakeStrat("kojiro", k_params, 1_980_000.7)
    kojiro.state.positions["900999"] = {"buy_price": 1.0}  # 표지 항목 — 오염 탐지 기준점
    kojiro.state.pending_buys.add("900998")
    kojiro.state.pending_buy_amounts["900997"] = 12345
    _install_registry(monkeypatch, [kojiro])          # donchian 미등록(부재)
    before_params = dict(kojiro.config.params)
    before_state = copy.deepcopy(vars(kojiro.state))
    seen: dict = {}
    sentinel = {"version": 1, "target_date": "2026-10-16", "ladder": {}, "summary": {}, "records": []}

    async def _spy(target_date, *, params_by_sid, budget_by_sid, held_by_sid=None, now_kst=None):
        seen.update(target_date=target_date, params=params_by_sid, budget=budget_by_sid)
        if isinstance(params_by_sid.get("kojiro"), dict):
            params_by_sid["kojiro"]["stop_atr"] = 99.0      # 사본이면 레지스트리 무영향
            params_by_sid["kojiro"]["injected"] = True
        return sentinel

    _install_fake_leaf(monkeypatch, _spy)
    metrics = await collector.collect_daily_log_metrics(
        date(2026, 10, 16), now_kst=datetime(2026, 10, 16, 21, 30, tzinfo=KST))

    assert metrics["pyramid_shadow"] == sentinel
    assert seen["target_date"] == date(2026, 10, 16)
    assert seen["budget"].get("kojiro") == 1_980_000 and isinstance(seen["budget"]["kojiro"], int)
    assert seen["params"].get("donchian_swing") is None
    assert seen["budget"].get("donchian_swing") is None
    assert kojiro.config.params == before_params, "레지스트리 params 가 바뀌었다 — 사본이 아니다"
    # 컨테이너 내용을 직접 단언(딥카피 기준) — M2·M3 가 여기서 잡힌다.
    assert kojiro.state.positions == before_state["positions"]
    assert kojiro.state.pending_buys == before_state["pending_buys"]
    assert kojiro.state.pending_buy_amounts == before_state["pending_buy_amounts"]
    assert kojiro.state.total_investment == before_state["total_investment"]
