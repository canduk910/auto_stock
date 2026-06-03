# 사이클 56 발주서 — DailyEmitCap 통합 + safe_write_log 헬퍼

> **채택 카드**: refactor-review 2026-06-03 메모 카드 #1 (`DailyEmitCap` 통합) + 카드 #5 (`safe_write_log` 헬퍼) — 옵션 A
> **위험 등급**: MEDIUM (#1) + LOW (#5) — domain-expert 자문 *미필요* (refactor-expert 평가 + team-leader 검수 결과)
> **목표**: 3 곳 동형 emit cap 패턴을 `DailyEmitCap` 제네릭으로 단일화 + order_engine.py 14곳 graceful write_log 패턴을 `safe_write_log` 헬퍼로 통일. **행위 보존 절대**.

---

## 1. 결정 사항 (D-1 ~ D-5)

### D-1 사이클 분할 전략 — **D-1-c (5 단계 별 commit) 채택**

| 단계 | 내용 | commit prefix | 의존 |
|---|---|---|---|
| 56-A | `DailyEmitCap` 헬퍼 신규 모듈 + 단위 테스트 (호출처 0) | `feat(engine): DailyEmitCap 헬퍼 도입 (사이클 56-A)` | 독립 |
| 56-B | `SellRejectionTracker._logged_today` 마이그레이션 | `refactor(sell_rejection): _logged_today DailyEmitCap 위임 (사이클 56-B)` | 56-A |
| 56-C | `OrderEngine._nxt_downgrade_logged_today` 마이그레이션 | `refactor(order_engine): NXT 다운그레이드 cap DailyEmitCap 위임 (사이클 56-C)` | 56-A |
| 56-D | `RiskManager._risk_silent_skip_logged_today` 마이그레이션 + `reset_daily()` 캡슐화 | `refactor(risk): silent skip cap DailyEmitCap 위임 + reset_daily 캡슐화 (사이클 56-D)` | 56-A |
| 56-E | `safe_write_log` 헬퍼 추출 + order_engine.py 14곳 통합 | `refactor(engine): safe_write_log 헬퍼 추출 (사이클 56-E)` | 독립 |

**사유**:
- refactor-expert 메모 "*분할 가능*" 명시 + 각 단계가 *변경 1 의도* 원칙 준수
- 56-B/C/D 는 독립 마이그레이션 — 한 단계 회귀 시 해당 단계만 revert 가능 (단일 commit 시 전체 revert)
- 56-E 는 56-A~D 와 무관 — 사이클 51 boot 분해 패턴 답습 (별 commit)
- commit 5개 부담은 회귀 추적 용이성 + 향후 사이클 56-X revert 시 변경 범위 명확화 이득이 큼

**진행 순서**: 56-A → (56-B, 56-C, 56-D 직렬, 한 commit 단위 PASS 검증) → 56-E

### D-2 모듈 위치 — **D-2-b 채택**: `src/engine/daily_emit_cap.py`

- 사이클 48 `stale_tracker.py` / 사이클 51 `boot_manager.py` / 사이클 55 `sell_rejection.py` *형제 모듈* 패턴 답습
- `src/engine/util/` 신규 디렉토리 도입은 *현시점 다른 util 0개* — 과잉 추상화
- `src/util/` 전역 util 은 *engine 전용 emit cap* 의 사용 범위와 불일치
- **확정**: `src/engine/daily_emit_cap.py`

### D-3 `safe_write_log` 위치 — **D-3-a 채택**: `src/db/system_logs.py` 내부 헬퍼

- 기존 `write_log` 와 *동일 모듈*에 위치하는 것이 시그너처/시맨틱 일관성 보존에 유리
- `src/util/logging.py` 신규는 *현재 다른 logging util 0개* — 과잉 추상화
- order_engine.py 내부 헬퍼는 *향후 다른 모듈 재사용 차단* — refactor-expert 메모 카드 #5 "정책 일관성" 효과 무산
- **확정**: `src/db/system_logs.py::safe_write_log` (export)

### D-4 RiskManager `reset_daily()` 캡슐화 — **옵션 1 채택**

`RiskManager.reset_daily_state()` 메서드 신설 + scheduler 위임 호출:

```python
# risk.py
class RiskManager:
    def reset_daily_state(self) -> None:
        """일일 cap state 초기화 — scheduler `_reset_daily_state` 가 위임 호출.

        OrderEngine.reset_daily_state() 와 동일 패턴 (사이클 52 답습).
        """
        self._risk_silent_skip_logged_today.reset()
```

- **사유**:
  - OrderEngine 사이클 52 `reset_daily_state()` 패턴 일관 — RiskManager 만 외부 직접 clear 가 *비대칭*
  - scheduler.py:3833 `self.risk_manager._risk_silent_skip_logged_today.clear()` + `except AttributeError` 가드 → `self.risk_manager.reset_daily_state()` + `except AttributeError` 가드 *유지* (테스트 `__new__` 인스턴스 보호 동일)
  - `RiskManager` 의 다른 상태 (`_tradable_skip_count` / `_regime_block_count`) 는 *1분 주기 emit + dict 폭주* 패턴이라 일일 reset 대상 아님 (현재도 reset 안 함). 본 메서드는 *cap 만* 책임 — 사이클 56+ 추가 cap 필드 시 같은 메서드 내 추가
- **확정**: 옵션 1 + AttributeError 가드 보존

### D-5 domain-expert 자문 — **불필요**

- refactor-expert 카드 #1/#5 모두 *행위 보존* + LOW/MEDIUM 위험 평가 명시
- D-4 옵션 1 채택의 RiskManager `reset_daily_state()` 신설은 *내부 캡슐화* 만 — 외부 동작 (scheduler 호출 시점/주기) 영향 0
- 호환 layer property (`_logged_today` 직접 노출 + AttributeError 가드) 모두 보존 → 회귀 가드 충족
- **확정**: domain-consult 스킬 호출 안 함. team-leader 책임 검수만

---

## 2. tdd-engineer Red 단계 발주

### G-1 `DailyEmitCap` 단위 테스트 (사이클 56-A 사전 작성)

**파일**: `tests/unit/engine/test_daily_emit_cap.py`

| 케이스 | 검증 |
|---|---|
| `test_should_emit_initial_true` | 초기 상태에서 `should_emit(key)` True |
| `test_mark_emitted_blocks_repeat` | `mark_emitted(key)` 후 `should_emit(key)` False |
| `test_mark_emitted_independent_keys` | key A 등록이 key B `should_emit` 에 영향 없음 |
| `test_discard_allows_reemit` | `mark_emitted` → `discard` → `should_emit` True 복원 (sell_rejection 패턴) |
| `test_reset_clears_all` | 다수 key 등록 후 `reset()` → 전체 `should_emit` True 복원 |
| `test_generic_key_str` | `DailyEmitCap[str]` 인스턴스 생성 + str 키 동작 |
| `test_generic_key_tuple` | `DailyEmitCap[tuple[str, str]]` 인스턴스 + 튜플 키 동작 (RiskManager 케이스) |

**총 7 케이스** — refactor-expert 카드 #1 회귀 가드 매트릭스 충족.

### G-2 SellRejectionTracker 호환 layer 회귀 (사이클 56-B)

**파일**: `tests/unit/engine/test_cycle55_sell_rejection_tracker.py` (기존 9 가드 보존) + 신규 1 케이스 추가

| 신규 케이스 | 검증 |
|---|---|
| `test_logged_today_internal_dailyemitcap_migration` | `tracker._logged_today` 가 `set[str]` 동등 인터페이스 (`add` / `discard` / `clear` / `in`) 동작 보존. `should_emit_block_log` / `mark_block_logged` / `register_market_closed` discard 호환 layer 동작 동일 |

**보존 가드**: 사이클 55 R-1 회귀 9 케이스 PASS 의무. **`reset_daily()` 4 필드 일괄 clear** 동일성 유지.

### G-3 OrderEngine `_nxt_downgrade_logged_today` 호환 layer (사이클 56-C)

**파일**: `tests/unit/engine/test_cycle54_nxt_downgrade_cap.py` (기존 4 가드 보존) + 신규 1 케이스

| 신규 케이스 | 검증 |
|---|---|
| `test_nxt_downgrade_cap_internal_dailyemitcap_migration` | `OrderEngine._nxt_downgrade_logged_today` 의 외부 동작 (`ticker in set` 검사 + `add` + `clear`) 동등 인터페이스 유지. `reset_daily_state()` 가 DailyEmitCap `reset()` 위임. 코드 코멘트 "사이클 56 통합 예정" 제거 검증 (정적 검색 1건) |

**보존 가드**: 사이클 54 4 가드 PASS 의무 + ticker별 1회/일 cap 행위 동일성.

### G-4 RiskManager `_risk_silent_skip_logged_today` 호환 layer (사이클 56-D)

**파일**: `tests/unit/engine/test_cycle31_r6_risk_silent_skip.py` (기존 가드 보존) + 신규 2 케이스

| 신규 케이스 | 검증 |
|---|---|
| `test_risk_silent_skip_cap_internal_dailyemitcap_migration` | `(ticker, strategy_id)` 페어 1회/일 cap 행위 동일성. `_risk_silent_skip_logged_today` 외부 인터페이스 (`in` / `add` / `clear`) 보존 |
| `test_risk_manager_reset_daily_state_encapsulation` | `RiskManager.reset_daily_state()` 메서드 호출이 cap reset 효과 동일. scheduler `_reset_daily_state` 가 외부 직접 clear 대신 `reset_daily_state()` 위임 호출. AttributeError 가드 (테스트 `__new__` 인스턴스) 보존 |

**보존 가드**: 사이클 31 R6 회귀 가드 PASS 의무 + 5/21 09:13 VB 미매수 사고 디버깅 케이스 동일성.

### G-5 `safe_write_log` 단위 테스트 (사이클 56-E)

**파일**: `tests/unit/db/test_safe_write_log.py`

| 케이스 | 검증 |
|---|---|
| `test_safe_write_log_normal_writes_through` | 정상 호출 시 `write_log` 위임 + 동일 인자 전달 |
| `test_safe_write_log_swallows_exception` | `write_log` raise (mock) 시 본 흐름 영향 0 (return None) |
| `test_safe_write_log_logs_debug_on_failure` | 실패 시 `logger.debug` 1행 + `debug_key` 포함 + `exc_info=True` |
| `test_safe_write_log_signature_compatibility` | `(level, msg, *, debug_key)` 시그너처 — `await safe_write_log("INFO", "[prefix] ...", debug_key="prefix")` |

**총 4 케이스**.

### Red 단계 진입 준비 상태

- **G-1 (7 케이스)**: 사이클 56-A 시작 *전* 작성 — `src/engine/daily_emit_cap.py` 미존재 상태에서 import 실패 Red
- **G-2/G-3/G-4 (총 4 케이스)**: 사이클 56-B/C/D 각 단계 *전* 작성 — 마이그레이션 미수행 상태에서 내부 구조 검사 Red
- **G-5 (4 케이스)**: 사이클 56-E 시작 *전* 작성 — `safe_write_log` 미존재 import 실패 Red

**총 신규 Red 케이스 수**: 7 + 1 + 1 + 2 + 4 = **15 케이스**

---

## 3. backend-dev Green 단계 인터페이스 명세

### 사이클 56-A: `src/engine/daily_emit_cap.py` 신규 모듈

```python
"""Daily emit cap 헬퍼 — 1회/key/일 로그 emit 정책 단일화.

사이클 56-A (2026-06-03, refactor-review 카드 #1).
3 곳 동형 패턴 통합:
  - RiskManager._risk_silent_skip_logged_today (사이클 31 R6, 페어 키)
  - OrderEngine._nxt_downgrade_logged_today (사이클 54, ticker 키)
  - SellRejectionTracker._logged_today (사이클 55, ticker 키 + discard 재발 허용)

scheduler `_reset_daily_state` 동행 reset 의무 — 호출자 책임.
"""
from dataclasses import dataclass, field
from typing import Generic, Hashable, TypeVar

K = TypeVar("K", bound=Hashable)


@dataclass
class DailyEmitCap(Generic[K]):
    """1회/key/일 emit cap. 만료 후 재발 허용은 discard 으로."""

    _emitted: set[K] = field(default_factory=set)

    def should_emit(self, key: K) -> bool:
        """key 가 아직 emit 안 된 상태면 True. 호출자가 즉시 mark_emitted 호출."""
        return key not in self._emitted

    def mark_emitted(self, key: K) -> None:
        """emit 등록 — 이후 should_emit(key) False."""
        self._emitted.add(key)

    def discard(self, key: K) -> None:
        """만료 후 재발 허용 (sell_rejection register_market_closed 패턴)."""
        self._emitted.discard(key)

    def reset(self) -> None:
        """일일 reset — scheduler `_reset_daily_state` 동행 호출."""
        self._emitted.clear()

    # ──────────── 호환 layer (set 동등 인터페이스 — 호출처 점진적 전환)

    def __contains__(self, key: K) -> bool:
        return key in self._emitted

    def __len__(self) -> int:
        return len(self._emitted)

    def add(self, key: K) -> None:
        """set.add 호환 — 호출처가 should_emit/mark_emitted 미사용 시."""
        self._emitted.add(key)

    def clear(self) -> None:
        """set.clear 호환 — reset() 의 alias."""
        self._emitted.clear()
```

**호환 layer 필수 사유**: 사이클 56-B/C/D 마이그레이션 시 호출처가 `set` 직접 인터페이스 (`in` / `add` / `clear`) 를 사용 중. property 노출 (사이클 55 패턴) + `set` 동등 메서드 둘 다 지원해야 *행위 보존*.

### 사이클 56-B: SellRejectionTracker 마이그레이션

**파일**: `src/engine/sell_rejection.py`

```python
# BEFORE
_logged_today: set[str] = field(default_factory=set)

# AFTER (1 줄 교체)
from src.engine.daily_emit_cap import DailyEmitCap
_logged_today: DailyEmitCap[str] = field(default_factory=DailyEmitCap)
```

- `should_emit_block_log` / `mark_block_logged` / `register_market_closed` (discard 호출) / `reset_daily` 모두 *수정 없음* — DailyEmitCap 의 `set` 호환 layer 가 흡수
- 사이클 17 코드 코멘트 "사이클 56 통합 예정" 제거 (line 17, 74)
- `_market_closed_blocked_logged_today` property (OrderEngine) 가 `self._sell_rejection._logged_today` 반환 — 타입이 `set[str]` → `DailyEmitCap[str]` 으로 변경되나 호출처 (`set` 인터페이스) 동작 동일

### 사이클 56-C: OrderEngine 마이그레이션

**파일**: `src/engine/order_engine.py`

```python
# BEFORE (line 91)
self._nxt_downgrade_logged_today: set[str] = set()

# AFTER
from src.engine.daily_emit_cap import DailyEmitCap
self._nxt_downgrade_logged_today: DailyEmitCap[str] = DailyEmitCap()
```

- 사용처 line 184 (`if ticker not in self._nxt_downgrade_logged_today`) / line 191 (`self._nxt_downgrade_logged_today.add(ticker)`) 모두 *수정 없음* — 호환 layer 흡수
- `reset_daily_state()` 의 `self._nxt_downgrade_logged_today.clear()` *수정 없음* — alias 동작
- 코드 코멘트 line 90 "사이클 56 emit cap 통합 시 tracker 위임 예정" 제거 + line 88-91 주석 갱신 ("사이클 56-C 완료" 명시)

### 사이클 56-D: RiskManager 마이그레이션 + reset_daily_state 캡슐화

**파일**: `src/engine/risk.py`

```python
# BEFORE (line 41)
self._risk_silent_skip_logged_today: set[tuple[str, str]] = set()

# AFTER
from src.engine.daily_emit_cap import DailyEmitCap
self._risk_silent_skip_logged_today: DailyEmitCap[tuple[str, str]] = DailyEmitCap()

# 신규 메서드 (line 41 이후 적절 위치, on_tick 전)
def reset_daily_state(self) -> None:
    """일일 cap state 초기화 — scheduler `_reset_daily_state` 가 위임 호출.

    사이클 56-D (2026-06-03, refactor-review 카드 #1).
    OrderEngine.reset_daily_state() 와 동일 패턴 (사이클 52 답습).
    """
    self._risk_silent_skip_logged_today.reset()
```

- 사용처 line 167 (`if emit_key not in self._risk_silent_skip_logged_today`) / line 168 (`.add`) 모두 *수정 없음*

**파일**: `src/engine/scheduler.py` (line 3830-3836)

```python
# BEFORE
try:
    self.risk_manager._risk_silent_skip_logged_today.clear()
except AttributeError:
    # 회귀 가드 — 사전 init 누락 인스턴스 (테스트 __new__ 등) 보호
    pass

# AFTER
try:
    self.risk_manager.reset_daily_state()
except AttributeError:
    # 회귀 가드 — 사전 init 누락 인스턴스 (테스트 __new__ 등) 보호
    pass
```

- AttributeError 가드 보존 (테스트 호환 의무)
- 외부 직접 clear *비대칭 해소* → OrderEngine/RiskManager 모두 `reset_daily_state()` 위임 패턴 일관

### 사이클 56-E: `safe_write_log` 헬퍼 추출

**파일**: `src/db/system_logs.py` (기존 `write_log` 옆 추가)

```python
async def safe_write_log(level: str, msg: str, *, debug_key: str) -> None:
    """write_log fire-and-forget — 실패 graceful (본 흐름 영향 0).

    사이클 56-E (2026-06-03, refactor-review 카드 #5).
    order_engine.py 14 곳 동형 패턴 통합. 정책 일관성 + 새로운 graceful
    write_log 추가 비용 0.

    Args:
        level: write_log 로그 레벨 (INFO/WARNING/ERROR/CRITICAL)
        msg: 로그 메시지 본문 (prefix 포함)
        debug_key: 실패 시 logger.debug 의 prefix 식별자 (예: "nxt_downgrade")
    """
    try:
        await write_log(level, msg)
    except Exception:
        logger.debug("[%s] write_log 실패", debug_key, exc_info=True)
```

**파일**: `src/engine/order_engine.py` — 14 곳 패턴 통합

| 위치 | BEFORE prefix | AFTER 호출 |
|---|---|---|
| L148-154 | `[stock_master_miss] write_log 실패` | `await safe_write_log("INFO", "...", debug_key="stock_master_miss")` |
| L165-170 | (nxt 관련) | `debug_key="nxt_downgrade_prepare"` 또는 기존 명칭 |
| L186-193 | `[nxt_downgrade] write_log 실패` | `debug_key="nxt_downgrade"` |
| L508-515 | `[market_closed_blocked] write_log 실패` | `debug_key="market_closed_blocked"` |
| L602+646 | (긴 try 블록 내 write_log) | 개별 안전 변환 — 동형 패턴 확인 후 통합 |
| L738-763 | (pending_next_day_clear 등록 실패) | `debug_key="next_day_clear_deferred"` |
| L757-763 | (동형) | `debug_key="next_day_clear_drained_pre"` |
| L794-808 | `[positions_reconciliation] write_log 실패` | `debug_key="positions_reconciliation"` |
| L802-808 | (동형) | (동일 prefix) |
| L820 | (1줄 except) | `debug_key="..."` 식별 후 통합 |
| L1082 / L1119 / L1150 | (잔여 except) | **safe_write_log 대상 아님 가능성** — write_log 외 본 흐름 except 면 *통합 제외* (회귀 위험 차단) |

**주의**: backend-dev 가 L141 / L337 / L473 / L775 / L792 / L828 / L895 / L918 / L1082 / L1119 / L1150 의 `except Exception` 은 *write_log 외 다른 graceful* 인지 1차 확인 후 통합 대상 결정. **14 곳 통합 목표는 카드 #5 메모 추정치** — 실제 통합 가능 곳만 마이그레이션 (refactor-expert 의 *변경 1 의도* 원칙).

---

## 4. tester Verify 단계 검수 항목

### V-1 회귀 무결성 (필수 PASS)

| 영역 | 검증 |
|---|---|
| 사이클 31 R6 회귀 | `_risk_silent_skip_logged_today` cap 1회/페어/일 행위 동일성. `_reset_daily_state` 동행 reset 동일 |
| 사이클 52 B-1 회귀 | `_market_closed_blocked` 진입 차단 + 5분 TTL + emit cap 1회/ticker/일 동일 |
| 사이클 54 회귀 | `_nxt_downgrade_logged_today` 1회/ticker/일 cap + 다운그레이드 결정 무영향 동일 |
| 사이클 55 R-1 회귀 | `SellRejectionTracker.reset_daily()` 4 필드 일괄 clear 동일. 호환 layer property 2개 동일 |
| 백엔드 전체 | `python -m pytest -q` 1748 + 15 = **1763 PASS** 목표 |
| 프론트엔드 | 변경 없음 — 160 PASS 유지 |

### V-2 신규 회귀 가드 (G-1 ~ G-5)

| 가드 | 케이스 수 | 위치 |
|---|---|---|
| G-1 DailyEmitCap 단위 | 7 | `tests/unit/engine/test_daily_emit_cap.py` |
| G-2 SellRejectionTracker 호환 | +1 | `tests/unit/engine/test_cycle55_sell_rejection_tracker.py` |
| G-3 OrderEngine NXT cap 호환 | +1 | `tests/unit/engine/test_cycle54_nxt_downgrade_cap.py` |
| G-4 RiskManager silent skip + reset 캡슐화 | +2 | `tests/unit/engine/test_cycle31_r6_risk_silent_skip.py` |
| G-5 safe_write_log 단위 | 4 | `tests/unit/db/test_safe_write_log.py` |

### V-3 정적 검증

- 코드 코멘트 "사이클 56 통합 예정" 정적 검색 0건 (`sell_rejection.py:17`, `order_engine.py:90`)
- `set[str]` / `set[tuple[str, str]]` 직접 타입 힌트 3곳 제거 확인
- `DailyEmitCap` import 3 곳 (sell_rejection / order_engine / risk)
- `safe_write_log` import 1 곳 (order_engine)
- order_engine.py 의 `except Exception` 카운트 **변화 확인** (14 곳 통합 시 18 → 4 ~ 8 예상)

### V-4 운영 안전 규칙 무회귀 (CLAUDE.md 절대 규칙)

- `_reset_daily_state` 동행 reset 의무: stale_tracker / sell_rejection / order_engine.nxt_cap / risk.silent_skip 4 곳 모두 reset 호출 보존
- NXT 좀비 차단 (`is_market_closed_rejection` + 2단계 TTL) 무회귀
- 매도 거부 4 분류 정책 무회귀
- WebSocket 4 중 안전망 무회귀 (본 사이클 변경 영역 외이나 통합 테스트로 확인)

### V-5 통합 시나리오 (옵션)

trading-test 스킬 위임 시:
1. 모의 잔고 시작 → 1회/일 cap 발화 + scheduler `_reset_daily_state` 후 익일 재 emit 시나리오
2. 사이클 55 R-1 sell 거부 4 분류 시나리오 (KRX 메인 5분 TTL / NXT 익일 09:00 TTL / market_order_disallowed 30초 TTL / insufficient_quantity reconciliation)
3. safe_write_log 실패 simulation (Supabase down) — 본 흐름 (매수/매도/체결통보) 영향 0 검증

---

## 5. 종료 검수 영역 (사이클 56 완료 시)

### 5-A. 코드 (사이클 56-A ~ E 누적)

| 영역 | 변경 |
|---|---|
| 신규 모듈 | `src/engine/daily_emit_cap.py` (+50L 추정) |
| 신규 헬퍼 | `src/db/system_logs.py::safe_write_log` (+15L) |
| 마이그레이션 | `sell_rejection.py` / `order_engine.py` / `risk.py` (각 ±5L) |
| scheduler 캡슐화 | `scheduler.py:3833` 1줄 교체 |
| order_engine 통합 | 14 곳 × 평균 3L → **-42L** 추정 |
| 회귀 가드 | 5 파일 × 평균 30L → **+150L** |

### 5-B. CLAUDE.md 동기화 (4 파일)

| 파일 | 추가 영역 |
|---|---|
| `CLAUDE.md` (루트) | "하네스 변경 이력" 표에 사이클 56 행 추가. 56-A/B/C/D/E 5 commit 명시 + emit cap 통합 + safe_write_log 헬퍼 + 1763 PASS 보고 |
| `src/engine/CLAUDE.md` | (1) 모듈 맵에 `daily_emit_cap.py(DailyEmitCap)` 추가, (2) `risk.py` 섹션에 `reset_daily_state()` 추가, (3) `order_engine.py` 사이클 54 행 갱신 ("사이클 56-C 통합 완료"), (4) `sell_rejection.py` 사이클 55 행 갱신 ("사이클 56-B 통합 완료") |
| `src/db/CLAUDE.md` | `system_logs.py` 섹션에 `safe_write_log(level, msg, *, debug_key)` 추가 |
| `src/CLAUDE.md` | (변경 없음 — 모듈 맵에 신규 daily_emit_cap.py 추가만 검토) |

### 5-C. HARNESS_CHANGELOG 갱신

`docs/HARNESS_CHANGELOG.md` 에 사이클 56 항목 신규:
- 56-A: DailyEmitCap 헬퍼 도입 (7 회귀 가드)
- 56-B: SellRejectionTracker._logged_today 마이그레이션 (1 호환 가드)
- 56-C: OrderEngine._nxt_downgrade_logged_today 마이그레이션 (1 호환 가드)
- 56-D: RiskManager._risk_silent_skip_logged_today 마이그레이션 + reset_daily_state 캡슐화 (2 가드)
- 56-E: safe_write_log 헬퍼 추출 + order_engine.py 14 곳 통합 (4 단위 가드)
- 백엔드 1763 PASS / 프론트 160 PASS / 매매 안전성 무영향

### 5-D. 분석 메모

`_workspace/refactor/2026-06-03_review.md` 에 *후속 추적* 섹션 추가 (사용자 채택 후, 사이클 종료 시 채택 카드 #1/#5 완료 표시 — 본 메모 영구 보존)

### 5-E. 매매 명세 (`_workspace/00_leader_trading_rules.md`)

- **변경 없음** — emit cap 통합은 *행위 보존* 만, 매매 파라미터 변경 0
- 단, 본 명세 끝에 "사이클 56 — emit cap 통합 + safe_write_log 헬퍼 (행위 무영향)" 1줄 기록 검토

---

## 6. 제약 사항 재명시

| 제약 | 적용 |
|---|---|
| 커밋/푸시는 사용자 명시 시 | 모든 56-A ~ E commit + push 는 사용자 명시 후 |
| 행위 보존 절대 | 사이클 31/52/54/55 호환 가드 *전부* PASS 의무 |
| CLAUDE.md 절대 규칙 우선 | `_reset_daily_state` 동행 reset + NXT 좀비 차단 + 매도 거부 정책 무회귀 |
| 운영 시간 회피 | 56-A ~ E 작업은 NXT 애프터 (15:30~) 또는 익일 07:50 _boot 전 push 권장 |
| domain-expert 자문 | **불필요** — refactor-expert 평가 + team-leader 검수 (D-5 확정) |

---

## 7. 진행 흐름 (요약)

```
[현재] team-leader 발주서 완성
   ↓
56-A: tdd-engineer Red (G-1 7 케이스) → backend-dev Green (DailyEmitCap 모듈) → tester PASS → commit
   ↓
56-B: tdd-engineer Red (G-2 +1) → backend-dev Green (SellRejectionTracker 마이그레이션) → tester PASS → commit
   ↓
56-C: tdd-engineer Red (G-3 +1) → backend-dev Green (OrderEngine 마이그레이션) → tester PASS → commit
   ↓
56-D: tdd-engineer Red (G-4 +2) → backend-dev Green (RiskManager 마이그레이션 + reset_daily_state) → tester PASS → commit
   ↓
56-E: tdd-engineer Red (G-5 4 케이스) → backend-dev Green (safe_write_log 추출 + 14 곳 통합) → tester PASS → commit
   ↓
team-leader 종료 검수 (5-A ~ 5-E) → 사용자 보고 → push 승인 대기
```

---

## 8. 미해결 결정 포인트

**없음** — D-1 ~ D-5 모두 team-leader 책임 하 확정. tdd-engineer 진입 준비 완료.

단, **사이클 56-E 의 14 곳 통합 대상 정밀 식별**은 backend-dev 가 Red 진입 *전* `grep -n "except Exception" src/engine/order_engine.py` 결과를 1차 분석하여 *write_log 외 다른 graceful* 분리. 통합 대상이 14 곳 미만이어도 무방 — *변경 1 의도* 우선.
