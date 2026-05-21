# 사이클 28 — Stale 구독 추적 로그 강화 (행위 분해)

> 명세: `_workspace/cycle28_stale_subscription_tracing_spec.md`
> 본 사이클 범위: *추적 로그 강화 only.* 동작 변경 금지.

---

## B1. websocket_pool 세션별 구독 그룹핑

**행위**: `get_subscriptions_by_session()` 호출 시 `dict[str, set[str]]` 반환. key 는 세션 label (`main`/`quote-1`/.../`unknown`), value 는 해당 세션이 보유한 ticker set.

**입력**: 풀에 main 세션 1개 + 종목 3개(A,B,C) 매핑된 상태
**기대**:
- `{"main": {"A","B","C"}}` 반환
- 종목이 매핑되었지만 세션 객체가 `_quote_sessions`/main 에 없으면 "unknown" 라벨
- 매핑이 0건이면 빈 dict
- 신규 영속 dict 추가 없음 (`_ticker_to_session` 역인덱싱만)

**테스트**: `tests/unit/realtime/test_websocket_pool_session_grouping.py`

---

## B2. _stale_last_resubscribe_at 추적

**행위**: `_check_and_resubscribe_stale` 가 종목에 대해 강제 재등록(`unsubscribe_in_pool` + `subscribe(HIGH, bypass_limit=True)`)을 *시도* 한 직후, `_stale_last_resubscribe_at[ticker]` 가 현재 KST datetime 으로 갱신된다.

**행위 2**: `_stale_retry_count.clear()` 시점에 `_stale_last_resubscribe_at` 도 동시에 clear (cleanup 동행, G5).

**입력**: stale 종목 1개(A) 가 첫 stale 로 감지
**기대**:
- 호출 후 `_stale_last_resubscribe_at["A"]` 존재 (`datetime` 인스턴스, tzinfo=KST)
- `_reset_daily_state()` 호출 후 `_stale_last_resubscribe_at` 비어 있음
- 모든 종목이 fresh 로 회복되어 `_stale_retry_count.clear()` 분기 진입 시 `_stale_last_resubscribe_at` 도 비워짐

**테스트**: `tests/unit/engine/test_scheduler_stale_tracking.py`

---

## B3. [stale_watcher_detail] 신규 행 출력

**행위**: `_check_and_resubscribe_stale` 가 기존 `[stale_watcher] subscribed=N stale=M force_reregistered=K skipped=S` 행을 *완전 동일 형식으로 보존* 한 뒤, 신규 prefix 로 세션별 상세 행을 추가 출력한다.

**포맷**:
```
[stale_watcher_detail] session=<label> sub=<count>/<MAX> fresh=<f> stale=<s> ratio=<x.xx> stale=[(<ticker>,r=<retries>,@<HH:MM:SS>), ...]
```

**규칙 (G1/G3)**:
- 기존 `[stale_watcher]` 행은 *바이트 단위 동일* 보존 (외부 모니터링 grep 호환)
- detail 행은 *세션별 stale_count > 0* 인 세션만 출력 (stale 0 세션 skip)
- stale 종목 리스트 최대 20개 cap, 초과 시 끝에 `...+N` 표시
- `last_resub` 가 미존재(첫 강제 재등록 *전* race) 종목은 `@-` 표시
- 세션 0개 (구독 0건) 케이스에서는 detail 행 0건 (기존 행만)

**입력**: main 세션 1개, 총 5종목 (3 fresh + 2 stale, 각 stale 종목 retries=2/3, last_resub 09:12:45/09:13:00)
**기대**:
- `[stale_watcher]` 1행 정확히 1회 출력
- `[stale_watcher_detail] session=main sub=5/41 fresh=3 stale=2 ratio=0.40 stale=[(A,r=2,@09:12:45), (B,r=3,@09:13:00)]` 1행

**테스트**: `tests/unit/engine/test_scheduler_stale_logging_format.py`

---

## B4. [tick_coverage_session] 신규 행 출력

**행위**: `_report_tick_coverage` 가 기존 출력을 *완전 동일* 보존한 뒤, 세션별 분포 1행을 추가한다.

**포맷**:
```
[tick_coverage_session] <label> sub=<n>/<MAX> fresh=<f> stale=<s> (<ratio>) | <label2> sub=...
```

**규칙**:
- 기존 출력 형식 보존 (G1)
- 모든 세션을 파이프(`|`) 구분으로 1행에 묶음 (stale=0 세션도 포함 — 풀 전체 분포 한눈 파악)
- 세션 0개면 detail 행 0건

**입력**: main 세션 1개, 5종목 (3 fresh + 2 stale)
**기대**:
- 기존 tick_coverage 행 정확히 1회
- `[tick_coverage_session] main sub=5/41 fresh=3 stale=2 (0.40)` 1행

**테스트**: `tests/unit/engine/test_scheduler_tick_coverage_session_view.py`

---

## B5. (회귀 가드) _resubscribe_stale_priority 도 last_resubscribe_at 갱신

**행위**: `_resubscribe_stale_priority` 가 강제 재구독한 종목들 또한 `_stale_last_resubscribe_at` 갱신.

**입력**: HIGH stale 종목 1개를 우선 재구독 경로로 처리
**기대**: `_stale_last_resubscribe_at` 에 해당 종목 키 존재 + 시점 = 호출 시각

**테스트**: B2와 동일 파일에 케이스 추가

---

## 행위 의존 그래프

```
B1 (websocket_pool 헬퍼)
   │
   └─→ B3, B4 (헬퍼 사용)
B2 (last_resubscribe_at)
   │
   └─→ B3 (포맷 필드)
   └─→ B5
```

B1, B2 는 독립. B3, B4 는 B1 + B2 의존. B5 는 B2 의존.

병렬 실행: B1, B2 동시 → 통과 후 B3, B4, B5 동시.
