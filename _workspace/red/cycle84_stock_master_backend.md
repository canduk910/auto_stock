# 사이클 84 Red — stock_master UI 메뉴 백엔드 단독 단계

작성일: 2026-06-09
작성자: tdd-engineer
배경: 사이클 84 발주 = `_workspace/cycle84_phase1_diagnosis.md` 진단 + 사용자 결정 채택 (Q1=B / Q2=A / Q3=3단계 분할 / Q5=B / Q6=A / Q7=B 90일 / Q8=A / Q9=B 생략).

선행 영속:
- 사이클 68 KST 영속 (`src/db/_kst.py` `KST` / `now_kst_iso()`)
- 사이클 72 dedupe 영속 (`_DbLogHandler` 500ms TTL — trigger 영역 무관)
- 사이클 81 silent 결함 패턴 차단 (`bfdy_clpr` 정정 영속)
- 사이클 83 `[scan_pool_eager_refresh]` emit 영속

## 1. Green 시정 영역 (backend-dev 인계)

### 1-1. migration 032 — `supabase/migrations/032_stock_master_history.sql`

신규 테이블 `stock_master_history`:

| 컬럼 | 타입 | NULL | 비고 |
|------|------|------|------|
| id | BIGSERIAL | NOT NULL | PK |
| ticker | TEXT | NOT NULL | FK 권고 `REFERENCES stock_master(ticker) ON DELETE CASCADE` |
| change_type | TEXT | NOT NULL | CHECK IN ('INSERT','UPDATE','DELETE','TTL_REFRESH') |
| before_raw | JSONB | NULL | INSERT 케이스 NULL |
| after_raw | JSONB | NULL | DELETE 케이스 NULL |
| changed_at | TIMESTAMPTZ | NOT NULL | DEFAULT `now()` (사이클 69 TIMESTAMPTZ 모델 영속) |

인덱스 2종:
- `idx_smh_ticker_changed_at ON stock_master_history(ticker, changed_at DESC)` — ticker 별 history 조회
- `idx_smh_changed_at ON stock_master_history(changed_at DESC)` — retention purge (Q7=B 90일, 사이클 87+ 인계)

trigger 함수 `stock_master_history_trigger()` (PL/pgSQL):
- AFTER INSERT: `change_type='INSERT'`, before_raw=NULL, after_raw=NEW.raw
- AFTER UPDATE: NEW.raw = OLD.raw 시 `TTL_REFRESH`, 그 외 `UPDATE`
- AFTER DELETE: `change_type='DELETE'`, before_raw=OLD.raw, after_raw=NULL

trigger: `stock_master_history_track AFTER INSERT OR UPDATE OR DELETE ON stock_master FOR EACH ROW EXECUTE FUNCTION stock_master_history_trigger();`

### 1-2. `src/db/stock_master.py` 헬퍼 4종 추가

- `list_all(limit: int = 100, offset: int = 0) -> list[dict]` — 페이징 list (StockBasics-like dict 반환 + refreshed_at)
- `get_stats() -> dict` — 집계 (count_all / bfdy_clpr_present / nxt_tradable_count / top_10_recent)
- `list_history(ticker: str, limit: int = 100) -> list[dict]` — `stock_master_history` ticker 별 changed_at DESC
- `count_eager_refresh_today() -> int` — `system_logs` `[scan_pool_eager_refresh]` 카운트 (사이클 83 emit 의존)

### 1-3. `src/routes/stock_master.py` 신규 5 라우트 (READ-ONLY GET)

prefix `/api/stock-master`, ApiResponse 래퍼 영속:

- `GET /stats` → `get_stats()` 위임
- `GET /list?limit=100&offset=0` → `list_all()` + Pydantic 422 (limit < 1 or > 1000 / offset < 0)
- `GET /{ticker}` → `get(ticker)`, 미존재 404
- `GET /{ticker}/history?limit=100` → `list_history(ticker, limit)`
- `GET /scan-pool/summary` → `{eager_refresh_today: count_eager_refresh_today()}` + 향후 확장

### 1-4. `src/main.py` 라우터 등록 (1 줄)

`from src.routes.stock_master import router as stock_master_router`
`app.include_router(stock_master_router)`

## 2. 회귀 가드 매트릭스 (17 케이스, HIGH 5 / MEDIUM 7 / LOW 5)

### HIGH 5 (35%)

| ID | 파일 | 의도 |
|----|------|------|
| M-1 | `tests/unit/db/test_cycle84_migration_032_applied.py` | migration 032 SQL 정적 검증 (테이블/컬럼/인덱스/trigger 정의 존재) |
| M-2 | `tests/unit/db/test_cycle84_trigger_insert.py` | UPSERT INSERT 시 trigger → history `change_type=INSERT` + before_raw=NULL + after_raw 전수 |
| M-3 | `tests/unit/db/test_cycle84_trigger_update.py` | UPSERT UPDATE (raw 변경) 시 trigger → `change_type=UPDATE` + before/after 모두 보존 |
| M-4 | `tests/unit/db/test_cycle84_trigger_ttl_refresh.py` | UPSERT (raw 동일, refreshed_at 만 갱신) → `change_type=TTL_REFRESH` |
| M-5 | `tests/unit/routes/test_cycle84_api_response_envelope.py` | 5 라우트 전수 `ApiResponse` 래퍼 정합 (`success`/`data`/`message`) |

### MEDIUM 7 (25%)

| ID | 파일 | 의도 |
|----|------|------|
| H-1 | `tests/unit/db/test_cycle84_list_all_pagination.py` | `list_all(limit=100, offset=0)` 페이징 |
| H-2 | `tests/unit/db/test_cycle84_get_stats_aggregation.py` | count / bfdy_clpr / nxt_tradable / top_10_recent |
| H-3 | `tests/unit/db/test_cycle84_list_history_per_ticker.py` | ticker filter + changed_at DESC |
| H-4 | `tests/unit/db/test_cycle84_count_eager_refresh_today.py` | system_logs `[scan_pool_eager_refresh]` 카운트 |
| H-5 | `tests/unit/routes/test_cycle84_route_404.py` | 미존재 ticker 시 404 |
| H-6 | `tests/unit/routes/test_cycle84_route_invalid_limit.py` | limit < 1 or > 1000 시 422 |
| H-7 | `tests/unit/routes/test_cycle84_route_invalid_offset.py` | offset < 0 시 422 |

### LOW 5 (40%)

| ID | 파일 | 의도 |
|----|------|------|
| L-1 | `tests/unit/db/test_cycle84_kst_consistency.py` | `changed_at` KST `+09:00` 영속 (사이클 68 답습) |
| L-2 | `tests/unit/ast/test_cycle84_ast_no_update_route.py` | `src/routes/stock_master.py` 에 PUT/POST/DELETE/PATCH 0건 (READ-ONLY 영구 가드) |
| L-3 | `tests/unit/engine/test_cycle84_scan_pool_emit_persistence.py` | 사이클 83 `[scan_pool_eager_refresh]` 1행 emit 영속 가드 |
| L-4 | `tests/unit/db/test_cycle84_cycle72_dedupe_no_impact.py` | trigger INSERT 가 `_DbLogHandler` dedupe 영역 무영향 (별도 경로) |
| L-5 | `tests/unit/engine/test_cycle84_cycle32_r4_no_impact.py` | 사이클 32 R4 universe guard 무영향 (READ-ONLY GET) |

## 3. Red 실행 결과 (예상)

- 백엔드 현재: 2120 PASS + 2 XFAIL + 2 skip
- 사이클 84 Red 추가 시: 17 신규 fail (production 코드 0 / migration 032 미적용)
- Green 단계 (backend-dev): migration 032 적용 + 4 헬퍼 + 5 라우트 → 2137 PASS

## 4. 영향 인덱스 갱신

`_workspace/test_index.yaml` backend tests 349 → 366 (+17).

## 5. 매매 안전성 영향 평가

- **무영향**: READ-ONLY GET 5종 + trigger 단일 진입점 (DB 레벨)
- 매매 hot path (`risk.on_tick` / `order_engine` / `scheduler._boot`) 변경 0
- 사이클 32 R4 universe guard 무영향 (L-5 가드)
- 사이클 72 dedupe 영속 무영향 (L-4 가드, trigger ≠ `_DbLogHandler`)
- 사이클 81 silent 결함 차단 패턴 영구 차단 (변경기록 영속)

## 6. 후속 사이클 인계

- **사이클 85** (프론트): 7번째 메뉴 "종목마스터" + 5 라우트 호출 컴포넌트
- **사이클 86** (통합 검증): E2E + 운영 측정
- **사이클 87+** (Q7=B 90일 retention cron job): `purge_old_stock_master_history()` 헬퍼 (사이클 6 `purge_old_logs` 답습)
