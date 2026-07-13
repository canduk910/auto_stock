# 사이클 208 Red — donchian_swing 박스 수축 보조 필터 완전 제거

> 자문: `_workspace/domain_consult/cycle_donchian_box_contraction.md`
> Red 작성 = tdd-engineer / Green(삭제 구현) = backend-dev.

## 배경 / 결정

donchian_swing = "20일 신고가 돌파" (추세추종). ATR 통과 후 유일 게이트인 박스 수축 필터
(`max_box_volatility_pct` ≤3.2% DB / 5.0 코드 default, `box_contraction_period` 12/10일)가
"돌파 전 초압축 횡보"를 요구 → **추세 상승 종목(신고가 = 박스 넓음)을 상시 탈락** →
최종 후보 상시 0 (오늘 KB금융·금호타이어 step8=2 → step9=0).

domain 결론 = **필터 완전 제거**. 페이크 방어는 청산 규칙(ATR×2 트레일링 / -7% /
`breakout_fail_n_days` / `max_breakout_extension_pct`)이 담당 → 제거 리스크 무손상.
VCP/BFB 와 역할 중복. domain (c): 박스 폭 임계는 손익 튜닝값 아닌 **전략 정체성 상수**
→ AI 자동튜닝 제외 (사이클 198 `flag_lookback_min` 선례).

## 제거 대상 (backend-dev Green 에서 삭제 — Red 가 삭제를 강제)

### 1. `src/engine/strategies/donchian_swing.py`
- **L368-384**: 박스 수축 필터 블록 전체
  - `box_period` / `max_box_vol` params 읽기 (L369-370)
  - `if len(candles) > box_period:` 블록 전체 (L371-384)
    - `box_highs`/`box_lows`/`box_closes` 슬라이스
    - `box_range = max(box_highs) - min(box_lows)`
    - `box_mean` / `vol_pct = box_range / box_mean * 100`
    - `if vol_pct > max_box_vol: continue` (박스 넓은 종목 탈락)
    - `stats["box_contraction_pass"] += 1`
    - `else: continue` (box_mean ≤ 0)
- **L57**: `_empty_scan_stats()` 의 `"box_contraction_pass": 0` 키
- **L104-105**: `DEFAULT_PARAMS` 의 `"box_contraction_period": 10` + `"max_box_volatility_pct": 5.0`

### 2. `src/engine/recommendation_engine.py`
- **L106-107**: `PARAM_RANGES` 의 `"box_contraction_period": (5, 30)` + `"max_box_volatility_pct": (1.0, 15.0)`
- **L122**: `INT_PARAMS` 의 `"box_contraction_period"`

## 회귀 가드 (Red — 현재 코드에서 FAIL 해야 함)

### `tests/unit/engine/strategies/test_cycle208_donchian_box_removal.py`
- **G-208-1 (HIGH, 핵심)** — ATR 까지 통과 + **박스가 넓은**(예전 필터라면 vol_pct >> 5.0 → 탈락)
  합성 종목이 이제 `prepare()` 후 `_candidates` (최종 후보)에 포함.
  = 20일 신고가 돌파 + 60일 EMA 우상향 + 종가>EMA + 거래대금 1.5×↑ + ATR>0 만족하되
  최근 박스 폭 매우 넓은 candles (추세 상승 종목 모사).
  **현재 코드 = 박스 필터 continue → 탈락 (FAIL) / 제거 후 = 포함 (PASS)**.
- **G-208-2** — `DonchianSwingStrategy.DEFAULT_PARAMS` 에 두 키 부재.
- **G-208-3** — `get_scan_stats()` / `_empty_scan_stats()` 에 `box_contraction_pass` 키 부재.
- **G-208-4** — `recommendation_engine.PARAM_RANGES` 에 두 키 부재.
- **G-208-5** — `recommendation_engine.INT_PARAMS` 에 `box_contraction_period` 부재.
- **G-208-6 (AST/SAFETY)** — 아래 AST 파일 참조.
- **불변식 (제거해도 PASS 유지)**:
  - 20일 신고가 미달 종목 여전히 탈락 (donchian_pass 미증가)
  - EMA 우상향 미달 여전히 탈락
  - ATR≤0 여전히 탈락
  - donchian `check_exit_signal` 본체 미변경 (SAFETY 불변식)

### `tests/unit/ast/test_cycle208_ast_no_box_filter.py`
- **G-208-6 (AST)** — `donchian_swing.py` prepare 영역에 박스 필터 토큰
  (`box_range` / `max_box_vol` / `box_contraction`) 잔존 0건 (미래 재도입 영구 차단).
  + 매매 안전성: 제거는 prepare(매수 진입 전, 사이클 38) 한정 → check_exit_signal/청산/손절 무관.

## 의미 전환 (사이클 66 K-2 패턴 — 삭제 말고 갱신)

- `tests/unit/engine/strategies/test_donchian_swing_box_contraction.py` — 박스 필터 *동작* 을
  단언하던 3 테스트 → 필터 *제거됨* 을 단언하도록 의미 전환 (박스 넓어도 통과 / stats 키 부재).
- `tests/unit/engine/test_param_ranges_vcp.py` — box 2 키가 PARAM_RANGES/INT_PARAMS 에
  있다고 단언하던 parametrize 엔트리 → 부재 단언으로 갱신.

## Red 유효성 (production 미변경 상태 예상)

신규 파일 (`test_cycle208_donchian_box_removal.py` + `test_cycle208_ast_no_box_filter.py`):

| 케이스 | 현재 코드 | 판정 |
|--------|----------|------|
| G-208-1 (넓은 박스 후보 포함) | 박스 필터 continue → 탈락 | **FAIL** |
| G-208-2 (DEFAULT_PARAMS 부재) | 두 키 존재 | **FAIL** |
| G-208-3 (scan_stats 키 부재) | box_contraction_pass 존재 | **FAIL** |
| G-208-4 (PARAM_RANGES 부재) | 두 키 존재 | **FAIL** |
| G-208-5 (INT_PARAMS 부재) | box_contraction_period 존재 | **FAIL** |
| G-208-6 AST 토큰 3건 (box_range/max_box_vol/box_contraction, parametrize) | 토큰 잔존 | **FAIL ×3** |
| G-208-6 AST 모듈 소스 키 부재 | 키 잔존 | **FAIL** |
| INV-1 신고가 미달 탈락 | 정상 탈락 | PASS (불변식) |
| INV-2 종가<EMA 탈락 | 정상 탈락 | PASS (불변식) |
| INV-3 완전 평탄(돌파X+ATR0) 탈락 | 정상 탈락 | PASS (불변식) |
| SAFETY check_exit_signal 본체 존재 (AST) | 본체 존재 | PASS (불변식) |
| SAFETY check_exit_signal 박스 토큰 0건 (AST) | 애초 부재 | PASS (불변식) |

**신규 파일 = 9 FAIL / 5 PASS(불변식)** (parametrize 로 G-208-6 토큰 3건 분리).
검증 실측 (production 미변경): `9 failed, 5 passed`.

의미 전환 파일:
- `test_donchian_swing_box_contraction.py` (3 케이스) — 현재 코드(필터 존재) 기준 갱신 후 FAIL,
  Green(필터 제거) 후 PASS.
- `test_param_ranges_vcp.py` — box 2 키 부재 단언 = 현재 코드 기준 FAIL, Green 후 PASS.
  (VCP 4 키 + P2 3 키(box 제외)는 불변 PASS.)

## Green 완료 후 재실행 기대

전체 격리 = 신규 6 + 의미전환 (box 3 + param_ranges box 엔트리) 모두 PASS.
매매 안전성 8영역 diff 0 (변경 = donchian prepare 필터 블록 + DEFAULT_PARAMS + recommendation_engine
화이트리스트 — 전부 매수 진입 전 영역).
