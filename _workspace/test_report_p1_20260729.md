# P1 통합·안전성 검증 리포트 (tester, 2026-07-29)

명세: `_workspace/red/_behaviors_p1_20260729.md`
Red 로그: `_workspace/red/p1a_donchian_layered_exit.md` · `_workspace/red/p1b_buy_fill_duplicate.md`
대상 변경: `src/engine/order_engine.py` (+48L) · `src/engine/strategies/donchian_swing.py` (+98L)

## 총평

**전 검증 항목 PASS. 매매 안전성 diff 0 확정. 회귀 0. B-3 미커버 영역 회귀 테스트 1건 추가.**

## 검증 항목별 결과

| # | 항목 | 결과 | 근거 |
|---|------|------|------|
| 1 | 체결통보 chain 통합 | **PASS** | H0STCNI0 26컬럼 파싱 계약 정합, B-1 가드가 파싱 무접촉 |
| 2 | B-3 CRITICAL 경로 실행 | **PASS** (테스트 추가) | fire-and-forget create_task 실발화 검증 |
| 3 | donchian recompute chain | **PASS** | 후크 순서·candles DESC 가정·params 스코프 정합 |
| 4 | 매매 안전성 diff 0 | **PASS** | 5영역 diff 완전 0, 금기 무위반 |
| 5 | 096770 승자 전환 시리즈 | **PASS** | A-6 트레일링 126,260 발화 확인 |
| 6 | 전체 백엔드 재실행 | **PASS** | 3,996 passed, 회귀 0 |

### 1. 체결통보 chain 통합 (PASS)
`handler._handle_execution`(handler.py:138) → `_on_execution` 콜백 → `OrderEngine.handle_execution_notice`(order_engine.py:849) → `_handle_buy_fill`(940) 경로 정합. B-1 멱등 가드는 `order_no`(H0STCNI0 fields[2]) 기준 `_handle_buy_fill` 최상단에서 작동하며 `price`(fields[10]=CNTG_UNPR)·`quantity`(fields[16]=CNTG_QTY) 파싱을 건드리지 않는다. 실 377450 시나리오에서 2차 통보 시 `_order_ticker`가 pop(None)되어 payload ticker 경로로 진입하지만, B-1이 `_completed_buy_orders` 체크로 positions/trade_history 뮤테이션 이전 early-return. 매도 통보 `_handle_sell_fill`·`execute_sell` diff 0.

### 2. B-3 CRITICAL 경로 실행 검증 (PASS — 회귀 테스트 추가)
미커버 영역. B-3는 `_handle_buy_fill`의 `if pos is None:` 신규 등록 분기(order_engine.py:1032)에서 `orphan_momentum_fallback=True`일 때 `asyncio.create_task(write_log("CRITICAL", ...))` 발화. `_handle_buy_fill`이 이벤트 루프 내 await되므로 create_task 정상 실행(사이클 57 V-1 패턴 정합).
**추가 테스트**: `tests/unit/engine/test_p1b_buy_fill_duplicate_race.py::test_B3_genuine_orphan_fires_critical_write_log` — 매핑 miss + trade_history miss + 미보유(진짜 고아) 시 momentum 등록 + `[buy_fill_fallback_orphan]` CRITICAL write_log가 `await_count==1`로 실발화함을 `asyncio.sleep(0)` drain으로 검증. 기존 케이스 무수정(append only).

### 3. donchian recompute chain (PASS)
`recompute_held_atr`(donchian_swing.py:663) 후크 순서: `_apply_high_since_buy_from_candles` → `_rederive_breakout_high`(728) → `_recompute_channel_low`(735) → `_rederive_entry_atr`(744). candles DESC(최신 우선) 가정은 선례 `_rederive_entry_atr`(`prior[:atr_period]`) 및 `recompute_held_atr`의 `closes[0]=prev_close`와 동일 — 신규 `_rederive_breakout_high`(`prior[:donchian_period]`)·`_recompute_channel_low`(당일 제외 후 `relevant[:channel_period]`) 모두 일관. `params["donchian_period"]`는 675행 `params=self.config.params` 스코프에서 유효(676행 기사용).

### 4. 매매 안전성 diff 0 (PASS)
`git diff --stat src/realtime/ src/auth/ src/api/order.py src/engine/risk.py` = **완전 0**.
CLAUDE.md "절대 깨지 말 것" 확인:
- 체결통보 구독(H0STCNI0/9) 무접촉
- 주문번호 매핑 동기영역 무변경 (place_order·insert_trade·`_order_qty[`·`_order_strategy[` 추가 0)
- 사이클 30 `_completed_orders` race 가드 무접촉 — 신규 `_completed_buy_orders`는 별도 목적 set, `_completed_orders`는 주석 참조만(로직 변경 0)
- `_reset_daily_state`는 `_completed_buy_orders.clear()` 동행 추가만(기존 제거 로직 0)
- 매도 경로·donchian 매수 경로(`check_buy_signal`/`prepare`/`_scan_universe`/`calc_buy_quantity`) diff 0

### 5. 096770 승자 전환 시리즈 (PASS)
`test_A6_096770_trailing_fires_before_backstop` 실행 확인. buy 117,300 / entry_atr 5,300 / 고점 135,800:
- 브레이크이븐 승격: 고점 135,800 ≥ 117,300+1.5×5,300=125,250 성립 → 손절선 117,300으로 tighten. 현재가 125,000 > 117,300이라 미발화(정상)
- 백스톱 -9%=106,743 미도달
- 트레일링: 135,800−1.8×5,300=**126,260**, 현재가 125,000 < 126,260 → TRAILING_STOP 발화
백스톱 이전 발화 = 승자 전환. 우선순위(STOP_LOSS 계열 선행 → 채널 → 트레일링) 정합.

### 6. 전체 백엔드 재실행 (PASS)
`pytest tests --ignore=tests/integration` = **3,996 passed** (기준선 3,995 + 신규 B-3 1건), 8 skipped, 326 xfailed, 12 xpassed. xfail/xpass는 전부 기존 의미 전환 마커(사이클 66 K-2 계열). 회귀 0.
신규 P1 스위트 격리: 20 PASS (p1a 13 + p1b 7). B-3 추가 후 p1b 8 PASS.
관련 baseline (donchian/order/execution/swing k-필터): 262 passed.

## 발견 결함
없음. 구현이 명세대로 정확하며 안전성 금기 위반 0.

## 추가 테스트
- `tests/unit/engine/test_p1b_buy_fill_duplicate_race.py::test_B3_genuine_orphan_fires_critical_write_log` (tester 직접 append, 기존 케이스 무수정)

## tdd-engineer 인계
추가 회귀 의뢰 없음 (B-3 회귀 가드는 통합 검증 중 tester가 직접 확보).

## 주의 (P1 범위 외 — team-leader 인지 필요)
현재 working tree에 P1 무관 변경 혼재: `src/config.py` · `src/engine/log_analysis_engine.py` · `.env.example` · `tests/unit/engine/test_log_analysis_openai_meta.py` · `_workspace/test_index.yaml`. log_analysis OpenAI 메타 별도 작업 스트림(추정). **P1 커밋 시 분리 권고** — P1 산출물은 `src/engine/order_engine.py` + `src/engine/strategies/donchian_swing.py` + 신규 테스트 2건(`test_p1a_donchian_layered_exit.py` · `test_p1b_buy_fill_duplicate_race.py`)에 한정.

## 최종 수치
- 전체 백엔드: 3,996 passed / 8 skipped / 326 xfailed / 12 xpassed / 0 failed
- 안전성 5영역 diff: 0
- 신규 테스트: +1 (B-3 회귀 가드)
