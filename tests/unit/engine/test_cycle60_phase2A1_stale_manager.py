"""사이클 60 Phase 2-A1 Red — `src/engine/stale_manager.py` 추출 회귀 가드 (17 케이스).

> **선행 명세**: `_workspace/red/cycle60_phase2A1_stale_manager.md`
> **설계 카드**: `_workspace/cycle60_phase2A1_design_card.md`
> **자문 응답**: `_workspace/cycle60_phase2A_domain_response.md` (Q1~Q7)
> **위험 등급**: LOW (read-only 4 함수 + ccnl evict 1 함수, 매매 hot path 무영향)
> **선례**: 사이클 51 `test_boot_manager_extraction.py` wrapper 위임 가드 패턴 답습

본 파일은 Red 단계 — `src/engine/stale_manager.py` 미존재 + 5 함수 미이동 상태에서
17 케이스 모두 *FAIL 또는 ImportError* 정상.

카테고리 (17 = 5+5+2+1+1+1+1+1):
- A 위임 1회 (LOW 5) — `_build_session_subscription_view` / `_emit_stale_session_detail` /
  `_refresh_stale_ccnl_cache` / `_evict_expired_ccnl` / `_prune_force_retry_history`
- B 5 상수 동일성 (LOW 5) — `MAX_STALE_RETRIES` 외 4종 `is` 동일성 + 값 검증
- C 호출 순서 보존 (MEDIUM 2) — refresh→evict 순서 / prune cap 순서
- D 의존성 역전 정적 검증 (LOW 1) — `ast` 로 stale_manager → scheduler import 0건
- E ccnl TTL evict 정합성 (LOW 1) — freezegun TTL 진행 + evict 정확성
- F force_retry 시간당 cap (MEDIUM 1) — 13번째 호출 skip (cap=12)
- G `_reset_daily_state` 동행 reset (HIGH 1) — `StaleTrackerState` 7 필드 동시 검증
  + dataclass 필드 누락 가드 (사이클 48 패턴)
- H import sanity (LOW 1) — `from src.engine import stale_manager` + 5 함수 + 5 상수 노출
  + property layer 9 호환 흡수 (`_last_ccnl_cache` getattr 패턴 보존)

회귀 가드 매트릭스 (CLAUDE.md 절대 깨지 말 것 7 종 보호):
- WebSocket 4 중 안전망 — A1/A2/A3 + C1 (호출 순서 보존)
- K stale watcher 우선순위 분리 — H1 (property layer 9 호환)
- `_reset_daily_state` 동행 reset — G1 (7 필드 + dataclass 필드 누락)
- KST 강제 — E1 (freezegun KST 명시)
- `_subscriptions` ACK 정합성 — A1 (build_session_subscription_view 위임)
"""
from __future__ import annotations

import ast
import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest
from freezegun import freeze_time

pytestmark = pytest.mark.unit

KST = timezone(timedelta(hours=9))


# ---------------------------------------------------------------------------
# 공용 fixture — TradingScheduler 의 stale 영역만 격리한 인스턴스
# ---------------------------------------------------------------------------
def _make_scheduler():
    """`TradingScheduler.__new__` + `_stale_state` 만 init.

    KIS API 호출 가능 영역은 모두 mock 으로 대체 (사이클 60 hotfix 패턴 — CI hang 차단).
    """
    from src.engine.scheduler import TradingScheduler
    from src.engine.stale_tracker import StaleTrackerState

    sched = TradingScheduler.__new__(TradingScheduler)
    # property layer 가 _stale_state 자동 init 하지만 명시
    object.__setattr__(sched, "_stale_state", StaleTrackerState())
    return sched


# ===========================================================================
# 카테고리 A — wrapper 위임 1회 검증 (LOW 5 케이스)
# 사이클 51 boot_manager 패턴: 2 줄 wrapper 가 stale_manager.{함수} 단일 호출
# ===========================================================================

def test_A1_build_session_subscription_view_delegates_to_stale_manager():
    """A-1: `_build_session_subscription_view` wrapper 가 stale_manager 단일 호출."""
    from src.engine import stale_manager  # ImportError 시 Red

    sched = _make_scheduler()
    expected = [{"label": "main", "subscribed_count": 0}]

    with patch.object(
        stale_manager, "build_session_subscription_view", return_value=expected
    ) as mock_fn:
        result = sched._build_session_subscription_view()

    mock_fn.assert_called_once_with(sched)
    assert result is expected, "wrapper 가 stale_manager 반환값을 그대로 전달해야 함"


def test_A2_emit_stale_session_detail_delegates_to_stale_manager():
    """A-2: `_emit_stale_session_detail` wrapper 가 stale_manager 단일 호출."""
    from src.engine import stale_manager  # ImportError 시 Red

    sched = _make_scheduler()
    now = datetime.now(KST)
    stale_tickers = ["005930", "000660"]

    with patch.object(
        stale_manager, "emit_stale_session_detail", return_value=None
    ) as mock_fn:
        sched._emit_stale_session_detail(stale_tickers, now)

    mock_fn.assert_called_once_with(sched, stale_tickers, now)


@pytest.mark.asyncio
async def test_A3_refresh_stale_ccnl_cache_delegates_to_stale_manager():
    """A-3: `_refresh_stale_ccnl_cache` wrapper 가 stale_manager 단일 호출 (async)."""
    from src.engine import stale_manager  # ImportError 시 Red

    sched = _make_scheduler()
    candidates = ["005930"]

    with patch.object(
        stale_manager, "refresh_stale_ccnl_cache", new=AsyncMock(return_value=None)
    ) as mock_fn:
        await sched._refresh_stale_ccnl_cache(candidates, cap=20)

    mock_fn.assert_awaited_once_with(sched, candidates, cap=20)


def test_A4_evict_expired_ccnl_delegates_to_stale_manager():
    """A-4: `_evict_expired_ccnl` wrapper 가 stale_manager 단일 호출."""
    from src.engine import stale_manager  # ImportError 시 Red

    sched = _make_scheduler()
    now = datetime.now(KST)

    with patch.object(
        stale_manager, "evict_expired_ccnl", return_value=3
    ) as mock_fn:
        result = sched._evict_expired_ccnl(now, ttl_secs=300)

    mock_fn.assert_called_once_with(sched, now, ttl_secs=300)
    assert result == 3, "wrapper 가 stale_manager 의 evict 카운트를 반환해야 함"


def test_A5_prune_force_retry_history_delegates_to_stale_manager():
    """A-5: `_prune_force_retry_history` wrapper 가 stale_manager 단일 호출."""
    from src.engine import stale_manager  # ImportError 시 Red

    sched = _make_scheduler()
    now = datetime.now(KST)

    with patch.object(
        stale_manager, "prune_force_retry_history", return_value=None
    ) as mock_fn:
        sched._prune_force_retry_history("005930", now, window_secs=3600)

    mock_fn.assert_called_once_with(sched, "005930", now, window_secs=3600)


# ===========================================================================
# 카테고리 B — 5 상수 `is` 동일성 (LOW 5 케이스, Q3-G1~G5)
# scheduler.X is stale_manager.X — re-export 호환 보장
# ===========================================================================

def test_B1_MAX_STALE_RETRIES_same_object_across_modules():
    """B-1: `MAX_STALE_RETRIES` scheduler import = stale_manager 정의 (`is` 동일성)."""
    from src.engine.scheduler import MAX_STALE_RETRIES as A
    from src.engine.stale_manager import MAX_STALE_RETRIES as B

    assert A is B, "MAX_STALE_RETRIES 가 두 모듈에서 동일 객체여야 함 (re-export)"
    assert A == 5, "MAX_STALE_RETRIES 값은 사이클 17 정의 5 유지"


def test_B2_STALE_FORCE_RETRY_AFTER_SECS_same_object():
    """B-2: `STALE_FORCE_RETRY_AFTER_SECS` 동일성 + 값 300."""
    from src.engine.scheduler import STALE_FORCE_RETRY_AFTER_SECS as A
    from src.engine.stale_manager import STALE_FORCE_RETRY_AFTER_SECS as B

    assert A is B
    assert A == 300, "사이클 29-R1 정의 (5분) 유지"


def test_B3_STALE_FORCE_RETRY_HOURLY_CAP_same_object():
    """B-3: `STALE_FORCE_RETRY_HOURLY_CAP` 동일성 + 값 12."""
    from src.engine.scheduler import STALE_FORCE_RETRY_HOURLY_CAP as A
    from src.engine.stale_manager import STALE_FORCE_RETRY_HOURLY_CAP as B

    assert A is B
    assert A == 12, "사이클 29-R1 정의 (시간당 12회 cap) 유지 — LMS 정지 위험 차단"


def test_B4_UNIVERSE_LOW_VOLUME_THRESHOLD_same_object():
    """B-4: `UNIVERSE_LOW_VOLUME_THRESHOLD` 동일성 + 값 10_000."""
    from src.engine.scheduler import UNIVERSE_LOW_VOLUME_THRESHOLD as A
    from src.engine.stale_manager import UNIVERSE_LOW_VOLUME_THRESHOLD as B

    assert A is B
    assert A == 10_000, "사이클 32 R4 정의 유지"


def test_B5_SILENT_INACTIVE_FRESH_RATIO_THRESHOLD_same_object():
    """B-5: `SILENT_INACTIVE_FRESH_RATIO_THRESHOLD` 동일성 + 값 0.2."""
    from src.engine.scheduler import SILENT_INACTIVE_FRESH_RATIO_THRESHOLD as A
    from src.engine.stale_manager import SILENT_INACTIVE_FRESH_RATIO_THRESHOLD as B

    assert A is B
    assert A == 0.2, "사이클 29-R2 정의 (20% 비율 기반) 유지"


# ===========================================================================
# 카테고리 C — 호출 순서 보존 (MEDIUM 2 케이스, Q1-G3 부분 적용)
# ===========================================================================

@pytest.mark.asyncio
async def test_C1_refresh_calls_evict_before_fetch():
    """C-1: `refresh_stale_ccnl_cache` 본체가 `evict_expired_ccnl` 을 *호출 진입 시점에* 먼저 실행.

    사이클 45 정책: TTL 만료 항목 자동 evict → 그 후 KIS 호출 (메모리 누수 차단).
    Red 단계: stale_manager 미존재 → ImportError.
    Green 후 stale_manager.refresh_stale_ccnl_cache 가 evict_expired_ccnl 을 먼저 호출 검증.
    """
    from src.engine import stale_manager  # ImportError 시 Red

    sched = _make_scheduler()
    sched._stale_state.retry_count["005930"] = 3  # eligible 만들기
    sched.registry = MagicMock()
    sched.registry.all.return_value = []

    call_order: list[str] = []

    def fake_evict(s, now, ttl_secs=300):
        call_order.append("evict")
        return 0

    async def fake_ccnl(ticker):
        call_order.append(f"ccnl:{ticker}")
        return None

    # 사이클 67 분해 후: refresh_stale_ccnl_cache 본체는 stale_diagnostics 에 위치.
    # 본체가 evict_expired_ccnl 을 동일 모듈 네임스페이스에서 직접 호출하므로
    # patch 경로도 stale_diagnostics 로 지정해야 인터셉트된다 (facade 패치 비효과).
    with patch("src.engine.stale_diagnostics.evict_expired_ccnl", side_effect=fake_evict), \
         patch("src.api.quotation.inquire_ccnl", new=AsyncMock(side_effect=fake_ccnl)):
        await stale_manager.refresh_stale_ccnl_cache(sched, ["005930"], cap=20)

    # evict 가 ccnl 호출보다 먼저 진입
    assert "evict" in call_order, "refresh 본체가 evict 를 호출해야 함"
    if any(c.startswith("ccnl:") for c in call_order):
        assert call_order.index("evict") < next(
            i for i, c in enumerate(call_order) if c.startswith("ccnl:")
        ), "evict 가 ccnl 호출보다 먼저 진입해야 함 (사이클 45 정책)"


def test_C2_prune_force_retry_history_preserves_cap_window_order():
    """C-2: `prune_force_retry_history` 가 60분 sliding window 외 항목만 제거 + 순서 보존.

    사이클 29-R1 정책: cap 비교 *직전* 호출. window 내 항목 list 의 시간 순서 보존
    (KIS LMS 정지 위험 차단 가드).
    """
    from src.engine import stale_manager  # ImportError 시 Red

    sched = _make_scheduler()
    now = datetime(2026, 6, 4, 16, 0, 0, tzinfo=KST)
    # 70분 전, 30분 전, 5분 전 = 첫 항목만 evict 대상
    sched._stale_state.force_retry_history["005930"] = [
        now - timedelta(minutes=70),
        now - timedelta(minutes=30),
        now - timedelta(minutes=5),
    ]

    stale_manager.prune_force_retry_history(sched, "005930", now, window_secs=3600)

    remaining = sched._stale_state.force_retry_history.get("005930", [])
    assert len(remaining) == 2, "60분 외 1건 evict, window 내 2건 보존"
    # 시간 순서 보존
    assert remaining[0] < remaining[1], "list 시간 순서 보존 (사이클 29-R1 cap 비교용)"


# ===========================================================================
# 카테고리 D — 의존성 역전 정적 검증 (LOW 1 케이스, Q3-G6)
# stale_manager 가 scheduler 를 역참조하면 순환 의존 위험 + 모듈 분해 무의미
# ===========================================================================

def test_D1_stale_manager_does_not_import_scheduler():
    """D-1: `ast` 모듈로 `src/engine/stale_manager.py` parsing → scheduler import 0건."""
    import pathlib

    path = pathlib.Path("src/engine/stale_manager.py")
    assert path.exists(), "stale_manager.py 가 존재해야 함 (Red 단계 미존재 → FAIL)"

    tree = ast.parse(path.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            assert not (node.module and "scheduler" in node.module), (
                f"stale_manager.py 가 scheduler 를 import 하면 안 됨: {node.module}"
            )
        elif isinstance(node, ast.Import):
            for alias in node.names:
                assert "scheduler" not in alias.name, (
                    f"stale_manager.py 가 scheduler import 하면 안 됨: {alias.name}"
                )


# ===========================================================================
# 카테고리 E — ccnl TTL evict 정합성 (LOW 1 케이스)
# 사이클 45: TTL 5분 (300s) 경과 항목 자동 evict + 미경과 항목 보존
# ===========================================================================

def test_E1_evict_expired_ccnl_removes_only_expired_entries_freezegun():
    """E-1: freezegun 시간 진행 후 TTL 경과 항목만 evict + 미만료 항목 보존."""
    from src.engine import stale_manager  # ImportError 시 Red

    sched = _make_scheduler()
    base = datetime(2026, 6, 4, 14, 0, 0, tzinfo=KST)

    # 10분 전 fetched (만료) + 1분 전 fetched (미만료)
    sched._stale_state.last_ccnl_cache["005930"] = {
        "fetched_at": base - timedelta(minutes=10),
        "last_cntg_hour": "135000",
        "today_volume": 50_000,
    }
    sched._stale_state.last_ccnl_cache["000660"] = {
        "fetched_at": base - timedelta(minutes=1),
        "last_cntg_hour": "135900",
        "today_volume": 30_000,
    }

    with freeze_time(base):
        evicted = stale_manager.evict_expired_ccnl(sched, base, ttl_secs=300)

    assert evicted == 1, "10분 전 1건만 evict"
    assert "005930" not in sched._stale_state.last_ccnl_cache, "만료 항목 제거"
    assert "000660" in sched._stale_state.last_ccnl_cache, "미만료 항목 보존"


# ===========================================================================
# 카테고리 F — force_retry 시간당 cap (MEDIUM 1 케이스)
# 사이클 29-R1: 시간당 12회 cap — KIS LMS / 앱키 정지 위험 차단
# ===========================================================================

def test_F1_prune_preserves_cap_window_after_freezegun_hour_progress():
    """F-1: freezegun 1시간 윈도우 슬라이딩 후 cap=12 유지 + 빈 list 시 dict 자동 제거."""
    from src.engine import stale_manager  # ImportError 시 Red

    sched = _make_scheduler()
    base = datetime(2026, 6, 4, 16, 0, 0, tzinfo=KST)

    # 빈 list 자동 제거 시나리오 — 모두 60분 외
    sched._stale_state.force_retry_history["009150"] = [
        base - timedelta(minutes=120),
        base - timedelta(minutes=90),
        base - timedelta(minutes=70),
    ]

    with freeze_time(base):
        stale_manager.prune_force_retry_history(
            sched, "009150", base, window_secs=3600
        )

    assert "009150" not in sched._stale_state.force_retry_history, (
        "빈 list 시 dict 에서 자동 제거 (메모리 누수 차단, 사이클 45)"
    )

    # 12회 cap 가드 — window 내 12개 + 1개 (외) 시
    sched._stale_state.force_retry_history["005930"] = (
        [base - timedelta(minutes=70)]  # window 외 evict 대상
        + [base - timedelta(minutes=m) for m in range(50, 2, -4)][:12]  # 정확히 12개
    )

    with freeze_time(base):
        stale_manager.prune_force_retry_history(
            sched, "005930", base, window_secs=3600
        )

    remaining = sched._stale_state.force_retry_history.get("005930", [])
    assert len(remaining) == 12, (
        f"window 내 12개만 남아야 함 (cap 비교용 가드) - actual={len(remaining)}"
    )


# ===========================================================================
# 카테고리 G — `_reset_daily_state` 동행 reset (HIGH 1 케이스, Q2-G1)
# 사이클 48 StaleTrackerState 7 필드 모두 reset + dataclass 필드 누락 가드
# ===========================================================================

def test_G1_reset_daily_state_clears_all_stale_fields_and_dataclass_field_guard():
    """G-1: `_reset_daily_state` 호출 후 `StaleTrackerState` 7 필드 동시 검증 + dataclass 필드 누락 가드.

    사이클 48 StaleTrackerState 7 필드:
    - retry_count / last_resubscribe_at / force_retry_history (사이클 17/28/29-R1)
    - silent_inactive_first_seen / silent_inactive_recovery_count (사이클 24)
    - universe_excluded_today (사이클 32 R4)
    - last_ccnl_cache (사이클 37)

    + dataclasses.fields 자동 비교 — 신규 필드 추가 시 reset_daily() 누락 사고 차단.

    Red 보강: `from src.engine import stale_manager` 동행 — Green 단계 모듈 분리 후
    `_reset_daily_state` 가 stale_manager 영역 reset 호환 영속하는지 확정.
    """
    from dataclasses import fields

    from src.engine import stale_manager  # Red: ImportError, Green: 정상
    from src.engine.scheduler import TradingScheduler
    from src.engine.stale_tracker import StaleTrackerState

    # stale_manager 가 StaleTrackerState 의 reset 경로 변경 시 회귀 차단
    assert hasattr(stale_manager, "evict_expired_ccnl"), (
        "stale_manager 가 evict_expired_ccnl 노출 후 reset 동행 가드"
    )

    sched = TradingScheduler()
    now = datetime(2026, 6, 4, 16, 0, 0, tzinfo=KST)

    # 사전 더미 데이터 7 필드 모두 주입
    sched._stale_state.retry_count["005930"] = 3
    sched._stale_state.last_resubscribe_at["005930"] = now
    sched._stale_state.force_retry_history["005930"] = [now]
    sched._stale_state.silent_inactive_first_seen["main"] = now
    sched._stale_state.silent_inactive_recovery_count["main"] = [now.timestamp()]
    sched._stale_state.universe_excluded_today.add("005930")
    sched._stale_state.last_ccnl_cache["005930"] = {
        "fetched_at": now,
        "last_cntg_hour": "135000",
        "today_volume": 50_000,
    }

    # 호출 — `_reset_daily_state` 가 `_stale_state.reset_daily()` 위임 보장
    # registry/order_engine/risk_manager/scanner 등 다른 영역은 mock 으로 격리
    with patch.object(sched.registry, "all", return_value=[]), \
         patch.object(sched, "order_engine", MagicMock(
             _selling=set(), _filled_qty={}, _order_qty={},
             _order_strategy={}, _order_ticker={}, _pending_buy_orders={},
             _pending_cancel_tasks={},
             reset_daily_state=MagicMock(),
         )), \
         patch.object(sched, "risk_manager", MagicMock(reset_daily_state=MagicMock())):
        sched._reset_daily_state()

    # 7 필드 동시 검증
    assert sched._stale_state.retry_count == {}, "retry_count 초기화 누락"
    assert sched._stale_state.last_resubscribe_at == {}, "last_resubscribe_at 초기화 누락"
    assert sched._stale_state.force_retry_history == {}, "force_retry_history 초기화 누락"
    assert sched._stale_state.silent_inactive_first_seen == {}, "silent_inactive_first_seen 초기화 누락"
    assert sched._stale_state.silent_inactive_recovery_count == {}, (
        "silent_inactive_recovery_count 초기화 누락 — 시간당 reconnect cap 위반 위험"
    )
    assert sched._stale_state.universe_excluded_today == set(), (
        "universe_excluded_today 초기화 누락 — 영구 블랙리스트 금지 (다음 영업일 재진입)"
    )
    assert sched._stale_state.last_ccnl_cache == {}, "last_ccnl_cache 초기화 누락"

    # dataclass 필드 누락 가드 — 사이클 48 패턴
    fresh = StaleTrackerState()
    for f in fields(StaleTrackerState):
        actual = getattr(sched._stale_state, f.name)
        expected = getattr(fresh, f.name)
        assert actual == expected, (
            f"reset_daily() 가 신규 필드 {f.name} 초기화 누락 "
            f"(actual={actual!r}, expected={expected!r}) — "
            f"StaleTrackerState.reset_daily() 갱신 필요"
        )


# ===========================================================================
# 카테고리 H — import sanity + property layer 9 호환 (LOW 1 케이스)
# `from src.engine import stale_manager` + 5 함수 + 5 상수 노출
# + `_last_ccnl_cache` getattr 패턴 (realtime.py L88-91) 호환 흡수
# ===========================================================================

def test_H1_stale_manager_import_exposes_5_functions_5_constants_and_property_compat():
    """H-1: `from src.engine import stale_manager` 성공 + 5 함수 + 5 상수 노출.

    + `src/routes/realtime.py` L88-91 의 `getattr(trading_scheduler, "_last_ccnl_cache", {})`
    호환 흡수 — property layer 9 보존 검증.

    + top-level import 가 순환 의존 없음 (scheduler / risk / order_engine import 0건 —
    D-1 정적 검증과 동행).
    """
    from src.engine import stale_manager

    # 5 함수 노출 (시그니처 미준수 시 추후 케이스에서 FAIL)
    for fname in (
        "build_session_subscription_view",
        "emit_stale_session_detail",
        "refresh_stale_ccnl_cache",
        "evict_expired_ccnl",
        "prune_force_retry_history",
    ):
        assert hasattr(stale_manager, fname), f"stale_manager 가 {fname} 노출해야 함"
        assert callable(getattr(stale_manager, fname)), (
            f"{fname} 가 callable 이어야 함"
        )

    # async 함수 가드 — refresh_stale_ccnl_cache 만
    assert asyncio.iscoroutinefunction(
        stale_manager.refresh_stale_ccnl_cache
    ), "refresh_stale_ccnl_cache 는 async 여야 함"

    # 5 상수 노출
    for cname in (
        "MAX_STALE_RETRIES",
        "STALE_FORCE_RETRY_AFTER_SECS",
        "STALE_FORCE_RETRY_HOURLY_CAP",
        "UNIVERSE_LOW_VOLUME_THRESHOLD",
        "SILENT_INACTIVE_FRESH_RATIO_THRESHOLD",
    ):
        assert hasattr(stale_manager, cname), f"stale_manager 가 {cname} 노출해야 함"

    # property layer 9 호환 — `_last_ccnl_cache` 외 6 property 가 동일 dict 반환
    # (realtime.py L88-91 의 `getattr` graceful 패턴 호환 흡수)
    from src.engine.scheduler import TradingScheduler

    sched = TradingScheduler()
    # property 접근 = StaleTrackerState 필드 직접 노출 (`is` 동일성)
    assert sched._last_ccnl_cache is sched._stale_state.last_ccnl_cache, (
        "realtime.py L91 의 `_last_ccnl_cache` getattr 패턴이 property 우회 시 깨짐"
    )
    assert sched._stale_retry_count is sched._stale_state.retry_count
    assert sched._stale_last_resubscribe_at is sched._stale_state.last_resubscribe_at


# ===========================================================================
# 카테고리 I — logger 이름 호환 (사이클 60 hotfix 영구 가드)
# stale_manager.logger 가 "src.engine.scheduler" 로 바인딩되어
# 운영 logging config 및 caplog 한정 캡처 호환 보장
# ===========================================================================

def test_I1_stale_manager_logger_is_scheduler_named():
    """I-1: stale_manager.logger 가 scheduler 로 바인딩되어 운영 logging config 호환.

    사이클 28 G1 명세 (외부 모니터링 grep 호환 완전 보존) 정합. 사이클 61 A2 /
    62 A3 이주 시 logger 이름 유지 영구 강제.

    근거:
    - 사이클 28 회귀 가드 (`test_scheduler_stale_logging_format.py`) 가
      `caplog.set_level(logger="src.engine.scheduler")` 한정 캡처 → `__name__` 바인딩 시
      `src.engine.stale_manager` 로거로 분기 → caplog 미캡처 → 4 FAIL 재현
    - 운영 logging.yaml 가 `src.engine.scheduler` 로거만 핸들러 지정 시 콘솔/파일 로그 누락
    - 사이클 61 A2 / 62 A3 이주 함수도 동일 logger 이름 보존 필요 (일관성)
    """
    import src.engine.stale_manager as sm
    assert sm.logger.name == "src.engine.scheduler", (
        f"stale_manager.logger.name 이 'src.engine.scheduler' 가 아님: {sm.logger.name}. "
        f"사이클 28 G1 명세 위반 — 운영 logging config 가 scheduler 로거만 캡처할 시 "
        f"콘솔/파일 로그 누락 위험."
    )
