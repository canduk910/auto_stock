# 사이클 95 (2026-06-10) — chicken-and-egg 결함 시정 + UI 전일종가/시장 한글 변환

> Red 단계 — tdd-engineer 작성. team-leader Phase 1 진단 (`_workspace/cycle95_phase1_diagnosis.md` 영속)
> 후 사용자 결정 채택:
>
> | 의제 | 채택 |
> |------|------|
> | Q43 영역 3 시정 | 1 unknown 합집합 (KIS 호출 0 증가) |
> | Q44 분할 | A 3 영역 통합 단일 사이클 95 |
> | Q45 push 시점 | A 진단 완료 직후 |

## 1. 근본 결함 (사이클 94 영역 3 chicken-and-egg)

사이클 94 시정 영역 3 (`fetch_top_500_universe()` post-split + `stock_master` 캐시 join) 적용 후에도
**universe 78 ticker 영속 lock-in** (사용자 보고). 결정적 발견:

- `_classify_market(sm_data)` (`src/engine/scanner.py:1413~1437`) = `sm_data` None / `excg_dvsn_cd` 없음 시
  `None` 반환 (graceful)
- `fetch_top_500_universe()` (L1602~L1614) = `market_class == "KOSPI" | "KOSDAQ"` 두 분기만 합집합 진입,
  `None` 분기는 **자연 skip**
- stock_master 부재 종목 = 영구 skip → 첫 사이클 stock_master 거의 비어있음 → 78 ticker 만 통과 →
  stock_master upsert chain `_universe_eager_refresh_loop(candidates)` 입력이 78 ticker → 영구 잔존

**chicken-and-egg lock-in 인과**:

```
첫 호출: stock_master 빈 상태
  → fetch_top_500_universe() → KIS volume_rank 500 raw
  → 78 종목만 stock_master.get() 성공 (이미 적재된 영역만)
  → _classify_market() = KOSPI/KOSDAQ 분류 = 78 통과
  → 422 ticker = None (graceful skip)
  → universe = 78
  → _universe_eager_refresh_loop(78) → 78 stock_master upsert
  → 다음 호출 동일 lock-in (78 → 80 → 82 ... 매우 느린 회복)
```

**시정 의도** (사용자 결정 Q43=1): `None` 분기 = `unknown` 합집합 진입 → 첫 호출에서 ~500 ticker
upsert chain trigger → 다음 사이클부터 KOSPI/KOSDAQ 정확 분류 자연 회복.

## 2. 사이클 95 시정 영역 (Green 단계 인계)

### 영역 3 (백엔드, HIGH 긴급) — `src/engine/scanner.py::fetch_top_500_universe()`

```python
async def fetch_top_500_universe() -> list[str]:
    """KIS volume_rank 단일 호출 + post-split + unknown 합집합 (사이클 95)."""
    all_raw = await _fetch_volume_rank(market="all", top_n=500)
    all_filtered = _universe_filter_securities_only(all_raw)
    all_sorted = sorted(all_filtered, key=_trade_amount_key, reverse=True)
    etf_excluded_total = len(all_raw) - len(all_filtered)

    kospi: list[dict] = []
    kosdaq: list[dict] = []
    unknown: list[dict] = []  # 사이클 95 신규 — chicken-and-egg lock-in 차단
    for row in all_sorted:
        ticker = row.get("mksc_shrn_iscd", "")
        if not ticker:
            continue
        sm_data = await _sm_mod.get(ticker)
        market_class = _classify_market(sm_data)
        if market_class == "KOSPI":
            kospi.append(row)
        elif market_class == "KOSDAQ":
            kosdaq.append(row)
        else:
            unknown.append(row)  # 사이클 95 — graceful None 영역 합집합

    # KOSPI 250 + KOSDAQ 250 = 500 ticker (사이클 89 영속)
    # 사이클 95 신규: unknown 영역 합산 (lock-in 차단)
    kospi_sorted = kospi[:250]
    kosdaq_sorted = kosdaq[:250]
    remaining = max(0, 500 - len(kospi_sorted) - len(kosdaq_sorted))
    unknown_sorted = unknown[:remaining]
    universe_rows = kospi_sorted + kosdaq_sorted + unknown_sorted

    tickers = [row["mksc_shrn_iscd"] for row in universe_rows if row.get("mksc_shrn_iscd")]
    tickers = tickers[:500]
    # ... (이하 emit/collector 영속, M-1 가시화 영역에 unknown 카운트 추가)
```

**핵심 시정 사양**:

1. `unknown: list[dict]` 신규 변수
2. `_classify_market(sm_data)` 반환 `None` 분기 → `unknown.append(row)` (continue 금지)
3. `kospi_sorted + kosdaq_sorted + unknown_sorted[:remaining]` 합집합 (500 cap 영속)
4. `[stock_master_bulk_refresh]` emit 에 `unknown=U` 카운트 추가 (M-1 운영 가시화)
5. KIS 호출 0건 증가 (사이클 94 영역 3 패턴 답습)

### 영역 1 (UI 전일종가 컬럼) — `frontend/src/pages/StockMaster.tsx`

list 테이블 (L608~L668 영역) 변경:

- `<thead>` 영역에 `<th>전일종가</th>` 컬럼 추가 (시장 컬럼 다음 / NXT 컬럼 *전*)
- `<tbody>` 영역에 `<td className="py-2 pr-3 font-mono text-right">{formatPrice(item.raw?.bfdy_clpr)}</td>` 추가
- `formatPrice` 헬퍼 (L113~L117) 영속 활용 — 변경 0

### 영역 2 (시장 코드 한글 변환) — `frontend/src/pages/StockMaster.tsx`

list 테이블 시장 컬럼 (L637~L639):

**Before** (사이클 85 영속):
```tsx
<td className="py-2 pr-3 text-gray-500">
  {item.excg_dvsn_cd ?? '—'}
</td>
```

**After** (사이클 95):
```tsx
<td className="py-2 pr-3 text-gray-500">
  {formatExchange(item.excg_dvsn_cd)}
</td>
```

`formatExchange` 헬퍼 (L101~L108) 영속 활용 — 변경 0 (사이클 89 hotfix 답습).

## 3. 회귀 가드 매트릭스 (10 케이스: HIGH 5 + MEDIUM 3 + LOW 2)

### HIGH 5 — silent 결함 영구 차단 + 핵심 행위

| 가드 | 파일 | 검증 영역 |
|------|------|----------|
| **H-1** | `tests/unit/engine/scanner/test_cycle95_unknown_split.py` | stock_master 부재 종목 = unknown 영역 합집합 진입 (mock) |
| **H-2** | `tests/unit/engine/scanner/test_cycle95_universe_500_lock_in_break.py` | 500 ticker 누적 영속 확정 (stock_master 부재 78건 + 422건 unknown 합집합 = 500) |
| **H-3** | `tests/unit/engine/scanner/test_cycle95_classify_market_graceful.py` | `_classify_market` graceful None 영속 + unknown 영역 분리 (행위 정합) |
| **H-4** | `frontend/src/pages/__tests__/StockMaster.test.tsx` (확장) | list 테이블 전일종가 컬럼 + `formatPrice` 영역 정합 |
| **H-5** | `frontend/src/pages/__tests__/StockMaster.test.tsx` (확장) | list 테이블 시장 한글 변환 (`"02"` → KOSPI 등) |

### MEDIUM 3 — 운영 가시화 + 영속 영역

| 가드 | 파일 | 검증 영역 |
|------|------|----------|
| **M-1** | `tests/unit/engine/scanner/test_cycle95_emit_visibility_unknown.py` | `[stock_master_bulk_refresh] universe=N kospi=K kosdaq=L unknown=U` 영역 emit (운영 가시화) |
| **M-2** | `tests/unit/engine/scanner/test_cycle95_chain_with_unknown.py` | `_scanner_upsert_loop` chain 영속 (unknown 영역 ticker 도 upsert 영역 진입) |
| **M-3** | `frontend/src/pages/__tests__/StockMaster.test.tsx` (확장) | `formatExchange` 헬퍼 5+ 코드 분류 영속 (KOSPI/KOSDAQ/ETF/ELW/ETN) |

### LOW 2 — 영속 의무 답습 검증

| 가드 | 파일 | 검증 영역 |
|------|------|----------|
| **L-1** | `tests/unit/engine/scanner/test_cycle95_g_reject_persistence.py` | 사이클 88 G-REJECT-1/2/3 영속 (외부 LLM 영구 차단 AST 가드 영역 0) |
| **L-2** | `tests/unit/engine/scanner/test_cycle95_kst_persistence.py` | KST 영속 (사이클 68 답습, `_kst` 헬퍼 영역 변경 0) |

## 4. 영속 의무 매트릭스 (사이클 95)

| 영속 의무 | 본 시정 영향 |
|----------|------------|
| 사이클 32 R4 universe guard (보유/익일청산 절대 보호) | 영향 0 (영역 분리) |
| 사이클 38 명문화 (매수 진입 전용) | 영향 0 |
| 사이클 64/65/81 graceful 설계 (price/trade_amount filter) | 영향 0 |
| 사이클 68 KST 일관성 | 영향 0 (`_kst` 헬퍼 변경 0) |
| 사이클 88 G-REJECT (외부 LLM 영구 차단 AST 가드 3) | 영향 0 + 답습 (L-1) |
| 사이클 89 KOSPI/KOSDAQ 분리 + ETF 제외 | **영속 + unknown 합집합 추가** |
| 사이클 91 페이징 (tr_cont + AST 가드 5) | 영향 0 |
| 사이클 92 자동 재기동 | 영향 0 |
| 사이클 93 호출 chain | 영향 0 (M-2 가드) |
| 사이클 94 영역 1/2/3 (`"0000"` 단일화 + post-split + UI 안내 배너) | **영속 + 영역 3 사이클 95 변경** |
| **CLAUDE.md "절대 깨지 말 것" 8 영역** | **영향 0 전수** (scanner 영역 = 매수 진입 *전* WS 구독 후보 영역) |

## 5. Red 단계 산출물 (10 신규 케이스 + 본 명세)

```
_workspace/red/cycle95_chicken_and_egg_fix_ui.md      (본 명세)

tests/unit/engine/scanner/
  test_cycle95_unknown_split.py                       (H-1)
  test_cycle95_universe_500_lock_in_break.py          (H-2)
  test_cycle95_classify_market_graceful.py            (H-3)
  test_cycle95_emit_visibility_unknown.py             (M-1)
  test_cycle95_chain_with_unknown.py                  (M-2)
  test_cycle95_g_reject_persistence.py                (L-1)
  test_cycle95_kst_persistence.py                     (L-2)

frontend/src/pages/__tests__/
  StockMaster.test.tsx                                (H-4 + H-5 + M-3, 확장)
```

## 6. Green 단계 (backend-dev + frontend-dev 인계)

### backend-dev

`src/engine/scanner.py::fetch_top_500_universe()`:
- `unknown: list[dict]` 신규 변수
- `_classify_market` None 분기 = `unknown.append(row)` (continue 금지)
- `remaining = max(0, 500 - len(kospi_sorted) - len(kosdaq_sorted))`
- `unknown_sorted = unknown[:remaining]`
- `universe_rows = kospi_sorted + kosdaq_sorted + unknown_sorted`
- `[stock_master_bulk_refresh]` emit `unknown=%d` 카운트 추가
- `record_universe_refresh({"unknown": len(unknown_sorted), ...})` collector 키 추가

### frontend-dev

`frontend/src/pages/StockMaster.tsx`:
- `<thead>` 에 `<th>전일종가</th>` 추가 (시장 컬럼 다음, NXT 컬럼 전)
- `<tbody>` 에 `<td>{formatPrice(item.raw?.bfdy_clpr)}</td>` 추가
- 시장 컬럼 `{item.excg_dvsn_cd ?? '—'}` → `{formatExchange(item.excg_dvsn_cd)}` 1줄 교체

## 7. Red → Green 전환 기대

- Red 단계 (사이클 95): 백엔드 2276 → 신규 7 fail (H-1/H-2/H-3 + M-1/M-2 + L-1/L-2) + 프론트 신규 3 fail (H-4/H-5/M-3) = **+10 신규 fail**
- Green 단계: backend-dev + frontend-dev 시정 후 10 신규 PASS + 회귀 0 + flakiness 0

## 8. 영향 인덱스 갱신

`_workspace/test_index.yaml`:
- backend tests +7 (사이클 95 scanner 7 신규)
- frontend tests +3 (StockMaster.test.tsx 확장)

## 9. 후속 사이클 인계 (사이클 96+)

- 운영 측정 의무: push 후 다음 영업일 09:30 첫 `_scan_loop` 에서 `[stock_master_bulk_refresh] universe=N kospi=K kosdaq=L unknown=U` emit 모니터링
- 회복 곡선 측정: 첫 사이클 unknown >> kospi+kosdaq → 다음 사이클 KOSPI/KOSDAQ 비중 증가 → 안정화 후 unknown ~0
- 사이클 94 영역 4 (UI 안내 배너) 영속
