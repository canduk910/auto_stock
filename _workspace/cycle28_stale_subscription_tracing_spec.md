# 사이클 28 — Stale 구독 추적 로그 강화 명세

> 작성: 2026-05-21 (team-leader)
> 트리거: 09:13 VB 돌파 미매수 정밀 진단 → tick_coverage stale=53% 사각지대 발견
> 별도 트랙 (이미 적용): VB weight 0.3 → 0.5, risk.py:152-153 사전 가드 침묵 인지
> 본 사이클 범위: *추적 로그 강화 only.* 동작 변경 금지.

---

## 1. 현업 문제 정의 (트레이더 관점)

오늘 아침 09:13 VB 변동성 돌파 대시보드에서 삼성전기/현대모비스가 *돌파* 로 표시됐지만 매수가 일어나지 않았다.
사후 진단으로 `risk.py` 사전 가드(`current_price > total_investment` 시 check_buy_signal 자체 skip)가 1차 원인으로 확정됐고, 부수 발견으로 **09:00~09:30 사각시간대에 구독 종목 30개 중 16개(53%)가 stale** 상태로 방치되었음이 드러났다.

매매 의사결정의 신뢰성을 회복하려면, 다음 사이클부터 트레이더가 *그 시점*에 다음을 즉시 답할 수 있어야 한다:

| 트레이더가 묻는 질문 | 현재 로그로 답할 수 있는가 | 필요 정보 |
|---|---|---|
| "지금 stale 인 종목이 정확히 무엇인가?" | 부분 (count 만) | 종목 리스트 + 누적 retry 횟수 |
| "그 종목은 어느 세션(main vs quote-N)에 붙어 있나?" | NO | session label |
| "마지막으로 강제 재구독한 게 언제인가?" | NO | 종목별 last_resubscribe_at |
| "세션별로 부하/실패가 편중되어 있는가?" | NO | 세션별 subscribed/fresh/stale + len/41 |
| "보조 시세 세션이 살아있긴 한가?" | 부분 | 보조 세션 가용 여부 + 사용량 |

본 작업은 *위 5개 질문에 다음 영업일 첫 사이클부터 즉답 가능*하게 하는 것을 목표로 한다.

---

## 2. 비기능 요구사항 (안전 가드)

| ID | 가드 | 사유 |
|---|---|---|
| G1 | 기존 prefix `[stale_watcher]` / `[tick_coverage]` / `[stale_priority_resubscribe]` 메시지 형식 *보존* | 외부 모니터링/SQL 알람이 prefix grep 기반. 깨면 알람 사일런스 |
| G2 | `MAX_STALE_RETRIES=5` 분기·임계 변경 *금지* | 본 작업은 *추적 only.* 동작 변경은 별도 사이클 |
| G3 | 종목별 상세 행은 `stale > 0` 일 때만 출력, 최대 20개 cap | 41개 한도 풀 구독 시 로그 폭주 차단 |
| G4 | 보조 세션 미등록(현재 운영 추정) 상태에서 main 단독 정상 동작 | 보조 세션 없는 환경 회귀 방지 |
| G5 | 신규 dict `_stale_last_resubscribe_at` 키 cleanup — `_stale_retry_count` 정리 분기에 동행 | dict 무한 누적 차단 |
| G6 | 매매 동작에 영향 주는 분기·시각 분기 변경 금지 | 추적 강화만 |

---

## 3. 추가 정보 항목 (정의)

### A. 종목 단위 (per-ticker)
- `ticker` — 6자리 종목코드
- `retries` — `_stale_retry_count[ticker]` (기존)
- `last_resubscribe_at` — 신규. `_check_and_resubscribe_stale` 가 강제 재등록 시도 *직후* 갱신 (KST ISO 또는 `HH:MM:SS`)
- `session_label` — `websocket_pool._session_label(ws)` 결과 — "main" / "quote-1" / ... / "unknown"

### B. 세션 단위 (per-session)
- `session_label`
- `subscribed_count` — 해당 세션 구독 종목 수 (`len(ws._subscriptions)` 또는 신규 헬퍼 합집합 기반)
- `fresh_count` / `stale_count` — 동일 세션 내 fresh/stale 분포
- `stale_ratio` — `stale/subscribed` (subscribed=0 이면 0.0)
- `capacity_used` — `subscribed_count / MAX_SUBSCRIPTIONS` (=41)
- `stale_tickers[]` — 최대 20개, `(ticker, retries, last_resub HH:MM:SS)` 튜플

### C. 풀 단위 (pool summary)
- `sessions_total` — main + quote-N 개수
- `quote_sessions_available[]` — label 리스트 (없으면 빈 리스트)

---

## 4. 출력 채널 명세

### 4.1 `_check_and_resubscribe_stale` (120s 주기)
기존 1행 요약 *보존* (G1) 한 뒤, 신규 prefix 별도 행 append:

```
[stale_watcher] checked=N total_stale=M force_resub=K skipped_over_max=S   ← 기존 보존
[stale_watcher_detail] session=main sub=30/41 fresh=14 stale=16 ratio=0.53 stale=[(009150,r=3,@09:12:45), (012330,r=2,@09:11:00), ...]
[stale_watcher_detail] session=quote-1 sub=0/41 fresh=0 stale=0 ratio=0.00 stale=[]
```

- 세션이 1개(main 단독)면 `quote-1` 라인은 출력 안 함 (`subscribed_count==0 && stale_count==0` skip)
- write_log INFO 동행 (system_logs)

### 4.2 `_report_tick_coverage` (scan_loop 5분)
기존 메시지 끝에 비파괴 append:

```
[tick_coverage] subscribed=N fresh=F stale=S ratio=...  ← 기존 보존
[tick_coverage_session] main sub=30/41 fresh=14 stale=16 (0.53) | quote-1 sub=0/41 fresh=0 stale=0 (0.00)
```

### 4.3 `_resubscribe_stale_priority` (5분 우선)
기존 `[stale_priority_resubscribe] count=N tickers=[...]` *보존*. 강제 재등록 직후 `_stale_last_resubscribe_at[ticker]` 도 함께 갱신해 4.1/4.2 출력 정합성 확보.

---

## 5. 인터페이스 변경 (구현 가이드)

### 5.1 `src/realtime/websocket_pool.py`
신규 메서드(또는 동등 헬퍼) 추가:
```python
def get_subscriptions_by_session(self) -> dict[str, set[str]]:
    """label -> set of tickers. 기존 _ticker_to_session 역인덱싱. 신규 영속 dict 추가 금지."""
```
- 기존 `_ticker_to_session` 재활용
- 세션이 정리됐는데 매핑이 남아있는 종목은 "unknown" 라벨로 묶음 (G4)

선택: `def get_session_capacity() -> dict[str, tuple[int, int]]` (label → (subscribed, MAX))
- 또는 `get_subscriptions_by_session` 와 `MAX_SUBSCRIPTIONS` 상수 export 후 호출 측에서 계산

### 5.2 `src/engine/scheduler.py`
- 인스턴스 필드 추가: `self._stale_last_resubscribe_at: dict[str, datetime] = {}`
- `_check_and_resubscribe_stale` 강제 재등록 직후 `self._stale_last_resubscribe_at[ticker] = now_kst()` 갱신
- 신규 헬퍼 `_build_stale_session_view() -> list[SessionView]` 도입 (테스트 용이성)
- `_check_and_resubscribe_stale` / `_report_tick_coverage` 가 동일 헬퍼 호출 (DRY)
- `_stale_retry_count` cleanup 시점에 `_stale_last_resubscribe_at` 동일 키 삭제 (G5)

---

## 6. TDD 진행 단계 (auto-trading-orchestrator)

### Phase 1 — tdd-engineer (Red)
1. `tests/unit/realtime/test_websocket_pool_session_grouping.py`
   - `get_subscriptions_by_session()` 가 main/quote-1 분리 반환
   - 세션 종료 후 매핑 잔류 종목은 "unknown" 으로 그룹핑
2. `tests/unit/engine/test_scheduler_stale_tracking.py`
   - `_stale_last_resubscribe_at` 가 강제 재등록 시 갱신
   - `_stale_retry_count` cleanup 시 `_stale_last_resubscribe_at` 동행 삭제
3. `tests/unit/engine/test_scheduler_stale_logging_format.py`
   - `[stale_watcher]` 기존 1행 여전히 출력 (G1)
   - `[stale_watcher_detail]` 신규 행이 세션별 분포 + 최대 20개 cap 포함
   - `stale_count==0` 인 세션은 detail 행 생략
4. `tests/unit/engine/test_scheduler_tick_coverage_session_view.py`
   - `[tick_coverage]` 기존 + `[tick_coverage_session]` 신규 동시 출력

### Phase 2 — backend-dev (Green)
- 위 인터페이스 명세 그대로 구현
- 회귀: 기존 stale_watcher / tick_coverage / stale_priority_resubscribe 기존 출력은 *완전 동일* 유지

### Phase 3 — tester (검증)
- 신규 4개 + 기존 stale 관련 회귀 테스트 전부 통과
- 출력 예시 1사이클 캡처 (mock + 실제 dry-run 가능 시)
- 안전 가드 G1~G6 체크리스트 확인

---

## 7. 향후 권고 (본 사이클 범위 외 — 다음 사이클 후보)

> 본 작업은 *진단 가시화* 까지만. 아래 액션 아이템은 가시화 후 한 사이클 운영 데이터로 우선순위 재산정.

- **R1** `_check_and_resubscribe_stale` 6회 초과 영구 stale 무한 skip 결함 — 일정 시간 후 자동 강제 unsubscribe → resubscribe(완전 재구독) 또는 세션 자체 재연결 트리거. 현재는 *영구 사망 종목* 침묵.
- **R2** 09:00~09:30 사각시간대 — `TIME_SCAN_START=09:30` 이전에도 `_resubscribe_stale_priority` 호출 (HIGH 우선순위 한정) 검토.
- **R3** VB risk.py:152-153 사전 가드 침묵 — `check_buy_signal` skip 시 `[risk_silent_skip] ticker=… strategy=vb reason=price_gt_total_investment price=… total=…` 1회/종목/일 INFO. 트레이더가 *침묵 매수* 를 즉시 인지.
- **R4** 보조 시세 세션 다중화 운영 도입 — quote-1, quote-2 등록 후 부하 분산 효과를 본 사이클 로그로 측정 후 결정.

---

## 8. 산출물 체크리스트

- [ ] 변경 파일 목록 + 핵심 diff 요약
- [ ] 신규 테스트 4종 + 기존 회귀 통과 결과
- [ ] 출력 예시 1사이클 (mock 또는 실 로그)
- [ ] 안전 가드 G1~G6 충족 확인
- [ ] 향후 권고 R1~R4 별도 spec 파일 생성 여부 (team-leader 차후 판단)
- [ ] *커밋 금지* — 사용자 명시 지시 없음
