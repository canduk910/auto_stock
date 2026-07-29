# P1-A Red 로그 — donchian 청산 상태 견고성 + 레이어드 청산

- 대상: `src/engine/strategies/donchian_swing.py::check_exit_signal` (L948-1008) + `recompute_held_atr` 훅
- 테스트 파일: `tests/unit/engine/strategies/test_p1a_donchian_layered_exit.py` (16 케이스)
- 명세: `_workspace/red/_behaviors_p1_20260729.md` 사이클 A
- 자문: `_workspace/domain_consult/cycle_weekly_review_20260729.md`
- 작성: 2026-07-29 (tdd-engineer)

## 근본 결함

ATR 트레일링(L995-1006)이 트레일링 폭 ATR 을 `self._candidates.get(ticker)["atr"]` 에서만 읽는다.
`_candidates` 는 매일 prepare 가 재구성 → 보유 종목이 20일 신고가 후보에서 이탈하면 `info=None`
→ `atr=0` → 트레일링 분기 영구 침묵. 하드손절만 `_entry_atr` 폴백 보유 → "백스톱만 발화"
(096770 +15.8% → -9% 반납 / 017670 +7.5% → -9.1%).

## 인터페이스 계약 (tdd-engineer 확정 → backend-dev 구현)

- **A-4 채널 데이터**: `_candidates` 와 독립인 전용 dict `self._channel_low: dict[str, int]`
  (`_entry_atr`/`_breakout_high` 선례) 에 prepare/recompute 시점 산출·저장. **on_tick KIS 호출 금지**.
  `__init__` 에 `self._channel_low: dict[str, int] = {}` 추가 + `_reset_daily_state`/on_position_closed 정리.
- **A-2 재도출**: `recompute_held_atr` (boot/저녁 훅) 에서 buy_date 이전 일봉의 20일(donchian_period)
  최고가로 `_breakout_high[ticker]` 재도출 (`_rederive_entry_atr` 선례, 같은 candles 재사용).
- **신규 DEFAULT_PARAMS**: `breakeven_promote_atr=1.5` / `channel_exit_period=10` (0=off).
  둘 다 **PARAM_RANGES 미편입** (전략 정체성 상수).
- **발화 순서** (명세): 하드손절(2ATR/승격 브레이크이븐) → 백스톱(-9%) → 시간청산 → 10일 채널 → ATR 트레일링.
  STOP_LOSS 계열이 TRAILING 계열보다 선행. 신규 분기는 기존 분기 뒤 삽입.

## RED 실행 결과 (2026-07-29)

기존 GREEN 기준선: `test_cycle_p2a2_donchian_turtle`(12) + `test_donchian_swing`(17) +
`test_donchian_swing_fail_n_days`(3) = **32 passed** (변경 없음, 무회귀).

신규 16 케이스 → **8 RED / 8 PASS**:

| 케이스 | 행위 | 상태 | RED 원인 |
|--------|------|------|----------|
| test_A1_trailing_uses_entry_atr_when_candidates_miss | A-1 HIGH | RED | `_candidates` miss → atr=0 → got `Signal.NONE` (기대 TRAILING_STOP) |
| test_A1_trailing_entry_atr_fallback_holds_above_chandelier | A-1 경계 | PASS | 경계(위) NONE — 구현 후에도 NONE 유지 가드 |
| test_A2_breakout_high_rederived_on_recompute | A-2 | RED | recompute 가 `_breakout_high` 미설정 → got `None`/0 (기대 130000) |
| test_A3_breakeven_promotion_triggers_stop_at_buy_price | A-3 | RED | 승격 로직 부재 → got `Signal.NONE` (기대 STOP_LOSS) |
| test_A3_breakeven_not_promoted_without_history | A-3 회귀 | PASS | 이력 미성립 시 NONE 보존 |
| test_A4_channel_exit_fires_below_10day_low | A-4 | RED | `AttributeError: '_channel_low'` (필드 부재) |
| test_A4_channel_exit_off_when_period_zero | A-4 opt-out | RED | `_channel_low` 부재 (구현 후 PASS 예정) |
| test_A4_channel_exit_holds_above_10day_low | A-4 경계 | RED | `_channel_low` 부재 (구현 후 PASS 예정) |
| test_A5_regression_turtle_2atr_hard_stop_preserved | A-5 | PASS | 2ATR 하드손절 보존 |
| test_A5_regression_backstop_preserved | A-5 | PASS | -9% backstop 보존 |
| test_A5_regression_position_ratio_percent_stop_byte_identical | A-5 | PASS | -7% byte 동일 보존 |
| test_A5_regression_time_based_exit_preserved | A-5 | PASS | 시간청산(011200) 보존 |
| test_A6_096770_trailing_fires_before_backstop | A-6 | RED | 트레일선(125200) 도달에도 got `Signal.NONE` (백스톱까지 방치) |
| test_new_layered_exit_keys_excluded_from_param_ranges | 가드 | PASS | 신규 키 PARAM_RANGES 미편입 |
| test_new_layered_exit_keys_in_default_params | 계약 | RED | DEFAULT_PARAMS 에 신규 2키 부재 |

RED 8 = A-1(1) + A-2(1) + A-3(1) + A-4(3) + A-6(1) + default_params(1).
PASS 8 = 경계/회귀/PARAM_RANGES 가드 (구현 후에도 GREEN 유지 의무).

## backend-dev 인계 요약

1. `__init__`: `self._channel_low: dict[str, int] = {}`.
2. `DEFAULT_PARAMS`: `breakeven_promote_atr=1.5`, `channel_exit_period=10`.
3. `check_exit_signal`:
   - ATR 트레일링 `atr` = `_candidates` miss 시 `_entry_atr.get(ticker, 0)` 폴백 (A-1/A-6).
   - 하드손절 분기에 브레이크이븐 승격 (high_since_buy ≥ buy+breakeven_promote_atr×entry_atr 이력 시
     손절선 `max(base_stop, buy_price)`, tighten-only, entry_atr 존재 시에만) (A-3).
   - 시간청산 뒤·ATR 트레일링 앞에 10일 채널 분기 (`channel_exit_period>0` AND
     `current_price < _channel_low[ticker]` → TRAILING_STOP) (A-4).
4. `recompute_held_atr`: buy_date 이전 봉 20일 최고가로 `_breakout_high` 재도출 (A-2) +
   10일(channel_exit_period) 저가로 `_channel_low` 산출 (A-4 데이터 소스).
5. `_reset_daily_state`/`on_position_closed`: `_channel_low` 정리 동행.
