# 사이클 63 Phase 2-A3 — domain-expert 행위 영향 평가 회신

> **작성자**: domain-expert (2026-06-05 16:40 KST)
> **수신자**: team-leader
> **자문 의뢰서**: `_workspace/cycle63_phase2A3_domain_consult.md`
> **설계 카드**: `_workspace/cycle63_phase2A3_design_card.md`
> **선행 자문**: `_workspace/cycle60_phase2A_domain_response.md` (§Q7 영속 의무 본 자문의 발주 근거)
> **위험 등급**: **HIGH (CRITICAL 등급에 근접)** — K stale watcher *핵심 본체*, 영구 hot path 360 회/일, KIS LMS/앱키 정지 chain 직접
> **자문 시점 시장 상태**: 2026-06-05 (금) 16:40 KST = NXT 애프터 진입 직후. 본 자문 자체는 운영 영향 0

---

## 핵심 결론 한 줄

**4 의제 모두 RECOMMEND (사이클 60 A1 / 사이클 61 A2 답습 + 1 패턴 변경 권고) — 단, *월요일 1h verify 시 사고 재현 사전 시나리오 도입 의무* + *Phase 2-A1 보존된 lazy import 빚 (`_emit_stale_session_detail` wrapper 경유)* 청산 권고**.

3 단계 분할의 마지막 단계인 A3 는 사이클 60 응답서가 *주말 push + 1h tester verify* 를 영속 의무로 박아둔 영역. A1/A2 의 누적 패턴이 견고해 위임 자체의 위험은 낮으나, K stale watcher 본체가 *시간 윈도우 상태* (force_retry 5분 cooldown + 12회/h cap + 60분 슬라이딩 윈도우) 의 *작성-읽기 race* 를 가지므로 회귀 가드 25 케이스의 HIGH 18 건은 *예외 없이 freezegun + 결정적 순서 보장* 의무.

---

## Q1 — K stale watcher 8 단계 호출 시점/순서 영향 평가

**답변**: **RECOMMEND** (사이클 60/61 답습 가능, 단 *5 단계 (high_tickers 구성) 위치 명시* 의무)

**근거 (트레이더 시각)**:

8 단계 중 *순서 보존이 결정적인* 단계는 **4 (force_retry 평가) → 5 (high_tickers 구성) → 6/7 (unsubscribe+subscribe) → 8 (`_emit_stale_session_detail`)** 4 단계. 나머지 1~3 단계는 read-only 또는 단순 비교라 위임 후에도 자연 보존된다.

- **5 단계 `high_tickers` 구성** = 사이클 29-R3 우선순위 분리의 *심장*. `registry.all()` positions 와 `_pending_next_day_clear` 를 *순회 시작 전 한 번에 합집합* 으로 만들어야 한다 — 만약 stale_manager 함수 내부에서 *for-loop 안에서* 매 종목마다 재구성하면 (a) 성능 저하 + (b) `_pending_next_day_clear` 가 동일 사이클 내 변경되면 결정 비결정성 발생. 본체 L2516~L2529 의 `try/except` 4 중 가드 위치 그대로 유지가 의무.

- **6/7 단계 `unsubscribe → 50ms sleep → subscribe`** = KIS 측 Rate Limit 보호 (사이클 17 KIS 공식 답변 인용 "다수 요청 시 LMS + 앱정보 이용중지"). 위임 후에도 50ms sleep 이 절대 빠지면 안 된다. 4 의제 1번 (호출 *순서* 보존) 의 핵심.

- **4 단계 force_retry 평가** = 사이클 29-R1 의 *영구 stale 무한 skip 결함* 차단 본체. `_stale_last_resubscribe_at[ticker]` 부재 → `age=float("inf")` 처리 → 즉시 1회 시도 분기가 *영구 stale 의심 첫 진입* 의 안전선. 위임 후에도 `hasattr` 가드 그대로 유지 의무 (테스트 `__new__` 호환).

- **8 단계 `_emit_stale_session_detail`** = Q4 에서 별도 다룸.

**트레이드오프**:
- 채택 시 비용: 4 단계 순서 보존 회귀 가드 (카테고리 A 의 wrapper 4 케이스 + 카테고리 I 의 우선순위 3 케이스 = 7 케이스로 충분)
- 채택 효과: 사이클 29 005935 사고 재발 영구 차단 + KIS LMS chain 사전 차단

**구현 가이드** (backend-dev):

1. **Q1-G1 (회귀 가드 카테고리 A 보강)**: stale_manager.check_and_resubscribe_stale 함수 내부에서 8 단계 호출 순서를 *시그니처 주석* 으로 명시 (`# Step 1~8` 라벨). 향후 수정자가 순서 깨뜨릴 가능성 차단.
2. **Q1-G2**: 5 단계 `high_tickers` 구성 위치 = **for-loop 시작 *전*** (단일 구성 + 순회 중 재구성 금지). `_resubscribe_stale_priority` 의 L2738~L2746 패턴 답습 (이미 정상).
3. **Q1-G3 (force_retry timing 보존)**: 4 단계의 `datetime.now(_KST_TZ)` 두 군데 호출 (L2552 + L2566) 이 *서로 다른 시각* 일 수 있음을 회귀 테스트가 freezegun 으로 검증. 위임 후에도 `from src.engine.scanner import KST_TZ as _KST_TZ` 가 stale_manager 함수 내부에서 동일하게 import 되어야 함.
4. **Q1-G4 (카운터 리셋 `is` 동일성)**: `self._stale_retry_count[ticker] = 0` (L2601) 이 위임 후에도 `scheduler._stale_retry_count` property 경유 동일 dict 갱신. 사이클 60 A1 응답서 §Q3 답습 (5 상수 `is` 동일성 패턴) — `assert id(scheduler._stale_state.retry_count) == id(scheduler._stale_retry_count)` 검증 케이스 1 건 (C 카테고리 기존 3 케이스에 흡수).

**위험 평가**: **HIGH** — 순서 깨지면 KIS LMS chain 직접. 단, 회귀 가드 7 케이스 + AST 정적 가드로 *증명 가능* 영역.

---

## Q2 — 우선순위 분리 (HIGH+bypass=True / LOW+bypass=False) 행위 보존

**답변**: **RECOMMEND** (사이클 29-R3 핵심 규칙, 풀 API 인터페이스 무변경 위임)

**근거 (트레이더 시각)**:

사이클 29-R3 의 실측 데이터 (main=25 → main=2, 편중 73% → 5%) 는 *보유 005935 silent inactive 사고가 자동 회복된* 결정적 증거다. 트레이더 관점에서 우선순위 분리는 **"보유 종목은 무슨 일이 있어도 메인 41 한도 안에 끌어놓는다"** 는 *손절 평가 latency 의 최후 보루* 다. 4 중 안전망의 *공통 분모* 가 바로 이 우선순위 분리 — `_resubscribe_stale_priority` (5분 우선) 도 동일 패턴, K stale watcher (120s) 도 동일 패턴.

위임 후 *유일한 위험* 은 (a) `high_tickers` 구성 위치가 잘못 옮겨가 매 종목마다 재구성되거나 (b) `bypass_limit=True` 인자 누락 가능성. 풀 API (`kis_ws_pool.subscribe(priority=..., bypass_limit=...)`) 자체는 *불변* 이므로 stale_manager 함수가 *그대로 전달* 만 하면 위험 0.

**트레이드오프**:
- 채택 시 비용: 카테고리 I 회귀 가드 3 케이스 (positions / next_day_clear / 그 외 후보) 전수 freezegun 필수 (freezegun 의무 아님, 단 결정적 순서 보장)
- 채택 효과: 사이클 28 silent inactive 사고 회복 메커니즘 영속 + 보유 종목 손절 평가 latency 최소화

**구현 가이드**:

1. **Q2-G1 (high_tickers 구성 함수 내부 위치)**: `stale_manager.check_and_resubscribe_stale` 의 *for-loop 시작 직전 단일 구성* (L2516~L2529 와 동일 패턴). 함수 시작점 ~5 줄 안에 배치 → 가독성 + 결정성 보장.
2. **Q2-G2 (`try/except` 4 중 가드 위치 보존)**: `registry.all()` 미주입 인스턴스 보호의 `try/except` 패턴은 `getattr(scheduler, "registry", None)` 대신 *현재 `try/except` 패턴 그대로* 유지 권고. 이유: `getattr` 폴백은 *None 반환* 으로 silent 실패하나 `try/except` 는 *예외 발생 시점에 로그 가능* 영역. K stale watcher 의 *영구 hot path 360 회/일* 특성상 *silent 실패가 더 위험*. 단, 본 자문은 사이클 60 A1 패턴 답습이므로 기존 `try/except` 보존이 안전 — 사이클 60 응답서 §Q1 *9 property 외부 접근 grep 권고* 영속.
3. **Q2-G3 (`bypass_limit=True` 인자 그대로 전달)**: 풀 API 인터페이스 무변경. stale_manager 함수가 *수정 0* 으로 그대로 전달. AST 정적 가드 (D 카테고리 2 케이스) 가 자동 검증.
4. **Q2-G4 (메인 편중 회귀 검증)**: tester 1h verify 단계 권고 — `/api/realtime/subscriptions` 의 `session_distribution` 응답으로 **메인 편중 비율** 모니터링. 사이클 28/29-R3 실측 대비 회귀 시 즉시 hotfix 의무.

**위험 평가**: **HIGH** — 우선순위 분리 깨지면 사이클 28 silent inactive 사고 (메인 fresh=0 stale=11) 재발. 단, 풀 API 무변경 + 회귀 가드 3 케이스 + 1h verify 로 *증명 가능* 영역.

---

## Q3 — 사이클 29 005935 사고 패턴 시뮬레이션

**답변**: **RECOMMEND** (8 step 시뮬레이션 회귀 가드 카테고리 H 4 케이스 + 1h verify 사전 시나리오 도입 의무)

**근거 (트레이더 시각)**:

8 step 시뮬레이션은 *트레이더 본능 + 코드 결함의 교차점* 을 검증하는 핵심 시나리오. T+11min 의 retry=5 마지막 정상 분기 → T+13min 의 retry=6 force_retry 분기 *전환 순간* 이 영구 잔류 결함의 진입점이다. T+17min 의 강제 재시도 성공 + 카운터 리셋이 *자연 회복* 의 끝점.

K stale watcher 의 *시간 윈도우 상태* (force_retry 5분 cooldown + 12회/h cap + 60분 슬라이딩 윈도우) 는 위임 함수가 scheduler 객체의 dict 를 *읽고-쓰기* 하는 패턴인데, 이 패턴은 freezegun + property layer `is` 동일성으로 검증 가능. 위임 hop 추가의 latency 영향 (~0.001ms) 은 분 단위 timing 에 *완전 무영향* — Q3 의제 2번 명확히 답.

다만 **사고 재현 사전 시나리오** 가 1h verify 단계에 *반드시 추가* 되어야 한다. 사이클 60 응답서 §Q7 (3 가지 본질 차이) 의 *결함 영향 시간 5~15 분 안에 KIS 앱키 정지 chain* 위험이 A3 의 본질. 자연 발생 stale 만 기다리는 monitoring 은 결함을 *놓칠 수 있다*.

**트레이드오프**:
- 채택 시 비용: 카테고리 H 4 케이스 freezegun 필수 + 1h verify 사고 재현 시나리오 2 종 (자연 발생 stale + 인위 stale 주입) 작성 + tester 1h 운영 환경 monitoring 강도 ↑
- 채택 효과: 사이클 29 사고 chain 영구 차단 증명 + KIS LMS chain 사전 차단 증명

**구현 가이드**:

1. **Q3-G1 (8 step 시뮬레이션 freezegun 케이스)**: 카테고리 H 4 케이스를 다음 시나리오로 매핑:
   - **H(a)** `_stale_last_resubscribe_at` 부재 시 즉시 1회 발화 → `age=float("inf")` 분기 검증
   - **H(b)** age >= 300s 시 발화 + 카운터 리셋 (0) → T+17min 시점 검증
   - **H(c)** age < 300s 시 skip → T+13min/T+15min 시점 검증
   - **H(d)** 시간당 12회 cap 초과 시 `[stale_force_retry_cap]` WARNING → 60분 슬라이딩 윈도우 12회 도달 검증
2. **Q3-G2 (보유 005935 vs `_pending_next_day_clear` 동등 보장)**: 카테고리 I 의 2 케이스 (positions 소속 / next_day_clear 소속) 가 HIGH+bypass=True 분기 통과 검증. K stale watcher + `_resubscribe_stale_priority` 양쪽 모두 동일 검증.
3. **Q3-G3 (latency 영향 무관 증명)**: 위임 hop 추가의 ~0.001ms latency 가 8 step 시뮬레이션 timing (분 단위) 에 *완전 무영향* — `freezegun.freeze_time(...)` 으로 시간 통제 시 wrapper hop 의 wall clock 영향 0. 별도 회귀 가드 불요.
4. **Q3-G4 (1h verify 사고 재현 사전 시나리오 — 신규 권고)**: 월요일 09:00~10:00 verify 시 *2 종* 시나리오 권고:
   - **시나리오 A (자연 발생 monitoring)**: 1h 동안 K stale watcher 5 사이클 (120s × 5 = 10min × 6 = 60min, ~30 사이클) 의 stale 발생 종목·force_retry 발화·cap 도달 *모두 로그 정합성* 모니터링. 자연 발생 0 건이면 시나리오 B 발화.
   - **시나리오 B (인위 stale 주입)**: tester 가 `_stale_retry_count` dict 에 임의 종목 6 카운트 + `_stale_last_resubscribe_at` 부재로 설정 → 다음 사이클 발화 시 `age=inf` 분기 진입 검증. 단 *운영 환경 영향 0 으로 격리* (테스트 종목만, 보유/익일청산 제외). 검증 후 즉시 `_stale_retry_count[테스트종목] = 0` 리셋.

   시나리오 B 가 위험하면 시나리오 A 만으로 한정 — 1h 동안 stale 발생 종목 0 건이면 *추가 검증 사이클* 발주 권고.

**위험 평가**: **HIGH** — 사고 재현 검증 누락 시 운영 회귀 발견 늦어짐. 단, freezegun + 1h verify 2 시나리오로 *증명 가능* 영역.

---

## Q4 — `_emit_stale_session_detail` wrapper 위임 vs 모듈 함수 직접 호출

**답변**: **CONSIDER B (모듈 함수 직접 호출 권고)** — 사이클 60 응답서 §Q7 본질 차이 + 사이클 61 backend-dev Green 패턴 + lazy import 빚 청산 의도 종합

**근거 (트레이더 시각 + 패턴 일관성)**:

이 의제는 *순수 패턴 일관성* vs *lazy import 빚 청산* 의 트레이드오프다. 사이클 60 A1 의 wrapper 분리 의도는 *외부 호출자 (scheduler 메서드 호출 패턴)* 가 깨지지 않게 하는 것이었지만, **A3 의 호출자는 자기 자신 (stale_manager 내부)** 이라는 본질적 차이가 있다. 외부 호출자 (예: `risk.on_tick` 또는 진단 라우트) 는 여전히 `scheduler._emit_stale_session_detail(...)` wrapper 를 사용하고, *모듈 내부 호출만* 직접 함수 호출로 단축하는 것이 **사이클 61 A2 패턴** (예: `_build_session_subscription_view` 가 `STALE_FRESHNESS_SECS` 직접 사용으로 lazy import 1 줄 제거) 와 *완벽히 같은 결* 이다.

선택지 A (wrapper 경유) 의 1 hop 추가는 운영 latency 영향 0 (μs 단위) 이지만, **lazy import 빚** 의 누적 위험이 더 크다. 사이클 61 응답서가 명시했듯 lazy import 는 *static analysis 가드 (AST 정적 의존성 역전)* 의 빈틈을 만든다. stale_manager 함수가 *자기 모듈 내부 함수를 호출* 하는데 *scheduler wrapper 를 거치는* 패턴은 명백히 잘못된 의존성 — *순환 import 위험* 의 잠재적 진입점이다.

다만 **사이클 60 A1 backend-dev Green 의 `_refresh_stale_ccnl_cache` 본체가 `self._evict_expired_ccnl` 우회 → `evict_expired_ccnl(scheduler, ...)` 직접 호출 패턴** 이 이미 *선례* 다. 본 의제는 그 선례의 *명시적 확장* — A3 가 사이클 60 패턴을 *답습하지 않고* 확장하는 *유일한 영역* 임을 인지.

**트레이드오프**:
- 채택 시 비용: backend-dev 가 `_check_and_resubscribe_stale` 본체의 L2662 `self._emit_stale_session_detail(...)` 호출을 `emit_stale_session_detail(scheduler, ...)` 로 변경 (1 줄, lazy import 1 줄 추가 — `from src.engine import stale_manager` 또는 이미 같은 파일 내라면 import 불요)
- 채택 효과: lazy import 빚 1 건 청산 + 사이클 61 backend-dev Green 패턴 일관성 + 향후 사이클 64+ 통합 cleanup loop 도입 시 stale_manager 내부 호출 그래프 자연 일관

**구현 가이드**:

1. **Q4-G1 (선택지 B 채택 시 구현)**: stale_manager.py 내부의 `check_and_resubscribe_stale` 본체에서:
   ```python
   # 사이클 63 A3 — 사이클 60 wrapper hop 단축, 모듈 내부 직접 호출
   emit_stale_session_detail(scheduler, stale_tickers, now)
   ```
   같은 파일 내 함수이므로 import 자체 불요 (`emit_stale_session_detail` 은 이미 stale_manager.py L154 정의됨).
2. **Q4-G2 (scheduler.py wrapper 보존)**: `scheduler._emit_stale_session_detail` wrapper L2678~L2683 은 *그대로 유지* — 외부 호출자 (예: 향후 진단 라우트가 직접 호출할 가능성) 호환 보장. 사이클 60 A1 wrapper 의도 그대로.
3. **Q4-G3 (회귀 가드 추가)**: 카테고리 A 의 wrapper 4 케이스 중 1 케이스를 *외부 호출자 호환* 으로 추가 — `scheduler._emit_stale_session_detail(...)` 호출 시에도 정상 동작 검증. *(현재 설계 카드 A 카테고리 4 케이스에 이미 포함됨)*
4. **Q4-G4 (사이클 60 응답서 §Q7 영속 의무)**: A3 가 사이클 60 패턴을 *답습하지 않는 유일한 영역* 이므로, `_workspace/cycle60_phase2A_domain_response.md` §Q7 의 *3 가지 본질 차이* 가 본 결정의 근거임을 명시 — sync-docs 단계의 HARNESS_CHANGELOG 사이클 63 행에 *Q4 lazy import 빚 청산* 명시 의무.

**위험 평가**: **LOW** — 외부 호출자 인터페이스 무변경 + 내부 1 hop 단축. 채택 안 함 (A 유지) 도 운영 영향 0 — 단, 사이클 64+ 통합 cleanup loop 도입 시 *추가 청산 필요* 영역.

---

## Q5 — 추가 발의 (team-leader 가 놓친 위험 영역)

### Q5-1 — 사이클 62 가격 필터 운영 데이터 축적 전 A3 추출 시점 영향

**답변**: **무관 (영향 0 확인)**

**근거**:
사이클 62 가격 필터 영역은 *매수 진입 게이트* (`risk.on_tick` → `check_buy_signal` 직전) 이고, A3 K stale watcher 영역은 *시세 구독 보장* (WebSocket 4 중 안전망) 이다. **호출 그래프 완전 분리** — 가격 필터는 `system_config.get_price_filter()` + `scanner.ticker_prev_close` 의존, K stale watcher 는 `kis_ws_pool` + `scanner.ticker_last_tick` 의존. 공유 자원 0.

운영 데이터 축적 전 추출이라도 *행위 보존 refactor* 이므로 가격 필터 운영 데이터 정합성 영향 0. 별도 회귀 가드 불요.

**위험 평가**: **무관 (영향 0)**

### Q5-2 — A3 후 stale_manager.py 비대화 (731L → ~1,053L) → sub-module 분해 시점

**답변**: **CONSIDER (별도 카드 발의, 사이클 64+ 적정)**

**근거 (트레이더 시각)**:

stale_manager.py 1,053L 는 단일 모듈로 *읽기 가능 한계* 에 근접. 사이클 51 boot_manager.py (305L) / 사이클 55 sell_rejection.py (~400L) / 사이클 48 stale_tracker.py (~150L) 와 비교 시 4배 이상 큼. 다만 **A3 까지의 누적 추출이 *의미 있는 단위* 로 끝나므로** A3 직후 sub-module 분해는 *행위 보존 검증 부담 중복* — 1h verify 통과 + 1 주 운영 검증 후 별도 카드 발의 권고.

**제안 sub-module 분해 청사진** (별도 카드, 사이클 64+):

| sub-module | 함수 | 라인 (대략) | 위험 |
|---|---|---|---|
| `stale_diagnostics.py` | `build_session_subscription_view` / `emit_stale_session_detail` / `refresh_stale_ccnl_cache` / `evict_expired_ccnl` / `prune_force_retry_history` | ~275L | LOW (진단 read-only) |
| `stale_session_recovery.py` | `detect_silent_inactive_sessions` / `force_reconnect_session` | ~155L | HIGH (KIS LMS chain) |
| `stale_universe_guard.py` | `delta_unsubscribe_dropped` / `evaluate_universe_guard` | ~170L | MEDIUM (보유/익일청산 보호) |
| `stale_watcher_core.py` | `check_and_resubscribe_stale` / `resubscribe_stale_priority` | ~322L | **HIGH (K stale watcher 핵심)** |

A3 까지 누적된 *9 함수 + 10 상수* 가 *3+1 sub-module* 로 명확히 분리됨 — 운영 검증 후 발의 권고.

**위험 평가**: **MEDIUM** — A3 직후 sub-module 분해는 부담 중복. 1 주 운영 검증 후 사이클 64+ 별도 카드 발의 권고.

### Q5-3 — `_resubscribe_stale_priority` 의 `sorted` 결정성 vs K stale watcher 의 stale_tickers 정렬 일관성

**답변**: **RECOMMEND (회귀 가드 카테고리 K 2 케이스로 충분)**

**근거**:

`_check_and_resubscribe_stale` L2491 + `_resubscribe_stale_priority` L2730 모두 `sorted(...)` 결정적 순서 보장 사용. 위임 후에도 *둘 다 같은 패턴 유지* 의무 — 향후 누군가 `set` 변환 또는 `dict.items()` 비결정 순서로 바꾸면 회귀 가드 K 카테고리 2 케이스가 자동 검증.

`cap=10` 적용 시 `sorted` 결정성이 *어느 종목이 우선 재구독되는지* 결정 — 트레이더 본능으로는 *보유 종목 (HIGH) 우선 + 종목코드 ascending* 이 자연스러운데, 현재 코드는 *종목코드 ascending 만* (priority 분리는 `cap` 적용 *후*). **이는 잠재적 결함** — `cap=10` 인 상황에서 종목코드가 작은 LOW 후보 10개가 모두 채워지면 HIGH 종목 (보유) 이 우선 재구독 안 됨.

**구현 가이드**:

1. **Q5-3-G1 (회귀 가드 K 카테고리 확인)**: `cap=10` 적용 시 HIGH 종목 우선 보장 여부 회귀 가드 1 케이스 추가 권고. *현재 코드 결함이라면 별도 카드 발의 의무*.
2. **Q5-3-G2 (현재 코드 결함 확인 권고)**: backend-dev 가 Green 단계에서 `_resubscribe_stale_priority` 의 cap 적용 위치 확인 — `targets = stale_tickers[:cap]` (L2748) 이 *priority 분리 전* 적용되므로 위 우려가 *실재함*. 별도 사이클 64 카드 #5 발의 권고: "cap=10 시 HIGH 종목 우선 보장 로직 추가".

**위험 평가**: **MEDIUM** — 현재 코드 결함 가능성 발견. 본 A3 카드 범위 밖 (행위 보존), 별도 카드 발의 의무.

---

## 종합 권고 요약 (team-leader 채택 결정 시 참조)

| 의제 | 권고 | 위험 | 채택 시 추가 작업 |
|---|---|---|---|
| **Q1** 8 단계 호출 순서 | **RECOMMEND** | HIGH | 회귀 가드 카테고리 A 4 + I 3 = 7 케이스 (현재 설계 카드 25 케이스에 포함) + 8 단계 순서 주석 명시 |
| **Q2** 우선순위 분리 보존 | **RECOMMEND** | HIGH | 카테고리 I 3 케이스 freezegun + `try/except` 4 중 가드 위치 보존 + 1h verify 메인 편중 모니터링 |
| **Q3** 사고 패턴 시뮬레이션 | **RECOMMEND** | HIGH | 카테고리 H 4 케이스 freezegun + **1h verify 사고 재현 사전 시나리오 2 종 도입 의무 (시나리오 A 자연 + 시나리오 B 인위 주입)** |
| **Q4** wrapper vs 직접 호출 | **CONSIDER B (직접 호출)** | LOW | 사이클 60 A1 패턴 답습하지 않는 유일 영역 — lazy import 빚 1 건 청산 + HARNESS_CHANGELOG Q4 명시 의무 |
| **Q5-1** 가격 필터 영향 | **무관 (영향 0)** | 무관 | — |
| **Q5-2** sub-module 분해 시점 | **CONSIDER (사이클 64+)** | MEDIUM | A3 후 1 주 운영 검증 후 별도 카드 발의 (3+1 sub-module 청사진 제시) |
| **Q5-3** cap=10 시 HIGH 우선 | **별도 카드 #5 발의 의무** | MEDIUM | 현재 코드 결함 가능성 발견 — backend-dev Green 단계 확인 + 사이클 64 카드 발의 |

**핵심 메시지**: A3 자체는 사이클 60/61 답습 가능 (Q1/Q2/Q3 RECOMMEND), *유일한 패턴 변경* 권고는 Q4 (lazy import 빚 청산). **월요일 1h verify 의 사고 재현 사전 시나리오 도입이 본 A3 의 마지막 안전선** — 자연 발생 stale 만 기다리는 monitoring 으론 결함을 놓칠 위험. Q5-3 의 cap=10 결함 가능성은 별도 카드 발의 의무 (본 A3 범위 밖).

---

## team-leader 1차 권고와의 차이점

| 항목 | team-leader 의뢰서 | domain-expert 응답 | 차이 |
|---|---|---|---|
| Q1 8 단계 순서 | "변경/race 발생 가능 단계 식별 요청" | 4/5/6/7/8 단계 결정적 + 1~3 자연 보존 | **세분화** — 5 단계 (high_tickers 구성 위치) 명시 |
| Q2 우선순위 분리 | "`high_tickers` 집합 구성 위치 + `try/except` 4 중 가드 + 풀 API 인터페이스" | 모두 RECOMMEND + Q2-G2 `getattr` 폴백 *비권고* (silent 실패 위험) | **반박 1** — `getattr` 대신 `try/except` 보존 권고 |
| Q3 005935 사고 | "T+17min 카운터 리셋 + latency 영향 + 1h verify 권장" | 모두 RECOMMEND + 1h verify 사고 재현 *2 종 시나리오* 도입 의무 | **확장** — 시나리오 B (인위 stale 주입) 신규 발의 |
| Q4 wrapper vs 직접 | "사이클 60 backend-dev Green 패턴 답습 가치 평가" | CONSIDER B (직접 호출) — lazy import 빚 청산 | **선택 명시** — 사이클 60 A1 패턴 *답습하지 않는 유일 영역* |
| Q5+ 신규 발의 | "사이클 62 가격 필터 영향 + 1h verify 보강 + sub-module 분해" | Q5-1 무관 + Q5-2 사이클 64+ + **Q5-3 cap=10 결함 발견** | **신규 위험 발견** — Q5-3 별도 카드 발의 의무 |

**동의 영역**: Q1/Q2/Q3 의 의제 범위 + 회귀 가드 25 케이스 청사진 + 주말 push 의무 + 월요일 1h verify 의무
**반박/확장 영역**: Q2 `getattr` 폴백 비권고 + Q3 인위 stale 주입 시나리오 + Q4 lazy import 빚 청산 선택 + **Q5-3 cap=10 결함 발견**

---

## 우선순위 결정 (사용자 결정 요청)

다음 순서로 사용자에게 결정 요청 권고 (자문 결과 변경 가능성이 HIGH 인 의제 우선):

1. **최우선 (사용자 명시 결정 의무)**: **Q4 선택지 A vs B** — wrapper 위임 (A, 사이클 60 답습) vs 직접 호출 (B, lazy import 빚 청산). 본 자문은 **B 권고** 이나 사이클 60 패턴 일관성 중시 시 A 유지도 안전.
2. **차순위 (사용자 명시 결정 권고)**: **Q3-G4 시나리오 B (인위 stale 주입)** — 1h verify 의 *운영 환경 격리* 가 보장되어야 함. 테스트 종목 선정 + 격리 방법 사용자 결정.
3. **차차순위 (사용자 인지만)**: **Q5-3 cap=10 결함 가능성** — A3 카드 범위 밖이나 backend-dev Green 단계에서 *확인 의무*. 결함 확인 시 별도 사이클 64 카드 #5 발의.
4. **자동 진행 (사용자 결정 불요)**: Q1/Q2/Q5-1/Q5-2 — RECOMMEND 채택 시 설계 카드 25 케이스 그대로 진행.

---

## 월요일 1h verify 시나리오 권고 (사이클 60 §Q7 영속 의무)

### 시나리오 A — 자연 발생 stale monitoring (1h 필수)

**시각**: 2026-06-09 (월) 09:00~10:00 KST (KRX 첫 _boot 직후)

**검증 항목**:
1. **09:00:05 첫 K stale watcher 사이클**: `[stale_watcher] subscribed=N stale=0` 로그 정상 (첫 사이클은 stale 0 기대) — `_scan_loop` 초기화 후 자연 fresh 상태
2. **09:30 _scan_loop 첫 발화 직후**: `[stale_priority_resubscribe] count=0 tickers=[]` 또는 `count=N tickers=[...]` 정상 로그
3. **09:00~10:00 K stale watcher ~30 사이클** (120s × 30 = 3600s = 60분): 자연 발생 stale 종목 *모든 발화* 로그 정합성 (`[stale_watcher]` + `[stale_watcher_detail]` 짝)
4. **메인 편중 비율 monitoring**: `/api/realtime/subscriptions` 의 `session_distribution` 응답 5분 주기 캡처 → 사이클 28/29-R3 실측 (메인 편중 5%) 대비 회귀 시 즉시 hotfix 의무
5. **`_stale_retry_count` 누적 종목 0 건 기대**: 자연 발생 stale 모두 *1 사이클 안에 회복* 정상 패턴. r>=2 누적 종목 발견 시 사고 chain 의심.

### 시나리오 B — 인위 stale 주입 (선택, 시나리오 A 에서 자연 발생 0 건 시 발화)

**전제**: 시나리오 A 1h monitoring 에서 자연 발생 stale 0 건 (회복 검증 부족) 시 발화

**격리 조건**:
- 테스트 종목: *보유 0 + 익일청산 0 + 모든 전략 후보 0* (예: 임의 KOSPI200 종목 1 건)
- 절대 보호: 보유 + 익일청산 종목 *주입 금지*
- 검증 후 즉시 정리: `_stale_retry_count[테스트종목] = 0` 리셋

**검증 시퀀스**:
1. **T+0min**: `_stale_retry_count[테스트종목] = 6` + `_stale_last_resubscribe_at` 부재 설정
2. **T+0~2min (다음 K stale watcher 사이클)**: `[stale_force_retry] ticker=테스트종목 retries=6 last_resub_age=inf` 로그 검증 → `age=float("inf")` 분기 진입 검증
3. **T+2min**: `_stale_retry_count[테스트종목] == 0` 리셋 검증 + `_stale_last_resubscribe_at[테스트종목]` 신규 시각 등록 검증
4. **T+5min~ (5분 cooldown 검증)**: 동일 종목 다시 `_stale_retry_count = 6` 설정 → 다음 사이클 `age < 300s` skip 검증
5. **검증 완료 후 즉시 정리**: 모든 dict 항목 제거 → 정상 상태 회복

### 시나리오 C — KIS LMS chain 사전 차단 monitoring (1h 자동 발화)

**시각**: 1h 동안 *자동 monitoring*, 별도 발화 불요

**검증 항목**:
1. **`[stale_force_retry_cap] ticker=... attempts_in_hour=12` WARNING 0 건 기대**: 자연 발생 시 KIS LMS 위험 의심 — *발화 시* 즉시 사고 chain 의심
2. **`_silent_inactive_recovery_count` dict cap 2 회/시간/세션 회귀 검증**: A2 (사이클 61) 이주 영역이지만 A3 와 *상호 영향* — silent inactive 사고 → silent reconnect 가 K stale watcher 와 동시 발화 race 차단 검증
3. **`[universe_excluded] ticker=...` INFO 정합성**: A2 (사이클 32 R4) 이주 영역이지만 *보유/익일청산 보호* 가 K stale watcher 의 `high_tickers` 와 일관 검증

### 1h verify 종료 후 보고 의무

tester 가 다음 형식으로 보고:
```
## 사이클 63 A3 1h verify 보고서 (2026-06-09 09:00~10:00)
- 시나리오 A 자연 발생 stale: N 건 (회복 시간 평균 M 초)
- 시나리오 B 인위 주입 (발화 여부): {발화|미발화}
- 시나리오 C LMS cap 발화: {0 건 = 정상 | N 건 = 사고 chain 의심}
- 메인 편중 비율 (실측): X% (사이클 29-R3 실측 5% 대비)
- 회귀 종목: {ticker, retry_count, last_resub_age} (있을 시)
- 결론: PASS / FAIL (FAIL 시 즉시 hotfix 의무)
```

---

## CLAUDE.md 절대 규칙 보호 체크리스트 (재확인)

본 자문 권고가 다음 절대 규칙을 *깨지 않음* 명시:

- [x] 체결통보 구독 (H0STCNI0/H0STCNI9) 영역 무관 (본 카드 외)
- [x] uvicorn 단일 워커 영향 0
- [x] **WebSocket 4 중 안전망** F1 + scan_loop + **K stale watcher (A3 본체)** + **`_resubscribe_stale_priority` (A3 본체)** — *행위 보존 + 회귀 가드 25 케이스*
- [x] **K stale watcher 우선순위 분리** (HIGH/LOW) — Q2 RECOMMEND + 회귀 가드 I 3 케이스 + 1h verify 메인 편중 모니터링
- [x] **stale watcher force_retry** (사이클 29-R1) — Q1/Q3 RECOMMEND + 회귀 가드 H 4 케이스 freezegun
- [x] silent inactive 시간당 세션당 2회 cap — A2 (사이클 61) 이주 완료, A3 영향 0
- [x] stale universe 가드 (보유/익일청산 절대 보호) — A2 (사이클 61) 이주 완료, A3 영향 0
- [x] **`_reset_daily_state` 동행 reset** (사이클 60 G-1 + 사이클 61 E-1) — A3 추가 dict 필드 0, 카테고리 E 2 케이스 보존
- [x] KST 강제 (모든 시각 KST timezone 명시) — stale_manager 함수 시그니처에 `KST_TZ` import 보존

---

## 후속 검증 권고 (tdd-engineer / tester / refactor-expert)

### tdd-engineer Red 발주 시
- 본 자문 응답 채택 후 25 케이스 (HIGH 18 우선) Red 작성
- **카테고리 H 4 케이스 freezegun 필수** + 카테고리 K 2 케이스 sorted 결정성 + **Q4 채택 시 카테고리 A 4 케이스에 *직접 호출 분기* 추가**
- Q5-3 cap=10 결함 가능성은 **Red 단계에서 *현재 코드 검증 케이스* 1 건 추가** 권고 (별도 카드 발의 근거 데이터 수집)

### tester Verify 시
- 백엔드 1882 → 1907 PASS 목표 (+25 케이스)
- **flakiness 3 회 반복 의무** (사이클 58 V-2 / 60 / 61 답습)
- **월요일 1h verify 시나리오 A/B/C 3 종 의무** (본 자문 §월요일 1h verify 시나리오 권고 절)

### refactor-expert 후속
- A3 완료 후 1 주 운영 검증 통과 시 **Q5-2 sub-module 분해 카드 발의** (사이클 64+, 3+1 sub-module 청사진)
- Q5-3 cap=10 결함 확인 시 **별도 사이클 64 카드 #5 발의** ("HIGH 종목 우선 보장 로직 추가")

### domain-expert 후속 자문 (필요 시)
- Q5-3 cap=10 결함 확인 시 *결함 영향 깊이* (보유 종목 stale → HIGH 승격 누락 → 손절 평가 지연 chain) 별도 자문 요청 권고
- Q5-2 sub-module 분해 시 *3+1 sub-module 경계 합리성* 별도 자문 요청 권고

---

## 자문 종료

**자문 종료**. team-leader 가 사용자 채택 결정 후 tdd-engineer Red 발주 권고.

**산출물 경로**: `/Users/koscom/Projects/auto_stock/_workspace/cycle63_phase2A3_domain_response.md`

**1줄 요약**: 4 의제 RECOMMEND (Q1/Q2/Q3) + 1 패턴 변경 권고 (Q4 lazy import 빚 청산) + 신규 위험 발견 (Q5-3 cap=10 결함). 월요일 1h verify 시나리오 A/B/C 3 종 도입 의무.
