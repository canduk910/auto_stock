"""cycle408-L1 Red — 09:30 자동 퍼널 캡처는 그날 이미 확정된 행을 덮지 않는다.

명세 = `_workspace/refactor/2026-10-04_eight_area_observability_fixes.md` L1 절 안 A.

결함: 같은 날 재기동하면 새 프로세스의 `_auto_funnel_snapshot_done_today` 가 False 로 다시
태어나 `_scan_loop` 첫 회차가 자동 캡처를 한 번 더 돌린다. `insert_snapshot` 의
`WHERE NOT (기존 확정 ∧ 새 잠정)` 은 잠정→확정만 막으므로 확정→확정은 통과해 09:35 행이
재기동 뒤 값으로 바뀐다(09-29 16:00:34 `saved=52 provisional=False` 실측).

Green 계약
- `strategy_funnel.insert_snapshot(..., protect_confirmed: bool = False)` — True 면 기존 WHERE
  **뒤에** 리터럴 `AND strategy_funnel_snapshots.is_provisional = TRUE` 를 붙인다. 바인딩은
  10개 그대로. False(기본)면 SQL 이 지금과 byte 동일.
- `scheduler.capture_funnel_snapshots(..., protect_confirmed: bool = False)` → 두 insert 에 전달.
- `True` 를 넘기는 곳은 `_auto_capture_funnel_snapshots` **한 곳뿐**(수동 trigger·저녁·레거시는
  현행 = 수동 확정→확정 덮어쓰기는 계속 허용, cycle364 pg 3b_4).

실 SQL 의미는 `tests/integration/test_cycle408_l1_funnel_protect_confirmed_pg.py` 가 잰다.
"""

from __future__ import annotations

import ast
import re
from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parents[3]
_D = date(2026, 9, 29)
_GUARD = "AND strategy_funnel_snapshots.is_provisional = TRUE"


def _norm(sql: str) -> str:
    return re.sub(r"\s+", " ", sql).strip()


async def _capture_sql(**extra):
    from src.db import strategy_funnel

    with patch.object(strategy_funnel, "pg", create=True) as pg_mod:
        pg_mod.fetchrow = AsyncMock(return_value={"id": "x"})
        await strategy_funnel.insert_snapshot(
            target_date=_D, strategy_id="vcp_breakout", step_no=99, step_name="최종",
            survived_tickers=["990101"], is_provisional=False, **extra,
        )
    call = pg_mod.fetchrow.await_args
    return call.args[0], call.args[1:]


# ── R2 — SQL 조각 ────────────────────────────────────────────────────────
async def test_l1_r2_1_sql_when_protect_false_then_byte_identical_to_default():
    default_sql, default_args = await _capture_sql()
    off_sql, off_args = await _capture_sql(protect_confirmed=False)
    assert off_sql == default_sql, "protect_confirmed=False 는 기본 SQL 과 byte 동일해야 한다"
    assert _GUARD not in default_sql, "기본값에 보호 조각이 붙으면 수동 확정→확정 덮어쓰기가 막힌다"
    assert len(off_args) == 10 and off_args[1:] == default_args[1:]  # [0] = 매 호출 uuid


async def test_l1_r2_2_sql_when_protect_true_then_guard_appended_after_where_not():
    default_sql, _ = await _capture_sql()
    on_sql, on_args = await _capture_sql(protect_confirmed=True)
    flat = _norm(on_sql)
    m = re.search(
        r"WHERE NOT \(strategy_funnel_snapshots\.is_provisional = FALSE AND "
        r"EXCLUDED\.is_provisional = TRUE\) AND strategy_funnel_snapshots\.is_provisional = TRUE "
        r"RETURNING \*",
        flat,
    )
    assert m, f"보호 조각이 WHERE NOT (…) 바로 뒤·RETURNING 앞에 없다: {flat}"
    assert len(on_args) == 10, "플래그는 SQL 조각 선택이지 바인딩이 아니다"
    assert _norm(on_sql.replace(" " + _GUARD, "")) == _norm(default_sql), (
        "보호 조각 말고 다른 것이 바뀌었다"
    )


# ── R3 — 호출자 계약 ─────────────────────────────────────────────────────
def _strategy(sid="vcp_breakout"):
    s = MagicMock()
    s.strategy_id = sid
    s._live_prepare_meta = {"as_of": None, "phase": "boot", "ok": True}
    s._funnel_steps = [{"step_no": 1, "step_name": "유니버스", "survived": ["990101"],
                        "survived_count": 1, "excluded": [], "excluded_count": 0}]
    s.get_scanned_tickers = MagicMock(return_value=["990101"])
    return s


def _sched_with(strategies):
    from src.engine.scheduler import TradingScheduler

    sched = TradingScheduler.__new__(TradingScheduler)
    sched.registry = MagicMock()
    sched.registry.all = MagicMock(return_value=strategies)
    return sched


async def test_l1_r3_1_auto_capture_when_called_then_every_insert_protects_confirmed(monkeypatch):
    from src.db._kst import today_kst

    s = _strategy()
    s._live_prepare_meta["as_of"] = today_kst()
    captured: list[dict] = []

    async def _fake(**kw):
        captured.append(kw)
        return {"id": "x"}

    monkeypatch.setattr("src.db.strategy_funnel.insert_snapshot", _fake)
    await _sched_with([s])._auto_capture_funnel_snapshots()
    assert len(captured) == 2, captured  # 단계 1 + step_no=99
    assert all(c.get("protect_confirmed") is True for c in captured), (
        "09:30 자동 캡처가 protect_confirmed=True 를 넘기지 않는다 — 재기동이 확정 행을 덮는다"
    )
    assert all(c.get("is_provisional") is False for c in captured)


async def test_l1_r3_2_helper_when_default_then_does_not_protect(monkeypatch):
    from src.engine.scheduler import capture_funnel_snapshots

    captured: list[dict] = []

    async def _fake(**kw):
        captured.append(kw)
        return {"id": "x"}

    monkeypatch.setattr("src.db.strategy_funnel.insert_snapshot", _fake)
    s = _strategy()
    s._live_prepare_meta = None  # label == today → no_meta 아님
    reg = MagicMock()
    reg.all = MagicMock(return_value=[s])
    await capture_funnel_snapshots(reg, is_provisional=False)
    assert captured and all(not c.get("protect_confirmed", False) for c in captured), (
        "기본값(수동 trigger·저녁)이 보호를 켜면 수동 재캡처가 거부된다"
    )


def _protect_true_calls():
    hits = []
    for path in sorted((_ROOT / "src").rglob("*.py")):
        src = path.read_text(encoding="utf-8")
        tree = ast.parse(src)
        for fn in ast.walk(tree):
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for node in ast.walk(fn):
                if isinstance(node, ast.Call):
                    for kw in node.keywords:
                        if kw.arg == "protect_confirmed" and not (
                            isinstance(kw.value, ast.Constant) and kw.value.value is False
                        ):
                            hits.append((path.relative_to(_ROOT).as_posix(), fn.name,
                                         ast.unparse(kw.value)))
    return hits


def test_l1_r3_3_ast_when_scanning_src_then_only_auto_capture_passes_true():
    hits = _protect_true_calls()
    # capture_funnel_snapshots 는 자기 인자를 insert 에 그대로 전달한다(Name) — 그 2곳은 전달이다.
    literal = [h for h in hits if h[2] != "protect_confirmed"]
    forwarded = [h for h in hits if h[2] == "protect_confirmed"]
    assert literal == [("src/engine/scheduler.py", "_auto_capture_funnel_snapshots", "True")], (
        f"protect_confirmed 를 켜는 곳은 09:30 자동 캡처 한 곳뿐이어야 한다: {literal}"
    )
    assert {(p, f) for p, f, _ in forwarded} == {("src/engine/scheduler.py", "capture_funnel_snapshots")}
    assert len(forwarded) == 2, f"단계 행·step_no=99 두 insert 모두 전달해야 한다: {forwarded}"


# ── R4 — 재기동 시나리오 (새 인스턴스 = 플래그 False) ─────────────────────
async def test_l1_r4_restart_when_second_instance_auto_captures_then_confirmed_rows_kept(monkeypatch):
    """가짜 DB 는 실 SQL 의미(보호 조각 포함)를 흉내 낸다 — 플래그 전달이 끊기면 값이 바뀐다."""
    from src.db._kst import today_kst

    db: dict[tuple, dict] = {}

    async def _fake(*, target_date, strategy_id, step_no, survived_count=None,
                    is_provisional=False, protect_confirmed=False, **kw):
        key = (target_date, strategy_id, step_no)
        old = db.get(key)
        if old is not None:
            if old["is_provisional"] is False and is_provisional is True:
                return None
            if protect_confirmed and old["is_provisional"] is False:
                return None
        db[key] = {"survived_count": survived_count, "is_provisional": is_provisional}
        return {"id": "x"}

    monkeypatch.setattr("src.db.strategy_funnel.insert_snapshot", _fake)

    morning = _strategy()
    morning._live_prepare_meta["as_of"] = today_kst()
    await _sched_with([morning])._auto_capture_funnel_snapshots()
    before = {k: dict(v) for k, v in db.items()}

    after_restart = _strategy()
    after_restart._live_prepare_meta["as_of"] = today_kst()
    after_restart._funnel_steps[0]["survived_count"] = 77
    after_restart.get_scanned_tickers = MagicMock(return_value=["990201", "990202"])
    await _sched_with([after_restart])._auto_capture_funnel_snapshots()
    assert db == before, "재기동 뒤 자동 캡처가 그날 09:35 확정 행을 덮었다 (cycle408-L1)"
