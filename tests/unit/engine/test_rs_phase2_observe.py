"""RS 2단계 Red — `src/engine/rs_fundamental_observe.py` 부팅 관찰 기록 (매매 행위 0).

명세 = `_workspace/design/2026-10-13_rs_fundamental_phase2.md` §B.

명세 해석 가정(구현이 따를 계약 — 바뀌면 이 머리말과 `Env` 만 고친다):
- 공개 = `spawn_boot_observe(scheduler) -> asyncio.Task | None`(일반 def, 루프 없으면 None·예외 없음).
  상수 `WAIT_PREPARE_SECS = 600` · `PREPARE_POLL_SECS = 10`(명세 「10초 간격」의 이름 — 테스트가 줄인다)
  · `RUN_TIMEOUT_SECS = 300` · `TARGET_STRATEGIES = ("donchian_swing", "vcp_breakout", "kojiro", "etf_trend")`.
- 레지스트리 = `scheduler.registry` (`get`/`all`/`enabled`). 켜짐 = `strategy.config.enabled`.
- prepare 완료 = `_live_prepare_meta` 가 dict 이고 `ok is True ∧ phase == "boot"`.
- 후보 = `strategy.get_scanned_tickers()`(`_candidates` 를 직접 읽지 않는다) · 보유 = `strategy.state.positions` 키.
  둘 다인 종목은 1행 `role="held"`.
- 입력(모듈 속성 경유 — 이 테스트가 원 모듈 속성을 바꾼다):
  `src.db.score_inputs.recent_closes_bulk(before=오늘, n=200)` · `score_inputs.master_raw_map(tickers)`
  · `score_inputs.financial_rows_bulk(tickers)`(분기 `div_cls="1"`·연간 `"0"` 행, 칸 = DB 칸 이름)
  · `src.db.invest_opinion.get_opinions(ticker, 오늘−400일, 오늘−1일)`
  · 쓰기 `src.db.candidate_scores.upsert_scores(rows)` **1회**(전 전략 행을 한 번에)
  · 킬스위치 `src.db.system_config._select_value("rs_fundamental_observe_mode")`(`{"value": str}`).
- 재무 칸 원천: 영업이익 = `bsop_prti` · 매출 = `sale_account` · 순이익 = `thtr_ntin` · 부채비율 = `lblt_rate`(연간)
  · ROE = `master_raw["roe"]`(숫자로 읽히면). 분기는 연초 누적 → `quarterly_from_cumulative` 로 단독값.
- 행 = dict(키 = migration 052 칸 이름 전부). 결측 = None(0 금지). `target_date` = 오늘(KST), `computed_at` = aware datetime.
"""
from __future__ import annotations

import asyncio
import copy
import logging
import math
from datetime import date, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import src.db.invest_opinion as io_db
import src.db.system_config as sc_db
from src.db._kst import today_kst
from src.engine import fundamental_score as fs
from src.engine import rs_fundamental_observe as rfo
from src.engine import rs_score
from src.engine.strategies.kojiro import _kojiro_sector_key

pytestmark = pytest.mark.unit

MODE_KEY = "rs_fundamental_observe_mode"
COLUMNS = (
    "target_date", "strategy_id", "ticker", "role",
    "rs_raw", "rs_pct", "sector_key", "vs_sector", "sector_pct", "in_sector_pct",
    "revision_breadth", "target_median_change", "opinion_brokers",
    "fin_quarter", "op_income_q", "op_income_q_yoy", "op_turnaround", "op_yoy_growth",
    "revenue_yoy_growth", "net_turnaround", "roe", "debt_ratio_latest", "debt_ratio_down_years",
    "ttm_op_to_max_ratio", "rs_population", "computed_at",
)
FIN_COLS = (
    "fin_quarter", "op_income_q", "op_income_q_yoy", "op_turnaround", "op_yoy_growth",
    "revenue_yoy_growth", "net_turnaround", "roe", "debt_ratio_latest", "debt_ratio_down_years",
    "ttm_op_to_max_ratio",
)
TARGET_COLS = ("revision_breadth", "target_median_change", "opinion_brokers")
RS_COLS = ("rs_raw", "rs_pct", "vs_sector", "sector_pct", "in_sector_pct")
TODAY = today_kst()
YESTERDAY = TODAY - timedelta(days=1)


def test_constants():
    assert rfo.WAIT_PREPARE_SECS == 600
    assert rfo.PREPARE_POLL_SECS == 10
    assert rfo.RUN_TIMEOUT_SECS == 300
    assert tuple(rfo.TARGET_STRATEGIES) == ("donchian_swing", "vcp_breakout", "kojiro", "etf_trend")


# ---------------------------------------------------------------------------
# 가짜 전략·레지스트리
# ---------------------------------------------------------------------------
class FakeStrategy:
    def __init__(self, sid, *, enabled=True, scanned=(), held=(), meta="ok"):
        self.__dict__["setattr_log"] = []
        self.strategy_id = sid
        self.config = SimpleNamespace(enabled=enabled, weight=0.1, params={})
        self.state = SimpleNamespace(positions={t: SimpleNamespace(ticker=t, quantity=3) for t in held})
        self._scanned = list(scanned)
        # get_scanned_tickers 와 다른 내용 — 구현이 _candidates 를 직접 읽으면 777770 행이 생긴다
        self._candidates = {t: {"ticker": t} for t in [*scanned, "777770"]}
        if meta == "ok":
            meta = {"ok": True, "phase": "boot", "as_of": TODAY}
        self._live_prepare_meta = meta
        self.__dict__["_frozen"] = True

    def __setattr__(self, key, value):
        if self.__dict__.get("_frozen"):
            self.__dict__["setattr_log"].append(key)
        self.__dict__[key] = value

    def get_scanned_tickers(self):
        return list(self._scanned)

    def snapshot(self):
        return copy.deepcopy((self._candidates, self.state.positions, self._live_prepare_meta,
                              self._scanned, vars(self.config)))


class FakeRegistry:
    def __init__(self, strategies):
        self._s = {s.strategy_id: s for s in strategies}

    def get(self, sid):
        return self._s.get(sid)

    def all(self):
        return list(self._s.values())

    def enabled(self):
        return [s for s in self._s.values() if s.config.enabled]


# ---------------------------------------------------------------------------
# 입력 데이터
# ---------------------------------------------------------------------------
_SECTOR = ["000010", "000020", "000030", "000040", "000050", "000060"]  # 반도체 6 (≥5)
_OTHERS = ["000070", "000080"]  # 미분류


def _closes(k: int, n: int = 200) -> list[float]:
    g = 0.0005 * (k + 1) * (1 if k % 2 == 0 else -1) + 0.0002 * k
    return [100.0 * (1.0 + g) ** i for i in range(n)]


CLOSES = {t: _closes(i) for i, t in enumerate(_SECTOR + _OTHERS)}
CLOSES["000090"] = _closes(9, n=150)  # 190봉 미만 → RS 없음

MASTER = {t: {"krx_smcn_yn": "Y"} for t in _SECTOR}
MASTER["000010"] = {"krx_smcn_yn": "Y", "roe": "12.5"}
MASTER["000070"] = {"roe": "8.0"}


def _q(stac, div, **v):
    return {"stac_yymm": stac, "div_cls": div, **v}


FIN_ROWS = [
    # 분기(연초 누적) — 2023: 50/110/180/260 · 2024: 10/5/35/75 · 2025: 20/50
    _q("202303", "1", bsop_prti=50, sale_account=100, thtr_ntin=5),
    _q("202306", "1", bsop_prti=110, sale_account=200, thtr_ntin=10),
    _q("202309", "1", bsop_prti=180, sale_account=300, thtr_ntin=15),
    _q("202312", "1", bsop_prti=260, sale_account=400, thtr_ntin=20),
    _q("202403", "1", bsop_prti=10, sale_account=100, thtr_ntin=5),
    _q("202406", "1", bsop_prti=5, sale_account=200, thtr_ntin=3),
    _q("202409", "1", bsop_prti=35, sale_account=300, thtr_ntin=8),
    _q("202412", "1", bsop_prti=75, sale_account=400, thtr_ntin=12),
    _q("202503", "1", bsop_prti=20, sale_account=120, thtr_ntin=4),
    _q("202506", "1", bsop_prti=50, sale_account=250, thtr_ntin=10),
    _q("209906", "1", bsop_prti=99999, sale_account=99999, thtr_ntin=99999),  # 미래 = 그때 알 수 없던 값
    # 연간
    _q("202212", "0", lblt_rate=80.0),
    _q("202312", "0", lblt_rate=70.0),
    _q("202412", "0", lblt_rate=75.0),
    _q("202512", "0", lblt_rate=60.0),
    _q("209912", "0", lblt_rate=1.0),  # 미래
]
FIN = {"000010": [dict(r, ticker="000010") for r in FIN_ROWS],
       "000070": [dict(r, ticker="000070") for r in FIN_ROWS]}

EXPECTED_FIN_000010 = {
    "fin_quarter": "202506", "op_income_q": 30.0, "op_income_q_yoy": -5.0,
    "op_turnaround": True, "op_yoy_growth": None, "revenue_yoy_growth": 0.3,
    "net_turnaround": True, "roe": 12.5, "debt_ratio_latest": 60.0, "debt_ratio_down_years": 1,
    "ttm_op_to_max_ratio": 120.0 / 260.0,
}


def _op(days_ago, broker, goal):
    return {"ticker": "x", "bsop_date": YESTERDAY - timedelta(days=days_ago), "mbcr_name": broker,
            "hts_goal_prc": goal, "invt_opnn": "매수"}


OPINIONS = {
    "000010": [_op(2, "SK", 120000), _op(15, "SK", 100000),
               _op(3, "KB", 90000), _op(20, "KB", 95000),
               _op(5, "NH", 110000)],
    "000070": [_op(2, "SK", 120000), _op(15, "SK", 100000)],
}


class Env:
    def __init__(self, monkeypatch, strategies, *, config=None):
        import src.db.candidate_scores as cs_db  # noqa: PLC0415 — 없으면 Red
        import src.db.score_inputs as si_db  # noqa: PLC0415

        self.registry = FakeRegistry(strategies)
        self.scheduler = SimpleNamespace(registry=self.registry)
        self.config = dict(config or {})
        self.closes = AsyncMock(side_effect=self._closes)
        self.master = AsyncMock(side_effect=lambda tickers: {t: MASTER[t] for t in tickers if t in MASTER})
        self.fin = AsyncMock(side_effect=lambda tickers: {t: FIN[t] for t in tickers if t in FIN})
        self.opinions = AsyncMock(side_effect=lambda t, a, b: list(OPINIONS.get(t, [])))
        self.upsert = AsyncMock(side_effect=lambda rows: len(list(rows)))
        mp = monkeypatch
        mp.setattr(si_db, "recent_closes_bulk", self.closes, raising=False)
        mp.setattr(si_db, "master_raw_map", self.master, raising=False)
        mp.setattr(si_db, "financial_rows_bulk", self.fin, raising=False)
        mp.setattr(io_db, "get_opinions", self.opinions)
        mp.setattr(cs_db, "upsert_scores", self.upsert, raising=False)
        mp.setattr(sc_db, "_select_value", self._select)
        mp.setattr(rfo, "WAIT_PREPARE_SECS", 0.3)
        mp.setattr(rfo, "PREPARE_POLL_SECS", 0.01, raising=False)

    async def _closes(self, before, n=200):
        return {t: list(c) for t, c in CLOSES.items()}

    async def _select(self, key):
        return self.config.get(key, sc_db._MISSING)

    async def run(self, timeout=5.0):
        task = rfo.spawn_boot_observe(self.scheduler)
        assert isinstance(task, asyncio.Task), f"spawn 은 Task 를 돌려준다: {task!r}"
        await asyncio.wait_for(task, timeout)
        assert task.exception() is None
        return task

    def rows(self):
        assert self.upsert.await_count == 1, f"쓰기 1회 (실측 {self.upsert.await_count})"
        return list(self.upsert.await_args.args[0])


def _default_strategies():
    return [
        FakeStrategy("donchian_swing", scanned=["000010", "000020", "999990"], held=["000030", "000020"]),
        FakeStrategy("vcp_breakout", scanned=["000040"]),
        FakeStrategy("kojiro", enabled=False, scanned=["000050"]),
        FakeStrategy("etf_trend", scanned=["000070"]),
        FakeStrategy("momentum", scanned=["000080"]),
    ]


def _by(rows):
    return {(r["strategy_id"], r["ticker"]): r for r in rows}


def _close(a, b):
    if a is None or b is None:
        return a is b
    if isinstance(b, bool) or isinstance(a, bool):
        return a is b
    if isinstance(b, (int, float)):
        return math.isclose(float(a), float(b), rel_tol=1e-9, abs_tol=1e-12)
    return a == b


# ---------------------------------------------------------------------------
# 대상 · 행 구성
# ---------------------------------------------------------------------------
async def test_rows_cover_enabled_target_strategies_only_with_roles(monkeypatch):
    env = Env(monkeypatch, _default_strategies())
    await env.run()
    rows = _by(env.rows())
    assert set(rows) == {
        ("donchian_swing", "000010"), ("donchian_swing", "000020"), ("donchian_swing", "999990"),
        ("donchian_swing", "000030"), ("vcp_breakout", "000040"), ("etf_trend", "000070"),
    }, sorted(rows)
    assert rows[("donchian_swing", "000010")]["role"] == "candidate"
    assert rows[("donchian_swing", "000030")]["role"] == "held"
    assert rows[("donchian_swing", "000020")]["role"] == "held", "후보∩보유 = held 1행"
    for r in rows.values():
        assert set(COLUMNS) <= set(r), set(COLUMNS) - set(r)
        assert r["target_date"] == TODAY
        assert isinstance(r["computed_at"], datetime) and r["computed_at"].tzinfo is not None


async def test_rs_and_sector_match_phase1_pure_functions(monkeypatch):
    env = Env(monkeypatch, _default_strategies())
    await env.run()
    rows = _by(env.rows())
    kw = env.closes.await_args
    got_before = kw.kwargs.get("before", kw.args[0] if kw.args else None)
    assert got_before == TODAY, "bas_dd < 오늘"
    assert kw.kwargs.get("n", kw.args[1] if len(kw.args) > 1 else 200) == 200

    scores = {t: rs_score.ibd_lite_return(c) for t, c in CLOSES.items()}
    pct = rs_score.percentile_ranks(scores)
    sector_of = {t: _kojiro_sector_key(MASTER.get(t), t) for t in CLOSES}
    rel = rs_score.sector_relative(scores, sector_of)
    population = sum(v is not None for v in scores.values())
    for (sid, t), r in rows.items():
        assert r["rs_population"] == population, (sid, t, r["rs_population"])
        if t not in CLOSES:
            continue
        assert _close(r["rs_raw"], scores[t]), (t, r["rs_raw"], scores[t])
        assert r["rs_pct"] == pct[t], (t, r["rs_pct"], pct[t])
        assert r["sector_key"] == sector_of[t]
        for c in ("vs_sector", "sector_pct", "in_sector_pct"):
            assert _close(r[c], rel[t][c]), (t, c, r[c], rel[t][c])
    assert rows[("donchian_swing", "000010")]["sector_pct"] is not None, "반도체 6종목 = 섹터 자격"


async def test_target_revision_matches_phase1_and_dates(monkeypatch):
    env = Env(monkeypatch, _default_strategies())
    await env.run()
    rows = _by(env.rows())
    r = rows[("donchian_swing", "000010")]
    ops = OPINIONS["000010"]
    assert _close(r["revision_breadth"], fs.target_revision_breadth(ops, YESTERDAY))
    assert _close(r["target_median_change"], fs.target_median_change(ops, YESTERDAY))
    assert r["opinion_brokers"] == 3
    calls = [c for c in env.opinions.await_args_list if c.args and c.args[0] == "000010"]
    assert calls, "목표가 입력 = get_opinions(ticker, …)"
    assert calls[0].args[1] == TODAY - timedelta(days=400) and calls[0].args[2] == YESTERDAY


async def test_fundamentals_from_known_as_of_quarters(monkeypatch):
    env = Env(monkeypatch, _default_strategies())
    await env.run()
    r = _by(env.rows())[("donchian_swing", "000010")]
    for c, want in EXPECTED_FIN_000010.items():
        assert _close(r[c], want), f"{c}: {r[c]!r} != {want!r}"


async def test_etf_trend_fin_and_target_are_null_but_rs_kept(monkeypatch):
    env = Env(monkeypatch, _default_strategies())
    await env.run()
    r = _by(env.rows())[("etf_trend", "000070")]
    for c in (*FIN_COLS, *TARGET_COLS):
        assert r[c] is None, f"etf_trend {c} 는 NULL (실측 {r[c]!r})"
    assert r["rs_raw"] is not None and r["rs_pct"] is not None, "RS 는 같은 전역 모집단 백분위"


async def test_missing_inputs_are_null_not_zero(monkeypatch):
    env = Env(monkeypatch, _default_strategies())
    await env.run()
    rows = _by(env.rows())
    r = rows[("donchian_swing", "999990")]
    for c in (*RS_COLS, *FIN_COLS, *TARGET_COLS):
        assert r[c] is None, f"모름 = NULL — {c}={r[c]!r}"
    r2 = rows[("vcp_breakout", "000040")]
    for c in (*FIN_COLS, *TARGET_COLS):
        assert r2[c] is None, f"{c}={r2[c]!r}"


# ---------------------------------------------------------------------------
# prepare 대기
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "meta",
    [None, {"ok": None, "phase": "boot"}, {"ok": False, "phase": "boot"}, {"ok": True, "phase": "evening"}],
    ids=["no_meta", "in_progress", "failed", "evening_phase"],
)
async def test_prepare_not_done_strategy_skipped(monkeypatch, caplog, meta):
    strategies = _default_strategies()
    strategies[1] = FakeStrategy("vcp_breakout", scanned=["000040"], meta=meta)
    env = Env(monkeypatch, strategies)
    with caplog.at_level(logging.DEBUG):
        await env.run()
    sids = {r["strategy_id"] for r in env.rows()}
    assert "vcp_breakout" not in sids and "donchian_swing" in sids
    msgs = [r.getMessage() for r in caplog.records]
    assert any("[rs_observe]" in m and "strategy=vcp_breakout" in m and "skipped=prepare_not_done" in m
               for m in msgs), msgs


async def test_waits_until_prepare_finishes(monkeypatch):
    strategies = _default_strategies()
    late = FakeStrategy("vcp_breakout", scanned=["000040"], meta={"ok": None, "phase": "boot"})
    strategies[1] = late
    env = Env(monkeypatch, strategies)

    async def _finish_later():
        await asyncio.sleep(0.08)
        late._live_prepare_meta["ok"] = True

    finisher = asyncio.create_task(_finish_later())
    await env.run()
    await finisher
    assert "vcp_breakout" in {r["strategy_id"] for r in env.rows()}, "10초 간격으로 다시 본다"


# ---------------------------------------------------------------------------
# 마커 · 킬스위치 · never-raise · 불변
# ---------------------------------------------------------------------------
async def test_marker_one_info_line_per_strategy(monkeypatch, caplog):
    env = Env(monkeypatch, _default_strategies())
    with caplog.at_level(logging.DEBUG):
        await env.run()
    lines = [r for r in caplog.records
             if r.getMessage().startswith("[rs_observe] ") and "skipped=" not in r.getMessage()]
    by_sid = {}
    for r in lines:
        for sid in ("donchian_swing", "vcp_breakout", "etf_trend", "kojiro", "momentum"):
            if f"strategy={sid}" in r.getMessage():
                by_sid.setdefault(sid, []).append(r)
    assert set(by_sid) == {"donchian_swing", "vcp_breakout", "etf_trend"}, sorted(by_sid)
    for sid, recs in by_sid.items():
        assert len(recs) == 1 and recs[0].levelno == logging.INFO
        msg = recs[0].getMessage()
        for f in ("candidates=", "held=", "rs_known=", "fin_known=", "opinion_known=",
                  "rs_population=", "elapsed_ms="):
            assert f in msg, (sid, f, msg)
    don = by_sid["donchian_swing"][0].getMessage()
    assert "held=2" in don


async def test_killswitch_off_does_nothing(monkeypatch):
    strategies = _default_strategies()
    env = Env(monkeypatch, strategies, config={MODE_KEY: {"value": "off"}})
    task = rfo.spawn_boot_observe(env.scheduler)
    if task is not None:
        await asyncio.wait_for(task, 5)
    assert env.upsert.await_count == 0
    assert env.closes.await_count == 0


async def test_killswitch_missing_means_record(monkeypatch):
    env = Env(monkeypatch, _default_strategies())
    await env.run()
    assert env.upsert.await_count == 1


async def test_killswitch_typo_means_record_with_warning(monkeypatch, caplog):
    env = Env(monkeypatch, _default_strategies(), config={MODE_KEY: {"value": "recrod"}})
    with caplog.at_level(logging.DEBUG):
        await env.run()
    assert env.upsert.await_count == 1
    assert any(r.levelno == logging.WARNING and MODE_KEY in r.getMessage() for r in caplog.records)


@pytest.mark.parametrize("stage", ["closes", "master", "fin", "opinions", "upsert", "config"])
async def test_never_raise_on_input_failure(monkeypatch, caplog, stage):
    env = Env(monkeypatch, _default_strategies())
    boom = RuntimeError(f"{stage} down")
    if stage == "closes":
        env.closes.side_effect = boom
    elif stage == "master":
        env.master.side_effect = boom
    elif stage == "fin":
        env.fin.side_effect = boom
    elif stage == "opinions":
        env.opinions.side_effect = boom
    elif stage == "upsert":
        env.upsert.side_effect = boom
    else:
        async def _boom(key):
            raise boom
        monkeypatch.setattr(sc_db, "_select_value", _boom)
    with caplog.at_level(logging.DEBUG):
        task = rfo.spawn_boot_observe(env.scheduler)
        if task is not None:
            await asyncio.wait_for(task, 5)
            assert task.exception() is None
    if stage != "config":
        assert any(r.levelno == logging.WARNING and r.getMessage().startswith("[rs_observe_failed] stage=")
                   for r in caplog.records), [r.getMessage() for r in caplog.records]


async def test_run_timeout_bounds_compute(monkeypatch):
    env = Env(monkeypatch, _default_strategies())

    async def _hang(before, n=200):
        await asyncio.sleep(30)
        return {}

    env.closes.side_effect = _hang
    monkeypatch.setattr(rfo, "RUN_TIMEOUT_SECS", 0.1)
    task = rfo.spawn_boot_observe(env.scheduler)
    await asyncio.wait_for(task, 3)
    assert task.exception() is None


async def test_strategy_objects_unchanged(monkeypatch):
    strategies = _default_strategies()
    before = {s.strategy_id: s.snapshot() for s in strategies}
    env = Env(monkeypatch, strategies)
    await env.run()
    for s in strategies:
        assert s.snapshot() == before[s.strategy_id], f"{s.strategy_id} 상태가 바뀌었다"
        assert s.setattr_log == [], f"{s.strategy_id} 에 속성 대입: {s.setattr_log}"


def test_spawn_without_running_loop_returns_none():
    sched = SimpleNamespace(registry=FakeRegistry(_default_strategies()))
    assert rfo.spawn_boot_observe(sched) is None


async def test_spawn_with_broken_scheduler_never_raises(monkeypatch):
    async def _missing(key):
        return sc_db._MISSING

    monkeypatch.setattr(sc_db, "_select_value", _missing)
    monkeypatch.setattr(rfo, "WAIT_PREPARE_SECS", 0.3)
    task = rfo.spawn_boot_observe(object())
    if task is not None:
        await asyncio.wait_for(task, 5)
        assert task.exception() is None
