# 사이클 C1 — 퀀트 재무 데이터 수집·적재 인프라 (Red 메모)

승인 계획: `~/.claude/plans/partitioned-kindling-lollipop.md` (C1 즉시 착수)

**성격**: 매매 무관 인프라 (scanner 매수 진입 전, 사이클 38). 매매 안전성 8영역 diff 0.

## 무엇을 Red 로 못박는가 (4 산출물)

### 1. migration `supabase/migrations/041_stock_master_financial.sql` (신규)
`034_stock_master_master_raw.sql` · `039_stock_master_numeric_generated_cols.sql` 답습 (IF NOT EXISTS idempotent).
- **Red 근거**: 파일 자체가 없음 → `Path(...).exists()` FAIL.
- 스키마 정본: PK `(ticker, stac_yymm, div_cls)` + 손익 5 (`sale_account/sale_totl_prfi/bsop_prti/thtr_ntin/depr_cost`)
  + 대차 7 (`cras/fxas/total_aset/flow_lblt/total_lblt/total_cptl/cpfn`)
  + 수익성 2 (`cptl_ntin_rate/sale_totl_rate`) + 안정성 2 (`lblt_rate/crnt_rate`) + 기타 2 (`ebitda/ev_ebitda`)
  + `raw JSONB NOT NULL DEFAULT '{}'::jsonb` (사이클 81 G-AST1 원본 보존) + `refreshed_at TIMESTAMPTZ NOT NULL DEFAULT now()`.
- 인덱스 `ix_smf_ticker_div ON (ticker, div_cls, stac_yymm DESC)`.
- **가드**: `CREATE TABLE IF NOT EXISTS` + `CREATE INDEX IF NOT EXISTS` (재적용 안전, 034/039 답습).

### 2. `src/db/stock_master_financial.py` (신규, `stock_master_daily.py` 100% 미러)
- **Red 근거**: 모듈 부재 → `import src.db.stock_master_financial` ModuleNotFoundError → 전체 함수 테스트 FAIL.
- `_safe_float` / `_safe_int` (daily 답습, 빈 값/예외 graceful).
- `async def upsert_financial_batch(ticker, rows: list[dict]) -> int`:
  - 100건 chunk (`_BATCH_SIZE=100`, daily 답습), `on_conflict="ticker,stac_yymm,div_cls"`.
  - graceful — 개별 chunk 실패 시 다음 chunk 진행 + 성공 카운트만 반환 (사이클 88 G-REJECT).
  - **KST `refreshed_at`**: `_kst.now_kst_iso()` (사이클 68). raw 원본 병합 보존.
- `async def get_financial_series(ticker, div_cls="0", limit=3) -> list[dict]`:
  - `execute_with_retry` 경유 (`src/db/supabase.py` 사이클 187, daily read 4함수 패턴).
  - `stac_yymm DESC` 정렬, graceful → `[]`.
- `async def max_stac_yymm(ticker, div_cls="0") -> str | None`: 백필/증분 분기 키, graceful → None.
- `async def count_all() -> int`: 진단, graceful → 0.

### 3. `src/api/finance.py` (신규, `condition.py::fetch_daily_candles_ranged` 답습)
- **Red 근거**: 모듈 부재 → import FAIL.
- KIS 정본 확인 (docs/kis/domestic-stock-info.md + 계획 표): 5 TR **모두 output=list**, 각 원소 `stac_yymm` 키 + 필드:
  - income `/uapi/domestic-stock/v1/finance/income-statement` **FHKST66430200** → sale_account/sale_totl_prfi/bsop_prti/thtr_ntin/depr_cost
  - balance `/uapi/domestic-stock/v1/finance/balance-sheet` **FHKST66430100** → cras/fxas/total_aset/flow_lblt/total_lblt/total_cptl/cpfn
  - profit `/uapi/domestic-stock/v1/finance/profit-ratio` **FHKST66430400** → cptl_ntin_rate/sale_totl_rate
  - stability `/uapi/domestic-stock/v1/finance/stability-ratio` **FHKST66430600** → lblt_rate/crnt_rate
  - other `/uapi/domestic-stock/v1/finance/other-major-ratios` **FHKST66430500** → ebitda/ev_ebitda
- 요청 파라미터: `FID_DIV_CLS_CODE`(0=년/1=분기) + `fid_cond_mrkt_div_code="J"` + `fid_input_iscd=ticker`.
- **TR_ID 컨벤션**: 5 TR 모두 **FH 접두사 = 실전/모의 동일** → `settings.get_tr_id()` **사용 금지**
  (`V`+base[1:] 변환이 `FH...`→`VH...` 로 깨짐). `condition.py::fetch_daily_candles_ranged` 가
  `kis_get_quote(URL, "FHKST03010100", ...)` 처럼 FH TR_ID 를 **직접 하드코딩**하는 정본 답습.
- `async def fetch_financial_tr(ticker, tr_key, div_cls="0") -> list[dict]`:
  단일 TR, output list 반환, 6자리 ticker 가드 (`ValueError`), graceful → `[]`.
- `async def fetch_all_financials(ticker, div_cls="0") -> list[dict]`:
  5 TR 순차 (각 사이 `asyncio.sleep(0.05)` 사이클 17) → `stac_yymm` 키로 join → 정규화 row list (스키마 컬럼명)
  + raw 병합. **개별 TR 실패 시 그 필드만 결측, 나머지 계속** (사이클 88 graceful).

### 4. `src/api/base.py` Path 화이트리스트 (시세성 풀)
- **Red 근거**: 현재 `_QUOTE_ALLOWED_PATHS` 7 path 에 finance 5 path 부재 → 화이트리스트 단언 FAIL.
  누락 시 `_request_via_quote_pool` 이 `QuotePoolPathError` raise (사이클 109 선례 재현 위험).
- 추가 대상 5 path:
  `/uapi/domestic-stock/v1/finance/income-statement`, `.../balance-sheet`,
  `.../profit-ratio`, `.../stability-ratio`, `.../other-major-ratios`.
- **가드**: `test_cycle109_market_cap_allowlist.py` 답습 — frozenset 엔트리 5 path 존재 단언
  + AST/source 텍스트 존재 검사 (재도입/누락 영구 방지).

## 회귀 가드 매트릭스
- PK `(ticker,stac_yymm,div_cls)` conflict 갱신 (`on_conflict` 문자열 + upsert 경로).
- graceful skip (개별 chunk 실패 → 성공분만 카운트).
- KST `refreshed_at` (`now_kst_iso` 경유, 사이클 68).
- Path 화이트리스트 5 path (frozenset + AST).
- fetch output=list 파싱 (5 TR 각 output 원소 → 정규화).
- 5 TR join stac_yymm 정합 (동일 stac_yymm 원소들이 한 row 로 병합).
- 개별 TR 실패 graceful (한 TR `[]` → 그 필드만 결측, 나머지 필드 채워짐).

## 테스트 위생
- respx 로 5 TR 응답 시리즈 합성 (output=다기간 list, 최소 2기 stac_yymm, 실제 KIS 필드명).
  `finance.py` 가 `kis_get_quote` 경유 → 단위 테스트는 `kis_get_quote` mock (AsyncMock, TR 별 dispatch)
  으로 격리 (cycle172 fetch 테스트 패턴 답습). 별도 respx 시리즈 테스트로 output=list 계약 못박음.
- `freeze_time` 안 DB read 태우지 않음 (사이클 187 hang 교훈, `src/db/CLAUDE.md`). DB 테스트는 supabase mock.

## 매매 안전성
전 산출물이 scanner 매수 진입 전 유니버스/prepare 인프라 (사이클 38).
`api/order.py`·`balance.py`·`risk.py`·`order_engine.py`·`realtime/`·`auth/`·`session.py`·`strategy_registry.py` 절대 미변경.
finance 모듈은 매매 hot path 에서 import 0.

## Red 상태 기대
- migration 파일 부재 → FAIL
- `src.db.stock_master_financial` import 실패 → FAIL
- `src.api.finance` import 실패 → FAIL
- base.py 5 path 부재 → 화이트리스트 단언 FAIL
= 전부 "production 코드 미작성" 으로 인한 실패 (테스트 설계 오류 아님).
