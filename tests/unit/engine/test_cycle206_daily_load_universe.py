"""사이클 206 (2026-07-11) — _stock_master_daily_load_once 유니버스 한정 적재 (Red).

Supabase 용량 시정 (매매 무관). stock_master_daily 가 3576종목 전부 일봉 적재하나
전략은 856종목(index ∪ mcap/trade 자격)만 사용 → 2720종목(74%)=317K행=~195MB 낭비.
즉시 raw SQL 퍼지 완료(261→54MB), 이제 **재적재 방지** 코드 시정.

확정 진단:
`_stock_master_daily_load_once` 의 ticker 수집 루프 (scanner.py L2156-2163) 가
list_all 페이징 루프에서 **모든 6자리 ticker 를 all_tickers 에 append** →
비유니버스 2720종목 낭비. 시정 = index(is_kospi200/is_kosdaq150) ∪
mcap500억&trade20억(BFB 자격 최저) 만 append.

구현 명세 (backend-dev Green):
- 신규 모듈 상수 `_DAILY_LOAD_MIN_MCAP_EOK = 500` (억원, BFB min_market_cap 500억 정합)
  + `_DAILY_LOAD_MIN_TRADE_WON = 2_000_000_000` (20억, BFB min_trade_amount 정합).
- 신규 헬퍼 `_is_daily_load_universe(row) -> bool`:
    raw = row.get("raw") or {}
    int(raw.get("hts_avls") or 0) >= _DAILY_LOAD_MIN_MCAP_EOK
      AND int(raw.get("acml_tr_pbmn") or 0) >= _DAILY_LOAD_MIN_TRADE_WON
    (비숫자 try/except → False, list_by_filter 답습)
- 수집 루프: is_index or is_qualifier 게이트 → append.
  is_index 만 vcp_universe_tickers.add (사이클 172/196 backfill 분기 정합).

회귀 가드 매트릭스:
- UNIVERSE-1 (HIGH): 비유니버스 제외 — index 2 + 자격 2 + 비유니버스 3 → total=4 (현재 7 → RED)
- UNIVERSE-2: index 포함 (시총/거래대금 무관, donchian/VCP)
- UNIVERSE-3a: 자격 경계 (mcap=500억&trade=20억 포함)
- UNIVERSE-3b: 자격 경계 하회 (mcap=499억 or trade=19.9억 제외)
- UNIVERSE-4: 헬퍼 graceful (raw 부재/비숫자 → is_qualifier=False, but index 면 포함)
- UNIVERSE-5 (HIGH): VCP backfill 불변 (vcp_universe_tickers = index 종목만)
- UNIVERSE-6 (AST): 수집 루프에 is_index or is_qualifier 게이트 (미래 전량 append 재발 차단)

매매 안전성:
- scanner 16:00 daily task = 매수 진입 전 (사이클 38). risk/order_engine/realtime diff 0.
- 보유 종목 절대 보호 (사이클 32 R4) — held 종목이 비유니버스면 일봉 미적재이나
  exit 은 실시간 tick 사용 (daily 무관, prepare 는 candidate 스캔 전용) → 무영향.
  (인계로 명시.)

영속 의무:
- 사이클 122 백필/증분 분기 영속 (비유니버스 제외 후에도 index/자격 종목은 현행 유지)
- 사이클 172/196 VCP backfill 분기 영속 (is_index 만 vcp_universe)
- 사이클 88 G-REJECT graceful
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from src.engine import scanner

pytestmark = pytest.mark.unit


# BFB 자격 임계 (Green 도입 예정 상수와 정합 — 여기서는 mock 값 산정용)
_MCAP_EOK_MIN = 500  # 억원
_TRADE_WON_MIN = 1_000_000_000  # 10억 원 (2026-07 — kojiro 전체상장 정합, 20억→10억)


def _candle(bas_dd: str = "20260710") -> dict:
    return {
        "stck_bsop_date": bas_dd, "stck_clpr": "71000",
        "stck_oprc": "70500", "stck_hgpr": "71500", "stck_lwpr": "70000",
        "acml_vol": "12345678", "acml_tr_pbmn": "876543210000",
    }


def _row(
    ticker: str,
    *,
    is_kospi200: bool = False,
    is_kosdaq150: bool = False,
    hts_avls: str | int | None = None,
    acml_tr_pbmn: str | int | None = None,
    include_raw: bool = True,
) -> dict:
    """stock_master.list_all row mock — raw JSONB 안에 hts_avls(억원)/acml_tr_pbmn(원)."""
    row: dict = {
        "ticker": ticker,
        "is_kospi200": is_kospi200,
        "is_kosdaq150": is_kosdaq150,
    }
    if include_raw:
        raw: dict = {}
        if hts_avls is not None:
            raw["hts_avls"] = hts_avls
        if acml_tr_pbmn is not None:
            raw["acml_tr_pbmn"] = acml_tr_pbmn
        row["raw"] = raw
    return row


def _patched_load(stock_master_rows: list[dict], **overrides):
    """공통 patch 컨텍스트 — list_all(1페이지) + KIS/DB mock. 반환 = patch stack + mocks."""
    max_bas_dd = overrides.get(
        "max_bas_dd", AsyncMock(return_value=None)
    )
    count_by_ticker = overrides.get(
        "count_by_ticker", AsyncMock(return_value=100)
    )
    backfill_mock = overrides.get(
        "backfill_mock", AsyncMock(return_value=[_candle()])
    )
    fetch_mock = overrides.get(
        "fetch_mock", AsyncMock(return_value=[_candle()])
    )
    return patch.multiple(
        "src.db.stock_master",
        list_all=AsyncMock(side_effect=[stock_master_rows, []]),
    ), patch.multiple(
        "src.db.stock_master_daily",
        max_bas_dd=max_bas_dd,
        count_by_ticker=count_by_ticker,
        upsert_batch=AsyncMock(return_value=1),
    ), patch.multiple(
        "src.api.condition",
        fetch_daily_candles_backfill=backfill_mock,
        fetch_daily_candles=fetch_mock,
    ), patch("asyncio.sleep", new=AsyncMock()), backfill_mock, fetch_mock


# ---------------------------------------------------------------------------
# UNIVERSE-1 (HIGH) — 비유니버스 제외 (핵심 결함 재현)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_universe1_excludes_non_universe():
    """index 2 + 자격 2 + 비유니버스 3 → all_tickers = 4 (현재 7 전량 → RED)."""
    rows = [
        # index 2 (시총/거래대금 무관 항상 포함)
        _row("005930", is_kospi200=True),
        _row("247540", is_kosdaq150=True),
        # 자격 2 (mcap 500억 이상 & trade 20억 이상)
        _row("000660", hts_avls=str(_MCAP_EOK_MIN + 10),
             acml_tr_pbmn=str(_TRADE_WON_MIN + 5_000_000_000)),
        _row("035420", hts_avls=str(_MCAP_EOK_MIN + 100),
             acml_tr_pbmn=str(_TRADE_WON_MIN + 1_000_000_000)),
        # 비유니버스 3 (mcap 부족 or trade 부족)
        _row("111111", hts_avls="400",  # 400억 < 500억
             acml_tr_pbmn=str(_TRADE_WON_MIN + 1_000_000_000)),
        _row("222222", hts_avls=str(_MCAP_EOK_MIN + 100),
             acml_tr_pbmn="500000000"),  # 5억 < 10억 (임계 하향 후 여전히 미달)
        _row("333333", hts_avls="100", acml_tr_pbmn="500000000"),  # 둘 다 부족
    ]

    p1, p2, p3, sleep_p, backfill_mock, fetch_mock = _patched_load(rows)
    with p1, p2, p3, sleep_p:
        summary = await scanner._stock_master_daily_load_once()

    # summary["total"] = len(all_tickers) — 유니버스 4 만 수집
    assert summary["total"] == 4, (
        "index 2 + 자격 2 = 4 만 append, 비유니버스 3 제외 "
        f"(현재 전량 append → total=7 = RED). 실제 total={summary['total']}"
    )
    # 비유니버스 3 은 KIS 호출 자체 0 (fetch + backfill 합 = 4)
    total_kis_calls = backfill_mock.await_count + fetch_mock.await_count
    assert total_kis_calls == 4, (
        "비유니버스 3 은 일봉 fetch 자체 skip "
        f"(현재 7 호출 → RED). 실제 호출={total_kis_calls}"
    )


# ---------------------------------------------------------------------------
# UNIVERSE-2 — index 포함 (시총/거래대금 무관, donchian/VCP)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_universe2_index_always_included():
    """is_kospi200/is_kosdaq150 종목은 시총·거래대금 부족해도 항상 포함."""
    rows = [
        # index 이지만 시총/거래대금 부족 (raw 자격 미달)
        _row("005930", is_kospi200=True, hts_avls="10", acml_tr_pbmn="1"),
        _row("247540", is_kosdaq150=True, hts_avls="5", acml_tr_pbmn="0"),
    ]

    p1, p2, p3, sleep_p, backfill_mock, fetch_mock = _patched_load(rows)
    with p1, p2, p3, sleep_p:
        summary = await scanner._stock_master_daily_load_once()

    assert summary["total"] == 2, (
        "index 종목은 시총/거래대금 무관 항상 포함 (donchian/VCP 유니버스). "
        f"실제 total={summary['total']}"
    )


# ---------------------------------------------------------------------------
# UNIVERSE-3a — 자격 경계 포함 (mcap=500억 & trade=20억 정확 경계)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_universe3a_qualifier_boundary_included():
    """mcap=500억(경계) & trade=20억(경계) → 포함 (>= 비교)."""
    rows = [
        _row("000660", hts_avls=str(_MCAP_EOK_MIN),      # 정확히 500억
             acml_tr_pbmn=str(_TRADE_WON_MIN)),          # 정확히 20억
    ]

    p1, p2, p3, sleep_p, backfill_mock, fetch_mock = _patched_load(rows)
    with p1, p2, p3, sleep_p:
        summary = await scanner._stock_master_daily_load_once()

    assert summary["total"] == 1, (
        "mcap/trade 경계값(500억/20억) 은 >= 비교로 포함. "
        f"실제 total={summary['total']}"
    )


# ---------------------------------------------------------------------------
# UNIVERSE-3b — 자격 경계 하회 제외 (mcap=499억 or trade=19.9억)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_universe3b_qualifier_below_boundary_excluded():
    """mcap=499억(하회) 또는 trade=19.9억(하회) → 제외."""
    rows = [
        # mcap 하회
        _row("111111", hts_avls=str(_MCAP_EOK_MIN - 1),
             acml_tr_pbmn=str(_TRADE_WON_MIN + 1_000_000_000)),
        # trade 하회 (20억 - 1억 = 19억)
        _row("222222", hts_avls=str(_MCAP_EOK_MIN + 100),
             acml_tr_pbmn=str(_TRADE_WON_MIN - 100_000_000)),
    ]

    p1, p2, p3, sleep_p, backfill_mock, fetch_mock = _patched_load(rows)
    with p1, p2, p3, sleep_p:
        summary = await scanner._stock_master_daily_load_once()

    assert summary["total"] == 0, (
        "mcap 또는 trade 경계 하회 종목은 제외 (비유니버스). "
        f"실제 total={summary['total']}"
    )


# ---------------------------------------------------------------------------
# UNIVERSE-4 — 헬퍼 graceful (raw 부재/비숫자 → is_qualifier=False)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_universe4_helper_graceful():
    """raw 부재 / 비숫자 hts_avls/acml_tr_pbmn → is_qualifier=False (예외 전파 0).

    단, index 종목은 raw 무관 포함 (게이트 우선순위 검증).
    """
    rows = [
        # raw 부재 비-index → 제외
        _row("111111", include_raw=False),
        # 비숫자 hts_avls → 제외
        _row("222222", hts_avls="N/A", acml_tr_pbmn=str(_TRADE_WON_MIN + 1)),
        # 비숫자 acml_tr_pbmn → 제외
        _row("333333", hts_avls=str(_MCAP_EOK_MIN + 1), acml_tr_pbmn=""),
        # raw 부재이지만 index → 포함
        _row("005930", is_kospi200=True, include_raw=False),
    ]

    p1, p2, p3, sleep_p, backfill_mock, fetch_mock = _patched_load(rows)
    with p1, p2, p3, sleep_p:
        summary = await scanner._stock_master_daily_load_once()

    assert summary["total"] == 1, (
        "raw 부재/비숫자 비-index 3 제외 + index 1 포함 → total=1 (예외 전파 0). "
        f"실제 total={summary['total']}"
    )


# ---------------------------------------------------------------------------
# UNIVERSE-5 (HIGH) — VCP backfill 불변 (vcp_universe = index 종목만)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_universe5_vcp_backfill_index_only():
    """자격(비-index) 종목은 VCP backfill 미사용 (fetch_daily_candles 100일),
    index 종목만 DB<120 시 fetch_daily_candles_backfill (사이클 172/196 정합).
    """
    rows = [
        # index — VCP backfill 대상 (DB < 120)
        _row("005930", is_kospi200=True),
        # 자격(비-index) — 현행 100일 백필 (DB < 50)
        _row("000660", hts_avls=str(_MCAP_EOK_MIN + 100),
             acml_tr_pbmn=str(_TRADE_WON_MIN + 5_000_000_000)),
    ]

    captured_days: list[int] = []

    async def capture_fetch(ticker, days):
        captured_days.append(days)
        return [_candle()]

    p1, p2, p3, sleep_p, backfill_mock, fetch_mock = _patched_load(
        rows,
        count_by_ticker=AsyncMock(return_value=10),  # index<120 backfill / 자격<50 백필
        fetch_mock=AsyncMock(side_effect=capture_fetch),
    )
    with p1, p2, p3, sleep_p:
        summary = await scanner._stock_master_daily_load_once()

    # index 종목 → fetch_daily_candles_backfill 1회 (VCP)
    assert backfill_mock.await_count == 1, (
        "index 종목만 VCP backfill (fetch_daily_candles_backfill). "
        f"실제 backfill 호출={backfill_mock.await_count}"
    )
    # 자격(비-index) 종목 → 현행 100일 fetch (VCP backfill 아님)
    assert 100 in captured_days, (
        "자격(비-index) 종목은 현행 100일 fetch (사이클 122 영속). "
        f"실제 captured_days={captured_days}"
    )
    assert summary["total"] == 2


# ---------------------------------------------------------------------------
# UNIVERSE-6 (AST) — 수집 루프에 is_index or is_qualifier 게이트 (재발 차단)
# ---------------------------------------------------------------------------
def test_universe6_ast_universe_gate_present():
    """_stock_master_daily_load_once 본체에 유니버스 필터 게이트 존재 —
    미래 all_tickers 전량 append 재발 영구 차단.

    검증:
    - _is_daily_load_universe 헬퍼 정의 존재 (모듈 레벨)
    - 수집 루프에 all_tickers.append 가 is_index/is_qualifier 게이트 하에 위치
      (무조건 append 아님)
    - 모듈 상수 _DAILY_LOAD_MIN_MCAP_EOK / _DAILY_LOAD_MIN_TRADE_WON 정의
    """
    scanner_path = Path(inspect.getfile(scanner))
    tree = ast.parse(scanner_path.read_text(encoding="utf-8"))

    # (1) 헬퍼 함수 정의 존재
    helper_defs = [
        n for n in ast.walk(tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        and n.name == "_is_daily_load_universe"
    ]
    assert helper_defs, (
        "_is_daily_load_universe 헬퍼 정의 부재 — 유니버스 필터 미도입 (RED)"
    )

    # (2) 모듈 상수 2종 정의 존재
    assigned_names: set[str] = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Assign):
            for tgt in n.targets:
                if isinstance(tgt, ast.Name):
                    assigned_names.add(tgt.id)
    for const in ("_DAILY_LOAD_MIN_MCAP_EOK", "_DAILY_LOAD_MIN_TRADE_WON"):
        assert const in assigned_names, (
            f"모듈 상수 {const} 정의 부재 — 유니버스 임계 미도입 (RED)"
        )

    # (3) _stock_master_daily_load_once 본체 내 all_tickers.append 가
    #     무조건이 아님 = is_index / is_qualifier 게이트 하에 위치.
    #     소스 텍스트 검증: 헬퍼 호출(_is_daily_load_universe) 이 본체에 존재.
    body_src = inspect.getsource(scanner._stock_master_daily_load_once)
    assert "_is_daily_load_universe" in body_src, (
        "_stock_master_daily_load_once 본체가 _is_daily_load_universe 미호출 — "
        "유니버스 게이트 미배선 (RED)"
    )
    assert ("is_index" in body_src and "is_qualifier" in body_src), (
        "수집 루프 is_index/is_qualifier 게이트 미배선 (RED)"
    )


# ---------------------------------------------------------------------------
# SAFETY-1 (HIGH) — 매매 무관 (매매 hot path 참조 0)
# ---------------------------------------------------------------------------
def test_safety1_no_trading_hot_path_reference():
    """_stock_master_daily_load_once + _is_daily_load_universe(도입 시) 매매 참조 0."""
    src = inspect.getsource(scanner._stock_master_daily_load_once)
    for forbidden in ("risk.on_tick", "order_engine", "execute_buy", "execute_sell",
                      "place_order", "check_exit_signal", "check_buy_signal"):
        assert forbidden not in src, (
            f"_stock_master_daily_load_once 매매 hot path 참조 0 의무: {forbidden}"
        )
