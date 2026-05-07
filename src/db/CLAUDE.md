# CLAUDE.md — src/db/ (Supabase DB)

Supabase(PostgreSQL) CRUD 모듈.

## 모듈별 역할

### supabase.py — 클라이언트 초기화
- `settings.supabase_url` + `settings.supabase_key`로 클라이언트 생성

### trade_history.py — 거래 내역
- `insert_trade()`: 주문 시 INSERT (status: PENDING)
- `update_trade_status() -> int`: 체결/취소 시 PENDING row를 새 status로 갱신하고 영향받은 row 수를 반환. 호출자(OrderEngine)가 0건이면 체결통보 선행 race로 판단해 COMPLETED 보정 INSERT를 수행한다
- `get_trades(limit, offset, ticker)`: 페이징 조회 + total count
- `get_trade_pairs(strategy=None, ticker=None)`: 매매손익 뷰용 매수/매도 페어 리스트. 같은 (ticker, strategy) 그룹 내 timestamp ASC 순회 → 누적 보유수량이 0으로 돌아오는 사이클마다 closed 페어 emit (매수가/매도가 가중평균, Decimal 보존), 잔여 보유는 open 페어로 emit (미실현 손익은 `scanner.ticker_prices` 현재가 fallback). 응답 키: buy_date/buy_time/sell_date/sell_time/ticker/ticker_name/buy_price/buy_qty/sell_price/sell_qty/profit_loss/profit_rate/status('closed'|'open')/strategy

### daily_performance.py — 일일 실적
- `upsert_daily_performance()`: 16:10 정산 시 당일 실적 기록 (total_asset, daily_profit_rate=실현손익 기반, daily_realized_pnl, net_external_cashflow, deposit, cumulative_return_rate=TWR 복리)
- `get_performance(days)`: 최근 N일 실적 조회 (날짜 오름차순)
- `get_latest_performance(strategy)`: 가장 최근 영업일 1행 — TWR 누적/Δ예수금 baseline
- `recompute_from_trades()`: PostgreSQL 함수 `recompute_daily_performance()` RPC 호출 — trade_history 기반 일괄 재계산 (멱등). _settle() 끝에서 자동 호출되어 누락된 영업일/cumulative 정합성을 보정한다. daily_profit_rate 분모(prev_asset)는 직전 영업일이 아니라 **가장 가까운 0이 아닌 이전 영업일 total_asset**(correlated subquery, migration 012). 정산 시점 state.total_investment=0이라 total_asset=0이 기록된 row가 있어도 그 다음 영업일 비율 계산이 깨지지 않는다.

### system_logs.py — 시스템 로그
- `write_log(level, message)`: 이벤트/에러 기록
- level: INFO, WARNING, ERROR, CRITICAL

### log_reports.py — 일일 로그 분석 리포트
- `insert_log_report()`: 16:10 정산 직후 분석 결과 INSERT (target_date UNIQUE, 충돌 시 None)
- `list_log_reports(days=30)`: 최근 N일 신규순 조회
- `get_log_report(target_date)`: 단일 영업일 조회
- 스키마 컬럼: id(uuid), target_date(unique), summary(text), findings(jsonb 배열), metrics(jsonb), model(varchar), created_at

### parameter_recommendations.py — 전략수정 AI자문 이력
- `insert_recommendation()`: 16:00 자문 생성 시 INSERT (status: pending). (target_date, strategy_id) unique
- `list_recommendations(days=30)`: 최근 N일 이력 조회 (신규+처리 완료 통합)
- `get_recommendation(id)`: 단일 자문 상세
- `update_recommendation_status(id, status, applied_params=...)`: status 갱신 + applied_at/rejected_at 자동 기록
- `expire_pending_before(target_date)`: 이전 pending 레코드를 expired로 일괄 마킹

## DB 스키마
- `supabase/migrations/001_init.sql`에 정의
- trade_history.status: PENDING → COMPLETED / PARTIAL → CANCELLED
- trade_history.trade_type: BUY / SELL
- parameter_recommendations.status: pending → applied / partial / rejected / expired

## 주의사항
- Supabase SDK는 동기 호출이므로 I/O-bound 작업은 `asyncio.to_thread` 고려
- status ENUM 값 변경 시 DB CHECK 제약조건도 함께 수정 (migration 추가)
