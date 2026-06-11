# 시세 구독 영역 전면 재검토 — 2026-06-11 (사이클 102)

> **사용자 명시**: "구독이 끊겼다는 판단으로 재구독 로직을 개발했던게 실수가 아닌가 싶어. 기존시스템에 개발해둔 로직이 아까워서 억지로 유지하려고 하지 말고 완전히 새로운 시각에서 판단하도록 해."
>
> **본 메모**: 검토 단독 (코드 변경 0). 사이클 88 G-REJECT 영구 차단 영역 재평가 + 외부 의견 객관 평가 + 권고 매트릭스 + 사용자 결정 의제.

---

## A. 시세 구독 영역 코드 정밀 검토 (READ-ONLY 정적 사실)

| 모듈 | 라인 | 책임 |
|------|-----|------|
| `src/realtime/websocket.py` | **736L** | 단일 세션 (connect/disconnect/restore/verify/heartbeat/action collector/auto_restart 사이클 92) |
| `src/realtime/websocket_pool.py` | **602L** | 멀티 세션 분배 + 우선순위 분리 + label 통일 |
| `src/realtime/handler.py` | 205L | 콜백 dispatch (`_on_tick` / `_on_execution` / `_on_board`) |
| `src/engine/stale_watcher_core.py` | **411L** | K stale watcher (`check_and_resubscribe_stale` + `resubscribe_stale_priority`) |
| `src/engine/stale_diagnostics.py` | 351L | CCNL 캐시 + force_retry prune + `[stale_watcher_detail]` |
| `src/engine/stale_session_recovery.py` | 253L | silent_inactive 3중 가드 + force_reconnect + delta_unsubscribe |
| `src/engine/stale_universe_guard.py` | 147L | 보유/익일청산 절대 보호 + 저거래량 unsubscribe |
| `src/engine/stale_tracker.py` | 82L | `StaleTrackerState` dataclass |
| `src/engine/stale_manager.py` | 96L | facade `__all__` 21 re-export only |

**라인 합산**: 시세 수신 = 1,543L (websocket + pool + handler). stale 복구 = 1,340L (4 sub-module + tracker + facade). **복구/수신 = 87%** (사이클 88 외부 LLM 92% 측정 영역 일관). 외부 의견 "복구 > 수신 폭증" 관찰 정합.

### dispatch 사이트 정밀 분석 (외부 의견 D 영역)

`handler.py::dispatch_message` (L64) → `_handle_tick/_handle_execution/_handle_market_op` 3분기 → 각 콜백 (`_on_tick/_on_execution/_on_board`) 호출 단순 chain. **`asyncio.Queue` / 적체 / 명시 retry / 백그라운드 dispatch task 0건** — websocket recv → handler dispatch → 콜백 모두 *동일 task 직렬*. 외부 의견 "queue 적체" 가설 = **현 구조 미해당** (queue 자체 없음).

### 예외 처리 매트릭스

- `websocket.py::_receive_loop` (L582): `asyncio.TimeoutError` (30s heartbeat) / `websockets.ConnectionClosed` → return → connect loop 재시도 (사이클 92 MAX 도달 시 auto_restart)
- `websocket.py::_handle_raw::_on_message` (L724-733): try/except Exception → `logger.exception` + 흡수 → **다음 메시지 수신 영속**
- `handler.py::_handle_execution` (L121-125): AES 복호화 실패 → `logger.exception` + return (시세는 비암호화로 무영향)
- `handler.py::dispatch_message` 자체 try/except 0 — 콜백 예외는 호출 측 (`_receive_loop`) 가 흡수

**dict overwrite / race condition 영역**: `ticker_last_tick[ticker] = now` (scanner L463) = `risk.on_tick` L81 단일 진입. 다중 세션이 같은 ticker tick 보내도 *마지막 값 단순 덮어쓰기* (의도 = "최신 tick 우선"). **race 자체는 손실이 아닌 *정상 행위*** — 외부 의견 "dict overwrite" 가설 = 현 구조에서 손실 영역 없음.

---

## B. 외부 의견 vs 현 영속 영역 정합 매트릭스

| 외부 의견 영역 | 현 영속 영역 | 정합 vs 충돌 | 평가 |
|------------|------------|----------|----|
| dispatch 누락 (콜백 미등록) | `register_*_handler` 모듈 전역 global 1회 등록 + None 가드 (L111/162/189) | 정합 | 결함 영역 미관찰 |
| callback 예외 (콜백 throw) | `_on_message` try/except + `logger.exception` 흡수 (L727) | 정합 | 다음 메시지 수신 영속 |
| queue 적체 | **현 구조 queue 미존재** (직렬 chain) | 미해당 | 가설 무용 |
| dict overwrite | `ticker_last_tick[ticker] = now` = *최신 tick 우선* 정상 행위 | 미해당 | 가설 무용 |
| race condition (ACK race) | 사이클 14-C orphan ACK 가드 (`_subscriptions` 정합성) + 사이클 32 R4 영속 | 정합 | 이미 답습 |
| `last_ws_message_at` (전체 메시지 시각) | **0 사이트 (미존재)** + 사이클 29 R2 세션 `fresh_ratio` 부분 답습 + 사이클 42 `_heartbeat_metrics` 송수신 통계 | **부분 충돌** | Q3 후속 카드 후보 |
| 종목별 4 영역 로그 (`ticker / session_id / subscribe_ack_time / last_tick_time / last_ws_message_at`) | 사이클 28 `[stale_watcher_detail] session=main sub=22/41 fresh=8 stale=14 ratio=0.64 stale=[(009150, r=3, @09:12:45), ...]` + `_stale_last_resubscribe_at` 영역 | 부분 정합 | `subscribe_ack_time` + `last_ws_message_at` 누락, Q4 후속 카드 후보 |
| OPSP0002 클라이언트-서버 불일치 | 사이클 17 backoff 300s + `_opsp_backoff_until` dict | 정합 | 영속 |
| 재연결 직후 일부 종목 누락 | F1 `_verify_subscriptions_after_reconnect` + K stale watcher 120s | 정합 | 영속 |

---

## C. 사이클 88 G-REJECT 영구 차단 영역 재평가 (HIGH 평가)

### G-REJECT-1 = 외부 의견 "재구독 로직 자체가 실수" 영역 직접 충돌

- **현 G-REJECT-1**: 4중 안전망 영속 (F1 + `_scan_loop` + K + priority) — `test_external_llm_reject_patterns.py::test_g_reject_1` 영구 가드
- **외부 의견**: "구독이 끊겼다는 판단으로 재구독 로직을 개발했던게 실수" → **재구독 로직 자체 폐기 의도**
- **충돌 평가 HIGH**: 사용자 명시 = "기존 로직 아까워서 억지로 유지 금지". 그러나 사이클 29 005935 사고 (T+0 stale → T+18min 8분 영구 잔류 + KIS LMS chain) 패턴 차단 의무.
- **재평가 결론**: 사이클 88 G-REJECT-1 = "4 함수 누적 분리" 보장. **단순 통합 차단 ≠ 재구독 폐기 차단**. 사용자 명시 의도 = "재구독 로직 폐기 검토" → 사이클 88 G-REJECT-1 와 *호환 가능*. **다만 폐기 시 사이클 29 사고 패턴 재발 위험 평가 의무**.

### G-REJECT-2 = 외부 의견 `last_ws_message_at` 도입 의도

- **현 G-REJECT-2**: 종목별 `ticker_last_tick` + `STALE_FRESHNESS_SECS` 영속 (외부 LLM R5 반려)
- **외부 의견**: "종목별 `last_tick_time` + 세션별 `last_ws_message_at` 비교"
- **충돌 평가 LOW**: 외부 의견 = **종목별 *유지* + 세션별 *보강*** = 사이클 88 영속 영역과 호환. *전체 메시지 단독 전환*이 아님.
- **재평가 결론**: G-REJECT-2 영속 + `last_ws_message_at` 도입 = **호환 가능**. Q3 후속 카드 후보.

### G-REJECT-3 = 외부 의견 SubscriptionRegistry 통합 의도

- **현 G-REJECT-3**: 4 dict 분리 영속 (`_subscriptions` / `_subscriptions_acked` / `_ticker_to_session` / `ticker_last_tick`)
- **외부 의견**: "통합 dict 의도" 일부 시사
- **충돌 평가 MEDIUM**: 4 dict 각각 책임 분리 (SEND/ACK/세션 분배/시세 수신) — 통합 시 orphan ACK race + KIS 41 한도 분배 가드 마비.
- **재평가 결론**: G-REJECT-3 영속 의무. read-only view 모듈 신설 (사이클 88 Q1 옵션 A) 권고 영속.

---

## D. dispatch 누락 / 예외 / 영역 정밀 검토

| 영역 | 사이트 | 보장 영역 |
|-----|-----|--------|
| 콜백 등록 누락 | `handler.py::register_*_handler` (L37/42/47) | None 가드 (L111/162/189) — silent skip |
| 콜백 예외 흡수 | `websocket.py::_handle_raw` L724-733 | `logger.exception` + 다음 메시지 수신 영속 |
| AES 복호화 실패 | `handler.py::_handle_execution` L121-125 | `logger.exception` + return + 시세 영향 0 |
| heartbeat timeout | `websocket.py::_receive_loop` L587-594 | `_heartbeat_timeout_count += 1` + reconnect |
| WS 연결 끊김 | `websocket.py::_receive_loop` L595-597 | reconnect (사이클 92 MAX 도달 시 auto_restart) |
| 재연결 max 도달 | `websocket.py::connect` L218-224 | `_trigger_auto_restart` (사이클 92, 60s cooldown + 시간당 3회 cap) |

**결정적 발견**: 외부 의견 가설 (dispatch 누락 / 예외 / queue 적체 / dict overwrite / race condition) 5 영역 중:
- **3 영역 (queue 적체 / dict overwrite / dispatch 누락) = 현 구조 미해당** (가설 무용)
- **2 영역 (callback 예외 / race condition) = 이미 답습** (try/except 흡수 + 사이클 14-C orphan ACK 가드)

**외부 의견 "70~80% 애플리케이션 버그" 추정 = 현 구조 영역 미관찰** — 객관 정량 측정 (Q4 운영 실증) 의무.

---

## E. `last_ws_message_at` 영역 영속 검증

- **`last_ws_message_at` 직접 grep**: 0 사이트 (미존재 확정)
- **등가 영역**: `ticker_last_tick` (종목별, 14 사이트) + 사이클 29 R2 `fresh_ratio = fresh / subscribed` (세션별 비율) + 사이클 42 `_pingpong_recv_count` / `_pingpong_last_at` (PINGPONG 송수신 통계, 5분 윈도우)
- **누락 영역**: *세션별 마지막 임의 메시지 수신 시각* — 사이클 88 시점 의도 부분 답습 (heartbeat metrics 인프라) 다만 *명시 시각 기록 0*.
- **도입 시 효과**: 종목별 stale + 세션별 silent 보강 시 *세션 수준 시각 기준* 추가 = 사이클 29 R2 3중 가드 (fresh_ratio + subscribed_count + 5분 지속) 에 4번째 가드 (`last_ws_message_at age > N` 추가) 가능.

---

## F. 재구독 로직 아키텍처 평가 (HIGH — 사용자 명시 의제)

### F-1. 사용자 명시 의도 해석

> "구독이 끊겼다는 판단으로 재구독 로직을 개발했던게 실수가 아닌가 싶어."

**해석 A (강해석)**: 재구독 로직 4 영역 전부 폐기 = G-REJECT-1 위반 = 사이클 29 005935 사고 재발 위험 HIGH. *반려 권고*.

**해석 B (중해석)**: 재구독 로직 *상태 판정 영역* (`ticker_last_tick` 기반 stale 판단) 폐기 + 단순 *전체 메시지 수신 시각 기반* 단일 보장 = 외부 의견 R5 = 사이클 88 G-REJECT-2 영속과 충돌. **종목 거래정지 미감지 위험** (예: 삼성전자 활성 + SK스퀘어 거래정지 시 세션 fresh_ratio 정상 → 종목 silent 미감지).

**해석 C (약해석)**: 재구독 로직 *과민반응 영역* (사이클 17 1~5회 즉시 재등록 / 사이클 29 R1 force_retry / 사이클 24 silent_inactive 강제 reconnect / 사이클 25-B priority resubscribe) 중 일부 폐기 + 단순 진단/로그 영역 강화. **호환 가능** — 사이클 88 G-REJECT-1 영속 + 발화 빈도 cap 강화.

### F-2. 정량 측정 의무 (Phase 3-A 채택)

사이클 74 영속 인프라 = `[stale_watcher_summary] checks=N stale_total=M retried=K cap_blocked=L force_retried=J` 5분 통계 + `[ws_action_summary] label=... SUBSCRIBE=N UNSUBSCRIBE=M ACK=K OPSP_ALREADY=L` 5분 통계 + `[ws_heartbeat] label=... pingpong_recv=N avg_interval=Xs heartbeat_timeout=Z` 5분 통계 = **운영 실증 측정 인프라 이미 영속**.

**측정 지표**:
- `stale_total / checks > 5%` → 과민 confirm
- `force_retried / stale_total > 30%` → 영구 stale 폭증
- `retried / stale_total > 50%` → 재구독 효과 측정
- `pingpong_recv / window_secs` → 세션 수신 빈도 정상 (11~14s 간격 vs 비정상 60s+)
- `heartbeat_timeout > 0` → 연결 불안정

**다음 영업일 (2026-06-12 금요일) 09:30~15:20 운영 후 Supabase MCP SQL 측정 의무**.

### F-3. 옵션 매트릭스

| 옵션 | 내용 | 회귀 위험 | 사이클 88 영속 | 권고 |
|------|----|-------|----------|----|
| **A** | 현 4 영역 영속 + 정량 측정만 (사이클 74 인프라 재사용) | LOW | 영속 | **추천** |
| **B** | 재구독 로직 1~5회 즉시 강제재등록 폐기 (KIS 정상 패턴 "신규 등록" 회의) + 6회 초과 force_retry 만 유지 | MEDIUM | G-REJECT-1 호환 (4 함수 영속) | 검토 가능 |
| **C** | silent_inactive 강제 reconnect (사이클 24) 폐기 + 세션별 자연 재연결 위임 | MEDIUM | G-REJECT-1 호환 (3 함수 영속) | 검토 가능 |
| **D** | priority resubscribe 5분 (사이클 25-B) 폐기 + scan_loop 단독 | HIGH | G-REJECT-1 위반 (3 함수 영속) | 반려 |
| **E** | 종목별 stale 판정 폐기 + 전체 메시지 단독 (외부 의견 R5) | HIGH | G-REJECT-2 위반 | 반려 |
| **F** | `last_ws_message_at` 도입 + 종목별 + 세션별 + 전체 3 계층 가드 | LOW | 호환 (영역 추가) | 검토 가능 |
| **G** | 4 영역 전부 폐기 (외부 의견 R4 단순 통합) | CRITICAL | G-REJECT-1 영구 위반 | **영구 차단** |

---

## G. 권고 영역 매트릭스 (시정 / 영속 / 폐기)

### G-1. 영속 영역 (변경 0)

- 사이클 88 G-REJECT-1/2/3 영구 차단 가드 = 영속 (외부 LLM R4/R5/R2 영구 반려)
- 사이클 29 R1/R2/R3 (종목 + 세션 + priority 분리) = 영속
- 사이클 32 R4 universe guard (보유/익일청산 절대 보호) = 영속
- 사이클 66 priority 분리 *후* cap = 영속
- 사이클 67 stale_manager 4 sub-module = 영속
- 사이클 74 5분 aggregation 인프라 = 영속 (정량 측정 인프라)
- 사이클 78 flush 호출 사이트 + AST G-AST1 = 영속
- 사이클 92 auto_restart cooldown + 시간당 3회 cap = 영속

### G-2. 카드 후보 (사용자 결정 의제)

| 카드 | 등급 | 의제 | 사이클 88 영속 | 선행 |
|-----|----|----|----------|----|
| **#R1** | HIGH | F-2 운영 실증 측정 (다음 영업일 2026-06-12 금요일 09:30~15:20) — `[stale_watcher_summary]` + `[ws_action_summary]` + `[ws_heartbeat]` Supabase MCP SQL 측정 후 정량 데이터 기반 재평가 | 호환 | 없음 (사이클 102 후속 사이클 103+) |
| **#R2** | MEDIUM | F-3 옵션 F 채택: `last_ws_message_at` 세션별 도입 (사이클 29 R2 4번째 가드 강화) + 사이클 88 외부 LLM 검토 #E1 (`subscription_registry.py` ~80L) 통합 | 호환 | #R1 측정 후 |
| **#R3** | LOW | 사이클 88 외부 LLM 검토 #E2 (4 계층 명명 매핑 docstring 보강) | 호환 | 사용자 결정 |
| **#R4 (반려)** | — | F-3 옵션 D/E/G = G-REJECT-1/2 영구 위반 | — | — |

### G-3. 폐기 영역 (사용자 결정 시)

옵션 B/C 채택 시:
- **B 채택**: 사이클 17 1~5회 즉시 강제재등록 폐기 (KIS 공식 답변 "기등록한 사항을 재등록하지 않도록" 정합) → `_check_and_resubscribe_stale` L256-272 영역 폐기 + 6회 초과 force_retry (5분 cooldown + 시간당 12회 cap) 단독 유지. 회귀 가드 = 사이클 29 R1 영속 (1~5회 강제재등록 사이트 0건 AST 가드 신설 의무).
- **C 채택**: 사이클 24 silent_inactive 강제 reconnect 폐기 → `stale_session_recovery.py::force_reconnect_session` 영역 폐기 + WS 자연 재연결 (heartbeat timeout 30s) 단독 위임. 회귀 가드 = 사이클 24 시간당 2회 cap 영속 AST.

**HIGH 위급도 (매매 hot path 직결)**: 옵션 B/C 채택 시 domain-expert 자문 의무 (보유/익일청산 영향 평가 + 사이클 29 005935 사고 재발 risk 평가).

---

## H. 사이클 88 G-REJECT 영속 vs 폐기 결정

| G-REJECT | 영속 vs 폐기 결정 | 사유 |
|---------|---------------|----|
| **G-REJECT-1** (4중 안전망) | **영속** | 사이클 29 005935 사고 패턴 차단 의무. 사용자 명시 "재구독 로직 폐기 검토" = 옵션 B/C 호환 (4 함수 중 일부 폐기 = 3 함수 영속 보장). 옵션 D/G = 영구 위반 |
| **G-REJECT-2** (종목별 stale `ticker_last_tick`) | **영속** | 종목 거래정지 미감지 위험. 외부 의견 = 종목별 *유지* + 세션별 *보강* (G-REJECT-2 호환). 옵션 F 채택 시 `last_ws_message_at` 추가 = 가드 강화 |
| **G-REJECT-3** (4 dict 분리) | **영속** | orphan ACK race + KIS 41 한도 분배 가드. 외부 의견 read-only view 모듈 (#E1) = 호환 |

---

## I. 사용자 결정 의제 (사이클 102 종결 + 사이클 103+ 인계)

### Q-사용자 1: F-3 옵션 매트릭스 채택 결정

- **A 추천**: 현 4 영역 영속 + 정량 측정 (사이클 74 인프라 재사용) — *권고 영역*
- **B**: 1~5회 즉시 강제재등록 폐기 + 6회 초과 force_retry 단독 — HIGH 위급도, domain-expert 자문 의무
- **C**: silent_inactive 강제 reconnect 폐기 + WS 자연 재연결 단독 — HIGH 위급도, domain-expert 자문 의무
- **F**: `last_ws_message_at` 도입 (사이클 29 R2 4번째 가드 강화) — MEDIUM, #R2 카드

### Q-사용자 2: #R1 운영 실증 측정 시점 결정

- 다음 영업일 = **2026-06-12 금요일 09:30~15:20**
- 측정 인프라 = 사이클 74 영속 (변경 0)
- 측정 후 정량 데이터 기반 사이클 103+ 옵션 채택

### Q-사용자 3: domain-expert 자문 의뢰 시점

- 옵션 B/C 채택 시 = 자문 의무
- 옵션 A/F 채택 시 = 자문 권고 (보유/익일청산 영향 0 명시 영역 외 추가 risk 평가)

### Q-사용자 4: 외부 LLM 의견서 카드 #E1/#E2/#E3 (사이클 88 영속) 처리

- **#E1** (`subscription_registry.py` read-only view ~80L) = 옵션 F 채택 시 흡수 가능 (단일 카드)
- **#E2** (4 계층 명명 docstring 보강) = LOW, 변경 0 영역, 채택 자유
- **#E3** (운영 실증 측정) = #R1 동일 영역 = 흡수

---

## J. 결론 요약

1. **현 구조 결함 영역 정량 측정 미실시 상태** — 외부 의견 "70~80% 애플리케이션 버그" 추정 = 사이클 74 인프라 (이미 영속) 로 실증 가능. 사이클 102 = 검토 단독, 정량 측정 = 사이클 103+ (운영 영업일 의무).
2. **사용자 명시 "재구독 로직 폐기 검토"** = 4 영역 전부 폐기 (옵션 D/G) = 사이클 88 G-REJECT-1 영구 위반 + 사이클 29 005935 사고 재발 위험. **반려 권고**. 일부 폐기 (옵션 B/C) = 사이클 88 G-REJECT-1 호환 + domain-expert 자문 의무.
3. **사이클 88 G-REJECT-2** = 외부 의견 `last_ws_message_at` 도입과 *호환* (종목별 유지 + 세션별 보강). 옵션 F 추가 검토 가능.
4. **사이클 88 G-REJECT-3** = SubscriptionRegistry 단일 통합 영구 차단. read-only view 모듈 (#E1) = 호환.
5. **권고 영역**: 옵션 A (현 영속 + 정량 측정) 우선 + #R1 (HIGH 다음 영업일 측정) + 측정 결과 기반 사이클 103+ 옵션 B/C/F 재평가.

---

## K. 인계 명세 (team-leader)

- **권고 영역**: 옵션 A (영속 + 정량 측정) — **사용자 결정 의제**: Q-사용자 1~4
- **HIGH 카드 #R1** (2026-06-12 운영 측정) — 사이클 74 인프라 재사용 (변경 0)
- **MEDIUM 카드 #R2** (옵션 F + #E1 통합) — 측정 후 채택
- **LOW 카드 #R3** (#E2 명명 docstring) — 채택 자유
- **반려 영역**: 옵션 D/E/G (G-REJECT-1/2 영구 위반)
- **domain-expert 자문 의무**: 옵션 B/C 채택 시
- **사이클 88 G-REJECT-1/2/3 영속 결정**: 전수 영속 (외부 의견과 호환 가능 영역 내 영속)
