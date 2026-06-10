# 사이클 100+ Phase 1 진단 — 4 영역 통합

**일자**: 2026-06-11 (Phase 1 READ-ONLY, 코드 변경 0)
**범위**: A KIS MCP 정본 재검증 / B 주문 발주 시장 분기 / C UI prefix 정합 / D 전체 종목 list + KIS API 만으로 stock_master 완성

---

## A. KIS MCP 정본 재검증 결과

### A-1. 전체 종목 list API — **단일 API 부재 확정**

`mcp__kis-code-assistant__search_domestic_stock_api` 156 API 전수 검색 결과 = **"전체 상장종목 list 다운로드 API" 단일 진입점 없음**. 정본 후보 5종:

| API | function | 한도 | 페이징 (tr_cont="M") | 시장 분기 |
|-----|----------|------|---------------------|----------|
| `market_cap` (FHPST01740000) | 시가총액 상위 | 단일 페이지 30 | **지원** (`tr_cont="M"` 영속) | `fid_input_iscd`: 0000전체 / 0001거래소 / 1001코스닥 / 2001코스피200 |
| `fluctuation` (FHPST01700000) | 등락률 상위 | 단일 페이지 30 | **사이클 98 확정 영구 비반환** | KOSPI/KOSDAQ 분리 호출 |
| `volume_rank` (FHPST01710000) | 거래량 순위 | 단일 페이지 30 | **사이클 96 확정 영구 비반환** | KOSPI/KOSDAQ 분리 호출 |
| `psearch_result` | 조건검색 결과 | HTS 사전 등록 의무 | 미지원 | 등록 운영자 영역 |
| `intstock_stocklist_by_group` | 관심종목 그룹별 | 그룹 미리 등록 의무 | 미지원 | HTS 관심종목 영역 |

**결정적 발견 (사이클 99 영속 영역 직접 해결 후보)**:
- **`market_cap` (FHPST01740000) 이 KIS 156 API 중 *유일하게 `tr_cont="M"` 페이징 지원 확정*** (정본 코드 L107~120 영역 재귀 호출 영속). 사이클 96/98 `volume_rank`/`fluctuation` 영구 비반환 확정 와 본질 차이.
- 페이징 호출로 KOSPI 전체 (~960종목) + KOSDAQ 전체 (~1,800종목) 시가총액 정렬 순회 가능 (한도 추정 ~3,000+ ticker).
- 단, 정렬 = 시가총액 (등락률/거래량 정렬 아님) — 사이클 99 `fluctuation` 영역 기능 차이.

### A-2. 개별 종목 정보 API — **2 API 정본 확정**

| TR_ID | function | URL | 컬럼 | 비고 |
|-------|----------|-----|------|------|
| **CTPF1604R** | `search_info` | `/uapi/domestic-stock/v1/quotations/search-info` | 12 컬럼 (상품번호 / 유형 / 판매상태 / 위험등급 등) | 재귀 페이징 지원 (`tr_cont="M"`) — 다국가 상품 (300주식/301선물/302채권/512미국 등) |
| **CTPF1002R** | `search_stock_info` | `/uapi/domestic-stock/v1/quotations/search-stock-info` | **67 컬럼** | 사이클 81 영속 (`bfdy_clpr` 전일종가) + `cptt_trad_tr_psbl_yn` **NXT 거래종목여부** + `nxt_tr_stop_yn` **NXT 거래정지여부** = stock_master `nxt_tradable` 정본 |

**핵심 67 컬럼 (CTPF1002R)**: `prdt_name`/`mket_id_cd`/`scty_grp_id_cd`/`excg_dvsn_cd`/`lstg_stqt`(상장주수)/`papr`(액면가)/`kospi200_item_yn`/`scts_mket_lstg_dt`(KOSPI 상장일)/`kosdaq_mket_lstg_dt`/`tr_stop_yn`(거래정지)/`admn_item_yn`(관리종목)/`thdt_clpr`(당일종가)/`bfdy_clpr`(전일종가)/`cptt_trad_tr_psbl_yn`(NXT 거래종목)/`nxt_tr_stop_yn`(NXT 정지).

**사용자 의도 검증** = "기타 API 없이 KIS API만으로 종목마스터 구성" = **확정 가능** (영역 D 청사진 참조).

---

## B. 주문 발주 시장 분기 영역 — **사이클 13/54/55 R-1 영속 영역 확정**

| 영역 | 위치 | 영속 사이클 | 행위 |
|------|------|------------|------|
| 매수 진입 전 NXT 사전 차단 | `order_engine.py::_strategy_exchange_async` L128~197 | 사이클 13 (Phase G) | `stock_master.get(ticker).nxt_tradable=False` → NXT/SOR → KRX 강제 + `[nxt_downgrade]` WARNING |
| 매도 진입 전 NXT 사전 차단 | `order_engine.py::execute_sell` L543 (`target_exchange = await self._strategy_exchange_async(...)`) | 사이클 13 (Phase G) | 매도 경로에도 동일 함수 호출 영속 |
| nxt_downgrade 로그 1회/일 cap | `_nxt_downgrade_logged_today: DailyEmitCap[str]` L92 | 사이클 54 (2026-06-03) | ticker별 1회/일 (다운그레이드 결정은 cap 밖) |
| NXT 매도 거부 진입 게이트 | `_sell_rejection.is_blocked(ticker, now_kst)` L505 | 사이클 55 R-1 (2026-06-03) | 2단계 TTL — KRX 메인 5분 / NXT 시간대 다음 KST 09:00 / market_order_disallowed 30초 |
| NXT 매도 거부 사후 보강 | L620~643 `stock_master.upsert_one(ticker, nxt_tradable=False)` | 사이클 13 | KIS 거부 응답 기반 stock_master 영구 보강 |
| 익일 청산 자동 전환 | `_pending_next_day_clear_provider().add((ticker, strategy_id))` L754 | 사이클 55 R-1 | NXT 폴백 실패 시 `[next_day_clear_deferred]` WARNING 1행 |

**Supabase 실측 (7일)**: `[nxt_downgrade]` 1건 WARNING / `[market_closed_blocked]` 2건 INFO = 영속 정상 작동. **사용자 보고 "08:00:00 APBK0918 매도 거부 = 적시 청산주문 놓칠 수 있다 우려"** 영역 = 사이클 55 R-1 영속이 정확히 해당 결함 영구 차단 영역.

**가능 시정 영역 (사용자 결정 A 채택 시)**:
- 옵션 B-1: 현 영속 영역 정합 검증만 (회귀 가드 강화) — 코드 변경 0
- 옵션 B-2: stock_master 영역 참조 확장 (`krx_halted` + `admin_item` 추가 분기) — 거래정지/관리종목 사전 차단 강화 (현 사용자 보고 영역 외)
- 옵션 B-3: 매도 진입 게이트 진입 전 stock_master eager refresh (lazy 한계 차단) — 보유 종목 시점 미스 차단 (사이클 13-D `_eager_refresh_stock_master_for_held_positions` 영속 영역 확장)

---

## C. UI prefix 정합 영역 — **3 prefix 영속 + UI 단일 grep 결함**

### C-1. 백엔드 실제 emit prefix (Supabase 실측 7일)

| prefix | 7일 cnt | 발화 영역 | 사이클 |
|--------|--------|----------|-------|
| `[universe_eager_refresh]` | **244** (최다) | `scheduler._universe_eager_refresh_loop` (5분 주기) | 사이클 89 |
| `[scan_pool_eager_refresh]` | 230 | `scheduler._scan_pool_eager_refresh_loop` (5분 주기) | 사이클 83 |
| `[stock_master_bulk_refresh]` | 140 | `scanner.fetch_top_500_universe` 내부 (개장 전 1회) | 사이클 89/95 |

### C-2. UI 단일 grep 결함

`db/stock_master.py::count_eager_refresh_today` L185 = `ilike("message", "%[scan_pool_eager_refresh]%")` **단일 grep** → UI `StockMaster.tsx::scanPoolQuery.data?.eager_refresh_today` (L548) → "오늘 자동 갱신 횟수" 표시 = **244 (universe_eager_refresh) + 140 (bulk_refresh) 누락** = 실제 발화 대비 ~62% 영역만 노출.

### C-3. 시정 영역

- 옵션 C-1: db/stock_master.py L185 grep 3 prefix `OR` 합산 (영구 시정, 1줄 변경) — UI 텍스트 변경 0
- 옵션 C-2: API 응답 dict 확장 `{eager_refresh_today: int, by_prefix: {...}}` — UI breakdown 표시 (사이클 100+ 신규 카드)

---

## D. KIS API 만으로 stock_master 완성 청사진

### D-1. 흐름 (옵션 D-A — 사용자 의도 정합)

```
Step 1: market_cap (FHPST01740000) 페이징 호출 (tr_cont="M")
  - KOSPI (0001) + KOSDAQ (1001) 분리 호출 (사이클 96/98 답습)
  - 한도 추정 ~3,000+ ticker (사이클 99 영속 60 ticker 대비 ~50x)
  - 응답: ticker list (시가총액 정렬)
Step 2: 각 ticker → search_stock_info (CTPF1002R) 호출
  - 67 컬럼 응답 → stock_master upsert (사이클 81 bfdy_clpr 영속)
  - nxt_tradable = cptt_trad_tr_psbl_yn=='Y' AND nxt_tr_stop_yn!='Y' (영역 B nxt_downgrade 정합)
  - krx_halted = tr_stop_yn=='Y'
  - admin_item = admn_item_yn=='Y'
Step 3: 24h TTL + 5분 주기 점진 적재 (사이클 89 답습)
```

### D-2. Rate Limit 영향 (HIGH 의제)

KIS 한도: 모의 5건/초 / 실전 20건/초. 3,000 ticker × 1 호출 = **600초 (모의) / 150초 (실전)** 분당 적재 부담. 사이클 83/89 5분 주기 (300초) 영속 영역 대비 **2~5x 증가**.

**대응 옵션**:
- D-2-1: 24h TTL 유지 + 일일 1회 개장 전 (07:50) 일괄 적재 (사이클 89 `[universe_eager_refresh]` 영속 영역 확장)
- D-2-2: 점진 적재 (5분 주기당 ~60 ticker = 사이클 99 영속 영역) + 우선순위 분리 (보유/익일청산 HIGH)
- D-2-3: search_stock_info skip — market_cap 응답 (FHPST01740000 단독 응답 ~10 컬럼 영역) 만 활용 (stock_master 67 컬럼 일부만 적재, nxt_tradable 분리 호출 필요)

### D-3. Supabase 실측 영속 영역

stock_master 총 **171 종목** (KOSPI/KOSDAQ 전체 ~2,800 대비 6% 미만) — 마지막 갱신 2026-06-10 23:00 KST. 옵션 D-A 적재 후 **171 → ~2,800+ (~16x)** 영역 확장 예상.

---

## 사용자 결정 의제 (Q61~Q63)

**Q61 (HIGH) 사이클 분할 전략** — 사용자 *"A로 발주 진행"* 명시 영역 정합:
- A: 사이클 100 (영역 1+2 통합) + 사이클 101 (영역 3+4 통합 = 전체 종목 list + KIS API 완성)
- B: 사이클 100 (영역 1 단독 즉시) + 사이클 101+ (영역 2+3+4 통합 후속)
- C: 사이클 100 (영역 1+2+3+4 통합 단일 사이클, HIGH 위험)
- D: 사이클 100 (영역 1+2) + 사이클 101 (영역 3) + 사이클 102 (영역 4)

**team-leader 권고 = A** (영역 1+2 통합 HIGH 응급 영역 + 영역 3+4 신규 청사진 영역 분리).

**Q62 (HIGH) domain-expert 자문 영역**:
- A: 영역 2 (주문 발주 시장 분기) 영역만 자문 의무
- B: 영역 2 + 영역 3+4 (전체 종목 영역 매수 후보 풀 영향) 통합 자문
- C: 영역 2+3+4 통합 자문 (HIGH 통합)

**team-leader 권고 = B** (사이클 100 영역 2 + 사이클 101 영역 3+4 각각 분리 자문 — 사이클 64/65/66/67 패턴 답습).

**Q63 (MEDIUM) KIS MCP 재검증 우선순위**:
- A: 영역 3 (전체 종목 list API) + 영역 4 (CTPF1604R) 동시 재검증 (사이클 81/91/94/96/97/98 답습)
- B: 영역 3 단독 우선 (전체 종목 list 영역 확정 후 영역 4 진행)

**team-leader 권고 = A** (이미 본 진단에서 정본 코드 검증 완료 = 의제 종결 가능).

**Q64 (HIGH 신규 의제) D-2 Rate Limit 대응 옵션**:
- D-2-1: 일일 1회 일괄 적재 (07:50 개장 전, 사이클 89 영역 확장)
- D-2-2: 점진 적재 (5분 주기 60 ticker, 사이클 99 영속 영역)
- D-2-3: market_cap 응답 단독 활용 (search_stock_info 분리 호출)

**Q65 (MEDIUM 신규 의제) 영역 C 시정 즉시성**:
- C-1: db/stock_master.py L185 grep 3 prefix OR 1줄 시정 (코드 변경 1줄, 영역 1 단독)
- C-2: API breakdown 확장 (사이클 100+ 별개 카드)

---

## 산출물

- 진단 보고: `_workspace/cycle100_phase1_diagnosis.md` (본 파일)
- 영향 영역 (Phase 2+ 시정 예상): `src/db/stock_master.py:185` (C-1) / `src/engine/scanner.py:1575~1700` (D-1 fetch_top_500_universe 영역 확장) / `frontend/src/pages/StockMaster.tsx:543` (UI 텍스트 영역 검토)
- 정본 KIS API 영역 확정: `market_cap` (FHPST01740000) + `search_info` (CTPF1604R) + `search_stock_info` (CTPF1002R)
- Supabase READ-ONLY 실측 영역: stock_master 171 종목 + 7일 prefix 발화 (244+230+140 영속)

**Phase 2 진행 가이드**: 사용자 Q61~Q65 결정 후 backend-dev/frontend-dev 영역 분배 (자세히는 TDD 사이클 100+ Red 명세 분해).
