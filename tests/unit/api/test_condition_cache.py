"""PR-C (2026-05-14) — condition.py TTL 캐시 검증.

`fetch_stock_detail` 5초 TTL / `fetch_daily_candles` 300초 TTL 캐시. 동일 ticker
반복 조회 시 KIS 호출 1회로 수렴 (5xx 노출 면적 축소 + 외부 부하 감소).

회귀 가드:
- TTL 만료 후 재호출 시 KIS 호출 발생
- days 별 캐시 키 분리 (60일 vs 21일 등)
- `_reset_daily_state` 호출 후 캐시 비어있음 (clear_caches API)
- 동시 다회 호출 시 race condition 없음 (asyncio.Lock)
"""

from __future__ import annotations

import asyncio

from unittest.mock import AsyncMock

import pytest

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def reset_caches_around_test():
    """매 테스트마다 캐시 초기화 — 격리."""
    from src.api import condition

    condition.clear_caches()
    yield
    condition.clear_caches()


# ---------------------------------------------------------------------------
# fetch_stock_detail — TTL hit
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_fetch_stock_detail_hits_cache_within_ttl(monkeypatch):
    """첫 호출 후 TTL 내 재호출은 KIS 호출 발생 안 함."""
    from src.api import condition

    mock_get = AsyncMock(return_value={"output": {"stck_prpr": "65000"}})
    monkeypatch.setattr(condition, "kis_get", mock_get)

    r1 = await condition.fetch_stock_detail("005930")
    r2 = await condition.fetch_stock_detail("005930")
    r3 = await condition.fetch_stock_detail("005930")

    assert r1 == r2 == r3 == {"stck_prpr": "65000"}
    assert mock_get.await_count == 1, "TTL 내 KIS 호출 1회만"


# ---------------------------------------------------------------------------
# fetch_stock_detail — TTL 만료 후 재호출
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_fetch_stock_detail_miss_after_ttl(monkeypatch):
    """TTL 경과 후 재호출 시 KIS 호출 발생."""
    from src.api import condition

    mock_get = AsyncMock(return_value={"output": {"stck_prpr": "65000"}})
    monkeypatch.setattr(condition, "kis_get", mock_get)

    # monotonic 을 monkeypatch — 시간 흐름 시뮬
    current_time = [1000.0]

    def fake_monotonic():
        return current_time[0]

    monkeypatch.setattr(condition.time, "monotonic", fake_monotonic)

    await condition.fetch_stock_detail("005930")  # t=1000
    assert mock_get.await_count == 1

    # TTL(5s) 내 → 캐시 hit
    current_time[0] = 1004.0
    await condition.fetch_stock_detail("005930")
    assert mock_get.await_count == 1

    # TTL 경과 → miss
    current_time[0] = 1006.0
    await condition.fetch_stock_detail("005930")
    assert mock_get.await_count == 2


# ---------------------------------------------------------------------------
# fetch_stock_detail — ticker 별 캐시 키 분리
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_fetch_stock_detail_separate_cache_per_ticker(monkeypatch):
    from src.api import condition

    responses = {
        "005930": {"output": {"stck_prpr": "65000"}},
        "000660": {"output": {"stck_prpr": "180000"}},
    }

    async def _fake_get(_path, _tr, params):
        return responses[params["fid_input_iscd"]]

    mock = AsyncMock(side_effect=_fake_get)
    monkeypatch.setattr(condition, "kis_get", mock)

    r1 = await condition.fetch_stock_detail("005930")
    r2 = await condition.fetch_stock_detail("000660")
    r3 = await condition.fetch_stock_detail("005930")  # 캐시 hit
    r4 = await condition.fetch_stock_detail("000660")  # 캐시 hit

    assert r1["stck_prpr"] == "65000"
    assert r2["stck_prpr"] == "180000"
    assert r1 == r3
    assert r2 == r4
    # ticker 당 1회씩만 KIS 호출
    assert mock.await_count == 2


# ---------------------------------------------------------------------------
# fetch_daily_candles — days 별 캐시 키 분리
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_fetch_daily_candles_caches_per_days_key(monkeypatch):
    """동일 ticker + 다른 days → 별도 캐시. 같은 (ticker, days) 만 재사용."""
    from src.api import condition

    call_count = [0]

    async def _fake_get(_path, _tr, params):
        call_count[0] += 1
        # output2에 days 일치 응답
        return {
            "output2": [
                {"stck_bsop_date": f"2026050{i}", "stck_clpr": str(60000 + i)}
                for i in range(1, 10)
            ]
        }

    monkeypatch.setattr(condition, "kis_get", _fake_get)

    await condition.fetch_daily_candles("005930", days=21)
    await condition.fetch_daily_candles("005930", days=21)  # 캐시 hit
    assert call_count[0] == 1

    await condition.fetch_daily_candles("005930", days=60)  # 다른 days → miss
    assert call_count[0] == 2

    await condition.fetch_daily_candles("005930", days=60)  # 캐시 hit
    assert call_count[0] == 2


# ---------------------------------------------------------------------------
# clear_caches / _reset_daily_state 통합
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_fetch_stock_detail_cache_cleared_on_clear_caches(monkeypatch):
    """`clear_caches()` 직접 호출 시 캐시 무효화 → 다음 호출은 KIS 발생."""
    from src.api import condition

    mock_get = AsyncMock(return_value={"output": {"stck_prpr": "65000"}})
    monkeypatch.setattr(condition, "kis_get", mock_get)

    await condition.fetch_stock_detail("005930")
    await condition.fetch_stock_detail("005930")
    assert mock_get.await_count == 1

    condition.clear_caches()

    await condition.fetch_stock_detail("005930")
    assert mock_get.await_count == 2, "clear_caches 후 캐시 miss → 재조회"


@pytest.mark.asyncio
async def test_reset_daily_state_clears_condition_caches(monkeypatch):
    """`scheduler._reset_daily_state()` 가 condition 캐시도 일괄 무효화한다.

    안전 규칙(CLAUDE.md): `_reset_daily_state` 에 새 상태(캐시) 추가 시 정리 누락 금지.
    """
    from src.api import condition
    from src.engine.scheduler import TradingScheduler

    mock_get = AsyncMock(return_value={"output": {"stck_prpr": "65000"}})
    monkeypatch.setattr(condition, "kis_get", mock_get)

    # 캐시 시드
    await condition.fetch_stock_detail("005930")
    assert "005930" in condition._price_cache

    # scheduler instance 의 reset 호출 (sync)
    sched = TradingScheduler()
    sched._reset_daily_state()

    assert "005930" not in condition._price_cache, "reset 후 price cache 비어있음"
    assert condition._candle_cache == {}, "reset 후 candle cache 비어있음"


# ---------------------------------------------------------------------------
# 동시 호출 — KIS 호출 1회 보장 (lock + 캐시 협조)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_fetch_stock_detail_concurrent_calls_share_first_fetch(monkeypatch):
    """asyncio.gather 로 10회 동시 호출해도 KIS 호출 1회만 (single-flight).

    명세(02_bundle_abc): 동시 호출 시 첫 호출만 fetch, 나머지는 같은 결과 합류.
    """
    import asyncio

    from src.api import condition

    call_count = [0]

    async def _slow_get(*_args, **_kwargs):
        call_count[0] += 1
        await asyncio.sleep(0.01)
        return {"output": {"stck_prpr": "65000"}}

    monkeypatch.setattr(condition, "kis_get", _slow_get)

    results = await asyncio.gather(*(
        condition.fetch_stock_detail("005930") for _ in range(10)
    ))

    assert all(r == {"stck_prpr": "65000"} for r in results)
    # single-flight — 10개 동시 호출이어도 KIS 1회만
    assert call_count[0] == 1, f"single-flight 위반: KIS {call_count[0]}회 호출"


@pytest.mark.asyncio
async def test_fetch_daily_candles_concurrent_calls_share_first_fetch(monkeypatch):
    """daily candle 동시 호출도 single-flight."""
    import asyncio

    from src.api import condition

    call_count = [0]

    async def _slow_get(*_args, **_kwargs):
        call_count[0] += 1
        await asyncio.sleep(0.01)
        return {
            "output2": [
                {"stck_bsop_date": "20260512", "stck_clpr": "65000"},
            ]
        }

    monkeypatch.setattr(condition, "kis_get", _slow_get)

    results = await asyncio.gather(*(
        condition.fetch_daily_candles("005930", days=21) for _ in range(8)
    ))

    assert all(len(r) == 1 for r in results)
    assert call_count[0] == 1, f"daily single-flight 위반: KIS {call_count[0]}회"


# ---------------------------------------------------------------------------
# PR-C2 (2026-05-14) — Copilot 리뷰 8건 회귀 가드
#
# 기존 Future 기반 single-flight 의 결함 4종:
#  1) `asyncio.get_event_loop()` deprecation (Py 3.12+)
#  2) `except BaseException` 이 CancelledError 흡수 (cancel 의미 깨짐)
#  3) joiner cancel 전파로 inflight Future 전체 깨짐 (`InvalidStateError`)
#  4) `clear_caches()` inflight race — 새 영업일 캐시에 stale write
#
# 재설계: `Future` → `asyncio.Task` + joiner 는 `asyncio.shield(task)` 로 await,
# `clear_caches()` 가 epoch counter bump + fetch 완료 시 epoch 일치할 때만 cache write.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_stock_detail_cancellation_safe_for_joiners(monkeypatch):
    """joiner 1 task 가 cancel 돼도 joiner 2 는 정상 결과 받음 (asyncio.shield)."""
    import asyncio

    from src.api import condition

    call_count = [0]
    started = asyncio.Event()
    proceed = asyncio.Event()

    async def _slow_get(*_args, **_kwargs):
        call_count[0] += 1
        started.set()
        await proceed.wait()
        return {"output": {"stck_prpr": "65000"}}

    monkeypatch.setattr(condition, "kis_get", _slow_get)

    # joiner1 + joiner2 동시에 await — 첫 호출이 fetch 담당, 둘 다 shield 로 합류
    j1 = asyncio.create_task(condition.fetch_stock_detail("005930"))
    j2 = asyncio.create_task(condition.fetch_stock_detail("005930"))

    await started.wait()  # fetch 시작 대기
    await asyncio.sleep(0)  # j1/j2 모두 await fut 진입 보장

    # joiner1 cancel — shield 가 inflight task 자체로의 cancel 전파를 차단해야 함
    j1.cancel()
    with pytest.raises(asyncio.CancelledError):
        await j1

    # fetch 완료
    proceed.set()

    # joiner2 는 정상 결과 수신
    result2 = await j2
    assert result2 == {"stck_prpr": "65000"}
    assert call_count[0] == 1, "single-flight 유지"


@pytest.mark.asyncio
async def test_fetch_stock_detail_clear_caches_during_inflight_skips_cache_write(monkeypatch):
    """inflight 중 clear_caches() 호출 → 결과 정상 반환되지만 캐시 write 차단 (epoch guard)."""
    import asyncio

    from src.api import condition

    call_count = [0]
    started = asyncio.Event()
    proceed = asyncio.Event()

    async def _slow_get(*_args, **_kwargs):
        call_count[0] += 1
        started.set()
        await proceed.wait()
        return {"output": {"stck_prpr": "65000"}}

    monkeypatch.setattr(condition, "kis_get", _slow_get)

    task = asyncio.create_task(condition.fetch_stock_detail("005930"))
    await started.wait()

    # inflight 진행 중 clear_caches 호출 → epoch 증가
    condition.clear_caches()

    proceed.set()
    result = await task

    # 결과는 정상 반환
    assert result == {"stck_prpr": "65000"}
    # 캐시 write 는 차단 — 다음 호출은 cache miss → 새 KIS fetch
    assert "005930" not in condition._price_cache, (
        "clear_caches 가 inflight 중 호출됐으면 결과는 stale → 캐시 write 차단"
    )

    # 후속 호출이 새 fetch 발생하는지 검증
    proceed2 = asyncio.Event()

    async def _next_get(*_args, **_kwargs):
        call_count[0] += 1
        proceed2.set()
        return {"output": {"stck_prpr": "70000"}}

    monkeypatch.setattr(condition, "kis_get", _next_get)
    result2 = await condition.fetch_stock_detail("005930")
    assert result2 == {"stck_prpr": "70000"}
    assert call_count[0] == 2, "epoch bump 후 새 fetch 발생"


@pytest.mark.asyncio
async def test_fetch_stock_detail_uses_get_running_loop_not_get_event_loop(monkeypatch):
    """asyncio.get_event_loop() 미사용 검증 — 호출되면 raise 하도록 monkeypatch."""
    from src.api import condition

    def _boom(*_args, **_kwargs):
        raise RuntimeError("get_event_loop must not be called")

    monkeypatch.setattr("asyncio.get_event_loop", _boom)

    mock_get = AsyncMock(return_value={"output": {"stck_prpr": "65000"}})
    monkeypatch.setattr(condition, "kis_get", mock_get)

    result = await condition.fetch_stock_detail("005930")
    assert result == {"stck_prpr": "65000"}


@pytest.mark.asyncio
async def test_fetch_stock_detail_does_not_emit_future_exception_warning(monkeypatch, caplog):
    """예외 raise 시 'Future exception was never retrieved' 경고 미발생.

    Task 기반에서 joiner 들이 모두 await 로 예외를 회수하므로 경고 없음.
    """
    import asyncio
    import logging

    from src.api import condition

    async def _failing_get(*_args, **_kwargs):
        raise RuntimeError("KIS 5xx")

    monkeypatch.setattr(condition, "kis_get", _failing_get)

    with caplog.at_level(logging.WARNING):
        with pytest.raises(RuntimeError, match="KIS 5xx"):
            await condition.fetch_stock_detail("005930")
        # gc 트리거 — Future exception 회수 안 됐으면 경고 발생
        import gc
        gc.collect()
        await asyncio.sleep(0)

    text = " ".join(rec.message for rec in caplog.records)
    assert "exception was never retrieved" not in text, (
        "Task await 에서 예외 회수 — Future exception 경고 잔존 시 운영 잡음"
    )


# fetch_daily_candles — 동일 4종 회귀 가드


@pytest.mark.asyncio
async def test_fetch_daily_candles_cancellation_safe_for_joiners(monkeypatch):
    """daily candle joiner cancel 안전성 — asyncio.shield 검증."""
    import asyncio

    from src.api import condition

    call_count = [0]
    started = asyncio.Event()
    proceed = asyncio.Event()

    async def _slow_get(*_args, **_kwargs):
        call_count[0] += 1
        started.set()
        await proceed.wait()
        return {
            "output2": [
                {"stck_bsop_date": "20260512", "stck_clpr": "65000"},
            ]
        }

    monkeypatch.setattr(condition, "kis_get", _slow_get)

    j1 = asyncio.create_task(condition.fetch_daily_candles("005930", days=21))
    j2 = asyncio.create_task(condition.fetch_daily_candles("005930", days=21))

    await started.wait()
    await asyncio.sleep(0)

    j1.cancel()
    with pytest.raises(asyncio.CancelledError):
        await j1

    proceed.set()
    result2 = await j2
    assert len(result2) == 1
    assert call_count[0] == 1


@pytest.mark.asyncio
async def test_fetch_daily_candles_clear_caches_during_inflight_skips_cache_write(monkeypatch):
    """daily candle inflight 중 clear_caches() → epoch guard 로 cache write 차단."""
    import asyncio

    from src.api import condition

    call_count = [0]
    started = asyncio.Event()
    proceed = asyncio.Event()

    async def _slow_get(*_args, **_kwargs):
        call_count[0] += 1
        started.set()
        await proceed.wait()
        return {
            "output2": [
                {"stck_bsop_date": "20260512", "stck_clpr": "65000"},
            ]
        }

    monkeypatch.setattr(condition, "kis_get", _slow_get)

    task = asyncio.create_task(condition.fetch_daily_candles("005930", days=21))
    await started.wait()

    condition.clear_caches()

    proceed.set()
    result = await task
    assert len(result) == 1
    assert ("005930", 21) not in condition._candle_cache, (
        "clear_caches inflight 중 → 캐시 write 차단"
    )


@pytest.mark.asyncio
async def test_fetch_daily_candles_uses_get_running_loop_not_get_event_loop(monkeypatch):
    """daily candle 도 get_event_loop 미사용."""
    from src.api import condition

    def _boom(*_args, **_kwargs):
        raise RuntimeError("get_event_loop must not be called")

    monkeypatch.setattr("asyncio.get_event_loop", _boom)

    async def _fake_get(*_args, **_kwargs):
        return {"output2": [{"stck_bsop_date": "20260512", "stck_clpr": "65000"}]}

    monkeypatch.setattr(condition, "kis_get", _fake_get)

    result = await condition.fetch_daily_candles("005930", days=21)
    assert len(result) == 1


@pytest.mark.asyncio
async def test_fetch_daily_candles_does_not_emit_future_exception_warning(monkeypatch, caplog):
    """daily candle 예외 시 'Future exception was never retrieved' 경고 미발생."""
    import asyncio
    import logging

    from src.api import condition

    async def _failing_get(*_args, **_kwargs):
        raise RuntimeError("KIS 5xx")

    monkeypatch.setattr(condition, "kis_get", _failing_get)

    with caplog.at_level(logging.WARNING):
        with pytest.raises(RuntimeError, match="KIS 5xx"):
            await condition.fetch_daily_candles("005930", days=21)
        import gc
        gc.collect()
        await asyncio.sleep(0)

    text = " ".join(rec.message for rec in caplog.records)
    assert "exception was never retrieved" not in text


# CancelledError 분리 처리 검증 — fetch helper 내부에서 CancelledError 가
# Exception 분기로 잘못 잡혀 다른 joiner 에게 전파되지 않아야 함.


@pytest.mark.asyncio
async def test_fetch_stock_detail_cancelled_error_does_not_corrupt_inflight(monkeypatch):
    """fetch task 가 cancel 됐을 때 inflight 정리 + CancelledError 정상 전파.

    이후 새 호출은 새 task 발화 (이전 cancel 잔존 X).
    """
    import asyncio

    from src.api import condition

    call_count = [0]
    proceed = asyncio.Event()

    async def _slow_get(*_args, **_kwargs):
        call_count[0] += 1
        await proceed.wait()
        return {"output": {"stck_prpr": "65000"}}

    monkeypatch.setattr(condition, "kis_get", _slow_get)

    task = asyncio.create_task(condition.fetch_stock_detail("005930"))
    await asyncio.sleep(0.01)  # fetch 시작

    # inflight 자체를 직접 cancel (epoch guard 와는 별개로 task lifecycle 검증)
    inflight = condition._inflight_price.get("005930")
    assert inflight is not None
    inflight.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task

    # inflight 정리 확인
    await asyncio.sleep(0)
    assert "005930" not in condition._inflight_price, "cancel 후 inflight 정리"

    # 새 호출은 새 task 발화
    proceed2 = asyncio.Event()

    async def _next_get(*_args, **_kwargs):
        call_count[0] += 1
        proceed2.set()
        return {"output": {"stck_prpr": "70000"}}

    monkeypatch.setattr(condition, "kis_get", _next_get)
    result = await condition.fetch_stock_detail("005930")
    assert result == {"stck_prpr": "70000"}
    assert call_count[0] == 2


# ---------------------------------------------------------------------------
# PR-C2 보강 (Copilot 2026-05-14)
# ---------------------------------------------------------------------------

def test_daily_candles_today_called_once_for_midnight_safety():
    """소스코드 분석으로 `_fetch_daily_candles_and_cache` 가 `date.today()` 를
    1회만 호출함을 검증 — 두 번 호출 시 자정 경계 race (end_date/start_date 날짜 어긋남).
    PR-C2 보강 (Copilot, 2026-05-14).
    """
    import inspect
    from src.api import condition

    src = inspect.getsource(condition._fetch_daily_candles_and_cache)
    # 코멘트 라인 제외 — 실제 함수 호출만 카운트
    code_lines = [ln for ln in src.splitlines() if "date.today()" in ln and not ln.lstrip().startswith("#")]
    today_calls = sum(ln.count("date.today()") for ln in code_lines)
    assert today_calls == 1, (
        f"date.today() 는 1회만 호출돼야 자정 race 안전 (실제 {today_calls}회)\n"
        f"매칭 라인: {code_lines}"
    )


@pytest.mark.asyncio
async def test_stock_detail_task_exception_drained_no_warning(monkeypatch: pytest.MonkeyPatch, caplog):
    """모든 joiner cancel 후 inflight task 가 예외로 종료해도 'Task exception was never retrieved' 미발생."""
    import logging as _logging
    from src.api import condition

    condition.clear_caches()

    async def _failing_get(*args, **kwargs):
        await asyncio.sleep(0.01)
        raise RuntimeError("KIS down")

    monkeypatch.setattr(condition, "kis_get", _failing_get)

    # joiner 생성 후 즉시 cancel — task 는 backgrond 에서 계속 실행
    joiner = asyncio.create_task(condition.fetch_stock_detail("005930"))
    await asyncio.sleep(0)  # task 발화 기회
    joiner.cancel()
    try:
        await joiner
    except (asyncio.CancelledError, RuntimeError):
        pass

    # inflight task 가 예외로 종료될 때까지 대기 + done_callback 발화
    await asyncio.sleep(0.05)

    # caplog 에 "Task exception was never retrieved" 메시지 없어야 함
    warning_msgs = [r.getMessage() for r in caplog.records if r.levelno >= _logging.WARNING]
    assert not any("Task exception was never retrieved" in m for m in warning_msgs), (
        f"Task exception 회수 안 됨: {warning_msgs}"
    )


@pytest.mark.asyncio
async def test_daily_candles_task_exception_drained_no_warning(monkeypatch: pytest.MonkeyPatch, caplog):
    """fetch_daily_candles 동일 — joiner cancel 시 inflight task 예외 회수."""
    import logging as _logging
    from src.api import condition

    condition.clear_caches()

    async def _failing_get(*args, **kwargs):
        await asyncio.sleep(0.01)
        raise RuntimeError("KIS down")

    monkeypatch.setattr(condition, "kis_get", _failing_get)

    joiner = asyncio.create_task(condition.fetch_daily_candles("005930", days=21))
    await asyncio.sleep(0)
    joiner.cancel()
    try:
        await joiner
    except (asyncio.CancelledError, RuntimeError):
        pass

    await asyncio.sleep(0.05)

    warning_msgs = [r.getMessage() for r in caplog.records if r.levelno >= _logging.WARNING]
    assert not any("Task exception was never retrieved" in m for m in warning_msgs), (
        f"Task exception 회수 안 됨: {warning_msgs}"
    )
