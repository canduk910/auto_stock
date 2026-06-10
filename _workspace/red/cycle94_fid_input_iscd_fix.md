# 사이클 94 (2026-06-10) — FID_INPUT_ISCD "0000" 단일화 + post-split + UI 안내 가이드

> Red 단계 — tdd-engineer 작성. team-leader Phase 1 진단 (KIS MCP 재검증 → KIS 정본
> `FID_INPUT_ISCD = "0000"` 영속 확정) 후 사용자 결정 채택:
>
> | 의제 | 채택 |
> |------|------|
> | Q37 시정 | C `_MARKET_INPUT_ISCD = "0000"` 단일화 + post-split |
> | Q38 UI 안내 | A 추가 |
> | Q39 분할 | C 단순 시정 (94) + 아키텍처 재정의 (95+) 분리 |
> | Q42 post-split 구현 | A `stock_master.market_id` 컬럼 join (캐시 활용 + 추가 KIS 호출 0) |
>
> Plan 영속: `/Users/koscom/.claude/plans/radiant-marinating-pumpkin.md`

## 1. 근본 결함 (사이클 91 페이징 영속 silent 결함)

사이클 91 (2026-06-09) 페이징 누적 시정 push 완료 후에도 UI "지금 새로고침" 토스트가
**universe 60 ticker 즉시 적재 완료** 영속 → `fetch_top_500_universe()` 자체가 60 반환.

team-leader Phase 1 진단 결과 **단일 근본 원인 = `FID_INPUT_ISCD` 영역 결함**:

- KIS 정본 (`open-trading-api/examples_llm/.../volume_rank.py`) = `"0000"` (전체)
- 우리 (사이클 89/91 영역) = `"0001"` (KOSPI **업종**) / `"0002"` (KOSDAQ **업종**)
- KIS docstring: `"0000": 전체, 기타: 업종코드`
- **업종코드 응답 = 단일 페이지 30건 한도** = KOSPI 30 + KOSDAQ 30 = 60 ticker 영속
- 사이클 91 페이징 누적 코드는 정상 → 17+ 페이지 요청 가능하나 KIS 가 업종코드 영역에서는
  첫 페이지만 응답 (tr_cont != "M") → 1 페이지만 누적

## 2. KIS MCP 정본 재인용 (READ-ONLY 영구 기록)

`mcp__kis-code-assistant__search_domestic_stock_api` (2026-06-10 재검증):

```
FID_INPUT_ISCD: 입력 종목코드
  - "0000": 전체 (페이징 영역 17+ 페이지 정상 작동)
  - 기타: 업종코드 ("0001" = KOSPI 업종 / "0002" = KOSDAQ 업종, 30건 한도)
```

운영 실측 (사용자 보고 + READ-ONLY 확정):

| 영역 | 기대 (KIS 정본) | 실측 (사이클 89/91 결함) | 결함 인과 |
|------|-----------------|------------------------|----------|
| `_fetch_volume_rank(market="1", top_n=250)` | 250 (페이징 누적) | **30** | "0001" 업종코드 = 30건 한도 |
| `_fetch_volume_rank(market="2", top_n=250)` | 250 (페이징 누적) | **30** | "0002" 업종코드 = 30건 한도 |
| `fetch_top_500_universe()` | 500 | **60** | KOSPI 30 + KOSDAQ 30 |

## 3. 시정 영역 (Green 단계 backend-dev 인계)

### 영역 1: `src/engine/scanner.py:1368~1371` `_MARKET_INPUT_ISCD` 단일화

**Before** (사이클 89/91 결함):
```python
_MARKET_INPUT_ISCD: dict[str, str] = {
    "1": "0001",  # KOSPI 업종 (30건 한도)
    "2": "0002",  # KOSDAQ 업종 (30건 한도)
}
```

**After** (사이클 94 KIS 정본 일치):
```python
# 사이클 94 — KIS 정본 일치 ("0000" 전체 영역 17+ 페이징 정상 작동)
_MARKET_INPUT_ISCD: dict[str, str] = {
    "all": "0000",  # KOSPI/KOSDAQ 통합 (전체) — 응답 post-split (Q42=A stock_master 캐시 join)
}
```

### 영역 2: `_fetch_volume_rank` 시그너처 단일 호출 영역

기존 `market` 인자 의미 폐기 (`"1"`/`"2"` → `"all"`). 호출자 1곳 (`fetch_top_500_universe`)
만 영향. 단일 호출 영역 = KIS API 호출 수 절반 감소 (2 → 1).

### 영역 3: `fetch_top_500_universe()` post-split (Q42=A `stock_master` 캐시 join)

**Before** (사이클 89/91 = 2회 호출):
```python
kospi_raw = await _fetch_volume_rank(market="1", top_n=250)
kosdaq_raw = await _fetch_volume_rank(market="2", top_n=250)
# ... ETF 제외 + 정렬 + 합집합
```

**After** (사이클 94 = 1회 호출 + post-split):
```python
# 사이클 94 — 단일 호출 영역 (KIS API 호출 수 절반 감소)
all_raw = await _fetch_volume_rank(market="all", top_n=500)

# ETF/리츠/SPAC 자동 제외 (사이클 89 영속)
all_filtered = _universe_filter_securities_only(all_raw)

# 거래대금 desc 재정렬 (사이클 48 BFB 패턴 답습)
all_sorted = sorted(all_filtered, key=_trade_amount_key, reverse=True)

# Q42=A post-split: stock_master 캐시 활용 (추가 KIS 호출 0)
from src.db import stock_master as _sm

kospi: list[dict] = []
kosdaq: list[dict] = []
for row in all_sorted:
    ticker = row.get("mksc_shrn_iscd", "")
    if not ticker:
        continue
    sm_data = await _sm.get(ticker)
    if sm_data is None:
        # graceful: stock_master 부재 = 분류 불가, 양쪽 모두 합집합 영속
        # (사이클 88 G-REJECT 영속 + 사이클 32 R4 universe guard 답습)
        continue
    market_code = _classify_market(sm_data)
    if market_code == "KOSPI":
        kospi.append(row)
    elif market_code == "KOSDAQ":
        kosdaq.append(row)

# KOSPI 250 + KOSDAQ 250 = 500 ticker 영속 (사이클 89 의도 답습)
universe_rows = kospi[:250] + kosdaq[:250]
tickers = [row["mksc_shrn_iscd"] for row in universe_rows if row.get("mksc_shrn_iscd")]
tickers = tickers[:500]
```

**`_classify_market(sm_data)` 헬퍼 (신규)**:

스펙 영역 불일치 발견 — 사용자 결정 문서는 `sm_data.market_id == "STK"` (KIS BlueAPI
nomenclature) 를 인용하나 **현재 스키마는 `excg_dvsn_cd` 컬럼만 존재** (KIS CTPF1002R
응답: `02` = KOSPI / `03` = KOSDAQ 등). backend-dev Green 단계에서 다음 두 옵션 중 선택
의무 — Red 가드는 **분류 함수 동작** 영역으로 작성 (컬럼 명 무관, 행위 영속).

**옵션 A** (스키마 변경 없음 - 권고): 기존 `excg_dvsn_cd` (`02`/`03`) 활용
```python
def _classify_market(sm_data: StockBasics) -> str | None:
    """KOSPI/KOSDAQ 분류 — stock_master 캐시 활용 (추가 KIS 호출 0)."""
    code = (sm_data.excg_dvsn_cd or "").strip()
    if code == "02":
        return "KOSPI"
    if code == "03":
        return "KOSDAQ"
    return None  # graceful — 분류 불가
```

**옵션 B** (`market_id` 컬럼 신규 추가 - migration 의무): 사용자 결정 문서 인용 영역
```python
# stock_master 테이블에 market_id 컬럼 신규 추가 (migration 032)
def _classify_market(sm_data: StockBasics) -> str | None:
    code = (getattr(sm_data, "market_id", "") or "").strip()
    if code == "STK":
        return "KOSPI"
    if code == "KSQ":
        return "KOSDAQ"
    return None
```

**Red 가드 영역**: 함수 호출 + 정합성 (KOSPI 250 + KOSDAQ 250) + graceful 영속만
검증 (옵션 A/B 무관).

### 영역 4: `frontend/src/pages/StockMaster.tsx` UI 안내 배너

사용자 혼동 영역 해소 — UI 종목마스터 (DB 직접 조회) vs 전략 후보 풀 (실시간 KIS API)
별개 영역 영구 명시.

```tsx
{/* 사이클 94 — 사용자 혼동 영역 해소 안내 (영역 영속 의무) */}
<div className="bg-blue-50 border border-blue-200 rounded p-3 text-sm text-blue-800"
     data-testid="stock-master-info-banner">
  <p className="font-medium mb-1">참고용 종목 마스터 데이터</p>
  <p className="text-xs text-blue-700">
    이 화면은 한국투자증권 종목 기본정보 (전일종가, NXT 거래가능 여부, 관리종목 등) 의
    적재 현황입니다. 실시간 매매 신호 (모멘텀, 변동성 돌파, 스윙 등) 와는 별개 영역이며,
    각 전략의 후보 종목은 매 사이클 한국투자증권 시세 API 직접 조회를 통해 별도 평가됩니다.
  </p>
</div>
```

**영속 의무**:
- 사이클 89 UI hotfix 답습 (한글 친숙 용어, 사이클 언급 0)
- 사이클 75 G-AST4 (useQuery retry:1) 영속 (변경 0)
- testid 신규 `stock-master-info-banner`

## 4. 회귀 가드 매트릭스 (12 케이스: HIGH 6 + MEDIUM 4 + LOW 2)

### HIGH 6 — silent 결함 영구 차단 + 핵심 행위

| 가드 | 파일 | 검증 영역 |
|------|------|----------|
| **H-1** | `tests/unit/engine/scanner/test_cycle94_fid_input_iscd_fix.py` | `_MARKET_INPUT_ISCD` value 가 `"0000"` 만 포함 (AST 정적) + `"0001"`/`"0002"` 영속 부재 |
| **H-2** | `tests/unit/engine/scanner/test_cycle94_volume_rank_pagination_500.py` | 페이징 mock 17+ 페이지 누적 → top_n=500 응답 ≥ 500 ticker (KIS 정본 영역 영속) |
| **H-3** | `tests/unit/engine/scanner/test_cycle94_post_split_market_id.py` | Q42=A `stock_master.get()` 호출 + KOSPI/KOSDAQ 분류 정합 (mock, 옵션 A/B 무관) |
| **H-4** | `tests/unit/engine/scanner/test_cycle94_kospi_kosdaq_split_500.py` | 단일 호출 (`_fetch_volume_rank` ≤ 1 회) + KOSPI 250 + KOSDAQ 250 = 500 ticker (mock) |
| **H-5** | `frontend/src/pages/__tests__/StockMaster.test.tsx` 확장 | `stock-master-info-banner` testid 존재 + 한글 텍스트 영속 + 사이클 언급 0 |
| **H-6** | `tests/unit/ast/test_cycle94_ast_no_industry_code.py` | AST 영구 가드 — `src/engine/scanner.py` 본문 `"0001"` / `"0002"` 업종코드 사이클 94 이후 영속 부재 |

### MEDIUM 4 — 운영 가시화 + 영속 영역

| 가드 | 파일 | 검증 영역 |
|------|------|----------|
| **M-1** | `tests/unit/engine/scanner/test_cycle94_emit_visibility.py` | `[fetch_volume_rank]` 페이지 카운트 영속 + `[stock_master_bulk_refresh] universe=500` 영속 (사이클 89 답습) |
| **M-2** | `tests/unit/engine/scanner/test_cycle94_etf_exclusion_500.py` | 사이클 89 ETF/리츠/SPAC 제외 영속 (500 ticker 영역 = `_universe_filter_securities_only` 호출 영속) |
| **M-3** | `tests/unit/engine/scanner/test_cycle94_graceful_market_id_missing.py` | stock_master 부재 종목 graceful 영속 (사이클 88 G-REJECT 답습, 분류 불가 = 자연 skip) |
| **M-4** | `tests/unit/engine/scanner/test_cycle94_scanner_upsert_chain.py` | 사이클 93 `_scanner_upsert_loop` chain 영속 (호출 chain 변경 0) |

### LOW 2 — 영속 의무 답습 검증

| 가드 | 파일 | 검증 영역 |
|------|------|----------|
| **L-1** | `tests/unit/engine/scanner/test_cycle94_kst_persistence.py` | KST 영속 (사이클 68 답습, `_kst` 헬퍼 영역 변경 0) |
| **L-2** | `tests/unit/engine/scanner/test_cycle94_g_reject_persistence.py` | 사이클 88 G-REJECT-1/2/3 영속 (외부 LLM 영구 차단 AST 가드 영역 0) |

## 5. 영속 의무 매트릭스 (사이클 94)

| 영속 의무 | 본 시정 영향 |
|----------|------------|
| 사이클 32 R4 universe guard (보유/익일청산 절대 보호) | 영향 0 (영역 분리) |
| 사이클 38 명문화 (매수 진입 전용) | 영향 0 |
| 사이클 64/65/81 graceful 설계 (price/trade_amount filter) | 영향 0 |
| 사이클 68 KST 일관성 | 영향 0 (`_kst` 헬퍼 변경 0) |
| 사이클 88 G-REJECT (외부 LLM 영구 차단 AST 가드 3) | 영향 0 + 답습 (L-2) |
| 사이클 89 KOSPI/KOSDAQ 분리 + ETF 제외 | **post-split 영역으로 영속** (의도 보존) |
| 사이클 91 페이징 (tr_cont + AST 가드 5) | 영속 + KIS 정본 영역 일치 |
| 사이클 92 자동 재기동 | 영향 0 |
| 사이클 93 호출 chain | 영향 0 (M-4 가드) |
| **CLAUDE.md "절대 깨지 말 것" 8 영역** | **영향 0 전수** (scanner 영역 = 매수 진입 *전* WS 구독 후보 영역) |

## 6. Red 단계 산출물 (12 신규 파일)

```
_workspace/red/cycle94_fid_input_iscd_fix.md      (본 명세)
tests/unit/engine/scanner/
  test_cycle94_fid_input_iscd_fix.py              (H-1)
  test_cycle94_volume_rank_pagination_500.py      (H-2)
  test_cycle94_post_split_market_id.py            (H-3)
  test_cycle94_kospi_kosdaq_split_500.py          (H-4)
  test_cycle94_emit_visibility.py                 (M-1)
  test_cycle94_etf_exclusion_500.py               (M-2)
  test_cycle94_graceful_market_id_missing.py      (M-3)
  test_cycle94_scanner_upsert_chain.py            (M-4)
  test_cycle94_kst_persistence.py                 (L-1)
  test_cycle94_g_reject_persistence.py            (L-2)
tests/unit/ast/
  test_cycle94_ast_no_industry_code.py            (H-6)
frontend/src/pages/__tests__/
  StockMaster.test.tsx                            (H-5, 확장)
```

## 7. Green 단계 (backend-dev 인계)

1. `src/engine/scanner.py`:
   - `_MARKET_INPUT_ISCD` 단일화 (`{"all": "0000"}`)
   - `_fetch_volume_rank(market="all", top_n=500, max_pages=17)` 시그너처 변경
   - `fetch_top_500_universe()` 단일 호출 + post-split + `_classify_market` 헬퍼 신규
2. `frontend/src/pages/StockMaster.tsx`:
   - `data-testid="stock-master-info-banner"` 안내 배너 추가
3. backend-dev 옵션 A/B 선택 (스키마 변경 vs `excg_dvsn_cd` 활용 — 본 Red 가드는 양쪽 모두 PASS)

## 8. Red → Green 전환 기대

- Red 단계: 백엔드 2261 → 사이클 94 신규 11 fail + 프론트 1 fail = **+12 신규 fail**
- Green 단계: backend-dev 시정 후 12 신규 PASS + 회귀 0 + flakiness 0

## 9. 영향 인덱스 갱신

`_workspace/test_index.yaml`:
- backend tests 421 → **432** (+11)
- frontend tests 신규 H-5 1 (StockMaster.test.tsx 확장)

## 10. 후속 사이클 인계 (사이클 95+)

사이클 95 Phase A (VB/LTV/BFB stock_master 베이스 전환) — Plan §사이클 95+ 영속.
domain-expert 자문 의무 (Q41 영속).
