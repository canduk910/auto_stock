# 사이클 G — VB RR 개선 Phase 1 Red 로그

명세: `_workspace/red/_behaviors_cycleG_vb_rr_20260802.md`
계획: `~/.claude/plans/luminous-drifting-widget.md` (승인됨)
작성: tdd-engineer (2026-08-02)

Part A(C2 실패돌파 조기청산, 청산, default-off byte-identical) + Part B(RS/RSI 관찰-배제0, 진입, prepare 훅). 매매 8영역 diff 0. 데이트레이드 정체성 보존.

## 신규 테스트 파일 (3)

| 파일 | 파트 | 케이스 |
|------|------|--------|
| `tests/unit/engine/strategies/test_cycleG_vb_failed_breakout_exit.py` | A | 13 |
| `tests/unit/engine/test_cycleG_ta_indicators.py` | B (순수함수) | 14 |
| `tests/unit/engine/strategies/test_cycleG_vb_rs_rsi_observe.py` | B (관찰 훅) | 16 |

총 43 케이스.

## Red 실행 결과

```
34 failed, 9 passed in 0.19s
```

### 9 PASS = 의도한 GREEN 기준선 (구현 후에도 유지 의무)

- **Part A default-off byte-identical (HIGH)**: `test_disabled_no_early_exit_on_reentry` (enabled=False → 조기청산 무발화) + `test_disabled_stop_loss_still_fires` (−3% 손절 정상) + `test_disabled_next_day_clear_still_fires` (익일안전망 정상) — 현행 코드 = GREEN 기준선. backend-dev 는 이 3개를 깨지 않아야 함(활성 전 byte-identical).
- **Part A 승자 미간섭 (HIGH)**: `test_winner_above_target_no_exit` — enabled=True + target 위 유지 → 무발화.
- **Part A 카운터 리셋**: `test_counter_resets_on_recovery` — confirm_ticks−1 재이탈 후 회복 → 미발화.
- **SAFETY diff 0**: Part A `test_check_buy_signal_no_failed_breakout_token` + Part B `test_check_buy_exit_no_rs_rsi_token`.
- **PARAM_RANGES 미편입**: Part A + Part B `test_params_not_in_param_ranges` (recommendation_engine.py 에 신규 키 부재).

### 34 RED = 미구현 산출물

- **Part A 파라미터**: DEFAULT_PARAMS 3키 부재 (`failed_breakout_exit_enabled`/`_buffer_pct`/`_confirm_ticks`).
- **Part A 상태**: `_failed_breakout_count` dict 부재 + prepare clear 부재 + on_position_closed 정리 부재.
- **Part A 발화 (핵심 RED)**: `test_fires_after_confirm_ticks` / `test_single_tick_when_confirm_one` / `test_buffer_exact_threshold` — enabled=True 재이탈 confirm_ticks 연속인데 현행 코드는 조기청산 분기 부재 → NONE(기대 STOP_LOSS).
- **Part B 순수함수**: `src/engine/ta_indicators.py` 모듈 부재 → 14 케이스 전량 ImportError.
- **Part B 관찰 훅**: `_apply_rs_rsi_observe_in_prepare` 미구현 + DEFAULT_PARAMS RS/RSI 키 부재 + VB_FUNNEL_STAGES 7→9 확장 부재 + prepare 말미 호출 부재.

## 안전 기준선 (기존 VB 스위트 무회귀)

```
test_volatility_breakout.py + _board_stop_loss + cycleC3_quant + cycle148_price_filter
+ cycle180_prepare_reset + cycle201_reentry_cooldown
→ 72 passed, 1 xfailed in 0.29s
```

기존 VB check_exit/prepare/DEFAULT_PARAMS 스위트 GREEN 유지 확인.

## backend-dev 인계 인터페이스

### Part A — C2 실패돌파 조기청산 (청산)

1. **DEFAULT_PARAMS 3키 추가** (`volatility_breakout.py:71-95`, quant 키 옆):
   - `failed_breakout_exit_enabled: bool = False` (default-off)
   - `failed_breakout_buffer_pct: float = -0.5` (재이탈 임계 = target × (1+buffer/100))
   - `failed_breakout_confirm_ticks: int = 2` (연속 확인)
   - **PARAM_RANGES/INT_PARAMS 미편입** (청산 정체성 상수).
2. **상태 `self._failed_breakout_count: dict[str, int] = {}`** (`__init__`).
   - `prepare()` transient clear 지점(vb.py:144-146, `_targets.clear()` 옆)에 `self._failed_breakout_count.clear()` **추가** (테스트가 `_failed_breakout_count.clear()` 문자열 존재 검증).
   - `on_position_closed(ticker)`(vb.py:979-986)에 `self._failed_breakout_count.pop(ticker, None)` 추가.
3. **check_exit_signal 조기청산 분기** — **손절 분기 뒤(911), 익일안전망 앞(923)** 삽입:
   ```
   if params.get("failed_breakout_exit_enabled", False):
       # target_price 획득: 활성보드(_resolve_active_board) boards[board]["target_price"]
       #                    우선, top-level info["target_price"] 폴백
       if target_price > 0:
           threshold = target_price * (1 + buffer_pct / 100)
           if current_price < threshold:
               self._failed_breakout_count[ticker] += 1  # get(ticker,0)+1
               if self._failed_breakout_count[ticker] >= confirm_ticks:
                   logger.info("[vb_failed_breakout_exit] ...")
                   return Signal.STOP_LOSS
           else:
               self._failed_breakout_count[ticker] = 0  # 회복 → 리셋
   ```
   - **재사용**: `_resolve_active_board()`(728), `_targets`, `Signal.STOP_LOSS`. `_get_stop_loss_for_board` 미접촉.
   - **enabled=False 면 분기 완전 미진입** = byte-identical (G-A4 HIGH).
   - buffer 정확: target 80500, buffer −0.5 → threshold 80097.5. `<` 엄격 비교 (80098 미달, 80097 재이탈).

### Part B — RS/RSI 관찰-배제0 (진입)

4. **신규 모듈 `src/engine/ta_indicators.py`** — 순수함수 (DB/HTTP/시계 미접촉, kojiro_indicators atr/ema 재사용 금지):
   - `rsi(closes: list[float], period: int = 14) -> float | None` — Wilder 평균. delta < period → None. all-gains → 100.0, all-losses → 0.0.
   - `relative_strength(stock_closes: list[float], index_closes: list[float], period: int = 20) -> float | None` — 종목 N일 수익률 − 지수 N일 수익률(또는 비율). 데이터 부족(어느 쪽이든) → None. 종목>지수 → 양수.
   - 두 함수 모두 결정적 (동일 입력 동일 출력).
5. **DEFAULT_PARAMS RS/RSI 키 추가**:
   - `rs_filter_enabled: bool = False` / `rsi_filter_enabled: bool = False`
   - `rsi_extreme_max: int = 85` (RSI 극단>85 관찰 — 단순 >70 컷 금지)
   - **PARAM_RANGES 미편입**. (period 파라미터화는 backend 재량 — 테스트 미강제, 순수함수 default 사용 가능)
6. **관찰 훅 `_apply_rs_rsi_observe_in_prepare(self, tickers: list[str]) -> list[str]`** — `_apply_quant_filter_in_prepare`(502-604) 미러:
   - 보유 protected 스킵 (`scanner._collect_protected_tickers_for_scanner`, 사이클 32 R4).
   - 각 후보 일봉 `stock_master_daily.get_recent_daily(ticker)` (close_price 필드, DESC 정렬 — 순수함수 전 시간순 변환은 backend 책임) + **지수 KODEX200 `069500` 일봉 1회 조회** → rsi/rs 계산.
   - `_record_funnel_pipeline_step(VB_FUNNEL_STAGES[7], ...)` + `[8]` — rs/rsi 스코어 detail 기록.
   - **`return list(tickers)` 배제 0** — enabled 무관. 일봉 결측/예외 fail-open(사이클 88), 지수 미수신 graceful(RS None).
   - check_exit_signal 호출 0 + risk/order_engine import 0 (SAFETY).
7. **VB_FUNNEL_STAGES 7→9 확장** (`volatility_breakout.py:30-38`):
   - `FunnelStage(8, "상대강도 RS 관찰 — ...")` + `FunnelStage(9, "RSI 관찰 — ...")` (이름에 "RS"/"상대강도" + "RSI" 포함 의무).
8. **prepare 말미 훅 호출** (vb.py:338, `_apply_quant_filter_in_prepare` 호출 옆/뒤): `await self._apply_rs_rsi_observe_in_prepare(final_prepared_tickers)`.

### 확정 사항 요약

- **파라미터 3키(A) + 3키(B)** 전부 default-off/관찰, PARAM_RANGES 제외.
- **`_failed_breakout_count`** dict + prepare clear + on_position_closed pop.
- **check_exit 분기 위치** = 손절 뒤(911)·익일안전망 앞(923).
- **ta_indicators 시그니처** = `rsi(closes, period=14)` / `relative_strength(stock_closes, index_closes, period=20)`.
- **관찰 훅** = `_apply_rs_rsi_observe_in_prepare(tickers)`, 배제 0, 지수 069500.
- **funnel 단계** = 9단계 (step 8 RS / step 9 RSI).
