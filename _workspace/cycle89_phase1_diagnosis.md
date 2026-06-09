# 사이클 89 Phase 1 진단 — stock_master 적재 영역 500+ 종목 확장

작성: team-leader (트레이딩 데스크 감독자)
작성일: 2026-06-09 (KST)
위급도: **MEDIUM~HIGH** (매수 후보 풀 확장 = 매매 의사결정 직접 영향)
domain-expert 자문: **HIGH 의무** (작전주/저거래량 매수 위험 + 사이클 32 R4 / 65 / 81 영속 매트릭스 영향 평가)
refactor-expert 자문: MEDIUM (Q23 옵션 B 공용 헬퍼 검토 시)

코드 변경 0. READ-ONLY 진단.

---

## A. 현재 영속 상태 (Supabase 실측 2026-06-09 KST 15:11)

### A-1. stock_master 적재 현황

| 항목 | 실측 |
|------|------|
| total_master | **52건** (CLAUDE.md 발주 컨텍스트의 29건 추정 → 실측 52건. 사이클 84 history trigger 후 누적 효과 확인) |
| nxt_tradable_cnt | 24건 (46%) — NXT 거래 가능 |
| bfdy_clpr 보유 | 51건 (98%) — 사이클 81 prdy_clpr → bfdy_clpr 키 시정 영속 확인 |
| latest_refresh | 2026-06-09 06:11:33 KST (_boot eager + scan_pool 5분 누적) |
| oldest_refresh | 2026-05-12 23:57:36 (28일 stale, is_stale 자연 갱신 대기) |

### A-2. stock_master_history 부담 (사이클 84 trigger 영속)

| 항목 | 실측 |
|------|------|
| history_total | 26건 (90일 retention) |
| distinct_tickers | 26건 (1:1, 신규 진입 효과) |
| last_1d_cnt | 26건 (사이클 84 trigger 신규) |
| change_type | INSERT 23 + UPDATE 3 (TTL_REFRESH 분리 영속 = 사이클 84 Q7 영속) |

### A-3. 사이클 83 scan_pool eager refresh 운영 실측

`[scan_pool_eager_refresh] candidates=12 refreshed=0 skipped=12 elapsed_ms ~1,400ms` (5분 주기) — **candidates=12 정상 운영 + 24h TTL 영속으로 refreshed=0 자연 흡수**.

12 candidates × 5분 × 24h = **하루 ~3,456 호출 잠재력**이나 TTL fresh skip 으로 실제 KIS 호출 ~0건. 영역 안전.

---

## B. 적재 영역 source 분석 (Q19)

### B-1. KIS 종목 list API 검토

KIS MCP 검색 결과 = **전체 종목 일괄 list API 부재** (KIS 정책상 universe API 미공개).

대안:
- **`fetch_rising_stocks` (FHPST01700000) 등락률 순위** — scanner 가 이미 사용. raw 응답 ~200건/호출 (KIS 한도)
- **`volume_rank` 거래량순위** — `FHPST01710000` 권장 (도메인 자문 후 확정)
- **`hts_top_view` HTS조회상위20** — top 20 한정, universe 부적합
- **단일 종목 list 합집합** = 사이클 26 `KOSPI_200_TICKERS` + `KOSDAQ_150_TICKERS` 350 고정 universe (donchian_swing) 이미 영속

### B-2. KRX 전체 ≈ 2,400 종목 (코스피 ~950 + 코스닥 ~1,650 추정)

universe 정의 = 운영자 선택 영역 (Q19).

---

## C. KIS Rate Limit 안전성 (Q20/Q22)

| 적재 영역 | 종목 수 | 호출 시간 (sequential 50ms sleep + CTPF1002R Rate Limit 20/s 내) | 일 부담 |
|-----------|--------|----------------------------------------------------------------|---------|
| 현재 영속 | 52건 | ~3초 | ~52 KIS/day (24h TTL) |
| 옵션 B (상위 500) | 500건 | **~25초** (50ms × 500) | 500 KIS/day |
| 옵션 A (KRX 2,400) | 2,400건 | **~120초 = 2분** | 2,400 KIS/day |
| 옵션 C (5,000) | 5,000건 | ~250초 = 4분 10초 | 5,000 KIS/day |

**KIS CTPF1002R Rate Limit = 20/s** (메인 단일 Semaphore). 50ms sleep 단계적 호출은 안전 영역.

24h TTL 영속 (사이클 83 Q3=B 답습) = 일 1회 적재 + 자연 재갱신 패턴.

---

## D. stock_master_history 부담 평가 (Q22)

### D-1. 사이클 84 PostgreSQL trigger 동작

`stock_master` upsert → trigger 자동 INSERT `stock_master_history` (change_type = INSERT/UPDATE/TTL_REFRESH).

90일 retention = `WHERE changed_at < NOW() - INTERVAL '90 day'` DELETE 영속.

| 옵션 | 일 INSERT (영업일) | 90일 누적 | Supabase 무료 tier 500MB |
|------|--------------------|-----------|--------------------------|
| 옵션 A (현 52건) | ~52 | 4,680 | 안전 (0.5%) |
| 옵션 B (500) | ~500 | 45,000 | 안전 (5%) |
| 옵션 A 전체 (2,400) | ~2,400 | 216,000 | 25% (검토 필요) |
| 옵션 C (5,000) | ~5,000 | 450,000 | **50% (위험)** |

`TTL_REFRESH` 영역 (변동 없는 정기 갱신) 분리 영속 = 사이클 84 Q7 영속. UPDATE/INSERT 만 실제 변화.

---

## E. 영구 차단 가드 매트릭스 영향 평가

| 사이클 | 가드 영역 | 사이클 89 영향 | 영속 의무 |
|-------|----------|---------------|---------|
| 32 R4 | universe guard 보유/익일청산 절대 보호 | 500+ ticker universe = stale 폭증 → universe guard 자동 제외 빈도 증가 가능 | **영속 필수** |
| 38 | tradable_boards 매수 진입 전용 | scanner 단계 필터링 영역 = 매수 영역만 영향 | 영속 필수 |
| 65 | trade_amount_filter scanner 작전주 차단 | stock_master 확장 = trade_amount_filter 미적용 종목 폭증 → 임계 0 디폴트로 작전주 통과 위험 | **HIGH** |
| 81 | price_filter bfdy_clpr 키 + trade_amount 폴백 폐기 | stock_master 500+ 적재 = bfdy_clpr 보유 종목 확대 → price_filter 정확도 상승 | 영속 + 우호적 |
| 83 | scan_pool eager refresh 5분 주기 | candidates 12 → 500+ 폭증 시 elapsed_ms 1.4s → ~25s = **5분 윈도우 안전** | 영역 확장 검토 |
| 84 | history trigger + 90일 retention | 일 INSERT 폭증 (D-1 참조) | retention 30일 단축 (옵션 B) 검토 |
| 88 | (직전 사이클, AST/silent 가드) | 영역 무관 | 영속 |

---

## F. 사용자 결정 의제 (Q19~Q23)

### Q19 (HIGH) 적재 영역 (Universe 정의)
- **옵션 A** (위험): KRX 전체 ~2,400 종목 — stock_master_history 90일 216,000 row (25%) + 신규 silent 결함 영역 폭증 위험
- **옵션 B** (권장): **거래대금/거래량 상위 500 종목** (scanner `fetch_rising_stocks` + `volume_rank` 합집합) — 사이클 65 trade_amount 임계 + 사이클 81 price_filter 영속 가드와 일치
- **옵션 C** (보수): 6 전략별 condition + universe 합집합 (500~1,000 추정)
- **옵션 D** (혼합): A + B 동행 — 운영 부담 큼

### Q20 (HIGH) 적재 시점
- **옵션 A** (권장): 개장 *전* 1회 (08:30 boot 직후, **신규 task `_universe_eager_refresh_loop`** 사이클 51 boot_manager 답습) + 사이클 83 5분 주기 영속 결합
- 옵션 B: 5분 주기 분산만 (사이클 83 답습) — 개장 *후* 적재 = 09:00~09:25 작전주 차단 race
- 옵션 C: 24h TTL 자연 갱신만 (lazy) — 첫 진입 race 위험

### Q21 (MEDIUM) source 영역
- **옵션 A** (권장): KIS `volume_rank` (FHPST01710000 거래량순위) — 시장 KRX + KOSDAQ 분리 호출, 응답 ~200건씩 × 2~3회
- 옵션 B: 사이클 65 `fetch_rising_stocks` + `volume_rank` 합집합 dedupe
- 옵션 C: `KOSPI_200_TICKERS` + `KOSDAQ_150_TICKERS` 350 고정 universe 확장 (검토)

### Q22 (HIGH) stock_master_history 부담
- **옵션 A** (권장 + 검토): 90일 영속 + 옵션 B 500종목 = 45,000 row (5%, 안전)
- 옵션 B: 90일 → 30일 단축 (옵션 A 2,400+ 채택 시)
- 옵션 C: TTL_REFRESH 제외 (UPDATE/INSERT만 영속) — 사이클 84 명세 위반 위험 (refactor-expert 자문 의무)

### Q23 (HIGH) 전략별 필터링 영역
- **옵션 A** (권장): 각 전략 `prepare()` 영역에서 stock_master 조회 + 필터링 — 전략 독립성 보존
- 옵션 B: 공용 헬퍼 `stock_master.filter_for_strategy(strategy_id)` (사이클 67 답습) — 3회 반복 검증 후 추상화
- 옵션 C (현 영속): 조건검색 API + 후보 풀 + stock_master 는 raw 데이터 캐시만 = **사이클 89 변경 0 영역** (사용자 요구 미충족)

---

## G. 회귀 가드 매트릭스 추정 (옵션 B 채택 시)

| 등급 | 가드 영역 | 사이클 89 신규 케이스 |
|------|----------|---------------------|
| HIGH | KIS Rate Limit (Semaphore 20/s 영속) | 1 (`volume_rank` 호출 Rate Limit 가드) |
| HIGH | 24h TTL 영속 + 사이클 83 _scan_pool_eager_refresh 호환 | 1 (신규 task ↔ 사이클 83 task race 가드) |
| HIGH | 사이클 32 R4 universe guard 보유/익일청산 절대 보호 | 1 (500+ universe 확장 시 보호 영역 영속) |
| HIGH | 사이클 65/81 가격/거래대금 필터 정확도 영속 | 1 (확장 영역에서 필터 정확 작동) |
| HIGH | stock_master_history 90일 retention 영속 | 1 (45,000 row 부담 분기 검증) |
| MEDIUM | 적재 source 검증 (volume_rank 응답 schema) | 2 (KOSPI/KOSDAQ 분리 호출 + dedupe) |
| MEDIUM | 전략별 필터링 정합성 (Q23 옵션 A) | 6 (전략 6개 prepare 영역) |
| MEDIUM | 운영 가시화 (`[universe_eager_refresh_summary]` 신규 prefix) | 1 (사이클 78 답습) |
| LOW | KST 영속 (사이클 68) / AST 영속 / KIS MCP 영속 | 3 |

**합계 추정**: HIGH 5 + MEDIUM 9 + LOW 3 = **17 회귀 가드 케이스**

---

## H. 위급도 평가 + 자문 의무

- **위급도 = MEDIUM~HIGH** (매수 후보 풀 확장 = 매매 의사결정 영역 직접 영향)
- **domain-expert 자문 의무 = HIGH** (Q19 옵션 B/D 결정 + Q21 source + Q23 전략별 필터링 영역 = 작전주 / 저거래량 / 액면분할 / IPO 신규 진입 위험 평가 의무)
- **refactor-expert 자문 = MEDIUM** (Q23 옵션 B 공용 헬퍼 = 사이클 67 답습 패턴, 3회 반복 검증 후 추상화)

---

## I. 권고안 (사용자 결정 대기)

**team-leader 1차 권고**:
- Q19 = **옵션 B** (상위 500 종목, scanner 의 거래대금/등락률 영역과 일치)
- Q20 = **옵션 A + 사이클 83 결합** (개장 전 1회 + 5분 주기 자연 흡수)
- Q21 = **옵션 A** (`volume_rank` 단독, scanner 와 영역 분리)
- Q22 = **옵션 A** (90일 영속, 부담 5% 안전)
- Q23 = **옵션 A** (전략 독립성 보존, 사이클 67 추상화는 3회 반복 후)

**도메인 자문 의무 결정 의제**:
- Q19-1: 500 종목 적정 기준 (거래대금 vs 거래량 vs 등락률 vs 시가총액)
- Q21-1: KRX + KOSDAQ 분리 호출 시 dedupe 정합성 (액면분할 종목, ETF 제외 영역)
- Q23-1: 전략별 필터링 영역 = momentum (상한가) / VB (변동성) / LTV (꼬리) / donchian (채널) / BFB (깃발) / VCP (수렴) — 각 영역 stock_master raw 활용 범위

---

## J. 사용자 다음 단계

1. Q19~Q23 결정 → team-leader 가 domain-expert 자문 발주 (Q19/Q21/Q23 의제)
2. domain-expert 자문 회신 → team-leader Phase 2 (명세 분해)
3. tdd-engineer Red → backend-dev Green → tester 검증 → CLAUDE.md / docs/HARNESS_CHANGELOG.md 갱신

산출물: `_workspace/cycle89_phase1_diagnosis.md` (본 문서)
