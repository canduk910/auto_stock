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

## Phase G — NXT 사전 판별 (CTPF1002R) — 2026-05-11
- `inquire_stock_basics(pdno)` → CTPF1002R 응답 파싱: `cptt_trad_tr_psbl_yn` + `nxt_tr_stop_yn` Y/N 4조합 → `nxt_tradable = (Y AND N)`
- `stock_master` 테이블 upsert + 24h staleness 판정 (`is_stale`)
- `OrderEngine._strategy_exchange(strategy_id, ticker=None)` — ticker 인자 시 `stock_master.get(ticker).nxt_tradable=False` 면 NXT/SOR → KRX 강제 다운그레이드 + `[nxt_downgrade]` 로그 1행
- scheduler `_execute_next_day_clear` — `nxt_tradable=False`이면 시가 폴링/안정화 거치지 않고 즉시 `_pending_next_day_clear` 등록 (NXT 주문 시도 0)
- `execute_sell` 거부(`is_market_closed_rejection`) 후 `stock_master.upsert_one(ticker, nxt_tradable=False)` 사후 보강

## Phase E3 — high_since_buy 일봉 폴백 (donchian_swing) — 2026-05-12
시세 미수신 누적으로 chandelier 트레일링 손절선이 매수가 부근에 동결되어 첫 갭다운에 즉시 청산되는 결함 차단. `_boot()` 직후 `donchian_swing.recompute_held_atr()` 시점에 KIS 일봉으로 매수일~전영업일 일별 high max 계산해 `high_since_buy` 보정.
- A: 매수일=어제, 일봉 어제 high=120000 > buy_price=115600 → `high_since_buy=120000` 보정 + `update_high` DB UPDATE 호출
- B: 매수일=오늘(buy_date==today_kst) → 보정 skip (당일은 buy_price가 진실, fetch 호출도 안 함)
- C: 일봉 응답 빈 리스트(`[]`) → 보정 skip, `high_since_buy` 변경 없음
- D: `fetch_daily_candles` 가 예외 raise → 해당 종목 skip + ERROR/exception 로그, 다른 포지션 보정 정상 진행
- E: 일별 high 모두 buy_price 미만(매수 후 하락만) → 보정 안 함, `high_since_buy` 변경 없음
- F: 일봉에 매수일 당일/오늘 데이터 포함 → 매수일 < bsop_date < today 범위만 max 계산 (경계 엄격)
- G: `pos.buy_date > today_kst` (비정상) → 보정 skip + WARNING 로그
- H: 다중 보유 3종목, 1종목 fetch 실패 → 나머지 2종목 정상 보정, sequential await (병렬 금지)
- 회귀: 기존 `recompute_held_atr` ATR 재계산 로직이 깨지지 않음 (high_since_buy 보정이 ATR 계산을 간섭하지 않음)
