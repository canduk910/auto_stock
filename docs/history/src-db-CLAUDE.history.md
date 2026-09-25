> 원본: `src/db/CLAUDE.md` · 이관: 2026-09-17

`src/db/` 정본에서 걷어낸 경위·실측 수치·결정 근거. 규약 = [`README.md`](README.md).
원문 그대로 옮긴다(append-only). 사이클별 보고 원문은 [`../HARNESS_CHANGELOG.md`](../HARNESS_CHANGELOG.md) 에 있다.

이 정본은 Supabase(PostgREST) 시절에 쓰이기 시작해 asyncpg 로 이전(M0~M6)한 뒤에도
옛 어휘와 사이클별 문단이 켜켜이 쌓여 있었다. 아래 이관 블록은 `---` 두 줄 사이가 원문이고,
그 안의 사이클 번호·실측 수치·가드 케이스 번호도 원문 그대로다.

---

## pg.py — asyncpg 연결 풀 + 쿼리 헬퍼

### M0~M6 이전 — 쿼리 헬퍼의 PostgREST 대응 표기

각 헬퍼 뒤에 `result.data` · `result.data[0]` · `count="exact"` 대응을 병기하던 서술.

원문(`src/db/CLAUDE.md:12`, 2026-09-17 이관):

---

- 헬퍼: `fetch(sql, *args) -> list[dict]` (SELECT 다건, `result.data` 대응) / `fetchrow -> dict|None` (`result.data[0]`) / `fetchval` (스칼라, `count="exact"` 대응) / `execute -> str` (INSERT/UPDATE/DELETE) / `executemany` (배치). SQL 은 `$1`/`$2` 위치 파라미터.

---

→ CHANGELOG: Supabase→RDS 이전(M0~M6) 최상단 엔트리

### 사이클 187·M0~M6 — `execute_with_retry` → `_with_retry` 대체 경위

`supabase.py::execute_with_retry`(사이클 187) 가 asyncpg 전환으로 `pg._with_retry` 가 된 경위. 현행 계약만 정본에 남겼다.

원문(`src/db/CLAUDE.md:13`, 2026-09-17 이관):

---

- **`_with_retry(coro_factory, *, op="")`** (`supabase.py::execute_with_retry` 사이클 187 의 asyncpg 대체): `coro_factory()` 를 **연결 계열 예외 1회 재시도** (`_RETRY_EXCEPTIONS = (asyncpg.PostgresConnectionError, asyncpg.InterfaceError, asyncpg.exceptions.ConnectionDoesNotExistError, asyncio.TimeoutError)`, 각 시도 사이 `asyncio.sleep(0.2)` backoff), 소진 시 마지막 예외 raise(호출자 graceful 보존). `logger.warning("[pg_retry] op=...")` 단독 — `write_log` 미호출(사이클 72 이중 INSERT 차단). **read 전용** (`fetch`/`fetchrow`/`fetchval` 만 경유, 쓰기 `execute`/`executemany` 는 멱등 우려로 미경유). read 호출자는 각 db 모듈의 SELECT 경로 전반 — asyncpg 전환으로 개별 함수 리스트가 아닌 헬퍼 계층에서 일괄 흡수.

---

→ CHANGELOG: 사이클 187 행 · Supabase→RDS 이전(M0~M6) 최상단 엔트리

---

## asyncpg 계약 패턴

### M0~M6 이전 — PostgREST → asyncpg 매핑표

PostgREST 어휘(`.in_` · `count="exact"` · supabase 응답 문자열)를 기준으로 쓴 대조표. 현행은 SQL 문장 자체가 계약이다.

원문(`src/db/CLAUDE.md:20` · `src/db/CLAUDE.md:23-24`, 2026-09-17 이관):

---

- **TIMESTAMPTZ** — 쓰기 = `datetime.fromisoformat(now_kst_iso())` (aware datetime 바인딩). 읽기 str 계약(기존 supabase `+00:00`/`+09:00` ISO 문자열 응답 대응)이 필요하면 SQL 에서 `to_char(t.<컬럼>, 'YYYY-MM-DD"T"HH24:MI:SS.US+09:00')` 로 KST ISO 렌더 (사이클 53 B-4 `+09:00` 정합).
- **`.in_` → `ANY($1::text[])`** — PostgREST `.in_(...)` 는 SQL `WHERE col = ANY($1::text[])` 로 전환.
- **`count="exact"` → 별도 `fetchval`** — PostgREST 동봉 count 는 별도 `SELECT count(*)` fetchval 쿼리로 분리 (PostgREST `db-max-rows=1000` silent cap 없음).

---

→ CHANGELOG: Supabase→RDS 이전(M0~M6) 최상단 엔트리

---

## _kst.py — KST 공용 헬퍼

### 사이클 68 — 결정 2-B · 17 모듈 목록 · AST 가드 G-1~G-12 명세

어느 모듈이 언제 헬퍼로 넘어왔는지의 목록과 가드 케이스 번호. 현행 정본에는 금기와 예외만 남겼다. `to_date` 를 감싸는 모듈 목록(7 DATE 모듈 + positions `buy_date` + stock_master_daily purge)도 함께 걷어냈다.

원문(`src/db/CLAUDE.md:31-38`, 2026-09-17 이관):

---

- **`to_date(x: date|datetime|str|None) -> date|None`** (사이클 M6 라이브 핫픽스): DATE 컬럼 바인딩 값을 `date` 객체로 강제 변환 (never-raise). `date`/`datetime`→`.date()`, `str`→`date.fromisoformat` (실패 시 앞 10자 슬라이스 재시도 = 타임스탬프 ISO 문자열 호환), `None`→`None` (호출자 graceful 분기 보존), 파싱 실패→`None` + `logger.warning`. asyncpg 가 DATE 에 str 을 거부하는 계약 방어. **각 DB 모듈이 `to_date(target_date)` 로 바인딩 지점을 감싸는 것은 호출자 책임** (7 DATE 모듈 + positions `buy_date` + stock_master_daily purge 전 DATE 바인딩)
- **결정 2-B (사이클 68)**: 사이클 65 hotfix H2/H2-bis (`system_logs.py:44` + `main.py:126`) 인라인 패턴 → 본 헬퍼로 통일. 8 DB 모듈 (stock_master / parameter_recommendations / log_reports / system_config / strategy_config / kis_quote_accounts / market_regime_snapshots / backtest_runs) + 9 engine/api 모듈 (api/balance / api/condition / engine/strategy_base / engine/strategy / engine/backtest_engine / engine/scheduler / engine/boot_manager / engine/strategies/long_tail_volatility / engine/strategies/volatility_breakout) 사용. AST 영구 가드 5 케이스 (`tests/unit/db/test_cycle68_*.py`):
  - G-1 헬퍼 모듈 export 검증 (3 sub-case)
  - G-2~G-9 8 DB 모듈 KST 명시 (8 케이스)
  - G-10 AST 정적 가드: `datetime.utcnow()` 0건 + `src/db/` payload `datetime.now(timezone.utc)` 0건 (2 sub-case)
  - G-11 `stock_master.is_stale()` KST 비교 통일 (Q3, 1 케이스)
  - G-12 `date.today()` 일괄 → `today_kst()` 교체 (Q1 LOW, 1 케이스)
- 사이클 65 H2/H2-bis 영속 (변경 0) — `system_logs.py:44` + `main.py:126` 은 인라인 `datetime.now(KST).isoformat()` 유지 (행위 동일, 헬퍼 통일은 후속 사이클 인계 가능)

---

→ CHANGELOG: 사이클 68 행 · Supabase→RDS 이전(M0~M6) 최상단 엔트리

---

## trade_history.py — 거래 내역

### cycle273a/273b (2026-09-10) — `update_trade_status` opt-in 2인자 도입 경위

원문(`src/db/CLAUDE.md:43`, 2026-09-17 이관):

---

- `update_trade_status() -> int`: 체결/취소 시 PENDING row 새 status 갱신 + 영향 row 수 반환. 0건이면 호출자(OrderEngine) 가 체결통보 선행 race 로 판단해 COMPLETED 보정 INSERT. **cycle273a/273b(2026-09-10)** — `match_partial=True`(opt-in) 면 PARTIAL 행도 갱신 대상이고, `order_no=`(opt-in, 호출 6곳 전부 전달) 를 넘기면 WHERE 가 그 주문 행으로 좁혀진다(빈 문자열도 필터로 취급). 둘 다 미전달 = 종전 byte 동일 + 당일 KST 하한(datetime 바인딩)

---

→ CHANGELOG: cycle273a · cycle273b 행

### 사이클 53 B-4 — `get_trades_in_range` KST 경계 결함 시정 경위

PostgREST 시절의 UTC 해석 결함 서술. 금기(경계에 `+09:00` 명시)는 정본에 남겼다.

원문(`src/db/CLAUDE.md:44`, 2026-09-17 이관):

---

- **`get_trades_in_range(start_date, end_date, strategy=None)`**: `[start_date, end_date]` KST 범위 inclusive 조회. `start_iso = f"{date}T00:00:00+09:00"` / `end_iso = f"{date}T23:59:59.999999+09:00"` — **`+09:00` timezone 명시 필수** (TZ 없으면 PostgREST UTC 해석 → KST 00:00~09:00 거래 누락). `recommendation_engine` + `log_analysis_engine` 공유. 사이클 53 B-4 시정.

---

→ CHANGELOG: 사이클 53 행

### 사이클 M5 — `boot_manager` 직접 supabase.table() 호출 헬퍼 추출

원문(`src/db/CLAUDE.md:50`, 2026-09-17 이관):

---

- **`mark_pending_buys_completed(ticker)` / `get_recent_buy_strategy(ticker) -> str|None` / `get_today_buys_ticker_strategy() -> list[dict]`** (사이클 M5): `boot_manager` 의 직접 supabase.table() 호출(PENDING BUY 일괄 COMPLETED + 최근 BUY strategy 조회 + 오늘 BUY 조회)을 헬퍼로 추출 (split-brain 시정). 오늘 조회는 `+09:00` KST 명시 (boot_manager 의 TZ-naive `today.isoformat()` 버그 동반 시정)

---

→ CHANGELOG: Supabase→RDS 이전(M0~M6) 최상단 엔트리

---

## llm_buy_evaluations.py — AI 매수평가 기록

### cycle276 후속 B-2 — `list_by_order_nos` 주문번호당 1행 접기 결함

원문(`src/db/CLAUDE.md:64-67`, 2026-09-17 이관):

---

  ⚠️ cycle276 후속 B-2 — 종전에는 여기서 "주문번호당 최신 1행" 으로 접었다. ODNO 가 하루 단위로만
  유일해서 그 접기는 오래된 날짜의 평가를 응답에서 지우고, 그 날짜의 거래 행은 버튼이 비활성인데
  상세 조회(`get_by_order(..., trade_date=…)`)로는 멀쩡히 읽혔다. 접는 일은 이 층이 하지 않고
  호출자가 두 값으로 대조한다(라우트가 `"<trade_date>|<order_no>"` 복합 키로 응답).

---

→ CHANGELOG: cycle276 행

### cycle276 후속 B-4 — `signal_time_kst` → `signal_time_local` 개명

개명 사실만 걷어냈다. tz-naive 로컬 시각이라는 계약 서술은 정본에 남겼다.

원문(`src/db/CLAUDE.md:71-75`, 2026-09-17 이관):

---

  NUMERIC = `Decimal`(라우트가 `float` 로 사영 — cycle266 흰 화면). 시각 문자열 열은
  **`signal_time_local`** 이다(cycle276 후속 B-4 개명) — 값의 원천이 6전략 `datetime.now()`(tz 인자
  없음)·kojiro `datetime.now(KST)` 라 컨테이너 `TZ=Asia/Seoul` 전제에서만 KST 와 같고 값 자체는
  KST 를 보장하지 않는다. 실 PG 왕복 가드 =
  `tests/integration/test_cycle276_llm_eval_pg_roundtrip.py`(mock 은 str 바인딩을 통과시키고 실 PG 만 `DataError` 다).

---

→ CHANGELOG: cycle276 행

---

## daily_performance.py — 일일 실적

### 정산 시각 표기 16:10 — cycle283 D3 로 21:30

정산은 16:10 → 20:10 → 21:30(cycle283 D3) 으로 옮겨졌고 코드 정본은 `scheduler.TIME_SETTLEMENT = time(21, 30)` 이다.

원문(`src/db/CLAUDE.md:118`, 2026-09-17 이관):

---

- `upsert_daily_performance()`: 16:10 정산 시 당일 실적 기록. `daily_realized_pnl`/`daily_profit_rate` 모두 **실현손익 기준** (SELL 매도 실현분만 합산). 매도 0건 → 둘 다 0 정상. 평가손익은 `BalanceTable.eval_profit_loss` 별도 표시. 컬럼: total_asset / daily_profit_rate / daily_realized_pnl / net_external_cashflow / deposit / cumulative_return_rate (TWR 복리, 실현손익 누적)

---

→ CHANGELOG: cycle283 행

---

## system_logs.py — 시스템 로그

### 사이클 190 (2026-07-03) — `write_log` never-raise 전환 · 7/3 크래시

원문(`src/db/CLAUDE.md:125`, 2026-09-17 이관):

---

- `write_log(level, message)`: 이벤트/에러 기록. level: INFO / WARNING / ERROR / CRITICAL. **사이클 190 (2026-07-03) — never-raise 전환**: INSERT 를 try/except Exception 으로 감싸 **어떤 예외도 호출자에 전파하지 않는다** (관찰성 함수 계약). 실패 시 `logger.debug("[write_log_failed] ...")` 단독 — WARNING 이상 금지 (`_DbLogHandler` 가 다시 DB INSERT 를 시도하는 재귀 위험, 사이클 56-E 답습). 배경 = 7/3 07:59 `scheduler.py` start() 의 bare `await write_log` 가 Supabase HTTP/2 `RemoteProtocolError` 로 raise → 사이클 146 KisApiError graceful 분기 미해당 → 매매 프로세스 크래시(다운 2.7분 + 아침 task 2벌 재실행). src/ 직접 호출 72곳 무변경으로 단일 지점 영구 차단. AST 가드 `tests/unit/ast/test_cycle190_ast_write_log_guard.py` (broad except + except 내 raise 0 + debug 단독). **사이클 65 hotfix H2 (2026-06-06)**: INSERT 페이로드에 `"timestamp": datetime.now(KST).isoformat()` 강제 — 사이클 53 KST `+09:00` 패턴 답습. DB default (`now()` UTC) 의존 폐기 — 신규 INSERT 부터 KST 보장. **호환 경로 영속** (`src/main.py::_insert_log_to_db` H2-bis): 표준 logging 의 `_DbLogHandler` 위임 경로도 동일 KST 강제 — `logger.info()` / `logger.warning()` 등 모든 호출이 KST timestamp 로 저장 (write_log 직접 호출보다 호출 빈도 높음). AST 영구 가드: `tests/unit/db/test_system_logs_kst_timestamp.py` 2 케이스 (`src/` 전체 rglob INSERT 호출처 + write_log 함수 단위) — 향후 system_logs INSERT 추가 시 KST 누락 영구 차단

---

→ CHANGELOG: 사이클 190 행 · 사이클 65 행

### 사이클 72 (2026-06-08) — `_DbLogHandler` dedupe + 이중 INSERT 제거 전모

원문(`src/db/CLAUDE.md:126`, 2026-09-17 이관):

---

- **사이클 72 hotfix (2026-06-08) — `_DbLogHandler` 500ms TTL dedupe 캐시 + 11+ 사이트 write_log 직접 호출 제거 (이중 INSERT 영구 차단)**: 사이클 71 운영 실증 발견 silent 결함 (09:00~09:25 system_logs INSERT 205건 / distinct 71 = **평균 2.89x dup**, `[swing_poll]` 23x / `[stale_watcher]` 7.33x / `[stale_watcher_detail]` 확정적 2.00x) 시정. **결함 root cause**: `_DbLogHandler` (`src/main.py:137`) 가 `record.name.startswith("src.")` 모든 logger emit → `_insert_log_to_db` 위임 INSERT + 같은 emit 사이트가 `await write_log(...)` 동시 호출 → 양쪽 경로 INSERT 누적. **옵션 A' (호출자 정정 11+ 사이트)**: `realtime/websocket.py` (`[ws_heartbeat]`) + `engine/stale_watcher_core.py` 4 사이트 (`[stale_watcher]` / `[stale_force_retry]` / `[stale_force_retry_cap]` / `[stale_priority_resubscribe]`) + `engine/stale_diagnostics.py` (`[stale_watcher_detail]`) + `engine/stale_session_recovery.py` 3 사이트 (`[silent_inactive_recovery_cap]` / `[silent_inactive_force_reconnect]` / `[scan_loop_delta]`) + `engine/stale_universe_guard.py` (`[universe_excluded]`) + `engine/scanner.py` (`[priority_drop]`) + G-6 AST 추가 검출 11 사이트 (`engine/boot_manager.py` `[cash_usage_ratio]` / `engine/scheduler.py` L735/L842/L1730/L1825/L1834/L2657 등) 의 `await write_log(...)` / `await _write_log(...)` / `asyncio.create_task(_write_log(...))` 호출 전수 제거. `logger.info/warning(...)` 단독 유지 → `_DbLogHandler` 위임 단일 INSERT 보장. **옵션 D (`_DbLogHandler` dedupe 캐시, `src/main.py:137-170`)**: `_DEDUPE_TTL_SECS = 0.5` 모듈 상수 + `_dedupe_cache: dict[str, float]` 인스턴스 변수 (message → last_emit_monotonic) + `emit()` 진입 직후 `time.monotonic()` 비교 → 동일 메시지 500ms 내 중복 emit 두 번째 INSERT skip + lazy evict (100 항목 cap, TTL 경과 항목 정리). 미래 신규 emit 사이트 silent 결함 runtime 안전망. **AST 영구 가드 3 신설**: G-6 (`tests/unit/ast/test_cycle72_ast_no_logger_write_log_pair.py`, `src/` 전체 rglob 각 `write_log` 호출 ±5 줄 동시 `logger.*` 호출 0건) + G-7 (`tests/unit/main/test_cycle72_db_log_dedupe_structure_ast.py`, `_DEDUPE_TTL_SECS = 0.5` 상수 + dedupe 캐시 dict + `time.monotonic` 비교 정적 검증) + G-8 (`tests/unit/main/test_cycle72_insert_log_kst_persistence_ast.py` 2 케이스, 사이클 65 H2-bis KST 영속 회귀 가드 보강). **회귀 가드 18 케이스 (6 파일)**: `tests/unit/engine/test_cycle72_no_duplicate_insert_per_site.py` 11 + `tests/unit/main/test_cycle72_db_log_dedupe.py` 3 (freezegun + mock supabase) + AST 4. F-1 통합 테스트 2건 (`test_boot_cash_usage_ratio.py` + `test_boot_eager_refresh.py`) obsolete `calls.write_log` assertion 옵션 C 채택 제거 (사이클 72 의도 일치, G-A 단위 가드로 회귀 가드 영속). **사이클 65 H2/H2-bis 영속 (변경 0)**: `system_logs.py:44` + `main.py:131` 인라인 KST 패턴 유지 — G-8 회귀 가드 PASS 영속. **silent 결함 영구 차단 9 회 누적** (사이클 60/64/65#1/65#2/65#3/66/67/68/72). **F-2 (HIGH 운영 영향) WebSocket dup 핵심 영역**: 운영 측정 dup 상위 4건 = `src.realtime.websocket` (ACK / 구독 / 해제 / 5xx) → 사이클 73 카드 #19 인계 (G-6 AST 가드 영역 확장 검토)

---

→ CHANGELOG: 사이클 72 행

### 사이클 56-E (2026-06-04) — `safe_write_log` 도입 경위

원문(`src/db/CLAUDE.md:127`, 2026-09-17 이관):

---

- **`safe_write_log(level, message, *, fallback_debug=None)`** (사이클 56-E, 2026-06-04): `write_log` 의 graceful skip 변형. Supabase 장애 등 예외 발생 시 전파 없이 `logger.debug` 만 발화. `fallback_debug` 명시 시 그 문자열을 debug 메시지로 사용, None 시 기본 메시지 `"[safe_write_log] {message[:80]} 실패: level={level}"`. `order_engine.py` 내 `try: await write_log / except Exception: logger.debug` 동형 패턴 4곳 통합 — `[stock_master_miss]` / `[stock_master_miss stale]` / `[market_closed_blocked]` / `[positions_reconciliation]`

---

→ CHANGELOG: 사이클 56-E 행

### 사이클 6 (2026-05-20) — `search_logs` PostgREST 어휘 서술

원문(`src/db/CLAUDE.md:129`, 2026-09-17 이관):

---

- **`search_logs(q, *, level=None, start=None, end=None, limit=200) -> {logs, total, has_more}`** (사이클 6 통합, 2026-05-20): 키워드 substring 검색. `ilike("message", "%q%")` 대소문자 무시. `level` 이 None/`"ALL"` 이면 무필터, 그 외 `eq("log_level", level)`. `start`/`end` 는 ISO 8601 시각 직접 받아 `gte`/`lte`. `limit` 1~1000 clamp (기본 200, 최대 1000). 빈 `q` ValueError. `has_more = total > len(logs)` — 200건 초과 시 UI 가 "키워드 좁히기" 안내. 라우트 `/api/logs/search` 와 1:1

---

→ CHANGELOG: 사이클 6 행

### 사이클 150·175 — PostgREST row-cap silent 결함과 루프 배치 시정 전모

원문(`src/db/CLAUDE.md:130-131`, 2026-09-17 이관):

---

- **`purge_old_logs() -> {info_deleted, high_deleted, elapsed_ms}`** (사이클 6 통합, 2026-05-20): 등급별 retention 정책 자동 정리. INFO 등급 `timestamp < now_kst - 2 days` DELETE / WARNING/ERROR/CRITICAL 등급 `timestamp < now_kst - 30 days` DELETE. **안전 가드**: 내부 헬퍼 `_purge_by_cutoff(cutoff_iso, level_filter)` 가 `cutoff_iso=None` 이면 `RuntimeError("cutoff must not be None")` raise (WHERE 누락 사고 절대 차단). **사이클 175 (2026-06-24) — PostgREST row-cap silent 결함 항구 시정 (루프 배치)**: 사이클 150 의 단발 `SELECT(id).limit(MAX_PURGE_BATCH=100_000)` 이 Supabase PostgREST `db-max-rows=1000` 기본 cap 에 silent 절단 → 1회 호출당 최대 1000행 삭제 (`[log_retention] info_deleted=1000` 매일 정확히 1000) → 하루 1회(20:10) × 1000 vs INFO 30K+/일 생성 → 640K+ 적체 → 242MB 비대. 시정 = `_purge_by_cutoff` 가 `SELECT(id).limit(PURGE_SELECT_BATCH=1000) + DELETE in_(ids)` 를 **drained 까지 루프** (ids 빈 리스트 또는 마지막 페이지 `len(ids) < PURGE_SELECT_BATCH` 시 종료) + 안전 cap 3중 (`PURGE_MAX_ITERATIONS=2000` 런어웨이 + `MAX_PURGE_BATCH=100_000` 누적 상한 = 단일 purge 호출 settlement 폭주 차단 + 마지막 페이지 조기 종료). migration/RPC/PostgREST `db-max-rows` 설정 변경 **0** (2-step + supabase-py SELECT.limit/DELETE.in_ 구조 유지, DELETE chain `.limit()` 미사용 = 사이클 6 AttributeError 영구 차단). retention 1회가 backlog 전량 드레인 → 재적체 방지. 운영 backlog 665K행 (INFO>2일 642K + WARNING/ERROR>30일 23K) 은 메인 세션이 raw SQL + `VACUUM FULL system_logs` 로 즉시 드레인 (535→368MB). 회귀 가드 = `tests/unit/db/test_cycle175_log_retention_loop.py` (8). INFO 1행 영구 로그 `[log_retention] info_deleted=N high_deleted=M elapsed_ms=K` (이제 N/M 이 1000 cap 안 걸림). 시점: `_settle` → `_log_analysis_engine` *후* + `_reset_daily_state()` *전* (분석이 system_logs 읽은 후 정리). 예외는 scheduler 가 graceful (`[log_retention_skip]` INFO + 다음 사이클 재시도)
- 상수: `INFO_RETENTION_DAYS=2` / `HIGH_RETENTION_DAYS=30` / `HIGH_LEVELS=("WARNING","ERROR","CRITICAL")` / `MAX_PURGE_BATCH=100_000` (단일 purge 호출 누적 상한) / **`PURGE_SELECT_BATCH=1000`** (사이클 175 — per-iteration SELECT limit, PostgREST `db-max-rows=1000` 정합) / **`PURGE_MAX_ITERATIONS=2000`** (사이클 175 — 루프 런어웨이 차단) / `SEARCH_DEFAULT_LIMIT=200` / `SEARCH_MAX_LIMIT=1000`

---

→ CHANGELOG: 사이클 175 행

---

## log_reports.py — 일일 로그 분석 리포트

### cycle283 — `upsert_external_report` 순수 INSERT 계약 반증 경위

옛 계약과 그 반증 과정. 현행 계약(SET 절 교집합 공집합)만 정본에 남겼다. cycle249 도입 시점의 20:10 병행 서술도 함께 걷어냈다.

원문(`src/db/CLAUDE.md:138`, 2026-09-17 이관):

---

- **`upsert_external_report(*, target_date, provider, model, summary, findings, report_md) -> dict`** (cycle249) — 20:20 KST 클라우드 루틴 결과를 `ext_*` 6컬럼에만 저장한다. `INSERT … ON CONFLICT (target_date) DO UPDATE SET` 절이 **ext_* 6개뿐**(`ext_provider`/`ext_model`/`ext_summary`/`ext_findings`/`ext_report_md`/`ext_created_at`) — 기존 컬럼(summary/findings/metrics/model + 토큰 5)은 **절대 SET 절에 넣지 않는다**. 한 컬럼이라도 새면 20:10 OpenAI 리포트(병행 비교 기준선)가 조용히 지워진다. 행이 없는 날(20:10 실패)의 INSERT 경로는 기존 컬럼을 하드코드 SQL 리터럴(`''`/`'[]'::jsonb`/`'{}'::jsonb`/`NULL`)로 채워 호출자 데이터가 심길 여지를 원천 차단한다 — 다만 이 빈 값 채우기는 "나중에 튕기지 않게" 하는 조치가 아니다. ⚠️ **cycle283 정정** — 종전 여기에는 "이 함수가 먼저 placeholder 를 만들면 그날의 `insert_log_report` 는 UNIQUE 충돌로 `None` 을 반환한다" 고 적혀 있었다. 그 서술은 **반증됐다**: `insert_log_report` 도 이제 `ON CONFLICT (target_date) DO UPDATE` 라 순서가 뒤집혀도 base 9컬럼을 정상 기록한다. 정산이 21:30 으로 밀린 뒤에는 이 함수(20:34 실측)가 먼저 오는 것이 오히려 정상 순서다. DB 규약 준수 — JSONB raw list 바인딩 + `::jsonb` 캐스트, DATE `to_date()`, TIMESTAMPTZ `datetime.fromisoformat(now_kst_iso())`.

---

→ CHANGELOG: cycle249 행 · cycle283 행

---

## system_config.py — 시스템 설정 키-값 헬퍼

### 사이클 189 계보 — read 경로 retry 함수 열거

원문(`src/db/CLAUDE.md:143`, 2026-09-17 이관):

---

- **read 경로 `pg._with_retry` 경유 (asyncpg, 사이클 189 계보)**: `get_cash_usage_ratio`/`get_auto_regime_adjust`/`_get_bool_or_none`/`get_buy_block_mode`/`_get_float_or_default`/`_get_bool_or_default`/`_get_int_or_default`/`_get_str_or_default_UNUSED`/`_get_string_or_none` 등 read 는 `pg.fetch`/`fetchrow`/`fetchval` (= `_with_retry` 내장) 경유 — connection 계열 예외 1회 재시도, 기존 폴백 기본값 불변. 쓰기(`_upsert`/`_set_*`)는 `pg.execute` (retry 미경유)

---

→ CHANGELOG: 사이클 189 행

### cycle294 → cycle295 — 전환 다이얼 5키 → 4키

다이얼 수가 5 에서 4 로 준 경위. 현행 4키와 폐기 키 재사용 금지는 정본에 남겼다.

원문(`src/db/CLAUDE.md:145`, 2026-09-17 이관):

---

- **cycle294 (2026-09-14) — 3단계 전환 다이얼 4키**(cycle295 로 5→4) (전부 `system_config` 축, 전략 `DEFAULT_PARAMS`·`param_catalog` **편입 금지**): `get_tick_channel_switch_enabled()`/`set_tick_channel_switch_enabled(enabled)` (`tick_channel_switch_enabled`, bool — **살아 있는 구독의 전환만** 끈다) · `get_tick_channel_switch_offset_secs()` (`tick_channel_switch_offset_secs`, float — 프리장 종료 뒤 전환까지, 클램프는 읽는 쪽) · `get_tick_channel_switch_ack_timeout_secs()` (`tick_channel_switch_ack_timeout_secs`, float — HIGH make-before-break ACK 대기) · `get_tick_channel_revert_probe_secs()` (`tick_channel_revert_probe_secs`, float — 자동 원복 측정 시점. 기본값은 새 숫자가 아니라 `stale_diagnostics.SUBSCRIBE_GRACE_SECS` 재사용이고 그 상수의 단일 정의처는 거기다). 전부 `_get_bool_or_none`/`_get_float_or_none` 경유 = **캐시 0 · TTL 0**. 키 부재·조회 실패는 `None` → 엔진이 **현재 값 유지**(기본값 되돌림 금지). 소비 = `engine/tick_channel_mode.refresh_switch_params()`(5분·120초 폴링) + `PUT /api/realtime/tick-channel-mode` 의 선택 필드 `switch_enabled`(즉시 반영)

---

→ CHANGELOG: cycle294 행 · cycle295 행

### 사이클 M5 — `auto_start` 헬퍼 추출 경위

원문(`src/db/CLAUDE.md:147`, 2026-09-17 이관):

---

- **`get_auto_start() -> bool` / `set_auto_start(enabled)`** (사이클 M5): 키 `auto_start`, JSONB `{"value": bool}` 왕복. `main.py` lifespan + `routes/strategies.py` auto-start 라우트가 직접 supabase.table() 호출하던 것을 헬퍼로 추출 (M5 split-brain 시정)

---

→ CHANGELOG: Supabase→RDS 이전(M0~M6) 최상단 엔트리

### 사이클 193 (2026-07-04) — task 신선도 마커 도입 경위

원문(`src/db/CLAUDE.md:148`, 2026-09-17 이관):

---

- **task 신선도 마커 (사이클 193, 2026-07-04)**: `get_task_last_success(task_label) -> str | None` (키 `task_last_success_<label>`, `_get_string_or_none` 경유 = 189 retry 자동 수혜) / `set_task_last_success(task_label, iso_ts)` (upsert 패턴, 쓰기 = retry 미경유 영속). `task_loop_helper.run_periodic_task_loop` 의 `immediate_skip_if_fresh_hours` 게이트 전용 — 재시작 immediate run 이 N시간 이내 성공 마커 존재 시 skip (아침 프리마켓 burst 완화). 값은 KST ISO (`now_kst_iso()`). **`get_task_last_success_bulk(task_labels) -> dict` (cycle285)** — 위 마커를 `key = ANY($1)` **단일 쿼리**로 묶어 조회한다(`GET /api/market-ops` 야간작업 타임라인이 폴링마다 라벨 수만큼 왕복하지 않도록). 결측 라벨은 반환 dict 에 **키 자체가 없다**(빈 문자열 아님). 쿼리 실패는 빈 dict(fail-open)

---

→ CHANGELOG: 사이클 193 행 · cycle285 행

### 사이클 2 → 사이클 I — 매수 가드 4모드가 게이트이던 시절

매크로 레짐은 사이클 I(2026-08-03)에서 매수 차단·축소 기능이 빠졌다. 네 모드와 임계 4키는 대시보드·자문 payload 표시용으로 남아 있다.

원문(`src/db/CLAUDE.md:156-160`, 2026-09-17 이관):

---

- **매수 가드 4 모드 + 4 임계값**:
  - `get_buy_block_mode() -> str` / `set_buy_block_mode(mode)`: 키 `buy_block_mode`, 기본 `HARD` (사이클 2 회귀 보존). 4 모드 외 `ValueError`
  - `get_buy_block_thresholds() -> BuyBlockThresholds` (Pydantic) / `set_buy_block_thresholds(vix_threshold=, fg_high_threshold=, fg_low_threshold=, defensive_enabled=)` 부분 갱신
  - 4 키: `buy_block_vix_threshold` (25.0) / `buy_block_fg_high_threshold` (85.0) / `buy_block_fg_low_threshold` (15.0) / `buy_block_regime_defensive_enabled` (true)
  - **.env fallback 없음** — 운영 가변 (DB 미설정 → 코드 디폴트)

---

→ CHANGELOG: 사이클 2 행 · 사이클 I 행

### 사이클 23 — AI 자문 자동 적용 토글 도입

원문(`src/db/CLAUDE.md:161-162`, 2026-09-17 이관):

---

- **사이클 23 AI 자문 자동 적용 토글**:
  - `get_auto_apply_enabled() -> bool` / `set_auto_apply_enabled(value)`: 키 `auto_apply_enabled`. 기본 **False** (안전 우선). .env fallback 없음 — 운영자 명시 활성화 후에만 P3 자동 적용 작동

---

→ CHANGELOG: 사이클 23 행

### 사이클 62·64·65 — scanner 구독 필터 2종의 도입 경위와 자문 결정

가격 필터(사이클 64, 사이클 62 의 mode 폐기)와 거래대금 필터(사이클 65)의 자문 Q번호·답습 관계. 현행 정본에는 두 필터의 계약만 남겼다.

원문(`src/db/CLAUDE.md:163-179`, 2026-09-17 이관):

---

- **사이클 65 거래대금 동행 필터 (2026-06-06) — scanner 단계 작전주 차단 보강 (사이클 64 가격 필터 답습 + Q7-5 갭상승 회피 효과 보강)**:
  - `get_trade_amount_filter() -> TradeAmountFilter` (Pydantic) / `set_trade_amount_filter(*, min_amount=None)` 부분 갱신
  - **단일 키**: `trade_amount_filter_min` (int, default 0 = 비활성, 원 단위)
  - 범위 외 ValueError (음수)
  - **.env fallback 없음** — 운영 가변 (DB 미설정 → 디폴트 0)
  - **적용 위치**: `src/engine/scanner.py::subscribe_filtered_stocks` 진입점 hook (사이클 64 `_apply_price_filter` 직후 순차 — Q3 자문)
  - **Q2 옵션 C 통합 폴백** (자문 핵심): `scanner.ticker_market_info["trade_amount_raw"]` (신규 키, 원 단위) 1순위 + `stock_master.raw.acml_tr_pbmn` 2순위 + graceful (KIS 호출 0건 추가)
  - 60s TTL 캐시 (`src/engine/scanner.py::_get_trade_amount_filter_for_scanner` 모듈 전역) + `invalidate_trade_amount_filter_cache_scanner()` (Q7-1 KIS LMS chain 차단 — unsubscribe 발화 0건)
  - **Q6-1 09:00 race graceful**: `acml_tr_pbmn=0` (양쪽 miss) = graceful 통과 (시스템 매매 무용 차단 영속)
  - **매수 진입 전용** (사이클 38 명문화) + **보유/익일청산 절대 보호** (사이클 64 Q1 옵션 D 3 중 안전망 헬퍼 재사용)
- **사이클 64 가격 필터 (2026-06-06) — scanner 단계 종목 필터 (사이클 62 단순화 + 위치 변경)**:
  - `get_price_filter() -> PriceFilter` (Pydantic) / `set_price_filter(*, min_price=None, max_price=None)` 부분 갱신
  - **2 키** (사이클 62 mode 폐기): `price_filter_min` (int, default 0 = 비활성) / `price_filter_max` (int, default 0 = 비활성)
  - 범위 외 ValueError (음수 / `min_price > max_price` 단 둘 다 >0 일 때)
  - **.env fallback 없음** — 운영 가변 (DB 미설정 → 코드 디폴트 0/0)
  - **적용 위치**: `src/engine/scanner.py::subscribe_filtered_stocks` 내부 단일 hook (사이클 62 `risk.on_tick` 폐기, Q4 자문 옵션 A). 60s TTL 캐시는 `src/engine/scanner.py::_get_price_filter_for_scanner` 모듈 전역 (`time.monotonic`, 사이클 56-E 답습) + `invalidate_price_filter_cache_scanner()` 즉시 무효화 (PUT 직후 호출, **unsubscribe 발화 0건** — Q7-1 KIS LMS chain 차단)
  - **WebSocket 구독 대상 필터** (매수 진입 전용 = 사이클 38 명문화) — 임계 외 종목은 시세 구독 자체 차단 + 후보 풀 축소. 매도/익일청산/손절/15:20 강제청산 영향 0. **보유/익일청산 절대 보호** (Q1 자문 옵션 D 3 중 안전망 — 공통 헬퍼 + early-return + AST keyword 의무 가드, 사이클 32 R4 universe guard 답습)

---

→ CHANGELOG: 사이클 62 행 · 사이클 64 행 · 사이클 65 행

---

## kis_quote_accounts.py — 보조 KIS 시세 수신 계좌 풀

### 사이클 189 계보 — read 4함수 retry 경유 경위

원문(`src/db/CLAUDE.md:185-186`, 2026-09-17 이관):

---

- **read 4함수 `pg._with_retry` 경유 (asyncpg, 사이클 189 계보)**: `list_accounts`/`get_account`/`get_account_by_label`/`get_credentials_for_token_manager` — `pg.fetch`/`fetchrow` 로 connection 계열 예외 1회 재시도(7/1 실측 `[kis_quote_accounts] list 실패` 11건/일 흡수), 기존 graceful·캐시 로직 불변. 쓰기(insert/update/delete)는 `pg.execute` (retry 미경유)
- **`list_accounts` 60s TTL 메모리 캐시**: 모듈 전역 `_list_cache` / `_list_cache_expires_at` + `invalidate_list_cache()` + `_LIST_CACHE_TTL=60.0`. `time.monotonic()` 비교 → TTL 내 캐시 hit (DB 호출 0). `active_only=True/False` 키 분리. DB 예외 + 캐시 있음 → stale 반환 (graceful), 캐시 없음 → 빈 리스트 (회귀 보존). INSERT/UPDATE/DELETE 직후 `invalidate_list_cache()` — 운영 토글 즉시 반영. Settings/Dashboard 30s 폴링 + 컨테이너 재시작 race + supabase HTTP/2 stale connection 결함 대응

---

→ CHANGELOG: 사이클 189 행

---

## strategy_funnel.py — 조건검색 단계별 추적

### 사이클 34 → 145 → 41 → 171 — `insert_snapshot` 변천

사이클 34 의 `.insert(row)` 가 만든 중복 INSERT 결함(6/15 BFB step_no=1 = 8 row)과 사이클 145 의 UPSERT 전환(migration 035), 사이클 41 형식 확장, 사이클 171 `is_provisional` 추가 경위.

원문(`src/db/CLAUDE.md:196`, 2026-09-17 이관):

---

- `insert_snapshot(target_date, strategy_id, step_no, step_name, survived_count, survived_tickers, excluded_count, excluded_sample, step_conditions=None, is_provisional=False)`: 단일 단계 snapshot **UPSERT** (사이클 145 (2026-06-16) — `.upsert(on_conflict="target_date,strategy_id,step_no")` 전환 영속). **사이클 171 (2026-06-22)** — `is_provisional: bool = False` 인자 추가 (migration 040 `is_provisional BOOLEAN NOT NULL DEFAULT FALSE`). True = 16:20 저녁 잠정 캡처 (전일 마스터 + 16:10 basics 기준) / False (기본) = 09:30 자동 + 수동 trigger (확정). payload 동행 (기존 호출자 미지정 → False, 회귀 0). 사이클 34 시점 = `.insert(row)` + UNIQUE `(target_date, strategy_id, step_no, snapshot_at)` → snapshot_at 매번 갱신 → 중복 INSERT 가능 → 운영 DB 6/15 BFB step_no=1 = 8 row 결함. 사이클 145 시정 = `.upsert(on_conflict=...)` + migration 035 UNIQUE 변경 (snapshot_at 키 폐기) → 같은 `(target_date, strategy_id, step_no)` 영역 = 최신 값 1 row. snapshot_at = supabase DEFAULT now() UPSERT 시 자동 갱신. **사이클 41 (2026-05-22)**: `survived_tickers: list[str \| dict]` 호환 (string 사이클 34 형식 + dict `{ticker, name}` 사이클 41 형식), `excluded_sample: list[dict]` (`{ticker, name, reason}` 수치 포함 사유), `step_conditions` 옵셔널 (단계 조건 명시 — UI 툴팁). DB JSONB 스키마는 변경 없음 (native dict 지원)

---

→ CHANGELOG: 사이클 34 행 · 사이클 145 행 · 사이클 171 행

### 사이클 39·41·171 — 자동 hook 과 공통 헬퍼 추출 경위

원문(`src/db/CLAUDE.md:201`, 2026-09-17 이관):

---

- 호출: `POST /api/strategy-funnel/snapshot` 수동 trigger + **사이클 39 자동 hook** (`scheduler._auto_capture_funnel_snapshots`, 09:30 `_scan_loop` 첫 진입 시 일일 1회 자동 발화). **사이클 39+41**: BFB/VCP/donchian `prepare()` 가 8단계 `_record_funnel_step` hook 으로 각 단계 통과/탈락 ticker + 수치 포함 사유 (`reason="음봉 비율 35% > 30%"` 등) 캡처 → 단계별 + 최종 (`step_no=99`) DB row 모두 저장. `_reset_daily_state` 동행 reset. **사이클 171 (2026-06-22)** — 공통 헬퍼 `scheduler.capture_funnel_snapshots(registry, *, is_provisional)` 추출 (3 호출처 공유: 09:30 자동 / 16:20 저녁 잠정 / 수동 trigger). 09:30 자동 + 수동 trigger 모두 단계별 + step_no=99 캡처 (수동 trigger 가 종전 step_no=99 단독 → 단계별 전체로 전환, is_provisional=False)

---

→ CHANGELOG: 사이클 39 행 · 사이클 171 행

---

## stock_master.py — 종목 마스터 캐시

### 사이클 162 (2026-06-18) — `pending_next_day_clear` 도입 경위

알테오젠·알지노믹스 6/17 15:20 강제청산 누락 사고. 이 항목은 `stock_master.py` 절 안에 있었고, 정본에서는 `pending_next_day_clear.py` 자기 절로 옮겼다.

원문(`src/db/CLAUDE.md:211`, 2026-09-17 이관):

---

- **사이클 162 (2026-06-18) — `pending_next_day_clear` 테이블 + CRUD 신규 (HIGH 익일청산큐 영속화)**: 알테오젠/알지노믹스 6/17 15:20 강제청산 누락 (EC2 재기동 시 `_pending_next_day_clear: set[tuple]` 메모리 휘발) 결함 시정. `supabase/migrations/038_pending_next_day_clear.sql` = `(target_date DATE, ticker TEXT, strategy_id TEXT)` 복합 PK + `created_at TIMESTAMPTZ`. `src/db/pending_next_day_clear.py` 4 CRUD = `save_pending_ndc(target_date, ticker, strategy_id)` / `delete_pending_ndc(ticker)` / `load_pending_ndc(target_date)` / `purge_pending_ndc_before(target_date)`. scheduler `_execute_next_day_clear` 등록 2 사이트 (nxt_not_tradable / nxt_open_missing) + `_drain_pending_next_day_clear` finally DELETE + `_reset_daily_state` fire-and-forget purge. boot_manager `boot()` 마지막 단계 `load_pending_ndc(today)` → 메모리 set 복구 (사이클 149 VI seed 패턴 답습). DB 실패 시 메모리 보존 graceful (사이클 88 답습). 회귀 가드 7 케이스. 매매 안전성 무영향 (재기동 후 알테오젠/알지노믹스 패턴 재발 차단). 운영 DB 적용 완료 (Supabase MCP).

---

→ CHANGELOG: 사이클 162 행

### 2026-07-24 — `list_by_filter` SELECT `name` COALESCE 폴백 시정 경위

원문(`src/db/CLAUDE.md:212`, 2026-09-17 이관):

---

- **2026-07-24 — `list_by_filter` SELECT `name` COALESCE 폴백 (전체상장 종목명 미표시 시정)**: 전체상장 스캔 전략(특히 kojiro, ~979 후보)의 funnel 후보가 종목명 없이 종목번호만 표시되던 버그. 근본 원인 = 마스터파일 한글명은 `master_raw->>'hts_kor_isnm'`(kis_master.py:242)에만 있고 `name` 컬럼(CTPF1002R `upsert_one` 전용, 소형주 미조회 시 빈값)·`raw`(CTPF1002R)는 비어있으며 SELECT 가 master_raw 미조회. **시정** = `_build_sql` SELECT 의 `name` → `COALESCE(NULLIF(name, ''), NULLIF(TRIM(master_raw->>'hts_kor_isnm'), ''), '') AS name` (① CTPF 이름 우선 → ② 마스터파일 한글명 고정폭 패딩 TRIM 폴백 → ③ 둘 다 없으면 `''` NULL-guard = 기존 소비자 `row.get("name","")` None 회귀 차단). **G-AST1(사이클 81) 준수** = master_raw 읽기(SELECT)만, `upsert_master_raw` 등 쓰기 경로·name 컬럼 write 무변경. `AS name` 별칭으로 반환 dict 키 불변 → 6전략(kojiro/donchian/VCP/VB/LTV/BFB)이 `list_by_filter` 소비 + kojiro `_scan_universe`(519)가 `ticker_names[ticker]=name` 채움 → funnel `_resolve_ticker_name` 해소, **전략 코드 변경 0**. 회귀 가드 `tests/unit/db/test_name_coalesce_list_by_filter.py`(2 = SQL 캡처 COALESCE/컬럼계약) + `tests/integration/test_name_coalesce_list_by_filter.py`(5 = CTPF우선/master_raw폴백/TRIM/빈값''/mcap필터·stage_counts 불변, pg_harness postgres:15 실 왕복). 매매 안전성 무영향 (매수 진입 *전* 조회 계층, risk/order_engine/realtime diff 0, 사이클 38 명문화). **잔여 LOW**: funnel step1(union ~3577)은 filtered rows 루프 밖이라 여전히 이름 미해소 가능 — 후보(step2~9)는 전부 해소.

---

→ CHANGELOG: 2026-07-24 행

### 사이클 170 (2026-06-20) — `return_stage_counts` 인자 추가 경위

원문(`src/db/CLAUDE.md:213`, 2026-09-17 이관):

---

- **사이클 170 (2026-06-20) — `list_by_filter(return_stage_counts: bool = False)` 인자 추가 (funnel 관찰성, 카드 A)**: True 시 단일 필터 루프 내 단계별 생존 ticker 누적 후 `(filtered, {"union_tickers", "mcap_tickers", "trade_tickers"})` 튜플 반환. union = index/형식/exclude 통과 (시총·거래대금 컷 *전*) / mcap = 시총컷 후 / trade = 거래대금컷 후 (= 최종 filtered, 순서 정합). False (기본) = 현행 list (**기존 호출자 전원 미지정 → 회귀 0**). cap 미적용 — 정확 count 보존 (소비처 `_record_funnel_step` 가 survived 리스트 200 cap + survived_count 정확 기록, rows 는 fetch buffer cap). **필터 로직/임계/순서/limit break 불변 = 매수 풀 행위 보존** (G-A-1 HIGH = `return_stage_counts=True` filtered == False 결과 원소·순서). 호출자: donchian `_scan_universe` (`self._scan_stage_counts` 보관 → prepare step1=union / step2=trade collapse 차단). 회귀 가드 `tests/unit/db/test_cycle170_card_a_stage_counts.py` 6 케이스. 매매 안전성 무영향 (관찰성 전용).

---

→ CHANGELOG: 사이클 170 행

### 사이클 153 (2026-06-16) — KOSPI200/KOSDAQ150 인자 추가 경위

원문(`src/db/CLAUDE.md:214`, 2026-09-17 이관):

---

- **사이클 153 (2026-06-16) — `list_by_filter()` KOSPI200 / KOSDAQ150 인자 추가**: 사용자 결정 Q2=A `is_kospi200: bool | None = None` + `is_kosdaq150: bool | None = None` 인자 (사이클 108 nxt_tradable 패턴 답습). 양쪽 모두 True 시 **OR 합집합** (donchian_swing FUNNEL_STAGES[0] "코스피200+코스닥150 합집합" 의무 정합). 한쪽만 True/False 시 AND (PostgREST `.eq()` 인덱스 활용 = `idx_stock_master_is_kospi200` + `idx_stock_master_is_kosdaq150` 부분 인덱스). 둘 다 None 시 무필터 (회귀 보존). **사이클 121 (2026-06-12) silent 결함 시정** = donchian_swing.py::_scan_universe() 영역 인자 전달 누락. 운영 DB 실측 (2026-06-16) = KOSPI200 1796 종목 + KOSDAQ150 149 종목 = ~1945 합집합. 회귀 가드 = `tests/unit/db/test_cycle153_list_by_filter_index_flags.py` (5 케이스). 매매 안전성 무영향 영속 (사이클 38 명문화 + scanner 매수 진입 전 한정).

---

→ CHANGELOG: 사이클 153 행

### 사이클 108 (2026-06-11) — `list_by_filter` 신규 도입 전모

도입 시점의 시그니처와 Python-side JSONB 필터 서술. 사이클 205(2026-07-09)가 시총·거래대금 컷을 생성 컬럼 DB-side 필터로 옮기고 오버페치를 없애면서 이 서술은 현행과 어긋났다.

원문(`src/db/CLAUDE.md:215`, 2026-09-17 이관):

---

- **사이클 108 (2026-06-11) — `list_by_filter()` 신규 메서드 (Plan Phase A 완료, VB/LTV/BFB stock_master 베이스 전환 + KIS volume-rank API 100% 폐기)**: 사이클 104 인계 Q5=B (LOW 위험 자문 생략) + 사이클 107 raw 보강 의존성 해소 완료 → Plan Phase A 데이터 활용 가능 → 사이클 108 = `list_by_filter()` 신규 메서드 + VB/LTV/BFB `_scan_universe()` 전환 통합. 사용자 결정 Q1=A 시총 = `hts_avls` (KIS FHKST01010100, 백만원 단위) + Q2=A 통합 단일 사이클 (3 전략 동시 전환) + Q3=C 4 필터. **`list_by_filter(*, market=None, min_market_cap=0, min_trade_amount=0, exclude_tickers=None, nxt_tradable=None, limit=500)` 시그너처** (cycle 108 도입 시점, 모두 keyword-only. 후속 인자 = 사이클 153 `is_kospi200`/`is_kosdaq150` + 사이클 170 `return_stage_counts` — 각 절 참조. `exclude_etf` 인자는 코드에 없음): (1) **Supabase 조회** (테이블 = `stock_master`, 2배 buffer `limit × 2` — 필터 후 결과 < limit 회피). (2) **Python-side JSONB 필터링**: `raw.hts_avls × 100_000_000` 억원 단위 환산 ≥ `min_market_cap` (사이클 166 정정 — cycle 108 시점 `× 1_000_000` 백만원 가정은 100배 silent 결함, 코드 L682) + `raw.acml_tr_pbmn` 거래대금 ≥ `min_trade_amount` + ticker `not in exclude_tickers` + `nxt_tradable` (None 시 무필터, 사이클 32 R4 답습). ETF 키워드 제외 + 6자리 ticker 검증은 list_by_filter 본체가 아닌 **호출자 `_scan_universe`** 가 수행 (`ETF_KEYWORDS`, 사이클 89 영속). (3) **graceful** (raw miss / hts_avls miss / acml_tr_pbmn miss = 통과, 사이클 65 Q6-1 09:00 race graceful 답습). (4) **filter 후 limit 적용** (final result ≤ limit). **사이클 107 raw 보강 의존성**: `inquire_stock_basics` 영역에서 `hts_avls` (사이클 108 신규) + `acml_tr_pbmn` (사이클 107) 키 자동 포함 = 사이클 108 `list_by_filter` 필터링 데이터 확보. **호출**: VB/LTV/BFB 3 전략 `_scan_universe()` (`src/engine/strategies/{volatility_breakout, long_tail_volatility, bull_flag_breakout}.py`). **운영 효과**: KIS `volume-rank` API (FHPST01710000) 호출 100% 폐기 (VB 3 + LTV 3 + BFB 3 = 9 호출/일 → 0 호출, 사이클 17 OPSP0002 backoff + KIS LMS chain 안전 효과). **회귀 가드**: `tests/unit/db/test_cycle108_list_by_filter.py` (Supabase 조회 + Python-side JSONB 필터링 + 2배 buffer + graceful + filter 후 limit 적용). **영속 의무 매트릭스**: 사이클 32 R4 universe guard 영속 (nxt_tradable 답습) + 사이클 89 답습 (KOSPI/KOSDAQ + ETF 제외 + 6자리 ticker 영속) + 사이클 107 영속 (raw 보강 의존성 영속) + 사이클 81 G-AST1 영속 (`bfdy_clpr` + `hts_avls` 덮어쓰기 금지 영속). **매매 안전성 무영향 확정** (종목 마스터 캐시 조회 한정 + scanner 단계 후보 풀 구성 한정 + 매수 진입 전 한정 + 매도/익일청산 hot path 무관 + 사이클 38 명문화 영속). Plan Phase C UI 운영자 필터링 호환 (`exclude_tickers` 인자 활용 + Settings UI 영역 가능).

---

→ CHANGELOG: 사이클 108 행 · 사이클 205 행

### 사이클 107 (2026-06-11) — raw JSONB 3키 보강 전모

원문(`src/db/CLAUDE.md:216`, 2026-09-17 이관):

---

- **사이클 107 (2026-06-11) — raw JSONB 3 키 추가 (CTPF1002R + FHKST01010100 merge, Plan Phase A 데이터 의존성 해소)**: `stock_master.raw` JSONB 영역에 사이클 107 시정 이후 자동 포함되는 3 키 명세 — `acml_tr_pbmn` (누적 거래 대금) + `lstn_stcn` (상장 주수) + `acml_vol` (누적 거래량, `prdy_vol` 동등). `src/api/condition.py::inquire_stock_basics` 본체 보강 (+44L 순증, 사이클 107 시정) → CTPF1002R 호출 *후* FHKST01010100 (`inquire_price` 주식현재가 시세) 추가 호출 → 응답 merge → raw JSONB 통합. CTPF1002R 응답 67 컬럼 = 3 키 모두 부재 (KIS MCP 정본 확정) → FHKST01010100 호출 영역에서만 입수 가능. **CTPF1002R 기존 키 덮어쓰기 금지 설계** = `bfdy_clpr` 정합 (사이클 81 G-AST1 영속). **호출 시점**: 매수/매도 진입 직전 lazy `upsert_one` 경로 + 사이클 101 `_full_universe_load_once` (사이클 106 lifecycle 영속) 배치 호출. **운영 효과 (사이클 107 시정 push 후)**: stock_master 2,800 종목 × 2 KIS 호출 + 50ms sleep = 약 5분 소요 / 향후 Plan Phase A (사이클 108+) `list_by_filter(min_market_cap=, min_trade_amount=)` 데이터 의존성 해소. **graceful fallback**: FHKST01010100 RuntimeError / KisApiError = CTPF1002R 단독 raw 반환 (호출자 보호 = stock_master 저장 graceful). **회귀 가드**: `tests/unit/api/test_cycle107_inquire_stock_basics_merge.py` 12 케이스 (HIGH 4 = 양쪽 API 호출 + raw 3 키 포함 + graceful fallback + AST 영구 가드). **영속 의무 매트릭스**: 사이클 81 G-AST1 (`bfdy_clpr` 덮어쓰기 금지) + 사이클 98 G-DOC1 (KIS 정본 `chk_inquire_price.py` 인용 의무) + 사이클 101 영속 (`_full_universe_load_once` 호출 영역 자동 반영) + 사이클 106 영속 (`_full_universe_load_task_loop` 변경 0 = lifecycle race 차단). **매매 안전성 무영향 확정** (종목 마스터 캐시 한정 + 매매 hot path 무관 + Rate Limit 50ms sleep KIS LMS chain 안전)

---

→ CHANGELOG: 사이클 107 행

### 사이클 129 (2026-06-14) — `master_raw` 별도 컬럼 절 머리말

`stock_master.py` 가 세 절(종목 마스터 캐시 · master_raw · 종목마스터 조회)로 나뉘어 있던 시절의 절 머리말. 정본에서는 한 절로 합쳤다.

원문(`src/db/CLAUDE.md:255-257`, 2026-09-17 이관):

---

## stock_master.py — 사이클 129 master_raw 별도 컬럼 (2026-06-14)

KIS 공식 일일 마스터 파일 (`kospi_code.mst` / `kosdaq_code.mst`) 영역 = `master_raw JSONB` 별도 컬럼 영구 영속 (사이클 81 G-AST1 영속 절대 보호 = raw 영역 변경 0). migration 034 `IF NOT EXISTS` idempotent 영속.

---

→ CHANGELOG: 사이클 129 행

### 사이클 167 — `get_market_cap_millions` dead code 폐기 표시

원문(`src/db/CLAUDE.md:276`, 2026-09-17 이관):

---

- ~~`get_market_cap_millions`~~ (사이클 167 폐기 — dead code, callsite 0건. 실제 시총 필터는 `list_by_filter` / `list_paged_by_filter` 직접 수행, 사이클 166 억원 정합)

---

→ CHANGELOG: 사이클 167 행

### 사이클 126·128 (2026-06-13) — `.range(0, 9999)` silent cap 시정 경위

원문(`src/db/CLAUDE.md:278-288`, 2026-09-17 이관):

---

## stock_master.py — 종목마스터 조회 영역 (사이클 128, 2026-06-13)

사이클 126이 `count_all` 만 `count="exact"` 별도 쿼리로 시정. 나머지 4 카운트는 `.range(0, 9999)` raw 후 Python-side `sum()` 영속 → **Supabase PostgREST `max-rows` 1,000행 silent cap** → 4 카운트 부분 집계 (`nxt_tradable_count` 운영 실측 400 → UI ~150 silent 결함). 사이클 128 시정 = 4 카운트 모두 `count="exact"` + filter 별도 쿼리 (사이클 126 패턴 100% 답습).

### `get_stats()` 4 카운트 시정

- 헬퍼 `_count_exact(filter_callable)` 캡슐화 — 동일 `count="exact"` + `.limit(0)` 패턴 4회 반복 회피
- `bfdy_clpr_present` / `with_hts_avls` / `with_acml_tr_pbmn`: JSONB 키 존재 + 0 제외 조합. **jsonb operator path 채택** (`raw->'bfdy_clpr'` numeric 비교) — text path (`raw->>'bfdy_clpr'`) gte 자릿수 비교 결함 (1조 이상 실제 332건 vs text 비교 2,696건 silent 결함, Supabase MCP READ-ONLY 검증) 영구 차단
- `nxt_tradable_count`: `.eq("nxt_tradable", True)` 단순 컬럼 필터
- `top_10_recent`: 별도 `limit(10)` fetch (전체 raw 의존 영구 폐기)
- AST 영구 가드 (`tests/unit/ast/test_cycle128_ast_no_range_9999_silent_cap.py`): `src/db/stock_master.py` 본체 `.range(0, 9999)` 잔존 0건 — silent cap 패턴 영구 차단

---

→ CHANGELOG: 사이클 126 행 · 사이클 128 행

### 사이클 128·166·168 — `list_paged_by_filter` 도입과 jsonb string 결함 전모

사이클 168 의 생성 컬럼 전환 근거와 실측. 도입 시점 시그니처는 `(rows, total)` 튜플 반환으로 적혀 있었으나 현행 코드는 keyword-only + dict 반환이다.

원문(`src/db/CLAUDE.md:290-300`, 2026-09-17 이관):

---

### `list_paged_by_filter()` 신규

- 시그너처: `list_paged_by_filter(market=None, min_market_cap=None, min_trade_amount=None, name_substr=None, limit=100, offset=0) -> tuple[list[dict], int]`
- `market`: 'KOSPI' / 'KOSDAQ' / None (전체)
- `min_market_cap`: int (원 단위). 생성 컬럼 `hts_avls_eok`(억원, bigint STORED) numeric gte 임계 = `min_market_cap // 100_000_000` (사이클 166 억원 정정 + 사이클 168 생성 컬럼 전환)
- `min_trade_amount`: int (원 단위). 생성 컬럼 `acml_tr_pbmn_won`(원, bigint STORED) numeric gte
- `name_substr`: str (대소문자 무시 substring — `ilike("name", "%q%")`)
- **사이클 168 (2026-06-20) — jsonb string 결함 → 생성 컬럼 전환 (UI 필터 0건 silent 결함 시정)**: 사이클 128 가정("raw 가 jsonb *number* 2,696/2,697")이 운영 DB 에서 회귀 — 적재부 `condition.py` merge 가 KIS 응답 문자열("1503" 등)을 그대로 저장 → `raw.hts_avls` / `raw.acml_tr_pbmn` / `raw.bfdy_clpr` 전부 jsonb *string* (운영 DB 실측 number=0 / string=3573·3441·3573). 종전 `q.gte("raw->hts_avls", N)` jsonb numeric gte 는 PostgreSQL jsonb 정렬에서 number > string 이라 항상 false → 어떤 임계든 **0건** (시총·거래대금 필터 무력화, market/name 필터는 정상). 실측: `raw->'hts_avls' >= '1000'::jsonb` = 0 vs `hts_avls_eok >= 1000` = **1,734** / `acml_tr_pbmn_won >= 10000000000` = **366**. **시정 (Option A, migration 039)**: 생성 컬럼 `hts_avls_eok bigint GENERATED ALWAYS AS (CASE WHEN raw->>'hts_avls' ~ '^[0-9]+$' THEN (raw->>'hts_avls')::bigint END) STORED`(억원) + `acml_tr_pbmn_won`(원) + 인덱스 `ix_sm_hts_avls_eok` / `ix_sm_acml_tr_pbmn_won`. 비숫자/null 은 정규식 가드로 NULL → `.gte` 자동 제외 (graceful). `list_paged_by_filter` `.gte("hts_avls_eok", ...)` / `.gte("acml_tr_pbmn_won", ...)` 전환. 임계 환산 로직 불변 (사이클 166 억원 정합). **get_stats 무관**: `with_hts_avls`/`with_acml_tr_pbmn`/`bfdy_clpr_present` 는 `raw->>` text path 의 non-null/`<>'0'`/`<>''` *존재성* 체크일 뿐 numeric 비교가 아님 → string 에서도 정상 (실측 3566/3441/3566). **scanner list_by_filter 무관**: Python-side `int(str(value))` 파싱(사이클 108/166) → 후보 풀 1,734 정확 (UI 읽기 경로 한정). 생성 컬럼은 raw 읽기만(GENERATED) → 사이클 81 G-AST1 영속 (raw 변경 0). 회귀 가드 `tests/unit/db/test_cycle168_list_paged_generated_cols.py` 10 케이스 (COL 2 + THRESH 4 + EMPTY 2 + AST 2, AST-1 = list_paged 본체 `raw->hts_avls`/`raw->acml_tr_pbmn` jsonb gte 잔존 0건 영구 가드). 사이클 128/166 테스트는 관용 substring 매칭(`"avls" in col` / `"hts_avls" in str(col)`)이라 의미 전환 0건 (여전히 PASS)
- `count="exact"` 동일 쿼리에 동봉 → 정확한 `total_count` 반환 (페이징 정합성 의무)
- 정렬: `refreshed_at DESC` 영속
- 호출자: `GET /api/stock-master/list` 라우트만 (UI 페이징 전용). `list_by_filter()` (사이클 108 scanner 전용) 와 영역 분리 영속

---

→ CHANGELOG: 사이클 128 행 · 사이클 166 행 · 사이클 168 행

---

## stock_master_daily.py — KIS 일봉 정규화

### 사이클 26 답습 — `upsert_batch` 100건 chunk 의 Supabase HTTP/2 근거

원문(`src/db/CLAUDE.md:225`, 2026-09-17 이관):

---

  - `upsert_batch(ticker, rows)` — 100건 배치 chunk (Supabase HTTP/2 stale 회피, 사이클 26 답습)

---

→ CHANGELOG: 사이클 26 행

### 사이클 172·173 — DB일봉 어댑터와 락/신선도 게이트 도입 전모

자문 완화책 채택 경위, 운영 DB 실측 보정(자문의 `!= 1.0` 오류), 의미 전환 2건. 현행 정본에는 폴백 조건 3개와 상수만 남겼다.

원문(`src/db/CLAUDE.md:232-233`, 2026-09-17 이관):

---

  - **`get_recent_daily_normalized(ticker, days, *, min_required=None)`** (사이클 172, 2026-06-22) — DB일봉 어댑터. DB row 의 `raw` JSONB (KIS 원본 키 `stck_clpr`/`stck_oprc` 등 보존) 를 **그대로 반환** → 사이클 173 prepare 의 `c.get("stck_clpr")` 무변경 사용 보장. DB 부족 (`< min_required`, 기본 None = `max(days//2, 10)`) 시 `fetch_daily_candles` KIS 폴백 (원본 KIS 키 반환). raw 키 부재 row 는 row 자체 반환 (graceful). 사이클 81 G-AST1 raw JSONB 변형 0 영속.
    - **사이클 173 (2026-06-22) — 락/신선도 게이트 추가 (수정주가 divergence silent 결함 방어, HIGH)**: domain-expert 자문 `_workspace/domain_consult/cycle173_prepare_db_equivalence.md` 완화책 1 채택. 어댑터에 2 게이트 추가 (DB 사용 전 검사 순서): **(1) 락 게이트 (G-EQ-3, 최우선)** — `get_recent_daily(ticker, days)` 윈도우 내 1 row 라도 락 발생 (`_row_has_lock`: `flng_cls_code not in ("","00")` OR `abs(float(prtt_rate)) > 0`) → DB 버리고 `fetch_daily_candles` KIS 강제 폴백. 근거: 수정주가는 조회 시점 의존값 → DB 박제 과거봉(락 전) vs KIS 재조정(락 후) 어긋남 → 락 종목만 KIS 폴백이 유일한 silent 방어. 검사 = DB row top-level `flng_cls_code`/`prtt_rate` 컬럼 (raw 와 별개 정규화 컬럼, migration 033) → **KIS 추가 호출 0건 탐지**. **(2) 신선도 게이트 (G-EQ-4)** — `max_bas_dd(ticker)` 가 `today - DAILY_STALENESS_DAYS(=4)` 보다 오래 (D-1 미적재 race) → KIS 폴백. `max_bas_dd None` (판정 불가) 은 graceful 통과. **(3) min_required 게이트 (172)** — `len < min_required` → KIS 폴백. **★ team-leader 운영 DB 실측 확정 (자문 보정)**: `flng_cls_code` 기본 = `""`/`"00"` (실측 99.6% "00", 비기본 01/02/03/05 = 락). `prtt_rate` 기본 = `0`/`""`/`None` (실측 99.7% "0.0000" — **자문의 `!= 1.0` 은 틀림, 전 종목 폴백 유발**). KIS 정본 docstring 은 코드 *값 의미* 미제공 → 비기본=무조건 락 의심 보수적 폴백. 헬퍼 3 = `_row_has_lock` / `_extract_raw` (raw 추출 DRY) / `_kis_fallback` (락/신선도/부족 공통 + 실패 시 DB graceful). 상수 `DAILY_STALENESS_DAYS = 4` (주말 2 + 공휴일 마진, 거짓 폴백 차단). **prepare 연결 = 사이클 173** (5 전략 days/min_required 명시: VB/LTV=22, donchian=63, BFB=35, VCP=100). 회귀 가드 `tests/unit/db/test_cycle173_adapter_lock_stale_gate.py` 13 케이스 (G-EQ-3 락 5 + G-EQ-4 신선도 3 + G-EQ-5 경계 2 + G-EQ-6 폴백 1 + 우선순위 1 + AST 1). 의미 전환 2건 = `test_cycle172_safety_no_trading_diff.py` (SAFETY-2 prepare 어댑터 호출 0 → xfail / SAFETY-3 raw 추출 헬퍼 위임 정합). 매매 안전성 무영향 (scanner 매수 진입 전 한정, 사이클 38).

---

→ CHANGELOG: 사이클 172 행 · 사이클 173 행

### 사이클 150·172·196 — `DAILY_RETENTION_DAYS` 근거 오류와 시정

도입 근거 "VCP 220일 + 10일 마진" 이 오류였고 사이클 196 이 VCP backfill target 을 120 으로 낮춰 수렴시켰다. 현행 정본에는 값과 그 값이 충분한 이유만 남겼다.

원문(`src/db/CLAUDE.md:234-235`, 2026-09-17 이관):

---

- **`DAILY_RETENTION_DAYS` (사이클 172) — 150 → 230** (도입 당시 근거 "VCP 220일 + 10일 마진"). `purge_old_rows` 로직 불변 (상수만, "230일 지난 것만 삭제"). 사이클 150 (VCP T-120일 + 30일 마진) → 사이클 172 확장. 의미 전환 1건 = `test_cycle150_supabase_capacity.py::TestG150DailyRetentionDays` (`== 150` → `== 230`, 사이클 66 K-2 패턴). 용량 ~22MB → ~34MB (무료 500MB 중 7%).
  - **⚠️ 사이클 196 (2026-07-07) 정정 — 230 은 달력일, VCP 220 영업일을 보유 못 함**: retention 230 **달력일** = **154 영업일** 만 보유 (운영 DB 실측 = rows_within_retention 154). 사이클 172 근거 "VCP 220일 lookback 충족"은 **오류** (220 영업일 = ~308 달력일 > 230). 이 불일치가 `existing_count < _DAILY_LOAD_VCP_BACKFILL_DAYS(=220)` 를 영구 True 로 만들어 VCP 348종목 무한 재backfill(churn) 유발 → **사이클 196 = VCP backfill target 220→120 하향** (retained 154 내 수렴, `src/engine/scanner.py` `_DAILY_LOAD_VCP_BACKFILL_DAYS`). **retention 230 은 불변** (VCP prepare 실사용 100일 << 154 보유 → 충분). 향후 VCP 220 EMA 원설계 복원 시 retention 을 ~320 달력일로 상향 필요.

---

→ CHANGELOG: 사이클 150 행 · 사이클 172 행 · 사이클 196 행

### 사이클 192 (2026-07-04) — `purge_old_rows` 전 실행 실패 결함 시정 전모

원문(`src/db/CLAUDE.md:236`, 2026-09-17 이관):

---

- **사이클 192 (2026-07-04) — `purge_old_rows` 날짜 슬라이스 루프 배치 전환 (전 실행 실패 결함 항구 시정)**: 사이클 150 도입 시점의 단일 bulk DELETE (`delete().lt("bas_dd", cutoff)`) 가 supabase-py 기본 `returning="representation"` 으로 적체 47,924행 × raw JSONB 를 응답으로 반환 시도 → **6/16 도입 이래 매 실행 실패** (`[stock_master_daily_purge] 실패 graceful` 515건, raw SQL 동일 DELETE 는 즉시 성공 = PostgREST 계층 결함 확정). 시정 = `PURGE_MAX_DATE_ITERATIONS=500` cap 루프: (1) SELECT `bas_dd` lt cutoff + **protected 제외** + order asc + limit 1 → 빈 결과 drained break (2) 그 날짜 전체 DELETE `delete(count="exact", returning="minimal").eq("bas_dd", oldest)` + protected 제외 → deleted 누적. **SELECT 쪽 protected 제외 누락 금지** — protected 만 남은 날짜 무한 재선택 = never-drain 회귀 (P-3 HIGH 가드). 예외 graceful = 부분 누적 deleted 반환 + `logger.exception` 에 `type(exc).__name__: str(exc)[:150]` 계측 (사이클 190 패턴). 시그니처/반환 계약/16:15 task/`DAILY_RETENTION_DAYS=230` 불변 + `execute_with_retry` 미경유 영속 (G-187-A2). 회귀 가드 17 (`test_cycle192_daily_purge_loop_batch.py` 12 + `test_cycle192_ast_purge_loop.py` 5) + 의미 전환 2 (cycle150 G-150-DAILY-3 / cycle172 test_ret2 — mock 형상만, intent 보존). 운영 적체 47,924행은 메인 세션 raw SQL 즉시 드레인 완료 → steady-state 하루 1날짜(~3.5K행).

---

→ CHANGELOG: 사이클 192 행

### 사이클 187 (2026-06-30) — read 4함수 `execute_with_retry` 경유 경위

`execute_with_retry`·`asyncio.to_thread` 는 현행 코드에 없다. 테스트 주의(`freeze_time` 안 hang)는 현행에도 유효해 정본에 남겼다.

원문(`src/db/CLAUDE.md:237`, 2026-09-17 이관):

---

- **사이클 187 (2026-06-30) — read 4함수 `execute_with_retry` 경유 (Supabase HTTP/2 stale connection 흡수)**: `get_recent_daily`/`count_all`/`count_by_ticker`/`max_bas_dd` 가 `asyncio.to_thread(lambda: ...execute())` → `src.db.supabase.execute_with_retry(lambda: ..., op="<함수명>")` 경유(connection 계열 예외 1회 재시도, `max_bas_dd` ticker None/지정 2분기 build if/else 후 단일 호출). 기존 `try/except Exception: logger.exception(...graceful)` + 폴백 반환값(`[]`/`0`/`None`) **불변**(retry 소진 시 마지막 예외가 graceful 로 떨어짐). **쓰기 3함수(`upsert_daily`/`upsert_batch`/`purge_old_rows`)는 미경유**(직접 to_thread 유지 = 멱등 우려 제외, AST G-187-A2 영구 불변식). `get_recent_daily_normalized`(사이클 173 어댑터)는 내부에서 `get_recent_daily` 호출이라 retry **간접 수혜**(KIS 폴백 빈도 감소). 배경 = EC2 운영 `httpx.RemoteProtocolError: Server disconnected` 90건/24h(16:00 일봉 task stale HTTP/2 연결 재사용). **테스트 주의**: `freeze_time` 안에서 prepare/stock_master_daily read 를 태우면 retry 의 `asyncio.sleep(0.2)` 이 동결 `time.monotonic` 과 결합해 무한 hang → DB read 를 mock 하거나 freeze 밖에서 read (사이클 187 BFB 회귀 흡수 교훈).

---

→ CHANGELOG: 사이클 187 행

### 사이클 68·81·M6·124 — 영속 의무·UI 동기화 의무 꼬리표

원문(`src/db/CLAUDE.md:239-240`, 2026-09-17 이관):

---

- 영속 의무: KST timestamp `_kst.now_kst_iso()` 사용 (사이클 68 G-10b AST) + raw JSONB 덮어쓰기 금지 (사이클 81 G-AST1 답습) + DATE 바인딩 `_kst.to_date()` 강제 (사이클 M6)
- **UI 활용 영역 (사이클 124, 2026-06-12)**: `stock_master_daily` 컬럼 추가 시 UI 동기화 의무 영속 — `GET /api/stock-master/{ticker}/daily?days=N` 라우트 (`src/routes/stock_master.py`) + `frontend/src/pages/StockMaster.tsx::DailyTab` 30 row 테이블. `get_stats()` 응답에 `total_daily_rows` + `last_daily_load_at` 노출. 절차 상세는 `frontend/CLAUDE.md` 사이클 124 본문 참조

---

→ CHANGELOG: 사이클 124 행

---

## DB 스키마

### 사이클 34 → 145 — `strategy_funnel_snapshots` UNIQUE 변경 서사

원문(`src/db/CLAUDE.md:345`, 2026-09-17 이관):

---

- `strategy_funnel_snapshots` (migration 030, 사이클 34): UNIQUE 변경 — `(target_date, strategy_id, step_no, snapshot_at)` (사이클 34) → `(target_date, strategy_id, step_no)` (**migration 035 사이클 145, snapshot_at 키 폐기**) + JSONB 필드 2개

---

→ CHANGELOG: 사이클 145 행

---

## TIMESTAMPTZ 계약

### 사이클 69 (2026-06-08) — 카드 #18(UTC 백필 migration) 폐기 명문화 전문

Supabase 시절 서버 timezone·PostgREST 응답 형식을 전제로 쓴 절. 현행 풀은 `init_pool(server_settings={"timezone": "Asia/Seoul"})` 이다.

원문(`src/db/CLAUDE.md:347-362`, 2026-09-17 이관):

---

## TIMESTAMPTZ 사실 명문화 (사이클 69, 2026-06-08)

**카드 #18 (UTC 잔존 데이터 백필 migration) 영구 폐기 — 사실: 백필 불필요**.

모든 시각 컬럼은 PostgreSQL `TIMESTAMPTZ` (timestamp with time zone) 모델:
- **내부 저장 = UTC instant** (timezone 정보 분리)
- **표시 시점 = 세션 timezone 변환** (PostgREST 응답은 `+00:00` ISO 기본)
- **instant 자체는 timezone 무관 절대 시점** — UTC 로 저장한 instant 와 KST 로 변환한 instant 는 *동일 시점*

DB DEFAULT `now()` (Supabase PG 서버 timezone = UTC) INSERT instant ≡ Python `datetime.now()` (컨테이너 `TZ=Asia/Seoul`) INSERT instant = **절대 시점 동일**.

사이클 65 hotfix H2/H2-bis + 사이클 68 17 모듈 시정 (`src/db/_kst.py` 헬퍼) = **표시 형식 (`+09:00` ISO) 일관화** + 호출자 정합성 보장 — *instant 정정이 아님*. 백필 migration 불필요.

조회 영역 (`get_trades_in_range` / `get_logs` / `_fetch_logs_in_range`) 의 KST `+09:00` 명시 (사이클 53 B-4) = TIMESTAMPTZ 비교 timezone 정합성 100% 보장.

미래 오해 차단 의무 — *"UTC 저장 = 결함"* 가정 시 본 명문화 인용. 진실의 원천: `docs/HARNESS_CHANGELOG.md` 사이클 69 행.

---

→ CHANGELOG: 사이클 69 행

---

## 주의사항

### M0~M6 이전 — supabase-py 동기 SDK · `asyncio.to_thread` 위임 정책 폐기 서술

원문(`src/db/CLAUDE.md:366-367`, 2026-09-17 이관):

---

- **DB 클라이언트 = `pg.py` (asyncpg 네이티브 async)** — 모든 CRUD 는 `pg.fetch`/`fetchrow`/`fetchval`/`execute`/`executemany` 경유. supabase-py 동기 SDK + `asyncio.to_thread` 위임 정책은 폐기 (asyncpg 는 직접 async I/O). `src/db/supabase.py` 는 롤백용 병존(미사용) — `src/` 전체 supabase 직접 참조 0건 (AST 가드: `grep supabase.table src/` = supabase.py 제외 0건).
- `_DbLogHandler` (main.py) 는 동기 `logging.Handler.emit` → **큐 producer + async consumer** 구조 (M3 seam 전환). dedupe 500ms(사이클 72) + KST(사이클 65) + never-raise(사이클 190) 보존

---

→ CHANGELOG: Supabase→RDS 이전(M0~M6) 최상단 엔트리


## stock_master_daily.py — KIS 일봉 정규화

### 2026-09-17 cycle299 — retention 230 → 380 (200일 EMA 를 담을 깊이)

바꾼 이유. 200일 EMA 를 쓰려면 일봉이 220 영업일 필요한데, 막고 있던 것은 KIS 가 아니라
우리 상수 둘이었다. KIS `FHKST03010100` 의 100일은 **호출당 한도**이고
`src/api/condition.py::fetch_daily_candles_backfill` 이 이미 날짜 윈도우를 `ceil(total_days/window)`
개로 쪼개 순차 호출·병합한다(사이클 172). "KIS 가 100일까지만 준다" 는 오해가 넉 달 동안
200일 EMA 를 막았다.

수치. retention 380 달력일 ≈ 254 영업일(환산 앵커 = 사이클196 실측 230cal ⇄ 154영업일),
target 220 → 마진 34 영업일(사이클196 의 34 와 같다). `fetch_daily_candles_backfill(total_days=220)`
은 윈도우 3개(100/100/20), 최고 도달 318 달력일 < retention 380.

매매 행위 변화 0 인 근거. `get_recent_daily` 가 `max(1, min(days, 100))` 로 하드 클램프하고,
행을 돌려주는 모든 읽기(`get_donchian_high`·`get_atr`·`get_recent_daily_with_fallback`·
`get_recent_daily_normalized`)가 이 함수를 경유한다. 나머지 소비처는 전부 스칼라 집계
(`max_bas_dd`·`count_all`·`count_by_ticker`·`routes/market_ops.py`)다. 가드 `test_g299_7a`/`7b`.

원문(`src/db/CLAUDE.md:283`, 2026-09-17 이관):

---

- **retention `DAILY_RETENTION_DAYS = 230`(달력일 ≈ 154 영업일)**. VCP backfill target 120 · prepare 실사용 100일이라 충분하다. ⚠️ **VCP 220 EMA 원설계를 복원하려면 retention 도 ~320 달력일로 함께 올려야 한다**(220 영업일 ≈ 308 달력일).

---

같은 줄의 ⚠️ 는 이번 사이클이 실현했으므로 정본에서 사라졌다. `get_recent_daily` 항목의
100행 클램프는 선재 코드 사실인데 문서에 없던 것이라 이번에 정본에 **보강**했다(이관 아님).

→ CHANGELOG: cycle299 행

### cycle299 (2026-09-18) — 목표를 220 → 225, 보존을 380 → 390 으로 다시 올린 경위

사이클 안에서 값이 한 번 더 움직였다. 앞 항목에 380/220 으로 적힌 서술은 그 시점의 기록이고,
확정값은 **retention 390 달력일 · VCP backfill target 225 영업일** 이다.

- **왜 225 인가** — VCP 추세 필터의 `effective_ema_long = min(ema_long, 보유 − uptrend_days(20) − 5)`
  에 운영 DB 값(`ema_short=50` / `ema_mid=150` / `ema_long=200`)을 넣고 보유 영업일을 움직이면,
  보유 220 에서는 실효 장기선이 **195** 에 그치고 **225 에서 정확히 200** 이 된다. 미네르비니 원전의
  200EMA 를 형식이 아니라 값으로 성립시키는 최소 깊이가 225 다. 같은 계산에서 mid↔long 간격도
  220 의 45 에서 225 의 50 으로 벌어진다(보유 100 이면 간격 10 = 사실상 동전던지기였다).
- **왜 retention 도 함께 올렸나** — 가드 `G-299-3c`(`retained_trading(retention) >= target + 30`)
  때문이다. 환산 앵커 230cal ⇄ 154영업일로 `retained(380) = 254` 인데 `225 + 30 = 255` 라 **1 모자라
  FAIL** 한다. 3c 를 만족하는 retention 최소값은 **381** 이고, 여유를 두어 390 을 택했다
  (`retained(390) = 261` → 마진 **36 영업일**, 사이클196 의 34 보다 크다).
- **실측(가드 헬퍼 `_capture_backfill_reach_cal` 로 확인)** — `total_days=225` 의 윈도우는 3개
  (100/100/25), 최고 도달 **325 달력일** < retention 390(여유 65cal). 1회 backfill 실도달은
  `trading_days_in(325) = 217` 영업일이라 target 에 **8 영업일** 모자라고, 이 부족분은 220 일 때와
  같다(둘 다 8). 전이 기간과 비용 추정은 앞 항목과 동일하다.
- **재핀** — `scanner.py` 가 다시 바뀌어 8영역 sha 핀 13곳(`_PIN_GUARD_FILES` 4 + 기준선 9)과
  `test_cycle287::_SRC_TREE_DIGEST` 를 같은 값으로 한 번 더 옮겼다. 단언은 약화되지 않았다.

### cycle299 (2026-09-18, 이어서) — 달력 환산을 고쳐 1회 backfill 이 목표를 넘게 했다

사용자 요청("데이터 지금 바로 채울 수는 없어?")으로, 별건으로 미뤄 두었던 환산식을 이 사이클에서 고쳤다.

- **고친 것** — `fetch_daily_candles_backfill` 의 **깊이**(마지막 윈도우 시작점) 환산에만 휴일 보정을
  비례로 얹었다: `int(n*7/5) + int(n*0.10) + 10`. 상수 3개를 이름으로 뽑고 근거를 주석에 남겼다
  (`_WEEKEND_CAL_PER_TRADING_DAY` / `_DAILY_BACKFILL_HOLIDAY_MARGIN_RATIO` / `_DAILY_BACKFILL_BASE_MARGIN_CAL`).
- **왜 계수를 통째로 올리지 않았나** — `3/2`(=1.50) 제안은 **stride 까지 함께 키운다**. KIS 가 한 호출에
  100건까지만 주므로 앞 윈도우는 공휴일이 하나도 없는 구간에서 정확히 100영업일 = **140 달력일**까지만
  덮는다. stride 가 140 을 넘는 순간 다음 윈도우의 머리가 그 바닥보다 아래로 내려가 **사이 구간이 통째로
  비고**, 빈 날짜는 어느 윈도우도 다시 집지 않는다(`3/2` 면 stride 150 > 140). 그래서 stride 는 7/5 로
  두고 깊이에만 보정을 얹는 형태를 택했다. 구멍 검사는 공휴일 0 이라는 최악 가정으로 확인했다.
- **실측** — `total_days=225` → 윈도우 3개 `[(0,160), (140,310), (280,347)]`, 최고 도달 **347 달력일**.
  실측 비율(앵커 230cal ⇄ 154영업일 = 1.479)로 **232 영업일**이라 목표 225 를 **7 넘는다**. 공휴일이
  없는 해(1.40)에는 247, 밀집한 해(1.52)에도 228 로 어느 쪽도 목표 위다. 전이 기간이 사라졌다.
- **가드** — `retention 390` 기준 3a(347 < 390, 여유 43) · 3b(347+30 = 377 ≤ 390) · 3c(261 ≥ 255) 전부
  통과라 retention 은 옮기지 않았다. `G-299-9` 는 "부족분 ≤ 10"(음수에서 공허해진다)에서
  **"실도달 ≥ target"** 으로 부등식을 뒤집어 강화했다.
- **`scanner.py` 무접촉** — 변경을 `condition.py` 에 가둬 8영역 sha 핀 13곳을 다시 옮기지 않았다.
  움직인 것은 `test_cycle287::_SRC_TREE_DIGEST` 하나다.
- **호출자** — `fetch_daily_candles_backfill` 의 프로덕션 호출자는 `scanner._stock_master_daily_load_once`
  **하나뿐**임을 `grep` 으로 재확인했다. 별도 함수 `fetch_daily_candles` 는 무접촉이다.

## 2026-09-18 — cycle300 · 읽기 100행 클램프 해제 (`_MAX_DAILY_ROWS = 400`)

- 사용자 명시 승인("100행 클램프도 해결하자" · "(오늘 켜는가) 응 켜야지").
- `get_recent_daily` 의 `clamped = max(1, min(days, 100))` 을 `max(1, min(days, _MAX_DAILY_ROWS))`
  로 바꿨다. **구조는 그대로 둔 채 상한만 올렸다** — `min()` 을 지우면 오염된 파라미터나 호출
  버그가 그대로 `LIMIT` 에 실려 한 종목 조회가 전체 스캔이 된다.
- **400 의 근거는 위아래 두 경계다.** 위 = retention 390 달력일이 보유하는 약 261 영업일과
  VCP full 요청 `ema_long(200) + base_max_days(75) + 10 = 285` 가 둘 다 400 아래라 관문이
  실데이터도 요청도 자르지 않는다. 아래 = 무한대로 두지 않는다(폭주 방어).
  두 부등식을 `test_cycle300_daily_depth_switch.py::test_g300_2/2b` 가 프로덕션 상수끼리
  비교해 잰다 — 테스트에 숫자를 박지 않았다.
- **다른 소비처는 1행도 바뀌지 않는다.** 클램프가 `min()` 이라 100 이하 요청은 요청값이
  그대로 실린다 — donchian 20 · `get_atr(14)`→15 · 매크로 ETF 90 · LLM 60 · kojiro 100 ·
  UI 라우트(`Query(30, ge=1, le=100)`) 전부 상향 전후 동일(G-300-6, pg.fetch 인자 캡처로 실측).
  실제로 더 읽는 것은 VCP 가 `daily_fetch_depth_mode="full"` 일 때뿐이다.
- **cycle299 의 G-299-7a 를 의미 전환했다.** 그 가드는 "리터럴 100 이 min() 안에 있는가" 를
  쟀는데, 그것이 봉인하던 명제("cycle299 는 읽기 깊이를 건드리지 않았다")는 cycle299 에 대한
  것이고 cycle300 은 바로 그 상한을 올리라는 승인을 받았다. 그래서 **클램프 구조 존재**로
  대상을 옮기고 숫자의 근거는 cycle300 가드가 맡는다. detector self-test 도 명명 상수 케이스를
  추가했다 — 리터럴만 잡던 탐지기는 상수화 직후 공허해진다.
- 되돌리기 = `_MAX_DAILY_ROWS` 를 100 으로 되돌리는 한 줄. 단 그 순간 VCP `"full"` 모드도
  함께 100 으로 잘린다(두 겹 중 한 겹만 닫는 것이라 무매매는 되지 않는다).

## strategy_funnel.py — 조건검색 단계별 추적

### 2026-09-25 cycle350 — `snapshot_at` 이 마지막 쓰기 시각이 됐다

`insert_snapshot` 의 `DO UPDATE SET` 에 `snapshot_at = now()` 가 들어가기 전 정본 서술(원문):

`snapshot_at` 은 **최초 INSERT 시각에 고정**된다 — `DO UPDATE SET` 에 `snapshot_at` 이 없고, 기본값 `now()`(migration 030)는 INSERT 때만 들어간다. 그래서 `snapshot_at` 으로는 그 행의 값이 언제 쓰였는지 알 수 없다(하루 쓰기 순서 = `src/engine/CLAUDE.md` 「funnel 스냅샷 캡처」 절).

→ CHANGELOG: cycle350 행

## system_config.py — 시스템 설정 키-값 헬퍼

### 2026-09-25 cycle363 — task 신선도 마커의 소비처 서술 교체

정본 원문:

- **task 신선도 마커**: `get_task_last_success(task_label) -> str | None`(키 `task_last_success_<label>`) / `set_task_last_success(task_label, iso_ts)`. 값은 KST ISO(`now_kst_iso()`). `task_loop_helper.run_periodic_task_loop` 의 `immediate_skip_if_fresh_hours` 게이트 전용이다 — 재시작 직후의 immediate run 이 N시간 안에 성공 마커가 있으면 건너뛴다(아침 프리마켓 burst 완화). **`get_task_last_success_bulk(task_labels) -> dict`** 은 같은 마커를 `key = ANY($1)` **단일 쿼리**로 묶는다(`GET /api/market-ops` 야간작업 타임라인이 폴링마다 라벨 수만큼 왕복하지 않게). 결측 라벨은 반환 dict 에 **키 자체가 없다**(빈 문자열이 아니다). 쿼리 실패는 빈 dict(fail-open)

경위: cycle363 이 부팅 즉시 실행 게이트를 두 갈래로 나눴다 — 시간 게이트(master·financial)와 영업일 슬롯 게이트(basics·daily_load·full_universe). 마커는 두 게이트가 함께 읽고, full_universe 도 처음으로 마커를 남긴다. 「`immediate_skip_if_fresh_hours` 게이트 전용」이 더는 참이 아니라 교체했다(하트비트 `engine_alive_heartbeat` 도 같은 키 공간을 쓴다).

→ CHANGELOG: cycle363 행

## stock_master_daily.py — KIS 일봉 정규화

### 2026-09-25 cycle363 — 어댑터에 `expected_head` 를 더하고 신선도 게이트를 두 갈래로 나눴다

정본 원문(시그니처 · 신선도 게이트 · 상수 줄):

  - **`get_recent_daily_normalized(ticker, days, *, min_required=None)`** — DB일봉 어댑터. DB row 의 `raw` JSONB(KIS 원본 키 `stck_clpr`/`stck_oprc` 등 보존)를 **그대로 반환**해 prepare 의 `c.get("stck_clpr")` 를 무변경으로 쓰게 한다. raw 키가 없는 row 는 row 자체를 돌려준다(graceful)
  2. **신선도 게이트** — `max_bas_dd(ticker)` 가 `today - DAILY_STALENESS_DAYS` 보다 오래면 폴백. `max_bas_dd` 가 `None`(판정 불가)이면 graceful 통과
  - 상수 `DAILY_STALENESS_DAYS = 4`(주말 2일 + 공휴일 마진 — 거짓 폴백 차단). 전략별 `days`/`min_required` = VB/LTV 22 · donchian 63 · BFB 35 · VCP 100

경위 (사용자 결정 2026-09-25 「①′ 도 같이」):

- `DAILY_STALENESS_DAYS = 4` 는 **달력일**이다. 09-28(월)은 추석 연휴(09-24·25) + 주말 뒤 첫 영업일이라
  `(09-28 − 09-23).days = 5 > 4` — 부팅 준비와 재준비에서 **모든 종목이 KIS 폴백**으로 갈 예정이었다
  (코드 계산, 아직 실제로 일어난 적은 없다). KIS 는 한 호출 100봉까지만 주므로 VCP
  `daily_fetch_depth_mode="full"`(250봉 설계)이 그날 100봉으로 계산될 참이었다. cycle173(06-22) 이후 달력 공백
  5일 이상은 이번이 처음으로 보였다(달력 추론).
- 평상시에도 봉 입력의 약 1/3 은 이미 KIS 폴백이다 — 09-23 하루 폴백 사유는 `lock` 2,232 · `insufficient`
  247 · `stale` 27 · `miss` 21 이었다(cycle360 §1.5).
- 시정 = 호출자가 넘긴 `expected_head`(직전 영업일)와 비교한다. 인자가 없으면 달력 판정 바이트 동일
  (하위 호환 — kojiro `recompute_held_atr` · `llm_buy_gate`). 부작용(하루치 결손도 폴백)은 테스트로 고정했다
  (`tests/unit/db/test_cycle363_expected_head.py`).
- 근거 = `_workspace/domain_consult/cycle360_boot_reprepare_4a_proposal.md` §1.5·§3 표 ①′.

→ CHANGELOG: cycle363 행

## stock_master_daily.py / stock_master.py

### 2026-09-25 cycle363(배포 전 보강) — F-3 (100봉 초과 + 1영업일 결손 예외) · F-4 (신규 카운트 함수)

경위 (독립 검증 finding #3 확정 반영, 사용자 결정 2026-09-25 D4 결정 2):

- F-3 이전 코드는 `expected_head` 가 있을 때 `latest < expected_head` 면 무조건 KIS 폴백했다.
  이것이 연휴가 아닌 **평상시 요일에도** 문제였다 — VCP `daily_fetch_depth_mode="full"`(~250봉
  요청)이 헤드가 하루 밀린 종목마다 KIS 100봉 상한에 걸려 200 EMA 가 75 EMA 로 계산됐다(독립
  검증이 harness 로 실측). 시정 = `days > 100`(KIS 1회 한도) 이고 `latest` 가 `expected_head`
  의 **정확히 1영업일 전**이면 폴백하지 않고 DB 를 그대로 쓴다. 2영업일 이상 결손·`days≤100` 은
  현행대로 폴백(사용자 결정 — 연휴 뒤 등은 값을 바로잡는 것이 목적이라 폴백이 정답).
- 판정은 `trading_calendar.previous_trading_day(expected_head)` 를 지연 import 로 불러
  `latest` 와 비교한다(never-raise, 실패·모름은 False = 폴백 쪽 안전 방향).
- F-4 — `stock_master.count_missing_kis_provenance_key()` 신규(`raw` 에 KIS
  `cptt_trad_tr_psbl_yn` 키가 없는 행 수). basics 강제 재실행 판정의 재료다. `count_active()`
  류의 "예외 시 0" fail-safe 방향과 **반대** — 이 함수는 예외를 삼키지 않는다(사용자 결정
  "쿼리 실패는 RUN 쪽").

→ CHANGELOG: cycle363(배포 전 보강) 행

## stock_master_daily.py — `change_rate`

### 2026-09-25 cycle365 P4 — `prdy_ctrt` 읽기 → `prdy_vrss` 후처리 산출

경위 (도메인 자문 §4 F-C 실증, 사용자 결정 2026-09-25 「P4 진행」):

- `_KIS_KEY_CHANGE_RATE = "prdy_ctrt"` 를 그대로 읽던 구현은 적재 시작(06-12)부터
  `change_rate` 전 행이 0 이었다. 원인 = FHKST03010100 **output2**(일봉 배열)에는
  `prdy_ctrt`(전일 대비율) 필드 자체가 없다 — `output1`(단건 요약)에만 있다.
  `docs/kis/domestic-stock-quote.md:5514-5518` Response Body 표(35~47번 = output2 필드)에
  `prdy_ctrt` 가 없고, KIS MCP `chk_inquire_daily_itemchartprice.py` 공식 COLUMN_MAPPING·
  Response Example 도 output2 행이 `prdy_vrss`/`prdy_vrss_sign` 만 가짐을 확인했다.
  마이그레이션 033 의 컬럼 코멘트("KIS prdy_ctrt 또는 후처리 산출")가 이미 이 후처리
  갈래를 예견하고 있었다.
- 시정 = `_derive_change_rate(candle)` 신설. `prdy_ctrt` 가 있으면(다른 TR 경유 등 미래
  호환) 그대로 쓰고, 없으면 `prdy_vrss`(전일 대비, 원 단위) ÷ 전일종가 × 100 으로
  계산한다. 전일종가 = 오늘 종가(`stck_clpr`) − `prdy_vrss` — `scanner._trade_amount_key`
  의 `prdy_close = stck_prpr - prdy_vrss` 와 같은 부호 규약(코드베이스에 이미 프로덕션
  검증된 패턴). `prdy_vrss_sign`(1상한/2상승/3보합/4하한/5하락)으로 부호를 교차검증해
  원본 문자열에 부호가 빠져 있는 경우(예: "500"인데 sign="5")를 보정한다.
- 분모(전일종가) 0 이거나 `prdy_vrss` 자체가 결측이면 0.0(graceful — 과거 동작과 동일값).
- **과거 적재 행은 백필하지 않는다** — DB UPDATE 는 별도 승인 대상이라 이 사이클은
  앞으로 적재할 행만 고친다.
- `grep` 전수 확인 — `stock_master_daily.change_rate` 를 읽는 매매 코드는 0건이다
  (전략들은 실시간 change_rate 를 현재가로 별도 계산한다). 소비처는 UI
  `StockMaster.tsx` 일봉 탭(0.00% 로 표시되던 문제)과 사람·AI 의 사후 분석뿐이다.
- 회귀 = `tests/unit/db/test_cycle365_change_rate.py`(9케이스 — 실제 output2 형태 계산 ·
  부호 보존·교차검증·보합·결측·분모0·prdy_ctrt 미래호환·종단통합·매매코드 무접촉 grep 가드).

→ CHANGELOG: cycle365 행
