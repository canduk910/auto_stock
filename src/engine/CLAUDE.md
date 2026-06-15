# CLAUDE.md — src/engine/ (매매 엔진)

다중 전략 아키텍처. `StrategyBase` 추상 클래스 기반 플러그인 구조.

> 전략 6개 상세: **`src/engine/strategies/CLAUDE.md`**
> 사이클별 변경 이력: `docs/HARNESS_CHANGELOG.md`

## 모듈 맵

```
strategy_base / strategy_registry → 추상 + 등록/비중/중복 가드
strategies/{momentum, volatility_breakout, long_tail_volatility, donchian_swing, bull_flag_breakout, vcp_breakout}
session.py(MarketBoard, SessionTracker)
risk.py(on_tick) → order_engine.py(체결통보·DB persistence) → scheduler.py(시간 가드·run/settle) ← boot_manager.py(_boot 본체, 사이클 51) / stale_tracker.py(StaleTrackerState, 사이클 48) / **stale_manager.py facade 96L** (re-export only, `__all__` 21 — 사이클 67 분해) ⇄ **4 sub-module (사이클 67 카드 #14 분해)**: stale_diagnostics.py 357L (5 함수 + 4 상수 — 진단·CCNL 캐시·force_retry history prune) / stale_session_recovery.py 274L (3 함수 + 5 상수 — silent inactive 감지·세션 강제 reconnect·delta unsubscribe) / stale_universe_guard.py 157L (1 함수 + 1 상수 — 보유/익일청산 절대 보호 universe guard) / stale_watcher_core.py 399L (2 함수 — **K stale watcher 본체 HIGH hot path** `check_and_resubscribe_stale` + `resubscribe_stale_priority` 사이클 66 priority 분리 *후* cap 영속). 사이클 60 Phase 2-A1 + 사이클 61 Phase 2-A2 + **사이클 63 Phase 2-A3 (refactor #2 완료)** + **사이클 67 sub-module 분해 (카드 #14 종결)** / sell_rejection.py(SellRejectionTracker, 사이클 55 R-1 + 사이클 57 V-1 알람)
scanner.py(종목 스캔/구독/STATIC_TICKER_NAMES + 사이클 122 `_stock_master_daily_load_once` + 사이클 126 `_stock_master_basics_refresh_once` + 사이클 129 `_stock_master_master_load_once`)
**metrics_collector.py** (사이클 133 — 공통 헬퍼 `make_metrics_collector(*, prefix, summary_keys, int_keys, str_keys, accumulate_keys, use_last) -> (record_fn, flush_fn, collector_list)` 팩토리. 사이클 76 Q2 빈 윈도우 skip + 사이클 89 누적/단일 행 분기 통합 + 사이클 68 KST `noqa: F401` L-3 영속. 4 facade 위임 영역 영구 영속)
**task_loop_helper.py** (사이클 134 — 공통 헬퍼 `run_periodic_task_loop(*, scheduler, task_label, wait_time, once_callable, record_fn, flush_fn, summary_log_format, summary_keys, immediate_first_run=True, retry_delay_secs=60)` 팩토리. 사이클 88 G-REJECT graceful (CancelledError + Exception 분리) + 사이클 106 lifecycle race 차단 (immediate_first_run start 직후 즉시 1회) + 사이클 78 G-AST1 (record + flush 호출 사이트 영속 = 헬퍼 영역 내부) + Protocol `_SchedulerLike` TradingScheduler 호환. 4 task loop facade 위임 영역 영구 영속 — scheduler.py 3,501L → 3,398L -103L)
stock_master_metrics.py / stock_master_basics_metrics.py / stock_master_daily_metrics.py / **stock_master_master_metrics.py** (사이클 133 — 4 facade re-export only 패턴, 사이클 67 stale_manager.py 답습. 3 기존 facade 298L → 132L -166L -56% + master 39L 신규 일관성 결함 해소. 사이클 78 G-AST1 영속 — 4 flush 호출 사이트 ≥ 1 의무 scheduler.py 영역)
refresh_progress.py (사이클 127 — 3 작업 universe/basics/daily 진행 state 통합 메모리 dict + threading.Lock + 헬퍼 `start_progress` / `update_progress` / `finish_progress` / `get_progress` / `get_all_progress` / `is_running` / `reset_progress` / `reset_all_progress`. uvicorn 단일 워커 의무 + KST timestamp 영속. **사이클 129 TaskKey 4 확장** `Literal["universe", "basics", "daily", "master"]` + `TASK_KEYS` tuple 2 위치 동행 — AST 영구 가드)
util/tick_size.py(KRX 7구간 호가단위 헬퍼 — `get_tick_size` / `round_to_tick` / `step_down` / `step_up`)
market_regime.py(dkstock.cloud 매크로 → 매수 가드 + cash_usage_ratio)
recommendation_engine.py(20:00 AI자문) / log_analysis_engine.py(20:10 일일 로그 분석)
```

## 사이클 129 (2026-06-14) — KIS 공식 일일 마스터 파일 도입 + master_raw 별도 컬럼 + 16:30 KST 자동 task

사용자 verbatim "종목마스터 만들 때 아래 소스코드 참고해줘" + KIS 공식 샘플 코드 제공. 사용자 결정 Q4=A 마스터 우선 + Q5=C 전수 보존 + Q6=C master_raw 별도 컬럼 + Q12=A × 100 단위 환산 + Q9=B 단계별 분할 진행.

### `scanner.py` 신규 영역 (+289L)

- `market_cap_master_to_millions(prdy_avls_scal: int) -> int: return prdy_avls_scal * 100` — KIS 마스터 시총 (억) → KIS API hts_avls (백만원) 환산. Q12 사용자 verbatim "× 100" 정합 (team-leader 자체 자문 "× 10,000" 결함 자체 발견 + 시정). 사이클 116 단위 환산 패턴 답습.
- `validate_market_cap_consistency(master_avls_million, hts_avls)` — ±5%/±20% 임계 + WARNING/CRITICAL emit + 사이클 88 G-REJECT graceful
- `_is_master_blocked_for_entry(ticker)` — **1단계 차단 7건** (master_raw 우선 + raw 폴백 chain): `trht_yn` 거래정지 / `mang_issu_yn` 관리종목 / `ssts_hot_yn` 공매도과열 / `stange_runup_yn` 이상급등 / `sltr_yn` 정리매매 / `mrkt_alrm_cls_code` 시장경고 / `invt_alrm_yn` 투자주의환기 (KOSDAQ 전용)
- `get_market_cap_millions(ticker)` — master_raw 우선 + raw 폴백 통합 헬퍼 (사이클 81 G-AST1 영속)
- `_stock_master_master_load_once(force=False)` — KIS 공식 파일 다운로드 (`src/api/kis_master.py`) + `master_raw` 배치 upsert + 진행 emit + graceful (사이클 88) + `refresh_progress` integration (사이클 127)

### `scheduler.py` 신규 16:30 KST task (+86L)

- `TIME_STOCK_MASTER_MASTER_LOAD = time(16, 30)` — 일봉 task 16:00 / basics task 16:10 직후 안전 마진 + KIS 마스터 갱신 시점
- `_stock_master_master_load_task_loop()` — start() 직후 즉시 1회 + 매일 16:30 KST while 루프 (사이클 106 lifecycle race 차단 답습)
- `task_attrs` 4 위치 영속 (instance + `connect().finally` + `run_daily.finally` + `stop()`) — 사이클 79 G-AST2 영속 / expected_members 14 → 15

### 매매 안전성 무영향

- scanner 단계 매수 진입 *전* 영역만 (사이클 38 명문화 영속)
- `risk.on_tick` / `order_engine` / `realtime/` / `auth/` 변경 0
- 매도/익일청산/15:20 강제청산/손절 hot path 무관
- 1단계 차단 7건 hook = 매수 진입 *전* 차단 (이미 보유 종목 영향 0)

### 영속 의무 매트릭스 (사이클 129 영구 확인 영역)

- 사이클 17 KIS LMS chain (외부 HTTP 1회 + 사이클 122 50ms sleep 답습)
- 사이클 38 명문화
- 사이클 79 G-AST2 task_attrs 4 위치 (`_stock_master_master_load_task`)
- **사이클 81 G-AST1 raw 영역 영구 보호 (master_raw 별도 컬럼 분리 = 절대 보호)**
- 사이클 84 L-2 POST 화이트리스트 (4 라우트 영속)
- 사이클 88 G-REJECT graceful
- 사이클 106 lifecycle race 차단
- **사이클 116 단위 환산 패턴 100% 답습 (× 100)**
- 사이클 122/126 task 패턴 100% 답습
- 사이클 127 fire-and-forget + refresh_progress TaskKey 4 확장

## 사이클 127 (2026-06-13) — 3 작업 fire-and-forget + 5초 폴링 진행 가시화

사이클 126 사용자 보고 — 기본정보 새로고침 13분 39초 후 "KIS API 일시 결함" 토스트. 운영 로그 = 백엔드 정상 완료(updated=2697/2697). 진짜 결함 = **axios 클라이언트 디폴트 timeout silent 결함**. 사용자 결정 Q1=5초 폴링 (경량) + Q2=상단 배너+카운터 + Q3=3 작업 통일.

### `refresh_progress.py` 신규 (3 작업 통합 state)

- 모듈 전역 `_progress: dict[TaskKey, dict]` (universe/basics/daily 3 키) + `threading.Lock` (FastAPI 동시 요청 + BackgroundTasks race 차단)
- 각 state schema (10 키): `status` (idle/running/completed/failed) + `total/processed/updated/skipped/failed` + `started_at/finished_at` (KST `+09:00` ISO) + `elapsed_ms` + `error_message`
- 헬퍼: `start_progress(task_key, total)` / `update_progress(task_key, **kwargs)` / `finish_progress(task_key, status, **kwargs)` / `get_progress(task_key) -> dict` / `get_all_progress() -> dict[TaskKey, dict]` / `is_running(task_key) -> bool` (409 Conflict 판정용) / `reset_progress(task_key)` + `reset_all_progress()` (테스트 전용)
- **uvicorn 단일 워커 필수** (process-local in-memory state). multi-worker 시 state 불일치 silent 결함 발생.

### `scanner.py::_stock_master_basics_refresh_once()` (사이클 126 추가 영역)

- KRX 1차 폴백의 `nxt_tradable=False`/`krx_halted=False`/`admin_item=False` 하드코딩 결함 시정. KIS `inquire_stock_basics()` (CTPF1002R + FHKST01010100 merge, 사이클 107 영속) 매스 호출 → `stock_master.upsert_one()` 갱신
- 페이징 `stock_master.list_all()` (PAGE_SIZE=1000) + Rate Limit `await asyncio.sleep(_BASICS_REFRESH_RATE_LIMIT_SLEEP_SECS=0.05)` (사이클 17 KIS LMS chain 답습)
- graceful: KIS 거부 → `[stock_master_basics_refresh_skip] ticker=X reason=Y` WARNING + `failed++` continue (사이클 88 G-REJECT 답습)
- 500건마다 `[stock_master_basics_refresh]` INFO 진행 emit + 종료 시 `[stock_master_basics_refresh_summary] total=N updated=K skipped=L failed=M elapsed_ms=X` 1행
- 2,697 종목 × ~100ms ≈ 13분 소요

### 라우트 fire-and-forget 전환 (routes/stock_master.py)

- 3 POST 라우트 (`/refresh-universe` + `/basics/refresh` + `/daily/refresh`) 모두 **FastAPI `BackgroundTasks`** 사용. response 전송 *후* schedule (axios timeout 영구 차단)
- `asyncio.Lock` 폐기 → `refresh_progress.is_running()` state 기반 가드 (single source of truth)
- 응답 schema 변경: 동기 summary `{universe, fetched, elapsed_ms, ...}` → `{status: "started", task_key}`
- `_run_universe_background` / `_run_basics_background` / `_run_daily_background` 3 wrapper — once 함수 호출 + Exception 시 `finish_progress("failed", error_message=str(exc))` 안전망
- 신규 라우트 `GET /refresh-progress` — 3 작업 통합 응답 (5초 폴링 endpoint)

### `_stock_master_basics_refresh_task_loop()` (스케줄러 신규 task — 사이클 126)

- `TIME_STOCK_MASTER_BASICS_REFRESH = time(16, 10)` (일봉 task 직후 안전 마진)
- start() 직후 즉시 1회 실행 + 매일 16:10 KST 정기 (사이클 106 lifecycle race 차단 답습)
- `task_attrs` 튜플 3곳 (`stop()` + `run_daily.finally` + `connect()` finally) 에 `"_stock_master_basics_refresh_task"` 추가 (사이클 79 G-AST2 영속)

### 영속 의무 매트릭스 (사이클 127 영구 확인 영역)

- 사이클 17 KIS LMS chain (50ms sleep 영속)
- 사이클 38 명문화 (scanner 단계 매수 진입 전용, 매도/익일청산 hot path 무관)
- 사이클 79 G-AST2 task_attrs 3곳 영속 (`_stock_master_basics_refresh_task` 추가)
- 사이클 84 L-2 POST 화이트리스트 (3 라우트 영속)
- 사이클 88 G-REJECT graceful (개별 ticker 실패 → continue)
- 사이클 90 `_refresh_universe_lock` 폐기 → state 기반 가드 의미 전환 (사이클 66 K-2 패턴 답습, xfail 의미 전환 9건)
- 사이클 106 lifecycle race 차단 (start() 즉시 1회 + while 루프 영속)
- 사이클 107 CTPF1002R + FHKST01010100 merge 영속
- 사이클 122 일봉 task 패턴 영속

### 회귀 가드 (사이클 127 격리 33 PASS, flakiness 0)

- engine `test_cycle127_refresh_progress_state.py` (11 케이스 — state 머신 transition + reset + concurrent 호출)
- routes `test_cycle127_progress_routes.py` (14 케이스 — 3 POST 라우트 started/409/BackgroundTasks 등록/응답 즉시 + GET schema + idle 디폴트). **TestClient 의존 폐기 + 라우트 함수 직접 await 호출** (anyio portal event loop hang silent 결함 영구 차단)
- ast `test_cycle127_ast_progress_hooks.py` (8 케이스 — 모듈 영속 + G-AST4 `background_tasks.add_task ≥ 3` + `asyncio.create_task == 0`)

### 운영 효과 (push + EC2 자동 배포 후)

- UI "기본정보 새로고침" 클릭 → 즉시 202 응답 (timeout 0) + 상단 배너 5초 폴링으로 1500/2697 진행률 실시간 가시화
- 동일 패턴 3 작업 통일 (universe + basics + daily)
- 자동 task = 매일 16:00 일봉 + 16:10 basics 정기 발화

## 사이클 126 (2026-06-13) — 종목마스터 UI/데이터 결함 4건 통합 시정

사용자 보고 4건: (1) 전체현황 1000 cap (2) 목록 데이터 부족 (3) NXT/거래정지/관리종목 입수 누락 (4) 일봉 task 미발화.

### 결함 1 시정 — `stock_master.get_stats()` count="exact" 디코딩

- PostgREST 디폴트 1000행 한도 → `len(rows) ≤ 1000` cap. 시정: count 전용 `.select("ticker", count="exact").limit(0)` + raw 분석 `.range(0, 9999)` 분리. `count_all = 2,697` 정확 반영

### 결함 3 시정 — KIS CTPF1002R 매스 보강 자동 task + 수동 trigger

- 자동 task: `scheduler.TIME_STOCK_MASTER_BASICS_REFRESH=16:10` + `_stock_master_basics_refresh_task_loop()` (start() 즉시 1회 + 매일 16:10 KST)
- 수동 trigger: `POST /api/stock-master/basics/refresh` (사이클 127 fire-and-forget 전환)
- 적재 함수: `scanner._stock_master_basics_refresh_once()` — `inquire_stock_basics()` (사이클 107 merge) + `upsert_one()` + Rate Limit 50ms sleep + graceful
- metrics 모듈: `stock_master_basics_metrics.py` (record/flush 페어링, 사이클 122 답습)
- 운영 실측 (2026-06-13 10:46 KST 시작 → 11:00:22 완료): updated=2697/2697, NXT 가능 400 / 거래정지 60 / 관리종목 57 (이전 0/0/0 영역에서 정상 분포 입수)

### 결함 4 시정 — 일봉 task 진단 강화 + 수동 trigger

- `scanner._stock_master_daily_load_once()` (사이클 122 영속) 영역에 진단 로그 강화 + `db_write_failures` 카운터
- 수동 trigger: `POST /api/stock-master/daily/refresh` (사이클 127 fire-and-forget)

### 매매 안전성 무영향

- scanner 단계 매수 진입 *전* 영역만 변경 (사이클 38 명문화 영속)
- `risk.on_tick` / `order_engine` / `realtime/` / `auth/` 변경 0
- 매도/익일청산/15:20 강제청산/손절 hot path 무관

## 사이클 122 (2026-06-12) — KIS 일봉 도입 + `stock_master_daily` 적재 task

사용자 결정 Q1=A + Q2=C + Q3=B + Q4=B (team-leader 권고 채택).

### 핵심 사실

- **신규 KIS API 도입 0건** — `fetch_daily_candles` (사이클 14, `src/api/condition.py`) 100% 재사용
- **영속화만 추가** — memcache 5분 TTL → DB 적재로 전환
- DB 적재 단계만 추가, 전략 prepare 영역 전환은 사이클 123+ 별개

### `scanner.py::_stock_master_daily_load_once` (+168L)

- 호출: `_stock_master_daily_load_task_loop` 매일 16:00 KST 1회
- 분기 로직: `max_bas_dd(ticker)` 사용 — 부재 시 백필 (T-100일), 존재 시 증분 (1일 단위)
- KIS `fetch_daily_candles(ticker, days=N)` 호출 → `upsert_batch(ticker, rows)` 영속화
- graceful (사이클 88 G-REJECT 답습) — KIS 거부/타임아웃 시 ticker skip 후 다음 진행
- emit: `[stock_master_daily_load_summary]` 1행 INFO (tickers_total / inserted / skipped / failed / elapsed_ms)

### `scheduler.py` — 매일 16:00 KST task lifecycle

- `TIME_STOCK_MASTER_DAILY_LOAD = time(16, 0)` (사이클 122 — KRX 메인 종료 30분 후 안전 마진)
- `_stock_master_daily_load_task_loop`: start() 직후 즉시 1회 + 매일 16:00 KST while 루프 (사이클 106 lifecycle race 패턴 답습)
- stop() task cancel 3곳 추가 (`_stock_master_daily_load_task` — `expected_members` 13종 갱신, 사이클 79 G-AST2 답습)

### 영속 의무

- 사이클 14 `fetch_daily_candles` 재사용 (신규 KIS API 도입 0건)
- 사이클 38 명문화 — scanner 단계 매수 진입 전 한정 (매도/익일청산 hot path 무관)
- 사이클 49 VCP Pullback ATR ZigZag = 캔들 입력만 의존 (행위 영향 0)
- 사이클 79 G-AST2 task cancel 영속
- 사이클 81 G-AST1 raw JSONB 덮어쓰기 금지 답습
- 사이클 106 lifecycle race 차단 패턴 (start() 즉시 1회 + while 루프)

### 운영 효과 (push + EC2 자동 배포 후)

- 16:00 KST start() 직후 1회 백필 — 2,700 종목 × 100ms ≈ 4.5분 소요
- 매일 16:00 KST D-1 영업일 증분 1행 추가
- DB 부담: 270K 행 × 80 bytes ≈ 22MB (Supabase 무료 tier 500MB 의 4.4%)
- donchian/VCP/VB 전략 선시행 데이터 준비 완료 (사이클 123+ 전환)

### 회귀 가드 (사이클 122 격리 34 PASS, flakiness 0)

- `tests/unit/db/test_cycle122_stock_master_daily.py` 15 케이스
- `tests/unit/engine/test_cycle122_daily_load_task.py` 11 케이스
- `tests/unit/ast/test_cycle122_kis_tr_id_persistence.py` 4 케이스 (FHKST03010100 TR_ID 영속)
- `tests/unit/engine/test_scheduler_stop_zombie_tasks.py` expected_members 13종 갱신 (사이클 79 G-AST2 답습)

### 사이클 123+ 인계

- HIGH: donchian/VCP/VB prepare 영역에서 `get_donchian_high` / `get_atr` / `get_recent_daily_with_fallback` 헬퍼 전환
- LOW: 90일 retention cron (사이클 6 답습)
- D+1 운영 실측 (다음 영업일 16:00 KST `[stock_master_daily_load_summary]` emit 확인)

## 사이클 106 (2026-06-11) — `_full_universe_load_task_loop` lifecycle race 영구 차단 (start() 직후 즉시 1회 + while 루프)

사용자 보고 (verbatim): "종목마스터 갱신작업 점검이 금일 내로 완료되어야 할 것 같아. 현재 종목마스터의 상단에 있는 메시지는 이제 무효한거 아닌가? 점검해서 UI에서 지우고 프론트와 백엔드 모두 현행화하길 바래." Phase 1 진단 결정적 발견: stock_master 191 ticker 영구 영속 = 사이클 101 `_full_universe_load_task_loop` 어제 (2026-06-10 수) 20:00:05 **미발화** 영역 영구 영속 확정. root cause = start() 직후 → `_wait_until(20:00:05)` 영역 영구 영속 대기 중 → 20:10 _settle → stop() cancel 발화 = **lifecycle race**.

### `_full_universe_load_task_loop` start() 직후 즉시 1회 + while 루프 영구 영속

- **위치**: `src/engine/scheduler.py::_full_universe_load_task_loop` (+21/-14L 순증 +7L)
- **변경 전 (사이클 101)**: while 루프 `_wait_until(20:00:05)` 후 호출 → start() 직후 영구 영속 대기 → lifecycle race 영역 영구 영속
- **변경 후 (사이클 106, 2026-06-11)**:
  1. **start() 직후 즉시 1회 실행 블록** — `_full_universe_load_once()` 호출 + try/except graceful (CancelledError → return / Exception → graceful `logger.exception("[full_universe_load] 초기 실행 실패 graceful")`)
  2. **while 루프 블록** — `_wait_until(20:00:05)` 무한 루프 (CancelledError → break / Exception → graceful `logger.exception("[full_universe_load] while 루프 실패 graceful") + asyncio.sleep(60)`)
- **사유**:
  - 사이클 101 시점 silent 결함 영구 차단 (start() 직후 영구 영속 대기 → 20:10 _settle → stop() cancel = lifecycle race 영구 차단)
  - 사이클 78 G-AST1 + 79 G-AST2 영속 (`_full_universe_load_task` stop 튜플 포함 영구 영속, lifecycle 영역 답습)
  - 사이클 83 `_scan_pool_eager_refresh_task` 영속 답습 (start() 직후 즉시 1회 + while 루프 + asyncio.sleep)
  - is_stale 24h TTL idempotency 영역 영구 영속 활용 = 동일 영업일 2회 실행 시 24h TTL idempotent 영구 영속 (`stock_master.is_stale()` 영속)
  - asyncio.sleep(60) = KIS LMS chain 안전 마진 영속 (사이클 17 OPSP0002 backoff 영속 답습)

### 영속 의무 매트릭스 (사이클 106 영구 확인 영역)

- **사이클 32 R4 universe guard 영속** (보유/익일청산 절대 보호)
- **사이클 38 명문화 영속** (영역 3 = scheduler lifecycle 영역, 매수 진입 전 영역 한정 + 매도/손절/익일청산/15:20 강제청산 hot path 무관)
- **사이클 78 G-AST1 + 79 G-AST2 영속** (`_full_universe_load_task` stop 튜플 포함 영구 영속, 영역 3 lifecycle 영역 답습 + `_api_recovered_collector_task` cancel 영구 가드 영속)
- **사이클 88 G-REJECT 영속** (재구독 영역 영구 보존, 영역 3 = lifecycle 영역 차단만, 재구독 영역 변경 0)
- **사이클 101 영속 영구 확인** (`_full_universe_load_once` 함수 영역 변경 0, lifecycle 영역만 시정)
- **사이클 102 G-REJECT 영속** (양 agent 일치, 매수/매도/익일청산 hot path 영역 보존 의무)
- **사이클 49→106 누적 61 사이클 + hotfix 14 영역 영속**

### 운영 효과 (push + EC2 자동 배포 후)

- `[full_universe_load] 초기 실행 완료 total=N kospi=K kosdaq=L` start() 직후 즉시 1회 emit (영구 영속)
- 매일 20:00:05 while 루프 정기 실행 영역 영구 영속
- stock_master 191 ticker → **~2,800 ticker 정상화 영역 영구 영속** (KOSPI ~1,400 + KOSDAQ ~1,400, 사이클 99 60 ticker 영역 영구 영속 회복 + 사이클 100 3 prefix OR 영구 영속)
- 매매 안전성 무영향 (영역 3 = lifecycle race 차단 영역 한정 + 매수/매도/익일청산/15:20 강제청산 hot path 무관)

## 사이클 103 (2026-06-11) — strategy.py dead code 영구 폐기 + momentum.py 손절 로그 임계 동행 emit

사이클 102.5 회고 결정적 사실: 코미코(183300) 2026-06-11 10:03 매수 138,200원 → 13:21:30 STOP_LOSS 매도 138,200원. 단일 근본 원인 = DB `strategy_config.momentum.params.stop_loss_rate = -2.4%` (2026-06-03 22:11 KST 사용자 수동 apply). 매도 시점 loss_rate = -2.604% ≤ -2.4% 만족 → momentum.py STOP_LOSS 분기 정상 작동. 사용자 의문 = 코드 DEFAULT `-7.5%` 가정 → 운영 영역 `-2.4%` 영구 영속 가시화 부족 → 오인. **결함 영역 = 아님** (코드 정상, 운영 가시화 영역 보강 의무).

### 영역 2 — `momentum.py:127` 손절 로그 임계 동행 emit

- **변경 전**: `logger.info("손절 신호: %s(%s) 매수가(%d) 대비 %.1f%% (현재가: %d)", strategy_name, ticker, buy_price, loss_rate * 100, current_price)`
- **변경 후 (사이클 103, 2026-06-11)**: `logger.info("손절 신호: %s(%s) 매수가(%d) 대비 %.1f%% (임계: %.1f%%, 현재가: %d)", strategy_name, ticker, buy_price, loss_rate * 100, stop_loss * 100, current_price)` (+1 인자 `stop_loss` 임계 동행 emit)
- **사유**:
  - 사이클 102.5 회고 결정적 사실 (코미코 사례 운영자 오인 영역 영구 차단)
  - 미래 동일 영역 운영자 오인 영구 차단 (운영자 즉시 임계 확인 가능)
  - 사이클 89 한글 친숙 용어 영속 답습 + 사이클 102 가시화 영역 보강 답습

### 영역 3 — `strategy.py` dead code 영구 폐기 (callsite 0건 영구 영속 확인 후 안전 폐기)

- **폐기 영역 (L85~L207, -119L 순감)**:
  - `check_buy_signal(ticker, current_price, recent_high, params, position_count_today)` — 64L 매수 신호 판단 모듈 함수 (callsite 0건 영구 영속 확인)
  - `check_stop_loss(ticker, current_price, buy_price, params)` — 21L 손절 판단 모듈 함수 (callsite 0건 영구 영속 확인)
  - `check_next_day_clear(ticker, current_price, buy_price, params)` — 34L 익일 청산 판단 모듈 함수 (callsite 0건 영구 영속 확인)
- **보존 영역 (영구 영속)**:
  - `class Signal` + `class Position` + `class StrategyState` (사용 영역 영속)
  - 7 상수 (`MOMENTUM_RECENT_HIGH_DAYS` 등 사용 영역 영속)
  - `calc_buy_quantity()` (사용 영역 영속)
- **AST 영구 가드 신설**: `tests/unit/ast/test_cycle103_ast_no_dead_strategy_funcs.py` (3 함수 영구 부재 영구 가드 + 미래 재발 영구 차단)
- **사유**:
  - callsite 0건 영구 영속 확인 (전체 production codebase grep + tests/ grep 모두 0건)
  - 사이클 78 G-AST1 + 79 G-AST2 영속 패턴 답습 (dead code 안전 폐기 + AST 영구 가드 신설)
  - 코드 정합성 영속 (사이클 49→103 누적 58 사이클 영속 영역)

### 영속 의무 매트릭스 (사이클 103 영구 확인 영역)

- **사이클 38 명문화 영속** (영역 2 매도 hot path 영역 — momentum.py STOP_LOSS 분기 PRE/MAIN/POST 무관 항상 작동)
- **사이클 78 G-AST1 + 79 G-AST2 영속** (영역 3 dead code 폐기 + AST 영구 가드 영역 답습)
- **사이클 89 한글 친숙 용어 영속** (영역 2 로그 한글 메시지 영속)
- **사이클 102 G-REJECT 영속** (양 agent 일치, 매수/매도/익일청산 hot path 영역 보존 의무)
- **사이클 49→103 누적 58 사이클 + hotfix 14 영역 영속**

### 운영 효과 (push + EC2 자동 배포 후)

- momentum.py 손절 로그 = 임계 동행 emit (운영자 즉시 임계 확인 가능, 코미코 사례 운영자 오인 영구 차단)
- strategy.py = dead code 영구 폐기 (코드 정합성 영속 + 미래 재발 영구 차단 AST 가드)
- 매매 안전성 무영향 (영역 2 = 로그 메시지 1줄 보강 영역 + 영역 3 = dead code 영구 폐기 (callsite 0건 영구 영속 확인) = 매수/매도/익일청산/15:20 강제청산 hot path 무관)

## 사이클 102 (2026-06-11) — force_retry 임계 상향 + flush 호출 사이트 영구 확인

사용자 신규 요구 "재구독 로직 자체가 실수가 아닌가 싶어. 시세구독 관련 부분을 전면 새로운 시각에서 재검토" + refactor-expert + domain-expert 병렬 자문 일치 (사이클 88 G-REJECT 영구 영속 + 임계 상향 영역 안전 마진 2 배 확장). 사용자 결정 Q73=B (5분 → 10분 + 12회 → 6회).

### `stale_diagnostics.py::STALE_FORCE_RETRY_AFTER_SECS` + `STALE_FORCE_RETRY_HOURLY_CAP` 임계 상향

- **위치**: `src/engine/stale_diagnostics.py:29~32`
- **변경 전 (사이클 29 R1, 2026-05-21)**: `STALE_FORCE_RETRY_AFTER_SECS = 300` (5분) + `STALE_FORCE_RETRY_HOURLY_CAP = 12` (시간당 12회)
- **변경 후 (사이클 102, 2026-06-11)**: `STALE_FORCE_RETRY_AFTER_SECS = 600` (10분) + `STALE_FORCE_RETRY_HOURLY_CAP = 6` (시간당 6회)
- **사유**:
  - KIS LMS chain 사고 안전 마진 2 배 확장 (사이클 29 005935 chain 진단 의무 영속)
  - 운영 실측 예상 (124~141건/일 → 50~70건/일 영구 감소)
  - 사이클 29 R1 영속 (임계 상향만, 영역 폐기 0 — 사이클 102 = 사이클 29 R1 임계 상향 영역 답습 + 시간 척도 유지)
- **영속 의무 영역 (변경 0)**: `MAX_STALE_RETRIES = 5` 영속 (사이클 17 보강) + `STALE_FRESHNESS_SECS = 60` 영속 (사이클 61 Phase 2-A2 이전 영역) + `_resubscribe_stale_priority` cap=10 priority 분리 *후* 적용 영속 (사이클 66 K-10).

### `scheduler.py::_api_recovered_collector_loop` flush 호출 사이트 영구 확인 (영역 1 변경 0)

- **위치**: `src/engine/scheduler.py:2543~L2565` (`_api_recovered_collector_loop`) + `stop()` (L923~L928) lifecycle hook
- **사이클 78 G-AST1 영역 영속 영구 확인 (변경 0)**: `flush_swing_rest_poll_collector` + `flush_stale_watcher_collector` 5분 주기 호출 영속 + `stop()` lifecycle hook 양쪽 flush 영속.
- **사이클 102 신규 추가 (handler.py flush 영역 chain)**: `flush_silent_drop_count` import (L41) + 5분 주기 호출 (L2567~L2571) try/except graceful (사이클 78 G-AST1 영역 답습 — 동일 collector loop 영역 chain).
- **AST 영구 가드 5 신설**: G-78-VERIFY-1~5 (`[swing_rest_poll_summary]` + `[stale_watcher_summary]` emit 영속 + flush 호출 사이트 3 (collector loop / stop / 5분 주기) 영속 + 사이클 102 신규 flush 영역 chain 영속).

### 영속 의무 매트릭스 (사이클 102 영구 확인 영역)

- **사이클 29 R1 영속**: 임계 상향만, 영역 폐기 0 (시간 척도 + cap 영역 유지)
- **사이클 32 R4 universe guard 영속**: 보유/익일청산 절대 보호
- **사이클 66 cap=10 priority 분리 영속**: HIGH > cap 절대 보장
- **사이클 67 stale_manager 4 sub-module 영속**: stale_diagnostics + stale_session_recovery + stale_universe_guard + stale_watcher_core
- **사이클 78 G-AST1 flush 호출 사이트 영속**: collector loop / stop / 5분 주기 (영역 1 변경 0 영구 확인)
- **사이클 79 G-AST2 task cancel 영속**: `_api_recovered_collector_task` cancel 목록 영속
- **사이클 88 G-REJECT-1/2/3 영구 영속**: 외부 LLM 단순 graceful 추천 거부 + 재연결 trigger 영역 영구 보존
- **WebSocket 4중 안전망 영속**: F1 + `_scan_loop` + K stale watcher + `_resubscribe_stale_priority`
- **CLAUDE.md "절대 깨지 말 것" 8 영역 영속**

### 운영 효과 예상 (push + EC2 자동 배포 후)

- `[stale_force_retry]` 124~141건/일 → **50~70건/일 영구 감소** (LMS chain 안전 마진 2 배 확장)
- `[swing_rest_poll_summary]` / `[stale_watcher_summary]` / `[dispatch_drop_summary]` 5분 주기 emit 영속 (사이클 74/78/102 통합 가시화)
- 사이클 88 G-REJECT-1 callback `raise` 영속 = WebSocket 재연결 자연 발화 영역 영구 보존

## strategy_base.py

- `StrategyBase` 추상 메서드: `prepare` / `check_buy_signal` / `check_exit_signal` / `calc_buy_quantity`
- 공통 헬퍼: `_calc_used_funds()` / `_fallback_one_share(current_price)` — 6개 전략의 1주 폴백 통합. 잔여 자금 = `total_investment - (positions buy_price×qty 합 + pending_buy_amounts 합)`. 전략 한도 초과 결함 차단
- `Signal`: NONE / BUY / STOP_LOSS / NEXT_DAY_CLEAR / TRAILING_STOP / FORCE_CLEAR
- `Position`: ticker, buy_price, quantity, order_no, strategy_id, buy_date, is_next_day(프로퍼티)
- `Position.is_next_day`: `buy_date < today AND strategy_id not in _MULTIDAY_STRATEGIES`(=`{donchian_swing, vcp_breakout}`). 멀티데이 전략은 항상 False — 확장 시 frozenset 멤버만 추가, `Position` 시그니처 변경 금지
- `StrategyState`: positions, pending_buys, **pending_buy_amounts**(ticker→가격×수량, 1주 폴백 잔여 자금 계산), total_investment, daily_realized_pnl, cached_buyable_qty/at, buy_blocked_until, low_funds_tickers, **signal_count_today / order_attempt_today / fill_count_today** + 헬퍼 (`is_buy_blocked / block_buy / unblock_buy / is_buyable_cache_fresh / is_low_funds_blocked / block_low_funds / clear_low_funds`)
- 일일 퍼널 카운터는 `_reset_daily_state()` 0 초기화 → `metrics.strategy_funnel` 노출
- `pending_buy_amounts` 는 OrderEngine `execute_buy` 시장가/지정가 폴백에서 `pending_buys.add(ticker)` 옆 동기 등록. `pending_buys.discard` 옆에서 동시 정리

## strategy_registry.py

- `allocate_funds(total_asset)` 비중 기반 분배 / `update_weights(weights)`
- `is_ticker_held_by_any` / `is_ticker_sold_today_by_any`
- **`is_ticker_blocked_for_buy(ticker)`** — 보유 OR 주문중 OR 당일매도 통합 가드. RiskManager·OrderEngine 매수 입구
- `get_strategies_status()` — 프론트 노출

## risk.py

`on_tick()`: ticker_prices 갱신 1회 → `registry.enabled()` 순회 → 전략별 exit/buy 신호.

- **사이클 19 (2026-05-20) `_selling` 가드**: `risk.on_tick` 의 보유 분기에서 `check_exit_signal` 호출 *전* `order_engine._selling` 검사 — 매도 발사 후 체결통보 도착 전까지 신호 평가 + 로그 폭주 차단. 042700 7초 18+ 행 운영 결함 대응. 6 전략 공통 적용

매수 신호 평가 *전* 가드 (순서):
- **보드 가드**: `session_tracker.is_tradable(strategy_id, params)`. **사이클 38 (2026-05-22) 명문화**: `tradable_boards` 는 매수 진입 전용 — 매도/손절/Trailing/익일청산/15:20 강제청산/상한가 손절 모니터링은 보드 가드 *없이* 항상 작동. `check_exit_signal` 분기는 본 가드 *전* 진입 (`on_tick` line 88-99 영역)
- **시장 레짐 매수 가드 (4 모드)**: `get_current_regime().get_buy_block_state()` async — DB `buy_block_mode` + 4 임계값 조회
  - `HARD blocked` → 매수 skip + `[regime_block]` 1분 주기 INFO
  - `WARN blocked` → 매수 허용 + `[buy_block_warn]` WARNING 1행
  - `SOFT blocked` → 매수 허용 + `execute_buy(soft_multiplier=0.5)` → 수량 `max(1, int(qty*0.5))` 축소
  - `OFF` → 가드 비활성
  - 4 임계 OR: `regime=defensive` (defensive_enabled=true) / `vix>vix_threshold` / `fear_greed_score>fg_high_threshold` / `<fg_low_threshold`. 매도/손절은 본 분기 진입 전 평가 → 영향 없음. 외부 fetch 실패 / `DKSTOCK_REGIME_ENABLED=false` → empty 폴백 (blocked=False)
  - 기본값: mode=HARD, vix=25 / fg_high=85 / fg_low=15 / defensive_enabled=true
- **중복 가드**: `registry.is_ticker_blocked_for_buy()`
- **자금 사전 가드**: `state.is_low_funds_blocked(ticker)` 또는 `current_price > state.total_investment` skip. **사이클 31 R6 (2026-05-21) 가시화**: `current_price > total_investment` 분기에 `_risk_silent_skip_logged_today: DailyEmitCap[tuple[str, str]]` (RiskManager 필드, 사이클 56-D 마이그레이션) 기반 1회/페어/일 INFO emit cap — `[risk_silent_skip] ticker=009150 strategy=volatility_breakout reason=price_gt_total_investment price=1186000 total=352217`. 매 틱 폭주 차단. `scheduler._reset_daily_state` → `RiskManager.reset_daily_state()` 위임 (사이클 56-D 캡슐화 — 사이클 52 OrderEngine 패턴 답습) + AttributeError 후방호환 가드. 5/21 09:13 VB 미매수 사고 디버깅 곤란 해소
- **사이클 65 거래대금 동행 필터 (2026-06-06) — scanner 단계 거래대금 임계 차단 (사이클 64 답습 + Q7-5 갭상승 회피 효과 폐기 보강)**: 사용자 의도 = 가격만으론 작전주 차단 불충분 (예: 5,000원 통과 + 거래대금 5천만 = 작전 신호). domain-expert 자문 옵션 A 전부 적용 (Q1~Q5 + Q6-1~Q6-4). **사이클 64 패턴 100% 답습**: `_collect_protected_tickers_for_scanner` 헬퍼 100% 재사용 + 60s TTL 캐시 (`time.monotonic`) + invalidate 즉시 무효화 (**Q7-1 unsubscribe 0 발화 영속**) + DailyEmitCap 1회/ticker/일 + daily_summary + reset_daily 동행 + AST keyword 의무 + 사이클 38 명문화 (매수 진입 전용). **Q1 임계 (HIGH)**: 디폴트 0 (비활성) + UI 0~100억 step 1억 + 권장값 마커 1억/5억/10억 (team-leader 1차 0~5,000억 → 도메인 반박 채택, 100억 이상 비현실). **Q2 데이터 소스 (HIGH 핵심) — 옵션 C 통합 폴백**: (1) `scanner.ticker_market_info["trade_amount_raw"]` (신규 키, 원 단위 정밀값) 1순위 — scanner 가 이미 `fetch_rising_stocks::fetch_stock_detail` 호출 + `acml_tr_pbmn` 보강 중이라 **KIS 호출 0건 추가** (2) `stock_master.raw.acml_tr_pbmn` 2순위 fallback (3) 둘 다 miss = graceful 통과 (Q6-1 09:00 race 영속, 시스템 매매 무용 차단). **신규 키 호환**: `trade_amount_raw` 추가 + 기존 `trade_amount` (억 단위 round) 호환 보존 — UI/API 응답 영속. **Q3 순차 hook**: `_apply_price_filter` (사이클 64) → `_apply_trade_amount_filter` (사이클 65) 순차 호출 — `subscribe_filtered_stocks` 4 호출 (tickers + extra_tickers + breakout/momentum for loop + swing 명시 분리). **Q4 헬퍼 재사용**: `_collect_protected_tickers_for_scanner` 100% 재사용 + 60s TTL **별도 캐시** (단일 책임). **Q5 별도 prefix**: `[trade_amount_filter_scanner_skip] ticker=... acml_tr_pbmn=... reason=below_min min=...` INFO + `[trade_amount_filter_scanner_daily_summary] block_count=N` 1행. **Q6-1 (HIGH) 09:00 race graceful 영속**: `acml_tr_pbmn=0` (양쪽 miss) = graceful 통과 — 09:00 직후 누적 거래대금 0 시 후보 차단 = 시스템 매매 무용 위험 영구 차단. **funnel `step_no=97`** (사이클 64 step_no=98 보다 *전* 단계 표기). **사이클 64 hotfix 패턴 답습 (H-2 NO_TRY)**: `scheduler._settle()` 직전 `await _scanner_mod.emit_trade_amount_filter_scanner_daily_summary()` **try/except 금지** (사이클 64 G-3 답습) + `_reset_daily_state()` 동행 `_scanner_mod.reset_trade_amount_filter_daily_state()` 호출. **신규 5 함수** (scanner.py): `_get_trade_amount_filter_for_scanner` (60s TTL) + `invalidate_trade_amount_filter_cache_scanner` (Q7-1 unsubscribe 0) + `reset_trade_amount_filter_daily_state` + `_get_acml_tr_pbmn` (Q2 옵션 C 3 분기) + `_apply_trade_amount_filter` (Q1 옵션 D 3중 안전망 + Q6-1 graceful + funnel step_no=97) + `emit_trade_amount_filter_scanner_daily_summary`. **모듈 전역 4 필드**: `_trade_amount_filter_cache` / `_trade_amount_filter_cache_expires_at` / `_trade_amount_filter_scanner_skip_logged_today: DailyEmitCap[str]` / `_trade_amount_filter_scanner_skip_count_today: dict[str, int]`. **회귀 가드 31 함수 (28 케이스 / 12 파일 분리, HIGH 3)**: A system_config 3 + B 본체 4 + B-5 옵션 C 3 분기 + **C 보유/익일청산 보호 2 HIGH** + D+E 캐시 + DailyEmitCap 4 + F integration 4 + **G AST keyword + 호출 카운트 2 HIGH** + H daily_summary 1 + H-2 scheduler 통합 + AST 3 + C-Route 3 함수 + **I 신규 (Q6 자문) 2** (I-1 옵션 C 정합성 + I-2 Q6-1 09:00 race) + F-FE 프론트 4. **백엔드 1939 → 1970 PASS** (+31 = 사이클 65 신규 26 + 사이클 64 vacuous PASS 5 진정한 PASS 전환). **사이클 64 vacuous PASS 진정한 PASS 전환 (부가 효과)**: 사이클 65 hook 추가로 사이클 64 G-2 keyword 호출 + H-2 NO_TRY 모두 호출 발생 → 진정한 PASS. **사이클 62 갭상승 회피 효과 폐기 보강 평가** (Q7-5 인계): 작전주 시나리오 80~90% 회복 (신규 상장 작전주 / 기존 갭상승 작전주 차단 + 정상 IPO/우량주 보존). 잔존 10~20% = 시스템 본질 한계 (운영자 화이트리스트 영역). **운영 2주 후 정량 측정 의무**. **신규 카드 #16 (MEDIUM, Q6-4)** 후보 풀 폭축 역설 risk 2주 회고 — 사이클 67+ 발의. UI: `TradeAmountFilterCard.tsx` 167L (사이클 64 PriceFilterCard 답습, 4 testid + 권장값 마커 3 + 안내 배너 Q6-1 명시).
- **사이클 64 가격 필터 (2026-06-06) — scanner 단계 종목 필터 (사이클 62 폐기 + 위치 변경 + 단순화)**: 사용자 의도 재정의 = **WebSocket 구독 *전* 종목 풀 차단** (매매 신호 판단용 X). 사이클 62 `risk.on_tick` 가격 필터 분기 + 3 모드 (HARD/WARN/OFF) + current_price fallback + RiskManager 캐시 4 헬퍼 **전부 폐기** (G3, risk.py -178L). 신규 위치: `src/engine/scanner.py::subscribe_filtered_stocks` 진입점 내부 **단일 hook** (Q4 자문 옵션 A — 호출자 시그너처 변경 0 + 신규 전략 추가 누락 차단). **단순화** (Q4 자문 옵션 A): mode 폐기 (HARD 만 의미 + WARN/OFF 제거 = 단순 임계 필터). DB 키 2 종만 (`price_filter_min` / `price_filter_max`, mode 키 폐기). **Q1 자문 옵션 D 3 중 안전망 (보유/익일청산 절대 보호 HIGH)**: (1) `_collect_protected_tickers_for_scanner()` 공통 헬퍼 (`registry.all().positions` ∪ `_pending_next_day_clear`, 사이클 32 R4 universe guard 답습), (2) `_apply_price_filter` 최상단 early-return (`if ticker in protected_tickers: survived.append(ticker); continue`), (3) AST `protected_tickers=` keyword 의무 가드 (G-2 정적 검증). **Q2 자문 (current_price fallback 폐기)**: `stock_master.raw.prdy_clpr` 단독 (scanner 단계 = WS 구독 *전*, current_price 미확보) + 미확보 graceful 통과 (사이클 32 R4 답습) + KIS `inquire-price` pre-fetch 비채택 (Rate Limit + hot path 부담). **60s TTL 캐시** (`time.monotonic`) + **`invalidate_price_filter_cache_scanner()` 즉시 무효화** + **Q7-1 unsubscribe 발화 0건 HIGH** (다음 `_scan_loop` 5분 자연 delta, KIS LMS chain 차단 — 사이클 17 OPSP0002 답습). 임계 외 종목 → `[price_filter_scanner_skip] ticker=... prdy_clpr=... reason=below_min/above_max min=... max=...` INFO + `DailyEmitCap[str]` 1회/ticker/일 cap. **Q7-4 funnel `step_no=98` hook**: `strategy_funnel_snapshots` step_no=98 INSERT (graceful). **일일 카운터** `_price_filter_scanner_skip_count: dict[str, int]` (`count`) — `scheduler._settle()` 직전 `[price_filter_scanner_daily_summary] min=... max=... skip_count=N` INFO 1행. **사이클 64 hotfix (H-2 + G-3 영구 가드, tester verify 결함 1건 발견 후)**: `scheduler.py:638-642` 가 사이클 62 폐기 메서드 `_emit_price_filter_daily_summary` 잔존 호출 → AttributeError graceful skip → 운영 가시화 무력화. 2 줄 교체 (`from src.engine import scanner as _scanner_mod; await _scanner_mod.emit_price_filter_scanner_daily_summary()`) + log prefix 갱신 + H-2 (scheduler 통합 가드 AST 정적) + G-3 (src/ 전체 폐기 메서드 호출 0건 AST 정적) 영구 가드 도입. **회귀 가드 28 케이스 (12 파일 분리, HIGH 8 = 29%)**: A system_config 단순화 4 (mode 인자 제거) + B scanner 필터 적용 5 + **C 보유/익일청산 보호 4 HIGH** (옵션 D 3 중 안전망) + D 60s TTL 캐시 2 (Q7-1 unsubscribe 0) + E DailyEmitCap 2 + F integration 4 (F-4 funnel step_no=98) + **G AST 2 HIGH** (G-1 risk.py 17 금지 문자열 0 + G-2 `protected_tickers` keyword 의무) + H daily_summary 1 + **H-2 scheduler 통합 가드 HIGH** + **G-3 폐기 메서드 src/ 전체 0건 AST HIGH** + C-Route 2 + F-FE 4 (mode 토글 폐기, 5 → 4). **백엔드 1944 → 1939 PASS** (사이클 62 폐기 34 케이스 + 사이클 64 신규 28 = 차이 -8, frontend 167 → 166). **사이클 38 명문화 영속**: scanner 단계 = 매수 진입 전용 (매도/익일청산/손절/15:20 강제청산 영향 0). **사이클 62 폐기 9 파일 git rm**: `test_cycle62_price_filter_*.py` (백엔드 33 케이스) + `PriceFilterCard.test.tsx::F-5 mode 토글` (1 케이스). UI: `PriceFilterCard.tsx` -88L (mode select 폐기) + 안내 배너 갱신 ("WebSocket 구독 대상 필터 — 임계 외 종목은 시세 구독 자체 차단. 보유/익일청산 종목은 절대 제외 안 됨").
- BUY 신호 발생 시 `state.signal_count_today += 1`

## market_regime.py

`dkstock.cloud` 매크로 기반 시장 레짐 + 매수 가드 + cash_usage_ratio 자동 조정.

- `MarketRegime` dataclass: regime / regime_desc / cycle_phase / vix / fear_greed_score / buffett_ratio / cash_min / raw
- `MarketRegime.empty()` — 외부 fetch 실패 graceful (`is_buy_allowed=True`)
- `MarketRegime.from_macro_cycle(macro)` — dkstock.cloud `/api/macro/macro-cycle` 응답 파싱
- `is_buy_allowed(strategy_id) -> bool` — 동기 회귀 가드 API
- **`get_buy_block_state() -> BuyBlockState` (async)** — 4 모드 분기. `BuyBlockState{mode, blocked, soft_multiplier, reasons}` 반환. DB 조회 실패 시 HARD + 기본 임계 fallback
- **`get_buy_block_state()` 60s TTL 인스턴스 캐시** — `_buy_block_cache` + `_buy_block_cache_expires_at` 필드(`compare=False, repr=False`). `BUY_BLOCK_CACHE_TTL=60.0`, `time.monotonic()` 비교. DB fetch 폴백 분기는 캐시 미저장. `invalidate_buy_block_cache()` 운영 토글 즉시 반영. 분당 ~1,800 DB 쿼리 → ~10 쿼리 (180배 감소)
- `to_advisor_dict()` 12 키 dict 반환 — AI 자문 user_payload 통합
- `cash_usage_ratio_from_regime(cash_min)` — `clamp((100 - cash_min)/100, 0.0, 1.0)`
- `refresh_from_dkstock()` — dkstock_client → MarketRegime. 모든 예외 흡수 → empty
- `persist_snapshot(regime, target_date)` — `market_regime_snapshots` 1행 INSERT
- `get_current_regime()` / `set_current_regime()` — 모듈 싱글톤
- 운영 graceful: `DKSTOCK_REGIME_ENABLED=false` 기본 → 외부 호출 0건, 매수 가드 비활성
- **DB 우선 토글**: `dkstock_client._check_enabled_async` + `mcp_client._check_enabled_async` + `backtest_engine.is_enabled_async()` 가 `system_config.get_*` 먼저 → DB True/False 채택, None / 예외 시 `settings.*` (.env) fallback. 매 호출마다 DB 조회 — Settings UI 토글 즉시 반영

`scheduler._boot()` 이 매크로 fetch + snapshot INSERT + `cash_usage_ratio` 자동 조정 통합.

## order_engine.py

매수/매도 실행 + 체결통보 처리 + DB positions 영속화.

매수 (`execute_buy`):
- **NXT 프리마켓 시장가 사전 차단 (preconvert)**: `place_order` 호출 *직전*, `MarketBoard.PRE_NXT in session_tracker.active` AND `MAIN not in active` AND `buy_exchange in ("NXT", "SOR")` 면 사전에 `step_up(current_price, 5)` 지정가로 변환. 변환 시 `state.pending_buy_amounts[ticker] = order_price × quantity` 동기 갱신, `record_price = order_price` 로 PENDING. INFO `[market_order_preconvert_pre_nxt]` 1행
- 진입 시 `is_buy_blocked()` + `is_low_funds_blocked(ticker)` 차단
- 매수가능 캐시 `BUYABLE_CACHE_TTL=60s` — KIS 호출 매 틱 → 분당 1회
- `max_buy_quantity<=0` 또는 `KisApiError(insufficient_cash)` → `block_buy(now+BUY_BLOCK_DURATION=900s)`
- `calc_buy_quantity()<=0` → `block_low_funds(ticker, now+LOW_FUNDS_COOLDOWN=900s)`
- **`is_market_order_disallowed` 거부 → 지정가 5호가 폴백 1회** — `step_up(current_price, 5)` + `LIMIT`. 매핑 동기 등록 + `_completed_orders` race 가드 + `insert_trade(PENDING, fallback_price)` 동기. 폴백 거부 시 cooldown
- 락/cooldown 은 다음 잔고 sync (15분) 에서 `unblock_buy()` + `clear_low_funds()` 일괄 해제

매도 (`execute_sell(..., limit_price=0)`):
- `_selling` set 중복 매도 차단
- `limit_price > 0` 이면 `LIMIT` + `exchange="NXT"` 강제. 0 이면 시장가 + 전략 `_strategy_exchange()` 라우팅. 호가단위 정렬은 호출자가 `util.tick_size.step_down` 책임
- `KisApiError(insufficient_quantity)` 시 3회 재시도 생략 + 즉시 break + 메모리/DB positions 정리
- **`is_market_closed_rejection(err)`** (장운영시간 외) → 재시도 중단 + `state.positions`·DB·`_selling` 보존 + 다음 거래 시각 자연 재트리거. NXT 시간대 거부면 `stock_master.upsert_one(ticker, nxt_tradable=False)` 사후 보강. **사이클 B-1 (2026-06-01) 진입 차단 이중 안전망** → **사이클 55 R-1 (2026-06-03) 2단계 TTL 로 갱신**: `SellRejectionTracker.register_market_closed(in_krx_main_hours=...)` 위임. KRX 메인(09:00~15:30) 거부 = 5분 TTL (일시 장애 가정), NXT 시간대 거부 = 다음 KST 09:00 TTL. `execute_sell` 진입 게이트에서 TTL 미경과 시 KIS 호출 없이 skip (INFO `[market_closed_blocked]` 1줄/ticker/일 cap, reason 필드 포함). `OrderEngine.reset_daily_state()` → `self._sell_rejection.reset_daily()` 5 필드 일괄 위임 (사이클 57 V-1: `_alarm_last_emitted` 추가) — `scheduler._reset_daily_state()` 위임 호출 보존. **사이클 57 V-1 (2026-06-04) 폭주 알람**: `_append_history` 단일 진입점에서 10분 윈도우 5건 초과 시 CRITICAL system_logs INSERT + 30분 per-ticker cooldown. 임계 상수: `ALARM_WINDOW_SECONDS=600 / ALARM_THRESHOLD=5 / ALARM_COOLDOWN_SECONDS=1800`. fire-and-forget (`asyncio.create_task`) — 매매 hot path 블로킹 0
- **`is_market_order_disallowed(err)` + `order_division==MARKET`** → 지정가 5호가 폴백 1회. `step_down(scanner.ticker_prices[ticker]["current_price"], 5)` + `LIMIT`. **사이클 55 R-1 (2026-06-03) 30초 TTL + NXT 익일 전환**: 폴백 결과(성공/실패) 무관 `SellRejectionTracker.register_market_order_disallowed(fallback_succeeded=...)` 위임 → 30초 TTL 등록 (동일 tick 폭주 차단). NXT 시간대 폴백 실패(`is_nxt_session=True, fallback_succeeded=False`) 시 `RejectionResult.next_day_clear_required=True` → `_pending_next_day_clear_provider().add((ticker, strategy_id))` + `[next_day_clear_deferred]` WARNING 1행. 폴백 실패 시 `_selling.discard` + positions 보존. 지정가 매도(`limit_price>0`)는 폴백 안 함. 키워드: `시장가호가불가` / `최유리/최우선지정가 주문만` / `지정가 및 최유리` (APBK1943 / APBK3013)
- **`is_insufficient_quantity(err)`** (보유 수량 부족) → 재시도 중단 + 메모리/DB positions 정리. **사이클 55 R-1 (2026-06-03) Q3 reconciliation**: `SellRejectionTracker.register_insufficient_quantity` history 적재(차단 X, positions 제거가 자연 차단) + `[positions_reconciliation]` INFO 로그 + `get_balance()` 1회 호출 (실제 잔량 > 0 이면 재등록 권고 로그). 실패 graceful

체결통보 race 가드:
- 주문번호 매핑(`_order_qty / _order_strategy / _order_ticker / _pending_buy_orders`)은 **`place_order` 응답 직후 동기 영역**, `await insert_trade` 진입 *전*
- `_completed_orders` set + `update_trade_status` 영향 row 0건 보정 INSERT — 체결통보가 REST 응답보다 먼저 도착해도 단일 COMPLETED row 보장

거래소 라우팅 (`exchange`):
- 모든 `place_order` / `cancel_order` 에 `_strategy_exchange(strategy_id)` 전달
- **NXT 거래가능 사전 차단**: `_strategy_exchange_async(strategy_id, ticker=...)` 가 `stock_master.get(ticker).nxt_tradable=False` 면 NXT/SOR → KRX 강제 다운그레이드 + `[nxt_downgrade]` 1행. 캐시 miss / 예외 시 전략 기본 exchange (보수적 fallback). 익일 청산 NXT 지정가(`limit_price>0`)는 사전 차단 적용 안 함. **사이클 54 (2026-06-03) — `[nxt_downgrade]` 로그 ticker별 1회/일 cap** (`_nxt_downgrade_logged_today: set[str]`). 다운그레이드 결정(return "KRX") 은 cap 밖 — 100회 호출 모두 정상 KRX 반환. `OrderEngine.reset_daily_state()` 동행 clear. 사이클 52 `_market_closed_blocked_logged_today` 와 동형 이중 안전망

체결 후처리:
- 매수 → DB `positions` 저장 + `cached_buyable_at=0` (가용액 캐시 무효화)
- 매도 → DB positions 삭제 + `sold_today` 등록. **사이클 15-A (2026-05-19) WS 구독 정리 hook** — `_unsubscribe_if_no_other_strategy(ticker)` 가 (a) `registry.is_ticker_held_by_any(ticker)=False` + (b) `_pending_next_day_clear` 부재 + (c) 모든 전략 `get_scanned_tickers()` 부재 — 모두 통과 시 `kis_ws_pool.unsubscribe(TICK_TR_ID, ticker)`. KIS 정상 패턴 "불필요 종목 구독해제" 즉시 적용. `_pending_next_day_clear_provider` 는 scheduler 가 `OrderEngine.__init__` 직후 주입 (lambda)
- 체결통보 처리 실패 안전장치: ticker 매핑 실패 → `pending_buys` 제거, strategy 미발견 → `_selling` 해제

퍼널 카운터: `place_order` 직전 `order_attempt_today += 1`, `_handle_buy_fill` 첫 체결 시 `fill_count_today += 1`

## session.py

`MarketBoard` enum: `pre_nxt` (08:00~) / `krx_open` (08:30~09:00) / `main` (09:00~15:20) / `krx_after` (15:30~18:00) / `post_nxt` (15:30~20:00).

- `_BOARD_SCHEDULE`: 시각 → 활성 보드 frozenset (H0NXMKO0 미수신 시 fallback)
- `SessionTracker.tick()`: `_session_loop` (scheduler 30s 주기) 에서 호출
- `is_tradable(strategy_id, params)`: 활성 보드 ∩ 전략 `tradable_boards` ≠ ∅
- `on_h0nxmko0(...)`: NXT 장운영정보 수신 (KIS 명세 미확정 → 코드 기록만)

## scheduler.py — KRX/NXT 통합 운영 08:00~20:00

시간 상수 (`scheduler.TIME_*`):

| 상수 | 시각 | 동작 |
|------|------|------|
| `TIME_AUTO_START` | 07:45 | DB `auto_start` 우선 폴백 자동 시작 |
| `TIME_BOOT` | 07:50 | `_boot()` (사이클 51 분해: 본체 `src/engine/boot_manager.py::boot(scheduler)` 위임 — 2 줄 wrapper. 외부 import 경로 영향 0) — `_preissue_all_tokens()` (사이클 20: 메인+보조 N 매니저 분당 1개 한도 직렬화 사전 발급) → DB positions 복구 → KIS 잔고 교차 검증 → 미체결 복구 → `_eager_refresh_stock_master_for_held_positions()` (보유 + 익일청산 후보 ticker 를 stock_master eager 갱신) → 매크로 fetch + `market_regime_snapshots` INSERT → `cash_usage_ratio` 자동 조정 → `allocate_funds(net_asset × ratio)` |
| `TIME_PRESUBSCRIBE` | 07:55 | `_collect_presubscribe_tickers()` — VB/LTV/donchian + 모든 전략 보유 합집합 사전 구독 |
| `TIME_PRE_NXT_OPEN` | 08:00 | 익일 청산 task (`_execute_next_day_clear`, `NEXT_DAY_STABILIZE_SECS=30s`). 사이클 26: VB/LTV PRE_NXT 매수 제거됨 — `_confirm_breakout_open_prices(board="pre_nxt")` 대상 없음 (tradable_boards=("main",)) |
| `TIME_KRX_MAIN_OPEN_PRESUBSCRIBE` | 08:59:10 | **사이클 26 신규**: KRX 채널(H0STCNT0) 사전 구독 마진 시작. `_board_transition_loop("H0NXCNT0","H0STCNT0", 보유+익일청산)` — 종목별 원자 전환 + 매수 후보 신규 subscribe |
| `TIME_KRX_OPEN_CONFIRM` | 09:00:05 | `_confirm_breakout_open_prices(board="main")` — VB/LTV가 KRX 09:00 시가로 target_price 계산. 직후 `_drain_pending_next_day_clear()` — 08:00 보류 종목 KRX 시장가 일괄 청산. 모두 이미 확정이면 idempotent skip |
| `TIME_SCAN_START` | 09:30 | 모멘텀 `scan_stocks()` + 통합 구독 |
| `TIME_KRX_MAIN_BUY_STOP` | 15:20 | `_force_clear_main_only` — VB/LTV tradable_boards=("main",) 이므로 POST_NXT 활성 0 → 전량 청산 |
| `TIME_KRX_MAIN_CLOSE` | 15:30 | KRX 메인 마감. 사이클 26: `_confirm_breakout_open_prices(board="post_nxt")` 제거 (VB/LTV tradable_boards 에 post_nxt 없음). 15:30~15:39:59 = MAIN 유지 (종가 흡수 마진) |
| `TIME_POST_NXT_OPEN_PRESUBSCRIBE` | 15:39:10 | **사이클 26 신규**: NXT 채널(H0NXCNT0) 사전 구독 마진 시작. `_board_transition_loop("H0STCNT0","H0NXCNT0", 보유+익일청산)` — 종목별 원자 전환 + 매수 후보 KRX unsubscribe |
| `TIME_POST_NXT_OPEN` | 15:40 | **사이클 26 신규**: NXT 애프터 진입 (기존 15:30 → 15:40 으로 변경). 매도만 (VB/LTV tradable_boards=("main",)) |
| `TIME_NXT_POST_BUY_STOP` | 19:50 | `buy_disabled = True` (NXT 애프터 신규 매수 중단, 변경 금지) |
| `TIME_NXT_POST_CLOSE` / `TIME_RECOMMENDATION` | 20:00 | `unsubscribe_all()` + `generate_recommendations()` — 동기 순차 (자문 ~3분, settlement 20:10 까지 7분 여유) |
| `TIME_SETTLEMENT` | 20:10 | `_settle()` → `generate_daily_log_report()` → **`purge_old_logs()`** (사이클 6 통합, 2026-05-20 — INFO 2일 / WARNING+ 30일 retention 자동 정리, 실패 graceful `[log_retention_skip]` INFO + 다음 사이클 재시도) → `_reset_daily_state()` (퍼널 카운터 초기화는 분석 *후*) |

기타:
- WebSocket 연결 직후 **체결통보 자동 구독** (실전 H0STCNI0+HTS ID / 모의 H0STCNI9+계좌번호) + 통합 장운영정보 `H0UNMKO0`/`005930` (실전 한정)
- `_load_strategy_config()`: DB `strategy_config` 에서 비중/`tradable_boards`/`exchange`/`k_value_*` 복구
- `run_daily()`: 주말+공휴일 건너뜀 (KIS `chk-holiday`), 매일 시작 전 DB auto_start 재확인
- `_scan_loop()` (5분 주기, 09:30~): VB+LTV+donchian + 모든 전략 보유 합집합 재구독. **사이클 15-A (2026-05-19) KIS 정상 패턴 준수**: 기존 `unsubscribe_all() → subscribe_filtered_stocks()` 전체 재구독 → `_delta_unsubscribe_dropped(new_set)` (빠진 종목만 unsubscribe) + `subscribe_filtered_stocks` (scanner LOW 분기에 `already_in_pool` 가드 추가로 이미 구독 중 종목 SEND skip). KIS 공지 "비정상 케이스 2" (무한 등록/해제) 패턴 차단. HIGH 종목 (positions/next_day_clear) 은 always 호출 — 풀의 `_select_session` promote 보존. 직후 `_reprepare_breakout_if_empty()` (사이클 48, 2026-05-27 — 대상 `volatility_breakout`/`long_tail_volatility`/`bull_flag_breakout`/`vcp_breakout`. BFB/VCP 는 boot 실패/일시 API 오류 회복 안전망 — 주 메커니즘은 prdy 시간무관 유니버스) + `_resubscribe_stale_priority(cap=10)` + `_report_tick_coverage()`. **사이클 25-B (2026-05-20) `_resubscribe_stale_priority` 우선순위 분리**: positions/next_day_clear 소속 stale → HIGH+bypass_limit=True (메인 절대 보장, 기존), 그 외 후보 stale → LOW+bypass_limit=False (보조 분산). 2026-05-20 14:58 VB/LTV 후보 8종목 stale→HIGH 메인 승격→메인 과부하→silent inactive 사고 대응. 사이클 24 자동 reconnect 와 이중 안전망
- **사이클 17 (2026-05-19) — 사이클 15-B/C 전체 롤백**: `_near_signal_loop` + `stream_pool_manager` + `near_signal_monitor` + `settings.near_signal_mode` + `_build_priority_groups` 분기 + `_near_signal_task` 멤버 + `GET /api/realtime/stream-status` + 프론트 `StreamStatus` 메뉴 모두 제거. 단순화 원칙(단일 데이터 경로 + 신규 모듈 추가 금지) 위반 + 60s `_near_signal_loop` 와 `_scan_loop`/K stale watcher race → KIS `OPSP0002` 폭주 → tick_coverage 0% 결함(2026-05-19 15:15 사고). `_build_priority_groups` 는 항상 momentum/breakout 정상 list 반환. WS 등록 경로 = `_scan_loop` 5분 delta 단일. OPSP0002 차단은 `_handle_raw` 의 backoff (`_opsp_backoff_until`) 로 단순 흡수
- **사이클 17 보강 (2026-05-19) — KIS 공식 답변 반영**: 1) `_check_and_resubscribe_stale` 의 1~5회 `pool.resend_subscribe_for_ticker` (같은 종목 재SEND) 분기 완전 폐기 → 첫 stale 즉시 `pool.unsubscribe_in_pool` + `pool.subscribe(HIGH, bypass_limit=True)` 강제 재등록 (KIS 정상 "신규 등록" 패턴). 2) OPSP0002 backoff 60s → 300s 연장 — `_scan_loop` 5분 주기 ≥ backoff 만료 보장. KIS 인용: "기 요청된 목록 관리하여 기등록한 사항을 재등록하지 않도록 (다수 요청 시 LMS + 앱정보 이용중지)". `MAX_STALE_RETRIES=5` 신규 상수 — 6회 이상 stale skip (영구 stale 의심)
- `_stale_watcher_loop()` (`_check_and_resubscribe_stale`, 120s 주기): `kis_ws_pool.get_subscribed_tickers()` 합집합 vs `scanner.ticker_last_tick` 비교. `STALE_FRESHNESS_SECS=60s` 초과면 stale, 종목별 `_stale_retry_count` 누적. **사이클 17 보강 (2026-05-19) — KIS 공식 답변 ("기등록한 사항을 재등록하지 않도록") 반영**: 1~5회 `pool.resend_subscribe_for_ticker` (같은 종목 재SEND) 분기 완전 폐기 → 첫 stale 즉시 `pool.unsubscribe_in_pool` + `pool.subscribe(priority='HIGH', bypass_limit=True)` 강제 재등록 (KIS 정상 "신규 등록" 패턴, 재SEND 0건). 6회 이상 (`> MAX_STALE_RETRIES=5`) → 사이클 28 *전*: skip / **사이클 29-R1 (2026-05-21)**: 시간 기반 force_retry — `STALE_FORCE_RETRY_AFTER_SECS=300` (5분) 경과 또는 `_stale_last_resubscribe_at` 부재 시 강제 재등록 + `_stale_retry_count[ticker]=0` 리셋 + `_stale_force_retry_history` (60분 슬라이딩 윈도우) 등록. `STALE_FORCE_RETRY_HOURLY_CAP=12` 초과 시 `[stale_force_retry_cap]` WARNING skip. 영구 stale 무한 skip 결함 차단. **사이클 29-R3 (2026-05-21) — K stale watcher 양쪽 분기 우선순위 분리**: `high_tickers` = `registry.all()` positions ∪ `_pending_next_day_clear` 합집합. `ticker in high_tickers` → HIGH+bypass=True (메인 절대 보장), 그 외 → LOW+bypass=False (보조 분산). 사이클 28 실측 main=25/보조 합 9 편중 73% → R3 후 main=2/보조 합 34 편중 5%. F1(재연결 1회) + `_scan_loop`(5분) + K(120s) + `_resubscribe_stale_priority`(5분 우선) 4중 안전망. **사이클 24 (2026-05-20) — 세션 단위 silent inactive 감지 + 강제 reconnect**: K stale watcher 가 종목별 재등록 외에 세션 자체 결함도 5분 지속 후 `_force_reconnect_session(label)` 으로 `_ws.close()` 발화 → 재연결 자동 발화. **사이클 29-R2 (2026-05-21) 정의 완화**: `fresh==0` → `fresh_ratio < SILENT_INACTIVE_FRESH_RATIO_THRESHOLD(=0.2, 20%)` + `subscribed_count >= 5` + 5분 지속 3중 가드. 시간당 2회 cap (LMS / 앱 정지 위험 차단) 보존. 사이클 28 실측 메인 fresh=2/25=8% 결함 자동 감지. **사이클 28 (2026-05-21) — 추적 강화**: `_stale_last_resubscribe_at: dict[str, datetime]` 신규 + `[stale_watcher_detail] session=main sub=22/41 fresh=8 stale=14 ratio=0.64 stale=[(009150,r=3,@09:12:45), ...]` 신규 prefix (종목 cap 20 + overflow `...+N`). 기존 `[stale_watcher]` / `[stale_priority_resubscribe]` 보존.
- **`_refresh_stale_ccnl_cache(stale_tickers, cap=20)` (사이클 37, 2026-05-21)**: stale r≥2 종목 대상 `quotation.inquire_ccnl` 호출 + `_last_ccnl_cache: dict[ticker, dict]` 갱신. TTL 5분 + cap 20 + 종목 간 50ms sleep + 보유 종목 우선 처리 + KIS None/예외 graceful 캐시 미저장. `_scan_loop` (5분 주기) 통합 + `_reset_daily_state` 동행 clear. R4 universe guard 와 race 무해 (TTL 자동 차단). `/api/realtime/subscriptions` 의 `tickers_detail.last_cntg_hour / today_volume` 응답 데이터 소스.
- **`_evaluate_universe_guard(candidate_tickers)` (사이클 32 R4, 2026-05-21)**: stale>5 + `today_volume < UNIVERSE_LOW_VOLUME_THRESHOLD(=10_000)` 종목 자동 universe 제외. 사전 가드 (보유/익일청산/이미 제외/stale≤5 → KIS 호출 자체 skip) + `inquire_ccnl` 호출 + `_universe_excluded_today.add()` + `kis_ws_pool.unsubscribe()` + `[universe_excluded] ticker=... reason=stale_6plus_low_volume retries=... last_resub_age=...s last_cntg_hour=... today_volume=...` INFO + system_logs 영구. `_collect_breakout_tickers` 필터링 + `_scan_loop` 5분 주기 통합 + `_reset_daily_state` 동행 clear (영구 블랙리스트 금지).
- **사이클 60 Phase 2-A1 (2026-06-04) — `stale_manager.py` 신규 모듈 추출**: 5 함수 (`_build_session_subscription_view` / `_emit_stale_session_detail` / `_refresh_stale_ccnl_cache` / `_evict_expired_ccnl` / `_prune_force_retry_history`, scheduler.py 의 ~275L) + 5 상수 (`MAX_STALE_RETRIES` / `STALE_FORCE_RETRY_AFTER_SECS` / `STALE_FORCE_RETRY_HOURLY_CAP` / `UNIVERSE_LOW_VOLUME_THRESHOLD` / `SILENT_INACTIVE_FRESH_RATIO_THRESHOLD`) 모두 stale_manager.py 로 이전. **사이클 51 boot_manager 패턴 답습** (scheduler 인자 + 2 줄 wrapper 위임). **행위 변경 0** (refactor) + **5 상수 re-export 호환** (`is` 동일성). **logger 명시 binding**: `logging.getLogger("src.engine.scheduler")` — 사이클 28 회귀 가드 (`caplog.set_level(logger="src.engine.scheduler")`) + 운영 logging config 호환 보존 (`__name__` 사용 시 `[stale_watcher_detail]` 운영 로그 누락 위험). property 7 쌍 (`_stale_retry_count` / `_stale_last_resubscribe_at` / `_last_ccnl_cache` 등) layer 보존 — `src/routes/realtime.py:88-91` `getattr` 호환. scheduler.py 3,880 → 3,605L (−275L, −7.1%). K stale watcher 핵심 (`_check_and_resubscribe_stale` 221L + `_resubscribe_stale_priority` 100L) 은 scheduler.py 잔류 (Phase 2-A2 사이클 61 / 2-A3 사이클 62 분리 예정).
- **사이클 61 Phase 2-A2 (2026-06-05) — `stale_manager.py` 4 함수 + 5 상수 추가 이주**: `_detect_silent_inactive_sessions` (62L, 사이클 29-R2 silent inactive 3중 가드) + `_force_reconnect_session` (83L, 사이클 24 세션 강제 reconnect, **KIS LMS/앱키 정지 위험 직접 영역**) + `_delta_unsubscribe_dropped` (52L, 사이클 15-A delta 패턴) + `_evaluate_universe_guard` (117L, 사이클 32 R4 보유/익일청산 보호) = **314L**. 추가 5 상수: `STALE_FRESHNESS_SECS=60` (사이클 17) + `SILENT_INACTIVE_MIN_SUBSCRIBED=5` / `SILENT_INACTIVE_PERSIST_SECS=300` / `SILENT_INACTIVE_RECOVERY_CAP_PER_HOUR=2` / `SILENT_INACTIVE_RECOVERY_WINDOW_SECS=3600` (사이클 24/29-R2). 누적 9 함수 + 10 상수 (사이클 60 A1 5+5 + 사이클 61 A2 4+5). scheduler.py 3,605 → 3,315L (−290L). stale_manager.py 358 → 731L. **사이클 60 lazy import 빚 청산**: `_build_session_subscription_view` 의 `from src.engine import scheduler as _sched_mod` 1 줄 제거 (`STALE_FRESHNESS_SECS` 이전으로 자연 해소). **`sys.modules.get("src.engine.scheduler")` 패턴**: `detect_silent_inactive_sessions` / `force_reconnect_session` 에서 `kis_ws_pool` / `kis_ws` / `datetime` 접근 시 scheduler 네임스페이스 우선 참조. D-1 AST 가드 통과 (정적 import 0) + 테스트 patch 호환 (`patch("src.engine.scheduler.kis_ws")`) + 운영 환경 동일 객체. **회귀 가드 20 케이스 (12 파일 분리)**: A 위임 4 + B 5 상수 동일성 + **C cap dict `is` 동일성 (HIGH)** + D 의존성 역전 정적 + E reset_daily 동행 + F dataclass 7 필드 누락 가드 (2 케이스) + G silent inactive cap freezegun + H 5분 지속 freezegun + **I universe guard 보유 보호 (HIGH)** + **J universe guard 익일청산 보호 (HIGH)** + K delta unsubscribe race best-effort + L import sanity. **백엔드 1862 → 1882 PASS** (+20, 회귀 0). 누적 scheduler.py 라인 감소: 사이클 51 직전 ~4,185 → 사이클 61 후 3,315 (**−870L, −21%**). **A3 (사이클 63) 잔여 2 함수**: `_check_and_resubscribe_stale` 221L + `_resubscribe_stale_priority` 100L = K stale watcher 핵심 — *주말 push 의무 + 월요일 첫 _boot 1h tester verify*.
- **사이클 66 (2026-06-06) — `_resubscribe_stale_priority` cap=10 결함 시정 (카드 #5 HIGH, 사이클 63 K-2 발견)**: 사이클 63 발견 결함 영속 시정. **결함 (사이클 63 K-2 PASS = 결함 confirm)**: `stale_manager.py:1023-1034` `targets = stale_tickers[:cap]` 가 priority 분리 *전* `[:cap]` 적용 → HIGH 종목 (보유/익일청산) 이 sorted LOW 후보에 밀려 cap 밖 잘림 가능 → 5분 우선 재구독 누락 → KIS LMS chain 사고 위험 (사이클 29 005935 사고 패턴). **시정 (사이클 66 K-2 = 시정 confirm 의미 전환)**: ~22L 교체 — Q1 priority 분리 *먼저* (`high_targets = [t for t in stale_tickers if t in high_tickers]` / `low_targets = [t for t in stale_tickers if t not in high_tickers]`) + Q2 try/except 4중 가드 통일 (본체 `_check_and_resubscribe_stale` 답습 — `for s in registry.all()` outer try + inner positions try + NDC try) + Q3 HIGH > cap 모두 보장 + `logger.warning("[stale_priority_resubscribe_cap_exceeded] ...")` (운영 가시화) + 최종 `targets = high_targets + low_targets[:max(0, cap - len(high_targets))]`. **회귀 가드 11 케이스 (단일 파일 `tests/unit/engine/stale_manager/test_cycle66_resubscribe_cap_priority_fix.py`, HIGH 4)**: K-2 시정 confirm (Q6-4 docstring 의미 전환 명시) + K-3 HIGH 12 > cap=10 모두 통과 + K-4 HIGH 5 후반 + LOW 20 정확 분리 + K-5/K-6/K-7 LOW 영속 + **K-8 registry 예외 try/except 4중 (Q2)** + K-9 HIGH 0 + LOW 0 early return + **K-10 WARNING 발화 (Q3)** + **AST 정적 가드** (`stale_tickers[:cap]` 잔존 0건 + `low_targets[:max(...)]` 패턴 1건). **사이클 63 K-2 의미 전환**: `tests/unit/engine/test_cycle63_phase2A3_priority_cap.py::test_K2` 에 `@pytest.mark.xfail(strict=False)` 마킹 — 사이클 63 시점 결함 confirm 영속 보존 (호환), 사이클 66 시정 완료로 자동 XFAIL 전환. **백엔드 1975 → 1984 PASS + 1 XFAIL** (+9 신규 PASS + 1 의미 전환 XFAIL) / 회귀 0 / coverage 80.95% (+0.02%). **사이클 29 005935 사고 패턴 영구 차단** (HIGH 종목 cap 밖 잘림 8분 영구 잔류 + KIS LMS chain 차단). **사이클 38 명문화 영속** (시세 영역 — 매도/익일청산/손절 영향 0). **무변경 영역 (회귀 가드)**: `sys.modules.get` 패턴 (사이클 61 D-1 AST) / `kis_ws_pool.subscribe(priority, bypass_limit)` 인터페이스 / `_stale_last_resubscribe_at` 갱신 / `asyncio.sleep(0.05)` Rate Limit / `[stale_priority_resubscribe]` INFO + `write_log` fire-and-forget / `high_tickers` ↔ `bypass_limit` 매핑 (HIGH=True / LOW=False) / 함수 시그너처. **월요일 (2026-06-09) 09:00~10:00 1h tester verify 시나리오 D 신규** (Q5 자문): HIGH 인위 stale 주입 보유 0 종목 + 신규 측정 지표 3 (HIGH 5분 우선 재구독 보장률 100% / WARNING 발화 빈도 / HIGH 회복 시간 ≤5분) — 시나리오 A/B/C/D 결합 효과 측정. domain-expert 자문 옵션 A 전부 (Q1~Q5 + Q6-1~Q6-6) 7 사이클 연속 패턴 일관 (사이클 55 R-1 / 60 / 62 / 63 / 64 / 65 / 66).
- **사이클 78 (2026-06-08) — 사이클 74 도입 누락 silent 결함 시정 (flush 호출 사이트 0건 + 메모리 leak 영구 차단)**: 사이클 78 C 진단 (Supabase READ-ONLY) 결과 = `[swing_rest_poll_summary]` + `[stale_watcher_summary]` 영구 0건 확정. **근본 원인**: 사이클 74 commit (`0017fe0`) 가 `record_swing_rest_poll` + `flush_swing_rest_poll_collector` + `record_stale_watcher_check` + `flush_stale_watcher_collector` 함수 도입했으나 *5분 주기 호출 사이트 누락* + 사이클 76 commit (`0d633a8`) 가 `_api_recovered_collector_loop` task 도입했으나 *swing/stale flush 도 함께 호출 누락* → collector 무한 누적 (메모리 leak HIGH) + summary 영원히 emit 0건. **시정 (옵션 1 = 사이클 76 task 재사용, +26L)**: `scheduler.py::_api_recovered_collector_loop` (L2469~L2480 영역) 본체에 `flush_stale_watcher_collector` import 추가 + swing/stale flush 4 줄 (try/except 각각) + `if not self._running: break` 를 flush 블록 *이후*로 이동 (sleep 후 무조건 1회 flush 보장, 사이클 42 답습) + `scheduler.py::stop()` lifecycle hook 양쪽 flush try/except (Q5 사이클 74 답습, `unsubscribe_all()` 직전 잔여 카운터 손실 방지). **회귀 가드 6 케이스 (3 파일)**: G-FL1~FL4 flush 호출 사이트 (각 collector ≥1건 + lifecycle hook + 5분 task co-located) + G-ML1 메모리 leak 차단 (5분 윈도우 종료 후 `len == 0`) + **G-AST1 영구 가드** (`record_*` 정의 모듈의 대응 `flush_*` 호출 사이트 ≥1건, 미래 신규 collector 추가 시 flush 호출 누락 영구 차단). 백엔드 2083 → 2089 PASS (+6) + 1 XFAIL + 2 skip / flakiness 0 / 회귀 0. **C 진단 부차 확정**: `[swing_rest_poll]` 개별 마지막 14:09:27 KST (사이클 74 배포 14:13 KST 이전) + `[stale_watcher]` 개별 마지막 14:08:57 KST = 모두 배포 후 emit 0건 = 사이클 74 collector 흡수 정상 작동 확정 = **카드 #19 (realtime_other 16.13x, 사이클 73 인계) 거짓 알람 종결**. **부차 발견 카드 #20 (LOW)**: `stop()` task cancel 목록 (L860~865) 에 `_api_recovered_collector_task` 누락 (좀비 task 위험, 운영 중 `_running=False` → loop 자연 종료로 즉각 위험 낮음, 본 사이클 범위 외). 17 사이클 연속 옵션 A 패턴 영속 (55 R-1 / 60 / 62~69 / 72~78). silent 결함 영구 차단 13 회 누적
- **사이클 74 (2026-06-08) — WebSocket 로그 sampling/aggregation 옵션 E-1/C 도입 (카드 #19 인계, refactor-expert 자문 6 카드 #A/#B 채택)**: 사이클 71/73 운영 실증 dup_factor 잔존 영역 (`[swing_rest_poll]` 5.00x / `[stale_watcher]` 3.00x / WS 구독·ACK·해제 logger.info 빈도) 5분 윈도우 1행 aggregation 흡수. **신규 모듈 헬퍼**: `stale_watcher_core.py` +51L (`record_stale_watcher_check(stats)` + `flush_stale_watcher_collector()` 모듈 전역, `[stale_watcher_summary] checks=N stale_total=M retried=K cap_blocked=L force_retried=J` 1행 emit, **결함 시 (`stale_count > 0`) `[stale_watcher_detail]` individual 영속** + 사이클 66 K-10 `[stale_force_retry_cap]` / `[stale_priority_resubscribe_cap_exceeded]` WARNING individual 영속) + `scheduler.py` +42L (`record_swing_rest_poll(stats)` + `flush_swing_rest_poll_collector()`, `[swing_rest_poll_summary] polls=N candidates_avg=X max=Y total_held=Z elapsed_ms_avg=W` 1행 emit). `_run_swing_rest_poll_once` (L2319) + `check_and_resubscribe_stale` (L237) 직접 `logger.info(...)` 제거 + collector 흡수. **AST 영구 가드 G-7/G-8 신설**: G-7 (`_send_subscribe` 직접 logger.info 0건) + G-8-A (`_run_swing_rest_poll_once` 영역 한정) + G-8-B (`check_and_resubscribe_stale` 영역 한정). **회귀 가드 9 케이스 (engine 영역)**: G-SP1~SP4 swing_rest_poll aggregation freezegun (5분 윈도우 / 통계 정확 / window reset / shutdown flush, Q5 옵션 A) + G-SW1/SW2/SW5 stale_watcher aggregation + G-SW3 `[stale_watcher_detail]` individual 영속 + G-SW4 `[stale_force_retry_cap]` WARNING 영속 (사이클 66 K-10). 운영 효과 예상: `[swing_rest_poll]` ~720/day → 144/day (~80% 감소) + `[stale_watcher]` ~360/day → 144/day. **사이클 17/29 LMS chain 차단 영속** (collector 흡수만, `_opsp_backoff_until` 등록 행위 변경 0) + **사이클 38/55 R-1/66/67 매매 안전성 영역 영향 0** (로깅 영역 시정만, ERROR/WARNING individual 보존 매트릭스 영속). 신규 모듈 헬퍼 = 영역별 격리 (Q3 옵션 A 채택, 사이클 76+ shared 헬퍼 추출 #20 인계). flush 주기 5분 (사이클 42 `HEARTBEAT_METRICS_INTERVAL_SECS=300` 답습, Q4 옵션 A).
- **사이클 67 (2026-06-06) — `stale_manager.py` 1,099L 4 sub-module + facade 96L 분해 (카드 #14 MEDIUM 종결, refactor #2 후속)**: domain-expert 옵션 A 자문 (Q1~Q5 + Q6-1~Q6-3) 전부 적용 (**8 사이클 연속 패턴 영속**) + **Q4 유일 불일치 채택** (옵션 B facade patch 영속, 자문 실측 `patch("src.engine.stale_manager.*")` = 0건 강력 권고). **분해 매트릭스**: `stale_diagnostics.py` 357L (5 함수 + 4 상수 — `build_session_subscription_view` / `emit_stale_session_detail` / `refresh_stale_ccnl_cache` / `evict_expired_ccnl` / `prune_force_retry_history`) + `stale_session_recovery.py` 274L (3 함수 + 5 상수 — `detect_silent_inactive_sessions` / `force_reconnect_session` / `delta_unsubscribe_dropped`) + `stale_universe_guard.py` 157L (1 함수 + 1 상수 — `evaluate_universe_guard`) + `stale_watcher_core.py` 399L (2 함수 — **K stale watcher 본체 HIGH hot path** `check_and_resubscribe_stale` 222L + `resubscribe_stale_priority` 100L). facade `stale_manager.py` 96L (`__all__` 21 항목 re-export only — 11 함수 + 10 상수). `scheduler.py` 11 wrapper L2435~L2501 + 5 상수 re-export L92 **변경 0** (Q5=A `from src.engine import stale_manager` lazy import 영속). **Q1=A facade** (단일 진입점 보존, 사이클 51 boot_manager 답습) / **Q2=P1 모듈-레벨 정적 import** (`stale_watcher_core.py:30-36` `from src.engine.stale_diagnostics import emit_stale_session_detail` 모듈-레벨, 함수-레벨 lazy import 비채택) / **Q3=A 4 sub-module 모두 `logger = logging.getLogger("src.engine.scheduler")` 명시** (사이클 60 I1 영속 — `caplog set_level(logger="src.engine.scheduler")` 호환) / **Q4=B facade patch 영속** (자문 실측 0건 → 갱신 의무 사실상 0, G-16 AST 신설로 silent 결함 영구 차단) / **Q5=A wrapper 변경 0** (`from src.engine import stale_manager; await stale_manager.X(self)` 패턴 영속). **Q6 채택**: Q6-1 (LOW) hot path import 캐시 측정 권고 / Q6-2 (MEDIUM) 사이클 71+ 옵션 B 헬퍼 청사진 (3 헬퍼 ~75L: `_sched_mod_get` / `_collect_high_tickers` / `_write_log_fire_and_forget`) / Q6-3 (MEDIUM) 사이클 68+ 시점 분리 권고 (사이클 67 push → 1 주 운영 → 사이클 68+ #16 후보 풀 폭축 회고 → 1 주 운영 → 사이클 71+ #15 액면분할). **사이클 29 005935 사고 영역 영속**: G-15 WARNING (`[stale_priority_resubscribe_cap_exceeded]` `stale_watcher_core.py:346-357`) + G-17 priority 분리 *후* cap AST. **사이클 66 시정 영속**: G-11 `high_targets`/`low_targets` 변수명 + G-12 try/except 4중. **회귀 가드 17 케이스 (6 파일, HIGH 6 = 35%)**: G-1~G-5 분해 검증 (5 — 4 sub-module 파일 존재 + 11 함수 + 10 상수 export + facade 21 `__all__`) + G-6~G-9 의존성+logger (4 — Q3 4 sub-module 동일 logger AST + Q1 단방향 의존 AST + Q2 모듈-레벨 정적 import AST + Q5 facade lazy import AST) + G-10~G-13 사이클 63+66 영속 (4 — Q4=B 직접 호출 + 사이클 66 변수명 + try/except 4중 + caplog 일관성) + G-14~G-15 사이클 60+64 영속 (2 — 폐기 메서드 0건 + 사이클 29 WARNING) + **G-16 facade patch 안전선 신규** (1 — `tests/unit/engine/` rglob `patch("src.engine.stale_manager.X")` → X facade export 검증) + **G-17 priority 분리 *후* cap 신규** (1 — `resubscribe_stale_priority` AST 정적 가드). **백엔드 1985 → 2002 PASS + 1 XFAIL** (+17 신규) **+ 2 skipped**. `tests/unit/engine/stale_manager/` 27 PASS / `tests/unit/engine/` 1,162 PASS + 1 XFAIL. flakiness 0 (3 회 `stale_manager/` 0.24~0.39s / `engine/` 36.34~36.56s, ±0.5%). 회귀 0 / 매매 안전성 무영향 (행위 보존 + 외부 인터페이스 0 + scheduler.py 변경 0). **누적 scheduler.py 감소** (사이클 51 직전 ~4,185 → 사이클 67 후 3,007 영속): **−1,178L, −28%**. **patch 경로 적응 3 건**: `test_C1` (`test_cycle60_phase2A1_stale_manager.py:227`) `patch.object(stale_manager, "evict_expired_ccnl")` → `patch("src.engine.stale_diagnostics.evict_expired_ccnl")` (본체 동일 모듈 네임스페이스 직접 호출 → facade patch 비효과) + `test_D2` (`test_cycle63_phase2A3_dependency_direction.py:64`) 단일 파일 grep → `stale_watcher_core.py` + `stale_session_recovery.py` 합산 grep (총 6건 ≥ 4 충족) + `test_cycle66_resubscribe_cap_priority_fix.py` 일부 적응. **G-12 라인 cap 마진 (정보, 결함 아님)**: `stale_watcher_core` 실측 399L (권고 ≤380L 대비 5% 초과) — 본체 라인 단위 보존 (행위 보존 의무 우선) + Q1/Q2/Q3 시정 모두 보존 결과. 후속 사이클 71+ Q6-2 헬퍼 분리 시 추가 압축 가능. **무변경 영역**: 함수 본체 라인 단위 + 시그너처 (`emit_stale_session_detail(scheduler, ...)` Q4=B 답습) + 상수 값 (cap=10 / SILENT_INACTIVE_* / UNIVERSE_*) + `sys.modules.get("src.engine.scheduler")` 패턴 (`stale_watcher_core` 3건 + `stale_session_recovery` 3건 = 6건, 사이클 61 D-1 AST) + try/except 4중 (사이클 66 Q2) + 운영 prefix 전수 (`[stale_watcher_detail]` / `[stale_priority_resubscribe]` / `[stale_priority_resubscribe_cap_exceeded]` / `[stale_force_retry]` / `[silent_inactive_*]` / `[universe_excluded]`) + WebSocket 4중 안전망 호출 시점/횟수 0 + silent inactive 시간당 세션당 2회 cap + universe 가드 보유/익일청산 절대 보호. **월요일 (2026-06-09) 09:00~10:00 1h tester verify 의무** (시나리오 A 자연 monitoring + B 인위 stale 주입 보유 0 + C KIS LMS chain 차단 + D HIGH 인위 stale — 사이클 67 분해 후 운영 hot path 첫 노출 검증).
- **사이클 63 Phase 2-A3 (2026-06-06) — `stale_manager.py` K stale watcher 핵심 2 함수 추가 이주 (HIGH, refactor #2 완료)**: `_check_and_resubscribe_stale` (222L, **K stale watcher 본체** — 사이클 17 보강 1~5회 즉시 강제재등록 + 사이클 29-R1 6회 초과 force_retry 5분 cooldown + 시간당 12회 cap + 사이클 29-R3 HIGH/LOW 우선순위 분리) + `_resubscribe_stale_priority` (100L, 사이클 25-B 5분 우선 재구독 분리). 합 322L. 누적 9 → **11 함수**. 추가 상수 0 (사이클 60+61 누적 10 상수 모두 이전 완료). **K stale watcher = 영구 hot path 360 회/일 + KIS LMS/앱키 정지 chain 직접 영역** — domain-expert §Q7 본질 차이 인지 별도 자문 (옵션 A 전부 적용). **Q4=B 직접 호출** (사이클 60 A1 답습하지 않는 *유일 영역*): `check_and_resubscribe_stale` 본체가 `_emit_stale_session_detail` 호출 시 `self.*` wrapper 우회 → `emit_stale_session_detail(scheduler, ...)` 모듈 함수 직접 호출 (1 hop 단축 + 사이클 61 `_refresh_stale_ccnl_cache` → `evict_expired_ccnl` 패턴 일관). **Q2 try/except 4 중 가드 보존** (`getattr` 폴백 silent 실패 위험으로 비채택). **사이클 29 005935 사고 패턴 차단 영속** (T+0 stale → T+18min 8 분 영구 잔류 + KIS LMS chain) — H 4 케이스 freezegun 재현 PASS. scheduler.py 3,315 → 3,007L (−308L). stale_manager.py 731 → 1,076L (+345L). **누적 scheduler.py 감소** (사이클 51 직전 ~4,185L → 사이클 63 후 3,007L): **−1,178L, −28%**. **회귀 가드 29 케이스 (12 파일)**: A 위임 4 (A-1 HIGH = Q4=B 직접 호출 검증) + C property 호환 3 + D AST 의존성 역전 2 + E reset_daily 동행 2 + F dataclass 누락 2 + **G 1~5회 강제재등록 3 HIGH** + **H 6회 초과 force_retry 4 HIGH (freezegun)** + **I 우선순위 분리 3 HIGH** + J history 60분 윈도우 2 (freezegun) + K cap=10 영역 2 + L caplog logger 1 + M import sanity 1. **HIGH 11 (38%) 전수 PASS**. **백엔드 1915 → 1944 PASS** (+29, 회귀 0). 기존 patch 경로 수정 2 파일 (`test_scheduler_stale_force_retry.py` + `test_scan_loop_stale_priority.py` — A3 이주 후 `src.db.system_logs.write_log` 추가 patch). **사이클 64+ 후속 카드 (tester 발견)**: **카드 #5 (HIGH)** Q5-3 cap=10 결함 영속 (K-2 PASS = 결함 confirm — `_resubscribe_stale_priority` L2748 `targets = stale_tickers[:cap]` priority 분리 *전* 적용 → HIGH 종목 cap 밖 잘림 가능) — 시정 안: priority 분리 *후* HIGH 먼저 + LOW 잔여 cap. **카드 #14 (MEDIUM)** Q5-2 stale_manager.py 1,076L sub-module 분해 (3+1 청사진: `stale_diagnostics` ~350L / `stale_session_recovery` ~250L / `stale_universe_guard` ~150L / `stale_watcher_core` ~322L). **월요일 (2026-06-09) 09:00~10:00 1h tester verify 의무** (시나리오 A 자연 monitoring + B 인위 stale 주입 보유 0 종목만 + C KIS LMS chain 차단 monitoring) — 사이클 60 §Q7 영속 의무.
- `_sync_orders_to_db(orders)`: KIS 주문체결내역(`get_daily_orders`) → trade_history 동기화. MTS/HTS 수동 매매분 반영. 중복 판정 키 `(ticker, order_no)` 페어
- `_sync_positions_from_balance()`: 15분 주기. strategy 매핑은 trade_history 직전 BUY 행에서 상속. 종료 시 `unblock_buy()` + `clear_low_funds()` 일괄 해제
- `_execute_next_day_clear()`: 다음 영업일 NXT 프리 시가 수신 후 30s 안정화 → 갭률 트레일링 또는 NXT 지정가 매도. 시가 미수신이면 `_pending_next_day_clear` set 보류. `stock_master.nxt_tradable=False` 가 1순위 판별 → 즉시 보류 등록 (NXT 주문 0건)
- `_drain_pending_next_day_clear()`: `_confirm_breakout_open_prices(board="main")` 직후 호출. `_pending_next_day_clear` 종목 KRX 시장가 일괄 청산
- 구조화 로그: `[next_day_clear_deferred] ticker={t} strategy={s} reason={nxt_not_tradable|nxt_open_missing}` / `[next_day_clear_drained] ticker={t} strategy={s} result={success|fail} elapsed_ms={ms}`
- `_reset_daily_state()`: 전략별 positions/pending_buys/sold_today + OrderEngine 추적 상태 + scanner 글로벌 dict (`ticker_last_tick.clear()` 포함) + `_pending_next_day_clear.clear()` + `_stale_retry_count.clear()` 전체 초기화

## scanner.py

- `scan_stocks()`: 모멘텀 등락률 순위
- `subscribe_filtered_stocks(tickers, extra_tickers, source_counts=None, *, priority_groups=None)`: 합집합 구독
  - `priority_groups` 분기: `kis_ws_pool.subscribe(tr_id, t, priority='HIGH'|'LOW', bypass_limit=...)` 위임. `positions`/`next_day_clear` → HIGH + `bypass_limit=True` (메인 절대 보장), `breakout`/`momentum`/`swing` → LOW + `bypass_limit=False` (보조 라운드로빈 우선, 보조 가득 시 메인 fallback)
  - **2-pass**: 1차 `breakout[:BREAKOUT_LOW_CAP=25]` + momentum + swing 잔여 슬롯 add → 2차 `MAX - len(_subscriptions) > 0` 면 breakout overflow 흡수 add. 최종 drop = `max(0, len(overflow) - absorbed_overflow)`. drop>0 시 `[priority_drop]` INFO + WARNING `system_logs`. 중복은 HIGH 1회만, HIGH 단독 41 초과 시 ERROR
  - `source_counts` dict 전달 시 `[scanner] 실시간 시세 구독 완료: total=N (vb=A, ltv=B, swing=C, momentum=D, positions=E)` 노출 (영문 라벨 — Grafana/Loki 안정성)
  - 평탄 처리 분기 (`priority_groups=None`)는 기존 `kis_ws.subscribe` 직접 호출 보존
- `KOSPI_200_TICKERS` / `KOSDAQ_150_TICKERS`: donchian_swing 고정 유니버스
- `STATIC_TICKER_NAMES` / `_parse_static_ticker_names()`: 모듈 import 시 자기 파일을 정규식으로 파싱 → 종목명 dict. KIS `inquire-price` 빈 응답 대비 보강
- 공용 데이터: ticker_names, ticker_prices, ticker_prev_close, ticker_market_info, **ticker_last_tick** (`risk.on_tick` 호출 시 KST `datetime` 갱신)
- **`get_scan_status()` 풀 전체 카운트**: `kis_ws_pool.get_subscribed_tickers()` / `get_acked_tickers()` 합집합 위임. `tick_coverage_total/acked/fresh/stale` 4 키 + 기존 `subscribed_count` 보존. `/api/trading/status` `scan` 필드 동봉 → ScanMonitor stale 색상 배지 + 진행바

## log_analysis_engine.py — 일일 로그 분석

20:10 정산 직후 `generate_daily_log_report(_now_kst=None)` 호출. 호출 *후* run loop가 `_reset_daily_state()` 별도 실행 (퍼널 카운터 보존). `_now_kst` 파라미터는 테스트용 현재 시각 override — None 이면 `datetime.now(KST)` 사용.

당일 KST 00:00~now `system_logs` + `trade_history` → OpenAI → `daily_log_reports` INSERT.

데이터 수집 구현 사양 (사이클 53 B-2/B-4 시정):
- **`_fetch_logs_in_range(start, end, limit=5000)`**: Supabase PostgREST default 1000 페이지 한도 회피를 위해 `.range(offset, offset+999)` 루프. `limit` 은 *총* 한도 (limit=5000 → 최대 5페이지). 빈 페이지 또는 <1000건 페이지 도달 시 종료. `.limit(N)` 단독은 서버가 1000으로 강제 cap 함 — 반드시 `.range()` 루프 사용.
- **사이클 53.1 — 호출 측 limit=30000 명시**: `generate_daily_log_report` 의 `_fetch_logs_in_range` 호출에 `limit=30000` 명시. 운영 부피 18,000건/일 대비 1.6배 마진 확보. 디폴트 5000 으로는 drained(ASC 7,000+번) 누락 결함 차단.
- **`get_trades_in_range`**: start/end ISO 에 `+09:00` KST timezone 명시 (`src/db/trade_history.py`). TZ 없는 문자열은 PostgREST 가 UTC 해석 → KST 00:00~09:00 거래 누락 결함.

확장 메트릭:
- `api_metrics`: `api/base.py::get_request_metrics()` (5xx/4xx/network/retries + path별 5xx top 5). INSERT 후 `reset_request_metrics()`
- `strategy_funnel`: 전략별 `{signals, orders, fills}` (registry 순회)
- `trades.by_ticker_pnl` (SELL PnL 절대값 top 5) / `trades.by_hour_pnl` (KST hour별)
- `next_day_clear`: `{deferred, drained_success, drained_fail}` (구조화 로그 prefix 정규식)

출력 스키마: `{summary, findings: [{category, severity, title, detail, suggestion}]}`. `(target_date)` UNIQUE. OpenAI 타임아웃 60s, 실패 시 메트릭만 보존 INSERT.

## recommendation_engine.py / recommendation_metrics.py — 20:00 AI자문

- 전략별 metrics(승률/평균손익/손절률/누적수익률) → OpenAI → `parameter_recommendations` INSERT (status: pending)
- `(target_date, strategy_id)` UNIQUE
- `/api/recommendations/{id}/apply`: 사용자 키 선택 적용 → `strategy_config.params` 갱신 + status applied/partial
- `expire_pending_before(target_date)`: 이전 영업일 pending 자동 만료
- `_validate_recommendations()` 5-tuple 반환 `(validated_params, reasoning, weight, notes, weight_reasoning)`
- user_payload 에 `current_weight` + `peer_weights` + `peer_metrics` + `market_regime` 12 키 추가
- `apply_weight=true` 옵션 → `save_weights({sid: w})` + `strategy.config.weight` 메모리 반영 + `applied_weight` 트래킹. `allocate_funds()` 즉시 재호출 금지 (다음 _boot 반영)
- `PARAM_RANGES` 화이트리스트 (자동 튜닝 대상): `k_value_krx_main`/`k_value_nxt_pre` `(0.5, 2.0)` (VB, LTV) + `stop_loss_main`/`stop_loss_pre_nxt` `(-15.0, 0.0)` + `donchian_period` `(10, 60)` + `long_ma_period` `(20, 120)` + `volume_multiplier` `(1.0, 5.0)` + `atr_trail_mult` `(1.0, 5.0)` + `min_prdy_rate` + **사이클 23**: VCP 4 키 (`base_depth_pct`/`volume_contraction_ratio`/`breakout_volume_mult`/`last_pullback_max`) + P2 신규 5 키 (`breakout_retention_minutes`/`breakout_fail_n_days`/`max_breakout_extension_pct`/`box_contraction_period`/`max_box_volatility_pct`)
- `INT_PARAMS`: `donchian_period` / `long_ma_period` / **사이클 23**: `breakout_retention_minutes` / `breakout_fail_n_days` / `box_contraction_period`
- **사이클 23 P3-1+2 `auto_apply_recommendations(target_date)` (신규 함수)**: 20:00 AI 자문 직후 자동 적용. 감액만 + 50% cap + 보수적 파라미터 (`_CONSERVATIVE_KEYS`) 자동 적용. `auto_apply_enabled=False` 시 즉시 disabled 반환. `[auto_weight_apply]`/`[auto_params_apply]`/`[auto_apply_skip_increase]`/`[auto_apply_safeguard_skip]` 4종 영구 로그. `status='applied_auto'` (수동 'applied' 와 분리). scheduler `TIME_RECOMMENDATION` 직후 호출. **사이클 36 hotfix (2026-05-21)**: scheduler.py:542 호출부에 `from src.engine.scanner import KST_TZ as _AUTO_APPLY_KST_TZ` import + `datetime.now(_AUTO_APPLY_KST_TZ).date()` 사용 (이전엔 `KST` 미정의 NameError 로 매일 20:00 자동 적용 실패). `backtest_engine.poll() / wait_for_result()` 의 `pending` status 도 `running` 동일 처리 (이전엔 unknown 분기 → ExternalAPIError → `backtest_runs status=failed` 잘못 기록)
- `recommendation_metrics._normalize_stop_loss_rate(params)`: 5 키 후보(`stop_loss_rate`/`intraday_stop_loss`/`overnight_stop_loss`/`stop_loss_main`/`stop_loss_pre_nxt`) → 음수만 → `min(candidates)` 반환 (가장 보수적). LTV 분리 키 흡수 + VB 보드별 키 운영
- SYSTEM_PROMPT 끝에 매크로 컨텍스트 활용 가이드 — defensive/neutral/aggressive 분기 + `buy_blocked=True` 시 매수 임계 변경 권고 무용 + `weight_reasoning`/`code_review_notes` 에 매크로 영향 명시 권장
- VIX 분류 `_classify_vix()` 임계 15/25/35 (low/normal/elevated/high). Fear & Greed 분류 `_classify_fear_greed()` 임계 15/35/65/85
- `weight_reasoning` (≤1000자, 한국어, 통합 `reasoning` 과 별개). `weight=None` 이면 자동 정리, `weight` 있는데 사유 누락 → `WEIGHT_REASONING_FALLBACK="(사유 미제공)"` + WARNING

## 절대 깨지면 안 되는 규칙

- 체결통보(H0STCNI0/9) 구독 제거 금지 — 미구독 시 포지션 등록 불가 → 손절 불가
- uvicorn 단일 워커 필수 (`--workers` 금지)
- 매수 신호는 반드시 "돌파 순간" 감지 (이전 틱 < 기준가 AND 현재 틱 ≥ 기준가)
- 익일 청산은 scheduler에서 시가 수신 후 30s 안정화 (`_next_day_clear_pending` 전략 가드 + `_pending_next_day_clear` scheduler 보류 set) — on_tick 즉시 청산 금지
- 익일 청산 갭률은 반드시 `ticker_prices[ticker]["open_price"]` (WebSocket 시가) — `high_since_buy` 폴백 금지. 시가 미수신이면 `_pending_next_day_clear` 보류 후 09:00 KRX 시장가
- NXT 프리/애프터 매도 거부 (`is_market_closed_rejection`) 시 `execute_sell` 이 `state.positions`·DB·`_selling` 보존 + NXT 시간대 거부면 `stock_master.upsert_one(ticker, nxt_tradable=False)` 사후 보강. **사이클 B-1 진입 차단 → 사이클 55 R-1 2단계 TTL**: `SellRejectionTracker.is_blocked()` 진입 게이트. KRX 메인(09:00~15:30) 거부 = 5분 TTL, NXT 시간대 거부 = 다음 KST 09:00 TTL. `market_order_disallowed` = 30초 TTL, NXT 폴백 실패 = 익일 청산 큐 등록. `_reset_daily_state` 동행 `_sell_rejection.reset_daily()` 위임 필수. 호환 layer property `_market_closed_blocked` / `_market_closed_blocked_logged_today` 유지
- 매수 시장가 거부 (`is_market_order_disallowed`) → `step_up(current_price, 5)` 지정가 1회 폴백
- 매도 시장가 거부 (`is_market_order_disallowed`) + `order_division==MARKET` → `step_down(current_price, 5)` 지정가 1회 폴백. 폴백 실패 시 cooldown 등록 안 함 + positions 보존 (청산 의무, 다음 사이클 재트리거). 지정가 매도는 폴백 안 함
- 주문번호 매핑 등록은 **`place_order` 응답 직후 동기 영역**, `await insert_trade` 진입 *전*
- 체결통보 선행 race 가드 (`_completed_orders` + UPDATE 0건 보정 INSERT) 매수·매도 양쪽 필수
- `BUYABLE_CACHE_TTL=60s` / `BUY_BLOCK_DURATION=900s` / `LOW_FUNDS_COOLDOWN=900s` ↔ sync 주기(15분) 정합성 — 변경 시 sync 종료 시 일괄 해제 동작 보존
- `Position` 에 `strategy_id` 필수 (체결통보 → 올바른 전략 라우팅)
- `position_ratio`는 **전략 할당 자금 기준** (순자산 × 전략비중 × position_ratio)
- TR_ID 는 `settings.get_tr_id()` 사용
- `_confirm_breakout_open_prices` 보드 경계 정각 호출은 `board=...` 명시 의무 — 08:00 `pre_nxt` / 09:00:05 `main` / 15:30 `post_nxt`. SessionTracker race 차단
- VB `DEFAULT_TRADABLE_BOARDS` 에 POST_NXT 추가 금지 — 당일 15:20 일괄매도 정책 위반 + OVERNIGHT 자연 보유 결함
- donchian_swing `_swing_rest_poll_loop` 제거 금지 — 09:30~15:20 60s REST 폴링으로 멀티데이 보유 손절 평가 보강
