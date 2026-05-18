# 사이클 13-E — 종료 시퀀스 풀 정리 누락 fix

**작성일**: 2026-05-18 (KST)
**작성자**: team-leader
**브랜치**: `claude/setup-codebase-mcp-cNc2f` (기존 부팅 훅 작업 연속)
**우선순위**: HIGH (자금 안전성 잠재 결함 — 24h 토큰 만료 후 보조 세션 silent death)

---

## 1. 현상

2026-05-18 20:29 KST (장 종료 후, settlement 20:10 한참 지난 시점) Dashboard
`KIS 시세 풀 (WebsocketPool)` 카드:

| 세션 | 연결 | 구독 | fresh | stale |
|------|------|------|-------|-------|
| main | **disconnected** | 0/41 | - | - |
| quote-1 | **connected** | 11/41 | 0 | 11 |

메인은 정상 종료됐지만 보조 세션이 11건 구독 + WebSocket 연결 유지된 채 잔존.

**리뷰 추가 발견 (PR #12, 2026-05-18)**: Copilot 봇이 3건 지적 — ① `start()` 예외 시
`finally` 가 메인 disconnect 도달 못함 (`scheduler.py:519`), ② 수동 `stop()` task cancel
목록에 `_swing_rest_poll_task` 누락 (`scheduler.py:621`), ③ scanner `unsubscribe_all()`
실패 swallow 후 항상 INFO 성공 로그 — 운영 가시성 오해 (`scanner.py:563`).
사이클 13-E-1 보강으로 §4 Patch 1/2/3 갱신.

---

## 2. 근본 원인 (코드 grep 확정)

### 원인 1 — `src/engine/scanner.py:549-554`

```python
async def unsubscribe_all() -> None:
    """모든 종목 구독을 해제한다."""
    for tr_id, tr_key in list(kis_ws._subscriptions):  # 메인 세션 _subscriptions 만 순회
        if tr_id == TICK_TR_ID:
            await kis_ws.unsubscribe(tr_id, tr_key)
```

`WebsocketPool.unsubscribe_all()` (`src/realtime/websocket_pool.py:325-340`) 는 풀 전체를 도는
별도 함수로 이미 구현되어 있는데 scanner 는 메인 세션만 직접 건드림. 보조 세션 `_ticker_to_session`
분배 추적이 정리되지 않음.

### 원인 2 — `src/engine/scheduler.py:485-492` (정상 종료 경로)

```python
self._reset_daily_state()

await kis_ws.disconnect()    # ← 메인만 disconnect
try:
    await ws_task
except asyncio.CancelledError:
    pass
# 여기에 `await kis_ws_pool.stop()` 호출 누락
```

### 원인 3 — `src/engine/scheduler.py:604-605` (수동 중지 `stop()`)

```python
await unsubscribe_all()
await kis_ws.disconnect()
await write_log("INFO", "매매 시스템 수동 중지")
# 여기에 `await kis_ws_pool.stop()` 호출 누락
```

`WebsocketPool.stop()` docstring 가 호출자 책임을 명시:

> "메인 세션은 호출자(scheduler) 책임으로 별도 disconnect — 본 메서드는 보조만 정리.
> 풀의 `_started` flag 재설정해 다음 `start()` 호출 시 재초기화."

호출자 (scheduler) 가 안 부르고 있음.

---

## 3. 트레이딩 안전성 평가

| 영역 | 영향 | 비고 |
|------|------|------|
| 체결통보 (H0STCNI0/H0STCNI9) | **영향 없음** | 메인 세션 강제. 메인은 정상 disconnect |
| 보유 종목 손절 (HIGH priority) | 운영 시간 외 영향 없음 | 다음 _boot 시 재구독 — HIGH 는 메인 절대 보장 |
| 보조 세션 (LOW: breakout/momentum/swing) | 잔존 구독 + WebSocket 연결 유지 | 스크린샷 증거 |
| **24h 토큰 만료 후 다음 _boot** | **잠재 결함 (자금 안전 영향)** | `_started` 멱등 가드 (`websocket_pool.py:105-107` "already started — noop") + 토큰 만료 → 보조 세션 silent 죽음 |
| 슬롯 회계 (`/api/realtime/subscriptions`) | 부정확한 fresh/stale | 카드가 증거 |

**최악 시나리오**: 보조 세션이 stale 한 상태로 다음날 _boot 진입 → `_started=True` 가드로
`pool.start()` noop → 보조 세션이 죽은 채 부활하지 못함 → 41 슬롯 (메인) 안에서만 운영 →
HIGH 우선순위 보장은 유지되지만 LOW (momentum/breakout/swing) drop 빈도 증가 → 매수 신호 누락.

체결통보·보유 손절은 무사하지만 **수익 기회 손실 + 운영 가시성 저하**.

---

## 4. fix 명세 (TDD Red→Green)

### Red (tdd-engineer 작성 단위 테스트)

#### Test A — `tests/unit/engine/test_scanner_unsubscribe_all_pool.py` (NEW)

`scanner.unsubscribe_all()` 호출 시 메인 + 모든 보조 세션의 구독이 비어야 함.

```
시나리오:
1. mock kis_ws_pool 에 메인 _subscriptions = {(TICK, "005930"), (TICK, "000660")}
2. quote-1 _subscriptions = {(TICK, "035420")} + _ticker_to_session = {"035420": quote-1}
3. await scanner.unsubscribe_all()
4. assert kis_ws._subscriptions == set()
5. assert quote-1._subscriptions == set()
6. assert kis_ws_pool._ticker_to_session == {}
```

호환 분기: 보조 0개일 때 메인 단독 해제도 정상 동작.

#### Test B — `tests/unit/engine/test_scheduler_pool_stop_on_shutdown.py` (NEW)

scheduler 종료 finally 시퀀스에서 `kis_ws.disconnect()` *와* `kis_ws_pool.stop()` 이
**둘 다** 호출돼야 함.

```
시나리오 1 (정상 종료):
- run() 진입 → _wait_until 패치로 즉시 종료 흐름 진입
- kis_ws.disconnect() 와 kis_ws_pool.stop() 호출 verify
- 둘 중 하나라도 호출 안 되면 fail

시나리오 2 (수동 중지 `stop()`):
- scheduler.stop() 호출
- kis_ws.disconnect() + kis_ws_pool.stop() 둘 다 호출 verify

시나리오 3 (보조 stop 예외 흡수):
- kis_ws_pool.stop() 이 RuntimeError → kis_ws.disconnect() 가 그 후에 호출돼야 함
- 또는 disconnect 가 먼저면 stop() 예외가 종료 흐름을 중단시키지 않아야 함
- write_log("INFO", "매매 시스템 종료") 가 도달 가능
```

#### Test C — `tests/unit/realtime/test_websocket_pool_stop_reset.py` (NEW 또는 기존 보강)

`WebsocketPool.stop()` 호출 후 `_started=False` 재설정 회귀 가드.

```
시나리오:
1. pool = WebsocketPool(...)
2. await pool.start()  # _started = True
3. await pool.stop()
4. assert pool._started is False
5. await pool.start()  # 멱등 noop 아니라 재초기화 발화 verify
```

기존 `test_websocket_pool.py:499` 의 `unsubscribe_all` 테스트와는 별개.

#### Test D — 회귀 가드 — `tests/unit/realtime/test_websocket_pool_stop_empty_quotes.py` (NEW)

보조 0개 (`kis_quote_accounts` 미등록) 상황에서 `pool.stop()` noop 정상 종료.

```
시나리오:
1. pool = WebsocketPool() ; await pool.start()  # 보조 0개
2. await pool.stop()  # 예외 없이 통과
3. assert pool._quotes == []
4. assert pool._started is False
```

### Green (backend-dev 최소 변경)

#### Patch 1 — `src/engine/scanner.py:549-563` (사이클 13-E-1 리뷰 ③ 반영)

```python
async def unsubscribe_all() -> None:
    """모든 종목 구독을 해제한다 (메인 + 보조 세션 전체)."""
    # 사이클 13-E-1 리뷰 ③ — 실패 카운터 + 조건부 로그 레벨.
    # 일부 구독 해제 실패 시 INFO "완료" 로그가 운영자에게 잘못된 신호를 보내지 않도록
    # 실패 개수를 집계해 WARNING 으로 격상 + 성공은 무실패 시에만 INFO.
    pool_failures = 0
    main_failures = 0

    # WebsocketPool 위임 — _ticker_to_session 추적까지 일괄 정리
    try:
        await kis_ws_pool.unsubscribe_all()
    except Exception:
        pool_failures += 1
        logger.warning("[scanner_unsubscribe_all] pool.unsubscribe_all 실패", exc_info=True)

    # 보강: pool 분배 추적에 없는 메인 직접 구독 (체결통보 제외 TICK) 잔존 정리
    for tr_id, tr_key in list(kis_ws._subscriptions):
        if tr_id == TICK_TR_ID:
            try:
                await kis_ws.unsubscribe(tr_id, tr_key)
            except Exception:
                main_failures += 1
                logger.debug("[scanner_unsubscribe_all] main 잔여 해제 실패", exc_info=True)

    total_failures = pool_failures + main_failures
    if total_failures > 0:
        logger.warning(
            "[scanner_unsubscribe_all] 일부 구독 해제 실패 — pool=%d, main=%d",
            pool_failures, main_failures,
        )
    else:
        logger.info("모든 시세 구독 해제 완료")
```

**중요**:
- `kis_ws_pool` import 가 scanner.py 상단에 이미 있는지 확인 — 없으면 추가.
- "모든 시세 구독 해제 완료" INFO 는 **무실패 (`total_failures == 0`) 시에만** 출력.
  실패 발생 시 WARNING `[scanner_unsubscribe_all]` 로 격상 — 운영자 오해 차단.

#### Patch 2 — `src/engine/scheduler.py` 정상 종료 + finally 보강 (사이클 13-E-1 리뷰 ① 반영)

**위치 결정 원칙**: `kis_ws_pool.stop()` 은 반드시 `finally` 블록 안 — 또는 try/except 외부에서
정상·비정상 종료 둘 다 통과하는 경로 — 에 둬야 한다. `except Exception` 위쪽 (try 본문 마지막)
에만 두면 매매 프로세스 예외 발생 시 보조 세션이 누수된 채 다음 사이클 진입.

**사이클 13-E-1 리뷰 ① 결정 — (A) 채택 (메인 disconnect best-effort 추가)**:
직접 코드 검토 결과 `KisWebSocket.disconnect()` (`src/realtime/websocket.py:163-169`) 는
**idempotent** 임을 확인:

```python
async def disconnect(self) -> None:
    """연결을 종료한다."""
    self._running = False         # ← 매번 안전하게 False
    if self._ws:                  # ← 가드: 이미 None 이면 close 호출 안 함
        await self._ws.close()
        self._ws = None           # ← nullify
    logger.info("WebSocket 연결 종료")
```

두 번째 호출은 `self._ws is None` → `if` 가드로 close skip + `self._running = False`
재대입은 무해. 따라서 (A) 안 (메인 idempotent + finally best-effort 추가) 가 최소 변경 +
정상 경로 동작 100% 보존.
**(B) 안** (메인 disconnect 자체를 finally 로 이동) 은 정상 경로에서 `ws_task` await 순서가
달라져 회귀 위험 — 기각.

권장 배치: **`finally` 블록 내부**, 백그라운드 task cancel 직후, `pool.stop()` *전* (메인→보조
정리 순서 보존).

```python
# 488~492 라인: 정상 경로 (기존 유지) — 정상 종료 시 메인 disconnect 1차 보장
await kis_ws.disconnect()
try:
    await ws_task
except asyncio.CancelledError:
    pass

except Exception:
    logger.exception("매매 프로세스 오류")
    await write_log("ERROR", "매매 프로세스 비정상 종료")
finally:
    # 백그라운드 task lifecycle (기존 유지) — 5종 cancel + await
    for task_attr in (
        "_next_day_task", "_session_task", "_stale_watcher_task",
        "_swing_poll_task", "_swing_rest_poll_task",
    ):
        task = getattr(self, task_attr, None)
        if task and not task.done():
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
        setattr(self, task_attr, None)

    # 사이클 13-E-1 리뷰 ① — 비정상 종료 경로에서도 메인 disconnect 보장 (best-effort).
    # `start()` 본문 488 라인 도달 전 예외 발생 시 `try` 의 `kis_ws.disconnect()` 가
    # 건너뛰어진 채 `finally` 진입 가능 → 메인 WebSocket 이 연결된 채 잔존 + 다음 부팅
    # 시 동일 계정 중복 접속 위험. `disconnect()` 는 idempotent (websocket.py:163-169
    # `if self._ws:` 가드 + `self._ws = None` nullify) — 정상 경로에서 두 번째 호출은
    # noop. 따라서 항상 호출해도 회귀 0.
    try:
        await kis_ws.disconnect()
    except Exception:
        logger.warning("[scheduler_shutdown] main disconnect 실패 (best-effort)", exc_info=True)

    # 추가: 보조 세션 풀 정리 — 정상·비정상 종료 양쪽 보장
    # _started=False 재설정으로 다음 _boot start() 재초기화 + 24h 토큰 만료 후
    # silent death 차단. 메인→보조 순서 (위 disconnect 후) 보존.
    try:
        await kis_ws_pool.stop()
    except Exception:
        logger.warning("[scheduler_shutdown] pool.stop 실패", exc_info=True)

    self._running = False
    self._phase = "idle"
    await write_log("INFO", "매매 시스템 종료")
```

**중요**:
- `kis_ws.disconnect()` (메인) 는 `try` 본문에 그대로 유지 (정상 경로 동작 보존) +
  `finally` 에 best-effort 1회 추가 (비정상 경로 누수 차단). idempotent 검증 완료.
- 정상 경로: try `kis_ws.disconnect()` → `self._ws = None` → finally `kis_ws.disconnect()`
  진입 시 `if self._ws:` False → noop. 회귀 0.
- 메인→보조 정리 순서: finally 안에서도 `kis_ws.disconnect()` → `kis_ws_pool.stop()` 순서 보존.

#### Patch 3 — `src/engine/scheduler.py` 수동 `stop()` 보강 (사이클 13-E-1 리뷰 ② 반영)

**리뷰 ② 결정 — `_swing_rest_poll_task` 추가 + finally 와 동일 패턴 정렬**:
현재 `stop()` 의 task cancel 목록은 4종 (`_next_day_task`, `_session_task`, `_stale_watcher_task`,
`_swing_poll_task`) 으로 `_swing_rest_poll_task` 가 누락. `start()` 가 생성하는 모든 백그라운드
task 를 finally 와 동일한 5종 패턴으로 cancel + await 해야 disconnect/pool.stop 이후에도
REST 폴링이 한 사이클 더 돌거나 예외 로그가 발생하지 않는다.

```python
async def stop(self) -> None:
    """매매 프로세스를 중지한다."""
    self._running = False
    # 사이클 13-E-1 리뷰 ② — finally 와 동일한 5종 task cancel.
    # _swing_rest_poll_task 누락 시 disconnect/pool.stop 이후 REST 폴링이 한 사이클 더
    # 돌거나 예외 로그가 발생할 수 있어 finally 와 동일 목록·동일 처리로 통일.
    for task_attr in (
        "_next_day_task", "_session_task", "_stale_watcher_task",
        "_swing_poll_task", "_swing_rest_poll_task",
    ):
        task = getattr(self, task_attr, None)
        if task and not task.done():
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
        setattr(self, task_attr, None)
    await unsubscribe_all()
    await kis_ws.disconnect()
    # 추가: 수동 중지 시에도 동일 보장
    try:
        await kis_ws_pool.stop()
    except Exception:
        logger.warning("[scheduler_stop] pool.stop 실패", exc_info=True)
    await write_log("INFO", "매매 시스템 수동 중지")
```

**중요**: task cancel 은 `unsubscribe_all()`/`disconnect()`/`pool.stop()` *이전* 에 수행 —
폴링 task 가 종료된 후 자원 해제 순서 유지.

#### Import 확인

`scheduler.py` 상단에 `from src.realtime.websocket_pool import kis_ws_pool` 이미 있을 것
(기존 patch 1 import 와 동일 모듈). 없으면 추가.

### Refactor

본 fix 는 안전 보강이 본질 — 추가 리팩터 금지. 최소 변경 원칙.

---

### 사이클 13-E-1 보강 결정 (PR #12 리뷰 반영)

PR #12 (https://github.com/canduk910/auto_stock/pull/12) 의 Copilot 봇 리뷰 3건 반영본.
사용자가 "전부 반영" 결정 → §4 Patch 1/2/3 갱신.

#### ① `src/engine/scheduler.py:519` — finally 의 메인 disconnect 누수
- **채택안**: **(A) `finally` 에 `kis_ws.disconnect()` best-effort 1회 추가**
- **근거**:
  - `KisWebSocket.disconnect()` (`src/realtime/websocket.py:163-169`) 직접 검토 결과
    **완전 idempotent** — `if self._ws:` 가드 + `self._ws = None` nullify. 두 번째 호출은
    close 자체를 skip + `self._running = False` 재대입은 무해.
  - (B) 안 (메인 disconnect 를 finally 로 이동) 은 정상 경로의 `ws_task` await 순서를
    바꿔 회귀 위험 — 기각.
  - try/except 로 1차 보호 + idempotent 가 검증된 이상, finally best-effort 가
    "정상 경로 noop / 비정상 경로 자원 회수" 양립 — 최소 변경 원칙 충족.
- **반영 위치**: §4 Patch 2 finally 블록 내부, `pool.stop()` *전* (메인→보조 순서 보존).
- **Copilot 코멘트**: https://github.com/canduk910/auto_stock/pull/12 `scheduler.py:519`

#### ② `src/engine/scheduler.py:621` — 수동 `stop()` task cancel 누락
- **채택안**: **`_swing_rest_poll_task` 추가 + finally 5종 패턴과 동일 정렬**
- **근거**:
  - `start()` 가 생성하는 백그라운드 task 5종 중 `_swing_rest_poll_task` 만 누락.
    disconnect/pool.stop 이후 REST 폴링이 한 사이클 더 돌거나 close 된 자원에 접근하며
    예외 로그 발생 가능.
  - finally 의 task cancel 블록과 정확히 동일한 목록·동일 처리 (cancel → await → setattr None)
    로 통일 — 정상/비정상/수동 종료 3 경로 동작 일치 보장.
- **반영 위치**: §4 Patch 3 신규 코드 블록.
- **Copilot 코멘트**: https://github.com/canduk910/auto_stock/pull/12 `scheduler.py:621`

#### ③ `src/engine/scanner.py:563` — INFO 로그 오해
- **채택안**: **실패 카운터 + 조건부 로그 레벨** (pool/main 실패 개수 집계 → 0 이면 INFO,
  >0 이면 WARNING `[scanner_unsubscribe_all]` 격상)
- **근거**:
  - 현재 코드는 `pool.unsubscribe_all()` / `kis_ws.unsubscribe()` 예외를 swallow 한 뒤
    항상 INFO "모든 시세 구독 해제 완료" 출력 → 실제 일부 실패해도 운영자는 "성공" 으로 오해.
  - 실패 개수 집계 (pool_failures / main_failures) → `total_failures > 0` 분기로 WARNING
    포맷 (`pool=N, main=M`) 출력 + 무실패 시에만 INFO "완료" 출력.
- **반영 위치**: §4 Patch 1 코드 블록.
- **Copilot 코멘트**: https://github.com/canduk910/auto_stock/pull/12 `scanner.py:563`

---

## 5. 회귀 시나리오 (tester 검증)

### 시나리오 A — 정상 사이클 종료

```
1. _boot() → start() → 메인 + 보조 1 세션 연결
2. 09:30 scan + subscribe (보조에 LOW 분배)
3. 20:00 TIME_NXT_POST_CLOSE → unsubscribe_all() 호출
4. 검증: 메인 _subscriptions == empty AND 보조 _subscriptions == empty AND
        _ticker_to_session == empty
5. 20:10 _settle → _reset_daily_state → kis_ws.disconnect → kis_ws_pool.stop()
6. 검증: 메인 ws_connected=False AND 보조 ws_connected=False AND _started=False
```

### 시나리오 B — 다음 _boot 재초기화

```
1. 시나리오 A 종료 상태에서 시작
2. 다음날 07:50 _boot → kis_ws_pool.start()
3. 검증: _started=False → True 재진입 정상 → 보조 세션 재연결 발화
4. 검증: list_accounts() 다시 호출돼 보조 KisWebSocket 재생성
```

### 시나리오 C — `/api/realtime/subscriptions` 응답

```
1. 시나리오 A 종료 직후
2. GET /api/realtime/subscriptions
3. 검증: total=0, acked=0, sessions[*].subscribed=0, sessions[*].ws_connected=False
```

### 시나리오 D — 수동 중지 경로

```
1. 운영 중 → POST /api/trading/stop (또는 scheduler.stop() 직접 호출)
2. 검증: 메인 + 보조 둘 다 disconnect + _started=False
```

### 시나리오 E — 보조 stop 예외 흡수

```
1. kis_ws_pool.stop() 이 예외 발생하도록 mock
2. scheduler 종료 흐름 → write_log("INFO", "매매 시스템 종료") 도달 verify
3. kis_ws.disconnect() 가 stop() 보다 *먼저* 호출돼 메인 자금 안전 경로 보장
```

### 시나리오 F — `_scan_loop` 1765 라인 영향 검증

```
1. 09:30 _scan_loop 진입 → unsubscribe_all() → subscribe_filtered_stocks()
2. 검증: 보조 세션 _ticker_to_session 추적이 stale 상태로 잔존하지 않음
   (Patch 1 로 자연 해결 — pool.unsubscribe_all() 이 _ticker_to_session.clear())
```

### 시나리오 G — 비정상 종료 → start() 예외 → finally → 메인 disconnect best-effort (사이클 13-E-1 ①)

```
1. start() 본문 진입 → kis_ws.connect() 후 488 라인 도달 *전* (예: ws_task 생성
   직후 또는 settle 중간) 의도적 예외 raise (mock 패치) → except 분기 진입
2. except 가 ERROR 로그 후 finally 진입
3. 검증: finally 의 task cancel 5종 정상 수행 (cancel + await + setattr None)
4. 검증: kis_ws.disconnect() 가 finally 에서 best-effort 호출됨 — 메인 _ws=None, _running=False
5. 검증: kis_ws_pool.stop() 이 그 *후* 호출됨 (메인→보조 순서)
6. 검증: write_log("INFO", "매매 시스템 종료") 도달
7. 회귀 가드 (정상 경로): start() 정상 종료 시 try `kis_ws.disconnect()` 1회 +
   finally `kis_ws.disconnect()` 2회차 → `if self._ws:` False 분기로 noop 보장
   (logger.info "WebSocket 연결 종료" 가 2회 출력될 뿐 자원 오작동 없음)
```

### 시나리오 H — 수동 stop() task 5종 cancel 검증 (사이클 13-E-1 ②)

```
1. start() 실행 중 (모든 백그라운드 task 5종 active) → scheduler.stop() 호출
2. 검증: _next_day_task / _session_task / _stale_watcher_task / _swing_poll_task /
        _swing_rest_poll_task 모두 cancel() 호출 + await 완료
3. 검증: disconnect/pool.stop *후* 에 REST 폴링 로그가 추가로 발생하지 않음
   (cancel 누락 시 한 사이클 더 돌며 close 된 자원에 접근 → 예외 로그)
4. 검증: 모든 task attribute 가 None 으로 재대입됨
```

### 시나리오 I — scanner.unsubscribe_all 실패 분기 로그 (사이클 13-E-1 ③)

```
케이스 I-1 (무실패):
- pool.unsubscribe_all() 정상 + kis_ws.unsubscribe() 정상
- 검증: INFO "모든 시세 구독 해제 완료" 1회 출력 + WARNING 없음

케이스 I-2 (pool 실패):
- pool.unsubscribe_all() → RuntimeError mock
- 검증: WARNING "[scanner_unsubscribe_all] pool.unsubscribe_all 실패" 1회
- 검증: WARNING "[scanner_unsubscribe_all] 일부 구독 해제 실패 — pool=1, main=0" 1회
- 검증: INFO "모든 시세 구독 해제 완료" 출력 안 됨

케이스 I-3 (main 잔여 일부 실패):
- pool 정상 + kis_ws.unsubscribe 2건 중 1건 예외
- 검증: WARNING "[scanner_unsubscribe_all] 일부 구독 해제 실패 — pool=0, main=1"
- 검증: INFO "모든 시세 구독 해제 완료" 출력 안 됨

케이스 I-4 (둘 다 실패):
- 양쪽 모두 예외
- 검증: WARNING 격상 + INFO "완료" 출력 안 됨
```

---

## 6. 안전 가드 (변경 금지)

| 규칙 | 비고 |
|------|------|
| 체결통보 (H0STCNI0/H0STCNI9) 메인 강제 분기 | 절대 손대지 말 것 |
| `_subscriptions` set 직접 수정 금지 | 반드시 `kis_ws_pool` API 경유 |
| 모든 시각 KST 강제 | `_to_kst(iso)` 헬퍼 |
| HIGH 우선순위 (보유/익일청산) `bypass_limit=True` | 변경 금지 |
| KRX 운영 시간 외 (15:30~/익일 07:50 _boot 전) 푸시 권장 | 안전 deploy |

---

## 7. 영향 인덱스 재생성

두 파일 변경분 반영:

```bash
python tools/test_impact/build_index.py
node  tools/test_impact/build_index_frontend.mjs
```

PR 빠른 피드백 가드 — `affected.py` 가 본 fix 의 영향 테스트를 정확히 잡아야 함.

---

## 8. 작업 분배 (사이클 13-E-1 — PR #12 리뷰 반영본)

| 단계 | 담당 | 모델 | 산출물 |
|------|------|------|--------|
| Red 테스트 작성 (보강) | tdd-engineer | opus | 13-E Test A~D 유지 + 13-E-1 Test E/F/G 신규 |
| Green 구현 (재실행) | backend-dev | sonnet | scanner.py + scheduler.py 두 파일 갱신 |
| 통합 검증 | tester | opus | 시나리오 A~I 회귀 (G/H/I 신규), `/api/realtime/subscriptions` 응답 확인 |
| 영향 인덱스 | (자동) | - | `tools/test_impact/build_index*` 재생성 |
| 문서 동기화 | (선택) | - | `docs/HARNESS_CHANGELOG.md` 사이클 13-E-1 1줄 추가 |

### 13-E-1 신규 Red 테스트 (tdd-engineer 추가 작성)

#### Test E — `tests/unit/engine/test_scheduler_finally_main_disconnect.py` (NEW, 리뷰 ①)

```
시나리오:
1. scheduler.start() 본문 mock 으로 488 라인 도달 전 RuntimeError raise
2. finally 진입 시 kis_ws.disconnect() 가 호출돼야 함 (best-effort)
3. kis_ws.disconnect() AsyncMock — finally 에서 1회 호출 verify
4. pool.stop() 이 disconnect *후* 호출되는 순서 verify (call_order)
5. write_log("INFO", "매매 시스템 종료") 도달 verify
회귀 가드:
6. 정상 종료 경로 — try 본문 disconnect 1회 + finally disconnect 1회 = 총 2회
   호출이지만 두 번째는 _ws=None 으로 noop 임을 verify (close 는 1회만)
```

#### Test F — `tests/unit/engine/test_scheduler_stop_task_cancel.py` (NEW, 리뷰 ②)

```
시나리오:
1. scheduler._next_day_task / _session_task / _stale_watcher_task /
   _swing_poll_task / _swing_rest_poll_task 5종을 AsyncMock task 로 주입
2. await scheduler.stop()
3. 각 task.cancel() 5회 모두 호출 verify
4. 각 task 가 await 됐는지 verify
5. 각 attr 가 None 으로 재대입됐는지 verify
6. cancel 순서가 unsubscribe_all/disconnect/pool.stop *이전* 인지 call_order verify
```

#### Test G — `tests/unit/engine/test_scanner_unsubscribe_all_logging.py` (NEW, 리뷰 ③)

```
시나리오 G-1 (무실패):
- pool.unsubscribe_all + kis_ws.unsubscribe 정상
- caplog: INFO "모든 시세 구독 해제 완료" present, WARNING absent

시나리오 G-2 (pool 실패):
- pool.unsubscribe_all → Exception
- caplog: WARNING "[scanner_unsubscribe_all] pool.unsubscribe_all 실패" present
- caplog: WARNING "일부 구독 해제 실패 — pool=1, main=0" present
- caplog: INFO "모든 시세 구독 해제 완료" *absent*

시나리오 G-3 (main 잔여 실패):
- 메인 unsubscribe 1건 예외
- caplog: WARNING "일부 구독 해제 실패 — pool=0, main=1" present
- caplog: INFO "완료" absent
```

### 분배 메시지 템플릿 (사이클 13-E-1)

**→ tdd-engineer (Red 단계, 재진입)**
> 사이클 13-E-1. PR #12 (https://github.com/canduk910/auto_stock/pull/12) Copilot 리뷰
> 3건 반영 보강. 본 명세의 §4 Patch 1/2/3 + §8 13-E-1 신규 Red 테스트 (Test E/F/G)
> 를 추가 작성하라. 기존 13-E Test A/B/C/D 는 그대로 유지 (회귀 가드).
> 핵심 검증 추가:
> (E) `scheduler` finally 에서 `kis_ws.disconnect()` best-effort 호출 + 정상경로 idempotent,
> (F) 수동 `stop()` 이 task 5종 (특히 `_swing_rest_poll_task`) cancel + await + None 재대입,
> (G) `scanner.unsubscribe_all` 이 실패 카운트에 따라 INFO/WARNING 분기.
> 모든 테스트는 *Red* 상태로 커밋. **금지**: 체결통보 분기 / `_subscriptions` 직접 수정.

**→ backend-dev (Green 단계, 재실행)**
> tdd-engineer 13-E-1 Red 통과 후 진입. 본 명세 §4 갱신본의 Patch 1/2/3 최소 변경 구현.
> **Patch 1 (scanner)**: 실패 카운터 pool_failures/main_failures + total_failures > 0 분기
> WARNING 격상, 무실패 시에만 INFO "완료". 기존 13-E patch 위에 덮어쓰기.
> **Patch 2 (scheduler finally)**: 기존 `pool.stop()` 호출 *전* 에 `kis_ws.disconnect()`
> best-effort try/except 추가. 메인→보조 순서 보존.
> **Patch 3 (scheduler stop)**: task cancel 목록을 finally 와 동일한 5종 (`_swing_rest_poll_task`
> 추가) + 동일 처리 패턴으로 통일. cancel 은 `unsubscribe_all`/`disconnect`/`pool.stop`
> *이전*.
> 변경 파일: `src/engine/scanner.py` + `src/engine/scheduler.py` 두 파일만.
> 영향 인덱스 재생성: `python tools/test_impact/build_index.py`.

**→ tester (통합 검증)**
> backend-dev 13-E-1 Green 통과 후 진입. 본 명세 §5 시나리오 A~I 전체 회귀.
> 특히 신규 시나리오:
> - G (비정상 종료 → start() 예외 → finally 메인 disconnect best-effort + 순서)
> - H (수동 stop task 5종 cancel — REST 폴링 한 사이클 더 도는지 확인)
> - I-1~I-4 (scanner 로그 분기 4 케이스, caplog 검증)
> `/api/realtime/subscriptions` 응답 sessions[*].subscribed 전부 0 회귀 유지.

---

## 9. 검수 체크리스트 (team-leader 최종 승인)

### 13-E 기본 (유지)

- [ ] 모든 단위 테스트 통과 (`pytest tests/unit/engine/ tests/unit/realtime/`)
- [ ] 통합 테스트 통과 (`pytest tests/integration/test_scheduler_*`)
- [ ] `kis_ws_pool.stop()` 이 메인 disconnect *후* 호출되는 순서 보존
- [ ] 보조 stop() 예외가 메인 종료 경로를 막지 않음 (try/except 흡수)
- [ ] `_started=False` 재설정 → 다음 `start()` 호출 시 재초기화 발화
- [ ] `_ticker_to_session` clear 까지 완료 (분배 추적 stale 0)
- [ ] 체결통보 분기 코드 무변경 verify (`git diff` 로 확인)
- [ ] **비정상 종료 경로 (run 본문 예외) → finally → pool.stop 도달 verify**
- [ ] 모의(VTS)에서 1사이클 검증 후 실전 배포
- [ ] 운영 가이드 — KRX 메인 시간 외 (15:30~ 또는 익일 07:50 _boot 전) 배포
- [ ] **로컬과 EC2 동시 실행 금지** — KIS 동일 계정 동시 접속 충돌 주의

### 13-E-1 보강 (PR #12 리뷰 ①②③ 반영)

- [ ] **(① 리뷰) 메인 `disconnect()` idempotent 직접 검증** — `src/realtime/websocket.py:163-169`
      `if self._ws:` 가드 + `self._ws = None` nullify 코드 라인 `git diff` 로 무변경 확인
- [ ] **(① 리뷰) finally 에서 `kis_ws.disconnect()` best-effort 호출** — try/except 로
      예외 흡수 + WARNING 로그 prefix `[scheduler_shutdown]`
- [ ] **(① 리뷰) finally 메인 disconnect 가 `pool.stop()` *전* 위치** — 메인→보조 순서 보존
- [ ] **(① 리뷰) 정상 종료 경로 회귀 0** — try 본문 disconnect 1회 + finally 2회차 = noop
      (close 자체는 1회만, "WebSocket 연결 종료" INFO 가 2회 출력될 수 있으나 자원 무관)
- [ ] **(② 리뷰) 수동 `stop()` task cancel 5종 동일 패턴** — `_next_day_task` / `_session_task`
      / `_stale_watcher_task` / `_swing_poll_task` / `_swing_rest_poll_task` (특히 마지막 누락 가드)
- [ ] **(② 리뷰) `stop()` 의 task cancel 이 `unsubscribe_all`/`disconnect`/`pool.stop`
      *이전* 수행** — 폴링이 close 자원에 접근하지 않음
- [ ] **(② 리뷰) `stop()` 후 REST 폴링 추가 1사이클 미발생** — caplog 또는 동작 로그로 확인
- [ ] **(③ 리뷰) `scanner.unsubscribe_all` 실패 카운터 분기** — 무실패 시 INFO "완료",
      실패 ≥1 시 INFO 출력 안 됨 + WARNING `[scanner_unsubscribe_all]` 격상
- [ ] **(③ 리뷰) WARNING 포맷에 `pool=N, main=M` 카운트 포함** — 운영자가 어느 경로
      실패인지 즉시 식별 가능
- [ ] **(③ 리뷰) pool/main 양쪽 모두 try/except 로 분리** — 한쪽 실패가 다른쪽 처리를
      막지 않음
