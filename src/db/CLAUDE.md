# CLAUDE.md — src/db/ (AWS RDS PostgreSQL + asyncpg)

> 이력: [`docs/history/src-db-CLAUDE.history.md`](../../docs/history/src-db-CLAUDE.history.md) · 사이클별: `docs/HARNESS_CHANGELOG.md`

AWS RDS PostgreSQL CRUD 모듈. DB 클라이언트 정본 = **`pg.py` (asyncpg 네이티브 async)**.
모든 CRUD 는 `pg.fetch`/`fetchrow`/`fetchval`/`execute`/`executemany` 를 경유한다.
`supabase.py` 는 롤백용으로만 남아 있다(아래 「supabase.py — 롤백용 병존 파일」 절).

## pg.py — asyncpg 연결 풀 + 쿼리 헬퍼 (DB 클라이언트 정본)

- `init_pool()` 이 `settings.database_url`(asyncpg DSN, `?sslmode=require`)로 전역 풀을 만든다(`min_size=2` / `max_size=10` / `max_inactive_connection_lifetime=300` / `command_timeout=30`). `main.py` lifespan 이 시작에 `init_pool()`, 종료에 `close_pool()`.
- **`_init_conn(conn)`** — 새 물리 연결마다 JSONB/JSON codec(`set_type_codec(encoder=json.dumps, decoder=json.loads)`)을 등록한다. **⚠️ 빠지면 `isinstance(raw, dict)` 를 기대하는 코드(`system_config.get_cash_usage_ratio` 등)가 조용히 폴백해 매매 파라미터가 기본값으로 돈다.**
- **KST 타임존은 `init_pool()` 의 `server_settings={"timezone": "Asia/Seoul"}`(핸드셰이크 파라미터)로 지정한다.** `init=` 훅의 `SET TIME ZONE` 은 쓰지 않는다 — 풀이 release 때 RESET 해 UTC 로 돌아가 KST 날짜가 하루 밀린다.
- 헬퍼: `fetch(sql, *args) -> list[dict]` / `fetchrow(sql, *args) -> dict | None` / `fetchval(sql, *args)`(스칼라) / `execute(sql, *args) -> str` / `executemany(sql, args_list)`. SQL 은 `$1`/`$2` 위치 파라미터.
- **`_with_retry(coro_factory, *, op="")`** — 연결 계열 예외 1회 재시도. `_RETRY_EXCEPTIONS = (asyncpg.PostgresConnectionError, asyncpg.InterfaceError, asyncpg.exceptions.ConnectionDoesNotExistError, asyncio.TimeoutError)`, 간격 `_RETRY_BACKOFF_SECS = 0.2`, 소진하면 마지막 예외를 raise(호출자 graceful 분기 보존). 로그는 `logger.warning("[pg_retry] op=…")` 단독(`write_log` 를 더하면 이중 INSERT). **read 전용**(`fetch`/`fetchrow`/`fetchval`) — 멱등이 아닌 `execute`/`executemany` 는 경유하지 않는다.
- ⚠️ **테스트에서 `freeze_time` 안으로 DB read 를 태우지 않는다** — retry 의 `asyncio.sleep(0.2)` 이 동결된 `time.monotonic` 과 만나 hang 한다. read 를 mock 하거나 freeze 밖에서 읽는다.

## asyncpg 계약 패턴

전 db 모듈의 바인딩·렌더 계약(신규 CRUD 의무):

- **JSONB** — codec 이 왕복한다. **raw dict/list 를 그대로 바인딩**(호출부 `json.dumps` = 이중 인코딩).
- **TIMESTAMPTZ** — 쓰기 = `datetime.fromisoformat(now_kst_iso())`. ISO 문자열 조회는 SQL `to_char(t.<컬럼>, 'YYYY-MM-DD"T"HH24:MI:SS.US+09:00')`(아래 「TIMESTAMPTZ 계약」 절).
- **DATE** — `src/db/_kst.py::to_date(x)` 로 변환해 바인딩. str 이면 asyncpg 가 `'str' object has no attribute 'toordinal'` 로 즉시 실패한다.
- **NUMERIC** — `Decimal` 반환(손익 정밀도 보존 — `get_trade_pairs` 등).
- **목록 필터** = `WHERE col = ANY($1::text[])` · **건수** = 데이터 쿼리와 분리된 `SELECT count(*)` fetchval.

## _kst.py — KST 공용 헬퍼

- `KST = timezone(timedelta(hours=9))` — KST tzinfo 단일 진입점
- `now_kst_iso() -> str` = `datetime.now(KST).isoformat()` — DB payload 시각 컬럼(`created_at` / `updated_at` / `refreshed_at` / `completed_at` / `timestamp` 등) 의무
- `today_kst() -> date` = `datetime.now(KST).date()` — `date.today()` 대신
- **`to_date(x: date|datetime|str|None) -> date|None`** — never-raise. `date`/`datetime`→`.date()`, `str`→`date.fromisoformat`(실패하면 앞 10자로 재시도), `None`→`None`, 파싱 실패→`None` + `logger.warning`. **바인딩 지점을 감싸는 것은 호출자 책임이다.**
- 🔴 **DB 시각 컬럼에 `datetime.utcnow()` · `date.today()` · `src/db/` payload 의 `datetime.now(timezone.utc)` 를 쓰지 않는다** — AST 가드 `tests/unit/db/test_cycle68_*.py`. aware `datetime.now(KST)` 직접 바인딩(`trade_history.insert_trade` · `main.py::_insert_log_to_db` 등)은 허용.

## trade_history.py — 거래 내역

- `insert_trade(record)`: 주문 시 INSERT (status: PENDING)
- **`update_trade_status(ticker, trade_type, status, strategy="momentum", price=None, profit_loss=None, *, order_no=None, match_partial=False) -> int`**: 진행 중 행의 status 변경, 영향 행 수 반환. COMPLETED 0건이면 호출자(OrderEngine)가 체결통보 선행 race 로 보고 보정 INSERT 한다. **PARTIAL·CANCELLED 에는 흡수 경로가 없다** — `OrderEngine` 4 호출부(매수·매도 × PARTIAL·CANCELLED)가 0건이면 `[trade_status_update_miss] status= order_no= ticker= side=` WARNING(cycle358, 관측 전용, 1회/(order_no, status)/일 `KstDailyEmitCap`, 로그 실패 흡수). SELL 행의 `price`·`profit_loss` 값의 뜻(주문 단위 누적·체결 가중평균) = `src/engine/CLAUDE.md` 「체결단가 정합」 절(cycle392).
  - `match_partial=True`(opt-in) = `status = ANY(...)` 로 PENDING ∪ PARTIAL. **기본을 넓히지 않는다** — `_cancel_after_wait`/`_cancel_and_reorder` 의 CANCELLED 까지 넓어져 부분 체결 사실이 정산·sync 에서 사라진다. 넘기는 호출부는 COMPLETED 2곳뿐(AST 봉인).
  - 같은 인자가 `AND timestamp >= (KST 오늘 00:00)` 하한도 켠다. 하한은 **`datetime` 바인딩**(str 이면 실 PG `DataError` 로 체결 경로 전건 예외 — AST5).
  - `order_no`(keyword-only, 기본 `None`, 빈 문자열도 필터) → `AND order_no = $n`. **order_engine 호출 6곳은 전부 넘긴다** — 빠지면 같은 `(ticker, trade_type, strategy)` 의 다른 `order_no` 행까지 덮는다(필옵틱스 161580 사건).
  - `affected > 1` 이면 `[trade_status_multi_update]` WARNING — `order_no` 를 넘기면 부분 UNIQUE 인덱스 때문에 안 나므로 WHERE·인덱스 후퇴 감시자다.
- `_update_trade_status_by_order_no(order_no, trade_type, status, price=None, profit_loss=None) -> int`: `order_no` 단일 키 UPDATE(전략 필터 없음). 보정 INSERT 가 UNIQUE 위반일 때의 폴백.
- **`get_trades_in_range(start_date, end_date, strategy=None)`**: KST inclusive. 경계 `f"{date}T00:00:00+09:00"` / `f"{date}T23:59:59.999999+09:00"` — **`+09:00` 필수**. `recommendation_engine`·`log_analysis_engine` 공유.
- `get_trades(limit=50, offset=0, ticker=None, strategy=None) -> (list[dict], int)`: 페이징 + 전체 건수
- `get_trade_pairs(strategy=None, ticker=None)`: `(ticker, strategy)` 를 timestamp ASC 로 훑어 누적 수량이 0 이 될 때마다 closed 페어(가중평균가, Decimal), 잔여는 open 페어(미실현 손익 = `scanner.ticker_prices`, 미수신이면 None). 응답 키 = buy_date / buy_time / sell_date / sell_time / ticker / ticker_name / buy_price / buy_qty / sell_price / sell_qty / profit_loss / profit_rate / status('closed'|'open') / strategy **+ `buy_order_nos: list[str]` / `sell_order_nos: list[str]` / `pair_key: str|None`**.
  - `pair_key` = `strategy:ticker:첫 매수 order_no`(페어의 유일한 안정 식별자). 빈 `order_no` 체결은 주문번호 목록에서만 빠진다. 시각은 `_to_kst()` 가 ISO(UTC/KST/tz-naive)를 `astimezone(KST).strftime()` 으로 변환.
- `get_today_buy_trades / get_today_sell_trades`: 당일(`f"{today}T00:00:00+09:00"`), **ticker 별 dedupe(최신 1건) — 포지션 복구·손익 매핑용.**
- `get_today_trades_for_settlement(strategy=None)`: 정산용, 당일 COMPLETED·PARTIAL 전부 · `get_today_buy_trades_for_funnel()`: funnel 대조용, 당일 BUY 전 상태. 둘 다 dedupe 없음.
- **`get_today_buy_trades_for_sync(ticker=None) / get_today_sell_trades_for_sync(ticker=None)`**: **dedupe 없음** + CANCELLED 제외 + optional ticker — `_sync_orders_to_db` 중복 판정 전용. 🔴 **포지션 복구용 dedupe 함수를 sync 중복 판정에 쓰지 않는다** — 다른 `order_no` 가 가려져 재기동마다 신규로 판정된다(5/20 042700 핑퐁 INSERT 사고).
- `mark_pending_buys_completed(ticker)` / `get_recent_buy_strategy(ticker) -> str|None` / `get_today_buys_ticker_strategy() -> list[dict]`: `boot_manager` 전용.
- **부분 UNIQUE 인덱스** (migration 029): `uq_trade_history_ticker_order_no_type ON (ticker, order_no, trade_type) WHERE order_no IS NOT NULL AND order_no != ''` — 코드가 회귀하면 PG 가 INSERT 를 거부한다. NULL/빈 `order_no`(수동 매매 등)는 인덱스 밖.

## llm_buy_evaluations.py — AI 매수평가 기록

- 테이블 `llm_buy_evaluations` (migration 043, 53열). **PK `(trade_date, account_no, ticker, order_no)`** — KIS ODNO 는 **하루 단위로만** 유일해 날짜가 선두이고, `trade_history` 조인도 `(trade_date, ticker, order_no)` **3축**이어야 한다. 실현손익은 `get_trade_pairs` 의 `buy_order_nos` 로 잇는다. 인덱스 4 = `(trade_date)` · `(strategy_id, trade_date)` · `(ticker, trade_date)` · `(order_no)`.
- 열 묶음 = 판정(`score`·`min_score`·`would_block`·`rationale`·`key_risks`·`invalidations`) · 모델·토큰·비용·지연 · 주문 스냅샷(주문가·수량·구분·경로·거래소·보드) · 신호 · 회고 층화(아래). `eval_kind`(`'order'`|`'blocked'`, 기본 `'order'`) — `'blocked'` 는 미구현 enforce 의 주문 없는 차단 평가(`order_no=''`)를 받을 예약 값이다. 지금 쓰는 값은 `'order'` 뿐이다(`src/engine/llm_buy_gate.py`). 이 열이 그 행을 빈 `order_no` 수기 체결 행과 가른다.
- `upsert_evaluation(**kw) -> dict|None`: **주문 1건 = 1행**(성공·실패 모두). 같은 PK 재기록은 UPDATE, `created_at` 보존. 실패 행도 `input_payload` 를 담고 `score`/`would_block` 은 **NULL**(0 위장 금지 — 점수 분포가 왜곡된다). 호출자 = leaf `engine/llm_buy_gate._persist_evaluation` 하나.
- `get_by_order(order_no, *, trade_date=None)`: 날짜가 없으면 **가장 최근 1행**.
- `list_by_order_nos([...], *, trade_date=None)`: 존재하는 **`(trade_date, order_no)` 쌍 전부**를 `trade_date DESC` 로(빈 목록 = **쿼리 없이** `[]`). 🔴 **주문번호당 1행으로 접지 않는다** — 옛 날짜 평가가 목록에서만 사라진다. 대조는 라우트가 `"<trade_date>|<order_no>"` 복합 키로.
- **타입 강제는 이 모듈이 한다**: DATE = `_kst.to_date()`, TIMESTAMPTZ = `_to_dt()`(ISO **문자열도 변환**, 미지 타입 `TypeError`), JSONB 4열(`key_risks`/`invalidations`/`input_payload`/`raw_response`) = **raw dict/list**(`json.dumps` 금지), NUMERIC = `Decimal`(라우트가 `float` 로 사영). 실 PG 왕복 가드 = `tests/integration/test_cycle276_llm_eval_pg_roundtrip.py`(mock 은 str 바인딩을 통과시킨다).
- **`signal_time_local`** 은 KST 를 보장하지 않는다 — 원천이 6전략 `datetime.now()`(tz 없음)·kojiro `datetime.now(KST)` 라 컨테이너 `TZ=Asia/Seoul` 전제에서만 KST 다.
- **이 모듈은 예외를 전파한다** — 기록 실패는 leaf 의 `[llm_eval_persist] result=error`, 조회 실패는 라우트 500 이 드러낸다. `except Exception: return None` 을 넣으면 두 채널이 함께 막힌다.
- 회고 층화 열 = `prompt_version`/`feature_version`(전후 행을 **섞어서 회귀 금지**) · `budget_total_won`/`budget_remaining_after_won`/`open_positions_n` · `raw_response`(파싱 전 원문) · `input_payload`(`build_messages` 3인자 전체 — 요약·절단 금지, 오프라인 재채점의 유일한 다리). 분석은 `trade_history.status` 로 **체결/부분체결/미체결/취소 4분류를 반드시 분리**한다(미체결을 손익 0 으로 섞지 않는다).

## positions.py — 보유 포지션 영속화

`positions` 테이블이 메모리 `scheduler.positions` 의 복구 원천이다 — 재시작이 보유를 잃으면 손절이 통째로 사라진다.

| 함수 | 계약 |
|---|---|
| `save_position(ticker, ticker_name, buy_price, quantity, order_no, strategy_id, buy_date, high_since_buy=0)` | `ON CONFLICT (ticker) DO UPDATE` upsert, **ticker PK** = 한 종목 한 포지션. 갱신 때 **빈 종목명은 저장된 이름을 덮지 않는다**(`ticker_name = COALESCE(NULLIF(EXCLUDED.ticker_name, ''), positions.ticker_name)`) — 호출자(매수 체결 · #1.5 재대조 · 분할 매도 뒤 잔여 저장)는 이름 캐시가 비면 빈 이름을 넘긴다. 새 행은 넘긴 값 그대로. `high_since_buy` 가 0·미지정이면 `buy_price`(0 이면 첫 틱에 트레일링이 즉시 발동한다) |
| `delete_position(ticker)` | 청산 완료 시 1행 삭제 |
| `load_all() -> list[dict]` | 부팅 복구용 전량 조회 |
| `update_high(ticker, high)` | 트레일링 고점 갱신 |
| `clear_all()` | 전량 삭제 — **운영 복구용**이지 일상 경로가 아니다 |

`buy_date` 는 DATE 라 `_kst.to_date()` 계약을 따른다(익일 청산 판정 기준일).

## strategy_config.py — 전략 설정 (`strategy_id` PK, `params` JSONB)

🔴 **비중 단위는 비율 `0.0~1.0`** — 값 크기로 단위를 추측하는 분기를 어느 계층에도 두지 않는다(루트 `CLAUDE.md` 「비중 단위 추론 변환 금지」). 로그의 `weight * 100` 은 표시 전용.

| 함수 | 계약 |
|---|---|
| `load_all() -> dict[str, dict]` | `{strategy_id: {"enabled", "weight", "params"}}`. `params` 가 dict 가 아니면 `{}`(JSONB 오염이 부팅을 죽이지 않게) |
| `save(strategy_id, enabled, weight, params)` | `ON CONFLICT (strategy_id) DO UPDATE` upsert. `updated_at` = `datetime.fromisoformat(now_kst_iso())` — **str 바인딩 불가** |
| `save_weights(weights)` | 비중만 갱신. **기존 `params` 를 먼저 읽어** 다시 넣는다(안 그러면 지워진다). `enabled = weight > 0` 을 함께 정한다 |
| `save_params(strategy_id, params)` | `params` JSONB 만 갱신 |

⚠️ **이 테이블에 쓴 값은 다음 백엔드 재시작에서만 반영된다**(`_load_strategy_config` 의 `_config_loaded` 가 프로세스당 1회, `_boot` 재호출은 no-op). 장중 즉시 반영은 `PUT /api/strategies/{id}/params`(in-memory `config.params` 를 덮는다)이고, cycle232 D6(보유 중 장중 재시작 금지) 때문에 **장중 실효 수단은 PUT 뿐**이다.

## daily_performance.py — 일일 실적

- **`upsert_daily_performance(target_date, total_asset, daily_profit_rate, strategy="total", *, net_external_cashflow=0.0, daily_realized_pnl=0.0, deposit=0.0, cumulative_return_rate=0.0)`**: **21:30 정산**(`scheduler.TIME_SETTLEMENT`) 기록, `target_date` 는 `to_date()`. `daily_realized_pnl`/`daily_profit_rate` 는 **실현손익(SELL) 기준** — 매도 0건이면 둘 다 0 이 정상(평가손익은 `BalanceTable.eval_profit_loss`). 컬럼 = total_asset / daily_profit_rate / daily_realized_pnl / net_external_cashflow / deposit / cumulative_return_rate(TWR 복리, 실현손익 누적).
- `get_performance(days=30, strategy="total")`: 최근 N일(오름차순) · `get_latest_performance(strategy="total")`: 최근 영업일 1행(TWR 누적·Δ예수금 baseline)
- `recompute_from_trades()`: PG 함수 `recompute_daily_performance()` — `trade_history` 기반 일괄 재계산(멱등), `_settle()` 끝에서 자동 호출. `daily_profit_rate` 분모 = **가장 가까운 0이 아닌 이전 영업일 `total_asset`**(correlated subquery).

## system_logs.py — 시스템 로그

- **`write_log(level, message)`**: INFO / WARNING / ERROR / CRITICAL. **never-raise** — 실패는 `logger.debug("[write_log_failed] …")` 단독. 🔴 **실패 로그를 WARNING 이상으로 올리지 않는다** — `_DbLogHandler` 가 다시 DB INSERT 로 태워 재귀한다. AST 가드 `tests/unit/ast/test_cycle190_ast_write_log_guard.py`(broad except + except 안 raise 0 + debug 단독).
- INSERT `timestamp` 는 KST aware datetime 강제(DB default `now()` 불신) — `write_log` = `datetime.fromisoformat(now_kst_iso())`, 표준 logging 경로 `src/main.py::_insert_log_to_db` = `datetime.now(KST)`. AST 가드 `tests/unit/db/test_system_logs_kst_timestamp.py` 2 케이스(`src/` 전체 rglob INSERT 호출처 + `write_log` 함수 단위).
- `_DbLogHandler`(main.py) = 동기 `logging.Handler.emit` → **큐 producer + async consumer**(`_log_queue_consumer`). 동일 메시지 500ms dedupe(`_DEDUPE_TTL_SECS = 0.5` + `_dedupe_cache: dict[str, float]`, `time.monotonic`, lazy evict 100 항목 cap) · KST 강제 · never-raise.
- 🔴 **같은 사이트에서 `logger.*` 와 `write_log` 를 함께 부르지 않는다** — `_DbLogHandler` 가 `record.name.startswith("src.")` emit 을 이미 `system_logs` 에 적어 이중 INSERT 다. AST 가드 `tests/unit/ast/test_cycle72_ast_no_logger_write_log_pair.py`(`write_log` ±5줄 `logger.*` 0건).
- **`safe_write_log(level, message, *, fallback_debug=None)`**: 예외 대신 `logger.debug` 만 남기는 변형(`fallback_debug` 없으면 `"[safe_write_log] {message[:80]} 실패: level={level}"`). 사용처 = `order_engine.py`(`[stock_master_miss]` reason=miss·stale · `[market_closed_blocked]` · `[positions_reconciliation]`) + `sell_rejection.py` 알람.
- `get_logs(limit=100, log_level=None, *, from_date=None, to_date=None, page=1, size=None)` → `{"items": list[dict], "total": int, "total_pages": int}`(`size` 미지정 = `limit`). 기간 경계 `"{date}T00:00:00+09:00"` / `"{date}T23:59:59.999999+09:00"`, `total` = 별도 `SELECT count(*)`, `total_pages = ceil(total / size)`.
- **`search_logs(q, *, level=None, start=None, end=None, limit=200) -> {logs, total, has_more}`**: `message ILIKE '%q%'`, `limit` 1~1000 clamp, 빈 `q` = `ValueError`, `start`/`end` = 포함 경계(`>=`/`<=`), `has_more = total > len(logs)`. 라우트 `/api/logs/search` 와 1:1(파라미터 뜻 = `src/routes/CLAUDE.md` 그 행).
- **`purge_old_logs() -> {info_deleted, high_deleted, elapsed_ms}`**: INFO 는 `INFO_RETENTION_DAYS`, `HIGH_LEVELS` 는 `HIGH_RETENTION_DAYS` 지난 행을 지운다.
  - `_purge_by_cutoff(*, cutoff_iso, level_filter)` 는 `cutoff_iso=None` 이면 `RuntimeError("cutoff must not be None …")` — **WHERE 누락 삭제 절대 차단**.
  - `PURGE_SELECT_BATCH` 씩 drained 까지 **루프**. 안전 cap 3중 = `PURGE_MAX_ITERATIONS` · `MAX_PURGE_BATCH` 누적 상한 · 마지막 페이지 조기 종료.
  - 시점 = `_settle` 의 로그 분석 **뒤**, `_reset_daily_state()` **앞**. 예외는 scheduler 가 `[log_retention_skip]` INFO 로 흡수하고 다음 사이클에 재시도. 결과 = `[log_retention] info_deleted=N high_deleted=M elapsed_ms=K`.
- 상수: `INFO_RETENTION_DAYS=2` / `HIGH_RETENTION_DAYS=30` / `HIGH_LEVELS=("WARNING","ERROR","CRITICAL")` / `MAX_PURGE_BATCH=100_000` / `PURGE_SELECT_BATCH=1000` / `PURGE_MAX_ITERATIONS=2000` / `SEARCH_DEFAULT_LIMIT=200` / `SEARCH_MAX_LIMIT=1000`

## log_reports.py — 일일 로그 분석 리포트

- `insert_log_report()`: `INSERT … ON CONFLICT (target_date) DO UPDATE SET` upsert(cycle283 D6). 🔴 **SET 절은 base 9컬럼만**(summary / findings / metrics / model + 토큰 5) — `ext_*` 6컬럼과 `created_at` 은 **절대 넣지 않는다**(새면 20:20 클라우드 루틴 결과가 조용히 지워진다). `upsert_external_report` 의 SET 절과 **교집합이 공집합**이라 쓰는 순서와 무관하게 서로를 보존한다.
  - 쓰는 주체 = 20:05 1차 스냅샷(`daily_metrics_snapshot`, model·토큰 NULL) · 21:30 완전판(`generate_daily_log_report`).
  - `on_conflict` = `"update"`(기본) | `"nothing"`(기존 행이 있으면 `None`), 그 밖은 `ValueError`. `"nothing"` 은 **프로덕션 호출자 0건**(오용 방어용).
  - `POST /api/log-reports/run` 의 비파괴는 **라우트 선조회 가드** `_is_complete_report`(4축 = `src/routes/CLAUDE.md` 해당 행)가 혼자 맡는다. 라우트는 `"nothing"` 을 쓰지 않는다 — 20:05~21:30 에는 1차 스냅샷 행이 있어 `"nothing"` 이면 수동 복구의 완전판이 버려진다.
  - 키워드 인자 = `target_date` / `summary` / `findings` / `metrics` / `model` + `input_tokens` / `output_tokens` / `total_tokens` / `latency_ms` / `cost_estimate_usd`(기본 `None` = NULL, `cost_estimate_usd` 는 `Decimal | None` → 저장 직전 `float`).
- **`upsert_external_report(*, target_date, provider, model, summary, findings, report_md) -> dict`**: 20:20 KST 클라우드 루틴 결과 저장. `DO UPDATE SET` 은 **`ext_provider`/`ext_model`/`ext_summary`/`ext_findings`/`ext_report_md`/`ext_created_at` 6개뿐**, base 컬럼은 **절대 넣지 않는다**. 행이 없는 날의 INSERT 는 base 컬럼을 SQL 리터럴(`''`/`'[]'::jsonb`/`'{}'::jsonb`/`NULL`)로 채운다(호출자 데이터가 심길 여지 없음). JSONB raw list + `::jsonb` 캐스트, DATE `to_date()`, TIMESTAMPTZ `datetime.fromisoformat(now_kst_iso())`.
- `list_log_reports(days=30)`: 최근 N일 신규순 · `get_log_report(target_date)`: 단일 영업일(둘 다 `SELECT *` — `ext_*` 포함)
- 테이블 `daily_log_reports`: id(uuid) / target_date(unique) / summary(text) / findings(jsonb 배열) / metrics(jsonb — `api_metrics`·`strategy_funnel`·`by_ticker_pnl`·`by_hour_pnl`·`next_day_clear` 등) / model(varchar) / created_at + 토큰 5(migration 031, NULL 허용 — 4개 int, cost_estimate_usd decimal(10,6)) + `ext_*` 6(migration 042, NULL 허용 — ext_findings jsonb, ext_created_at timestamptz, 나머지 text)

## system_config.py — 시스템 설정 키-값 헬퍼

- 저장 = `system_config(key, value JSONB)`. 내부 헬퍼 `_select_value(key)`(`pg.fetch` 직행, 0건 = `_MISSING` sentinel) / `_upsert_value(key, value)`(`ON CONFLICT (key) DO UPDATE`, `updated_at` = `datetime.fromisoformat(now_kst_iso())`). read 는 `_with_retry` 내장, 쓰기(`pg.execute`)는 미경유. 범위 밖 입력 = `ValueError`.

**시세 채널 전환 다이얼** (전부 `system_config` 축 — 전략 `DEFAULT_PARAMS`·`param_catalog` **편입 금지**):

- **`get_tick_channel_resolver_mode() -> str | None` / `set_tick_channel_resolver_mode(mode)`** — 키 `tick_channel_resolver_mode`, 시세 채널 리졸버 킬스위치의 **DB 정본**(`off`/`observe`/`enforce_low`/`enforce`), `_get_string_or_none` 경유.
- **전환 다이얼 4키** — `get_tick_channel_switch_enabled()` / `set_tick_channel_switch_enabled(enabled)`(`tick_channel_switch_enabled`, bool) · `get_tick_channel_switch_offset_secs()`(`tick_channel_switch_offset_secs`) · `get_tick_channel_switch_ack_timeout_secs()`(`tick_channel_switch_ack_timeout_secs`) · `get_tick_channel_revert_probe_secs()`(`tick_channel_revert_probe_secs`, 기본값 = `stale_diagnostics.SUBSCRIBE_GRACE_SECS` 재사용 — 단일 정의처는 거기, 여기서 재정의하지 않는다). 뜻·기본값 = `src/realtime/CLAUDE.md` 「시세 채널 — 시간축 전환 + 프리 창 속성축 보정」 절 운영 다이얼 표, 클램프는 읽는 쪽.
- 다섯 키 모두 **캐시 0 · TTL 0**(캐시만큼 장중 킬스위치가 늦어진다). **키 부재·조회 실패 = `None`** → 엔진이 **현재 값을 유지**(기본값으로 되돌리지 않는다). 소비 = `engine/tick_channel_mode.refresh_mode()` / `refresh_switch_params()`(5분·120초 폴링) + `PUT /api/realtime/tick-channel-mode`(즉시, 선택 필드 `switch_enabled`).
- 🔴 **`tick_channel_gap_hold_enabled` 는 소비처 없는 폐기 키다** — 이름을 재사용하지 않는다(반대 의미로 되살리면 운영 DB 에 남은 `false` 가 조용히 적용된다). 그 행은 지우지 않는다 — DELETE 는 승인 대상 운영 조치이고 얻는 것이 없다.

**운영 토글·자금**:

- `get_auto_start() -> bool` / `set_auto_start(enabled)`: 키 `auto_start`, `{"value": bool}`. 소비 = `main.py` lifespan + `routes/strategies.py` auto-start 라우트
- `get_cash_usage_ratio() -> float` / `set_cash_usage_ratio(ratio)`: 키 `cash_usage_ratio`, `{"value": float}`, 범위 `[0.0, 1.0]`, 5% 단위 자동 보정, 기본 1.0. 새 값 ≤ 직전 × 0.7(`_CASH_USAGE_RATIO_DROP_ALERT_RATIO`)이면 `[cash_usage_ratio]` WARNING(관측 전용 — 저장은 한다)
- `get_auto_regime_adjust() -> bool` / `set_auto_regime_adjust(value)`: 키 `auto_regime_adjust`, 기본 **False**(`_AUTO_REGIME_ADJUST_DEFAULT`). 🔴 **판독 불가(키 없음·`value` null·dict/bool 아닌 타입·예외)는 전부 False(수동 모드)** + `[auto_regime_adjust] default_used reason=…` WARNING — True 로 떨어지면 레짐 `cash_min` 이 `cash_usage_ratio` 로 영속돼 예산이 접힌다(`defensive` `cash_min=75` → 0.25)
- `get_auto_apply_enabled() -> bool` / `set_auto_apply_enabled(value)`: 키 `auto_apply_enabled`, 기본 **False**(운영자가 켠 뒤에만 AI 자문 자동 적용) · `get_etf_regime_enabled() -> bool` / `set_etf_regime_enabled(value)`: 키 `etf_regime_enabled`, 부재 = False. 둘 다 `.env` 폴백 없음
- `get_account_risk_warn_pct() -> float` / `get_account_risk_block_pct() -> float | None`: 키 `account_risk_warn_pct` / `account_risk_block_pct`. 부재·조회 실패 = warn 4.0 / block `None`(차단 비활성)
- `get_krx_open_api_config()` / `set_krx_open_api_config(...)`: 키 `krx_open_api_enabled` / `krx_open_api_base_url` / `krx_open_api_key`. 🔴 **끄기 전에 소비처를 전수 확인한다** — 끄면 `src/api/krx.py` 가 `KrxApiError` 를 던져 `scanner._full_universe_load_krx_primary` 가 KIS 폴백으로 밀린다(루트 「핵심 안전 규칙」 비활성화 심층 검증 의무). 키 값은 응답·로그에 노출하지 않는다
- **외부 통합 토글 (DB 우선, `.env` 폴백)**: `get_dkstock_regime_enabled() -> bool | None` / `set_dkstock_regime_enabled(value)`(키 `dkstock_regime_enabled`) · `get_kis_mcp_enabled() -> bool | None` / `set_kis_mcp_enabled(value)`(키 `kis_mcp_enabled`). 부재·판독 불가·DB 조회 실패 = `None` → 호출자가 `settings.*` 로 폴백. 헬퍼 `_get_bool_or_none(key)` / `_set_bool(key, value)` 가 `{"value": bool}` 과 옛 형식(직저장 bool, `'true'`/`'false'` 문자열)을 모두 읽는다
- **task 신선도 마커**: `get_task_last_success(task_label) -> str | None`(키 `task_last_success_<label>`) / `set_task_last_success(task_label, iso_ts)`, 값 = KST ISO. `task_loop_helper.run_periodic_task_loop` 의 부팅 즉시 실행 게이트 두 갈래(`immediate_skip_if_fresh_hours` · `immediate_skip_if_fresh_since_trading_slot`)가 읽고 `once()` 성공 직후에만 쓴다(대상·판정 순서 = `src/engine/CLAUDE.md` 「정기 task 루프」 절). 60초 하트비트 `engine_alive_heartbeat`(`uptime_monitor.py`)도 같은 키 공간이다. **`get_task_last_success_bulk(task_labels) -> dict`** = `key = ANY($1)` **단일 쿼리**(`GET /api/market-ops`) — 결측 라벨은 **키가 없고**(빈 문자열 아님), 쿼리 실패는 빈 dict(fail-open)

**종목상태 킬스위치 2키 (cycle369)** — 관리종목(51)·단기과열(59) 보유 청산과 당일 매수 차단을 따로 끈다:

- `get_status_exit_mode_raw() -> str | None` / `set_status_exit_mode(mode)` — 키 `status_exit_mode`(보유 청산) · `get_status_buy_block_mode_raw() -> str | None` / `set_status_buy_block_mode(mode)` — 키 `status_buy_block_mode`(당일 매수 차단). 저장 = `{"value": str}`, getter 는 직저장 문자열도 읽는다(`_string_from_raw`). 캐시 0.
- 🔴 **`None`(키 없음)은 행 자체가 없을 때(`_select_value` 의 `_MISSING`)뿐이다.** 행은 있는데 모양이 틀리면(값 없는 dict · `{"value": null}` · JSONB null · 숫자 · 목록) 어휘 밖 마커 `_MALFORMED_MARKER`(`"__cycle369_malformed__"`)를 돌려주고 leaf 가 `observe` 로 떨어뜨린다 — 깨진 행을 「키 없음 = `enforce`」 로 접으면 끄려던 매도가 켜진다.
- 🔴 **getter 는 `_get_string_or_none` 이 아니라 `_select_value` 를 직접 불러 DB 예외를 전파한다** — 그 헬퍼는 예외를 `None` 으로 삼켜 「키 없음 = `enforce`」 와 「DB 장애 = 직전 값 유지」 를 가르지 못한다. 예외 처리는 `status_exit_watch.refresh_modes()` 가 한다.
- setter 는 어휘(`enforce`/`observe`/`off`)를 검증하지 않는다(라우트 모델 `StatusExitModeRequest` 가 한다). 값의 의미 = `src/engine/CLAUDE.md` 「종목상태 청산·당일 매수 차단」 절.

**레짐 표시 설정 (매매가 소비하지 않는다)** — `.env` 폴백 없음(DB 미설정이면 코드 기본값):

- `get_buy_block_mode() -> str` / `set_buy_block_mode(mode)`: 키 `buy_block_mode`, 기본 `HARD`. 4 모드 밖은 `ValueError`
- `get_buy_block_thresholds() -> BuyBlockThresholds`(Pydantic) / `set_buy_block_thresholds(vix_threshold=, fg_high_threshold=, fg_low_threshold=, defensive_enabled=)` 부분 갱신. 4 키 = `buy_block_vix_threshold`(25.0) / `buy_block_fg_high_threshold`(85.0) / `buy_block_fg_low_threshold`(15.0) / `buy_block_regime_defensive_enabled`(true)
- ⚠️ **이 값들은 매수를 차단하지 않는다** — 대시보드·자문 payload 표시 전용(루트 `CLAUDE.md` 「외부 통합」).

**scanner 구독 필터 2종** (`.env` 폴백 없음, 운영 가변):

- `get_price_filter() -> PriceFilter`(Pydantic) / `set_price_filter(*, min_price=None, max_price=None)` 부분 갱신. 키 `price_filter_min` / `price_filter_max`(int 원, 0 = 비활성). 음수, 그리고 둘 다 0 초과일 때 `min_price > max_price` 는 `ValueError`
- `get_trade_amount_filter() -> TradeAmountFilter`(Pydantic) / `set_trade_amount_filter(*, min_amount=None)` 부분 갱신. 키 `trade_amount_filter_min`(int 원, 0 = 비활성). 음수는 `ValueError`
- 적용 = `src/engine/scanner.py::subscribe_filtered_stocks` 진입 hook(가격 → 거래대금), 60s TTL 캐시 `_get_price_filter_for_scanner` / `_get_trade_amount_filter_for_scanner`. 거래대금 소스·보호 종목 처리 = `src/engine/CLAUDE.md` 「risk.py」 절 가격·거래대금 필터 항목. PUT 직후 `invalidate_price_filter_cache_scanner()` / `invalidate_trade_amount_filter_cache_scanner()` — **무효화가 unsubscribe 를 발화시키지 않는다**(KIS LMS chain 차단)
- 🔴 **매수 진입 전용** — 임계 밖 종목은 구독만 막히고 매도·손절·익일청산·15:20 강제청산 영향은 0. **보유·익일청산 종목은 절대 통과**(공통 헬퍼 + early-return + AST keyword 의무 가드 3중)

## kis_quote_accounts.py — 보조 KIS 시세 수신 계좌 풀

- `list_accounts(active_only=False)` / `get_account(id)` / `get_account_by_label(label)` — 응답 `KisQuoteAccount` 는 `app_secret_masked` 만 담는다(평문 노출 금지)
- read 4함수(`list_accounts`/`get_account`/`get_account_by_label`/`get_credentials_for_token_manager`)는 `_with_retry` 내장, 쓰기(insert/update/delete)는 `pg.execute` 로 미경유
- **`list_accounts` 60s TTL 메모리 캐시**: 모듈 전역 `_list_cache` / `_list_cache_expires_at` + `invalidate_list_cache()` + `_LIST_CACHE_TTL=60.0`(`time.monotonic()`), `active_only` 값별 키. DB 예외 시 캐시가 있으면 stale, 없으면 빈 리스트. INSERT/UPDATE/DELETE 직후 `invalidate_list_cache()` 로 즉시 반영
- `insert_account(label, app_key, app_secret, kis_env)` — label UNIQUE 충돌 = `LabelConflictError`, 빈 값·부적합 `kis_env` = `ValueError`
- `update_account(id, active=None, label=None)` — 부분 갱신(label 충돌 = `LabelConflictError`). app_key/app_secret 수정 미지원(보안 감사 추적성 — 삭제 후 재등록) · `delete_account(id)` — 존재하면 True, 없으면 False
- `get_credentials_for_token_manager(label)` — **토큰 매니저 전용 평문 노출 함수**. `src/auth/token.py::get_token_manager(label)` lazy 초기화에서만 부른다. 🔴 **API 응답·로그에 절대 노출 금지**
- 테이블 `kis_quote_accounts`(UUID PK, label UNIQUE, active=true 부분 인덱스). **시세 수신 한정**이다 — `order.py` / `balance.py` / 체결통보 구독은 메인 계좌만 쓴다

## strategy_funnel.py — 조건검색 단계별 추적

- **`insert_snapshot(*, target_date, strategy_id, step_no, step_name, survived_tickers=None, excluded_sample=None, survived_count=None, excluded_count=0, step_conditions=None, is_provisional=False) -> dict | None`** — 전부 keyword-only. `(target_date, strategy_id, step_no)` **UPSERT**(UNIQUE = migration 035) — 단계당 최신 1행.
  - `snapshot_at` = **그 행의 마지막 쓰기 시각**(생성 시각 아님). 첫 INSERT = 컬럼 기본값 `now()`(migration 030), 덮어쓰기 = `DO UPDATE SET … snapshot_at = now()` — 둘 다 DB 시계(애플리케이션 `datetime` 미바인딩). 이 값을 조건으로 쓰는 소비처는 `routes/market_ops.py` 하나(`src/routes/CLAUDE.md` `/api/market-ops` 행).
  - `survived_tickers` = `list[str]` 또는 `list[dict]`(`{ticker, name}`), `excluded_sample` = `[{ticker, name, reason}]` — 읽는 쪽이 형식을 분기한다. `survived_count` 가 `None` 이면 `len(survived_tickers)`. `step_conditions` = UI 툴팁 문자열.
  - `is_provisional=True` = 저녁 잠정 캡처(21:00 미리보기는 `target_date` = **다음 거래일**, 부팅 +600초 레거시 재준비는 오늘). `False`(기본) = 09:30 자동·수동 trigger(확정, 오늘).
  - 🔴 **잠정 쓰기는 확정 행을 덮지 못한다(③-b)** — `ON CONFLICT (target_date, strategy_id, step_no) DO UPDATE SET … WHERE NOT (strategy_funnel_snapshots.is_provisional = FALSE AND EXCLUDED.is_provisional = TRUE)`. 그 조합이면 `RETURNING` 이 비어 **`None`** 이고 확정 행(`snapshot_at` 포함)은 그대로다. 나머지 세 조합(잠정→잠정 · 확정→잠정 · 확정→확정)은 갱신된다(09:30 확정 캡처가 그날 잠정 행을 덮는 것이 정상 경로). `None` 반환 = 이 거부 또는 DB 예외. 가드 = `tests/unit/db/test_cycle364_funnel_protect_confirmed.py` · PG 왕복 `tests/integration/test_cycle364_funnel_protect_confirmed_pg.py`.
  - **JSONB cap**: `SURVIVED_TICKERS_CAP = 200` / `EXCLUDED_SAMPLE_CAP = 20`. `survived_count` 는 cap 과 무관하게 정확한 값.
- `list_snapshots(*, target_date, strategy_id=None, raise_on_error=False)`: 그 영업일 + 전략의 전 단계(`step_no` ASC). 조회 예외는 기본 WARNING + `[]`, `raise_on_error=True` 면 던진다(`funnel_capture` ④ 가 DB 장애를 「저녁 캡처 없음」과 가르려고 쓴다)
- `list_recent_by_strategy(strategy_id, days=7)`: 최근 N영업일 추이 — `target_date <= 오늘` 이라 저녁 미리보기(다음 거래일) 행은 안 나온다
- 테이블 `strategy_funnel_snapshots`(UUID PK + 인덱스 2 = `target_date DESC` / `(strategy_id, target_date DESC)`)
- 쓰기 = 공통 헬퍼 `scheduler.capture_funnel_snapshots(registry, *, is_provisional=False, target_date=None, skipped_out=None)` 하나. 호출처·시각·라벨 가드·쓰기 순서 = `src/engine/CLAUDE.md` 「funnel 스냅샷 캡처」 절, 단계 수집 hook(`_record_funnel_step`) = `src/engine/strategies/CLAUDE.md`.

## stock_master.py — 종목 마스터 캐시

- `upsert_one(StockBasics)` / `get(ticker) -> Optional[StockBasics]` / `is_stale(ticker, max_age_hours=24) -> bool`
- 테이블 `stock_master`. PK `ticker`(KRX 6자리), `refreshed_at` 24h TTL
- NXT 거래가능 사전 판별 3경로 = `OrderEngine._strategy_exchange_async` · `scheduler._execute_next_day_clear` · `execute_sell` 거부 사후 보강(`upsert_one(..., nxt_tradable=False)`)
- 호출 = 매수/매도 진입 직전 lazy(miss/stale → `inquire_stock_basics` 후 upsert) + 부팅 eager `scheduler._eager_refresh_stock_master_for_held_positions()`(보유 + `_pending_next_day_clear`, 24h fresh 는 skip) — lazy 만이면 첫 사이클 캐시 miss → SOR/NXT 발사 → KIS 거부다
- **ticker 정규화**: `inquire_stock_basics` 가 `_normalize_ticker()` 로 KIS `pdno` 12자리의 마지막 6자리를 뽑고, `upsert_one` 이 6자리 미준수 입력도 정규화한다(이중 안전망, WARNING)
- 조회·진단 보조: `count_active()` / `list_all(limit=100, offset=0)` / `list_history(ticker, limit=100)`(「DB 스키마」 절 `stock_master_history`) / `count_eager_refresh_today()`

### `master_raw` 컬럼 (migration 034)

KIS 공식 일일 마스터 파일(`kospi_code.mst` / `kosdaq_code.mst`) 영역 = `master_raw JSONB` **별도 컬럼**.

- 컬럼 `master_raw JSONB NOT NULL DEFAULT '{}'::jsonb` + `master_raw_updated_at TIMESTAMPTZ`. 인덱스 2 = GIN(키 검색) + DESC NULLS LAST(갱신 시각 진단)
- 🔴 **`raw` 영역을 건드리지 않는다** — `bfdy_clpr` / `hts_avls` 덮어쓰기 0건, AST 가드 `tests/unit/ast/test_cycle129_ast_master_raw_separation.py`
- `upsert_master_raw(ticker, master_raw: dict, *, is_kospi200: bool = False, is_kosdaq150: bool = False) -> None` — `master_raw_updated_at` KST 강제. `ON CONFLICT DO UPDATE` 가 payload 키만 SET 하므로 **기존 ticker 갱신 때 두 플래그 명시가 의무**다(빠뜨리면 False 로 덮인다)
- `get_master_raw(ticker) -> Optional[dict]` — 단건, lazy 폴백 없음(16:30 배치 적재분만) · `count_master_raw_today() -> int` — KST 영업일 기준 `master_raw_updated_at` 카운트
- **`get_nxt_provenance_map(tickers) -> dict[str, bool]`**: 그 행 `raw` 에 CTPF1002R 키 `cptt_trad_tr_psbl_yn` 이 **있는가**(값이 아니라 키 존재 — `raw ? 'cptt_trad_tr_psbl_yn'`). 형제 `get_nxt_tradable_map(tickers) -> dict[str, bool | None]` 과 같은 `= ANY($1::text[])` 1회 왕복. 시세 채널 리졸버가 `nxt_tradable` 을 **믿어도 되는지** 가른다. 소비처의 **독립 try** 금기 = `src/engine/CLAUDE.md` `no_feed_registry.py` 항목
- **`count_missing_kis_provenance_key() -> int`(cycle363)**: 같은 판별자의 **전체 카운트** — basics 강제 재실행 판정의 재료(`src/engine/CLAUDE.md` 「정기 task 루프」 절). 🔴 **`count_active()` 류와 달리 예외를 0 으로 삼키지 않는다** — 0 은 "결측 0건"(SKIP)이라 "쿼리 실패는 RUN 쪽 fail-safe" 결정과 반대로 움직인다(예외는 `reason=force_check_error` 로 RUN)
- 호출자: 적재 = `scanner._stock_master_master_load_once()`(16:30 `TIME_STOCK_MASTER_MASTER_LOAD`) / 조회 = `scanner.apply_master_block_filter` · `scanner.scan_stocks`(momentum 경로) — 둘 다 `_is_master_blocked_for_entry(master_raw, raw)` 1단계 차단 11건(= master_raw 7 + raw 4) · `sector_naming` · kojiro 섹터

### `get_stats()` — 운영 진단 집계 8키

- 8키 = `count_all` / `bfdy_clpr_present` / `nxt_tradable_count` / `with_hts_avls` / `with_acml_tr_pbmn` / `top_10_recent` / `total_daily_rows` / `last_daily_load_at`(뒤 둘은 `stock_master_daily` 연동). 타입 = `frontend/src/types/stock-master.ts` `StockMasterStats`
- 🔴 **카운트는 전부 별도 `SELECT count(*)`** — 행을 가져와 Python 에서 세지 않는다. AST 가드 `tests/unit/ast/test_cycle128_ast_no_range_9999_silent_cap.py`(`src/db/stock_master.py` 의 `.range(0, 9999)` 잔존 0건)
- JSONB 키 존재성(`bfdy_clpr_present` / `with_hts_avls` / `with_acml_tr_pbmn`) = `raw->>'키'` non-null ∧ `<> '0'` ∧ `<> ''`(수치 비교 아님). 각 쿼리는 실패해도 0. `top_10_recent` 는 별도 `LIMIT 10` fetch

### `list_by_filter()` — scanner 유니버스 조회

```python
list_by_filter(*, market=None, min_market_cap=0, min_trade_amount=0,
               exclude_tickers=None, nxt_tradable=None,
               is_kospi200=None, is_kosdaq150=None,
               limit=500, return_stage_counts=False, sort_by=None,
               exclude_etf_like=False)
    -> list[dict] | tuple[list[dict], dict[str, list[str]]]
```

- 전부 keyword-only. KIS `volume-rank` 없이 DB 만으로 유니버스를 만든다(KIS 호출 0건).
- **필터는 전부 SQL WHERE 이고 `LIMIT` 앞이다** — 정렬 `ORDER BY refreshed_at DESC`, `LIMIT` = 요청 `limit`(오버페치 없음). 그래서 `exclude_etf_like=True` 면 ETF 가 후보 칸을 먼저 차지하지 않는다.
  - `market`: `"kospi"` → `excg_dvsn_cd = '02'` / `"kosdaq"` → `'03'` / `None` → 전체
  - `min_market_cap`(원): 생성 컬럼 `hts_avls_eok`(억원) `>= (min_market_cap + 99_999_999) // 100_000_000` · `min_trade_amount`(원): 생성 컬럼 `acml_tr_pbmn_won`(원) `>=` 직접 비교
  - `exclude_tickers`: `ticker <> ALL($n::text[])` · `nxt_tradable`: `None` 무필터 / True·False 등가 비교
  - `is_kospi200`·`is_kosdaq150`: **둘 다 True 면 `(is_kospi200 = true OR is_kosdaq150 = true)` OR 합집합**(donchian_swing `FUNNEL_STAGES[0]` "코스피200+코스닥150 합집합" 정합), 한쪽만 주면 그 컬럼 AND, 둘 다 None 이면 무필터
  - `exclude_etf_like`: `False`(기본)면 SQL 불변. `True` 면 `NOT (CASE WHEN 코드 <> '' THEN 코드 = ANY(ETF_GROUP_CODES) ELSE 이름 LIKE ANY('%kw%'…) END)` 로 ETF/ETN(류)를 뺀다(코드 = `UPPER(BTRIM(raw->>'scty_grp_id_cd', E' \t\r\n'))`, 이름 = 아래 COALESCE 이름, NULL 은 `COALESCE` 가 `''` 로 받는다 — `NOT (...)` 이 NULL 이 되어 행이 조용히 빠지지 않게). `src.engine.etf_like.is_etf_like` 와 **행 단위로 같다**(PG 차등 테스트 `tests/integration/test_cycle380_list_by_filter_etf_pg.py`). 상수는 그 leaf 에서 import 하고 다시 적지 않는다(AST G6). `True` 는 6 전략 `_scan_universe` 만 넘긴다(`scanner._stock_master_financial_load_once` · `tools/validate_turtle_sizing.py` 는 기본값).
- SELECT 종목명 = `COALESCE(NULLIF(name, ''), NULLIF(TRIM(master_raw->>'hts_kor_isnm'), ''), '') AS name` — CTPF1002R 이름 → 마스터파일 한글명 → `''`(호출자 `row.get("name","")` 의 None 회귀 차단).
- `return_stage_counts=True` 면 `(filtered, {"union_tickers", "mcap_tickers", "trade_tickers"})` — union(시총·거래대금 컷 전) → mcap(시총 컷 후) → trade(= 최종 filtered) 3쿼리(같은 SQL 빌더라 ETF 제외도 union 부터). funnel 관찰성 전용 — **필터 로직·임계·순서 불변**(`True` 의 filtered 가 `False` 결과와 원소·순서까지 같다 = 가드 계약).
- `sort_by`: 정렬 훅, `None`(기본) = `refreshed_at DESC`. **6자리 ticker 검증은 호출자 `_scan_universe` 가 한다**.
- `raw` 의 `acml_tr_pbmn` / `lstn_stcn` / `acml_vol` 은 `inquire_stock_basics` 가 CTPF1002R 뒤에 FHKST01010100 을 merge 해 채운다. 🔴 **CTPF1002R 기존 키를 덮어쓰지 않는다**(`bfdy_clpr` 정합, AST G-AST1).

### `list_paged_by_filter()` — UI 종목목록 조회

```python
list_paged_by_filter(*, market=None, min_market_cap=0, min_trade_amount=0,
                     name_substr=None, limit=100, offset=0) -> dict
```

- 전부 keyword-only. 반환 `{"items": list[dict], "total": int, "limit": int, "offset": int}`.
- `market`: `"KOSPI"` → `excg_dvsn_cd = '02'` / `"KOSDAQ"` → `'03'`(대소문자 무시) / `None` → 전체. `min_market_cap`·`min_trade_amount` 는 `list_by_filter` 와 같은 생성 컬럼 비교. `name_substr`: `name ILIKE '%substr%'`
- 🔴 **시총·거래대금 비교는 생성 컬럼(migration 039)으로만 한다** — `raw` 의 두 값은 jsonb *문자열*이라 `raw->'hts_avls' >= N::jsonb` 가 **항상 false** 인데 결함이 안 보인다. 생성 컬럼 = `CASE WHEN raw->>'…' ~ '^[0-9]+$' THEN (raw->>'…')::bigint END STORED`. AST 가드 `tests/unit/db/test_cycle168_list_paged_generated_cols.py`(jsonb gte 잔존 0건)
- `total` = 같은 WHERE 의 별도 `SELECT count(*)`(페이징 정합). 정렬 `refreshed_at DESC`. count·data 쿼리는 각각 실패해도 0 / `[]`
- 호출자 = `GET /api/stock-master/list` 라우트뿐(scanner 전용 `list_by_filter()` 와 분리)

## stock_master_daily.py — KIS 일봉 정규화

- 테이블 `stock_master_daily`(migration 033). PK `(ticker, bas_dd)` + 인덱스 `(ticker, bas_dd DESC)` · `(bas_dd DESC)`. 적재 매일 20:30(`TIME_STOCK_MASTER_DAILY_LOAD`) — 대상·깊이·흐름 = `src/engine/CLAUDE.md` 「저녁 데이터 적재」 절.
- 컬럼 10종: `open_price`/`high_price`/`low_price`/`close_price`/`volume`/`trade_value`/`change_rate`/`flng_cls_code`/`prtt_rate`/`raw JSONB`. KIS FHKST03010100 키 매핑(`chk_inquire_daily_itemchartprice.py` 정본) = `stck_bsop_date / stck_oprc / stck_hgpr / stck_lwpr / stck_clpr / acml_vol / acml_tr_pbmn / flng_cls_code / prtt_rate`
- **`change_rate` = `_derive_change_rate(candle)`(cycle365)** — 일봉 output2 에는 `prdy_ctrt` 가 없어(`output1` 전용) `prdy_vrss ÷ (stck_clpr − prdy_vrss) × 100` 으로 낸다(`prdy_ctrt` 가 오면 그대로). 부호는 `prdy_vrss_sign`(1상한/2상승/3보합/4하한/5하락)으로 교차검증·보정, 분모 0·`prdy_vrss` 결측은 0.0. 권리락·액면변경일에는 연속 종가 비율이 아니라 이 칸이 실제 등락률이다. 매매 코드는 읽지 않는다(소비처 = UI `StockMaster.tsx` 일봉 탭).
- CRUD:
  - `upsert_daily(ticker, bas_dd, ohlcv)` — KIS row 단건 정규화 upsert · `upsert_batch(ticker, candles) -> int` — `_BATCH_SIZE = 100` chunk
  - `get_recent_daily(ticker, days=20)` — 최근 N일(DESC). 🔴 **`days` 를 `max(1, min(days, _MAX_DAILY_ROWS))` 로 하드 클램프**한다. 행을 돌려주는 읽기 4함수(`get_donchian_high`·`get_atr`·`get_recent_daily_with_fallback`·`get_recent_daily_normalized`)가 전부 이 함수를 경유해 **어느 소비처도 상한을 넘겨 읽지 못한다**(나머지는 스칼라 집계). 예외 = `list_provisional_rows`(날짜 창 `[since, head]` 조회, 창 폭 `daily_bar_finalize.WINDOW_CAL_DAYS` 21일).
    - **`_MAX_DAILY_ROWS = 400`(cycle300)** — 보유 약 261 영업일과 VCP full 요청 285행을 자르지 않으면서, 오염된 파라미터가 `LIMIT` 에 실려 전체 스캔이 되는 것을 막는 폭주 방어선이다.
    - 🔴 **`min()` 구조 자체를 지우지 않는다** — 값은 바뀌어도 클램프가 방어선이다. 가드 `tests/unit/db/test_cycle299_retention_expansion.py::test_g299_7a_get_recent_daily_keeps_days_clamp`(구조) + `tests/unit/engine/strategies/test_cycle300_daily_depth_switch.py`(숫자의 근거).
    - ⚠️ 상한은 관문이지 읽는 양이 아니다. 100행 초과 요청 = VCP `daily_fetch_depth_mode="full"` · `market_unit`(`FETCH_ROWS = 120`) · 야간 `pyramid_shadow`(400)뿐이다.
  - `get_donchian_high(ticker, days=20)` — 직전 N일 최고가(당일 제외)
  - `get_atr(ticker, days=14)` — True Range = 와일더 3-way `max(고−저, |고−전종|, |저−전종|)`, 평활 = **단순평균(SMA) baseline**. Wilder 지수평활은 호출자 책임이고 실제 Wilder ATR 은 `kojiro_indicators.atr`(ewm α=1/N) 뿐
  - `count_all()` / `count_by_ticker(ticker)` — 적재 진단
  - `max_bas_dd(ticker=None)` — 백필 vs 증분 분기 키(스캐너). `None` = 테이블 전체 최대값. DB 예외는 삼키고 `None`(ERROR 로그만)
  - **`max_bas_dd_before(today) -> date | None`**(cycle386) — 전일 잠정 봉 확정의 헤드(`SELECT max(bas_dd) FROM stock_master_daily WHERE bas_dd < $1`, `today` = 호출자가 정한 KST `date`). 🔴 **예외를 삼키지 않는다**(`max_bas_dd(None)` 과 다르다) — 삼키면 조회 실패가 「오늘 앞 봉 없음」 = `result=noop`(INFO)으로 둔갑한다. 실패는 호출자가 `result=error stage=head` 로 남긴다. 재시도는 `pg.fetchval`.
  - **`list_provisional_rows(*, since, head, today_boundary) -> list[dict]`**(cycle386) — 전일 「잠정 봉」 조회(계약 = `src/engine/CLAUDE.md` 「저녁 데이터 적재」 절). `bas_dd` 가 `[since, head]` 안이고 아래 조건인 행의 `ticker, bas_dd, open_price, high_price, low_price, close_price` 를 `ticker, bas_dd` 순으로 돌려준다. 이 함수와 `max_bas_dd_before` 의 소비처는 `src/engine/daily_bar_finalize.py` 하나다.
    - 헤드 행(`bas_dd = head`) = `updated_at < today_boundary`(호출자가 오늘 06:00 KST 를 넘긴다)
    - 그 밖(`bas_dd < head`) = `updated_at < ((bas_dd + 1)::timestamp AT TIME ZONE 'Asia/Seoul') + interval '6 hours'`
    - SQL 안에서 `'Asia/Seoul'` 을 명시한다(세션 시간대에 기대면 연결이 UTC 로 돌던 사고 = `pg.py::_init_conn` 을 다시 만든다). 🔴 **예외를 삼키지 않는다** — 빈 목록이면 「대상 조회 실패」가 「고칠 것 없음」으로 둔갑한다. 재시도는 `pg.fetch`.
  - `get_recent_daily_with_fallback(ticker, n)` — DB miss 시 `fetch_daily_candles` 폴백
  - **`get_recent_daily_normalized(ticker, days, *, min_required=None, expected_head: date | None = None)`** — DB일봉 어댑터. row 의 `raw` JSONB(KIS 원본 키 `stck_clpr`/`stck_oprc` 등)를 **그대로 반환**해 prepare 의 `c.get("stck_clpr")` 를 무변경으로 쓰게 한다(raw 키 없는 row 는 row 자체)
  - `purge_old_rows(cutoff_date, *, protected_tickers=None) -> dict[str, int]` — 아래 retention 항목
- **KIS 폴백 조건 3개 (DB 를 쓰기 전에 이 순서로 검사한다)**:
  1. **락 게이트(최우선)** — 윈도우 안 1 row 라도 `_row_has_lock`(`flng_cls_code not in ("", "00")` 또는 `abs(float(prtt_rate)) > 0`)이면 `fetch_daily_candles` 로 강제 폴백한다(수정주가는 조회할 때 달리는 값이라 DB 의 락 전 과거봉과 어긋난다). 정규화 컬럼만 보므로 **KIS 추가 호출 0건**. ⚠️ `prtt_rate != 1.0` 을 기준으로 삼지 않는다 — 정상 행이 `"0.0000"` 이라 전 종목이 폴백한다
  2. **신선도 게이트** — `max_bas_dd(ticker)` 가 `None`(판정 불가)이면 graceful 통과.
     - `expected_head` **있음**(키워드 전용, 「직전 영업일」 — 6전략 `prepare()` 가 `StrategyBase._resolve_expected_daily_head()` 로 넘긴다) → `latest < expected_head` 면 폴백(`reason=stale`), 벽시계 달력 판정은 안 본다. **하루치 결손도 폴백**이라 저녁 적재가 빠진 다음 날은 prepare 가 느려진다 — `[daily_head_stale]`(`boot_manager.emit_daily_head_staleness`)가 그 아침 알린다.
     - `expected_head` **없음**(`None`) → `(today − latest).days > DAILY_STALENESS_DAYS` 면 폴백. 인자 없는 호출부(kojiro `recompute_held_atr` · `llm_buy_gate`)와 휴장일 조회가 실패한 날의 prepare 가 이 갈래다.
     - 🔴 **깊은 요청(`days > _KIS_SINGLE_CALL_MAX_DAYS`=100) 예외(cycle363)** — KIS 는 1회 최대 100봉이라 폴백하면 VCP full(~250봉)이 100봉으로 깎인다(200 EMA → 75 EMA). 그래서 `days > 100` 이면 **① `_legacy_calendar_fresh`(달력 4일 이내) 또는 ② `latest` 가 `expected_head` 의 정확히 1영업일 전**(`_is_exactly_one_business_day_behind` — `trading_calendar.previous_trading_day` 지연 import, never-raise, 실패·모름 = False)이면 DB 행을 쓴다. 그 밖(2영업일 이상 결손 등)과 ≤100봉 요청은 폴백한다. 회귀 = `tests/unit/db/test_cycle363_expected_head.py`(F3 절).
  3. **min_required 게이트** — `len < min_required`(기본 `max(days // 2, 10)`)이면 폴백
  - 폴백이 실패하면 DB 값을 쓴다. 헬퍼 3 = `_row_has_lock` / `_extract_raw` / `_kis_fallback`. 폴백 로그 = `[prepare_db_fallback] ticker= reason= db= kis=` 1행
  - `DAILY_STALENESS_DAYS = 4`(달력일 — 주말 2일 + 공휴일 마진)는 `expected_head` 가 없을 때만 쓴다. 전략별 `min_required` = `src/engine/strategies/CLAUDE.md` 「prepare 공통」 절
- **retention `DAILY_RETENTION_DAYS = 390`(달력일 ≈ 261 영업일, cycle299)** — backfill target 225 영업일(`src/engine/CLAUDE.md` 「저녁 데이터 적재」 절) 위로 **36 영업일 마진**. 🔴 **이 값과 target 은 함께 움직인다** — target 이 보유 영업일을 넘으면 `existing_count` 가 target 에 못 닿아 매일 밤 전량 재backfill(churn)이 된다. 가드 `tests/unit/db/test_cycle299_retention_expansion.py`.
- **`purge_old_rows` 는 날짜 슬라이스 루프다** — `PURGE_MAX_DATE_ITERATIONS = 500` cap 안에서 ① cutoff 이전 가장 오래된 `bas_dd` 를 **protected 를 뺀 채** SELECT(없으면 drained break) ② 그 날짜를 **protected 를 뺀 채** DELETE ③ deleted 누적. 🔴 **SELECT 쪽 protected 제외를 빼지 않는다** — protected 만 남은 날짜를 무한히 다시 고르는 never-drain 이 된다. 예외 시 부분 누적 deleted 를 반환한다(`logger.exception` 에 `type(exc).__name__: str(exc)[:150]`)
- 🔴 **`updated_at` 은 「KIS 값을 받아 그 행에 쓴 순간」 하나만 뜻한다** — `_candle_to_row` 가 `now_kst_iso()` 로 찍고 `_UPSERT_DAILY_SQL` 이 충돌 때도 `updated_at = EXCLUDED.updated_at` 으로 다시 찍는다. 전일 잠정 봉 판정(`list_provisional_rows`)이 이 칼럼 하나에 기댄다(20:30 적재분은 잠정, 다음 아침 `daily_bar_finalize` 가 확정 — `src/engine/CLAUDE.md` 「저녁 데이터 적재」 절).
  - 🔴 `_UPSERT_DAILY_SQL` 말고 이 테이블 `updated_at` 을 바꾸는 쓰기(UPDATE 문 · 트리거 · 마이그레이션)를 두지 않는다 — 잠정 봉이 확정으로 분류돼 다음 부팅이 고치지 않는다. 1회 백필(예: `change_rate`)도 `updated_at` 을 건드리지 않는다.
  - 가드 = `tests/unit/ast/test_cycle386_ast_finalize.py` G5(c1~c4 — `src/` 의 쓰기 SQL · 찍는 자리 · 마이그레이션) + 실 Postgres `tests/integration/test_cycle386_provisional_predicate_pg.py`(충돌 때 다시 찍기 · 트리거 없음).
- DB 호출 = `pg.fetch`/`pg.execute`/`pg.executemany`. read 는 `_with_retry` 내장, 쓰기 3함수(`upsert_daily`/`upsert_batch`/`purge_old_rows`)는 미경유(AST G-187-A2 영구 불변식). KST timestamp `_kst.now_kst_iso()` · raw JSONB 덮어쓰기 금지(G-AST1) · DATE 바인딩 `_kst.to_date()` 강제
- **UI 동기화 의무**: 컬럼 추가 시 `GET /api/stock-master/{ticker}/daily?days=N`(`src/routes/stock_master.py`) · `frontend/src/pages/StockMaster.tsx::DailyTab` · `get_stats()` 의 `total_daily_rows`/`last_daily_load_at` 을 함께 고친다. 절차 = `frontend/CLAUDE.md` 「(6) 신규 데이터 추가 시 UI 동기화 절차」 절

## stock_master_financial.py — KIS 재무 5 TR 정규화

- 테이블 `stock_master_financial`(migration 041). PK `(ticker, stac_yymm, div_cls)`(`div_cls` 0=년/1=분기) + 인덱스 `ix_smf_ticker_div (ticker, div_cls, stac_yymm DESC)`
- 정규화 NUMERIC 18종: 손익 5(`sale_account`/`sale_totl_prfi`/`bsop_prti`/`thtr_ntin`/`depr_cost`) + 대차 7(`cras`/`fxas`/`total_aset`/`flow_lblt`/`total_lblt`/`total_cptl`/`cpfn`) + 수익성 2(`cptl_ntin_rate`/`sale_totl_rate`) + 안정성 2(`lblt_rate`/`crnt_rate`) + 기타 2(`ebitda`/`ev_ebitda`) + `raw JSONB` + `refreshed_at TIMESTAMPTZ`. 마법공식(EV/EBITDA·ROC) + F-Score-7(`src/engine/quant_score.py`) 원천
- CRUD(`stock_master_daily.py` 미러): `upsert_financial_batch(ticker, rows)`(100건 chunk + `ON CONFLICT (ticker, stac_yymm, div_cls) DO UPDATE SET` + graceful + KST `now_kst_iso`) · `get_financial_series(ticker, div_cls="0", limit=3)`(최근 N기, `stac_yymm` DESC, "0"=년 / "1"=분기) · `max_stac_yymm(ticker, div_cls="0")`(신선도·백필 게이트 키) · `count_all()`
- `pg`(asyncpg) 경유 + raw JSONB 덮어쓰기 금지(G-AST1)
- 호출자: `src/engine/scanner.py::_stock_master_financial_load_once()`(주1회 16:40 적재) + `src/engine/strategies/volatility_breakout.py::_apply_quant_filter_in_prepare()`(관찰 훅). 매매 hot path 무관

## pending_next_day_clear.py — 익일청산 큐 영속화

메모리 `_pending_next_day_clear: set[tuple]` 의 복구 원천이다 — 메모리만 두면 EC2 재기동이 큐를 통째로 잃는다(6/17 알테오젠·알지노믹스 15:20 강제청산 누락 사고).

- 테이블 `pending_next_day_clear`(migration 038). 복합 PK `(target_date DATE, ticker TEXT, strategy_id TEXT)` + `created_at TIMESTAMPTZ` + `reason VARCHAR(50) NOT NULL DEFAULT 'unknown'`(진단용)
- CRUD 4:
  - `save_pending_ndc(target_date, ticker, strategy_id, reason="unknown")` — 1행 UPSERT. 쓰는 곳 = `scheduler._execute_next_day_clear` 보류 3분기(`reason` = `nxt_not_tradable` · `nxt_open_missing` · `nxt_underthreshold`)
  - `delete_pending_ndc(target_date, ticker, strategy_id)` — `_drain_pending_next_day_clear` finally 에서 호출(없는 행은 no-op)
  - `load_pending_ndc(target_date) -> set[tuple[str, str]]` — 부팅(`boot_manager.boot`)이 메모리 set 을 복구
  - `purge_pending_ndc_before(target_date) -> int` — `_reset_daily_state` 가 fire-and-forget 으로 호출
- ⚠️ `order_engine` 의 매도 시장가 거부 → NXT 폴백 실패 익일청산(`[next_day_clear_deferred] … reason=market_order_disallowed_nxt_fallback_fail`)은 메모리 set 에만 들어가고 이 테이블에 쓰지 않는다
- **DB 가 실패해도 메모리 상태를 보존한다** — 호출자가 try/except 로 흡수하고 `[pending_ndc_save_skip]` 등을 남긴다

## backtest_runs.py — 외부 MCP 백테스트 실행 이력

20:00 AI 자문 직후 활성 전략마다 2 kind(`current`|`recommended`) job 을 fire-and-forget 으로 띄운 기록이다.

| 함수 | 계약 |
|---|---|
| `insert_run(target_date, strategy_id, params_kind, params_snapshot) -> dict \| None` | `status="queued"` 로 1행. `params_kind` 는 `"current"`/`"recommended"` 뿐, 그 밖은 **`ValueError`**(조용한 흡수 금지). 🔴 **UNIQUE `(target_date, strategy_id, params_kind)` 충돌은 예외가 아니라 `None`** — 자문 사이클 재진입에 멱등하다 |
| `get_by_id(run_id)` · `list_by_date(target_date)` | 조회 |
| `update_status(run_id, status, *, mcp_job_id=None, error_message=None, metrics=None)` | `running`=mcp_job_id 부여 / `completed`=metrics + `completed_at` / `failed`=error_message + `completed_at` / `skipped`=로컬 백테스트 실행기 없음, `completed_at` 기록. 허용 status = `queued`·`running`·`completed`·`failed`·`skipped`, 그 밖은 `ValueError` |

`target_date` 는 DATE 라 `_kst.to_date()` 로 강제 변환한다(str 입력도 받는다).

## market_regime_snapshots.py — 매크로 레짐 일일 스냅샷 (출처 = 자체 `macro` 컨테이너)

`_boot()` 시점에 1행. 매크로 레짐은 **관찰 지표**라 매수를 차단하지 않는다 — `buy_blocked` 컬럼은 그날 판정의 기록이지 게이트가 아니다.

| 함수 | 계약 |
|---|---|
| `insert_snapshot(snapshot_date, regime, regime_desc, cycle_phase, vix, fear_greed_score, buffett_ratio, raw_response, computed_cash_usage_ratio, buy_blocked, block_reason) -> dict \| None` | 🔴 **같은 `snapshot_date` 가 있으면 예외가 아니라 `None`**(graceful) — 하루 두 번 부팅해도 첫 기록이 이긴다 |
| `get_by_date(snapshot_date)` · `get_latest()` · `list_recent(days=30)` | 조회. `list_recent` 가 `GET /api/market-regime/history` 의 소스 |

`raw_response` JSONB 는 외부 응답 **원문**이다 — 정규화해서 넣지 않는다(외부 스키마가 바뀐 날 무엇이 왔는지 되짚을 유일한 기록).

## parameter_recommendations.py — 전략수정 AI자문 이력

- `insert_recommendation()`: 20:00 자문 생성 시 INSERT(status: pending). `(target_date, strategy_id)` UNIQUE 충돌은 `None`
- `list_recommendations(days=30)`: 최근 N일 이력(신규 + 처리 통합) · `get_recommendation(id)`: 단일 상세 · `list_pending_by_date(target_date)`: 그 영업일의 pending 목록
- `update_recommendation_status(id, status, applied_params=..., applied_weight=...)`: status 갱신 + `applied_at`/`rejected_at` 자동 기록. 페이로드는 applied/partial 상태에서만 포함
- `expire_pending_before(target_date)`: 이전 pending 자동 만료
- `update_backtest_summary(...)` / `list_recommendations_pending_backtest(target_date)`: 외부 MCP 백테스트 결과를 `backtest_summary` JSONB 에 붙이는 경로
- 컬럼: `recommended_weight` NUMERIC nullable / `code_review_notes` TEXT nullable(≤2000자) / `applied_weight` NUMERIC nullable / `weight_reasoning` TEXT nullable(≤1000자) / `backtest_summary` JSONB. INSERT 시점 `applied_weight` 는 `None` 이고 apply 라우트가 사용자 명시 토글일 때만 채운다
- `status` = pending → applied / partial / rejected / expired / applied_auto. `applied_auto`(migration 028)는 AI 자문 **자동** 적용 전용 — 운영자 수동 `applied` 와 분리해 추적한다

## supabase.py — 롤백용 병존 파일

어느 모듈도 import 하지 않는다. 🔴 **새 코드에서 `supabase.table()` 이나 `asyncio.to_thread` DB 위임을 쓰지 않는다** — DB I/O 는 `pg.py`(asyncpg) 직행이 정본이다. 확인 = `grep supabase.table src/`(`supabase.py` 자신을 빼면 0건).

## DB 스키마

- 마이그레이션 = `supabase/migrations/NNN_*.sql`(디렉터리명은 `supabase/` 유지 — 스키마 SQL 정본, RDS 에 순차 적용). 테이블별 계약은 위 모듈 절이 정본이다.
- `trade_history.status` CHECK = `PENDING`/`COMPLETED`/`PARTIAL`/`CANCELLED`(PENDING → COMPLETED / PARTIAL → CANCELLED) · `trade_type` CHECK = `BUY`/`SELL`(migration 001). status 값을 바꾸면 CHECK 제약도 새 migration 으로 함께 고친다.
- `stock_master_history`(migration 032·036, 전용 모듈 없음 — `stock_master.list_history` 가 읽는다): `stock_master` 의 INSERT/UPDATE/DELETE 트리거가 쓰는 직전본 표. PK `(ticker, seq)` — `seq` 0=최신본·1=직전본. UPDATE 는 `raw` 가 바뀔 때만 기록하고, DELETE 는 그 종목 행을 지운다.

## TIMESTAMPTZ 계약

모든 시각 컬럼은 `TIMESTAMPTZ` 다 — **절대 시점(instant)을 저장**하고 timezone 은 분리된다. UTC 로 들어간 옛 행과 KST 행은 **같은 시점**이라 결함이 아니고 백필도 필요 없다. 🔴 ***"UTC 저장 = 결함"* 이라는 가정이 나오면 이 절을 인용해 차단한다.**

규약은 표시 형식(SQL `to_char(...,'+09:00')` — 「asyncpg 계약 패턴」 절)과 **비교 경계** 둘뿐이다. 조회 경계 문자열에는 `+09:00` 을 명시한다(`get_trades_in_range` / `get_logs` / `_fetch_logs_in_range` / `trade_history._today_kst_iso()` 를 쓰는 당일 조회 — `boot_manager` 전용 3함수 포함) — 빠뜨리면 UTC 로 해석돼 KST 00:00~09:00 이 잘린다. 풀 세션 timezone = 「pg.py」 절.
