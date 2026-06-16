# 사이클 150 — SUPABASE 용량초과 시정 (3 영역 통합)

사용자 결정 = Q1=A (stock_master_history seq=0/1 단일) + Q3=C (T-150일) + Q4=B (즉시 TDD) + Q5=B (즉시 DROP) + Q6=A (사이클 6 retention 동행 시정).

## Phase 1 진단 결정적 발견

운영 DB 632MB / 500MB tier 초과 확정. 상위 4 테이블 97.4%:
- system_logs 210MB (55일 잔존, 사이클 6 retention 24일 silent 결함)
- stock_master_history 202MB (9.2만 row, 일평균 +1.15만 폭증)
- stock_master_daily 184MB (36.2만 row, T-100일 백필 후 무한 누적)
- stock_master 20MB (정상 영역)

목표 영역 = 632MB → ~170MB (73% 절감, 34% tier 사용률).

## 영역 A — stock_master_history seq=0/1 단일 정책 (사이클 84 재설계)

### 신규 migration 036

`supabase/migrations/036_stock_master_history_seq.sql` 신규:

1. **기존 데이터 DROP** (사용자 Q5=B 즉시 DROP):
   - `DROP TABLE stock_master_history CASCADE`
   - 92,335 row 즉시 삭제 (변경 추적 영역 = 운영 직접 의존 0)
2. **재생성**:
   - PK 변경 `(ticker, seq)` 단일 영역, `seq INT NOT NULL CHECK (seq IN (0, 1))`
   - 컬럼 정합: ticker / seq / change_type / raw JSONB / changed_at
   - before_raw 폐기 (seq=1 자체가 이전본 영구 영속)
3. **trigger 영역 재설계** (사이클 84 trigger 폐기 후 신규):
   - `INSERT`: seq=0 row 신규 (변경 없음)
   - `UPDATE`: `OLD.raw IS DISTINCT FROM NEW.raw` 시에만 발화 — seq=0 → seq=1 shift (UPSERT) + 신규 seq=0 INSERT (NEW.raw)
   - `DELETE`: seq=0/1 모두 삭제
   - **TTL_REFRESH 영역 = trigger 미발화** (`OLD.raw IS NOT DISTINCT FROM NEW.raw` 영역에서 즉시 RETURN, INSERT 0건)
4. **인덱스 영역**: `(ticker, seq)` PK 영역 + `(changed_at DESC)` 진단용 단일

### Supabase MCP 운영 적용 영역

- migration 036 `apply_migration` 호출
- 사이클 145 패턴 답습 (deploy.yml psql 영역은 사이클 145 영속 = 별도 자동 적용 영역 영속)

### CRUD 영역 (`src/db/stock_master.py`)

- `get_history(ticker)` 영역 영구 영속 정합 = 응답 키 변경 (seq=0 최신본 / seq=1 직전본)
- 호출자 없음 → UI 영역 변경 0 (frontend StockMaster.tsx 영향 검증 의무)

## 영역 B — stock_master_daily T-150일 retention cron

### 신규 함수 `src/db/stock_master_daily.py::purge_old_rows()`

```python
async def purge_old_rows(cutoff_date: date, *, protected_tickers: set[str] | None = None) -> dict[str, int]:
    """T-150일 retention. cutoff_date 이전 row DELETE.

    Args:
        cutoff_date: bas_dd < cutoff_date 인 row DELETE.
        protected_tickers: 보유/익일청산 ticker (사이클 32 R4 답습) — 절대 보호.

    Returns:
        {"deleted": int, "protected": int, "elapsed_ms": int}
    """
```

- SQL 영역 = `supabase.table("stock_master_daily").delete().lt("bas_dd", cutoff_iso)` + `not_("ticker", "in", protected_tickers)`
- supabase-py `.lt()` + `.not_("ticker", "in", ...)` SDK 검증 의무
- graceful 영역 영속 (사이클 122 답습)

### 신규 task `src/engine/scheduler.py::_stock_master_daily_purge_task_loop()`

- 매일 16:15 KST 발화 (사이클 122 16:00 적재 직후 1차 청소)
- 사이클 134 `task_loop_helper.run_periodic_task_loop` 영역 활용 (사이클 134 패턴 답습)
- cutoff = `today_kst() - timedelta(days=150)`
- protected_tickers = `_positions.tickers() | _pending_next_day_clear.keys()` 합집합 영역 (사이클 32 R4 답습)
- INFO 로그 `[stock_master_daily_purge] deleted=N protected=M elapsed_ms=K`

### lifecycle hook

- scheduler `__init__` 영역에 task 등록
- `start()` task 생성 + `stop()` task cancel 영역 영속 (사이클 78 G-AST2 답습)
- `_reset_daily_state()` 변경 0 (cron task 영역 = 독립 영역)

## 영역 C — 사이클 6 retention silent 결함 시정

### 결함 영역 (`src/db/system_logs.py::_purge_by_cutoff` L245)

```python
# 현재 (silent 결함)
chain = chain.lt("timestamp", cutoff_iso).limit(MAX_PURGE_BATCH)  # ← .limit() 미지원
# AttributeError 'SyncFilterRequestBuilder' object has no attribute 'limit'
# 24일 연속 silent skip
```

### 시정 영역 옵션 A (subquery)

```python
# 영역 1: subquery로 id 추출 후 DELETE
def _delete():
    # subquery SELECT id LIMIT MAX_PURGE_BATCH
    select_chain = supabase.table("system_logs").select("id")
    if isinstance(level_filter, str):
        select_chain = select_chain.eq("log_level", level_filter)
    else:
        select_chain = select_chain.in_("log_level", list(level_filter))
    select_chain = select_chain.lt("timestamp", cutoff_iso).limit(MAX_PURGE_BATCH)
    rows = select_chain.execute()
    ids = [r["id"] for r in (rows.data or [])]
    if not ids:
        return type("R", (), {"data": [], "count": 0})()

    # 영역 2: DELETE WHERE id IN ids
    del_chain = supabase.table("system_logs").delete().in_("id", ids)
    return del_chain.execute()
```

이 패턴 영역 = supabase-py DELETE chain 영역에서 `.limit()` 우회 + WHERE id IN (배치 영역) 정합.

### 회귀 가드 영역

- AST 영구 가드: `_purge_by_cutoff` 함수 본체에서 `.limit(` 호출 `.delete()` chain 직후 0건 영구 영속
- 실효 검증: mock supabase + 2 단계 호출 (select → delete) 정합

## Red 회귀 가드 (G-150 시리즈)

### G-150-HIST — stock_master_history seq=0/1 (5 케이스)

- G-150-HIST-1 (HIGH): migration 036 영역 영구 영속 (`supabase/migrations/036_stock_master_history_seq.sql` 존재 + DROP TABLE + CHECK seq IN (0, 1))
- G-150-HIST-2 (HIGH): trigger 영역 영구 영속 (`OLD.raw IS DISTINCT FROM NEW.raw` 분기 + TTL_REFRESH 영역 영구 미발화)
- G-150-HIST-3: PK `(ticker, seq)` 영역 영구 영속 (UNIQUE 가드)
- G-150-HIST-4: seq=2+ INSERT 자동 차단 (CHECK constraint)
- G-150-HIST-5: AST `BEFORE_RAW` 컬럼 영구 폐기 영속 (마이그레이션 영역)

### G-150-DAILY — stock_master_daily T-150 cron (5 케이스)

- G-150-DAILY-1 (HIGH): `purge_old_rows(cutoff_date, protected_tickers)` 시그너처 영역 영구 영속
- G-150-DAILY-2 (HIGH): cutoff_date = today_kst() - timedelta(days=150) (T-150일 영구 영속, VCP T-120일 + 30일 안전 마진)
- G-150-DAILY-3: protected_tickers 영역 절대 보호 (사이클 32 R4 답습 — DELETE 0 row)
- G-150-DAILY-4: scheduler 16:15 KST task 영역 영속 (사이클 134 task_loop_helper 답습)
- G-150-DAILY-5: graceful 영속 (예외 시 0 반환 + 로그 영역)

### G-150-PURGE — system_logs purge_old_logs 실효 (4 케이스)

- G-150-PURGE-1 (HIGH): `_purge_by_cutoff` 영역 영구 영속 `.limit(` 호출 `.delete()` chain 직후 0건 (사이클 6 결함 영구 차단)
- G-150-PURGE-2 (HIGH): subquery select + DELETE in_ id 영역 영구 영속
- G-150-PURGE-3: INFO/HIGH 양쪽 영역 영구 영속 정확 cutoff (mock + freezegun)
- G-150-PURGE-4: graceful + 빈 결과 영역 영구 영속 (`type("R", ...)` 또는 동등 short-circuit)

### G-150-SAFETY — 매매 안전성 영구 영속 (3 케이스)

- G-150-SAFETY-1: VCP/donchian/BFB prepare 영역 변경 0 (사이클 38 명문화 영속)
- G-150-SAFETY-2: positions / 익일청산 영역 stock_master_daily 영역 의존 0 (영역 B 영향 0)
- G-150-SAFETY-3: trade_history / daily_performance / positions 영역 미변경 (3 영역 모두 무관)

## 영속 의무 매트릭스

- CLAUDE.md "절대 깨지 말 것" 8 영역 영속 (변경 0)
- 사이클 6 retention 영역 실효 영구 영속 (24일 silent 차단 영속)
- 사이클 32 R4 universe guard 보유/익일청산 절대 보호 (purge_old_rows protected_tickers 답습)
- 사이클 38 명문화 (scanner 매수 진입 전 한정, 매매 hot path 무관)
- 사이클 48 VCP EMA effective_long T-120일 영역 영구 영속 (T-150일 retention 안전 마진)
- 사이클 68 _kst.now_kst_iso() KST 명시 영속 (purge cutoff timestamp 영역)
- 사이클 78 G-AST2 task cancel 영역 영속 (신규 task lifecycle hook)
- 사이클 81 G-AST1 raw JSONB 영역 보호 영속 (raw 폐기 미진행)
- 사이클 84 trigger 영역 재설계 영속 (seq=0/1 단일 정책)
- 사이클 122 stock_master_daily T-100일 백필 영역 영속 (T-150일 retention 정합)
- 사이클 134 task_loop_helper 영역 영속 (scheduler 신규 task 패턴 답습)
- 사이클 145 deploy.yml 자동 migration 영역 영속 (migration 036 자동 적용)

## 비목표 영역

- raw JSONB 폐기 영역 (사이클 150 영역 외, 사이클 81 G-AST1 영속 검증 의무 영역으로 별도 사이클)
- frontend UI 영역 변경 0 (StockMaster.tsx 영역 호환성 유지)
- positions / trade_history / daily_performance / 기타 11 테이블 영향 0
