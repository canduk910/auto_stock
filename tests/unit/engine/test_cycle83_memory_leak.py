"""사이클 83 G-ML1 — 5분 윈도우 종료 후 collector `len == 0` 검증 (메모리 leak 영구 차단).

명세 (`_workspace/red/cycle83_scan_pool_eager_refresh.md`):

Red 단계: flush 호출 사이트 미존재 → collector 무한 누적 → 운영 후 비워지지 않음 FAIL.
Green 단계: 5분 주기 task 가 collector flush → 윈도우 종료 후 `len == 0` PASS.

운영 메모리 leak 위험:
- `_scan_pool_eager_refresh_collector: list[dict]` 5분 윈도우 누적
- ticker 150건 × 60min/5min = 1,800 dict / hour 누적 가능 (flush 누락 시)
- 영업일 12시간 운영 = 21,600 dict / day 누적 = 메모리 leak HIGH

영속 의무:
- 사이클 78 G-ML1 패턴 답습
- 사이클 74 sampling/aggregation 패턴 영속
- 매매 안전성 영향 0 (collector 영역)
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit


# ===========================================================================
# G-ML1: 5분 주기 task 1회 실행 후 collector `len == 0` (운영 leak 차단)
# ===========================================================================
@pytest.mark.asyncio
async def test_g_ml1_periodic_task_clears_eager_refresh_collector(monkeypatch):
    """G-ML1: 5분 주기 task 1회 실행 후 `_scan_pool_eager_refresh_collector` `len == 0`.

    검증 방식 (사이클 78 G-ML1 답습):
    1. `_scan_pool_eager_refresh_collector` 에 임의 stats 누적
    2. 스케줄러 5분 주기 task 1회 실행 (asyncio.sleep monkeypatch 즉시 통과)
    3. collector `len == 0` 확인 (메모리 leak 차단)

    Red 상태 (사이클 83): 신규 함수/collector 미존재 → ImportError → FAIL.

    Green (사이클 84):
    - scanner.py 모듈 전역 `_scan_pool_eager_refresh_collector: list[dict]` +
      `record_*` + `flush_*` 함수 도입
    - scheduler.py `_scan_pool_eager_refresh_loop` 본체 5분 주기 flush 호출

    영구 가드 — 미래 신규 5분 주기 task 본체에서 flush 호출 제거 시 즉시 FAIL.
    """
    # Red 사전조건: scanner 모듈에서 collector 변수 import 시도
    try:
        from src.engine import scanner as _scanner_mod
        collector = getattr(
            _scanner_mod, "_scan_pool_eager_refresh_collector", None
        )
        record_fn = getattr(_scanner_mod, "record_scan_pool_eager_refresh", None)
        flush_fn = getattr(_scanner_mod, "flush_scan_pool_eager_refresh_collector", None)
    except ImportError:
        pytest.fail(
            "\n사이클 83 G-ML1 Red 상태 — scanner 모듈 import 실패."
        )

    if collector is None or record_fn is None or flush_fn is None:
        pytest.fail(
            f"\n사이클 83 G-ML1 Red 상태 — scanner 모듈 필수 컴포넌트 누락:\n"
            f"  _scan_pool_eager_refresh_collector: {collector!r}\n"
            f"  record_scan_pool_eager_refresh: {record_fn!r}\n"
            f"  flush_scan_pool_eager_refresh_collector: {flush_fn!r}\n\n"
            f"  Green (사이클 84): backend-dev 가 scanner.py 모듈 전역 +\n"
            f"  record/flush 함수 도입 의무 (사이클 74 패턴 답습).\n"
            f"  - `_scan_pool_eager_refresh_collector: list[dict] = []`\n"
            f"  - `def record_scan_pool_eager_refresh(stats: dict) -> None`\n"
            f"  - `def flush_scan_pool_eager_refresh_collector() -> None`"
        )

    # Step 1: collector 에 stats 누적 (5건)
    collector.clear()
    for i in range(5):
        record_fn({
            "candidates": 30 + i,
            "refreshed": 10 + i,
            "skipped": 18,
            "failed": 0,
            "elapsed_ms": 1500 + i * 100,
        })

    assert len(collector) == 5, (
        f"G-ML1: 사전 누적 collector 5 건 실패 (실제: {len(collector)})"
    )

    # Step 2: 5분 주기 task 1회 실행 (Green 시점 활성화)
    import asyncio
    from src.engine.scheduler import TradingScheduler

    scheduler_instance = TradingScheduler()
    scheduler_instance._running = True

    # asyncio.sleep monkeypatch → 즉시 통과 + 단일 루프 보장
    sleep_call_count = {"n": 0}
    original_sleep = asyncio.sleep

    async def _fast_sleep(delay):
        sleep_call_count["n"] += 1
        if sleep_call_count["n"] >= 1:
            scheduler_instance._running = False
        await original_sleep(0)

    monkeypatch.setattr("src.engine.scheduler.asyncio.sleep", _fast_sleep)

    # 사이클 85 hotfix — CI sandbox 환경 KIS API DNS resolve fail 차단 (운영 무영향).
    # `flush_scan_pool_eager_refresh_collector` 가 `stock_master.upsert_from_kis` 를 호출하나
    # CI sandbox 는 openapivts.koreainvestment.com 에 접근 불가 → 60s timeout.
    # `is_stale()` 를 False 로 mock = TTL fresh skip 분기 진입 → KIS 호출 0 → collector clear 만 검증
    # (테스트 의도 = collector len == 0, KIS 실제 호출 검증 아님).
    # 사이클 85 hotfix #2 — CI sandbox 환경 KIS API DNS race 영구 차단 (운영 무영향).
    # scheduler._scan_pool_eager_refresh_loop 는 매 윈도우마다 (1) scanner._scan_pool_eager_refresh_loop
    # async 호출 (KIS API stock_master.upsert_one), (2) flush_scan_pool_eager_refresh_collector sync 호출.
    # CI sandbox 는 openapivts.koreainvestment.com 접근 불가 → 60s timeout.
    # 시정: scanner async refresh 함수를 no-op 으로 교체 → KIS 호출 0 + flush 는 정상 호출 (collector clear).
    async def _noop_scanner_refresh(*_args, **_kwargs):
        pass

    monkeypatch.setattr(
        _scanner_mod, "_scan_pool_eager_refresh_loop", _noop_scanner_refresh
    )

    # Green 시점에 사용 가능한 함수 호출 시도
    loop_fn = getattr(
        scheduler_instance, "_scan_pool_eager_refresh_loop", None
    )
    if loop_fn is None:
        pytest.fail(
            "\n사이클 83 G-ML1 Red 상태 — `TradingScheduler._scan_pool_eager_refresh_loop` "
            "메서드 미존재.\n"
            "  Green (사이클 84): scheduler.py 에 신규 task 메서드 도입 의무."
        )

    await loop_fn()

    # Step 3: collector `len == 0` 검증 (메모리 leak 차단 영구 가드)
    assert len(collector) == 0, (
        f"\n사이클 83 G-ML1 위반 — 5분 주기 task 1회 실행 후 "
        f"`_scan_pool_eager_refresh_collector` 잔존 {len(collector)} 건.\n"
        f"  메모리 leak: 21,600 dict/day 누적 영구 (영업일 12시간 운영)\n"
        f"  시정: `_scan_pool_eager_refresh_loop` 본체에 "
        f"`flush_scan_pool_eager_refresh_collector()` 호출 추가.\n\n"
        f"  사이클 78 G-ML1 패턴 답습."
    )
