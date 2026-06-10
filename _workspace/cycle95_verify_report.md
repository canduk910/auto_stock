# 사이클 95 통합 tester verify 보고서

작성 시각: 2026-06-10 KST
대상: 사이클 95 chicken-and-egg 결함 시정 + UI 전일종가 + 시장 한글 변환 통합
범위: V-1~V-8 전수 검증 / production 코드 변경 0 (검증 단독)

---

## V-1 (HIGH) 전체 회귀 0 — PASS

| 영역 | 결과 |
|------|------|
| 백엔드 | **2293 PASS + 2 skip + 7 xfail** (사이클 94 M-3 의미 전환 포함) |
| 프론트 | **245 PASS** (41 test files) |
| 합계 | **2538 PASS / 회귀 0** |

Green 보고치 그대로 영속. 사이클 94 `test_m3_graceful_missing_market_id_skips_ticker` 가 xfail 정확 마킹 (사이클 66 K-2 패턴 답습, 의미 전환 — 사이클 95 unknown 합집합 채택으로 graceful skip 결함 confirm 자동 가시화).

## V-2 (HIGH) flakiness 0 — PASS (3 회 반복)

| 회차 | 백엔드 | 프론트 |
|------|--------|--------|
| 1 | 61.83s, 2293/2/7 | 4.17s, 245 |
| 2 | 56.47s, 2293/2/7 | 3.74s, 245 |
| 3 | 64.02s, 2293/2/7 | 4.23s, 245 |

카운트 3 회 완전 동일. ±10% 시간 진동 정상 (CI 환경 영향, flakiness 0 확정).

## V-3 (HIGH) 신규 25 케이스 카테고리 분리 — PASS

### 백엔드 18 케이스 (8 파일)
- `test_cycle95_unknown_split.py` 2 (H-1) — unknown 합집합 신규 + subset 검증
- `test_cycle95_universe_500_lock_in_break.py` 3 (H-2) — lock-in 차단 + remaining cap (full KOSPI/KOSDAQ + overflow unknown)
- `test_cycle95_classify_market_graceful.py` 3 (H-3) — `_classify_market` None 분기 + partition + `_fetch_top_500_universe` unknown append
- `test_cycle95_emit_visibility_unknown.py` 2 (M-1) — emit 문자열 `unknown=%d` + collector 키 추가
- `test_cycle95_chain_with_unknown.py` 3 (M-2) — universe chain 입력 + signature 무변경 + upsert chain 진입
- `test_cycle95_g_reject_persistence.py` 2 (L-1) — 사이클 88 G-REJECT-1/2/3 가드 파일 영속 + 사이클 95 scanner 신규 키워드 0건
- `test_cycle95_kst_persistence.py` 3 (L-2) — `_kst` helper export + KST timezone 값 + scanner utc_now 오용 0
- `test_cycle94_graceful_market_id_missing.py::test_m3` 1 XFAIL — 사이클 94 graceful skip 결함 confirm 영속 (사이클 95 시정으로 자동 가시화)

전수 PASS (0.28s).

### 프론트 7 케이스 (`StockMaster.test.tsx` 27 신규 영역 포함, 0.52s)
- H-4 전일종가 3 — `<thead>` 컬럼 헤더 + `<tbody>` formatPrice 천단위 콤마 + raw NULL graceful
- H-5 시장 한글 2 — `'02': 'KOSPI'` + `'03': 'KOSDAQ'` + STK/KSQ backward compat
- M-3 formatExchange 2 — 헬퍼 추출 + 라벨 매핑 정확

전수 PASS.

## V-4 (HIGH) 영속 의무 매트릭스 8 영역 — PASS

| # | 영속 영역 | 가드 파일 | 결과 |
|---|----------|----------|------|
| 1 | 사이클 88 G-REJECT (89/90/92 누적) | `ast/test_cycle89_g_reject_persistence.py` 외 2 | PASS |
| 2 | 사이클 89/94 (KOSPI/KOSDAQ 500 cap + `_fetch_volume_rank` 단일 + max_pages=17 + `"0000"` 단일) | `scanner.py:1505/1587/1464`, `ast/test_cycle94_ast_no_industry_code.py` | PASS (grep + AST) |
| 3 | 사이클 93 `_scanner_upsert_loop` chain | `ast/test_cycle93_ast_chain_required.py` + 2 scheduler | PASS |
| 4 | 사이클 68 KST 일관성 (G-1/G-10/G-11) | `db/test_cycle68_*_g{1,10,11}.py` | PASS |
| 5 | 사이클 75 G-RT retry:1 (변경 0) | `frontend/_ast_useQuery_retry_required.test.ts` (7) | PASS |
| 6 | 사이클 80 hotfix #3 LIFO (e2e api-mocks) | `e2e_mocks/test_cycle85_api_mocks_stock_master_lifo.py`, `_cycle75_*` | PASS |
| 7 | 사이클 94 UI 안내 배너 (`stock-master-info-banner`) | `frontend/StockMaster.tsx:471` | PASS (grep) |
| 8 | 사이클 85 G-KST / H-POLLING / H-DETAIL | 41 케이스 통합 영속 | PASS (V-1 합계 포함) |

직접 측정 13 가드 파일 = **35 PASS** (0.26s) + 프론트 7 PASS (0.44s).

## V-5 (HIGH) 매매 안전성 무영향 — PASS

| 검증 | 결과 |
|------|------|
| scanner 단계 (매수 진입 전, 사이클 38 명문화 영속) | `risk.py:105/120` `tradable_boards` 매수 전용 정책 + `long_tail_volatility.py:53` 명문화 영속 |
| KIS 호출 0 증가 (Rate Limit) | `_fetch_volume_rank` 단일 호출 영속 (사이클 94), unknown 분류 = 메모리만 |
| 매도/손절/익일청산/15:20 hot path 무영향 | `risk.on_tick` `check_exit_signal` 분기 무변경, `session_tracker.is_tradable` 검사 *전* 진입 영속 |
| CLAUDE.md "절대 깨지 말 것" 8 영역 영속 | 체결통보 `H0STCNI0/H0STCNI9` (`websocket.py:55`) / 단일 워커 / 주문번호 매핑 (`order_engine.py:81/375`) / `_reset_daily_state` / 익일청산 30s / NXT 좀비 (`SellRejectionTracker` `order_engine.py:88`) / WebSocket 4중 (`MAX_SUBSCRIPTIONS=41` + bypass_limit) / KIS 거부 `[kis_rejection]` 전수 영속 |

## V-6 (HIGH) chicken-and-egg lock-in 영구 차단 — PASS

- `scanner.py:1607` `unknown: list[dict] = []` 신규 — graceful None 영역 합집합 (continue 금지)
- `scanner.py:1625` `remaining = max(0, 500 - len(kospi_sorted) - len(kosdaq_sorted))` cap
- `scanner.py:1626` `unknown_sorted = unknown[:remaining]` (overflow 차단)
- `scanner.py:1640` `[stock_master_bulk_refresh] universe=%d kospi=%d kosdaq=%d unknown=%d ...` emit 운영 가시화
- 첫 호출에서 ~500 ticker upsert chain trigger → 다음 사이클부터 KOSPI/KOSDAQ 분리 자연 회복
- H-2 3 케이스 (lock-in 차단 + full cap + overflow unknown) 전수 PASS = 78 → 500 ticker 영속 효과 확정

## V-7 (MEDIUM) UI 시각 영역 — PASS

| 영역 | 검증 |
|------|------|
| 전일종가 컬럼 헤더 + 천단위 콤마 | `StockMaster.tsx:86` `bfdy_clpr: '전일종가'` + `:121` `formatPrice` + `:650` list `<tbody>` |
| 시장 한글 표기 | `StockMaster.tsx:101` `formatExchange` 헬퍼 + `:197/647` 적용 (raw `"02"/"03"` 직접 노출 0건) |
| 모바일 375px 가로 스크롤 | `:615/713` `overflow-x-auto` 영속 |
| 사이클 94 안내 배너 | `:471` `data-testid="stock-master-info-banner"` 영속 |

`StockMaster.test.tsx` 27 PASS (신규 7 포함).

## V-8 (MEDIUM) 사이클 96+ 인계 명세 — 영속

- **사이클 95 Phase A/B (VB/LTV/BFB + donchian/VCP stock_master 베이스 전환)** Plan 영속 — 본 사이클은 Phase 0 (chicken-and-egg lock-in 차단) 단독, Phase A/B 별개 사이클 인계
- **사이클 96+ Phase C** (UI 운영자 필터링) 인계
- **익일 (2026-06-11 목) 07:55** 운영 측정 권고: 사이클 92+93+94+95 통합 효과 — `[stock_master_bulk_refresh]` unknown 카운트 추이 + 78 → 500 ticker 회복 검증
- 카드 #21 (LOW 사이클 74 flaky) / #16 (Q6-3) / auth 1.43x 영속

---

## 종합 판정 — PASS (push 권고)

V-1~V-8 8 영역 전수 충족. 회귀 0 / flakiness 0 / 영속 매트릭스 8 영역 / 매매 안전성 무영향 / chicken-and-egg lock-in 영구 차단 확정.

**관련 파일 (절대 경로)**:
- `/Users/koscom/Projects/auto_stock/src/engine/scanner.py` (+9L, 사이클 95 unknown 합집합)
- `/Users/koscom/Projects/auto_stock/frontend/src/pages/StockMaster.tsx` (+9L, formatExchange + 전일종가)
- `/Users/koscom/Projects/auto_stock/tests/unit/engine/scanner/test_cycle95_*.py` 7 신규 + 사이클 94 M-3 xfail 의미 전환
- `/Users/koscom/Projects/auto_stock/frontend/src/pages/__tests__/StockMaster.test.tsx` (27 PASS, 신규 7 포함)
