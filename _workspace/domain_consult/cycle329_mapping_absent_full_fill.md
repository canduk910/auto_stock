# cycle329 자문 — 매핑 부재 창의 전량 오판, 무엇을 어떻게 고치는가

> 요청: team-leader (2026-09-20) · 선행 문서 `_workspace/refactor/2026-09-20_step1_gate_domain.md` §5
> 대상: `src/engine/order_engine.py` (8영역) · `src/realtime/handler.py` (8영역, 조건부)
> 성격: **매매 행위 변경(청산 규약)** — 승인 + 이 자문 선행이 의무인 축

---

## 결론 먼저

**① 사후 추론으로 "우리 주문인가"를 가르려 하지 마라. 발사 시점에 사실을 남겨라.**

축 (a)를 "매핑 부재를 어떻게 해석할 것인가"의 문제로 놓으면 team-leader 가 우려한 맞바꿈
(우리 주문 오판 ↔ 수동 매매 오판)이 **반드시** 생긴다. 그런데 그 맞바꿈은 문제의 성질이 아니라
**문제를 놓은 자리**에서 나온다. `await place_order` 도중에 우리가 모르는 것은 `order_no` 뿐이고,
**`ticker` 와 `주문수량` 은 이미 손에 있다.** 그 둘을 발사 **전**에 적어 두면 매핑 부재 상태에서도
"이건 우리가 방금 낸 주문이다 + 수량은 N 이다" 를 **동기 dict 조회 한 번**으로 확정할 수 있다.

그러면 수동 매매 경로는 **한 글자도 바뀌지 않는다**(우리가 적은 적이 없으므로 조회가 miss →
현행 폴백 그대로). 맞바꿈이 사라진다.

**② 축 (b)는 축 (a)와 독립이 아니다 — (b)가 (a)의 앞 절반이다.** (b)가 만드는 지역 변수
`ordered_qty`(발사 전 확정)가 곧 ①이 적어 둘 값이다. 둘을 쪼개면 같은 줄을 두 번 건드린다.

**③ 매수 축이 더 위험하다.** 같은 창이 `execute_buy` 에도 있고, 피해가 **자기 치유되지 않는다**
(아래 3절). 사이클을 쪼갤 거면 매도가 아니라 **매수를 먼저** 고쳐야 할 정도다. 한 커밋 권고.

**④ 가장 그럴듯한 새 결함 = `_schedule_cancel_and_reorder` 가 새로 도달한다.** 그리고
`_cancel_and_reorder` 에는 **포지션 재조회가 없다**(아래 「정정」). 시정의 부수효과로 신규 매도
주문이 나가는 경로가 열리므로, 그 경로를 명시적으로 닫는 것이 이 사이클의 필수 동반 조항이다.

---

## 🔴 먼저 — 관문 문서의 사실 두 개를 정정한다

### 정정 1 — `_cancel_and_reorder` 에 포지션 재조회는 **없다**

관문 문서 §5.3 이 이렇게 적었다.

> `_cancel_and_reorder` 는 `:2855` 에서 `positions.get(ticker)` 를 다시 읽어 None 이면 빠지므로
> 중복 매도까지 가지는 않지만, 그건 우연한 방어이지 설계된 방어가 아니다.

**`:2855` 는 `cancel_remaining`(`order_engine.py:2850`)이고 `_cancel_and_reorder`(`:2701-2834`)와
다른 함수다.** `_cancel_and_reorder` 본문 전체에 `positions` 참조가 **0건**이다 —
`sleep(30)` → `_market_rest_gate` → `cancel_order` → `update_trade_status(CANCELLED)` →
`place_order(quantity=remaining)`(`:2796-2810`) 이고, 중간에 보유를 확인하는 문장이 없다.

즉 **우연한 방어조차 없다.** `remaining` 이 어떤 값이든 그대로 매도 주문이 나간다. 이 사실이
6절(새 결함)의 무게를 바꾸므로 먼저 적는다.

### 정정 2 — 실측 2건의 시각을 다시 확인해 달라 (UTC 의심)

> 시각 05:44 · 23:13 KST = 엔진 운영 창(07:45~21:30) **밖**

**EC2 는 UTC 다**(메모리 `feedback_exact_instructed_values` 의 실측 항목). `system_logs.timestamp`
는 TIMESTAMPTZ 이고, 우리 규약은 **읽을 때 `to_char(..., '+09:00')` 캐스트를 건다**
(`src/db/CLAUDE.md`). 캐스트 없이 psql 로 조회했다면 세션 타임존(UTC)으로 렌더된다.

- 05:44 UTC → **14:44 KST** (KRX 정규장 한복판)
- 23:13 UTC → **08:13 KST** (NXT 프리장 한복판)

둘 다 **장중**이다. "운영 창 밖이라 무해" 라는 읽기가 뒤집힌다. 재확인 한 줄:

```sql
SELECT to_char(timestamp, 'YYYY-MM-DD HH24:MI:SS+09:00') AS kst, log_level, message
FROM system_logs
WHERE message LIKE '%주문번호%에 대한 종목 매핑 없음%'
ORDER BY timestamp DESC;
```

시정 결정 자체는 이미 사용자가 내렸으니 이 확인이 착수를 막지는 않는다. 다만 **빈도 추정과
보고서 문구**가 달라진다("한 번도 장중에 안 열렸다" vs "33일에 2번 장중에 열렸다").

---

## 1. 축 (a) — 매핑 부재 상태의 수량 판정

### 1.1 판정에 쓸 수 있는 신호 전수 — 그 순간 실제로 믿을 수 있는가

`handle_execution_notice`(`:2112`) 진입 시점, `known_ticker is None` 인 상태에서 읽을 수 있는 것.

| # | 신호 | 그 순간 상태 | 신뢰도 | 판정에 쓸 수 있나 |
|---|---|---|---|---|
| 1 | `_order_ticker.get(order_no)` (`:2127`) | **없다** | — | 창의 정의 자체. 쓸 수 없다 |
| 2 | `_order_qty` (`:2158`) | **없다**(`:1619`/`:1188` 이 await 뒤) | — | 쓸 수 없다 |
| 3 | `_order_strategy` | **없다**(같은 동기 블록) | — | 쓸 수 없다 |
| 4 | `_order_exchange` / `_order_division` | **없다**(같은 블록 `:1622`/`:1625`) | — | 쓸 수 없다 |
| 5 | `_pending_buy_orders` (`:1203`) | **없다**(같은 블록) | — | 쓸 수 없다 |
| 6 | **`self._selling`** (`:1425`) | **있다** — `place_order` **전**에 `add` | 높음 | ✅ "이 종목을 지금 우리가 팔고 있다" |
| 7 | `self._selling_since[ticker]` (`:1426`) | 있다 | 높음 | 나이(창 안이면 ms~초) |
| 8 | **`state.pending_buys`** (`:1056`, 폴백 `:1306`) | **있다** — `place_order` 전 | 높음 | ✅ 매수 축의 대응물 |
| 9 | `state.pending_buy_amounts[ticker]` (`:1058`) | 있다 | 중 | **원** 단위라 주식 수가 안 나온다(`÷ 현재가` 는 사전 변환·호가 반올림으로 어긋난다) |
| 10 | `registry.is_ticker_held_by_any(ticker)` | 있다 | **낮음** | 보유 종목의 **수동 매도**도 참이다 — 단독으로는 가르지 못한다 |
| 11 | `_filled_qty.get(order_no)` (`:2162`) | 2번째 통보부터만 | 중 | 첫 통보(= 창의 본체)에선 0 |
| 12 | `_completed_orders` | 이 핸들러가 **하류에서** 넣는 값 | — | 순환 |
| 13 | `trade_history` 조회 | DB | 높음 | 🔴 **금지** — 아래 1.3 |
| 14 | **payload `fields[16] ODER_QTY`** | KIS 가 실어 보낸다 | ? | ✅ 이론상 정답. 단 **한 번도 읽어 본 적이 없다** — 아래 1.4 |

**핵심 관찰**: 6·8이 `place_order` **앞**에 세워지고, 1~5가 **뒤**에 세워진다. 지금 코드는
판정을 1~5(뒤)로만 하고 있다. 6·8(앞)을 쓰지 않는 것이 결함의 구조적 뿌리다.

### 1.2 그래서 판정식이 아니라 **기록**으로 푼다 (권고 = B안)

`_selling`/`pending_buys` 를 *판정식에* 쓰는 것(B′안)도 되지만, 그것들은 **불리언**이라
"우리 주문이다" 만 알려 주고 **수량을 안 알려 준다**. 수량이 없으면 전량 판정을 유보하는 것밖에
못 하고, 유보는 6절의 부작용을 만든다. 한 걸음 더 간다.

**B안 — 발사 전 in-flight 수량 기록**

```
# execute_sell 재시도 루프 안, place_order 앞
ordered_qty = pos.quantity                              # ← 축 (b)
self._inflight_ordered_qty[("SELL", ticker)] = ordered_qty   # ← 축 (a)
try:
    result = await place_order(..., quantity=ordered_qty, ...)
    self._order_qty[result.order_no] = ordered_qty      # 기존 자리·기존 순서
    ...
finally:
    self._inflight_ordered_qty.pop(("SELL", ticker), None)
```

그리고 `handle_execution_notice` 의 `:2158-2159` 를 이렇게 바꾼다.

```
known_ordered = order_no in self._order_qty
if known_ordered:
    ordered_qty, qty_src = self._order_qty[order_no], "map"
else:
    inflight = self._inflight_ordered_qty.get((side, ticker))
    if inflight and inflight > 0:
        ordered_qty, qty_src = inflight, "inflight"
    else:
        ordered_qty, qty_src = quantity, "increment"    # ← 현행 그대로
```

전량 판정(`_handle_sell_fill:2536` · `_handle_buy_fill:2352`)의 조건을
`total_filled >= ordered_qty` **∧ `qty_src != "increment"`** 로 바꾼다.

**이 설계가 맞바꿈을 없애는 이유:**

| 상황 | `_inflight` 조회 | 결과 |
|---|---|---|
| 창 2(우리 주문, 매핑 미등록) | **hit** — 우리가 방금 적었다 | 진짜 주문수량으로 정확 판정 |
| 수동 매매(MTS/HTS)·외부 주문 | **miss** — 우리가 적은 적이 없다 | `qty_src="increment"` → **현행 행위 유지** |
| 2번째 통보 이후 | `_order_qty` hit(창은 ms 만에 닫힌다) | 현행 그대로 byte 동일 |

즉 **수동 매매 경로는 행위 변경 0 이다.** team-leader 가 지목한 "두 오류를 맞바꾸는 선택" 이
아니라, 한쪽만 고치고 다른 쪽은 건드리지 않는다.

### 1.3 hot path 제약 — `await`·DB 조회를 넣어도 되는가

**안 된다. 그리고 B안은 넣을 필요가 없다.**

근거 셋:

1. `handle_execution_notice` 는 `realtime/handler.py:700` 의 `_on_execution` 콜백이고, 그
   콜백에서 예외가 나면 `raise` 규약(`src/realtime/CLAUDE.md` G-REJECT-1)에 따라
   **WebSocket 이 재연결된다**. 조회 하나가 느려지거나 던지면 체결통보 채널이 흔들린다 —
   그 채널이 죽으면 포지션 등록·손절이 통째로 멈춘다(루트 금기 1번).
2. 이미 같은 함수에 `_lookup_strategy_from_trade_history`(`:2289`/`:2506`)라는 DB 폴백이
   **하류에** 있다. 그러나 그것은 *전량/부분 판정 이후*가 아니라 *전략 귀속*이고, 무엇보다
   **판정 분기 앞에 새 `await` 를 넣으면 그 await 동안 또 다른 통보가 끼어드는 새 창**이 생긴다
   (지금 고치려는 결함과 같은 모양의 결함을 판정기 안에 심는 셈이다).
3. B안의 신호는 전부 **프로세스 메모리 dict 조회**다. 동기·O(1)·never-raise.

**결론: 동기 신호만으로 충분하고, 그래야 한다.**

### 1.4 payload `ODER_QTY`(fields[16]) — 매력적이지만 이번 사이클은 아니다

KIS 체결통보 정본(`docs/kis/domestic-stock-realtime.md:426`)에 **`[16] ODER_QTY 주문수량`** 이
있다. 이걸 쓰면 **수동 매매의 부분 체결까지** 정확히 판정된다(B안이 포기한 축).

그런데 이번 사이클에 넣지 말자고 권고한다. 이유 셋:

1. **우리는 그 인덱스를 한 번도 읽어 본 적이 없다.** `handler.py` 가 쓰는 최대 인덱스는
   `fields[13]`(CNTG_YN)이다. 0~13 이 맞는다는 실측 증거는 매일의 정상 체결이 주지만,
   **16 에 대한 증거는 0** 이다.
2. **이 payload 는 인덱스 오독 전과가 있다.** cycle235 가 바로 `[9]`↔`[16]` 을 뒤집어 읽어
   257720 포지션 과대 → 익일 전량 매도 APBK0400 를 냈다. 같은 자리다.
3. **모의(VTS) H0STCNI9 의 컬럼 수가 실전과 같은지 실측이 없다.** 정본은 같은 표에 묶어
   두었지만 그것은 문서의 사실이지 우리 실측이 아니다.
   (09-14 제도 변경은 체결통보 필드를 바꾸지 않았다 — 변경 대상은 실시간**체결가**의
   `MARKET_CLS_CODE` 와 실시간**호가**의 `ANTC_EXCH_CLS_CODE` 다. `docs/kis/README.md`
   「제도 변경 공지 반영」 절 확인함. 그래도 ②의 전과가 남는다.)

**권고 = shadow 먼저.** `handler.py` 가 `ordered_qty_payload` 를 **키워드 전용·기본값 None** 으로
넘기고(기존 5인자 호출 계약 무변경), 엔진은 **행위에 쓰지 않고** `_order_qty` 와 대조만 로그로
남긴다. 며칠 실측 뒤 일치가 확인되면 그때 `_inflight` 다음 순위로 폴백 체인에 편입한다.
그 단계가 오면 수동 매매 축까지 정확해진다 — **그러나 6절의 위험도 그때 같이 온다**(수동
주문에 우리가 취소·재주문을 거는 문제). 그때 판단하면 된다.

⚠️ AST 가드 `test_cycle235_ast_execution_qty.py` 는 `quantity = int(fields[16]` 만 금지한다.
다른 이름의 변수로 읽는 것은 막지 않으므로 충돌 없다. 다만 **그 가드의 의도를 존중해
`quantity` 근처에 두지 않는다**(예: `ordered_qty_payload`).

---

## 2. 축 (b) — 발사 시점 수량 고정

### 2.1 (b) 단독으로 무엇이 닫히고 무엇이 남는가

**닫히는 것: 거의 없다.** 매도 경로에서 `await place_order` 도중 `pos.quantity` 를 바꿀 수 있는
경로를 전수 확인했다.

| 변경 주체 | 도달 가능성 |
|---|---|
| `_handle_buy_fill:2343` (`pos.quantity = total_filled`) | `registry.is_ticker_blocked_for_buy` 가 보유 종목 매수를 막아 정상 흐름 도달 0 |
| `execute_sell:1803` (`pos.quantity = target_qty`, 수량초과 재대조) | **같은 코루틴의 다른 재시도 회차**라 동시성 아님 |
| `_sync_positions_from_balance`(`scheduler.py:3436-3448`) | `is_ticker_held_by_any` → `continue`. **기보유 수량을 갱신하지 않는다** |

즉 관문 문서 §5.0 의 정정이 옳다 — **현재 (b)의 실효는 ~0 이다.**

**남는 것: 창 2 전체.** (b)는 `_order_qty` 에 들어가는 *값*을 고정할 뿐이고, 창 2 는 그 dict 가
*비어 있는* 구간이다. 축이 다르다.

### 2.2 폴백 경로도 같은 모양인가 — 같다

`:1937-1962`(매도 시장가 거부 → 지정가 5호가 폴백)가 `pos.quantity` 를 **세 번** 다시 읽는다
(`place_order(quantity=)` `:1940` · `_order_qty[fb]=` `:1947` · 헬퍼 `quantity=` `:1962`).
`pos` 는 재시도 루프 top(`:1598`)의 지역 참조이고 폴백은 `except KisApiError` **안**이라 같은
회차다. 1차 주문은 거부됐으니 체결이 없고, 루프 top 값을 쓰는 것이 정합이다 —
**`ordered_qty` 하나로 통일**하면 된다.

`_cancel_and_reorder:2797`(`quantity=remaining`)도 같은 창을 갖지만 `remaining` 은 이미
발사 전 확정된 인자라 (b)는 무접촉이고, (a)의 in-flight 기록만 필요하다.

### 2.3 (b)가 (a)를 쉽게 만드는가 — **만든다. 같은 한 줄이다**

(b)가 만드는 `ordered_qty = pos.quantity`(place_order 앞)가 **정확히 (a)가 기록해야 할 값**이다.
(b) 없이 (a)만 하면 `self._inflight_ordered_qty[...] = pos.quantity` 로 또 한 번 읽게 되어
"발사 전 한 번만 읽는다" 는 cycle327 ⓒ 계약이 다시 어긋난다. **묶어야 한다.**

---

## 3. 매수 축 — 같은 창이 있고, 피해가 더 오래간다

### 3.1 창은 동일하다

`execute_buy:1180` `result = await place_order(**place_kwargs)` → `:1188` `_order_qty[...] = quantity`.
매핑 5종 + `_pending_buy_orders` 가 전부 await **뒤**다. 매도와 같은 구조.

`_handle_buy_fill:2352` 의 전량 판정도 **같은 `ordered_qty` 폴백**을 쓴다.

### 3.2 다만 축 (b)는 매수에 **이미 충족돼 있다**

`quantity` 는 `calc_buy_quantity`(`:1015`)가 만든 **지역 int** 이고 `place_order` 앞에서 확정된다.
await 뒤에 다시 읽지 않는다. 폴백(`:1309-1320`)도 같은 지역 변수다.
→ **매수 축은 (a)만 필요하다.**

### 3.3 피해 모양은 매도와 다르고, **더 나쁘다**

10주 매수, 창 안에 3주 부분 체결이 착지했을 때:

```
_handle_buy_fill:2321  pos 없음 → Position(quantity=total_filled=3) 등록      ← 🔴 7주 누락
:2352  3 >= 3 → 전량 분기
:2432  save_position(quantity=3)                                             ← DB 에도 3
:2443-2448  _filled_qty·_order_qty·_order_strategy·_order_ticker … 전부 pop
:2451  _completed_buy_orders.add(order_no)                                   ← 🔴 멱등 가드 무장
execute_buy:1188  _order_qty[order_no] = 10                                  ← 뒤늦게(무의미)

  ◀ 잔여 7주 체결통보 도착
:2275  order_no in _completed_buy_orders → "[buy_fill_duplicate_ignored]" + return
                                                                             ← 🔴 조용히 버려진다
```

**복구 경로가 없다.**

- `_sync_positions_from_balance` 는 `is_ticker_held_by_any(h.ticker)` 가 True 면 `continue`
  (`scheduler.py:3447`). 이미 3주로 들고 있으므로 **수량을 영원히 고치지 않는다**.
- DB `positions` 행도 3주라 21:30 `_reset_daily_state` → 익일 `_boot` 복구도 3주다.
- 즉 **우리는 10주를 갖고 있는데 엔진은 종일·익일·그 이후로 3주로 믿는다.** 손절이 걸리면
  3주만 팔고 7주는 아무도 보지 않는 채 남는다.

매도 축(포지션 삭제)은 `_sync_positions_from_balance` 가 15분 안에 되살린다 — 불완전하지만
(고점 `high_since_buy` 유실 · `sold_today` 재매수 차단 · 매수가 평단으로 치환 · 전략 귀속 이동)
**복구는 된다.** 매수 축은 복구 자체가 없다.

### 3.4 실측 2건이 전부 매수였던 것의 해석

두 건 모두 `[buy_fill_fallback_held_conflict]`(`:2296`) 동반이었다. 그 분기는
`_order_strategy` miss → `trade_history` miss → **이미 보유 중** → `return`(`:2301`) 이라
**수량 판정에 도달하기 전에 빠져나간다.**

즉 실측이 말해 주는 것과 말해 주지 않는 것이 갈린다.

- 말해 주는 것: **창은 프로덕션에서 실제로 열린다**(보존 33일에 2회, 시각 재확인 필요).
  그리고 그때 `_order_strategy` 까지 같이 비어 있었다 = 창의 완전체였다.
- 말해 주지 않는 것: 수량 오판이 실제로 일어난 적이 있는지. **0건 관측이 아니라 미관측이다**
  — 그 두 건은 `held_conflict` 조기 return 에 먹혔고, 수량 오판 자체에는 **전용 마커가 없다**.

이것이 "매수 쪽이 이미 이 창을 밟고 있었는데 `[buy_fill_fallback_held_conflict]` 로만 드러난
것인가" 에 대한 답이다 — **밟았지만 다른 분기로 빠졌다.** 보유 중이 아닌 신규 매수였다면
3.3 의 사슬을 그대로 탔을 것이고, 그 경우 **아무 마커도 남지 않는다**(`Position` 등록 INFO 는
정상 로그와 구별되지 않는다).

---

## 4. 시정 범위와 순서

### 4.1 한 커밋인가 쪼개는가 — **한 커밋**

회귀 추적 가능성 기준으로 판단한다(승인 횟수 기준이 아니다).

**묶는 근거:**

1. **한 메커니즘이다.** `_inflight_ordered_qty` dict 하나 + 발사점 5곳에 같은 2줄 + 판정기
   1곳. 쪼개면 "dict 는 있는데 쓰는 데가 없는" 중간 커밋이 생긴다.
2. **(b)와 (a)가 같은 줄을 만진다**(2.3). 쪼개면 `ordered_qty` 도입 커밋과 기록 커밋이 같은
   블록을 연달아 고쳐 diff 가 두 배가 되고 bisect 가 더 어려워진다.
3. **매수 축을 뒤로 미루면 더 위험한 쪽이 남는다**(3.3). "매도부터 관망" 은 이 결함에서는
   위험이 큰 쪽을 남기는 선택이다.
4. revert 가 **1커밋**이다(롤백 다이얼이 없는 변경이라 그게 유일 수단이다 — 관문 문서 6절
   결론 유지).

**쪼개는 것 = payload ODER_QTY(1.4).** 그건 다른 값의 출처이고 다른 파일이며 shadow 선행이
필요하다. **이 커밋에 넣지 않는다.**

### 4.2 접촉 파일과 AST 가드 충돌 점검

| 파일 | 접촉 | 8영역 |
|---|---|---|
| `src/engine/order_engine.py` | `__init__` dict 1 · `reset_daily_state` clear 1 · 발사점 5 · 판정기 1 · 분기 2 | ✅ 승인 |
| `src/realtime/handler.py` | **무접촉**(payload 축을 뺐으므로) | — |
| `src/engine/scheduler.py` | **무접촉** | — |

가드 전수 확인(읽고 대조함):

| 가드 | 판정 |
|---|---|
| `test_cycle185_cluster1_ast.py` G2-STRUCT-INVARIANT | ✅ positions 제거 site 집합 `{_handle_sell_fill, execute_sell}` **불변**. 우리는 site 를 늘리지 않고 기존 site 의 **조건만** 좁힌다. companion `on_position_closed` 동반도 유지 |
| `test_cycle328_sell_pending_helper.py` g328_1 | ✅ 매핑 등록 ~ 헬퍼 호출 사이 `await` 0건 — 우리 삽입은 `place_order` **앞** |
| 〃 g328_2 / g328_3b / g328_4 | ✅ 헬퍼 본문 무접촉(인자 **값 표현식**만 `pos.quantity` → `ordered_qty`) |
| `test_budget_limit_ast.py` A-ATOMIC | ✅ `calc_buy_quantity`(`:1015`) ~ `pending_buys.add`(`:1056`) 구간 무접촉. 삽입 자리는 `place_order` 직전(`:1180`)으로 그 구간 **밖** |
| 〃 A-PURE | ✅ 관문(`_apply_budget_limit`) 무접촉 |
| `test_cycle291_ast_scope.py` a3 (프리장 사전변환 블록 byte 동일) | ✅ 그 블록은 재시도 루프 **앞**이다 |
| 〃 a10a (매핑이 `place_kwargs` 파생값을 읽는지) | ✅ `_order_division` 축 무접촉 |
| 〃 a10c (모든 place_order 성공 site 에 매핑 등록) | ✅ 등록 유지 + 앞에 한 줄 추가 |
| `test_cycle235_ast_execution_qty.py` | ✅ `handler.py` 무접촉 |
| `test_order_engine_sell_fallback.py` 시나리오 J | ⚠️ 헬퍼 4값(`record_price`/`quantity`/`path`/`order_no`) 봉인. `quantity` 의 **값**은 정상 흐름에서 동일하므로 통과 예상 — **tdd 가 실행으로 확인**할 것 |

### 4.3 배포 창

`src/engine/order_engine.py` 변경 = `BACKEND_RE` 히트 = **full 모드 = backend 재시작**.
보유 포지션이 있으면 D6 가 09:00~15:30 push 를 막고, D8 이 20:00~21:35 를 막는다.
가용 창 = **15:30~16:00 · 21:35~익일 07:45 · 주말·공휴일**.

관문 문서 6절의 부대조건을 **그대로 승계**한다: 이 커밋은 **일요일 중에 배포·실측까지 끝낸다.**
월요일 새벽 배포 + 07:45 부팅은 문제 발생 시 되돌릴 창이 15:30 까지 없다(약 6시간 반 노출).

---

## 5. 관측 — 이 창이 열렸다는 것을 어떻게 아는가

### 5.1 `:2143` WARNING 으로는 부족하다

세 가지를 구별하지 못한다: ① 매수/매도 ② 우리 주문/수동 주문 ③ **수량 판정이 실제로
어떻게 갈렸는가**. 게다가 그 줄은 `_order_ticker` 축만 본다 — `_order_qty` 만 비고
`_order_ticker` 는 차 있는 상태(구조상 같은 블록이라 현재는 동시 발생이지만, 그것은 계약이
아니라 현재 코드의 성질이다)는 침묵한다.

### 5.2 신규 마커 2종 (권고)

**`KstDailyEmitCap`(`src/engine/daily_emit_cap.py`) + `observer_trace` 관례를 따른다.**

```
[fill_qty_src] order_no=%s ticker=%s side=%s src=map|inflight|increment
               ordered=%d filled_total=%d incr=%d verdict=full|partial|held
```

- 위치: `handle_execution_notice` 의 `ordered_qty` 해석 **직후**, `_handle_*_fill` 분기 앞
- 레벨: `src=map` → **DEBUG**(정상이고 하루 수천 건) / `src=inflight` 또는 `increment` → **WARNING**
- cap: `KstDailyEmitCap[(src, ticker, side)]` — **1회/(출처, 종목, 방향)/일**
  (`order_no` 를 키에 넣으면 cap 이 사실상 무력해진다. 창이 같은 종목에 여러 번 열리는 것은
  빈도 문제이고, 그건 아래 summary 가 센다)
- 🔴 **행위는 cap 밖**: 마커 성패와 무관하게 판정은 수행한다. never-raise, 자기 실패는
  `trace_observer_failure("[fill_qty_src]", key, cap)`

**`[fill_qty_src_summary] window=day map=%d inflight=%d increment=%d`**

- 위치: `_settle()`(21:30) 직전, `emit_price_filter_scanner_daily_summary` 선례와 같은 자리
- 🔴 **try/except 로 감싸지 않는다** — `scanner` 일일 summary 2종과 같은 이유(감싸면 폐기
  메서드 잔존 같은 결함이 AttributeError graceful skip 으로 조용히 먹힌다)
- **판독 규칙**: `inflight > 0` = 창이 그날 실제로 열렸고 **우리가 막았다**(성공 서명).
  `increment > 0` = 수동/외부 주문이 그날 있었다(정상일 수 있음 — 수동 매매를 했다면).
  **`increment > 0` 인데 그날 수동 매매를 한 적이 없으면 그것이 조사 신호다**(B안의
  `_inflight` 기록이 새는 경로가 있다는 뜻).

### 5.3 일일 리포트 도달성 — 의도적으로 WARNING 으로 둔다

`log_analysis_engine._aggregate_log_patterns` 는 `{WARNING, ERROR, CRITICAL}` 만 `top_patterns`
에 넣는다. `src=map` 을 DEBUG 로 두고 나머지를 WARNING 으로 두면 **비정상만 리포트에 오른다**.
`[ratio_notional_blocked]` 가 INFO 라 리포트에 한 글자도 안 들어가 오귀인을 낳은 선례
(`src/engine/CLAUDE.md` ρ축 절)의 반대를 택한다.

---

## 6. 🔴 이 시정이 만들 수 있는 새 결함

### 가장 그럴듯한 것 — **`_schedule_cancel_and_reorder` 가 새로 도달한다**

지금은 창 2 의 첫 통보가 **전량 분기**로 가므로 재주문 타이머가 안 걸린다. 시정 후 그 통보는
**부분 분기**(`_handle_sell_fill:2617-2621`)로 가고, 거기 끝에 이것이 있다.

```
remaining = ordered_qty - total_filled              # :2620   10 - 3 = 7
self._schedule_cancel_and_reorder(ticker, order_no, remaining, is_stop_loss=True)   # :2621
```

30초 뒤 `_cancel_and_reorder`(`:2701`)가 **취소 + `place_order(quantity=7)` 신규 매도**를 낸다.
그리고 **정정 1** 에서 확인했듯 그 함수에는 **포지션 재조회가 한 줄도 없다.**

무엇이 어긋날 수 있나:

| 시나리오 | 결과 |
|---|---|
| 진짜 부분 체결이었다 | **의도된 동작**(손절 잔여 재주문). 정상 |
| 그 30초 안에 잔여 7주가 체결됐다 | `_handle_sell_fill` 전량 분기가 `_pending_cancel_order_no` 일치 시 타이머를 **해제**한다(`:2608-2613`). 막힌다 |
| 잔여가 이미 취소·만료됐다(NXT GTP 08:50 등) | `cancel_order` APBK0927 거부 → `raise` → `except Exception` 흡수(`:2831`). 재주문 미도달. 막힌다 |
| **`ordered_qty` 가 실제보다 크다** | 있지도 않은 잔량으로 **신규 매도 발사** → APBK0400 → `is_sell_qty_exceeded` 재대조가 흡수. 자기 치유되지만 **주문이 한 번 나간다** |

마지막 줄이 본체다. B안에서 `ordered_qty` 는 우리가 직접 적은 값이라 틀릴 여지가 작지만,
**1.4 의 payload ODER_QTY 를 나중에 편입하면 그 값은 KIS 가 준 값이고, 수동 매매 주문에까지
적용된다.** 그러면 우리 엔진이 **사람이 HTS 로 낸 주문을 30초 뒤에 취소하고 다시 낸다.**
cycle327 이 "주문이 나간 뒤의 실패로 재발사 금지" 로 봉한 것과 같은 계열의 사고다.

### 막는 방법 — 이 사이클의 **필수 동반 조항**

> **`qty_src != "map"` 인 랏은 취소·재주문 타이머를 걸지 않는다.**

```
# _handle_sell_fill 부분 분기
if qty_src == "map":
    self._schedule_cancel_and_reorder(ticker, order_no, remaining, is_stop_loss=True)
else:
    logger.warning("[fill_partial_no_reorder] ticker=%s order_no=%s src=%s "
                   "remaining=%d — 매핑 확정 전 통보라 재주문 보류", ...)
# _handle_buy_fill 부분 분기의 _schedule_cancel(:2471) 도 같은 게이트
```

**근거 셋:**

1. 잃는 것이 없다. `qty_src == "inflight"` 는 *우리 주문의 첫 통보*이고, 매핑은 **밀리초 뒤에
   등록된다**. 잔여가 남아 있으면 **다음 통보가 `src=map` 으로 와서** 그때 정상적으로 타이머를
   건다. 진짜로 그 한 통보가 마지막이면(= 전량이었는데 우리가 부분으로 읽었다면) 아래 3 이 받는다.
2. `qty_src == "increment"` 는 수동/외부 주문이다. **우리가 남의 주문에 손대지 않는다** 는 것이
   현행 행위이고(오늘은 전량 판정으로 빠져 타이머가 안 걸린다), 그것을 보존한다.
3. **잔여 회수의 진짜 안전망은 재주문이 아니라 `risk.on_tick` 재평가 + `_sync_positions_from_balance`
   다.** 포지션이 남아 있으면 다음 틱에 손절 조건이 다시 평가되고, 수량이 어긋나 있으면
   `is_sell_qty_exceeded` → `[sell_qty_reconciled]` 가 보유 실체로 보정한다(cycle273b, 설계된 경로).

### 두 번째로 그럴듯한 것 — `_selling` 좀비 (완전 체결을 부분으로 읽은 경우)

`qty_src="inflight"` 인데 그 통보가 **실은 전량**이었을 수 있나? B안에서는 `ordered_qty` 가
우리가 보낸 수량 그 자체이므로 `total_filled >= ordered_qty` 가 정확히 참이 되어 **전량으로
읽힌다**. 즉 B안에서는 이 실패 모양이 **구조적으로 생기지 않는다.**

생기는 것은 `qty_src="increment"` 잔여뿐이고, 그건 정의상 수동/외부 주문이라 `_selling` 에
없다(우리가 넣은 적이 없다). **B안을 택하면 이 위험이 닫힌다** — 반대로 관문 문서가 검토했던
"`known_ordered=False` 면 무조건 부분으로 처리" 안(B′)을 택하면 **이 좀비가 실재한다**:
시장가 즉시 전량 체결이 매도의 가장 흔한 모양이라, 그 안은 가장 흔한 경우에서
`_selling` 유지 + 포지션 유령 잔존(`selling_reconcile` 의 `held_zero` 는 **유지** 분기다)을 만든다.
**이것이 B′안을 권고하지 않는 결정적 이유다.**

---

## 현 코드·정본과의 정합성

**충돌 없음.** 확인한 금기 전수:

| 정본 금기 | 판정 |
|---|---|
| 체결통보 구독 제거 금지 | 무접촉 |
| 주문번호 매핑 등록은 `place_order` 응답 직후 **동기 영역**, `await insert_trade` 진입 전 | ✅ 유지. 우리는 그 **앞**에 동기 한 줄을 더한다(await 없음) |
| 체결통보 선행 race 가드(`_completed_orders` + 보정 INSERT) | 무접촉 |
| 주문이 나간 뒤의 실패로 재발사 금지(cycle327) | ✅ 강화 방향(6절 동반 조항) |
| `_reset_daily_state()` 제거 금지 | ✅ 신규 dict 를 `OrderEngine.reset_daily_state()` clear 목록에 **동행 추가**(`_order_exchange`·`_order_division` 선례와 같은 자리·같은 이유 — `order_no`/in-flight 는 하루 단위 개념) |
| `tradable_boards` 는 매수 진입 전용 | 무접촉 |
| NXT 매도 거부 좀비 차단 · `_selling` discard 규약 | 무접촉(6절 두 번째 항목이 이 규약을 **지키기 위해** B′를 배제한 것이다) |
| 익일 청산 · 15:20 일괄청산 | 무접촉 |

**루트 `CLAUDE.md` 상 이 변경의 성격** = 「매매 행위를 바꾸는 코드 변경 — 청산 규약(포지션 제거
시점)」 → 8영역 승인 + `domain-consult` 선행. **이 문서가 그 선행이다.**

---

## 반례 / 한계 — B안이 못 막는 것

1. **`_inflight` 기록이 새는 경로.** `finally` 로 닫지 않으면 stale 엔트리가 남아 *나중의 다른
   통보*에 잘못된 수량을 준다. `(side, ticker)` 키 + `finally` pop + `reset_daily_state` clear
   3중이 필요하고, **셋 중 하나라도 빠지면 이 시정이 새 결함이 된다.** tdd 회귀에서
   "예외 발생 후 dict 가 비어 있는가" 를 반드시 본다.
2. **같은 종목·같은 방향 동시 주문.** 키가 ticker 라 두 개가 동시에 뜨면 뒤가 앞을 덮는다.
   매도는 `_selling`(`:1422`), 매수는 `is_ticker_blocked_for_buy` + `pending_buys`(`:1056`)가
   막지만, **구조적 보장이 아니라 다른 가드에 기댄 보장**이다. `_cancel_and_reorder` 의
   재주문이 `_selling` 검사를 거치지 않는다는 점이 이 한계의 실체다 —
   그래서 `_cancel_and_reorder` 에도 같은 기록을 넣되, **기존 엔트리가 있으면 덮지 않는다**
   (`setdefault`)는 보수적 처리를 권고한다.
3. **수동 매매의 부분 체결은 여전히 전량으로 읽힌다.** 이건 B안이 의도적으로 안 고친 축이고,
   1.4 의 payload 경로가 열려야 고쳐진다. 그때 6절의 위험이 같이 오므로 별도 판단이다.
4. **`_order_strategy` 축은 이 시정이 손대지 않는다.** 같은 창에서 전략 귀속도 비어 있고
   `_lookup_strategy_from_trade_history` → `"momentum"` 폴백으로 흐른다. 수량은 고쳐지지만
   **잘못된 전략에 귀속될 수 있다.** 같은 `_inflight` 기록에 `strategy_id` 를 함께 담으면
   추가 비용 0 으로 같이 닫힌다 — **동반 권고**(단, 전략 귀속은 자본 위험이 아니라 성과 귀인
   문제라 이번 스코프에서 빼도 무방하다. 넣으면 diff 가 한 필드 늘고, 빼면 `"momentum"`
   오귀속이 남는다. team-leader 가 고른다).
5. **빈도를 여전히 모른다.** 5절 마커가 붙기 전까지는 이 시정이 실제로 몇 번 발화하는지 알 수
   없다. 마커가 이 커밋에 함께 들어가는 것이 그래서 필수다.

---

## 후속 검증 권고 (tdd-engineer / tester)

**tdd Red — 결정적 시리즈 5개**(전부 `_order_qty` 미등록 상태에서 `handle_execution_notice` 직접 호출)

| # | 입력 | 기대 |
|---|---|---|
| R1 | 매도 10주 in-flight 기록 있음 + 3주 통보 | **부분**(`positions` 보존) · `_schedule_cancel_and_reorder` **미호출** · `[fill_qty_src] src=inflight verdict=partial` |
| R2 | R1 직후 `_order_qty=10` 등록 + 7주 통보 | **전량** · `positions` 삭제 · `on_position_closed` 1회 · `src=map` |
| R3 | 매도 10주 in-flight + 10주 통보 | **전량**(현행과 같은 결과 — B안이 전량을 부당하게 막지 않음을 봉인) |
| R4 | in-flight 기록 **없음** + 3주 통보(수동 매매 모사) | **현행 행위 byte 동일**(전량 판정) · `src=increment` WARNING |
| R5 | 매수 10주 in-flight + 3주 통보 → 이어서 `_order_qty=10` 등록 + 7주 통보 | 최종 `positions[ticker].quantity == 10` · `_completed_buy_orders` 가 1차에서 **무장되지 않음** · `save_position` 최종 10 |

**tdd 누수 가드**

| # | 입력 | 기대 |
|---|---|---|
| R6 | `place_order` 가 `KisApiError` 를 던지는 3회 재시도 소진 | `_inflight_ordered_qty` **비어 있음** |
| R7 | `_persist_sell_pending_after_send` 가 예외를 삼킨 뒤 | 동일 |
| R8 | `reset_daily_state()` 호출 후 | 동일 |

**AST 가드 신설 권고**

- G-329-1: `order_engine.py` 의 모든 `place_order` 성공 site(5곳)에서 `_inflight_ordered_qty`
  기록이 `place_order` 호출 **앞** 라인에 있을 것 (a10c 의 대칭)
- G-329-2: 기록 라인 ~ `place_order` 사이 `await` 0건
- G-329-3: `_inflight_ordered_qty` pop 이 `finally` 블록 안에 있을 것
- G-329-4: `OrderEngine.reset_daily_state` 에 `_inflight_ordered_qty.clear()` 존재
  (`_order_exchange`/`_order_division` 선례와 같은 형태 — `test_cycle291_ast_scope.py::a10` 대칭)
- G-329-5: `_handle_sell_fill`/`_handle_buy_fill` 의 `_schedule_cancel*` 호출이 `qty_src` 게이트
  **안**에 있을 것 (6절 동반 조항의 구조 봉인 — 행위 테스트로는 열거 누락에 노출된다,
  `test_cycle328_...::test_g328_3b` 가 증명한 교훈)

**tester 실측 (D+1)**

1. `[fill_qty_src_summary]` 의 `inflight`/`increment` 카운트
2. `increment > 0` 인 날 수동 매매 이력(`trade_history` 의 빈 `order_no` 행 · MTS 체결) 대조
3. `:2143` WARNING 과 `[fill_qty_src]` 의 **동시 발생률** — 1.0 이 아니면 두 축(`_order_ticker`
   와 `_order_qty`)이 실제로 갈릴 수 있다는 뜻이고, 그건 현재 코드 구조에 대한 내 전제가
   틀렸다는 신호다

**별건 카드(이 사이클 밖)**

- F-329-A: payload `ODER_QTY` shadow 대조(1.4) — `handler.py` 1줄 + 엔진 관측, 행위 0
- F-329-B: `_cancel_and_reorder` 에 포지션 재조회 추가(정정 1) — **독립적으로 실재하는 결함**이다.
  이 시정과 무관하게 지금도 그 함수는 보유를 안 보고 매도를 낸다
- F-329-C: `_order_strategy` 축의 같은 창(한계 4)

---

매매 행위 영향: **있다(의도된 변경)** — 매핑 미확정 상태의 전량 판정이 사라지고, 그 상태의
취소·재주문이 보류된다. 수동/외부 주문 경로는 행위 변경 0.
