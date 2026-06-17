# 사이클 160 hotfix — `_wait_until` target 도달 시 break 본질 복원

## 운영 사고 (verbatim)

사용자 보고: "문제가 좀 생긴 것 같아. 알테오젠 종목은 변동성 돌파, 알지노믹스 종목은 롱테일 변동성 돌파 전략으로 매수가 된 잔고인데, 장마감 시점에 매도가 안되었어. 원래는 둘다 매도가 되었어야되는데 말이야."

## 사고 매트릭스

| 시각 (KST) | 종목 | 전략 | 매수가 | 수량 | 매도 의무 | 실제 |
|------------|------|------|--------|------|-----------|------|
| 2026-06-17 14:03 | 알테오젠 (196170) | volatility_breakout | 367,000 | 1 | 15:20 강제청산 | 미발화 |
| 2026-06-17 14:33 | 알지노믹스 (476830) | long_tail_volatility | 110,000 | 1 | 15:20 강제청산 | 미발화 |

## 근본 원인 — 사이클 152 hotfix 도입 결정타 결함

`_wait_until(target)` 의 본질 = "target 시각 도달까지 대기 후 return". 사이클 152 hotfix(commit `36d2d2e`, 2026-06-16) 가 task_loop_helper 폭주 차단 의도로 `_wait_until` 본문을 교체 — `now_dt >= target_dt` 조건에서 무조건 `target_dt += timedelta(days=1)` 적용.

결과: target 정확 도달 시점 (`now == target`) 부터 이미 지난 시점까지 모두 **다음 날로 미루기** + 60s sleep 반복 → **return 불가**.

```python
# 사이클 152 결함 코드
while self._running:
    now_dt = datetime.now()
    target_dt = now_dt.replace(hour=target.hour, ...)
    if now_dt >= target_dt:           # 정확 도달도 매치
        target_dt += timedelta(days=1)  # 내일로 무조건 미룸
    wait_secs = (target_dt - now_dt).total_seconds()
    await asyncio.sleep(min(wait_secs, 60))
    # 다음 iteration → 같은 분기 → 무한 반복
```

## 운영 영향 확장

`run_daily()` 영역 5 호출 모두 작동 불가:

| 라인 | 호출 | 대상 phase | 누락 영역 |
|------|------|-----------|-----------|
| 647 | `_wait_until(TIME_KRX_MAIN_BUY_STOP)` | 15:20 | **`_force_clear_main_only` 강제청산 누락** |
| 661 | `_wait_until(TIME_KRX_MAIN_CLOSE)` | 15:30 | `post_nxt_trading` phase 전환 누락 |
| 675 | `_wait_until(TIME_NXT_POST_BUY_STOP)` | 19:50 | `buy_disabled` 미설정 |
| 682 | `_wait_until(TIME_NXT_POST_CLOSE)` | 20:00 | `unsubscribe_all` + AI자문 누락 |
| 727 | `_wait_until(TIME_SETTLEMENT)` | 20:10 | 정산 + 일일 로그 분석 + retention 누락 |

15:40 `[Session] 보드 진입: post_nxt` 로그는 정상 — `SessionTracker._session_loop` 30s 별개 task. 보드 전환은 정상이지만 scheduler 영역 phase 전환 멈춤.

## Phase 1 진단 증거

Supabase MCP READ-ONLY 추출:
- 14:34:01 KST `매매 모드 진입 (KRX 메인 + NXT)` (scheduler.py:645 도달 후)
- 14:33:29 VB prepare 완료 / 14:34:01 LTV 시가 확정 정상
- **15:00 ~ 16:00 KST 영역 `force_clear` / `execute_sell` / `매도` / `next_day_clear` 로그 0건**
- 15:21:48 KST 첫 stale 알람 (시세 단절 영역, 사이클 160 와 무관)
- 15:43:04 KST 시세 회복 (fresh=9/9 ratio=100%)
- 06:50 ~ 11:00 UTC = 15:50 ~ 20:00 KST 영역 `next_day_clear` / `settlement` / `정산` / `post_nxt_stopped` / `closing` 모두 0건

= run_daily 영역 L647 `_wait_until(15:20)` 진입 후 **return 불가** 확정.

## 시정안 — 2 모드 분기

```python
async def _wait_until(self, target: time, *, advance_if_passed: bool = False) -> None:
    while self._running:
        now_dt = datetime.now()
        target_dt = now_dt.replace(hour=target.hour, ...)
        if now_dt >= target_dt:
            if not advance_if_passed:
                return   # 본질 복원 — run_daily phase 전환 즉시
            target_dt += timedelta(days=1)   # task_loop_helper 폭주 차단 영속
        wait_secs = (target_dt - now_dt).total_seconds()
        if wait_secs <= 0:
            await asyncio.sleep(1)
            continue
        await asyncio.sleep(min(wait_secs, 60))
```

- **`run_daily()` 영역**: default 모드 (`advance_if_passed=False`) → target 도달 즉시 return → phase 전환 정상
- **`task_loop_helper` 영역**: `advance_if_passed=True` 명시 → 사이클 152 폭주 차단 의도 영속

## 변경 영역

| 파일 | 변경 | 라인 |
|------|------|------|
| `src/engine/scheduler.py::_wait_until` | 2 모드 분기 + docstring 갱신 | +25 |
| `src/engine/task_loop_helper.py` | Protocol 시그너처 갱신 + while 루프 `advance_if_passed=True` 명시 | +5 |
| `tests/unit/engine/test_cycle160_wait_until_break_restore.py` | 신규 7 케이스 (HIGH 5) | +250 |
| `tests/unit/engine/test_cycle152_wait_until_runaway_hotfix.py` | G-152-PAST-1 의미 전환 (`advance_if_passed=True` 명시) | +3 |
| `tests/unit/engine/test_cycle106_full_universe_load_lifecycle.py` | mock_wait_until 시그너처 `**kwargs` 흡수 (6건) | +6 |
| `tests/unit/engine/test_cycle134_task_loop_helper.py` | 라인 임계 ≤3,675 → ≤3,700 의미 전환 (사이클 66 K-2 패턴) | +3 |

## 회귀 가드 (사이클 160 격리 7 케이스, HIGH 5)

- G-160-BREAK-1 (HIGH): default 모드 target 도달 시점 즉시 return
- G-160-BREAK-2 (HIGH): default 모드 target 이미 지난 시점 즉시 return (늦은 진입 영역)
- G-160-ADVANCE-1: `advance_if_passed=True` 모드 target 지난 시점 내일 대기
- G-160-FUTURE-1: target 미래 시점 정상 대기 (양 모드 공통)
- G-160-RUN-DAILY (HIGH): `run_daily` / `start` 영역 `advance_if_passed=True` 호출 0건 AST 가드
- G-160-TASK-HELPER (HIGH): `task_loop_helper` 영역 `advance_if_passed=True` 명시 AST 가드
- G-160-SAFETY (HIGH): `_force_clear_main_only` / `TIME_KRX_MAIN_BUY_STOP` / `TIME_KRX_MAIN_CLOSE` / `order_engine` import 영속

## 영속 의무 매트릭스

- 사이클 26 VB MAIN 단독 영속 (`tradable_boards=("main",)`)
- 사이클 38 LTV 3보드 영속 (`("pre_nxt","main","post_nxt")`) + 명문화 (매도/익일청산/강제청산 보드 가드 *없이* 항상 작동)
- 사이클 142 결함 #1 시정 영속 (POST_NXT 활성 무관 `check_force_clear()` 호출, LTV 본체 상한가 모드 제외)
- 사이클 142 결함 #2 시정 영속 (LTV 트레일링 분기 `_limit_up_reached.add` + `high_since_buy = today_open`)
- 사이클 152 hotfix 의도 영속 (task_loop_helper 폭주 차단 — `advance_if_passed=True` 명시 영역만)
- 사이클 158/159 stagger 영속 (4 task 동시 발화 race 차단, 0/240/480/720s)
- 사이클 66 K-2 의미 전환 패턴 답습 (사이클 134 라인 임계 ≤3,675 → ≤3,700)

## 매매 안전성 검증

- 시정 영역 = `_wait_until` 본체 한정 + task_loop_helper `_wait_until` 호출 1건
- `risk.on_tick` / `order_engine` / `realtime/` / `auth/` / `scanner` 변경 0
- 15:20 강제청산 / 15:30 phase 전환 / 19:50 매수중단 / 20:00 자문 / 20:10 정산 **모두 정상 회복**
- task_loop_helper 4 task (universe / basics / daily / master) 폭주 차단 의도 영속 (사이클 158/159 stagger + 사이클 152 advance 분기 양쪽 영속)

## 운영자 즉시 액션 의무

**현재 위험 잔존 — 사이클 160 hotfix 배포 *전* 영역**:

1. **알테오젠 (196170) — HTS/MTS 즉시 시장가 매도** (NXT 애프터 15:30 ~ 20:00 가능 / KRX 다음 영업일 6/18 09:00 ~)
2. **알지노믹스 (476830) — HTS/MTS 즉시 시장가 매도** (위 동일)
3. **EC2 서버 재시작 또는 hotfix 배포** — 현재 run_daily 가 영구 정체 → 16:30 master task / 20:00 자문 / 20:10 정산 모두 누락 위험

사이클 160 hotfix 배포 영역 후:
- 6/17 손익 = `daily_performance` 영역 정산 누락 영역 검토
- 다음 영업일 6/18 _boot 영역 `run_daily()` 정상 진입 영구 확정 의무

## commit/push 대기

CLAUDE.md "코드 변경 사용자 명시 승인 전 commit/push 금지" 영속. 사용자 명시 발주 대기.
