# Red 명세 — 사이클 122 KIS 일봉 도입 + stock_master_daily 정규화

작성: 2026-06-12 (금) team-leader
대상 사용자 결정 (Q1~Q4) 확정 후 tdd-engineer Red 명세 정밀화 의무.

---

## 0. 영역 분해

| 영역 | 책임 | 산출물 | 회귀 가드 |
|------|------|--------|-----------|
| 영역 1 | DB schema + CRUD | migration 033 + `src/db/stock_master_daily.py` | HIGH 5 + MEDIUM 2 |
| 영역 2 | KIS API 호출 (재사용) | `src/api/condition.py::fetch_daily_candles` 영속 (변경 0) | HIGH 0 + MEDIUM 1 (정합 검증) |
| 영역 3 | 스케줄러 통합 | `src/engine/scheduler.py` lifecycle race 차단 패턴 | HIGH 3 + MEDIUM 3 |
| 영역 4 | AST 영구 가드 | KIS TR_ID + DB schema + lifecycle | AST 4 |

총 회귀 가드 = HIGH 8 + MEDIUM 6 + AST 4 = **18 케이스**

---

## 1. 영역 1: DB schema + CRUD

### G-DB1 (HIGH) — migration 033 적용
- Supabase MCP `apply_migration` 영역 적용 (사이클 84 답습)
- 테이블 `stock_master_daily` 생성 확인 (PK `(ticker, bas_dd)` 복합)
- 인덱스 2종 생성 확인 (`idx_stock_master_daily_ticker_bas_dd` + `idx_stock_master_daily_bas_dd`)

```python
# tests/unit/db/test_cycle122_stock_master_daily_schema.py
def test_g_db1_migration_applied():
    # Supabase MCP READ-ONLY 영역에서 information_schema 조회
    tables = supabase.rpc("get_table_info", {"table_name": "stock_master_daily"}).execute()
    assert tables.data is not None
    columns = {row["column_name"] for row in tables.data}
    assert "ticker" in columns
    assert "bas_dd" in columns
    assert "open_price" in columns
    assert "high_price" in columns
    assert "low_price" in columns
    assert "close_price" in columns
    assert "volume" in columns
    assert "trade_value" in columns
    assert "raw" in columns
```

### G-DB2 (HIGH) — `upsert_daily(ticker, bas_dd, ohlcv)` 단건 upsert
- 신규 row INSERT
- 동일 PK `(ticker, bas_dd)` ON CONFLICT UPDATE (사이클 30 답습)
- `updated_at` 갱신 확인

### G-DB3 (HIGH) — `upsert_daily_batch(rows)` batch upsert 100건
- 100건 단위 batch 영역 (Supabase HTTP/2 stale connection 회피, 사이클 26 답습)
- 50ms sleep (KIS LMS chain 안전 마진, 사이클 83/91/97/107 답습)
- 부분 실패 시 graceful (사이클 88 G-REJECT 영속)

### G-DB4 (HIGH) — `get_recent_daily(ticker, days)` 최근 N일 조회
- `bas_dd DESC` 정렬
- 100일 cap (KIS 호출 한도 영속)
- 미존재 시 빈 list (graceful)

### G-DB5 (HIGH) — `get_donchian_high(ticker, days=20)` + `get_atr(ticker, days=14)` 활용 헬퍼
- donchian 20일 신고가 = `MAX(close_price)` over last 20 rows
- ATR 14일 = `mean(high - low + |open - prev_close|)` over last 14 rows (Wilder 공식 영속)
- 미존재 시 None (graceful)

### G-DB6 (MEDIUM) — `count_all()` + `count_by_ticker(ticker)` 진단 영역
- UI 영역 확장 시 진단 영역 (사이클 85 stock_master UI 답습)

### G-DB7 (MEDIUM) — `get_last_bas_dd(ticker)` 점진 적재 영역
- 점진 적재 시 신규 행 영역 결정 (사이클 122 = 백필 / 사이클 123+ = D-1 신규)

---

## 2. 영역 2: KIS API 호출 (재사용)

### G-API1 (MEDIUM) — `fetch_daily_candles` 호출 영속 정합 검증
- 사이클 122 = 기존 `fetch_daily_candles(ticker, days=100)` 영속 재사용 (변경 0)
- TR_ID `FHKST03010100` 영속 확인 (AST 영역 영구 가드)
- `FID_ORG_ADJ_PRC=0` 수정주가 영역 영속 확인

---

## 3. 영역 3: 스케줄러 통합

### G-SCHED1 (HIGH) — `_stock_master_daily_load_task_loop` lifecycle race 차단
- start() 직후 즉시 1회 실행 + while 루프 (사이클 106 답습)
- `_wait_until(16:00:00)` 영역 영구 영속
- try/except 4중 가드 (CancelledError → break / Exception → graceful + asyncio.sleep(60))

### G-SCHED2 (HIGH) — `_stock_master_daily_load_once` 본체
- `stock_master.list_all()` 영역 호출 (전체 2,700 종목)
- ticker 별 `fetch_daily_candles(ticker, days=100)` 호출 + 50ms sleep
- `stock_master_daily.upsert_daily_batch(rows)` batch upsert
- 진행 상황 emit `[stock_master_daily_load] start/progress/complete total=N elapsed_ms=K kospi=L kosdaq=M`

### G-SCHED3 (HIGH) — stop() lifecycle 정리
- 사이클 79 G-AST2 영속 (task cancel 목록에 `_stock_master_daily_load_task` 포함)
- 사이클 78 답습 (collector flush)

### G-SCHED4 (MEDIUM) — TIME_STOCK_MASTER_DAILY_LOAD 상수 신규
- `TIME_STOCK_MASTER_DAILY_LOAD = time(16, 0)` 신규 상수

### G-SCHED5 (MEDIUM) — `_full_universe_load_once` 의존성 영역
- 사이클 106 lifecycle race 차단 영역 영속 (stock_master 적재 *후* 일봉 적재)
- 의존성 영역 확인 (`is_stale()` 24h TTL idempotency)

### G-SCHED6 (MEDIUM) — graceful 영역 (사이클 88 G-REJECT 영속)
- 일봉 적재 실패 시 = 5 전략 prepare 영역 영향 (donchian/VCP/VB/LTV/BFB)
- 회피 영역 = stock_master_daily 미존재 시 KIS 호출 fallback (사이클 81 G-AST1 graceful 답습)

---

## 4. 영역 4: AST 영구 가드

### G-AST1 — KIS TR_ID `FHKST03010100` 영속
- `src/api/condition.py` 영역 grep 1건 영구 영속 (변경 시 silent 결함 영구 차단)

### G-AST2 — DB schema 영속
- migration 033 영역 영구 보존 (사이클 122 적용 영역 영구 영속)
- 사이클 123+ 신규 컬럼 추가 시 별도 migration 의무

### G-AST3 — lifecycle race 차단 패턴 영속
- `_stock_master_daily_load_task_loop` 영역 = start() 직후 즉시 1회 + while 루프 (사이클 106 답습)
- AST 정적 가드 = `while True:` 영역 영구 영속 + `await self._wait_until(...)` 영역 영구 영속

### G-AST4 — task cancel 목록 영속
- 사이클 79 G-AST2 영속 = `_stock_master_daily_load_task` cancel 목록 포함 영구 영속

---

## 5. 영속 의무 매트릭스

- 사이클 17 OPSP0002 backoff 영속 (300s, KIS LMS chain 차단)
- 사이클 30 trade_history ON CONFLICT UPDATE 영속 (PK 복합 키 패턴 답습)
- 사이클 32 R4 universe guard 영속 (보유/익일청산 절대 보호)
- 사이클 38 명문화 영속 (scanner 매수 진입 전 영역 한정)
- 사이클 49 VCP Pullback ATR ZigZag 영속 (DB 조회 영역 변경만 + 알고리즘 무변경)
- 사이클 78/79 G-AST1/G-AST2 영속 (task lifecycle + flush 영역)
- 사이클 81 G-AST1 raw JSONB merge 영속
- 사이클 83/91/97/107 50ms sleep 영속 (KIS LMS chain 안전 마진)
- 사이클 84 Supabase MCP `apply_migration` 영속 (운영 DB 적용 영역)
- 사이클 88 G-REJECT 영속 (graceful 영역 단위 의무)
- 사이클 101+106 `_full_universe_load_*` lifecycle race 차단 영속
- 사이클 107 inquire_stock_basics merge 패턴 영속
- 사이클 117 basDd 전일 영업일 영속
- CLAUDE.md "절대 깨지 말 것" 8 영역 영속

---

## 6. 매매 안전성 평가

- scanner 단계 매수 진입 전 일봉 데이터 조회 영역 영구 영속
- 매도/익일청산/15:20 강제청산 hot path 무관 영구 영속
- 사이클 49 VCP Pullback 영속 (DB 조회 영역 변경만 + 알고리즘 무변경)
- 사이클 88 G-REJECT 영속 (graceful 영역 단위)
- 사이클 32 R4 영속 (보유/익일청산 절대 보호)

---

## 7. 회귀 가드 카운트

- 영역 1 (DB): HIGH 5 + MEDIUM 2 = 7
- 영역 2 (API 재사용): MEDIUM 1 = 1
- 영역 3 (스케줄러): HIGH 3 + MEDIUM 3 = 6
- 영역 4 (AST): AST 4 = 4
- **총 18 케이스**

---

## 8. 다음 단계

1. domain-expert 자문 (A1~A6) 완료 의무
2. 사용자 결정 (Q1~Q4) 확정 의무
3. Phase 2.5 분해 (영역 1~4) 후 tdd-engineer Red 명세 정밀화
4. backend-dev Green 구현
5. tester verify (백엔드 + 프론트 + flakiness 0 영구 영속)
6. D+1 운영 측정 의무 (2026-06-13 토 또는 다음 영업일 16:00 KST)
