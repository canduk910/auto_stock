# D4 작업 구성 — `_bought_today` 를 주문 확정 뒤에 기록 (cycle245 후속 F-10, 월요일 별도 사이클)

> 사용자 결정 2026-09-05: "D4: 월요일 별도 작업 구성". 이 문서는 월요일 착수용 명세 초안이다. 8영역(`order_engine.py`) 접촉이 필요하므로 착수 시 승인 + sha 핀 절차를 따른다.

## 1. 문제 (사실)
- 4전략이 `check_buy_signal` 안에서 **주문을 내기 전에** `self._bought_today.add(ticker)` 를 호출한다:
  - `src/engine/strategies/bull_flag_breakout.py:1093` (진입 확정 직전, `_vol_latch.pop` 직후)
  - `src/engine/strategies/vcp_breakout.py:1160` (동일 구조)
  - `src/engine/strategies/donchian_swing.py:1726` (돌파 확정) — `:1701` 은 갭 스킵 경로(의도적 '오늘은 안 산다' 표식이라 **대상 아님**)
  - `src/engine/strategies/kojiro.py:853/857/864` (세 분기 — 각각 의미 확인 필요)
- 그 뒤 `StrategyBase._apply_budget_limit` → `_apply_lot_units_cap`(cycle242) → `_apply_ratio_notional_cap`(cycle245) 관문에서 수량이 **0 이 되면 주문이 나가지 않는데** `_bought_today` 는 이미 기록돼 그날은 다시 시도하지 못한다(cycle245 §7.1 이 BFB·VCP 를 DB 에서 K_ρ=20 으로 선반영한 이유). 잔고 부족·KIS 거부(APBK)·`order_engine` 의 매수 수량 0 WARNING 경로도 같은 결과다.
- 영향: 표본이 귀한 BFB·VCP(비중 합 25%)의 **당일 표본 영구 소실**. 표적 3전략(LTV·VB·momentum)에는 `_bought_today` 가 없어 하루 3~4회 재시도(cycle245 의미 전환 2 참고).

## 2. 목표
- "오늘 샀다" 표식은 **주문이 실제로 접수(또는 체결)된 뒤**에만 남긴다. 수량 0·거부·예외 경로에서는 표식이 남지 않아 같은 날 재평가가 가능하다.
- 갭 스킵·과열 스킵처럼 **의도적으로** "오늘은 이 종목을 안 산다" 는 표식(donchian:1701)은 유지한다 — 두 의미를 분리한다.

## 3. 설계 후보 (월요일 자문 없이 결정 가능한 범위)
- **A. 콜백 훅**: `StrategyBase.on_buy_order_placed(ticker, order_no, qty)` 기본 no-op 을 두고 `order_engine.execute_buy` 가 `place_order` 성공 직후(주문번호 매핑 등록과 같은 동기 영역, `await insert_trade` 전)에 전략 인스턴스의 훅을 호출한다. 4전략은 `check_buy_signal` 의 `_bought_today.add` 를 훅으로 옮긴다. 8영역 접촉 = `order_engine.py` 1곳(훅 호출 1줄 + try/except 흡수).
  - 장점: 의미가 정확("주문이 나갔다"). 단점: 8영역 승인 필요, 동기 영역 원자성(A-ATOMIC 가드) 검토.
- **B. 관문 반환값 기반**: `check_buy_signal` 은 표식을 안 남기고, `calc_buy_quantity` 가 0 을 돌려주면 `execute_buy` 가 아예 진입하지 않으므로… 그러나 표식을 남길 주체가 없다(신호 → 주문 사이에 전략 코드가 다시 불리지 않음) → 단독으로는 불가. A 와 결합해야 한다.
- **C. 전략 내부 지연 표식**: `_bought_today_pending[ticker] = now` 로 임시 표식 후 `on_tick` 다음 회차에 `positions`/`pending_buys` 에 종목이 있으면 확정, 없으면 해제. 8영역 무접촉이지만 레이스(체결통보 선행·부분체결)와 30초 이상 지연 경로가 있어 오탐 가능. **비권고**.
- 권고 = **A**. 도메인 자문은 불필요(매매 규칙 변경이 아니라 표식 시점 정정). tdd-engineer Red: (1) 수량 0 → 표식 없음 → 같은 날 다음 틱에 재평가 가능 (2) 주문 성공 → 표식 있음 (3) KIS 거부 → 표식 없음 (4) donchian 갭 스킵 표식 유지 (5) 동기 영역 await 0 AST (6) 8영역 diff = 승인 sha 핀.

## 4. 범위·금기
- 접촉: `strategy_base.py`(훅 기본 구현), 전략 4파일(add 위치 이동), `order_engine.py`(훅 호출 1곳, **8영역 승인**). `scheduler.py`·`risk.py` 무접촉.
- 금기: 주문번호 매핑 순서(place_order 응답 직후 동기 영역) 변경 금지, `_completed_orders` race 가드 무접촉, 훅 예외가 주문 흐름을 끊지 않을 것(흡수 + WARNING 1회/일).
- D+1 서명: `[bought_today_marked] reason=order_placed` INFO(1회/종목/일) — 종전 `check_buy_signal` 시점 대비 지연 ≤ 수 초. 수량 0 경로에서 같은 종목 재평가 로그가 같은 날 2회 이상 등장하면 목표 달성.

## 5. 월요일 착수 순서
1. 사용자 승인(8영역 `order_engine.py` 1곳) → 2. domain-consult 생략, team-leader 명세 확정 → 3. Red → Green → Verify(뮤테이션·차분: 주문 성공 경로 byte 동일) → 4. 장외 배포(15:30 이후) → 5. D+1 판독.
