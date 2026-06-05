# 사이클 63 Phase 2-A3 domain-expert 추가 자문 의뢰서

> **작성**: 2026-06-05 (Fri) 16:30 KST · team-leader
> **요청 대상**: `domain-expert` (데이/스윙 트레이더, 매매 행위 영향 평가)
> **답습 기반**: 사이클 60 응답서 §Q7 ("A3 진입 시점에 재의뢰") 영속
> **위험 등급**: **HIGH** — K stale watcher *핵심* 자체, KIS LMS/앱키 정지 chain 직접, 영구 hot path 360 회/일

---

## 1. 의뢰 배경

refactor #2 카드 #2 (stale_manager 추출) 의 **마지막 단계**. 사이클 60 (Phase 2-A1) + 사이클 61 (Phase 2-A2) 누적으로 stale 영역 9 함수 + 10 상수 = ~589L 이주 완료. **잔여 2 함수 322L** 이주 = 사이클 63 Phase 2-A3.

A1 = LOW (진단/캐시 read-only), A2 = MEDIUM (silent inactive timing + universe guard). **A3 = HIGH** — K stale watcher 본체 (`_check_and_resubscribe_stale` 222L) + `_scan_loop` 5분 우선 재구독 (`_resubscribe_stale_priority` 100L) = **시세 보장 영구 hot path**.

### 1.1 사이클 29 005935 사고 회고 (참고 자료)

2026-05-21 13:21:41 보유 005935 stale 진입 → 1~5회 즉시 강제 재등록 시도 모두 실패 → 6회 초과 후 **8 분 영구 잔류** (당시 사이클 28 까지는 6회 초과 시 무한 skip 결함) → 손절 평가 지연 → 손실 확정. 사이클 29-R1 (시간 기반 force_retry 5분 cooldown + 시간당 12회 cap) + 사이클 29-R3 (우선순위 분리 HIGH+bypass=True / LOW+bypass=False) 로 시정.

**A3 가 본 영역의 *핵심 본체*를 모듈 이주** → 행위 보존 100% 검증 + KIS LMS/앱키 정지 chain 사전 차단 의무.

---

## 2. 자문 의제 (4 항목)

### Q1. K stale watcher 호출 시점/순서 영향 평가

`_check_and_resubscribe_stale` 본체의 호출 순서:

```
1. kis_ws_pool.get_subscribed_tickers()        # 풀 전체 구독 집합
2. subscribed empty → return (retry 보존)
3. datetime.now(_KST_TZ) + threshold 비교       # stale 판정
4. 전체 fresh → _stale_retry_count.clear() + _stale_last_resubscribe_at.clear() → return
5. high_tickers = positions ∪ _pending_next_day_clear  # 우선순위 분리
6. for stale_ticker:
   a. retry = _stale_retry_count.get + 1 → set
   b. sub_priority = HIGH if ticker in high else LOW
   c. if retry > MAX_STALE_RETRIES(5):
      - last_at = _stale_last_resubscribe_at.get(ticker)
      - age_secs 계산 (None → infinity)
      - cooldown 미경과(age<300s) → skip
      - history evict (60분 이전)
      - cap 12 초과 → WARNING skip
      - 강제 재시도: unsubscribe + sleep(50ms) + subscribe(priority, bypass)
        + _stale_retry_count[ticker] = 0 리셋 + _stale_last_resubscribe_at[ticker] = now
        + history.append(now)
   d. else (1~5회):
      - unsubscribe + sleep(50ms) + subscribe(priority, bypass)
      + _stale_last_resubscribe_at[ticker] = now
7. logger.info([stale_watcher] ...) + write_log
8. _emit_stale_session_detail(stale_tickers, now)  # 사이클 60 A1 이주분, wrapper 위임
```

**자문 의제**:
1. 위 8 단계 순서 중 **stale_manager 이주 후 변경 또는 race 발생 가능 단계가 있는가?**
2. **force_retry timing** (5분 cooldown / 시간당 12회 cap) 행위가 stale_manager 함수 호출 (`scheduler` 인자 + `sys.modules.get("src.engine.scheduler")` 패턴) 시 동일 보장되는가?
3. **카운터 리셋 (`_stale_retry_count[ticker] = 0`)** 이 force_retry 성공 직후 sync 영역에서 발생 — wrapper 위임 후 `scheduler._stale_retry_count` property setter 경유 시 동일 객체 갱신 보장되는가? (사이클 60 A1 응답서 §Q3 답습)
4. `_emit_stale_session_detail` 호출 시점이 **모든 stale 처리 직후 + 1회만** — wrapper 위임 호출 vs 모듈 함수 직접 호출 (1 hop 단축) 중 어느 쪽이 행위 보존 + 위험 최소화에 적합한가?

### Q2. 우선순위 분리 (HIGH+bypass=True / LOW+bypass=False) 행위 보존

사이클 29-R3 (2026-05-21) 핵심 규칙:
- `positions` (보유 종목) → HIGH+bypass=True (메인 절대 보장, KIS 41 한도 무시)
- `_pending_next_day_clear` (익일청산 보류) → HIGH+bypass=True (동일)
- 그 외 후보 (VB/LTV/donchian 스캔 종목) → LOW+bypass=False (보조 세션 라운드로빈 분산)

사이클 28 실측 (R3 *전*): main=25 / quote-1=3 / quote-2=4 / quote-3=2 → 메인 편중 73%.
사이클 28 실측 (R3 *후*): main=2 / 보조 합 34 → 메인 편중 5% → 사이클 28 silent inactive 사고 자동 회복.

**자문 의제**:
1. **stale_manager 이주 시 `high_tickers` 집합 구성** (`registry.all()` + `_pending_next_day_clear` 합집합) 이 wrapper 위임 후 *어느 영역*에서 구성되어야 하는가? (scheduler wrapper 또는 stale_manager 함수 내부)
2. `registry.all()` 미주입 인스턴스 (테스트 `__new__`) 보호를 위한 `try/except` 4 중 가드 (L2517~L2529) 가 wrapper 위임 후 동일 위치 보존 의무 — `scheduler` 인자로 위임 받은 stale_manager 함수가 `getattr(scheduler, "registry", None)` 또는 `try/except` 중 어느 쪽으로 가드해야 하는가?
3. HIGH/LOW 결정 후 `kis_ws_pool.subscribe(TICK_TR_ID, ticker, priority=..., bypass_limit=...)` 호출 시 **`bypass_limit=True` 인자가 풀 내부에서 41 한도 검사를 skip** 하는 동작이 stale_manager 함수 호출 경유 시 동일 보장되는가? (풀 API 인터페이스 무변경 — 단순 위임)

### Q3. 사이클 29 005935 사고 패턴 시뮬레이션

사이클 29 사고 재현 시나리오 (회귀 가드 케이스 H 4건의 기반):

```
T+0min: 보유 005935 시세 정상 수신
T+1min: WS silent inactive → 005935 stale 진입 (1회)
T+3min: K stale watcher 발화 → retry=1 → 즉시 강제 재등록 (HIGH+bypass) → 실패 (KIS 응답 timeout)
T+5min: retry=2 → 동일 → 실패
T+7min: retry=3 → 동일 → 실패
T+9min: retry=4 → 동일 → 실패
T+11min: retry=5 → 동일 → 실패
T+13min: retry=6 → MAX_STALE_RETRIES(5) 초과 → force_retry 분기
        - _stale_last_resubscribe_at[005935] = T+11min (마지막 1~5회 시점)
        - age = T+13min - T+11min = 2min = 120s < 300s → cooldown 미경과 → skip
T+15min: retry=7 → age = 240s < 300s → skip
T+17min: retry=8 → age = 360s >= 300s → 강제 재시도 발화 → 성공
        - _stale_retry_count[005935] = 0 리셋
        - _stale_last_resubscribe_at[005935] = T+17min
        - history.append(T+17min)
T+18min: 정상 시세 수신 회복
```

**자문 의제**:
1. 위 시나리오의 **T+17min 시점 강제 재시도 성공 직후 `_stale_retry_count[ticker] = 0` 리셋** 이 stale_manager 함수 위임 후 동일 보장되는가?
2. **stale_manager 이주 후 wrapper hop 추가로 인한 latency 증가** (예: 위임 함수 호출 ~0.001ms) 가 위 시나리오 (분 단위 timing) 에 영향이 있는가? (예상: 무영향)
3. 사고 재현 시 **`_pending_next_day_clear` 보유 종목** 도 동일하게 HIGH+bypass=True 보장되는가? (사이클 29-R3 두 영역 모두 HIGH)
4. tester 1h 운영 환경 verify (월요일 09:00~10:00) 시 **사고 재현 사전 시나리오** 추가 권장 사항이 있는가?

### Q4. `_check_and_resubscribe_stale` 의 internal 호출 (`_emit_stale_session_detail` + `_refresh_stale_ccnl_cache` + 기타) wrapper 위임 vs 모듈 함수 직접 호출

현재 `_check_and_resubscribe_stale` 본체 L2662 마지막 줄:

```python
self._emit_stale_session_detail(stale_tickers, now)
```

→ `_emit_stale_session_detail` 은 이미 사이클 60 A1 에서 stale_manager 로 이주 완료 (scheduler.py L2678~L2683 wrapper):

```python
def _emit_stale_session_detail(self, stale_tickers, now) -> None:
    """``[stale_watcher_detail]`` 세션별 분포 행 출력 — 사이클 60 Phase 2-A1 stale_manager 위임."""
    from src.engine import stale_manager
    stale_manager.emit_stale_session_detail(self, stale_tickers, now)
```

A3 후 `_check_and_resubscribe_stale` 가 stale_manager 로 이주되면 **2 가지 선택지**:

**선택지 A (RECOMMEND)**: `scheduler._emit_stale_session_detail(stale_tickers, now)` 호출 (wrapper 경유, 1 hop 추가)
- 장점: 사이클 60 A1 패턴 일관성 유지, scheduler interface 안정성
- 단점: 1 hop 추가 (~0.001ms 미만, 무영향)

**선택지 B (CONSIDER)**: `stale_manager.emit_stale_session_detail(scheduler, stale_tickers, now)` 직접 호출 (1 hop 단축, lazy import 빚 추가 청산)
- 장점: 1 hop 단축, stale_manager 내부 일관성, 사이클 61 도입 `sys.modules.get()` 패턴과 시너지
- 단점: 사이클 60 wrapper 분리 의도와 약간 상충 (외부 호출자는 wrapper 사용해야 함)

**자문 의제**:
1. 선택지 A vs B 중 **행위 보존 + 위험 최소화** 관점에서 어느 쪽이 적합한가?
2. `_refresh_stale_ccnl_cache` (사이클 37, A1 이주분) 호출이 `_check_and_resubscribe_stale` 본체에서 발생하는가? (현재 L2442~L2663 본체 코드 grep 결과 = **호출 없음** — `_scan_loop` 가 별도 호출. A3 영향 0)
3. 기타 stale_manager 내부 함수 (`evict_expired_ccnl` / `prune_force_retry_history`) 가 `_check_and_resubscribe_stale` 내부에서 호출되는가? (현재 본체 grep = **호출 없음** — 별도 cleanup loop 호출. A3 영향 0)
4. 향후 사이클 64+ 에서 stale_manager 내부 통합 cleanup loop 도입 시 본 A3 결정의 영향이 있는가?

---

## 3. 응답 형식 (사이클 60/61 답습)

각 자문 의제에 대해:
- **답변 요지** (1~3 문장)
- **권고 분류**: RECOMMEND / CONSIDER / AVOID
- **회귀 가드 영향**: 추가/변경 케이스 명세 (있을 시)
- **운영 환경 1h verify 영향**: 시나리오 추가 권고 (있을 시)
- **사이클 29 사고 chain 회피 영향**: 직접/간접/무관 분류

---

## 4. 산출물

- 본 의뢰서: `_workspace/cycle63_phase2A3_domain_consult.md` (현재)
- domain-expert 응답: `_workspace/cycle63_phase2A3_domain_response.md` (자문 후 작성 의무)

---

## 5. 자문 후 의사결정

domain-expert 응답 수신 후:
1. team-leader 가 응답 요약 (사이클 60 패턴 답습)
2. 사용자에게 RECOMMEND/CONSIDER/AVOID 분류 보고 + 채택 결정 요청
3. 채택 결정 후 tdd-engineer Red 발주 (회귀 가드 케이스 25 + 자문 영향 추가 케이스)

---

> **다음 단계**: 사용자가 본 의뢰서 검토 후 명시 지시 시 → `Agent({subagent_type: "domain-expert"})` SendMessage 발주.
