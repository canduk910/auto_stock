"""사이클 170 카드 A — list_by_filter 단계 노출 (return_stage_counts).

결함: donchian prepare step1/step2 둘 다 survived=tickers (동일 변수) → attrition
(union 348 → 시총컷 348 → 거래대금컷 321) 미노출. list_by_filter 가 단일 호출로
union+시총+거래대금 한 번에 수행하고 최종 list 만 반환.

채택안: `list_by_filter(return_stage_counts=True)` 단일 호출 단일 진실.
- union: index/형식/exclude 통과, 시총·거래대금 컷 전
- mcap: 시총컷 후
- trade: 거래대금컷 후 (= 최종 filtered)
- True → (filtered, {union_tickers, mcap_tickers, trade_tickers}), False → filtered (현행)

회귀 가드 (A 6 케이스):
- G-A-1 (HIGH): True 의 filtered == False 의 결과 (원소+순서). 매수 풀 불변 핵심.
- G-A-2: union ⊇ mcap ⊇ trade, len(trade)==len(filtered) 단조.
- G-A-3: 실측 348/348/321 픽스처.
- G-A-4: 미지정 호출자 → list (tuple 아님).
- G-A-5: donchian prepare step1=348/step2=321 collapse 차단.
- G-A-6 (AST): 시그너처 keyword + donchian _scan_universe 전달.

사이클 205 (2026-07-09, phase 1) 의미 전환: `list_by_filter` 가 DB-side 생성 컬럼 gte
전환으로 return_stage_counts=True 시 3쿼리(union/mcap/trade) 구조로 바뀜 — 단일 mock rows
로는 3단계(union⊇mcap⊇trade) 를 재현 못하므로 `_run_filter`/`g_a_1`/`g_a_2`/`g_a_3` 가
per-execute rows 시퀀스(다중 `.execute()` 지원)를 주입하도록 갱신. `g_a_4`/`g_a_5`/`g_a_6`
은 단일 쿼리(return_stage_counts 미지정) 또는 직접 monkeypatch/시그너처 검사라 무변경.
상세 근거는 `_workspace/red/cycle205_list_by_filter_db_side.md` 참조.
"""
from __future__ import annotations

import ast
import asyncio
import inspect
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.unit


def _make_row(
    ticker: str,
    hts_avls: str = "10000",
    acml_tr_pbmn: str = "50000000000",
    excg_dvsn_cd: str = "02",
    nxt_tradable: bool = True,
    name: str = "테스트종목",
    is_kospi200: bool = True,
    is_kosdaq150: bool = False,
) -> dict:
    return {
        "ticker": ticker,
        "name": name,
        "excg_dvsn_cd": excg_dvsn_cd,
        "nxt_tradable": nxt_tradable,
        "is_kospi200": is_kospi200,
        "is_kosdaq150": is_kosdaq150,
        "raw": {"hts_avls": hts_avls, "acml_tr_pbmn": acml_tr_pbmn},
    }


def _run_filter(rows, **kwargs):
    """단일 rows (모든 pg.fetch 동일 응답) — return_stage_counts=False 또는
    3쿼리 모두 같은 rows 를 받아도 되는(union==mcap==trade) 단순 케이스용.

    사이클 M2b — pg.fetch 경유. mock 은 이미 DB-side 필터링된 rows 를 반환 →
    production 이 _post_filter (exclude/limit) 만 적용.
    """
    from unittest.mock import AsyncMock

    with patch.object(_sm(), "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(return_value=rows)
        return asyncio.run(_sm().list_by_filter(**kwargs))


def _run_filter_staged(rows_per_execute: list[list[dict]], **kwargs):
    """사이클 M2b — per-fetch rows 시퀀스 주입 (3쿼리: union/mcap/trade 각자 다른 rows).

    return_stage_counts=True 시 production 이 pg.fetch 를 3회(union→mcap→trade) 발화 →
    side_effect 로 순서대로 다음 rows 반환.
    """
    from unittest.mock import AsyncMock

    with patch.object(_sm(), "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(side_effect=list(rows_per_execute))
        return asyncio.run(_sm().list_by_filter(**kwargs))


def _sm():
    import src.db.stock_master as sm
    return sm


# ------------------------------------------------------------------
# G-A-1 (HIGH) — 행위 보존: True 의 filtered == False 의 결과
# ------------------------------------------------------------------
def test_g_a_1_filtered_identical_with_and_without_stage_counts():
    """return_stage_counts=True 의 filtered 가 False 의 결과와 원소·순서 동일.

    사이클 205 — DB-side 3쿼리 구조. base(단일 쿼리, `_run_filter`)는 전량(4건)을 받아
    Python 미필터(=DB 가 이미 필터링했다고 가정)로 그대로 반환하고, paired(3쿼리)는
    trade 쿼리(마지막)가 base 와 동일 rows 를 받도록 주입 — trade 쿼리 = 최종 filtered.
    """
    all_rows = [
        _make_row("000001", hts_avls="2000", acml_tr_pbmn="50000000000"),
        _make_row("000002", hts_avls="500", acml_tr_pbmn="50000000000"),   # 시총 탈락 (union 만)
        _make_row("000003", hts_avls="2000", acml_tr_pbmn="1000000000"),   # 거래대금 탈락 (union/mcap)
        _make_row("000004", hts_avls="3000", acml_tr_pbmn="80000000000"),
    ]
    # DB-side gte 가 이미 필터링했다고 가정한 trade(=최종) 결과 — 000002/000003 탈락.
    trade_only_rows = [all_rows[0], all_rows[3]]
    kw = dict(min_market_cap=100_000_000_000, min_trade_amount=10_000_000_000)

    base = _run_filter(trade_only_rows, **kw)
    paired = _run_filter_staged(
        [all_rows, [all_rows[0], all_rows[3]], trade_only_rows],
        return_stage_counts=True, **kw,
    )

    assert isinstance(paired, tuple), "return_stage_counts=True → tuple 반환 의무"
    filtered_paired, stage = paired
    base_tickers = [r["ticker"] for r in base]
    paired_tickers = [r["ticker"] for r in filtered_paired]
    assert base_tickers == paired_tickers, (
        f"매수 풀 불변 위반 — base={base_tickers} paired={paired_tickers}"
    )


# ------------------------------------------------------------------
# G-A-2 — 단조 감소: union ⊇ mcap ⊇ trade, len(trade)==len(filtered)
# ------------------------------------------------------------------
def test_g_a_2_stage_monotonic():
    """union ⊇ mcap ⊇ trade, len(trade_tickers)==len(filtered) 단조.

    사이클 205 — 3쿼리 per-execute rows 주입 (union 3건 → mcap 2건(000002 시총탈락)
    → trade 1건(000003 거래대금탈락)).
    """
    r1 = _make_row("000001", hts_avls="2000", acml_tr_pbmn="50000000000")
    r2 = _make_row("000002", hts_avls="500", acml_tr_pbmn="50000000000")
    r3 = _make_row("000003", hts_avls="2000", acml_tr_pbmn="1000000000")

    filtered, stage = _run_filter_staged(
        [[r1, r2, r3], [r1, r3], [r1]],
        min_market_cap=100_000_000_000, min_trade_amount=10_000_000_000,
        return_stage_counts=True,
    )
    union = stage["union_tickers"]
    mcap = stage["mcap_tickers"]
    trade = stage["trade_tickers"]

    assert set(mcap) <= set(union), "mcap ⊄ union"
    assert set(trade) <= set(mcap), "trade ⊄ mcap"
    assert len(union) >= len(mcap) >= len(trade)
    assert len(trade) == len(filtered), "trade_tickers != filtered"
    assert [r["ticker"] for r in filtered] == trade


# ------------------------------------------------------------------
# G-A-3 — 실측 348/348/321 패턴 재현 (시총컷 통과율 100%, 거래대금컷 일부 탈락)
# ------------------------------------------------------------------
def test_g_a_3_realistic_attrition_348_348_321():
    """union=N → mcap=N (시총 전부 통과) → trade<N (거래대금 일부 탈락) 패턴.

    사이클 205 — 3쿼리 per-execute rows 주입: union=mcap=348(시총 전부 통과) 이므로
    두 쿼리는 동일 348 rows, trade 쿼리는 321 rows(거래대금 27건 탈락 반영 완료)만 반환.
    """
    all_348 = [
        _make_row(f"{i:06d}", hts_avls="2000", acml_tr_pbmn="50000000000")
        for i in range(348)
    ]
    trade_321 = all_348[:321]  # 마지막 27종목 거래대금 미달 → DB gte 가 이미 제외

    filtered, stage = _run_filter_staged(
        [all_348, all_348, trade_321],
        min_market_cap=50_000_000_000, min_trade_amount=10_000_000_000,
        limit=500, return_stage_counts=True,
    )
    assert len(stage["union_tickers"]) == 348
    assert len(stage["mcap_tickers"]) == 348
    assert len(stage["trade_tickers"]) == 321
    assert len(filtered) == 321


# ------------------------------------------------------------------
# G-A-4 — 미지정 호출자 회귀: list (tuple 아님)
# ------------------------------------------------------------------
def test_g_a_4_default_returns_list_not_tuple():
    """return_stage_counts 미지정 → list 반환 (기존 호출자 회귀 0)."""
    rows = [_make_row("000001")]
    result = _run_filter(rows, min_market_cap=100_000_000_000)
    assert isinstance(result, list), "미지정 호출자 list 반환 위반"
    assert not isinstance(result, tuple)


# ------------------------------------------------------------------
# G-A-5 — donchian prepare step1=union / step2=trade collapse 차단
# ------------------------------------------------------------------
@pytest.mark.asyncio
async def test_g_a_5_donchian_step1_union_step2_trade(monkeypatch):
    """donchian prepare 후 step1 survived_count=union, step2=trade (collapse 차단)."""
    from src.engine.strategies.donchian_swing import DonchianSwingStrategy
    from src.engine.strategy_base import StrategyConfig

    strat = DonchianSwingStrategy(StrategyConfig(strategy_id="donchian_swing", name="dc"))

    # _scan_universe 가 stage counts 를 인스턴스 필드에 보관 + filtered 반환
    async def _fake_scan(self):
        self._scan_stage_counts = {
            "union_tickers": [f"{i:06d}" for i in range(348)],
            "mcap_tickers": [f"{i:06d}" for i in range(348)],
            "trade_tickers": [f"{i:06d}" for i in range(321)],
        }
        return [f"{i:06d}" for i in range(321)]

    monkeypatch.setattr(DonchianSwingStrategy, "_scan_universe", _fake_scan)

    async def _empty_block(self, tickers):
        return tickers, []

    monkeypatch.setattr(
        DonchianSwingStrategy, "_apply_master_block_filter_in_prepare", _empty_block
    )

    # fetch_daily_candles 모킹 (모든 ticker 빈 candle → 후속 단계 0, step1/2 만 검증)
    import src.api.condition as _cond

    async def _empty_candles(ticker, days=0):
        return []

    monkeypatch.setattr(_cond, "fetch_daily_candles", _empty_candles)

    await strat.prepare()

    step1 = next(s for s in strat._funnel_steps if s["step_no"] == 1)
    step2 = next(s for s in strat._funnel_steps if s["step_no"] == 2)
    assert step1["survived_count"] == 348, (
        f"step1 union 미반영 — count={step1['survived_count']} (collapse 결함)"
    )
    assert step2["survived_count"] == 321, (
        f"step2 거래대금컷 미반영 — count={step2['survived_count']} (collapse 결함)"
    )


# ------------------------------------------------------------------
# G-A-6 (AST) — 시그너처 keyword + donchian 전달
# ------------------------------------------------------------------
def test_g_a_6_ast_signature_and_donchian_call():
    """list_by_filter 에 return_stage_counts keyword 존재 + donchian 가 True 전달."""
    import src.db.stock_master as sm

    sig = inspect.signature(sm.list_by_filter)
    assert "return_stage_counts" in sig.parameters, (
        "list_by_filter 에 return_stage_counts keyword 부재"
    )
    assert sig.parameters["return_stage_counts"].default is False, (
        "return_stage_counts 기본값 False 아님 (회귀 보존 위반)"
    )

    from src.engine.strategies import donchian_swing

    src = Path(inspect.getfile(donchian_swing)).read_text(encoding="utf-8")
    tree = ast.parse(src)
    found = False
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "list_by_filter"
        ):
            for kw in node.keywords:
                if (
                    kw.arg == "return_stage_counts"
                    and isinstance(kw.value, ast.Constant)
                    and kw.value.value is True
                ):
                    found = True
    assert found, "donchian _scan_universe 가 return_stage_counts=True 미전달"
