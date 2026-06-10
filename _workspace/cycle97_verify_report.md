# 사이클 97 tester verify 보고서 — KIS fluctuation API 영역 신규 도입 + 사이클 89/91/94/96 전수 폐기

**작성일**: 2026-06-10
**검증자**: tester (auto-trading-orchestrator)
**선행 영역**: `_workspace/red/cycle97_fluctuation_api_replacement.md` (Red 명세)
**대상**: Q52=A KIS fluctuation 신규 + Q53=A volume_rank 전수 폐기 + Q54=A 진단 직후 push
**production 코드 변경**: 0 (검증 단독)

---

## V-1 (HIGH) 전체 회귀 0 — PASS

| 영역 | 결과 | 비고 |
|------|------|------|
| 백엔드 | **2294 passed + 2 skipped + 53 xfailed + 1 xpassed** | Green 보고 동일 카운트 |
| 프론트 | **245 passed (41 files)** | 4.31s |
| **합계** | **2539 PASS / 회귀 0** | |

xfail 53 = 사이클 89/91/94/96 영역 전수 폐기 의미 전환 (사이클 66 K-2 패턴 영속).
xpass 1 = `test_cycle96_g_reject_persistence.py::test_l1_g_reject_pattern_no_external_llm_call_in_scanner` (사이클 97 L-1 가드가 영역 흡수, 외부 LLM 영구 차단 영역 확장).

---

## V-2 (HIGH) flakiness 3 회 반복 — PASS

| 회차 | 결과 | 실행 시간 |
|------|------|-----------|
| 1 | 2294 PASS / 2 skip / 53 xfail / 1 xpass | 49.24s |
| 2 | 2294 PASS / 2 skip / 53 xfail / 1 xpass | 49.40s |
| 3 | 2294 PASS / 2 skip / 53 xfail / 1 xpass | 49.47s |

**flakiness 0** (±0.5% 시간 분산, 카운트 완전 동일).

---

## V-3 (HIGH) 신규 27 sub-case 카테고리 분리 — PASS

| 매트릭스 | 위치 | 케이스 | 결과 |
|----------|------|--------|------|
| **H-1** URL/TR_ID AST | `test_cycle97_fluctuation_url_tr_id.py` | 3 | PASS |
| **H-2** 페이징 누적 ≥500 | `test_cycle97_fluctuation_pagination_500.py` | 2 | PASS |
| **H-3** `FID_INPUT_CNT_1` 제어 | `test_cycle97_fid_input_cnt_1_control.py` | 3 | PASS |
| **H-4** volume_rank 폐기 | `test_cycle97_volume_rank_deprecated.py` | 4 | PASS |
| **H-5** AST 영구 가드 | `tests/unit/ast/test_cycle97_ast_no_volume_rank.py` | 4 | PASS |
| **M-1** `[stock_master_bulk_refresh]` emit | `test_cycle97_emit_visibility_fluctuation.py` | 2 | PASS |
| **M-2** Rate Limit + 2 call | `test_cycle97_rate_limit_2call.py` | 2 | PASS |
| **M-3** `_universe_eager_refresh_loop` chain | `test_cycle97_scanner_upsert_chain.py` | 2 | PASS |
| **L-1** G-REJECT 영속 | `test_cycle97_g_reject_persistence.py` | 3 | PASS |
| **L-2** KST 영속 | `test_cycle97_kst_persistence.py` | 2 | PASS |
| **합계** | | **27** | **전수 PASS** |

---

## V-4 (HIGH) 영속 의무 매트릭스 10 영역 — PASS

| 영속 의무 | 사이클 97 영향 | 검증 영역 |
|-----------|---------------|---------|
| 사이클 32 R4 universe guard (보유/익일청산 보호) | **영향 0** | 영역 분리 |
| 사이클 38 명문화 (매수 진입 전용) | **영향 0** | `risk.py` / `order_engine.py` 변경 0 |
| 사이클 64 protected_tickers | **영향 0** | 영역 분리 |
| 사이클 65 거래대금 동행 필터 | **영향 0** | 영역 분리 |
| 사이클 81 `bfdy_clpr` 가격필터 키 | **영향 0** | 영역 분리 |
| 사이클 88 G-REJECT 외부 LLM AST | **영속** | L-1 가드 흡수 + 확장 |
| 사이클 89 ETF 제외 + 거래대금 정렬 | **흡수** | fluctuation 영역에서 `_universe_filter_securities_only` + `_trade_amount_key` 적용 |
| 사이클 91 페이징 누적 (`tr_cont` "" → "N") | **흡수** | fluctuation 영역 적용 |
| 사이클 93 chain 영속 | **영속** | 호출 chain 변경 0 |
| 사이클 95 unknown=0 영속 | **영속** | 2 call 분리 = unknown 불필요 |
| 사이클 96 KOSPI/KOSDAQ 분리 호출 | **흡수** | fluctuation 영역 적용 |
| **CLAUDE.md "절대 깨지 말 것" 8 영역** | **영향 0 전수** | scanner 단독 + 매도 hot path 무영향 |
| **KIS LMS chain 차단** | **영속** | KIS 단위 영역 호환 (fluctuation 정본 정합) |

---

## V-5 (HIGH) 매매 안전성 무영향 — PASS

`git diff --stat` 결과:

| 파일 | 변경 |
|------|------|
| `src/engine/scanner.py` | +113 / -106 (순 +7L) |
| `src/engine/risk.py` | 변경 0 |
| `src/engine/order_engine.py` | 변경 0 |
| `src/engine/scheduler.py` | 변경 0 |

scanner 단계 (매수 진입 *전*, 사이클 38 명문화 영속) 단독 시정. 매도/손절/Trailing/익일청산 hot path 영향 0.

---

## V-6 (HIGH) KIS volume_rank 영역 영구 폐기 — PASS

`grep` 검증 결과 (scanner.py source):
- `volume-rank` URL literal: **0건**
- `FHPST01710000` TR_ID literal: **0건**
- `_VOLUME_RANK_URL` 상수: **0건**
- `_VOLUME_RANK_TR_ID` 상수: **0건**
- `_fetch_volume_rank` 함수: **0건**
- `_MARKET_INPUT_ISCD` dict (구 명명): **0건** (신규 `_FLUCTUATION_MARKET_INPUT_ISCD` 로 영역 분리)

AST H-5 4 케이스 전수 PASS = **미래 회귀 영구 차단**.
xfail 53 의미 전환 = 사이클 89/91/94/96 영역 전수 폐기 confirm (사이클 66 K-2 패턴 영속).

---

## V-7 (MEDIUM) KIS fluctuation 영역 도입 — PASS

`grep` 검증 결과 (scanner.py source):
- `_FLUCTUATION_URL == "/uapi/domestic-stock/v1/ranking/fluctuation"`: **정합**
- `_FLUCTUATION_TR_ID == "FHPST01700000"`: **정합**
- `_FLUCTUATION_MARKET_INPUT_ISCD = {"kospi": "0001", "kosdaq": "0002"}`: **정합**
- 응답 키 `stck_shrn_iscd` 사용 (`row.get("stck_shrn_iscd") or row.get("mksc_shrn_iscd", "")`): **정합** (KIS chk_fluctuation.py COLUMN_MAPPING 정본)
- `FID_INPUT_CNT_1 = str(top_n)` 사용자 제어: **정합**
- 페이징 누적 (`tr_cont == "M"` → `"N"`): **정합** (KIS 정본 패턴)
- 50ms sleep (사이클 83 Rate Limit 영속): **정합**

H-1/H-2/H-3/M-1/M-2 합 12 sub-case 전수 PASS.

---

## V-8 (MEDIUM) 사이클 98+ 인계 명세

| 인계 영역 | 내용 |
|-----------|------|
| **운영 측정 (HIGH, 다음 영업일 2026-06-11 목요일 09:30~)** | `[stock_master_bulk_refresh] universe=500 kospi=250 kosdaq=250 unknown=0 securities=500 etf_excluded=N elapsed_ms=...` 1행 실측 + KIS fluctuation API (FHPST01700000) 운영 정합 확인 |
| **사이클 92~97 통합 측정** | 07:55 KIS 강제 중단 충돌 시정 + chain broken 시정 + chicken-and-egg lock-in 시정 + KOSPI/KOSDAQ 분리 + fluctuation 신규 도입 통합 운영 측정 |
| **사이클 95 Plan Phase A/B** | VB / LTV / BFB + donchian / VCP stock_master 베이스 전환 (사이클 95 Plan 영속) |
| **사이클 96+ Phase C** | UI 운영자 필터링 영역 |
| **카드 #21 (LOW, 사이클 74 flaky)** | 영속 인계 |
| **xfail 53 정리 (사이클 100+ 의제)** | 누적 cleanup 검토 (현재 영속 영역 — 사이클 66 K-2 패턴) |

---

## 결론

사이클 97 tester verify **전수 PASS**. KIS fluctuation API 영역 신규 도입 + 사이클 89/91/94/96 volume_rank 영역 전수 폐기 영구 시정 완료.

- V-1~V-8 8 영역 전수 PASS
- 회귀 0 / flakiness 0 (3 회 ±0.5%)
- 매매 안전성 무영향 (scanner 단독 + 사이클 38 명문화 영속)
- KIS volume_rank 영역 영구 폐기 (H-5 AST 가드 4 PASS)
- KIS fluctuation 영역 정본 정합 (URL + TR_ID + 응답 키 `stck_shrn_iscd` + 페이징 + Rate Limit)
- 영속 의무 매트릭스 10 영역 전수 영향 0 또는 흡수

push 권고 = Q54=A 진단 완료 직후 (사이클 97 시정 의무 영속).
운영 실증 의무 = 다음 영업일 2026-06-11 목요일 09:30~ KIS API fluctuation 영역 정상 호출 + universe=500 정상 적재 + unknown=0 정상 확인.
