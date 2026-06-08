# 사이클 74 Red — WebSocket 로그 sampling/aggregation/rate cap

- 일자: 2026-06-08
- 단계: **Red (실패 테스트 작성 only — Green 코드 작성 금지)**
- 발주자: team-leader (Phase 1 + refactor-expert 자문 메모 `_workspace/refactor/cycle74_sampling_advisory.md`)
- 영속 의무: 사이클 17/24/29-R1/R2/R3/38/55 R-1/66/67/68/72/73 + CLAUDE.md 14 항목

## 채택 결정 매트릭스 (사용자 결정 → 본 Red 사양)

| 의제 | 사용자 결정 | Red 테스트 매트릭스 |
|------|------------|--------------------|
| R3 (전체 적용) | 채택 | 모든 영역 옵션 C / E-1 |
| 2-A `[swing_rest_poll]` | 옵션 C (5분 aggregation) | 파일 1 — 4 케이스 |
| 2-B `[stale_watcher]` | 옵션 C 조건부 (aggregation + 결함 시 individual) | 파일 2 — 5 케이스 |
| 2-C WS 구독/ACK/해제 | 옵션 E-1 (tr_id별 aggregation + ERROR individual 보존) | 파일 3 — 6 케이스 |
| X `[ws_heartbeat]` 5분 | 보존 (사이클 42 영속) | 사이클 42 영속 회귀 가드 영속 |
| Q2-D OPSP0002 | 옵션 A (aggregation 흡수) | 파일 3 G-WS5 |
| Q2-E `[ws_ack_orphan]` | 옵션 A (DEBUG 현행 유지) | 본 Red 비대상 (영속 유지) |
| Q3 collector 헬퍼 | 옵션 A (C-individual, 사이클 76+ #20 인계) | 본 Red 비대상 (사이클 76+ #20) |
| Q4 flush 주기 | 옵션 A (5분 영속) | 모든 freezegun 5분 윈도우 |
| Q5 마지막 flush | 옵션 A (disconnect/cancel 전 1회) | 모든 파일 마지막 케이스 |

## Red 테스트 매트릭스 — 5 파일 / 22 케이스

### 파일 1 — `tests/unit/engine/test_cycle74_swing_rest_poll_aggregation.py` (4 케이스)

| ID | 의도 | 검증 패턴 |
|----|------|----------|
| G-SP1 | 5분 윈도우 내 5회 poll → `[swing_rest_poll_summary]` 1행 (80% 감소) | freezegun + collector 인스턴스 검증 |
| G-SP2 | 윈도우 통계 정확 (polls/candidates_avg/max/total_held/elapsed_ms_avg) | 메시지 키워드 매칭 |
| G-SP3 | 윈도우 종료 직후 첫 poll 다시 5분 누적 | freezegun step (`+5min1s` 후 poll 1회) |
| G-SP4 | disconnect/cancel 시 잔존 윈도우 마지막 flush 1회 (Q5) | shutdown hook 호출 후 emit 1행 |

### 파일 2 — `tests/unit/engine/test_cycle74_stale_watcher_aggregation.py` (5 케이스)

| ID | 의도 | 검증 패턴 |
|----|------|----------|
| G-SW1 | 5분 내 30 check (120s × 30 simulated) → `[stale_watcher_summary]` 1행 | freezegun + collector |
| G-SW2 | 윈도우 통계 정확 (checks/stale_total/retried/cap_blocked/force_retried) | 메시지 키워드 매칭 |
| G-SW3 | stale_count > 0 시 individual `[stale_watcher_detail]` 보존 (사이클 73) | stale_diagnostics 분기 영속 |
| G-SW4 | `[stale_force_retry_cap]` WARNING individual 영속 (사이클 66 K-10) | cap 초과 시나리오 WARNING 1행 |
| G-SW5 | 윈도우 종료 시 마지막 flush | shutdown hook 호출 후 emit |

### 파일 3 — `tests/unit/realtime/test_cycle74_ws_action_aggregation.py` (6 케이스)

| ID | 의도 | 검증 패턴 |
|----|------|----------|
| G-WS1 | subscribe 6 + unsubscribe 6 → `[ws_action_summary]` 1행 | freezegun + _record_action |
| G-WS2 | 다중 tr_id (H0UNCNT0+H0STCNT0) 별도 aggregation | 2 row emit 검증 |
| G-WS3 | SUBSCRIBE SUCCESS ACK aggregation 흡수 | `_handle_raw` SUBSCRIBE SUCCESS 호출 → action=ACK |
| G-WS4 | `[ws_subscribe_reject]` ERROR individual 보존 (사이클 73 R-2) | 거절 응답 시 logger.error individual + aggregation 흡수 0 |
| G-WS5 | OPSP0002 ALREADY 흡수 (Q2-D 옵션 A) | `_record_action(..., "OPSP_ALREADY")` |
| G-WS6 | 윈도우 종료 시 마지막 flush + disconnect cancel *전* flush (Q5) | shutdown/disconnect hook 호출 후 emit |

### 파일 4 — `tests/unit/realtime/test_cycle74_error_preservation_matrix.py` (5 케이스)

| ID | 사이트 | 보존 의무 사이클 |
|----|-------|----------------|
| G-ERR1 | `[ws_subscribe_reject]` logger.error | 사이클 73 R-2 영속 |
| G-ERR2 | silent inactive force_reconnect | 사이클 24 / 29-R2 영속 |
| G-ERR3 | heartbeat timeout | 사이클 42 영속 |
| G-ERR4 | AES key error / `aes_key_skip` DEBUG | 사이클 16 영속 |
| G-ERR5 | `[ws_reverify]` WARNING | 사이클 73 R-1 영속 |

### 파일 5 — `tests/unit/ast/test_cycle74_ast_aggregator_helper.py` (2 케이스)

| ID | 의도 | 검출 패턴 |
|----|------|----------|
| G-7 | `_send_subscribe` 본문 `logger.info("WebSocket 구독/해제...")` 직접 호출 0건 (aggregator helper 의무) | AST AsyncFunctionDef + ast.Call.func.attr="info" |
| G-8 | `_run_swing_rest_poll_once` + stale_watcher 본문 `logger.info("[swing_rest_poll] ...")` / `logger.info("[stale_watcher] ...")` 직접 호출 0건 (aggregator helper 의무) | AST grep + 함수 isolation |

## Red 검증 의무 — 현재 (Green 전) 상태

| 파일 | 케이스 | 예상 결과 (Green 전) |
|------|--------|---------------------|
| 파일 1 | G-SP1~SP4 | **FAIL** (aggregator helper 미존재 — `_swing_rest_poll_collector` / `[swing_rest_poll_summary]` prefix 0) |
| 파일 2 | G-SW1, G-SW2, G-SW5 | **FAIL** (aggregator helper 미존재 — `_stale_watcher_collector` / `[stale_watcher_summary]` prefix 0) |
| 파일 2 | G-SW3 | **PASS** (사이클 73 stale_diagnostics 영속 영역 = 영구 가드) |
| 파일 2 | G-SW4 | **PASS** (사이클 66 K-10 영속 영역 = 영구 가드) |
| 파일 3 | G-WS1~WS3, G-WS5, G-WS6 | **FAIL** (`_record_action` / `_ws_action_collector` 미존재 + `[ws_action_summary]` prefix 0) |
| 파일 3 | G-WS4 | **PASS** (사이클 73 R-2 영속 영역 = 영구 가드) |
| 파일 4 | G-ERR1~ERR5 | **PASS** (사이클 16/24/29/42/72/73 영속 영역 = 영구 가드) |
| 파일 5 | G-7, G-8 | **FAIL** (직접 logger.info 호출 잔존 — aggregator helper 미존재) |

## flakiness 가드

- 3 회 반복 실행 = 모두 동일 결과 (사이클 60/64/65 패턴 답습)
- freezegun 사용 시 `tick=False` (auto-tick 비활성) → 결정론적 시간 경과

## 안전 규칙 영속 보장

| 안전 규칙 (CLAUDE.md) | 본 Red 영향 |
|----------------------|------------|
| 체결통보 H0STCNI0/9 구독 | **0** (테스트는 시세 영역만) |
| uvicorn 단일 워커 | **0** |
| 주문번호 매핑 / 체결통보 race 가드 | **0** |
| WebSocket 4중 안전망 (F1/_scan_loop/K stale watcher/_resubscribe_stale_priority) | **유지** (호출 시점/순서 무변경 + ERROR 보존 매트릭스 영속) |
| 사이클 17 KIS LMS chain 차단 (재SEND 0건) | **유지** |
| 사이클 29-R1/R2/R3 (force_retry / silent inactive / priority 분리) | **유지** |
| 사이클 38 명문화 (`tradable_boards` 매수 진입 전용) | **0** |
| 사이클 55 R-1 SellRejectionTracker | **0** |
| 사이클 66 cap=10 priority + K-10 WARNING | **유지** (G-SW4 영속 검증) |
| 사이클 67 stale_manager facade + 4 sub-module | **0** |
| 사이클 68 KST `src/db/_kst.py` | **0** |
| 사이클 72 `_DbLogHandler` dedupe + G-6 | **유지** (aggregation 흡수 후에도 dedupe 안전망 영속) |
| 사이클 73 R-1/R-2/S-1 + G-6.R/G-6.S | **유지** (G-WS4/ERR1/ERR5 영속 검증) |

## 산출물

- `tests/unit/engine/test_cycle74_swing_rest_poll_aggregation.py` (4 케이스)
- `tests/unit/engine/test_cycle74_stale_watcher_aggregation.py` (5 케이스)
- `tests/unit/realtime/test_cycle74_ws_action_aggregation.py` (6 케이스)
- `tests/unit/realtime/test_cycle74_error_preservation_matrix.py` (5 케이스)
- `tests/unit/ast/test_cycle74_ast_aggregator_helper.py` (2 케이스)
- `_workspace/red/cycle74_sampling.md` (본 파일)

총 **22 케이스 / 5 파일**.

## 다음 단계 (Green 발주)

- backend-dev 인계 시 aggregator helper 신규 도입 + 호출 사이트 정정 (옵션 E-1 패턴 답습)
- `_ws_action_collector` / `_swing_rest_poll_collector` / `_stale_watcher_collector` 인스턴스/모듈 변수
- flush 주기 5분 (사이클 42 답습) + lifecycle (connect/disconnect/cancel 직전 마지막 flush 1회)
- ERROR 보존 매트릭스 영속 (사이클 73 R-2 / 사이클 24 / 사이클 42 / 사이클 16 / 사이클 73 R-1)
- 사이클 76+ 카드 #20 collector 헬퍼 추출 (refactor-expert 권고)
