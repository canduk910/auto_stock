# 사이클 M2a (Red) — system_config + trade_history asyncpg 전환 계약 가드

승인 계획: `~/.claude/plans/partitioned-kindling-lollipop.md` (단계 2 — 매매 hot path, **HIGH 위험**).
브랜치: `db-migration-rds`. 선행: M0(pg 인프라) + M1(저의존 8모듈) Green 완료.

## 이 증분 = hot path 2모듈 (미묘 계약 집중, HIGH)

M2a 는 매매 hot path 2모듈만 다룬다 (stock_master/stock_master_daily = M2b, 별도 증분).
계약을 절대 보존해야 하는 미묘 지점에 테스트를 집중한다.

| 모듈 | 라인/호출 | 최대 위험 계약 |
|------|-----------|----------------|
| `system_config.py` | 882L / 25 | ⚠️ **JSONB `{"value": x}` codec → `isinstance(raw, dict)` True** (미작동 시 매매 파라미터 silent 폴백 = cash_usage_ratio 강제 1.0). read 헬퍼 타입(bool/float/int/str) + `key` PK upsert |
| `trade_history.py` | 623L / 59 | ⚠️ **TIMESTAMPTZ `+09:00` 계약(사이클 53 B-4)** — `get_trades_in_range` / `_to_kst` 가 timestamp 를 str 로 소비. `get_trade_pairs` Decimal 페어링. `count`+`range` 페이징. `.in_(status)` = `ANY($1::text[])`. sync 함수 dedupe 없음·CANCELLED 제외 |

## 검증된 M1 패턴 복제 (변경 금지)

1. **JSONB codec** — `pg.py::_init_conn` 이 jsonb encoder=json.dumps/decoder=json.loads 등록.
   Green 은 raw dict/list 를 **직접 바인딩**(json.dumps 사전 적용 금지 = 이중인코딩).
   read 는 codec 이 dict 로 복원 → `isinstance(raw, dict)` 분기 그대로 작동.
2. **TIMESTAMPTZ 쓰기** — `datetime.fromisoformat(now_kst_iso())` 바인딩 (str 금지, asyncpg TIMESTAMPTZ 컬럼은 datetime 요구).
3. **TIMESTAMPTZ 읽기 str 계약** — `_to_kst(row["timestamp"])` / `get_trades_in_range` 소비처가 str 을 기대.
   asyncpg 는 TIMESTAMPTZ 를 기본 `datetime` 반환 → Green 은 SELECT 에서
   `to_char(timestamp, 'YYYY-MM-DD"T"HH24:MI:SS+09:00') AS timestamp` 로 **str `+09:00` 반환 유지**
   (사이클 53 B-4 `+09:00` 계약 + `_to_kst`/`_today_kst_iso` 무변경 보장).
   ⚠️ 이게 이 증분의 최대 미묘 계약 — Green 이 datetime 을 그대로 흘리면 `_to_kst` 계약 붕괴.
4. **복합/단일 키 upsert** — `INSERT ... ON CONFLICT (key) DO UPDATE`.
5. **execute 상태 파싱** — "UPDATE N" / "DELETE N" → affected 수.
6. **NUMERIC→Decimal** — asyncpg NUMERIC 반환은 Decimal. `get_trade_pairs` 는 이미 `Decimal(str(...))`
   명시 캐스트라 안전 (float 소비처는 float() 명시).
7. **범위/count 페이징** — `count="exact"` → 별도 `SELECT count(*)`, `.range(a,b)` → `LIMIT/OFFSET`.
8. **`.in_(status)`** → `status = ANY($1::text[])` (배열 바인딩).

## 테스트 파일

- `tests/unit/db/test_cycleM2a_system_config_pg.py` — mock `pg.*` 단위 계약.
- `tests/unit/db/test_cycleM2a_trade_history_pg.py` — mock `pg.*` 단위 계약.
- `tests/integration/test_cycleM2a_hotpath_roundtrip.py` — 실 PG 왕복 (JSONB codec / `+09:00` TZ 경계 / count+range / Decimal / sync dedupe·CANCELLED).
- `tests/unit/db/test_cycleM2a_safety_diff0.py` — 매매 안전성 8영역 diff 0 불변식 (호출부 미변경 단언).

## 계약 단언 (핵심)

### system_config
- **JSONB `{"value": x}` 왕복 = dict 반환 → 실제 값** (codec 미작동 = default 폴백 → FAIL로 잡는 1순위 가드):
  - `get_cash_usage_ratio` — dict → float (미작동 시 1.0 강제 폴백)
  - `get_buy_block_mode` — dict → str (4모드 검증), invalid → HARD 폴백
  - `get_auto_regime_adjust` / `_get_bool_or_default` — dict → bool
  - `_get_float_or_default` / `_get_int_or_default` — dict → float/int
  - `_get_string_or_none` — dict → str, 키 부재 → None
- **read `_with_retry` 경유** (사이클 189 정책 = read 만 retry, 쓰기 미경유).
- **upsert `key` PK** — `INSERT ... ON CONFLICT (key) DO UPDATE`, `{"value": adjusted}` dict 바인딩,
  updated_at datetime 바인딩.
- **폴백 계약 보존** — 0건/타입 불일치/예외 → default (매매 파라미터 안전).
- **set_* 검증** — `set_cash_usage_ratio` 범위 밖 ValueError, step 0.05 보정. `set_buy_block_mode` 4모드 밖 ValueError.

### trade_history
- **`+09:00` TZ 경계** — `get_trades_in_range(start,end)` 가 `start_iso = "{d}T00:00:00+09:00"` /
  `end_iso = "{d}T23:59:59.999999+09:00"` 로 바인딩 (KST 00:00~09:00 거래 범위 포함, 사이클 53 B-4).
  통합에서 KST 08:00 거래가 당일 범위에 포함되는지 실증.
- **읽기 str 계약** — SELECT 가 timestamp 를 `+09:00` str 로 반환 → `_to_kst` 가 KST date/time 파싱.
- **`get_trade_pairs` Decimal 페어링** — 가중평균 buy/sell + profit_loss Decimal 보존, closed/open emit.
- **count + range 페이징** — `get_trades(limit, offset)` = 별도 count SELECT (총건수 정확) + LIMIT/OFFSET data.
- **`.in_(status)`** — `ANY($1::text[])` 배열 바인딩 (COMPLETED/PARTIAL).
- **sync 함수 계약** — `get_today_buy_trades_for_sync` / `get_today_sell_trades_for_sync`:
  dedupe 없음(같은 ticker 다른 order_no 전부 보존) + CANCELLED 제외 (사이클 30/73).
- **`insert_trade` timestamp datetime 바인딩** (M1 패턴 2 — str 금지).
- **`update_trade_status` affected 수** — "UPDATE N" 파싱, PENDING→COMPLETED 필터 4-eq 보존.

### 매매 안전성 8영역 diff 0
- system_config/trade_history 소비처 = risk/order_engine/scheduler 는 db 함수만 호출 →
  함수 계약(시그니처·반환형·graceful) 보존 시 호출부 diff 0.
- 8영역 git diff 0 불변식 + 호출부 미변경 단언.

## freeze_time / 통합 정책 (사이클 187)
- `freeze_time` 안에서 DB read 를 태우면 `_with_retry` 의 `asyncio.sleep(0.2)` 이 동결
  `time.monotonic` 과 결합해 무한 hang → 단위는 mock, 통합은 freeze **밖**.

## 의미 전환 (Green 에서 xfail 은퇴 — M1 선례)
- 사이클 189 `execute_with_retry` AST (`test_cycle189_ast_read_retry.py`) — supabase `execute_with_retry`
  경유 단언 → asyncpg `_with_retry` 로 전환되며 supabase 심볼 부재 → xfail.
- 사이클 68 KST AST (`test_cycle68_*`) — `src/db/` payload `now_kst_iso()` str 바인딩 단언 중
  trade_history INSERT timestamp 가 str→datetime 전환되는 부분 → 재평가.
- 사이클 29/73 upsert 회피 / 부분 UNIQUE 인덱스 패턴 — supabase-py 특유 체인 mock 단언 → xfail.
- 상세는 Green 단계에서 M1-1 `test_cycleM0_config_and_safety.py::test_no_existing_db_module_changed`
  xfail 은퇴 선례 답습.

## Red 유효성 확인
- production 2모듈(system_config/trade_history) 미변경 → `pg` 심볼 부재 → mock patch 미발화 →
  계약 단언 FAIL (단위) + 실 PG 왕복 경로 부재 → FAIL/에러 (통합).
- 8영역 diff 0 + 호출부 미변경 = 불변식 PASS.
