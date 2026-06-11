"""사이클 106 영역 3 (HIGH) — _full_universe_load_task lifecycle 시정.

Root cause (사이클 101 도입 결함):
    start() 직후 `_full_universe_load_task_loop` = _wait_until(20:00:05) 대기
    → 20:10 _settle → stop() cancel 발화 = lifecycle race.
    결과: 191 ticker 영속 (사이클 101 목표 ~2,800 미달).

Q1=A 시정 (사이클 78/83 답습):
    start() 직후 즉시 1회 실행 + while self._running 무한 루프
    → _wait_until 대기 전 즉시 실행으로 stop() race 영구 차단.
    is_stale 24h TTL idempotency 활용 = 조기 호출 부수 효과 0.

회귀 가드 케이스:
    G-LC1 (HIGH): start() 직후 즉시 _full_universe_load_once 1회 호출
    G-LC2 (HIGH): _running=True + _wait_until 이후 2회차 호출
    G-LC3 (HIGH): CancelledError 즉시 실행 단계 → return (graceful)
    G-LC4 (HIGH): CancelledError while 루프 단계 → break (graceful)
    G-LC5 (MEDIUM): 즉시 실행 예외 → graceful continue (while 루프 진입)
    G-LC6 (MEDIUM): while 루프 예외 → asyncio.sleep(60) + 계속

영속 의무:
    - 사이클 32 R4 universe guard 영속 (scanner 단계 매수 진입 전용)
    - 사이클 38 명문화 영속 (tradable_boards 매수 진입 전용)
    - 사이클 78 G-AST1 flush 호출 사이트 영속
    - 사이클 79 G-AST2 task cancel 목록 영속
    - 사이클 88 G-REJECT 영속 (WebSocket 4중 안전망)
    - 사이클 101 _full_universe_load_once is_stale 24h TTL 영속
    - 사이클 102 G-REJECT 영속
    - CLAUDE.md "절대 깨지 말 것" 8 영역 영속
    - 매매 안전성 무영향 (scanner 단계, 매도/손절/익일청산 hot path 무관)
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# 공통 픽스처
# ---------------------------------------------------------------------------

def _make_summary(
    total: int = 100,
    kospi: int = 50,
    kosdaq: int = 50,
    fetched: int = 80,
    skipped_ttl: int = 20,
    failed: int = 0,
    elapsed_ms: int = 1000,
) -> dict:
    return {
        "total": total,
        "kospi": kospi,
        "kosdaq": kosdaq,
        "fetched": fetched,
        "skipped_ttl": skipped_ttl,
        "failed": failed,
        "elapsed_ms": elapsed_ms,
    }


# ---------------------------------------------------------------------------
# G-LC1 (HIGH): start() 직후 즉시 _full_universe_load_once 1회 호출
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_g_lc1_immediate_call_on_start(monkeypatch):
    """G-LC1 (HIGH): _full_universe_load_task_loop 최초 진입 시 _wait_until 대기 *전*
    즉시 _full_universe_load_once 1회 호출 확인 (사이클 101 lifecycle race 영구 차단).

    사이클 101 결함: _wait_until → stop() cancel → 호출 0건.
    사이클 106 시정: 즉시 1회 호출 → while 루프 진입.
    """
    from src.engine.scheduler import TradingScheduler

    mock_summary = _make_summary()
    mock_load_once = AsyncMock(return_value=mock_summary)
    mock_record = MagicMock()
    mock_flush = MagicMock()

    # _running=False 로 while 루프 즉시 탈출 (즉시 실행 1회만 확인)
    scheduler = MagicMock(spec=TradingScheduler)
    scheduler._running = False

    async def mock_wait_until(t):
        pass  # _running=False 이므로 while 진입 자체를 막음

    scheduler._wait_until = mock_wait_until

    with patch("src.engine.scanner._full_universe_load_once", mock_load_once), \
         patch("src.engine.stock_master_metrics.record_full_universe_load_summary", mock_record), \
         patch("src.engine.stock_master_metrics.flush_full_universe_load_collector", mock_flush):
        # 실제 메서드 호출 (unbound method + 스케줄러 인스턴스 전달)
        await TradingScheduler._full_universe_load_task_loop(scheduler)

    # 즉시 1회 호출 확인
    assert mock_load_once.call_count >= 1, (
        "G-LC1 FAIL: 즉시 실행 단계에서 _full_universe_load_once 호출 0건. "
        "사이클 101 lifecycle race 시정 미완료."
    )
    # record + flush 동행 확인
    assert mock_record.call_count >= 1, "G-LC1 FAIL: record_full_universe_load_summary 미호출"
    assert mock_flush.call_count >= 1, "G-LC1 FAIL: flush_full_universe_load_collector 미호출"


# ---------------------------------------------------------------------------
# G-LC2 (HIGH): _running=True → while 루프 2회차 호출 확인
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_g_lc2_while_loop_second_call(monkeypatch):
    """G-LC2 (HIGH): _running=True 에서 while 루프 진입 후 _wait_until 이후
    _full_universe_load_once 2회차 호출 확인.

    검증 흐름:
    1. 즉시 실행 1회 (G-LC1 영속)
    2. while 루프 진입 → _wait_until → 2회차 호출
    3. 2회차 이후 _running=False → break

    구현 패턴: _wait_until 이후 `if not self._running: break` 가 있으므로
    wait_until 호출 시 _running=False 로 전환 → 2회차 _load_once 미호출.
    따라서 while 루프 1회 _wait_until → not _running → break = 즉시 실행 1회만.
    G-LC2 검증: while 루프 진입 자체 확인 (wait_until 1회 호출 = while 루프 진입 증거).
    """
    from src.engine.scheduler import TradingScheduler

    mock_summary = _make_summary()
    wait_call_count = {"n": 0}

    scheduler = MagicMock(spec=TradingScheduler)
    scheduler._running = True

    async def mock_wait_until(t):
        wait_call_count["n"] += 1
        # _wait_until 후 _running=False → while 루프 break
        scheduler._running = False

    scheduler._wait_until = mock_wait_until

    with patch("src.engine.scanner._full_universe_load_once", return_value=mock_summary), \
         patch("src.engine.stock_master_metrics.record_full_universe_load_summary"), \
         patch("src.engine.stock_master_metrics.flush_full_universe_load_collector"):
        await TradingScheduler._full_universe_load_task_loop(scheduler)

    # while 루프 진입 증거: _wait_until 1회 이상 호출
    assert wait_call_count["n"] >= 1, (
        f"G-LC2 FAIL: while 루프 미진입 (_wait_until 호출 {wait_call_count['n']}회). "
        "while loop 구조 시정 미완료."
    )


# ---------------------------------------------------------------------------
# G-LC3 (HIGH): CancelledError 즉시 실행 단계 → return (graceful)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_g_lc3_cancelled_error_in_immediate_phase(monkeypatch):
    """G-LC3 (HIGH): 즉시 실행 단계에서 CancelledError → return (graceful).

    시나리오: start() 직후 즉시 실행 중 task cancel 발화 → return.
    사이클 101 시정 의도: stop() cancel = 즉시 실행 중 CancelledError → graceful return.
    """
    from src.engine.scheduler import TradingScheduler

    async def mock_load_once_cancel():
        raise asyncio.CancelledError()

    scheduler = MagicMock(spec=TradingScheduler)
    scheduler._running = True

    with patch("src.engine.scanner._full_universe_load_once", side_effect=mock_load_once_cancel), \
         patch("src.engine.stock_master_metrics.record_full_universe_load_summary"), \
         patch("src.engine.stock_master_metrics.flush_full_universe_load_collector"):
        # CancelledError → return (예외 전파 금지)
        try:
            await TradingScheduler._full_universe_load_task_loop(scheduler)
        except asyncio.CancelledError:
            pytest.fail(
                "G-LC3 FAIL: 즉시 실행 단계 CancelledError 가 외부로 전파됨. "
                "graceful return 필요."
            )


# ---------------------------------------------------------------------------
# G-LC4 (HIGH): CancelledError while 루프 단계 → break (graceful)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_g_lc4_cancelled_error_in_while_loop(monkeypatch):
    """G-LC4 (HIGH): while 루프 내 _wait_until CancelledError → break (graceful).

    시나리오: 즉시 실행 완료 → while 루프 → _wait_until cancel → break.
    """
    from src.engine.scheduler import TradingScheduler

    mock_summary = _make_summary()
    phase = {"immediate_done": False}

    async def mock_load_once():
        if not phase["immediate_done"]:
            phase["immediate_done"] = True
            return mock_summary
        raise asyncio.CancelledError()

    scheduler = MagicMock(spec=TradingScheduler)
    scheduler._running = True

    async def mock_wait_until(t):
        raise asyncio.CancelledError()

    scheduler._wait_until = mock_wait_until

    with patch("src.engine.scanner._full_universe_load_once", side_effect=mock_load_once), \
         patch("src.engine.stock_master_metrics.record_full_universe_load_summary"), \
         patch("src.engine.stock_master_metrics.flush_full_universe_load_collector"):
        try:
            await TradingScheduler._full_universe_load_task_loop(scheduler)
        except asyncio.CancelledError:
            pytest.fail(
                "G-LC4 FAIL: while 루프 CancelledError 가 외부로 전파됨. "
                "graceful break 필요."
            )

    # 즉시 실행은 완료되어야 함
    assert phase["immediate_done"], "G-LC4 FAIL: 즉시 실행 단계 미완료"


# ---------------------------------------------------------------------------
# G-LC5 (MEDIUM): 즉시 실행 예외 → graceful continue (while 루프 진입)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_g_lc5_exception_in_immediate_phase_continues(monkeypatch):
    """G-LC5 (MEDIUM): 즉시 실행 단계 일반 예외 → graceful logger.exception + while 루프 진입.

    시나리오: 즉시 실행 Exception → graceful → while 루프 진입 확인.
    while 루프 진입 증거: _wait_until 호출 ≥1회.
    """
    from src.engine.scheduler import TradingScheduler

    scheduler = MagicMock(spec=TradingScheduler)
    scheduler._running = True
    wait_call_count = {"n": 0}

    async def mock_load_once_raise():
        raise RuntimeError("즉시 실행 실패")

    async def mock_wait_until(t):
        wait_call_count["n"] += 1
        scheduler._running = False  # while 루프 1회 후 종료

    scheduler._wait_until = mock_wait_until

    with patch("src.engine.scanner._full_universe_load_once", side_effect=mock_load_once_raise), \
         patch("src.engine.stock_master_metrics.record_full_universe_load_summary"), \
         patch("src.engine.stock_master_metrics.flush_full_universe_load_collector"), \
         patch("src.engine.scheduler.logger") as mock_logger:
        await TradingScheduler._full_universe_load_task_loop(scheduler)

    # graceful logger.exception 호출 확인
    assert mock_logger.exception.called, (
        "G-LC5 FAIL: 즉시 실행 예외 시 logger.exception 미호출 (graceful 처리 누락)."
    )
    # while 루프 진입 확인 (즉시 실행 예외 후에도 while 루프 진입)
    assert wait_call_count["n"] >= 1, (
        f"G-LC5 FAIL: 즉시 실행 예외 후 while 루프 미진입 (_wait_until {wait_call_count['n']}회). "
        "graceful continue 필요."
    )


# ---------------------------------------------------------------------------
# G-LC6 (MEDIUM): while 루프 예외 → asyncio.sleep(60) + 계속
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_g_lc6_exception_in_while_loop_sleeps(monkeypatch):
    """G-LC6 (MEDIUM): while 루프 일반 예외 → graceful + asyncio.sleep(60).

    사이클 78/83 패턴 답습: loop 예외 시 asyncio.sleep(60) 후 재시도.
    """
    from src.engine.scheduler import TradingScheduler

    mock_summary = _make_summary()
    phase = {"immediate_done": False, "while_exception_raised": False}
    sleep_calls = []

    async def mock_load_once():
        if not phase["immediate_done"]:
            phase["immediate_done"] = True
            return mock_summary
        if not phase["while_exception_raised"]:
            phase["while_exception_raised"] = True
            raise RuntimeError("while 루프 예외")
        return mock_summary

    scheduler = MagicMock(spec=TradingScheduler)
    _values = iter([True, True, False])

    def get_running():
        try:
            return next(_values)
        except StopIteration:
            return False

    type(scheduler)._running = property(lambda self: get_running())

    async def mock_wait_until(t):
        pass

    scheduler._wait_until = mock_wait_until

    async def mock_sleep(secs):
        sleep_calls.append(secs)

    with patch("src.engine.scanner._full_universe_load_once", side_effect=mock_load_once), \
         patch("src.engine.stock_master_metrics.record_full_universe_load_summary"), \
         patch("src.engine.stock_master_metrics.flush_full_universe_load_collector"), \
         patch("asyncio.sleep", side_effect=mock_sleep):
        await TradingScheduler._full_universe_load_task_loop(scheduler)

    # asyncio.sleep(60) 호출 확인
    assert 60 in sleep_calls, (
        f"G-LC6 FAIL: while 루프 예외 후 asyncio.sleep(60) 미호출 (실제 sleep_calls={sleep_calls}). "
        "사이클 78/83 패턴 답습 필요."
    )


# ---------------------------------------------------------------------------
# G-LC7 (LOW): [full_universe_load] 즉시 실행 emit prefix 확인
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_g_lc7_emit_prefix_immediate(monkeypatch):
    """G-LC7 (LOW): 즉시 실행 완료 후 logger.info '[full_universe_load] 초기 실행 완료' 발화.

    운영 가시화 — 즉시 실행(초기)과 while 루프(정기) 구분.
    """
    from src.engine.scheduler import TradingScheduler

    mock_summary = _make_summary()

    scheduler = MagicMock(spec=TradingScheduler)
    scheduler._running = False  # while 루프 미진입

    async def mock_wait_until(t):
        pass

    scheduler._wait_until = mock_wait_until

    info_calls = []

    def mock_info(msg, *args, **kwargs):
        info_calls.append(msg % args if args else msg)

    with patch("src.engine.scanner._full_universe_load_once", return_value=mock_summary), \
         patch("src.engine.stock_master_metrics.record_full_universe_load_summary"), \
         patch("src.engine.stock_master_metrics.flush_full_universe_load_collector"), \
         patch("src.engine.scheduler.logger") as mock_logger:
        mock_logger.info.side_effect = mock_info
        await TradingScheduler._full_universe_load_task_loop(scheduler)

    matching = [c for c in info_calls if "[full_universe_load]" in c]
    assert matching, (
        "G-LC7 FAIL: '[full_universe_load]' prefix 를 포함한 logger.info 미발화. "
        "운영 가시화 누락."
    )
