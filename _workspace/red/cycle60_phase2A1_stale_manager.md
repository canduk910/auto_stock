# Red 명세 — 사이클 60 Phase 2-A1 stale_manager 추출 (LOW)

> **작성**: team-leader (2026-06-04 16:15 KST, 골격 + grep 사전 점검 결과 첨부) → tdd-engineer 가 본체 작성
> **선행 카드**: `_workspace/cycle60_phase2A1_design_card.md`
> **자문 응답**: `_workspace/cycle60_phase2A_domain_response.md` (Q1~Q7 전부 반영)
> **위험 등급**: LOW (read-only 4 함수 + ccnl evict 1 함수, 매매 hot path 무영향)
> **TDD 사이클**: Red (회귀 가드 사전 작성) → Green (stale_manager.py 신규 A1 5 함수 + wrapper) → Refactor

---

## 9 property 외부 접근 사전 점검 결과 (Q1 권고 — team-leader 사전 실행)

### 프로덕션 코드 외부 접근 (1 곳)

**파일**: `src/routes/realtime.py`

```python
L82:    # scheduler._stale_retry_count / _stale_last_resubscribe_at 접근 — 부재 시 graceful.
L83:    ...
L84:    # 사이클 37 (2026-05-21) — KIS 실제 last_cntg_hour 캐시 매핑 (`_last_ccnl_cache`).
L85:    ...
L88:        stale_retry_count = getattr(trading_scheduler, "_stale_retry_count", {}) or {}
L89:        stale_last_resubscribe_at = getattr(trading_scheduler, "_stale_last_resubscribe_at", {}) or {}
L91:        last_ccnl_cache = getattr(trading_scheduler, "_last_ccnl_cache", {}) or {}
```

**3 property 접근** (모두 `getattr` graceful 패턴):
- `_stale_retry_count`
- `_stale_last_resubscribe_at`
- `_last_ccnl_cache`

### A1 영향 평가

본 A1 5 함수 중 외부 접근 property 사용 함수:
- `_refresh_stale_ccnl_cache` (A1 이동 대상) → `_last_ccnl_cache` 접근 (set)
- `_evict_expired_ccnl` (A1 이동 대상) → `_last_ccnl_cache` 접근 (delete)
- `_prune_force_retry_history` (A1 이동 대상) → `_stale_force_retry_history` 접근 (delete)

**결론**: realtime.py 의 3 property 접근은 *읽기 only* + `getattr` graceful. stale_manager 가 *동일 경로 (scheduler.\_last\_ccnl\_cache 등 property setter) 로 쓰기* 보장하면 외부 접근 호환 영속. **A1 진행 시 호환 유지** (property layer 보존).

### 테스트 코드 외부 접근

다수 발견 (정상 — 테스트는 직접 접근 패턴 의도된 사용):
- `tests/unit/engine/test_scheduler_stale_tracking.py` (사이클 28 회귀 가드, B2-1~B2-3)
- `tests/unit/engine/test_session_silent_inactive_ratio.py` (사이클 24 회귀 가드)

**결론**: 테스트는 회귀 가드로 *유지*. stale_manager 함수가 property 경로 (`sched._stale_retry_count` 등) 통해 동일하게 작동하면 회귀 0건.

---

## 회귀 가드 17 케이스 (A1 한정)

### 카테고리 A — 위임 1회 검증 (5 케이스)

각 wrapper 가 `stale_manager` 단일 함수만 호출하는지 검증.

| # | 테스트 | 검증 |
|---|---|---|
| A-1 | `_build_session_subscription_view` → `stale_manager.build_session_subscription_view(self)` 1 회 | mock spy + call_args |
| A-2 | `_emit_stale_session_detail(...)` → `stale_manager.emit_stale_session_detail(self, ...)` 1 회 | mock spy |
| A-3 | `_refresh_stale_ccnl_cache(...)` → `stale_manager.refresh_stale_ccnl_cache(self, ...)` 1 회 (async) | mock spy + await |
| A-4 | `_evict_expired_ccnl(now)` → `stale_manager.evict_expired_ccnl(self, now)` 1 회 | mock spy |
| A-5 | `_prune_force_retry_history(...)` → `stale_manager.prune_force_retry_history(self, ...)` 1 회 | mock spy |

**파일**: `tests/unit/engine/test_cycle60_phase2A1_delegation.py`
**패턴**: `unittest.mock.patch.object(stale_manager, "...")` + assert call_count==1 + assert call_args

### 카테고리 B — 5 상수 동일성 (Q3-G1~G5, 5 케이스)

| # | 테스트 | 검증 |
|---|---|---|
| B-1 | `MAX_STALE_RETRIES` | `scheduler.MAX_STALE_RETRIES is stale_manager.MAX_STALE_RETRIES` + `== 5` |
| B-2 | `STALE_FORCE_RETRY_AFTER_SECS` | 동일 + `== 300` |
| B-3 | `STALE_FORCE_RETRY_HOURLY_CAP` | 동일 + `== 12` |
| B-4 | `UNIVERSE_LOW_VOLUME_THRESHOLD` | 동일 + `== 10_000` |
| B-5 | `SILENT_INACTIVE_FRESH_RATIO_THRESHOLD` | 동일 + `== 0.2` |

**파일**: `tests/unit/engine/test_cycle60_phase2A1_constants.py`
**패턴**: 단일 파일 5 케이스 묶음. `is` 동일성 보장 (re-export 검증)

### 카테고리 C — 호출 순서 보존 (Q1-G3, 2 케이스)

| # | 테스트 | 검증 |
|---|---|---|
| C-1 | K stale watcher → `_emit_stale_session_detail` 호출 순서 보존 (사이클 28 도입 순서) | mock call_order + scheduler._stale_watcher_loop 1 cycle simulation |
| C-2 | `_refresh_stale_ccnl_cache` 호출 후 `_evict_expired_ccnl` 호출 순서 (TTL 갱신 후 evict) | mock spy + 호출 순서 검증 |

**파일**: `tests/unit/engine/test_cycle60_phase2A1_call_order.py`

### 카테고리 D — 의존성 역전 정적 검증 (Q3-G6, 1 케이스)

| # | 테스트 | 검증 |
|---|---|---|
| D-1 | `ast` 모듈로 `src/engine/stale_manager.py` 의 `from src.engine.scheduler import` / `import scheduler` 검색 → 발견 시 fail | static analysis |

**파일**: `tests/unit/engine/test_cycle60_phase2A1_dependency_inversion.py`
**구현 예시**:
```python
import ast
def test_stale_manager_does_not_import_scheduler():
    with open("src/engine/stale_manager.py") as f:
        tree = ast.parse(f.read())
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            assert not (node.module and "scheduler" in node.module)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                assert "scheduler" not in alias.name
```

### 카테고리 E — ccnl TTL evict (1 케이스)

| # | 테스트 | 검증 |
|---|---|---|
| E-1 | TTL 만료 항목 evict + 미만료 항목 보존 (freezegun) | dict pre/post 비교 |

**파일**: `tests/unit/engine/test_cycle60_phase2A1_ccnl_evict.py`

### 카테고리 F — force_retry 시간당 cap (1 케이스)

| # | 테스트 | 검증 |
|---|---|---|
| F-1 | 동일 종목 13번째 force_retry 시 skip (cap=12, freezegun 1시간) | history 길이 12 유지 |

**파일**: `tests/unit/engine/test_cycle60_phase2A1_force_retry_cap.py`

### 카테고리 G — `_reset_daily_state` 동행 reset (Q2-G1, 1 케이스)

| # | 테스트 | 검증 |
|---|---|---|
| G-1 | scheduler.`_reset_daily_state()` 호출 후 6 필드 동시 검증 + dataclass 필드 누락 가드 | 6 assert + `dataclasses.fields(StaleTrackerState)` 비교 |

**파일**: `tests/unit/engine/test_cycle60_phase2A1_reset_daily_state.py`
**구현 예시**:
```python
def test_reset_daily_state_clears_all_stale_fields():
    sched = TradingScheduler()
    # 사전 더미 데이터 주입
    sched._stale_state.retry_count = {"005930": 3}
    sched._stale_state.last_resubscribe_at = {"005930": datetime.now(KST)}
    sched._stale_state.force_retry_history = {"005930": [datetime.now(KST)]}
    sched._silent_inactive_first_seen["main"] = datetime.now(KST)
    sched._silent_inactive_recovery_count["main"] = [datetime.now(KST).timestamp()]
    sched._universe_excluded_today.add("005930")

    sched._reset_daily_state()

    assert sched._stale_state.retry_count == {}
    assert sched._stale_state.last_resubscribe_at == {}
    assert sched._stale_state.force_retry_history == {}
    assert sched._silent_inactive_first_seen == {}
    assert sched._silent_inactive_recovery_count == {}
    assert sched._universe_excluded_today == set()

    # 추가 가드 — dataclass 필드 누락 방지
    from dataclasses import fields
    from src.engine.stale_tracker import StaleTrackerState
    fresh = StaleTrackerState()
    for f in fields(StaleTrackerState):
        assert getattr(sched._stale_state, f.name) == getattr(fresh, f.name), (
            f"reset_daily() 가 필드 {f.name} 초기화 누락"
        )
```

### 카테고리 H — import sanity (1 케이스)

| # | 테스트 | 검증 |
|---|---|---|
| H-1 | `from src.engine import stale_manager` 성공 + 5 함수 (`build_session_subscription_view`, `emit_stale_session_detail`, `refresh_stale_ccnl_cache`, `evict_expired_ccnl`, `prune_force_retry_history`) + 5 상수 노출 | hasattr + callable + value 검증 |

**파일**: `tests/unit/engine/test_cycle60_phase2A1_imports.py`

---

## 총 17 케이스

| 카테고리 | 케이스 | 위험 등급 |
|---|---|---|
| A 위임 1회 | 5 | LOW (mock) |
| B 5 상수 | 5 | LOW |
| C 호출 순서 | 2 | MEDIUM |
| D 의존성 역전 정적 | 1 | LOW |
| E ccnl TTL evict | 1 | LOW |
| F force_retry cap | 1 | MEDIUM |
| G reset 동행 | 1 | HIGH |
| H import sanity | 1 | LOW |
| **합계** | **17** | HIGH 1 / MEDIUM 3 / LOW 13 |

---

## 통과 기준

- 백엔드 1844 PASS (사이클 58 V-2 기준) → **1844 + 17 = 1861 PASS** 유지
- 기존 `tests/unit/engine/test_scheduler_stale_tracking.py` + `test_session_silent_inactive_ratio.py` 회귀 0건 (property layer 보존 검증)
- `src/routes/realtime.py` 의 `getattr(trading_scheduler, "_last_ccnl_cache", ...)` 호환 (property 경로 유지)
- WebSocket 통합 시나리오 회귀 0건 (A1 범위 *밖* 함수 그대로 작동)
- `_scan_loop` E2E 회귀 0건

---

## 사전 조건 (Red 작성 *전*)

- [x] 9 property 외부 접근 grep 사전 점검 (team-leader 실행 완료 — realtime.py 3 property `getattr` 패턴 확인)
- [x] domain-expert 자문 회신 (`_workspace/cycle60_phase2A_domain_response.md`)
- [x] 사용자 채택 결정 (옵션 A 전부 적용)
- [x] team-leader 설계 카드 보강 (`_workspace/cycle60_phase2A1_design_card.md`)
- [ ] **tdd-engineer 가 본 명세 기반 Red 17 케이스 본체 작성** (다음 단계)

---

## 후속 단계 (Green 발주)

본 17 케이스 Red 통과 후:
- **backend-dev**:
  - `src/engine/stale_manager.py` 신규 (A1 5 함수 + 5 상수, ~350~400L)
  - `src/engine/scheduler.py` 5 wrapper 2 줄 위임 + 5 상수 re-export (`from src.engine.stale_manager import MAX_STALE_RETRIES, ...`)
- **test-impact-index**: Python AST 영향 인덱스 갱신
- 17 케이스 + 기존 1844 PASS = **1861 PASS** 통과 검증

---

## CLAUDE.md 절대 규칙 보호 체크리스트 (재확인)

- [x] WebSocket 4 중 안전망 — A1 범위 *밖* 함수 (read-only 5 함수만 이동) → 행위 보존
- [x] K stale watcher 우선순위 분리 — A1 범위 *밖*
- [x] silent inactive 시간당 세션당 2회 cap — A1 범위 *밖*
- [x] stale universe 가드 — A1 범위 *밖*
- [x] `_reset_daily_state` 동행 reset — **카테고리 G 1 케이스 가드** (Q2-G1 6 필드 + dataclass 필드 누락)
- [x] `_subscriptions` ACK 정합성 가드 — A1 범위 *밖*
- [x] KST 강제 — stale_manager 함수 시그니처에 `KST_TZ` import 명시

---

## tdd-engineer 발주 시 주의사항

1. **본 명세 17 케이스 골격 그대로 작성** — 케이스 추가/삭제 시 team-leader 확인 필수
2. **9 property 외부 접근 grep 결과 반영**: realtime.py 의 3 property 호환 보장 (property layer 보존)
3. **freezegun + asyncio mock 활용**: 카테고리 E/F/G 시간 freeze 필수
4. **카테고리 G HIGH 우선**: `_reset_daily_state` 동행 reset 가드는 최우선 작성 (사이클 32 universe 가드 + 사이클 29 force_retry 누적 카운터 모두 초기화 보장)
5. **회귀 0건 보장 후 backend-dev Green 발주**
