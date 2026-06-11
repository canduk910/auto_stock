# 사이클 102 도메인 자문 — 시세 구독 영역 전면 재검토 (재구독 로직 아키텍처)

**의뢰**: team-leader (사이클 102 Phase 1)
**자문 일시**: 2026-06-11 (목) KST
**위급도**: **HIGH** (재구독 영역 전면 재설계 / 매매 안전성 영역 직접 영향)
**자문 범위**: A1~A8 (HIGH 5 + MEDIUM 3)
**코드 변경**: 0 (자문 단독)
**선행**: 사이클 88 G-REJECT 영구 차단 영속 / 외부 LLM 의견서 (`_workspace/external_llm_reviews/2026-06-09_realtime_review.md`)
**운영 실측 (Supabase READ-ONLY, 최근 7일)**: `[stale_watcher_detail]` 660~809건/일 / `[stale_force_retry]` 124~141건/일 / `[stale_priority_resubscribe]` 42~64건/일 / `[universe_excluded]` 37~39건/일 / `[stale_watcher_summary]` **0건** (사이클 78 시정 후 첫 영업일 운영 부족 또는 collector flush 결함 의심)

---

## 1. 질문 요약

사용자 핵심: "구독이 끊겼다는 판단으로 재구독 로직을 개발했던게 실수가 아닌가" + "완전히 새로운 시각에서 판단하도록". 외부 의견 = 원인 분포 = **애플리케이션 버그 70~80% / 거래소 구독 상태 유실 10~20% / 네트워크 5% / 프로토콜 매우 낮음**. 본 자문 = (1) 재구독 영역 영구 폐기 가능성 평가 + (2) 외부 의견 영역 (dispatch 누락 / callback 예외 / queue 적체 / dict overwrite / race) 우리 영역 실제 영속 여부 + (3) 사이클 88 G-REJECT 영속 vs 폐기 결정 + (4) 매매 안전성 영역 영향 평가.

---

## 2. 트레이더 시각 (전체 의제 공통 배경)

### 사용자 인식의 정확한 지점

"재구독 로직 = 실수" 라는 직관은 **부분적으로 정확**하다. 트레이더 본능 = "체결창이 멈췄다 = 내가 종목 자체를 잘못 보고 있는 것 / 호가가 진짜 없는 것 / 거래정지 / 시스템 부재" 4 가지 *시장 본질* 가설이 우선이고, "구독이 끊겼다" 는 *시스템 결함* 가설은 **마지막**이어야 한다. 우리 코드는 18 사이클 누적 결과 = *시스템 결함 가설을 1 순위로 영속화* → 재구독 hot path 비대화 (복구 92% vs 수신 8%).

**그러나** "재구독 로직 자체 폐기" = 위험. 운영 실측 = `[stale_priority_resubscribe]` 42~64건/일 = **실제 종목별 stale 발생 빈도 정상 영역**. 5분 우선 재구독 발화 평균 일 50건 = HIGH 보유 절대 보장 + LOW 후보 정상 분산. 폐기 시 = 사이클 29 005935 사고 (8분 영구 잔류 + KIS LMS chain) 재현 위험 100%.

### 외부 의견 핵심 통찰의 정확한 지점

외부 의견 "70~80% 애플리케이션 버그" 핵심 = **dispatch 누락 / callback 예외 / queue 적체 / dict overwrite / race condition**. 우리 영역 실제 분포 =
- **dispatch 누락**: `handler.py::_handle_tick` `if len(fields) < 10: return` graceful → silent drop 가능. 운영 가시화 0 (사이클 88 영역 외).
- **callback 예외**: `dispatch_message` 의 `_on_tick(...)` await 예외 흡수 = **없음** (예외 발생 시 `_receive_loop` 전체 정지 + 재연결 trigger).
- **queue 적체**: `asyncio.Queue` 미사용 = 직접 await dispatch → KIS WS 메시지 순차 처리 → 적체 시 KIS 측 timeout. *해당 없음*.
- **dict overwrite**: 사이클 16 AES 키 격리 영속 (`is_main` + `_EXECUTION_NOTICE_TR_IDS` 이중 가드) = 영구 차단. 사이클 60 logger binding = 영구 차단.
- **race condition**: 사이클 29 R3 priority 분리 + 사이클 88 G-REJECT-3 4 dict 분리 영속 = 영구 차단.

**결정적 발견**: 외부 의견 5 영역 중 **dispatch 누락 + callback 예외** 2 영역 = 우리 영역에서 *실제 운영 가시화 부재 영역*. 사이클 88 영역 외 새 영역. 채택 가능.

### 시장 가설 (도메인 본질)

- **KIS WebSocket = "메시지 brokerage" 본질**: KIS 서버가 SUBSCRIBE 명령 받고 ACK 보내고 시세 push 보내는 *push only* 시스템. 우리 측 = *수신 후 분석*. "구독 끊김" 판정 = 우리 측 가설일 뿐 KIS 측은 정상 송신 중일 가능성 높음.
- **종목별 stale ≠ 세션 stale**: 우선주 / 거래정지 / 품절주 = KIS 정상 동작에서도 60s+ tick 공백 자연 발생. "stale = 결함" 가정 = 오류. *사이클 32 R4 universe guard (today_volume < 10,000) 이 흡수* 가 정답.
- **재구독 = "수신 못 했으니 다시 보내라" KIS 정책 위반 가능성**: KIS 공식 답변 인용 "기등록한 사항을 재등록하지 않도록 (LMS + 앱정보 이용중지)". 사이클 17 OPSP0002 backoff 300s + 사이클 29 시간당 12회 cap = 위반 직접 차단 영속. *그러나* 재구독 영역 자체 = KIS 정책 잠재 위반 영역 (영구 줄여야 하는 영역).

---

## 3. 자문 권고 (A1~A8 세부)

### A1 — "재구독 로직 자체가 실수" 평가 (HIGH)

**권고**: **부분 영구 폐기 비추 + 사용자 직관 부분 채택 (재구독 hot path 라인 비율 92% → 60% 영역 목표)** = **옵션 B (영역 축소 + 운영 가시화 강화)** 단독 채택.

#### 폐기 vs 영속 매트릭스

| 영역 | 영속 의무 (영구) | 폐기 가능 (사이클 102+ 영역) |
|------|----------------|--------------------------|
| **K stale watcher 120s 주기** | **영속 의무** (사이클 29 005935 영구 차단) | 폐기 시 005935 재현 100% |
| **F1 재연결 직후 verify (60s)** | **영속 의무** (KIS silent inactive 차단) | 폐기 시 재연결 후 수분 공백 영구 |
| **`_resubscribe_stale_priority` 5분 우선** | **영속 의무** (HIGH 보유 절대 보장) | 폐기 시 HIGH 보유 5분 지연 영구 |
| **`_check_and_resubscribe_stale` 1~5회 즉시** | **영속 의무** (KIS 정상 "신규 등록" 패턴) | 폐기 시 첫 stale 5분 지연 |
| **`_scan_loop` 5분 delta** | **영속 의무** (스캐너 후보 갱신 연동) | 폐기 시 스캐너 ↔ 구독 일관성 영구 손실 |
| **`_check_and_resubscribe_stale` 6회 초과 force_retry** | **부분 폐기 가능** | 사이클 29 R1 5분 cooldown + 시간당 12회 cap = 사실상 *영속 의무*. **단**, 운영 실측 = 141건/일 = 과도 영역. *임계 상향 영역 (10회 초과 + 10분 cooldown) 검토 가능* |
| **`_detect_silent_inactive_sessions` 세션 reconnect** | **부분 폐기 가능** | 운영 실측 = 0건 (silent_inactive_force_reconnect 0건/7일). *임계 도달 0건 = 영속 의무 영역이나 운영 실측 미발화 → 영역 축소 검토 가능* |
| **`_evaluate_universe_guard` (R4)** | **영속 의무** (보유 절대 보호) | 폐기 시 작전주 자동 차단 영구 손실 |

#### 사이클 29 005935 LMS chain 사고 패턴 재현 위험 평가

**결정적**: 재구독 영역 폐기 시 → 13:21:41 마지막 시도 후 **8분 영구 잔류** → 보유 005935 손절 평가 지연 → 손실 확정. **영구 차단 의무**. 사용자 직관 "실수가 아닌가" = *영역 축소*에는 동의 가능하나, *영역 폐기*는 동의 불가.

#### 권고 옵션 B 영역 축소 매트릭스

- **유지 (영속)**: F1 / `_scan_loop` / K stale watcher 1~5회 / priority 5분 / R4 universe guard (5 영역)
- **부분 완화 (사이클 102+ 검토)**: 6회 초과 force_retry 임계 5분→10분 cooldown + 시간당 12회→6회 cap (운영 실측 141건/일 → 70건/일 목표)
- **부분 축소 (사이클 102+ 검토)**: silent_inactive_force_reconnect 영역 = 0건/7일 실측 = 영역 축소 (5분→10분 지속 임계)

---

### A2 — 외부 의견 4 영역 로그 (`last_ws_message_at`) 평가 (HIGH)

**권고**: **사이클 88 G-REJECT-2 영구 차단 영속 + `last_ws_message_at` 영역 *보조 가시화* 신규 도입 (영구 채택 가능)**.

- 외부 의견 = 종목별 + 세션별 stale 영역 분리 로그. **사이클 88 G-REJECT-2 = 종목별 영속 의무** (영구 차단 동일).
- 그러나 **세션별 가시화 영역 = 신규 영역**. 현 영속 `[ws_heartbeat]` 5분 PINGPONG 통계 = 세션별 송수신 빈도 영속이나, *마지막 메시지 시각 단독 추적 = 부재*. 신규 도입 가능 (`_last_ws_message_at: datetime` 인스턴스 변수 + `_heartbeat_metrics_emit_once` 영역 추가 + 운영 가시화).
- **핵심**: 종목별 stale 판정 (`ticker_last_tick` 기반) = **영속 의무** (G-REJECT-2). 세션별 `last_ws_message_at` = **보조 가시화** (판정 책임 X). 두 영역 = *책임 분리* 영속.

#### 매매 안전성 영역 영향 평가

- 보조 가시화 도입 = **영향 0** (판정 로직 변경 0, 로그 추가만).
- 세션 단위 단독 stale 판정 시 = **HIGH 보유 매도 hot path 마비 100%** (G-REJECT-2 사고 영역). 영구 차단.

---

### A3 — dispatch 누락 / callback 예외 / queue 적체 / dict overwrite / race 평가 (HIGH)

**권고**: **운영 가시화 영역 신규 도입 (silent drop 추적 + callback 예외 logger 보강)**. 4 영역은 우리 영역 영속.

| 외부 의견 영역 | 우리 영역 실제 상태 | 권고 |
|--------------|------------------|------|
| **dispatch 누락** | `handler.py::_handle_tick` `if len(fields) < 10: return` graceful silent drop = 운영 가시화 0 | **신규**: `_silent_drop_count: dict[str, int]` 모듈 전역 + 5분 주기 emit (사이클 74 collector 답습) |
| **callback 예외** | `dispatch_message` `_on_tick(...)` await 예외 = `_receive_loop` 정지 + 재연결 trigger | **신규**: callback 영역 try/except + logger.exception + `[callback_exception]` prefix (재연결 trigger 보존 영속) |
| **queue 적체** | `asyncio.Queue` 미사용 = 직접 await dispatch | **해당 없음** (KIS 적체 시 timeout 자연 trigger) |
| **dict overwrite** | 사이클 16 AES 격리 + 사이클 60 logger binding 영속 | **영속 영구** (영구 차단 영역) |
| **race condition** | 사이클 29 R3 priority + 사이클 88 G-REJECT-3 4 dict 분리 영속 | **영속 영구** (영구 차단 영역) |

**결정적 발견**: dispatch 누락 + callback 예외 = **신규 운영 가시화 영역** (사이클 88 영역 외). 채택 가능 (사이클 102+ 별개 카드 인계).

---

### A4 — 사이클 88 G-REJECT 3 영구 차단 영역 평가 (HIGH)

**권고**: **G-REJECT-1/2/3 영구 영속 의무 영구** (사이클 88 시점 양 agent 일치 결론 영역 영구 보존).

#### G-REJECT 영역별 외부 의견과의 정합/충돌 매트릭스

| G-REJECT | 사이클 88 영구 차단 | 외부 의견 영역 | 평가 |
|---------|------------------|-------------|------|
| **G-REJECT-1** 단일 restore 통합 차단 | 4중 안전망 영속 (F1 + scan_loop + K + priority) | 외부 의견 = "재구독 로직 자체가 실수" → 단일화 추정 | **충돌**. G-REJECT-1 영속 의무 (4 영역 시간 척도 분리 = 의무) |
| **G-REJECT-2** stale 전체 WS 단독 차단 | 종목별 `ticker_last_tick` 14 사이트 영속 | 외부 의견 = `last_ws_message_at` *전체* 기준 도입 | **부분 충돌**. 종목별 영속 + 세션 보조 가시화 *추가* = 정합 가능 |
| **G-REJECT-3** SubscriptionRegistry 단일 dict 차단 | 4 dict 분리 (`_subscriptions` / `_subscriptions_acked` / `_ticker_to_session` / `ticker_last_tick`) 영속 | 외부 의견 = 단일 통합 추정 | **충돌**. G-REJECT-3 영속 의무 (KIS race / 41 한도 / orphan ACK 분리 = 도메인 의무) |

#### 결정적 영구 차단 영역 (사이클 88 양 agent 일치 결론 영구 보존)

- **G-REJECT-1**: 단일 restore 도입 시 = 사이클 29 005935 사고 재현 100%. **영구 차단 영역 영속**.
- **G-REJECT-2**: 종목별 stale 폐기 시 = SK하이닉스 활성 + 삼성전자 거래정지 시나리오 = 삼성전자 silent 미감지 → 보유 매도 hot path 마비. **영구 차단 영역 영속**.
- **G-REJECT-3**: 4 dict 통합 시 = orphan ACK race + 41 한도 분산 영구 손실 + 사이클 29 R3 priority 분리 회귀. **영구 차단 영역 영속**.

---

### A5 — 매매 안전성 영역 영속 의무 (HIGH)

**권고**: **CLAUDE.md "절대 깨지 말 것" 8 영역 영구 영속 + 본 사이클 102 자문 결과 = 매매 안전성 영역 영향 0 보장**.

- **체결통보 (H0STCNI0/H0STCNI9) 구독 제거 금지**: 본 자문 영역 외. 영속.
- **WebSocket 4중 안전망 영속**: 본 사이클 102 자문 결과 = 영역 축소 (부분 완화) 가능하나 *4 영역 시간 척도 분리 영속 의무*. F1 + scan_loop + K + priority 4 영역 모두 영속.
- **보유/익일청산 절대 보호 (사이클 32 R4)**: 본 사이클 102 영역 외 (universe guard 영역). 영속.

#### 매매 안전성 영역 영향 평가 매트릭스

| 권고 영역 | 매매 안전성 영향 | 평가 |
|---------|----------------|------|
| 재구독 영역 *폐기* | **HIGH 위험** (005935 재현 100%) | **거부** |
| 재구독 영역 *부분 완화* (force_retry 임계 상향) | LOW 위험 (사이클 29 R1 cap 영속) | **검토 채택 가능** |
| 외부 의견 `last_ws_message_at` *보조 가시화* | 영향 0 (로그 영역) | **채택 가능** |
| dispatch 누락 / callback 예외 *운영 가시화* | 영향 0 (로그 영역) | **채택 가능** |
| G-REJECT 3 영역 영속 | 영속 의무 (영구 차단) | **영속 영구** |

---

### A6 — 운영 실측 영역 평가 (MEDIUM)

**권고**: **운영 실측 영역 → 외부 의견 가설 영역 검증 영구 의무 (사이클 102+ 별개 카드 인계)**.

#### 운영 실측 7일 분포 (Supabase READ-ONLY 본 자문 직접 측정)

| prefix | 일일 평균 | 평가 |
|--------|---------|------|
| `[stale_watcher_detail]` | 660~809건/일 | **정상 영역** (사이클 73 individual 영속, 사이클 29 005935 진단 의무) |
| `[stale_force_retry]` | 124~141건/일 | **과도 영역 (사이클 29 R1 발화 빈번)** — 임계 상향 검토 영역 |
| `[stale_priority_resubscribe]` | 42~64건/일 | **정상 영역** (HIGH 보유 + LOW 후보 분산) |
| `[universe_excluded]` | 37~39건/일 | **정상 영역** (사이클 32 R4 작전주 차단) |
| `[stale_watcher_summary]` | **0건** | **결함 의심**: 사이클 78 시정 commit 시점 미배포 또는 collector flush 결함 |
| `[silent_inactive_force_reconnect]` | 0건 | **영속 영역 (영구 차단 정상 결과)** |
| `[ws_subscribe_reject]` | 측정 부재 | 외부 의견 검증 영역 (사이클 102+ 별개 카드) |
| `[ws_reverify]` | 측정 부재 | 외부 의견 검증 영역 (사이클 102+ 별개 카드) |

#### 결정적 발견

- **`[stale_watcher_summary]` 0건/7일** = **사이클 78 silent 결함 영역** 또는 **배포 미반영 영역**. 사이클 102 별개 카드 *영구 확인 의무*.
- **`[stale_force_retry]` 141건/일** = 사이클 29 R1 cap (시간당 12회) 정상 영역이나 *임계 상향 검토 영역* (사이클 102+ 별개 카드).

---

### A7 — 6 전략 후보 풀 영역 영향 (MEDIUM)

**권고**: **재구독 영역 영역 축소 (사이클 102+ 부분 완화) = 6 전략 후보 풀 영향 0 보장** (사이클 38 명문화 영속 + scanner 단계 영역 분리).

- 사이클 38 명문화 (`tradable_boards` 매수 진입 전용) = 매수/매도 영역 분리. 재구독 영역 변경 시 매도 hot path 영향 0.
- 후보 풀 = scanner 단계 영역 (subscribe_filtered_stocks). 재구독 영역 = stale 발생 *후* 영역. 영역 분리 영속.

---

### A8 — Plan Phase A/B 영속 영향 (MEDIUM)

**권고**: **사이클 102 재구독 영역 재설계 = Plan Phase A/B 영역 영향 0 보장** (stock_master 적재 영역 분리).

- 사이클 101 = market_cap + CTPF1002R 적재 (Plan 영속). 재구독 영역 = WebSocket 시세 수신 *후* 영역.
- Plan Phase A/B (사이클 102+ 영속) = 6 전략 후보 풀 stock_master 베이스 전환. 재구독 영역 영향 0.

---

## 4. 권고 매트릭스 (시정 / 영속 / 폐기 결정 영구)

| 영역 | 결정 | 위급도 | 사이클 |
|------|------|------|-------|
| **재구독 영역 전면 폐기** | **거부** (005935 재현 100% 위험) | — | — |
| **사이클 88 G-REJECT-1/2/3 영구 차단** | **영속 영구** | HIGH | 사이클 88 영속 |
| **재구독 영역 부분 완화** (force_retry 임계 상향 5분→10분 + cap 12→6회) | **검토 채택** | MEDIUM | 사이클 102+ 별개 카드 |
| **외부 의견 `last_ws_message_at` 보조 가시화** | **검토 채택** | LOW | 사이클 102+ 별개 카드 |
| **dispatch 누락 silent_drop_count 가시화** | **검토 채택** | MEDIUM | 사이클 102+ 별개 카드 |
| **callback 예외 `[callback_exception]` prefix 신규** | **검토 채택** | MEDIUM | 사이클 102+ 별개 카드 |
| **`[stale_watcher_summary]` 0건/7일 실측 결함 영구 확인** | **즉시 발의** | HIGH | 사이클 102 부차 카드 |
| **사이클 88 #E1 SubscriptionRegistry read-only view** | **선행 자문 영속** | MEDIUM | 사이클 89+ 영속 (사이클 102 외) |

---

## 5. 반례 / 한계 (영구 영속 의무)

- **반례 1**: 본 자문 = 코드 변경 0 (자문 단독). 권고 영역 모두 사이클 102+ 별개 카드 인계 의무.
- **반례 2**: 외부 의견 70~80% "애플리케이션 버그" 영역 = 우리 영역 *부분 정확* (dispatch 누락 + callback 예외 2 영역) + *부분 영역 외* (queue 적체 / dict overwrite / race = 사이클 16/29/88 영구 차단 영속).
- **반례 3**: `[stale_watcher_summary]` 0건/7일 = 사이클 78 시정 영역 검증 의무. 본 자문 단독 결정 영역 외.
- **한계 1**: 운영 실측 7일 = 사이클 78 시정 commit 2026-06-08 이후 = *최근 운영 부족*. 사이클 102+ 1주 운영 영속 후 재평가 영구 의무.
- **한계 2**: 본 자문 = 도메인 자문 단독 (refactor-expert 자문 미실시). 사이클 102+ 본격 시정 시 refactor-expert 동행 자문 영구 의무.

---

## 6. 후속 검증 권고 (사이클 102+ tdd-engineer / tester 인계)

- **사이클 102 부차 카드 (HIGH)**: `[stale_watcher_summary]` 0건/7일 영역 영구 확인 (사이클 78 시정 배포 검증 + collector flush 결함 의심 영구 차단).
- **사이클 102+ 별개 카드 (MEDIUM)**: force_retry 임계 상향 (5분→10분 cooldown + 시간당 12회→6회 cap) — domain-expert 자문 + tdd-engineer 회귀 가드 (freezegun) + tester verify (1주 운영 후).
- **사이클 102+ 별개 카드 (MEDIUM)**: dispatch 누락 + callback 예외 운영 가시화 신규 도입 — `_silent_drop_count` 5분 emit + `[callback_exception]` prefix (사이클 74 collector 답습).
- **사이클 102+ 별개 카드 (LOW)**: `last_ws_message_at` 세션별 보조 가시화 (`_heartbeat_metrics_emit_once` 영역 추가).
- **사이클 89+ 영속**: #E1 (MEDIUM) SubscriptionRegistry read-only view 모듈 신설 (~80L) — 사이클 88 영속 채택 가능 카드.
- **AST 영구 가드 영역 영속**: G-REJECT-1/2/3 영구 영속 의무 (사이클 88 영속).

---

## 7. 결론 (영구 영속)

사용자 직관 = **부분 정확** (재구독 hot path 비대화 영역 인식 정확) + **부분 오류** (영역 폐기 시 매매 안전성 영역 직접 영향 100%). 본 자문 = **옵션 B 영역 축소 + 운영 가시화 강화** 단독 채택. 사이클 88 G-REJECT-1/2/3 영구 영속 의무 + 외부 의견 `last_ws_message_at` 보조 가시화 + dispatch 누락 + callback 예외 운영 가시화 = **3 영역 신규 채택 가능** (사이클 102+ 별개 카드 인계). 매매 안전성 영역 영향 0 보장 + 사이클 29 005935 사고 패턴 재현 영구 차단 + 사이클 32 R4 universe guard 영속 + CLAUDE.md "절대 깨지 말 것" 8 영역 영속.

**핵심 영구 영속**: 재구독 영역 = *KIS 도메인 의무* (사이클 88 양 agent 일치 결론 영구 보존). 폐기 X / 영역 축소 O / 운영 가시화 강화 O.
