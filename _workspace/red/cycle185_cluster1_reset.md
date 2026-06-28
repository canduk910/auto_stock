# 사이클 185 클러스터 ① Red — 전략 인스턴스 상태 일일 미리셋 (strat-2~5)

승인 계획 `~/.claude/plans/hazy-prancing-cookie.md` + domain-expert 자문
`_workspace/domain_consult/cycle185_position_closed_cleanup.md`.

**Red 단계 — 실패 테스트만 작성, production 미변경.** Green = backend-dev.

## 결함 (왜)

`scheduler._reset_daily_state()`(20:10 정산 후, scheduler.py L3804~3930)는 registry 순회
(L3806~3818)에서 `strategy.state.*` 만 비우고 **전략 인스턴스 자신의 dict/set 필드는 미참조**.
전략은 프로세스 생애 싱글톤 → 영업일 가로질러 누적. 코드리뷰 cluster ① strat-2~5 4건 잔존.

| 결함 | 필드 | 분류 | 오작동 |
|------|------|------|--------|
| strat-4 momentum | `_prev_prdy_rate` (L61) | transient | 익일 첫 틱이 전일값과 비교 → 갭상승 거짓 돌파 즉시 매수 |
| strat-3 BFB | `_breakout_first_seen` (L132) | transient | `_reset_daily_state()`(L978) **고아**(호출 0건) → retention 가드 우회 |
| strat-2 LTV | `_limit_up_reached` (L113) | 보유결합 | 재매수 종목 전일 상한가 모드 잔존 → 15:20 청산 누락 + 손절 -5%/-3% 오적용 |
| strat-5 BFB | `_partial_exit` (L128) | 보유결합 | 재진입 종목 measured-move 익절 영구 억제 |

**두 메커니즘 분리**: transient(매수 전 전용) = 20:10 일괄 리셋. 보유결합(청산 모드) =
밤샘 보유(DB 영속+07:50 boot+cycle142 08:00 재확립)라 일괄 리셋 금지 → **전량 매도 체결 시점 정리**.

## Green 목표 (테스트가 가정하는 동작)

- **메커니즘 1**: `StrategyBase._reset_daily_state()` 기본 no-op + momentum override(`_prev_prdy_rate.clear()`)
  + BFB 기존 L978 불변(이제 호출). scheduler 등록 순회 L3818 직후 per-strategy `try/except` 배선.
- **메커니즘 2**: `StrategyBase.on_position_closed(ticker)` 기본 no-op + LTV override(`_limit_up_reached.discard`)
  + BFB override(`_partial_exit.pop`). order_engine 2 site — `_handle_sell_fill` 전량 분기 `if pos:` 블록 후
  (L1169 직후) + `execute_sell` insufficient_quantity reconciliation(L793) 직후, 각 `try/except` 격리.

## 현재 코드 FAIL 근거 (직접 grep)

- `grep on_position_closed src/engine/` = **0건** → 매도 시 보유결합 flag 미정리 (G2-* discard 가드 FAIL).
- scheduler `_reset_daily_state` 에 `strategy._reset_daily_state()` Call 노드 0건 → transient dict 미리셋
  (G1-MOM-RESET / G1-BFB-RESET / G1-WIRING-AST FAIL).
- order_engine positions 제거 site 2곳(L793 pop / L1169 del) 에 on_position_closed 동반 0건 (G2-OE-AST / G2-STRUCT-INVARIANT FAIL).
- BFB `_reset_daily_state`(L978) 정의는 있으나 호출처 0건 = 고아 → G1-BFB-RESET FAIL.

## 가드 → 결함 매핑

### 메커니즘 1 (`test_cycle185_cluster1_reset.py::TestMechanism1DailyReset`)
- **G1-MOM-RESET** (Red): seed `_prev_prdy_rate[X]=28.0` → `scheduler._reset_daily_state()` → `=={}` +
  익일 첫 틱 29.5% → check_buy_signal NONE(기록만). 현재 FAIL = dict 미클리어 → 첫 틱 즉시 BUY.
- **G1-MOM-LEAK-CONTROL** (특성/문서, 양쪽 PASS): 리셋 미발생 시 seed 잔존 → 첫 틱 즉시 BUY(거짓 돌파 동기 문서화).
- **G1-BFB-RESET** (Red): `_breakout_first_seen[X]=어제` → reset → `=={}`. 현재 FAIL = L978 고아.
- **G1-WIRING-ISO (HIGH)** (Red): `_reset_daily_state` raise stub 전략 first 주입 → (a) 예외 삼킴
  + raise stub 호출됨(배선 존재) (b) 다른 전략 state.positions clear (c) `_pending_next_day_clear` clear.
  현재 FAIL = raise stub 미호출(배선 부재). NAIVE green(try/except 누락) 시 (b)/(c) FAIL.

### 메커니즘 2 (`test_cycle185_cluster1_reset.py::TestMechanism2OnPositionClosed`)
- **G2-LTV-DISCARD (HIGH)** (Red): LTV positions[X]+`_limit_up_reached={X}` → 전량 매도 → `X not in _limit_up_reached`.
- **G2-LTV-REBUY-FRESH (HIGH)** (Red): 위 후 X 재매수 → check_exit(-3.5%) → 당일 모드 STOP_LOSS(-5% 아님)
  + check_force_clear 에 X 포함. 현재 FAIL = stale flag → 상한가 모드 → -3.5%>-5% NONE + force_clear 제외.
- **G2-LTV-HELD-SAFETY (HIGH SAFETY)** (양쪽 PASS): positions[X]+flag, `scheduler._reset_daily_state()` →
  `X in _limit_up_reached` 유지. mechanism1 이 보유결합 flag 절대 미접촉(밤샘 청산모드 보존) 가드.
- **G2-LTV-PARTIAL-SAFETY (HIGH, domain-expert 신규)** (양쪽 PASS): 부분 체결 → positions[X] 잔량 +
  `X in _limit_up_reached` 유지 + 잔량 check_exit -3.5% → NONE(-5% overnight 보존, 당일 -3% 아님).
- **G2-LTV-CYCLE142-SEQUENCE (HIGH, freezegun)** (Red): 08:00 add → 보유 flag 유지 → full 매도 → discard
  → 매도된 X 미재부착. 순서역전 부재.
- **G2-BFB-POP** (Red): `_partial_exit={X:True}` → 전량 매도 → `X not in _partial_exit`.
- **G2-BFB-REENTRY** (Red): 위 후 X 재매수 + measured-move 도달 → TRAILING_STOP 발화. 현재 FAIL = stale True → 억제(NONE).
- **G2-BFB-PARTIAL-SAFETY (domain-expert 신규)** (양쪽 PASS): 부분 체결 → `_partial_exit[X]` 유지(억제 보존).
- **G2-SECONDARY-COMMON (HIGH)** (Red): `execute_sell` insufficient_quantity(actual_qty=0) reconciliation(L793)
  → positions 강제 pop + on_position_closed discard. 현재 FAIL = pop 만, flag 잔존. 수동 HTS 매도 catch-all.
- **G2-OE-ISO (HIGH)** (Red): on_position_closed raise stub → `_handle_sell_fill` 전량 분기 (배선) 호출됨
  + (예외 삼킴) del positions/sold_today/DB delete/update/unsubscribe 모두 완료. 현재 FAIL = 미호출.

### AST (`test_cycle185_cluster1_ast.py`)
- **G1-WIRING-AST** (Red): scheduler `_reset_daily_state` FunctionDef 에 `<name>._reset_daily_state()`
  Call 노드(receiver=Name) 존재. source 텍스트 스캔 금지 — AST 노드(사이클 167/179).
- **G2-OE-AST** (Red): `_handle_sell_fill` + `execute_sell` 양쪽 FunctionDef 에 `on_position_closed` Call ≥1.
- **G2-STRUCT-INVARIANT (HIGH, domain-expert 권고 B)**: order_engine.py 에서 `state.positions` 제거
  (`del ...positions[...]` / `...positions.pop(...)`) 직접 포함 함수 집합 == `{_handle_sell_fill, execute_sell}`
  (구조 불변, 양쪽 PASS = 3번째 site 추가 영구 차단) + 각 함수에 on_position_closed 동반 의무(Red).

## 기존 테스트 영향 (의미 전환 유무)

- **의미 전환 0건.** 메커니즘 1/2 모두 **신규 메서드 추가 + 배선 1줄** (기존 메서드 본체 0 변경).
- `_handle_sell_fill` 회귀(cycle147/161/163) / `execute_sell` 회귀(cycle55/100/b1) / scheduler
  `_reset_daily_state` 회귀(cycle61) = on_position_closed/`_reset_daily_state` 호출이 1줄 추가될 뿐
  기존 단언(positions del/sold_today/DB/update/unsubscribe 순서·조건) 불변 → Green 시 회귀 0 예상.
- BFB 기존 `_reset_daily_state`(L978) = 호출처 0건 고아였으므로 본체 테스트 부재 → 신규 G1-BFB-RESET 가 첫 가드.

## 매매 안전성 (Green 시 검증 의무 — backend-dev/tester)

- `git diff -- src/engine/risk.py src/realtime/ src/auth/ src/api/order.py src/engine/session.py
  src/engine/scanner.py src/engine/strategy_registry.py` = 0.
- order_engine.py = on_position_closed 호출 1줄 + try/except 격리만 (매도/익일청산/15:20/손절 의사결정 불변).
- 전략 파일 = 메서드 추가만. 사이클 19/32 R4/38/142/147/161/163 영속.
