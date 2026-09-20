# cycle332 — 매수 축 잔량 취소 타이머: 파괴·범위·게이트 판정

> 작성 2026-09-21 00:4x KST · domain-expert 자문 메모 (코드 변경 0)
> 판정 기준 = **지금 워킹트리**(cycle331 반영, 미커밋) + **EC2 배포본 `b1263c7`**(= HEAD, cycle330)
> 선행 자문 = `_workspace/domain_consult/cycle331_buy_fill_dropped.md` · `cycle329_mapping_absent_full_fill.md`

---

## 0. 먼저 — 정본 금기와의 충돌

이 메모의 권고 중 **정본 금기를 깨는 것은 없다.** 다만 충돌에 가까운 지점 셋을 먼저 적는다.

| 지점 | 정본 | 이 메모의 입장 |
|---|---|---|
| `cancel_all=True` 유지 | `src/api/CLAUDE.md:97` — 취소 3경로는 `order_division` 미전달 | **건드리지 않는다.** 주장 2 의 원인은 `cancel_all` 이 아니다(§3) |
| `_pending_cancel_tasks` 키 변경 | `tests/unit/engine/test_cycle273a_cancel_timer_on_full_fill.py:254` 가 "매수·매도가 같은 dict 를 공유한다는 **사실**" 을 가드로 고정 | 그 가드는 *공유* 를 계약으로 못박은 게 아니라 **해제가 order_no 게이트 뒤에 있어야 한다**는 계약이다(테스트 docstring `:221-222`). 키를 분리하면 그 계약은 더 강하게 성립한다 — 다만 **테스트 4~6건의 키 표현을 함께 고쳐야 하므로 승인 대상** |
| 매도 청산 경로 차단 금지 | 루트 `CLAUDE.md` — 매도/손절/트레일링은 보드 무관 항상 작동 | 권고는 **매도 타이머를 지키는 방향**뿐이다. 어떤 안도 매도 타이머를 새로 막지 않는다 |

🔴 **그리고 시각 제약이 하나 있다.** cycle329(`297d335`)는 **2026-09-20 17:22 커밋 = 일요일 장외**에 배포됐다. **오늘 2026-09-21(월) 09:00 이 cycle329 아래 맞는 첫 거래일**이다. 즉 §6 에서 판정하는 「매수 축 구멍」은 **아직 한 번도 열린 적이 없고, 오늘 개장부터 처음 열린다**. 장외 배포 창은 **07:45 까지**다(루트 `CLAUDE.md` 운영 가이드).

---

## 1. 질문 요약

B3 조사가 낸 주장 3건의 진위, 타이머 파괴의 실재성, `cancel_all` 의 범위, cycle331 게이트의 커버리지, 매도 게이트 복붙의 가부, 시정 범위와 8영역 승인 면적, 새 결함 1건, 관측 마커.

---

## 2. 주장 1~3 판정

### 주장 1 — `_schedule_cancel` 이 ticker 키로 기존 타이머를 무조건 cancel 한다 → **참 (기전 정확)**

```
src/engine/order_engine.py:299   self._pending_cancel_tasks: dict[str, asyncio.Task] = {}   # ticker -> 취소 대기 태스크
src/engine/order_engine.py:304   self._pending_cancel_order_no: dict[str, str] = {}         # ticker -> 그 타이머가 지키는 order_no

:2842  def _schedule_cancel(self, ticker, order_no, original_qty, strategy_id="momentum"):
:2844      if ticker in self._pending_cancel_tasks:
:2845          self._pending_cancel_tasks[ticker].cancel()      # ← order_no 무검사
:2847      self._pending_cancel_tasks[ticker] = asyncio.create_task(...)
:2850      self._pending_cancel_order_no[ticker] = order_no

:2907  def _schedule_cancel_and_reorder(self, ticker, order_no, remaining, *, is_stop_loss):
:2911      if ticker in self._pending_cancel_tasks:
:2912          self._pending_cancel_tasks[ticker].cancel()      # ← 같은 모양, 같은 dict
:2914      self._pending_cancel_tasks[ticker] = asyncio.create_task(...)
:2917      self._pending_cancel_order_no[ticker] = order_no
```

두 등록 함수가 **같은 dict 를 ticker 키로 공유**하고 **둘 다 order_no 를 보지 않고 죽인다**. 코드 주석 `:300-304` 가 공유 사실을 이미 적어 두고 있다.

🔴 **핵심은 「공유」가 아니라 「비대칭」이다.** cycle273a 는 **해제 경로** 두 곳을 order_no 로 좁혔다 —

```
:2644  if self._pending_cancel_order_no.get(ticker) == order_no:      # 매수 전량체결 해제
:2811  if self._pending_cancel_order_no.get(ticker) == order_no:      # 매도 전량체결 해제
```

그런데 **등록 경로 두 곳(`:2844`·`:2911`)은 그대로 ticker 로 뭉갠다.** cycle273a 가 절반만 닫았다. 그 사이클의 자기 테스트가 이 손실을 직접 문장으로 적어 두었는데(`test_cycle273a_cancel_timer_on_full_fill.py:241-242` — "매수 잔량이 장 마감까지 미체결로 남는다"), 같은 손실이 **등록 방향으로는 여전히 도달 가능**하다.

### 주장 2 — `cancel_all=True` 라 사람이 낸 매수의 잔량을 우리가 취소한다 → **결론은 참(HEAD 기준), 기전 설명은 거짓**

- **기전은 틀렸다.** `cancel_all` 은 종목 전체가 아니라 **그 원주문 한 건의 잔량 전부**다(§3 실증).
- **결론은 맞다.** 다만 원인은 플래그가 아니라 **`order_no` 자체가 남의 주문번호**라는 것이다. 체결통보는 우리 주문과 수동 주문을 가리지 않고 오고, **HEAD(=배포본)의 매수 부분 분기에는 게이트가 한 줄도 없다**:

```
# git show HEAD:src/engine/order_engine.py — _handle_buy_fill 부분체결 분기
self._schedule_cancel(ticker, order_no, ordered_qty, strategy_id)     # 무게이트
```

`cancel_all=False` 로 바꿔도 **결론은 그대로**다(취소 대상이 그 주문인 건 변함없다). 즉 B3 가 지목한 플래그는 원인이 아니고, 그 플래그를 손대는 시정은 아무것도 고치지 못한다.

### 주장 3 — `_handle_buy_fill` 의 `qty_src` 가 본문에서 0회 사용 → **HEAD 기준 참, 워킹트리 기준 거짓(이미 해소)**

```
$ git show HEAD:... 의 _handle_buy_fill 본문 qty_src 등장 = 1회 (시그니처 `*, qty_src: str = "map"` 뿐)
```

워킹트리(cycle331)는 **2회 사용**한다 — 관측 로그 `:2472` 와 타이머 게이트 `:2665`. **주장 3 은 cycle331 구현으로 이미 닫혔다.** 이 항목으로 별도 작업을 만들 이유가 없다.

---

## 3. `cancel_all=True` 의 범위 — KIS body 실증

`src/api/order.py:147-158` 의 실제 body:

```python
body = {
    ...
    "ORGN_ODNO": original_order_no,          # :151  ← 취소 대상 = 이 주문번호 하나
    "ORD_QTY": str(quantity),                # :154
    "QTY_ALL_ORD_YN": "Y" if cancel_all else "N",   # :156
    "EXCG_ID_DVSN_CD": exchange,             # :157
}
```

- **`QTY_ALL_ORD_YN="Y"` = 「그 원주문의 잔량 전부」** 라는 뜻이다. 그래서 호출부가 `ORD_QTY=0` 을 보낼 수 있다(`:2881`·`:2960`).
- **종목 단위 일괄취소 플래그가 아니다.** KIS 정정취소(TTTC0013U)는 `ORGN_ODNO` 로 주문 한 건을 지목하는 API이고, 종목 전체를 쓸어내는 축 자체가 body 에 없다.
- **따라서 "사람이 낸 *다른* 주문까지 취소된다" 는 성립하지 않는다.** 성립하는 것은 "**체결통보에 실려 온 그 주문번호**가 사람 것이면 그 주문을 취소한다" 하나다.

트레이더 어법으로: 우리가 호가창에서 빼는 것은 **그 한 줄**이다. 다만 그 한 줄이 누구 것인지 확인하지 않고 뺀다 — 그게 문제였다.

---

## 4. 타이머 파괴가 실재하는가 — 시각 순서와 손실

**공유 사실 확인**: `_schedule_cancel`(매수)과 `_schedule_cancel_and_reorder`(매도)는 `_pending_cancel_tasks` **단일 dict 를 ticker 키로 공유**한다(`:299`·`:2847`·`:2914`). 공유한다.

### 시나리오 S1 — 매수 타이머가 **손절 타이머**를 죽인다 (심각)

| 시각 | 사건 | 상태 |
|---|---|---|
| T+0.0s | 종목 X 지정가 매수 10주 발사, `_order_qty[B]=10` | — |
| T+0.4s | 매수 3주 부분체결 통보 → `_handle_buy_fill` 부분 분기 → `_schedule_cancel(X, B, …)` | `tasks[X]=TaskB`, `order_no[X]=B`, 포지션 3주 |
| T+11s | 급락 → `risk.on_tick` 손절 → `execute_sell` 3주. `_selling.add(X)` (`:1507`) | `_selling={X}` |
| T+11.3s | 매도 1주 **부분**체결 통보 → `_handle_sell_fill` 부분 분기 `:2820` → `_schedule_cancel_and_reorder(X, S, remaining=2, is_stop_loss=True)` | `:2911-2912` 가 **TaskB 를 cancel** → `tasks[X]=TaskA` |
| T+18s | 매수 잔여 7주 추가 부분체결 통보 → 부분 분기 → `_schedule_cancel(X, B, …)` | `:2844-2845` 가 **TaskA 를 cancel** → `tasks[X]=TaskB'` |
| T+41s | TaskB' 만료 → 매수 잔여 취소 | **손절 잔여 2주는 아무도 다시 보지 않는다** |

**잃는 것 (S1):**

1. 🔴 **손절이 미완결 상태로 고착된다.** `_cancel_and_reorder`(`:2919`)는 취소 3경로 중 **유일하게 `cancel_order → place_order` atomic replace** 다(`src/engine/CLAUDE.md:416` 이 그렇게 적는다). 그게 죽으면 원 매도 주문은 호가에 그대로 남고, 시장가가 아닌 경우 — **프리장 사전 `step_down(현재가,5)` 변환·KRX 애프터 `41` 지정가·NXT 잔존** — 안 팔린다.
2. 🔴 **그 사이 손절 재평가도 멈춰 있다.** 매도 **부분**체결 분기(`:2820-2840`)는 `_selling` 을 **discard 하지 않는다**(discard 는 `:2726` 전략 미발견 · `:2754` 전량체결뿐). `risk.on_tick` 의 `_selling` 가드가 `check_exit_signal` 을 건너뛰므로, 그 종목의 손절은 **TaskA 가 유일한 출구**였다.
3. 🔴 **`selling_reconcile`(180초 재대조)도 풀어 주지 않는다.** 원 매도 주문이 **열린 채로 남아 있으므로** 판정이 `open_order` = **유지** 분기다(`src/engine/CLAUDE.md` selling_reconcile 절). 결국 그날 21:30 `_reset_daily_state` 까지 `_selling` 좀비 + 손절 잔여 방치가 이어질 수 있다.

즉 **S1 의 손실은 "매수 잔량 자동취소를 놓친다" 가 아니라 "급락장에서 손절 잔여가 체결도 재주문도 재평가도 못 받는다" 다.**

### 시나리오 S2 — 매도 타이머가 **매수 타이머**를 죽인다

위 표의 T+11.3s 단계에서 끝나는 경우(매수 잔여 추가 체결이 없을 때). TaskB 가 죽고 매수 잔여 7주가 호가에 남는다.

**잃는 것 (S2):**

1. 우리가 **손절 중인 종목을 계속 사들인다** — 방향이 정반대인 주문이 동시에 산다.
2. 🔴 **랏 상한이 사후적으로 뚫린다.** `pending_buys`/`pending_buy_amounts` 는 **첫 부분체결에서 이미 풀린다**(`:2532-2534`, 전량/부분 공통 경로). 예산 점유가 풀린 채 미취소 잔여가 나중에 체결되면 `pos.quantity` 가 설계 랏을 넘고, K축(`max_lot_units`)·ρ축(`max_lot_ratio_mult`) 캡은 **진입 시점 통제**라 이걸 못 막는다.

### 셋째 — 같은 축 두 주문 (cycle273a 테스트 A2 의 거울상)

`test_cycle273a_cancel_timer_on_full_fill.py:216-244` 가 "주문 A 부분체결 → 주문 B **전량**체결 → A 타이머 생존" 을 가드한다. 그런데 **주문 B 가 「부분」체결이면** `:2844` 가 A 를 죽인다. 같은 손실, 반대 방향, 가드 없음.

다만 이 셋째 경로는 cycle331 이 착지하면 **구조적으로 닫힌다** — 첫 부분체결이 포지션을 정상 등록하므로 `registry.is_ticker_blocked_for_buy` 가 같은 종목의 두 번째 매수를 막는다. 그래서 **남는 실효 충돌은 S1/S2(매수↔매도) 한 축뿐**이다.

---

## 5. cycle331 게이트가 주장 2 를 막는가 — **완전히 막는다**

```
:2665   if qty_src == "map" and not strategy_from_pending:
:2666       self._schedule_cancel(ticker, order_no, ordered_qty, strategy_id)
```

`qty_src == "map"` 은 `_order_qty[order_no]` 가 존재한다는 뜻이고(cycle329 3단 표), **그 dict 는 우리가 `place_order` 응답 직후 동기 영역에서만 쓴다**. 수동(HTS/MTS)·외부 주문의 주문번호는 원리상 거기 없다. 따라서:

- **수동/외부 매수는 `qty_src` 가 절대 `"map"` 이 될 수 없다 → `_schedule_cancel` 에 도달하지 못한다.** 주장 2 의 결론은 cycle331 로 100% 닫힌다.
- 두 번째 항 `not strategy_from_pending` 은 **첫 항에 함의된 중복**이다 — `strategy_from_pending=True` 는 `_order_strategy` miss 를 뜻하고, `_order_strategy`·`_order_qty` 는 같은 자리에서 함께 등록·pop 되므로(`:2629-2634`) 그때 `qty_src != "map"` 이다. **해롭지 않고 의도를 문서화한다.** 🔴 다만 나중에 누가 `qty_src` 항을 완화하면 이 항이 홀로 남아 pending 귀속 랏을 계속 막는다 — 그게 옳은 방향이니 그대로 둔다.

### 남는 구멍 (= 이번 사이클의 대상)

| # | 구멍 | 게이트가 막나 | 심각도 |
|---|---|---|---|
| A | 🔴 **§4 의 타이머 파괴(S1/S2)** — 게이트는 "누가 타이머를 거는가" 만 좁혔고 "이미 걸린 남의 타이머를 죽이는가" 는 **그대로** | ✗ | **HIGH** — 손절 미완결 |
| B | 재시작 뒤 낸 우리 주문의 부분체결이 `payload` 로 와서 타이머를 못 건다(`_order_qty` 는 메모리) | — (설계상 보류) | LOW — 기회비용(잔여 미취소), 자본 위험 0 |
| C | 발사 창에서 **두 번째** 부분체결 통보가 와도 `pending_buys` 가 첫 통보에서 이미 discard(`:2533`) 되어 귀속 불가 → `[buy_fill_fallback_held_conflict]` 로 **수량 갱신이 버려진다** | ✗ | LOW — `await place_order` 지속 시간(수십~수백 ms) 안에 부분체결 2회가 필요 |
| D | `[buy_partial_no_cancel_timer]` 보류 랏은 **영구 미취소**다(다음 통보가 `map` 으로 오지 않으면 아무도 안 건다) | — | LOW |

**A 만 이번 사이클 대상이다. B·C·D 는 관측으로 세고 미룬다.**

---

## 6. 매도 게이트를 매수에 복붙하면 안 되는가 — **B3 의 경고는 틀렸다**

B3: "복붙 금지(우리 잔량 자동취소가 사라진다)".

검증:

- 우리가 낸 매수 주문은 `place_order` 응답 직후 `_order_qty[order_no]` 에 등록된다. **정상 통보의 `qty_src` 는 `"map"` 이다** — 게이트를 통과한다. **우리 잔량 자동취소는 사라지지 않는다.**
- 통과 못 하는 것은 **발사 창(매핑 미등록) 통보**뿐이고, 다주 랏이면 **ms 뒤 다음 통보가 `map` 으로 와서 정상적으로 건다**. 1주 랏은 부분체결 자체가 불가능하다.
- 매도 축이 같은 게이트로 이미 살고 있다(`:2832`, cycle329). 비대칭을 남길 이유가 없다.

**결론: 복붙이 옳다. cycle331 이 이미 한 그 형태(`qty_src == "map" and not strategy_from_pending`)가 매수 축의 올바른 게이트다.** B3 의 경고를 근거로 cycle331 의 게이트를 되돌리면, 오늘 개장부터 열리는 구멍을 다시 여는 것이다.

---

## 7. 실측

접속 = `ssh auto-stock` · psql 세션 TZ 는 UTC 라 `AT TIME ZONE 'Asia/Seoul'` 병기.

**① 부분체결은 5개월에 사실상 2건이다.**

```
trade_history 전수 (2026-04-22 ~ 2026-09-18)
 BUY  COMPLETED 324 | BUY  PARTIAL 1 | BUY  PENDING 12
 SELL COMPLETED 320 | SELL CANCELLED 1 | SELL PENDING 1
```

**② `_schedule_cancel` 이 실제로 발화한 흔적 = 2건.** (INFO 는 2일 retention 이라 WARNING+ 만 남는다)

| KST | level | 원문 |
|---|---|---|
| 2026-08-28 09:16:22 | ERROR | `부분 체결 잔여 취소 실패: 257720` |
| 2026-09-10 09:05:32 | ERROR | `부분 체결 잔여 취소 실패: 004990` |

09-10 건은 30초 전 `09:05:02 [buy_fill_correction_unique_violation] ticker=004990 strategy=kojiro` 와 짝이다 — 발사 창 race 로 부분 분기에 들어가 타이머가 걸렸고, 30초 뒤 취소가 거부됐다.

**③ `_schedule_cancel_and_reorder`(매도) 발화 흔적 = 0건.** `매도 잔여 취소` / `손절 잔여 재주문` / `매도 잔여 취소/재주문 실패` 전부 0행. 즉 **매도 부분체결은 5개월간 한 번도 없었다.**

**④ `[buy_fill_fallback_held_conflict]` = 2건** (08-26 078930 · 08-31 161890) — cycle331 자문의 2건과 동일 표본.

**⑤ cycle329 마커(`[fill_qty_src]` 계열) = 0행.** 배포가 2026-09-20 17:22(일요일 장외)라 **경과 거래일 0** 이다. 표본 부재이지 정상 확인이 아니다.

### 실측의 해석 — 🔴 빈도로 미루면 안 되는 이유

평시 빈도가 0에 가까운 이유는 **랏이 1주 언저리**여서다(메모리 `project_lot_geometry` — VB q=0.74·LTV 1.11 등, 입금 후 기준). 1주는 부분체결이 원리상 불가능하다.

그런데 **부분체결은 「유동성이 얇아지는 순간」에 집중된다** — 급락·VI 직후·프리장·애프터. 그 구간이 정확히 `_cancel_and_reorder` 가 존재하는 이유다. **평시 표본으로 재면 0건, 필요한 날에는 1건.** 트레이더 판단으로는 이 타이머는 "빈도" 가 아니라 "그날 있느냐" 로 값을 매긴다.

---

## 8. 정량 권고

### 세 안

| 안 | 내용 | 8영역 면적 | 잃는 것 | 판정 |
|---|---|---|---|---|
| **A** | `_pending_cancel_tasks`/`_pending_cancel_order_no` 키를 **`(ticker, side)` 복합 키**로. 매수·매도 타이머가 공존한다 | `order_engine.py` 6곳 + `scheduler.py` 2곳 | 없음 | 🟢 **권고** |
| B | `_schedule_cancel`(매수)에만 "기존 타이머가 **매도** 면 걸지 않는다" 가드. 매도가 항상 이긴다 | `order_engine.py` 2곳 | 그 30초 동안 매수 잔량 자동취소 **영구** 포기 | 🟡 차선 |
| C | 충돌 순간에 `[cancel_timer_stomped]` WARNING 만 남기고 **행위 불변** | `order_engine.py` 2곳 | 손절 미완결 위험 존치 | 🟠 최소 |

### 권고 = **A**

근거 셋:

1. **비대칭 해소가 원래 의도다.** cycle273a 가 해제를 order_no 로 좁힌 그 논리(`test_cycle273a...:221-222`)가 등록에도 그대로 적용된다. A 는 새 규약이 아니라 **미완성 규약의 완성**이다.
2. **잃는 것이 없다.** B 는 매수 잔량 취소를 버리는 교환이고, C 는 교환조차 없이 위험을 남긴다. A 만 양쪽을 다 지킨다.
3. **UI 계약이 보존된다.** `scheduler.py:1327` 이 `"pending_cancels": list(self.order_engine._pending_cancel_tasks.keys())` 로 내보내고 프론트(`frontend/src/types/trading.ts:175` · `frontend/src/components/OrderMonitor.tsx:115-119`)가 **ticker 배열**로 그린다. 키를 `order_no` 단독으로 바꾸면 화면이 조용히 주문번호로 바뀌지만, `(ticker, side)` 면 `sorted({tk for tk, _ in ...})` **한 줄 파생**으로 현행 의미가 그대로다.

🔴 **`order_no` 단독 키는 권고하지 않는다.** 더 정확하지만 (a) UI 의미가 바뀌고 (b) `_pending_cancel_order_no` 가 통째로 사라져 cycle273a·cycle291 의 가드 다수가 재작성 대상이 된다 — **이번 사이클이 고치려는 것에 비해 면적이 과하다.** 같은 축 두 매수 주문(§4 셋째)은 cycle331 이 착지하면 `is_ticker_blocked_for_buy` 가 구조적으로 막으므로 `(ticker, side)` 로 충분하다.

### A 의 계약 (구현자에게)

- 키 = `(ticker, side)` where `side ∈ {"buy", "sell"}` — **문자열 리터럴 2개를 모듈 상수로** 두고 두 등록 함수가 각각 자기 것만 쓴다.
- 등록: `if key in tasks: tasks[key].cancel()` — **같은 축 재스케줄만 교체**한다(부분체결이 연달아 오는 정상 동작 보존).
- 해제(`:2644`·`:2811`): `self._pending_cancel_order_no.get((ticker, "buy"))` / `("sell")` 로 좁힌다. **order_no 일치 게이트는 그대로 유지한다**(cycle273a 계약).
- `finally` 자기 pop(`:2903-2905`·`:3044-3046`): 같은 복합 키로. `is asyncio.current_task()` 동일성 가드 **유지**.
- `scheduler.py:3628-3632`(일일 clear)는 `.values()`/`.clear()` 라 **키 모양과 무관 = 무접촉**.
- `scheduler.py:1327` 만 `sorted({tk for tk, _ in ...keys()})` 로 한 줄 바꾼다. **프론트·`trading.ts` 무접촉.**
- 🔴 **`_cancel_after_wait`/`_cancel_and_reorder` 본문은 byte 동일로 둔다** — `tests/unit/ast/test_cycle295_ast_market_rest.py:76` 가 `cancel_remaining` 등 4함수의 **소스 세그먼트 sha 를 핀**하고 있다. 키 변경이 그 함수들의 본문(`finally` 블록)에 닿으므로 **핀 갱신이 딸려 온다** — 승인 면적에 포함해 계산한다.

### 8영역 승인 면적 (정리)

| 파일 | 8영역 | 변경 |
|---|---|---|
| `src/engine/order_engine.py` | ✅ | `__init__` 타입 2줄 · `_schedule_cancel` · `_schedule_cancel_and_reorder` · 해제 게이트 2곳 · `finally` pop 2곳 = **7곳** |
| `src/engine/scheduler.py` | 8영역 아님, 단 **라인 상한 `<3,900L`** 승인 대상 | `:1327` 1줄 (증감 0) |
| 테스트 | — | `test_cycle273a_cancel_timer_on_full_fill.py`(키 표현 5~7곳) · `test_cycle273a_ast_partial_optin_and_timer.py`(AST 가드) · `test_cycle287_krx_after_exit.py`(`_pending_cancel_tasks[_TICKER]` 6곳) · `test_cycle291_pre_nxt_gtp.py`(4곳) · `test_cycle329_...`·`test_cycle331_...`(각 1곳) · `tests/integration/test_reset_daily_state.py` |
| sha 핀 | — | `test_cycle295_ast_market_rest.py:76` 의 `_cancel_after_wait`/`cancel_remaining` 핀 재산정 |

🔴 **매매 행위를 바꾼다**(취소 타이머의 수명) → 루트 `CLAUDE.md` 자율 진행 규약상 **사용자 승인 + 이 자문 선행**이 모두 필요하다. 이 메모가 그 선행이다.

---

## 9. 시정 범위와 순서

### 지금(오늘 07:45 장외 창 안) — 순서가 중요하다

| 순서 | 항목 | 이유 |
|---|---|---|
| **1** | 🔴 **cycle331 을 그대로 배포한다** | cycle329 가 연 매수 축 구멍이 **오늘 09:00 부터 처음 열린다**. cycle331 의 게이트(`:2665`)가 그것을 닫는 유일한 코드다. §6 이 "복붙이 옳다" 를 확인했으므로 되돌릴 이유가 없다 |
| **2** | cycle332 = **안 A**(복합 키) | §4 의 A 구멍. 승인 대상 |

**1 과 2 를 한 배포에 묶어도 되고 나눠도 된다.** 다만 **1 을 2 때문에 미루면 안 된다** — 1 은 이미 구현돼 있고 회귀도 서 있다(`tests/unit/engine/test_cycle331_buy_fill_from_pending.py`, 6케이스).

### 이번 사이클 밖 (별건 카드)

| 카드 | 내용 |
|---|---|
| J-1 | 🔴 **§10 의 새 결함** — `cancel_remaining` 배선 |
| J-2 | `_cancel_and_reorder`(`:3028`)의 `place_order` 직전에 **포지션 재조회가 없다**. cycle327 은 `execute_sell` 루프에만 재조회를 넣었다. 30초 전 스냅샷 `remaining` 을 그대로 쏜다 — 지금은 취소 실패가 `raise` 로 재주문을 막아 주지만(`:2962-2964`), 그건 우연한 방어다. **피라미딩 착수 시 필수** |
| J-3 | 부분체결 뒤 취소된 주문의 `trade_history` 행이 **`PARTIAL` + 주문수량**으로 영구 잔존한다. `update_trade_status` 는 `quantity` 를 **SET 하지 않고**(`src/db/trade_history.py:129-137`), CANCELLED 호출은 `match_partial=False` 라 PARTIAL 행을 못 잡는다(cycle273a 의도). 실측 = `257720 BUY PARTIAL qty=2` 가 08-28 부터 24일째 잔존. 성과 집계 왜곡 가능성 — **측정 먼저** |
| J-4 | §5 의 구멍 C(발사 창 두 번째 부분체결의 수량 갱신 유실) |

---

## 10. 새 결함 — `cancel_remaining` 은 프로덕션 호출자가 0 인데, 정본이 그것을 「회수 경로」로 약속한다

### 사실

```
$ grep -rn "cancel_remaining" --include="*.py" src tests
src/engine/order_engine.py:3071   async def cancel_remaining(...)   ← 정의
tests/... (호출은 테스트 4곳뿐)
```

**`src/` 안에 `cancel_remaining` 을 부르는 코드가 한 줄도 없다.** 그런데 `src/engine/CLAUDE.md:416` 은 cycle295 의 15:30~16:00 완전 휴식 컷을 이렇게 정당화한다:

> 컷이면 **취소도 하지 않고** 작동 중인 주문을 그대로 둔다(16:00 이후 `cancel_remaining` 또는 `risk.on_tick` 재평가에 위임한다).

그리고 `tests/unit/engine/test_cycle295_market_rest_cut.py:617` 이 같은 문장을 복창한다.

### 왜 결함인가

- 컷에 걸린 `_cancel_and_reorder`(`:2936-2944`)는 **취소도 재주문도 하지 않고 return** 한다. 원 매도 주문은 호가에 남는다.
- 약속된 회수처 둘 중 **`cancel_remaining` 은 존재하지 않는 경로**다. 남는 것은 `risk.on_tick` 재평가뿐인데, 그건 **새 매도 주문을 내는 것**이지 호가에 걸린 미체결을 취소하지 않는다.
- 🔴 **거래소별 존속 규약이 이 구멍을 가른다**(`src/engine/CLAUDE.md` session.py 절): **KRX 는 정규장 마감 후 미체결 자동취소**라 거래소가 대신 치워 준다. **NXT 는 미체결이 애프터까지 유지**된다. 운영 DB 7전략 `exchange` 가 전부 `NXT` 이므로(메모리 `project_live_db_param_deltas`), **NXT 로 나간 손절 지정가 잔여는 15:30 컷 이후 20:00 까지 호가에 산다.**
- 그 상태에서 16:00 KRX 애프터 진입 후 `risk.on_tick` 이 다시 손절을 내면 **같은 포지션에 두 개의 매도 주문**이 뜬다(= cycle327 이 봉한 「이미 판 것을 다시 판다」와 같은 계열). `_selling` 가드가 살아 있으면 막히지만, 15:30~16:00 컷 구간에서 `_selling` 이 어떻게 남는지는 경로마다 다르다.

### 막는 법 (세 갈래, 값싼 것부터)

1. **정본을 사실로 고친다** — `src/engine/CLAUDE.md:416` 과 cycle295 테스트 docstring 에서 `cancel_remaining` 을 위임처로 적은 문장을 지우고 "그 구간 잔여는 **회수 경로가 없다**(KRX 는 거래소 자동취소, NXT 는 20:00 까지 존속)" 로 바꾼다. 8영역 무접촉·매매 행위 0.
2. **가드를 세운다** — `src/` 안 `cancel_remaining` 호출 수가 0이면 **RED** 인 텍스트 가드. "배선하든지 지우든지" 를 강제한다. 🔴 **가드는 고치면 초록이 되어야 한다**(메모리 `feedback_guard_must_be_fixable`) — 지금 상태(호출 0)가 붉은 것이 맞고, 1번 문서 시정만으로는 초록이 되지 않게 **가드의 판정 대상은 호출 수**로 둔다. 즉 이 가드는 3번을 하기 전까지 의도적으로 붉다 → **그러면 CI 가 상시 붉어 무시당한다.** ⇒ **가드 대신 `_workspace/00_URGENT_WORKLIST.md` 카드로 둔다.**
3. **실제 배선**(매매 행위 변경, 별건 승인) — 16:00 KRX 애프터 진입 시 컷으로 남은 미체결을 한 번 회수한다. 🔴 단 이건 **KRX 애프터에서 새 손절 호가(44/41)를 내는 경로와 충돌하지 않게** 설계해야 한다. cycle287 의 애프터 청산 규약을 먼저 읽는다.

**권고 = 1 즉시 + 3 은 워크리스트 카드.** 2 는 넣지 않는다(상시 RED 가드 금지).

---

## 11. 관측 — 마커 제안

### M1 (안 A 동반, 필수) — `[cancel_timer_conflict]`

복합 키 도입 뒤에도 **충돌이 있었는지**를 세야 한다. 안 A 는 충돌을 없애는 게 아니라 **공존시키는** 것이므로, 같은 종목에 두 축 타이머가 동시에 살아 있던 사건 자체가 관측 대상이다.

```
[cancel_timer_conflict] ticker= side= other_side= other_order_no= new_order_no= coexist=1
```

- **레벨 = WARNING.** 21:30 리포트 `top_patterns` 는 WARNING 이상만 집계한다(ρ축 마커가 INFO 라 리포트에 한 글자도 안 들어가 오귀인을 낳은 선례의 반대).
- cap = `KstDailyEmitCap[(ticker, side)]` **1회/일**. 🔴 무cap 으로 두지 않는다 — 부분체결이 연달아 오면 폭주한다.
- **행위는 cap 밖.** 마커 실패가 타이머 등록을 바꾸면 안 된다(`observer_trace.trace_observer_failure` 규약).
- **판독**: `coexist=1` 이 한 번이라도 뜨면 **HEAD 였다면 손절 타이머가 죽었을 순간**이다 = 이 사이클의 성공 서명.

### M2 (안 A 없이 안 C 만 갈 때) — `[cancel_timer_stomped]`

```
[cancel_timer_stomped] ticker= killed_side= killed_order_no= new_side= new_order_no=
```
레벨 WARNING, cap `[(ticker, killed_side)]` 1회/일. **빈도 실측 전용**이고 그 자체로는 아무것도 고치지 않는다.

### M3 (이미 있음, 판독 규칙만 추가) — `[buy_partial_no_cancel_timer]`

cycle331 이 넣은 마커(`:2668-2673`). 판독을 정본에 적어 둔다:

| 관측 | 뜻 |
|---|---|
| `src=payload` + `from_pending=0` | 🔴 **수동/외부 주문의 부분체결이다 — 우리가 안 건드렸다(성공 서명)** |
| `src=payload` + `from_pending=1` | 발사 창에 착지한 **우리** 매수. ms 뒤 `src=map` 통보가 따라와야 정상 |
| `src=increment` | payload 가 안 실려 온다 — cycle329 의 남은 사각. 누적되면 조사 |
| `remaining` 이 큰 값으로 반복 | §5 구멍 D(영구 미취소)의 규모 |

### M4 — 일일 요약에 한 줄

`_settle()` 직전 `[fill_qty_src_summary]`(cycle329) 옆에 **타이머 축 1행**을 붙인다:

```
[cancel_timer_summary] window=day buy_scheduled= sell_scheduled= buy_gated= conflicts=
```

🔴 호출부를 `try/except` 로 감싸지 않는다(scanner 일일 summary 2종과 같은 이유 — 감싸면 폐기 메서드 잔존 호출 같은 결함이 조용히 먹힌다).

---

## 12. 반례 / 한계

1. 🔴 **§8 의 권고는 「빈도가 낮으니 미루자」는 반론에 취약하다.** 실측은 5개월 2건이고, 매도 부분체결은 **0건**이다. 순수 기대값으로는 안 C(관측만)가 합리적이다. 내 권고가 A 인 근거는 통계가 아니라 **손실의 비대칭**이다 — 잃을 때 잃는 것이 손절 커버리지다. **team-leader 가 이 교환을 명시적으로 고르는 것이 맞다.**
2. **`(ticker, side)` 는 같은 축 두 주문을 여전히 못 가른다.** cycle331 이 착지하면 `is_ticker_blocked_for_buy` 가 구조적으로 막지만, 그 전제가 깨지면(예: 전략별 중복 매수 허용, 피라미딩 도입) **같은 결함이 매수 축 안에서 부활한다.** 🔴 **피라미딩 착수 사이클은 이 키를 `order_no` 로 다시 검토한다.**
3. **S1/S2 의 진입 조건(우리 매수 미체결 잔여 + 같은 종목 손절)은 랏이 커질수록 흔해진다.** 지금 랏이 1~2주라 희귀한 것이고, 비중 재배분(메모리 `project_lot_geometry` 의 `q ≥ N` 논의)이 진행되면 **부분체결 빈도 자체가 오른다.** 이 사이클의 값은 앞으로 커진다.
4. **실측 표본의 한계** — `system_logs` INFO retention 이 2일(현재 최고참 INFO = 2026-09-16 21:31)이라 `[partial_cancel_timer_cleared]`·`매수 부분 체결`·`[after_cancel_result]` 는 **과거를 볼 수 없다**. §7 의 2건은 ERROR(30일)로 살아남은 것뿐이고, **실제 발화 횟수는 그보다 많을 수 있다.**
5. **`cancel_all` 을 「그 주문 한 건」으로 읽은 근거는 우리 body 구성이지 KIS 문서 원문이 아니다.** `docs/kis/*.md` 는 2026-09-11 스냅샷이라 별도 확인 대상이다. 다만 `ORGN_ODNO` 가 필수 키라는 사실만으로 "종목 전체 취소" 해석은 배제된다.
6. **§10 의 중복 매도 시나리오는 추론이다.** 15:30~16:00 컷 구간에서 `_selling` 이 어떤 경로로 남는지 코드 전수를 따라가지 않았다 — 카드로 넘길 때 그 확인이 선결이다.

---

## 13. 후속 검증 권고

### tdd-engineer 에게 (안 A 채택 시 Red)

| ID | 시나리오 | 기대 |
|---|---|---|
| R1 | 매수 부분체결(타이머 B) → **같은 ticker** 매도 부분체결(타이머 A) | **두 task 가 모두 살아 있다**(`not done()`). HEAD 에서는 B 가 죽는다 |
| R2 | R1 역순(매도 먼저 → 매수) | 동일 |
| R3 | 매도 부분체결 → 같은 ticker 매수 부분체결 → `PARTIAL_FILL_WAIT` 경과 | **`cancel_order` 가 2회**(매수 잔여 + 매도 잔여) 호출되고, `place_order` 재주문이 **1회**(손절 잔여) 발사된다. HEAD 에서는 매도 잔여 재주문이 **0회** |
| R4 | 같은 축 재스케줄(매수 부분체결 2회, 같은 order_no) | 타이머가 **교체**된다(구 task `done()`, 신 task 생존) — 현행 행위 보존 |
| R5 | 매도 **전량**체결이 매수 타이머를 건드리지 않는다 | `test_a3`(`:251`)의 복합 키 버전 — **의미 보존 확인** |
| R6 | `scheduler.get_status()` 의 `pending_cancels` | **ticker 문자열 배열**이고 중복이 없다(복합 키 파생 검증). 프론트 계약 보존 |
| R7 | 수동 주문(`_order_qty` 미등록) 부분체결 | `_pending_cancel_tasks` 가 **비어 있고** `[buy_partial_no_cancel_timer] src=payload from_pending=0` 1행 — cycle331 게이트의 양성 대조군 |

🔴 **R3 이 이 사이클의 본체다.** R1/R2 는 상태만 보므로 `finally` 를 지워도 초록일 수 있다 — **행위(`cancel_order`/`place_order` 호출 수)를 재는 R3 이 없으면 뮤테이션이 빠져나간다.**

🔴 **돌연변이 검증 2개를 같이 심는다**: ① `_schedule_cancel` 의 side 를 `"sell"` 로 바꿔치기 → R1 이 붉어야 한다 ② 해제 게이트의 복합 키에서 side 를 지워 ticker 단독으로 → R5 가 붉어야 한다. 하나라도 초록이면 가드가 공허하다.

### tester 에게

- **D+1(2026-09-22) 아침 판독 3종**: `[buy_partial_no_cancel_timer]` 유무 → §11 M3 표로 분류 / `[fill_qty_src]` WARNING(payload·increment) 카운트 → cycle329 의 첫 거래일 실측 / `[buy_fill_strategy_from_pending]` 유무 → cycle331 의 성공 서명.
- 🔴 **`[buy_fill_fallback_held_conflict]` 의 메시지 문구가 2026-09-21 에 바뀐다**(cycle331, `"이미 타 전략 보유 중"` → `"타 전략 보유/주문중"`). 21:30 리포트 `top_patterns` 는 메시지 전문을 키로 쓰므로 **그 날짜 전후 패턴 문자열을 비교하지 않는다.**

### team-leader 에게 — 결정할 것 2개

1. **§8 의 안 A / B / C 중 어느 것인가.** (권고 A. 8영역 7곳 + `scheduler.py` 1줄 + sha 핀 재산정 + 테스트 6파일)
2. **§9 순서 1 — cycle331 을 오늘 07:45 전에 배포하는가.** (권고 예. cycle329 가 연 구멍이 오늘 09:00 부터 처음 열린다)

---

**한 줄 요약** — 주장 1 참(등록 경로가 아직 ticker 로 뭉갠다, cycle273a 가 해제만 고쳤다) · 주장 2 결론만 참(원인은 `cancel_all` 이 아니라 남의 `order_no`, cycle331 게이트가 **완전히** 닫는다) · 주장 3 은 cycle331 로 이미 해소 · B3 의 "복붙 금지" 경고는 **틀렸다**(우리 주문은 `src=map` 이라 자동취소가 사라지지 않는다) · 이번 사이클 대상은 **매수↔매도 타이머 공유 하나**이고 권고는 `(ticker, side)` 복합 키다.
