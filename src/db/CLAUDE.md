# CLAUDE.md — src/db/ (Supabase DB)

Supabase (PostgreSQL) CRUD 모듈.

> 사이클별 변경 이력: `docs/HARNESS_CHANGELOG.md`

## supabase.py — 클라이언트 초기화

- `settings.supabase_url` + `settings.supabase_key` 로 클라이언트 생성

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

- `write_log(level, message)`: 이벤트/에러 기록. level: INFO / WARNING / ERROR / CRITICAL. **사이클 65 hotfix H2 (2026-06-06)**: INSERT 페이로드에 `"timestamp": datetime.now(KST).isoformat()` 강제 — 사이클 53 KST `+09:00` 패턴 답습. DB default (`now()` UTC) 의존 폐기 — 신규 INSERT 부터 KST 보장. **호환 경로 영속** (`src/main.py::_insert_log_to_db` H2-bis): 표준 logging 의 `_DbLogHandler` 위임 경로도 동일 KST 강제 — `logger.info()` / `logger.warning()` 등 모든 호출이 KST timestamp 로 저장 (write_log 직접 호출보다 호출 빈도 높음). AST 영구 가드: `tests/unit/db/test_system_logs_kst_timestamp.py` 2 케이스 (`src/` 전체 rglob INSERT 호출처 + write_log 함수 단위) — 향후 system_logs INSERT 추가 시 KST 누락 영구 차단
- **사이클 72 hotfix (2026-06-08) — `_DbLogHandler` 500ms TTL dedupe 캐시 + 11+ 사이트 write_log 직접 호출 제거 (이중 INSERT 영구 차단)**: 사이클 71 운영 실증 발견 silent 결함 (09:00~09:25 system_logs INSERT 205건 / distinct 71 = **평균 2.89x dup**, `[swing_poll]` 23x / `[stale_watcher]` 7.33x / `[stale_watcher_detail]` 확정적 2.00x) 시정. **결함 root cause**: `_DbLogHandler` (`src/main.py:137`) 가 `record.name.startswith("src.")` 모든 logger emit → `_insert_log_to_db` 위임 INSERT + 같은 emit 사이트가 `await write_log(...)` 동시 호출 → 양쪽 경로 INSERT 누적. **옵션 A' (호출자 정정 11+ 사이트)**: `realtime/websocket.py` (`[ws_heartbeat]`) + `engine/stale_watcher_core.py` 4 사이트 (`[stale_watcher]` / `[stale_force_retry]` / `[stale_force_retry_cap]` / `[stale_priority_resubscribe]`) + `engine/stale_diagnostics.py` (`[stale_watcher_detail]`) + `engine/stale_session_recovery.py` 3 사이트 (`[silent_inactive_recovery_cap]` / `[silent_inactive_force_reconnect]` / `[scan_loop_delta]`) + `engine/stale_universe_guard.py` (`[universe_excluded]`) + `engine/scanner.py` (`[priority_drop]`) + G-6 AST 추가 검출 11 사이트 (`engine/boot_manager.py` `[cash_usage_ratio]` / `engine/scheduler.py` L735/L842/L1730/L1825/L1834/L2657 등) 의 `await write_log(...)` / `await _write_log(...)` / `asyncio.create_task(_write_log(...))` 호출 전수 제거. `logger.info/warning(...)` 단독 유지 → `_DbLogHandler` 위임 단일 INSERT 보장. **옵션 D (`_DbLogHandler` dedupe 캐시, `src/main.py:137-170`)**: `_DEDUPE_TTL_SECS = 0.5` 모듈 상수 + `_dedupe_cache: dict[str, float]` 인스턴스 변수 (message → last_emit_monotonic) + `emit()` 진입 직후 `time.monotonic()` 비교 → 동일 메시지 500ms 내 중복 emit 두 번째 INSERT skip + lazy evict (100 항목 cap, TTL 경과 항목 정리). 미래 신규 emit 사이트 silent 결함 runtime 안전망. **AST 영구 가드 3 신설**: G-6 (`tests/unit/ast/test_cycle72_ast_no_logger_write_log_pair.py`, `src/` 전체 rglob 각 `write_log` 호출 ±5 줄 동시 `logger.*` 호출 0건) + G-7 (`tests/unit/main/test_cycle72_db_log_dedupe_structure_ast.py`, `_DEDUPE_TTL_SECS = 0.5` 상수 + dedupe 캐시 dict + `time.monotonic` 비교 정적 검증) + G-8 (`tests/unit/main/test_cycle72_insert_log_kst_persistence_ast.py` 2 케이스, 사이클 65 H2-bis KST 영속 회귀 가드 보강). **회귀 가드 18 케이스 (6 파일)**: `tests/unit/engine/test_cycle72_no_duplicate_insert_per_site.py` 11 + `tests/unit/main/test_cycle72_db_log_dedupe.py` 3 (freezegun + mock supabase) + AST 4. F-1 통합 테스트 2건 (`test_boot_cash_usage_ratio.py` + `test_boot_eager_refresh.py`) obsolete `calls.write_log` assertion 옵션 C 채택 제거 (사이클 72 의도 일치, G-A 단위 가드로 회귀 가드 영속). **사이클 65 H2/H2-bis 영속 (변경 0)**: `system_logs.py:44` + `main.py:131` 인라인 KST 패턴 유지 — G-8 회귀 가드 PASS 영속. **silent 결함 영구 차단 9 회 누적** (사이클 60/64/65#1/65#2/65#3/66/67/68/72). **F-2 (HIGH 운영 영향) WebSocket dup 핵심 영역**: 운영 측정 dup 상위 4건 = `src.realtime.websocket` (ACK / 구독 / 해제 / 5xx) → 사이클 73 카드 #19 인계 (G-6 AST 가드 영역 확장 검토)
- **`safe_write_log(level, message, *, fallback_debug=None)`** (사이클 56-E, 2026-06-04): `write_log` 의 graceful skip 변형. Supabase 장애 등 예외 발생 시 전파 없이 `logger.debug` 만 발화. `fallback_debug` 명시 시 그 문자열을 debug 메시지로 사용, None 시 기본 메시지 `"[safe_write_log] {message[:80]} 실패: level={level}"`. `order_engine.py` 내 `try: await write_log / except Exception: logger.debug` 동형 패턴 4곳 통합 — `[stock_master_miss]` / `[stock_master_miss stale]` / `[market_closed_blocked]` / `[positions_reconciliation]`
- `get_logs(limit=100, log_level=None, *, from_date=None, to_date=None, page=1, size=None)`: 페이징 + KST 기간 필터. 반환 `{"items": list[dict], "total": int, "total_pages": int}`. `size` 미지정 시 `limit` 흡수 (하위 호환). `from_date`/`to_date` 명시 시 `timestamp >= "{date}T00:00:00+09:00"` / `<= "{date}T23:59:59.999999+09:00"` KST 강제. supabase-py `count="exact"` 로 total 동봉, `total_pages = ceil(total / size)`
- **`search_logs(q, *, level=None, start=None, end=None, limit=200) -> {logs, total, has_more}`** (사이클 6 통합, 2026-05-20): 키워드 substring 검색. `ilike("message", "%q%")` 대소문자 무시. `level` 이 None/`"ALL"` 이면 무필터, 그 외 `eq("log_level", level)`. `start`/`end` 는 ISO 8601 시각 직접 받아 `gte`/`lte`. `limit` 1~1000 clamp (기본 200, 최대 1000). 빈 `q` ValueError. `has_more = total > len(logs)` — 200건 초과 시 UI 가 "키워드 좁히기" 안내. 라우트 `/api/logs/search` 와 1:1
- **`purge_old_logs() -> {info_deleted, high_deleted, elapsed_ms}`** (사이클 6 통합, 2026-05-20): 등급별 retention 정책 자동 정리. INFO 등급 `timestamp < now_kst - 2 days` DELETE / WARNING/ERROR/CRITICAL 등급 `timestamp < now_kst - 30 days` DELETE. **안전 가드**: 내부 헬퍼 `_purge_by_cutoff(cutoff_iso, level_filter)` 가 `cutoff_iso=None` 이면 `RuntimeError("cutoff must not be None")` raise (WHERE 누락 사고 절대 차단). 1회 cap `MAX_PURGE_BATCH=100_000` (`limit(100000)` 적용). 잔여분은 다음 사이클 자연 흡수. INFO 1행 영구 로그 `[log_retention] info_deleted=N high_deleted=M elapsed_ms=K`. 시점: `_settle` → `_log_analysis_engine` *후* + `_reset_daily_state()` *전* (분석이 system_logs 읽은 후 정리). 예외는 scheduler 가 graceful (`[log_retention_skip]` INFO + 다음 사이클 재시도)
- 상수: `INFO_RETENTION_DAYS=2` / `HIGH_RETENTION_DAYS=30` / `HIGH_LEVELS=("WARNING","ERROR","CRITICAL")` / `MAX_PURGE_BATCH=100_000` / `SEARCH_DEFAULT_LIMIT=200` / `SEARCH_MAX_LIMIT=1000`

## log_reports.py — 일일 로그 분석 리포트

- `insert_log_report()`: 20:10 정산 직후 INSERT. `target_date` UNIQUE (충돌 시 None). **사이클 58 V-2 (2026-06-04)**: `input_tokens / output_tokens / total_tokens / latency_ms / cost_estimate_usd` 5 keyword 추가 (모두 기본 None — NULL INSERT). `cost_estimate_usd` 는 `Decimal | None` → DB 저장 시 `float` 변환.
- `list_log_reports(days=30)`: 최근 N일 신규순
- `get_log_report(target_date)`: 단일 영업일
- 스키마: id(uuid) / target_date(unique) / summary(text) / findings(jsonb 배열) / metrics(jsonb) / model(varchar) / created_at / **input_tokens(int, NULL)** / **output_tokens(int, NULL)** / **total_tokens(int, NULL)** / **latency_ms(int, NULL)** / **cost_estimate_usd(decimal(10,6), NULL)** (migration 031, 사이클 58)

## system_config.py — 시스템 설정 키-값 헬퍼

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
- **`list_accounts` 60s TTL 메모리 캐시**: 모듈 전역 `_list_cache` / `_list_cache_expires_at` + `invalidate_list_cache()` + `_LIST_CACHE_TTL=60.0`. `time.monotonic()` 비교 → TTL 내 캐시 hit (DB 호출 0). `active_only=True/False` 키 분리. DB 예외 + 캐시 있음 → stale 반환 (graceful), 캐시 없음 → 빈 리스트 (회귀 보존). INSERT/UPDATE/DELETE 직후 `invalidate_list_cache()` — 운영 토글 즉시 반영. Settings/Dashboard 30s 폴링 + 컨테이너 재시작 race + supabase HTTP/2 stale connection 결함 대응
- `insert_account(label, app_key, app_secret, kis_env)` — label UNIQUE 충돌 시 `LabelConflictError`, 빈 값/kis_env 부적합 시 `ValueError`
- `update_account(id, active=None, label=None)` — 부분 갱신. app_key/app_secret 수정 미지원 (보안 감사 추적성 — 삭제 후 재등록 패턴)
- `delete_account(id)` — 존재 시 True, 미존재 False
- `get_credentials_for_token_manager(label)` — **토큰 매니저 전용 평문 노출 함수**. `src/auth/token.py::get_token_manager(label)` lazy 초기화에서만 호출. API 응답/로그 절대 노출 금지
- 테이블: `kis_quote_accounts` (UUID PK, label UNIQUE, active=true 부분 인덱스)
- 자금 안전: 본 모듈 응답은 **시세 수신 한정**. order.py / balance.py / 체결통보 구독은 메인 계좌만

## strategy_funnel.py — 조건검색 단계별 추적 (사이클 34, 2026-05-21)

- `insert_snapshot(target_date, strategy_id, step_no, step_name, survived_count, survived_tickers, excluded_count, excluded_sample, step_conditions=None)`: 단일 단계 snapshot INSERT. `(target_date, strategy_id, step_no, snapshot_at)` UNIQUE — 같은 영업일 다회 trigger 가능. **사이클 41 (2026-05-22)**: `survived_tickers: list[str \| dict]` 호환 (string 사이클 34 형식 + dict `{ticker, name}` 사이클 41 형식), `excluded_sample: list[dict]` (`{ticker, name, reason}` 수치 포함 사유), `step_conditions` 옵셔널 (단계 조건 명시 — UI 툴팁). DB JSONB 스키마는 변경 없음 (native dict 지원)
- `list_snapshots(target_date, strategy_id)`: 특정 영업일 + 전략 의 모든 단계 (`step_no` ASC)
- `list_recent_by_strategy(strategy_id, days=7)`: 최근 N영업일 추이
- **JSONB cap**: `survived_tickers` 200건 / `excluded_sample` 20건 자동 적용 (응답·저장 크기 보호)
- 테이블: `strategy_funnel_snapshots` (UUID PK + 인덱스 2: `target_date DESC` / `(strategy_id, target_date DESC)`)
- 호출: `POST /api/strategy-funnel/snapshot` 수동 trigger + **사이클 39 자동 hook** (`scheduler._auto_capture_funnel_snapshots`, 09:30 `_scan_loop` 첫 진입 시 일일 1회 자동 발화). **사이클 39+41**: BFB/VCP/donchian `prepare()` 가 8단계 `_record_funnel_step` hook 으로 각 단계 통과/탈락 ticker + 수치 포함 사유 (`reason="음봉 비율 35% > 30%"` 등) 캡처 → 단계별 + 최종 (`step_no=99`) DB row 모두 저장. `_reset_daily_state` 동행 reset

## stock_master.py — 종목 마스터 캐시

- `upsert_one(StockBasics)` / `get(ticker) -> Optional[StockBasics]` / `is_stale(ticker, max_age_hours=24) -> bool`
- 테이블: `stock_master`. PK `ticker` (KRX 6자리), `refreshed_at` 24h TTL
- NXT 거래가능 사전 판별용 — `OrderEngine._strategy_exchange_async` + `scheduler._execute_next_day_clear` + `execute_sell` 거부 사후 보강 3경로
- 호출: 매수/매도 진입 직전 lazy. miss/stale → `inquire_stock_basics` 호출 후 upsert
- **eager 사전 갱신**: `scheduler._boot()` 마지막에 `_eager_refresh_stock_master_for_held_positions()` — 보유 + `_pending_next_day_clear` 합집합 sequential upsert (24h fresh skip). lazy 한계 (첫 사이클 캐시 miss → SOR/NXT 발사 → KIS 거부) 차단
- **ticker 정규화**: PK 형식 KRX 6자리. `inquire_stock_basics` 가 `_normalize_ticker()` 로 KIS `pdno` 12자리 표준코드 → 마지막 6자리 추출. `upsert_one` 이중 안전망 — 6자리 미준수 입력도 정규화 후 저장 (WARNING)
- **사이클 108 (2026-06-11) — `list_by_filter()` 신규 메서드 영구 영속 (Plan Phase A 완료, VB/LTV/BFB stock_master 베이스 전환 + KIS volume-rank API 100% 폐기)**: 사이클 104 인계 Q5=B (LOW 위험 자문 생략 영구 영속) + 사이클 107 raw 보강 의존성 해소 영구 영속 완료 → Plan Phase A 데이터 영역 영구 영속 활용 가능 → 사이클 108 = `list_by_filter()` 신규 메서드 + VB/LTV/BFB `_scan_universe()` 전환 통합. 사용자 결정 Q1=A 시총 영역 = `hts_avls` (KIS FHKST01010100, 백만원 단위 영구 영속) + Q2=A 통합 단일 사이클 (3 전략 동시 전환) + Q3=C 4 필터. **`list_by_filter(min_market_cap=0, min_trade_amount=0, exclude_tickers=None, nxt_tradable=None, market=None, limit=500, *, exclude_etf=True)` 시그너처 영구 영속**: (1) **Supabase 영역 조회 영구 영속** (테이블 = `stock_master`, 2배 buffer `limit × 2` 영역 영구 영속 — 필터 후 결과 < limit 영역 회피 영역 영구 영속). (2) **Python-side JSONB 필터링 영역 영구 영속**: `raw.hts_avls × 1_000_000` 백만원 단위 환산 영역 영구 영속 ≥ `min_market_cap` + `raw.acml_tr_pbmn` 거래대금 영역 영속 ≥ `min_trade_amount` + ticker `not in exclude_tickers` 영역 + `nxt_tradable` 영역 영속 (None 시 무필터, 사이클 32 R4 답습) + ETF 키워드 제외 영역 영구 영속 (`exclude_etf=True` 시 사이클 89 답습 + 6자리 ticker 영속). (3) **graceful 영역 영구 영속** (raw miss / hts_avls miss / acml_tr_pbmn miss 영역 = 통과 영구 영속, 사이클 65 Q6-1 09:00 race graceful 답습 영구 영속). (4) **filter 후 limit 적용 영구 영속** (final result ≤ limit 영역 영구 영속). **사이클 107 raw 보강 의존성 영구 영속**: `inquire_stock_basics` 영역에서 `hts_avls` (사이클 108 신규) + `acml_tr_pbmn` (사이클 107) 키 자동 포함 영구 영속 = 사이클 108 `list_by_filter` 필터링 영역 영구 영속 데이터 영역 영구 영속 확보. **호출 영역 영구 영속**: VB/LTV/BFB 3 전략 `_scan_universe()` 영역 영구 영속 (`src/engine/strategies/{volatility_breakout, long_tail_volatility, bull_flag_breakout}.py` 영역). **운영 효과 영구 영속**: KIS `volume-rank` API (FHPST01710000) 호출 100% 폐기 영구 영속 (VB 3 + LTV 3 + BFB 3 = 9 호출/일 → 0 호출 영구 영속, 사이클 17 OPSP0002 backoff + KIS LMS chain 안전 영역 영구 영속 효과). **회귀 가드 영역**: `tests/unit/db/test_cycle108_list_by_filter.py` 영역 (Supabase 영역 조회 + Python-side JSONB 필터링 + 2배 buffer + graceful 영역 + filter 후 limit 적용 영역). **영속 의무 매트릭스**: 사이클 32 R4 universe guard 영속 (nxt_tradable 영역 답습) + 사이클 89 답습 (KOSPI/KOSDAQ + ETF 제외 + 6자리 ticker 영속) + 사이클 107 영속 (raw 보강 의존성 영속) + 사이클 81 G-AST1 영속 (`bfdy_clpr` + `hts_avls` 덮어쓰기 금지 영속). **매매 안전성 무영향 확정 영구 영속** (종목 마스터 캐시 조회 영역 한정 영구 영속 + scanner 단계 후보 풀 구성 영역 한정 영구 영속 + 매수 진입 전 영역 한정 영구 영속 + 매도/익일청산 hot path 무관 영구 영속 + 사이클 38 명문화 영속). Plan Phase C UI 운영자 필터링 호환 영역 영구 영속 (`exclude_tickers` 인자 활용 영구 영속 + Settings UI 영역 영구 영속 가능).
- **사이클 107 (2026-06-11) — raw JSONB 3 키 추가 영구 영속 (CTPF1002R + FHKST01010100 merge, Plan Phase A 데이터 영역 의존성 해소)**: `stock_master.raw` JSONB 영역에 사이클 107 시정 이후 자동 포함되는 3 키 영구 영속 명세 — `acml_tr_pbmn` (누적 거래 대금) + `lstn_stcn` (상장 주수) + `acml_vol` (누적 거래량, `prdy_vol` 영속 동등). 영역 영구 영속 = `src/api/condition.py::inquire_stock_basics` 본체 보강 (+44L 순증, 사이클 107 시정) → CTPF1002R 호출 *후* FHKST01010100 (`inquire_price` 주식현재가 시세) 추가 호출 → 응답 merge → raw JSONB 통합. CTPF1002R 응답 67 컬럼 영역 = 3 키 모두 부재 영구 영속 (KIS MCP 정본 영구 영속 확정) → FHKST01010100 호출 영역 영구 영속에서만 입수 가능. **CTPF1002R 기존 키 덮어쓰기 금지 설계 영구 영속** = `bfdy_clpr` 영역 영구 영속 정합 (사이클 81 G-AST1 영구 영속). **호출 시점 영역**: 매수/매도 진입 직전 lazy `upsert_one` 경로 영속 + 사이클 101 `_full_universe_load_once` (사이클 106 lifecycle 영속) 배치 호출 영역. **운영 효과 영구 영속 (사이클 107 시정 push 후)**: stock_master 2,800 종목 × 2 KIS 호출 + 50ms sleep = 약 5분 소요 영역 영구 영속 / 향후 Plan Phase A (사이클 108+) `list_by_filter(min_market_cap=, min_trade_amount=)` 데이터 영역 영구 영속 의존성 해소 영역 영구 영속. **graceful fallback 영역 영구 영속**: FHKST01010100 RuntimeError / KisApiError 영역 = CTPF1002R 단독 raw 반환 (호출자 보호 영구 영속 = stock_master 저장 영역 영구 영속 graceful). **회귀 가드 영역**: `tests/unit/api/test_cycle107_inquire_stock_basics_merge.py` 12 케이스 (HIGH 4 = 양쪽 API 호출 + raw 3 키 포함 + graceful fallback + AST 영구 가드). **영속 의무 매트릭스**: 사이클 81 G-AST1 (`bfdy_clpr` 덮어쓰기 금지 영구 영속) + 사이클 98 G-DOC1 (KIS 정본 `chk_inquire_price.py` 인용 의무 영구 영속) + 사이클 101 영속 (`_full_universe_load_once` 호출 영역 자동 반영 영구 영속) + 사이클 106 영속 (`_full_universe_load_task_loop` 영역 변경 0 = lifecycle race 차단 영구 영속). **매매 안전성 무영향 확정 영구 영속** (종목 마스터 캐시 영역 한정 + 매매 hot path 무관 + Rate Limit 50ms sleep KIS LMS chain 안전)

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
- Supabase 동기 SDK 호출은 `asyncio.to_thread()` 위임 (사이클 53 정책 답습)
- 영속 의무: KST timestamp `_kst.now_kst_iso()` 사용 (사이클 68 G-10b AST) + raw JSONB 덮어쓰기 금지 (사이클 81 G-AST1 답습)

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
- `strategy_funnel_snapshots` (migration 030, 사이클 34): `(target_date, strategy_id, step_no, snapshot_at)` UNIQUE + JSONB 필드 2개

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
