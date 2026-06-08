# 사이클 83 — Phase 1 진단 보고서

**발주 카드**: #82-A (MEDIUM 신규, 사용자 결정 옵션 1 채택)
**발주 일시**: 2026-06-09 (화) 07:15 KST
**진단자**: team-leader
**선행 사이클**: 사이클 82 진단 (`_workspace/cycle82_c2_diagnosis.md`) — 진짜 결함 = "stock_master eager refresh 영역의 후보 풀 미커버" 확정.

---

## 1. 운영 시간대 가드 (진행 결정)

- 현재 시각 = **2026-06-09 (화) 07:15 KST** — `TIME_AUTO_START=07:45` / `TIME_BOOT=07:50` 직전.
- KRX 메인 (09:00~15:30) 진입 *이전* 1시간 35분 마진 확보.
- TDD Red→Green→Refactor 사이클 + 회귀 가드 작성 + tester verify 시간 부족 가능 → **진행하되 push 시점은 NXT 애프터 (15:30~) 또는 익일 _boot 전 (07:50 이전) 으로 미룬다.**
- 결정: **Phase 1~2 진단/명세는 진행, Red/Green 코드 변경은 별도 사이클 (또는 본 사이클 후반 NXT 애프터) 로 미루는 옵션도 열어 둠** — Q6 사용자 결정 의제.

---

## 2. Phase 1-A 결함 사이트 식별 (코드 grep 실측)

### 2.1 `_scan_loop` 정의 + 호출 chain

- 정의: `src/engine/scheduler.py:1985` `_scan_loop(self)` — 5분 주기 (`SCAN_INTERVAL`)
- 시작 사이트 2곳:
  - `scheduler.py:592` `self._scan_task = asyncio.create_task(self._scan_loop())` — 09:30 정상 진입
  - `scheduler.py:620` 동일 (NXT 애프터 보드 전환 후 유지, 사이클 26)
- 5분 주기 진입 시 매번 `scan_stocks()` + `_collect_breakout_tickers()` + 보유 합집합 → `subscribe_filtered_stocks(...)` 호출 (L2008).

### 2.2 `subscribe_filtered_stocks` 4 호출 사이트 (사이클 82 진단 확정)

| # | 위치 | 시점 / 컨텍스트 | tickers + extra 규모 |
|---|------|-----------------|---------------------|
| (1) | `scheduler.py:521` | 07:55 `TIME_PRESUBSCRIBE` — 사전 구독 (보유 + 익일청산 + VB/LTV/donchian 후보) | 보통 10~30 |
| (2) | `scheduler.py:562` | 09:00~09:30 중간 부팅 (서버 재기동 등) | 보통 10~30 |
| (3) | `scheduler.py:582` | 09:30 `TIME_SCAN_START` 첫 진입 모멘텀 스캔 통합 구독 | 모멘텀+돌파+스윙 = 30~50 |
| (4) | `scheduler.py:2008` | **`_scan_loop` 5분 주기** (09:30~15:20) — HIGH hot path | 30~50 (영업일 누적) |

### 2.3 `stock_master.upsert_from_kis` 기존 호출자 (eager refresh 패턴 재사용 가능 영역)

grep 결과 = `stock_master.upsert_one` (실제 함수명, `upsert_from_kis` 는 인지 오류 — `upsert_one(StockBasics)` 가 진실):

- `src/engine/order_engine.py:631` — 매도 거부 사후 보강 (`nxt_tradable=False`)
- `src/engine/scheduler.py:1872` — `_eager_refresh_stock_master_for_held_positions()` 본체 내부 (보유+익일청산 합집합 sequential)
- 기타 호출자 없음 = **eager refresh 패턴은 _boot() 1 사이트 단일** (사이클 82 진단 일치)

### 2.4 사이클 82 진단 부수 확정

- stock_master 총 14건 적재 (운영 실측 2026-06-08), `bfdy_clpr` 13건 valid.
- `_apply_price_filter` (`src/engine/scanner.py:166`) 가 `bfdy_clpr <= 0` (= stock_master 미적재) 시 **graceful 통과** (L173-176, Q2 옵션 A "신규 상장 영구 차단 방지").
- 후보 풀 ~90% 가 stock_master 미적재 → 가격필터 사실상 우회 = 사이클 81 시정 효과 stock_master 적재 영역에 결정적 의존.

---

## 3. Phase 2 사용자 결정 의제 (Q1~Q5 옵션 A/B/C)

### Q1 (HIGH) — 시정 사이트 범위
- **옵션 A** `_scan_loop` 단일 (사이트 4만) — 5분 주기 hot path 우선, 진입점 가장 영향 큼. 사전 구독/중간 부팅 미커버 = 09:00~09:30 영역 회피 위험.
- **옵션 B** `subscribe_filtered_stocks` 진입점 내부 단일 hook (사이클 64 `_apply_price_filter` 패턴 답습) — 4 사이트 호출자 무변경 + 신규 진입점 추가 시 누락 차단. **권장**.
- **옵션 C** scheduler 4 호출자 모두 직접 호출 — 명시적이나 누락 위험 + 사이클 64 hotfix (H-2/G-3) 영구 가드 패턴 위반.

### Q2 (HIGH) — eager refresh 시점
- **옵션 A** 구독 *전* (`_apply_price_filter` *전*) — 가격필터 정확성 보장, 단 KIS 호출 후 구독 = latency 증가 (영업일 후보 풀 30~50건 × inquire_stock_basics ≈ 1.5~2.5s 직렬).
- **옵션 B** 구독 *후* 첫 tick 시점 — latency 0이나 가격필터는 *다음 5분 사이클*부터 효과 (1 사이클 지연 = 5분).
- **옵션 C** 백그라운드 task (`asyncio.create_task`, fire-and-forget) — 구독 차단 0 + 가격필터 2 사이클째부터 정확. **권장 (Q3 결합)**.

### Q3 (MEDIUM) — KIS Rate Limit 가드
- 사이클 56-E TTL 답습 가능 = `_eager_refresh_stock_master_for_held_positions` 본체 패턴 (`is_stale(ticker, max_age_hours=24)` fresh skip + sequential await + 종목당 50ms sleep 권고).
- **옵션 A** 24h TTL 단독 — 신규 ticker 만 KIS 호출 (영업일 ~30건 × 50ms = 1.5s, 충분).
- **옵션 B** 24h TTL + 종목당 50ms sleep — 사이클 17 OPSP0002 backoff 영역 답습 (안전).
- **옵션 C** 24h TTL + 10건 cap (사이클 37 패턴) — 부담 최소화, 단 미커버 ticker = 다음 5분 사이클 자연 흡수.

### Q4 (MEDIUM) — 회귀 가드 매트릭스
- 사이클 64/65 패턴 답습 권고:
  - HIGH: Q1 옵션 B 진입점 호출 AST + Q2 옵션 C task 발화 AST + 사이클 32 R4 universe guard 충돌 검증
  - MEDIUM: 신규 헬퍼 `_eager_refresh_stock_master_for_scan_pool` 24h TTL 동작 + KIS 호출 카운트 freezegun
  - LOW: 신규 ticker 운영 시나리오 (SK스퀘어 graceful 통과 → eager refresh 후 차단)

### Q5 (HIGH) — 사이클 32 R4 universe guard 충돌 가능성
- 사이클 32 R4 (`_evaluate_universe_guard`) = stale>5 + 저거래량 자동 unsubscribe.
- 본 사이클 신규 eager refresh = 구독 *전* (or 직후) ticker 의 stock_master 갱신만 → universe guard 와 **충돌 없음** (universe guard 는 *구독 이후* tick 누적 감시 영역).
- 단 사이클 32 R4 의 `inquire_ccnl` 호출과 KIS Rate Limit 합산 부담 검증 필요 → domain-expert 자문 의제.

### Q6 (사용자 결정 의제 추가) — push 시점
- **옵션 A** 본 사이클 내 push (NXT 애프터 15:30~ or 익일 07:50 전) — 정합성 + 회귀 가드 + tester verify 모두 본 사이클 완료.
- **옵션 B** 사이클 84 분리 (Phase 1~2 명세만 본 사이클, Red/Green 별도 사이클) — 안전 우선.

---

## 4. domain-expert 자문 트리거 (의무)

옵션 1 = MEDIUM + 매수 진입 hot path 인접 (`subscribe_filtered_stocks` → 가격필터 → WS 구독) → **domain-expert 자문 의무**. 자문 의제 정리:

1. **eager refresh 호출 부담**: 영업일 후보 풀 30~50건 × inquire_stock_basics (KIS CTPF1002R) RPS 측정 + 24h TTL 효과 (재실행 시 0건) + 사이클 32 R4 `inquire_ccnl` 합산 KIS Rate Limit 안전.
2. **`_scan_loop` 5분 race 안전성**: 보드 전환 mutex (KRX↔NXT 사이클 26) + 동시 호출 (`_scan_loop` 5분 + K stale watcher 120s + `_evaluate_universe_guard`) 합산 KIS 호출 충돌 + 60s TTL 캐시 (사이클 56-E) 답습 가능 여부.
3. **사이클 38 명문화 (`tradable_boards` 매수 진입 전용) 영속**: 매도/손절/Trailing/익일청산/15:20 강제청산 영향 0 보장 — `_apply_price_filter` 영역 = scanner 진입점 전 단계 (사이클 64 명문화) 영속.
4. **사이클 31 R6 silent_skip 마지막 안전망 영속**: `risk.on_tick` 의 `current_price > total_investment` 분기 (RiskManager) 영속 — 본 사이클 시정 = scanner 단계 (구독 진입 전), R6 = risk 단계 (매수 평가) 영역 분리, 영향 0 확정.
5. **Q2 옵션 C (백그라운드 task) 부작용**: fire-and-forget eager refresh 중 `_scan_loop` 다음 사이클 진입 race + 메모리 누수 (task cancel 누락 = 사이클 79 `_api_recovered_collector_task` 패턴 답습 검증).

---

## 5. 산출물

- 본 진단 메모 = `_workspace/cycle83_phase1_diagnosis.md` (영구 기록)
- 다음 단계: 사용자 Q1~Q6 결정 → domain-expert 자문 발주 → Red 명세 → backend-dev Green → tester verify

**team-leader 권장 디폴트** (사용자 의사 부재 시): Q1=B / Q2=C / Q3=B / Q4 표준 매트릭스 / Q5 충돌 없음 확정 / Q6=B (사이클 84 분리, 안전 우선).
