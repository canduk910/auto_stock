"""사이클 76 Red — `_request` 메인 단일 5xx WARNING dedupe (60s 윈도우).

배경 (2026-06-08 사이클 76 Phase 1 진단):
- `src/api/base.py::_request` (메인 단일) 의 `logger.warning("HTTP %s (attempt N/3)")` 사이트
  (line 358) 가 **사이클 18 dedupe 헬퍼 미적용** 잔존
- 영향: 매매/잔고/체결조회/체결통보 호출이 5xx 폭주 시 WARNING 폭주 (운영 로그 dup 5.80x)
- 사이클 18 (`_request_via_quote_pool` 영역) 의 `_record_5xx_for_dedupe` + 60s WARNING
  dedupe 패턴을 메인 `_request` 영역에 *직답습* (자금 안전 핵심 호출 → 신규 dedupe state
  분리, `_request_5xx_dedupe` + `_request_5xx_dedupe_lock`)

옵션 E (사용자 결정 1, 사이클 74 답습 + 사이클 18 답습 하이브리드):
- 동일 (path, status) 키 60s 윈도우 첫 1회만 WARNING + 카운트 누적
- 윈도우 만료 → 다음 발생 첫 WARNING + 카운트 1 리셋
- 다른 path / 다른 status → 독립 dedupe (키 분리)

설계:
- 모듈 상수: `_REQUEST_5XX_DEDUPE_WINDOW = 60.0`
- 상태: `_request_5xx_dedupe: dict[(path, status), (window_start_loop_ts, count)]`
- 락: `_request_5xx_dedupe_lock = asyncio.Lock()`
- 헬퍼: `_record_request_5xx_for_dedupe(path, status) -> bool` (should_emit 반환)

Q4 (사용자 결정): 메인 + 풀 dedupe state **분리** (사이클 18 `_quote_5xx_dedupe`
비침범, `_request_5xx_dedupe` 신규 모듈 변수).

검증 사양 (4 케이스):
- G-MD1: 첫 호출 → should_emit=True + count=1
- G-MD2: 동일 키 5회 → 첫 True + 4 False + count=5
- G-MD3: 60s 만료 후 → True + 카운트 1 리셋
- G-MD4: 다른 path 또는 다른 status → 각각 별도 dedupe

영속 의무 (변경 0):
- 사이클 18 `_record_5xx_for_dedupe` (시세 풀 영역, key=(path, label, status))
- 사이클 17 OPSP0002 backoff (`websocket.py` 영역)
- 사이클 72 `_DbLogHandler` 500ms dedupe (`main.py` 영역)
"""
from __future__ import annotations

import asyncio

import pytest

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# 헬퍼 — 메인 `_request` dedupe state 초기화 (격리 보장)
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _reset_request_dedupe_state():
    """매 테스트마다 `_request_5xx_dedupe` dict 초기화 — Green 후 모듈 변수 존재 가정.

    Red 단계에서는 모듈 변수 미존재 → AttributeError 흡수 (테스트 자체는 헬퍼 호출 시 FAIL).
    """
    from src.api import base as _b

    state = getattr(_b, "_request_5xx_dedupe", None)
    if state is not None:
        state.clear()
    yield
    state = getattr(_b, "_request_5xx_dedupe", None)
    if state is not None:
        state.clear()


# ---------------------------------------------------------------------------
# G-MD1: 첫 호출 → should_emit=True + count=1
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_g_md1_first_5xx_emits_warning_and_count_one():
    """G-MD1: 첫 (path, status) 호출 → should_emit=True + count=1.

    `_record_request_5xx_for_dedupe(path, status)` 헬퍼 미존재 시 Red FAIL.
    """
    from src.api import base as _b

    record = getattr(_b, "_record_request_5xx_for_dedupe", None)
    assert record is not None, (
        "사이클 76 G-MD1: `_record_request_5xx_for_dedupe` 헬퍼 미존재 — Green 발주 대상"
    )

    path = "/uapi/domestic-stock/v1/trading/order-cash"
    should_emit = await record(path, 503)

    assert should_emit is True, "첫 발생은 WARNING emit 해야 함"
    state = getattr(_b, "_request_5xx_dedupe", None)
    assert state is not None, "사이클 76 G-MD1: `_request_5xx_dedupe` 모듈 변수 미존재"
    key = (path, 503)
    assert key in state, f"첫 발생 후 dedupe state 등록 의무 — keys={list(state.keys())}"
    _, count = state[key]
    assert count == 1, f"첫 발생 카운트는 1, got {count}"


# ---------------------------------------------------------------------------
# G-MD2: 동일 키 5회 호출 → 첫 True + 4 False + count=5
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_g_md2_repeated_5xx_within_window_suppresses_warning():
    """G-MD2: 동일 (path, status) 윈도우 내 5회 → 첫 True + 나머지 4 False + count=5 누적.

    사이클 18 답습 — WARNING 폭주 1행 + 4 suppress.
    """
    from src.api import base as _b

    record = getattr(_b, "_record_request_5xx_for_dedupe", None)
    assert record is not None, (
        "사이클 76 G-MD2: `_record_request_5xx_for_dedupe` 헬퍼 미존재 — Green 발주 대상"
    )

    path = "/uapi/domestic-stock/v1/trading/order-cash"
    results: list[bool] = []
    for _ in range(5):
        r = await record(path, 503)
        results.append(r)

    assert results == [True, False, False, False, False], (
        f"첫 emit + 4 suppress, got {results}"
    )

    state = getattr(_b, "_request_5xx_dedupe", None)
    assert state is not None
    key = (path, 503)
    _, count = state[key]
    assert count == 5, f"카운트 누적 5, got {count}"


# ---------------------------------------------------------------------------
# G-MD3: 60s 만료 후 → should_emit=True + 카운트 1 리셋
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_g_md3_5xx_after_window_expiry_emits_again_and_resets_count(
    monkeypatch,
):
    """G-MD3: 60s 초과 후 동일 키 재발생 → True + 카운트 1 리셋.

    `asyncio.get_event_loop().time()` stub 으로 시각 조작 (사이클 18 패턴 답습).
    """
    from src.api import base as _b

    record = getattr(_b, "_record_request_5xx_for_dedupe", None)
    assert record is not None, (
        "사이클 76 G-MD3: `_record_request_5xx_for_dedupe` 헬퍼 미존재 — Green 발주 대상"
    )

    path = "/uapi/domestic-stock/v1/trading/order-cash"
    times = [1000.0, 1000.5, 1100.0]  # 첫 호출 / 윈도우 내 / 100s 경과
    call_idx = [0]

    def _fake_time():
        idx = min(call_idx[0], len(times) - 1)
        return times[idx]

    real_loop = asyncio.get_event_loop()
    monkeypatch.setattr(real_loop, "time", _fake_time)

    call_idx[0] = 0
    r1 = await record(path, 503)
    assert r1 is True, "첫 발생 emit"

    call_idx[0] = 1
    r2 = await record(path, 503)
    assert r2 is False, "윈도우 내 suppress"

    state = getattr(_b, "_request_5xx_dedupe", None)
    assert state is not None
    key = (path, 503)
    _, count_before_expire = state[key]
    assert count_before_expire == 2, f"윈도우 내 count=2, got {count_before_expire}"

    # 100s 경과 (>60s 윈도우)
    call_idx[0] = 2
    r3 = await record(path, 503)
    assert r3 is True, "윈도우 만료 후 재 emit"

    _, count_after_expire = state[key]
    assert count_after_expire == 1, (
        f"윈도우 만료 후 카운트 리셋되어 1, got {count_after_expire}"
    )


# ---------------------------------------------------------------------------
# G-MD4: 다른 path 또는 status → 각각 독립 dedupe (키 분리)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_g_md4_different_keys_tracked_independently():
    """G-MD4: (path_A, 503) / (path_B, 503) / (path_A, 502) 각각 독립 dedupe.

    Q4 (메인 + 풀 분리) 와 별도 — 메인 영역 내에서도 키 분리 의무.
    """
    from src.api import base as _b

    record = getattr(_b, "_record_request_5xx_for_dedupe", None)
    assert record is not None, (
        "사이클 76 G-MD4: `_record_request_5xx_for_dedupe` 헬퍼 미존재 — Green 발주 대상"
    )

    path_a = "/uapi/domestic-stock/v1/trading/order-cash"
    path_b = "/uapi/domestic-stock/v1/trading/inquire-balance"

    r1 = await record(path_a, 503)  # 첫 path_a
    r2 = await record(path_b, 503)  # 다른 path
    r3 = await record(path_a, 502)  # 같은 path, 다른 status

    assert r1 is True and r2 is True and r3 is True, (
        f"키 다르면 각각 첫 emit, got {(r1, r2, r3)}"
    )

    state = getattr(_b, "_request_5xx_dedupe", None)
    assert state is not None
    assert len(state) == 3, (
        f"세 키 독립 추적, got {len(state)} 엔트리, keys={list(state.keys())}"
    )

    # Q4 — 메인 dedupe state 와 풀 dedupe state 분리 의무
    quote_state = getattr(_b, "_quote_5xx_dedupe", None)
    assert quote_state is not None, "사이클 18 `_quote_5xx_dedupe` 영속 의무"
    assert len(quote_state) == 0, (
        f"Q4: 메인 record 호출이 풀 dedupe state 침범 금지, "
        f"got {len(quote_state)} 엔트리 in `_quote_5xx_dedupe`"
    )
