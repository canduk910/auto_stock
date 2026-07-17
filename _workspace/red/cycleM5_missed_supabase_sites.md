# 사이클 M5 (Red) — 누락 사이트 전환 (split-brain 시정)

승인 계획: `~/.claude/plans/partitioned-kindling-lollipop.md` (Supabase→RDS 이전).
브랜치: `db-migration-rds`. M0~M3(17 db 모듈) Green 완료.

## 문제 (컷오버 중 발견)

초기 탐색이 놓친 **src/db/ 밖 4개 파일의 직접 `supabase.table()` 호출**이 여전히
Supabase 를 읽고/써서 RDS 와 split-brain. M0~M3 는 db 모듈을 전부 pg(asyncpg) 로 전환했으나
아래 4파일이 `from src.db.supabase import supabase` 로 Supabase 를 직접 접근 → auto_start 등을
Supabase 에서 읽으면 RDS 에 쓴 값과 불일치.

전수 실측 (`grep -rE "from src\.db\.supabase import|supabase\.(table|rpc)\(" src/ | grep -v src/db/supabase.py`):

```
src/engine/log_analysis_engine.py:29  from src.db.supabase import supabase
src/engine/log_analysis_engine.py:122 supabase.table("system_logs")            (읽기, 페이지드 SELECT)
src/engine/scheduler.py:413           from src.db.supabase import supabase
src/engine/scheduler.py:414           supabase.table("system_config")...auto_start (읽기)
src/engine/scheduler.py:3738          from src.db.supabase import supabase
src/engine/scheduler.py:3739          supabase.table("trade_history").update(...)  (쓰기)
src/engine/scheduler.py:3755          from src.db.supabase import supabase as _sb  (읽기)
src/engine/boot_manager.py:187        from src.db.supabase import supabase as _sb  (읽기)
src/engine/boot_manager.py:239        from src.db.supabase import supabase
src/engine/boot_manager.py:241        supabase.table("trade_history").update(...)  (쓰기)
src/engine/boot_manager.py:268        from src.db.supabase import supabase as _sb2 (읽기)
src/routes/strategies.py:8            from src.db.supabase import supabase
src/routes/strategies.py:114          supabase.table("system_config")...auto_start (읽기)
src/routes/strategies.py:124          supabase.table("system_config").upsert(auto_start) (쓰기)
```

## 전환 대상 (정확한 사이트 + 최소 전환)

### 1. `src/routes/strategies.py`
- L8 `from src.db.supabase import supabase` 제거.
- L112-118 `get_auto_start` → **`system_config.get_auto_start()`** (M3b 헬퍼 존재) 호출.
  반환 dict `{auto_start: bool}` 계약 보존.
- L121-128 `set_auto_start` → **`system_config.set_auto_start(req.enabled)`**.
  ⚠️ `set_auto_start` 헬퍼가 system_config 에 **부재** → **추가**(`_set_bool` 패턴 답습,
  `{"value": bool}` JSONB upsert + KST). 응답 메시지 계약 보존
  (`"자동 매매 시작 {'활성화' if enabled else '비활성화'}"`).

### 2. `src/engine/scheduler.py`
- L413-414 `_is_auto_start_enabled` auto_start read → `system_config.get_auto_start()`.
  부팅 매매 스케줄 결정 — 계약 보존 필수 (예외 시 `settings.auto_start` .env 폴백 유지).
- L3737-3745 `_sync_positions_from_balance` — ticker별 PENDING BUY→COMPLETED 일괄 UPDATE →
  **`trade_history.mark_pending_buys_completed(ticker)`** 신규 함수 (pg.execute UPDATE).
  boot_manager L239-245 와 동일 로직 → 공통 함수화. graceful(except pass) 보존.
- L3754-3764 특정 ticker 최근 BUY strategy 조회 →
  **`trade_history.get_recent_buy_strategy(ticker)`** 신규 함수 (pg.fetch, ORDER timestamp DESC LIMIT 1).
  기존 `_lookup_strategy_from_trade_history` 는 order_no + PENDING/PARTIAL 필터라 부적합
  (여기는 order_no 무관 최근 BUY 아무 status). graceful(None) 보존.

### 3. `src/engine/boot_manager.py`
- L186-196 특정 ticker 최근 BUY strategy 조회 → **`trade_history.get_recent_buy_strategy(ticker)`** 재사용.
  graceful 보존.
- L238-247 ticker별 PENDING BUY→COMPLETED 일괄 갱신 (kis_tickers 루프) →
  **`trade_history.mark_pending_buys_completed(ticker)`** 재사용. graceful 보존.
- L267-286 오늘 BUY (ticker, strategy) 조회 (`gte("timestamp", today.isoformat())`) →
  **`trade_history.get_today_buys_ticker_strategy()`** 신규 함수 (pg.fetch).
  ⚠️ `+09:00` KST 계약 (사이클53) 보존 — `today.isoformat()` (TZ-naive) → `_today_kst_iso()`
  (`+09:00` 명시) 로 시정. (기존 코드는 TZ-naive 라 KST 00:00~09:00 누락 버그 잠재 — 신규 함수는
  `_today_kst_iso()` 사용 = KST 정합.)

### 4. `src/engine/log_analysis_engine.py`
- L29 import + L122 `supabase.table("system_logs")` 페이지드 SELECT →
  **`pg.fetch`** (ASC-ordered, 시간 윈도우, LIMIT/OFFSET 페이징). timestamp 는 `to_char(...,'+09:00')`
  str 캐스트 (사이클53 B-4 계약). M 노트가 "insert"라 했으나 실제는 **읽기(paged SELECT)** —
  `_fetch_logs_in_range` 의 페이징/윈도우/컬럼(timestamp,log_level,message) 계약 보존.

## Red 요구 (이 증분)

각 사이트 단위 테스트: 전환 후 **supabase 미참조** + 올바른 db함수/pg 호출 + 반환/graceful 계약 보존.

핵심 불변식:
- **auto_start get/set 왕복** (routes+scheduler 동일 값 = split-brain 해소).
- **trade_history 갱신/조회 KST/status 계약** (PENDING→COMPLETED, 오늘 BUY `+09:00`).
- **log 분석 SELECT** (페이징/윈도우/컬럼 보존).

전수 가드 (HIGH):
`grep -rE "from src\.db\.supabase import|supabase\.(table|rpc)\(" src/ | grep -v src/db/supabase.py`
= **0건** (텍스트/AST 가드, 향후 재발 영구 차단). = 이전의 진짜 마지막.

매매 안전성 8영역 diff 0 (이 4파일은 8영역 밖이나, risk/order_engine/realtime/auth/api/order.py/
session/scanner/strategy_registry diff 0 확인).

신규 헬퍼 단위 테스트:
- `system_config.set_auto_start(enabled)` — `_upsert_value(auto_start, {"value": bool})`.
- `trade_history.mark_pending_buys_completed(ticker)` — pg.execute UPDATE (status PENDING→COMPLETED, BUY).
- `trade_history.get_recent_buy_strategy(ticker)` — pg.fetch (최근 BUY strategy, graceful None).
- `trade_history.get_today_buys_ticker_strategy()` — pg.fetch (오늘 BUY, `+09:00` KST 바인딩).

## Red 유효성

production 미변경 → 신규 헬퍼 부재 (AttributeError) + supabase 잔존 사이트 4파일 grep 0건 위반 → FAIL.

## 테스트 파일
- `tests/unit/db/test_cycleM5_new_helpers.py` — 신규 4 헬퍼 (system_config.set_auto_start + trade_history 3).
- `tests/unit/routes/test_cycleM5_strategies_auto_start.py` — routes 전환 + 왕복.
- `tests/unit/engine/test_cycleM5_scheduler_pg_sites.py` — scheduler 3 사이트.
- `tests/unit/engine/test_cycleM5_boot_manager_pg_sites.py` — boot_manager 3 사이트.
- `tests/unit/engine/test_cycleM5_log_analysis_pg.py` — log_analysis_engine SELECT.
- `tests/unit/ast/test_cycleM5_no_supabase_outside_db.py` — 전수 가드 (HIGH) + 8영역 diff 0.
