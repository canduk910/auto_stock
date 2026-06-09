# 외부 LLM 의견서 검토 — 2026-06-09

> **목적**: 타 LLM 이 제출한 "시세 수신 오류 + 구조 단순화" 관점 의견서의 *객관성* 평가 + *현 프로젝트 영속 패턴* 과의 충돌 식별. 본 메모는 검토 단독 (코드 변경 0).

## 0. 외부 의견 verbatim

> **총평**: "시세를 받기 위한 기능보다 시세를 복구하기 위한 기능이 더 많아진 상태" = 복구 기능 폭증.
>
> **원인 가능성 추정**: stale_watcher 과민반응 40% / 상태 불일치 25% / reconnect 복구 루프 꼬임 20% / Pool 구조 10% / 실제 WS 장애 5%.
>
> **추천 4 계층 구조**: `RealtimeManager → SubscriptionRegistry → EventDispatcher → StrategyEngine`.
>
> **stale 판단 개선**: 종목별 `ticker_last_tick` → 전체 `last_ws_message_at` 기준 전환.
>
> **코드 정리 우선순위**: (1) stale watcher 재검토 (2) subscription 상태 통합 (3) WS 책임 축소 (4) 복구 로직 단일화 (`restore`/`reverify`/`stale_recovery` → 하나).

---

## Phase 1 — 현 영속 영역 식별 (READ-ONLY 정적 grep)

### 1-A. 모듈 라인 수 사실 (정적 측정)

| 모듈 | 라인 | 책임 |
|------|-----|------|
| `src/realtime/websocket.py` | **653L** | 단일 세션: connect/disconnect/subscribe/restore/reverify/heartbeat/action collector |
| `src/realtime/websocket_pool.py` | **602L** | 멀티 세션 분배 (메인 + quote-1/2/3) + 우선순위 분리 |
| `src/realtime/handler.py` | 205L | 콜백 dispatch (EventDispatcher 역할 *이미* 분리됨) |
| `src/engine/stale_watcher_core.py` | **411L** | K stale watcher 본체 + priority resubscribe |
| `src/engine/stale_diagnostics.py` | 351L | CCNL 캐시 + force_retry prune + 진단 |
| `src/engine/stale_session_recovery.py` | 253L | silent_inactive + force_reconnect + delta_unsubscribe |
| `src/engine/stale_universe_guard.py` | 147L | 보유/익일청산 절대 보호 + 저거래량 unsubscribe |
| `src/engine/stale_tracker.py` | 82L | `ticker_last_tick` 데이터클래스 |
| `src/engine/stale_manager.py` | 96L | facade re-export only |
| `src/engine/scheduler.py` | 3162L | (참고) |

**관찰**: stale 영역 합 = 1,340L (4 sub-module + tracker + facade). websocket 영역 합 = 1,460L (단일 세션 + pool + handler). **외부 의견 "복구 > 수신" 비율 = 1,340 / 1,460 ≈ 92%**. 객관 사실로 *근접 정합* (총평 부분 동의).

### 1-B. 상태 객체 분포 (정적 grep)

`_subscriptions / _subscriptions_acked / _ticker_to_session / ticker_last_tick / stale_retry_count / _opsp_backoff_until` 참조:

| 모듈 | 참조 횟수 |
|------|---------|
| `websocket_pool.py` | 40 |
| `websocket.py` | 40 |
| `stale_diagnostics.py` | 9 |
| `stale_watcher_core.py` | 8 |
| `stale_session_recovery.py` | 3 |
| `stale_universe_guard.py` | 2 |
| `stale_tracker.py` | 1 |

**관찰**: 상태 객체는 **websocket 영역에 80, stale 영역에 23 분포**. websocket_pool 의 `_subscriptions / _subscriptions_acked` 는 사이클 32 R4 ACK 정합성 가드 (orphan ACK race 차단) + websocket_pool L565~591 property 패턴으로 *세션별 → 풀 합집합* 노출. **외부 추천 "SubscriptionRegistry 단일 관리" = 이미 부분 답습** (property 패턴으로 단일 view 제공, 다만 source-of-truth 가 세션별 분산).

### 1-C. 복구 함수 분포 (정적 grep)

`restore / reverify / silent_inactive / force_reconnect` 사이트:
- `websocket.py:397` `_restore_subscriptions_after_reconnect` (F1 안전망)
- `websocket.py:409` `_verify_subscriptions_after_reconnect` (재연결 후 검증)
- `stale_session_recovery.py` `_detect_silent_inactive_sessions` + `_force_reconnect_session` + `_delta_unsubscribe_dropped`
- `stale_watcher_core.py` `_check_and_resubscribe_stale` + `_resubscribe_stale_priority`

**관찰**: **4 종 복구 사이트 = 6 함수**. 외부 추천 "단일 restore" 는 4 영역의 *발화 조건 자체가 다름* (재연결 후 / 종목별 stale / 세션 silent / 우선순위 5분 주기) 을 단일 함수로 흡수하면 발화 조건 식별 정밀도 손실. **단순화 == 가시성 손실** 트레이드오프 존재.

### 1-D. stale 판단 시간 소스 (정적 grep)

`ticker_last_tick` 참조 = 14 사이트 / `last_ws_message_at` 참조 = **0 사이트** (미존재).

**관찰**: 현 시스템은 **종목별 stale 판단 단독** (외부 의견 정확). 다만 사이클 29 R2 silent_inactive 는 *세션별 fresh_ratio* (전체 메시지 비율) 로 보강 = **세션 수준 전체 메시지 기준 부분 답습**. 사이클 42 `_heartbeat_metrics_emit_once` (5분 주기) 는 송수신 빈도 측정 = **전체 메시지 기준 측정 인프라 존재**.

---

## Phase 2 — 영속 패턴 vs 외부 추천 충돌 매트릭스

| 외부 추천 | 현 영속 영역 | 충돌 평가 | 등급 |
|----------|-------------|----------|------|
| **R1. RealtimeManager 단일 (연결/재연결/heartbeat)** | `websocket_pool.start/stop/select_session` + `websocket.connect/disconnect/_heartbeat_metrics_emit_once` 이미 분리 | 부분 답습, 다만 "연결" 영역 = 멀티 세션 분배 책임 분리 영속 의무 (사이클 43 라벨 통일) | LOW 충돌 |
| **R2. SubscriptionRegistry 단일** | `websocket_pool` property 4종 (`_subscriptions / _subscriptions_acked / get_subscriptions_by_session / get_session_status`) 단일 view 제공. 사이클 29 R3 priority 분리 + 사이클 32 R4 universe guard 보유/익일청산 절대 보호 | 단일 source 전환 시 priority 분리 / 보호 영역 / orphan ACK race 가드 보존 의무 | **MEDIUM** 충돌 |
| **R3. EventDispatcher 분리** | `handler.py` 205L 이미 dispatch 책임 분리 | **이미 답습** | 0 충돌 |
| **R4. 복구 로직 단일화 (restore 하나)** | F1 재연결 / K stale watcher 종목별 / silent_inactive 세션별 / priority resubscribe 5분 = **CLAUDE.md "WebSocket 4중 안전망" 영속 의무** | 단일화 = "절대 깨지 말 것" 영역 위반 (4중 안전망 → 1중) | **HIGH** 충돌 = 반려 |
| **R5. stale 판단 = 전체 메시지 기준** | 종목별 `ticker_last_tick` 단독 (14 사이트) + 사이클 29 R2 세션 fresh_ratio 보강 | 종목별 판단 폐기 시 *특정 종목 거래 정지/품절* 미감지 (시세 전체는 흐르나 해당 종목만 stale) | **HIGH** 충돌 = 종목별 영속 + 전체 메시지 *보조* 가산 권고 |
| **R6. stale_watcher 과민반응 (외부 추정 40%)** | 사이클 29 R1 시간당 12회 cap + 사이클 66 priority cap=10 시정 + 사이클 67 4 sub-module 분할 + 사이클 74 5분 aggregation | **이미 답습** 다층 시정 누적. 운영 측정 (사이클 74 `[stale_watcher_summary]`) 으로 과민반응 정량 측정 가능 | LOW 충돌 |
| **R7. 4 계층 구조 (RM / SR / ED / SE)** | 현 구조 = `WebsocketPool → KisWebSocket(N) → handler.py → risk.on_tick` = 4 계층 *이미 답습* (다만 명명 다름) | 명명 통일 권고 가능, 구조 자체는 정합 | LOW 충돌 = 명명 정리 카드 후보 |

---

## Phase 3 — 검증 가능 영역 분류

| 외부 가설 | 분류 | 검증 방법 |
|----------|-----|----------|
| stale_watcher 과민반응 40% | **A** (Supabase READ-ONLY) | `[stale_watcher_summary] checks=N stale_total=M retried=K` 5분 통계 (사이클 74) — `stale_total/checks` 비율 측정. >5% 이면 과민 confirm |
| 상태 불일치 25% | **B** (정적 grep) | `_subscriptions vs _subscriptions_acked` 차집합 = orphan ACK race 영역. 사이클 32 R4 가드 영속으로 차단 중. 운영 `[ws_subscribe_reject]` 빈도 측정 |
| reconnect 루프 꼬임 20% | **A** | `_force_reconnect_session` 호출 빈도 (사이클 74 collector). 시간당 세션당 2회 cap 초과 시 confirm |
| Pool 구조 10% | **D** (미검증 추정) | 사이클 43 라벨 통일 + 사이클 67 분할로 가시성 확보, 정량 측정 미비 |
| 실제 WS 장애 5% | **A** | `[ws_heartbeat]` heartbeat_timeout_count 5분 통계 |

**결정적 발견**: 외부 의견 *원인 확률 추정* 은 정량 측정 인프라 **이미 존재** (사이클 42/74). 추정 → 실증 전환 가능.

---

## Phase 4 — 권고 분류 (사용자 결정 의제)

### Q1 — R2 SubscriptionRegistry 통합 (MEDIUM 충돌)
- **옵션 A (수정 권고)**: 현 property 패턴 영속 + 신규 모듈 `src/realtime/subscription_registry.py` (read-only view + priority/protection 메타데이터 통합 노출). source-of-truth 는 세션별 영속 (orphan ACK race 가드 + 사이클 32 R4 보호 영속). 사용자 결정 요청.
- **옵션 B (반려)**: 현 구조 유지, 명명만 docstring 보강.

### Q2 — R4 복구 단일화 (HIGH 충돌)
- **반려 권고 확정**: CLAUDE.md "WebSocket 4중 안전망" 영속 의무 (사이클 29 R1/R2/R3 + 사이클 32 R4 누적 시정). 단일화 = 영구 차단 사항. 외부 의견 *발화 조건 차이 미인지* 결함.

### Q3 — R5 stale 판단 전환 (HIGH 충돌)
- **옵션 A (수정 권고)**: 종목별 `ticker_last_tick` **영속** + `last_ws_message_at` 세션 수준 보조 가산 (현 `_heartbeat_metrics` 재사용). 사이클 29 R2 `fresh_ratio` 이미 부분 답습 → 명문화. domain-expert 자문 의무 (보유/익일청산 영향 평가).
- **옵션 B (반려)**: 외부 추천 그대로 전환 = 종목 거래 정지 미감지 위험 → 반려.

### Q4 — R6 stale_watcher 과민반응 실증
- **옵션 A (Phase 3-A 채택)**: 다음 영업일 (2026-06-09 월요일) 09:30~15:20 운영 후 Supabase MCP `[stale_watcher_summary]` SQL 측정. `stale_total/checks > 5%` 이면 과민 confirm + 후속 카드 발의. 측정 후 결정.

### Q5 — R7 4 계층 명명 정리 (LOW)
- **옵션 A (LOW 카드)**: docstring 보강 단독 (코드 변경 0). 명명: `WebsocketPool` ≡ RealtimeManager / `_subscriptions` property ≡ SubscriptionRegistry / `handler.py` ≡ EventDispatcher / `risk.on_tick` ≡ StrategyEngine. CLAUDE.md 4 계층 매핑 표 추가 권고.

---

## 5. domain-expert 자문 의무 영역

- **Q3 stale 판단 전환** = 보유/익일청산 영향 평가 의무 (사이클 32 R4 universe guard 보호 영속 의무).
- **Q1 SubscriptionRegistry source-of-truth 변경** = orphan ACK race 가드 영향 평가 (사이클 29 R3 priority 분리 영속 의무).

## 6. team-leader 인계 명세 (사이클 87+ 후속 카드 후보)

| 카드 | 등급 | 의제 | 선행 |
|-----|------|------|-----|
| **#E1** | MEDIUM | Q1 옵션 A SubscriptionRegistry read-only view 모듈 신설 (~80L) | domain-expert 자문 |
| **#E2** | LOW | Q5 4 계층 명명 매핑 docstring 보강 (코드 변경 0) | 사용자 결정 |
| **#E3** | LOW | Q4 운영 실증 측정 (사이클 74 인프라 재사용) | 다음 영업일 후 |
| **#E4 (반려)** | — | R4 복구 단일화 = 영구 차단 (CLAUDE.md 4중 안전망 영속) | — |
| **#E5 (반려)** | — | R5 stale 전체 메시지 단독 전환 = 영구 차단 (종목별 보존) | — |

---

## 7. 외부 의견 객관 평가 (총평)

- **정확한 관찰** (3 영역): (a) 복구 > 수신 라인 비율 92% 정합 (b) 종목별 stale 단독 사실 정합 (c) 4 계층 분리 필요성 정합 (다만 *이미 답습*).
- **부분 정확 추정** (2 영역): (a) 원인 확률 추정 = 정량 측정 인프라 *이미 존재* 인지 누락 (b) SubscriptionRegistry 통합 = property 패턴 *이미 답습* 인지 누락.
- **결함 추천** (2 영역): (a) R4 복구 단일화 = CLAUDE.md "절대 깨지 말 것" 4중 안전망 영속 의무 미인지 (b) R5 stale 전체 메시지 단독 = 종목 거래 정지/품절 시 미감지 위험 미인지.

**종합**: 외부 의견은 *구조 관찰* 은 객관적이나 *영속 시정 누적 18 사이클 (사이클 29 R1~R4 + 32 R4 + 60/63/66/67/74/78)* 의 도메인 지식 부재. 단순화 권고 일부는 시정 회귀 위험. **채택 가능 영역 = Q1/Q5 (LOW~MEDIUM, 2 카드)** + **운영 실증 측정 1 영역 (Q4)** + **반려 2 영역 (Q2/Q3 옵션 B)**.
