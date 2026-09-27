# cycle385 Red 명세 — B7 분할 매도(보유 축 차감) · J-2 재주문 직전 보유 재조회 · J-1 주석

- 작성: domain-expert · 2026-09-27(일) KST · 워크트리 `auto_stock_c385` (base `ba5bea1`)
- 결정 원문: 워크리스트 「09-27 사용자 답」 ③ — 「보유수량보다 적게 매도… 부분매도해도 잔여보유수량에 대한 추가매도가 가능하도록 실시간잔고의 매도상황을 추적관리할 수 있다는 전제하에 허용」 + 「b7 분할매도 진행」. 8영역 `src/engine/order_engine.py` 승인. **배포는 09-28 실측 판독 뒤**(워크리스트: 다음 주말)
- 근거 문서: `_workspace/red/bundle_D_plan.md` ⑦ · `_workspace/domain_consult/cycle332_buy_cancel_timer.md` §9 J-1/J-2 · `_workspace/domain_consult/cycle329_mapping_absent_full_fill.md` §2(축 b)·§6 · `src/engine/CLAUDE.md` 「체결통보 주문수량」「취소 타이머 키」「접수 후 PENDING 영속화」
- 범위 밖: **J-3**(PARTIAL 행 수량·CANCELLED 뒤집힘 — M-c 숫자 뒤 설계), `scheduler.py`(§i 결론 = 불요), `handler.py`(불요 — payload 는 cycle329 가 이미 넘긴다)
- 사용자 규칙 「새 제안 금지」 — 범위 밖은 §n 한 줄 후속으로만

---

## 0. 결론 (한눈에)

| 항목 | 정한 것 |
|---|---|
| 근본 변경 | `_handle_sell_fill` 의 판정을 **두 축으로 분리**한다. **주문 축**(`total_filled >= ordered_qty`, 그 주문이 끝났나) = 장부·매핑·타이머·`_selling`. **보유 축**(`pos.quantity` 를 체결량만큼 차감, 0 이 됐나) = 포지션 삭제·DB 삭제·`on_position_closed`·`sold_today`·구독 해제 |
| 보유 축에 출처 게이트 | **없다**(cycle329 금기 그대로). `map`/`payload`/`increment` 어느 출처든 체결량만큼 빼고 0 이면 닫는다 |
| 소유자 | 「그 종목을 실제로 들고 있는 전략」. 매핑·장부 전략이 들고 있으면 그것, 아니면 **registry 전수에서 보유 전략이 정확히 1개**일 때 그것. 0개 = 추적 보유 없음(현행 의미), 2개 이상·판정 예외 = **보유 축 무동작** + ERROR |
| 필수 동반 ① (새로 드러난 것) | `execute_sell` 발사 수량 고정 `send_qty` — B7 이 발사 창 통보로 `pos.quantity` 를 **await 도중에** 바꾸므로, 발사 뒤 `pos.quantity` 를 다시 읽는 3곳(주 경로 매핑·PENDING, 폴백 매핑·PENDING)이 **깎인 값**을 적는다 → 다음 통보가 overrun 클램프로 잘려 **보유가 남는 유령**이 된다(§a-2). cycle329 자문 §2 「축 (b)」가 「실효 ~0」이라 미뤘던 것이 B7 에서 실효가 된다 |
| 필수 동반 ② (새로 드러난 것) | `routes/trading.py` manual-sell 의 `_selling.add` 를 `place_order` **앞**으로. 지금은 **뒤**라, 시장가가 REST 응답 전에 체결되면 주문 종료의 `_selling.discard` 가 먼저 돌고 그 뒤 add 가 **잔여 보유의 손절을 막는 좀비**를 만든다(§g-3). B7 이전엔 포지션이 통째로 지워져 무해했던 순서다 |
| J-2 | `_cancel_and_reorder` 의 `place_order` 직전(마지막 await 뒤, 동기)에 registry 전수 재조회. 보유 1개 → `min(remaining, 보유)` 발사 · 보유 0 → **발사 안 함** + `_selling` 해제 · 2개 이상/예외 → **현행대로 `remaining` 발사** |
| J-1 | `order_engine.py:3085-3090` 주석만 사실대로(§f-4 원문). 코드 무변경 |
| KIS 잔고 대사(§i) | **불요.** 과대 추적은 매도 시점 #1.5 재대조(`order_engine.py:1968-2035`)가 이미 고치고, 과소 추적은 B7 밖(수동 추가매수 B-2)에서만 생긴다. `scheduler.py` **무접촉** |
| 8영역 면적 | `order_engine.py` 1파일(`_handle_sell_fill` · `execute_sell` 2자리 · `_cancel_and_reorder` · 신규 동기 메서드 2개) + 비8영역 `routes/trading.py` 1함수 |
| 핀 | order_engine whole-file 10곳 값만 재핀 + cycle287 `_SRC_TREE_DIGEST`(routes/trading.py) 값만 재핀. cycle295 `_BYTE_IDENTICAL_PINS`·cycle287 `_FROZEN_SEGMENTS` 는 **불변이어야 한다**(무접촉 증명) |
| 롤백 | 1커밋 revert + full 배포(장외 창). 런타임 다이얼 없음. DB 스키마 무변경 — 차감된 `positions.quantity` 는 revert 된 코드에도 그대로 유효 |

---

## 1. 트레이더 시각

**가설** — 「계좌에 남은 주식은 전부 손절선 아래에 있어야 한다.」 분할 매도는 트레이더의 기본 동작이다(반 익절·반 보유, 급할 때 일부만 던지기). 지금 코드는 「주문이 다 체결됐다 = 포지션이 끝났다」로 읽는다. 전략 매도는 언제나 보유 전량을 내므로(`execute_sell:1823` `quantity=pos.quantity`) 두 말이 같았지만, **사람이 일부만 팔면 두 말이 갈라진다** — 3주 매도가 다 체결되는 순간 남은 7주가 추적에서 사라지고, 그 7주는 손절·트레일링·15:20 청산 누구의 눈에도 없다.

**실전 사례 모양**

| 누가 | 무엇을 | 지금 | B7 뒤 |
|---|---|---|---|
| 운영자 대시보드 `POST /api/trading/manual-sell` | 10주 중 3주 | 3주 체결 → `del positions` + DB 삭제 + `sold_today` → 7주 **무방비**. 15분 sync(`scheduler.py:3437` 미보유 → 재채택)가 되살리지만 고점·전략·손절 규약이 바뀐다 | 7주로 차감·저장, `_selling` 해제 → 다음 틱부터 7주에 손절 평가 |
| 운영자 MTS | 10주 중 3주 | 매핑 부재 → `"momentum"` 폴백 → 소유 전략(예: kojiro)이면 **momentum 쪽에서** `sold_today`·`on_position_closed`, 그리고 `delete_position(ticker)` 가 **kojiro 의 DB 행을 지운다**(PK=ticker). kojiro 메모리엔 10주가 그대로(실제 7주) | kojiro 에서 7주로 차감·저장 |
| 손절 잔여 재주문 | 30초 뒤 | 스냅샷 `remaining` 그대로 발사, 보유 재조회 0(`:3137-3197`) | 재조회 후 `min(remaining, 보유)` · 보유 0 이면 발사 안 함 |

**위험 시나리오(이 명세가 막는 것)**
1. 잔여 보유가 추적 밖으로 사라져 손절 없는 노출이 생긴다(B7 본체).
2. 잔여 보유가 추적 안에 있지만 `_selling` 좀비가 손절 평가를 막는다(§g — manual-sell 순서, 주문 종료 시 해제 누락).
3. 수량이 틀려 없는 주식을 판다/덜 판다(§a-2 발사 수량, §f J-2).
4. 소유 전략을 잘못 짚어 남의 DB 행을 지운다(§e).

**반례(가설이 깨지는 곳)** — §m.

---

## a. 매도 주문의 **부분** 체결 (주문 축 = 부분)

### a-1. 규칙
`handle_execution_notice`(`order_engine.py:2324`)는 무변경 — 출처 3단(`:2383-2400`)·overrun 클램프(`:2420-2428`)·`[fill_qty_src]`(`:2430`) 그대로. 클램프 뒤의 `quantity` 가 **유효 증분**이고 보유 축은 이 값을 쓴다.

`_handle_sell_fill`(`:2813`) 부분 체결(주문 축 `total_filled < ordered_qty`)에서:
1. 소유자 해석(§e) → `pos` 확정
2. 손익 = `(price - buy_price) × quantity`, `daily_realized_pnl` 누적 — **현행 식 그대로**(증분 기준)
3. **보유 축(동기, await 없음)**: `held_before = pos.quantity` → `pos.quantity = max(0, held_before - quantity)` → `close_position = (pos.quantity == 0)`
4. `close_position` 거짓 → `save_position(...)`(§h) — `try/except Exception` 으로 감싼다
5. 주문 축: 현행 그대로 — PARTIAL UPDATE(`:2961`) · `remaining = ordered_qty - total_filled` · **`qty_src == "map"` 일 때만** `_schedule_cancel_and_reorder`(`:2976`) · 아니면 `[fill_partial_no_reorder]` · **`_selling` 유지**(주문이 아직 열려 있다)
6. INFO 「매도 부분 체결」(`:2984`) 끝에 `held_after=%d` 를 덧붙인다(INFO 라 `top_patterns` 무관)

### a-2. 🔴 필수 동반 — `execute_sell` 발사 수량 고정 `send_qty`

**새로 드러난 결함 경로(B7 이 만든다):**
```
execute_sell   pos.quantity = 10
               await place_order(quantity=10)
                 ◀ 창 안 부분 통보 3주(payload=10) → B7 이 pos.quantity 10 → 7
               _order_qty[order_no] = pos.quantity        ← 🔴 7 이 적힌다 (:1831)
               _persist_sell_pending_after_send(quantity=pos.quantity)  ← 🔴 PENDING 7 (:1846)
  ◀ 잔여 7주 통보(map)   total_filled 3+7=10 > ordered 7 → [fill_qty_overrun] 클램프
                        → total 7, quantity = 7-3 = 4 → 보유 7-4 = 3 이 **남는다**(실제 0)
```
결과 = 실보유 0 인데 3주 유령 + 주문 종료로 `_selling` 해제 → 다음 틱 손절이 3주 매도 → APBK0400/부족 → #1.5 가 결국 정리하지만 **거부 주문 1건 + 손익 4주분 누락**.

**규칙:** 재시도 루프 상단 재조회(`:1810`) 직후, `place_order` 앞에서 `send_qty = pos.quantity` 를 한 번 잡고 발사·매핑·PENDING·로그에 **그 값만** 쓴다.

| 자리 | 지금 | 바꾼 뒤 |
|---|---|---|
| 주 경로 발사 `:1823` | `quantity=pos.quantity` | `quantity=send_qty` |
| 주 경로 매핑 `:1831` | `self._order_qty[result.order_no] = pos.quantity` | `= send_qty` |
| 주 경로 PENDING `:1846` | `quantity=pos.quantity` | `quantity=send_qty` |
| 주 경로 로그 `:1851-1853` | `pos.quantity` | `send_qty` |
| 폴백 발사 `:2152` | `quantity=pos.quantity` | `quantity=send_qty` |
| 폴백 매핑 `:2159` | `= pos.quantity` | `= send_qty` |
| 폴백 PENDING `:2174` | `quantity=pos.quantity` | `quantity=send_qty` |

- 폴백도 **루프 상단 값**을 쓴다 — 1차 주문은 거부돼 체결이 없고, 같은 회차다(cycle329 자문 §2.2 「`ordered_qty` 하나로 통일」).
- `record_price=pos.buy_price`(`:1845`·폴백 `record_price=fallback_price`)는 무변경 — 매수가는 차감으로 바뀌지 않는다.
- 🔴 매핑 등록 ~ `_persist_sell_pending_after_send` 사이 await 0(`test_g328_1`) · 헬퍼 본문·경계 `except Exception`(`test_g328_3b`) **무접촉**. 바뀌는 것은 인자 **값 표현식**뿐이다. 시나리오 J(`test_order_engine_sell_fallback.py`)의 `quantity` 값은 정상 흐름에서 동일.
- `_cancel_and_reorder` 의 발사 수량은 이미 지역 int(`remaining`) → J-2 의 `fire_qty`(§f)로 대체. manual-sell 은 `req.quantity`(고정값) → 무변경.

---

## b. 보유보다 **작은** 주문의 전량 체결 (주문 축 = 종료, 보유 > 0) — B7 본체

`if total_filled >= ordered_qty:`(주문 종료) 에서 보유 축이 `close_position` 거짓(= 보유가 남았다)이면:

| 효과 | 규칙 |
|---|---|
| `state.positions[ticker]` | **유지**(차감된 수량) |
| `save_position` | 차감 수량으로 upsert(§h) |
| `delete_position` · `on_position_closed` · `sold_today.add` · `_unsubscribe_if_no_other_strategy` | **하지 않는다** |
| `self._selling.discard(ticker)` | **한다** — 주문이 끝났으므로 진행 중 표식은 거짓이다. 해제해야 다음 틱에 잔여 보유의 손절이 평가된다 |
| `update_trade_status(COMPLETED, match_partial=True, order_no=...)` + 보정 INSERT/강제 UPDATE 사슬 | **현행 그대로**(`:2894-2936`). 그 행은 **이 주문의 수량(=판 수량)**을 담고, 잔여 보유는 장부에 매도로 적히지 않는다 |
| 매핑 pop 6종(`:2937-2942`) | 현행 그대로 |
| 타이머 해제(`:2949-2955`, `(ticker, sell)` 키 + `order_no` 일치 게이트) | 현행 그대로 |
| 로그 | 「매도 전량 체결」 INFO(`:2943`)는 **보유가 0 일 때만**. 보유가 남으면 `[sell_fill_holding_remains]` WARNING(§j) |

**잔여분 추가 매도 가능성(사용자 전제의 행위 증명)** — 이후 `execute_sell` 은 루프 상단 재조회 `pos.quantity`(차감값)로 발사한다(`:1810`→`send_qty`). 15:20 청산·익일청산·트레일링 모두 `execute_sell` 경유라 자동으로 잔여 수량을 판다.

---

## c. 보유보다 **큰** 체결 (체결량 > 추적 보유)

생기는 곳: manual-sell 수량 > 추적 수량(계좌엔 더 있음) · 수동 추가매수로 추적 < 실보유(B-2 `[buy_fill_fallback_held_conflict]` `:2610-2616`) · 그 상태의 MTS 매도.

| 규칙 | 값 |
|---|---|
| 보유 축 | `pos.quantity = max(0, held_before - quantity)` — **음수 금지**, 0 이면 닫는다(§h 닫기 묶음) |
| 관측 | `[sell_fill_exceeds_holding]` WARNING(§j) |
| 손익 | **현행 그대로** 체결 증분 기준. 추적 밖 주식의 원가를 모르므로 바꾸지 않는다(한계 §m-5) |
| 주문 축 | 무변경. 주문이 아직 열려 있으면(부분) `_selling` 유지 — 남은 체결 통보가 주문 종료에서 해제하고, 타이머가 걸렸다면 J-2 가 「보유 0」으로 발사하지 않고 해제한다(§f) |
| 남은 실보유 | 포지션이 닫혔으므로 15분 sync 가 「미보유」로 보고 재채택한다(`scheduler.py:3437-3460`) — 과소 추적이 **지속되지 않는다** |

⚠️ 이 클램프는 기존 **주문 축 overrun 클램프**(`:2420`, 누적 > 주문수량)와 **다른 축**이다. 둘은 독립적으로 발화할 수 있다.

---

## d. 매핑 부재 매도 (MTS/HTS 수동 · 발사 창 안의 우리 주문)

- 수량 출처: cycle329 3단 그대로. `payload`(fields[16] ODER_QTY)가 있으면 주문 축이 정확하고, 없으면 `increment` 로 **통보마다 주문 종료**로 읽힌다.
- 🔴 **보유 축은 출처와 무관하게 정확하다** — `increment` 퇴화에서도 통보마다 체결량만큼 빠지고 0 에서만 닫힌다. cycle329 가 「남는 사각」으로 적은 매도 축 피해(잔량이 손절 감시 밖으로 사라짐)는 B7 로 **닫힌다**.
- 소유자: §e 의 해석을 탄다. `_order_strategy` miss → `_lookup_strategy_from_trade_history`(PENDING/PARTIAL 행) miss → **(신규) 보유 전략이 정확히 1개면 그 전략** → 그래도 없으면 `"momentum"`(현행 폴백·현행 WARNING 문구 그대로).
- 타이머: `qty_src != "map"` 이면 **걸지 않는다**(cycle329 금기 불변) — 사람이 낸 주문을 우리가 취소·재주문하지 않는다.
- `_selling`: 수동 주문은 우리가 넣은 적이 없다. 다만 우리 손절이 `[sell_qty_partial_locked]`(`:1996`)로 `_selling` 을 **유지**해 둔 상태라면, 그 MTS 주문의 종료가 해제한다 → 차감된 잔여로 손절 재평가(현행 해제 동작을 그대로 쓴다).
- 🔴 **sell 측 멱등 마커(`_completed_sell_orders`)는 두지 않는다** — 매수 측 P1-B 와 달리, 매도에서 「종료 뒤 같은 주문번호의 통보」는 `increment` 퇴화에서 **진짜 분할 체결**이다. 막으면 보유가 덜 빠진다. 보유 축의 `max(0, …)` 가 과차감을 막는 마지막 선이다.

---

## e. 여러 전략 · 종목 소유

### e-1. 불변식
전략 간 동일 종목 보유는 `registry.is_ticker_blocked_for_buy`(`strategy_registry.py:86-98`)가 막는다 → 정상 흐름에서 보유 전략은 **최대 1개**. 2개 이상은 부팅·sync 이상에서만 생기는 **방어 대상**이다.

### e-2. 신규 동기 헬퍼 (order_engine.py, 8영역)
```python
def _ticker_holders(self, ticker: str) -> "list[StrategyBase] | None":
    """registry 전수(`self.registry.all()` — 비활성 전략 포함)에서 `ticker in s.state.positions` 인 전략.
    await 0 · never-raise · 판정 예외 = None."""
```
- 🔴 `registry.all()` 이어야 한다(`enabled()` 아님) — 꺼진 전략의 보유도 실보유다(루트 금기 「보유 전략 끄기」와 같은 이유).
- 🔴 `registry.get(strategy_id)` 로 좁히지 않는다 — 그것이 `"momentum"` 기본값 함정이다(`_cancel_and_reorder:3084` 가 `.get(order_no, "momentum")`).

### e-3. `_handle_sell_fill` 소유 해석 (순서가 계약)
```
① sid = _order_strategy.get(order_no)                                    (현행 :2842)
② sid 없음 → await _lookup_strategy_from_trade_history(...)             (현행 :2846)
   ├ 찾음 → [sell_fill_strategy_lookup_recovered] INFO                  (현행)
   └ 못 찾음 → (신규) holders = _ticker_holders(ticker)
                ├ 정확히 1 → sid = holders[0].strategy_id + [sell_fill_owner_from_holding] from=none
                └ 그 밖 → [sell_fill_strategy_lookup_fallback] WARNING(현행 문구) + sid = "momentum"
③ strategy = registry.get(sid) · 없으면 현행 ERROR + _selling.discard + return (:2860-2864 무변경)
④ (신규, 동기) 소유자 owner:
   - ticker in strategy.state.positions      → owner = strategy
   - 아니고 holders == 정확히 1               → owner = holders[0] + [sell_fill_owner_from_holding] from=<sid>
   - 아니고 holders 가 2개 이상 또는 None(예외) → owner = None, ambiguous = True + [sell_fill_owner_ambiguous] ERROR
   - 아니고 holders == 0                      → owner = None (추적 보유 없음)
```
- holders 는 ②(await) **뒤** 한 번 계산해 ②·④ 가 같이 쓴다. ④ 이후 보유 축(§a 3)까지 **await 0** — 그래야 `execute_sell` 루프 상단 재조회·J-2 재조회와 원자적으로 맞물린다.
- **장부 축 전략 = `sid`**(`update_trade_status(strategy=sid)`·보정 INSERT). PENDING 행이 `sid` 로 적혀 있으므로 WHERE 가 맞는다. MTS 처럼 행이 없는 매도는 ② 의 신규 단 덕에 `sid` 가 **보유 전략**이 되어 보정 INSERT 행이 그 전략으로 적힌다(지금은 momentum 오귀속).
- **보유 축 전략 = `pos_strategy = owner or strategy`** — `pos` · `daily_realized_pnl` · `on_position_closed` · `sold_today` 는 전부 `pos_strategy` 에서. owner 가 None 이면 `strategy` = 현행과 **완전히 같은 대상**이다(cycle147 005940 재현 `sold_today` LTV 단언 보존).
- 🔴 G147-AST-1: `_handle_sell_fill` 안 `self._order_strategy.get(order_no, "momentum")` 0건 유지.

---

## f. J-2 — 재주문 직전 보유 재조회

### f-1. 자리
`_cancel_and_reorder`(`:3074`)의 `if is_stop_loss and remaining > 0:`(`:3137`) 블록 **첫 문장**. 앞의 마지막 await(`update_trade_status(CANCELLED)` `:3129`) 뒤이고, 뒤의 애프터 호가 판정(`:3143-3172`)·`place_kwargs`(`:3174`)는 전부 동기라 **재조회 ~ `await place_order`(`:3188`) 사이 await 0** 이 성립한다.

- 취소(`cancel_order`)는 **현행대로 무조건** 낸다(쌍 게이트 `_market_rest_gate` 무변경). J-2 는 **발사 여부와 수량만** 바꾼다.

### f-2. 신규 동기 헬퍼
```python
def _reorder_requery(self, ticker: str, order_no: str, remaining: int) -> int:
    """반환 = 발사 수량(0 = 발사하지 않는다). await 0 · never-raise(예외 = remaining)."""
```
| holders(`_ticker_holders`) | verdict | 반환 | 레벨 |
|---|---|---|---|
| 정확히 1, 보유 ≥ remaining | `same` | `remaining` | INFO |
| 정확히 1, 0 < 보유 < remaining | `shrunk` | 보유 | WARNING |
| 0 개(또는 1개인데 수량 ≤ 0) | `gone` | 0 | WARNING |
| 2개 이상 | `ambiguous` | `remaining`(**현행 행위**) | WARNING |
| `None`(예외) · 헬퍼 내부 예외 | `error` | `remaining`(**현행 행위**) | WARNING |

- 🔴 **「보유에 맞춘다」는 상한이지 증액이 아니다 — `min(remaining, 보유)`.** 보유 > remaining 은 manual-sell 부분 주문(3주 주문, 1주 체결 → remaining 2, 보유 9)에서 생긴다. 보유로 올리면 운영자가 남기려던 7주까지 판다 = 사용자 결정(분할 매도 허용)의 정면 위반이다.
- 🔴 의심스러우면 **쏜다** — 손절 잔여를 버리는 쪽이 더 비싸다(과대 요청은 KIS 가 APBK0400 으로 막고 #1.5 가 흡수한다).

### f-3. `_cancel_and_reorder` 안 적용
```python
fire_qty = self._reorder_requery(ticker, order_no, remaining)
if fire_qty <= 0:
    self._selling.discard(ticker)          # 원주문은 방금 취소됐고 새 주문도 없다 = 진행 중 표식은 거짓
    self._selling_since.pop(ticker, None)
    return                                  # try 안 → finally 가 자기 타이머 키를 pop (무변경)
...
place_kwargs = dict(..., quantity=fire_qty, ...)
self._order_qty[result.order_no] = fire_qty     # :3190 (remaining → fire_qty)
logger.info("손절 잔여 재주문: %s %d주", t(ticker), fire_qty)   # :3197
```
- `place_order` 호출은 여전히 **정확히 1개**이고 값으로 받는다(G-295-C4).
- `strategy_id = self._order_strategy.get(order_no, "momentum")`(`:3084`)·쌍 게이트·취소·CANCELLED UPDATE·`finally` pop 은 **무변경**.

### f-4. J-1 — 주석만 (`:3085-3090`)
현행 `:3089-3090` 「(16:00 이후 `cancel_remaining` 또는 `risk.on_tick` 재평가에 위임한다).」 를 지우고 아래로 바꾼다(정본 `src/engine/CLAUDE.md:719-721` 과 같은 사실):
```python
            # cycle295 (B) — 쌍 게이트(§3-5③). 이 함수만 취소 3경로 중 유일하게
            # `sleep(30) → cancel_order → place_order` 의 atomic replace 다.
            # 절반만 막으면 "호가창의 손절을 우리가 빼고 아무것도 안 넣은" 상태가
            # 된다 — 컷이면 취소도 하지 않고 작동 중인 주문을 그대로 둔다.
            # 🔴 그 잔량을 우리가 거두는 경로는 없다 — `cancel_remaining` 은 호출자가
            # 0 이고(배선해도 매수 주문번호를 취소한다), `risk.on_tick` 재평가는 새
            # 매도를 낼 뿐 걸린 주문을 취소하지 않는다. KRX 잔량은 정규장 마감 뒤
            # 거래소가 자동 취소한다. NXT 잔량은 20:00 까지 남는데, 그런 매도는
            # 프리장 `pre_nxt_keep` · `order_exchange_clock_mode="off"` · `probe_error`
            # 로 base 를 유지했을 때만 생긴다. 정본 = `src/engine/CLAUDE.md` 규칙 3.
```
코드(AST) 변경 0. `:1428`·`:465` 의 `cancel_remaining` 언급은 「취소 함수 목록」이라 사실이다 — 손대지 않는다.

---

## g. `_selling` 수명

### g-1. 표
| 사건 | `_selling` | 근거 |
|---|---|---|
| `execute_sell` 진입 | add + `_selling_since`(`:1637-1638`) | 무변경 |
| 발사 전 실패·게이트(차단·컷·포지션 없음·장운영외·폴백 모두 거부·최종 실패) | discard | 무변경 |
| 발사 성공 | 유지 | 무변경 |
| 체결 통보 — 주문 **부분** | 유지(주문이 열려 있다) | 무변경 |
| 체결 통보 — 주문 **종료**, 보유 0 | discard | 무변경 |
| 체결 통보 — 주문 **종료**, 보유 남음 | **discard** | 🔴 신규 규칙의 핵심 — 남기면 잔여 손절 마비 |
| 주문 부분인데 보유 0(§c) | 유지 → 주문 종료 통보 또는 J-2 `gone` 에서 해제 | 신규 |
| J-2 `gone` | **discard + since pop** | 신규 |
| J-2 발사 성공 | 유지(새 주문의 종료가 해제) | 무변경 |
| J-2 `place_order` 실패(`except Exception` `:3200`) | 유지 → `selling_reconcile`(180초 age + 열린 주문 없음) 해제 | 현행(§n 후속) |
| `[sell_qty_partial_locked]`·`[sell_qty_locked]` | 유지(열린 기주문 실재) | 무변경 |
| manual-sell | **발사 앞에서 add** + since | 🔴 필수 동반 ②(§g-3) |

### g-2. 불변식
- 🔴 **「주문이 끝났다」와 「보유가 남았다」가 동시에 참이면 `_selling` 은 반드시 비어 있어야 한다.** `risk.on_tick` 은 `ticker in _selling` 이면 `check_exit_signal` 을 건너뛴다(`risk.py:699-700`).
- 해제는 주문 축에서만(보유 축은 `_selling` 을 건드리지 않는다). 예외 = J-2 `gone`(주문 축의 끝을 J-2 가 만들었으므로).

### g-3. 🔴 필수 동반 ② — manual-sell (`src/routes/trading.py:129-213`, 비8영역)
현행 순서(`:166` `await place_order` → `:178-181` 매핑 + `_selling.add`)에서 시장가가 REST 응답 전에 체결되면:
```
await place_order ◀ 체결 통보(3주, payload 3) → 주문 종료 → _selling.discard(없음) · 보유 10→7
route             _selling.add(ticker)           ← 🔴 열린 주문도 없는데 표식이 선다
                  → 7주 손절 평가 정지. `_selling_since` 도 없어 age 게이트는 건너뛰지만,
                    해제는 15분 sync(09:30~15:20·15:30~20:00 에만 돈다) 때까지 기다린다
```
**규칙:**
```python
engine = trading_scheduler.order_engine
_added = req.ticker not in engine._selling
if _added:
    engine._selling.add(req.ticker)
    engine._selling_since[req.ticker] = datetime.now(<KST>)
_sent = False
try:
    result = await place_order(...)
    _sent = True
    ... 매핑 3종 등록 (현행 :178-180, `_selling.add` 줄 :181 은 삭제) ...
    await insert_trade(record)          # 현행
    ...
except Exception as e:
    if _added and not _sent:            # 발사 전 실패만 되돌린다
        engine._selling.discard(req.ticker)
        engine._selling_since.pop(req.ticker, None)
    ... 현행 ERROR + 실패 응답 ...
```
- 🔴 **`_sent` 이후의 실패로 `_selling` 을 풀지 않는다** — 주문은 이미 거래소에 있다(루트 금기 「주문이 나간 뒤의 실패로 재발사 금지」와 같은 원리). 그 주문의 종료 통보가 해제한다.
- 🔴 이미 `_selling` 에 있던 종목(자동 매도 진행 중)은 **건드리지 않는다**(`_added` 거짓).
- 라우트 docstring 의 「실패 경로에 `_selling.discard` 가 없어 stale `_selling` 이 남는다」를 「발사 전 실패는 되돌리고, 발사 뒤는 통보가 해제한다」로 정정.

---

## h. DB · positions · trade_history · 실현손익 · sold_today · 구독 · on_position_closed

### h-1. 효과 행렬
`close_position` 정의(§a 3 · §e-3):
- `pos` 있음 → 차감 뒤 `pos.quantity == 0`
- `pos` 없음 ∧ ambiguous → **거짓**(보유 축 무동작)
- `pos` 없음 ∧ 보유 전략 0 → `total_filled >= ordered_qty`(**현행 의미 그대로** — 추적 보유가 없는 전략의 멱등 정리)

| 효과 | 주문 부분 · 보유 남음 | 주문 부분 · 보유 0(§c) | 주문 종료 · 보유 남음 | 주문 종료 · 보유 0 | pos 없음 · 보유 전략 0 · 종료 | ambiguous |
|---|---|---|---|---|---|---|
| `pos.quantity` 차감 | ✅ | ✅(→0) | ✅ | ✅(→0) | — | — |
| `save_position`(차감값) | ✅ | — | ✅ | — | — | — |
| `del state.positions[ticker]` | — | ✅ | — | ✅ | — | — |
| `on_position_closed`(`pos_strategy`) | — | ✅ | — | ✅ | ✅(현행) | — |
| `sold_today.add`(`pos_strategy`) | — | ✅ | — | ✅ | ✅(현행) | — |
| `delete_position(ticker)` | — | ✅ | — | ✅ | ✅(현행) | — |
| `daily_realized_pnl += 증분손익` | ✅ | ✅ | ✅ | ✅ | ✅(0) | ✅(0) |
| trade_history | PARTIAL(현행) | PARTIAL(현행) | COMPLETED(현행) | COMPLETED(현행) | COMPLETED(현행) | 주문 축 그대로 |
| `_selling.discard` | — | — | ✅ | ✅ | ✅ | 종료면 ✅ |
| 매핑 pop · 타이머 해제 | — | — | ✅ | ✅ | ✅ | 종료면 ✅ |
| 재주문 타이머(map 한정) | ✅ | ✅(J-2 가 `gone`) | — | — | — | 부분·map 이면 ✅ |
| `_unsubscribe_if_no_other_strategy` | — | — | — | ✅ | ✅ | — |
| 마커 | INFO held_after | `[sell_fill_exceeds_holding]` | `[sell_fill_holding_remains]` | 「매도 전량 체결」 INFO | 현행 | `[sell_fill_owner_ambiguous]` |

### h-2. 구조 (문장 순서)
```
[소유 해석 §e-3] → [손익 현행] → [보유 축 차감(동기)] →
if close_position:            ← 닫기 묶음 1곳 (del · 훅 try · sold_today · await delete_position)
    ...
elif pos is not None:         ← 저장 1곳 (try/except Exception → [sell_fill_db_error] step=save_position)
    ...
if total_filled >= ordered_qty:   ← 🔴 이 If 는 문자 그대로 · 함수 본문 최상위 · 1개
    _selling.discard → COMPLETED 사슬(현행) → pop(현행) → 로그 → 타이머 해제(현행) → close 면 구독 해제 / 아니면 [sell_fill_holding_remains]
else:
    PARTIAL(현행) → remaining → map 게이트 타이머(현행) → INFO(held_after)
```
- 🔴 `del state.positions[...]` 는 **`_handle_sell_fill` 안에 남는다**(헬퍼로 빼면 G2-STRUCT-INVARIANT 의 site 집합 `{_handle_sell_fill, execute_sell}` 이 깨진다). 같은 함수에 `on_position_closed` 호출 동반.
- 🔴 `if total_filled >= ordered_qty:` 를 `if order_done:` 등으로 바꾸지 않는다 — `test_cycle273a_ast_partial_optin_and_timer.py::_full_fill_if` 가 그 **문자 그대로의 If** 안에서 `_pending_cancel_tasks`·`order_no` 비교를 찾는다(g273_ast3/ast4). 보유 축의 `close_position = total_filled >= ordered_qty` 는 **대입**이라 걸리지 않는다. 그 밖에 같은 모양의 If 를 만들지 않는다.
- `match_partial=True` 는 여전히 **정확히 2곳**(매수·매도 COMPLETED) · CANCELLED 호출에 붙이지 않는다(g273_ast1/ast2).
- `delete_position` 은 현행처럼 **감싸지 않는다**(현행 행위 보존 — §n 후속). 새 `save_position` 만 감싼다(체결통보 콜백의 예외는 WS 재연결을 부른다, `handler.py:757-770`).

### h-3. `save_position` 인자
`src/db/positions.py:21` upsert — 한 필드라도 빠지면 다른 값이 덮인다.
```python
await save_position(
    ticker=ticker, ticker_name=scanner.ticker_names.get(ticker, ""),
    buy_price=pos.buy_price, quantity=pos.quantity, order_no=pos.order_no,
    strategy_id=pos_strategy.strategy_id, buy_date=pos.buy_date,
    high_since_buy=pos.high_since_buy,
)
```
- 부팅은 DB 수량을 그대로 복원한다(`boot_manager.py:283-316`) → 차감이 재시작을 넘어 유지된다. 저장 실패 시 DB 는 옛(큰) 수량 → 재시작 뒤 과대 추적 → 매도 시점 #1.5 가 고친다(§i).

### h-4. 불변식 요약
- `on_position_closed` = 보유가 0 이 될 때만(+ 추적 보유 없는 전략의 현행 멱등 정리), 호출 site 여전히 정확히 2함수.
- `sold_today` = 닫힐 때만. 보유가 남은 동안 재매수는 `has_position` 이 이미 막는다.
- 구독 해제 = 닫힐 때만. 🔴 잔여 보유의 WS 틱을 끊으면 손절이 REST 폴에만 기댄다.
- 손익 = 체결 증분만(잔여 보유분은 손익에 들어가지 않는다). trade_history SELL 행 수량 = 그 주문의 수량(=판 수량). 분할 매도의 매수↔매도 짝짓기는 `get_trade_pairs` 의 누적 보유 모델(`trade_history.py:635-639`)이 이미 처리한다.

---

## i. KIS 잔고 대사가 사용자 전제에 필요한가 — **불요 · `scheduler.py` 무접촉**

사용자 전제 = 「부분 매도 뒤 잔여 보유를 추적해 잔여분 추가 매도·손절이 가능해야 한다」. 실시간 추적의 1차 경로는 체결통보(H0STCNI0)이고 B7 이 그것을 보유 축에 반영한다. 어긋남이 생기는 두 방향을 따로 본다.

| 방향 | 어디서 생기나 | 누가 고치나 | B7 이 새로 만드나 |
|---|---|---|---|
| **과대**(추적 > 실보유) | 체결통보 유실 · `save_position` 실패 뒤 재시작 | 매도 시점 `is_sell_qty_exceeded` #1.5 → `[sell_qty_reconciled]` held 로 하향·재시도(`order_engine.py:1968-2035`) · 실보유 0 이면 insufficient 경로 삭제(`:2052-2061`, `:2272-2320`) · 열린 주문 없는 `_selling` 은 `selling_reconcile.py:104-151` 해제 | 아니다(기존 경로가 그대로 흡수) |
| **과소**(추적 < 실보유) | 보유 중 수동 추가매수 = B-2 조기 return(`:2610-2616`) + sync 가 보유 종목 수량을 안 고침(`scheduler.py:3437`) | 추적분이 닫히면 sync 가 남은 실보유를 재채택 | **대부분 아니다.** 예외 2 — ① 이미 과소인 혼합 보유에서의 수동 부분 매도(그 전엔 통째 삭제 → 재채택이 우연히 고쳤다) ② 같은 체결의 진짜 재전송(`increment` 에서 이중 차감, 실측 증거 없음 — cycle235 의 「중복」은 [9]/[16] 오독이었다) |

**결론:** 전제는 추적되는 주식(전략 매수·manual-sell·추적 종목의 MTS 매도)에 대해 B7 만으로 성립한다. 과소 방향 대사(상향)는 「수동으로 산 주식을 어느 전략이 관리하느냐」는 **채택 정책 결정**을 선행해야 하는 별건이다(§n F-385-2). 따라서 **`scheduler.py` 위임은 필요 조건이 아니다 — 무접촉**(3,786줄 불변).

---

## j. 마커

| 마커 | 레벨 | cap | 필드 | 뜻 · 판독 |
|---|---|---|---|---|
| `[sell_fill_holding_remains]` | WARNING | 없음(드묾, 건별 조사 단위 — cycle331 선례) | `order_no= ticker= owner= sold= held_after= ordered= src=` | **B7 의 성공 서명.** 주문이 끝났는데 보유가 남았다 = 분할 매도. `src=increment` 와 짝이면 payload 부재 퇴화(주문 종료가 거짓일 수 있다 — `[fill_qty_src]` 와 대조) |
| `[sell_fill_exceeds_holding]` | WARNING | 없음 | `order_no= ticker= owner= held_before= fill= src=` | 추적보다 많이 팔렸다 = 추적이 이미 과소였다(수동 추가매수 등). 0 이 정상 |
| `[sell_fill_owner_from_holding]` | WARNING | 없음 | `order_no= ticker= from=<sid\|none> to=<sid> src=` | momentum 기본값 함정을 비껴갔다. `from=none` = MTS·발사 창 / `from=<sid>` = 장부 전략이 안 들고 있었다(이상) |
| `[sell_fill_owner_ambiguous]` | ERROR | 없음 | `order_no= ticker= sid= holders=<csv\|error> src=` | 보유 전략 2개 이상 또는 판정 예외 → 보유 축 무동작. **0 이 정상**, 1건이면 조사 |
| `[sell_fill_db_error] step=save_position` | ERROR | 없음 | `ticker= order_no= owner= held_after= err=` | 차감이 DB 에 안 남았다 → 재시작하면 과대 추적(매도 시점 자기 치유). 하루 여러 건이면 RDS |
| `[reorder_requery]` | `same`=INFO, 그 외 WARNING | 없음(5개월 발화 0) | `verdict=same\|shrunk\|gone\|ambiguous\|error ticker= order_no= remaining= held= fire_qty=` | `gone` = 재주문 안 냄 + `_selling` 해제 / `shrunk` = 취소 대기 중 체결이 더 있었다 |
| 「매도 부분 체결」 INFO(`:2984`) | INFO | — | 끝에 `held_after=` | 부분 체결마다 보유 잔량 |

- 전부 **행위 밖** — 로그 실패가 판정을 바꾸지 않는다(로그 호출은 `logger.*` 뿐, 새 `write_log`·DB 없음).
- WARNING 이상만 21:30 `top_patterns` 에 오른다 — 위 표의 WARNING/ERROR 가 리포트에 뜨는 것이 의도다.
- 신규 `KstDailyEmitCap` 속성 0 → `reset_daily_state` 무변경.

---

## k. 롤백

| 수단 | 방법 | 반영 |
|---|---|---|
| 유일 수단 | 이 사이클 커밋 1개 `git revert` + push → full(backend 재시작) | 장외 창만: 21:35~익일 07:45 · 주말·공휴일. 🔴 20:00~21:35 금지(D8) · 보유 중 09:00~15:30 금지(D6) |
| 런타임 다이얼 | **없다**(`DEFAULT_PARAMS`·`system_config` 신규 키 0 — 사용자 규칙) | — |
| 데이터 호환 | 스키마 무변경. B7 이 차감해 둔 `positions.quantity` 는 revert 된 코드에서도 유효(부팅이 DB 수량 ∩ KIS 로 복원) | 마이그레이션·DB 보정 불요 |
| 되돌린 뒤 운영 | 수동 부분 매도(manual-sell·MTS)를 다시 **피한다**(B7 결함 복귀) | 운영자 공지 |

---

## l. 테스트 · 돌연변이 계획

### l-1. 새 파일
- `tests/unit/engine/test_cycle385_b7_partial_sell.py` — T1~T19
- `tests/unit/engine/test_cycle385_reorder_requery.py` — T20~T26
- `tests/unit/routes/test_cycle385_manual_sell_selling.py` — T27~T29
- `tests/unit/ast/test_cycle385_ast_b7.py` — A1~A9

하네스 선례: 발사 창 주입 = `test_cycle329_mapping_absent_full_fill.py::_make_env`(fake `place_order` 안에서 `handle_execution_notice` 호출) · 재주문 = `test_cycle295_stop_loss_reorder_mapping.py`(`PARTIAL_FILL_WAIT=0`, `cancel_order`/`place_order` AsyncMock). `src.db.positions.save_position`/`delete_position` 는 호출 인자까지 기록하는 AsyncMock. 🔴 caplog 단언은 WARNING 이상 + prefix 로만(메모리 `feedback_caplog_debug_level`).

### l-2. 행위 테스트
| ID | 입력 | 기대 |
|---|---|---|
| T1 (b) | 보유 10(kojiro), `_order_qty[S1]=3`·`_order_strategy=kojiro`, 통보 3 | 보유 7 · `save_position(quantity=7, buy_price·order_no·buy_date·high_since_buy 보존, strategy_id=kojiro)` 1회 · `delete_position` 0 · `sold_today` 미포함 · `on_position_closed` 0 · 구독 해제 0 · `_selling` 미포함 · COMPLETED `match_partial=True` 1회 · 매핑 pop · `[sell_fill_holding_remains]` 1행 · `daily_realized_pnl == (px-buy)*3` |
| T2 (a) | 보유 10, `_order_qty=10`, 통보 4 | 보유 6 · save(6) · PARTIAL · `_selling` 유지 · `(ticker,"sell")` 타이머 등록 · 「매도 부분 체결」에 `held_after=6` |
| T3 (a→b) | T2 뒤 통보 6 | 닫힘: del · 훅 1 · `sold_today` · delete 1 · 구독 해제 1 · `_selling` 해제 · 손익 = 4주+6주 |
| T4 (b 전제) | T1 뒤 `execute_sell(STOP_LOSS, kojiro)` | `place_order(quantity=7)` (10 아님) |
| T5 (c) | 보유 5, `_order_qty=8`, 통보 8 | `[sell_fill_exceeds_holding]` · 닫힘 · 수량 음수 없음 · 손익 = 8주 기준(현행) |
| T6 (c 부분) | 보유 5, ordered 8, 통보 6 | 부분 분기에서 닫힘(del·훅·delete) · `_selling` **유지** · 타이머 등록 |
| T7 (d) | kojiro 10 보유, momentum 미보유, 매핑·장부 miss, 통보 3(payload 3) | 주인 kojiro · 보유 7 · momentum `sold_today`/훅 0 · `delete_position` 0 · `[sell_fill_owner_from_holding] from=none` · 보정 INSERT 행 `strategy=kojiro` |
| T8 (d increment) | kojiro 10, 매핑·장부 miss, payload 없음, 같은 주문번호로 통보 2 → 1 | 보유 7 · 닫히지 않음 · delete 0 |
| T9 (d 전량) | kojiro 10, MTS payload 10 · 통보 10 | kojiro 에서 닫힘(훅·sold_today·delete) |
| T10 (e 무보유) | 아무도 미보유, 매핑·장부 miss | 현행 그대로: `[sell_fill_strategy_lookup_fallback]` · momentum `sold_today` · delete 1 |
| T11 (e 모호) | momentum·kojiro 둘 다 보유(인위), 매핑·장부 miss(→momentum 은 보유라 ④ 첫 줄) — 모호 재현은 장부 sid=VB(미보유) + 두 보유자 | 두 전략 수량 불변 · delete 0 · `[sell_fill_owner_ambiguous]` ERROR · 주문 종료면 `_selling` 해제 |
| T12 (e 장부 복구) | cycle147 005940 재현(보유 0, 장부=LTV) | LTV `sold_today` 포함(현행) · `[sell_fill_owner_from_holding]` 0 |
| T13 (창·send_qty) | `execute_sell`, fake place_order 안에서 통보 3(payload 10) | 반환 뒤 `_order_qty[no]==10` · PENDING 수량 10 · 보유 7 → 이어서 통보 7(map) · `[fill_qty_overrun]` 0 · 닫힘 · 손익 10주 |
| T14 (폴백 send_qty) | 1차 APBK1943 거부 → 폴백 발사 안에서 통보 3(payload 10) | `_order_qty[fb]==10` · 폴백 PENDING 수량 10 |
| T15 (g) | T1 뒤 | `ticker not in _selling` · 곧바로 `execute_sell` 이 `_selling` 중복 차단에 안 걸린다 |
| T16 (g) | T2 뒤 | `_selling` 유지(현행 회귀) |
| T17 (h) | `save_position` 이 `RuntimeError` | `handle_execution_notice` 예외 전파 0 · 메모리 보유 차감됨 · `[sell_fill_db_error] step=save_position` · 주문 축 완료(pop·`_selling` 해제) |
| T18 (h) | manual 3주 종료 → 전략 7주 종료 | `on_position_closed` 전체 **1회** · `sold_today` 1회 |
| T19 (h) | T1 / T3 | 구독 해제 0 / 1 |

### l-3. J-2 테스트
| ID | 입력 | 기대 |
|---|---|---|
| T20 | 보유 6, `_cancel_and_reorder(remaining=6)` | 취소 1 · 발사 1 `quantity=6` · `_order_qty[new]==6` · `verdict=same` |
| T21 | remaining 6, `cancel_order` await 안에서 보유 6→2 로 바꿈 | 발사 `quantity=2` · `verdict=shrunk` WARNING |
| T22 | 취소 전에 포지션 제거 | 취소 1 · 발사 0 · `_selling`·`_selling_since` 비움 · `verdict=gone` · 타이머 키 pop |
| T23 | `_order_strategy` miss(→"momentum"), 보유자 kojiro 6 | 발사 `quantity=6`(전략 한정 조회면 0) |
| T24 | 보유자 2 | 발사 `quantity=remaining` · `verdict=ambiguous` |
| T25 | `registry.all` 이 예외 | 발사 `quantity=remaining` · `verdict=error` |
| T26 | ordered 3·체결 1 → remaining 2, 보유 9 | 발사 `quantity=2`(9 아님) |

### l-4. manual-sell 테스트
| ID | 입력 | 기대 |
|---|---|---|
| T27 | 보유 10, fake `src.api.order.place_order` 가 await 안에서 통보 3(payload 3), 장부 lookup None | 라우트 반환 뒤 `ticker not in _selling` · 보유 7 (HEAD = `_selling` 좀비 + 보유 삭제) |
| T28 | `place_order` 예외, 사전 `_selling` 없음 | `_selling`·`_selling_since` 비어 있음 · `success=False` |
| T28b | 사전 `_selling` 있음(자동 매도 중) + `place_order` 예외 | `_selling` **유지** |
| T29 | 정상 접수 | `_selling_since[ticker]` 설정 · `_selling.add` 가 발사 **앞** |

### l-5. AST 가드 (`test_cycle385_ast_b7.py`)
| ID | 단언 |
|---|---|
| A1 | `_handle_sell_fill` 안 `If(test=Compare(total_filled >= ordered_qty))` 가 **정확히 1개**이고 함수 본문 **최상위** 문장 |
| A2 | `_handle_sell_fill` 안 `save_position` 호출이 `except Exception` 핸들러를 가진 `Try` 안에 있다 |
| A3 | `execute_sell` 의 `place_order` 2호출 `quantity=` 가 `Name("send_qty")` · `_order_qty[...]` 대입 2곳 값이 `Name("send_qty")` · `_persist_sell_pending_after_send(quantity=Name("send_qty"))` 2곳 · 각 `await place_order` 와 그 헬퍼 호출 사이 `pos.quantity` 읽기 0 |
| A4 | `_cancel_and_reorder` 안 `_reorder_requery` 호출이 `update_trade_status(CANCELLED)` await **뒤** · 그 호출 ~ `place_order` 사이 `Await` 0 · `place_order` 1개(C4 와 교차) |
| A5 | `_reorder_requery`·`_ticker_holders` 는 **동기 def** · 본문에 `Await` 0 · 최상위 `Try`(`except Exception`) · `_ticker_holders` 가 `registry.all` 을 부르고 `registry.get`·`registry.enabled` 를 부르지 않는다 |
| A6 | `_handle_sell_fill` 이 `_ticker_holders` 를 부른다 · `_order_strategy.get(order_no, "momentum")` 0(G147 교차) |
| A7 | `order_engine.py` 에 문자열 「`cancel_remaining` 또는 `risk.on_tick` 재평가에 위임」 0(J-1 — 고치면 초록) |
| A8 | `routes/trading.py::manual_sell` 의 `_selling.add` 호출 lineno < `place_order` await lineno |
| A9 | `_handle_sell_fill` 안 `pos.quantity` 대입 lineno < (두 번째 `_ticker_holders` 호출 뒤의) 첫 `Await` lineno — 보유 차감이 소유 해석 뒤 첫 await 보다 앞 |

### l-6. 돌연변이 (≥20, 각각 최소 1개가 붉어야 한다)
| # | 돌연변이 | 죽이는 테스트 |
|---|---|---|
| M1 | 보유 차감 줄 삭제 | T1·T2·T4 |
| M2 | `close_position` 을 주문 축으로(보유 무시) | T1·T15 |
| M3 | 차감을 `quantity` 대신 `total_filled` 로 | T3·T8 |
| M4 | `max(0, …)` 제거 | T5 |
| M5 | `[sell_fill_exceeds_holding]` 삭제 | T5 |
| M6 | 남음 분기 `save_position` 삭제 | T1·T2 |
| M7 | `save_position` try 제거 | T17·A2 |
| M8 | `_selling.discard` 를 닫기 묶음 안으로 이동 | T1·T15 |
| M9 | 부분 분기에서 `_selling.discard` | T16 |
| M10 | 남음에서 `on_position_closed` 호출 | T1·T18 |
| M11 | 남음에서 `sold_today.add` | T1 |
| M12 | 남음에서 `delete_position` | T1 |
| M13 | 남음에서 구독 해제 | T19 |
| M14 | ② 신규 단 삭제(momentum 폴백 복귀) | T7 |
| M15 | 모호 시 첫 보유자 채택 | T11 |
| M16 | 보유자 0 이면 닫기 묶음 생략 | T10·T12 |
| M17 | `_order_qty[result] = pos.quantity` 복귀 | T13·A3 |
| M18 | 주 경로 PENDING `quantity=pos.quantity` 복귀 | T13·A3 |
| M19 | 폴백 매핑 `pos.quantity` 복귀 | T14·A3 |
| M20 | J-2 재조회 삭제(remaining 발사) | T21·T22·T23 |
| M21 | J-2 전략 한정 조회(`registry.get(strategy_id)`) | T23·A5 |
| M22 | J-2 모호/예외에서 발사 안 함 | T24·T25 |
| M23 | J-2 수량 = 보유(min 제거) | T26 |
| M24 | J-2 `gone` 에서 `_selling` 유지 | T22 |
| M25 | J-2 재조회를 `cancel_order` 앞으로 | T21·A4 |
| M26 | manual-sell `_selling.add` 를 발사 뒤로(HEAD) | T27·A8 |
| M27 | manual-sell 실패에서 discard 안 함 | T28 |
| M28 | manual-sell 실패에서 무조건 discard | T28b |
| M29 | 주문 축 If 를 `if order_done:` 로 | A1 · g273_ast3/4 |
| M30 | 보유 차감을 첫 DB await 뒤로 | A9 |

### l-7. 돌려야 할 기존 스위트(의미 변경 없음을 확인)
`test_cycle329_mapping_absent_full_fill` · `test_cycle273a_cancel_timer_on_full_fill` · `test_cycle273a_partial_row_full_fill_no_correction` · `test_cycle273b_161580_cross_order_overwrite` · `test_cycle185_cluster1_reset`(LTV 부분 안전 — 보유 6 으로 남고 플래그 유지) · `test_cycle147_sell_fill_strategy_fallback` · `test_cycle235_fill_qty_overrun`(3주 → 2+2 → 첫 통보 부분 차감 3→1, 둘째 클램프 1 → 닫힘, 손익 3주) · `test_order_engine_unsubscribe_on_sell`(case B 두 보유자 — 장부 전략이 보유라 모호 아님) · `test_cycle327_sell_fill_during_insert` · `test_order_engine_sell_fallback`(시나리오 J) · `test_cycle332_cancel_timer_key` · `test_cycle287_krx_after_exit`(K11 — 보유 5 ≥ remaining 2) · `test_cycle295_stop_loss_reorder_mapping`(보유 10 ≥ 7) · `test_cycle295_market_rest_cut`(T10b 보유 3 ≥ 2) · `test_cycle291_pre_nxt_gtp` · `test_cycle358_trade_status_update_miss` · `test_cycle286_nxt_rejection_attribution` · 통합 `test_sell_flow` · `test_reset_daily_state` · 계약 `test_routes_trading` · `test_cycle295_manual_sell_exempt` · AST `test_cycle185_cluster1_ast`·`test_cycle191_cooldown_ast`·`test_cycle147_ast_sell_fill_fallback`·`test_cycle273a_ast_partial_optin_and_timer`·`test_cycle328_sell_pending_helper`·`test_cycle291_ast_scope`(a10c)·`test_cycle295_ast_market_rest`(C4 + `_BYTE_IDENTICAL_PINS` **불변**)·`test_cycle287_ast_scope`(`_FROZEN_SEGMENTS` **불변**, digest 재핀)·`test_cycle319_no_clobbered_module` → **마지막에 전체 스위트**(메모리 `feedback_rerun_suite_after_edit`).
🔴 기존 테스트가 「보유보다 작은 주문의 전량 체결 = 포지션 삭제」를 단언하고 있으면 그것은 **결함을 봉인한 것**이다 — 사유 한 줄과 함께 기대값을 바꾸고 명세 §b 를 인용한다(조용히 지우지 않는다).

### l-8. 핀 재산정(값만, 사유 주석 동반)
- `order_engine.py` whole-file sha 10곳: `test_cycle222a3_ast_followup_fixes.py::_APPROVED_CONTENT_SHA`(자매 4곳 동값 — `test_g3_9b`) · `test_cycle223_ast_donchian_exit_fix` · `test_cycle223f_ast_manual_apply_safeguard` · `test_cycle274_ast_llm_gate` · `test_cycle278_ast_catalog_guards` · `test_cycle282_ast_purity` · `test_cycle290_ast_scope` · `test_cycle294_ast_stage3` · `test_cycle297_ast_scope` · `tests/unit/engine/strategies/test_cycle226_zero_breakout_defense`. 착수 전 `grep -rl <현재 sha 118ebf38…>` 로 다시 센다.
- `routes/trading.py` → `test_cycle287_ast_scope.py::_SRC_TREE_DIGEST` 값만(파일 수 162 불변, `_PINNED_DIR_FILE_COUNTS` 불변).
- `_workspace/test_index.yaml` 재생성(`tools/test_impact/build_index.py`).
- 🔴 `test_cycle295_ast_market_rest.py::_BYTE_IDENTICAL_PINS`(`_cancel_after_wait`·`cancel_remaining`) 가 **붉어지면 범위 밖을 건드린 것**이다 — 재핀하지 말고 되돌린다.

---

## m. 반례 / 한계

1. **혼합 보유**(전략 추적분 + 추적 밖 수동분)에서의 수동 부분 매도는 전략 보유에서 빠진다 — 주식은 구별되지 않는다. 과소 추적이 남고 추적분이 닫힌 뒤에야 sync 가 재채택한다(§i).
2. **같은 체결의 진짜 재전송**이 `increment` 로 오면 이중 차감된다. 증거 0(cycle235 의 「중복」은 오독). `max(0,…)` 이 음수만 막는다.
3. **trade_history `profit_loss` 는 여러 통보 주문에서 마지막 증분으로 덮인다**(`update_trade_status` 가 SET, `trade_history.py:135-137`). B7 이전부터의 성질이고 J-3 계열 — 이번에 고치지 않는다. `daily_realized_pnl`(메모리)은 증분 합이라 정확하다.
4. **manual-sell 의 PENDING INSERT 경계 부재**(cycle327 계열, 현행) — 체결통보가 먼저 보정 INSERT 를 하면 라우트 INSERT 가 UNIQUE 위반 → 「매도 주문 실패」 응답인데 실제로는 팔렸다. 🔴 분할 매도를 쓰기 시작하면 **재클릭 = 추가 매도**다. 운영 수칙: 실패 응답이면 재클릭 전에 잔고·체결을 확인. 시정은 §n F-385-1.
5. 추적보다 큰 체결(§c)의 손익은 추적 밖 주식에도 전략 매수가를 쓴다(현행 유지).
6. 잔여 보유는 손절 조건이 살아 있으면 **다음 틱에 곧바로 팔린다** — 사용자 전제가 요구한 동작이다. 「일부만 팔고 나머지는 손절선 아래로 버틴다」는 불가능하다(그것은 손절 해제다).
7. `increment` 퇴화에서 우리 주문의 첫 통보가 거짓 「주문 종료」를 만들면 매핑이 비워지고, 잔여 통보가 `map`(등록 뒤)으로 와서 부분으로 읽혀 재주문 타이머가 **이미 끝난 주문**에 걸릴 수 있다 → 30초 뒤 취소 거부로 무해하게 끝난다. 빈도 = `[fill_qty_src_summary] increment=`.
8. `delete_position` 예외는 현행처럼 전파된다(WS 재연결) — 이번 범위 밖.
9. 재시작 뒤 열린 부분 매도 주문의 `_selling` 은 복원되지 않는다(현행). 통보는 장부 lookup 으로 소유가 복구되어 B7 차감은 정상 동작한다.

---

## n. 후속 (한 줄씩 — 이번 사이클 밖)

- **F-385-1** manual-sell 의 접수 후 구간을 `_persist_sell_pending_after_send` 와 같은 경계로(선행 체결 확인 + 넓은 except) — §m-4.
- **F-385-2** 보유 수량 상향 대사(KIS > 추적)는 수동 추가매수 채택 정책 결정이 먼저 — §i.
- **F-385-3** J-3(PARTIAL 행 수량·CANCELLED) 와 다중 통보 `profit_loss` 덮어쓰기 — M-c 숫자 뒤.
- **F-385-4** `_cancel_and_reorder` 재주문 `place_order` 실패 시 `_selling` 해제 — 지금은 `selling_reconcile` 이 ≤15분+180초에 푼다.

---

## o. 09-28 에 확인할 사실 (배포 전)

| # | 무엇 | 어떻게 | 무엇이면 멈추나 |
|---|---|---|---|
| F1 | fields[16] 신뢰 | `[ordered_qty_mismatch]` 건수 | 1건 이상 → 원인 확인 전 배포 보류(보유 축은 안전하지만 주문 축 판독이 흔들린다) |
| F2 | payload 가 실제로 오는가 | 21:30 `[fill_qty_src_summary] map= payload= increment=` · cycle374 `[order_notice] … ord_qty=` 의 SELL 행 | `increment>0` 인데 그날 수동 매매가 없었으면 조사 |
| F3 | 매도 분할 통보 빈도 | `[order_notice]` SELL 을 `order_no` 로 묶어 통보 수(SOR 분할 = 2) | 정보용(부분 경로가 실전에서 도는지) |
| F4 | **B7 운영 서명(과거 30일 + 09-28)** | `system_logs` 에서 「포지션 동기화 (체결통보 누락 보완)」 WARNING 이 **같은 날 먼저 SELL 체결이 있었던 종목**에 뜬 건수(psql 은 `timestamp AT TIME ZONE 'Asia/Seoul'`) + 「매도 체결: 포지션 없음」 · `[sell_fill_strategy_lookup_fallback]` 건수 | 정보용 — 결함이 실제로 밟혔던 횟수와 momentum 함정 빈도. 보고서에 「실측」으로 옮기기 전에 행을 눈으로 확인(전칭 명제 금지) |
| F5 | 추적 ↔ 실보유 기준선 | 장 마감 뒤 `GET /api/trading/positions` 종목별 수량 vs KIS 잔고 수량 | 불일치가 있으면 **배포 전 기록**(B7 탓으로 오귀인 방지 — 수동 추가매수 B-2 계열일 가능성) |
| F6 | 사용자 MTS 시험 주문(워크리스트 19) | 봇 보유 종목의 **매도**가 있었는지 | 🔴 B7 배포 전에는 봇 보유 종목의 **부분 수량 매도를 하지 않는다**(현행 코드가 잔여를 추적에서 지운다). 했다면 F4 서명이 그 종목에 떠야 한다 = 실전 재현 증거 |
| F7 | `_selling` 기준선 | `[selling_hold]` · `[selling_reconcile]` 건수 | 정보용 |
| F8 | 부분 매도 기준선 | `[fill_partial_no_reorder]` · 「매도 잔여 취소」·「손절 잔여 재주문」 · `[trade_status_update_miss] status=PARTIAL side=SELL` | 정보용(5개월 0 이 기대값) |
| F9 | 배포 순간 전제 | KIS 일별 주문 `sll_buy_dvsn_cd=01 ∧ rmn_qty>0` = 0 · 상태 API `_selling` 비어 있음 · 장외 창 · 🔴 20:00~21:35 아님 | 열린 매도 주문이 있으면 그 종료 뒤로 미룬다(재시작이 `_selling` 을 비운다) |

배포 뒤 D+1 판독: `[sell_fill_holding_remains]`(분할 매도를 했다면 건별 1행) · `[sell_fill_owner_from_holding] from=none`(MTS 매도가 있었다면) · `[sell_fill_owner_ambiguous]`·`[sell_fill_exceeds_holding]`·`[sell_fill_db_error]` = 0 · 대시보드 보유 수량이 KIS 와 같음.

---

## 현 코드·정본과의 정합성

| 항목 | 판정 |
|---|---|
| **충돌** `src/engine/CLAUDE.md:557` 「부분 체결은 full-fill 한정이라 잔량 청산모드가 자연 보존된다」 | 「주문 전량」→「보유 0」으로 뜻이 바뀐다. 의도(보유 중 flag 유지)는 그대로이고 더 정확해진다 → 문서 갱신 |
| **충돌** `handle_execution_notice` docstring 「매도: … 포지션 제거」(`:2337`) · `routes/trading.py` manual_sell docstring 의 stale `_selling` 문장 | 같은 커밋에서 사실대로 |
| **충돌** `src/engine/CLAUDE.md` 「체결통보 주문수량」 절의 매도 피해 서술 · order_engine 절 #1.5 의 「sync 는 기보유 수량을 갱신하지 않으므로」 | 사실은 유지, B7 의 보유 축 한 줄 추가 — `/sync-docs`(report-writer) 후보. 신규 마커 6종 기재 |
| cycle329 「전량 판정에 출처 게이트 금지」·「재주문 타이머 map 한정」 | 유지(보유 축에도 게이트 없음) |
| cycle332 `(ticker, side)` 키 · 해제 `order_no` 게이트 | 무접촉 |
| cycle327/328 접수 후 경계 · 넓은 `except` | 무접촉(인자 값만) |
| cycle331 B-2 · 매수 축 전체 · A-ATOMIC | 무접촉 |
| fields[9] 체결수량(`handler.py:737`, cycle235) | 무접촉 — `handler.py` diff 0 |
| G2-STRUCT-INVARIANT | 제거 site 함수 집합 불변, 훅 동반 |
| 선택지 | 사용자가 이미 **변경**을 골랐다. 「현 상태 유지」는 수동 부분 매도 금지를 운영 수칙으로만 지키는 것 |

## 8영역 · 파일 면적

| 파일 | 8영역 | 변경 |
|---|---|---|
| `src/engine/order_engine.py` | ✅(승인) | `_handle_sell_fill`(소유 해석 · 보유 축 · 닫기/저장 묶음 · 마커) · `execute_sell` 발사 수량 7자리 · `_cancel_and_reorder`(J-2 + J-1 주석) · 신규 동기 메서드 `_ticker_holders`·`_reorder_requery` |
| `src/routes/trading.py` | ✗ | `manual_sell` `_selling` 순서·실패 되돌림·docstring |
| `src/realtime/handler.py` | — | **무접촉** |
| `src/engine/scheduler.py` | — | **무접촉**(§i) |
| `src/db/*` | — | 무접촉(`save_position` 기존 함수 재사용) |

**배포**: `src/` 변경 = full(backend 재시작). 창 = 21:35~익일 07:45 · 주말·공휴일, 보유 중 장중 금지. 계획상 09-28 판독 뒤(워크리스트 「다음 주말」). 같은 주말에 order_engine 을 만지는 다른 카드(카드 E+J-4)가 먼저 착지하면 줄 앵커·핀을 그 위에서 다시 잡는다.

---

## 부록 R — 검토 반영(F-1·F-2·F-3·a~d)

- 작성: domain-expert · 2026-09-27(일) KST · 워크트리 `auto_stock_c385`(B7+J-2+J-1 구현 위, 미커밋). 줄 번호는 **이 부록 작성 시점의 워크트리 줄**이다.
- 입력: 검토 2건(둘 다 GO)의 F-1(MEDIUM) · F-2(LOW, HEAD 대비 회귀) · F-3(사용자 전제 공백) + a~d. 재현 프로브 = scratchpad `c385/test_probe_adv.py::test_p1/p2/p3` · `c385/probe/test_repro_reconcile_double_count.py`.
- 사용자 전제(09-26) 「잔여보유수량에 대한 추가매도가 가능하도록 실시간잔고의 매도상황을 추적관리」를 세 불변식으로 푼다. 이 부록의 모든 규칙은 이 셋 중 하나를 지키기 위해 있다.
  - **R-INV-1 추적 밖 실보유 0** — 추적 수량이 실제보다 **작아지는** 방향(과소 추적)은 어떤 경로·어떤 실패에서도 만들지 않는다. 과대 추적은 허용한다(다음 매도의 APBK0400 → #1.5 재대조가 회수한다).
  - **R-INV-2 우리 주문 합 ≤ 추적 수량** — 걸려 있는 우리 매도 + 새로 내는 우리 매도가 추적 수량을 넘지 않는다. 계좌에 추적보다 많은 주식(운영자가 따로 산 몫)이 있어도 우리 주문이 그 몫을 팔지 않는다.
  - **R-INV-3 잔여는 팔 수 있어야 한다** — 다른 주문이 일부를 잠가도, 잠기지 않은 추적 잔여는 손절이 판다. 동결은 「팔 수 있는 추적 잔여가 0」일 때만.
- 사용자 규칙 「새 제안 금지」 — 이 부록은 지적 7건만 다룬다. 범위 밖은 R-13 끝 한 줄.

### R-0. 결론 (한눈에)

| 지적 | 판정 | 처방 한 줄 | 파일 |
|---|---|---|---|
| F-1 | 재현됨(test_p1: HEAD 발사 `[10,7]` / B7 `[10,4]` — 실보유 7) | #1.5 재대조 때 **주문별로 「스냅샷에 이미 반영된 체결」을 크레딧으로 기록**하고, 늦게 온 통보는 크레딧을 먼저 소진한 뒤 **초과분만** 보유에서 뺀다. 주문 조회 실패 = 종목 단위 크레딧(과대 추적 방향) | `order_engine.py` · `api/balance.py`(`pdno=` 키워드 1개) |
| F-2 | 재현됨(test_p2: B7 재발사 0 / HEAD 3) | manual 라우트 주문을 **명시 표식** `_manual_sell_orders` 로 등록하고, J-2 는 그 표식 주문이면 보유와 무관하게 `remaining` 을 쏜다 | `order_engine.py` · `routes/trading.py` |
| F-3 | 전제 공백 확인 | `[sell_qty_partial_locked]` 에서 `fire = sellable − (held − 추적)` 이 1 이상이면 그 수량을 판다. 0 이하 또는 `sellable == 0` 이면 현행 동결 | `order_engine.py` |
| (c) LOW #3 | **운영자 몫을 팔 수 있다**(R-3-2 수치) → 닫는다 | `_selling` 해제를 「그 표식의 **주인**이 끝났을 때」로 좁힌다 — 무관한 주문의 종료는 풀지 않는다(동결 대기 중일 때만 예외) | `order_engine.py` · `routes/trading.py` |
| (a) | 사실과 다른 docstring | 문구 교체 | `order_engine.py:2345` |
| (b) | M22b 생존 | `_ticker_holders` 가 예외를 던지는 테스트 1건 | 테스트 |
| (d) | 이름 캐시 miss 시 저장된 종목명을 빈 값으로 덮는다 | upsert 가 **빈 이름으로는 저장된 이름을 덮지 않는다** | `db/positions.py:39` |

---

### R-1. F-1 — 재대조와 통보 차감의 멱등

#### R-1-1. 결함 (재현 경로)
```
kojiro 추적 10 · 계좌 10.  MTS 3주 전량 체결(거래소) → 계좌 7, 통보는 아직 오는 중
손절 execute_sell  send 10 → APBK0400
  #1.5 get_balance → held 7 · sellable 7 → [sell_qty_reconciled] pos.quantity = 7   (:2021)
  ◀ 늦은 MTS 통보 3 → B7 보유 축이 다시 뺀다: 7 → 4                             (:2939)
  재발사 4 → 체결 → 추적 0, 계좌 3 = 손절 밖 3주 (사용자 전제 정면 위반)
```
HEAD 는 이 통보를 momentum 폴백으로 흘려 kojiro 를 안 건드렸기 때문에 우연히 7 을 쐈다. B7 이 소유자를 제대로 찾으면서 이중 차감이 드러났다. 트레이더 말로 — 「잔고를 새로 떠 왔는데, 그 잔고에 이미 빠진 3주의 체결 문자가 뒤늦게 오니까 한 번 더 뺐다.」

#### R-1-2. 상태 (order_engine `__init__`, `:396` `_trade_status_update_miss_logged` 뒤)
| 이름 | 타입 | 뜻 |
|---|---|---|
| `_sell_notice_seen` | `dict[str, int]` | 정규화 주문번호 → 그날 `_handle_sell_fill` 이 처리한 **매도 유효 증분 누적**(출처 무관, 주문 종료에도 pop 하지 않는다). `_filled_qty` 는 주문 종료와 `increment` 퇴화에서 매 통보 pop 되므로 이 용도로 못 쓴다 |
| `_sell_reflected_credit` | `dict[str, int]` | 정규화 주문번호 → 재대조 스냅샷에 **이미 반영됐지만** 통보가 아직 처리되지 않은 체결 수량 |
| `_sell_blind_credit` | `dict[str, int]` | ticker → 주문 조회가 실패했을 때의 종목 단위 크레딧(R-1-5) |

- 모듈 수준 순수 함수 `_odno_key(s) -> str` = `str(s).strip().lstrip("0") or "0"`. 세 경로(REST 응답 `result.order_no` · 통보 `fields[2]` · TTTC0081R `odno`)의 0-패딩 차이를 흡수한다(서로 다른 주문번호는 앞 0 을 떼도 서로 다르다). cycle379 는 `strip()` 비교만 했고 운영에서 맞았지만, 여기서는 불일치 = 크레딧 미소진 = **이중 차감**이라 한 단계 더 방어한다.
- `reset_daily_state()`(`:3425` 뒤) 가 셋을 `clear()` 한다(주문번호는 하루 단위로만 유일 — `_order_division` 선례).

#### R-1-3. 재대조 규칙 — `execute_sell` #1.5 `[sell_qty_reconciled]` 분기(`:2008-2041`)
순서가 계약이다.

| # | 단계 | 동기/await | 규칙 |
|---|---|---|---|
| 1 | 잔고 스냅샷 `holdings = await get_balance()`(`:1985`) | await(기존) | 시각 **t1**. `held`·`sellable` |
| 2 | 분기 판정 `0 < sellable < pos.quantity` ∧ 부분잠김 아님 | 동기(기존) | 무변경 |
| 3 | **(신규)** `rows = await get_daily_orders(exchange="ALL", pdno=ticker)` | await | 시각 **t2**. **반드시 1 뒤**(t1 < t2 → 크레딧이 모자랄 수 없다, R-1-6). `try/except Exception` → `fills = None` |
| 4 | **(신규)** `fills = _sell_fills_by_order(rows, ticker)` | 동기·순수 | R-1-4 |
| 5 | **(신규)** 재검증 `strategy.state.positions.get(ticker) is pos` | 동기 | 거짓이면 `[sell_qty_reconcile_skipped] reason=position_replaced` INFO → `continue`(루프 상단 재조회가 소멸·교체를 처리한다). **여기부터 7 까지 await 0** |
| 6 | **(신규)** 크레딧 기록 | 동기 | `fills` 정상 → 행의 각 주문 `o` 에 `c = fills[o] − _sell_notice_seen.get(o, 0)`; `c > 0` 이면 `_sell_reflected_credit[o] = c`, 아니면 `pop(o)`. 그리고 `_sell_blind_credit.pop(ticker, None)`(정확한 자료가 있으면 종목 크레딧은 폐기). `fills is None` → `_sell_blind_credit[ticker] = max(0, pos.quantity − target_qty)`(이 동기 시점의 `pos.quantity`) + `[sell_qty_reconcile_orders_unavailable]` WARNING |
| 7 | `pos.quantity = target_qty`(기존 식 그대로 = held) · **`sell_cap = None`**(R-2) | 동기 | 기존 |
| 8 | `[sell_qty_reconciled]` 기존 문구 끝에 ` credit_src=orders\|blind credit_orders=%d credit_qty=%d` | 동기 | prefix 불변(기존 caplog 단언 호환) |
| 9 | `await save_position(...)` → `continue` | await(기존) | 무변경 |

- **판정(2)과 대입(7) 사이에 await(3)이 새로 끼는 것에 대한 논증** — 하드 불변식 「검사와 그 검사가 지키는 행동 사이에 await 를 넣지 않는다」와의 정합: 7 의 대입은 「t1 에 계좌 보유 = held, 반영됐지만 미처리인 통보 = 크레딧」이라는 **절대 진술**이다. await 동안 `pos.quantity` 가 통보로 어떻게 바뀌었든(그 통보는 `_sell_notice_seen` 에 이미 들어가 크레딧 계산에서 빠진다) 진술은 성립한다(R-1-6 증명). 그래서 재검증은 **객체 동일성**(5)만 하고 수량 술어는 다시 보지 않는다. 동일성 재검증을 빼면 await 중 닫힌 포지션의 분리된 객체에 held 를 쓰고 `save_position` 이 DB 행을 **되살린다**(MR6).
- `get_daily_orders` 는 `get_balance` 처럼 분기 안 lazy import(`from src.api.balance import get_daily_orders`) — 테스트가 `src.api.balance.get_daily_orders` 모듈 속성을 패치한다.

#### R-1-4. 파서 `_sell_fills_by_order(rows, ticker) -> dict[str, int] | None` (동기 · 순수 · never-raise)
1. `rows` 가 list 가 아니면 `None`.
2. `len(rows) >= 100` → `None`(실전 1쪽 상한. `get_daily_orders` 는 연속조회를 하지 않으므로 가득 찬 쪽은 잘렸을 수 있다. 종목 필터 뒤 100건은 사실상 불가능하니 실전에서는 도달하지 않는다. 모의 1쪽 15건은 모의에서만 fallback 을 탄다).
3. 필터: `str(row.get("pdno","")).strip() == ticker` ∧ `str(row.get("sll_buy_dvsn_cd","")).strip() == "01"`(매도). 나머지 행은 **무시**(서버가 PDNO 를 무시하는 퇴화에 대비한 클라이언트 필터 — MR11).
4. 필터를 통과한 행에서 `odno` 가 비었거나 `tot_ccld_qty` 가 정수 문자열이 아니면 → **전체 `None`**. 부분 신뢰 금지 — 한 주문이 빠지면 그 주문의 늦은 통보가 이중 차감된다(R-INV-1).
5. 같은 `odno` 의 여러 행(SOR)은 `tot_ccld_qty` **합**(cycle379 `buying_reconcile` B 단계 선례 「행이 여럿(SOR)이면 수량은 합」).
6. 반환 `{_odno_key(odno): 합}`. 정정·취소 주문 행은 자기 `odno` 를 갖고 `tot_ccld_qty` 가 0 이라 무해하다.

#### R-1-5. 통보 차감 — `_handle_sell_fill` 보유 축(`:2929` 주석 뒤 · `:2931` `if pos is not None:` 앞, 동기)
```python
k = _odno_key(order_no)
self._sell_notice_seen[k] = self._sell_notice_seen.get(k, 0) + quantity
a_order = min(quantity, self._sell_reflected_credit.get(k, 0))
if a_order:
    left = self._sell_reflected_credit[k] - a_order
    if left > 0: self._sell_reflected_credit[k] = left
    else:        self._sell_reflected_credit.pop(k, None)
rest = quantity - a_order
a_blind = min(rest, self._sell_blind_credit.get(ticker, 0))
if a_blind:  # 같은 방식으로 차감·pop
    ...
hold_dec = rest - a_blind
if a_order or a_blind:
    logger.warning("[sell_fill_credit_absorbed] order_no=%s ticker=%s fill=%d absorbed_order=%d "
                   "absorbed_blind=%d hold_dec=%d src=%s", ...)
```
그 뒤 기존 보유 축의 `quantity` 두 자리를 `hold_dec` 로 바꾼다 — `[sell_fill_exceeds_holding]` 비교(`:2933`, `fill=` 값도 `hold_dec`)와 `pos.quantity = max(0, held_before - hold_dec)`(`:2939`).
- **손익은 그대로 `quantity`**(`:2926`) — 흡수분도 실제로 판 주식이고, 재대조는 손익을 적지 않았다.
- 원장·흡수는 `pos` 유무·모호 여부·출처와 **무관하게 무조건** 돈다(출처 게이트 없음 — A10 유지). `pos` 가 없으면 흡수만 되고 보유 축은 현행 의미 그대로.
- 닫기 묶음(`:2948-2962`)의 `del` 과 같은 동기 구간에서 `self._sell_blind_credit.pop(ticker, None)`.
- 주문별 크레딧은 **자기 주문의 통보만** 소진한다. 우리 재발사 체결이 먼저 와도 MTS 주문의 크레딧을 먹지 않는다(MR4 — 먹으면 유령 3주가 남는다).

#### R-1-6. 왜 추적 밖 실보유가 생기지 않나 (증명)
- 주문 `o` 의 t1 까지 체결 `C_o(t1)`, t2 까지 `C_o(t2) ≥ C_o(t1)`, 6 시점까지 처리한 통보 `S_o`. 크레딧 `K_o = max(0, C_o(t2) − S_o) ≥ max(0, C_o(t1) − S_o)` = 「held 에 반영됐지만 아직 안 뺀 것」.
- 한 주문의 통보는 체결 순서대로 오므로 재대조 뒤 `o` 의 처음 `K_o` 주가 흡수되고, 반영분은 그 안에 전부 들어간다 → 반영분은 두 번 빠지지 않는다 → **최종 추적 − 최종 실보유 = Σ_o (t1 이후 ~ 6 시점 사이 체결) ≥ 0**. 오염(유실 통보)은 절대 대입이 지우므로 과대분에 남지 않는다.
- 과대분 = 재대조 창(수백 ms) 안의 체결뿐 → 다음 매도 APBK0400 1건 → #1.5 가 다시 맞춘다. 과소는 0.
- 종목 크레딧(조회 실패) `K = pos_sync − held` 도 같은 식으로 최종 추적 − 실보유 = 오염 E(≥0) 또는 await 중 처리된 t1 이후 체결 ≥ 0 → 과소 0. 대가는 E 만큼의 일시 과대(R-13-4).
- **전제**: 우리 매수는 보유 종목에 나가지 않는다(`is_ticker_blocked_for_buy`). 운영자 수동 매수가 t1 전에 있었으면 held 에 들어가 채택된다 — 현행 #1.5 와 같은 성질(F-385-2 채택 정책, 이번 범위 밖).

#### R-1-7. KIS 호출
| 항목 | 값 |
|---|---|
| TR | `TTTC0081R`(실전) / `VTTC0081R`(모의) 주식일별주문체결조회 — `settings.get_tr_id("TTTC0081R")`(하드코딩 금지) |
| 경로 | GET `/uapi/domestic-stock/v1/trading/inquire-daily-ccld` — 기존 `src/api/balance.py::get_daily_orders`(`:226`) 재사용, `_request` 경유(rate limit·재시도·`[kis_rejection]` 자동) |
| 변경 | `get_daily_orders(target_date="", exchange="ALL", *, odno="", pdno="")` — keyword-only `pdno` 추가, params `"PDNO": pdno`(`:248`). **기본값 호출 params byte 동일**(cycle379 `odno=` 선례, D1 회귀 가드 형식) |
| 요청 값 | `INQR_STRT_DT=INQR_END_DT`=오늘 KST · `SLL_BUY_DVSN_CD="00"`(무변경 — 매도 필터는 클라이언트) · `PDNO=ticker` · `CCLD_DVSN="00"` · `INQR_DVSN="00"`(역순) · `EXCG_ID_DVSN_CD="ALL"`(KRX+NXT+SOR) · `ODNO=""` · CTX 공란(1쪽) |
| 쓰는 응답 필드 | `output1[]` 의 `odno` · `pdno` · `sll_buy_dvsn_cd` · `tot_ccld_qty` (그 밖은 읽지 않는다) |
| 1쪽 | 실전 100건 · 모의 15건(정본 개요) |
| 빈도 | `[sell_qty_reconciled]` 분기 1회 진입당 1건(execute_sell 1회 최대 3건). 잔고(TTTC8434R) 1건 뒤에 붙는다. 실전 한도 18건/초/앱키(2026-04-20 공지) 대비 무시 가능 |
| 쓰지 않는 것 | TTTC8408R(매도가능수량조회) — `sll_qty` 는 종목 합이라 주문별 멱등이 안 되고 당일/누적 정의가 정본에 없다. TTTC0084R(정정취소가능) — 체결 누적이 아니다 |
| F-3 | **새 호출 0** — 같은 TTTC8434R 스냅샷의 `hldg_qty`(held)·`ord_psbl_qty`(sellable)만 쓴다 |

#### R-1-8. 실패 모드 — 어느 쪽으로 넘어지나
| 상황 | 동작 | 방향 |
|---|---|---|
| TTTC0081R 예외·타임아웃·거부(`KisApiError`) | 종목 크레딧 `pos − held` 기록 후 **재대조는 진행**(재발사 held) + `[sell_qty_reconcile_orders_unavailable] reason=error` | 과대 추적(안전), 손절 정지 없음 |
| 행 불량(odno 공백·수량 비정수) | 같음, `reason=bad_row` | 같음 |
| 1쪽 가득(≥100) | 같음, `reason=page_full` | 같음 |
| 잔고 TTTC8434R 실패 | **현행 그대로** — `sellable is None` → 일반 재시도, 재대조 없음 | 무변경 |
| await 중 포지션 소멸·교체 | 재대조 안 함, `[sell_qty_reconcile_skipped]` → `continue` | — |
| 크레딧 주문의 통보가 끝내 안 옴(유실) | 크레딧이 소진되지 않고 남는다 — 무해(held 가 이미 정답), 일일 clear | — |
| 주문번호 0-패딩 형식 차이 | `_odno_key` 가 흡수 | — |

「실패 시 재대조를 하지 않는다」(= 현행 잔고 실패와 같은 처리)는 **택하지 않는다** — TTTC0081R 만 막혀도 오염된 포지션의 손절이 그 사이 멈춘다(추적 10 을 계속 내고 계속 APBK0400). 「실패 시 크레딧 없이 재대조」(= 지금 B7)는 R-INV-1 위반이다.

---

### R-2. F-3 — 외부 부분 매도가 걸려 있어도 잔여는 판다

#### R-2-1. 결함
`[sell_qty_partial_locked]`(`:1996-2007`): `held ≥ 추적` ∧ `0 < sellable < 추적` → 보존 + `_selling` 유지 + return. `selling_reconcile` 은 열린 매도가 있는 동안 `open_order` 로 유지한다. 결과 — 운영자가 MTS 로 3주 지정가를 걸어 둔 동안, 안 잠긴 추적 7주의 손절이 **그 주문이 끝날 때까지** 멈춘다(R-INV-3 위반).

#### R-2-2. 규칙 (`:1996` 분기 교체)
```python
elif 0 < sellable < pos.quantity and held_qty >= pos.quantity:
    surplus = held_qty - pos.quantity        # 계좌 − 추적 = 추적 밖 초과분(운영자 몫)
    fire = sellable - surplus                # = 추적 − (held − sellable) = 추적 − 걸린 매도 전부
    if fire >= 1:
        sell_cap = fire
        logger.warning("[sell_qty_partial_sellable] ticker=%s strategy=%s held=%d sellable=%d "
                       "positions=%d surplus=%d fire=%d", ...)
        continue                              # 루프 상단에서 send_qty = min(pos.quantity, sell_cap)
    logger.warning("[sell_qty_partial_locked] ... (기존 문구) surplus=%d fire=%d", ...)
    self._selling_locked_wait.add(ticker)     # R-3 — 이 동결이 기다리는 것은 「걸린 주문의 끝」
    return
```
- `pos.quantity` 는 **바꾸지 않는다**(C236-F1: 잠긴 주식도 추적 보유 — 걸린 주문이 취소되면 다시 손절 대상).
- 재시도 루프 앞(`:1670` `last_error` 옆)에 `sell_cap: int | None = None`. 루프 상단(`:1824`):
  ```python
  send_qty = pos.quantity
  if sell_cap is not None:
      send_qty = min(send_qty, sell_cap)      # 줄이기만 한다 — 대기 중 체결로 추적이 줄었으면 그쪽이 이긴다
  ```
  F-1 재대조 분기는 `sell_cap = None`(새 절대 상태가 이전 상한을 무효로 한다). 폴백 발사도 같은 `send_qty` 를 쓴다(§a-2 규칙 그대로).
- `sellable == 0 ∧ held > 0`(`[sell_qty_locked]` `:2042-2057`) = **현행 그대로**(사용자 지시) + return 직전 `self._selling_locked_wait.add(ticker)`.
- **수식 근거** — `held − sellable` 은 이 종목에 걸린 매도 전부(우리 것·manual·MTS, 매핑 여부 무관 — 재시작 뒤 매핑이 사라진 우리 주문도 들어간다)다. `fire = 추적 − 걸린 전부` 이므로 **우리 새 주문 + 걸린 전부 ≤ 추적**(R-INV-2). 초과분이 없으면(`held == 추적`) `fire = sellable` = KIS 가 허락하는 전부(R-INV-3). 걸린 매도에 우리 자신의 주문이 섞여 있어도 이미 빼고 계산하므로 **우리 잠긴 주식을 두 번 파는 일이 없다**.
- 트레이더 말로 — 「MTS 로 3주 지정가 걸어둔 사이 손절이 오면, 안 잠긴 7주는 바로 던진다. 계좌에 전략 몫보다 많이 있으면(운영자가 따로 산 것) 걸린 주문은 먼저 전략 몫을 파는 것으로 보고, 그만큼 덜 던진다 — 운영자 몫은 절대 우리가 안 판다.」

#### R-2-3. 동작 예
| 추적 | held | sellable | 걸린 매도 | fire | 결과 |
|---|---|---|---|---|---|
| 10 | 10 | 7 | MTS 3 | 7 | 7 발사. 7 체결 → 추적 3, `_selling` 해제(우리 주문 종료) → 다음 틱 3 발사 → sellable 0 → `[sell_qty_locked]` 동결 → MTS 3 체결(동결 대기 해제) → 추적 0 |
| 3 | 3 | 1 | 2 | 1 | 1 발사(기존 cycle236 테스트의 입력 — 기대값 변경, R-10) |
| 10 | 15 | 8 | 7 | 3 | 3 발사. 운영자 몫 5 는 보존 |
| 10 | 15 | 5 | 우리 10(매핑 잃음) | 0 | 동결 — 우리 주문이 이미 추적 전부를 팔고 있다(R-3 프로브 경로) |
| 3 | 3 | 0 | 3 | — | `[sell_qty_locked]` 현행 동결 |

---

### R-3. (c) LOW #3 — 「무관한 주문의 종료가 `_selling` 을 푼다」

#### R-3-1. 무엇인가
`_handle_sell_fill` 주문 축 종료(`:2984` If 안 `:2988`) `self._selling.discard(ticker)` 가 **그 종목의 어느 주문이든** 끝나면 표식을 푼다. 우리 손절 주문이 호가에 걸려 있거나 아직 발사 중(`await place_order`)이어도 MTS 주문 하나가 끝나면 풀린다.

#### R-3-2. F-3 과 합쳐서 운영자 몫을 팔 수 있나 — **팔 수 있다** (그래서 닫는다)
```
kojiro 추적 10 · 운영자 초과 10 · 계좌 20
손절 execute_sell  send 10 → await place_order 중
  ◀ MTS 3 전량 체결(매핑 없음) → B7: 추적 10→7 · 주문 종료 → _selling 해제   ← LOW #3
  우리 주문 A 10 접수, 호가에 걸림(10 잠김)
다음 틱 손절 → execute_sell(7): sellable = 17 − 10 = 7 ≥ 7 → **1차에서 접수**
  → 우리 주문 합 17 > 추적 10 → 운영자 몫 7주를 판다 (R-INV-2 위반)
```
- F-3 의 `fire` 식은 APBK0400 뒤(#1.5)에만 탄다. 이 경로는 **1차 발사가 통과**해 버려 F-3 이 개입할 틈이 없다 → F-3 만으로는 못 막는다. `_selling` 해제 규칙 자체를 닫는다.
- 초과분이 작으면(계좌 13) 1차 7 이 APBK0400 → #1.5 held 10 · sellable 0 → `[sell_qty_locked]` 동결 → 안전. 즉 **운영자 초과분 ≥ 추적 잔여**일 때만 뚫린다 — 드물지만 운영자 몫을 파는 결함이라 이번에 닫는다.
- HEAD 도 같은 해제가 있었지만 추적을 줄이지 않아(10 그대로) 2차 발사가 10 이었다 — 초과분 ≥ 10 이어야 뚫렸다. B7 이 추적을 정확히 줄이면서 문턱이 낮아졌다.

#### R-3-3. 규칙 — `_selling` 은 **주인이 끝났을 때만** 푼다
상태(`__init__`):
| 이름 | 타입 | 뜻 |
|---|---|---|
| `_selling_locked_wait` | `set[str]` | `_selling` 이 **걸린 외부 주문의 끝을 기다리는 동결**로만 서 있는 종목(`[sell_qty_locked]`·F-3 `fire ≤ 0` 에서 add) |
| `_sell_orders_done` | `set[str]` | 그날 주문 축이 끝난 매도 주문번호(출처 무관) |
| `_manual_sell_orders` | `dict[str, bool]` | manual 라우트 주문번호 → 그 주문이 `_selling` 을 **세웠는가**(`_added`) — R-4 와 공용 |

동기 헬퍼 2개(await 0):
```python
def _sell_end_releases_selling(self, ticker: str, order_no: str, qty_src: str) -> bool:
    """주문 축 종료가 `_selling` 을 풀어도 되는가 — 순수 판정."""
    if qty_src == "map":                                  # 우리가 낸 주문(매핑 확정)
        return self._manual_sell_orders.get(order_no, True)   # manual 손님 주문(False)은 주인이 아니다
    return ticker in self._selling_locked_wait            # 매핑 없는 종료 = 동결이 기다리던 것일 때만

def _sell_placed(self, ticker: str, order_no: str, *, owns_selling: bool) -> None:
    """발사 성공 직후(동기) — 그 주문이 await 창 안에서 이미 끝났으면 여기서 푼다. never-raise."""
    try:
        if owns_selling and order_no in self._sell_orders_done:
            self._selling.discard(ticker)
            self._selling_locked_wait.discard(ticker)
            logger.info("[selling_released_after_window] ticker=%s order_no=%s", ...)
    except Exception:
        logger.warning("[selling_released_after_window] 판정 실패 — 무시: %s", ticker, exc_info=True)
```

적용 자리:
| 자리 | 변경 |
|---|---|
| `_handle_sell_fill` 주문 축 If(`:2984`) 첫 문장 | `self._sell_orders_done.add(order_no)` 뒤, 기존 무조건 `self._selling.discard(ticker)`(`:2988`)를 → `if ticker in self._selling:` 안에서 `_sell_end_releases_selling(...)` 참이면 `discard` + `_selling_locked_wait.discard`, 거짓이면 `[selling_kept]` WARNING. If 자체(문자 그대로·최상위·1개 — A1)와 나머지 문장은 **무변경** |
| `execute_sell` 주 경로 | 매핑 블록 끝(`:1843` `_order_division` 대입) 뒤 · `_persist_sell_pending_after_send`(`:1847`) 앞: `self._sell_placed(ticker, result.order_no, owns_selling=True)` |
| `execute_sell` 폴백 | `:2173` 뒤 · `:2177` 앞: 같은 호출(`fb_result.order_no`) |
| `_cancel_and_reorder` 재주문 | `:3384` 결과 블록 안 `_completed_orders.discard`(`:3391`) 뒤: manual 표식 상속(R-4) 다음 `self._sell_placed(ticker, result.order_no, owns_selling=self._manual_sell_orders.get(order_no, True))` |
| `routes/trading.py::manual_sell` | 매핑 3종(`:195-197`) 뒤 · `await insert_trade`(`:212`) 앞: `engine._manual_sell_orders[result.order_no] = _added` 다음 `engine._sell_placed(req.ticker, result.order_no, owns_selling=_added)` |
| `_selling_locked_wait.discard` | `execute_sell` `:1637` `_selling.add` 직후 · 라우트 `_added` 분기의 add 직후 · J-2 `gone` 해제(`:3329`) 옆 · `reset_daily_state` |
| `_selling_locked_wait.add` | `[sell_qty_locked]` return 직전 · F-3 `fire ≤ 0` return 직전 |
| `reset_daily_state()` | `_sell_orders_done`·`_manual_sell_orders`·`_selling_locked_wait` clear(`_selling` 자체는 scheduler `:3616` 이 이미 비운다 — scheduler 무접촉) |

- `:2894`(「매도 체결: 전략 찾을 수 없음」 오류 경로)의 무조건 해제는 **손대지 않는다** — 운영에서 momentum 은 항상 등록돼 있어 도달하지 않는 오류 경로다.

#### R-3-4. 좀비가 새로 생기지 않는가 — `_selling` 을 세운 것마다 푸는 주체
| `_selling` 을 세운 것 | 푸는 주체 |
|---|---|
| `execute_sell` 실행 중(발사 전·재시도 대기) | 그 코루틴의 출구들(현행 — 발사 전 게이트·거부·최종 실패의 discard). **무관한 종료로는 안 풀린다** → 재시도 대기 중 두 번째 `execute_sell` 이 겹쳐 뜨는 틈도 같이 닫힌다 |
| 우리 주문이 걸림(매핑 확정) | 그 주문의 map 종료 · J-2 `gone` · `selling_reconcile`(180초 + 열린 매도 0) |
| 우리 주문이 발사 창에서 끝남(통보가 REST 응답보다 먼저) | `_sell_placed`(발사 직후 동기) |
| 동결(`_selling_locked_wait`) | **어느** 주문의 종료든(매핑 여부 무관) · `selling_reconcile` |
| manual `_added` 참 | 그 주문의 map 종료 · `_sell_placed` · 발사 전 실패 되돌림(현행) |
| manual 손님 주문(`_added` 거짓) | 풀지 않는다 — 주인(자동 매도)이 푼다 |

- **잃는 것 1건** — 우리 주문이 통보 없이 사라진 경우(운영자가 MTS 로 우리 주문 취소 · 거래소 자동취소 · 접수 뒤 거부). 지금은 무관한 주문 종료가 「운 좋게」 풀기도 했는데, 이제는 원래 이 상황의 정식 수습자인 `selling_reconcile` 몫이다(현행과 같은 상한).
- **cycle329 금기(「전량 판정에 출처 게이트 금지」)와 다른가** — 그 금기는 주문 축 「끝났다」 판정과 보유 축 닫기에 출처를 걸어 **종료 자체를 유보**하는 것(B′안)을 막는다. 이 규칙은 둘 다 건드리지 않는다: 종료 판정·장부·매핑 pop·보유 닫기는 모든 출처에서 그대로 일어나고(`_sell_orders_done` 기록 포함), `_selling` 해제에서 **주인 확인**만 한다. 위 표대로 모든 유지 상태에 해제 주체가 있다. A10(보유 차감 출처 게이트 없음)은 그대로 초록이어야 한다.

#### R-3-5. 프로브 판정 (test_p3 형태)
위 규칙 뒤: MTS-9 종료는 매핑 없음 ∧ 동결 아님 → `[selling_kept] reason=unrelated_end` → 우리 주문 A 접수 뒤에도 `_selling` 유지 → 다음 틱 `execute_sell` 은 중복 차단(`:1634`) → 2차 발사 0. A 체결(map 10) → 추적 7 에서 10 을 빼 0(`[sell_fill_exceeds_holding]`) 닫힘 · `_selling` 해제. 계좌 20 − 3 − 10 = 7 = 운영자 몫 그대로(R-INV-2).

---

### R-4. F-2 — manual 라우트 주문은 운영자 의도를 따른다

#### R-4-1. 결함
J-2 `gone`(보유자 0 → 발사 0)이 **manual 라우트로 추적 밖 주식을 판 주문**의 잔여 재주문까지 버린다(test_p2: B7 0 / HEAD 3). 운영자가 「5주 팔아」라고 눌렀는데 2주만 팔리고 3주는 취소된 채 끝난다.

#### R-4-2. 규칙
- **표식**: `routes/trading.py::manual_sell` 매핑 등록(`:195-197`)과 같은 동기 구간에서 `engine._manual_sell_orders[result.order_no] = _added`(R-3-3 표). `strategy_id` 로 추론하지 않는다(`"momentum"` 기본값 함정 — 라우트는 보유 전략이 있으면 그 전략 id 를 쓰므로 manual 주문도 kojiro 등으로 적힌다). `_order_strategy` 값으로도 추론하지 않는다.
- **J-2**: `_reorder_requery`(`:3204`) `try` 첫 문장 — `order_no in self._manual_sell_orders` 이면 보유자 수와 무관하게 `verdict=manual`, 반환 `remaining`(HEAD 행위). 로그 `held=` 는 보유자 조회값을 그대로 적고, 레벨은 보유자 1 ∧ 보유 ≥ `remaining` 이면 INFO, 그 밖(보유 0·부족·모호·조회 실패)은 WARNING.
- **상속**: `_cancel_and_reorder` 재주문 결과 블록(`:3384`)에서 `if order_no in self._manual_sell_orders: self._manual_sell_orders[result.order_no] = self._manual_sell_orders[order_no]` — 재주문이 또 부분 체결되면 다음 J-2 도 manual 규칙을 탄다.
- **안 바꾸는 것**: 비-manual 주문의 J-2 표(`same/shrunk/gone/ambiguous/error`)·`min(remaining, 보유)` 상한·`gone` 의 `_selling` 해제 — 전부 그대로. manual 은 「보유에 맞춘다」 상한도 적용하지 않는다(운영자 주문의 대상이 추적 밖 주식일 수 있다). 과대 요청은 KIS 가 APBK0400 으로 막고 `_cancel_and_reorder` 의 `except` 가 흡수한다(현행 F-385-4).
- 트레이더 말로 — 「운영자가 버튼으로 낸 수량은 운영자 몫이다. 추적 장부에 있든 없든 그 수량을 끝까지 내 준다. 봇 손절 잔여만 장부에 맞춘다.」

---

### R-5. (a) docstring · (b) M22b · (d) 종목명 보존

**(a)** `handle_execution_notice` docstring(`:2342-2346`)을 이렇게 바꾼다:
```
매수: 체결통보 수신 시 포지션 등록 (주문 시점이 아닌 체결 시점)
매도: 체결 수량만큼 손익 계산 + 보유 수량 차감 — 보유가 0 이 될 때만 포지션 제거
      (cycle385 B7 두 축: 주문 축 = 장부·매핑·타이머·`_selling`, 보유 축 = 수량·삭제)
부분 체결: PARTIAL 상태 기록 + 30초 후 잔여 취소(손절 잔여는 보유 재조회 뒤 재주문)
```

**(b)** M22b(`_reorder_requery` 바깥 `except` 의 `return remaining` → `return 0`)가 사는 이유 — T25 는 `registry.all` 을 터뜨리는데 그 예외는 `_ticker_holders` 가 먼저 삼켜 `verdict=error` 분기로 가고 바깥 `except` 에 도달하지 않는다. 바깥 `except` 에 도달하는 테스트가 필요하다 → TR26(R-7).

**(d)** `src/db/positions.py:39` `ticker_name = EXCLUDED.ticker_name,` → `ticker_name = COALESCE(NULLIF(EXCLUDED.ticker_name, ''), positions.ticker_name),`
- 이유 — 빈 이름은 정보가 아니다. 남음 경로(`_handle_sell_fill` `:2972` `ticker_names.get(ticker, "")`)와 #1.5 재대조(`:2026` `t(ticker)` 파생 — miss 면 `""`)가 캐시 miss 때 저장된 이름을 지웠다. 세 호출자(매수 체결·재대조·남음) 모두 이득이고 INSERT(행 없음)는 무변경.
- 호출부 인자는 **그대로** 둔다(order_engine 쪽 변경 0 — 이름을 따로 조회하느라 await 를 더하지 않는다).

---

### R-6. 마커 (신규·변경)
| 마커 | 레벨 | cap | 필드 | 뜻 · 판독 |
|---|---|---|---|---|
| `[sell_qty_reconciled]` (변경) | WARNING | 없음(현행) | 기존 + `credit_src=orders\|blind credit_orders= credit_qty=` | `credit_qty>0` = 재대조 순간 통보가 날아오는 중이었다(F-1 경로가 실제로 쓰였다) |
| `[sell_qty_reconcile_orders_unavailable]` | WARNING | 없음 | `ticker= reason=error\|bad_row\|page_full blind_credit=` | TTTC0081R 을 못 믿어 종목 크레딧으로 갔다. 0 이 정상 |
| `[sell_qty_reconcile_skipped]` | INFO | — | `ticker= reason=position_replaced` | 재대조 조회 중 포지션이 닫혔다 |
| `[sell_fill_credit_absorbed]` | WARNING | 없음 | `order_no= ticker= fill= absorbed_order= absorbed_blind= hold_dec= src=` | 늦은 통보를 이중 차감하지 않았다 = F-1 이 막은 건수 |
| `[sell_qty_partial_sellable]` | WARNING | 없음 | `ticker= strategy= held= sellable= positions= surplus= fire=` | F-3 성공 서명 — 걸린 외부 주문 옆에서 잔여를 팔았다 |
| `[sell_qty_partial_locked]` (변경) | WARNING | 없음 | 기존 + `surplus= fire=` | 이제 `fire ≤ 0`(초과분이 걸린 주문을 덮는다)일 때만 뜬다 |
| `[selling_kept]` | WARNING | 없음(드묾) | `ticker= order_no= reason=unrelated_end\|guest_manual src=` | 주인이 아닌 주문의 종료라 `_selling` 을 안 풀었다 = LOW #3 이 막은 건수 |
| `[selling_released_after_window]` | INFO | — | `ticker= order_no=` | 우리 주문이 발사 창 안에서 끝나 발사 직후 풀었다(정상, 흔함) |
| `[reorder_requery] verdict=manual` (추가) | 보유 ≥ remaining 이면 INFO, 아니면 WARNING | 없음 | 기존 필드 | manual 잔여는 운영자 의도대로 발사 |

전부 `logger.*` 만(새 `write_log`·DB 0), 행위 밖. 신규 `KstDailyEmitCap` 0.

---

### R-7. 테스트 (Red 먼저)
하네스: `tests/unit/engine/test_cycle385_b7_partial_sell.py` 의 `_make_env`·`_sell_notice`·`_map_order`·`_held`·`_install_place_order` 재사용. 잔고는 `src.api.balance.get_balance`, 주문 목록은 `src.api.balance.get_daily_orders` 를 **반드시** 패치(미패치면 실제 KIS 호출 경로를 탄다). 행 모양 = `{"odno":…, "pdno":TICKER, "sll_buy_dvsn_cd":"01", "tot_ccld_qty":"3"}`. caplog 단언은 WARNING 이상 + prefix.

새 파일 · 추가 자리:
- `tests/unit/engine/test_cycle385r_recount_credit.py` — TR1~TR12 (F-1)
- `tests/unit/engine/test_cycle385r_partial_locked_sell.py` — TR13~TR21 (F-3 · c)
- `tests/unit/engine/test_cycle385_reorder_requery.py`(추가) — TR22 · TR24 · TR25 · TR26
- `tests/unit/routes/test_cycle385_manual_sell_selling.py`(추가) — TR20 · TR23
- `tests/unit/db/test_cycle385r_positions_name_keep.py` — TR27
- `tests/unit/api/test_cycle385r_daily_orders_pdno.py` — TR28
- `tests/unit/ast/test_cycle385_ast_b7.py`(추가·A3b 개정) — AR1~AR13

| ID | 입력 | 기대 |
|---|---|---|
| TR1 (test_p1 이식) | kojiro 10. 1차 발사 APBK0400, 이후 수락. 잔고 held 7·sellable 7. 주문 행 `MTS-1` tot 3. `save_position` 첫 호출 안에서 MTS-1 통보 3(payload 3) | 발사 `[10, 7]` · MTS-1 통보 뒤 kojiro 7 · `[sell_fill_credit_absorbed] absorbed_order=3` 1행 · 우리 7 체결(map) → 닫힘. (HEAD `[10,7]` / B7 `[10,4]`) |
| TR2 (repro 이식) | kojiro 10. 거래소 held 7(A 3 체결)·걸린 B 2 → `quantity > 5` 면 APBK0400, 아니면 접수. 행 A tot 3 · B tot 0 | 발사 `[10, 7, 5]`(재대조 → F-3 fire 5) · 크레딧 A 3 · A 통보 흡수 → 7 · 우리 5 → 2 · B 2 → 0 닫힘 · 매 단계 `추적 ≥ 거래소 보유` |
| TR3 (원장이 크레딧을 줄인다) | 추적 11·실보유 10(오염 1). MTS-A 2 체결·통보 처리(추적 9). 발사 가짜는 **전부** APBK0400(재대조만 본다). 잔고 held 8·sellable 8. 행 A tot 2 | 크레딧 A 없음(`2 − 2`) · 재대조 뒤 추적 8 · `execute_sell` 종료 뒤 A 가 3 더 체결 → 통보 3 → 추적 5 (= 실보유 5) |
| TR4 (주문별이지 종목별이 아니다) | TR1 에서 우리 재발사 체결 7(map)이 MTS-1 통보보다 **먼저** | 우리 체결로 추적 0 → 닫힘 · 뒤이은 MTS-1 통보는 흡수만(보유 없음, 예외 0) · 유령 0 |
| TR5 (호출 순서) | 가짜 두 조회가 한 거래소 상태를 공유하고, **먼저 불린 쪽**이 스냅샷을 만든 **뒤** B 2 체결을 일으킨다. 행 A tot 3, B 는 호출 시점 누적 | 최종 `추적 ≥ 거래소 보유`(정상 순서면 추적 7 · 실보유 5 = 과대 2 허용). 순서를 뒤집으면 추적 3 < 5 → 붉다 |
| TR6 (동일성 재검증) | `get_daily_orders` await 안에서 전량 매도 통보(포지션 닫힘) | `[sell_qty_reconcile_skipped] reason=position_replaced` · 닫힌 뒤 `save_position` 호출 0(DB 부활 없음) · `[sell_position_gone]` 로 종료 |
| TR7 (조회 실패 → 종목 크레딧) | TR1 에서 `get_daily_orders` 가 `RuntimeError` | `[sell_qty_reconcile_orders_unavailable] reason=error blind_credit=3` · 발사 `[10, 7]` · MTS-1 통보 흡수 → 7 |
| TR8 (행 불량) | 행 `tot_ccld_qty=""` | `reason=bad_row` · TR7 과 같은 결과 |
| TR9 (SOR 합) | 같은 odno 두 행 tot 1·2 | 크레딧 3 · 통보 1·2 모두 흡수 → 7 |
| TR10 (종목 필터) | 행에 다른 종목 Y 의 매도 Z tot 3(momentum 이 Y 5 보유, Z 통보 미처리) | Z 크레딧 기록 0 · 뒤이은 Y 통보 3 → Y 2 |
| TR11 (닫힐 때 종목 크레딧 정리) | TR7 끝(닫힘) | `TICKER not in _sell_blind_credit` |
| TR12 (일일 정리) | 여섯 구조에 값 → `reset_daily_state()` | 전부 비어 있다 |
| TR13 (F-3 기본 — cycle236 입력) | held 3 · sellable 1 · 추적 3. 1차 APBK0400, 2차 수락 | 발사 `[3, 1]` · 추적 3(하향 보정 없음) · `save_position` 0 · `[sell_qty_partial_sellable] fire=1` · `_selling` 유지(우리 주문 걸림) · 동결 표식 없음 |
| TR14 (초과분 차감) | 추적 10 · held 15 · sellable 8 | 발사 `[10, 3]` |
| TR15 (초과분이 덮으면 동결 = c) | 추적 10 · held 15 · sellable 5(매핑 잃은 우리 10 이 걸림) | 발사 `[10]` 뿐 · `[sell_qty_partial_locked] surplus=5 fire=0` · `_selling` 유지 · `_selling_locked_wait` 에 TICKER |
| TR16 (전량 잠김 현행) | held 3 · sellable 0 | 발사 1 · 추적 3 · `[sell_qty_locked]` · `_selling` 유지 · 동결 표식 set |
| TR17 (동결은 외부 종료가 푼다) | TR15 또는 TR16 뒤 매핑 없는 MTS 통보(payload = qty, 전량) | `_selling` 해제 · 동결 표식 해제 |
| TR18 (test_p3 이식) | kojiro 10. 우리 `place_order` await 안에서 MTS-9 3(payload 3) 전량 | 반환 뒤 `TICKER in _selling` · `[selling_kept] reason=unrelated_end` · 곧바로 `execute_sell` 다시 → 발사 수 불변 · 우리 주문 map 10 체결 → 닫힘 · `_selling` 해제 |
| TR19 (발사 창 자기 종료) | 우리 `place_order` await 안에서 **같은 주문번호** 전량 통보(payload 10). 폴백 변형(APBK1943 → 폴백 안에서 전량) | 반환 뒤 `_selling` 비어 있음 · `[selling_released_after_window]` 1행(주·폴백 각각) |
| TR20 (손님 manual) | 자동 매도 S1 10 걸림(매핑, `_selling` 선재). 라우트로 3주(`_added` 거짓) → 체결 통보 map 3 전량 | `_selling` 유지 · `[selling_kept] reason=guest_manual` · 이어서 S1 map 종료 → 해제 |
| TR21 (진입 시 동결 표식 청소) | 동결 표식만 남은 상태(`_selling` 없음)에서 `execute_sell` 접수 성공(주문 걸림) → 매핑 없는 무관 종료 | `_selling` 유지 |
| TR22 (test_p2 이식) | 보유 전략 0. `_map_order("MAN-1", 5, "momentum")` + `_manual_sell_orders["MAN-1"]=True`. 통보 2(payload 5) → 타이머 | 재주문 1건 `quantity=3` · `[reorder_requery] verdict=manual` WARNING. 대조군(표식 없음) = 발사 0 |
| TR23 (라우트 끝까지) | 라우트 manual 5주(보유 전략 없음 → momentum) → 통보 map 2 → 타이머 | 재주문 `quantity=3` · 재주문 번호가 `_manual_sell_orders` 에 상속 |
| TR24 (상속) | TR22 의 재주문 MAN-2 가 1 부분 체결 → 두 번째 타이머 | 두 번째 재주문 `quantity=2` · `verdict=manual` |
| TR25 (strategy_id 로 추론하지 않는다) | ① manual 표식 주문 sid=`kojiro`, 보유 0 ② 표식 없는 sid=`momentum` 주문, 보유 0 | ① 발사 remaining ② 발사 0(`gone`) |
| TR26 (M22b 킬러) | `engine._ticker_holders` 를 예외를 던지는 함수로 교체 | `_reorder_requery(TICKER, "S1", 6) == 6` · WARNING 「재조회 자체가 실패」 · `_cancel_and_reorder` 경유 발사 `quantity=6` |
| TR27 (d) | 단위: 가짜 `pg.execute` 가 SQL 수집. 통합(CI `DATABASE_URL_TEST`, `pg_harness`): 이름 「삼성전자」 행 → `save_position(ticker_name="")` → `("X")` | SQL 에 `COALESCE(NULLIF(EXCLUDED.ticker_name, ''), positions.ticker_name)` · 빈 이름 저장 뒤 「삼성전자」 유지 · 「X」 저장 뒤 「X」 |
| TR28 (`pdno=`) | `get_daily_orders` 서명 · 기본 호출 params · `pdno="005930"` | keyword-only 기본 `""` · 기본 호출 params 가 직전과 byte 동일(`PDNO: ""`) · `PDNO: "005930"` |

---

### R-8. AST 가드 (`tests/unit/ast/test_cycle385_ast_b7.py` 추가)
| ID | 단언 |
|---|---|
| AR1 | `execute_sell` 에서 `get_balance` await lineno < `get_daily_orders` await lineno. `get_daily_orders` await ~ `pos.quantity = target_qty` 사이 `Await` 0, 그 사이에 `is` 비교(`positions.get(ticker) is pos`)가 있다 |
| AR2 | `_handle_sell_fill` 에서 `_sell_notice_seen[...]` 저장과 `_sell_reflected_credit` 읽기가 `pos.quantity` 대입보다 앞이고, 소유 해석 뒤 첫 `Await` 보다 앞이다(A9 확장). 차감식 우변이 `hold_dec` |
| AR3 | `profit_loss` 곱셈 피연산자는 여전히 `quantity`(흡수가 손익을 바꾸지 않는다) |
| AR4 | F-3 분기(`held_qty >= pos.quantity` 비교를 가진 elif) 안에 `pos.quantity` 대입 0 · `sell_cap` 대입 1 · `return` 앞에 `_selling_locked_wait.add` |
| AR5 | (A3b 개정) 루프 안 `send_qty` 대입은 정확히 2개 — 첫째 `pos.quantity`, 둘째 `If(sell_cap is not None)` 본문의 `min(send_qty, sell_cap)`. 둘 다 재조회 뒤 · 첫 발사 앞 |
| AR6 | 주문 축 If 안에 `_sell_orders_done.add(order_no)` 가 있고, 그 If 안의 `_selling.discard(ticker)` 는 전부 `_sell_end_releases_selling(...)` 호출을 test 로 가진 If 안에 있다 |
| AR7 | `_sell_placed` 호출: `execute_sell` 2(각 `_order_division[...]` 대입 뒤 · `_persist_sell_pending_after_send` 앞 · 사이 `Await` 0) · `_cancel_and_reorder` 1(`place_order` 뒤) · `routes/trading.py::manual_sell` 1(`insert_trade` await 앞) |
| AR8 | `manual_sell` 에서 `_manual_sell_orders[result.order_no] = _added` 가 `place_order` await 뒤 · `insert_trade` await 앞, 사이 `Await` 0 |
| AR9 | `_reorder_requery` 가 `_manual_sell_orders` 를 읽고, 본문에 상수 `"momentum"`·이름 `strategy_id` 가 없다 |
| AR10 | `_sell_placed`·`_sell_end_releases_selling`·`_sell_fills_by_order`·`_odno_key` 는 동기 def · `Await` 0 · `_sell_placed` 는 최상위 `Try(except Exception)` |
| AR11 | `reset_daily_state` 가 `_sell_notice_seen`·`_sell_reflected_credit`·`_sell_blind_credit`·`_sell_orders_done`·`_manual_sell_orders`·`_selling_locked_wait` 를 `clear()` |
| AR12 | `order_engine.py` 에 문자열 「매도: 체결 수량만큼 손익 계산, 포지션 제거」 0 (a) |
| AR13 | `src/db/positions.py` `save_position` SQL 에 `NULLIF(EXCLUDED.ticker_name, '')` (d) · `get_daily_orders` 에 keyword-only `pdno` 기본 `""` |

A1(주문 축 If 문자 그대로·최상위·1개)·A9·A10(보유 차감 출처 게이트 없음)·G147-AST-1·g273_ast1~4·G-295-C4·test_g328_1/3b 는 **그대로 초록**이어야 한다.

---

### R-9. 돌연변이 계획 (32개 — 각각 최소 1개가 붉어야 한다)
| # | 돌연변이 | 죽이는 것 |
|---|---|---|
| MR1 | 흡수 제거(`hold_dec = quantity`) | TR1 · TR2 |
| MR2 | 재대조에서 주문별 크레딧 미기록 | TR1 |
| MR3 | 크레딧 = `tot_ccld_qty`(원장 무시) | TR3 |
| MR4 | 주문별 크레딧을 종목 단위로 소진(어느 주문 통보든 먹는다) | TR4 |
| MR5 | `get_daily_orders` 를 `get_balance` 앞으로 | TR5 · AR1 |
| MR6 | 동일성 재검증 삭제 | TR6 |
| MR7 | 조회 실패 → 크레딧 없이 재대조(지금 B7) | TR7 |
| MR8 | 조회 실패 → 재대조 생략(추적 유지) | TR7(발사 `[10,7]` 아님) |
| MR9 | 불량 행을 0 으로 읽기 | TR8 |
| MR10 | SOR 여러 행 마지막 값만 | TR9 |
| MR11 | 클라이언트 종목·매도 필터 제거 | TR10 |
| MR12 | 닫힐 때 종목 크레딧 pop 제거 | TR11 |
| MR13 | `reset_daily_state` 신규 clear 누락(하나씩) | TR12 · AR11 |
| MR14 | 손익을 `hold_dec` 로 | AR3 · TR1(손익 10주분) |
| MR15 | F-3 제거(부분 잠김은 현행 동결) | TR13 |
| MR16 | `fire = sellable`(초과분 무시) | TR14 · TR15 |
| MR17 | `fire ≤ 0` 에서도 `min(sellable, 추적)` 발사 | TR15 |
| MR18 | F-3 가 `pos.quantity = fire` 로 하향 | TR13 · AR4 |
| MR19 | 루프 상단 상한 적용 삭제 | TR13 |
| MR20 | 상한을 `send_qty = sell_cap`(min 제거) | AR5 |
| MR21 | 동결 두 곳에서 `_selling_locked_wait.add` 삭제 | TR17 |
| MR22 | 주문 축 종료 해제를 무조건 discard 로 복귀(LOW #3) | TR18 |
| MR23 | 매핑 없는 종료는 절대 해제 안 함 | TR17 |
| MR24 | `_sell_placed` 호출 삭제(주 경로) / (폴백) / (라우트) | TR19 · T27 |
| MR25 | 손님 manual 종료도 해제 | TR20 |
| MR26 | `execute_sell` 진입 시 동결 표식 청소 삭제 | TR21 |
| MR27 | `_reorder_requery` 의 manual 분기 삭제 | TR22 |
| MR28 | 라우트가 manual 표식 미등록 | TR23 · AR8 |
| MR29 | 재주문의 manual 표식 상속 삭제 | TR24 |
| MR30 | manual 판정을 `strategy_id == "momentum"` 으로 | TR25 · AR9 |
| MR31 | M22b(바깥 except `return 0`) | TR26 |
| MR32 | `NULLIF` 제거(빈 이름으로 덮기) | TR27 · AR13 |

(a) docstring 되돌리기는 AR12 가 죽인다. 앞선 M1~M30(§l-6)은 그대로 다시 돌린다 — 특히 M8·M9(`_selling` 위치)·M20~M25(J-2)가 새 해제 규칙 뒤에도 죽는지 확인한다.

---

### R-10. 기존 테스트 기대값 변경 (사유 동반 — 조용히 지우지 않는다)
| 테스트 | 지금 단언 | 바뀐 뒤 | 사유 |
|---|---|---|---|
| `tests/unit/engine/test_cycle236_sell_qty_exceeded.py::test_partial_lock_with_accurate_position_not_downgraded` | 발사 1 · `[sell_qty_partial_locked]` · `_selling` 유지 | **둘로 나눈다**: ① 원 입력(held 3·sellable 1·추적 3) → TR13 기대(발사 `[3,1]`, 추적 3, save 0, `_selling` 유지) ② 신규 입력(held 5·sellable 1·추적 3 → `fire = −1`) → 원 계약(발사 1 · `[sell_qty_partial_locked]` · `_selling` 유지 · 추적 3) | 부록 R-2 — 사용자 전제(잔여 매도 가능). 원 계약 「하향 보정 금지」는 둘 다 유지 |
| 같은 파일 `mock_env` fixture | — | `src.api.balance.get_daily_orders` 를 `AsyncMock(return_value=[])` 로 패치 추가 | 재대조 분기의 새 외부 호출(R-1-3). 기대값 불변(`[3,2]`) |
| 같은 파일 `test_locked_all_quantity_preserves_position` | 현행 | + `_selling_locked_wait` 에 종목(추가 단언만) | R-3 |
| `tests/unit/ast/test_cycle385_ast_b7.py::test_a3b_send_qty_is_taken_from_loop_top_requery` | 루프 안 `send_qty` 대입 1개 | AR5 형태(2개) | R-2 상한 |
| 전체 스위트에서 「매핑 없는 종료가 동결 아닌 `_selling` 을 푼다」를 단언하는 테스트가 나오면 | — | 사유 한 줄 + 기대값 변경, 명세 R-3 인용 | LOW #3 봉합 |

---

### R-11. 핀 · 문서 · 인덱스
- `order_engine.py` whole-file sha **10곳** 값만 재핀(§l-8 목록 그대로, 사유 「cycle385 부록 R — F-1·F-2·F-3·c·a」). 착수 전 현재 값으로 `grep -rl` 로 다시 센다.
- `test_cycle287_ast_scope.py::_BASE_SHA["src/api/balance.py"]` 값만 재핀(사유 「cycle385 R `get_daily_orders` keyword-only `pdno=""`, 기본 호출 byte 동일」, 직전 값 주석 보존 — cycle379 선례).
- `test_cycle287_ast_scope.py::_SRC_TREE_DIGEST` 값만 재핀(`api/balance.py` · `db/positions.py` · `routes/trading.py`). `src/` 파일 수 불변(신규 모듈 0) → `_SRC_TREE_FILES`·`_PINNED_DIR_FILE_COUNTS` 불변.
- **붉어지면 범위 밖을 건드린 것**(재핀 금지, 되돌린다): `test_cycle295_ast_market_rest.py::_BYTE_IDENTICAL_PINS`(`_cancel_after_wait`·`cancel_remaining`) · `test_cycle287_ast_scope.py::_FROZEN_SEGMENTS`(`execute_sell_pre_nxt_preconvert` 등) · `scheduler.py` 라인 수(3,786) · `src/realtime/**`.
- `_workspace/test_index.yaml` 재생성.
- 문서 갱신 후보(`/sync-docs` → report-writer): `src/engine/CLAUDE.md`(#1.5 크레딧 · 부분 잠김 F-3 · `_selling` 주인 규칙 · 마커 9종) · `src/routes/CLAUDE.md`(manual 표식) · `src/db/CLAUDE.md`(`save_position` 빈 이름 무시) · `src/api/CLAUDE.md`(`get_daily_orders(pdno=)`).

---

### R-12. 하드 불변식 대조
| 불변식 | 이 부록 뒤 |
|---|---|
| `fields[9]` 체결수량 | 무접촉(`handler.py` diff 0) |
| 주문수량 3단 출처 | 무접촉 |
| 전량 판정에 출처 게이트 없음 | 주문 축 판정·보유 닫기 무변경. 크레딧 흡수는 모든 출처에 똑같이 적용. `_selling` 해제의 주인 확인은 판정이 아니다(R-3-4) — A10 초록 |
| 재주문 타이머 `qty_src=="map"` 한정 · `(ticker, side)` 키 | 무접촉 |
| `_persist_sell_pending_after_send` 넓은 `except` | 무접촉(인자 무변경, 앞에 동기 호출 1개) |
| `_selling` 좀비 없음 | R-3-4 표 — 모든 유지 상태에 해제 주체. 잃는 것 = 우리 주문 무통보 소멸의 「우연한 조기 해제」뿐(원래 `selling_reconcile` 몫) |
| `on_position_closed` 는 보유 0 에서만 · site 정확히 2함수 | 신규 site 0 |
| A-ATOMIC | `execute_buy` 무접촉 |
| 8영역 sha 값만 재핀 + 사유 | R-11 |
| `scheduler.py` 무접촉 | 무접촉(3,786L) |
| `src/realtime/**` 무접촉 | 무접촉 |
| 검사 ~ 행동 사이 await 추가 금지 | 신규 await 는 R-1-3 의 `get_daily_orders` 1개 — 뒤에 동일성 재검증을 두고, 대입이 수량 술어에 기대지 않는 절대 진술임을 증명(R-1-6). F-3·해제 규칙·manual 표식은 전부 동기 |

---

### R-13. 반례 / 한계
1. **운영자 초과분 + 걸린 매도가 추적 이상을 덮는다**(`fire ≤ 0`) → 손절은 그 주문이 끝날 때까지 기다린다. 걸린 주문을 「운영자가 전략 몫부터 판다」로 읽는 보수 해석의 대가이고, 운영자 몫을 우리가 파는 쪽보다 낫다.
2. F-3 이 3회차(마지막) 시도에서 걸리면 `continue` 로 루프가 끝나 「매도 주문 최종 실패」 CRITICAL + `_selling` 해제 → 다음 틱에 다시 들어와 판다(재대조 분기의 기존 성질과 같다).
3. **과대 추적 창** — 재대조 조회 사이(수백 ms) 체결만큼. 다음 매도 APBK0400 1건으로 회수.
4. 종목 크레딧(조회 실패)은 오염(유실 통보)까지 들고 있어 뒤 통보를 흡수 → 일시 유령 → 다음 매도 APBK0400 → #1.5(보유 0 이면 insufficient 경로 삭제).
5. 우리 주문이 통보 없이 사라지면(MTS 로 우리 주문 취소 등) `_selling` 은 `selling_reconcile` 이 풀 때까지 남는다(09:30 전에는 sync 가 돌지 않는다) — 현행과 같은 상한.
6. manual 손님 주문이 걸린 채 주인 주문이 먼저 끝나면 `_selling` 이 비어, 손님 주문 옆에서 1차 발사가 통과할 수 있다(운영자 초과분 ≥ 추적 잔여 + 자동 손절 중 운영자 수동 매도가 겹칠 때만).
7. `increment` 퇴화(`fields[16]` 없음)에서 우리 주문의 발사 창 첫 통보가 거짓 「종료」를 만들면 `_sell_placed` 가 `_selling` 을 푼다 — 현행 해제와 같은 결과(§m-7 계열). 빈도 = 09-28 F2.
8. 재대조 held 가 t1 전 운영자 수동 매수분을 포함하면 그만큼 채택된다(현행 #1.5 와 같음 — F-385-2).

후속(범위 밖, 한 줄): **F-385-5** 무통보 소멸한 우리 주문을 즉시 알아채는 「걸린 우리 매도 등록부」(+ `selling_reconcile` 정리) — R-13-5·6.

---

### R-14. 09-28 확인 추가 (§o 뒤에 붙인다)
| # | 무엇 | 어떻게 | 무엇이면 멈추나 |
|---|---|---|---|
| F-R1 | 주문번호 형식 | 같은 주문의 cycle374 `[order_notice]` `order_no` ↔ TTTC0081R `odno` ↔ REST `ODNO` 가 문자 그대로 같은가(0-패딩 포함) | 다르면 기록(`_odno_key` 가 흡수하지만 가정을 사실로 바꾼다) |
| F-R2 | F-1·F-3 경로 빈도 | `system_logs` 30일 `[sell_qty_reconciled]` · `[sell_qty_partial_locked]` · `[sell_qty_locked]` 건수 | 정보용 — 행을 눈으로 보고 옮긴다(전칭 명제 금지) |
| F-R3 | SOR 주문의 TTTC0081R 행 모양 | SOR 로 나간 매도 1건의 `inquire-daily-ccld` 원문 — 같은 `odno` 여러 행인가, 부모·자식 합계 행이 섞이는가 | 합계 행이 섞이면 R-1-4 5(합산)를 멈추고 알린다 — 합산이 이중 계산이 된다 |

---

### R-15. 본문 대체 목록 (이 부록이 이기는 자리)
| 본문 | 대체 |
|---|---|
| §d 「`_selling`: … 그 MTS 주문의 종료가 해제한다」 | 동결(`_selling_locked_wait`) 상태일 때만(R-3-3) |
| §g-1 표 「주문 종료 → discard」 두 행 · 「`[sell_qty_partial_locked]`·`[sell_qty_locked]` 유지」 행 | 주인 규칙(R-3-3) · 부분 잠김은 `fire ≥ 1` 이면 판다(R-2) · 동결 시 표식 |
| §f-2 J-2 표 | 맨 위에 `manual` 행(R-4) |
| §h-3 `save_position` 인자 | 인자 무변경, SQL 이 빈 이름을 무시(R-5 d) |
| §i 「KIS 잔고 대사 불요」 | 결론 유지(상향 대사 불요 · `scheduler.py` 무접촉). #1.5 재대조에 주문 조회 1건 추가(R-1) |
| §j 마커 표 | R-6 추가분 |
| §l-6 M22 | M22b 는 TR26 이 죽인다 |
| §0 「8영역 면적」·말미 「8영역 · 파일 면적」 표 | + `src/api/balance.py`(`pdno=`) · `src/db/positions.py`(SQL 1줄) — 둘 다 비8영역. `src/db/*` 「무접촉」 줄은 R-5 d 로 대체 |

---

## 부록 R2 — 2차 검토 반영(H1~H8·테스트 공백·수용 기준)

- 작성: domain-expert · 2026-09-27(일) KST · 워크트리 `auto_stock_c385`(B7 + 부록 R 구현 위, 미커밋). 줄 번호는 **이 부록 작성 시점의 워크트리 줄**이다(`order_engine.py` sha `d94adb15…`).
- 입력: 2차 검토 NO-GO 8건(H1~H8) + 테스트 공백(XT-K·XT-D·XT-A/XT-I·XT-J·XT-E) + 재핀 사유 주석 정정 + 수용 기준(무작위 프로브의 모든 지표 ≤ B7, 적대 프로브 전부 통과, 못 맞추면 R-3 소유 규칙 제거).
- 방법: 스크래치 복사본에 두 경로를 **시제품**으로 구현해 수용 프로브를 직접 돌렸다(구현본이 아니다 — 주석·문서·죽은 코드 정리 없음). 경로 A = R-3 유지 + H1~H8 · 경로 B2 = R-3 제거 + 나머지 전부 + 동결 닫힘 해제(R2-5). 시제품 diff = scratchpad `c385r2/ref_r2_pathB_order_engine.patch`·`ref_r2_pathB_trading.patch`(B2), `ref_r2_pathA_order_engine.patch`(A). 측정 출력 = `c385r2/out/*.json`, 검증 테스트 = `c385r2v/test_r2_validate.py`, 돌연변이 러너 = `c385r2/mut_r2.py`.
- 사용자 규칙 「새 제안 금지」 — 이 부록은 지적 목록만 다룬다. 목록 밖에서 새로 확인된 것은 R2-19 끝에 한 줄로만 둔다. 예외 1건(R2-5 동결 닫힘 해제)은 **수용 지표를 맞추려면 필요한 최소 규칙**이라 넣었고, 이유와 측정값을 같이 적는다.

### R2-0. 결론 (한눈에)

| 지적 | 판정 | 처방 한 줄 | 자리 |
|---|---|---|---|
| **경로** | 경로 A(R-3 유지)는 수용 기준 **불충족**(정산점 좀비 5·7 > B7 4, 무해 좀비 12/7/15 > 0/1/4) | **R-3 소유 규칙을 제거한다**(B7 해제 의미로 복귀). LOW #3 은 알려진 한계로 되돌린다(R2-1) | `order_engine.py` · `routes/trading.py` |
| H1 | 경로 B2 에서 결함 자체가 사라진다 | 주문 축 종료의 `_selling` 해제는 **조건 없이** 한다 — 판정할 값이 없으니 낡은 값을 읽을 수도 없다. AST 가드로 되살아남 차단(AR2-1) | `:3112-3126` |
| H2 | 재현(A3·p5: 추적 2 < 계좌 5) | 종목 크레딧은 **누적**한다(덮어쓰지 않는다) | `:2103` |
| H3 | 재현(A1: 발사 `[10,6]`, 전략 몫 3) | F-3 도 주문 조회를 쓰고, **아직 안 온 외부 체결 통보를 먼저 뺀 추적(eff)**으로 초과분을 잰다. 분기 술어도 `held ≥ eff` 로. 조회 실패 = F-3 발사 없음(현행 동결) | `:2035-2140` |
| H4 | 경로 B2 에서 구조적으로 성립 | 어느 주문의 종료든 `_selling` 을 푼다 → 매핑된 manual 주문의 종료도 동결을 푼다 | 무변경(해제 무조건) |
| H5 | 재현(seed 1068) | `_cancel_and_reorder` 가 원주문 취소에 성공했는데 재주문이 **확정적으로 안 걸렸으면**(발사 전 종료·KIS 거부) 그 주문이 `_selling` 의 주인일 때 푼다. 발사 결과를 모르면(전송 중 예외·취소) 유지 | `:3438-3586` |
| H6 | 수용 | `get_daily_orders` 를 `asyncio.wait_for(…, 2.0초)` 로 묶고 초과 = `reason=timeout` 실패 경로 | 신규 헬퍼 |
| H7 | 수용 | 쪽 가득 판정을 환경별 쪽 크기(실전 100·모의 15)로 | `:314-317` |
| H8 | 건전한 영속 원천 **없음**(R2-11) | 과대 추적은 그대로 둔다. F-3 은 공식 자체가 재시작 뒤에도 보수적이라(미확인 체결 전부를 pending 으로 센다) 별도 「미시드」 게이트를 두지 않는다 — 벽시계 게이트는 CI 를 깨고 더하는 것이 없다. 남는 한계 문서화 | 무변경 + 테스트 |
| 테스트 공백 | 5건 전부 | 결정적 테스트로 막는다(R2-12) · 돌연변이 23종 시제품에서 전부 죽음(R2-14) | 새 파일 1 + 기존 5 |
| 재핀 주석 | 틀린 서술 3건 | `balance.py` 는 8영역 아님 · F-2 뜻 · 트리 다이제스트에 `db/positions.py` 포함 — 문구 교체(R2-16) | AST 핀 파일 |

### R2-1. 경로 선택 — 측정값과 이유

**측정**(시제품, 400 시드 × payload 1.0/0.0/0.6, 값은 `1.0/0.0/0.6` 순). M0 = 기본(재대조 켬), M2 = 주문 조회 실패(`PROBE_ORDERS=fail`), M4 = 운영자 초과분(`PROBE_SURPLUS=1`), M5 = M2+M4(참고). B7 은 주문 조회가 없어 M2 의 기준은 B7 M0, M5 의 기준은 B7 M4 다.

| 지표 (프로브 키) | B7 M0 | A M0 | **B2 M0** | A M2 | **B2 M2** | B7 M4 | A M4 | **B2 M4** | B2 M5(참고) |
|---|---|---|---|---|---|---|---|---|---|
| 정산점 좀비·추적>0 `transient_zombie_tracked_runs` | 4/4/8 | 4/**5**/2 | 3/2/2 | 4/**7**/4 | 4/2/2 | 6/3/5 | 3/2/3 | 1/1/2 | 1/1/2 |
| 최종 좀비·추적>0 `H3` | 0/0/0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| 최종 과소 추적 `GT_under` | 0/2/0 | 0 | 0 | 0 | 0 | 1/0/0 | 0 | 0 | 0 |
| 포지션 유실 `H2` | 0/2/0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| 정산점 과소 추적 `transient_under_runs` | 32/46/29 | 0 | 0 | 0 | 0 | 315/300/314 | 309/297/310 | 311/297/309 | 308/289/304 |
| 잔여 손절 오작동 `H6` | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| 운영자 몫 매도 `GT_INV2` | 0 | 0 | 0 | 0 | 0 | 35/34/30 | 22/19/15 | 29/27/18 | **36/42**/30 |
| 운영자 몫 매도(외부 걸림 포함) `GT_INV2c` | 0 | 0 | 0 | 0 | 0 | 52/46/48 | 45/32/29 | 50/42/33 | **55/53**/45 |
| 무해 좀비·추적 0 `H3_benign_persist` | 0/1/4 | **12/7/15** | 0/0/0 | **10/7/13** | 0/0/0 | 0/0/1 | **13/11/8** | 0/0/1 | 0/0/1 |
| 최종 불일치·과대 `H1`·`GT_over` | 0/2/0 · 0 | 0 · 0 | 0 · 0 | 0 · 0 | 0 · 0 | 0 · 0 | 0 · 0 | 0 · 0 | 0 · 0 |
| 통보 예외·음수 `H4`·`H5` | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |

- M4 의 `transient_under_runs` 는 정의상 계좌(초과분 포함) 대비라 뜻이 없다(B7 도 300대).
- 1,600 시드 재측정(노이즈 확인): B2 M0 정산점 좀비 9/6/4 vs B7 21/19/20 · 무해 좀비 0/0/0 vs 0/2/22 · B2 M4 `GT_INV2` 110/131/101 vs B7 143/167/146 · B2 M5 142/180/149 vs B7 M4 143/167/146.

**경로 A 가 못 맞추는 이유(뿌리 1개)** — `_schedule_cancel_and_reorder`(`:3348-3360`)는 같은 `(ticker, sell)` 키의 **다음 부분 체결 통보**가 오면 걸려 있던 `_cancel_and_reorder` 태스크를 **무조건 취소**한다(`:3353-3354`). 원주문 취소가 이미 성공했고 태스크가 `await place_order`(`:3561`) 중이면, 재주문이 거래소에 나갔는지 알 길이 없다(시드 1031·1071 = 안 나감, 3101·1024 = 나갔고 매핑이 끝내 안 선다). R-3 아래에서는 그 `_selling` 을 풀 주인이 없어 `selling_reconcile`(보유>0·열린 주문 0·180초) 만 푼다 → 정산점 좀비. 보유가 0 이면 `selling_reconcile` 도 손대지 않아(`held_zero`) 무해 좀비로 하루 끝까지 남는다. 이것을 고치려면 **타이머 교체 의미**를 바꿔야 하는데 H1~H8 밖이다 → 사용자 규칙 → 지시된 대체 경로(R-3 제거).

**B2 가 B7 를 넘는 칸(정직하게)** — 목록 지표(좀비·과소 추적·유실·잔여 손절·운영자 몫)는 M0·M2·M4 전부 ≤ B7. 넘는 것은 두 부류뿐이다.
1. **거부된 발사 횟수 `oversell_*`**(APBK0400 를 받은 주문 시도. 돈·보유 변화 0): `oversell_manual`(프로브가 운영자 버튼 수량을 `1..추적` 에서 뽑는다 — 추적이 B7 처럼 줄지 않으니 더 큰 수를 뽑는다, 엔진 무관) · `oversell_reorder_manual`(부록 R F-2 설계 — 운영자 잔여는 보유 상한 없이 쏜다) · `oversell_reorder_stop` M0 1,600 시드 33/28/32 vs 19/13/16(J-2 상한이 정확한 추적이라 통보가 늦은 외부 체결만큼 크다) · `oversell_stop` M2 291/360/316 vs 280/349/282(조회 실패 = 종목 크레딧 = 과소 추적 대신 과대 추적). 전부 **R-INV-1(과소 추적 금지)의 직접 대가**다 — B7 은 이중 차감으로 추적을 줄여서 덜 거부됐다.
1b. **`INV2` 의 하위 계수 `INV2_stop_stacked`**(M4 payload 0.0: 5 vs 3) — 런 단위 `INV2` 는 9/12/5 vs 13/13/8 로 낮다. 1,600 시드에서 10 vs 9 · 9 vs 9 · 3 vs 4 로 같은 수준 = LOW #3 의 쌓기(B7 과 같은 기제)가 궤적에 따라 흔들린 것.
2. **M5(초과분 + 조회 실패) 운영자 몫** 36/42/30 vs 35/34/30 — 조회가 안 되면 「걸린 체결 통보」와 「초과분」을 가를 수 없어 재대조가 초과분을 받아들인다(R-13-8 과 같은 성질). B7 은 이중 차감이 우연히 그만큼을 깎았다. 1,600 시드로는 1.0·0.6 이 동률이고 0.0(통보에 주문수량 없음)만 +13. M5 는 지시된 모드 목록 밖이다.
- 판단은 메인 세션 몫이다. 도메인 의견 = 1 은 손해 지표가 아니라 활동 계수이고, 2 는 R-INV-1 을 지키는 한 없앨 수 없다.

**R-3 제거로 되돌아오는 한계(LOW #3, 알려진 한계로 문서화)** — 우리 손절 주문이 걸려 있는 동안 **무관한 주문**(MTS·손님 manual)이 끝나면 `_selling` 이 풀리고, 다음 틱 손절이 추적 잔여를 또 낸다. 계좌에 운영자 초과분 ≥ 추적 잔여가 있으면 1차 발사가 통과해 운영자 몫을 판다(부록 R-3-2 수치 그대로). **B7 과 같은 성질**이고(적대 프로브 p3·p3b 는 B7 에서도 실패) 무작위 프로브의 운영자 몫 지표는 B7 보다 낮다(29/27/18 vs 35/34/30). 막는 수단은 「걸린 우리 매도 등록부」(§n F-385-5) — 이번 사이클 밖.

### R2-2. 제거하는 것 — 부록 R-3 되돌림 (정확한 목록)

| 자리 | 지금 | 바꾼 뒤 |
|---|---|---|
| `_handle_sell_fill` 주문 축 If 첫머리 `:3113-3126` | `_sell_orders_done.add` · `if ticker in self._selling: if self._sell_end_releases_selling(...)` · `[selling_kept]` | `self._selling.discard(ticker)` · `self._selling_locked_wait.discard(ticker)` **두 문장만**, If 본문의 첫 두 문장(첫 `await update_trade_status` 앞). 주석 = 「주문이 끝났다 = 진행 중 표식은 거짓. 어느 주문의 종료든 푼다(B7 해제 의미 — 부록 R2-1, LOW #3 은 알려진 한계)」 |
| `_sell_end_releases_selling` 정의 `:3239-3243` · `_sell_placed` 정의 `:3245-3257` | 있음 | **삭제** |
| `_sell_placed` 호출 4곳 — `execute_sell` `:1884` · 폴백 `:2274` · `_cancel_and_reorder` `:3572-3575` · `routes/trading.py:200` | 있음 | **삭제**(앞뒤 문장 무변경 — `test_g328_1` 매핑 등록~PENDING 헬퍼 사이 await 0 은 그대로) |
| `_sell_orders_done` — 선언 `:431` · add `:3116` · clear `:3613` | 있음 | **삭제** |
| 마커 `[selling_kept]` · `[selling_released_after_window]` | 있음 | 삭제 |
| `_manual_sell_orders` | F-2 표식 + 주인 여부 | **유지**(F-2 J-2 `verdict=manual` + H5 주인 판정에 쓴다). 라우트 값 `= _added` 무변경 |
| `_selling_locked_wait` | 동결 표식(해제 판정용) | **유지, 뜻을 좁힌다**(R2-5) |
| `routes/trading.py` `manual_sell` docstring(`:144-149`) | `_sell_placed` 언급 없음 | 무변경(「발사 전 실패는 되돌리고, 발사 뒤는 그 주문의 종료 통보가 해제한다」 그대로 사실) |

- 부록 R 의 R-3-3 규칙표·R-3-4 표·R-3-5, R-6 의 두 마커 행, R-7 TR18~TR21 의 기대값, R-8 AR6·AR7·AR10b, R-9 MR22~MR26 은 이 부록이 대체한다(R2-20).

### R2-3. H1 — 해제 판정이 await 전에 잡은 값을 읽지 않는다

- 경로 B2 의 주문 축 해제는 **조건이 없다** — 판정할 값이 없으니 `qty_src`(통보 시작 시점 값)든 `holders`·`owner`·`pos`(첫 await 전 값)든 읽을 수 없다. 1차 검토의 재현 넷(p4a·p4b·p4c·money A2)은 B2 시제품에서 전부 통과한다(발사 창에서 시작해 DB await 에서 멈춘 통보가 REST 응답 뒤 재개돼도, 종료 시점에 무조건 푼다).
- 🔴 되살아남 방지 AST 가드 AR2-1(R2-13) — `_handle_sell_fill` 에서: (가) 주문 축 If(`total_filled >= ordered_qty`, 최상위 1개 — A1)의 본문 **직계 문장**으로 `self._selling.discard(ticker)` 가 있고 그 If 의 첫 `Await` 앞이다 (나) 주문 축 If 안에서 `_selling.discard` 를 감싸는 **다른 If 가 없다** (다) `qty_src` 를 테스트로 읽는 If 가 `_selling.discard` 를 감싸지 않고, `qty_src` 를 인자로 받는 호출의 결과가 해제를 가르지 않는다 (라) 닫기 묶음의 해제(R2-5)를 감싸는 If 테스트는 `ticker`·`self._selling_locked_wait` 만 읽는다 (마) `ticker`·`order_no` 에 대입 0. 범위 밖 = 전략 미등록 오류 경로(`:2994-2997` `if not strategy:` — `strategy` 는 바로 앞 줄에서 await 없이 잡는다, 본문·부록 R 이 손대지 않기로 한 자리). 주문 축 If 의 테스트 `total_filled`·`ordered_qty` 는 **이 통보의** 주문 축 사실(인자, 불변)이지 공유 상태의 스냅샷이 아니다.
- `_cancel_and_reorder`(H5)의 `_cancel_ok`·`_place_state` 는 **그 태스크 자신이 한 일의 기록**(단조 증가, 그 태스크만 쓴다)이지 공유 상태의 스냅샷이 아니다 — H1 가드의 대상이 아니다. 주인 여부는 해제 시점에 `self._manual_sell_orders` 를 **그때** 읽는다.

### R2-4. H4 — 동결은 어느 주문의 종료로든 풀린다

- 경로 B2 에서는 주문 축 종료가 조건 없이 `_selling` 을 푼다 → 매핑된 manual 손님 주문의 종료도, MTS 주문의 종료도 동결(`[sell_qty_locked]`·F-3 `fire ≤ 0`)을 푼다. 부록 R-3-3/R-3-4 의 의도(「동결은 어느 주문의 종료든」)가 구조적으로 성립한다.
- 테스트 TQ18(R2-12): 동결 + 매핑된 손님 manual(`_manual_sell_orders[no]=False`) map 전량 종료 → `_selling`·`_selling_locked_wait` 비어 있음.

### R2-5. 동결 표식의 새 뜻 + 「지키던 보유가 닫히면 동결을 푼다」

**뜻** — `_selling_locked_wait` = 「지금 `_selling` 은 우리 `execute_sell` 이 **주문 없이** 멈춰(`[sell_qty_locked]`·F-3 `fire ≤ 0`) 세워 둔 것이다」. 그 멈춘 `execute_sell` 은 아무것도 걸지 않았다.

| 사건 | 표식 |
|---|---|
| `[sell_qty_locked]` return 직전(`:2156`) · F-3 `fire ≤ 0` return 직전(`:2058` → 새 분기 안) | add(무변경) |
| `execute_sell` 진입 `_selling.add` 직후(`:1674`) · 라우트 `_added` add 직후(`routes/trading.py:179`) | discard(무변경 — 새 주인이 섰다) |
| 주문 축 종료(R2-2) · J-2 `gone`(`:3508`) · H5 해제(R2-6) · `reset_daily_state`(`:3615`) | discard |
| **(신규) 닫기 묶음**(`if close_position:` `:3075`) | 아래 규칙 |

**규칙(닫기 묶음, 동기, 첫 await 앞)** — `:3079`(`self._sell_blind_credit.pop(ticker, None)`) 바로 뒤, `on_position_closed` 앞:
```python
if ticker in self._selling_locked_wait:
    # 동결이 지키던 보유가 사라졌다 — 멈춘 execute_sell 은 주문을 걸지 않았으므로
    # 이 표식은 더 지킬 것이 없다(부록 R2-5).
    self._selling.discard(ticker)
    self._selling_since.pop(ticker, None)
    self._selling_locked_wait.discard(ticker)
    logger.info("[selling_freeze_released] ticker=%s order_no=%s reason=position_closed",
                ticker, order_no)
```
- **왜 넣나** — 동결이 기다리던 외부 주문이 **부분 체결로** 추적을 0 으로 만들고 끝내 「종료」가 오지 않으면(운영자가 나머지를 취소 등) `_selling` 이 보유 0 으로 하루 끝까지 남는다(`selling_reconcile` 은 `held_zero` 를 건드리지 않는다). B7 에도 같은 기제가 있고(0/1/4), 이 규칙이 없으면 B2 가 400 시드에서 5 vs 4 · 2 vs 1 로 B7 을 넘는다(같은 기제, 다른 궤적). 있으면 0/0/0.
- **안전** — 조건이 표식이라 「우리 주문이 걸린 채 외부 체결이 추적을 0 으로 만든」 경우(§c `주문 부분 · 보유 0`)는 **유지**한다(T6 가 지킨다). 표식이 선 뒤 새 주인이 서면 진입에서 표식을 지우므로(위 표) 새 주인의 `_selling` 을 잘못 풀지 않는다(TQ25).
- 부록 R 의 H4 문구(「동결 먼저 확인」)는 B2 에서 판정 함수가 없으므로 이 절로 대체된다.

### R2-6. H5 — 원주문을 취소했는데 우리 것이 아무것도 안 걸렸으면 `_selling` 을 푼다

**결함(seed 1068)** — `_cancel_and_reorder` 가 `cancel_order` 에 성공한 뒤 재주문이 APBK0400 으로 거부되면 `except Exception`(`:3579`)이 로그만 남기고 끝난다 → 우리 것이 하나도 안 걸렸는데 `_selling` 이 남는다 → 잔여 손절 정지(`selling_reconcile` 180초+15분 주기까지). 부록 R 의 F-385-4 가 미뤘던 것이다.

**규칙** — 태스크 자신의 두 사실을 `try` **앞**에서 초기화하고, `finally` 에서 한 번 판정한다.
```python
async def _cancel_and_reorder(self, ticker, order_no, remaining, *, is_stop_loss):
    _cancel_ok = False        # 이 태스크가 원주문 취소에 성공했나
    _place_state = "none"     # none | sending | accepted | rejected
    try:
        await asyncio.sleep(PARTIAL_FILL_WAIT)
        ...                                   # 쌍 게이트·거래소 해석 무변경
        _cancel_err = ""                      # `:3473` 의 `_cancel_ok = False` 는 위로 올린다
        try:
            await cancel_order(order_no, 0, cancel_all=True, exchange=ex)
            _cancel_ok = True
        ...                                   # `[after_cancel_result]` finally 무변경
        ...                                   # CANCELLED 장부 · J-2 재조회 · gone 해제 무변경
        _place_state = "sending"              # 🔴 `_reorder_requery` ~ place_order 사이 await 0 유지(A4)
        try:
            result = await place_order(**place_kwargs)     # G-295-C4: 여전히 1개, 값으로 받는다
        except KisApiError:
            _place_state = "rejected"          # KIS 가 응답으로 거부 = 확정적으로 안 걸렸다
            raise                              # 바깥 `except Exception` 의 기존 로그 그대로
        _place_state = "accepted"
        ...                                   # 매핑·manual 표식 상속 무변경(`_sell_placed` 호출만 삭제)
    except asyncio.CancelledError:
        pass
    except Exception:
        logger.exception("매도 잔여 취소/재주문 실패: %s", ticker)
    finally:
        if (
            _cancel_ok and _place_state in ("none", "rejected")
            and ticker in self._selling
            and self._manual_sell_orders.get(order_no, True)   # 🔴 해제 시점에 읽는다
        ):
            self._selling.discard(ticker)
            self._selling_since.pop(ticker, None)
            self._selling_locked_wait.discard(ticker)
            logger.warning("[reorder_selling_released] ticker=%s order_no=%s place=%s",
                           ticker, order_no, _place_state)
        ...                                   # 타이머 키 pop 무변경
```

| 출구 | `_cancel_ok` | `_place_state` | `_selling` | 근거 |
|---|---|---|---|---|
| 쌍 게이트 컷(취소 안 함) · 취소 실패(APBK0927 등) | False | none | 유지 | 원주문이 아직 걸려 있거나 이미 끝났다(끝났으면 그 통보가 푼다) |
| 취소 성공 → CANCELLED 장부·재조회 중 예외 · 이 태스크 취소(교체) | True | none | **해제**(주인일 때) | 우리 것이 아무것도 안 걸렸다 |
| 취소 성공 → J-2 `gone` | True | none | 해제(기존 `:3506-3508`, finally 는 `ticker in _selling` 거짓이라 중복 로그 없음) | 무변경 |
| 취소 성공 → 재주문 KIS 거부(`KisApiError`) | True | rejected | **해제**(주인일 때) | seed 1068 |
| 취소 성공 → 재주문 전송 중 예외(타임아웃 등) · 전송 중 태스크 취소 | True | sending | **유지** | 🔴 거래소에 나갔을 수 있다 — 풀면 다음 틱이 한 번 더 낸다(루트 금기 「주문이 나간 뒤의 실패」 원리). `selling_reconcile` 이 푼다 |
| 취소 성공 → 재주문 접수 | True | accepted | 유지 | 새 주문의 종료가 푼다(B7 해제) |

- **주인 판정** — `self._manual_sell_orders.get(order_no, True)`: 자동 주문(표식 없음)은 참, manual `_added` 참은 참, **손님 manual**(`_added` 거짓, 자동 매도가 `_selling` 주인)은 거짓 → 풀지 않는다(XT-A). 재주문의 표식 상속(`:3570-3571`)이 값을 그대로 넘기므로 2세대 재주문도 손님이면 거짓이다(XT-I).
- 「운영자 초과분」 걱정은 재주문이 **걸렸을 때만** 해당한다 — 그때는 유지한다. 안 걸렸으면 우리 것이 하나도 없으니 다음 틱 `execute_sell` 이 추적에서 다시 시작하고 KIS 매도가능수량이 상한이다.
- `[reorder_selling_released]` WARNING(cap 없음, 드묾) — `place=rejected` 가 떴다 = 재주문 거부 뒤 손절 재평가가 즉시 재개됐다. `place=none` = 교체·예외로 재주문을 못 냈다.
- 본문 §n **F-385-4 는 이것으로 해소**된다(목록에서 지운다).

### R2-7. H2 — 종목 크레딧은 누적한다

`:2103` `self._sell_blind_credit[ticker] = _blind` → `self._sell_blind_credit[ticker] = self._sell_blind_credit.get(ticker, 0) + _blind`.
- 이유 — 두 번째 재대조의 `_blind = pos − held₂` 는 **첫 재대조 이후** 새로 반영된 몫만 센다(첫 재대조가 `pos` 를 `held₁` 로 이미 내렸다). 첫 몫이 아직 소진 전이면 둘을 더해야 「걸린 통보 전부」다(누적 = 첫 재대조 하나로 `pos₀ → held₂` 를 한 것과 같다). 덮어쓰면 첫 몫의 통보가 다시 빠져 과소 추적(A3: 추적 2 < 계좌 5).
- 소진식(`:3044-3050`)은 무변경 — 부분 소진이면 남은 값을 둔다(XT-D 가 이걸 지운다).
- 주문 조회가 성공한 재대조는 종목 크레딧을 **버린다**(`:2099`, 무변경 — 주문별 크레딧이 그 몫을 정확히 대신한다).

### R2-8. H3 — F-3 은 아직 안 온 외부 체결 통보를 먼저 뺀다

**결함(money A1)** — 추적 10 · 계좌 15(운영자 5) · MTS-A 3 체결(통보 대기) · MTS-B 4 걸림. `held 12 · sellable 8`. 지금 F-3 은 `surplus = 12 − 10 = 2`(참값 5) → `fire = 6` → 운영자 3주를 판다. B7 은 동결했다.

**구조** — `:2035-2140` 의 두 분기(`elif 0 < sellable < pos.quantity and held_qty >= pos.quantity:` / `elif 0 < sellable < pos.quantity:`)를 **하나의 `elif 0 < sellable < pos.quantity:`** 로 합치고 안에서 가른다. 주문 조회는 두 갈래가 같이 쓰므로 **한 번** 부른다.
```python
elif 0 < sellable < pos.quantity:
    fills, _reason = await self._sell_orders_snapshot(ticker)        # t2 — 반드시 get_balance(t1) 뒤
    if strategy.state.positions.get(ticker) is not pos:              # 동일성 재검증(부록 R-1-3 ⑤ 그대로)
        logger.info("[sell_qty_reconcile_skipped] ticker=%s reason=position_replaced", ticker)
        continue
    # ── 여기부터 대입(pos.quantity = target / sell_cap = fire)까지 await 0 ──
    pending = self._sell_pending_dec(fills) if fills is not None else None
    eff = pos.quantity - pending if pending is not None else pos.quantity
    if held_qty >= eff:                                              # 초과분 쪽(F-3)
        surplus = held_qty - eff
        fire = sellable - surplus if fills is not None else 0       # 🔴 조회 실패 = 발사 없음
        if fire >= 1:
            sell_cap = fire
            logger.warning("[sell_qty_partial_sellable] ... surplus=%d fire=%d pending=%d", ...)
            continue
        logger.warning("[sell_qty_partial_locked] ... (기존 문구) surplus=%d fire=%d "
                       "pending=%s orders=%s", ..., pending if pending is not None else "?", _reason)
        self._selling_locked_wait.add(ticker)
        return
    # 재대조 쪽(held < eff — 오늘 주문으로 설명되지 않는 오염) — 부록 R-1-3 ⑥~⑨ 그대로
    target_qty = held_qty if 0 < held_qty < pos.quantity else sellable   # 무변경 식
    ... 주문별 크레딧 / 종목 크레딧(누적, R2-7) / [sell_qty_reconciled] / pos.quantity = target_qty
    ... sell_cap = None / await save_position / continue
```

**`_sell_pending_dec(fills) -> int`** (신규 동기 메서드, await 0, never-raise 불필요 — 순수 dict 산술):
```python
return sum(max(0, f - self._sell_notice_seen.get(o, 0) - self._sell_reflected_credit.get(o, 0))
           for o, f in fills.items())
```
- = 「거래소는 체결했는데 아직 우리 보유에서 빠지지 않았고, 앞으로 통보가 오면 **빠질** 수량」. 주문별 크레딧은 빼지 않을 몫이라 뺀다.
- 🔴 **종목 크레딧(`_sell_blind_credit`)은 빼지 않는다**(보수 쪽). 종목 크레딧에는 유실 통보(E)가 섞일 수 있어, 그것을 빼면 eff 가 E 만큼 커지고 초과분을 적게 봐 운영자 몫을 판다. 빼지 않으면 eff 가 작아져 **덜 쏜다**(TQ5: `[10,7,2]` — 나머지는 통보가 온 뒤 다음 틱이 판다).

**`_sell_orders_snapshot(ticker) -> tuple[dict | None, str]`** (신규 `async` 메서드, 유일한 await = `wait_for`, 예외를 밖으로 내지 않는다):
```python
try:
    from src.api.balance import get_daily_orders          # lazy — 테스트가 모듈 속성을 패치한다
    rows = await asyncio.wait_for(get_daily_orders(exchange="ALL", pdno=ticker),
                                  timeout=SELL_ORDERS_QUERY_TIMEOUT)          # H6
except asyncio.TimeoutError:
    return None, "timeout"
except Exception:
    return None, "error"
from src.config import settings
page = _DAILY_ORDERS_PAGE_REAL if settings.is_production else _DAILY_ORDERS_PAGE_VTS   # H7
if isinstance(rows, list) and len(rows) >= page:
    return None, "page_full"
fills = _sell_fills_by_order(rows, ticker, page)
return (None, "bad_row") if fills is None else (fills, "ok")
```
- 🔴 `exchange="ALL"`·`pdno=ticker` 는 키워드로 고정(XT-K·XT-L — KRX 만 보면 NXT/SOR 체결을 놓쳐 크레딧이 모자란다).

**왜 운영자 몫을 안 파나(요지)** — 통보 하나(수량 `q`)가 보유를 `d`, 주문별 크레딧을 `a`, 종목 크레딧을 `b` 만큼 소비하면(`q = d + a + b`) `seen += q`·주문별 크레딧 `−= a` 라 `pending` 이 `d + b` 줄고 `pos` 가 `d` 준다 → **eff 는 보유 차감·주문별 흡수에 불변**이고 종목 흡수 `b` 만큼만 오른다.
- 종목 크레딧이 없으면(주문 조회가 되는 평상시) eff 는 통보에 불변이다. 주문별 재대조 직후 eff = `held(t1) − (재대조 뒤 새 체결)` 이라 참 전략 보유보다 커질 수 있는 폭은 재대조 조회 창(t1~t2, 수백 ms)의 체결뿐이다. 재대조가 없던 경우 `pending` 은 그날의 미확인 체결 전부(유실 통보 포함)라 eff 는 참값 **이하**다.
- 종목 크레딧이 있으면(조회 실패 재대조 뒤, 다음 조회 성공 재대조가 그것을 버리기 전까지 — `:2099`) 흡수될 때까지는 pending 이 그 몫을 차감으로 세어 보수적이고, 흡수된 뒤의 eff 는 종목 크레딧의 오차(유실 통보 E)를 그대로 싣는다 — 부록 R-13-4 와 같은 크기·같은 원인이다.
- `surplus = held(t1) − eff` 에서 t1 뒤 체결은 pending 에만 들어가 surplus 를 키운다(= 덜 쏜다).

**분기 술어를 eff 로 바꾸는 이유** — `held ≥ pos` 로 가르면, 추적 10 · 초과분 5 · MTS-A 6 체결(통보 대기) · B 2 걸림(`held 9 < 10`)에서 재대조가 `pos = 9`(운영자 5 를 받아들임)로 내리고 다음 회차가 `[10, 9, 7]` 을 낸다(참 전략 몫 4 − 걸림 2 = 2). eff(= 4)로 가르면 초과분 쪽으로 가서 `[10, 2]`(TQ2). 오늘 주문으로 설명되는 차이는 재대조(절대 대입)가 아니라 「통보가 곧 뺄 것」이다.

**동작 예**
| 추적 | 계좌 | 걸림 | 미확인 체결 | held/sellable | pending → eff | 경로 | 발사 |
|---|---|---|---|---|---|---|---|
| 10 | 15 | B 4 | A 3 | 12/8 | 3 → 7 | F-3, surplus 5 | `[10, 3]` (A1) |
| 10 | 15 | B 2 | A 6 | 9/7 | 6 → 4 | F-3, surplus 5 | `[10, 2]` (TQ2) |
| 10 | 10 | B 2 | A 3 | 7/5 | 3 → 7 | F-3, surplus 0 | `[10, 5]` (부록 R TR2 → 재대조 단계 없이) |
| 12(유령 2) | 10 | B 2 | A 3 | 7/5 | 3 → 9 | 재대조 → pos 7·크레딧 A 3 → F-3 pending 0 | `[12, 7, 5]` (TQ4) |
| 10 | 10 | B 3 | — | 10/7, 조회 실패 | ? → 10 | 동결(`orders=error`) | `[10]` (TQ3) |

**검사→행동 사이 await(하드 불변식)** — 분기 판정(`0 < sellable < pos.quantity`)과 행동 사이에 `await self._sell_orders_snapshot` 이 낀다. 행동은 await **뒤에** 동일성을 재검증하고 `pos.quantity`·원장을 **그때** 다시 읽어 eff 를 만든다. 판정에 쓴 `held`·`sellable`(t1)은 절대 스냅샷이고 위 요지대로 t1 뒤 변화는 전부 덜 쏘는 쪽으로만 작용한다. 부록 R-1-3 의 논증과 같은 구조다. eff 계산 ~ `sell_cap = fire`/`pos.quantity = target_qty` 사이 await 0(AR2-5).

**부록 R 대비 바뀌는 사실** — R-1-7 「F-3: 새 호출 0」 → **F-3 도 TTTC0081R 1건**(재대조와 같은 1건을 공유, execute_sell 1회 최대 3건 무변경). 부록 R TR13 의 「F-3 새 KIS 호출 0」 단언은 「주문 조회 1건(`exchange="ALL", pdno=TICKER`)」 으로 바뀐다.

### R2-9. H6 — 주문 조회 2초 상한

- 모듈 상수 `SELL_ORDERS_QUERY_TIMEOUT = 2.0`(초, `_sell_fills_by_order` 위 `:309` 부근). `DEFAULT_PARAMS`·`system_config` 키 아님(런타임 다이얼 없음 — 본문 §k).
- 2초 = 손절 경로가 APBK0400 뒤 이미 잔고 1건을 기다린 상태에서 더할 수 있는 상한. KIS REST 정상 왕복(수백 ms)보다 넉넉하고, 넘으면 종목 크레딧(재대조) / 동결(F-3)로 넘어간다 — 둘 다 과소 추적 0 쪽이다.
- 초과 시 `[sell_qty_reconcile_orders_unavailable] reason=timeout` 또는 `[sell_qty_partial_locked] ... orders=timeout`. `wait_for` 가 취소하는 것은 읽기 조회뿐이다(주문 아님).
- 테스트는 상수를 monkeypatch(0.01)하고 가짜 조회가 0.5초 잔다(돌연변이 「wait_for 제거」가 0.5초 뒤 행을 돌려줘 `reason=ok` 로 가므로 붉다).

### R2-10. H7 — 쪽 크기는 환경별

- `_DAILY_ORDERS_PAGE_REAL = 100` · `_DAILY_ORDERS_PAGE_VTS = 15`(정본 `docs/kis/domestic-stock-order.md:3839-3840` — 실전 1회 100건, 모의 15건). `settings.is_production`(`src/config.py:117`)으로 고른다.
- `_sell_fills_by_order(rows, ticker, page_size)` — `page_size` 를 **기본값 없는 세 번째 인자**로(기본값을 두면 그 기본값이 곧 이 결함이다). `len(rows) >= page_size` → `None`.
- `_sell_orders_snapshot` 이 판정한 `page_full` 을 이유로 돌려준다(지금 `:2073-2078` 의 `>= 100` 인라인 판정은 삭제).
- 모의 환경에서 그날 그 종목 매도 주문이 15건 이상이면 늘 종목 크레딧/동결로 간다 — 모의에서만의 보수화이고 실전은 100.

### R2-11. H8 — 재시작 뒤 원장(`_sell_notice_seen`)

**영속 원천 검토 — 건전한 것이 없다**
| 원천 | 판정 |
|---|---|
| `trade_history` 매도 행 | ✗ `update_trade_status` 는 수량을 안 바꾼다 — PENDING/PARTIAL/COMPLETED 행의 `quantity` 는 **주문 수량**이다. `increment` 퇴화(`fields[16]` 없음)에서 우리 주문의 첫 통보가 거짓 「종료」를 만들면 COMPLETED 행이 받은 적 없는 체결까지 「봤다」고 말한다 → seen 과대 → 크레딧 과소 → **과소 추적**(R-INV-1 위반). 쓰면 안 된다 |
| `positions` 행 | ✗ 주문별 정보가 없다(종목 합계 수량뿐) |
| `system_logs` | ✗ 체결 통보 줄은 INFO 「매도 부분 체결/전량 체결」 뿐이고 `_DbLogHandler` 가 500ms 중복 제거·큐·500자 자르기를 한다(유실 가능). `[order_notice]` 는 `CNTG_YN=1`(접수) 전문만 싣는다(`handler.py:714-726`) |
| KIS TTTC0081R 부팅 스냅샷 | 건전하지만 **부팅 배선**(scheduler `_boot`/`boot_manager`)이 필요하다 — `scheduler.py` 무접촉 규칙 + 새 제안 금지 |

**결론** — 과대 추적은 그대로 둔다. 대신:
1. **F-3 은 재시작 뒤에도 보수적이다(공식이 그렇다)** — 재시작 직후 `seen` 이 비어 있으면 `pending` 이 그날의 체결을 **전부**(재시작 전에 이미 반영된 것까지) 세어 eff 가 참값보다 **작다** → 초과분을 크게 본다 → 덜 쏘거나 동결. 재시작 뒤 주문별 재대조가 크레딧을 과하게 적어도, R2-8 의 불변성 때문에 eff 는 재대조 창만큼만 틀린다. 그래서 별도의 「원장 미시드」 게이트를 두지 않는다 — 그 게이트는 벽시계(08:00 기준)를 읽어야 해 CI 를 시간대별로 붉게 만들고(메모리 `feedback_wall_clock_gate_breaks_ci`), 막는 것이 이미 막혀 있다. 테스트 TQ6 이 증명한다(재시작 모양: 새 엔진·`seen` 비움·TTTC0081R 에 재시작 전 체결 4, 초과분 0/5 두 변형 → 첫 발사 뒤 발사 없음, 동결).
2. **남는 한계(문서화)** — 재시작 뒤 첫 주문별 재대조의 크레딧은 `fills − seen(재시작 뒤분)` 이라 재시작 전에 이미 반영된 체결까지 크레딧이 된다. 그 주문(아직 걸려 있는 외부 지정가)이 **재대조 뒤에 더 체결되면** 그 통보가 흡수돼 보유가 안 빠진다 → 과대 추적. 다음 손절의 **1차 발사**(초과분 공식을 타지 않는다)는 추적 수량을 내므로, 계좌에 운영자 초과분이 있으면 그만큼까지 운영자 몫을 팔 수 있다. 조건 = 장중 재시작(보유 중 장중 재시작은 D6 금지) ∧ 재시작 전 부분 체결된 외부 주문이 재시작 뒤에도 체결 중 ∧ APBK0400 재대조 ∧ 운영자 초과분. 확인 = R2-18 F-R2-4.

### R2-12. 테스트 (Red 먼저)

하네스 = `tests/unit/engine/test_cycle385_b7_partial_sell.py` 의 `_make_env`·`_sell_notice`·`_map_order`·`_held`·`_install_place_order`·`_warn_lines`(`kis_env="vts"` 고정 — 쪽 크기 15). 계좌 모형 = 적대 프로브의 `Acct`(보유·걸린 주문·체결 누적; `place_order` 는 `qty > sellable` 이면 APBK0400, `get_daily_orders` 는 체결 누적 행을 돌려준다) — 새 파일 안에 둔다. caplog 는 WARNING 이상 + prefix(INFO 마커 `[selling_freeze_released]` 는 상태로 단언한다). 시제품에서 아래 TQ 전부 통과. 현재 워크트리(`d94adb15…`)에서 실측으로 붉은 것 = TQ1·2·3·5·7·8·9·10·12·14(a)·17 (TQ20·TQ21 은 기대값이 R2 경로라 붉다). TQ4·TQ6·TQ11·TQ13·TQ14(b)·TQ15·TQ16 은 지금도 초록 — 돌연변이 킬러이자 되살아남 방지용이다(R2-14).

**새 파일 `tests/unit/engine/test_cycle385r2_round2.py`** (TQ15·TQ25 의 라우트 변형은 기존 라우트 하네스가 있는 `tests/unit/routes/test_cycle385_manual_sell_selling.py` 에 둔다)
| ID | 무엇(원 프로브) | 입력 | 기대 |
|---|---|---|---|
| TQ1 | H3 · money A1 · XT-K | 추적 10, 계좌 15, MTS-A 3 체결(통보 대기), MTS-B 4 걸림 | 발사 `[10, 3]` · `get_daily_orders` await 1회, 키워드 정확히 `{exchange:"ALL", pdno:TICKER}` · 추적 10 그대로 · `save_position` 0 · 이어서 A 통보 3 → 7, 우리 3 체결 → 4, B 4 → 닫힘 · 우리 매도 합 ≤ 3 |
| TQ2 | H3 분기 술어 | 추적 10, 계좌 15, A 6 체결(대기), B 2 걸림(held 9 < 10) | 발사 `[10, 2]` · `save_position` 0(초과분 채택 없음) |
| TQ3 | H3 조회 실패 | 추적 10, 계좌 10, B 3 걸림, 조회 `RuntimeError` | 발사 `[10]` · `_selling`·`_selling_locked_wait` 에 종목 · `[sell_qty_partial_locked]` 에 `fire=0` · `orders=error` |
| TQ3b | 같은 것, param `timeout`/`bad_row`/`page_full` | 조회 0.5초 지연(상수 0.01) / `tot_ccld_qty=""` / 16행 | 발사 `[10]` · `orders=` 가 각 이유 |
| TQ4 | 부록 R TR2 의 재대조 판(주문별 크레딧이 pending 에서 빠진다) | 추적 12(유령 2), 계좌 10, A 3 체결(대기), B 2 걸림 | 발사 `[12, 7, 5]` · `_sell_reflected_credit == {"MTS-A": 3}` · A 통보 → 7 |
| TQ5 | 종목 크레딧은 pending 에서 빼지 않는다(보수) | 추적 10, 계좌 10, A 3 체결. 1차 조회 실패(→ 종목 크레딧 3, 추적 7), 2차 발사 직전 B 2 걸림, 2차 조회 성공 | 발사 `[10, 7, 2]` |
| TQ6 | H8 재시작 모양 | 새 엔진(원장 빈), 추적 10, 계좌 10+s(s∈{0,5}), MTS-X 재시작 전 체결 4(행 tot 4) · 8 걸림 | 첫 발사 10 · 그 뒤 발사 전부 ≤ 2(실측: 0 — 동결) |
| TQ7 | H2 · money A3 · p5 · XT-D | 추적 10, 계좌 10, A 3 체결(대기), B 2 걸림, 조회 항상 실패, 2차 발사 직전 B 2 체결 | 종목 크레딧 5(3+2) · A 통보 1(payload 3) 뒤 크레딧 4(통째 삭제 아님) · 추적 5 · A 2·B 2 통보 뒤 추적 == 계좌 == 5 |
| TQ8 | H6 | 조회가 0.5초 잔다, `SELL_ORDERS_QUERY_TIMEOUT` 0.01, 계좌 7 | 발사 `[10, 7]` · 종목 크레딧 3 · `reason=timeout` |
| TQ9 | H7 파서 | `(vts,15)→None` `(vts,14)→dict` `(real,15)→dict` `(real,100)→None` · 서명 | `page_size` 기본값 없음(`inspect.signature`) |
| TQ10 | H7 배선 | vts, 다른 주문 15행 + 계좌 7 | `reason=page_full` · 종목 크레딧 3 |
| TQ11 | XT-E | 보유 전략 0, 통보 `0000077` 4주(payload 9) | `_sell_notice_seen == {"77": 4}` |
| TQ12 | H5 거부 · seed 1068 | 자동 주문 S1 10(매핑, `_selling` 섬), 통보 4 → 타이머(대기 0) → 취소 성공 → 재주문 APBK0400 | `_selling`·`_selling_since` 비움 · `[reorder_selling_released] ... place=rejected` · 이어서 `execute_sell` 이 6주 발사(막히지 않는다) |
| TQ13 | H5 모호 | 같은 입력, 재주문이 `TimeoutError`(전송 뒤 응답 유실) | `_selling` **유지** |
| TQ14 | H5 교체 취소 | (a) CANCELLED 장부 await 에서 태스크 `cancel()` (b) `place_order` await 에서 `cancel()` | (a) 해제 `place=none` (b) 유지 |
| TQ15 | XT-A · XT-I · XT-M | S1 이 `_selling` 주인. 손님 manual `MAN-1`(표식 False) 1주 부분 → 재주문 거부 / 변형: 재주문 `MAN-2` 접수(상속 False) → MAN-2 부분 → 재주문 거부 / 라우트 변형: `_selling` 선재 상태로 라우트 manual → 부분 → 재주문 거부 | 셋 다 `_selling` 유지 · `_manual_sell_orders["MAN-2"] is False` |
| TQ16 | XT-J | 보유 전략 0, 손님 manual `MAN-1` 5주(표식 False) 2주 부분 → 타이머 | 재주문 `quantity=3`(`verdict=manual`) |
| TQ17 | R2-5 동결 닫힘 해제 | 추적 3, 계좌 3, MTS-9 3 걸림(sellable 0) → `[sell_qty_locked]` · 그 뒤 MTS-9(주문 9주) 3주 **부분** 통보 | 추적 닫힘 · `_selling`·`_selling_locked_wait` 비움 |
| TQ18 | H4 | 동결 + 매핑된 손님 manual 3주 map 전량 종료 | `_selling`·표식 비움 |
| TQ19 | H1 · p4a/p4b/p4c · money A2 | 적대 프로브 그대로(장부 lookup 을 게이트로 멈춰 통보가 REST 응답 뒤 재개) | p4a: 닫힘·`_selling` 비움 / p4b: 추적 3·운영자 취소 뒤 손절 3 발사 / p4c·A2: 추적 6·손절 `[6]` |
| TQ20 | p1 을 R2 에 맞춘 판 — param `ok`/`fail`/`unpatched`(`src.api.base._request` 차단) | 추적 10, 1차 APBK0400, 계좌 7/7, 행 MTS-1 tot 3 · MTS-1 통보는 `execute_sell` **반환 뒤** | 셋 다 발사 `[10, 7]`. `ok`: 추적 10(F-3, 재대조 아님) → MTS-1 통보 → 7. `fail`·`unpatched`: 재대조(종목 크레딧 3) → 추적 7 → MTS-1 통보 흡수 → 7. 이어서 우리 7 → 닫힘 · `_selling` 비움 |
| (p2) | p2 — manual 잔여 재주문 | — | **부록 R TR22 가 이미 이식본**(`test_cycle385_reorder_requery.py`, 무변경) |
| TQ21 | repro(rp) 를 R2 에 맞춘 판 | 부록 R TR2 입력, 조회 성공 / 실패 | 성공: 발사 `[10, 5]` · 매 단계 추적 ≥ 계좌 · 끝 0 / 실패: 발사 `[10, 7]` 뒤 동결 · 매 단계 추적 ≥ 계좌 · B 종료 통보가 `_selling` 해제 · 다음 `execute_sell` 5 발사 → 0 |
| TQ22 | p3 · p3b(두 변형) | 적대 프로브 그대로 | 🔴 `pytest.mark.xfail(strict=True, reason="LOW #3 알려진 한계 — 부록 R2-1, F-385-5")` — B7 에서도 실패하는 성질. 등록부가 생기면 뒤집힌다 |
| TQ25 | 진입이 낡은 동결 표식을 지운다(닫힘 해제가 새 주인을 풀지 않는다) | 표식만 남은 상태에서 `execute_sell` 접수(우리 10 걸림) → 외부 부분 체결이 추적을 0 으로 | `_selling` **유지**(우리 주문이 걸려 있다) · 라우트 진입 변형 동일 |

**기존 테스트 기대값 변경(사유 동반 — 조용히 지우지 않는다)**
| 테스트 | 지금 | 바꾼 뒤 | 사유 |
|---|---|---|---|
| `test_cycle385r_recount_credit.py` TR1(두 param)·TR4·TR9·TR10 | 추적 10 · 오늘 행으로 설명되는 차이 → 재대조 | 보유를 **12(유령 2)** 로 — 재대조 분기가 계속 검증되게. 발사 기대의 첫 값 12 | R2-8 분기 술어(eff). 오늘 주문으로 설명되는 차이는 이제 F-3 으로 간다(TQ1·TQ20 이 그 경로를 지킨다) |
| 같은 파일 TR2 | `[10, 7, 5]` | `[10, 5]`(TQ21 과 같은 입력) · 매 단계 추적 ≥ 계좌 불변 | 재대조 단계 없이 F-3 |
| 같은 파일 TR7b | `[10, 7, 5]` | `[10, 7, 2]`(= TQ5) | R2-8 종목 크레딧 비차감(보수) |
| 같은 파일 `test_tr_parser_filters_sums_and_refuses_partial_trust` | `parse(rows, TICKER)` | `parse(rows, TICKER, 100)` 등 page 인자 명시 | R2-10 서명 |
| `test_cycle385r_partial_locked_sell.py` TR13 | 「F-3 새 KIS 호출 0」(`get_daily_orders.await_count == 0`) | `await_count == 1` + 키워드 `{exchange:"ALL", pdno:TICKER}` | R2-8 — F-3 도 조회한다 |
| 같은 파일 TR18 | `_selling` 유지 | TQ22 처럼 `xfail(strict=True)` | R2-1 LOW #3 |
| 같은 파일 TR19(main·fallback) | `[selling_released_after_window]` 1행 | 마커 단언 삭제, 「반환 뒤 `_selling` 비어 있음」 유지 | R2-2 — 종료 자체가 푼다 |
| 같은 파일 TR21 | 낡은 표식 + 무관 종료 → 유지 | TQ25 로 교체 | R2-5 |
| `tests/unit/routes/test_cycle385_manual_sell_selling.py` TR20·TR20b | 손님 manual 종료가 주인 `_selling` 을 안 푼다 | `xfail(strict=True)` | R2-1 LOW #3(같은 성질의 손님 변형) |
| 같은 파일 TR21b | 라우트 진입 + 무관 종료 → 유지 | TQ25 라우트 변형으로 교체 | R2-5 |
| `test_cycle236_sell_qty_exceeded.py` | fixture 가 `get_daily_orders` 를 `[]` 로 패치 | 무변경(이미 패치) — F-3 기대 `[3, 1]` 그대로 | — |

### R2-13. AST 가드 (`tests/unit/ast/test_cycle385_ast_b7.py`)

| ID | 단언 | 부록 R 대비 |
|---|---|---|
| AR2-1 | (H1) R2-3 의 (가)~(마) 다섯 단언 — 주문 축 If 의 첫 문장 = `self._selling.discard(ticker)`(첫 `Await` 앞, 감싸는 If 없음) · `qty_src` 가 해제를 가르지 않음 · 닫힘 해제 If 는 `ticker`·`self._selling_locked_wait` 만 읽음 · `ticker`·`order_no` 대입 0. 전략 미등록 오류 경로(`if not strategy:`)는 범위 밖 | AR6 대체 |
| AR2-2 | `order_engine.py`·`routes/trading.py` 에 `_sell_placed`·`_sell_end_releases_selling`·`_sell_orders_done` 이름과 문자열 `[selling_kept]`·`[selling_released_after_window]` 0 | AR7·AR10b 대체 |
| AR2-3 | (H5) `_cancel_and_reorder` 최상위에서 `_cancel_ok`·`_place_state` 대입이 `Try` 앞 · `place_order` await 가 `except KisApiError` 핸들러(본문 = `_place_state = "rejected"` + 맨 `raise`)를 가진 `Try` 안 · 그 앞에 `_place_state = "sending"` · `finally` 에 `self._selling.discard(ticker)` 가 있고 그 If 테스트가 `_cancel_ok`·`_place_state`·`self._manual_sell_orders` 를 읽는다 · `finally` 안 `Await` 0 | 신규 |
| AR2-4 | (H2) `_sell_blind_credit[ticker]` 대입의 우변이 `self._sell_blind_credit.get(ticker, 0) + _blind`(또는 `+=`) — 맨 `_blind` 대입 0 | 신규 |
| AR2-5 | (H3) `execute_sell` 에 `await self._sell_orders_snapshot(ticker)` 정확히 1개, `await get_balance()` 뒤 · 바로 뒤 문장이 `positions.get(ticker) is not pos` If · 그 뒤 ~ `pos.quantity = target_qty` / `sell_cap = fire` 사이 `Await` 0 · F-3 If 테스트가 `held_qty >= eff` · `eff` 우변에 `pos.quantity - pending` · `fire` 대입에 `fills is not None` 조건 | AR1·AR4 대체 |
| AR2-6 | (H6·H7·XT-K) `_sell_orders_snapshot` 안 `asyncio.wait_for(` 가 `timeout=SELL_ORDERS_QUERY_TIMEOUT` · 그 안 `get_daily_orders` 호출 키워드가 정확히 `exchange="ALL"`·`pdno=ticker` · `settings.is_production` 을 읽는다 · `_sell_fills_by_order` 서명 `(rows, ticker, page_size)` 기본값 없음 · 모듈에 리터럴 `>= 100` 0 | 신규 |
| AR2-7 | (R2-5) 닫기 묶음(`if close_position:`) 안 `self._selling.discard` 가 `ticker in self._selling_locked_wait` If 안에 있고 그 묶음의 첫 `Await` 앞 | 신규 |
| AR2-8 | `_sell_pending_dec` 동기 def · `Await` 0 · `_sell_notice_seen`·`_sell_reflected_credit` 를 읽고 `_sell_blind_credit` 를 **읽지 않는다** | 신규 |
| AR10 | 매개변수 목록 → `["_sell_fills_by_order", "_odno_key", "_sell_pending_dec"]` 동기·await 0 | 목록 교체 |
| AR11 | `_R_DAILY` → `_sell_notice_seen`·`_sell_reflected_credit`·`_sell_blind_credit`·`_manual_sell_orders`·`_selling_locked_wait`(다섯) | `_sell_orders_done` 삭제 |

A1·A3·A3b·A4·A4b·A5*·A6·A7·A8·A9·A10·AR2·AR3·AR4b·AR5·AR8·AR9·AR12·AR13·G147-AST-1·g273_ast1~4·G-295-C4·test_g328_1/3b 는 **그대로 초록**이어야 한다.

### R2-14. 돌연변이 계획 (23종 — 시제품에서 전부 죽음, 러너 `c385r2/mut_r2.py`)

| # | 돌연변이 | 죽인 것(시제품 실측) |
|---|---|---|
| MQ1 | 주문 축 해제를 `if qty_src == "map":` 아래로(H1 결함 복귀) | money A2 → TQ19 · AR2-1 |
| MQ2 | 종목 크레딧 덮어쓰기(H2) | TQ7 · AR2-4 |
| MQ3 | 종목 크레딧 부분 소진 시 통째 삭제(XT-D) | TQ7 |
| MQ4 | pending 무시(`eff = pos.quantity`) | TQ1(`[10, 6]`) |
| MQ5 | 분기 술어를 `held_qty >= pos.quantity` 로 | TQ2(`[10, 9, 7]`) |
| MQ6 | 조회 실패에도 F-3 발사 | TQ3(`[10, 7]`) |
| MQ7 | pending 에서 주문별 크레딧 미차감 | TQ4(`[12, 7, 2]`) |
| MQ8 | pending 에서 종목 크레딧 차감 | TQ5(`[10, 7, 5]`) · AR2-8 |
| MQ9 | `wait_for` 제거 | TQ8 |
| MQ10 | 쪽 크기 100 고정 | TQ10 · AR2-6 |
| MQ11 | `>=` → `>` | TQ9(vts 15) |
| MQ12 | 조회 `exchange="KRX"`(XT-K) | TQ1 · AR2-6 |
| MQ13 | 원장이 보유 없는 통보를 건너뜀(XT-E) | TQ11 |
| MQ14 | manual 분기를 `.get(order_no)` 로(XT-J) | TQ16 |
| MQ15 | 재주문 표식 상속을 `True` 로(XT-I) | TQ15(2세대) |
| MQ16 | H5 주인 판정 삭제(XT-A) | TQ15(1세대) |
| MQ17 | H5 를 `rejected` 에만 | TQ14(a) |
| MQ18 | H5 를 `sending` 에도 | TQ13 · TQ14(b) |
| MQ19 | H5 해제 삭제 | TQ12 |
| MQ20 | 동결 닫힘 해제 삭제 | TQ17 |
| MQ21 | 동결 닫힘 해제를 무조건 | 기존 T6(`주문 부분 · 보유 0` 에서 `_selling` 유지) |
| MQ22 | `[sell_qty_locked]` 의 동결 표식 add 삭제 | TQ17 |
| MQ23 | 동일성 재검증 삭제 | 부록 R TR6 |

- 부록 R 의 MR1~MR21·MR27~MR32 와 본문 M1~M30 은 그대로 다시 돌린다. **MR22~MR26(소유 규칙) 은 폐기**(대상 코드가 없다).
- 시제품 러너는 스크래치 전용이다 — 구현본에서 tester 가 같은 23종을 다시 적용해 킬을 잰다.

### R2-15. 마커

| 마커 | 레벨 | cap | 필드 | 뜻 |
|---|---|---|---|---|
| `[reorder_selling_released]` (신규) | WARNING | 없음(드묾) | `ticker= order_no= place=none\|rejected` | 원주문 취소 뒤 우리 재주문이 안 걸려 `_selling` 을 풀었다(H5) |
| `[selling_freeze_released]` (신규) | INFO | — | `ticker= order_no= reason=position_closed` | 동결이 지키던 보유가 닫혀 동결을 풀었다(R2-5) |
| `[sell_qty_partial_sellable]` (변경) | WARNING | 없음 | 기존 + `pending=` | F-3 발사. `pending>0` = 걸린 외부 체결 통보를 빼고 쐈다 |
| `[sell_qty_partial_locked]` (변경) | WARNING | 없음 | 기존 + `pending=<n\|?> orders=ok\|error\|timeout\|bad_row\|page_full` | `orders≠ok` = 조회를 못 믿어 동결(H3) |
| `[sell_qty_reconcile_orders_unavailable]` (변경) | WARNING | 없음 | `reason=` 에 `timeout` 추가 | — |
| `[selling_kept]` · `[selling_released_after_window]` | — | — | — | **삭제**(R2-2) |

전부 `logger.*` 만(새 `write_log`·DB 0), 행위 밖. 신규 `KstDailyEmitCap` 0.

### R2-16. 핀 · 사유 주석 정정 · 문서

- `order_engine.py` whole-file sha **10곳**(현재 값 `d94adb15a55ee026607bf6e0bc129729f3fba9cac35871aa314f10dd5f8ce13b`, 착수 전 `grep -rl` 로 다시 센다) 값만 재핀. 새 사유 주석:
  `# 🔁 2026-09-27 (cycle385 부록 R2) 재핀 — 2차 검토 반영: _selling 주인 규칙(R-3) 제거(B7 해제 의미 복귀) · 재주문이 안 걸리면 _selling 해제(H5) · F-3 이 걸린 외부 체결 통보를 먼저 뺀다(H3) · 종목 크레딧 누적(H2) · 주문 조회 2초 상한·환경별 쪽 크기(H6·H7) · 동결 보유가 닫히면 동결 해제. 사용자 승인(8영역), 나머지 7영역 diff 0.`
- **부록 R 사유 주석 정정**(10곳 공통 문구): 「F-2(수동주문 J-2 재조회는 보유대로 보존)」 → 「F-2(manual 라우트 주문의 잔여 재주문은 보유와 무관하게 `remaining` 을 쏜다 — `_manual_sell_orders` 표식)」. 「F-3(잠금 중 판매 가능분은 판다)」는 사실이라 유지.
- `test_cycle287_ast_scope.py::_BASE_SHA["src/api/balance.py"]` — R2 에서 `balance.py` 는 **안 바뀐다**(값 무변경). 주석만 정정: 「(F-1 … 사용자 승인 8영역)」 → 「(비8영역 — `src/api/balance.py` 는 8영역 목록 `_EIGHT_AREAS` 에 없다)」.
- `test_cycle287_ast_scope.py::_SRC_TREE_DIGEST` — `routes/trading.py` 가 또 바뀌므로(`_sell_placed` 호출·docstring) 값 재핀. 부록 R 주석 정정: 「`routes/trading.py` … 와 `src/api/balance.py` … 가 더 바뀌어」 → 「`routes/trading.py`(manual 표식·`_selling_locked_wait` 정리) · `src/api/balance.py`(`pdno=`) · `src/db/positions.py`(`save_position` 빈 이름 무시 COALESCE/NULLIF) 가 더 바뀌어」. R2 주석 = 「🔁 cycle385 부록 R2 재핀(값만, 파일 수 불변 162) — `routes/trading.py` 의 `_sell_placed` 호출 삭제(R-3 소유 규칙 제거). 직전 값 = `d77b1be6…`」.
- **붉어지면 범위 밖을 건드린 것**(재핀 금지): `test_cycle295_ast_market_rest.py::_BYTE_IDENTICAL_PINS` · `_FROZEN_SEGMENTS` · `scheduler.py`(3,786줄) · `src/realtime/**` · `src/api/balance.py`·`src/db/positions.py`(R2 무접촉).
- `_workspace/test_index.yaml` 재생성 · `tools/test_impact/manual_overrides.yaml` 에 새 파일 등록(부록 R 선례).
- 문서 갱신 후보(`/sync-docs` → report-writer): `src/engine/CLAUDE.md`(부록 R 이 넣은 `_selling` 주인 규칙 문단을 R2 로 교체 — 「어느 주문의 종료든 푼다 · 재주문 안 걸리면 푼다 · 동결 보유 닫히면 푼다 · LOW #3 알려진 한계」, F-3 eff·조회 필수·2초·쪽 크기, 마커 표) · `src/routes/CLAUDE.md`(manual-sell `_sell_placed` 삭제) · `_workspace/00_leader_trading_rules.md`(부록 R 이 적은 주인 규칙 줄) · `docs/architecture.md`(부록 R 반영분 중 주인 규칙) · history 파일(append).

### R2-17. 수용 기준 측정 절차 (tester)

1. 무작위 프로브 = `c385t/probe/test_probe_t.py`(**무수정**), 400 시드 × payload 1.0/0.0/0.6. 트리 = 구현 워크트리 vs `c385r/base`(B7). 모드 = M0(기본) · M2(`PROBE_ORDERS=fail`) · M4(`PROBE_SURPLUS=1`) — 기준 = B7 M0 · B7 M0 · B7 M4. 참고로 M1·M3·M5 도 돌려 표에 싣는다. 러너 선례 = `c385t/run_matrix.sh`(프로브 파일은 **워크트리의 조상이 아닌** 디렉터리에 둔다 — 조상에 두면 `conftest.py` 의 `pytest_plugins` 가 루트 밖으로 읽혀 수집이 깨진다).
2. 비교 = `mk_*`·`runs`·`recount_orders_query` 를 뺀 모든 키. 시제품 기대값 = R2-1 표. `oversell_*`(거부된 발사 횟수)·M5 는 R2-1 「B2 가 B7 를 넘는 칸」의 원인과 함께 표에 따로 적는다 — 넘으면 원인이 그 둘인지 시드 트레이스로 확인한다(`PROBE_ONE=<seed>`).
3. 적대 프로브 = p1(ok·fail·unpatched) · rp(ok·fail) · p2 · p3 · p3b(2) · p4a · p4b · p4c · p5 · money A1·A2·A3 · seed 1068. **p1[ok]·rp[fail] 의 원문은 R2 규칙과 다른 것을 단언한다**(p1[ok] = 알림을 `save_position` 안에서 주입 — F-3 경로는 저장하지 않는다 / rp[fail] = 조회 실패 뒤 매도 기대 — H3 가 동결을 명한다) → TQ20·TQ21 로 옮긴 판을 기준으로 한다. **p3·p3b 는 LOW #3 이라 경로 B2 에서 실패가 정상**(B7 도 실패) → TQ22 xfail strict. 시제품 결과 = 나머지 11개 전부 통과, seed 1068 정산점 좀비 0.
4. 전체 스위트(메모리 `feedback_rerun_suite_after_edit`) — 시제품(`tests/unit`+`tests/contract`, 12,945 통과)에서 cycle385 관련으로 붉어진 것은 R2-12·R2-13 표의 19건(TR1×2·TR2·TR4·TR7b·TR9·TR10·TR13·TR18·TR19×2·TR20·TR20b·TR21·TR21b·AR1·AR4·AR6·AR7)과 8영역 sha 핀뿐이었다(그 밖의 붉음은 스크래치 복사본에 `frontend/`·`docs/`·`e2e/`·`macro/`·git 이 없어서 생긴 것). 시제품은 죽은 정의를 남겨 두었고 파서 `page_size` 에 기본값을 두었으므로, 구현본에서는 AR10·AR10b·AR11 과 파서 테스트 1건이 더 바뀐다(표에 있다).

### R2-18. 09-28 확인 추가 (§o·R-14 뒤)

| # | 무엇 | 어떻게 | 무엇이면 멈추나 |
|---|---|---|---|
| F-R2-1 | TTTC0081R 응답 시간 | 잔고 재대조가 있었던 날 `[kis_rejection]`·API 메트릭의 `inquire-daily-ccld` 지연 분포(p99) | p99 가 1초를 넘으면 2초 상한이 자주 걸린다 — 기록하고 보고 |
| F-R2-2 | `_cancel_and_reorder` 재주문 거부 빈도 | 30일 `system_logs` 「매도 잔여 취소/재주문 실패」 + 「손절 잔여 재주문」 | 정보용(H5 가 여는 경로가 실전에서 도는지) |
| F-R2-3 | 타이머 교체 경합 | 같은 주문번호의 `[after_cancel_result] result=ok` 뒤 `result=error err=[APBK0927]` 쌍 | 정보용(R2-1 뿌리의 실전 빈도) |
| F-R2-4 | 장중 재시작 기록 | 30일 `_boot` 기동 시각이 08:00~20:00 인 날 | 있으면 R2-11 한계의 노출 창 — 기록 |

### R2-19. 반례 / 한계

1. **LOW #3**(R2-1) — 무관한 주문 종료가 `_selling` 을 풀어 우리 주문 옆에 손절이 또 나갈 수 있다. 운영자 초과분 ≥ 추적 잔여일 때만 운영자 몫. B7 과 같은 성질, 무작위 지표는 B7 이하.
2. **조회 실패 + 운영자 초과분**(M5) — 재대조가 초과분을 받아들인다(R-13-8 과 같음). R-INV-1 을 지키는 한 B7 의 우연한 절삭만큼은 못 따라간다.
3. **거부된 발사 증가**(`oversell_*`) — 과소 추적을 없앤 대가. 한 번의 APBK0400 은 #1.5 가 흡수한다.
4. **재시작 뒤 과대 추적**(R2-11 ②).
5. **`_selling` 에 주인 식별자가 없다(ABA)** — H5·닫힘 해제·종료 해제가 푸는 순간 다른 코루틴이 새로 세운 `_selling` 일 가능성은 LOW #3 경로로 `_selling` 이 한 번 풀린 뒤에만 생긴다. 그 경우 결과는 B7 과 같다.
6. **H5 모호 구간** — 재주문 전송 중 예외·교체 취소는 유지한다(보수). 그 `_selling` 은 우리 재주문이 실제로 걸렸으면 그 종료가, 안 걸렸으면 `selling_reconcile` 이 푼다.
7. **eff 오차** — (가) 주문별 재대조의 t1~t2 창(수백 ms) 체결만큼 eff 가 클 수 있다(부록 R-1-6 의 과대 추적 창과 같은 크기). (나) 조회 실패 재대조가 남긴 종목 크레딧이 흡수된 뒤에는 그 크레딧의 유실 통보 몫(E)만큼 eff 가 클 수 있다 — 조회 실패 뒤 조회 성공 F-3 가 이어지고 운영자 초과분이 있을 때만 운영자 몫으로 번진다(R2-8 요지, 부록 R-13-4 와 같은 원인).

후속(범위 밖, 한 줄): **F-385-6** `_schedule_cancel_and_reorder` 가 원주문 취소를 이미 낸(= 커밋된) `_cancel_and_reorder` 태스크를 취소하는 경합(R2-1 뿌리) — 재주문 유실·무매핑 재주문. F-385-5(걸린 우리 매도 등록부)와 함께 봐야 R-3 을 다시 세울 수 있다.

### R2-20. 대체 목록 (이 부록이 이기는 자리)

| 자리 | 대체 |
|---|---|
| 부록 R-0 (c) 행 · R-3 전체(R-3-3 규칙·상태 `_sell_orders_done`·헬퍼 2개·적용 자리 표, R-3-4, R-3-5) | R2-1·R2-2 — 제거. LOW #3 알려진 한계 |
| 부록 R-2-2 F-3 규칙(`surplus = held − pos.quantity`, 새 호출 0) | R2-8 — eff·pending·조회 필수·조회 실패 = 동결 |
| 부록 R-1-3 ③(인라인 `get_daily_orders`)·R-1-4 ②(`>= 100`) | R2-8 `_sell_orders_snapshot` · R2-9 · R2-10 |
| 부록 R-1-3 ⑥ 종목 크레딧 대입 | R2-7 누적 |
| 부록 R-1-7 「F-3 새 호출 0」 · R-1-8 실패 표 | F-3 도 1건 · `timeout` 추가 · F-3 조회 실패 = 동결 |
| 부록 R-6 `[selling_kept]`·`[selling_released_after_window]` 행 | 삭제 · R2-15 |
| 부록 R-7 TR13·TR18~TR21·TR20·TR20b·TR21b, R-8 AR1·AR4·AR6·AR7·AR10·AR10b·AR11, R-9 MR22~MR26 | R2-12·R2-13·R2-14 |
| 부록 R-12 「`_selling` 좀비 없음」 행 · R-13-5·6 | R2-19 |
| 부록 R-5 (b)·TR26 | 무변경 |
| 본문 §g-1 「J-2 `place_order` 실패 → 유지 → selling_reconcile」 행 · §n F-385-4 | R2-6 — 원주문 취소 성공 + 재주문 미접수면 해제. F-385-4 해소 |
| 본문 §g-1 「체결 통보 — 주문 종료」 두 행 | 조건 없이 해제(B7 의미, R2-2) |

### R2-21. 하드 불변식 대조

| 불변식 | 이 부록 뒤 |
|---|---|
| `fields[9]` 체결수량 | 무접촉(`handler.py` diff 0) |
| 주문수량 3단 출처 | 무접촉 |
| 전량 판정에 출처 게이트 없음 | 주문 축·보유 축 판정 무변경. 해제는 이제 **조건조차 없다** · A10 초록 |
| 재주문 타이머 `qty_src=="map"` 한정 · `(ticker, side)` 키 | 무접촉(`_schedule_cancel_and_reorder` 무변경) |
| `_persist_sell_pending_after_send` 넓은 `except` | 무접촉 — 앞의 `_sell_placed` 동기 호출이 빠질 뿐(`test_g328_1`·`3b` 초록) |
| `_selling` 좀비 없음 | 종료 해제 무조건 + H5 + 닫힘 해제. 남는 유지 = H5 모호 구간(`selling_reconcile` 이 수습, R2-19-6) |
| `on_position_closed` 보유 0 에서만 · site 정확히 2함수 | 신규 site 0(닫힘 해제는 같은 묶음 안의 `_selling` 조작뿐) |
| A-ATOMIC | `execute_buy` 무접촉 |
| 8영역 재핀 값만 + 사유 | R2-16(사유 주석 정정 포함) |
| `scheduler.py` · `src/realtime/**` 무접촉 | 무접촉 |
| 검사 ~ 행동 사이 await 추가 금지 | 새 await = `_sell_orders_snapshot` 1개(부록 R 의 인라인 조회를 옮긴 것 — 개수 불변). 뒤에 동일성 재검증 + eff 를 await 뒤 상태로 계산(R2-8 논증). H5·닫힘 해제·종료 해제는 전부 동기 |

### R2-22. Red 착지 (tdd-engineer · 2026-09-27)

- 파일 — 새 `tests/unit/engine/test_cycle385r2_round2.py`(TQ1~TQ25) · `tests/unit/routes/test_cycle385_manual_sell_selling.py`(TQ15·TQ25 라우트 판, TR20·TR20b strict xfail, TR21b 삭제) · `test_cycle385r_recount_credit.py`·`test_cycle385r_partial_locked_sell.py`(R2-12 표 그대로) · `tests/unit/ast/test_cycle385_ast_b7.py`(AR2-1~AR2-8 추가, AR1·AR4·AR6·AR7·AR10b 삭제, AR10·AR11 교체). AR4 의 F-3 본문 단언(추적 대입 0 · `sell_cap = fire` 1 · return 앞 동결 표식)은 AR2-5 에 합쳤다.
- 표 밖 추가(성질 보존·명세 문장 그대로의 단언뿐) — **TQ5b**: TR7b 기대값이 F-3 경로로 바뀌어 「조회 성공 재대조는 앞선 종목 크레딧을 버린다」(R2-7 무변경)를 재는 테스트가 사라졌다 → 그 성질만 따로 잰다(돌연변이 XR12 킬러). **TQ8b** 상수 2.0(R2-9). **TQ9b** `page_size` 기본값 없음(TQ9 의 서명 단언 분리). **TQ12 `own_manual`** 파라미터(R2-6 「manual `_added` 참은 참」). **TR12** `_R_STRUCTS` 에서 `_sell_orders_done` 삭제(R2-2 — 남기면 Green 에서 AttributeError).
- AR2-1·AR2-3·AR2-7 은 판정식을 **평가**한다 — If 테스트를 떼어 허용된 이름(`ticker`·`self`·`_cancel_ok`·`_place_state`·`order_no`)만 넣고 돌려 진리표를 맞춘다. 다른 값을 읽으면 `NameError` 로 붉다(H1 「await 전에 잡은 값을 읽지 않는다」 의 구조 가드).
- `manual_overrides.yaml` 등록 없음 — 새 파일은 함수 안 import 로 `order_engine`·`routes/trading`·`api/balance` 에 정적으로 잡힌다(`build_index.py` 재생성으로 확인).
- 스크래치 참조(구현본 아님 — 주석·문서 정리 없음) = scratchpad `c385r2t/ref_r2_order_engine.patch` · `c385r2t/ref_r2_trading.patch`(R2-2~R2-10 그대로, 죽은 정의 삭제·`page_size` 기본값 없음). 생성기 `c385r2t/make_ref.py`, 돌연변이 러너 `c385r2t/mut_ref.py`.

---

## 부록 R3 — 3차 검토 반영(K1~K5)

- 작성: domain-expert · 2026-09-28(월) 새벽 KST · 워크트리 `auto_stock_c385`(B7 + 부록 R + R2 구현 위, 미커밋, `order_engine.py` sha `235165aa…`). 줄 번호는 **이 부록 작성 시점의 워크트리 줄**이다.
- 입력: 3차 검토(코드 GO · tester 조건부 PASS · 돈 렌즈 NO-GO)의 K1(MEDIUM) · K2 · K3 · K4 · K5(LOW·테스트 위생). N2 는 문서화된 한계(R-13-4) 그대로.
- 방법: 스크래치 복사본에 **시제품**을 만들어 적대 프로브·결정적 테스트·무작위 프로브(재시작 모의 추가)·돌연변이를 직접 돌린 뒤 규칙을 적었다. 시제품 = scratchpad `c385r3k/` — 생성기 `make_proto.py`(`V1c` = 이 부록 규칙 전부) · diff `ref_r3_order_engine.patch`·`ref_r3_trading.patch` · 결정적 테스트 `red/test_cycle385r3_round3.py`·`red/test_cycle385r3_manual_route.py`·`red/test_k5_rewrites.py` · 적대 이식판 `ports/test_r3_ports.py` · 재시작 모의 프로브 `probe/test_probe_r3.py`(생성기 `gen_probe.py`, 원 프로브 `c385t/probe/test_probe_t.py` 무수정) · 러너 `run_matrix.sh` · 비교 `gate.py`·`r3_tables.md` · 돌연변이 `mut_r3.py`→`mut_r3_results.json` · 전체 스위트 `full_v1c.log`/`full_ref.log`. 시제품은 구현본이 아니다(주석·문서 정리 없음) — 이 부록의 코드 블록이 정본이다.
- 사용자 규칙 「새 제안 금지」 — 지적 K1~K5 만 다룬다. 지시 밖으로 넣은 것은 **K1 에 딸린 최소 규칙 1건**(R3-1-5 크레딧 상한)뿐이고, 없으면 K1 의 처방이 재시작 모의에서 B7 을 넘는다는 측정값을 같이 적는다(부록 R2-5 선례). 지시와 충돌하는 1점(「걸린 것 없으면 절대 동결하지 않는다」)은 R3-1-6 에 측정값과 함께 **결정 요청**으로 올린다.

### R3-0. 결론 (한눈에)

| 지적 | 판정 | 처방 한 줄 | 자리 |
|---|---|---|---|
| **K1** | 재현(원문 N3 발사 `[5,5,5,5]` 매도 0 · N3b `[7,1,6,6,6]` 매도 1 — B7 은 다 판다). **부팅은 복원 수량을 KIS 에 맞추지 않는다**(R3-1-1) → 「원장 시작 전 주문 = 다 봤다」 시드는 틀린 전제 | 원장 시작 시각 `_sell_ledger_since` 을 두고, TTTC0081R `ord_dt`+`ord_tmd` 가 그보다 앞인 주문은 **pending 에서 뺀다**(분기 = B7 의 보유 대 추적 비교로 돌아간다). 그 주문의 재대조 크레딧은 **상한**(재대조 폭 + 남은 크레딧 − 뒤 주문 크레딧). 걸린 것 없는 보류는 문구를 `[sell_qty_unnoticed_fills]` 로 분리 | `order_engine.py` |
| **K2** | 재현(N1: 운영자 6주 매도) | 재주문 `KisApiError` 중 **APBK0400(`is_sell_qty_exceeded`)만** 「안 걸렸다」, 나머지는 「전송 중」(유지). manual 라우트 `_sent` 도 **같은 결함이 있다** → 같은 전제(APBK0400 만 되돌림) + `[manual_sell_selling_kept]` | `order_engine.py` · `routes/trading.py` |
| **K3** | 재현(h4h5 잔여) | H5 해제 주인 판정 = `ticker in self._selling_locked_wait or self._manual_sell_orders.get(order_no, True)` | `order_engine.py` |
| **K4** | 테스트 공백(XF3c 생존) | 주문별 `max(0, …)` 를 단위·행위 두 테스트로 고정 | 테스트 |
| **K5** | 사실 | TR18·TR20 을 마커 없이 LOW #3 **행위만** 재는 strict xfail 로(고쳐지면 XPASS 로 뒤집힌다 — 실측). 낡은 주석 2곳 교체 | 테스트 · `manual_overrides.yaml` |
| N2 | 유지(R-13-4) | TK13 strict xfail 로 한계를 고정 | 테스트 |
| 부팅·scheduler | **변경 불요**(R3-1-1 — 부팅 무접촉으로 K1 이 닫힌다) | `boot_manager.py`·`scheduler.py`·`src/realtime/**` 무접촉 | — |

수용(시제품, R3-10 절차): 재시작 없음·원장 재시작(지시판) 모두 M0·M2·M4 의 목록 지표 ≤ B7(표 R3-1-7). 결정적 테스트 엔진 17건(16 통과 + TK13 xfail) · 라우트 4건 통과 · 적대 프로브 N1·N3·N3b(이식)·N3c·N3d·N4·A1·A2·A3·p1/rp(재기준판)·h4h5·p2·p4a/b/c·p5 통과 · 돌연변이 21종 전부 죽음 · 전체 스위트에서 새로 붉어진 것 = 8영역 sha 핀 · 트리 다이제스트 · AR2-3 · T28(전부 이 부록이 바꾸라고 적은 것).

---

### R3-1. K1 — 재시작 뒤 원장이 빈 채로 pending 이 이미 반영된 체결까지 센다

#### R3-1-1. 부팅이 KIS 수량으로 하는 일 (사실 — 시드 가능 여부의 판정 근거)

| 자리 | 하는 일 |
|---|---|
| `boot_manager.py:187` | `holdings, summary = await get_balance()` — KIS 잔고 1회 |
| `boot_manager.py:274` · `:278-281` | DB `positions` 전부 적재 · `kis_tickers` = KIS 보유 **수량 > 0 인 종목의 집합**(수량 자체는 쓰지 않는다) |
| `boot_manager.py:286-290` | DB 행의 종목이 KIS 에 **없으면** 행 삭제(「DB 포지션 정리 (KIS 미보유)」) |
| `boot_manager.py:300-308` | 남은 행은 `Position(quantity=row["quantity"])` — **DB 수량 그대로** 복원. KIS 수량과 비교·정렬 없음 |
| `boot_manager.py:327` · `:321-386` | DB 에 있는 종목은 KIS 쪽 2차 경로를 건너뛴다. KIS 에**만** 있는 종목만 KIS 수량(`:363`·`:374`)으로 채택 |
| `boot_manager.py:431` | 미체결 복구는 **매수만**(`sll_buy_dvsn_cd != "02"` → continue) — 걸린 매도 주문은 복원하지 않는다 |
| `scheduler.py:3426-3437` | 15분 sync 도 보유 중인 종목은 `is_ticker_held_by_any` → continue — 수량을 고치지 않는다 |
| `scheduler.py:385` | `OrderEngine(self.registry)` = 프로세스 시작 — `_sell_notice_seen` 이 빈 채로 시작한다 |
| `scheduler.py:1008` → `:3629` | 21:30 정산 뒤 `order_engine.reset_daily_state()` — 원장을 비운다 |

**판정** — 부팅은 복원 수량을 KIS 에 맞추지 **않는다**. 복원 수량은 「직전 프로세스가 마지막으로 저장한 값」이라 ① `save_position` 실패(N3b — 메모리 4 · DB 7) ② 다운타임 동안의 체결(통보가 오지 않는다) 만큼 KIS 와 다를 수 있다. 그러니 「원장 시작 전 주문의 체결 = 복원 수량에 반영됐다」고 원장을 **시드하는 것은 틀린 전제**다. 지시의 두 번째 갈래 — **원장 시작 전 주문을 pending 에서 뺀다** — 를 택한다. 빼면 그 주문들로 설명되는 차이가 사라지고 분기가 B7 의 「보유 대 추적」 비교로 돌아간다(N3: `held 4 < 추적 5` → 재대조 → 4 발사). **부팅 쪽 변경은 필요 없다** — 아래 규칙이 `boot_manager.py`·`scheduler.py` 무접촉으로 K1 을 닫는다(R3-1-7 측정).

#### R3-1-2. 원장 시작 시각 `_sell_ledger_since`

| 자리 | 코드 |
|---|---|
| `__init__` — `:436` `self._manual_sell_orders` 뒤 | `self._sell_ledger_since: datetime = datetime.now(_KST_TZ)` |
| `reset_daily_state()` — `:3624` `self._selling_locked_wait.clear()` 뒤 | `self._sell_ledger_since = datetime.now(_KST_TZ)` |

- 뜻 = 「`_sell_notice_seen` 은 이 시각 **뒤** 에 처리한 매도 통보를 빠짐없이 담는다」. 21:30 뒤 비우면 그날 21:30 전 주문은 전부 「앞」, 다음 날 주문은 전부 「뒤」가 된다.
- 🔴 **벽시계 게이트가 아니다** — 기록된 두 시각(원장 시작 vs 그 주문의 접수 시각)을 비교할 뿐, 지금이 몇 시냐로 판정이 갈리지 않는다(부록 R2-11 이 거부한 「08:00 미시드 게이트」와 다르다 · 메모리 `feedback_wall_clock_gate_breaks_ci`). 테스트는 이 값을 **고정 대입**한다(R3-7).

#### R3-1-3. 분류 파서 (모듈 수준 · 동기 · never-raise) — `_sell_fills_by_order` 뒤(`:338` 뒤, `SELL_MAX_RETRIES` `:341` 앞)

```python
def _ord_datetime(ord_dt, ord_tmd) -> "datetime | None":
    """TTTC0081R `ord_dt`(YYYYMMDD) + `ord_tmd`(HHMMSS) → KST datetime. 못 읽으면 None."""
    try:
        d = str(ord_dt).strip() if ord_dt is not None else ""
        s = str(ord_tmd).strip() if ord_tmd is not None else ""
        if len(d) != 8 or not d.isdigit() or len(s) != 6 or not s.isdigit():
            return None
        return datetime(int(d[0:4]), int(d[4:6]), int(d[6:8]),
                        int(s[0:2]), int(s[2:4]), int(s[4:6]), tzinfo=_KST_TZ)
    except Exception:
        return None


def _sell_orders_placed_before(rows, ticker: str, since) -> "frozenset[str]":
    """부록 R3 K1 — 이 종목 매도 주문 중 원장 시작(`since`) **전에** 접수된 것(정규화 주문번호).
    한 주문의 행이 전부 읽히고 그 **가장 늦은** 접수 시각이 `since` 앞일 때만 넣는다.
    하나라도 못 읽으면 넣지 않는다(= pending 에 센다 — 덜 쏘는 쪽). 예외 = 빈 집합."""
    try:
        latest: dict = {}
        bad: set = set()
        for row in rows:
            if str(row.get("pdno", "")).strip() != ticker:
                continue
            if str(row.get("sll_buy_dvsn_cd", "")).strip() != "01":
                continue
            k = _odno_key(str(row.get("odno", "")).strip())
            dt = _ord_datetime(row.get("ord_dt"), row.get("ord_tmd"))
            if dt is None:
                bad.add(k)
                continue
            if k not in latest or dt > latest[k]:
                latest[k] = dt
        return frozenset(k for k, v in latest.items() if k not in bad and v < since)
    except Exception:
        return frozenset()
```
- 근거: 정본 `docs/kis/domestic-stock-order.md:3907`(`ord_dt` 필수 · 8) · `:3918`(`ord_tmd` 필수 · 6). 선례 `buying_reconcile.py:114` `_parse_ord_tmd`(KST · SOR 여러 행은 가장 늦은 값). 여기서는 `ord_dt` 를 행에서 읽어 벽시계의 「오늘」에 기대지 않는다.
- `since` 와 **같은** 시각은 「앞」이 아니다(`<`). 정정 주문은 새 주문번호·새 접수 시각을 갖고 체결도 그 번호로 온다 — 원주문의 재시작 전 체결은 원주문 번호에 남아 「앞」으로 빠진다.
- 🔴 실패 방향 = **못 읽으면 「뒤」**(pending 에 센다). 접수 시각 없이 재시작 전 체결(N3)과 재시작 뒤 통보 대기(N3c)는 같은 모양이고, 뒤쪽에서 쏘면 운영자 몫을 판다(R3-1-6).

#### R3-1-4. 조회 헬퍼 · pending · 호출부

| 자리 | 지금 | 바꾼 뒤 |
|---|---|---|
| `_sell_orders_snapshot`(`:3228`) 반환형 | `tuple[dict \| None, str]` | `tuple[dict \| None, str, frozenset]` — 실패 넷(`timeout`·`error`·`page_full`·`bad_row`) 셋째 = `frozenset()`, 정상 = `(fills, "ok", _sell_orders_placed_before(rows, ticker, self._sell_ledger_since))`. 유일한 await = `wait_for` 무변경(AR2-6) |
| `_sell_pending_dec`(`:3247`) | `(self, fills)` | `(self, fills, pre)` — `sum(max(0, f - seen.get(o, 0) - credit.get(o, 0)) for o, f in fills.items() if o not in pre)`. 🔴 `max(0, …)` 는 **주문별**(K4 — 표가 통보보다 늦은 주문의 음수가 다른 주문의 대기분을 지우면 운영자 몫을 판다, TK7) |
| `execute_sell` `:2042` | `fills, _reason = await …` | `fills, _reason, _pre = await self._sell_orders_snapshot(ticker)` |
| `execute_sell` `:2049` | `self._sell_pending_dec(fills)` | `self._sell_pending_dec(fills, _pre)` |

- 🔴 **크레딧(재대조)은 원장 시작 전 주문도 센다** — pending 에서만 뺀다. 크레딧에서도 빼면 t1 잔고에 이미 빠졌는데 통보가 아직인 재시작 뒤 체결이 두 번 빠진다(과소 추적 — 돌연변이 MK18 이 TK4·TK4b 에서 죽는다). 대신 R3-1-5 상한.
- 동일성 재검증(`:2043`)·eff·분기 술어 `held_qty >= eff`(`:2051`)·`fire` 식(`:2053`)은 **무변경**.

#### R3-1-5. 원장 시작 전 주문의 재대조 크레딧 상한 (K1 에 딸린 최소 규칙)

**왜** — 빼기(R3-1-4)가 재시작 뒤 경로를 F-3 에서 **재대조**로 돌린다. 재대조의 크레딧 `fills − seen` 은 원장이 모르는 재시작 전 체결(복원 수량에 이미 들어갔고 통보는 다시 오지 않는다)까지 크레딧으로 적어, 그 주문이 **계속 체결되면** 새 통보를 삼킨다 → 과대 추적(부록 R2-11 ②). 상한 없이(시제품 V1) 원장 재시작 M0 `H6` 1 > B7 0(seed 1341, 끝에 유령 1) — 상한을 두면 0.

**규칙** — `:2073` `target_qty` 뒤 · `:2076` `if fills is not None:` 블록을 이렇게(동기, 동일성 재검증 뒤라 await 0 — AR2-5 그대로):
```python
                        _credit_orders = 0
                        _credit_qty = 0
                        _pre_orders = 0
                        _pre_cap = 0
                        if fills is not None:
                            # 부록 R3 K1 — 원장 시작 뒤 주문 = 정확한 크레딧(부록 R-1-3 ⑥ 그대로).
                            # 원장 시작 전 주문 = 「이번 재대조가 내리는 폭 + 남은 크레딧 − 뒤 주문
                            # 크레딧」 을 넘지 않게. 남은 크레딧은 덮어쓰기 **전에** 센다.
                            _old_credit = sum(
                                self._sell_reflected_credit.get(_o, 0) for _o in fills
                            ) + self._sell_blind_credit.get(ticker, 0)
                            _post_credit = 0
                            for _o, _filled in fills.items():
                                if _o in _pre:
                                    continue
                                _c = _filled - self._sell_notice_seen.get(_o, 0)
                                if _c > 0:
                                    self._sell_reflected_credit[_o] = _c
                                    _credit_orders += 1
                                    _credit_qty += _c
                                    _post_credit += _c
                                else:
                                    self._sell_reflected_credit.pop(_o, None)
                            _pre_cap = max(
                                0, pos.quantity - target_qty - _post_credit + _old_credit
                            )
                            for _o, _filled in fills.items():
                                if _o not in _pre:
                                    continue
                                _pre_orders += 1
                                _c = min(_filled - self._sell_notice_seen.get(_o, 0), _pre_cap)
                                if _c > 0:
                                    self._sell_reflected_credit[_o] = _c
                                    _credit_orders += 1
                                    _credit_qty += _c
                                else:
                                    self._sell_reflected_credit.pop(_o, None)
                            self._sell_blind_credit.pop(ticker, None)
                            _credit_src = "orders"
                        else:
                            ...                     # 종목 크레딧(누적 — R2-7) 무변경
```
`[sell_qty_reconciled]`(`:2099-2106`) 문구 끝에 ` pre_orders=%d pre_cap=%d`(인자 `_pre_orders, _pre_cap`) — prefix 불변.

**증명 (과소 추적 0)** — 계산 시점(await 뒤 · 대입 전)에 P = 추적, H = t1 계좌 보유, S = H 속 운영자 몫(≥0), K = 덮어쓰기 전 남은 크레딧 합(주문별 + 종목), U_o = t1 까지 체결됐는데 아직 통보 안 된 수량, X = t1 뒤 체결인데 계산 전에 통보가 처리된 수량, Y = 뒤 주문의 (t1, t2] 체결로 아직 통보 전인 수량, E = 직전까지의 과대 추적(≥0 — R-INV-1 이 지켜 왔다), R = U 중 앞선 재대조가 이미 H 로 대입해 크레딧으로 들고 있는 몫(≤ K).
1. 장부식: P = (H − S) + U − R + E − X → U_pre = (P − H) − U_post + R − E + X + S ≤ (P − H) − U_post + K + X + S.
2. 뒤 주문 크레딧 C_post = Σ(fills − seen) ≥ U_post(부록 R-1-6) 이고 초과분은 Y. 상한 cap = max(0, P − H − C_post + K) 이면 U_pre ≤ cap + S + X + Y.
3. 앞 주문 o 의 크레딧 c_o = min(raw_o, cap) ≥ min(U_o, cap) — 두 번 빠지는 양 D = Σ_pre max(0, U_o − c_o) ≤ Σ_pre max(0, U_o − cap) ≤ max(0, U_pre − cap) ≤ S + X + Y.
4. 통보가 다 온 뒤 추적 = H − D, 전략 참값 = H − S − X − Y(Y 는 뒤 주문 크레딧이 삼키므로 추적에서 안 빠진다) → **추적 − 참값 = S + X + Y − D ≥ 0**. ∎
- 크레딧은 주문마다 cap 까지라 합이 참값을 넘을 수 있다 — 넘는 것은 과대 추적(허용, 다음 APBK0400 재대조가 회수)이고, 부록 R2-11 ② 의 크기를 「앞 주문 원체결 전부」에서 「재대조 폭」으로 줄인다.
- **남은 크레딧을 더하는 이유**(seed 5222 · TK4b) — 한 `execute_sell` 안의 두 번째 재대조에서 P 는 첫 재대조가 이미 H₁ 로 내려 놓은 값이다. 첫 재대조 크레딧(아직 안 온 통보 3)을 빼먹으면 상한이 2 로 작아져 뒤 통보 3 중 1 이 두 번 빠진다(시제품 첫 판: 정산점 추적 2 < 계좌 5). `_old_credit` 은 반드시 첫 덮어쓰기 **앞**에서 센다(MK21).

#### R3-1-6. 걸린 것 없는 보류 — 「never freeze with nothing resting」 과의 관계 (**결정 요청**)

- 빼기 뒤 걸린 매도가 없을 때(`held == sellable`) F-3 보류가 나는 조건은 **하나**다: `fire = eff ≤ 0` ⇔ **원장 시작 뒤** 접수된 주문의 미통보 체결 ≥ 추적. 거래소 기록으로는 전략 몫이 이미 다 팔렸고, 계좌에 남은 것은 운영자 몫이다(외부 매도는 전략 몫부터 판다 — 부록 R-2-2 의 보수 해석).
- **규칙** — `:2063-2071` 보류 로그를 걸림 여부로 가른다(동작은 R2 그대로: `_selling_locked_wait.add` → return):
```python
                            if held_qty > sellable:
                                logger.warning("[sell_qty_partial_locked] … 기존 문구 그대로 …")
                            else:
                                logger.warning(
                                    "[sell_qty_unnoticed_fills] ticker=%s strategy=%s held=%d "
                                    "sellable=%d positions=%d pending=%d eff=%d — 걸린 매도 없음, "
                                    "거래소가 확인한 미통보 체결이 추적 전부를 덮는다 — 발사 없이 "
                                    "통보 대기(종료 통보·보유 닫힘·selling_reconcile 이 푼다)",
                                    ticker, strategy_id, held_qty, sellable, pos.quantity,
                                    pending or 0, eff,
                                )
                            self._selling_locked_wait.add(ticker)
                            return
```
  「외부 부분 매도주문 잠김」은 `held == sellable` 에서 **절대 뜨지 않는다**(TK3 · MK8). 조회 실패(`fills is None`)로는 이 갈래에 올 수 없다(`held ≥ pos` 와 `sellable < pos` 가 `held == sellable` 에서 모순).
- **풀리는 길** — 통보가 오면 보유가 0 이 되어 닫힘 해제(R2-5), 또는 그 주문의 종료가 해제(R2-2). 통보가 유실되면 `selling_reconcile`(보유 > 0 · 열린 매도 0 · 180초). 운영자 몫은 그 사이 안 팔린다.
- **증거** — TK3(N3c): 추적 5 · 계좌 4 · 원장 뒤 MTS-X 5 체결(통보 대기) → B7 발사 `[5, 4]`(운영자 4주 매도) · R3 `[5]` 보류 → 통보 5 → 닫힘 · `_selling` 해제 · 계좌 4 보존.
- **충돌** — 문자 그대로 「걸린 것 없으면 절대 동결하지 않는다」(시제품 V2 = 걸린 것 없고 `eff ≤ 0` 이면 재대조로)는 재시작 없음 M4 `GT_INV2` **36/36/25 > B7 35/34/30** — 수용 기준(운영자 몫 ≤ B7)을 못 맞춘다. 원장 재시작 M4 도 29/34/31(1.0 이 B7 26 초과). 두 요구가 이 한 점에서 부딪힌다 → **도메인 권고 = 보류 유지(위 규칙)**. 메인 세션이 문자 그대로를 고르면 V2(돌연변이 MK9 모양)이고 비용은 위 수치다.
- **원문 N3/N3b(scratch `c385r2m/test_adv_r2.py`)** 는 TTTC0081R 행에 접수 시각이 없어 재시작 전(N3)과 재시작 뒤 통보 대기(N3c)를 가를 수 없다 — 두 세계 중 하나는 반드시 틀린다. R3 에서 원문은 붉고(보류) 그것이 옳은 쪽이다. **수용은 시각을 실은 이식판**으로 잰다: 결정적 TK1(`[N3]`·`[N3b]`) · 적대 `c385r3k/ports/test_r3_ports.py::test_n3_port…`·`test_n3b_port…`.

#### R3-1-7. 측정 (시제품 V1c = R3, 400 시드 × payload 1.0/0.0/0.6)

재시작 모의 = 프로브 중간 한 번 `_sell_notice_seen` 을 비우고 `_sell_ledger_since` 을 그 순간(논리 시계)으로 — **실제 재시작이 하는 일 중 원장 부분**(지시판). TTTC0081R 행에 논리 시계 `ord_dt`/`ord_tmd` 를 싣는다(B7·R2 는 읽지 않는다). 재시작 없음 판은 원 프로브와 수치가 **완전히 같다**(WT M0 대조 diff 0).

**재시작 없음**
| 지표 | M0 B7 | M0 R3 | M2 B7(=M0) | M2 R3 | M4 B7 | M4 R2 | M4 R3 |
|---|---|---|---|---|---|---|---|
| 정산점 좀비·추적>0 | 4/4/8 | 3/2/2 | 4/4/8 | 3/2/2 | 6/3/5 | 1/1/2 | 1/1/1 |
| 최종 좀비 `H3` | 0/0/0 | 0/0/0 | 0/0/0 | 0/0/0 | 0/0/0 | 0/0/0 | 0/0/0 |
| 최종 과소 `GT_under` | 0/2/0 | 0/0/0 | 0/2/0 | 0/0/0 | 1/0/0 | 0/0/0 | 0/0/0 |
| 유실 `H2` | 0/2/0 | 0/0/0 | 0/2/0 | 0/0/0 | 0/0/0 | 0/0/0 | 0/0/0 |
| 정산점 과소 | 32/46/29 | 0/0/0 | 32/46/29 | 0/0/0 | (M4 뜻 없음) | | |
| 잔여 손절 `H6` | 0/0/0 | 0/0/0 | 0/0/0 | 0/0/0 | 0/0/0 | 0/0/0 | 0/0/0 |
| 운영자 몫 `GT_INV2` | 0/0/0 | 0/0/0 | 0/0/0 | 0/0/0 | 35/34/30 | 29/27/18 | 29/27/18 |

**원장 재시작(지시판)**
| 지표 | M0 B7 | M0 R3 | M2 B7(=M0) | M2 R3 | M4 B7 | M4 R2 | M4 R3 |
|---|---|---|---|---|---|---|---|
| 정산점 좀비·추적>0 | 6/5/10 | 1/0/3 | 6/5/10 | 1/0/3 | 2/1/2 | 3/1/0 | 2/1/0 |
| 최종 좀비 `H3` | 0/0/0 | 0/0/0 | 0/0/0 | 0/0/0 | 0/0/0 | 0/0/0 | 0/0/0 |
| 최종 과소 `GT_under` | 0/2/1 | 0/0/0 | 0/2/1 | 0/0/0 | 0/0/0 | 0/0/0 | 0/0/0 |
| 유실 `H2` | 0/2/1 | 0/0/0 | 0/2/1 | 0/0/0 | 0/0/0 | 0/0/0 | 0/0/0 |
| 정산점 과소 | 37/45/40 | 0/0/0 | 37/45/40 | 0/0/0 | (M4 뜻 없음) | | |
| 잔여 손절 `H6` | 0/0/0 | 0/0/0 | 0/0/0 | 0/0/0 | 0/0/0 | 0/0/0 | 0/0/0 |
| 운영자 몫 `GT_INV2` | 0/0/0 | 0/0/0 | 0/0/0 | 0/0/0 | 26/39/38 | 21/30/27 | 24/31/29 |

- 원장 재시작 M4 `GT_INV2` 는 R3 가 R2 보다 크다(24/31/29 vs 21/30/27) — R2 는 재시작 전 체결까지 pending 에 세어 **얼어서** 운영자 몫을 덜 팔았다(N3 의 동결이 우연히 막은 것). 빼기로 B7 의 판단으로 돌아가며 그 우연이 사라진다. B7(26/39/38) 이하다.
- 참고(수용 밖): M5(초과분 + 조회 실패)는 R2 와 **같은 값**(`GT_INV2` 36/42/30 vs B7 35/34/30 — 부록 R2-1 「B2 가 B7 을 넘는 칸」 2 그대로). 원장 재시작 M5 도 R2 와 같다.
- 참고(수용 밖·지시 밖): **완전 재시작 모의**(새 엔진 · 진행 중 코루틴·타이머 종료 · 전송 중 통보 유실 · 다운타임 체결 0~3 통보 유실 · 포지션은 DB 그림자에서 복원) — 모든 추적 트리가 B7 보다 `H6`·과대·최종 좀비(유령 보유 + `held_zero` 로 selling_reconcile 이 못 푸는 `_selling`)가 많다(M2 `H6` R3 16/14/16 · R2 16/14/16 · B7 8/12/12). 원인 둘 다 **기존 문서화 한계**: M2 = 종목 크레딧이 유실 통보를 싣는다(R-13-4 = N2), M0·M4 = 재시작으로 잃은 통보를 크레딧·동결이 모른다(R2-11 ②). 과소·유실은 **0**(전 모드), 운영자 몫은 B7 이하(M4 41/49/47 vs 44/52/54). R3 는 R2 대비 M0 `H6` 10/15/15 → 7/10/9 로 줄였다. 표 전부 = scratch `c385r3k/r3_tables.md`.

---

### R3-2. K2 — 재주문 거부는 APBK0400 만 「안 걸렸다」

#### R3-2-1. 결함 (N1)
`src/api/base.py::_request`(`:476`) 는 주문 POST 도 재시도 루프(`:489`)에 태운다 — 5xx(`:506-547`) · `httpx.RequestError`(`:548-574`, 타임아웃 10초). 앞 시도가 거래소에 **접수됐는데 응답만 잃고** 뒤 시도가 거부되면 `place_order` 는 `KisApiError` 를 던지지만 우리 재주문은 걸려 있다. H5(부록 R2-6)는 모든 `KisApiError` 를 「확정적으로 안 걸렸다」로 읽어 `_selling` 을 풀었고, 다음 틱 손절이 걸린 재주문 위에 또 나가 운영자 6주를 팔았다(N1 · 계좌 20 → 4).

#### R3-2-2. 규칙 — `_cancel_and_reorder` `:3558-3562`
```python
                _place_state = "sending"
                try:
                    result = await place_order(**place_kwargs)
                except KisApiError as _place_exc:
                    # 부록 R3 K2 — `_request` 는 주문 POST 도 전송 실패·5xx 에 재시도한다.
                    # APBK0400(수량 초과)만 「안 걸렸다」로 센다 — 나머지는 전송 중과 같다(유지).
                    if is_sell_qty_exceeded(_place_exc):
                        _place_state = "rejected"
                    raise
                _place_state = "accepted"
```
`is_sell_qty_exceeded` 는 이미 모듈 import(`:17-24`). G-295-C4(`place_order` 1개·값으로 받는다)·A4(재조회 ~ 발사 사이 await 0) 무변경. `finally` 판정식은 R3-3.

#### R3-2-3. 왜 APBK0400 만 안전한가 (증명) · 남는 틈
- 재주문 수량 R(= J-2 `same`/`shrunk` 면 `min(remaining, 추적 T)` ≤ T). 앞 시도 접수 + 뒤 시도 APBK0400 ⇒ 그 순간 `R > held − 다른걸림 − R`. 다음 틱 손절의 1차 발사 T 가 통과하려면 `T ≤ held − 다른걸림 − R < R` → `T < R` 이어야 하는데 R ≤ T 라 **통과하지 못한다** → APBK0400 → F-3 가 걸린 재주문(주문 조회에 실린다)을 빼고 계산 → 쌓이지 않는다(TK10 `physical`).
- 다른 거부 코드(EGW00201 초당 한도 등)는 이 부등식을 주지 않는다 → 풀면 다음 1차 발사가 통과할 수 있다(N1). 그래서 유지 — 그 `_selling` 은 우리 재주문이 걸려 있으면 그 종료가, 없으면 `selling_reconcile`(열린 매도 0 · 180초)이 푼다(TK9 · TK10 `EGW00201`).
- **남는 틈(기록)** — (가) 숨은 재주문이 다음 틱 **전에 부분 체결**돼 추적이 R 아래로 내려가면 위 부등식이 풀린다(필요: 앞 시도 접수·응답 유실 ∧ 뒤 시도 APBK0400 ∧ 부분 체결 f ≥ R + 다른걸림 − 운영자 초과분 ∧ 초과분 > 0). (나) `verdict=manual`·`ambiguous`·`error` 는 R 이 추적을 넘을 수 있다(부록 R-4 — 운영자 버튼 수량). 둘 다 LOW #3 모양(우리 주문이 `_selling` 없이 걸림)이다.

#### R3-2-4. manual 라우트 `_sent` — **같은 결함이 있다** → 같은 전제
- `routes/trading.py::manual_sell` 의 `place_order`(`src/api/order.py:25` → `kis_post` → `_request`)도 같은 재시도를 탄다. 지금 `except`(`:229-235`)는 `_sent` 가 거짓이면 무조건 되돌린다 → 앞 시도 접수 + 뒤 시도 예외에서 걸린 manual 주문 옆의 `_selling` 을 푼다.
- **규칙** — 함수 머리 import 묶음(`:151-158`)에 `from src.api.base import KisApiError` · `from src.api.balance import is_sell_qty_exceeded` 를 더하고 `:229-235` 를:
```python
    except Exception as e:
        # 🔴 cycle385 부록 R3 K2 — 「발사 안 됨」이 **확정된** 실패(APBK0400 수량 초과)만 되돌린다.
        # `_request` 는 주문 POST 도 전송 실패·5xx 에 재시도하므로 그 밖의 예외는 앞 시도가 접수됐을
        # 수 있다 — 표식을 두고 그 주문의 종료 통보 또는 `selling_reconcile` 에 맡긴다.
        # 발사 뒤(`_sent`) 실패는 되돌리지 않는다(루트 금기 「주문이 나간 뒤의 실패」).
        if _added and not _sent:
            if isinstance(e, KisApiError) and is_sell_qty_exceeded(e):
                engine._selling.discard(req.ticker)
                engine._selling_since.pop(req.ticker, None)
            else:
                logger.warning(
                    "[manual_sell_selling_kept] ticker=%s err=%s — 발사 여부를 확정할 수 없어 "
                    "_selling 유지(열린 주문이 없으면 selling_reconcile 이 푼다)",
                    req.ticker, e,
                )
        logger.error("수동 매도 실패: %s — %s", req.ticker, e)
        return ApiResponse(success=False, message=f"매도 주문 실패: {e}")
```
- docstring `:145-146` 「(발사 전 실패는 되돌리고, 발사 뒤는 그 주문의 종료 통보가 해제한다)」 → 「(발사되지 않은 것이 확정된 실패(APBK0400)만 되돌리고, 그 밖의 실패·발사 뒤는 그 주문의 종료 통보 또는 `selling_reconcile` 이 해제한다)」.
- **비용(기록 · 결정 메모)** — 같은 본문이면 앞 시도도 같은 이유로 거부됐을 **순서 무관 거부**(APBK3013 애프터 시장가 — 이 라우트 docstring `:141-143` 이 적은 알려진 별건 · APBK0918 장운영외)도 이제 「전송 중」이라 `_selling` 이 남는다 → 그 종목 자동 손절이 `selling_reconcile` 까지 멈춘다(15분 sync + 180초, **09:30 전에는 sync 가 돌지 않는다**). 이 코드들을 「안 걸렸다」에 넣을지는 지시(「APBK0400 만」) 밖이라 메인 세션 결정으로 둔다. 판독 = `[manual_sell_selling_kept]` 건수와 `err=` 코드(R3-12 F-R3-3).

#### R3-2-5. 부록 R2-6 출구 표 갱신
| 출구 | `_place_state` | `_selling` |
|---|---|---|
| 재주문 `KisApiError` · `is_sell_qty_exceeded` 참 | rejected | **해제**(주인 또는 동결 — R3-3) |
| 재주문 `KisApiError` · 그 밖의 코드 | **sending** | **유지**(신규 — K2) |
| 그 밖의 행 | 무변경 | 무변경 |
`[reorder_selling_released] place=rejected` 의 뜻이 「APBK0400 로 거부됐다」로 좁아진다.

---

### R3-3. K3 — 동결이면 손님 manual 의 재주문 거부도 푼다

- `_cancel_and_reorder` `finally`(`:3580-3584`) 판정식:
```python
            if (
                _cancel_ok and _place_state in ("none", "rejected")
                and ticker in self._selling
                and (
                    ticker in self._selling_locked_wait
                    or self._manual_sell_orders.get(order_no, True)
                )
            ):
```
- 진리표: 해제 ⇔ 취소 성공 ∧ (none ∨ rejected) ∧ `ticker ∈ _selling` ∧ (동결 표식 ∨ 주인). 주인 = 자동 주문(표식 없음 → 참) · manual `_added` 참.
- **왜 안전한가** — 동결 표식은 「지금 `_selling` 은 우리 `execute_sell` 이 **주문 없이** 멈춰 세운 것」이다(부록 R2-5). 새 주인이 서면 진입에서 지운다(`execute_sell` `:1678` · 라우트 `_added` 분기). 손님 manual 은 `_added` 거짓이라 표식을 지우지 않는다 → 표식이 서 있으면 `_selling` 의 주인은 아무것도 걸지 않은 동결이고, 원주문은 방금 취소됐고, 재주문은 APBK0400 으로 확정 거부됐다(K2) → 우리 것이 아무것도 없다. h4h5(동결 → 운영자가 앱에서 MTS-9 취소(통보 없음) → 손님 manual 3 → 1 체결 → 재주문 거부) 에서 R2 는 걸린 것이 하나도 없는데 `_selling` 을 `selling_reconcile`(15분 sync + 180초, 09:30 전에는 돌지 않는다)까지 남겼다.
- 표식이 없는 손님 manual 은 **여전히 유지**(TQ15 무변경 — 자동 손절 S1 이 걸려 있다).
- 다른 손님 manual 이 따로 걸려 있으면 풀린 뒤 다음 손절이 APBK0400 → F-3 가 그 주문을 빼고 계산한다 — 「동결은 어느 주문의 종료로든 풀린다」(R2-4)와 같은 성질.

---

### R3-4. K4 — 주문별 `max(0, …)` 고정

- TK6(단위): `seen={"1": 5}` · `fills={"1": 3, "2": 4, "3": 6}` · `pre={"3"}` → `_sell_pending_dec == 4`(합 뒤 clamp 면 2) · `pre=∅` → 10.
- TK7(행위 — XF3c 킬러): 추적 5 · 계좌 5 · MTS-A 표 3(통보는 5 처리 — 표 지연) · MTS-B 4 체결(통보 대기) · MTS-C 2 걸림 → 참 전략 몫 1(= 5 − 4), 그 1 도 C 에 잠김 → 발사 `[5]` 뿐. 합 뒤 clamp 면 pending 2 → eff 3 → fire 1 → 운영자 1주 매도.
- AST(AR3-3): `_sell_pending_dec` 반환 = `sum(<생성식>)` 이고 생성식 원소가 `max(0, …)` 호출(바깥 `max(0, sum(…))` 아님).

---

### R3-5. K5 — 테스트 위생

| 자리 | 지금 | 바꾼 뒤 |
|---|---|---|
| `tests/unit/engine/test_cycle385r_partial_locked_sell.py::test_tr18_…`(strict xfail) | `[selling_kept] reason=unrelated_end` 단언(AR2-2 가 금지한 마커 — LOW #3 이 고쳐져도 마커가 없어 영원히 xfail) | 마커 단언·`caplog` 삭제. 남는 단언 = 반환 뒤 추적 7 · `TICKER in _selling` · 곧바로 다시 들어온 손절 발사 수 불변(1) · 우리 10 체결(map) → 닫힘 · `_selling` 해제. docstring 에서 마커 서술 삭제 |
| `tests/unit/routes/test_cycle385_manual_sell_selling.py::test_tr20_…`(strict xfail) | `[selling_kept] reason=guest_manual` 단언 | 마커 단언·`caplog` 삭제. 남는 단언 = 손님 표식 `False` · 손님 종료 뒤 `TICKER in _selling` · S1 종료 → 해제 |
| `tests/unit/engine/test_cycle236_sell_qty_exceeded.py:282-283` 주석 | 「cycle385 부록 R-3 — 이 동결이 기다리는 것은 「걸린 주문의 끝」 이다. 표식이 있어야 매핑 없는 그 외부 종료가 `_selling` 을 푼다(무관한 종료는 못 푼다).」 | 「cycle385 부록 R2-5 · R3 K3 — 동결 표식 = 우리 `execute_sell` 이 주문 없이 멈춰 세운 `_selling` 이라는 표시. 주문 종료는 표식과 무관하게 `_selling` 을 풀고(R2-2), 표식은 지키던 보유가 닫힐 때(R2-5)와 원주문 취소 뒤 재주문이 안 걸렸을 때(R3 K3 — 손님 manual 포함) 푸는 근거다.」 |
| `tools/test_impact/manual_overrides.yaml:191` 주석 | 「AST 가드(A8·AR7·AR8)」 | 「AST 가드(A8·AR8·AR2-2·AR3-7)」 — AR7 은 부록 R2 가 지웠다 |

- 실측(시제품): 새 TR18·TR20 은 R3 트리에서 **XFAIL**, 부록 R 의 주인 규칙 트리(scratch `c385r/ref`)에서 **XPASS(strict) = 붉음** — LOW #3 이 고쳐지면 뒤집히는 신호가 산다.

---

### R3-6. 마커 (신규·변경)

| 마커 | 레벨 | cap | 필드 | 뜻 · 판독 |
|---|---|---|---|---|
| `[sell_qty_unnoticed_fills]` (신규) | WARNING | 없음(드묾) | `ticker= strategy= held= sellable= positions= pending= eff=` | 걸린 매도 없이 보류 — 원장 시작 뒤 주문의 미통보 체결이 추적 전부를 덮는다. 통보가 오면 풀린다. 같은 종목에서 15분마다 반복되면 **통보 유실 유령**(R3-13-5) |
| `[sell_qty_partial_locked]` (변경) | WARNING | 없음 | 무변경 | 이제 `held > sellable`(무엇이 걸려 있을 때)에서만 뜬다 |
| `[sell_qty_reconciled]` (변경) | WARNING | 없음 | 기존 + `pre_orders= pre_cap=` | `pre_orders>0` = 재시작 전 접수 주문이 재대조에 섞였다(상한 적용) |
| `[manual_sell_selling_kept]` (신규, `src.routes.trading`) | WARNING | 없음(드묾) | `ticker= err=` | manual 발사 실패가 APBK0400 이 아니라 표식을 남겼다 → `selling_reconcile` 까지 그 종목 손절 정지 |
| `[reorder_selling_released]` (뜻 변경) | WARNING | 없음 | 무변경 | `place=rejected` = **APBK0400** 거부 |

전부 `logger.*` 만(새 `write_log`·DB 0), 행위 밖. 신규 `KstDailyEmitCap` 0.

---

### R3-7. 테스트 (Red 먼저)

하네스 = `tests/unit/engine/test_cycle385r2_round2.py` 의 `_Acct`·`_env`·`_reorder_env`·`_reorder_place`·`_await_sell_timer`·`_apbk0400`·`drain` + `test_cycle385_b7_partial_sell.py` 의 `_sell_notice`·`_map_order`·`_held`·`_warn_lines`. 새 파일 안에 `_install_acct_t(monkeypatch, env, acct, times, *, before_place=None, missing=False)` — R2 `_install_acct` 와 같고 TTTC0081R 행에 `ord_dt="20260928"`·`ord_tmd=times.get(odno, POST)` 를 싣고(`missing` 이면 두 키를 뺀다) `env.engine._sell_ledger_since = SINCE`(2026-09-28 12:00 KST) 로 **고정**한다. `PRE="100000"` · `POST="123000"`. 🔴 벽시계 금지 — 원장 시작·행 시각은 전부 상수. caplog 는 WARNING 이상 + prefix. 시제품 = scratch `c385r3k/red/*.py`(엔진 파일: R3 트리 16 통과 + 1 xfail · 현재 워크트리 14 붉음 / 라우트: R3 4 통과 · 워크트리 3 붉음). 시제품 이름 대응: TK6 = `test_tk6_tk7_pending_excludes_pre_and_clamps_per_order` · TK7 = `test_tk7b_lagging_row_does_not_cancel_other_orders_pending`.

**새 파일 `tests/unit/engine/test_cycle385r3_round3.py`**
| ID | 무엇 | 입력 | 기대 |
|---|---|---|---|
| TK1 `[N3]`·`[N3b]` | K1 · N3/N3b 이식 | 추적 5 / 7 · 계좌 4 · 행 MTS-X tot 6 `PRE` · 걸린 것 없음 | 발사 `[5, 4]` / `[7, 4]` · `[sell_qty_reconciled]` 1 · `[sell_qty_partial_locked]`·`[sell_qty_unnoticed_fills]` 0 · 우리 체결 → 닫힘 · `_selling` 비움 |
| TK3 `[post]`·`[missing]` | 걸린 것 없는 보류(N3c) · 못 읽는 시각 = 뒤 | 추적 5 · 계좌 4 · MTS-X tot 5 `POST`(또는 시각 키 없음) | 발사 `[5]` · `[sell_qty_unnoticed_fills]` 1행(`pending=5`·`eff=0`) · 「잠김」 0 · `_selling`·동결 표식 섬 · MTS-X 통보 5 → 닫힘 · 둘 다 비움 · 계좌 4 |
| TK4 | 크레딧 상한(N3d) | 추적 6 · 계좌 4 · MTS-Y tot 6 `PRE`(재시작 전 4 + 뒤 2 통보 대기) · 잔량 3 걸림 | `_sell_reflected_credit == {"MTS-Y": 2}` · Y 통보 2 · 우리 체결 · Y 3 체결·통보 — 매 단계 추적 ≥ 계좌 · 끝 `(0, 0)` |
| TK4b | 남은 크레딧 더하기(seed 5222) | 추적 10 · 계좌 10 · MTS-A 8 걸림 `PRE` · A 3 체결(대기) · 두 번째 발사 직전 A 2 더 | 크레딧 A == 5 · A 통보 3·2 뒤 추적 == 계좌 == 5 |
| TK5 | 파서 | R3-1-3 행 묶음(앞·뒤·같은 시각·시각 없음·못 읽음·SOR 앞+뒤·SOR 앞+앞·다른 종목·매수·전날·8자리 아닌 날짜·앞+못 읽음) | `== frozenset({"1", "7", "10"})` · `rows=None` → 빈 집합 · `since=None` → 빈 집합 |
| TK6 | K4 단위 | R3-4 | 4 · 10 |
| TK7 | K4 행위(XF3c) | R3-4 | 발사 `[5]` |
| TK8 | 원장 시작 시각 | 새 엔진 · `SINCE` 대입 뒤 `reset_daily_state()` | 초기값 tz-aware(+09:00) · 리셋 뒤 `SINCE` 아님 · +09:00 |
| TK9 `[EGW00201]`·`[APBK0918]`·`[APBK3013]` | K2 | 자동 S1 10(매핑, `_selling`) · 통보 4 → 타이머 → 취소 성공 → 재주문 그 코드로 거부 | `_selling` 유지 · `[reorder_selling_released]` 0 |
| TK10 `[EGW00201-20]`·`[physical-13]` | K2 · N1 이식 | 계좌 20 / 13 · 추적 10 · 우리 10 → 4 체결 → 타이머 → 재주문 시도 1 접수(응답 유실) + 시도 2 = EGW00201 / 계좌가 판정(APBK0400) | EGW: `_selling` 유지 · 다음 손절 중복 차단 · 끝 계좌 10 / physical: `_selling` 해제 · 이어진 손절 3틱 뒤 계좌 3 · 둘 다 추적 닫힘(운영자 몫 보존) |
| TK12 | K3 · h4h5 이식 | 계좌 10 · MTS-9 10 걸림 → `[sell_qty_locked]` 동결 → MTS-9 앱 취소(통보 없음) → 손님 MAN-1 3(`False`) → 1 체결 → 타이머 → 취소 → 재주문 APBK0400 | 걸린 것 없음 · `_selling`·동결 표식 비움 · `[reorder_selling_released] place=rejected` 1 |
| TK13 | N2(문서화된 한계) | 추적 12 · 계좌 10 · 조회 늘 실패 · 전량 매도 뒤 운영자가 5 매수 → 손절 | 🔴 `xfail(strict=True, reason="부록 R-13-4 · R3 유지 — N2")` · 단언 = 유령 없음 · 계좌 5 |

**`tests/unit/routes/test_cycle385_manual_sell_selling.py`**(기존 `env` 픽스처)
| ID | 입력 | 기대 |
|---|---|---|
| TK11a | `place_order` 가 `KisApiError(APBK0400)` | `_selling`·`_selling_since` 비움 · `[manual_sell_selling_kept]` 0 |
| TK11b `[runtime]`·`[egw00201]`·`[apbk3013]` | `RuntimeError` / `KisApiError(EGW00201)` / `KisApiError(APBK3013)` | `success=False` · `_selling`·`_selling_since` **유지** · `src.routes.trading` WARNING `[manual_sell_selling_kept]` 1행(`ticker=005930`) |

**기존 테스트 기대값 변경(사유 동반)**
| 테스트 | 지금 | 바꾼 뒤 | 사유 |
|---|---|---|---|
| `test_cycle385_manual_sell_selling.py::test_t28_send_failure_rolls_back_selling_it_added` | `RuntimeError` → `_selling` 되돌림 | **TK11a·TK11b 로 교체**(삭제 아님 — 같은 자리) | K2 — 발사 안 됨이 확정된 실패만 되돌린다 |
| 같은 파일 T28b · T28c | 현행 | 무변경 | `_added` 거짓 · 발사 뒤는 원래 유지 |
| `test_cycle385r2_round2.py::test_tq6_post_restart_f3_never_overfires` | 시각 없는 행 · docstring 「원장이 비면 pending 이 재시작 전 체결까지 세어 … 동결」 | 파라미터 `rows_time ∈ {None, "pre"}` 추가 — `None` 은 현행(발사 뒤 ≤ 2, 실측 보류) · `"pre"` 는 `_install_acct_t` 로 MTS-X `PRE` → **발사 `[10, 2]`**(초과분 0/5 둘 다). docstring 을 「시각이 있으면 재시작 전 주문은 pending 에서 빠지고 F-3 가 전략 몫 − 걸림 = 2 를 판다(R3-1), 시각이 없으면 뒤로 읽어 보류한다」로 | K1 |
| TR18 · TR20 | 마커 단언 | R3-5 | K5 |

---

### R3-8. AST 가드 (`tests/unit/ast/test_cycle385_ast_b7.py`)

| ID | 단언 | 부록 R2 대비 |
|---|---|---|
| AR2-3 (개정) | `place_order` 를 감싼 Try 에 `except KisApiError as <n>:` · 본문 = `[If(test=is_sell_qty_exceeded(<n>), body=[_place_state = "rejected"], orelse=[]), Raise()]`. `finally` 해제 If 테스트를 `_cancel_ok`·`_place_state`·`ticker`·`order_no`·`self` 로 평가해 진리표 = `ok ∧ state∈{none, rejected} ∧ (frozen ∨ owner)`(`self` 에 `_selling_locked_wait` 추가, frozen ∈ {참, 거짓} 차원) | 핸들러 본문·진리표 개정 |
| AR3-1 | `__init__` 에 `self._sell_ledger_since = datetime.now(_KST_TZ)`(주석 대입 허용) 1 · `reset_daily_state` 에 같은 대입 1 | 신규 |
| AR3-2 | `_sell_orders_snapshot` 의 모든 `Return` 값이 3-튜플 · 셋째가 실패 넷에서 `frozenset()` · 정상에서 `_sell_orders_placed_before(rows, ticker, self._sell_ledger_since)` 호출 | 신규 |
| AR3-3 | `_sell_pending_dec(self, fills, pre)` · 반환 = `sum(GeneratorExp)` · 원소 = `max(0, …)` · 생성식 조건 = `o not in pre` | 신규(K4 구조판) |
| AR3-4 | `_ord_datetime`·`_sell_orders_placed_before` = 모듈 수준 동기 def · Await 0 · 최상위 `Try(except Exception)` | AR10 목록에 둘 추가 |
| AR3-5 | `execute_sell`: 조회 대입 대상 = `fills, _reason, _pre` · `self._sell_pending_dec(fills, _pre)` 1 · 재대조 블록에서 `_old_credit` 대입이 첫 `self._sell_reflected_credit[...] =` 저장보다 앞 · `_pre_cap` 우변에 `pos.quantity - target_qty - _post_credit + _old_credit` · `min(…, _pre_cap)` 은 `_o not in _pre` 로 거른 루프 안에만 | 신규 |
| AR3-6 | F-3 If(`held_qty >= eff`) 본문의 보류 경로: `If(held_qty > sellable)` 본문에 `[sell_qty_partial_locked]` 문자열 · orelse 에 `[sell_qty_unnoticed_fills]` · 그 뒤 `_selling_locked_wait.add` → `return`. `execute_sell` 안 `[sell_qty_partial_locked]` 문자열은 그 If 본문에만 | 신규 |
| AR3-7 | `routes/trading.py::manual_sell` except 핸들러: `_selling.discard(req.ticker)` 가 `is_sell_qty_exceeded(e)` 호출을 테스트에 가진 If 안에 있고, 그 If 는 `_added`·`_sent` 를 읽는 If 안이다 · 문자열 `[manual_sell_selling_kept]` 1 | 신규 |
| AR11 (확장) | 기존 다섯 `clear()` + AR3-1 대입 | 확장 |

A1·A3·A3b·A4·A4b·A5*·A6·A7·A8·A9·A10·AR2·AR3·AR4b·AR5·AR8·AR9·AR12·AR13·AR2-1·AR2-2·AR2-4·AR2-5·AR2-6·AR2-7·AR2-8·G147-AST-1·g273_ast1~4·G-295-C4·test_g328_1/3b 는 **그대로 초록**이어야 한다(시제품 실측 — 새로 붉어진 AST 는 AR2-3 하나).

---

### R3-9. 돌연변이 계획 (21종 — 시제품에서 전부 죽음, 러너 `c385r3k/mut_r3.py` → `mut_r3_results.json`)

| # | 돌연변이 | 죽인 것(실측) |
|---|---|---|
| MK1 | pending 이 `pre` 를 안 거른다(K1 이전) | TK1×2 · TK4 · TK4b · TK6 |
| MK2 | SOR 여러 행에서 가장 **이른** 시각 | TK5 |
| MK3 | 못 읽는 시각 = 「앞」 | TK3`[missing]` · TK5 · TQ1 · TQ20`[ok]` 등 9 |
| MK4 | `v < since` → `v <= since` | TK5 |
| MK5 | `reset_daily_state` 가 원장 시작을 안 바꾼다 | TK8 |
| MK6 | 앞 주문 크레딧 상한 삭제 | TK4 |
| MK7 | 상한에서 `+ _old_credit` 삭제 | TK4b |
| MK8 | 보류 문구를 늘 「잠김」 | TK3×2 |
| MK9 | 걸린 것 없고 `eff ≤ 0` 이면 재대조(V2 — 문자 그대로 「절대 동결 안 함」) | TK3×2 |
| MK10 | 재주문 `KisApiError` 전부 rejected(K2 이전) | TK9×3 · TK10`[EGW]` |
| MK11 | rejected 를 아예 안 셈 | TQ12×2 · TK12 |
| MK12 | K3 삭제(주인만) | TK12 |
| MK13 | K3 을 동결 표식만으로(주인 삭제) | TQ12×2 · TQ14`[before_place]` |
| MK14 | 라우트: 발사 전 실패는 전부 되돌림(K2 이전) | TK11b×3 |
| MK15 | 라우트: 절대 안 되돌림 | TK11a |
| MK16 | pending 을 합 뒤 clamp(XF3c) | TK6 · TK7 |
| MK17 | 분류 기준을 벽시계 `datetime.now()` 로 | TK1×2 · TK4 · TK4b |
| MK18 | 앞 주문 크레딧 0(pending 처럼 크레딧에서도 뺀다) | TK4 · TK4b |
| MK19 | `__init__` 에서 원장 시작 대입 삭제 | TK8 · TQ1·TQ2·TQ4·TQ5·TQ6 등 30 |
| MK20 | 상한 무한대(`_pre_cap = 10**9`) | TK4 |
| MK21 | `_old_credit` 을 덮어쓴 **뒤** 센다(0 과 같다) | TK4b |

- 대상 파일 = R3 새 두 파일 + TR18·TR20 판 + `test_cycle385r2_round2` · `test_cycle385r_recount_credit` · `test_cycle385r_partial_locked_sell` · `test_cycle385_reorder_requery` · `test_cycle385_b7_partial_sell` · `test_cycle385_manual_sell_selling`(T28 제외) · `test_cycle236_sell_qty_exceeded`. 부록 R2 의 MQ1~MQ23 · 부록 R 의 MR1~MR21·MR27~MR32 · 본문 M1~M30 은 그대로 다시 돌린다 — 특히 MQ18(H5 를 `sending` 에도)은 K2 뒤에도 TQ13·TK9 가 죽여야 한다.
- 시제품 러너는 스크래치 전용 — 구현본에서 tester 가 같은 21종을 다시 적용한다.

---

### R3-10. 수용 측정 절차 (tester)

1. **적대 프로브** — `c385r2m/test_adv_money.py`(A1·A2·A3) · `test_adv_r1fix.py`(p1·rp 재기준판) · `test_adv_r2.py` 의 N1·N4 · `c385r3/h4h5/test_h4h5_residual.py` · `c385r2m/t/test_adv_t.py` 의 p2·p4a·p4b·p4c·p5 · **N3·N3b 는 이식판** `c385r3k/ports/test_r3_ports.py`(N3·N3b·N3c·N3d·N1 두 변형) — 시제품 전부 통과. 원문 N3·N3b 는 R3-1-6 이유로 붉은 것이 정상, N2 는 TK13 xfail(R-13-4), p3·p3b 는 LOW #3(TQ22 xfail), p1[ok]·rp[fail] 원문은 부록 R2-17 대로 재기준판이 기준.
2. **무작위 프로브** — `c385r3k/probe/test_probe_r3.py`(원 프로브 + 논리 시계 + 재시작 모의, `gen_probe.py` 로 원문에서 생성 · 재시작 없음 판은 원 프로브와 수치 동일). 러너 `c385r3k/run_matrix.sh`(`TLIST="B7 <구현 트리>" MLIST="M0 M2 M4 M5" RLIST="none ledger full"`) → `gate.py <구현> B7`. 기준 = 같은 모드·같은 재시작 판의 B7. **수용 = `none`·`ledger` 의 M0·M2·M4 목록 지표(정산점 좀비·최종 좀비·최종 과소·유실·정산점 과소(M4 제외)·H6·GT_INV2) ≤ B7.** M5·`full`·`GT_INV2c`·`oversell_*` 는 기록만(R3-1-7).
   - 🔴 재시작 모의는 `_sell_notice_seen` 을 비우는 것만으로는 **틀린 재시작**이다 — 실제 재시작은 새 엔진이라 `_sell_ledger_since` 도 그 순간이 된다. 원장만 비우고 시각을 두면 모든 주문이 「뒤」로 읽혀 N3 동결이 재현된다(R2 와 같은 결과). 프로브 행에는 `ord_dt`/`ord_tmd` 가 실려야 한다.
3. **결정적 테스트** — R3-7 전부 + 기존 cycle385 파일 전부 + 전체 스위트(메모리 `feedback_rerun_suite_after_edit`). 시제품 전체 스위트(`tests/unit`+`tests/contract`, 13,186 통과)에서 워크트리 사본 대비 새로 붉어진 것 = 8영역 sha 핀 7건(cycle274 · 276 `test_c6_4c` · 278 · 282 · 290 · 294 · 297 — 222a3·223·223f·226 은 스크래치에 git 이 없어 양쪽 다 원래 붉다) · cycle287 `_SRC_TREE_DIGEST` · AR2-3 · T28 — 전부 R3-7·R3-11 이 바꾸라고 적은 것.

---

### R3-11. 핀 · 문서

- `order_engine.py` whole-file sha **10곳**(현재 `235165aaa77b0e4cda9819334f10311e7d1595da0110452b5a29f7a580fae41b` — 착수 전 `grep -rl` 로 다시 센다: cycle222a3 · 223 · 223f · 226 · 274 · 278 · 282 · 290 · 294 · 297) 값만 재핀. cycle276 `test_c6_4c` 는 222a3 핀을 따라 초록이 된다. 사유 주석: `# 🔁 2026-09-28 (cycle385 부록 R3) 재핀 — 3차 검토 반영: 원장 시작 전 접수 주문은 pending 에서 빼고 그 재대조 크레딧에 상한(K1) · 걸린 것 없는 보류 문구 분리 · 재주문 거부는 APBK0400 만 해제(K2) · 동결이면 손님 manual 재주문 거부도 해제(K3). 사용자 승인(8영역), 나머지 7영역 diff 0.`
- `test_cycle287_ast_scope.py::_SRC_TREE_DIGEST` 값만 재핀(`routes/trading.py` — K2). 주석: `🔁 cycle385 부록 R3 재핀(값만, 파일 수 불변 162) — routes/trading.py manual_sell 발사 실패 되돌림을 APBK0400 으로 좁힘(K2). 직전 값 = <현재 값 앞 8자리>…`. `_BASE_SHA["src/api/balance.py"]` 무변경.
- **붉어지면 범위 밖**(재핀 금지, 되돌린다): `test_cycle295_ast_market_rest.py::_BYTE_IDENTICAL_PINS` · `_FROZEN_SEGMENTS` · `scheduler.py`(3,786줄) · `boot_manager.py` · `src/realtime/**` · `src/api/*` · `src/db/*`.
- `_workspace/test_index.yaml` 재생성. 새 테스트 파일은 정적 import 로 잡힌다(`manual_overrides.yaml` 등록 불요 — 부록 R2-22 와 같다). `manual_overrides.yaml:191` 주석만 R3-5.
- 문서 갱신 후보(`/sync-docs` → report-writer): `src/engine/CLAUDE.md`(원장 시작 시각 · 원장 시작 전 주문은 pending 제외 · 앞 주문 크레딧 상한 · `[sell_qty_unnoticed_fills]` · 재주문 거부 = APBK0400 · K3 해제 조건) · `src/routes/CLAUDE.md`(manual-sell 실패 되돌림 = APBK0400 만 · `[manual_sell_selling_kept]`) · history append.

---

### R3-12. 09-28 확인 추가 (§o · R-14 · R2-18 뒤)

| # | 무엇 | 어떻게 | 무엇이면 멈추나 |
|---|---|---|---|
| F-R3-1 | TTTC0081R 매도 행의 `ord_dt`·`ord_tmd` | 실전 `inquire-daily-ccld` 원문(KRX·NXT·SOR 각 1건)에서 두 필드가 8·6자리 숫자인가, SOR 부모·자식 행의 `ord_tmd` 가 같은가 | 비었거나 형식이 다르면 **배포 전 보고** — 전부 「뒤」로 읽혀 재시작 뒤 N3 동결이 되살아난다(돈은 안전 쪽) |
| F-R3-2 | 주문 시각의 시계 | 우리 주문의 REST 응답 `ORD_TMD`(= `OrderResult.order_time`) 와 같은 주문번호 TTTC0081R `ord_tmd` · EC2 `date` 차이 | 수 초 이상 어긋나면 기록 — 재시작 직전·직후 몇 초의 주문만 경계가 흐려진다 |
| F-R3-3 | manual 발사 실패 코드 | 30일 `system_logs` 「수동 매도 실패」 의 `msg_cd`(특히 APBK3013·APBK0918) 건수 | 정보용 — 배포 뒤 그 건수만큼 `[manual_sell_selling_kept]` 가 뜨고 손절이 `selling_reconcile` 까지 멈춘다(R3-2-4 비용) |

---

### R3-13. 반례 / 한계

1. **접수 시각을 못 읽는 행**은 「뒤」 — 그 주문이 재시작 전 것이면 N3 모양 보류가 돌아온다(KIS 가 필수 필드를 비울 때만 · F-R3-1).
2. **재시작 전 접수 주문이 재시작 뒤에도 체결 중이고 통보가 아직일 때** pending 에서 빠져 eff 가 그만큼 크다 → 운영자 초과분이 있으면 F-3 가 그만큼 더 쏜다. 원장 재시작 M4 `GT_INV2` 24/31/29(R2 21/30/27 · B7 26/39/38).
3. **다운타임 체결**(프로세스가 죽은 동안 재시작 전 주문의 체결 — 통보 없음)은 복원 수량에 없다 → 초과분이 없으면 APBK0400 재대조가 고치고, 초과분 ≥ 그 양이면 첫 발사가 통과해 운영자 몫을 판다 — **모든 트리 공통**(B7·HEAD 포함).
4. **앞 주문 크레딧 상한은 주문마다** — 합은 참값을 넘을 수 있다(과대 추적, 부록 R2-11 ② 의 크기만 줄였다).
5. **통보 유실 유령**(원장 뒤 주문의 체결 통보를 잃음, 초과분 있음) — `[sell_qty_unnoticed_fills]` 보류가 `selling_reconcile` 해제마다(15분) 되풀이된다: APBK0400 1 + 조회 2. 계좌의 것은 운영자 몫이라 돈 손실 0, B7 은 그 몫을 판다.
6. **K2 남는 틈** — R3-2-3 (가)(나). **K2 비용** — R3-2-4(순서 무관 거부도 유지).
7. **완전 재시작**의 유령·동결(R3-1-7 참고 표)은 부록 R-13-4 · R2-11 ② 계열 — 과소 0.

후속(범위 밖, 한 줄): 없음 — 새로 확인된 것은 R3-2-4 결정 메모(순서 무관 거부 코드)와 R3-1-6 결정 요청뿐이다.

---

### R3-14. 대체 목록 (이 부록이 이기는 자리)

| 자리 | 대체 |
|---|---|
| 부록 R2-8 `_sell_pending_dec(fills)` · `_sell_orders_snapshot` 2-튜플 | R3-1-4(원장 시작 전 주문 제외 · 3-튜플) |
| 부록 R2-8 동작 예 표 · 부록 R-1-3 ⑥ 크레딧 | R3-1-5(원장 시작 전 주문 상한 · 남은 크레딧) — 원장 시작 뒤 주문은 그대로 |
| 부록 R2-11 ① 「F-3 은 재시작 뒤에도 보수적(공식이 그렇다) · 별도 게이트 없음」 | R3-1(시각 비교로 원장 시작 전 주문을 뺀다 — 게이트가 아니다). ② 는 R3-1-5 로 크기만 줄고 R3-13-4 로 남는다 |
| 부록 R2-6 출구 표 「재주문 KIS 거부(`KisApiError`) → rejected」 | R3-2-5 |
| 부록 R2-6 주인 판정 `self._manual_sell_orders.get(order_no, True)` | R3-3 |
| 본문 §g-3 manual-sell 「발사 전 실패는 되돌린다」 · T28 | R3-2-4 · TK11a/b |
| 부록 R2-12 TQ6 docstring | R3-7 |
| 부록 R2-13 AR2-3 · AR10 목록 · AR11 | R3-8 |
| `[sell_qty_partial_locked]` 가 걸린 것 없이도 뜨던 것 | R3-1-6 |

---

### R3-15. 하드 불변식 대조

| 불변식 | 이 부록 뒤 |
|---|---|
| `fields[9]` 체결수량 · 주문수량 3단 출처 | 무접촉(`handler.py` diff 0) |
| 전량 판정에 출처 게이트 없음 | 주문 축·보유 축 판정 무변경 · A10 초록 |
| 재주문 타이머 `qty_src=="map"` 한정 · `(ticker, side)` 키 | 무접촉 |
| `_persist_sell_pending_after_send` 넓은 `except` | 무접촉 |
| `_selling` 좀비 없음 | K3 가 h4h5 좀비를 닫는다. K2 는 「전송 중」 유지를 늘린다 — 해제 주체 = 그 재주문의 종료(걸렸으면) · `selling_reconcile`(열린 매도 0 · 180초). 걸린 것 없는 보류는 통보(닫힘·종료) · `selling_reconcile` |
| `on_position_closed` 보유 0 에서만 · site 정확히 2함수 | 신규 site 0 |
| A-ATOMIC | `execute_buy` 무접촉 |
| 8영역 재핀 값만 + 사유 | R3-11 |
| `scheduler.py` · `boot_manager.py` · `src/realtime/**` 무접촉 | 무접촉 — R3-1-1 이 부팅 변경 **불요**를 보였다 |
| 검사 ~ 행동 사이 await 추가 금지 | 새 await 0. 분류·pending·상한·문구 분기·K2·K3 는 전부 기존 await(주문 조회) 뒤의 동기 구간 또는 `finally` |
| AR2-1 무조건 해제 | 무접촉(`_handle_sell_fill` diff 0) |

### R3-16. Red 착지 (tdd-engineer · 2026-09-28)

- **새 파일** `tests/unit/engine/test_cycle385r3_round3.py` — TK1(`[N3]`·`[N3b]`) · TK3(`[post]`·`[missing]`) · TK4 · TK4b · TK5 · TK6 · TK7 · TK8 · TK9 ×3 · TK10 ×2 · TK12 · TK13(strict xfail). 이름은 표 ID 를 따른다(시제품 `test_tk6_tk7_…` → `test_tk6_pending_excludes_pre_and_clamps_per_order`, `test_tk7b_…` → `test_tk7_lagging_row_does_not_cancel_other_orders_pending`). `_install_acct_t`·`SINCE`·`PRE`·`POST` 는 이 파일에 둔다.
- **바꾼 파일** — `test_cycle385_manual_sell_selling.py`: T28 자리에 TK11a · TK11b ×3(`src.routes.trading` WARNING + prefix 로 한정), TR20 은 마커 단언·`caplog` 삭제(R3-5), 모듈 docstring 규칙에 K2 한 줄 · `test_cycle385r_partial_locked_sell.py`: TR18 마커 단언·`caplog` 삭제 · `test_cycle385r2_round2.py`: TQ6 에 `rows_time ∈ {None, "pre"}`(`pre` 는 `_install_acct_t` 를 함수 안에서 import) · `test_cycle236_sell_qty_exceeded.py:282-285` 주석 · `manual_overrides.yaml:192` 주석 · `test_cycle385_ast_b7.py`: AR2-3 개정 · AR10 목록 +2 · AR11 확장 · AR3-1~AR3-7 신규.
- **표 밖 추가(명세 문장 그대로의 단언뿐)** — TK4 에 `[sell_qty_reconciled]` 1행 · `pre_orders=1` · `pre_cap=2`(R3-6 마커 필드). AR3-5 에 `_old_credit` 우변이 `_sell_reflected_credit`·`_sell_blind_credit` 를 읽는다 · 「뒤 주문 루프 → `_pre_cap` → 앞 주문 루프」 순서(R3-1-5 코드 블록). AR3-1 에 모듈 전체 `_sell_ledger_since` 대입 2곳(R3-1-2 표). AR3-7 은 판정식을 **평가**한다 — except 핸들러에서 discard·`[manual_sell_selling_kept]` 에 닿는 If 조건들을 `_added`·`_sent`·`e`·`isinstance`·`KisApiError`·`is_sell_qty_exceeded` 로만 돌려 진리표(`_added ∧ ¬_sent ∧ APBK0400` / `… ∧ ¬APBK0400`)를 맞춘다 — 중첩 If 든 한 줄 If 든 뜻이 같으면 초록, 별칭을 쓰면 `NameError` 로 붉다.
- **Red 실측(워크트리, git 있음 · `tests/unit`+`tests/contract`)** — 31 failed / 13,192 passed / 333 xfailed / 12 xpassed(비엄격, 기존). 붉은 31 = 새 TK 14 · TQ6`[pre]` 2 · TK11b 3 · AST 12(AR2-3 · AR10 ×2 · AR11 · AR3-1~AR3-7 ×9). **그 밖에 붉은 것 0** — 8영역 핀·트리 다이제스트·인덱스 신선도는 초록(`build_index.py` 재생성 반영). 워크트리에서 초록인 새 테스트 = TK7 · TK10`[physical-13]` · TK11a(현행도 성립 — 회귀 가드).
- **통과 가능성(스크래치 참조, 구현본 아님)** = scratchpad `c385r3t/ref` — 부록 R3 코드 블록 그대로: `order_engine.py` = 시제품 `ref_r3_order_engine.patch`(sha `8c91fe44…`), `routes/trading.py` = R3-2-4 코드 블록(중첩 If · 함수 머리 import · docstring — 시제품의 별칭 한 줄 If 가 아니다, `make_route_ref.py`). 결과: 위 31 전부 초록 · cycle385 9파일 195 passed + 7 xfailed. 전체 스위트는 git 없는 사본끼리 비교(`wtc` 대 `ref2`): 참조가 새로 붉힌 것 = `order_engine.py` sha 핀 7(cycle274 · 276 `test_c6_4c` · 278 · 282 · 290 · 294 · 297) + cycle287 `_SRC_TREE_DIGEST` — R3-11 의 재핀 대상 그대로(222a3·223·223f·226 은 git 없는 사본에서 양쪽 다 원래 붉다).
- **K5 뒤집힘 실측** — 새 TR18·TR20 을 부록 R 주인 규칙 트리(scratch `c385r/ref` + 이 워크트리 tests)에서 돌리면 둘 다 `XPASS(strict)` = 붉다. R3 참조에서는 XFAIL.
- **적대 프로브(참조)** — `c385r3k/ports/test_r3_ports.py` 6 · `ports/test_adv_money.py` 3 · `c385r2m/test_adv_r1fix.py` 4 · `c385r3/h4h5` 1 통과 · `c385r2m/test_adv_r2.py` N1·N4 통과(N2·원문 N3·N3b 붉음 = R3-10 1 의 기대) · `c385r2m/t/test_adv_t.py` p2·p4a·p4b·p4c·p5 통과(p1`[ok]`·rp`[fail]` 원문 · p3·p3b 붉음 = 기대).
- **돌연변이(참조, 57종 전부 죽음 · 전부 행위 테스트가 죽인다)** — R3 MK1~MK21(라우트 MK14·MK15 는 중첩 If 앵커로 옮김) + 부록 R2 MQ1~MQ23(MQ8·MQ16 은 R3 뒤 앵커로 옮김 — MQ16 은 「주인 ∨ 동결」 괄호째 삭제) + 부록 R 보강 13(X-MR2·X-MR11 은 앞/뒤 주문 루프·두 파서로 나눠 a/b/c, X-F3 은 새 보류 문구 뒤 앵커). MQ18(H5 를 `sending` 에도)은 TK9 ×3 · TK10`[EGW]` 등 6건이 죽인다. 러너 = scratchpad `c385r3t/mut_r3t.py` → `mut_r3t_results.json`.
- `manual_overrides.yaml` 등록 없음 — 새 파일은 정적 import 로 잡힌다(`build_index.py` 재생성 확인, `_workspace/test_index.yaml` 갱신).
- **Green 이 할 일(명세 그대로)** — 부록 R3 코드 블록 구현 · R3-11 재핀(10곳 + cycle287 다이제스트, 값만 + 사유 주석) · 문서. 이 착지는 `src/` 를 건드리지 않았다.


## 부록 R4 — 4차 검토 결정(D1~D5) 반영

- 작성: tdd-engineer · 2026-09-28(월) KST · 워크트리 `auto_stock_c385`(B7 + R · R2 · R3 구현 위, 미커밋, `order_engine.py` sha `8c91fe44…` · `routes/trading.py` sha `11ba5f80…`).
- 입력: 메인 세션 결정 D1~D5(최종). 증거 = scratchpad `c385r4/`(tester 표 · `mut/results.json` — MX3·MX4·MX7 은 AST 만 죽였고 MX12 는 생존 · TOCTOU `adv/test_r4_toctou.py`) · `c385r4adv/probes/test_r4_adv.py`(R4-1~R4-7).
- 통과 가능성 참조(구현본 아님) = scratchpad `c385r4t/` — 생성기 `make_ref.py` → `order_engine.REF.py`·`trading.REF.py` · 사본 `ref`(돌연변이)·`ref2`(전체 스위트)·`wtc`(git 없는 워크트리 사본) · 러너 `mut_r4t.py` → `mut_r4t_results.json`. **이 부록의 코드 블록이 정본이다.**

### R4-0. 결론

| 결정 | 처방 | 자리 |
|---|---|---|
| D1 | 걸린 것 없는 보류(`held == sellable` · `eff ≤ 0`) **유지**(운영자 몫 보호 · 푸는 주체 = 종료 통보 · 보유 닫힘 · `selling_reconcile`). 코드 변경 없음 — 문구만 D4 | — |
| D2 | 「안 걸렸다」 판정을 한 곳 `_sell_not_placed_reason(exc)` 로 — APBK0400(R3 K2 그대로) + **주문 자체의 결정적 거부**(시장가 불가 · 장운영시간 외). 나머지(EGW00201 · 5xx · 전송 예외 · 모르는 코드 · 보유 부족 문구)는 「전송 중」 유지. 재주문과 manual 라우트가 같은 판정을 쓰고, 분류를 기존 마커·줄에 싣는다 | `order_engine.py` · `routes/trading.py` |
| D3 | R4-7 · R4-1 = 문서화된 한계(R4-4) | 문서 |
| D4 | 조회 실패(`fills is None`) · 걸린 것 없음 보류는 `[sell_qty_unnoticed_fills]` 대신 `[sell_qty_hold_orders_unavailable] … orders=<이유>` | `order_engine.py` |
| D5 | MX12 · MX3 · MX7 (+ MX4) 를 행위 테스트로 죽인다 | 테스트 |

### R4-1. D2 판정 헬퍼 — 모듈 수준 · 동기 · never-raise

자리 = `_classify_after_exit_rejection` 바로 뒤(그 함수는 「관측 전용 · 게이트에 쓰지 않는다」가 계약이라 재사용하지 않는다).

```python
def _sell_not_placed_reason(exc: BaseException) -> "str | None":
    """cycle385 부록 R4 D2 — 이 발사 예외가 「우리 매도 주문이 거래소에 걸리지 않았다」를 확정하는가.
    (a) APBK0400 — 부록 R3-2-3 부등식. (b) 주문 자체의 결정적 거부 — 같은 본문의 첫 전송 시도도 똑같이
    거부됐을 것: 시장가 불가(APBK1943·APBK3013 계열) · 장운영시간 외(APBK0918 + 장운영시간 문구).
    그 밖은 None = 「전송 중」. 분류는 `src.api.balance` 의 기존 판정 함수만 쓴다. never-raise."""
    try:
        if not isinstance(exc, KisApiError):
            return None
        if is_sell_qty_exceeded(exc):
            return "qty_exceeded"
        if is_market_closed_rejection(exc):
            return "market_closed"
        if is_market_order_disallowed(exc):
            return "market_order_disallowed"
        return None
    except Exception:
        return None
```

| 예외 | 결과 |
|---|---|
| APBK0400 +「수량」·「초과」 | `qty_exceeded` |
| 장운영시간 문구 · 프리마켓 문구(두 분류기에 다 걸림 — `execute_sell` 과 같은 우선순위) | `market_closed` |
| APBK1943 · APBK3013(애프터 · 단일가) 시장가 불가 문구 | `market_order_disallowed` |
| EGW00201(순서 의존) · APBK0918 보유 부족 문구 · 코드만 APBK0400 인 다른 문구(**앞 시도의 접수가 만들 수 있다**) · 모르는 코드 · `RuntimeError` · `httpx` 전송 예외 · HTTP 5xx | None |

- 🔴 분류기는 **msg1 문구 기반**(기존 `_MARKET_CLOSED_KEYWORDS` · `_MARKET_ORDER_DISALLOWED_KEYWORDS`)이다. 같은 코드라도 문구가 안 걸리면 None — 덜 푸는 쪽. 프로브 R4-2 의 APBK3013(msg1 `"rejected"`)이 D2 뒤에도 붉은 이유이고, 이식판 TR4-6 은 실제 문구를 쓴다. 키워드를 여기서 다시 맞추지 않는다(AST AR4-1).
- 남는 틈(기록) — 장 경계를 가로지른 재시도(앞 시도가 경계 앞에 접수·응답 유실 → 뒤 시도가 경계 뒤 장운영시간 외·시장가 불가 거부)면 걸린 주문 옆에서 `_selling` 이 풀린다. 그 창의 다음 손절도 같은 이유로 거부되고 KRX 정규장 미체결은 마감 자동 취소라 쌓이지 않는 쪽이지만 증명은 아니다.

### R4-2. D2 자리

**재주문** `_cancel_and_reorder` (`finally` 판정식 = R3-3 진리표 **무변경** — D2 는 「무엇이 안 걸렸나」만 넓히고 「누구의 표식을 푸나」(주인 ∨ 동결)는 그대로, TR4-4):
```python
        _cancel_ok = False
        _place_state = "none"
        _place_reject: "str | None" = None
        ...
                _place_state = "sending"
                try:
                    result = await place_order(**place_kwargs)
                except KisApiError as _place_exc:
                    # 부록 R3 K2 · R4 D2 — 「안 걸렸다」 = APBK0400 · 주문 자체의 결정적 거부뿐.
                    _place_reject = _sell_not_placed_reason(_place_exc)
                    if _place_reject is not None:
                        _place_state = "rejected"
                    raise
        ...
                logger.warning(
                    "[reorder_selling_released] ticker=%s order_no=%s place=%s reject=%s",
                    ticker, order_no, _place_state, _place_reject or "-",
                )
```

**manual 라우트** `routes/trading.py::manual_sell` — 함수 머리 import 에서 `KisApiError`·`is_sell_qty_exceeded` 를 빼고 `from src.engine.order_engine import _KST_TZ, _sell_not_placed_reason`. docstring 「확정된 실패(APBK0400)만 되돌리고」 → 「(APBK0400 · 시장가 불가 · 장운영시간 외 — `_sell_not_placed_reason`)만 되돌리고」.
```python
    except Exception as e:
        # 🔴 cycle385 부록 R3 K2 · R4 D2 — 「발사 안 됨」이 **확정된** 실패만 되돌린다
        # (`_sell_not_placed_reason` = APBK0400 · 시장가 불가 · 장운영시간 외). 그 밖은 표식을 두고 그 주문의
        # 종료 통보 또는 `selling_reconcile` 에 맡긴다. 발사 뒤(`_sent`) 실패는 되돌리지 않는다.
        _released = "-"
        if _added and not _sent:
            _not_placed = _sell_not_placed_reason(e)
            if _not_placed is not None:
                engine._selling.discard(req.ticker)
                engine._selling_since.pop(req.ticker, None)
                _released = _not_placed
            else:
                logger.warning("[manual_sell_selling_kept] ticker=%s err=%s — …(문구 무변경)", req.ticker, e)
        logger.error("수동 매도 실패: %s — %s selling_released=%s", req.ticker, e, _released)
        return ApiResponse(success=False, message=f"매도 주문 실패: {e}")
```
- 라우트 분류 칸을 실패 줄에 싣는 이유 — 되돌림 경로엔 마커가 없고 새 접두를 만들지 않는다. 실패 줄은 발사 실패마다 1행이다.

### R4-3. D4 — 조회 실패 · 걸린 것 없음 보류 문구

`execute_sell` F-3 보류(`held_qty >= eff` 본문 · `fire < 1`)의 문구 분기를 셋으로 — 동작(동결 표식 + return)은 D1 대로 무변경, 새 await 0:
```python
                            if held_qty > sellable:
                                logger.warning("[sell_qty_partial_locked] … 무변경 …")
                            elif fills is None:
                                # 부록 R4 D4 — 조회를 못 믿는데 걸린 매도가 없다(조회 await 중 통보가
                                # 추적을 줄였다). 거래소가 확인한 미통보 체결이 있는지 모른다.
                                logger.warning(
                                    "[sell_qty_hold_orders_unavailable] ticker=%s strategy=%s "
                                    "held=%d sellable=%d positions=%d orders=%s — 걸린 매도 없음 · "
                                    "주문 조회 실패로 미통보 체결 여부를 알 수 없어 발사 없이 보류"
                                    "(종료 통보·보유 닫힘·selling_reconcile 이 푼다)",
                                    ticker, strategy_id, held_qty, sellable, pos.quantity, _reason,
                                )
                            else:
                                logger.warning("[sell_qty_unnoticed_fills] … 무변경 …")
                            self._selling_locked_wait.add(ticker)
                            return
```
- 도달 = 진입 `0 < sellable < 추적`(await **앞** 값) 뒤 조회 await 동안 매도 통보가 추적을 보유 이하로 줄였다(seed 1177). 부록 R3-1-6 「조회 실패로는 이 갈래에 올 수 없다」는 이 경합을 놓쳤다.
- 접두는 조회 실패 계열(`[sell_qty_reconcile_orders_unavailable]` 과 짝 · `orders=` = `[sell_qty_partial_locked]` 의 조회 실패 칸과 같은 이름). AR3-6 은 그대로 초록(`elif` 는 `held_qty > sellable` 의 orelse 안).

### R4-4. D3 — 문서화된 한계(코드 변경 없음)

- **R4-7** — 교체된 재주문 타이머의 `finally` 가 손님 manual 주문이 걸린 동안 `_selling` 을 푼다. 조건 = 손님 manual 주문 + 원주문 취소 뒤 CANCELLED 장부 await 창(ms)에 부분 체결 통보(교체) + 운영자 초과분. 실측(워크트리·참조 같음) 발사 `[10, 4, 3, 6]` — 걸린 manual 위에 다음 손절 6 이 쌓였다(계좌 20 → 7, 그 시드는 「전략 10 + manual 4 이하」 안). 초과분이 쌓인 몫보다 작으면 운영자 몫을 판다. 부록 R2-1 대가(LOW #3)와 같은 계열.
- **R4-1** — 재주문 앞 시도 접수(응답 유실) + 뒤 시도 APBK0400 + 숨은 재주문의 부분 체결 통보가 다음 틱 **전**에 착지(R3-2-3 (가)). 실측 `notice_first=True` 발사 `[10, 6, 6, 3]` · 계좌 13 → 0(운영자 3 매도) · `False` 는 계좌 3 보존.
- D2 가 남기는 비용 — EGW00201·전송 예외로 manual 발사가 실패하면 `_selling` 이 남아 그 종목 손절이 `selling_reconcile`(15분 sync + 180초, 09:30 전 sync 없음)까지 멈춘다(TR4-6`[EGW00201-kept]` 이 고정). R3-2-4 비용 중 APBK3013·APBK0918 몫은 없어졌다.
- 범위 밖 프로브 붉음(R4-3 시각 어긋남 `115958` · R4-4 · R4-5)은 R3-13 · F-R3-2 그대로.

### R4-5. 마커

| 마커 | 변경 |
|---|---|
| `[reorder_selling_released]` WARNING | 끝에 `reject=qty_exceeded\|market_closed\|market_order_disallowed\|-`(`place=none` 이면 `-`) |
| `수동 매도 실패: <ticker> — <err> selling_released=<이유\|->` (`src.routes.trading` ERROR) | 끝 칸 추가 — 라우트가 `_selling` 을 되돌렸으면 이유, 아니면 `-`(유지 · 손님 · 발사 뒤) |
| `[sell_qty_hold_orders_unavailable] ticker= strategy= held= sellable= positions= orders=` WARNING | 신규(D4) · 드묾 |
| `[sell_qty_unnoticed_fills]` · `[manual_sell_selling_kept]` | 형식 무변경 · 뜻 좁힘(각각 조회 성공일 때만 · 판정 None 일 때만) |

전부 `logger.*`(새 `write_log`·DB·`KstDailyEmitCap` 0).

### R4-6. 테스트 (Red)

새 파일 `tests/unit/engine/test_cycle385r4_round4.py`(하네스 = R2·R3 파일 · 벽시계 0 · 새 심볼은 함수 안 import):
- **TR4-1** 판정표 14행(never-raise — msg1 이 문자열이 아닌 행 포함).
- **TR4-2 ×6** 재주문 결정적 거부(장운영시간 외 · 프리마켓 · APBK1943 · APBK3013 애프터·단일가 · APBK0400) → `_selling`·`_selling_since`·동결 비움 · `[reorder_selling_released] place=rejected reject=<이유>` 1 · 다음 손절 6 발사.
- **TR4-3 ×5** 재주문 EGW00201 · APBK0918 보유 부족 · 모르는 코드 · 코드만 APBK0400 · `RuntimeError` → 유지 · 해제 마커 0.
- **TR4-4 ×2** 손님 manual(동결 아님) 재주문 결정적 거부 → 주인 `_selling` 유지.
- **TR4-5** 재주문 없이 해제 → `place=none reject=-`.
- **TR4-6 ×4** R4-2 이식 — manual 첫 시도 거부 뒤 손절: APBK3013 · APBK0918 · APBK0400 → `[10]` · EGW00201 → `[]`(비용 고정).
- **TR4-7 ×3** D4 TOCTOU 이식 `error`·`bad_row`: 발사 `[10]` · `[sell_qty_hold_orders_unavailable] orders=<이유> held=6 sellable=6 positions=6` 1 · unnoticed·locked 0 · 동결 표식 · 다음 틱 `[10, 6]` / `ok`(대조): `[10, 6]` · 보류 문구 0.
- **TR4-8**(MX12) 추적 13 · MTS-P(원장 시작 전 접수, 재시작 전 체결 0) 뒤 3 통보 처리 + 2 대기 · 잔량 1 → 크레딧 `{P: 2}`(= `min(5 − 3, 상한 5)`) · `pre_cap=5` · 발사 `[10, 5, 4]` · 끝 `(None, 0)` · 매 단계 추적 ≥ 계좌.
- **TR4-9**(MX3) 추적 7 · MTS-Y(앞) 재시작 전 4 + 뒤 2 대기 · 잔량 3 · MTS-Q(뒤) 1 대기 → 크레딧 `{Y: 2, Q: 1}` · `pre_cap=2`(= 7 − 4 − **1** + 0) · 발사 `[7, 4, 1]` · 끝 `(None, 0)`.
- **TR4-10**(MX4) TK4b 의 첫 조회 실패판 → 종목 크레딧 3 → 둘째 재대조 상한 5 → A 크레딧 5 · 종목 크레딧 비움 · 추적 == 계좌 == 5(빼먹으면 과소 추적 — R-INV-1).

`tests/unit/routes/test_cycle385_manual_sell_selling.py`:
- **TR4-R1 ×5** 결정적 거부(`apbk0918_closed` · `apbk0918_premarket` · `apbk1943` · `apbk3013_after` · `apbk3013_tk11b_old`) → 되돌림 · 유지 마커 0 · `selling_released=<이유>`.
- **TR4-R2 ×4**(MX7) 손님(`_selling`·시각 선재) 실패(APBK0400 · 장운영시간 외 · APBK3013 · `RuntimeError`) → 그대로 · 유지 마커 0 · `selling_released=-`.

### R4-7. AST (`tests/unit/ast/test_cycle385_ast_b7.py`)

- **AR2-3(개정)** 재주문 `except KisApiError as <n>:` = 맨 끝 bare `raise`(그 밖 raise·await 0) · `_sell_not_placed_reason(<n>)` 정확히 1 · 본문을 **실행해** 판정 None → `sending` / 이유 → `rejected` · `_cancel_and_reorder` 안 분류기 셋 직접 호출 0 · 해제 문구 ` reject=`. `finally` 진리표 무변경.
- **AR3-7(개정 · 이름 `…_only_on_not_placed_rejection`)** manual 핸들러를 판정 대역으로 **실행해** 16조합: 되돌림 ⇔ `_added ∧ ¬_sent ∧ 이유` · 유지 마커 ⇔ `_added ∧ ¬_sent ∧ None` · 실패 줄 끝 `selling_released=<이유|->` · 판정 1회 · 분류기 직접 호출 0 · 함수 안 `from src.engine.order_engine import … _sell_not_placed_reason`.
- **AR10(확장)** + `_sell_not_placed_reason`.
- **AR4-1** 헬퍼 = 모듈 수준 동기 def · await 0 · 본문 `try/except Exception` 하나 · 호출 = `isinstance(…, KisApiError)` + 분류기 셋 · 속성 읽기 0 · 문자열 상수 = 이유 셋 · 분류기 셋은 `src.api.balance` import.
- **AR4-2** F-3 안 `[sell_qty_hold_orders_unavailable]` 도달 ⇔ 걸린 것 없음 ∧ `fills is None` · `[sell_qty_unnoticed_fills]` 도달 ⇔ 걸린 것 없음 ∧ `fills is not None`(조건 실행) · `orders=%s` ← `_reason`.

### R4-8. 기존 테스트 변경(사유 동반)

| 테스트 | 변경 | 사유 |
|---|---|---|
| `test_tk11b_…[apbk3013]`(msg1 「시장가 주문 불가」) | 목록에서 빼 TR4-R1`[apbk3013_tk11b_old]`(되돌림)로. 대신 `apbk0918_holding_short` · `unknown_code` · `read_timeout` | D2 — 그 문구는 시장가 불가 분류기에 걸린다 |
| TK11a · TK11b | + 실패 줄 `selling_released=qty_exceeded` / `-` | D2 분류 칸 |
| `test_cycle385r3_round3.py::test_tk9_…` | docstring 한 단락(msg1 「거부」 는 분류기에 안 걸려 D2 뒤에도 유지) | D2 |
| 라우트 모듈 docstring | 규칙 두 줄(D2 · D5) | — |

### R4-9. 돌연변이 (참조, 87종 전부 죽음 — 85종은 행위 테스트)

- 기반 = tester 69종(경로만 바꿈). 앵커가 사라진 6종은 R4 앵커로 옮김(MK10 판정 `or "any"` · MK11 `if False` · MK14/MK15 라우트 `if True/False` · MX6 헬퍼 첫머리 「APBK 면 거부」 · MX9 헬퍼 `isinstance` 가드 삭제).
- **D5 확인** — MX12 → TR4-8 · MX3 → TR4-9 · MX4 → TR4-10 · MX7 → TR4-R2 ×4.
- 신규 18종 R4M1~R4M18 — 헬퍼(APBK0400 만 · 시장가 불가 삭제 · 장운영시간 삭제 · 순서 뒤집기 · 모든 `KisApiError` · 보유 부족 추가 · never-raise 제거) · 재주문(핸들러 APBK0400 만 · 주인 규칙 우회 · `reject=` 삭제 · `_place_reject` 초기화 삭제) · 라우트(APBK0400 만 · 발사 뒤에도 되돌림 · `selling_released` 미기록) · D4(unnoticed 문구 · 잠김 문구 · 조회 실패에도 발사(D1) · `orders=` 가 이유 아님). 전부 죽음 — 행위 17 · AST 만 1(R4M13 라우트 `if _added:` — 발사 뒤 `KisApiError` 는 이 경로에 없다).
- AST 만 죽인 2종 = R4M13 · MX9(헬퍼가 never-raise 라 `isinstance` 가드를 빼도 행위가 같다 — 동치, AR4-1 이 막는다).

### R4-10. Red 실측 · 통과 가능성

- **Red(워크트리, git 있음 · `tests/unit`+`tests/contract`)** — 32 failed / 13,230 passed / 333 xfailed / 12 xpassed(비엄격, 기존). 붉은 32 = 엔진 12(TR4-1 · TR4-2 ×6 · TR4-5 · TR4-6 ×2 · TR4-7 ×2) · 라우트 15(TK11a · TK11b ×5 · TR4-R1 ×5 · TR4-R2 ×4 — TR4-R2 는 상태는 맞고 분류 칸만 없다) · AST 5(AR10 · AR2-3 · AR3-7 · AR4-1 · AR4-2). **그 밖에 붉은 것 0**(8영역 핀 · 트리 다이제스트 · 인덱스 신선도 초록 — `build_index.py` 재생성 반영). 이미 초록인 새 테스트 13 = TR4-3 ×5 · TR4-4 ×2 · TR4-6 ×2 · TR4-7`[ok]` · TR4-8 · TR4-9 · TR4-10(회귀 가드).
- **통과 가능성(참조 `c385r4t/ref`)** — cycle385 12파일 239 passed + 7 xfailed. 전체 스위트 git 없는 사본끼리(`wtc` 대 `ref2`): 참조가 새로 붉힌 것 = `order_engine.py` sha 핀 7(cycle274 · 276 `test_c6_4c` · 278 · 282 · 290 · 294 · 297) + cycle287 `_SRC_TREE_DIGEST` = R4-11 재핀 대상 그대로(222a3 · 223 · 223f · 226 과 git 전용 가드는 양쪽 다 원래 붉다). 참조가 초록으로 돌린 것 = 위 32 전부.
- **적대 프로브(참조)** — TOCTOU `[fail]` 문구가 `[sell_qty_hold_orders_unavailable]` 로 · 다음 틱 6 매도(돈 결과 무변경). `test_r4_adv.py` 는 워크트리와 같은 결과(R4-4 한계 · 범위 밖 · R4-1 의 msg1 사유).
- `manual_overrides.yaml` 등록 없음. 이 착지는 `src/` 를 건드리지 않았다.

### R4-11. 핀 · 문서 (Green)

- `order_engine.py` whole-file sha **10곳**(현재 `8c91fe44b8aaa361e1b324c3f7b74cef18fe555e159f04696c6c4cd387404a0b` — 착수 전 `grep -rl` 로 다시 센다: cycle222a3 · 223 · 223f · 226 · 274 · 278 · 282 · 290 · 294 · 297) 값만 재핀. 사유 주석: `# 🔁 2026-09-28 (cycle385 부록 R4) 재핀 — 4차 검토 결정: 「안 걸렸다」 판정 한 곳 _sell_not_placed_reason(APBK0400 · 시장가 불가 · 장운영시간 외, D2) · 재주문 해제 로그 reject= 칸 · 조회 실패 걸린 것 없음 보류 문구 분리(D4). 사용자 승인(8영역), 나머지 7영역 diff 0.`
- `test_cycle287_ast_scope.py::_SRC_TREE_DIGEST` 값만 재핀(`routes/trading.py`). `_BASE_SHA["src/api/balance.py"]` 무변경.
- 붉어지면 범위 밖(재핀 금지, 되돌린다): `test_cycle295_ast_market_rest.py::_BYTE_IDENTICAL_PINS` · `_FROZEN_SEGMENTS` · `scheduler.py` · `boot_manager.py` · `src/realtime/**` · `src/api/*` · `src/db/*`.
- 문서(`/sync-docs` → report-writer): `src/engine/CLAUDE.md` 「매도 체결 — 주문 축과 보유 축」(재주문 미접수 해제 판정 = `_sell_not_placed_reason` · `reject=` · `[sell_qty_hold_orders_unavailable]` · unnoticed 는 조회 성공일 때만 · 「지시 문장과 다른 동작」 의 APBK3013 비용 정정 · 알려진 한계에 R4-7 · R4-1) · `src/routes/CLAUDE.md` manual-sell 행(되돌림 판정 · `selling_released=` · 알려진 한계 ① 「APBK3013 이면 `_selling` 이 남고」 → 되돌린다로 정정) · history append.

### R4-12. 하드 불변식

`fields[9]` · 주문수량 3단 출처 · 전량 판정 출처 게이트 없음 · 재주문 타이머 `qty_src=="map"`·`(ticker, side)` · `_persist_sell_pending_after_send` 넓은 `except` · `on_position_closed` 보유 0 · 2함수 · AR2-1 무조건 해제 · A-ATOMIC — 전부 무접촉(`_handle_sell_fill` · `execute_buy` diff 0). `_selling` 좀비 — D2 는 해제만 늘린다(루트 규칙 「APBK0918 거부는 `_selling` 을 해제한다」), 유지가 늘어난 곳 0. 검사 ~ 행동 사이 새 await 0. `scheduler.py` · `boot_manager.py` · `src/realtime/**` · `src/api/*` 무접촉. 8영역 재핀 값만 + 사유(R4-11).

### R4-13. 대체 목록 (이 부록이 이기는 자리)

| 자리 | 대체 |
|---|---|
| R3-2-2 핸들러 `if is_sell_qty_exceeded(_place_exc)` · R3-2-5 출구 표 「그 밖의 코드 → sending」 | R4-2 |
| R3-2-4 라우트 핸들러 · 「순서 무관 거부 비용」 결정 메모 | R4-2 · R4-4 |
| R3-6 `[reorder_selling_released]` 「`place=rejected` = APBK0400」 · `[manual_sell_selling_kept]` 뜻 | R4-5 |
| R3-1-6 「조회 실패로는 이 갈래에 올 수 없다」 | R4-3 |
| R3-8 AR2-3 · AR3-7 · AR10 | R4-7 |
