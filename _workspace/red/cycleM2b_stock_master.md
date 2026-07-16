# 사이클 M2b (Red) — stock_master + stock_master_daily asyncpg 전환 계약 가드

승인 계획: `~/.claude/plans/partitioned-kindling-lollipop.md` (단계 2 — 매매 hot path, **HIGH 위험**).
브랜치: `db-migration-rds`. 선행: M0(pg 인프라) + M1(저의존 8모듈) + **M2a(system_config/trade_history) Green 완료**.

## 이 증분 = 매매 hot path 2모듈 (최대·최복잡, HIGH)

M2b 는 매매 hot path 중 **매수 유니버스 + 일봉 어댑터** 2모듈을 다룬다.
`list_by_filter`(매수 풀 구성)와 `get_recent_daily_normalized`(prepare 일봉 소스)가 hot path 직결이라
**필터 결과 원소·순서·limit·폴백 우선순위를 극도로 보존**해야 한다.

| 모듈 | 라인/호출 | 최대 위험 계약 |
|------|-----------|----------------|
| `stock_master.py` | 770L / 56 (**최대**) | ⚠️ **`list_by_filter` 매수 유니버스** — DB-side 생성컬럼 필터(사이클205 `hts_avls_eok`/`acml_tr_pbmn_won` gte) + is_kospi200∪is_kosdaq150 **OR 합집합**(사이클153) + return_stage_counts **3쿼리 union/mcap/trade**(사이클170/205) + exclude/limit. **필터 결과 원소·순서·limit 불변**(G-A-1 HIGH). `get_stats` 4카운트 jsonb 존재성 text path. `list_paged_by_filter` UI 생성컬럼 gte + name ilike + count. upsert raw JSONB + ticker 6자리 정규화. master_raw 컬럼. |
| `stock_master_daily.py` | 700L / 17 | ⚠️ **`get_recent_daily_normalized` 락/신선도/부족 폴백**(사이클172/173, prepare 일봉 소스) — `get_recent_daily`/`max_bas_dd`(내부 SQL) + `fetch_daily_candles`(KIS **미변경**) 조합, raw JSONB 그대로 반환(사이클81). **`purge_old_rows` 날짜 슬라이스 루프**(사이클192) — SELECT/DELETE **양쪽 protected 제외**(never-drain P-3). `upsert_batch` 100 chunk. `get_atr`/`get_donchian_high` Python 계산(SQL은 fetch만). |

## 검증된 M0/M1/M2a 패턴 복제 (변경 금지)

1. **JSONB codec** — `pg.py::_init_conn` 이 jsonb encoder=json.dumps/decoder=json.loads 등록.
   Green 은 raw dict 를 **직접 바인딩**(json.dumps 사전 적용 금지 = 이중인코딩). read 는 codec 이
   dict 로 복원 → `row["raw"]` dict 그대로 소비. (stock_master `raw` / stock_master_daily `raw` 왕복.)
2. **TIMESTAMPTZ 쓰기** — `datetime.fromisoformat(now_kst_iso())` 바인딩(str 금지). refreshed_at /
   master_raw_updated_at / updated_at 컬럼.
3. **TIMESTAMPTZ 읽기 str 계약** — `is_stale` refreshed_at 소비처가 str/datetime 모두 흡수(현행
   `isinstance(datetime)` 분기 보존). 별칭 `t.` 필수(`ORDER BY t.컬럼` 모호성 해소).
4. **`.in_`→`ANY($1::text[])`** — purge_old_rows `not_.in_("ticker", pt)` → `ticker != ALL($1::text[])`
   또는 `NOT (ticker = ANY(...))`.
5. **count="exact"→별도 `fetchval("SELECT count(*)")`** — get_stats 4카운트, count_active,
   count_master_raw_today, count_all/count_by_ticker.
6. **range→LIMIT/OFFSET** — list_all, list_paged_by_filter data 쿼리.
7. **복합키 ON CONFLICT DO UPDATE** — upsert_daily/upsert_batch `(ticker,bas_dd)` / upsert_one ·
   upsert_master_raw `(ticker)`.
8. **execute "DELETE N" 파싱** — purge_old_rows 날짜별 DELETE affected 누적.
9. **읽기 `pg.fetch`(내부 _with_retry) / 쓰기 `pg.execute`(retry 미경유)** — 사이클187/189 정책 계승.
   특히 사이클192 G-187-A2 = **purge_old_rows 는 SELECT 도 `_with_retry` 미경유**(쓰기 함수 멱등 보수 분류).
10. **supabase import 제거** — 전환 후 두 모듈에 `supabase` 심볼 부재(pg 단독).

## 테스트 파일

- `tests/unit/db/test_cycleM2b_stock_master_pg.py` — mock `pg.*` 단위 계약 (list_by_filter 3쿼리/합집합/
  생성컬럼 gte, get_stats 4카운트, list_paged, upsert/get/is_stale, master_raw, count_active/eager).
- `tests/unit/db/test_cycleM2b_stock_master_daily_pg.py` — mock `pg.*` 단위 계약 (upsert_batch chunk,
  get_recent_daily, get_atr/get_donchian_high 계산, get_recent_daily_normalized 락/신선도/부족 폴백,
  purge 날짜 슬라이스 protected 보존).
- `tests/integration/test_cycleM2b_universe_daily_roundtrip.py` — 실 PG 왕복 (생성컬럼 임계 정확,
  is_kospi200∪is_kosdaq150 합집합, return_stage_counts 3단계, get_stats 4카운트, upsert_batch 100 chunk,
  get_atr/get_donchian_high 정합, purge 날짜슬라이스 protected 보존, JSONB raw 왕복).
- `tests/unit/db/test_cycleM2b_safety_diff0.py` — 매매 안전성 8영역 diff 0 + 호출부(strategies/scanner)
  미변경 불변식.

## 계약 단언 (핵심)

### stock_master.list_by_filter (⚠️ 매수 유니버스 hot path)
- **생성컬럼 gte** — `min_market_cap>0` → `hts_avls_eok >= ceil(min_market_cap/1e8)` /
  `min_trade_amount>0` → `acml_tr_pbmn_won >= min_trade_amount` (사이클205 DB-side, 사이클168 패턴).
- **is_kospi200∪is_kosdaq150** — 양True = **OR 합집합**(사이클153 donchian FUNNEL_STAGES[0]) /
  한쪽 = AND / 둘 다 None = 무필터.
- **return_stage_counts=True** — `(filtered, {"union_tickers","mcap_tickers","trade_tickers"})` 튜플.
  사이클205 = 3쿼리(union: mcap/trade gte 미포함 / mcap: mcap gte / trade: mcap+trade gte).
  **trade_filtered == return_stage_counts=False 결과 원소·순서 정합(G-A-1 HIGH — 매수 풀 불변)**.
- **exclude_tickers / limit** — 제외 집합 + limit 절단 계약 보존.
- **읽기 pg.fetch** 경유. 반환 dict 키(ticker/name/excg_dvsn_cd/nxt_tradable/is_kospi200/is_kosdaq150/raw).

### stock_master 나머지
- **get_stats 4카운트** — count_all / nxt_tradable_count(.eq) / bfdy_clpr_present ·
  with_hts_avls · with_acml_tr_pbmn(**raw->>'키' 존재성** = non-null AND `<>'0'` AND `<>''` text path)
  = 각 `fetchval("SELECT count(*) ...")`. top_10_recent 별도 limit 10.
- **list_paged_by_filter** — 생성컬럼 gte + market .eq + name ilike + count(*) 별도 + range→LIMIT/OFFSET.
- **upsert_one** — INSERT ON CONFLICT (ticker), raw dict JSONB 직접 바인딩, refreshed_at datetime,
  ticker 6자리 정규화(비6자리 → `_normalize_ticker`).
- **get(ticker)** — fetchrow → StockBasics 또는 None.
- **is_stale** — refreshed_at 파싱 → 24h 비교, 미존재/부재/파싱실패 → True.
- **count_active / count_eager_refresh_today** — count(*) fetchval. eager 는 3 prefix ilike + KST 범위.
- **master_raw** — upsert_master_raw(is_kospi200/is_kosdaq150 컬럼 + master_raw JSONB +
  master_raw_updated_at KST + nxt_tradable=False 신규 INSERT 이중 안전망 보존) / get_master_raw /
  count_master_raw_today.

### stock_master_daily
- **upsert_batch** — 100 chunk (`_BATCH_SIZE`), 복합키 ON CONFLICT (ticker,bas_dd), graceful chunk 실패.
- **get_recent_daily** — bas_dd DESC + limit, 읽기 pg.fetch, graceful 빈 list.
- **get_donchian_high / get_atr** — get_recent_daily rows 위 **Python 계산**(SQL은 fetch만).
- **get_recent_daily_normalized (⚠️ prepare 일봉 소스)** — 락 게이트(`_row_has_lock`) → KIS 폴백 /
  신선도 게이트(max_bas_dd > today-4) → KIS 폴백 / min_required 부족 → KIS 폴백 / 정상 → raw JSONB
  그대로. `fetch_daily_candles`(KIS) **미변경** 폴백 경로. 폴백 우선순위 절대 보존.
- **purge_old_rows (⚠️ never-drain P-3)** — 날짜 슬라이스 루프: SELECT oldest bas_dd(**protected 제외**,
  lt cutoff, order asc, limit 1) → 없으면 drained break → 그 날짜 DELETE(**protected 제외**, count 파싱).
  **SELECT 쪽 protected 제외 절대 보존**(누락 = never-drain 회귀). `DAILY_RETENTION_DAYS=230` 불변.
  purge 는 SELECT/DELETE **모두 `_with_retry` 미경유**(G-187-A2 쓰기 함수 멱등 보수).

### 매매 안전성 8영역 diff 0
- list_by_filter/get_recent_daily_normalized 소비처 = strategies/scanner 는 db 함수만 호출 →
  함수 계약(시그니처·반환형·graceful) 보존 시 호출부 diff 0.
- 8영역 git diff 0 불변식 + 호출부(scanner/strategies) 미변경 단언.

## freeze_time / 통합 정책 (사이클 187)
- `freeze_time` 안에서 DB read(`get_recent_daily_normalized`/`is_stale`/`purge_old_rows`)를 태우면
  `_with_retry` 의 `asyncio.sleep(0.2)` 이 동결 `time.monotonic` 과 결합해 무한 hang →
  단위는 mock(freeze 밖 또는 read mock), 통합은 freeze **밖**.
- `get_recent_daily_normalized` 신선도 게이트가 `datetime.now(KST)` 를 태움 → mock 단위 테스트는
  `max_bas_dd` 를 date.today() 근처로 patch(사이클173 선례) — freeze 불필요.

## 의미 전환 (Green 에서 xfail 은퇴 — M1/M2a 선례, 근거 명시)
Green 이 두 모듈을 pg 로 전환하면 아래 supabase 체인 mock 단언이 라우팅 불가 → xfail 은퇴 재평가:
- 사이클 108 (`test_cycle108_list_by_filter.py`) — `MagicMock` supabase 체인 `.select().order().limit()`
  단언 + 205 gte 시뮬 rows → pg.fetch 로 라우팅 불가.
- 사이클 128 (`test_cycle128_list_paged_by_filter.py`) — supabase count="exact"/range/ilike 체인 +
  AST `.range(0,9999)` 잔존 0건(supabase 체인 전용 패턴) 재평가.
- 사이클 153 (`test_cycle153_list_by_filter_index_flags.py`) — supabase `.or_()`/`.eq()` 체인 단언.
- 사이클 166 (`test_cycle166_hts_avls_unit_correction.py`) — 억원 환산 mock(체인/gte 시뮬).
- 사이클 168 (`test_cycle168_list_paged_generated_cols.py`) — 생성컬럼 gte 체인 + AST supabase 체인 가드.
- 사이클 170 (`test_cycle170_card_a_stage_counts.py`) — return_stage_counts 3쿼리 supabase mock.
- 사이클 173 (`test_cycle173_adapter_lock_stale_gate.py`) — 어댑터 게이트. **핵심**: 이 테스트는
  `get_recent_daily`/`max_bas_dd`/`fetch_daily_candles` 를 patch(모듈 함수 레벨) → pg 전환과 무관하게
  **대부분 PASS 유지**(어댑터 계약 = 모듈 함수 조합, SQL 무관). supabase 직접 체인 단언만 재평가.
- 사이클 187 (`test_cycle187_daily_read_retry.py` / `test_cycle187_ast_read_retry.py`) — supabase
  `execute_with_retry` 경유 단언 → pg `_with_retry` 로 전환되며 supabase 심볼 부재 → xfail.
- 사이클 192 (`test_cycle192_daily_purge_loop_batch.py` / `test_cycle192_ast_purge_loop.py`) —
  supabase `.not_.in_()`/`.delete(count,returning)` 체인 + AST `execute_with_retry` 미경유 가드 →
  pg 전환 재평가. **G-187-A2(purge SELECT/DELETE `_with_retry` 미경유) 불변식은 pg 로 계승**(Green 가드 유지).

> 상세는 Green 단계에서 M1-1 `test_cycleM0_config_and_safety.py::test_no_existing_db_module_changed`
> xfail 은퇴 선례 + M2a 선례 답습(근거 = supabase 체인 특유 mock → pg 단일 호출로 단순화).

## Red 유효성 확인
- production 2모듈(stock_master/stock_master_daily) 미변경 → `pg` 심볼 부재 →
  `patch.object(stock_master, "pg", create=True)` mock 발화 0 (모듈이 실제로 supabase 를 호출) →
  계약 단언 FAIL (단위). 실 PG 왕복 경로 부재(모듈이 supabase 호출) → FAIL/에러 (통합).
- 8영역 diff 0 + 호출부(scanner/strategies) 미변경 = 불변식 PASS.
