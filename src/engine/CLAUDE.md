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

### strategies/volatility_breakout.py — 변동성 돌파 (KRX+NXT 보드별 분리)
- _scan_universe(): 거래량순위 API(`FHPST01710000`) 응답 1건으로 후보 + 시총·전일 거래대금 산출. `prdy_vol × (stck_prpr - prdy_vrss)`로 전일 거래대금 추정 → 시간 의존 제거. 0종목 확정 시 `ERROR` 로그 + `system_logs` 기록
- prepare(): 22일 일봉 → K값(20일 평균 노이즈) + 전일 Range → `target_offset_base = prev_range × k`. candles[0]==오늘이면 candles[1]을 전일로 사용. `prev_range/target_offset_base==0` 종목 skip
- **보드별 시가/타겟가 분리** (Phase 5 Q1=C): `_targets[ticker] = {target_offset_base, k, prev_range, boards: {board: {open_price, target_price, target_offset}}}`. `on_open_price_confirmed(ticker, open_price, board)` 호출 시 `target_offset = base × k_value_{board}` 곱 후 보드별 dict에 저장. `_open_confirmed[ticker] = {board: bool}`, `_prev_price[ticker] = {board: int}` (보드별 돌파 순간 분리 감지)
- DEFAULT_PARAMS: `tradable_boards = ["pre_nxt", "main", "post_nxt"]`, `k_value_krx_main = 1.0`, `k_value_nxt_pre = 1.0`, `k_value_nxt_post = 1.0`, `exchange = "KRX"` (Phase 4: 주문 라우팅)
- check_buy_signal(): `_resolve_active_board()`로 현재 활성 보드(main 우선) 결정 → 해당 보드의 target_price 돌파 순간 매수
- 매수가 대비 -3% 손절
- 15:20 강제 청산 — POST_NXT가 `tradable_boards`에 있으면 보류 (19:50 매수 중단까지 유지)

### strategies/donchian_swing.py — 20일 신고가 스윙 (추세추종 멀티데이)
- _scan_universe(): **코스피200 + 코스닥150 고정 유니버스**(`scanner.KOSPI_200_TICKERS` + `KOSDAQ_150_TICKERS` 합집합) → `fetch_stock_detail`로 **시총 사후 컷만** 적용. 거래대금 컷은 `prepare()`의 volume_multiplier 1.5×에서 일원화 — `acml_tr_pbmn`(당일 누적)은 장 시작 전 0이라 시점 의존성 발생. 거래량순위 API 미사용 — 추세추종 부적합. 0종목 확정 시 `ERROR` 로그 + `system_logs` 기록. **종목명 fallback**: `hts_kor_isnm`만 신뢰(시장 분류명 `rprs_mrkt_kor_name`은 종목명 부적합이라 fallback 제거), KIS가 빈 응답 시 `scanner.STATIC_TICKER_NAMES`로 보강
- prepare(): 유니버스 스캔 → 60일 일봉 fetch → Donchian 20일 신고가 + 60일 EMA 우상향 + 거래대금 1.5배 검증. **단계별 통과 카운트**(`universe_candidates → universe_filtered → candle_fetch_ok → donchian_pass → ema_uptrend_pass → volume_pass → atr_pass → final_prepared`)를 `_scan_stats`에 누적. **`candles[0].stck_bsop_date == 오늘`이면 candles[1]을 전일로 사용**(VB/LTV와 동일 prev_idx 분기) — 장중 prepare 재실행 시 candles[0]이 오늘 부분봉으로 들어와 신고가 돌파 판정이 어긋나던 결함 차단(5/8 08:20 prepare donchian_pass=0 vs 10:18 재기동 prepare donchian_pass=8 차이가 발생했던 사례)
- get_scan_stats(): 마지막 prepare의 단계별 카운트 반환 — `strategy_registry.get_strategies_status()` `scan_stats` 필드로 노출되어 프론트 ScanMonitor 깔때기 시각화에 사용
- recompute_held_atr(): _boot 후 보유 종목 ATR 재계산 (멀티데이 트레일링 유지용)
- check_buy_signal(): 09:05~09:30 시간 가드 + 갭 +3%↑ 스킵 + 1회만 매수
- check_exit_signal(): ATR×2 Chandelier 트레일링 + 하드 손절 -7% (시간 손절 없음)
- check_force_clear(): 빈 리스트 — 15:20 강제 청산 제외
- 시스템 최초의 멀티데이 보유 전략 — positions DB 영속화 + _boot DB 복구로 일자 넘어 유지

### strategies/long_tail_volatility.py — 롱테일 변동성 돌파 (VB + 상한가 모멘텀 합성)
- VB 방식 조기 진입 + 상한가 도달 시 모멘텀 방식 익일 청산
- prepare(): VB와 동일 스캔(거래량순위 응답으로 시총·전일 거래대금 산출) + K값 계산 + 연속상한가 필터(`_is_consecutive_limit_up(start=prev_idx)`) + ticker_prev_close 사전 등록. **VB와 동일 prev_idx 분기**(candles[0]==오늘이면 candles[1]을 전일로) + prev_range/target_offset==0 skip. 0종목 확정 시 `ERROR` 로그 + `system_logs` 기록
- 매수: 시가 + (전일Range × K) 돌파 + 전일대비 `min_prdy_rate`% 이상 (09:00:05부터 매매 가능, VB와 동일 시점)
- 2단계 청산: `_limit_up_reached` set으로 모드 관리
  - 당일 모드(기본): 손절 `intraday_stop_loss`(-3%), 15:20 강제 청산
  - 상한가 모드(`limit_up_threshold` 도달): 손절 `overnight_stop_loss`(-5%), 익일 갭/트레일링 청산, 15:20 강제 청산 제외
- `_next_day_clear_pending`: 익일 청산 시가 안정화 대기 플래그 (momentum과 동일)

### risk.py — 리스크 관리
- on_tick(): ticker_prices 갱신(1회) → registry.enabled() 순회 → 전략별 exit/buy 신호
- **보드 가드** (Phase 8): 매수 신호 평가 전 `session_tracker.is_tradable(strategy_id, params)`로 현재 활성 보드가 전략의 `tradable_boards`에 있는지 확인 — 비활성 보드에서는 신호 평가 자체 skip
- PR7 롤백 이력: 동일가 연속 틱 skip 가드는 **VB 시가 확정 직후 _prev_price=0 first-tick skip + 동일가 PR7 skip이 겹쳐 _prev_price가 영원히 0으로 유지 → 매수 신호 끝까지 미발생** 결함이 발견되어 롤백(2026-05-11). 이벤트 루프 CPU보다 매수 기회 누락 손실이 크다는 판단. 향후 동일 최적화 시 strategy._prev_price 초기화 보장 필수
- 중복 매수 방지: registry.is_ticker_blocked_for_buy() — 보유/주문중/당일매도 통합 검사 (전략 간)

### order_engine.py — 주문 실행
- execute_buy(ticker, price, strategy): 전략별 calc_buy_quantity, state 참조. 진입 시 `state.is_buy_blocked()` + `state.is_low_funds_blocked(ticker)` → 차단, 캐시(`BUYABLE_CACHE_TTL=60s`) 유효 시 KIS `get_buyable()` 생략. `max_buy_quantity<=0` 또는 `KisApiError(insufficient_cash)` 시 `state.block_buy(now+BUY_BLOCK_DURATION=900s)`로 락 등록. **`calc_buy_quantity()<=0`인 종목은 `state.block_low_funds(ticker, now+LOW_FUNDS_COOLDOWN=900s)` 등록** — 매 틱 같은 종목에서 "매수 수량 0" 경고 반복/무의미 호출 차단
- execute_sell(ticker, signal, strategy_id): `_selling` set으로 중복 매도 차단. `KisApiError(insufficient_quantity)` 시 3회 재시도 생략하고 즉시 break + 메모리 포지션 + DB positions 정리(다음 잔고 sync에서 보정)
- 주문번호 매핑(_order_qty/_order_strategy/_order_ticker/_pending_buy_orders) 등록은 `place_order` 응답 직후 동기 영역에서 수행 — `await insert_trade` 진입 전. 시장가 즉시체결 시 체결통보가 insert_trade await 도중 도착해도 매핑이 보장된다
- _order_ticker: order_no → ticker 매핑 (체결통보 종목코드 보정)
- _order_strategy: order_no → strategy_id 매핑 — 미등록 시 기본값 "momentum" 사용. 매핑 누락은 잘못된 전략에 INSERT/포지션 등록을 유발하므로 위 동기 등록 순서 필수
- _completed_orders: 체결통보가 REST 응답보다 먼저 도착한 order_no를 추적하는 set. `_handle_*_fill`에서 `update_trade_status` 영향 row 0건이면 COMPLETED 직접 INSERT + set에 등록 → execute_buy/sell이 응답 후 set 체크해 PENDING INSERT 생략(중복 row 방지)
- 체결통보: _order_ticker로 정확한 종목 → 올바른 전략에 포지션 등록/제거
- 매수 체결 시 DB positions에 저장 + `state.cached_buyable_at = 0`(가용액 캐시 무효화), 매도 체결 시 DB에서 삭제
- 매도 체결 시 sold_today에 등록 (당일 재매수 차단)
- 체결통보 처리 실패 시 안전장치: ticker 매핑 실패 → pending_buys 제거, strategy 미발견 → _selling 해제

### session.py — 세션/보드 추상화 (Phase 3)
- `MarketBoard` enum: `pre_nxt`(NXT 프리 08:00~) / `krx_open`(08:30~09:00) / `main`(09:00~15:20) / `krx_after`(15:30~18:00) / `post_nxt`(NXT 애프터 15:30~20:00)
- `_BOARD_SCHEDULE`: 시각 → 활성 보드 frozenset 매핑 (H0NXMKO0 미수신 시 fallback)
- `SessionTracker`: 활성 보드 추적 + 진입/종료 콜백 발화. `tick()`을 30초 주기 `_session_loop`에서 호출
- `is_tradable(strategy_id, params)`: 현재 활성 보드 ∩ 전략 `tradable_boards`(또는 `_DEFAULT_TRADABLE_BOARDS` fallback) 비어있지 않으면 매매 가능
- `on_h0nxmko0(tr_key, mkop_cls_code, payload)`: NXT 장운영정보 수신. 명세 필드 미확정이라 현재는 코드 기록만 — 향후 정확도 보강용
- 전역: `session_tracker` 인스턴스 + `register_board_handler` 콜백을 scheduler.start()에서 등록

### scheduler.py — 스케줄 관리 (KRX/NXT 통합 운영 08:00~20:00)
- StrategyRegistry 생성, 전략 등록
- _boot(): DB positions 우선 복구 → KIS 잔고 교차 검증 (trade_history에서 전략 매핑) → 미체결 주문 복구 (db_strategy_map)
- _load_strategy_config(): DB strategy_config에서 비중/파라미터 복구 (`tradable_boards`, `exchange`, `k_value_*` 포함)
- WebSocket 연결 후 **체결통보 구독** (실전: H0STCNI0 + HTS ID, 모의: H0STCNI9 + 계좌번호) + **통합 장운영정보 구독** (실전 한정: `H0UNMKO0` / `005930`). 장운영정보는 종목 단위 구독이지만 `MKOP_CLS_CODE`는 시장 전체 공통이라 대표 종목 1개로 보드 전환 수신. SessionTracker.on_h0nxmko0 콜백이 코드 기록 + 시각 기반 tick()이 보드 결정 (코드/시각 정합성 검증 후 코드 → 보드 enum 직접 매핑 도입 예정)
- **시간 상수**: `TIME_AUTO_START 07:45 / TIME_BOOT 07:50 / TIME_PRESUBSCRIBE 07:55 / TIME_PRE_NXT_OPEN 08:00 / TIME_KRX_OPEN_CONFIRM 09:00:05 / TIME_SCAN_START 09:30 / TIME_KRX_MAIN_BUY_STOP 15:20 / TIME_KRX_MAIN_CLOSE 15:30 / TIME_NXT_POST_BUY_STOP 19:50 / TIME_RECOMMENDATION 19:50 / TIME_NXT_POST_CLOSE 20:00 / TIME_SETTLEMENT 20:10`. 기존 이름(`TIME_NEXT_DAY_CLEAR/TIME_VB_OPEN_CONFIRM/TIME_BUY_STOP/TIME_MARKET_CLOSE`)은 backwards-compat alias로 보존
- **07:55 사전 구독** (`TIME_PRESUBSCRIBE`): `_collect_presubscribe_tickers()` — 돌파(VB+LTV) + 스윙(donchian) + 모든 전략 보유 포지션 합집합을 사전 구독 → 08:00 NXT 프리 첫 거래 즉시 수신
- **08:00 NXT 프리 진입**: 익일 청산 백그라운드 task(`_execute_next_day_clear`, `NEXT_DAY_STABILIZE_SECS=30`초 안정화) + `_confirm_breakout_open_prices(board="pre_nxt")` 시가 확정. PRE_NXT 활성 전략(VB/LTV `tradable_boards`에 pre_nxt 포함)이 매매 시작 (`_phase = "pre_nxt_trading"`)
- **09:00:05 KRX 메인 시가 확정**: `_confirm_breakout_open_prices(board="main")` 재실행 — VB/LTV가 KRX 09:00 시가로 보드별 별도 target_price 계산 (`_phase = "main_trading"`)
- 09:30 모멘텀 스캔: `scan_stocks()` + 통합 구독, `_phase = "trading"`
- **15:20 KRX 메인 매수 중단 + 강제 청산**: `_force_clear_main_only` — `tradable_boards`에 POST_NXT가 있는 전략은 보유 유지, 나머지(POST_NXT 미활성 전략)만 청산
- **15:30 KRX 메인 마감 → NXT 애프터 전환**: 구독 유지(POST_NXT 종목 시세), `_phase = "post_nxt_trading"`
- **19:50 NXT 애프터 신규 매수 중단 + AI자문**: `buy_disabled = True` for all enabled strategies, `generate_recommendations()` 실행
- **20:00 NXT 애프터 종료**: `unsubscribe_all()`, `_phase = "closing"`
- **20:10 정산 + 일일 로그 분석**: `_settle()` + `generate_daily_log_report()`
- _execute_next_day_clear(): 다음 영업일 NXT 프리 첫 거래 시가 + 30초 안정화 후 즉시 청산(Q2=B). 시가 미수신 시 `_resolve_open_price()` 폴백
- _confirm_breakout_open_prices(board=None): 보드별 시가 확정. board 미지정 시 SessionTracker 활성 보드 우선순위(main → post_nxt → pre_nxt)로 결정. 해당 보드를 `tradable_boards`에 활성화한 전략만 대상
- _force_clear_main_only(): 15:20 KRX 메인 강제 청산. POST_NXT 활성 전략은 유지(19:50 매수 중단까지)
- _session_loop(): 30초 주기 `session_tracker.tick()` background task — 보드 진입/종료 이벤트 발화
- _resolve_open_price(): 시가 폴링(0.5초 간격) → KIS `fetch_stock_detail()` 폴백 헬퍼. `_execute_next_day_clear()`에서 익일청산 시가 미수신 시 호출
- run_daily(): 매일 08:20 자동 시작, 주말+공휴일 건너뜀(KIS `chk-holiday` API로 개장 여부 확인 후 다음 영업일까지 대기), **매일 시작 전 DB auto_start 설정 재확인** (`_is_auto_start_enabled()`)
- 중간 시각 시작 대응: 현재 시각 이후 스케줄부터 실행 (09:00:05 이후 부팅 시에도 사전구독 + 시가확정 즉시 실행)
- _scan_loop(): 09:30 이후 5분(`SCAN_INTERVAL=300`) 주기 — `unsubscribe_all()` 후 `scan_stocks()` 결과 + **돌파(VB+LTV) + 스윙(donchian) + 모든 전략 보유 종목 합집합**으로 재구독. 이전엔 VB만 재구독해 09:30 이후 swing/LTV/보유 종목 시세가 끊겨 손절 감시까지 누락되던 결함 차단
- _sync_positions_from_balance(): 15분 주기 체결통보 누락 보완. **strategy 매핑은 trade_history의 직전 BUY 행에서 상속**(이전 momentum 하드코딩 → 알루코류 BUY/SELL strategy 어긋남 재발 차단). 종료 시 모든 전략의 `state.unblock_buy()` + `state.clear_low_funds()`로 매수 락/매수가능 캐시 + per-ticker 투자금 부족 cooldown 일괄 해제 — 가용액 회복 가능성 반영

### scanner.py — 종목 스캔
- scan_stocks(): 모멘텀용 등락률 순위 스캔
- subscribe_filtered_stocks(tickers, extra_tickers): 모멘텀 + 돌파(VB+LTV) + 스윙(donchian_swing) 종목 합집합 구독
- KOSPI_200_TICKERS / scan_kospi200(), KOSDAQ_150_TICKERS / scan_kosdaq150(): 정적 시총 상위 리스트 (donchian_swing 고정 유니버스용)
- `STATIC_TICKER_NAMES` / `_parse_static_ticker_names()`: 모듈 import 시 1회 자기 파일을 정규식(`"(\d{6})",\s*#\s*(.+)$`)으로 파싱해 인라인 코멘트의 종목명을 dict로 추출. 모듈 로드 시 `ticker_names.update(STATIC)`로 시드 — KIS `inquire-price`가 `hts_kor_isnm`을 빈 문자열로 응답해도 종목명이 시장명으로 떨어지지 않도록 보강. 코멘트 변경 시 자동 동기화
- 공용 데이터: ticker_names, ticker_prices, ticker_prev_close, ticker_market_info

### log_analysis_engine.py — 일일 로그 분석 리포트
- 16:10 정산 직후(`_settle()` 호출 직후, `_phase = "log_analysis"`) `generate_daily_log_report()` 호출
- 당일 KST 00:00~now의 `system_logs`(레벨별 카운트 + 종목코드/숫자 마스킹 후 패턴 집계 + 상위 패턴 샘플) + `trade_history`(매수/매도/실현손익/전략별/상태별 집계) → OpenAI 호출 → `daily_log_reports`에 INSERT
- 출력 스키마: `{summary, findings: [{category, severity(high/medium/low), title, detail, suggestion}]}` — 화이트리스트 검증 후 저장
- 카테고리: trading, order, websocket, scan, balance, settlement, data_quality, infra, etc
- (target_date) UNIQUE — 동일 영업일 재실행 시 INSERT 무시 (None 반환)
- OpenAI 호출 60초 타임아웃, 실패 시에도 메트릭만 보존하여 INSERT (summary는 안내 문구)
- 모델은 `settings.openai_recommend_model` 재사용

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
- **매수가능 캐시 TTL(`BUYABLE_CACHE_TTL=60s`) / 매수 락 지속(`BUY_BLOCK_DURATION=900s`) / per-ticker low-funds cooldown(`LOW_FUNDS_COOLDOWN=900s`)** 변경 시 잔고 sync 주기(15분)와 정합성 확인. sync 종료 시 `unblock_buy()` + `clear_low_funds()`로 일괄 해제되므로 락/cooldown ≈ sync 주기가 자연스럽다
