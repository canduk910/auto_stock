# 사이클 90 Phase 1 진단 — stock_master 500+ 수동 trigger API

**발주 시점**: 2026-06-09 (장 종료 후 추정 / `Today's date is 2026-06-09`)
**사용자 결정**: B 옵션 (영구 영속 + 미래 영구 해소 + 백+프 통합 단일 사이클)
**진단 모드**: READ-ONLY (코드 변경 0)
**자문 필요성**: domain-expert 자문 **불요** (READ-ONLY POST + 매매 hot path 무영향 가설 확정 — 아래 §C-1 근거)

---

## A. 영역 분석 (READ-ONLY 확정)

### A-1. `src/routes/stock_master.py` 현 영역 (사이클 84 영속)

| 라우트 | Method | 영속 사이클 | 비고 |
|--------|--------|------------|------|
| `/stats` | GET | 84 | count_all / bfdy_clpr_present / nxt_tradable_count / top_10_recent |
| `/list` | GET | 84 | limit ∈ [1,1000], offset ≥ 0 |
| `/scan-pool/summary` | GET | 84 | 사이클 83 `[scan_pool_eager_refresh]` 카운트 |
| `/{ticker}/history` | GET | 84 | migration 032 `stock_master_history` |
| `/{ticker}` | GET | 84 | StockBasics dict, 미존재 404 |

**5 GET 모두 READ-ONLY** — 사이클 84 L-2 AST 영구 가드 = PUT/POST/DELETE/PATCH 0건 영속.

라우트 순서 의무 영속: 정적 (stats / list / scan-pool) → 동적 ({ticker}/history) → 동적 ({ticker}) (FastAPI LIFO 정합).

### A-2. `src/engine/scanner.py::fetch_top_500_universe()` 영역 (사이클 89 영속)

- 시그너처: `async def fetch_top_500_universe() -> list[str]`
- **scheduler 의존 0** — 직접 호출 가능
- KOSPI 250 + KOSDAQ 250 volume_rank API (FHPST01710000) 분리 호출
- ETF/리츠/SPAC 자동 제외 (`_universe_filter_securities_only`)
- 거래대금 desc 재정렬 (사이클 48 BFB 답습)
- 50ms sleep 종목 간 (Rate Limit 20/s 보호)
- 500 ticker × 50ms = **~25초 소요 추정**
- KIS 실패 graceful → `[]` 반환
- `[stock_master_bulk_refresh]` INFO emit + `record_universe_refresh` collector 적재 + `flush_universe_collector()` 즉시 1회 flush

### A-3. 사이클 89 자동 task 영역 (`src/engine/scheduler.py`)

```python
# L497~L503 (start() 영역)
self._universe_eager_refresh_task = asyncio.create_task(
    self._universe_eager_refresh_loop()
)
```

- `start()` 호출 안 되면 task 생성 안 됨 (사용자 보고 결함)
- `stop()` task_attrs L759/L879/L908 = 3 위치 cancel 보장 (사이클 79 영속)
- `_universe_eager_refresh_loop()` (L2580+) 본체:
  - 개장 전 1회 즉시 `fetch_top_500_universe()` 호출
  - 5분 주기 반복 (`while self._running`)
  - `flush_universe_collector()` 동행

### A-4. 사이클 84 L-2 AST 영구 가드 현황

**파일**: `tests/unit/ast/test_cycle84_ast_no_update_route.py` (L1~57, 1 테스트)

```python
FORBIDDEN_METHODS = {"put", "post", "delete", "patch"}

def test_L2_ast_no_write_decorators_in_stock_master_route():
    # 모든 함수 정의 데코레이터 순회
    # `@router.<method>(...)` 매칭 시 fail
```

**갱신 의무**: 사이클 90 신규 POST 1개 (`/refresh-universe`) 추가 시 fail → POST 1개 예외 허용 + 기타 POST/PUT/DELETE/PATCH 0건 영속 패턴 신설.

### A-5. e2e api-mocks LIFO 영역 (사이클 80 hotfix #3 + 사이클 85 답습)

**파일**: `e2e/fixtures/api-mocks.ts` L295~L335

현 패턴: wildcard `**/api/stock-master/**` 가 *먼저* 등록 + 5 구체 라우트 *후* 등록 (LIFO 우선 매칭).

사이클 90 추가 의무: `**/api/stock-master/refresh-universe` POST mock 등록 — wildcard *후* 등록 (LIFO 우선).

### A-6. 프론트엔드 영역 (사이클 84/85 영속)

- `frontend/src/pages/StockMaster.tsx` 페이지 존재
- `frontend/src/api/stock-master.ts` API 클라이언트 존재
- `frontend/src/types/stock-master.ts` 타입 정의 존재
- `frontend/src/pages/__tests__/StockMaster.test.tsx` 테스트 존재
- `frontend/src/api/__tests__/stock-master.test.ts` API 테스트 존재
- 사이클 75 G-RT (useQuery retry:1) — useMutation 영역 신규 검토 의무

---

## B. 시정 영역 설계 (예상 결과물 — 코드 변경 0)

### B-1. 백엔드 라우트 신규 (`src/routes/stock_master.py` +~30L 예상)

```python
@router.post("/refresh-universe", response_model=ApiResponse[dict])
async def refresh_universe_now():
    """사이클 90 — universe 500+ 즉시 trigger (수동 발화).

    장 종료 후 또는 scheduler idle 상태에서 사용자 즉시 실행 영역.
    사이클 84 L-2 AST 영구 가드 = POST 1개 예외 허용 (refresh-universe 단독).
    매매 hot path 무영향 (READ-ONLY POST — KIS volume_rank + stock_master upsert).
    """
    from src.engine.scanner import fetch_top_500_universe
    import time

    start = time.monotonic()
    tickers = await fetch_top_500_universe()
    elapsed_ms = int((time.monotonic() - start) * 1000)

    return ApiResponse(
        success=True,
        data={"universe": len(tickers), "elapsed_ms": elapsed_ms},
        message=f"universe {len(tickers)} ticker 즉시 적재 완료",
    )
```

### B-2. AST 가드 갱신 (`tests/unit/ast/test_cycle84_ast_no_update_route.py`)

POST 1개 예외 허용 패턴:

```python
ALLOWED_WRITE_DECORATORS = {
    ("post", "/refresh-universe"),  # 사이클 90 신규 예외
}

# 기존 검출 + ALLOWED 화이트리스트 차감
forbidden_hits = [...]
forbidden_hits = [h for h in forbidden_hits if not _is_allowed(h)]
```

기존 사이클 84 L-2 의미는 영속 (PUT/DELETE/PATCH 0건 + 기타 POST 0건).

### B-3. 프론트엔드 UI (`StockMaster.tsx` +~40L 예상)

- "지금 새로고침" 버튼 (stats 카드 상단)
- `useMutation` + 로딩 인디케이터 + 결과 토스트
- 사이클 75 G-RT retry:1 검토 (mutation 영역 — 일반 미적용 권장)

### B-4. e2e api-mocks (LIFO 영속, `api-mocks.ts` +~5L)

```typescript
// 사이클 90 — POST /refresh-universe
await page.route("**/api/stock-master/refresh-universe", (route) =>
  route.fulfill({
    json: envelope({ universe: 500, elapsed_ms: 25000 }),
  }),
);
```

wildcard *후* 등록 (LIFO 우선 매칭).

---

## C. 사용자 결정 의제 (Q25~Q27 권고안)

### C-1. domain-expert 자문 필요성 평가 → **불요** 확정

**근거 3중**:
1. **매매 hot path 무영향**: scanner 단계 = WebSocket 구독 *전* 영역 (사이클 38 명문화 영속 — 매수 진입 전용)
2. **사이클 64/65/89 영속**: scanner 영역 시정/추가 시 매매 안전성 영향 0 일관
3. **POST 의미가 READ-ONLY**: `fetch_top_500_universe()` 가 KIS API 조회 + `stock_master` upsert (조회·캐시 적재 영역 — 주문/매도/손절 무관)

### Q25 (HIGH) 동시 호출 가드

**권고**: **옵션 A — 단일 in-flight 가드** (asyncio.Lock + 409 Conflict)

- 옵션 A 권고 이유:
  - 25초 소요 작업 → 사용자 더블 클릭 / 다중 탭 시 KIS 호출 중복
  - 단순 + 명확 + 사용자에게 즉시 피드백
  - 패턴: `if _refresh_lock.locked(): raise HTTPException(409, "already in progress")`
- 옵션 B (큐잉) 비채택: 25초 × 2 = 50초 대기 = UX 악화
- 옵션 C (graceful) 비채택: KIS Rate Limit 폭주 위험

### Q26 (MEDIUM) 버튼 위치

**권고**: **옵션 A — stats 카드 상단 우측 (단일 버튼)**

- 옵션 A 이유: stats 카드가 universe 적재 결과 (count_all) 표시 영역 — 같은 카드 내 새로고침 자연
- 옵션 B 비채택: list 카드는 페이징 영역 (리프레시 의미 분산)
- 옵션 C 비채택: 별개 카드 = UI 복잡도 증가

### Q27 (LOW) emit 영역

**권고**: **옵션 A — 사이클 89 `[stock_master_bulk_refresh]` 영속 영역 활용**

- 옵션 A 이유: `fetch_top_500_universe()` 내부에서 이미 emit + collector 적재 = 자동/수동 구분 불필요 (운영 관점 동일)
- 옵션 B 비채택: 신규 prefix 도입 = 사이클 78 silent 결함 영역 추가 위험
- 옵션 C 비채택: 양쪽 = dup 위험 (사이클 72/73/74 답습)

---

## D. 회귀 가드 매트릭스 추정

| 위급도 | 카테고리 | 예상 케이스 수 |
|--------|----------|---------------|
| HIGH | 라우트 정합 (ApiResponse) | 1 |
| HIGH | 동시 호출 가드 (Q25=A 옵션) | 2 (lock + 409) |
| HIGH | L-2 AST 갱신 (POST 1개 예외 + 기타 0건) | 2 |
| HIGH | `fetch_top_500_universe` 호출 정합 (사이클 89 영속) | 1 |
| MEDIUM | UI 버튼 + useMutation + 로딩 + 토스트 | 4 |
| MEDIUM | e2e api-mocks LIFO 등록 검증 | 1 |
| MEDIUM | 사이클 86 e2e 호환 영속 | 1 |
| LOW | KST 영속 (사이클 68 영속) | 1 |
| LOW | AST 영구 가드 (G-AST 사이클 90 신설) | 1 |
| LOW | 사이클 88 G-REJECT 영속 | 1 |

**합계 예상**: HIGH 6 + MEDIUM 6 + LOW 3 = **15 케이스 (백 9 + 프 6 추정)**

---

## E. 영속 의무 (사이클 85 영역 패턴 답습)

| 영속 영역 | 영향 |
|-----------|------|
| 사이클 84 L-2 AST | **갱신** (POST 1개 예외 허용) |
| 사이클 85 e2e 5 라우트 | **추가** (POST refresh-universe 1) |
| 사이클 80 hotfix #3 LIFO 정합 | 영속 (wildcard 먼저 → 구체 후) |
| 사이클 89 자동 task | 영속 (수동 trigger 와 별개 영역) |
| 사이클 38 명문화 (tradable_boards 매수 진입 전용) | 영속 (scanner 영역 무영향) |
| 사이클 64/65 scanner 단계 | 영속 (매매 hot path 무관) |

---

## F. 사이클 91+ 후속 카드 인계 후보 (Phase 1 발의 0건)

본 사이클 단독 완결 영역 (백+프 통합) — 후속 카드 인계 0.

기존 카드 영속 (이전 사이클 인계):
- C-2 (HIGH) `_scan_loop` 후보 풀 raw 보강 영역 확장 (사이클 82+)
- C-4 (LOW) `[risk_silent_skip]` DailyEmitCap 폭주 검증
- C-5 (LOW) `[price_filter_scanner_pass_no_data]` emit
- #16 (MEDIUM Q6-3 2026-06-13 이후 후보 풀 폭축 회고)
- #20 (LOW collector shared 헬퍼 추출 사이클 74+76+78 = 3회 답습 충족)

---

**Phase 1 진단 완료. Phase 2 진행을 위해 사용자 결정 의제 Q25~Q27 확정 권고.**
