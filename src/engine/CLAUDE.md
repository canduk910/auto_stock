# CLAUDE.md — src/engine/ (매매 엔진)

다중 전략 아키텍처. StrategyBase 추상 클래스 기반 플러그인 구조.

## 아키텍처

```
StrategyBase (추상)
├── MomentumStrategy (상한가 모멘텀)
└── VolatilityBreakoutStrategy (변동성 돌파)

StrategyRegistry ← 전략 등록/비중/중복 방지
    ↑
RiskManager (on_tick → registry 순회 → 전략별 신호 체크)
    ↑
OrderEngine (strategy_id 태깅 → 체결 시 올바른 전략에 포지션)
    ↑
TradingScheduler (registry 기반 boot/run/settle)
```

## 모듈별 역할

### strategy_base.py — 추상 베이스
- `StrategyBase`: 모든 전략이 구현할 추상 메서드 (prepare, check_buy_signal, check_exit_signal, calc_buy_quantity)
- `Signal`: NONE, BUY, STOP_LOSS, NEXT_DAY_CLEAR, TRAILING_STOP, FORCE_CLEAR
- `Position`: ticker, buy_price, quantity, order_no, strategy_id, buy_date, is_next_day(프로퍼티)
- `StrategyState`: 전략별 독립 상태 (positions, pending_buys, total_investment, daily_realized_pnl)
- `StrategyConfig`: strategy_id, name, enabled, weight, params

### strategy_registry.py — 전략 관리
- register/get/all/enabled: 전략 등록/조회
- allocate_funds(total_asset): 비중 기반 자금 분배
- update_weights(weights): 비중 변경
- is_ticker_held_by_any(ticker): 전략 간 중복 매수 방지
- get_strategies_status(): 전략별 상태 반환

### strategies/momentum.py — 상한가 모멘텀
- 전일종가 대비 +29% 돌파 매수 (돌파 순간만, 상한가 30% 제외)
- 매수가 대비 -7.5% 손절
- 익일 청산: 갭상승 +10% → 트레일링 스탑 -2% / 그 외 즉시 매도
- `_next_day_clear_pending`: 익일 청산 시가 안정화 대기 플래그 (check_exit_signal에서 NEXT_DAY_CLEAR 억제, 손절은 유지)
- 파라미터: DEFAULT_PARAMS 딕셔너리

### strategies/volatility_breakout.py — 변동성 돌파
- _scan_universe(): 코스피+코스닥 전체에서 시총/거래대금 조건 필터 (Settings에서 조건 변경 가능)
- prepare(): 스캔 종목의 21일 일봉 → K값(20일 평균 노이즈) → Target_Offset 계산
- 시가 확정 후 Target_Price = 시가 + offset
- current_price >= target_price 시 매수
- 매수가 대비 -3% 손절
- 15:20 전량 강제 청산

### risk.py — 리스크 관리
- on_tick(): ticker_prices 갱신(1회) → registry.enabled() 순회 → 전략별 exit/buy 신호
- 중복 매수 방지: registry.is_ticker_held_by_any()

### order_engine.py — 주문 실행
- execute_buy(ticker, price, strategy): 전략별 calc_buy_quantity, state 참조
- execute_sell(ticker, signal, strategy_id): `_selling` set으로 중복 매도 차단
- _order_ticker: order_no → ticker 매핑 (체결통보 종목코드 보정)
- _order_strategy: order_no → strategy_id 매핑
- 체결통보: _order_ticker로 정확한 종목 → 올바른 전략에 포지션 등록/제거
- 매수 체결 시 DB positions에 저장, 매도 체결 시 DB에서 삭제
- 매도 체결 시 sold_today에 등록 (당일 재매수 차단)
- 체결통보 처리 실패 시 안전장치: ticker 매핑 실패 → pending_buys 제거, strategy 미발견 → _selling 해제

### scheduler.py — 스케줄 관리
- StrategyRegistry 생성, 전략 등록
- _boot(): DB positions 우선 복구 → KIS 잔고 교차 검증 (trade_history에서 전략 매핑) → 미체결 주문 복구 (db_strategy_map)
- _load_strategy_config(): DB strategy_config에서 비중/파라미터 복구
- WebSocket 연결 후 **체결통보 구독** (실전: H0STCNI0 + HTS ID, 모의: H0STCNI9 + 계좌번호)
- 09:00 익일 청산: `_next_day_clear_pending=True` → 60초 시가 안정화 대기 → WebSocket 실제 시가(ticker_prices)로 갭률 판단 → 청산/트레일링
- 09:01 변동성돌파 시가 확정 (WebSocket 캐시 → KIS API 폴백)
- 15:20 강제 청산, _settle(): 전략별 + 합산 daily_performance 기록 + `_reset_daily_state()`로 일간 상태 전체 초기화
- run_daily(): 매일 08:20 자동 시작, 주말 건너뜀, **매일 시작 전 DB auto_start 설정 재확인** (`_is_auto_start_enabled()`)
- 중간 시각 시작 대응: 현재 시각 이후 스케줄부터 실행
- _sync_positions_from_balance(): 15분 주기 체결통보 누락 보완

### scanner.py — 종목 스캔
- scan_stocks(): 모멘텀용 등락률 순위 스캔
- subscribe_filtered_stocks(tickers, extra_tickers): 모멘텀 + 변동성돌파 종목 합집합 구독
- 공용 데이터: ticker_names, ticker_prices, ticker_prev_close, ticker_market_info

## 새 전략 추가 시
1. `strategies/` 에 StrategyBase 서브클래스 작성 (prepare, check_buy_signal, check_exit_signal, calc_buy_quantity)
2. `scheduler.py` __init__에 registry.register() 추가
3. 필요 시 scanner.py에 스캔 함수 추가
4. _workspace/00_leader_trading_rules.md에 전략 명세 추가

## 수정 시 주의사항
- 전략 파라미터는 각 전략 클래스의 DEFAULT_PARAMS에서 관리 (Settings 페이지에서 런타임 변경 가능, DB 영속화)
- **`position_ratio`는 전략 할당 자금 기준** — 순자산 전체가 아님 (순자산 × 전략비중 × position_ratio)
- Position에 strategy_id 필수 — 체결통보에서 올바른 전략으로 라우팅
- **체결통보(H0STCNI0/9) 구독을 절대 제거하지 말 것** — 구독 없으면 포지션 등록 불가 → 손절 불가
- **uvicorn 단일 워커 필수** — 다중 워커 시 스케줄/포지션/WebSocket 중복
- 매수 신호는 반드시 "돌파 순간" 감지 (이전 틱 < 기준가 AND 현재 틱 >= 기준가)
- **익일 청산은 반드시 scheduler에서 60초 대기 후 처리** — on_tick에서 즉시 청산 금지 (`_next_day_clear_pending` 가드)
- 익일 청산 갭률은 `ticker_prices[ticker]["open_price"]`(WebSocket 실제 시가) 사용 — `high_since_buy` 사용 금지 (전일 고가 혼입 위험)
- order_engine의 매도 재시도 로직 제거 금지
- 모든 TR_ID는 settings.get_tr_id() 사용
- **`_reset_daily_state()` 제거 금지** — 정산 후 상태 초기화가 없으면 pending_buys/positions/sold_today가 다음 날까지 잔류
- **체결통보 실패 시 pending_buys/_selling 정리 로직 제거 금지** — 매핑 실패 시 해당 종목이 영구 차단됨
