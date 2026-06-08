"""사이클 76 Red — `[api_retry_recovered]` 5분 collector 도입 (메인 + 풀 분리).

배경 (2026-06-08 사이클 76 Phase 1 진단):
- `_request` (메인) + `_request_via_quote_pool` (풀) 양쪽이 `attempt > 1` rt_cd=0 성공 시
  `[api_retry_recovered] path=... tr_id=... attempts=N` write_log 1행/매 호출 emit
- 운영 5xx 재시도 후 성공 빈발 → recovered 행 폭주 (api retry dup 5.80x 결함 중 일부)
- 사이클 74 옵션 E-1 `_ws_action_collector` 패턴 100% 답습 → 5분 윈도우 누적 + 1행 summary

옵션 E (사용자 결정 1, 사이클 74 답습 + 사이클 18 답습 하이브리드):
- 5분 윈도우 내 모든 recovered 누적 → `[api_retry_recovered_summary] window=300s
  total=N by_path={...}` 1행 INFO write_log (5→1 = 80% 감소)
- Q2 (사용자 결정): 빈 윈도우 (count=0) → emit 0 (no-op)
- Q4 (사용자 결정): 메인 + 풀 **분리** state — 각각 별도 collector

설계:
- 모듈 상수: `_API_RECOVERED_COLLECTOR_WINDOW = 300.0`
- 메인 상태: `_api_recovered_collector: dict[str, int]` (path → count)
- 풀 상태: `_quote_recovered_collector: dict[str, int]` (path → count) — Q4 분리
- 헬퍼:
  - `_record_api_recovered(path: str) -> None` — 메인 경유
  - `_record_quote_recovered(path: str) -> None` — 풀 경유
  - `_flush_api_recovered_collector() -> None` — 메인 collector 1행 summary + clear
  - `_flush_quote_recovered_collector() -> None` — 풀 collector 1행 summary + clear

검증 사양 (4 케이스):
- G-RC1: 5분 윈도우 내 메인 5회 recovered → 1행 summary (5→1 = 80% 감소)
- G-RC2: path 별 by_path 통계 정확 (`by_path={path_a:3, path_b:2}`)
- G-RC3: 빈 윈도우 (count=0) flush → emit 0 (Q2)
- G-RC4: 메인 + 풀 collector 분리 (Q4) — 각각 별도 flush

영속 의무 (변경 0):
- 사이클 74 `_ws_action_collector` (`websocket.py` 영역, 5분 윈도우)
- 사이클 17/29/66 stale watcher 영속
"""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# 헬퍼 — collector state 초기화 (격리 보장)
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _reset_collector_state():
    """매 테스트마다 메인/풀 recovered collector dict 초기화."""
    from src.api import base as _b

    for attr in ("_api_recovered_collector", "_quote_recovered_collector"):
        state = getattr(_b, attr, None)
        if state is not None:
            state.clear()
    yield
    for attr in ("_api_recovered_collector", "_quote_recovered_collector"):
        state = getattr(_b, attr, None)
        if state is not None:
            state.clear()


@pytest.fixture
def mock_write_log(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    """`system_logs.write_log` 모킹 — collector flush 가 write_log 경유."""
    mock = AsyncMock(return_value=None)
    import src.db.system_logs as _system_logs_mod

    monkeypatch.setattr(_system_logs_mod, "write_log", mock)
    from src.api import base as _b

    if hasattr(_b, "write_log"):
        monkeypatch.setattr(_b, "write_log", mock, raising=False)
    # base 모듈은 `_system_logs.write_log` 형태로 호출
    monkeypatch.setattr(_b._system_logs, "write_log", mock, raising=False)
    return mock


def _join_call_args(call) -> str:
    parts: list[str] = []
    for a in call.args:
        parts.append(str(a))
    for v in call.kwargs.values():
        parts.append(str(v))
    return " | ".join(parts)


# ---------------------------------------------------------------------------
# G-RC1: 5분 윈도우 내 메인 5회 → 1행 summary (5→1 = 80% 감소)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_g_rc1_5min_window_5_recovered_emits_one_summary_row(mock_write_log):
    """G-RC1: 메인 collector 5회 record + 1회 flush → `[api_retry_recovered_summary]`
    1행 write_log + total=5 + window=300s.

    5→1 = 80% 감소 (사이클 74 dup 6.68x→2.0x 효과 답습).
    """
    from src.api import base as _b

    record = getattr(_b, "_record_api_recovered", None)
    flush = getattr(_b, "_flush_api_recovered_collector", None)
    assert record is not None, (
        "사이클 76 G-RC1: `_record_api_recovered` 헬퍼 미존재 — Green 발주 대상"
    )
    assert flush is not None, (
        "사이클 76 G-RC1: `_flush_api_recovered_collector` 헬퍼 미존재 — Green 발주 대상"
    )

    path = "/uapi/domestic-stock/v1/trading/order-cash"
    for _ in range(5):
        record(path)

    await flush()

    summary_calls = [
        c for c in mock_write_log.await_args_list
        if "[api_retry_recovered_summary]" in _join_call_args(c)
    ]
    assert len(summary_calls) == 1, (
        f"G-RC1: `[api_retry_recovered_summary]` 1행 emit 의무 "
        f"— actual={len(summary_calls)} (5→1 = 80% 감소 위반)"
    )

    joined = _join_call_args(summary_calls[0])
    assert "total=5" in joined, f"G-RC1: total=5 누락 — actual: {joined}"
    assert "window=300s" in joined, f"G-RC1: window=300s 누락 — actual: {joined}"


# ---------------------------------------------------------------------------
# G-RC2: path 별 by_path 통계 정확 (`_api_recovered_collector: dict[path, count]`)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_g_rc2_by_path_aggregation_accurate(mock_write_log):
    """G-RC2: 메인 collector path 별 통계 정확 — by_path={path_a:3, path_b:2}.

    `_api_recovered_collector` state 검증 + flush summary 메시지에 by_path 포함.
    """
    from src.api import base as _b

    record = getattr(_b, "_record_api_recovered", None)
    flush = getattr(_b, "_flush_api_recovered_collector", None)
    assert record is not None and flush is not None, (
        "사이클 76 G-RC2: collector 헬퍼 미존재 — Green 발주 대상"
    )

    path_a = "/uapi/domestic-stock/v1/trading/order-cash"
    path_b = "/uapi/domestic-stock/v1/trading/inquire-balance"

    for _ in range(3):
        record(path_a)
    for _ in range(2):
        record(path_b)

    # state 검증 (flush 전)
    state = getattr(_b, "_api_recovered_collector", None)
    assert state is not None, (
        "사이클 76 G-RC2: `_api_recovered_collector` 모듈 변수 미존재"
    )
    assert state.get(path_a) == 3, (
        f"G-RC2: path_a count=3 의무, got {state.get(path_a)}"
    )
    assert state.get(path_b) == 2, (
        f"G-RC2: path_b count=2 의무, got {state.get(path_b)}"
    )

    await flush()

    summary_calls = [
        c for c in mock_write_log.await_args_list
        if "[api_retry_recovered_summary]" in _join_call_args(c)
    ]
    assert len(summary_calls) == 1, "1행 summary 의무"
    joined = _join_call_args(summary_calls[0])
    assert "total=5" in joined, f"G-RC2: total=5 누락 — actual: {joined}"
    # by_path 항목 (정렬 무관, 두 path 모두 포함)
    assert path_a in joined and "3" in joined, (
        f"G-RC2: path_a by_path 누락 — actual: {joined}"
    )
    assert path_b in joined and "2" in joined, (
        f"G-RC2: path_b by_path 누락 — actual: {joined}"
    )

    # flush 후 state clear
    state_after = getattr(_b, "_api_recovered_collector", {})
    assert len(state_after) == 0, (
        f"G-RC2: flush 후 collector clear 의무, got {len(state_after)} 엔트리"
    )


# ---------------------------------------------------------------------------
# G-RC3: 빈 윈도우 (count=0) → emit 0 (Q2)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_g_rc3_empty_window_skips_emit(mock_write_log):
    """G-RC3: collector 가 비어 있을 때 flush → write_log 호출 0건 (Q2 사용자 결정).

    운영 매 5분 주기 호출 시 무의미한 빈 행 차단.
    """
    from src.api import base as _b

    flush = getattr(_b, "_flush_api_recovered_collector", None)
    assert flush is not None, (
        "사이클 76 G-RC3: `_flush_api_recovered_collector` 헬퍼 미존재 — Green 발주 대상"
    )

    # collector 비어 있는 상태에서 flush
    await flush()

    summary_calls = [
        c for c in mock_write_log.await_args_list
        if "[api_retry_recovered_summary]" in _join_call_args(c)
    ]
    assert len(summary_calls) == 0, (
        f"G-RC3 (Q2): 빈 윈도우 (count=0) 시 emit 0 의무 "
        f"— actual={len(summary_calls)} 행 emit (불필요 로그)"
    )


# ---------------------------------------------------------------------------
# G-RC4: 메인 + 풀 collector 분리 (Q4) — 각각 별도 state + flush
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_g_rc4_main_and_quote_collectors_separated(mock_write_log):
    """G-RC4 (Q4): 메인 record 가 풀 state 침범 금지 + 풀 record 가 메인 state 침범 금지.

    각각 별도 flush 헬퍼 — `_flush_api_recovered_collector` /
    `_flush_quote_recovered_collector`.
    """
    from src.api import base as _b

    record_main = getattr(_b, "_record_api_recovered", None)
    record_quote = getattr(_b, "_record_quote_recovered", None)
    flush_main = getattr(_b, "_flush_api_recovered_collector", None)
    flush_quote = getattr(_b, "_flush_quote_recovered_collector", None)

    assert record_main is not None, "메인 record 헬퍼 미존재"
    assert record_quote is not None, (
        "사이클 76 G-RC4: `_record_quote_recovered` 헬퍼 미존재 — Q4 분리 의무"
    )
    assert flush_main is not None, "메인 flush 헬퍼 미존재"
    assert flush_quote is not None, (
        "사이클 76 G-RC4: `_flush_quote_recovered_collector` 헬퍼 미존재 — Q4 분리 의무"
    )

    # 메인 3건 + 풀 2건
    path_main = "/uapi/domestic-stock/v1/trading/order-cash"
    path_quote = "/uapi/domestic-stock/v1/quotations/inquire-price"
    for _ in range(3):
        record_main(path_main)
    for _ in range(2):
        record_quote(path_quote)

    main_state = getattr(_b, "_api_recovered_collector", {})
    quote_state = getattr(_b, "_quote_recovered_collector", {})

    # Q4 — state 분리 의무
    assert main_state.get(path_main) == 3, (
        f"G-RC4: 메인 state count=3 의무, got {main_state.get(path_main)}"
    )
    assert path_quote not in main_state, (
        f"G-RC4 (Q4): 풀 path 가 메인 state 침범 금지 — keys={list(main_state.keys())}"
    )
    assert quote_state.get(path_quote) == 2, (
        f"G-RC4: 풀 state count=2 의무, got {quote_state.get(path_quote)}"
    )
    assert path_main not in quote_state, (
        f"G-RC4 (Q4): 메인 path 가 풀 state 침범 금지 — keys={list(quote_state.keys())}"
    )

    # flush 각각 1행 (총 2행)
    await flush_main()
    await flush_quote()

    summary_calls = [
        c for c in mock_write_log.await_args_list
        if "[api_retry_recovered_summary]" in _join_call_args(c)
    ]
    assert len(summary_calls) == 2, (
        f"G-RC4: 메인 + 풀 각각 1행 = 총 2행 의무 — actual={len(summary_calls)}"
    )

    # 각 행은 별도 total 카운트 (3 / 2)
    totals = sorted(
        int(s.split("total=")[1].split()[0])
        for s in (_join_call_args(c) for c in summary_calls)
        if "total=" in s
    )
    assert totals == [2, 3], (
        f"G-RC4: 메인 total=3 + 풀 total=2 분리 의무 — actual totals={totals}"
    )
