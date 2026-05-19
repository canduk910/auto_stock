"""사이클 18 Red — `[quote_pool] HTTP 500` WARNING dedupe + 60s INFO summary.

배경 (2026-05-19 사이클 17 옵션 A 안정화 직후 운영 로그 진단):
- `[quote_pool] HTTP 500 (attempt 1/3)` `label=ISA` 가 20분 18건 / 시간당 30+ 회 폭주
- `inquire-price` / `inquire-daily-itemchartprice` 두 path 가 보조 ISA 라벨에서 영구 5xx
- 메인 fallback 으로 결국 성공하나 **로그 폭주 + KIS 측 부담** 결함

해결책 (영역 A-1):
- 동일 (path, label, status) 키 60s 윈도우 내 재발생 시 WARNING 억제 + 카운트 누적
- 60s 윈도우 만료 시점에 `_emit_5xx_dedupe_summary()` 가 카운트 ≥ 2 인 항목만 INFO 1행 출력
- 첫 발생은 즉시 WARNING (운영자가 결함 감지 못 하면 안 됨)

검증 사양 (5 케이스):
1. 첫 발생 should_emit=True + count=1
2. 동일 키 5회 should_emit=False (1회 emit + 4 suppressed)
3. 윈도우 만료 (61s 경과) 후 should_emit=True + 카운트 리셋
4. summary 발화 → INFO 1행 출력 + dedupe state clear (count>=2 만 출력)
5. (path_A, label_X) 와 (path_B, label_X) 별도 추적, 윈도우 분리

설계:
- `_record_5xx_for_dedupe(path, label, status) -> bool` (`base.py`) — should_emit 반환
- `_emit_5xx_dedupe_summary() -> None` — 60s 주기 background task 호출. 윈도우 만료 + count>=2 인 키 1행 INFO + dedupe state clear
- `_QUOTE_5XX_DEDUPE_WINDOW=60.0` 모듈 상수
- 카운터: `_quote_5xx_dedupe: dict[(path,label,status), (window_start_ts, count)]`
- 락: `_quote_5xx_dedupe_lock` (asyncio.Lock)
"""
from __future__ import annotations

import asyncio
import logging
from unittest.mock import patch

import pytest

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# 헬퍼 — dedupe state 초기화 (격리 보장)
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _reset_dedupe_state():
    """매 테스트마다 `_quote_5xx_dedupe` dict 초기화."""
    from src.api import base as _b

    _b._quote_5xx_dedupe.clear()
    yield
    _b._quote_5xx_dedupe.clear()


# ---------------------------------------------------------------------------
# 사양 1 — 첫 발생 should_emit=True + count=1
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_first_5xx_emits_warning_and_resets_window():
    """첫 (path, label, status) 발생 → should_emit=True + count=1."""
    from src.api.base import _record_5xx_for_dedupe, _quote_5xx_dedupe

    should_emit = await _record_5xx_for_dedupe(
        "/uapi/domestic-stock/v1/quotations/inquire-price", "ISA", 500
    )
    assert should_emit is True, "첫 발생은 WARNING emit 해야 함"
    key = ("/uapi/domestic-stock/v1/quotations/inquire-price", "ISA", 500)
    _, count = _quote_5xx_dedupe[key]
    assert count == 1, f"첫 발생 카운트는 1, got {count}"


# ---------------------------------------------------------------------------
# 사양 2 — 동일 키 5회 should_emit=False (1회 emit + 4 suppressed)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_repeated_5xx_within_window_suppresses_warning():
    """동일 키 윈도우 내 5회 → 첫 True + 나머지 4회 False + count=5."""
    from src.api.base import _record_5xx_for_dedupe, _quote_5xx_dedupe

    path = "/uapi/domestic-stock/v1/quotations/inquire-price"
    results = []
    for _ in range(5):
        r = await _record_5xx_for_dedupe(path, "ISA", 500)
        results.append(r)

    assert results == [True, False, False, False, False], (
        f"첫 emit + 4 suppress, got {results}"
    )
    key = (path, "ISA", 500)
    _, count = _quote_5xx_dedupe[key]
    assert count == 5, f"카운트 누적 5, got {count}"


# ---------------------------------------------------------------------------
# 사양 3 — 윈도우 만료 후 should_emit=True + 카운트 리셋
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_5xx_after_window_expiry_emits_again(monkeypatch):
    """61s 점프 후 동일 키 재발생 → True + 카운트 1 리셋."""
    from src.api import base as _b

    path = "/uapi/domestic-stock/v1/quotations/inquire-price"
    base_time = 1000.0

    # 첫 호출 — t=1000
    monkeypatch.setattr(
        asyncio.get_event_loop(), "time", lambda: base_time, raising=False
    )
    # 안전한 monkeypatch — module-level wrapper 활용
    times = [base_time, base_time + 61.0]
    call_idx = [0]

    def _fake_time():
        idx = min(call_idx[0], len(times) - 1)
        return times[idx]

    # asyncio.get_event_loop().time() 를 직접 stub
    import asyncio as _asyncio
    real_loop = _asyncio.get_event_loop()
    monkeypatch.setattr(real_loop, "time", _fake_time)

    call_idx[0] = 0
    r1 = await _b._record_5xx_for_dedupe(path, "ISA", 500)
    assert r1 is True

    call_idx[0] = 1  # 61s 경과
    r2 = await _b._record_5xx_for_dedupe(path, "ISA", 500)
    assert r2 is True, "윈도우 만료 후 재발생은 다시 emit"

    key = (path, "ISA", 500)
    _, count = _b._quote_5xx_dedupe[key]
    assert count == 1, f"윈도우 만료 후 카운트 리셋, got {count}"


# ---------------------------------------------------------------------------
# 사양 4 — summary 발화 → INFO 1행 + dedupe clear
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_summary_emits_aggregate_for_repeated_5xx(monkeypatch, caplog):
    """5회 5xx 누적 + 윈도우 만료 후 summary 호출 → INFO 1행 + state clear."""
    from src.api import base as _b

    path = "/uapi/domestic-stock/v1/quotations/inquire-price"

    # 5회 같은 윈도우에서 누적 (t=1000)
    times = [1000.0, 1000.5, 1001.0, 1001.5, 1002.0, 1100.0]  # 5회 + summary 시각
    call_idx = [0]

    def _fake_time():
        idx = min(call_idx[0], len(times) - 1)
        return times[idx]

    import asyncio as _asyncio
    real_loop = _asyncio.get_event_loop()
    monkeypatch.setattr(real_loop, "time", _fake_time)

    for i in range(5):
        call_idx[0] = i
        await _b._record_5xx_for_dedupe(path, "ISA", 500)

    # 윈도우 만료 시점 summary
    call_idx[0] = 5  # t=1100 (100s 경과, > 60s 윈도우)

    caplog.set_level(logging.INFO, logger="src.api.base")
    await _b._emit_5xx_dedupe_summary()

    summary_records = [
        r for r in caplog.records if "quote_pool_5xx_summary" in r.getMessage()
    ]
    assert len(summary_records) == 1, (
        f"summary INFO 1행 발화 (count=5), got {len(summary_records)} 행"
    )
    msg = summary_records[0].getMessage()
    assert "ISA" in msg and "count=5" in msg and "status=500" in msg, (
        f"summary 메시지에 label/count/status 포함, got {msg!r}"
    )
    # dedupe state 는 윈도우 만료 키 제거됨
    key = (path, "ISA", 500)
    assert key not in _b._quote_5xx_dedupe, "summary 후 만료 키 제거"


# ---------------------------------------------------------------------------
# 사양 5 — 키별 독립 추적 (path 또는 label 다르면 별도 카운터)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_different_keys_tracked_independently():
    """(path_A, ISA) 와 (path_B, ISA) 별도 추적 — 두 번째 첫 emit 보존."""
    from src.api.base import _record_5xx_for_dedupe, _quote_5xx_dedupe

    path_a = "/uapi/domestic-stock/v1/quotations/inquire-price"
    path_b = "/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice"

    r1 = await _record_5xx_for_dedupe(path_a, "ISA", 500)
    r2 = await _record_5xx_for_dedupe(path_b, "ISA", 500)  # 다른 path
    r3 = await _record_5xx_for_dedupe(path_a, "quote-2", 500)  # 다른 label

    assert r1 is True and r2 is True and r3 is True, (
        f"키 다르면 각각 첫 emit, got {(r1, r2, r3)}"
    )
    assert len(_quote_5xx_dedupe) == 3, (
        f"세 키 독립 추적, got {len(_quote_5xx_dedupe)} 엔트리"
    )
