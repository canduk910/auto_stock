# 팀장 작업지시서 — 우선순위 큐 재정렬 / donchian Pull 전환 / 가설 검증 로깅

작업일자: 2026-05-12 KST · 브랜치: `claude/diagram-stock-filtering-IaJ4G`

이 문서는 트레이더(팀장) 관점에서 사용자의 3가지 코드 변경 요청을 백엔드 구현 단위로 분해한 명세이다.
`CLAUDE.md`(루트), `src/CLAUDE.md`, `src/engine/CLAUDE.md`, `src/realtime/CLAUDE.md` 안전 규칙은 한 줄도 깨지지 않게 진행한다.

---

## 트레이더 의도 요약

1. **HIGH 슬롯은 절대 안전 (보유/익일청산)**, LOW 슬롯은 모멘텀/돌파/스윙 중 무엇을 먼저 채울지의 정책 문제.
   현재 LOW 우선순위가 `swing → momentum → breakout`이라 변동성 돌파(VB/LTV) 후보가 가장 먼저 잘림. 일중 변동성 큰
   브레이크아웃 매매를 살리기 위해 LOW 순서를 **`breakout → momentum → swing`** 로 재정렬.

2. **donchian_swing은 일봉 기반**이고 매수 판단은 09:05~09:30 사이 시가/현재가만 보면 충분.
   그런데 50~150개 후보를 실시간 WebSocket으로 구독하고 있어 슬롯을 잠식. **WebSocket 구독을 끊고
   1분 주기 KIS REST 폴링(Pull)** 으로 전환. 단, **보유 종목은 그대로 HIGH 구독** + **청산 신호는 그대로
   on_tick에서 평가**(ATR 트레일링/하드 -7%는 실시간 시세 필수).

3. 가설 5종(A~E) 가시화. 운영자가 Grafana/Loki로 즉시 추적할 수 있도록 영문 prefix 로그 강화.

---

## 작업 1: LOW 우선순위 재정렬 (breakout 우선)

### 변경 지점
- `src/engine/scanner.py::subscribe_filtered_stocks()` — `priority_groups` 처리 루프 순서
- `src/engine/scheduler.py::_build_priority_groups()` — dict 반환 키 의미는 동일, 값 그대로

### 변경 사양

**현재** (`scanner.py:416~437`):
```
for label, candidates in (("swing", swing), ("momentum", momentum), ("breakout", breakout)):
   ...
[priority_drop] swing=X momentum=Y breakout=Z
```

**변경 후**:
```
for label, candidates in (("breakout", breakout), ("momentum", momentum), ("swing", swing)):
   ...
[priority_drop] breakout=X momentum=Y swing=Z total_subscribed=N max=41 high_count=H remaining=R
```

- HIGH 그룹 (`positions` + `next_day_clear`)은 절대 변경 금지 — `bypass_limit=True` 그대로
- 새 로그 형식의 4개 추가 필드:
  - `total_subscribed` = `len(kis_ws._subscriptions)` (drop 발생 시점)
  - `max` = `MAX_SUBSCRIPTIONS` (=41)
  - `high_count` = HIGH 그룹 unique ticker 합 (`len(positions ∪ next_day_clear)`)
  - `remaining` = `max - total_subscribed`
- drop 발생 시(`total_dropped > 0`)에만 `write_log("WARNING", ...)` fire-and-forget 추가 (가설 A — 가시성)

### 안전 불변식
- HIGH 그룹(보유/익일청산) bypass_limit 절대 보장
- `_build_priority_groups()` 반환 dict의 5개 키 (positions/next_day_clear/swing/momentum/breakout) 그대로 유지
- 기존 평탄 처리(`priority_groups=None`) fallback 경로 영향 없음

---

## 작업 2: donchian_swing — Pull 기반 매수 평가 (G안)

### 핵심 원칙
- **WebSocket은 보유 종목만**. 후보(스캔)는 1분 주기 KIS REST 폴링으로 09:05~09:30 사이 매수 평가
- 청산은 그대로 실시간 (보유 종목은 HIGH 그룹으로 구독되므로 on_tick에서 ATR 트레일링/하드 -7% 평가)
- 시간 가드(09:05~09:30) + `_bought_today` 중복 진입 가드는 그대로 유지 (보호장치)

### 2-1. swing 후보를 WebSocket 구독에서 제외

**파일**: `src/engine/scheduler.py`

| 함수 | 현재 | 변경 후 |
|------|------|---------|
| `_collect_presubscribe_tickers()` (line 903~914) | `tickers.update(self._collect_swing_tickers())` 포함 | swing 라인 **삭제**. 보유는 그대로 (`s.state.positions.keys()` 보존) |
| `_build_priority_groups()` (line 965~1001) | `"swing": self._collect_swing_tickers()` | `"swing": []` (빈 list — 시그니처 호환 유지) |
| `_scan_loop()` (line 1488~1492) | `+ self._collect_swing_tickers()` 라인 포함 | swing 라인 **삭제**. 보유 + 돌파만 |

**보유 종목 보존 검증**: `_build_priority_groups()` 의 `positions` 키는 `self.registry.all()` 순회로
모든 전략 보유를 합집합 → donchian_swing 보유도 자동 포함. 별도 처리 불필요.

### 2-2. scheduler에 swing 매수 폴링 task 추가

**새 메서드**: `src/engine/scheduler.py::_swing_buy_poll_loop()`

```
async def _swing_buy_poll_loop(self) -> None:
    """
    09:05:00 KST ~ 09:30:00 KST 사이 1분 주기로 donchian_swing 후보의 시가/현재가를
    KIS REST(fetch_stock_detail)로 조회하여 매수 신호 평가.

    G안 핵심: donchian은 일봉 전략이라 실시간 tick이 구조적 낭비. WebSocket 슬롯을
    breakout/momentum에 양보하고, 매수 결정은 보드 시작 25분간 1분에 1회씩 평가.

    - WebSocket on_tick 의 check_buy_signal 평가는 risk.py 에서 donchian skip (2-3)
    - 청산(check_exit_signal)은 on_tick 에서 그대로 평가 (보유는 HIGH 구독)
    - 종목별 sequential await (KIS Rate Limit 20/s 보호, asyncio.gather 금지)
    - 1사이클 종료 시 INFO 로그 1행: `[swing_poll] candidates=N filtered=M bought=K elapsed=T.Ts`
    - 본체 예외는 ERROR 로그 흡수, 다음 사이클 자연 재시도
    """
```

상세 흐름 (사이클 1회):
1. `now = datetime.now(KST_TZ).time()` — 09:05 이전이면 다음 분까지 sleep, 09:30 초과면 task 종료
2. `strategy = self.registry.get("donchian_swing")`. None/disabled면 skip
3. `candidates = strategy.get_scanned_tickers()`
4. 필터:
   - `if ticker in strategy._bought_today: continue`
   - `if self.registry.is_ticker_blocked_for_buy(ticker): continue`
5. 각 ticker에 대해 sequential `await fetch_stock_detail(ticker)`:
   - `current_price = int(detail.get("stck_prpr") or 0)`
   - `open_price = int(detail.get("stck_oprc") or 0)`
   - 0이면 skip
6. `signal = strategy.check_buy_signal(ticker, current_price, open_price)`
7. `Signal.BUY` 면 `await self.order_engine.execute_buy(ticker, current_price, strategy)` (기존 시그니처 그대로)
8. 사이클 끝나면 다음 분까지 sleep (시각 정렬: `await asyncio.sleep(60 - (now.second + now.microsecond/1e6))`)

**Task lifecycle**:
- `__init__`: `self._swing_poll_task: asyncio.Task | None = None`
- `start()` 안에서 `_session_task` / `_stale_watcher_task` 발화 직후 `self._swing_poll_task = asyncio.create_task(self._swing_buy_poll_loop())`
- `start()` finally 블록의 task tuple에 `"_swing_poll_task"` 추가 (좀비 task 방지)
- `stop()` 의 task_attr tuple에도 동일 추가

### 2-3. risk.py — on_tick 매수 평가에서 donchian skip

**파일**: `src/engine/risk.py:98` (check_buy_signal 직전)

```
# 매수 신호 평가 직전 가드
if strategy.strategy_id == "donchian_swing":
    continue  # 매수는 Pull 폴링(_swing_buy_poll_loop) 으로만 평가 — WebSocket tick 우회
signal = strategy.check_buy_signal(ticker, current_price, open_price)
```

**중요**: 청산 평가는 그대로 (line 74~79). `check_exit_signal` 호출 전 가드가 아니라
**매수 평가(line 98) 직전에만 skip**. 보유 종목의 ATR 트레일링/하드 손절은 WebSocket tick으로 동작 유지.

### 2-4. donchian_swing.py — 그대로 보존

- `check_buy_signal` 의 09:05~09:30 시간 가드는 유지 (이중 안전망)
- `_bought_today` set 유지 (Pull 폴링 1분 1회도 중복 방지 필요)

### 안전 불변식 (작업 2 전체)
- 보유 종목은 여전히 positions HIGH 그룹으로 WebSocket 구독 — 청산 누락 절대 금지
- check_exit_signal 경로 영향 없음 (ATR 트레일링/하드 -7%)
- execute_buy 시그니처 그대로 — 매핑 동기 등록 규약(`_order_qty/_order_strategy/_order_ticker/_pending_buy_orders`)은
  내부에서 보장
- `donchian_swing.check_buy_signal` 의 시간 가드/`_bought_today` 가드 그대로
- `_swing_buy_poll_loop` 본체 예외는 흡수 — `_session_task`/`_stale_watcher_task` 와 동일 패턴
- 종목별 await 사이 50ms sleep 권장 (KIS Rate Limit 20/s 보호)

---

## 작업 3: 가설 검증 로깅 강화

영문 prefix 유지 (한국어 prefix 금지). 모든 로그는 KST 기준.

### 가설 A — `[priority_drop]` 확장 (작업 1과 일체)
- 형식: `[priority_drop] breakout=X momentum=Y swing=Z total_subscribed=N max=41 high_count=H remaining=R`
- `total_dropped > 0` 일 때만 `write_log("WARNING", ...)` 영구 저장
- 위치: `src/engine/scanner.py::subscribe_filtered_stocks()` (작업 1에서 통합)

### 가설 B — `[tick_coverage]` 확장
- **위치**: `src/engine/scheduler.py::_report_tick_coverage()` (line 1663~1698)
- **현재 형식**: `[tick_coverage] subscribed=N fresh=F stale=S`
- **변경 형식**: `[tick_coverage] subscribed=N fresh=F stale=S ratio=R% stale_sample=[t1,t2,...] last_tick_avg_age=Xs`
  - `ratio` = `100.0 * fresh / max(subscribed, 1)` (1 자리 소수)
  - `stale_sample` = sorted(stale tickers)[:10]
  - `last_tick_avg_age` = 전체 평균 마지막 tick 경과시간(초), `ticker_last_tick.get(t, min_dt)` 사용. dict 비어있으면 -1.
- **임계 조건**: `stale_ratio = stale / max(subscribed, 1)` > 0.30 이면 `write_log("WARNING", ...)`, 그 외 INFO
- system_logs 메시지에도 동일 필드 포함

### 가설 C — `[breakout_open_confirm]` 노출
- **위치**: `src/engine/scheduler.py::_confirm_breakout_open_prices()` 호출 직후 1회 INFO 로그
  - 현재 호출 지점은 `_collect_breakout_tickers` / VB·LTV 전략 시가 확정 직후 (확인 필요)
- **형식**: `[breakout_open_confirm] board=BOARD strategy=SID confirmed=N empty=M sample={ticker:open_price,...}`
  - `confirmed` = `open_price > 0` 인 후보 카운트
  - `empty` = `open_price == 0` 인 후보 카운트
  - `sample` = 최대 5개 (sorted ticker → open_price dict)
- 각 board × strategy 조합당 1행

### 가설 D — `[tradable_skip]` 분당 1회
- **위치**: `src/engine/risk.py::on_tick()` 의 `session_tracker.is_tradable()` skip 분기
- **카운터**: `RiskManager._tradable_skip_count: dict[str, int]` (기본 0)
- 매 skip 시 `self._tradable_skip_count[strategy_id] += 1`
- 1분 주기 출력 + reset (별도 task 또는 RiskManager 내부 `_last_emit_ts`로 lazy emit)
  - 옵션 A (권장): `on_tick` 안에서 `now_ts - self._last_tradable_emit_ts >= 60` 일 때 emit + reset + ts 갱신.
    별도 task 도입 없이 tick 흐름에 묶기.
- **형식**: `[tradable_skip] momentum=X breakout=Y ltv=Z swing=W active_boards=[...]`
  - `active_boards` = `sorted([b.value for b in session_tracker._active_boards])` 또는 등가 표현
- INFO 레벨

### 가설 E — `[stock_master_miss]` 노출
- **위치**: `src/engine/order_engine.py::_strategy_exchange_async()` (line 73~109)
- 현재 `[nxt_downgrade]` 만 노출. 추가로 stock_master 캐시 miss/stale 시 1행 로그:
  - **형식**: `[stock_master_miss] ticker=T strategy=S exchange_keep=E reason=miss|stale`
  - `reason=miss`: `stock_master.get(ticker)` 결과가 None
  - `reason=stale`: 결과는 있으나 `basics.is_stale()` 또는 동등 메서드 True (없으면 24h 외 — 헬퍼 확인 필요)
- fire-and-forget `write_log("INFO", ...)`. 본 흐름(전략 기본 exchange 유지) 영향 없음

---

## 산출물 / TDD 사이클

### Red (tdd-engineer)
다음 테스트 파일을 신규 작성하여 모두 **실패하도록** 한다 (현 코드는 새 동작을 모름):

1. `tests/engine/test_scanner_priority_order.py`
   - 새 LOW 순서 `breakout → momentum → swing` 검증 (한도 초과 시 swing이 가장 먼저 drop)
   - 새 `[priority_drop]` 로그 형식 검증 (caplog 또는 write_log mock)
   - HIGH bypass_limit 절대 보장 회귀 케이스 (positions 50개 + breakout 100개에서 positions 50개 모두 add)

2. `tests/engine/test_swing_poll_loop.py` (freezegun + monkeypatch fetch_stock_detail)
   - 09:05:30에 1사이클 발화 → `execute_buy` 1회 호출 검증
   - 09:30:01 에 task 종료 검증
   - `_bought_today` 중복 방지 (같은 종목에 대해 1사이클만 매수)
   - `is_ticker_blocked_for_buy=True` 종목은 skip
   - `stck_oprc=0` 응답 종목은 skip
   - INFO 로그 `[swing_poll]` 형식

3. `tests/engine/test_scheduler_swing_subscription_removed.py`
   - `_collect_presubscribe_tickers()` 결과에 swing 후보 미포함, 보유 포함
   - `_build_priority_groups()["swing"]` 가 `[]`
   - `_scan_loop` 통합 extra 에 swing 후보 미포함

4. `tests/engine/test_risk_donchian_skip_buy.py`
   - donchian_swing 의 `check_buy_signal` 이 on_tick 안에서 호출되지 않음 (mock 검증)
   - donchian_swing 의 `check_exit_signal` 은 그대로 호출 (보유 종목)

5. `tests/engine/test_observability_logs.py`
   - `[tick_coverage]` 새 필드(ratio/stale_sample/last_tick_avg_age) 노출
   - stale_ratio > 30% 시 WARNING 레벨
   - `[breakout_open_confirm]` 노출 (board/strategy/confirmed/empty/sample)
   - `[tradable_skip]` 분당 1회 emit (freezegun으로 시간 진행)
   - `[stock_master_miss]` reason=miss / reason=stale 분기

### Green (backend-dev)
위 5개 테스트 파일을 모두 통과시키는 최소한의 코드 변경. 안전 불변식 위반 금지.

### Refactor
```
python tools/test_impact/build_index.py
```

### Verify (tester)
- pytest 전체 통과
- 영향 인덱스 기반 회귀 테스트 (`tools/test_impact/affected.py`)
- 수동 시나리오:
  1. swing 보유 종목이 positions HIGH 그룹으로 구독되는지 (positions=donchian 보유 1+ 케이스)
  2. swing 매수가 09:05~09:30 폴링으로 트리거되는지 (FakeKisRest)
  3. `[priority_drop]` 새 형식이 system_logs WARNING으로 영구 저장되는지
  4. donchian 청산(ATR/하드 -7%) 경로 영향 없음 — check_exit_signal mock 호출 검증

---

## 커밋 정책

3개 커밋으로 분리:
1. `fix(scanner): reorder priority queue to breakout > momentum > swing`
2. `feat(scheduler): donchian_swing pull-based buy evaluation (G plan)`
3. `obs(scheduler): enrich tick_coverage / priority_drop / tradable_skip logs`

각 커밋은 해당 작업의 Red 테스트 + Green 구현 + 명세 갱신을 포함한다.
PR 생성 금지 — push 까지만.

---

## 작업 분배

- **tdd-engineer (opus)**: Red 테스트 5개 파일 작성
- **backend-dev (sonnet)**: 작업 1/2/3 코드 구현 + 테스트 통과
- **tester (opus)**: 회귀 + 안전성 검증 + 수동 시나리오 검수

---

## 절대 금지 사항 (재확인)

- 체결통보 구독(H0STCNI0/H0STCNI9) 제거 금지
- uvicorn 단일 워커 필수
- 매핑 동기 등록 규약(`_order_qty/_order_strategy/_order_ticker/_pending_buy_orders`) 변경 금지
- `_completed_orders` race 가드 제거 금지
- `_reset_daily_state()` 제거 금지
- HIGH 그룹(보유/익일청산) `bypass_limit=True` 절대 보장
- `MAX_SUBSCRIPTIONS=41` 변경 금지
- 익일청산 보류 set(`_pending_next_day_clear`) 동작 변경 금지
- 한국어 로그 prefix 금지 (`[xxx_yyy]` 영문만)
- 모든 시각 데이터 KST 강제
