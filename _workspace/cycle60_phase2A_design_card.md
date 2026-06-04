# 사이클 60 Phase 2-A — stale_manager 추출 설계 카드

> **작성**: team-leader (2026-06-04)
> **승인 대기**: 사용자 (domain-expert 자문 Q1~Q4 결정 후 → tdd-engineer Red 발주)
> **선행 카드**: `_workspace/refactor/2026-06-04_review.md` 카드 #2 (재발의, 우선순위 1, HIGH)
> **선례 답습**: 사이클 51 `src/engine/boot_manager.py` (305L, `scheduler` 인자 + 2 줄 wrapper 위임)
> **위험 등급**: HIGH (모듈 간 경계 + WebSocket 4 중 안전망 hot path)
> **CLAUDE.md 절대 규칙 보호**: WebSocket 4 중 안전망 / 우선순위 분리 / silent inactive cap / stale universe 가드 / `_reset_daily_state` 동행

---

## 1. 분리 대상 — 11 함수 + 5 상수

### 1.1 5 상수 (scheduler.py 모듈 상수 → stale_manager.py 이전)

| 상수 | 현 위치 | 값 | 보호 정책 |
|---|---|---|---|
| `MAX_STALE_RETRIES` | L88 | 5 | 연속 N회 초과 stale skip — K stale watcher 핵심 |
| `STALE_FORCE_RETRY_AFTER_SECS` | L95 | 300 | 영구 stale 의심 종목 최소 재시도 간격 (5분, 사이클 29-R1) |
| `STALE_FORCE_RETRY_HOURLY_CAP` | L96 | 12 | 시간당 동일 종목 최대 force_retry — LMS/앱키 정지 위험 차단 |
| `UNIVERSE_LOW_VOLUME_THRESHOLD` | L103 | 10_000 | 당일 누적 체결량 임계 (사이클 32) |
| `SILENT_INACTIVE_FRESH_RATIO_THRESHOLD` | L119 | 0.2 | fresh_ratio < 20% silent 의심 (사이클 24/29-R2) |

**호환 보장**: scheduler.py 가 `from src.engine.stale_manager import MAX_STALE_RETRIES, ...` re-export. 외부 import 경로 호환 layer 유지.

### 1.2 11 함수 (scheduler.py 메서드 → stale_manager.py 함수)

| 함수 | 라인 (현) | 분류 | 패턴 |
|---|---|---|---|
| `_detect_silent_inactive_sessions` | L2434 (~62L) | silent inactive (사이클 29-R2) | sync method |
| `_force_reconnect_session` | L2496 (~83L) | silent inactive 강제 reconnect | async method |
| `_check_and_resubscribe_stale` | L2579 (~221L) | **K stale watcher 핵심** (4 중 안전망 #3) | async method |
| `_build_session_subscription_view` | L2810 (~98L) | stale 진단 read-only | sync method |
| `_emit_stale_session_detail` | L2909 (~43L) | stale 세부 로그 emit | sync method |
| `_delta_unsubscribe_dropped` | L2952 (~52L) | stale 후보 drop 시 unsubscribe | async method |
| `_resubscribe_stale_priority` | L3004 (~100L) | **5분 우선 재구독** (4 중 안전망 #4) | async method |
| `_evaluate_universe_guard` | L3105 (~116L) | **stale universe 가드** (사이클 32) | async method |
| `_refresh_stale_ccnl_cache` | L3222 (~93L) | inquire_ccnl 캐시 | async method |
| `_evict_expired_ccnl` | L3316 (~29L) | ccnl TTL evict | sync method |
| `_prune_force_retry_history` | L3345 (~33L) | force_retry 시간당 cap 정리 | sync method |

**소계**: ~930L (라인 측정 합산, scheduler.py 의 약 24%)

### 1.3 비분리 대상 (scheduler.py 잔류)

| 함수 | 사유 |
|---|---|
| `_stale_watcher_loop` (L2379, ~32L) | scheduler.start() 가 직접 task 등록 — wrapper 보존하되 본체는 `await stale_manager.check_and_resubscribe(scheduler)` 1 줄 |
| `_session_health_loop` (L3378) | silent inactive + heartbeat 통합 task — 별개 lifecycle 책임 |
| `_emit_heartbeat_metrics_all_sessions` (L3409) | health metric, stale 무관 |
| `_ensure_stale_state` + 9 property (L283~357) | StaleTrackerState 호환 layer — scheduler 책임. property 보존 |

---

## 2. stale_manager.py 인터페이스 명세

### 2.1 모듈 위치 & 예상 라인
- **경로**: `src/engine/stale_manager.py` (신규)
- **예상 라인**: ~1,000L (분리 함수 본체 930L + 5 상수 + docstring + import)

### 2.2 함수 시그니처 (사이클 51 boot_manager 패턴 답습)

```python
"""K stale watcher + silent inactive + universe guard (사이클 60 Phase 2-A, 2026-06-04).

CLAUDE.md 절대 규칙 보호 영역:
- WebSocket 4 중 안전망 #3 (K stale watcher 120s) + #4 (resubscribe_stale_priority 5분 우선)
- 우선순위 분리: positions/_pending_next_day_clear HIGH+bypass=True / 그 외 LOW+bypass=False
- silent inactive 시간당 세션당 2회 cap (LMS/앱키 정지 차단)
- stale universe 가드 (사이클 32): stale>5 + today_volume<10_000 자동 unsubscribe + 보유/익일청산 절대 보호
- 모든 함수는 scheduler 인자로 받아 scheduler 상태 (positions/_pending_next_day_clear/kis_ws_pool/_stale_state)
  를 위임 호출. scheduler 의 행위/순서/우선순위 그대로 보존.

호환 layer:
- 5 상수 (MAX_STALE_RETRIES / STALE_FORCE_RETRY_AFTER_SECS / STALE_FORCE_RETRY_HOURLY_CAP /
  UNIVERSE_LOW_VOLUME_THRESHOLD / SILENT_INACTIVE_FRESH_RATIO_THRESHOLD) 모듈 상수
- scheduler.py 가 from src.engine.stale_manager import * (re-export) 으로 외부 호환 보장
"""
from __future__ import annotations

# 5 상수 모듈 이전
MAX_STALE_RETRIES = 5
STALE_FORCE_RETRY_AFTER_SECS = 300
STALE_FORCE_RETRY_HOURLY_CAP = 12
UNIVERSE_LOW_VOLUME_THRESHOLD = 10_000
SILENT_INACTIVE_FRESH_RATIO_THRESHOLD = 0.2

# 11 함수 시그니처 (scheduler 인자 첫번째)
def detect_silent_inactive_sessions(scheduler) -> list[str]: ...
async def force_reconnect_session(scheduler, label: str) -> bool: ...
async def check_and_resubscribe_stale(scheduler) -> None: ...
def build_session_subscription_view(scheduler) -> list[dict]: ...
def emit_stale_session_detail(scheduler, ...) -> None: ...
async def delta_unsubscribe_dropped(scheduler, new_set: set[str]) -> None: ...
async def resubscribe_stale_priority(scheduler, cap: int = 10) -> list[str]: ...
async def evaluate_universe_guard(scheduler, candidate_tickers: list[str]) -> None: ...
async def refresh_stale_ccnl_cache(scheduler, ...) -> None: ...
def evict_expired_ccnl(scheduler, now) -> None: ...
def prune_force_retry_history(scheduler, ...) -> None: ...
```

### 2.3 scheduler.py wrapper 패턴 (사이클 51 boot_manager 동일)

```python
# scheduler.py 잔류 wrapper 예시
async def _check_and_resubscribe_stale(self) -> None:
    from src.engine import stale_manager
    await stale_manager.check_and_resubscribe_stale(self)

def _detect_silent_inactive_sessions(self) -> list[str]:
    from src.engine import stale_manager
    return stale_manager.detect_silent_inactive_sessions(self)
```

**호환 layer**: 11 wrapper 모두 *2 줄 위임*. scheduler.py 외부 호출 (start / _stale_watcher_loop / _scan_loop / _board_transition_loop 등) 호출 경로 보존.

---

## 3. 회귀 가드 — tdd-engineer 작성 영역

### 3.1 카테고리별 가드 수 (예상)

| 카테고리 | 가드 수 | 영역 |
|---|---|---|
| 위임 1회 검증 | 11 케이스 | wrapper 가 stale_manager 단일 호출 — `unittest.mock.patch` |
| 5 상수 동일성 | 5 케이스 | `from src.engine.scheduler import MAX_STALE_RETRIES` == `from src.engine.stale_manager import MAX_STALE_RETRIES` 동일성 |
| 호출 순서 보존 | 4 케이스 | (a) `_stale_watcher_loop` → `check_and_resubscribe_stale` 1회 / (b) `_scan_loop` → `evaluate_universe_guard` 순서 / (c) `_board_transition_loop` → `delta_unsubscribe_dropped` 순서 / (d) `_session_health_loop` → `detect_silent_inactive_sessions` |
| WebSocket 4 중 안전망 | 4 케이스 | F1 / `_scan_loop` 5분 / K stale watcher 120s / `resubscribe_stale_priority` 5분 — 행위 보존 |
| 우선순위 분리 (사이클 29-R3) | 2 케이스 | positions/_pending HIGH+bypass=True / 그 외 LOW+bypass=False |
| silent inactive 시간당 2회 cap | 1 케이스 | `_force_reconnect_session` 3 회 호출 시 3번째 skip |
| universe 가드 보호 (사이클 32) | 2 케이스 | (a) 보유 종목 unsubscribe 안 됨 / (b) `_pending_next_day_clear` 종목 unsubscribe 안 됨 |
| `_reset_daily_state` 동행 reset | 1 케이스 | scheduler.`_reset_daily_state` 호출 후 `_stale_state.reset_daily()` 작동 (이전과 동일) |
| ccnl 캐시 TTL evict | 1 케이스 | 만료 항목 evict + 미만료 보존 |
| force_retry 시간당 cap | 1 케이스 | 동일 종목 13번째 force_retry 시 skip |

**총 32 케이스** (예상). 사이클 51 boot_manager 16 케이스의 2배 — stale 영역의 WebSocket 4 중 안전망 + 우선순위 + cap + 가드 다층 보호 필요.

### 3.2 회귀 0건 통과 기준
- 백엔드 1844 PASS (사이클 58 V-2 기준) → 1844 + 32 = **1876 PASS** 유지
- WebSocket 통합 시나리오 (`tests/integration/test_*websocket*.py`) 회귀 0건
- `_scan_loop` E2E 회귀 0건

---

## 4. domain-expert 자문 의뢰 (HIGH 의무 — Q1~Q4)

team-leader 는 사용자 결정 전 다음 4 가지 핵심 질문에 domain-expert 자문이 필수.

### Q1: WebSocket 4 중 안전망 호출 시점/순서 영향
- K stale watcher (120s 주기) 가 `check_and_resubscribe_stale` 함수 호출 시점 보존 보장?
- silent inactive `_force_reconnect_session` 의 시간당 세션당 2회 cap 이 모듈 이동 후에도 정확히 작동?
- `resubscribe_stale_priority` 의 5분 우선 재구독 timing 영향 없음?

### Q2: `_reset_daily_state` 동행 stale_state.reset_daily 호출 순서
- scheduler.`_reset_daily_state` 가 `_stale_state.reset_daily()` 를 호출 (L3828). 모듈 분해 후에도 이 순서 보존?
- stale_manager 함수가 `_stale_state` 를 통한 위임만 하므로 reset 호출 위치는 scheduler 잔류 — 안전?

### Q3: 5 상수 모듈 이동 시 import 경로 변경의 행위 영향
- `from src.engine.scheduler import MAX_STALE_RETRIES` 외부 사용처 영구 호환 보장 필요?
- 회귀 가드 #2 (5 상수 동일성) 으로 충분? 추가 보강 필요?

### Q4: 11 함수 *전체 묶음 이동* vs *2 단계 분할*
- **옵션 A (전체)**: 사이클 60 Phase 2-A 1 사이클로 11 함수 일괄 이동 (~930L, scheduler.py −24%)
- **옵션 B (2 단계)**: 사이클 60 Phase 2-A1 (read-only 4 함수: `_build_session_subscription_view` / `_emit_stale_session_detail` / `_evict_expired_ccnl` / `_prune_force_retry_history` — ~203L) → 사이클 60 Phase 2-A2 (hot path 7 함수: 나머지 — ~727L)
- 위험 분산 + 회귀 격리 효과 vs 1 사이클 분해 효율 — domain-expert 권고?

---

## 5. 사용자 결정 요청 (Q1~Q5 분류 선택지)

domain-expert 자문 회신 후 사용자에게 다음 분류 결정 요청:

| 질문 | 옵션 | 권고 |
|---|---|---|
| Q1 호출 시점 영향 | RECOMMEND / CONSIDER / AVOID | (자문 후 표시) |
| Q2 reset 순서 보존 | RECOMMEND / CONSIDER / AVOID | (자문 후 표시) |
| Q3 5 상수 호환 | RECOMMEND / CONSIDER / AVOID | (자문 후 표시) |
| Q4 분할 vs 일괄 | A (일괄) / B (2단계) | (자문 후 표시) |
| Q5 push 시점 | 본 사이클 발주 후 NXT 애프터 / 익일 _boot 전 | NXT 애프터 (15:30~20:00) 권장 |

---

## 6. 절대 깨지 말 것 (체크리스트)

CLAUDE.md 7 종 + 사이클 32/29-R1/R2/R3/24 신규:

- [ ] 체결통보 구독 (H0STCNI0/H0STCNI9) 제거 금지 (본 카드 영역 외 — stale 영역 무관)
- [ ] uvicorn 단일 워커 (영향 없음)
- [ ] WebSocket 4 중 안전망 F1 + scan_loop + K stale watcher + resubscribe_stale_priority — wrapper 보존
- [ ] K stale watcher 우선순위 분리 (positions/_pending HIGH+bypass=True / 그 외 LOW+bypass=False)
- [ ] silent inactive 시간당 세션당 2회 cap
- [ ] stale universe 가드 (사이클 32) — 보유/익일청산 절대 보호 + `_reset_daily_state` 동행 clear
- [ ] KST 강제 (모든 시각 KST timezone 명시)
- [ ] `_subscriptions` ACK 정합성 가드 (orphan ACK race 차단)

---

## 7. 발주 순서 (사용자 확정 후)

1. **domain-expert 자문 회신** (Q1~Q4 RECOMMEND/CONSIDER/AVOID + Q5 push 시점)
2. **사용자 채택 결정** (자문 회신 정리 → 사용자 의사 반영)
3. **tdd-engineer Red** (`_workspace/red/cycle60_phase2A_stale_manager.md` 32 케이스 회귀 가드)
4. **backend-dev Green** (`src/engine/stale_manager.py` 신규 + scheduler.py wrapper 11 곳 + 5 상수 re-export)
5. **test-impact-index 갱신** (Python AST + 영향 인덱스)
6. **tester Verify** (`trading-test` 스킬 — WebSocket 4 중 안전망 통합 시나리오 + CI 시뮬레이션)
7. **sync-docs** (HARNESS_CHANGELOG.md + `src/engine/CLAUDE.md` 모듈 맵 + 루트 CLAUDE.md 변경 이력)
8. **사용자 명시 지시 후 commit + push** (메모리 정책 — 사용자 commit 명시 전 금지)

---

## 8. 예상 효과

- `scheduler.py` 3,880 → **~2,950** (-930L, **-24%**)
- 후속 카드 #3 settlement_manager 의존성 해소 (stale_state.reset_daily 위임 명확화)
- stale 사이클 추가 비용 -50% (단일 모듈 격리)
- 사이클 51 + 60 누적 scheduler 분해: 4,185L → ~2,950L (-30%)

---

## 9. 위험 평가 매트릭스

| 영역 | 위험 | 완화 |
|---|---|---|
| WebSocket 4 중 안전망 호출 timing | HIGH | 가드 4 케이스 + 통합 시나리오 회귀 0건 + domain-expert Q1 자문 |
| `_stale_state` 호환 layer 9 property | MEDIUM | scheduler 잔류 + property 본체 변경 0 |
| 5 상수 외부 import 호환 | LOW | re-export + 가드 5 케이스 |
| 우선순위 분리 회귀 | HIGH | 가드 2 케이스 + WebSocket 통합 시나리오 |
| silent inactive cap 회귀 | MEDIUM | 가드 1 케이스 + 시간 freeze 테스트 |
| universe 가드 보호 회귀 | HIGH | 가드 2 케이스 + 보유 종목 명시 보호 |
| ccnl 캐시 race | LOW | 가드 1 케이스 (TTL evict) |
| `_reset_daily_state` 동행 reset | MEDIUM | scheduler 잔류 + 가드 1 케이스 |

→ HIGH 3 영역 모두 가드 + domain-expert 자문 + 통합 시나리오 3 중 보호.
