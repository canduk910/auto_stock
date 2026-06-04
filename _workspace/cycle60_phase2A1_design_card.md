# 사이클 60 = Phase 2-A1 설계 카드 (단독)

> **작성**: team-leader (2026-06-04 16:10 KST, Phase 2-A1 단독 좁힘)
> **승인 상태**: 사용자 채택 — 옵션 A (자문 결과 전부 적용) + Q4 옵션 B (3 단계 분할)
> **선행 자문**: `_workspace/cycle60_phase2A_domain_response.md` (Q1~Q7 전부 반영)
> **상위 설계**: `_workspace/cycle60_phase2A_design_card.md` (사이클 60~62 누적 통합 — Phase 2-A1/A2/A3 분리 후 본 카드가 사이클 60 한정)
> **위험 등급**: **LOW** (read-only 진단 4 함수 + ccnl 캐시 evict 1 함수 — 매매 hot path 무영향)
> **CLAUDE.md 절대 규칙 충돌**: 없음 (진단 로그 + 캐시 영역만)
> **push 시점**: **NXT 애프터 18:00 이후 허용** (Q5 자문 권고)

---

## 1. 범위 좁힘 — Phase 2-A1 단독 (5 함수 ~262~296L)

### 1.1 자문 권고 기반 분류 인용 (응답서 §Q4 권고)

> "Phase 2-A1 (LOW 위험, ~262L): read-only 4 함수 + ccnl TTL evict + force_retry prune 정리 함수
> `_build_session_subscription_view` / `_emit_stale_session_detail` / `_evict_expired_ccnl` / `_prune_force_retry_history` / `_refresh_stale_ccnl_cache`
> 회귀 가드 ~10 케이스 (단순 read + 캐시 evict)
> 위험: 진단 로그 영향만 (매매 hot path 무영향)"

### 1.2 Phase 2-A1 분리 5 함수 (확정)

| 함수 | 현 위치 | 라인 (실측) | 분류 | 위험 |
|---|---|---|---|---|
| `_build_session_subscription_view` | L2810 | ~98 | 진단 read-only (세션별 구독 뷰) | LOW |
| `_emit_stale_session_detail` | L2909 | ~43 | 진단 read-only (stale 세부 로그 emit) | LOW |
| `_refresh_stale_ccnl_cache` | L3222 | ~93 | KIS inquire_ccnl 캐시 갱신 (read-only API 호출) | LOW |
| `_evict_expired_ccnl` | L3316 | ~29 | ccnl 캐시 TTL evict (내부 정리) | LOW |
| `_prune_force_retry_history` | L3345 | ~33 | force_retry 시간당 cap 정리 (내부 정리) | LOW |

**합계**: ~296L (scheduler.py 의 ~7.6%)

**잔류 — 사이클 61/62 분리**:
- Phase 2-A2 (사이클 61, MEDIUM): `_detect_silent_inactive_sessions` (L2434), `_force_reconnect_session` (L2496), `_evaluate_universe_guard` (L3105), `_delta_unsubscribe_dropped` (L2952) — ~365L
- Phase 2-A3 (사이클 62, HIGH): `_check_and_resubscribe_stale` (L2579), `_resubscribe_stale_priority` (L3004) — ~321L

---

## 2. 적용 자문 권고 (Q1~Q7 전부 반영)

### Q1 CONSIDER — 회귀 가드 +4 케이스 + 9 property 외부 접근 grep

본 사이클 (Phase 2-A1) 범위 *내* 적용:
- **Q1-G1**: `_stale_watcher_loop` 호출 주기 120s 보존 가드 (1 케이스) — A1 범위 *밖* (hot path 함수 미이동) **→ A3 사이클 62로 이연**
- **Q1-G2**: `_force_reconnect_session` cap dict 동일성 가드 — A1 범위 *밖* (silent inactive 함수 미이동) **→ A2 사이클 61로 이연**
- **Q1-G3**: K stale watcher → `_emit_stale_session_detail` 호출 순서 가드 — A1 범위 *내* (emit 함수 이동 대상) **→ 본 사이클 적용 (1 케이스)**
- **Q1-G4**: `_resubscribe_stale_priority(cap=10)` cap 인자 전달 가드 — A1 범위 *밖* (resubscribe 함수 미이동) **→ A3 사이클 62로 이연**

**9 property 외부 접근 grep** (tdd-engineer 사전 점검 의무):
- `_stale_retry_count` / `_stale_last_resubscribe_at` / `_stale_force_retry_history` / `_silent_inactive_first_seen` / `_silent_inactive_recovery_count` / `_universe_excluded_today` / `_last_ccnl_cache` (7 property + `_ensure_stale_state` + property setter 9개)
- tdd-engineer 가 Red 작성 *전* `grep -rn "_stale_retry_count\|_stale_last_resubscribe_at\|_stale_force_retry_history\|_silent_inactive_first_seen\|_silent_inactive_recovery_count\|_universe_excluded_today\|_last_ccnl_cache" src/ tests/ frontend/src/` 실행 + 외부 접근 보고
- 외부 접근 있을 시 stale_manager 함수가 *반드시 property 우회 없이 동일 경로* 읽기 (A1 5 함수 중 `_refresh_stale_ccnl_cache` 가 `_last_ccnl_cache` 접근 + `_prune_force_retry_history` 가 `_stale_force_retry_history` 접근 — 2 영역 보존 확인 필수)

### Q2 RECOMMEND — `_reset_daily_state` 동행 6 필드 검증

A1 5 함수 모두 이동 대상이지만 `_reset_daily_state` 자체는 scheduler 잔류. 다만 본 사이클에서 `_stale_state.reset_daily()` 가 *모든 stale 영역 필드 초기화* 보장 가드 1 케이스 추가:

- **Q2-G1**: `scheduler._reset_daily_state()` 호출 후 6 필드 동시 검증 (응답서 §Q2 인용)
  ```python
  assert scheduler._stale_state.retry_count == {}
  assert scheduler._stale_state.last_resubscribe_at == {}
  assert scheduler._stale_state.force_retry_history == {}
  assert scheduler._silent_inactive_first_seen == {}
  assert scheduler._silent_inactive_recovery_count == {}
  assert scheduler._universe_excluded_today == set()
  ```
- **추가 가드**: `dataclasses.fields(StaleTrackerState)` 와 reset 후 비교 — 필드 누락 가드 1 케이스

### Q3 RECOMMEND — 5 상수 re-export + 의존성 역전 정적 검증 + 5→10 확장

본 사이클 (Phase 2-A1) 범위:
- **5 상수 모듈 이동** (A1 시점에 이동 확정 — A1 의 `_refresh_stale_ccnl_cache` / `_prune_force_retry_history` 가 `STALE_FORCE_RETRY_AFTER_SECS` / `STALE_FORCE_RETRY_HOURLY_CAP` 사용)
- **5 상수 동일성 가드** (Q3-G1~G5, 5 케이스): `from src.engine.scheduler import X as A; from src.engine.stale_manager import X as B; assert A is B` (`is` 동일성)
- **Q3-G6 의존성 역전 정적 검증** (1 케이스): `ast` 모듈로 `src/engine/stale_manager.py` 의 `from src.engine.scheduler import` / `import scheduler` 검색 + 발견 시 fail
- **추가 권고 5→10 확장 검토** (backend-dev 가 Green 시점 판단):
  - 응답서 §Q3 권고: `SILENT_INACTIVE_MIN_SUBSCRIBED` / `SILENT_INACTIVE_PERSIST_SECS` / `SILENT_INACTIVE_RECOVERY_CAP_PER_HOUR` / `SILENT_INACTIVE_RECOVERY_WINDOW_SECS` / `STALE_FRESHNESS_SECS`
  - **본 사이클 결정**: A1 사용 상수만 우선 이동 (5 종 확정). 나머지 5 종은 A2 사이클 61 시점 silent inactive 함수 이동 시 동시 이동 권고 (응답서 §Q3 "관련 상수 그룹화" 의도 답습)

### Q4 — A1 단독 진행 (사이클 60)
사이클 60 = Phase 2-A1 = 5 함수 ~296L. A2/A3 는 별도 사이클 61/62.

### Q5 push 시점 — NXT 애프터 18:00 이후 허용
- A1 LOW 라 NXT 애프터 push 허용 (응답서 §Q5 대안 인용: "Phase 2-A1 (LOW): NXT 애프터 18:00 이후 push 허용")
- 본 사이클 검증 + 문서 동기화 + commit + push 모두 NXT 시간대 내 완료 목표 (현재 16:10 → 18:00 이후 push 시점 가능, 약 1h 50min 여유)

### Q6 별개 카드 #11 발의 (본 사이클 종료 후)
- 보드 전환 ↔ K stale watcher race (`_board_transition_lock: asyncio.Lock`) → A1 범위 *밖*
- `_workspace/refactor/2026-06-04_review.md` 에 카드 #11 추가 (또는 별도 `_workspace/cycle60_phase2A_card11_board_transition_mutex.md`)
- **본 사이클 종료 후** team-leader 가 발의

### Q7 본질 차이 3 가지 인지
- stale = 영구 hot path (boot 와 다름)
- A3 (62) 진행 시점에 별도 자문 + 주말 push 정책 적용
- 본 사이클 (A1) 은 read-only + 캐시 영역만 → 본질 차이 영향 *낮음*

---

## 3. stale_manager.py 인터페이스 명세 (A1 한정)

### 3.1 모듈 위치 & 예상 라인

- **경로**: `src/engine/stale_manager.py` (신규)
- **예상 라인**: ~350~400L
  - A1 5 함수 본체 ~296L
  - 5 상수 모듈 상수 + docstring + imports ~50L
  - 향후 A2/A3 함수 이동 시 동일 모듈에 추가 (모듈 분리 X)

### 3.2 함수 시그니처 (사이클 51 boot_manager 패턴 답습 — scheduler 인자 첫번째)

```python
"""K stale watcher 진단 + 캐시 정리 (사이클 60 Phase 2-A1, 2026-06-04).

본 모듈은 사이클 60 Phase 2-A1 (LOW) 5 함수 + 5 상수만 포함.
사이클 61 (Phase 2-A2, MEDIUM): silent inactive + universe guard 4 함수 추가 예정.
사이클 62 (Phase 2-A3, HIGH): K stale watcher 핵심 2 함수 추가 예정.

CLAUDE.md 절대 규칙 보호 영역 (A1 한정):
- 5 상수 동일성 (re-export 호환): MAX_STALE_RETRIES / STALE_FORCE_RETRY_AFTER_SECS /
  STALE_FORCE_RETRY_HOURLY_CAP / UNIVERSE_LOW_VOLUME_THRESHOLD / SILENT_INACTIVE_FRESH_RATIO_THRESHOLD
- ccnl 캐시 TTL evict + force_retry 시간당 cap 정리 (A1 범위 + A2/A3 시점 호환)
- `_stale_state` 9 property 경로 보존 (`_last_ccnl_cache` + `_stale_force_retry_history` 접근)
- KST 강제 (모든 시각 KST timezone 명시)

호환 layer:
- scheduler.py 가 from src.engine.stale_manager import (5 상수) re-export 으로 외부 호환 보장
- scheduler.py 의 5 wrapper 메서드 (2 줄 위임) 보존 — 외부 호출 경로 영향 0

A1 진행 후속 (사이클 61/62):
- A2 시점: silent inactive 4 함수 + 5 상수 추가 (SILENT_INACTIVE_MIN_SUBSCRIBED 등)
- A3 시점: K stale watcher 2 함수 + Q6 별개 카드 (#11) 보드 전환 mutex 적용
"""
from __future__ import annotations

# 5 상수 모듈 이전 (A1 단계)
MAX_STALE_RETRIES = 5
STALE_FORCE_RETRY_AFTER_SECS = 300
STALE_FORCE_RETRY_HOURLY_CAP = 12
UNIVERSE_LOW_VOLUME_THRESHOLD = 10_000
SILENT_INACTIVE_FRESH_RATIO_THRESHOLD = 0.2

# A1 5 함수 시그니처
def build_session_subscription_view(scheduler) -> list[dict]: ...
def emit_stale_session_detail(scheduler, ...) -> None: ...
async def refresh_stale_ccnl_cache(scheduler, ...) -> None: ...
def evict_expired_ccnl(scheduler, now) -> None: ...
def prune_force_retry_history(scheduler, ...) -> None: ...
```

### 3.3 scheduler.py wrapper 패턴 (5 wrapper, 사이클 51 boot_manager 동일)

```python
# scheduler.py 잔류 wrapper 예시 (각 2 줄)
def _build_session_subscription_view(self) -> list[dict]:
    from src.engine import stale_manager
    return stale_manager.build_session_subscription_view(self)

def _emit_stale_session_detail(self, ...) -> None:
    from src.engine import stale_manager
    stale_manager.emit_stale_session_detail(self, ...)

async def _refresh_stale_ccnl_cache(self, ...) -> None:
    from src.engine import stale_manager
    await stale_manager.refresh_stale_ccnl_cache(self, ...)

def _evict_expired_ccnl(self, now) -> None:
    from src.engine import stale_manager
    stale_manager.evict_expired_ccnl(self, now)

def _prune_force_retry_history(self, ...) -> None:
    from src.engine import stale_manager
    stale_manager.prune_force_retry_history(self, ...)
```

**호환 layer**: 5 wrapper 모두 *2 줄 위임*. scheduler.py 외부 호출 (`_check_and_resubscribe_stale` 등 A2/A3 호출자) 경로 보존.

---

## 4. 회귀 가드 — A1 한정 (~12~15 케이스 + Q1 +1 + Q2 +1)

자문 응답서 §Q4 권고 "회귀 가드 ~10 케이스 (단순 read + 캐시 evict)" + Q1-G3 1 케이스 + Q2-G1 1 케이스 + Q3-G1~G5 5 케이스 + Q3-G6 1 케이스 = **18 케이스** (혹은 응답서 권고 10 + Q 가드 5 = 15 케이스, tdd-engineer 가 본 명세 기반으로 조정).

### 4.1 카테고리별 가드 수 (예상)

| 카테고리 | 케이스 | 영역 |
|---|---|---|
| **A 위임 1회 검증** (A1 5 함수) | 5 | wrapper 가 stale_manager 단일 호출 — `unittest.mock.patch` |
| **B 5 상수 동일성** (Q3-G1~G5) | 5 | `scheduler.X is stale_manager.X` + 값 검증 |
| **C 호출 순서 보존** (A1 범위) | 2 | (a) K stale watcher → `_emit_stale_session_detail` 호출 순서 (Q1-G3) / (b) `_refresh_stale_ccnl_cache` → `_evict_expired_ccnl` 호출 순서 |
| **D 의존성 역전 정적 검증** (Q3-G6) | 1 | `ast` 모듈로 stale_manager.py 의 scheduler.py import 검색 → 발견 시 fail |
| **E ccnl TTL evict** | 1 | 만료 항목 evict + 미만료 항목 보존 (freezegun) |
| **F force_retry 시간당 cap** | 1 | 동일 종목 13번째 force_retry 시 skip (cap=12, freezegun) |
| **G `_reset_daily_state` 동행 reset** (Q2-G1) | 1 | 6 필드 동시 검증 + dataclass 필드 누락 가드 |
| **H import sanity** | 1 | `from src.engine import stale_manager` 성공 + 5 함수 + 5 상수 노출 |
| **합계** | **17** | LOW 11 / MEDIUM 5 / HIGH 1 (G reset 동행) |

### 4.2 통과 기준

- 백엔드 1844 PASS (사이클 58 V-2 기준) → 1844 + 17 = **1861 PASS** 유지
- WebSocket 통합 시나리오 회귀 0건 (A1 범위 *밖* 함수 그대로 작동)
- `_scan_loop` E2E 회귀 0건
- 영향 인덱스 갱신 (`test-impact-index` 스킬)

---

## 5. 작업 순서 (확정)

1. **team-leader (현재 — 완료)**: A1 5 함수 확정 + 본 설계 카드 보강
2. **tdd-engineer Red 발주** (다음 단계):
   - 9 property 외부 접근 grep 사전 점검 (Q1 권고)
   - `_workspace/red/cycle60_phase2A1_stale_manager.md` 작성 (17 케이스)
3. **backend-dev Green 발주**:
   - `src/engine/stale_manager.py` 신규 (A1 5 함수 + 5 상수)
   - scheduler.py 5 wrapper 2 줄 위임 + 5 상수 re-export
   - 영향 인덱스 갱신
4. **tester Verify** (`trading-test` 스킬):
   - 4 카테고리 분리 측정 (unit/engine + unit/db + integration + contract)
   - 1844 → 1861 PASS 회귀 0건
   - WebSocket 4 중 안전망 통합 시나리오 (A1 범위 *밖* 함수 회귀 0건)
   - CI 시뮬레이션 (사이클 60 hotfix 영구 가드 작동 검증)
   - push 후 CI conclusion 명시 확인
5. **sync-docs**:
   - `docs/HARNESS_CHANGELOG.md` 사이클 60 행 추가
   - `src/engine/CLAUDE.md` 모듈 맵에 `stale_manager.py` 신규 행 + scheduler.py 행 갱신
   - 루트 `CLAUDE.md` 변경 이력 표 행 추가
6. **사용자 명시 commit + push 지시 대기** (메모리 정책)

---

## 6. 후속 카드 발의 (본 사이클 종료 후)

| 카드 | 사이클 | 위험 | push 시점 |
|---|---|---|---|
| Phase 2-A2 (silent inactive + universe guard) | 사이클 61 | MEDIUM | 익일 _boot 전 또는 주말 |
| Phase 2-A3 (K stale watcher 핵심) | 사이클 62 | HIGH | **주말 필수** + 월요일 _boot 1h tester verify |
| #11 보드 전환 mutex (Q6 별개 카드) | 사이클 ?? | MEDIUM-HIGH | A2 진행 *전* 발의 권고 (보드 전환 ↔ silent inactive race 가능성) |
| #3 settlement_manager 의존성 재평가 | 사이클 63+ | HIGH | A3 완료 후 |

---

## 7. 절대 깨지 말 것 (체크리스트)

CLAUDE.md 7 종 + 사이클 32/29-R1/R2/R3/24 신규:

- [x] 체결통보 구독 (H0STCNI0/H0STCNI9) 영역 무관 (본 카드 외)
- [x] uvicorn 단일 워커 영향 0
- [x] WebSocket 4 중 안전망 — A1 5 함수는 진단/캐시 영역, hot path 미이동 → 행위 보존
- [x] K stale watcher 우선순위 분리 — A1 범위 *밖* 함수 (A3 사이클 62)
- [x] silent inactive 시간당 세션당 2회 cap — A1 범위 *밖* (A2 사이클 61)
- [x] stale universe 가드 (보유/익일청산 절대 보호) — A1 범위 *밖* (A2 사이클 61)
- [x] `_reset_daily_state` 동행 reset — 본 사이클 가드 1 케이스 (Q2-G1 6 필드)
- [x] KST 강제 (모든 시각 KST timezone 명시)
- [x] `_subscriptions` ACK 정합성 가드 — A1 범위 *밖* (read-only 진단 함수만 이동)

---

## 8. 예상 효과

- `scheduler.py` 3,880 → ~3,584 (-296L, **-7.6%**)
- Phase 2-A1+A2+A3 누적 (사이클 60+61+62): 3,880 → ~2,898 (-25%) 예상
- 사이클 51 + 60+61+62 누적: 4,185L → ~2,898 (-31%)
- 진단/캐시 영역 단일 모듈 격리 → 향후 A2/A3 점진 이동 시 모듈 라인 자연 증가

---

## 9. 위험 평가 매트릭스 (A1 한정)

| 영역 | 위험 | 완화 |
|---|---|---|
| 진단 read-only 함수 행위 보존 | LOW | 가드 5 케이스 (위임 1회) + 호출 순서 가드 (Q1-G3) |
| 5 상수 외부 import 호환 | LOW | re-export + 가드 5 케이스 (`is` 동일성) |
| 의존성 역전 (stale_manager → scheduler 역참조) | LOW | 정적 검증 가드 1 케이스 (Q3-G6) |
| ccnl TTL evict race | LOW | 가드 1 케이스 (freezegun) |
| force_retry cap 회귀 | LOW | 가드 1 케이스 (freezegun) |
| `_reset_daily_state` 동행 reset | HIGH | 가드 1 케이스 (Q2-G1 6 필드 동시 검증) |
| `_stale_state` 9 property 외부 접근 회귀 | MEDIUM | tdd-engineer Red 전 grep 사전 점검 (Q1 권고) |

→ HIGH 1 영역 (reset 동행) 만 가드 + 단위 케이스 보호. 매매 hot path 영향 0.

---

## 10. 운영 안전 가드 재확인

- **현재 시각**: 2026-06-04 (목) 16:10 KST = NXT 애프터 진입 직전 (15:30~)
- **push 가능 시간**: 18:00 이후 (Q5 자문 권고, A1 LOW 한정)
- **18:00 까지 작업 여유**: 약 1h 50min — tdd-engineer Red + backend-dev Green + tester Verify + sync-docs 모두 완료 가능 목표
- **회귀 발생 시 hotfix**: NXT 애프터 시간대 내 즉시 가능 (LOW 카드 특성)
- **사용자 commit 명시 전 git 작업 금지** (메모리 정책)

---

## 부록 — A1 5 함수 위치 인용 (scheduler.py 실측)

```
L2810: def _build_session_subscription_view(self) -> list[dict]:        # ~98L (~L2908 까지)
L2909: def _emit_stale_session_detail(self, ...):                       # ~43L (~L2951 까지)
L3222: async def _refresh_stale_ccnl_cache(self, ...):                  # ~93L (~L3315 까지)
L3316: def _evict_expired_ccnl(self, now):                              # ~29L (~L3344 까지)
L3345: def _prune_force_retry_history(self, ...):                       # ~33L (~L3377 까지)
```

**합계**: ~296L (scheduler.py 의 ~7.6%)
