# 사이클 13-G — start/stop 동시성 race 가드 명세

> 13-F 리뷰 후속. PR #12 (https://github.com/canduk910/auto_stock/pull/12) — Copilot 추가 리뷰 2건 모두 정당.
> 13-E-2 의 `self.*` 속성 승격 (task lifecycle 일원화) 이후 누락된 race 안전성 보완.
> 본 사이클: **race 가드 2건 추가만**. 흐름·생성 위치·정리 순서 변경 금지.

---

## §1 현상

### 1-1. Copilot 리뷰 ① — `scheduler.py:409` manual stop AttributeError race

> `start()`에서 `await self._wait_until(TIME_KRX_MAIN_BUY_STOP)` 동안 외부에서 `/api/trading/stop`로 `stop()`이 호출되면, `stop()`이 `self._scan_task = None`으로 정리한 뒤 여기서 `self._scan_task.cancel()`을 호출하면서 `AttributeError`가 발생할 수 있습니다.

라인 408~409:
```python
await self._wait_until(TIME_KRX_MAIN_BUY_STOP)   # 다년간 대기 (최대 수 시간)
self._scan_task.cancel()                         # 무가드 — race 시 NoneType AttributeError
```

### 1-2. Copilot 리뷰 ② — `scheduler.py:493` await None TypeError race

> 여기서 `await self._ws_task`는 `stop()`이 실행 중인 `start()`를 수동 중지하면서 `_ws_task`를 cancel 후 `None`으로 재대입하는 케이스에서 `TypeError: object NoneType can't be used in 'await' expression`로 터질 수 있습니다.

라인 491~495:
```python
await kis_ws.disconnect()                     # yield point
try:
    await self._ws_task                       # race 시 None await → TypeError
except asyncio.CancelledError:
    pass
```

### 1-3. race 시퀀스 (텍스트 다이어그램)

```
[start() task]                        [/api/trading/stop → stop() task]
─────────────                         ──────────────────────────────
... self._scan_task = create_task()
await self._wait_until(15:20)         ─┐
                                       │  stop() 진입
                                       │  self._running = False
                                       │  for task_attr in (..., "_scan_task", "_ws_task"):
                                       │    task = self._scan_task
                                       │    task.cancel(); await task
                                       │    self._scan_task = None    ←★ None 재대입
                                       │  await unsubscribe_all()
                                       │  await kis_ws.disconnect()
                                       │  ...
                                       │  return  (stop 완료)
self._scan_task.cancel()  ←★★★ AttributeError: 'NoneType' has no attribute 'cancel'
  → except Exception:
    logger.exception("매매 프로세스 오류")
    await write_log("ERROR", "매매 프로세스 비정상 종료")  ←★★★ 운영자 오인
```

동일 패턴이 line 491~493 에서도 발생:
```
await kis_ws.disconnect()  ← yield point ─┐
                                            │  stop() 진입 → _ws_task = None
await self._ws_task  ←★★★ TypeError: object NoneType can't be used in 'await'
  → except CancelledError 가드 통과 못함 (TypeError 별개) → except Exception 로 전파
```

---

## §2 근본 원인

13-E-2 에서 `ws_task` / `scan_task` 를 `self.*` 속성으로 승격하면서 **task lifecycle 통합 정리 루프** (finally line 505~517) 와 `stop()` (line 625~637) 이 동일한 7종 cancel 패턴을 사용하도록 했다. 이는 좀비 task 방지 측면에서 옳지만, **`start()` 본문 자체에서 `self._scan_task` / `self._ws_task` 를 직접 사용하는 4곳 (line 409, 431, 444, 493)** 의 race 안전성을 평가하지 않았다.

`stop()` 은 외부 (`/api/trading/stop` 라우트) 에서 비동기로 호출 가능하며, `start()` 의 `await self._wait_until(...)` (수 시간 대기) / `await kis_ws.disconnect()` (네트워크 IO yield) 가 race window 를 제공한다. 13-E-2 의 통합 cancel 루프는 `setattr(self, task_attr, None)` 으로 끝나므로, race 후 `start()` 가 재개되면 None 참조에 도달한다.

`start()` 본문은 단일 task 컨텍스트에서 작성되었다는 암묵 가정 — 그러나 13-E-2 의 `stop()` 통합 정리로 인해 그 가정이 깨졌다.

---

## §3 트레이딩 안전성 평가

### 3-1. log_analysis 일일 보고서 오염
- AttributeError / TypeError 가 `except Exception:` 으로 전파 → `logger.exception("매매 프로세스 오류")` + `write_log("ERROR", "매매 프로세스 비정상 종료")`.
- 정상 수동 중지였음에도 `system_logs` 에 ERROR 로 기록 → 20:10 `generate_daily_log_report()` 의 `findings` 에 false-positive `severity=high` 항목 생성 → 운영자 오인 + AI 자문 컨텍스트 오염.

### 3-2. 사용자 신뢰성
- 운영자가 `/api/trading/stop` 호출 후 로그에서 "매매 프로세스 비정상 종료" 를 보면, 실제 stop 은 성공했음에도 시스템 결함으로 오인 가능 → 재시작/지원티켓 등 불필요 대응.

### 3-3. 자금 안전 직접 영향 평가
- **line 409 race (AttributeError)**: `_scan_task.cancel()` 직후의 코드는 line 414~ 의 `_force_clear_main_only()` (15:20 KRX 메인 강제 청산). AttributeError 가 `except Exception:` 으로 즉시 전파되어 `_force_clear_main_only()` 가 **skip 됨**. 그러나 `stop()` 자체가 이미 `unsubscribe_all()` + `kis_ws.disconnect()` + `pool.stop()` 을 수행하므로 시세 수신은 정상 종료. 단, **stop() 은 강제 청산을 수행하지 않음** — 사용자가 의도적으로 stop 한 경우 보유 포지션 유지가 정상 동작이므로 자금 안전 영향 0.
- **line 493 race (TypeError)**: `await self._ws_task` 직후의 코드 없음 (try 블록 종단). `finally` 진입 → `kis_ws.disconnect()` 재호출 (idempotent, 13-E-1 보장) + `pool.stop()` 재호출. **이중 정리는 idempotent 보장됨** (13-E + 13-E-1 + 13-E-3 누적 검증). 자금 안전 직접 영향 0.
- **결론**: 자금 안전 직접 영향은 0. 로그 오염 + 운영자 오인이 주된 영향. 단, **PR #12 리뷰 봇이 명시한 race 는 명확한 결함** 이므로 본 사이클에서 차단 의무.

### 3-4. 보조 세션 정리 race 위험 평가
- `stop()` 의 정리 순서: 7종 task cancel → `unsubscribe_all()` → `kis_ws.disconnect()` → `kis_ws_pool.stop()`. `start()` 의 `except Exception:` 진입 → `finally:` 의 동일 순서 정리는 13-E-1 / 13-E-3 가 idempotent 보장. **중복 호출 안전** — 보조 세션 정리 누락 가능성 없음.

---

## §4 fix 명세

### Patch A — `src/engine/scheduler.py:408~409` `_scan_task` race 가드

**Before:**
```python
await self._wait_until(TIME_KRX_MAIN_BUY_STOP)
self._scan_task.cancel()
```

**After:**
```python
await self._wait_until(TIME_KRX_MAIN_BUY_STOP)
# 사이클 13-G — manual stop race 가드. `_wait_until` 는 수 시간 대기 — 그 사이
# /api/trading/stop 가 _scan_task 를 cancel + None 재대입 가능. 무가드 cancel 시
# AttributeError → `except Exception` → ERROR "매매 프로세스 비정상 종료" 오기록.
if self._scan_task is not None and not self._scan_task.done():
    self._scan_task.cancel()
```

가드 패턴은 line 431 / 444 와 동일 (already-safe 두 곳과 일관성).

### Patch B — `src/engine/scheduler.py:491~495` `_ws_task` race 가드

**Before:**
```python
await kis_ws.disconnect()
try:
    await self._ws_task
except asyncio.CancelledError:
    pass
```

**After:**
```python
await kis_ws.disconnect()
# 사이클 13-G — manual stop race 가드. `kis_ws.disconnect()` 는 IO yield —
# 그 사이 /api/trading/stop 가 _ws_task 를 cancel + None 재대입 가능. 무가드
# `await None` 시 TypeError (CancelledError 가드는 포착 못함) → ERROR 오기록.
# 로컬 캡처 후 None 가드 → 안전한 await + CancelledError 흡수.
_ws_task = self._ws_task
if _ws_task is not None:
    try:
        await _ws_task
    except asyncio.CancelledError:
        pass
```

### Patch C — 다른 6곳 무가드 접근 평가 결과

| 라인 | 접근 형태 | race 평가 | 적용 여부 |
|------|----------|----------|----------|
| 247 | `self._ws_task = create_task(...)` 대입 | 단순 대입, race 없음 | **변경 없음** |
| 405 | `self._scan_task = create_task(...)` 대입 | 단순 대입, race 없음 | **변경 없음** |
| 411 | `self._scan_task = None` 대입 (else 분기) | 단순 대입, race 없음 | **변경 없음** |
| 431 | `if self._scan_task is None or self._scan_task.done():` | 이미 `is None` 가드 + 단축평가 | **already safe** |
| 432 | `self._scan_task = create_task(...)` 재대입 | 단순 대입, race 없음 | **변경 없음** |
| 444~445 | `if self._scan_task and not self._scan_task.done(): self._scan_task.cancel()` | 444 와 445 사이 await 없음 (연속 라인) → race window 0 | **already safe** |
| 493 | `await self._ws_task` (무가드) | **race 위험** — Patch B 대상 | **Patch B 적용** |
| 409 | `self._scan_task.cancel()` (무가드) | **race 위험** — Patch A 대상 | **Patch A 적용** |

**결론**: Patch A + B 만 적용. YAGNI 원칙 — race 위험 없는 위치는 변경 금지.

**주의**: line 444~445 는 이미 가드 패턴이 들어가 있으나, 444 의 `not self._scan_task.done()` 평가 시점과 445 의 `.cancel()` 호출 시점 사이에는 yield point 가 없으므로 (단순 메서드 호출 연속 실행) 추가 보강 불필요. 또한 446 라인 `await unsubscribe_all()` 은 `_scan_task` 를 다시 참조하지 않음.

---

## §5 회귀 시나리오 (Red 테스트)

### Test O — `_scan_task` race 가드

#### O-1: `_wait_until` 중 `stop()` 동시 호출 race
- **상황**: `start()` 가 line 408 `await self._wait_until(TIME_KRX_MAIN_BUY_STOP)` 에서 대기.
- **trigger**: `stop()` 진입 → 7종 task cancel 루프에서 `self._scan_task = None` 재대입.
- **검증**: `_wait_until` 즉시 종료 모의 (예: cancel 발생) → line 409 가드 (`if self._scan_task is not None and not self._scan_task.done():`) 가 None 진입 차단 → AttributeError 0건. `except Exception` 미진입 → `system_logs` ERROR "매매 프로세스 비정상 종료" 0건.
- **fixture**: `freeze_time` + asyncio.Event 로 stop 동기화.

#### O-2: 정상 흐름 — `_wait_until` 종료 후 `cancel()` 호출
- **상황**: stop 호출 없이 자연 종료. `_wait_until(15:20)` 종료 시점에 `_scan_task` 는 정상 task.
- **검증**: 가드 통과 (`_scan_task is not None and not done()`) → `.cancel()` 정상 호출 → 기존 동작 보존. `_force_clear_main_only()` 정상 호출.

### Test P — `_ws_task` race 가드

#### P-1: `kis_ws.disconnect()` 중 `stop()` race
- **상황**: `start()` 정상 흐름이 line 491 `await kis_ws.disconnect()` 에서 yield.
- **trigger**: `stop()` 진입 → 7종 task cancel 루프에서 `self._ws_task = None` 재대입 → `kis_ws.disconnect()` 재호출 (idempotent).
- **검증**: line 493 의 로컬 캡처 (`_ws_task = self._ws_task`) 가 None 캡처 → `if _ws_task is not None:` False → await skip. TypeError 0건. `except Exception` 미진입.

#### P-2: 정상 흐름 — `_ws_task` 정상 await
- **상황**: stop 호출 없이 자연 종료. `_ws_task` 는 정상 task.
- **검증**: 로컬 캡처 → `if _ws_task is not None:` True → `await _ws_task` 정상 완료 (CancelledError 흡수). 기존 동작 보존.

### 기존 회귀 가드 (참조만, 신규 테스트 추가 없음)
- 13-E-2 Test J-1 ~ J-5: 7종 task 통합 cancel 루프 정합성.
- 13-E-3 Test L-1 / L-2 / M: `stop()` 의 `_ws_task` / `_scan_task` 포함 + finally idempotency.

---

## §6 안전 가드 (변경 금지 항목)

- 체결통보 (H0STCNI0 / H0STCNI9) 구독/분기/race 가드.
- `_subscriptions` 직접 수정 (kis_ws / kis_ws_pool 캡슐화 위반 금지).
- 메인 disconnect 순서 (kis_ws.disconnect → pool.stop).
- 13-E + 13-E-1 + 13-E-2 + 13-E-3 + 13-F 의 task lifecycle 핵심 로직 — **race 가드 추가만, 흐름 변경 금지**.
- `start()` 의 task 생성 위치 (line 247 / 405 / 411 / 431 / 432 / 444 / 445) — Patch A/B 는 cancel/await 시점의 가드 추가만, 생성 시점 미변경.
- `stop()` 의 7종 task cancel 루프 (line 625~637) — 본 사이클 변경 없음.
- `finally` 정리 루프 (line 505~517) — 본 사이클 변경 없음.

---

## §7 영향 인덱스

- 수정 대상 파일: `src/engine/scheduler.py` (2 hunk: line 408~409, line 491~495).
- 신규 테스트 파일: `tests/test_scheduler_start_stop_race_cycle13g.py` (NEW).
- 영향 없는 모듈: `src/realtime/*` / `src/engine/order_engine.py` / `src/engine/risk.py` / 전략 6종 — race 가드는 scheduler 내부 task lifecycle 한정.
- 영향받는 기존 테스트: `tests/test_scheduler_*cycle13e*` (회귀 검증만, 변경 0). `python tools/test_impact/affected.py` 인덱스 갱신 의무.

---

## §8 작업 분배

### 8-1. tdd-engineer (Red 테스트 작성)

**파일**: `tests/test_scheduler_start_stop_race_cycle13g.py` (NEW)

**분배 메시지 초안**:

> 사이클 13-G Red 테스트 작성 의뢰. 명세: `_workspace/cycle13g_start_stop_race_guard_spec.md` §5.
>
> 4 시나리오 — 모두 `src/engine/scheduler.py` 의 `start()` / `stop()` 동시성 race 가드 검증.
>
> 1. **Test O-1** (`test_scan_task_cancel_guard_during_stop_race`): `start()` 가 `await self._wait_until(TIME_KRX_MAIN_BUY_STOP)` 에서 대기 중일 때 `stop()` 호출 → `_scan_task = None` 재대입 → 재개 시 line 409 AttributeError 0건 + `system_logs` "매매 프로세스 비정상 종료" 0건 검증.
> 2. **Test O-2** (`test_scan_task_cancel_normal_path`): stop 호출 없이 자연 흐름 — line 409 `.cancel()` 정상 호출 + `_force_clear_main_only()` 진입 검증.
> 3. **Test P-1** (`test_ws_task_await_guard_during_stop_race`): `start()` 가 `await kis_ws.disconnect()` 에서 yield 중 `stop()` 호출 → `_ws_task = None` → 재개 시 line 493 TypeError 0건 + ERROR 로그 0건 검증.
> 4. **Test P-2** (`test_ws_task_await_normal_path`): stop 호출 없이 자연 종료 — `await _ws_task` 정상 완료 + CancelledError 흡수 검증.
>
> 공통 fixture:
> - `freeze_time` 으로 시각 제어 (07:50 → 15:20 점프).
> - `asyncio.Event` 로 race 시점 동기화 (start() 의 await 지점에서 stop() trigger).
> - `kis_ws.disconnect` / `kis_ws_pool.stop` mock 으로 graceful idempotent 보장.
> - `write_log` mock 으로 ERROR 호출 0건 assert.
>
> **Red 단계**: 현재 코드 (Patch A/B 적용 전) 에서 O-1 / P-1 만 fail, O-2 / P-2 는 pass 가 정상. 4개 모두 pass 면 race 가드 효과 미검증 의심 → 시나리오 재설계.
>
> **금지**: scheduler.py 구현부 수정 금지. 명세 §6 안전 가드 위반 금지.

### 8-2. backend-dev (Green 구현)

**파일**: `src/engine/scheduler.py` (line 408~409, line 491~495 2 hunk).

**분배 메시지 초안**:

> 사이클 13-G Green 구현 의뢰. 명세: `_workspace/cycle13g_start_stop_race_guard_spec.md` §4.
>
> tdd-engineer 의 Red 테스트 (`tests/test_scheduler_start_stop_race_cycle13g.py`) O-1 / P-1 을 통과시킨다. O-2 / P-2 는 회귀 가드 — 깨지면 안 됨.
>
> **Patch A** (line 408~409): `self._scan_task.cancel()` 무가드 호출 → `if self._scan_task is not None and not self._scan_task.done(): self._scan_task.cancel()` 로 가드.
>
> **Patch B** (line 491~495): `await self._ws_task` 무가드 → 로컬 변수 캡처 + None 가드:
> ```python
> _ws_task = self._ws_task
> if _ws_task is not None:
>     try:
>         await _ws_task
>     except asyncio.CancelledError:
>         pass
> ```
>
> **금지**: §6 안전 가드 — 13-E ~ 13-F 핵심 로직 변경 금지, task 생성 위치 변경 금지, stop() / finally 정리 루프 변경 금지. Patch C 후보 6곳 (line 247/405/411/431-432/444-445) **변경 금지** — 이미 race-safe (§4 표 참조).
>
> 완료 시 `pytest tests/test_scheduler_start_stop_race_cycle13g.py -v` 4건 pass + 회귀 인덱스 (`tools/test_impact/affected.py`) 영향 테스트 전부 pass.

### 8-3. tester (검수)

**분배 메시지 초안**:

> 사이클 13-G 검수. 명세: `_workspace/cycle13g_start_stop_race_guard_spec.md` §9.
>
> 검수 범위:
> 1. Patch A/B 가 §4 명세대로 정확히 적용되었는지 (라인 위치 + 가드 패턴).
> 2. Patch C 후보 6곳 (247/405/411/431-432/444-445) 변경 없음 확인.
> 3. Red 테스트 4건 (O-1, O-2, P-1, P-2) 모두 pass.
> 4. 기존 13-E-2 Test J-1~J-5 + 13-E-3 Test L-1/L-2/M 회귀 0건.
> 5. 전체 backend pytest 실행 — 신규 회귀 0건.
> 6. `system_logs` 에 "매매 프로세스 비정상 종료" / "매매 프로세스 오류" 가 race 시나리오에서 발생하지 않는지 mock 검증.
> 7. 자금 안전 영향 평가 (§3-3) — Patch 적용 후 stop 동작 (보유 포지션 유지) 정상.
>
> 검수 실패 시 backend-dev 재작업 지시. 검수 통과 시 PR #12 자동 머지 가능 라벨.

---

## §9 검수 체크리스트

1. **Patch A 적용 확인**: line 408 직후 `if self._scan_task is not None and not self._scan_task.done():` 가드 진입 + line 409 의 `.cancel()` 가 가드 블록 내부로 이동.
2. **Patch B 적용 확인**: line 491 `await kis_ws.disconnect()` 직후 `_ws_task = self._ws_task` 로컬 캡처 + `if _ws_task is not None:` 가드 + `try/except CancelledError` 보존.
3. **Patch C 미적용 확인**: line 247/405/411/431-432/444-445 모두 13-F 동일 상태 (diff 0).
4. **Red 테스트 4건 pass**: O-1 race AttributeError 0건 / O-2 정상 cancel / P-1 race TypeError 0건 / P-2 정상 await.
5. **회귀 0건**: 13-E-2 (J-1~5) + 13-E-3 (L-1/L-2/M) + 13-F 기존 테스트 전체 pass. `system_logs` 에 race 시나리오 ERROR 0건.
