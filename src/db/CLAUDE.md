# CLAUDE.md — src/db/ (Supabase DB)

Supabase (PostgreSQL) CRUD 모듈.

> 사이클별 변경 이력: `docs/HARNESS_CHANGELOG.md`

## supabase.py — 클라이언트 초기화

- `settings.supabase_url` + `settings.supabase_key` 로 클라이언트 생성

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

- `write_log(level, message)`: 이벤트/에러 기록. level: INFO / WARNING / ERROR / CRITICAL
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
- **사이클 62 가격 필터 (2026-06-05)** — 매수 진입 전용 가격대 차단 (사이클 38 명문화 답습):
  - `get_price_filter() -> PriceFilter` (Pydantic) / `set_price_filter(*, min_price=None, max_price=None, mode=None)` 부분 갱신
  - 3 키: `price_filter_min` (int, default 0 = 비활성) / `price_filter_max` (int, default 0 = 비활성) / `price_filter_mode` (str, default `OFF`, 3 모드 HARD/WARN/OFF)
  - **3 모드 의미** (domain-expert Q4 자문 옵션 A): HARD = 매수 차단 + INFO 로그 / WARN = 매수 진행 + WARNING 로그 (운영자 임계 조정 기간 1주 권고) / OFF = 분기 미진입
  - 범위 외 ValueError (음수 / `min_price > max_price` 단 둘 다 >0 일 때 / 잘못된 mode 문자열)
  - **.env fallback 없음** — 운영 가변 (DB 미설정 → 코드 디폴트 OFF). `RiskManager._get_price_filter_cached()` 60s TTL 캐시 (사이클 56-E `buy_block` 패턴 답습)
  - **매수 진입 전용** — 매도/익일청산/손절/15:20 강제청산 영향 0 (사이클 38 명문화 답습 + Q3 추가 가드: `order_engine.py` 시장가 거부 5호가 폴백 시 필터 재평가 금지, E-4 AST 정적 회귀 가드)
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

## 주의사항

- **Supabase SDK 는 동기 client → 모든 `.execute()` 호출이 `asyncio.to_thread()` 로 thread pool 위임** (이벤트 루프 블로킹 차단). `lambda` 또는 inner function 패턴 사용
- `_DbLogHandler` (main.py) 도 동기 `logging.Handler.emit` 이라 to_thread 불가 → `ThreadPoolExecutor(max_workers=2)` 에 fire-and-forget submit
- 매핑 등록 (`_order_qty/_order_strategy/_order_ticker`) 은 **반드시 to_thread 진입 전 동기 영역** 완료 (시장가 즉시체결 race 차단)
- status ENUM 값 변경 시 DB CHECK 제약조건도 함께 수정 (migration 추가)
