# 사이클 M3a (Red) — 분석·관찰 3모듈 asyncpg 전환 계약 가드

승인 계획: `~/.claude/plans/partitioned-kindling-lollipop.md` (단계 3 — 분석·관찰, 비 hot-path).
브랜치: `db-migration-rds`. M0·M1·M2(4모듈) Green 완료 후 M3a 증분.

## 범위 (3모듈, 비 hot-path)

| 모듈 | 라인 | 호출 | 핵심 계약 |
|---|---|---|---|
| `src/db/parameter_recommendations.py` | 220L | 18 | `(target_date, strategy_id)` UNIQUE(부분 pending/applied/partial) · JSONB(current/recommended_params/metrics/backtest_summary) · NUMERIC nullable(recommended/applied_weight) · status ENUM(pending/applied/partial/rejected/expired/applied_auto) · applied_at/rejected_at 자동 |
| `src/db/kis_quote_accounts.py` | 282L | 11 | read 4함수 `_with_retry` 경유(사이클189) · **60s TTL 메모리 캐시**(hit/만료/DB예외 stale 반환/invalidate) · label UNIQUE(LabelConflictError) · **평문 credential = `get_credentials_for_token_manager` 만 노출** · UUID PK |
| `src/db/stock_master_financial.py` | 181L | 8 | PK `(ticker, stac_yymm, div_cls)` 복합 upsert(ON CONFLICT) · batch 100 chunk · **NUMERIC 18컬럼 → Decimal** · raw JSONB · `get_financial_series` `_with_retry` 경유 · graceful |

**M3b (system_logs + `_DbLogHandler` seam + main.py auto_start) 미터치.**

## 신규 파일

### 하네스 fixture (`tests/integration/pg_harness.py` +3)
- `clean_parameter_recommendations` / `clean_kis_quote_accounts` / `clean_stock_master_financial`
- `clean_kis_quote_accounts` 는 setup/teardown 양쪽 `invalidate_list_cache()` 동반(캐시 오염 차단).
- `tests/integration/conftest.py` re-export 3건 추가 (import OK 확인).

### 단위 (mock `pg.*`)
- `tests/unit/db/test_cycleM3a_parameter_recommendations_pg.py` (18 케이스)
- `tests/unit/db/test_cycleM3a_kis_quote_accounts_pg.py` (28 케이스)
- `tests/unit/db/test_cycleM3a_stock_master_financial_pg.py` (18 케이스)
- `tests/unit/db/test_cycleM3a_safety_diff0.py` (9 케이스 — 8영역 diff0 + 심볼/시그니처 보존)

### 통합 (실 PG 왕복)
- `tests/integration/test_cycleM3a_three_modules_roundtrip.py` (14 케이스)
  - UNIQUE upsert(param_rec / financial 복합PK) + JSONB(backtest_summary nested) 왕복 dict
  - kis_quote 60s 캐시 stale 반환(DB예외) + 평문 격리 + label UNIQUE
  - **NUMERIC → Decimal**(financial 18컬럼) + batch 100 chunk 전량 적재

## 검증된 패턴 복제 (M1/M2 선례)
- JSONB raw dict 직접 바인딩(codec, json.dumps 금지) — `_has_jsonb_binding` 헬퍼(dict 또는 dumps 문자열 허용, Green 자유도)
- TIMESTAMPTZ 쓰기 = `datetime` 바인딩(`fromisoformat(now_kst_iso())`), str 금지
- `.in_`→`ANY`, count="exact"→`fetchval count(*)`, execute "UPDATE N" 파싱, 읽기 `pg.fetch`·쓰기 `pg.execute`
- read `_with_retry` 경유(사이클189) / 쓰기 `_with_retry` 미경유(멱등)
- supabase / execute_with_retry 심볼 잔존 금지 불변식

## Red 확인 (production 3모듈 미변경)

```
tests/unit/db/test_cycleM3a_{3모듈}_pg.py + safety_diff0.py:
  44 failed, 27 passed  (0.4s, hang 0)
tests/integration/test_cycleM3a_three_modules_roundtrip.py:
  14 failed  (2.7s, hang 0)  ← docker postgres:15 컨테이너 + migration 001~041 적용됨
```

### 27 PASS = 의도된 불변식 (Green 후에도 PASS 유지)
- safety 8영역 diff0(3모듈은 8영역 밖) + 3모듈 함수 심볼/시그니처 보존 + `auth/token.py` credentials 계약 호출
- 상수/캐시 심볼 보존(`_BATCH_SIZE=100` / `_LIST_CACHE_TTL=60.0` / `invalidate_list_cache` / 평문 격리 정적)
- graceful 폴백 계약(예외 → `[]`/`None`/`{}`/`False`/`0`/ValueError) — 현행 supabase graceful 과 pg graceful 둘 다 만족(계약 보존)

### 44+14 FAIL = pg 라우팅 미구현 (Green 대상)
- SQL/JSONB 바인딩/datetime 바인딩/`pg._with_retry` on pg/캐시 pg 경유 단언 → 전부 Red
- `pg` mock 은 발화하나 production 은 supabase(`to_thread`/`execute_with_retry`) 호출 → "중립화" 예외/ConnectError 로 FAIL = **production 미전환 증거**

### Red hang/DNS 노이즈 차단 (autouse `_neutralize_supabase`)
- 3 단위 파일 + 통합 파일에 현행 supabase 경로(`asyncio.to_thread` / `execute_with_retry`) 즉시 예외 중립화 autouse fixture.
- 목적 = production 이 실 Supabase(DNS)로 나가 httpx ConnectError/60s timeout 유발하던 것을 차단 → 테스트가 *계약 단언* 으로 빠르게 FAIL(Red 의도 선명).
- **Green 후 무해**: 전환되면 supabase/execute_with_retry 심볼이 사라지므로 `raising=False` patch 는 no-op. 실 pg 왕복(`pg.*`)은 이 fixture 와 무관.

## Green 인계 (backend-dev)

### 전환 요령 (M1/M2 카탈로그)
- `parameter_recommendations`: insert → `INSERT ... RETURNING *` (fetchrow) + `ON CONFLICT` 없이 부분 UNIQUE 충돌은 asyncpg `UniqueViolationError`(23505) catch → None. list → `WHERE target_date >= $1 ORDER BY created_at DESC`. update_status → `UPDATE ... RETURNING *`, applied_at/rejected_at 조건부 SET(datetime 바인딩). update_backtest_summary → `UPDATE ... backtest_summary=$1 ... RETURNING`. expire → `UPDATE ... status='expired' WHERE status='pending' AND target_date < $1` + `"UPDATE N"` 파싱 int.
- `kis_quote_accounts`: read 4함수 `pg._with_retry(_factory, op=...)` 경유 + `from_row` 마스킹 유지. **캐시 로직(`_list_cache`/TTL/stale 반환/invalidate) 절대 보존** — pg.fetch 예외 시 stale 캐시 반환. 쓰기(insert/update/delete)는 `pg.execute` 직접(retry 미경유). `get_credentials_for_token_manager` 만 평문 dict — 로그 금지.
- `stock_master_financial`: upsert → chunk(100) 당 `pg.executemany` 또는 `pg.execute` + `ON CONFLICT (ticker, stac_yymm, div_cls) DO UPDATE`. raw dict/refreshed_at datetime 바인딩. read 2함수 `_with_retry` 경유. NUMERIC 은 asyncpg 가 Decimal 반환(라우트 직렬화 확인).

### 의미 전환 (Green xfail 은퇴 — M1/M2 선례)
Green 시 3모듈이 supabase import 를 잃으므로 아래 기존 supabase-mock 테스트가 깨진다 → xfail 마킹 또는 은퇴:
- `tests/unit/db/test_parameter_recommendations_v2.py` / `test_parameter_recommendations_backtest.py` / `test_parameter_recommendations_weight_reasoning.py`
- `tests/unit/db/test_kis_quote_accounts.py` / `test_kis_quote_accounts_cache.py`
- `tests/unit/db/test_cycleC1_stock_master_financial_crud.py`
- 사이클189 AST(`test_cycle189_ast_read_retry.py` — kis_quote read retry 정본) / 사이클68 KST(`test_cycle68_*` per-module) / C1 supabase 체인 단언 → pg 정합으로 갱신.
- (현재 이 3모듈 관련 supabase 테스트 20건 PASS 확인 = production 미변경 증거.)

### 검증 의무
- 매매 안전성 8영역 diff 0 (3모듈 소비처 = db 함수만 호출, 호출부 미변경).
- `freeze_time` 안 DB read mock(사이클187) — 이 Red 는 freeze 미사용(mock 주력).
- Green 후 `test_cycleM3a_*_pg.py` 44 FAIL → PASS + 통합 14 FAIL → PASS(docker/DATABASE_URL_TEST 환경).
