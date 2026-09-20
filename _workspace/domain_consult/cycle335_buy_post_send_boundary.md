# cycle335 자문 요청 — 매수 축 「접수 후 경계」 부재 (워크리스트 2B)

작성 = 메인 세션 · 2026-09-21 02:0x KST · 자율 구간(사용자 지시 = 07:00까지, 승인은 권고대로)

## 0. 이 자문이 필요한 이유

cycle334(직전 사이클, 배포 완료 `a3f4841`)가 접수 후 PENDING 영속화를 4곳 → 1코어로 모으면서,
**매수 축에는 접수 후 경계가 없다**는 사실을 코드 주석과 문서에 「결함」으로 명시하고 분리했다.
그 시정이 이 사이클이다. `src/engine/order_engine.py` = **8영역**이고 매수 실패 경로의
자금 회계·재매수 가능 여부를 바꾸므로 **도메인 자문 선행**이 규약이다.

---

## 1. 현행 코드 (실측, `src/engine/order_engine.py`)

### 1.1 매수 주 경로

```
1312  try:
1317      place_kwargs = dict(ticker=…, side=BUY, quantity=…, price=order_price, exchange=…)
1324      if order_division != MARKET: place_kwargs["order_division"] = order_division
1326      result = await place_order(**place_kwargs)          # ← 여기부터 주문은 거래소에 있다
1334      self._order_qty[result.order_no] = quantity          ┐
1335      self._order_strategy[...] = strategy.strategy_id     │ 매핑 6종 동기 등록
1336      self._order_ticker[...] = ticker                     │ (await 0 — 금기의 전제)
1343      self._order_exchange[...] = buy_exchange             │
1348      self._order_division[...] = _sent_division.value     │
1349      self._pending_buy_orders[result.order_no] = {...}    ┘
1361      try: llm_buy_gate.observe_order(...)                 # 이미 자체 try
1390      except Exception: logger.debug(...)
1397      await self._persist_pending_after_send(              # ← cycle334 코어 (전파한다)
              trade_type=BUY, …, path="market")
1407      logger.info("매수 주문 접수: …")
1410      state.cached_buyable_at = 0.0
1412  except KisApiError as e:
1413      state.pending_buys.discard(ticker)                   # ← 발사 실패의 정리
1414      state.pending_buy_amounts.pop(ticker, None)
          … 잔고부족 / 시장가거부 폴백 / …
1523      raise
1524  except Exception:
1525      state.pending_buys.discard(ticker)                   # ← 발사 실패의 정리
1526      state.pending_buy_amounts.pop(ticker, None)
1527      raise                                                # ← risk.on_tick 으로 전파
```

### 1.2 매수 폴백 경로 (시장가 거부 → 지정가 5호가 1회)

```
1429  if is_market_order_disallowed(e) or (order_division is NXT_GTP_LIMIT):
1440      try:
1441          state.pending_buys.add(ticker)                   # 폴백 진입 — 재등록
1443          state.pending_buy_amounts[ticker] = fallback_price * quantity
1444          result = await place_order(…, price=fallback_price, order_division=LIMIT)
1455          … 매핑 6종 동기 등록 …
1473          try: llm_buy_gate.observe_order(…)
1498          await self._persist_pending_after_send(trade_type=BUY, …, path="fallback")
1508          logger.warning("시장가 거부 → 지정가 5호가 폴백: …")
1512          state.cached_buyable_at = 0.0
1513          return
1514      except KisApiError as e2:                            # ← 핸들러가 이것 하나뿐
1515          state.pending_buys.discard(ticker)
1516          state.pending_buy_amounts.pop(ticker, None)
1517          state.block_low_funds(ticker, time.time() + LOW_FUNDS_COOLDOWN)
1518          logger.error("지정가 폴백도 거부 → cooldown: …")
1522          return
```

### 1.3 매도 축은 cycle327·328 이 이미 닫아 뒀다 (대칭 참조)

`_persist_sell_pending_after_send(*, ticker, order_no, strategy_id, record_price,
quantity, path)` 가 코어를 부르고 **자기 자신의 `except Exception`** 으로 닫은 뒤
`logger.exception("[sell_post_send_error] ticker=… order_no=… strategy=… path=… —
주문은 접수됐다. 재발사하지 않고 체결통보·동기화에 맡긴다.")` 1행을 남기고 **정상 종료**한다.
구조 가드 `test_cycle328_sell_pending_helper.py::test_g328_3b` 가 「최상위 `try` 1개 · 핸들러 1개 ·
타입 `Exception`」 을 봉인한다(좁히면 접수 성공 주문을 「거부」로 장부에 적는 회귀가 전부 초록으로 통과한다).

---

## 2. 결함의 모양 — 무엇이 언제 깨지는가

`place_order` 가 성공하면 **그 주문은 이미 거래소에 있다.** 그 뒤의 어떤 예외도 「발사 실패」가
아닌데, 지금은 실패 정리 코드가 그대로 실행된다.

### 2.1 주 경로 (1397 `_persist_pending_after_send` 가 예외를 던지는 경우)

그 함수가 던질 수 있는 것 = `_insert_pending_or_absorb_race` 안 `await insert_trade` 의
DB 예외(타임아웃·RDS 페일오버·커넥션 풀 고갈) + 증거 없는 `UniqueViolationError`(코어가
`order_no in _completed_orders` 일 때만 흡수하고 그 밖은 **의도적으로 전파**한다).
KIS 호출은 없으므로 `KisApiError` 는 나지 않는다 → **`except Exception:`(1524)** 으로 간다.

| # | 결과 | 피해 |
|---|---|---|
| a | `pending_buys.discard(ticker)` | `registry.is_ticker_blocked_for_buy(ticker)` = **False** → 같은 종목을 다시 산다 |
| b | `pending_buy_amounts.pop(ticker)` | `StrategyBase._calc_used_funds()` 에서 그 주문의 예정 금액이 빠진다 → **예산 이중 사용**. ⚠️ 미체결 LIMIT 은 하루 종일 안 채워질 수 있다 — ms 창이 아니다 |
| c | `raise` | `risk.on_tick` 에 try 가 없다 → 그 틱의 **나머지 전략 청산 평가가 통째로 소멸** + WS 재연결(`realtime/handler.py` 규약) |
| d | `cached_buyable_at = 0.0` 미실행 | 가용액 캐시가 최대 60초 stale → 그 창에 가용액을 과대평가한 채 추가 매수 |

⚠️ `_pending_buy_orders[order_no]` 와 매핑 5종은 **남는다**(1334~1354 는 이미 실행됨). 그래서
체결통보가 오면 `_handle_buy_fill` 이 정상 귀속하고, `update_trade_status` affected=0 →
보정 INSERT 로 `trade_history` 도 결국 맞는다. **장부는 자기 치유되고 자금 회계만 깨진다** —
그래서 화면·DB 어느 쪽을 봐도 정상으로 보인다.

### 2.2 폴백 경로 (1498 이 예외를 던지는 경우)

핸들러가 `except KisApiError as e2` **하나뿐**이다. non-`KisApiError`(= DB 예외 전부)는
- 형제 핸들러 `except Exception:`(1524)이 **잡지 못한다**(파이썬: `except` 블록 안에서 난
  예외는 같은 `try` 의 다른 `except` 로 가지 않는다)
- → `execute_buy` 를 통째로 관통 → `risk.on_tick` 사망 (2.1-c 와 같은 피해)
- → 게다가 `pending_buys`/`pending_buy_amounts` 는 **1441~1443 에서 재등록된 채 남는다**
  → 예산 **과대**계상 + 그 종목 그날 재매수 차단(21:30 `_reset_daily_state` 까지)

즉 두 경로의 자금 오차 **방향이 반대**다(주 경로 = 과소계상/이중사용, 폴백 = 과대계상/봉쇄).

### 2.3 실측 빈도

`system_logs` 에 `[buy_post_send_error]` 에 해당하는 마커가 **아직 없다**(이 사이클이 만든다).
매도 축의 같은 계열은 cycle327 이 실측 3회 발사를 확인했다. 매수 축의 과거 발생 빈도는
**측정 채널이 없어 미상**이고, 그 사실 자체가 이 사이클이 마커를 만드는 이유다.

---

## 3. 메인 세션의 제안 (자문이 검증·반박할 대상)

매도와 **완전 대칭**으로 경계 래퍼를 호출자 층에 세운다. cycle334 가 정한 설계
(「코어는 전파, 경계는 호출자 층」)를 매수 축에 그대로 적용하는 것이다.

```python
async def _persist_buy_pending_after_send(
    self, *, ticker, order_no, strategy_id, record_price, quantity, path,
) -> None:
    try:
        await self._persist_pending_after_send(
            trade_type=TradeType.BUY, ticker=ticker, order_no=order_no,
            strategy_id=strategy_id, record_price=record_price,
            quantity=quantity, path=path,
        )
    except Exception:
        logger.exception(
            "[buy_post_send_error] ticker=%s order_no=%s strategy=%s path=%s "
            "— 주문은 접수됐다. pending 을 풀지 않고 체결통보·동기화에 맡긴다.",
            ticker, order_no, strategy_id, path,
        )
```

호출부 2곳(`:1397` `path="market"` / `:1498` `path="fallback"`)을 이 래퍼로 바꾼다.
그 밖의 줄은 **한 글자도 건드리지 않는다**.

### 이렇게 하면

- 주 경로: 예외가 래퍼에서 멎는다 → `except Exception:`(1524) 미도달 → **a·b·c·d 전부 소멸**.
  `logger.info("매수 주문 접수")` 와 `cached_buyable_at = 0.0` 이 정상 실행된다.
- 폴백: 예외가 래퍼에서 멎는다 → `execute_buy` 관통 소멸. `pending_buys` 는 1441~1443 의
  재등록 상태 그대로 **유지**된다(주문이 실제로 나갔으므로 유지가 옳다는 것이 제안의 전제다).
- 성공 경로는 byte 동일.

---

## 4. 자문에 묻는 것

### Q1. 🔴 `pending_buys` 유지가 옳은가 — 이것이 이 사이클의 핵심 결정이다

제안은 "주문이 나갔으므로 `pending_buys`/`pending_buy_amounts` 를 **유지**한다" 이다.
유지의 귀결:

- 그 종목은 `is_ticker_blocked_for_buy` 로 **그날 재매수가 막힌다**
- 그 금액은 `_calc_used_funds` 에 계속 잡혀 **예산을 점유한다**
- 체결되면 `_handle_buy_fill` 이 `pending_buys.discard` + `pending_buy_amounts.pop` +
  `_pending_buy_orders.pop` 으로 정상 해제한다
- **미체결로 끝나면 21:30 `_reset_daily_state` 까지 점유가 남는다**
  (LIMIT 폴백 주문은 종일 안 채워질 수 있다)

질문 = 트레이더 관점에서 **접수 성공 + 장부 기록 실패** 상태의 올바른 자금 취급은 무엇인가?
(a) 제안대로 유지(보수적 — 예산을 이중으로 쓰지 않는다, 대신 미체결이면 그 예산이 종일 논다)
(b) 유지하되 별도 회수 경로를 둔다(예: 15분 `_sync_positions_from_balance` 가 KIS 주문내역에
    그 `order_no` 가 없으면 해제) — 복잡도 증가
(c) 다른 방향

### Q2. 마커 레벨과 이름

매도는 `logger.exception(...)` = **ERROR** + `[sell_post_send_error]`. 매수도 대칭으로
`[buy_post_send_error]` ERROR 를 제안한다. 21:30 `top_patterns` 는 WARNING 이상만 집계하므로
ERROR 면 리포트에 오른다. 이 선택이 맞는가? (빈도가 높을 수 있다면 cap 이 필요한가 —
매도 쪽은 무cap 이다)

### Q3. 경계의 시작점

제안은 경계를 `_persist_pending_after_send` **호출 한 문장**에만 건다. 대안은 매핑 등록
(`:1334~1354`)까지 포함하는 것이다. 매핑 등록은 dict 대입 6개라 실패 시나리오가 사실상 없고,
**실패하면 오히려 즉시 드러나야 하는** 성격(매핑 없이 체결통보가 오면 귀속이 깨진다)으로 본다.
매도 축도 매핑 등록은 경계 밖이다. 이 판단이 맞는가?

### Q4. `llm_buy_gate.observe_order` 훅의 자리

현재 훅은 `try/except Exception → logger.debug` 로 이미 닫혀 있고 경계 밖이다(코어 앞).
cycle276 이 「매핑 등록 **뒤** · PENDING INSERT **앞**」을 명세로 못 박았다. 무접촉이 맞는가?

### Q5. 이 시정이 **매매 행위**를 바꾸는가

성공 경로는 byte 동일이고 실패 경로만 바뀐다. 그런데 실패 경로의 변화는
「그 종목을 다시 사지 않게 된다」 + 「그 예산을 다시 쓰지 않게 된다」 + 「그 틱의 다른 종목
손절 평가가 살아난다」 이다. 이것은 **행위 보존이 아니라 행위 시정**이다.
승인 대상 분류(8영역 + 매매 행위 변경)가 맞는가? 롤백 다이얼이 필요한가,
아니면 cycle327·328 처럼 1커밋 revert 로 충분한가?

### Q6. 놓친 피해 경로

위 2.1/2.2 말고 더 있는가? 특히:
- `_pending_buy_orders[order_no]` 가 남고 `trade_history` PENDING 행이 **없는** 상태에서
  `scheduler._sync_orders_to_db`(15분)가 KIS 주문내역을 보고 INSERT 하는가? 중복이 나는가?
- 그 상태에서 `_cancel_after_wait`(부분체결 30초 잔량 취소 타이머)가 정상 동작하는가?
- 피라미딩(사다리 증량) 착수 시 이 경계 부재가 어떻게 증폭되는가?

---

## 5. 참고 정본

- 루트 `CLAUDE.md` 「주문이 나간 뒤의 실패로 재발사 금지 (cycle327)」 — 서술은 매도지만
  근거(주문은 이미 거래소에 있다)는 축과 무관하다
- `src/engine/CLAUDE.md` 「접수 후 PENDING 영속화 — 4경로 1코어 + 경계는 호출자 층 (cycle334)」
- `_workspace/refactor/2026-09-21_step2_card.md` §2B
- `_workspace/domain_consult/cycle329_mapping_absent_full_fill.md`(발사 창 계열 선행 자문)
- 가드 = `tests/unit/ast/test_cycle328_sell_pending_helper.py`(9케이스) ·
  `tests/unit/engine/test_cycle327_sell_fill_during_insert.py`(6케이스)

---

## 자문 답변 (domain-expert, 2026-09-21)

읽은 정본 = `src/engine/order_engine.py`(`execute_buy` 1086~1527 · 코어 1005~1047 · 매도 래퍼
1049~1084 · `_insert_pending_or_absorb_race` 870~908 · `_handle_buy_fill` 2434~2712 ·
`_cancel_after_wait` 2899~2953) · `src/engine/strategy_base.py:449~477` ·
`src/engine/strategy_registry.py:86~98` · `src/engine/risk.py:675~751` ·
`src/engine/scheduler.py:2300~2400, 2760~2795` · `src/engine/strategies/{donchian_swing,kojiro}.py` ·
`tests/unit/engine/test_cycle271_execute_buy_fill_during_insert.py`.

---

### Q1. `pending_buys` 유지가 옳은가 — **(a) 유지. 확신한다.**

#### 트레이더 시각 — 접수된 매수는 「예약된 자금」이 아니라 「이미 묶인 자금」이다

KIS 는 매수 주문을 접수하는 순간 그 금액을 주문가능금액에서 차감한다 — 우리가
`get_buyable` 로 읽는 바로 그 값이다. 즉 **브로커 장부는 이미 묶였다.** 이 상태에서
`pending_buy_amounts.pop(ticker)` 를 하는 것은 "자금이 풀렸다" 가 아니라
**"우리가 묶인 사실을 잊는다"** 다.

호가에 매수를 걸어둔 채 "아직 안 채워졌으니 그 돈은 내 돈" 이라고 생각하고 다른 종목을
사는 트레이더는 없다. 첫 주문이 체결되는 순간 미수가 난다. 우리 시스템이 미수까지 가지
않는 이유는 계좌 레벨 방어(`get_buyable`)가 따로 있기 때문인데 — **그게 정확히 함정이다.**
전략 예산(`순자산 × cash_usage_ratio × weight`)은 계좌 잔고보다 훨씬 작으므로 계좌 방어는
통과하고 **전략 예산 관문만 조용히 무력화된다**(`strategy_base.py:457-461` 의
`_calc_used_funds` 가 `pending_buy_amounts` 합을 그대로 읽는다).

#### 피해가 전략마다 다르다 — 요청서 §2.1 이 뭉갠 부분

| 피해 | 적용 범위 | 근거 |
|---|---|---|
| (a) 같은 종목 재매수 | **momentum · VB · LTV 3전략만** | donchian·kojiro·VCP·BFB 는 `_bought_today` 일일 래치가 `check_buy_signal` 에서 이미 도장돼 있다(`donchian_swing.py:1663` · `kojiro.py:944`). 그 4전략은 `pending_buys` 가 풀려도 그날 재진입이 막힌다 |
| (b) 예산 이중 사용 | **7전략 전부** | `_calc_used_funds` 는 전략 무관 관문 입력이다. 래치가 있는 전략도 **다른 종목**에 대해 예산이 과대 산정된다 |
| (c) `risk.on_tick` 사망 | **WS 틱 경로 5전략**(momentum·VB·LTV·BFB·VCP) | `risk.py:749` 는 try 가 없다. 그러나 donchian·kojiro 는 `scheduler.py:2776-2787` 폴 루프가 `except Exception: logger.exception("[swing_poll] execute_buy 실패")` 로 잡는다 — **그 둘은 on_tick 을 죽이지 않는다** |
| (d) `cached_buyable_at` stale | 7전략 전부 | 요청서는 "가용액 과대평가" 까지만 썼는데 **귀결이 더 무겁다** — 과대평가된 가용액으로 다음 매수를 내면 KIS 가 잔고부족으로 거부하고 `:1415-1416` 이 `block_buy(+900s)` 를 건다. **그 전략 15분 전면 매수 정지** |

(b) 는 랏 기하학과 직결된다. q(설계 랏 ÷ 중앙 주가)가 VB 0.74 · LTV 1.11 인 지금, 예산
이중 사용은 곧 **그 전략 노출 2배**다. K축·ρ축 캡은 **랏 하나의 크기**만 보므로 랏 개수
폭증을 구조적으로 못 막는다(cycle332 S2 와 같은 계열).

#### 유지의 비용은 생각보다 훨씬 작다 — 두 가지 실측 근거

**첫째, 매수 축에서 「종일 미체결」은 구조적으로 드물다.**
- 주 경로는 시장가다(`:1224`).
- 폴백·프리장 변환 지정가는 `step_up(current_price, 5)` — 현재가보다 **5틱 위**다(`:1234`,
  `:1439`). 매수에서 시장가보다 위에 건 지정가는 사실상 즉시 체결이다. 매도의 `step_down`
  과 대칭인 「체결률 확보」 방향이다.
- 진짜 잔존 구간은 **NXT 프리장(08:00~08:50) 매수** 하나인데, 그 코호트는 GTP(`27`)면
  08:50 거래소 자동취소이고 **우리가 그 취소 통보를 처리하지 못하는 기존 결함**이 이미
  문서화돼 있다(`src/engine/CLAUDE.md` 「알려진 비용 — GTP 08:50 자동취소 잔존 상태」).
  즉 그 코호트는 **이미** `pending_buys` 종일 잔존 상태이고, 이 사이클의 유지 결정이 그
  결함의 모양을 바꾸지 않는다.

**둘째 — 🔴 `pending_buys` 해제는 「전량 체결」이 아니라 「첫 체결」에 일어난다.**
`order_engine.py:2572-2576` 은 `if total_filled >= ordered_qty:` 분기(`:2578`) **앞**에 있다.
즉 **1주만 채워져도** `pending_buys.discard` + `pending_buy_amounts.pop` +
`_pending_buy_orders.pop` 이 실행된다. 유지의 비용이 남는 것은 **체결이 0인 주문뿐**이다.
(그 대가로 부분체결 잔여가 예산에서 빠지는 것은 cycle332 S2 가 이미 적어 둔 별개 사안이다.)

**결론 — 비대칭이 명백하다.**
유지의 최악 비용 = 그 전략, 그 종목 슬롯 1개 + 그 금액이 21:30 `_reset_daily_state` 까지 논다
(그것도 무체결 주문 한정).
해제의 비용 = 예산 이중 사용 + 같은 종목 2랏 + 900초 매수 락 + 그 틱 청산 평가 전면 소멸.

#### (b) 「별도 회수 경로」를 반대하는 이유

방향은 옳지만 **이 사이클이 아니다.** 제대로 하려면 `selling_reconcile.py` 의 대칭인
`buying_reconcile` 이 필요하고, 그쪽이 그랬듯 3중 가드(열린 주문 존재 / 보유 상태 / 최소
경과 시간)를 요구한다. `execute_buy` 안에 KIS 주문내역 왕복을 얹는 것은 더 나쁘다 —
그 함수는 A-ATOMIC 구간을 안고 있다. **별건 카드 A.**

#### 반례 — 유지가 틀리는 단 하나의 경우

주문이 접수된 직후 **거래소가 스스로 취소**하는 경우다: ① NXT GTP 08:50 일괄취소
② KRX 정규장 마감 후 미체결 자동취소(09-14 제도). 그때는 자금이 실제로 풀렸는데 우리는
계속 묶는다. 다만 이것은 **취소 통보 미처리라는 기존 결함**이지 이 사이클이 만드는 것이
아니고, 시정 경로도 이미 정본에 적혀 있다(**별건 카드 B**).

---

### Q2. 마커 — ERROR · 무cap 동의, **필드 2개 추가 권고**

**레벨 ERROR 동의.** 매도 대칭이고 `_aggregate_log_patterns` 가 WARNING 이상만
`top_patterns` 에 넣으므로 21:30 리포트에 오른다. WARNING 으로 낮추면 같은 리포트에
들어가긴 하지만 매도 축과 심각도가 갈려 판독이 어긋난다.

**무cap 동의 — 적극적 근거가 있다.** 이 마커는 **「예산을 점유한 채 `trade_history` 행이
없는 주문」의 유일한 목록**이다. 운영자가 D+1 에 어느 주문을 KIS 주문내역과 대조해야
하는지 알려면 건별로 전부 남아야 한다(cycle331 이 `[buy_fill_strategy_from_pending]` 을
무cap 으로 둔 것과 같은 논리 — 한 건 한 건이 조사 단위다). 빈도 폭주 우려도 낮다: 이
경로가 발화하려면 DB 예외가 나야 하고(RDS 페일오버는 수십 초), 그 창에 매수 시도는
`is_ticker_blocked_for_buy` + `max_positions` 때문에 한 자릿수다.

**추가 권고 — `qty=` · `price=` 를 싣는다.** 매도 축은 포지션이 남아 있어 사후에 수량을
알 수 있다. **매수는 포지션도 장부도 없다.** 그 주문의 규모를 알 채널이 KIS 주문내역
말고는 이 마커뿐이다. 두 값은 이미 래퍼 인자라 비용 0이다.

```
[buy_post_send_error] ticker=%s order_no=%s strategy=%s path=%s qty=%d price=%d
— 주문은 접수됐다. pending 을 풀지 않고 체결통보·동기화에 맡긴다.
```

**꼬리 문구는 매도와 달라야 한다.** 매도의 "재발사하지 않고" 는 재시도 루프가 있어서
나온 문장이다. 매수에는 재시도 루프가 없다(폴백 1회뿐). 제안의 "pending 을 풀지 않고" 가
정확하다 — 그대로 간다.

---

### Q3. 경계의 시작점 — **제안대로 코어 호출 한 문장. 동의.**

매핑 등록(`:1334~1354`)을 경계 밖에 두는 판단이 맞다. 근거 셋:

1. **dict 대입 6개는 실패 경로가 없다.** `MemoryError` 급이면 전체가 죽는 게 맞다. 실패할
   수 없는 코드를 감싸면 감싼 만큼 진짜 결함이 숨는다.
2. **매핑 실패는 삼키면 안 되는 종류다.** 매핑 없이 체결통보가 오면 귀속이 깨지고, 그게
   cycle331 이 고친 바로 그 병리(포지션 미등록 = 그날 손절·트레일링·15:20 일괄청산 전면
   부재)다. 조용히 넘기면 자본 위험이 곧바로 생긴다.
3. **매도 축도 매핑 등록은 경계 밖이다.** 두 축의 경계 폭이 갈리면 다음 사이클이 어느 쪽을
   정본으로 볼지 모른다 — cycle334 가 4곳을 1코어로 모은 이유가 그 흩어짐이었다.

**🔴 다만 구조에 조건 하나를 붙인다 — 호출부 인라인 `try` 2개로 하지 말고 반드시 래퍼
함수를 만든다.** cycle328 이 매도에서 확정한 원칙이 이것이다: 경계는 호출부의 문맥이
아니라 **함수 자신의 `except Exception`** 에 있어야 한다. 그래야 폴백 경로처럼
**`except KisApiError` 블록 안**이라는 위험한 자리에서도 "이 문장은 예외를 던지지
않는다" 가 성립한다. 인라인으로 하면 두 자리의 `except` 가 따로 놀아 **한쪽만 좁혀지는**
회귀가 열린다(cycle328 격리 실측이 보여 준 그 방향이다).

**🔴 `:1407` 의 `logger.info("매수 주문 접수")` 와 `:1410` 의 `cached_buyable_at = 0.0` 을
경계 안으로 옮기지 않는다.** 경계 뒤에 남아야 예외가 멎은 뒤 정상 실행된다 — 그게 피해
(d) 시정의 본체다.

---

### Q4. `llm_buy_gate.observe_order` 훅 — **무접촉이 맞다. 그리고 이 사이클에서 그 훅의 가치가 오른다.**

무접촉 근거는 요청서가 쓴 대로다(이미 자체 `try/except Exception → logger.debug`,
never-raise, cycle276 이 「매핑 등록 **뒤** · PENDING INSERT **앞**」을 명세로 못 박음).
여기에 하나 더한다:

**접수 성공 + `trade_history` 부재 상태에서 `llm_buy_evaluations` 행이 「그 주문이
존재했다」는 두 번째 장부가 된다.** migration 043 은 주문 1건 = 1행(성공·실패 모두)이고
`order_no`·주문가·수량·`budget_total_won`/`budget_remaining_after_won` 스냅샷을 담는다.
`llm_gate_mode=shadow` 인 동안 이 행은 `[buy_post_send_error]` 와 **교차 대조 가능한 유일한
구조화 기록**이다(`trade_history` 는 없고 포지션도 없다). 경계 안으로 옮기거나 순서를
바꾸면 그 가치가 사라진다.

부수적으로, 훅이 경계 **앞**에 있다는 사실이 경계의 스코프를 좁게 유지하는 근거이기도
하다 — 경계를 매핑 등록까지 넓히면 이 훅도 그 안에 들어가 버려 cycle276 명세가 깨진다.

---

### Q5. 매매 행위 변경인가 — **그렇다. 행위 보존이 아니라 행위 시정이다. 승인 대상 분류 맞다.**

실패 경로에서 바뀌는 것 넷:
- 그 종목 재매수 가능 → **차단** (진입 가능성 변경)
- 그 예산 해제 → **점유** (사이징 여력 변경)
- 그 틱의 나머지 전략 청산 평가 소멸 → **생존** (청산 커버리지 변경)
- **추가로 발견** — donchian·kojiro 의 **매수 직후 HIGH 구독 여부가 뒤집힌다**(Q6-④)

네 가지 모두 「진입·청산·수량」 축이므로 8영역 + 매매 행위 변경 + `domain-consult` 선행 —
정확히 규약대로다.

#### 롤백 다이얼 — **불필요하다. 두지 마라. 1커밋 revert 로 충분하다.**

1. 다이얼을 두면 "경계를 끄는 값" 이 존재하게 되고, 그 값의 의미는 **「접수된 주문의
   예산을 푼다」** 다. cycle328 이 `except` 를 좁히면 안 된다고 한 것과 같은 계열 —
   **끌 수 있게 만든 순간 누군가 끈다.**
2. cycle327·328 이 매도 축에서 다이얼 없이 갔다. 대칭을 깨면 두 축의 롤백 절차가 갈린다.
3. **성공 경로가 byte 동일**이라 롤백 필요성 자체가 낮다. 바뀌는 것은 오직 "코어가 예외를
   던졌을 때" 뿐이고, 그건 평시 0건이다.

**대신 롤백 조건을 명시해 둔다**: `[buy_post_send_error]` 가 하루 5건 이상 나오면 그것은
이 사이클의 결함이 아니라 **DB 가 아픈 것**이다. 그때 할 일은 revert 가 아니라 RDS 를
보는 것이다. 이 마커가 늘어난다고 revert 하면 **경계를 없애서 로그를 지우는 것**일 뿐
결함은 그대로 남는다(오히려 예산 이중 사용이 부활한다).

---

### Q6. 놓친 피해 경로 — 팀장 확인 사항 3건 대조 + 피라미딩

#### ① `_sync_orders_to_db` — **팀장 확인 전부 맞다. 한 가지 덧붙인다.**

- ✅ `scheduler.py:2340-2342` — `ccld_qty = int(order.get("tot_ccld_qty","0")); if ccld_qty <= 0
  or not ticker: continue`. **미체결 주문은 sync 대상이 아니다.**
- ✅ 체결되면 체결통보가 먼저 도착 → `update_trade_status` affected=0(`:2606`) →
  `_completed_orders.add` + **보정 INSERT COMPLETED**(`:2612-2622`) → 그 행이
  `(ticker, order_no)` 키를 채우므로 15분 sync 의 `existing_buy_keys`(`:2327-2328`)에 걸려
  skip. **중복 없음.**
- ✅ 체결통보까지 놓친 경우 15분 sync 가 마지막 안전망으로 INSERT 하고, 그때
  `db_strategy_map` 미스로 **`strategy="momentum"` 기본 귀속**(`:2357-2358`)이 된다.

🔴 **덧붙일 것 — 그 오귀인의 무게.** 메모리의 「1순위 위험 = 성과 귀인 붕괴」와 정면으로
닿는다. 그리고 **고칠 재료가 이미 메모리에 있다** — `_order_strategy[order_no]` 매핑은
그 상황에서도 **살아 있다**(매핑 등록은 경계 앞이고 `_handle_buy_fill` 전량 분기에서만
pop 된다). 즉 `db_strategy_map.get(ticker)` 미스 시 `order_engine._order_strategy.get(odno)`
를 한 단 더 보게 하면 한 줄로 닫힌다. **별건 카드 C.**

#### ② `_handle_buy_fill` 의 pending 해제 — **🔴 정정 필요. 「전량 체결」이 아니라 「첫 체결」이다.**

팀장이 인용한 `order_engine.py:2573-2576` 은 `if total_filled >= ordered_qty:` 분기
(`:2578`) **앞**에 있다. 그 자리는 「첫 체결 → 포지션 신규 등록」(`:2548`)과 「추가 체결 →
수량 갱신」(`:2567`)의 **합류점**이다. 따라서:

- **1주만 채워져도** `pending_buys.discard` + `pending_buy_amounts.pop` +
  `_pending_buy_orders.pop` 이 실행된다.
- 결론 방향은 팀장과 같다(정상 해제된다). **다만 이 사실이 Q1 의 (a) 판정을 더 강하게
  만든다** — 유지의 비용이 남는 것은 **체결이 0건인 주문뿐**이고, 매수 축에서 그건 사실상
  NXT 프리장 지정가 한 코호트다.
- 반대로 이것은 **부분체결 잔여가 예산에서 빠진다**는 뜻이기도 하다(cycle332 S2 가 이미
  적어 둔 별개 사안, 피라미딩에서 증폭된다 — 아래 ③).

#### ③ `_cancel_after_wait` — **팀장 확인 맞다. 다만 「무해」를 한 문장 조여야 한다.**

- ✅ 부분체결 분기(`:2692`)의 타이머 게이트는 `if qty_src == "map" and not
  strategy_from_pending:`(`:2707`)이다. **매핑 6종이 전부 남아 있으므로**(`:1334~1354` 는
  이미 실행됐다) `qty_src == "map"` · `strategy_from_pending == False` → 타이머가 정상
  등록된다.
- ✅ 30초 뒤 `ex = self._order_exchange.get(order_no)`(`:2914`)도 존재하므로 라우터 재평가
  없이 **원주문 거래소로 정상 취소**된다. `cancel_order` 는 성공한다.
- ⚠️ `:2942` 의 `update_trade_status(..., CANCELLED, order_no=order_no)` 는 **affected=0** 이
  되고 그 함수는 affected 를 받지도 확인하지도 않는다. 팀장 말대로 **보정 INSERT 경로가
  아니라 새 결함은 안 생긴다.** 다만 「무해」의 정확한 뜻은 **「취소 사실이 장부에 한 글자도
  안 남는다」**이고, 그 주문의 최종 기록은 15분 sync(= ① 의 momentum 오귀인 경로)에만
  의존한다. 같은 계열로 부분체결 분기 `:2695` 의 `PARTIAL` UPDATE 도 affected 를 안 본다.
  → **별건 카드 D**(관측만 추가, 행위 무변경).
- **이 사이클 기준으로는 현행과 제안이 동일하다** — 제안이 이 경로를 열지도 악화시키지도
  않는다. 현행에서도 `_handle_buy_fill` 은 별도 콜백이라 `risk.on_tick` 이 죽어도 돈다.

#### ④ 🔴 **추가 발견 — swing poll 의 `buy_succeeded` 판정이 뒤집힌다** (요청서·팀장 확인 모두 미포함)

`src/engine/scheduler.py:2780-2783`:
```
buy_succeeded = (
    t in strategy.state.pending_buys
    or t in strategy.state.positions
)
```
현행에서 접수 성공 + 장부 실패가 나면 `:1525` 가 `pending_buys` 를 지우고 포지션은 체결통보
전이라 아직 없다 → **`buy_succeeded = False`**. 그 결과 바로 아래(`:2788-2791`)의
**「안전 불변식: 보유 종목 손절/트레일링 평가 필수 → 매수 직후 HIGH 구독」이 통째로
건너뛰어진다.** 회복은 포지션 등록 이후 `_scan_loop` 5분이다. donchian·kojiro 는 멀티데이
전략이라 그 5분이 손절 blind 다. `total_bought` 집계도 어긋난다.

제안을 적용하면 `pending_buys` 가 남아 `buy_succeeded = True` 가 되고 이 경로가 자동으로
고쳐진다. **부수 이득이지만 회귀로 봉인할 가치가 있다**(아래 회귀 목록 10번).

#### ⑤ 무해 확인 2건

- `_completed_orders` 잔존 — 래퍼가 예외를 먹고 끝나면 이후 체결통보의
  `_completed_orders.add(order_no)`(`:2609`)를 아무도 discard 하지 않는다. KIS `ODNO` 는
  하루 단위 유일이고 `reset_daily_state` 가 clear 하므로 **무해**.
- `state.order_attempt_today`(`:1205`)는 `pending_buys.add` 옆에서 이미 증가했고 실패 경로가
  되돌리지 않는다. 현행과 동일 — **무해**.

#### ⑥ 피라미딩 착수 시 증폭 — **이 사이클은 피라미딩의 선결 조건이다**

피라미딩이 들어오면 `is_ticker_blocked_for_buy`(`strategy_registry.py:86-98`)가 더 이상
"한 종목 1랏" 을 강제하지 못하고, **`pending_buy_amounts` 가 그 종목 미체결 랏 총액의 유일한
장부**가 된다. 세 갈래로 증폭된다:

1. 🔴 **`pending_buy_amounts` 는 `ticker → 금액` 단일 dict 다**(`strategy_base.py:110`).
   같은 종목 두 번째 주문이 첫 번째를 **덮어쓴다**. 현행 실패 정리(`pop(ticker)`)는
   **랏 1의 예정 금액까지 함께 지운다** — 피해가 그 종목의 **전체 미체결 예산**으로
   확대되고 랏 3이 곧바로 나갈 수 있다.
2. 🔴 위 ②가 더해진다 — **첫 부분체결에서 이미 해제**되므로, 피라미딩에서는 랏 1의
   1주 체결이 랏 2·3의 예정 금액까지 장부에서 지운다. 사다리를 올릴수록 예산 장부가
   실제보다 작아지는 **단조 과소계상**이 된다.
3. K축·ρ축 캡은 진입 시점 **랏 하나의 크기**만 보므로 **랏 개수 폭증을 못 막는다**
   (cycle332 S2 와 같은 계열). 유일한 브레이크가 예산 관문인데 그게 과소계상된다.

→ 키를 `(ticker, order_no)` 로 바꾸는 것이 피라미딩 선결이다(**별건 카드 E**). 그리고
**그 전에 접수 후 경계가 없으면 키 변경도 무의미하다** — 경계가 없으면 예외 한 번이
그 종목 전체 장부를 날린다. 순서는 **이 사이클 → E → 피라미딩**이다.

---

### 팀장 확정 사항 2건에 대한 판정

#### (가) `test_cycle271::test_c7_1`·`test_c7_2` 재작성 — **동의한다. 단 잃는 것이 하나 있고, 그것을 되찾는 방법이 있다.**

**팀장 판단이 맞다.** 두 케이스가 봉인한 계약은 「**코어가 흡수해서 성공으로 만들지
않는다**」이고, 그 단언은 `_marker_records(caplog) == []`(= `[buy_fill_during_insert]`
부재)다. `pytest.raises` 는 그 계약의 **관측 수단**이었지 계약 자체가 아니다. 경계가
서면 관측 수단이 「예외가 호출자에 도달한다」에서 「`[buy_post_send_error]` 가 1행
남는다」로 옮겨가는 것이 맞다. 두 계약 모두 새 단언으로 **그대로 검출된다**:

- 누군가 코어에 `try/except` 를 들여 조용히 흡수하면 → 예외 없음 → **`[buy_post_send_error]`
  미발화** → 새 단언이 붉어진다.
- m7 뮤테이션(코어의 `except UniqueViolationError:` → `except Exception:`)도 같은 이유로
  붉어진다(`test_c7_2`).

🔴 **잃는 것 = 예외의 「타입 충실도」다.** 래퍼는 `except Exception` 이라 타입을 삼킨다.
`test_c7_1` 의 `UniqueViolationError`, `test_c7_2` 의 `ConnectionResetError(match=...)` 가
증명하던 "코어가 **그 예외를 그대로** 올려보낸다" 는 `execute_buy` 층에서 더 이상 관측
불가다. 코어가 예외를 **감싸서** 다른 타입으로 던지는 회귀는 새 단언을 통과한다.

**되찾는 방법 — 코어 층에 직접 단언을 하나 내린다.** `_persist_pending_after_send` 를
직접 호출하는 단위 테스트 2케이스를 두고 거기서 `pytest.raises(UniqueViolationError)` /
`pytest.raises(ConnectionResetError)` 를 유지한다. 그것이 cycle334 의 「**코어는 전파한다**」
계약이 여전히 참인 **유일한 층**이고, 비용은 작은 테스트 둘이다. `execute_buy` 층 테스트는
팀장 안대로 새 계약으로 옮긴다. 이 분리가 깔끔하다 —
**「코어는 던진다」(코어 층) + 「execute_buy 는 안 던진다」(호출자 층)** 가 나란히 봉인된다.

**부수 정리 2건(행위 무관, 문서 드리프트):**
- `test_c1_2` docstring 의 "예외가 호출자로 직행한다" 는 이 사이클 이후 **거짓**이 된다.
  같이 고친다.
- `test_c5_1`·`test_c5_2` 의 `try: ... except UniqueViolationError: pass` 는 이미 방어적
  코드였고 계속 통과한다(무해). 굳이 건드리지 않아도 된다.

#### (나) 매수 축 접수 후 행위 회귀 0건 — **사실 확인 동의. 그래서 이 사이클의 그물이 본체다.**

`test_cycle271` 6케이스는 **race 흡수**(체결통보 선행) 축만 덮고 **접수 후 경계** 축은
한 케이스도 없다. 매도 축은 cycle327 6 + cycle328 9 케이스가 있는데 매수는 0이다 —
그 비대칭 자체가 이 결함이 지금까지 안 보인 이유다. 그러니 이 사이클의 산출물 중
**회귀 그물이 코드 변경만큼 중요하다**. 아래 13개가 최소 집합이다.

---

## 권고 요약

### 1. 채택/수정/반대

**채택한다 — 제안(§3)의 설계는 옳고, 마커에 `qty=`·`price=` 두 필드를 더하는 것만 수정
권고한다.** 핵심 판정은 「접수된 주문의 자금은 브로커 장부에서 이미 묶였으므로 우리
장부도 묶어 둔다 = (a) 유지」이고, 유지의 비용(무체결 주문 한정, 그 전략 슬롯 1개가
21:30까지 논다)이 해제의 비용(예산 이중 사용 + 같은 종목 2랏 + 900초 매수 락 + 그 틱
청산 평가 전면 소멸)보다 **명백히 작다**.

### 2. 시정 범위

| 파일 | 위치 | 변경 |
|---|---|---|
| `src/engine/order_engine.py` | `:1084` 직후(`_persist_sell_pending_after_send` 바로 아래) | 신규 `_persist_buy_pending_after_send(self, *, ticker, order_no, strategy_id, record_price, quantity, path) -> None` — 매도 래퍼와 **동일 구조**(최상위 `try` 1개 · 핸들러 1개 · `except Exception` · `logger.exception`) |
| `src/engine/order_engine.py` | `:1397~1405` | 코어 직접 호출 → 래퍼 호출 (`path="market"`) |
| `src/engine/order_engine.py` | `:1498~1506` | 코어 직접 호출 → 래퍼 호출 (`path="fallback"`) |
| — | 그 밖 | **한 글자도 건드리지 않는다.** 특히 `:1334~1354`(매핑) · `:1361~1391`(LLM 훅) · `:1407`·`:1410` · `:1412~1416` · `:1441~1443` · `:1514~1522` · `:1524~1527` |
| `tests/unit/engine/test_cycle271_execute_buy_fill_during_insert.py` | `test_c7_1`·`test_c7_2` | `pytest.raises` → `[buy_post_send_error]` 1행 + `pending_buys` 유지 단언. `_marker_records == []` 는 **그대로 둔다**. `test_c1_2` docstring 정정 |
| `tests/unit/engine/` (신규) | 코어 층 2케이스 | `_persist_pending_after_send` 직접 호출 + `pytest.raises` 유지 (타입 충실도 회수) |
| `tests/unit/engine/` (신규) | cycle335 회귀 | 아래 3항 1~10 |
| `tests/unit/ast/` | cycle328 가드 재조준 또는 신규 | 아래 3항 11~13 |
| `src/engine/CLAUDE.md` | 「접수 후 PENDING 영속화 — 4경로 1코어」 절 | 「매수는 아직 닫지 않는다」·「매수 축의 접수 후 경계 부재는 결함이다」 두 단락을 **현재 상태로 덮어쓴다**(코어 호출 = 래퍼 2 = 정확히 2곳, 코어 직접 호출 0) |
| 루트 `CLAUDE.md` | 「주문이 나간 뒤의 실패로 재발사 금지 (cycle327)」 | 매수 축이 같은 규약 아래 들어왔음을 한 문장 추가 |

### 3. 회귀 테스트로 봉인할 계약 (케이스별 한 줄)

**행위 — 주 경로**
1. 코어가 임의 `Exception` 을 던져도 `execute_buy` 가 정상 종료하고 `pending_buys` / `pending_buy_amounts` 가 **유지**된다.
2. 같은 조건에서 `state.cached_buyable_at == 0.0` 이 되고 `"매수 주문 접수"` INFO 가 남는다.
3. 같은 조건에서 매핑 6종(`_order_qty`/`_order_strategy`/`_order_ticker`/`_order_exchange`/`_order_division`/`_pending_buy_orders`)이 전부 남는다.

**행위 — 폴백 경로**
4. 1차 `KisApiError`(APBK1943) → 폴백 `place_order` 성공 → 코어가 **non-`KisApiError`** 를 던져도 `execute_buy` 가 정상 `return` 하고 `pending_buys` 유지 + `cached_buyable_at == 0.0` + 폴백 WARNING 이 남는다.
5. 같은 조건에서 `block_low_funds` 가 **등록되지 않는다**(`:1517` 은 발사 실패 전용이다).

**마커**
6. 두 경로 모두 `[buy_post_send_error]` ERROR 1행 + 6필드(`ticker`/`order_no`/`strategy`/`path`/`qty`/`price`), `path` 가 각각 `market`·`fallback`.
7. 코어의 **정상 skip 경로**(체결통보 선행 = `order_no in _completed_orders`)는 예외를 던지지 않으므로 마커가 **나오지 않는다**(cycle328 `test_g328_4` 와 같은 오염 차단).
8. `UniqueViolationError` + **증거 없음**(`order_no ∉ _completed_orders`) → 코어가 전파 → 래퍼가 먹고 마커 1행 + `[buy_fill_during_insert]` 는 **0행**(= 재작성된 `test_c7_1`).

**무회귀**
9. 코어가 정상 완료하면 마커 0행 + 기존 로그·상태·호출 순서 전부 byte 동일.
10. 🔴 **swing poll 연동** — 접수 후 장부 실패로 끝나도 `scheduler.py:2780-2783` 의 `buy_succeeded == True` 가 되어 `:2791` 의 매수 직후 HIGH 구독이 호출된다.

**구조 (AST)**
11. `_persist_buy_pending_after_send` = 최상위 `try` 1개 · 핸들러 1개 · 타입 정확히 `Exception` · 본문 앞부분의 `await` 는 코어 호출 **하나뿐**(cycle328 `test_g328_3b`/`test_g328_2` 재조준).
12. `execute_buy` 안의 `_persist_pending_after_send` **직접 호출 0건**(두 곳 모두 래퍼 경유).
13. 코어 `_persist_pending_after_send` 에 여전히 `try` **0개**(cycle334 `test_g328_0d` 유지).

### 4. 이 사이클에서 하면 안 되는 것 (금기)

- 🔴 **코어 `_persist_pending_after_send` 에 `try` 를 넣지 않는다.** 넣으면 cycle334 가 세운 「코어는 전파, 경계는 호출자 층」이 무너진다.
- 🔴 **래퍼의 `except Exception` 을 좁히지 않는다.** cycle328 격리 실측이 증명했다 — 좁히면 기존 행위 회귀가 **전부 초록인 채로** 새는 경로가 남는다. 구조 가드가 유일한 방어다.
- 🔴 **호출부 인라인 `try` 2개로 대체하지 않는다.** 경계는 호출부 문맥이 아니라 함수 자신의 `except` 에 있어야 한다(폴백은 `except KisApiError` **안**이라는 위험한 자리다).
- 🔴 **`:1441~1443` 의 폴백 `pending_buys.add` / `pending_buy_amounts` 재등록을 건드리지 않는다.** 그 재등록은 "주문이 또 나간다" 는 사실의 기록이고 유지 결정과 정합한다.
- 🔴 **`:1407` INFO 와 `:1410` `cached_buyable_at = 0.0` 을 경계 안으로 옮기지 않는다.**
- 🔴 **`pending_buys` 회수 로직(KIS 주문내역 조회 등)을 `execute_buy` 안에 넣지 않는다.** 별건이고, A-ATOMIC 구간을 안은 함수에 KIS 왕복을 얹는 일이다.
- 🔴 **마커를 WARNING 으로 낮추거나 `KstDailyEmitCap` 을 걸지 않는다.** 이 마커가 「예산을 점유한 채 장부가 없는 주문」의 유일한 목록이다.
- 🔴 **`llm_buy_gate.observe_order` 의 자리·훅을 건드리지 않는다.** 그 행이 이 상태에서 주문 존재를 증명하는 두 번째 장부다.
- 🔴 **롤백 다이얼(파라미터 키)을 만들지 않는다.** 그 다이얼의 의미는 「접수된 주문의 예산을 푼다」이고, 끌 수 있게 만든 순간 누군가 끈다.
- 🔴 **`test_c7_1`·`test_c7_2` 의 `_marker_records(caplog) == []` 단언을 함께 지우지 않는다.** 그것이 두 케이스의 **본 계약**이고 `pytest.raises` 는 옛 관측 수단일 뿐이다.

### 5. 이 사이클 밖으로 빼야 할 별건 카드

| # | 카드 | 근거 | 접촉 |
|---|---|---|---|
| **A** | `buying_reconcile` — `selling_reconcile.py` 의 대칭. 15분 sync 에서 KIS 미체결 주문에 그 `order_no` 가 없으면 `pending_buys` 해제 | Q1 의 (b) 안이 가리킨 진짜 수요. 3중 가드(열린 주문 / 보유 / 최소 경과) 필요 | 신규 leaf + `scheduler.py` 위임(승인) |
| **B** | 거래소 자동취소 통보 처리 — GTP 08:50 일괄취소 + KRX 정규장 마감 미체결 자동취소 | 유지 결정이 틀리는 **유일한** 경우를 닫는다. 선결 = 취소 프레임 판별 필드 실측(정본에 이미 명시) | `realtime/handler.py` + `order_engine.py` **둘 다 8영역** |
| **C** | `_sync_orders_to_db` 의 `strategy` 폴백에 `order_engine._order_strategy` 한 단 추가 | `scheduler.py:2357-2358` 이 `"momentum"` 으로 폴백해 **성과 귀인이 붕괴**한다. 매핑은 메모리에 살아 있어 한 줄 | `scheduler.py`(승인) |
| **D** | 부분체결 `PARTIAL` UPDATE(`:2695`) · 취소 `CANCELLED` UPDATE(`:2942`)의 `affected==0` 무관측 | 장부 행이 없으면 부분체결·취소가 한 글자도 안 남고 15분 sync 에만 의존한다 | 관측만 추가(행위 무변경) |
| **E** | `pending_buy_amounts` 키를 `(ticker, order_no)` 로 | **피라미딩 선결.** 같은 종목 두 번째 주문이 첫 번째를 덮어쓰고, 첫 부분체결이 전체를 해제한다 | `strategy_base.py` + `order_engine.py`(8영역) |

---

**마지막 한 마디.** 이 시정은 매도 축(cycle327·328)과 완전 대칭이고, 성공 경로가 byte
동일이며, 실패 경로의 변화가 전부 **보수 방향**(덜 사고, 덜 쓰고, 더 오래 감시한다)이다.
07:45 전 배포 창에 넣기에 적절한 크기다 — 다만 **회귀 10번(swing poll `buy_succeeded`)을
빠뜨리지 말 것**을 강조한다. 그것이 요청서·팀장 확인 어디에도 없던 유일한 행위 변화이고,
donchian·kojiro 의 매수 직후 손절 커버리지에 직접 닿는다.
