# 사이클 60 Phase 2-A — domain-expert 행위 영향 평가 회신

> **작성자**: domain-expert (2026-06-04 16:05 KST)
> **수신자**: team-leader
> **자문 의뢰서**: `_workspace/cycle60_phase2A_domain_consult.md`
> **설계 카드**: `_workspace/cycle60_phase2A_design_card.md`
> **위험 등급**: HIGH (WebSocket 4 중 안전망 hot path + 모듈 간 경계)
> **자문 시점 시장 상태**: 2026-06-04 (목) 15:55 KST = NXT 애프터 진입 직전. 본 자문 자체는 운영 영향 0

---

## 핵심 결론 한 줄

**옵션 B (2 단계 분할) + 추가 가드 7 케이스 보강 권고**. 선례인 사이클 51 boot_manager 와 달리 stale 영역은 *영구 hot path* 이며 4 중 안전망의 동시 호출 + KIS LMS/앱키 정지 cap 의 *시간 윈도우 상태* 가 모듈 경계를 가로지른다. 1 사이클 일괄 이동은 회귀 0건 보장의 *증명 부담* 이 너무 크다.

---

## Q1 — WebSocket 4 중 안전망 호출 시점/순서 영향 평가

**답변**: CONSIDER (행위 보존 가능하나 *추가 가드 4 케이스* 필수)

**근거 (트레이더 시각)**:

K stale watcher 120s 주기는 보유 종목의 손절 평가 latency 의 *최후 보루* 다. 보유 005935 가 13:21:41 stale 후 8 분 영구 잔류한 사이클 29 사고가 바로 이 hot path 의 미세 timing 가 깨졌을 때 무엇이 일어나는지 보여준다. 트레이더 관점에서 stale watcher 는 단순한 "주기 함수" 가 아니라 *호가창을 못 보는 동안 손절선이 깨졌을 수도 있다* 는 공포의 보완 장치다. 함수 호출 비용 자체는 무시 가능 (μs 단위) 하나, 문제는 **모듈 경계를 가로지르는 _stale_state 의 변경 가시성** 이다 — `force_retry_count`, `_stale_force_retry_history`, `_silent_inactive_recovery_count` 가 모두 *시간 윈도우 상태* 인데, 모듈 함수가 scheduler 인자로 받아 *읽고 다시 쓰는* 패턴은 GIL 보호 하에서 안전하나, 향후 누군가 thread / event loop 분리를 시도할 때 *경계 가시성이 흐려진다*.

또한 `silent_inactive` 의 cap (`_silent_inactive_recovery_count` dict 의 60분 슬라이딩 윈도우) 은 LMS/앱키 정지 위험을 막는 *마지막 cap* 인데, 이 카운터가 scheduler._stale_state 에 잔류한다면 stale_manager 함수가 scheduler 인자로 매번 읽어야 한다. 한 번이라도 누군가 우회 호출하면 cap 이 초기화되며, 이는 *KIS 측에서 우리 앱키를 정지시키는 결과* 로 직결된다.

**트레이드오프**:
- 채택 시 비용: 회귀 가드 4 케이스 추가 + 통합 시나리오 시간 freeze 테스트 (`freezegun`) 작성 필요
- 채택 효과: 4 중 안전망의 모든 timing 보존 증명 → 운영 회귀 0건 보장

**구현 가이드** (backend-dev 가 그대로 따를 것):

1. **Q1-G1**: `_stale_watcher_loop` 의 호출 *주기* 가 120s 보존되는지 (`scheduler.start()` 가 등록한 task 의 sleep 값 변경 0) — 단위 가드 1 케이스, `unittest.mock.patch("asyncio.sleep")` + 호출 인자 검증
2. **Q1-G2**: `_force_reconnect_session` 시간당 cap (`SILENT_INACTIVE_RECOVERY_CAP_PER_HOUR`) 이 모듈 이동 후에도 *동일 dict* 참조 보존 — `assert scheduler._silent_inactive_recovery_count is stale_manager._get_state(scheduler).recovery_count` 형태 (혹은 property layer 일관성)
3. **Q1-G3**: K stale watcher → `_emit_stale_session_detail` 호출 *순서* 보존 (`stale_watcher` 본체 → detail emit, 사이클 28 도입 순서) — Mock 호출 순서 가드
4. **Q1-G4**: `_resubscribe_stale_priority(cap=10)` 의 cap 인자가 `_scan_loop` 에서 그대로 전달되는지 (현 라인 L3004 에 호출자 인자 cap=10 명시) — wrapper 가 default 값 변경 안 함

**추가 권고 — `_stale_state` 호환 layer 9 property 보존 의무**:

설계 카드 §1.3 의 `_ensure_stale_state + 9 property` 가 scheduler 잔류한다고 했는데, 이 9 property 가 *외부 코드* (예: `risk.on_tick` 또는 진단 라우트) 에서 직접 접근되는지 사전 grep 필수. 만약 외부 접근이 있다면 stale_manager 가 *반드시* property 를 우회하지 않고 동일 경로로 읽어야 한다 — 그렇지 않으면 사이클 48 `StaleTrackerState` 도입 이전의 누적 결함이 재현된다.

---

## Q2 — `_reset_daily_state` 동행 stale_state.reset_daily 호출 순서 보장

**답변**: RECOMMEND (사이클 55 R-1 / 56-D / 52 패턴 답습 — 안전)

**근거 (트레이더 시각)**:

사이클 56-D 의 `risk_manager.reset_daily_state()` 위임 (5/21 사이클에서 `_risk_silent_skip_logged_today` 1 필드 추가만으로 매끄럽게 흡수됨) 과 사이클 55 R-1 의 `_sell_rejection.reset_daily()` (4 필드 일괄 위임) 가 모두 *scheduler 가 잔류한 reset 분기에서 한 줄 위임* 패턴으로 성공했다. 본 카드 Q2 는 동일 패턴 — `_stale_state` 가 이미 사이클 48 부터 데이터클래스로 통합되어 있고 `reset_daily()` 메서드를 보유하므로, scheduler 잔류 + stale_manager 가 `_stale_state` 읽기/쓰기만 위임하면 reset 순서는 자연 보존된다.

다만 *함정 한 가지* — scheduler `_reset_daily_state` 의 L3828 가 `self._stale_state.reset_daily()` 인지, 아니면 사이클 60 이후 `stale_manager.reset_daily(self)` 위임으로 바뀌는지에 따라 외부 가시성이 달라진다. **권고**: 사이클 56-D 패턴 답습 — `self._stale_state.reset_daily()` 직접 호출 유지 (위임 라인 추가 금지). 외부에서 `scheduler._stale_state` 접근이 항상 동일한 데이터클래스를 가리키므로 위임 layer 도 일관된다.

**트레이드오프**:
- 채택 시 비용: 회귀 가드 1 케이스 (`_reset_daily_state` 호출 후 모든 stale_state 필드 초기값 일치)
- 채택 효과: 다음 영업일 sale leak 영구 차단 (사이클 32 universe 가드 + 사이클 29 force_retry 누적 카운터 모두 초기화 보장)

**구현 가이드**:

1. **Q2-G1**: `scheduler._reset_daily_state()` 호출 후 `assert scheduler._stale_state.retry_count == {}` + `assert scheduler._stale_state.last_resubscribe_at == {}` + `assert scheduler._stale_state.force_retry_history == {}` + `assert scheduler._silent_inactive_first_seen == {}` + `assert scheduler._silent_inactive_recovery_count == {}` + `assert scheduler._universe_excluded_today == set()` (6 필드 동시 검증, 단일 케이스)
2. **추가 가드 권고**: `_stale_state.reset_daily()` 가 **모든** 필드를 초기화하는지 *데이터클래스 필드 누락 가드* — `dataclasses.fields(StaleTrackerState)` 와 reset 후 비교

---

## Q3 — 5 상수 모듈 이동 시 import 경로 변경의 행위 영향

**답변**: RECOMMEND (re-export 충분, 단 추가 보강 1 권고)

**근거**:

5 상수 (`MAX_STALE_RETRIES` / `STALE_FORCE_RETRY_AFTER_SECS` / `STALE_FORCE_RETRY_HOURLY_CAP` / `UNIVERSE_LOW_VOLUME_THRESHOLD` / `SILENT_INACTIVE_FRESH_RATIO_THRESHOLD`) 은 모두 *튜닝 가능한 임계값* 이지만 *런타임 변경 가능성은 0* 이다 (모듈 상수). re-export 는 Python 의 표준 패턴이며 사이클 51 boot_manager 가 동일한 방식으로 외부 import 호환을 유지했다. 단위 값 변경 자체는 *별개 카드* (튜닝 변경) 이며 본 카드 범위 밖이다.

**다만 우려 한 가지** — `SILENT_INACTIVE_MIN_SUBSCRIBED` / `SILENT_INACTIVE_PERSIST_SECS` / `SILENT_INACTIVE_RECOVERY_CAP_PER_HOUR` / `SILENT_INACTIVE_RECOVERY_WINDOW_SECS` / `STALE_FRESHNESS_SECS` 등 *함께 사용되는 상수들* 도 stale_manager 로 이동해야 일관된다. 설계 카드 5 상수만 이동하면 stale_manager.py 가 scheduler.py 상수를 *역참조* 하는 모양이 되며, 향후 누군가 scheduler.py 상수를 변경할 때 stale_manager.py 행위가 자동으로 바뀐다 (사이클 17/24/29 같은 임계 튜닝 사이클에서 위험).

**트레이드오프**:
- 채택 시 비용: 회귀 가드 5 케이스 (`from src.engine.scheduler import X` == `from src.engine.stale_manager import X`)
- 추가 권고 채택 시 비용: 상수 이동을 5 → 10 개로 확장 (관련 상수 통합)
- 채택 효과: 외부 import 영원 호환 + 튜닝 카드의 명확한 위치 (stale_manager.py 단일 진실)

**구현 가이드**:

1. **Q3-G1~G5**: 5 상수 두 import 경로 동일성 검증 — `from src.engine.scheduler import MAX_STALE_RETRIES as A; from src.engine.stale_manager import MAX_STALE_RETRIES as B; assert A is B` (5 케이스, `is` 동일성 보장)
2. **Q3-G6 (추가 권고)**: stale_manager 가 scheduler.py 상수를 역참조하지 *않는지* 정적 검증 — `ast` 모듈로 stale_manager.py 의 `import scheduler` 또는 `from src.engine.scheduler import` 검색, 발견 시 fail. 의존성 역전 방지
3. **추가 권고**: 5 상수 + `SILENT_INACTIVE_MIN_SUBSCRIBED` / `SILENT_INACTIVE_PERSIST_SECS` / `SILENT_INACTIVE_RECOVERY_CAP_PER_HOUR` / `SILENT_INACTIVE_RECOVERY_WINDOW_SECS` / `STALE_FRESHNESS_SECS` 까지 함께 이동 검토 (관련 상수 그룹화)

---

## Q4 — 11 함수 *전체 묶음 이동* vs *2 단계 분할*

**답변**: **B (2 단계 분할) 강력 권고**

**근거 (트레이더 시각 — 가장 중요한 답)**:

선례인 사이클 51 boot_manager 는 *1 회성 부팅 흐름* 이다. 07:50 에 한 번 실행되고 끝난다. 만약 boot_manager 에 결함이 있어도 *다음 영업일까지 발견 시간* 이 있고, 최악의 경우에도 scheduler.start() 가 다시 실행되면 회복 가능하다. 트레이더의 *판단 시간* 도 있다.

반면 stale_manager 는 **120s 주기로 영원히 실행되는 hot path** 다. 09:00~15:30 메인 + 08:00~20:00 NXT 까지 약 12 시간 운영, 즉 *360 회/일 호출* 된다. 만약 함수 11 개 중 1 개라도 *경계 결함* (예: high_tickers 계산이 모듈 분리 후 미세하게 늦는다) 이 있으면, 보유 종목 stale → HIGH 승격 누락 → 메인 편중 73% 재발 → silent inactive 5 분 지속 → `_ws.close()` 발화 → KIS 측 LMS/앱키 정지 위험까지 *15 분 안에 chain* 된다. 사이클 29-R3 실측 데이터 (main=25 → main=2) 이 보여주는 게 바로 이 chain 의 위력이다.

11 함수를 *동시에* 옮기면 결함이 어디서 시작됐는지 *bisect 가 어렵다*. 회귀 가드 32 케이스 + 통합 시나리오 1회로 모든 경계 결함을 잡는 것은 *증명 부담이 과도하다* — 특히 4 중 안전망의 동시 호출 timing, 우선순위 분리 (HIGH/LOW), cap 카운터 (시간당 12회/2회), reset 동행 의 *모든 조합* 을 단일 회귀 테스트로 망라하기 어렵다.

**옵션 B 의 *수정안 권고***:

설계 카드의 분할 (read-only 4 + hot path 7) 보다 **위험도 기반 3 단계 분할** 을 권고:

- **Phase 2-A1 (LOW 위험, ~262L)**: read-only 4 함수 + ccnl TTL evict + force_retry prune 정리 함수
  - `_build_session_subscription_view` / `_emit_stale_session_detail` / `_evict_expired_ccnl` / `_prune_force_retry_history` / `_refresh_stale_ccnl_cache`
  - 회귀 가드 ~10 케이스 (단순 read + 캐시 evict)
  - 위험: 진단 로그 영향만 (매매 hot path 무영향)

- **Phase 2-A2 (MEDIUM 위험, ~365L)**: silent inactive + universe guard
  - `_detect_silent_inactive_sessions` / `_force_reconnect_session` / `_evaluate_universe_guard` / `_delta_unsubscribe_dropped`
  - 회귀 가드 ~12 케이스 (cap 검증 + 보유/익일청산 보호 + 5분 지속 검증)
  - 위험: 세션 reconnect cap 위반 시 KIS 앱키 정지 위험 (cap 가드 회귀 절대 0건 보장 필요)

- **Phase 2-A3 (HIGH 위험, ~321L)**: K stale watcher 핵심 + 5분 우선 재구독
  - `_check_and_resubscribe_stale` / `_resubscribe_stale_priority`
  - 회귀 가드 ~15 케이스 (4 중 안전망 + 우선순위 분리 + force_retry 시간당 cap + 종목별 50ms sleep)
  - 위험: 보유 종목 손절 평가 latency 직접 영향 — 09:13 VB 미매수 사고 재현 위험

**3 단계 분할 비용 vs 효과**:
- 비용: 3 사이클 + 회귀 가드 ~37 케이스 + 통합 시나리오 3회 (vs 옵션 A 의 1 사이클 + 32 케이스 + 1 회)
- 효과: HIGH 영역 분리 격리 (Phase 2-A3 회귀 시 Phase 2-A1/A2 는 이미 *7~14 일 운영 검증* 완료 후이므로 bisect 즉시 가능) + 사용자 신뢰 (HIGH 카드를 *작게 자르는* 게 사이클 51 답습보다 안전)

**구현 가이드**:

1. **Q4-G1**: Phase 2-A1 발주 → 1 영업일 NXT 애프터 운영 후 회귀 0건 확인 → Phase 2-A2 발주
2. **Q4-G2**: Phase 2-A2 발주 → 1 영업일 운영 (NXT + KRX 메인 1 사이클) → 회귀 0건 + silent inactive 카운터 정상 누적 확인 → Phase 2-A3 발주
3. **Q4-G3**: Phase 2-A3 발주 시 *별도 브랜치* (cycle60/phase2A3/stale-watcher-core) — 메인 머지 전 트레이딩 데스크 모의 운영 1일 권고

---

## Q5 — push 시점 권고

**답변**: **주말 (2026-06-06 토요일 또는 2026-06-07 일요일)**

**근거**:

설계 카드 §5 옵션 두 가지 (NXT 애프터 / 익일 새벽) 모두 안전성 부족:

- **NXT 애프터 (15:30~20:00)**: 사용자 작업 시간대 의도는 이해하나, NXT 애프터 시간대는 *보유 종목 매도 + 익일 청산 후보 모니터링* 이 활성. push → 컨테이너 재시작 → `_boot` 재실행 시 *보유 종목 손절 평가 latency 30~60s* 발생. NXT 애프터 18:00 이후라면 거래량 적어 영향 작지만 매매 영향 0 아님.

- **익일 새벽 (07:50 _boot 전)**: 가장 안전한 *영업일 옵션* 이나, 본 카드는 Phase 2-A1+A2+A3 누적 3 사이클이라면 *각 사이클 push 시점도 분산* 필요. 매 사이클 새벽 push 는 *push → 운영 → 회귀 발견 → 다음 새벽 hotfix* 의 24h cycle 강제로 *느림*.

- **주말 권고 (가장 안전)**: 토/일 push → 월요일 07:50 _boot 첫 검증. 만약 회귀 발견 시 일요일 hotfix 가능, 매매 영향 0. Phase 2-A3 같은 HIGH 카드는 *반드시 주말 push* 권고.

**대안** (NXT 애프터 사용자 현실 반영):
- Phase 2-A1 (LOW): NXT 애프터 18:00 이후 push 허용
- Phase 2-A2 (MEDIUM): 익일 _boot 전 push 허용 또는 주말 권고
- Phase 2-A3 (HIGH): **반드시 주말 push** + 월요일 첫 _boot 1 시간 tester verify 동반

---

## 추가 발견 (Q6~Q7)

### Q6 — 보드 전환 race 위험 (사이클 26 의 잠재 영향)

**답변**: AVOID 위험 발견 — *명시적 가드* 필요

**근거**:

설계 카드는 `_board_transition_loop` 가 `_delta_unsubscribe_dropped` 를 호출한다고 명시 (회귀 가드 #3 (c)). 그러나 사이클 26 도입의 *보드 전환 시점* (08:59:10 / 15:39:10 사전 구독 마진) 은 K stale watcher 120s 주기와 *동시 발화 가능* 하다. 보드 전환 중에 K stale watcher 가 `_check_and_resubscribe_stale` 을 실행하면:

1. 보드 전환 task 가 H0NXCNT0 (NXT 채널) 종목을 unsubscribe
2. 동시에 K stale watcher 가 같은 종목을 HIGH+bypass=True 로 재등록 (`high_tickers` 에 포함됨)
3. 보드 전환 task 가 H0STCNT0 (KRX 채널) 로 신규 subscribe
4. 결과: 한 종목이 H0NXCNT0 + H0STCNT0 양쪽 등록 → `_subscriptions` set 정합성 위반

본 카드는 *행위 보존* 이지만, 11 함수를 모듈 분리하면서 이런 race 가 *우연히 더 자주 발화* 할 가능성 있다 (예: 모듈 import 오버헤드로 timing 미세 변화). 사이클 26 보드 전환 도입 후 본 race 의 운영 발생 빈도가 관찰됐는지 모르겠으나, *현재까지 결함 보고 없음* 이라면 본 카드에서 race 가드 도입은 별개 카드로 분리해야 한다.

**구현 가이드**:

1. **Q6-G1**: Phase 2-A2 의 `_delta_unsubscribe_dropped` 이동 시 회귀 가드 — 보드 전환 중 K stale watcher 동시 발화 시뮬레이션 (`asyncio.gather` + 동일 종목)
2. **Q6-G2 (별개 카드 권고)**: 보드 전환 task 와 K stale watcher 의 *명시적 mutex* 도입 — `_board_transition_lock: asyncio.Lock`. 본 카드 범위 밖, 후속 카드 #4 로 발의 권고

### Q7 — 사이클 51 boot_manager 선례와 본 카드의 본질적 차이점

**답변**: 본질적 차이 *3 가지* 명시

**근거**:

| 차원 | 사이클 51 boot_manager | 사이클 60 Phase 2-A stale_manager |
|---|---|---|
| 실행 빈도 | 1 회/일 (07:50) | 360 회/일 (120s 주기) |
| 상태 의존성 | scheduler 1회 읽기 + 1회 쓰기 | scheduler `_stale_state` 9 필드 + 시간 윈도우 + cap 카운터 |
| 결함 영향 시간 | 다음 영업일까지 24h | 5~15 분 안에 KIS 앱키 정지 위험 chain |
| 회복 메커니즘 | 다음 _boot 재실행 | 4 중 안전망 의존 (자체 회복 X) |
| race 위험 | 없음 (단일 실행) | 보드 전환 / scan_loop / silent inactive 동시 발화 |
| 운영 검증 시간 | 1 일 (다음 _boot 검증) | 1~3 일 (NXT 애프터 + KRX 메인 + 익일 청산 + silent inactive 5분 지속) |

**결론**: 사이클 51 boot_manager 답습은 *패턴은 동일* 하나 *위험은 본질적으로 다르다*. 회귀 가드 32 케이스도 *실제로는 ~50 케이스가 안전선* 일 가능성 — 옵션 B 3 단계 분할로 케이스 분산 권고.

---

## 종합 권고 요약 (team-leader 채택 결정 시 참조)

| 항목 | 권고 | 채택 시 추가 작업 |
|---|---|---|
| Q1 호출 시점 영향 | CONSIDER | 회귀 가드 +4 케이스 (Q1-G1~G4) + 9 property 외부 접근 grep |
| Q2 reset 순서 보존 | RECOMMEND | 회귀 가드 +1 케이스 (Q2-G1, 6 필드 동시 검증) + dataclass 필드 누락 가드 |
| Q3 5 상수 호환 | RECOMMEND | 회귀 가드 +5 케이스 (Q3-G1~G5) + 의존성 역전 정적 검증 (Q3-G6) + 5 → 10 상수 확장 검토 |
| Q4 분할 vs 일괄 | **B (3 단계 분할)** | Phase 2-A1 (LOW, 5 함수, ~262L) → Phase 2-A2 (MEDIUM, 4 함수, ~365L) → Phase 2-A3 (HIGH, 2 함수, ~321L) |
| Q5 push 시점 | **주말 권고 (Phase 2-A3 필수)** | Phase 2-A1 NXT 애프터 / Phase 2-A2 익일 새벽 / Phase 2-A3 주말 + 월요일 tester verify 1h |
| Q6 보드 전환 race | AVOID 위험 발견 | 별개 카드 #4 (보드 전환 mutex) 발의 권고 — 본 카드 범위 밖 |
| Q7 boot 선례 차이 | 본질 차이 3 가지 | 회귀 가드 32 → ~50 케이스 안전선 / 운영 검증 시간 1 → 1~3 일 / race 위험 0 → 다중 |

**핵심 메시지**: 옵션 A (1 사이클 일괄) 채택 시 운영 회귀 발생 시 *사이클 29 사고급 chain 위험* 존재. 옵션 B 3 단계 분할 채택 시 *비용 3 배* 이지만 *증명 가능성과 bisect 가능성 보장*. team-leader 와 사용자의 *위험 선호도* 결정 사항.

---

## 후속 검증 권고 (tdd-engineer / tester / refactor-expert)

### tdd-engineer Red 발주 시
- 옵션 B 3 단계 분할 채택 시 *Phase 2-A1 회귀 가드 카드* 먼저 (`_workspace/red/cycle60_phase2A1_stale_manager.md`)
- 회귀 가드 ~10 케이스 (read-only 4 함수 + ccnl evict + force_retry prune)
- 우선순위: silent inactive cap 회귀 0건 보장 가드를 *최우선* (KIS 앱키 정지 위험)

### tester Verify 시
- `trading-test` 스킬 — WebSocket 4 중 안전망 통합 시나리오 (`freezegun` + 시간 진행)
- Phase 2-A3 verify 시 *반드시* 보유 종목 stale → HIGH 승격 → 손절 발화 chain 시뮬레이션 (사이클 29 사고 재현 가드)
- 시간 freeze 테스트: 120s × 100 회 = 12000s 시뮬레이션 (5분 force_retry cooldown + 60분 시간당 cap + 5분 silent inactive 지속 모두 검증)

### refactor-expert 후속
- 본 카드 (사이클 60 Phase 2-A) 완료 후 카드 #3 (settlement_manager) 의존성 재평가
- 사이클 51 + 60 누적 분해 (4,185L → ~2,950L, -30%) 후 scheduler.py 의 다음 분해 후보 (scan_loop / board_transition_loop 등) 재발의 시점 판단

---

## CLAUDE.md 절대 규칙 보호 체크리스트 (재확인)

본 자문 권고가 다음 절대 규칙을 *깨지 않음* 명시:

- [x] 체결통보 구독 (H0STCNI0/H0STCNI9) 영역 무관 (본 카드 외)
- [x] uvicorn 단일 워커 영향 0
- [x] WebSocket 4 중 안전망 F1 + scan_loop + K stale watcher + resubscribe_stale_priority — *행위 보존 + 추가 가드 4 케이스*
- [x] K stale watcher 우선순위 분리 (HIGH/LOW) — 회귀 가드 2 케이스 보존
- [x] silent inactive 시간당 세션당 2회 cap — 회귀 가드 1 케이스 + cap 카운터 dict 동일성 보장
- [x] stale universe 가드 (보유/익일청산 절대 보호) — 회귀 가드 2 케이스 보존
- [x] `_reset_daily_state` 동행 stale_state.reset_daily — Q2-G1 6 필드 동시 검증
- [x] KST 강제 (모든 시각 KST timezone 명시) — stale_manager 함수 시그니처에 `KST_TZ` import 보존

---

**자문 종료**. team-leader 가 사용자 채택 결정 후 tdd-engineer Red 발주 권고.
