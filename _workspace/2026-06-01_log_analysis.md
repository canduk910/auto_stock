# 2026-06-01 당일자 로그 분석 — 후보 카드

작성: 2026-06-01 (사이클 51 직후) / 분석가: 메인 세션 + Explore 3 / 데이터 원천: `daily_log_reports` (gpt-5.4 / 2026-06-01 20:10 KST INSERT) + Supabase 원시 (`system_logs` · `strategy_funnel_snapshots` · `trade_history` · `positions`).

## 요약

- 자동 리포트 **존재** (findings 6개, severity high 2 / medium 2 / low 2). 핵심 메트릭 자동 집계 — `realized_pnl=26,000원`, `trades_total=4` (VB 4건만 집계 — **실제 trade_history 는 5건**, momentum 064400 SELL 1건 자동 리포트에서 누락).
- **매매 실측**: BUY 2 + SELL 3 (5건 모두 COMPLETED). VB 5/31 BUY → 6/1 15:xx SELL (005930 +23,000 / 035420 +3,000) + momentum 064400 5/29 BUY → 6/1 08:20 KST SELL (+30,100, +26.6%). 보유 0.
- **KIS 거부 폭주**: 064400 매도 거부 (APBK0918/KIOK0320) — **23:00:00 ~ 23:09:53 UTC 10분간 500+ 건**(2건/초). 자동 리포트의 "116건" 은 표면 카운트, 실제 폭주 규모는 5배.
- **WS 결함 prefix**: `level` 컬럼명 부재로 prefix별 카운트 미수집 (분석 도구 결함 — 가시화 카드 V-3 참조).
- **사이클 49 검증 결과**: VCP step 6 통과 = **1건** (시정 작동 확인). 단 step 7 (거래량 수축) 에서 1건 전부 탈락 → step 8 = 0 → **VCP 매매 0건** (사이클 48 BFB/VCP 0매매와 동일 결과, 게이트가 한 단계 뒤로 이동).

## 사이클 49 후속 검증 (핀포인트)

| 항목 | 결과 | 판정 |
|------|------|------|
| VCP step 6 (Pullback 점진 수축) 통과 카운트 | **1건** (00:35/08:12 양쪽 모두) | ✅ 시정 작동 — 사이클 49 회귀 가드 OK |
| VCP step 7 (거래량 수축) 통과 | **0건** (1건 전부 탈락) | ⚠️ 다음 게이트가 막힘 |
| VCP step 8 (최종 prepared) | 0건 | ⚠️ 매수 도달 못함 |
| VCP 첫 매매 발생 | **없음** | (4중 청산 검증 보류 — 다음 영업일) |
| BFB step 6 (거래량 수축) | 0건 (08:12 측정 6건 전부 탈락) | 동일 결함 — BFB 도 같은 게이트에서 막힘 |

→ **사이클 49 핵심 검증은 PASS** (Pullback 게이트 통과 = 1). 그러나 직후 게이트(거래량 수축)에서 BFB/VCP 둘 다 0건 탈락. 다음 사이클 후보.

---

## 후보 카드

### 버그 카드 (즉시 시정)

#### B-1 [CRITICAL] 매도 좀비 폭주 — 가드가 호출 내 재시도만 차단, 외부 재호출은 무방비

> **사이클 52 종결 (2026-06-01)** — `OrderEngine._market_closed_blocked` ticker별 TTL 게이트 + `_compute_next_market_open_kst` + `reset_daily_state` 캡슐화 + 회귀 가드 8 시나리오 (`tests/unit/engine/test_b1_market_closed_zombie_block.py`) + CLAUDE.md 안전규칙 동기화. 백엔드 1766 PASS (1748→+18). tester 프로덕션 배포 가능 판정. 상세: `docs/HARNESS_CHANGELOG.md` 사이클 52 행. 후속 카드 R-1 (`SellRejectionTracker` 단일 정책 객체) / V-1 (실시간 알람) 보존.

**근거**:
- `system_logs` 매도 거부 (장운영시간 외) 064400: **500+건 / 10분간** (2026-05-31T23:00:00 ~ 23:09:53 UTC), 평균 2건/초.
- 23:00:00~07 → 23:00:37~58 → … 매 tick (~0.5s) 마다 `execute_sell` 진입 → `is_market_closed_rejection` 검출 → WARNING ("재시도 중단") + return.
- `order_engine.py:523` 의 가드: 함수 *반환* 만 수행, positions 보존 + 다음 호출 차단 *플래그* 없음. `risk.on_tick` 또는 `_swing_rest_poll_loop` 가 매 tick exit 평가 → 동일 종목에 또 `execute_sell` 진입 → 재폭주.

**영향**: 매매 안전성 *직접* (KIS rate limit 위반 위험 / `system_logs` 폭주로 다른 결함 가시성 저하 / 백엔드 자원 소모). 결국 23:20 시장 정상화 후 매도 체결되어 *손실은 없었지만*, 다음 동일 시나리오에서 KIS 차단 시 손절 자체가 불가능해질 수 있다.

**제안 액션**:
1. `OrderEngine` 에 `_market_closed_blocked: dict[str, datetime]` 추가 — `is_market_closed_rejection` 시 ticker 등록 + TTL (예: KRX 정규시간 09:00 KST 까지).
2. `execute_sell()` 진입 직후 `_market_closed_blocked` 검사 → 등록되어 있고 TTL 미경과면 *조용히 skip* (로그 INFO 1줄). 사이클 30 `_completed_orders` 패턴과 동형.
3. `risk.on_tick` 호출 빈도 자체에 손대지 말고 (다른 종목 영향), `execute_sell` 게이트만 추가.
4. 회귀 가드: `tests/unit/engine/test_b1_market_closed_zombie_block.py` — mock `kis_request` 가 APBK0918 반환 → `execute_sell` 100회 연속 호출해도 KIS 호출은 1회만 발생함을 검증.
5. **CLAUDE.md 핵심 안전규칙** "NXT 매도 거부 좀비 차단" 항목 확장: "*진입 차단* 까지 보장" 명문화.

#### B-2 [HIGH] `next_day_clear_drained` 로그 발화 누락 — drained_success=0 인데 실제 SELL COMPLETED

> **사이클 53/53.1 종결 (2026-06-02)** — `_fetch_logs_in_range` 페이지네이션 (`.range(offset, offset+999)` 루프) + 호출 측 limit=30000 명시. 6/1 재집계 metrics: drained_success=1 정확 산출 (운영 부피 18,435건 fetch). 재집계 사고로 row 임시 손상 → 메인 세션이 metrics-only 복구. 상세: HARNESS_CHANGELOG 2026-06-02 행.

**근거**:
- 자동 리포트 metrics `next_day_clear = {deferred:1, drained_success:0, drained_fail:0}`.
- `trade_history` 에 064400 SELL 2026-05-31T23:20:00 UTC (= 6/1 08:20 KST) COMPLETED, +30,100원. *실제로는 익일청산이 성공*.
- 로그 분석은 `[next_day_clear_drained]…result=success` regex 로 success 카운트 (`log_analysis_engine.py:125`). 해당 prefix 가 SELL 발화 시점에 INSERT 되지 않은 것.
- `scheduler.py:1127` 의 `[next_day_clear_drained]` 발화 경로 — 그러나 064400 은 `_pending_next_day_clear` 에 *없는* 종목이었을 가능성 (momentum 일반 손절 트리거였다면). 그렇다면 자동 리포트의 "deferred=1 / drained=0" 은 *VB 상한가 같은 다른 종목* 의 *진짜 누락*.

**영향**: 익일청산 운영 모니터링 신뢰도 직접 훼손. 다음 시나리오에서 drained_fail 인데 0으로 보일 위험.

**제안 액션**:
1. 정확한 root cause 분리 필요 — (a) 064400 이 `_pending_next_day_clear` 에 등록됐는지 검증 (`[next_day_clear_deferred]` 064400 로그 조회), (b) 다른 종목의 deferred=1 이 drained=0 인지 확인.
2. 만약 (b) 라면 `scheduler.py::_drain_pending_next_day_clear` 의 `result=success` 분기 누락 또는 예외 경로 식별.
3. 064400 의 경우 위 B-1 의 단순 손절 폭주 경로였으면 별건. 다음 사이클에서 검증 데이터로 사용.
4. 회귀 가드: `tests/integration/test_b2_next_day_clear_log_emission.py` — `_drain_pending_next_day_clear` 성공/실패 양 분기에서 prefix 발화 검증.

#### B-3 [MEDIUM] NXT 다운그레이드 폭주 — `stock_master.nxt_tradable=False` 사후 보강 누락

> **사이클 54 종결 (2026-06-03)** — 분석 메모 가설 (사후 보강 누락) *반증* 후 실질 결함 시정. 064400 stock_master `nxt_tradable=False` 이미 저장 확인 (사후 보강 정상). 115건 폭주는 B-1 매도 좀비 부작용 — 사이클 52 가드로 외부 재호출 자동 차단 + 사이클 54 의 `_nxt_downgrade_logged_today` ticker별 1행/일 cap 으로 이중 안전망. 다운그레이드 결정 (`return "KRX"`) 무영향, 로그만 cap. 회귀 가드 4 시나리오 (`tests/unit/engine/test_b3_nxt_downgrade_log_cap.py`). 백엔드 1776 PASS (1772→+4). 상세: `docs/HARNESS_CHANGELOG.md` 사이클 54 행.

**근거**:
- `[nxt_downgrade] 064400 strategy=momentum from=SOR to=KRX reason=nxt_not_tradable` **115건** (자동 리포트 finding 3).
- 사후 보강 (`stock_master.upsert_one(ticker, nxt_tradable=False)`) 이 1회만 작동하면 다음 호출부터 사전 판별로 다운그레이드 자체가 발생하지 않아야 함. 115건 반복은 사후 보강이 *작동 안 함* 또는 *boot 시 캐시 갱신 안 됨* 의 신호.
- 또 다른 ERROR: `[src.engine.order_engine] stock_master.get 실패 (전략 기본 exchange 유지): 064400` 1건 — DB 조회 실패가 동반.

**영향**: 보조적 (이미 다운그레이드 폴백이 작동). 그러나 사이클 32 의 "NXT 거래가능 사전 판별 — `_boot()` eager 갱신" 정책 위반. system_logs 노이즈.

**제안 액션**:
1. `order_engine` 의 NXT 다운그레이드 분기에서 `stock_master.upsert_one(ticker, nxt_tradable=False)` 호출 확인 — 비동기 fire-and-forget 인지, 실패해도 다음 호출 사전 판별이 안 되는 이유.
2. `_boot()` 의 eager 사전 갱신 대상에 `_pending_next_day_clear` 외 *현재 보유 종목* + *현재 evaluate 중 종목* 포함 여부 확인.
3. 회귀 가드: 첫 호출에서 nxt 거부 → upsert_one 호출 → 다음 호출은 *사전 판별로 KRX 직행* 검증.

#### B-4 [MEDIUM] 자동 리포트 trade_metrics 1건 누락 — 064400 SELL 미집계

> **사이클 53 종결 (2026-06-02)** — `get_trades_in_range` 의 timestamp 문자열에 `+09:00` KST suffix 명시. 6/1 재집계 metrics: trades_total=5 + realized_pnl=56,100 (064400 SELL UTC 23:20 포함 정합). 상세: HARNESS_CHANGELOG 2026-06-02 행.

**근거**:
- 자동 리포트 `trade_metrics.trades_total=4 / by_strategy={volatility_breakout:4}`.
- 실제 `trade_history` 6/1 데이터: **5건** (064400 SELL momentum +30,100 포함).
- 064400 SELL `timestamp=2026-05-31T23:20:00 UTC` = 6/1 08:20 KST → KST 6/1 영업일 정상 포함되어야 함.
- `log_analysis_engine` 의 trade 윈도우가 KST 09:00 시작 / UTC 자정 시작 등 *경계 결함* 의심 가능성.

**영향**: 일일 PnL 누락 (오늘은 +30,100원 빠짐 = realized_pnl 실제는 56,100원). 자동 리포트 신뢰도.

**제안 액션**:
1. `log_analysis_engine.py` 의 trade 윈도우 정의 확인 (`target_date` → UTC/KST 변환).
2. 회귀 가드: 23:20 UTC (= 익일 08:20 KST) timestamp 의 trade 가 KST `target_date` 에 포함됨을 검증.

---

### 리팩토링 카드 (구조 개선, 사이클 누적)

#### R-1 [HIGH] OrderEngine sell 분기 — 거부 분류 + 차단 플래그 + 폴백 통일

> **사이클 55 종결 (2026-06-03)** — `SellRejectionTracker` 단일 정책 객체 도입 (`src/engine/sell_rejection.py` 271L) + `OrderEngine` 4 분기 위임 + 호환 layer property (`_market_closed_blocked` / `_market_closed_blocked_logged_today`). domain-expert 자문 Q1~Q5 RECOMMEND 전부 적용 — 행위 변경 3종 (Q1 2단계 TTL / Q2 NXT 폴백 실패 익일 청산 전환 / Q3 `[positions_reconciliation]` + get_balance 1회). 회귀 가드 36 시나리오 (신규 27 + 사이클 52 보존 9). 백엔드 1776 → 1804 PASS (+28). tester 프로덕션 배포 가능 판정. 사이클 52/54 후속 + V-1 history deque 인프라 사전 도입. 상세: `docs/HARNESS_CHANGELOG.md` 사이클 55 행 + `_workspace/cycle55_R1_design_card.md`.

**근거**: order_engine.py 의 sell 경로에 분류 분기 (is_market_closed_rejection / is_insufficient_quantity / is_insufficient_cash / is_market_order_disallowed) 가 각각 *호출 내* 가드만 가짐. B-1 이 드러난 후 *외부 재호출* 까지 책임지는 단일 *차단 정책 객체* (`SellRejectionTracker`) 가 필요.

**행위 보존**: 기존 가드의 *호출 내* 행위 유지 + 진입 직후 tracker 검사 추가. 매매 hot path 라 risk: HIGH.

**관련 기존 카드**: refactor/2026-05-22_review.md 카드 #1 (HIGH scheduler 분해) — 사이클 51 boot 추출이 1단계. R-1 은 같은 카드 #1 의 *order_engine* 측면. 사실 *별도 카드* 로 발주하는 게 적절 (scheduler 분해와 독립).

#### R-2 [MEDIUM] funnel 단계 hook 미배선 전략 — momentum / VB / LTV step=99 단일 row

**근거**: strategy_funnel_snapshots 6/1 데이터:
- BFB / Donchian / VCP: step 1~8 + 99 (정상)
- momentum / VB / LTV: step=99 단일 row (단계 hook 미적용)

**영향**: 사이클 48 시정의 BFB/VCP funnel 가시성과 비대칭. 사이클 39 의 "단계별 자동 hook" 정책이 *3 전략에만* 적용됨. 사이클 51 boot 추출 후속 작업 후보.

**행위 보존**: hook 만 추가, 매수 로직 무변경. risk: LOW (조회용 메타데이터).

#### R-3 [MEDIUM] api_metrics 집계 범위 — quote_pool 500 누락

**근거**: 자동 리포트 finding 5 가 정확히 짚음. WARNING 로그에 `[quote_pool] HTTP 500 (attempt 1/3)` 1건 있는데 `api_metrics.http_5xx=0`. quote_pool 경로가 `get_request_metrics()` 계측 대상에서 빠짐.

**제안**: `src/api/base.py` 의 `_request_via_quote_pool` 에 메트릭 INSERT 추가 — main path 와 동일 카운터 (path/status/retries) 사용.

---

### 가시화 카드 (진단/메트릭 부족)

#### V-1 [P1] 매도 거부 폭주 알람 — 시간당 거부 N건 이상 즉시 알림

> **사이클 57 종결 (2026-06-04)** — `SellRejectionTracker._append_history` 공통 진입점 + `_maybe_emit_burst_alarm` 10분 5건 임계 + 30분 cooldown per-ticker + CRITICAL safe_write_log fire-and-forget. 메시지 포맷 = tracker 독립 최소 (KST + ticker + 거부 코드 분포 + 마지막 메시지). R-1 (사이클 55) deque(maxlen=20) + 56 DailyEmitCap 2 종 사전 인프라 직계 활용 — 사이클 52 B-1 10분 500건 폭주의 *실시간 감지 안전망* 완성. 회귀 가드 15 시나리오 (`tests/unit/engine/test_v1_rejection_alarm.py`). 백엔드 1819 → 1834 PASS (+15) / 회귀 0. 상세: `docs/HARNESS_CHANGELOG.md` 사이클 57 행.

**근거**: B-1 의 10분 500건 폭주가 *실시간 운영자 알람 없이* 다음 날 20:10 자동 리포트에서야 발견됨. CLAUDE.md 의 "stale_silent_inactive 시간당 cap" 패턴 같은 *우선 알림* 필요.

**제안**: `[kis_rejection]` per-ticker 시간당 5건 초과 시 CRITICAL 레벨 system_logs INSERT + `system_config.notification_enabled` 시 외부 채널 (Slack/email — 추후).

#### V-2 [P2] daily_log_reports OpenAI 모델/토큰 비용 메타 표시

**근거**: model=gpt-5.4 만 기록. 사용 토큰/비용/소요시간 미기록. 운영 비용 추적 불가.

**제안**: `daily_log_reports` 컬럼 `usage_tokens int, latency_ms int, cost_estimate_krw decimal` 추가 — migration 새 사이클.

#### V-3 [P2] system_logs 컬럼명 일관성 — `level` vs `log_level`

**근거**: 분석 도구에서 `select('level')` → "column does not exist" 에러. 실제 컬럼은 다른 이름 (`log_level` 추정). `src/db/system_logs.py::get_logs` 의 `log_level` 인자 — 컬럼명과 1:1 매핑 확인 후 *내부* 함수에 컬럼명 상수화 또는 sql view 추가.

#### V-4 [P3] strategy_funnel_snapshots 단계별 *탈락 사유 sample* 활용도

**근거**: 6/1 BFB 08:12 step 6 (거래량 수축) survived=0 excluded=6 — 어떤 6 종목이 *왜* 탈락했는지 `excluded_sample` JSONB 가 답을 가짐. 현재 read 도구는 단계 카운트만 추출, sample 무시.

**제안**: `frontend/src/pages/StrategyFunnel.tsx` 의 *탈락 사유 정밀 추적* 카드 사용 빈도 점검 + 백엔드에 step 7/8 의 *직전 게이트 직후* 후보 종목 1~3건 inspect API 추가.

---

## 신규 vs 기존 카드 매핑

| 카드 | 기존 사이클/카드 관련 |
|------|---------------------|
| B-1 | 신규 (CLAUDE.md "NXT 매도 거부 좀비 차단" 정책의 *진입 차단* 확장) |
| B-2 | 신규 |
| B-3 | 사이클 32 정책 (eager 사전 갱신) 검증 누적 |
| B-4 | 신규 (자동 리포트 자체 결함) |
| R-1 | refactor/2026-05-22_review.md 카드 #1 (HIGH scheduler 분해) 사이클 51 후속의 *order_engine 측면* |
| R-2 | 사이클 39 (funnel 단계 hook) 의 3 전략 누락 |
| R-3 | 자동 리포트 finding 5 (수렴) |
| V-1 | 신규 |
| V-2 | 신규 |
| V-3 | 신규 (분석 도구 측 결함) |
| V-4 | 사이클 41 (탈락 사유 정밀 추적) 활용 강화 |

---

## 다음 사이클 발주 추천 우선순위

1. **B-1 (CRITICAL)** — 매도 좀비 폭주 차단. team-leader → tdd-engineer Red → backend-dev Green. 회귀 가드 + CLAUDE.md 안전규칙 동기화 필수.
2. **B-2 (HIGH)** — 진단 추가 (B-1 시정 전 *원인 분리* 검증으로 활용 가능).
3. **R-1 (HIGH)** — B-1 시정 직후 구조 정리. domain-expert 자문 (매매 행위 영향 평가) 동반 권장.

B-3 / B-4 / R-2 / V-1~V-4 는 후속 사이클 또는 도메인 자문 결과에 따라.

---

## 잔여 카드 우선순위 재정렬 (사이클 54 종결 후 — 2026-06-03)

사이클 52 (B-1) + 53 (B-2/B-4) + 53.1 (운영 부피 cap) + 54 (B-3) 종결로 **버그 카드 전량 소진**. 다음 사이클 후보 우선순위:

| 순위 | 카드 | 등급 | 영역 | 메모 |
|------|------|------|------|------|
| 1 | **R-1** | HIGH | 리팩토링 | `SellRejectionTracker` 단일 정책 객체 — 사이클 52 B-1 + 사이클 54 B-3 시정 직후 *구조 정리*. order_engine sell 경로의 거부 분류 + 차단 플래그 + 폴백 통일. 3개 emit cap set (`_risk_silent_skip_logged_today` 사이클 31 / `_market_closed_blocked_logged_today` 사이클 52 / `_nxt_downgrade_logged_today` 사이클 54) 동형 패턴 누적 → 통합 추상화 후보. domain-expert 자문 (매매 행위 영향 평가) 동반 필수. 매매 hot path 라 risk: HIGH |
| 2 | **V-1** | P1 | 가시화 | 매도 거부 폭주 실시간 알람 — `[kis_rejection]` per-ticker 시간당 5건 초과 시 CRITICAL system_logs + (추후 외부 채널). B-1 의 10분 500건 폭주 *실시간 감지* 안전망 |
| 3 | **V-2** | P2 | 가시화 | `daily_log_reports` OpenAI 모델/토큰/비용 메타 컬럼 추가 (migration). 운영 비용 추적 + 사이클 53.1 재집계 사고 같은 시나리오에서 OPENAI_API_KEY 부재/실패 사유 정량 기록 가능 |
| 4 | **R-2** | MEDIUM | 리팩토링 | momentum/VB/LTV funnel 단계 hook 추가 (사이클 39 의 3 전략 누락 보완). 사이클 47 FUNNEL_STAGES + `_record_funnel_pipeline_step` 위임 패턴 재활용 |
| 5 | **R-3** | MEDIUM | 리팩토링 | `_request_via_quote_pool` api_metrics 계측 추가 (quote_pool 500 누락) |
| 6 | **V-3** | P2 | 가시화 | system_logs 컬럼명 일관성 (`level` vs `log_level`) — 분석 도구 측 결함 동시 해소 |
| 7 | **V-4** | P3 | 가시화 | strategy_funnel_snapshots 탈락 사유 sample 활용도 (BFB/VCP step 6/7 직후 후보 종목 inspect API) |

**권고**: 다음 사이클은 (1) **R-1** (사이클 52/54 emit cap 패턴 통합 + B-1 구조 정리, domain-expert 자문 동반) 우선 발주가 정합. 또는 (2) **refactor-review 트리거** (사이클 49→54 누적 6회, 3개 emit cap set 통합 추상화 + scheduler 분해 후속 단계 동반 검토) 사용자 결정.

---

## 잔여 카드 우선순위 재정렬 (사이클 55 R-1 종결 후 — 2026-06-03)

사이클 52 (B-1) + 53 (B-2/B-4) + 53.1 (운영 부피 cap) + 54 (B-3) + 55 (R-1) 종결로 **버그 카드 + R-1 HIGH 소진**. R-1 제거 후 다음 사이클 후보 우선순위:

| 순위 | 카드 | 등급 | 영역 | 메모 |
|------|------|------|------|------|
| 1 | **V-1** | P1 | 가시화 | 매도 거부 폭주 실시간 알람 — `SellRejectionTracker.get_recent_rejections()` deque(maxlen=20) **사이클 55 사전 도입** 인프라 위에 알람 hook 추가. `[kis_rejection]` per-ticker 시간당 5건 초과 시 CRITICAL system_logs + (추후 외부 채널). B-1 의 10분 500건 폭주 *실시간 감지* 안전망. R-1 종결로 즉시 발주 가능 |
| 2 | **V-2** | P2 | 가시화 | `daily_log_reports` OpenAI 모델/토큰/비용 메타 컬럼 추가 (migration). 운영 비용 추적 + 사이클 53.1 재집계 사고 같은 시나리오에서 OPENAI_API_KEY 부재/실패 사유 정량 기록 가능 |
| 3 | **R-2** | MEDIUM | 리팩토링 | momentum/VB/LTV funnel 단계 hook 추가 (사이클 39 의 3 전략 누락 보완). 사이클 47 FUNNEL_STAGES + `_record_funnel_pipeline_step` 위임 패턴 재활용 |
| 4 | **R-3** | MEDIUM | 리팩토링 | `_request_via_quote_pool` api_metrics 계측 추가 (quote_pool 500 누락) |
| 5 | **V-3** | P2 | 가시화 | system_logs 컬럼명 일관성 (`level` vs `log_level`) — 분석 도구 측 결함 동시 해소 |
| 6 | **V-4** | P3 | 가시화 | strategy_funnel_snapshots 탈락 사유 sample 활용도 (BFB/VCP step 6/7 직후 후보 종목 inspect API) |

**refactor-review 트리거 권고 (사이클 49→55 누적 7회 — 임계 5회 *2배 초과*)**:
- 3개 emit cap set (`_risk_silent_skip_logged_today` 사이클 31 / `_market_closed_blocked_logged_today` 사이클 52→55 tracker 흡수 / `_nxt_downgrade_logged_today` 사이클 54) → `DailyEmitCap` 제네릭 추상화 (사이클 56 후보 — `_nxt_downgrade_logged_today` 잔존 1건 흡수)
- scheduler 분해 후속 단계 (`stale_manager` / `swing_manager` / `settlement_manager`) — 사이클 51 boot_manager 추출 후속
- 광범위 예외절 누적 (`order_engine.py:1059` 사이클 52 식별 + `:1150` 사이클 55 새 식별) — refactor 카드 누적

**권고**: 다음 사이클 진입 *전* **refactor-review 발주** 후 V-1 P1 진입이 정합.

---

## 잔여 카드 우선순위 재정렬 (사이클 56 종결 후 — 2026-06-04)

> 사이클 56 종결 (refactor-review 카드 #1 emit cap 통합 4 단계 + 카드 #5 safe_write_log 헬퍼). 백엔드 1804 → 1819 PASS. 신규 모듈 `src/engine/daily_emit_cap.py` (89L) + `src/db/system_logs.py::safe_write_log`. 3 emit cap set 모두 `DailyEmitCap` 통합 완성. **사이클 49→56 누적 8 사이클 = refactor-review 채택분 진행 완료**.

**V-1 P1 즉시 발주 가능** — 사이클 55 R-1 `deque(maxlen=20)` 인프라 + 사이클 56 `DailyEmitCap` 알람 cap 패턴 *2 종 사전 준비 완성*. V-1 알람 hook 은 (a) `SellRejectionTracker.get_recent_rejections()` 시간당 카운트 + (b) ticker별 알람 발화 cap (`DailyEmitCap[str]` 또는 시간당 cap 신규) 직계 활용 가능.

| 순위 | 카드 | 등급 | 영역 | 메모 |
|------|------|------|------|------|
| **1** | **V-1** | **P1** | 가시화 | **R-1 deque + 사이클 56 DailyEmitCap 인프라 직계 활용** — 매도 거부 폭주 실시간 알람. team-leader 우선 권고 |
| 2 | refactor #2 | HIGH | 리팩토링 | scheduler 분해 1단계 stale_manager 추출 (-1,000L). domain-expert 자문 필수. 사이클 51 boot_manager 패턴 답습 |
| 3 | V-2 | P2 | 가시화 | daily_log_reports OpenAI 메타 컬럼 |
| 4 | refactor #3 | HIGH | 리팩토링 | settlement_manager 추출 (-376L), 카드 #2 후속 |
| 5 | R-2 | MEDIUM | 리팩토링 | momentum/VB/LTV funnel hook |
| 6 | refactor #4 | MEDIUM | 리팩토링 | swing_manager 추출 (-400L) |
| 7 | R-3 | MEDIUM | 리팩토링 | api_metrics quote_pool 500 |
| 8 | refactor #6 | MEDIUM | 리팩토링 | KIS API except 좁히기 (KIS MCP 의존) |
| 9 | V-3 | P2 | 가시화 | system_logs 컬럼명 일관성 |
| 10 | V-4 | P3 | 가시화 | strategy_funnel 탈락 사유 sample |

**권고**: 다음 사이클은 **V-1 P1** (R-1 + DailyEmitCap 인프라 직계 활용, 매매 안전성 critical 가시화) 또는 **refactor #2 HIGH** (scheduler 분해 본격 진행) 우선 발주. 사용자 결정 대기.

---

## 잔여 카드 우선순위 재정렬 (사이클 57 V-1 종결 후 — 2026-06-04)

> 사이클 57 종결 (V-1 P1 매도 거부 폭주 실시간 알람). `src/engine/sell_rejection.py` +97L (`_append_history` 공통 진입점 + `_maybe_emit_burst_alarm` 10분 5건 임계 + 30분 cooldown + CRITICAL safe_write_log fire-and-forget). 회귀 가드 15 시나리오 (`tests/unit/engine/test_v1_rejection_alarm.py`). 백엔드 1819 → 1834 PASS (+15). **V-1 P1 카드 소진** — sell rejection 4 사이클 완결 (52 진입 차단 → 55 분류 통합 + TTL → 56 cap 추상화 → 57 실시간 알람).

**V-2 P2 가시화 카드 1순위 승격** — V-1 종결 후 분석 메모 잔여 가시화 카드 최고 우선순위. `daily_log_reports` 운영 비용 메타 (OpenAI 모델/토큰/cost_estimate_krw + latency_ms) 컬럼 추가 = migration 단일 카드. 사이클 53.1 재집계 사고 같은 시나리오에서 OPENAI_API_KEY 부재/실패 사유 정량 기록 가능.

| 순위 | 카드 | 등급 | 영역 | 메모 |
|------|------|------|------|------|
| **1** | **V-2** | **P2** | 가시화 | **V-1 종결 후 가시화 카드 최고 우선** — `daily_log_reports` OpenAI 모델/토큰/cost_estimate_krw/latency_ms 컬럼 migration. 운영 비용 추적 + 사이클 53.1 재집계 사고 같은 OPENAI_API_KEY 결함 정량 기록 |
| 2 | refactor #2 | HIGH | 리팩토링 | scheduler 분해 1단계 stale_manager 추출 (-1,000L). domain-expert 자문 필수. 사이클 51 boot_manager 패턴 답습 |
| 3 | refactor #3 | HIGH | 리팩토링 | settlement_manager 추출 (-376L), 카드 #2 후속 |
| 4 | R-2 | MEDIUM | 리팩토링 | momentum/VB/LTV funnel hook (사이클 39 의 3 전략 누락 보완). 사이클 47 FUNNEL_STAGES + `_record_funnel_pipeline_step` 위임 패턴 재활용 |
| 5 | refactor #4 | MEDIUM | 리팩토링 | swing_manager 추출 (-400L) |
| 6 | R-3 | MEDIUM | 리팩토링 | `_request_via_quote_pool` api_metrics 계측 추가 (quote_pool 500 누락) |
| 7 | refactor #6 | MEDIUM | 리팩토링 | KIS API except 좁히기 (KIS MCP 의존) |
| 8 | V-3 | P2 | 가시화 | system_logs 컬럼명 일관성 (`level` vs `log_level`) — 분석 도구 측 결함 동시 해소 |
| 9 | V-4 | P3 | 가시화 | strategy_funnel_snapshots 탈락 사유 sample 활용도 (BFB/VCP step 6/7 직후 후보 종목 inspect API) |

**운영 모니터링 권고 (사이클 58 진입 전 점검)**:
- V-1 알람 발화 임계 (10분 5건) 가 운영 1~2 영업일 후 *과민/둔감* 여부 평가.
- **과민** (정상 운영에서 알람 빈번 발화) → 임계 상향 (10분 10건) 검토.
- **둔감** (사이클 52 같은 사고에서 알람 늦게 발화) → 임계 하향 또는 윈도우 단축 (5분).
- 평가 SQL: `SELECT COUNT(*), MIN(occurred_at_kst), MAX(occurred_at_kst) FROM system_logs WHERE level='CRITICAL' AND message LIKE '[매도거부폭주]%' AND occurred_at >= now()-interval '7 days'`.
- 평가 결과 따라 사이클 58+ 에서 domain-expert 자문 + 임계 조정 (`ALARM_WINDOW_SECONDS` / `ALARM_THRESHOLD` 상수 단순 변경).

**권고**: 다음 사이클은 (a) **V-2 P2** (단일 migration, 운영 비용 추적 즉시 가용) 또는 (b) **refactor #2 HIGH** (scheduler 분해 본격 진행, domain-expert 자문 동반). V-2 가 *최소 본질 단일 책임 카드* 라 사이클 58 우선 권고. 사용자 결정 대기.

