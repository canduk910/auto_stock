# 사이클 3-B (placeholder) — LTV 보드별 손절 분리

> **상태:** 발의 대기 (사이클 3 회귀 검증 후 결정)
> **선행 조건:** 5/18 사이클 1+2+3 운영 검증 완료

## 배경

사이클 3 에서 VB 의 보드별 손절(`stop_loss_main` / `stop_loss_pre_nxt`) 분리 완료. LTV(`long_tail_volatility`) 도 동일 권고를 받았으나 **시간 모드 × 보드 = 4 조합** 의 복잡도로 별도 사이클로 미뤘다.

## LTV 현재 손절 구조

```python
# DEFAULT_PARAMS
"intraday_stop_loss": -2.5,    # 당일 모드 손절
"overnight_stop_loss": -2.0,   # 익일 (상한가) 모드 손절
```

LTV 의 `check_exit_signal()` 는 `_limit_up_reached` set 분기:
- 당일 모드 (상한가 미도달): `intraday_stop_loss` 적용
- 익일 모드 (상한가 도달, 다음 영업일 NXT 프리 청산): `overnight_stop_loss` 적용

LTV 매수 보드: PRE_NXT + MAIN (POST_NXT 매수 비활성, 2026-05-15 결함 D)
LTV 보유 종목 손절 모니터링: 모든 보드 (`risk.on_tick` 은 보드 가드 무관)

## 4 조합 매트릭스 분석

| 시간 모드 | 보드 | 키 후보 | 임계 권고 (예시) |
|-----------|------|---------|------------------|
| 당일 (intraday) | MAIN | `intraday_stop_loss_main` | -2.5 (기존) |
| 당일 (intraday) | PRE_NXT | `intraday_stop_loss_pre_nxt` | -3.0 (PRE_NXT 노이즈 흡수) |
| 익일 (overnight) | MAIN | `overnight_stop_loss_main` | -2.0 (기존) |
| 익일 (overnight) | PRE_NXT | `overnight_stop_loss_pre_nxt` | -2.5 (NXT 프리 청산 직전 손절) |
| 익일 (overnight) | POST_NXT | `overnight_stop_loss_post_nxt` | -2.5 (POST_NXT 손절 모니터링 — 보유 평가만) |

**5 키 (post_nxt 까지) — 4 조합 + post_nxt overnight 1 추가**

## 복잡도 우려사항

### 1. 키 네임스페이스 확장
- 기존 2 키 → 5 키 (+150%)
- `_normalize_stop_loss_rate` 후보 5 → 8 (LTV 만 5 신규)
- PARAM_RANGES 5 키 추가 → OpenAI 자문 권고 매트릭스 비대화

### 2. fallback 계층
복합 fallback 우선순위 ((mode × board) → mode → top-level):
```
1. params.get(f"{mode}_stop_loss_{board}")     # 4 조합 키
2. params.get(f"{mode}_stop_loss")             # 기존 mode 키 (LTV 호환)
3. params.get("stop_loss_rate")                # 통합 fallback
```

→ 헬퍼 `_get_ltv_stop_loss_for_mode_and_board(params, mode, board)` 신규 필요.

### 3. 마이그 자동 복사
```sql
-- LTV strategy_config.params 의 intraday/overnight 값을 보드별 키로 복사
UPDATE strategy_config
SET params = params
    || jsonb_build_object(
        'intraday_stop_loss_main', params->>'intraday_stop_loss',
        'intraday_stop_loss_pre_nxt', params->>'intraday_stop_loss',
        'overnight_stop_loss_main', params->>'overnight_stop_loss',
        'overnight_stop_loss_pre_nxt', params->>'overnight_stop_loss',
        'overnight_stop_loss_post_nxt', params->>'overnight_stop_loss'
    )
WHERE strategy_id = 'long_tail_volatility' ...
```

### 4. 회귀 영향도
- LTV `check_exit_signal` 내부 분기 변경 (당일/익일 모드 진입 후 보드별 fallback)
- `_normalize_stop_loss_rate` 5 키 추가 (보드별 차별화 시 가장 보수적 손절 카운트)
- `tests/unit/engine/strategies/test_long_tail_volatility.py` 및 회귀 가드 영향 평가 필요

## 검토 사항

### A. 사이클 3-B 진행 여부
- **찬성**: LTV `code_review_notes` 권고 충실 반영
- **반대**: LTV 의 당일/익일 모드 분리는 이미 보드 특성을 일부 흡수 (intraday=KRX MAIN 위주 / overnight=NXT 프리 위주). 추가 분리의 한계 효용 작을 가능성

### B. 단순화 옵션
- **3 키 안**: `intraday_stop_loss_main` + `overnight_stop_loss_main` + `overnight_stop_loss_post_nxt` (PRE_NXT 는 매수 직후라 차별 효용 낮음)
- **2 키 안**: `intraday_stop_loss` 그대로 + `overnight_stop_loss_post_nxt` 만 추가 (POST_NXT 손절 모니터링 특화)

### C. 결정 기준 (5/18 사이클 1+2 검증 후)
1. 사이클 3 (VB) 운영 5 영업일 후 보드별 차별화 효과 측정
2. LTV 5/18~5/22 운영 데이터로 보드별 손절률 격차 확인
3. 격차 < 0.5%p 면 사이클 3-B 보류 / 격차 > 1.0%p 면 5 키 안 진행

## 회귀 영향 평가 (예상)

| 영향 영역 | 범위 | 위험 |
|-----------|------|------|
| `_normalize_stop_loss_rate` | 후보 5 → 8 | 낮음 (음수 필터링 보존) |
| LTV `check_exit_signal` | 분기 2 → 5 | 중간 (모드 × 보드 분기 추가) |
| PARAM_RANGES | 신규 3~5 키 | 낮음 |
| 마이그 025 | LTV strategy_config 자동 복사 | 낮음 (멱등) |
| 회귀 테스트 | LTV 단위 5+ 신규 / 통합 3+ 신규 | 중간 |

## 후속 작업

본 명세 발의 결정 시:
1. `_workspace/red/cycle3b_ltv_board_stop_loss.md` 행위 분해 작성
2. Red 테스트 작성 (LTV 보드별 손절 단위 + 회귀 가드)
3. Green 구현 (LTV `_get_stop_loss_for_mode_and_board` 헬퍼 + `check_exit_signal` 갱신)
4. 마이그 025 SQL 작성
5. 통합 검증 + 운영 활성화 절차
