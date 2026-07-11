# 사이클 205 (phase 1) — list_by_filter DB-side 필터 전환 (Red)

**명세 출처**: `_workspace/domain_consult/cycle205_universe_selection.md` (④ 1-a/1-b + 현 코드 정합)
**사용자 결정**: 보수 — DB-side 필터만. 정렬(refreshed_at DESC)·max_scan_stocks 유지.
**행위**: `list_by_filter` 의 시총/거래대금 Python-side 컷 → DB-side 생성 컬럼 gte 전환
(refreshed_at 편향 진원 = PostgREST 1000행 cap 오버페치 완화, 자격 ≤821<1000 전량 반환).

---

## 문제 (확정)

`src/db/stock_master.py::list_by_filter` (L562-735):
```
.order("refreshed_at", desc=True).limit(max(limit*2, 1000))   # 오버페치 + PostgREST 1000 cap
... Python-side int(raw.hts_avls)*1e8 < min_market_cap / int(raw.acml_tr_pbmn) < min_trade_amount ...
if len(filtered) >= limit: break                               # refreshed_at 순 절단
```
자격 821(BFB) 중 refreshed_at 최신 1000 버퍼에 든 42~143만 Python 필터 통과 = 나머지 누락.
refreshed_at 은 종목 품질 무관 축 → 자의적 부분집합 = selection bias.

**시정**: 시총/거래대금을 DB-side `.gte("hts_avls_eok", ...)` / `.gte("acml_tr_pbmn_won", ...)`
(사이클 168 migration 039 생성 컬럼, 인덱스 존재)로 전환 → 자격만 반환(≤821<1000) → cap/편향 동시 해소.
`list_paged_by_filter`(L384-500)가 **이미 이 패턴** — 임계 환산 로직(시총 원→억원 ceil, 거래대금 원 직접) 답습.

---

## Red

- 테스트 파일: `tests/unit/db/test_cycle205_list_by_filter_db_side.py` (14 케이스)
- Fake Supabase = 사이클 168 `FakeQuery` 클래스 패턴 답습 (다중 `.execute()` 지원 = 3쿼리 필수).
  `.gte/.eq/.or_/.order/.limit` 호출 전수 캡처(`seen` dict) + `executes` 카운트 + per-execute rows 시퀀스.

### 실행 결과 (현재 코드 = Red)
```
9 failed, 5 passed
```

**FAIL 9 (시정 대상)**:
| 케이스 | FAIL 사유 (현재 코드) |
|--------|----------------------|
| G-205-1a market_cap gte | `.gte("hts_avls_eok", 1000)` 미발생 (Python-side 컷) |
| G-205-1b trade_amount gte | `.gte("acml_tr_pbmn_won", 200억)` 미발생 |
| G-205-1e 비숫자/null 컷 | 생성 컬럼 gte 미사용 (raw Python 파싱 잔존) |
| G-205-2a fetch_limit 폐지 | `.limit(300)` 아닌 `max(300*2,1000)=1000` 걸림 |
| G-205-3a 3쿼리 | 단일 쿼리(execute=1), 3쿼리 부재 |
| G-205-4b sort_by 인자 | `sort_by` keyword 부재 |
| G-205-5a OR + mcap gte | 시총 gte 미발생 (Python-side) |
| G-205-5b eq + mcap gte | 시총 gte 미발생 |
| G-205-6b 시그너처 | `sort_by` 부재 |

**PASS 5 (불변식 — Green 후에도 유지 의무)**:
| 케이스 | 불변식 |
|--------|--------|
| G-205-1c 임계 0 시 gte 금지 | min_market_cap=0/min_trade_amount=0 → 시총/거래대금 gte 미발생 (무필터 보존) |
| G-205-1d 유효 rows 전량 반환 | 임계 이상 rows 전량 반환 (mock 미필터라 현재도 PASS, Green 후 raw 재컷 잔존 시 회귀 검출) |
| G-205-3b 기본 list/단일쿼리 | 미지정 → list + execute=1 |
| G-205-4a refreshed_at DESC 유지 | sort_by=None → `.order("refreshed_at", desc=True)` (phase 1 정렬 무변경) |
| G-205-6a 반환 row 필드 불변 | ticker/name/excg_dvsn_cd/nxt_tradable/is_kospi200/is_kosdaq150/raw |

---

## Green 구현 지시 (backend-dev — 정확 라인)

대상: `src/db/stock_master.py::list_by_filter` (L562-735).

1. **시그너처** (L562-573): `sort_by: str | None = None` 인자 추가 (phase 2 훅 — phase 1 은 None 만).
2. **임계 환산** (L610 fetch_limit 위): `list_paged_by_filter` L431-438 답습.
   - `hts_avls_threshold = (min_market_cap + 99_999_999) // 100_000_000` (min_market_cap>0 시, ceil).
     ★ 동치 근거: Python-side `hts_avls*1e8 >= min_market_cap` ⟺ `hts_avls >= ceil(min_market_cap/1e8)`.
   - `acml_tr_pbmn_threshold = int(min_trade_amount)` (min_trade_amount>0 시).
3. **fetch_limit 폐지** (L611-612): `fetch_limit = max(limit*2, 1000)` 제거 → 쿼리에 `.limit(limit)` 직접.
4. **쿼리 빌더** (L614-639): `refreshed_at` order 유지(sort_by=None) + market/nxt/index(or_/eq) 유지 +
   **`.gte("hts_avls_eok", hts_avls_threshold)` (threshold>0)** + **`.gte("acml_tr_pbmn_won", acml_tr_pbmn_threshold)` (threshold>0)** AND 결합.
5. **Python-side 시총/거래대금 컷 제거** (L697-721): `if min_market_cap>0: ... hts_avls*1e8 < min_market_cap: continue`
   + `if min_trade_amount>0: ... acml_tr < min_trade_amount: continue` **삭제** (DB-side 이관).
   ★ exclude_tickers / index OR·AND / 6자리 형식(호출자) Python-side 로직은 **유지** (DB 미이관).
6. **return_stage_counts=True = 3쿼리** (L644-734): 단일 루프 카운트(사이클 170) → 3쿼리:
   - union: index/market/nxt 필터만 (mcap/trade gte **없이**) → exclude Python 제외 → `union_tickers`
   - mcap: union + 시총 gte → exclude 제외 → `mcap_tickers`
   - trade: mcap + 거래대금 gte → exclude 제외 → `trade_tickers` (= filtered rows)
   각 쿼리 동일 정렬(refreshed_at DESC)+`.limit(limit)`. union⊇mcap⊇trade + `trade==filtered`(원소·순서, G-A-1) 유지.
7. **docstring** (L578-579 "JSONB 숫자 비교 미지원 → limit*2 버퍼 후 Python-side 필터"): DB-side 생성 컬럼 전환 반영.
   L589-590 "raw miss=graceful 통과" → 실동작(생성 컬럼 NULL = gte 자동 제외) 정정.
8. **max_scan_stocks 불변**: 전략 DEFAULT_PARAMS 변경 0 (phase 1).

---

## 의미 전환 목록 (backend-dev — Green 시 갱신 의무, 임의 삭제 금지 = 사이클 66 K-2)

DB-side 전환으로 **기존 mock 이 Python-side 필터 동작을 흉내내지 못해** 회귀하는 테스트. mock 이
gte 필터를 시뮬레이션하거나(rows 를 임계 기준 사전 분할 주입), 3쿼리 per-execute rows 를 주도록 갱신.

### `tests/unit/db/test_cycle108_list_by_filter.py` (Python-side 컷 의존 → DB-side)
| 케이스 | 회귀 사유 | 갱신 방식 |
|--------|----------|----------|
| `TestListByFilterHigh1::test_h1_min_market_cap_filters_correctly` | mock 미필터 → 000002(500억) 도 반환 (Python 컷 제거) | mock 이 `hts_avls_eok` gte 시뮬레이션 (rows 사전 분할) 또는 000002 를 gte 임계 미달 생성 컬럼으로 주입해 DB 제외 흉내 |
| `TestListByFilterHigh1::test_h1_min_trade_amount_filters_correctly` | 동일 (거래대금 컷) | 동일 (`acml_tr_pbmn_won`) |
| `TestListByFilterHigh5::test_h5_hts_avls_just_below_threshold_excluded` | 999억 Python 컷 제거 | mock gte 시뮬레이션 |
| `TestListByFilterHigh5::test_h5_hts_avls_missing_graceful` | hts_avls=0 Python 컷 제거 | 생성 컬럼 NULL row = gte 제외 흉내 |
| `TestListByFilterMedium3::test_m3_fetch_limit_is_double` | `.limit>=200` 단언 → fetch_limit 폐지로 `.limit(limit)` | **의미 전환**: `.limit == 요청 limit` 로 단언 갱신 (오버페치 폐지 = G-205-2 정합) |
| (KEPT) `test_h1_exclude_tickers` / `test_h1_nxt_tradable` / `test_h1_limit_caps_result` / `test_h5_..._1trillion` / `test_m3_no_kis_api_import` | Python-side exclude/eq/limit-cap/pass = 불변 | 무변경 |

### `tests/unit/db/test_cycle170_card_a_stage_counts.py` (단일 루프 → 3쿼리)
| 케이스 | 회귀 사유 | 갱신 방식 |
|--------|----------|----------|
| `test_g_a_1_filtered_identical_...` | 단일 mock rows → base(1쿼리) vs paired(3쿼리) 결과 불일치 | mock 이 trade 쿼리 = 최종 filtered rows 반환하도록 per-execute rows 주입 (base=trade 쿼리와 동일 rows) |
| `test_g_a_2_stage_monotonic` | union/mcap/trade 가 동일 mock rows → 단조성 붕괴 | per-execute rows 3단(union⊇mcap⊇trade) 주입 |
| `test_g_a_3_realistic_attrition_348_348_321` | 단일 mock 348 rows → 3쿼리 모두 348 (321 미재현) | union=348/mcap=348/trade=321 per-execute rows 주입 |
| (KEPT) `test_g_a_4_default_returns_list` / `test_g_a_5_donchian_...`(_scan_universe monkeypatch) / `test_g_a_6_ast_signature` | 미지정 list / 직접 monkeypatch / keyword 존재 = 불변 | 무변경 |

### 무관 (확인만, 변경 0)
- `tests/unit/db/test_cycle153_list_by_filter_index_flags.py` — is_kospi200/is_kosdaq150 OR/eq Python-side
  필터는 **유지** (DB 미이관). min_market_cap=0/min_trade_amount=0 로 호출 → 시총/거래대금 gte 미발생 → 무영향.
- `tests/unit/db/test_cycle128_list_paged_by_filter.py` — `list_paged_by_filter`(UI, 별개 함수) 무관.
- `tests/unit/db/test_cycle168_list_paged_generated_cols.py` — `list_paged_by_filter` 무관.

---

## 검증 매트릭스 (Green 후 tester/tdd 확인)

- 격리: `test_cycle205_list_by_filter_db_side.py` 14 PASS ×2 (flakiness 0).
- 인접: cycle108(의미 전환 후) + cycle170(의미 전환 후) + cycle153 + cycle128 + cycle168 전량 PASS.
- **매매 안전성 8영역 diff 0**: `git diff -- src/engine/risk.py src/engine/order_engine.py src/realtime/
  src/auth/ src/api/order.py src/engine/session.py src/engine/scanner.py src/engine/strategy_registry.py` = 0
  (list_by_filter 는 scanner 매수 진입 *전* 유니버스 구성, 사이클 38 명문화 + 사이클 32 R4 보유 절대 보호 무관).
- 전략 호출자 5(VB/LTV/BFB/VCP/donchian): `list_by_filter` 반환 형식 불변(G-205-6a) → prepare 회귀 0.
  return_stage_counts=True 소비처(donchian/VCP `_scan_stage_counts`) 계약 보존(G-205-3a trade==filtered).

## 인계 (phase 2)
- sort_by 훅 실사용 (거래대금/시총 DESC 정렬 전환) = 별도 사이클 (자문 ①②).
- max_scan_stocks 상향(BFB 100→300 등) = DEFAULT_PARAMS 변경 → `00_leader_trading_rules.md` 동기화 의무.
- D+1 운영 실측: BFB 자격 전량 반환 확인 + PostgREST 1000 cap 재발 여부(자격>1000 시).
