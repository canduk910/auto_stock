# 사이클 103 영역 2 — momentum.py 손절 로그 임계 동행 emit

**명세 출처**: 사용자 결정 사이클 103 (Q11'=C, 2026-06-11) — 영역 2 = momentum.py 로그 AST + 단위 테스트 통합
**행위**: `src/engine/strategies/momentum.py:127` logger.info 메시지 영역에 임계 (`stop_loss`) 인자 1줄 추가 — 운영 가시화 보강 (사이클 89 한글 친숙 용어 답습 + 사이클 102 G-DOC1 영속 패턴 답습)

## 영속 의무 매트릭스 (HIGH)

- 사이클 38 명문화 영속 (매도 hot path 영역 = 보드 가드 무관 항상 작동)
- 사이클 89 한글 친숙 용어 답습
- 사이클 102 G-DOC1 영속 (논리적 영역 명문화)
- CLAUDE.md "절대 깨지 말 것" 8 영역 영속

## 영역 2 시정 영역

- **위치**: `src/engine/strategies/momentum.py:127`
- **Before**: `"손절 신호: %s 매수가(%d) 대비 %.1f%% (현재가: %d)"`
- **After**: `"손절 신호: %s 매수가(%d) 대비 %.1f%% (임계: %.1f%%, 현재가: %d)"`
- **호출자 영역 변경**: 인자 + `stop_loss` 1개 (L128 영역)
- **영속 영역**: `Signal.STOP_LOSS` 반환 영역 무변경 + 매도 hot path 무영향

## 회귀 가드 2 케이스 (HIGH 2)

### HIGH-1: momentum.py:127 logger.info 호출 영역 임계 인자 영구 영속

- **`tests/unit/engine/strategies/test_cycle103_momentum_log_threshold.py::H1_logger_args_include_stop_loss`**:
  - `MomentumStrategy.check_exit_signal(ticker, current_price, open_price)` 호출 영역 영속
  - 매도 시점 (loss_rate <= stop_loss) 영역 발화 영속
  - `caplog.records[].args` 영역 길이 ≥5 영역 영속 (ticker / buy_price / loss_rate / **stop_loss** / current_price)
  - logger 메시지 형식 `"손절 신호: %s 매수가(%d) 대비 %.1f%% (임계: %.1f%%, 현재가: %d)"` 영역 정합 영속
  - `stop_loss` 인자 영역 값 = `self.config.params["stop_loss_rate"]` (디폴트 -7.5) 영속

### HIGH-2: momentum.py AST 영역 메시지 형식 영속 (사이클 89 G-AST + 사이클 102 G-DOC1 답습)

- **`tests/unit/ast/test_cycle103_ast_momentum_log_format.py::H2_ast_log_format_includes_threshold`**:
  - `src/engine/strategies/momentum.py` rglob 영역 = 단일 파일 영역
  - `"%.1f%% (임계: %.1f%%, 현재가:"` 영역 정확 영구 영속 (정적 grep ≥1건)
  - 기존 `"%.1f%% (현재가: %d)"` 영역 = 0건 영속 (영역 폐기 영구 차단)
  - 인자 영역 정적 검증 = `args` 영역에 `stop_loss` 또는 `self.config.params["stop_loss_rate"]` 영역 영속 (AST 본체 영역 정합)

## Red 단계 (production 코드 변경 0)

- `src/engine/strategies/momentum.py:127` = 사이클 102 영역 이전 영역 영속 (변경 0)
- 2 신규 테스트 영역 = 모두 RED 영구 영속
- pytest 실행 시 `assert "임계" in caplog.records[0].getMessage()` 영역 → AssertionError 영속

## Green 단계 인계 (backend-dev 영역)

1. `src/engine/strategies/momentum.py:127~129` 영역 1줄 시정:
   - L127: `"손절 신호: %s 매수가(%d) 대비 %.1f%% (현재가: %d)"` → `"손절 신호: %s 매수가(%d) 대비 %.1f%% (임계: %.1f%%, 현재가: %d)"`
   - L128: `t(ticker), pos.buy_price, loss_rate, current_price,` → `t(ticker), pos.buy_price, loss_rate, stop_loss, current_price,`

## 영속 의무 영속 검증 (Green 단계 후)

- 사이클 38 명문화 영속 (매도 hot path 보드 가드 무관 영역 영속)
- 사이클 89 한글 친숙 용어 답습 (`임계:` 한글 라벨 영역 영속)
- 사이클 102 G-DOC1 영속 (논리적 영역 명문화 영구 영속)
- CLAUDE.md "절대 깨지 말 것" 8 영역 영속 (매도 hot path 영향 0)
- 매매 안전성 무영향 (로깅 영역 시정만, `Signal.STOP_LOSS` 반환 무변경)
