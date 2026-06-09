# 외부 LLM 의견서 통합 영구 기록 — 2026-06-09 (사이클 88)

> **목적**: 타 LLM 제출 "시세 수신 오류 + 구조 단순화" 의견서에 대한 refactor-expert 검토 + domain-expert 자문을 통합하여 영구 기록. 미래 동일 추천 재현 시 이 문서 + AST 가드 3종으로 즉시 차단.

---

## 1. 외부 의견 verbatim (원문)

> **총평**: "시세를 받기 위한 기능보다 시세를 복구하기 위한 기능이 더 많아진 상태" = 복구 기능 폭증.
>
> **원인 가능성 추정**:
> - stale_watcher 과민반응 **40%**
> - 상태 불일치 **25%**
> - reconnect 복구 루프 꼬임 **20%**
> - Pool 구조 **10%**
> - 실제 WS 장애 **5%**
>
> **추천 4 계층 구조**: `RealtimeManager → SubscriptionRegistry → EventDispatcher → StrategyEngine`
>
> **stale 판단 개선**: 종목별 `ticker_last_tick` → 전체 `last_ws_message_at` 기준 전환
>
> **코드 정리 우선순위**:
> 1. stale watcher 재검토
> 2. subscription 상태 통합
> 3. WS 책임 축소
> 4. 복구 로직 단일화 (`restore` / `reverify` / `stale_recovery` → 하나)

---

## 2. refactor-expert 검토 결과 (8 영역 처리 매트릭스)

### 2-1. 객관 정확 (3 영역)

| 영역 | 사실 | 검토 |
|------|------|------|
| 복구 > 수신 라인 비율 | stale 1,340L / websocket 1,460L = 92% | 정합. "복구 기능 폭증" 총평 *사실* |
| 종목별 stale 단독 (14 사이트) | `ticker_last_tick` 14 사이트 / `last_ws_message_at` 0 사이트 | 정합. 외부 추천 관찰 정확 |
| 4 계층 분리 필요성 | `WebsocketPool → KisWebSocket → handler.py → risk.on_tick` *이미 4 계층 답습* | 정합. 다만 외부 LLM 이 *이미 답습*임을 모름 |

### 2-2. 부분 정확 추정 (2 영역)

| 영역 | 외부 추정 | 실제 |
|------|---------|------|
| 원인 확률 정량 | 정성 추정 (40/25/20/10/5) | 측정 인프라 *이미 존재* — 사이클 42/74 `[stale_watcher_summary]` + `[ws_action_summary]`. 추정 → 실증 전환 가능 |
| SubscriptionRegistry 통합 | 단일 dict 권고 | property 패턴으로 *이미 단일 view* 제공 (`websocket_pool.py` 호환 property 4종). source-of-truth 는 세션별 분산 (영속 의무) |

### 2-3. 과대 추정 (1 영역)

| 영역 | 외부 추정 | 실제 |
|------|---------|------|
| 상태 불일치 25% | "상태 불일치 = 4 dict 분리 문제" | 4 dict 분리는 *의무* (orphan ACK race / 41 한도 / 종목별 tick 추적). 실측 불일치 < 5% (사이클 29 R3 ACK 정합 가드 이후). 외부 LLM KIS race/멀티 세션 정책 미인지 |

### 2-4. 반려 확정 (2 영역)

| 외부 추천 | 반려 근거 | 영구 차단 |
|----------|---------|---------|
| **R4. 복구 단일화** (`restore` 하나) | CLAUDE.md "절대 깨지 말 것" — WebSocket 4중 안전망 (F1 즉시 / `_scan_loop` 5분 / K stale watcher 120s / priority 5분). 각각 발화 조건 다름 (재연결 / 종목별 tick / 세션 silent / 우선순위). 단일화 = 발화 조건 정밀도 손실 + 사이클 29 005935 사고 재현 위험 | AST G-REJECT-1 |
| **R5. stale 전체 WS 기준 전환** | 사이클 29 R1 종목 단위 tick 14 사이트 영속. 특정 종목 거래정지/품절 → 세션 fresh_ratio 정상 → 미감지 → 보유 매도 hot path 마비. 005935 사고 = 종목 단위 가시성으로 진단 가능했음 (전체 기준이면 발견 불가) | AST G-REJECT-2 |

### 2-5. 후속 카드 (#E1 ~ #E5)

| 카드 | 등급 | 내용 | 선행 |
|-----|------|------|-----|
| **#E1** | MEDIUM | Q1 `subscription_registry.py` read-only view 모듈 신설 (~80L) | domain-expert 자문 완료 → 사이클 89+ 발의 가능 |
| **#E2** | LOW | 4 계층 명명 매핑 docstring 보강 (코드 변경 0) | 사용자 결정 |
| **#E3** | LOW | 운영 실증 측정 (사이클 74 인프라 재사용) | 2026-06-09 이후 영업일 데이터 누적 후 |
| **#E4 (반려)** | — | R4 복구 단일화 = 영구 차단 (CLAUDE.md 4중 안전망 영속) | — |
| **#E5 (반려)** | — | R5 stale 전체 메시지 단독 전환 = 영구 차단 (종목별 보존) | — |

---

## 3. domain-expert 자문 결과

### 3-1. 원인 비중 재추정 (도메인 실측 기준)

| 외부 추정 | 외부 % | 도메인 실측 % | 근거 |
|----------|-------|------------|------|
| stale_watcher 과민반응 | 40% | **30%** | 사이클 29 R1 시간당 12회 cap + 사이클 66 priority cap=10 누적 흡수. 우선주/ETF 정상 공백 > 60s = 실제 위양성 영역 |
| 상태 불일치 | 25% | **< 5%** | 사이클 29 R3 ACK 정합 가드 + 4 dict 분리 의무로 차단 |
| reconnect 루프 꼬임 | 20% | **10%** | 시간당 2회 cap (사이클 29 R2) + KIS 거부 분기 분리 (OPSP0002/APBK0918/5xx/토큰) |
| Pool 구조 | 10% | **≈ 0%** | 사이클 43 라벨 통일 + 사이클 67 4 sub-module 분해 완료 |
| 실제 WS 장애 | 5% | **20~25%** | OPSP0002/5xx 합산 일 100건+ (사이클 74 실측). 외부 LLM KIS 운영 안정성 과대평가 |

### 3-2. Q1 — "전체 WS 기준" 채택 시 도메인 위험

- SK하이닉스 활성 (초당 30 tick) + 삼성전자 거래정지 → 세션 fresh_ratio > 0.2 → **세션 정상 판정** → 삼성전자 silent **미감지**
- 사이클 29 005935 사고: 삼성전자우 HIGH 우선 8분 영구 잔류 진단 = 종목 단위 가시성으로 가능 (전체 기준이면 발견 불가)
- 우선주/동전주/ETF: 정상 tick 공백 > 60s 빈번 → 위양성 발생. 이는 이미 사이클 32 R4 universe guard (stale + today_volume < 10,000) 가 흡수

### 3-3. Q2 — 4 dict 분리 영속 의무

- `_subscriptions` vs `_subscriptions_acked` 분리: KIS SUBSCRIBE 송신 ↔ ACK 수신 race (수십 ms~수초). orphan ACK 분리 보존 의무
- `_ticker_to_session`: KIS 세션당 41 한도 물리 정책 — 단일 dict 통합 시 사이클 29 R3 priority 분리 회귀 위험
- **결론**: 4 dict 분리는 *구현 선택*이 아닌 *KIS 도메인 의무*

### 3-4. Q3 — 4중 안전망 시간 척도 분리 영속

| 안전망 | 시간 척도 | 트리거 | 단일화 시 손실 |
|-------|----------|--------|-------------|
| F1 재연결 verify | 즉시 | 소켓 disconnect 이벤트 | 재연결 후 수초~수분 공백 → 보유 stop loss 미발화 |
| `_scan_loop` | 5분 | 스캐너 후보 갱신 | — |
| K stale watcher | 120s | 종목별 tick 부재 | — |
| `_resubscribe_stale_priority` | 5분 | priority HIGH 우선 | 보유/익일청산 절대 보호 마비 |

---

## 4. 양 agent 일치 결론

> **구조 관찰 객관, 영속 시정 18 사이클 도메인 지식 부재**

- refactor-expert: 복구/수신 92% 비율 정합 + 4 계층 이미 답습. 외부 추천 단순화 일부는 *시정 회귀 위험*
- domain-expert: stale 트레이드오프 직관 정확 + KIS 운영 실측 (OPSP0002/5xx 일 100건+) 미인지. 종목 단위 stale = *KIS 도메인 의무* (005935 사고 재현 방지)
- **채택 가능**: #E1 (MEDIUM, SubscriptionRegistry read-only view) + #E2 (LOW, docstring) + #E3 (LOW, 운영 측정)
- **영구 차단**: R4 (복구 단일화) + R5 (전체 WS 기준 단독 전환) + 단일 사이클 4 계층 전체 분할

---

## 5. 사용자 결정 (Plan 영속)

- **A 점진 흡수**: 후속 카드 #E1/#E2/#E3 단계적 채택
- **전수 3 AST 가드**: 사이클 88 `tests/unit/ast/test_external_llm_reject_patterns.py` 즉시 배포
- **8 쿼리 채택**: refactor-expert Phase 2 충돌 매트릭스 + domain-expert Q1~Q5 전부 산출

---

## 6. 영구 차단 영역 3

### R4 영구 차단 (AST G-REJECT-1)

WebSocket 4중 안전망 함수 4종 영속:
1. `websocket.py::_verify_subscriptions_after_reconnect` (F1)
2. `scheduler.py::_scan_loop` (5분)
3. `stale_watcher_core.py::check_and_resubscribe_stale` (120s K watcher)
4. `stale_watcher_core.py::resubscribe_stale_priority` (5분 우선)

단일화 시 사이클 29 005935 사고 재현 위험. KIS 거부 분기 (OPSP0002/APBK0918/5xx/토큰) 분리 영속.

### R5 영구 차단 (AST G-REJECT-2)

종목별 `ticker_last_tick` 영속:
- `stale_tracker.py::ticker_last_tick` 영속 (14 사이트)
- `stale_watcher_core.py::STALE_FRESHNESS_SECS` 영속

전체 WS 기준 단독 채택 시 특정 종목 거래정지/품절 미감지 → 보유 매도 hot path 마비.

### R2 단일 dict 통합 영구 차단 (AST G-REJECT-3)

4 dict 분리 영속:
- `websocket.py::_subscriptions` (SEND 기준)
- `websocket.py::_subscriptions_acked` (ACK 정합성 가드)
- `websocket_pool.py::_ticker_to_session` (멀티 세션 분배)
- `stale_tracker.py` / `scanner.py::ticker_last_tick` (종목별 tick)

---

## 7. 사이클 96 재평가 시점 예약

1주 운영 실증 (2026-06-09 ~ 2026-06-13) 후:
- `[stale_watcher_summary]` 5분 통계: `stale_total/checks` 비율 측정 → > 5% 이면 카드 #A (후보 stale 임계 완화) 발의
- `[ws_action_summary]`: OPSP0002/5xx 빈도 실증 → 외부 LLM 5% 추정 vs 도메인 20~25% 재검증
- `[api_retry_recovered_summary]`: api retry 1.0~1.2x 유지 확인 (사이클 76 효과 영속)

**재평가 결과에 따라**:
- 과민반응 실증 confirm → 카드 #A (MEDIUM) 발의
- 정상 범위 → AST 가드 3종 영속 + 후속 카드 #E1 단독 진행

---

## 8. 영속 보장 매트릭스 (단순 통합 추천 영구 거부)

| 영속 영역 | 근거 사이클 | 거부 대상 추천 |
|----------|-----------|------------|
| WebSocket 4중 안전망 시간 척도 | 사이클 29 R1/R2/R3 + 사이클 32 R4 | R4 복구 단일화 |
| 종목 + 세션 2 계층 stale 하이브리드 | 사이클 29 R1 (종목) + R2 (세션) | R5 전체 WS 기준 단독 |
| 4 dict 분리 (subscriptions/acked/session/tick) | 사이클 29 R3 + 사이클 32 R4 | R2 SubscriptionRegistry 단일 dict |
| HIGH bypass_limit=True + 보유/익일청산 절대 보호 | 사이클 32 R4 universe guard | 단일 사이클 4 계층 전체 분할 |
| 사이클 38 명문화 (tradable_boards 매수 진입 전용) | 사이클 38 | StrategyEngine 분기 통합 |
| 사이클 66 priority cap=10 시정 | 사이클 66 | 단일 restore 로 우선순위 혼합 |
| 사이클 67 stale_manager 4 sub-module 분할 | 사이클 67 | 재통합 추천 |
| 사이클 74 5분 aggregation | 사이클 74 | 직접 emit 재도입 |
| 사이클 78 flush 누락 영구 차단 | 사이클 78 | collector 제거 |

---

**참조**:
- 선행: `_workspace/refactor/2026-06-09_external_llm_review.md` (refactor-expert 원본)
- 선행: `_workspace/refactor/2026-06-09_external_llm_domain_consult.md` (domain-expert 원본)
- AST 가드: `tests/unit/ast/test_external_llm_reject_patterns.py`
- 재평가: 사이클 96 (2026-06-13 이후 영업일 데이터 누적 후)
