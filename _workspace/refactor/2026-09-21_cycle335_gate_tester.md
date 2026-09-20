# cycle335 관문 — tester (매수 축 「접수 후 경계」)

> 대상 = `src/engine/order_engine.py` — 신규 `_persist_buy_pending_after_send` +
> `execute_buy` 호출부 2곳 승격.
> 자문 = [`_workspace/domain_consult/cycle335_buy_post_send_boundary.md`](../domain_consult/cycle335_buy_post_send_boundary.md)
> 직전 사이클 관문(방법 재사용) = [`2026-09-21_step2_gate_tester.md`](2026-09-21_step2_gate_tester.md)

## 측정 환경 — 공유 워크트리 `src/`·`tests/` 는 한 글자도 쓰지 않았다

| 스냅샷 | 구성 | `order_engine.py` sha |
|---|---|---|
| `head` | `git archive HEAD`(cycle334 `a3f4841`) | `1aa8d1b6c93eae6d` |
| `work` | 위 + 워크트리 수정분 전부 — **돌연변이 전용** | `fe9886c8e2e3cccd` |
| `workcap` | 위와 같은 내용 — **캡처/부가 돌연변이 전용**(돌연변이 배치와 격리) | `fe9886c8e2e3cccd` |

돌연변이는 매 회차 pristine 사본에서 다시 만들고 앵커 유일성(`count(old)==1`)으로
"내 변경만 들어갔다" 를 강제했다. 모든 실행 전후로 공유 워크트리 sha 를 재확인했고
`order_engine.py` = `fe9886c8e2e3cccd` · `scheduler.py` = `4b9c8ac94706ae62` 로 불변이었다
(`git status --porcelain` 22행, 착수 시점과 동일).

자산 = `<scratchpad>/c335/{head,work,workcap}` · `cap_{HEAD,WORK}.json` ·
`yield_{HEAD,WORK}.json` · `mutate.py` · `run_mt.py` · `run_mt2.py` ·
`order_engine_WORK_pristine.py` · `scheduler_pristine.py`

---

## 1. 행위 보존 — **확인**. 성공 경로는 AST·런타임·로그가 전부 동일하다

### 1-a. 모듈 전수 AST — 바뀐 것은 정확히 3가지뿐

| 축 | HEAD | WORK |
|---|---|---|
| 함수 개수 | 45 | 46 |
| 신규 | — | `_persist_buy_pending_after_send` **1개** |
| 코드가 다른 함수 | — | `_persist_pending_after_send`(**docstring 만**) · `execute_buy`(**2줄**) |

`execute_sell` · `_persist_sell_pending_after_send` · `_insert_pending_or_absorb_race` ·
`_handle_buy_fill` · `_handle_sell_fill` · `_cancel_after_wait` · `_cancel_and_reorder` 를
포함한 **나머지 44 함수는 AST unparse 가 byte 동일**하다.

`execute_buy` unparse 는 양쪽 **159줄**이고 diff 는 아래 2줄이 전부다.

```
-await self._persist_pending_after_send(trade_type=TradeType.BUY, ticker=…, path='market')
+await self._persist_buy_pending_after_send(ticker=…, path='market')
-await self._persist_pending_after_send(trade_type=TradeType.BUY, ticker=…, path='fallback')
+await self._persist_buy_pending_after_send(ticker=…, path='fallback')
```

핸들러 체인도 동일하다 — `execute_buy` 안 `ast.Try` **8개**, 타입·순서 전부 일치
(`[KisApiError] … [KisApiError, Exception] … [KisApiError] … [Exception]`). 폴백이 바깥
`try` 에 안 걸리는 구조도 그대로 보존됐다.

### 1-b. 코어 직접 호출 전수 (모듈 전체, `execute_*` 한정이 아님)

```
L1093 _persist_pending_after_send      <- _persist_buy_pending_after_send
L1134 _persist_pending_after_send      <- _persist_sell_pending_after_send
L1456 _persist_buy_pending_after_send  <- execute_buy
L1559 _persist_buy_pending_after_send  <- execute_buy
L1811 _persist_sell_pending_after_send <- execute_sell
L2139 _persist_sell_pending_after_send <- execute_sell
```

`src/engine/CLAUDE.md` 의 「코어 직접 호출은 그 두 래퍼뿐」 주장이 **모듈 전수로도 참**이다.

### 1-c. 런타임 37축 — 22축 동일 / 15축 상이, 상이한 15축이 전부 «매수 접수 후 실패»

축 = `raised` · `place_order` 횟수 · `pending_buys` · `pending_buy_amounts` · 매핑 6종 ·
`cached_buyable_at==0` · `is_ticker_blocked_for_buy` · `is_low_funds_blocked` ·
`is_buy_blocked` · `_selling` · `positions` · `_completed_orders` · `db_rows` ·
**로그 전문(레벨+메시지)**.

| 코호트 | 축 수 | HEAD↔WORK |
|---|---|---|
| 성공/race 흡수 (매수 주·폴백 × race 유무) | 4 | **전부 동일 — 로그 전문까지 byte 동일** |
| 매도 접수 후 실패 (8 예외타입 × 주·폴백) | 16 | **전부 동일** |
| 매수 접수 후 실패 — `BaseException`(KeyboardInterrupt) | 2 | **동일**(`raised=KeyboardInterrupt`) |
| 매수 접수 후 실패 — Exception 7종 × 주·폴백 + 증거없는 UNIQUE | 15 | **의도된 상이** |

🔴 **`BaseException` 축이 동일하다는 것이 중요하다** — `except Exception` 이 `CancelledError`·
`KeyboardInterrupt` 계열을 삼키지 않는다는 실측이다(삼켰다면 task 취소가 무음이 된다).

### 1-d. 양보점 — 최초 suspension 은 여전히 `await insert_trade` 다

`place_order` 반환 직전에 `asyncio.create_task` 마커를 걸고 `insert_trade` 진입 시점에
그 마커가 돌았는지 본다. **양성 대조군**(`await asyncio.sleep(0)` 삽입)을 함께 쟀다.

| | measure | 양성 대조군 |
|---|---|---|
| HEAD 매수 주 / 폴백 | **False** | **True** |
| WORK 매수 주 / 폴백 | **False** | **True** |

래퍼가 한 프레임 늘었지만 그 앞에 `await` 가 0건이라 「주문번호 매핑은 `place_order`
응답 직후 동기 영역」 금기의 전제가 유지된다.

### 1-e. 커버리지 — 코어·두 래퍼 미커버 0줄 · 부분분기 0

`_persist_pending_after_send` = `:1005-1048` · `_persist_buy_pending_after_send` = `:1050-1107` ·
`_persist_sell_pending_after_send` = `:1109-1144`. Missing 목록의 인접값은 `981-982` 와
`1163-1164` 이고 **`1005-1144` 구간이 Missing 에도 부분분기에도 한 줄 없다**(신규 래퍼의
`except` 분기 포함).

---

## 2. 경계가 실제로 닫히는가 — **닫힌다**. 그리고 폴백의 오귀인 사슬이 실제로 끊겼다

`insert_trade` 를 8 예외타입으로 터뜨린 매수 2경로 런타임 실측.

| 축 | HEAD | WORK |
|---|---|---|
| 주 경로 · Exception 7종 | `raised=<그 타입>` · `pending_buys=[]` · `pending_buy_amounts={}` · `blocked_for_buy=False` · `cache0=False` | **`raised=None`** · `pending_buys=['004990']` · `{'004990': 25000000}` · `blocked_for_buy=True` · `cache0=True` |
| 폴백 · non-`KisApiError` | `raised=<그 타입>`(=`execute_buy` 관통) · `cache0=False` | **`raised=None`** · pending 유지 · `cache0=True` |
| 폴백 · `KisApiError` | `raised=None` · pending 해제 · **`low_funds_blocked=True`** | `raised=None` · **pending 유지** · **`low_funds_blocked=False`** |
| 매핑 6종 | 양쪽 전부 유지 | 동일 |
| `place_order` 횟수 | 주 1 / 폴백 2 | **동일**(재발사 0) |

🔴 **폴백 + `KisApiError` 축이 cycle334 관문 §10 이 예고한 그 사슬이다.** HEAD 는
`place_order` **2회 접수 성공**인데 장부에 이렇게 적었다:

```
HEAD [ERROR] 지정가 폴백도 거부 → cooldown: 테스트종목(004990) ([APBK1943] … → [EGW00201] …)
```

접수된 주문을 「거부」로 적고 900초 cooldown 을 걸고 예산까지 풀었다 — 운영자가 로그만
보면 **주문이 안 나갔다고 믿는다**. WORK 는 같은 자리에서:

```
WORK [ERROR] [buy_post_send_error] ticker=004990 order_no=BUY-000001 strategy=momentum
             path=fallback qty=1250 price=20250 — 주문은 접수됐다. pending 을 풀지 않고 …
WORK [WARNING] 시장가 거부 → 지정가 5호가 폴백: 테스트종목(004990) @ 20250 (원인 [APBK1943] …)
```

마커 렌더도 확인했다 — 주 경로 `path=market qty=1250 price=20000` / 폴백
`path=fallback qty=1250 price=20250`. 레벨은 양쪽 **ERROR** 이고 정상 skip 경로에서는 0행이다.

---

## 3. 매도 축 무접촉 — **보존됨**

- AST: `execute_sell` · `_persist_sell_pending_after_send` **byte 동일**(§1-a).
- 런타임 **16축 전부 동일**(8 예외타입 × 주·폴백): `raised=None` · `place_order` 주 1 / 폴백 2
  (**재발사 0 · 폴백 관통 0**) · `_selling=['004990']` 유지 · `positions` 유지 ·
  `[sell_post_send_error]` 4필드·꼬리 문구 byte 동일.
- 구조 가드 `test_g328_3`/`3b` 가 `[sell]`/`[buy]` 두 축 parametrize 로 늘었고 매도 쪽 단언은
  내용이 같다(문구만 축 이름이 들어갔다).

cycle327 ⓑ 계약 3종(재발사 0 · 폴백 관통 0 · `_selling`·positions 유지) 전부 유지 확인.

---

## 4. 🔴 그물 구멍 — **내가 고안한 15종 중 7종이 빠져나간다**

판정 기준 = `work` 스냅샷 베이스라인(`tests/unit/engine` + `tests/unit/ast` +
`tests/integration` = **16 failed / 8480 passed**, 16 은 전부 `.git` 부재 구조 실패).
🔴 **sha 핀 7건은 어떤 돌연변이에도 붉으므로 판별기에서 제외**했다(`test_cycle274 c15_1` ·
`test_cycle276 c6_4c` · `test_cycle278` · `test_cycle282 h3` · `test_cycle290 g290_1` ·
`test_cycle294 a1b` · `test_cycle297 g2_9a`).

| # | 돌연변이 | 실질 검출 | 판정 |
|---|---|---|---|
| **MT-T2** | 마커 인자 `quantity` ↔ `record_price` **맞바꿈** | 🔴 **0** | 그물 구멍 (신규) |
| **MT-T8** | 마커 인자 `ticker` ↔ `order_no` **맞바꿈** | 🔴 **0** | 그물 구멍 (신규) |
| **MT-T1** | 래퍼→코어 `path=path` → `path="market"` 고정 | 🔴 **0** | 그물 구멍 (cycle334 MT-B 의 매수 절반) |
| **MT-T6** | `logger.exception` → `logger.error`(traceback 소실) | 🟠 **0** | 그물 구멍 (신규) |
| **MT-T5** | 래퍼 본문 맨 앞에 `await asyncio.sleep(0)` 삽입 | 🟠 **0** | 그물 구멍 (cycle334 부터 두 축 공통) |
| **MT-T11** | `execute_buy` 의 outer `except Exception:` 정리 블록 **통째 제거** | 🟠 **0** | 선재 |
| **MT-T12** | 그 블록에서 `pending_buy_amounts.pop` 만 제거 | 🟠 **0** | 선재 |
| MT-T4 | 래퍼 `trade_type=BUY` → `SELL` | ✅ 14 | |
| MT-T3 | 코어 호출 `record_price` ↔ `quantity` 맞바꿈 | ✅ 8 | |
| MT-T9 | 마커 제거(경계는 유지) | ✅ 5 | |
| MT-T13 | `except KisApiError` 발사 실패 정리 제거 | ✅ 2 | |
| MT-T7 | 폴백 **호출부** `path="fallback"` → `"market"` | ✅ 1 | |
| MT-T10 | 마커 `path` 인자를 `"market"` 리터럴로 고정 | ✅ 1 | |
| MS-1 | 스케줄러 `buy_succeeded` 술어에서 `pending_buys` 제거 | ✅ 2 | |
| MS-2 | 술어는 살아 있고 **HIGH 구독 게이팅만** 무력화 | ✅ 2 | |

(참고 — team-lead 의 MT-2 를 독립 재현했다: 매수 래퍼 `except Exception` →
`except UniqueViolationError` 는 **행위 8건 + 구조 2건**(`test_g328_3[buy]`·`3b[buy]`)이 붉고
`test_8`(UniqueViolation 케이스)·`test_7`·`test_9`·코어 층 2건은 **초록**이다. 정본 문서의
「14건 중 `UniqueViolationError` 케이스가 통과」 서술이 정확하다.)

### 🔴 G1 — 마커 **필드 값**이 presence-only 다 (MT-T2 · MT-T8)

`test_6` 은 `ticker=`·`order_no=`·`qty=`·`price=` 의 **존재**만 보고, 값을 보는 것은
`strategy=momentum` 과 `path=<경로>` 뿐이다(`"qty=0" not in msg` 는 0 만 거른다).

실측 렌더: 정상 `qty=1250 price=20000` → 맞바꿈 `qty=20000 price=1250`. **둘 다 0이 아니고
둘 다 그럴듯하다.** `ticker` ↔ `order_no` 맞바꿈도 `ticker=BUY-000001 order_no=004990` 로
조용히 통과한다. 회귀 14 + 17 + 11 케이스가 **전부 초록**이다.

**왜 이것이 이 사이클에서 특히 무거운가** — 자문 §Q2 가 이 두 필드를 도입한 근거가
「매수는 포지션도 장부도 없어 이 줄이 규모를 아는 **유일한 채널**」이고, 판독 절차가
「건별로 KIS 주문내역과 **대조**한다」이다. `ticker`/`order_no` 는 그 대조의 **키**이고
`qty`/`price` 는 대조 **대상**이다. 넷 중 어느 쌍이 뒤집혀도 운영자는 D+1 에 엉뚱한 주문을
찾거나 엉뚱한 수량을 맞다고 판정한다.

**그리고 매도 축은 이미 이 교훈을 겪었다.** `test_order_engine_sell_fallback.py` 시나리오 J
(3건)의 주석이 그대로다 — *"관문 리뷰(2026-09-20)에서 tester·tdd-engineer 가 독립적으로 같은
구멍을 찾았다 … 실측된 돌연변이 3종이 전부 행위 테스트 0건으로 통과했다 … 값이 이름 있는
인자 네 개로 헬퍼에 넘어가면서 실수로 뒤바꾸기가 쉬워졌으므로 그 단계의 산출물로 닫는다."*
매수 축은 **코어 호출 값**(MT-T3, 8건 검출 ✅)은 `test_order_engine_buy.py` 가 이미 닫았는데,
이번에 새로 생긴 **마커 렌더 값**은 안 닫혔다.

→ **tdd-engineer 의뢰 (1건, 한 줄)**: `test_6` 에 값 단언을 더한다.
```python
assert f"ticker={TICKER}" in msg and "order_no=BUY-000001" in msg, msg
assert f"qty={expected_qty} price={expected_price}" in msg, msg
```
판별력의 전제는 이미 성립한다 — `qty=1250` · `price=20000`(주) / `20250`(폴백) ·
`ticker=004990` · `order_no=BUY-000001` 이 서로 전부 다르다.

### 🔴 G2 — 매수 축 `path` 전달 한 줄이 여전히 무방비 (MT-T1)

cycle334 관문이 MT-B 로 올린 그 자리다. 그 뒤 **매도 축만 닫혔다** —
`test_cycle327_sell_fill_during_insert.py:308-354` 가 `[sell_fill_during_insert] path=fallback`
을 단언한다(docstring 에 "cycle334 MT-B" 라고 적혀 있다). **매수 축은 0건**이다:
`test_cycle271` 전체에 `path` 문자열이 4회 나오는데 전부 테스트 **이름**이고 단언이 아니다.
`_PENDING_SKIP_PREFIX` 가 만드는 매수 skip 수식어(`"매수 "`/`"폴백 "`)를 단언하는 테스트도
리포 전체에 없다.

cycle335 가 이 구멍을 만들지는 않았지만 **한 겹 더 깊게 밀어 넣었다** — `path` 는 이제
호출부 → 래퍼 → 코어 → 흡수기 3홉을 지나고, 끝의 두 홉(마커 렌더 = MT-T10 ✅ / 호출부 =
MT-T7 ✅)은 막혔는데 **가운데 홉만 뚫려 있다**. 피해는 관측 한정(`[buy_fill_during_insert]
path=` 와 skip WARNING 수식어가 폴백에서 거짓이 된다)이라 **되돌릴 사유는 아니다**.

→ **tdd-engineer 의뢰 (1건)**: `test_cycle271::test_c5_2`(폴백 흡수 마커)에
`assert "path=fallback" in hits[0]` 한 줄 — 매도 쪽 형제 테스트와 같은 모양.

### 🟠 G3 — `logger.exception` → `logger.error` 가 무검출 (MT-T6)

레벨(ERROR)도 메시지도 같고 **traceback 만 사라진다**. 자문 §Q5 의 롤백 규칙이
「하루 5건 이상이면 이 시정의 결함이 아니라 **RDS 가 아픈 것**」인데, 그 판정에는 예외의
정체(타임아웃인가 / UNIQUE 인가 / 풀 고갈인가)가 필요하고 유일한 전달 수단이 `exc_info` 다.

→ 의뢰: `test_6` 에 `assert rec.exc_info is not None` 한 줄(매도 축에도 같은 구멍이 있다).

### 🟠 G4 — 「래퍼 본문 앞에 `await` 를 넣지 않는다」가 docstring 에만 있다 (MT-T5)

두 래퍼의 docstring이 명시적으로 금하는데 강제하는 가드가 없다. cycle334 가
`test_g328_2` 를 **코어**로 재조준하면서 래퍼 축이 비었고, `test_g328_1`(매도 매핑↔호출) ·
`test_c1_9`(매수 훅↔호출)는 둘 다 `execute_*` **바깥쪽**만 본다.

⚠️ **실제 위험도는 낮다** — 매핑 6종은 래퍼 호출 **전**에 이미 등록되므로 그 `await` 가
「매핑은 동기 영역」 금기를 실제로 깨지는 않고, 그 창에 착지한 체결통보는 코어의
`_completed_orders` 판정이 정상 흡수한다. 다만 **금기를 적어 놓고 아무도 안 보는 상태**라
다음 사람이 그 줄을 믿는다.

→ 의뢰(선택): `test_g328_2` 를 래퍼 2축으로 확대 —「래퍼 본문의 `await` 는 코어 호출
하나뿐」.

### 🟠 G5 — 발사 실패 정리의 **generic 분기**가 무검출 (MT-T11 · MT-T12, 선재)

`except KisApiError` 쪽 정리는 막혀 있다(MT-T13 → `test_order_engine_buy.py` 2건 검출 ✅).
그런데 **outer `except Exception:`** 의 `pending_buys.discard` + `pending_buy_amounts.pop` 은
통째로 지워도, 둘 중 하나만 지워도 **0건**이다.

이 구멍은 cycle335 가 만들지 않았지만 **이번 주석이 정확히 그 블록을 가리킨다** —
*"래퍼가 예외를 닫으므로 아래 `except` 두 개는 **발사 실패에만** 닿는다"*. 다음 사람이 그
문장을 읽고 "그럼 이건 이제 뭘 하지?" 하며 손대면 진짜 발사 실패(=`place_order` 가
non-`KisApiError` 로 실패)에서 그 종목이 하루 종일 `is_ticker_blocked_for_buy` 에 걸리고
예산을 점유한다. 되돌릴 사유는 아니다(현행 코드는 옳다).

→ 의뢰(낮은 우선순위): `place_order` 가 generic `Exception` 으로 실패할 때
`pending_buys`/`pending_buy_amounts` 가 **풀린다**는 회귀 1건.

---

## 5. 자문 §3 회귀 1~13 — 항목별 대조

| # | 계약 | 착지 | 판정 |
|---|---|---|---|
| 1 | 임의 `Exception` → 정상 종료 + pending 유지 | `test_1` | ✅ (내 캡처 7타입 × 2경로로 교차 확인) |
| 2 | `cached_buyable_at==0.0` + 접수 INFO 1행 | `test_2` | ✅ |
| 3 | 매핑 6종 전부 유지 | `test_3` | ✅ |
| 4 | 폴백 non-`KisApiError` → 정상 return + pending + cache0 + 폴백 WARNING | `test_4` | ✅ |
| 5 | `block_low_funds` 미등록 | `test_5` | ✅ (실측: HEAD `True` → WORK `False`) |
| 6 | 마커 ERROR 1행 + 6필드, `path` 경로별 | `test_6`(param 2) | ⚠️ **부분** — 필드 **존재**와 `strategy`·`path` **값**만. `ticker`/`order_no`/`qty`/`price` 값은 무방비(**G1**) |
| 7 | 정상 skip 경로는 마커 0행 | `test_7` | ✅ |
| 8 | 증거 없는 UNIQUE → 마커 1행 + race 마커 0행 | `test_8` + `test_c7_1` | ✅ |
| 9 | 성공 경로 무회귀 | `test_9` | ✅ (+ 내 HAPPY 4축 **로그 전문까지 byte 동일**) |
| 10 | swing poll `buy_succeeded==True` → HIGH 구독 | `test_10` **+ `test_swing_poll_loop.py` 3건** | ✅ **아래 상술** |
| 11 | 래퍼 구조: 최상위 `try` 1 · 핸들러 1 · `Exception` · 본문 앞 `await` 는 코어 호출 하나뿐 | `test_g328_3b[buy]` + `test_core_has_no_try_and_buy_wrapper_has_exactly_one` | ⚠️ **부분** — `try`/핸들러/타입은 ✅, **`await` 절은 미착지**(**G4**) |
| 12 | `execute_buy` 안 코어 직접 호출 0건 | `test_g328_0c` | ✅ (모듈 전수 실측으로 교차 확인) |
| 13 | 코어에 `try` 0개 | `test_g328_0d` + `test_core_has_no_try…` | ✅ |

### 10번 — 거울이 낡지 않게 막는 장치는 **충분하다**

team-lead 가 걱정한 지점을 돌연변이로 갈랐다.

| 돌연변이 | 붉어지는 것 |
|---|---|
| **MS-1** 스케줄러 술어에서 `t in strategy.state.pending_buys` 제거 | `test_10`(거울) **AND** `test_swing_poll_loop::test_swing_poll_subscribes_ticker_after_buy_signal` |
| **MS-2** 술어 텍스트는 그대로 두고 `if buy_succeeded:` → `if True:` (게이팅만 무력화) | `test_swing_poll_subscribe_skipped_when_buy_raises` + `…_when_buy_rejected_no_pending` |

즉 그물이 두 겹이다 — **거울은 술어의 존재**를, `test_swing_poll_loop.py` Case 8/10/11 은
**술어 → HIGH 구독(`bypass_limit=True`) 링크**를 각각 덮는다. 거울의 두 앵커
(`"buy_succeeded = ("` · `"in strategy.state.pending_buys"`)는 `scheduler.py` 에서 각각
**정확히 1회** 출현하므로 공허 통과도 없다.

⚠️ 남는 것은 **재배치 취약성** 하나다 — `scheduler.py` 라인 상한(<3,900L) 때문에 이 폴 루프가
언젠가 leaf 로 빠지면 거울이 `scheduler.py` 에서 앵커를 못 찾아 **붉어진다**. 그것은 결함이
아니라 재조준을 강제하는 **올바른 실패**다(「가드는 고치면 초록이 되어야 한다」에 부합).
다만 그때 `_PERSIST_ENTRYPOINTS` 처럼 **경로 계보 상수**로 바꾸는 것이 자연스럽다.

---

## 6. 회귀 실행 (전부 실 워크트리, sha `fe9886c8e2e3cccd` 불변)

| 범위 | 결과 |
|---|---|
| 매수 축 9파일 | **209 passed** |
| 매도 축 9파일 | **110 passed** |
| AST 가드 전체 | **1808 passed · 4 skipped · 26 xfailed** (cycle334 관문 1806 → **+2** = `test_g328_3`/`3b` 의 `[buy]` 파라미터) |
| `tests/unit/engine` + `tests/integration` + `tests/unit/db` | 1 failed · **7501 passed** · 6 skipped · 281 xfailed · 12 xpassed |
| **백엔드 전체** | **11170 passed · 12 skipped · 328 xfailed · 13 xpassed** (343.9s) |

- 광역의 1건 = `tests/unit/db/test_cycle64_price_filter_scanner_system_config.py::test_A1_…` —
  **단독 실행하면 4 passed**. cycle334 관문이 이미 「순서 의존 선재 결함」으로 기록한 그것이고
  백엔드 전체 실행에서는 나타나지 않는다.
- **백엔드 전체 수치가 team-lead 측정과 완전히 일치**한다.

케이스 수도 정본 문서와 맞다 — cycle335 **14** · cycle271 **17** · cycle328 **11** · cycle327 **6**.

sha 재핀 10파일 전부 신규 값
`fe9886c8e2e3cccd03370f3470cc73449bf3a7c615c177c8ea87bd399949a8b2` 로 일치하고 구 sha
`1aa8d1b6…` 는 `src/`·`tests/` 에 **0건**(직전 관문 문서에만 기준값으로 남아 있다).

---

## 7. 남기는 관찰 (판정 근거 아님)

- **문서 정확도 확인** — `src/engine/CLAUDE.md` 의 신설 절이 주장하는 4가지(코어 직접 호출 =
  두 래퍼뿐 · 좁히면 매수는 `UniqueViolationError` 케이스가 통과 · 가드 11 / 회귀 14·17·6 ·
  마커 2종의 필드 구성)를 전부 독립 실측했고 **일치**한다.
- **`[buy_post_send_error]` 는 무cap 이라 `system_logs` 에 건별로 남는다.** 21:30
  `top_patterns` 는 메시지 전문이 키이므로 이 마커는 `ticker`/`order_no`/`qty`/`price` 가
  전부 달라 **패턴이 건마다 갈린다** — `top_patterns` 상위권에는 안 오르고 건수 집계로만
  보인다. 자문이 의도한 "건별 조사 목록" 과 정합하지만, 운영자가 리포트 상단만 보면 못
  본다. D+1 판독은 `system_logs` 직접 조회가 유일 채널임을 워크리스트에 적어 두면 좋겠다.
- 직전 관문이 낸 의뢰 2건 중 **매도 축 `path=` 는 닫혔고 매수 축은 안 닫혔다**(G2). 다음
  의뢰를 낼 때 「두 축」이라고 명시하는 편이 낫겠다.

---

## 판정

**행위 보존: 확인**

근거 = §1(모듈 전수 AST 에서 바뀐 것이 신규 함수 1 + 호출부 2줄 + docstring 1 뿐 ·
런타임 37축 중 성공·race 4축과 매도 16축과 `BaseException` 2축이 **로그 전문까지 byte 동일** ·
양보점 양성 대조군 포함 불변 · 코어/래퍼 미커버 0) · §2(경계가 8 예외타입 × 2경로에서
전부 닫히고 폴백 `KisApiError` 오귀인 사슬이 실제로 끊겼다) · §3(매도 축 byte 동일) ·
§6(요구 회귀 전량 초록, 광역 1건은 선재·단독 초록, 백엔드 전체가 team-lead 측정과 일치).

§4 의 **G1~G5 는 그물의 빈 곳이지 이 판본의 결함이 아니다** — 현 코드는 다섯 자리 모두
올바르고, 다섯 돌연변이의 피해는 전부 **관측 축**(G1·G2·G3)이거나 **규약 문서화 축**(G4)
이거나 **선재**(G5)다. **되돌릴 사유가 아니다.**

다만 **G1 은 이 사이클이 새로 만든 단일 실패점**이고, 매도 축이 cycle328 에서 겪은 것과
**같은 계열**이며, 닫는 비용이 `test_6` 두 줄이다. 07:45 창 안에 함께 넣기를 권고한다
(코드 무접촉 = 배포 모드 판정 불변). G2 는 같이 넣으면 한 줄 더다. G3~G5 는 다음 사이클로
미뤄도 된다.
