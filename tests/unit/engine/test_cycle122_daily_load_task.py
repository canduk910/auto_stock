"""사이클 122 (2026-06-12) — _stock_master_daily_load_once + task lifecycle 회귀 가드.

회귀 가드 매트릭스:
- G-SCAN1 (HIGH) — _stock_master_daily_load_once stock_master 전체 ticker 적재
- G-SCAN2 (HIGH) — 점진 적재 idempotency (max_bas_dd >= today → skip)
- G-SCAN3 (HIGH) — 백필 vs 증분 자동 분기 (count < 225 백필 / >= 225 증분)
- G-SCAN4 (MEDIUM) — Rate Limit 50ms sleep (사이클 83/91/97/107 답습)
- G-SCAN5 (MEDIUM) — graceful (KIS fetch 실패 시 다음 ticker 진행)
- G-SCHED1 (HIGH) — TIME_STOCK_MASTER_DAILY_LOAD = 16:00 KST
- G-SCHED2 (HIGH) — task cancel 목록에 _stock_master_daily_load_task 포함

⚠️ **cycle302 의미 전환 — 분기가 지나가는 *함수* 가 바뀌었다(명제는 그대로).**
종전 분기는 `count < 50 → fetch_daily_candles(days=100)` / `>= 50 → days=7` 이었다.
cycle302 가 backfill 대상을 적재 대상 전부로 넓히면서 게이트가
`existing_count < _DAILY_LOAD_VCP_BACKFILL_DAYS(225)` 하나가 됐고, 그 분기는
**`condition.fetch_daily_candles_backfill`**(분할 3콜)을 부른다. 100일 단발 분기
(`_DAILY_LOAD_INCREMENTAL_THRESHOLD=50`)는 `225 > 50` 인 한 **도달 불가**한 구조적
폴백이다(그 관계는 `test_cycle302_backfill_scope_expansion.py::G-302-8b` 가 핀한다).
그래서 이 파일은 같은 명제("얕으면 백필 · 깊으면 증분 · 실패는 graceful")를 **새
경로 기준으로** 다시 잰다 — 단언을 지우거나 약화시키지 않는다.

🔴 `no_real_kis` opt-in — 이 파일은 backfill 분기를 의도적으로 탄다. 두 fetch 중
하나라도 모킹을 빠뜨리면 실 KIS 를 때리므로(2026-09-18 CI red 의 기전) 공통 관문
`condition.kis_get_quote` 를 막아 그 누락이 네트워크가 아니라 즉시 실패가 되게 한다.

영속 의무:
- 사이클 14 fetch_daily_candles 재사용
- 사이클 38 명문화 (scanner 매수 진입 전 영역)
- 사이클 79 G-AST2 task cancel 영속
- 사이클 88 G-REJECT graceful
- 사이클 106 lifecycle race 차단
"""

from __future__ import annotations

import asyncio
import inspect
from datetime import date, time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.engine import scanner, scheduler, data_load_tasks

pytestmark = [pytest.mark.unit, pytest.mark.usefixtures("no_real_kis")]

#: 수렴 상태(목표 깊이 이상) — 증분 분기를 타는 `count_by_ticker` 값.
#: 리터럴 대신 상수 파생이라 목표 깊이가 바뀌어도 의도가 따라 움직인다.
_CONVERGED_COUNT = scanner._DAILY_LOAD_VCP_BACKFILL_DAYS + 10


# ---------------------------------------------------------------------------
# G-SCAN1 (HIGH) — _stock_master_daily_load_once 영역 호출 + summary 정합
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_g_scan1_load_once_iterates_stock_master():
    """stock_master 전체 ticker → 각 ticker 별 KIS fetch + upsert_batch.

    cycle302 의미 전환 — `count_by_ticker=0`(신규 적재)은 이제 분할 backfill 분기다.
    재는 명제("적재 대상 전 종목이 빠짐없이 fetch 를 탄다")는 그대로이고, 세는 목만
    `fetch_daily_candles` → `fetch_daily_candles_backfill` 로 옮겼다.
    """
    stock_master_rows = [
        {"ticker": "005930", "raw": {"hts_avls": "1000", "acml_tr_pbmn": "5000000000"}},
        {"ticker": "000660", "raw": {"hts_avls": "1000", "acml_tr_pbmn": "5000000000"}},
        {"ticker": "035420", "raw": {"hts_avls": "1000", "acml_tr_pbmn": "5000000000"}},
    ]
    mock_candles = [
        {"stck_bsop_date": "20260612", "stck_clpr": "71000",
         "stck_oprc": "70000", "stck_hgpr": "71500", "stck_lwpr": "69500",
         "acml_vol": "12345678", "acml_tr_pbmn": "876543210000"},
    ]

    with patch(
        "src.db.stock_master.list_all",
        new=AsyncMock(side_effect=[stock_master_rows, []]),
    ), patch(
        "src.db.stock_master_daily.max_bas_dd",
        new=AsyncMock(return_value=None),  # 신규 적재
    ), patch(
        "src.db.stock_master_daily.count_by_ticker",
        new=AsyncMock(return_value=0),  # 백필 모드
    ), patch(
        "src.api.condition.fetch_daily_candles_backfill",
        new=AsyncMock(return_value=mock_candles),
    ) as mock_backfill, patch(
        "src.api.condition.fetch_daily_candles",
        new=AsyncMock(return_value=mock_candles),
    ) as mock_kis, patch(
        "src.db.stock_master_daily.upsert_batch",
        new=AsyncMock(return_value=1),
    ) as mock_upsert, patch(
        "asyncio.sleep", new=AsyncMock(),
    ):
        summary = await scanner._stock_master_daily_load_once()

    assert summary["total"] == 3
    assert summary["fetched"] == 3
    assert summary["upserted_rows"] == 3
    assert summary["failed"] == 0
    assert mock_backfill.call_count == 3, (
        "신규 적재(count=0) 3종목은 전부 분할 backfill 분기다 (cycle302). "
        f"실제 backfill 호출={mock_backfill.call_count}"
    )
    assert mock_kis.call_count == 0, (
        "얕은 종목이 단발 fetch 로 새면 목표 깊이에 영원히 못 닿는다. "
        f"실제 단발 fetch 호출={mock_kis.call_count}"
    )
    assert mock_upsert.call_count == 3


# ---------------------------------------------------------------------------
# G-SCAN2 (HIGH) — max_bas_dd >= today → skip (idempotency)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_g_scan2_skip_when_already_loaded_today():
    """오늘 이미 적재된 ticker 는 KIS 호출 skip (점진 적재 영구 영속)."""
    from src.db._kst import today_kst

    today = today_kst()
    stock_master_rows = [{"ticker": "005930", "raw": {"hts_avls": "1000", "acml_tr_pbmn": "5000000000"}}]

    with patch(
        "src.db.stock_master.list_all",
        new=AsyncMock(side_effect=[stock_master_rows, []]),
    ), patch(
        "src.db.stock_master_daily.max_bas_dd",
        new=AsyncMock(return_value=today),  # 이미 오늘 적재됨
    ), patch(
        "src.api.condition.fetch_daily_candles",
        new=AsyncMock(),
    ) as mock_kis, patch(
        "asyncio.sleep", new=AsyncMock(),
    ):
        summary = await scanner._stock_master_daily_load_once()

    assert summary["skipped_fresh"] == 1
    assert summary["fetched"] == 0
    assert not mock_kis.called  # KIS 호출 0건 (idempotency)


# ---------------------------------------------------------------------------
# G-SCAN3 (HIGH) — 백필 vs 증분 자동 분기
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_g_scan3_backfill_when_count_below_threshold():
    """count < 225 → 백필 모드 (목표 깊이 분할 backfill).

    cycle302 의미 전환 — 종전에는 `count < 50 → fetch_daily_candles(days=100)` 였다.
    지금은 얕은 종목이 **전부** `fetch_daily_candles_backfill(total_days=225)` 를 탄다.
    `count=10` 은 그대로 둔다(그 값이 재려던 것은 "얕다" 이고, 10 은 두 임계 아래다).
    """
    stock_master_rows = [{"ticker": "005930", "raw": {"hts_avls": "1000", "acml_tr_pbmn": "5000000000"}}]

    captured_days: list[int] = []
    captured_total_days: list[int] = []

    async def capture_kis_call(ticker, days):
        captured_days.append(days)
        return [{"stck_bsop_date": "20260612", "stck_clpr": "71000"}]

    async def capture_backfill_call(ticker, total_days=None):
        captured_total_days.append(total_days)
        return [{"stck_bsop_date": "20260612", "stck_clpr": "71000"}]

    with patch(
        "src.db.stock_master.list_all",
        new=AsyncMock(side_effect=[stock_master_rows, []]),
    ), patch(
        "src.db.stock_master_daily.max_bas_dd",
        new=AsyncMock(return_value=date(2026, 6, 1)),  # 11일 전
    ), patch(
        "src.db.stock_master_daily.count_by_ticker",
        new=AsyncMock(return_value=10),  # 10건 < 225 = 백필
    ), patch(
        "src.api.condition.fetch_daily_candles_backfill",
        new=AsyncMock(side_effect=capture_backfill_call),
    ), patch(
        "src.api.condition.fetch_daily_candles",
        new=AsyncMock(side_effect=capture_kis_call),
    ), patch(
        "src.db.stock_master_daily.upsert_batch",
        new=AsyncMock(return_value=1),
    ), patch(
        "asyncio.sleep", new=AsyncMock(),
    ):
        await scanner._stock_master_daily_load_once()

    assert captured_total_days == [scanner._DAILY_LOAD_VCP_BACKFILL_DAYS], (
        "얕은 종목은 목표 깊이 분할 backfill 이다 (cycle302). "
        f"실제 total_days={captured_total_days}"
    )
    assert captured_days == [], (
        "단발 fetch 로 새면 그 종목은 목표 깊이에 못 닿는다. "
        f"실제 captured_days={captured_days}"
    )


@pytest.mark.asyncio
async def test_g_scan3_incremental_when_count_above_threshold():
    """count >= 225 → 증분 모드 (T-7일 호출).

    cycle302 의미 전환 — 종전 값 `100` 은 당시 임계(50) 위였지만 지금은 목표
    깊이(225) 아래라 **backfill 로 샌다**. 이 테스트가 재려던 것은 "수렴한 종목은
    증분 1콜" 이므로 값을 수렴 상태로 올린다.
    """
    stock_master_rows = [{"ticker": "005930", "raw": {"hts_avls": "1000", "acml_tr_pbmn": "5000000000"}}]

    captured_days: list[int] = []

    async def capture_kis_call(ticker, days):
        captured_days.append(days)
        return [{"stck_bsop_date": "20260612", "stck_clpr": "71000"}]

    with patch(
        "src.db.stock_master.list_all",
        new=AsyncMock(side_effect=[stock_master_rows, []]),
    ), patch(
        "src.db.stock_master_daily.max_bas_dd",
        new=AsyncMock(return_value=date(2026, 6, 10)),
    ), patch(
        "src.db.stock_master_daily.count_by_ticker",
        new=AsyncMock(return_value=_CONVERGED_COUNT),  # >= 225 = 증분
    ), patch(
        "src.api.condition.fetch_daily_candles_backfill",
        new=AsyncMock(side_effect=AssertionError("수렴한 종목이 재 backfill 을 탔다")),
    ) as mock_backfill, patch(
        "src.api.condition.fetch_daily_candles",
        new=AsyncMock(side_effect=capture_kis_call),
    ), patch(
        "src.db.stock_master_daily.upsert_batch",
        new=AsyncMock(return_value=1),
    ), patch(
        "asyncio.sleep", new=AsyncMock(),
    ):
        await scanner._stock_master_daily_load_once()

    assert captured_days == [7]  # 증분 = T-7일
    assert mock_backfill.await_count == 0, (
        "수렴 상태(count >= 225)에서 재 backfill 이 돌면 매일 밤 KIS 호출이 3배다 "
        "(cycle302 의 무비용 근거 = G-302-3)"
    )


# ---------------------------------------------------------------------------
# G-SCAN4 (MEDIUM) — Rate Limit 50ms sleep (사이클 83/91/97/107 답습)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_g_scan4_rate_limit_50ms_per_ticker():
    """ticker 간 50ms sleep — KIS LMS chain 안전 마진."""
    stock_master_rows = [{"ticker": "005930", "raw": {"hts_avls": "1000", "acml_tr_pbmn": "5000000000"}}, {"ticker": "000660", "raw": {"hts_avls": "1000", "acml_tr_pbmn": "5000000000"}}]
    sleep_durations: list[float] = []

    async def capture_sleep(duration):
        sleep_durations.append(duration)

    with patch(
        "src.db.stock_master.list_all",
        new=AsyncMock(side_effect=[stock_master_rows, []]),
    ), patch(
        "src.db.stock_master_daily.max_bas_dd",
        new=AsyncMock(return_value=None),
    ), patch(
        "src.db.stock_master_daily.count_by_ticker",
        new=AsyncMock(return_value=0),
    ), patch(
        # cycle302 — count=0 은 backfill 분기다. 분기가 어디로 가든 ticker 당 50ms 는
        # 지켜져야 하므로 두 fetch 를 **둘 다** 모킹해 실 KIS 를 원천 차단한다.
        "src.api.condition.fetch_daily_candles_backfill",
        new=AsyncMock(return_value=[{"stck_bsop_date": "20260612", "stck_clpr": "71000"}]),
    ), patch(
        "src.api.condition.fetch_daily_candles",
        new=AsyncMock(return_value=[{"stck_bsop_date": "20260612", "stck_clpr": "71000"}]),
    ), patch(
        "src.db.stock_master_daily.upsert_batch",
        new=AsyncMock(return_value=1),
    ), patch(
        "asyncio.sleep", side_effect=capture_sleep,
    ):
        await scanner._stock_master_daily_load_once()

    # 2 ticker × 1 sleep/ticker = 2건 (모두 50ms)
    rate_limit_sleeps = [d for d in sleep_durations if d == 0.05]
    assert len(rate_limit_sleeps) == 2


# ---------------------------------------------------------------------------
# G-SCAN5 (MEDIUM) — KIS fetch 실패 시 graceful (다음 ticker 진행)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_g_scan5_graceful_on_kis_failure():
    """KIS 일봉 fetch 실패 시 다음 ticker 진행 — 사이클 88 G-REJECT.

    cycle302 의미 전환 — `count=0` 은 backfill 분기라 실패를 주입할 목도
    `fetch_daily_candles_backfill` 이다. 재는 명제(한 종목의 KIS 실패가 나머지
    적재를 멈추지 않는다)는 그대로다.
    """
    stock_master_rows = [{"ticker": "005930", "raw": {"hts_avls": "1000", "acml_tr_pbmn": "5000000000"}}, {"ticker": "000660", "raw": {"hts_avls": "1000", "acml_tr_pbmn": "5000000000"}}]

    async def kis_side_effect(ticker, total_days=None):
        if ticker == "005930":
            raise RuntimeError("KIS rate limit")
        return [{"stck_bsop_date": "20260612", "stck_clpr": "71000"}]

    with patch(
        "src.db.stock_master.list_all",
        new=AsyncMock(side_effect=[stock_master_rows, []]),
    ), patch(
        "src.db.stock_master_daily.max_bas_dd",
        new=AsyncMock(return_value=None),
    ), patch(
        "src.db.stock_master_daily.count_by_ticker",
        new=AsyncMock(return_value=0),
    ), patch(
        "src.api.condition.fetch_daily_candles_backfill",
        side_effect=kis_side_effect,
    ), patch(
        "src.api.condition.fetch_daily_candles",
        new=AsyncMock(side_effect=AssertionError("신규 적재가 단발 fetch 로 샜다")),
    ), patch(
        "src.db.stock_master_daily.upsert_batch",
        new=AsyncMock(return_value=1),
    ), patch(
        "asyncio.sleep", new=AsyncMock(),
    ):
        summary = await scanner._stock_master_daily_load_once()

    assert summary["failed"] == 1
    assert summary["fetched"] == 1  # 두 번째 ticker 는 성공


# ---------------------------------------------------------------------------
# G-SCHED1 (HIGH) — TIME_STOCK_MASTER_DAILY_LOAD = 20:30 KST (cycle283)
# ---------------------------------------------------------------------------
def test_g_sched1_time_constant_is_20_30():
    """TIME_STOCK_MASTER_DAILY_LOAD = time(20, 30) — cycle283(2026-09-11, 사용자 결정 D2).

    이력: 16:00(사이클 122) → 18:10(cycle273f, 시간외 단일가 ~18:00 물량) → **20:30**.
    09-14(월)부터 KRX 애프터마켓 16:00~20:00 실시간 체결이 신설돼 그날 거래가 20:00 에
    끝나고, 일봉 **거래량**은 그동안 계속 는다(09-11 실측: OHLC 는 15:30 확정, 거래량은
    시간외 내내 증가 — 16:14 저장분 대비 중앙값 +0.51%·최대 +13.97%).
    20:30 은 애프터마켓 종료 후이고, 실측 전량 스윕 121초라 정산(21:30) 앞에 끝난다.
    """
    assert scheduler.TIME_STOCK_MASTER_DAILY_LOAD == time(20, 30)


# ---------------------------------------------------------------------------
# G-SCHED2 (HIGH) — task cancel 목록 포함 (3 곳 모두)
# ---------------------------------------------------------------------------
def test_g_sched2_stock_master_daily_load_task_in_cancel_tuples():
    """stop() + run_daily.finally + start.finally 3 곳 모두 cancel 목록 포함."""
    src = inspect.getsource(scheduler)
    # _stock_master_daily_load_task 가 cancel 튜플 3 곳 모두 포함되었는지 정적 검증
    count = src.count('"_stock_master_daily_load_task"')
    assert count >= 3, (
        f"_stock_master_daily_load_task 가 cancel 튜플 3 곳 모두에 포함되어야 함. "
        f"실제 등장 횟수={count}"
    )


# ---------------------------------------------------------------------------
# G-SCHED3 (MEDIUM) — _stock_master_daily_load_task_loop 메서드 존재
# ---------------------------------------------------------------------------
def test_g_sched3_task_loop_method_exists():
    """_stock_master_daily_load_task_loop 메서드 존재 + start() 직후 즉시 1회 실행.

    사이클 134 의미 전환 (카드 #21 — refactor-review 권고 채택) — 사이클 66 K-2 패턴 답습:
    - Red 시점 (사이클 122) = facade 본체 `while self._running` + `초기 실행 완료` 인라인
    - Green 시점 (사이클 134) = `run_periodic_task_loop` 헬퍼 위임 + lifecycle 영역 헬퍼 흡수
    - 핵심 의도 보존: 메서드 영속 + _wait_until 정합 + 즉시 실행 + while 영속 (헬퍼 흡수).
    """
    sched = scheduler.TradingScheduler()
    assert hasattr(sched, "_stock_master_daily_load_task_loop")
    assert callable(sched._stock_master_daily_load_task_loop)

    # refactor-review B1 (2026-08-09) — 본체 data_load_tasks 위임 이관. wrapper(TIME_) + 본체(helper) 결합.
    src = inspect.getsource(sched._stock_master_daily_load_task_loop) + \
        inspect.getsource(data_load_tasks.stock_master_daily_load_task_loop)
    # _wait_until 인자 정합 영속 (facade 또는 헬퍼 인자 영역 영구 영속)
    assert "TIME_STOCK_MASTER_DAILY_LOAD" in src, (
        "TIME_STOCK_MASTER_DAILY_LOAD 인자 영속 부재 — facade 영속 의무 위반"
    )

    # 사이클 134 의미 전환 — 헬퍼 위임 OR 인라인 영역 영구 영속
    has_helper = "run_periodic_task_loop" in src
    has_inline = "while self._running" in src and ("초기 실행 완료" in src or "초기 실행 예외" in src)
    assert has_helper or has_inline, (
        "lifecycle race 차단 패턴 영속 부재 — "
        "Red 시점 (인라인) 또는 Green 시점 (헬퍼 위임) 영속 의무 위반"
    )

    if has_helper:
        # 헬퍼 영역 영구 영속에서 lifecycle 흡수 영속
        from pathlib import Path
        helper_src = Path("src/engine/task_loop_helper.py").read_text(encoding="utf-8")
        assert "while scheduler._running" in helper_src
        assert "초기 실행" in helper_src
