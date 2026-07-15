# CLAUDE.md — src/db/ (Supabase DB)

Supabase (PostgreSQL) CRUD 모듈.

> 사이클별 변경 이력: `docs/HARNESS_CHANGELOG.md`

## supabase.py — 클라이언트 초기화

- `settings.supabase_url` + `settings.supabase_key` 로 클라이언트 생성
- **`execute_with_retry(build, *, retries=1, op="")`** (사이클 187, 2026-06-30): 동기 Supabase 쿼리(`build()` = `.execute()` 포함 무인자 callable)를 `asyncio.to_thread` 위임 + **connection 계열 예외 `retries`회 재시도**. `_RETRY_EXCEPTIONS = (httpx.RemoteProtocolError, ConnectError, ConnectTimeout, ReadError)` 만 캐치(각 시도 사이 `asyncio.sleep(_RETRY_BACKOFF_SECS=0.2)`), 소진 시 마지막 예외 raise(호출자 graceful except 보존), 비-retry 예외(`postgrest.APIError`/`ValueError`)는 즉시 전파. `logger.warning("[supabase_retry] op=... attempt=...")` 단독 — `write_log` 미호출(사이클 72 이중 INSERT 차단, `src.db.supabase` logger → `_DbLogHandler` 단일 INSERT). **멱등 SELECT 전용** — 쓰기(INSERT/UPDATE)는 RemoteProtocolError 가 '요청 도달 후 응답만 유실' 시 중복 위험이라 미적용. 배경 = EC2 운영 traceback 확정 `httpx.RemoteProtocolError: Server disconnected` 90건/24h(16:00 일봉 task 가 수백 종목 순회 → httpx pool stale keep-alive HTTP/2 연결 재사용, 전부 read 경로·매매 hot path 0). 현재 호출자 = `stock_master_daily` read 4함수(사이클 187) + **사이클 189 (2026-07-02) 확장** = `kis_quote_accounts` read 4함수(`list_accounts`/`get_account`/`get_account_by_label`/`get_credentials_for_token_manager`) + `system_config` read 9함수(`get_cash_usage_ratio`/`get_auto_regime_adjust`/`_get_bool_or_none`/`get_buy_block_mode`/`_get_float_or_default`/`_get_bool_or_default`/`_get_int_or_default`/`_get_str_or_default_UNUSED`/`_get_string_or_none`) — 7/1 로그분석 F4(kis_quote_accounts list 실패 11건/일 + price_filter/system_config get 실패) 흡수, 양 모듈 쓰기(`_upsert`/`_set_*`/insert 계열)는 미경유 영속. AST 영구 가드 `tests/unit/ast/test_cycle187_ast_read_retry.py` + `test_cycle189_ast_read_retry.py`(read 경유 + 쓰기 미경유 + 헬퍼 `write_log` Call 0건). **인계**: 잔여 db read 모듈(positions/trade_history 등 저노이즈 경로) 점진 전환

## _kst.py — KST 공용 헬퍼 (사이클 68, 2026-06-07)

- `KST = timezone(timedelta(hours=9))` — KST aware tzinfo 단일 진입점
- `now_kst_iso() -> str` — `datetime.now(KST).isoformat()`. DB INSERT/UPSERT payload 의 시각 컬럼 (`created_at` / `updated_at` / `refreshed_at` / `completed_at` / `timestamp` 등) 의무 사용
- `today_kst() -> date` — `datetime.now(KST).date()`. 서버 timezone 의존 (`date.today()`) 회피 — Q1 LOW 결함 차단
- **결정 2-B (사이클 68)**: 사이클 65 hotfix H2/H2-bis (`system_logs.py:44` + `main.py:126`) 인라인 패턴 → 본 헬퍼로 통일. 8 DB 모듈 (stock_master / parameter_recommendations / log_reports / system_config / strategy_config / kis_quote_accounts / market_regime_snapshots / backtest_runs) + 9 engine/api 모듈 (api/balance / api/condition / engine/strategy_base / engine/strategy / engine/backtest_engine / engine/scheduler / engine/boot_manager / engine/strategies/long_tail_volatility / engine/strategies/volatility_breakout) 사용. AST 영구 가드 5 케이스 (`tests/unit/db/test_cycle68_*.py`):
  - G-1 헬퍼 모듈 export 검증 (3 sub-case)
  - G-2~G-9 8 DB 모듈 KST 명시 (8 케이스)
  - G-10 AST 정적 가드: `datetime.utcnow()` 0건 + `src/db/` payload `datetime.now(timezone.utc)` 0건 (2 sub-case)
  - G-11 `stock_master.is_stale()` KST 비교 통일 (Q3, 1 케이스)
  - G-12 `date.today()` 일괄 → `today_kst()` 교체 (Q1 LOW, 1 케이스)
- 사이클 65 H2/H2-bis 영속 (변경 0) — `system_logs.py:44` + `main.py:126` 은 인라인 `datetime.now(KST).isoformat()` 유지 (행위 동일, 헬퍼 통일은 후속 사이클 인계 가능)

## trade_history.py — 거래 내역

- `insert_trade()`: 주문 시 INSERT (status: PENDING)
- `update_trade_status() -> int`: 체결/취소 시 PENDING row 새 status 갱신 + 영향 row 수 반환. 0건이면 호출자(OrderEngine) 가 체결통보 선행 race 로 판단해 COMPLETED 보정 INSERT
- **`get_trades_in_range(start_date, end_date, strategy=None)`**: `[start_date, end_date]` KST 범위 inclusive 조회. `start_iso = f"{date}T00:00:00+09:00"` / `end_iso = f"{date}T23:59:59.999999+09:00"` — **`+09:00` timezone 명시 필수** (TZ 없으면 PostgREST UTC 해석 → KST 00:00~09:00 거래 누락). `recommendation_engine` + `log_analysis_engine` 공유. 사이클 53 B-4 시정.
- `get_trades(limit, offset, ticker)`: 페이징 조회 + total count
- `get_trade_pairs(strategy=None, ticker=None)`: 매매손익 뷰용 매수/매도 페어 리스트. 같은 (ticker, strategy) 그룹 내 timestamp ASC 순회 → 누적 보유수량 0 사이클마다 closed 페어 emit (매수가/매도가 가중평균, Decimal 보존), 잔여 보유는 open 페어 emit (미실현 손익은 `scanner.ticker_prices` fallback). 응답 키: buy_date/buy_time/sell_date/sell_time/ticker/ticker_name/buy_price/buy_qty/sell_price/sell_qty/profit_loss/profit_rate/status('closed'|'open')/strategy. `_to_kst()` 헬퍼로 ISO (UTC/KST/tz-naive 모두) → `astimezone(KST).strftime()` 명시 변환
- `get_today_buy_trades / get_today_sell_trades / get_today_pending_buys`: today 기준 same-day. 쿼리 기준점 `f"{today}T00:00:00+09:00"` KST timezone 명시 (timezone-naive → PostgreSQL TIMESTAMPTZ UTC 해석 결함 차단). **ticker 별 dedupe 적용 (포지션 복구용 — 최신 1건만 반환)**
- **`get_today_buy_trades_for_sync(ticker=None) / get_today_sell_trades_for_sync(ticker=None)`** (사이클 30, 2026-05-21): **dedupe 없음** + CANCELLED 제외 + optional ticker filter. `_sync_orders_to_db` 중복 판정 키 소스 전용. 절대 포지션 복구용 dedupe 함수를 sync 에 재사용 금지 (5/20 042700 핑퐁 INSERT 사고 — 같은 ticker 의 다른 `order_no` 가 가려져 매 재기동마다 신규 판정)
- **DB 부분 UNIQUE 인덱스** (사이클 30, migration 029): `uq_trade_history_ticker_order_no_type ON (ticker, order_no, trade_type) WHERE order_no IS NOT NULL AND order_no != ''`. 코드 결함 재발 시 PG 가 INSERT 거부 → 애플리케이션 로직 회귀 보호. NULL/빈 order_no (수동 매매 사전 등) 는 제외

## daily_performance.py — 일일 실적

- `upsert_daily_performance()`: 16:10 정산 시 당일 실적 기록. `daily_realized_pnl`/`daily_profit_rate` 모두 **실현손익 기준** (SELL 매도 실현분만 합산). 매도 0건 → 둘 다 0 정상. 평가손익은 `BalanceTable.eval_profit_loss` 별도 표시. 컬럼: total_asset / daily_profit_rate / daily_realized_pnl / net_external_cashflow / deposit / cumulative_return_rate (TWR 복리, 실현손익 누적)
- `get_performance(days)`: 최근 N일 (날짜 오름차순)
- `get_latest_performance(strategy)`: 가장 최근 영업일 1행 — TWR 누적/Δ예수금 baseline
- `recompute_from_trades()`: PostgreSQL 함수 `recompute_daily_performance()` RPC 호출 — trade_history 기반 일괄 재계산 (멱등). `_settle()` 끝에서 자동 호출. `daily_profit_rate` 분모는 직전 영업일이 아니라 **가장 가까운 0이 아닌 이전 영업일 total_asset** (correlated subquery)

## system_logs.py — 시스템 로그

- `write_log(level, message)`: 이벤트/에러 기록. level: INFO / WARNING / ERROR / CRITICAL. **사이클 190 (2026-07-03) — never-raise 전환**: INSERT 를 try/except Exception 으로 감싸 **어떤 예외도 호출자에 전파하지 않는다** (관찰성 함수 계약). 실패 시 `logger.debug("[write_log_failed] ...")` 단독 — WARNING 이상 금지 (`_DbLogHandler` 가 다시 DB INSERT 를 시도하는 재귀 위험, 사이클 56-E 답습). 배경 = 7/3 07:59 `scheduler.py` start() 의 bare `await write_log` 가 Supabase HTTP/2 `RemoteProtocolError` 로 raise → 사이클 146 KisApiError graceful 분기 미해당 → 매매 프로세스 크래시(다운 2.7분 + 아침 task 2벌 재실행). src/ 직접 호출 72곳 무변경으로 단일 지점 영구 차단. AST 가드 `tests/unit/ast/test_cycle190_ast_write_log_guard.py` (broad except + except 내 raise 0 + debug 단독). **사이클 65 hotfix H2 (2026-06-06)**: INSERT 페이로드에 `"timestamp": datetime.now(KST).isoformat()` 강제 — 사이클 53 KST `+09:00` 패턴 답습. DB default (`now()` UTC) 의존 폐기 — 신규 INSERT 부터 KST 보장. **호환 경로 영속** (`src/main.py::_insert_log_to_db` H2-bis): 표준 logging 의 `_DbLogHandler` 위임 경로도 동일 KST 강제 — `logger.info()` / `logger.warning()` 등 모든 호출이 KST timestamp 로 저장 (write_log 직접 호출보다 호출 빈도 높음). AST 영구 가드: `tests/unit/db/test_system_logs_kst_timestamp.py` 2 케이스 (`src/` 전체 rglob INSERT 호출처 + write_log 함수 단위) — 향후 system_logs INSERT 추가 시 KST 누락 영구 차단
- **사이클 72 hotfix (2026-06-08) — `_DbLogHandler` 500ms TTL dedupe 캐시 + 11+ 사이트 write_log 직접 호출 제거 (이중 INSERT 영구 차단)**: 사이클 71 운영 실증 발견 silent 결함 (09:00~09:25 system_logs INSERT 205건 / distinct 71 = **평균 2.89x dup**, `[swing_poll]` 23x / `[stale_watcher]` 7.33x / `[stale_watcher_detail]` 확정적 2.00x) 시정. **결함 root cause**: `_DbLogHandler` (`src/main.py:137`) 가 `record.name.startswith("src.")` 모든 logger emit → `_insert_log_to_db` 위임 INSERT + 같은 emit 사이트가 `await write_log(...)` 동시 호출 → 양쪽 경로 INSERT 누적. **옵션 A' (호출자 정정 11+ 사이트)**: `realtime/websocket.py` (`[ws_heartbeat]`) + `engine/stale_watcher_core.py` 4 사이트 (`[stale_watcher]` / `[stale_force_retry]` / `[stale_force_retry_cap]` / `[stale_priority_resubscribe]`) + `engine/stale_diagnostics.py` (`[stale_watcher_detail]`) + `engine/stale_session_recovery.py` 3 사이트 (`[silent_inactive_recovery_cap]` / `[silent_inactive_force_reconnect]` / `[scan_loop_delta]`) + `engine/stale_universe_guard.py` (`[universe_excluded]`) + `engine/scanner.py` (`[priority_drop]`) + G-6 AST 추가 검출 11 사이트 (`engine/boot_manager.py` `[cash_usage_ratio]` / `engine/scheduler.py` L735/L842/L1730/L1825/L1834/L2657 등) 의 `await write_log(...)` / `await _write_log(...)` / `asyncio.create_task(_write_log(...))` 호출 전수 제거. `logger.info/warning(...)` 단독 유지 → `_DbLogHandler` 위임 단일 INSERT 보장. **옵션 D (`_DbLogHandler` dedupe 캐시, `src/main.py:137-170`)**: `_DEDUPE_TTL_SECS = 0.5` 모듈 상수 + `_dedupe_cache: dict[str, float]` 인스턴스 변수 (message → last_emit_monotonic) + `emit()` 진입 직후 `time.monotonic()` 비교 → 동일 메시지 500ms 내 중복 emit 두 번째 INSERT skip + lazy evict (100 항목 cap, TTL 경과 항목 정리). 미래 신규 emit 사이트 silent 결함 runtime 안전망. **AST 영구 가드 3 신설**: G-6 (`tests/unit/ast/test_cycle72_ast_no_logger_write_log_pair.py`, `src/` 전체 rglob 각 `write_log` 호출 ±5 줄 동시 `logger.*` 호출 0건) + G-7 (`tests/unit/main/test_cycle72_db_log_dedupe_structure_ast.py`, `_DEDUPE_TTL_SECS = 0.5` 상수 + dedupe 캐시 dict + `time.monotonic` 비교 정적 검증) + G-8 (`tests/unit/main/test_cycle72_insert_log_kst_persistence_ast.py` 2 케이스, 사이클 65 H2-bis KST 영속 회귀 가드 보강). **회귀 가드 18 케이스 (6 파일)**: `tests/unit/engine/test_cycle72_no_duplicate_insert_per_site.py` 11 + `tests/unit/main/test_cycle72_db_log_dedupe.py` 3 (freezegun + mock supabase) + AST 4. F-1 통합 테스트 2건 (`test_boot_cash_usage_ratio.py` + `test_boot_eager_refresh.py`) obsolete `calls.write_log` assertion 옵션 C 채택 제거 (사이클 72 의도 일치, G-A 단위 가드로 회귀 가드 영속). **사이클 65 H2/H2-bis 영속 (변경 0)**: `system_logs.py:44` + `main.py:131` 인라인 KST 패턴 유지 — G-8 회귀 가드 PASS 영속. **silent 결함 영구 차단 9 회 누적** (사이클 60/64/65#1/65#2/65#3/66/67/68/72). **F-2 (HIGH 운영 영향) WebSocket dup 핵심 영역**: 운영 측정 dup 상위 4건 = `src.realtime.websocket` (ACK / 구독 / 해제 / 5xx) → 사이클 73 카드 #19 인계 (G-6 AST 가드 영역 확장 검토)
- **`safe_write_log(level, message, *, fallback_debug=None)`** (사이클 56-E, 2026-06-04): `write_log` 의 graceful skip 변형. Supabase 장애 등 예외 발생 시 전파 없이 `logger.debug` 만 발화. `fallback_debug` 명시 시 그 문자열을 debug 메시지로 사용, None 시 기본 메시지 `"[safe_write_log] {message[:80]} 실패: level={level}"`. `order_engine.py` 내 `try: await write_log / except Exception: logger.debug` 동형 패턴 4곳 통합 — `[stock_master_miss]` / `[stock_master_miss stale]` / `[market_closed_blocked]` / `[positions_reconciliation]`
- `get_logs(limit=100, log_level=None, *, from_date=None, to_date=None, page=1, size=None)`: 페이징 + KST 기간 필터. 반환 `{"items": list[dict], "total": int, "total_pages": int}`. `size` 미지정 시 `limit` 흡수 (하위 호환). `from_date`/`to_date` 명시 시 `timestamp >= "{date}T00:00:00+09:00"` / `<= "{date}T23:59:59.999999+09:00"` KST 강제. supabase-py `count="exact"` 로 total 동봉, `total_pages = ceil(total / size)`
- **`search_logs(q, *, level=None, start=None, end=None, limit=200) -> {logs, total, has_more}`** (사이클 6 통합, 2026-05-20): 키워드 substring 검색. `ilike("message", "%q%")` 대소문자 무시. `level` 이 None/`"ALL"` 이면 무필터, 그 외 `eq("log_level", level)`. `start`/`end` 는 ISO 8601 시각 직접 받아 `gte`/`lte`. `limit` 1~1000 clamp (기본 200, 최대 1000). 빈 `q` ValueError. `has_more = total > len(logs)` — 200건 초과 시 UI 가 "키워드 좁히기" 안내. 라우트 `/api/logs/search` 와 1:1
- **`purge_old_logs() -> {info_deleted, high_deleted, elapsed_ms}`** (사이클 6 통합, 2026-05-20): 등급별 retention 정책 자동 정리. INFO 등급 `timestamp < now_kst - 2 days` DELETE / WARNING/ERROR/CRITICAL 등급 `timestamp < now_kst - 30 days` DELETE. **안전 가드**: 내부 헬퍼 `_purge_by_cutoff(cutoff_iso, level_filter)` 가 `cutoff_iso=None` 이면 `RuntimeError("cutoff must not be None")` raise (WHERE 누락 사고 절대 차단). **사이클 175 (2026-06-24) — PostgREST row-cap silent 결함 항구 시정 (루프 배치)**: 사이클 150 의 단발 `SELECT(id).limit(MAX_PURGE_BATCH=100_000)` 이 Supabase PostgREST `db-max-rows=1000` 기본 cap 에 silent 절단 → 1회 호출당 최대 1000행 삭제 (`[log_retention] info_deleted=1000` 매일 정확히 1000) → 하루 1회(20:10) × 1000 vs INFO 30K+/일 생성 → 640K+ 적체 → 242MB 비대. 시정 = `_purge_by_cutoff` 가 `SELECT(id).limit(PURGE_SELECT_BATCH=1000) + DELETE in_(ids)` 를 **drained 까지 루프** (ids 빈 리스트 또는 마지막 페이지 `len(ids) < PURGE_SELECT_BATCH` 시 종료) + 안전 cap 3중 (`PURGE_MAX_ITERATIONS=2000` 런어웨이 + `MAX_PURGE_BATCH=100_000` 누적 상한 = 단일 purge 호출 settlement 폭주 차단 + 마지막 페이지 조기 종료). migration/RPC/PostgREST `db-max-rows` 설정 변경 **0** (2-step + supabase-py SELECT.limit/DELETE.in_ 구조 유지, DELETE chain `.limit()` 미사용 = 사이클 6 AttributeError 영구 차단). retention 1회가 backlog 전량 드레인 → 재적체 방지. 운영 backlog 665K행 (INFO>2일 642K + WARNING/ERROR>30일 23K) 은 메인 세션이 raw SQL + `VACUUM FULL system_logs` 로 즉시 드레인 (535→368MB). 회귀 가드 = `tests/unit/db/test_cycle175_log_retention_loop.py` (8). INFO 1행 영구 로그 `[log_retention] info_deleted=N high_deleted=M elapsed_ms=K` (이제 N/M 이 1000 cap 안 걸림). 시점: `_settle` → `_log_analysis_engine` *후* + `_reset_daily_state()` *전* (분석이 system_logs 읽은 후 정리). 예외는 scheduler 가 graceful (`[log_retention_skip]` INFO + 다음 사이클 재시도)
- 상수: `INFO_RETENTION_DAYS=2` / `HIGH_RETENTION_DAYS=30` / `HIGH_LEVELS=("WARNING","ERROR","CRITICAL")` / `MAX_PURGE_BATCH=100_000` (단일 purge 호출 누적 상한) / **`PURGE_SELECT_BATCH=1000`** (사이클 175 — per-iteration SELECT limit, PostgREST `db-max-rows=1000` 정합) / **`PURGE_MAX_ITERATIONS=2000`** (사이클 175 — 루프 런어웨이 차단) / `SEARCH_DEFAULT_LIMIT=200` / `SEARCH_MAX_LIMIT=1000`

## log_reports.py — 일일 로그 분석 리포트

- `insert_log_report()`: 20:10 정산 직후 INSERT. `target_date` UNIQUE (충돌 시 None). **사이클 58 V-2 (2026-06-04)**: `input_tokens / output_tokens / total_tokens / latency_ms / cost_estimate_usd` 5 keyword 추가 (모두 기본 None — NULL INSERT). `cost_estimate_usd` 는 `Decimal | None` → DB 저장 시 `float` 변환.
- `list_log_reports(days=30)`: 최근 N일 신규순
- `get_log_report(target_date)`: 단일 영업일
- 스키마: id(uuid) / target_date(unique) / summary(text) / findings(jsonb 배열) / metrics(jsonb) / model(varchar) / created_at / **input_tokens(int, NULL)** / **output_tokens(int, NULL)** / **total_tokens(int, NULL)** / **latency_ms(int, NULL)** / **cost_estimate_usd(decimal(10,6), NULL)** (migration 031, 사이클 58)

## system_config.py — 시스템 설정 키-값 헬퍼

- **read 9함수 `execute_with_retry` 경유 (사이클 189)**: `get_cash_usage_ratio`/`get_auto_regime_adjust`/`_get_bool_or_none`/`get_buy_block_mode`/`_get_float_or_default`/`_get_bool_or_default`/`_get_int_or_default`/`_get_str_or_default_UNUSED`/`_get_string_or_none` — connection 계열 예외 1회 재시도, 기존 폴백 기본값 불변. 쓰기(`_upsert`/`_set_*`)는 직접 to_thread 유지 (AST `test_cycle189_ast_read_retry.py`)
- **task 신선도 마커 (사이클 193, 2026-07-04)**: `get_task_last_success(task_label) -> str | None` (키 `task_last_success_<label>`, `_get_string_or_none` 경유 = 189 retry 자동 수혜) / `set_task_last_success(task_label, iso_ts)` (upsert 패턴, 쓰기 = retry 미경유 영속). `task_loop_helper.run_periodic_task_loop` 의 `immediate_skip_if_fresh_hours` 게이트 전용 — 재시작 immediate run 이 N시간 이내 성공 마커 존재 시 skip (아침 프리마켓 burst 완화). 값은 KST ISO (`now_kst_iso()`)
- `get_cash_usage_ratio() -> float` / `set_cash_usage_ratio(ratio)`: 키 `cash_usage_ratio`, JSONB `{"value": float}`. 범위 `[0.0, 1.0]`, 5% 단위 자동 보정, 기본 1.0
- `get_auto_regime_adjust() -> bool` / `set_auto_regime_adjust(value)`: 키 `auto_regime_adjust`, 기본 True
- **외부 통합 토글** (DB 우선, .env fallback):
  - `get_dkstock_regime_enabled() -> bool | None` / `set_dkstock_regime_enabled(value)`: 키 `dkstock_regime_enabled`
  - `get_kis_mcp_enabled() -> bool | None` / `set_kis_mcp_enabled(value)`: 키 `kis_mcp_enabled`
  - 기본값 `None` — 호출자가 `settings.*` 환경변수 fallback. `cash_usage_ratio`/`auto_regime_adjust` 와 다른 점 (.env 호환 보존)
  - 내부 헬퍼 `_get_bool_or_none(key)` / `_set_bool(key, value)` — JSONB `{"value": bool}` + 과거 호환 (직저장 bool / 'true'/'false' 문자열) 모두 흡수
- **매수 가드 4 모드 + 4 임계값**:
  - `get_buy_block_mode() -> str` / `set_buy_block_mode(mode)`: 키 `buy_block_mode`, 기본 `HARD` (사이클 2 회귀 보존). 4 모드 외 `ValueError`
  - `get_buy_block_thresholds() -> BuyBlockThresholds` (Pydantic) / `set_buy_block_thresholds(vix_threshold=, fg_high_threshold=, fg_low_threshold=, defensive_enabled=)` 부분 갱신
  - 4 키: `buy_block_vix_threshold` (25.0) / `buy_block_fg_high_threshold` (85.0) / `buy_block_fg_low_threshold` (15.0) / `buy_block_regime_defensive_enabled` (true)
  - **.env fallback 없음** — 운영 가변 (DB 미설정 → 코드 디폴트)
- **사이클 23 AI 자문 자동 적용 토글**:
  - `get_auto_apply_enabled() -> bool` / `set_auto_apply_enabled(value)`: 키 `auto_apply_enabled`. 기본 **False** (안전 우선). .env fallback 없음 — 운영자 명시 활성화 후에만 P3 자동 적용 작동
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
- 범위 외 입력은 `ValueError`. supabase 동기 호출은 `asyncio.to_thread` 위임

## kis_quote_accounts.py — 보조 KIS 시세 수신 계좌 풀

- `list_accounts(active_only=False)` / `get_account(id)` / `get_account_by_label(label)` — 응답은 `KisQuoteAccount` (`app_secret_masked` 만, 평문 절대 노출 안 함)
- **read 4함수 `execute_with_retry` 경유 (사이클 189)**: `list_accounts`/`get_account`/`get_account_by_label`/`get_credentials_for_token_manager` — connection 계열 예외 1회 재시도(7/1 실측 `[kis_quote_accounts] list 실패` 11건/일 흡수), 기존 graceful·캐시 로직 불변. 쓰기(insert/update/delete)는 직접 to_thread 유지
- **`list_accounts` 60s TTL 메모리 캐시**: 모듈 전역 `_list_cache` / `_list_cache_expires_at` + `invalidate_list_cache()` + `_LIST_CACHE_TTL=60.0`. `time.monotonic()` 비교 → TTL 내 캐시 hit (DB 호출 0). `active_only=True/False` 키 분리. DB 예외 + 캐시 있음 → stale 반환 (graceful), 캐시 없음 → 빈 리스트 (회귀 보존). INSERT/UPDATE/DELETE 직후 `invalidate_list_cache()` — 운영 토글 즉시 반영. Settings/Dashboard 30s 폴링 + 컨테이너 재시작 race + supabase HTTP/2 stale connection 결함 대응
- `insert_account(label, app_key, app_secret, kis_env)` — label UNIQUE 충돌 시 `LabelConflictError`, 빈 값/kis_env 부적합 시 `ValueError`
- `update_account(id, active=None, label=None)` — 부분 갱신. app_key/app_secret 수정 미지원 (보안 감사 추적성 — 삭제 후 재등록 패턴)
- `delete_account(id)` — 존재 시 True, 미존재 False
- `get_credentials_for_token_manager(label)` — **토큰 매니저 전용 평문 노출 함수**. `src/auth/token.py::get_token_manager(label)` lazy 초기화에서만 호출. API 응답/로그 절대 노출 금지
- 테이블: `kis_quote_accounts` (UUID PK, label UNIQUE, active=true 부분 인덱스)
- 자금 안전: 본 모듈 응답은 **시세 수신 한정**. order.py / balance.py / 체결통보 구독은 메인 계좌만

## strategy_funnel.py — 조건검색 단계별 추적 (사이클 34, 2026-05-21)

- `insert_snapshot(target_date, strategy_id, step_no, step_name, survived_count, survived_tickers, excluded_count, excluded_sample, step_conditions=None, is_provisional=False)`: 단일 단계 snapshot **UPSERT** (사이클 145 (2026-06-16) — `.upsert(on_conflict="target_date,strategy_id,step_no")` 전환 영속). **사이클 171 (2026-06-22)** — `is_provisional: bool = False` 인자 추가 (migration 040 `is_provisional BOOLEAN NOT NULL DEFAULT FALSE`). True = 16:20 저녁 잠정 캡처 (전일 마스터 + 16:10 basics 기준) / False (기본) = 09:30 자동 + 수동 trigger (확정). payload 동행 (기존 호출자 미지정 → False, 회귀 0). 사이클 34 시점 = `.insert(row)` + UNIQUE `(target_date, strategy_id, step_no, snapshot_at)` → snapshot_at 매번 갱신 → 중복 INSERT 가능 → 운영 DB 6/15 BFB step_no=1 = 8 row 결함. 사이클 145 시정 = `.upsert(on_conflict=...)` + migration 035 UNIQUE 변경 (snapshot_at 키 폐기) → 같은 `(target_date, strategy_id, step_no)` 영역 = 최신 값 1 row. snapshot_at = supabase DEFAULT now() UPSERT 시 자동 갱신. **사이클 41 (2026-05-22)**: `survived_tickers: list[str \| dict]` 호환 (string 사이클 34 형식 + dict `{ticker, name}` 사이클 41 형식), `excluded_sample: list[dict]` (`{ticker, name, reason}` 수치 포함 사유), `step_conditions` 옵셔널 (단계 조건 명시 — UI 툴팁). DB JSONB 스키마는 변경 없음 (native dict 지원)
- `list_snapshots(target_date, strategy_id)`: 특정 영업일 + 전략 의 모든 단계 (`step_no` ASC)
- `list_recent_by_strategy(strategy_id, days=7)`: 최근 N영업일 추이
- **JSONB cap**: `survived_tickers` 200건 / `excluded_sample` 20건 자동 적용 (응답·저장 크기 보호)
- 테이블: `strategy_funnel_snapshots` (UUID PK + 인덱스 2: `target_date DESC` / `(strategy_id, target_date DESC)`)
- 호출: `POST /api/strategy-funnel/snapshot` 수동 trigger + **사이클 39 자동 hook** (`scheduler._auto_capture_funnel_snapshots`, 09:30 `_scan_loop` 첫 진입 시 일일 1회 자동 발화). **사이클 39+41**: BFB/VCP/donchian `prepare()` 가 8단계 `_record_funnel_step` hook 으로 각 단계 통과/탈락 ticker + 수치 포함 사유 (`reason="음봉 비율 35% > 30%"` 등) 캡처 → 단계별 + 최종 (`step_no=99`) DB row 모두 저장. `_reset_daily_state` 동행 reset. **사이클 171 (2026-06-22)** — 공통 헬퍼 `scheduler.capture_funnel_snapshots(registry, *, is_provisional)` 추출 (3 호출처 공유: 09:30 자동 / 16:20 저녁 잠정 / 수동 trigger). 09:30 자동 + 수동 trigger 모두 단계별 + step_no=99 캡처 (수동 trigger 가 종전 step_no=99 단독 → 단계별 전체로 전환, is_provisional=False)

## stock_master.py — 종목 마스터 캐시

- `upsert_one(StockBasics)` / `get(ticker) -> Optional[StockBasics]` / `is_stale(ticker, max_age_hours=24) -> bool`
- 테이블: `stock_master`. PK `ticker` (KRX 6자리), `refreshed_at` 24h TTL
- NXT 거래가능 사전 판별용 — `OrderEngine._strategy_exchange_async` + `scheduler._execute_next_day_clear` + `execute_sell` 거부 사후 보강 3경로
- 호출: 매수/매도 진입 직전 lazy. miss/stale → `inquire_stock_basics` 호출 후 upsert
- **eager 사전 갱신**: `scheduler._boot()` 마지막에 `_eager_refresh_stock_master_for_held_positions()` — 보유 + `_pending_next_day_clear` 합집합 sequential upsert (24h fresh skip). lazy 한계 (첫 사이클 캐시 miss → SOR/NXT 발사 → KIS 거부) 차단
- **ticker 정규화**: PK 형식 KRX 6자리. `inquire_stock_basics` 가 `_normalize_ticker()` 로 KIS `pdno` 12자리 표준코드 → 마지막 6자리 추출. `upsert_one` 이중 안전망 — 6자리 미준수 입력도 정규화 후 저장 (WARNING)
- **사이클 162 (2026-06-18) — `pending_next_day_clear` 테이블 + CRUD 신규 (HIGH 익일청산큐 영속화)**: 알테오젠/알지노믹스 6/17 15:20 강제청산 누락 (EC2 재기동 시 `_pending_next_day_clear: set[tuple]` 메모리 휘발) 결함 시정. `supabase/migrations/038_pending_next_day_clear.sql` = `(target_date DATE, ticker TEXT, strategy_id TEXT)` 복합 PK + `created_at TIMESTAMPTZ`. `src/db/pending_next_day_clear.py` 4 CRUD = `save_pending_ndc(target_date, ticker, strategy_id)` / `delete_pending_ndc(ticker)` / `load_pending_ndc(target_date)` / `purge_pending_ndc_before(target_date)`. scheduler `_execute_next_day_clear` 등록 2 사이트 (nxt_not_tradable / nxt_open_missing) + `_drain_pending_next_day_clear` finally DELETE + `_reset_daily_state` fire-and-forget purge. boot_manager `boot()` 마지막 단계 `load_pending_ndc(today)` → 메모리 set 복구 (사이클 149 VI seed 패턴 답습). DB 실패 시 메모리 보존 graceful (사이클 88 답습). 회귀 가드 7 케이스. 매매 안전성 무영향 (재기동 후 알테오젠/알지노믹스 패턴 재발 차단). 운영 DB 적용 완료 (Supabase MCP).
- **사이클 170 (2026-06-20) — `list_by_filter(return_stage_counts: bool = False)` 인자 추가 (funnel 관찰성, 카드 A)**: True 시 단일 필터 루프 내 단계별 생존 ticker 누적 후 `(filtered, {"union_tickers", "mcap_tickers", "trade_tickers"})` 튜플 반환. union = index/형식/exclude 통과 (시총·거래대금 컷 *전*) / mcap = 시총컷 후 / trade = 거래대금컷 후 (= 최종 filtered, 순서 정합). False (기본) = 현행 list (**기존 호출자 전원 미지정 → 회귀 0**). cap 미적용 — 정확 count 보존 (소비처 `_record_funnel_step` 가 survived 리스트 200 cap + survived_count 정확 기록, rows 는 fetch buffer cap). **필터 로직/임계/순서/limit break 불변 = 매수 풀 행위 보존** (G-A-1 HIGH = `return_stage_counts=True` filtered == False 결과 원소·순서). 호출자: donchian `_scan_universe` (`self._scan_stage_counts` 보관 → prepare step1=union / step2=trade collapse 차단). 회귀 가드 `tests/unit/db/test_cycle170_card_a_stage_counts.py` 6 케이스. 매매 안전성 무영향 (관찰성 전용).
- **사이클 153 (2026-06-16) — `list_by_filter()` KOSPI200 / KOSDAQ150 인자 추가**: 사용자 결정 Q2=A `is_kospi200: bool | None = None` + `is_kosdaq150: bool | None = None` 인자 (사이클 108 nxt_tradable 패턴 답습). 양쪽 모두 True 시 **OR 합집합** (donchian_swing FUNNEL_STAGES[0] "코스피200+코스닥150 합집합" 의무 정합). 한쪽만 True/False 시 AND (PostgREST `.eq()` 인덱스 활용 = `idx_stock_master_is_kospi200` + `idx_stock_master_is_kosdaq150` 부분 인덱스). 둘 다 None 시 무필터 (회귀 보존). **사이클 121 (2026-06-12) silent 결함 시정** = donchian_swing.py::_scan_universe() 영역 인자 전달 누락. 운영 DB 실측 (2026-06-16) = KOSPI200 1796 종목 + KOSDAQ150 149 종목 = ~1945 합집합. 회귀 가드 = `tests/unit/db/test_cycle153_list_by_filter_index_flags.py` (5 케이스). 매매 안전성 무영향 영속 (사이클 38 명문화 + scanner 매수 진입 전 한정).
- **사이클 108 (2026-06-11) — `list_by_filter()` 신규 메서드 (Plan Phase A 완료, VB/LTV/BFB stock_master 베이스 전환 + KIS volume-rank API 100% 폐기)**: 사이클 104 인계 Q5=B (LOW 위험 자문 생략) + 사이클 107 raw 보강 의존성 해소 완료 → Plan Phase A 데이터 활용 가능 → 사이클 108 = `list_by_filter()` 신규 메서드 + VB/LTV/BFB `_scan_universe()` 전환 통합. 사용자 결정 Q1=A 시총 = `hts_avls` (KIS FHKST01010100, 백만원 단위) + Q2=A 통합 단일 사이클 (3 전략 동시 전환) + Q3=C 4 필터. **`list_by_filter(*, market=None, min_market_cap=0, min_trade_amount=0, exclude_tickers=None, nxt_tradable=None, limit=500)` 시그너처** (cycle 108 도입 시점, 모두 keyword-only. 후속 인자 = 사이클 153 `is_kospi200`/`is_kosdaq150` + 사이클 170 `return_stage_counts` — 각 절 참조. `exclude_etf` 인자는 코드에 없음): (1) **Supabase 조회** (테이블 = `stock_master`, 2배 buffer `limit × 2` — 필터 후 결과 < limit 회피). (2) **Python-side JSONB 필터링**: `raw.hts_avls × 100_000_000` 억원 단위 환산 ≥ `min_market_cap` (사이클 166 정정 — cycle 108 시점 `× 1_000_000` 백만원 가정은 100배 silent 결함, 코드 L682) + `raw.acml_tr_pbmn` 거래대금 ≥ `min_trade_amount` + ticker `not in exclude_tickers` + `nxt_tradable` (None 시 무필터, 사이클 32 R4 답습). ETF 키워드 제외 + 6자리 ticker 검증은 list_by_filter 본체가 아닌 **호출자 `_scan_universe`** 가 수행 (`ETF_KEYWORDS`, 사이클 89 영속). (3) **graceful** (raw miss / hts_avls miss / acml_tr_pbmn miss = 통과, 사이클 65 Q6-1 09:00 race graceful 답습). (4) **filter 후 limit 적용** (final result ≤ limit). **사이클 107 raw 보강 의존성**: `inquire_stock_basics` 영역에서 `hts_avls` (사이클 108 신규) + `acml_tr_pbmn` (사이클 107) 키 자동 포함 = 사이클 108 `list_by_filter` 필터링 데이터 확보. **호출**: VB/LTV/BFB 3 전략 `_scan_universe()` (`src/engine/strategies/{volatility_breakout, long_tail_volatility, bull_flag_breakout}.py`). **운영 효과**: KIS `volume-rank` API (FHPST01710000) 호출 100% 폐기 (VB 3 + LTV 3 + BFB 3 = 9 호출/일 → 0 호출, 사이클 17 OPSP0002 backoff + KIS LMS chain 안전 효과). **회귀 가드**: `tests/unit/db/test_cycle108_list_by_filter.py` (Supabase 조회 + Python-side JSONB 필터링 + 2배 buffer + graceful + filter 후 limit 적용). **영속 의무 매트릭스**: 사이클 32 R4 universe guard 영속 (nxt_tradable 답습) + 사이클 89 답습 (KOSPI/KOSDAQ + ETF 제외 + 6자리 ticker 영속) + 사이클 107 영속 (raw 보강 의존성 영속) + 사이클 81 G-AST1 영속 (`bfdy_clpr` + `hts_avls` 덮어쓰기 금지 영속). **매매 안전성 무영향 확정** (종목 마스터 캐시 조회 한정 + scanner 단계 후보 풀 구성 한정 + 매수 진입 전 한정 + 매도/익일청산 hot path 무관 + 사이클 38 명문화 영속). Plan Phase C UI 운영자 필터링 호환 (`exclude_tickers` 인자 활용 + Settings UI 영역 가능).
- **사이클 107 (2026-06-11) — raw JSONB 3 키 추가 (CTPF1002R + FHKST01010100 merge, Plan Phase A 데이터 의존성 해소)**: `stock_master.raw` JSONB 영역에 사이클 107 시정 이후 자동 포함되는 3 키 명세 — `acml_tr_pbmn` (누적 거래 대금) + `lstn_stcn` (상장 주수) + `acml_vol` (누적 거래량, `prdy_vol` 동등). `src/api/condition.py::inquire_stock_basics` 본체 보강 (+44L 순증, 사이클 107 시정) → CTPF1002R 호출 *후* FHKST01010100 (`inquire_price` 주식현재가 시세) 추가 호출 → 응답 merge → raw JSONB 통합. CTPF1002R 응답 67 컬럼 = 3 키 모두 부재 (KIS MCP 정본 확정) → FHKST01010100 호출 영역에서만 입수 가능. **CTPF1002R 기존 키 덮어쓰기 금지 설계** = `bfdy_clpr` 정합 (사이클 81 G-AST1 영속). **호출 시점**: 매수/매도 진입 직전 lazy `upsert_one` 경로 + 사이클 101 `_full_universe_load_once` (사이클 106 lifecycle 영속) 배치 호출. **운영 효과 (사이클 107 시정 push 후)**: stock_master 2,800 종목 × 2 KIS 호출 + 50ms sleep = 약 5분 소요 / 향후 Plan Phase A (사이클 108+) `list_by_filter(min_market_cap=, min_trade_amount=)` 데이터 의존성 해소. **graceful fallback**: FHKST01010100 RuntimeError / KisApiError = CTPF1002R 단독 raw 반환 (호출자 보호 = stock_master 저장 graceful). **회귀 가드**: `tests/unit/api/test_cycle107_inquire_stock_basics_merge.py` 12 케이스 (HIGH 4 = 양쪽 API 호출 + raw 3 키 포함 + graceful fallback + AST 영구 가드). **영속 의무 매트릭스**: 사이클 81 G-AST1 (`bfdy_clpr` 덮어쓰기 금지) + 사이클 98 G-DOC1 (KIS 정본 `chk_inquire_price.py` 인용 의무) + 사이클 101 영속 (`_full_universe_load_once` 호출 영역 자동 반영) + 사이클 106 영속 (`_full_universe_load_task_loop` 변경 0 = lifecycle race 차단). **매매 안전성 무영향 확정** (종목 마스터 캐시 한정 + 매매 hot path 무관 + Rate Limit 50ms sleep KIS LMS chain 안전)

## stock_master_daily.py — KIS 일봉 정규화 (사이클 122, 2026-06-12)

- 테이블: `stock_master_daily` (migration 033). PK 복합 `(ticker, bas_dd)` + 인덱스 `(ticker, bas_dd DESC)` + `(bas_dd DESC)`
- 컬럼 10종: `open_price`/`high_price`/`low_price`/`close_price`/`volume`/`trade_value`/`change_rate`/`flng_cls_code`/`prtt_rate`/`raw JSONB`
- KIS FHKST03010100 (`chk_inquire_daily_itemchartprice.py` 정본) 응답 키 매핑 — `stck_bsop_date / stck_oprc / stck_hgpr / stck_lwpr / stck_clpr / acml_vol / acml_tr_pbmn / prdy_ctrt / flng_cls_code / prtt_rate`
- 9 CRUD 함수:
  - `upsert_daily(ticker, bas_dd, row)` — KIS row 단건 정규화 후 upsert
  - `upsert_batch(ticker, rows)` — 100건 배치 chunk (Supabase HTTP/2 stale 회피, 사이클 26 답습)
  - `get_recent_daily(ticker, n)` — 최근 N일 (DESC) — donchian/VCP 입력
  - `get_donchian_high(ticker, lookback=20)` — 직전 N일 최고가 (당일 제외)
  - `get_atr(ticker, period=14)` — Wilder smoothing 14일 ATR
  - `count_all()` / `count_by_ticker(ticker)` — 적재 진단
  - `max_bas_dd(ticker)` — 백필 vs 증분 자동 분기 키 (스캐너 사용)
  - `get_recent_daily_with_fallback(ticker, n)` — DB miss 시 `fetch_daily_candles` 폴백 (사이클 14 호환)
  - **`get_recent_daily_normalized(ticker, days, *, min_required=None)`** (사이클 172, 2026-06-22) — DB일봉 어댑터. DB row 의 `raw` JSONB (KIS 원본 키 `stck_clpr`/`stck_oprc` 등 보존) 를 **그대로 반환** → 사이클 173 prepare 의 `c.get("stck_clpr")` 무변경 사용 보장. DB 부족 (`< min_required`, 기본 None = `max(days//2, 10)`) 시 `fetch_daily_candles` KIS 폴백 (원본 KIS 키 반환). raw 키 부재 row 는 row 자체 반환 (graceful). 사이클 81 G-AST1 raw JSONB 변형 0 영속.
    - **사이클 173 (2026-06-22) — 락/신선도 게이트 추가 (수정주가 divergence silent 결함 방어, HIGH)**: domain-expert 자문 `_workspace/domain_consult/cycle173_prepare_db_equivalence.md` 완화책 1 채택. 어댑터에 2 게이트 추가 (DB 사용 전 검사 순서): **(1) 락 게이트 (G-EQ-3, 최우선)** — `get_recent_daily(ticker, days)` 윈도우 내 1 row 라도 락 발생 (`_row_has_lock`: `flng_cls_code not in ("","00")` OR `abs(float(prtt_rate)) > 0`) → DB 버리고 `fetch_daily_candles` KIS 강제 폴백. 근거: 수정주가는 조회 시점 의존값 → DB 박제 과거봉(락 전) vs KIS 재조정(락 후) 어긋남 → 락 종목만 KIS 폴백이 유일한 silent 방어. 검사 = DB row top-level `flng_cls_code`/`prtt_rate` 컬럼 (raw 와 별개 정규화 컬럼, migration 033) → **KIS 추가 호출 0건 탐지**. **(2) 신선도 게이트 (G-EQ-4)** — `max_bas_dd(ticker)` 가 `today - DAILY_STALENESS_DAYS(=4)` 보다 오래 (D-1 미적재 race) → KIS 폴백. `max_bas_dd None` (판정 불가) 은 graceful 통과. **(3) min_required 게이트 (172)** — `len < min_required` → KIS 폴백. **★ team-leader 운영 DB 실측 확정 (자문 보정)**: `flng_cls_code` 기본 = `""`/`"00"` (실측 99.6% "00", 비기본 01/02/03/05 = 락). `prtt_rate` 기본 = `0`/`""`/`None` (실측 99.7% "0.0000" — **자문의 `!= 1.0` 은 틀림, 전 종목 폴백 유발**). KIS 정본 docstring 은 코드 *값 의미* 미제공 → 비기본=무조건 락 의심 보수적 폴백. 헬퍼 3 = `_row_has_lock` / `_extract_raw` (raw 추출 DRY) / `_kis_fallback` (락/신선도/부족 공통 + 실패 시 DB graceful). 상수 `DAILY_STALENESS_DAYS = 4` (주말 2 + 공휴일 마진, 거짓 폴백 차단). **prepare 연결 = 사이클 173** (5 전략 days/min_required 명시: VB/LTV=22, donchian=63, BFB=35, VCP=100). 회귀 가드 `tests/unit/db/test_cycle173_adapter_lock_stale_gate.py` 13 케이스 (G-EQ-3 락 5 + G-EQ-4 신선도 3 + G-EQ-5 경계 2 + G-EQ-6 폴백 1 + 우선순위 1 + AST 1). 의미 전환 2건 = `test_cycle172_safety_no_trading_diff.py` (SAFETY-2 prepare 어댑터 호출 0 → xfail / SAFETY-3 raw 추출 헬퍼 위임 정합). 매매 안전성 무영향 (scanner 매수 진입 전 한정, 사이클 38).
- **`DAILY_RETENTION_DAYS` (사이클 172) — 150 → 230** (도입 당시 근거 "VCP 220일 + 10일 마진"). `purge_old_rows` 로직 불변 (상수만, "230일 지난 것만 삭제"). 사이클 150 (VCP T-120일 + 30일 마진) → 사이클 172 확장. 의미 전환 1건 = `test_cycle150_supabase_capacity.py::TestG150DailyRetentionDays` (`== 150` → `== 230`, 사이클 66 K-2 패턴). 용량 ~22MB → ~34MB (무료 500MB 중 7%).
  - **⚠️ 사이클 196 (2026-07-07) 정정 — 230 은 달력일, VCP 220 영업일을 보유 못 함**: retention 230 **달력일** = **154 영업일** 만 보유 (운영 DB 실측 = rows_within_retention 154). 사이클 172 근거 "VCP 220일 lookback 충족"은 **오류** (220 영업일 = ~308 달력일 > 230). 이 불일치가 `existing_count < _DAILY_LOAD_VCP_BACKFILL_DAYS(=220)` 를 영구 True 로 만들어 VCP 348종목 무한 재backfill(churn) 유발 → **사이클 196 = VCP backfill target 220→120 하향** (retained 154 내 수렴, `src/engine/scanner.py` `_DAILY_LOAD_VCP_BACKFILL_DAYS`). **retention 230 은 불변** (VCP prepare 실사용 100일 << 154 보유 → 충분). 향후 VCP 220 EMA 원설계 복원 시 retention 을 ~320 달력일로 상향 필요.
- **사이클 192 (2026-07-04) — `purge_old_rows` 날짜 슬라이스 루프 배치 전환 (전 실행 실패 결함 항구 시정)**: 사이클 150 도입 시점의 단일 bulk DELETE (`delete().lt("bas_dd", cutoff)`) 가 supabase-py 기본 `returning="representation"` 으로 적체 47,924행 × raw JSONB 를 응답으로 반환 시도 → **6/16 도입 이래 매 실행 실패** (`[stock_master_daily_purge] 실패 graceful` 515건, raw SQL 동일 DELETE 는 즉시 성공 = PostgREST 계층 결함 확정). 시정 = `PURGE_MAX_DATE_ITERATIONS=500` cap 루프: (1) SELECT `bas_dd` lt cutoff + **protected 제외** + order asc + limit 1 → 빈 결과 drained break (2) 그 날짜 전체 DELETE `delete(count="exact", returning="minimal").eq("bas_dd", oldest)` + protected 제외 → deleted 누적. **SELECT 쪽 protected 제외 누락 금지** — protected 만 남은 날짜 무한 재선택 = never-drain 회귀 (P-3 HIGH 가드). 예외 graceful = 부분 누적 deleted 반환 + `logger.exception` 에 `type(exc).__name__: str(exc)[:150]` 계측 (사이클 190 패턴). 시그니처/반환 계약/16:15 task/`DAILY_RETENTION_DAYS=230` 불변 + `execute_with_retry` 미경유 영속 (G-187-A2). 회귀 가드 17 (`test_cycle192_daily_purge_loop_batch.py` 12 + `test_cycle192_ast_purge_loop.py` 5) + 의미 전환 2 (cycle150 G-150-DAILY-3 / cycle172 test_ret2 — mock 형상만, intent 보존). 운영 적체 47,924행은 메인 세션 raw SQL 즉시 드레인 완료 → steady-state 하루 1날짜(~3.5K행).
- **사이클 187 (2026-06-30) — read 4함수 `execute_with_retry` 경유 (Supabase HTTP/2 stale connection 흡수)**: `get_recent_daily`/`count_all`/`count_by_ticker`/`max_bas_dd` 가 `asyncio.to_thread(lambda: ...execute())` → `src.db.supabase.execute_with_retry(lambda: ..., op="<함수명>")` 경유(connection 계열 예외 1회 재시도, `max_bas_dd` ticker None/지정 2분기 build if/else 후 단일 호출). 기존 `try/except Exception: logger.exception(...graceful)` + 폴백 반환값(`[]`/`0`/`None`) **불변**(retry 소진 시 마지막 예외가 graceful 로 떨어짐). **쓰기 3함수(`upsert_daily`/`upsert_batch`/`purge_old_rows`)는 미경유**(직접 to_thread 유지 = 멱등 우려 제외, AST G-187-A2 영구 불변식). `get_recent_daily_normalized`(사이클 173 어댑터)는 내부에서 `get_recent_daily` 호출이라 retry **간접 수혜**(KIS 폴백 빈도 감소). 배경 = EC2 운영 `httpx.RemoteProtocolError: Server disconnected` 90건/24h(16:00 일봉 task stale HTTP/2 연결 재사용). **테스트 주의**: `freeze_time` 안에서 prepare/stock_master_daily read 를 태우면 retry 의 `asyncio.sleep(0.2)` 이 동결 `time.monotonic` 과 결합해 무한 hang → DB read 를 mock 하거나 freeze 밖에서 read (사이클 187 BFB 회귀 흡수 교훈).
- Supabase 동기 SDK 호출은 `asyncio.to_thread()` 위임 (사이클 53 정책 답습)
- 영속 의무: KST timestamp `_kst.now_kst_iso()` 사용 (사이클 68 G-10b AST) + raw JSONB 덮어쓰기 금지 (사이클 81 G-AST1 답습)
- **UI 활용 영역 (사이클 124, 2026-06-12)**: `stock_master_daily` 컬럼 추가 시 UI 동기화 의무 영속 — `GET /api/stock-master/{ticker}/daily?days=N` 라우트 (`src/routes/stock_master.py`) + `frontend/src/pages/StockMaster.tsx::DailyTab` 30 row 테이블. `get_stats()` 응답에 `total_daily_rows` + `last_daily_load_at` 노출. 절차 상세는 `frontend/CLAUDE.md` 사이클 124 본문 참조

## stock_master_financial.py — KIS 재무 5 TR 정규화 (사이클 C1, 2026-07-15)

- 테이블: `stock_master_financial` (migration 041). PK 복합 `(ticker, stac_yymm, div_cls)` — `div_cls` 0=년/1=분기 + 인덱스 `ix_smf_ticker_div (ticker, div_cls, stac_yymm DESC)`
- 컬럼 18종 정규화 NUMERIC: 손익 5 (`sale_account`/`sale_totl_prfi`/`bsop_prti`/`thtr_ntin`/`depr_cost`) + 대차 7 (`cras`/`fxas`/`total_aset`/`flow_lblt`/`total_lblt`/`total_cptl`/`cpfn`) + 수익성 2 (`cptl_ntin_rate`/`sale_totl_rate`) + 안정성 2 (`lblt_rate`/`crnt_rate`) + 기타 2 (`ebitda`/`ev_ebitda`) + `raw JSONB` + `refreshed_at TIMESTAMPTZ`. 마법공식(EV/EBITDA·ROC) + F-Score-7 (`src/engine/quant_score.py`) 원천 데이터
- CRUD 함수 (`stock_master_daily.py` 미러):
  - `upsert_financial_batch(ticker, rows)` — 100건 배치 chunk + `on_conflict="ticker,stac_yymm,div_cls"` + graceful + KST (`now_kst_iso`, 사이클 68 영속)
  - `get_financial_series(ticker, div_cls="0", limit=3)` — `execute_with_retry` 경유 (사이클 187 read retry). 최근 N기 (`stac_yymm` DESC). div_cls "0"=년/"1"=분기
  - `max_stac_yymm(ticker, div_cls="0")` — 신선도/백필 게이트 키 (스캐너 사용)
  - `count_all()` — 적재 진단
- Supabase 동기 호출 `asyncio.to_thread()` 위임 + raw JSONB 덮어쓰기 금지 (사이클 81 G-AST1 답습)
- 호출자: `src/engine/scanner.py::_stock_master_financial_load_once()` (주1회 16:40 적재) + `src/engine/strategies/volatility_breakout.py::_apply_quant_filter_in_prepare()` (관찰 훅, 사이클 C3)
- 매매 hot path 무관 (재무 적재 = 매수 진입 전 데이터 계층, 사이클 38)

## stock_master.py — 사이클 129 master_raw 별도 컬럼 (2026-06-14)

KIS 공식 일일 마스터 파일 (`kospi_code.mst` / `kosdaq_code.mst`) 영역 = `master_raw JSONB` 별도 컬럼 영구 영속 (사이클 81 G-AST1 영속 절대 보호 = raw 영역 변경 0). migration 034 `IF NOT EXISTS` idempotent 영속.

### `master_raw` 컬럼 영역 (migration 034)

- 컬럼: `master_raw JSONB NOT NULL DEFAULT '{}'::jsonb` + `master_raw_updated_at TIMESTAMPTZ`
- 인덱스 2건: GIN (master_raw 키 검색) + DESC NULLS LAST (갱신 시각 진단)
- 사이클 81 G-AST1 영속 보호: `raw` 영역 변경 0 (`bfdy_clpr` / `hts_avls` 덮어쓰기 0 영속) — AST `tests/unit/ast/test_cycle129_ast_master_raw_separation.py` 영구 가드

### CRUD 함수 영역 (사이클 129, +77L 영속)

- `upsert_master_raw(ticker, master_raw: dict, *, is_kospi200: bool = False, is_kosdaq150: bool = False) -> None` — master_raw JSONB upsert + `master_raw_updated_at` KST 강제 (사이클 68 `_kst.now_kst_iso()` 영속). **사이클 153 (2026-06-16)** `is_kospi200` / `is_kosdaq150` 동행 명시 영속 (Q1=A 사용자 결정 영속 + 사이클 146 nxt_tradable 패턴 답습) — ON CONFLICT DO UPDATE 영역이 payload 키 영역만 SET → 기존 ticker 갱신 시 명시 의무
- `get_master_raw(ticker) -> Optional[dict]` — 단건 조회 (lazy fallback 없음, 16:30 KST 매스 적재 영역)
- `count_master_raw_today() -> int` — KST 영업일 기준 master_raw_updated_at 카운트 (운영 진단 영역)

### 호출자 영역

- `src/engine/scanner.py::_stock_master_master_load_once()` (사이클 129) 16:30 KST 매스 적재
- `src/engine/scanner.py::_is_master_blocked_for_entry(ticker)` (사이클 129) 1단계 차단 7건 hook
- ~~`get_market_cap_millions`~~ (사이클 167 폐기 — dead code, callsite 0건. 실제 시총 필터는 `list_by_filter` / `list_paged_by_filter` 직접 수행, 사이클 166 억원 정합)

## stock_master.py — 종목마스터 조회 영역 (사이클 128, 2026-06-13)

사이클 126이 `count_all` 만 `count="exact"` 별도 쿼리로 시정. 나머지 4 카운트는 `.range(0, 9999)` raw 후 Python-side `sum()` 영속 → **Supabase PostgREST `max-rows` 1,000행 silent cap** → 4 카운트 부분 집계 (`nxt_tradable_count` 운영 실측 400 → UI ~150 silent 결함). 사이클 128 시정 = 4 카운트 모두 `count="exact"` + filter 별도 쿼리 (사이클 126 패턴 100% 답습).

### `get_stats()` 4 카운트 시정

- 헬퍼 `_count_exact(filter_callable)` 캡슐화 — 동일 `count="exact"` + `.limit(0)` 패턴 4회 반복 회피
- `bfdy_clpr_present` / `with_hts_avls` / `with_acml_tr_pbmn`: JSONB 키 존재 + 0 제외 조합. **jsonb operator path 채택** (`raw->'bfdy_clpr'` numeric 비교) — text path (`raw->>'bfdy_clpr'`) gte 자릿수 비교 결함 (1조 이상 실제 332건 vs text 비교 2,696건 silent 결함, Supabase MCP READ-ONLY 검증) 영구 차단
- `nxt_tradable_count`: `.eq("nxt_tradable", True)` 단순 컬럼 필터
- `top_10_recent`: 별도 `limit(10)` fetch (전체 raw 의존 영구 폐기)
- AST 영구 가드 (`tests/unit/ast/test_cycle128_ast_no_range_9999_silent_cap.py`): `src/db/stock_master.py` 본체 `.range(0, 9999)` 잔존 0건 — silent cap 패턴 영구 차단

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

## parameter_recommendations.py — 전략수정 AI자문 이력

- `insert_recommendation()`: 20:00 자문 생성 시 INSERT (status: pending). `(target_date, strategy_id)` unique
- `list_recommendations(days=30)`: 최근 N일 이력 (신규+처리 통합)
- `get_recommendation(id)`: 단일 자문 상세
- `update_recommendation_status(id, status, applied_params=..., applied_weight=...)`: status 갱신 + `applied_at`/`rejected_at` 자동 기록. applied/partial 상태에서만 페이로드 포함
- `expire_pending_before(target_date)`: 이전 pending 자동 만료
- 컬럼: `recommended_weight` NUMERIC nullable / `code_review_notes` TEXT nullable (≤2000자) / `applied_weight` NUMERIC nullable / `weight_reasoning` TEXT nullable (≤1000자) / `backtest_summary` JSONB. INSERT 시점 `applied_weight=None`, apply 라우트가 사용자 명시 토글일 때만 채움
- **사이클 23**: `status='applied_auto'` 추가 — AI 자문 자동 적용 전용 (`migration 028`). 운영자 수동 'applied' 와 분리하여 추적성 확보. `list_pending_by_date(target_date)` 헬퍼 신규 추가

## DB 스키마

- `supabase/migrations/001_init.sql` 정의
- `trade_history.status`: PENDING → COMPLETED / PARTIAL → CANCELLED
- `trade_history.trade_type`: BUY / SELL
- `trade_history` 부분 UNIQUE 인덱스 `(ticker, order_no, trade_type) WHERE order_no IS NOT NULL AND != ''` (migration 029, 사이클 30)
- `parameter_recommendations.status`: pending → applied / partial / rejected / expired / applied_auto
- `strategy_funnel_snapshots` (migration 030, 사이클 34): UNIQUE 변경 — `(target_date, strategy_id, step_no, snapshot_at)` (사이클 34) → `(target_date, strategy_id, step_no)` (**migration 035 사이클 145, snapshot_at 키 폐기**) + JSONB 필드 2개

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

## 주의사항

- **Supabase SDK 는 동기 client → 모든 `.execute()` 호출이 `asyncio.to_thread()` 로 thread pool 위임** (이벤트 루프 블로킹 차단). `lambda` 또는 inner function 패턴 사용
- `_DbLogHandler` (main.py) 도 동기 `logging.Handler.emit` 이라 to_thread 불가 → `ThreadPoolExecutor(max_workers=2)` 에 fire-and-forget submit
- 매핑 등록 (`_order_qty/_order_strategy/_order_ticker`) 은 **반드시 to_thread 진입 전 동기 영역** 완료 (시장가 즉시체결 race 차단)
- status ENUM 값 변경 시 DB CHECK 제약조건도 함께 수정 (migration 추가)
