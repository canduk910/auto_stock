# cycle M1-2 (Red) — Supabase→RDS 이전, M1 증분 2 (4 저의존 모듈)

승인 계획: `~/.claude/plans/partitioned-kindling-lollipop.md` (단계 1, 증분 2).
선행: M0(`src/db/pg.py`) Green · M1-1(`positions`/`strategy_config`) Green.

## 대상 4 모듈 (저의존·비 hot-path)

| 모듈 | 테이블 | 특수 계약 |
|---|---|---|
| `src/db/log_reports.py` | `daily_log_reports` (target_date UNIQUE) | JSONB `findings`/`metrics` · DECIMAL cost_estimate_usd · UNIQUE upsert(중복 None) |
| `src/db/backtest_runs.py` | `backtest_runs` ((target_date,strategy_id,params_kind) UNIQUE) | JSONB `params_snapshot`/`metrics` · 복합 UNIQUE(중복 None) · update_status |
| `src/db/market_regime_snapshots.py` | `market_regime_snapshots` (snapshot_date UNIQUE) | JSONB `raw_response` · NUMERIC vix/fg/buffett/ratio · UNIQUE(중복 None) |
| `src/db/pending_next_day_clear.py` | `pending_next_day_clear` (복합 PK (target_date,ticker,strategy_id)) | ⚠️ 익일청산 큐(매매 안전성) · 복합 PK upsert · set 반환 계약 |

## M1-1 확정 필수 패턴 (전 모듈 적용)

1. **JSONB 쓰기**: SQL 은 `$N::jsonb` 캐스트 + 바인딩은 `json.dumps(dict)` (codec 은 read 전용).
   - 단위: `pg.execute`/`pg.fetch` args 에 `json.dumps(...)` 문자열 또는 dict 바인딩 단언.
   - 통합: 왕복 후 **dict 반환** 단언(codec 실증 = 계획 3대 리스크 1순위).
2. **TIMESTAMPTZ 쓰기**: asyncpg str 바인딩 불가 → 호출부 `datetime.fromisoformat(now_kst_iso())` 로
   **datetime 변환 후 바인딩** (`now_kst_iso()` 문자열 계약은 보존 — SQL 인자만 datetime).
   - 단위: `created_at`/`completed_at` 바인딩 인자가 `datetime` 인스턴스인지 단언.
3. **TIMESTAMPTZ 읽기**: str 계약 필요 시 `to_char(ts,'YYYY-MM-DD"T"HH24:MI:SS+09:00')`.
   본 4 모듈은 조회 결과의 시각 컬럼을 호출부가 직접 파싱하지 않고 dict pass-through(라우트 JSON
   직렬화) → 왕복 통합에서 created_at 존재만 확인(계약 최소, 사이클53 `+09:00` 캐스트는 Green 재량).
4. **함수 계약(시그니처·반환형·graceful) 100% 보존** → 호출부 diff 0.

## 함수별 전환 SQL (대표 키워드) + 계약 불변식

### log_reports.py
- `insert_log_report(*, target_date, summary, findings, metrics, model, input_tokens=…, …, cost_estimate_usd=None)`
  → `INSERT INTO daily_log_reports (...) VALUES (...$N::jsonb...) RETURNING *`
  → 반환: 삽입 dict | None. **UNIQUE(target_date) 충돌 → None** (기존 `duplicate key`/`23505` 분기).
  - `findings`/`metrics` JSONB 바인딩 · `cost_estimate_usd` Decimal→float · `created_at` datetime.
- `list_log_reports(days=30)` → `SELECT * ... ORDER BY target_date DESC LIMIT $1` → list[dict] (0건 []).
- `get_log_report(target_date)` → `SELECT * ... WHERE target_date = $1 LIMIT 1` → dict | None.

### backtest_runs.py
- `insert_run(target_date, strategy_id, params_kind, params_snapshot)`
  → 사전 중복 SELECT(`WHERE target_date=$1 AND strategy_id=$2 AND params_kind=$3`) 존재 시 None
  → `INSERT INTO backtest_runs (...) VALUES (...$N::jsonb...) RETURNING *`.
  → `params_kind` in {current,recommended} 아니면 `ValueError` (본체 검증 보존).
  → UNIQUE 충돌(race) `duplicate/unique/23505` → None. INSERT 실패 → None(graceful).
  - `params_snapshot` JSONB · `id` uuid · `created_at` datetime.
- `get_by_id(run_id)` → `SELECT * ... WHERE id=$1 LIMIT 1` → dict | None.
- `list_by_date(target_date)` → `SELECT * ... WHERE target_date=$1` → list[dict].
- `update_status(run_id, status, *, mcp_job_id=None, error_message=None, metrics=None)`
  → `UPDATE backtest_runs SET status=$…[, mcp_job_id=…][, metrics=$N::jsonb][, completed_at=$…] WHERE id=$… RETURNING *`
  → status 부적합 `ValueError`. 적용 row 0건 → `{}`. metrics JSONB · completed_at datetime(completed/failed/skipped).

### market_regime_snapshots.py
- `insert_snapshot(snapshot_date, regime, …, raw_response, …, buy_blocked, block_reason)`
  → 사전 중복 SELECT(`WHERE snapshot_date=$1`) 존재 시 None
  → `INSERT INTO market_regime_snapshots (...) VALUES (...$N::jsonb...) RETURNING *`.
  → UNIQUE 충돌 → None. INSERT 실패 → None(graceful). `raw_response` JSONB · NUMERIC 컬럼 float.
- `get_by_date(snapshot_date)` → `SELECT * ... WHERE snapshot_date=$1 LIMIT 1` → dict | None (except graceful None).
- `get_latest()` → `SELECT * ... ORDER BY snapshot_date DESC LIMIT 1` → dict | None (except graceful None).
- `list_recent(days=30)` → `SELECT * ... ORDER BY snapshot_date DESC LIMIT $1` → list[dict] (except graceful []).

### pending_next_day_clear.py  ⚠️ 매매 안전성(익일청산 큐)
- `save_pending_ndc(target_date, ticker, strategy_id, reason="unknown")` → None
  → `INSERT INTO pending_next_day_clear (target_date,ticker,strategy_id,reason,created_at)
     VALUES ($1,$2,$3,$4,$5) ON CONFLICT (target_date,ticker,strategy_id) DO UPDATE SET reason=EXCLUDED.reason`
  → 복합 PK upsert. `created_at` datetime. graceful(사이클 88 = 호출자 흡수, 본체 raise 허용).
- `delete_pending_ndc(target_date, ticker, strategy_id)` → None
  → `DELETE FROM pending_next_day_clear WHERE target_date=$1 AND ticker=$2 AND strategy_id=$3` (idempotent).
- `load_pending_ndc(target_date)` → `set[tuple[str,str]]`
  → `SELECT ticker, strategy_id FROM ... WHERE target_date=$1` → `{(ticker, strategy_id), …}`.
  → **실패 시 빈 set(graceful)** — 호출자 메모리 set 보존(사이클 162 절대 계약).
- `purge_pending_ndc_before(target_date)` → int
  → `DELETE FROM ... WHERE target_date < $1` → 삭제 행 수. 실패 시 -1(graceful).
  → asyncpg execute "DELETE N" 상태 문자열에서 count 파싱 필요(Green 재량).

## Red 유효성 (production 4 모듈 미변경 = 현행 supabase)

- **단위**: `pg.fetch`/`pg.execute` 를 patch 했으나 4 모듈이 아직 `supabase.table(...).execute()` 호출
  → pg mock 미발화 → SQL/args/반환 계약 단언 FAIL. 또한 각 모듈 `hasattr(mod,"pg")` False /
  `hasattr(mod,"supabase")` True 불변식 단언 FAIL(전환 후 PASS).
- **통합**: production 이 pg 미경유(supabase 미연결) → 실 PG 왕복 경로 없음 → JSONB dict/복합 PK/
  UNIQUE upsert 단언 FAIL/에러. docker/`DATABASE_URL_TEST` 없으면 pg_harness fixture 가 `pytest.skip`.

## 매매 안전성 8영역 diff 0

- 4 모듈 전부 `src/db/` 내부. 소비처(scheduler/boot_manager/recommendation_engine/log_analysis_engine
  /market_regime)는 db 함수만 호출 → **함수 계약 보존 시 호출부 diff 0**.
- 특히 `pending_next_day_clear` 소비처(scheduler `_execute_next_day_clear`/`_drain_…`/`_reset_daily_state`
  + boot_manager `boot()` load 복구)는 시그니처/반환형/graceful 절대 보존 = 호출부 미변경.
- Green 단계 회귀 = `git diff -- src/engine/risk.py src/engine/order_engine.py src/realtime/
  src/auth/ src/api/order.py src/engine/session.py src/engine/scanner.py
  src/engine/strategy_registry.py` = 0 byte 직접 검증.

## 하네스

- 통합 격리 fixture 신규 4: `clean_log_reports` / `clean_backtest_runs` / `clean_market_regime`
  / `clean_pending_ndc` (`pg_harness.py` + conftest re-export). seed 행 DELETE 선행.
- `freeze_time` 안 DB read mock 의무(사이클 187 hang 교훈). 통합은 freeze 밖.

## 파일

- 단위: `tests/unit/db/test_cycleM1_2_log_reports_pg.py` / `…_backtest_runs_pg.py` /
  `…_market_regime_pg.py` / `…_pending_ndc_pg.py`.
- 통합: `tests/integration/test_cycleM1_2_four_modules_roundtrip.py` (`@pytest.mark.integration`).
