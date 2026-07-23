# 자문 — NXT 프리 익일청산 지정가 미체결 → stale `_selling` 방치 엣지케이스 (매도 hot path)

## 질문 요약
VB 익일청산 08:00 NXT 프리 지정가(open−1tick) 매도가 얇은 유동성으로 미체결 만료(ccld=0/rmn=0).
결과 두 결함: (1) 갭<임계 NXT 지정가 분기가 `_pending_next_day_clear` 미등록 → 09:00 KRX 드레인 폴백 부재.
(2) NXT 지정가는 `place_order` 성공 후 `_selling` 유지(체결통보 대기) → 미체결 만료 시 KIS 통보 없어 `_selling` 영구 잔존
→ 이후 15:20 강제청산/드레인/**손절(risk.on_tick)** 전부 차단. double-sell 레이스 없이 robust 하게 보강하는 최소 설계?

## 트레이더 시각

### 결함의 진짜 심각도 — Defect 2 가 손절까지 죽인다
- `risk.py:128` — `if ticker in self.order_engine._selling: continue`. 즉 stale `_selling` 은 15:20 강제청산만이 아니라
  **on_tick 의 check_exit_signal (손절/트레일링 포함) 을 종일 억제**한다. 종목이 -X% 로 무너져도 손절 신호가 평가조차 안 됨.
  금호타이어는 "당일 청산 실패 + 익일 이월" 로 끝났지만, 급락장이었으면 무방비 오버나이트가 된다. → Defect 2 는 HIGH.
- `_selling.discard` 는 (a) `_handle_sell_fill` 체결통보, (b) execute_sell 내부 거부/예외 early-return 에서만 발생.
  NXT 지정가 미체결 **만료는 어느 경로에도 안 걸림** (place_order 는 성공했고, 통보는 안 옴). 구조적 leak.

### NXT 프리 지정가 조기청산의 손익 비대칭 — 애초에 나쁜 거래
- 얇은 NXT 프리에서 전량을 open−1tick 지정가로 매도 → 매수호가 두께가 없으면 그냥 안 걸린다.
  금호 실측이 정확히 이 케이스: +3% 로 떴지만 6250 에 받아줄 잔량이 없어 미체결. **그 +3% 는 종이 이익**이었다
  (그 가격·그 수량으로 실제 나갈 수 없음).
- 즉 "갭<임계 (약하게 뜨거나 눌린 시가) → NXT 프리 지정가로 조기 탈출" 은 **성공확률 낮고(얇은 호가) 실패시 대가 큰(stale
  selling → 종일 방치 → 익일 이월 + 손절 마비)** 전형적 나쁜 손익비 트레이드.
- 반대편: 조기탈출이 유의미하려면 NXT 프리 매수호가가 두꺼워야 하는데, 그런 종목이면 09:00 KRX 시장가로도 잘 나간다.
  → 조기청산으로 얻는 실이익은 대부분의 종목에서 미미하고 불확실.

### double-sell 레이스의 정체 (Q1)
- 레이스는 "08:00 NXT 주문을 낸다 + 09:00 드레인이 또 판다" 두 청산 경로가 공존할 때만 생긴다.
  08:00 주문을 안 내면 레이스 자체가 소멸(단일 경로).
- **주의: 현재의 stale `_selling` 은 이 레이스를 오히려 막고 있다.** 08:59:59 체결 → 통보 09:00:06 인 경우,
  09:00:05 드레인은 `_selling` 이 아직 살아있어 execute_sell 이 조기 return(차단) → 통보 도착 후 자연 정리.
  **fix(B) 로 `_selling` 을 맹목 discard 하는 순간 이 보호가 사라지고 double-sell 이 생긴다.**
- 또 하나: NXT 지정가 day-order 가 프리 마감에 만료되지 않고 NXT 연속세션(09:00~)으로 **살아 넘어갈 가능성**.
  살아있으면 KRX 시장가 재매도 = 양 거래소 동시 체결 = 진짜 이중매도(oversell). 금호 rmn=0 은 만료를 시사하나
  KIS 가 이를 항상 보장한다고 문서로 확정된 바 없다 → 벽시계만 믿고 discard 하면 안 됨.

## 정량 권고

### 권고 Tier 1 (채택 권장, 최소 blast radius) — NXT 프리 지정가 제거, 09:00 KRX 단일 청산
`_execute_next_day_clear` 의 갭<임계 분기(scheduler.py:1438~1452)를 **execute_sell(limit) 대신
`_pending_next_day_clear.add((ticker,strategy_id))` + `save_pending_ndc(reason="nxt_underthreshold")`** 로 교체.
바로 위 두 분기(`nxt_not_tradable` L1340, `nxt_open_missing` L1383)가 이미 쓰는 정확히 같은 패턴을 재사용.

- Defect 1 해소: 드레인이 잡는다.
- Defect 2 해소: NXT 주문을 안 내므로 `_selling` 을 애초에 세팅하지 않는다 → leak 원천 소멸.
- Q1 레이스 해소: 08:00 청산 주문이 없으니 09:00 드레인과 경합할 대상이 없다. **단일 경로 = 레이스 0.**
- 대가: 갭<임계(예: +3%) 종목의 NXT 프리 조기탈출 포기. 위 손익비 분석상 대부분 미미·불확실한 이익 포기 → 수용 권고.
  단, 이 "포기" 는 트레이더 판단 영역이라 team-leader/사용자 확정 필요.

### 권고 Tier 2 (조기탈출 가치를 지키려면) — A + 잔고 재대조 드레인 (+ cancel-then-resell)
NXT 프리 지정가를 **그대로 내되** 동시에 `_pending_next_day_clear.add` 등록(fix A). 드레인은 재매도 전에:
1. (NXT day-order 잔존 가능성 대비) 저장해둔 NXT order_no 로 **cancel_order 선행** — 살아있으면 취소, 이미 만료면 무해.
2. `get_balance()` 로 **실제 보유수량 재조회** → `actual_qty` 만 KRX 시장가 재매도. `actual_qty==0` (NXT 가 이미 체결) → 재매도 skip + 정리.
3. 재매도 직전에만 `_selling.discard(ticker)` — **잔고로 보유 확인한 뒤에만** 덮어쓴다(맹목 discard 금지).

- double-sell 방지의 핵심은 `_completed_orders` 가 아니다(그건 반대 방향 레이스=통보 선행용). **권한 있는 보유 재확인**(잔고 or 해당 order rmn_qty)이 정답.
- 잔고 반영지연 리스크: 08:59:59 체결이 09:00:05 잔고에 반영 안 될 확률은 낮으나 0 아님 → order_no 기반 `rmn_qty` 조회가 더 정밀(단 order_no 를 pending 튜플에 실어야 하는 추가 plumbing). 잔고 재조회로 충분하다고 판단하되, cancel 선행이 이중 안전.
- 대가: 드레인에 잔고/취소 왕복 + plumbing → Tier 1 보다 blast radius 큼.

### 권고 (Tier 무관 공통) — stale `_selling` 재대조를 hot path 밖에
Defect 2 의 "손절 마비" 는 이 버그 밖에서도 재발 가능한 지뢰(예: 정상 시장가 매도인데 체결통보 WebSocket 유실).
방어선을 execute_sell 코어(레이스 가드/매핑 동기영역)에 넣지 말고 **hot path 밖**에:
- 기존 15분 `_sync_positions_from_balance` 에 대조 훅: `_selling` 각 ticker 에 대해 (열린 매도주문 없음 AND 보유 잔존) 이면 `_selling.discard` → 다음 on_tick 부터 손절 재평가. off hot path, 저위험.
- 또는 `_selling_since: dict[ticker, datetime]` 를 두고 관대한 TTL(예: 5분 — 시장가 매도는 초 단위 체결이라 안전). 단독으론 NXT 잔존/이중거래소를 못 막으므로 **Tier 1/2 의 보조**로만.

### 파라미터/사실 근거
- gap_up_threshold 기본 10.0 (scheduler.py:1370). 금호 +3% 는 이 아래 → NXT 지정가 분기 진입 확인.
- 드레인(`_drain_pending_next_day_clear`)은 이미 KRX 시장가 재매도 + DB pending DELETE + 구조화 로그를 갖춘 검증된 경로 → Tier 1 은 새 코드가 아니라 **기존 안전망에 배선만 추가**.

## 현 코드와의 정합성
- **충돌 없음 — Tier 1 은 CLAUDE.md 안전규칙과 정렬**:
  - "익일청산 갭률은 open_price, high_since_buy 폴백 금지, 시가/조건 불명이면 `_pending_next_day_clear` 보류 후 09:00 KRX 시장가" — Tier 1 이 이 규칙을 갭<임계에도 **확장 적용**하는 셈. 오히려 규칙 일관성 강화.
  - `tradable_boards 는 매수 진입 전용` / 매도·손절 항상 작동 — Defect 2 시정은 이 규칙의 실효 회복(stale `_selling` 이 손절을 막던 위반 상태 해소).
  - `_pending_next_day_clear` 영속(save/delete_pending_ndc, 사이클 162) 패턴 재사용 → EC2 재기동 메모리 휘발 방어도 자동 상속.
- **주의 — VB `tradable_boards=("main",)` / 15:20 일괄청산 정책 불변**: Tier 1 은 POST_NXT 추가나 15:20 정책 변경이 전혀 아님. 08:00 NXT 프리 지정가 매도만 09:00 KRX 로 미룸.
- fix(B) 맹목 discard 안(사용자 후보 B 원안)은 **CLAUDE.md 매도 레이스 가드 정신과 충돌** → 반드시 잔고 확인 후 discard 로 한정.

## 반례 / 한계
- Tier 1 반례: NXT 프리 매수호가가 실제로 두꺼운 유동종목이 갭<임계로 뜬 경우, 09:00 KRX 까지 1시간 노출 + 그 사이 시가 훼손 가능. (완화: 그런 종목은 09:00 KRX 시장가로도 잘 빠짐. 손실은 대개 제한적.)
- Tier 2 반례: NXT day-order 가 만료가 아니라 살아 넘어가고, cancel 이 체결과 레이스(취소 직전 체결)면 잔고 재조회가 이를 흡수해야 함(취소 실패 → 잔고 0 → skip 로 자연 처리). 즉 cancel 은 best-effort, 최종 판단은 잔고.
- 공통: 잔고 재조회는 KIS 반영지연에 이론상 취약. order_no rmn_qty 조회가 최정밀이나 plumbing 비용.
- 데이터 한계: NXT day-order 의 세션 경계 만료 정책을 KIS 정본으로 확정하지 못함 → tester 가 운영/모의로 검증 권고.

## 후속 검증 권고 (tdd-engineer / tester)
1. (tdd) 갭<임계 → execute_sell(limit) 호출 0건 + `_pending_next_day_clear` 등록 + `save_pending_ndc` 호출 (Tier 1).
2. (tdd) 09:00 드레인이 pending 을 KRX 시장가로 청산 (기존 드레인 테스트에 신규 사유 케이스 추가).
3. (tdd) 회귀: 갭>=임계 트레일링 분기 불변 + 정상 익일청산(nxt_tradable=False/nxt_open_missing) 분기 불변 + 15:20 강제청산이 `_selling` 없어 정상 접수.
4. (tdd) Defect 2 재대조: `_selling` 잔존 + 보유 + 열린주문 없음 → 대조 훅이 discard → on_tick 손절 재평가 재개 (hot path 밖 훅).
5. (tester) double-sell: (Tier 2 채택 시) NXT 08:59:59 체결 + 드레인 09:00:05 → **총 매도 수량 = 보유수량**(초과매도 0) 검증. NXT day-order 세션경계 만료/잔존 여부 모의·운영 관찰.
6. (tester) KIS MCP 로 NXT 지정가 미체결 만료 시 통보(체결/거부) 발신 여부 정본 확인 — `_selling` leak 전제 재확인.
