# 사이클 92 — 07:50 KIS API 강제 중단 충돌 영구 시정 도메인 자문

> **자문 위상**: domain-expert 데이/스윙 트레이더 출신 도메인 컨설턴트
> **자문 일시**: 2026-06-10 09:30 KST (KRX 메인 진입 후 30분)
> **자문 요청 위상**: team-leader (사용자 결정 Q28~Q31 영속 채택 후 명세 분해 *전*)
> **위급도**: **HIGH** (매매 안전성 직접 영역 — 시세 0건 = 매수/매도 hot path 완전 정지)
> **결정 영속**: Q28=E (TIME_BOOT 07:55 + 자동 재기동) / Q29=A (TIME_AUTO_START 07:45 영속) / Q30=A (start() idempotent 재호출 + 60s cooldown + 시간당 3회 cap) / Q31=C (KIS 공식 명문 생략)
> **사이클 88 G-REJECT 영속**: WebSocket 4중 안전망 = 자동 재기동 = *추가* 영역 (대체 X) — G-REJECT-1 위반 0

---

## A1 (HIGH) TIME_BOOT 07:50 → 07:55 이동 영향 — 4 부 답변

### A1-Q1 `_boot()` 순차 진행 영속 보장? (HIGH)

**도메인 권고**: **현재 `_boot()` 순차 영역 변경 0 의무 + 5분 마진은 충분**.

`_boot()` (사이클 51 boot_manager.py 위임) 의 순차 진행 영역은 트레이더 시각에서 *7~15초* 정도 소요 추정 (도메인 실측 추정):
- `_preissue_all_tokens` (3~5초): 메인 캐시 hit 즉시 + 보조 N 캐시 hit 시 즉시 / 캐시 miss 시 분당 1개 한도 직렬화 (60초 gap) — 정상 운영에선 *전부 캐시 hit* 가정 (사이클 20 토큰 24h 캐시 영속)
- DB positions 복구 (0.5~1초): Supabase 단일 쿼리
- KIS 잔고 교차 검증 (1~2초): `/uapi/domestic-stock/v1/trading/inquire-balance`
- 미체결 복구 (1~2초): `get_daily_orders` 1회 + reconciliation
- stock_master eager refresh (1~3초): 보유 + 익일청산 합집합 N 개 × `inquire-price` 50ms gap
- 매크로 fetch (1~2초): dkstock.cloud `/api/macro/macro-cycle` — 실패 graceful empty
- `cash_usage_ratio` 자동 조정 + `allocate_funds` (0.5초): 메모리 영역만

총합 **7~15초 정상 / 캐시 miss 누적 시 최대 60~120초** (보조 매니저 N 명 × 60s).

**5 분 마진 (07:55 → 08:00 NXT 사전 구독 영역) 충분 영역**: 정상 7~15초 → 5 분 영역 안 80% 마진 + 캐시 miss 누적 시 60~120초 → 5 분 영역 안 60% 마진. **트레이더 본능**: KIS 강제 중단 후 *재 토큰 발급* 의무 가능성 (KIS LMS 정책) — 5 분 마진은 *그 영역까지* 흡수 가능.

**위험 시나리오**: 메인 + 보조 5 명 모두 캐시 miss + 신규 발급 → 6 × 60s = 360s = 6 분 → 5 분 마진 부족. **회피**: 사이클 20 토큰 캐시 (24h `.token_cache/` 볼륨) 영속 의무 — 컨테이너 재기동 시점 (CI/CD push 영역) 외엔 *전부 캐시 hit*. CI/CD push 영역 자체는 운영 가이드 (CLAUDE.md) "NXT 애프터 (15:30+) 또는 익일 07:45 *전* push" 영속.

### A1-Q2 `TIME_PRESUBSCRIBE = 07:55` 와 동시 발화 race? (HIGH)

**도메인 권고**: **`TIME_PRESUBSCRIBE` 도 동행 이동 의무 (`08:00` 또는 `07:59`)**.

현재 `scheduler.py:508` 영역 = `if now < TIME_PRESUBSCRIBE: await self._wait_until(TIME_PRESUBSCRIBE)`. `_boot()` 본체가 *동기적* 으로 진행되므로 (start() 의 `await self._boot()` 영속), `TIME_BOOT == TIME_PRESUBSCRIBE = 07:55` 인 경우:
- 07:55:00 → `_boot()` 진입
- 07:55:07~07:55:15 → `_boot()` 완료
- 07:55:15 → `now < TIME_PRESUBSCRIBE = 07:55` *false* → 즉시 사전 구독 진입 (대기 0초)

**race 가능성 0** (동기 순차 보장). 그러나 *논리적 race 회피* 영역 = `TIME_PRESUBSCRIBE` 도 `08:00` 또는 `07:59` 동행 이동 권고 — 사이클 92 시정 의도 명시 (07:55 = `_boot()` 시작, 사전 구독 = 그 *후* 영역).

**옵션 권고**:
- **옵션 P1 (강력 권고)**: `TIME_PRESUBSCRIBE = time(7, 59)` 또는 `time(7, 58)` — `_boot()` 완료 후 1~2 분 마진 + 사전 구독 *전* 토큰 안정화 영역 확보
- 옵션 P2 (변경 0): `TIME_PRESUBSCRIBE = time(7, 55)` 영속 — 위 race 0 보장 영역 활용

### A1-Q3 `TIME_PRESUBSCRIBE` 동행 이동 의무? (HIGH)

**답변**: 옵션 P1 영역 권고 (`07:59`). 이유:
1. `_boot()` 완료 *후* 사전 구독 분리 = 명시적 단계 분리 (트레이더 본능)
2. 사이클 88 G-REJECT-1 영속 영역 (4중 안전망 시간 척도) 영향 0 — `TIME_PRESUBSCRIBE` 자체 변경은 4중 안전망 구조 무영향
3. `08:00 TIME_PRE_NXT_OPEN` 영역 영향 0 — 1 분 마진 확보

### A1-Q4 `08:00 TIME_PRE_NXT_OPEN` 익일 청산 task 시점 영향? (MEDIUM)

**답변**: **영향 0 보장**.

`TIME_PRE_NXT_OPEN = 08:00` 영속 + `_execute_next_day_clear` task 시점 영속. NXT 프리 시가 (08:00 첫 거래) 수신 후 `NEXT_DAY_STABILIZE_SECS=30s` 안정화 영속. `TIME_BOOT` / `TIME_PRESUBSCRIBE` 이동은 *08:00 직전 단계* 영역 한정 영향만 — 익일 청산 hot path 영역 영향 0.

**위험 시나리오**: `TIME_BOOT = 07:55` 이동 후 `_boot()` 가 캐시 miss 누적 6 분 소요 → 08:00 NXT 프리 진입 시점 *_boot 미완료* → race? **회피**: `start()` 의 `await self._boot()` 가 동기 영역 → `TIME_PRESUBSCRIBE` / `TIME_PRE_NXT_OPEN` 자동 대기 → race 0. 단, 08:00 시점 시가 수신 *직전* `_boot()` 미완료 시 `_execute_next_day_clear` task 시작 지연 → 30s 안정화 영역 안 흡수 가능.

---

## A2 (HIGH) 자동 재기동 영역 안전성 (Q30=A) — 5 부 답변

### A2-Q1 `start()` idempotent 의무?

**도메인 권고**: **idempotent 의무 명시 + 진입 게이트 영속**.

`scheduler.py:395-405` 영역 = `if self._running: logger.warning("이미 실행 중"); return` 영속. 사이클 92 자동 재기동 영역에서 `start()` 재호출 *전* `self._running = False` 강제 의무 — 그러지 않으면 진입 게이트가 즉시 return → 재기동 무영향. **권고 패턴**: `MAX_RECONNECT` 도달 시점 `self._running = False` + `stop()` 호출 (기존 task cancel + lifecycle 정리) → 60s cooldown → `start()` 재호출. 사이클 79/80 task lifecycle 답습.

### A2-Q2 시간당 3회 cap = KIS LMS chain 차단 충분 영역?

**도메인 권고**: **3회/시간 cap 적정 + 사이클 24 silent_inactive 2회 답습 보강 영역 가능**.

KIS LMS / 앱키 정지 정책 (도메인 실측): *분당 1개 토큰 한도 + 시간당 5~10회 이상 발급 시 임시 정지* 추정 (정본 명문 부재). 시간당 3회 자동 재기동 = 3 × (메인 + 보조 N) 토큰 발급 영역 — 보조 5명 가정 시 = 18 토큰/시간 = LMS chain 위험 영역 진입. **회피**: 사이클 20 토큰 24h 캐시 영속 의무 — 자동 재기동 시 캐시 hit 우선 → *신규 발급 0건* 가정 → LMS chain 차단.

**옵션 권고**:
- 옵션 A1 (강력 권고): 시간당 3회 cap + ERROR 가시화 `[ws_max_reconnect_exceeded_auto_restart] count=N/3 hourly_window_expired=Xs`
- 옵션 A2 (보강): 일일 5~10회 cap 추가 (24h 윈도우) — 시간당 cap 통과해도 일일 한도 차단

### A2-Q3 `start()` 재호출 시 `_preissue_all_tokens` 영역 영향? (HIGH)

**도메인 권고**: **캐시 hit 보장 영역 = 토큰 발급 0건 영속 — `start()` 재호출 안전 영역**.

사이클 20 토큰 캐시 (24h `.token_cache/` 볼륨 영속) 가정 시:
- 자동 재기동 시점 → 메인 토큰 캐시 hit (TTL 24h) → 즉시 return → 신규 발급 0건
- 보조 N 매니저 동일 영역 → 캐시 hit → 신규 발급 0건

**위험 시나리오**: 토큰 캐시 부재 / 만료 시점 → 메인 신규 발급 1회 + 보조 N 신규 발급 N회 × 60s gap = 분당 1개 한도 직렬화 → 자동 재기동 1회당 (N+1) × 60s 소요 → 시간당 3회 cap × (N+1) × 60s = 시간 영역 초과 위험. **회피**: 토큰 캐시 24h 영속 의무 + 자동 재기동 *전* 캐시 상태 검증 권고 (옵션).

### A2-Q4 WebSocket 4중 안전망 영역과 race? (HIGH)

**도메인 권고**: **4중 안전망 = 자동 재기동 = 독립 영역 — race 0 보장**.

4중 안전망 영역 (F1 / `_scan_loop` / K stale watcher / `_resubscribe_stale_priority`) 모두 `self._ws is not None` 전제 작동. 자동 재기동 시점 `self._ws = None` (`websocket.py:221` 영속) → 4중 안전망 자연 skip → 자동 재기동 완료 후 `connect()` 재진입 → `self._ws = ClientConnection` → 4중 안전망 자연 재진입.

**위험 시나리오**: 자동 재기동 진행 중 (60s cooldown 영역) K stale watcher (120s 주기) 가 깨어남 → `self._ws is None` → graceful skip → 위험 0. F1 (`_verify_subscriptions_after_reconnect`) 은 `connect()` 내부 task → 자동 재기동 후 `connect()` 재진입 시 자연 재발화.

### A2-Q5 사이클 88 G-REJECT-1 영구 차단 영역 vs 자동 재기동 단일 통합 = 위반?

**도메인 권고**: **위반 0 — 자동 재기동 = 4중 안전망 *추가* 영역 (대체 X) — 명시 권고**.

사이클 88 G-REJECT-1 = "단일 restore 도입 영구 차단 = 4중 안전망 영속". 사이클 92 자동 재기동 (Q30=A `start()` 재호출) 영역 = **4중 안전망 영역과 독립 영역 (lifecycle 영역)** — `MAX_RECONNECT` 도달 (=lifecycle 종료 위험) 시점에 한정 발화 = 4중 안전망 *대체* 아님. **회귀 가드 의무**: G-REJECT-1 영속 검증 (`tests/unit/ast/test_external_llm_reject_patterns.py` AST 영역) 자동 재기동 도입 후에도 4중 안전망 함수 4종 (`_verify_subscriptions_after_reconnect` / `_scan_loop` / `check_and_resubscribe_stale` / `resubscribe_stale_priority`) 영속.

---

## A3 (HIGH) MAX_RECONNECT 한도 자체 영역 검토

**도메인 권고**: **옵션 C (영속) + 자동 재기동 추가 — Q30=A 단일 채택 영역 권고**.

옵션 A (`MAX_RECONNECT=10`, ~17분 누적) = 17 분 동안 KIS LMS 영역 위험 직접 노출 + 시세 0건 시간 직접 연장 = 매매 안전성 영역 *악화*. 옵션 B (`BACKOFF_BASE=0.5`) = 절반 시간 (~16초) + 빈도 ↑ = LMS 위험 직접 ↑. **옵션 C (영속) + 자동 재기동** = 31초 한도 영속 + 60s cooldown + 시간당 3회 cap = 총 ~3 분 회복 시간 + LMS 안전 영역. **트레이더 본능**: KIS 강제 중단 지속 시간 = *5~30초 추정* (도메인 실측, KIS 정책 부재) → 31초 한도 한계 영역 일치.

---

## A4 (MEDIUM) 운영 시간 가드 영역

**도메인 권고**: **옵션 1 (NXT 애프터 15:30+ push) 강력 권고**.

현재 시각 = 09:30 KST (KRX 메인 진입 후 30분, 사이클 92 자문 시점). 시정 push 시점 의제:

- **옵션 1 (강력 권고)**: NXT 애프터 15:30+ push → 익일 (2026-06-11 목) 07:45 진입 시점 시정 영역 자연 적용. CLAUDE.md "운영 가이드" (KRX 메인 시간 09:00~15:30 중 빈번한 push 자제 — `_scan_loop` 5분 race 가능) 영속.
- 옵션 2 (차선): 익일 (2026-06-11 목) 07:45 *전* push → 동일 효과, 단 새벽 push 운영자 부담
- 옵션 3 (비채택): 다음 영업일 07:50 KIS 강제 중단 영역 진단 후 push → 시정 지연 3 영업일

**보강 권고**: push 후 즉시 검증 의무 = 익일 (2026-06-11 목) 07:45 ~ 08:00 영역 SQL READ-ONLY 4 쿼리 (Phase 1 §4) + `[ws_max_reconnect_exceeded_auto_restart]` ERROR 0건 검증.

---

## A5 (MEDIUM) 회귀 가드 매트릭스 권고

### HIGH (6 케이스 — 매매 안전성 직접 영역)

| ID | 영역 | 검증 |
|----|------|------|
| **G-TIME-1** | `TIME_BOOT == time(7, 55)` | AST 정적 |
| **G-TIME-2** | `TIME_BOOT >= TIME_AUTO_START + 10분` | AST 정적 KIS 강제 중단 안전 마진 |
| **G-REC-1** | `MAX_RECONNECT` 도달 → `start()` idempotent 재호출 | freezegun + asyncio mock |
| **G-REC-2** | 자동 재기동 60s cooldown | freezegun 1 + N 회 |
| **G-REC-3** | 시간당 3회 cap | freezegun + 시간당 윈도우 |
| **G-REJECT-1** | 사이클 88 4중 안전망 함수 4종 영속 | AST 정적 (영속 검증) |

### MEDIUM (5 케이스)

| ID | 영역 | 검증 |
|----|------|------|
| G-TIME-3 | `TIME_PRESUBSCRIBE` 동행 이동 (`07:59` 권고) | AST 정적 |
| G-REC-4 | `_reset_daily_state` 동행 가드 (중복 reset 차단) | mock |
| G-REC-5 | `[ws_max_reconnect_exceeded_auto_restart] count=N/3` ERROR | caplog |
| G-BOOT-1 | `_boot()` 동기 영역 영속 (`await self._boot()`) | AST 정적 |
| G-TOKEN-1 | `_preissue_all_tokens` 캐시 hit 우선 영역 영속 | AST 정적 |

### LOW (3 케이스)

| ID | 영역 | 검증 |
|----|------|------|
| G-KST-1 | KST 강제 영속 (사이클 65 H2/H2-bis + 68) | AST 정적 |
| G-AST-1 | 자동 재기동 영역 신규 함수 AST 영구 가드 | AST 정적 |
| G-DOC-1 | `docs/architecture.md` + `docs/kis/rate-limits.md:196` 동행 갱신 | grep |

**합 14 케이스 (HIGH 6 = 43%)**. 사이클 81 답습 패턴 (HIGH ≥ 30% 의무).

---

## A6 (LOW) 사이클 88 G-REJECT 영역 영속 보장 명시

**도메인 권고**: **G-REJECT-1/2/3 모두 영속 의무 + 사이클 92 자동 재기동 = G-REJECT-1 위반 0 명시**.

사이클 88 G-REJECT 3 영역 (`tests/unit/ast/test_external_llm_reject_patterns.py`):
- **G-REJECT-1**: 단일 restore 도입 차단 (4중 안전망 영속) — 사이클 92 자동 재기동 = 4중 안전망 *추가* 영역 → 위반 0
- **G-REJECT-2**: stale 전체 WS 단독 판정 차단 (사이클 29 005935 재현 방지) — 사이클 92 영향 0
- **G-REJECT-3**: SubscriptionRegistry 단일 dict 통합 차단 — 사이클 92 영향 0

**명시 영역**: 사이클 92 Red 명세 + Green 구현 영역에서 G-REJECT-1 AST 검증 영속 확인 의무 (회귀 0 보장).

---

## 정량 권고 매트릭스

| 항목 | 권고값 | 근거 |
|------|--------|------|
| `TIME_BOOT` | `time(7, 55)` | Q28=E 영속 (사용자 결정) + 5 분 마진 (KIS 강제 중단 지속 5~30초 추정) |
| `TIME_AUTO_START` | `time(7, 45)` 영속 | Q29=A 영속 (Python loop 영역, KIS 무관) |
| `TIME_PRESUBSCRIBE` | `time(7, 59)` 권고 (P1 옵션) | `_boot()` 완료 후 1~2 분 마진 (동행 이동) |
| `TIME_PRE_NXT_OPEN` | `time(8, 0)` 영속 | NXT 프리 진입 영역 영향 0 |
| `MAX_RECONNECT` | `5` 영속 | 31초 한도 (KIS 강제 중단 지속 추정 범위 일치) |
| 자동 재기동 cooldown | `60.0s` | 사이클 13-E-2 task lifecycle 답습 + KIS 재기동 완료 안전 마진 |
| 자동 재기동 시간당 cap | `3` | 사이클 24 silent_inactive 2회 답습 보강 + LMS chain 차단 |
| 자동 재기동 일일 cap (옵션) | `5~10` | 24h 윈도우 보강 영역 |

---

## 현 코드와 정합성 — 충돌 0 확인

- **변경 영역**: `scheduler.py:52` `TIME_BOOT` 1 줄 + `scheduler.py:53` `TIME_PRESUBSCRIBE` 1 줄 (옵션 P1) + 자동 재기동 영역 신규 함수 ~50L (`scheduler.py` 또는 신규 `auto_restart_manager.py`)
- **무영향 영역**: `TIME_AUTO_START` / `TIME_PRE_NXT_OPEN` / `TIME_KRX_OPEN_CONFIRM` / `MAX_RECONNECT` / `BACKOFF_BASE` / 4중 안전망 4 함수 / 사이클 88 G-REJECT 3 영역 / 사이클 38 명문화 / 사이클 55 R-1 / 사이클 65 H2/H2-bis / 사이클 67 stale_manager 분해 / 사이클 78 flush
- **사이클 81 답습**: 단일 근본 원인 (KIS 07:50 강제 중단 + `MAX_RECONNECT=5` 31초 한도) + 1~3 줄 시정 + 신규 함수 ~50L + AST 영구 가드 ~14 케이스
- **20+ 사이클 연속 옵션 A 패턴 영속** 후보

---

## 반례 / 한계

### 반례 1: 토큰 캐시 부재 시 자동 재기동 LMS chain 위험

토큰 24h 캐시 (`.token_cache/`) 부재 / 만료 시점 자동 재기동 시:
- 메인 신규 발급 1회 + 보조 N 신규 발급 N회 × 60s gap
- 시간당 3회 cap × (N+1) × 60s = 시간 영역 초과 + LMS chain 위험 직접 노출

**회피**: 토큰 캐시 24h 영속 의무 + 자동 재기동 *전* 캐시 상태 검증 권고 (옵션 보강).

### 반례 2: KIS 강제 중단 지속 시간 30분+ 시나리오

KIS 강제 중단이 30 분 이상 지속 시 (정책 부재 → 가정):
- 자동 재기동 시간당 3회 × 60s cooldown = 3 분 영역 한정 재시도
- 3 분 후 영구 종료 → 사용자 수동 재기동 유일 회복 경로

**회피**: KIS 공식 명문 확보 (Q31=A) 후 정책 수립 — 현재 영역 외 (별개 카드).

### 반례 3: `_boot()` 캐시 miss 누적 6 분 시나리오

`_boot()` 메인 + 보조 5 명 캐시 miss 누적 360 초 = 6 분 → `TIME_PRESUBSCRIBE = 07:59` 영역 안 미완료 → 사전 구독 진입 지연.

**회피**: 토큰 캐시 24h 영속 의무 영속 + CI/CD push 시점 운영 가이드 영속.

---

## 후속 검증 권고 — tdd-engineer / tester 인계

### tdd-engineer Red 명세 권고

- **Red-1** `TIME_BOOT == time(7, 55)` AST 검증 (단순)
- **Red-2** `MAX_RECONNECT` 도달 시 `start()` 재호출 (asyncio mock + freezegun)
- **Red-3** 자동 재기동 60s cooldown freezegun
- **Red-4** 시간당 3회 cap freezegun + 시간당 윈도우
- **Red-5** 사이클 88 G-REJECT-1 영속 AST (회귀 차단)

### tester verify 권고 — 익일 (2026-06-11 목) 07:45~08:00 1h

- **시나리오 V-1** 07:45 자동 시작 → 07:55 `_boot()` 완료 → 07:59 사전 구독 → 08:00 NXT 프리 진입 정상 흐름 (시각 정확 측정)
- **시나리오 V-2** `[ws_max_reconnect_exceeded_auto_restart] count=N/3` ERROR 0건 검증 (정상 영역 가정)
- **시나리오 V-3** `[boot_preissue]` 토큰 발급 ERROR 0건 검증
- **시나리오 V-4** Phase 1 §4 SQL 4 쿼리 직접 실행 (운영 EC2 SSH) — `_boot` + `[ws_*]` + 토큰 발급 영역

---

## 핵심 권고 한 줄 요약

> **Q28=E 채택 영속 + Q29=A + Q30=A + Q31=C 모두 적정**. `TIME_BOOT = time(7, 55)` + `TIME_PRESUBSCRIBE = time(7, 59)` (P1 권고, 동행 이동 의무) + `MAX_RECONNECT=5` 영속 + 자동 재기동 (`start()` idempotent + 60s cooldown + 시간당 3회 cap) — 사이클 88 G-REJECT-1 영속 의무 + 토큰 24h 캐시 영속 의무 + push 시점 NXT 애프터 15:30+ 권고. 회귀 가드 14 케이스 (HIGH 6 = 43%).
