# CLAUDE.md — src/engine/ (매매 엔진)

다중 전략 아키텍처. `StrategyBase` 추상 클래스 기반 플러그인 구조.

> 전략 6개 상세: **`src/engine/strategies/CLAUDE.md`**
> 사이클별 변경 이력: `docs/HARNESS_CHANGELOG.md`

## 모듈 맵

```
strategy_base / strategy_registry → 추상 + 등록/비중/중복 가드
strategies/{momentum, volatility_breakout, long_tail_volatility, donchian_swing, bull_flag_breakout, vcp_breakout}
session.py(MarketBoard, SessionTracker)
risk.py(on_tick) → order_engine.py(체결통보·DB persistence) → scheduler.py(시간 가드·run/settle) ← boot_manager.py(_boot 본체, 사이클 51) / stale_tracker.py(StaleTrackerState, 사이클 48)
scanner.py(종목 스캔/구독/STATIC_TICKER_NAMES)
util/tick_size.py(KRX 7구간 호가단위 헬퍼 — `get_tick_size` / `round_to_tick` / `step_down` / `step_up`)
market_regime.py(dkstock.cloud 매크로 → 매수 가드 + cash_usage_ratio)
recommendation_engine.py(20:00 AI자문) / log_analysis_engine.py(20:10 일일 로그 분석)
```

## strategy_base.py

- `StrategyBase` 추상 메서드: `prepare` / `check_buy_signal` / `check_exit_signal` / `calc_buy_quantity`
- 공통 헬퍼: `_calc_used_funds()` / `_fallback_one_share(current_price)` — 6개 전략의 1주 폴백 통합. 잔여 자금 = `total_investment - (positions buy_price×qty 합 + pending_buy_amounts 합)`. 전략 한도 초과 결함 차단
- `Signal`: NONE / BUY / STOP_LOSS / NEXT_DAY_CLEAR / TRAILING_STOP / FORCE_CLEAR
- `Position`: ticker, buy_price, quantity, order_no, strategy_id, buy_date, is_next_day(프로퍼티)
- `Position.is_next_day`: `buy_date < today AND strategy_id not in _MULTIDAY_STRATEGIES`(=`{donchian_swing, vcp_breakout}`). 멀티데이 전략은 항상 False — 확장 시 frozenset 멤버만 추가, `Position` 시그니처 변경 금지
- `StrategyState`: positions, pending_buys, **pending_buy_amounts**(ticker→가격×수량, 1주 폴백 잔여 자금 계산), total_investment, daily_realized_pnl, cached_buyable_qty/at, buy_blocked_until, low_funds_tickers, **signal_count_today / order_attempt_today / fill_count_today** + 헬퍼 (`is_buy_blocked / block_buy / unblock_buy / is_buyable_cache_fresh / is_low_funds_blocked / block_low_funds / clear_low_funds`)
- 일일 퍼널 카운터는 `_reset_daily_state()` 0 초기화 → `metrics.strategy_funnel` 노출
- `pending_buy_amounts` 는 OrderEngine `execute_buy` 시장가/지정가 폴백에서 `pending_buys.add(ticker)` 옆 동기 등록. `pending_buys.discard` 옆에서 동시 정리

## strategy_registry.py

- `allocate_funds(total_asset)` 비중 기반 분배 / `update_weights(weights)`
- `is_ticker_held_by_any` / `is_ticker_sold_today_by_any`
- **`is_ticker_blocked_for_buy(ticker)`** — 보유 OR 주문중 OR 당일매도 통합 가드. RiskManager·OrderEngine 매수 입구
- `get_strategies_status()` — 프론트 노출

## risk.py

`on_tick()`: ticker_prices 갱신 1회 → `registry.enabled()` 순회 → 전략별 exit/buy 신호.

- **사이클 19 (2026-05-20) `_selling` 가드**: `risk.on_tick` 의 보유 분기에서 `check_exit_signal` 호출 *전* `order_engine._selling` 검사 — 매도 발사 후 체결통보 도착 전까지 신호 평가 + 로그 폭주 차단. 042700 7초 18+ 행 운영 결함 대응. 6 전략 공통 적용

매수 신호 평가 *전* 가드 (순서):
- **보드 가드**: `session_tracker.is_tradable(strategy_id, params)`. **사이클 38 (2026-05-22) 명문화**: `tradable_boards` 는 매수 진입 전용 — 매도/손절/Trailing/익일청산/15:20 강제청산/상한가 손절 모니터링은 보드 가드 *없이* 항상 작동. `check_exit_signal` 분기는 본 가드 *전* 진입 (`on_tick` line 88-99 영역)
- **시장 레짐 매수 가드 (4 모드)**: `get_current_regime().get_buy_block_state()` async — DB `buy_block_mode` + 4 임계값 조회
  - `HARD blocked` → 매수 skip + `[regime_block]` 1분 주기 INFO
  - `WARN blocked` → 매수 허용 + `[buy_block_warn]` WARNING 1행
  - `SOFT blocked` → 매수 허용 + `execute_buy(soft_multiplier=0.5)` → 수량 `max(1, int(qty*0.5))` 축소
  - `OFF` → 가드 비활성
  - 4 임계 OR: `regime=defensive` (defensive_enabled=true) / `vix>vix_threshold` / `fear_greed_score>fg_high_threshold` / `<fg_low_threshold`. 매도/손절은 본 분기 진입 전 평가 → 영향 없음. 외부 fetch 실패 / `DKSTOCK_REGIME_ENABLED=false` → empty 폴백 (blocked=False)
  - 기본값: mode=HARD, vix=25 / fg_high=85 / fg_low=15 / defensive_enabled=true
- **중복 가드**: `registry.is_ticker_blocked_for_buy()`
- **자금 사전 가드**: `state.is_low_funds_blocked(ticker)` 또는 `current_price > state.total_investment` skip. **사이클 31 R6 (2026-05-21) 가시화**: `current_price > total_investment` 분기에 `_risk_silent_skip_logged_today: set[tuple[ticker, strategy_id]]` (RiskManager 필드) 기반 1회/페어/일 INFO emit cap — `[risk_silent_skip] ticker=009150 strategy=volatility_breakout reason=price_gt_total_investment price=1186000 total=352217`. 매 틱 폭주 차단. `scheduler._reset_daily_state` 동행 clear + AttributeError 방어 가드. 5/21 09:13 VB 미매수 사고 디버깅 곤란 해소
- BUY 신호 발생 시 `state.signal_count_today += 1`

## market_regime.py

`dkstock.cloud` 매크로 기반 시장 레짐 + 매수 가드 + cash_usage_ratio 자동 조정.

- `MarketRegime` dataclass: regime / regime_desc / cycle_phase / vix / fear_greed_score / buffett_ratio / cash_min / raw
- `MarketRegime.empty()` — 외부 fetch 실패 graceful (`is_buy_allowed=True`)
- `MarketRegime.from_macro_cycle(macro)` — dkstock.cloud `/api/macro/macro-cycle` 응답 파싱
- `is_buy_allowed(strategy_id) -> bool` — 동기 회귀 가드 API
- **`get_buy_block_state() -> BuyBlockState` (async)** — 4 모드 분기. `BuyBlockState{mode, blocked, soft_multiplier, reasons}` 반환. DB 조회 실패 시 HARD + 기본 임계 fallback
- **`get_buy_block_state()` 60s TTL 인스턴스 캐시** — `_buy_block_cache` + `_buy_block_cache_expires_at` 필드(`compare=False, repr=False`). `BUY_BLOCK_CACHE_TTL=60.0`, `time.monotonic()` 비교. DB fetch 폴백 분기는 캐시 미저장. `invalidate_buy_block_cache()` 운영 토글 즉시 반영. 분당 ~1,800 DB 쿼리 → ~10 쿼리 (180배 감소)
- `to_advisor_dict()` 12 키 dict 반환 — AI 자문 user_payload 통합
- `cash_usage_ratio_from_regime(cash_min)` — `clamp((100 - cash_min)/100, 0.0, 1.0)`
- `refresh_from_dkstock()` — dkstock_client → MarketRegime. 모든 예외 흡수 → empty
- `persist_snapshot(regime, target_date)` — `market_regime_snapshots` 1행 INSERT
- `get_current_regime()` / `set_current_regime()` — 모듈 싱글톤
- 운영 graceful: `DKSTOCK_REGIME_ENABLED=false` 기본 → 외부 호출 0건, 매수 가드 비활성
- **DB 우선 토글**: `dkstock_client._check_enabled_async` + `mcp_client._check_enabled_async` + `backtest_engine.is_enabled_async()` 가 `system_config.get_*` 먼저 → DB True/False 채택, None / 예외 시 `settings.*` (.env) fallback. 매 호출마다 DB 조회 — Settings UI 토글 즉시 반영

`scheduler._boot()` 이 매크로 fetch + snapshot INSERT + `cash_usage_ratio` 자동 조정 통합.

## order_engine.py

매수/매도 실행 + 체결통보 처리 + DB positions 영속화.

매수 (`execute_buy`):
- **NXT 프리마켓 시장가 사전 차단 (preconvert)**: `place_order` 호출 *직전*, `MarketBoard.PRE_NXT in session_tracker.active` AND `MAIN not in active` AND `buy_exchange in ("NXT", "SOR")` 면 사전에 `step_up(current_price, 5)` 지정가로 변환. 변환 시 `state.pending_buy_amounts[ticker] = order_price × quantity` 동기 갱신, `record_price = order_price` 로 PENDING. INFO `[market_order_preconvert_pre_nxt]` 1행
- 진입 시 `is_buy_blocked()` + `is_low_funds_blocked(ticker)` 차단
- 매수가능 캐시 `BUYABLE_CACHE_TTL=60s` — KIS 호출 매 틱 → 분당 1회
- `max_buy_quantity<=0` 또는 `KisApiError(insufficient_cash)` → `block_buy(now+BUY_BLOCK_DURATION=900s)`
- `calc_buy_quantity()<=0` → `block_low_funds(ticker, now+LOW_FUNDS_COOLDOWN=900s)`
- **`is_market_order_disallowed` 거부 → 지정가 5호가 폴백 1회** — `step_up(current_price, 5)` + `LIMIT`. 매핑 동기 등록 + `_completed_orders` race 가드 + `insert_trade(PENDING, fallback_price)` 동기. 폴백 거부 시 cooldown
- 락/cooldown 은 다음 잔고 sync (15분) 에서 `unblock_buy()` + `clear_low_funds()` 일괄 해제

매도 (`execute_sell(..., limit_price=0)`):
- `_selling` set 중복 매도 차단
- `limit_price > 0` 이면 `LIMIT` + `exchange="NXT"` 강제. 0 이면 시장가 + 전략 `_strategy_exchange()` 라우팅. 호가단위 정렬은 호출자가 `util.tick_size.step_down` 책임
- `KisApiError(insufficient_quantity)` 시 3회 재시도 생략 + 즉시 break + 메모리/DB positions 정리
- **`is_market_closed_rejection(err)`** (장운영시간 외) → 재시도 중단 + `state.positions`·DB·`_selling` 보존 + 다음 거래 시각 자연 재트리거. NXT 시간대 거부면 `stock_master.upsert_one(ticker, nxt_tradable=False)` 사후 보강. **사이클 B-1 (2026-06-01) 진입 차단 이중 안전망**: 거부 시 `_market_closed_blocked[ticker] = _compute_next_market_open_kst(now_kst)` 등록. `execute_sell` 진입 게이트에서 TTL 미경과 시 KIS 호출 없이 skip (INFO `[market_closed_blocked]` 1줄/ticker/일 cap). TTL = 다음 KST 09:00. `OrderEngine.reset_daily_state()` 가 dict + cap set 일괄 clear — `scheduler._reset_daily_state()` 위임 호출
- **`is_market_order_disallowed(err)` + `order_division==MARKET`** → 지정가 5호가 폴백 1회. `step_down(scanner.ticker_prices[ticker]["current_price"], 5)` + `LIMIT`. 폴백 실패 시 `_selling.discard` + positions 보존 (청산 의무, 다음 사이클 재트리거). 지정가 매도(`limit_price>0`)는 폴백 안 함 (이미 지정가). 키워드: `시장가호가불가` / `최유리/최우선지정가 주문만` / `지정가 및 최유리` (APBK1943 / APBK3013)

체결통보 race 가드:
- 주문번호 매핑(`_order_qty / _order_strategy / _order_ticker / _pending_buy_orders`)은 **`place_order` 응답 직후 동기 영역**, `await insert_trade` 진입 *전*
- `_completed_orders` set + `update_trade_status` 영향 row 0건 보정 INSERT — 체결통보가 REST 응답보다 먼저 도착해도 단일 COMPLETED row 보장

거래소 라우팅 (`exchange`):
- 모든 `place_order` / `cancel_order` 에 `_strategy_exchange(strategy_id)` 전달
- **NXT 거래가능 사전 차단**: `_strategy_exchange_async(strategy_id, ticker=...)` 가 `stock_master.get(ticker).nxt_tradable=False` 면 NXT/SOR → KRX 강제 다운그레이드 + `[nxt_downgrade]` 1행. 캐시 miss / 예외 시 전략 기본 exchange (보수적 fallback). 익일 청산 NXT 지정가(`limit_price>0`)는 사전 차단 적용 안 함

체결 후처리:
- 매수 → DB `positions` 저장 + `cached_buyable_at=0` (가용액 캐시 무효화)
- 매도 → DB positions 삭제 + `sold_today` 등록. **사이클 15-A (2026-05-19) WS 구독 정리 hook** — `_unsubscribe_if_no_other_strategy(ticker)` 가 (a) `registry.is_ticker_held_by_any(ticker)=False` + (b) `_pending_next_day_clear` 부재 + (c) 모든 전략 `get_scanned_tickers()` 부재 — 모두 통과 시 `kis_ws_pool.unsubscribe(TICK_TR_ID, ticker)`. KIS 정상 패턴 "불필요 종목 구독해제" 즉시 적용. `_pending_next_day_clear_provider` 는 scheduler 가 `OrderEngine.__init__` 직후 주입 (lambda)
- 체결통보 처리 실패 안전장치: ticker 매핑 실패 → `pending_buys` 제거, strategy 미발견 → `_selling` 해제

퍼널 카운터: `place_order` 직전 `order_attempt_today += 1`, `_handle_buy_fill` 첫 체결 시 `fill_count_today += 1`

## session.py

`MarketBoard` enum: `pre_nxt` (08:00~) / `krx_open` (08:30~09:00) / `main` (09:00~15:20) / `krx_after` (15:30~18:00) / `post_nxt` (15:30~20:00).

- `_BOARD_SCHEDULE`: 시각 → 활성 보드 frozenset (H0NXMKO0 미수신 시 fallback)
- `SessionTracker.tick()`: `_session_loop` (scheduler 30s 주기) 에서 호출
- `is_tradable(strategy_id, params)`: 활성 보드 ∩ 전략 `tradable_boards` ≠ ∅
- `on_h0nxmko0(...)`: NXT 장운영정보 수신 (KIS 명세 미확정 → 코드 기록만)

## scheduler.py — KRX/NXT 통합 운영 08:00~20:00

시간 상수 (`scheduler.TIME_*`):

| 상수 | 시각 | 동작 |
|------|------|------|
| `TIME_AUTO_START` | 07:45 | DB `auto_start` 우선 폴백 자동 시작 |
| `TIME_BOOT` | 07:50 | `_boot()` (사이클 51 분해: 본체 `src/engine/boot_manager.py::boot(scheduler)` 위임 — 2 줄 wrapper. 외부 import 경로 영향 0) — `_preissue_all_tokens()` (사이클 20: 메인+보조 N 매니저 분당 1개 한도 직렬화 사전 발급) → DB positions 복구 → KIS 잔고 교차 검증 → 미체결 복구 → `_eager_refresh_stock_master_for_held_positions()` (보유 + 익일청산 후보 ticker 를 stock_master eager 갱신) → 매크로 fetch + `market_regime_snapshots` INSERT → `cash_usage_ratio` 자동 조정 → `allocate_funds(net_asset × ratio)` |
| `TIME_PRESUBSCRIBE` | 07:55 | `_collect_presubscribe_tickers()` — VB/LTV/donchian + 모든 전략 보유 합집합 사전 구독 |
| `TIME_PRE_NXT_OPEN` | 08:00 | 익일 청산 task (`_execute_next_day_clear`, `NEXT_DAY_STABILIZE_SECS=30s`). 사이클 26: VB/LTV PRE_NXT 매수 제거됨 — `_confirm_breakout_open_prices(board="pre_nxt")` 대상 없음 (tradable_boards=("main",)) |
| `TIME_KRX_MAIN_OPEN_PRESUBSCRIBE` | 08:59:10 | **사이클 26 신규**: KRX 채널(H0STCNT0) 사전 구독 마진 시작. `_board_transition_loop("H0NXCNT0","H0STCNT0", 보유+익일청산)` — 종목별 원자 전환 + 매수 후보 신규 subscribe |
| `TIME_KRX_OPEN_CONFIRM` | 09:00:05 | `_confirm_breakout_open_prices(board="main")` — VB/LTV가 KRX 09:00 시가로 target_price 계산. 직후 `_drain_pending_next_day_clear()` — 08:00 보류 종목 KRX 시장가 일괄 청산. 모두 이미 확정이면 idempotent skip |
| `TIME_SCAN_START` | 09:30 | 모멘텀 `scan_stocks()` + 통합 구독 |
| `TIME_KRX_MAIN_BUY_STOP` | 15:20 | `_force_clear_main_only` — VB/LTV tradable_boards=("main",) 이므로 POST_NXT 활성 0 → 전량 청산 |
| `TIME_KRX_MAIN_CLOSE` | 15:30 | KRX 메인 마감. 사이클 26: `_confirm_breakout_open_prices(board="post_nxt")` 제거 (VB/LTV tradable_boards 에 post_nxt 없음). 15:30~15:39:59 = MAIN 유지 (종가 흡수 마진) |
| `TIME_POST_NXT_OPEN_PRESUBSCRIBE` | 15:39:10 | **사이클 26 신규**: NXT 채널(H0NXCNT0) 사전 구독 마진 시작. `_board_transition_loop("H0STCNT0","H0NXCNT0", 보유+익일청산)` — 종목별 원자 전환 + 매수 후보 KRX unsubscribe |
| `TIME_POST_NXT_OPEN` | 15:40 | **사이클 26 신규**: NXT 애프터 진입 (기존 15:30 → 15:40 으로 변경). 매도만 (VB/LTV tradable_boards=("main",)) |
| `TIME_NXT_POST_BUY_STOP` | 19:50 | `buy_disabled = True` (NXT 애프터 신규 매수 중단, 변경 금지) |
| `TIME_NXT_POST_CLOSE` / `TIME_RECOMMENDATION` | 20:00 | `unsubscribe_all()` + `generate_recommendations()` — 동기 순차 (자문 ~3분, settlement 20:10 까지 7분 여유) |
| `TIME_SETTLEMENT` | 20:10 | `_settle()` → `generate_daily_log_report()` → **`purge_old_logs()`** (사이클 6 통합, 2026-05-20 — INFO 2일 / WARNING+ 30일 retention 자동 정리, 실패 graceful `[log_retention_skip]` INFO + 다음 사이클 재시도) → `_reset_daily_state()` (퍼널 카운터 초기화는 분석 *후*) |

기타:
- WebSocket 연결 직후 **체결통보 자동 구독** (실전 H0STCNI0+HTS ID / 모의 H0STCNI9+계좌번호) + 통합 장운영정보 `H0UNMKO0`/`005930` (실전 한정)
- `_load_strategy_config()`: DB `strategy_config` 에서 비중/`tradable_boards`/`exchange`/`k_value_*` 복구
- `run_daily()`: 주말+공휴일 건너뜀 (KIS `chk-holiday`), 매일 시작 전 DB auto_start 재확인
- `_scan_loop()` (5분 주기, 09:30~): VB+LTV+donchian + 모든 전략 보유 합집합 재구독. **사이클 15-A (2026-05-19) KIS 정상 패턴 준수**: 기존 `unsubscribe_all() → subscribe_filtered_stocks()` 전체 재구독 → `_delta_unsubscribe_dropped(new_set)` (빠진 종목만 unsubscribe) + `subscribe_filtered_stocks` (scanner LOW 분기에 `already_in_pool` 가드 추가로 이미 구독 중 종목 SEND skip). KIS 공지 "비정상 케이스 2" (무한 등록/해제) 패턴 차단. HIGH 종목 (positions/next_day_clear) 은 always 호출 — 풀의 `_select_session` promote 보존. 직후 `_reprepare_breakout_if_empty()` (사이클 48, 2026-05-27 — 대상 `volatility_breakout`/`long_tail_volatility`/`bull_flag_breakout`/`vcp_breakout`. BFB/VCP 는 boot 실패/일시 API 오류 회복 안전망 — 주 메커니즘은 prdy 시간무관 유니버스) + `_resubscribe_stale_priority(cap=10)` + `_report_tick_coverage()`. **사이클 25-B (2026-05-20) `_resubscribe_stale_priority` 우선순위 분리**: positions/next_day_clear 소속 stale → HIGH+bypass_limit=True (메인 절대 보장, 기존), 그 외 후보 stale → LOW+bypass_limit=False (보조 분산). 2026-05-20 14:58 VB/LTV 후보 8종목 stale→HIGH 메인 승격→메인 과부하→silent inactive 사고 대응. 사이클 24 자동 reconnect 와 이중 안전망
- **사이클 17 (2026-05-19) — 사이클 15-B/C 전체 롤백**: `_near_signal_loop` + `stream_pool_manager` + `near_signal_monitor` + `settings.near_signal_mode` + `_build_priority_groups` 분기 + `_near_signal_task` 멤버 + `GET /api/realtime/stream-status` + 프론트 `StreamStatus` 메뉴 모두 제거. 단순화 원칙(단일 데이터 경로 + 신규 모듈 추가 금지) 위반 + 60s `_near_signal_loop` 와 `_scan_loop`/K stale watcher race → KIS `OPSP0002` 폭주 → tick_coverage 0% 결함(2026-05-19 15:15 사고). `_build_priority_groups` 는 항상 momentum/breakout 정상 list 반환. WS 등록 경로 = `_scan_loop` 5분 delta 단일. OPSP0002 차단은 `_handle_raw` 의 backoff (`_opsp_backoff_until`) 로 단순 흡수
- **사이클 17 보강 (2026-05-19) — KIS 공식 답변 반영**: 1) `_check_and_resubscribe_stale` 의 1~5회 `pool.resend_subscribe_for_ticker` (같은 종목 재SEND) 분기 완전 폐기 → 첫 stale 즉시 `pool.unsubscribe_in_pool` + `pool.subscribe(HIGH, bypass_limit=True)` 강제 재등록 (KIS 정상 "신규 등록" 패턴). 2) OPSP0002 backoff 60s → 300s 연장 — `_scan_loop` 5분 주기 ≥ backoff 만료 보장. KIS 인용: "기 요청된 목록 관리하여 기등록한 사항을 재등록하지 않도록 (다수 요청 시 LMS + 앱정보 이용중지)". `MAX_STALE_RETRIES=5` 신규 상수 — 6회 이상 stale skip (영구 stale 의심)
- `_stale_watcher_loop()` (`_check_and_resubscribe_stale`, 120s 주기): `kis_ws_pool.get_subscribed_tickers()` 합집합 vs `scanner.ticker_last_tick` 비교. `STALE_FRESHNESS_SECS=60s` 초과면 stale, 종목별 `_stale_retry_count` 누적. **사이클 17 보강 (2026-05-19) — KIS 공식 답변 ("기등록한 사항을 재등록하지 않도록") 반영**: 1~5회 `pool.resend_subscribe_for_ticker` (같은 종목 재SEND) 분기 완전 폐기 → 첫 stale 즉시 `pool.unsubscribe_in_pool` + `pool.subscribe(priority='HIGH', bypass_limit=True)` 강제 재등록 (KIS 정상 "신규 등록" 패턴, 재SEND 0건). 6회 이상 (`> MAX_STALE_RETRIES=5`) → 사이클 28 *전*: skip / **사이클 29-R1 (2026-05-21)**: 시간 기반 force_retry — `STALE_FORCE_RETRY_AFTER_SECS=300` (5분) 경과 또는 `_stale_last_resubscribe_at` 부재 시 강제 재등록 + `_stale_retry_count[ticker]=0` 리셋 + `_stale_force_retry_history` (60분 슬라이딩 윈도우) 등록. `STALE_FORCE_RETRY_HOURLY_CAP=12` 초과 시 `[stale_force_retry_cap]` WARNING skip. 영구 stale 무한 skip 결함 차단. **사이클 29-R3 (2026-05-21) — K stale watcher 양쪽 분기 우선순위 분리**: `high_tickers` = `registry.all()` positions ∪ `_pending_next_day_clear` 합집합. `ticker in high_tickers` → HIGH+bypass=True (메인 절대 보장), 그 외 → LOW+bypass=False (보조 분산). 사이클 28 실측 main=25/보조 합 9 편중 73% → R3 후 main=2/보조 합 34 편중 5%. F1(재연결 1회) + `_scan_loop`(5분) + K(120s) + `_resubscribe_stale_priority`(5분 우선) 4중 안전망. **사이클 24 (2026-05-20) — 세션 단위 silent inactive 감지 + 강제 reconnect**: K stale watcher 가 종목별 재등록 외에 세션 자체 결함도 5분 지속 후 `_force_reconnect_session(label)` 으로 `_ws.close()` 발화 → 재연결 자동 발화. **사이클 29-R2 (2026-05-21) 정의 완화**: `fresh==0` → `fresh_ratio < SILENT_INACTIVE_FRESH_RATIO_THRESHOLD(=0.2, 20%)` + `subscribed_count >= 5` + 5분 지속 3중 가드. 시간당 2회 cap (LMS / 앱 정지 위험 차단) 보존. 사이클 28 실측 메인 fresh=2/25=8% 결함 자동 감지. **사이클 28 (2026-05-21) — 추적 강화**: `_stale_last_resubscribe_at: dict[str, datetime]` 신규 + `[stale_watcher_detail] session=main sub=22/41 fresh=8 stale=14 ratio=0.64 stale=[(009150,r=3,@09:12:45), ...]` 신규 prefix (종목 cap 20 + overflow `...+N`). 기존 `[stale_watcher]` / `[stale_priority_resubscribe]` 보존.
- **`_refresh_stale_ccnl_cache(stale_tickers, cap=20)` (사이클 37, 2026-05-21)**: stale r≥2 종목 대상 `quotation.inquire_ccnl` 호출 + `_last_ccnl_cache: dict[ticker, dict]` 갱신. TTL 5분 + cap 20 + 종목 간 50ms sleep + 보유 종목 우선 처리 + KIS None/예외 graceful 캐시 미저장. `_scan_loop` (5분 주기) 통합 + `_reset_daily_state` 동행 clear. R4 universe guard 와 race 무해 (TTL 자동 차단). `/api/realtime/subscriptions` 의 `tickers_detail.last_cntg_hour / today_volume` 응답 데이터 소스.
- **`_evaluate_universe_guard(candidate_tickers)` (사이클 32 R4, 2026-05-21)**: stale>5 + `today_volume < UNIVERSE_LOW_VOLUME_THRESHOLD(=10_000)` 종목 자동 universe 제외. 사전 가드 (보유/익일청산/이미 제외/stale≤5 → KIS 호출 자체 skip) + `inquire_ccnl` 호출 + `_universe_excluded_today.add()` + `kis_ws_pool.unsubscribe()` + `[universe_excluded] ticker=... reason=stale_6plus_low_volume retries=... last_resub_age=...s last_cntg_hour=... today_volume=...` INFO + system_logs 영구. `_collect_breakout_tickers` 필터링 + `_scan_loop` 5분 주기 통합 + `_reset_daily_state` 동행 clear (영구 블랙리스트 금지).
- `_sync_orders_to_db(orders)`: KIS 주문체결내역(`get_daily_orders`) → trade_history 동기화. MTS/HTS 수동 매매분 반영. 중복 판정 키 `(ticker, order_no)` 페어
- `_sync_positions_from_balance()`: 15분 주기. strategy 매핑은 trade_history 직전 BUY 행에서 상속. 종료 시 `unblock_buy()` + `clear_low_funds()` 일괄 해제
- `_execute_next_day_clear()`: 다음 영업일 NXT 프리 시가 수신 후 30s 안정화 → 갭률 트레일링 또는 NXT 지정가 매도. 시가 미수신이면 `_pending_next_day_clear` set 보류. `stock_master.nxt_tradable=False` 가 1순위 판별 → 즉시 보류 등록 (NXT 주문 0건)
- `_drain_pending_next_day_clear()`: `_confirm_breakout_open_prices(board="main")` 직후 호출. `_pending_next_day_clear` 종목 KRX 시장가 일괄 청산
- 구조화 로그: `[next_day_clear_deferred] ticker={t} strategy={s} reason={nxt_not_tradable|nxt_open_missing}` / `[next_day_clear_drained] ticker={t} strategy={s} result={success|fail} elapsed_ms={ms}`
- `_reset_daily_state()`: 전략별 positions/pending_buys/sold_today + OrderEngine 추적 상태 + scanner 글로벌 dict (`ticker_last_tick.clear()` 포함) + `_pending_next_day_clear.clear()` + `_stale_retry_count.clear()` 전체 초기화

## scanner.py

- `scan_stocks()`: 모멘텀 등락률 순위
- `subscribe_filtered_stocks(tickers, extra_tickers, source_counts=None, *, priority_groups=None)`: 합집합 구독
  - `priority_groups` 분기: `kis_ws_pool.subscribe(tr_id, t, priority='HIGH'|'LOW', bypass_limit=...)` 위임. `positions`/`next_day_clear` → HIGH + `bypass_limit=True` (메인 절대 보장), `breakout`/`momentum`/`swing` → LOW + `bypass_limit=False` (보조 라운드로빈 우선, 보조 가득 시 메인 fallback)
  - **2-pass**: 1차 `breakout[:BREAKOUT_LOW_CAP=25]` + momentum + swing 잔여 슬롯 add → 2차 `MAX - len(_subscriptions) > 0` 면 breakout overflow 흡수 add. 최종 drop = `max(0, len(overflow) - absorbed_overflow)`. drop>0 시 `[priority_drop]` INFO + WARNING `system_logs`. 중복은 HIGH 1회만, HIGH 단독 41 초과 시 ERROR
  - `source_counts` dict 전달 시 `[scanner] 실시간 시세 구독 완료: total=N (vb=A, ltv=B, swing=C, momentum=D, positions=E)` 노출 (영문 라벨 — Grafana/Loki 안정성)
  - 평탄 처리 분기 (`priority_groups=None`)는 기존 `kis_ws.subscribe` 직접 호출 보존
- `KOSPI_200_TICKERS` / `KOSDAQ_150_TICKERS`: donchian_swing 고정 유니버스
- `STATIC_TICKER_NAMES` / `_parse_static_ticker_names()`: 모듈 import 시 자기 파일을 정규식으로 파싱 → 종목명 dict. KIS `inquire-price` 빈 응답 대비 보강
- 공용 데이터: ticker_names, ticker_prices, ticker_prev_close, ticker_market_info, **ticker_last_tick** (`risk.on_tick` 호출 시 KST `datetime` 갱신)
- **`get_scan_status()` 풀 전체 카운트**: `kis_ws_pool.get_subscribed_tickers()` / `get_acked_tickers()` 합집합 위임. `tick_coverage_total/acked/fresh/stale` 4 키 + 기존 `subscribed_count` 보존. `/api/trading/status` `scan` 필드 동봉 → ScanMonitor stale 색상 배지 + 진행바

## log_analysis_engine.py — 일일 로그 분석

20:10 정산 직후 `generate_daily_log_report()` 호출. 호출 *후* run loop가 `_reset_daily_state()` 별도 실행 (퍼널 카운터 보존).

당일 KST 00:00~now `system_logs` + `trade_history` → OpenAI → `daily_log_reports` INSERT.

확장 메트릭:
- `api_metrics`: `api/base.py::get_request_metrics()` (5xx/4xx/network/retries + path별 5xx top 5). INSERT 후 `reset_request_metrics()`
- `strategy_funnel`: 전략별 `{signals, orders, fills}` (registry 순회)
- `trades.by_ticker_pnl` (SELL PnL 절대값 top 5) / `trades.by_hour_pnl` (KST hour별)
- `next_day_clear`: `{deferred, drained_success, drained_fail}` (구조화 로그 prefix 정규식)

출력 스키마: `{summary, findings: [{category, severity, title, detail, suggestion}]}`. `(target_date)` UNIQUE. OpenAI 타임아웃 60s, 실패 시 메트릭만 보존 INSERT.

## recommendation_engine.py / recommendation_metrics.py — 20:00 AI자문

- 전략별 metrics(승률/평균손익/손절률/누적수익률) → OpenAI → `parameter_recommendations` INSERT (status: pending)
- `(target_date, strategy_id)` UNIQUE
- `/api/recommendations/{id}/apply`: 사용자 키 선택 적용 → `strategy_config.params` 갱신 + status applied/partial
- `expire_pending_before(target_date)`: 이전 영업일 pending 자동 만료
- `_validate_recommendations()` 5-tuple 반환 `(validated_params, reasoning, weight, notes, weight_reasoning)`
- user_payload 에 `current_weight` + `peer_weights` + `peer_metrics` + `market_regime` 12 키 추가
- `apply_weight=true` 옵션 → `save_weights({sid: w})` + `strategy.config.weight` 메모리 반영 + `applied_weight` 트래킹. `allocate_funds()` 즉시 재호출 금지 (다음 _boot 반영)
- `PARAM_RANGES` 화이트리스트 (자동 튜닝 대상): `k_value_krx_main`/`k_value_nxt_pre` `(0.5, 2.0)` (VB, LTV) + `stop_loss_main`/`stop_loss_pre_nxt` `(-15.0, 0.0)` + `donchian_period` `(10, 60)` + `long_ma_period` `(20, 120)` + `volume_multiplier` `(1.0, 5.0)` + `atr_trail_mult` `(1.0, 5.0)` + `min_prdy_rate` + **사이클 23**: VCP 4 키 (`base_depth_pct`/`volume_contraction_ratio`/`breakout_volume_mult`/`last_pullback_max`) + P2 신규 5 키 (`breakout_retention_minutes`/`breakout_fail_n_days`/`max_breakout_extension_pct`/`box_contraction_period`/`max_box_volatility_pct`)
- `INT_PARAMS`: `donchian_period` / `long_ma_period` / **사이클 23**: `breakout_retention_minutes` / `breakout_fail_n_days` / `box_contraction_period`
- **사이클 23 P3-1+2 `auto_apply_recommendations(target_date)` (신규 함수)**: 20:00 AI 자문 직후 자동 적용. 감액만 + 50% cap + 보수적 파라미터 (`_CONSERVATIVE_KEYS`) 자동 적용. `auto_apply_enabled=False` 시 즉시 disabled 반환. `[auto_weight_apply]`/`[auto_params_apply]`/`[auto_apply_skip_increase]`/`[auto_apply_safeguard_skip]` 4종 영구 로그. `status='applied_auto'` (수동 'applied' 와 분리). scheduler `TIME_RECOMMENDATION` 직후 호출. **사이클 36 hotfix (2026-05-21)**: scheduler.py:542 호출부에 `from src.engine.scanner import KST_TZ as _AUTO_APPLY_KST_TZ` import + `datetime.now(_AUTO_APPLY_KST_TZ).date()` 사용 (이전엔 `KST` 미정의 NameError 로 매일 20:00 자동 적용 실패). `backtest_engine.poll() / wait_for_result()` 의 `pending` status 도 `running` 동일 처리 (이전엔 unknown 분기 → ExternalAPIError → `backtest_runs status=failed` 잘못 기록)
- `recommendation_metrics._normalize_stop_loss_rate(params)`: 5 키 후보(`stop_loss_rate`/`intraday_stop_loss`/`overnight_stop_loss`/`stop_loss_main`/`stop_loss_pre_nxt`) → 음수만 → `min(candidates)` 반환 (가장 보수적). LTV 분리 키 흡수 + VB 보드별 키 운영
- SYSTEM_PROMPT 끝에 매크로 컨텍스트 활용 가이드 — defensive/neutral/aggressive 분기 + `buy_blocked=True` 시 매수 임계 변경 권고 무용 + `weight_reasoning`/`code_review_notes` 에 매크로 영향 명시 권장
- VIX 분류 `_classify_vix()` 임계 15/25/35 (low/normal/elevated/high). Fear & Greed 분류 `_classify_fear_greed()` 임계 15/35/65/85
- `weight_reasoning` (≤1000자, 한국어, 통합 `reasoning` 과 별개). `weight=None` 이면 자동 정리, `weight` 있는데 사유 누락 → `WEIGHT_REASONING_FALLBACK="(사유 미제공)"` + WARNING

## 절대 깨지면 안 되는 규칙

- 체결통보(H0STCNI0/9) 구독 제거 금지 — 미구독 시 포지션 등록 불가 → 손절 불가
- uvicorn 단일 워커 필수 (`--workers` 금지)
- 매수 신호는 반드시 "돌파 순간" 감지 (이전 틱 < 기준가 AND 현재 틱 ≥ 기준가)
- 익일 청산은 scheduler에서 시가 수신 후 30s 안정화 (`_next_day_clear_pending` 전략 가드 + `_pending_next_day_clear` scheduler 보류 set) — on_tick 즉시 청산 금지
- 익일 청산 갭률은 반드시 `ticker_prices[ticker]["open_price"]` (WebSocket 시가) — `high_since_buy` 폴백 금지. 시가 미수신이면 `_pending_next_day_clear` 보류 후 09:00 KRX 시장가
- NXT 프리/애프터 매도 거부 (`is_market_closed_rejection`) 시 `execute_sell` 이 `state.positions`·DB·`_selling` 보존 + NXT 시간대 거부면 `stock_master.upsert_one(ticker, nxt_tradable=False)` 사후 보강. **사이클 B-1 진입 차단까지 보장** — `_market_closed_blocked` ticker별 TTL 게이트 (다음 KST 09:00 만료). TTL 미경과 시 `execute_sell` 자체가 KIS 호출 없이 return. `_reset_daily_state` 동행 clear 필수
- 매수 시장가 거부 (`is_market_order_disallowed`) → `step_up(current_price, 5)` 지정가 1회 폴백
- 매도 시장가 거부 (`is_market_order_disallowed`) + `order_division==MARKET` → `step_down(current_price, 5)` 지정가 1회 폴백. 폴백 실패 시 cooldown 등록 안 함 + positions 보존 (청산 의무, 다음 사이클 재트리거). 지정가 매도는 폴백 안 함
- 주문번호 매핑 등록은 **`place_order` 응답 직후 동기 영역**, `await insert_trade` 진입 *전*
- 체결통보 선행 race 가드 (`_completed_orders` + UPDATE 0건 보정 INSERT) 매수·매도 양쪽 필수
- `BUYABLE_CACHE_TTL=60s` / `BUY_BLOCK_DURATION=900s` / `LOW_FUNDS_COOLDOWN=900s` ↔ sync 주기(15분) 정합성 — 변경 시 sync 종료 시 일괄 해제 동작 보존
- `Position` 에 `strategy_id` 필수 (체결통보 → 올바른 전략 라우팅)
- `position_ratio`는 **전략 할당 자금 기준** (순자산 × 전략비중 × position_ratio)
- TR_ID 는 `settings.get_tr_id()` 사용
- `_confirm_breakout_open_prices` 보드 경계 정각 호출은 `board=...` 명시 의무 — 08:00 `pre_nxt` / 09:00:05 `main` / 15:30 `post_nxt`. SessionTracker race 차단
- VB `DEFAULT_TRADABLE_BOARDS` 에 POST_NXT 추가 금지 — 당일 15:20 일괄매도 정책 위반 + OVERNIGHT 자연 보유 결함
- donchian_swing `_swing_rest_poll_loop` 제거 금지 — 09:30~15:20 60s REST 폴링으로 멀티데이 보유 손절 평가 보강
