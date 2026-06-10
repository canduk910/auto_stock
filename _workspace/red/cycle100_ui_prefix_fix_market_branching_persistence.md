# 사이클 100 Red 명세 — UI prefix 정정 (영역 1) + 주문 발주 시장 분기 영속 확인 (영역 2)

**일자**: 2026-06-11
**위급도**: HIGH (영역 1: ~62% 결함 노출) + MEDIUM (영역 2: 영속 가드)
**Phase 1 진단 영속**: `_workspace/cycle100_phase1_diagnosis.md`
**사용자 결정 영속**: Q61=A (사이클 100 영역 1+2 + 사이클 101 영역 3+4) / Q65=C-1 (3 prefix OR)

---

## 결함 요약 (영역 1) + 영속 확인 요약 (영역 2)

### 영역 1 (HIGH) — `count_eager_refresh_today` 단일 grep 결함

- **위치**: `src/db/stock_master.py::count_eager_refresh_today` L169~194
- **결함**: 단일 `ilike("message", "%[scan_pool_eager_refresh]%")` (사이클 83 prefix) — UI `StockMaster.tsx::scanPoolQuery.data?.eager_refresh_today` (L548) "오늘 자동 갱신 횟수" 표시 영역
- **실측 (Supabase 7일)**: 사이클 89 `[universe_eager_refresh]` 244건 (최다) + 사이클 95 `[stock_master_bulk_refresh]` 140건 = **누락 384/614 = ~62% 노출**
- **사용자 결정 Q65=C-1**: 3 prefix `OR` 합산 (`universe_eager_refresh` + `scan_pool_eager_refresh` + `stock_master_bulk_refresh`)

### 영역 2 (MEDIUM) — 주문 발주 시장 분기 영속 확정 (변경 0)

- **`_strategy_exchange_async`** (`src/engine/order_engine.py:128~197`) = 사이클 13 (Phase G) 영속
  - 매수 진입 직전 호출 (`execute_buy` 영역)
  - 매도 진입 직전 호출 (`execute_sell:543` 시장가 경로 영속)
  - `stock_master.get(ticker).nxt_tradable=False` → NXT/SOR → KRX 강제 다운그레이드 + `[nxt_downgrade]` WARNING
- **사이클 55 R-1 `SellRejectionTracker` 영속**: 매도 진입 게이트 (NXT 시간대 매도 거부 영역 다음 KST 09:00 TTL + 익일 청산 자동 전환)
- **시정 의무 = 0** (변경 0, 영속 확인 가드만 — Q61=A 결정)

---

## 시정 영역 (Green 단계 backend-dev 인계)

### 영역 1: `src/db/stock_master.py::count_eager_refresh_today` 3 prefix OR 시정

**의도**:
- 사이클 89 `[universe_eager_refresh]` (244건 영속) 흡수
- 사이클 95 `[stock_master_bulk_refresh]` (140건 영속) 흡수
- 사이클 83 `[scan_pool_eager_refresh]` (230건 영속) 영속 유지
- 사이클 99 KIS 본질 한계 영구 영속 영역 호환

**Green 단계 후보 구현 (참고만, backend-dev 영역 정합 조정 가능)**:

```python
async def count_eager_refresh_today() -> int:
    """사이클 100 — 3 prefix OR 통합 카운트.

    사이클 89 [universe_eager_refresh] (244건 영속) + 사이클 83 [scan_pool_eager_refresh]
    (230건 영속) + 사이클 95 [stock_master_bulk_refresh] (140건 영속) 통합.

    사용자 결정 Q65=C-1.
    """
    from src.db._kst import today_kst

    today = today_kst()
    start = f"{today}T00:00:00+09:00"
    end = f"{today}T23:59:59.999999+09:00"

    PREFIXES = (
        "%[universe_eager_refresh]%",     # 사이클 89, 244건 영속
        "%[scan_pool_eager_refresh]%",    # 사이클 83, 230건 영속 (기존 유지)
        "%[stock_master_bulk_refresh]%",  # 사이클 95, 140건 영속
    )

    total = 0
    for pattern in PREFIXES:
        result = await asyncio.to_thread(
            lambda p=pattern: (
                supabase.table("system_logs")
                .select("id", count="exact")
                .ilike("message", p)
                .gte("timestamp", start)
                .lte("timestamp", end)
                .execute()
            )
        )
        if hasattr(result, "count") and result.count is not None:
            total += int(result.count)
        else:
            total += len(result.data or [])
    return total
```

**대안**: supabase `or_("message.ilike.%X%,message.ilike.%Y%,message.ilike.%Z%")` 단일 쿼리 (3 round-trip → 1) — backend-dev 채택 영역.

### 영역 2: 영속 확인만 (변경 0)

- `_strategy_exchange_async` 호출 사이트 영속 (사이클 13)
- 매도 `execute_sell:543` `target_exchange = await self._strategy_exchange_async(...)` 영속
- `SellRejectionTracker.is_blocked()` 진입 게이트 영속

---

## 회귀 가드 8 케이스 (HIGH 4 + MEDIUM 2 + LOW 2)

### HIGH 4 — 결함 영역 직접 시정 + 영속 확정 (매매 안전성 영역)

#### G-UI1: `count_eager_refresh_today` 3 prefix OR 영역 정합 (HIGH)

**파일**: `tests/unit/db/test_cycle100_count_eager_refresh_three_prefix.py`

**Red 의도**:
- mock `supabase.table().select().ilike().gte().lte().execute()` 호출 시 3 prefix 각각 다른 카운트 반환
- `count_eager_refresh_today()` 결과 = 3 prefix OR 합산 확정
- 사이클 84 H-4 영속 유지 (`scan_pool_eager_refresh` 단독 분기 호환)

**Red 검증**:
- mock 호출 횟수 = 3 (3 prefix 각각 분리 쿼리)
- 호출 패턴 인수 영역 = `%[universe_eager_refresh]%` + `%[scan_pool_eager_refresh]%` + `%[stock_master_bulk_refresh]%` 3 영역 매칭
- 결과 = 3 prefix 카운트 합산 (사용자 결정 Q65=C-1)

**Red 상태**: production 단일 grep (`[scan_pool_eager_refresh]` 1회) → 3 prefix 검증 mock 호출 = 1 ≠ 3 → FAIL.

**Green (backend-dev)**: 3 prefix OR 영역 시정 → 3 호출 + 합산 → PASS.

#### G-UI2: AST 영구 가드 — `count_eager_refresh_today` 본체 3 prefix 영역 grep (HIGH)

**파일**: `tests/unit/ast/test_cycle100_ast_count_eager_refresh_three_prefix.py`

**Red 의도**:
- AST 정적 검증 — `count_eager_refresh_today` 함수 본체 source text 영역에 3 prefix 영역 grep ≥1건 영속
  - `universe_eager_refresh` 영속 (사이클 89, 244건)
  - `scan_pool_eager_refresh` 영속 (사이클 83, 기존 유지)
  - `stock_master_bulk_refresh` 영속 (사이클 95, 140건)
- 미래 backend-dev 가 prefix 1개 silent 누락 영역 영구 차단 (사이클 81 silent 결함 영구 차단 패턴 답습)

**Red 상태**: production 본체 = `scan_pool_eager_refresh` 단독 → 3 prefix 검증 시 2 영역 부재 → FAIL.

**Green (backend-dev)**: 3 prefix 영역 source 영역 등장 → PASS.

#### G-MKT1: `_strategy_exchange_async` 매수 영역 호출 영속 (HIGH, 사이클 13 영속)

**파일**: `tests/unit/engine/test_cycle100_strategy_exchange_persistence_buy.py`

**Red 의도**:
- mock `stock_master.get(ticker)` = `StockBasics(nxt_tradable=False)` 반환
- `_strategy_exchange_async(strategy_id, ticker="005930")` 호출
- 결과 = `"KRX"` (NXT/SOR → KRX 강제 다운그레이드 영속)
- `[nxt_downgrade]` 영역 영속 (1회/일 cap 영역)
- AST 정적 검증 — `execute_buy` 본체에 `_strategy_exchange_async` 호출 ≥1건 영속

**Red 상태**: 영역 영속 확인 가드 — 호출 사이트 부재 시 FAIL (사이클 13 silent 결함 가설 영구 차단).

**Green**: 사이클 13 영속 = production 변경 0 → 영속 가드 PASS.

#### G-MKT2: `_strategy_exchange_async` 매도 영역 호출 영속 (HIGH, 사이클 13 영속)

**파일**: `tests/unit/engine/test_cycle100_strategy_exchange_persistence_sell.py`

**Red 의도**:
- AST 정적 검증 — `execute_sell` 본체에 `_strategy_exchange_async` 호출 ≥1건 영속 (사이클 13 영속)
- `target_exchange = await self._strategy_exchange_async(strategy_id, ticker=ticker)` (L543) 영역 정합
- `limit_price > 0` 분기 (NXT 익일청산 지정가) = `target_exchange = "NXT"` 우회 영역 영속
- 적시 청산 영역 영속 (시장가 매도 = NXT 사전 차단 영속)

**Red 상태**: 영역 영속 확인 가드 — 호출 사이트 부재 시 FAIL (사이클 13 매도 영역 누락 가설 영구 차단).

**Green**: 사이클 13 영속 = production 변경 0 → 영속 가드 PASS.

### MEDIUM 2

#### G-INT1: `GET /api/stock-master/scan-pool/summary` 통합 카운트 영속 (MEDIUM)

**파일**: `tests/integration/test_cycle100_count_eager_refresh_integration.py`

**Red 의도**:
- FastAPI TestClient + mock `count_eager_refresh_today` = 384 (예: 244+140 영역 통합)
- `GET /api/stock-master/scan-pool/summary` 응답 `data.eager_refresh_today == 384`
- ApiResponse 래퍼 영속 (`{success, data, message}`)
- 라우트 영역 변경 0 (영역 1 = db 영역만 시정)

**Red 상태**: production 단일 grep → 통합 카운트 부재 영역 → 응답 영역 검증 mock 결과 ≠ 통합 → FAIL.

**Green**: 영역 1 시정 자동 흡수 → PASS.

#### G-REG1: 사이클 55 R-1 `SellRejectionTracker` 영속 (MEDIUM, NXT 시간대 적시 청산 영역)

**파일**: `tests/unit/engine/test_cycle100_sell_rejection_persistence.py`

**Red 의도**:
- AST 정적 검증 — `execute_sell` 본체에 `self._sell_rejection.is_blocked(ticker, now_kst)` 진입 게이트 호출 영속
- AST 정적 검증 — `register_market_closed(ticker, _now_kst, in_krx_main_hours=...)` 호출 영속
- `_sell_rejection.reset_daily()` 위임 영속 (`OrderEngine.reset_daily_state` 영역)
- NXT 시간대 매도 거부 → 다음 KST 09:00 TTL → 익일 청산 자동 전환 영역 영속

**Red 상태**: 영역 영속 확인 가드 — 호출 사이트 부재 시 FAIL (사이클 55 R-1 silent 결함 가설 영구 차단).

**Green**: 사이클 55 R-1 영속 = production 변경 0 → 영속 가드 PASS.

### LOW 2

#### G-DOC1: 사이클 98 G-DOC1 영구 가드 영속 (LOW, 변경 0)

**파일**: `tests/unit/ast/test_cycle100_docstring_kis_chk_citation.py`

**Red 의도**:
- `src/engine/scanner.py::_fetch_fluctuation` docstring 영역에 `chk_fluctuation.py` 또는 `chk_*` 또는 `chk_` 인용 ≥1건 영속 (사이클 98 G-DOC1 영속)
- 사이클 100 = 영역 변경 0 → 사이클 98 G-DOC1 영속 가드 PASS 의무

**Red 상태**: 사이클 98 영속 = production 변경 0 → PASS (영속 확인 가드).

**Green**: 사이클 98 G-DOC1 영속 = PASS.

#### G-PERSIST1: 사이클 99 60 ticker 영구 영속 (LOW, 변경 0)

**파일**: `tests/unit/engine/scanner/test_cycle100_60_ticker_persistence.py`

**Red 의도**:
- mock `_fetch_fluctuation(market="kospi")` + `_fetch_fluctuation(market="kosdaq")` 각 30 ticker
- `fetch_top_500_universe()` 결과 = 60 ticker 영구 영속 (KIS API 본질 한계 영구 수용)
- 사이클 99 영속 = production 변경 0 → PASS

**Red 상태**: 사이클 99 영속 = production 변경 0 → PASS (영속 확인 가드).

**Green**: 사이클 99 영속 = PASS.

---

## 영향 인덱스 갱신

- `tools/test_impact/build_index.py` 재실행 (Green 단계 *후*)
- 신규 영향:
  - `src/db/stock_master.py` → `tests/unit/db/test_cycle100_count_eager_refresh_three_prefix.py` + `tests/unit/ast/test_cycle100_ast_count_eager_refresh_three_prefix.py` + `tests/integration/test_cycle100_count_eager_refresh_integration.py`
  - `src/engine/order_engine.py` → `tests/unit/engine/test_cycle100_strategy_exchange_persistence_buy.py` + `tests/unit/engine/test_cycle100_strategy_exchange_persistence_sell.py` + `tests/unit/engine/test_cycle100_sell_rejection_persistence.py`
  - `src/engine/scanner.py` → `tests/unit/ast/test_cycle100_docstring_kis_chk_citation.py` + `tests/unit/engine/scanner/test_cycle100_60_ticker_persistence.py`

## 백엔드 전체 카운트 (예상)

- 사이클 99 종료: 2302 PASS
- 사이클 100 Red 작성 후: 2302 → **2310** (+8 신규)
- Red 단계 = 결함 영역 가드 2 (G-UI1 + G-UI2 + G-INT1) FAIL / 영속 가드 5 (G-MKT1 + G-MKT2 + G-REG1 + G-DOC1 + G-PERSIST1) PASS
- Green 단계 (backend-dev) 후: 모두 PASS

---

## 매매 안전성 영역 영속 매트릭스

| 영역 | 사이클 영속 | 변경 |
|------|-----------|------|
| 체결통보 H0STCNI0/H0STCNI9 | 절대 | 0 |
| uvicorn 단일 워커 | 절대 | 0 |
| 주문번호 매핑 race 가드 | 절대 | 0 |
| `_reset_daily_state` | 절대 | 0 |
| NXT 매도 거부 좀비 차단 + SellRejectionTracker | 사이클 55 R-1 | 0 (영속 가드 추가) |
| WebSocket 4중 안전망 | 절대 | 0 |
| KIS 거부 응답 영구 저장 | 절대 | 0 |
| tradable_boards 매수 진입 전용 | 사이클 38 명문화 | 0 |
| `_strategy_exchange_async` NXT 사전 차단 | 사이클 13 Phase G | 0 (G-MKT1/MKT2 영속 가드) |

**결론**: 영역 1 (DB 영역 카운트 시정) + 영역 2 (영속 가드 추가) = 매매 hot path 영향 0.

---

## 산출물

- 본 Red 명세 (`_workspace/red/cycle100_ui_prefix_fix_market_branching_persistence.md`)
- 회귀 가드 8 케이스 (5 파일 + 3 AST 파일):
  - `tests/unit/db/test_cycle100_count_eager_refresh_three_prefix.py` (G-UI1)
  - `tests/unit/ast/test_cycle100_ast_count_eager_refresh_three_prefix.py` (G-UI2)
  - `tests/unit/engine/test_cycle100_strategy_exchange_persistence_buy.py` (G-MKT1)
  - `tests/unit/engine/test_cycle100_strategy_exchange_persistence_sell.py` (G-MKT2)
  - `tests/integration/test_cycle100_count_eager_refresh_integration.py` (G-INT1)
  - `tests/unit/engine/test_cycle100_sell_rejection_persistence.py` (G-REG1)
  - `tests/unit/ast/test_cycle100_docstring_kis_chk_citation.py` (G-DOC1)
  - `tests/unit/engine/scanner/test_cycle100_60_ticker_persistence.py` (G-PERSIST1)
- 영향 인덱스 갱신 (Green 단계 후)

## 다음 단계 (Green 단계 backend-dev 인계)

영역 1 시정:
1. `src/db/stock_master.py::count_eager_refresh_today` 3 prefix OR 영역 시정 (사용자 결정 Q65=C-1)
2. 회귀 가드 G-UI1 + G-UI2 + G-INT1 PASS 확인
3. 영역 2 영속 가드 G-MKT1 + G-MKT2 + G-REG1 PASS 영속 확인

영향 인덱스 갱신:
- `python tools/test_impact/build_index.py` 재실행
- `_workspace/test_index.yaml` 갱신
