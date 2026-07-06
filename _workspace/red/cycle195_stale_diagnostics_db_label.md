# 사이클 195 — stale_diagnostics quote-N 잔존 시정 (build_session_subscription_view DB 라벨 매칭)

## 배경 (사이클 194 인계)

사이클 194가 `force_reconnect_session`의 사이클 43 quote-N 잔존을 시정했으나, **동일 계열
잔존이 `src/engine/stale_diagnostics.py::build_session_subscription_view`에 하나 더** 있음
(사이클 194 범위 축소로 인계). 이 함수는 `[stale_watcher_detail]` / `[tick_coverage_session]`
로그의 세션별 capacity 표시를 빌드하는 **관찰성 전용** 함수.

### 결함 (2곳, 사이클 43 미이주)

1. **label_order phantom 생성 (L87-89)**:
   ```python
   label_order = ["main"] + [f"quote-{i}" for i in range(1, len(kis_ws_pool._quotes) + 1)]
   ```
   `get_subscriptions_by_session()`는 사이클 43에서 **DB 라벨(gold/sub)** 키를 반환하는데,
   여기서 phantom `quote-N`을 생성 → groups에 매칭 안 됨 → L100 `if not tickers and label
   not in groups: continue`로 전부 skip. 실제 세션은 L94-96 (groups 키 append)으로만 노출.
   즉 phantom quote-N은 순수 noise(skip됨).

2. **capacity 해석 quote-N 파싱 (L108-114)**:
   ```python
   elif label.startswith("quote-"):
       idx = int(label.split("-", 1)[1]) - 1
       if 0 <= idx < len(kis_ws_pool._quotes):
           ws_obj = kis_ws_pool._quotes[idx]
   ```
   DB 라벨(gold/sub)은 `startswith("quote-")` False → `ws_obj=None` → L122 `cap_used =
   len(tickers)` 폴백. 즉 보조 세션 capacity가 실제 세션 `_subscriptions` TICK 카운트가 아닌
   groups ticker 수(len(tickers))로 degrade. `_ticker_to_session` 역인덱스와 세션 `_subscriptions`가
   diverge하면 capacity_used 부정확.

## 시정 (단일 함수, stale_diagnostics.py)

정본 재사용 = `disable_quote_session`(websocket_pool.py:454-458) / 사이클 194 패턴 미러.

1. **L87-89**: phantom 제거 → `label_order = ["main"]` (groups 키는 기존 L91-96이 append).
   phantom quote-N은 전부 skip되던 noise라 제거 = 행위 보존 (실제 출력 = main + groups 키).
2. **L108-114**: quote-N 파싱 → DB 라벨 매칭:
   ```python
   else:
       ws_obj = next(
           (q for q in kis_ws_pool._quotes if getattr(q, "_label", None) == label),
           None,
       )
   ```
   `ws_obj is None` (미매칭) → L122 `cap_used = len(tickers)` 폴백 보존 (graceful).

### 불변식 / 함정

- fresh/stale 분리(L124-141)·ratio·stale_tickers·cap 20(호출자)·`_main` 분기(L106-107) 불변.
- `label == "main"` 분기는 `kis_ws_pool._main` 직접 참조 = 불변.
- `_label` 미매칭 시 `cap_used = len(tickers)` graceful 폴백 보존 (test mock 호환 + unknown 세션).
- 관찰성 전용 — 매칭/매매 결정 무관. 매매 안전성 8영역(risk/order_engine/realtime/auth/
  api order.py/session/scanner/strategy_registry) diff 0 (stale_diagnostics는 engine, 8영역 외).

## 테스트 (TDD Red → Green)

기존 커버리지: 사이클 43 테스트는 이 함수 미커버. `test_scheduler_stale_logging_format`은
mock 세션에 `_label` 미설정 + `q._subscriptions = {(H0STCNT0, t) for t in tickers}` (TICK
카운트 == len(tickers)) → 수치 동일 → **의미 전환 없음**(현행 quote-N path든 새 폴백이든 cap 동일).
`test_A1_build_session_subscription_view_delegates` (cycle60)는 함수 통째 mock → 무관.

### 신규 회귀 가드 `tests/unit/engine/test_cycle195_stale_diag_db_label.py`

- **G-195-1 (핵심)**: 보조 세션 `_label="gold"`, `_subscriptions = {(H0STCNT0,X),(H0STCNT0,Y),
  (H0UNMKO0,Z)}` (TICK 2 + 非TICK 1), groups={"main":{...}, "gold":{X,Y}}.
  → `build_session_subscription_view` 결과 "gold" 세션 `capacity_used == 2`
  (실제 세션 `_subscriptions` TICK 카운트, 非TICK H0UNMKO0 제외). **현재 코드 = 미매칭 →
  len(tickers)=2** 이므로 수치로는 구분 안 됨 → **divergence 케이스로 구분**: groups["gold"]에
  ticker 3개({X,Y,W}) 넣되 세션 `_subscriptions`엔 TICK 2개만 → 새 코드 cap=2(세션 실측),
  현재 코드 cap=len(tickers)=3. Red = 현재 3, Green 기대 2.
- **G-195-2**: 라벨이 정확히 매칭 (`_quotes=[gold, sub]`, groups에 "sub" → sub 세션의
  `_subscriptions` TICK 카운트, gold 아님). 인덱스 아닌 라벨 매칭 검증.
- **G-195-3**: `_label` 미설정/미매칭 세션("unknown") → `cap_used = len(tickers)` graceful 폴백.
- **G-195-4 (AST)**: `build_session_subscription_view` 함수 본체에 `startswith("quote-")` /
  `int(label.split` / `f"quote-{` 0건 + `getattr(..., "_label")` 매칭 존재 (quote-N 재도입
  영구 차단). `_ast_helpers.py` 재사용 + self-test.

mock 구성은 `test_scheduler_stale_logging_format.py::_setup_pool_mock` 참고하되, 보조 세션에
`_label` **명시 설정** + `get_subscriptions_by_session` return + `ticker_last_tick`
(fresh/stale은 capacity와 무관하니 전부 fresh로 단순화 가능). `datetime.now` 시간 의존 회피
(freezegun 불요 — capacity_used는 시각 무관, ticker_last_tick만 now 기준 fresh 설정).

## 검증

- 격리 신규 ×2 flakiness 0. Red 유효성 stash 시 G-195-1/2/4 FAIL.
- 인접 회귀: `test_cycle60_phase2A1_stale_manager` / `test_cycle43_session_label_unified` /
  `test_cycle67_module_decomposition_g1_g5` PASS. **주의**: `test_scheduler_stale_logging_format`
  은 기존 시간대 의존 flaky(15:15~15:35 call-auction) — 내 변경 무관 stash 교차검증으로 확인.
- 매매 안전성 8영역 diff 0.

## 오케스트레이션

메인 스카우트(완료) → tdd-engineer Red(G-195-1~4) → backend-dev Green → 메인 검증.
관찰성 전용 LOW. 커밋/푸시 보류.
