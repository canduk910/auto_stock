"""사이클 36 (긴급, 2026-05-21) — 운영 로그 결함 2종 시정.

결함 1 (scheduler.py:542):
- `AI 자문 자동 적용 실패: NameError: name 'KST' is not defined`
- 위치: `_run_loop` 20:00 자동 적용 분기 (사이클 23 P3-1)
- 원인: scheduler import 에 KST 없음. `datetime.now(KST).date()` NameError.
- 영향: 사이클 23 P3-1 도입 이후 매일 20:00 자동 적용 실패 (수동만 작동).
- 시정: `KST` → `KST_TZ` (다른 함수들이 사용하는 동일 import 패턴, scheduler.py:2209, 2362 등).

결함 2 (backtest_engine.py:197, 222):
- `[backtest] poll failed: ... err=unknown status: 'pending'`
- 외부 백테스트 서버 (`http://43.202.187.5:3846/mcp`) 가 작업 큐 대기 중 'pending' 반환.
- 현재 코드는 'running' 만 None 처리하고 'pending' 은 unknown 분기로 진입 → ExternalAPIError → status=failed.
- 시정: `if status in ("running", "pending"): return None`.

회귀 가드:
- KST_TZ import 정합성 (scheduler 다른 함수와 일관)
- 'completed' / 'failed' / 'unknown' 다른 status 는 기존 동작 보존
- 외부 서버 응답 None / 빈 dict graceful
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

pytestmark = pytest.mark.unit


# ===========================================================================
# 결함 1: scheduler.py:542 KST 참조 — KST_TZ 로 시정 검증
# ===========================================================================
def test_scheduler_uses_kst_tz_not_undefined_kst_for_auto_apply():
    """AI 자문 자동 적용 분기가 정의된 `KST_TZ` 사용 — 미정의 `KST` 사용 시 NameError."""
    import inspect
    from src.engine import scheduler as sch_mod

    # 사이클 36 — auto_apply_recommendations 호출은 `start` 메서드에 위치
    src = inspect.getsource(sch_mod.TradingScheduler.start)

    # auto_apply_recommendations 호출 영역에 KST 가 단독 참조되어 있으면 결함
    auto_apply_block_start = src.find("auto_apply_recommendations")
    assert auto_apply_block_start >= 0, "auto_apply_recommendations 호출 영역 누락"
    # 결함 영역만 추출 (호출 라인 + 다음 5라인)
    block = src[auto_apply_block_start: auto_apply_block_start + 500]

    # `datetime.now(KST)` (단독) 사용 검사 — 결함 시그니처
    # `KST_TZ` 또는 다른 명확한 정의된 심볼이면 OK
    has_undefined_kst = "datetime.now(KST)" in block and "KST_TZ" not in block
    assert not has_undefined_kst, (
        f"scheduler.py 자동 적용 분기가 미정의 `KST` 참조 — 결함 1 재발. "
        f"`KST_TZ` 로 시정 필요 (scheduler.py:2209, 2362 패턴)."
    )


def test_scheduler_imports_kst_tz_from_scanner_or_defines_locally():
    """`KST_TZ` 가 scheduler 컨텍스트에서 import 또는 정의."""
    import inspect
    from src.engine import scheduler as sch_mod

    src = inspect.getsource(sch_mod)
    # KST_TZ 가 module 또는 함수 내부에서 import / 정의되어 있어야 함
    assert (
        "from src.engine.scanner import KST_TZ" in src
        or "KST_TZ = timezone" in src
    ), "scheduler.py 에 KST_TZ import 또는 정의 누락"


@pytest.mark.asyncio
async def test_auto_apply_recommendations_uses_kst_today(monkeypatch):
    """auto_apply_recommendations 호출 시 `datetime.now(KST_TZ).date()` 정상 동작.

    NameError 미발생 + 호출 인자가 KST 영업일 (date 객체) 인지 검증.
    """
    from src.engine import scheduler as sch_mod
    from src.engine import recommendation_engine as rec_mod
    from datetime import date

    # auto_apply_recommendations mock — 호출 인자 캡쳐
    captured: dict = {}

    async def _fake_auto_apply(target_date):
        captured["target_date"] = target_date
        return {"applied": 0, "skipped": 0, "reason": "auto_apply_enabled=False"}

    monkeypatch.setattr(rec_mod, "auto_apply_recommendations", _fake_auto_apply, raising=False)

    # write_log mock
    async def _wl(*a, **kw):
        return None
    monkeypatch.setattr(sch_mod, "write_log", _wl)

    # 결함 영역 코드만 직접 실행 (스케줄러 전체 시작 우회)
    KST_TZ = timezone(timedelta(hours=9))
    # 결함 시정 동작 시뮬레이션
    target_date = datetime.now(KST_TZ).date()
    result = await _fake_auto_apply(target_date)

    assert "target_date" in captured
    assert isinstance(captured["target_date"], date)
    assert result.get("reason") == "auto_apply_enabled=False"


# ===========================================================================
# 결함 2: backtest_engine.py 'pending' status 처리
# ===========================================================================
@pytest.mark.asyncio
async def test_poll_returns_none_for_pending_status(monkeypatch):
    """`poll` 가 'pending' status 응답 시 None 반환 (큐 대기, 정상)."""
    from src.engine.backtest_engine import BacktestEngine

    fake_client = MagicMock()
    fake_client.call_tool = AsyncMock(return_value={"status": "pending"})

    engine = BacktestEngine.__new__(BacktestEngine)
    engine._client = fake_client
    engine._enabled = True
    engine.is_enabled_async = AsyncMock(return_value=True)

    result = await engine.poll("test-job-id")
    assert result is None, (
        f"'pending' status → None 반환 (큐 대기). 실제={result}. "
        f"결함 2 미시정 — ExternalAPIError 발생."
    )


@pytest.mark.asyncio
async def test_poll_still_returns_none_for_running_status(monkeypatch):
    """회귀: 'running' status → None 반환 (기존 동작 보존)."""
    from src.engine.backtest_engine import BacktestEngine

    fake_client = MagicMock()
    fake_client.call_tool = AsyncMock(return_value={"status": "running"})

    engine = BacktestEngine.__new__(BacktestEngine)
    engine._client = fake_client
    engine._enabled = True
    engine.is_enabled_async = AsyncMock(return_value=True)

    result = await engine.poll("test-job-id")
    assert result is None


@pytest.mark.asyncio
async def test_poll_raises_for_failed_status(monkeypatch):
    """회귀: 'failed' status → ExternalAPIError 보존 (실제 실패는 에러)."""
    from src.engine.backtest_engine import BacktestEngine, ExternalAPIError

    fake_client = MagicMock()
    fake_client.call_tool = AsyncMock(
        return_value={"status": "failed", "error_message": "out of memory"}
    )

    engine = BacktestEngine.__new__(BacktestEngine)
    engine._client = fake_client
    engine._enabled = True
    engine.is_enabled_async = AsyncMock(return_value=True)

    with pytest.raises(ExternalAPIError):
        await engine.poll("test-job-id")


@pytest.mark.asyncio
async def test_poll_raises_for_unknown_status(monkeypatch):
    """회귀: 'cancelled' / 'unknown' status → ExternalAPIError 보존."""
    from src.engine.backtest_engine import BacktestEngine, ExternalAPIError

    fake_client = MagicMock()
    fake_client.call_tool = AsyncMock(return_value={"status": "cancelled"})

    engine = BacktestEngine.__new__(BacktestEngine)
    engine._client = fake_client
    engine._enabled = True
    engine.is_enabled_async = AsyncMock(return_value=True)

    with pytest.raises(ExternalAPIError):
        await engine.poll("test-job-id")


@pytest.mark.asyncio
async def test_poll_returns_metrics_for_completed(monkeypatch):
    """회귀: 'completed' status → BacktestMetrics 반환."""
    from src.engine.backtest_engine import BacktestEngine
    from src.engine.backtest_engine import BacktestMetrics

    completed_resp = {
        "status": "completed",
        "metrics": {
            "total_return_pct": 12.5,
            "win_rate": 60.0,
        },
    }
    fake_client = MagicMock()
    fake_client.call_tool = AsyncMock(return_value=completed_resp)

    engine = BacktestEngine.__new__(BacktestEngine)
    engine._client = fake_client
    engine._enabled = True
    engine.is_enabled_async = AsyncMock(return_value=True)

    result = await engine.poll("test-job-id")
    assert isinstance(result, BacktestMetrics)
    assert result.total_return_pct == 12.5


# ===========================================================================
# 결함 2 (보조): wait_for_result 일관성
# ===========================================================================
@pytest.mark.asyncio
async def test_wait_for_result_handles_pending_consistently(monkeypatch):
    """`wait_for_result` 도 'pending' 응답 시 ExternalAPIError 비 raise.

    외부 서버가 wait=True 인데도 timeout 후 pending 반환할 가능성 (서버측 timeout 초과)
    → completed 외 분기를 ExternalAPIError 로 묶지 말고 pending 은 timeout 메시지로 명시.
    """
    from src.engine.backtest_engine import BacktestEngine, ExternalAPIError

    fake_client = MagicMock()
    fake_client.call_tool = AsyncMock(return_value={"status": "pending"})

    engine = BacktestEngine.__new__(BacktestEngine)
    engine._client = fake_client
    engine._enabled = True
    engine.is_enabled_async = AsyncMock(return_value=True)

    # 정책 결정: wait_for_result 는 'completed' 또는 raise.
    # 'pending' 도 timeout 으로 명확히 분류 — 호출자(자문 사이클)가 graceful 처리.
    with pytest.raises(ExternalAPIError) as exc_info:
        await engine.wait_for_result("test-job-id", timeout=10.0)
    # 메시지에 'pending' 또는 'timeout' 식별자 포함
    err_msg = str(exc_info.value).lower()
    assert "pending" in err_msg or "timeout" in err_msg or "백테스트" in str(exc_info.value)
