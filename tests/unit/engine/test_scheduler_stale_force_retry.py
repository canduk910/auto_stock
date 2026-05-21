"""사이클 29 (2026-05-21) — 영구 stale 무한 skip → 시간 기반 강제 재시도 전환.

배경 (실측 결함 — 2026-05-21 13:13~13:29 운영 로그):
- `[stale_watcher] subscribed=34 stale=23 force_reregistered=1 skipped=22`
- 22개 종목이 `r=6→9` 카운터만 증가하고 강제 재등록 0건
- 13:21:41 마지막 시도 후 8분 이상 추가 시도 없음
- 보유 종목 005935(삼성전자우) 가 stale 명단에 포함 → ATR×2 트레일링/하드 -7% 손절 평가 지연 위험

원인:
- `_check_and_resubscribe_stale` 의 `if retry > MAX_STALE_RETRIES: skipped_giveup += 1; continue`
  분기(`src/engine/scheduler.py:2695-2699`) 가 **무한 skip** 으로 작동
- 설계 의도(거래정지·이상 종목 보호) 와 실상(정상 종목까지 12분 이상 영구 stale 잔류) 의 괴리

본 사이클(29) 변경:
- 신규 상수 `STALE_FORCE_RETRY_AFTER_SECS = 300` (5분 cooldown)
- 신규 상수 `STALE_FORCE_RETRY_HOURLY_CAP = 12` (시간당 12회 cap, LMS 위험 가드)
- 신규 필드 `_stale_force_retry_history: dict[str, list[datetime]]` (60분 슬라이딩 윈도우)
- `r > MAX_STALE_RETRIES` 분기에서:
  1. `last_resub_age >= 300s` → 강제 재시도 + `_stale_retry_count[ticker] = 0` 카운터 리셋
  2. `last_resub_age < 300s` → skip (기존 동작 보존)
  3. `_stale_last_resubscribe_at` 부재 → 즉시 1회 시도 (영구 stale 의심 첫 진입)
  4. 시간당 12회 cap 초과 → skip + `[stale_force_retry_cap]` WARNING

사양:
- F-1: 신규 상수 2개 노출 검증
- F-2: 신규 필드 초기화 검증 + `_reset_daily_state` 동행 clear
- F-3: r=6 + last_resub_age >= 300s → 강제 재시도 + 카운터 0 리셋
- F-4: r=6 + last_resub_age < 300s → skip (기존 보존)
- F-5: r=6 + last_resub_at 부재 → 즉시 1회 시도
- F-6: `[stale_force_retry]` 로그 포맷 검증
- F-7: 시간당 cap 12회 초과 → skip + WARNING
- F-8: r <= 5 분기 기존 동작 회귀 (강제 재등록 + 카운터 그대로)
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

pytestmark = pytest.mark.unit

KST = timezone(timedelta(hours=9))


# ---------------------------------------------------------------------------
# 공용 픽스처 — _check_and_resubscribe_stale 환경 구성
# ---------------------------------------------------------------------------
def _setup_env(monkeypatch, *, tickers: list[str], stale_age_secs: int = 300):
    """공통: kis_ws / kis_ws_pool / scanner.ticker_last_tick / write_log mock."""
    from src.engine import scheduler as sch_mod
    import src.engine.scanner as scanner_mod
    import src.realtime.websocket_pool as wp_mod

    subscribed_set = set(tickers)
    monkeypatch.setattr(
        sch_mod, "kis_ws", MagicMock(get_subscribed_tickers=lambda: set(subscribed_set))
    )

    old = datetime.now(KST) - timedelta(seconds=stale_age_secs)
    last_tick = {t: old for t in tickers}
    monkeypatch.setattr(scanner_mod, "ticker_last_tick", last_tick)

    pool_mock = MagicMock()
    pool_mock.get_subscribed_tickers = lambda: list(subscribed_set)
    pool_mock.unsubscribe_in_pool = AsyncMock()
    pool_mock.subscribe = AsyncMock()
    pool_mock.resend_subscribe_for_ticker = AsyncMock()
    monkeypatch.setattr(wp_mod, "kis_ws_pool", pool_mock)

    log_calls: list[tuple[str, str]] = []

    async def _wl(level, msg, *a, **kw):
        log_calls.append((level, msg))
        return None

    monkeypatch.setattr(sch_mod, "write_log", _wl)

    return pool_mock, log_calls


def _make_sched():
    """`__new__` 기반 minimal scheduler instance."""
    from src.engine.scheduler import TradingScheduler

    sched = TradingScheduler.__new__(TradingScheduler)
    sched._stale_retry_count = {}
    sched._stale_last_resubscribe_at = {}
    sched._stale_force_retry_history = {}
    sched._running = True
    return sched


# ===========================================================================
# F-1: 신규 상수 노출 검증
# ===========================================================================
def test_stale_force_retry_after_secs_is_300():
    """``STALE_FORCE_RETRY_AFTER_SECS`` 가 300s (5분) 로 정의됨.

    사이클 29: 영구 stale 종목 최소 재시도 간격. KIS LMS / 앱키 정지 위험 차단.
    """
    from src.engine import scheduler

    assert scheduler.STALE_FORCE_RETRY_AFTER_SECS == 300, (
        "사이클 29: 영구 stale 5분 cooldown — KIS 답변 (기등록 재등록 자제) 정신 유지"
    )


def test_stale_force_retry_hourly_cap_is_12():
    """``STALE_FORCE_RETRY_HOURLY_CAP`` 이 12회 로 정의됨.

    사이클 29: 시간당 동일 종목 최대 재시도 횟수 (5분 × 12 = 60분).
    LMS / 앱키 정지 위험 추가 가드.
    """
    from src.engine import scheduler

    assert scheduler.STALE_FORCE_RETRY_HOURLY_CAP == 12, (
        "사이클 29: 시간당 12회 cap — LMS 위험 추가 가드"
    )


# ===========================================================================
# F-2: 신규 필드 초기화 + _reset_daily_state 동행 clear
# ===========================================================================
def test_stale_force_retry_history_field_initialized_in_constructor():
    """``__init__`` 에서 ``_stale_force_retry_history`` dict 가 초기화됨."""
    from src.engine.scheduler import TradingScheduler

    # 실제 __init__ 호출은 외부 의존성이 많으므로 클래스 어노테이션 또는
    # __new__ + 명시적 init 패턴 확인. 핵심은 필드 존재 여부.
    sched = TradingScheduler.__new__(TradingScheduler)
    # 사이클 29 — backend-dev 가 __init__ 에 추가하면 hasattr 통과
    # Red 단계: 아직 미구현 → 실패
    # Green 단계 후: 인스턴스 생성 시 자동 초기화 확인
    # 본 단위 테스트는 hasattr 가능성 + dict 타입 검증으로 단순화
    # (전체 __init__ 호출은 통합 테스트가 담당)
    import inspect
    src = inspect.getsource(TradingScheduler.__init__)
    assert "_stale_force_retry_history" in src, (
        "TradingScheduler.__init__ 에 _stale_force_retry_history 초기화 누락"
    )


def test_reset_daily_state_clears_stale_force_retry_history():
    """``_reset_daily_state`` 가 ``_stale_force_retry_history`` 도 clear."""
    from src.engine.scheduler import TradingScheduler

    src = __import__("inspect").getsource(TradingScheduler._reset_daily_state)
    assert "_stale_force_retry_history" in src and ".clear()" in src, (
        "_reset_daily_state 에 _stale_force_retry_history.clear() 누락"
    )


# ===========================================================================
# F-3: r=6 + last_resub_age >= 300s → 강제 재시도 + 카운터 0 리셋
# ===========================================================================
@pytest.mark.asyncio
async def test_force_retry_fires_when_cooldown_elapsed(monkeypatch):
    """r=6 (이미 MAX_STALE_RETRIES 초과) + last_resub_age >= 300s → 강제 재시도.

    핵심:
    - `unsubscribe_in_pool` + `subscribe(HIGH, bypass_limit=True)` 호출
    - `_stale_retry_count[ticker] == 0` 카운터 리셋 (신규 사이클 시작)
    """
    pool_mock, _ = _setup_env(monkeypatch, tickers=["005935"])
    sched = _make_sched()
    sched._stale_retry_count = {"005935": 5}  # +1 → 6
    # 마지막 강제 재등록이 301초 전 → cooldown 경과
    sched._stale_last_resubscribe_at = {
        "005935": datetime.now(KST) - timedelta(seconds=301)
    }

    await sched._check_and_resubscribe_stale()

    pool_mock.unsubscribe_in_pool.assert_awaited_once()
    pool_mock.subscribe.assert_awaited_once()
    kwargs = pool_mock.subscribe.await_args.kwargs
    assert kwargs.get("priority") == "HIGH"
    assert kwargs.get("bypass_limit") is True

    # 핵심: 카운터 리셋 (신규 사이클 시작)
    assert sched._stale_retry_count["005935"] == 0, (
        "force_retry 분기는 _stale_retry_count[ticker] = 0 리셋 필수 — "
        "다음 사이클부터 다시 1~5 정상 분기로 동작"
    )
    # last_resubscribe_at 도 갱신됨
    assert sched._stale_last_resubscribe_at["005935"] > (
        datetime.now(KST) - timedelta(seconds=2)
    )


# ===========================================================================
# F-4: r=6 + last_resub_age < 300s → skip (기존 동작 보존)
# ===========================================================================
@pytest.mark.asyncio
async def test_skip_when_cooldown_not_elapsed(monkeypatch):
    """r=6 + last_resub_age < 300s → skip (기존 동작 보존, LMS 위험 차단).

    카운터는 +1 되어 r=7 로 누적 (skip 도 카운트 — 기존 동작).
    """
    pool_mock, _ = _setup_env(monkeypatch, tickers=["005935"])
    sched = _make_sched()
    sched._stale_retry_count = {"005935": 5}  # +1 → 6
    # 마지막 강제 재등록이 100초 전 → cooldown 미경과
    sched._stale_last_resubscribe_at = {
        "005935": datetime.now(KST) - timedelta(seconds=100)
    }

    await sched._check_and_resubscribe_stale()

    pool_mock.unsubscribe_in_pool.assert_not_called()
    pool_mock.subscribe.assert_not_called()
    # skip 도 카운트
    assert sched._stale_retry_count["005935"] == 6
    # last_resubscribe_at 변동 없음
    assert sched._stale_last_resubscribe_at["005935"] < (
        datetime.now(KST) - timedelta(seconds=90)
    )


# ===========================================================================
# F-5: r=6 + last_resub_at 부재 → 즉시 1회 시도 (영구 stale 의심 첫 진입)
# ===========================================================================
@pytest.mark.asyncio
async def test_force_retry_fires_when_no_last_resub_at_recorded(monkeypatch):
    """r=6 인데 `_stale_last_resubscribe_at` 에 ticker 항목이 없는 케이스.

    `_stale_last_resubscribe_at` 부재 = 영구 stale 의심 첫 진입 (혹은 운영 중 추적 누락).
    → 즉시 1회 시도 (안전 폴백, age=infinity 로 간주).
    """
    pool_mock, _ = _setup_env(monkeypatch, tickers=["232680"])
    sched = _make_sched()
    sched._stale_retry_count = {"232680": 8}  # +1 → 9
    sched._stale_last_resubscribe_at = {}  # 부재

    await sched._check_and_resubscribe_stale()

    pool_mock.unsubscribe_in_pool.assert_awaited_once()
    pool_mock.subscribe.assert_awaited_once()
    # 카운터 리셋
    assert sched._stale_retry_count["232680"] == 0
    # last_resubscribe_at 등록됨
    assert "232680" in sched._stale_last_resubscribe_at


# ===========================================================================
# F-6: [stale_force_retry] 로그 포맷 검증
# ===========================================================================
@pytest.mark.asyncio
async def test_stale_force_retry_log_format(monkeypatch, caplog):
    """``[stale_force_retry]`` prefix + ticker / retries / last_resub_age 필드 포함."""
    import logging

    pool_mock, log_calls = _setup_env(monkeypatch, tickers=["006340"])
    sched = _make_sched()
    sched._stale_retry_count = {"006340": 8}  # +1 → 9
    sched._stale_last_resubscribe_at = {
        "006340": datetime.now(KST) - timedelta(seconds=500)
    }

    caplog.set_level(logging.INFO, logger="src.engine.scheduler")
    await sched._check_and_resubscribe_stale()

    # logger 또는 write_log 중 하나에 prefix 노출되면 통과
    log_text = " ".join(r.message for r in caplog.records) + " " + " ".join(
        msg for _, msg in log_calls
    )
    assert "[stale_force_retry]" in log_text, (
        f"[stale_force_retry] 로그 누락. captured={log_text!r}"
    )
    assert "006340" in log_text
    # last_resub_age 필드 (300s 이상 경과 — 500s)
    assert "last_resub_age" in log_text or "age" in log_text


# ===========================================================================
# F-7: 시간당 cap 12회 초과 → skip + [stale_force_retry_cap] WARNING
# ===========================================================================
@pytest.mark.asyncio
async def test_hourly_cap_blocks_13th_attempt(monkeypatch):
    """시간당 12회 강제 재시도 후 13번째는 skip + WARNING.

    60분 슬라이딩 윈도우 내 12회 누적 → 13번째 시도는 차단.
    """
    pool_mock, log_calls = _setup_env(monkeypatch, tickers=["005935"])
    sched = _make_sched()
    sched._stale_retry_count = {"005935": 8}  # +1 → 9, r > 5 분기
    # cooldown 경과
    sched._stale_last_resubscribe_at = {
        "005935": datetime.now(KST) - timedelta(seconds=400)
    }
    # 시간당 cap 가득 — 60분 윈도우 내 12번 누적
    now = datetime.now(KST)
    sched._stale_force_retry_history = {
        "005935": [now - timedelta(minutes=55 - i * 4) for i in range(12)]
    }

    await sched._check_and_resubscribe_stale()

    # cap 초과 → 강제 재시도 호출 0건
    pool_mock.unsubscribe_in_pool.assert_not_called()
    pool_mock.subscribe.assert_not_called()

    # [stale_force_retry_cap] WARNING 노출
    cap_logs = [msg for level, msg in log_calls if "[stale_force_retry_cap]" in msg]
    assert len(cap_logs) >= 1, (
        f"시간당 cap 초과 시 [stale_force_retry_cap] WARNING 누락. log_calls={log_calls!r}"
    )
    assert any(level == "WARNING" for level, msg in log_calls if "[stale_force_retry_cap]" in msg)


@pytest.mark.asyncio
async def test_hourly_cap_allows_12th_attempt(monkeypatch):
    """시간당 11회 후 12번째는 허용 (cap 경계 — 12회까지 허용)."""
    pool_mock, _ = _setup_env(monkeypatch, tickers=["005935"])
    sched = _make_sched()
    sched._stale_retry_count = {"005935": 8}
    sched._stale_last_resubscribe_at = {
        "005935": datetime.now(KST) - timedelta(seconds=400)
    }
    # 60분 윈도우 내 11번 누적 — 12번째는 허용
    now = datetime.now(KST)
    sched._stale_force_retry_history = {
        "005935": [now - timedelta(minutes=55 - i * 5) for i in range(11)]
    }

    await sched._check_and_resubscribe_stale()

    pool_mock.unsubscribe_in_pool.assert_awaited_once()
    pool_mock.subscribe.assert_awaited_once()
    # history 에 12번째 항목 추가됨
    assert len(sched._stale_force_retry_history["005935"]) == 12


@pytest.mark.asyncio
async def test_hourly_cap_sliding_window_evicts_old_entries(monkeypatch):
    """60분 이전 항목은 슬라이딩 윈도우에서 제거되어 cap 재충전됨."""
    pool_mock, _ = _setup_env(monkeypatch, tickers=["005935"])
    sched = _make_sched()
    sched._stale_retry_count = {"005935": 8}
    sched._stale_last_resubscribe_at = {
        "005935": datetime.now(KST) - timedelta(seconds=400)
    }
    # 60분 이전 12회 + 최근 0회 → 모두 만료되어 cap 0/12 → 허용
    now = datetime.now(KST)
    sched._stale_force_retry_history = {
        "005935": [now - timedelta(hours=2, minutes=i) for i in range(12)]
    }

    await sched._check_and_resubscribe_stale()

    pool_mock.unsubscribe_in_pool.assert_awaited_once()
    pool_mock.subscribe.assert_awaited_once()
    # 만료 항목 evict + 새 항목 1건만 잔존
    assert len(sched._stale_force_retry_history["005935"]) == 1


# ===========================================================================
# F-8: r <= 5 분기 기존 동작 회귀 (사이클 17 보존)
# ===========================================================================
@pytest.mark.asyncio
async def test_existing_r_le_5_branch_unchanged(monkeypatch):
    """r=3 (= 5 이하) 케이스는 기존 동작 그대로 (강제 재등록 + 카운터 그대로).

    `_stale_last_resubscribe_at` 갱신은 사이클 28 패턴 보존.
    `_stale_force_retry_history` 는 갱신 안 됨 (r <= 5 분기는 시간당 cap 미적용).
    """
    pool_mock, _ = _setup_env(monkeypatch, tickers=["005930"])
    sched = _make_sched()
    sched._stale_retry_count = {"005930": 2}  # +1 → 3

    await sched._check_and_resubscribe_stale()

    pool_mock.unsubscribe_in_pool.assert_awaited_once()
    pool_mock.subscribe.assert_awaited_once()
    # r=3 카운터 유지 (사이클 17: 1~5 회는 매 사이클 강제 재등록 + 카운터 누적)
    assert sched._stale_retry_count["005930"] == 3
    # last_resubscribe_at 갱신 (사이클 28)
    assert "005930" in sched._stale_last_resubscribe_at
    # history 는 r <= 5 분기에서는 등록 안 됨
    assert "005930" not in sched._stale_force_retry_history
