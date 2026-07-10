# 사이클 198 — BFB `flag_lookback_min` 3→2 완화 (Red)

> 작성: 2026-07-09 (tdd-engineer) · 단계: Red 완료, backend-dev Green 대기
> 배경: `_workspace/domain_consult/cycle198_pattern_strictness_korea.md` (도메인 자문 + 298종목×4일 DB 실측)
> 사용자 결정: 보수(이 단일 파라미터만).

## 의도

한국 급등주는 눌림(플래그)이 얕고 빠르다 — 상한가 익일 눌림 → 3일차 재돌파 리듬.
현재 `flag_lookback_min=3` 은 2일 얕은 눌림을 플래그로 못 잡아 검출 0.
298종목 as-of 실측: 3→2 = 유의미 레버 (7/9 2→9, 7/7 0→2). flag_volume_ratio(0.60)
안전장치가 급락 되돌림(하락 초입) 후보를 전량 흡수 실증(7/8 완화 시 PASS +0).

**변경 대상 = 단일 파라미터.** `bull_flag_breakout.py::DEFAULT_PARAMS["flag_lookback_min"]` 3 → 2.
검출 함수 `_detect_pole_and_flag_detailed` 의 flag_len 루프 `range(flag_min, flag_max+1)` 가
flag_min=2 이면 2일 플래그 조합을 포함. 그 외 임계(flag_volume_ratio/pole_min_return/
flag_retracement_max/pole_max_red_ratio) 전부 불변. donchian/vcp 무변경.

## backend-dev 구현 지시 (정확히 무엇을 바꿔야 Green)

**단 한 줄:** `src/engine/strategies/bull_flag_breakout.py:93`
```python
"flag_lookback_min": 3,   →   "flag_lookback_min": 2,
```
그 외 코드 변경 0. 검출 함수(`_detect_pole_and_flag_detailed`)·prepare·__init__ 무변경
(flag_min 은 이미 `p["flag_lookback_min"]` 로 파라미터에서 읽음 — 값만 바뀌면 루프가
2일 조합을 포함하도록 자연 동작).

**동기화 의무 (CLAUDE.md 규칙):** DEFAULT_PARAMS 변경 → `_workspace/00_leader_trading_rules.md`
6-E 명세 갱신 (flag_lookback_min "3영업일"→"2영업일"). PARAM_RANGES 추가는 별도 결정
(자문 §정합성: 플래그 시간창은 시장 리듬 상수라 자동 튜닝 부적합 = 수동 유지 권고 →
사이클 198 에서는 PARAM_RANGES 미변경).

## 산출물

- `tests/unit/engine/strategies/test_cycle198_bfb_flag_lookback_min.py` — (a) 완화 실증 + (b) SAFETY 불변 + (d) 인접 키 불변 + (e) 최종값.
- `tests/unit/ast/test_cycle198_ast_default_params_scope.py` — (c) donchian/vcp DEFAULT_PARAMS scope 가드 (AST 토큰 기반, 사이클 180 C.8/167 답습).

## 가드 매트릭스

| ID | 파일 | 성격 | 현재 코드(min=3) | 완화 후(min=2) |
|----|------|------|:---:|:---:|
| (a) `test_a_shallow_2day_flag_detected_only_with_min2` | strategies | **Red 핵심** — 얕은 2일 눌림+거래량 고갈, min=3 None / min=2 dict 명시 대비 + DEFAULT 검출 | **FAIL** | PASS |
| (b) `test_b_2day_drop_high_volume_rejected[3]` | strategies | **SAFETY 불변** — 얕은 조정+거래량 유지(하락 초입 위장) → volume_contraction 탈락 | PASS | PASS |
| (b) `test_b_2day_drop_high_volume_rejected[2]` | strategies | 동일 (min=2) | PASS | PASS |
| (d) `test_d_adjacent_safety_params_unchanged` | strategies | **불변** — flag_volume_ratio 0.60 / pole_min_return 15.0 / flag_retracement_max 0.382 / pole_max_red_ratio 0.45 / flag_lookback_max 10 | PASS | PASS |
| (e) `test_e_flag_lookback_min_is_2` | strategies | **Red** — DEFAULT_PARAMS 최종값 == 2 | **FAIL** | PASS |
| (c) G-198-SCOPE-1 | ast | donchian DEFAULT_PARAMS 에 flag_lookback_min 키 부재 | PASS | PASS |
| (c) G-198-SCOPE-2 | ast | vcp DEFAULT_PARAMS 에 flag_lookback_min 키 부재 | PASS | PASS |
| (c) G-198-SCOPE-3 | ast | donchian 대표 키 5종 불변(donchian_period/long_ma_period/volume_multiplier/stop_loss_rate/breakout_fail_n_days) | PASS | PASS |
| (c) G-198-SCOPE-4 | ast | vcp 대표 키 10종 불변(ema_short/mid/long/base_min/max_days/pullback_count_min/max/last_pullback_max/volume_contraction_ratio/breakout_volume_mult) | PASS | PASS |
| (c) G-198-SCOPE-5 | ast | (self-test) BFB DEFAULT_PARAMS 에 flag_lookback_min 키 존재 (탐지기 검증) | PASS | PASS |

## Red 유효성 실행 결과 (현재 코드 = flag_lookback_min 3)

```
tests/unit/engine/strategies/test_cycle198_bfb_flag_lookback_min.py
tests/unit/ast/test_cycle198_ast_default_params_scope.py
→ 2 failed, 8 passed
  FAILED test_a_shallow_2day_flag_detected_only_with_min2  (Red)
  FAILED test_e_flag_lookback_min_is_2                     (Red)
  PASSED test_b[3] / test_b[2] / test_d / SCOPE-1~5        (불변식)
```

**Green 확인** (DEFAULT 임시 flip 3→2 후 실행 → 즉시 revert): 10 passed. min=2 하에서
인접 BFB 전략 스위트(125 passed, 9 xfailed) 회귀 0 — **의미 전환 0건**.

## 의미 전환 유무

**0건.** grep 결과 기존 테스트가 `flag_lookback_min == 3` 을 계약으로 단언하는 곳 없음
(cycle48/50/bull_flag_breakout 전수 확인). min=2 하에서 BFB 관련 465 케이스 스위트 회귀 0.
`_build_candles`(cycle50 헬퍼)·기존 검출 케이스는 flag_len=4 등 3+ 조합이라 min 하향에
영향 없음. backend-dev 는 기존 테스트 수정 불필요.

## 매매 안전성

- BFB `prepare()` = scanner 매수 진입 *전* 후보 풀 구성 (사이클 38 명문화). 검출 창만 확대.
- 돌파 절대규칙(`flag_high` 돌파 순간 = 이전틱<기준가 AND 현재틱>=기준가) 무변경 (자문 §정합성).
- 거래량 고갈 안전장치(flag_volume_ratio 0.60) 절대 불변 — (b) SAFETY 가드가 급락 되돌림
  오판 차단을 고정 (자문 §반례 #2 실증 봉쇄).
- risk.on_tick / order_engine / realtime / auth / 매도·손절·익일청산 hot path 무관.
