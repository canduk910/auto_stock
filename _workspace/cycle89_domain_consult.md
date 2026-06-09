# 사이클 89 도메인 자문 — stock_master 적재 500+ 종목 확장 (universe eager refresh)

**의뢰**: team-leader (사이클 89 Phase 2)
**자문 일시**: 2026-06-09 (화) KST
**위급도**: **HIGH** (작전주 차단/저거래량 회피/사이클 31·32·65·81 영속 매트릭스 영향)
**선행**: `_workspace/cycle89_phase1_diagnosis.md` (Q19~Q23 사용자 결정 채택)
**채택 결정**: Q19=B(상위 500) / Q20=D(개장 전 1회 + 사이클 83 5분 결합) / Q21=A(`volume_rank`) / Q22=A(90일) / Q23=A(전략별 독립 필터링)
**자문 범위**: A1~A6 (HIGH 4 + MEDIUM 2)
**코드 변경**: 0 (자문 단독)

---

## 1. 질문 요약

사이클 81 이후 잔존 silent 결함 = `stock_master` 운영 적재 52건 한정 → 후보 풀 ~90% 가 `bfdy_clpr <= 0` graceful 통과. 사이클 83 5분 주기 eager refresh = candidates=12 영역만 흡수. **500+ universe 사전 적재 = scanner 가격/거래대금 필터 정확도 회복 + 6 전략 후보 풀 확장 = 매수 진입 hot path 직접 영향**. domain-expert HIGH 자문 의무 — 작전주 / 저거래량 / 액면분할 / IPO 신규 진입 / WS 41 한도 / Rate Limit 영역 평가.

---

## 2. 트레이더 시각 (전체 의제 공통 배경)

### 시장 가설

- **거래대금 = 작전주의 1차 시그널**: 시가총액 작아도 거래대금 폭주 (1억~5억) = 작전 가능성. 거래대금 하루 10억 이상 = 정상 매매 영역. 거래대금 100억+ = 메이저 (사이클 65 디폴트 권장값 1억/5억/10억 영속).
- **거래량 단독 = 작전 위험 직접 노출**: 회전율 100%+ 종목 = 시총 ÷ 거래대금 비율 깨짐 = 작전 일순간 폭주. 거래량 *단독* 기준 = 위험.
- **시가총액 = 안정성**: 1,000억 이상 = donchian/VCP 기준 (영속). 500억~1,000억 = 중소형주 영역 (BFB). 100억 미만 = 작전주 영역.
- **등락률 단독 = 모멘텀 시그널이나 작전 함정**: ±15%+ 종목 = scanner.fetch_rising_stocks 영역 (영속). ±30% 상한가/하한가 = 모멘텀 / 상한가 전략 영역.

### 실전 사례

- **사이클 65 trade_amount_filter 영속**: 거래대금 임계 디폴트 0 = 비활성, 운영자 1억/5억/10억 권장값 마커. 사이클 89 500 universe 확장 = **거래대금 임계 자동 디폴트 채택 위험** (운영자가 운영 중 미설정 시 사이클 65 효과 폐기 회귀).
- **사이클 81 SK스퀘어 (402340)**: 1,122,340원 고가 종목 = 사이클 64 price_filter_max=500,000원 2배 초과 = R6 silent_skip 270건/일 폭주. stock_master 미적재 → bfdy_clpr=0 graceful 통과 → 가격필터 무용. **500 universe 적재 = 1,122,340원 정상 차단 회복**.
- **사이클 32 R4 universe guard**: stale>5 + today_volume<10,000 = 자동 제외. 500 universe 확장 = stale 평가 영역 확장 = guard 정확도 상승. 보유/익일청산 절대 보호 영속.

### 위험 시나리오

- **R-1 (HIGH)**: 500 universe 적재 시 KIS CTPF1002R 50ms sleep × 500 = 25초 백그라운드 직렬. 사이클 83 패턴 답습 (백그라운드 task lifecycle) 의무.
- **R-2 (HIGH)**: 6 전략 후보 풀 폭증 → 사이클 31 R6 silent_skip 폭주 재현 위험. 디폴트 trade_amount 임계 0 = scanner 필터 미작동 = SK스퀘어 류 추가 진입.
- **R-3 (MEDIUM)**: WebSocket 41 한도 (사이클 32 R4 영속) — 500 universe 중 실제 구독 = 후보 풀 필터링 후 ~30~50건 = **한도 영향 0** (보유 HIGH bypass 영속).
- **R-4 (HIGH)**: ETF/리츠/우선주/SPAC = momentum (상한가) / VB (변동성) 부적합. ETF 단가/거래대금 패턴 = 일반주 다름 → 회귀 위험.
- **R-5 (MEDIUM)**: KOSPI/KOSDAQ 통합 vs 분리 정렬 — 코스닥 변동성 비중 (momentum/VCP/BFB) 보존 의무.

---

## 3. 자문 권고 (A1~A6 세부)

### A1 — 500 기준 선정 (HIGH) — Q19-1 답변

**권고**: **거래대금 (전일 기준) 단독 정렬 = 1순위, 등락률 보조 dedupe = 2순위**.

#### 근거

| 기준 | 6 전략 적합성 | 작전주 차단 | 권고 |
|------|--------------|------------|------|
| **거래대금 (전일)** | 6 전략 모두 후보 풀 적합 (momentum 상한가 / VB 변동성 / LTV 꼬리 / donchian 채널 / BFB 깃발 / VCP 수렴) | **HIGH** (사이클 65 영속) | **1순위 (전일 거래대금 상위 500)** |
| 거래량 (절대) | momentum/VB/LTV 적합, donchian/VCP 부적합 (저거래 우량주 회피) | LOW (회전율 깨짐 시 작전 직접) | **단독 비채택** (보조 검토만) |
| 등락률 (±15%+) | scanner.fetch_rising_stocks 영속 영역 = 분리 hook | MEDIUM | **2순위 dedupe** (거래대금 500 + 등락률 ±15%+ 합집합) |
| 시가총액 | donchian (1,000억+) / BFB (500억+) / VCP (1,000억+) 적합 | MEDIUM | **3순위 검토** (사이클 90+ 정밀화 영역) |

#### 정량 권고

- **거래대금 전일 정렬 상위 500** (KIS `volume_rank` 응답 = 거래량순위, 단 응답 정렬 = 거래량 — **사이클 89 추가 정렬 의무**: 응답 후 `trade_amount = prdy_vol × (stck_prpr - prdy_vrss)` 재정렬 = 사이클 48 BFB 패턴 답습).
- **상위 500 = KRX ~2,400 종목 중 21%** = 일일 거래대금 ~10억 이상 영역 = 작전주/저거래량 자동 차단.
- **등락률 dedupe**: scanner.fetch_rising_stocks (±15%+) 와 거래대금 500 의 합집합. dedupe 결과 = 500~700 영역 예상 (3월 KRX 통계 = 등락률 15%+ ~50~100건/일, 거래대금 500 과 ~30~50% 중복).

#### 회피 시나리오

- **거래대금 5일 평균 채택 비추**: 액면분할/IPO/거래정지 회복 종목 = 5일 평균 왜곡 → 후보 풀 누락 위험. **전일 단독** = 일일 시장 변동 자연 반영.

---

### A2 — KOSPI/KOSDAQ 분리 dedupe + ETF 제외 (HIGH) — Q21-1 답변

**권고**: **KOSPI 250 + KOSDAQ 250 분리 정렬 = 1순위. ETF/리츠/우선주/SPAC 자동 제외 의무**.

#### 근거

| 분리 방식 | 6 전략 효과 | 권고 |
|----------|------------|------|
| **KOSPI 250 + KOSDAQ 250 분리** | momentum (상한가 KOSDAQ 비중) / VCP (코스닥 변동성) / BFB (깃발 KOSDAQ) 균형 | **권고** |
| 통합 500 (거래대금 정렬) | KOSPI 대형주 편중 (시총 1조+ 25~30 종목 잠식) = 코스닥 변동성 비중 ~10% 감소 | 비추 |
| 전체 500 ETF 제외 | momentum/VB/VCP 코스닥 변동성 영역 보존 | 결합 영속 의무 |

#### KOSPI/KOSDAQ 분리 정량 근거

- **KIS `volume_rank` (FHPST01710000) `mrkt_div_cls_code` 인자**: `0` (전체) / `1` (KOSPI) / `2` (KOSDAQ) — **2회 호출** (KOSPI 250 + KOSDAQ 250 분리). dedupe 불필요 (시장 분리).
- **거래대금 비대칭 보정**: KOSPI 거래대금 상위 100 = ~5,000억+ / KOSDAQ 거래대금 상위 100 = ~500억+ = 10배 차이. 통합 정렬 시 KOSDAQ 상위 ~50건만 통과 = 코스닥 변동성 영역 누락.

#### ETF/리츠/우선주/SPAC 제외 의무

- **ETF (KODEX/TIGER/RISE 등)**: momentum 상한가 부적합 (운용사 운영 NAV 추적), VB 변동성 부적합 (지수 추적 → K 값 의미 폐기), BFB/VCP 패턴 분석 무의미. **6 전략 전부 부적합 → 제외 의무**.
- **리츠 (~50 종목 KOSPI 상장)**: 부동산 신탁 패턴 = momentum/VB/VCP 무의미. 등락률 일평균 ±1% 영역. **제외 의무**.
- **우선주 (~150 종목)**: 보통주 대비 거래량 1/10 이하 = donchian/VCP 부적합. momentum 상한가 가능하나 거래 부족으로 매수 불가 빈번. **제외 권고** (운영자 토글 영역 검토).
- **SPAC (~50 종목)**: 합병 직전 폭주 패턴 = momentum 일부 적합하나 합병 후 즉시 정리 → 정상 종목 아님. **제외 권고**.

#### KIS API 종목 분류 키 (CTPF1002R 영속)

- `stock_master.raw.scts_mket_cls_code` (`Y`=KOSPI / `N`=KOSDAQ): 사이클 81 영속 영역.
- `stock_master.raw.std_pdno` (12자리): 처음 2자리 = 시장 구분 (`KR`=주식 / `ETF`/`REITS` 분류 가능 영역 → KIS MCP 검색 의무, 후속 backend-dev Green 영역).
- **사이클 89 도입 의무**: `_universe_filter_securities_only(rows)` 헬퍼 신규 — `lstn_stcn` (상장주식수) `prdt_type_cd` 키 활용 (KIS MCP 검색 의무).

---

### A3 — 전략별 stock_master raw 활용 범위 (HIGH) — Q23-1 답변

**권고**: **각 전략 `prepare()` 영역 독립 필터링 (Q23 옵션 A 영속) + 공통 필터 헬퍼는 사이클 91+ (3회 반복 후 추상화)**.

#### 전략별 stock_master raw 활용 매트릭스

| 전략 | 공통 필터 (stock_master raw) | 고유 필터 (KIS 별도 조회) |
|------|----------------------------|--------------------------|
| **momentum** | `bfdy_clpr` (사이클 81), `acml_tr_pbmn` (사이클 65), `lstn_stcn` 시총 산출 | 상한가 조건검색 (`condition_id` 영속, KIS condition_id 등록 영역) |
| **VB** | `bfdy_clpr`, `acml_tr_pbmn`, 시총 | 일봉 (전일 high/low) — `kis_get_quote(FHKST01010100)` 영속 |
| **LTV** | `bfdy_clpr`, `acml_tr_pbmn`, 시총 | 일봉 (전일 꼬리) + 연속 상한가 (FHPST01710000) |
| **donchian** | `bfdy_clpr`, `lstn_stcn` 시총 ≥ 1,000억 | 60일 일봉 (donchian 채널 + EMA + ATR) |
| **BFB** | `bfdy_clpr`, 시총 ≥ 500억, `acml_tr_pbmn` ≥ 20억 | 30일 일봉 (폴 + 플래그 검출) |
| **VCP** | `bfdy_clpr`, 시총 ≥ 1,000억 | 220일 일봉 (베이스 + EMA 정배열 + pullback 수축) |

#### 정량 권고

- **공통 필터 (4 항목)**: `bfdy_clpr (사이클 81)` + `acml_tr_pbmn (사이클 65)` + `lstn_stcn × stck_prpr` (시총 산출) + `scts_mket_cls_code` (KOSPI/KOSDAQ 분리). 6 전략 모두 stock_master raw 활용 가능 = **사이클 89 적재 효과 직접 입증 영역**.
- **고유 필터 (전략별 1~2 항목)**: 일봉 / 조건검색 / 폴플래그 패턴 = stock_master raw 만으로 불충분. **KIS 일봉 API 영속 영역** (`kis_get_quote(FHKST01010100)` 호출 영역 변경 0 = 사이클 89 영향 없음).
- **사이클 89 hot path 영역**: scanner 단계 (subscribe_filtered_stocks 진입) 가격필터 / 거래대금 필터 = **공통 필터 100% 적용 = stock_master 직접 활용**. 전략별 `prepare()` 영역 = 고유 필터 100% (사이클 89 변경 0).

#### 회피 시나리오

- **공용 헬퍼 옵션 B 비추**: 사이클 67 답습 패턴 = *3회 반복 후 추상화* 규칙 — 사이클 89 = 1회차 (사이클 65 영역 + 사이클 81 영역) → **사이클 91+ 도입 검토** (3회차 충족 후). 추상화 조기 도입 = 전략 독립성 침해 위험 (사이클 67 영속 의무).

---

### A4 — 매수 후보 풀 폭증 위험 평가 (HIGH) — 신규

**권고**: **scanner 단계 필터링 영역 영속 (사이클 64/65/81) = 후보 풀 폭증 위험 영구 차단 보장. WS 41 한도 영향 0**.

#### 후보 풀 흐름 분석

```
500 universe (사이클 89 적재) — stock_master 만 (구독 0)
  ↓ filter
  scanner.subscribe_filtered_stocks 진입점:
    → fetch_rising_stocks (±15%+) 합집합 ~50~100건
    → ticker_market_info 풀 (시총/거래대금) 보강
    → _apply_price_filter (사이클 64): 임계 외 ticker 제외
    → _apply_trade_amount_filter (사이클 65): 거래대금 미달 ticker 제외
    → protected_tickers (보유/익일청산) 절대 보호
  ↓
  실제 WS 구독 후보 풀 ~30~50건 (사이클 32 R4 영속 + 41 한도 영속)
```

#### 정량 매트릭스

| 영역 | 사이클 89 *전* (52 universe) | 사이클 89 *후* (500 universe) | 위험 평가 |
|------|------------------------------|------------------------------|----------|
| `stock_master` 적재 | 52건 | 500건 (10배) | 안전 (R-1 R-2 가드) |
| `subscribe_filtered_stocks` 후보 풀 | ~30~50건 | ~30~50건 (불변, 필터링 효과 동일) | **영향 0** |
| 실제 WS 구독 | ~30~40건 (HIGH 보유 ~5~10 + LOW 후보 ~20~30) | ~30~40건 (불변) | **영향 0** |
| 사이클 31 R6 silent_skip 폭주 (SK스퀘어 패턴) | 270건/일 | **0~10건/일** (가격필터 정상 발화) | **회복 (사이클 81 의도)** |
| 사이클 32 R4 universe guard 보호 | 영속 | 영속 (보유/익일청산 절대 보호) | 영속 영구 |
| KIS Rate Limit (Semaphore 20/s) | 영속 | 영속 (50ms sleep × 500 = 25초 백그라운드) | 안전 영역 |
| 6 전략 동시 매수 시도 | 영속 (cash_usage_ratio 영역) | 영속 (필터링 후 풀 동일) | **영향 0** |

#### 사이클 31 R6 영속 보장 검증

- **사이클 81 시정 (bfdy_clpr 키)**: stock_master 적재 시 가격필터 정상 발화 → SK스퀘어 류 자연 차단.
- **사이클 89 적재 효과**: 500 universe 적재 = bfdy_clpr 보유 비율 ~95%+ (24h TTL 안정화 후) → **가격필터 정확도 회복 100%**.
- **R6 (`current_price > total_investment`)**: 영속 안전망 영역 (사이클 31 영속) — 운영자 가격필터 임계 미설정 시 단독 안전망 보존.
- **trigger 빈도 정량 추정**: 270건/일 → 0~10건/일 (가격필터 정상화로 R6 우회 시나리오 자연 차단).

#### 6 전략 동시 매수 + KIS Rate Limit

- **자금 분배 (cash_usage_ratio)**: 영속 영역 (사이클 38) — 전략 비중 × cash_usage_ratio × position_ratio 영속.
- **KIS REST 호출 빈도**: scanner.fetch_rising_stocks (5분 주기) + ticker_market_info 보강 (사이클 65 영속) + 일봉 (전략 prepare 영역, 영속) = 사이클 89 변경 0.
- **사이클 89 추가 부담**: `volume_rank` 2회 호출 (KOSPI + KOSDAQ) + CTPF1002R 500 호출 (24h TTL 영속 = 2 사이클째부터 0건). **일일 추가 부담 = ~502 호출 (개장 전 1회)** = 안전 영역.

---

### A5 — 사이클 88 G-REJECT AST 가드 영속 보장 (MEDIUM)

**권고**: **G-REJECT-1/2/3 영속 영구 보장 — 사이클 89 변경 영역 0**.

#### G-REJECT-1 (4중 안전망 영속) — 영향 0

- 4중 안전망 = F1 재연결 + `_scan_loop` 5분 + K stale watcher 120s + `_resubscribe_stale_priority` 5분 = WebSocket 구독 영역.
- 사이클 89 = stock_master 적재 영역 (DB CRUD) = **WebSocket 구독 영역과 분리** = 영향 0.

#### G-REJECT-2 (종목별 stale 영속) — 영향 0

- `ticker_last_tick` 추적 = scanner 모듈 전역 dict = WebSocket 구독 후 갱신 영역.
- 사이클 89 적재 = stock_master DB upsert 영역 = `ticker_last_tick` 영향 0.
- **500 universe 중 실제 구독 ~30~50건** → `ticker_last_tick` 추적 규모 동일 = 영향 0.

#### G-REJECT-3 (4 dict 분리 영속) — 영향 0

- 4 dict = scanner.ticker_names / ticker_prices / ticker_prev_close / ticker_market_info.
- 사이클 89 = 500 universe 중 ticker_market_info 풀 보강 영역 (사이클 65 영속) = 영향 0.
- **신규 dict 도입 비추**: 사이클 89 = stock_master 영역만 (DB) = 모듈 전역 dict 추가 0.

---

### A6 — 운영 가시화 영역 (MEDIUM)

**권고**: **2 신규 prefix 도입 의무 (사이클 74 collector 패턴 답습)**.

#### 권고 신규 prefix

1. **`[stock_master_bulk_refresh] universe=500 kospi=250 kosdaq=250 securities=480 etf_excluded=15 fetched=N elapsed_ms=M`** — 개장 전 1회 적재 시 1행 INFO.
   - `securities` = ETF/리츠/SPAC 제외 후 보통주 카운트.
   - `etf_excluded` = 제외 카운트 (A2 권고 영속).
   - `fetched` = KIS CTPF1002R 호출 카운트 (24h TTL skip 제외).

2. **`[stock_master_universe_summary] total=500 fresh=N stale=M held=K next_day=L`** — 5분 주기 1행 (사이클 74 collector 패턴 답습).
   - `fresh` = 24h TTL 유효.
   - `stale` = TTL 만료 + 갱신 대기.
   - `held` / `next_day` = 보유 / 익일청산 카운트 (사이클 32 R4 보호 영역).

#### G-AST 영속 가드 (사이클 78/79 답습)

- **G-AST1 (사이클 78 답습)**: `record_*` 정의 모듈의 대응 `flush_*` 호출 사이트 ≥1건 정적 검증 — 사이클 89 신규 `record_stock_master_summary` / `flush_stock_master_summary_collector` 도입 시 자동 가드.
- **G-AST2 (사이클 79 답습)**: 신규 task attribute `_universe_eager_refresh_task` 도입 시 `scheduler.py::stop()` task_attrs 튜플 + `run_daily()` finally 블록 양쪽 동행 추가 의무.

---

## 4. 현 코드와의 정합성

### 충돌 항목 없음

- **사이클 38 명문화**: `tradable_boards` 매수 진입 전용 영속 — 사이클 89 = scanner 단계 영역 = 매수 진입만 영향. 매도/익일청산/15:20 강제청산 영향 0.
- **사이클 31 R6 영속**: 가격필터 정상화로 R6 trigger 빈도 270 → 0~10건/일 = R6 안전망 단독 의존 회복 (사이클 64 의도).
- **사이클 32 R4 universe guard**: 보유/익일청산 절대 보호 영속 — 500 universe 적재 = R4 평가 영역 확장 (positives only).
- **사이클 64 Q1 옵션 D**: `_collect_protected_tickers_for_scanner` 3중 안전망 영속 — 500 universe 적재해도 보유 ticker 가격필터 graceful 통과 영속.
- **사이클 65/81 영속**: trade_amount_filter (사이클 65) + price_filter bfdy_clpr (사이클 81) 정확도 회복 직접 영역.
- **사이클 67 stale_manager 분해**: 영향 0 (영역 분리).
- **사이클 78 flush 호출 사이트 영속**: G-AST1 패턴 답습 의무 (A6 권고).
- **사이클 79 cancel 영구 가드**: G-AST2 패턴 답습 의무 (A6 권고).
- **사이클 83 scan_pool eager refresh**: candidates=12 영역 영속 + 500 universe 영역 = 영역 분리 (24h TTL 자연 자연 흡수).
- **사이클 84 history trigger**: 90일 retention 영속 + 500 universe = 45,000 row (5%, 안전) — Q22 채택 영속.
- **사이클 88 G-REJECT-1/2/3**: 영향 0 (A5 분석 영속).

---

## 5. 위험 영역 매트릭스

| 등급 | 영역 | 영향 | 시정 의무 |
|------|------|------|----------|
| HIGH | 작전주 자동 차단 | 거래대금 정렬 정확 = 작전주 자동 제외 | A1 권고 영속 |
| HIGH | ETF/리츠/우선주/SPAC 제외 | 6 전략 부적합 종목 자동 제외 | A2 권고 영속 |
| HIGH | KIS Rate Limit (Semaphore 20/s) | 50ms sleep × 500 = 25초 백그라운드 안전 | 사이클 83 답습 |
| HIGH | 후보 풀 폭증 영구 차단 | scanner 필터링 영속으로 ~30~50건 영속 | A4 분석 영속 |
| HIGH | 사이클 31 R6 영속 + trigger 빈도 회복 | 270 → 0~10건/일 = 사이클 64 의도 회복 | 영속 영구 |
| MEDIUM | KOSPI/KOSDAQ 비대칭 (코스닥 변동성 보존) | A2 분리 정렬 = 250 + 250 권고 | A2 분리 의무 |
| MEDIUM | stock_master_history 부담 (45,000 row) | 90일 영속 + 500 universe = 5% (안전) | Q22 채택 영속 |
| MEDIUM | 백그라운드 task lifecycle (사이클 79 답습) | 신규 task attribute 도입 시 cancel 영구 가드 | A6 G-AST2 의무 |
| MEDIUM | 운영 가시화 (2 신규 prefix) | `[stock_master_bulk_refresh]` + `[universe_summary]` | A6 도입 의무 |
| LOW | KST 영속 (사이클 68) | `src/db/_kst.py` 헬퍼 영속 | 영속 영구 |
| LOW | AST 영속 (사이클 79/88) | 신규 task / 신규 collector 자동 가드 | A6 영속 |
| LOW | KIS MCP 영속 | `volume_rank` (FHPST01710000) 기존 호출 영역 | 영속 |

---

## 6. 시정 영역 명세 (backend-dev 인계)

### 신규 영역 (사이클 89 권고)

1. **`src/engine/scanner.py::fetch_top_500_universe()` 신규 함수** (~50L):
   - KIS `volume_rank` (FHPST01710000) 2회 호출 (`mrkt_div_cls_code=1` KOSPI + `mrkt_div_cls_code=2` KOSDAQ) 각 250건.
   - `trade_amount = prdy_vol × (stck_prpr - prdy_vrss)` 재정렬 (사이클 48 BFB 답습).
   - ETF/리츠/SPAC/우선주 제외 (A2 권고 — `_universe_filter_securities_only(rows)` 신규 헬퍼).
   - 응답 list 반환 (최대 500건).

2. **`src/engine/scheduler.py::_universe_eager_refresh_loop` 신규 task** (~60L):
   - 개장 전 1회 (08:30~08:50 영역, `_boot` 직후) + 사이클 83 5분 주기 결합.
   - `fetch_top_500_universe()` 호출 + 500 ticker × CTPF1002R + `stock_master.upsert_one()` (24h TTL 자연 skip).
   - 50ms sleep × 500 = 25초 백그라운드 직렬.
   - lifecycle (`connect/disconnect`) hook = 사이클 79 답습 의무.

3. **`src/engine/stock_master_metrics.py` 신규 모듈** (~50L, 사이클 74/78 답습):
   - `record_stock_master_summary(stats)` + `flush_stock_master_summary_collector()` (5분 윈도우 1행 emit).
   - `[stock_master_universe_summary]` prefix.
   - `_api_recovered_collector_loop` (사이클 76/78 영속) 본체에 flush 호출 추가 (사이클 78 답습).

4. **AST 영구 가드**:
   - G-AST1 (사이클 78 답습): record_* 정의 모듈의 대응 flush_* 호출 사이트 ≥1건.
   - G-AST2 (사이클 79 답습): `_universe_eager_refresh_task` cancel 목록 영속.

### 변경 0 영역 (영속 의무)

- `src/engine/risk.py` (사이클 64 영속 영역)
- `src/engine/order_engine.py` (체결통보 영역, 사이클 55 R-1 영속)
- `src/engine/stale_*.py` (사이클 67 영속)
- 6 전략 `prepare()` (Q23 옵션 A 영속 — 전략 독립성)
- 사이클 83 `_scan_pool_eager_refresh_task` (영역 분리 영속)

---

## 7. 회귀 가드 매트릭스 권고

### HIGH 5 (작전주/Q19/Q21/Q23/Rate Limit)

| ID | 가드 영역 | 검증 방법 |
|----|----------|----------|
| H-1 | 거래대금 정렬 정확 (A1) | `volume_rank` mock 응답 → `trade_amount` 재정렬 결과 = 거래대금 DESC 순 |
| H-2 | ETF/리츠/SPAC 자동 제외 (A2) | mock 응답 ETF 5건 + 보통주 495건 → 결과 = 495건 (ETF 0건) |
| H-3 | KOSPI/KOSDAQ 분리 정확 (A2) | `mrkt_div_cls_code=1` 호출 → KOSPI 250건 + `=2` → KOSDAQ 250건 |
| H-4 | KIS Rate Limit (50ms sleep) | 500 ticker upsert → KIS 호출 간격 ≥45ms (50ms ±10% 마진) |
| H-5 | 후보 풀 폭증 영구 차단 (A4) | 500 universe 적재 후 `subscribe_filtered_stocks` 결과 ≤ 50건 영속 |

### MEDIUM 7 (lifecycle/가시화/통합)

| ID | 가드 영역 | 검증 방법 |
|----|----------|----------|
| M-1 | 백그라운드 task lifecycle (사이클 79 답습) | `stop()` 시점 `_universe_eager_refresh_task` cancel 발화 |
| M-2 | 24h TTL fresh skip 영속 | 24h 내 호출 → `_eager_refresh_skipped` 카운터 증가 |
| M-3 | 사이클 32 R4 보호 영속 | 500 universe 중 보유/익일청산 ticker 자연 보호 |
| M-4 | 사이클 64 protected_tickers 영속 | 보유 ticker bfdy_clpr 갱신해도 가격필터 graceful 통과 |
| M-5 | 사이클 65 trade_amount_filter 영속 | 500 universe 적재 후 trade_amount 임계 정확 작동 |
| M-6 | 사이클 81 bfdy_clpr 키 영속 | 500 universe 적재 후 `_apply_price_filter` 정확 발화 |
| M-7 | 운영 가시화 (`[stock_master_bulk_refresh]` 1행) | 개장 전 1회 적재 시 1행 emit |

### LOW 5 (AST/KST/통합)

| ID | 가드 영역 | 검증 방법 |
|----|----------|----------|
| L-1 | G-AST1 영구 가드 (사이클 78 답습) | `record_*` ↔ `flush_*` 호출 사이트 ≥1건 |
| L-2 | G-AST2 영구 가드 (사이클 79 답습) | 신규 task attribute = stop task_attrs 튜플 차집합 ∅ |
| L-3 | KST 영속 (사이클 68) | `_kst.py` 헬퍼 영속 사용 |
| L-4 | 사이클 84 history trigger 영속 | 500 ticker upsert 시 history INSERT/UPDATE 분리 영속 |
| L-5 | 사이클 88 G-REJECT-1/2/3 영속 | 사이클 89 변경 영역 0 (영향 0) |

**합계**: HIGH 5 + MEDIUM 7 + LOW 5 = **17 회귀 가드 케이스** (Phase 1 추정 17 일치).

---

## 8. 반례 / 한계

### 반례 1 — 코스닥 거래대금 폭주 (MEDIUM)

- 시나리오: 코스닥 작전주 1종목 거래대금 1,000억+ (KOSDAQ 평균 ~50억) → 거래대금 상위 1위 진입.
- 영향: **사이클 65 trade_amount_filter (디폴트 0)** 우회 (운영자 임계 미설정 시) → SK스퀘어 패턴 재현 (사이클 81).
- **회피**: 운영자 trade_amount 임계 1억~10억 설정 권장 (사이클 65 UI 권장값 마커 영속).

### 반례 2 — IPO 신규 종목 첫날 진입 (LOW)

- 시나리오: 신규 상장 첫날 거래대금 폭주 → 500 universe 진입. `bfdy_clpr=0` (전일 종가 없음) → 가격필터 graceful 통과.
- 영향: 가격필터 단독 안전망 우회. R6 (`current_price > total_investment`) 안전망 단독 의존.
- **회피**: 사이클 31 R6 영속 영역 (사이클 81 의도 보존) — 신규상장 영구 차단 방지 = 정상 동작.

### 한계 — 사용자 trade_amount 임계 미설정

- **사이클 65 디폴트 = 0 (비활성)**: 운영자가 운영 중 임계 미설정 시 사이클 89 효과 = 작전주 차단 = 사이클 65 영역만 영속.
- **운영자 결정 영역**: UI Settings 권장값 마커 (1억/5억/10억) 영속 + 사이클 89 적재 효과로 정확도 회복 — **운영자 임계 1억 이상 설정 권장**.

### 한계 — KOSPI 통합 vs 분리

- KOSPI 250 + KOSDAQ 250 분리 = 코스닥 변동성 보존 (A2 권고).
- **단점**: KOSPI 상위 251~300 종목 (시총 ~3,000억) 누락 가능 → donchian/VCP 영역 부분 손실. **사이클 90+ 동적 분할 검토** (KOSPI/KOSDAQ 비율 변동 시 자동 조정, 사이클 89 범위 외).

---

## 9. 후속 검증 권고 (tdd-engineer / tester)

### tdd-engineer

- Red 단계 17 케이스 (HIGH 5 + MEDIUM 7 + LOW 5) 신설.
- **G-AST1 (사이클 78 답습) + G-AST2 (사이클 79 답습) 반드시 신설** — 미래 신규 collector / task 추가 시 누락 영구 차단.
- **H-2 (ETF 자동 제외) HIGH 우선**: ETF 5건 + 보통주 495건 mock fixture 신설 의무.
- 백그라운드 task lifecycle 검증 (`stop()` 시점 cancel) = 사이클 79 패턴 직접 답습.

### tester

- **D+1 (수) 09:00~10:00 1h verify**:
  - 개장 전 1회 적재 `[stock_master_bulk_refresh] universe=500 kospi=250 kosdaq=250 securities=~480 etf_excluded=~15 fetched=N elapsed_ms=M` 1행 emit 확인.
  - `stock_master` 총 row 52 → 500+ 확인.
  - SK스퀘어 (402340) `bfdy_clpr` valid 확인 (500 universe 진입 검증).
  - `[stock_master_universe_summary]` 5분 주기 emit ≥10건 (10시까지).

- **D+5 (월) 1주 운영 측정**:
  - `[risk_silent_skip]` (R6) trigger 빈도 변화 (270 → 0~10건/일).
  - `[price_filter_scanner_skip]` 정상 발화 빈도 (사이클 64/65/81 본래 의도 회복 검증).
  - `subscribe_filtered_stocks` 후보 풀 카운트 변화 (~30~50건 영속 검증).
  - KIS API 호출 dup_factor 변화 (사이클 76 영속, 영향 0 예상).
  - WS 41 한도 영향 0 검증 (사이클 32 R4 영속).

- **D+30 (1개월) 운영 회고**:
  - **반례 1 (코스닥 작전주) 실측**: 운영자 trade_amount 임계 설정 권장값 채택 비율 측정.
  - 작전주 차단 실효성 (270 → 0건/일 영속 검증).
  - 후보 풀 6 전략 균형 (momentum/VB/LTV/donchian/BFB/VCP 후보 분포).

---

## 10. 결론

**사이클 89 = 사이클 65/81 정확도 회복 + 사이클 64 의도 영구 보존 + 사이클 31 R6 영속 + 사이클 32 R4 영속 + 사이클 83 영역 결합**. domain-expert 자문 권고 영속 매트릭스 17 케이스 (HIGH 5 + MEDIUM 7 + LOW 5) 신설 의무. **6 전략 매매 hot path 영향 0** (scanner 단계 영역 한정, 매도/익일청산/손절 영향 0). **사이클 88 G-REJECT-1/2/3 영속 영구 보장** (영역 분리, 영향 0). **A1=거래대금 단독 + 등락률 dedupe / A2=KOSPI/KOSDAQ 250+250 분리 + ETF/리츠/SPAC 제외 / A3=Q23 옵션 A 영속 (전략 독립) / A4=후보 풀 폭증 영구 차단 (필터링 영속) / A5=영향 0 / A6=2 신규 prefix + G-AST 2 영속 가드**.

**Phase 2 명세 분해 (team-leader) 인계 = backend-dev Green 단계 진행 가능**.

---

**산출물**: `_workspace/cycle89_domain_consult.md` (본 문서)
**핵심 권고 한 줄**: A1 거래대금 정렬 + A2 KOSPI/KOSDAQ 250+250 분리 + ETF/리츠/SPAC 제외 + A3 전략 독립 필터링 영속 + A4 후보 풀 폭증 영구 차단 + A5 G-REJECT 영향 0 + A6 2 신규 prefix + G-AST 2 가드 = HIGH 5 + MEDIUM 7 + LOW 5 = 17 회귀 가드 의무.
