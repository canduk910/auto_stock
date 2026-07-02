# 사이클 188 Red 작업 지시서 — `_wait_until(advance_if_passed=True)` never-return 회귀 시정

승인 계획: `~/.claude/plans/188-bubbly-spring.md` (2026-07-02 사용자 승인)

## 결함 (사이클 160 회귀, 2026-06-17 도입 — 2주 지속)

`src/engine/scheduler.py:3960~3977` `_wait_until(target, *, advance_if_passed=True)` 모드에 **return 경로가 없다**:
- 60초 단위 sleep 루프가 매 iteration "오늘의 target"을 재계산
- target 도달 순간 `now >= target` → `target_dt += 1일`로 밀고 **return 없이 계속 sleep**
- 자정 지나면 다시 "오늘 target" 대기 → 도달하면 또 `+1일` → 영원히 반복
- 유일한 탈출 = `self._running = False`

결과: `task_loop_helper.py:114` (`run_periodic_task_loop` while 루프, production 유일 advance 호출처) 가 영원히 대기 → **모든 정기 task(16:00 일봉/16:10 basics/16:15 purge/16:20 저녁 funnel/16:30 master/20:00:05 universe) 정기 시각 발화 0회**. 매일 아침 boot 의 `immediate_first_run` 만 발화 (운영 실측: 7/1 정기 발화 0 + funnel is_provisional 스냅샷 전부 아침 07:59 생성).

## 기존 스위트가 못 잡은 이유 (Explore 전수 판정)

cycle160 ADVANCE-1 / cycle152 PAST-1 등 기존 advance 케이스는 전부 **고정 clock**(MockDT.now 고정값) + fake sleep 안에서 `_running=False` 강제 탈출 → "return 여부"를 단언한 적 없음. **기존 테스트 깨짐 0건 / xfail 의미 전환 0건** — 신규 파일이 갭을 전담.

## 시정 목표 동작 (Green 계약)

```
호출 시점에 target_dt 1회 확정:
  now < target  → 오늘 target
  now >= target → default 모드: 즉시 return (사이클 160 보존)
                  advance 모드: 내일 동일 시각으로 +1일 (사이클 152 폭주 차단 보존)
이후 while self._running 루프:
  now >= 확정 target_dt → return (사이클 188 신규 — 발화)
  아니면 asyncio.sleep(min(잔여초, 60))
_running=False → 발화 없이 return (헬퍼가 `if not scheduler._running: break` 흡수)
```

- naive `datetime.now()` 유지 (컨테이너 TZ=Asia/Seoul, default 경로 일관)
- 시그니처 불변: `_wait_until(self, target: time, *, advance_if_passed: bool = False)`
- **cycle152 AST 가드 호환**: `if now >= target: break` 패턴 금지 — `return` + `target_dt += timedelta(days=1)` 형태 의무

## Red 테스트 — 신규 `tests/unit/engine/test_cycle188_wait_until_advance_return.py` (7케이스)

mock 방식: **가상 시계 단조 전진** — `_MockDT.now()` 가 mutable 상태를 반환하고, fake `asyncio.sleep(secs)` 가 가상 시계를 `secs` 만큼 전진. `patch("src.engine.scheduler.datetime", _MockDT)` (naive datetime 반환, 기존 cycle160/152 파일과 동일 patch 경로). 무한 루프 안전망: fake sleep 호출 횟수 상한(예: 5,000회) 초과 시 `_running=False` + `pytest.fail`.

| 케이스 | 등급 | 시나리오 | 단언 |
|--------|------|---------|------|
| G-188-1 | HIGH | advance, now=10:00, target=16:00 | 당일 16:00 도달 시 **return** (현재 코드 = 무한 advance → FAIL) |
| G-188-2 | HIGH | advance, now=18:00, target=16:30 | 익일 16:30 도달 시 return + **도달 전(당일) return 없음** (152 폭주 차단 보존) |
| G-188-3 | HIGH | G-188-1/2 return 시점 검증 | return 시 가상 시각이 확정 target 이상 + 초과 ≤ 60s (재-advance 로 밀리지 않음) |
| G-188-4 | MED | default, now=16:00, target=15:20 | 즉시 return + sleep 0회 (사이클 160 BREAK 보존) |
| G-188-5 | MED | default, now=10:00, target=15:20 | 15:20 도달 시 return (원설계 보존) |
| G-188-6 | MED | advance, 대기 중 `_running=False` | 발화(target 도달) 없이 return |
| G-188-7 | HIGH | 통합: `run_periodic_task_loop`(immediate_first_run=False, wait_time=16:00) + **실제 `_wait_until`** + 가상 시계 | `once_callable` 호출 ≥1 (정기 발화 end-to-end — 현재 코드 = 0회 → FAIL). 1회 발화 확인 후 `_running=False` 종료 |

주의:
- G-188-7 은 scheduler 인스턴스가 아닌 `_SchedulerLike` 호환 경량 객체 또는 `TradingScheduler()` 인스턴스 사용 — 실제 `_wait_until` 본체가 반드시 실행돼야 함 (mock 금지). record_fn/flush_fn = no-op, summary_log_format 최소.
- 기존 파일(cycle160/152/134/158) **수정 금지** — 전부 PASS 유지 (Explore 판정).
- freezegun 사용 금지 (사이클 187 교훈: freeze 된 monotonic + asyncio sleep = hang). MockDT + fake sleep 로 자체 가상 시계.

## Red 유효성 기준

현재 production 코드에서 G-188-1/2(당일/익일 발화)/3/7 **FAIL**, G-188-4/5/6 PASS(보존 불변식) 허용.

## Green 범위

`src/engine/scheduler.py::_wait_until` 1함수 재구성만. `task_loop_helper.py` 변경 0. docstring 에 사이클 188 회귀 시정 내역 추가 (사이클 160/152 계약 보존 명시).

## 검증 (메인 세션)

1. cycle188 격리 7 PASS × 2회 flakiness 0
2. 인접: cycle160(7) + cycle152(3) + cycle134 + cycle158 + cycle106 전부 PASS
3. engine 광역 회귀 0
4. 매매 안전성 8영역 diff 0 (`git diff -- src/engine/risk.py src/engine/order_engine.py src/realtime/ src/auth/ src/api/order.py src/engine/session.py src/engine/scanner.py src/engine/strategy_registry.py`)
5. Red 유효성: production stash 시 G-188-1/2/3/7 FAIL 재확인
