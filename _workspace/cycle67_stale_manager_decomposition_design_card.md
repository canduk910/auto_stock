# 사이클 67 설계 카드 — `stale_manager.py` 1,099L sub-module 분해 (카드 #14 MEDIUM)

> **작성**: team-leader (트레이딩 데스크 감독자)
> **작성일**: 2026-06-06 (토)
> **근거**: refactor-review 카드 #14 (MEDIUM, 사이클 49~66 누적 18 사이클 + hotfix 4 영역 종결 후 첫 refactor 사이클)
> **선행 의존**: 사이클 60 A1 / 61 A2 / 63 A3 / 66 시정 (3 단계 누적 11 함수 + 10 상수 + 78 회귀 가드 영속)
> **위험 등급**: **MEDIUM** (행위 보존 refactor, 단 78 케이스 영향 영역 + K stale watcher 본체 HIGH hot path)
> **push 시점 권고**: **일요일 (2026-06-07)** — KRX/NXT 휴장 + production 변경 영역 0 의무

---

## 1. 배경 — 사이클 49~66 회고

### 1.1 누적 진척
| 사이클 | Phase | 작업 영역 | 산출 |
|--------|-------|---------|------|
| 60 | A1 (read-only) | 5 함수 + 5 상수 (build_session_subscription_view / emit_stale_session_detail / refresh_stale_ccnl_cache / evict_expired_ccnl / prune_force_retry_history) | 18 회귀 가드 |
| 61 | A2 (silent inactive + universe) | 4 함수 + 5 상수 (detect_silent_inactive_sessions / force_reconnect_session / delta_unsubscribe_dropped / evaluate_universe_guard) | 20 회귀 가드 |
| 63 | A3 (K stale watcher 본체) | 2 함수 (check_and_resubscribe_stale / resubscribe_stale_priority) | 29 회귀 가드 |
| 66 | A3 시정 | resubscribe_stale_priority L1023~1057 (priority 분리 *후* cap) | 11 회귀 가드 |
| **누적** | — | **11 함수 + 10 상수 + 1,099L** | **78 회귀 가드** |

### 1.2 사이클 67 명세 (현재)
`src/engine/stale_manager.py` 1,099L (실측) 단일 모듈 → **4 sub-module 분해**:
- 책임 영역 명확 분리 (진단 read-only / silent inactive 복구 / universe 가드 / K stale watcher 본체)
- scheduler.py 11개 위임 wrapper 시그너처 변경 0 의무
- 78 회귀 가드 patch 경로 일관 갱신 (15 `patch("src.engine.stale_manager.*")` 영역)
- 사이클 60 G-3 / 사이클 63 D-1 / 사이클 66 AST 등 영구 가드 영속

---

## 2. 4 sub-module 책임 매트릭스

### 2.1 분해 청사진

| sub-module | 라인 (예상) | 함수 | 상수 | 책임 영역 | 사이클 출처 |
|-----------|----------|-----|------|---------|-----------|
| **`stale_diagnostics.py`** | ~350L | 5 (build_session_subscription_view / emit_stale_session_detail / refresh_stale_ccnl_cache / evict_expired_ccnl / prune_force_retry_history) | 5 (MAX_STALE_RETRIES / STALE_FORCE_RETRY_AFTER_SECS / STALE_FORCE_RETRY_HOURLY_CAP / STALE_FRESHNESS_SECS / 진단 한정) | 진단 read-only + CCNL 캐시 + force_retry 정리 | 사이클 60 A1 |
| **`stale_session_recovery.py`** | ~280L | 3 (detect_silent_inactive_sessions / force_reconnect_session / delta_unsubscribe_dropped) | 4 (SILENT_INACTIVE_FRESH_RATIO_THRESHOLD / MIN_SUBSCRIBED / PERSIST_SECS / RECOVERY_CAP_PER_HOUR / RECOVERY_WINDOW_SECS) | silent inactive 감지 + force reconnect + delta unsubscribe | 사이클 61 A2 (3/4) |
| **`stale_universe_guard.py`** | ~150L | 1 (evaluate_universe_guard) | 1 (UNIVERSE_LOW_VOLUME_THRESHOLD) | universe stale 가드 (10K 임계 + ccnl 보강) | 사이클 32 + 61 (1/4) |
| **`stale_watcher_core.py`** | ~320L | 2 (check_and_resubscribe_stale / resubscribe_stale_priority) | 0 (상수 의존만) | K stale watcher 본체 + 5분 우선순위 재구독 (사이클 66 시정 영속) | 사이클 63 A3 + 66 |

### 2.2 함수 ↔ sub-module 매핑 (1:1)

```
stale_manager.py (1,099L 현재)
├─ build_session_subscription_view (L59-160)    → stale_diagnostics.py
├─ emit_stale_session_detail (L161-208)         → stale_diagnostics.py
├─ refresh_stale_ccnl_cache (L209-307)          → stale_diagnostics.py
├─ evict_expired_ccnl (L308-341)                → stale_diagnostics.py
├─ prune_force_retry_history (L342-379)         → stale_diagnostics.py
├─ detect_silent_inactive_sessions (L380-454)   → stale_session_recovery.py
├─ force_reconnect_session (L455-555)           → stale_session_recovery.py
├─ delta_unsubscribe_dropped (L556-613)         → stale_session_recovery.py
├─ evaluate_universe_guard (L614-742)           → stale_universe_guard.py
├─ check_and_resubscribe_stale (L743-969)       → stale_watcher_core.py (사이클 66 시정 영속 22L)
└─ resubscribe_stale_priority (L970-1099)       → stale_watcher_core.py
```

### 2.3 상수 분포 (10 상수)

| 상수 | 현재 위치 | sub-module 이주 | 이유 |
|------|---------|---------------|------|
| MAX_STALE_RETRIES | stale_manager L33 | stale_diagnostics | prune_force_retry_history + check_and_resubscribe_stale 양쪽 사용 → diagnostics 단방향 import 영역 |
| STALE_FORCE_RETRY_AFTER_SECS | L36 | stale_diagnostics | 동일 |
| STALE_FORCE_RETRY_HOURLY_CAP | L37 | stale_diagnostics | 동일 |
| STALE_FRESHNESS_SECS | L47 | stale_diagnostics | F1 + watcher_core 공통 → diagnostics 가 단방향 import 영역 (사이클 61 D-1 답습) |
| UNIVERSE_LOW_VOLUME_THRESHOLD | L40 | stale_universe_guard | evaluate_universe_guard 전용 |
| SILENT_INACTIVE_FRESH_RATIO_THRESHOLD | L43 | stale_session_recovery | detect_silent_inactive_sessions 전용 |
| SILENT_INACTIVE_MIN_SUBSCRIBED | L51 | stale_session_recovery | 동일 |
| SILENT_INACTIVE_PERSIST_SECS | L52 | stale_session_recovery | 동일 |
| SILENT_INACTIVE_RECOVERY_CAP_PER_HOUR | L53 | stale_session_recovery | 동일 |
| SILENT_INACTIVE_RECOVERY_WINDOW_SECS | L54 | stale_session_recovery | 동일 |

---

## 3. import 의존성 그래프 — 옵션 A/B/C

### 3.1 옵션 A — `stale_watcher_core` 단방향 의존 (권고)

```
                    ┌───────────────────────┐
scheduler.py  ──→  │ stale_manager.py      │ (facade, ~30L)
(11 wrapper)       │ - 4 sub-module re-export│
                    │ - 10 상수 re-export    │
                    └─────────┬─────────────┘
                              │
              ┌───────────────┼────────────────┐
              ↓               ↓                ↓
   stale_diagnostics    stale_session_      stale_universe
   (read-only)          recovery            _guard
              ↑               ↑                ↑
              └───────────────┴────────────────┘
                              │
                    ┌─────────┴──────────────┐
                    │ stale_watcher_core.py  │ (HIGH hot path)
                    │ - check_and_resubscribe│
                    │ - resubscribe_priority │
                    └────────────────────────┘
```

**장점**: 순환 0 + watcher_core 가 진단/복구/가드 모두 호출 가능 + facade 보존으로 scheduler.py wrapper 0 변경
**단점**: facade re-export 16 항목 (11 함수 + 10 상수 - watcher_core 2 함수 = 19 항목, watcher_core 2 도 facade re-export 시 21)

### 3.2 옵션 B — 공통 헬퍼 (`stale_helpers.py`) 신설

```
   stale_helpers.py (sys.modules.get + logger binding 헬퍼 ~50L)
       ↑              ↑              ↑              ↑
       │              │              │              │
  diagnostics    recovery       universe_guard   watcher_core
```

**장점**: 사이클 61/63 `sys.modules.get("src.engine.scheduler")` 패턴 중복 제거 (4회 → 1 헬퍼)
**단점**: 추가 모듈 1개 (4 → 5) + 헬퍼 자체가 SoT 분산 위험

### 3.3 옵션 C — `stale_manager.py` facade 유지 + 4 sub-module 내부 분리

옵션 A 와 동등 — facade 패턴 = 옵션 A.

### 3.4 권고

**옵션 A 채택** (사이클 60/61/63 답습 + scheduler.py wrapper 0 변경 보장).
옵션 B (공통 헬퍼) 는 사이클 68+ 별도 카드로 분리 — 사이클 67 범위 외.

---

## 4. 위험 매트릭스

| 항목 | 위험 등급 | 영속 가드 영역 | 대응 |
|------|---------|--------------|------|
| **누적 회귀 가드 78 케이스 영향** | **HIGH** | 사이클 60 18 + 사이클 61 20 + 사이클 63 29 + 사이클 66 11 | patch 경로 15회 일관 갱신 + 회귀 78 전수 RE-RUN |
| **K stale watcher 본체 영역** | **HIGH** | 360 회/일 hot path (120s 주기) + KIS LMS chain 직접 영역 | watcher_core sub-module 회귀 가드 + 행위 비교 (사이클 63 답습) |
| **사이클 66 시정 영속 (resubscribe_stale_priority L1023-1057)** | **HIGH** | 사이클 29 005935 사고 패턴 영구 차단 의무 | watcher_core 내 영속 + AST 가드 priority 분리 *후* cap 영속 |
| **사이클 60 G-3 / 사이클 63 D-1 영구 가드 영속** | **HIGH** | `caplog logger="src.engine.scheduler"` + AST 정적 가드 | 4 sub-module 모두 동일 logger binding (사이클 63 답습) |
| **Q4=B 직접 호출 (사이클 63 영속)** | MEDIUM | `emit_stale_session_detail` 직접 호출 (1 hop 단축) | sub-module 간 import 명시화 — `from src.engine.stale_diagnostics import emit_stale_session_detail` (cross-module call) |
| **`sys.modules.get` 패턴 4회** | MEDIUM | 사이클 61/63 답습, freezegun patch 호환 | 4 sub-module 모두 동일 패턴 영속 (또는 옵션 B 헬퍼 분리) |
| **scheduler.py wrapper 시그너처 변경 0** | LOW | scheduler.py L2434~L2501 11개 wrapper | lazy import 경로만 변경 (`from src.engine import stale_manager` → `from src.engine.stale_diagnostics import X` 또는 facade 유지) |
| **import 순환 0** | LOW | watcher_core → diagnostics/recovery/universe_guard 단방향 | AST 정적 가드 (사이클 63 D-1 답습) |

---

## 5. 회귀 가드 청사진 (15~20 케이스)

### 5.1 의무 가드 카테고리

| # | 카테고리 | 가드 형태 | 사이클 출처 |
|---|---------|---------|-----------|
| G-1 | 4 sub-module import sanity | `from src.engine.stale_diagnostics import build_session_subscription_view, emit_stale_session_detail, refresh_stale_ccnl_cache, evict_expired_ccnl, prune_force_retry_history` 등 4 sub-module 전수 | 사이클 61 A2 import_sanity 답습 |
| G-2 | facade re-export 보존 | `from src.engine.stale_manager import *` 후 11 함수 + 10 상수 전수 존재 | 사이클 60/61/63 답습 |
| G-3 | scheduler.py wrapper 시그너처 0 변경 | AST 정적 가드: 11 wrapper signature hash 비교 (before/after) | 사이클 60 G-3 + 사이클 63 D-1 답습 |
| G-4 | scheduler.py 위임 lazy import 작동 | `from src.engine import stale_manager` 패턴 후 모든 함수 `getattr` 성공 | 사이클 60/61/63 답습 |
| G-5 | import 순환 0 (AST) | `stale_diagnostics` 가 `stale_session_recovery` / `stale_universe_guard` / `stale_watcher_core` import 0건 (AST grep) | 신규 (옵션 A 단방향) |
| G-6 | logger binding 영속 | `logging.getLogger("src.engine.scheduler")` 사용 — 4 sub-module 모두 (caplog 호환) | 사이클 60 I1 + 사이클 63 D-1 영구 |
| G-7 | `sys.modules.get("src.engine.scheduler")` 패턴 영속 | watcher_core 가 freezegun patch 호환 (사이클 63 답습) | 사이클 61 D-2 답습 |
| G-8 | 사이클 60 18 회귀 가드 RE-RUN PASS (patch 경로 갱신) | `patch("src.engine.stale_diagnostics.X")` 갱신 후 18/18 PASS | 사이클 60 hotfix 패턴 (사이클 61/63 답습) |
| G-9 | 사이클 61 20 회귀 가드 RE-RUN PASS (patch 경로 갱신) | `patch("src.engine.stale_session_recovery.X")` + `patch("src.engine.stale_universe_guard.X")` 갱신 후 20/20 PASS | 사이클 60 hotfix 패턴 답습 |
| G-10 | 사이클 63 29 회귀 가드 RE-RUN PASS (patch 경로 갱신) | `patch("src.engine.stale_watcher_core.X")` 갱신 후 29/29 PASS | 사이클 60 hotfix 패턴 답습 |
| G-11 | 사이클 66 11 회귀 가드 RE-RUN PASS | resubscribe_stale_priority L1023~1057 영속 + AST 가드 priority 분리 *후* cap 영속 | 사이클 66 영속 의무 |
| G-12 | 4 sub-module 라인 cap | stale_diagnostics ≤ 400 / stale_session_recovery ≤ 320 / stale_universe_guard ≤ 200 / stale_watcher_core ≤ 380 | 신규 (모듈 비대화 차단) |
| G-13 | Q4=B 직접 호출 영속 | `check_and_resubscribe_stale` 본체 마지막에 `emit_stale_session_detail(scheduler, ...)` 직접 호출 (1 hop 단축) AST 검증 | 사이클 63 Q4=B 영속 |
| G-14 | 상수 SoT 분산 차단 | 10 상수 각각 정의는 정확히 1 sub-module 만 (`grep MAX_STALE_RETRIES = ` count == 1) | 신규 (SoT 분산 차단) |
| G-15 | scheduler.py L92 re-export 호환 | `from src.engine.stale_manager import (5 상수)` 영속 (사이클 60 답습) | 사이클 60 A1 영속 |

### 5.2 카테고리 분리 측정 + flakiness 3 회

사이클 60 hotfix 패턴 답습 의무:
- pytest 카테고리 분리 측정 (`pytest --collect-only -q` 4 sub-module 별 회귀 가드 분포)
- flakiness 3 회 (동일 회귀 가드 3 회 RE-RUN 후 모두 PASS — order independence)

---

## 6. 사이클 60~66 답습 매트릭스

| 항목 | 사이클 60 A1 | 사이클 61 A2 | 사이클 63 A3 | 사이클 66 시정 | **사이클 67 분해 답습 의무** |
|------|------------|------------|------------|------------|------------------------|
| 위임 wrapper (2~3 줄 lazy import) | ✅ | ✅ | ✅ | (수정 없음) | ✅ scheduler.py 11 wrapper 시그너처 변경 0 |
| `sys.modules.get("src.engine.scheduler")` | (도입) | ✅ (4회) | ✅ (4회) | ✅ | sub-module 간에도 동일 패턴 (혹은 옵션 B) |
| logger 명시 binding (`logging.getLogger("src.engine.scheduler")`) | I1 영구 | ✅ | ✅ | ✅ | 4 sub-module 모두 동일 영속 |
| AST 정적 가드 | G-3 (폐기 메서드 0) | D-1 (의존성 역전) | G-3 (Q4=B) | AST (priority 분리 *후* cap) | sub-module import 순환 0 + Q4=B 영속 |
| 카테고리 분리 측정 + flakiness 3 회 | hotfix 도입 | ✅ | ✅ | ✅ | 의무 |
| domain-expert 자문 옵션 A 전부 | ✅ | ✅ | ✅ | ✅ | 7 사이클 연속 + 사이클 67 = **8 사이클 연속** |
| facade re-export 호환 | (단일 모듈) | (단일 모듈) | (단일 모듈) | (단일 모듈) | **신규**: `stale_manager.py` facade 30L (re-export only) |

---

## 7. 산출 경로

| 파일 | 역할 |
|------|------|
| `src/engine/stale_diagnostics.py` (신규 ~350L) | 진단 read-only 5 함수 + 4 상수 |
| `src/engine/stale_session_recovery.py` (신규 ~280L) | silent inactive + reconnect 3 함수 + 5 상수 |
| `src/engine/stale_universe_guard.py` (신규 ~150L) | universe 가드 1 함수 + 1 상수 |
| `src/engine/stale_watcher_core.py` (신규 ~320L) | K stale watcher 본체 2 함수 |
| `src/engine/stale_manager.py` (재작성 ~30L) | facade — 4 sub-module + 10 상수 re-export |
| `src/engine/scheduler.py` (변경 0) | 11 wrapper 시그너처 변경 0 의무 |
| `tests/unit/engine/stale_manager/test_cycle67_*.py` (신규 ~15 케이스) | G-1~G-15 회귀 가드 |
| `tests/unit/engine/test_cycle60_*.py` ~ `test_cycle66_*.py` (patch 경로 갱신) | 사이클 60 18 + 사이클 61 20 + 사이클 63 29 + 사이클 66 11 = 78 PASS |
| `docs/HARNESS_CHANGELOG.md` | 사이클 67 항목 추가 |
| `CLAUDE.md` | 디렉토리 역할 영역 4 sub-module 추가 |
| `src/engine/CLAUDE.md` | 모듈 맵 갱신 (stale_manager → 4 sub-module 분해) |

---

## 8. 발주 순서

1. **team-leader (현재)** — 설계 카드 + 자문 의뢰서 (본 문서)
2. **domain-expert 자문 발주** — `cycle67_stale_manager_decomposition_domain_consult.md` (Q1~Q5 + Q6+)
3. **사용자 결정** (옵션 A/B/C + Q4=B 영속 여부) — 옵션 A 전부 권장 (8 사이클 연속 답습)
4. **tdd-engineer Red** — 회귀 가드 ~15~20 케이스 (G-1~G-15) 실패 확인
5. **backend-dev Green** — `stale_manager.py` 1,099L → 4 sub-module + facade 30L
6. **tester Verify** — V1~V13 + V-Submodule (78 회귀 0 회귀) + V-AST (import 순환 0)
7. **sync-docs** — CLAUDE.md / HARNESS_CHANGELOG / src/engine/CLAUDE.md / refactor-review 카드 #14 완료
8. **사용자 명시 commit + push 지시 대기** — **일요일 (2026-06-07) 권장** (사이클 60 §Q5 답습)

---

## 9. push 시점 권고

| 옵션 | 시점 | 위험 |
|------|------|------|
| **권장** | **일요일 (2026-06-07)** | KRX/NXT 휴장 + production 변경 영역 0 의무 — 사이클 60 §Q5 답습 |
| 차선 | 월요일 (2026-06-08) 07:50 _boot 전 | KRX 메인 09:00 이전 + GH Actions deploy 1~5분 cushion |
| 비권장 | KRX 메인 (09:00~15:30) | `_scan_loop` 5분 race + K stale watcher 120s race + 사이클 29 005935 사고 영역 |

**채택**: 일요일 (2026-06-07).

---

## 10. 후속 카드 영속

- 사이클 68+ = 카드 #16 (MEDIUM) 사이클 65 후보 풀 폭축 2주 회고
- 사이클 68+ = 카드 #17 (LOW) 기타 INSERT 모듈 UTC → KST 일관성
- 사이클 69+ = 카드 #15 (LOW) Q7-2 액면분할 prdy_clpr invalidate
- 사이클 70+ = 카드 #11/#12 보드 mutex / 14 모듈 logger
- 사이클 71+ = 옵션 B 공통 헬퍼 (`stale_helpers.py`) 분리 — 사이클 67 보류 결정 시
