# 사이클 13-E-2 — `start()` 로컬 task lifecycle 좀비 차단

**작성일**: 2026-05-18 (KST)
**작성자**: team-leader
**브랜치**: `claude/setup-codebase-mcp-cNc2f` (PR #12 연속)
**우선순위**: HIGH (자금 안전성 — 좀비 WebSocket task 가 다음 부팅 시 KIS 동일 계정 중복 접속 + 24h 토큰 만료 후 silent death)
**전제**: 13-E + 13-E-1 의 `finally` 블록 task 5종 cancel 로직은 변경 금지, **확장만** 허용

---

## §1. 현상

### Copilot 리뷰 (PR #12, 두 번째 리뷰)

> `src/engine/scheduler.py:519` 위치 — `start()`의 `finally`에서 `kis_ws_pool.stop()`을
> 호출하도록 추가된 것은 좋지만, `ws_task = asyncio.create_task(kis_ws.connect(...))`
> 및 `scan_task = asyncio.create_task(self._scan_loop())`는 로컬 변수로 생성되고
> `finally`에서 취소/await되지 않습니다. 따라서 try 본문 중간에 예외가 나면
> `finally`가 풀을 stop한 뒤에도 `ws_task`/`scan_task`가 살아남아 연결/구독을
> 유지하거나 다시 구독을 시도할 수 있어(좀비 태스크) 종료 정리 의도가 깨질 수 있습니다.
> `ws_task`/`scan_task`를 try 밖에서 None으로 초기화한 뒤 `finally`에서 존재 시
> cancel+await(또는 self 속성으로 관리)하고, 그 다음에 `kis_ws_pool.stop()`을
> 호출하도록 정리 순서를 보강해 주세요.

### Line 단위 grep 사실관계

| Line | 코드 | 비고 |
|------|------|------|
| `scheduler.py:244` | `ws_task = asyncio.create_task(kis_ws.connect(dispatch_message))` | **로컬 변수**, finally 미참조 |
| `scheduler.py:402` | `scan_task = asyncio.create_task(self._scan_loop())` | **로컬 변수** (KRX 메인 매수 시작 분기) |
| `scheduler.py:408` | `scan_task = None` (15:20 이후 시작 시) | 정상 경로 처리 |
| `scheduler.py:428-429` | `if scan_task is None or scan_task.done(): scan_task = asyncio.create_task(self._scan_loop())` | NXT 애프터 재생성 |
| `scheduler.py:441-442` | `if scan_task and not scan_task.done(): scan_task.cancel()` | 20:00 정상 분기 cancel only |
| `scheduler.py:490` | `await ws_task` | 정상 경로 only |
| `scheduler.py:497-510` finally | `self._next_day_task` + `_session_task` + `_stale_watcher_task` + `_swing_poll_task` + `_swing_rest_poll_task` 5종만 처리 | 로컬 `ws_task` / `scan_task` 누락 |

→ `try` 본문 line 244 ~ line 488 사이 어디서든 예외 발생 시 `ws_task` / `scan_task` 가
`finally` 진입 시점에 **unreachable** — cancel/await 경로 부재.

---

## §2. 근본 원인 — 로컬 변수 lifecycle 미관리

`start()` 의 task 5종 (`_next_day_task` / `_session_task` / `_stale_watcher_task` /
`_swing_poll_task` / `_swing_rest_poll_task`) 은 `self.*` 속성이라 `finally` 의
`getattr(self, task_attr, None)` 루프로 일괄 정리되지만, `ws_task` / `scan_task` 는
함수 로컬 변수로 남았다. Python 스코프 규칙상 `try` 본문 *중간* 예외 시:

1. 로컬 변수 `ws_task` / `scan_task` 는 `finally` 블록의 다른 분기에서 참조 불가
2. asyncio task 는 garbage collect 되어도 즉시 cancel 되지 않음 — event loop 가 참조 보유
3. `kis_ws_pool.stop()` 직후에도 `ws_task` 는 `kis_ws.connect()` 의 무한 루프 안에서 살아남음
4. `scan_task` 는 `_scan_loop()` 의 5분 sleep 후 깨어나 `subscribe_filtered_stocks()` 재시도 가능

→ 좀비 task 2종 (메인 WebSocket connect loop + scan_loop 재구독) 가 다음 `_boot()` 까지 잔류.

---

## §3. 트레이딩 안전성 평가

### 자금 안전 영향 (HIGH)

- **다음 부팅 시 KIS 동일 계정 중복 접속**: 좀비 `ws_task` 가 `kis_ws.connect()` 의 ping/reconnect
  loop 안에서 socket 유지 → 다음 날 07:50 `_boot()` 시 새 connect 시도가 KIS 서버에서
  거부 (동일 계정 동시 접속 차단) → 메인 시세 0 건 수신 → **매수/매도 신호 전면 차단**.
- **24h 토큰 만료 후 silent death**: 좀비 `ws_task` 의 토큰이 만료되면 KIS 서버가 연결을
  끊고 좀비 task 는 reconnect 시도하지만 manager 가 garbage collected → 새 토큰 발급
  불가 → silent 상태로 메모리만 점유 (CLAUDE.md "WebSocket 다중 안전망" 4중 가드를 회피).
- **scan_task 좀비**: `_scan_loop` 5분 주기로 `subscribe_filtered_stocks()` 호출 →
  종료된 줄 알았던 시스템이 KIS API 호출 발생 + Rate Limit 카운트 소모. 13-E 가 잡으려
  했던 보조 세션 좀비의 다른 경로 (메인 task → 보조 세션 재발급 트리거).

### 회귀 위험 평가 (LOW)

- 13-E + 13-E-1 의 5종 task 처리 코드와 충돌 없음 — **추가만 발생**.
- `kis_ws.connect()` 는 `asyncio.CancelledError` 안전 처리 (`websocket.py` 의 receive
  loop 가 cancel scope 인식). cancel + await 패턴이 idempotent.
- `_scan_loop` 의 5분 sleep 도 `asyncio.sleep()` 기반 → cancel 안전.

---

## §4. Fix 명세

### 결정: **방식 (B) 채택 — `self._ws_task` / `self._scan_task` 속성 승격**

**근거 (3 문장)**:
1. 13-E-1 finally 블록이 이미 `self.*` 속성 5종을 `for task_attr in (...)` 루프로 일괄
   정리하는 패턴을 채택했고, 같은 패턴에 2종을 추가하는 것이 **가독성 + 일관성** 측면에서
   우월하다.
2. `ws_task` / `scan_task` 는 `start()` 본문에서 여러 라인 (244, 402, 408, 428, 441, 490) 에
   걸쳐 참조되므로, 로컬 변수 lifecycle 을 try 밖 None 초기화로 노출하면 변수 scope 가
   `start()` 전체로 퍼져 어차피 self 화와 가독성 차이가 없다.
3. 향후 `stop()` 메서드 (`scheduler.py:621` 부근) 에서도 동일 정리가 필요할 수 있어
   `self.*` 속성화가 확장성 측면에서 우월하다 (13-E-1 의 `_swing_rest_poll_task` 누락
   회귀와 같은 결함 차단).

### Red Patch (먼저 실패해야 함 — tdd-engineer 작성)

```python
# tests/engine/test_scheduler_zombie_task_cleanup.py (NEW)
# 13-E-2 회귀 가드 — finally 블록이 ws_task / scan_task 도 정리하는지 검증
```

### Green Patch — 정확한 변경 위치

**Patch 1**: `scheduler.py` `__init__` (속성 초기화 추가)
- 위치: 13-E-1 이 추가한 `self._swing_rest_poll_task = None` 직후 (대략 line ~120)
- before/after:
  ```python
  # before
  self._swing_rest_poll_task: Optional[asyncio.Task] = None

  # after
  self._swing_rest_poll_task: Optional[asyncio.Task] = None
  # 사이클 13-E-2 — start() 본문 로컬 task 를 속성 승격, finally 좀비 차단
  self._ws_task: Optional[asyncio.Task] = None
  self._scan_task: Optional[asyncio.Task] = None
  ```

**Patch 2**: `scheduler.py:244` (ws_task 생성)
- before:
  ```python
  ws_task = asyncio.create_task(kis_ws.connect(dispatch_message))
  ```
- after:
  ```python
  self._ws_task = asyncio.create_task(kis_ws.connect(dispatch_message))
  ```

**Patch 3**: `scheduler.py:402, 408, 428-429, 441-442, 490` (scan_task / ws_task 참조 자리 모두 self 화)
- `scan_task = asyncio.create_task(self._scan_loop())` → `self._scan_task = asyncio.create_task(self._scan_loop())`
- `scan_task = None` (line 408) → `self._scan_task = None`
- `scan_task is None or scan_task.done()` → `self._scan_task is None or self._scan_task.done()`
- `scan_task = asyncio.create_task(self._scan_loop())` (line 429) → `self._scan_task = ...`
- `if scan_task and not scan_task.done(): scan_task.cancel()` (line 441-442) → `if self._scan_task and not self._scan_task.done(): self._scan_task.cancel()`
- `await ws_task` (line 490) → `await self._ws_task`

**Patch 4**: `scheduler.py:499-502` (finally 루프에 2종 추가)
- before:
  ```python
  for task_attr in (
      "_next_day_task", "_session_task", "_stale_watcher_task",
      "_swing_poll_task", "_swing_rest_poll_task",
  ):
  ```
- after:
  ```python
  # 사이클 13-E-2 — ws_task / scan_task 도 self.* 속성화 후 동일 cancel 루프 포함.
  # 정리 순서: 백그라운드 task 6종 cancel → 메인 ws disconnect → pool stop.
  # ws_task 가 살아있으면 disconnect 가 race 가능 → cancel 을 먼저.
  for task_attr in (
      "_next_day_task", "_session_task", "_stale_watcher_task",
      "_swing_poll_task", "_swing_rest_poll_task",
      "_ws_task", "_scan_task",
  ):
  ```

### Refactor 금지 영역

- `start()` 본문 ws_task / scan_task **생성 시점 변경 금지** — 244 / 402 / 408 / 428 라인의
  생성 분기 자체는 그대로 (self 화만 수행)
- 13-E + 13-E-1 의 finally 블록 5종 처리 코드 변경 금지 (추가만)
- line 488 `await kis_ws.disconnect()` 위치 보존 (정상 경로)
- line 490 `await ws_task` 위치 보존 (정상 경로, self 화만)
- `kis_ws_pool.stop()` 호출 위치 (line 526~528) 변경 금지

---

## §5. 회귀 시나리오 (J / K — 13-E 의 A~I 와 회귀 회피)

### Test J — 13-E-2 신규 회귀 가드

| ID | 시나리오 | 기대 |
|----|----------|------|
| J-1 | `start()` line 244 직후 (ws_task 생성 후 ~ line 402 이전) 예외 mock raise | finally 진입 → `self._ws_task.cancel()` + await CancelledError swallow, `self._scan_task is None` 분기 skip 안전, `kis_ws.disconnect()` + `kis_ws_pool.stop()` 호출 검증 |
| J-2 | `start()` line 402 직후 (scan_task 생성 후 ~ line 488 이전) 예외 raise | finally 진입 → `self._ws_task` AND `self._scan_task` 모두 cancel + await, 좀비 0건 |
| J-3 | `start()` 정상 경로 (line 490 도달) | `self._ws_task` 이미 await 완료 → finally 의 `not done()` 가드로 cancel skip, `self._scan_task` 도 line 442 에서 cancel 후 finally 에서 done 가드 skip |
| J-4 | 15:20 이후 시작 분기 (line 408 → `self._scan_task = None`) | finally 의 `if task and not task.done()` 가드가 None 안전 처리, AttributeError 없음 |
| J-5 | 정상 경로 finally 진입 시 cancel 호출이 idempotent (already done task 의 cancel 안전) | logger.warning 0건 + 예외 0건 |

### Test K — 13-E + 13-E-1 회귀 가드 (변경 후에도 통과)

| ID | 회귀 대상 | 기대 |
|----|-----------|------|
| K-A | 13-E Test A: 정상 종료 후 pool.stop 호출 | 13-E-2 변경 후에도 통과 |
| K-B | 13-E Test B: 비정상 종료 (`generate_recommendations` 예외) 후 pool.stop 호출 | 통과 |
| K-C | 13-E Test C: 메인 disconnect 후 pool.stop 순서 보장 | 통과 (Patch 4 finally 루프 순서는 task cancel → main disconnect → pool stop 으로 보존) |
| K-D | 13-E Test D: scanner.unsubscribe_all 실패 로깅 분리 | 통과 (scanner 미수정) |
| K-E | 13-E-1 Test E: `stop()` 의 `_swing_rest_poll_task` 누락 회귀 가드 | 통과 (stop() 미수정) |
| K-F | 13-E-1 Test F: scanner.unsubscribe_all 의 `error_count > 0` 분기 | 통과 |
| K-G | 13-E-1 Test G: try 본문 line 488 도달 전 예외 시 finally 메인 disconnect best-effort | 통과 (line 518-521 보존) |

---

## §6. 안전 가드 (변경 금지)

- 체결통보 (H0STCNI0 / H0STCNI9) 분기 (line 257-270)
- `_subscriptions` 직접 수정 금지 — `kis_ws.subscribe()` / `unsubscribe()` 경유
- 13-E + 13-E-1 finally 블록 task 5종 처리 코드 (line 497-510) — **확장만, 변경 금지**
- 메인 disconnect 순서: line 488 `try` 본문 + line 518-521 `finally` best-effort (둘 다 보존)
- `start()` 본문의 ws_task / scan_task 생성 위치 자체 (line 244 / 402 / 408 / 428) —
  lifecycle 관리만 추가, 생성 시점 / 방식 변경 금지
- `kis_ws_pool.stop()` 호출 위치 (line 526~528) 보존
- 정상 경로 line 490 `await ws_task` (→ `await self._ws_task`) 보존
- 정상 경로 line 441-442 `scan_task.cancel()` (→ `self._scan_task.cancel()`) 보존 —
  finally 에서 두 번 cancel 되어도 idempotent

---

## §7. 영향 인덱스 재생성

```bash
python tools/test_impact/build_index.py
node  tools/test_impact/build_index_frontend.mjs
```

`tools/test_impact/affected.py origin/main --target=backend` 가 `scheduler.py` 변경으로
다음 테스트를 영향 집합에 포함해야 함:
- `tests/engine/test_scheduler_*` 기존 전체
- `tests/engine/test_scheduler_zombie_task_cleanup.py` (신규)
- `tests/engine/test_scheduler_shutdown_*` (13-E + 13-E-1)

---

## §8. 작업 분배

### tdd-engineer (Red — opus)

- **신규 파일**: `tests/engine/test_scheduler_zombie_task_cleanup.py`
- Test J-1 ~ J-5 (5 케이스) 작성
- mock 전략:
  - `kis_ws.connect`, `kis_ws.disconnect`, `kis_ws_pool.start`, `kis_ws_pool.stop` → AsyncMock
  - `scheduler._boot`, `_settle`, `_force_clear_main_only`, `_confirm_breakout_open_prices` 등
    → AsyncMock (즉시 return)
  - `_wait_until` → AsyncMock (즉시 return, 시간 가드 우회)
  - 예외 주입: `register_tick_handler` 또는 `_boot` 직후 mock raise
- assert 포인트:
  - `scheduler._ws_task.cancel.called` (또는 task done 상태)
  - `scheduler._scan_task` None 또는 cancelled
  - `kis_ws.disconnect.await_count >= 1` + `kis_ws_pool.stop.await_count >= 1`
  - `_ws_task` / `_scan_task` 가 finally 종료 후 None (setattr 재설정 확인)
- **Test K (회귀)**: 기존 13-E + 13-E-1 테스트 파일이 변경 없이 통과해야 함 (별도 신규 작성 X)

### backend-dev (Green — sonnet)

- **수정 파일**: `src/engine/scheduler.py` 1개만
- Patch 1~4 (§4) 정확한 line 위치에 적용
- 자체 검증:
  ```bash
  python -m pytest tests/engine/test_scheduler_zombie_task_cleanup.py -v
  python -m pytest tests/engine/test_scheduler_shutdown_pool_cleanup.py -v  # 13-E
  python -m pytest tests/engine/test_scheduler_shutdown_review_fixes.py -v  # 13-E-1
  python -m pytest tests/engine/ -k scheduler -q
  ```
- 커밋 금지 — 메인 세션이 13-E-2 종료 시 일괄 정리

### tester (검증 — opus)

- 풀스위트 `pytest -q` 통과 확인
- 13-E + 13-E-1 + 13-E-2 cross-cycle 회귀 검증
- frontend `npm test` 영향 없음 (scheduler.py 단독 변경) — 영향 인덱스로 skip 검증
- E2E `playwright` 영향 없음 확인

---

## §9. 검수 체크리스트 (team-leader 최종 승인)

1. [ ] `self._ws_task` / `self._scan_task` 가 `__init__` 에서 None 초기화 되었는가
2. [ ] line 244 / 402 / 408 / 428 / 441 / 490 의 모든 `ws_task` / `scan_task` 참조가 `self.*` 화 되었는가 (정확한 grep 확인)
3. [ ] finally 루프 task_attr tuple 에 `_ws_task` / `_scan_task` 가 5종 뒤에 추가되어 **순서 = task cancel → main disconnect → pool stop** 보존되는가
4. [ ] Test J-1 ~ J-5 모두 Red → Green 사이클 통과 + Test K (13-E + 13-E-1) 회귀 0건
5. [ ] `_workspace/00_leader_trading_rules.md` 의 "WebSocket 다중 안전망" 절에 13-E-2 한 줄 추가 ("`start()` 본문 로컬 task 2종 self.* 승격으로 좀비 차단" 류)

---

## 다음 단계 — tdd-engineer 분배 메시지 초안

```
사이클 13-E-2 Red 단계.
명세: /home/user/auto_stock/_workspace/cycle13e2_zombie_task_spec.md §4 + §5 + §8

[작업]
1. tests/engine/test_scheduler_zombie_task_cleanup.py 신규 작성
2. Test J-1 ~ J-5 (5 케이스) — finally 블록이 self._ws_task / self._scan_task 도
   cancel + await 검증
3. mock 전략은 §8 tdd-engineer 항목 참조
4. 현재 코드 (scheduler.py 변경 전) 에서 모든 테스트가 FAIL 해야 함 (Red)
5. Test K 는 기존 13-E + 13-E-1 테스트 파일 재사용 — 신규 작성 X

[금기]
- scheduler.py 본 코드 수정 금지 (Green 은 backend-dev)
- ws_task / scan_task 생성 위치 자체 변경 금지
- 13-E + 13-E-1 finally 5종 task 처리 코드 변경 금지

완료 후 Red 사이클 결과 (테스트 파일 경로 + 실패 메시지) 보고.
```
