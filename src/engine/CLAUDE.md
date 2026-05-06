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
- `StrategyState`: 전략별 독립 상태 (positions, pending_buys, total_investment, daily_realized_pnl, **cached_buyable_qty/amount/at**, **buy_blocked_until**) + 헬퍼(`is_buy_blocked / block_buy / unblock_buy / is_buyable_cache_fresh`)
- `StrategyConfig`: strategy_id, name, enabled, weight, params

### strategy_registry.py — 전략 관리
- register/get/all/enabled: 전략 등록/조회
- allocate_funds(total_asset): 비중 기반 자금 분배
- update_weights(weights): 비중 변경
- is_ticker_held_by_any(ticker): 전략 간 보유/주문 중 검사 (포지션 복구 경로 등)
- is_ticker_sold_today_by_any(ticker): 전략 간 당일 매도 여부 검사
- is_ticker_blocked_for_buy(ticker): 매수 차단 통합 가드 — 보유 OR 주문중 OR 당일매도 (RiskManager / OrderEngine 매수 입구에서 사용)
- get_strategies_status(): 전략별 상태 반환

### strategies/momentum.py — 상한가 모멘텀
- 전일종가 대비 +29% 돌파 매수 (돌파 순간만, 상한가 30% 제외)
- 매수가 대비 -7.5% 손절
- 익일 청산: 갭상승 +10% → 트레일링 스탑 -2% / 그 외 즉시 매도
- `_next_day_clear_pending`: 익일 청산 시가 안정화 대기 플래그 (check_exit_signal에서 NEXT_DAY_CLEAR 억제, 손절은 유지)
- 파라미터: DEFAULT_PARAMS 딕셔너리

### strategies/volatility_breakout.py — 변동성 돌파
- _scan_universe(): 거래량순위 API(`FHPST01710000`) 응답 1건으로 후보 + 시총·전일 거래대금 산출. `prdy_vol × (stck_prpr - prdy_vrss)`로 전일 거래대금 추정 → 시간 의존 제거(휴장 직후 첫 영업일 0종목 확정 이슈 해결). 0종목 확정 시 `ERROR` 로그 + `system_logs` 기록
- prepare(): 스캔 종목의 21일 일봉 → K값(20일 평균 노이즈) → Target_Offset 계산. 추가로 candles[0]의 stck_clpr을 `scanner.ticker_prev_close`에 사전 등록 (09:30 scan_stocks 이전에도 등락률 필터 동작 보장)
- 시가 확정 후 Target_Price = 시가 + offset
- current_price >= target_price 시 매수 (09:00:05 시가 확정 직후부터 매매 가능)
- 매수가 대비 -3% 손절
- 15:20 전량 강제 청산

### strategies/donchian_swing.py — 20일 신고가 스윙 (추세추종 멀티데이)
- _scan_universe(): **코스피200 + 코스닥150 고정 유니버스**(`scanner.KOSPI_200_TICKERS` + `KOSDAQ_150_TICKERS` 합집합) → `fetch_stock_detail`로 시총/거래대금 사후 컷(휴면·미달 종목 제거). 거래량순위 API 미사용 — 추세추종 부적합 + 시점 의존 제거. 0종목 확정 시 `ERROR` 로그 + `system_logs` 기록
- prepare(): 유니버스 스캔 → 60일 일봉 fetch → Donchian 20일 신고가 + 60일 EMA 우상향 + 거래대금 1.5배 검증
- recompute_held_atr(): _boot 후 보유 종목 ATR 재계산 (멀티데이 트레일링 유지용)
- check_buy_signal(): 09:05~09:30 시간 가드 + 갭 +3%↑ 스킵 + 1회만 매수
- check_exit_signal(): ATR×2 Chandelier 트레일링 + 하드 손절 -7% (시간 손절 없음)
- check_force_clear(): 빈 리스트 — 15:20 강제 청산 제외
- 시스템 최초의 멀티데이 보유 전략 — positions DB 영속화 + _boot DB 복구로 일자 넘어 유지

### strategies/long_tail_volatility.py — 롱테일 변동성 돌파 (VB + 상한가 모멘텀 합성)
- VB 방식 조기 진입 + 상한가 도달 시 모멘텀 방식 익일 청산
- prepare(): VB와 동일 스캔(거래량순위 응답으로 시총·전일 거래대금 산출) + K값 계산 + 연속상한가 필터(`_is_consecutive_limit_up`) + ticker_prev_close 사전 등록. 0종목 확정 시 `ERROR` 로그 + `system_logs` 기록
- 매수: 시가 + (전일Range × K) 돌파 + 전일대비 `min_prdy_rate`% 이상 (09:00:05부터 매매 가능, VB와 동일 시점)
- 2단계 청산: `_limit_up_reached` set으로 모드 관리
  - 당일 모드(기본): 손절 `intraday_stop_loss`(-3%), 15:20 강제 청산
  - 상한가 모드(`limit_up_threshold` 도달): 손절 `overnight_stop_loss`(-5%), 익일 갭/트레일링 청산, 15:20 강제 청산 제외
- `_next_day_clear_pending`: 익일 청산 시가 안정화 대기 플래그 (momentum과 동일)

### risk.py — 리스크 관리
- on_tick(): ticker_prices 갱신(1회) → registry.enabled() 순회 → 전략별 exit/buy 신호
- 중복 매수 방지: registry.is_ticker_blocked_for_buy() — 보유/주문중/당일매도 통합 검사 (전략 간)

### order_engine.py — 주문 실행
- execute_buy(ticker, price, strategy): 전략별 calc_buy_quantity, state 참조. 진입 시 `state.is_buy_blocked()` → 차단, 캐시(`BUYABLE_CACHE_TTL=60s`) 유효 시 KIS `get_buyable()` 생략. `max_buy_quantity<=0` 또는 `KisApiError(insufficient_cash)` 시 `state.block_buy(now+BUY_BLOCK_DURATION=900s)`로 락 등록
- execute_sell(ticker, signal, strategy_id): `_selling` set으로 중복 매도 차단. `KisApiError(insufficient_quantity)` 시 3회 재시도 생략하고 즉시 break + 메모리 포지션 + DB positions 정리(다음 잔고 sync에서 보정)
- 주문번호 매핑(_order_qty/_order_strategy/_order_ticker/_pending_buy_orders) 등록은 `place_order` 응답 직후 동기 영역에서 수행 — `await insert_trade` 진입 전. 시장가 즉시체결 시 체결통보가 insert_trade await 도중 도착해도 매핑이 보장된다
- _order_ticker: order_no → ticker 매핑 (체결통보 종목코드 보정)
- _order_strategy: order_no → strategy_id 매핑 — 미등록 시 기본값 "momentum" 사용. 매핑 누락은 잘못된 전략에 INSERT/포지션 등록을 유발하므로 위 동기 등록 순서 필수
- _completed_orders: 체결통보가 REST 응답보다 먼저 도착한 order_no를 추적하는 set. `_handle_*_fill`에서 `update_trade_status` 영향 row 0건이면 COMPLETED 직접 INSERT + set에 등록 → execute_buy/sell이 응답 후 set 체크해 PENDING INSERT 생략(중복 row 방지)
- 체결통보: _order_ticker로 정확한 종목 → 올바른 전략에 포지션 등록/제거
- 매수 체결 시 DB positions에 저장 + `state.cached_buyable_at = 0`(가용액 캐시 무효화), 매도 체결 시 DB에서 삭제
- 매도 체결 시 sold_today에 등록 (당일 재매수 차단)
- 체결통보 처리 실패 시 안전장치: ticker 매핑 실패 → pending_buys 제거, strategy 미발견 → _selling 해제

### scheduler.py — 스케줄 관리
- StrategyRegistry 생성, 전략 등록
- _boot(): DB positions 우선 복구 → KIS 잔고 교차 검증 (trade_history에서 전략 매핑) → 미체결 주문 복구 (db_strategy_map)
- _load_strategy_config(): DB strategy_config에서 비중/파라미터 복구
- WebSocket 연결 후 **체결통보 구독** (실전: H0STCNI0 + HTS ID, 모의: H0STCNI9 + 계좌번호)
- **08:55 사전 구독** (`TIME_PRESUBSCRIBE`): `_collect_presubscribe_tickers()` — 돌파 전략(VB+LTV) 스캔 종목 + 스윙 전략(donchian_swing) 스캔 종목(`_collect_swing_tickers()`) + 모든 전략 보유 포지션 합집합을 WebSocket 사전 구독 → 09:00 시가 즉시 수신. 돌파/스윙 유니버스가 비어있으면 각각 prepare 재실행(KIS API 일시 장애 대비)
- 09:00:00 익일 청산은 백그라운드 task(`asyncio.create_task`)로 실행하여 60초 안정화 대기를 비차단으로 처리. 동시에 `_confirm_breakout_open_prices()`(0.5초 간격 5초 폴링 → 미확정 종목 KIS API 폴백) 즉시 실행
- **09:00:05 돌파 전략 매매 시작** (`TIME_VB_OPEN_CONFIRM = time(9, 0, 5)`): VB + LTV 시가 확정 직후 진입(`_phase = "vb_trading"`)
- 09:30 모멘텀 스캔: `scan_stocks()` + 통합 구독(`extra_tickers = 돌파(VB+LTV) + 스윙(donchian_swing)`), `_phase = "trading"`
- 15:20 강제 청산: `_force_clear_intraday_strategies()` — VB + LTV(상한가 미도달 종목) 공용. _settle(): 전략별 + 합산 daily_performance 기록 + `_reset_daily_state()`로 일간 상태 전체 초기화
- _resolve_open_price(): 시가 폴링(0.5초 간격) → KIS `fetch_stock_detail()` 폴백 헬퍼. `_execute_next_day_clear()`에서 익일청산 시가 미수신 시 호출
- run_daily(): 매일 08:20 자동 시작, 주말+공휴일 건너뜀(KIS `chk-holiday` API로 개장 여부 확인 후 다음 영업일까지 대기), **매일 시작 전 DB auto_start 설정 재확인** (`_is_auto_start_enabled()`)
- 중간 시각 시작 대응: 현재 시각 이후 스케줄부터 실행 (09:00:05 이후 부팅 시에도 사전구독 + 시가확정 즉시 실행)
- _sync_positions_from_balance(): 15분 주기 체결통보 누락 보완. 종료 시 모든 전략의 `state.unblock_buy()`로 매수 락/매수가능 캐시 일괄 해제 — 가용액 회복 가능성 반영

### scanner.py — 종목 스캔
- scan_stocks(): 모멘텀용 등락률 순위 스캔
- subscribe_filtered_stocks(tickers, extra_tickers): 모멘텀 + 돌파(VB+LTV) + 스윙(donchian_swing) 종목 합집합 구독
- KOSPI_200_TICKERS / scan_kospi200(), KOSDAQ_150_TICKERS / scan_kosdaq150(): 정적 시총 상위 리스트 (donchian_swing 고정 유니버스용)
- 공용 데이터: ticker_names, ticker_prices, ticker_prev_close, ticker_market_info

### recommendation_engine.py / recommendation_metrics.py — 전략수정 AI자문
- 16:00 `generate_recommendations()`: 전략별 metrics(승률/평균손익/손절률/누적수익률 등) 집계 → OpenAI 호출 → `parameter_recommendations`에 INSERT (status: pending)
- 동일 (target_date, strategy_id) unique 보장. 재실행 시 중복은 None 반환
- 사용자가 `/api/recommendations/{id}/apply`로 키 선택 적용 → `strategy_config.params` 갱신 + DB status를 applied/partial로 갱신
- `expire_pending_before(target_date)`: 이전 영업일 pending 자동 만료

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
- **체결통보 선행 race 가드(`_completed_orders` + UPDATE 0건 보정 INSERT) 제거 금지** — 시장가 즉시체결 + REST 응답 지연 시 trade_history가 PENDING으로 영구 잔존하던 이슈를 해결한다. 매수·매도 양쪽 모두 가드 필수
- **주문번호 매핑(_order_qty/_order_strategy/_order_ticker/_pending_buy_orders) 등록을 `await insert_trade` 뒤로 옮기지 말 것** — `place_order` 응답 직후 동기 영역에서 등록해야 시장가 즉시체결 시 체결통보가 insert_trade await 도중 도착해도 올바른 전략으로 라우팅된다. 매핑 누락 시 기본값 "momentum"으로 잘못 INSERT되어 손익 0 + 잘못된 strategy로 기록된 사례가 있었음
- **매수가능 캐시 TTL(`BUYABLE_CACHE_TTL=60s`) / 매수 락 지속(`BUY_BLOCK_DURATION=900s`)** 변경 시 잔고 sync 주기(15분)와 정합성 확인. sync 종료 시 `unblock_buy()`로 일괄 해제되므로 BUY_BLOCK_DURATION ≈ sync 주기가 자연스럽다
