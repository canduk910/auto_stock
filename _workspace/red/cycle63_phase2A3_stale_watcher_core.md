# Red 명세 — 사이클 63 Phase 2-A3 K stale watcher 핵심 추출

> **작성**: 2026-06-05 (Fri) 17:25 KST · team-leader
> **위험 등급**: **HIGH** (K stale watcher 본체, 영구 hot path 360 회/일, KIS LMS/앱키 정지 chain 직접)
> **Red 산출 대상**: `tests/unit/engine/test_cycle63_phase2A3_stale_watcher_core.py` (단일 파일, 25 케이스)
> **답습 기반**: 사이클 60 Red (240줄, 17 케이스) + 사이클 61 Red (498줄, 18~20 케이스) + 사이클 62 Red (204줄, 가격 필터)
> **확정 근거**: `_workspace/cycle63_phase2A3_design_card.md` v2 + `_workspace/cycle63_phase2A3_domain_response.md` (Q1~Q5-3 채택)

---

## 1. 추출 대상 코드 재확인

| 함수 | scheduler.py 위치 | 라인 수 | stale_manager 신규 함수명 |
|------|-------------------|---------|--------------------------|
| `_check_and_resubscribe_stale` | L2442~L2663 | 222L | `check_and_resubscribe_stale(scheduler) -> None` (async) |
| `_resubscribe_stale_priority` | L2690~L2789 | 100L | `resubscribe_stale_priority(scheduler, cap=10) -> list[str]` (async) |

scheduler.py 후 wrapper (4 줄 × 2 함수):

```python
async def _check_and_resubscribe_stale(self) -> None:
    """K stale watcher 본체 — 사이클 63 Phase 2-A3 stale_manager 위임."""
    from src.engine import stale_manager
    await stale_manager.check_and_resubscribe_stale(self)

async def _resubscribe_stale_priority(self, cap: int = 10) -> list[str]:
    """`_scan_loop` 5분 stale 우선순위 재구독 — 사이클 63 Phase 2-A3 stale_manager 위임."""
    from src.engine import stale_manager
    return await stale_manager.resubscribe_stale_priority(self, cap=cap)
```

---

## 2. 회귀 가드 25 케이스 명세 (카테고리별)

> **HIGH 케이스 18 건 = tdd-engineer Red 단계 *전수 우선* 작성 의무** (사이클 60/61 답습)
> **freezegun 의무**: 카테고리 H (4건) + J (2건) = **6건**
> **caplog 의무**: 카테고리 L (1건) + H 일부 (force_retry WARNING) = **2~3건**

### 카테고리 A — 위임 wrapper 검증 (4 케이스, HIGH 1)

| 번호 | 케이스 명 | 위험 | 검증 |
|------|----------|------|------|
| A-1 | `_check_and_resubscribe_stale` wrapper 호출 시 `stale_manager.check_and_resubscribe_stale(self)` 1회 호출 | MED | `unittest.mock.patch("src.engine.stale_manager.check_and_resubscribe_stale")` → wrapper 호출 후 `mock.assert_called_once_with(scheduler)` |
| A-2 | `_resubscribe_stale_priority` wrapper 호출 시 `stale_manager.resubscribe_stale_priority(self, cap=10)` 1회 호출 | MED | cap=5 / cap=10 / default 3 변형 모두 `cap=` kwarg 통과 |
| A-3 | wrapper 가 `await` 정상 + return 값 (list[str]) 전달 보존 | MED | `mock.return_value = ["005930", "000660"]` → wrapper return 동일 list |
| **A-4** | `check_and_resubscribe_stale` 함수 내부에서 `stale_manager.emit_stale_session_detail(scheduler, ...)` **직접 호출** (Q4 채택 = CONSIDER B, wrapper 미경유) | **HIGH** | `patch("src.engine.stale_manager.emit_stale_session_detail")` + stale_tickers 비공집합 fixture → 1회 호출 (`scheduler._emit_stale_session_detail` mock 은 미호출 검증) |

### 카테고리 B — 상수 재export 동일성 (0 케이스, A1+A2 기존 케이스 유지)

A3 추가 상수 0. 사이클 60 A1 (3 상수) + 사이클 61 A2 (5 상수) = 누적 8 상수 회귀 가드 *그대로 보존*. 본 사이클 신규 케이스 없음.

### 카테고리 C — property `is` 동일성 (3 케이스, HIGH 2)

A3 가 3 dict 외부 `getattr` (`src/routes/realtime.py:88-91`) 접근 동일성 보장 필수:

| 번호 | 케이스 명 | 위험 |
|------|----------|------|
| **C-1** | `scheduler._stale_retry_count` setter 경유 갱신 시 stale_manager 함수가 받은 `scheduler` 인자의 동일 dict 접근 (`is` 동일성) | **HIGH** |
| **C-2** | `scheduler._stale_last_resubscribe_at` setter 경유 갱신 시 동일성 | **HIGH** |
| C-3 | `scheduler._stale_force_retry_history` setter 경유 갱신 시 동일성 | MED |

검증:
```python
sched._stale_retry_count = {}  # setter
sched_dict_id = id(sched._stale_retry_count)
await stale_manager.check_and_resubscribe_stale(sched)
# 함수 내부에서 sched._stale_retry_count.clear() 호출 후
assert id(sched._stale_retry_count) == sched_dict_id  # 동일 dict
```

### 카테고리 D — AST 정적 의존성 역전 가드 (2 케이스, HIGH 1)

| 번호 | 케이스 명 | 위험 |
|------|----------|------|
| **D-1** | stale_manager.py 가 `from src.engine.scheduler import ...` 정적 import 0 (사이클 60 답습) | **HIGH** |
| D-2 | stale_manager.py 가 `import src.engine.scheduler as _sched_mod` 직접 import 0 — `sys.modules.get("src.engine.scheduler")` 패턴만 허용 (사이클 61 답습) | MED |

검증:
```python
import ast
with open("src/engine/stale_manager.py") as f:
    tree = ast.parse(f.read())
for node in ast.walk(tree):
    if isinstance(node, ast.ImportFrom) and node.module == "src.engine.scheduler":
        pytest.fail(f"D-1 violation: from src.engine.scheduler import {node.names}")
    if isinstance(node, ast.Import):
        for alias in node.names:
            if alias.name == "src.engine.scheduler":
                pytest.fail(f"D-2 violation: import src.engine.scheduler")
```

### 카테고리 E — `_reset_daily_state` 동행 reset (2 케이스, HIGH 1)

A3 추가 dict 필드 0 → 사이클 60 G-1 + 사이클 61 E-1 기존 케이스 보존 검증만:

| 번호 | 케이스 명 | 위험 |
|------|----------|------|
| **E-1** | `_reset_daily_state()` 호출 후 `_stale_retry_count` / `_stale_last_resubscribe_at` / `_stale_force_retry_history` 3 dict 모두 비어있음 | **HIGH** |
| E-2 | `_reset_daily_state()` 호출 직후 `check_and_resubscribe_stale` 발화 → 모든 stale 종목 `retry=1` 부터 시작 (이전 카운터 잔류 0 확인) | MED |

### 카테고리 F — dataclass 7 필드 누락 가드 (사이클 48) (2 케이스, HIGH 1)

A3 가 `_stale_state` 추가 필드 0 (현재 추가 0) → 사이클 48 dataclass 자동 가드 케이스 보존만:

| 번호 | 케이스 명 | 위험 |
|------|----------|------|
| **F-1** | `_stale_state` dataclass 7 필드 (`retry_count` / `last_resubscribe_at` / `force_retry_history` / ...) 모두 reset_daily 동행 | **HIGH** |
| F-2 | A3 후 dataclass 필드 누락 없음 (정적 검증 — `dataclasses.fields()` 7 필드 확인) | MED |

### 카테고리 G — 1~5회 즉시 강제 재등록 (KIS 정상 패턴) (3 케이스, HIGH 3)

사이클 17 KIS 공식 답변 반영 — 1~5회 모두 `unsubscribe + sleep(50ms) + subscribe` 패턴:

| 번호 | 케이스 명 | 위험 |
|------|----------|------|
| **G-1** | retry=1 첫 stale → `kis_ws_pool.unsubscribe_in_pool(TICK_TR_ID, ticker)` + `asyncio.sleep(0.05)` + `kis_ws_pool.subscribe(TICK_TR_ID, ticker, priority=..., bypass_limit=...)` 호출 순서 + 카운트 | **HIGH** |
| **G-2** | retry=3 중간 stale → 동일 분기 (force_retry 미진입 검증, `_stale_retry_count` setter 경유 갱신) | **HIGH** |
| **G-3** | retry=5 마지막 분기 (`retry == MAX_STALE_RETRIES`, 강제 재등록 분기로 진입 = `retry > MAX_STALE_RETRIES` 분기 *아님*) | **HIGH** |

검증 (G-1 예시):
```python
mock_pool = AsyncMock()
with patch("src.engine.stale_manager.kis_ws_pool", mock_pool):
    sched._stale_retry_count = {}
    ticker_last_tick["005930"] = datetime.now(_KST_TZ) - timedelta(seconds=120)
    # subscribed = {"005930"}
    mock_pool.get_subscribed_tickers.return_value = {"005930"}
    await stale_manager.check_and_resubscribe_stale(sched)
    # 005930 → high_tickers (positions) → HIGH+bypass=True
    mock_pool.unsubscribe_in_pool.assert_called_once_with(TICK_TR_ID, "005930")
    mock_pool.subscribe.assert_called_once_with(
        TICK_TR_ID, "005930", priority="HIGH", bypass_limit=True
    )
    assert sched._stale_retry_count["005930"] == 1
```

### 카테고리 H — 6회 초과 시간 기반 force_retry (사이클 29-R1) (4 케이스, HIGH 4, freezegun 4)

사이클 29 005935 사고 영역 핵심 — 회귀 시 8 분 영구 잔류 손실 chain 재발:

| 번호 | 케이스 명 | 위험 |
|------|----------|------|
| **H-1** | `_stale_last_resubscribe_at` 부재 (None) 시 즉시 1회 발화 (age=infinity) | **HIGH** |
| **H-2** | retry=7, age=600s (>=300s) → 강제 재시도 발화 + `_stale_retry_count[ticker] = 0` 리셋 + `_stale_last_resubscribe_at[ticker] = now` 갱신 + history.append | **HIGH** |
| **H-3** | retry=7, age=120s (<300s) → cooldown 미경과 skip + `skipped_giveup += 1` 카운트 | **HIGH** |
| **H-4** | retry=7, age=600s, history 12건 (시간당 cap 도달) → `[stale_force_retry_cap]` WARNING + skip + `force_retry_cap_blocked += 1` | **HIGH** |

검증 (H-2 freezegun 예시):
```python
from freezegun import freeze_time
with freeze_time("2026-05-21 13:00:00", tz_offset=9):
    sched._stale_retry_count = {"005935": 7}
    sched._stale_last_resubscribe_at = {"005935": datetime(2026, 5, 21, 12, 50, tzinfo=_KST_TZ)}  # 10분 전
    sched._stale_force_retry_history = {"005935": []}  # cap 0
    mock_pool.get_subscribed_tickers.return_value = {"005935"}
    ticker_last_tick["005935"] = datetime(2026, 5, 21, 12, 58, tzinfo=_KST_TZ)  # 2분 전 stale
    await stale_manager.check_and_resubscribe_stale(sched)
    assert sched._stale_retry_count["005935"] == 0  # 리셋 검증 (사이클 29-R1)
    assert len(sched._stale_force_retry_history["005935"]) == 1  # history append
    # [stale_force_retry] INFO 로그 검증
    assert "[stale_force_retry] ticker=005935 retries=7 last_resub_age=600s" in caplog.text
```

검증 (H-4 caplog 예시):
```python
with freeze_time("2026-05-21 14:00:00", tz_offset=9):
    sched._stale_force_retry_history = {"005935": [
        datetime(2026, 5, 21, 13, 0 + i, tzinfo=_KST_TZ) for i in range(12)
    ]}
    # 12건 모두 60분 윈도우 내
    ...
    await stale_manager.check_and_resubscribe_stale(sched)
    assert "[stale_force_retry_cap] ticker=005935 attempts_in_hour=12" in caplog.text
    mock_pool.subscribe.assert_not_called()  # skip
```

### 카테고리 I — 우선순위 분리 HIGH/LOW (사이클 29-R3) (3 케이스, HIGH 3)

| 번호 | 케이스 명 | 위험 |
|------|----------|------|
| **I-1** | `positions` 소속 ticker → HIGH+bypass=True (보유 종목 메인 절대 보장) | **HIGH** |
| **I-2** | `_pending_next_day_clear` 소속 ticker → HIGH+bypass=True (익일청산 보장) | **HIGH** |
| **I-3** | 그 외 후보 → LOW+bypass=False (보조 세션 분산) | **HIGH** |

검증 (I-2 예시):
```python
sched._pending_next_day_clear = {("005935", "long_tail_volatility")}
# 005935 = positions 미보유 + _pending_next_day_clear 만 소속
mock_pool.get_subscribed_tickers.return_value = {"005935"}
ticker_last_tick["005935"] = datetime.now(_KST_TZ) - timedelta(seconds=120)
await stale_manager.check_and_resubscribe_stale(sched)
mock_pool.subscribe.assert_called_once_with(
    TICK_TR_ID, "005935", priority="HIGH", bypass_limit=True
)
```

### 카테고리 J — force_retry history 60분 슬라이딩 윈도우 (2 케이스, HIGH 1, freezegun 2)

| 번호 | 케이스 명 | 위험 |
|------|----------|------|
| **J-1** | history append 후 60분 경과한 entry evict (`history[:] = [t for t in history if t > hour_ago]`) | **HIGH** |
| J-2 | cap 12 비교 정확성 (60분 윈도우 내 정확히 11 → 1 추가 가능 / 정확히 12 → skip) | MED |

### 카테고리 K — `_scan_loop` 5분 cap=10 결정성 (2 케이스, MED 2)

| 번호 | 케이스 명 | 위험 | 비고 |
|------|----------|------|------|
| K-1 | stale 30 종목 중 cap=10 만 재구독 + `sorted()` 결정적 순서 보장 | MED | **Q5-3 결함 가능성 영역** — Green 단계 backend-dev 정독 의무 |
| K-2 | stale 종목 0건 시 `return []` 즉시 종료 (빈 리스트) | MED | |

### 카테고리 L — caplog logger 명시 binding (사이클 60 I1) (1 케이스, HIGH 1)

| 번호 | 케이스 명 | 위험 |
|------|----------|------|
| **L-1** | `caplog.set_level(logging.INFO, logger="src.engine.scheduler")` 로 `[stale_watcher]` / `[stale_priority_resubscribe]` / `[stale_force_retry]` / `[stale_force_retry_cap]` 4 prefix 로그 캡처 가능 | **HIGH** |

검증:
```python
caplog.set_level(logging.INFO, logger="src.engine.scheduler")
await stale_manager.check_and_resubscribe_stale(sched)
assert any("[stale_watcher]" in r.message for r in caplog.records)
assert any(r.name == "src.engine.scheduler" for r in caplog.records)
# stale_manager 가 잘못된 logger 사용 시 (예: getLogger(__name__))
# r.name == "src.engine.stale_manager" 로 분리 → 테스트 실패
```

### 카테고리 M — import sanity (1 케이스)

| 번호 | 케이스 명 | 위험 |
|------|----------|------|
| M-1 | `from src.engine import stale_manager as sm` + `assert callable(sm.check_and_resubscribe_stale)` + `assert asyncio.iscoroutinefunction(sm.check_and_resubscribe_stale)` + 동일하게 `resubscribe_stale_priority` | LOW |

---

## 3. 카테고리별 합계 + HIGH 비중

| 카테고리 | 케이스 수 | HIGH 비중 |
|----------|-----------|-----------|
| A 위임 | 4 | 1 |
| B 상수 | 0 | 0 |
| C property is | 3 | 2 |
| D AST 가드 | 2 | 1 |
| E reset_daily | 2 | 1 |
| F dataclass | 2 | 1 |
| **G 1~5회 강제 재등록** | **3** | **3** |
| **H 6회 초과 force_retry** | **4** | **4** |
| **I 우선순위 분리** | **3** | **3** |
| J history 60분 윈도우 | 2 | 1 |
| K 5분 cap=10 | 2 | 0 |
| L caplog | 1 | 1 |
| M import sanity | 1 | 0 |
| **합계** | **25** | **18** (HIGH 비중 72%) |

### HIGH 18 케이스 우선 작성 순서 (tdd-engineer 의무)

```
1. G-1 (retry=1 즉시 강제 재등록, KIS 정상 패턴)
2. G-2 (retry=3 중간)
3. G-3 (retry=5 마지막)
4. I-1 (positions HIGH+bypass=True)
5. I-2 (next_day_clear HIGH+bypass=True)
6. I-3 (그 외 후보 LOW+bypass=False)
7. H-1 (force_retry 첫 진입, last_at=None)
8. H-2 (force_retry age>=300s 발화 + 카운터 리셋)
9. H-3 (force_retry age<300s skip)
10. H-4 (시간당 cap 12 WARNING) — caplog 의무
11. A-4 (emit_stale_session_detail 직접 호출, Q4=B)
12. C-1 (_stale_retry_count is 동일성)
13. C-2 (_stale_last_resubscribe_at is 동일성)
14. D-1 (AST 정적 import 가드)
15. E-1 (reset_daily 3 dict 비어있음)
16. F-1 (_stale_state 7 필드 reset 동행)
17. J-1 (history 60분 evict)
18. L-1 (caplog logger=src.engine.scheduler)
```

---

## 4. Red 작성 시 주의 사항 (tdd-engineer 인계)

### 4.1 logger caplog 설정

모든 caplog 테스트는 `caplog.set_level(logging.INFO, logger="src.engine.scheduler")` 명시. `caplog.set_level(logging.INFO)` (logger 미지정) 시 stale_manager 가 잘못된 logger 사용 시 발견 못함.

### 4.2 mock 시그니처 패턴 (사이클 61 답습)

`kis_ws_pool` patch 는 **stale_manager 네임스페이스**:
```python
with patch("src.engine.stale_manager.kis_ws_pool", mock_pool):  # OK
# 또는
with patch("src.engine.scanner.ticker_last_tick", {...}):  # OK
```

`patch("src.engine.scheduler.kis_ws_pool", ...)` 금지 — wrapper 만 호출되고 stale_manager 내부 import 는 우회 못함.

### 4.3 freezegun 사용

```python
from freezegun import freeze_time
@freeze_time("2026-05-21 13:00:00", tz_offset=9)
async def test_H_2_force_retry_after_300s():
    ...
```

`tz_offset=9` 명시 의무 (KST). 미명시 시 `_KST_TZ` aware datetime 과 naive datetime 비교 결함.

### 4.4 async 테스트

```python
import pytest
@pytest.mark.asyncio
async def test_G_1_first_stale_immediate_reregister():
    ...
```

### 4.5 fixture 패턴 (사이클 60/61 답습)

```python
@pytest.fixture
def sched():
    """`__new__` 호출로 init 우회 + 필요한 dict 만 setter 경유 set"""
    from src.engine.scheduler import TradingScheduler
    s = TradingScheduler.__new__(TradingScheduler)
    s._stale_retry_count = {}
    s._stale_last_resubscribe_at = {}
    s._stale_force_retry_history = {}
    s._pending_next_day_clear = set()
    # registry mock — F1, I1, I3 케이스용
    s.registry = MagicMock()
    s.registry.all.return_value = []  # 기본: positions 없음
    return s
```

### 4.6 통과 기준 (Red 완료 시)

- 25 케이스 모두 작성 → **모두 fail** (Green 단계 stale_manager 함수 미구현이므로)
- AST 가드 D-1 / D-2 는 현재 stale_manager.py 에 신규 함수 없으므로 **PASS** (정적 import 0 유지)
- `python -m pytest tests/unit/engine/test_cycle63_phase2A3_stale_watcher_core.py --collect-only` 25 케이스 collect 확인
- caplog 테스트 (L-1, H-4) 가 임포트 오류 없이 collect 됨 확인

---

## 5. 후속 단계 인계

### 5.1 backend-dev Green 작업 매트릭스

| 작업 | 파일 | 라인 변화 |
|------|------|-----------|
| stale_manager.py 본체 추가 — `check_and_resubscribe_stale` | `src/engine/stale_manager.py` | +222L |
| stale_manager.py 본체 추가 — `resubscribe_stale_priority` | `src/engine/stale_manager.py` | +100L |
| scheduler.py wrapper 작성 — `_check_and_resubscribe_stale` (4 줄) | `src/engine/scheduler.py` | -218L (222→4) |
| scheduler.py wrapper 작성 — `_resubscribe_stale_priority` (4 줄) | `src/engine/scheduler.py` | -96L (100→4) |
| **net 변화** | | scheduler.py ~−315L, stale_manager.py +~322L |

**Green 의무 추가 사항**:
1. **Q4=B 직접 호출**: `check_and_resubscribe_stale` 내부 마지막 `stale_manager.emit_stale_session_detail(scheduler, stale_tickers, now)` 직접 호출 (A-4 케이스 통과 의무)
2. **Q5-3 cap=10 결함 확인 의무**: `resubscribe_stale_priority` L2748 `targets = stale_tickers[:cap]` 코드 정독 + 결함 재현 시뮬 → 결함 확인 시 사이클 64+ 카드 #5 별도 발의 보고 / 결함 부재 시 verify 보고서 명시
3. **logger 명시 binding**: stale_manager.py 상단 `logger = logging.getLogger("src.engine.scheduler")` 확인 (사이클 60 I1)
4. **`sys.modules.get()` 패턴**: `kis_ws_pool` / `scanner.ticker_last_tick` / `datetime.now()` 접근 시 scheduler 네임스페이스 우선 (사이클 61)
5. **기존 9 테스트 파일 sanity**: Green 직후 `pytest tests/unit/engine/test_stale_watcher*.py tests/unit/engine/test_scan_loop_stale_priority.py tests/integration/test_stale_watcher*.py -x` 1 회 PASS 의무

### 5.2 tester Verify 작업 매트릭스 (사이클 60 hotfix 카테고리 분리 측정 패턴)

| 카테고리 | 측정 항목 |
|----------|-----------|
| 백엔드 전체 PASS | 1882 → 1907 목표 (+25 신규) |
| 4 카테고리 분리 측정 | (a) 신규 25 케이스 PASS / (b) 기존 9 stale 테스트 PASS / (c) 전체 회귀 PASS / (d) HIGH 18 케이스 단독 PASS |
| flakiness 3 회 반복 | `pytest tests/unit/engine/test_cycle63_phase2A3_stale_watcher_core.py --count=3` (pytest-repeat) → flake 0 |
| HIGH 케이스 전수 우선 | 18 케이스 단독 PASS 보고 분리 |
| **V12 (백엔드 only)** | 프론트엔드 무관 — `cd frontend && npm test` 생략 |
| **V13 매도 영향 0** | stale watcher = 시세 영역, 매도 영역 무관. `risk.execute_sell` / `order_engine` 변경 0 확인 |
| **카테고리 P (사이클 60 답습)** | property `is` 동일성 (C-1, C-2, C-3) 단독 검증 분리 보고 |

### 5.3 sync-docs 작업 매트릭스

| 파일 | 추가 내용 |
|------|----------|
| `src/engine/CLAUDE.md` | 모듈 맵 갱신 (stale_manager 9 → 11 함수) + 본문 사이클 63 행 |
| `src/engine/stale_manager.py` 헤더 | 사이클 63 행 (Q4=B 직접 호출 명시) |
| 루트 `CLAUDE.md` | 사이클 63 행 (PASS 카운트 갱신, scheduler.py 3320 → ~3,005L) |
| `docs/HARNESS_CHANGELOG.md` | **Q4=B 직접 호출 = *사이클 60 답습하지 않음* 명시 의무** (선택 근거 동봉) |
| `_workspace/refactor/2026-06-04_review.md` | 카드 #2 A3 완료 표시 + **카드 #14 (Q5-2) 신규 발의** + 카드 #5 (Q5-3 결함 확인 시) 조건부 발의 |

---

## 6. 사이클 64+ 인계 (Q5-2 + Q5-3)

### Q5-2 — stale_manager.py sub-module 분해 (카드 #14)

본 사이클 종료 후 발의. 청사진 = 4 sub-module:
- `stale_diagnostics.py` (~350L)
- `stale_session_recovery.py` (~250L)
- `stale_universe_guard.py` (~150L)
- `stale_watcher_core.py` (~322L)

### Q5-3 — cap=10 결함 시정 (카드 #5, 조건부)

backend-dev Green 결함 확인 시 발의. 시정 제안:
```python
high_stale = [t for t in stale_tickers if t in high_tickers]
low_stale = [t for t in stale_tickers if t not in high_tickers]
targets = high_stale + low_stale[:max(0, cap - len(high_stale))]
```

---

## 7. 절대 깨지 말 것 (CLAUDE.md + Red 시점 의무)

1. **WebSocket 4 중 안전망 보존** — A3 = K stale watcher + 5분 우선, 본체 행위 100% 보존
2. **K stale watcher 우선순위 분리 보존** (사이클 29-R3) — I 3 케이스 전수 검증
3. **stale watcher force_retry 보존** (사이클 29-R1) — G 3 + H 4 = 7 케이스 전수 검증
4. **silent inactive 시간당 cap 2회 (사이클 29-R2)** — A2 이주 완료, A3 영향 0
5. **stale universe 가드 (사이클 32)** — A2 이주 완료, A3 영향 0
6. **`_reset_daily_state` 동행 reset** — E 2 케이스 보존 (A3 추가 0)
7. **logger 명시 binding** — L 1 케이스
8. **사이클 38 매도 영역 무관** — stale watcher = 시세 영역, `risk.on_tick` 매도 분기 무영향
9. **금요일 NXT 애프터 push 금지** — 주말 push 의무 (별도 브랜치 `cycle63/phase2A3/stale-watcher-core`)
10. **월요일 09:00 1h 운영 환경 verify 의무** — 시나리오 A/B/C 3 종

---

> **다음 단계**: 사용자 보고 → tdd-engineer Red 발주 진행 지시 대기.
