# cycle273 U-B — F-3(고지로 갭 판정 오염) 코드 경로 재확인 + F-3b 등재 조사 (2026-09-10, 읽기 전용)

> 과제 = 사용자 결정 "2. D2 … **(나)** 순서로 진행" 중 **(나) = F-3**(`risk.py:646` skip 목록에
> kojiro 추가)의 **착수 전 코드 재확인**과 **F-3b**(momentum·LTV 익일청산 갭률 동일 오염) 조사.
> **이 문서는 코드·테스트·설정을 1 byte 도 바꾸지 않는다.** 모든 인용은 `git show HEAD:<path>`
> 기준(`HEAD = a10191b`, 2026-09-10 저녁). 워킹트리는 조사 시점 clean 이었다(cycle272 변경 미관측).
>
> 선행 정본 = `_workspace/analysis/2026-09-10_kojiro_gap_readout.md`(cycle268 D+1 판독) ·
> `_workspace/consult/2026-09-07_open_price_scope_filter.md` §3.2(여섯 소비처 표) ·
> `_workspace/analysis/2026-09-10_cycle265_direction_report.md`(방향 카드) · 워크리스트 F-2/F-3/F-3b.

---

## 0. 결론 (5줄)

1. **`risk.py:646` 은 "매수 신호 평가"만 건너뛰는 한 줄이고, LTV 프리장 화이트리스트
   (`_PRE_MARKET_EXIT_EVAL_STRATEGIES`, `risk.py:79`)와는 **다른 축**이다** — 하나는 *매수*,
   다른 하나는 *청산*이며 서로 다른 라인·다른 상수·다른 사이클에서 왔다(§1).
2. **kojiro 의 갭 게이트(`kojiro.py:868·871·880`)와 붕괴 가드(`:891`)는 같은 인자 `open_price`
   하나를 읽는다.** 경로 B 에서 그 인자는 `handler._parse_tick_prices` 의 `int(fields[7])`
   (`handler.py:417`)가 **아무 스코프 필터 없이** 그대로 흘러온 값이다 — 형제 필드 `[8] 고가`는
   `[27] HGPR_HOUR` MAIN 창 필터를 갖는데(`handler.py:422-530`) `[7]` 에는 **대응물이 없다**(§2).
3. **판독의 3대 결론은 코드로 재확인된다.** 특히 `caller=on_tick` 행이 WS 유래라는 것은 로그가
   아니라 **코드로 확정**된다 — `on_tick` 호출자는 리포 전체에 2개뿐이고(`handler.py:631` ·
   `scheduler.py:2834`), 후자는 **보유 종목 전용**이라 `has_position`/`is_ticker_blocked_for_buy`
   에서 관측 지점 1(`kojiro.py:825`) **앞**에 잘린다(§2.3). 005490 붕괴 뒤집힘 산술도 재현했다(§3).
4. **(ii) cycle272 의 REST 기준가로는 자동 해소되지 않는다.** 그 시정의 착지점은
   `_confirm_breakout_open_prices` → `on_open_price_confirmed` → 전략 내부 `_targets` 이고,
   그 루프는 `("volatility_breakout","long_tail_volatility")` **하드코딩**(`scheduler.py:1616`)에
   `_targets`/`on_open_price_confirmed` 속성 보유(`:1618`)까지 요구한다 — kojiro 는 **둘 다 없다.**
   kojiro 가 읽는 것은 `ticker_prices` 도 `_targets` 도 아닌 **함수 인자**다(§4.2). ⇒ **F-3 은 여전히 필요하다.**
5. **F-3 착수 시 깨지는 기존 가드가 1건 확정**이다 —
   `tests/unit/engine/test_cycle268_tester_real_call_paths.py::test_real_risk_on_tick_yields_caller_on_tick`
   (docstring 에 "삭제하지 마라" 명시)은 실제 `RiskManager.on_tick` 으로 kojiro 마커 행을 뽑아
   `caller=="on_tick"` 을 단언한다. F-3 이후 그 경로가 사라지면 `assert rows` 에서 FAIL 한다(§5.1).

---

## 1. `risk.py:646` skip 목록 — 정체·이력·`_PRE_MARKET_EXIT_EVAL_STRATEGIES` 와의 관계

### 1.1 무엇을 건너뛰는가 (원문 6줄, `risk.py:643-648`)

```python
# G안 (2026-05-12): donchian_swing 매수 평가는 Pull 폴링(_swing_buy_poll_loop)에서만.
# WebSocket tick 흐름에서는 skip — 일봉 전략이라 실시간 tick 평가가 구조적 낭비.
# 청산(ATR 트레일링/하드 -7%)은 위 check_exit_signal 분기에서 정상 동작 — 영향 없음.
if strategy.strategy_id == "donchian_swing":
    continue
signal = strategy.check_buy_signal(ticker, current_price, open_price)
```

**엄밀히 말하면 "목록" 이 아니다** — 문자열 1개와의 `==` 비교다. 집합/상수가 아니라 리터럴이라
"목록에 추가" 는 자료구조 신설을 뜻한다(§5.6 구현 형태 2안).

이 한 줄이 서 있는 자리는 `on_tick` 전략 루프의 **맨 끝**이다. 앞선 관문을 전부 통과한 뒤에 걸린다:

| 순서 | 라인 | 관문 | F-3 이후에도 kojiro 에 대해 **그대로 실행되는가** |
|---|---|---|---|
| L0 | `risk.py:589-597` | 보유 시 `check_exit_signal` → `execute_sell` | ✅ 그대로 (skip 지점보다 **앞**) |
| — | `:558-586` | `day_high` 앵커 병합(`high_since_buy`) | ✅ 그대로 |
| L1 | `:603` | `session_tracker.is_tradable` 보드 가드 + `[tradable_skip]` 카운터 | ✅ 그대로 (카운터 값 불변) |
| L3 | `:617` | `registry.is_ticker_blocked_for_buy` | ✅ 그대로 |
| L4 | `:623` / `:625` | 자금 사전 가드 + `[risk_silent_skip]` | ✅ 그대로 |
| **skip** | **`:646`** | **매수 평가 우회** | ← 여기에 kojiro 추가 |
| — | `:648-653` | `check_buy_signal` → `signal_count_today += 1` → `execute_buy` | ❌ kojiro 는 도달 불가 |

⇒ **F-3 의 행위 영향은 "경로 B 를 통한 kojiro 신규 매수 = 0" 딱 하나다.** 청산·손절·트레일링·
앵커 갱신·보드 카운터·자금 가드 로그는 전부 무접촉이다(donchian 이 4개월째 같은 자리에서
청산 정상 동작해 온 선례가 그 증거다).

### 1.2 이력 — 왜 donchian 만 등재됐나

`git log -S` 로 이 줄의 유일한 도입 커밋을 확정했다:

```
35a08eb  2026-05-12 20:48  feat(scheduler): donchian_swing pull-based buy evaluation (G plan)
  - scheduler._swing_buy_poll_loop() 신설 — 09:05~09:30 KST 1분 주기 fetch_stock_detail
  - _collect_presubscribe_tickers(): swing 스캔 후보 제외 (보유는 그대로)
  - _build_priority_groups(): swing=[] (시그니처 호환 유지)
  - risk.on_tick: donchian_swing 매수 평가 skip (이중 안전망, 청산은 그대로)
```

**설계 의도가 커밋 메시지에 명시돼 있다 — 이 skip 은 주 기전이 아니라 "이중 안전망"이다.**
주 기전은 *구독 자체를 끊는 것*(`swing: []`)이고, skip 은 **그래도 어떤 경로로든 틱이 들어오면**
(다른 전략 후보와의 교집합 · 보유 승격 · 매수 직후 bypass 구독) 매수 평가가 살아나는 것을 막는
**후위 방어**다. 이 구조는 F-3 판단에 직접 쓰인다 — §4.1 참조.

### 1.3 kojiro 가 여기 없는 이유 — 우연이 아니라 **다크런치 제약의 잔여물**

kojiro 를 `_SWING_POLL_STRATEGIES` 에 넣은 커밋(`24b8b5c`, 2026-07-17 "고지로 대순환 스윙 전략
신규 — Phase 1 다크런치")은 **`src/engine/risk.py` 를 한 줄도 건드리지 않았다**
(`git show 24b8b5c --name-only | grep risk.py` = 0건). 커밋 메시지가 그 이유를 적어 뒀다:

> "enabled=False 다크런치로 병합 — **매매 안전성 8영역 diff 0**, 백테스트·실측 검증 후 활성."
> "배선(**8영역 밖**): scheduler: 등록(다크런치) + `_SWING_POLL_STRATEGIES=("donchian_swing","kojiro")`"

즉 kojiro 는 **폴 루프 쪽 절반만 donchian 과 같아졌고**(`_SWING_POLL_STRATEGIES` ·
`_collect_swing_tickers` 가 `_SWING_POLL_STRATEGIES` 를 순회하므로 `swing: []` 미구독까지 자동 상속),
**risk.on_tick 쪽 나머지 절반(이중 안전망)은 8영역 무접촉 원칙 때문에 미적용으로 남았다.**

⇒ **F-3 은 새 정책이 아니라 2026-07-17 에 의도적으로 미룬 배선의 완성이다.** 이 프레이밍은
자문·승인 문서에 쓸 만한 사실이며, 반대로 "그때 안 넣은 데는 이유가 있지 않았나" 라는 반문에
대한 답이기도 하다 — 이유는 **행위 판단이 아니라 승인 범위**였다.

### 1.4 `_PRE_MARKET_EXIT_EVAL_STRATEGIES` 와 같은 것인가 — **다르다**

| 축 | `risk.py:646` 매수 skip | `_PRE_MARKET_EXIT_EVAL_STRATEGIES` (`risk.py:79`) |
|---|---|---|
| 자료구조 | 문자열 `==` 리터럴 (상수 없음) | `frozenset({"long_tail_volatility"})` 모듈 상수 |
| 방향 | **등재 = 건너뛴다**(매수 평가 안 함) | **등재 = 평가한다**(화이트리스트, 미등재가 보류) |
| 대상 | `check_buy_signal` (`:648`) | `check_exit_signal` 분기 전체 (`:589` `defer_exit`) |
| 조건 | 무조건(항상) | NXT 프리장 단독 구간(08:00~09:00)에서만 |
| 판정자 | `strategy.strategy_id` | `_defers_pre_market_exit()` (`:194-231`, 2소스 OR + fail-open) |
| 도입 | `35a08eb` 2026-05-12 G안 | 2026-08-06 사용자 결정 + cycle238 시각 폴백 |
| 현재 멤버 | `donchian_swing` | `long_tail_volatility` |
| 금기 | (명문 없음) | `tradable_boards` 로 게이팅 **금지**(AST 가드) — 매수 설정이 청산 규약을 바꾸는 커플링 차단 |

**두 목록은 겹치지 않고 서로를 참조하지도 않는다.** 다만 **명명·설계 관례는 후자가 정본**이다 —
루트 `CLAUDE.md` 의 "판정은 **명시 상수**로만 한다" 는 규약이 청산 축에서 확립됐으므로, F-3 이
매수 축에 두 번째 멤버를 넣는 순간 같은 관례(전용 frozenset 상수 + AST 가드)를 따르는 것이
일관적이다(§5.6).

⚠️ **혼동 주의** — kojiro 는 `_PRE_MARKET_EXIT_EVAL_STRATEGIES` 에 **없다**(= 프리장 청산 평가
보류 대상이다). F-3 은 그 사실과 무관하며, F-3 이 그 집합을 건드릴 이유는 없다.

---

## 2. 고지로 갭 게이트·붕괴 가드가 **실제로 읽는 값** — 코드 전수

### 2.1 판정 코드 (`kojiro.py`, HEAD 실측 라인)

```
:799  _account_soft_gate_blocked / :801 buy_disabled / :803 has_position·is_buy_pending
:805  is_sold_today / :807 _bought_today / :809 is_max_positions / :811 is_daily_loss_exceeded
:815  _is_open_risk_capped / :818 not info / :820 stage != 1        ← 11갈래 선-관문(무로그)
:825  observe_gap(..., "candidate", arg_open=open_price, ...)       ← 관측 지점 1
:832~ 섹터캡 / :845 시간 가드 09:05~09:30
:866  prev_close = info["prev_close"]                               ← 일봉 전일 종가(오염 없음, 11/11 DB 일치)
:868  gap_rate = (open_price - prev_close) / prev_close * 100       ← ★ 인자
:871  if gap_rate >= gap_up (5.0)   → skip_up   + :878 _bought_today.add  = 당일 영구 스킵
:880  if gap_rate <= gap_down(-4.0) → skip_down + :887 _bought_today.add  = 당일 영구 스킵
:891  if open_price > 0 and current_price < open_price → collapse   ← ★ 같은 인자, 창 내 재시도
:901  observe_gap(..., "pass", ...) → :905 _bought_today.add → Signal.BUY
```

**네 개의 관문(갭업·갭다운·붕괴·통과)이 전부 같은 `open_price` 인자 하나에 매달려 있다.**
임계 `gap_up_skip_pct=5.0` / `gap_down_skip_pct=-4.0` 은 `kojiro.py:158-159` DEFAULT_PARAMS 이며
정체성 상수(PARAM_RANGES 제외)다 — 09-09/09-10 로그 20행 전부 이 값이라 라이브 실효값도 같다.

### 2.2 그 인자가 어디서 오는가 — 두 경로

| | 경로 A `_swing_buy_poll_loop` | 경로 B `risk.on_tick` |
|---|---|---|
| 시가 출처 | `fetch_stock_detail(t)["stck_oprc"]` (`scheduler.py:2669`) = KIS REST 현재가 시세 | `int(fields[7])` (`handler.py:417` `_parse_tick_prices`) = 통합채널 `H0UNCNT0` `[7] STCK_OPRC` |
| 현재가 | `stck_prpr` (`:2668`) | `int(fields[2])` |
| 호출 | `strategy.check_buy_signal(t, current_price, open_price)` (`scheduler.py:2677`) | `strategy.check_buy_signal(ticker, current_price, open_price)` (`risk.py:648`) |
| 주기 | 09:05~09:30, **분당 1회** × 종목당 `await`+50ms 순차 | **틱마다** |
| 스코프 필터 | 없음(REST 가 이미 당일 KRX 시가) | **없음** ← 오염의 구조적 원인 |

**형제 필드와의 비대칭이 결정적 증거다.** 같은 payload 의 `[8] 고가`는 cycle222-a2 가
`[27] HGPR_HOUR` 를 읽어 `09:00:00 ≤ h ≤ 15:30:00` MAIN 창 밖이면 **0 으로 강등**하는 필터를
갖는다(`handler.py:_parse_day_high`, `_HGPR_HOUR_MAIN_START/END`). `[7] 시가`에 대응하는
`[24] OPRC_HOUR` 는 cycle264 가 **관측만**(`_maybe_log_open_scope_observe`, `handler.py:310-380`)
심었을 뿐 파싱→필터 경로가 **없다**. `_parse_tick_prices` 는 `int(fields[7])` 를 그대로 반환한다.

⇒ **"경로 B 는 일-스코프(프리장 포함) 시가를 MAIN 구간에도 그대로 실어 나른다" 는 것은 로그
해석이 아니라 코드 구조다.** 판독의 4/4 오염은 그 구조가 낳은 관측치다.

### 2.3 `caller=on_tick` 행이 WS 유래라는 것은 **코드로 확정된다** (판독 보강)

`RiskManager.on_tick` 의 호출자는 리포 전체에 **2곳뿐**이다:

| # | 호출자 | 시가 인자 | kojiro 매수 평가에 닿는가 |
|---|---|---|---|
| 1 | `handler.py:631` `await _on_tick(ticker, current_price, open_price, …)` | WS `[7]` (오염 가능) | ✅ 닿는다 |
| 2 | `scheduler.py:2834` `_run_swing_rest_poll_once` | REST `stck_oprc` (깨끗) | ❌ **닿지 않는다** |

2번이 닿지 않는 이유(코드): 그 호출은 `if ticker in held_set:` 안에 있다(`scheduler.py:2833`).
`held_set` 은 스윙 전략들의 **보유 종목**이므로 — kojiro 보유면 `kojiro.py:803 has_position` 에서,
donchian 보유면 `risk.py:617 is_ticker_blocked_for_buy` 에서 — **관측 지점 1(`kojiro.py:825`)에
도달하기 전에** 전부 잘린다. 09:05~09:30 구간은 `held_only=True` 확장창이라 후보는 애초에 폴 대상도 아니다.

⇒ 판독 §3-a 의 "경로 B 4건" 은 **전부 WS 프레임 유래**이며, REST 폴이 섞여 비율을 흐렸을
가능성은 **구조적으로 0** 이다. (판독은 `[open_scope_observe]` 값 일치로 같은 결론에 도달했다 —
이 절은 그 결론의 **독립 근거**다.)

### 2.4 kojiro 는 `scanner.ticker_prices` 를 판정에 쓰지 않는다

`check_buy_signal` 은 `ticker_prices` 를 **읽지 않는다**. 그 dict 를 읽는 것은 관측 leaf
(`kojiro_gap_observe.observe_gap`, `ws_open`/`ws_cmp`/`ws_gap`/`ws_verdict` 4필드)뿐이고, 그것은
`logger.info` 전용이다. 그리고 `risk.on_tick` 은 매 틱 `ticker_prices[ticker] = {...}` 로 dict 를
**통째 교체**한다(`risk.py:495-500`, `:497` 이 `"open_price": open_price`) — 누가 그 dict 에 깨끗한
시가를 써 넣어도 **다음 틱에 덮인다**. §4.2 의 "자동 해소되지 않는다" 는 결론의 두 번째 축이다.

---

## 3. 판독 재확인 — "경로 B 4/4 오염 · 붕괴 가드 1건 뒤집힘"

판독의 오프라인 조인(로그 `arg_open` ↔ `stock_master_daily.open_price`) 자체는 이 문서에서
재수행하지 않았다(로그 원문은 `system_logs` INFO 2일 보존으로 이미 만료 구간). **코드가 검증할 수
있는 것은 "그 수치를 넣었을 때 판정이 그렇게 나오는가" 이며, 그 산술은 전건 재현했다.**

| 사례 | 입력(판독 §2·§3) | 코드 경로 재현 | 결과 |
|---|---|---|---|
| 09-10 `005490` 실제 | open=340,000 / prev=337,000 / cur=335,500 | `:868` gap=**+0.890%** → `:871` 5.0 미달, `:880` −4.0 초과 ⇒ 게이트 통과 → `:891` `335,500 < 340,000` **참** | **collapse** ✅ 로그와 일치 |
| 09-10 `005490` 반사실(KRX 331,500) | open=331,500 / prev=337,000 / cur=335,500 | gap=**−1.632%** ⇒ 게이트 통과 → `:891` `335,500 < 331,500` **거짓** → `:901` | **pass = Signal.BUY** ✅ **뒤집힘 확인** |
| 09-10 `034020` 실제 | open=91,700 / prev=91,700 / cur=89,600 | gap=0.00% 통과 → `89,600 < 91,700` 참 | collapse |
| 09-10 `034020` 반사실(KRX 90,000) | open=90,000 / prev=91,700 / cur=89,600 | gap=**−1.854%** 통과 → `89,600 < 90,000` **참** | collapse — **뒤집히지 않음** ✅ |
| 09-10 `004990` 실제(경로 A) | open=24,600(REST=KRX) / prev=24,850 / cur=24,800 | gap=**−1.006%** 통과 → `24,800 < 24,600` 거짓 | **pass → BUY 5주 @24,800** ✅ |
| 09-10 `004990` 반사실(WS 24,650) | open=24,650 | gap=**−0.805%** 통과 → `24,800 < 24,650` 거짓 | pass — **동일**(이 체결은 어느 값으로도 오염 무관) ✅ |

**갭 게이트 뒤집힘 0/4 · 붕괴 가드 뒤집힘 1/2(창 안 경로 B)** — 판독 결론 유지.

### 3-a. 코드가 판독에 **덧붙이는** 한 가지 — 교차 경로 오염 채널

판독 §8-b-10 이 "코드 사실" 로만 적어 둔 것을 여기서 경로로 확정한다:

```
경로 B(오염) 에서 skip_up/skip_down 발화
  → kojiro.py:878 / :887  self._bought_today.add(ticker)
  → scheduler.py::_swing_buy_poll_loop  `if t in getattr(strategy, "_bought_today", set()): continue`
  → 그날 남은 시간 동안 경로 A(깨끗)가 그 종목을 **다시 심사하지 못한다**
```

즉 **오염된 경로가 깨끗한 경로를 당일 영구히 무력화할 수 있다.** 09-09/09-10 실측은
`skip_up`/`skip_down` **0건**이라 이 채널이 발화한 증거는 없지만, 경로가 존재한다는 것은
코드 사실이고 **F-3 은 이 채널을 통째로 닫는다.** (반대로 `pass` 도 `:905` 에서 `_bought_today`
를 찍으므로, 경로 B 의 매수 확정 역시 경로 A 의 재심사를 막는다.)

---

## 4. 대안 비교

### 4.1 (i) `risk.py:646` skip 에 kojiro 추가 — 무엇이 바뀌고 무엇이 안 바뀌나

**바뀌는 것 (전부)**
- 경로 B 를 통한 kojiro `check_buy_signal` 호출 = **0**. ⇒ 오염된 시가로 내려지던 판정 소멸.
- 경로 B 발 `_bought_today` 오염 래치(§3-a) 소멸.
- `[kojiro_gap_observe]` 의 `caller=on_tick` 행 = **0**(D+1 서명, §5.5).
- 경로 B 발 kojiro 매수 = 0. **이것이 "매매 행위 변경" 의 실체다.**

**바뀌지 않는 것**
- 후보 **집합** 무변(경로 A 대상 `get_scanned_tickers()` = `ranked_final ∪ held_only` ⊇ `_candidates`).
- 청산·손절·트레일링·익일청산·`day_high` 앵커·보드 카운터·자금 가드 로그(§1.1 표).
- 경로 A 의 판정 로직·임계·수량 관문(`_apply_budget_limit`·K·K_ρ) 전부.
- donchian 동작(문자열 하나 추가일 뿐 기존 분기 그대로).

**대가 (판독 K-6/K-7 이 정확히 지적한 것)**
- 붕괴 가드 `current_price < open_price` 는 **그 순간 가격**을 읽는 판정이고, `collapse` 는
  당일 영구가 아니라 **창 내 재시도형**이다. 경로 B 를 끊으면 그 재시도 **빈도**가
  `틱마다` → `분당 1회`로 떨어진다. "일봉 전략이라 틱 해상도가 불필요" 는 `risk.py:644` 의
  **2026-05-12 donchian 에 대한 주석**이지 kojiro 에 대해 검증된 명제가 아니다.
- 다만 **비대칭이 있다**: 빈도가 줄어 놓치는 것은 "오염된 값으로 내려질 뻔한 판정" 이 아니라
  "깨끗한 값으로도 성립했을 수 있는 진입 기회" 다. 즉 **손실 방향이 아니라 기회 방향**의 비용이다.
  (경로 A 는 09:05~09:30 동안 25회 재시도한다 — 창 전체를 덮는다.)

### 4.2 (ii) **cycle272 의 REST 기준가로 자동 해소되는가 — 아니다 (증거 4)**

> ⚠️ 조사 시점 워킹트리가 clean 이라 cycle272 의 **실제 diff 는 보지 못했다.** 아래는
> 그 사이클이 따르기로 한 **정본 설계**(자문 §0·§7.1 + 방향 리포트 축 ①)를 코드에 대조한 결과다.
> 병합 시 재확인 절차는 §7 에 적었다.

1. **착지점이 다르다.** REST 기준가 시정의 대상은 `_confirm_breakout_open_prices`
   (`scheduler.py:1581-1690`)의 `strategy.on_open_price_confirmed(ticker, open_price, board=board)`
   → 전략 내부 `_targets` 기준가다. 그 루프는 대상 전략을 **하드코딩**한다:
   `for sid in ("volatility_breakout", "long_tail_volatility"):` (`:1616`) + `hasattr(strategy,
   '_targets') and hasattr(strategy, 'on_open_price_confirmed')` (`:1618`). **kojiro 는 두 속성이
   모두 없고 그 튜플에도 없다.**
2. **kojiro 가 읽는 값이 다르다.** kojiro 는 `_targets` 도 `ticker_prices` 도 아닌 **함수 인자**
   `open_price` 를 읽는다(`risk.py:648` → `kojiro.py:868/891`). 그 인자는 `handler.py:417` 에서
   오며 VB/LTV 기준가 경로와 **한 번도 만나지 않는다.**
3. **자문이 그 방향을 명시적으로 기각했다.** `2026-09-07_open_price_scope_filter.md` §3.2 표
   6행 = "`kojiro.check_buy_signal` 갭업/갭다운 스킵 + 시가 아래 거부 … 두 가드가 `if open_price > 0`
   로 감싸여 있어 통째로 침묵 ⇒ **가드 무음 해제**" 이고, 결론이 "**소스 레벨 파괴는 명확히 기각**"
   이다. 방향 리포트(축 ①)의 "**못 고치는 것**" 칸도 "kojiro 갭스킵/시가아래 가드 (= 후속 F-3)" 를
   **이름으로** 적는다. 즉 cycle272 의 설계 자체가 kojiro 를 범위 밖으로 선언했다.
4. **설령 `ticker_prices` 에 깨끗한 시가를 써 넣어도 무효다.** `risk.on_tick:495-500` 이 매 틱
   그 dict 를 통째 교체한다. 그리고 kojiro 판정은 그 dict 를 읽지도 않는다(§2.4).

⇒ **F-3 은 cycle272 와 독립이며, cycle272 배포 후에도 그대로 필요하다.**
반대 방향의 상호작용도 없다 — F-3 은 VB/LTV 를 건드리지 않으므로 cycle272 의 D+1 귀인을 오염시키지
않는다(단 **같은 날 배포하면** kojiro 진입 건수 변화와 VB/LTV 진입 건수 변화가 같은 리포트에 섞이므로,
자문 §3-Q6-3 의 귀인 분리 원칙을 따르려면 **배포일을 나누는 편이 낫다** — 결정 사항).

**교차 확인 (같은 세션의 cycle272 조사 문서 — 이 문서 집필 중 도착)**
`_workspace/analysis/2026-09-10_cycle272_U1_open_price_path.md` 가 **독립적으로 같은 결론**에 이르렀다:
- §5 소비처 표 = "kojiro 갭스킵·시가아래 붕괴 가드 (`kojiro.py:858-901`) — `[7]` 을 쓰는가 **그렇다** /
  이번 범위 **밖 (F-3)**", "momentum 익일 갭률(`momentum.py:209`) — 범위 밖 (F-3b)",
  "LTV 익일 갭률(`long_tail_volatility.py:938`) — **범위 밖, 무접촉**".
- §후보 A = "`on_open_price_confirmed` 한 메서드"가 최소 diff, "`_parse_tick_prices` **[7] 파싱을 안 건드리므로 무영향**",
  "`board=="main"` 목표가만 REST 로 갈면 나머지 4개 소비처(익일청산 갭·kojiro 갭·`change_rate`·LTV pre_nxt)는 **byte 동일**".
⇒ **두 조사가 서로 다른 출발점에서 같은 경계선을 그었다.** §4.2 결론은 cycle272 측 설계 문서로도 확인된다.

**유일한 반전 조건** — cycle272 가 `handler._parse_tick_prices` 또는 `risk.on_tick` 의
`check_*_signal` **호출 인자**를 바꿨다면 kojiro 도 자동으로 영향을 받는다. 그러나 그것은
(a) 자문 §3.2 가 "🔴 파괴"(소비처 3·4 = LTV 프리장 매수 전면 사망 · 08:00 익일청산 전면 밀림)로
기각한 형태이고, (b) 워크리스트 F-3b 행이 "cycle265(F-2)가 `check_*_signal` 호출 인자 **byte 동일**을
검증 항목으로 못박았다" 고 기록한 계약의 위반이다. **병합 시 이 한 가지만 확인하면 결론이 확정된다.**

### 4.3 기각한 다른 대안 (기록)

| # | 대안 | 기각 사유 (코드 근거) |
|---|---|---|
| B | kojiro 가 판정 직전 REST 로 시가 재조회 | `check_buy_signal` 은 **동기·IO 금지** hot path. AST 영구 가드 `test_cycle268_ast_gap_observe.py::test_g268_8_check_buy_signal_stays_sync_and_io_free` 가 FAIL |
| C | `sys._getframe` 로 호출자 판별해 경로 B 만 거부 | 관측 기법을 **행위**에 쓰는 것. 리포 관례상 leaf 는 read-only·never-raise 계약(`kojiro_gap_observe` docstring), 스택 의존 행위는 리팩터에 취약 |
| D | handler 에서 `[7]` 에 `[24] OPRC_HOUR` 스코프 필터 | 근본 시정(F-2)이지만 `src/realtime/**` = 8영역이고 자문이 "0 강등 금지"(소비처 3·4 파괴)를 명시. **별도 사이클** |
| E | 무시하고 관측만 연장 | 갭 게이트 뒤집힘 0/4 는 N=4 의 무관측일 뿐이고(진짜 갭률의 경계 여유 최소 2.15%p ↔ 관측 최대 오차 2.52%p = **같은 자릿수**), §3-a 의 교차 경로 오염 채널이 열린 채 남는다 |
| F | `_candidates[ticker]` 에 KRX 시가를 미리 채워 두고 게이트가 그것을 읽게 | 두 경로 **모두**의 입력이 바뀌는 더 큰 행위 변경 + 채우는 주체(09:05 leaf)를 새로 만들어야 함. F-3 보다 비용·위험이 크고 얻는 것은 경로 B 유지뿐 |

---

## 5. F-3 착수 시 실무 제약 (착수 전 반드시 읽을 것)

### 5.1 🔴 깨지는 기존 가드 **1건 확정**

`tests/unit/engine/test_cycle268_tester_real_call_paths.py:179-208`
`test_real_risk_on_tick_yields_caller_on_tick`

```python
rm = RiskManager(registry, order_engine)          # 실제 프로덕션 객체
await rm.on_tick(TICKER, 10100, 10050, 0.5)       # 실제 경로 B
rows = _rows(caplog)
assert rows, "실제 on_tick 경로에서 마커가 한 행도 나오지 않았다"   # ← F-3 이후 여기서 FAIL
assert callers == {"on_tick"}
```

docstring 이 **"삭제하지 마라"** 로 끝난다. 그 가드의 목적은 `observe_gap(depth=2)` 전제를
*두 실경로를 나란히 돌려* 봉인하는 것("한쪽만으로는 depth 오프셋 오류가 '양쪽 다 틀린 이름'으로
조용히 통과한다"). F-3 이 경로 B 를 없애면 **그 봉인의 B팔이 프로덕션에서 소멸**한다.

권고(구현자 판단이 아니라 team-leader/사용자 결정 사항):
- 이 테스트를 **삭제하지 말고 계약을 뒤집어 재작성**한다 — 같은 실제 `RiskManager.on_tick` 호출로
  **마커 행이 0 행임**을 단언(= F-3 의 회귀 가드가 된다). depth=2 봉인은 경로 A 테스트
  (`test_real_swing_poll_loop_yields_caller_swing_buy_poll_loop`, 같은 파일 :132)가 계속 진다.
- 재작성 시 **왜 B팔 봉인이 사라졌는지**를 docstring 에 남긴다(다음 사람이 "합성 shim 으로
  되살리자" 고 하면 그건 이 파일이 없애려던 바로 그것이다).

### 5.2 갱신·추가 대상 테스트 (사전 조사분)

| 파일 | 성격 | F-3 영향 |
|---|---|---|
| `tests/unit/engine/test_risk_donchian_skip_buy.py` | donchian skip 행위 스파이 4케이스 | **케이스 추가 대상**(kojiro 쌍둥이). 기존 4케이스는 그대로 통과 |
| `tests/unit/engine/test_cycle268_tester_real_call_paths.py` | 경로 A/B 실호출 봉인 | **§5.1 — FAIL 확정** |
| `tests/unit/engine/strategies/test_cycle268_kojiro_gap_behavior.py` | 지역 함수 `on_tick`(:340)으로 `check_buy_signal` 직접 호출 | **무영향**(risk 를 거치지 않는다) |
| `test_cycle227_risk_on_tick_acml.py` · `test_cycle227_e2e_acml_vol_pipeline.py` | `strategy_id="kojiro"` 인 `_NoopStrategy` 등록 | `acml_vol`/`tick_volume` 단언뿐 — **무영향으로 보이나 실행 확인 필요** |
| `test_risk_pre_market_exit_gate.py` (:107 파라미터에 `"kojiro"`) | **청산** 보류 게이트 | 무영향(skip 지점보다 앞) |
| `test_cycle222a*` 계열 | `day_high` 앵커(청산 축) | 무영향 |

### 5.3 8영역 sha 핀 절차

`src/engine/risk.py` 는 8영역이다. 네 가드의 취급이 **서로 다르다** — 실측:

| 가드 | risk.py 취급 | F-3 시 필요 |
|---|---|---|
| `test_cycle222a3_ast_followup_fixes.py::test_ga3_6` | `_ALLOWED = {"src/engine/risk.py", "src/realtime/handler.py"}` **파일명 영구 허용** | 핀 불필요(자동 통과) |
| `test_cycle223_ast_donchian_exit_fix.py` (`_PREEXISTING_CONTENT_SHA`) | 8영역 변경은 **내용 sha 핀 필수** | ✅ 핀 등록 |
| `test_cycle223f_ast_manual_apply_safeguard.py` (`_PREEXISTING_CONTENT_SHA`) | 동일 | ✅ 핀 등록 |
| `tests/unit/engine/strategies/test_cycle226_zero_breakout_defense.py` (`_ALLOWED_CONTENT_SHA`, :1140) | 동일 | ✅ 핀 등록 |

세 곳에 **같은 값**을 넣고(값이 갈리면 그 자체가 결함 — 네 가드가 같은 워킹트리를 본다),
커밋 직후 **후속 커밋으로 비운다**(`test_g3_9a/9b` "핀은 항상 4곳" 규약). cycle271 이
`d4cbb58` → `4d88aa6` 로 실행한 그 절차 그대로다.

### 5.4 관측이 스스로를 지우는 문제

F-3 이후 `[kojiro_gap_observe]` 는 경로 A 행만 남는다. 그런데 **경로 A 행도 `ws_open`·`ws_cmp`·
`ws_gap`·`ws_verdict` 를 계속 싣는다**(leaf 는 `caller` 와 무관하게 `ticker_prices` 를 본다) —
즉 **"WS 값이었다면 어떻게 판정됐을까" 반사실은 살아남는다.** 이것이 마커 설계 의도이기도 하다
("깨끗한 경로는 걸렀는데 오염 경로였으면 놓쳤을 종목이 드러난다").

⚠️ **단 한 가지가 사라진다** — `_verdict_for_gap` 은 docstring 이 명시하듯 **갭 게이트만**
재현하고 **붕괴 가드는 제외**한다(`kojiro_gap_observe.py`). 그런데 이번 판독에서 실제로 뒤집힌
유일한 관문이 **붕괴 가드**다. ⇒ F-3 이후 "붕괴 가드가 오염으로 뒤집혔을 사례" 는
**더 이상 관측되지 않는다.** 이를 유지하려면 leaf 에 반사실 필드 1개(`ws_collapse`)를 더하는
**관측 전용** 변경이 필요하다(비8영역 leaf, 행위 0). 착수 여부는 결정 사항 — §8 open question.

### 5.5 D+1 판독 규칙 (의미 반전 — grep 합산 금지)

| 서명 | 배포 전 | 배포 후 기대 |
|---|---|---|
| `[kojiro_gap_observe] … caller=on_tick` | 09-09 0행 / 09-10 2행 | **0행** (핵심 성공 서명) |
| `[kojiro_gap_observe] … caller=_swing_buy_poll_loop` | 09-09 8 / 09-10 8 | **불변**(줄면 다른 결함) |
| kojiro 체결 | 09-09 1건 / 09-10 1건 | 감소 방향 가능 — **단일 일자로 판정 불가** |
| `[swing_poll] … bought=` | — | 불변 |

⚠️ **cycle263 선례와 같은 의미 반전이다** — 배포 전후 로그를 합산해 "경로 B 오염률" 을 계산하면
분모가 반쯤 죽은 수가 나온다. 판독은 **배포일 경계로 잘라서** 한다.

### 5.6 구현 형태 2안 (행위 동일, 문서·가드 비용만 다름)

| | (가) 리터럴 확장 | (나) 명시 상수 |
|---|---|---|
| 코드 | `if strategy.strategy_id in ("donchian_swing", "kojiro"):` | `_TICK_BUY_EVAL_SKIP_STRATEGIES = frozenset({"donchian_swing", "kojiro"})` (모듈 상수, `:79` 관례) + `if strategy.strategy_id in _TICK_BUY_EVAL_SKIP_STRATEGIES:` |
| diff | 1행 치환 | 1행 치환 + 상수 블록(주석 포함 ~10행) |
| 장점 | 최소 diff, 핀 재산출 최소 | `_PRE_MARKET_EXIT_EVAL_STRATEGIES` 와 같은 관례, AST 가드 걸기 쉬움, 세 번째 전략 추가 시 자연스러움 |
| 단점 | 세 번째 멤버가 생기면 다시 손댐 | 8영역 심볼 1개 증가 |

**주의(양안 공통)**: 삽입 위치는 **반드시 현행 skip 과 같은 자리**(`:646`, `check_buy_signal` 직전)여야
한다. 앞으로 옮기면 `[tradable_skip]`·`[risk_silent_skip]` 카운터와 `is_ticker_blocked_for_buy`
호출 횟수가 바뀌어 **관측 지표가 조용히 드리프트**한다(행위 변경 범위 확대).
그리고 판정은 **`strategy_id` 로만** 한다 — `tradable_boards` 나 `sizing_mode` 로 게이팅하면
설정 하나가 매수 평가 경로를 바꾸는 커플링이 생긴다(청산 축의 AST 금기와 동형).

---

## 6. F-3b — momentum·LTV 익일청산 갭률 (등재 조사, **미착수**)

> 사용자는 F-3b 에 답하지 않았다 ⇒ **이 절은 자문 재료이며 착수 제안이 아니다.**

### 6.1 계산 지점 (HEAD 실측)

| 전략 | 함수 | 갭률 | 임계 | 분기 |
|---|---|---|---|---|
| momentum | `check_exit_signal` (`momentum.py:177`) | `:209` `gap_rate = (open_price - pos.buy_price) / pos.buy_price * 100` | `gap_up_threshold=10.0` (`:60`) | `gap_rate < 10` → **NEXT_DAY_CLEAR**(즉시 시장가) / 아니면 트레일링(`trailing_stop_rate=-2.0`) |
| LTV | `check_exit_signal` (`long_tail_volatility.py:913`) | `:938` 동일 식 | `gap_up_threshold=10.0` (`:103`) | 동일 (단 `_limit_up_reached` 종목 + `is_next_day` 한정) |

두 지점 모두 **`risk.on_tick:595` 가 넘겨준 `open_price` 인자**를 읽는다 = **kojiro 와 완전히 같은 값**
(`handler.py:417` → `risk.py:648`… 이 아니라 `:595`, 같은 인자). ⇒ **오염 여부: 동일하다.**

### 6.2 그런데 구조가 다르다 — 그대로 "kojiro 와 같은 문제" 로 읽으면 틀린다

1. **선행 게이트가 다르다.** `if not pos.is_next_day: return NONE`(`momentum.py:198`) +
   `if self._next_day_clear_pending: return NONE`(`:203`). 후자는 08:00:00~08:00:30 만 True 다
   (`scheduler.py:1352·1365`) — 그 뒤로는 **종일 열려 있다.**
2. **momentum 은 프리장 청산 평가 보류 대상이다**(`_PRE_MARKET_EXIT_EVAL_STRATEGIES` 에 없다)
   ⇒ 08:00~09:00 은 `defer_exit` 로 평가 자체가 안 된다. **실효 노출은 09:00 MAIN 부터.**
   **LTV 는 화이트리스트 멤버**라 프리장에도 평가된다 — 프리장 구간의 `[7]` 은 *그 세션의 시가* 라
   자문 §4 기준으로 **정답**이다. 문제는 **09:00 이후에도 같은 낡은 값을 계속 읽는 것**이다.
3. **갭률이 하루 종일 상수다.** `open_price`(일-스코프)와 `pos.buy_price`(전일 확정) 둘 다
   장중 불변이므로 `gap_rate` 도 불변 — 즉 이 분기는 **매 틱 같은 답**을 낸다. 오염은 "가끔
   경계에서 흔들리는" 것이 아니라 **그날의 모드(즉시청산 ↔ 트레일링)를 통째로 고정**한다.
4. **08:00:30 의 1차 판정과 중복된다.** `scheduler._execute_next_day_clear:1460-1466` 이 같은
   식(`(today_open - pos.buy_price)/pos.buy_price`)으로 먼저 판정하고, 미달이면 **즉시 매도가
   아니라** `_pending_next_day_clear` 보류(Tier 1, 2026-07-21 자문) → 09:00:05 `_drain` 시장가 청산이다
   (`scheduler.py:791`). ⇒ MAIN 진입 직후 `on_tick` 이 `_drain` 보다 **먼저** 발화할 수 있는
   09:00:00~09:00:05 창이 실재한다(둘 다 매도이므로 결과는 대개 같다).

### 6.3 08:00 경로는 오염이 **아니다** (워크리스트 서술 재확인)

`_execute_next_day_clear` 가 읽는 `today_open` 은 `ticker_prices["open_price"]`(그 시점 최신 프리장
시가) 또는 `_resolve_open_price` REST 폴백이다(`scheduler.py:1420-1425`). 08:00 시점에 "오늘 첫 시가"
= 프리장 시가가 **설계상 정답**이다(자문 §3.2 소비처 4). ⇒ **문제는 MAIN 구간의 잔상**뿐이다.

### 6.4 방향 — 손실 확대가 아니라 **모드 오선택**

- `[7]`(프리장) **<** KRX 시가 ⇒ 갭률 **과소** ⇒ `gap_rate < 10` ⇒ 트레일링으로 갔어야 할 종목을
  **즉시 청산** = 상방 포기(기대수익 훼손).
- `[7]` **>** KRX 시가 ⇒ 갭률 **과대** ⇒ 즉시 청산했어야 할 종목을 **트레일링 유지** = 설계보다
  오래 보유(노출 확대). LTV 는 여기에 더해 `pos.high_since_buy = today_open`(`scheduler.py:1476`)로
  **트레일링 기준점 자체**가 그 값에서 출발한다.
- 09-07 3자 대조 표본에서 프리장 시가가 KRX 보다 **낮은 쪽이 64/98** 이었다 ⇒ 첫 방향(기대수익
  훼손)이 우세할 것으로 **추정**되나, **뒤집힘 빈도는 한 번도 측정되지 않았다**(임계 10.0% 는
  kojiro 의 5.0% 보다 멀어 뒤집힘이 드물 것이라는 것도 추정이다).

### 6.5 F-3 도 cycle272 도 F-3b 를 닫지 않는다

- **F-3 불가**: 청산 분기는 `risk.py:595`, 매수 skip 은 `:646` — skip 은 청산보다 **뒤**에 있다.
  게다가 momentum/LTV 의 매수를 끄는 것은 전혀 다른 이야기다.
- **cycle272 불가**: 자문·워크리스트가 `check_*_signal` **호출 인자 byte 동일**을 검증 항목으로
  못박았다. 인자가 그대로면 `:595` 가 넘기는 값도 그대로다.
- ⇒ 남는 수단은 (a) **F-2 근본 시정**(`[7]` 스코프, 8영역) 또는 (b) **전략 레벨**로 익일청산 갭률의
  기준 시가를 MAIN 스코프 값으로 바꾸는 것(= 매매 행위 변경, `domain-consult` 필수)뿐이다.

### 6.6 자문에 넘길 질문 3개 (착수 전 답이 필요한 것)

1. **08:00 판정과 MAIN 재판정의 관계** — MAIN `on_tick` 재판정은 08:00 판정의 *중복*인가
   *2차 방어*인가? 중복이라면 MAIN 구간 갭 분기를 아예 닫는(= 08:00·09:00 두 지점에서만 판정)
   설계가 오염과 무관하게 더 단순하다.
2. **LTV 트레일링 기준점** — `high_since_buy = today_open`(프리장 시가)이 오염이 아니라
   *설계* 라면, MAIN 갭률만 KRX 시가로 바꿀 때 두 값의 출처가 갈린다. 트레이더 관점에서 허용되나?
3. **측정 선행 여부** — kojiro 는 관측(cycle268) → 판독 → 시정 순서를 밟았다. F-3b 도 같은 순서를
   요구하는가(= `[next_day_gap_observe]` 류 shadow 마커 선행), 아니면 F-2 를 기다리는가?

---

## 7. 병합 시 재확인 절차 (cycle272 와의 상호작용 — 이 문서의 유일한 미확정 축)

조사 시점 워킹트리가 clean 이어서 cycle272 의 **코드 diff** 는 보지 못했다(설계 문서 `2026-09-10_cycle272_U1_open_price_path.md` 는 §4.2 교차 확인에 반영했다). **아래 3줄이 전부 참이면
§4.2 결론(자동 해소 없음)이 확정**이고, 하나라도 거짓이면 **F-3 필요성을 재평가해야 한다**:

```bash
# 1) 인자 배관이 그대로인가 (여기가 바뀌면 kojiro 도 영향을 받는다)
git diff <cycle272 base>..HEAD -- src/realtime/handler.py | grep -n "fields\[7\]\|_parse_tick_prices\|_on_tick("
git diff <cycle272 base>..HEAD -- src/engine/risk.py     | grep -n "check_buy_signal\|check_exit_signal\|open_price"
# 기대: 빈 출력 (= 호출 인자 byte 동일)

# 2) REST 기준가의 착지점이 VB/LTV 전용인가
git diff <cycle272 base>..HEAD -- src/engine/scheduler.py | grep -n "on_open_price_confirmed\|volatility_breakout\", \"long_tail_volatility"
# 기대: 두 전략 하드코딩 루프 안에서만 변경

# 3) kojiro 가 새 속성을 얻지 않았는가
git show HEAD:src/engine/strategies/kojiro.py | grep -c "_targets\|on_open_price_confirmed"
# 기대: 0
```

---

## 8. 확인 불가 / 이 문서의 범위 밖

- **경로 B 로 kojiro 가 실제로 매수한 이력** — `[kojiro_gap_observe]` 는 2026-09-07 배포라
  그 이전은 무증거다. `trade_history` 만으로는 두 경로를 구별할 수 없다(주문 경로가 같다).
  ⇒ "F-3 이 없앨 매수가 연간 몇 건인가" 는 **모른다**.
- **경로 B 가 창 안 판정자가 되는 빈도의 정상 수준** — 이틀 표본(09-10 2건)뿐(판독 §8-c 동일).
- **판독의 오프라인 조인 수치 자체**(로그 ↔ `stock_master_daily`) — 재수행하지 않았다.
  이 문서가 재확인한 것은 **그 수치를 넣었을 때 코드가 그 판정을 내는가** 다(§3).
- **09-08 0행의 기각 관문** — 관측 지점 1 이 11갈래 관문 뒤라 구조적으로 무로그(판독 K-4 유지).
- **F-3b 의 뒤집힘 빈도** — 한 번도 측정된 적이 없다(§6.4).
- **cycle272 실제 코드 diff** — 설계 문서만 대조했다(§4.2 교차 확인). 구현이 그 설계를 따르는지는 §7 절차로 확인한다.

---

## 부록 A. 이 문서가 짚은 라인 정본 (HEAD `a10191b`)

| 파일:라인 | 내용 |
|---|---|
| `src/engine/risk.py:79` | `_PRE_MARKET_EXIT_EVAL_STRATEGIES = frozenset({"long_tail_volatility"})` |
| `src/engine/risk.py:214` | 화이트리스트 최상단 검사 (`_defers_pre_market_exit`) |
| `src/engine/risk.py:495-500` | `ticker_prices[ticker] = {...}` 매 틱 통째 교체 (`:497` open_price) |
| `src/engine/risk.py:595` | `check_exit_signal(ticker, current_price, open_price)` ← F-3b 경로 |
| `src/engine/risk.py:603/617/623/625` | 보드·중복·자금 관문 (skip 지점보다 앞) |
| `src/engine/risk.py:646` | `if strategy.strategy_id == "donchian_swing": continue` ← **F-3 대상** |
| `src/engine/risk.py:648-653` | `check_buy_signal` → `signal_count_today` → `execute_buy` |
| `src/engine/strategies/kojiro.py:158-159` | `gap_up_skip_pct=5.0` / `gap_down_skip_pct=-4.0` |
| `src/engine/strategies/kojiro.py:825` | 관측 지점 1 (`candidate`) |
| `src/engine/strategies/kojiro.py:868/871/880` | 갭률 산식 / 갭업 / 갭다운 (+`:878`·`:887` `_bought_today`) |
| `src/engine/strategies/kojiro.py:891` | 붕괴 가드 `current_price < open_price` |
| `src/engine/strategies/kojiro.py:901-905` | `pass` 관측 → `_bought_today` → `Signal.BUY` |
| `src/realtime/handler.py:417` | `return int(fields[2]), int(fields[7])` — **스코프 필터 없음** |
| `src/realtime/handler.py:422-530` | `_parse_day_high` — `[27] HGPR_HOUR` MAIN 창 필터(대조군) |
| `src/realtime/handler.py:631` | `await _on_tick(ticker, current_price, open_price, …)` |
| `src/engine/scheduler.py:143` | `_SWING_POLL_STRATEGIES = ("donchian_swing", "kojiro")` |
| `src/engine/scheduler.py:1352/1365` | `_next_day_clear_pending` True→False (08:00:00→08:00:30) |
| `src/engine/scheduler.py:1460-1476` | 08:00 익일청산 갭 판정 + LTV 앵커 리셋 |
| `src/engine/scheduler.py:1616/1618` | REST 기준가 대상 = VB·LTV 하드코딩 + `_targets` 속성 요구 |
| `src/engine/scheduler.py:1911` | `"swing": []` — 스윙 후보 미구독 |
| `src/engine/scheduler.py:2669/2677` | 경로 A REST `stck_oprc` → `check_buy_signal` |
| `src/engine/scheduler.py:2833-2834` | REST 폴의 `on_tick` — **보유 전용** |
| `src/engine/kojiro_gap_observe.py` | `_verdict_for_gap` = **갭 게이트만** 재현(붕괴 제외) |
| `tests/unit/engine/test_cycle268_tester_real_call_paths.py:179` | F-3 이 깨뜨리는 가드 |
| `tests/unit/engine/test_risk_donchian_skip_buy.py` | kojiro 쌍둥이 케이스 추가 대상 |
