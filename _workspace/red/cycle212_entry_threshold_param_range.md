# cycle212 — 진입 임계 buy_threshold(momentum)·donchian_period(donchian) PARAM_RANGES 제외

**명세 출처**: team-leader 사이클 212 D 지시 (백로그 D — 208/209 논리: 진입 임계 = 전략 정체성 상수, AI 자동튜닝 부적합)
**선례**: 사이클 198 (BFB flag_lookback PARAM_RANGES 밖) / 208 (donchian box 2키 제외) / 209 (max_breakout_extension_pct 제외)
**행위**: `recommendation_engine.PARAM_RANGES` 에서 `buy_threshold`/`donchian_period` 제거 + `INT_PARAMS` 에서 `donchian_period` 제거 → AI 자동튜닝 대상에서 진입 임계 배제.

## 변경 대상 (backend-dev Green — 구현 금지, Red 범위 아님)
`src/engine/recommendation_engine.py`:
- PARAM_RANGES 에서 `"buy_threshold": (0.0, 30.0),`(L68) 제거
- PARAM_RANGES 에서 `"donchian_period": (10, 60),`(L93) 제거
- INT_PARAMS 에서 `"donchian_period",`(L114) 제거 (buy_threshold 는 float — INT_PARAMS 무관)

## 회귀 가드 (Red — production 미변경 시 FAIL)
신규 파일:
- `tests/unit/engine/test_cycle212_entry_threshold_param_range.py`
  - **G-212-1**: `PARAM_RANGES` 에 `buy_threshold` 부재 → 현재 잔존 = FAIL
  - **G-212-2**: `PARAM_RANGES` 에 `donchian_period` 부재 → 현재 잔존 = FAIL
  - **G-212-3**: `INT_PARAMS` 에 `donchian_period` 부재 → 현재 잔존 = FAIL
  - 불변식(PASS 유지): 나머지 PARAM_RANGES/INT_PARAMS 키 잔존 + 208/209 제외분(box/max_box/max_breakout_extension) 부재 유지 + INT_PARAMS ⊆ PARAM_RANGES 규약
- `tests/unit/ast/test_cycle212_ast_entry_threshold.py`
  - **G-212-4 (AST)**: PARAM_RANGES/INT_PARAMS dict/set 리터럴에 `buy_threshold`/`donchian_period` 문자열 키 부재 → 현재 잔존 = FAIL (docstring/주석 false-positive 차단, 209 AST 패턴 답습)

## 의미 전환 (사이클 66 K-2) — 기존 테스트 부재로 갱신
`buy_threshold`/`donchian_period` 를 PARAM_RANGES/INT_PARAMS 에 있다고 단언·의존하는 기존 테스트를 제거 후 정합으로 갱신:

- `tests/unit/engine/test_recommendation_param_ranges.py`
  - `_NEW_RANGE_KEYS` / `_NEW_INT_KEYS` 에서 `donchian_period` 제거
  - `test_int_params_includes_donchian_and_long_ma_period` → `long_ma_period` 단독
  - `test_validate_recommendations_rejects_out_of_range_new_keys` → donchian_period 제거, WARNING 3→2
  - `test_validate_recommendations_casts_donchian_period_to_int` → donchian_period 는 이제 비화이트리스트 = 드롭됨 단언
  - `test_existing_validate_flow_still_works` → buy_threshold 는 이제 드롭됨 + 화이트리스트 키(position_ratio) 통과 단언
- `tests/unit/engine/test_recommendation_engine_smoke.py`
  - `test_param_ranges_present_and_bounded` expected_keys 에서 `buy_threshold` 제거
  - `test_validate_recommendations_filters_unknown_key` → buy_threshold 드롭됨(화이트리스트 아님) + 화이트리스트 키 통과로 대체
  - `test_validate_recommendations_clamps_out_of_range` → buy_threshold 대신 화이트리스트 float 키(k_value_krx_main)로 범위 밖 검증

검증 소재: `_validate_recommendations` 은 `key not in PARAM_RANGES` → debug 로그 후 드롭 (WARNING 아님). ghost_param 과 동일 취급.

## Red 실행 결과 (production 미변경)

4 파일 (신규 2 + 의미 전환 2) 합산: **8 FAIL / 18 PASS**

FAIL (Green 이 뒤집을 8건):
- `test_cycle212_entry_threshold_param_range.py::test_g212_1_buy_threshold_absent_from_param_ranges`
- `test_cycle212_entry_threshold_param_range.py::test_g212_2_donchian_period_absent_from_param_ranges`
- `test_cycle212_entry_threshold_param_range.py::test_g212_3_donchian_period_absent_from_int_params`
- `test_cycle212_ast_entry_threshold.py::test_g212_4_param_ranges_literal_absent`
- `test_cycle212_ast_entry_threshold.py::test_g212_4_int_params_literal_absent_donchian_period`
- `test_recommendation_param_ranges.py::test_int_params_includes_donchian_and_long_ma_period` (의미 전환)
- `test_recommendation_param_ranges.py::test_validate_recommendations_casts_donchian_period_to_int` (의미 전환)
- `test_recommendation_param_ranges.py::test_existing_validate_flow_still_works` (의미 전환)

PASS (불변식 + 의미 전환 중 이미 정합 = 18): G-212 잔존키/규약/self-test + smoke 의미 전환 3(buy_threshold 드롭 계약) 등.

## Green 시뮬레이션 검증 (production 임시 3줄 제거 → 즉시 revert)
3줄 제거 (PARAM_RANGES buy_threshold + donchian_period + INT_PARAMS donchian_period) 후
동일 4 파일 = **26 PASS / 0 FAIL** 확인. production 원복 완료 (`git status src/` clean).

→ backend-dev Green: PARAM_RANGES L68/L93 + INT_PARAMS L114 3줄 제거만.
