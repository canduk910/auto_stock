# cycle210 — auto_apply ratchet 차단 (P0-B)

**명세 출처**: `_workspace/strategy_review/2026-07-14_phaseA_domain_analysis.md` 판단1 (domain 자문)
**행위**: AI 자문 자동적용(`auto_apply_recommendations`)의 손절/일일한도/비중 param 자동적용 차단 — auto_apply 는 weight 감액만 잔존 (param ratchet 차단).

## 배경 (근본 원인)

`recommendation_engine.py::auto_apply_recommendations` (L976~) 의 `_CONSERVATIVE_KEYS`(L952-960) 게이트가 손절/일일한도/비중을 **조이는 방향만** 자동 적용(완화 경로 없음) = 단조 ratchet → 전략 교살. donchian daily_loss_limit -6 → -0.8 방치가 그 산물. 시정 = `_CONSERVATIVE_KEYS` 7키 전량 제거 (**빈 frozenset**) → L1066 게이트가 모든 param k 를 `continue` → param 자동적용 0, weight 감액만 잔존.

auto_apply 는 현재 OFF(applied_auto=0)라 예방적 조치.

## 변경 대상 (backend-dev Green)

- `src/engine/recommendation_engine.py` `_CONSERVATIVE_KEYS` → **빈 frozenset** (7키 전량 제거) + 사이클 210 주석.
  → L1066 `if k not in _CONSERVATIVE_KEYS: continue` 가 모든 param k 를 continue → param 자동적용 0.
- `_STOP_LOSS_KEYS` / L1077~ 게이트 로직은 도달 불가(무해)로 유지 or 정리는 backend-dev 재량 (최소 변경 우선). weight 감액 경로(①, L1037~)는 불변.

## 회귀 가드 (Red — production 미변경 시 FAIL)

- **G-210-1**: `_CONSERVATIVE_KEYS` 에 7키(stop_loss_rate/daily_loss_limit/intraday_stop_loss/overnight_stop_loss/stop_loss_main/stop_loss_pre_nxt/position_ratio) 전부 부재(빈 집합). → 현재 7키 잔존 = FAIL.
- **G-210-2 (HIGH, 행위)**: `auto_apply_recommendations` — 손절/일일한도를 **더 조이는**(stop_loss_rate -6→-3, daily_loss_limit -6→-1) + position_ratio 축소(0.5→0.3) 자문에 대해, 자동 적용 후 **applied_params(strategy.config.params 및 save_params)에 이 키들 미반영** = param 자동적용 0. → 현재 = 조임 자동적용 = FAIL.
- **G-210-3 (HIGH, weight 보존)**: weight 감액(recommended 0.1 < current 0.2)은 여전히 자동 적용(auto_apply 순기능 보존). param 차단이 weight 경로를 훼손하지 않음. → 현재 PASS (Green 후에도 유지 = 회귀 가드).
- **G-210-4 (AST)**: `recommendation_engine.py` `_CONSERVATIVE_KEYS` 정의 dict/set 리터럴에 손절/한도/비중 키 문자열 부재. → 현재 잔존 = FAIL.

## 의미 전환 (사이클 66 K-2)

- `tests/unit/engine/test_auto_apply_recommendations.py::test_auto_apply_conservative_params_only` — "보수적 param(stop_loss_rate) 자동 적용" 단언 → "자동 적용 안 됨(param 미반영, weight 전용)"으로 갱신. auto_apply weight 자동적용 케이스(1~4)는 보존.

## 산출물

- Red memo: 본 파일.
- 신규: `tests/unit/engine/test_cycle210_auto_apply_ratchet_block.py` (G-210-1/2/3) + `tests/unit/ast/test_cycle210_ast_conservative_keys.py` (G-210-4).
- 의미 전환: `test_auto_apply_recommendations.py::test_auto_apply_conservative_params_only`.

## Red 실행 결과 (production 미변경)

신규 파일 4 케이스 = **4 FAIL**:
- `test_cycle210_auto_apply_ratchet_block.py::test_g210_1_conservative_keys_empty` — FAIL (현재 7키 잔존)
- `::test_g210_2_tightening_params_not_applied` — FAIL (현재 조임 param 자동적용)
- `::test_g210_3_weight_reduction_still_applied` — FAIL (weight 감액은 통과하나 동반 조임 param 이 현재 자동적용됨 → 회귀 가드 = param 미적용 단언 FAIL). Green 후 weight+param 양쪽 PASS.
- `test_cycle210_ast_conservative_keys.py::test_g210_4_...` — FAIL (리터럴에 7키 잔존)

의미 전환 파일:
- `test_auto_apply_recommendations.py::test_auto_apply_conservative_params_only` — **FAIL** (assert -5.0 == -7.0 — 현재 stop_loss_rate 자동적용됨). 나머지 4 케이스(1~4) PASS 유지.

→ 신규 4 FAIL + 의미 전환 1 FAIL = **5 FAIL** (production 미변경). Green(빈 `_CONSERVATIVE_KEYS`) 후 전량 PASS 예상.

## Green (backend-dev 완료 후 기입)
## Refactor (사이클 종료 시 기입)
