# 사이클 192 — stock_master_daily purge 루프 배치 전환 (날짜 슬라이스)

## 결함 (운영 실증, 2026-07-04 확정)

`src/db/stock_master_daily.py::purge_old_rows` 가 **6/16 도입 이래 전 실행 실패** (system_logs
`[stock_master_daily_purge] 실패 graceful` 누적 515건, 최근 매일 1~4회 = 매 실행).
운영 DB 실측: 총 462,062행 / cutoff(2025-11-15) 이전 **47,924행** 적체 (사이클 172 VCP 220일
백필분 노화, 매일 ~3.5K행씩 증가) → Supabase 무료 500MB 용량 재초과 경로.

### 근본 원인 (추정 — 교차 증거)

- 현재 구현 = `supabase.table(...).delete().lt("bas_dd", cutoff).execute()` **단일 bulk DELETE**.
- supabase-py DELETE 기본 `returning="representation"` → 47,924행 × raw JSONB 를 응답으로 반환
  시도 → 응답 비대/timeout 으로 예외 (raw SQL 동일 DELETE 는 즉시 성공 — 메인 세션 실증,
  47,924행 드레인 완료 = Postgres 측 문제 아님, PostgREST 경유 계층 결함).
- `logger.exception` 이라 DB 메시지에 예외 타입 미부착 (사이클 190 계측 교훈 미적용 영역)
  → 원인 규명 지연.
- 사이클 175 가 system_logs `_purge_by_cutoff` 를 루프 배치로 시정했으나 stock_master_daily
  purge 는 미적용 잔존 (동일 계열 3번째: 사이클 6 → 150 → 175 → **192**).

### 메인 세션 즉시 완화 (2026-07-04 완료)

cutoff 이전 47,924행 raw SQL 드레인 완료 (보유 0/익일청산 0 = 보호 예외 없음).
→ 시정 후 steady-state 는 하루 1날짜(~3.5K행) 삭제만 남음.

## 시정 설계 (사이클 175 루프 배치 패턴 답습 + 복합 PK 적응)

`stock_master_daily` 는 PK `(ticker, bas_dd)` 복합 — id 컬럼 없음 → 사이클 175 의
`SELECT(id) + DELETE in_(ids)` 직답습 불가. **날짜 슬라이스 루프** 채택:

```python
PURGE_MAX_DATE_ITERATIONS = 500  # 모듈 상수 — 런어웨이 가드 (잔여는 다음 실행이 드레인)

# purge_old_rows 내부:
deleted = 0
for _ in range(PURGE_MAX_DATE_ITERATIONS):
    # (1) 가장 오래된 삭제 대상 날짜 1건 조회 — protected 제외 의무!
    q = supabase.table(TABLE_NAME).select("bas_dd").lt("bas_dd", cutoff_iso)
    if protected_tickers:
        q = q.not_.in_("ticker", list(protected_tickers))
    rows = q.order("bas_dd").limit(1).execute().data
    if not rows:
        break  # drained
    oldest = rows[0]["bas_dd"]
    # (2) 그 날짜 전체 DELETE — returning minimal (응답 비대 근본 차단) + count exact
    chain = supabase.table(TABLE_NAME).delete(count="exact", returning="minimal").eq("bas_dd", oldest)
    if protected_tickers:
        chain = chain.not_.in_("ticker", list(protected_tickers))
    result = chain.execute()
    deleted += int(result.count or 0)
```

### 핵심 불변식 / 함정

1. **SELECT 에도 protected 제외 의무** — 누락 시 protected 종목 row 가 남은 날짜를 SELECT 가
   계속 반환 → 같은 날짜 무한 재선택 → MAX_ITERATIONS 공회전 (never-drain 회귀).
2. **DELETE `returning="minimal"` 의무** — 응답 비대 근본 원인 차단. `count="exact"` 로 삭제
   수 집계 (기존 반환 계약 `{"deleted", "protected_count", "elapsed_ms"}` 보존).
3. **시그니처 불변**: `purge_old_rows(cutoff_date, *, protected_tickers=None)` (G-150-DAILY-1).
4. **graceful 보존 + 계측 보강**: 루프 중 예외 → ERROR 로그에
   `type(exc).__name__: str(exc)[:150]` 부착 (사이클 190 패턴) + **부분 누적 deleted 반환**
   (기존 "0 반환" 은 첫 호출 실패 케이스에 한해 자연 보존 — deleted=0 누적이므로).
   `logger.exception` 유지 (write_log 직접 호출 금지 — 사이클 72).
5. **execute_with_retry 미경유 유지** — 쓰기 함수 (G-187-A2 AST 가드 영속).
6. **asyncio.to_thread 위임 유지** — 동기 SDK 정책. 루프 iteration 단위 to_thread.
7. cutoff/`DAILY_RETENTION_DAYS=230`/16:15 task/scheduler 호출부 **변경 0**.
8. 매매 안전성 무영향 — db 모듈 + 정산 후 16:15 task 한정, 매매 hot path 0.

## 회귀 가드 (Red 요구)

- **P-1 (HIGH)**: backlog 3날짜 → 루프 3 iteration + deleted 합산 정확 + drained 후 break
  (SELECT 빈 결과 시 종료).
- **P-2 (HIGH)**: DELETE 체인이 `returning="minimal"` 로 생성 — bulk `.lt()` DELETE 잔존 0
  (AST: `_delete`/purge 본체에 `delete()` 무인자 + `.lt(` 직결 패턴 금지, `.eq("bas_dd"` 필수).
- **P-3 (HIGH, never-drain 가드)**: protected_tickers 지정 시 **SELECT 와 DELETE 양쪽**
  `not_.in_("ticker", ...)` 적용 — SELECT 쪽 누락 시 FAIL 하도록 mock 시나리오 구성
  (protected 만 남은 날짜 → SELECT 가 제외해서 다음 날짜로 진행하는지).
- **P-4**: PURGE_MAX_DATE_ITERATIONS 상수 존재 + 루프 cap (초과 backlog 시 부분 삭제 후 정상 반환).
- **P-5**: 예외 시 graceful — 부분 누적 deleted 반환 + ERROR 로그 발화 + 예외 타입 문자열 포함.
- **P-6**: 빈 테이블(삭제 대상 0) → SELECT 1회 + DELETE 0회 + deleted=0.
- **P-7 (AST)**: purge_old_rows 가 execute_with_retry 미경유 영속 (G-187-A2 와 중복이면 생략 가).

## 의미 전환 (사이클 66 K-2)

- `test_cycle150_supabase_capacity.py::TestG150DailyProtectedTickers::test_g150_daily_3_protected_tickers_excluded`
  — 기존 mock 이 `delete().lt().not_.in_()` 단일 체인 형상 고정 → 루프 배치 형상으로 갱신
  (intent 보존: protected 절대 보호). 기타 G-150-DAILY-1/2/4/5 는 무변경 PASS 예상 (5 는
  실측 확인).

## 테스트 파일

- `tests/unit/db/test_cycle192_daily_purge_loop_batch.py` 신규
- `tests/unit/ast/test_cycle192_ast_purge_loop.py` 신규 (P-2/P-7)
