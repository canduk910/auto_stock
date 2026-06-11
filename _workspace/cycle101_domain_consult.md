# 사이클 101 도메인 자문 — market_cap 페이징 + CTPF1002R 편입 (~2,800 ticker 확장)

**의뢰**: team-leader (사이클 101 Phase 2)
**자문 일시**: 2026-06-11 (수) KST
**위급도**: **HIGH** (사이클 99 60 ticker 영구 영속 → ~2,800 16x 확장 본질 해결 / 매매 hot path 영향 평가)
**선행**: `_workspace/cycle101_phase1_diagnosis.md` (Q67~Q70 사용자 결정 채택)
**채택 결정**: Q67=B (20:00:05 자문 직후 + NXT 마감 동행) / Q68=A (fluctuation 영구 폐기) / Q69=B (사이클 89 5분 주기 폐기) / Q70=A (Phase 1 후 자문 발주)
**자문 범위**: A1~A5 (HIGH 3 + MEDIUM 2)
**코드 변경**: 0 (자문 단독)

---

## 1. 질문 요약

사이클 99 시점 fluctuation API = `mksc_shrn_iscd` 비반환 = **60 ticker 영구 영속** (KIS API 본질 한계 확정). 사이클 100 Phase 1 + 사이클 101 Phase 1 정본 재검증 결과 = **market_cap (FHPST01740000) = KIS 156 API 중 유일 `tr_cont="M"` 페이징 지원** = ~2,800 ticker 확장 가능. 본 자문 = stock_master ~2,800 적재 + 매일 20:00:05 일괄 + fluctuation 영구 폐기 + 사이클 89 5분 주기 폐기 = **사이클 89 답습 + 본질 해결 영역** 매매 hot path 영향 평가 의무.

---

## 2. 트레이더 시각 (전체 의제 공통 배경)

### 시장 가설

- **~2,800 = KRX 전체 종목 ≈ 코스피 950 + 코스닥 1,650 + ETF/리츠 200 (정상 KRX 매매 활성 종목)**: 사이클 89 권고 (KOSPI 250 + KOSDAQ 250 = 500) 대비 **5.6배 확장** = "전 종목 시야 확보" 전환점. 트레이더 실전 = 데일리 후보 풀은 *모니터링 영역* 과 *진입 영역* 분리 — 모니터링은 전 종목 가능, 진입은 거래대금/시총 필터링 후 ~30~50건이 표준.
- **사이클 89 답습 영속 (단 16x 확장)**: 사이클 89 권고 A4 매트릭스 (후보 풀 폭증 위험 차단) 영속 보장 — *적재 영역 (DB)* 과 *구독/매수 영역 (hot path)* 분리. ~2,800 적재 = stock_master DB 확장만, WS 구독 41 한도 영향 0 (사이클 32 R4 영속).
- **fluctuation (등락률) = 사이클 89 영역 부산물**: 사이클 97 도입 (volume_rank 60 한도 보강) → 사이클 99 mksc_shrn_iscd 비반환 발견 → 60 ticker 영구 영속. **market_cap = 정렬 기준 (시가총액) 본질 우월** — 등락률 정보는 별도 hook (`fetch_rising_stocks` 영속) 으로 보강 가능. 폐기 = 결함 영구 차단.
- **매일 20:00:05 적재 = NXT 마감 동행**: KRX 마감 (15:30) + NXT POST 마감 (20:00) = 시장 1일 데이터 확정 시점. 익일 09:00 매매 시작 = 전일 적재 영속 영역 100% 활용 (24h TTL 영속).

### 실전 사례

- **사이클 81 SK스퀘어 (402340) 영속**: 1,122,340원 고가 종목 = stock_master 미적재 → `bfdy_clpr=0` graceful → 가격필터 무용. 사이클 89 500 universe 적재 = 부분 회복. **사이클 101 ~2,800 적재 = bfdy_clpr 정확도 ~99%+ (24h TTL 안정화 후)** = 가격필터 효과 영구 회복.
- **사이클 65 trade_amount_filter 영속**: 디폴트 0 = 비활성 (운영자 임계 영역). 사이클 101 ~2,800 적재 = trade_amount 임계 정확도 ~99%+ 회복 = 작전주 자동 차단 효과 영구 확립. 운영자 임계 1억 이상 권장 (사이클 65 UI 권장값 마커 영속).
- **사이클 31 R6 영속 (`current_price > total_investment`)**: 사이클 81 → ~2,800 적재 = R6 trigger 빈도 270/일 → 0~5건/일 영속. R6 = *마지막 안전망* 으로 영구 보존 의무 (사이클 81 영속).
- **사이클 17 OPSP0002 + 사이클 29 005935 LMS chain 사고 영속**: ~2,800 × CTPF1002R = 모의 9분 / 실전 2분 = **연속 호출 차단 영구 영속 의무**. 50ms sleep × 2,800 = 140초 (실전) ~ 9분 (모의) 백그라운드 직렬 — KIS LMS chain 차단 영속 (사이클 76 collector 영속).
- **사이클 89 5분 주기 task vs 사이클 101 매일 20:00:05 일괄**: 사이클 89 = 5분 주기 (5분 마다 60 ticker 갱신 = 운영 시간 적시성 강조) / 사이클 101 = 매일 1회 (전일 일괄 적재 = 24h TTL 안정성 강조). **사이클 89 영구 폐기 = 적시성 영역 손실 vs 운영 단순화 (메모리/REST 부하 안정)** 트레이드오프.

### 위험 시나리오

- **R-1 (HIGH)**: 20:00:05 동시 호출 race — `unsubscribe_all()` (NXT 마감) + `generate_recommendations()` (OpenAI 3분) + `_full_universe_load_once()` (KIS REST 2~9분) **동시 발화**. 외부 API 3종 동시 부담 영역.
- **R-2 (HIGH)**: KIS LMS chain (~2,800 호출 영역) — 사이클 29 005935 사고 패턴 (8분 영구 잔류 + KIS LMS chain 차단). 50ms sleep + graceful + Semaphore 20/s 영속 의무.
- **R-3 (HIGH)**: 정산 (20:10) 영역 race — 모의 환경 = 9분 적재 → 20:09 종료 → 정산 (20:10) 직전 1분 마진. **모의 환경 정산 지연 위험** = 사이클 6 정산 영속 영역 위협.
- **R-4 (MEDIUM)**: fluctuation 영구 폐기 = 등락률 순위 정보 손실. `scanner.fetch_rising_stocks` (±15%+) 별도 hook 영속 = **등락률 기반 후보 풀 영역 영향 0**. 단, UI 종목마스터 영역 = 등락률 컬럼 표시 = 영향 영역 (검토 의무).
- **R-5 (LOW)**: 사이클 89 영역 폐기 + 사이클 95 unknown 합집합 영역 — market_cap KOSPI/KOSDAQ 명시 분리 = unknown=0 영속. 사이클 95 `_classify_market` 영역 영속 가능 (시장 분류 헬퍼 모듈 영역 한정).
- **R-6 (LOW)**: ~2,800 적재 = stock_master_history 부담 — 사이클 84 90일 retention 영속 + ~2,800 = 252,000 row (5% 미만 영역, 안전).

---

## 3. 자문 권고 (A1~A5 세부)

### A1 — ~2,800 적재 시 매매 영향 평가 (HIGH)

**권고**: **사이클 38 명문화 영속 + 사이클 32 R4 영속 + 사이클 64/65/81 graceful 영속 = 매매 hot path 영향 0 보장**. ~2,800 적재 = DB 영역 한정 + scanner 단계 필터링 영속 + WS 41 한도 영속 = 영구 차단.

#### 매매 영역 매트릭스 (HIGH 4)

| 영역 | 사이클 101 *전* (171 ticker) | 사이클 101 *후* (~2,800 ticker) | 위험 평가 |
|------|------------------------------|--------------------------------|----------|
| **사이클 38 명문화** (`tradable_boards` 매수 진입 전용) | 영속 | 영속 (매수 진입만 영향, 매도/익일청산/15:20 강제청산 영향 0) | **영향 0** |
| **사이클 32 R4 universe guard** (보유/익일청산 절대 보호) | 영속 | 영속 (~2,800 적재해도 보유 ticker 절대 보호) | **영속 영구** |
| **사이클 64/65/81 graceful** (stock_master 부재 graceful) | graceful 영속 | **strict 전환 가능** (~99% 적재율) | **회복 (사이클 81 의도)** |
| **6 전략 후보 풀** (Plan Phase A/B 인계) | 사이클 95 unknown 영속 | **명시 KOSPI/KOSDAQ 영역 전환** | **정확도 회복** |

#### 사이클 38 명문화 영속 보장 검증 (HIGH 핵심)

- **사이클 38 명문화 (2026-05-22)**: `tradable_boards` 매수 진입 전용 = 매도/손절/Trailing/익일청산/15:20 강제청산/상한가 손절 모니터링 = **PRE/MAIN/POST 무관 항상 작동**. `risk.on_tick::check_exit_signal` 분기 `session_tracker.is_tradable` 검사 *전* 진입.
- **사이클 101 ~2,800 적재 영향**: scanner 단계 (subscribe_filtered_stocks 진입) = **매수 진입 영역만**. 매도/익일청산 영역 = 영향 0.
- **회피 시나리오**: ~2,800 적재가 어떤 새로운 매수 신호도 직접 발화하지 않음 — *전략 prepare → check_buy_signal* chain 영속 영역 의무.

#### 사이클 32 R4 universe guard 영속 보장 (HIGH)

- **사이클 32 R4**: stale>5 + `today_volume < 10_000` → 자동 unsubscribe + `_universe_excluded_today` 등록. **보유/익일청산 절대 보호 영속**.
- **사이클 101 ~2,800 적재 영향**: stale 평가 영역 확장 (171 → ~2,800) → guard 정확도 상승. **보유/익일청산 절대 보호 영속** (R4 평가 *전* protected_tickers 우선 보호 영속).
- **WS 41 한도 영속**: ~2,800 적재 ≠ ~2,800 WS 구독. 실제 WS 구독 = scanner 필터링 후 ~30~50건 (사이클 32 R4 영속 + 41 한도 영속).

#### 사이클 64/65/81 graceful → strict 전환 영역 (MEDIUM)

- **현 graceful 영역**: stock_master 부재 → `bfdy_clpr=0` graceful 통과 / `acml_tr_pbmn` 폴백 영속 (사이클 65 영역).
- **사이클 101 적재율 ~99%+**: 24h TTL 안정화 후 ~2,800 / 2,800 = ~100% 적재율. **strict 전환 가능 영역** (graceful 통과 ticker 0 영역 영속).
- **권고**: **graceful 영속 유지 + 운영 가시화 prefix 신규 도입**: `[price_filter_graceful_pass]` ticker=N (≥1건 = 적재 누락 신호). 사이클 81 silent 결함 영구 차단 패턴 영속 의무. **strict 전환 비추 (운영 안정성 우선)** — 신규 종목 IPO 첫날 = 전일 영역 없음 = graceful 통과 영속 필요.

#### 6 전략 후보 풀 영역 영향 (Plan Phase A/B 인계)

| 전략 | 사이클 101 적재 활용 | 후보 풀 변화 |
|------|---------------------|------------|
| momentum | bfdy_clpr + acml_tr_pbmn + 시총 (lstn_stcn × stck_prpr) | 상한가 조건검색 영속 (변경 0) |
| VB | bfdy_clpr + acml_tr_pbmn + 시총 | 일봉 영속 (변경 0) |
| LTV | bfdy_clpr + acml_tr_pbmn + 시총 | 일봉 + 연속 상한가 영속 |
| donchian | 시총 ≥ 1,000억 (lstn_stcn × stck_prpr) | **stock_master 베이스 전환 가능** (Plan Phase B) |
| BFB | 시총 ≥ 500억 + acml_tr_pbmn ≥ 20억 | **stock_master 베이스 전환 가능** (Plan Phase A) |
| VCP | 시총 ≥ 1,000억 | **stock_master 베이스 전환 가능** (Plan Phase B) |

- **Plan Phase A/B 인계 영역**: 사이클 101 = 적재 영역 단독 (전략 prepare 변경 0). Plan Phase A (VB/LTV/BFB) + Phase B (donchian/VCP) = 별개 사이클 인계 의무 (사이클 102+).
- **회피 시나리오**: 적재만 도입하고 전략 prepare 미변경 시 = 사이클 101 효과 = scanner 필터링 영역만 한정. Plan Phase A/B 인계 = 후보 풀 stock_master 베이스 전환 = **별개 사이클 (사이클 102+)** 영역.

---

### A2 — 20:00:05 적재 시점 영역 race 평가 (HIGH)

**권고**: **Q67=B (20:00:05) 채택 영속 + 사이클 89 5분 주기 영구 폐기 (Q69=B) + 정산 (20:10) 마진 확보 의무 = 옵션 2 영역 + 운영 환경 분리 가드 신설**.

#### race 위험 매트릭스 (HIGH 3)

| 영역 | 동시 시점 | API | race 영역 | 위험 평가 |
|------|---------|-----|----------|----------|
| `unsubscribe_all()` (NXT 마감) | 20:00:00 | KIS WebSocket | 시세 전수 해제 (5초 이내 완료 영속) | **race 0** (5초 마진) |
| `generate_recommendations()` (AI 자문) | 20:00:00 | OpenAI | OpenAI ~3분 (외부 API 단독) | **race 0** (외부 API 서로 다름) |
| `auto_apply_recommendations()` (사이클 23) | 20:03:00 (자문 직후) | Supabase | DB INSERT/UPDATE (사이클 23 영속) | **race 0** (DB 영역) |
| `_full_universe_load_once()` (사이클 101 신규) | 20:00:05 | KIS REST (CTPF1002R) | KIS REST 2~9분 (Rate Limit 영역) | **R-1 검토 영역** |
| 사이클 89 `_universe_eager_refresh_loop` (5분 주기) | 20:00 (5분 주기 중 1회) | KIS REST | KIS REST 12초 (60 ticker) | **R-2 폐기 영속** |
| `_settle()` (정산) | 20:10:00 | DB + 일일 보고 | 일일 보고 ~60초 (사이클 6) | **R-3 모의 환경 위험** |

#### R-1 (HIGH) 20:00:05 동시 호출 race 평가

- **현황**: `unsubscribe_all()` (5초) + `generate_recommendations()` (OpenAI 3분) + `_full_universe_load_once()` (KIS REST 2~9분) = 외부 API 3종 동시 발화 영역.
- **결정적 발견**: **3 API 서로 다른 엔드포인트** — KIS WebSocket / OpenAI / KIS REST = 서로 다른 외부 API + 서로 다른 RTT. KIS REST = 2,800 호출 = 50ms sleep 영속 = 직렬 호출 영역 (Semaphore 20/s 영속).
- **위험 평가**: **race 0** (KIS WebSocket = 시세 영역 / OpenAI = AI 자문 영역 / KIS REST = 종목정보 영역 = 영역 분리 영속). 단 *KIS Rate Limit 영역* = OpenAI 자문 직후 KIS REST 호출 시 호출 빈도 영역 영속 의무 (사이클 76 collector 영속).
- **권고**: **옵션 2 (20:00:05) 채택 영속** + Semaphore 20/s 영역 영속 + 50ms sleep 영속 의무.

#### R-2 (HIGH) 사이클 89 5분 주기 task vs 사이클 101 매일 1회 — Q69=B 영속

- **사이클 89 영구 폐기 (Q69=B)**: `_universe_eager_refresh_loop` (5분 주기) + `_universe_eager_refresh_task` 영구 cancel.
- **race 위험 0**: 사이클 89 영구 폐기 = 20:00 시점 동시 호출 위험 0.
- **사이클 89 답습 가치**: 5분 주기 = 적시성 영역 (운영 중 새 종목 발견 시 즉시 적재). **사이클 101 = 매일 20:00 일괄 = 적시성 영역 손실** = 익일 09:00 매매 시작 시점 = 전일 적재 영역 영속. **운영자 추적 의무**: 운영 중 신규 IPO 종목 (당일 진입 위험) = `[stock_master_loaded_at]` 1주일 이상 = WARNING emit 의무.
- **권고**: **Q69=B (영구 폐기) 채택 영속** + 운영 가시화 prefix 신설 `[stock_master_age_warning]` ticker=N age_days=M (사이클 89 적시성 영역 손실 보강) + 신규 IPO 종목 운영자 수동 적재 영역 후속 사이클 (사이클 102+) 검토.

#### R-3 (HIGH) 정산 (20:10) 영역 race — 모의 환경 위험

- **모의 환경**: 5건/초 Rate Limit = 2,800 / 5 = 560초 (9분 24초) = **20:09:24 종료 → 20:10 정산 직전 36초 마진**.
- **실전 환경**: 20건/초 Rate Limit = 2,800 / 20 = 140초 (2분 20초) = **20:02:25 종료 → 정산 7분 35초 마진** = 안전 영역.
- **위험 평가**: **모의 환경 정산 지연 위험 HIGH** = 사이클 6 정산 영속 영역 위협. Semaphore 20/s 영속 + Rate Limit 환경 분리 영역 영속 의무.
- **권고**: **운영 환경 분리 가드 신설** — `max_load_seconds=600` (모의) / `=300` (실전) 영역 타임아웃 (graceful skip + WARNING emit) + 정산 (20:10) 영역 race 절대 차단 의무. `KIS_ENV` 환경 변수 영역 영속 분기 의무.

#### 외부 백테스트 영역 (사이클 27 영속) race

- **사이클 27 영속**: 20:00:05 AI 자문 INSERT 직후 외부 MCP 백테스트 (12 job fire-and-forget).
- **race 영역**: fire-and-forget = 백그라운드 영역 = 사이클 101 적재와 동시 가능 영속. 외부 MCP 서버 = 별도 호스트 (43.202.187.5) = KIS REST 영역 무관 = **race 0**.
- **권고**: **사이클 27 영속 영역 변경 0** (외부 MCP 영역 분리 영속).

---

### A3 — Rate Limit / KIS LMS chain 위험 평가 (HIGH)

**권고**: **사이클 17/18/29/76/88 영속 매트릭스 = ~2,800 호출 영역 LMS chain 차단 영속 보장**. 50ms sleep + Semaphore 20/s + graceful + 환경 분리 가드 + 운영 가시화 = 5중 안전망 영속.

#### LMS chain 위험 매트릭스 (HIGH 5)

| 영역 | 영속 매트릭스 | 사이클 101 적용 | 위험 평가 |
|------|--------------|---------------|----------|
| **사이클 17 OPSP0002 backoff** (WebSocket 영역) | `_opsp_backoff_until` dict 영속 | WS 구독 영역 무관 (DB 영역) | **영향 0** |
| **사이클 18 60s WARNING dedupe** (REST 영역) | `_request_5xx_dedupe` 영속 | ~2,800 호출 중 5xx 응답 시 dedupe 영속 | **영속 영속** |
| **사이클 29 005935 LMS chain 사고** (8분 영구 잔류) | priority 분리 + cap 영속 | ~2,800 호출 = K stale watcher 영역 무관 (백그라운드 task 영역) | **영향 0** |
| **사이클 76 retry collector** (5분 윈도우) | `_api_recovered_collector` 영속 | ~2,800 호출 = collector 흡수 영속 | **영속 영속** |
| **사이클 88 G-REJECT-1/2/3** (4중 안전망) | 영속 | WS 영역 무관 (DB 영역) | **영향 0** |

#### 사이클 29 005935 LMS chain 사고 패턴 영구 차단

- **사고 패턴 (사이클 29)**: K stale watcher 6회 초과 즉시 재등록 → KIS LMS chain 차단 → 005935 8분 영구 잔류.
- **사이클 101 영역 분리**: ~2,800 호출 = `_full_universe_load_once()` 함수 영역 = 백그라운드 task (lifecycle 영역) = K stale watcher (시세 영역) 무관 = **영향 0**.
- **권고**: K stale watcher 영역 영속 변경 0 + 사이클 101 `_full_universe_load_once()` = 50ms sleep + Semaphore 20/s + graceful (사이클 88 G-REJECT 영속) 5중 안전망 영속.

#### 사이클 88 G-REJECT 영속 영역

- **G-REJECT-1 (4중 안전망)**: 사이클 101 변경 영역 0 (WS 영역 무관).
- **G-REJECT-2 (종목별 stale 영속)**: 사이클 101 = stock_master DB 영역 = `ticker_last_tick` (WS 영역) 영향 0.
- **G-REJECT-3 (4 dict 분리 영속)**: 사이클 101 = 모듈 전역 dict 추가 0 (stock_master DB upsert 영역만).
- **권고**: **사이클 88 G-REJECT-1/2/3 영속 영구 보장** (영역 분리, 영향 0). 사이클 89 답습 영속 (A5 영속 영역).

#### Rate Limit 영역 환경 분리 영역 영속

- **모의 환경**: 5건/초 = 50ms sleep × 2,800 = 560초 (9분 24초).
- **실전 환경**: 20건/초 = 50ms sleep × 2,800 = 560초 동일 (sleep 영역 동일) / Semaphore 영역 차이.
- **결정적 발견**: **50ms sleep = Semaphore 20/s 영역 한도 (50ms = 1/20 = 20건/초) 일치** = **실전 환경 효율 최대화 영역 영속**. 모의 환경 = Semaphore 5/s 영역 = 200ms sleep 영역 권고.
- **권고**: **환경 분리 sleep 영역 영속 의무** — `KIS_ENV=real` 50ms / `KIS_ENV=vts` 200ms 분기. 정산 (20:10) 영역 race 차단 영역 영속.

#### graceful + 운영 가시화 영역 (사이클 88 G-REJECT 답습)

- **graceful 영속**: KIS CTPF1002R 호출 실패 (rt_cd != "0") 시 `try: ... except Exception: continue` 영속 (사이클 88 G-REJECT 답습).
- **운영 가시화 prefix 신설 (사이클 74/76 답습)**:
  1. `[full_universe_load_summary] total=N kospi=M kosdaq=K securities=L etf=J fetched=I skipped_ttl=H failed=G elapsed_ms=F` — 매일 20:00:05 적재 후 1행 INFO.
  2. `[full_universe_load_rate_limit] env=real|vts sleep_ms=50|200 semaphore=20|5 calls=2800 throttle_events=N` — Rate Limit 영역 영속 가시화.
  3. `[full_universe_load_failed] ticker=X status=N msg=Y` — 실패 ticker 영역 (사이클 88 G-REJECT-3 분리 영속).
- **G-AST 영속 가드 (사이클 78/79 답습)**:
  - **G-AST1 (사이클 78 답습)**: `record_full_universe_load_summary` / `flush_full_universe_load_collector` 호출 사이트 ≥1건 정적 검증.
  - **G-AST2 (사이클 79 답습)**: `_full_universe_load_task` cancel 목록 (`stop()` task_attrs 튜플) + `run_daily()` finally 블록 양쪽 동행 추가 의무.

---

### A4 — Q68 fluctuation 영구 폐기 영향 (MEDIUM)

**권고**: **Q68=A (영구 폐기) 채택 영속 + market_cap 단독 영속 + 등락률 정보 영역 별도 hook 영속**. fluctuation 영역 폐기 = 결함 영구 차단 + market_cap = 정렬 기준 (시가총액) 본질 우월.

#### fluctuation 폐기 영향 매트릭스 (MEDIUM 3)

| 영역 | 사이클 99 *전* (fluctuation 60) | 사이클 101 *후* (market_cap ~2,800) | 영향 평가 |
|------|--------------------------------|------------------------------------|----------|
| **등락률 순위 정보** | fluctuation 응답 (등락률 정렬) | 별도 hook 영속 (`scanner.fetch_rising_stocks` ±15%+) | **영향 0** (별도 hook 영속) |
| **6 전략 후보 풀** | 60 ticker 한정 | ~2,800 ticker 확장 = 후보 풀 영구 확장 | **회복 영구** |
| **UI 종목마스터 영역** | 등락률 컬럼 표시 가능 | 등락률 컬럼 = `bfdy_ctrt` (CTPF1002R 영속) 영속 가능 | **영향 영역** (UI 후속 검토) |

#### 등락률 정보 영역 별도 hook 영속 보장

- **`scanner.fetch_rising_stocks` 영속**: ±15%+ 종목 = 모멘텀 / 상한가 전략 영역 = scanner 단계 영속 (사이클 89 영속).
- **사이클 89 답습 영역**: A1 자문 영속 — *등락률 단독 = 모멘텀 시그널이나 작전 함정* / *거래대금 = 작전주의 1차 시그널*. 등락률 정렬 = 작전주 위험 (사이클 89 영속).
- **권고**: **fluctuation 폐기 = 등락률 정렬 영역 폐기 영속** + `scanner.fetch_rising_stocks` (±15%+) 별도 hook 영속.

#### UI 종목마스터 영역 영향 (LOW)

- **`stock_master.raw.bfdy_ctrt`** (전일등락률, CTPF1002R 67 컬럼 영속): 사이클 101 적재 시 등락률 컬럼 자동 적재. UI 표시 = 영속 가능.
- **사이클 101 추가 시정 영역 비추 (운영 안정 우선)**: UI 영역 = 사이클 101 범위 외 (후속 사이클 검토 영역).

#### 사이클 95 unknown 합집합 영역 관계 (A5 연결)

- **사이클 95 `_classify_market` 영속**: KOSPI/KOSDAQ 명시 분리 영역 영속. unknown = 시장 분류 영역 영속.
- **사이클 101 market_cap 직접 호출 시점**: `fid_input_iscd="0001"` (KOSPI) + `fid_input_iscd="1001"` (KOSDAQ) = **명시 분리 영역 = unknown=0 영속**.
- **권고**: 사이클 95 `_classify_market` 영역 영속 영구 보존 (시장 분류 헬퍼 모듈 영역 한정) + unknown=0 영속 영역 영속 의무.

---

### A5 — Q69 사이클 89 폐기 영향 + 사이클 95 unknown 합집합 영역 관계 (MEDIUM)

**권고**: **Q69=B (영구 폐기) 채택 영속 + 매일 20:00 일괄 단독 영역 영속 + 운영 가시화 prefix 신설 (적시성 영역 손실 보강)**. 사이클 95 unknown 합집합 영역 = 사이클 101 market_cap 명시 분리로 unknown=0 영속.

#### 사이클 89 폐기 영향 매트릭스 (MEDIUM 3)

| 영역 | 사이클 89 *영속* (5분 주기) | 사이클 101 *후* (매일 20:00 단독) | 영향 평가 |
|------|---------------------------|----------------------------------|----------|
| **운영 적시성** | 5분 주기 = 운영 중 즉시 적재 | 매일 1회 = 익일 09:00 매매 시작 영속 | **적시성 영역 손실** (보강 의무) |
| **메모리/REST 부하** | 5분 × 24시간 = 288회/일 × 60 ticker = 17,280 호출/일 | 매일 1회 × ~2,800 ticker = 2,800 호출/일 = **84% 감소** | **운영 단순화 (안정)** |
| **24h TTL 안정성** | 5분 주기 = TTL 자연 갱신 영속 | 매일 20:00 = TTL 24h 정확 일치 영속 | **영향 0** (TTL 영속) |
| **사이클 95 unknown 합집합** | unknown 영속 영역 (fluctuation 영역) | unknown=0 영속 (market_cap KOSPI/KOSDAQ 명시 분리) | **회복 영구** |

#### 적시성 영역 손실 보강 권고

- **신규 IPO 종목 영역**: 당일 IPO 종목 = 전일 적재 영역 부재 = `bfdy_clpr=0` graceful 통과 영속 (사이클 81 영속). **사이클 101 = 익일 20:00 적재 영속** = IPO 당일 진입 위험 = graceful 단독 영역.
- **권고**: **운영 가시화 prefix 신설** — `[stock_master_age_warning] ticker=X loaded_at=Y age_days=Z` (7일 이상 = WARNING emit). 신규 IPO 종목 운영자 수동 적재 영역 후속 사이클 (사이클 102+) 검토.

#### 매일 20:00 일괄 단독 영역 영속 보장

- **24h TTL 영속**: 매일 20:00 적재 → 익일 19:59 만료 → 익일 20:00 재적재 영속. **TTL 영역 정확 일치 영속**.
- **익일 09:00 매매 시작 시점**: 전일 적재 영역 100% 활용 (13시간 후 = TTL 11시간 잔존). 매매 hot path 영역 영속.
- **권고**: **매일 20:00 일괄 단독 영역 영속 의무** + `_universe_eager_refresh_loop` (5분 주기) 영구 폐기.

#### 사이클 95 unknown 합집합 영역 관계 (LOW)

- **사이클 95 `_classify_market` 영속**: 사이클 99 fluctuation 영역 영속 시 unknown=영속 (시장 분류 영역).
- **사이클 101 market_cap 명시 분리**: `fid_input_iscd="0001"` (KOSPI) + `"1001"` (KOSDAQ) = **명시 분리 영역 = unknown=0 영속**.
- **사이클 95 영역 영속 가능**: `_classify_market` 헬퍼 모듈 영역 한정 영속 (시장 분류 헬퍼 영역). 폐기 비추 (모듈 재사용 영역 영속).
- **권고**: **사이클 95 `_classify_market` 영역 영속 영구 보존** + unknown=0 영속 영역 영속 의무.

---

## 4. 현 코드와의 정합성

### 충돌 항목 없음

- **사이클 38 명문화**: `tradable_boards` 매수 진입 전용 영속 — 사이클 101 = scanner 단계 영역 = 매수 진입만 영향. 매도/익일청산/15:20 강제청산 영향 0.
- **사이클 31 R6 영속**: 가격필터 정상화로 R6 trigger 빈도 270 → 0~5건/일 = R6 안전망 영속.
- **사이클 32 R4 universe guard**: 보유/익일청산 절대 보호 영속 — ~2,800 적재 = R4 평가 영역 확장 (positives only).
- **사이클 64 Q1 옵션 D**: `_collect_protected_tickers_for_scanner` 3중 안전망 영속 — ~2,800 적재해도 보유 ticker graceful 통과 영속.
- **사이클 65/81 영속**: trade_amount_filter (사이클 65) + price_filter bfdy_clpr (사이클 81) 정확도 회복 ~99%+.
- **사이클 67 stale_manager 분해**: 영향 0 (영역 분리).
- **사이클 78/79 영속**: G-AST1 (flush 호출 사이트) + G-AST2 (cancel 영구 가드) 답습 의무.
- **사이클 83 scan_pool eager refresh**: candidates=12 영역 영속 + ~2,800 영역 = 영역 분리 (24h TTL 자연 흡수).
- **사이클 84 history trigger**: 90일 retention 영속 + ~2,800 universe = 252,000 row (5% 미만, 안전).
- **사이클 88 G-REJECT-1/2/3**: 영향 0 (A3 분석 영속).
- **사이클 89 영구 폐기 (Q69=B)**: `_universe_eager_refresh_loop` + `_universe_eager_refresh_task` 영구 cancel.
- **사이클 95 `_classify_market` 영속**: 헬퍼 모듈 영역 한정 영속 (unknown=0 영속).
- **사이클 97 fluctuation 영구 폐기 (Q68=A)**: `_fetch_fluctuation` + `_FLUCTUATION_URL` + `_FLUCTUATION_TR_ID` 영구 폐기.
- **사이클 98 G-DOC1 영속**: KIS chk_*.py 정본 인용 의무 영속.
- **사이클 99 60 ticker 영구 영속 영역 본질 해결**: market_cap 페이징으로 ~2,800 16x 확장.
- **사이클 100 Phase 1 D-1 영속**: market_cap = KIS 156 중 유일 페이징 지원 영역.

---

## 5. 위험 영역 매트릭스

| 등급 | 영역 | 영향 | 시정 의무 |
|------|------|------|----------|
| HIGH | ~2,800 적재 매매 hot path 영향 0 | 사이클 38/32/64/65/81 영속 매트릭스 | A1 권고 영속 |
| HIGH | 20:00:05 동시 호출 race (R-1) | 외부 API 3종 영역 분리 영속 | A2 권고 영속 |
| HIGH | 정산 (20:10) 모의 환경 race (R-3) | `max_load_seconds` 환경 분리 가드 신설 | A2 권고 영속 |
| HIGH | KIS LMS chain (~2,800 호출 영역) | 사이클 17/18/29/76 영속 매트릭스 + Semaphore 20/s + 50ms sleep + graceful | A3 권고 영속 |
| HIGH | 사이클 88 G-REJECT-1/2/3 영속 | 영향 0 (영역 분리) | 영속 영구 |
| HIGH | 사이클 32 R4 universe guard | 보유/익일청산 절대 보호 영속 | 영속 영구 |
| HIGH | 사이클 38 명문화 영속 | `tradable_boards` 매수 진입 전용 영속 | 영속 영구 |
| MEDIUM | fluctuation 폐기 등락률 정보 영역 | `scanner.fetch_rising_stocks` 별도 hook 영속 | A4 권고 영속 |
| MEDIUM | 사이클 89 5분 주기 영구 폐기 | 적시성 영역 손실 + `[stock_master_age_warning]` 보강 | A5 권고 영속 |
| MEDIUM | 사이클 95 `_classify_market` 영속 | 헬퍼 모듈 영역 한정 영속 (unknown=0 영속) | A5 영속 영속 |
| MEDIUM | 백그라운드 task lifecycle (사이클 79 답습) | 신규 task attribute 도입 시 cancel 영구 가드 | A3 G-AST2 의무 |
| MEDIUM | 운영 가시화 (3 신규 prefix) | `[full_universe_load_summary]` + `[full_universe_load_rate_limit]` + `[full_universe_load_failed]` | A3 영속 |
| LOW | UI 종목마스터 등락률 컬럼 | `bfdy_ctrt` 영속 가능 (후속 사이클 검토) | 사이클 102+ 인계 |
| LOW | stock_master_history 부담 (252,000 row) | 90일 영속 + ~2,800 = 5% 미만 (안전) | Q22 답습 영속 |
| LOW | KST 영속 (사이클 68) | `src/db/_kst.py` 헬퍼 영속 | 영속 영구 |
| LOW | KIS MCP 정본 인용 (사이클 98 G-DOC1) | `chk_market_cap.py` + `chk_search_stock_info.py` 정본 100% 인용 | 영속 영구 |

---

## 6. 시정 영역 명세 (backend-dev 인계)

### 신규 영역 (사이클 101 권고)

1. **`src/engine/scanner.py::_fetch_market_cap_page()` 신규 함수** (~60L, Phase 1 D-1 답습):
   - KIS `market_cap` (FHPST01740000) 호출 + `tr_cont="M"` 재귀 페이징 누적 (정본 L107~120 영역 영속).
   - `fid_input_iscd` 인자: `"0001"` (KOSPI) / `"1001"` (KOSDAQ) 명시 분리.
   - `fid_cond_mrkt_div_code="J"` 강제 (정본 ValueError 가드 영속) + `fid_cond_scr_div_code="20174"` 강제.
   - 페이지 당 30 ticker × 최대 100 페이지 = 3,000 ticker 안전 한도.
   - `ka.smart_sleep()` 페이징 간 sleep (정본 영속).
   - 응답 list 반환 (최대 3,000 ticker × 11 컬럼).

2. **`src/engine/scanner.py::_full_universe_load_once()` 신규 함수** (~50L):
   - KOSPI + KOSDAQ market_cap 페이징 누적 (~2,800 ticker 예상).
   - 50ms sleep × 2,800 = 140초 (실전) ~ 9분 (모의) 백그라운드 직렬.
   - 환경 분리 sleep 영역 영속 의무 (`KIS_ENV=real` 50ms / `KIS_ENV=vts` 200ms 분기).
   - CTPF1002R 67 컬럼 → `stock_master.upsert_one()` 호출 영역 (24h TTL 자연 skip + graceful 영속).
   - `max_load_seconds` 환경 분리 타임아웃 영역 (모의 600s / 실전 300s) + graceful skip + WARNING emit.
   - 응답 dict 반환 (`total`/`kospi`/`kosdaq`/`securities`/`etf`/`fetched`/`skipped_ttl`/`failed`/`elapsed_ms`).

3. **`src/engine/scheduler.py::_full_universe_load_task` 신규 task** (~30L):
   - 매일 20:00:05 1회 발화 (`TIME_FULL_UNIVERSE_LOAD = time(20, 0, 5)` 신규 상수).
   - lifecycle (`connect/disconnect`) hook = 사이클 79 답습 의무 (`stop()` task_attrs 튜플 + `run_daily()` finally 블록 양쪽 동행).
   - graceful 영속 (사이클 88 G-REJECT 답습).

4. **`src/engine/stock_master_metrics.py` 신규 모듈** (~50L, 사이클 74/78 답습):
   - `record_full_universe_load_summary(stats)` + `flush_full_universe_load_collector()` (1회 emit 영속).
   - `[full_universe_load_summary]` prefix.
   - `_api_recovered_collector_loop` (사이클 76/78 영속) 본체에 flush 호출 추가 (사이클 78 답습).

5. **AST 영구 가드**:
   - G-AST1 (사이클 78 답습): `record_full_universe_load_summary` 정의 모듈의 대응 `flush_full_universe_load_collector` 호출 사이트 ≥1건 정적 검증.
   - G-AST2 (사이클 79 답습): `_full_universe_load_task` cancel 목록 (`stop()` task_attrs 튜플) + `run_daily()` finally 블록 양쪽 동행 추가 의무.

### 폐기 영역 (사이클 101 권고)

1. **`src/engine/scanner.py::_fetch_fluctuation`** (사이클 97 영속) — Q68=A 영구 폐기.
2. **`src/engine/scanner.py::fetch_top_500_universe`** (사이클 89 영속) — Q69=B 영구 폐기.
3. **`src/engine/scheduler.py::_universe_eager_refresh_loop`** (사이클 89 영속) — Q69=B 영구 폐기.
4. **`src/engine/scheduler.py::_universe_eager_refresh_task`** (사이클 89 영속) — Q69=B 영구 cancel.
5. **`_FLUCTUATION_URL` / `_FLUCTUATION_TR_ID`** (scanner.py 모듈 전역) — Q68=A 영구 폐기.

### 변경 0 영역 (영속 의무)

- `src/engine/risk.py` (사이클 64 영속 영역)
- `src/engine/order_engine.py` (체결통보 영역, 사이클 55 R-1 영속)
- `src/engine/stale_*.py` (사이클 67 영속)
- 6 전략 `prepare()` (Plan Phase A/B 인계 영역, 사이클 102+ 영역)
- 사이클 83 `_scan_pool_eager_refresh_task` (영역 분리 영속)
- 사이클 95 `_classify_market` (헬퍼 모듈 영역 한정 영속)
- `src/db/stock_master.py` (upsert 영역 영속, 사이클 81 영속)

---

## 7. 회귀 가드 매트릭스 권고

### HIGH 6 (매매 hot path / 시점 race / LMS chain / graceful 영속)

| ID | 가드 영역 | 검증 방법 |
|----|----------|----------|
| H-1 | 매매 hot path 영향 0 (A1) | ~2,800 적재 후 `subscribe_filtered_stocks` 결과 ≤ 50건 영속 (사이클 32 R4 영속) |
| H-2 | 사이클 38 명문화 영속 (A1) | ~2,800 적재해도 매도/익일청산/15:20 강제청산 영향 0 (호출 0건 검증) |
| H-3 | 20:00:05 동시 호출 race 0 (A2) | mock OpenAI 3분 + mock KIS REST 2,800 호출 동시 발화 → 충돌 0건 |
| H-4 | 정산 (20:10) 모의 환경 race 차단 (A2) | mock `KIS_ENV=vts` 환경 600초 타임아웃 → 9분 초과 시 graceful skip + WARNING emit |
| H-5 | KIS LMS chain 차단 (A3) | mock CTPF1002R 2,800 호출 → 50ms sleep × 2,800 ≥140초 (실전) / ≥560초 (모의) |
| H-6 | 사이클 88 G-REJECT 영속 (A3) | ~2,800 적재 영역 변경 0 (영향 0 정적 검증) |

### MEDIUM 6 (시점 / 폐기 / 가시화 / lifecycle)

| ID | 가드 영역 | 검증 방법 |
|----|----------|----------|
| M-1 | 사이클 89 5분 주기 영구 폐기 (Q69=B) | `_universe_eager_refresh_loop` 함수 정의 0건 (정적 grep) + `_universe_eager_refresh_task` 등록 0건 |
| M-2 | fluctuation 영구 폐기 (Q68=A) | `_fetch_fluctuation` 함수 정의 0건 + `_FLUCTUATION_URL` 0건 + `_FLUCTUATION_TR_ID` 0건 |
| M-3 | market_cap KOSPI/KOSDAQ 명시 분리 (A1) | mock `fid_input_iscd="0001"` 호출 → KOSPI 종목 + `="1001"` → KOSDAQ 종목 |
| M-4 | 백그라운드 task lifecycle (A3) | `stop()` 시점 `_full_universe_load_task` cancel 발화 |
| M-5 | 운영 가시화 (`[full_universe_load_summary]` 1행) | 매일 20:00:05 적재 시 1행 emit |
| M-6 | 환경 분리 sleep (A3) | mock `KIS_ENV=real` → 50ms sleep / `KIS_ENV=vts` → 200ms sleep |

### LOW 5 (AST / KST / 통합)

| ID | 가드 영역 | 검증 방법 |
|----|----------|----------|
| L-1 | G-AST1 영구 가드 (사이클 78 답습) | `record_full_universe_load_summary` ↔ `flush_full_universe_load_collector` 호출 사이트 ≥1건 |
| L-2 | G-AST2 영구 가드 (사이클 79 답습) | `_full_universe_load_task` cancel 목록 영속 (`stop()` task_attrs 튜플 + `run_daily()` finally 블록 양쪽) |
| L-3 | KST 영속 (사이클 68) | `_kst.py` 헬퍼 영속 사용 |
| L-4 | 사이클 95 `_classify_market` 영속 | 헬퍼 모듈 영역 한정 영속 (unknown=0 영속) |
| L-5 | KIS MCP 정본 인용 (사이클 98 G-DOC1) | `chk_market_cap.py` + `chk_search_stock_info.py` 정본 100% 인용 (정적 grep) |

**합계**: HIGH 6 + MEDIUM 6 + LOW 5 = **17 회귀 가드 케이스** (사이클 89 답습 17 일치).

---

## 8. 반례 / 한계

### 반례 1 — 신규 IPO 종목 당일 진입 (MEDIUM)

- 시나리오: 당일 IPO 종목 = 전일 적재 영역 부재 = `bfdy_clpr=0` graceful 통과 → 가격필터 단독 안전망 우회.
- 영향: 사이클 31 R6 (`current_price > total_investment`) 안전망 단독 의존.
- **회피**: 사이클 31 R6 영속 영역 (사이클 81 의도 보존) — 신규상장 영구 차단 방지 = 정상 동작. **사이클 102+ 운영자 수동 적재 영역 후속 검토**.

### 반례 2 — KIS API 5xx 응답 폭주 (MEDIUM)

- 시나리오: 2,800 호출 중 일부 시점 KIS API 5xx 응답 폭주 = 사이클 18 60s WARNING dedupe 영속 영역.
- 영향: 사이클 76 retry collector 영속 흡수 영역.
- **회피**: 사이클 18 + 76 영속 매트릭스 영속 + graceful 영속 (사이클 88 G-REJECT 영속) + 운영 가시화 prefix 영속.

### 반례 3 — 모의 환경 정산 (20:10) 직전 9분 적재 미완 (HIGH)

- 시나리오: 모의 환경 = 5건/초 = 2,800 / 5 = 560초 (9분 24초) → 20:09:24 종료 → 정산 (20:10) 직전 36초 마진. **타임아웃 차단 영역**.
- 영향: 사이클 6 정산 영속 영역 위협.
- **회피**: `max_load_seconds=600` (모의) 환경 분리 가드 신설 (graceful skip + WARNING emit) + 정산 (20:10) 영역 race 절대 차단 의무.

### 한계 — fluctuation 폐기 등락률 정보 영역 손실

- **사이클 89 영역 답습**: 등락률 단독 = 모멘텀 시그널이나 작전 함정 영속. fluctuation 폐기 = 등락률 정렬 영역 폐기 영속.
- **`scanner.fetch_rising_stocks` 별도 hook 영속**: ±15%+ 종목 = 별도 hook 영속 (사이클 89 영속).
- **회피**: fluctuation 폐기 = 등락률 정렬 영역 결함 영구 차단 + market_cap = 시가총액 본질 우월 영역 영속.

### 한계 — 사이클 89 5분 주기 적시성 영역 손실

- **사이클 101 = 매일 20:00 일괄 단독**: 적시성 영역 손실 (운영 중 신규 종목 즉시 적재 불가).
- **`[stock_master_age_warning]` 보강**: 7일 이상 = WARNING emit 의무.
- **사이클 102+ 검토**: 운영자 수동 적재 영역 (단발 호출) + 신규 IPO 종목 영역 별도 hook 검토.

---

## 9. 후속 검증 권고 (tdd-engineer / tester)

### tdd-engineer

- Red 단계 17 케이스 (HIGH 6 + MEDIUM 6 + LOW 5) 신설.
- **G-AST1 (사이클 78 답습) + G-AST2 (사이클 79 답습) 반드시 신설** — 미래 신규 collector / task 추가 시 누락 영구 차단.
- **H-3 (20:00:05 동시 호출 race 0) HIGH 우선**: mock OpenAI 3분 + mock KIS REST 2,800 호출 동시 발화 fixture 신설 의무.
- **H-4 (정산 모의 환경 race 차단) HIGH 우선**: mock `KIS_ENV=vts` 환경 600초 타임아웃 + graceful skip + WARNING emit fixture 신설 의무.
- 백그라운드 task lifecycle 검증 (`stop()` 시점 cancel) = 사이클 79 패턴 직접 답습.

### tester

- **D+1 (목) 09:00~10:00 1h verify**:
  - 매일 20:00:05 적재 `[full_universe_load_summary] total=2800 kospi=950 kosdaq=1650 securities=2600 etf=200 fetched=N skipped_ttl=M failed=K elapsed_ms=L` 1행 emit 확인.
  - `stock_master` 총 row 171 → ~2,800 (~16x) 확인.
  - SK스퀘어 (402340) `bfdy_clpr` valid 확인 (~2,800 universe 진입 검증).
  - `[full_universe_load_rate_limit]` 영역 영속 emit (KIS_ENV=real 시 1행 / vts 시 1행).
  - 사이클 89 `_universe_eager_refresh_loop` 호출 0건 (Q69=B 영구 폐기 검증).
  - 사이클 97 `_fetch_fluctuation` 호출 0건 (Q68=A 영구 폐기 검증).

- **D+5 (월) 1주 운영 측정**:
  - `[risk_silent_skip]` (R6) trigger 빈도 변화 (270 → 0~5건/일).
  - `[price_filter_scanner_skip]` 정상 발화 빈도 (사이클 64/65/81 본래 의도 회복 검증).
  - `[price_filter_graceful_pass]` 0건 영속 검증 (~99%+ 적재율).
  - `subscribe_filtered_stocks` 후보 풀 카운트 변화 (~30~50건 영속 검증).
  - KIS API 호출 dup_factor 변화 (사이클 76 영속, 영향 0 예상).
  - WS 41 한도 영향 0 검증 (사이클 32 R4 영속).
  - 매일 20:00:05 적재 5일 연속 성공률 ≥ 99%.

- **D+30 (1개월) 운영 회고**:
  - **반례 1 (신규 IPO 종목) 실측**: `[stock_master_age_warning]` 7일 이상 emit 빈도 측정 + 운영자 수동 적재 영역 후속 사이클 (사이클 102+) 발의 의무.
  - 작전주 차단 실효성 (270 → 0건/일 영속 검증).
  - 후보 풀 6 전략 균형 (momentum/VB/LTV/donchian/BFB/VCP 후보 분포).
  - **Plan Phase A/B 인계 검토**: 사이클 102+ 전략 prepare stock_master 베이스 전환 영역.

---

## 10. 결론

**사이클 101 = 사이클 99 60 ticker 영구 영속 영역 본질 해결 (16x 확장) + 사이클 89 답습 + 사이클 38/32/64/65/81 영속 매트릭스 + fluctuation 영구 폐기 + 사이클 89 5분 주기 영구 폐기 = 단일 해결 영역**. domain-expert 자문 권고 영속 매트릭스 17 케이스 (HIGH 6 + MEDIUM 6 + LOW 5) 신설 의무. **6 전략 매매 hot path 영향 0** (scanner 단계 영역 한정 + Plan Phase A/B 별개 사이클 인계). **사이클 88 G-REJECT-1/2/3 영속 영구 보장** (영역 분리, 영향 0). **사이클 17/18/29/76 LMS chain 영속 매트릭스 영구 보장** (영역 분리 + 5중 안전망).

**A1=매매 hot path 영향 0 (사이클 38/32 영속) / A2=20:00:05 race 0 (외부 API 영역 분리) + 정산 race 환경 분리 가드 신설 / A3=KIS LMS chain 차단 5중 안전망 (50ms + Semaphore 20/s + graceful + 환경 분리 + 운영 가시화) / A4=fluctuation 영구 폐기 (등락률 별도 hook 영속) / A5=사이클 89 영구 폐기 + 적시성 보강 prefix + 사이클 95 `_classify_market` 영속**.

**Phase 2 명세 분해 (team-leader) 인계 = backend-dev Green 단계 진행 가능**.

---

**산출물**: `_workspace/cycle101_domain_consult.md` (본 문서)
**핵심 권고 한 줄**: A1 매매 hot path 영향 0 (사이클 38/32/64/65/81 영속) + A2 20:00:05 race 0 (외부 API 영역 분리) + 정산 모의 환경 600s 타임아웃 가드 신설 + A3 KIS LMS chain 5중 안전망 (50ms + Semaphore 20/s + graceful + 환경 분리 + 가시화) + A4 fluctuation 영구 폐기 (등락률 별도 hook 영속) + A5 사이클 89 영구 폐기 + `[stock_master_age_warning]` 보강 + 사이클 95 `_classify_market` 영속 = HIGH 6 + MEDIUM 6 + LOW 5 = 17 회귀 가드 의무.
