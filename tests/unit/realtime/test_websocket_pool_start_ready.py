"""사이클 13-H Red — ``WebsocketPool.start()`` 보조 first-ready await 결함 가드.

진단 (`_workspace/cycle13h_pool_start_race_spec.md` §2-1 / §4 Patch 1):

운영 환경 (2026-05-19 09:15:42 KST) 에서 보조 시세 세션 connect 가 19초 지연돼
``pool.start()`` 가 fire-and-forget 으로 즉시 return — 직후 25 종목 subscribe 가
``_available_quotes()`` 에서 ``_ws is None`` 가드로 빈 list 받음 → 메인 fallback
고착. 메인 25 부착 → KIS throttle stale 23 (HIGH 보유 1 + dummy 1 만 fresh).

Patch 1 (§4) 핵심: ``pool.start()`` 가 보조 세션 ``_ws`` 가 적어도 1개 ready 될
때까지 timeout (7s 기본) 까지 await. Timeout 초과 시 WARNING + return → 기존
메인 fallback 흐름 보존 (회귀 0).

본 파일은 §5 Q-1/Q-2/Q-3/Q-4/Q-5 5종 시나리오를 Red 로 고정한다.

기대 결과 (현재 코드 기준):
- Q-1 정상 first-ready 50ms → FAIL (fire-and-forget 으로 _ws is None 유지)
- Q-2 timeout 7s 초과 → FAIL (timeout 분기 자체 없음)
- Q-3 보조 0개 → PASS (line 117-119 graceful 분기로 이미 처리, 회귀 가드)
- Q-4 _started=True 멱등 → PASS (line 105-107 idempotent 분기, 회귀 가드)
- Q-5 N=3 중 1개만 ready → FAIL (first-ready break 로직 자체 없음)

Patch 1 적용 후 Q-1/Q-2/Q-5 도 PASS (5건 모두 Green).

Mock 전략 (명세 §8.1):
- ``kis_quote_accounts.list_accounts`` patch — 보조 계좌 리스트 길이 제어
- ``get_token_manager`` patch — AsyncMock (토큰 발급 race 격리)
- ``KisWebSocket.__init__`` + ``connect`` patch — 실제 KIS WS 연결 시도 금지.
  ``_ws`` 속성을 N초 후 set 하는 fake coroutine 으로 시뮬레이션.
- ``POOL_START_READY_TIMEOUT_SECS`` monkeypatch — 7s → 1s 가속 (테스트 실행 시간 단축).
  Patch 1 미적용 시 module-level 상수 자체 부재 → monkeypatch attempt 가 곧
  Red 시그널의 일부 (명세 §8.1 backend-dev 분배 시 module-level 선언 명시).

안전 가드 (CLAUDE.md):
- 체결통보 (H0STCNI0/H0STCNI9) 분기 손대지 않음 — TICK 시뮬만
- ``_subscriptions`` set 직접 수정 금지 — mock 인스턴스 attr 만 조작
- 운영 싱글톤 (``kis_ws_pool``) 사용 금지 — 새 ``WebsocketPool()`` 인스턴스만
- ``_quote_connect_tasks`` 잔존 task 는 테스트 종료 시 fixture 에서 cancel
"""

from __future__ import annotations

import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Fixtures — mock account + KisWebSocket fake
# ---------------------------------------------------------------------------
def _make_account(label: str):
    """KisQuoteAccount 시뮬 — ``getattr(acct, 'label', None)`` 만 사용됨."""
    acct = MagicMock()
    acct.label = label
    return acct


def _fake_connect_factory(delay_secs: float):
    """``KisWebSocket.connect`` 의 fake coroutine 생성기.

    delay_secs 후 ``self._ws`` 를 set 한 뒤 무한 sleep (실제 KIS connect 는
    재연결 + heartbeat 루프라 never-complete) — Patch 1 의 `_ws` 폴링이
    "ready" 시그널로 _ws set 시점을 잡는 동작 시뮬.

    Returns:
        async function — KisWebSocket 인스턴스에 bound method 로 patch 가능.
    """

    async def _fake_connect(self, dispatch_message):
        # delay_secs 후 _ws set (KIS 핸드쉐이크 + AES iv/key 수신 완료 시뮬)
        if delay_secs > 0:
            await asyncio.sleep(delay_secs)
        self._ws = MagicMock()  # truthy + getattr(_ws, ...) 호환
        # 실제 코드처럼 무한 대기 — task 자체는 never-complete
        try:
            await asyncio.sleep(3600)
        except asyncio.CancelledError:
            return

    return _fake_connect


async def _drain_tasks(pool):
    """fixture teardown — 잔존 connect task 안전 cancel.

    ``stop()`` 대신 task 만 정리해 Q-4 멱등 검증 등 ``_started`` 상태 보존.
    """
    for task in pool._quote_connect_tasks:
        if not task.done():
            task.cancel()
    if pool._quote_connect_tasks:
        await asyncio.gather(*pool._quote_connect_tasks, return_exceptions=True)


def _patch_timeout(monkeypatch, value: float = 1.0):
    """``POOL_START_READY_TIMEOUT_SECS`` 가속 monkeypatch.

    Patch 1 적용 후 module-level 상수가 추가되면 7s → ``value`` 로 가속.
    상수 부재 (Red 시점) 시 setattr 은 성공하지만 ``start()`` 본문이 local
    상수를 사용하므로 무효 — 그 경우 fake connect delay 만으로 검증 진행.
    """
    import src.realtime.websocket_pool as mod
    monkeypatch.setattr(mod, "POOL_START_READY_TIMEOUT_SECS", value, raising=False)
    monkeypatch.setattr(mod, "POOL_START_READY_POLL_INTERVAL_SECS", 0.05, raising=False)


# ---------------------------------------------------------------------------
# Q-1 (Red) — 보조 1개, connect 50ms 후 _ws set → first-ready 도달 + INFO 로그
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_pool_start_awaits_first_ready_when_quote_connects_quickly(
    monkeypatch, caplog
):
    """Red: ``pool.start()`` 종료 시점에 보조 ``_ws is not None`` + INFO log.

    시나리오 (Q-1):
    1. 보조 1개 활성, ``KisWebSocket.connect`` 가 50ms 후 ``_ws`` set
    2. ``await pool.start(dispatch=mock)`` 호출
    3. assert: 함수 반환 시점에 ``pool._quotes[0]._ws is not None`` (first-ready 도달)
    4. assert: ``[pool_start_ready]`` prefix INFO 로그 1회 출력

    현재 코드 (fire-and-forget) → FAIL: ``connect`` task 발화만 하고 즉시 return
    이라 ``_ws`` 는 None 인 채 함수 반환. ``[pool_start_ready]`` 로그도 없음.
    """
    from src.realtime.websocket_pool import WebsocketPool

    _patch_timeout(monkeypatch, value=2.0)  # 50ms ready < 2s timeout 충분

    pool = WebsocketPool()

    accounts = [_make_account("quote-1")]
    fake_manager = AsyncMock()
    dispatch = AsyncMock()

    with patch(
        "src.db.kis_quote_accounts.list_accounts", new=AsyncMock(return_value=accounts)
    ), patch(
        "src.auth.token.get_token_manager", new=AsyncMock(return_value=fake_manager)
    ), patch(
        "src.realtime.websocket_pool.KisWebSocket.connect",
        new=_fake_connect_factory(delay_secs=0.05),
    ):
        with caplog.at_level(logging.INFO, logger="src.realtime.websocket_pool"):
            await pool.start(dispatch_message=dispatch)

        try:
            assert len(pool._quotes) == 1, (
                f"보조 1개 등록 기대, 실제: {len(pool._quotes)}"
            )
            assert getattr(pool._quotes[0], "_ws", None) is not None, (
                "Red: pool.start() 반환 시점에 보조 _ws 가 set 돼야 한다 "
                "(first-ready await). 현재 fire-and-forget 이라 None 유지."
            )
            ready_logs = [
                rec for rec in caplog.records
                if "[pool_start_ready]" in rec.getMessage()
            ]
            assert len(ready_logs) == 1, (
                f"Red: [pool_start_ready] INFO 1행 출력 기대. 실제: {len(ready_logs)}"
            )
        finally:
            await _drain_tasks(pool)


# ---------------------------------------------------------------------------
# Q-2 (Red) — 보조 connect 가 timeout 초과 → WARNING + graceful return
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_pool_start_logs_timeout_warning_when_quote_never_ready(
    monkeypatch, caplog
):
    """Red: 보조 connect 가 timeout 초과 → WARNING + 예외 없이 return.

    시나리오 (Q-2):
    1. 보조 1개 활성, ``connect`` mock 이 timeout 초과 (3s sleep > 1s timeout)
    2. ``await pool.start(...)`` 호출
    3. assert: timeout 후 return + ``[pool_start_ready_timeout]`` WARNING 1행
    4. assert: ``pool.start()`` 가 예외 raise 안 함 (graceful)
    5. assert: 메인 fallback 흐름 보존 — ``_quotes`` 는 등록되어 있음 (이후 connect 완료 시 자연 회복)

    현재 코드 → FAIL: timeout 분기 자체가 없어 ``pool.start()`` 가 즉시 return
    + WARNING 로그 0건.
    """
    from src.realtime.websocket_pool import WebsocketPool

    _patch_timeout(monkeypatch, value=0.5)  # 0.5s timeout < 3s connect delay

    pool = WebsocketPool()

    accounts = [_make_account("quote-1")]
    fake_manager = AsyncMock()
    dispatch = AsyncMock()

    with patch(
        "src.db.kis_quote_accounts.list_accounts", new=AsyncMock(return_value=accounts)
    ), patch(
        "src.auth.token.get_token_manager", new=AsyncMock(return_value=fake_manager)
    ), patch(
        "src.realtime.websocket_pool.KisWebSocket.connect",
        new=_fake_connect_factory(delay_secs=3.0),  # > timeout
    ):
        with caplog.at_level(logging.WARNING, logger="src.realtime.websocket_pool"):
            # 예외 없이 return — graceful timeout
            await pool.start(dispatch_message=dispatch)

        try:
            timeout_logs = [
                rec for rec in caplog.records
                if "[pool_start_ready_timeout]" in rec.getMessage()
            ]
            assert len(timeout_logs) == 1, (
                "Red: [pool_start_ready_timeout] WARNING 1행 출력 기대. "
                f"실제: {len(timeout_logs)}"
            )
            assert timeout_logs[0].levelno == logging.WARNING, (
                "Red: timeout 로그는 WARNING 레벨이어야 함 — "
                "운영자 알림 트리거 호환 (Slack/SMS 임계)"
            )
            assert len(pool._quotes) == 1, (
                "메인 fallback 보존: 보조 세션 등록 자체는 보존 — "
                "이후 connect 완료 시 다음 _scan_loop 5분 주기에서 자연 회복"
            )
        finally:
            await _drain_tasks(pool)


# ---------------------------------------------------------------------------
# Q-3 (의도된 PASS, 회귀 가드) — 보조 0개 → ready 분기 진입 안 함
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_pool_start_skips_ready_branch_when_no_quote_accounts(
    monkeypatch, caplog
):
    """정상 회귀 가드 (의도된 PASS): 보조 0개 DB → ready 분기 진입 안 함.

    시나리오 (Q-3):
    1. ``list_accounts(active_only=True)`` mock 이 빈 list 반환
    2. ``await pool.start(...)`` 호출
    3. assert: ``[pool_start_ready]`` / ``[pool_start_ready_timeout]`` 로그 0건
    4. assert: 즉시 return + ``_started=True``
    5. assert: ``[pool_start] 보조 시세 계좌 0개`` INFO 1행 출력 (기존 line 117-119)

    현재 코드 → PASS — 보조 0개는 ``self._quotes`` 가 빈 list 라 ready 분기
    if 조건 (``self._quotes and dispatch_message is not None``) 으로 skip.
    Patch 1 적용 후에도 동일 동작 보장.
    """
    from src.realtime.websocket_pool import WebsocketPool

    _patch_timeout(monkeypatch, value=1.0)

    pool = WebsocketPool()
    dispatch = AsyncMock()

    with patch(
        "src.db.kis_quote_accounts.list_accounts", new=AsyncMock(return_value=[])
    ):
        with caplog.at_level(logging.DEBUG, logger="src.realtime.websocket_pool"):
            await pool.start(dispatch_message=dispatch)

        try:
            ready_logs = [
                rec for rec in caplog.records
                if "[pool_start_ready]" in rec.getMessage()
                or "[pool_start_ready_timeout]" in rec.getMessage()
            ]
            assert len(ready_logs) == 0, (
                "보조 0개 시 ready 분기 진입 0건 — Patch 1 if 조건 보존. "
                f"실제: {[r.getMessage() for r in ready_logs]}"
            )
            assert pool._started is True, "보조 0개 graceful 분기에서도 _started=True"
            assert pool._quotes == [], "보조 0개 → _quotes 빈 list 유지"
            zero_acct_logs = [
                rec for rec in caplog.records
                if "보조 시세 계좌 0개" in rec.getMessage()
            ]
            assert len(zero_acct_logs) == 1, (
                "기존 line 117-119 [pool_start] 보조 0개 INFO 1행 보존"
            )
        finally:
            await _drain_tasks(pool)


# ---------------------------------------------------------------------------
# Q-4 (의도된 PASS, 회귀 가드) — _started=True 멱등 noop
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_pool_start_is_idempotent_noop_when_already_started(monkeypatch, caplog):
    """정상 회귀 가드 (의도된 PASS): ``_started=True`` 사전 세팅 시 즉시 noop.

    시나리오 (Q-4):
    1. ``pool._started = True`` 사전 설정 후 ``pool.start(...)`` 호출
    2. assert: 즉시 return + ``list_accounts`` 호출 0건
    3. assert: ``[pool_start_ready]`` / ``[pool_start_ready_timeout]`` 로그 0건

    현재 코드 → PASS — line 105-107 의 멱등 가드 ``if self._started: return``.
    Patch 1 적용 후에도 ready 분기는 멱등 noop 이후의 코드라 도달 안 함.
    회귀 가드: 13-G 의 _started 멱등 보존 확인.
    """
    from src.realtime.websocket_pool import WebsocketPool

    _patch_timeout(monkeypatch, value=1.0)

    pool = WebsocketPool()
    pool._started = True  # 사전 세팅 — 이미 start 된 상태 시뮬

    list_accounts_mock = AsyncMock(return_value=[_make_account("quote-1")])
    dispatch = AsyncMock()

    with patch("src.db.kis_quote_accounts.list_accounts", new=list_accounts_mock):
        with caplog.at_level(logging.DEBUG, logger="src.realtime.websocket_pool"):
            await pool.start(dispatch_message=dispatch)

        try:
            assert list_accounts_mock.await_count == 0, (
                "멱등 noop: 이미 started 면 list_accounts 호출 0회. "
                f"실제: {list_accounts_mock.await_count}"
            )
            ready_logs = [
                rec for rec in caplog.records
                if "[pool_start_ready]" in rec.getMessage()
                or "[pool_start_ready_timeout]" in rec.getMessage()
            ]
            assert len(ready_logs) == 0, (
                "멱등 noop 시 ready 분기 진입 0건 — Patch 1 if 조건이 "
                "_started 가드 *뒤* 에 있어야 함"
            )
            assert pool._quotes == [], "멱등 noop 시 _quotes 변동 없음"
        finally:
            await _drain_tasks(pool)


# ---------------------------------------------------------------------------
# Q-5 (Red) — 보조 N=3 중 1개만 ready → 즉시 break + INFO ready=1/3
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_pool_start_breaks_on_first_ready_when_multiple_quotes_register(
    monkeypatch, caplog
):
    """Red: 보조 3개 중 1개만 ready → 첫 ready 후 break (timeout 대기 안 함).

    시나리오 (Q-5):
    1. 보조 3개 활성. ``connect`` mock — 라벨별 delay 분기:
       - quote-1: 50ms 후 _ws set
       - quote-2: 30s sleep (timeout 초과)
       - quote-3: 30s sleep (timeout 초과)
    2. ``await pool.start(...)`` 호출
    3. assert: 첫 ready 후 ~빠르게 return (timeout 1s 까지 대기 안 함)
    4. assert: ``[pool_start_ready]`` INFO 1행 + 메시지에 ``ready=1/3`` 또는
       동등한 카운트 표현 포함
    5. assert: ``[pool_start_ready_timeout]`` WARNING 0건 (timeout 안 도달)

    현재 코드 → FAIL: first-ready 로직 자체 없음 → ready 로그 0건.
    Patch 1 적용 후 break 로 quote-1 ready 즉시 종료.

    측정: 함수 시작~종료 elapsed wall-clock < 0.5s 검증 (50ms ready << 1s timeout).
    """
    from src.realtime.websocket_pool import WebsocketPool

    _patch_timeout(monkeypatch, value=1.0)  # timeout 1s — 30s sleep 가 초과

    pool = WebsocketPool()

    accounts = [
        _make_account("quote-1"),
        _make_account("quote-2"),
        _make_account("quote-3"),
    ]
    fake_manager = AsyncMock()
    dispatch = AsyncMock()

    # quote-1 은 빠르게 ready, 나머지는 timeout 초과 sleep
    # KisWebSocket 인스턴스를 라벨별로 식별하기 어렵기 때문에 호출 순서로 분기.
    call_idx = {"n": 0}

    async def _fake_connect_per_call(self, dispatch_message):
        idx = call_idx["n"]
        call_idx["n"] += 1
        # 첫 번째 인스턴스만 50ms 후 ready, 나머지 두 개는 30s sleep
        if idx == 0:
            await asyncio.sleep(0.05)
            self._ws = MagicMock()
        else:
            self._ws = None  # 명시 — 미리 ready 처리 차단
        try:
            await asyncio.sleep(30)
        except asyncio.CancelledError:
            return

    with patch(
        "src.db.kis_quote_accounts.list_accounts", new=AsyncMock(return_value=accounts)
    ), patch(
        "src.auth.token.get_token_manager", new=AsyncMock(return_value=fake_manager)
    ), patch(
        "src.realtime.websocket_pool.KisWebSocket.connect",
        new=_fake_connect_per_call,
    ):
        with caplog.at_level(logging.INFO, logger="src.realtime.websocket_pool"):
            start_t = asyncio.get_event_loop().time()
            await pool.start(dispatch_message=dispatch)
            elapsed = asyncio.get_event_loop().time() - start_t

        try:
            # 첫 ready (~50ms) 후 즉시 break — 1s timeout 까지 대기 안 함
            assert elapsed < 0.5, (
                f"Red: first-ready 즉시 break 기대. 실제 elapsed={elapsed:.3f}s "
                f"— timeout 까지 대기 중인 것으로 의심됨"
            )
            assert len(pool._quotes) == 3, (
                f"보조 3개 등록 기대. 실제: {len(pool._quotes)}"
            )

            ready_logs = [
                rec for rec in caplog.records
                if "[pool_start_ready]" in rec.getMessage()
            ]
            assert len(ready_logs) == 1, (
                f"Red: [pool_start_ready] INFO 1행 기대. 실제: {len(ready_logs)}"
            )
            # ready=1/3 또는 동등 카운트 표현
            msg = ready_logs[0].getMessage()
            assert "1" in msg and "3" in msg, (
                f"Red: ready=1/3 형식 카운트 포함 기대. 실제 msg={msg!r}"
            )

            timeout_logs = [
                rec for rec in caplog.records
                if "[pool_start_ready_timeout]" in rec.getMessage()
            ]
            assert len(timeout_logs) == 0, (
                f"timeout 안 도달 — WARNING 0건 기대. 실제: {len(timeout_logs)}"
            )
        finally:
            await _drain_tasks(pool)
