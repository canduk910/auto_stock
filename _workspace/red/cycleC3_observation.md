# 사이클 C3 (2026-07-15) — 퀀트 재무필터 관찰 전용 배포 (Red 메모)

승인 계획: `~/.claude/plans/partitioned-kindling-lollipop.md` (C3 절).
C1(재무 인프라: `stock_master_financial.py` + `finance.py` + base.py 화이트리스트) ·
C2(계산 모듈: `quant_score.py`) Green 완료.

## C3 = **관찰 전용 (Phase 1)**. 매매 로직 diff 0.

- momentum = 어느 사이클에서도 매매 로직 변경 0 (검증 +47K 알파 보존). C3 스코어 노출조차 안 함 (오프라인 유의성 검정).
- VB 관찰 훅 = `quant_filter_enabled=False` (기본) → 스코어 계산·funnel 노출만, **배제 0**.
- Phase 2(C4, VB F-Score ≤1 배제 활성)는 유의성 검정 통과 시에만 발주.

## 산출물 4개 (production — backend-dev Green 대상)

### (a) `src/engine/scanner.py::_stock_master_financial_load_once(force=False)` 신규 함수 (추가만)
`_stock_master_daily_load_once` 답습.
- 유니버스 = `stock_master.list_by_filter`(index∪시총500억&거래20억, 사이클 206) — daily load 와 동일 856 종목.
- 각 ticker: `max_stac_yymm` 신선도 skip (당분기 이미 적재 시) → `fetch_all_financials` → `upsert_financial_batch`.
- graceful (개별 실패 continue) + `[stock_master_financial_load_summary] total=N updated=K skipped=L failed=M` emit.
- `refresh_progress.py` TaskKey `"financial"` 추가 (현재 4키 → 5키, `TASK_KEYS` tuple + `Literal` 동행).
- **scan_stocks / subscribe_filtered_stocks / 매수 발사 경로 diff 0 byte** — 순수 추가 함수.

### (b) `src/engine/scheduler.py` — 주1회 재무 적재 task lifecycle
- `TIME_STOCK_MASTER_FINANCIAL_LOAD = time(16, 40)` 상수 (master 16:30 후 stagger).
- `_stock_master_financial_load_task_loop` — `run_periodic_task_loop` 재사용 + `initial_delay_secs=900`(master 720 후) + `immediate_skip_if_fresh_hours=168`(7일, 사이클193).
- 주1회 신선도 게이트: `immediate_skip_if_fresh_hours=168` (7일 미경과 시 immediate skip).
- **task_attrs 4위치 (사이클79 G-AST2)**: instance create + connect finally cancel tuple + run_daily finally cancel tuple + stop() tuple.
- `test_scheduler_stop_zombie_tasks.py::expected_members` +1 (`_stock_master_financial_load_task`, 17종 → 18종).

### (c) `src/engine/strategies/volatility_breakout.py::_apply_quant_filter_in_prepare()` 관찰 훅 (배제 0)
`_apply_price_filter_in_prepare`(사이클148) 미러. `_scan_universe`→master_block(사이클157) **다음** 단계 삽입.
- `DEFAULT_PARAMS`: `quant_filter_enabled=False`(기본 OFF), `quant_min_f_score=0`, `quant_max_mf_rank=0`.
- **관찰 모드(enabled=False)**: 후보별 `get_financial_series(ticker, div_cls="0", limit=2)` 2기 로드 →
  `compute_f_score_7(curr, prev)` + `compute_magic_formula(series_by_ticker, mktcap_by_ticker)` (유니버스 시총 `hts_avls_eok`) →
  **funnel step 에 스코어 기록만, 배제 0** (전체 통과).
- 보유 절대보호(`_collect_protected_tickers_for_scanner`, 사이클32 R4) + 결측 통과(fail-open, f_score=None/series 부족 → 통과).
- `VB_FUNNEL_STAGES` +1단계 (step_no=7, "퀀트 재무 게이트(관찰)"). 기존 6단계 → 7단계.
- `_record_funnel_pipeline_step`(사이클170 in-place upsert).
- **PARAM_RANGES 미편입** (`recommendation_engine.py` diff 0 AST).

## Red 가드 매트릭스

### 파일 1 — `tests/unit/engine/test_cycleC3_financial_load_task.py`
scanner load 함수 + scheduler task lifecycle + refresh_progress TaskKey.
- LOAD-1 (HIGH): `_stock_master_financial_load_once` 유니버스 = list_by_filter 재사용 (index∪자격) → fetch_all_financials 호출.
- LOAD-2: `max_stac_yymm` 신선도 skip (당분기 이미 적재 → skipped++, fetch 미호출).
- LOAD-3: graceful — 개별 ticker fetch 예외 → failed++ + 다음 ticker 진행 (사이클88).
- LOAD-4: `[stock_master_financial_load_summary]` emit + summary 키 (total/updated/skipped/failed).
- LOAD-5: `upsert_financial_batch` 호출 (fetch 성공 시).
- **G-3 (HIGH SAFETY, AST)**: `scan_stocks` / `subscribe_filtered_stocks` 본체 diff 0 — 신규 함수만 추가. (재무 로직이 scan_stocks 에 인젝션되지 않았음 = momentum 발사 경로 byte-identical.)
- TASKKEY-1: `refresh_progress.TaskKey` / `TASK_KEYS` 에 `"financial"` 포함 (5키).
- SCHED-1 (AST): `TIME_STOCK_MASTER_FINANCIAL_LOAD = time(16, 40)` 상수.
- SCHED-2 (AST): `_stock_master_financial_load_task_loop` = `run_periodic_task_loop` 위임 + `immediate_skip_if_fresh_hours=168` + `initial_delay_secs=900`.
- SCHED-3 (AST, G-AST2): task_attrs 4위치 (`_stock_master_financial_load_task` = create + connect finally + run_daily finally + stop tuple).
- ZOMBIE-1: `test_scheduler_stop_zombie_tasks.py::expected_members` +1 (18종) — 여기서는 stop tuple 에 `_stock_master_financial_load_task` 포함 검증 (기존 zombie 테스트 갱신은 Green 동반).

### 파일 2 — `tests/unit/engine/strategies/test_cycleC3_vb_quant_filter_observe.py`
VB 관찰 훅 (배제 0).
- **G-2 (HIGH) OBSERVE-1**: `quant_filter_enabled=False`(기본) → 전체 통과 (배제 0). 입력 N 종목 == 출력 N 종목.
- OBSERVE-2: 스코어 계산 (get_financial_series 2기 로드 → compute_f_score_7 + compute_magic_formula 호출).
- OBSERVE-3: funnel step (step_no=7) 스코어 기록 — `_record_funnel_pipeline_step` 호출.
- FAILOPEN-1 (결측 통과): series 부족(1기 이하) → f_score=None → 통과 (배제 0).
- FAILOPEN-2: get_financial_series 예외 graceful → 통과.
- PROTECT-1 (사이클32 R4): 보유 종목 무조건 통과 (스코어 무관).
- PARAM-1 (AST): DEFAULT_PARAMS `quant_filter_enabled=False` / `quant_min_f_score=0` / `quant_max_mf_rank=0`.
- FUNNEL-1: `VB_FUNNEL_STAGES` 7단계 (step_no=7 "퀀트 재무 게이트(관찰)").
- HOOK-ORDER (AST): `_apply_quant_filter_in_prepare` 가 master_block **다음** 호출 (prepare 순서).
- **G-1 (HIGH SAFETY, AST)**: 매매 로직(check_buy_signal / check_exit_signal) 본체 diff 0.
- SAFETY-2 (AST): `_apply_quant_filter_in_prepare` 영역 check_exit_signal 호출 0건 + risk/order_engine import 0.
- **PARAM-RANGES (AST)**: `recommendation_engine.py` PARAM_RANGES 에 quant 키 미편입 (diff 0).

## 매매 안전성 8영역
scanner.py = 8영역이나 사이클38 "매수 진입 전" 만 허용 → **scan_stocks/subscribe/매수 발사 경로 diff 0 AST 가드 필수** (신규 load 함수만 추가).
`git diff -- src/engine/risk.py src/engine/order_engine.py src/realtime/ src/auth/ src/api/order.py src/engine/session.py src/engine/strategy_registry.py` = 0.

## freeze_time 안 DB read mock 의무 (사이클187 hang)
prepare/load 테스트는 `get_financial_series`/`fetch_all_financials`/`list_by_filter` mock. freeze_time 미사용 (async sleep 동결 hang 회피).

## Red 실행 결과 (production 미구현 상태)
- 파일 1: `_stock_master_financial_load_once` 부재 → AttributeError FAIL. TaskKey `"financial"` 부재 FAIL. SCHED AST 상수/함수 부재 FAIL. G-3(scan_stocks diff 0)/ZOMBIE-1(stop tuple)은 현 상태 PASS (불변식 — 아직 인젝션 안 됨) → Green 후에도 유지되어야 하는 SAFETY 불변식.
- 파일 2: `_apply_quant_filter_in_prepare` 부재 → FAIL. DEFAULT_PARAMS quant 키 부재 FAIL. VB_FUNNEL_STAGES 6단계 (7단계 아님) FAIL. G-1/SAFETY-2/PARAM-RANGES 는 현 상태 PASS (불변식) → Green 후 유지 의무.

## Green 인계
- scanner 신규 함수는 **순수 추가** — 기존 함수 편집 금지 (G-3 diff 0).
- VB 훅은 `filtered` 반환 시 배제 0 (관찰 모드) — 발사 로직 무변경.
- zombie 테스트 expected_members 18종 갱신은 Green 동반 (본 Red 는 stop tuple 포함만 검증).
