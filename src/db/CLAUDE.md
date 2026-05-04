# CLAUDE.md — src/db/ (Supabase DB)

Supabase(PostgreSQL) CRUD 모듈.

## 모듈별 역할

### supabase.py — 클라이언트 초기화
- `settings.supabase_url` + `settings.supabase_key`로 클라이언트 생성

### trade_history.py — 거래 내역
- `insert_trade()`: 주문 시 INSERT (status: PENDING)
- `update_trade_status()`: 체결/취소 시 상태 ��데이트
- `get_trades(limit, offset, ticker)`: 페이징 조회 + total count

### daily_performance.py — 일일 실적
- `upsert_daily_performance()`: 16:10 정산 시 당일 실적 기록 (total_asset, daily_profit_rate=실현손익 기반, daily_realized_pnl, net_external_cashflow, deposit, cumulative_return_rate=TWR 복리)
- `get_performance(days)`: 최근 N일 실적 조회 (날짜 오름차순)
- `get_latest_performance(strategy)`: 가장 최근 영업일 1행 — TWR 누적/Δ예수금 baseline

### system_logs.py — 시스템 로그
- `write_log(level, message)`: 이벤트/에러 기록
- level: INFO, WARNING, ERROR, CRITICAL

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
