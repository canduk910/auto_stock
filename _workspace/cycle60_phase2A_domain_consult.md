# 사이클 60 Phase 2-A — domain-expert 자문 의뢰서

> **의뢰자**: team-leader (2026-06-04 15:55 KST)
> **대상**: domain-expert
> **사이클 카드**: `_workspace/cycle60_phase2A_design_card.md`
> **위험 등급**: HIGH (WebSocket 4 중 안전망 hot path + 모듈 간 경계)
> **자문 의무**: HIGH 카드는 행위 영향 평가 의무 (CLAUDE.md `domain-consult` 스킬)

---

## 배경

사이클 60 Phase 2-A 는 `src/engine/scheduler.py` (3,880L) 의 stale 영역 11 함수 + 5 상수를 신규 모듈 `src/engine/stale_manager.py` 로 추출하는 *행위 보존 리팩토링* 입니다.

**선례**: 사이클 51 `boot_manager.py` (305L) — `scheduler` 인자 + 2 줄 wrapper 위임 패턴 답습.

**분리 대상**:
- 11 함수 ~930L (scheduler.py 의 24%, 표 부록)
- 5 상수: `MAX_STALE_RETRIES` / `STALE_FORCE_RETRY_AFTER_SECS` / `STALE_FORCE_RETRY_HOURLY_CAP` / `UNIVERSE_LOW_VOLUME_THRESHOLD` / `SILENT_INACTIVE_FRESH_RATIO_THRESHOLD`

**CLAUDE.md 절대 규칙 보호 영역**:
- WebSocket 4 중 안전망 #3 (K stale watcher 120s) + #4 (resubscribe_stale_priority 5분 우선)
- 우선순위 분리 (사이클 29-R3): positions/_pending_next_day_clear HIGH+bypass=True / 그 외 LOW+bypass=False
- silent inactive 시간당 세션당 2회 cap (LMS/앱키 정지 차단)
- stale universe 가드 (사이클 32): stale>5 + today_volume<10_000 자동 unsubscribe + 보유/익일청산 절대 보호
- `_reset_daily_state` 동행 reset (`_stale_state.reset_daily()`)

---

## 자문 요청 (Q1~Q4)

### Q1 — WebSocket 4 중 안전망 호출 시점/순서 영향 평가

`check_and_resubscribe_stale` 함수가 scheduler.py 메서드에서 `stale_manager` 모듈 함수 (scheduler 인자) 로 위임 변경됩니다.

**구체 우려**:
- K stale watcher (120s 주기, `_stale_watcher_loop`) → `await stale_manager.check_and_resubscribe_stale(scheduler)` wrapper 1 줄 위임. 함수 호출 비용 영향?
- silent inactive `_force_reconnect_session` (시간당 세션당 2회 cap) 의 cap 카운터 (`_silent_inactive_recovery_count` dict) 가 `scheduler._stale_state` 에 잔류 — 모듈 분해 후에도 카운터 일관성 보장?
- `resubscribe_stale_priority` 의 5분 우선 재구독 timing (positions/_pending 우선) 영향 없음?

**자문 의뢰**: 행위 보존 보장 (RECOMMEND) / 추가 가드 필요 (CONSIDER) / 위임 자체 위험 (AVOID) 분류 + 근거.

### Q2 — `_reset_daily_state` 동행 stale_state.reset_daily 호출 순서 보장

scheduler.`_reset_daily_state` (L3788~3870) 는 25+ 필드를 일괄 reset 하며, 그 중 한 줄 (L3828) 이 `self._stale_state.reset_daily()` 입니다.

**구체 우려**:
- stale_manager 함수가 `_stale_state` 직접 위임만 하고, reset 호출 위치는 scheduler 잔류. 이 순서 보존 자체는 안전?
- 사이클 56-D 의 `risk_manager.reset_daily_state()` 위임 패턴 (이미 +1 필드 반영됨) 과 동등?
- 본 사이클에서 *추가 동행 필드* 필요 없음?

**자문 의뢰**: 순서 보존 안전 (RECOMMEND) / 단위 가드 1 케이스 추가 (CONSIDER) / 분해 자체 위험 (AVOID) 분류.

### Q3 — 5 상수 모듈 이동 시 import 경로 변경의 행위 영향

5 상수는 scheduler.py 모듈 상수 (L88~119) 에서 stale_manager.py 모듈 상수로 이전. scheduler.py 는 `from src.engine.stale_manager import MAX_STALE_RETRIES, ...` re-export.

**구체 우려**:
- 기존 외부 호출 `from src.engine.scheduler import MAX_STALE_RETRIES` 호환 유지 (re-export)?
- 회귀 가드 #2 (5 상수 동일성 5 케이스: 두 import 경로 모두 같은 값) 으로 충분?
- 추가 보강 필요 (예: 단위 상수 자체 값 변경 회귀 가드)?

**자문 의뢰**: re-export 충분 (RECOMMEND) / 단위 값 가드 추가 (CONSIDER) / 호환 layer 자체 위험 (AVOID) 분류.

### Q4 — 11 함수 *전체 묶음 이동* vs *2 단계 분할*

**옵션 A (전체 일괄)**: 사이클 60 Phase 2-A 1 사이클로 11 함수 일괄 이동 (~930L).
- 효율: 분해 1회 + 회귀 가드 32 케이스 + 통합 시나리오 1회
- 위험: 분해 중 1 함수 결함 발생 시 11 함수 영향
- 사이클 51 boot_manager (305L, 1 사이클) 답습 — 라인 수 3배지만 동일 위험 등급

**옵션 B (2 단계 분할)**:
- Phase 2-A1 (read-only 4 함수: `_build_session_subscription_view` / `_emit_stale_session_detail` / `_evict_expired_ccnl` / `_prune_force_retry_history` — ~203L)
- Phase 2-A2 (hot path 7 함수: 나머지 — ~727L)
- 위험 분산: read-only 영역 격리 후 hot path 분해
- 비용: 2 사이클 + 회귀 가드 2회 + 통합 시나리오 2회 + 차이 통합 비용

**자문 의뢰**: A 권고 (RECOMMEND) / B 권고 (CONSIDER) / 다른 분할 권고 (예: hot path 만 먼저, 또는 universe 가드 별도)?

---

## Q5 — push 시점 권고 (운영 안전)

본 사이클 분해 + push 의 운영 시간 권고:

- **NXT 애프터 (15:30~20:00)**: 메인 시간 외, NXT 시세 영향 가능성 — but stale 영역 분해는 NXT 정합성 보존 (사이클 32/29-R3 보호)
- **익일 07:50 _boot 전 (영업일 새벽)**: 가장 안전, _scan_loop 5분 race 없음
- **주말/공휴일**: 가장 안전, 매매 영향 0

자문 의뢰: NXT 애프터 (현실적 — 사용자 작업 시간대) vs 익일 새벽 (안전 우선) 권장 시점.

---

## 회신 형식 요청

domain-expert 의 회신은 다음 형식 권장 (사이클 55 R-1 답습):

```
Q1: [RECOMMEND/CONSIDER/AVOID] — 근거 (3~5 문장)
Q2: [RECOMMEND/CONSIDER/AVOID] — 근거
Q3: [RECOMMEND/CONSIDER/AVOID] — 근거
Q4: [A/B/기타] — 근거
Q5: [NXT 애프터 / 익일 새벽 / 주말] — 근거

추가 권고 (선택): scheduler 분해 후속 카드 (#3 settlement_manager) 의존성 관점에서 본 카드 영향
```

---

## 부록 — 분리 대상 11 함수 위치

| 함수 | 현 위치 | 라인 | 분류 |
|---|---|---|---|
| `_detect_silent_inactive_sessions` | L2434 | ~62 | silent inactive (사이클 29-R2) |
| `_force_reconnect_session` | L2496 | ~83 | silent inactive 강제 reconnect |
| `_check_and_resubscribe_stale` | L2579 | ~221 | **K stale watcher 핵심** (4 중 안전망 #3) |
| `_build_session_subscription_view` | L2810 | ~98 | stale 진단 read-only |
| `_emit_stale_session_detail` | L2909 | ~43 | stale 세부 로그 emit |
| `_delta_unsubscribe_dropped` | L2952 | ~52 | stale 후보 drop 시 unsubscribe |
| `_resubscribe_stale_priority` | L3004 | ~100 | **5분 우선 재구독** (4 중 안전망 #4) |
| `_evaluate_universe_guard` | L3105 | ~116 | **stale universe 가드** (사이클 32) |
| `_refresh_stale_ccnl_cache` | L3222 | ~93 | inquire_ccnl 캐시 |
| `_evict_expired_ccnl` | L3316 | ~29 | ccnl TTL evict |
| `_prune_force_retry_history` | L3345 | ~33 | force_retry 시간당 cap 정리 |

**합계**: ~930L (scheduler.py 의 24%)
