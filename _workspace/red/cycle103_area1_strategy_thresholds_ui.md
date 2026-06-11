# 사이클 103 영역 1 — UI 손절 임계 가시화 (Strategies.tsx 신규 페이지)

**명세 출처**: 사용자 결정 사이클 103 (Q10'=B, 2026-06-11) — 영역 1 = 트레이딩 대시보드 각 전략 카드 영역 4 임계 영속 보강
**행위**: `/strategies` 신규 페이지 = 각 전략 카드 4 임계 (`stop_loss_rate` / `daily_loss_limit` / `trailing_stop_rate` / `position_ratio`) 영구 실시간 표시 + 한글 라벨 + graceful 영역

## 영속 의무 매트릭스 (HIGH)

- 사이클 41 StrategyFunnel 4 카드 패턴 영속
- 사이클 65 H3 useQuery retry:1 영속
- 사이클 68 KST 영속
- 사이클 89 한글 친숙 용어 + 사이클 언급 0 영속
- 사이클 102 G-REJECT 영속

## 영역 1 데이터 출처 (기존 GET /api/strategies 영역 활용)

- API: `GET /api/strategies` (`frontend/src/api/trading.ts::getStrategies` 기존 영역)
- 응답 영역: `strategies[].params` JSONB (`stop_loss_rate` / `daily_loss_limit` / `trailing_stop_rate` / `position_ratio` 4 키 영속)
- 빈 응답 시: `params={}` graceful 영속 (HIGH-4)

## 회귀 가드 5 케이스 (HIGH 5)

### HIGH-1: Strategies.tsx 4 임계 렌더 정합

- **`frontend/src/pages/__tests__/Strategies.test.tsx::H1_render_4_thresholds`**: 각 전략 카드 (`data-testid="strategy-card-{id}"`) 영역에 4 키 영역 영속:
  - `data-testid="strategy-{id}-stop-loss-rate"` = "-7.5%" 영역
  - `data-testid="strategy-{id}-daily-loss-limit"` = "-5.0%" 영역
  - `data-testid="strategy-{id}-trailing-stop-rate"` = "-2.0%" 영역
  - `data-testid="strategy-{id}-position-ratio"` = "25%" 영역

### HIGH-2: API GET /api/strategies 영역 strategy_config.params 정합

- **`frontend/src/pages/__tests__/Strategies.test.tsx::H2_api_strategy_config_params_4keys`**: MSW 영역 `getStrategies` 응답 `strategies[].params` 영역에 4 키 영역 영속 (mock fixture 영역 영속 + 4 키 영역 영속 검증)

### HIGH-3: 한글 라벨 + 사이클 89 답습 (영문 영역 0건)

- **`frontend/src/pages/__tests__/Strategies.test.tsx::H3_korean_labels_no_english`**: 4 키 한글 라벨 영역 영속:
  - `stop_loss_rate` → "손절 임계" / "손절율"
  - `daily_loss_limit` → "일일 손실 한도"
  - `trailing_stop_rate` → "트레일링 스탑"
  - `position_ratio` → "종목당 비중"
- 영문 영역 (`stop_loss_rate` / `daily_loss_limit` 등 raw 키 표기) = 0건 영역 정적 검증

### HIGH-4: 데이터 영역 부재 시 graceful

- **`frontend/src/pages/__tests__/Strategies.test.tsx::H4_graceful_empty_params`**: MSW 영역 `params={}` 응답 시 "—" 영역 또는 0 표시 영역 영속 + React Error Boundary 미발화 영역 영속

### HIGH-5: 모바일 viewport 375px 영역 4 임계 영역 정합

- **`frontend/src/pages/__tests__/Strategies.test.tsx::H5_mobile_viewport_4_thresholds`**: 375px viewport 영역에 4 임계 영역 모두 렌더 영역 영속 (사이클 81 M-1~M-8 답습)

## Red 단계 (production 코드 변경 0)

- `frontend/src/pages/Strategies.tsx` = **신규 페이지 미존재** → 5 신규 테스트 영역 모두 RED
- `frontend/src/App.tsx::navItems` = `Strategies` 미등록 → 영역 0 영역 통합 영역 (사이클 103 영역 0 8 메뉴 + 영역 1 9 메뉴 = 합산 결정 = 사용자 결정 영속 미명시 영역 → 사이클 103 영역 0 = 8 메뉴 영역 영속 + 영역 1 Strategies = **9 메뉴** 영역 영속)
- 사이클 103 영역 1 = 모든 신규 테스트 영역 RED 영구 영속

## Green 단계 인계 (frontend-dev 영역)

1. `frontend/src/pages/Strategies.tsx` 신규 (~200L, 6 전략 카드 영역 + 4 임계 표시)
2. `frontend/src/App.tsx` 갱신 (navItems 8→9 + lazy import + Route + MobileMenuLabel)
3. `frontend/src/api/trading.ts::getStrategies` 기존 영역 활용 (변경 0)
4. `frontend/src/test/handlers.ts` MSW 영역 `params` 4 키 영역 보강 (영역 영속)

## 영속 의무 영속 검증 (Green 단계 후)

- 사이클 65 H3 retry:1 영속 (Strategies useQuery 영역 1건)
- 사이클 68 KST 영속 (시각 표시 영역 부재 = 비적용 영역)
- 사이클 89 한글 라벨 영역 + 사이클 언급 0
- CLAUDE.md "절대 깨지 말 것" 8 영역 영속 (UI 레이어 한정, READ-ONLY)
