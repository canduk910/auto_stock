# 사이클 124 Red 명세 — 종목마스터 UI 확장 + 지침 영구 가드

날짜: 2026-06-13 (토)
team-leader 발주 (tdd-engineer → backend-dev / frontend-dev → tester verify)
위험 등급: LOW (UI 가시화 + READ-ONLY GET endpoint 한정)

## A. 백엔드 회귀 가드 (tdd-engineer Red 명세)

### A1. `tests/unit/routes/test_cycle124_daily_endpoint.py` 신규

#### G-DAILY1 — GET /{ticker}/daily?days=30 정상 응답

```python
async def test_g_daily1_recent_daily_returns_30_rows():
    """GET /api/stock-master/005930/daily?days=30 → 30 row 응답."""
    # mock stock_master_daily.get_recent_daily → 30 row 반환
    # 응답 ApiResponse<list[StockMasterDailyRow]> 정확 매칭
    # 사이클 122 컬럼 10종 + raw 포함
```

#### G-DAILY2 — days 인자 범위 422 (1 미만 / 100 초과)

```python
async def test_g_daily2_days_range_422_under_1():
    """days=0 → 422 (FastAPI Query ge=1)."""

async def test_g_daily2_days_range_422_over_100():
    """days=101 → 422 (FastAPI Query le=100, KIS 호출 한도 정합)."""
```

#### G-DAILY3 — ticker 미존재 시 빈 list 반환 (graceful)

```python
async def test_g_daily3_unknown_ticker_returns_empty_list():
    """GET /api/stock-master/999999/daily → ApiResponse(data=[]). graceful 영속."""
```

### A2. `tests/unit/routes/test_cycle124_stats_expansion.py` 신규

#### G-STATS1 — 4 신규 키 포함

```python
async def test_g_stats1_response_includes_4_new_keys():
    """GET /api/stock-master/stats → with_hts_avls / with_acml_tr_pbmn /
    total_daily_rows / last_daily_load_at 4 키 포함."""
```

#### G-STATS2 — 정확 카운트

```python
async def test_g_stats2_counts_accuracy():
    """mock 4 ticker (2 with_hts_avls + 3 with_acml_tr_pbmn) →
    응답 with_hts_avls=2 + with_acml_tr_pbmn=3 정확."""
```

### A3. `tests/unit/ast/test_cycle124_ast_endpoint_order.py` 신규

#### G-AST1 — 라우트 순서 정합 (`/{ticker}/daily` *전* + `/{ticker}` *후*)

```python
def test_g_ast1_daily_endpoint_registered_before_ticker_catchall():
    """src/routes/stock_master.py AST 정적 분석:
    - @router.get("/{ticker}/daily") 정의 위치 < @router.get("/{ticker}") 정의 위치
    - 사이클 84 라우트 순서 의무 영속 (정적 > 동적, /history > /daily > /{ticker})."""
```

### A4. `tests/unit/ast/test_cycle124_ast_stock_master_daily_dependency.py` 신규

#### G-AST2 — 사이클 122 의존성 영속

```python
def test_g_ast2_stock_master_daily_imports_in_routes():
    """src/routes/stock_master.py 또는 src/db/stock_master.py 영역:
    - from src.db import stock_master_daily 호출 영역 ≥1건
    - stock_master_daily.get_recent_daily 호출 사이트 ≥1건
    - stock_master_daily.count_all 호출 사이트 ≥1건
    - stock_master_daily.max_bas_dd 호출 사이트 ≥1건
    사이클 122 영역 영구 영속 의존성 정적 검증."""
```

### A5. `tests/integration/test_cycle124_ui_endpoints_integration.py` 신규

#### G-INT1 — 통합 시나리오

```python
async def test_g_int1_full_ui_scenario():
    """4 종목 fixture + 일봉 30 row + stats 확장 키 통합 영역:
    1. GET /api/stock-master/stats → 8 키 정확
    2. GET /api/stock-master/list → 4 종목
    3. GET /api/stock-master/005930/daily?days=30 → 30 row
    4. GET /api/stock-master/005930 → detail (사이클 84 영속)
    """
```

## B. 프론트엔드 회귀 가드 (tdd-engineer Red 명세)

### B1. `frontend/src/pages/__tests__/StockMaster.test.tsx` 확장

#### F-CARD8 — 8 카드 표시

```typescript
describe('사이클 124 - 8 카드 + 4 신규 카드', () => {
  it('F-CARD8: 8 카드 영역 표시 + 4 신규 카드 데이터 정확', async () => {
    // mock fetchStats → 8 키 반환
    // render StockMaster → 8 카드 testid 정확 표시
    // - stock-master-stats-with-hts-avls
    // - stock-master-stats-with-acml-tr-pbmn
    // - stock-master-stats-total-daily-rows
    // - stock-master-stats-last-daily-load-at (KST 포맷)
  });
});
```

#### F-LABEL6 — 신규 6 매핑 키 한글 라벨

```typescript
it('F-LABEL6: detail 모달 신규 6 매핑 키 한글 라벨 표시', async () => {
  // mock fetchDetail → raw 에 6 키 포함 (hts_avls + acml_tr_pbmn + bfdy_clpr + lstn_stcn + acml_vol + prdy_vrss)
  // detail 모달 열고 → 6 라벨 정확 표시
  // - "시가총액 (백만원)" + "누적거래대금" + "전일종가" + "상장주식수" + "누적거래량" + "전일대비"
});
```

#### F-DAILY1 — 일봉 탭 정상 표시

```typescript
it('F-DAILY1: 일봉 탭 정상 표시 + 30 row', async () => {
  // mock fetchDaily → 30 row 반환
  // detail 모달 열고 → 일봉 탭 클릭
  // - 30 row 테이블 표시 (bas_dd DESC)
  // - 컬럼 8종 (영업일 / 시가 / 고가 / 저가 / 종가 / 거래량 / 거래대금 / 등락률)
});
```

#### F-DAILY2 — useQuery retry:1 + enabled

```typescript
it('F-DAILY2: useQuery retry:1 영속 + enabled !!ticker', async () => {
  // useQuery 옵션 정적 검증
  // - retry: 1
  // - refetchInterval: 60_000
  // - enabled: !!selectedTicker
});
```

#### F-DAILY3 — ticker 변경 시 자동 호출

```typescript
it('F-DAILY3: ticker 변경 시 enabled true → useQuery 자동 호출', async () => {
  // ticker A → B 변경
  // - fetchDaily 호출 2회 (각 ticker 별)
});
```

#### F-HIGHLIGHT — 6 키 highlight

```typescript
it('F-HIGHLIGHT: 6 키 highlight 영역 (amber 배경)', async () => {
  // HIGHLIGHT_KEYS = ['bfdy_clpr', 'hts_avls', 'acml_tr_pbmn', 'lstn_stcn', 'acml_vol', 'prdy_vrss']
  // 각 키 testid `stock-master-detail-highlight-${key}` 표시 + amber-50 배경
});
```

#### F-CATEGORY — 6 카테고리 영역

```typescript
it('F-CATEGORY: 6 카테고리 영역 (신규 "시총/주식수" 추가)', async () => {
  // CATEGORY_KEYS 6 카테고리 = 기본 / 가격 / 거래 / 시총/주식수 / 플래그 / 메타
  // 각 카테고리 헤더 표시 + 정확 키 매칭
});
```

### B2. `frontend/src/api/__tests__/stock-master.test.ts` 확장

#### F-API-DAILY — fetchDaily 정확 호출

```typescript
describe('사이클 124 - fetchDaily', () => {
  it('fetchDaily 호출 → /stock-master/${ticker}/daily?days=${days} 정확 URL', async () => {
    // mock axios → fetchDaily('005930', 30) 호출
    // - URL 정확 매칭
    // - 응답 data.data 추출 (사이클 85 답습)
  });
});
```

### B3. `frontend/src/test/handlers.ts` MSW 확장

#### F-MSW — MSW handler 8 키 응답

- `GET /api/stock-master/${ticker}/daily` MSW handler 신규
- `GET /api/stock-master/stats` 응답 확장 (4 → 8 키)

### B4. `frontend/src/components/__tests__/_ast_api_mocks_coverage.test.ts` 확장

#### F-AST-MOCK — api-mocks 영역 등록

- `REQUIRED_STOCK_MASTER_ENDPOINTS` literal 에 `/api/stock-master/{ticker}/daily` 추가
- AST 정적 검증 (사이클 75 G-AST5 영속)

### B5. `tests/unit/e2e_mocks/test_cycle124_api_mocks_stock_master_daily_lifo.py` 신규

#### F-AST-LIFO — Playwright LIFO 정합

```python
def test_f_ast_lifo_stock_master_daily_route_after_wildcard():
    """e2e/fixtures/api-mocks.ts AST 정적 분석:
    - wildcard `**/api/stock-master/**` 등록 위치 < 구체 `**/api/stock-master/**/daily*` 등록 위치
    - 사이클 80 hotfix #3/#4 Playwright LIFO 정합 영속."""
```

## C. 백엔드 시정 영역 명세 (backend-dev 발주)

### C1. `src/routes/stock_master.py`

```python
@router.get("/{ticker}/daily")
async def get_stock_master_daily(
    ticker: str,
    days: int = Query(30, ge=1, le=100),
):
    """사이클 124 — 일봉 N영업일 조회 (T-100일 한도 정합).

    사이클 122 stock_master_daily 영역 영구 영속 활용.
    Q1=A detail 모달 일봉 탭 영구 영속.
    """
    from src.db import stock_master_daily

    rows = await stock_master_daily.get_recent_daily(ticker, days)
    return ApiResponse(success=True, data=rows, message="")
```

### C2. `src/db/stock_master.py::get_stats()`

```python
async def get_stats() -> dict:
    """사이클 84 + 사이클 124 — 4 → 8 카운트 확장.

    사이클 124 신규 4 키:
    - with_hts_avls: 시총 데이터 보유 종목 수 (사이클 116/118 매핑 가시화)
    - with_acml_tr_pbmn: 거래대금 데이터 보유 종목 수 (사이클 107 매핑 영구 영속)
    - total_daily_rows: 일봉 적재 총 행 수 (사이클 122 영구 영속)
    - last_daily_load_at: 일봉 마지막 적재 영업일 (ISO +09:00)
    """
    from src.db import stock_master_daily

    # ... 기존 4 카운트 영속 ...

    with_hts_avls = sum(
        1 for r in rows
        if r.get("raw") and r["raw"].get("hts_avls") not in (None, "", "0", 0)
    )
    with_acml_tr_pbmn = sum(
        1 for r in rows
        if r.get("raw") and r["raw"].get("acml_tr_pbmn") not in (None, "", "0", 0)
    )

    total_daily_rows = await stock_master_daily.count_all()
    last_daily_load_at = None
    # max_bas_dd 영역은 사이클 122 함수 — 전체 ticker 가 아닌 적재 영역 일반 max
    # graceful (테이블 미존재 / 빈 영역 시 None)
    try:
        # 일봉 적재 전체 영역 max bas_dd — 비교적 가벼운 쿼리 활용
        from src.db.supabase import supabase
        import asyncio
        result = await asyncio.to_thread(
            lambda: supabase.table("stock_master_daily")
            .select("bas_dd")
            .order("bas_dd", desc=True)
            .limit(1)
            .execute()
        )
        if result.data:
            last_daily_load_at = result.data[0].get("bas_dd")
    except Exception:
        logger.exception("[stock_master.get_stats] last_daily_load_at 조회 실패 graceful")

    return {
        "count_all": count_all,
        "bfdy_clpr_present": bfdy_clpr_present,
        "nxt_tradable_count": nxt_tradable_count,
        "top_10_recent": top_10_recent,
        "with_hts_avls": with_hts_avls,         # 사이클 124 신규
        "with_acml_tr_pbmn": with_acml_tr_pbmn, # 사이클 124 신규
        "total_daily_rows": total_daily_rows,   # 사이클 124 신규
        "last_daily_load_at": last_daily_load_at, # 사이클 124 신규
    }
```

## D. 프론트엔드 시정 영역 명세 (frontend-dev 발주)

### D1. `frontend/src/types/stock-master.ts`

```typescript
export interface StockMasterStats {
  count_all: number;
  bfdy_clpr_present: number;
  nxt_tradable_count: number;
  top_10_recent: Array<{ ticker: string; name: string; refreshed_at: string }>;
  // 사이클 124 신규 4 키
  with_hts_avls: number;
  with_acml_tr_pbmn: number;
  total_daily_rows: number;
  last_daily_load_at: string | null; // ISO +09:00 또는 null
}

// 사이클 124 신규 (사이클 122 stock_master_daily 컬럼 10종 + raw)
export interface StockMasterDailyRow {
  ticker: string;
  bas_dd: string; // YYYY-MM-DD
  open_price: number;
  high_price: number;
  low_price: number;
  close_price: number;
  volume: number;
  trade_value: number;
  change_rate: number;
  flng_cls_code: string;
  prtt_rate: number;
  raw: Record<string, unknown>;
  updated_at: string; // KST +09:00 ISO
}
```

### D2. `frontend/src/api/stock-master.ts`

```typescript
import type { StockMasterDailyRow } from '../types/stock-master';

export async function fetchDaily(
  ticker: string,
  days = 30,
): Promise<StockMasterDailyRow[]> {
  const { data } = await apiClient.get<ApiResponse<StockMasterDailyRow[]>>(
    `/stock-master/${ticker}/daily`,
    { params: { days } },
  );
  return data.data;
}
```

### D3. `frontend/src/pages/StockMaster.tsx`

**FIELD_LABELS 확장 (6 신규 키)**:

```typescript
const FIELD_LABELS: Record<string, string> = {
  // 기존
  ticker: '종목코드',
  name: '종목명',
  excg_dvsn_cd: '거래소',
  bfdy_clpr: '전일종가',
  stck_prpr: '현재가',
  stck_hgpr: '고가',
  stck_lwpr: '저가',
  acml_vol: '누적거래량',
  acml_tr_pbmn: '누적거래대금',
  nxt_tradable: 'NXT 거래가능',
  krx_halted: 'KRX 거래정지',
  admin_item: '관리종목',
  refreshed_at: '갱신시각',
  // 사이클 124 신규
  hts_avls: '시가총액 (백만원)',
  lstn_stcn: '상장주식수',
  prdy_vrss: '전일대비',
};
```

**CATEGORY_KEYS 확장 (6 카테고리, 신규 "시총/주식수" 추가)**:

```typescript
const CATEGORY_KEYS: Record<string, string[]> = {
  '기본': ['ticker', 'name', 'excg_dvsn_cd'],
  '가격': ['bfdy_clpr', 'prdy_vrss', 'stck_prpr', 'stck_hgpr', 'stck_lwpr'],
  '거래': ['acml_vol', 'acml_tr_pbmn'],
  '시총/주식수': ['hts_avls', 'lstn_stcn'],
  '플래그': ['nxt_tradable', 'krx_halted', 'admin_item'],
  '메타': ['refreshed_at'],
};
```

**HIGHLIGHT_KEYS Q2=A 6 키**:

```typescript
const HIGHLIGHT_KEYS = [
  'bfdy_clpr',   // 전일종가
  'hts_avls',    // 시가총액
  'acml_tr_pbmn', // 누적거래대금
  'lstn_stcn',   // 상장주식수
  'acml_vol',    // 누적거래량
  'prdy_vrss',   // 전일대비
];
```

**CATEGORY_ICONS 추가**:

```typescript
const CATEGORY_ICONS: Record<string, string> = {
  '기본': '📋',
  '가격': '💰',
  '거래': '📊',
  '시총/주식수': '🏢',  // 사이클 124 신규
  '플래그': '🚩',
  '메타': '⏱️',
};
```

**8 카드 영역** (기존 4 + 신규 4):

```typescript
// 사이클 124 신규 카드 4 영역
<div className="bg-cyan-50 rounded p-3">
  <p className="text-xs text-gray-500">시가총액 데이터 보유</p>
  <p className="text-2xl font-bold text-cyan-700"
     data-testid="stock-master-stats-with-hts-avls">
    {statsQuery.data?.with_hts_avls ?? '—'}
  </p>
</div>
<div className="bg-indigo-50 rounded p-3">
  <p className="text-xs text-gray-500">거래대금 데이터 보유</p>
  <p className="text-2xl font-bold text-indigo-700"
     data-testid="stock-master-stats-with-acml-tr-pbmn">
    {statsQuery.data?.with_acml_tr_pbmn ?? '—'}
  </p>
</div>
<div className="bg-purple-50 rounded p-3">
  <p className="text-xs text-gray-500">일봉 적재 총 행</p>
  <p className="text-2xl font-bold text-purple-700"
     data-testid="stock-master-stats-total-daily-rows">
    {statsQuery.data?.total_daily_rows ?? '—'}
  </p>
</div>
<div className="bg-pink-50 rounded p-3">
  <p className="text-xs text-gray-500">일봉 마지막 적재</p>
  <p className="text-lg font-bold text-pink-700"
     data-testid="stock-master-stats-last-daily-load-at">
    {statsQuery.data?.last_daily_load_at
      ? formatKstDate(statsQuery.data.last_daily_load_at)
      : '—'}
  </p>
</div>
```

**detail 모달 일봉 탭** (Q1=A):

```typescript
// DetailModal 컴포넌트 내부 영역
const [activeTab, setActiveTab] = useState<'detail' | 'daily'>('detail');

const dailyQuery = useQuery({
  queryKey: ['stock-master-daily', ticker],
  queryFn: () => fetchDaily(ticker, 30),
  enabled: !!ticker && activeTab === 'daily',
  retry: 1,
  staleTime: 30_000,
  refetchInterval: 60_000,
});

// 탭 영역
<div className="flex border-b border-gray-200 mb-4">
  <button
    data-testid="stock-master-detail-tab-detail"
    onClick={() => setActiveTab('detail')}
    className={activeTab === 'detail' ? '...active' : '...inactive'}
  >
    상세 정보
  </button>
  <button
    data-testid="stock-master-detail-tab-daily"
    onClick={() => setActiveTab('daily')}
    className={activeTab === 'daily' ? '...active' : '...inactive'}
  >
    일봉 (30영업일)
  </button>
</div>

// 일봉 테이블 (activeTab === 'daily' 영역)
{activeTab === 'daily' && (
  <div className="overflow-x-auto" data-testid="stock-master-detail-daily-table">
    {dailyQuery.isLoading ? (
      <p>로딩 중...</p>
    ) : !dailyQuery.data || dailyQuery.data.length === 0 ? (
      <p>일봉 데이터가 없습니다.</p>
    ) : (
      <table className="min-w-full text-sm">
        <thead>
          <tr>
            <th>영업일</th><th>시가</th><th>고가</th><th>저가</th>
            <th>종가</th><th>거래량</th><th>거래대금</th><th>등락률</th>
          </tr>
        </thead>
        <tbody>
          {dailyQuery.data.map((row) => (
            <tr key={row.bas_dd}>
              <td>{row.bas_dd}</td>
              <td>{formatPrice(row.open_price)}</td>
              <td>{formatPrice(row.high_price)}</td>
              <td>{formatPrice(row.low_price)}</td>
              <td>{formatPrice(row.close_price)}</td>
              <td>{formatVolume(row.volume)}</td>
              <td>{formatAmount(row.trade_value)}</td>
              <td>{row.change_rate.toFixed(2)}%</td>
            </tr>
          ))}
        </tbody>
      </table>
    )}
  </div>
)}
```

### D4. `frontend/src/test/handlers.ts` MSW

```typescript
// 사이클 124 신규
http.get('/api/stock-master/:ticker/daily', ({ params, request }) => {
  const url = new URL(request.url);
  const days = parseInt(url.searchParams.get('days') ?? '30', 10);
  return HttpResponse.json({
    success: true,
    data: generateMockDailyRows(params.ticker as string, days),
    message: '',
  });
}),

// 기존 stats 응답 확장 (4 → 8 키)
http.get('/api/stock-master/stats', () => {
  return HttpResponse.json({
    success: true,
    data: {
      count_all: 2800,
      bfdy_clpr_present: 2750,
      nxt_tradable_count: 1200,
      top_10_recent: [...],
      // 신규 4 키
      with_hts_avls: 2700,
      with_acml_tr_pbmn: 2780,
      total_daily_rows: 280000,
      last_daily_load_at: '2026-06-12',
    },
    message: '',
  });
}),
```

### D5. `e2e/fixtures/api-mocks.ts` Playwright LIFO 정합

```typescript
// 사이클 80 hotfix #3/#4 영속 — wildcard *전* 등록 + 구체 *후* 등록 (LIFO 우선)

// 1. wildcard fallback (구체 라우트보다 *전* 등록)
await page.route("**/api/stock-master/**", (route) => {
  return route.fulfill({ json: envelope({}) });
});

// 2. 구체 라우트 (LIFO 우선)
await page.route("**/api/stock-master/stats", (route) => {
  return route.fulfill({ json: envelope({
    count_all: 100,
    bfdy_clpr_present: 95,
    nxt_tradable_count: 50,
    top_10_recent: [],
    with_hts_avls: 90,        // 사이클 124 신규
    with_acml_tr_pbmn: 95,    // 사이클 124 신규
    total_daily_rows: 10000,  // 사이클 124 신규
    last_daily_load_at: '2026-06-12', // 사이클 124 신규
  }) });
});

await page.route("**/api/stock-master/*/daily*", (route) => {
  return route.fulfill({ json: envelope([
    {
      ticker: "005930",
      bas_dd: "2026-06-12",
      open_price: 70000,
      high_price: 71000,
      low_price: 69500,
      close_price: 70500,
      volume: 12000000,
      trade_value: 840000000000,
      change_rate: 0.71,
      flng_cls_code: "00",
      prtt_rate: 0.0,
      raw: {},
      updated_at: "2026-06-12T16:00:00+09:00",
    },
    // ... 30 row
  ]) });
});
```

## E. 지침 영구 가드 명세 (team-leader 직접 시정)

### E1. 루트 `CLAUDE.md` DB 스키마 표

`stock_master` 행 뒤 영구 가드 영역 추가:

```markdown
> **stock_master 컬럼/raw 키 추가 시 UI 동기화 의무 영속 (사이클 124)**:
> stock_master 또는 stock_master_daily 컬럼/raw 키 추가 시
> `frontend/src/pages/StockMaster.tsx` 의 FIELD_LABELS + CATEGORY_KEYS + HIGHLIGHT_KEYS 확장 +
> stats 카드 영역 확장 + `frontend/CLAUDE.md` 본문 동기화 의무 영속.
> 미동기화 시 운영자 가시화 부족 → 사용자 보고 재발 위험 (사이클 124 원인).
```

### E2. `frontend/CLAUDE.md` 본문 사이클 124 추가

```markdown
## 사이클 124 (2026-06-13) — 종목마스터 UI 확장 + UI 노출 의무 영구 가드

사용자 보고 ("UI 너무 제한적") 영속 시정 4 영역 통합.

### 사용자 결정

- Q1=A 일봉 detail 모달 확장
- Q2=A 신규 6 키 highlight (hts_avls / acml_tr_pbmn / bfdy_clpr / lstn_stcn / acml_vol / prdy_vrss)
- Q3=A 진단 카드 4 → 8 카드
- Q4=A 지침 3 영역 동기화

### StockMaster.tsx 영역 영구 영속

- **8 카드 영역**: 기존 4 + 신규 4 (with_hts_avls / with_acml_tr_pbmn / total_daily_rows / last_daily_load_at)
- **FIELD_LABELS 6 신규 키 한글 라벨**:
  - hts_avls: "시가총액 (백만원)" (사이클 116/118 매핑)
  - lstn_stcn: "상장주식수" (사이클 119 매핑)
  - prdy_vrss: "전일대비" (사이클 107 매핑)
  - 기존 acml_vol / acml_tr_pbmn / bfdy_clpr 영속
- **CATEGORY_KEYS 6 카테고리** (신규 "시총/주식수" 추가)
- **HIGHLIGHT_KEYS Q2=A 6 키 영구 영속**
- **detail 모달 일봉 탭 (Q1=A)**: 상세 정보 / 일봉 (30영업일) 2 탭 영역
  - useQuery retry:1 영속 (사이클 65 H3) + refetchInterval 60_000 + enabled !!ticker
  - 30 row 테이블 (bas_dd DESC) 8 컬럼 (영업일 / OHLCV / 거래량 / 거래대금 / 등락률)

### UI 노출 의무 영구 가드 (영구 영속)

stock_master / stock_master_daily 컬럼/raw 키 추가 시:
1. `FIELD_LABELS` 한글 라벨 추가 의무
2. `CATEGORY_KEYS` 적절 카테고리 배치 의무
3. 핵심 키 (작전주 차단 / 시총 필터 / 거래대금 필터 등) `HIGHLIGHT_KEYS` 추가 검토
4. 진단 카드 영역 (with_${key} 카운트) 추가 검토
5. `frontend/CLAUDE.md` 본문 갱신 의무
6. 미동기화 시 운영자 가시화 부족 → 사용자 보고 재발 위험 (사이클 124 원인)

### 영속 의무 매트릭스

- 사이클 65 H3 useQuery retry:1 영속 (G-AST-RT TARGET_PAGES `StockMaster.tsx` 확장)
- 사이클 68 KST 영속 (formatKst / formatKstDate)
- 사이클 75 G-AST5 api-mocks 영속 (MSW + Playwright 핸들러 확장)
- 사이클 80 hotfix #3/#4 Playwright LIFO 영속 (wildcard *전* + 구체 *후*)
- 사이클 81 G-AST1 raw JSONB 덮어쓰기 금지 영속 (UI 표시 영역만 확장)
- 사이클 85 G-MOBILE-9 영속 (네비 9개 영역 유지 — 종목마스터 메뉴 영속)
- 사이클 89 한글 친숙 용어 영속 (영문 prefix 인접 한글 라벨 영속)
- 사이클 122 stock_master_daily 영구 영속 (UI 활용)
```

### E3. `src/db/CLAUDE.md` 본문 사이클 124 영역 추가

`stock_master_daily.py` 명세 영역에 1줄 추가:

```markdown
- **사이클 124 영속** (2026-06-13) — `get_recent_daily()` / `count_all()` / `max_bas_dd()` 영역 UI `/stock-master` detail 모달 일봉 탭 (Q1=A) + stats 카드 영역 (with_hts_avls / with_acml_tr_pbmn / total_daily_rows / last_daily_load_at) 활용. 사용자 보고 ("UI 너무 제한적") 영속 시정. 매매 안전성 무영향 (READ-ONLY GET endpoint + UI 가시화 영역 한정). 컬럼/raw 키 추가 시 `frontend/src/pages/StockMaster.tsx` 의 FIELD_LABELS + CATEGORY_KEYS + HIGHLIGHT_KEYS 동기화 의무 영구 영속.
```

## F. tester verify 영역 (영속 의무)

- 백엔드 풀 회귀 0 (사이클 110 2387 PASS 영속 기준 + 신규 8 케이스 = 2395 PASS 목표)
- 프론트엔드 풀 회귀 0 (사이클 104 268 PASS 영속 기준 + 신규 10 케이스 = 278 PASS 목표)
- flakiness 0 × 3회 반복 의무
- 영속 의무 매트릭스 7 영역 영구 영속 확인
- 매매 안전성 무영향 확정 (사이클 38 명문화 + 90 POST 화이트리스트 + 122 stock_master_daily 활용 영속)
