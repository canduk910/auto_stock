"""사이클 24 (2026-05-20) — 세션 단위 silent inactive 자동 감지 + 강제 reconnect.

배경:
- 2026-05-20 14:58 운영 결함: 메인 세션 sub=11 ack=11 fresh=0 stale=11 (4분 안정 후도 회복 안 됨).
  종목별 unsubscribe+subscribe 재등록(K stale watcher 사이클 17 보강) 으로 회복 안 됨.
- 근본 원인: KIS 측 메인 appkey 세션 silent inactive 적용. 세션 자체 결함이라 종목별 재등록 무효.

처방:
- K stale watcher (120s 주기) 가 종목 단위 외에 세션 단위 silent inactive 도 감지.
- 5분 지속 후 `_force_reconnect_session(label)` 으로 `_ws.close()` 발화 → 자동 재연결 → 새 세션 재구독.
- 시간당 2회 cap (KIS 측 무한 재연결 회피, LMS / 앱 정지 위험 차단).

회귀 가드 (8 케이스):
1. fresh=0 + sub>=5 + 5분 미달 → 감지 안 함 (대기)
2. fresh=0 + sub>=5 + 5분 도달 → 감지 + _force_reconnect_session 호출
3. fresh=1 (일부 tick) → 감지 안 함 (silent 아님) + _silent_inactive_first_seen 리셋
4. sub<5 → 감지 안 함 (거래량 부족 자연)
5. 메인 세션 force_reconnect → kis_ws._ws.close() 호출 검증
6. 보조 세션 force_reconnect → pool._quotes[idx]._ws.close() 호출 검증
7. 시간당 2회 cap — 60분 내 3회 시도 시 3번째 SKIP + WARNING
8. 시간당 cap 만료 후 — 60분+ 경과 후 다시 가능
"""
from __future__ import annotations

import time as _time_mod
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = pytest.mark.unit

KST = timezone(timedelta(hours=9))
NOW = datetime(2026, 5, 20, 15, 0, 0, tzinfo=KST)


def _make_session(label: str, subscribed: int, tickers: list[str] | None = None) -> dict:
    """테스트용 세션 상태 dict 생성."""
    t_list = tickers if tickers is not None else [f"00000{i}" for i in range(subscribed)]
    return {
        "label": label,
        "subscribed": subscribed,
        "acked": subscribed,
        "limit": 41,
        "ws_connected": True,
        "reconnect_count": 0,
        "tickers": {
            "subscribed": t_list,
            "acked": t_list,
        },
    }


@pytest.fixture
def scheduler_inst():
    """TradingScheduler 인스턴스 (단위 테스트용)."""
    from src.engine.scheduler import TradingScheduler
    return TradingScheduler()


# ---------------------------------------------------------------------------
# 1. fresh=0 + sub>=5 + 5분 미달 → 감지 안 함 (first_seen 등록만)
# ---------------------------------------------------------------------------
def test_silent_inactive_5min_not_reached(scheduler_inst):
    """fresh=0 + sub>=5 충족하지만 5분 미달 → 감지 안 함 (first_seen 만 등록)."""
    from src.engine import scheduler as sch_mod

    tickers = [f"00000{i}" for i in range(11)]
    sessions = [_make_session("main", subscribed=11, tickers=tickers)]

    with patch.object(sch_mod, "kis_ws_pool") as mock_pool:
        mock_pool.get_session_status = MagicMock(return_value=sessions)
        # ticker_last_tick 빈 dict → fresh=0 (모든 종목 tick 없음)
        with patch("src.engine.scanner.ticker_last_tick", {}):
            with patch("src.engine.scheduler.datetime") as mock_dt:
                mock_dt.now.return_value = NOW
                mock_dt.min = datetime.min
                # 첫 호출 — first_seen 등록, 5분 미달이므로 감지 안 함
                result = scheduler_inst._detect_silent_inactive_sessions()

    assert result == [], f"5분 미달 시 감지 안 함 — got {result}"
    assert "main" in scheduler_inst._silent_inactive_first_seen, "first_seen 등록 확인"


# ---------------------------------------------------------------------------
# 2. fresh=0 + sub>=5 + 5분 도달 → 감지 + _force_reconnect_session 호출
# ---------------------------------------------------------------------------
def test_silent_inactive_5min_reached(scheduler_inst):
    """fresh=0 + sub>=5 + 5분 도달 → label 반환."""
    from src.engine import scheduler as sch_mod

    tickers = [f"00000{i}" for i in range(11)]
    sessions = [_make_session("main", subscribed=11, tickers=tickers)]
    # 5분 초과 이전 시각 사전 등록
    five_min_ago = NOW - timedelta(seconds=sch_mod.SILENT_INACTIVE_PERSIST_SECS + 1)
    scheduler_inst._silent_inactive_first_seen["main"] = five_min_ago

    with patch.object(sch_mod, "kis_ws_pool") as mock_pool:
        mock_pool.get_session_status = MagicMock(return_value=sessions)
        with patch("src.engine.scanner.ticker_last_tick", {}):
            with patch("src.engine.scheduler.datetime") as mock_dt:
                mock_dt.now.return_value = NOW
                mock_dt.min = datetime.min
                result = scheduler_inst._detect_silent_inactive_sessions()

    assert "main" in result, f"5분 도달 시 label 반환 — got {result}"


# ---------------------------------------------------------------------------
# 3. fresh_ratio >= 0.2 (일부 tick) → 감지 안 함 + first_seen 리셋
# ---------------------------------------------------------------------------
def test_silent_inactive_fresh_partial_no_detect(scheduler_inst):
    """fresh_ratio >= 임계 (정상 tick 흐름) → silent 아님 → first_seen 미등록 (리셋).

    사이클 29-R2 (2026-05-21) 의미 갱신: 기존 `fresh=1/11 (9%)` 는 R2 후 silent 판정됨.
    본 케이스는 `fresh=4/11 (36%) >= 20%` 임계 *이상* 시나리오로 갱신 — 정상 흐름.
    """
    from src.engine import scheduler as sch_mod

    tickers = [f"00000{i}" for i in range(11)]
    sessions = [_make_session("main", subscribed=11, tickers=tickers)]
    # first_seen 사전 등록 → 회복 시 pop 검증
    scheduler_inst._silent_inactive_first_seen["main"] = NOW - timedelta(seconds=100)

    # 4 종목 fresh (36% — 임계 20% 이상, 정상 흐름)
    last_tick_map = {tickers[i]: NOW - timedelta(seconds=10) for i in range(4)}

    with patch.object(sch_mod, "kis_ws_pool") as mock_pool:
        mock_pool.get_session_status = MagicMock(return_value=sessions)
        with patch("src.engine.scanner.ticker_last_tick", last_tick_map):
            with patch("src.engine.scheduler.datetime") as mock_dt:
                mock_dt.now.return_value = NOW
                mock_dt.min = datetime.min
                result = scheduler_inst._detect_silent_inactive_sessions()

    assert result == [], f"fresh_ratio 정상 시 감지 안 함 — got {result}"
    assert "main" not in scheduler_inst._silent_inactive_first_seen, "first_seen pop 확인"


# ---------------------------------------------------------------------------
# 4. sub<5 → 감지 안 함 (거래량 부족 자연)
# ---------------------------------------------------------------------------
def test_silent_inactive_sub_below_threshold(scheduler_inst):
    """subscribed<5 → 위양성 차단 (거래량 부족 자연) → 감지 안 함."""
    from src.engine import scheduler as sch_mod

    tickers = [f"00000{i}" for i in range(3)]
    sessions = [_make_session("main", subscribed=3, tickers=tickers)]

    with patch.object(sch_mod, "kis_ws_pool") as mock_pool:
        mock_pool.get_session_status = MagicMock(return_value=sessions)
        with patch("src.engine.scanner.ticker_last_tick", {}):
            with patch("src.engine.scheduler.datetime") as mock_dt:
                mock_dt.now.return_value = NOW
                mock_dt.min = datetime.min
                result = scheduler_inst._detect_silent_inactive_sessions()

    assert result == [], f"sub<5 시 감지 안 함 — got {result}"
    assert "main" not in scheduler_inst._silent_inactive_first_seen, "first_seen 미등록 확인"


# ---------------------------------------------------------------------------
# 5. 메인 세션 force_reconnect → kis_ws._ws.close() 호출 + 상태 갱신
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_force_reconnect_main_session(scheduler_inst):
    """메인 세션 → kis_ws._ws.close() 호출 + first_seen pop + history append."""
    mock_ws = AsyncMock()
    mock_ws.close = AsyncMock()

    scheduler_inst._silent_inactive_first_seen["main"] = NOW

    # write_log mock
    async def _noop_write_log(*a, **kw):
        return None

    with patch("src.engine.scheduler.kis_ws") as mock_kis_ws, \
         patch("src.engine.scheduler.write_log", _noop_write_log):
        mock_kis_ws._ws = mock_ws
        result = await scheduler_inst._force_reconnect_session("main")

    assert result is True, "메인 세션 reconnect 성공"
    mock_ws.close.assert_awaited_once()
    assert "main" not in scheduler_inst._silent_inactive_first_seen, "first_seen pop 확인"
    assert len(scheduler_inst._silent_inactive_recovery_count["main"]) == 1, "history append 확인"


# ---------------------------------------------------------------------------
# 6. 보조 세션 force_reconnect → pool._quotes[idx]._ws.close() 호출
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_force_reconnect_quote_session(scheduler_inst):
    """보조 세션 quote-1 → pool._quotes[0]._ws.close() 호출."""
    mock_ws = AsyncMock()
    mock_ws.close = AsyncMock()
    mock_quote_session = MagicMock()
    mock_quote_session._ws = mock_ws

    scheduler_inst._silent_inactive_first_seen["quote-1"] = NOW

    async def _noop_write_log(*a, **kw):
        return None

    with patch("src.engine.scheduler.kis_ws_pool") as mock_pool, \
         patch("src.engine.scheduler.write_log", _noop_write_log):
        mock_pool._quotes = [mock_quote_session]
        result = await scheduler_inst._force_reconnect_session("quote-1")

    assert result is True, "보조 세션 reconnect 성공"
    mock_ws.close.assert_awaited_once()
    assert "quote-1" not in scheduler_inst._silent_inactive_first_seen, "first_seen pop 확인"


# ---------------------------------------------------------------------------
# 7. 시간당 2회 cap — 60분 내 3회 시도 시 3번째 SKIP + WARNING
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_force_reconnect_hourly_cap(scheduler_inst):
    """60분 내 3번째 reconnect 시도 → SKIP + WARNING + _ws.close() 호출 안 함."""
    mock_ws = AsyncMock()
    mock_ws.close = AsyncMock()

    now_mono = _time_mod.time()
    # 2회 이미 시도 (30분 전 + 10분 전)
    scheduler_inst._silent_inactive_recovery_count["main"] = [
        now_mono - 1800.0,
        now_mono - 600.0,
    ]
    scheduler_inst._silent_inactive_first_seen["main"] = NOW

    async def _noop_write_log(*a, **kw):
        return None

    with patch("src.engine.scheduler.kis_ws") as mock_kis_ws, \
         patch("src.engine.scheduler.write_log", _noop_write_log):
        mock_kis_ws._ws = mock_ws
        result = await scheduler_inst._force_reconnect_session("main")

    assert result is False, "cap 도달 시 SKIP"
    mock_ws.close.assert_not_awaited()


# ---------------------------------------------------------------------------
# 8. 시간당 cap 만료 후 — 60분+ 경과 후 다시 가능
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_force_reconnect_cap_expired(scheduler_inst):
    """60분+ 경과 후 history 자동 정리 → 다시 reconnect 가능."""
    mock_ws = AsyncMock()
    mock_ws.close = AsyncMock()

    now_mono = _time_mod.time()
    # 2회 이미 시도했지만 모두 70분+ 전 → 만료
    scheduler_inst._silent_inactive_recovery_count["main"] = [
        now_mono - 4200.0,  # 70분
        now_mono - 4500.0,  # 75분
    ]
    scheduler_inst._silent_inactive_first_seen["main"] = NOW

    async def _noop_write_log(*a, **kw):
        return None

    with patch("src.engine.scheduler.kis_ws") as mock_kis_ws, \
         patch("src.engine.scheduler.write_log", _noop_write_log):
        mock_kis_ws._ws = mock_ws
        result = await scheduler_inst._force_reconnect_session("main")

    assert result is True, "cap 만료 후 reconnect 가능"
    mock_ws.close.assert_awaited_once()
    # 만료 항목 제거 후 새 항목 추가 → 총 1개
    assert len(scheduler_inst._silent_inactive_recovery_count["main"]) == 1, \
        "만료 항목 제거 + 신규 추가 후 1개"
