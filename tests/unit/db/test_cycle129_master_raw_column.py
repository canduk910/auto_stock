"""사이클 129 — `stock_master.master_raw` 컬럼 Red 회귀 가드.

배경:
- migration 034: ALTER TABLE stock_master ADD master_raw JSONB + master_raw_updated_at TIMESTAMPTZ
- 사용자 결정 Q6=C 별도 컬럼 → 사이클 81 G-AST1 (raw 덮어쓰기 금지) 영속 보호

회귀 가드 4 케이스:
- G-MC1: upsert_master_raw 정상 (JSONB + updated_at_kst KST timestamp)
- G-MC2: get_master_raw 조회 (NULL/{} 부재 회피)
- G-MC3: count_master_raw_today 진단
- G-MC4: 사이클 81 G-AST1 영속 = raw 영역 변경 0 (upsert_master_raw 호출 후 raw 동일)
"""
from __future__ import annotations

import asyncio
import pytest


@pytest.mark.asyncio
async def test_g_mc1_upsert_master_raw_jsonb_kst(monkeypatch):
    """G-MC1: upsert_master_raw 정상 (master_raw JSONB + master_raw_updated_at KST +09:00).

    payload 영역 검증:
    - master_raw = dict (JSONB)
    - master_raw_updated_at = KST `+09:00` ISO string (사이클 68 G-10b 답습)
    """
    from src.db import stock_master

    captured_payload = {}

    class _StubExec:
        def execute(self):
            return None

    class _StubTable:
        def upsert(self, row, *, on_conflict=None):
            captured_payload.update(row)
            return _StubExec()

        def update(self, row):
            captured_payload.update(row)
            return self

        def eq(self, *_args, **_kwargs):
            return _StubExec()

    class _StubSupabase:
        def table(self, _name):
            return _StubTable()

    monkeypatch.setattr(stock_master, "supabase", _StubSupabase())

    sample_master = {
        "mksc_shrn_iscd": "005930",
        "hts_kor_isnm": "삼성전자",
        "trht_yn": "N",
        "mang_issu_yn": "N",
        "ssts_hot_yn": "N",
        "stange_runup_yn": "N",
        "mrkt_alrm_cls_code": "00",
        "prdy_avls_scal": "5000000",  # 5,000,000 억 = 500조원
        "lstn_stcn": "5969783",  # 596억주 (천주 단위)
        "roe": "12.5",
    }

    assert hasattr(stock_master, "upsert_master_raw"), (
        "G-MC1: upsert_master_raw 함수 부재"
    )

    await stock_master.upsert_master_raw("005930", sample_master)

    assert "master_raw" in captured_payload, (
        "G-MC1: master_raw 컬럼 payload 부재"
    )
    assert captured_payload["master_raw"] == sample_master, (
        "G-MC1: master_raw 값 불일치"
    )
    assert "master_raw_updated_at" in captured_payload, (
        "G-MC1: master_raw_updated_at 컬럼 payload 부재"
    )
    assert "+09:00" in captured_payload["master_raw_updated_at"], (
        "G-MC1: KST +09:00 timestamp 영역 위반 (사이클 68 G-10b 답습)"
    )


@pytest.mark.asyncio
async def test_g_mc2_get_master_raw(monkeypatch):
    """G-MC2: get_master_raw 조회 영역 (NULL/{} 부재 회피)."""
    from src.db import stock_master

    sample_master = {"mksc_shrn_iscd": "000660", "trht_yn": "Y"}

    class _StubExec:
        def __init__(self, row):
            self._row = row

        def execute(self):
            class _Resp:
                def __init__(self, data):
                    self.data = data
            return _Resp([self._row] if self._row else [])

    class _StubTable:
        def select(self, *_args, **_kwargs):
            return self

        def eq(self, *_args, **_kwargs):
            return self

        def limit(self, *_args, **_kwargs):
            return _StubExec({"ticker": "000660", "master_raw": sample_master})

    class _StubSupabase:
        def table(self, _name):
            return _StubTable()

    monkeypatch.setattr(stock_master, "supabase", _StubSupabase())

    assert hasattr(stock_master, "get_master_raw"), (
        "G-MC2: get_master_raw 함수 부재"
    )
    result = await stock_master.get_master_raw("000660")
    assert result == sample_master, (
        f"G-MC2: master_raw 조회 결함 (result={result!r})"
    )


@pytest.mark.asyncio
async def test_g_mc3_count_master_raw_today(monkeypatch):
    """G-MC3: count_master_raw_today 오늘 영역 갱신 진단."""
    from src.db import stock_master

    class _StubExec:
        def execute(self):
            class _Resp:
                count = 2697
                data = []
            return _Resp()

    class _StubTable:
        def select(self, *_args, **_kwargs):
            return self

        def gte(self, *_args, **_kwargs):
            return self

        def limit(self, *_args, **_kwargs):
            return _StubExec()

    class _StubSupabase:
        def table(self, _name):
            return _StubTable()

    monkeypatch.setattr(stock_master, "supabase", _StubSupabase())

    assert hasattr(stock_master, "count_master_raw_today"), (
        "G-MC3: count_master_raw_today 함수 부재"
    )
    result = await stock_master.count_master_raw_today()
    assert isinstance(result, int), (
        "G-MC3: count_master_raw_today int 반환 영역 위반"
    )
    assert result >= 0, "G-MC3: 음수 영역 위반"


@pytest.mark.asyncio
async def test_g_mc4_upsert_master_raw_preserves_raw_g_ast1(monkeypatch):
    """G-MC4: 사이클 81 G-AST1 영속 = upsert_master_raw 호출 후 raw 영역 변경 0.

    master_raw 별도 컬럼 채택 사유 (Q6=C) = raw 영역 덮어쓰기 금지 영속.
    """
    from src.db import stock_master

    captured_payload = {}

    class _StubExec:
        def execute(self):
            return None

    class _StubTable:
        def upsert(self, row, *, on_conflict=None):
            captured_payload.update(row)
            return _StubExec()

        def update(self, row):
            captured_payload.update(row)
            return self

        def eq(self, *_args, **_kwargs):
            return _StubExec()

    class _StubSupabase:
        def table(self, _name):
            return _StubTable()

    monkeypatch.setattr(stock_master, "supabase", _StubSupabase())

    await stock_master.upsert_master_raw("005930", {"trht_yn": "N"})

    # G-AST1 영속 (사이클 81): raw 영역 payload 미포함 영구 영속
    assert "raw" not in captured_payload, (
        "G-MC4: 사이클 81 G-AST1 위반 — upsert_master_raw 가 raw 영역 덮어쓰기 시도"
    )
    # bfdy_clpr / hts_avls 키 명시 영역 부재 의무
    assert "bfdy_clpr" not in captured_payload, (
        "G-MC4: 사이클 81 G-AST1 위반 — bfdy_clpr 덮어쓰기 시도"
    )
    assert "hts_avls" not in captured_payload, (
        "G-MC4: 사이클 81 G-AST1 위반 — hts_avls 덮어쓰기 시도"
    )
