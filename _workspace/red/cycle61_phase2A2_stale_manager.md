# Red 명세 — 사이클 61 Phase 2-A2 stale_manager 추가 이주 (MEDIUM)

> **작성**: team-leader (2026-06-05 09:40 KST, 골격 + 사이클 60 A1 grep 결과 답습) → tdd-engineer 가 본체 작성
> **선행 카드**: `_workspace/cycle61_phase2A2_design_card.md`
> **선행 사이클**: 사이클 60 = Phase 2-A1 (LOW, push 완료 + CI ✅ `436aa3c`)
> **선행 자문**: `_workspace/cycle60_phase2A_domain_response.md` (§Q1~Q7 A2 영역 권고 인용)
> **위험 등급**: **MEDIUM** (silent inactive cap + universe guard, KIS LMS/앱키 정지 위험 영역)
> **TDD 사이클**: Red (회귀 가드 사전 작성) → Green (stale_manager.py 확장 A2 4 함수 + wrapper) → Refactor

---

## 9 property 외부 접근 사전 점검 결과 (Q1 권고, A1 grep 재활용)

### 프로덕션 코드 외부 접근 (사이클 60 A1 grep 결과 답습 — 변경 없음)

**파일**: `src/routes/realtime.py` L82~91 — 3 property `getattr` graceful (A2 영향 0)
- `_stale_retry_count` (A2 사용 안 함)
- `_stale_last_resubscribe_at` (A2 `_evaluate_universe_guard` 읽기 사용)
- `_last_ccnl_cache` (A2 사용 안 함)

**A2 4 함수의 _stale_state property 접근 매트릭스**:

| 함수 | 접근 property | 작업 |
|---|---|---|
| `_detect_silent_inactive_sessions` | `_silent_inactive_first_seen` | set/pop |
| `_force_reconnect_session` | `_silent_inactive_first_seen` + `_silent_inactive_recovery_count` | pop / setdefault + append + in-place evict |
| `_delta_unsubscribe_dropped` | (없음 — `kis_ws_pool` 만 사용) | — |
| `_evaluate_universe_guard` | `_stale_retry_count` + `_stale_last_resubscribe_at` + `_universe_excluded_today` | 읽기 / 읽기 / add |

**결론**: A2 4 함수가 사용하는 4 property (`_silent_inactive_first_seen` / `_silent_inactive_recovery_count` / `_stale_retry_count` / `_stale_last_resubscribe_at` / `_universe_excluded_today`) 모두 `StaleTrackerState` 데이터클래스 통합 (사이클 48) → property setter 경로 보존하면 회귀 0건.

### 테스트 코드 외부 접근 (A2 영향)

핵심 테스트 파일 (이주 후에도 변경 없이 PASS 보장 의무):
- `tests/unit/engine/test_session_silent_inactive_ratio.py` — `_silent_inactive_first_seen` 직접 접근 다수 (L91/118/154/169/182/207/220/242/270 등)
- `tests/unit/engine/test_scheduler_stale_tracking.py` (사이클 28 B2-1~B2-3)
- `tests/unit/engine/test_stale_watcher_thresholds.py` (사이클 17/24/29-R1 회귀 가드)

**결론**: 테스트는 회귀 가드로 *유지*. stale_manager A2 함수가 property 경로 (`sched._silent_inactive_first_seen` 등) 통해 동일 작동하면 회귀 0건.

---

## 회귀 가드 18 케이스 (A2 한정)

### 카테고리 A — 위임 1회 검증 (4 케이스)

각 wrapper 가 `stale_manager` 단일 함수만 호출하는지 검증.

| # | 테스트 | 검증 |
|---|---|---|
| A-1 | `_detect_silent_inactive_sessions()` → `stale_manager.detect_silent_inactive_sessions(self)` 1 회 | mock spy + call_args |
| A-2 | `_force_reconnect_session("main")` → `stale_manager.force_reconnect_session(self, "main")` 1 회 (async) | mock spy + await |
| A-3 | `_delta_unsubscribe_dropped({"005930"})` → `stale_manager.delta_unsubscribe_dropped(self, ...)` 1 회 (async) | mock spy + await |
| A-4 | `_evaluate_universe_guard([...])` → `stale_manager.evaluate_universe_guard(self, ...)` 1 회 (async) | mock spy + await |

**파일**: `tests/unit/engine/test_cycle61_phase2A2_delegation.py`
**패턴**: 사이클 60 A1 `test_cycle60_phase2A1_delegation.py` 답습 — `unittest.mock.patch.object(stale_manager, "...")` + assert call_count==1 + assert call_args

### 카테고리 B — 5 상수 동일성 (Q3-G1~G5, 5 케이스)

| # | 테스트 | 검증 |
|---|---|---|
| B-1 | `SILENT_INACTIVE_MIN_SUBSCRIBED` | `scheduler.X is stale_manager.X` + `== 5` |
| B-2 | `SILENT_INACTIVE_PERSIST_SECS` | 동일 + `== 300.0` |
| B-3 | `SILENT_INACTIVE_RECOVERY_CAP_PER_HOUR` | 동일 + `== 2` |
| B-4 | `SILENT_INACTIVE_RECOVERY_WINDOW_SECS` | 동일 + `== 3600.0` |
| B-5 | `STALE_FRESHNESS_SECS` | 동일 + `== 60` |

**파일**: `tests/unit/engine/test_cycle61_phase2A2_constants.py`
**패턴**: 사이클 60 A1 `test_cycle60_phase2A1_constants.py` 답습. `is` 동일성 보장 (re-export 검증).

**주의 (Green 시점)**:
- `STALE_FRESHNESS_SECS` 이 stale_manager 로 이전되면 scheduler.py `_check_and_resubscribe_stale` L2615 + `_resubscribe_stale_priority` L2899 + `_session_health_loop` 등 잔류 함수도 `STALE_FRESHNESS_SECS` re-export 경로로 접근 (모듈 상수 변경 없음 — `is` 동일성 보장)
- 사이클 60 A1 의 `_build_session_subscription_view` 가 사용한 lazy import 패턴 (`from src.engine import scheduler as _sched_mod; _sched_mod.STALE_FRESHNESS_SECS`) 은 **Green 시점 제거** (이전 후 자연 해소) — D-1 정적 검증 가드로 보장

### 카테고리 C — cap dict `is` 동일성 (Q1-G2, **HIGH** 1 케이스)

`_force_reconnect_session` 의 시간당 cap dict `_silent_inactive_recovery_count` 가 이주 후에도 *동일 dict 참조* 유지 — KIS LMS/앱키 정지 위험 영구 차단.

| # | 테스트 | 검증 |
|---|---|---|
| C-1 | cap dict `is` 동일성 (HIGH) | `scheduler._silent_inactive_recovery_count is scheduler._stale_state.silent_inactive_recovery_count` + `force_reconnect_session` 호출 후에도 동일 참조 유지 (mutation 후 같은 dict) |

**파일**: `tests/unit/engine/test_cycle61_phase2A2_cap_dict_identity.py`
**패턴**:
```python
sched = TradingScheduler.__new__(TradingScheduler)
sched._ensure_stale_state()
dict_before = sched._silent_inactive_recovery_count
assert dict_before is sched._stale_state.silent_inactive_recovery_count

# stale_manager 함수가 동일 dict 에 mutation 후에도 참조 동일
from src.engine import stale_manager
stale_manager.force_reconnect_session  # 호출은 mock 으로 차단 가능 (시그니처 검증만)
assert sched._silent_inactive_recovery_count is dict_before
```

**중요**: 사이클 60 A1 `_last_ccnl_cache` 동일성 가드와 동일 패턴 답습 (사이클 60 hotfix I1 영구 가드 일관성).

### 카테고리 D — 의존성 역전 정적 검증 (Q3-G6 갱신, 1 케이스)

| # | 테스트 | 검증 |
|---|---|---|
| D-1 | stale_manager.py 가 scheduler.py 역참조 안 함 (lazy import 제거 검증) | `ast` 모듈로 `src/engine/stale_manager.py` AST 파싱 → `from src.engine.scheduler import` / `import src.engine.scheduler` / `from src.engine import scheduler` 검색 → 발견 시 fail |

**파일**: `tests/unit/engine/test_cycle61_phase2A2_dependency_direction.py`
**패턴**:
```python
import ast
from pathlib import Path

def test_stale_manager_does_not_import_scheduler():
    src = Path("src/engine/stale_manager.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.module == "src.engine.scheduler":
                raise AssertionError(
                    f"stale_manager.py L{node.lineno}: scheduler 역참조 발견 — "
                    "사이클 60 A1 lazy import (`from src.engine import scheduler as _sched_mod`) "
                    "는 사이클 61 A2 시점 STALE_FRESHNESS_SECS 이전 후 제거 의무"
                )
            if node.module == "src.engine" and any(
                alias.name == "scheduler" for alias in node.names
            ):
                raise AssertionError(
                    f"stale_manager.py L{node.lineno}: `from src.engine import scheduler` 역참조 발견"
                )
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "src.engine.scheduler":
                    raise AssertionError(
                        f"stale_manager.py L{node.lineno}: `import src.engine.scheduler` 역참조 발견"
                    )
```

**주의**: 사이클 60 A1 의 `_build_session_subscription_view` lazy import (line ~62 `from src.engine import scheduler as _sched_mod; _STALE_FRESHNESS_SECS = _sched_mod.STALE_FRESHNESS_SECS`) 는 본 사이클 Green 시점 제거 의무 — D-1 가드로 영구 차단.

### 카테고리 E — `_reset_daily_state` 동행 reset (Q2-G1, 1 케이스)

A2 영향 3 필드 동시 검증.

| # | 테스트 | 검증 |
|---|---|---|
| E-1 | `_reset_daily_state()` 호출 후 A2 3 필드 초기화 | `_silent_inactive_first_seen == {}` + `_silent_inactive_recovery_count == {}` + `_universe_excluded_today == set()` |

**파일**: `tests/unit/engine/test_cycle61_phase2A2_reset_daily.py`
**패턴**:
```python
sched = TradingScheduler.__new__(TradingScheduler)
sched._ensure_stale_state()
# 임의 mutation
sched._silent_inactive_first_seen["main"] = datetime.now(KST)
sched._silent_inactive_recovery_count["quote-1"] = [time.time()]
sched._universe_excluded_today.add("005930")
# ... (registry / order_engine / scanner 등은 mock 필요)
sched._reset_daily_state()
assert sched._silent_inactive_first_seen == {}
assert sched._silent_inactive_recovery_count == {}
assert sched._universe_excluded_today == set()
```

**중요**: `_reset_daily_state` 가 다른 전략 / order_engine / scanner 도 reset 하므로, 본 테스트는 *해당 영역 mock 필수*. tdd-engineer 가 `sched._registry` / `sched.order_engine` 등 minimal mock 주입.

### 카테고리 F — dataclass 필드 누락 가드 (Q2-G2, 1 케이스)

**사이클 60 G-1 정정 사례 영구 가드** (명세 "6 필드" → 실측 7 필드 정정).

| # | 테스트 | 검증 |
|---|---|---|
| F-1 | `StaleTrackerState` 필드 7 종 일치 (reset 후 모두 빈 값) | `dataclasses.fields(StaleTrackerState)` 7 필드 검증 + reset_daily() 후 7 필드 모두 빈 dict/set |

**파일**: `tests/unit/engine/test_cycle61_phase2A2_dataclass_completeness.py`
**패턴**:
```python
import dataclasses
from src.engine.stale_tracker import StaleTrackerState

def test_stale_tracker_state_has_7_fields():
    fields = dataclasses.fields(StaleTrackerState)
    field_names = {f.name for f in fields}
    expected = {
        "retry_count", "last_resubscribe_at", "force_retry_history",
        "silent_inactive_first_seen", "silent_inactive_recovery_count",
        "universe_excluded_today", "last_ccnl_cache",
    }
    assert field_names == expected, (
        f"StaleTrackerState 필드 불일치 — 사이클 48 정의 7 필드 보존 의무. "
        f"실측: {field_names}, 기대: {expected}"
    )

def test_reset_daily_clears_all_fields():
    state = StaleTrackerState()
    # 모든 필드 임의 mutation
    state.retry_count["a"] = 1
    state.last_resubscribe_at["a"] = datetime.now(KST)
    state.force_retry_history["a"] = [datetime.now(KST)]
    state.silent_inactive_first_seen["main"] = datetime.now(KST)
    state.silent_inactive_recovery_count["main"] = [1.0]
    state.universe_excluded_today.add("005930")
    state.last_ccnl_cache["a"] = {"x": 1}
    state.reset_daily()
    # 7 필드 모두 빈 값
    for f in dataclasses.fields(StaleTrackerState):
        val = getattr(state, f.name)
        if isinstance(val, dict):
            assert val == {}, f"{f.name} reset 누락"
        elif isinstance(val, set):
            assert val == set(), f"{f.name} reset 누락"
        else:
            raise AssertionError(f"{f.name} 타입 처리 미정의 ({type(val)})")
```

### 카테고리 G — silent inactive 시간당 cap (1 케이스, freezegun)

`_force_reconnect_session` 3번째 호출 시 cap=2 도달 → False 반환 + WARNING 로그.

| # | 테스트 | 검증 |
|---|---|---|
| G-1 | cap 도달 시 reconnect skip (freezegun, 60분 window 내 3회 호출) | 1회 = True, 2회 = True, 3회 = False (cap=2 초과). `[silent_inactive_recovery_cap]` WARNING 로그 emit (caplog) |

**파일**: `tests/unit/engine/test_cycle61_phase2A2_silent_inactive_cap.py`
**패턴**:
```python
from freezegun import freeze_time

@freeze_time("2026-06-05 10:00:00")
async def test_silent_inactive_cap_60min_window():
    sched = TradingScheduler.__new__(TradingScheduler)
    sched._ensure_stale_state()
    # kis_ws / kis_ws_pool mock — _ws.close() AsyncMock
    ...
    # 1회 호출 — 성공
    result1 = await sched._force_reconnect_session("main")
    assert result1 is True
    assert len(sched._silent_inactive_recovery_count["main"]) == 1

    # 2회 호출 — 성공 (시간 동결, 같은 monotonic 시각)
    result2 = await sched._force_reconnect_session("main")
    assert result2 is True
    assert len(sched._silent_inactive_recovery_count["main"]) == 2

    # 3회 호출 — cap 도달 skip
    result3 = await sched._force_reconnect_session("main")
    assert result3 is False
    assert len(sched._silent_inactive_recovery_count["main"]) == 2  # 증가 안 함
    assert "[silent_inactive_recovery_cap]" in caplog.text
```

**중요**: `time.time()` (monotonic 아님 — 본체 L2501 확인) 사용이므로 `freezegun` 으로 시각 동결 가능. caplog logger 명시 binding 가드 (`caplog.set_level(logging.WARNING, logger="src.engine.scheduler")`).

### 카테고리 H — silent inactive 5분 지속 판정 (1 케이스, freezegun)

`_detect_silent_inactive_sessions` — 4분 30s = 미감지 / 5분 = 감지.

| # | 테스트 | 검증 |
|---|---|---|
| H-1 | 5분 지속 임계 정확성 (freezegun) | first_seen=10:00:00 → 10:04:30 미감지 / 10:05:00 감지 (`SILENT_INACTIVE_PERSIST_SECS=300.0` 임계) |

**파일**: `tests/unit/engine/test_cycle61_phase2A2_silent_inactive_5min.py`
**패턴**: 기존 `tests/unit/engine/test_session_silent_inactive_ratio.py` 답습 — fresh_ratio < 0.2 + sub >= 5 조건 충족 시나리오 + first_seen 시각 5분 전 설정 + freezegun 으로 4분30s vs 5분 분기.

### 카테고리 I — universe guard 보유 보호 (**HIGH**, 1 케이스)

`_evaluate_universe_guard` — 보유 종목은 stale>5 + low_volume 이어도 제외 안 함.

| # | 테스트 | 검증 |
|---|---|---|
| I-1 | 보유 종목 절대 보호 (HIGH) | `registry.is_ticker_held_by_any("005930") == True` 시 stale=10 + today_volume=100 (≤ THRESHOLD) 시나리오에서 `_universe_excluded_today` 에 추가 안 됨 + `inquire_ccnl` 호출 자체 skip |

**파일**: `tests/unit/engine/test_cycle61_phase2A2_universe_guard_held_protection.py`
**패턴**:
```python
async def test_universe_guard_held_ticker_never_excluded():
    sched = TradingScheduler.__new__(TradingScheduler)
    sched._ensure_stale_state()
    sched._stale_retry_count["005930"] = 10  # stale > MAX_STALE_RETRIES(=5)
    sched._pending_next_day_clear = set()
    # registry mock — is_ticker_held_by_any("005930") == True
    sched._registry = Mock()
    sched._registry.is_ticker_held_by_any = Mock(return_value=True)
    # registry.all() 도 mock (사전 가드 분기 진입 전 필요시)

    # inquire_ccnl mock — 호출되면 fail
    with patch("src.api.quotation.inquire_ccnl") as mock_inquire:
        await sched._evaluate_universe_guard(["005930"])
        assert "005930" not in sched._universe_excluded_today
        mock_inquire.assert_not_called()  # 사전 가드로 KIS 호출 자체 skip
```

### 카테고리 J — universe guard 익일청산 보호 (**HIGH**, 1 케이스)

`_pending_next_day_clear` 종목 절대 제외 금지.

| # | 테스트 | 검증 |
|---|---|---|
| J-1 | 익일청산 종목 절대 보호 (HIGH) | `_pending_next_day_clear = {("005930", "ltv")}` 시 stale=10 + low_volume 시나리오에서 `_universe_excluded_today` 에 추가 안 됨 + `inquire_ccnl` skip |

**파일**: `tests/unit/engine/test_cycle61_phase2A2_universe_guard_ndc_protection.py`
**패턴**: I-1 답습 + `_pending_next_day_clear` 분기 검증. `registry.is_ticker_held_by_any` 는 False 반환 (보유는 아니지만 익일청산 후보).

### 카테고리 K — delta unsubscribe race 시뮬레이션 (Q6-G1, 1 케이스, best-effort)

`_delta_unsubscribe_dropped` 이 `_scan_loop` + `_board_transition_loop` 동시 발화 시 동일 종목 unsubscribe 충돌 — *발견 시 별개 카드 #11 발의 근거*.

| # | 테스트 | 검증 |
|---|---|---|
| K-1 | race 시뮬레이션 (best-effort) | `asyncio.gather(call_a, call_b)` — `kis_ws_pool.unsubscribe` mock 호출 카운트 == 2 (동일 종목 2회 호출 = 무해) 또는 == 1 (mutex 자동 차단). 회귀 가드 아님 — 현 행위 기록 only |

**파일**: `tests/unit/engine/test_cycle61_phase2A2_delta_unsubscribe_race.py`
**패턴**:
```python
async def test_delta_unsubscribe_race_records_current_behavior():
    """현재 행위 = mutex 없음, 동일 종목 2회 unsubscribe 호출 가능 (KIS 무해)."""
    sched = TradingScheduler.__new__(TradingScheduler)
    # kis_ws_pool mock
    with patch("src.realtime.websocket_pool.kis_ws_pool") as mock_pool:
        mock_pool.get_subscribed_tickers = Mock(return_value={"005930"})
        mock_pool.unsubscribe = AsyncMock()
        # 동시 호출 (race)
        await asyncio.gather(
            sched._delta_unsubscribe_dropped(set()),
            sched._delta_unsubscribe_dropped(set()),
        )
        # 현재 행위 = 2회 호출 (mutex 없음). 별개 카드 #11 발의 근거.
        assert mock_pool.unsubscribe.call_count >= 1
```

**중요**: K-1 은 *행위 기록* 목적. 실제 mutex 도입은 별개 카드 #11 (본 사이클 *밖*).

### 카테고리 L — import sanity (1 케이스)

A2 4 함수 + A2 5 상수 노출 검증.

| # | 테스트 | 검증 |
|---|---|---|
| L-1 | stale_manager 모듈 노출 검증 | `from src.engine import stale_manager` 후 9 함수 + 10 상수 (A1 5 + A2 5) 모두 callable / 정의된 값 |

**파일**: `tests/unit/engine/test_cycle61_phase2A2_import_sanity.py`
**패턴**:
```python
def test_stale_manager_exports_a1_a2_all():
    from src.engine import stale_manager
    # A1 5 함수
    assert callable(stale_manager.build_session_subscription_view)
    assert callable(stale_manager.emit_stale_session_detail)
    assert callable(stale_manager.refresh_stale_ccnl_cache)
    assert callable(stale_manager.evict_expired_ccnl)
    assert callable(stale_manager.prune_force_retry_history)
    # A2 4 함수
    assert callable(stale_manager.detect_silent_inactive_sessions)
    assert callable(stale_manager.force_reconnect_session)
    assert callable(stale_manager.delta_unsubscribe_dropped)
    assert callable(stale_manager.evaluate_universe_guard)
    # A1 5 상수
    assert stale_manager.MAX_STALE_RETRIES == 5
    assert stale_manager.STALE_FORCE_RETRY_AFTER_SECS == 300
    assert stale_manager.STALE_FORCE_RETRY_HOURLY_CAP == 12
    assert stale_manager.UNIVERSE_LOW_VOLUME_THRESHOLD == 10_000
    assert stale_manager.SILENT_INACTIVE_FRESH_RATIO_THRESHOLD == 0.2
    # A2 5 상수
    assert stale_manager.SILENT_INACTIVE_MIN_SUBSCRIBED == 5
    assert stale_manager.SILENT_INACTIVE_PERSIST_SECS == 300.0
    assert stale_manager.SILENT_INACTIVE_RECOVERY_CAP_PER_HOUR == 2
    assert stale_manager.SILENT_INACTIVE_RECOVERY_WINDOW_SECS == 3600.0
    assert stale_manager.STALE_FRESHNESS_SECS == 60
```

---

## 테스트 파일 정리 (12 파일 분리 — 사이클 60 A1 패턴 답습)

| # | 파일 | 카테고리 | 케이스 수 |
|---|---|---|---|
| 1 | `tests/unit/engine/test_cycle61_phase2A2_delegation.py` | A | 4 |
| 2 | `tests/unit/engine/test_cycle61_phase2A2_constants.py` | B | 5 |
| 3 | `tests/unit/engine/test_cycle61_phase2A2_cap_dict_identity.py` | C (HIGH) | 1 |
| 4 | `tests/unit/engine/test_cycle61_phase2A2_dependency_direction.py` | D | 1 |
| 5 | `tests/unit/engine/test_cycle61_phase2A2_reset_daily.py` | E | 1 |
| 6 | `tests/unit/engine/test_cycle61_phase2A2_dataclass_completeness.py` | F | 2 (필드 7종 + reset) |
| 7 | `tests/unit/engine/test_cycle61_phase2A2_silent_inactive_cap.py` | G | 1 |
| 8 | `tests/unit/engine/test_cycle61_phase2A2_silent_inactive_5min.py` | H | 1 |
| 9 | `tests/unit/engine/test_cycle61_phase2A2_universe_guard_held_protection.py` | I (HIGH) | 1 |
| 10 | `tests/unit/engine/test_cycle61_phase2A2_universe_guard_ndc_protection.py` | J (HIGH) | 1 |
| 11 | `tests/unit/engine/test_cycle61_phase2A2_delta_unsubscribe_race.py` | K (best-effort) | 1 |
| 12 | `tests/unit/engine/test_cycle61_phase2A2_import_sanity.py` | L | 1 |
| **합계** | | | **20** (F 카테고리 2 케이스, 나머지 명세 18) |

> **합계 정정**: 설계 카드 18 케이스 → Red 작성 시 F 카테고리 2 케이스 (필드 7종 + reset) 명확 분리 → 총 20 케이스. tdd-engineer 가 조정 가능.

---

## Red 작성 시 주의 사항 (tdd-engineer 인계)

### 1. logger caplog 설정

caplog 사용 가드 케이스 (G-1) 는 반드시:
```python
caplog.set_level(logging.WARNING, logger="src.engine.scheduler")
```
사이클 60 I1 영구 가드 답습 — `__name__` 사용 시 emit 누락 위험.

### 2. mock 시그니처 패턴

```python
from src.engine.scheduler import TradingScheduler
sched = TradingScheduler.__new__(TradingScheduler)  # __init__ skip
sched._ensure_stale_state()  # property graceful init
```
사이클 60 A1 패턴 답습.

### 3. freezegun 사용

`_force_reconnect_session` 의 `time.time()` (L2501) 은 wall clock — `freezegun` 동결 가능.
`_detect_silent_inactive_sessions` 의 `datetime.now(_KST_TZ)` 도 freezegun 동결 가능.

### 4. async 테스트

A-2/A-3/A-4 + G/H/I/J/K = async. `pytest-asyncio` 의 `@pytest.mark.asyncio` 데코레이터 사용.

### 5. 4 함수 의존성 mock 매트릭스

| 함수 | mock 필요 |
|---|---|
| `_detect_silent_inactive_sessions` | `kis_ws_pool.get_session_status()` + `ticker_last_tick` dict |
| `_force_reconnect_session` | `kis_ws._ws` (AsyncMock close) / `kis_ws_pool._quotes[N]._ws` / `write_log` |
| `_delta_unsubscribe_dropped` | `kis_ws_pool.get_subscribed_tickers()` + `kis_ws_pool.unsubscribe` (AsyncMock) + `write_log` |
| `_evaluate_universe_guard` | `registry.is_ticker_held_by_any` + `inquire_ccnl` (AsyncMock) + `kis_ws_pool.unsubscribe` + `write_log` |

### 6. 통과 기준 (Red 완료 시)

- 모든 20 케이스가 ImportError / AttributeError 또는 AssertionError 로 **실패** (Green 미진입 상태)
- A 카테고리 (위임) = `stale_manager.detect_silent_inactive_sessions` 등 *존재 안 함* → ImportError 또는 AttributeError
- B 카테고리 (상수) = `stale_manager.SILENT_INACTIVE_MIN_SUBSCRIBED` 등 *존재 안 함* → AttributeError
- C/E/F/G/H/I/J/K/L = Red 시점 wrapper 변경 0 → 일부 case 는 PASS 가능 (예: F-1 `StaleTrackerState` 필드 검증은 사이클 48 부터 7 필드 → Red 시점 이미 PASS)

> **Red 검증**: tdd-engineer 가 Red 작성 후 `pytest tests/unit/engine/test_cycle61_phase2A2_*.py -v` 실행 → 최소 A/B/D 카테고리 (10 케이스) 가 실패 확인 → Green 발주 가능.

---

## 후속 단계 인계 (Green)

### backend-dev Green 작업 매트릭스

| # | 작업 | 파일 |
|---|---|---|
| G1 | `STALE_FRESHNESS_SECS` 상수 stale_manager.py 이전 + scheduler.py re-export | `src/engine/stale_manager.py` + `src/engine/scheduler.py` |
| G2 | `SILENT_INACTIVE_*` 4 상수 stale_manager.py 이전 + scheduler.py re-export | 동일 |
| G3 | A2 4 함수 stale_manager.py 추가 (self.* → scheduler.* 치환만) | `src/engine/stale_manager.py` |
| G4 | scheduler.py 4 wrapper 추가 (2~3 줄 위임) | `src/engine/scheduler.py` |
| G5 | `_build_session_subscription_view` 의 `STALE_FRESHNESS_SECS` lazy import 제거 (의존성 역전 자연 해소) | `src/engine/stale_manager.py` |
| G6 | 영향 인덱스 갱신 | `python tools/test_impact/build_index.py` |

**행위 변경 0건 의무**: A2 4 함수 본체는 *그대로 복붙* + self → scheduler 치환만. 로직 변경 절대 금지.

### tester Verify 작업 매트릭스 (사이클 60 hotfix 카테고리 분리 측정 패턴)

| # | 작업 | 명령 |
|---|---|---|
| V1 | unit/engine 카테고리 분리 측정 | `pytest tests/unit/engine/ -v --tb=short` |
| V2 | unit/db 카테고리 분리 측정 | `pytest tests/unit/db/ -v --tb=short` |
| V3 | integration 카테고리 분리 측정 | `pytest tests/integration/ -v --tb=short` |
| V4 | contract 카테고리 분리 측정 | `pytest tests/contract/ -v --tb=short` |
| V5 | 사이클 61 신규 가드 단독 측정 | `pytest tests/unit/engine/test_cycle61_phase2A2_*.py -v` |
| V6 | 사이클 60 A1 회귀 가드 측정 | `pytest tests/unit/engine/test_cycle60_phase2A1_*.py -v` |
| V7 | 사이클 28 회귀 가드 측정 (`_stale_last_resubscribe_at`) | `pytest tests/unit/engine/test_scheduler_stale_tracking.py -v` |
| V8 | 사이클 24 회귀 가드 측정 (`_silent_inactive_first_seen`) | `pytest tests/unit/engine/test_session_silent_inactive_ratio.py -v` |
| V9 | 사이클 17/29-R1 회귀 가드 측정 | `pytest tests/unit/engine/test_stale_watcher_thresholds.py -v` |
| V10 | flakiness 차단 (3회 반복 측정) | V5~V9 3회 연속 실행 |
| V11 | CI 시뮬레이션 | `python -m pytest -q` 전체 |

**HIGH 3 케이스 우선 검증**: C-1 (cap dict 동일성) / I-1 (universe guard 보유 보호) / J-1 (universe guard 익일청산 보호).

---

## 사이클 61 종결 후 사이클 62 인계 (Q3 = 가격 필터)

본 사이클 종결 보고 시 동행 작성:
1. `_workspace/cycle62_price_filter_domain_consult.md` — 6 의제 자문 의뢰서
2. `_workspace/cycle62_price_filter_design_card.md` — 1차 sketch

---

## 절대 깨지 말 것 (CLAUDE.md + Red 시점 의무)

- [x] silent inactive 시간당 세션당 2회 cap (KIS LMS/앱키 정지 위험) — C-1 + G-1 가드 2 케이스 이중 보호
- [x] stale universe 가드 보유/익일청산 절대 보호 — I-1 + J-1 가드 2 케이스
- [x] `_reset_daily_state` 동행 reset — E-1 가드 1 케이스 + F-1 dataclass 누락 가드
- [x] KIS "비정상 케이스 2" 차단 (`_delta_unsubscribe_dropped` 행위 보존) — A-3 위임 가드
- [x] WebSocket 4 중 안전망 행위 보존 — 호출자 (`_scan_loop` / `_stale_watcher_loop`) scheduler.py 잔류
- [x] KST 강제 — A2 4 함수 모두 `KST_TZ` lazy import 보존
- [x] logger 명시 binding (사이클 60 I1 영구 가드) — caplog `logger="src.engine.scheduler"` 명시
- [x] 5 상수 `is` 동일성 (re-export) — B-1~B-5 가드 5 케이스
- [x] 의존성 역전 (stale_manager → scheduler) — D-1 정적 검증 가드 + `STALE_FRESHNESS_SECS` lazy import 제거

---

**Red 명세 종료**. tdd-engineer 가 본 명세 기반으로 20 케이스 본체 작성 → Red 검증 (최소 10 케이스 실패) → backend-dev Green 발주.
