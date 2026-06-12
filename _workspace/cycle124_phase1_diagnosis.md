# 사이클 124 Phase 1 진단 — 종목마스터 UI 확장 + 지침 영구 가드

날짜: 2026-06-13 (토)
team-leader: Phase 1 진단 (Auto Mode 채택, 즉시 진행)
위험 등급: **LOW** (UI 가시화 + READ-ONLY GET endpoint 신규 한정, 매매 hot path 무관)

## 1. 사용자 보고 (verbatim)

> "UI의 종목마스터 메뉴에서 보여주는 정보가 너무 제한적이야. 종목마스터 데이터 수집을 정확히 확인하려면 종목마스터와 관련된 내역을 조회할 수 있는 UI도 투명하게 내용을 보여줘야해. 이제 전략에서 종목마스터 데이터를 참고하기로 한만큼 종목마스터에 대한 수집데이터가 추가될 때마다 UI에도 보여줄 수 있도록 작업 완료 후에는 지침에도 추가해줘."

## 2. 사용자 결정 (영속 의무)

- Q1=A 일봉 (T-100일 OHLCV) UI = detail 모달 확장 + 마지막 30일 테이블
- Q2=A 신규 6 키 highlight (hts_avls / acml_tr_pbmn / bfdy_clpr / lstn_stcn / acml_vol / prdy_vrss)
- Q3=A 진단 카드 4 → 8 카드 (with_hts_avls / with_acml_tr_pbmn / total_daily_rows / last_daily_load_at)
- Q4=A 지침 3 영역 동기화 (루트 CLAUDE.md + frontend/CLAUDE.md + src/db/CLAUDE.md)

## 3. 현재 영역 사실 (영구 영속 확정)

### 3.1 백엔드

- **`src/db/stock_master.py::get_stats()` (사이클 84, L113~148)**: 4 카운트만 = `count_all` / `bfdy_clpr_present` / `nxt_tradable_count` / `top_10_recent` — 사이클 116/118/119 신규 매핑 6 키 진단 영역 부재
- **`src/db/stock_master_daily.py` (사이클 122)**: 9 CRUD 영구 영속 + 테이블 적재 정상이나 **UI 노출 0건** (라우트 미연결)
- **`src/routes/stock_master.py`**: 5 GET + 1 POST (사이클 90) — `/api/stock-master/{ticker}/daily` 엔드포인트 부재
- 사이클 90 L-2 화이트리스트 (POST 1개 예외) 영구 영속

### 3.2 프론트엔드

- **`frontend/src/pages/StockMaster.tsx` (사이클 85, ~330L + 사이클 106 갱신)**: 4 카드 + list + detail 모달 + history + refresh 버튼
- **`FIELD_LABELS` 13 키 정의** (L82~L96): ticker / name / excg_dvsn_cd / bfdy_clpr / stck_prpr / stck_hgpr / stck_lwpr / acml_vol / acml_tr_pbmn / nxt_tradable / krx_halted / admin_item / refreshed_at — **신규 6 키 영역 부재** (hts_avls / lstn_stcn / prdy_vrss)
- **`CATEGORY_KEYS` (L71~L77)**: 기본 / 가격 / 거래 / 플래그 / 메타 5 카테고리 — 신규 키 영역 미배치
- **`HIGHLIGHT_KEYS` (L66)**: 핵심 5 키 (bfdy_clpr / acml_vol / nxt_tradable / krx_halted / admin_item) — 사용자 결정 Q2 6 키 영역 미반영
- **사이클 122 stock_master_daily UI 노출 0건** (detail 모달 일봉 탭 부재)

### 3.3 누락 영역 (사용자 보고 "너무 제한적")

- **누락 1**: 사이클 122 stock_master_daily UI 노출 0건
- **누락 2**: 사이클 116/118/119 신규 매핑 6 키 detail 모달 한글 라벨 부재
- **누락 3**: 진단 영역 (with_hts_avls / with_acml_tr_pbmn 비율 / total_daily_rows / last_daily_load_at) 부재

## 4. 시정 영역 정리

### 4.1 백엔드 (backend-dev 발주 4 영역)

#### 영역 1: `GET /api/stock-master/{ticker}/daily?days=30` 신규 라우트

- 위치: `src/routes/stock_master.py`
- 호출 영역: `stock_master_daily.get_recent_daily(ticker, days)`
- 응답: `ApiResponse<list[StockMasterDailyRow]>`
- 라우트 순서 의무: `/{ticker}/history` 정합 (`/{ticker}/daily` *전* + `/{ticker}` *후* 등록)
- query 검증: `days: int = Query(30, ge=1, le=100)` (사이클 122 KIS 1회 호출 한도 100일 영속)

#### 영역 2: `GET /api/stock-master/stats` 응답 확장

- 위치: `src/routes/stock_master.py::get_stock_master_stats`
- 응답 4 → 8 키 (4 신규):
  - `with_hts_avls: int` — `raw.hts_avls` 보유 ticker 카운트 (시총 영역)
  - `with_acml_tr_pbmn: int` — `raw.acml_tr_pbmn` 보유 ticker 카운트 (거래대금 영역)
  - `total_daily_rows: int` — `stock_master_daily.count_all()` 호출
  - `last_daily_load_at: str | null` — `stock_master_daily` 최신 `bas_dd` (max 영역, ISO `+09:00`)

#### 영역 3: `src/db/stock_master.py::get_stats()` 확장

- 위치: `src/db/stock_master.py:113`
- 기존 4 카운트 유지 + 3 신규 카운트 추가 (`with_hts_avls` + `with_acml_tr_pbmn` + `with_bfdy_clpr` 갱신)
- `stock_master_daily.count_all()` + `max_bas_dd()` 활용 (사이클 122 영구 영속)
- graceful (raw miss / hts_avls miss / acml_tr_pbmn miss = 카운트 영역 0 통과)

#### 영역 4: KIS MCP 정본 영역 영구 영속

- 사이클 98 G-DOC1 영속 (`chk_inquire_daily_itemchartprice.py` 정본 인용 의무)
- 사이클 81 G-AST1 영속 (raw JSONB 덮어쓰기 금지)
- 사이클 108 list_by_filter 영역 영구 영속 (Plan Phase A 기존 영역 영구 영속)

### 4.2 프론트엔드 (frontend-dev 발주 5 영역)

#### 영역 1: `frontend/src/types/stock-master.ts` 확장

- `StockMasterStats` 4 키 추가 (`with_hts_avls` + `with_acml_tr_pbmn` + `total_daily_rows` + `last_daily_load_at`)
- `StockMasterDailyRow` 신규 interface (사이클 122 컬럼 10종 + raw)

#### 영역 2: `frontend/src/api/stock-master.ts` 확장

- `fetchDaily(ticker: string, days = 30): Promise<StockMasterDailyRow[]>` 신규 함수
- 백엔드 신규 endpoint 호출 (`/stock-master/${ticker}/daily?days=${days}`)
- ApiResponse `data.data` 추출 영속 (사이클 85 답습)

#### 영역 3: `frontend/src/pages/StockMaster.tsx` 4 → 8 카드 + detail 모달 일봉 탭

**8 카드 영역 영구 영속**:
- 기존 4 카드 영속 (count_all / bfdy_clpr_present / nxt_tradable_count / eager_refresh_today)
- 신규 4 카드:
  - `with_hts_avls` (시총 데이터 보유 종목 수)
  - `with_acml_tr_pbmn` (거래대금 데이터 보유 종목 수)
  - `total_daily_rows` (일봉 적재 총 행 수)
  - `last_daily_load_at` (일봉 마지막 적재 영업일, KST 포맷)

**FIELD_LABELS + CATEGORY_KEYS 확장**:
- 신규 6 매핑 키 한글 라벨:
  - `hts_avls`: "시가총액 (백만원)"
  - `acml_tr_pbmn`: "누적거래대금" (영속, 기존 영역 유지)
  - `bfdy_clpr`: "전일종가" (영속)
  - `lstn_stcn`: "상장주식수"
  - `acml_vol`: "누적거래량" (영속)
  - `prdy_vrss`: "전일대비"
- `CATEGORY_KEYS`:
  - "기본" + ticker / name / excg_dvsn_cd
  - "가격" + bfdy_clpr / prdy_vrss / stck_prpr / stck_hgpr / stck_lwpr
  - "거래" + acml_vol / acml_tr_pbmn
  - "시총/주식수" (신규 카테고리) + hts_avls / lstn_stcn
  - "플래그" + nxt_tradable / krx_halted / admin_item
  - "메타" + refreshed_at
- `HIGHLIGHT_KEYS` (Q2=A 6 키): bfdy_clpr / hts_avls / acml_tr_pbmn / lstn_stcn / acml_vol / prdy_vrss

**detail 모달 일봉 탭** (Q1=A):
- 신규 탭 (기본/상세 + 일봉 2 탭 영역)
- `useQuery({queryKey: ['stock-master-daily', ticker], queryFn: () => fetchDaily(ticker, 30), retry: 1, refetchInterval: 60_000, enabled: !!ticker})` (사이클 65 H3 영속)
- 30 row 테이블 (bas_dd DESC) — 영업일 / 시가 / 고가 / 저가 / 종가 / 거래량 / 거래대금 / 등락률

#### 영역 4: `frontend/src/test/handlers.ts` MSW handler 확장

- `GET /api/stock-master/${ticker}/daily` MSW handler 추가
- `GET /api/stock-master/stats` 응답 확장 (4 → 8 키)

#### 영역 5: `e2e/fixtures/api-mocks.ts` Playwright 확장

- `**/api/stock-master/**/daily*` 라우트 추가
- 사이클 80 hotfix #3 LIFO 정합 영속 = wildcard `**/api/stock-master/**` *전* 등록 + 구체 라우트 *후* 등록 (LIFO 우선 매칭)

### 4.3 회귀 가드 (TDD)

#### 백엔드 8 케이스 (tdd-engineer 발주)

- **G-DAILY1** GET /{ticker}/daily?days=30 정상 응답
- **G-DAILY2** days 인자 범위 422 (1 미만 / 100 초과)
- **G-DAILY3** ticker 미존재 시 빈 list 반환 (graceful)
- **G-STATS1** stats 응답에 with_hts_avls / with_acml_tr_pbmn / total_daily_rows / last_daily_load_at 4 키 포함
- **G-STATS2** stats 신규 키 정확 카운트 (mock raw 영역)
- **G-AST1** AST endpoint 영구 가드 (라우트 정합 + `/{ticker}/daily` *전* + `/{ticker}` *후*)
- **G-AST2** 사이클 122 stock_master_daily 의존성 영속 (`get_recent_daily` + `count_all` + `max_bas_dd` 호출 영역 정적 검증)
- **G-INT1** 통합 시나리오 (4 종목 + 일봉 30 row + stats 확장 키 영역 확인)

#### 프론트엔드 10 케이스 (tdd-engineer 발주)

- **F-CARD8** 8 카드 표시 + 4 신규 카드 데이터 정확
- **F-LABEL6** detail 모달 신규 6 매핑 키 한글 라벨 표시 (Q2=A)
- **F-DAILY1** 일봉 탭 정상 표시 + 30 row 영역
- **F-DAILY2** 일봉 탭 useQuery retry:1 영속 (사이클 65 H3 + AST G-RT)
- **F-DAILY3** ticker 변경 시 enabled true → useQuery 자동 호출
- **F-HIGHLIGHT** 6 키 highlight 영역 (amber 배경 영구 영속)
- **F-CATEGORY** 6 카테고리 영역 (신규 "시총/주식수" 추가)
- **F-MSW** MSW handler 8 키 응답 정확
- **F-AST-MOCK** api-mocks 영역 등록 (사이클 75 G-AST5 영속)
- **F-AST-LIFO** Playwright LIFO 정합 (wildcard 후 등록, 사이클 80 hotfix #3 영속)

## 5. 지침 영구 가드 (3 영역)

### 5.1 루트 `CLAUDE.md` DB 스키마 표 영역

- `stock_master` / `stock_master_daily` 행 뒤에 영구 가드 영역 추가:
  - "stock_master / stock_master_daily 컬럼/raw 키 추가 시 UI detail 모달 + stats 카드 + frontend/CLAUDE.md 동기화 의무 영속"

### 5.2 `frontend/CLAUDE.md` 본문

- 사이클 124 영역 신규 추가:
  - UI 노출 의무 영역
  - FIELD_LABELS / CATEGORY_KEYS / HIGHLIGHT_KEYS 확장 의무
  - 일봉 탭 영구 영속 명세

### 5.3 `src/db/CLAUDE.md`

- `stock_master_daily.py` 모듈 명세 영역에 UI 의무 1줄 명시:
  - "사이클 124 영속 — `get_recent_daily()` / `count_all()` / `max_bas_dd()` 영역 UI `/stock-master` detail 모달 일봉 탭 + stats 카드 영역 활용"

## 6. 영속 의무 매트릭스

- 사이클 38 명문화 / 49 VCP / 65 H3 retry:1 / 75 G-AST5 api-mocks / 80 hotfix #3 LIFO / 81 G-AST1 raw JSONB 덮어쓰기 금지 / 84 stock_master 라우트 / 85 UI 페이지 / 88 G-REJECT / 89 한글 친숙 용어 / 90 POST 화이트리스트 / 98 G-DOC1 KIS 정본 인용 / 106 lifecycle / 108 list_by_filter / 122 stock_master_daily / CLAUDE.md "절대 깨지 말 것" 8 영역

## 7. 매매 안전성 무영향 확정

- order_engine / risk / realtime / auth / scheduler 변경 0
- UI 노출 영역 + READ-ONLY GET endpoint 신규 한정 (5 → 6 GET 추가)
- 사이클 90 POST 화이트리스트 영속 (refresh-universe 단독 영구 영속)
- 매수/매도/익일청산/15:20 강제청산 hot path 무관
- 사이클 38 명문화 영속 (tradable_boards 매수 진입 전용)

## 8. 운영 효과 예상 (push 후 EC2 자동 배포 이후)

- 운영자 UI 종목마스터 메뉴 → 8 카드 가시화 (시총 데이터 / 거래대금 데이터 / 일봉 적재 행 수 / 일봉 마지막 적재 영업일)
- detail 모달 클릭 → 6 매핑 키 한글 라벨 highlight (사이클 116/118/119 신규 매핑 가시화)
- detail 모달 일봉 탭 클릭 → 마지막 30 영업일 OHLCV 테이블 (사이클 122 적재 검증 영구 영속)
- 사용자 보고 "너무 제한적" 영역 영구 시정

## 9. 사이클 125+ 후속 카드 인계 (영속 의무)

- D+1 운영 측정 의무 (2026-06-15 월 09:00~10:00) — UI 8 카드 정상 표시 + 일봉 탭 30 row 영역 표시 영구 영속
- 사이클 122 D+1 인계 영역 (T-1 영업일 추적 일봉 적재 정상화 영구 영속) 동행
- 카드 #21 (LOW 사이클 74 flaky stale_watcher logging caplog race)
- 카드 #16 (MEDIUM Q6-3 2026-06-13 이후 후보 풀 폭축 회고)
- auth 1.43x (LOW)
- 사이클 100 인계 영역 3+4 (Plan Phase B)

## 10. team-leader 메모 (영구 영속 의무)

- memory `feedback_no_redundant_phrases` 영속 = "영구 영속이" 등 무의미 반복 어휘 금지 (응답/문서/커밋 모두 단문 + 사실 중심)
- memory `feedback_commit_policy` 영속 = 사용자 명시 commit 지시 전엔 git commit/push 금지
- memory `feedback_ci_verification_required` 영속 = push 후 CI 확인 의무 (해당 사이클은 push 영역 별개)
- memory `feedback_korean_commit_messages` 영속 = 한글 커밋 메시지 (해당 사이클 push 시점 영속)
