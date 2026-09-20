# 1단계 코드리뷰 관문 — 도메인 판정 (잘린 뒷부분)

> 대상: `src/engine/order_engine.py::execute_sell` 접수 후 구간 헬퍼 추출 (1단계)
> 관문: domain-expert · 앞서 전달한 1~4번과 새 질문 A·B 답변은 여기 반복하지 않는다.
> 이 문서는 **5번의 잘린 뒷부분 · 6번 · 7번 · 판정 줄**만 담는다.

---

## 🔴 먼저 — 내 앞선 메시지의 오류 하나를 정정한다

앞 메시지에서 이렇게 적었다.

> `await place_order` 가 걸려 있는 동안 체결통보가 착지해 `_handle_sell_fill` 이 **`pos.quantity` 를 실제로 변형한다** — `src/engine/order_engine.py:2343` 의 `pos.quantity = total_filled`(부분 체결 분기).

**틀렸다.** `:2343` 은 `_handle_buy_fill`(`:2240-2473`) 안이다. `_handle_sell_fill`(`:2474-2621`)은 **`pos.quantity` 를 한 번도 변형하지 않는다** — 전량 분기는 `del state.positions[ticker]`(`:2542`), 부분 분기는 `update_trade_status(PARTIAL)` + `_schedule_cancel_and_reorder`(`:2617-2619`)뿐이다.

이 정정은 결론을 바꾼다. **매도 경로에서 `pos.quantity` 재읽기 자체의 실효는 거의 없다.** 그 창에서 `pos.quantity` 를 실제로 바꿀 수 있는 유일한 경로는 `_handle_buy_fill:2343`(같은 종목을 동시에 사고 파는 경우)인데, `registry.is_ticker_blocked_for_buy` 가 보유 종목 매수를 막으므로 정상 흐름에서는 닿지 않는다.

**대신 같은 창에 더 큰 결함이 있다.** 아래 5번은 그 결함으로 축을 바로잡아 다시 쓴 것이다. 판정 결론(`매매 행위 영향: 0`)은 바뀌지 않는다 — 이 결함도 이 diff 밖의 **기존 코드**이고, 추출이 악화시키지도 개선하지도 않는다.

---

## 5. 선결 결함 — 축을 바로잡은 전문

### 5.0 이 diff 자체는 문제없다 (앞서 보낸 부분의 결론 재확인)

헬퍼가 `quantity` 를 **인자(값)** 로 받는 것은 cycle327 ⓒ 와 충돌하지 않는다. PENDING 행이 기록해야 할 것은 "지금 보유량" 이 아니라 **"방금 주문한 수량"** 이고, 호출부가 `place_order` 에 넘긴 것과 같은 식을 그대로 넘기므로 계약이 유지된다. ⓒ 는 **발사 직전** 진실원, 헬퍼는 **발사 후** 기록자 — 역할이 갈린다.

### 5.1 진짜 결함 — 매핑 부재 창의 전량 오판

**사슬(전부 실측 라인 인용):**

```
execute_sell:1598   pos = strategy.state.positions.get(ticker)      ⓒ 재조회 (보유 10주)
execute_sell:1608   result = await place_order(..., quantity=pos.quantity=10, ...)
                    └─ 🔴 이 await 동안 order_no 는 아직 우리 손에 없다
                       (KIS 응답이 와야 order_no 를 안다 — 구조적으로 앞당길 수 없다)

  ◀ 이 창에 부분 체결통보(3주) 착지
     handle_execution_notice:2126  known_ticker = self._order_ticker.get(order_no)  → None
     :2143  WARNING "체결통보: 주문번호 %s에 대한 종목 매핑 없음, payload ticker 사용"
            → return 하지 않고 **그대로 진행**
     :2158  known_ordered = order_no in self._order_qty              → False
     :2159  ordered_qty = self._order_qty.get(order_no, quantity)    → 🔴 3 (증분값 폴백)
     :2162  total_filled = 3
     _handle_sell_fill:2541  if total_filled >= ordered_qty:         → 3 >= 3 → 🔴 전량 판정

execute_sell:1619   self._order_qty[result.order_no] = pos.quantity  ← 뒤늦게 10 등록
execute_sell:1631   await self._persist_sell_pending_after_send(...)  ← _completed_orders 히트 → skip (정상 동작)
execute_sell:1640   logger.info("매도 주문 접수") → return
```

**왜 결함인가.** `ordered_qty` 가 "주문 수량" 이 아니라 **"이번 통보의 증분 체결량"** 으로 폴백되므로, 첫 부분 체결이 **항상 `total_filled == ordered_qty`** 가 되어 전량으로 읽힌다. cycle235 주석(`:2145-2149`)이 이 위험을 이미 지목했지만 닫은 것은 `quantity <= 0` 축뿐이고, `quantity > 0` 부분 체결 축은 열려 있다.

**이 diff 와의 관계 — 악화도 개선도 아니다.** 변경 전에도 `TradeRecord(quantity=pos.quantity)` 가 같은 `await` 뒤 재읽기였고, `:1619` ↔ `:1634` 사이 `await` 는 전후 모두 **0건**이라 두 재읽기는 서로 일관된다. 매핑 등록 자리(`:1617-1623`)도 한 줄 안 움직였다. 추출은 이 결함을 **그대로 옮겼다**.

---

### 5.2 (질문 1) 실현 가능성 — 창은 실재한다. 다만 **두 창을 구분해야 한다**

당신 지적이 맞다. 시장가 즉시체결에서 WS 체결통보가 REST 응답보다 먼저 오는 것은 정본이 인정한 사실이고, 그래서 `_completed_orders` 가드가 있다. **그 가드가 발화한다는 것 자체가 이 창이 프로덕션에서 열린다는 증거다.**

그런데 "체결통보가 먼저 왔다" 에는 창이 **둘** 있고 피해가 다르다.

| | 창 | 그때 `_order_qty` 는 | 피해 |
|---|---|---|---|
| **창 1** | `place_order` **반환 후** ~ `await insert_trade` 도중 | **있다**(`:1619` 에서 등록 완료) | `ordered_qty` 정상 → 전량/부분 판정 정확. PENDING INSERT 만 UNIQUE 충돌 → **cycle271/327 흡수기가 덮는다** |
| **창 2** | `await place_order` **도중** | **없다**(order_no 미상) | `ordered_qty` 증분 폴백 → **전량 오판**. 흡수기가 덮지 않는다(흡수기는 INSERT 축만 본다) |

**현행 회귀·마커가 증명하는 것은 창 1 뿐이다.** `[sell_fill_during_insert]`·"체결통보 선행 race — COMPLETED 직접 INSERT" 는 둘 다 창 1·창 2 에서 모두 날 수 있어 구별하지 못한다.

**창 2 만의 지문이 하나 있다 — `order_engine.py:2143` 의 WARNING.**

```
"체결통보: 주문번호 %s에 대한 종목 매핑 없음, payload ticker 사용: %s"
```

이 줄은 `_order_ticker[order_no]` 가 없을 때만 찍히고, 매핑은 `place_order` 반환 직후 동기 영역에서 등록되므로 **`await place_order` 도중 도착한 통보에서만** 발화한다. WARNING 이라 `_DbLogHandler` INFO 컷을 넘어 `system_logs` 에 영구 적재된다.

**즉 D+1 측정이 가능하다:**

```sql
SELECT timestamp, message FROM system_logs
WHERE message LIKE '%주문번호%에 대한 종목 매핑 없음%'
ORDER BY timestamp DESC LIMIT 200;
```

⚠️ 이 마커는 매수·매도를 구분하지 않는다(그 자리엔 `side` 가 안 실린다). 같은 `order_no` 를 `trade_history.trade_type` 으로 조인하거나, 인접 시각의 `"매도 주문 접수"` / `"매수 체결 → 포지션 등록"` 로그로 축을 가른다. 그리고 **수동 매매(MTS/HTS)·외부 주문도 같은 줄을 찍는다** — 그쪽은 매핑이 원래 없는 정상 케이스라 분모에서 빼야 한다(우리 `execute_sell` 발사 시각과 초 단위로 겹치는 행만 창 2 다).

### 5.3 (질문 2) 피해의 크기 — **전량인데 부분이 아니라, 부분인데 전량으로 읽는다**

방향이 명확하다. `ordered_qty` 가 **작은 쪽으로** 오염되므로 `total_filled >= ordered_qty` 가 **너무 일찍 참**이 된다.

**10주 매도 발사 → 창 2 에서 3주 부분 체결이 착지한 경우:**

| 대상 | 결과 |
|---|---|
| **포지션(메모리)** | `del state.positions[ticker]`(`:2542`) — 🔴 **미체결 7주가 무보유가 된다.** `risk.on_tick` 은 `registry.enabled()` 의 `positions` 만 순회하므로 그 7주는 **손절·트레일링·익일청산·15:20 강제청산이 전부 정지**한다. 이 금기(「보유 포지션이 있는 전략을 끄지 않는다」)가 막으려던 것과 **같은 결과**를 다른 경로로 만든다 |
| **포지션(DB)** | `delete_position(ticker)` — 재시작해도 안 돌아온다 |
| **`on_position_closed`** | 호출됨 → LTV `_limit_up_reached.discard` · BFB `_partial_exit.pop` · BFB/VCP 쿨다운 등록. 청산 모드 상태가 7주 남은 채로 지워진다 |
| **`sold_today`** | `.add(ticker)` → `is_ticker_blocked_for_buy` 가 **당일 재진입을 막는다**(잔량을 되살릴 길도 막힌다) |
| **`_selling`** | `.discard` → 진행 중 표식 해제(이 축은 오히려 정상 방향) |
| **`trade_history`** | 1차 `update_trade_status(COMPLETED, match_partial=True)` 가 `affected==0`(PENDING 미삽입) → 보정 COMPLETED INSERT + `_completed_orders.add(order_no)`. **3주가 "전량 체결" 로 기록된다.** 실현손익도 3주분만 |
| **정리 dict** | `_filled_qty`/`_order_qty`/`_order_strategy`/`_order_ticker`/`_order_exchange`/`_order_division` 을 **전부 pop**(`:2597-2602`) |

**그리고 2차 피해가 붙는다.** 위에서 `_filled_qty` 가 pop 됐으므로, 같은 주문의 잔여 7주 체결통보가 오면 `prev_total=0` → `total_filled=7`. 이때는 `:1619` 가 이미 `_order_qty[order_no]=10` 을 등록해 뒀으므로 `7 >= 10` **거짓 → 부분 판정** → `_schedule_cancel_and_reorder(ticker, order_no, remaining=3, is_stop_loss=True)`. **포지션이 없는데 손절 재주문 타이머가 걸린다.** `_cancel_and_reorder` 는 `:2855` 에서 `positions.get(ticker)` 를 다시 읽어 None 이면 빠지므로 중복 매도까지 가지는 않지만, 그건 우연한 방어이지 설계된 방어가 아니다.

**요약**: 자본 위험의 본체는 **미체결 잔량 7주가 손절 감시 밖으로 사라지는 것**이다. `_sync_positions_from_balance`(15분)가 KIS 잔고에서 포지션을 되살리지만, `sold_today` 와 전략 매핑 복원 여부가 그 복구의 완전성을 좌우하고, 그 15분 동안은 **손절이 없다**.

### 5.4 (질문 3) 지금 시정인가, 피라미딩 착수 때인가 — **지금은 「측정」이고, 시정은 그 결과에 건다**

앞 메시지에서 "지금은 부분 체결이 예외 경로라 무해" 라고 했다. **근거가 약했고 철회한다.** 당신 지적이 맞다 — cycle327 도 같은 논리로 5개월 잠복했다.

다만 cycle327 과 **결정적으로 다른 점이 하나** 있고, 그것이 내 판단의 근거다.

> **cycle327 이 5개월 잠복한 이유는 그 사슬에 마커가 하나도 없었기 때문이다.** 이 창은 다르다 — `:2143` WARNING 이 **이미 존재하고 `system_logs` 에 적재된다**. 즉 "보이지 않는 잠복" 이 아니라 **"측정하면 보이는데 아직 안 봤다"** 다.

그래서 정확한 현재 상태는 "무해하다" 가 아니라 **"빈도를 모른다"** 이다. 판단은 다음과 같이 갈린다.

| 측정 결과(최근 30일, 매도 축) | 판단 |
|---|---|
| **1건이라도 있다** | 🔴 **즉시 시정 대상.** 피라미딩을 기다리지 않는다 — 단일 `Position` 상태에서도 위 5.3 피해가 그대로 난다 |
| **0건** | 피라미딩 착수 사이클의 **선결 과제**로 둔다. 피라미딩에서는 부분 체결이 정상 경로가 되어 빈도가 구조적으로 는다 |

**지금 이 사이클에 섞지 않는 이유는 따로 있다** — 진행 규약 §3 「1단계 = 1커밋 = 1의도」다. 이건 행위 변경이고 8영역이라, 행위 보존 추출 커밋에 섞으면 회귀 추적이 불가능해진다. cycle327 을 리팩토링과 분리한 것과 같은 판단이다.

**권고 = 측정을 이 사이클의 산출물로 넣는다.** 코드 변경 0, SQL 한 줄, 승인 불필요. 결과를 `_workspace/00_URGENT_WORKLIST.md` 에 숫자로 남기면 다음 판단이 감이 아니라 실측이 된다.

### 5.5 (질문 4) 시정 방향 — 지역 변수만으로는 **불충분하다.** 두 축이다

> "발사 직전에 `ordered_qty = pos.quantity` 를 지역 변수로 한 번만 읽고 매핑·헬퍼가 그 값을 쓰는 것으로 충분합니까?"

**충분하지 않다.** 그건 **축 (b)** 만 닫는데, 5.0 의 정정대로 매도 경로에서 (b) 의 실효는 거의 없다. 본체는 **축 (a)** 다.

#### 축 (a) — 매핑 부재 상태의 전량 판정을 금지한다 [본체]

`handle_execution_notice` 의 `known_ordered`(`:2158`)는 이미 계산돼 있는데 **overrun 클램프에만 쓰이고 전량 판정에는 안 쓰인다**. 그것을 `_handle_sell_fill:2541` 의 분기에 물린다 — `known_ordered == False` 면 전량으로 확정하지 않고 **부분(PARTIAL)로만 처리**한다(포지션을 지우지 않는다).

- **cycle235 의 확장이다** — 그쪽은 `quantity <= 0` 을 fail-closed 로 막았고, 이건 `known_ordered=False` 를 같은 방향으로 막는다. 설계 철학이 동일하다.
- 🔴 **반대 위험을 반드시 따져야 한다.** 매핑 부재는 **수동 매매(MTS/HTS)·외부 주문의 정상 상태**이기도 하다. 그 경우 전량 판정을 막으면 **포지션이 영영 안 지워지고** `_schedule_cancel_and_reorder` 가 실재하지 않는 잔량을 취소하려 든다. 즉 (a)는 "안전한 방향으로 조인다" 가 아니라 **두 오류를 맞바꾸는 선택**이다.
- 그래서 (a)는 단순 시정이 아니다. **`domain-consult` 선행 + tdd Red 선행**이 필요하고, 십중팔구 "매핑 부재 + 그 ticker 를 우리가 보유 중" 같은 **추가 조건**으로 두 케이스를 가르는 설계가 된다. 카드 한 장짜리가 아니다.

#### 축 (b) — 발사 시점 수량 고정 [동반, 저비용]

```
ordered_qty = pos.quantity          # place_order 앞에서 한 번만
result = await place_order(..., quantity=ordered_qty, ...)
self._order_qty[result.order_no] = ordered_qty          # :1619
await self._persist_sell_pending_after_send(..., quantity=ordered_qty, ...)   # :1634
```

폴백 경로(`:1937-1940` / `:1947` / `:1962`)도 동일. 실효는 작지만 **cycle327 ⓒ 의 계약 문구("수량의 유일한 진실원")와 코드를 일치시킨다** — 지금은 문구가 발사 시점을 말하는데 코드는 발사 후에 다시 읽는다. 피라미딩에서 `_handle_buy_fill` 경유 변형이 정상 경로가 되면 실효도 생긴다.

#### 승인 범위

- **(a)·(b) 둘 다 `src/engine/order_engine.py` = 8영역 = 승인 필요.**
- (a)는 추가로 **「매매 행위를 바꾸는 코드 변경」**(청산 규약 — 포지션 제거 시점)이라 루트 `CLAUDE.md` 의 **`domain-consult` 선행 의무**가 붙는다.
- (b)만 단독이면 행위 보존에 가깝지만(값이 같은 경우가 대부분), **`_order_qty` 에 들어가는 값이 바뀔 수 있는 변경**이라 행위 보존이라고 주장하지 않는다. 역시 승인 대상이다.
- ⚠️ (a)는 `_handle_sell_fill` 을 건드리는데, 그 함수의 전량 분기는 `test_cycle185_cluster1_ast.py` 가 **positions 제거 site 집합 `{_handle_sell_fill, execute_sell}`** 로 봉인하고 있다. site 를 늘리지 않고 조건만 조이는 모양이면 그 가드는 통과한다.

### 5.6 (질문 5) cycle327 ⓒ 와의 관계 — **같은 계약의 앞뒤가 아니다. ⓒ 가 이 결함을 가린다**

| | ⓒ (cycle327) | 이 결함 |
|---|---|---|
| 보는 시점 | **재시도 사이**(루프 top, `:1598`) | **한 시도 안**(`await place_order` 도중) |
| 트리거 | `place_order` 가 **실패**해서 루프가 다시 돈다 | `place_order` 가 **성공**한다 |
| 발화 | `[sell_position_gone]` | **없다** |

**ⓒ 는 구조적으로 이 창을 못 본다.** 위 시나리오에서 포지션이 지워지면, *다음 재시도가 있었다면* ⓒ 가 `[sell_position_gone]` 으로 잡았을 것이다. 그런데 이 경로는 `place_order` 가 성공해 `:1642` 에서 `return` 하므로 **다음 재시도가 없다.** ⓒ 는 「실패 후 재시도」 축만 덮고 「**성공 후 오판**」 축은 덮지 않는다.

**그리고 ⓒ 가 이 결함을 부분적으로 가린다** — 두 가지 방식으로.

1. **문구가 가린다.** ⓒ 의 계약 문구 "발사 직전 재조회가 수량의 유일한 진실원" 을 읽으면 수량 축이 닫힌 것처럼 보인다. 실제로는 발사 **후** 두 번 다시 읽는다(`:1619`, `:1634`). 축 (b)가 이 어긋남을 닫는다.
2. **사고 조사를 가린다.** 창 2 가 터진 날에도 `[sell_position_gone]` 은 0건이므로, 그 마커를 "포지션 소멸 감시자" 로 믿고 보면 **아무 일 없었다고 읽힌다.** 실제 지문은 `:2143` WARNING 이고 그건 지금 아무도 안 본다.

**결론**: ⓒ 는 이 결함의 앞 단계가 아니라 **인접한 다른 축**이다. ⓒ 를 강화해도 이 창은 안 닫힌다 — 5.5 의 (a)가 있어야 닫힌다.

---

## 6. 장중 롤백 가능성 — 수단이 없다. 그러나 이 단계를 막을 근거는 아니다

- **파라미터 다이얼 없음.** 이 변경은 `DEFAULT_PARAMS` 키를 만들지도 읽지도 않는다.
- `src/engine/order_engine.py` 변경 → `BACKEND_RE` 첫 대안(`src/`) 히트 → **full 모드 = backend 재생성 = 재시작.**
- 보유 11종목 + D6(보유 중 09:00~15:30 push 금지) → **월요일 장중 롤백 불가.** 사용 가능한 창은 **15:30~16:00 · 21:35~익일 07:45 · 주말·공휴일**뿐이다(16:00~20:00 은 KRX 애프터마켓 실매매, 20:00~21:35 은 D8 금지).
- 즉 **월요일 아침에 문제가 드러나면 가장 이른 되돌림이 15:30**이다. 약 6시간 반 노출.

**그럼에도 다이얼을 새로 달자는 권고는 하지 않는다.** 예외 경계에 롤백 스위치를 다는 것은 곧 "경계를 끄는 길" 을 코드에 심는 것이고, 그 스위치가 켜지는 순간 cycle327 이 막은 재발사가 살아난다. cycle295 시장휴식 컷이 다이얼 없이 간 것과 같은 판단이고, 그쪽 정본도 "롤백 수단은 1커밋 revert + 장외 배포뿐" 으로 적혀 있다.

**대신 조건을 건다 — 이것이 내 관문 통과의 유일한 부대조건이다.**

> 이 커밋은 **일요일 중에 배포·실측까지 끝낸다.** 월요일 새벽에 배포하고 07:45 부팅을 맞으면, 문제가 났을 때 되돌릴 창이 15:30까지 없다.

진행 규약 §5 의 "월요일 07:45 가 가까워지면 되돌리고 중단" 을 **커밋 시각이 아니라 배포·실측 완료 시각 기준**으로 읽어야 한다는 뜻이다. 노출을 감수할 근거는 이 diff 가 주문 발사에 구조적으로 닿지 않는다는 2번의 결론이고, 그 결론이 틀렸을 경우의 유일한 방어선이 배포 전 검증이다.

---

## 7. 가장 위험한 한 가지 — **폴백 경로의 탈출 비대칭이 편집 지점에서 보이지 않게 됐다**

AST 로 뜬 위상이 근거다.

```
execute_sell:
  Try@1607-2058  handlers=[KisApiError, Exception]   ← main 헬퍼 호출(:1631)이 여기 안
    │                                                   새면 → 재시도 루프 → 재발사
    └ except KisApiError as e:
         Try@1936-2044  handlers=[KisApiError]        ← fallback 헬퍼 호출(:1959)이 여기 안
                                                         새면 → execute_sell 관통 → risk.on_tick
```

`except` 블록 안에서 난 예외는 **같은 try 의 형제 핸들러가 잡지 못한다.** 그래서 폴백에서 non-`KisApiError` 가 새면 `execute_sell` 을 통째로 뚫고 `risk.on_tick` 까지 올라가고, **그 틱의 다른 모든 보유 종목 손절 평가가 함께 사라진다.**

지금은 헬퍼의 `except Exception`(`:933`)이 둘 다 막는다. 위험한 것은 **피해의 비대칭이 코드에서 사라졌다**는 점이다.

- 전에는 폴백 블록을 고치는 사람 눈에 바로 위 `except KisApiError as fb_err:` 가 보였다. 지금 헬퍼에는 문맥이 없고 **docstring 이 유일한 전달자**다.
- 피해 크기가 다르다 — main 이 새면 **그 종목 중복 매도**(종목 1개), fallback 이 새면 **전 보유 종목의 그 틱 손절 정지**(현재 11종목). 자릿수가 다른 두 리스크를 `except Exception` 한 줄이 떠받친다.
- **제안된 AST 가드 ②는 예외 폭을 전혀 보지 않는다**(매핑↔헬퍼 `await` 순서 · 헬퍼 앞부분 `await` 0건). 현행 그물은 회귀 둘뿐이다 — `test_sell_does_not_refire_on_generic_insert_error`(일반 예외), 시나리오 I(`TimeoutError`). 따라서 **그 두 타입을 포함하되 다른 것을 빼는 좁히기**(예: `except (UniqueViolationError, TimeoutError, OSError):`)는 **초록으로 통과한다.**
- 더 나쁜 변종: 새는 예외가 우연히 `KisApiError` 면 폴백의 `except KisApiError as fb_err` 가 그걸 잡아 **"폴백도 거부" 로 오분류**한다 → `_selling.discard` + `register_market_order_disallowed(fallback_succeeded=False)` + NXT 시간대면 `_pending_next_day_clear` 등록. **거래소에 살아 있는 주문을 장부에 "거부" 로 적고 익일청산 큐에 넣는다.** 조용한 이중 청산 경로다.

**권고(채택은 team-leader 몫)** — 선행 의뢰 ②에 **조항 3** 을 더한다.

> `_persist_sell_pending_after_send` 본문의 최상위 `ast.Try` 는 핸들러가 정확히 1개이고 그 타입이 `Exception` 일 것.

AST 한 줄이고, M1·M2 돌연변이를 **타입 표본 둘에 기대는 그물**이 아니라 **구조**로 닫는다. 지금 이 항목이 이 단계에서 내가 가장 덜 확신하는 자리이고, 조항 3 이 들어오면 확신 수준이 나머지 여섯 답과 같아진다.

---

## 후속 과제 (이 관문의 산출물)

| # | 항목 | 성격 | 승인 |
|---|---|---|---|
| F1 | 헬퍼 최상위 `except Exception` 단일 핸들러 AST 봉인(조항 3) | 이 사이클에 동반 권고 | tests/ 만 — 불필요 |
| F2 | `:2143` WARNING 카운트 실측(SQL 1줄, 최근 30일, 매도 축) | **코드 변경 0** | 불필요 |
| F3 | 매핑 부재 전량 판정 금지(축 a) | 행위 변경 · 청산 규약 | 8영역 + **`domain-consult` 선행** |
| F4 | 발사 시점 `ordered_qty` 고정(축 b) | 행위 변경 소 · 계약 정합 | 8영역 |
| F5 | `logger.exception` 무방비 | **추가 작업 없음으로 종결**(질문 B 답변) | — |

F3·F4 는 **F2 의 결과에 따라** 즉시 착수 / 피라미딩 선결로 갈린다.

---

매매 행위 영향: 0
