"""사이클 29-R2 (2026-05-21) — silent_inactive 판정 비율 기반 전환.

배경 (실측 결함 — 2026-05-21 13:13~13:29 운영 로그):
- 메인 세션: `fresh=2/25 (8%) stale=23` (사이클 24 _detect_silent_inactive_sessions 미판정)
- 강제 reconnect 0건 발화 — 사이클 24 정의 `fresh == 0` 분기에 `fresh=2 > 0` 이라 미충족
- 결과: 92% stale 인데 silent inactive 미판정 → R1 종목별 force_retry 에만 의존

처방:
- 정의 완화: `fresh == 0` → `fresh_ratio < SILENT_INACTIVE_FRESH_RATIO_THRESHOLD (=0.2, 20%)`
- 3중 가드 구조 보존: 비율 + sub>=5 + 5분 지속
- 시간당 2회 cap 절대 보존 (LMS / 앱키 정지 위험 차단 — KIS 공지)
- 5분 지속 보존 (단발 끊김 즉시 close 차단)
- sub>=5 보존 (위양성 차단, 빈 세션 무시)

R2 회귀 가드:
- N-1: `SILENT_INACTIVE_FRESH_RATIO_THRESHOLD == 0.2` 상수 노출
- N-2: fresh=0 분기 자동 호환 (0/N = 0.0 < 0.2 → silent 판정 보존)
- N-3: fresh=2/25 (8%, 실측 결함 시나리오) → silent 판정 + 5분 도달 시 label 반환
- N-4: fresh=5/25 (20%, 임계 경계) → silent 판정 안 함 (`< 0.2` 미충족, `>=` 아님)
- N-5: fresh=4/25 (16%, 임계 미만) → silent 판정
- N-6: fresh=20/25 (80%) → silent 판정 안 함 + first_seen 리셋
- N-7: fresh_ratio < 0.2 + sub=4 → 감지 안 함 (sub>=5 가드 보존)
- N-8: fresh_ratio < 0.2 + 5분 미달 → first_seen 등록만, 감지 안 함
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.unit

KST = timezone(timedelta(hours=9))
NOW = datetime(2026, 5, 21, 13, 25, 0, tzinfo=KST)


def _make_session(label: str, subscribed: int, tickers: list[str] | None = None) -> dict:
    """테스트용 세션 상태 dict 생성."""
    t_list = tickers if tickers is not None else [f"{i:06d}" for i in range(subscribed)]
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
    """TradingScheduler 인스턴스."""
    from src.engine.scheduler import TradingScheduler
    return TradingScheduler()


# ===========================================================================
# N-1: 상수 노출 검증
# ===========================================================================
def test_silent_inactive_fresh_ratio_threshold_is_0_2():
    """``SILENT_INACTIVE_FRESH_RATIO_THRESHOLD == 0.2`` 노출.

    사이클 29-R2: 메인 세션 fresh=2/25 (8%) 실측 결함 대응. 20% 미만 fresh 시 silent 판정.
    """
    from src.engine import scheduler

    assert scheduler.SILENT_INACTIVE_FRESH_RATIO_THRESHOLD == 0.2, (
        "사이클 29-R2: 메인 8% 실측 결함 대응 — 20% 미만 fresh ratio 시 silent 판정"
    )


# ===========================================================================
# N-2: fresh=0 분기 자동 호환 (회귀 가드)
# ===========================================================================
def test_zero_fresh_still_detected_after_ratio_change(scheduler_inst):
    """fresh=0/11 (0%) → 기존 사이클 24 동작 보존 (0 < 0.2 자동 충족).

    사이클 24 회귀 가드: ratio 정의 도입해도 기존 fresh=0 케이스는 자동 포함.
    """
    from src.engine import scheduler as sch_mod

    tickers = [f"00000{i}" for i in range(11)]
    sessions = [_make_session("main", subscribed=11, tickers=tickers)]
    # 5분 도달 사전 세팅
    five_min_ago = NOW - timedelta(seconds=sch_mod.SILENT_INACTIVE_PERSIST_SECS + 1)
    scheduler_inst._silent_inactive_first_seen["main"] = five_min_ago

    with patch.object(sch_mod, "kis_ws_pool") as mock_pool:
        mock_pool.get_session_status = MagicMock(return_value=sessions)
        with patch("src.engine.scanner.ticker_last_tick", {}):  # 전부 stale
            with patch("src.engine.scheduler.datetime") as mock_dt:
                mock_dt.now.return_value = NOW
                mock_dt.min = datetime.min
                result = scheduler_inst._detect_silent_inactive_sessions()

    assert "main" in result, f"fresh=0 케이스 자동 호환 — got {result}"


# ===========================================================================
# N-3: fresh=2/25 (8%, 실측 결함 시나리오) → silent 판정
# ===========================================================================
def test_low_fresh_ratio_detects_silent_real_world_scenario(scheduler_inst):
    """실측 결함 재현 — fresh=2/25 (8%) + sub>=5 + 5분 도달 → silent 판정.

    2026-05-21 13:13~13:29 메인 세션 결함 시나리오. R2 핵심 검증.
    """
    from src.engine import scheduler as sch_mod

    tickers = [f"{i:06d}" for i in range(25)]
    sessions = [_make_session("main", subscribed=25, tickers=tickers)]
    # 5분 도달 사전 세팅
    five_min_ago = NOW - timedelta(seconds=sch_mod.SILENT_INACTIVE_PERSIST_SECS + 1)
    scheduler_inst._silent_inactive_first_seen["main"] = five_min_ago

    # 2개만 fresh (10초 전 tick)
    last_tick_map = {
        tickers[0]: NOW - timedelta(seconds=10),
        tickers[1]: NOW - timedelta(seconds=10),
    }
    # 나머지 23개는 stale (last_tick 부재)

    with patch.object(sch_mod, "kis_ws_pool") as mock_pool:
        mock_pool.get_session_status = MagicMock(return_value=sessions)
        with patch("src.engine.scanner.ticker_last_tick", last_tick_map):
            with patch("src.engine.scheduler.datetime") as mock_dt:
                mock_dt.now.return_value = NOW
                mock_dt.min = datetime.min
                result = scheduler_inst._detect_silent_inactive_sessions()

    assert "main" in result, (
        f"fresh=2/25 (8%, 실측 결함) 시나리오 silent 판정 누락 — got {result}. "
        f"사이클 29-R2 회복 결함 — 비율 기반 전환 안 됨."
    )


# ===========================================================================
# N-4: fresh=5/25 (20%, 임계 경계) → silent 판정 안 함 (`< 0.2` 미충족)
# ===========================================================================
def test_boundary_ratio_exact_threshold_not_detected(scheduler_inst):
    """fresh=5/25 (정확히 20%) → silent 판정 안 함 (`< 0.2` 엄격 비교).

    경계 정책: 임계 미만(<) 만 silent. 정확히 20% 는 정상 범주.
    """
    from src.engine import scheduler as sch_mod

    tickers = [f"{i:06d}" for i in range(25)]
    sessions = [_make_session("main", subscribed=25, tickers=tickers)]
    # 사전 first_seen 등록 → 임계 미충족 시 pop 검증
    scheduler_inst._silent_inactive_first_seen["main"] = NOW - timedelta(seconds=100)

    # 5개 fresh (정확히 20%)
    last_tick_map = {tickers[i]: NOW - timedelta(seconds=10) for i in range(5)}

    with patch.object(sch_mod, "kis_ws_pool") as mock_pool:
        mock_pool.get_session_status = MagicMock(return_value=sessions)
        with patch("src.engine.scanner.ticker_last_tick", last_tick_map):
            with patch("src.engine.scheduler.datetime") as mock_dt:
                mock_dt.now.return_value = NOW
                mock_dt.min = datetime.min
                result = scheduler_inst._detect_silent_inactive_sessions()

    assert result == [], f"정확히 20% 임계 silent 판정 안 함 — got {result}"
    # 정상 범주 → first_seen pop
    assert "main" not in scheduler_inst._silent_inactive_first_seen


# ===========================================================================
# N-5: fresh=4/25 (16%, 임계 미만) → silent 판정
# ===========================================================================
def test_below_threshold_ratio_detects_silent(scheduler_inst):
    """fresh=4/25 (16% < 20%) + sub>=5 + 5분 도달 → silent 판정."""
    from src.engine import scheduler as sch_mod

    tickers = [f"{i:06d}" for i in range(25)]
    sessions = [_make_session("main", subscribed=25, tickers=tickers)]
    five_min_ago = NOW - timedelta(seconds=sch_mod.SILENT_INACTIVE_PERSIST_SECS + 1)
    scheduler_inst._silent_inactive_first_seen["main"] = five_min_ago

    last_tick_map = {tickers[i]: NOW - timedelta(seconds=10) for i in range(4)}

    with patch.object(sch_mod, "kis_ws_pool") as mock_pool:
        mock_pool.get_session_status = MagicMock(return_value=sessions)
        with patch("src.engine.scanner.ticker_last_tick", last_tick_map):
            with patch("src.engine.scheduler.datetime") as mock_dt:
                mock_dt.now.return_value = NOW
                mock_dt.min = datetime.min
                result = scheduler_inst._detect_silent_inactive_sessions()

    assert "main" in result, f"16% 미만 임계 silent 판정 누락 — got {result}"


# ===========================================================================
# N-6: fresh=20/25 (80%, 정상) → silent 판정 안 함 + first_seen pop
# ===========================================================================
def test_high_fresh_ratio_no_detect_and_reset(scheduler_inst):
    """fresh=20/25 (80%) → silent 판정 안 함 + first_seen 리셋."""
    from src.engine import scheduler as sch_mod

    tickers = [f"{i:06d}" for i in range(25)]
    sessions = [_make_session("main", subscribed=25, tickers=tickers)]
    # 사전 첫 감지 시각 → 회복 시 pop 검증
    scheduler_inst._silent_inactive_first_seen["main"] = NOW - timedelta(seconds=200)

    last_tick_map = {tickers[i]: NOW - timedelta(seconds=10) for i in range(20)}

    with patch.object(sch_mod, "kis_ws_pool") as mock_pool:
        mock_pool.get_session_status = MagicMock(return_value=sessions)
        with patch("src.engine.scanner.ticker_last_tick", last_tick_map):
            with patch("src.engine.scheduler.datetime") as mock_dt:
                mock_dt.now.return_value = NOW
                mock_dt.min = datetime.min
                result = scheduler_inst._detect_silent_inactive_sessions()

    assert result == [], f"fresh=80% 시 silent 판정 안 함 — got {result}"
    assert "main" not in scheduler_inst._silent_inactive_first_seen, "회복 first_seen pop 검증"


# ===========================================================================
# N-7: fresh_ratio < 0.2 + sub=4 → sub>=5 가드 보존 (감지 안 함)
# ===========================================================================
def test_low_ratio_but_sub_below_min_no_detect(scheduler_inst):
    """fresh=0/4 (0% < 20%) 인데 sub<5 → 감지 안 함 (위양성 차단 가드 보존)."""
    from src.engine import scheduler as sch_mod

    tickers = [f"{i:06d}" for i in range(4)]
    sessions = [_make_session("main", subscribed=4, tickers=tickers)]

    with patch.object(sch_mod, "kis_ws_pool") as mock_pool:
        mock_pool.get_session_status = MagicMock(return_value=sessions)
        with patch("src.engine.scanner.ticker_last_tick", {}):
            with patch("src.engine.scheduler.datetime") as mock_dt:
                mock_dt.now.return_value = NOW
                mock_dt.min = datetime.min
                result = scheduler_inst._detect_silent_inactive_sessions()

    assert result == [], f"sub<5 가드 보존 — got {result}"
    assert "main" not in scheduler_inst._silent_inactive_first_seen


# ===========================================================================
# N-8: fresh_ratio < 0.2 + 5분 미달 → first_seen 등록만, 감지 안 함
# ===========================================================================
def test_low_ratio_but_5min_not_reached(scheduler_inst):
    """fresh=2/25 (8%) + sub>=5 충족하지만 5분 미달 → first_seen 등록만."""
    from src.engine import scheduler as sch_mod

    tickers = [f"{i:06d}" for i in range(25)]
    sessions = [_make_session("main", subscribed=25, tickers=tickers)]
    # first_seen 미등록 (첫 감지) → 5분 미달

    last_tick_map = {
        tickers[0]: NOW - timedelta(seconds=10),
        tickers[1]: NOW - timedelta(seconds=10),
    }

    with patch.object(sch_mod, "kis_ws_pool") as mock_pool:
        mock_pool.get_session_status = MagicMock(return_value=sessions)
        with patch("src.engine.scanner.ticker_last_tick", last_tick_map):
            with patch("src.engine.scheduler.datetime") as mock_dt:
                mock_dt.now.return_value = NOW
                mock_dt.min = datetime.min
                result = scheduler_inst._detect_silent_inactive_sessions()

    assert result == [], f"5분 미달 silent 판정 안 함 — got {result}"
    assert "main" in scheduler_inst._silent_inactive_first_seen, (
        "조건 1+2 충족 시 first_seen 등록 — 5분 카운트 시작"
    )


# ===========================================================================
# N-9: 0 subscribed 세션 — division by zero 방어
# ===========================================================================
def test_empty_session_no_detect_and_no_zero_division(scheduler_inst):
    """subscribed=0 세션 → 비율 계산 무해 (sub>=5 가드가 먼저 차단)."""
    from src.engine import scheduler as sch_mod

    sessions = [_make_session("main", subscribed=0, tickers=[])]

    with patch.object(sch_mod, "kis_ws_pool") as mock_pool:
        mock_pool.get_session_status = MagicMock(return_value=sessions)
        with patch("src.engine.scanner.ticker_last_tick", {}):
            with patch("src.engine.scheduler.datetime") as mock_dt:
                mock_dt.now.return_value = NOW
                mock_dt.min = datetime.min
                # ZeroDivisionError 없이 정상 반환
                result = scheduler_inst._detect_silent_inactive_sessions()

    assert result == []
