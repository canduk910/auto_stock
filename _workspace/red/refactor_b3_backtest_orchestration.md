# Red — refactor 카드 B3: 백테스트 오케스트레이션 위임 분해 (행위 보존)

- 날짜: 2026-08-18
- 트랙: offline AI자문 계층 (20:00 백테스트 오케스트레이션). **8영역 무관**.
- 테스트 파일: `tests/unit/engine/test_refactor_b3_backtest_orchestration.py` (8 케이스)
- 구현: backend-dev (본 파일은 Red 전용 — 구현 금지)

## 목표

`recommendation_engine.py` 의 백테스트 오케스트레이션(5 함수 + 전역/상수)을 신규
`src/engine/backtest_orchestration.py` 로 **행위 보존 이관**하되, recommendation_engine
이 module-level 재export 로 기존 import 경로를 전부 보존한다(순수 리팩토링, diff 0 행위).

## 이관 대상 정본 (recommendation_engine.py 현 위치, 라인 = 현 소스 실측)

전역/상수:
- `_BACKTEST_POLL_INTERVAL_SECS: int = 60`  (recommendation_engine.py:56)
- `_BACKTEST_POLL_TIMEOUT_HOURS: int = 24`  (:58)
- `_backtest_poll_loop_running: set[date] = set()`  (:61)

5 함수:
- `_get_backtest_engine()`  (sync, :518)
- `_spawn_backtest_poll_task(target_date)`  (sync, :525 — 내부 nested `_on_done` 포함 이동)
- `_enqueue_backtest_jobs(target_date, inserted_recs)`  (async, :550)
- `_backtest_poll_loop(target_date)`  (async, :711)
- `_emit_pending_summaries(target_date, summarized_rec_ids)`  (async, :866)

## 순환 import 없음 (확인됨)

5 함수 본체가 참조하는 것:
- `_db_*` aliased import (`src.db.parameter_recommendations` / `src.db.backtest_runs`):
  `_db_list_pending_backtest`, `_db_update_backtest_summary`, `_db_insert_run`,
  `_db_list_by_date`, `_db_update_status`
- `_get_backtest_engine` 내부의 `from src.engine.backtest_engine import get_backtest_engine` (lazy)
- `compute_metric_diff` (`src.models.backtest`)
- `BacktestNotSupportedError` / `ExternalAPIError` / `ConfigError` (`src.services.exceptions`)
- `KST` (`timezone(timedelta(hours=9))`)
- 표준 라이브러리: `asyncio`, `datetime`, `logging`

recommendation_engine core(`_validate_recommendations`/`_call_openai`/
`generate_recommendations`/`compute_metrics`)는 **미호출** → 신규 모듈은 leaf(recommendation_engine
을 import 하지 않는다).

## 위임 규약 (backend-dev 인계 — 반드시 준수)

1. **logger**: 신규 모듈은 `logger = logging.getLogger("src.engine.recommendation_engine")`
   **명시** — 운영 grep `[backtest_poll]`/`[backtest_enqueue]` 연속성. `__name__` 사용 금지
   (사이클 60 stale_manager 선례: `getLogger(__name__)` 로 바꾸면 운영 로그 config 에서
   해당 prefix 누락 위험).
2. **KST**: 신규 모듈이 자체 `KST = timezone(timedelta(hours=9))` 정의. recommendation_engine
   에서 import 하면 순환. (`_backtest_poll_loop`/`_emit_pending_summaries` 가 `datetime.now(KST)` 사용)
3. **`_db_*` aliased import 동반 이관**: 위 5 개 `_db_*` alias 를 신규 모듈이 자체 import
   (`from src.db.parameter_recommendations import list_recommendations_pending_backtest as _db_list_pending_backtest, update_backtest_summary as _db_update_backtest_summary` +
   `from src.db.backtest_runs import insert_run as _db_insert_run, list_by_date as _db_list_by_date, update_status as _db_update_status`).
   recommendation_engine core 가 이들을 쓰지 않으므로 recommendation_engine.py 의 해당 import 는
   제거 가능(단 제거 필수 아님 — 본 Red 는 그 여부를 강제하지 않음).
4. **상수/exceptions 동반 이관**: `_BACKTEST_POLL_*` 상수 + `BacktestNotSupportedError`/
   `ExternalAPIError`/`ConfigError` import.
5. **재export**: recommendation_engine.py 는 module-level
   `from src.engine.backtest_orchestration import (_backtest_poll_loop_running,
   _BACKTEST_POLL_INTERVAL_SECS, _BACKTEST_POLL_TIMEOUT_HOURS, _get_backtest_engine,
   _spawn_backtest_poll_task, _enqueue_backtest_jobs, _backtest_poll_loop,
   _emit_pending_summaries)` 로 기존 이름 전부 보존.
   - `generate_recommendations`(:508 영역)의 `await _enqueue_backtest_jobs(target_date, inserted)`
     = 재export 된 이름으로 그대로 동작(generate_recommendations 는 recommendation_engine 잔류,
     자기 네임스페이스에서 재export 된 전역을 lookup).
   - `_SUPPORTED_STRATEGIES`/`_FALLBACK_STRATEGIES` frozenset(:47/:51)은 `_enqueue_backtest_jobs`
     본체가 사용 → 신규 모듈로 이동하거나 재export. (본 Red 는 위치를 강제하지 않으나 enqueue
     본체가 참조하므로 신규 모듈에서 접근 가능해야 한다.)

## Red 요구 → 케이스 매핑 (현 코드 FAIL → 이관 후 PASS)

| # | 요구 | 테스트 함수 | 현 RED 사유 |
|---|------|-------------|-------------|
| 1 | 모듈 존재 + 5 함수(async 3 + sync 2) + 3 전역 | `test_orchestration_module_defines_moved_functions_and_globals` | 신규 모듈 부재 |
| 2 | 재export 호환 = 동일 객체 | `test_recommendation_engine_reexports_same_objects` | 신규 모듈 부재 |
| 3 | 순환 import 0 (AST) | `test_orchestration_has_no_recommendation_engine_import` | 신규 모듈 부재 |
| 4 | 본체 이관 완료 (rec_engine 에 def 부재) | `test_recommendation_engine_no_longer_defines_moved_functions` | 5 함수 전부 아직 정의됨 (AssertionError 실측) |
| 5 | 행위 보존 — enqueue (True submit / False skip) | `test_enqueue_behavior_preserved_enabled` / `_disabled` | 신규 모듈 부재 |
| 6 | 행위 보존 — poll 중복 가드 | `test_poll_loop_duplicate_guard_preserved` | 신규 모듈 부재 |
| 7 | 8영역 diff 0 = scheduler import 경로 보존 + 가드 set 동일 객체 | `test_scheduler_import_path_preserved_and_guard_shared` | scheduler 문자열 assert 는 PASS(무접촉 확인), 가드 set 동일성은 신규 모듈 부재로 RED |

RED 실측 (2026-08-18): **8 failed in 0.19s** — 7 건 "backtest_orchestration 모듈 미존재",
1 건(#4) AssertionError `['_get_backtest_engine','_spawn_backtest_poll_task','_enqueue_backtest_jobs','_backtest_poll_loop','_emit_pending_summaries']`.

## patch 경로 적응 계획 (기존 backtest/poll 테스트 — 수정은 backend-dev/tester 협의)

**핵심 원리**: 이관 후 5 함수 본체는 `backtest_orchestration` 네임스페이스에서 전역을
lookup 한다. `monkeypatch.setattr(rec_mod, "<name>", ...)` 는 recommendation_engine 의 재export
바인딩만 바꾸므로 **본체 lookup 에 반영 안 됨** → 무력화. 따라서 *본체가 소비하는* 심볼의 patch
타깃을 `backtest_orchestration.*` 로 옮겨야 한다.

### 적응 필요 (본체가 소비 → `backtest_orchestration.*` 로 이동)

`_db_insert_run` · `_db_update_status` · `_db_list_by_date` · `_db_list_pending_backtest` ·
`_db_update_backtest_summary` · `_get_backtest_engine` · `_spawn_backtest_poll_task` ·
`_backtest_poll_loop_running` · `_BACKTEST_POLL_INTERVAL_SECS` · `_BACKTEST_POLL_TIMEOUT_HOURS`

대상 파일/라인:
- `tests/unit/engine/test_backtest_enqueue_db_toggle.py` — `_install_db_doubles`(85-86) +
  `_get_backtest_engine`(130/188/241/299) + `_spawn_backtest_poll_task`(133/191/242/304).
  T4 는 `system_config.get_kis_mcp_enabled`(281) patch 는 그대로(그건 backtest_engine 이 소비, 무관).
- `tests/unit/engine/test_backtest_poll_loop.py` — `_db_list_by_date`/`_db_update_status`/
  `_db_list_pending_backtest`/`_db_update_backtest_summary`/`_get_backtest_engine`/
  `_BACKTEST_POLL_INTERVAL_SECS`/`_BACKTEST_POLL_TIMEOUT_HOURS`(108-143, 218-239, 300-328,
  374-392) + 케이스 E 의 `_backtest_poll_loop_running`(419-423). 호출은 `rec_mod._backtest_poll_loop(target)`
  그대로 가능(재export 동일 함수 객체) 또는 `orch._backtest_poll_loop`.
- `tests/unit/engine/test_recommendation_backtest_hook.py` — B~F 케이스의 `_db_insert_run`/
  `_db_update_status`/`_get_backtest_engine`/`_spawn_backtest_poll_task` patch(181-204, 247-265,
  313-328, 374-394, 460-477) → `backtest_orchestration.*`.
  **케이스 A(`test_generate_recommendations_calls_enqueue_after_insert`) 의 `_enqueue_backtest_jobs`
  patch(136) 는 적응 불필요** — `generate_recommendations` 가 recommendation_engine 잔류, 재export
  전역을 자기 네임스페이스에서 lookup → `rec_mod._enqueue_backtest_jobs` rebind 가 그대로 유효.
- `tests/integration/test_recommendation_backtest_flow.py` — `_db_*`/`_get_backtest_engine`/
  `_spawn_backtest_poll_task`/`_BACKTEST_POLL_INTERVAL_SECS`(152-196, 307-332) →
  `backtest_orchestration.*`. `_backtest_poll_loop`(192) 직접 호출은 그대로 가능.
- `tests/integration/test_backtest_disabled_and_graceful.py` — `_db_*`/`_get_backtest_engine`/
  `_spawn_backtest_poll_task`/`_BACKTEST_POLL_*`(141-143, 181-185, 261-265, 333-337, 355-369) →
  `backtest_orchestration.*`. `_backtest_poll_loop`(365) 직접 호출 그대로.

### 적응 불필요 (recommendation_engine core 가 소비 → `rec_mod.*` 유지)

`expire_pending_before` · `get_trades_in_range` · `get_performance` · `compute_metrics` ·
`_call_openai` · `insert_recommendation` — 전부 `generate_recommendations`(rec_engine 잔류)가
소비하므로 patch 타깃 `rec_mod.*` 그대로.

### 적응 방식 옵션 (backend-dev/tester 택1, 본 Red 는 방식 미강제)

- (A) patch 타깃을 `src.engine.backtest_orchestration.*` 로 재지정(권장 — 명시적).
- (B) `import src.engine.backtest_orchestration as _bt` 후 `monkeypatch.setattr(_bt, ...)`.
- (재export 동일 객체 검증은 본 Red #2/#7 이 이미 담보 — 방식 (A)/(B) 등가.)

## 제약 준수

- **8영역 무접촉**: recommendation_engine.py + 신규 backtest_orchestration.py 만. scheduler.py
  미접촉(재export 로 :3760 import 경로 보존, 본 Red #7 이 문자열+동일객체 이중 가드).
- 신규 테스트 파일만 추가. 기존 backtest/poll 테스트 **미수정**(적응은 위 계획대로 backend-dev/tester).
- 순수 리팩토링 — DEFAULT_PARAMS/매매 규칙 변경 0 → `_workspace/00_leader_trading_rules.md` 동기화 불요.
