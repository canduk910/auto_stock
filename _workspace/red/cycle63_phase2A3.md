# 사이클 63 Phase 2-A3 Red 명세 — K stale watcher 핵심 추출

> **작성**: 2026-06-05 (Fri) 17:30 KST · tdd-engineer
> **선행 문서**:
> - 설계 카드 v2: `_workspace/cycle63_phase2A3_design_card.md`
> - domain 응답: `_workspace/cycle63_phase2A3_domain_response.md` (Q1~Q4 RECOMMEND / Q4=B 직접 호출 채택 / Q5-3 cap=10 결함 확인 의무)
> - domain 의뢰: `_workspace/cycle63_phase2A3_domain_consult.md`
> **위험 등급**: **HIGH** — K stale watcher 핵심, 영구 hot path 360 회/일, 사이클 29 005935 사고 chain 직접 영역
> **선례 답습**: 사이클 60 A1 / 사이클 61 A2 패턴 (logger binding + sys.modules.get + freezegun + AsyncMock + dataclass guard)

---

## §1. grep 결과 (Red 단계 사전 검증)

### 1.1 추출 대상 2 함수 라인 실측

| 함수 | 위치 | 라인 수 | 명세 일치 |
|------|------|---------|----------|
| `_check_and_resubscribe_stale` | scheduler.py L2442~L2663 | **222L** | ✓ |
| `_resubscribe_stale_priority` | scheduler.py L2690~L2789 | **100L** | ✓ |
| 합계 | — | **322L** | ✓ 설계 카드 일치 |

### 1.2 함수 호출처 (Red 단계 외부 호출 가드)

```
grep "_check_and_resubscribe_stale" src/
  scheduler.py:2387 (주석)
  scheduler.py:2397 await self._check_and_resubscribe_stale()  ← 유일 호출처 (_stale_watcher_loop)
  scheduler.py:2442 async def _check_and_resubscribe_stale(self) -> None:
  stale_tracker.py:43 (주석)

grep "_resubscribe_stale_priority" src/
  scheduler.py:1978 await self._resubscribe_stale_priority(cap=10)  ← 유일 호출처 (_scan_loop)
  scheduler.py:1980 (예외 로그)
  scheduler.py:2690 async def _resubscribe_stale_priority(self, cap: int = 10):
```

→ **외부 호출처 0건** (스케줄러 내부 1+1=2건만). A wrapper 위임 후 외부 인터페이스 영향 0.

### 1.3 property 7 쌍 외부 접근 grep (C 카테고리 가드)

```
grep "_stale_retry_count\|_stale_last_resubscribe_at\|_stale_force_retry_history" src/
(scheduler / stale_manager / stale_tracker 제외)
  /src/routes/realtime.py:88  stale_retry_count = getattr(trading_scheduler, "_stale_retry_count", {}) or {}
  /src/routes/realtime.py:89  stale_last_resubscribe_at = getattr(trading_scheduler, "_stale_last_resubscribe_at", {}) or {}
```

→ 외부 접근 = `src/routes/realtime.py` 2 라인 (사이클 60/61 동일). A3 추가 영역 0.

### 1.4 sys.modules.get 패턴 grep (Q4=B 직접 호출 + D-1 AST 가드)

```
grep "sys.modules.get" src/engine/stale_manager.py
  L395  _sched_mod = sys.modules.get("src.engine.scheduler")  (detect_silent_inactive_sessions)
  L473  _sched_mod = sys.modules.get("src.engine.scheduler")  (force_reconnect_session)
```

→ 사이클 61 A2 도입 패턴. A3 2 함수도 동일 패턴 적용 의무 (`kis_ws_pool` / `datetime.now()` / `scanner` 접근 시).

### 1.5 emit_stale_session_detail 호출처 (Q4=B 직접 호출 검증)

```
src/engine/scheduler.py:2662  self._emit_stale_session_detail(stale_tickers, now)  ← A3 이주 후 변경 대상
src/engine/scheduler.py:2678  def _emit_stale_session_detail(...)  ← wrapper 보존 (외부 호환)
src/engine/scheduler.py:2683  stale_manager.emit_stale_session_detail(self, stale_tickers, now)
src/engine/stale_manager.py:154 def emit_stale_session_detail(scheduler: Any, ...)  ← 직접 호출 대상
```

→ Q4=B 채택 후 A3 본체 L2662 `self._emit_stale_session_detail(...)` → `emit_stale_session_detail(scheduler, ...)` 직접 호출 (1 hop 단축).

---

## §2. 25 케이스 카테고리 분류

| Cat | 파일 | 케이스 | 검증 | 위험 |
|-----|------|--------|------|------|
| A | `test_cycle63_phase2A3_delegation.py` | A-1: `_check_and_resubscribe_stale` wrapper → stale_manager 단일 호출 | wrapper assert_awaited_once_with(sched) | HIGH |
|   |   | A-2: `_resubscribe_stale_priority` wrapper → stale_manager 단일 호출 (cap=10) | wrapper assert_awaited_once_with(sched, cap=10) | LOW |
|   |   | A-3: `_resubscribe_stale_priority(cap=5)` wrapper → cap 인자 그대로 전달 | wrapper assert_awaited_once_with(sched, cap=5) | LOW |
|   |   | A-4: `_emit_stale_session_detail` wrapper 보존 (외부 호환) | scheduler 메서드 호출 시 stale_manager 동일 함수 호출 (사이클 60 A1 보존) | LOW |
| C | `test_cycle63_phase2A3_property_compat.py` | C-1: `_stale_retry_count` 외부 `getattr` 호환 (routes/realtime.py:88) | getattr fallback 정상 | LOW |
|   |   | C-2: `_stale_last_resubscribe_at` 외부 `getattr` 호환 (routes/realtime.py:89) | getattr fallback 정상 | LOW |
|   |   | C-3: 3 dict `is` 동일성 — wrapper 위임 후 동일 객체 갱신 보장 | scheduler._stale_state.retry_count IS scheduler._stale_retry_count | LOW |
| D | `test_cycle63_phase2A3_dependency_direction.py` | D-1: stale_manager.py 가 scheduler 정적 import 0건 (AST) | `from src.engine import scheduler` 금지 | LOW |
|   |   | D-2: A3 2 함수가 `sys.modules.get("src.engine.scheduler")` 패턴 사용 (AST) | AST `Attribute` 검색 | LOW |
| E | `test_cycle63_phase2A3_reset_daily.py` | E-1: `_reset_daily_state()` 후 A3 영향 3 dict 모두 빈 dict (`_stale_state.reset_daily()` 위임) | dict empty 검증 | MEDIUM |
|   |   | E-2: `_reset_daily_state()` 후 `_stale_force_retry_history` 빈 dict (사이클 29-R1 60분 슬라이딩 cap 리셋) | history dict empty | MEDIUM |
| F | `test_cycle63_phase2A3_dataclass_completeness.py` | F-1: `StaleTrackerState` 7 필드 정확 일치 보존 (A3 추가 필드 0) | dataclasses.fields() 비교 | MEDIUM |
|   |   | F-2: reset_daily() 호출 후 7 필드 모두 empty (auto-detect 회귀 가드) | for f in fields: empty 검증 | MEDIUM |
| **G** | `test_cycle63_phase2A3_force_resubscribe.py` | **G-1: 첫 stale (retry=1) → 즉시 unsubscribe + 50ms sleep + subscribe (KIS 정상 패턴, 사이클 17 보강)** | mock pool.unsubscribe_in_pool + subscribe 호출 검증 | **HIGH** |
|   |   | **G-2: retry=5 (마지막 1~5회 분기) → 동일 강제 재등록 분기 통과** | 5회까지 동일 호출 | **HIGH** |
|   |   | **G-3: 강제 재등록 직후 `_stale_last_resubscribe_at[ticker]` 갱신** (사이클 28) | 호출 후 dict 갱신 검증 | **HIGH** |
| **H** | `test_cycle63_phase2A3_force_retry.py` | **H-1: `_stale_last_resubscribe_at` 부재 시 즉시 1회 force_retry (age=inf 분기, 영구 stale 첫 진입)** | freezegun + retry=6 + 부재 | **HIGH** |
|   |   | **H-2: age >= 300s 시 force_retry 발화 + `_stale_retry_count[ticker] = 0` 카운터 리셋 (T+17min 시점)** | freezegun + 300s 경과 + 리셋 검증 | **HIGH** |
|   |   | **H-3: age < 300s 시 skip (cooldown 미경과, T+13min 시점)** | freezegun + 120s/240s 경과 + unsubscribe 호출 0건 | **HIGH** |
|   |   | **H-4: 시간당 12회 cap 초과 시 `[stale_force_retry_cap]` WARNING + skip (KIS LMS 차단)** | history 12건 누적 + cap 도달 + WARNING 로그 | **HIGH** |
| **I** | `test_cycle63_phase2A3_priority_split.py` | **I-1: positions 소속 stale → HIGH + bypass_limit=True (사이클 29-R3 메인 절대 보장)** | subscribe(priority='HIGH', bypass_limit=True) | **HIGH** |
|   |   | **I-2: `_pending_next_day_clear` 소속 stale → HIGH + bypass_limit=True (익일청산 보장)** | 동일 검증 | **HIGH** |
|   |   | **I-3: 그 외 후보 stale → LOW + bypass_limit=False (보조 라운드로빈 분산)** | subscribe(priority='LOW', bypass_limit=False) | **HIGH** |
| J | `test_cycle63_phase2A3_history_window.py` | J-1: history 60분 슬라이딩 윈도우 evict (60분 이전 항목 제거) | freezegun + 50/70분 entry + 70분 evict | MEDIUM |
|   |   | J-2: cap=12 정확 도달 시 WARNING + skip (=12 vs >12 경계 검증) | history 12건 정확 cap | MEDIUM |
| K | `test_cycle63_phase2A3_priority_cap.py` | K-1: stale 30 종목 중 cap=10 만 재구독 + sorted 결정성 (`stale_tickers[:cap]` L2748) | 30 stale → 10 호출 | MEDIUM |
|   |   | **K-2: Q5-3 cap=10 결함 가능성 — HIGH 종목이 sorted "0..." 우선 후 cap 밖 잘림 시나리오 (현재 결함 영속)** | HIGH 005935 + LOW 30 종목 → 005935 cap 밖 검증 (현재 결함 confirm) | MEDIUM |
| L | `test_cycle63_phase2A3_logger_binding.py` | L-1: stale_manager.logger 가 "src.engine.scheduler" 로 binding (사이클 60 I1 영속) | logger.name 검증 | LOW |
| M | `test_cycle63_phase2A3_import_sanity.py` | M-1: A3 2 함수 노출 + async coroutine (callable + iscoroutinefunction) | hasattr + iscoroutinefunction | LOW |

**합계**: **29 케이스 / 12 파일** (A 4 + C 3 + D 2 + E 2 + F 2 + G 3 + H 4 + I 3 + J 2 + K 2 + L 1 + M 1).

> **명세 카운팅 정정** (2026-06-05 17:50 KST): 설계 카드 v2 + 의뢰서의 "25 케이스" 텍스트는 산술 오류 (실제 합계 29). 카테고리별 분배 (4+3+2+2+2+3+4+3+2+2+1+1=29) 는 변경 없음. tester verify 보고서의 PASS 카운트도 +29 로 갱신 의무.

HIGH 케이스 = **10** (G 3 + H 4 + I 3). A 카테고리 A-1 도 wrapper 위임 검증으로 HIGH 가능 — 그러나 사이클 60/61 답습 패턴이므로 LOW-MEDIUM 분류.

---

## §3. mock 패턴 표

| 영역 | mock 방식 | 사용 사이클 |
|------|----------|-----------|
| `kis_ws_pool.subscribe / unsubscribe_in_pool / get_subscribed_tickers` | `patch("src.engine.scheduler.kis_ws_pool")` (사이클 61 패턴) | A / G / H / I / K |
| `src.engine.scanner.ticker_last_tick` | `patch("src.engine.scanner.ticker_last_tick", new={...})` | G / H / I / J / K |
| `src.db.system_logs.write_log` | `patch("src.engine.stale_manager.write_log", new=AsyncMock())` 또는 import 후 monkey-patch | H / I (WARNING 검증 시) |
| `stale_manager.<func>` 위임 | `patch.object(stale_manager, "<func>", new=AsyncMock(return_value=...))` (사이클 61 A1 답습) | A |
| `registry.all()` (positions) | `patch.object(sched, "registry", MagicMock(all=lambda: [...]))` | I |
| `_pending_next_day_clear` | 직접 set 주입 (`sched._pending_next_day_clear = {("005930", "vb"), ...}`) | I-2 |
| 시간 통제 | `freeze_time(base)` + `datetime.now(_KST_TZ)` mock | H / J |

---

## §4. freezegun 사용 위치 (의무)

| Cat | 케이스 | 검증 시간 시나리오 |
|-----|--------|------------------|
| H-1 | _stale_last_resubscribe_at 부재 즉시 발화 | 단일 시점 (now=base) — age=inf 검증 |
| H-2 | age >= 300s force_retry + 카운터 리셋 | base + 300s 이후 last_at 등록 → now=base+301s |
| H-3 | age < 300s skip | last_at = now-120s / now-240s 두 분기 |
| H-4 | 시간당 12회 cap 초과 WARNING | history 12건 누적 (모두 60분 이내) → 13회 차단 |
| J-1 | history 60분 슬라이딩 evict | 50분 전 / 70분 전 entry → 70분 evict |
| J-2 | cap=12 정확 도달 경계 | 12건 정확 vs 11건 (PASS vs WARNING) |

**6 케이스 freezegun 의무**. 모든 케이스에 `from freezegun import freeze_time` import + `with freeze_time(base):` 블록.

---

## §5. 회귀 가드 매트릭스 (CLAUDE.md 절대 규칙 6 종 매핑)

| 절대 규칙 (CLAUDE.md) | 보호 케이스 |
|----------------------|------------|
| 1. **WebSocket 4 중 안전망** (F1 + scan_loop + K + 5분 우선) | A-1 / A-2 / G-1 / G-2 / H-* / I-* / K-1 |
| 2. **K stale watcher 우선순위 분리 HIGH+bypass / LOW+bypass=False** (사이클 29-R3) | I-1 / I-2 / I-3 (3 케이스 전수) |
| 3. **stale watcher force_retry** (사이클 29-R1: 1~5회 즉시 + 6회 초과 5분 cooldown + 시간당 12회 cap) | G-1/2/3 (1~5회) + H-1/2/3/4 (6회 초과) |
| 4. **silent inactive 시간당 세션당 2회 cap** (사이클 29-R2) | A2 (사이클 61) 영역, A3 영향 0 — F-1/F-2 dataclass 7 필드 보존만 |
| 5. **stale universe 가드** (사이클 32, 보유/익일청산 보호) | A2 (사이클 61) 영역, A3 영향 0 — F-1/F-2 보존만 |
| 6. **`_reset_daily_state` 동행 reset** (사이클 60 G-1 + 사이클 61 E-1) | E-1 / E-2 (A3 영향 3 dict 검증) |

→ HIGH 6 케이스 (G/H/I) 가 *전수* 규칙 2/3 영역 (K stale watcher 핵심) 보호.

---

## §6. 통과 기준

| 단계 | 기준 |
|------|------|
| Red (현재) | **29 케이스 중 19 FAIL / 10 PASS** — A3 함수 미존재로 19 FAIL (A 3 + D 1 + G 3 + H 4 + I 3 + J 2 + K 2 + M 1) + 사이클 60/61 영속 회귀 가드 10 PASS (A-4 + C 3 + D-1 + E 2 + F 2 + L 1) |
| Green (backend-dev) | 29 케이스 모두 PASS — A3 2 함수 stale_manager 이주 + scheduler wrapper 2 줄 위임 + Q4=B 직접 호출 |
| Tester verify | 백엔드 2082 → 2111 PASS (+29). 4 카테고리 분리 측정 (HIGH/MEDIUM/LOW/A) + flakiness 3 회 반복 |
| 1h verify | 시나리오 A/B/C 전수 (월요일 09:00~10:00) |

**Red 단계 FAIL 예측**:
- A-1/A-2/A-3: AttributeError (`stale_manager.check_and_resubscribe_stale` 미존재) — A-4 는 사이클 60 보존 검증으로 PASS 가능
- D-1: 현재 stale_manager.py 가 scheduler 정적 import 0건 (A2 lazy import 청산 완료) — Red 시점 PASS 가능
- D-2: A3 2 함수 미이주 상태 → `sys.modules.get` 호출 grep 0건 → 함수 자체 부재로 케이스 skip 또는 FAIL
- E-1/E-2: 정상 인스턴스 동작 검증 — 사이클 60/61 영속 → PASS 가능
- F-1/F-2: 사이클 60 보존 → PASS 가능 (회귀 가드)
- G/H/I: wrapper 위임 후 stale_manager 본체 호출 검증 → 현재 미이주 → AttributeError FAIL
- J/K: 사이클 60/61 영속 영역 호출 시 PASS 가능 vs A3 함수 호출 시 FAIL
- L-1: 사이클 60 영속 PASS
- M-1: AttributeError FAIL (함수 미존재)

→ **예상 FAIL 카테고리**: A (3), D-2 (1 — skip 또는 FAIL), G (3), H (4), I (3), J (2), K (2), M (1) = **약 18~19 FAIL 예측**. 잔여 ~6 PASS 는 사이클 60/61 영속 회귀 가드.

---

## §7. Q3 시나리오 A/B/C 사전 명세 (tester 1h verify 인계)

**시간**: 2026-06-09 (월) 09:00~10:00 KST. tester 직접 모니터링.

### 시나리오 A — 자연 monitoring (의무)

- 09:00:05 첫 K stale watcher 사이클: `[stale_watcher] subscribed=N stale=0` 정상
- 09:30 `_scan_loop` 첫 발화 후: `[stale_priority_resubscribe] count=N tickers=[...]` 정상
- 10:00 K stale watcher ~30 사이클 (120s × 30 = 60분): stale 발생 시 `[stale_watcher_detail]` 짝 정합
- 보유 종목 stale 시: HIGH+bypass=True 메인 재등록 검증
- stale 6회 초과 시: `[stale_force_retry]` + `_stale_retry_count[ticker]` 0 리셋

### 시나리오 B — 인위 stale 주입 (선택, 자연 발생 0 건 시)

- 격리 조건: 보유 0 + 익일청산 0 + 모든 전략 후보 0
- 주입: `ticker_last_tick[test_ticker] = datetime.now(_KST_TZ) - timedelta(seconds=120)`
- 검증: 다음 K stale watcher 사이클 `force_reregistered=1` 로그
- 회복: ~10초 내 정상 시세 + `ticker_last_tick[test_ticker]` 갱신

### 시나리오 C — KIS LMS chain 사전 차단 (자동 monitoring)

- `[stale_force_retry_cap] ticker=... attempts_in_hour=12` WARNING 0 건 기대
- 발화 시: 즉시 사용자 보고 → 다음 작업 차단
- 1h 종료 후: `[ws_heartbeat]` 5분 통계 + `[tick_coverage_session]` 정상 + KIS LMS/앱키 정지 0 확인

---

## §8. Q5-3 cap=10 결함 확인 영역 (backend-dev Green 시점)

**의심 위치**: `_resubscribe_stale_priority` L2748 (이주 후 동일 위치):

```python
targets = stale_tickers[:cap]  # cap=10 적용
```

→ `stale_tickers` = `sorted(...)` 결정성 보장, **priority 분리 *전*** cap 적용. stale 30 종목 중 sorted "000xxx" 우선 LOW 후보 10건이 cap 채우면 HIGH 005935 cap 밖.

**backend-dev Green 단계 의무**:
1. L2748 (이주 후 동일 위치) 코드 정독 + K-2 케이스 결함 재현 확인
2. **결함 확인 시**: 사이클 64+ 카드 #5 별도 발의 (`_workspace/refactor/2026-06-04_review.md`)
3. **결함 부재 시**: tester verify 보고서에 sorted 순서 cap=10 정상 작동 명시 + 카드 skip

**시정 안 (사이클 64+ 카드 #5 채택 시)**:
```python
high_stale = [t for t in stale_tickers if t in high_tickers]
low_stale = [t for t in stale_tickers if t not in high_tickers]
targets = high_stale + low_stale[:max(0, cap - len(high_stale))]
```

K-2 케이스는 *현재 결함 confirm* 형태로 작성 (현재 코드가 HIGH 005935 cap 밖으로 잘림 = PASS = 결함 confirm).

---

## §9. backend-dev Green 발주 명세

1. **stale_manager.py 신규 2 함수 이주**:
   - `async def check_and_resubscribe_stale(scheduler: Any) -> None` — L2442~L2663 본체 그대로 + `self.*` → `scheduler.*` 치환 + `sys.modules.get("src.engine.scheduler")` 패턴 (`kis_ws_pool` / `datetime.now()` / `scanner` 접근 시)
   - `async def resubscribe_stale_priority(scheduler: Any, cap: int = 10) -> list[str]` — L2690~L2789 본체 그대로 + 동일 치환
2. **Q4=B 직접 호출 패턴 적용**: 본체 L2662 `self._emit_stale_session_detail(...)` → `emit_stale_session_detail(scheduler, ...)` 직접 호출 (lazy import 빚 청산)
3. **scheduler.py wrapper 2 줄 × 2 함수**:
   ```python
   async def _check_and_resubscribe_stale(self) -> None:
       from src.engine import stale_manager
       await stale_manager.check_and_resubscribe_stale(self)

   async def _resubscribe_stale_priority(self, cap: int = 10) -> list[str]:
       from src.engine import stale_manager
       return await stale_manager.resubscribe_stale_priority(self, cap=cap)
   ```
4. **Q5-3 cap=10 결함 확인 의무**: K-2 케이스 통과 후 결함 재현 확인 → 사용자 보고
5. **영향 인덱스 갱신**: `python tools/test_impact/build_index.py` 재실행 (사이클 60/61 답습)
6. **선행 회귀 가드 1회 실행 의무**: `pytest tests/unit/engine/test_stale_watcher*.py tests/integration/test_stale_watcher*.py -x` (기존 9 테스트 파일 patch 경로 깨짐 사전 확인)

---

## §10. 산출물 파일 목록

| 파일 | 케이스 수 | 작성 완료 |
|------|---------|----------|
| `tests/unit/engine/test_cycle63_phase2A3_delegation.py` | 4 | ✓ |
| `tests/unit/engine/test_cycle63_phase2A3_property_compat.py` | 3 | ✓ |
| `tests/unit/engine/test_cycle63_phase2A3_dependency_direction.py` | 2 | ✓ |
| `tests/unit/engine/test_cycle63_phase2A3_reset_daily.py` | 2 | ✓ |
| `tests/unit/engine/test_cycle63_phase2A3_dataclass_completeness.py` | 2 | ✓ |
| `tests/unit/engine/test_cycle63_phase2A3_force_resubscribe.py` | 3 | ✓ |
| `tests/unit/engine/test_cycle63_phase2A3_force_retry.py` | 4 | ✓ |
| `tests/unit/engine/test_cycle63_phase2A3_priority_split.py` | 3 | ✓ |
| `tests/unit/engine/test_cycle63_phase2A3_history_window.py` | 2 | ✓ |
| `tests/unit/engine/test_cycle63_phase2A3_priority_cap.py` | 2 | ✓ |
| `tests/unit/engine/test_cycle63_phase2A3_logger_binding.py` | 1 | ✓ |
| `tests/unit/engine/test_cycle63_phase2A3_import_sanity.py` | 1 | ✓ |
| **합계** | **29 케이스 / 12 파일** | — |
