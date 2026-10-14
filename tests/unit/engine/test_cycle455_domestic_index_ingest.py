"""cycle455 — 종합지수 적재 leaf · KIS 래퍼 · 배선.

명세 = `_workspace/red/cycle455_market_unit_by_market_spec.md` §3.3~§3.5 · §7.

| # | 계약 |
|---|---|
| I1 | 행 부족(< 130) → 과거로 내려가는 history 경로 · 충분 → `max_bas_dd − 7일` 증분 |
| I2 | 15:40 KST 전이면 오늘 봉을 버린다 · 15:40 뒤면 남긴다 |
| I3 | KIS 예외는 그 시장만 실패로 세고 흡수 · 요약 마커 WARNING · 다른 시장은 진행 |
| K1 | `fetch_index_daily` — 0 이하·비수치·날짜 불량 버림 · 오름차순 · 중복 제거 · 파라미터 |
| K2 | `fetch_index_daily_history` — 50봉 창을 과거로 · min_rows 채우면 멈춤 · 0행이면 멈춤 · 상한 6회 |
| K3 | path 가 `_QUOTE_ALLOWED_PATHS` 에 있다 |
| W1 | 부팅 = `ensure_fresh(phase="boot")` 가 `wait_for_boot` 앞 · `emit_daily_head_staleness` 앞 · 상한 대기 |
| W2 | 저녁 = 일봉 적재 뒤 지수 적재 · 일봉 예외여도 지수 적재 후 재발생 · 요약은 일봉 것 |
"""
from __future__ import annotations

import ast
import inspect
import logging
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

KST = timezone(timedelta(hours=9))
TODAY = date(2026, 10, 15)


class _DB:
    def __init__(self, counts):
        self.counts = dict(counts)
        self.upserts: list[tuple] = []

    async def count(self, code):
        return self.counts.get(code, 0)

    async def max_bas_dd(self, code):
        return date(2026, 10, 13) if self.counts.get(code) else None

    async def upsert_many(self, code, rows, **k):
        self.upserts.append((code, list(rows)))
        return len(rows)


class _API:
    def __init__(self, rows=None, exc_codes=()):
        self.rows = rows or [("20261013", 2500.0), ("20261014", 2510.0), ("20261015", 2520.0)]
        self.exc_codes = set(exc_codes)
        self.calls: list[tuple] = []

    async def fetch_index_daily(self, code, start, end):
        self.calls.append(("inc", code, start, end))
        if code in self.exc_codes:
            raise RuntimeError("kis 500")
        return list(self.rows)

    async def fetch_index_daily_history(self, code, end, min_rows):
        self.calls.append(("hist", code, end, min_rows))
        if code in self.exc_codes:
            raise RuntimeError("kis 500")
        return list(self.rows)


def _install(monkeypatch, db, api):
    import src.api.domestic_index as A
    import src.db.domestic_index as D

    for n in ("count", "max_bas_dd", "upsert_many"):
        monkeypatch.setattr(D, n, getattr(db, n))
    for n in ("fetch_index_daily", "fetch_index_daily_history"):
        monkeypatch.setattr(A, n, getattr(api, n))


@pytest.mark.real_domestic_index_ingest
async def test_i1_history_when_short_incremental_when_enough(monkeypatch):
    from src.engine import domestic_index_ingest as ing

    db, api = _DB({"0001": 200, "1001": 10}), _API()
    _install(monkeypatch, db, api)
    await ing.ensure_fresh(phase="boot", now_kst=datetime(2026, 10, 15, 20, 31, tzinfo=KST))
    kinds = {(c[0], c[1]) for c in api.calls}
    assert kinds == {("inc", "0001"), ("hist", "1001")}
    inc = next(c for c in api.calls if c[0] == "inc")
    assert inc[2] == date(2026, 10, 13) - timedelta(days=7) and inc[3] == TODAY
    hist = next(c for c in api.calls if c[0] == "hist")
    assert hist[3] == ing.TARGET_ROWS == 130


@pytest.mark.real_domestic_index_ingest
async def test_i2_drop_today_bar_before_1540(monkeypatch):
    from src.engine import domestic_index_ingest as ing

    db, api = _DB({"0001": 200, "1001": 200}), _API()
    _install(monkeypatch, db, api)
    await ing.ensure_fresh(phase="boot", now_kst=datetime(2026, 10, 15, 7, 50, tzinfo=KST))
    assert all("20261015" not in [r[0] for r in rows] for _, rows in db.upserts)
    db2 = _DB({"0001": 200, "1001": 200})
    _install(monkeypatch, db2, _API())
    await ing.ensure_fresh(phase="evening", now_kst=datetime(2026, 10, 15, 20, 31, tzinfo=KST))
    assert all("20261015" in [r[0] for r in rows] for _, rows in db2.upserts)


@pytest.mark.real_domestic_index_ingest
async def test_i3_kis_exception_absorbed_per_market(monkeypatch, caplog):
    from src.engine import domestic_index_ingest as ing

    caplog.set_level(logging.INFO, logger="src.engine.domestic_index_ingest")
    db, api = _DB({"0001": 200, "1001": 200}), _API(exc_codes={"1001"})
    _install(monkeypatch, db, api)
    out = await ing.ensure_fresh(phase="boot", now_kst=datetime(2026, 10, 15, 20, 31, tzinfo=KST))
    assert out["failed"] == 1 and [c for c, _ in db.upserts] == ["0001"]
    summary = [r for r in caplog.records if r.getMessage().startswith("[domestic_index_ingest] phase=boot")]
    assert len(summary) == 1 and summary[0].levelno == logging.WARNING
    assert "failed=1" in summary[0].getMessage() and "kosdaq_rows=-" in summary[0].getMessage()


async def test_k1_fetch_index_daily_parses_and_sorts(monkeypatch):
    import src.api.domestic_index as A

    seen = {}

    async def fake(path, tr_id, params=None, **k):
        seen.update(path=path, tr_id=tr_id, params=params)
        return {"output2": [
            {"stck_bsop_date": "20261014", "bstp_nmix_prpr": "2510.55"},
            {"stck_bsop_date": "20261013", "bstp_nmix_prpr": "2500"},
            {"stck_bsop_date": "20261013", "bstp_nmix_prpr": "2501"},     # 중복 — 뒤 값
            {"stck_bsop_date": "20261012", "bstp_nmix_prpr": "0"},        # 0 이하
            {"stck_bsop_date": "2026101", "bstp_nmix_prpr": "1"},         # 날짜 불량
            {"stck_bsop_date": "20261011", "bstp_nmix_prpr": "abc"},      # 비수치
            "garbage",
        ]}

    monkeypatch.setattr(A, "kis_get_quote", fake)
    out = await A.fetch_index_daily("1001", date(2026, 9, 1), date(2026, 10, 14))
    assert out == [("20261013", 2501.0), ("20261014", 2510.55)]
    assert seen["path"] == A.PATH and seen["tr_id"] == "FHKUP03500100"
    assert seen["params"] == {"FID_COND_MRKT_DIV_CODE": "U", "FID_INPUT_ISCD": "1001",
                              "FID_INPUT_DATE_1": "20260901", "FID_INPUT_DATE_2": "20261014",
                              "FID_PERIOD_DIV_CODE": "D"}


def _bars(end: date, n: int) -> list[tuple[str, float]]:
    out, d = [], end
    while len(out) < n:
        if d.weekday() < 5:
            out.append((d.strftime("%Y%m%d"), 1000.0 + len(out)))
        d -= timedelta(days=1)
    return sorted(out)


async def test_k2_history_pages_back_until_min_rows(monkeypatch):
    import src.api.domestic_index as A

    calls = []

    async def fake_daily(code, start, end):
        calls.append(end)
        return _bars(end, 50)

    async def no_sleep(_s):
        return None

    monkeypatch.setattr(A, "fetch_index_daily", fake_daily)
    monkeypatch.setattr(A.asyncio, "sleep", no_sleep)
    out = await A.fetch_index_daily_history("0001", TODAY, 130)
    assert len(out) >= 130 and out == sorted(out) and len(calls) == 3
    assert calls[1] < calls[0] and calls[2] < calls[1], "창이 과거로 내려간다"

    calls.clear()

    async def empty(code, start, end):
        calls.append(end)
        return []

    monkeypatch.setattr(A, "fetch_index_daily", empty)
    assert await A.fetch_index_daily_history("0001", TODAY, 130) == [] and len(calls) == 1

    calls.clear()

    async def same(code, start, end):            # 매번 같은 봉 — 진전 없으면 멈춘다
        calls.append(end)
        return _bars(TODAY, 50)

    monkeypatch.setattr(A, "fetch_index_daily", same)
    await A.fetch_index_daily_history("0001", TODAY, 130)
    assert len(calls) == 2 <= A.HISTORY_MAX_CALLS


def test_k3_path_in_quote_allowlist():
    from src.api import base, domestic_index

    assert domestic_index.PATH in base._QUOTE_ALLOWED_PATHS


def _boot_stmts():
    from src.engine import boot_manager

    tree = ast.parse(inspect.getsource(boot_manager.boot))
    fn = tree.body[0]
    return [ast.unparse(s) for s in fn.body]


def test_w1_boot_ingest_before_wait_and_head_observer():
    stmts = _boot_stmts()
    i_ing = next(i for i, s in enumerate(stmts) if "domestic_index_ingest.ensure_fresh(phase='boot')" in s)
    i_wait = next(i for i, s in enumerate(stmts) if "daily_bar_finalize.wait_for_boot(" in s)
    i_head = next(i for i, s in enumerate(stmts) if "emit_daily_head_staleness()" in s)
    assert i_ing < i_wait < i_head
    assert "wait_for" in stmts[i_ing] and "BOOT_INDEX_BUDGET_SECS" in stmts[i_ing]
    from src.engine import boot_manager

    assert boot_manager.BOOT_INDEX_BUDGET_SECS == 20


async def test_w2_evening_composite_runs_index_after_daily_and_reraises(monkeypatch):
    from src.engine import data_load_tasks, domestic_index_ingest, scanner

    order: list[str] = []
    captured = {}

    async def daily_ok():
        order.append("daily")
        return {"total": 1}

    async def ingest(*, phase):
        order.append(f"index:{phase}")
        return {}

    async def fake_loop(**kw):
        captured.update(kw)

    monkeypatch.setattr(scanner, "_stock_master_daily_load_once", daily_ok)
    monkeypatch.setattr(domestic_index_ingest, "ensure_fresh", ingest)
    monkeypatch.setattr("src.engine.task_loop_helper.run_periodic_task_loop", fake_loop)
    await data_load_tasks.stock_master_daily_load_task_loop(object(), wait_time=None)
    once = captured["once_callable"]
    assert await once() == {"total": 1} and order == ["daily", "index:evening"]

    async def daily_boom():
        order.append("daily")
        raise RuntimeError("kis")

    order.clear()
    monkeypatch.setattr(scanner, "_stock_master_daily_load_once", daily_boom)
    with pytest.raises(RuntimeError):
        await once()
    assert order == ["daily", "index:evening"], "일봉 예외여도 지수 적재는 돈다"


def test_w3_ingest_leaf_import_boundary():
    src = Path("src/engine/domestic_index_ingest.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    mods = []
    for n in ast.walk(tree):
        if isinstance(n, ast.ImportFrom) and n.module:
            mods.append(n.module)
        elif isinstance(n, ast.Import):
            mods += [a.name for a in n.names]
    banned = ("src.engine.scheduler", "src.engine.risk", "src.engine.order_engine", "src.engine.scanner",
              "src.engine.session", "src.engine.strategy_registry", "src.api.order", "src.realtime",
              "src.auth")
    assert not [m for m in mods if m.startswith(banned)], mods
    assert '"0001"' not in src and '"1001"' not in src, "지수 코드 정본은 market_unit 하나"


async def test_n1_boot_tests_see_inert_ingest():
    """중립화 메타 — 마커 없는 테스트의 `ensure_fresh` 는 DB·KIS 없이 즉시 `{}`."""
    from src.engine import domestic_index_ingest as ing

    assert await ing.ensure_fresh(phase="boot") == {}

