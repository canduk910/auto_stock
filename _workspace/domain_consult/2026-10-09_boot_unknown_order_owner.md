# ⑦-F2 — 부팅 복구가 출처 모를 미체결 매수에 momentum 을 쓰는 우회

작성 2026-10-09 · domain-expert · 읽기 전용 분석(코드·DB·운영 서버 무접촉). 기준 HEAD `14e48038`.
선행 결정 = 09-27 #18 「부팅 복구가 출처 모를 주문에 momentum 을 쓰지 않고 기존 가드가 처리」.

## 질문 요약
1. 우회가 지금 열려 있나(줄 단위) 2. 초안(주문번호 해석 → 모르면 `_order_strategy` 비움)의 위험
3. 8영역 접촉 여부 + 회귀 시나리오 4. 진행/보류

## 트레이더 시각
- **계좌에 걸린 사람 주문은 운영자의 의도다.** 시스템이 할 일은 셋뿐 — 건드리지 않는다(취소 금지),
  전략 예산으로 잡지 않는다, 체결되면 손절은 걸고 크게 알린다. 지금 부팅 경로는 첫째를 어긴다.
- 서버가 돌고 있을 때 MTS 로 낸 매수는 이미 그렇게 처리된다(매핑 없음 → `qty_src=payload` →
  타이머 없음 → momentum 고아 귀속 + CRITICAL). **재시작 전후로 같은 주문이 다르게 처리되는 것**이 결함의 본질이다.

### 1. 우회는 실재한다 (매수 쪽만)
경로 — `src/engine/boot_manager.py`:
- `:428` 당일 BUY 를 **종목 기준**으로 `db_strategy_map` 에 넣는다(기본 `"momentum"`). 주문번호를 보지 않는다
- `:455` `strategy_id = db_strategy_map.get(ticker, "momentum")` · `:456` `registry.get(...) or registry.get("momentum")`
- `:458-461` 그 전략의 `pending_buys`·`pending_buy_amounts` 시드 · `:463` `_pending_buy_orders`
- `:469` `_order_qty[order_no] = ord_qty` · `:470` `_order_strategy[order_no] = strategy_id`

체결 쪽 — `src/engine/order_engine.py`:
- `:2637-2641` `order_no in _order_qty` → `qty_src="map"`
- `:2826` `_order_strategy.get(order_no)` 적중 → cycle331 귀속 단(`:2849`)을 **건너뛰고** `strategy_from_pending=False`
- `:3056` `if qty_src == "map" and not strategy_from_pending:` → `_schedule_cancel` → `:3483`
  `cancel_order(order_no, 0, cancel_all=True)` — **30초 뒤 사람 주문의 잔량 전부 취소**

성립 조건 = 장중 재시작 · 그 시점 체결 0 인 사람 매수 주문 · 그 종목을 어느 전략도 보유/주문 중이 아님 ·
재시작 뒤 **부분** 체결. 매수 타이머는 「취소」 만 하고 재주문은 하지 않는다.
- 덤: `:428` 이 종목 기준이라, 같은 날 전략 X 가 사고팔았던 종목에 사람이 새로 낸 주문은 **X 소유**가 된다.
- cycle329(타이머는 map 한정)·cycle331(발사 창 귀속이면 타이머 보류)은 **이 경로를 막지 못한다** —
  부팅이 바로 그 두 조건(map 출처 · 매핑 적중)을 손으로 채워 주기 때문이다. cycle385 는 매도 축이라 무관.
- **매도 쪽은 열려 있지 않다.** 부팅은 매도 미체결을 복구하지 않는다(`:443` `sll_buy_dvsn_cd != "02"` 건너뜀)
  → 사람 매도 통보는 `payload` → `:3380` 게이트로 재주문 없음(`[fill_partial_no_reorder]`).
- 빈도: 09-26 S2 실측 15회 부팅 복구 0건. **실재하지만 잠복** — 급하지 않다.

### 2. 초안의 위험
초안 = `_order_strategy` 만 비우고 pending·`_order_qty` 는 유지.
- **타이머**: 첫 통보는 `_lookup_strategy_from_trade_history` miss → `_resolve_pending_buy_owner` 가 부팅이 시드한
  전략을 돌려줌 → `strategy_from_pending=True` → 타이머 보류. 첫 통보는 닫힌다.
- **소유**: 그 「시드한 전략」 이 `:455-456` 의 momentum 이다. 초안은 결정 #18 을 **이름만** 지킨다 — momentum 이
  `_order_strategy` 대신 `pending_buys` 를 통해 그대로 주인이 된다. **결정 문구와 충돌.**
- **두 번째 부분체결이 버려진다(초안이 새로 여는 구멍)**: 첫 통보가 포지션을 세우고 `pending_buys` 를 지운다 →
  두 번째 통보는 매핑 miss · 장부 miss(사람 주문엔 PENDING 행 없음) · pending 0 → `:2864` 보유 중이라
  `[buy_fill_fallback_held_conflict]` ERROR 후 `return`. 포지션 수량이 첫 체결분에 멈춘다 = **추적 밖 실보유**
  (cycle385 불변식 위반) → 손절이 일부 수량만 판다. 지금 코드는 momentum 매핑 덕에 수량은 맞게 따라간다.
  ⚠️ 이 구멍은 런타임 MTS 주문·발사 창 주문에도 이미 있다 = 계획의 **J-4**(구멍 C, `pos.order_no==order_no` 정확 일치 귀속).
- **예산 장부**: 시드 전략(momentum, 비중 0.03 ≈ 14만 원)의 `pending_buy_amounts` 에 사람 주문 금액이 잡힌다 →
  momentum 잔여가 음수로 눌려 체결·취소 확인(⑨A `buying_reconcile`) 때까지 momentum 매수 0. 작지만 오귀인.
- **손절**: 귀속 전략이 켜져 있으면 걸린다. momentum 은 지금 비중 0.03 으로 켜져 있다. 🔴 momentum 을 비중 0 으로
  퇴출하는 날 「주인 모를 = momentum」 폴백 전부(이 경로 포함)가 **손절 정지 보유**를 만든다(카드 #11 소관).

## 정량 권고 — 3안

| | 안1 초안 | 안2 맵 둘 다 비움 + 시드 유지 | **안3 미상은 아무것도 시드 안 함 (권고)** |
|---|---|---|---|
| 해석 순서(공통) | 주문번호 → `trade_history` PENDING/PARTIAL(`_lookup_strategy_from_trade_history` 재사용) → `llm_buy_evaluations(trade_date,ticker,order_no).strategy_id` → 미상. **종목 기준 당일 BUY 는 근거에서 뺀다** | 같음 | 같음 |
| 해석됨 | 현행대로 전부 등록(타이머 정상) | 같음 | 같음 |
| 미상 `_order_strategy`/`_order_qty` | 비움 / 유지 | 비움 / **비움** | 비움 / 비움 |
| 미상 pending·`_pending_buy_orders` | momentum 시드 | momentum 시드 | **없음** |
| 타이머 | 첫 통보만 보류 | 이중 보류(`qty_src≠map`) | 이중 보류 |
| 결정 #18 문구 | 충돌 | 충돌 | **일치** |
| 런타임 MTS 주문과 | 다름 | 다름(CRITICAL 없음) | **동일**(고아 귀속 + CRITICAL) |
| 같은 종목 중복 매수 차단 | 있음 | 있음 | 없음(런타임 MTS 도 없음) |
| 두 번째 부분체결 | 버려짐 | 버려짐 | 버려짐 — 셋 다 J-4 가 닫는다 |

근거:
- 종목 기준 당일 BUY 를 빼는 이유 — 주문번호가 다른 행은 「다른 주문」의 증거다. sync(`scheduler._sync_orders_to_db`)가
  momentum 폴백으로 쓴 COMPLETED 행도 근거에서 빠지도록 PENDING/PARTIAL 만 본다(폴백 세탁 차단).
- `_order_qty` 를 비우는 이유 — 타이머가 귀속 경로(pending 유일성)와 무관하게 `qty_src` 로 닫힌다. 나중에 J-4 가
  두 번째 체결을 같은 포지션에 붙여도 `map` 이 아니므로 타이머가 다시 열리지 않는다. 체결통보 `fields[16]` 이 비면
  `increment` 로 떨어져 첫 체결을 전량으로 읽지만, 그 결과는 「버려짐」 과 같고 타이머는 여전히 없다.
- 안3 을 권고하는 이유 — 사람 주문 처리 규칙이 하나가 된다. 체결되면 momentum 고아 귀속 + `[buy_fill_fallback_orphan]`
  CRITICAL 로 운영자가 바로 안다. 예산 오귀인 0.
- 안2 를 남기는 이유 — 「우리 주문인데 증거가 둘 다 없는」 경우(PENDING INSERT 실패 + LLM 행 없음 + 체결 전 재시작)에
  같은 전략이 같은 종목을 다시 사는 이중 랏을 막는다. 발생 확률은 매우 낮다.
- **DB 조회 예외 = 미상**으로 처리한다(실패 방향 = 타이머 없음). 우리 주문이면 잃는 것은 30초 잔량 취소 하나다 —
  잔량은 우리가 산정한 수량 안이라 예산 위반이 아니고, KRX 정규장 마감 자동취소가 회수한다.

## 현 코드와의 정합성
- **고칠 자리 = `boot_manager.py` 만**(`:418-472`). `order_engine.py`(8영역)·`scheduler.py` 무접촉 — 기존 가드
  (`:2829` 장부 조회 · `:2849` cycle331 · `:2864` B-2 · `:2876` B-3 · `:3056` 타이머 게이트)를 그대로 쓴다.
- 함께 바꿀 것: `:428`·`:433` 의 종목 기준 맵은 `sold_today` 시드 용도로는 유지해도 된다(재매수 차단, 소유 무관).
  미체결 복구 루프만 주문번호 해석으로 바꾼다.
- 카드 #11 1단계(`FALLBACK_OWNER_ID` 명명, 행위 0)와 ⑦ 관측(`[boot_recover_strategy_unknown] path=unfilled_order`)이
  먼저 착지하면 diff 가 작아진다. `_SRC_TREE_DIGEST` 재핀 · 영향 인덱스 재생성 동반.
- 매매 행위 변경이므로 **사용자 승인**이 필요하다. 결정 #18 은 방향 승인이고 안2/안3 선택은 남는다.

## 반례 / 한계
- 안3 에서 재시작 뒤 우리 전략이 같은 종목을 새로 주문하면, 사람 주문 체결이 cycle331 로 **우리 전략에** 붙고
  이어 우리 체결이 `pos.quantity = total_filled` 로 수량을 덮는다. 연쇄 확률은 낮지만 장부가 틀어진다.
- 재시작 **전** 부분체결된 사람 주문은 이 루프에 오지 않는다(F1 잔고 보완이 보유로 세우고 `:452` 가 건너뜀).
  잔량 체결은 `:2864` 에서 버려진다 — F1(보류)·J-4 소관.
- `llm_buy_evaluations` 는 AI 매수평가가 켜진 주문에만 행이 있다. 두 번째 근거일 뿐이다.
- 사람 보유를 momentum 청산 규약(익일 시가 청산 등)이 관리하는 것 자체는 그대로다 — F1 의 「수동 보유를 자동 관리할지」 질문.

## 후속 검증 권고 (tdd-engineer → tester)
주인 {사람 MTS · 우리(장부 odno 일치) · 우리(장부 없음·LLM 행) · 미상} × 방향 {매수 · 매도} × 시점.
1. 사람 매수, 체결 0 → 재시작 → 부분 통보(payload 10, 체결 3): `_schedule_cancel` 0회 · `[buy_partial_no_cancel_timer]` ·
   (안3) CRITICAL 1행·momentum 포지션 3주 · pending/`pending_buy_amounts` 어느 전략에도 없음
2. 1 에 이어 잔량 통보 7: 현행 핀(`held_conflict` ERROR, 수량 3) — J-4 착지 때 10 으로 뒤집히는 자리라고 주석
3. 사람 매수 1회 전량 통보: 포지션 1·타이머 0·장부 COMPLETED INSERT 1
4. 우리 매수(장부 PENDING odno 일치, kojiro) → 재시작 → 부분: 전략 kojiro · 타이머 1회 · `_order_qty` 등록
5. 우리 매수, 장부 없음·LLM 행 kojiro → 해석 kojiro · 타이머 1회
6. 같은 종목 당일 전략 X 의 매수·매도 이력 + 다른 odno 의 사람 주문 → **미상**(현행은 X) — 종목 기준 귀속 차단 핀
7. 장부에 같은 odno 의 COMPLETED(sync 폴백 momentum) 행만 → 근거 불채택
8. 장부·LLM 조회 예외 → 미상 처리, 부팅 계속, 맵 0
9. 재시작 전 부분체결 사람 주문(보유 복구됨) → 루프 건너뜀(현행 핀)
10. 매도 미체결 재시작 → 부팅 시드 0 · 부분 통보 → 재주문 0(현행 핀, `[fill_partial_no_reorder]`)
11. AST: 미체결 복구 루프 안에 리터럴 `"momentum"`·`registry.get("momentum")` 0
12. (안2 선택 시) 사람 주문 취소 → `buying_reconcile` 이 시드 해제
돌연변이: `:470` 를 되살리면 1 이 붉어지는지, 해석 순서에서 장부 단을 빼면 4 가 붉어지는지.

## 결론
- 우회 실재: **예**(매수만, 잠복 — 15회 부팅 복구 0). 매도 쪽은 닫혀 있다.
- 권고: **진행** — 계획 순서대로(카드 #11 1단계 → ⑦ 관측 → ⑦-F2), 긴급 아님. 방식은 **안3**(대안 안2). 초안(안1)은 비권고.
- 고칠 자리: `boot_manager.py` 만, **8영역 무접촉**. 두 번째 부분체결 구멍은 J-4(8영역, 계획에 있음)가 닫는다.
