# 사이클 209 Red — donchian `max_breakout_extension_pct` 0.5→4.0 복원 + PARAM_RANGES 제외

**명세 출처**: `_workspace/domain_consult/cycle209_donchian_extension_gate.md` (domain-expert 자문 채택)
**선례**: 사이클 208 (박스 수축 필터 제거) · 사이클 198 (BFB flag_lookback_min AI 과튜닝 차단)
**행위**: donchian extension 가드 default 값 4.0 복원 + PARAM_RANGES 제외 + extension≥gap 불변식 명문화. 정상 1~3% 돌파는 통과(매수 재개), S-Oil 유형 6.45% 뒷북 추격은 차단(순기능 보존).

## 배경 (2차 병목 규명)

사이클 208 로 박스 필터 제거 → 최종 후보(step9=1, S-Oil 010950) 생성. 그러나 extension 가드(운영 DB `max_breakout_extension_pct=0.5`, AI 20:00 자문이 default 3.0 → 하한 0.5 로 과튜닝)에서 스킵 → donchian 또 매수 0. donchian 후보 = "어제 종가 > 직전20일 신고가"(이미 돌파) → 오늘 대개 기준가 위에서 열림 → `ext_pct = (daily_high - donchian_high)/donchian_high*100` 항상 양수 → 0.5% 면 정상 1~3% 돌파까지 상시 차단(구조상 필연). 실측 S-Oil ext=6.45% 스킵은 **정상**(뒷북 추격 차단이 옳음). 문제는 0.5 값이 정상 돌파까지 봉쇄.

## 변경 대상 (backend-dev Green — Red 가 강제)

1. `src/engine/strategies/donchian_swing.py` DEFAULT_PARAMS `"max_breakout_extension_pct": 3.0` → **4.0** (L101)
2. `src/engine/recommendation_engine.py` PARAM_RANGES `"max_breakout_extension_pct": (0.5, 10.0)` **제거** (L105). INT_PARAMS 무관(float, 미등록 확인).
(운영 DB `strategy_config.donchian_swing.params.max_breakout_extension_pct` 0.5→4.0 지혈 = 메인 세션 MCP 별도 — Red 범위 아님)

## 회귀 가드

### 신규 `tests/unit/engine/strategies/test_cycle209_donchian_extension_gate.py` (6 케이스)
- **G-209-1**: `DEFAULT_PARAMS["max_breakout_extension_pct"] == 4.0` — Red: 현재 3.0 → FAIL.
- **G-209-4 (불변식)**: `ext(4.0) >= gap_skip_threshold(3.0)` + `ext >= gap + 1.0` (갭+장중 소폭 수용 여유) — Red: 현재 3.0 → `3.0 >= 3.0+1.0` FAIL. 두 게이트 모순 방지 명문화(자문 (b)).
- **G-209-3 정상 돌파 (HIGH, 핵심 행위)**:
  - `test_..._ext_3_5_pct_buys_with_default`: default(4.0) 전제, ext 3.5% ≤ 4.0 + gap 1% + 창 09:10 → **BUY**. Red: default 3.0 stash 시 3.5 > 3.0 스킵 → NONE → FAIL. freezegun 09:10 고정, `scanner.ticker_prices` mock(daily_high 주입).
  - `test_..._db_value_0_5_reproduction_then_4_0_unblocks` (**PASS, 대조**): 동일 후보/시세로 params `max_ext=0.5` → ext 2% 스킵(NONE) / `max_ext=4.0` → BUY 전환. params 직접 주입 = default 무관 → 현재 코드에서도 재현 = PASS. 실측 DB 병목 재현 + 시정 방향 대조.
- **G-209-5 추격 차단 보존 (2 케이스, PASS)**: S-Oil 재현 daily_high=143500/donchian_high=134800 → ext 6.45% > 4.0(및 3.0) → NONE. 값 변경과 무관하게 항상 스킵 = 순기능 불변 → PASS.

### 신규 `tests/unit/ast/test_cycle209_ast_extension_param_range.py` (5 케이스)
- **G-209-2 (PARAM_RANGES 부재)**:
  - `test_..._absent_from_param_ranges`: 런타임 dict 에 키 부재 — Red: 현재 L105 잔존 → FAIL.
  - `test_..._absent_from_int_params` (**PASS**): INT_PARAMS 무관(float) — 제거 후에도 부재 유지 = PASS.
- **G-209-6 (AST/SAFETY)**:
  - `test_..._absent_from_param_ranges_dict_literal`: PARAM_RANGES **dict 리터럴 AST 키 노드** 검사(docstring/주석 false-positive 차단, 사이클 208/167 패턴). PARAM_RANGES 는 `AnnAssign`(타입 어노테이션) → Assign+AnnAssign 양쪽 포괄. Red: 현재 잔존 → FAIL.
  - `test_..._safety_check_exit_signal_unchanged` (**PASS**): donchian check_exit_signal 본체 존재 + 청산 로직(STOP_LOSS/TRAILING) 보존 + extension 토큰 부재. extension 가드는 매수 진입(check_buy_signal)만 = 청산 무관(사이클 38).
  - `test_..._safety_extension_gate_in_check_buy_signal` (**PASS**): extension 가드가 check_buy_signal 에 존재(로직 제거 아닌 값/튜닝만 변경) 반증.

## 의미 전환 (사이클 66 K-2)

- `tests/unit/engine/test_param_ranges_vcp.py`:
  - `test_p2_key_ranges` parametrize 에서 `("max_breakout_extension_pct", 0.5, 10.0)` 제거 (PARAM_RANGES 등록 단언 폐기).
  - `test_box_keys_removed_from_param_ranges` parametrize 에 `"max_breakout_extension_pct"` 추가 (부재 단언으로 전환, 사이클 208 box 2키 패턴 답습).
  - 사이클 209 의미 전환 주석 동반.
  - Red: 이동 후 `test_box_keys_removed_from_param_ranges[max_breakout_extension_pct]` = FAIL (현재 잔존) → Green 시 PASS.
- `tests/unit/engine/strategies/test_donchian_swing_extension_cap.py`: **수정 불요** — `_make_strat(max_ext=3.0)` 로 explicit 주입 + 4.0% 초과 케이스라 default 값 변경과 무관하게 PASS 보존 (검증 완료).

## Red 유효성 (production 미변경 시 FAIL/PASS 개수)

**신규 2 파일 (11 케이스): 5 FAIL / 6 PASS**
- FAIL (Red, 구현이 강제): G-209-1 / G-209-4 / G-209-3(3.5% BUY) / G-209-2(PARAM_RANGES 런타임) / G-209-6(dict 리터럴 AST)
- PASS (불변식/대조/SAFETY): G-209-3(0.5 재현 대조) / G-209-5(6.45% 스킵 ×2) / G-209-2(INT_PARAMS 무관) / G-209-6(check_exit + 매수게이트 존재)

**의미 전환 (test_param_ranges_vcp.py): 1 FAIL** — `test_box_keys_removed_from_param_ranges[max_breakout_extension_pct]` (Green 시 PASS).

**총 Red = 6 FAIL / 인접·불변식 = 6+ PASS.** (인접 회귀: donchian 스위트 57 PASS + cycle208 AST 통과 확인.)

## Green 예상 (backend-dev)

- DEFAULT_PARAMS 4.0 → G-209-1/G-209-4/G-209-3(3.5%) PASS 전환.
- PARAM_RANGES L105 제거 → G-209-2/G-209-6(dict)/의미전환 PASS 전환.
- 매매 안전성 8영역 diff 0 (extension 가드는 check_buy_signal = 매수 진입 전, 사이클 38 / check_exit·ATR·신고가·EMA 불변).
