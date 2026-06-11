# 사이클 103 영역 3 — strategy.py dead code 영구 폐기 + AST 영구 가드 신설

**명세 출처**: 사용자 결정 사이클 103 (Q12'=B, 2026-06-11) — 영역 3 = AST 영구 가드 신설 후 dead code 삭제
**행위**: `src/engine/strategy.py` 영역 = `check_stop_loss` + `check_next_day_clear` + `check_buy_signal` 3 모듈 함수 영역 = callsite 0건 영속 확인 후 일괄 삭제 + AST 영구 가드 신설 (사이클 78 G-AST1 + 사이클 79 G-AST2 답습)

## 영속 의무 매트릭스 (HIGH)

- 사이클 78 G-AST1 영속 (`flush_*` 호출 사이트 ≥1건 정적 가드 답습)
- 사이클 79 G-AST2 영속 (task cancel 영역 영구 영속 답습)
- CLAUDE.md "절대 깨지 말 것" 8 영역 영속

## 영역 3 영구 폐기 영역

### callsite 0건 영구 영속 확인 의무

- **grep 영역 1 (src/)**: `grep -rn "check_stop_loss\|check_next_day_clear\|from src\.engine\.strategy import" /Users/koscom/Projects/auto_stock/src/` = **0건 영속** 영구 영속
- **grep 영역 2 (tests/)**: 동일 grep 영역 `tests/` 영역 = **0건 영속** 영구 영속
- **grep 영역 3 (production callsite)**: `from src.engine.strategy import check_buy_signal` 또는 동일 `check_buy_signal` 모듈 함수 영역 외부 호출 = **0건 영속** 영구 영속 (`MomentumStrategy.check_buy_signal` 메서드 영역과 분리)

### 영구 폐기 대상

- `src/engine/strategy.py:85~148` (`check_buy_signal` 모듈 함수, ~63L) — `MomentumStrategy.check_buy_signal` 메서드 영역과 별개 영역 (모듈 영역 dead code)
- `src/engine/strategy.py:151~171` (`check_stop_loss` 모듈 함수, ~20L)
- `src/engine/strategy.py:174~207` (`check_next_day_clear` 모듈 함수, ~33L)
- `src/engine/strategy.py:210~215` (`calc_buy_quantity` 모듈 함수 영역) = callsite 영역 영속 확인 필요 (사이클 103 영역 외 영속 의무)

### 영속 영역 (변경 0)

- `Signal` enum (L28~33) + `Position` dataclass (L36~52) + `StrategyState` dataclass (L55~78) + `_prev_prdy_rate` 모듈 dict (L82) + 임계 상수 7개 (L19~25) = **영속 의무** 영역 영구 영속 (외부 import 영역 영속)

## 회귀 가드 1 케이스 (HIGH 1)

### HIGH-1: AST 영구 가드 (사이클 78 G-AST1 + 사이클 79 G-AST2 답습)

- **`tests/unit/ast/test_cycle103_ast_no_dead_strategy_funcs.py::H1_no_dead_module_funcs`**:
  - `src/engine/strategy.py` rglob 영역 = 단일 파일 영역
  - `def check_stop_loss(` 영역 = **0건 영속** 영구 영속
  - `def check_next_day_clear(` 영역 = **0건 영속** 영구 영속
  - `def check_buy_signal(` 영역 (모듈 함수 영역, 클래스 메서드 영역과 분리) = **0건 영속** 영구 영속
  - 정규식 영역 = `^def check_stop_loss\b` / `^def check_next_day_clear\b` / `^def check_buy_signal\b` (모듈 영역 정적 검증)
  - 미래 동일 영역 재발 영구 차단 영역 영속

## Red 단계 (production 코드 변경 0)

- `src/engine/strategy.py` 영역 = 3 모듈 함수 영역 영속 (변경 0)
- 1 신규 AST 테스트 영역 = RED 영구 영속 (`def check_stop_loss(` 영역 ≥1건 영속 = AssertionError 영속)

## Green 단계 인계 (backend-dev 영역)

1. `src/engine/strategy.py:85~207` 영역 일괄 삭제 (3 모듈 함수 영역 영구 폐기, ~120L -)
2. `src/engine/strategy.py` 영속 영역 (Signal / Position / StrategyState / 임계 상수 / `_prev_prdy_rate` dict / `calc_buy_quantity`) = 변경 0 영구 영속
3. 사이클 103 영역 3 = 단일 파일 영역 시정 (callsite 0건 영구 영속 확인 후 안전 영역)

## 영속 의무 영속 검증 (Green 단계 후)

- 사이클 78 G-AST1 답습 = 미래 dead code 재도입 영구 차단 영역 영속
- 사이클 79 G-AST2 답습 = AST 정적 가드 영역 영속
- CLAUDE.md "절대 깨지 말 것" 8 영역 영속 (dead code 폐기 영역 = 매매 hot path 영향 0)
- 매매 안전성 무영향 (외부 callsite 0건 영구 영속 확인 후 안전 폐기 영역)

## 사이클 103 영역 4 (사이클 103 명세 동기화 통합, 사용자 결정 Q13'=A)

- `docs/HARNESS_CHANGELOG.md` 사이클 103 행 = 4 영역 통합 영구 영속
- `CLAUDE.md` 루트 하네스 변경 이력 표 = 사이클 103 행 영구 영속
- `_workspace/test_index.yaml` 영향 인덱스 갱신 (backend tests +3 / frontend modules +2)
