# RS · 재무 · 목표가 리비전 — 2단계 명세 (적재 배선 + 4전략 관찰 기록)

> 출처: 2026-10-13 22:5x KST 사용자 승인 「2단계 승인 · 5시간 자율 진행 · 승인요청 없이 진행 · 자세한 보고」.
> 1단계 = `2026-10-13_rs_fundamental_phase1.md` + `_amend1.md`(동결). 사전 등록 성공 기준은 1단계 문서 그대로다.

## 설계 원칙 — 승인 대상 파일을 건드리지 않는다

- `scheduler.py`(3,898줄, 상한 `< 3,900`) · `scanner.py`(8영역) · 전략 파일 · `strategy_base.py` · `DEFAULT_PARAMS` **무접촉**.
- 적재는 이미 매일 16:40 에 도는 재무 적재 task(`data_load_tasks.stock_master_financial_load_task_loop`)에 **얹는다** — `once_callable` 을 「기존 연간 적재 → 추가 적재」 를 차례로 부르는 합성 함수로 바꾼다. 새 task·새 시각 상수·`scheduler.py` 0줄.
- 관찰 기록은 매매 행위 0 — 주문·수량·신호·후보 목록·전략 상태를 읽기만 하고 바꾸지 않는다. 전략 파라미터 키 대신 `system_config` 킬스위치를 쓴다(`account_cluster_mode` 선례).

## A. 추가 적재 — `src/engine/fundamental_load_tasks.py` (신규)

공개 = `async run_extra_loads_once(*, now_kst=None) -> dict`(never-raise, `CancelledError` 만 전파). 세 갈래를 차례로 돌고 각 갈래는 독립 `try`.

1. **분기 재무**(`div_cls="1"`) — 유니버스 = 연간 적재와 같은 `stock_master.list_by_filter(...)` 자격(코드 공유: scanner 의 상수 `_DAILY_LOAD_MIN_MCAP_EOK`·`_DAILY_LOAD_MIN_TRADE_WON` 을 **읽기만** import). 종목마다 `stock_master_financial.max_stac_yymm(ticker, div_cls="1")` 이 `target_quarter(today)` 이상이면 skip, 아니면 `finance.fetch_all_financials(ticker, div_cls="1")` → `upsert_financial_batch`. `target_quarter(today)` = 분기말(03·06·09·12) 중 `분기말 + 45일 <= today` 인 가장 최근 것의 `YYYYMM`(순수 함수). 종목 간 `asyncio.sleep(0.05)`.
2. **투자의견**(`FHKST663300C0`) — 주 1회(`system_config` 마커 `fundamental_opinion_load_last` 가 7일 이내면 갈래 전체 skip). 종목마다 DB 최신 `bsop_date` 를 보고, 없으면 오늘−400일부터, 있으면 그 다음 날부터 오늘까지 **90일 창으로 나눠** `inquire_invest_opinion` → `upsert_opinions`. 응답 100건 = 잘림 경고(래퍼가 남김) — 그 창을 반으로 나눠 1회 재시도.
3. **추정실적 월 스냅샷**(`HHKST668300C0`, 실전 전용) — 이번 달(`snapshot_month` = 그 달 1일)에 행이 있는 종목은 skip. 대상 = 같은 유니버스. 빈 응답은 저장하지 않는다(커버리지 약 160종목).

- 킬스위치 `system_config.fundamental_extra_load_mode` — 키 없음 = `on`, `off` = 세 갈래 전부 skip, 그 밖 = `on` + WARNING. 매 실행 시작에 읽는다.
- 요약 `[fundamental_extra_load] quarterly_total= quarterly_fetched= quarterly_skipped= quarterly_failed= opinion_tickers= opinion_rows= opinion_skipped= estimate_saved= estimate_skipped= elapsed_ms= mode=` 1행 INFO(실패가 하나라도 있으면 WARNING).
- 전체 상한 `EXTRA_LOAD_HARD_CAP_SECS = 3000`(50분) — 넘으면 남은 종목은 다음 실행으로 미루고 `truncated=1`.
- **배선**: `data_load_tasks.stock_master_financial_load_task_loop` 의 `once_callable` → `_financial_load_with_extras(force=False)` = `summary = await scanner._stock_master_financial_load_once(force)` 다음 `try: await fundamental_load_tasks.run_extra_loads_once() except Exception: logger.exception(...)` → `summary` 반환(연간 요약 키·로그 서식 불변). 연간 적재 실패가 추가 적재를 막지 않게 연간 쪽 예외도 감싼 뒤 다시 올린다(기존 graceful 계약 유지).

## B. 관찰 기록 — `src/engine/rs_fundamental_observe.py` (신규) + migration 052

### 테이블 `candidate_score_snapshots` (가산형 신규)

PK `(target_date, strategy_id, ticker)`. 칸:
- `role` TEXT(`candidate` | `held`) · `rs_raw` DOUBLE · `rs_pct` INT · `sector_key` TEXT · `vs_sector` DOUBLE · `sector_pct` INT · `in_sector_pct` INT
- `revision_breadth` DOUBLE · `target_median_change` DOUBLE · `opinion_brokers` INT
- `fin_quarter` TEXT(그때 알 수 있던 최신 분기 YYYYMM) · `op_income_q` DOUBLE · `op_income_q_yoy` DOUBLE · `op_turnaround` BOOL · `op_yoy_growth` DOUBLE · `revenue_yoy_growth` DOUBLE · `net_turnaround` BOOL · `roe` DOUBLE · `debt_ratio_latest` DOUBLE · `debt_ratio_down_years` INT · `ttm_op_to_max_ratio` DOUBLE
- `rs_population` INT · `computed_at` TIMESTAMPTZ NOT NULL
- 모든 점수 칸 NULL 허용(「모름」 = NULL, 0 으로 채우지 않는다).

### 흐름 — `spawn_boot_observe(scheduler) -> asyncio.Task | None`

- 대상 전략 = `("donchian_swing", "vcp_breakout", "kojiro", "etf_trend")` 중 레지스트리에 있고 켜진 것.
- 배선 = `boot_manager.boot()` 의 `account_cluster.spawn_boot_assign(...)` 바로 뒤 `try/except Exception` 블록 1개(await 없음).
- 태스크: 최대 `WAIT_PREPARE_SECS=600` 동안 10초 간격으로 대상 전략마다 `_live_prepare_meta`(`ok is True ∧ phase == "boot"`) 를 기다린다(못 기다린 전략은 `[rs_observe] strategy= skipped=prepare_not_done`).
- 입력(쿼리 몇 번으로 일괄):
  - RS: `stock_master_daily` 에서 `bas_dd < 오늘` 최근 200봉 종가 — 새 db 함수 `src/db/score_inputs.py::recent_closes_bulk(before, n=200)`(창 함수 1쿼리). 모집단 = 190봉 이상 있는 전 종목 → `rs_score.ibd_lite_return` → `percentile_ranks`.
  - 섹터: `stock_master.master_raw` 로 `strategies.kojiro._kojiro_sector_key(master_raw, ticker)`(읽기 전용 import) → `rs_score.sector_relative`.
  - 목표가: `invest_opinion.get_opinions(ticker, 오늘−400일, 오늘−1일)` → `fundamental_score.target_revision_breadth` / `target_median_change`(as_of = 어제).
  - 재무: `stock_master_financial` 분기·연간 행 → `known_as_of(as_of=오늘)` → `quarterly_from_cumulative` → 최신 분기와 4분기 전 비교(`turnaround_flags`), 매출 YoY, 순이익 흑자전환, TTM 영업이익(최근 4분기 합) ÷ 과거 TTM 최댓값(가용 범위), 연간 `lblt_rate` 최근 3개 중 감소 횟수. ROE = `stock_master.master_raw.roe`(숫자로 읽히면).
- **etf_trend** 는 재무·목표가 칸이 NULL 이고, RS 는 같은 전역 모집단 백분위를 쓴다(ETF 가 일봉 적재 대상이 아니면 NULL). 같은 기초지수 묶기는 3단계(관찰 판독 때).
- 대상 종목 = 그 전략 `get_scanned_tickers()`(후보) ∪ 그 전략 `state.positions` 키(보유, `role=held`).
- 쓰기 = 새 db 모듈 `src/db/candidate_scores.py::upsert_scores(rows)`(executemany, PK 충돌 = 덮기). 하루 1회(부팅). 재기동하면 같은 날 다시 쓴다(덮기라 멱등).
- 킬스위치 `system_config.rs_fundamental_observe_mode` — 키 없음 = `record`, `off` = 안 돈다, 그 밖 = `record` + WARNING.
- 마커 `[rs_observe] strategy= candidates= held= rs_known= fin_known= opinion_known= rs_population= elapsed_ms=` 전략당 1행 INFO + 실패 `[rs_observe_failed] stage=` WARNING. 전체 상한 `RUN_TIMEOUT_SECS=300`.
- 🔴 never-raise · 전략 객체에 쓰지 않는다 · `src.api` 호출 0(KIS 0 — DB 만) · 8영역·`scheduler` import 0.

## C. 가드

- AST: 새 모듈 3개(`fundamental_load_tasks.py`·`rs_fundamental_observe.py`·db 2개)의 import 에 8영역·`scheduler`·`src.realtime`·`src.auth` 0 · `rs_fundamental_observe.py` 에 `src.api` import 0 · 전략 객체 속성 대입 0.
- `scheduler.py`·`scanner.py`·전략 파일·`strategy_base.py` git diff 0.
- `test_cycle287_ast_scope.py` 파일 수 핀 갱신(정당한 추가).
