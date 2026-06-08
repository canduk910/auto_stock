# 사이클 73 Red 명세 — WebSocket dup 핵심 영역 시정

## 사이클 정의

- **카드**: #19 (HIGH) WebSocket dup 핵심 영역 시정
- **분류**: 사이클 72 옵션 A' 시정 영역 확장 (사이클 72 hotfix 운영 효과 측정 결과 보강)
- **결정 (사용자)**:
  - 결정 1 = **C** (옵션 A' + G-6 AST 가드 영역 확장) = **12 사이클 연속 옵션 A 패턴 영속**
  - 결정 2 = **G-6.전체** (`src/realtime/` + `src/engine/scheduler.py::_run_swing_rest_poll_once` 영역 한정)
  - 결정 3 = auth 1.43x 별개 사이클 74+ 카드 인계

## 배경 — 사이클 72 hotfix 운영 효과 측정 (배포 후)

- 사이클 72 hotfix 11 사이트 시정 직후 **dup_factor 3.72 → 1.34 (64% 감소)**
- 잔존 1.34 = 사이클 72 매트릭스 누락 3 사이트:
  - **R-1** `src/realtime/websocket.py:380-393` `[ws_reverify]` (`logger.warning` L380 multi-line + `await write_log("WARNING", ...)` L386)
  - **R-2** `src/realtime/websocket.py:512-529` `[ws_subscribe_reject]` (`logger.error` L512 multi-line + `await write_log("ERROR", ...)` L523)
  - **S-1** `src/engine/scheduler.py::_run_swing_rest_poll_once` L2319 `logger.info` multi-line + L2325 `await write_log("INFO", ...)` (60s 폴링 350회/일 emit hot path)
- 시정 후 예상 dup_factor → ~1.00 (단일 INSERT 정합성 완성)

## Red 테스트 매트릭스 (7 케이스)

### G-RT1: R-1 `[ws_reverify]` 사이트 write_log 호출 0건 (1 케이스)

- 파일: `tests/unit/realtime/test_cycle73_ws_reverify_no_write_log.py`
- 함수: `test_g_rt1_ws_reverify_site_no_write_log_call`
- 검증: `src/realtime/websocket.py` 본체 `[ws_reverify]` 사이트 (±5 줄 윈도우) `write_log(` 호출 0건
- Red: FAIL (L386 `await write_log(` 잔존)
- Green: PASS (시정 후 0건)

### G-RT2: R-2 `[ws_subscribe_reject]` 사이트 write_log 호출 0건 (1 케이스)

- 파일: `tests/unit/realtime/test_cycle73_ws_subscribe_reject_no_write_log.py`
- 함수: `test_g_rt2_ws_subscribe_reject_site_no_write_log_call`
- 검증: 동일 방식 (`[ws_subscribe_reject]` 사이트 write_log 호출 0건)
- Red: FAIL (L523 `await write_log(` 잔존)
- Green: PASS (시정 후 0건)

### G-SCH1: S-1 `_run_swing_rest_poll_once` 사이트 write_log 호출 0건 (1 케이스)

- 파일: `tests/unit/engine/test_cycle73_swing_rest_poll_no_write_log.py`
- 함수: `test_g_sch1_swing_rest_poll_once_no_write_log_call`
- 검증: AST `_extract_function_lines` 로 `_run_swing_rest_poll_once` 라인 범위 추출 → 함수 본체 write_log 호출 0건
- Red: FAIL (L2325 `await write_log(` 잔존)
- Green: PASS (시정 후 0건)

### G-6.R: AST 영구 가드 (src/realtime/ 영역, 1 케이스)

- 파일: `tests/unit/ast/test_cycle73_ast_realtime_no_logger_write_log_pair.py`
- 함수: `test_g_6_r_no_logger_write_log_pair_in_realtime`
- 검증: `src/realtime/` 전수 rglob → 각 `write_log` 호출 **±10 줄** 윈도우 동시 `logger.*` 호출 + 동일 prefix 검출 (사이클 72 ±5 줄 보강 — multi-line logger 호출 흡수)
- Red: FAIL (R-1 검출 — R-2 는 `[ws_subscribe_reject]` 가 logger.error 메시지 라인에 없어 미검출 = false-negative 한계, G-RT2 가 직접 가드)
- Green: PASS (R-1 시정 후)

### G-6.S: AST 영구 가드 (scheduler.py::_run_swing_rest_poll_once 함수 영역, 1 케이스)

- 파일: `tests/unit/ast/test_cycle73_ast_swing_rest_poll_no_logger_write_log_pair.py`
- 함수: `test_g_6_s_no_logger_write_log_pair_in_swing_rest_poll_once`
- 검증: AST 함수 영역 한정 ±10 줄 윈도우 + multi-line logger 7줄 흡수 → 동일 prefix 동시 호출 0건
- Red: FAIL (L2325 검출, prefix=`swing_rest_poll`)
- Green: PASS (시정 후 0건)

### G-72.E: 사이클 72 영역 영속 (기존 파일)

- 파일: `tests/unit/ast/test_cycle72_ast_no_logger_write_log_pair.py` (기존)
- 함수: `test_g_6_no_logger_write_log_pair_within_5_lines`
- 검증: 사이클 72 11 사이트 시정 영속 (회귀 0)
- Red 시점: PASS (사이클 72 영역 영속)
- Green 시점: PASS (사이클 73 영역 시정으로 영향 0, 사이클 72 가드 영속)

### G-RT3: logger 영속 보장 (2 케이스)

- 파일: `tests/unit/realtime/test_cycle73_logger_persistence.py`
- 함수:
  - `test_g_rt3_a_ws_reverify_logger_warning_persistence` — `[ws_reverify]` 사이트 `logger.warning` 호출 영속
  - `test_g_rt3_b_ws_subscribe_reject_logger_error_persistence` — `[ws_subscribe_reject]` 사이트 `logger.error` 호출 영속
- 검증 의도: 시정 과정에서 실수로 logger.* 까지 제거 시 운영 가시화 (stdout/file/DB 3중 보존) 무력화 영구 차단
- Red 시점: PASS (현재 logger 호출 존재)
- Green 시점: PASS (시정 후에도 logger 호출 영속, write_log 만 제거)

## Red 검증 결과

```
collected 7 items
tests/unit/realtime/test_cycle73_ws_reverify_no_write_log.py::test_g_rt1_ws_reverify_site_no_write_log_call FAILED
tests/unit/realtime/test_cycle73_ws_subscribe_reject_no_write_log.py::test_g_rt2_ws_subscribe_reject_site_no_write_log_call FAILED
tests/unit/engine/test_cycle73_swing_rest_poll_no_write_log.py::test_g_sch1_swing_rest_poll_once_no_write_log_call FAILED
tests/unit/ast/test_cycle73_ast_realtime_no_logger_write_log_pair.py::test_g_6_r_no_logger_write_log_pair_in_realtime FAILED
tests/unit/ast/test_cycle73_ast_swing_rest_poll_no_logger_write_log_pair.py::test_g_6_s_no_logger_write_log_pair_in_swing_rest_poll_once FAILED
tests/unit/realtime/test_cycle73_logger_persistence.py::test_g_rt3_a_ws_reverify_logger_warning_persistence PASSED
tests/unit/realtime/test_cycle73_logger_persistence.py::test_g_rt3_b_ws_subscribe_reject_logger_error_persistence PASSED

=== 5 failed, 2 passed in 0.05s ===
```

### flakiness 3 회 반복

```
Run 1: 5 failed, 2 passed in 0.04s
Run 2: 5 failed, 2 passed in 0.04s
Run 3: 5 failed, 2 passed in 0.03s
```

**flakiness 0 (3 회 동일 결과)**.

### G-72.E (사이클 72 영역 영속) 별도 확인

```
tests/unit/ast/test_cycle72_ast_no_logger_write_log_pair.py::test_g_6_no_logger_write_log_pair_within_5_lines PASSED
1 passed in 0.03s
```

## Green 단계 안내 (backend-dev 인계)

### R-1 시정 (`src/realtime/websocket.py:385-393`)

```python
# 시정 전 (R-1)
            try:
                await write_log(
                    "WARNING",
                    f"[ws_reverify] reconnect_count={self._reconnect_count} "
                    f"stale={len(stale)}/{len(subscribed)} preview={preview}",
                )
            except Exception:
                # fire-and-forget — write_log 실패해도 재구독 흐름 보존
                logger.debug("[ws_reverify] write_log 실패", exc_info=True)

# 시정 후 (logger.warning L380~L384 단독 유지 — _DbLogHandler 위임 단일 INSERT)
# (try/except + await write_log 블록 9 줄 전체 제거)
```

### R-2 시정 (`src/realtime/websocket.py:520-529`)

```python
# 시정 전 (R-2)
                    # 운영 trace 영구 저장 — Phase A1 [kis_rejection] 패턴 차용.
                    # fire-and-forget: write_log 실패해도 본래 흐름 보존 (정합성 회복 우선).
                    try:
                        await write_log(
                            "ERROR",
                            f"[ws_subscribe_reject] tr_id={tr_id} tr_key={tr_key} "
                            f"rt_cd={rt_cd} msg_cd={msg_cd} msg1={msg1}",
                        )
                    except Exception:
                        pass

# 시정 후 (logger.error L512~L515 단독 유지 — _subscriptions.discard 정합성 회복 영속)
# (try/except + await write_log 블록 10 줄 전체 제거)
# 메시지 prefix [ws_subscribe_reject] 를 logger.error 메시지에 명시적으로 포함 의무
# (현재 logger.error 메시지에 prefix 누락 — Green 단계 시 prefix 추가 필수)
```

### S-1 시정 (`src/engine/scheduler.py:2324-2333`)

```python
# 시정 전 (S-1)
        try:
            await write_log(
                "INFO",
                f"[swing_rest_poll] candidates={stats['candidates']} held={stats['held']} "
                f"pending={stats['pending']} updated={stats['updated']} failed={stats['failed']} "
                f"elapsed_ms={stats['elapsed_ms']}",
            )
        except Exception:
            # system_logs 실패는 swallow — 본체 흐름 보존
            pass

# 시정 후 (logger.info L2319~L2323 단독 유지 — _DbLogHandler 위임 단일 INSERT)
# (try/except + await write_log 블록 10 줄 전체 제거)
```

### Green 단계 검증 명령

```bash
python -m pytest tests/unit/realtime/test_cycle73_*.py tests/unit/engine/test_cycle73_*.py tests/unit/ast/test_cycle73_*.py tests/unit/ast/test_cycle72_*.py -v --tb=short
# 예상: 8 passed (G-RT1 + G-RT2 + G-SCH1 + G-6.R + G-6.S + G-RT3-A + G-RT3-B + G-72.E)
```

## 안전 규칙 영속 보장

- **WebSocket 4중 안전망 영속** — F1 (재연결 1회) + `_scan_loop` (5분) + K stale watcher (120s) + `_resubscribe_stale_priority` (5분 우선) 모두 호출 시점/횟수 변경 0
- **KIS LMS/앱키 정지 chain 차단 영속** — 본 사이클은 logging 영역 시정만 (WS subscribe/unsubscribe 호출 0)
- **사이클 38 명문화 영속** — `tradable_boards` 매수 진입 전용 보존 (매도/익일청산 영향 0)
- **사이클 72 hotfix 영속** — `_DbLogHandler` 500ms TTL dedupe 캐시 + G-6 AST 영속

## 산출물 경로 (절대 경로)

- `/Users/koscom/Projects/auto_stock/tests/unit/realtime/test_cycle73_ws_reverify_no_write_log.py` (1 케이스, G-RT1)
- `/Users/koscom/Projects/auto_stock/tests/unit/realtime/test_cycle73_ws_subscribe_reject_no_write_log.py` (1 케이스, G-RT2)
- `/Users/koscom/Projects/auto_stock/tests/unit/engine/test_cycle73_swing_rest_poll_no_write_log.py` (1 케이스, G-SCH1)
- `/Users/koscom/Projects/auto_stock/tests/unit/ast/test_cycle73_ast_realtime_no_logger_write_log_pair.py` (1 케이스, G-6.R)
- `/Users/koscom/Projects/auto_stock/tests/unit/ast/test_cycle73_ast_swing_rest_poll_no_logger_write_log_pair.py` (1 케이스, G-6.S)
- `/Users/koscom/Projects/auto_stock/tests/unit/realtime/test_cycle73_logger_persistence.py` (2 케이스, G-RT3)
- `/Users/koscom/Projects/auto_stock/tests/unit/ast/test_cycle72_ast_no_logger_write_log_pair.py` (기존, G-72.E 영속 보장)
- `/Users/koscom/Projects/auto_stock/_workspace/red/cycle73_ws_dup_fix.md` (본 Red 명세)

## 결정 사항 영속

- **12 사이클 연속 옵션 A 패턴 영속** (사이클 55 R-1 / 60 / 62 / 63 / 64 / 65 / 66 / 67 / 71 / 72 / 73)
- **G-6 AST 가드 영역 확장 패턴** — 사이클 72 (`src/` 전체 ±5 줄) → 사이클 73 (`src/realtime/` + 함수 영역 한정 ±10 줄 + multi-line 7줄 흡수)
- **결정 3 = auth 1.43x 별개 사이클 74+ 카드 인계**

## 운영 검증 의무 (Green 단계 후)

- 배포 후 24h 운영 monitoring → dup_factor 1.34 → ~1.00 검증
- `system_logs` `[ws_reverify]` / `[ws_subscribe_reject]` / `[swing_rest_poll]` 3 prefix 단일 INSERT 정합성 확인
- 운영 가시화 (stdout/file logger.* 출력) 영속 확인 (write_log 제거로 인한 정보 손실 0)
