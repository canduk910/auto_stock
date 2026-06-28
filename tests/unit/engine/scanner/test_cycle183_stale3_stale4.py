"""사이클 183 (2026-06-28) Red — stale-3 (KST 강제) + stale-4 (60s TTL 캐시 우회) 시정.

> **선행 명세**: `_workspace/red/cycle183_stale3_stale4.md`
> 둘 다 `src/engine/scanner.py` 단독. 매매 행위 변경 0
>   (stale-3 = 표시 문자열 KST / stale-4 = DB read 횟수 최적화, 필터 결과 보존).

## 결함 1 (stale-3, LOW — KST 강제 위반)
`scanner.py:681` `_last_scan_time = datetime.now().strftime("%H:%M:%S")` — naive
`datetime.now()` (서버 로컬). 바로 아랫줄 L685 는 이미 `datetime.now(KST_TZ)` 사용 → 불일치.
`_last_scan_time` 은 `get_scan_status()` 응답 `last_scan_time` (L726) 표시용.
CLAUDE.md "모든 시각 데이터 KST 강제" 위반.

- 시정 (Green): `datetime.now(KST_TZ).strftime("%H:%M:%S")` (`KST_TZ` = scanner.py:32 기정의)
- Red 가드 (행위): freezegun UTC 고정 (`2024-06-20 00:30:00+00:00` = KST 09:30) →
  `scan_stocks()` 후 `_last_scan_time == "09:30:00"`. 현재 naive → "00:30:00" → FAIL.

## 결함 2 (stale-4, LOW — 60s TTL 캐시 우회)
`scanner._apply_price_filter` (L136~) 가 L152 `pf = await get_price_filter()` 직접 호출 →
60s TTL 캐시 (`_get_price_filter_for_scanner`, L101) **우회**. `subscribe_filtered_stocks` 가
`_apply_price_filter` 를 최대 4~5회 호출 → scan 당 `get_price_filter()` DB read 최대 4~5×
(캐시가 정확히 이 용도로 존재하는데 미사용).

- 시정 (Green): `_apply_price_filter` 의 `get_price_filter()` → `_get_price_filter_for_scanner()`
  (캐시 경유). 정합성 보존: PUT 즉시 무효화는 `invalidate_price_filter_cache_scanner()`
  (L113, 사이클 64/148 PUT hook) 가 이미 담당.
- Red 가드:
  - PERF-1: 60s 내 `_apply_price_filter` 2회 → 내부 `get_price_filter`(DB read) 1회 (현재 2 → FAIL)
  - PERF-2: `subscribe_filtered_stocks` 1 scan → `get_price_filter` ≤1회 (현재 ~2~5 → FAIL)
  - CORRECT-1: invalidate 후 `_apply_price_filter` → 재호출 (즉시 반영 보존) = PASS 보존
  - CORRECT-2(a~d): 필터 동작 자체 (보유 보호 / min·max / 비활성 / bfdy_clpr miss) 불변 = PASS 보존
"""
from __future__ import annotations

import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from freezegun import freeze_time

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# 헬퍼
# ---------------------------------------------------------------------------
def _make_pf(min_price: int = 0, max_price: int = 0):
    from src.db.system_config import PriceFilter
    return PriceFilter(min_price=min_price, max_price=max_price)


def _make_basics(ticker: str, bfdy_clpr: int):
    """StockBasics mock — raw.bfdy_clpr 정본 키 (사이클 81)."""
    from src.models.stock import StockBasics
    return StockBasics(
        ticker=ticker, name=f"종목{ticker}",
        excg_dvsn_cd="1", nxt_tradable=True,
        krx_halted=False, admin_item=False,
        raw={"bfdy_clpr": str(bfdy_clpr)},
    )


async def _passthrough_taf(candidates, **kwargs):
    """거래대금 필터 passthrough — stale-4 검증은 get_price_filter 만 추적."""
    return list(candidates)


# ---------------------------------------------------------------------------
# autouse — 가격 필터 캐시 + DailyEmitCap 격리 (테스트 간 오염 차단, H-1 daily_summary 보호)
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _isolate_price_filter_cache():
    from src.engine import scanner

    def _reset():
        if hasattr(scanner, "invalidate_price_filter_cache_scanner"):
            scanner.invalidate_price_filter_cache_scanner()
        if hasattr(scanner, "reset_price_filter_daily_state"):
            scanner.reset_price_filter_daily_state()

    _reset()
    yield
    _reset()


# ===========================================================================
# stale-3 — _last_scan_time KST wall-clock (행위)
# ===========================================================================
@pytest.mark.asyncio
@freeze_time("2024-06-20 00:30:00")  # UTC 00:30 = KST 09:30 (고정 연도 2024, 사이클 176 교훈)
async def test_stale3_last_scan_time_uses_kst_wallclock():
    """stale-3: `scan_stocks()` 후 `_last_scan_time` 은 KST wall-clock 이어야 한다.

    UTC 00:30:00 고정 → KST 09:30:00.
    - 현재 (naive `datetime.now()`): "00:30:00" → FAIL (Red).
    - Green (`datetime.now(KST_TZ)`): "09:30:00" → PASS.

    매매 무관 — 표시 문자열 (`get_scan_status().last_scan_time`) 만 영향.
    """
    from src.engine import scanner

    with patch("src.engine.scanner.fetch_rising_stocks", AsyncMock(return_value=[])):
        await scanner.scan_stocks()

    assert scanner._last_scan_time == "09:30:00", (
        "stale-3 위반 — `_last_scan_time` naive `datetime.now()` (서버 로컬) 사용. "
        f"KST wall-clock '09:30:00' 의무 (실제 {scanner._last_scan_time!r}). "
        "CLAUDE.md '모든 시각 데이터 KST 강제' + L685 `datetime.now(KST_TZ)` 와 정합 위반."
    )


# ===========================================================================
# stale-4 PERF-1 — _apply_price_filter 캐시 경유 (60s 내 2회 → DB read 1회)
# ===========================================================================
@pytest.mark.asyncio
async def test_PERF1_apply_price_filter_cache_within_60s_single_db_read():
    """PERF-1: 60s 내 `_apply_price_filter` 2회 호출 → `get_price_filter`(DB read) 1회만.

    - 현재 (직접 `get_price_filter()`): 2회 호출 → DB read 2건 → FAIL (Red).
    - Green (`_get_price_filter_for_scanner()` 캐시 경유): 첫 호출 miss + 둘째 hit → 1건 → PASS.
    """
    from src.engine import scanner

    pf = _make_pf(min_price=5000, max_price=0)
    db_mock = AsyncMock(return_value=pf)
    basics = _make_basics("005930", bfdy_clpr=3000)  # below_min 차단 대상

    with patch("src.engine.scanner.get_price_filter", db_mock), \
         patch("src.db.stock_master.get", AsyncMock(return_value=basics)), \
         patch("src.db.system_logs.write_log", AsyncMock()), \
         patch("src.db.strategy_funnel.insert_snapshot", AsyncMock()):
        await scanner._apply_price_filter(["005930"], protected_tickers=set())
        await scanner._apply_price_filter(["005930"], protected_tickers=set())

    assert db_mock.call_count == 1, (
        "stale-4 PERF-1 위반 — `_apply_price_filter` 가 60s TTL 캐시 우회. "
        f"60s 내 2회 호출 시 DB read 1건 의무 (실제 {db_mock.call_count}건). "
        "`get_price_filter()` 직접 호출 → `_get_price_filter_for_scanner()` 전환 필요."
    )


# ===========================================================================
# stale-4 PERF-2 — subscribe_filtered_stocks 1 scan → get_price_filter ≤1회
# ===========================================================================
@pytest.mark.asyncio
async def test_PERF2_subscribe_one_scan_at_most_one_get_price_filter():
    """PERF-2: `subscribe_filtered_stocks` 1 scan → `get_price_filter` ≤1회.

    `subscribe_filtered_stocks` 는 `_apply_price_filter` 를 tickers(1) + extra_tickers(1)
    [+ priority_groups for-loop] 로 호출 → 캐시 우회 시 매 호출 DB read.
    - 현재: ≥2회 (tickers + extra) → FAIL (Red).
    - Green: 캐시 경유 → 1회 → PASS.

    매매 무관 — 구독 대상 집합/결과 불변 (캐시는 같은 PriceFilter 반환).
    """
    from src.engine import scanner

    pf = _make_pf(min_price=1000, max_price=2_000_000)  # active, 후보 전부 통과
    db_mock = AsyncMock(return_value=pf)

    async def fake_sm_get(ticker):
        return _make_basics(ticker, bfdy_clpr=50_000)  # min~max 사이 → 통과

    mock_ws = MagicMock()
    mock_ws.subscribe = AsyncMock()

    with patch("src.engine.scanner.get_price_filter", db_mock), \
         patch("src.db.stock_master.get", AsyncMock(side_effect=fake_sm_get)), \
         patch("src.engine.scanner._collect_protected_tickers_for_scanner",
               return_value=set()), \
         patch("src.engine.scanner._apply_trade_amount_filter", new=_passthrough_taf), \
         patch("src.engine.scanner._record_scan_pool_candidates", MagicMock()), \
         patch("src.engine.scanner.kis_ws", mock_ws), \
         patch("src.db.system_logs.write_log", AsyncMock()), \
         patch("src.db.strategy_funnel.insert_snapshot", AsyncMock()):
        await scanner.subscribe_filtered_stocks(
            ["005930", "000660"],
            extra_tickers=["035720", "035420"],
        )

    assert db_mock.call_count <= 1, (
        "stale-4 PERF-2 위반 — 1 scan 당 `get_price_filter` DB read 다회 발생. "
        f"60s TTL 캐시 경유로 ≤1회 의무 (실제 {db_mock.call_count}건)."
    )


# ===========================================================================
# stale-4 CORRECT-1 — invalidate 즉시 반영 보존 (PASS 보존)
# ===========================================================================
@pytest.mark.asyncio
async def test_CORRECT1_invalidate_forces_refetch_immediate_reflection():
    """CORRECT-1 (PASS 보존): `invalidate_price_filter_cache_scanner()` 후 다음
    `_apply_price_filter` 호출은 DB 재조회 (Settings PUT 즉시 반영 — 사이클 64/148 hook).

    현재/Green 모두 PASS 의무 — Green 전환 후에도 즉시 무효화 영속 보장.
    """
    from src.engine import scanner

    pf = _make_pf(min_price=5000, max_price=0)
    db_mock = AsyncMock(return_value=pf)
    basics = _make_basics("005930", bfdy_clpr=3000)

    with patch("src.engine.scanner.get_price_filter", db_mock), \
         patch("src.db.stock_master.get", AsyncMock(return_value=basics)), \
         patch("src.db.system_logs.write_log", AsyncMock()), \
         patch("src.db.strategy_funnel.insert_snapshot", AsyncMock()):
        # warm (캐시 채움 — Green) / 직접 호출 (현재)
        await scanner._apply_price_filter(["005930"], protected_tickers=set())
        db_mock.reset_mock()
        # Settings PUT race — 즉시 무효화
        scanner.invalidate_price_filter_cache_scanner()
        # 무효화 직후 호출은 반드시 DB 재조회
        await scanner._apply_price_filter(["005930"], protected_tickers=set())

    assert db_mock.call_count >= 1, (
        "CORRECT-1 위반 — invalidate 후 `_apply_price_filter` 가 DB 재조회 안 함. "
        "Settings PUT 즉시 반영 (5분 grace 금지) 영속 위반."
    )


# ===========================================================================
# stale-4 CORRECT-2 — 필터 동작 불변 (캐시 경유로 결과 동일, PASS 보존)
# ===========================================================================
@pytest.mark.asyncio
async def test_CORRECT2a_protected_ticker_early_return_unchanged():
    """CORRECT-2a (PASS 보존): 보유/익일청산 종목은 임계 외라도 early-return 통과.

    사이클 32 R4 + 사이클 64 Q1 옵션 D 절대 보호 — 캐시 경유 무관 불변.
    """
    from src.engine import scanner

    pf = _make_pf(min_price=0, max_price=500_000)
    basics = _make_basics("HELD01", bfdy_clpr=2_000_000)  # above_max 인데 보유

    with patch("src.engine.scanner.get_price_filter", AsyncMock(return_value=pf)), \
         patch("src.db.stock_master.get", AsyncMock(return_value=basics)), \
         patch("src.db.system_logs.write_log", AsyncMock()), \
         patch("src.db.strategy_funnel.insert_snapshot", AsyncMock()):
        result = await scanner._apply_price_filter(
            ["HELD01"], protected_tickers={"HELD01"},
        )

    assert result == ["HELD01"], (
        f"CORRECT-2a 위반 — 보유 종목 절대 보호 회귀 (실제 {result})."
    )


@pytest.mark.asyncio
async def test_CORRECT2b_min_max_block_unchanged(caplog: pytest.LogCaptureFixture):
    """CORRECT-2b (PASS 보존): below_min / above_max 차단 동작 불변 + skip emit 1행."""
    from src.engine import scanner

    pf = _make_pf(min_price=5000, max_price=100_000)

    async def fake_sm_get(ticker):
        return {
            "LOWX": _make_basics("LOWX", bfdy_clpr=3000),      # below_min
            "PASS": _make_basics("PASS", bfdy_clpr=50_000),    # 통과
            "HIGHX": _make_basics("HIGHX", bfdy_clpr=200_000), # above_max
        }[ticker]

    caplog.set_level(logging.INFO, logger="src.engine.scanner")

    with patch("src.engine.scanner.get_price_filter", AsyncMock(return_value=pf)), \
         patch("src.db.stock_master.get", AsyncMock(side_effect=fake_sm_get)), \
         patch("src.db.system_logs.write_log", AsyncMock()), \
         patch("src.db.strategy_funnel.insert_snapshot", AsyncMock()):
        result = await scanner._apply_price_filter(
            ["LOWX", "PASS", "HIGHX"], protected_tickers=set(),
        )

    assert result == ["PASS"], (
        f"CORRECT-2b 위반 — min/max 차단 회귀 (실제 {result})."
    )
    skip_logs = [r for r in caplog.records if "[price_filter_scanner_skip]" in r.message]
    assert len(skip_logs) == 2, (
        f"CORRECT-2b — 차단 2종목 skip emit 2행 의무 (실제 {len(skip_logs)}건)."
    )


@pytest.mark.asyncio
async def test_CORRECT2c_inactive_passthrough_unchanged():
    """CORRECT-2c (PASS 보존): 비활성 (0/0) → 전체 통과 + stock_master 조회 0."""
    from src.engine import scanner

    pf = _make_pf(0, 0)
    sm_get = AsyncMock()

    with patch("src.engine.scanner.get_price_filter", AsyncMock(return_value=pf)), \
         patch("src.db.stock_master.get", sm_get):
        result = await scanner._apply_price_filter(
            ["005930", "000660"], protected_tickers=set(),
        )

    assert result == ["005930", "000660"], (
        f"CORRECT-2c 위반 — 비활성 시 전체 통과 회귀 (실제 {result})."
    )
    sm_get.assert_not_called()


@pytest.mark.asyncio
async def test_CORRECT2d_bfdy_clpr_miss_graceful_unchanged():
    """CORRECT-2d (PASS 보존): bfdy_clpr 미확보 (miss / 빈 raw) → graceful 통과.

    신규 상장 1일차 영구 차단 방지 (사이클 64 Q2 + 사이클 81).
    """
    from src.engine import scanner
    from src.models.stock import StockBasics

    pf = _make_pf(min_price=5000, max_price=0)

    async def fake_sm_get(ticker):
        if ticker == "MISS":
            return None
        return StockBasics(
            ticker=ticker, name="", excg_dvsn_cd="", nxt_tradable=False,
            krx_halted=False, admin_item=False, raw={},  # 빈 raw
        )

    with patch("src.engine.scanner.get_price_filter", AsyncMock(return_value=pf)), \
         patch("src.db.stock_master.get", AsyncMock(side_effect=fake_sm_get)), \
         patch("src.db.system_logs.write_log", AsyncMock()), \
         patch("src.db.strategy_funnel.insert_snapshot", AsyncMock()):
        result = await scanner._apply_price_filter(
            ["MISS", "EMPTY"], protected_tickers=set(),
        )

    assert set(result) == {"MISS", "EMPTY"}, (
        f"CORRECT-2d 위반 — bfdy_clpr 미확보 graceful 통과 회귀 (실제 {result})."
    )
