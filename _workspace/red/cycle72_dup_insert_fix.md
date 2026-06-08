# 사이클 72 Red 명세 — system_logs 이중 INSERT 시정

## 배경

사이클 71 운영 진단 결과:
- 09:00~09:25 system_logs 205 건 INSERT, distinct prefix 71 = **평균 2.89 x dup**
- 핵심 결함: 동일 메시지를 `logger.info(...)` + `await write_log(...)` 두 경로로 동시 emit
- `logger.info` → `_DbLogHandler.emit` → `ThreadPoolExecutor.submit(_insert_log_to_db)` (위임 경로)
- `await write_log` → `asyncio.to_thread(supabase.insert)` (직접 경로)
- 두 경로 모두 system_logs INSERT → **확정적 2건 INSERT**

## 11 사이트 (Phase 1-A 식별)

| # | 모듈                                | 라인       | prefix                               |
|---|------------------------------------|-----------|---------------------------------------|
| A1 | src/realtime/websocket.py         | 250-265   | `[ws_heartbeat]`                     |
| A2 | src/engine/stale_watcher_core.py  | 212-224   | `[stale_force_retry]`                |
| A3 | src/engine/stale_watcher_core.py  | 251-263   | `[stale_watcher]`                    |
| A4 | src/engine/stale_watcher_core.py  | 177-189   | `[stale_force_retry_cap]`            |
| A5 | src/engine/stale_watcher_core.py  | 384-397   | `[stale_priority_resubscribe]`       |
| A6 | src/engine/stale_diagnostics.py   | 178-191   | `[stale_watcher_detail]`             |
| A7 | src/engine/stale_session_recovery.py | 158-169 | `[silent_inactive_recovery_cap]`     |
| A8 | src/engine/stale_session_recovery.py | 192-203 | `[silent_inactive_force_reconnect]`  |
| A9 | src/engine/stale_session_recovery.py | 262-273 | `[scan_loop_delta]`                  |
| A10 | src/engine/stale_universe_guard.py | 138-155 | `[universe_excluded]`                |
| A11 | src/engine/scanner.py            | 1140-1155 | `[priority_drop]`                    |

## 시정 방향 (Green 단계 — backend-dev 수행)

**옵션 A' + D + AST 가드 (사용자 결정)**:
- A': 각 사이트에서 `logger.info/warning(...)` 만 유지 + `await write_log(...)` 호출 제거
  (logger 가 `_DbLogHandler` 위임으로 자동 INSERT → 단일 INSERT 경로)
- D: `_DbLogHandler.emit` 에 **500ms TTL dedupe 캐시** 도입 — 동일 메시지 중복 emit 차단
- AST 가드 G-6/G-7/G-8 — silent 결함 영속 차단

## Red 테스트 매트릭스 (17 케이스)

### G-A1 ~ G-A11 (각 사이트 1 케이스)

각 사이트의 모듈 소스를 정규식 분석:
- `await write_log(` 또는 `await _write_log(` 또는 `asyncio.create_task(_write_log(`
  prefix `[X]` 메시지에 대한 호출이 **0 건이어야 한다** (Green 검증).
- Red 단계 = 현재 모두 1+ 건 → FAIL.

### G-D1 ~ G-D3 (`_DbLogHandler` dedupe 캐시, freezegun)

- G-D1: 동일 메시지 100ms 내 두 번째 emit → `_insert_log_to_db` 호출 1 회 (두 번째 skip)
- G-D2: 동일 메시지 600ms 후 두 번째 emit → 호출 2 회 (TTL 경과 정상 INSERT)
- G-D3: 다른 메시지 동일 시간 → 둘 다 INSERT (메시지 키 dedupe 정확)

Red 단계 = `_DbLogHandler` 미구현 → 모두 FAIL.

### G-6 (AST 정적 가드 — `await write_log` ±5 줄 동시 logger 호출 0건)

`src/` 전체 rglob, 각 `write_log` 호출 사이트 ±5 줄에 동일 prefix `logger.info/warning(...)` 동시 호출 패턴 0 건.

Red 단계 = 11 사이트 잔존 → FAIL.

### G-7 (`_DbLogHandler` dedupe 캐시 구조 AST)

`src/main.py::_DbLogHandler.emit` 가 dict + `time.monotonic()` 비교 + 500ms TTL 상수 사용 정적 검증.

Red 단계 = 미구현 → FAIL.

### G-8 (`_insert_log_to_db` KST 영속, 사이클 65 H2-bis 보강)

`src/main.py:126` 의 `datetime.now(KST).isoformat()` 패턴 영속 + `+09:00` suffix 영속.

Red 단계 = 사이클 65 H2-bis 영속 → **PASS** (회귀 가드 강화).

## 안전 규칙

- Green 코드 작성 금지 (Red 단계 한정)
- CLAUDE.md "절대 깨지 말 것" 영속 — logging 영역 시정, 매도/WebSocket 4중 안전망 영향 0
- 사이클 67 분해 영속 (4 sub-module + facade), 사이클 68 KST 영속

## 산출물

- `tests/unit/engine/test_cycle72_no_duplicate_insert_per_site.py` (11 케이스, G-A1~G-A11)
- `tests/unit/main/test_cycle72_db_log_dedupe.py` (3 케이스, freezegun)
- `tests/unit/ast/test_cycle72_ast_no_logger_write_log_pair.py` (1 케이스, G-6)
- `tests/unit/main/test_cycle72_db_log_dedupe_structure_ast.py` (1 케이스, G-7)
- `tests/unit/main/test_cycle72_insert_log_kst_persistence_ast.py` (1 케이스, G-8)
