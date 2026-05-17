# 사이클 3 — VB 보드별 손절 분리

## 배경

5/15 첫 자문 발화의 VB `code_review_notes` 권고:
> "보드별(kospi/krx main, pre/open 구간 등) 개별 손절·진입시간 파라미터 분리"

VB 현재 운영:
- 진입: PRE_NXT (08:00~09:00) + MAIN (09:00~15:20)
- 손절: 단일 `stop_loss_rate = -3.0` (보드 무관)
- K값은 이미 보드별 분리 (`k_value_krx_main` / `k_value_nxt_pre` / `k_value_nxt_post`, 사이클 1 PARAM_RANGES 등록)

본 사이클 — K값과 같은 패턴으로 손절도 보드별 분리.

LTV 는 본 사이클 범위 외 — 이미 시간 모드 분리(intraday/overnight). 보드 × 모드 = 4 조합 복잡도라 사이클 3-B 로 별도.

## 자율 결정 — `active_board` 전달 방식

3 가지 옵션 검토:
- 옵션 1: `risk.on_tick` 가 `active_board` 인자로 전달 → `check_exit_signal(ticker, current, open, board)` 시그니처 변경
- 옵션 2: VB 내부에서 `session_tracker.active` 조회 (기존 `_resolve_active_board()` 재사용)
- 옵션 3: `check_exit_signal()` 시그니처 확장 (`board: MarketBoard | None`)

**채택: 옵션 2**

이유:
1. VB 에 이미 `_resolve_active_board()` 헬퍼 존재 — 재활용 가능
2. `check_exit_signal(ticker, current_price, open_price)` 시그니처는 6 전략 + 5+ 테스트 mock 에서 광범위 사용 → 변경 시 회귀 영향 큼
3. 보드별 손절 분리는 VB 단독 — 다른 전략에 인자 전달 불필요
4. `risk.py` 변경 0건 (옵션 1 회피)

## 행위 분해

### 행위 A — `_get_stop_loss_for_board(params, board)` 헬퍼
- 입력: params dict, board 문자열 ("main", "pre_nxt", "post_nxt", None)
- 우선순위:
  1. `params.get(f"stop_loss_{board}")` (board 가 None 이면 skip)
  2. `params.get("stop_loss_rate")` (fallback)
- 음수만 인정 (양수/None/0 은 fallback 으로)
- 반환: float (음수 손절 임계값)

### 행위 B — VB `check_exit_signal` 보드 인식
- 활성 보드 1개 (`_resolve_active_board()` 조회) → 보드별 키 우선
- 활성 보드 미감지 → top-level `stop_loss_rate` fallback
- 보드별 키 부재 → top-level fallback

### 행위 C — PARAM_RANGES 확장
- `stop_loss_main`: `(-15.0, 0.0)`
- `stop_loss_pre_nxt`: `(-15.0, 0.0)`
- (`stop_loss_post_nxt` 는 VB 가 POST_NXT 미사용이라 제외)

### 행위 D — `_normalize_stop_loss_rate()` 헬퍼 갱신
기존 3 키(`stop_loss_rate`/`intraday_stop_loss`/`overnight_stop_loss`) → 5 키 후보:
- `stop_loss_rate`
- `intraday_stop_loss`
- `overnight_stop_loss`
- `stop_loss_main` (신규)
- `stop_loss_pre_nxt` (신규)

`min(candidates)` (가장 보수적인 = 절대값 큰) 로 정규화. `compute_metrics` 의 `stop_loss_hits` 카운트 정확도 보존.

### 행위 E — 마이그 024 (적용 보류)
`supabase/migrations/024_vb_board_stop_loss_defaults.sql`:
- VB `strategy_config.params` 의 `stop_loss_rate` 값을 `stop_loss_main` + `stop_loss_pre_nxt` 로 자동 복사
- IF NOT EXISTS 멱등 가드

## 회귀 가드

- 5/15 운영값(`stop_loss_rate=-3.5` 단일 키) → fallback 동작 보존
- LTV `intraday_stop_loss`/`overnight_stop_loss` → `_normalize_stop_loss_rate` 정상 동작 보존
- momentum/donchian/bull_flag/vcp `stop_loss_rate` 단일 키 → 변화 없음
- VB `_next_day_clear_pending` 가드 / 익일 청산 안전망 → 영향 없음

## Red 테스트 파일

1. `tests/unit/engine/strategies/test_volatility_breakout_board_stop_loss.py` — 행위 A+B (6 케이스)
2. `tests/unit/engine/test_recommendation_metrics_board_stop_loss.py` — 행위 D (회귀 5 + 신규 3)
3. `tests/unit/engine/test_recommendation_param_ranges_board_stop_loss.py` — 행위 C (3 케이스)
4. `tests/integration/test_vb_board_stop_loss_fallback.py` — 운영 흐름 (3 케이스)

## 시그니처 회귀 가드

- VB `check_exit_signal(ticker, current_price, open_price)` 시그니처 보존
- `risk.on_tick` 호출부 시그니처 보존
- 5 케이스 (`test_observability_logs.py`, `test_scan_loop_reprepare.py`, etc.) 의 mock 시그니처 무영향
