# 사이클 102 Phase 2 명세 분해 — 시세 구독 영역 전면 재검토 시정 (3 영역 통합)

**발주자**: team-leader (사이클 102 Phase 2)
**일시**: 2026-06-11 (목) KST
**위급도**: **HIGH** (시세 구독 영역 직접 영향 + 매매 안전성 영역 영속 의무)
**범위**: 3 영역 통합 단일 사이클 (영역 1 + 영역 2 + 영역 3)
**선행**: 사이클 102 domain-consult 자문 (`_workspace/cycle102_domain_consult.md`) + 사이클 88 G-REJECT 영구 영속
**코드 변경 (Phase 2)**: 0 (명세 단독)
**Phase 3 인계**: tdd-engineer Red 작성

---

## 1. 사용자 결정 요약 (영속)

| 의제 | 채택 | 영속 의무 |
|------|------|---------|
| **Q71** 사이클 102 발주 영역 | **A** = 사이클 78 silent 결함 의심 + 외부 의견 가시화 + force_retry 임계 상향 (3 영역 통합) | 단일 사이클 통합 영구 |
| **Q72** 외부 의견 채택 범위 | **F+가시화** = `last_ws_message_at` + dispatch + callback 가시화 | 사이클 88 G-REJECT-2 영속 + 보조 가시화 |
| **Q73** force_retry 임계 상향 | **B** = 5분 → 10분 + 12회 → 6회 | 사이클 29 R1 패턴 답습 (영역 폐기 0) |

---

## 2. 영역별 시정 명세

### 영역 1 — 사이클 78 silent 결함 의심 영구 확인 (HIGH 부차)

**결정적 발견 (domain-consult §A6 + 운영 실측)**:
- `[stale_watcher_summary]` **0건 / 7일** 영속 = 사이클 78 시정 영역 (`scheduler.py::_api_recovered_collector_loop` L2543~L2565) 배포 미검증 silent 결함 의심
- 사이클 78 commit (이미 배포) flush 4 줄 + lifecycle hook 양쪽 영속 영역 영구 확인 의무
- 코드 영역 결함 vs 배포 영역 결함 vs 운영 환경 영역 분리 결함 가설 3 분리 확인

#### 1-A 시정 명세 (영역 1)

**`src/engine/scheduler.py::_api_recovered_collector_loop`** (L2529~L2567) 영역:
- 사이클 78 영속 코드 영역 영구 확인 (변경 0 의무 — 영구 가드만 신설)
- `flush_swing_rest_poll_collector` (L2559) + `flush_stale_watcher_collector` (L2563) 호출 영속
- `if not self._running: break` 영역 *flush 이후* 위치 영속 (사이클 78 의도)

**`src/engine/scheduler.py::stop()`** (L923~L928 영역) 영역:
- `flush_swing_rest_poll_collector()` (L923) + `flush_stale_watcher_collector()` (L928) lifecycle hook 영속

#### 1-B 회귀 가드 명세 (영역 1, 5 케이스)

| 가드 | 위급도 | 영역 | 명세 |
|------|------|------|------|
| **G-78-VERIFY-1** | **HIGH** | `_api_recovered_collector_loop` body 영속 | `await asyncio.sleep(_API_RECOVERED_COLLECTOR_WINDOW)` *후* `flush_swing_rest_poll_collector` + `flush_stale_watcher_collector` 양쪽 호출 영속 (AST 정적) |
| **G-78-VERIFY-2** | **HIGH** | `stop()` lifecycle hook 영속 | `unsubscribe_all()` *전* `flush_swing_rest_poll_collector()` + `flush_stale_watcher_collector()` 양쪽 호출 영속 (AST 정적) |
| **G-78-VERIFY-3** | HIGH | 5분 주기 emit 정상 발화 | `record_stale_watcher_check(stats={"stale": 5})` *후* 5분 경과 (freezegun) → `flush_stale_watcher_collector()` 호출 시 `[stale_watcher_summary] checks=1 stale_total=5 ...` 1행 emit 영속 |
| **G-78-VERIFY-4** | MEDIUM | `if not self._running: break` 위치 영속 | `flush_*` 4 줄 *이후* 위치 영속 (사이클 78 의도, 마지막 1회 flush 보장) AST 정적 |
| **G-78-VERIFY-5** | MEDIUM | empty collector skip | `_stale_watcher_collector = []` 상태에서 `flush_stale_watcher_collector()` 호출 → emit 0 + collector 비어 있음 영속 (no-op) |

---

### 영역 2 — 외부 의견 가시화 신규 (HIGH, Q72=F+가시화)

**결정적 발견 (domain-consult §A2 + §A3)**: 사이클 88 G-REJECT-2 영구 차단 영속 + `last_ws_message_at` + dispatch 누락 + callback 예외 3 영역 운영 가시화 신규.

#### 2-A `_last_ws_message_at` 세션별 보조 가시화 (영역 2-A)

**`src/realtime/websocket.py`** 영역 명세:
- `KisWebSocket.__init__` 영역에 `_last_ws_message_at: dict[str, datetime] = {}` 인스턴스 변수 신규 (label → 마지막 메시지 수신 시각, 사이클 16 `_aes_iv` 인스턴스 변수 영속 패턴 답습)
- `_handle_raw` 진입 시 영속 update: `self._last_ws_message_at[self.label] = datetime.now(KST_TZ)` (사이클 68 KST 일관성 영속)
- `_heartbeat_metrics_loop` 5분 emit 영역에 `last_age=Ys` 보조 표시 (현재 `last_age` 영속 + `_last_ws_message_at` 기반 보조 검증)
- **사이클 88 G-REJECT-2 영구 영속**: 종목별 `ticker_last_tick` (판정 책임 영속) ↔ 세션별 `_last_ws_message_at` (보조 가시화) **책임 분리 영속**

#### 2-B dispatch 누락 silent_drop_count 가시화 (영역 2-B)

**`src/realtime/handler.py`** 영역 명세:
- `_handle_tick` (L89) 영역에 `if len(fields) < 10: return` *전* 시정 (line 96~97):
  - 모듈 전역 `_silent_drop_count: dict[str, int] = {}` (ticker → drop 횟수) 신규
  - 사이클 88 G-REJECT-2 영속 (종목별 영속 의무) 답습
- `_handle_tick` graceful drop 분기 (`len(fields) < 10` AND `parsed is None`) 양쪽에서 `_silent_drop_count[ticker] = _silent_drop_count.get(ticker, 0) + 1` (단, `len(fields) < 1` 시 ticker 추출 불가 → `"_unknown"` 사용)
- **`_flush_silent_drop_count()` 5분 주기**: `[dispatch_drop_summary] window=300s drops_total=N by_ticker={ticker:count, ...}` 1행 emit (사이클 74 collector 답습)
- scheduler `_api_recovered_collector_loop` 영역에 `from src.realtime.handler import flush_silent_drop_count` import 추가 + try/except 호출 추가 (사이클 78 패턴 답습)

#### 2-C callback 예외 [callback_exception] prefix 가시화 (영역 2-C)

**`src/realtime/handler.py`** 영역 명세:
- `_handle_tick` 영역 `_on_tick(...)` await 분기 (L111~112) try/except 영역 신규:
  ```python
  if _on_tick:
      try:
          await _on_tick(ticker, current_price, open_price, change_rate)
      except Exception:
          logger.exception("[callback_exception] handler=_on_tick ticker=%s", ticker)
          raise  # 재연결 trigger 영속 (사이클 88 G-REJECT-1 영속)
  ```
- **사이클 88 G-REJECT-1 영구 영속**: `_receive_loop` 정지 + 재연결 trigger 영속 보장 (`raise` 영속 의무)
- 동일 패턴 `_handle_execution` (`_on_execution`) + `_handle_market_op` (`_on_board`) 3 콜백 모두 적용 (silent 결함 영역 통일)

#### 2-D 회귀 가드 명세 (영역 2, 7 케이스)

| 가드 | 위급도 | 영역 | 명세 |
|------|------|------|------|
| **G-WS-MSG-1** | HIGH | `_last_ws_message_at` 세션별 update | `_handle_raw` 진입 시 `self._last_ws_message_at[self.label]` KST datetime update 영속 |
| **G-WS-MSG-2** | MEDIUM | `_heartbeat_metrics_loop` 5분 emit 영역에 `last_age` 영속 | 메인+보조 인스턴스별 독립 카운터 영속 + 사이클 42 5분 통계 영속 |
| **G-DISPATCH-1** | **HIGH** | `_silent_drop_count` ticker별 누적 | `_handle_tick(payload)` payload `len < 10` 또는 `parsed is None` 분기 진입 시 `_silent_drop_count[ticker]` 영속 +1 |
| **G-DISPATCH-2** | MEDIUM | `flush_silent_drop_count` 5분 emit | `_silent_drop_count = {"005930": 3, "000660": 1}` 상태에서 flush 호출 → `[dispatch_drop_summary] window=300s drops_total=4 by_ticker={...}` 1행 emit |
| **G-CALLBACK-1** | **HIGH** | `_on_tick` 예외 발생 시 raise (재연결 trigger 영속) | `_on_tick` 영역 raise Exception 시 `_handle_tick` 가 `[callback_exception] handler=_on_tick` ERROR + raise 영속 (사이클 88 G-REJECT-1) |
| **G-CALLBACK-2** | HIGH | 3 콜백 (`_on_tick` / `_on_execution` / `_on_board`) 일관 패턴 | 동일 try/except + logger.exception + raise 패턴 영속 (AST 정적) |
| **G-REJECT-PRESERVE-1** | **HIGH** | 사이클 88 G-REJECT-1/2/3 영속 보장 | `tests/unit/ast/test_external_llm_reject_patterns.py` 사이클 88 가드 영역 전수 PASS 영속 (영역 2 도입 후 회귀 0) |

---

### 영역 3 — force_retry 임계 상향 (HIGH, Q73=B)

**결정적 발견 (domain-consult §A6 운영 실측)**: `[stale_force_retry]` 124~141건/일 = 사이클 29 R1 정상 영역이나 *과도 영역* (LMS chain 안전 마진 증가 영역).

#### 3-A 시정 명세 (영역 3)

**`src/engine/stale_diagnostics.py`** (L30~L31) 영역:
```python
# 사이클 29 (2026-05-21) — 영구 stale 무한 skip → 시간 기반 강제 재시도 전환
# 사이클 102 (2026-06-11) Q73=B — 임계 상향 (LMS chain 안전 마진 증가)
STALE_FORCE_RETRY_AFTER_SECS = 600          # 영구 stale 의심 종목 최소 재시도 간격 (10분, 사이클 29 5분 → 사이클 102 10분)
STALE_FORCE_RETRY_HOURLY_CAP = 6            # 시간당 동일 종목 최대 재시도 횟수 (사이클 29 12회 → 사이클 102 6회, LMS / 앱키 정지 위험 차단)
```

**`src/engine/stale_watcher_core.py`** (L193 + L210) 영역:
- 상수 import 영역 영속 (L32~L33, 변경 0 = 상수 정의처 단일 SoT)
- 사용 영역 (L193 `if age_secs < STALE_FORCE_RETRY_AFTER_SECS` + L210 `if len(history) >= STALE_FORCE_RETRY_HOURLY_CAP`) 영속 (변경 0 = 상수 값만 변경)

#### 3-B 회귀 가드 명세 (영역 3, 5 케이스)

| 가드 | 위급도 | 영역 | 명세 |
|------|------|------|------|
| **G-FR-RAISE-1** | **HIGH** | 임계 상향 확정 | `STALE_FORCE_RETRY_AFTER_SECS == 600` 영속 (사이클 102 Q73=B) |
| **G-FR-RAISE-2** | **HIGH** | cap 상향 확정 | `STALE_FORCE_RETRY_HOURLY_CAP == 6` 영속 (사이클 102 Q73=B) |
| **G-FR-RAISE-3** | HIGH | 9분 미경과 skip (freezegun) | `_stale_last_resubscribe_at[ticker]` 시각 *후* 9분 경과 시 `check_and_resubscribe_stale` force_retry skip 영속 (사이클 29 R1 패턴 답습) |
| **G-FR-RAISE-4** | HIGH | 11분 경과 force_retry 영속 (freezegun) | 11분 경과 시 force_retry 발화 영속 |
| **G-FR-RAISE-5** | HIGH | 7회 cap 차단 freezegun | 60분 윈도우 내 6회 force_retry 후 7회째 `[stale_force_retry_cap]` WARNING + skip 영속 (사이클 66 K-10 WARNING 영속 답습) |

---

## 3. 회귀 가드 매트릭스 종합 (17 케이스)

| 영역 | HIGH | MEDIUM | LOW | 합계 |
|------|------|------|------|------|
| 영역 1 (사이클 78 영구 확인) | 3 | 2 | 0 | 5 |
| 영역 2 (외부 의견 가시화) | 5 | 2 | 0 | 7 |
| 영역 3 (force_retry 임계) | 5 | 0 | 0 | 5 |
| **합계** | **13** | **4** | **0** | **17** |

**HIGH 비율**: 13/17 = **76%** (사이클 66 36% / 사이클 67 35% 대비 HIGH 비율 영역 증가 = 영역 1+3 모두 안전성 직접 영역).

**xfail 의미 전환 영역**: 없음 (영역 모두 영속 의무, xfail 패턴 답습 불필요).

---

## 4. 영속 의무 매트릭스 (HIGH)

| 영속 영역 | 사이클 | 변경 0 보장 |
|---------|------|----------|
| **사이클 88 G-REJECT-1/2/3 영구 영속** | 사이클 88 | 영역 2 가시화 신규 도입 후 G-REJECT-PRESERVE-1 영속 |
| **사이클 17 OPSP0002 backoff 300s 영속** | 사이클 17 | 영역 3 force_retry 임계 상향과 영역 분리 (별도 분기, 변경 0) |
| **사이클 29 R1 시간 기반 force_retry 영속** | 사이클 29 | 영역 폐기 0, 임계만 상향 (5분→10분, 12회→6회) |
| **사이클 29 R2 silent_inactive 세션 단위 3중 가드 영속** | 사이클 29 | 영역 1+2+3 모두 영향 0 |
| **사이클 29 R3 HIGH/LOW 우선순위 분리 영속** | 사이클 29 | 영역 분리 (별도 분기, 변경 0) |
| **사이클 32 R4 universe guard 영속** | 사이클 32 | 영역 1+2+3 모두 영향 0 |
| **사이클 66 cap=10 priority 분리 영속** | 사이클 66 | 영역 분리 (별도 분기, 변경 0) |
| **사이클 67 stale_manager 4 sub-module 영속** | 사이클 67 | stale_diagnostics.py L30~L31 상수 영역만 변경 (행위 영역 0) |
| **사이클 78 G-AST1 flush 호출 사이트 영속** | 사이클 78 | **영역 1 = 영구 확인 의무** (G-78-VERIFY-1~5) |
| **사이클 79 G-AST2 task cancel 영속** | 사이클 79 | 영역 1+2+3 모두 영향 0 |
| **4중 안전망 영속 (F1 + scan_loop + K + priority)** | 사이클 17/25-B/29 R1+R3 | 영역 1+2+3 모두 영향 0 |
| **CLAUDE.md "절대 깨지 말 것" 8 영역 영속** | 영구 | 영역 1+2+3 모두 영향 0 |

---

## 5. tdd-engineer Red 인계 명세

### Phase 3 Red 작성 의무 매트릭스 (영역별)

**영역 1**: `tests/unit/engine/test_cycle102_area1_stale_summary_verify.py` 신규 5 케이스 (G-78-VERIFY-1~5).
- AST 영역 2 (G-78-VERIFY-1/2): `tests/unit/ast/test_cycle102_ast_flush_sites.py` 신규
- freezegun 영역 1 (G-78-VERIFY-3): `_API_RECOVERED_COLLECTOR_WINDOW` 5분 windows mock
- empty skip 영역 1 (G-78-VERIFY-5): collector clear + emit 0 검증

**영역 2**: `tests/unit/realtime/test_cycle102_area2_visualization.py` 신규 7 케이스 (G-WS-MSG-1/2 + G-DISPATCH-1/2 + G-CALLBACK-1/2 + G-REJECT-PRESERVE-1).
- AST 영역 2 (G-CALLBACK-2): `tests/unit/ast/test_cycle102_ast_callback_exception.py` 신규
- handler module 영역 4 (G-DISPATCH-1/2 + G-CALLBACK-1 + G-REJECT-PRESERVE-1)
- websocket module 영역 2 (G-WS-MSG-1/2)

**영역 3**: `tests/unit/engine/test_cycle102_area3_force_retry_threshold.py` 신규 5 케이스 (G-FR-RAISE-1~5).
- 상수 영역 2 (G-FR-RAISE-1/2): import + 값 검증
- freezegun 영역 3 (G-FR-RAISE-3/4/5): 9분/11분/cap freeze + skip/발화 검증

**합계**: 신규 6 파일 + 17 케이스 + AST 가드 3 신설.

---

## 6. 진행 가이드 (Phase 3 인계 핵심)

1. **사이클 78 영역 영구 확인 (영역 1)**: 코드 영역 검토 후 변경 0 의무 영역. 영구 가드만 신설 (G-78-VERIFY-1~5).
2. **외부 의견 가시화 (영역 2)**: 사이클 88 G-REJECT-2 영속 + 보조 가시화 영역 신규 도입. `_last_ws_message_at` 세션 + `_silent_drop_count` ticker + `[callback_exception]` 3 콜백 일관 패턴.
3. **force_retry 임계 상향 (영역 3)**: 사이클 29 R1 패턴 답습 (영역 폐기 0, 임계만 상향). `STALE_FORCE_RETRY_AFTER_SECS` 5분→10분 + `STALE_FORCE_RETRY_HOURLY_CAP` 12회→6회.

**영속 의무**:
- 사이클 88 G-REJECT-1/2/3 영구 영속 (양 agent 일치 결론)
- 4중 안전망 영속 (F1 + scan_loop + K + priority)
- CLAUDE.md "절대 깨지 말 것" 8 영역 영속
- 사이클 29 005935 사고 패턴 재현 영구 차단

**운영 효과 예상 (push 후 V-12 SQL 측정 의무)**:
- `[stale_watcher_summary]` 0건/7일 → 144건/day (5분 주기 정상 emit, 영역 1 영구 확인 결과)
- `[stale_force_retry]` 124~141건/일 → 50~70건/일 (영역 3 임계 상향 효과, LMS chain 안전 마진 증가)
- `[dispatch_drop_summary]` 신규 (영역 2-B) 0건 영역 영구 가시화
- `[callback_exception]` 신규 (영역 2-C) 0건 영역 영구 가시화 (재연결 trigger 영속)

---

## 7. 산출물 (영구 기록)

- 본 파일 (`_workspace/cycle102_phase2_design.md`) — Phase 2 명세 단독 영구 기록
- 선행 자문 영속: `_workspace/cycle102_domain_consult.md` (A1~A8 영구 보존)
- 외부 LLM 의견서 영속: `_workspace/external_llm_reviews/2026-06-09_realtime_review.md` (사이클 88 영속)
- Phase 3 Red 명세 인계: tdd-engineer 작성 의무 (`_workspace/red/cycle102_*.md` 신규 3 파일)

**Phase 2 종결 (코드 변경 0, 명세 단독)**.
