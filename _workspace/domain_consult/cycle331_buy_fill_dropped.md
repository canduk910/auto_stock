# cycle331 자문 — 발사 창에 착지한 매수 체결통보가 포지션을 남기지 않는다

작성 2026-09-20 · domain-expert · 요청자 team-leader
대상 = `src/engine/order_engine.py::_handle_buy_fill` 의 `[buy_fill_fallback_held_conflict]` 조기 return
코드 변경 없음 — 진단 + 시정 방향 권고

---

## 0. 한 줄

**제기된 주장은 참이다. 그리고 실측 2건은 전부 우리 LTV 자기 주문이었고, 한 건은 하루 온종일 손절이 꺼진 채로 −6.5% 에 청산됐다.**
다만 주장 중 두 군데를 정정한다 — ① 익일청산은 멈추지 않았다(익일 `_boot` 이 되살린다) ② 로그 문구 「이미 타 전략 보유 중」은 **사실이 아니다**(같은 전략의 자기 `pending_buys` 다).

---

## 1. 사슬이 실재하는가 — 전부 참, 파일:행

| 주장 | 판정 | 근거 |
|---|---|---|
| `is_ticker_held_by_any` 가 `is_buy_pending` 을 참으로 친다 | **참** | `src/engine/strategy_registry.py:69-74` — `if s.state.has_position(ticker) or s.state.is_buy_pending(ticker): return True`. 판정 대상은 `self._strategies.values()` **전부**(자기 자신 포함). `is_buy_pending` 정의 = `src/engine/strategy_base.py:121` |
| `pending_buys.add` 가 `place_order` **앞**이다 | **참** | `src/engine/order_engine.py:1138` `state.pending_buys.add(ticker)` → `:1140` `pending_buy_amounts` → `:1146` `await self._strategy_exchange_async(...)` → `:1262` `result = await place_order(**place_kwargs)` |
| 매핑 5종은 `place_order` **뒤** 동기 등록이다 | **참** | `:1270-1290` (`_order_qty`/`_order_strategy`/`_order_ticker`/`_order_exchange`/`_order_division`/`_pending_buy_orders`). 즉 `await place_order` 가 걸린 동안 **매핑은 전부 비어 있고 `pending_buys` 는 이미 차 있다** |
| 조기 return 이 Position 등록 **전**이다 | **참** | 조기 return = `:2415-2421`, Position 신규 등록 = `:2441-2451`. 사이에 다른 경로 없음 |
| trade_history 폴백도 miss 한다 | **참(구조적)** | `src/db/trade_history.py:222-237` 의 WHERE 가 `ticker AND order_no AND trade_type AND status IN (PENDING, PARTIAL)` 이다. PENDING INSERT 는 `place_order` 가 **돌아온 뒤**라 창 안에는 그 `order_no` 행이 원리상 존재하지 않는다 → 항상 `None` |

### 창의 정확한 경계

```
1138  pending_buys.add(ticker)          ← 여기서 is_ticker_held_by_any(t) = True 가 된다
1146  await _strategy_exchange_async()
1262  await place_order()               ← KIS 가 주문을 받는 시점 ~ 응답이 돌아오는 시점
      ◄──────── 체결통보가 여기 착지하면 매핑 0 / pending 1 ────────►
1270  _order_qty[order_no] = ...        ← 여기부터는 정상 경로(src=map)
```

### 수신 쪽 경로

`handle_execution_notice`(`:2194`) → `_order_ticker.get(order_no)` 가 `None`(`:2211`) → payload ticker 가 6자리 영숫자라 **처리는 계속**되고 `:2227` 에 `"종목 매핑 없음, payload ticker 사용"` WARNING 1행 → `:2304` `_handle_buy_fill` → `:2406` `_order_strategy.get` miss → `:2409` trade_history miss → `:2415` `is_ticker_held_by_any` **참** → `:2421` **return**.

그 뒤로 실행되지 않는 것들(전부 return 아래):

- `:2441-2451` `state.positions[ticker] = Position(...)` + `fill_count_today += 1`
- `:2467-2470` `pending_buys.discard` / `pending_buy_amounts.pop` / `_pending_buy_orders.pop`
- `:2489` `update_trade_status(... COMPLETED ...)`
- `:2552` `save_position` (DB `positions` 행)
- `:2571` `_completed_buy_orders.add`

---

## 2. 자기 자신이 세운 조건인가 — **그렇다. 그리고 100% 결정적이다**

`is_ticker_held_by_any` 는 **다른 전략만** 보지 않는다. `_strategies.values()` 전수이고 자기 자신이 포함되며, 조건도 `has_position` 이 아니라 `has_position OR is_buy_pending` 이다.

매수 당사자가 `:1138` 에서 스스로 `pending_buys` 에 넣고 그 뒤에야 `await` 로 양보하므로, **창 안에 착지한 우리 자신의 매수 체결통보는 예외 없이 이 조기 return 에 걸린다.** 확률적 사건이 아니다.

결함의 크기 판정에 직결되는 두 결론:

1. **로그 문구가 거짓이다.** `[buy_fill_fallback_held_conflict] … 이미 타 전략 보유 중 → momentum 폴백 skip` — 실측 2건 모두 *타 전략*이 아니라 **자기 전략**이고, *보유 중*이 아니라 **주문 중**이었다. 운영자가 이 ERROR 를 읽고 "다른 전략이 들고 있어서 중복을 막았구나" 로 읽으면 정확히 반대로 이해한다.
2. **가드의 원래 표적(미지 출처 체결)과 지금 잡히는 것(우리 자기 주문)이 섞여 있다.** 가드는 유지하되 **자기 주문을 먼저 건져내는 단**이 앞에 있어야 한다.

---

## 3. 실측 2건 — 이 경로가 맞다. 그리고 둘 다 우리 LTV 주문이다

운영 DB 조회(psql 세션 TZ=UTC, `ts AT TIME ZONE` 로 두 열 병기).

### 3.1 마커 쌍

| # | KST | UTC | level | 마커 |
|---|---|---|---|---|
| 330093 | 2026-08-26 14:44:11 | 2026-08-26 05:44:11 | WARNING | `종목 매핑 없음, payload ticker 사용: 078930` |
| 330095 | 2026-08-26 14:44:11 | 2026-08-26 05:44:11 | ERROR | `[buy_fill_fallback_held_conflict] order_no=0001329100 ticker=078930` |
| 362247 | 2026-08-31 08:13:16 | 2026-08-30 23:13:16 | WARNING | `종목 매핑 없음, payload ticker 사용: 161890` |
| 362249 | 2026-08-31 08:13:17 | 2026-08-30 23:13:17 | ERROR | `[buy_fill_fallback_held_conflict] order_no=0000042100 ticker=161890` |

같은 초에 짝으로 붙는다 = **매핑 부재 창 그 자체**다. `[buy_fill_strategy_lookup_fallback]`·`[buy_fill_fallback_orphan]` 은 보존 구간 전체에 **0건** — 즉 이 창에 착지한 매수 통보는 지금까지 **전부** 조기 return 으로 갔고, momentum 폴백으로 흘러간 적은 한 번도 없다.

### 3.2 그 종목이 그날 어떻게 됐나

```
078930 GS   BUY  COMPLETED long_tail_volatility 0001329100 129,100 ×1  08-26 14:44:11
078930 GS   SELL COMPLETED long_tail_volatility 0000285800 131,200 ×1  08-27 09:00:15  P/L +2,000
161890 콜마 BUY  COMPLETED long_tail_volatility 0000042100 171,700 ×1  08-31 08:13:16
161890 콜마 SELL COMPLETED long_tail_volatility 0000002300 160,200 ×1  09-01 08:00:18  P/L −11,200
```

둘 다 **LTV 자기 주문 1주**다. 수동 매매도 외부 주문도 아니다.
`trade_history` 가 COMPLETED 로 보이는 것은 `_handle_buy_fill` 이 고친 것이 아니라 `mark_pending_buys_completed`(`scheduler.py:3444`, `boot_manager.py:380-386`)가 **장부만** 뒤늦게 맞춘 것이다. **장부는 맞고 메모리는 비어 있었다** — 이 결함이 가장 고약한 지점이다. 대시보드·DB 어느 쪽을 봐도 정상으로 보인다.

### 3.3 매도가 난 이유 = 익일 `_boot` 이 되살렸다 (주장 정정 ①)

`boot_manager.py:317-378` 2차 「KIS 잔고 보완 복구」가 다음 날 아침 KIS 잔고에 있고 어느 전략도 안 들고 있는 종목을 `get_recent_buy_strategy`(→ LTV, 정확)로 되살린다. `:329` 에 `buy_dt = yesterday` 가 기본이고 그날 매수 주문이 없으니 그대로 → `is_next_day=True` → 익일청산 발화.

**그래서 익일청산은 멈추지 않았다.** 멈춘 것은 그날 하루의 **손절·트레일링·15:20 일괄청산**이다.

- 손절/트레일링: `risk.py:627` `registry.enabled()` 순회 → `:638` `pos = state.positions.get(ticker)` → `None` → `:686` `check_exit_signal` 분기 자체에 못 들어간다.
- 15:20: `strategies/long_tail_volatility.py:1093-1098` `check_force_clear` 가 `self.state.positions` 를 순회한다 → 빈 dict → **대상 0**.

### 3.4 잃은 것의 크기 (일봉 대조)

**161890 — 손절이 실제로 무력화됐다.**

| | |
|---|---|
| 매수 | 08-31 08:13 NXT 프리 **171,700** |
| 그날 KRX 시가 | **162,200** (−5.53% vs 체결가) · 고가 165,900 · **저가 155,400(−9.5%)** · 종가 160,100 |
| 운영 DB LTV 당일 손절 | `intraday_stop_loss = −5.0` → 손절선 **163,115** |
| 반사실 | 09:00 첫 틱이 이미 손절선 아래 → **09:00 ≈162,200 손절, −9,500(−5.5%)** |
| 실제 | 09-01 08:00:18 **160,200**, **−11,200(−6.52%)** |
| 차이 | 추가 손실 −1,700 + **하루 전체 무방비 노출**(저가 −9.5% 순간에 청산 시스템은 아무것도 보고 있지 않았다) |

프리장에서 171,700 에 사서 KRX 가 162,200 에 열었다 — NXT 프리 프리미엄이 개장과 함께 증발한 전형이다. 이런 랏이야말로 09:00 손절이 존재 이유인데, 정확히 그 랏이 감시 밖이었다.

**078930 — 결함 덕에 오히려 벌었다.** 매수 129,100(08-26 14:44, 그날 고가 129,700 근처) → 15:20 일괄청산 대상에 오르지 못해 밤을 넘김 → 08-27 시가 130,200 갭업 → 09:00:15 익일청산 131,200, **+2,000**. 15:20 에 정상 청산됐다면 종가권 ≈127,700 근처(추정)라 대략 **−1,100 ~ −1,400** 이었을 것이다.

> 🔴 **이 결함은 손익 결함이 아니라 통제 결함이다.** 표본 2건의 기대값은 거의 상쇄된다(+2,000 / −1,700). 바뀌는 것은 **분산**이다 — 손절이 꺼진 랏은 좋은 쪽으로도 나쁜 쪽으로도 꼬리가 열린다. 트레이더 어법으로 "브레이크를 뗀 채 달렸는데 이번엔 직선이었다" 이고, 실적표로는 절대 드러나지 않는다.

### 3.5 빈도

- WARNING+ 보존 구간 = 2026-08-20 07:50 ~ 2026-09-18 21:30 (retention 30일)
- 같은 구간 `trade_history` BUY COMPLETED = **96건 / 22 영업일**
- 이 창 착지 = **2건 → 2.1% (약 월 2회)**

96건 중 2건이면 드물지만, **1주 랏에 집중**된다는 점이 중요하다. 1주 주문은 단일 통보로 전량 체결되므로 **두 번째 통보가 없다** = 자기 치유 경로가 구조적으로 없다. 다주 랏이면 잔여 통보가 `src=map` 으로 와서 `pos` 를 만들어 준다. 그리고 메모리 [랏 기하] 에 따르면 우리 매수의 **상당수가 1주**다(donchian 76% · kojiro 52%) — 즉 **지금 포트폴리오 구성이 이 결함의 노출을 극대화하는 쪽**이다.

---

## 4. 복구 경로가 정말 없는가 — 15분 sync 는 **구조적으로** 못 고친다

`scheduler._sync_positions_from_balance`(`scheduler.py:3424`):

```
3436  for h in holdings:
3444      await mark_pending_buys_completed(h.ticker)     ← 장부만 고친다
3447      if self.registry.is_ticker_held_by_any(h.ticker):
3448          continue                                     ← 여기서 빠진다
3452      strategy_id = await get_recent_buy_strategy(...)  ← 도달 못 함
3457      target.state.positions[h.ticker] = Position(...)  ← 도달 못 함
```

`:3447` 이 **같은 함수** `is_ticker_held_by_any` 를 쓴다. `pending_buys` 는 `:2467` 에 못 갔으므로 그대로 남아 있고, 따라서 sync 는 매번 `continue` 한다. `pending_buys` 가 실제로 비는 시각은 **21:30 `_reset_daily_state`**(`scheduler.py:3597-3602` `pending_buys.clear()` / `pending_buy_amounts.clear()`)다. 그때는 이미 `_scan_loop` 이 죽어 sync 가 돌지 않는다.

게다가 호출 위치 자체도 늦다 — sync 는 `_scan_loop` 안 3회차마다(`scheduler.py:2522-2527`)이고 `_scan_loop` 은 09:30 에야 생긴다. **161890(08:13 체결)의 경우 첫 sync 기회 자체가 09:45 였고, 그마저 위 `continue` 로 무효였다.**

부수 피해 하나 더: `pending_buy_amounts[ticker]` 도 남아 그날 내내 LTV 예산을 점유한다(`_calc_used_funds`). 포지션은 없는데 예산만 묶인다.

**결론 = 실질 복구는 익일 `_boot` 하나뿐이다.** 블라인드 창 = 체결 시각 ~ 다음 영업일 07:45~07:55. 실측 **약 17시간(078930) / 약 23.7시간(161890)**, 그중 실매매 구간만 각각 36분 + NXT 애프터 / **08-31 온종일**.

---

## 5. cycle329 가 이것을 바꿨는가 — **행위는 0. 그런데 순서 관계가 중요하다**

### 5.1 행위 영향 없음

cycle329 가 넣은 3단(`map`→`payload`→`increment`, `order_engine.py:2253-2270`)과 overrun 클램프(`:2290`)는 전부 `_handle_buy_fill` **호출 전**에서 `ordered_qty` 를 정하고, 조기 return(`:2421`)은 `ordered_qty` 를 **한 번도 쓰지 않고** 돌아간다. 도달 빈도도 결과도 불변이다.

### 5.2 그런데 — cycle329 의 **매수 축 서사는 이 조기 return 때문에 오늘까지 도달 불가였다**

`src/engine/CLAUDE.md` 「체결통보 주문수량 — 출처 3단」이 적은 매수 축 피해는 이렇다:

> 매수는 `_completed_buy_orders` 가 무장해 잔여 통보가 `[buy_fill_duplicate_ignored]` 로 조용히 버려진 채 … 10주를 갖고 3주로 믿는 상태가 익일 `_boot` 까지 간다

그 상태가 되려면 `:2472` 전량 분기와 `:2571` `_completed_buy_orders.add` 에 **닿아야** 한다. 그런데 §2 에서 본 대로 **우리 자기 주문은 예외 없이 `:2421` 에서 되돌아간다.** 즉 매수 축에서 그 시나리오는 "우리 주문이 아닌 어떤 매수"(= 미지 출처)에만 성립했고, 실측상 그런 건은 0건(`[buy_fill_strategy_lookup_fallback]` 0행)이다.

**그래서 두 사이클은 순서 의존이다:**

- cycle331 만 하고 cycle329 가 없었다면 → 창에 착지한 **부분** 체결이 처음으로 `:2472` 에 도달하면서 `ordered_qty=increment` 폴백 때문에 **전량으로 오판** + `_completed_buy_orders` 무장 = cycle329 가 고친 그 결함을 **새로 활성화**했을 것이다.
- cycle329 가 먼저 착지한 지금 순서가 **정확하다.** cycle331 은 cycle329 의 매수 축을 비로소 유효하게 만드는 후속이다.

이건 좋아진 것도 나빠진 것도 아니라, **cycle331 의 선행 조건이 이미 충족돼 있다**는 뜻이다. 그대로 진행해도 된다.

### 5.3 덤으로 관측이 하나 생겼다

`_emit_fill_qty_src`(`:2300`)가 `_handle_buy_fill` **앞**에서 `src=payload` 를 WARNING 으로 남긴다(`src=map` 은 DEBUG). 이 창이 열리면 **조기 return 여부와 무관하게** 마커가 뜬다. `[fill_qty_src] src=payload side=BUY` + 같은 초의 `[buy_fill_fallback_held_conflict]` = **이 결함의 서명**이다. 시정 뒤 판독 기준으로 그대로 쓴다.

> 배포 확인: EC2 `.deployed_sha = 297d3356…` = cycle329 포함. `[fill_qty_src]` 는 `system_logs` 0행인데, 배포 이후 아직 창이 안 열렸기 때문이다(`src=map` 은 DEBUG 라 애초에 DB 에 안 남는다).

---

## 6. 시정 방향

### 6-(a) 조기 return 을 없애면 무엇이 깨지는가 — **없애면 안 된다. 좁혀야 한다**

그 가드의 정체는 P1-B (B-2)(docstring `:2379-2380`)다. 막으려던 것 = **출처를 모르는 매수 체결을 `momentum` 이라고 우겨서 이미 누가 들고 있는 종목의 포지션을 덮어쓰는 것**(377450 사고).

오늘 그 표적이 여전히 유효한 잔여 시나리오:

1. **수동/외부 매수**(MTS·HTS·영업점) — 매핑 없음 + trade_history 행 없음(`_sync_orders_to_db` 이전). 그 종목을 어떤 전략이 들고 있으면, momentum 에 포지션을 만들면 실제 소유 전략의 포지션과 이중 장부가 된다.
2. **재기동 직후 race** — 매핑은 비었는데 PENDING 행도 아직 없는 짧은 창.

그러니 **가드는 살려 두고, 그 앞에 「이 체결의 주인이 누구인지 in-memory 로 아는 단」을 하나 더 넣는다.**

### 6-(b) 우리 주문과 수동·외부 주문을 가르는 식별자 = `pending_buys` 단독 소유

`order_no` 는 KIS 응답 전까진 존재하지 않으므로 **주문번호 축으로는 원리상 가를 수 없다**(클라이언트 주문 ID 를 실을 자리가 국내주식 주문 TR 에 없다). 유일하게 창 안에서 이미 참인 사실은 **"그 전략이 그 종목의 매수 주문을 방금 냈다"** 이고, 그것이 곧 `pending_buys` 다.

**A안 (권고) — 폴백 체인에 `pending` 귀속 단을 하나 끼운다**

```
현행:  map → trade_history → [held/pending 이면 return] → momentum
권고:  map → trade_history → pending 단독 소유자 → [held/pending 이면 return] → momentum
```

`pending 단독 소유자` 판정(전부 in-memory, `await` 0):

- `registry.all()` 순회로 `ticker in s.state.pending_buys` 인 전략을 모은다
- **정확히 1개**이고, 그 전략의 `state.positions` 에 그 ticker 가 **없을** 때만 채택
- 0개 또는 2개 이상 → **채택하지 않고 현행 그대로**(조기 return 유지) = fail-open, 결과 집합 ⊆ 현행

왜 이게 안전한가:

- 채택 조건이 성립하면 그 전략은 **정의상** 방금 그 종목 매수를 발사했고 아직 체결 처리를 못 받은 전략이다. 우리 주문의 귀속으로 이보다 강한 증거는 없다.
- `execute_buy` 진입 가드 2중(`:1038` 자기 중복 · `:1042` `registry.is_ticker_blocked_for_buy`)이 "한 종목은 한 전략만 pending" 을 사실상 보장한다. 드문 race 로 2개가 되면 위 `== 1` 조건이 스스로 물러선다.
- 수동/외부 매수는 우리 `pending_buys` 에 없으므로 **건드리지 않는다** — B-2 의 표적은 그대로 잡힌다.

**B안(창 자체를 없앤다)은 불가능**하다 — `order_no` 를 미리 알 방법이 없다.
**C안(조기 return 시 통보를 스택해 1~2초 뒤 재처리)은 비권고** — `_filled_qty` 는 이미 증가했으므로 재처리가 이중 계상 경로를 새로 열고, 비동기 순서 뒤집힘을 감수하면서 얻는 것이 A안과 같다.
**D안(15분 sync 백스톱)은 별건 권고** — §6-(d).

### 6-(c) `handle_execution_notice` 는 hot path 다 — `await`·DB 를 넣어도 되는가

**A안은 넣을 필요가 없다.** 판정이 전부 메모리 dict/set 조회다.

사실 관계만 정리하면: 이 경로는 이미 `await` 를 쓴다(`:2409` trade_history 조회, `:2489` `update_trade_status`, `:2552` `save_position`). 금지되는 것은 **예외를 밖으로 내보내는 것**이다 — `src/realtime/handler.py:709-720` 이 `_on_execution` 예외를 `logger.exception` 후 **`raise` 한다**(설계된 규약, `_receive_loop` 로 전파 → WS 재연결). 그래서 새 단은:

- `try/except Exception` 으로 통째로 감싸고, 실패하면 **현행 조기 return 으로 낙하**(never-raise, fail-open)
- 마커 emit 실패도 행위를 바꾸지 않는다(관측은 판정 밖)
- `await`/DB/HTTP 신규 0 — A-PURE 계열 규약과 같은 결로 유지한다(이 함수는 `_apply_budget_limit` 관문이 아니므로 AST A-PURE 대상은 아니지만, 굳이 hot path 에 왕복을 얹을 이유가 없다)

### 6-(d) 백스톱(별건 권고, 이번 사이클에 넣지 말 것)

`scheduler.py:3447` 의 `is_ticker_held_by_any` 를 **보유 축만 보는 별도 헬퍼**(예: `is_ticker_position_held_by_any` = `has_position` 만)로 바꾸면 블라인드 창이 17~24시간 → **≤15분**(09:30 이후)으로 줄고, `get_recent_buy_strategy` 가 LTV 를 정확히 돌려주므로 귀속도 맞다.

**그런데 이번 사이클에 묶지 말 것을 권고한다.** 이유:

- `is_ticker_held_by_any` 소비처가 5곳(`order_engine.py:2324` 구독 정리 · `boot_manager.py:324,435` · `stale_universe_guard.py:78` · `scheduler.py:3447`)이고 각자 `pending` 을 참으로 치는 데 다른 이유가 있다. 한 함수를 바꾸면 광역 회귀다.
- A안이 근본 시정이고, A안이 들어가면 `pending_buys` 고착 자체가 사라져 D안의 실익이 급감한다.
- 승인 면적이 `order_engine.py`(8영역) 하나에서 `scheduler.py`(라인 상한)까지 번진다.

### 6-(e) 함께 고칠 것 — 로그 문구

`:2417-2419` 의 `"이미 타 전략 보유 중"` 은 실측상 거짓이다. `"타 전략 보유/주문중"` 로 정정하고 판정 근거(`held=`/`pending_owner=`)를 필드로 싣는다.
⚠️ **21:30 리포트 주의** — `log_analysis_engine._normalize_message` 가 메시지 전문을 패턴 키로 쓰므로 **변경일 전후의 `top_patterns` 문자열을 비교하지 않는다**(cycle328 폴백 문구 통일과 같은 주의).

---

## 7. 이 시정이 만들 수 있는 새 결함 — **부분 체결 잔량 취소 타이머의 오발**

**시나리오.** A안으로 귀속이 열리면, 창에 착지한 통보가 **처음으로** 부분 체결 분기(`:2584-2592`)에 도달한다. 거기서 `self._schedule_cancel(ticker, order_no, ordered_qty, strategy_id)` 가 걸리고 `_cancel_after_wait`(`:2770`)가 `PARTIAL_FILL_WAIT=30초` 뒤 **잔량을 취소**한다.

귀속이 틀린 랏(= §6-(b) 의 판정이 어떤 이유로 잘못 채택된 경우, 특히 `boot_manager.py:442` 가 KIS 미체결 주문으로 seed 한 `pending_buys` 가 남아 있는 상태)에서 이 타이머가 걸리면 **사람이 낸 주문을 우리가 30초 뒤 취소한다.** cycle327(「주문이 나간 뒤의 실패로 재발사 금지」)·cycle329(「재주문 타이머는 `qty_src == "map"` 일 때만」)와 **정확히 같은 계열**의 사고다.

**막는 법 — cycle329 의 선례를 그대로 대칭 적용한다.**

> 귀속 출처가 `map` 이 **아닌** 랏(= `pending` 단으로 건진 랏, 그리고 `qty_src != "map"`)에는 **`_schedule_cancel` 을 걸지 않는다.** 보류 사실은 `[buy_partial_no_cancel_timer] order_no= ticker= strategy= src=` WARNING 1행으로 남긴다.

**잃는 것이 없다.** 우리 자신의 주문이라면 `place_order` 가 곧 돌아와 매핑이 서고, 잔여 통보는 ms~초 뒤 `src=map` 으로 와서 정상적으로 타이머를 건다. 사람 주문이라면 애초에 우리가 취소할 일이 아니다.

---

## 8. 관측 — 시정이 「열렸다」는 것을 무엇으로 아는가

| 마커 | 레벨 | cap | 뜻 |
|---|---|---|---|
| `[buy_fill_strategy_from_pending] order_no= ticker= strategy= qty_src= incr= filled_total= ordered= pending_owners=` | **WARNING** | **무cap** | **새 마커.** `pending` 단으로 귀속이 성립해 포지션이 실제로 등록됐다. **시정의 성공 서명** |
| `[buy_fill_fallback_held_conflict]`(기존) | ERROR | 무cap | 시정 뒤에는 **진짜 미지 출처만** 남아야 한다 → **0 에 수렴이 정상** |
| `[fill_qty_src] src=payload side=BUY`(cycle329 기존) | WARNING | `KstDailyEmitCap[(src,ticker,side)]` | 같은 초에 위 새 마커와 **짝으로** 뜨는 것이 이 창의 서명 |
| `[buy_partial_no_cancel_timer]`(§7) | WARNING | 무cap | 잔량 취소 타이머를 일부러 안 걸었다 |

**cap 정책 근거.** `KstDailyEmitCap` 관례를 따르되 **키를 `order_no` 로 잡으면 사실상 무cap** 이고, `(ticker, strategy)` 로 묶으면 **같은 날 두 번째 사건이 사라진다**. 이 사건은 실측 빈도가 **96건 중 2건(2.1%)** 이고 **한 건 한 건이 조사 단위**다. 형제 마커 `[buy_fill_fallback_held_conflict]` 도 오늘 무cap ERROR 다. → **무cap WARNING 권고.** WARNING 이상만 21:30 `top_patterns` 에 오르므로 리포트에도 자연히 실린다.

**일일 요약(선택).** cycle329 `[fill_qty_src_summary]` 선례를 따라 `_settle()` 직전 `[buy_fill_from_pending_summary] window=day n= conflict_remaining=` 1행. `n>0` 이면 그날 창이 열렸고 **우리가 막았다**, `conflict_remaining>0` 이면 미지 출처 체결이 실제로 있었다 = 별도 조사. 호출부는 **try/except 로 감싸지 않는다**(scanner 일일 summary 2종과 같은 이유).

**D+1 판독 절차.**

1. `[buy_fill_strategy_from_pending]` 가 1행이라도 있으면 → 그 `ticker` 로 `trade_history` BUY 와 `positions` 를 대조. **같은 날 안에** 포지션이 있으면 성공.
2. `[fill_qty_src] src=payload side=BUY` 는 있는데 위 마커가 없으면 → 새 단이 채택되지 않았다(`pending_owners != 1`). 그 값을 보고 race 를 판단.
3. `[buy_fill_fallback_held_conflict]` 가 남으면 → 그 `order_no` 를 KIS 주문내역과 대조해 **수동/외부 주문인지** 확인. 우리 주문이면 시정이 덜 됐다는 뜻이다.

---

## 9. 정본과의 정합성 / 승인 면적

### 충돌 없음 (검토 결과)

| 정본 규칙 | 판정 |
|---|---|
| 「주문번호 매핑 등록은 `place_order` 응답 직후 동기 영역, `await insert_trade` 진입 전」 | **무접촉** — `execute_buy` 는 한 글자도 안 바뀐다 |
| 「체결통보 선행 race 가드(`_completed_orders` + 보정 INSERT) 제거 금지」 | **무접촉** — 그 아래 분기는 그대로 |
| P1-B (B-1) `_completed_buy_orders` 멱등 | **무접촉**(`:2395`, 새 단보다 앞) |
| P1-B (B-2) 폴백 안전 | **좁히는 것이지 없애지 않는다** — 377450(동일 order_no 2차 통보)는 B-1 이 1차 방어, B-2 는 미지 출처 전용으로 남는다 |
| AST G-161-K-6(`update_trade_status` 에 `price=` 의무) | **무접촉** — 새 분기는 기존 분기로 합류 |
| `handler` 콜백 `raise` 의무 | **준수** — 새 단은 자체 try/except never-raise |
| `_apply_budget_limit` A-ATOMIC / A-PURE | **무접촉** — 다른 함수다 |
| 「`tradable_boards` 는 매수 진입 전용, 청산은 항상 작동」 | **이 시정이 그 규칙을 복원하는 쪽**이다 — 지금은 포지션이 없어 청산 자체가 성립하지 않았다 |

### 2026-09-14 제도 변경 관련

이 결함은 보드·호가유형과 무관하다(귀속 축). 다만 실측 1건이 **NXT 프리장 08:13** 이라는 점은 짚는다 — 프리장 매수는 `step_up(현재가,5)` 지정가/GTP(27)라 **즉시 전량 체결이 잦고 1주 랏이 많다** = 이 창에 가장 잘 걸리는 코호트다. `src/engine/CLAUDE.md` `session.py` 절 시간표와 충돌 없음.

### 승인 대상 (명시)

- `src/engine/order_engine.py` = **8영역 → 승인 필요**
- 그리고 **매매 행위를 바꾼다**(포지션 등록 = 손절·트레일링·15:20 청산 규약이 살아난다) → 사용자 결정 + `domain-consult` 선행 = **이 문서**
- **변경 면적 권고 = `order_engine.py` 1파일.** `scheduler.py`·`strategy_registry.py`·`boot_manager.py`·전략 7파일 **무접촉**
- `is_ticker_held_by_any`(`strategy_registry.py:69`) 자체는 **건드리지 않는다** — 소비처 5곳 광역 회귀. 새 단은 `_handle_buy_fill` 안에서 registry 를 **읽기만** 한다

---

## 10. 반례 / 한계

1. **두 전략이 같은 ticker 를 동시에 pending** — `:1042` 중복 가드와 `:1138` `pending_buys.add` 사이에 `await get_buyable`(`:1079`)이 있어 이론적 race 가 있다. `pending_owners == 1` 조건이 그 경우 스스로 물러서므로 **현행보다 나빠지지 않는다**(fail-open).
2. **수동 매수가 정확히 그 ~100ms 창에 같은 종목으로 체결** — 확률 ≈0. 설령 일어나도 우리 주문의 다음 통보가 `src=map` 으로 수량을 덮어 오늘과 같은 상태로 수렴한다.
3. **`pending_buys` 가 다른 이유로 고착된 상태** — `boot_manager.py:442` 가 KIS 미체결 주문으로 seed 하는 경로가 있다. 그 종목의 미지 체결이 오면 귀속이 그 seed 로 간다. §7 의 취소 타이머 게이트가 이 경우의 최악(사람 주문 취소)을 막는다.
4. **`payload` 가 안 실려 오는 KIS 응답** — cycle329 가 이미 적어 둔 사각이다. 그 경우 부분 체결이 전량으로 오판되는 위험이 A안과 함께 되살아날 수 있으므로, **`qty_src == "increment"` 인 랏에는 `pending` 귀속을 적용하지 않는 것**도 선택지다(더 보수적). 실측상 `increment` 발생 빈도가 0으로 관측되면 완화한다.
5. **표본이 2건이다.** 30일 보존 한계라 그 이전 사건은 볼 수 없다. 빈도 2.1% 는 2026-08-20~09-18 구간의 값이고, **순자산 증액(09-20) 이후 랏이 2배가 되면 1주 랏 비중이 줄어 빈도가 자연 감소할 수 있다** — 그래도 시정은 필요하다(1주 랏이 0이 되지 않는다).
6. **이 시정이 돈을 벌어 주지는 않는다.** §3.4 가 보여주듯 표본 기대값은 거의 상쇄다. 사는 것은 **통제**이고, 통제의 가치는 꼬리에서만 회수된다.

---

## 11. 후속 검증 권고 (tdd-engineer / tester)

**Red 테스트 5케이스**(전부 `_handle_buy_fill` 단위, respx 불요):

| # | 입력 | 기대 |
|---|---|---|
| R1 | 매핑 5종 비움 + trade_history miss + LTV `pending_buys={t}` + `positions={}` + 전량 통보 | LTV `positions[t]` 등록 · `pending_buys` 비움 · `[buy_fill_strategy_from_pending]` 1행 · `[buy_fill_fallback_held_conflict]` **0행** |
| R2 | 같은 조건 + **부분** 통보(`ordered=10, incr=3`) | LTV `positions[t].quantity == 3` · PARTIAL UPDATE · **`_schedule_cancel` 미호출** + `[buy_partial_no_cancel_timer]` 1행 |
| R3 | R2 뒤 잔여 통보가 **매핑 있는 상태**(`src=map`)로 도착 | `positions[t].quantity == 10` · 전량 분기 · `_completed_buy_orders` 무장 |
| R4 | 매핑 miss + trade_history miss + **어느 전략도 pending 아님** + momentum 이 그 종목 보유 중 | **현행 그대로** `[buy_fill_fallback_held_conflict]` + return (B-2 보존) |
| R5 | 매핑 miss + **두 전략**이 같은 ticker pending | **현행 그대로** 조기 return (fail-open, `pending_owners=2` 필드 확인) |

**회귀 보존 확인**: `tests/unit/engine/test_cycle329_mapping_absent_full_fill.py` 5케이스 전부 초록 유지(매도 축 무접촉 증명).

**AST/구조 가드 제안**:

- `_handle_buy_fill` 안에서 새 단이 `await` 를 쓰지 않는다(신규 `Await` 노드 0건, 폴백 체인 구간 한정)
- `_schedule_cancel` 호출이 `qty_src`/귀속 출처 게이트 **안쪽**에 있다(cycle329 SELL 축 게이트와 대칭)
- `strategy_registry.is_ticker_held_by_any` 소스 무변경(sha 핀)

**운영 실측(D+1)**: §8 판독 절차 3단계. 추가로 **시정 배포 후 첫 「1주 매수 + 즉시 전량 체결」 이 난 날**에 그 종목의 `positions` 가 **같은 날 안에** 존재했는지를 `GET /api/trading/status` 로 확인한다 — 그것이 이 사이클이 실제로 무엇을 되찾았는지의 유일한 직접 증거다.

---

## 부록 — 인용한 파일:행

```
src/engine/order_engine.py:1038,1042           execute_buy 중복 매수 가드 2중
src/engine/order_engine.py:1138-1141           pending_buys.add / pending_buy_amounts / order_attempt_today
src/engine/order_engine.py:1146,1262           await 2개 (창의 시작·본체)
src/engine/order_engine.py:1270-1290           매핑 5종 + _pending_buy_orders 동기 등록
src/engine/order_engine.py:2194,2211-2213      handle_execution_notice / _order_ticker.get
src/engine/order_engine.py:2227                "종목 매핑 없음, payload ticker 사용" WARNING
src/engine/order_engine.py:2253-2270,2290,2300 cycle329 3단 · overrun 클램프 · [fill_qty_src]
src/engine/order_engine.py:2359,2395-2403      _handle_buy_fill / _completed_buy_orders 멱등
src/engine/order_engine.py:2406-2411           _order_strategy.get → trade_history 폴백
src/engine/order_engine.py:2415-2421           [buy_fill_fallback_held_conflict] 조기 return  ← 본건
src/engine/order_engine.py:2441-2451           Position 신규 등록 + fill_count_today
src/engine/order_engine.py:2467-2470           pending_buys.discard / pending_buy_amounts.pop
src/engine/order_engine.py:2472,2489,2552,2571 전량 분기 · update_trade_status · save_position · _completed_buy_orders.add
src/engine/order_engine.py:2584-2592,2770      부분 분기 · _schedule_cancel · _cancel_after_wait
src/engine/strategy_registry.py:69-74          is_ticker_held_by_any (has_position OR is_buy_pending)
src/engine/strategy_base.py:121                is_buy_pending
src/db/trade_history.py:201-243                _lookup_strategy_from_trade_history (ticker+order_no+PENDING/PARTIAL)
src/engine/scheduler.py:2522-2527              sync 호출부 (_scan_loop 3회차 = 15분)
src/engine/scheduler.py:3424,3436-3448         _sync_positions_from_balance · is_ticker_held_by_any continue
src/engine/scheduler.py:3452-3463              복구 등록 (도달 못 함)
src/engine/scheduler.py:3597-3602              _reset_daily_state pending_buys.clear
src/engine/boot_manager.py:317-378             익일 KIS 잔고 보완 복구 (실질 유일 복구 경로)
src/engine/boot_manager.py:324-325,329,442     is_ticker_held_by_any continue · buy_dt=yesterday · 미체결 seed
src/engine/risk.py:627,638,686                 enabled() 순회 → positions.get → check_exit_signal
src/engine/strategies/long_tail_volatility.py:1093-1098   check_force_clear (state.positions 순회)
src/realtime/handler.py:689-698,709-720        ODER_QTY 파싱 · 콜백 예외 raise 규약
```

운영 DB 근거: `system_logs` id 330093/330095/362247/362249 · `trade_history` order_no 0001329100/0000042100 ·
`stock_master_daily` 078930(08-25~08-28)·161890(08-27~09-02) · `strategy_config.long_tail_volatility.params` ·
보존 구간 2026-08-20 07:50 ~ 2026-09-18 21:30 의 BUY COMPLETED 96건/22영업일.
