# J-4 — 매수 두 번째 부분 체결의 정확 일치 귀속

작성 2026-10-10(토) 18시 KST · domain-expert · 자문 메모(코드 변경 없음)
요청 = 묶음 D ⑥행(`_workspace/red/bundle_D_plan.md`) · cycle427 알려진 한계(`src/engine/CLAUDE.md` boot_manager 절) · 카드 E(cycle436) 맞물림

## 질문 요약

1. 운영 로그에 `[buy_fill_fallback_held_conflict]` 가 몇 건이고, 같은 주문번호의 `[buy_fill_strategy_from_pending]` 이 앞선 것(구멍 C 서명)은 몇 건인가.
2. 두 번째 부분 체결이 버려지는 경로 전부, 그리고 `pos.order_no == order_no` 정확 일치로 귀속할 때의 안전 조건.
3. (a) 평균단가·`high_since_buy`·터틀 `_entry_atr`·kojiro 스탬프 (b) 부팅 복구 포지션(`order_no=""`) 뒤 같은 주문 잔량 체결 (c) 카드 E `(ticker, order_no)` 예약과의 맞물림 (d) 회귀 시나리오 표.

---

## 1. 운영 판독 (읽기만 함 — 2026-10-10 18:09 KST)

### 1.1 EC2 파일 로그 `~/auto_stock/logs/auto_stock.log*`

보존 = 2026-09-19 ~ 2026-10-10(09-14~09-18 은 이미 지워졌다). 거래일 11일(09-21·22·23·28·29·30·10-01·02·06·07·08). 09-24·25, 10-05, 10-09 는 휴장, 10-08 은 매수 0건.

| 마커 | 11거래일 합 | 비고 |
|---|---|---|
| `[buy_fill_fallback_held_conflict]` | **0** | 파일 전부 0 |
| `[buy_fill_strategy_from_pending]` | 4 | 09-23 ×2 · 09-28 ×1 · 09-30 ×1 |
| └ 그중 부분 체결(`filled_total < ordered`) | **0** | 4건 모두 `incr == ordered` — 한 통보로 전량 체결(1주·9주·12주·9주) |
| `[buy_partial_no_cancel_timer]` | 0 | 발사 창 부분 체결이 한 번도 없었다는 뜻 |
| `[buy_fill_fallback_orphan]` · `[buy_fill_strategy_lookup_fallback]` | 0 · 0 | |
| `[boot_recover_strategy_unknown] path=unfilled_order` | 0 | cycle427 은 10-10 배포라 아직 표본 없음 |
| 매수 주문 접수 / 포지션 등록 / 전량 체결 | 72 / 72 / 72 | 세 숫자가 날마다 일치 |
| **매수 부분 체결** | **0** | 72건 모두 체결통보 1건으로 끝났다(주문번호별 `[fill_qty_src] side=BUY` 집계로 확인) |

### 1.2 `system_logs`(WARNING 이상, 보존 시작 2026-09-09) · `trade_history` — SELECT 만

- `system_logs`: `held_conflict` **0** · `from_pending` 4 · `orphan` 0 · `buy_partial_no_cancel_timer` 0. 사건 2건(08-26 078930 · 08-31 161890, cycle331 자문)은 보존 구간보다 앞이라 여기에 안 잡힌다. 둘 다 cycle331 이 고친 1주 전량 체결이었다.
- `trade_history` BUY(08-20 이후): COMPLETED 169(2주 이상 70) · PENDING 1(09-15) · **PARTIAL 0**.

### 1.3 판독 결론

- **구멍 C 서명(같은 주문번호에서 `from_pending` 다음 `held_conflict`)은 0건이다.** 구멍 C 가 생기려면 (발사 창에 첫 체결이 들어옴, 4/72 = 5.6%) × (부분 체결, 0/72 — 3의 법칙으로 95% 상한 약 4%) × (두 번째 통보도 창 안에 들어옴)이 다 겹쳐야 한다. 지금 랏 크기(1~12주, 시장가)에서는 사실상 일어나지 않는다.
- 이 수치는 「지난 11거래일에 없었다」는 뜻이지 「일어날 수 없다」는 뜻이 아니다. 랏이 커지거나(입금·비중 확대), 호가가 얇은 종목이거나, 프리장 지정가(GTP)로 사면 부분 체결 확률이 오른다.
- 그래서 J-4 는 **급하지 않은 장부 정합 작업**이다. 묶음 D 의 대기 조건(「0건이고 E 도 보류면 더 미룬다」)에서 E 는 진행 중이므로, 사용자 결정(10-10 저녁 「카드 E+J-4 지금 진행」)대로 E 와 같은 주에 착지하는 것은 문제없다. 다만 회귀 위험을 키우면서까지 범위를 넓힐 이유는 없다.

---

## 2. 트레이더 시각

### 시장 가설
- 우리 체결 하나는 「이 전략이 이 가격대에서 이만큼 사겠다고 한 결정」의 일부다. 같은 주문번호의 체결은 **결정이 하나, 포지션도 하나**다. 그래서 두 번째 체결을 버리면 장부는 3주인데 계좌는 10주인 상태가 된다. 손절은 3주만 던지고, 남은 7주는 **손절선 없는 재고**가 된다. 루트 불변식 「추적 밖 실보유 0」을 정면으로 어긴다.
- 반대로 주문번호가 다른 체결은 **다른 결정**이다. 사람이 MTS 로 낸 것이든, 출처를 모르는 것이든, 다른 전략이 든 것이든 같은 포지션에 합치면 안 된다. B-2 가드가 지키는 선이 이것이고, 이번 자문에서도 그대로 둔다.

### 두 번째 체결이 버려지는 경로 (코드 판독, `src/engine/order_engine.py`)

| # | 경로 | 어떻게 버려지나 | J-4 정확 일치로 막히나 |
|---|---|---|---|
| C1 | **발사 창 연속 부분 체결**(구멍 C) | 1차 통보: 매핑 miss → `trade_history` miss → `_resolve_pending_buy_owner` 적중 → 포지션 등록, 그 자리에서 `pending_buys.discard`. 2차 통보(아직 `place_order` 응답 전): 매핑 miss → `trade_history` miss → pending 단은 `pending_buys` 가 비었고 그 전략이 보유 중이라 `None` → `is_ticker_held_by_any` 참 → `held_conflict` 후 return | **막힌다** — 1차가 `order_no=order_no` 로 등록했다 |
| C2 | **부팅 뒤 출처 모를 주문의 분할 체결**(cycle427 한계) | 1차: 고아 폴백으로 momentum + `[buy_fill_fallback_orphan]` CRITICAL, `order_no=order_no` 등록. 2차: 매핑·`trade_history`·pending 전부 miss → `held_conflict` 후 return | **막힌다** |
| C3 | 부팅 전 일부 체결된 주문의 잔량 + 그 주문 행이 부팅 때 COMPLETED 로 바뀜 | KIS 잔고 보완 복구가 `order_no=""` 로 포지션을 만든다 → 미체결 복구 루프는 보유 중이라 건너뛴다 → 부팅의 `mark_pending_buys_completed` 가 PENDING 행을 COMPLETED 로 바꿔 `_lookup_strategy_from_trade_history`(PENDING/PARTIAL 만 봄) miss → `held_conflict` | **안 막힌다**(`order_no=""`) — §4(b) |
| C4 | **같은 조건인데 행이 PARTIAL 로 남은 경우** | 조회가 전략 S 를 찾아 `pos` 가 있는 「추가 체결」 분기로 간다 → `pos.quantity = total_filled` 인데 `_filled_qty` 가 재시작으로 0 에서 다시 셌으므로 **잔량만큼으로 덮어써 수량이 줄어든다**(예: 3주 보유 + 잔량 1주 체결 → 1주) | 버려지는 게 아니라 **수량이 줄어드는 기존 결함**. J-4 와 별개 — §4(b) |
| C5 | 매핑·payload 둘 다 없는 통보(`qty_src="increment"`) | 1차가 `ordered=quantity` 라 전량으로 읽혀 `_completed_buy_orders` 에 들어가고, 2차는 B-1 멱등 가드(`[buy_fill_duplicate_ignored]`)에서 버려진다 | **J-4 지점에 오지 않는다**. KIS 가 ODER_QTY 를 늘 실어 주므로 실제로는 거의 없다. 범위 밖 |

---

## 3. 정량 권고 — 정확 일치 귀속의 안전 조건

### 3.1 자리
`_handle_buy_fill` 의 `strategy_id is None`(매핑 miss → `trade_history` miss) 블록에서 **pending 단(cycle331) 바로 뒤 · B-2 가드 바로 앞**에 `elif` 하나를 넣는다. 고아 폴백(momentum)은 「아무도 안 들고 있음」이 조건이라 정확 일치(=누가 들고 있음)와 겹치지 않는다.

### 3.2 채택 조건 — 전부 만족해야 한다

| # | 조건 | 왜 |
|---|---|---|
| E1 | 매핑 miss ∧ `trade_history` miss ∧ pending 단 `None` | 지금 B-2 로 떨어지는 통보만 대상으로 한다. **결과 집합 ⊆ 현행 B-2 집합**이어야 B-2 를 느슨하게 하지 않는 것이다 |
| E2 | 레지스트리 전체에서 `positions[ticker].order_no == order_no` 이고 `order_no` 가 비어 있지 않은 전략이 **정확히 1개** | 0개면 B-2. 2개 이상은 실재할 수 없는 상태라 물러선다(fail-open = 현행) |
| E3 | **이 프로세스가 같은 주문의 앞선 체결을 이미 셌다** — `prev_total = self._filled_qty.get(order_no, 0)` (이번 증분을 더하기 **전** 값) `> 0` | 🔴 핵심 조건. KIS 주문번호는 **날마다 다시 매긴다**. DB 에서 복구한 스윙 포지션은 며칠 전 주문번호를 들고 있으므로, 오늘 사람이 같은 종목을 낸 주문번호가 우연히 같으면 E2 만으로는 남의 주문을 우리 포지션에 합친다. 재시작 뒤 같은 주문의 중복 통보도 같다. `prev_total > 0` 이면 「오늘, 이 프로세스에서, 이 주문의 앞선 체결로 그 포지션을 만들었다」가 성립한다 |
| E4 | `handle_execution_notice` 판정 순서와 예외 규약 유지 — in-memory · `await` 0 · never-raise. 판정 중 예외는 `None`(→ B-2) | 체결통보 콜백 예외는 `realtime/handler.py` 규약상 WS 재연결을 부른다 |

`pos.quantity == prev_total` 은 조건에 넣지 **않는다**. 넣으면 두 체결 사이에 사람이 일부를 팔았을 때(cycle385 분할 매도 허용) 두 번째 체결을 다시 버린다. 대신 수량을 증분으로 더한다(§4(a)).

### 3.3 채택했을 때 하는 일

- `strategy_id = 그 전략`, 플래그 `strategy_from_exact = True`.
- 관측 = `[buy_fill_exact_order_match] order_no= ticker= strategy= qty_src= incr= filled_total= ordered= prev_qty=` **무cap WARNING**. `from_pending` 과 같은 이유다 — 건마다 조사할 단위이고, WARNING 이상이어야 21:30 `top_patterns` 에 오른다.
- **잔량 취소 타이머는 걸지 않는다** — 조건을 `qty_src == "map" and not strategy_from_pending and not strategy_from_exact` 로 넓힌다. 우리 주문이면 곧 매핑이 서고, 다음 통보가 `src=map` 으로 와서 정상적으로 타이머를 건다. C2(사람 주문일 수 있음)에서는 **사람 주문을 30초 뒤 취소하는 사고**를 원천 차단한다(cycle327·329·331 계열 금기).
- `fill_count_today` 는 올리지 않는다(같은 주문 = 같은 진입). 고아 CRITICAL 도 다시 내지 않는다(첫 체결 때 이미 냈다).
- `trade_history`·`save_position`·매핑 정리·`_completed_buy_orders` 는 기존 전량/부분 분기를 그대로 탄다. C1 의 전량 완결이면 `affected == 0` → `_completed_orders.add` + COMPLETED 직접 INSERT → `execute_buy` 의 PENDING INSERT 가 race 가드로 흡수된다(cycle331 R1 과 같은 길, 09-23·09-28 실측에서 이미 돈 길).

### 3.4 B-2 가 계속 막는 것 (변경 0)

- 다른 주문번호(사람 주문·다른 날 주문번호) → E2 불성립.
- 같은 주문번호지만 이 프로세스가 앞선 체결을 본 적 없음(재시작 직후·다른 날 번호 충돌) → E3 불성립.
- 다른 전략이 그 종목을 보유 → E2 불성립(그 포지션의 `order_no` 는 그 전략 주문).
- `order_no=""` 부팅 복구 포지션 → E2 불성립(§4(b)).

---

## 4. 질문별 답

### (a) 평균단가 · `high_since_buy` · `_entry_atr` · kojiro 스탬프

| 항목 | 권고 | 근거 |
|---|---|---|
| **수량** | `pos.quantity += quantity`(overrun 클램프 뒤의 유효 증분) | 사이에 아무 일도 없으면 `total_filled` 와 같다. 사람이 그 사이 일부를 팔았으면(cycle385 보유 축이 `pos.quantity` 를 깎았다) 덮어쓰기는 **판 것을 되살려** 다음 매도가 APBK0400(잔고부족)으로 간다. 증분이 틀릴 수 없는 쪽이다 |
| **평균단가 `buy_price`** | **map 경로와 같은 규약 = 마지막 체결가로 덮는다**(`pos.buy_price = price`). VWAP 로 바꾸지 않는다 | 한 주문의 세 번째 통보가 map 경로로 오면 어차피 마지막 체결가로 덮인다. J-4 만 VWAP 로 하면 같은 주문 안에서 규약이 갈린다. 시장가 매수의 마지막 체결가는 VWAP 이상이라 손절선이 약간 **위**에 서고(조금 일찍 나간다 = 보수 방향), 우리 랏(1~12주, 부분 체결 0/72)에서 차이는 무시할 수준이다. VWAP 통일은 모든 경로를 같이 바꾸는 별도 결정이다(재시작하면 KIS 평균가로 복구되므로 그때만 값이 VWAP 로 튄다 — 기존 동작) |
| `high_since_buy` | **손대지 않는다** | 첫 체결 때 `__post_init__` 이 매수가로 세웠고, 그 뒤는 `on_tick` 이 최고가로만 올린다. 두 번째 체결이 더 비싸도 그 사이 틱이 이미 그 가격을 지나갔다 |
| 터틀 `_entry_atr` | **손대지 않는다**(첫 스탬프 유지) | 스탬프는 체결이 아니라 **사이징 시점**(`calc_buy_quantity` — donchian `:1965` · BFB `:1480/:1514` · VCP `:1800/:1834`)에 종목 키로 찍힌다. 같은 주문 = 같은 사이징 ATR 이라 커플링 불변식(「스탬프 값 = sizing 에 쓴 ATR」)이 그대로 맞다. C2(momentum 고아)에는 스탬프가 없고 고정 % 손절이다 — 지금과 같다 |
| kojiro `_position_atr`·`_position_sectors` | **손대지 않는다** | 신호 시점(`kojiro.py:1038~1046`)에 종목 키로 찍힌다. 오픈 리스크 합(`max_open_risk_pct`)은 수량이 늘어난 만큼 커지는데, 그게 원래 설계한 랏이다 |
| `save_position`(전량 분기) | `quantity=state.positions[ticker].quantity` · `buy_price=state.positions[ticker].buy_price` 로 읽게 한다 | 기존 경로에서는 `pos.quantity == total_filled`, `pos.buy_price == price` 라 **바이트 동일**하다. J-4 에서 사이에 매도가 있었을 때만 값이 달라지고, 그때 맞는 쪽이 `pos` 다 |

### (b) 부팅 복구 포지션(`order_no=""`) 뒤 같은 주문의 잔량 체결

- **J-4 는 `""` 를 맞추지 않는다**(E2·E3 둘 다 불성립). 재시작 뒤에는 이 프로세스가 앞선 체결을 본 적이 없으므로, 「같은 주문이다」의 증거가 메모리에 없다. 그 증거 없이 합치면 사람 주문을 우리 포지션에 섞는 길이 열린다.
- 그 결과 두 갈래가 남는다(§2 표 C3·C4).
  - **C3(행이 COMPLETED 로 바뀐 경우) → 지금처럼 `held_conflict`**, 잔량은 추적 밖. 다음 영업일 부팅 잔고 복구가 맞춘다. 장중에는 cycle433 의 15분 관측이 주문이 끝난 뒤 수량 차이를 알린다(주문이 열려 있는 동안은 「진행 중」이라 조용하다).
  - **C4(행이 PARTIAL 로 남은 경우) → 기존 「추가 체결」 분기의 덮어쓰기 때문에 수량이 줄어든다.** 이번 판독으로 찾은 **기존 결함**이다. J-4 가 만든 것도, J-4 가 고치는 것도 아니다.
- 발생 조건 = 「장중 재시작」 ∧ 「그 순간 일부만 체결된 매수 주문이 열려 있음」. 보유 중 장중 push 는 금지(D6)이고, 매수 부분 체결은 0/72 라 지금 실측 빈도는 사실상 0 이다.
- 고치는 길은 둘이다(사용자 결정 ②).
  - **B-i(작음, 8영역, J-4 와 같은 함수)** — 「추가 체결」 분기에서 `pos.order_no != order_no`(=`""` 포함)이면 덮어쓰기 대신 `pos.quantity += quantity` + 가중평균 단가로 합친다. C4 만 고친다. C3 은 그대로 남는다. 같은 주문번호(`==`)의 기존 경로는 바이트 동일하다.
  - **B-ii(부팅 쪽, 8영역 아님)** — 미체결 복구 루프가 「보유 중이라 건너뜀」 대신, 주문번호로 주인을 찾았고(`_resolve_unfilled_buy_owner`) 그 주인이 그 종목의 보유자와 같으면 매핑을 등록하고 `_filled_qty[odno] = tot_ccld_qty`(KIS 주문내역의 이미 체결된 수량)로 시드한다. C3·C4 둘 다 고치고, 잔량 통보가 `src=map` 으로 와서 타이머도 정상으로 선다. 대신 부팅 경로 회귀 범위가 B-i 보다 넓다.
  - 권고 = **J-4 에는 넣지 않고 워크리스트 후속으로 적는다.** 빈도가 0 이고, B-i 는 J-4 의 8영역 커밋을 불리며, B-ii 는 별도 사이클 크기다. 넣는다면 B-i 를 J-4 와 같은 커밋에 넣는 것이 8영역 sha 재핀 비용 면에서 가장 싸다.

### (c) 카드 E `(ticker, order_no)` 예약과의 맞물림

- **J-4 는 예약 코드를 따로 갖지 않는다.** 귀속이 정해진 뒤 모든 체결 경로(map · `trade_history` 복구 · pending 단 · 정확 일치)가 지나는 **공통 후처리 한 곳**(지금 `state.pending_buys.discard` + `pending_buy_amounts.pop` 두 줄 자리)만 쓴다. 카드 E 의 「예약 한 곳」이 그 자리를 대신하면 J-4 는 자동으로 따라간다.
- 🔴 **카드 E 가 반드시 지켜야 할 맞물림 하나 — 발사 창의 키 갈아끼우기.** 예약은 `place_order` **앞**에서 걸어야 한다(A-ATOMIC — `calc_buy_quantity`↔`pending_buys.add` 사이 `await` 0). 그때는 주문번호가 없으므로 임시 키로 걸었다가 응답 뒤 `(ticker, order_no)` 로 바꾸게 된다. 그런데 C1(구멍 C)과 cycle331 R1(창 안 전량 체결)은 **응답보다 체결이 먼저** 온다.
  - 창 안 체결은 주문번호를 알지만 예약은 아직 임시 키에 있다 → 공통 후처리는 「그 전략·그 종목의 임시 예약」을 찾아 줄이거나 지워야 한다(그 전략의 그 종목 임시 예약은 최대 1개다 — `execute_buy` 가 `pending_buys` 로 같은 종목 재진입을 막는다).
  - 응답 뒤 키를 바꿀 때 `order_no in _completed_buy_orders`(창 안 전량 체결)면 **예약을 되살리지 않는다**. `order_no in _filled_qty`(창 안 부분 체결)면 남은 양으로만 되살린다. 이 검사가 없으면 이미 산 금액이 포지션과 예약에 **이중으로 잡혀** 그 전략 예산이 21:30 까지 줄어든 채 남는다(실측상 하루 0~2건 창 체결 → 하루 1랏 분량의 유령 예약). 지금 종목 키 구조는 창 안 체결이 예약을 지우고 응답 뒤에 다시 넣지 않아서 이 문제가 없다. 카드 E 로 **새로 생길 수 있는 회귀**다.
- **「체결분만큼 예약 감소」** — 두 안.

| 안 | 동작 | 장 | 단 |
|---|---|---|---|
| 현행 유지 | 그 주문의 첫 체결에서 예약 전체를 지운다 | 단순, 카드 E 를 키 바꾸기만으로 끝낼 수 있다 | 미체결 잔량은 KIS 가 이미 묶은 돈인데 우리 예산에서 사라진다. 부분 체결 0/72 라 실제 피해는 0 에 가깝다 |
| 감소 | 예약 = `주문가 × (주문수량 − 누적체결)`. 전량·취소 확인·거부·21:30 리셋 때 지운다 | 「포지션(체결분) + 예약(잔량) = 주문 전체」가 늘 맞는다. cycle335 원칙(「접수된 매수는 이미 묶인 자금」)과 같은 방향이다 | 지울 자리(취소 확인·거부)를 빠짐없이 묶어야 한다. 하나라도 빠지면 유령 예약이 21:30 까지 남는다(매수가 덜 되는 방향이라 안전 쪽 실패) |

  권고 = **카드 E 는 현행 유지(키만 바꾼다), 감소는 하지 않는다.** 부분 체결 실측 0, 카드 E 의 선결 이유였던 피라미딩은 cycle372 에서 닫혔다. 감소 안은 지울 자리를 전부 찾는 일이 커서 「일을 벌이지 말 것」 원칙과 맞지 않는다. 사용자 결정 ③.
- `pending_buys`(종목 집합)는 카드 E 뒤에도 같은 종목에 열린 주문이 하나뿐인 지금 구조에서는 그대로 맞다. 한 종목에 여러 주문을 동시에 열게 되는 날(피라미딩)에는 「그 종목 예약이 남아 있지 않을 때만 discard」로 바꿔야 한다 — 지금은 해당 없음.

### (d) 회귀 시나리오 표

공통 전제: 매핑 5종 miss, `trade_history` miss(행 없음 또는 COMPLETED), `qty_src="payload"`, 별도 표시 없으면 오늘·같은 프로세스.

| # | 상황 | 기대 결과 |
|---|---|---|
| J4-1 | C1: VB `pending_buys={t}` · 1차 3/10 → pending 단 등록 → 2차 4/10(창 안) | VB `positions[t].quantity == 7`, `order_no` 유지, `[buy_fill_exact_order_match]` 1행, `held_conflict` 0, 취소 타이머 미등록(`[buy_partial_no_cancel_timer]`), `fill_count_today` 1 그대로 |
| J4-2 | C1 전량: 1차 3/10, 2차 7/10(창 안) | 전량 분기 — COMPLETED 직접 INSERT + `_completed_orders` 등록, `save_position(quantity=10)`, `_completed_buy_orders` 에 추가, 이어지는 `execute_buy` PENDING INSERT 흡수(행 1개) |
| J4-3 | J4-2 뒤 응답 도착 → 카드 E 키 바꾸기 | 그 주문의 예약이 **남지 않는다**(`pending_buy_amounts` 에 `(t, order_no)` 없음), `_calc_used_funds` = 포지션 금액만 |
| J4-4 | J4-1 뒤 응답 도착 → 3차 3/10 이 `src=map` 으로 | 기존 map 경로 — `quantity == 10`, 그때 타이머 정상(전량이라 해제), 행 COMPLETED |
| J4-5 | C2: 부팅 뒤 미상 주문 1차 2/5 → momentum 고아 등록(CRITICAL 1) → 2차 3/5 | momentum `quantity == 5`, CRITICAL 추가 0, 타이머 **한 번도** 안 걸림(사람 주문 취소 0) |
| J4-6 | B-2 유지: momentum 이 주문 A 로 보유(오늘·이 프로세스), 미상 주문 B 통보 | `held_conflict` 1행 + return, 포지션 무변경 |
| J4-7 | B-2 유지: kojiro 가 DB 복구 스윙 포지션(`order_no="0000338400"`, 며칠 전), 오늘 같은 종목·같은 번호의 사람 주문 통보 | E3 불성립(`prev_total == 0`) → `held_conflict`, 포지션 무변경 |
| J4-8 | B-2 유지: 재시작 직후 오늘 전량 체결된 주문(DB 복구, `order_no` 일치)의 중복 통보 | E3 불성립 → `held_conflict`, 수량 무변경(덮어쓰기로 줄지 않는다) |
| J4-9 | B-2 유지: 다른 전략이 보유, 그 포지션 `order_no` 는 그 전략 주문 | E2 불성립 → `held_conflict` |
| J4-10 | E2 0개: `order_no=""` KIS 잔고 복구 포지션 + 잔량 통보(C3) | 현행 그대로 `held_conflict`(알려진 한계로 문서화) |
| J4-11 | C4: PARTIAL 행 조회 적중 + `pos.order_no == ""` | 현행 = 덮어쓰기로 수량 감소(**기존 결함 재현 테스트로 고정**). B-i 채택 시 = `k + r`, 가중평균 단가, `save_position` 이 `pos.quantity` |
| J4-12 | 사이 매도: J4-5 에서 1차 뒤 사람이 1주 매도(보유 축이 2→1) → 2차 3/5 | `quantity == 4`(증분). 덮어쓰기였다면 5 → 다음 매도 APBK0400 |
| J4-13 | 판정 예외: 레지스트리 순회 중 예외 주입 | `None` → `held_conflict`, 예외가 `handle_execution_notice` 밖으로 안 나감 |
| J4-14 | E2 2개(인위 주입): 두 전략이 같은 `order_no` 포지션 | 물러섬 → `held_conflict` |
| J4-15 | 구조 검사(AST) | 정확 일치 `elif` 가 pending 단 **뒤**·B-2 **앞**에 있고, 타이머 조건에 `strategy_from_exact` 가 들어 있고, B-2 `return` 이 남아 있다 |

---

## 5. 현 코드와의 정합성

- **충돌 없음 — B-2 는 느슨해지지 않는다.** 정확 일치가 받는 통보 ⊂ 지금 B-2 가 버리는 통보이고, 그중 「같은 주문번호 + 이 프로세스가 앞선 체결을 봄」만 받는다.
- **8영역** = `src/engine/order_engine.py` 한 파일. `_APPROVED_CONTENT_SHA` 한 줄 재핀(루트 CLAUDE.md 승인 도장 규약). 카드 E 와 커밋은 나누되(10-10 사용자 결정) 같은 주 배포 창에 태운다.
- 기존 「추가 체결」 분기(`pos.quantity = total_filled`, `pos.buy_price = price`)는 **바꾸지 않는다**. J-4 는 자기 플래그가 있을 때만 수량을 증분으로 더한다. `save_position` 의 `pos` 읽기 전환은 기존 경로에서 바이트 동일이다.
- ⚠️ **⑦-F1 과의 접점** — momentum 은 운영 DB 에서 `weight 0 · enabled false` 다(워크리스트 10-10). C2 에서 고아 폴백으로 momentum 에 올라간 포지션은 `risk.on_tick`(켜진 전략만 순회)의 손절 감시를 받지 않는다. J-4 는 그 포지션의 **수량을 맞출 뿐** 감시 공백을 만들지도 고치지도 않는다. 감시 공백은 ⑦-F1 자문(`2026-10-10_f1_unknown_holding_liquidation.md`, 권고 U)의 몫이다. 정확 일치는 「누가 들고 있든 그 포지션」에 붙으므로 U 가 착지해 고아 주인이 바뀌어도 그대로 맞는다.

## 6. 반례 / 한계

1. **표본** — 파일 로그 11거래일·매수 72건, `system_logs` 30일. 부분 체결 0 은 「지금 랏 크기에서 드물다」는 뜻이다. 랏이 커지면(입금·비중 확대·1주 폴백 축소) 바로 바뀐다.
2. **C3(`""` + COMPLETED 행)은 J-4 뒤에도 남는다.** 고치려면 B-ii(부팅 시드)가 필요하다.
3. **매핑·payload 둘 다 없는 통보(C5)는 범위 밖**이다. B-1 멱등 가드가 2차를 버린다.
4. **피라미딩(같은 종목 두 번째 주문)의 창 안 체결은 J-4 가 못 받는다** — 주문번호가 다르기 때문이다(E2 불성립 → B-2). 피라미딩은 닫혔으므로(cycle372) 지금은 해당 없다. 다시 열면 별도 귀속 설계가 필요하다.
5. 마지막 체결가 규약 때문에 부분 체결 주문의 `buy_price` 는 VWAP 보다 약간 높게 남는다(기존 동작, 보수 방향).

## 7. 후속 검증 권고

- **tdd-engineer** — §4(d) J4-1~J4-15 를 Red 로. J4-11 은 「현행 결함 고정」(B-i 채택 여부에 따라 기대값이 갈린다 — 결정 뒤 확정). J4-3 은 카드 E 커밋의 테스트로 두는 편이 맞다(키 갈아끼우기는 E 의 코드다).
- **tester** — 배포 뒤 첫 5거래일 `[buy_fill_exact_order_match]`·`[buy_fill_fallback_held_conflict]`·`[buy_partial_no_cancel_timer]` 를 센다. 정상 = 셋 다 0 근처. `exact_order_match` 가 뜨면 그 주문번호를 KIS 주문내역(TTTC0081R)의 `tot_ccld_qty` 와 대조해 장부 수량이 맞는지 본다.
- **워크리스트 후속(사용자 결정 뒤)** — C4 기존 결함(B-i 또는 B-ii) · C3 부팅 시드.

## 사용자 결정 필요

1. **J-4 착수** — 위 E1~E4 조건 · 수량 증분 · 단가 마지막 체결가 · 타이머 미등록으로 진행할지(8영역 `order_engine.py` 승인 포함).
2. **C4 기존 결함(부팅 복구 포지션의 잔량 체결이 수량을 줄인다)** — (가) J-4 커밋에 B-i 동반 (나) 워크리스트 후속으로 미룸(B-i 또는 B-ii) (다) 알려진 한계로 문서화만. 권고 = (나).
3. **카드 E 예약 감소** — (가) 현행 유지(첫 체결에서 그 주문 예약을 지운다, 키만 바꾼다) (나) 체결분만큼 감소. 권고 = (가). 어느 쪽이든 「창 안 체결 뒤 키 바꾸기 때 예약을 되살리지 않는다」는 카드 E 의 필수 조건이다.
