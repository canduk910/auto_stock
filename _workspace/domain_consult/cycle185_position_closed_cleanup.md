# 사이클 185 클러스터 ① 메커니즘 2 — 보유결합 상태 매도 체결 시점 정리 (행위 영향·안전성 자문)

> 대상: `StrategyBase.on_position_closed(ticker)` no-op 추가 + LTV `_limit_up_reached.discard` / BFB `_partial_exit.pop` override + order_engine 2 site 배선 (`_handle_sell_fill` 전량 체결 / `execute_sell` insufficient_quantity reconciliation).
> 승인 계획: `~/.claude/plans/hazy-prancing-cookie.md` 메커니즘 2.
> 메커니즘 1 (transient 일일 리셋) 은 본 자문 범위 밖.

## 질문 요약

핵심 불변식 = **"보유 중 flag 유지, 전량 매도 시 flag clear"**. 20:10 일괄 리셋이 아니라 *매도 체결 시점* 정리가 맞는지, cycle 142 (08:00 `_limit_up_reached.add` 재확립) 와 충돌/순서역전이 없는지, secondary hook (reconciliation) 포함이 타당한지, 재매수 fresh·부분체결 edge 의 행위 영향이 트레이더 의도에 맞는지 5개 의제로 평가.

---

## 결정적 코드 사실 (자문 전제 — 직접 검증)

자문의 결론은 아래 4개 사실에 의존한다. 모두 직접 grep/read 로 확인했다.

1. **flag 는 메모리 전용 (미영속)**: `_limit_up_reached: set[str]`(LTV L113) / `_partial_exit: dict[str,bool]`(BFB L128) 모두 인스턴스 메모리. DB 영속 0. 프로세스 재시작 시 빈 상태로 재구성. prepare() 는 의도적으로 미접촉 (LTV L138 cycle 180 주석 — 청산 모드 경로라 prepare clear 금지).

2. **flag 는 매수 진입을 게이트하지 않는다**: LTV `_limit_up_reached` 의 production 참조처는 (a) L569 status 표시 (관찰성, `_targets` 기반), (b) L764 check_exit_signal 모드 분기, (c) L808 상한가 도달 add, (d) L820 check_force_clear 제외 필터뿐. **check_buy_signal 에는 참조 0건**. 즉 stale flag 가 있어도 재매수 자체는 막지 않고, *재매수된 포지션의 청산 모드* 만 오염시킨다. BFB `_partial_exit` 도 동일 — check_exit_signal(L915/L917) 에서만 읽고 쓴다.

3. **`is_ticker_blocked_for_buy` 가 포지션 존재 ↔ 재매수 차단을 결합**: 포지션이 메모리에 살아있는 동안(`is_ticker_held_by_any`) 또는 당일 매도(`sold_today`) 동안 재매수 차단. → **포지션이 제거되기 전에는 재매수 불가** = flag 정리와 재매수 사이에 race window 없음 (flag 정리는 포지션 제거와 동기).

4. **`_sync_positions_from_balance` 는 additive-only**: `h.quantity > 0` 인 KIS 잔고만 순회하며 *누락 포지션 추가* 만 수행 (scheduler L3637~3690). **KIS 잔고에서 사라진 포지션을 메모리에서 제거하는 분기 0건**. → 수동 HTS 매도 등 외부 청산은 balance sync 가 정리하지 못하고, 알고리즘이 다음 매도 시도 시 `insufficient_quantity` 응답 → **secondary hook (L793) 가 유일한 catch-all** 이 된다.

order_engine 내 메모리 포지션 제거 site 는 전수 2곳뿐 (grep 확인): L793 (secondary, insufficient_qty) + L1169 (primary, 전량 체결). 이 2곳이 곧 flag 정리 site 와 1:1 대응한다. (L3807 `positions.clear()` = 20:10 `_reset_daily_state` 는 별도 — 의제 1 에서 다룸.)

---

## 의제 1 — held-position flag 영속 안전성 + cycle 142 순서역전 (HIGH)

### 트레이더 시각

LTV "연속 상한가 익일 청산" 설계는 *밤새 들고 가는 포지션* 의 청산 모드를 표현한다. 상한가 모드 종목은 익일 시초 갭에 따라 (갭 < 10% → 즉시 청산 / 갭 ≥ 10% → 트레일링) 처리되며, 이 판단은 `_limit_up_reached` 멤버십이 켜져 있어야 발동한다. 즉 **보유가 지속되는 동안 flag 가 유지되는 것이 곧 청산 모드의 정의**다. flag 가 꺼지면 그 종목은 당일 모드(-3% + 15:20 강제청산)로 강등 = 밤샘 보유 의도가 깨진다. 그래서 20:10 일괄 리셋은 *절대* 안 되고(밤샘 보유 종목의 청산 모드 파괴), 매도 시점 정리가 정답이라는 계획 판단은 트레이더 본능과 일치한다.

### flag 생애주기 정밀 추적 (재시작 유무 분기)

- **무재시작 세션**: Day1 상한가 → L808 add → 20:10 `_reset_daily_state` 가 `positions.clear()` 하지만 `_limit_up_reached` 는 미접촉 → flag 가 밤새 메모리에 생존 → Day2 07:50 boot 가 DB 에서 positions 복원 → flag 그대로 → 청산 모드 정합. **이 경우 flag 유지가 정확.**
- **재시작 세션**: flag 소멸(빈 set) → 07:50 boot positions 복원되나 flag 비어있음 → **08:00 cycle 142 가 갭상승 트레일링 분기에서 `_limit_up_reached.add(ticker)` + `pos.high_since_buy=today_open` 재확립** (scheduler L1390~1394) → 청산 모드 복원.

두 경로 모두 08:00 시점에 (재확립 또는 잔존으로) flag 가 ON. `on_position_closed` 의 discard 는 *전량 매도 체결 이후에만* 발화하고, 매도는 빨라야 08:00 `_execute_next_day_clear`(즉시 청산 분기) 또는 장중 트레일링/손절 — 즉 **항상 08:00 재확립 *이후***.

### 순서역전 가능성 — 없음 (근거)

- cycle 142 의 add 는 08:00 1회, *아직 보유 중인(미매도)* 포지션을 트레일링 모드로 넣을 때만 수행. discard 는 *매도 체결* 시. 같은 ticker 가 08:00 시점에 "트레일링 모드로 들어가는 중(보유)" 과 "전량 매도 체결(소멸)" 을 동시에 만족할 수 없다 → 동일 tick 충돌 불가.
- "discard 먼저 → cycle 142 add 가 매도된 종목에 flag 재부착" 시나리오? cycle 142 는 처리 대상 포지션(보유 中)만 순회하므로 이미 매도되어 positions/익일청산 set 에서 빠진 종목엔 add 하지 않는다 → 재부착 0.
- 즉시 청산 분기(갭 < threshold)에서는 cycle 142 가 애초에 add 하지 않음. 이 종목이 즉시 매도되면 discard 는 (잔존 flag 있으면) 정리, (빈 set 이면) no-op — 어느 쪽이든 안전.

### 판정: **GO**

보유 중 유지 → 매도 시 정리의 시간적 분리는 견고하며 cycle 142 와 race/순서역전이 없다. 본 변경은 boot/cycle142 재구성 로직을 *전혀 건드리지 않고* 매도 시 discard 만 추가하므로 기존 재확립 메커니즘과 직교(orthogonal)한다.

---

## 의제 2 — 재매수 fresh 의 행위 영향 (HIGH)

### 트레이더 시각

"연속 상한가 익일 청산" 은 **동일 포지션을 끊지 않고 들고 가는** 전략이지, *매도 후 재매수* 종목의 전일 상한가 이력을 추적하는 전략이 아니다. 재매수는 prepare() 필터를 새로 통과하고 새 돌파/연속상한가 조건으로 들어온 **신규 진입**이다. 신규 진입 시점에 그 종목이 다시 상한가를 치면 그날 L808 에서 `_limit_up_reached.add` 가 새로 발화해 상한가 모드로 전환되고, 치지 않으면 당일 모드(-3% + 15:20 강제청산)가 맞다. 전일에 상한가였다는 사실이 오늘 새로 산 포지션의 손절 임계나 보유 정책을 결정해서는 안 된다 — 그건 **이력 누설(leakage)** 이지 추적이 아니다.

코드 사실 2 가 이를 뒷받침: `_limit_up_reached` 는 check_buy_signal 을 게이트하지 않으므로, 재매수는 정상 발생하고 stale flag 는 오직 *청산 모드만* 오염시킨다. 따라서 재매수 시 flag 가 비어 있어 당일 모드로 진입하는 것이 정확한 의도다.

### 누설 경로 — 본 변경으로 완전 봉쇄됨 (핵심 결과)

stale flag 가 "재매수 오모딩" 버그를 일으키려면 *flag 가 살아있는 상태에서 같은 ticker 가 재매수* 되어야 한다. 코드 사실 3 에 의해 재매수는 포지션이 메모리에서 제거된 *후* 에만 가능하고, 포지션 제거 site 는 전수 2곳(L793/L1169)뿐이며 본 변경이 두 곳 모두에 discard 를 배선한다 → **flag 는 어떤 재매수보다 반드시 먼저 정리된다**. 추가로 프로세스 재시작이 flag 를 전면 소거(코드 사실 1)하므로 잔존 window 는 단일 연속 세션으로 한정되고, 그 세션 내에서도 2 hook 이 누설을 봉쇄한다.

> 운영 맥락: 후성(093370) 사례처럼 상한가 모드 종목이 재매수 회전되는 코스닥 테마주 환경에서 이 누설은 실제 손실로 직결됐다(전일 모드 잔존 → -5% 손절 + 15:20 강제청산 회피 → 의도치 않은 밤샘 보유). 본 변경이 그 뿌리를 끊는다.

### 판정: **GO**

재매수 = 신규 진입 → 당일 모드 진입이 트레이더 의도에 정합. 연속 상한가는 "보유 지속"으로 추적되지 "재매수 이력"으로 추적되지 않는다. 본 변경이 누설 경로를 구조적으로 봉쇄한다.

---

## 의제 3 — secondary hook (execute_sell L793 reconciliation) 타당성 (HIGH)

### 트레이더 시각

L793 분기는 "모든 매도 재시도 실패 + `insufficient_quantity`(KIS 보유 수량 부족)" → 메모리 positions 강제 pop. 이는 곧 **KIS 측에 그 종목이 없다 = 포지션이 외부에서 사라졌다** 는 신호다. 포지션이 사라지는 지점이므로 청산 모드 flag 도 함께 정리되는 것이 일관된다.

더 중요한 점: 코드 사실 4 에 의해 `_sync_positions_from_balance` 는 *사라진 포지션을 제거하지 않는다*. 따라서 **수동 HTS 매도** 등 외부 청산은 알고리즘이 다음 매도(08:00 익일청산 / 장중 트레일링·손절)를 시도해 `insufficient_quantity` 를 받는 이 L793 경로로만 정리된다. **secondary hook 은 "외부에서 증발한 포지션" 의 유일한 catch-all** 이며, 이것이 없으면 수동 매도된 상한가 모드 종목의 flag 가 재시작 전까지 누설된다. 즉 secondary hook 은 "실제 매도가 아니라 reconciliation 이니 빼자" 가 아니라 *오히려 누락 봉쇄에 필수*.

### actual_qty > 0 edge (보수적·안전 방향)

L818 의 재조회에서 `actual_qty > 0`(수동 부분매도로 일부 잔량 존재) 이면 positions 는 이미 pop 되었고(기존 코드의 선재 비일관 — 변경 전부터 존재) 재등록은 *권고 로그만* 남긴다. 본 변경으로 flag 도 함께 정리되면, 이후 balance sync 가 그 잔량을 **fresh 포지션(flag 없음)** 으로 재등록 → 당일 모드(-3% + 15:20 강제청산). 이는 *더 보수적인* 방향(타이트한 손절 + 빠른 청산)이며 위험하지 않다. 위험한 방향은 그 반대(당일 종목이 상한가 모드를 잘못 유지 → 15:20 회피 → 의도치 않은 밤샘)인데, 본 변경은 그 반대 방향을 *막는다*. 흔한 케이스(actual_qty=0, 진짜 증발)에서는 flag 정리가 정확하고, 드문 edge(actual_qty>0)에서는 보수적 — 양쪽 모두 안전.

### 판정: **GO**

secondary hook 은 외부 증발 포지션의 catch-all 로서 누락 봉쇄에 필수. actual_qty>0 edge 는 보수적(안전) 방향. 단, 격리 try/except 로 reconciliation 본류(positions pop/DB delete/get_balance 재조회)를 절대 차단하지 않을 것(계획 명시 — 유지).

---

## 의제 4 — BFB `_partial_exit` 재진입 (MEDIUM)

### 트레이더 시각

`_partial_exit` 는 measured-move(폴 폭만큼 추가 상승) 도달 시 1회만 익절 신호(현 1차 구현 = 전량 청산 TRAILING_STOP)를 내기 위한 **once-only 가드**다. 이 "once-only" 의 의미 단위는 *해당 보유 기간(per-holding-period)* 이지 *종목 영구(per-ticker-forever)* 가 아니다. 동일 종목을 끊고 다시 새 폴/플래그 패턴으로 재진입하면, 그건 새 측정이동 타겟을 가진 새 트레이드다. 새 트레이드가 측정이동에 도달하면 익절이 다시 발화하는 것이 정상 — 영구 억제는 오히려 결함이다.

매도 후 `pop` → 재진입 시 빈 dict → measured-move 재도달하면 TRAILING_STOP 재발화. 의도 정합.

### 한계 / 인접 이슈 (범위 밖 명시)

- BFB 재진입 쿨다운(`register_cooldown_after_exit`, 3영업일)은 현재 **고아(호출 0건, 계획 A-4 인계)** 이므로 재진입이 쿨다운 없이 일어날 수 있다. 이는 별개 행위변경 의제(domain 동반 별도 사이클). 본 변경의 `_partial_exit.pop` 은 쿨다운 활성 여부와 무관하게 정확하다(재진입이 언제 일어나든 fresh 가 맞음).
- `_breakout_first_seen`(돌파 retention 3분 dict, transient)는 메커니즘 1 의 `_reset_daily_state` L978~980 가 일일 정리하므로 `on_position_closed` 에서 중복 정리 불필요. 고아 `register_cooldown_after_exit` 내부의 `_breakout_first_seen.pop` 도 일일 리셋과 중복이라 defer 무해.

### 판정: **GO**

once-only 는 per-holding-period 의미이며 재진입 시 fresh 가 정상. `_partial_exit.pop` 단독으로 충분(쿨다운/breakout_first_seen 은 별도 경로 처리).

---

## 의제 5 — 부분 체결 (partial fill) edge (HIGH for LTV)

### 트레이더 시각

`_handle_sell_fill` 은 `total_filled >= ordered_qty`(전량) 일 때만 positions 제거 → **부분 체결 시 positions 유지 → on_position_closed 미발화 → flag 유지**. 이것이 정확하다. 부분 매도 후 *잔량을 계속 보유 중* 인 상태에서 그 잔량은 여전히:

- **LTV 상한가 모드**: 남은 주식은 여전히 익일/상한가 청산 모드여야 한다(-5% overnight 손절 + 트레일링). 만약 부분 체결에 flag 를 정리하면 다음 tick 의 check_exit_signal 이 잔량을 당일 모드(-3% + 15:20 강제청산)로 강등 → **잔여 밤샘 포지션의 청산 정책이 깨진다**. 따라서 부분 체결 시 flag 유지가 필수적으로 옳다.
- **BFB measured-move**: 측정이동 신호는 신호 발화 시점(L917)에 이미 `_partial_exit=True` 로 마킹됐고, 부분 체결 후 잔량은 ATR 트레일링(L926, `_partial_exit` 비의존)으로 청산된다. 잔량 보유 중 `_partial_exit` 유지 → 측정이동 재발화 억제가 맞다(이미 한 번 마킹). 전량 체결 시에만 pop → 재진입 시 fresh.

full-fill 한정 hook 배치가 이 "잔량 보유 중 flag 유지" 를 **자연 달성**한다 — 별도 분기 불필요.

### 판정: **GO**

부분 체결 시 잔량 보유 중 flag 유지가 청산 정책 정합상 필수. full-fill 분기(L1166 `total_filled >= ordered_qty`) 한정 hook 이 정확히 이를 만족.

---

## 정량 권고 (배선 위치 refinement)

계획안을 채택하되, 트레이더·구조 관점에서 2개 미세 보강을 권고한다.

### 권고 A (primary hook 위치) — `if pos:` 블록 *후* 배치 권장 (MEDIUM)

계획은 "L1169 `del state.positions[ticker]` 직후" = `if pos:` 내부. 그러나 전량 체결 분기에서 `pos` 가 None 인 race(체결통보 선행, L1158 "포지션 없음")가 드물게 존재한다. 이 경우 positions 는 이미 부재하지만 **flag 는 stale 일 수 있다**. discard/pop 은 멱등·안전하므로, hook 을 `if pos: del ...` 블록 *직후* (여전히 full-fill 분기 `total_filled >= ordered_qty` 내부, 예: `state.sold_today.add(ticker)` 인접)에 두면 pos 유무와 무관하게 *모든 전량 체결*에서 1회 정리되어 더 견고하다. "포지션이 닫혔다" 의 표준 시맨틱은 full-fill 자체이지 pos 객체 존재가 아니다.

- 영향: 행위 동일(정상 케이스), pos=None race 에서만 추가 정리 = 누설 차단 강화.
- 대안 유지: 계획대로 `if pos:` 내부에 둬도 *주요* 위험은 없음(재시작이 결국 정리). 단 권고 A 가 누설 봉쇄를 1단계 더 단단하게 함. 최종 채택은 team-leader 판단.

### 권고 B (구조 불변식 가드) — positions 제거 site = on_position_closed 동반 의무 (HIGH, 회귀 영구 차단)

본 변경의 안전성은 **"order_engine 의 모든 메모리 positions 제거 site 가 on_position_closed 와 1:1 대응한다"** 는 구조 불변식에 의존한다(코드 사실 3+4). 미래에 누군가 3번째 positions 제거 분기를 추가하면서 on_position_closed 를 누락하면 누설 버그가 silent 재발한다. AST/구조 가드로 "order_engine 내 `state.positions` 제거(`del`/`.pop`/`.clear`) 발생 함수는 on_position_closed 호출을 동반하거나 명시 예외 주석을 갖는다" 를 영구 가드할 것을 강권한다. 이는 cycle 167/170 의 AST 영구 가드 패턴 답습이며, 본 클러스터에서 가장 가치가 높은 SAFETY 가드다.

---

## 현 코드와의 정합성 (충돌 점검)

충돌 **없음**. 본 변경은 신규 메서드 추가(`on_position_closed` base no-op + 2 override) + order_engine 2 site 1줄 호출 + try/except 격리뿐이며, 기존 매매 의사결정 로직(positions del/sold_today/DB delete/update_trade_status/unsubscribe 순서·조건)을 변경하지 않는다.

영속 의무와의 정합:
- **cycle 142**(scheduler L1390~1394 재확립): 직교 — 본 변경은 boot/cycle142 미접촉, 매도 시 discard 만 추가. 의제 1 에서 race 없음 확인.
- **cycle 180**(VB/LTV prepare `_targets`/`_open_confirmed`/`_prev_price` clear, `_limit_up_reached` 절대 미포함): 정합 — prepare 는 transient 만 정리, 보유결합 flag 는 prepare 가 아닌 매도 hook 이 정리. 두 메커니즘 분리 유지.
- **cycle 19 `_selling` / 32 R4 보유·익일청산 절대 보호 / 38 명문화 / 147 strategy fallback / 161 price 정합 / 163 DB 격리**: 모두 무변경(`_handle_sell_fill`/`execute_sell` 본체 0 변경, 호출 1줄 + 격리만 추가). 매매 안전성 8영역 diff 0 유지.
- **20:10 `_reset_daily_state`(positions.clear)**: 변경 0 — 의도적으로 flag 미정리(밤샘 보유 종목 청산 모드 보존). 본 변경이 이를 깨지 않음(매도 시점 정리만).

---

## 반례 / 한계

1. **수동 HTS 부분매도 + actual_qty>0 + 동일종목 재등록**: balance sync 가 잔량을 fresh 로 재등록 → 당일 모드. 잔여 밤샘 의도가 있었다면 청산이 다소 조기. 단 *보수적(안전) 방향* 이고 발생 빈도 극히 낮음(알고 보유 종목을 사용자가 같은 reconciliation 윈도우에 수동 부분매도). 허용.
2. **flag 미영속의 본질 한계(범위 밖)**: `_limit_up_reached` 가 메모리 전용이라 *재시작 직후 ~ 08:00 cycle142 재확립 사이* 에 보유 중인 상한가 종목이 일시적으로 빈 flag 상태. 이는 본 변경 *이전부터 존재* 하는 기존 설계(cycle 142 가 메우는 갭)이며 본 변경이 악화시키지 않는다. 항구 해소(flag DB 영속)는 별도 사이클 의제 — 인계 권고.
3. **secondary hook 도달 불가 시 누설 잔존(이론)**: 외부 증발 포지션을 알고리즘이 *영원히 매도 시도하지 않으면* L793 미도달. 그러나 보유 종목은 항상 청산 경로(트레일링/손절/익일청산/15:20)의 평가 대상이고(cycle 38 명문화 — 보드 가드 무관 항상 작동), LTV 상한가 종목은 익일 `_execute_next_day_clear` 대상이므로 매도 시도가 보장된다 → 실질 누설 0.
4. **BFB 재진입 쿨다운 고아(A-4 인계)**: `_partial_exit` 정리와 무관하나, 쿨다운 부재로 재진입 빈도 자체가 의도보다 높을 수 있음 — 별도 행위변경 사이클(domain 동반).

---

## 후속 검증 권고 (tdd-engineer 가 추가할 SAFETY 가드)

계획의 G2-* 가드를 채택하되, 도메인 관점에서 아래를 **명시 추가/강조** 권고한다.

### 보유결합 핵심 SAFETY (HIGH)
- **G2-LTV-HELD-SAFETY (HIGH)**: LTV positions[X] + `_limit_up_reached={X}` + *매도 미발생* → `X in _limit_up_reached` 유지. cycle 180 prepare 호출 후에도 유지(prepare 미접촉 확인). 밤샘 청산모드 보존. [계획 보유 — 유지]
- **G2-LTV-PARTIAL-SAFETY (HIGH, 의제 5 — 신규 명시)**: LTV 상한가 모드 X 의 매도가 *부분 체결*(`total_filled < ordered_qty`) → positions[X] 유지 → `X in _limit_up_reached` 유지 → 다음 tick check_exit_signal 이 *익일/상한가 모드*(-5% overnight + 트레일링) 분기 진입(당일 모드 -3% 아님). 잔량 청산정책 보존 직접 검증.
- **G2-BFB-PARTIAL-SAFETY (의제 5 — 신규 명시)**: BFB measured-move 신호 발화(`_partial_exit[X]=True`) 후 *부분 체결* → positions[X] 유지 → `_partial_exit[X]` 유지 → 측정이동 재발화 억제(이미 마킹). 잔량은 ATR 트레일링 경로.

### 정리 정확성 (HIGH)
- **G2-LTV-DISCARD (HIGH)**: positions[X] + `_limit_up_reached={X}` → `_handle_sell_fill(X, full)` → `X not in _limit_up_reached`. [계획 보유]
- **G2-LTV-REBUY-FRESH (HIGH, 의제 2)**: 위 후 X 재매수 → check_exit_signal(X, -3.5%) → 당일 모드 **-3% STOP_LOSS(상한가 -5% 아님)** + check_force_clear() 에 X **포함**. [계획 보유 — 의제 2 핵심]
- **G2-BFB-POP / G2-BFB-REENTRY (의제 4)**: 매도 후 `_partial_exit` pop / 재진입 measured-move 재도달 시 TRAILING_STOP **발화(억제 아님)**. [계획 보유]

### cycle 142 순서 (HIGH)
- **G2-LTV-CYCLE142-SEQUENCE (HIGH, 의제 1 — 강화)**: 08:00 cycle 142 `_limit_up_reached.add(X)` → 보유 지속(flag 유지) → 전량 매도 → discard(X) → **그 이후 cycle 142 재발화 시 매도된 X 미재부착** 검증(순서역전 부재). freezegun 으로 08:00 add → 장중 sell → discard 순서 재현.

### secondary hook (HIGH)
- **G2-SECONDARY-COMMON (HIGH, 의제 3)**: `execute_sell` 모든 재시도 실패 + insufficient_quantity(actual_qty=0) → positions.pop(X) **직후** on_position_closed → `X not in _limit_up_reached`. 외부 증발 포지션 catch-all 검증.
- **G2-SECONDARY-CONSERVATIVE (의제 3 edge, 문서화)**: actual_qty>0 → flag 정리됨 → (재등록 시 당일 모드) = 보수적 방향. xfail 또는 명시 주석으로 "의도된 보수적 동작" 문서화(미래 오인 차단).

### 격리 + 구조 불변식 (HIGH)
- **G2-OE-ISO (HIGH)**: `on_position_closed` raise stub 주입 → `_handle_sell_fill` 전량 분기가 예외 삼키고 del positions/sold_today/delete_position/update_trade_status/unsubscribe **모두 정상 완료**. secondary hook 도 동일(positions pop/DB delete/get_balance 재조회 정상 완료). [계획 G2-OE-ISO 확장]
- **G2-OE-AST (HIGH)**: `_handle_sell_fill` 전량 분기 + `execute_sell` insufficient_qty 분기 양쪽에 `on_position_closed` Call 노드 존재. [계획 보유]
- **G2-STRUCT-INVARIANT (HIGH, 권고 B — 신규)**: order_engine 내 `state.positions` 제거(`del`/`.pop`) 를 포함하는 함수 집합 = {`_handle_sell_fill`, `execute_sell`} 로 고정, 각각 on_position_closed 호출 동반. 미래 3번째 제거 site 추가 시 가드 FAIL(누설 silent 재발 영구 차단). cycle 167/170 AST 패턴 답습.

### 매매 안전성 8영역 (계획 영속)
- `git diff -- src/engine/risk.py src/realtime/ src/auth/ src/api/order.py src/engine/session.py src/engine/scanner.py src/engine/strategy_registry.py` = **0** 직접 검증. order_engine 은 호출 1줄 + try/except 격리만(의사결정 로직 0 변경). 전략 파일은 메서드 추가만(check_exit/check_buy 본체 0 변경).

---

## 최종 안전성 판정: **조건부 GO**

5개 의제 모두 트레이더 의도·청산 정책 정합 확인. 핵심 불변식("보유 중 유지, 전량 매도 시 정리")은 cycle 142·cycle 180 과 직교하며 race 없음. secondary hook 은 외부 증발 포지션 catch-all 로 누락 봉쇄에 *필수*. 재매수 누설 경로는 본 변경(2 site)으로 구조적으로 봉쇄됨.

**조건부**의 조건 = 권고 A(primary hook 을 `if pos:` 블록 후 배치, MEDIUM, 누설 봉쇄 강화) + 권고 B(positions 제거 site ↔ on_position_closed 구조 불변식 AST 가드, HIGH, silent 재발 영구 차단) 채택. 권고 A 는 team-leader 재량(미채택해도 주요 위험 없음), 권고 B 는 강권. 인계: `_limit_up_reached` DB 영속(재시작~08:00 갭 항구 해소) + BFB 재진입 쿨다운 고아 활성화(A-4) 별도 사이클.
