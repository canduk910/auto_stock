"""사이클 M3a (Red) — src/db/stock_master_financial.py asyncpg 전환 계약 가드.

승인 계획: `~/.claude/plans/partitioned-kindling-lollipop.md` (단계 3 — 분석·관찰, 비 hot-path).

현행 stock_master_financial.py = supabase-py 체인 + `execute_with_retry`(read, 사이클 187/C1).
이 증분 = `pg.*` 전환. **함수 계약(시그니처·반환형·graceful) 100% 보존** → 호출부 diff 0.

핵심 계약 (8 호출):
- upsert_financial_batch(ticker, rows) → 100건 chunk + ON CONFLICT (ticker, stac_yymm, div_cls)
  DO UPDATE (복합 PK) + graceful (chunk 실패 시 다음 chunk 진행, 성공 건수 반환) + refreshed_at
  datetime(now_kst_iso, 사이클 68) + raw JSONB. executemany 또는 chunk 당 execute.
- get_financial_series(ticker, div_cls="0", limit=3) → SELECT ... WHERE ticker=$ AND div_cls=$
  ORDER BY stac_yymm DESC LIMIT $. `pg._with_retry` 경유 (사이클 187 read retry). 예외 → [] graceful.
- max_stac_yymm(ticker, div_cls="0") → SELECT stac_yymm ... DESC LIMIT 1 → str | None. graceful None.
- count_all() → SELECT count(*) → int (fetchval). graceful 0.

⚠️ NUMERIC → Decimal (계획 3대 미묘 계약 ③): asyncpg 는 18 NUMERIC 컬럼을 Decimal 로 반환.
mock 은 계약(반환 dict) 재현, 실 Decimal 왕복은 통합 테스트.

Red 유효성: production 미변경(supabase 체인 + execute_with_retry) → pg mock 미발화 → 계약 단언 FAIL.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _neutralize_supabase(monkeypatch):
    """현행 supabase(asyncio.to_thread + execute_with_retry) 경로 중립화 — Red hang/노이즈 차단.

    Green 전환 후엔 무해 (심볼 사라짐, raising=False).
    """
    from src.db import stock_master_financial as smf

    async def _fast_to_thread(fn, *a, **k):
        raise Exception("to_thread 중립화 (M3a Red)")

    async def _fast_retry(build, *, op: str = ""):
        raise Exception("execute_with_retry 중립화 (M3a Red)")

    monkeypatch.setattr(smf, "supabase", None, raising=False)
    monkeypatch.setattr(smf, "execute_with_retry", _fast_retry, raising=False)
    monkeypatch.setattr(smf.asyncio, "to_thread", _fast_to_thread, raising=False)
    yield


def _fin_row(stac_yymm="202312", div_cls="0", **over):
    row = {
        "ticker": "005930",
        "stac_yymm": stac_yymm,
        "div_cls": div_cls,
        "sale_account": 1000.0,
        "total_aset": 5000.0,
        "ev_ebitda": 8.5,
        "raw": {"src": "FHKST66430200"},
    }
    row.update(over)
    return row


# ---------------------------------------------------------------------------
# upsert_financial_batch — 100 chunk + ON CONFLICT PK 3키 + refreshed_at + graceful
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_upsert_batch_uses_on_conflict_pk_three_keys():
    """upsert_financial_batch → INSERT ... ON CONFLICT (ticker, stac_yymm, div_cls) DO UPDATE."""
    from src.db import stock_master_financial as smf

    rows = [_fin_row("202312"), _fin_row("202212")]
    with patch.object(smf, "pg", create=True) as pg_mod:
        pg_mod.execute = AsyncMock(return_value="INSERT 0 1")
        pg_mod.executemany = AsyncMock(return_value=None)
        out = await smf.upsert_financial_batch("005930", rows)

    assert out == 2, "upsert 성공 건수 2 반환 계약."
    all_sql = _collect_sql(pg_mod)
    joined = " ".join(all_sql)
    assert "INSERT INTO stock_master_financial" in joined, "INSERT INTO stock_master_financial 누락."
    assert "ON CONFLICT (ticker, stac_yymm, div_cls)" in joined, (
        "복합 PK ON CONFLICT (ticker, stac_yymm, div_cls) DO UPDATE 누락."
    )


@pytest.mark.asyncio
async def test_upsert_batch_empty_returns_zero():
    """빈 rows → 0 (DB 미발화)."""
    from src.db import stock_master_financial as smf

    with patch.object(smf, "pg", create=True) as pg_mod:
        pg_mod.execute = AsyncMock(return_value="INSERT 0 1")
        pg_mod.executemany = AsyncMock(return_value=None)
        out = await smf.upsert_financial_batch("005930", [])

    assert out == 0, "빈 rows → 0."
    assert pg_mod.execute.await_count == 0 and pg_mod.executemany.await_count == 0, (
        "빈 rows → DB 미발화."
    )


@pytest.mark.asyncio
async def test_upsert_batch_100_chunk_boundary():
    """100건 chunk — 250 rows → 3 chunk 발화 (100/100/50, 사이클 26 stale connection 회피)."""
    from src.db import stock_master_financial as smf

    rows = [_fin_row(f"2023{i:02d}") for i in range(250)]
    with patch.object(smf, "pg", create=True) as pg_mod:
        pg_mod.execute = AsyncMock(return_value="INSERT 0 1")
        pg_mod.executemany = AsyncMock(return_value=None)
        out = await smf.upsert_financial_batch("005930", rows)

    assert out == 250, "250건 전량 upsert 성공."
    # chunk 배치 발화 횟수 = ceil(250/100) = 3 (executemany 3회 또는 execute 250회 그룹)
    batch_calls = pg_mod.executemany.await_count
    if batch_calls:
        assert batch_calls == 3, "100건 chunk → 3 배치 (executemany) 발화."
    else:
        # execute 로 chunk 당 배치했다면 최소 3회 이상 (chunk 경계 발화)
        assert pg_mod.execute.await_count >= 3, "100건 chunk 경계 발화 (≥3)."


@pytest.mark.asyncio
async def test_upsert_batch_refreshed_at_datetime():
    """refreshed_at TIMESTAMPTZ → datetime 바인딩 (사이클 68 KST, M1 패턴 2 str 금지)."""
    from src.db import stock_master_financial as smf

    captured = []

    async def _cap_execute(sql, *args):
        captured.append(args)
        return "INSERT 0 1"

    async def _cap_many(sql, args_list):
        for a in args_list:
            captured.append(tuple(a))

    with patch.object(smf, "pg", create=True) as pg_mod:
        pg_mod.execute = AsyncMock(side_effect=_cap_execute)
        pg_mod.executemany = AsyncMock(side_effect=_cap_many)
        await smf.upsert_financial_batch("005930", [_fin_row("202312")])

    flat = [v for args in captured for v in args]
    assert any(isinstance(v, datetime) for v in flat), (
        "refreshed_at 은 datetime 바인딩 (fromisoformat(now_kst_iso())) — str 금지."
    )


@pytest.mark.asyncio
async def test_upsert_batch_raw_jsonb_binding():
    """raw JSONB dict 바인딩 (사이클 81 raw 보존)."""
    from src.db import stock_master_financial as smf

    captured = []

    async def _cap_execute(sql, *args):
        captured.append(args)
        return "INSERT 0 1"

    async def _cap_many(sql, args_list):
        for a in args_list:
            captured.append(tuple(a))

    with patch.object(smf, "pg", create=True) as pg_mod:
        pg_mod.execute = AsyncMock(side_effect=_cap_execute)
        pg_mod.executemany = AsyncMock(side_effect=_cap_many)
        await smf.upsert_financial_batch("005930", [_fin_row(raw={"key": "val"})])

    flat = [v for args in captured for v in args]
    assert _has_jsonb_binding(flat, {"key": "val"}), "raw JSONB dict/json.dumps 바인딩 누락."


@pytest.mark.asyncio
async def test_upsert_batch_graceful_partial_failure():
    """chunk 실패 graceful — 한 chunk 예외 시 다음 chunk 진행, 성공 건수만 반환 (사이클 88)."""
    from src.db import stock_master_financial as smf

    rows = [_fin_row(f"2023{i:02d}") for i in range(150)]  # 2 chunk (100/50)
    calls = {"n": 0}

    async def _fail_first_chunk(sql, args_list):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("chunk error")

    async def _fail_first_exec(sql, *args):
        calls["n"] += 1
        if calls["n"] <= 100:  # 첫 chunk 범위
            raise RuntimeError("chunk error")
        return "INSERT 0 1"

    with patch.object(smf, "pg", create=True) as pg_mod:
        pg_mod.executemany = AsyncMock(side_effect=_fail_first_chunk)
        pg_mod.execute = AsyncMock(side_effect=_fail_first_exec)
        out = await smf.upsert_financial_batch("005930", rows)

    # 첫 chunk 실패 graceful → 성공 건수는 전체보다 작음 (예외 전파 없음)
    assert out < 150, "첫 chunk 실패 graceful → 성공 건수 감소 (예외 전파 금지)."


# ---------------------------------------------------------------------------
# get_financial_series — _with_retry + stac_yymm DESC + graceful []
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_get_financial_series_uses_pg_fetch_desc():
    """get_financial_series → pg.fetch(WHERE ticker=$ AND div_cls=$ ORDER BY stac_yymm DESC LIMIT $)."""
    from src.db import stock_master_financial as smf

    rows = [_fin_row("202312"), _fin_row("202212")]
    with patch.object(smf, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(return_value=rows)
        pg_mod._with_retry = AsyncMock(side_effect=lambda f, **k: f())
        out = await smf.get_financial_series("005930", div_cls="0", limit=3)

    assert out == rows, "get_financial_series → list[dict] 반환."
    sql = pg_mod.fetch.await_args.args[0].upper()
    assert "STOCK_MASTER_FINANCIAL" in sql
    assert "ORDER BY STAC_YYMM DESC" in sql, "stac_yymm DESC 정렬 누락."
    passed = pg_mod.fetch.await_args.args[1:]
    assert "005930" in passed and "0" in passed and 3 in passed, (
        "ticker / div_cls / limit 바인딩 누락."
    )


@pytest.mark.asyncio
async def test_get_financial_series_uses_with_retry():
    """read 는 retry-보유 accessor(pg.fetch) 경유 (사이클 187/C1 = read retry).

    계약: get_financial_series read 는 pg.fetch 를 태운다. pg.fetch 가 내부에서
    pg._with_retry 를 경유하는 것은 M0 pg.py 계약이 별도 보증 (test_cycleM0_*).
    read 함수가 pg._with_retry 를 직접 부르지는 않음 (이중 retry 방지).
    """
    from src.db import stock_master_financial as smf

    with patch.object(smf, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(return_value=[])
        await smf.get_financial_series("005930")

    assert pg_mod.fetch.await_count >= 1, (
        "get_financial_series read 는 retry-보유 accessor(pg.fetch) 경유 (사이클 187)."
    )


@pytest.mark.asyncio
async def test_get_financial_series_exception_graceful_empty():
    """예외 → [] graceful (사이클 88 G-REJECT)."""
    from src.db import stock_master_financial as smf

    with patch.object(smf, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(side_effect=Exception("boom"))
        pg_mod._with_retry = AsyncMock(side_effect=Exception("boom"))
        out = await smf.get_financial_series("005930")

    assert out == [], "예외 → [] graceful."


# ---------------------------------------------------------------------------
# max_stac_yymm — DESC LIMIT 1 → str | None graceful
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_max_stac_yymm_returns_latest():
    """max_stac_yymm → SELECT stac_yymm ... DESC LIMIT 1 → str."""
    from src.db import stock_master_financial as smf

    with patch.object(smf, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(return_value=[{"stac_yymm": "202312"}])
        pg_mod.fetchrow = AsyncMock(return_value={"stac_yymm": "202312"})
        pg_mod.fetchval = AsyncMock(return_value="202312")
        pg_mod._with_retry = AsyncMock(side_effect=lambda f, **k: f())
        out = await smf.max_stac_yymm("005930", div_cls="0")

    assert out == "202312", "max_stac_yymm → 최신 stac_yymm 반환."


@pytest.mark.asyncio
async def test_max_stac_yymm_missing_returns_none():
    """미존재 → None."""
    from src.db import stock_master_financial as smf

    with patch.object(smf, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(return_value=[])
        pg_mod.fetchrow = AsyncMock(return_value=None)
        pg_mod.fetchval = AsyncMock(return_value=None)
        pg_mod._with_retry = AsyncMock(side_effect=lambda f, **k: f())
        out = await smf.max_stac_yymm("005930")

    assert out is None, "미존재 → None."


@pytest.mark.asyncio
async def test_max_stac_yymm_exception_graceful_none():
    """예외 → None graceful."""
    from src.db import stock_master_financial as smf

    with patch.object(smf, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(side_effect=Exception("boom"))
        pg_mod.fetchrow = AsyncMock(side_effect=Exception("boom"))
        pg_mod.fetchval = AsyncMock(side_effect=Exception("boom"))
        pg_mod._with_retry = AsyncMock(side_effect=Exception("boom"))
        out = await smf.max_stac_yymm("005930")

    assert out is None, "예외 → None graceful."


# ---------------------------------------------------------------------------
# count_all — fetchval count(*) → int graceful 0
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_count_all_returns_int():
    """count_all → pg.fetchval(SELECT count(*)) → int."""
    from src.db import stock_master_financial as smf

    with patch.object(smf, "pg", create=True) as pg_mod:
        pg_mod.fetchval = AsyncMock(return_value=42)
        pg_mod._with_retry = AsyncMock(side_effect=lambda f, **k: f())
        out = await smf.count_all()

    assert out == 42 and isinstance(out, int), "count_all → int 카운트."
    sql = pg_mod.fetchval.await_args.args[0].upper()
    assert "COUNT(*)" in sql or "COUNT (*)" in sql, "count(*) SELECT 누락."


@pytest.mark.asyncio
async def test_count_all_exception_graceful_zero():
    """예외 → 0 graceful."""
    from src.db import stock_master_financial as smf

    with patch.object(smf, "pg", create=True) as pg_mod:
        pg_mod.fetchval = AsyncMock(side_effect=Exception("boom"))
        pg_mod._with_retry = AsyncMock(side_effect=Exception("boom"))
        out = await smf.count_all()

    assert out == 0, "예외 → 0 graceful."


# ---------------------------------------------------------------------------
# 계약 보존 불변식 — supabase / execute_with_retry 미참조 (pg 단독)
#
# ⚠️ 소스 파일 정적 검사 (런타임 hasattr 금지): autouse `_neutralize_supabase` fixture 가
# `monkeypatch.setattr(smf, "supabase", None)` + `execute_with_retry` 를 *생성* 하므로
# 런타임 `hasattr` 는 항상 True → 계약 검증 불가. 소스 AST 로만 검증 가능 (docstring/
# 주석의 'supabase' 문자열은 파싱 무시).
# ---------------------------------------------------------------------------
def test_stock_master_financial_no_supabase_after_transition():
    """전환 후 supabase / execute_with_retry 심볼 잔존 금지 (pg 단독).

    소스 AST 검사 — import/코드 참조 부재 + src.db.pg import 존재.
    (fixture 오염 회피 = 이 테스트는 autouse fixture 무관 = 소스 텍스트만 검사.)
    """
    from src.db import stock_master_financial as smf

    _assert_no_supabase_reference_in_source(
        smf, forbidden_names=("supabase", "execute_with_retry")
    )
    assert _source_imports_pg(smf), "stock_master_financial 이 src.db.pg 를 import 해야 함."


def test_batch_size_constant_preserved():
    """_BATCH_SIZE = 100 계약 보존 (사이클 26 stale connection 회피)."""
    from src.db import stock_master_financial as smf

    assert smf._BATCH_SIZE == 100, "_BATCH_SIZE 100 계약 보존."


# ---------------------------------------------------------------------------
# 헬퍼 — 소스 AST 정적 검사 (supabase / execute_with_retry 미참조 계약)
# ---------------------------------------------------------------------------
def _source_imports_pg(mod) -> bool:
    """소스가 `import src.db.pg as pg` (또는 `from src.db import pg`) 를 하는지 AST 로 검증."""
    import ast
    import inspect

    tree = ast.parse(inspect.getsource(mod))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "src.db.pg":
                    return True
        elif isinstance(node, ast.ImportFrom):
            if node.module == "src.db" and any(a.name == "pg" for a in node.names):
                return True
    return False


def _assert_no_supabase_reference_in_source(mod, *, forbidden_names) -> None:
    """소스 AST 에 forbidden 심볼의 import / 코드 참조(Name) 가 없음을 단언.

    docstring/주석의 'supabase' 문자열은 파싱 대상이 아니므로 자연 무시된다.
    """
    import ast
    import inspect

    forbidden = set(forbidden_names)
    tree = ast.parse(inspect.getsource(mod))
    offenders: list[str] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                base = alias.name.split(".")[0]
                if base in forbidden or alias.name in forbidden:
                    offenders.append(f"import {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            mod_base = (node.module or "").split(".")[0]
            if mod_base in forbidden:
                offenders.append(f"from {node.module} import ...")
            for alias in node.names:
                if alias.name in forbidden:
                    offenders.append(f"from {node.module} import {alias.name}")
        elif isinstance(node, ast.Name) and node.id in forbidden:
            offenders.append(f"name {node.id}")

    assert not offenders, (
        f"전환 후 supabase/execute_with_retry 코드 참조 잔존 금지 (pg 단독). 발견: {offenders}"
    )


# ---------------------------------------------------------------------------
# 헬퍼 — SQL 수집 (isinstance(m, AsyncMock) 가드로 미설정 accessor 오탐 차단)
# ---------------------------------------------------------------------------
def _collect_sql(pg_mod) -> list[str]:
    sqls: list[str] = []
    for name in ("execute", "executemany", "fetch", "fetchrow", "fetchval"):
        m = getattr(pg_mod, name, None)
        if not isinstance(m, AsyncMock):
            continue
        for c in m.await_args_list:
            if c.args:
                sqls.append(c.args[0])
    return sqls


def _has_jsonb_binding(args, expected) -> bool:
    """JSONB 컬럼 바인딩이 dict/list 원본 또는 json.dumps 문자열로 포함되는지."""
    import json

    dumped = json.dumps(expected)
    for a in args:
        if a == expected:
            return True
        if isinstance(a, str) and a == dumped:
            return True
    return False
