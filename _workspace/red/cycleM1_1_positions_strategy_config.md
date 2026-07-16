# 사이클 M1-1 (Red) — Supabase→RDS 이전 단계 M1 증분 1

승인 계획: `~/.claude/plans/partitioned-kindling-lollipop.md` (단계 1, 저의존 독립 모듈).
선행: M0 (`src/db/pg.py` asyncpg 인프라) Green 완료.

## 증분 범위
① 실 Postgres 통합 하네스 + CI service 컨테이너
② `positions.py` (5함수) supabase → `pg.*` 전환
③ `strategy_config.py` (4함수, JSONB `params` 최우선) supabase → `pg.*` 전환

**다른 M1 모듈 6개(log_reports/backtest_runs/market_regime/pending_next_day_clear/
daily_performance/strategy_funnel)는 이 증분 범위 밖 — 미터치.**

## 산출물

| 파일 | 역할 |
|---|---|
| `tests/integration/pg_harness.py` | 세션 스코프 실 PG 하네스 (fixture: `pg_dsn`/`pg_migrated`/`pg_pool`/`clean_positions`/`clean_strategy_config`) |
| `tests/integration/conftest.py` | 하네스 fixture re-export (기존 파일에 import 추가만) |
| `tests/integration/test_cycleM1_1_pg_roundtrip.py` | 실 PG 왕복 (positions 5 + strategy_config 6 = 11) |
| `tests/unit/db/test_cycleM1_1_positions_pg.py` | positions mock 계약 (8) |
| `tests/unit/db/test_cycleM1_1_strategy_config_pg.py` | strategy_config mock 계약 (8) |
| `.github/workflows/ci.yml` | `backend-test` job 에 `postgres:15` service + `DATABASE_URL_TEST` env |

## 하네스 설계
- `DATABASE_URL_TEST` env 있으면 사용(CI service 컨테이너), 없으면 subprocess
  `docker run -d --rm -p 0:5432 postgres:15` 기동 + `docker port` 로 랜덤 포트 파싱
  + asyncpg healthcheck 폴링. testcontainers 부재라 subprocess 직접 사용.
- **migration 001~041 순차 적용**: `sorted(supabase/migrations/*.sql)` 각 파일을
  asyncpg `conn.execute`. psql 로컬 없음 → asyncpg 로 .sql 실행.
- `pg_pool` fixture 가 `settings.database_url` 을 통합 DSN 으로 임시 교체 후 `pg.init_pool()`.
- docker/DB 없으면 `pg_dsn` fixture 가 `pytest.skip` — 통합은 옵셔널 안전망, mock 이 주력.
- `@pytest.mark.integration` + `@pytest.mark.slow` 마커.
- 하네스 실증(직접 probe): migration 41개 적용 성공 + positions/strategy_config 테이블
  존재 + JSONB codec `dict` 반환 확인. 컨테이너 teardown 클린(누수 0).
  - 주의: migration 002/011/018 이 strategy_config 기본 3행 seed → 통합 테스트는
    `clean_strategy_config` (DELETE) 로 격리 시작.

## 전환 대상 계약 (Green 지침)

### positions.py
| 함수 | SQL (대표) | 반환 |
|---|---|---|
| `save_position` | `INSERT INTO positions ... ON CONFLICT (ticker) DO UPDATE` | None |
| `delete_position` | `DELETE FROM positions WHERE ticker = $1` | None |
| `load_all` | `SELECT * FROM positions` → `pg.fetch` | list[dict] (컬럼명 키) |
| `update_high` | `UPDATE positions SET high_since_buy = $1 WHERE ticker = $2` | None |
| `clear_all` | `DELETE FROM positions` | None |
- `high_since_buy=0` → `buy_price` 보정 계약 보존 (기존 `high or buy_price`).

### strategy_config.py (⚠️ JSONB 최우선)
| 함수 | 계약 |
|---|---|
| `load_all` | `pg.fetch(SELECT * strategy_config)` → `{sid: {enabled, weight: float, params: dict}}`. **params JSONB → dict** (codec) + weight NUMERIC → `float()` + params non-dict → `{}` 폴백 |
| `save` | `INSERT ... ON CONFLICT (strategy_id) DO UPDATE`. params dict JSONB 바인딩 (codec `json.dumps`) |
| `save_weights` | 기존 params `pg.fetch` 조회 후 유지 + weight 갱신 |
| `save_params` | 기존 enabled/weight 조회 후 유지 + params 갱신. 미존재 시 (True, 0.5) 기본 |

## 계약 보존 불변식
- 시그니처·반환형 100% 동일 → 호출부(order_engine 등) **diff 0**.
- load_all 반환 dict 키 = 컬럼명 불변 (매매 hot path 소비).
- 전환 후 모듈에 `supabase` 심볼 부재 + `pg` 심볼 존재 (pg 단독 전환 증명).

## Red 확인 (production 미변경 상태)
- **단위 15 FAIL** (positions 8 + strategy_config 7... 실측 8+8=16 중 `httpx.ConnectError`
  14 + `no_supabase_reference` AssertionError 2):
  - pg mock patch 했으나 production 이 여전히 supabase 호출 → `httpx.ConnectError`
    (mock 미발화 = 아직 pg 미사용 실증).
  - `no_supabase_reference` 단언 = 모듈에 supabase 심볼 잔존 → FAIL.
- **통합 10 FAIL**: 하네스가 PG 기동 + migration 적용 + pg 풀 연결 성공(clean fixture 의
  `DELETE FROM positions` 를 pg 로 정상 실행 = 인프라 OK) 했으나, production `save_position`
  이 supabase 호출 → `httpx.ConnectError`. 실 PG 왕복 경로 부재 실증.
- 기존 db 단위 441 PASS (M1 15 deselect) — 회귀 0, conftest re-export 무해.

## 매매 안전성
- 8영역 diff 0 (`git diff -- src/engine/risk.py order_engine.py realtime/ auth/
  api/order.py session.py scanner.py strategy_registry.py` = 빈 출력 직접 검증).
- production positions.py/strategy_config.py/pg.py **미터치** (Red = 현행 supabase 그대로).
- `freeze_time` 안 DB read mock 의무(사이클187) 준수 — 단위는 pg AsyncMock, 통합은
  freeze 밖 실 PG.

## Green 인계
- positions.py/strategy_config.py 를 `pg.*` 로 전환 → 단위 16 + 통합 11 PASS.
- `import src.db.pg as pg` 추가 + `from src.db.supabase import supabase` 제거.
- save 계열은 `pg.execute` (retry 미경유 = 쓰기 멱등), load 계열은 `pg.fetch`.
