# 사이클 83 Phase 2 — domain-expert 자문 (옵션 1 `_scan_loop` 후보 풀 eager refresh 영역 확장)

**발주**: team-leader (사이클 83 Phase 2)
**의뢰 일시**: 2026-06-09 (화) KST
**자문 위급도**: **MEDIUM** (매수 진입 hot path 인접, 자금 손실 영역 아님, 가드 우회 영구 차단 의도)
**선행**: `_workspace/cycle83_phase1_diagnosis.md` (Phase 1 진단 + Q1~Q6 사용자 결정 채택)
**채택 결정**: Q1=B / Q2=C / Q3=B / Q6=B (사이클 84 분리)

---

## 1. 질문 요약

사이클 81 시정 (`prdy_clpr` → `bfdy_clpr`) 후 잔존 결함 = `stock_master` 운영 적재 14건 한정 → 후보 풀 ~90% 가 `bfdy_clpr <= 0` graceful 통과 → 가격필터 사실상 우회. SK스퀘어 (402340) 류 미적재 ticker = 사이클 31 R6 silent_skip 마지막 안전망 단독 의존. **`subscribe_filtered_stocks` 진입점 hook + 백그라운드 task + 24h TTL/50ms sleep 가드 채택 안전성 검증** + 5건 자문 의제 (A1~A5).

---

## 2. 트레이더 시각

### 시장 가설
- KIS CTPF1002R (주식기본조회) = 시세성 아님, 종목 메타 (BFDY_CLPR/시가총액/거래정지 등). RPS 부담 = REST 일반 호출 등급 (시세 push 대비 1/10 이하).
- 24h TTL 의 트레이더 본능: 종목 메타 = 영업일 단위 변동 (액면분할/거래정지/상장폐지). 24h TTL = "전일 종가는 오늘 하루 동안 변하지 않는다" 본능과 정합. 사이클 56-E 의 60s TTL (시세 영역) 과는 결이 다름.
- 영업일 후보 풀 30~50 ticker × 24h TTL = **2 사이클째부터 KIS 호출 0건** (캐시 hit 100%). 영업일 첫 진입 (07:50 _boot 직후 + 09:00 시작) 만 cold start ~1.5~2.5s 직렬 부담 → 백그라운드 task (Q2=C) 로 latency 0 흡수 정합.

### 실전 사례
- 사이클 17 OPSP0002 backoff = WebSocket 구독 거부 시 50ms sleep + dict 등록 → KIS 안정. REST `_request` 도 동일 패턴 (50ms sleep = 1 RPS 미만 보장).
- 사이클 56-E 60s TTL = 시세 캐시 (조건검색 결과). 본 사이클 24h TTL = 종목 메타 캐시 → **다른 TTL 정책 정합** (사이클 56-E 답습은 *TTL 가드 패턴* 만 답습, *TTL 값* 은 종목 메타 특성 따라 24h 유지).
- 사이클 32 R4 `inquire_ccnl` = 종목당 1회 (stale 의심 시점만). 본 사이클 eager refresh = 종목당 1회 (24h TTL 신규 ticker 만) → **합산 KIS RPS 충돌 없음** (시간대 분산 + 신규 ticker 영역 분리).

### 위험 시나리오
- **R-1 (LOW)**: KIS CTPF1002R 일시 5xx → graceful skip (사이클 76 dedupe 영속) → 다음 5분 사이클 재시도. 1 사이클 지연 영향 = 가격필터 1 사이클 우회 (~5분), R6 안전망 단독 의존 → SK스퀘어 류 1회 진입 위험. 허용 가능 (사이클 31 R6 영속).
- **R-2 (MEDIUM)**: 백그라운드 task cancel 누락 → 사이클 79 패턴 답습 위반 → 좀비 task. `stop()` 시점 cancel + `connect/disconnect` lifecycle 정합 필수.
- **R-3 (LOW)**: 첫 영업일 cold start (07:50 _boot) 시 후보 풀 30~50 ticker × 50ms = 1.5~2.5s 백그라운드 직렬. `_boot()` 차단 0 (Q2=C) → latency 영향 0.

---

## 3. 정량 권고

### A1 — KIS RPS 부담 평가 (위급도 LOW)
- **권고**: Q1=B + Q3=B 채택 안전.
- **근거**:
  - 영업일 누적 = cold start ~30~50 ticker × 1회 + 24h TTL hit 이후 0건 = **일 ~30~50 호출** (5분 주기 ~10~12회 호출 가정 무의미, TTL hit 으로 실제 호출 = 신규 ticker 만).
  - 50ms sleep 가드 = 최대 20 RPS 상한 → KIS REST 한도 (~50 RPS) 절반 미만.
  - 기존 `_eager_refresh_stock_master_for_held_positions` 14 ticker 비교 시 약 2~3배 부담이나 24h TTL 로 영업일 2 사이클째부터 균등 흡수.
- **추가 가드 권고**: 백그라운드 task 내부 `[scan_pool_eager_refresh] tickers=N kis_calls=M skipped_cached=K elapsed_ms=L` 1행 emit (사이클 74 aggregation 패턴 답습, 5분 윈도우 1회) — KIS 호출 실측 가시화 의무.

### A2 — `_scan_loop` 5분 race 안전성 (위급도 MEDIUM)
- **권고**: Q2=C 백그라운드 task lifecycle 안전 패턴 = **사이클 79 영구 가드 직접 답습 의무**.
- **근거**:
  - 신규 task attribute `_scan_pool_eager_refresh_task` 도입 시 → `scheduler.py::stop()` task_attrs 튜플 (L866) + `run_daily()` `finally` 블록 task_attrs 튜플 (L742) **양쪽 동행 추가** (사이클 79 G-AST1 영역 답습).
  - 사이클 79 AST 가드 (`create_task` 패턴 attribute = stop task_attrs 튜플 차집합 = ∅) 자동 검출 → 누락 시 Red 단계 FAIL 보장.
  - 5분 주기 `_scan_loop` 동시 호출 race: 백그라운드 task 자체 idempotent (24h TTL fresh skip) → 동시 진입 안전. 단 동일 ticker 동시 KIS 호출 가능성 → **`asyncio.Lock` per ticker 불필요** (TTL fresh ratio ~95% + 신규 ticker 동시 진입 확률 극소).
- **추가 가드 권고**: 사이클 78 `[swing_rest_poll_summary]` 패턴 답습 = 5분 윈도우 종료 후 collector `len == 0` freezegun 회귀 가드 1 케이스 신설 (메모리 leak 차단).

### A3 — 사이클 38 명문화 영속 보장 (위급도 LOW)
- **권고**: 영속 의무 영구 가드 매핑 — **위반 가능성 0 확정**.
- **근거**:
  - `subscribe_filtered_stocks` 진입점 = **매수 진입 *전*** WS 구독 단계 (사이클 38 명문화 영역). eager refresh = `stock_master` 메타 갱신만, `tradable_boards` 분기 검사 0건 = 매도/손절/Trailing/익일청산/15:20 강제청산 영역 무관.
  - 사이클 64 Q1 옵션 D `_collect_protected_tickers_for_scanner` 3중 안전망 영속 (보유/익일청산/_pending_buy_orders 합집합) → eager refresh 가 보유 ticker 의 `bfdy_clpr` 갱신해도 가격필터 graceful 통과 영속 (사이클 64 명문화).
- **AST 영구 가드 권고**: `_scan_pool_eager_refresh` 본체 (or 헬퍼) 가 `tradable_boards` keyword 참조 0건 정적 검증 (사이클 38 영속 자동 차단).

### A4 — 사이클 31 R6 silent_skip 마지막 안전망 영속 보장 (위급도 LOW)
- **권고**: 영속 의무 + trigger 빈도 감소 예상 정량.
- **근거**:
  - R6 (`RiskManager.on_tick` 의 `current_price > total_investment` skip) = `risk` 모듈 매수 평가 단계 (구독 *이후*). 본 사이클 시정 = scanner 단계 (구독 *전*) → **분리 영역 영속**.
  - eager refresh 효과 = `bfdy_clpr` valid 비율 ~10% → ~95%+ (24h TTL 안정화 후) → `_apply_price_filter` 정상 차단 ~50건/일 (사이클 64/65 본래 의도 영역). R6 trigger 빈도 = SK스퀘어 류 270건/일 → 0~10건/일 (잔존 = 사용자 설정 price_filter_max 미설정 + 신규 ticker 1 사이클 지연 영역).
  - R6 안전망 단독 의존 → 2중 (가격필터 + R6) 으로 회복 = 사이클 64 명문화 의도 회복.
- **영속 가드 권고**: R6 emit dedupe (사이클 31 영속) 변경 0 + R6 trigger count daily summary 운영 측정 (사이클 84 push 후 1주 모니터링).

### A5 — Q2 옵션 C 백그라운드 task 부작용 평가 (위급도 MEDIUM)
- **권고**: 사이클 74 + 사이클 79 영구 가드 패턴 답습 **3중 의무**.
- **근거**:
  - 사이클 74 `_api_recovered_collector_task` + 사이클 79 cancel 영구 가드 = lifecycle (connect/disconnect) + `_running=False` 체크 + 마지막 flush 1회 (사이클 42/78 답습).
  - flush 잔여 ticker = collector dict (`{ticker: KIS_call_count}`) `stop()` 시점 1회 emit + clear → 메모리 leak 영구 차단.
  - 사이클 78 G-AST1 (`record_*` 정의 모듈의 대응 `flush_*` 호출 사이트 ≥1건 정적 검증) 패턴 답습 → 본 사이클 신규 `_record_scan_pool_eager` / `_flush_scan_pool_eager_collector` 도입 시 동일 AST 가드 신설.
- **회귀 가드 매트릭스 (Q4 권고)**:
  - **HIGH 3**: G-AST1 (stop task_attrs 튜플 누락 차단, 사이클 79 영속) / G-AST2 (사이클 38 `tradable_boards` 참조 0건) / G-LC1 (lifecycle cancel + setattr None freezegun, 사이클 79 답습).
  - **MEDIUM 4**: G-TT1 (24h TTL fresh skip count) / G-TT2 (50ms sleep ≥1회 호출) / G-FL1 (`stop()` 시점 마지막 flush 1회) / G-ML1 (5분 윈도우 종료 후 collector `len == 0`).
  - **LOW 3**: G-OP1 (운영 시나리오 SK스퀘어 graceful → eager refresh → 차단 freezegun) / G-OP2 (`[scan_pool_eager_refresh]` 1행 emit) / G-RT1 (R6 trigger 빈도 감소 회귀, 사이클 84 측정 후 추가).

---

## 4. 현 코드와의 정합성

- **사이클 38 명문화 영속**: 위반 가능성 0 (A3 확정).
- **사이클 31 R6 영속**: 분리 영역, 영속 (A4 확정).
- **사이클 64 Q1 옵션 D 3중 안전망**: 보유 ticker 보호 영속 — eager refresh 가 보유 ticker `bfdy_clpr` 갱신해도 `_collect_protected_tickers_for_scanner` 영속 영역으로 가격필터 graceful 통과 영속.
- **사이클 32 R4 universe guard**: 충돌 없음 (Phase 1 §3 Q5 확정) — `inquire_ccnl` (시세 영역) 과 CTPF1002R (메타 영역) 분리.
- **사이클 79 cancel 영구 가드**: 신규 task attribute 도입 = G-AST1 자동 검출 → 누락 영구 차단.

**충돌 항목 없음**.

---

## 5. 사용자 결정 검증 (Q1~Q6)

| 결정 | 사용자 채택 | 자문 권고 | 일치 |
|------|------------|----------|------|
| Q1 시정 사이트 | B (진입점 hook) | B | **일치** |
| Q2 시점 | C (백그라운드 task) | C + A2/A5 lifecycle 패턴 의무 | **일치 + 의무 가드 추가** |
| Q3 Rate Limit | B (24h TTL + 50ms sleep) | B | **일치** |
| Q6 push 시점 | B (사이클 84 분리) | B | **일치** (안전 우선 + 1주 운영 모니터링) |

**자문 권고 = 사용자 결정 전부 일치**. 추가 의무 = A2/A5 영구 가드 매트릭스 10 케이스 (HIGH 3 + MEDIUM 4 + LOW 3).

---

## 6. 사이클 84 push 시점 검증 시나리오

**시점**: 2026-06-09 (화) NXT 애프터 (15:30~) 또는 익일 (수) 07:50 _boot 전.

**검증 시나리오**:
1. **즉시 (push 직후)**: 백엔드 단위 PASS + AST G-AST1 ∅ 검증 + `_scan_pool_eager_refresh_task` 시작/cancel lifecycle freezegun PASS.
2. **D+1 (수) 09:00~10:00 1h tester verify**:
   - `[scan_pool_eager_refresh] tickers=N kis_calls=M skipped_cached=K` 5분 윈도우 emit ≥10건 (10시까지).
   - `stock_master` 총 row 14 → 30~50+ (영업일 후보 풀 영역).
   - SK스퀘어 (402340) `bfdy_clpr` valid 확인 (운영 적재 검증).
3. **D+5 (월) 1주 운영 측정**:
   - `[risk_silent_skip]` (R6) 270건/일 → 0~10건/일 (A4 정량 검증).
   - `[price_filter_scanner_skip]` 0~50건/일 (사이클 64/65 본래 의도 회복 검증).
   - KIS API 호출 `api` dup_factor 변화 0 (사이클 76 영속).

---

## 7. 반례 / 한계

- **반례 1**: 후보 풀이 200+ ticker 폭주 (사이클 33 BFB+VCP fix 회귀 가능성) → 영업일 첫 cold start 200 × 50ms = 10s 백그라운드 직렬. Q2=C 백그라운드라 차단 0이나 10s 동안 가격필터 우회 = R6 단독 의존 일시 확장. → **허용** (사이클 31 R6 영속 영역, 10s 한정).
- **반례 2**: KIS CTPF1002R 응답이 `bfdy_clpr=0` (실제 신규상장 첫 영업일) → 24h TTL 잔존 → graceful 통과 영속. → **허용** (사이클 64 Q2 옵션 A 명문화 영속, 신규상장 영구 차단 방지 의도).
- **한계**: 사용자 `price_filter_max` 미설정 (디폴트 0 = OFF) 시 본 사이클 시정 효과 0 → 사용자 설정 의존. UI Settings 권장값 마커 (1억/5억/10억) 영속 (사이클 65).

---

## 8. 후속 검증 권고 (tdd-engineer / tester)

- **tdd-engineer**: Red 단계 10 케이스 (HIGH 3 + MEDIUM 4 + LOW 3) 신설. AST G-AST1 (사이클 79 답습) + G-AST2 (사이클 38 영속) **반드시 신설** — 미래 신규 task 추가 시 cancel 누락 + `tradable_boards` 위반 silent 영구 차단.
- **tester**: D+1 (수) 09:00~10:00 1h verify 의무 (시나리오 A/B/C 결합) + D+5 (월) 1주 운영 측정 (R6 trigger 빈도 + 가격필터 정상 발화).

---

## 결론

**옵션 1 채택 = 안전 (HIGH 카드 1, MEDIUM 카드 4, LOW 카드 3 영구 가드 매트릭스 10 케이스 신설 의무)**. 사용자 결정 Q1=B / Q2=C / Q3=B / Q6=B = 자문 권고 전부 일치. 사이클 38 명문화 + 사이클 31 R6 + 사이클 64 Q1 옵션 D + 사이클 79 cancel 영구 가드 영속 보장. 사이클 84 push 후 1주 운영 측정 의무.
