# CLAUDE.md — src/db/ (Supabase DB)

Supabase(PostgreSQL) CRUD 모듈.

## 모듈별 역할

### supabase.py — 클라이언트 초기화
- `settings.supabase_url` + `settings.supabase_key`로 클라이언트 생성

### trade_history.py — 거래 내역
- `insert_trade()`: 주문 시 INSERT (status: PENDING)
- `update_trade_status() -> int`: 체결/취소 시 PENDING row를 새 status로 갱신하고 영향받은 row 수를 반환. 호출자(OrderEngine)가 0건이면 체결통보 선행 race로 판단해 COMPLETED 보정 INSERT를 수행한다
- `get_trades(limit, offset, ticker)`: 페이징 조회 + total count
- `get_trade_pairs(strategy=None, ticker=None)`: 매매손익 뷰용 매수/매도 페어 리스트. 같은 (ticker, strategy) 그룹 내 timestamp ASC 순회 → 누적 보유수량이 0으로 돌아오는 사이클마다 closed 페어 emit (매수가/매도가 가중평균, Decimal 보존), 잔여 보유는 open 페어로 emit (미실현 손익은 `scanner.ticker_prices` 현재가 fallback). 응답 키: buy_date/buy_time/sell_date/sell_time/ticker/ticker_name/buy_price/buy_qty/sell_price/sell_qty/profit_loss/profit_rate/status('closed'|'open')/strategy. **L1(2026-05-12)**: `_to_kst()` 헬퍼로 ISO 타임스탬프(UTC/KST/tz-naive 모두) → `astimezone(KST).strftime()` 명시 변환 후 date/time 추출 — UI 시각 KST 일관성 보장
- `get_today_buy_trades / get_today_sell_trades / get_today_pending_buys`: today 기준 same-day 매수/매도/PENDING 조회. **L5(2026-05-12)**: 쿼리 기준점 `f"{today}T00:00:00+09:00"` 로 KST timezone 명시 (이전 timezone-naive → PostgreSQL TIMESTAMPTZ UTC 해석 결함 → KST 09시 이전 기록이 same-day 쿼리에서 누락되던 결함 차단. 2026-05-12 005930 보완 INSERT 사고 대응)

### daily_performance.py — 일일 실적
- `upsert_daily_performance()`: 16:10 정산 시 당일 실적 기록. `daily_realized_pnl`/`daily_profit_rate` 모두 **실현손익 기준**(SELL 매도 실현분만 합산). 매도 0건인 날은 둘 다 0 정상 — 보유 평가손익 변동은 포함 안 함(2026-05-15 정책 명시화). 평가손익은 `BalanceTable.eval_profit_loss`(실시간 KIS 잔고 응답) 으로 별도 표시. 컬럼: total_asset, daily_profit_rate, daily_realized_pnl, net_external_cashflow, deposit, cumulative_return_rate(TWR 복리, 실현손익 누적)
- `get_performance(days)`: 최근 N일 실적 조회 (날짜 오름차순)
- `get_latest_performance(strategy)`: 가장 최근 영업일 1행 — TWR 누적/Δ예수금 baseline
- `recompute_from_trades()`: PostgreSQL 함수 `recompute_daily_performance()` RPC 호출 — trade_history 기반 일괄 재계산 (멱등). _settle() 끝에서 자동 호출되어 누락된 영업일/cumulative 정합성을 보정한다. daily_profit_rate 분모(prev_asset)는 직전 영업일이 아니라 **가장 가까운 0이 아닌 이전 영업일 total_asset**(correlated subquery, migration 012). 정산 시점 state.total_investment=0이라 total_asset=0이 기록된 row가 있어도 그 다음 영업일 비율 계산이 깨지지 않는다.

### system_logs.py — 시스템 로그
- `write_log(level, message)`: 이벤트/에러 기록
- level: INFO, WARNING, ERROR, CRITICAL
- `get_logs(limit=100, log_level=None, *, from_date=None, to_date=None, page=1, size=None)`: 페이징 + KST 기간 필터 조회 (사이클 6, 2026-05-17). 반환 `{"items": list[dict], "total": int, "total_pages": int}`. `size` 미지정 시 `limit` 흡수(하위 호환). `from_date`/`to_date` 명시 시 `timestamp >= "{date}T00:00:00+09:00"` / `<= "{date}T23:59:59.999999+09:00"` 비교 — KST 강제. supabase-py `count="exact"` 로 total 동봉, `total_pages = ceil(total / size)`

### log_reports.py — 일일 로그 분석 리포트
- `insert_log_report()`: 16:10 정산 직후 분석 결과 INSERT (target_date UNIQUE, 충돌 시 None)
- `list_log_reports(days=30)`: 최근 N일 신규순 조회
- `get_log_report(target_date)`: 단일 영업일 조회
- 스키마 컬럼: id(uuid), target_date(unique), summary(text), findings(jsonb 배열), metrics(jsonb), model(varchar), created_at

### system_config.py — 시스템 설정 키-값 헬퍼
- `get_cash_usage_ratio() -> float` / `set_cash_usage_ratio(ratio: float) -> None` (J3, 2026-05-12)
- 키 `cash_usage_ratio`, JSONB 값 `{"value": float}`. **사이클 2 (2026-05-17)** 범위 확장: [0.5, 1.0] → **[0.0, 1.0]** (defensive 레짐 0.25 수용). 5% 단위 자동 보정. 미설정 시 기본 1.0
- `get_auto_regime_adjust() -> bool` / `set_auto_regime_adjust(value: bool) -> None` (사이클 2, 2026-05-17). 키 `auto_regime_adjust`. 미설정 시 기본 True
- **사이클 5 (2026-05-17) 외부 통합 토글 4 헬퍼 추가**:
  - `get_dkstock_regime_enabled() -> bool | None` / `set_dkstock_regime_enabled(value: bool) -> None` (키 `dkstock_regime_enabled`)
  - `get_kis_mcp_enabled() -> bool | None` / `set_kis_mcp_enabled(value: bool) -> None` (키 `kis_mcp_enabled`)
  - **기본값이 `None`** — 호출자가 `settings.dkstock_regime_enabled` / `settings.kis_mcp_enabled` 환경변수로 fallback 결정. cash_usage_ratio (기본 1.0) / auto_regime_adjust (기본 True) 와 다른 점 — DB 미설정 시 .env 호환 보존
  - 내부 헬퍼 `_get_bool_or_none(key)` / `_set_bool(key, value)` 가 JSONB `{"value": bool}` + 과거 호환(직저장 bool / 'true'/'false' 문자열) 모두 흡수
- scheduler `_boot()` 가 `summary.net_asset × ratio` 로 `allocate_funds()` 호출 — 변경은 다음 영업일 _boot 부터 반영
- 범위 외 입력은 ValueError. supabase 동기 호출은 `asyncio.to_thread` 위임

### kis_quote_accounts.py — 보조 KIS 시세 수신 계좌 풀 (사이클 7-A, 2026-05-17)
- `list_accounts(active_only=False)` / `get_account(id)` / `get_account_by_label(label)` — 응답은 `KisQuoteAccount` (`app_secret_masked` 만, 평문 절대 노출 안 함)
- `insert_account(label, app_key, app_secret, kis_env)` — label UNIQUE 충돌 시 `LabelConflictError`, 빈 값 / kis_env 부적합 시 `ValueError`
- `update_account(id, active=None, label=None)` — 부분 갱신. app_key/app_secret 수정은 본 사이클 미지원(보안 감사 추적성 위해 삭제 후 재등록 패턴)
- `delete_account(id)` — 존재 시 True, 미존재 False
- `get_credentials_for_token_manager(label)` — **토큰 매니저 전용 평문 노출 함수**. `src/auth/token.py::get_token_manager(label)` lazy 초기화에서만 호출. API 응답/로그 절대 노출 금지
- 테이블: `kis_quote_accounts` (migration 026, UUID PK, label UNIQUE, active=true 부분 인덱스)
- 자금 안전: 본 모듈 응답은 **시세 수신 한정**. order.py / balance.py / 체결통보 구독은 메인 계좌만 — 코드 리뷰 시 보조 계좌 변수 전달 차단 확인
- supabase 동기 SDK 호출은 모두 `asyncio.to_thread()` 위임

### stock_master.py — 종목 마스터 캐시 (Phase G, 2026-05-11)
- `upsert_one(StockBasics)` / `get(ticker) -> Optional[StockBasics]` / `is_stale(ticker, max_age_hours=24) -> bool`
- 테이블: `stock_master` (migration 015). PK `ticker`, `refreshed_at` 24h TTL
- NXT 거래가능 사전 판별용 — `OrderEngine._strategy_exchange_async` + `scheduler._execute_next_day_clear` + `execute_sell` 거부 사후 보강 3경로에서 사용
- 호출: 매수/매도 진입 직전 lazy 조회. miss/stale → `inquire_stock_basics` 호출 후 upsert
- **eager 사전 갱신 (I3, 2026-05-12)**: `scheduler._boot()` 마지막에 `_eager_refresh_stock_master_for_held_positions()` 호출 — 보유 + `_pending_next_day_clear` ticker 합집합을 sequential 로 upsert (24h TTL fresh skip). lazy 갱신 한계(첫 사이클 캐시 miss 시 SOR/NXT 발사 → KIS 거부, 2026-05-12 계양전기 사례) 차단
- **Phase G2 (2026-05-13)**: ticker 키 형식을 KRX 6자리로 정규화. KIS `pdno` 12자리 표준코드(`00000A000100`)를 그대로 저장하던 결함으로 `get()` 이 항상 miss → Phase G 사전 차단 무력화되던 운영 사고 차단. (1) `inquire_stock_basics` 가 `_normalize_ticker()` 로 응답 `pdno` 마지막 6자리 추출 후 모델 생성, (2) `upsert_one` 이 호출자 무관 이중 안전망으로 6자리 미준수 입력을 동일 헬퍼로 정규화 후 저장 (WARNING 로그), (3) 마이그레이션 017 이 기존 12자리 row 일괄 DELETE → 다음 `_boot` eager_refresh 가 6자리로 재생성. 검증: positions.ticker(6자리)와 PK 형식 일치 보장
- supabase 동기 호출은 모두 `asyncio.to_thread()` 위임 — 일관 정책

### parameter_recommendations.py — 전략수정 AI자문 이력
- `insert_recommendation()`: 16:00 자문 생성 시 INSERT (status: pending). (target_date, strategy_id) unique
- `list_recommendations(days=30)`: 최근 N일 이력 조회 (신규+처리 완료 통합)
- `get_recommendation(id)`: 단일 자문 상세
- `update_recommendation_status(id, status, applied_params=..., applied_weight=...)`: status 갱신 + applied_at/rejected_at 자동 기록. **J4(2026-05-12)** — `applied_weight` 키워드 추가, applied/partial 상태에서만 페이로드 포함
- `expire_pending_before(target_date)`: 이전 pending 레코드를 expired로 일괄 마킹
- **J4 신규 컬럼 (migration 016)**: `recommended_weight` NUMERIC nullable / `code_review_notes` TEXT nullable (≤2000자) / `applied_weight` NUMERIC nullable. INSERT 시점 applied_weight 는 None, apply 라우트가 사용자 명시 토글일 때만 채움

## DB 스키마
- `supabase/migrations/001_init.sql`에 정의
- trade_history.status: PENDING → COMPLETED / PARTIAL → CANCELLED
- trade_history.trade_type: BUY / SELL
- parameter_recommendations.status: pending → applied / partial / rejected / expired

## 주의사항
- **Supabase SDK는 동기 client → 모든 `.execute()` 호출이 `asyncio.to_thread()`로 thread pool에 위임**(이벤트 루프 블로킹 차단). `lambda` 또는 inner function 패턴 사용. PR3에서 일괄 적용됨
- `_DbLogHandler`(main.py)도 동기 `logging.Handler.emit`이라 to_thread 불가 → `ThreadPoolExecutor(max_workers=2)`에 fire-and-forget submit
- 매핑 등록(`_order_qty/_order_strategy/_order_ticker`)은 **반드시 to_thread 진입 전 동기 영역**에서 완료 (CLAUDE.md 안전장치 — 시장가 즉시체결 시 race 차단)
- status ENUM 값 변경 시 DB CHECK 제약조건도 함께 수정 (migration 추가)
