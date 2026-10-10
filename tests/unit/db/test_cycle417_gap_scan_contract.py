"""cycle417 (Red) — `stock_master_daily.earliest_missing_bas_dd` 계약 (DB 없이 재는 부분).

계약 = `_workspace/red/cycle417/gap_fill_contract.md` §2. SQL 의미(달력·첫 행·빈 날)는
실 Postgres 통합 테스트 `tests/integration/test_cycle417_daily_gap_scan_pg.py` 가 잰다.
"""

from __future__ import annotations

import ast
import inspect
import textwrap
from datetime import date

import pytest

import src.db.pg as pg
from src.db import stock_master_daily as smd

pytestmark = pytest.mark.unit

_HELPER = "earliest_missing_bas_dd"


def test_d1_constants():
    """달력 = 최근 100 영업일 · 그날 행 수 >= 300 (우리 DB 자체로 만든 달력)."""
    assert smd.GAP_HORIZON == 100
    assert smd.GAP_CALENDAR_MIN_ROWS == 300


def test_d2_signature_before_is_keyword_only():
    """`before` 는 키워드 전용 — 「오늘」 을 위치 인자로 잘못 넘기는 호출을 막는다."""
    sig = inspect.signature(getattr(smd, _HELPER))
    params = sig.parameters
    assert list(params)[0] == "tickers"
    assert params["before"].kind is inspect.Parameter.KEYWORD_ONLY
    assert params["horizon"].default == smd.GAP_HORIZON
    assert params["min_rows"].default == smd.GAP_CALENDAR_MIN_ROWS


async def test_d3_db_error_propagates(monkeypatch):
    """조회 실패를 삼키지 않는다 — 빈 dict 로 접으면 「판정 실패」 가 「구멍 없음」 으로 둔갑한다.

    호출부(scanner)가 fail-open + WARNING 으로 받는다(`list_provisional_rows` 선례).
    읽기 함수 셋을 모두 막으므로 구현이 어느 것을 쓰든 같다.
    """
    async def _boom(*_a, **_k):
        raise RuntimeError("db down")

    for name in ("fetch", "fetchrow", "fetchval"):
        monkeypatch.setattr(pg, name, _boom)
    with pytest.raises(RuntimeError, match="db down"):
        await getattr(smd, _HELPER)(["005930"], before=date(2026, 10, 12))


def test_d4_no_await_inside_loop():
    """쿼리는 종목 수와 무관하게 상수 — 루프·컴프리헨션 안의 `await` 금지(종목당 조회 차단)."""
    tree = ast.parse(textwrap.dedent(inspect.getsource(getattr(smd, _HELPER))))
    loops = (ast.For, ast.AsyncFor, ast.While, ast.ListComp, ast.SetComp,
             ast.DictComp, ast.GeneratorExp)
    offenders = []
    for loop in ast.walk(tree):
        if isinstance(loop, loops):
            offenders += [n for n in ast.walk(loop) if isinstance(n, ast.Await)]
    assert offenders == [], f"루프 안 await {len(offenders)}건 — 종목당 쿼리가 된다"


# ══════════════════════════════════════════════════════════════════════
# cycle437 (리팩토링 카드 #10 ③) — `calendar_size` 계약(DB 없이 재는 부분).
# SQL 의미(실제 달력 행 수)는 통합 테스트 `tests/integration/test_cycle417_daily_gap_scan_pg.py`.
# ══════════════════════════════════════════════════════════════════════
_CAL = "calendar_size"


def test_d5_calendar_size_signature():
    """`before` 는 첫 위치 인자 · `horizon`/`min_rows` 는 키워드 전용, 헬퍼와 같은 기본값."""
    sig = inspect.signature(getattr(smd, _CAL))
    params = sig.parameters
    assert list(params)[0] == "before"
    assert params["before"].kind in (
        inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.POSITIONAL_ONLY,
    )
    assert params["horizon"].kind is inspect.Parameter.KEYWORD_ONLY
    assert params["horizon"].default == smd.GAP_HORIZON
    assert params["min_rows"].kind is inspect.Parameter.KEYWORD_ONLY
    assert params["min_rows"].default == smd.GAP_CALENDAR_MIN_ROWS


async def test_d6_calendar_size_db_error_propagates(monkeypatch):
    """조회 실패를 삼키지 않는다 — `earliest_missing_bas_dd` 와 같은 규약.

    호출부(scanner)가 fail-open(0) + WARNING 으로 받는다.
    """
    async def _boom(*_a, **_k):
        raise RuntimeError("db down")

    for name in ("fetch", "fetchrow", "fetchval"):
        monkeypatch.setattr(pg, name, _boom)
    with pytest.raises(RuntimeError, match="db down"):
        await getattr(smd, _CAL)(date(2026, 10, 12))


def test_d7_calendar_size_no_await_inside_loop():
    """루프·컴프리헨션이 없는 순수 쿼리 1회 함수(종목 인자가 없다)."""
    tree = ast.parse(textwrap.dedent(inspect.getsource(getattr(smd, _CAL))))
    loops = (ast.For, ast.AsyncFor, ast.While, ast.ListComp, ast.SetComp,
             ast.DictComp, ast.GeneratorExp)
    offenders = []
    for loop in ast.walk(tree):
        if isinstance(loop, loops):
            offenders += [n for n in ast.walk(loop) if isinstance(n, ast.Await)]
    assert offenders == [], f"루프 안 await {len(offenders)}건"


async def test_d8_calendar_size_none_scalar_becomes_zero(monkeypatch):
    """`pg.fetchval` 이 `None`(빈 테이블 등)을 주면 0 — 예외와 구분된다."""
    async def _none(*_a, **_k):
        return None

    monkeypatch.setattr(pg, "fetchval", _none)
    got = await getattr(smd, _CAL)(date(2026, 10, 12))
    assert got == 0
