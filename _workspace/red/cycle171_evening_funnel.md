# 사이클 171 — 저녁 16:20 잠정 funnel 캡처 + 수동 trigger 단계별 캡처 (MEDIUM, 운영자 가치)

작성: team-leader (트레이딩 데스크 감독자)
승인 설계: `/Users/koscom/.claude/plans/funnel-vast-wolf.md` (사이클 171 절)
자문 근거: `_workspace/domain_consult/cycle171_master_funnel_timing_redesign.md` (의제 4 우선순위 2 + 의제 6 (a))

## 배경 (재도출 금지)

funnel은 순수 관찰성 + D-1 일봉 기반 → 장중 불변. 전날 저녁에 미리 만들면 운영자가 밤에 후보 확인 가능 (현재 09:30 개장 후 캡처는 늦음). 사이클 170에서 funnel 일관성(0-시드 + in-place upsert) 이미 시정 완료.

## 구현 명세

### 1. migration 040 — `is_provisional` 컬럼
- `supabase/migrations/040_funnel_provisional.sql`: `strategy_funnel_snapshots` 에 `is_provisional BOOLEAN NOT NULL DEFAULT FALSE` (additive, `ADD COLUMN IF NOT EXISTS`).
- 운영 DB 즉시 적용 (Supabase MCP `apply_migration`, project_id=`etaligxesjtjfkbntdve`). additive → 장중에도 안전.

### 2. `src/db/strategy_funnel.py::insert_snapshot`
- `is_provisional: bool = False` 인자 추가 (기존 호출자 회귀 0 — keyword default).
- payload dict 에 `"is_provisional": bool(is_provisional)` 동행.

### 3. 공통 헬퍼 추출 — `capture_funnel_snapshots(registry, *, is_provisional)`
- `scheduler._auto_capture_funnel_snapshots` 의 "registry 순회 → 각 strategy `_funnel_steps` 단계별 + step_no=99 insert_snapshot" 로직을 추출.
- 위치: `src/engine/scheduler.py` 모듈 함수 (또는 신규 모듈). registry + is_provisional 인자.
- **3 호출처 공유**:
  - (a) 09:30 자동 (`_auto_capture_funnel_snapshots` → 헬퍼 위임, is_provisional=False) — 현행 행위 보존
  - (b) 16:20 저녁 (신규, is_provisional=True)
  - (c) 수동 trigger (route, is_provisional=False)
- **현행 09:30 행위 보존 의무**: 헬퍼 추출 후에도 09:30 캡처가 단계별 + step_no=99 동일 row 생성 (insert_snapshot 호출 인자 동일).

### 4. `src/engine/scheduler.py` — 16:20 저녁 task
- `TIME_EVENING_FUNNEL_CAPTURE = time(16, 20)` 상수 (16:00 일봉 < 16:10 basics < **16:20 funnel** < 16:30 마스터 순서).
- `_evening_funnel_capture_task_loop` — `run_periodic_task_loop` 답습 (`_stock_master_master_load_task_loop` 패턴 100%).
  - 본체 (once_callable): registry 순회 → `strategy.prepare()` (기존 KIS-fetch 그대로 — 16:20 한가, 속도 무관, HIGH DB일봉 전환은 사이클 173) → `capture_funnel_snapshots(registry, is_provisional=True)`.
  - **16:00 일봉 적재 완료 대기**: `stock_master_daily.count_all()` (또는 `count_active`) 폴링 가드 (사이클 163 boot prepare 가드 패턴). 일봉 미적재 시 prepare 가 빈 결과 → 빈 funnel 영속 방지.
  - graceful try/except (사이클 88 답습) — prepare 실패 ticker skip, 전체 task 보존.
  - `initial_delay_secs` stagger 적절히 (16:20 정시 발화 + start() 즉시 1회 race 회피).
- **task_attrs 4 위치** (사이클 79 G-AST2): instance(`__init__`/start) + start finally + run_daily finally + stop. `_evening_funnel_capture_task` 추가. `expected_members` 갱신.

### 5. `src/routes/strategy_funnel.py::POST /snapshot`
- 현재 step_no=99 만 캡처 → `capture_funnel_snapshots(registry, is_provisional=False)` 단계별 전체 캡처로 전환.
- 응답 schema 유지 (`{target_date, saved, count}`) — saved 항목 수만 증가 가능.

### 6. UI — "잠정" 배지
- `src/routes/strategy_funnel.py` GET 응답 `snapshots[*].is_provisional` 노출 (list_snapshots 가 row `*` select 이므로 자동 포함).
- `frontend/src/api/strategy-funnel.ts`: `FunnelSnapshot.is_provisional?: boolean` 타입 추가.
- `frontend/src/pages/StrategyFunnel.tsx`: 각 row 가 `is_provisional=true` 면 amber "잠정" 배지 (testid `funnel-provisional-badge-{sid}-{step_no}`).
- MSW handlers + e2e mock 동기화 (frontend/CLAUDE.md UI 동기화 의무).

## 회귀 가드 (TDD Red 설계)

### 백엔드
- **DB**: `insert_snapshot(is_provisional=True)` → payload 에 키 동행 / 기본 False (회귀) / migration 컬럼.
- **헬퍼 3 호출처 정합**: `capture_funnel_snapshots` 가 단계별 + step_no=99 insert_snapshot 호출 (09:30 행위 보존) / is_provisional 전파 / 3 호출처 (auto/evening/route) 모두 동일 헬퍼 위임 (AST).
- **16:20 task**: freezegun 16:20 발화 + prepare 호출 + `is_provisional=True` 영속 / 일봉 미적재 시 count 폴링 대기 / task_attrs 4 위치 (`_evening_funnel_capture_task` in expected_members) / `TIME_EVENING_FUNNEL_CAPTURE == time(16,20)`.
- **수동 trigger**: route 가 단계별 (step1~N + 99) 캡처 (step_no=99 단독 폐기) / is_provisional=False.
- **SAFETY (HIGH)**: `check_exit_signal` / `check_buy_signal` funnel hook 0건 (사이클 143/170 영속) + risk/order_engine/realtime/auth import 0 + 사이클 170 in-place upsert 영속.

### 프론트
- `is_provisional=true` row → "잠정" 배지 렌더 / false → 미렌더 / 타입 정합.

## 매매 안전성
- 관찰성 한정. scanner/risk.on_tick/order_engine/realtime/auth diff 0.
- 16:00 일봉 → 16:20 prepare → 16:30 마스터 순서 의존성 보장.
- 사이클 158 재시도 hook + 사이클 32 R4 보유/익일청산 보호 + 132 (momentum funnel 제외) + 170 in-place upsert 영속.

## 검증
- `python -m pytest -q` 전체 PASS (현 3,117 기준) flakiness 0.
- 프론트 `npm test` PASS.
- `git diff -- src/engine/risk.py src/engine/order_engine.py src/realtime/ src/auth/ src/api/order.py` = 0.
- 운영 DB migration 적용 + `is_provisional` 컬럼 존재 실측.

## 커밋 금지 (장중)
구현·검증·migration 까지만. `git commit`/`git push` 절대 금지 (월요일 장중 + 사용자 명시 승인 대기). migration 은 additive 라 MCP 적용 OK (EC2 배포는 push 보류로 자연 차단).
