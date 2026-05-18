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

#### Patch 1 — `src/engine/scanner.py:549-554`

```python
async def unsubscribe_all() -> None:
    """모든 종목 구독을 해제한다 (메인 + 보조 세션 전체)."""
    # WebsocketPool 위임 — _ticker_to_session 추적까지 일괄 정리
    try:
        await kis_ws_pool.unsubscribe_all()
    except Exception:
        logger.warning("[scanner_unsubscribe_all] pool.unsubscribe_all 실패", exc_info=True)
    # 보강: pool 분배 추적에 없는 메인 직접 구독 (체결통보 제외 TICK) 잔존 정리
    for tr_id, tr_key in list(kis_ws._subscriptions):
        if tr_id == TICK_TR_ID:
            try:
                await kis_ws.unsubscribe(tr_id, tr_key)
            except Exception:
                logger.debug("[scanner_unsubscribe_all] main 잔여 해제 실패", exc_info=True)
    logger.info("모든 시세 구독 해제 완료")
```

**중요**: `kis_ws_pool` import 가 scanner.py 상단에 이미 있는지 확인 — 없으면 추가.

#### Patch 2 — `src/engine/scheduler.py:488-492` 직후

```python
await kis_ws.disconnect()
try:
    await ws_task
except asyncio.CancelledError:
    pass
# 추가: 보조 세션 풀 정리 — _started=False 재설정으로 다음 _boot start() 재초기화 보장
try:
    await kis_ws_pool.stop()
except Exception:
    logger.warning("[scheduler_shutdown] pool.stop 실패", exc_info=True)
```

#### Patch 3 — `src/engine/scheduler.py:604-606` 사이

```python
await unsubscribe_all()
await kis_ws.disconnect()
# 추가: 수동 중지 시에도 동일 보장
try:
    await kis_ws_pool.stop()
except Exception:
    logger.warning("[scheduler_stop] pool.stop 실패", exc_info=True)
await write_log("INFO", "매매 시스템 수동 중지")
```

#### Import 확인

`scheduler.py` 상단에 `from src.realtime.websocket_pool import kis_ws_pool` 이미 있을 것
(기존 patch 1 import 와 동일 모듈). 없으면 추가.

### Refactor

본 fix 는 안전 보강이 본질 — 추가 리팩터 금지. 최소 변경 원칙.

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

## 8. 작업 분배

| 단계 | 담당 | 모델 | 산출물 |
|------|------|------|--------|
| Red 테스트 작성 | tdd-engineer | opus | Test A/B/C/D 4종 테스트 파일 |
| Green 구현 | backend-dev | sonnet | scanner.py + scheduler.py 두 파일 최소 변경 |
| 통합 검증 | tester | opus | 시나리오 A~F 회귀, `/api/realtime/subscriptions` 응답 확인 |
| 영향 인덱스 | (자동) | - | `tools/test_impact/build_index*` 재생성 |
| 문서 동기화 | (선택) | - | `docs/HARNESS_CHANGELOG.md` 사이클 13-E 1줄 추가 |

---

## 9. 검수 체크리스트 (team-leader 최종 승인)

- [ ] 모든 단위 테스트 통과 (`pytest tests/unit/engine/ tests/unit/realtime/`)
- [ ] 통합 테스트 통과 (`pytest tests/integration/test_scheduler_*`)
- [ ] `kis_ws_pool.stop()` 이 메인 disconnect *후* 호출되는 순서 보존
- [ ] 보조 stop() 예외가 메인 종료 경로를 막지 않음 (try/except 흡수)
- [ ] `_started=False` 재설정 → 다음 `start()` 호출 시 재초기화 발화
- [ ] `_ticker_to_session` clear 까지 완료 (분배 추적 stale 0)
- [ ] 체결통보 분기 코드 무변경 verify (`git diff` 로 확인)
- [ ] 모의(VTS)에서 1사이클 검증 후 실전 배포
