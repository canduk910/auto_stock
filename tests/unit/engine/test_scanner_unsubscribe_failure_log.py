"""사이클 13-E-1 Red — scanner.unsubscribe_all 실패 카운터 + 조건부 로그 레벨 검증.

명세 (`_workspace/cycle13e_shutdown_pool_cleanup_spec.md` §4 Patch 1, §8 Test G):

PR #12 Copilot 리뷰 ③ — `src/engine/scanner.py:563` 위치에서 발견된 운영 가시성 결함:
현재 ``unsubscribe_all()`` 은 ``pool.unsubscribe_all()`` / ``kis_ws.unsubscribe()`` 의
예외를 swallow 한 뒤 *항상* INFO "모든 시세 구독 해제 완료" 를 출력 → 실제 일부 실패해도
운영자는 "성공" 으로 오해.

기대 동작 (Green Patch 1):
- 실패 카운터: ``pool_failures`` / ``main_failures`` 집계
- ``total_failures > 0`` → WARNING ``[scanner_unsubscribe_all] 일부 구독 해제 실패 —
  pool=N, main=M`` 포맷으로 격상 출력. INFO "완료" 는 출력 안 됨
- ``total_failures == 0`` → INFO "모든 시세 구독 해제 완료" 만 출력. WARNING 없음

Red 단계:
- 현재 코드 (`scanner.py:549-563`) 는 실패 여부와 무관하게 INFO "완료" 출력 →
  Test G-2 / G-3 의 "WARNING present + INFO absent" assert 가 fail.

안전 가드 (CLAUDE.md):
- 체결통보 분기 (H0STCNI0/H0STCNI9) 무관 — TICK_TR_ID 만 검증
- ``_subscriptions`` set 은 mock 위에서만 조작
"""

from __future__ import annotations

import logging
from unittest.mock import AsyncMock, MagicMock

import pytest

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# 헬퍼 — 가짜 메인 KisWebSocket 세션 (TICK 구독 2건 기본)
# ---------------------------------------------------------------------------
def _fake_main_ws(subs: set[tuple[str, str]]) -> MagicMock:
    """unsubscribe 가 ``_subscriptions`` discard 하는 mock 세션."""
    ws = MagicMock()
    ws._subscriptions = set(subs)
    ws._subscriptions_acked = set()

    async def _unsub(tr_id: str, tr_key: str) -> None:
        ws._subscriptions.discard((tr_id, tr_key))

    ws.unsubscribe = AsyncMock(side_effect=_unsub)
    return ws


# ---------------------------------------------------------------------------
# Test G-1 — 무실패: INFO "완료" 출력 + WARNING 없음
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_unsubscribe_all_no_failures_emits_info_completion(monkeypatch, caplog):
    """Red: pool + main 양쪽 모두 정상이면 INFO "모든 시세 구독 해제 완료" 1회 +
    WARNING 0회 — 현재 코드는 WARNING 없는 상태로 통과할 가능성 있지만, Green Patch 1
    적용 후 카운터 분기로도 동일 동작을 보장해야 한다.

    명세 §5 시나리오 I-1 (무실패):
    - pool.unsubscribe_all() 정상 + kis_ws.unsubscribe() 정상
    - 검증: INFO "모든 시세 구독 해제 완료" 1회 + WARNING 없음

    회귀 가드: Green Patch 1 후에도 무실패 시에는 INFO 가 출력되어야 한다.
    Red 단계 검증 핵심은 G-2/G-3 — 본 테스트는 회귀 가드 역할.
    """
    from src.engine import scanner

    TICK = scanner.TICK_TR_ID

    main_ws = _fake_main_ws({(TICK, "005930"), (TICK, "000660")})

    fake_pool = MagicMock()
    fake_pool.unsubscribe_all = AsyncMock(return_value=None)

    monkeypatch.setattr(scanner, "kis_ws", main_ws, raising=True)
    monkeypatch.setattr(scanner, "kis_ws_pool", fake_pool, raising=True)

    caplog.set_level(logging.DEBUG, logger="src.engine.scanner")

    await scanner.unsubscribe_all()

    info_completion_records = [
        r for r in caplog.records
        if r.name == "src.engine.scanner"
        and r.levelno == logging.INFO
        and "모든 시세 구독 해제 완료" in r.getMessage()
    ]
    warning_records = [
        r for r in caplog.records
        if r.name == "src.engine.scanner" and r.levelno == logging.WARNING
    ]

    assert len(info_completion_records) == 1, (
        f"무실패 시 INFO '모든 시세 구독 해제 완료' 1회 출력 기대. "
        f"실제: {len(info_completion_records)}회. 전체 INFO 메시지: "
        f"{[r.getMessage() for r in caplog.records if r.levelno == logging.INFO]}"
    )
    assert len(warning_records) == 0, (
        f"무실패 시 WARNING 미출력 기대. 실제 WARNING: "
        f"{[r.getMessage() for r in warning_records]}"
    )


# ---------------------------------------------------------------------------
# Test G-2 — pool 실패: WARNING "pool=1, main=0" + INFO "완료" 미출력
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_unsubscribe_all_pool_failure_warns_and_skips_info(monkeypatch, caplog):
    """Red: ``pool.unsubscribe_all()`` 이 예외 raise 시 WARNING
    ``[scanner_unsubscribe_all] 일부 구독 해제 실패 — pool=1, main=0`` 출력 +
    INFO "모든 시세 구독 해제 완료" 는 출력되면 안 된다 — 현재 코드에서 fail 해야 함.

    명세 §5 시나리오 I-2 + §4 Patch 1:
    > total_failures > 0 분기로 WARNING 포맷 (`pool=N, main=M`) 출력 + 무실패 시에만
    > INFO "완료" 출력.

    Red 상태: 현재 `scanner.py:563` 의 INFO "모든 시세 구독 해제 완료" 가 무조건 출력 →
    본 테스트의 "INFO absent" assert 가 fail.
    """
    from src.engine import scanner

    TICK = scanner.TICK_TR_ID

    main_ws = _fake_main_ws(set())  # 메인 잔여 0 — 메인 실패 없음

    fake_pool = MagicMock()
    fake_pool.unsubscribe_all = AsyncMock(side_effect=RuntimeError("풀 정리 실패 시뮬레이션"))

    monkeypatch.setattr(scanner, "kis_ws", main_ws, raising=True)
    monkeypatch.setattr(scanner, "kis_ws_pool", fake_pool, raising=True)

    caplog.set_level(logging.DEBUG, logger="src.engine.scanner")

    await scanner.unsubscribe_all()

    # WARNING `[scanner_unsubscribe_all] ... pool=1, main=0` 출력 검증
    warning_summary_records = [
        r for r in caplog.records
        if r.name == "src.engine.scanner"
        and r.levelno == logging.WARNING
        and "[scanner_unsubscribe_all]" in r.getMessage()
        and "일부 구독 해제 실패" in r.getMessage()
        and "pool=1" in r.getMessage()
        and "main=0" in r.getMessage()
    ]
    assert len(warning_summary_records) >= 1, (
        f"pool 실패 시 WARNING 요약 '[scanner_unsubscribe_all] 일부 구독 해제 실패 — "
        f"pool=1, main=0' 출력 누락. 전체 WARNING 메시지: "
        f"{[r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]}"
    )

    # INFO "모든 시세 구독 해제 완료" 는 출력되면 안 됨
    info_completion_records = [
        r for r in caplog.records
        if r.name == "src.engine.scanner"
        and r.levelno == logging.INFO
        and "모든 시세 구독 해제 완료" in r.getMessage()
    ]
    assert len(info_completion_records) == 0, (
        f"pool 실패 시 INFO '모든 시세 구독 해제 완료' 출력되면 안 됨 — 운영자 오해 차단. "
        f"실제 INFO 출력: {[r.getMessage() for r in info_completion_records]}"
    )


# ---------------------------------------------------------------------------
# Test G-3 — main 잔여 일부 실패: WARNING "pool=0, main=N" + INFO 미출력
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_unsubscribe_all_main_failure_warns_with_main_count(monkeypatch, caplog):
    """Red: ``kis_ws.unsubscribe`` 가 일부 ticker 에 대해 예외 raise 시
    WARNING 격상 + 정확한 main 실패 카운트 (``pool=0, main=N``) 출력 + INFO 미출력 —
    현재 코드에서 fail 해야 함.

    명세 §5 시나리오 I-3 + §4 Patch 1:
    > 메인 unsubscribe 1건 예외 → WARNING "일부 구독 해제 실패 — pool=0, main=1" +
    > INFO 미출력.

    시뮬레이션: 메인 _subscriptions 2건 중 1건은 unsubscribe 성공, 나머지 1건은 RuntimeError.

    Red 상태: 현재 코드는 main_failures 카운트 자체가 없고 INFO 가 무조건 출력 → fail.
    """
    from src.engine import scanner

    TICK = scanner.TICK_TR_ID

    fail_ticker = "005930"
    success_ticker = "000660"

    main_ws = MagicMock()
    main_ws._subscriptions = {(TICK, fail_ticker), (TICK, success_ticker)}
    main_ws._subscriptions_acked = set()

    async def _unsub_partial_fail(tr_id: str, tr_key: str) -> None:
        if tr_key == fail_ticker:
            raise RuntimeError(f"main 단건 해제 실패 시뮬레이션 — {tr_key}")
        main_ws._subscriptions.discard((tr_id, tr_key))

    main_ws.unsubscribe = AsyncMock(side_effect=_unsub_partial_fail)

    fake_pool = MagicMock()
    fake_pool.unsubscribe_all = AsyncMock(return_value=None)  # 풀 정상

    monkeypatch.setattr(scanner, "kis_ws", main_ws, raising=True)
    monkeypatch.setattr(scanner, "kis_ws_pool", fake_pool, raising=True)

    caplog.set_level(logging.DEBUG, logger="src.engine.scanner")

    await scanner.unsubscribe_all()

    # WARNING `pool=0, main=1` 검증
    warning_summary_records = [
        r for r in caplog.records
        if r.name == "src.engine.scanner"
        and r.levelno == logging.WARNING
        and "[scanner_unsubscribe_all]" in r.getMessage()
        and "일부 구독 해제 실패" in r.getMessage()
        and "pool=0" in r.getMessage()
        and "main=1" in r.getMessage()
    ]
    assert len(warning_summary_records) >= 1, (
        f"main 1건 실패 시 WARNING 요약 '[scanner_unsubscribe_all] 일부 구독 해제 실패 — "
        f"pool=0, main=1' 출력 누락. 전체 WARNING 메시지: "
        f"{[r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]}"
    )

    # INFO "모든 시세 구독 해제 완료" 는 출력되면 안 됨 (1건이라도 실패 시)
    info_completion_records = [
        r for r in caplog.records
        if r.name == "src.engine.scanner"
        and r.levelno == logging.INFO
        and "모든 시세 구독 해제 완료" in r.getMessage()
    ]
    assert len(info_completion_records) == 0, (
        f"main 1건 실패 시 INFO '모든 시세 구독 해제 완료' 출력되면 안 됨. "
        f"실제 INFO 출력: {[r.getMessage() for r in info_completion_records]}"
    )
