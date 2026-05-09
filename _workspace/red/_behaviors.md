# Phase A~F 행위 분해 — 누적 카탈로그

각 사이클에서 검증 가능한 행위로 분해된 매매 시스템 명세를 기록한다.
신규 행위는 이 파일에 추가하고, 회귀 테스트는 `_workspace/regression/<slug>.md` 에 별도 등록.

## Phase A — 인프라 부트스트랩
- KIS REST 호출 메트릭 누적/리셋
- TokenManager 토큰 만료 10분 전 갱신 판정
- TokenManager 캐시 저장/로드 라운드트립

## Phase B — 전략 엔진
- StrategyState 잔고 락(900s) / 매수가능 캐시(60s TTL) / per-ticker low_funds cooldown
- StrategyRegistry 비중 분배 + 전략 간 통합 매수 차단
- Momentum: +29% 돌파 순간 / -7.5% 손절 / 익일 갭<10% 즉시 / 갭>=10% 트레일링-2% / `_next_day_clear_pending` 손절만 유지
- VolatilityBreakout: 보드별 K값 분리 / 보드별 first tick 기록 / -3% 손절
- LongTailVolatility: min_prdy_rate 진입 / `_limit_up_reached` 모드 전환 / 익일 모드 -5%
- DonchianSwing: 09:05~09:30 시간 가드 / 갭 +3% 스킵 / ATR×2 chandelier 트레일링
- SessionTracker: 시각 기반 활성 보드 / is_tradable 교집합

## Phase C — order_engine + risk
- execute_buy 매핑 등록 → 응답 → PENDING INSERT 또는 PENDING 생략(race)
- handle_execution_notice 체결 → save_position / sold_today
- _completed_orders set: WS 선행 race 가드
- block_buy(insufficient_cash) / block_low_funds(calc_qty=0) 분리
- RiskManager.on_tick: 보드 가드 + 자금 사전 가드 + 청산 우선

## Phase D — 시간 기반 스케줄러
- _force_clear_main_only: POST_NXT 활성 전략 보존
- _execute_next_day_clear: pending 플래그 lifecycle + 갭률 분기
- _confirm_breakout_open_prices: 보드별 target 계산 + KIS 폴백
- _reset_daily_state: 모든 state + scanner 전역 dict + STATIC 재시드
- _is_auto_start_enabled: DB 우선 + settings 폴백
- _collect_presubscribe_tickers: 합집합 + 중복제거

## Phase E — 라우트 계약 + 프론트 단위
- TestClient(lifespan 미실행) + 싱글톤 scheduler 모킹
- 7개 라우트 그룹 19+ 엔드포인트 스키마/에러 분기
- ConfirmModal/InfoTooltip/TradingStatusContext 동작
- 6개 API wrapper 응답 unwrap

## Phase F — E2E 스모크 + CI 게이트 + 회귀 패턴
- 5개 페이지 진입 검증 (route mock 인프라)
- coverage 게이트 60% baseline (점진적 70 → 80 상향)
- 회귀 등록/영구화 절차 정립 (`_workspace/regression/`)
