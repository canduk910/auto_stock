# 사이클 90 Red 명세 — stock_master 500+ universe 수동 trigger API

**작성일**: 2026-06-09
**작성자**: tdd-engineer
**위급도**: MEDIUM (수동 trigger 영역 — 매매 hot path 무관 + 사이클 84 L-2 AST 영구 가드 갱신 영역)
**카드**: 사이클 89 후속 (개장 전 1회 자동 task → 수동 trigger 보완)

**선행**:
- Phase 1 진단: `_workspace/cycle90_phase1_diagnosis.md` 영속
- 사이클 89 `fetch_top_500_universe()` 신규 영속 (`src/engine/scanner.py`)
- 사이클 89 자동 task `_universe_eager_refresh_task` 영속
- 사이클 84 L-2 AST 영구 가드 `tests/unit/ast/test_cycle84_ast_no_update_route.py` 영속 (POST 0건)
- 사이클 80 hotfix #3 Playwright LIFO 정합 영속 (wildcard → 구체 라우트)
- 사이클 88 G-REJECT-1/2/3 영속 (WebSocket 4중 안전망 + ticker_last_tick + 4 dict 분리)

**domain-expert 자문 생략 근거**:
1. READ-ONLY POST (`fetch_top_500_universe()` 가 KIS 조회 + DB upsert 영역 — 주문/매도/손절 무관)
2. 사이클 89 영속 영역의 단순 진입점 추가 (행위 변경 0)
3. 사이클 38 명문화 영속 (`tradable_boards` 매수 진입 전용)

**사용자 결정 채택 (영속)**:

| 의제 | 채택 |
|------|------|
| Q24 처리 방향 | **B** 사이클 90 수동 trigger API |
| Q25 동시 호출 가드 | **A** 단일 in-flight 가드 (asyncio.Lock + 409 Conflict) |
| Q26 버튼 위치 | **A** stats 카드 상단 우측 |
| Q27 emit 영역 | **A** 사이클 89 `[stock_master_bulk_refresh]` 영속 활용 |

---

## 1. Green 시정 영역 (backend-dev + frontend-dev 사이클 90 인계)

### 1-1. 백엔드 `src/routes/stock_master.py` POST 라우트 추가 (~40L)

```python
import asyncio
import time

_refresh_universe_lock = asyncio.Lock()  # Q25=A in-flight 가드

@router.post("/refresh-universe", response_model=ApiResponse[dict])
async def refresh_universe_now():
    """사이클 90 — universe 500+ 즉시 trigger (수동 발화).

    장 종료 후 또는 scheduler idle 상태에서 사용자 즉시 실행.
    Q25=A 단일 in-flight 가드 = 동시 호출 시 두번째 호출 즉시 409 Conflict.
    Q27=A 사이클 89 [stock_master_bulk_refresh] 영속 활용 (자동/수동 구분 0).

    사이클 84 L-2 AST 영구 가드 영역 = POST 1개 예외 허용 (refresh-universe 단독).
    """
    if _refresh_universe_lock.locked():
        raise HTTPException(
            status_code=409,
            detail="universe refresh 진행 중 — 잠시 후 재시도",
        )

    async with _refresh_universe_lock:
        from src.engine.scanner import fetch_top_500_universe

        start_time = time.monotonic()
        tickers = await fetch_top_500_universe()
        elapsed_ms = int((time.monotonic() - start_time) * 1000)

        return ApiResponse(
            success=True,
            data={
                "universe": len(tickers),
                "elapsed_ms": elapsed_ms,
            },
            message=f"universe {len(tickers)} ticker 즉시 적재 완료",
        )
```

### 1-2. 사이클 84 L-2 AST 영구 가드 갱신

`tests/unit/ast/test_cycle84_ast_no_update_route.py`:
- `_ALLOWED_POST_ROUTES = {"refresh-universe"}` 화이트리스트 신설
- POST 1개 예외 허용 + 기타 POST/PUT/DELETE/PATCH 0건 영속
- 의미 영속 (사이클 84 Q9=B READ-ONLY 원칙 변경 0) — `_collect_route_paths_for_method("post")` 결과가 `refresh-universe` 단독일 때만 PASS

### 1-3. 프론트엔드 `frontend/src/types/stock-master.ts` 신규 타입

```typescript
export interface RefreshUniverseResult {
  universe: number;
  elapsed_ms: number;
}
```

### 1-4. 프론트엔드 `frontend/src/api/stock-master.ts` 신규 함수

```typescript
export async function refreshUniverseNow(): Promise<RefreshUniverseResult> {
  const { data } = await apiClient.post<ApiResponse<RefreshUniverseResult>>(
    "/stock-master/refresh-universe",
  );
  return data.data;
}
```

### 1-5. 프론트엔드 `frontend/src/pages/StockMaster.tsx` UI 갱신 (~40L)

- stats 카드 상단 우측 "지금 새로고침" 버튼 (Q26=A)
- `useMutation` 활용 + 로딩 인디케이터 + 결과 토스트 (성공/409/실패)
- 사이클 75 G-RT retry:1 영역 — useMutation 은 default no retry. 명시 의무 보존

### 1-6. e2e api-mocks + MSW 등록

- `frontend/src/test/handlers.ts` MSW `POST /api/stock-master/refresh-universe` mock
- `e2e/fixtures/api-mocks.ts` Playwright LIFO 정합 (wildcard *후* 등록)
- 사이클 80 hotfix #3 LIFO 정합 영속 (구체 라우트가 wildcard *후* 등록)

---

## 2. 회귀 가드 매트릭스 (15 케이스, HIGH 6 + MEDIUM 6 + LOW 3)

### HIGH 6 (40%)

| ID | 파일 | 의도 |
|----|------|------|
| **H-1** | `tests/unit/routes/test_cycle90_post_route_envelope.py` | POST `/refresh-universe` ApiResponse 정합 (success/data/message + universe/elapsed_ms 키) |
| **H-2** | `tests/unit/routes/test_cycle90_concurrent_lock.py` | Q25=A asyncio.Lock + 409 Conflict 동시 호출 가드 (2 호출 시 첫 번째 200 + 두 번째 409) |
| **H-3** | `tests/unit/ast/test_cycle84_ast_no_update_route.py` (갱신) | L-2 AST 갱신: POST 1개 예외 허용 (`refresh-universe`) + 기타 POST/PUT/DELETE/PATCH 0건 영속 |
| **H-4** | `tests/unit/routes/test_cycle90_fetch_top_500_call.py` | `fetch_top_500_universe()` 호출 정합 (mock 결과 `["005930", "402340", ...]` → universe=N 반영) |
| **H-5** | `frontend/src/api/__tests__/stock-master.test.ts` (갱신) | `refreshUniverseNow()` ApiResponse `data.data` 추출 정합 (universe / elapsed_ms 키) |
| **H-6** | `frontend/src/pages/__tests__/StockMaster.test.tsx` (갱신) | "지금 새로고침" 버튼 + useMutation 호출 + 로딩/성공/409/실패 토스트 |

### MEDIUM 6 (40%)

| ID | 파일 | 의도 |
|----|------|------|
| **M-1** | `tests/unit/routes/test_cycle90_route_405_other.py` | PUT/DELETE/PATCH `/refresh-universe` 405 영속 (L-2 영구 차단) |
| **M-2** | `tests/unit/routes/test_cycle90_response_timing.py` | elapsed_ms 응답 timing 검증 (mock graceful, 25초 작업 시뮬레이션) |
| **M-3** | `tests/unit/routes/test_cycle90_lock_release.py` | Lock release 정합 (예외 발생 시도 release — `async with` 컨텍스트 매니저 보장) |
| **M-4** | `frontend/src/pages/__tests__/StockMaster.test.tsx` (갱신) | 버튼 위치 (stats 카드 상단 우측) + disabled 상태 (로딩 중 isPending) |
| **M-5** | `frontend/src/components/__tests__/_ast_api_mocks_coverage.test.ts` (갱신) | api-mocks `refresh-universe` POST mock 등록 영구 가드 (사이클 75 G-AST5 답습) |
| **M-6** | `tests/unit/e2e_mocks/test_api_mocks_routes_registered.py` (갱신) | POST refresh-universe LIFO 정합 (사이클 80 hotfix #3 영속, wildcard *후* 등록) |

### LOW 3 (20%)

| ID | 파일 | 의도 |
|----|------|------|
| **L-1** | `tests/unit/routes/test_cycle90_kst_persistence.py` | KST 영속 (사이클 68 답습) — refresh 시점 timestamp 미생성, 응답 elapsed_ms 외 시각 0건 검증 |
| **L-2** | `tests/unit/ast/test_cycle90_g_reject_persistence.py` | 사이클 88 G-REJECT-1/2/3 영속 (사이클 90 영역 무영향 정적 검증) |
| **L-3** | `tests/unit/routes/test_cycle90_emit_persistence.py` | Q27=A `[stock_master_bulk_refresh]` 영속 활용 (사이클 89 prefix 영역 변경 0 + neue prefix 도입 0건) |

---

## 3. Red 실행 결과 (예상)

- 백엔드 현재 (사이클 89 직후): 2180 PASS + 2 XFAIL + 2 skip
- 사이클 90 Red 작성 시 신규 케이스:
  - **신규 FAIL 예상 9건**: H-1, H-2, H-4, M-1, M-2, M-3, L-1, L-3 (백 8건 = production code 0 → POST 라우트 없음) + H-3 갱신 영역 (POST 1 예외 허용 패턴 미적용)
  - **신규 PASS 예상 4건**: L-2 G-REJECT (영속 정합 정적 검증, 사이클 88 영역 변경 0) + M-5 갱신 (frontend) + M-6 갱신 (LIFO 영속 확인) + 갱신 영역
- 프론트 현재: 223 PASS
- 사이클 90 Red 작성 시 신규 프론트 케이스:
  - **신규 FAIL 예상 3건**: H-5, H-6, M-4 갱신 (refreshUniverseNow + 버튼 미존재)

**총 신규 FAIL 12건** (백 9 + 프 3) + **신규 PASS 3건** (사전 정합 + 영속 가드)

---

## 4. 영향 인덱스 갱신

`_workspace/test_index.yaml` 갱신:
- backend tests 385 → 393 (+8 신규 cycle90 + H-3 갱신은 기존 영역)
- frontend tests 41 → 43 (+2 신규 cycle90 vitest, H-5/H-6 갱신 + M-4 갱신은 기존 영역)

---

## 5. 매매 안전성 영향 평가

- **무영향**: POST 라우트 = READ-ONLY 영역 (KIS 조회 + DB upsert)
- 사이클 38 명문화 영속 (`tradable_boards` 매수 진입 전용)
- 사이클 64 protected_tickers 영속 (M-3 가드)
- 사이클 65 trade_amount_filter 영속
- 사이클 81 bfdy_clpr 영속
- 사이클 89 자동 task 영속 (수동 trigger 와 별개 영역)
- 사이클 88 G-REJECT-1/2/3 영속 (L-2 가드)
- 사이클 84 L-2 AST 의미 영속 (POST 1개 예외 허용 + 원칙 변경 0)
- 사이클 80 hotfix #3 LIFO 영속 (M-6 가드)
- 매도/익일청산/15:20 강제청산/손절/Trailing 영향 0

---

## 6. 영속 의무 (각 케이스 docstring 명시)

- **사이클 38 명문화 영속**: `tradable_boards` 매수 진입 전용 영역 한정
- **사이클 64 protected_tickers 영속**: 보유 ticker 가격필터 graceful 통과
- **사이클 65 trade_amount_filter 영속**: 거래대금 임계 정확 작동
- **사이클 68 KST 영속**: timestamp 영역 정합 (L-1 가드)
- **사이클 75 G-AST5/G-AST6 영속**: e2e api-mocks endpoint 등록 의무 (M-5 갱신)
- **사이클 80 hotfix #3 LIFO 영속**: 구체 라우트 wildcard *후* 등록 (M-6 갱신)
- **사이클 81 bfdy_clpr 영속**: `_apply_price_filter` 정상 발화
- **사이클 84 L-2 영속**: POST 1개 예외 허용 + 원칙 변경 0 (H-3 갱신)
- **사이클 88 G-REJECT-1/2/3 영속**: 영향 0 영구 확인 (L-2 가드)
- **사이클 89 [stock_master_bulk_refresh] 영속**: emit 영역 변경 0 (L-3 가드)
- **사이클 89 자동 task 영속**: `_universe_eager_refresh_task` 영역 분리

---

## 7. 후속 사이클 인계

- **사이클 91+** (운영 검증): 수동 trigger 발화 시 elapsed_ms 분포 측정 (25초 영역 검증) + 동시 호출 시나리오 (실 사용 시 9 Conflict 빈도)
- **사이클 92+** (Q24 후속): refresh-universe 외 다른 수동 trigger 필요 시 화이트리스트 확장 패턴 답습

기존 카드 영속 (이전 사이클 인계):
- C-2 (HIGH) `_scan_loop` 후보 풀 raw 보강 영역 확장 (사이클 82+)
- C-4 (LOW) `[risk_silent_skip]` DailyEmitCap 폭주 검증
- C-5 (LOW) `[price_filter_scanner_pass_no_data]` emit
- #16 (MEDIUM Q6-3 2026-06-13 이후 후보 풀 폭축 회고)
- #20 (LOW collector shared 헬퍼 추출 사이클 74+76+78 = 3회 답습 충족)

---

## 8. 운영 효과 예상 (사이클 90 Green push 후)

- 사용자가 stats 카드 새로고침 버튼 클릭 → 백엔드 POST `/refresh-universe` 발화 → KIS volume_rank 2회 호출 → `stock_master` upsert ~500건 + 25초 후 응답
- 동시 호출 시 두번째는 즉시 409 Conflict (KIS Rate Limit 폭주 차단)
- 자동 task (개장 전 1회 + 5분 주기) 와 별개로 사용자 즉시 실행 가능
- `[stock_master_bulk_refresh]` emit 영속 (자동/수동 구분 0, Q27=A 영속)
- 작전주/초고가 종목 즉시 차단 효과 회복 (사이클 81 bfdy_clpr 영속 + 사이클 89 universe 500 적재)
