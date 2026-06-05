# 사이클 61 = Phase 2-A2 설계 카드 (MEDIUM)

> **작성**: team-leader (2026-06-05 09:35 KST)
> **승인 상태**: 사용자 명시 발주 — 사이클 60 종결 후 A2 인계
> **선행 사이클**: 사이클 60 = Phase 2-A1 (LOW, 5 함수 + 5 상수, push 완료 + CI ✅ `436aa3c`)
> **선행 자문**: `_workspace/cycle60_phase2A_domain_response.md` (§Q4 권고 = 3 단계 분할)
> **위험 등급**: **MEDIUM** (silent inactive cap + universe guard — KIS LMS/앱키 정지 위험 영역)
> **CLAUDE.md 절대 규칙 충돌**: 없음 (행위 보존, hot path 함수 이주만)
> **push 시점**: **익일 새벽** (Q5 자문 권고) 또는 **NXT 애프터 18:00 이후** (현재 09:35 KST = KRX 메인 진입 직후, push 금지 시간대)

---

## 1. 범위 — Phase 2-A2 단독 (4 함수 314L)

### 1.1 자문 권고 인용 (§Q4)

> "Phase 2-A2 (MEDIUM 위험, ~365L): silent inactive + universe guard
> `_detect_silent_inactive_sessions` / `_force_reconnect_session` / `_evaluate_universe_guard` / `_delta_unsubscribe_dropped`
> 회귀 가드 ~12 케이스 (cap 검증 + 보유/익일청산 보호 + 5분 지속 검증)
> 위험: 세션 reconnect cap 위반 시 KIS 앱키 정지 위험 (cap 가드 회귀 절대 0건 보장 필요)"

### 1.2 A2 4 함수 (코드 정독 후 라인 실측)

| 함수 | 현 위치 | 라인 (실측) | 분류 | 위험 |
|---|---|---|---|---|
| `_detect_silent_inactive_sessions` | L2423~2484 | **62L** | 세션 단위 silent inactive 판정 (3중 가드: fresh_ratio + min_sub + 5분 지속) | MEDIUM |
| `_force_reconnect_session` | L2485~2567 | **83L** | 세션 강제 reconnect (시간당 cap 2회 + `_ws.close()` 발화) | **MEDIUM-HIGH** (KIS LMS 직접 영향) |
| `_delta_unsubscribe_dropped` | L2811~2862 | **52L** | `_scan_loop` delta unsubscribe (KIS "비정상 케이스 2" 차단) | LOW-MEDIUM |
| `_evaluate_universe_guard` | L2964~3080 | **117L** | universe stale 가드 (stale>5 + low_volume) | MEDIUM |

**합계**: **314L** (Q4 견적 365L 보다 51L 적음 — domain-expert 견적 차이, 실제는 정확 측정값 사용)

**잔류 (Phase 2-A3 사이클 62)**:
- `_check_and_resubscribe_stale` (L2568~2798, ~231L)
- `_resubscribe_stale_priority` (L2863~2962, ~100L)

---

## 2. 적용 자문 권고 (Q1~Q7 A2 영역 한정)

### Q1 CONSIDER — 회귀 가드 +4 케이스 (A2 범위)

A2 적용:
- **Q1-G1**: `_stale_watcher_loop` 호출 주기 120s 보존 가드 — A2 범위 *밖* (호출자 `_check_and_resubscribe_stale` 가 A3 이주) → **A3 사이클 62로 이연**
- **Q1-G2**: **`_force_reconnect_session` cap dict 동일성 가드 — 본 사이클 적용 의무 (1 케이스)**
  - `scheduler._silent_inactive_recovery_count is stale_manager._get_state(scheduler).silent_inactive_recovery_count` (`is` 동일성)
  - 이주 후에도 *동일 dict 참조* 보장 → KIS LMS/앱키 정지 위험 영구 차단
  - **사이클 60 A1 `_last_ccnl_cache` 동일성 가드 답습** (사이클 60 hotfix I1 영구 가드 일관성)
- **Q1-G3**: K stale watcher → `_emit_stale_session_detail` 호출 순서 가드 — 사이클 60 A1 에서 적용 완료
- **Q1-G4**: `_resubscribe_stale_priority(cap=10)` cap 인자 전달 가드 — A3 사이클 62 이연

### Q2 RECOMMEND — `_reset_daily_state` 동행 reset (A2 영역 검증)

**중요 발견 (코드 정독 후)**: A2 4 함수가 사용하는 상태 3종 (`_silent_inactive_first_seen` / `_silent_inactive_recovery_count` / `_universe_excluded_today`) **모두 `StaleTrackerState` 데이터클래스에 이미 통합 (사이클 48)**. `_reset_daily_state` L3553 `self._stale_state.reset_daily()` 단일 호출이 7 필드 일괄 clear.

→ **A2 이주 시 reset 동행 자동 보존**, 신규 reset 추가 0건. 단, **회귀 가드는 의무**:
- **Q2-G1 (사이클 60 G-1 패턴 답습)**: `_reset_daily_state()` 호출 후 A2 영향 3 필드 검증
  ```python
  scheduler._reset_daily_state()
  assert scheduler._silent_inactive_first_seen == {}
  assert scheduler._silent_inactive_recovery_count == {}
  assert scheduler._universe_excluded_today == set()
  ```
- **Q2-G2 dataclass 필드 누락 가드**: `dataclasses.fields(StaleTrackerState)` 와 reset 후 비교 — 사이클 60 G-1 명세 "6 필드" → 실측 7 필드 정정 사례 영구 가드

### Q3 RECOMMEND — 5 상수 추가 이전 (A2 시점)

**사이클 60 A1 이전 완료**: `MAX_STALE_RETRIES` / `STALE_FORCE_RETRY_AFTER_SECS` / `STALE_FORCE_RETRY_HOURLY_CAP` / `UNIVERSE_LOW_VOLUME_THRESHOLD` / `SILENT_INACTIVE_FRESH_RATIO_THRESHOLD` (5종)

**A2 추가 이전 (5종 → 10종)**: 응답서 §Q3 권고 "관련 상수 그룹화"
- `SILENT_INACTIVE_MIN_SUBSCRIBED` (=5) — `_detect_silent_inactive_sessions` L2468 사용
- `SILENT_INACTIVE_PERSIST_SECS` (=300.0) — `_detect_silent_inactive_sessions` L2477 + `_force_reconnect_session` L2544 사용
- `SILENT_INACTIVE_RECOVERY_CAP_PER_HOUR` (=2) — `_force_reconnect_session` L2507 사용
- `SILENT_INACTIVE_RECOVERY_WINDOW_SECS` (=3600.0) — `_force_reconnect_session` L2502 사용
- `STALE_FRESHNESS_SECS` (=60) — A2 3 함수 사용 (`_detect_silent_inactive_sessions` L2443, scheduler 잔류 함수도 사용)

**STALE_FRESHNESS_SECS 처리 특이점**: scheduler.py 의 다른 함수 (`_check_and_resubscribe_stale` L2615 + `_resubscribe_stale_priority` L2899 = A3 잔류) 도 사용 → **A2 시점에 stale_manager 로 이전 + scheduler.py re-export** (사이클 60 A1 패턴 답습). A3 사이클 62 시점에 호출자도 이주하면 자연 일관.

**Q3-G1~G5 (A2 추가 5 상수 동일성 가드)**: 5 케이스
```python
from src.engine.scheduler import SILENT_INACTIVE_MIN_SUBSCRIBED as A
from src.engine.stale_manager import SILENT_INACTIVE_MIN_SUBSCRIBED as B
assert A is B  # `is` 동일성 (re-export)
```
- 동일 패턴 4 상수 + `STALE_FRESHNESS_SECS` = 5 케이스

**Q3-G6 의존성 역전 정적 검증** (사이클 60 A1 적용 완료 가드 보존): stale_manager.py 가 scheduler.py 역참조 안 함 — 단, *예외*: `_build_session_subscription_view` 가 `STALE_FRESHNESS_SECS` lazy import 함 (`from src.engine import scheduler as _sched_mod; _sched_mod.STALE_FRESHNESS_SECS`). **A2 시점에 `STALE_FRESHNESS_SECS` 가 stale_manager 로 이전되면 본 lazy import 제거** (의존성 역전 자연 해소).

### Q4 — A2 단독 진행 (사이클 61)

사이클 61 = Phase 2-A2 = 4 함수 314L. A3 는 별도 사이클 62.

### Q5 push 시점 — **익일 새벽 또는 NXT 애프터 18:00 이후 (오늘 금요일이므로 주말 허용)**

- 현재: 2026-06-05 (금) 09:35 KST = **KRX 메인 진입 직후** → push 절대 금지 시간대
- 권고 옵션:
  - **옵션 A (NXT 애프터)**: 오늘 15:30 이후 18:00 사이 NXT 거래량 적은 시각 → push → 18:00 이후 1~2h tester verify
  - **옵션 B (주말)**: 토/일 push → 월요일 _boot 첫 검증. 가장 안전, 매매 영향 0
  - **옵션 C (익일 새벽 — 월요일 06:00~07:50)**: _boot 전 push → 07:50 _boot 첫 검증
- **team-leader 권고**: **옵션 B (주말 푸시)** — A2 MEDIUM 등급이고 cap 위반 시 KIS 앱키 정지 위험 → 가장 안전한 옵션 채택 권고. 사용자 최종 결정.

### Q6 별개 카드 (보드 전환 mutex)

- A2 의 `_delta_unsubscribe_dropped` 가 `_scan_loop` + `_board_transition_loop` 양쪽에서 호출됨 → 사이클 26 race 가능성 잔존
- **본 사이클 범위 *밖*** (응답서 §Q6 권고 답습) — 별개 카드 #11 발의 (A3 사이클 62 시점 또는 별도 사이클)
- A2 회귀 가드에는 race 시뮬레이션 1 케이스 추가 (Q6-G1 — `asyncio.gather` + 동일 종목)

### Q7 본질 차이 3 가지 인지 — A2 단계 적용

- A2 의 `_force_reconnect_session` = **영구 hot path + KIS LMS 직접 영향** (boot 와 본질 차이 가장 큰 함수)
- 시간당 세션당 2회 cap = KIS 앱키 정지 위험 차단 *마지막 cap* → 회귀 가드 1 케이스 (Q1-G2 cap dict 동일성) **절대 0건 보장**
- A2 완료 후 1 영업일 NXT 애프터 + KRX 메인 1 사이클 운영 → silent inactive 카운터 정상 누적 확인 → A3 발주 (응답서 §Q4-G2)

---

## 3. stale_manager.py 인터페이스 명세 (A2 추가)

### 3.1 모듈 확장 — 기존 모듈에 4 함수 + 5 상수 추가

- **경로**: `src/engine/stale_manager.py` (사이클 60 A1 신규 모듈 — 모듈 분리 X)
- **A1 라인**: 358L (5 함수 + 5 상수 + docstring + imports)
- **A2 예상 추가 라인**: ~360~400L (4 함수 314L + 5 상수 + docstring 보강)
- **A2 후 예상**: ~720~760L

### 3.2 함수 시그니처 (사이클 51/60 패턴 답습 — scheduler 인자 첫번째)

```python
# A2 추가 — silent inactive + universe guard + delta unsubscribe

def detect_silent_inactive_sessions(scheduler: Any) -> list[str]:
    """세션 단위 silent inactive 감지 (사이클 24 / 29-R2). L2423 본체 그대로 이주."""
    ...

async def force_reconnect_session(scheduler: Any, label: str) -> bool:
    """세션 단위 silent inactive 강제 reconnect (사이클 24). L2485 본체 그대로 이주.

    절대 깨지 말 것:
    - 시간당 세션당 2회 cap (KIS LMS/앱키 정지 위험) — `_silent_inactive_recovery_count` dict 동일성 보장
    - cap 윈도우 in-place evict (`history[:] = ...`) 정합성 보존
    - `_ws.close()` 발화 순서 보존
    """
    ...

async def delta_unsubscribe_dropped(scheduler: Any, new_set: set[str]) -> list[str]:
    """`_scan_loop` delta unsubscribe (사이클 15-A). L2811 본체 그대로 이주.

    절대 깨지 말 것:
    - KIS 공지 "비정상 케이스 2" (무한 등록/해제 반복) 차단
    - 50ms sleep + 종목별 예외 격리
    """
    ...

async def evaluate_universe_guard(
    scheduler: Any, candidate_tickers: list[str]
) -> None:
    """universe stale 가드 평가 + KIS 최근체결시각 기록 (사이클 32 R4). L2964 본체 그대로 이주.

    절대 깨지 말 것:
    - 보유 종목 / 익일청산 종목 절대 제외 금지 (사전 가드 순서 보존)
    - `_universe_excluded_today.add()` + `kis_ws_pool.unsubscribe()` 순서 보존
    - 50ms sleep Rate Limit 보호
    - `_reset_daily_state` 동행 clear (`_stale_state.reset_daily()` 통합 — A2 추가 없음)
    """
    ...
```

### 3.3 scheduler.py wrapper 패턴 (4 wrapper, 사이클 51/60 동일)

```python
def _detect_silent_inactive_sessions(self) -> list[str]:
    from src.engine import stale_manager
    return stale_manager.detect_silent_inactive_sessions(self)

async def _force_reconnect_session(self, label: str) -> bool:
    from src.engine import stale_manager
    return await stale_manager.force_reconnect_session(self, label)

async def _delta_unsubscribe_dropped(self, new_set: set[str]) -> list[str]:
    from src.engine import stale_manager
    return await stale_manager.delta_unsubscribe_dropped(self, new_set)

async def _evaluate_universe_guard(self, candidate_tickers: list[str]) -> None:
    from src.engine import stale_manager
    await stale_manager.evaluate_universe_guard(self, candidate_tickers)
```

**호환 layer**: 4 wrapper 모두 *2 줄 위임* (async 함수는 await 1 줄 추가 = 실질 3 줄). scheduler.py 외부 호출 경로 보존.

### 3.4 logger 명시 binding (사이클 60 I1 영구 가드 답습)

A2 신규 이주 함수에서 사용하는 logger 도 `logging.getLogger("src.engine.scheduler")` 명시 binding — `__name__` 사용 시 `[silent_inactive_recovery_cap]` / `[universe_excluded]` 운영 로그 누락 위험.

stale_manager.py 모듈 상단 `logger = logging.getLogger("src.engine.scheduler")` (사이클 60 A1 에서 이미 binding 완료) **재사용** — A2 추가 함수 모두 동일 logger.

---

## 4. 회귀 가드 — A2 한정 (총 15~18 케이스)

### 4.1 카테고리별 가드 수

| 카테고리 | 케이스 | 영역 |
|---|---|---|
| **A 위임 1회 검증** (A2 4 함수) | 4 | wrapper 가 stale_manager 단일 호출 — `unittest.mock.patch` |
| **B 5 상수 동일성** (A2 추가 5 상수) | 5 | `scheduler.X is stale_manager.X` + 값 검증 |
| **C cap dict 동일성** (Q1-G2) | 1 | `scheduler._silent_inactive_recovery_count is _stale_state.silent_inactive_recovery_count` |
| **D 의존성 역전 정적 검증** (Q3-G6 갱신) | 1 | `ast` 모듈로 stale_manager.py 의 scheduler.py 역참조 검증 — **단, A2 시점 STALE_FRESHNESS_SECS lazy import 제거 의무 확인** |
| **E `_reset_daily_state` 동행 reset** (Q2-G1) | 1 | A2 영향 3 필드 동시 검증 (`_silent_inactive_first_seen` + `_silent_inactive_recovery_count` + `_universe_excluded_today`) |
| **F dataclass 필드 누락 가드** (Q2-G2) | 1 | `dataclasses.fields(StaleTrackerState)` vs reset 후 비교 (사이클 60 G-1 명세 정정 사례 영구 가드) |
| **G silent inactive 시간당 cap** | 1 | `_force_reconnect_session` 3번째 호출 시 cap=2 도달 → False 반환 + WARNING (freezegun) |
| **H silent inactive 5분 지속 판정** | 1 | `_detect_silent_inactive_sessions` 4분 30s = 미감지 / 5분 = 감지 (freezegun) |
| **I universe guard 보유 보호** | 1 | `_evaluate_universe_guard` — 보유 종목은 stale>5 + low_volume 이어도 제외 안 함 |
| **J universe guard 익일청산 보호** | 1 | `_pending_next_day_clear` 종목 절대 제외 금지 |
| **K delta unsubscribe race 시뮬레이션** (Q6-G1) | 1 | `asyncio.gather(_scan_loop_call, _board_transition_call)` 동일 종목 unsubscribe 충돌 검증 (best-effort, race 발견 시 별개 카드 #11 발의 근거) |
| **L import sanity** | 1 | `from src.engine import stale_manager` 후 A2 4 함수 + A2 5 상수 노출 검증 |
| **합계** | **18** | LOW 7 / MEDIUM 8 / HIGH 3 (C cap dict + G cap + I 보유 보호) |

### 4.2 통과 기준

- 백엔드 사이클 60 종결 PASS 카운트 (가정 ~1850) → +18 = **~1868 PASS** 유지
- WebSocket 통합 시나리오 회귀 0건
- `_scan_loop` E2E 회귀 0건 (delta unsubscribe 변경 영향 0)
- `_stale_watcher_loop` 회귀 0건 (silent inactive 호출 경로 보존)
- 영향 인덱스 갱신 (`test-impact-index` 스킬)

---

## 5. 작업 순서 (확정 — 사이클 60 패턴 답습)

1. **team-leader (현재 — 완료)**: A2 4 함수 + 314L 확정 + 본 설계 카드 보강
2. **domain-expert 추가 자문 — 발주 여부 결정** (아래 §6)
3. **tdd-engineer Red 발주**:
   - A2 영향 9 property + 5 상수 외부 접근 grep 사전 점검 (Q1 권고 — A1 grep 이미 수행, A2 시점 변경 없음)
   - `_workspace/red/cycle61_phase2A2_stale_manager.md` 작성 (18 케이스)
4. **backend-dev Green 발주**:
   - `src/engine/stale_manager.py` 확장 (A2 4 함수 + 5 상수 추가)
   - scheduler.py 4 wrapper 추가 + 5 상수 re-export 추가
   - **stale_manager.py `_build_session_subscription_view` lazy import 제거** (`STALE_FRESHNESS_SECS` 이전 후 자연 해소)
   - 영향 인덱스 갱신
5. **tester Verify** (`trading-test` 스킬 — 사이클 60 hotfix 카테고리 분리 측정 패턴 답습):
   - 4 카테고리 분리 측정 (unit/engine + unit/db + integration + contract)
   - ~1850 → ~1868 PASS 회귀 0건
   - WebSocket 4 중 안전망 통합 시나리오 회귀 0건
   - silent inactive cap freeze 테스트 (60분 window × 3회 호출)
   - flakiness 차단 (사이클 58 V-2 + 사이클 60 hotfix 패턴)
   - push 후 CI conclusion 명시 확인
6. **sync-docs**:
   - `docs/HARNESS_CHANGELOG.md` 사이클 61 행 추가
   - `src/engine/CLAUDE.md` stale_manager.py 행 갱신 (A2 4 함수 + A2 5 상수 추가 명시)
   - 루트 `CLAUDE.md` 변경 이력 표 행 추가
   - `_workspace/refactor/2026-06-04_review.md` 카드 #2 갱신 (A2 완료 표기 + A3 잔류 명시)
7. **사용자 명시 commit + push 지시 대기** (메모리 정책, push 시점 §Q5 안전 가드 준수)

---

## 6. domain-expert 추가 자문 필요 여부 판단

### 6.1 사이클 60 응답서 §Q4 인용 재확인

> "Phase 2-A3 (HIGH 위험, ~321L): K stale watcher 핵심 + 5분 우선 재구독"
> "Phase 2-A2 (MEDIUM 위험, ~365L): silent inactive + universe guard"
> "회귀 가드 ~12 케이스 (cap 검증 + 보유/익일청산 보호 + 5분 지속 검증)"

응답서가 A2 영역도 *자세히* 분석 완료. team-leader 판단:

- **자문 재발주 불필요한 영역**: silent inactive cap 메커니즘 / universe guard 보유 보호 / delta unsubscribe 기본 패턴 — 응답서 §Q1~Q5 모두 권고 명시
- **자문 재발주 권고 영역 (신규 의제)**:
  - **신규 의제 #1**: `_force_reconnect_session` 의 `_ws.close()` 호출 시점이 KRX 메인 09:00~15:30 vs NXT 시간대 (08:00~09:00 / 15:30~20:00) 에서 *재연결 latency* 차이 (KIS 서버 부하 차이)
  - **신규 의제 #2**: `_evaluate_universe_guard` 의 보유 종목 보호 분기에서 `registry.is_ticker_held_by_any(ticker)` 호출 비용 — A1 lazy import 패턴 답습 시 매 ticker 마다 import 비용 누적 가능성
  - **신규 의제 #3**: Q6 보드 전환 race 의 A2 단계 실측 위험도 — `_delta_unsubscribe_dropped` 이 A2 이주 후 race 빈도 변화 (모듈 import 오버헤드 영향)

### 6.2 team-leader 결정

**옵션 1 (자문 발주)**: 신규 의제 3종 추가 자문 (소요 ~10~15분, 추가 인사이트 확보)
**옵션 2 (직행)**: 응답서 §Q1~Q7 권고 + 본 설계 카드 18 케이스로 충분 → tdd-engineer Red 직행

→ **사용자 결정 사항**. team-leader 권고는 **옵션 2 (직행)** — 응답서가 A2 영역도 충분히 커버하고, 신규 의제는 *low priority* (운영 발견 후 사후 자문 가능). MEDIUM 등급 한 사이클을 위해 매번 자문 발주는 비용 과다.

---

## 7. 후속 카드 발의 (본 사이클 종료 후)

| 카드 | 사이클 | 위험 | push 시점 |
|---|---|---|---|
| Phase 2-A3 (K stale watcher 핵심 2 함수) | 사이클 62 | **HIGH** | **주말 필수** + 월요일 _boot 1h tester verify (응답서 §Q5 권고) |
| #11 보드 전환 mutex (Q6 별개 카드) | 사이클 63? | MEDIUM-HIGH | A3 진행 *전* 발의 권고 (보드 전환 ↔ silent inactive race 가능성) |
| 가격 필터 (사용자 결정) | 사이클 62 대안 | MEDIUM | 백엔드 + 프론트 단일 사이클 |

**사용자 사이클 62 결정**:
- 옵션 가: A2 push → 운영 1~2 영업일 검증 → A3 (HIGH) 진행
- 옵션 나: A2 push → 가격 필터 (MEDIUM) 진행 → A3 추후

본 사이클 종료 보고 시 가격 필터 사전 준비 (자문 의제 6 종 + 설계 카드 1 차 sketch) 동행 권고 (사용자 인계 사항).

---

## 8. 절대 깨지 말 것 (체크리스트)

CLAUDE.md 절대 규칙 + 사이클 24/29-R2/32/15-A 신규:

- [x] 체결통보 구독 (H0STCNI0/H0STCNI9) 영역 무관 (본 카드 외)
- [x] uvicorn 단일 워커 영향 0
- [x] WebSocket 4 중 안전망 — A2 4 함수 이주, 호출자 (`_scan_loop` / `_stale_watcher_loop`) 잔류 → 4 중 안전망 행위 보존
- [x] **silent inactive 시간당 세션당 2회 cap (KIS LMS/앱키 정지 위험)** — Q1-G2 cap dict 동일성 가드 + G silent inactive 시간당 cap freezegun 가드 2 케이스 동시 보호
- [x] **stale universe 가드 (보유/익일청산 절대 보호)** — I 보유 보호 + J 익일청산 보호 가드 2 케이스
- [x] K stale watcher 우선순위 분리 — A2 범위 *밖* 함수 (A3 사이클 62)
- [x] `_reset_daily_state` 동행 reset — A2 영향 3 필드 자동 보존 (`_stale_state.reset_daily()` 통합), 회귀 가드 1 케이스
- [x] **KIS "비정상 케이스 2" (무한 등록/해제) 차단 (사이클 15-A)** — `_delta_unsubscribe_dropped` 이주 시 행위 보존 + delta 계산 정확성 (`current - new_set`) 보존
- [x] KST 강제 (모든 시각 KST timezone 명시) — A2 4 함수 모두 `KST_TZ` lazy import 보존
- [x] `_subscriptions` ACK 정합성 가드 — A2 함수 모두 `kis_ws_pool.unsubscribe` / `subscribe` 만 사용, 직접 수정 0
- [x] logger 명시 binding (사이클 60 I1 영구 가드) — stale_manager.py 단일 logger 재사용

---

## 9. 예상 효과

- `scheduler.py` 3,605 → ~3,291 (-314L, **-8.7% 본 사이클**)
- 사이클 51 + 60 + 61 누적 분해 (4,185L → ~3,291L, **-21%**)
- A3 사이클 62 완료 후 누적 (4,185L → ~2,970L, **-29%**)
- `stale_manager.py` 358 → ~720L (A1+A2 통합) — *향후 A3 시점 모듈 분리 여부 재평가* (전체 1,000L+ 시점)

---

## 10. 위험 평가 매트릭스 (A2 한정)

| 영역 | 위험 | 완화 |
|---|---|---|
| `_force_reconnect_session` cap dict 동일성 회귀 | **HIGH** | Q1-G2 가드 1 케이스 (`is` 동일성) + G cap freezegun 1 케이스 (이중 안전망) |
| silent inactive 5분 지속 판정 회귀 | MEDIUM | H 판정 가드 1 케이스 (freezegun 4분30s / 5분) |
| universe guard 보유/익일청산 보호 회귀 | **HIGH** | I + J 가드 2 케이스 (사전 가드 순서 보존) |
| delta unsubscribe race (보드 전환) | MEDIUM | K race 시뮬레이션 1 케이스 + 별개 카드 #11 발의 (사후 mutex) |
| 5 상수 외부 import 호환 | LOW | re-export + Q3-G1~G5 가드 5 케이스 |
| 의존성 역전 (`STALE_FRESHNESS_SECS` lazy import 제거) | LOW | Q3-G6 정적 검증 가드 1 케이스 + Green 시점 lazy import 제거 |
| `_reset_daily_state` 동행 reset 회귀 | MEDIUM | Q2-G1 가드 1 케이스 + Q2-G2 dataclass 누락 가드 1 케이스 |
| logger 명시 binding 회귀 | LOW | 사이클 60 I1 영구 가드 답습 (운영 로그 누락 위험 차단) |

→ HIGH 2 영역 (cap dict + 보유 보호), MEDIUM 4 영역. **회귀 0건 절대 요구**.

---

## 11. 운영 안전 가드 재확인

- **현재 시각**: 2026-06-05 (금) 09:35 KST = **KRX 메인 진입 직후**
- **push 가능 시간**:
  - 오늘 NXT 애프터 18:00 이후 (옵션 A) — 사용 시 1~2h tester verify 동반
  - 주말 (옵션 B) — 가장 안전, team-leader 권고
  - 월요일 새벽 06:00~07:50 (옵션 C) — _boot 전
- **18:00 까지 작업 여유**: 약 8h 25min — tdd-engineer Red + backend-dev Green + tester Verify + sync-docs 모두 충분 (단, KRX 메인 시간대 git push 자제 — `_scan_loop` 5분 race 가능)
- **회귀 발생 시 hotfix**: NXT 애프터 시간대 즉시 가능 (사이클 60 hotfix 패턴 — 시간 가드 보강)
- **사용자 commit 명시 전 git 작업 금지** (메모리 정책)

---

## 12. 사이클 60 회수 사항 (인계 처리)

| 항목 | 사이클 60 인계 | A2 적용 |
|---|---|---|
| 명세 vs 실측 정정 | G-1 "6 필드" → 실측 7 필드 정정 | Q2-G2 dataclass 필드 누락 가드 영구 추가 (사이클 60 정정 사례 답습) |
| flakiness 차단 | tester 카테고리 분리 측정 의무 | tester verify 단계 4 카테고리 분리 + 사이클 58 V-2 패턴 답습 |
| logger 명시 binding (I1 영구 가드) | A1 신규 함수 logger binding 완료 | A2 신규 함수도 stale_manager.py 단일 logger 재사용 (자동 보존) |
| `_workspace/refactor/2026-06-04_review.md` 카드 #2 | A2 완료 표기 의무 | sync-docs 단계 갱신 |

---

## 부록 — A2 4 함수 위치 실측 인용 (scheduler.py)

```
L2423: def _detect_silent_inactive_sessions(self) -> list[str]:           # 62L  (~L2484)
L2485: async def _force_reconnect_session(self, label: str) -> bool:      # 83L  (~L2567)
L2811: async def _delta_unsubscribe_dropped(self, new_set: set[str]):     # 52L  (~L2862)
L2964: async def _evaluate_universe_guard(self, candidate_tickers):       # 117L (~L3080)
```

**합계**: 314L (scheduler.py 의 ~8.7%)

A2 추가 5 상수 위치 인용:
```
L82:  STALE_FRESHNESS_SECS = 60
L104: SILENT_INACTIVE_MIN_SUBSCRIBED = 5
L105: SILENT_INACTIVE_PERSIST_SECS = 300.0
L106: SILENT_INACTIVE_RECOVERY_CAP_PER_HOUR = 2
L107: SILENT_INACTIVE_RECOVERY_WINDOW_SECS = 3600.0
```

---

## 13. 다음 단계 결정 (사용자 인계)

**team-leader 단계 종료** — 다음 진행 옵션:

| 옵션 | 내용 | 소요 |
|---|---|---|
| **A** | domain-expert 추가 자문 (§6.2 신규 의제 3 종) | ~15~20min |
| **B** | tdd-engineer Red 직행 (응답서 §Q1~Q7 + 본 설계 카드 18 케이스 충분) | 즉시 |

**team-leader 권고**: **옵션 B (직행)** — A2 MEDIUM 등급에 자문 비용 과다, 응답서 충분 커버.

**push 시점 사용자 결정 (Q5)**:
| 옵션 | 시점 | 위험 |
|---|---|---|
| **A** | 오늘 (금) NXT 애프터 18:00 이후 | NXT 거래량 적은 시각 매매 영향 작음 |
| **B** | **주말 (토/일)** — **team-leader 권고** | 매매 영향 0 + 월요일 _boot 첫 검증 |
| **C** | 월요일 새벽 06:00~07:50 | _boot 전 검증 |

사용자가 다음 단계 (옵션 A vs B) + push 시점 (옵션 A/B/C) 결정 → tdd-engineer Red 발주 인계.
