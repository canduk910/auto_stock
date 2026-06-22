# 사이클 172 — stock_master_daily 220일 확보 (LOW~MEDIUM, 데이터 plumbing)

> 승인 설계: `/Users/koscom/.claude/plans/funnel-vast-wolf.md` (사이클 172 절 + §1 매트릭스 + §2 부족분 확보 + §3 어댑터 정독)
> 선행: 사이클 173 prepare DB일봉 전환의 데이터 의존성 해소.
> **prepare/매수 target 미변경** — 데이터 적재/조회 plumbing 한정.

## 배경 (재도출 말 것)

- 전략별 최대 일봉 lookback = **VCP 220일**. 나머지 5전략 ≤65일 (현 retention 150 충분).
- 현재 `stock_master_daily`: backfill T-100 / retention T-150 → **VCP universe (KOSPI200∪KOSDAQ150, 348종목)만 220일 부족**.
- KIS `FHKST03010100` (국내주식기간별시세) = `FID_INPUT_DATE_1/2` 기간 조회 + **호출당 최대 100건** → 날짜 윈도우 ×3 페이지네이션으로 220일 backfill.

## KIS MCP 정본 (재확인 완료, 2026-06-22)

- TR_ID = `FHKST03010100` (실전/모의 동일, FH 시세성 풀)
- params: `FID_COND_MRKT_DIV_CODE="J"` + `FID_INPUT_ISCD` + `FID_INPUT_DATE_1`(시작) + `FID_INPUT_DATE_2`(종료) + `FID_PERIOD_DIV_CODE="D"` + `FID_ORG_ADJ_PRC`
- **호출당 최대 100건** (정본 docstring "최대 100건")
- output2 = stck_bsop_date/stck_clpr/stck_oprc/stck_hgpr/stck_lwpr/acml_vol/acml_tr_pbmn/flng_cls_code/prtt_rate
- **`FID_ORG_ADJ_PRC` = `"0"`** (기존 `_fetch_daily_candles_and_cache` 실측 정합 — 정본 샘플은 "1" 예시이나 본 코드베이스는 사이클 14부터 "0" 수정주가 사용. **173 동등성 게이트 보장을 위해 기존과 동일 "0" 채택** = 설계 문서 괄호 "기존 정합" 의도)

## 구현 명세

### 1. 분할 fetch (`src/api/condition.py`)

신규 `fetch_daily_candles_ranged(ticker, start_yyyymmdd, end_yyyymmdd) -> list[dict]`:
- 단일 100일 윈도우 KIS 호출 (`kis_get_quote(DAILY_PRICE_URL, "FHKST03010100", params)` 경유 = Rate Limit/메트릭, 사이클 17 KIS LMS chain).
- params = `FID_INPUT_DATE_1=start` / `FID_INPUT_DATE_2=end` / `FID_ORG_ADJ_PRC="0"` / 나머지 정본 정합.
- output2 (최신순) + `stck_bsop_date` 빈 placeholder 제거. **memcache/single-flight 없음** (backfill 전용, 사이클 173에서 호출 0건 — 16:00 task만).
- 6자리 ticker 가드 + graceful (예외 전파, 호출자 graceful).

신규 backfill 헬퍼 `fetch_daily_candles_backfill(ticker, total_days=220, *, window=100) -> list[dict]`:
- 220일을 100일 윈도우 ×3 (T-230~T-130 / T-130~T-30 / T-30~T) 순차 호출 + 병합.
- 중복 `stck_bsop_date` dedupe (윈도우 경계 겹침 제거) + bas_dd DESC 정렬.
- 윈도우 간 50ms sleep (사이클 17 KIS LMS chain 답습).
- `total_days`/`window` 기반 윈도우 개수 동적 산출 (`ceil(total_days/window)`).
- 기존 `fetch_daily_candles` (memcache 5분, single-flight) **변경 0** — 별도 함수.

### 2. `src/engine/scanner.py::_stock_master_daily_load_once`

- VCP universe (`is_kospi200 OR is_kosdaq150`) 종목 중 DB 깊이 < 220 이면 **220일 backfill 분기** (`fetch_daily_candles_backfill`).
- 나머지 종목 = 현행 T-100 backfill/증분 유지 (회귀 0).
- VCP universe 판별: `list_all()` row 의 `is_kospi200`/`is_kosdaq150` 컬럼 (`.select("*")` 이미 포함) 사용 — 별도 쿼리 0건.
- graceful (사이클 88 G-REJECT) + 진행 emit + `_DAILY_LOAD_RATE_LIMIT_SLEEP_SECS` Rate Limit.
- **장중 자동 실행 금지** — 16:00 daily task (장 마감 후) + 수동 trigger 경로만 (변경 0, 기존 task lifecycle 그대로).

### 3. `src/db/stock_master_daily.py`

- `DAILY_RETENTION_DAYS` 150 → **230** (220 + 10 마진). `purge_old_rows` 로직 불변 (상수만, "230일 지난 것만 삭제").
- 신규 어댑터 `get_recent_daily_normalized(ticker, days, *, min_required=None) -> list[dict]`:
  - DB row 의 `raw` JSONB (KIS 원본 키 `stck_clpr` 등 보존) 그대로 반환 → 173 prepare 의 `c.get("stck_clpr")` 무변경 사용.
  - DB 부족 (`< min_required`) 시 `fetch_daily_candles` KIS 폴백 (기존 `get_recent_daily_with_fallback` 위임).
  - DB row 에 `raw` 키 없으면 row 자체 반환 (graceful) — 단 정상 적재 row 는 `_candle_to_row` 가 `raw` 항상 포함.
  - **172는 어댑터 정의만** — prepare 연결은 173 (호출처 0).

## 회귀 가드 (목표 ≈ 22 케이스)

### condition (분할 fetch)
- RANGE-1: `fetch_daily_candles_ranged` 100건 경계 (정본 params 정합 + output2 파싱)
- RANGE-2: `FID_ORG_ADJ_PRC="0"` 기존 정합 (AST/respx)
- RANGE-3: `FID_INPUT_DATE_1/2` start/end 전달
- RANGE-4: 6자리 ticker 가드 + graceful 빈 응답
- BACKFILL-1: 3 윈도우 호출 (T-230~T-130 / T-130~T-30 / T-30~T)
- BACKFILL-2: 중복 bas_dd dedupe (윈도우 경계 겹침 → 유니크)
- BACKFILL-3: bas_dd DESC 병합 정렬
- BACKFILL-4: `fetch_daily_candles` 변경 0 (memcache/single-flight 영속 AST)

### scanner (VCP universe 분기)
- SCAN-1: VCP universe (is_kospi200) DB < 220 → backfill 분기 호출 (`fetch_daily_candles_backfill`)
- SCAN-2: VCP universe (is_kosdaq150) 동일
- SCAN-3: 비 VCP universe → 현행 100일 `fetch_daily_candles` 유지 (회귀)
- SCAN-4: VCP universe DB ≥ 220 → 증분 유지 (재 backfill 금지)
- SCAN-5: graceful (backfill 실패 → 다음 ticker 진행)

### db (retention + 어댑터)
- RET-1: `DAILY_RETENTION_DAYS == 230` 상수
- RET-2: `purge_old_rows` 로직 불변 (cutoff = today - 230)
- ADAPT-1: `get_recent_daily_normalized` DB 충분 → raw JSONB 반환 (KIS 키 `stck_clpr` 보존)
- ADAPT-2: DB miss (`< min_required`) → KIS `fetch_daily_candles` 폴백
- ADAPT-3: `min_required=None` 기본값 (days//2, 10 max — 위임 정합)
- ADAPT-4: raw 키 부재 graceful

### SAFETY
- SAFETY-1 (HIGH): 매매 무관 — `git diff` risk/order_engine/realtime/auth/api/order = 0 (AST import 0)
- SAFETY-2 (HIGH): prepare 미변경 — 5 전략 prepare 매수 target 불변 (어댑터 호출처 0)
- SAFETY-3: 사이클 81 G-AST1 raw JSONB 분리 (어댑터 raw 그대로 반환, 변형 0)

### 의미 전환 (사이클 66 K-2 패턴)
- `test_cycle150_supabase_capacity.py::test_g150_daily_2_retention_days_constant` — `DAILY_RETENTION_DAYS == 150` → `== 230` 갱신 (사이클 150 G-150-DAILY-2 의미 전환, 사이클 172 retention 확장 의무).

## 매매 안전성

- 데이터 적재/조회 한정. scanner `_stock_master_daily_load_once` = 16:00 daily task (매수 진입 무관, 사이클 38/122).
- 어댑터 = 정의만 (prepare 미연결). **실제 220일 backfill 은 장중 실행 금지** — 회귀 테스트는 mock KIS 만, 운영 적재는 push 후 16:00 task 자연 발화.

## 검증

- `python -m pytest -q` 전체 PASS (현 3,134 기준) flakiness 0.
- `git diff -- src/engine/risk.py src/engine/order_engine.py src/realtime/ src/auth/ src/api/order.py` = 0.
- 운영 DB 220일 실측은 push 후 16:00 task 발화 후 D+1 인계.

## 커밋/푸시 금지 + 실제 backfill 실행 금지

구현·검증·문서까지만. `git commit`/`git push` 절대 금지. 운영 DB 실제 220일 적재 금지 (장중). 변경은 작업 트리에 둔 채 보고만.
