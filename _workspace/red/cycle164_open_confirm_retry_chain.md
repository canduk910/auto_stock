# 사이클 164 Red — 시가 확정 chain 재시도 안전망

## 결함 사례 (2026-06-18 11:03 KST)

- 09:00:05 KST `_confirm_breakout_open_prices(board="main")` 정상 발화
- 11:03 KST EC2 재기동 (사이클 163 배포 직전)
- 11:17 KST prepare 완료 (4/15종목)
- `_targets[ticker]["boards"]["main"]["open_price"]` 비어있음
- UI = "시가 대기" 표시

## 근본 원인

1. EC2 11:03 재기동 → `run_daily` 진입 `now = 11:03 KST`
2. L548 `if now <= TIME_KRX_OPEN_CONFIRM` (09:00:05) → False
3. L608 `elif now <= TIME_SCAN_START` (09:30) → False
4. L625 `if now < TIME_SCAN_START` (09:30) → False
5. L629 `if now < TIME_KRX_MAIN_BUY_STOP` (15:20) → True
6. L630 `await scan_stocks()` 호출
7. **L640 `if now > TIME_KRX_OPEN_CONFIRM: await self._confirm_breakout_open_prices()`** 호출
8. 호출 시점 prepare 미완료 = `_targets` 비어있음
9. `_confirm_breakout_open_prices` L1413 `if not targets: return` silent skip
10. 이후 prepare 완료 11:17 → `_targets` 등록되지만 시가 확정 재시도 chain 부재

## 시정 옵션 (옵션 C 통합)

- **A**: `_boot()` 영역 09:00 이후 강제 시가 확정 호출
- **B**: `_scan_loop` 5분 주기 시가 미확정 종목 자동 재시도 hook
- **C**: A + B 통합 (이중 안전망) ← **사용자 결정 채택**
- **D**: tick 자동 확정 fallback 강화 (이미 존재)

## 시정 영역 (production)

### `src/engine/scheduler.py`

1. **신규 메서드 `_confirm_breakout_open_prices_if_pending()`**:
   - VB/LTV `_targets` 영역 영구 영속에서 `_open_confirmed[ticker][active_board] == False` 인 종목 1개 이상 존재 시 `_confirm_breakout_open_prices(board=active_board)` 재시도
   - 활성 보드 = SessionTracker 위임 + 시각 기반 fallback (`_confirm_breakout_open_prices` 영속 패턴 답습)
   - 모든 종목 confirmed → silent skip (idempotent 영속)
   - 전략 자동 결정 = registry 영역 `volatility_breakout` + `long_tail_volatility` 합집합

2. **`_scan_loop` hook 추가**: `_reprepare_breakout_if_empty()` 직후 `try/except` graceful wrap

## 회귀 가드 ≥10 케이스

### `tests/unit/engine/test_cycle164_open_confirm_retry_chain.py`

- G-164-OPEN-1 (HIGH): `_confirm_breakout_open_prices_if_pending` 영역 = `_targets` 빈 종목 1개 이상 시 `_confirm_breakout_open_prices` 재시도
- G-164-OPEN-2 (HIGH): 모든 종목 confirmed → silent skip
- G-164-OPEN-3: `_scan_loop` 영역 hook 호출
- G-164-OPEN-4: 예외 graceful (다음 사이클 자연 재시도)
- G-164-OPEN-5 (HIGH): VB + LTV 양쪽 전략 영속 호출
- G-164-OPEN-6: idempotent — 동일 영역 영구 영속 2회 호출 시 결함 0

### G-SAFETY 영역

- G-164-SAFETY-1 (HIGH): `src/engine/risk.py` / `src/engine/order_engine.py` / `src/realtime/` / `src/auth/` 변경 0 AST 정적 가드
- G-164-SAFETY-2 (HIGH): 매도/익일청산/15:20 강제청산/손절 hot path 변경 0
- G-164-SAFETY-3: `DEFAULT_TRADABLE_BOARDS` 변경 0 (VB MAIN 단독 영속 + LTV 3보드 영속)
- G-164-AST-1: `_scan_loop` 영역 영구 영속 `_confirm_breakout_open_prices_if_pending` 호출 ≥ 1건 AST 정적 가드 (미래 silent 제거 영구 차단)

## 영속 의무 매트릭스

- 사이클 26 VB MAIN 단독 + 사이클 38 LTV 3보드
- 사이클 81 G-AST1 raw 보호 (영향 0)
- 사이클 88 G-REJECT graceful
- 사이클 102 G-REJECT-1 callback exception raise (영역 변경 0)
- 사이클 162 익일청산큐 영속
- 사이클 163 boot 가드 영속
- CLAUDE.md "절대 깨지 말 것" 8 영역 영속

## 매매 안전성

- scanner 단계 매수 진입 *전* 영역 한정 (사이클 38 명문화 영속)
- 매도/익일청산/15:20 강제청산/손절 hot path 무관
- risk / order_engine / realtime / auth 변경 0
