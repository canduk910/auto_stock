"""사이클 168 — list_paged_by_filter jsonb string 결함 → 생성 컬럼 전환 회귀 가드.

근본 원인 (운영 DB 실측, project_id=etaligxesjtjfkbntdve):
- stock_master.raw.hts_avls / acml_tr_pbmn 가 전부 JSONB *문자열* 로 저장됨
  (hts_avls number=0/string=3573, acml_tr_pbmn string=3441).
- list_paged_by_filter 가 `q.gte("raw->hts_avls", N)` jsonb numeric 비교 →
  PostgreSQL jsonb 정렬은 number > string → `"1503">=1000` 항상 false → 0건.
- 실측: raw->'hts_avls' >= '1000'::jsonb = 0 vs hts_avls_eok >= 1000 = 1734건.

시정 (Option A, migration 039):
- 생성 컬럼 hts_avls_eok(억원, bigint STORED) + acml_tr_pbmn_won(원, bigint STORED) + 2 인덱스.
- list_paged_by_filter .gte("hts_avls_eok", min_market_cap//100_000_000)
                       .gte("acml_tr_pbmn_won", min_trade_amount).

영속 의무:
- 임계 환산 로직 불변 (사이클 166 억원 정합): hts_avls_eok=억원 → min_market_cap//100_000_000.
- 빈 필터 = 무필터 보존 (사이클 128 T-1 영속).
- scanner list_by_filter (Python-side) 변경 0 — UI 읽기 경로 한정.
- 사이클 81 G-AST1 영속: 생성 컬럼은 raw 읽기만(GENERATED) → raw 변경 0.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# 사이클 M2b — pg.fetchval/fetch 경유. gte (col, val) 를 SQL 텍스트 + args 대조로 캡처.
#
# production list_paged_by_filter 는 WHERE 절에 `<col> >= $N` / `<col> ILIKE $N` 을
# 넣고 args 를 append 순서대로 바인딩한다. placeholder($N) ↔ arg 매핑으로 (col, val)
# 을 복원하여 seen["gte"] / seen["ilike"] / seen["range"] 에 기록한다.
# ---------------------------------------------------------------------------
def _record_clauses(sql: str, args: tuple, seen: dict) -> None:
    s = sql
    # `<col> >= $N` 패턴 → gte (col, args[N-1])
    for m in re.finditer(r"(\w+)\s*>=\s*\$(\d+)", s):
        col, idx = m.group(1), int(m.group(2))
        if 1 <= idx <= len(args):
            seen.setdefault("gte", []).append((col, args[idx - 1]))
    # `<col> ILIKE $N`
    for m in re.finditer(r"(\w+)\s+ILIKE\s+\$(\d+)", s, re.IGNORECASE):
        col, idx = m.group(1), int(m.group(2))
        if 1 <= idx <= len(args):
            seen.setdefault("ilike", []).append((col, args[idx - 1]))
    # `<col> = $N` (eq)
    for m in re.finditer(r"(\w+)\s*=\s*\$(\d+)", s):
        col, idx = m.group(1), int(m.group(2))
        if 1 <= idx <= len(args):
            seen.setdefault("eq", []).append((col, args[idx - 1]))
    # LIMIT $N OFFSET $M → range (offset, offset+limit)
    lm = re.search(r"LIMIT\s+\$(\d+)\s+OFFSET\s+\$(\d+)", s, re.IGNORECASE)
    if lm:
        li, oi = int(lm.group(1)), int(lm.group(2))
        if 1 <= li <= len(args) and 1 <= oi <= len(args):
            seen["range"] = (args[oi - 1], args[oi - 1] + args[li - 1])


async def _run(seen: dict, **kwargs):
    from src.db import stock_master

    async def _fetchval(sql, *args):
        _record_clauses(sql, args, seen)
        return 42  # total count

    async def _fetch(sql, *args):
        _record_clauses(sql, args, seen)
        return [{"ticker": "005930"}]

    with patch.object(stock_master, "pg", create=True) as pg_mod:
        pg_mod.fetchval = AsyncMock(side_effect=_fetchval)
        pg_mod.fetch = AsyncMock(side_effect=_fetch)
        return await stock_master.list_paged_by_filter(**kwargs)


# ===========================================================================
# G-168-COL — 생성 컬럼 .gte 호출 (col 정확 검증)
# ===========================================================================
@pytest.mark.asyncio
async def test_g168_col1_market_cap_uses_hts_avls_eok():
    """G-168-COL-1: min_market_cap>0 → .gte("hts_avls_eok", threshold) 호출.

    jsonb raw->hts_avls 가 아니라 생성 컬럼 hts_avls_eok 으로 비교해야 한다.
    """
    seen: dict = {}
    await _run(seen, min_market_cap=100_000_000_000, limit=50, offset=0)

    gte_cols = [col for col, _ in seen.get("gte", [])]
    assert "hts_avls_eok" in gte_cols, (
        f"min_market_cap → .gte('hts_avls_eok', ...) 의무. 실제 gte: {seen.get('gte')}"
    )
    # jsonb 경로 잔존 0건 (런타임 단언)
    assert not any(c == "raw->hts_avls" for c in gte_cols), (
        f"raw->hts_avls jsonb gte 잔존 금지 (string 비교 결함). 실제: {seen.get('gte')}"
    )


@pytest.mark.asyncio
async def test_g168_col2_trade_amount_uses_acml_tr_pbmn_won():
    """G-168-COL-2: min_trade_amount>0 → .gte("acml_tr_pbmn_won", threshold) 호출."""
    seen: dict = {}
    await _run(seen, min_trade_amount=10_000_000_000, limit=50, offset=0)

    gte_cols = [col for col, _ in seen.get("gte", [])]
    assert "acml_tr_pbmn_won" in gte_cols, (
        f"min_trade_amount → .gte('acml_tr_pbmn_won', ...) 의무. 실제 gte: {seen.get('gte')}"
    )
    assert not any(c == "raw->acml_tr_pbmn" for c in gte_cols), (
        f"raw->acml_tr_pbmn jsonb gte 잔존 금지. 실제: {seen.get('gte')}"
    )


# ===========================================================================
# G-168-THRESH — 임계 환산 정합 (사이클 166 억원 정합 영속)
# ===========================================================================
@pytest.mark.asyncio
async def test_g168_thresh1_market_cap_1000eok():
    """G-168-THRESH-1: min_market_cap=1,000억(원) → hts_avls_eok 임계 = 1000 (억원)."""
    seen: dict = {}
    await _run(seen, min_market_cap=100_000_000_000, limit=50, offset=0)

    threshold = next(v for c, v in seen["gte"] if c == "hts_avls_eok")
    assert threshold == 1000, f"1,000억 원 → 임계 1000(억원) 의무. 실제 {threshold}"


@pytest.mark.asyncio
async def test_g168_thresh2_market_cap_ten_trillion():
    """G-168-THRESH-2: min_market_cap=10조(원) → hts_avls_eok 임계 = 100,000 (억원)."""
    seen: dict = {}
    await _run(seen, min_market_cap=10_000_000_000_000, limit=50, offset=0)

    threshold = next(v for c, v in seen["gte"] if c == "hts_avls_eok")
    assert threshold == 100_000, f"10조 원 → 임계 100,000(억원) 의무. 실제 {threshold}"


@pytest.mark.asyncio
async def test_g168_thresh3_trade_amount_won_passthrough():
    """G-168-THRESH-3: min_trade_amount=100억(원) → acml_tr_pbmn_won 임계 = 원 그대로."""
    seen: dict = {}
    await _run(seen, min_trade_amount=10_000_000_000, limit=50, offset=0)

    threshold = next(v for c, v in seen["gte"] if c == "acml_tr_pbmn_won")
    assert threshold == 10_000_000_000, (
        f"거래대금은 원 단위 그대로 비교. 실제 {threshold}"
    )


@pytest.mark.asyncio
async def test_g168_thresh1b_market_cap_ceil_boundary():
    """G-168-THRESH-1b: 비정확 경계 ceil 보존 — 99,999,999,999 → 1000 (사이클 166 ceil 영속)."""
    seen: dict = {}
    await _run(seen, min_market_cap=99_999_999_999, limit=50, offset=0)

    threshold = next(v for c, v in seen["gte"] if c == "hts_avls_eok")
    # (99_999_999_999 + 99_999_999) // 100_000_000 = 1000 (ceil)
    assert threshold == 1000, f"ceil 보존 의무. 실제 {threshold}"


# ===========================================================================
# G-168-EMPTY — 빈 필터 무필터 보존 (T-1 영속)
# ===========================================================================
@pytest.mark.asyncio
async def test_g168_empty1_no_market_cap_no_gte():
    """G-168-EMPTY-1: min_market_cap=0 → hts_avls_eok gte 미호출 (무필터 보존)."""
    seen: dict = {}
    await _run(seen, min_market_cap=0, min_trade_amount=0, limit=50, offset=0)

    gte_cols = [col for col, _ in seen.get("gte", [])]
    assert "hts_avls_eok" not in gte_cols, (
        f"min_market_cap=0 → hts_avls_eok gte 미적용 의무. 실제: {seen.get('gte')}"
    )
    assert "acml_tr_pbmn_won" not in gte_cols, (
        f"min_trade_amount=0 → acml_tr_pbmn_won gte 미적용 의무. 실제: {seen.get('gte')}"
    )


@pytest.mark.asyncio
async def test_g168_empty2_response_envelope_preserved():
    """G-168-EMPTY-2: 빈 필터 시 응답 envelope (items/total/limit/offset) 보존."""
    seen: dict = {}
    result = await _run(seen, limit=100, offset=0)

    assert set(result.keys()) >= {"items", "total", "limit", "offset"}
    assert result["limit"] == 100
    assert result["offset"] == 0
    assert result["total"] == 42


# ===========================================================================
# G-168-AST — 정적 가드: list_paged_by_filter 본체 raw->hts_avls / raw->acml_tr_pbmn jsonb gte 잔존 0건
# ===========================================================================
def _list_paged_func_source() -> str:
    src_path = (
        Path(__file__).resolve().parents[3]
        / "src" / "db" / "stock_master.py"
    )
    tree = ast.parse(src_path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "list_paged_by_filter":
            return ast.get_source_segment(src_path.read_text(encoding="utf-8"), node) or ""
    raise AssertionError("list_paged_by_filter 함수를 찾을 수 없음")


def test_g168_ast1_no_jsonb_gte_in_list_paged():
    """G-168-AST-1 (HIGH): list_paged_by_filter 본체에 jsonb raw->hts_avls / raw->acml_tr_pbmn

    gte 문자열 잔존 0건. 생성 컬럼 전환 영구 가드 — 미래 silent string 비교 결함 차단.
    """
    func_src = _list_paged_func_source()
    assert "raw->hts_avls" not in func_src, (
        "list_paged_by_filter 에 raw->hts_avls jsonb 경로 잔존 (string 비교 결함). "
        "hts_avls_eok 생성 컬럼으로 전환되어야 함."
    )
    assert "raw->acml_tr_pbmn" not in func_src, (
        "list_paged_by_filter 에 raw->acml_tr_pbmn jsonb 경로 잔존. "
        "acml_tr_pbmn_won 생성 컬럼으로 전환되어야 함."
    )
    # 생성 컬럼 사용 명시 검증
    assert "hts_avls_eok" in func_src, "hts_avls_eok 생성 컬럼 사용 의무."
    assert "acml_tr_pbmn_won" in func_src, "acml_tr_pbmn_won 생성 컬럼 사용 의무."


def test_g168_ast2_migration_039_exists():
    """G-168-AST-2: migration 039 생성 컬럼 + 인덱스 정의 존재."""
    mig = (
        Path(__file__).resolve().parents[3]
        / "supabase" / "migrations" / "039_stock_master_numeric_generated_cols.sql"
    )
    assert mig.exists(), "migration 039 파일 존재 의무."
    text = mig.read_text(encoding="utf-8")
    assert "hts_avls_eok" in text and "GENERATED ALWAYS AS" in text and "STORED" in text
    assert "acml_tr_pbmn_won" in text
    assert "ix_sm_hts_avls_eok" in text and "ix_sm_acml_tr_pbmn_won" in text
    # idempotent 가드
    assert "IF NOT EXISTS" in text
    # 비숫자 graceful 가드
    assert "^[0-9]+$" in text
