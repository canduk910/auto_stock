# CLAUDE.md — src/db/ (AWS RDS PostgreSQL + asyncpg)

> 이력: [`docs/history/src-db-CLAUDE.history.md`](../../docs/history/src-db-CLAUDE.history.md)

AWS RDS PostgreSQL CRUD 모듈. DB 클라이언트 정본 = **`pg.py` (asyncpg 네이티브 async)**.
`supabase.py` 는 롤백용으로만 남아 있고 어느 db 모듈도 참조하지 않는다.

> 사이클별 변경 이력: `docs/HARNESS_CHANGELOG.md`

## pg.py — asyncpg 연결 풀 + 쿼리 헬퍼 (DB 클라이언트 정본)

- `settings.database_url`(asyncpg DSN, `?sslmode=require`) 로 `init_pool()` 이 전역 풀을 만든다 (`min_size=2` / `max_size=10` / `max_inactive_connection_lifetime=300` / `command_timeout=30`). `main.py` lifespan 시작에 `init_pool()`, 종료에 `close_pool()` 을 1회씩 부른다.
- **`_init_conn(conn)`** — 신규 물리 연결마다 도는 init 훅. JSONB/JSON codec 등록 (`set_type_codec(encoder=json.dumps, decoder=json.loads)`) 으로 asyncpg 기본 `str` 반환을 dict 왕복으로 강제한다. **⚠️ codec 이 빠지면 `system_config.get_cash_usage_ratio` 처럼 `isinstance(raw, dict)` 를 기대하는 코드가 전부 silent 폴백한다 — 매매 파라미터가 조용히 기본값으로 돈다.**
- **KST 타임존은 `init_pool()` 의 `server_settings={"timezone": "Asia/Seoul"}`(연결 핸드셰이크 파라미터)로 지정한다.** `init=` 훅 안의 `SET TIME ZONE`(세션 레벨)로 쓰면 안 된다 — 풀이 release 때 RESET 해 UTC 로 되돌아가고, 그 상태에서 `to_char(..., '+09:00')` 가 UTC 를 렌더해 KST 날짜가 하루 밀린다(M2a 통합 검증에서 실제로 걸린 결함이다).
- 헬퍼: `fetch(sql, *args) -> list[dict]` / `fetchrow(sql, *args) -> dict | None` / `fetchval(sql, *args)`(스칼라) / `execute(sql, *args) -> str` / `executemany(sql, args_list)`. SQL 은 `$1`/`$2` 위치 파라미터를 쓴다.
- **`_with_retry(coro_factory, *, op="")`** — 연결 계열 예외를 1회 재시도한다. `_RETRY_EXCEPTIONS = (asyncpg.PostgresConnectionError, asyncpg.InterfaceError, asyncpg.exceptions.ConnectionDoesNotExistError, asyncio.TimeoutError)`, 시도 사이 `_RETRY_BACKOFF_SECS = 0.2` backoff, 소진하면 마지막 예외를 raise 한다(호출자의 graceful 분기를 보존한다). 로그는 `logger.warning("[pg_retry] op=…")` 단독이고 `write_log` 는 부르지 않는다(사이클 72 이중 INSERT 차단). **read 전용** — `fetch`/`fetchrow`/`fetchval` 만 경유하고 쓰기(`execute`/`executemany`)는 멱등이 보장되지 않아 경유하지 않는다.
- ⚠️ **테스트에서 `freeze_time` 안으로 DB read 를 태우지 않는다** — retry 의 `asyncio.sleep(0.2)` 이 동결된 `time.monotonic` 과 만나 hang 한다. read 를 mock 하거나 freeze 밖에서 읽는다.

## asyncpg 계약 패턴

전 db 모듈이 지키는 바인딩·렌더 계약. 신규 CRUD 를 쓸 때 의무다.

- **JSONB** — codec(`_init_conn`) 이 dict/list 를 왕복 처리한다. **raw dict/list 를 그대로 바인딩**한다(호출부에서 `json.dumps` 를 먼저 걸면 이중 인코딩이다). 읽기도 codec 이 dict 로 복원한다.
- **TIMESTAMPTZ** — 쓰기는 `datetime.fromisoformat(now_kst_iso())`(aware datetime 바인딩). ISO 문자열로 돌려줘야 하는 조회는 SQL 에서 `to_char(t.<컬럼>, 'YYYY-MM-DD"T"HH24:MI:SS.US+09:00')` 로 KST 렌더한다.
- **DATE** — `src/db/_kst.py::to_date(x)` 로 강제 변환한 뒤 바인딩한다. asyncpg 는 DATE 컬럼에 Python `date` 객체를 요구하고 str 을 넘기면 `'str' object has no attribute 'toordinal'` 로 즉시 실패한다.
- **NUMERIC** — asyncpg 가 `Decimal` 로 반환한다(손익 정밀도 보존 — `get_trade_pairs` 등).
- **목록 필터** — `WHERE col = ANY($1::text[])`.
- **건수** — 데이터 쿼리와 분리된 `SELECT count(*)` fetchval.

## _kst.py — KST 공용 헬퍼

- `KST = timezone(timedelta(hours=9))` — KST aware tzinfo 단일 진입점
- `now_kst_iso() -> str` — `datetime.now(KST).isoformat()`. DB INSERT/UPSERT payload 의 시각 컬럼(`created_at` / `updated_at` / `refreshed_at` / `completed_at` / `timestamp` 등) 의무 사용
- `today_kst() -> date` — `datetime.now(KST).date()`. 서버 timezone 에 기대는 `date.today()` 를 쓰지 않기 위한 단일 진입점
- **`to_date(x: date|datetime|str|None) -> date|None`** — DATE 컬럼 바인딩 값을 `date` 로 강제 변환(never-raise). `date`/`datetime`→`.date()`, `str`→`date.fromisoformat`(실패하면 앞 10자 슬라이스로 재시도 = 타임스탬프 ISO 문자열 호환), `None`→`None`(호출자 graceful 분기 보존), 파싱 실패→`None` + `logger.warning`. **DATE 컬럼을 쓰는 모듈이 바인딩 지점을 `to_date(...)` 로 감싸는 것은 호출자 책임이다.**
- 🔴 **DB 시각 컬럼에 `datetime.utcnow()` · `date.today()` · `src/db/` payload 의 `datetime.now(timezone.utc)` 를 쓰지 않는다** — AST 영구 가드 `tests/unit/db/test_cycle68_*.py`. 예외는 `system_logs.py` 와 `main.py` 의 인라인 `datetime.now(KST).isoformat()` 둘뿐이고 행위는 헬퍼와 같다.

## trade_history.py — 거래 내역

- `insert_trade(record)`: 주문 시 INSERT (status: PENDING)
- **`update_trade_status(ticker, trade_type, status, strategy="momentum", price=None, profit_loss=None, *, order_no=None, match_partial=False) -> int`**: 진행 중 거래 행의 status 를 갱신하고 영향 행 수를 돌려준다. 0건이면 호출자(OrderEngine)가 체결통보 선행 race 로 판단해 COMPLETED 보정 INSERT 를 한다.
  - `match_partial=True`(opt-in) 면 `status = ANY(...)` 로 PENDING ∪ PARTIAL 을 함께 잡는다. **기본을 넓히지 않는다** — 넓히면 `_cancel_after_wait`/`_cancel_and_reorder` 의 CANCELLED 호출까지 함께 넓어져 부분 체결 사실이 정산·sync 양쪽에서 사라진다. 이 인자를 넘기는 호출부는 COMPLETED 2곳뿐이고 AST 가 봉인한다.
  - 같은 인자가 `AND timestamp >= (KST 오늘 00:00)` 하한도 켠다. 하한은 **`datetime` 바인딩**이다(str 로 바인딩하면 실 PG 에서 `DataError` 가 나 매수·매도 체결 경로가 전건 예외다 — AST5 가 바인딩 타입을 잰다).
  - `order_no`(keyword-only, 기본 `None`)를 넘기면 WHERE 에 `AND order_no = $n` 이 붙어 그 주문 행으로 좁혀진다(빈 문자열도 필터로 취급). **order_engine 호출 6곳은 전부 넘긴다** — 넘기지 않으면 같은 `(ticker, trade_type, strategy)` 의 다른 `order_no` 행까지 함께 덮는다(필옵틱스 161580 사건의 원인).
  - `affected > 1` 이면 `[trade_status_multi_update]` WARNING 1행. 부분 UNIQUE 인덱스 때문에 `order_no` 를 넘긴 호출은 구조적으로 발화할 수 없다 — 이 마커는 과거를 재는 측정기가 아니라 WHERE·인덱스가 뒤로 물러나는 것을 잡는 감시자다.
- **`get_trades_in_range(start_date, end_date, strategy=None)`**: `[start_date, end_date]` KST inclusive 조회. 경계는 `f"{date}T00:00:00+09:00"` / `f"{date}T23:59:59.999999+09:00"` 로 **`+09:00` 을 반드시 명시**한다 — TZ 가 없으면 UTC 로 해석돼 KST 00:00~09:00 거래가 통째로 빠진다. `recommendation_engine` 과 `log_analysis_engine` 이 공유한다.
- `get_trades(limit=50, offset=0, ticker=None, strategy=None) -> (list[dict], int)`: 페이징 조회 + 전체 건수
- `get_trade_pairs(strategy=None, ticker=None)`: 매매손익 뷰용 매수/매도 페어. 같은 `(ticker, strategy)` 그룹을 timestamp ASC 로 훑어 누적 보유수량이 0 으로 돌아올 때마다 closed 페어를 emit 하고(매수가·매도가는 가중평균, Decimal 보존), 잔여 보유는 open 페어로 emit 한다(미실현 손익은 `scanner.ticker_prices` 폴백, 시세 미수신이면 None). 응답 키 = buy_date / buy_time / sell_date / sell_time / ticker / ticker_name / buy_price / buy_qty / sell_price / sell_qty / profit_loss / profit_rate / status('closed'|'open') / strategy **+ `buy_order_nos: list[str]` / `sell_order_nos: list[str]` / `pair_key: str|None`**. `pair_key` 는 `strategy:ticker:첫 매수 order_no` 다 — 페어는 어디에도 저장되지 않으므로 그 사이클을 가리키는 유일한 안정 식별자다. **단수 필드는 불가하다**(운영 DB 실측에서 한 페어가 매수 주문 2건 이상인 사례가 9건). 빈 `order_no` 체결은 목록에서만 빠지고 행 자체는 그대로 만든다 → `pair_key=None` 이면 UI 버튼이 비활성이다. 시각은 `_to_kst()` 헬퍼가 ISO(UTC/KST/tz-naive 전부)를 `astimezone(KST).strftime()` 으로 명시 변환한다.
- `get_today_buy_trades / get_today_sell_trades / get_today_pending_buys`: 당일 조회. 기준점은 `f"{today}T00:00:00+09:00"` KST 명시. **ticker 별 dedupe 가 걸려 있다 — 포지션 복구용이라 최신 1건만 돌려준다.**
- **`get_today_buy_trades_for_sync(ticker=None) / get_today_sell_trades_for_sync(ticker=None)`**: **dedupe 없음** + CANCELLED 제외 + optional ticker 필터. `_sync_orders_to_db` 의 중복 판정 키 소스 전용이다. 🔴 **포지션 복구용 dedupe 함수를 sync 중복 판정에 재사용 금지 — 5/20 042700 핑퐁 INSERT 사고**(같은 ticker 의 다른 `order_no` 가 가려져 매 재기동마다 신규로 판정됐다).
- `mark_pending_buys_completed(ticker)` / `get_recent_buy_strategy(ticker) -> str|None` / `get_today_buys_ticker_strategy() -> list[dict]`: `boot_manager` 전용. 당일 조회는 `+09:00` 을 명시한다.
- **DB 부분 UNIQUE 인덱스** (migration 029): `uq_trade_history_ticker_order_no_type ON (ticker, order_no, trade_type) WHERE order_no IS NOT NULL AND order_no != ''`. 코드가 회귀하면 PG 가 INSERT 를 거부한다. NULL/빈 `order_no`(수동 매매 사전 등)는 인덱스 밖이다.

## llm_buy_evaluations.py — AI 매수평가 기록

- 테이블 `llm_buy_evaluations` (migration 043, 53열). **PK `(trade_date, account_no, ticker, order_no)`** — KIS ODNO 는 **하루 단위로만** 유일하므로 날짜가 PK 선두여야 하고, `trade_history` 조인도 `(trade_date, ticker, order_no)` **3축**이어야 안전하다. 인덱스 4 = `(trade_date)` · `(strategy_id, trade_date)` · `(ticker, trade_date)` · `(order_no)`.
- `upsert_evaluation(**kw) -> dict|None`: **주문 1건 = 평가 1행**(성공·실패 모두). 같은 PK 재기록은 UPDATE 이고 `created_at` 은 보존한다. 실패 행도 `input_payload` 를 담고 `score`/`would_block` 은 **NULL** 이다(0 위장 금지 — 점수 분포가 0 근처로 왜곡된다). 호출자는 leaf `engine/llm_buy_gate._persist_evaluation` 하나뿐이다.
- `get_by_order(order_no, *, trade_date=None)`: 날짜를 주면 좁히고, 없으면 **가장 최근 1행**.
- `list_by_order_nos([...], *, trade_date=None)`: 존재하는 **`(trade_date, order_no)` 쌍 전부**를 `trade_date DESC` 로 돌려준다(빈 목록은 **쿼리 없이** `[]` — 빈 배치가 전체 스캔이 되지 않게). 🔴 **주문번호당 1행으로 접지 않는다** — ODNO 가 하루 단위로만 유일해서 접으면 오래된 날짜의 평가가 응답에서 사라지고, 그 날짜의 거래 행은 버튼이 비활성인데 상세 조회(`get_by_order(..., trade_date=…)`)로는 멀쩡히 읽히는 비대칭이 생긴다. 접는 일은 이 층이 하지 않고 라우트가 `"<trade_date>|<order_no>"` 복합 키로 대조한다.
- **타입 강제는 호출자에게 맡기지 않는다**: DATE = `_kst.to_date()`, TIMESTAMPTZ = `_to_dt()` 가 aware `datetime` 으로 강제(ISO **문자열도 변환**하고 미지 타입은 `TypeError`), JSONB 4열(`key_risks`/`invalidations`/`input_payload`/`raw_response`)은 **raw dict/list** 바인딩(`json.dumps` 금지), NUMERIC = `Decimal`(라우트가 `float` 로 사영한다). 시각 문자열 열은 **`signal_time_local`** 이다 — 값의 원천이 6전략 `datetime.now()`(tz 인자 없음)·kojiro `datetime.now(KST)` 라 컨테이너 `TZ=Asia/Seoul` 전제에서만 KST 와 같고 값 자체는 KST 를 보장하지 않는다. 실 PG 왕복 가드 = `tests/integration/test_cycle276_llm_eval_pg_roundtrip.py`(mock 은 str 바인딩을 통과시키고 실 PG 만 `DataError` 를 낸다).
- **이 모듈은 예외를 전파한다** — 기록 실패의 침묵은 leaf 의 `[llm_eval_persist] result=error` 가 깨고, 조회 실패의 침묵은 라우트의 500 이 깬다. 여기서 `except Exception: return None` 을 하면 그 두 채널이 동시에 막힌다.
- 회고 층화 열 = `prompt_version`/`feature_version`(프롬프트·지표가 바뀐 전후 행을 **섞어서 회귀 금지**) · `budget_total_won`/`budget_remaining_after_won`/`open_positions_n`(차단의 반사실은 "손익이 사라진다" 가 아니라 "다른 종목 매수로 대체된다") · `raw_response`(파싱 전 원문 — 다른 파서로 재해석 가능) · `input_payload`(`build_messages` 3인자 전체, 요약·절단 금지 = 오프라인 재채점의 유일한 다리). 분석 시 `trade_history.status` 로 **체결/부분체결/미체결/취소 4분류를 반드시 분리**한다(미체결을 손익 0 으로 섞으면 통째로 오염된다).

## positions.py — 보유 포지션 영속화

매매 hot path 의 영속 계층이다. 재시작이 보유 상태를 잃으면 손절이 통째로 사라지므로,
`positions` 테이블이 메모리 `scheduler.positions` 의 복구 원천이다.

| 함수 | 계약 |
|---|---|
| `save_position(ticker, ticker_name, buy_price, quantity, order_no, strategy_id, buy_date, high_since_buy=0)` | `ON CONFLICT (ticker) DO UPDATE` upsert. **ticker 가 PK** = 한 종목은 한 포지션. `high_since_buy` 가 0·미지정이면 `buy_price` 로 채운다(트레일링 고점의 하한이 매수가라는 계약 — 0 으로 남기면 첫 틱에 고점이 0 에서 출발해 트레일링이 즉시 발동한다) |
| `delete_position(ticker)` | 청산 완료 시 1행 삭제 |
| `load_all() -> list[dict]` | 부팅 복구용 전량 조회 |
| `update_high(ticker, high)` | 트레일링 고점 갱신 |
| `clear_all()` | 전량 삭제 — **운영 복구용**이지 일상 경로가 아니다 |

`buy_date` 는 DATE 라 `_kst.to_date()` 계약을 따른다(익일 청산 판정의 기준일).

## strategy_config.py — 전략 설정 (`strategy_id` PK, `params` JSONB)

🔴 **비중 단위는 비율 `0.0~1.0` 이다** — 값 크기로 단위를 추측하는 분기를 어느 계층에도 두지 않는다
(루트 `CLAUDE.md` 「비중 단위 추론 변환 금지」). 로그 문자열의 `weight * 100` 은 표시 전용이다.

| 함수 | 계약 |
|---|---|
| `load_all() -> dict[str, dict]` | `{strategy_id: {"enabled", "weight", "params"}}`. `params` 가 dict 가 아니면 `{}` 로 방어(JSONB 오염이 전략 부팅을 죽이지 않게) |
| `save(strategy_id, enabled, weight, params)` | `ON CONFLICT (strategy_id) DO UPDATE` upsert. `updated_at` 은 `datetime.fromisoformat(now_kst_iso())` — **str 바인딩 불가**(KST 문자열 계약은 보존하고 바인딩 직전에만 변환) |
| `save_weights(weights)` | 비중만 갱신. 종목별로 **기존 `params` 를 먼저 읽어** 그대로 다시 넣는다(안 그러면 `params` 가 통째로 지워진다). `enabled = weight > 0` 을 함께 정한다 |
| `save_params(strategy_id, params)` | `params` JSONB 만 갱신 |

⚠️ **이 테이블에 쓴 값은 다음 백엔드 재시작에서만 전략 객체에 반영된다** —
`_load_strategy_config` 의 `_config_loaded` 가 프로세스당 1회이고 `_boot` 재호출은 no-op 이다.
장중 즉시 반영이 필요하면 `PUT /api/strategies/{id}/params`(라우트가 in-memory `config.params` 를 덮는다)를
쓴다. cycle232 D6 가 보유 중 장중 재시작을 금지하므로 **장중 실효 수단은 PUT 뿐**이다.

## daily_performance.py — 일일 실적

- **`upsert_daily_performance(target_date, total_asset, daily_profit_rate, strategy="total", *, net_external_cashflow=0.0, daily_realized_pnl=0.0, deposit=0.0, cumulative_return_rate=0.0)`**: **21:30 정산**(`scheduler.TIME_SETTLEMENT`) 때 당일 실적을 기록한다. `daily_realized_pnl`/`daily_profit_rate` 는 **실현손익 기준**이다(SELL 매도 실현분만 합산). 매도가 0건이면 둘 다 0 이 정상이고 평가손익은 `BalanceTable.eval_profit_loss` 가 따로 보여 준다. 컬럼 = total_asset / daily_profit_rate / daily_realized_pnl / net_external_cashflow / deposit / cumulative_return_rate(TWR 복리, 실현손익 누적). `target_date` 는 DATE 라 `to_date()` 로 강제 변환한다.
- `get_performance(days=30, strategy="total")`: 최근 N일(날짜 오름차순)
- `get_latest_performance(strategy="total")`: 가장 최근 영업일 1행 — TWR 누적·Δ예수금 baseline
- `recompute_from_trades()`: PostgreSQL 함수 `recompute_daily_performance()` RPC 호출 — `trade_history` 기반 일괄 재계산(멱등). `_settle()` 끝에서 자동 호출된다. `daily_profit_rate` 의 분모는 직전 영업일이 아니라 **가장 가까운 0이 아닌 이전 영업일 `total_asset`** 이다(correlated subquery).

## system_logs.py — 시스템 로그

- **`write_log(level, message)`**: 이벤트·에러 기록(INFO / WARNING / ERROR / CRITICAL). **never-raise** — 어떤 예외도 호출자에 전파하지 않고 실패는 `logger.debug("[write_log_failed] …")` 단독이다. 🔴 **실패 로그를 WARNING 이상으로 올리지 않는다** — `_DbLogHandler` 가 그 로그를 다시 DB INSERT 로 태워 재귀한다. AST 가드 `tests/unit/ast/test_cycle190_ast_write_log_guard.py`(broad except + except 안 raise 0 + debug 단독).
- INSERT 페이로드의 `timestamp` 는 `datetime.now(KST).isoformat()` 으로 강제한다(DB default `now()` 에 기대지 않는다). 표준 logging 을 타고 오는 `_DbLogHandler` 경로(`src/main.py::_insert_log_to_db`)도 같은 KST 강제를 거친다 — 호출 빈도는 이쪽이 더 높다. AST 영구 가드 `tests/unit/db/test_system_logs_kst_timestamp.py` 2 케이스(`src/` 전체 rglob INSERT 호출처 + `write_log` 함수 단위).
- 🔴 **같은 사이트에서 `logger.*` 와 `write_log` 를 함께 부르지 않는다** — `_DbLogHandler` 가 `record.name.startswith("src.")` 인 emit 을 이미 `system_logs` 에 적으므로 둘을 함께 부르면 이중 INSERT 다(운영 실측 평균 2.89배). AST 가드 `tests/unit/ast/test_cycle72_ast_no_logger_write_log_pair.py` 가 `write_log` 호출 ±5줄의 `logger.*` 동시 호출을 0건으로 묶는다.
- `_DbLogHandler` 는 동일 메시지 500ms dedupe 캐시를 둔다(`_DEDUPE_TTL_SECS = 0.5` + `_dedupe_cache: dict[str, float]`, `time.monotonic` 비교, lazy evict 100 항목 cap). 미래에 새로 생길 emit 사이트의 silent 이중 INSERT 에 대한 runtime 안전망이다.
- **`safe_write_log(level, message, *, fallback_debug=None)`**: `write_log` 의 graceful 변형. 예외를 전파하지 않고 `logger.debug` 만 남긴다. `fallback_debug` 를 주면 그 문자열을, 없으면 `"[safe_write_log] {message[:80]} 실패: level={level}"` 을 쓴다. `order_engine.py` 의 동형 패턴 4곳(`[stock_master_miss]` / `[stock_master_miss stale]` / `[market_closed_blocked]` / `[positions_reconciliation]`)이 공유한다.
- `get_logs(limit=100, log_level=None, *, from_date=None, to_date=None, page=1, size=None)`: 페이징 + KST 기간 필터. 반환 `{"items": list[dict], "total": int, "total_pages": int}`. `size` 미지정 시 `limit` 을 흡수한다(하위 호환). `from_date`/`to_date` 를 주면 `timestamp >= "{date}T00:00:00+09:00"` / `<= "{date}T23:59:59.999999+09:00"` 로 KST 를 강제한다. `total` 은 별도 `SELECT count(*)` fetchval 이고 `total_pages = ceil(total / size)`.
- **`search_logs(q, *, level=None, start=None, end=None, limit=200) -> {logs, total, has_more}`**: `message ILIKE '%q%'` 키워드 검색(대소문자 무시). `level` 이 None 또는 `"ALL"` 이면 무필터, 그 밖이면 `log_level` 등가 필터. `start`/`end` 는 ISO 8601 시각을 받아 `>=`/`<=` 로 건다. `limit` 은 1~1000 clamp(기본 200). 빈 `q` 는 `ValueError`. `has_more = total > len(logs)` — UI 가 "키워드 좁히기" 를 안내하는 근거다. 라우트 `/api/logs/search` 와 1:1.
- **`purge_old_logs() -> {info_deleted, high_deleted, elapsed_ms}`**: 등급별 retention 자동 정리. INFO 는 2일, WARNING/ERROR/CRITICAL 은 30일 지난 행을 지운다.
  - 내부 헬퍼 `_purge_by_cutoff(cutoff_iso, level_filter)` 는 `cutoff_iso=None` 이면 `RuntimeError("cutoff must not be None")` 를 raise 한다 — **WHERE 누락 삭제 절대 차단**이다.
  - 삭제는 `PURGE_SELECT_BATCH` 씩 골라 지우기를 drained 까지 **루프**한다(빈 결과 또는 마지막 페이지에서 종료). 안전 cap 3중 = `PURGE_MAX_ITERATIONS` 런어웨이 차단 + `MAX_PURGE_BATCH` 누적 상한 + 마지막 페이지 조기 종료.
  - 시점은 `_settle` 의 로그 분석 **뒤**, `_reset_daily_state()` **앞**이다(분석이 `system_logs` 를 읽은 다음에 정리한다). 예외는 scheduler 가 `[log_retention_skip]` INFO 로 graceful 처리하고 다음 사이클에 재시도한다. 결과 1행 = `[log_retention] info_deleted=N high_deleted=M elapsed_ms=K`.
- 상수: `INFO_RETENTION_DAYS=2` / `HIGH_RETENTION_DAYS=30` / `HIGH_LEVELS=("WARNING","ERROR","CRITICAL")` / `MAX_PURGE_BATCH=100_000` / `PURGE_SELECT_BATCH=1000` / `PURGE_MAX_ITERATIONS=2000` / `SEARCH_DEFAULT_LIMIT=200` / `SEARCH_MAX_LIMIT=1000`

## log_reports.py — 일일 로그 분석 리포트

- `insert_log_report()`: `INSERT … ON CONFLICT (target_date) DO UPDATE SET` upsert(cycle283 D6). 🔴 **SET 절은 base 9컬럼만**(summary / findings / metrics / model + 토큰 5) — `ext_*` 6컬럼과 `created_at` 은 **절대 넣지 않는다**. 한 컬럼이라도 새면 20:20 클라우드 루틴 결과가 조용히 지워진다. `upsert_external_report` 의 SET 절(`ext_*` 6)과 **교집합이 공집합**이라 어느 순서로 써도 서로를 보존한다.
  - 호출 주체 2개 — 20:05 1차 스냅샷(`daily_metrics_snapshot`, model·토큰 NULL)과 21:30 완전판(`generate_daily_log_report`)이 같은 행을 쓴다.
  - `on_conflict="nothing"` 은 비파괴 모드(기존 행이 있으면 손대지 않고 `None`)이고 **프로덕션 호출자가 0건**이다 — 오용 방어용 파라미터다. `POST /api/log-reports/run` 의 비파괴는 **라우트 선조회 가드**가 혼자 담당한다(`_is_complete_report` = `metrics.snapshot_pass` 아님 ∧ `summary` 가 비지 않음 ∧ OpenAI 실패 placeholder 아님 ∧ `model` 채워짐). 라우트가 `"nothing"` 을 쓰지 않는 이유 = 20:05~21:30 에는 1차 스냅샷 행이 이미 있어 `DO NOTHING` 이면 수동 복구의 완전판이 조용히 버려진다.
  - 키워드 인자 = `target_date` / `summary` / `findings` / `metrics` / `model` + `input_tokens` / `output_tokens` / `total_tokens` / `latency_ms` / `cost_estimate_usd`(기본 전부 `None` = NULL). `cost_estimate_usd` 는 `Decimal | None` 이고 저장 직전 `float` 로 변환한다.
- **`upsert_external_report(*, target_date, provider, model, summary, findings, report_md) -> dict`**: 20:20 KST 클라우드 루틴 결과를 `ext_*` 6컬럼에만 저장한다. `DO UPDATE SET` 절이 **`ext_provider`/`ext_model`/`ext_summary`/`ext_findings`/`ext_report_md`/`ext_created_at` 6개뿐**이고 base 컬럼은 **절대 SET 절에 넣지 않는다**. 행이 없는 날의 INSERT 경로는 base 컬럼을 하드코드 SQL 리터럴(`''`/`'[]'::jsonb`/`'{}'::jsonb`/`NULL`)로 채워 호출자 데이터가 심길 여지를 원천 차단한다. DB 규약 준수 — JSONB raw list 바인딩 + `::jsonb` 캐스트, DATE `to_date()`, TIMESTAMPTZ `datetime.fromisoformat(now_kst_iso())`.
- `list_log_reports(days=30)`: 최근 N일 신규순 (`SELECT *` — `ext_*` 6컬럼 자동 포함)
- `get_log_report(target_date)`: 단일 영업일 (`SELECT *` — 동일)
- 스키마: id(uuid) / target_date(unique) / summary(text) / findings(jsonb 배열) / metrics(jsonb) / model(varchar) / created_at / **input_tokens(int, NULL)** / **output_tokens(int, NULL)** / **total_tokens(int, NULL)** / **latency_ms(int, NULL)** / **cost_estimate_usd(decimal(10,6), NULL)** (migration 031) / **ext_provider(text, NULL)** / **ext_model(text, NULL)** / **ext_summary(text, NULL)** / **ext_findings(jsonb, NULL)** / **ext_report_md(text, NULL)** / **ext_created_at(timestamptz, NULL)** (migration 042)

## system_config.py — 시스템 설정 키-값 헬퍼

- 저장 형태 = `system_config(key, value JSONB)`. 내부 헬퍼 `_select_value(key)`(`pg.fetch` 직행, 0건이면 `_MISSING` sentinel) / `_upsert_value(key, value)`(`ON CONFLICT (key) DO UPDATE`, `updated_at` 은 `datetime.fromisoformat(now_kst_iso())`). read 는 `pg.fetch`/`fetchrow`/`fetchval` 이라 `_with_retry` 를 내장하고, 쓰기는 `pg.execute` 라 경유하지 않는다.
- 범위 밖 입력은 `ValueError` 다.

**시세 채널 전환 다이얼** (전부 `system_config` 축 — 전략 `DEFAULT_PARAMS`·`param_catalog` **편입 금지**):

- **`get_tick_channel_resolver_mode() -> str | None` / `set_tick_channel_resolver_mode(mode)`** — 키 `tick_channel_resolver_mode`, 시세 채널 리졸버 킬스위치의 **DB 정본**(`off`/`observe`/`enforce_low`/`enforce`). `_get_string_or_none` 경유 = **캐시 0 · TTL 0**(`pg.fetch` 직행) — 캐시를 붙이면 장중 킬스위치가 그만큼 늦어진다.
- **전환 다이얼 4키** — `get_tick_channel_switch_enabled()` / `set_tick_channel_switch_enabled(enabled)`(`tick_channel_switch_enabled`, bool — **살아 있는 구독의 전환만** 끈다) · `get_tick_channel_switch_offset_secs()`(`tick_channel_switch_offset_secs`, float — 프리장 종료 뒤 전환까지) · `get_tick_channel_switch_ack_timeout_secs()`(`tick_channel_switch_ack_timeout_secs`, float — HIGH make-before-break ACK 대기) · `get_tick_channel_revert_probe_secs()`(`tick_channel_revert_probe_secs`, float — 자동 원복 측정 시점, 기본값은 새 숫자가 아니라 `stale_diagnostics.SUBSCRIBE_GRACE_SECS` 재사용이고 그 상수의 단일 정의처는 거기다). 클램프는 읽는 쪽이 한다.
- 다섯 키 모두 **캐시 0 · TTL 0** 이고 **키 부재·조회 실패는 `None`** 이다 → 엔진이 **현재 값을 유지**한다(기본값으로 되돌리지 않는다). 소비 = `engine/tick_channel_mode.refresh_mode()` / `refresh_switch_params()`(5분·120초 폴링) + `PUT /api/realtime/tick-channel-mode`(즉시 반영, 선택 필드 `switch_enabled`).
- 🔴 **`tick_channel_gap_hold_enabled` 는 소비처가 없는 폐기 키다(cycle295)** — getter/setter 도 함께 삭제됐다. 운영 DB 에 값 `false` 가 남아 있다(읽는 코드가 없어 지우지 않았다 — DELETE 는 되돌리기 어려운 운영 조치라 승인 대상이고 얻는 것이 0행이다). ⚠️ **이 키 이름을 재사용하지 않는다** — 같은 이름을 반대 의미로 되살리면 저장된 `false` 가 조용히 적용된다.

**운영 토글·자금**:

- `get_auto_start() -> bool` / `set_auto_start(enabled)`: 키 `auto_start`, JSONB `{"value": bool}`. 소비 = `main.py` lifespan + `routes/strategies.py` auto-start 라우트
- `get_cash_usage_ratio() -> float` / `set_cash_usage_ratio(ratio)`: 키 `cash_usage_ratio`, JSONB `{"value": float}`. 범위 `[0.0, 1.0]`, 5% 단위 자동 보정, 기본 1.0
- `get_auto_regime_adjust() -> bool` / `set_auto_regime_adjust(value)`: 키 `auto_regime_adjust`, 기본 True
- `get_auto_apply_enabled() -> bool` / `set_auto_apply_enabled(value)`: 키 `auto_apply_enabled`, 기본 **False**(안전 우선 — 운영자가 명시로 켠 뒤에만 AI 자문 자동 적용이 돈다). `.env` 폴백 없음
- `get_etf_regime_enabled() -> bool` / `set_etf_regime_enabled(value)`: 키 `etf_regime_enabled`
- `get_account_risk_warn_pct() -> float` / `get_account_risk_block_pct() -> float | None`: 키 `account_risk_warn_pct` / `account_risk_block_pct`. 조회 실패는 기본값(warn) 또는 `None`(block) 으로 graceful
- `get_krx_open_api_config()` / `set_krx_open_api_config(...)`: 키 `krx_open_api_enabled` / `krx_open_api_base_url` / `krx_open_api_key`. 🔴 **끄기 전에 소비처를 전수 확인한다** — 2026-08-08 에 이 토글을 "무효 키" 로 오판해 끈 결과 주 소스 `scanner._full_universe_load_krx_primary` 가 폴백으로 밀려 `full_universe_load` 가 3,577→60종목으로 degrade 했다. 키 값은 자격이므로 응답·로그에 노출하지 않는다
- **외부 통합 토글 (DB 우선, `.env` 폴백)**: `get_dkstock_regime_enabled() -> bool | None` / `set_dkstock_regime_enabled(value)`(키 `dkstock_regime_enabled`) · `get_kis_mcp_enabled() -> bool | None` / `set_kis_mcp_enabled(value)`(키 `kis_mcp_enabled`). 기본값이 `None` 인 것이 `cash_usage_ratio`/`auto_regime_adjust` 와 다른 점이다 — 호출자가 `settings.*` 환경변수로 폴백한다(`.env` 호환 보존). 내부 헬퍼 `_get_bool_or_none(key)` / `_set_bool(key, value)` 가 JSONB `{"value": bool}` 과 과거 형식(직저장 bool, `'true'`/`'false'` 문자열)을 모두 흡수한다
- **task 신선도 마커**: `get_task_last_success(task_label) -> str | None`(키 `task_last_success_<label>`) / `set_task_last_success(task_label, iso_ts)`. 값은 KST ISO(`now_kst_iso()`). `task_loop_helper.run_periodic_task_loop` 의 `immediate_skip_if_fresh_hours` 게이트 전용이다 — 재시작 직후의 immediate run 이 N시간 안에 성공 마커가 있으면 건너뛴다(아침 프리마켓 burst 완화). **`get_task_last_success_bulk(task_labels) -> dict`** 은 같은 마커를 `key = ANY($1)` **단일 쿼리**로 묶는다(`GET /api/market-ops` 야간작업 타임라인이 폴링마다 라벨 수만큼 왕복하지 않게). 결측 라벨은 반환 dict 에 **키 자체가 없다**(빈 문자열이 아니다). 쿼리 실패는 빈 dict(fail-open)

**레짐 표시 설정 (매매가 소비하지 않는다)**:

- `get_buy_block_mode() -> str` / `set_buy_block_mode(mode)`: 키 `buy_block_mode`, 기본 `HARD`. 4 모드 밖은 `ValueError`
- `get_buy_block_thresholds() -> BuyBlockThresholds`(Pydantic) / `set_buy_block_thresholds(vix_threshold=, fg_high_threshold=, fg_low_threshold=, defensive_enabled=)` 부분 갱신. 4 키 = `buy_block_vix_threshold`(25.0) / `buy_block_fg_high_threshold`(85.0) / `buy_block_fg_low_threshold`(15.0) / `buy_block_regime_defensive_enabled`(true)
- **`.env` 폴백 없음** — 운영 가변(DB 미설정이면 코드 기본값)
- ⚠️ **이 값들은 매수를 차단하지 않는다** — 매크로 레짐은 사이클 I 에서 관찰 지표가 됐고 이 키들은 대시보드·자문 payload 표시 전용이다.

**scanner 구독 필터 2종** (`.env` 폴백 없음, 운영 가변):

- `get_price_filter() -> PriceFilter`(Pydantic) / `set_price_filter(*, min_price=None, max_price=None)` 부분 갱신. 2 키 = `price_filter_min` / `price_filter_max`(int 원, 0 = 비활성). 음수, 그리고 둘 다 0 보다 클 때의 `min_price > max_price` 는 `ValueError`
- `get_trade_amount_filter() -> TradeAmountFilter`(Pydantic) / `set_trade_amount_filter(*, min_amount=None)` 부분 갱신. 단일 키 = `trade_amount_filter_min`(int 원, 0 = 비활성). 음수는 `ValueError`
- **적용 위치** = `src/engine/scanner.py::subscribe_filtered_stocks` 진입 hook. 순서는 가격 → 거래대금이다. 60s TTL 캐시는 scanner 모듈 전역(`_get_price_filter_for_scanner` / `_get_trade_amount_filter_for_scanner`, `time.monotonic` 비교)이고 `invalidate_price_filter_cache_scanner()` / `invalidate_trade_amount_filter_cache_scanner()` 가 PUT 직후 즉시 무효화한다 — **무효화가 unsubscribe 를 발화시키지 않는다**(KIS LMS chain 차단)
- 거래대금 소스는 `scanner.ticker_market_info["trade_amount_raw"]`(원 단위) 1순위, `stock_master.raw.acml_tr_pbmn` 2순위다. 양쪽이 없거나 0 이면 **통과**시킨다(KIS 추가 호출 0건, 09:00 race 에서 시스템이 통째로 매매 불능이 되지 않게)
- 🔴 **매수 진입 전용이다** — 임계 밖 종목은 시세 구독 자체가 막혀 후보 풀이 줄지만 매도·손절·익일청산·15:20 강제청산에는 영향이 0 이고, **보유·익일청산 종목은 절대 통과**한다(공통 헬퍼 + early-return + AST keyword 의무 가드 3중)

## kis_quote_accounts.py — 보조 KIS 시세 수신 계좌 풀

- `list_accounts(active_only=False)` / `get_account(id)` / `get_account_by_label(label)` — 응답은 `KisQuoteAccount`(`app_secret_masked` 만 담고 평문은 절대 노출하지 않는다)
- read 4함수(`list_accounts`/`get_account`/`get_account_by_label`/`get_credentials_for_token_manager`)는 `pg.fetch`/`fetchrow` 라 `_with_retry` 를 내장한다. 쓰기(insert/update/delete)는 `pg.execute` 로 경유하지 않는다
- **`list_accounts` 60s TTL 메모리 캐시**: 모듈 전역 `_list_cache` / `_list_cache_expires_at` + `invalidate_list_cache()` + `_LIST_CACHE_TTL=60.0`. `time.monotonic()` 비교로 TTL 안이면 DB 호출 0. `active_only=True/False` 는 키를 나눈다. DB 예외 + 캐시 있음이면 stale 반환(graceful), 캐시 없음이면 빈 리스트. INSERT/UPDATE/DELETE 직후 `invalidate_list_cache()` 로 운영 토글이 즉시 반영된다
- `insert_account(label, app_key, app_secret, kis_env)` — label UNIQUE 충돌은 `LabelConflictError`, 빈 값·부적합 `kis_env` 는 `ValueError`
- `update_account(id, active=None, label=None)` — 부분 갱신. app_key/app_secret 수정은 지원하지 않는다(보안 감사 추적성 — 삭제 후 재등록 패턴)
- `delete_account(id)` — 존재하면 True, 없으면 False
- `get_credentials_for_token_manager(label)` — **토큰 매니저 전용 평문 노출 함수**. `src/auth/token.py::get_token_manager(label)` lazy 초기화에서만 부른다. 🔴 **API 응답·로그에 절대 노출 금지**
- 테이블: `kis_quote_accounts`(UUID PK, label UNIQUE, active=true 부분 인덱스)
- 자금 안전: 이 모듈의 응답은 **시세 수신 한정**이다. `order.py` / `balance.py` / 체결통보 구독은 메인 계좌만 쓴다

## strategy_funnel.py — 조건검색 단계별 추적

- **`insert_snapshot(*, target_date, strategy_id, step_no, step_name, survived_tickers=None, excluded_sample=None, survived_count=None, excluded_count=0, step_conditions=None, is_provisional=False) -> dict | None`** — 인자는 전부 keyword-only 다. `(target_date, strategy_id, step_no)` **UPSERT** 라 같은 단계는 최신 1행만 남고 `snapshot_at` 이 자동 갱신된다.
  - `survived_tickers` 는 `list[str]` 과 `list[dict]`(`{ticker, name}`) 를 모두 받고, `excluded_sample` 은 `[{ticker, name, reason}]`(수치 포함 사유) 형식이다. DB 응답을 읽는 쪽이 형식을 분기 처리한다.
  - `survived_count` 가 `None` 이면 `len(survived_tickers)` 를 쓴다. `step_conditions` 는 UI 툴팁용 단계 조건 문자열이다.
  - `is_provisional=True` = 16:20 저녁 잠정 캡처(전일 마스터 + 16:10 basics 기준), `False`(기본) = 09:30 자동·수동 trigger(확정).
  - **JSONB cap**: `SURVIVED_TICKERS_CAP = 200` / `EXCLUDED_SAMPLE_CAP = 20` 자동 적용(응답·저장 크기 보호). `survived_count` 는 cap 과 무관하게 정확한 값을 기록한다.
- `list_snapshots(target_date, strategy_id)`: 특정 영업일 + 전략의 모든 단계(`step_no` ASC)
- `list_recent_by_strategy(strategy_id, days=7)`: 최근 N영업일 추이
- 테이블: `strategy_funnel_snapshots`(UUID PK + 인덱스 2 = `target_date DESC` / `(strategy_id, target_date DESC)`)
- **호출은 공통 헬퍼 `scheduler.capture_funnel_snapshots(registry, *, is_provisional)` 하나로 모인다** — 호출처 3 = 09:30 `_scan_loop` 첫 진입의 자동 캡처(`_auto_capture_funnel_snapshots`, `is_provisional=False`) / 16:20 저녁 잠정 캡처(`_evening_funnel_capture_once`, `is_provisional=True`) / 수동 trigger `POST /api/strategy-funnel/snapshot`. 세 경로 모두 **단계별 + 최종(`step_no=99`)** 을 캡처한다. 단계 수집은 BFB/VCP/donchian `prepare()` 의 8단계 `_record_funnel_step` hook 이 하고, `_reset_daily_state` 가 동행 reset 한다.

## stock_master.py — 종목 마스터 캐시

- `upsert_one(StockBasics)` / `get(ticker) -> Optional[StockBasics]` / `is_stale(ticker, max_age_hours=24) -> bool`
- 테이블 `stock_master`. PK `ticker`(KRX 6자리), `refreshed_at` 24h TTL
- NXT 거래가능 사전 판별용 — `OrderEngine._strategy_exchange_async` + `scheduler._execute_next_day_clear` + `execute_sell` 거부 사후 보강 3경로가 읽는다
- 호출: 매수/매도 진입 직전 lazy. miss/stale 이면 `inquire_stock_basics` 를 부른 뒤 upsert 한다
- **eager 사전 갱신**: `scheduler._boot()` 마지막의 `_eager_refresh_stock_master_for_held_positions()` 가 보유 + `_pending_next_day_clear` 합집합을 sequential upsert 한다(24h fresh 는 skip). lazy 만 두면 첫 사이클 캐시 miss → SOR/NXT 발사 → KIS 거부로 이어진다
- **ticker 정규화**: PK 형식은 KRX 6자리다. `inquire_stock_basics` 가 `_normalize_ticker()` 로 KIS `pdno` 12자리 표준코드의 마지막 6자리를 뽑고, `upsert_one` 이 이중 안전망으로 6자리 미준수 입력도 정규화해 저장한다(WARNING)
- 조회·진단 보조: `count_active()` / `list_all(limit=100, offset=0)` / `list_history(ticker, limit=100)` / `count_eager_refresh_today()`

### `master_raw` 컬럼 (migration 034)

KIS 공식 일일 마스터 파일(`kospi_code.mst` / `kosdaq_code.mst`) 영역은 `master_raw JSONB` **별도 컬럼**이다.

- 컬럼: `master_raw JSONB NOT NULL DEFAULT '{}'::jsonb` + `master_raw_updated_at TIMESTAMPTZ`. 인덱스 2건 = GIN(master_raw 키 검색) + DESC NULLS LAST(갱신 시각 진단)
- 🔴 **`raw` 영역을 건드리지 않는다** — `bfdy_clpr` / `hts_avls` 덮어쓰기 0건이 계약이고 AST 영구 가드 `tests/unit/ast/test_cycle129_ast_master_raw_separation.py` 가 잰다
- `upsert_master_raw(ticker, master_raw: dict, *, is_kospi200: bool = False, is_kosdaq150: bool = False) -> None` — master_raw JSONB upsert + `master_raw_updated_at` KST 강제. `ON CONFLICT DO UPDATE` 가 payload 키 영역만 SET 하므로 **기존 ticker 를 갱신할 때 두 플래그를 명시하는 것이 의무**다(빠뜨리면 False 로 덮인다)
- `get_master_raw(ticker) -> Optional[dict]` — 단건 조회. lazy 폴백이 없다(16:30 KST 매스 적재 영역)
- `count_master_raw_today() -> int` — KST 영업일 기준 `master_raw_updated_at` 카운트(운영 진단)
- **`get_nxt_provenance_map(tickers) -> dict[str, bool]`**: 그 종목 행의 `raw` 에 KIS CTPF1002R 키 `cptt_trad_tr_psbl_yn` 이 **존재하는가**(값이 아니라 키 존재 — `raw ? 'cptt_trad_tr_psbl_yn'`). 형제 `get_nxt_tradable_map(tickers) -> dict[str, bool | None]` 과 같은 `= ANY($1::text[])` 1회 왕복 형태다. 용도 = 시세 채널 리졸버가 `nxt_tradable` 값을 **믿어도 되는지**의 판정이다. `_full_universe_load_krx_primary` 가 KRX raw 로 `nxt_tradable=False` 를 2,674종목에 도장하는데 그 raw 엔 이 키가 **없고**(09-14 실측 2,674/2,674 정확 일치) 16:1x basics_refresh(부팅 날은 07:53~08:08)가 진실을 복원한다 — 그 오염 창 안에 `TIME_PRESUBSCRIBE`(07:59)가 들어 있다. ⚠️ 소비처(`engine/no_feed_registry.ensure_fresh`)는 이 조회를 `get_nxt_tradable_map` 과 **독립 try** 로 감싼다 — 한 try 로 묶으면 출처 쿼리가 실패하는 날 cycle252 의 churn 차단까지 함께 죽는다
- 호출자: `src/engine/scanner.py::_stock_master_master_load_once()`(16:30 KST 매스 적재) · `src/engine/scanner.py::_is_master_blocked_for_entry(ticker)`(1단계 차단 7건 hook)

### `get_stats()` — 운영 진단 집계 8키

- `count_all` / `bfdy_clpr_present` / `nxt_tradable_count` / `with_hts_avls` / `with_acml_tr_pbmn` / `top_10_recent` / `total_daily_rows` / `last_daily_load_at`(뒤 둘은 `stock_master_daily` 연동)
- 🔴 **카운트는 전부 `SELECT count(*)` 별도 쿼리다** — 행을 가져와 Python 에서 세는 부분 집계를 쓰지 않는다. AST 영구 가드 `tests/unit/ast/test_cycle128_ast_no_range_9999_silent_cap.py` 가 `src/db/stock_master.py` 본체의 `.range(0, 9999)` 잔존을 0건으로 묶는다
- JSONB 키 존재성(`bfdy_clpr_present` / `with_hts_avls` / `with_acml_tr_pbmn`)은 `raw->>'키'` text path 의 non-null ∧ `<> '0'` ∧ `<> ''` 조합이다(존재성 검사이지 수치 비교가 아니다). 각 쿼리는 실패해도 0 으로 graceful
- `top_10_recent` 는 별도 `LIMIT 10` fetch 다

### `list_by_filter()` — scanner 유니버스 조회

```python
list_by_filter(*, market=None, min_market_cap=0, min_trade_amount=0,
               exclude_tickers=None, nxt_tradable=None,
               is_kospi200=None, is_kosdaq150=None,
               limit=500, return_stage_counts=False, sort_by=None)
    -> list[dict] | tuple[list[dict], dict[str, list[str]]]
```

- 전부 keyword-only. KIS `volume-rank` API 없이 DB 만으로 유니버스를 만든다(KIS 호출 0건).
- **필터는 전부 SQL WHERE 절이다.**
  - `market`: `"kospi"` → `excg_dvsn_cd = '02'` / `"kosdaq"` → `'03'` / `None` → 전체
  - `min_market_cap`(원): 생성 컬럼 `hts_avls_eok`(억원) `>= (min_market_cap + 99_999_999) // 100_000_000`
  - `min_trade_amount`(원): 생성 컬럼 `acml_tr_pbmn_won`(원) `>=` 직접 비교
  - `exclude_tickers`: `ticker <> ALL($n::text[])`
  - `nxt_tradable`: `None` 무필터 / True·False 등가 비교
  - `is_kospi200`·`is_kosdaq150`: **둘 다 True 면 `(is_kospi200 = true OR is_kosdaq150 = true)` OR 합집합**(donchian_swing `FUNNEL_STAGES[0]` "코스피200+코스닥150 합집합" 의무 정합), 한쪽만 주면 그 컬럼 AND, 둘 다 None 이면 무필터
  - 정렬 `ORDER BY refreshed_at DESC`, `LIMIT` 은 요청 `limit` 그대로다(오버페치 없음)
- SELECT 의 종목명은 `COALESCE(NULLIF(name, ''), NULLIF(TRIM(master_raw->>'hts_kor_isnm'), ''), '') AS name` 다 — ① CTPF1002R 이름 → ② 마스터파일 한글명(고정폭 패딩 TRIM) → ③ 둘 다 없으면 `''`(호출자 `row.get("name","")` 의 None 회귀 차단). `AS name` 별칭이라 반환 dict 키는 그대로다.
- `return_stage_counts=True` 면 `(filtered, {"union_tickers", "mcap_tickers", "trade_tickers"})` 튜플을 돌려준다 — union(시총·거래대금 컷 전) → mcap(시총 컷 후) → trade(거래대금 컷 후 = 최종 filtered) 3쿼리다. funnel 관찰성 전용이고 **필터 로직·임계·순서는 바뀌지 않는다**(`True` 의 filtered 가 `False` 의 결과와 원소·순서까지 같아야 한다는 것이 가드 계약이다).
- `sort_by`: 정렬 훅. `None`(기본)이면 `refreshed_at DESC` 를 그대로 쓴다. 실사용은 별도 사이클에 인계돼 있다.
- **ETF 키워드 제외와 6자리 ticker 검증은 이 함수가 아니라 호출자 `_scan_universe` 가 한다**(`ETF_KEYWORDS`).
- `raw` 의 `acml_tr_pbmn` / `lstn_stcn` / `acml_vol` 은 `inquire_stock_basics` 가 CTPF1002R 뒤에 FHKST01010100 을 덧붙여 merge 로 채운다. 🔴 **CTPF1002R 기존 키를 덮어쓰지 않는다**(`bfdy_clpr` 정합, AST G-AST1).

### `list_paged_by_filter()` — UI 종목목록 조회

```python
list_paged_by_filter(*, market=None, min_market_cap=0, min_trade_amount=0,
                     name_substr=None, limit=100, offset=0) -> dict
```

- 전부 keyword-only. 반환은 `{"items": list[dict], "total": int, "limit": int, "offset": int}` 다.
- `market`: `"KOSPI"` → `excg_dvsn_cd = '02'` / `"KOSDAQ"` → `'03'`(대소문자 무시) / `None` → 전체
- `min_market_cap`(원) → `hts_avls_eok >= (min_market_cap + 99_999_999) // 100_000_000`, `min_trade_amount`(원) → `acml_tr_pbmn_won >=` 직접 비교
- `name_substr`: `name ILIKE '%substr%'`
- 🔴 **시총·거래대금 비교는 반드시 생성 컬럼으로 한다** — `raw` 의 두 값은 jsonb *문자열*이라 `raw->'hts_avls' >= N::jsonb` 형태의 jsonb numeric 비교가 **항상 false** 다(어떤 임계를 줘도 0건이고 market·name 필터만 동작해 결함이 보이지 않는다). 생성 컬럼은 `CASE WHEN raw->>'…' ~ '^[0-9]+$' THEN (raw->>'…')::bigint END STORED` 라 비숫자는 NULL 로 빠진다(graceful). AST 가드 `tests/unit/db/test_cycle168_list_paged_generated_cols.py` 가 본체의 jsonb gte 잔존을 0건으로 묶는다
- `total` 은 같은 WHERE 절의 별도 `SELECT count(*)` 다(페이징 정합성 의무). 정렬은 `refreshed_at DESC`. count·data 쿼리는 각각 실패해도 0 / `[]` 로 graceful
- 호출자는 `GET /api/stock-master/list` 라우트뿐이다 — scanner 전용 `list_by_filter()` 와 영역이 분리돼 있다

## stock_master_daily.py — KIS 일봉 정규화

- 테이블 `stock_master_daily`(migration 033). PK 복합 `(ticker, bas_dd)` + 인덱스 `(ticker, bas_dd DESC)` + `(bas_dd DESC)`
- 컬럼 10종: `open_price`/`high_price`/`low_price`/`close_price`/`volume`/`trade_value`/`change_rate`/`flng_cls_code`/`prtt_rate`/`raw JSONB`
- KIS FHKST03010100(`chk_inquire_daily_itemchartprice.py` 정본) 응답 키 매핑 — `stck_bsop_date / stck_oprc / stck_hgpr / stck_lwpr / stck_clpr / acml_vol / acml_tr_pbmn / prdy_ctrt / flng_cls_code / prtt_rate`
- CRUD:
  - `upsert_daily(ticker, bas_dd, ohlcv)` — KIS row 단건 정규화 후 upsert
  - `upsert_batch(ticker, candles) -> int` — `_BATCH_SIZE = 100` 건 chunk 배치 upsert
  - `get_recent_daily(ticker, days=20)` — 최근 N일(DESC). donchian/VCP 입력. 🔴 **`days` 를 `max(1, min(days, _MAX_DAILY_ROWS))` 로 하드 클램프**한다. 행을 돌려주는 읽기 4함수(`get_donchian_high`·`get_atr`·`get_recent_daily_with_fallback`·`get_recent_daily_normalized`)가 전부 이 함수를 경유하므로 **어느 소비처도 상한을 넘겨 읽을 수 없다**(구조적 보장). 나머지 소비처는 스칼라 집계뿐이다(`max_bas_dd`·`count_all`·`count_by_ticker`·`routes/market_ops.py`).
    - **`_MAX_DAILY_ROWS = 400`(cycle300)** — 위아래 두 경계 사이다. 위: retention 390달력일이 보유하는 약 261 영업일과 VCP full 요청 `ema_long(200) + base_max_days(75) + 10 = 285` 가 둘 다 400 아래라 관문이 실데이터도 요청도 자르지 않는다. 아래: 무한대로 두지 않는다 — 오염된 파라미터나 호출 버그가 그대로 `LIMIT` 에 실려 한 종목 조회가 전체 스캔이 되는 것을 막는 폭주 방어선이다.
    - 🔴 **`min()` 구조 자체를 지우지 않는다** — 상한 값은 사이클마다 바뀔 수 있어도 클램프는 그 방어선이다. 가드 `tests/unit/db/test_cycle299_retention_expansion.py::test_g299_7a_get_recent_daily_keeps_days_clamp`(구조) + `tests/unit/engine/strategies/test_cycle300_daily_depth_switch.py`(숫자의 근거).
    - ⚠️ 상한을 올린 것이 **곧 더 읽는다는 뜻은 아니다** — 소비처는 각자 요청한 만큼만 받는다. 100 이하를 요청하는 소비처(donchian 20 · ATR 15 · 매크로 ETF 90 · LLM 60 · kojiro 100 · UI 라우트 `le=100`)는 상향 전후로 **받는 행 수가 1행도 바뀌지 않는다**. 실제로 더 읽는 것은 VCP 가 `daily_fetch_depth_mode="full"` 일 때뿐이다.
  - `get_donchian_high(ticker, days=20)` — 직전 N일 최고가(당일 제외)
  - `get_atr(ticker, days=14)` — 14일 ATR. True Range 는 웰스 와일더 3-way `max(고−저, |고−전종|, |저−전종|)` 이고 평활은 **단순평균(SMA) baseline** 이다 — Wilder 지수평활은 호출자 책임이고, 실제 Wilder ATR 은 `kojiro_indicators.atr`(ewm α=1/N) 뿐이다
  - `count_all()` / `count_by_ticker(ticker)` — 적재 진단
  - `max_bas_dd(ticker=None)` — 백필 vs 증분 분기 키(스캐너 사용)
  - `get_recent_daily_with_fallback(ticker, n)` — DB miss 시 `fetch_daily_candles` 폴백
  - **`get_recent_daily_normalized(ticker, days, *, min_required=None)`** — DB일봉 어댑터. DB row 의 `raw` JSONB(KIS 원본 키 `stck_clpr`/`stck_oprc` 등 보존)를 **그대로 반환**해 prepare 의 `c.get("stck_clpr")` 를 무변경으로 쓰게 한다. raw 키가 없는 row 는 row 자체를 돌려준다(graceful)
  - `purge_old_rows(cutoff_date, *, protected_tickers=None) -> dict[str, int]` — 아래 retention 항목 참조
- **KIS 폴백 조건 3개 (DB 를 쓰기 전에 이 순서로 검사한다)**:
  1. **락 게이트(최우선)** — 윈도우 안 1 row 라도 `_row_has_lock` 이 참이면(`flng_cls_code not in ("", "00")` 또는 `abs(float(prtt_rate)) > 0`) DB 를 버리고 `fetch_daily_candles` 로 강제 폴백한다. 근거 = 수정주가는 조회 시점에 달린 값이라 DB 에 박제된 과거봉(락 전)과 KIS 재조정봉(락 후)이 어긋난다. 검사는 정규화 컬럼 `flng_cls_code`/`prtt_rate` 만 보므로 **KIS 추가 호출이 0건**이다. ⚠️ 판정 기준은 "기본값이 아니면 락 의심" 이다 — 운영 DB 실측으로 `flng_cls_code` 는 99.6% 가 `"00"`, `prtt_rate` 는 99.7% 가 `"0.0000"` 이고, `prtt_rate != 1.0` 을 기준으로 삼으면 전 종목이 폴백한다
  2. **신선도 게이트** — `max_bas_dd(ticker)` 가 `today - DAILY_STALENESS_DAYS` 보다 오래면 폴백. `max_bas_dd` 가 `None`(판정 불가)이면 graceful 통과
  3. **min_required 게이트** — `len < min_required`(기본 `max(days // 2, 10)`)이면 폴백
  - 폴백 자체가 실패하면 DB 값을 그대로 쓴다(graceful). 헬퍼 3 = `_row_has_lock` / `_extract_raw`(raw 추출 DRY) / `_kis_fallback`(락·신선도·부족 공통 + 실패 시 DB graceful)
  - 상수 `DAILY_STALENESS_DAYS = 4`(주말 2일 + 공휴일 마진 — 거짓 폴백 차단). 전략별 `days`/`min_required` = VB/LTV 22 · donchian 63 · BFB 35 · VCP 100
- **retention `DAILY_RETENTION_DAYS = 390`(달력일 ≈ 261 영업일, cycle299)**. 실효 장기선이 정확히 200 이 되려면 일봉이 225 영업일 필요하고(`effective_ema_long = min(ema_long, 보유 − uptrend_days(20) − 5)`), 그 깊이를 담아 둘 자리가 이 값이다. 일봉 적재 대상 전부에 적용되는 backfill target 225 위로 **36 영업일 마진**이 남는다(환산 앵커 = 사이클196 실측 230cal ⇄ 154영업일). 🔴 **이 값과 target 은 함께 움직인다** — target 이 보유 영업일을 넘으면 `existing_count` 가 영원히 target 에 못 닿아 매일 밤 전량 재backfill(churn)이 된다(사이클 196 이 시정한 결함). 그 깊이를 실제로 읽으려면 위 `get_recent_daily` 의 상한(`_MAX_DAILY_ROWS`)과 전략 쪽 요청(VCP `daily_fetch_depth_mode`)이 둘 다 열려 있어야 한다. 가드 `tests/unit/db/test_cycle299_retention_expansion.py`.
- **`purge_old_rows` 는 날짜 슬라이스 루프다** — `PURGE_MAX_DATE_ITERATIONS = 500` cap 안에서 ① cutoff 이전의 가장 오래된 `bas_dd` 를 **protected 를 뺀 채** SELECT(없으면 drained break) ② 그 날짜 전체를 **protected 를 뺀 채** DELETE ③ deleted 누적. 🔴 **SELECT 쪽 protected 제외를 빼지 않는다** — 빼면 protected 만 남은 날짜를 무한히 다시 고르는 never-drain 이 된다. 예외는 부분 누적 deleted 를 반환하고 `logger.exception` 에 `type(exc).__name__: str(exc)[:150]` 를 남긴다
- DB 호출은 `pg.fetch`/`pg.execute`/`pg.executemany` 다. read 는 `_with_retry` 를 내장하고 쓰기 3함수(`upsert_daily`/`upsert_batch`/`purge_old_rows`)는 경유하지 않는다(AST G-187-A2 영구 불변식)
- 영속 의무: KST timestamp `_kst.now_kst_iso()` · raw JSONB 덮어쓰기 금지(G-AST1) · DATE 바인딩 `_kst.to_date()` 강제
- **UI 동기화 의무**: `stock_master_daily` 컬럼을 추가하면 UI 도 함께 고친다 — `GET /api/stock-master/{ticker}/daily?days=N`(`src/routes/stock_master.py`) + `frontend/src/pages/StockMaster.tsx::DailyTab` 30 row 테이블, 그리고 `get_stats()` 응답의 `total_daily_rows`/`last_daily_load_at`. 절차 상세는 `frontend/CLAUDE.md`

## stock_master_financial.py — KIS 재무 5 TR 정규화

- 테이블 `stock_master_financial`(migration 041). PK 복합 `(ticker, stac_yymm, div_cls)` — `div_cls` 0=년/1=분기 + 인덱스 `ix_smf_ticker_div (ticker, div_cls, stac_yymm DESC)`
- 컬럼 18종 정규화 NUMERIC: 손익 5(`sale_account`/`sale_totl_prfi`/`bsop_prti`/`thtr_ntin`/`depr_cost`) + 대차 7(`cras`/`fxas`/`total_aset`/`flow_lblt`/`total_lblt`/`total_cptl`/`cpfn`) + 수익성 2(`cptl_ntin_rate`/`sale_totl_rate`) + 안정성 2(`lblt_rate`/`crnt_rate`) + 기타 2(`ebitda`/`ev_ebitda`) + `raw JSONB` + `refreshed_at TIMESTAMPTZ`. 마법공식(EV/EBITDA·ROC) + F-Score-7(`src/engine/quant_score.py`) 의 원천 데이터다
- CRUD(`stock_master_daily.py` 미러):
  - `upsert_financial_batch(ticker, rows)` — 100건 배치 chunk + `ON CONFLICT (ticker, stac_yymm, div_cls) DO UPDATE SET` + graceful + KST(`now_kst_iso`)
  - `get_financial_series(ticker, div_cls="0", limit=3)` — 최근 N기(`stac_yymm` DESC). `div_cls` "0"=년 / "1"=분기
  - `max_stac_yymm(ticker, div_cls="0")` — 신선도·백필 게이트 키(스캐너 사용)
  - `count_all()` — 적재 진단
- DB 호출은 `pg`(asyncpg) 경유 + raw JSONB 덮어쓰기 금지(G-AST1)
- 호출자: `src/engine/scanner.py::_stock_master_financial_load_once()`(주1회 16:40 적재) + `src/engine/strategies/volatility_breakout.py::_apply_quant_filter_in_prepare()`(관찰 훅)
- 매매 hot path 무관 — 재무 적재는 매수 진입 전 데이터 계층이다

## pending_next_day_clear.py — 익일청산 큐 영속화

메모리 `_pending_next_day_clear: set[tuple]` 만 두면 EC2 재기동이 큐를 통째로 잃는다 —
6/17 알테오젠·알지노믹스 15:20 강제청산 누락이 그 사고다. 이 테이블이 그 큐의 복구 원천이다.

- 테이블 `pending_next_day_clear`(migration 038). 복합 PK `(target_date DATE, ticker TEXT, strategy_id TEXT)` + `created_at TIMESTAMPTZ` + `reason VARCHAR(50) NOT NULL DEFAULT 'unknown'`(진단용 — `nxt_not_tradable` / `nxt_open_missing` / `market_order_disallowed_fallback`)
- CRUD 4:
  - `save_pending_ndc(target_date, ticker, strategy_id, reason="unknown")` — 1행 UPSERT. 등록 사이트 4 = `_execute_next_day_clear` 의 `nxt_tradable=False` 분기 · `_execute_next_day_clear` 의 NXT 시가 미수신 분기 · sell_rejection 의 NXT 익일 전환 · order_engine 매도 거부 NXT 폴백
  - `delete_pending_ndc(ticker)` — `_drain_pending_next_day_clear` 의 finally 에서 호출
  - `load_pending_ndc(target_date) -> set[tuple[str, str]]` — `boot()` 마지막 단계에서 메모리 set 복구
  - `purge_pending_ndc_before(target_date) -> int` — `_reset_daily_state` 가 fire-and-forget 으로 호출
- **DB 가 실패해도 메모리 상태를 보존한다**(graceful) — 호출자가 try/except 로 흡수하고 WARNING 을 남긴다

## backtest_runs.py — 외부 MCP 백테스트 실행 이력

20:00 AI 자문 직후 6 전략 × 2 kind = 12 job 을 fire-and-forget 으로 띄운 기록이다.

| 함수 | 계약 |
|---|---|
| `insert_run(target_date, strategy_id, params_kind, params_snapshot) -> dict \| None` | `status="queued"` 로 1행. `params_kind` 는 `"current"`/`"recommended"` 둘뿐이고 그 밖은 **`ValueError`**(조용한 흡수 금지). 🔴 **UNIQUE `(target_date, strategy_id, params_kind)` 충돌은 예외가 아니라 `None`** — 자문 사이클이 재진입해도 멱등하게 넘어가라는 계약이다 |
| `get_by_id(run_id)` · `list_by_date(target_date)` | 조회 |
| `update_status(run_id, status, *, mcp_job_id=None, error_message=None, metrics=None)` | `running`=mcp_job_id 부여 / `completed`=metrics + `completed_at` / `failed`=error_message + `completed_at` / `skipped`=YAML DSL 미지원 전략, `completed_at` 기록 |

`target_date` 는 DATE 라 `_kst.to_date()` 로 강제 변환한다(str 입력도 받는다).

## market_regime_snapshots.py — dkstock.cloud 매크로 일일 스냅샷

`_boot()` 시점에 1행. 매크로 레짐은 **관찰 지표**이고 매수를 차단하지 않는다(사이클 I) —
`buy_blocked` 컬럼은 그날의 판정을 남기는 기록이지 게이트가 아니다.

| 함수 | 계약 |
|---|---|
| `insert_snapshot(snapshot_date, regime, regime_desc, cycle_phase, vix, fear_greed_score, buffett_ratio, raw_response, computed_cash_usage_ratio, buy_blocked, block_reason) -> dict \| None` | 🔴 **같은 `snapshot_date` 가 이미 있으면 예외가 아니라 `None`**(graceful) — 하루 두 번 부팅해도 첫 기록이 이긴다 |
| `get_by_date(snapshot_date)` · `get_latest()` · `list_recent(days=30)` | 조회. `list_recent` 가 `GET /api/market-regime/history` 의 소스 |

`raw_response` JSONB 는 외부 응답 **원문**이다 — 정규화해서 넣지 않는다(외부 스키마가 바뀐 날
무엇이 왔는지 되짚을 수 있는 유일한 기록이다).

## parameter_recommendations.py — 전략수정 AI자문 이력

- `insert_recommendation()`: 20:00 자문 생성 시 INSERT(status: pending). `(target_date, strategy_id)` UNIQUE
- `list_recommendations(days=30)`: 최근 N일 이력(신규 + 처리 통합)
- `get_recommendation(id)`: 단일 자문 상세
- `list_pending_by_date(target_date)`: 그 영업일의 pending 목록
- `update_recommendation_status(id, status, applied_params=..., applied_weight=...)`: status 갱신 + `applied_at`/`rejected_at` 자동 기록. 페이로드는 applied/partial 상태에서만 포함한다
- `expire_pending_before(target_date)`: 이전 pending 자동 만료
- `update_backtest_summary(...)` / `list_recommendations_pending_backtest(target_date)`: 외부 MCP 백테스트 결과를 `backtest_summary` JSONB 에 붙이는 경로
- 컬럼: `recommended_weight` NUMERIC nullable / `code_review_notes` TEXT nullable(≤2000자) / `applied_weight` NUMERIC nullable / `weight_reasoning` TEXT nullable(≤1000자) / `backtest_summary` JSONB. INSERT 시점의 `applied_weight` 는 `None` 이고 apply 라우트가 사용자 명시 토글일 때만 채운다
- `status` 값 `applied_auto`(migration 028)는 AI 자문 **자동** 적용 전용이다 — 운영자 수동 `applied` 와 분리해 추적성을 남긴다

## supabase.py — 롤백용 병존 파일

어느 모듈도 import 하지 않는다. 🔴 **새 코드에서 `supabase.table()` 이나 `asyncio.to_thread` DB 위임을 쓰지 않는다** — DB I/O 는 `pg.py`(asyncpg) 직행이 정본이다. 확인은 `grep supabase.table src/` 다(`supabase.py` 자신을 빼면 0건이어야 한다).

## DB 스키마

- `supabase/migrations/001_init.sql` 정의
- `trade_history.status`: PENDING → COMPLETED / PARTIAL → CANCELLED
- `trade_history.trade_type`: BUY / SELL
- `trade_history` 부분 UNIQUE 인덱스 `(ticker, order_no, trade_type) WHERE order_no IS NOT NULL AND != ''` (migration 029)
- `llm_buy_evaluations` (migration 043): PK `(trade_date, account_no, ticker, order_no)` + 53열 (`eval_kind` = `'order'`|`'blocked'` — enforce 로 가면 주문 없는 차단 평가가 `order_no=''` 로 하루 1행 = 전방 호환) + 인덱스 4
- `parameter_recommendations.status`: pending → applied / partial / rejected / expired / applied_auto
- `strategy_funnel_snapshots` (migration 030): UNIQUE `(target_date, strategy_id, step_no)` (migration 035) + JSONB 필드 2개

## TIMESTAMPTZ 계약

모든 시각 컬럼은 PostgreSQL `TIMESTAMPTZ` 다 — **절대 시점(instant)을 저장하고 timezone 정보는 분리**된다.
UTC 로 들어간 값과 KST 로 들어간 값은 **같은 시점**이라, 옛 행이 UTC 로 저장돼 있다고 해서 결함이 아니고
백필도 필요 없다. 🔴 ***"UTC 저장 = 결함"* 이라는 가정이 나오면 이 절을 인용해 차단한다.**

우리 규약은 두 가지뿐이다.

- **표시 형식** — ISO 문자열이 필요하면 SQL 에서 `to_char(...,'+09:00')` 로 KST 를 렌더한다.
- **비교 경계** — 조회 경계 문자열에 `+09:00` 을 명시한다(`get_trades_in_range` / `get_logs` / `_fetch_logs_in_range`). 빠뜨리면 UTC 로 해석돼 KST 00:00~09:00 이 잘린다.

풀 세션 timezone 은 `init_pool(server_settings={"timezone": "Asia/Seoul"})` 이 정한다.

## 주의사항

- **모든 CRUD 는 `pg.fetch`/`fetchrow`/`fetchval`/`execute`/`executemany` 를 경유한다**
- `_DbLogHandler`(main.py) 는 동기 `logging.Handler.emit` → **큐 producer + async consumer** 구조다. dedupe 500ms · KST 강제 · never-raise 를 보존한다
- 매핑 등록(`_order_qty`/`_order_strategy`/`_order_ticker`)은 **반드시 async DB write 진입 전 동기 영역**에서 끝낸다(시장가 즉시체결 race 차단)
- status ENUM 값을 바꾸면 DB CHECK 제약조건도 함께 고친다(migration 추가)
