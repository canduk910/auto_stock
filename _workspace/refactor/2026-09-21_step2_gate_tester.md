# 2단계 코드리뷰 관문 — tester (행위 보존)

> 대상 = `src/engine/order_engine.py` — 접수 후 PENDING 영속화를 4경로 1코어로
> (`_persist_pending_after_send`). 설계 카드 = [`2026-09-21_step2_card.md`](2026-09-21_step2_card.md)
> 진행 규약 = [`2026-09-20_execute_sell_plan.md`](2026-09-20_execute_sell_plan.md)
> 1단계 관문(방법 재사용) = [`2026-09-20_step1_gate_tester.md`](2026-09-20_step1_gate_tester.md)

## 측정 환경 — 공유 워크트리 `src/`·`tests/` 는 한 글자도 쓰지 않았다

1단계 사고(두 리뷰어 동시 돌연변이 → 129 errors) 재발 방지로 **격리 스냅샷 2개**를 떴다.

| 스냅샷 | 구성 | `order_engine.py` sha |
|---|---|---|
| `head` | `git archive HEAD`(cycle333 `42644e0`) | `e1beeb1fffab6ca5` |
| `work` | 위 + 워크트리 수정분 전부(src·tests·docs) | `1aa8d1b6c93eae6d` |

돌연변이는 **`work` 스냅샷 안에서만** 적용·원복했고, 매 회차 pristine 사본에서 다시 만들어
"내 변경만 들어갔다" 를 앵커 유일성(`count(old)==1`)으로 강제했다. 모든 실행 전후로
공유 워크트리 sha 를 재확인했고 `1aa8d1b6c93eae6d` 로 불변이었다.

자산 = `<scratchpad>/step2/{head,work}` · `cap_{HEAD,WORK}.json` · `yield_{HEAD,WORK}.json` ·
`mutate.py` · `order_engine_WORK_pristine.py`
(`<scratchpad>` = `/private/tmp/claude-501/-Users-koscom-Projects-auto-stock/0ab1df6c-a50f-4d03-a764-95fae85df295/scratchpad`)

---

## 1. 매수 두 경로의 예외 전파가 한 글자도 안 바뀌었는가 — **그렇다**

### 1-a. 구조 — 핸들러 체인이 같은 순서로 닿는다

코어에 `ast.Try` **0건**(`_persist_pending_after_send` AST 실측), `await` **1건**이고 그것이
`_insert_pending_or_absorb_race` 다. 따라서 코어가 던지는 모든 예외는 호출부의 문맥으로
그대로 올라간다. 두 판본에서 그 문맥을 AST 로 떠서 대조했다(핸들러 본문은 그 `try` 의
보호 밖이므로 제외하고 계산).

| 호출부 | HEAD | WORK |
|---|---|---|
| 매수 주 경로 | `try@1275[KisApiError@1386, Exception@1511]` | `try@1312[KisApiError@1412, Exception@1524]` |
| 매수 폴백 | `try@1414[KisApiError@1501]` | `try@1440[KisApiError@1514]` |

**핸들러 개수·타입·순서가 동일**하다. 폴백이 바깥 `try` 에 안 걸리는 것(= non-`KisApiError`
가 `execute_buy` 를 관통한다)도 **양쪽 모두 그대로**다 — 그것이 카드 §2B 가 결함으로
지목한 구조이고, 이 단계는 그것을 **보존**한다.

### 1-b. 런타임 — 4 예외타입 × 매수 2경로 = **8축 전부 동일**

`insert_trade` 를 `TimeoutError` / `RuntimeError` / `UniqueViolationError` / `KisApiError` 로
터뜨리고 12개 상태축을 캡처해 HEAD↔WORK 를 diff 했다. **전부 동일**이다.

```
E_buy_main_TimeoutError        raised=TimeoutError  place_order=1  pending_buys=[]  pend_amounts={}
                               order_qty={'BUY-000001':3}  pending_buy_orders=['BUY-000001']
                               cached_buyable_at==0 → False   blocked_for_buy=False
E_buy_main_KisApiError         raised=KisApiError   place_order=1  (미분류 재전파)
E_buy_fb_TimeoutError          raised=TimeoutError  place_order=2  pending_buys=['012200'] 유지
E_buy_fb_KisApiError           raised=None          place_order=2
                               ERROR "지정가 폴백도 거부 → cooldown" + low_funds_blocked=True
```

🔴 **마지막 줄이 카드 §2B ④ 의 실측이다** — 폴백 주문이 **접수에 성공**(`place_order` 2회)
했는데 장부에는 "폴백도 거부"로 적히고 cooldown 이 걸린다. 1단계 관문의 매도 N3/N4 와
**같은 사슬**이다. 다만 **HEAD 도 한 글자까지 같다** — 이 단계가 만든 결함이 아니고,
이 단계는 그 결함을 그대로 보존한다.

⚠️ 카드 §2B ④ 가 예고한 「주 경로에서 `KisApiError` 가 새면 `:1418` 에서 **두 번째 매수
주문을 발사**」는 이번 표본에서 **재현되지 않았다**(`place_order=1`). `EGW00201` msg1 이
`is_market_order_disallowed` 키워드에 안 걸려 미분류 `raise` 로 빠지기 때문이다.
카드의 "**구조는 열려 있다**(오늘은 도달 불가)" 표현이 정확하다.

---

## 2. 매도 축도 보존됐는가 — **그렇다**

`[sell_post_send_error]` 를 4 예외타입 × 2경로 = **8축 전부 캡처**했고 HEAD↔WORK **완전 동일**.

```
X_sell_main_*   raised=None  place_order=1  selling=['012200']  positions=['012200']
  ERROR [sell_post_send_error] ticker=012200 order_no=SELL-000001 strategy=momentum path=market
        — 주문은 접수됐다. 재발사하지 않고 체결통보·동기화에 맡긴다.
X_sell_fb_*     raised=None  place_order=2  selling=['012200']  positions=['012200']
  ERROR [sell_post_send_error] … path=fallback — (같은 꼬리)
```

**cycle327 ⓑ 계약 유지 확인**

- 주 경로 재발사 **0** — `place_order` 가 1회다(재시도 루프 미진입).
- 폴백 `execute_sell` 관통 **0** — 4 예외타입 전부 `raised=None`.
- 발화 조건·필드(`ticker`/`order_no`/`strategy`/`path`)·꼬리 문구 **byte 동일**.
- `_selling` 유지 · `positions` 유지 · `_pending_next_day_clear` 무변동.

구조 가드도 그대로다 — 래퍼 `_persist_sell_pending_after_send` 는 `try` **1개**,
핸들러 **1개**, 타입 `Exception`(`test_g328_3`/`3b` 초록). 래퍼가 1문 `try` 로 얇아져
오히려 더 조여졌다.

---

## 3. 로그 렌더 byte 대조 — **카드 주장이 정확하다. 변경은 정확히 1건이고 정보가 느는 방향이다**

4경로를 **실제로 실행해** WARNING 을 렌더하고 캡처 36축을 diff 했다 → **35축 동일, 1축 상이**.

| 경로 | HEAD | WORK | 판정 |
|---|---|---|---|
| 매수 주 | `매수 응답보다 체결통보 선행 — PENDING INSERT 생략: 테스트종목(012200) (주문번호: BUY-000001)` | 동일 | **byte 동일** |
| **매수 폴백** | `폴백 응답보다 … 생략: 테스트종목(012200)` | `폴백 응답보다 … 생략: 테스트종목(012200) (주문번호: BUY-000001)` | 🔴 **1건 변경** |
| 매도 주 | `매도 응답보다 … (주문번호: SELL-000001)` | 동일 | **byte 동일** |
| 매도 폴백 | `매도 폴백 응답보다 … (주문번호: SELL-000001)` | 동일 | **byte 동일** |

`_completed_orders` 잔여(소비/discard)도 4경로 전부 동일하다.

**정보가 느는 방향인가 — 그렇다.** 잃는 토큰이 없고 `(주문번호: %s)` 하나가 붙는다.
지금 그 줄은 **어느 주문이 skip 됐는지 말하지 않는** 유일한 경로였고, 이제 4경로가 균일하다.

**21:30 리포트 파급 (실측)** — `log_metrics_collector._normalize_message` 에 4 문구를 통과시켰다.

- 매수 폴백 패턴 키는 **바뀐다**(카드 경고대로) → **2026-09-21 전후 그 패턴 문자열을 직접 비교하지 않는다.**
- 4경로 패턴 키는 여전히 **서로 다르다** — 병합되지 않는다(경로별 집계 보존).
- 건수 영향 0.

⚠️ `("buy","fallback") → "폴백 "` 이 다른 셋과 비대칭인 것(`"매수 폴백 "` 이 아니다)은
카드가 밝힌 대로 **현행 보존 선택**이다. 나는 그 선택에 동의한다 — 문구 변경을 1건으로
묶는 쪽이 이 단계의 판정을 단순하게 만든다. 다만 **정규화는 2B 에서 함께 하는 것이 좋다**
(그때 매수 폴백 패턴 키가 어차피 한 번 더 바뀐다면 두 번 나눠 바꿀 이유가 없다).

---

## 4. `record` 9필드 — 4경로 전부 추출 전후 동일

런타임 캡처(WORK, HEAD 와 **완전 동일**):

| 경로 | trade_type | price | quantity | 나머지 6필드 |
|---|---|---|---|---|
| 매수 주 | **BUY** | 4500.0 | 3 | ticker `012200` · ticker_name `테스트종목` · profit_loss 0 · status PENDING · strategy momentum · order_no BUY-000001 |
| 매수 폴백 | **BUY** | **4525.0**(`step_up(4500,5)`) | 3 | 〃 |
| 매도 주 | **SELL** | 4500.0(`pos.buy_price`) | **10**(`pos.quantity`) | 〃 SELL-000001 |
| 매도 폴백 | **SELL** | **4475.0**(`step_down(4500,5)`) | 10 | 〃 |

`profit_loss` 는 매수 생략 ↔ 모델 기본값 `0` 이라 **같은 값 0.0** 으로 확인됐다(카드 주장 검증).

**뒤집으면 붉어지는가** — 돌연변이로 확인했다.

- 매수 주 `trade_type=BUY→SELL` → **7건 붉음**(cycle333 A3 + cycle271 C2-1/C2-2/C5-1/C7-1/C7-2/B-1)
- 매수 폴백 `trade_type=BUY→SELL` → **3건 붉음**(cycle333 A3 폴백 + cycle271 C2-4/C5-2)
- 코어의 `price`↔`quantity` 맞바꿈 → **10건 붉음**(4경로 전부)

즉 **`trade_history` 매수/매도 뒤집힘은 방어된다.**

---

## 5. 양보점 불변 — **최초 suspension 은 여전히 `await insert_trade` 다**

구조: 코어 본문의 `await` 는 1건뿐이고 그것이 `_insert_pending_or_absorb_race` 호출이며,
그 함수의 첫 문장이 `await insert_trade(record)` 다. `side` 파생·`_completed_orders` 판정·
`TradeRecord` 조립에 `await` 0건.

런타임으로도 쟀다. `place_order` 반환 직전에 `asyncio.create_task` 로 마커를 걸고
`insert_trade` 진입 시점에 그 마커가 돌았는지 본다(마커는 **이벤트 루프가 제어를 잡아야만** 돈다).

| 경로 | `place_order`↔`insert_trade` 사이 루프 양보 | 양성 대조군(`sleep(0)` 뒤) |
|---|---|---|
| 매수 주 · 매수 폴백 · 매도 주 · 매도 폴백 | **False (= 0회)** | **True** |

HEAD↔WORK 동일. ⚠️ **첫 측정은 공허했다** — 카운터가 0/0 이라 "양보가 없다" 와 "측정기가
안 돈다" 를 구분하지 못했다. 양성 대조군을 넣어 재설계한 뒤의 값이 위 표다.

따라서 「주문번호 매핑은 `place_order` 응답 직후 동기 영역」 금기의 전제가 유지된다.
매핑 블록(5종 + `_pending_buy_orders`)은 한 줄도 움직이지 않았고 `_order_exchange[` 5곳
카운트도 불변이다(`test_cycle291_ast_scope::test_a10c` 초록).

---

## 6. 매수 쪽에만 있는 것 — 전부 헬퍼 **밖**, 순서 보존

`execute_buy` 시작점 기준 **상대 오프셋**으로 대조했다(절대 라인은 코어 삽입분만큼 밀린다).

| 관심사 | HEAD 오프셋 | WORK 오프셋 |
|---|---|---|
| ⑥ `calc_buy_quantity` | +75 | **+75** |
| ⑨ `pending_buys.add` / `pending_buy_amounts[...]` | +116 / +118 | **+116 / +118** |
| ⑫ 발사 `place_order` | +240 | **+240** |
| ⑭ 매핑 5종 (`_order_qty` … `_order_exchange`) | +248 / +257 | **+248 / +257** |
| ⑭ `_pending_buy_orders` 등록 | +263 | **+263** |
| ⑮ `llm_buy_gate.observe_order` | **+276** | **+276** |
| ⑯ 선행체크 + INSERT ↔ **코어 호출** | +308 … +327 | **+311**(한 문장) |
| ⑰ `cached_buyable_at = 0.0` | +335 | +324 |
| ⑨ `pending_buys.discard` / `pend_amounts.pop` | +338 / +339 | +327 / +328 |

폴백 경로도 같은 모양이다(훅 +399→+388, 코어 +423→+412, 캐시무효화 +450→+426).

- **훅 순서 계약(cycle276 C7/C8) 보존** — 훅은 여전히 매핑 **뒤** · 선행판정/INSERT **앞**이다.
  가드는 앵커를 `_persist_pending_after_send` 호출 lineno 로 재조준했고(`test_c1_7`/`c1_8`/`c1_9`)
  전부 초록이다. 재조준 docstring 이 "🔴 `ast.Compare` 로 되돌리면 `execute_buy` 안에 0건이라
  **가드가 공허해진다**" 를 명시한 것이 정확하다 — 그 함정을 피했다.
- 런타임으로도 훅 인자를 확인했다: 주 `{order_no: BUY-000001, path: market, price: 4500, qty: 3}` /
  폴백 `{order_no: BUY-000001, path: fallback, price: 4525, qty: 3}`. HEAD 와 동일.
- `_pending_buy_orders` · `pending_buys` · `pending_buy_amounts` · `cached_buyable_at` 은
  **코어 안에서 한 번도 참조되지 않는다**(AST 확인) — 전부 헬퍼 밖에 남았다.

---

## 7. 회귀 실행

전부 실행 전후로 소스 sha 를 확인했다(`1aa8d1b6c93eae6d` 불변).

### 7-a. 매수 축 — **195 passed**

```
tests/unit/engine/test_order_engine_buy.py
tests/unit/engine/test_cycle271_execute_buy_fill_during_insert.py
tests/unit/engine/test_cycle276_order_time_hook.py
tests/unit/engine/test_cycle291_pre_nxt_gtp.py
tests/unit/engine/test_cycle331_buy_fill_from_pending.py
tests/unit/engine/test_cycle329_mapping_absent_full_fill.py
tests/unit/engine/test_cycle332_cancel_timer_key.py
tests/integration/test_chegyeol_race.py
→ 195 passed in 1.23s
```

### 7-b. 매도 축 — **121 passed**

```
test_cycle327_sell_fill_during_insert · test_order_engine_sell_fallback ·
test_cycle229_sell_fallback_e2e · test_cycle236_sell_qty_exceeded ·
test_cycle287_krx_after_exit · test_order_engine_sell_pre_nxt_preconvert ·
tests/unit/ast/test_cycle185_cluster1_ast · test_cycle185_cluster1_reset ·
tests/integration/test_sell_rejection_integration · tests/unit/ast/test_cycle328_sell_pending_helper
→ 121 passed in 7.39s
```

### 7-c. AST 가드 전체 — **1806 passed, 4 skipped, 26 xfailed**

1단계 시점 1805 → **+1**(신규 `test_g328_0d`). sha 재핀 10 파일 전부 신규 값
`1aa8d1b6c93eae6dd27182fefc4d485056cb4175aff7166789222df613db6285` 로 일치하고
구 sha `e1beeb1f…` 는 `tests/`·`src/` 에 **0건**(설계 카드 본문에만 기준값으로 남아 있다).

### 7-d. 백엔드 광역 — **7484 passed, 2 failed (둘 다 선재)**

```
tests/unit/engine tests/integration tests/unit/db
→ 2 failed, 7484 passed, 7 skipped, 282 xfailed, 11 xpassed in 88.40s
FAILED tests/unit/engine/strategies/test_cycle226_zero_breakout_defense.py::test_common_1_eight_areas_untouched
FAILED tests/unit/db/test_cycle64_price_filter_scanner_system_config.py::test_A1_get_price_filter_default_no_mode_field
```

**둘 다 이번 변경과 무관하다.** 근거 2:
- **HEAD 스냅샷에서 같은 인자로 돌려도 똑같이 붉다**(`4 failed, 7512 passed` — 나머지 2건은
  내가 넣은 프로브 파일이 `CAP_OUT` 없이 수집된 것이라 무관).
- 실제 워크트리에서 각각 단독 실행하면 **초록**이다(`test_cycle226` 35 passed / `test_cycle64` 4 passed).
  `test_cycle226` 은 스냅샷에 `.git` 이 없어 붉은 8영역 digest 가드이고,
  `test_cycle64` 는 1단계 관문이 이미 적어 둔 **순서 의존 선재 결함**이다.

### 7-e. 코어 헬퍼 커버리지 — **미커버 0줄 · 미커버 분기 0**

`_persist_pending_after_send` = `order_engine.py:1005-1047`,
래퍼 `_persist_sell_pending_after_send` = `:1049-1084`(AST `lineno`/`end_lineno` 실측).

```
src/engine/order_engine.py  … Missing: … 981-982, 1103-1104, 1107-1111, …
                                 부분분기: 141->155, 1848->1850, 1850->1852, 2179->1713, 2642->2655, 2951->exit
```

**`1005-1084` 구간이 Missing 목록에 한 줄도 없고 부분 분기에도 없다.** 인접 미커버가
`981-982` 와 `1103-1104` 라 두 함수가 그 사이에 통째로 덮여 있음이 경계로도 확인된다.

---

## 8. 내가 고안한 돌연변이 — **7종. 하나가 그물을 통째로 빠져나간다**

team-lead 가 확인한 셋(코어에 `try` 내리기 · `trade_type` 고정 · 매수 폴백 인라인 되돌리기)
말고, **이 추출이 새로 만든 단일 실패점**을 겨냥했다. 판정 기준 = 격리 스냅샷 자체 베이스라인
(행위 258 passed / AST 15 failed·1795 passed — AST 의 15는 `.git` 부재 구조 실패다).
sha 핀 7건은 어떤 돌연변이에도 붉으므로 **판별기에서 제외**했다.

| # | 돌연변이 | 행위 회귀 | 구조 AST |
|---|---|---|---|
| MT-A | `_PENDING_SIDE_BY_TRADE_TYPE` 값 맞바꿈(`BUY→"sell"`, `SELL→"buy"`) | ✅ **4건 붉음** | 없음 |
| **MT-B** | 코어의 `_insert_pending_or_absorb_race(…, path=path)` → **`path="market"` 고정** | 🔴 **258건 전부 초록** | 🔴 **없음** |
| MT-C | 코어의 `price=record_price, quantity=quantity` **맞바꿈** | ✅ **10건 붉음** | 없음 |
| MT-D | `_PENDING_SKIP_PREFIX.get((side, path))` → `.get((path, side))` | ⚠️ **1건만**(매도 축) | 없음 |
| MT-E | 코어의 skip 분기 무력화(`if False and …`) | ✅ **5건 붉음** | 없음 |
| MT-F | 매수 **주** 호출부 `trade_type=BUY→SELL` | ✅ **7건 붉음** | 없음 |
| MT-G | 매수 **폴백** 호출부 `trade_type=BUY→SELL` | ✅ **3건 붉음** | 없음 |

### 🔴 MT-B — 이 추출이 새로 만든 단일 실패점이고, **아무것도 막지 않는다**

코어가 받은 `path` 를 흡수기로 **전달하는 한 줄**을 `"market"` 리터럴로 바꾸면
`[buy_fill_during_insert] path=` · `[sell_fill_during_insert] path=` 가 **폴백 2경로에서 거짓**이
된다(주 경로는 원래 `market` 이라 무증상). 그런데 **행위 258건이 전부 초록**이고
구조 가드도 없다.

- **추출 전에는 이 자리가 없었다.** 네 호출부가 각자 `path="market"`/`"fallback"` 리터럴을
  직접 흡수기에 넘겼으므로, 한 곳을 깨면 한 경로만 오염됐고 1단계 관문의 T-2(호출부 리터럴
  맞바꿈)가 2건을 붉혔다. 지금은 **전달 한 줄**이 매수·매도 두 폴백을 동시에 결정한다.
- **피해는 관측 한정**(매매 행위 0). `path` 는 `_insert_pending_or_absorb_race` 의 INFO 로그
  에만 쓰인다. 다만 그 필드가 "INSERT 도중 체결이 주 주문에 착지했나, 5호가 지정가 폴백
  주문에 착지했나" 를 읽는 **유일한 채널**이고, 그 판독이 정확히 뒤집힌다.
- ⚠️ 더 나쁜 점 = **skip WARNING 의 수식어는 계속 올바르다**(같은 `path` 를 쓰지만 다른 표를
  탄다). 즉 두 관측 채널이 **조용히 갈라진다** — 로그만 보면 모순이 안 보인다.
- **되돌릴 사유는 아니다.** 현 판본은 `path=path` 로 올바르고, 이건 결함이 아니라 **그물 구멍**
  이다. 1단계 T-1(로그 수식어 단일 실패점)과 같은 계열이다.

→ **tdd-engineer 의뢰**: `[buy_fill_during_insert]`/`[sell_fill_during_insert]` 의 `path=` 필드를
**4경로 쌍으로** 고정하는 회귀 1~2건. cycle271 `test_c5_2` · cycle327 `test_sell_emits_fill_during_insert_marker`
가 이미 그 마커를 잡으므로 **단언 한 줄 추가**로 끝난다.

### ⚠️ MT-D — 매수 축 문구 그물이 여전히 0건이다(그리고 그 원인을 찾았다)

키 튜플 순서를 뒤집으면 `.get` 이 전부 miss → **4경로 수식어가 모두 사라진다**
(`응답보다 체결통보 선행 — …`). 붉어지는 것은 매도 축의
`test_sell_pending_skip_warning_distinguishes_market_and_fallback` **한 건뿐**이다.

**원인 = 카드의 선행 의뢰 J-BUY-1~4 가 착지하지 않았다.**

- `git diff HEAD -- tests/unit/engine/test_order_engine_buy.py` = **무변경**
- `grep -rn "PENDING INSERT 생략" tests/` = 매도 축·주석뿐, **매수 축 단언 0건**

카드가 「M-B3·M-B5 는 J-BUY-3/J-BUY-1·2 가 닫는다」고 적은 그 핀들이다. 지금은 **코어 공유
덕분에 매도 가드가 매수 축까지 전이적으로 덮는** 상태다(MT-D 가 잡힌 이유). 그건 이 리팩토링의
**소득**이지만, 매수 전용 오염(예: 매수 프리픽스 두 값만 뭉개기)은 여전히 무방비다.

→ **tdd-engineer 의뢰**: J-BUY-3·J-BUY-4(매수 skip 문구 쌍 + `order_no` 포함)와
J-BUY-1·J-BUY-2(접수 후 전파·상태 핀). 특히 **J-BUY-2(폴백 축)는 리포 전체 회귀 0건**이고
2B 가 그것을 다시 쓸 때 "무엇이 바뀌었는지" 를 재는 유일한 자다.

### 카드가 예고했으나 착지하지 않은 가드 2건 (정보용)

| 카드 | 상태 | 대체 커버 |
|---|---|---|
| **G-2A-4** — 4 호출부 `trade_type` 리터럴 구조 가드 | ❌ 미착지(`grep TradeType.BUY tests/unit/ast/` = 0건) | 행위 그물이 덮는다 — MT-F 7건 · MT-G 3건 |
| `test_g328_1` 을 **4 호출부 전수**로 확대 | ❌ 미확대(여전히 `execute_sell` 2곳만) | 매수 축은 `test_cycle276_ast_order_hook::test_c1_9`(재조준)가 「훅~코어 호출 사이 `await` 0」을 덮는다. 매핑↔훅은 `test_c1_6` |

둘 다 **되돌릴 사유가 아니다**(다른 가드가 같은 축을 덮는다). 다만 카드와 착지분이
어긋나 있으므로 다음 사람이 카드를 읽고 가드가 있다고 믿지 않도록 여기 남긴다.

---

## 9. 착지한 신규·재조준 가드 (실측 목록)

`tests/unit/ast/test_cycle328_sell_pending_helper.py` — 9 케이스.

| 케이스 | 내용 | 카드 대응 |
|---|---|---|
| `test_g328_0c` **(재작성)** | `execute_buy` 가 **코어 2회** · 래퍼가 코어 **1회** · `execute_sell` 이 코어 **직접 0회** | G-2A-1 + **G-2A-2** |
| `test_g328_0d` **(신규)** | 코어에 `ast.Try` **0건** | **G-2A-3** |
| `test_g328_2` (재조준) | **코어**의 `_completed_orders` 판정보다 앞에 `await` 0건 | 양보점 |
| `test_g328_4` (재조준) | **코어**의 수식어 표 조회가 `[...]` 아닌 `.get()` | G-2A-5 |
| `test_g328_0a/0b/1/3/3b` | 무변경(래퍼 축) | — |

🔴 **`test_g328_0c` 의 docstring 이 1단계 카드의 「반드시 뒤집히거나 삭제된다」를 정확히
인계받아 재작성돼 있다** — 관문이 지적했던 "무심코 지우면 매수 승격을 아무도 안 본다"가
닫혔다. `test_g328_0d`(`execute_sell` 코어 직접 호출 0)가 이 단계에서 가장 중요한 신규 가드라는
카드 판단에 동의한다 — 그것이 깨지면 cycle327 ⓑ 경계가 **무증상으로** 사라진다.

---

## 10. 남기는 관찰 (판정의 근거가 아님)

- **매수 폴백 + `KisApiError` 오귀인 사슬이 실측된다**(§1-b). 접수 성공한 주문에
  `block_low_funds` cooldown 이 걸리고 `pending_buy_amounts` 가 사라져 예산 이중 사용 창이 열린다.
  HEAD 와 동치라 이 단계의 사유는 아니지만, **2B 의 명세가 되어야 할 실측**이다.
- 설계 카드 본문의 기준 sha 는 착수 전 값(`e1beeb1f…`)이다. 착지 후 값(`1aa8d1b6…`)을
  카드에 병기해 두면 다음 사람이 재핀 대조에 쓸 수 있다.

---

## 판정

1~6번(격리 2판본 36축 diff = **35축 byte 동일 + 의도된 1축**) · 7번(요구 회귀 전량 초록,
광역 2건은 HEAD 동치 선재, 코어 미커버 0) 을 근거로 판정한다.

8번의 MT-B·MT-D 는 **그물의 빈 곳**이지 이 판본의 결함이 아니며(현 코드는 두 자리 모두
올바르다), 둘 다 **관측 전용**이라 이 단계를 되돌릴 사유가 아니다. 다만 MT-B 는 이 추출이
**새로 만든** 단일 실패점이므로 tdd-engineer 의뢰 1건으로 닫기를 권고한다.

행위 보존: 확인
