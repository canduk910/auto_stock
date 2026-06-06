# 사이클 64 Red 명세 — 가격 필터 위치 이전 (risk → scanner) + mode 단순화

> **작성**: tdd-engineer (2026-06-06 KST)
> **선행 설계 카드**: `_workspace/cycle64_price_filter_scanner_design_card.md` v1
> **자문 응답**: `_workspace/cycle64_price_filter_scanner_domain_response.md` (옵션 A 전부 채택)
> **위험 등급 종합**: MEDIUM (보유/익일청산 보호 영역 HIGH)
> **선례**: 사이클 60~63 분리 12 파일 답습 (logger 명시 binding + AsyncMock + freezegun + AST 가드)

---

## 0. 사이클 62 → 사이클 64 핵심 변화 요약

| 항목 | 사이클 62 (현 위치, 폐기) | 사이클 64 (신규) |
|---|---|---|
| 적용 위치 | `risk.on_tick` 매수 신호 평가 직전 | **scanner `subscribe_filtered_stocks` 직전 단일 hook** (Q4 옵션 A) |
| 모드 | 3 모드 (HARD/WARN/OFF) | **단순 필터링만** (모드 폐기) |
| 비교 가격 | `prev_close` 우선 + `current_price` fallback | **`stock_master.raw.prdy_clpr` 단독** (KIS pre-fetch 비채택) |
| 보호 헬퍼 | (없음 — 매수 진입만 영향) | **`_collect_protected_tickers_for_scanner`** 합집합 헬퍼 + early-return |
| invalidate 호출 | `risk_manager.invalidate_price_filter_cache` | **`scanner.invalidate_price_filter_cache_scanner`** |
| 로그 prefix | `[price_filter_skip]` / `[price_filter_warn]` | **`[price_filter_scanner_skip]`** 신규 단일 |
| 일일 집계 prefix | `[price_filter_daily_summary]` | **`[price_filter_scanner_daily_summary]`** 신규 |
| 자동 unsubscribe | (없음) | **AVOID** (invalidate 는 캐시만, 다음 `_scan_loop` 5분 자연 delta — Q7-1) |

---

## §1. grep 정독 결과 (소스 진실의 원천 검증)

### 1.1 `subscribe_filtered_stocks` 진입점 (Q4 옵션 A 진실)

```
src/engine/scanner.py:494 — async def subscribe_filtered_stocks(
    tickers, extra_tickers=None, source_counts=None, *, priority_groups=None
)
```

호출처 (scheduler.py grep):
- L481: `_collect_breakout_tickers` (BFB/VCP/donchian) 통합 구독
- L522: presubscribe (08:00) 보유+익일청산 사전 구독
- L542: presubscribe 보유+pending
- L1961: `_scan_loop` 5분 주기 재구독

→ **단일 진입점 `subscribe_filtered_stocks` 내부 첫 줄에 `_apply_price_filter` hook 채택 시 4 호출처 모두 자동 통과** (옵션 A 자문 §Q4)

### 1.2 사이클 62 `risk.py::on_tick` 가격 필터 분기 (전부 폐기 대상)

```
src/engine/risk.py:19  — from src.db.system_config import PriceFilter, get_price_filter
src/engine/risk.py:30  — PRICE_FILTER_CACHE_TTL: float = 60.0
src/engine/risk.py:54-62 — 7 필드 (cache + cap 2 + count 3)
src/engine/risk.py:71-78 — reset_daily_state 6 라인
src/engine/risk.py:213-246 — on_tick 본체 분기 (33 라인)
src/engine/risk.py:266-281 — _get_price_filter_cached / invalidate_price_filter_cache
src/engine/risk.py:284-321 — _emit_price_filter_skip
src/engine/risk.py:323-357 — _emit_price_filter_warn
src/engine/risk.py:359-381 — _emit_price_filter_daily_summary
```

→ **G-1 AST 가드 의무**: `src/engine/risk.py` 전체에서 `price_filter` 문자열 매칭 0건 검증 (Green 후 영구 차단)

### 1.3 사이클 62 `system_config.py::PriceFilter` mode 필드 (폐기 대상)

```
src/db/system_config.py:494-504 — _PRICE_FILTER_MIN/MAX/MODE_KEY + DEFAULT + VALID_MODES
src/db/system_config.py:511-526 — class PriceFilter(min_price, max_price, mode)
src/db/system_config.py:529-543 — get_price_filter() (3 키 조회)
src/db/system_config.py:546-600 — set_price_filter (mode sentinel + 검증)
```

→ **A 카테고리**: mode 필드/상수/유효값 모두 제거. `get_price_filter()` 는 2 키만 조회

### 1.4 `routes/system.py` mode 인자 (폐기 대상)

```
src/routes/system.py:114-118 — PriceFilterUpdateRequest.mode: Optional[str]
src/routes/system.py:148-149 — mode 처리 (kwargs)
src/routes/system.py:158 — trading_scheduler.risk_manager.invalidate_price_filter_cache()
```

→ **C-Route 카테고리**: mode 필드 제거 + invalidate 호출은 `scanner.invalidate_price_filter_cache_scanner()` 로 변경

### 1.5 `_pending_next_day_clear` 위치 (Q1 옵션 D 헬퍼 source)

```
src/engine/scheduler.py:200 — self._pending_next_day_clear: set[tuple[str, str]] = set()
src/engine/scheduler.py:2945 — _reset_daily_state 동행 clear
```

→ **C-4 헬퍼**: `_collect_protected_tickers_for_scanner` = `registry.all().positions` ∪ `_pending_next_day_clear` (lazy import 가드)

### 1.6 stock_master.get 시그니처 (Q2 단독 데이터 소스)

```
src/db/stock_master.py:81 — async def get(ticker: str) -> Optional[StockBasics]
src/models/stock.py — StockBasics.raw: dict — KIS CTPF1002R 원본 응답 (prdy_clpr 포함)
```

→ **B 카테고리**: `await stock_master.get(ticker)` → `basics.raw.get("prdy_clpr", 0)` 1순위 단독 (KIS pre-fetch 비채택)

### 1.7 사이클 60~63 패턴 (logger 명시 binding + AsyncMock)

```
src/engine/stale_manager.py:1 — logger = logging.getLogger("src.engine.scheduler")
src/engine/risk.py:27 — logger = logging.getLogger(__name__)  → "src.engine.risk"
src/engine/scanner.py:19 — logger = logging.getLogger(__name__)  → "src.engine.scanner"
```

→ **caplog 명시**: `caplog.set_level(logging.INFO, logger="src.engine.scanner")` 의무

---

## §2. 24 케이스 카테고리 분류 (12 파일 분리)

| # | 카테고리 | 파일 | 케이스 | 위험 | 의도 |
|---|---|---|---|---|---|
| 1 | A system_config 단순화 | `tests/unit/db/test_cycle64_price_filter_scanner_system_config.py` | 4 | LOW | mode 인자 폐기 + 2 키만 조회 |
| 2 | B scanner 필터 적용 | `tests/unit/engine/test_cycle64_price_filter_scanner_apply.py` | 5 | MEDIUM | 비활성/below/above/missing graceful/pass |
| 3 | **C 보유/익일청산 보호 (HIGH)** | `tests/unit/engine/test_cycle64_price_filter_scanner_protected.py` | **4** | **HIGH** | 보유/익일청산/합집합/헬퍼 단독 |
| 4 | D 60s TTL 캐시 + invalidate | `tests/unit/engine/test_cycle64_price_filter_scanner_cache.py` | 2 | MEDIUM | freezegun TTL + invalidate 즉시 + unsubscribe 0건 (Q7-1) |
| 5 | E DailyEmitCap + reset | `tests/unit/engine/test_cycle64_price_filter_scanner_emit_cap.py` | 2 | LOW | cap 1회/일 + reset 동행 |
| 6 | F E2E integration + funnel hook | `tests/integration/test_cycle64_price_filter_scanner_integration.py` | 4 | MEDIUM | scan → filter → subscribe + Settings PUT + protected 보존 + funnel step_no=98 |
| 7 | **G AST 가드 (HIGH)** | `tests/unit/engine/test_cycle64_price_filter_scanner_ast.py` | **2** | **HIGH** | risk.py 가격 필터 0건 + `_apply_price_filter` 호출 `protected_tickers=` keyword 의무 |
| 8 | H scanner daily_summary | `tests/unit/engine/test_cycle64_price_filter_scanner_daily_summary.py` | 1 | LOW | `[price_filter_scanner_daily_summary]` freezegun 20:10 |
| 9 | C-Route API | `tests/contract/test_cycle64_routes_price_filter.py` | 2 | LOW | mode 필드 폐기 + 422 (mode 명시 거부) |
| 10 | F-FE 프론트 | `frontend/src/components/__tests__/PriceFilterCard.test.tsx` (갱신) | 4 | LOW | mode select 폐기 (5→4 케이스, 사이클 62 F-5 폐기) |

**합계**: 24 케이스 / 11 신규 파일 + 1 갱신 (F-FE)

(F 카테고리 F-1/F-2/F-3/F-4 4 케이스 단일 파일로 통합 — F-4 funnel hook 별도 파일 분리 안 하고 같은 integration 파일 흡수)

**HIGH 6 = 25%** (C 4 + G 2)

---

## §3. mock 패턴 표 (사이클 60 hotfix 답습 의무)

| 영역 | mock 대상 | 이유 |
|---|---|---|
| scanner `_apply_price_filter` 본체 | `src.engine.scanner.get_price_filter` (AsyncMock) | DB 호출 격리 |
| scanner `_collect_protected_tickers_for_scanner` | `src.engine.scanner.registry` + `_sched.trading_scheduler` | scheduler / registry 미초기화 graceful |
| stock_master.raw.prdy_clpr | `src.db.stock_master.get` (AsyncMock → StockBasics(raw={"prdy_clpr": N})) | KIS API 호출 격리 |
| system_logs.write_log | `src.db.system_logs.write_log` (AsyncMock) | DB INSERT 격리 |
| funnel snapshot (F-4) | `src.db.strategy_funnel.insert_snapshot` (AsyncMock) | DB INSERT 격리 |
| `kis_ws_pool.unsubscribe` (D-2 Q7-1) | `src.engine.scanner.kis_ws_pool` (MagicMock) | unsubscribe 0건 검증 |

**사이클 60 hotfix 패턴**: KIS API 가능 영역은 모두 mock 우선. CI hang 차단 (실제 호출로 인한 timeout 결함 영구 차단).

---

## §4. freezegun 사용 위치

| 케이스 | 사용 이유 | 시각 |
|---|---|---|
| D-1 캐시 TTL 60s | `time.monotonic()` 진행 | base + 0 / +59.9 / +60.1 |
| D-2 invalidate 즉시 | invalidate 후 새 값 | base + 5.0 → invalidate → +5.1 |
| H-1 daily_summary | `_settle()` 직전 시각 | `freeze_time(datetime(2026,6,6,20,10,0,tzinfo=KST))` |

E 카테고리는 freezegun 불필요 (`DailyEmitCap` 내부 add/contains 만 검증).

---

## §5. 회귀 가드 매트릭스 (CLAUDE.md 절대 규칙 매핑)

| CLAUDE.md 절대 규칙 | 본 사이클 케이스 | 보호 메커니즘 |
|---|---|---|
| **`tradable_boards` 매수 진입 전용 (사이클 38)** | C-1/C-2/C-3/F-3 | scanner 차단 = 매수 후보만. 매도/익일청산/손절 영역 무관 |
| **WebSocket 시세 보유·익일청산 우선 보장 (MAX 41)** | **C-1/C-2/C-3/C-4 + G-2 (HIGH 5)** | `_apply_price_filter` 최상단 early-return + `protected_tickers` keyword 의무 |
| **WebSocket 4 중 안전망** | D-2 (Q7-1) | invalidate 시 unsubscribe 발화 0건 — 다음 `_scan_loop` 5분 자연 delta |
| **K stale watcher 우선순위 분리 (사이클 29-R3)** | (영향 0) | scanner 차단 종목 = 구독 안 됨 → stale 진입 안 함 |
| **사이클 32 R4 universe guard 답습** | C-4 헬퍼 + C-1/C-2/C-3 | `registry.all().positions` ∪ `_pending_next_day_clear` 합집합 — universe guard `_evaluate_universe_guard` 답습 패턴 |
| **`_reset_daily_state` 동행 reset** | E-2 + H-1 | emit cap clear + scheduler `_reset_daily_state` 호출 동행 |
| KST 강제 | H-1 | `freeze_time` + KST timezone 명시 |
| **사이클 62 코드 완전 제거 (잔존 위험)** | G-1 | AST 정적 검증 — risk.py 에 `price_filter` 매칭 0건 |
| **graceful 통과 영속 (Q2 자문)** | B-4 | `prdy_clpr=0` 미확보 종목 매수 허용 |

---

## §6. 사이클 62 폐기 18 케이스 정리 표기 (옵션 A 권고 — Green 단계 backend-dev 실제 삭제)

### 6.1 옵션 A (코드 cleanup — Green 단계 backend-dev 실제 삭제)

본 Red 단계에서는 *식별만* 진행. backend-dev Green 단계에서 실제 파일/케이스 삭제.

| 파일 | 폐기 케이스 | 사유 | 옵션 |
|---|---|---|---|
| `tests/unit/engine/test_cycle62_price_filter_risk_on_tick.py` | **전체 4 케이스 (B-1~B-4)** | risk.on_tick 영역 자체 제거 | C (파일 전체 삭제) |
| `tests/unit/engine/test_cycle62_price_filter_cache.py` | **전체 2 케이스 (D-1~D-2)** | risk 영역 60s 캐시 폐기, scanner 영역 D 2 신규 | C (파일 전체 삭제) |
| `tests/unit/engine/test_cycle62_price_filter_q2_fallback.py` | **전체 5 케이스 (F-1~F-5)** | current_price fallback 자체 폐기 (전일종가 단독, Q2 자문) | C (파일 전체 삭제) |
| `tests/unit/engine/test_cycle62_price_filter_warn_mode.py` | **전체 2 케이스 (G-1~G-2)** | WARN 모드 폐기 | C (파일 전체 삭제) |
| `tests/unit/engine/test_cycle62_price_filter_daily_summary.py` | 전체 1 케이스 (H-1) | 사이클 64 H scanner 영역 신규로 대체 | C (파일 전체 삭제) |
| `tests/unit/engine/test_cycle62_price_filter_sell_unaffected.py` | E-1/E-2/E-3/E-4 → C+G 통합 흡수 | 사이클 64 C 카테고리 + G-1 AST 가드 흡수 | C (파일 전체 삭제) |
| `tests/unit/engine/test_cycle62_price_filter_emit_cap.py` | 전체 2 케이스 (C-1~C-2) | scanner 영역 E 2 신규로 대체 | C (파일 전체 삭제) |
| `tests/integration/test_cycle62_price_filter_integration.py` | 전체 5 케이스 (I-1~I-5) | scanner 영역 F 4 신규로 대체 | C (파일 전체 삭제) |
| `tests/unit/db/test_cycle62_price_filter_system_config.py` | A-1~A-5 → 사이클 64 A 4 신규로 대체 (mode 폐기) | A 카테고리 단순화 | C (파일 전체 삭제) |
| `tests/contract/test_cycle62_routes_price_filter.py` | CR-1~CR-3 → 사이클 64 C-Route 2 신규로 대체 | mode 폐기 | C (파일 전체 삭제) |
| `frontend/src/components/__tests__/PriceFilterCard.test.tsx::F-5` | F-5 mode 토글 케이스 | mode select 폐기 | A (해당 it 블록 삭제, 다른 4 케이스 갱신) |

**합계 폐기**: 사이클 62 백엔드 + integration + contract 10 파일 전체 + 프론트 1 it 블록 (38 케이스 중 18+ 케이스 폐기 / 갱신).

**Red 단계 = 표기만** — 실제 삭제는 backend-dev/frontend-dev Green 단계. 본 사이클 64 Red 24 케이스는 *신규 파일* 만 작성.

---

## §7. 통과 기준 (Red → Green 카운트)

| 단계 | 백엔드 PASS | 프론트 PASS | 비고 |
|---|---|---|---|
| Red 직후 | 2111 (변경 0) — 신규 24 케이스 FAIL/ImportError | 160 (변경 0) — F-FE 갱신 4 case 일부 FAIL | 본 Red 작성 영향 0 |
| Green 완료 (backend-dev) | **2111 + 24 - 18 폐기 = 2117** 추정 | **160 - 1 (F-5 폐기) = 159** 추정 | 사이클 62 폐기 18 + 사이클 64 신규 24 |

신규 24 케이스 모두 PASS 조건:
- A 4 = `get_price_filter()` 가 PriceFilter(min, max) 만 반환 (mode 없음) + `set_price_filter` mode 인자 거부
- B 5 = `_apply_price_filter` 신규 + 모든 분기 정확
- **C 4 HIGH** = `_collect_protected_tickers_for_scanner` 헬퍼 + early-return + 보유/익일청산 통과
- D 2 = `_get_price_filter_for_scanner` 60s TTL + `invalidate_price_filter_cache_scanner` 즉시 + unsubscribe 0건
- E 2 = `_price_filter_scanner_skip_logged_today` cap + `reset_price_filter_daily_state` 동행
- F 4 = scan → filter → subscribe + Settings PUT race + 보호 + funnel
- **G 2 HIGH** = risk.py 가격 필터 0건 + `_apply_price_filter` 호출 keyword 의무
- H 1 = `emit_price_filter_scanner_daily_summary` 1행 INFO
- C-Route 2 = mode 필드 폐기 + 422
- F-FE 4 = mode select 폐기 (5→4)

---

## §8. Q7-1 KIS LMS 차단 명시 (자동 unsubscribe 검증)

**Q7-1 (HIGH) 자문 확정**: `invalidate_price_filter_cache_scanner()` 호출 시 *기존 구독 종목 unsubscribe 발화 0건*. 다음 `_scan_loop` 5분 사이클 자연 delta 위임.

**D-2 케이스에 통합 검증**:
- Settings PUT → `invalidate_price_filter_cache_scanner()` 호출
- 검증: `kis_ws_pool.unsubscribe` mock 호출 0건
- 검증: 다음 `_get_price_filter_for_scanner()` 호출 시 DB 재조회 (즉시 반영)

이유: 즉시 unsubscribe = KIS 등록/해제 race → 사이클 17 OPSP0002 폭주 위험 (KIS 공지 "비정상 케이스 2 무한 등록/해제") 재발.

---

## §9. 실행 명령 (Red 검증)

```bash
# 본 사이클 신규 11 파일 단독 실행
pytest tests/unit/db/test_cycle64_price_filter_scanner_system_config.py \
       tests/unit/engine/test_cycle64_price_filter_scanner_apply.py \
       tests/unit/engine/test_cycle64_price_filter_scanner_protected.py \
       tests/unit/engine/test_cycle64_price_filter_scanner_cache.py \
       tests/unit/engine/test_cycle64_price_filter_scanner_emit_cap.py \
       tests/unit/engine/test_cycle64_price_filter_scanner_ast.py \
       tests/unit/engine/test_cycle64_price_filter_scanner_daily_summary.py \
       tests/integration/test_cycle64_price_filter_scanner_integration.py \
       tests/contract/test_cycle64_routes_price_filter.py -v

# 프론트
cd frontend && npm test -- PriceFilterCard
```

Red 단계 예상: 24 케이스 모두 FAIL/ImportError/AttributeError.

---

## §10. Green 후 영향 인덱스 갱신

```bash
python tools/test_impact/build_index.py
node  tools/test_impact/build_index_frontend.mjs
```

`_workspace/test_index.yaml` 의 `src/engine/scanner.py` + `src/db/system_config.py` + `src/engine/risk.py` (가격 필터 영역 제거) + `src/routes/system.py` + `frontend/src/components/PriceFilterCard.tsx` 의존 매핑 자동 재생성.
