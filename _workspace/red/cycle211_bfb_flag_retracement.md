# 사이클 211 (2026-07-15) — BFB `flag_retracement_max` 0.382→0.5 완화 (Red)

## 배경
Phase B funnel: BFB 폴/플래그 병목. 오프라인 스윕 — flag_retracement_max 0.382→0.5 =
폴+플래그 통과 3→10 (3.3배). pole_min_return DB 20→15 는 이미 지혈 (코드 default 15).
flag_volume_ratio 0.6 안전장치 유지. 사이클 198 (flag_lookback_min 3→2) 답습 — 단일
파라미터 완화 + 안전장치 불변.

## 변경 대상 (backend-dev Green — 구현 금지, Red 만)
- `src/engine/strategies/bull_flag_breakout.py` DEFAULT_PARAMS
  `"flag_retracement_max": 0.382` → **0.5** + 사이클 211 근거 주석.
  `pole_min_return`(15.0) / `flag_volume_ratio`(0.60) / `pole_max_red_ratio`(0.45) 불변.

## 검출 로직 (`_detect_pole_and_flag_detailed` L434~)
- `retracement_max = p["flag_retracement_max"]` — 플래그 조정폭이 폴 폭의 최대 허용 비율.
  `actual_retracement = (pole_high - flag_low) / pole_width`, `pole_width = pole_high - pole_start`.
  `actual_retracement > retracement_max` 초과 시 `fail_stage="flag_retracement"` 탈락.
- `flag_vol_ratio = p["flag_volume_ratio"]`(0.60) — `flag_avg >= pole_avg × 0.60` 이면
  `fail_stage="volume_contraction"` 탈락 (거래량 수축 안전장치).
- `min_return = p["pole_min_return"]`(15.0).
- 실패 시 `_FAIL_STAGE_ORDER` 최고 rank 조합 사유 보고 (flag_retracement=3 / volume_contraction=4).

## 회귀 가드 (Red — 현재 코드 flag_retracement_max=0.382 에서)
- **G-211-1** (`test_g211_1_flag_retracement_max_is_0_5`): `DEFAULT_PARAMS["flag_retracement_max"] == 0.5`.
  → 현재 코드(0.382) FAIL. Green 후 PASS.
- **G-211-2 (HIGH)** (`test_g211_2_mid_retracement_detected_only_with_0_5`):
  합성 candles — 폴(+30%) 후 플래그 조정폭 ≈ 폴폭의 45% (0.382 초과, 0.5 이내) +
  거래량 수축 통과. `flag_retracement_max=0.382` 주입 시 fail_stage="flag_retracement"
  탈락(None) → `0.5` 주입 시 result != None 검출. DEFAULT 대조 = 현재 코드(0.382) None → Red.
- **G-211-3 (안전장치 불변)** (`test_g211_3_volume_contraction_still_guards` +
  `test_g211_3_flag_volume_ratio_and_pole_min_return_unchanged`):
  ① 거래량 수축 미달 플래그(조정폭 0.45, retr 0.5 통과 범위)는 `flag_retracement_max=0.5`
     여도 fail_stage="volume_contraction" 탈락 (0.382/0.5 양쪽 불변식, Red 아님).
  ② DEFAULT_PARAMS `flag_volume_ratio == 0.60` + `pole_min_return == 15.0` +
     `pole_max_red_ratio == 0.45` 불변.
- **G-211-4 (SAFETY/AST)** (`test_cycle211_ast_default_params_scope.py`):
  ① donchian/vcp DEFAULT_PARAMS 에 `flag_retracement_max` 키 부재 (BFB 전용).
  ② donchian/vcp 대표 키 불변 diff 0 (AST 토큰 기반, 사이클 198/180 답습).
  ③ BFB `flag_retracement_max` 키 존재 self-test.
  ④ `check_exit_signal` 본체 불변 — flag_retracement 관련 청산 로직 부재 (매수 진입 전용).

## 의미 전환
- `test_cycle198_bfb_flag_lookback_min.py::test_d_adjacent_safety_params_unchanged`
  L242-244 `dp["flag_retracement_max"] == 0.382` 단언 → `== 0.5` 갱신 (사이클 211 완화 반영).
- `test_bull_flag_breakout.py:81` `p["flag_retracement_max"] == 0.382` → `== 0.5` 갱신.

## Red 유효성 (production 미변경 상태)
- G-211-1 (e 계열): FAIL — 현재 0.382 ≠ 0.5.
- G-211-2 (a 계열): FAIL — DEFAULT(0.382) 에서 mid-retracement(0.45) 셋업 None.
- G-211-3: PASS (불변식 — flag_volume_ratio/pole_min_return 은 이 사이클 무변경, 현재 값 유지).
  단, `flag_volume_ratio`/`pole_min_return`/`pole_max_red_ratio` 단언은 현재 값과 일치 → PASS.
- G-211-4: PASS (donchian/vcp 무변경 + BFB 키 존재 + check_exit 불변 = 전부 현재 상태 참).
- 의미 전환 2건: 현재 코드에선 PASS(0.382) → Green 후 0.5 로 갱신해야 PASS 유지.
  Red 단계에서 갱신하면 현재 코드에서 FAIL (예상된 Red).

## 산출물
- `tests/unit/engine/strategies/test_cycle211_bfb_flag_retracement.py` (G-211-1/2/3).
- `tests/unit/ast/test_cycle211_ast_default_params_scope.py` (G-211-4).
- 의미 전환 2건.
- 합성 폴/플래그 = `test_cycle198_bfb_flag_lookback_min.py` + `_detect_pole_and_flag_detailed` 참고.
