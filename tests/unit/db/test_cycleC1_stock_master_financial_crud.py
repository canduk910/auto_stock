"""사이클 C1 — src/db/stock_master_financial.py CRUD Red 가드.

Red 명세: `_workspace/red/cycleC1_financial_infra.md`

`stock_master_daily.py` 100% 미러. `upsert_financial_batch` / `get_financial_series`
/ `max_stac_yymm` / `count_all` + `_safe_float`/`_safe_int` 헬퍼.

가드:
- upsert_financial_batch: 100건 chunk + on_conflict PK 3키 + graceful (개별 실패 카운트)
  + KST refreshed_at (사이클 68 now_kst_iso)
- get_financial_series: execute_with_retry 경유 (사이클 187) + stac_yymm DESC + graceful []
- max_stac_yymm: graceful None
- count_all: graceful 0

production 모듈 미작성 → import 실패로 전부 FAIL (Red).
freeze_time 미사용 — supabase mock (사이클 187 hang 교훈).
매매 안전성 무영향 (scanner 매수 진입 전, 사이클 38).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

pytestmark = pytest.mark.unit


def _fin_row(stac_yymm: str, div_cls: str = "0", **overrides) -> dict:
    """정규화 재무 row (스키마 컬럼명). 최소 필드 + overrides."""
    row = {
        "ticker": "005930",
        "stac_yymm": stac_yymm,
        "div_cls": div_cls,
        "sale_account": 2589355.0,
        "sale_totl_prfi": 785469.0,
        "bsop_prti": 65670.0,
        "thtr_ntin": 154871.0,
        "depr_cost": 99.99,
        "cras": 1959366.0,
        "fxas": 2599694.0,
        "total_aset": 4559060.0,
        "flow_lblt": 757195.0,
        "total_lblt": 922281.0,
        "total_cptl": 3636779.0,
        "cpfn": 8975.0,
        "cptl_ntin_rate": 3.43,
        "sale_totl_rate": 30.33,
        "lblt_rate": 25.36,
        "crnt_rate": 258.77,
        "ebitda": 23464.0,
        "ev_ebitda": 0.0,
        "raw": {"stac_yymm": stac_yymm},
    }
    row.update(overrides)
    return row


# ---------------------------------------------------------------------------
# G-C1-DB-1 — 모듈 import + 4 CRUD + 2 헬퍼 존재
# ---------------------------------------------------------------------------
def test_module_and_public_api_present():
    """stock_master_financial 모듈 + 필수 함수 전수 노출 (daily 미러)."""
    from src.db import stock_master_financial as smf

    for name in (
        "upsert_financial_batch",
        "get_financial_series",
        "max_stac_yymm",
        "count_all",
        "_safe_float",
        "_safe_int",
    ):
        assert hasattr(smf, name), f"stock_master_financial.{name} 부재 (daily 미러 의무)."


# ---------------------------------------------------------------------------
# G-C1-DB-2 — _safe_float / _safe_int graceful (daily 답습)
# ---------------------------------------------------------------------------
def test_safe_helpers_graceful():
    """빈 값/비숫자 → default (daily _safe_* 답습)."""
    from src.db import stock_master_financial as smf

    assert smf._safe_float("2589355.00") == pytest.approx(2589355.0)
    assert smf._safe_float("") == 0.0
    assert smf._safe_float(None) == 0.0
    assert smf._safe_float("abc") == 0.0
    assert smf._safe_int("8975") == 8975
    assert smf._safe_int("") == 0
    assert smf._safe_int(None) == 0


# ---------------------------------------------------------------------------
# G-C1-DB-3 — upsert_financial_batch on_conflict PK 3키
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_upsert_on_conflict_pk_three_keys(monkeypatch):
    """upsert 가 on_conflict='ticker,stac_yymm,div_cls' (PK 3키 갱신)."""
    from src.db import stock_master_financial as smf

    captured = {}

    def _fake_upsert(rows, on_conflict=None):
        captured["on_conflict"] = on_conflict
        chain = MagicMock()
        chain.execute = MagicMock(return_value=MagicMock(data=rows))
        return chain

    table = MagicMock()
    table.upsert = MagicMock(side_effect=_fake_upsert)
    fake_supabase = MagicMock()
    fake_supabase.table = MagicMock(return_value=table)
    monkeypatch.setattr(smf, "supabase", fake_supabase)

    rows = [_fin_row("202312"), _fin_row("202309")]
    count = await smf.upsert_financial_batch("005930", rows)

    assert captured.get("on_conflict") == "ticker,stac_yymm,div_cls", (
        f"on_conflict PK 3키 정합 부재: {captured.get('on_conflict')!r}"
    )
    assert count == 2, f"성공 카운트 2 != {count}"


# ---------------------------------------------------------------------------
# G-C1-DB-4 — upsert graceful (개별 chunk 실패 시 성공분만 카운트)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_upsert_graceful_partial_failure(monkeypatch):
    """개별 chunk 실패 시 예외 미전파 + 성공 chunk 만 카운트 (사이클 88 G-REJECT).

    _BATCH_SIZE=100 → 250건 = 3 chunk (100/100/50). 2번째 chunk 실패 시 200 반환.
    """
    from src.db import stock_master_financial as smf

    assert getattr(smf, "_BATCH_SIZE", None) == 100, "_BATCH_SIZE=100 (daily 답습) 부재."

    call_idx = {"n": 0}

    def _fake_upsert(rows, on_conflict=None):
        chain = MagicMock()

        def _execute():
            call_idx["n"] += 1
            if call_idx["n"] == 2:  # 2번째 chunk 실패
                raise RuntimeError("supabase chunk error")
            return MagicMock(data=rows)

        chain.execute = MagicMock(side_effect=_execute)
        return chain

    table = MagicMock()
    table.upsert = MagicMock(side_effect=_fake_upsert)
    fake_supabase = MagicMock()
    fake_supabase.table = MagicMock(return_value=table)
    monkeypatch.setattr(smf, "supabase", fake_supabase)

    rows = [_fin_row(f"2023{m:02d}") for m in range(1, 13)]  # 12건
    rows += [_fin_row(f"2022{m:02d}") for m in range(1, 13)]  # 24건
    # 채우기 — stac_yymm 을 연도별로 다양화해 250건 확보 (div_cls 교차)
    for year in range(2000, 2020):
        rows += [
            _fin_row(f"{year}{m:02d}", div_cls=str(m % 2)) for m in range(1, 13)
        ]
    rows = rows[:250]
    assert len(rows) == 250, f"테스트 fixture 250건 미달: {len(rows)}"

    count = await smf.upsert_financial_batch("005930", rows)
    # 3 chunk 중 2번째(100건) 실패 → 성공 100 + 50 = 150
    assert count == 150, (
        f"graceful 부분 실패 카운트 150 != {count} (2번째 chunk 100건 실패 제외)."
    )


# ---------------------------------------------------------------------------
# G-C1-DB-5 — upsert KST refreshed_at (사이클 68 now_kst_iso)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_upsert_kst_refreshed_at(monkeypatch):
    """upsert row 에 KST refreshed_at (+09:00) 주입 — now_kst_iso 경유 (사이클 68)."""
    from src.db import stock_master_financial as smf

    captured_rows = {}

    def _fake_upsert(rows, on_conflict=None):
        captured_rows["rows"] = rows
        chain = MagicMock()
        chain.execute = MagicMock(return_value=MagicMock(data=rows))
        return chain

    table = MagicMock()
    table.upsert = MagicMock(side_effect=_fake_upsert)
    fake_supabase = MagicMock()
    fake_supabase.table = MagicMock(return_value=table)
    monkeypatch.setattr(smf, "supabase", fake_supabase)
    # now_kst_iso 를 결정론적 값으로 patch — KST +09:00 명시 검증
    monkeypatch.setattr(smf, "now_kst_iso", lambda: "2026-07-15T16:40:00+09:00")

    await smf.upsert_financial_batch("005930", [_fin_row("202312")])

    up_rows = captured_rows.get("rows") or []
    assert up_rows, "upsert row 미전달"
    ref = up_rows[0].get("refreshed_at")
    assert ref == "2026-07-15T16:40:00+09:00", (
        f"refreshed_at KST 미주입: {ref!r} — now_kst_iso 경유 의무 (사이클 68)."
    )


# ---------------------------------------------------------------------------
# G-C1-DB-6 — get_financial_series execute_with_retry 경유 + stac_yymm DESC
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_get_series_retry_and_desc(monkeypatch):
    """get_financial_series 가 execute_with_retry 경유 (사이클 187) + stac_yymm DESC 정렬 요청."""
    from src.db import stock_master_financial as smf

    order_captured = {}

    def _order(col, desc=False):
        order_captured["col"] = col
        order_captured["desc"] = desc
        chain = MagicMock()
        chain.limit = MagicMock(return_value=chain)
        chain.execute = MagicMock(
            return_value=MagicMock(data=[_fin_row("202312"), _fin_row("202309")])
        )
        return chain

    select_chain = MagicMock()
    select_chain.eq = MagicMock(return_value=select_chain)
    select_chain.order = MagicMock(side_effect=_order)
    table = MagicMock()
    table.select = MagicMock(return_value=select_chain)
    fake_supabase = MagicMock()
    fake_supabase.table = MagicMock(return_value=table)
    monkeypatch.setattr(smf, "supabase", fake_supabase)

    retry_called = {"n": 0}

    async def _fake_retry(build, *, retries=1, op=""):
        retry_called["n"] += 1
        return build()

    monkeypatch.setattr(smf, "execute_with_retry", _fake_retry)

    result = await smf.get_financial_series("005930", div_cls="0", limit=3)

    assert retry_called["n"] == 1, "execute_with_retry 미경유 (사이클 187 daily read 패턴 의무)."
    assert order_captured.get("col") == "stac_yymm", (
        f"정렬 컬럼 stac_yymm 부재: {order_captured.get('col')!r}"
    )
    assert order_captured.get("desc") is True, "stac_yymm DESC 정렬 부재 (최신 기수 우선)."
    assert len(result) == 2


# ---------------------------------------------------------------------------
# G-C1-DB-7 — get_financial_series graceful []
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_get_series_graceful_empty(monkeypatch):
    """DB 예외 시 예외 미전파 + 빈 list 반환 (호출자 graceful, 사이클 88)."""
    from src.db import stock_master_financial as smf

    async def _boom(build, *, retries=1, op=""):
        raise RuntimeError("supabase down")

    monkeypatch.setattr(smf, "execute_with_retry", _boom)

    result = await smf.get_financial_series("005930")
    assert result == [], f"graceful [] 부재: {result!r}"


# ---------------------------------------------------------------------------
# G-C1-DB-8 — max_stac_yymm graceful None + 백필/증분 분기 키
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_max_stac_yymm_and_graceful(monkeypatch):
    """max_stac_yymm 최신 기수 반환 + DB 예외 시 None (백필/증분 분기)."""
    from src.db import stock_master_financial as smf

    async def _ok(build, *, retries=1, op=""):
        return build()

    select_chain = MagicMock()
    select_chain.eq = MagicMock(return_value=select_chain)
    select_chain.order = MagicMock(return_value=select_chain)
    select_chain.limit = MagicMock(return_value=select_chain)
    select_chain.execute = MagicMock(return_value=MagicMock(data=[{"stac_yymm": "202312"}]))
    table = MagicMock()
    table.select = MagicMock(return_value=select_chain)
    fake_supabase = MagicMock()
    fake_supabase.table = MagicMock(return_value=table)
    monkeypatch.setattr(smf, "supabase", fake_supabase)
    monkeypatch.setattr(smf, "execute_with_retry", _ok)

    latest = await smf.max_stac_yymm("005930", div_cls="0")
    assert latest == "202312", f"최신 stac_yymm 202312 != {latest!r}"

    async def _boom(build, *, retries=1, op=""):
        raise RuntimeError("down")

    monkeypatch.setattr(smf, "execute_with_retry", _boom)
    assert await smf.max_stac_yymm("005930") is None, "graceful None 부재."


# ---------------------------------------------------------------------------
# G-C1-DB-9 — count_all graceful 0
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_count_all_graceful(monkeypatch):
    """count_all 진단 카운트 + DB 예외 시 0 (daily count_all 답습)."""
    from src.db import stock_master_financial as smf

    async def _ok(build, *, retries=1, op=""):
        return build()

    select_chain = MagicMock()
    select_chain.limit = MagicMock(return_value=select_chain)
    select_chain.execute = MagicMock(return_value=MagicMock(count=42, data=[]))
    table = MagicMock()
    table.select = MagicMock(return_value=select_chain)
    fake_supabase = MagicMock()
    fake_supabase.table = MagicMock(return_value=table)
    monkeypatch.setattr(smf, "supabase", fake_supabase)
    monkeypatch.setattr(smf, "execute_with_retry", _ok)

    assert await smf.count_all() == 42

    async def _boom(build, *, retries=1, op=""):
        raise RuntimeError("down")

    monkeypatch.setattr(smf, "execute_with_retry", _boom)
    assert await smf.count_all() == 0, "graceful 0 부재."
