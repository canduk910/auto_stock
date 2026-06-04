# Red 명세 — 사이클 60 Phase 2-A stale_manager 추출

> **작성**: team-leader (2026-06-04, 골격) → tdd-engineer (사용자 채택 후 32 케이스 본체)
> **선행 카드**: `_workspace/cycle60_phase2A_design_card.md`
> **자문 의뢰**: `_workspace/cycle60_phase2A_domain_consult.md`
> **위험 등급**: HIGH (WebSocket 4 중 안전망 hot path)
> **TDD 사이클**: Red (회귀 가드 사전 작성) → Green (stale_manager.py 신규 + wrapper) → Refactor

---

## 회귀 가드 32 케이스 골격

### 카테고리 A — 위임 1회 검증 (11 케이스)

각 wrapper 가 `stale_manager` 단일 함수만 호출하는지 검증.

| # | 테스트 | 파일 |
|---|---|---|
| A-1 | `_check_and_resubscribe_stale` → `stale_manager.check_and_resubscribe_stale(self)` 1 회 호출 | `tests/unit/engine/test_cycle60_stale_manager_delegation.py` |
| A-2 | `_detect_silent_inactive_sessions` → `stale_manager.detect_silent_inactive_sessions(self)` 1 회 | ↑ |
| A-3 | `_force_reconnect_session(label)` → `stale_manager.force_reconnect_session(self, label)` 1 회 | ↑ |
| A-4 | `_build_session_subscription_view` → `stale_manager.build_session_subscription_view(self)` 1 회 | ↑ |
| A-5 | `_emit_stale_session_detail(...)` → `stale_manager.emit_stale_session_detail(self, ...)` 1 회 | ↑ |
| A-6 | `_delta_unsubscribe_dropped(new_set)` → `stale_manager.delta_unsubscribe_dropped(self, new_set)` 1 회 | ↑ |
| A-7 | `_resubscribe_stale_priority(cap)` → `stale_manager.resubscribe_stale_priority(self, cap)` 1 회 | ↑ |
| A-8 | `_evaluate_universe_guard(candidates)` → `stale_manager.evaluate_universe_guard(self, candidates)` 1 회 | ↑ |
| A-9 | `_refresh_stale_ccnl_cache(...)` → `stale_manager.refresh_stale_ccnl_cache(self, ...)` 1 회 | ↑ |
| A-10 | `_evict_expired_ccnl(now)` → `stale_manager.evict_expired_ccnl(self, now)` 1 회 | ↑ |
| A-11 | `_prune_force_retry_history(...)` → `stale_manager.prune_force_retry_history(self, ...)` 1 회 | ↑ |

**패턴**: `unittest.mock.patch.object(stale_manager, "...")` + assert call_count==1 + assert call_args.

### 카테고리 B — 5 상수 동일성 (5 케이스)

| # | 테스트 | 검증 |
|---|---|---|
| B-1 | `MAX_STALE_RETRIES` | `scheduler.MAX_STALE_RETRIES is stale_manager.MAX_STALE_RETRIES` + `== 5` |
| B-2 | `STALE_FORCE_RETRY_AFTER_SECS` | 동일 + `== 300` |
| B-3 | `STALE_FORCE_RETRY_HOURLY_CAP` | 동일 + `== 12` |
| B-4 | `UNIVERSE_LOW_VOLUME_THRESHOLD` | 동일 + `== 10_000` |
| B-5 | `SILENT_INACTIVE_FRESH_RATIO_THRESHOLD` | 동일 + `== 0.2` |

**패턴**: 단일 파일 `tests/unit/engine/test_cycle60_stale_manager_constants.py` 5 케이스 묶음.

### 카테고리 C — 호출 순서 보존 (4 케이스)

| # | 테스트 | 검증 |
|---|---|---|
| C-1 | `_stale_watcher_loop` 1 cycle → `check_and_resubscribe_stale` 정확히 1회 호출 | mock spy + 120s 시간 freeze |
| C-2 | `_scan_loop` 1 cycle → `evaluate_universe_guard(candidates)` 호출 순서 (다른 step 이후) | mock spy |
| C-3 | `_board_transition_loop` 1 cycle → `delta_unsubscribe_dropped(new_set)` 호출 | mock spy |
| C-4 | `_session_health_loop` 1 cycle → `detect_silent_inactive_sessions` 호출 → 결과에 따라 `force_reconnect_session` 분기 | mock spy + 시간 freeze |

**파일**: `tests/unit/engine/test_cycle60_stale_manager_call_order.py`

### 카테고리 D — WebSocket 4 중 안전망 행위 가드 (4 케이스)

| # | 테스트 | 검증 |
|---|---|---|
| D-1 | F1 (재연결 1회) — 분해 후에도 `websocket.reconnect()` 호출 작동 | mock 통합 |
| D-2 | `_scan_loop` (5분) — stale 평가 시점 5분 주기 보존 | freezegun 5분 |
| D-3 | K stale watcher (120s) — `check_and_resubscribe_stale` 주기 보존 | freezegun 120s |
| D-4 | `resubscribe_stale_priority` (5분 우선) — positions/_pending 우선순위 보존 | mock subscribe + 우선순위 verify |

**파일**: `tests/integration/test_cycle60_websocket_quad_safety_net.py`

### 카테고리 E — 우선순위 분리 (사이클 29-R3) (2 케이스)

| # | 테스트 | 검증 |
|---|---|---|
| E-1 | positions 종목 → HIGH 우선순위 + `bypass_limit=True` | `_resubscribe_stale_priority` 호출 시 verify |
| E-2 | 일반 후보 종목 → LOW 우선순위 + `bypass_limit=False` | ↑ |

**파일**: `tests/unit/engine/test_cycle60_priority_separation.py`

### 카테고리 F — silent inactive 시간당 2회 cap (1 케이스)

| # | 테스트 | 검증 |
|---|---|---|
| F-1 | 동일 세션 `force_reconnect_session` 3 회 호출 → 3번째 skip (cap = 2) | freezegun 1시간 |

**파일**: `tests/unit/engine/test_cycle60_silent_inactive_cap.py`

### 카테고리 G — universe 가드 보호 (사이클 32) (2 케이스)

| # | 테스트 | 검증 |
|---|---|---|
| G-1 | positions 종목 stale>5 + today_volume<10_000 → unsubscribe **안 됨** (절대 보호) | positions 종목 verify |
| G-2 | `_pending_next_day_clear` 종목 동일 조건 → unsubscribe **안 됨** | pending verify |

**파일**: `tests/unit/engine/test_cycle60_universe_guard_protection.py`

### 카테고리 H — `_reset_daily_state` 동행 reset (1 케이스)

| # | 테스트 | 검증 |
|---|---|---|
| H-1 | scheduler.`_reset_daily_state()` 호출 → `_stale_state.reset_daily()` 작동 (universe_excluded_today / silent_inactive_first_seen / force_retry_history 등 clear) | mock + verify |

**파일**: `tests/unit/engine/test_cycle60_reset_daily_state_integration.py`

### 카테고리 I — ccnl 캐시 TTL evict (1 케이스)

| # | 테스트 | 검증 |
|---|---|---|
| I-1 | TTL 만료 항목 evict + 미만료 항목 보존 | freezegun + dict verify |

**파일**: `tests/unit/engine/test_cycle60_ccnl_cache_evict.py`

### 카테고리 J — force_retry 시간당 cap (1 케이스)

| # | 테스트 | 검증 |
|---|---|---|
| J-1 | 동일 종목 13번째 force_retry 시 skip (cap = 12) | freezegun 1시간 |

**파일**: `tests/unit/engine/test_cycle60_force_retry_hourly_cap.py`

### 카테고리 K — 추가 회귀 가드 (1 케이스, 신규 import 호환)

| # | 테스트 | 검증 |
|---|---|---|
| K-1 | `from src.engine import stale_manager` import 성공 + 11 함수 + 5 상수 모두 노출 | import sanity |

**파일**: `tests/unit/engine/test_cycle60_stale_manager_imports.py`

---

## 총 32 케이스

| 카테고리 | 케이스 | 위험 등급 |
|---|---|---|
| A 위임 1회 | 11 | LOW (mock 위주) |
| B 5 상수 | 5 | LOW |
| C 호출 순서 | 4 | MEDIUM |
| D WebSocket 4중 | 4 | HIGH |
| E 우선순위 분리 | 2 | HIGH |
| F silent inactive cap | 1 | MEDIUM |
| G universe 가드 보호 | 2 | HIGH |
| H reset 동행 | 1 | HIGH |
| I ccnl TTL evict | 1 | LOW |
| J force_retry cap | 1 | MEDIUM |
| K import sanity | 1 | LOW |
| **총** | **32** | HIGH 4 / MEDIUM 3 / LOW 4 |

---

## 통과 기준

- 백엔드 1844 PASS (사이클 58 V-2 기준) → 1844 + 32 = **1876 PASS** 유지
- WebSocket 통합 시나리오 회귀 0건
- `_scan_loop` E2E 회귀 0건
- 영향 인덱스 갱신 (`test-impact-index` 스킬) — stale_manager 가 모든 11 함수 영향 인덱스에 등록

---

## 사전 조건 (Red 작성 *전*)

1. domain-expert 자문 Q1~Q4 회신 (`_workspace/cycle60_phase2A_domain_consult.md`)
2. 사용자 채택 결정 (Q1~Q5 분류 RECOMMEND/CONSIDER/AVOID)
3. team-leader 가 사용자 결정 반영 후 tdd-engineer 에게 본 명세 발주

---

## 후속 단계 (Green 발주)

본 32 케이스 Red 통과 후:
- backend-dev 가 `src/engine/stale_manager.py` 신규 작성 (사이클 51 boot_manager 패턴)
- scheduler.py 의 11 함수 → wrapper 2 줄 위임
- 5 상수 stale_manager 로 이동 + scheduler 가 re-import (호환 보장)
- 32 케이스 + 기존 1844 PASS = 1876 PASS 통과 검증
