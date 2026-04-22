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
- `upsert_performance()`: 16:10 정산 시 당일 실적 기록
- `get_performance(days)`: 최근 N일 실적 조회

### system_logs.py — 시스템 로그
- `write_log(level, message)`: 이벤트/에러 기록
- level: INFO, WARNING, ERROR, CRITICAL

## DB 스키마
- `supabase/migrations/001_init.sql`에 정의
- trade_history.status: PENDING → COMPLETED / PARTIAL → CANCELLED
- trade_history.trade_type: BUY / SELL

## 주의사항
- Supabase SDK는 동기 호출이므로 I/O-bound 작업은 `asyncio.to_thread` 고려
- status ENUM 값 변경 시 DB CHECK 제약조건도 함께 수정 (migration 추가)
