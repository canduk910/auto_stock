# 사이클 4 — 매크로 레짐 → AI 자문 통합 (2026-05-17)

## 목적
`recommendation_engine._call_openai()` 의 user_payload 에 `market_regime` 필드 추가
+ SYSTEM_PROMPT 에 매크로 컨텍스트 활용 가이드 1 문단 추가.

## 동기
- 5/15 사이클 2 (시장 레짐 필터 + dkstock.cloud) 도입 + `_boot()` 시점 매크로 fetch 가능
- 그러나 OpenAI 자문 user_payload 에는 매크로 컨텍스트 무전달 → 자문이 "통계만 보고" 손절률 조정
- defensive 레짐(VIX>25, 공포지수 극단) 일 때 손절률 더 보수적 권고 필요
- aggressive 레짐(확장기, 낮은 VIX) 일 때 진입 임계 완화 가능
- buy_blocked=True 일 때 매수 임계 변경 권고 무용 — 손절·청산 파라미터만

## 변경 사양

### A. `MarketRegime.to_advisor_dict()` 신규 메소드 (`src/engine/market_regime.py`)

11 키 dict 반환:
```
regime              # defensive|neutral|aggressive
regime_desc         # 한국어 설명
cycle_phase         # expansion|contraction
vix                 # float
vix_level           # low(<15) / normal(15~25) / elevated(25~35) / high(>35)
fear_greed_score    # float
fear_greed_label    # 극공포(<15) / 공포(15~35) / 중립(35~65) / 탐욕(65~85) / 극탐욕(>85)
buffett_ratio       # float | None
buy_blocked         # bool
block_reason        # str | None
cash_min_recommended      # int | None  (cash_min 직결)
stock_max_recommended     # int | None  (raw.regime.params.stock_max 우선, 없으면 None)
```

→ 총 12 키 (수정: stock_max_recommended 까지 포함하여 검증 가능하면 표시. 명세는 11 키이지만
`stock_max_recommended` 가 명세 5 절차 list 에 포함되어 있어 12 로 표시).
실제 검증은 dict 안에 **11 키 + stock_max 1 = 12 키** 로 진행. 핵심 키 11 개 + stock_max_recommended.

내부 헬퍼:
- `_classify_vix() -> str | None`: 임계 15/25/35
- `_classify_fear_greed() -> str | None`: 임계 15/35/65/85

raw_response, cash_min(원본), raw 등 대용량/내부 필드는 제외.

### B. `_call_openai()` user_payload 확장

```python
from src.engine.market_regime import get_current_regime  # 모듈 싱글톤

regime = get_current_regime()

user_payload = {
    "strategy_name": ...,
    "strategy_description": ...,
    "current_params": ...,
    "metrics": ...,
    "param_ranges": ...,
    "current_weight": ...,
    "peer_weights": ...,
    "peer_metrics": ...,
}
if regime is not None and not regime.empty():
    user_payload["market_regime"] = regime.to_advisor_dict()
```

graceful 분기:
- regime is None → 키 추가 안 함
- regime.empty() (모든 필드 None) → 키 추가 안 함
- `regime.regime is None` 도 empty 의 한 가지로 본다 (사이클 2 정의)

### C. SYSTEM_PROMPT 매크로 가이드 추가

현 SYSTEM_PROMPT 끝에 다음 1 문단 추가:

```
시장 매크로 컨텍스트 활용 (user_payload 에 market_regime 가 있을 때만):
- regime=defensive (현금 권고, VIX 25↑, 공포지수 극단): 손절률을 더 보수적으로 (절대값 작게) 조정, position_ratio 축소, daily_loss_limit 강화 권고
- regime=neutral: 기존 파라미터 유지 또는 미세 조정
- regime=aggressive (확장기, 낮은 VIX, 적정 fear_greed): 진입 임계 완화 또는 position_ratio 확대 가능 (단, 변동성 큰 모멘텀류는 신중)
- buy_blocked=True: 모든 전략 매수 차단된 상태. 매수 임계 변경 권고 무용 — 손절·청산·트레일링 파라미터만 권고
- weight_reasoning 에 매크로 영향 (예: "defensive 레짐 + VIX 28 → 보수적 비중") 명시 권장
- code_review_notes 에 매크로 의존 로직 도입 제안 가능 (예: VIX 25↑ 시 자동 매수 중단)
```

### D. 회귀 가드

**`tests/unit/engine/test_recommendation_market_regime_payload.py` (신규)** — 9 케이스:
- A: `regime.empty()` 시 user_payload 에 `market_regime` 키 없음
- B: `regime is None` 시 user_payload 에 `market_regime` 키 없음
- C: 매크로 활성 (`regime.regime="defensive"`) → user_payload["market_regime"] dict 포함
- D: dict 내용 검증 (11+1 키 = 12)
- E: `_classify_vix()` 분류 (4 케이스)
- F: `_classify_fear_greed()` 분류 (5 케이스)
- G: `to_advisor_dict()` 가 raw_response/raw 같은 민감 필드 제외 검증
- H: SYSTEM_PROMPT 에 매크로 가이드 키워드 포함 검증
- I: 5/15 자문 회귀 — regime 비활성 시 user_payload 가 사이클 1 의 8 필드 그대로

**`tests/integration/test_recommendation_with_market_regime.py` (신규)** — 3 케이스:
- A: `DKSTOCK_REGIME_ENABLED=false` → 자문 정상 (매크로 미포함)
- B: 활성 + defensive → user_payload market_regime 포함 + OpenAI 호출 검증 (mock)
- C: 매크로 fetch 실패 → graceful (자문 정상 진행)

### E. 문서 동기화

- `src/engine/CLAUDE.md`: recommendation_engine 사이클 4 1 행
- `_workspace/00_leader_trading_rules.md`: 사이클 4 섹션
- `docs/HARNESS_CHANGELOG.md`: 사이클 4 1 행
- `CLAUDE.md` (루트): 핵심 안전 규칙 — 본 사이클은 핵심 안전 규칙 신규 등록 없음 (자문 통합만)

### F. 마이그 없음

코드 + SYSTEM_PROMPT 변경만. DB 스키마 영향 0.

## 안전 원칙

- graceful fallback: regime 비활성/empty/None 시 분기 skip → 사이클 1 의 8 필드 그대로 (회귀 0)
- 5/18 자문 첫 발화 안전: `DKSTOCK_REGIME_ENABLED=false` 운영 상태 → 기존 동작
- 운영 매매 흐름 미침범: recommendation_engine 만 변경
- 5/15 자문 row 영향 없음: 소급 재계산 안 함
- commit/push 자동 금지
