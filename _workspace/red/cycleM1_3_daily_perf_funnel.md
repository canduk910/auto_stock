# 사이클 M1-3 (Red) — daily_performance(RPC) + strategy_funnel asyncpg 전환

승인 계획: `~/.claude/plans/partitioned-kindling-lollipop.md` (단계 1, M1 마무리 = 마지막 2모듈).
M0 · M1-1 · M1-2 Green 완료. **검증된 패턴 복제** (M1-1/M1-2 mock 계약 + 통합 왕복).

## 대상 2모듈 (production 미변경 = 현행 supabase)

1. `src/db/daily_performance.py` (102L) — ⚠️ **RPC 포함**
   - `upsert_daily_performance(target_date, total_asset, daily_profit_rate, strategy='total', *, net_external_cashflow, daily_realized_pnl, deposit, cumulative_return_rate)` → None
   - `get_performance(days=30, strategy='total')` → list[dict] (**date ASC 반환**, client-side `sorted`)
   - `get_latest_performance(strategy='total')` → dict | None (ORDER BY date DESC LIMIT 1)
   - `recompute_from_trades()` → bool — `.rpc("recompute_daily_performance", {})` → `pg.execute("SELECT recompute_daily_performance()")`. 성공 True / 예외 graceful False
2. `src/db/strategy_funnel.py` (204L) — JSONB cap + UNIQUE + is_provisional
   - `insert_snapshot(*, target_date, strategy_id, step_no, step_name, survived_tickers, excluded_sample, survived_count, excluded_count, step_conditions, is_provisional)` → dict | None
   - `list_snapshots(*, target_date, strategy_id=None)` → list[dict]
   - `list_recent_by_strategy(strategy_id, days=7)` → list[dict]

## 전환 계약 (M1-1/M1-2 확정 패턴)

- **JSONB**: 쓰기 `$N::jsonb` + json.dumps (또는 codec dict/list 그대로), 읽기 codec dict/list 반환 (추가 파싱 금지).
  - daily_performance = JSONB 컬럼 **없음** (전 컬럼 DATE/NUMERIC/VARCHAR).
  - strategy_funnel = `survived_tickers`(list[str|dict], cap 200) / `excluded_sample`(list[dict], cap 20).
- **TIMESTAMPTZ**: 쓰기 `datetime.fromisoformat(now_kst_iso())` (str 불가). daily_performance/strategy_funnel 모두 시각 컬럼은 DB DEFAULT `now()` (snapshot_at/created_at) → 명시 바인딩 불요. RPC 는 timestamp 를 KST 캐스트(plpgsql 내부).
- **복합 키/UNIQUE**: `ON CONFLICT (컬럼…) DO UPDATE SET col=EXCLUDED.col`.
  - daily_performance = `(date, strategy)` 복합 PK (migration 002).
  - strategy_funnel = `(target_date, strategy_id, step_no)` UNIQUE (migration 035, snapshot_at 키 폐기).
- **asyncpg 상태 문자열**: `execute` → "DELETE N"/"UPDATE N"/"INSERT 0 1"/"SELECT 1". (본 2모듈 count 반환 함수 없음 — daily_performance 는 카운트 미반환, strategy_funnel 도 미반환.)
- **NUMERIC → Decimal**: asyncpg NUMERIC = Decimal. get_* 반환 dict 의 total_asset/daily_realized_pnl/daily_profit_rate/cumulative_return_rate 가 Decimal → 라우트 float 캐스트 안전. 통합에서 `isinstance(..., Decimal)` 단언.
- **함수 계약 100% 보존** → 호출부 diff 0 (scheduler `_settle`/`recompute_from_trades`, 라우트 `POST /api/strategy-funnel/snapshot`, `capture_funnel_snapshots`).

## ⚠️ RPC 전환 (daily_performance 고유)

- 현행: `supabase.rpc("recompute_daily_performance", {}).execute()`.
- 전환: `pg.execute("SELECT recompute_daily_performance()")`.
- plpgsql 함수 `recompute_daily_performance()` = migration 010 정의 + 012 보강 → **하네스에 이미 존재** (migration 001~041 순차 적용).
- **RPC 는 기존 daily_performance 행을 UPDATE 만 함** (INSERT 안 함) — 3-step:
  1. trade_history SELL profit_loss 합 → daily_realized_pnl (전략별 + 'total')
  2. daily_profit_rate = realized / **가장 가까운 0 아닌 이전 영업일** total_asset * 100 (012 correlated subquery)
  3. cumulative_return_rate = TWR 복리 누적
- → 통합 RPC 테스트는 upsert 로 (전략 행 + 'total' 행 + 전일 baseline 행) **선생성 필수**, 그 후 trade_history SELL seed → recompute → daily_realized_pnl UPDATE 실증.

## Red 유효성 (production 미변경 → FAIL 확인)

- **단위** (`pg.*` mock patch): 2모듈이 아직 `supabase.table(...)`/`supabase.rpc(...)` 호출 → pg mock 미발화 → SQL/args/반환 계약 단언 FAIL. 불변식 `hasattr(mod,"pg")` False / `hasattr(mod,"supabase")` True 도 FAIL (전환 후 PASS).
- **통합** (실 PG 왕복): production 이 pg 미경유(supabase 미연결) → 실 PG 왕복 경로 없음 → JSONB dict/list · RPC UPDATE · NUMERIC Decimal · UNIQUE upsert 단언 FAIL/에러. docker/`DATABASE_URL_TEST` 없으면 pg_harness fixture `pytest.skip`.

## 매매 안전성 8영역 diff 0

- 2모듈 전부 `src/db/` 내부. 소비처(scheduler `_settle`/recompute, log_analysis_engine, 라우트 strategy_funnel, `capture_funnel_snapshots`)는 db 함수만 호출 → 함수 계약 보존 시 호출부 diff 0.
- daily_performance/strategy_funnel = 정산·관찰성 경로 (매매 hot path 무관, 사이클 38 명문화).
- Green 회귀 = `git diff -- src/engine/risk.py src/engine/order_engine.py src/realtime/ src/auth/ src/api/order.py src/engine/session.py src/engine/scanner.py src/engine/strategy_registry.py` = 0 byte 직접 검증.

## 하네스 (M1 증분 3)

- 격리 fixture 신규 2 (`pg_harness.py` + conftest re-export):
  - `clean_daily_performance` — daily_performance **+ trade_history** DELETE (RPC seed 격리).
  - `clean_strategy_funnel` — strategy_funnel_snapshots DELETE.
- `freeze_time` 안 DB read mock 의무 (사이클 187 hang 교훈). 통합은 freeze 밖.

## 의미 전환 (Green 에서 xfail 은퇴 — M1-1/M1-2 선례)

- 사이클 68 KST timestamp AST 가드 (`test_cycle68_*`) 는 8 DB 모듈 명시 대상 목록에 daily_performance/strategy_funnel 이 **포함되지 않음** (G-2~G-9 = stock_master/parameter_recommendations/log_reports/system_config/strategy_config/kis_quote_accounts/market_regime_snapshots/backtest_runs). G-10 rglob 은 `datetime.utcnow()`/`datetime.now(timezone.utc)` 잔존 0건만 검사 → asyncpg 전환(supabase 패턴 소멸) 무영향. → **본 2모듈은 cycle68 의미 전환 없음**. (Green 시 supabase import 제거만.)
- 이 memo 는 Red 산출물. Green(backend-dev) 이 2모듈 pg 전환 후 단위/통합 PASS + 매매 안전성 8영역 diff 0 검증.

## 파일

- 단위: `tests/unit/db/test_cycleM1_3_daily_performance_pg.py` / `test_cycleM1_3_strategy_funnel_pg.py`.
- 통합: `tests/integration/test_cycleM1_3_daily_perf_funnel_roundtrip.py` (`@pytest.mark.integration`).
- 하네스: `tests/integration/pg_harness.py` (+2 fixture) / `tests/integration/conftest.py` (+2 re-export).
