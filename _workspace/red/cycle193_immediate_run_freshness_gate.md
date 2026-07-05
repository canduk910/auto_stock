# 사이클 193 — 재시작 immediate run 신선도 게이트 (아침 burst 부하 완화)

## 배경 (사이클 188/189 인계 + 187 잔존 오류 공통 뿌리)

재시작 시 `run_periodic_task_loop(immediate_first_run=True)` 가 5 task 를 무조건 풀런:
- 7/3 15:40 배포 재시작 실측 = basics 풀런 17분(3,575건) + master 4분(4,374건) 즉시 실행
  → 16:00~16:30 정기분과 **이중 실행**.
- 아침 07:50 boot 도 동일 — 프리마켓 준비 구간(07:45~08:13) Supabase burst
  = 187 잔존 read 실패 33건/일의 공통 뿌리 (사이클 188 changelog 명시).
- immediate run 은 정기 task 미발화 시절(160 회귀~188 시정 전)의 유일한 공급로였으나,
  188 로 정기 발화 복원 후엔 **데이터가 신선한데도 무조건 풀런**.

**사용자 결정 (2026-07-04 AskUserQuestion 2)**: ① 신선도 게이트 (마지막 성공 시각
system_config 기록, N시간 이내면 immediate skip — catch-up 경로 보존) ② 5 task 일괄
(daily_load 16:00 / basics 16:10 / purge 16:15 / master 16:30 / universe 20:00:05).
**evening_funnel_capture 는 범위 외** (변경 0).

## 시정 설계

### 1. `src/db/system_config.py` — task 마커 헬퍼 2개 신규

```python
async def get_task_last_success(task_label: str) -> str | None:
    """키 task_last_success_<label> 의 ISO 문자열 (없으면/실패 시 None graceful)."""
    return await _get_string_or_none(f"task_last_success_{task_label}")

async def set_task_last_success(task_label: str, iso_ts: str) -> None:
    """마지막 성공 시각 upsert. 실패 시 예외 전파 없이 graceful (호출자에서 try/except)."""
```

- read 는 기존 `_get_string_or_none` 재사용 (사이클 189 execute_with_retry 경유 = 자동 수혜).
- write 는 기존 `_upsert` 패턴 재사용 (JSONB `{"value": iso}`), **retry 미경유** (쓰기 정책 영속).

### 2. `src/engine/task_loop_helper.py` — 게이트 파라미터

```python
IMMEDIATE_FRESH_SKIP_HOURS = 20.0  # 모듈 상수 (16:10 저녁 성공 → 익일 07:50 boot = ~15.7h → skip)

async def run_periodic_task_loop(..., immediate_skip_if_fresh_hours: float | None = None):
```

- **immediate_first_run 블록** (stagger sleep *후*, once() *전*):
  `immediate_skip_if_fresh_hours is not None` 일 때만 → `get_task_last_success(task_label)`
  조회 → ISO 파싱 성공 + `now_kst - last < hours` → immediate once() **skip** +
  `logger.info("[%s] immediate run skip — fresh last_success=%s", ...)` 1행.
  파싱 실패/None/조회 예외 → **실행** (안전 방향 = catch-up 보존, graceful try/except).
- **성공 마커 기록**: `immediate_skip_if_fresh_hours is not None` 인 경우에 한해,
  immediate + while 루프 양쪽에서 once() 성공 직후 `set_task_last_success(task_label,
  now_kst_iso())` — try/except graceful (기록 실패 → 다음 부팅 immediate 실행 = 안전 방향).
- **핵심 회귀 보존**: 파라미터 미지정(None) = 마커 조회/기록 일절 없음 → 기존 테스트
  (cycle106/134/158/160/171 등 helper 직접 호출) **행위 완전 동일** (신규 DB 접근 0).
- import 는 함수 내부 lazy (`from src.db.system_config import ...`) — 테스트 patch 용이 +
  순환 import 회피.
- 시각은 `src/db/_kst.py` (`KST`, `now_kst_iso`) 사용 — naive now 금지 (CLAUDE.md KST 강제).

### 3. `src/engine/scheduler.py` — 5 wrapper 에 인자 추가

`full_universe_load` / `stock_master_daily_load` / `stock_master_basics_refresh` /
`stock_master_master_load` / `stock_master_daily_purge` 5곳에
`immediate_skip_if_fresh_hours=IMMEDIATE_FRESH_SKIP_HOURS` 1줄씩 (+5L).
`evening_funnel_capture` 는 **변경 0** (범위 외 — 사용자 결정).

### 불변식 / 함정

1. **정기 while 루프 발화는 게이트 무관 무조건 실행** — skip 은 immediate 블록 한정.
   (사이클 188 복원한 정기 발화를 게이트가 다시 막으면 안 됨 — HIGH 가드.)
2. 마커 부재(최초 배포/DB 초기화) → 실행. 조회 예외 → 실행. 미래 시각 마커(시계 이상) →
   음수 경과 = fresh 로 skip 되면 위험하나 실익 낮음 — `0 <= elapsed < hours` 로 방어.
3. stagger(`initial_delay_secs`) 순서 불변: sleep → 게이트 → once. (게이트를 sleep 앞에
   두면 조회 자체가 burst 에 합류 — sleep 뒤가 맞음.)
4. 사이클 158 stagger / 106 race / 160 advance_if_passed / 88 graceful / 79 task_attrs 불변.
5. 매매 안전성 무영향 — lifecycle hook + system_config 키 2개 한정.
6. scheduler 라인 임계 가드 (`test_cycle134_task_loop_helper.py` ≤4,015) — +5L 로 초과 시
   의미 전환 (임계 상향, 사이클 66 K-2).

## 회귀 가드 (Red 요구)

- **F-1 (HIGH)**: fresh 마커 (now-10h) → immediate once() 미호출 + skip INFO 발화 +
  while 루프는 정상 진입.
- **F-2 (HIGH)**: stale 마커 (now-30h) → immediate once() 호출 (catch-up 보존).
- **F-3**: 마커 None → 실행. **F-4**: 조회 예외 → 실행 (graceful). **F-5**: 파싱 불가
  문자열 → 실행.
- **F-6 (HIGH, 회귀 보존)**: `immediate_skip_if_fresh_hours` 미지정 → 마커 조회/기록
  호출 0건 + 기존 immediate 동작 동일.
- **F-7**: once() 성공 시 `set_task_last_success(label, KST iso)` 호출. 기록 실패 예외 →
  루프 정상 지속 (graceful).
- **F-8 (HIGH)**: 정기 while 루프 발화는 fresh 마커여도 once() 실행 (skip 은 immediate 한정).
- **F-9**: 미래 시각 마커 → 실행 (음수 경과 방어).
- **F-10 (AST/구조)**: scheduler 5 wrapper 에 `immediate_skip_if_fresh_hours` 존재 +
  `evening_funnel_capture` wrapper 에 부재 (범위 외 영속) + `IMMEDIATE_FRESH_SKIP_HOURS`
  상수 존재 + 게이트 경로 naive `datetime.now()` 0건 (KST 강제).
- **F-11**: system_config 헬퍼 2개 — get 은 `_get_string_or_none` 경유(189 retry 수혜),
  set 은 upsert 패턴 + retry 미경유.

## 의미 전환 예상

- `test_cycle134_task_loop_helper.py` scheduler 라인 임계 (초과 시).
- cycle158 stagger 테스트가 wrapper kwargs 전체를 고정 단언하면 흡수 (확인 필요 —
  initial_delay_secs 값 단언만이면 무변경).

## 테스트 파일

- `tests/unit/engine/test_cycle193_immediate_fresh_gate.py` 신규 (F-1~F-9)
- `tests/unit/db/test_cycle193_task_marker_helpers.py` 신규 (F-11)
- `tests/unit/ast/test_cycle193_ast_fresh_gate.py` 신규 (F-10)
