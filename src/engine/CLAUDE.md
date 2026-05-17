# CLAUDE.md — src/engine/ (매매 엔진)

다중 전략 아키텍처. `StrategyBase` 추상 클래스 기반 플러그인 구조.

## 모듈 맵

```
strategy_base / strategy_registry → 추상 + 등록/비중/중복 가드
strategies/{momentum, volatility_breakout, long_tail_volatility, donchian_swing}
session.py(MarketBoard, SessionTracker)
risk.py(on_tick) → order_engine.py(체결통보·DB persistence) → scheduler.py(시간 가드·boot/run/settle)
scanner.py(종목 스캔/구독/STATIC_TICKER_NAMES)
util/tick_size.py(KRX 7구간 호가단위 헬퍼 — `get_tick_size` / `round_to_tick` / `step_down`)
recommendation_engine.py(20:00 AI자문) / log_analysis_engine.py(20:10 일일 로그 분석)
```

## strategy_base.py

- `StrategyBase` 추상 메서드: `prepare`, `check_buy_signal`, `check_exit_signal`, `calc_buy_quantity`
- **공통 헬퍼 (2026-05-11 P1)**: `_calc_used_funds()` / `_fallback_one_share(current_price)` — 4개 전략의 `calc_buy_quantity()` 1주 폴백을 통합. 잔여 자금 = `total_investment - (positions buy_price×qty 합 + pending_buy_amounts 합)`. 결함 차단: 기존 로직은 고정 `total_investment`와 직접 비교 → 동일 전략 자금 90% 사용 후에도 1주 추가 매수 → **전략 한도 초과**(2026-05-11 운영 사고)
- `Signal`: NONE / BUY / STOP_LOSS / NEXT_DAY_CLEAR / TRAILING_STOP / FORCE_CLEAR
- `Position`: ticker, buy_price, quantity, order_no, strategy_id, buy_date, is_next_day(프로퍼티)
- **`Position.is_next_day` (2026-05-12 I2)**: `buy_date < today` AND `strategy_id not in _MULTIDAY_STRATEGIES`(=`{donchian_swing}`). 멀티데이 보유 전략은 시간 청산 개념 없어 항상 False — OrderMonitor 청산 배지 무의미 표시 차단 (donchian_swing은 둘째 날부터 자동 익일 분류되던 결함). 확장 시 `_MULTIDAY_STRATEGIES` frozenset 멤버만 추가, `Position` 시그니처 변경 금지
- `StrategyState`: positions, pending_buys, **pending_buy_amounts**(ticker→가격×수량, pending_buys와 동기 dict — 1주 폴백 잔여 자금 계산용), total_investment, daily_realized_pnl, **cached_buyable_qty/at**, **buy_blocked_until**, **low_funds_tickers**, **signal_count_today / order_attempt_today / fill_count_today** + 헬퍼(`is_buy_blocked / block_buy / unblock_buy / is_buyable_cache_fresh / is_low_funds_blocked / block_low_funds / clear_low_funds`)
  - 일일 퍼널 카운터 3종은 `_reset_daily_state()`에서 0 초기화 → `metrics.strategy_funnel`로 노출
  - `pending_buy_amounts`는 OrderEngine `execute_buy` 시장가/지정가 폴백 양쪽에서 `pending_buys.add(ticker)` 옆에 동기 등록 (`current_price × quantity` 또는 `fallback_price × quantity`), 체결/거부/실패/체결통보 정리 시 `pending_buys.discard` 옆에서 동시 정리. `_reset_daily_state()` + `_boot()` 미체결 복구도 동일 규약

## strategy_registry.py

비중/중복 매수 가드:
- `allocate_funds(total_asset)` 비중 기반 분배 / `update_weights(weights)`
- `is_ticker_held_by_any` / `is_ticker_sold_today_by_any`
- **`is_ticker_blocked_for_buy(ticker)`** — 보유 OR 주문중 OR 당일매도 통합 가드. RiskManager·OrderEngine 매수 입구에서 사용
- `get_strategies_status()` — 프론트 노출용

## 전략 (`strategies/`)

| 전략 | 핵심 동작 | 손절·청산 | tradable_boards / exchange |
|------|----------|----------|---------------------------|
| `momentum` | 전일종가 +29% 돌파 (상한가 30% 제외, 돌파 순간만) | -7.5% / 익일 청산: 갭+10%↑ → 트레일링 -2% / 그 외 즉시 매도 | KRX_OPEN+MAIN / KRX·NXT·SOR (실전 SOR 권장, 모의는 KRX 강제) |
| `volatility_breakout` | 보드별 시가 + (전일Range × 보드별 K) 돌파. `_targets[ticker].boards[board]`에 보드별 분리 저장. `_open_confirmed[ticker]` / `_prev_price[ticker]`도 `{board: ...}` dict | **보드별 손절** (사이클 3, 2026-05-17): `stop_loss_main` / `stop_loss_pre_nxt` 우선 → 부재 시 `stop_loss_rate` top-level fallback. `_get_stop_loss_for_board(params, board)` 헬퍼 + `_resolve_active_board()` 활성 보드 조회. SessionTracker 미동작 시 None → fallback (graceful). **15:20 KRX 메인 일괄 청산** (OVERNIGHT 거부, 2026-05-15 결함 D) | **PRE_NXT+MAIN** (POST_NXT 제외) / `k_value_krx_main` `k_value_nxt_pre` (`k_value_nxt_post` 키는 호환 보존만) |
| `long_tail_volatility` | VB 방식 조기 진입 + 전일대비 `min_prdy_rate%`↑. `_limit_up_reached` set으로 모드 관리 | 당일 모드 -3% / 상한가 모드 -5% + 익일 갭/트레일링. **15:20 상한가 미도달 일괄 청산** / 상한가 모드는 익일 NXT 프리 청산 + POST_NXT 손절 모니터링 (`risk.on_tick` 청산 평가는 보드 가드 무관). `_next_day_clear_pending` 가드 (momentum과 동일) | **PRE_NXT+MAIN** (POST_NXT 제외, 2026-05-15 결함 D — 매수만. 보유 종목 손절 평가는 POST_NXT 에서도 작동) |
| `donchian_swing` | 코스피200+코스닥150 고정 유니버스 → 시총 컷 → 60일 일봉 → 20일 신고가 + 60일 EMA 우상향 + 거래대금 1.5×. **prepare 시 candles[0]==오늘이면 candles[1]을 전일로** (장중 재실행 시 부분봉 혼입 차단). 09:05~09:30 매수, 갭 +3%↑ 스킵, 1회만. **`recompute_held_atr()` 직후 또는 함께 `high_since_buy` 일봉 보정 (E3, 2026-05-12)** — 매수일~전영업일 KIS 일봉 high max 로 복구. 시세 미수신 누적으로 chandelier 트레일링이 매수가 부근에 동결되는 결함 차단 (2026-05-12 이마트 사례). 매수일 당일/미래일 skip(미래는 WARNING). sequential await, 종목별 fetch 예외 격리. 보정값이 기존 high_since_buy 초과 시 `db.positions.update_high` + `system_logs` `[high_since_buy_recover]` 1행 | ATR(14)×2 Chandelier 트레일링 + -7% 하드. **시간·15:20 청산 없음** — 멀티데이 보유 (DB positions 영속화) | MAIN |
| `bull_flag_breakout` (2026-05-15 추가) | KRX 등락률 순위 → 시총 ≥ 500억 + 거래대금 ≥ 20억 컷 → 30일 일봉 fetch → **폴 자동 검출**(직전 3~10영업일 누적 +20%↑, 음봉 비율 ≤ 30%) + **플래그 자동 검출**(3~10영업일, 조정 폭 ≤ 폴 폭의 38.2%, 거래량 < 폴 평균 × 60%). 09:05~13:00 **플래그 상단(`flag_high`) 돌파 순간**(`_prev_price[ticker]<flag_high<=now`) + 당일 거래량 ≥ `flag_avg_volume × 2`. `_bought_today` set 1회 가드 + `_cooldown_until[ticker]=date` 3영업일 쿨다운. 부분봉 가드 동일 (candles[0]==오늘이면 [1] 부터) | -5% 손절 / **플래그 하단(`flag_low`) 이탈 → STOP_LOSS** / **측정된 이동 도달 → TRAILING_STOP**(타겟가 = `flag_high + (pole_high - pole_start)`, `_partial_exit[ticker]=True` 마킹 — 1차 구현은 전량 청산) / 잔여 `high_since_buy - ATR×2` 트레일링 / 5영업일 시간 청산 (캘린더일 +2 보정) | MAIN / KRX |
| `vcp_breakout` (2026-05-15 추가) | **미네르비니식 VCP**. 코스피200+코스닥150 → 시총 ≥ 1,000억 컷 → 220일 일봉 fetch → **추세 필터**(종가 > 50EMA > 150EMA > 200EMA + 200EMA 1개월(20영업일) 우상향) → **베이스 자동 검출**(25~75영업일, 깊이 ≤ 25%, 최대 30% — 가장 긴 박스권) → **pullback 점진 수축**(swing high→low→high 검출, 2~4회, 직전 대비 폭 감소, 마지막 ≤ 8%) → **거래량 수축**(마지막 5일 평균 < 베이스 직전 20일 평균 × 70%). 09:05~14:30 **베이스 상단(`base_high`) 돌파 순간** + 당일 거래량 ≥ 20일 평균 × 1.5. `_bought_today` + `_cooldown_until` 7영업일 쿨다운. **`Position._MULTIDAY_STRATEGIES` 멤버 등록**(import 시 frozenset 교체) → `is_next_day` 항상 False, OrderMonitor "청산" 배지 미표시 | -7% 손절 / **베이스 하단(`base_low`) 이탈 → STOP_LOSS** / `high_since_buy - ATR×2` 트레일링 / **50일 EMA 이탈 → TRAILING_STOP**. **시간·15:20 청산 없음** — donchian 컨벤션, 멀티데이 보유 | MAIN / KRX |

공통:
- `prepare()` 단계별 통과 카운트는 `_scan_stats`에 누적 → `get_scan_stats()` → `strategies.<id>.scan_stats`로 프론트 ScanMonitor 깔때기
- VB/LTV `_scan_universe`: 거래량순위 API(`FHPST01710000`) 응답 1건으로 후보 + 시총·전일거래대금 산출(`prdy_vol × (stck_prpr - prdy_vrss)`로 시간 의존 제거)
- VB/LTV/donchian 모두 `prev_idx` 분기 동일: `candles[0].stck_bsop_date == 오늘`이면 candles[1]을 전일로 사용
- 0종목 확정 시 `ERROR` 로그 + `system_logs` 기록

## risk.py

`on_tick()`: ticker_prices 갱신 1회 → `registry.enabled()` 순회 → 전략별 exit/buy 신호.

매수 신호 평가 *전* 가드 (순서):
- **보드 가드**: `session_tracker.is_tradable(strategy_id, params)` — 비활성 보드는 신호 평가 자체 skip
- **시장 레짐 매수 가드 (사이클 2, 2026-05-17)**: `get_current_regime().is_buy_allowed(strategy_id)` — `regime=defensive` OR `vix>25` OR `fear_greed_score>85` OR `<15` 시 모든 전략 매수 차단. **매도/손절은 본 분기 진입 전 `check_exit_signal` 에서 평가 → 영향 없음.** 외부 fetch 실패 / `DKSTOCK_REGIME_ENABLED=false` → `MarketRegime.empty()` → `is_buy_allowed=True` (graceful 기존 동작 유지). 분당 1회 `[regime_block]` INFO 로그 (`_maybe_emit_regime_block`)
- **중복 가드**: `registry.is_ticker_blocked_for_buy()`
- **자금 사전 가드**: `state.is_low_funds_blocked(ticker)` 또는 `current_price > state.total_investment`(1주 매수 자금 미달)이면 skip — OrderEngine 진입 후 cooldown 등록 사후처리에서 매 틱 발생하던 "매수 수량 0 → 900s cooldown" 노이즈 제거
- BUY 신호 발생 시 `state.signal_count_today += 1` (퍼널 카운터)

## market_regime.py (사이클 2, 2026-05-17)

`dkstock.cloud` 매크로 기반 시장 레짐 + 매수 가드 + cash_usage_ratio 자동 조정.

- `MarketRegime` dataclass: regime/regime_desc/cycle_phase/vix/fear_greed_score/buffett_ratio/cash_min/raw
- `MarketRegime.empty()` — 외부 fetch 실패 graceful 폴백 (`is_buy_allowed=True`)
- `MarketRegime.from_macro_cycle(macro)` — dkstock.cloud `/api/macro/macro-cycle` 응답 파싱
- `is_buy_allowed(strategy_id) -> bool` — 복합 임계 OR (defensive/VIX>25/FG>85/FG<15)
- `cash_usage_ratio_from_regime(cash_min)` — `clamp((100 - cash_min)/100, 0.0, 1.0)`
- `refresh_from_dkstock()` — dkstock_client → MarketRegime. 모든 예외 흡수 → empty
- `persist_snapshot(regime, target_date)` — `market_regime_snapshots` 1행 INSERT. empty 는 skip
- `get_current_regime()` / `set_current_regime()` — 모듈 싱글톤 (단일 워커 가정)
- 운영 graceful: `DKSTOCK_REGIME_ENABLED=false` 기본 → 외부 호출 0건, 매수 가드 비활성
- **사이클 5 (2026-05-17) DB 우선 토글**: `src/services/dkstock_client.py::_check_enabled_async` + `src/services/mcp_client.py::_check_enabled_async` + `src/engine/backtest_engine.py::is_enabled_async()` 가 `system_config.get_dkstock_regime_enabled` / `get_kis_mcp_enabled` 먼저 조회 → DB True/False 면 DB 채택, None 또는 예외 시 `settings.*` (.env) fallback. 매 호출마다 DB 조회(캐시 없음) — 운영자 즉시 ON/OFF 보장. 호출 진입점: dkstock_client(login/refresh/_get) / mcp_client(initialize/call_tool/list_tools/health_check) / backtest_engine(run_for_strategy/poll/wait_for_result). Settings UI 의 IntegrationToggleCard 에서 토글 시 즉시 반영 — 컨테이너 재시작 불필요. `_refresh_market_regime_and_persist_safely` (`src/routes/system_integrations.py`) 가 dkstock-regime PUT enabled=true 직후 `asyncio.create_task` 백그라운드 fetch 발화 — toggle 응답은 즉시 반환

`scheduler._boot()` 가 매크로 fetch + snapshot INSERT + cash_usage_ratio 자동 조정 통합 수행. 자세한 흐름은 아래 scheduler.py 섹션.

## order_engine.py

매수/매도 실행 + 체결통보 처리 + DB positions 영속화.

매수 (`execute_buy`):
- **PR-F (P2, 2026-05-15) — NXT 프리마켓 시장가 사전 차단 (preconvert)**: `place_order` 호출 *직전*, `MarketBoard.PRE_NXT in session_tracker.active` AND `MarketBoard.MAIN not in session_tracker.active` AND `buy_exchange in ("NXT", "SOR")` 면 시장가 거부(APBK0918 [프리마켓] 시장가 매매 불가) 100% 예측 → 사전에 `step_up(current_price, 5)` 지정가(`OrderDivision.LIMIT`) 로 변환해 발사. **membership 체크 (PR #9 Codex P2)**: 08:30~09:00 동안 `active={PRE_NXT, KRX_OPEN}` 인 후반 30분도 커버 — exact equality(`== frozenset({PRE_NXT})`) 는 false 처리되어 시장가 거부 패턴 반복하던 결함 차단. 변환 시 `state.pending_buy_amounts[ticker] = order_price * quantity` 동기 갱신, `record_price = order_price` 로 trade_history PENDING / `_pending_buy_orders` price 기록 — 정합성 유지. INFO 로그 `[market_order_preconvert_pre_nxt] ticker=... exchange=... current_price=... converted_to_limit_price=...` 1행. session_tracker 접근 예외는 swallow → 기존 사후 폴백(`is_market_order_disallowed`) 분기에서 자연 회복. MAIN 보드 / KRX 거래소 / 다른 보드 동시 활성 케이스는 시장가 그대로 (변환 안 함). 2026-05-15 08:00:34 064400 LTV 매수 사례 — 매번 시장가 거부 → 5호가 폴백 패턴의 운영 노이즈 사전 차단
- 진입 시 `is_buy_blocked()` + `is_low_funds_blocked(ticker)` → 차단
- 매수가능 캐시 (`BUYABLE_CACHE_TTL=60s`) — `get_buyable()` KIS 호출 매 틱 → 분당 1회
- `max_buy_quantity<=0` 또는 `KisApiError(insufficient_cash)` → `block_buy(now+BUY_BLOCK_DURATION=900s)`
- `calc_buy_quantity()<=0` → `block_low_funds(ticker, now+LOW_FUNDS_COOLDOWN=900s)`
- **`KisApiError(is_market_order_disallowed)` (msg1 "시장가매매불가" 변형) → 지정가 5호가 폴백 1회** — `step_up(current_price, steps=5)` 가격으로 `OrderDivision.LIMIT` 재호출. 매핑 등록(`_order_qty/_order_strategy/_order_ticker/_pending_buy_orders`) + `_completed_orders` race 가드 + `insert_trade(PENDING, price=fallback_price)`는 시장가 경로와 동일 동기 순서. 폴백도 거부되면 `block_low_funds(ticker, now+LOW_FUNDS_COOLDOWN)` cooldown 등록. 2026-05-11 계양전기 거부 대응 (`docs/kis/error-codes.md` 4-2절). 진짜 원인은 Phase A1(`src/api/base.py`)의 `[kis_rejection]` 영구 로깅으로 다음 거부에서 자동 캡처
- 락/cooldown은 다음 잔고 sync(15분 주기)에서 `unblock_buy()` + `clear_low_funds()`로 일괄 해제

매도 (`execute_sell(..., limit_price=0)`):
- `_selling` set 중복 매도 차단
- `limit_price > 0` 이면 `OrderDivision.LIMIT` + `exchange="NXT"` 강제 라우팅 (NXT 지정가). 0 이면 시장가 + 전략 `_strategy_exchange()` 라우팅. 호가단위 정렬은 호출자가 `util.tick_size.step_down`으로 책임
- `KisApiError(insufficient_quantity)` 시 3회 재시도 생략 + 즉시 break + 메모리 포지션 + DB positions 정리
- **`is_market_closed_rejection(err)` (장운영시간 외 / 매매 불가 시간 / 거래시간 외)** → 재시도 중단 + `state.positions`·DB `positions`·`_selling` 모두 **보존** + 다음 거래 가능 시각에 자연 재트리거. NXT 프리/애프터가 시장가를 거부할 때 좀비 포지션 방지 (KIS 계좌엔 보유, 시스템엔 삭제되던 결함 차단)
- **`is_market_order_disallowed(err)` + `order_division==MARKET` (Phase C, 2026-05-11)** → 지정가 5호가 폴백 1회. `step_down(scanner.ticker_prices[ticker]["current_price"], steps=5)` 가격으로 `OrderDivision.LIMIT` 재호출. 매핑(`_order_qty/_order_strategy/_order_ticker`) 동기 등록 + `_completed_orders` race 가드 + `insert_trade(PENDING, price=fallback_price)`는 매수 폴백·시장가 경로와 동일 동기 순서. 폴백 성공 → `return`(`_selling` 은 체결통보에서 해제). 폴백 실패 → `_selling.discard` + `write_log` + `return` (positions 메모리/DB **보존**, cooldown 등록 안 함 — 청산 의무, 다음 사이클 자연 재트리거). 지정가 매도(`limit_price>0`)에서는 폴백 분기 진입 안 함 (이미 지정가, 기존 3회 재시도 유지). 현재가 캐시 miss(`cur_price<=0`)면 폴백 불가 → 일반 재시도 흐름. stock_master 사후 보강은 NXT `is_market_closed_rejection` 전용 — APBK1943은 호가 자체 불가 사유라 NXT 무관. 2026-05-11 계양전기 09:00:21 매도 ×3 실패(APBK1943 "시장가호가불가") 대응. `docs/kis/error-codes.md` 5-4절

체결통보 race 가드:
- 주문번호 매핑(`_order_qty / _order_strategy / _order_ticker / _pending_buy_orders`)은 **`place_order` 응답 직후 동기 영역에서 등록** (`await insert_trade` 진입 *전*) — 시장가 즉시체결 시 체결통보가 await 도중 도착해도 올바른 strategy로 라우팅. 누락 시 기본값 "momentum"으로 잘못 INSERT됨
- `_completed_orders` set + `update_trade_status` 영향 row 0건 보정 INSERT — 체결통보가 REST 응답보다 먼저 도착해도 trade_history 단일 COMPLETED row 보장. `execute_buy/sell`은 응답 후 set 체크해 PENDING INSERT 생략

거래소 라우팅 (`exchange` 파라미터):
- 모든 `place_order` / `cancel_order` 호출에 `_strategy_exchange(strategy_id)` 로 조회한 전략 `exchange` 전달 (미설정 시 KRX)
- 적용: `execute_buy` / `execute_sell` / `_schedule_cancel` / `_schedule_cancel_and_reorder` / `cancel_remaining`
- 모멘텀 익일 청산이 SOR로 라우팅되면 KIS가 NXT 프리 시간(08:00~09:00)에 NXT로 자동 분배 → KRX 메인 시작 전 청산 가능
- **NXT 거래가능 사전 차단 (Phase G, 2026-05-11)** — `_strategy_exchange_async(strategy_id, ticker=...)` 비동기 변형이 `execute_buy`(시장가/지정가 폴백) + `execute_sell`(시장가 청산)에 사용된다. `src.db.stock_master.get(ticker).nxt_tradable=False` 면 NXT/SOR → **KRX 강제 다운그레이드** + `system_logs` `[nxt_downgrade]` prefix 1행 (strategy/ticker/원래 exchange/적용 exchange). 캐시 miss 또는 stock_master 예외는 전략 기본 exchange 그대로 (보수적 fallback). `place_order` 호출 *전* await 로 완료해 주문번호 매핑 동기 등록 규약은 그대로 유지. 익일 청산 NXT 지정가(`limit_price>0`)는 사전 차단 적용 안 함 — exchange="NXT" 강제 유지(호출자 책임)
- **거부 응답 사후 보강** — `execute_sell` 의 `is_market_closed_rejection` 분기에서 NXT 시간대(08:00~09:00, 15:30~20:00) 거부면 `stock_master.upsert_one(ticker, nxt_tradable=False)` 즉시 반영. 같은 종목 다음 사이클부터 자동 KRX 다운그레이드

체결 후처리:
- 매수 체결 → DB `positions` 저장 + `cached_buyable_at = 0` (가용액 캐시 무효화)
- 매도 체결 → DB positions 삭제 + `sold_today` 등록 (당일 재매수 차단)
- 체결통보 처리 실패 안전장치: ticker 매핑 실패 → `pending_buys` 제거, strategy 미발견 → `_selling` 해제

퍼널 카운터: `place_order` 직전 `order_attempt_today += 1`, `_handle_buy_fill` 첫 체결 시 `fill_count_today += 1`

## session.py

`MarketBoard` enum: `pre_nxt`(NXT 프리 08:00~) / `krx_open`(08:30~09:00) / `main`(09:00~15:20) / `krx_after`(15:30~18:00) / `post_nxt`(NXT 애프터 15:30~20:00).

- `_BOARD_SCHEDULE`: 시각 → 활성 보드 frozenset (H0NXMKO0 미수신 시 fallback)
- `SessionTracker.tick()`: `_session_loop`(scheduler.py 30초 주기)에서 호출
- `is_tradable(strategy_id, params)`: 활성 보드 ∩ 전략 `tradable_boards` ≠ ∅
- `on_h0nxmko0(...)`: NXT 장운영정보 수신 (KIS 명세 미확정 → 코드 기록만)

## scheduler.py — KRX/NXT 통합 운영 08:00~20:00

시간 상수 (`scheduler.TIME_*`):

| 상수 | 시각 | 동작 |
|------|------|------|
| `TIME_AUTO_START` | 07:45 | DB `auto_start` 우선 폴백 자동 시작 (`_is_auto_start_enabled()`) |
| `TIME_BOOT` | 07:50 | `_boot()` — DB positions 우선 복구 → KIS 잔고 교차 검증 → 미체결 주문 복구 → **`_eager_refresh_stock_master_for_held_positions()` (I3, 2026-05-12)** 보유 + 익일청산 후보 ticker 를 stock_master 에 eager 갱신. Phase G lazy 한계(캐시 miss → SOR/NXT 그대로 발사) 차단. **`cash_usage_ratio` 곱셈 (J3, 2026-05-12)**: `summary.net_asset` 산출 직후 `get_cash_usage_ratio()` 조회 → `int(net_asset × ratio)` 로 `allocate_funds()` 호출. **사이클 2 (2026-05-17) — 시장 레짐 fetch 통합**: `_refresh_market_regime_and_persist()` → dkstock.cloud 매크로 → `set_current_regime()` + `market_regime_snapshots` INSERT (graceful — empty 폴백 시 모두 skip). 직후 `_resolve_cash_usage_ratio()` 가 `auto_regime_adjust=true` + `regime.computed_cash_usage_ratio() != None` 일 때 레짐 cash_min 기반 자동 갱신 (DB `set_cash_usage_ratio` + 산출값 반환). `auto_regime_adjust=false` 또는 empty 레짐이면 운영자 수동값 그대로. `[cash_usage_ratio]` + `[market_regime]` 2 prefix system_logs 1행씩 |
| `TIME_PRESUBSCRIBE` | 07:55 | `_collect_presubscribe_tickers()` — VB/LTV/donchian + 모든 전략 보유 합집합 사전 구독 |
| `TIME_PRE_NXT_OPEN` | 08:00 | 익일 청산 task(`_execute_next_day_clear`, `NEXT_DAY_STABILIZE_SECS=30s`) + `_confirm_breakout_open_prices(board="pre_nxt")`. **시가 수신 → 갭률 트레일링 또는 NXT 지정가(`step_down(open,1)`, `EXCG_ID_DVSN_CD=NXT`, `ORD_DVSN=00`). 시가 미수신 → `_pending_next_day_clear` set 등록 후 보류** (NXT 거래불가 종목 추론) |
| `TIME_KRX_OPEN_CONFIRM` | 09:00:05 | `_confirm_breakout_open_prices(board="main")` — VB/LTV가 KRX 09:00 시가로 보드별 별도 target_price 계산. 직후 `_drain_pending_next_day_clear()` — 08:00 보류 종목을 KRX 시장가로 일괄 청산. **PR-H idempotent 강화 (2026-05-15)**: 호출 시점에 모든 대상 종목이 이미 `_is_confirmed(strategy, ticker)` 면 1차 폴링 / 2차 KIS API 폴백 / 종합 INFO 로그 / `_emit_breakout_open_confirm` 모두 skip. DEBUG 로그만 1행 (`[confirm_open_prices_skip] board=...`). 부분 확정은 기존 분기 그대로 (안전 보존). 운영 결함 회복: 5번 EC2 재시작 직후 LTV `_scanned_tickers` 빈 케이스로 `_reprepare_breakout_if_empty` 가 LTV 만 발화 → prepare 가 `_open_confirmed[ticker]={}` reset → 시가 재확정 호출 → 매번 INFO 로그 (2026-05-15 15:30~16:39 LTV 4회 사례). KIS Rate Limit + 운영 가시성 노이즈 동시 차단 |
| `TIME_SCAN_START` | 09:30 | 모멘텀 `scan_stocks()` + 통합 구독 |
| `TIME_KRX_MAIN_BUY_STOP` | 15:20 | `_force_clear_main_only` — POST_NXT 미활성 전략만 청산, 활성 전략은 19:50까지 보유 |
| `TIME_KRX_MAIN_CLOSE` | 15:30 | KRX 메인 마감 → NXT 애프터 전환, 구독 유지. **`_confirm_breakout_open_prices(board="post_nxt")` 명시 호출 (M, 2026-05-12)** — POST_NXT 시점엔 자동 결정(main 우선)이 SessionTracker 전환 race 가능. 누락 시 VB/LTV 후보의 `_targets[t]["boards"]["post_nxt"]["open_price"]` 영영 비어 "시가 대기" 좀비 잠복 (2026-05-12 사용자 보고 6종목 사례) |
| `TIME_NXT_POST_BUY_STOP` | 19:50 | `buy_disabled = True` (NXT 애프터 신규 매수 중단 안전 마감, 변경 금지) |
| `TIME_NXT_POST_CLOSE` / `TIME_RECOMMENDATION` | 20:00 | `unsubscribe_all()` + `generate_recommendations()` — 동기 await 순차 (자문 ~3분, settlement 20:10 까지 7분 여유). **Phase 0 (2026-05-15)**: 자문 시점 19:50 → 20:00 이동 — Phase 3 백테스트 검증 정합성 사전 확보 |
| `TIME_SETTLEMENT` | 20:10 | `_settle()` → `generate_daily_log_report()` → `_reset_daily_state()` 순서. **퍼널 카운터 초기화는 분석 *후*** (분석이 0을 수집하지 않도록 분리) |

기타:
- WebSocket 연결 직후 **체결통보 자동 구독**(실전 H0STCNI0+HTS ID / 모의 H0STCNI9+계좌번호) + 통합 장운영정보 `H0UNMKO0`/`005930` (실전 한정, 모의 미지원)
- `_load_strategy_config()`: DB `strategy_config`에서 비중/`tradable_boards`/`exchange`/`k_value_*` 복구
- `run_daily()`: 주말+공휴일 건너뜀(KIS `chk-holiday`), 매일 시작 전 DB auto_start 재확인
- 중간 시각 시작: 현재 시각 이후 스케줄부터 실행
- `_scan_loop()`: 09:30 이후 `SCAN_INTERVAL=300s` 주기, **VB+LTV+donchian + 모든 전략 보유** 합집합 재구독 (이전엔 VB만 재구독해 swing/LTV/보유 시세 끊겨 손절 누락). **빈 `_targets` 자동 재 prepare 가드 (KIS 5xx 회복)**: 통합 구독 직후 `_reprepare_breakout_if_empty()` 호출 — VB/LTV 중 `get_scanned_tickers()`==[] 이면서 `enabled=True` 인 전략만 prepare() 1회 재시도. donchian_swing 은 대상 아님(고정 유니버스). prepare() 예외는 ERROR 로그로 흡수, 다음 사이클 자연 재시도. **Phase D (2026-05-11)**: 재 prepare 가드 직후 `_report_tick_coverage()` 1행 노출 — `kis_ws.get_subscribed_tickers()` 중 최근 60초 내 `ticker_last_tick` 갱신 비율을 `INFO` + `system_logs` (prefix `[tick_coverage]`) 로 카운트. "구독은 됐으나 시세 무수신" 결함(어제 VB/LTV 종일 시세 무수신) 즉시 가시화. 본체 예외 흡수
- `_stale_watcher_loop()` / `_check_and_resubscribe_stale()` (K, 2026-05-12): `start()` 안에서 `_session_task` 발화 직후 `_stale_watcher_task = asyncio.create_task(_stale_watcher_loop())` 시작. `STALE_WATCHER_INTERVAL_SECS=30s` 주기로 `kis_ws.get_subscribed_tickers()` 와 `scanner.ticker_last_tick` 비교 → `STALE_FRESHNESS_SECS=60s` 초과면 stale. 종목별 누적 `_stale_retry_count` retry 카운터: 1~3회 → `_send_subscribe(TICK_TR_ID, t, subscribe=True)` 재발송, 4~6회(`> STALE_FORCE_REREGISTER_AFTER=3`) → `unsubscribe`+`subscribe(bypass_limit=True)` 강제 재등록, 6회 초과 → skip(`skipped_giveup` 카운트, 다음 `_scan_loop` 사이클에 위임). 전체 fresh 회복 시 `_stale_retry_count.clear()` 자동 리셋. Rate Limit 보호 50ms sleep, 종목별 예외 격리. 본체 예외는 ERROR 로그로 흡수해 다음 사이클 진행. `[stale_watcher] subscribed=N stale=K resubscribed=A force_reregistered=B skipped=C` INFO + `write_log` 1행. `start()` finally + `stop()` 의 task_attr 튜플에 `_stale_watcher_task` 포함(좀비 task 방지). `_reset_daily_state()` 가 `_stale_retry_count.clear()` 추가. F1(재연결 1회) + `_scan_loop`(5분) + K(30s) 3중 안전망. 2026-05-12 11:48 fresh=1/stale=26 운영 사고 대응. **사이클 7-C (2026-05-18) 풀 통합**: 단일 세션 직접 호출(`kis_ws._send_subscribe` / `kis_ws.unsubscribe` / `kis_ws.subscribe`) → 풀 헬퍼(`kis_ws_pool.resend_subscribe_for_ticker` / `kis_ws_pool.unsubscribe_in_pool` / `kis_ws_pool.subscribe(priority='HIGH', bypass_limit=True)`) 위임. 풀의 `_ticker_to_session` 분배 추적을 활용해 정확한 세션(메인/보조)에서 재전송/재등록. 강제 재등록 시 `unsubscribe_in_pool` 이 추적 dict 에서 제거 → 이어지는 `subscribe` 가 라운드로빈 재선택 (보조 0개 시 메인 fallback 정상)
- `_sync_orders_to_db(orders)`: KIS 주문체결내역(`get_daily_orders`)을 trade_history 에 동기화. MTS/HTS 수동 매매분도 반영. **L5(2026-05-12)**: 중복 판정 키를 `ticker` 단독 → **`(ticker, order_no)` 페어**로 변경 — 같은 ticker 의 다른 order_no(분할/재매수 등)를 위양성 skip 하지 않음. `get_today_buy_trades / get_today_sell_trades` 의 KST timezone 명시 쿼리(L5, db/CLAUDE.md)와 짝. 2026-05-12 005930 보완 INSERT 사고(timezone 누락 + ticker 단독 중복 체크) 두 원인 모두 차단
- `_sync_positions_from_balance()`: 15분 주기. **strategy 매핑은 trade_history 직전 BUY 행에서 상속** (이전 momentum 하드코딩 결함 차단). 종료 시 `unblock_buy()` + `clear_low_funds()` 일괄 해제
- `_execute_next_day_clear()`: 다음 영업일 NXT 프리 첫 거래 시가 수신 후 30s 안정화 → 갭률 트레일링 또는 NXT 지정가(`step_down(open,1)`) 매도. **시가 미수신이면 `_pending_next_day_clear` set에 `(ticker, strategy_id)` 등록 후 즉시 청산 보류** — `high_since_buy` 폴백 + 갭률 0% 즉시 청산 경로는 전일 고가 혼입 결함으로 제거. `_resolve_open_price()` 폴백은 NXT 거래가능 종목 추론용으로만 유지. **Phase G (2026-05-11)**: `stock_master.get(ticker).nxt_tradable=False` 가 1순위 판별 — 시가 폴링/안정화 대기 거치지 않고 즉시 `_pending_next_day_clear` 등록 (NXT 주문 시도 0건). stock_master miss + 예외 시에만 기존 시가 휴리스틱으로 fallback
- `_drain_pending_next_day_clear()`: `_confirm_breakout_open_prices(board="main")` 직후 호출. `_pending_next_day_clear` 종목을 KRX 시장가(`limit_price=0`)로 일괄 청산 → 보류 set 비움
- **NXT 익일 청산 구조화 로그 (PR-B, 2026-05-14)**: 사람용 한국어 로그와 별도로 Loki 파싱용 영문 prefix 1행 추가. 보류 등록 시점 `_execute_next_day_clear` 에서 `[next_day_clear_deferred] ticker={t} strategy={s} reason={nxt_not_tradable|nxt_open_missing}` (Phase G stock_master 차단 vs 시가 미수신 분기). drain 시점 `_drain_pending_next_day_clear` 에서 종목별 `[next_day_clear_drained] ticker={t} strategy={s} result={success|fail} elapsed_ms={ms}` (success INFO / fail WARNING). `log_analysis_engine._aggregate_next_day_clear` 가 prefix 정규식으로 `metrics.next_day_clear.{deferred,drained_success,drained_fail}` 카운트 노출 — 다음날 20:10 리포트로 추적 가능
- `_reset_daily_state()`: 전략별 positions/pending_buys/sold_today + OrderEngine 추적 상태 + scanner 글로벌 dict (ticker_prices/ticker_prev_close/ticker_market_info/ticker_names → STATIC_TICKER_NAMES로 재시드 / **ticker_last_tick.clear()** Phase D) + `_pending_next_day_clear.clear()` 전체 초기화

## scanner.py

- `scan_stocks()`: 모멘텀 등락률 순위
- `subscribe_filtered_stocks(tickers, extra_tickers, source_counts=None, *, priority_groups=None)`: 합집합 구독.
  - **사이클 7-C (2026-05-18) — 풀(`kis_ws_pool`) 위임 + priority 명시**: priority_groups 분기에서 `kis_ws.subscribe(...)` 직접 호출 → `kis_ws_pool.subscribe(tr_id, t, priority='HIGH'|'LOW', bypass_limit=True|False)` 위임. `positions`/`next_day_clear` → `priority='HIGH'` + `bypass_limit=True` (메인 세션 절대 보장), `breakout`/`momentum`/`swing` → `priority='LOW'` + `bypass_limit=False` (보조 라운드로빈 우선, 보조 가득 시 메인 fallback). 풀 내부에서 보조 0개 → 메인 only 동작 (회귀 0). 평탄 처리 분기(`priority_groups=None`)는 기존 `kis_ws.subscribe` 직접 호출 보존 (외부 호환)
  - **`source_counts` dict(`vb/ltv/swing/momentum/positions`) 전달 시 출처별 카운터 로그 노출 (Phase B, 2026-05-12)** — 형식 `[scanner] 실시간 시세 구독 완료: total=N (vb=A, ltv=B, swing=C, momentum=D, positions=E)`. 출처별은 합집합 *전* 원본 개수(중복 가능), total 은 dedupe 후. None 이면 기존 "(모멘텀: X, 기타: Y)" fallback. 영문 라벨 유지 — Grafana/Loki 쿼리 안정성
  - **`priority_groups` dict(`positions/next_day_clear/swing/momentum/breakout`) 전달 시 우선순위 큐로 처리 (E1, 2026-05-12 + PR-E 2026-05-15 2-pass)** — HIGH→LOW 순서로 subscribe. `positions/next_day_clear` 는 `bypass_limit=True` 로 `MAX_SUBSCRIPTIONS=41` 무시 절대 보장. 후순위(breakout/momentum/swing) **2-pass**: 1차에서 `breakout[:BREAKOUT_LOW_CAP=25]` + momentum + swing 순으로 잔여 슬롯에 add → 2차에서 `MAX - len(_subscriptions) > 0` 면 breakout cap 초과분(overflow) 을 잔여 슬롯에 흡수 add. 최종 drop = `max(0, len(overflow) - absorbed_overflow)` 만 `drop_counts["breakout"]` 에 합산. drop>0 시 `[priority_drop] breakout=X momentum=Y swing=Z total_subscribed=N max=41 high_count=H low_remaining=R` INFO + WARNING `system_logs` 영구 저장. 중복 종목은 HIGH 순위로 1회만 subscribe (후순위에서 skip, drop 카운트에도 미포함). HIGH 단독 41 초과 시 ERROR + `system_logs`. None 이면 기존 평탄 처리 fallback (외부 호환). `source_counts` 로그는 `priority_groups` 와 무관하게 동시 노출. **PR-E 2-pass 결함 차단 (2026-05-15 07:55:08)**: 운영 로그 `[priority_drop] breakout=3 ... total_subscribed=30 max=41 ... low_remaining=11` — 11 슬롯 미사용인데도 cap 초과 3 종목이 silently drop 되어 운영 슬롯 낭비 + 부당 drop. 2-pass 가 잔여 슬롯에 overflow 흡수해 두 결함 동시 차단. momentum 슬롯 보호(cap 의 본래 의도)는 1차 단계에서 `breakout[:cap]` 처리로 보존 — overflow 가 momentum 슬롯 침범 안 함
  - scheduler 호출부 4곳(사전 구독·중간 부팅 사전 구독·09:30 통합 구독·`_scan_loop` 재구독)이 `_build_subscription_source_counts(momentum_tickers=...)` 와 `_build_priority_groups(momentum_tickers=...)` 산출 dict 를 전달
- `KOSPI_200_TICKERS` / `KOSDAQ_150_TICKERS`: donchian_swing 고정 유니버스
- `STATIC_TICKER_NAMES` / `_parse_static_ticker_names()`: 모듈 import 시 자기 파일을 정규식(`"(\d{6})",\s*#\s*(.+)$`)으로 파싱해 인라인 코멘트의 종목명을 dict로 추출. 모듈 로드 시 `ticker_names.update(STATIC)` — KIS `inquire-price`가 빈 종목명 응답해도 시장명으로 떨어지지 않도록 보강
- 공용 데이터: ticker_names, ticker_prices, ticker_prev_close, ticker_market_info, **ticker_last_tick**(Phase D — `risk.on_tick` 호출 시 KST `datetime`으로 갱신, `_report_tick_coverage` 가 사용)
- **`get_scan_status()` tick_coverage 4종 키 (G3, 2026-05-12)**: `tick_coverage_total/acked/fresh/stale` 추가. `_subscriptions` TICK 필터 size / `_subscriptions_acked` TICK 필터 size / 최근 60s 내 tick 수신 카운트 / 60s 미수신 카운트. 기존 `subscribed_count` 보존(호환성). `/api/trading/status` 의 `scan` 필드에 그대로 동봉되어 ScanMonitor 가 stale 기반 색상 배지(0=gray / 1~5=yellow / 6+=red) + total/41 진행바(80%+ amber) 노출

## log_analysis_engine.py — 일일 로그 분석

20:10 정산 직후(`_settle()` 완료, `_phase = "log_analysis"`) `generate_daily_log_report()` 호출. 호출 *후* run loop가 `_reset_daily_state()` 별도 실행 (퍼널 카운터 보존).

당일 KST 00:00~now `system_logs`(레벨/패턴/샘플) + `trade_history`(매수/매도/실현손익/전략별·상태별) → OpenAI → `daily_log_reports` INSERT.

확장 메트릭:
- `api_metrics`: `api/base.py::get_request_metrics()` (5xx/4xx/network/retries + path별 5xx top 5). INSERT 후 `reset_request_metrics()`
- `strategy_funnel`: 전략별 `{signals, orders, fills}` (registry 순회) — VB가 신호만 있고 체결 없는 패턴 등 깔때기 추적
- `trades.by_ticker_pnl` (SELL PnL 절대값 top 5) / `trades.by_hour_pnl` (KST hour별)

출력 스키마: `{summary, findings: [{category, severity, title, detail, suggestion}]}`. `(target_date)` UNIQUE → 동일 영업일 재실행 시 None. OpenAI 타임아웃 60s, 실패 시 메트릭만 보존 INSERT.

## recommendation_engine.py / recommendation_metrics.py — 20:00 AI자문 (Phase 0, 2026-05-15: 19:50 → 20:00 이동)

- 전략별 metrics(승률/평균손익/손절률/누적수익률) → OpenAI → `parameter_recommendations` INSERT (status: pending)
- `(target_date, strategy_id)` UNIQUE
- `/api/recommendations/{id}/apply`: 사용자 키 선택 적용 → `strategy_config.params` 갱신 + status applied/partial
- `expire_pending_before(target_date)`: 이전 영업일 pending 자동 만료
- **J4 (2026-05-12) AI자문 고도화** — `_validate_recommendations` 4-tuple 반환 `(validated_params, reasoning, weight, notes)`. user_payload 에 `current_weight` + `peer_weights` + `peer_metrics` 추가해 자산배정 자문(`recommended_weight` 0.0~1.0) + 로직 자유 텍스트 자문(`code_review_notes` ≤ 2000자) 컨텍스트 제공. peer metrics 는 사전 일괄 수집 후 자기 제외 dict 전달 — N²번 API 호출 차단. apply 라우트가 `apply_weight=true` 옵션을 받으면 `save_weights({sid: w})` + `strategy.config.weight` 메모리 반영 + `applied_weight` 트래킹. `allocate_funds()` 즉시 재호출 금지 — 다음 _boot 에서 자연 반영
- **Phase B (2026-05-17) PARAM_RANGES 화이트리스트 확장** — 5/15 첫 자문 `code_review_notes` 권고 반영. `PARAM_RANGES` 에 7 키 추가: `k_value_krx_main`/`k_value_nxt_pre`/`k_value_nxt_post` 각 `(0.5, 2.0)` (VB, LTV) + `donchian_period` `(10, 60)` + `long_ma_period` `(20, 120)` + `volume_multiplier` `(1.0, 5.0)` + `atr_trail_mult` `(1.0, 5.0)` (donchian_swing/bull_flag/vcp). `INT_PARAMS` 에 `donchian_period`/`long_ma_period` 추가(정수 일봉 개수). `min_prdy_rate` 는 사이클 이전부터 등록되어 있어 중복 추가하지 않음. 다음 자문 사이클(5/18 월 20:00) 부터 OpenAI 가 보드별 K값/기간/거래량 멀티/ATR 트레일 자동 튜닝 가능. 회귀 가드: `tests/unit/engine/test_recommendation_param_ranges.py` 9 케이스
- **Phase A (2026-05-17) LTV `stop_loss_hits=0` metrics 결함 진단 (진단만)** — `recommendation_metrics.compute_metrics()` 의 `current_params.get("stop_loss_rate")` 단일 키 참조 결함. LTV(`long_tail_volatility`) 만 `intraday_stop_loss`/`overnight_stop_loss` 분리 키 사용 → `None` 폴백 → `if stop_loss_rate < 0` 분기 영영 skip → 항상 0. 5/15 실측: 자문 metrics `stop_loss_hits=0` vs trade_history `pnl_pct ≤ -2.5%` 1건(`064400` -3.030%). metrics 결함 분류(a). fix 는 별도 사이클 인계 — `_workspace/red/phase-a-ltv-stop-loss-hits.md`
- **Phase A2 (2026-05-17) LTV `stop_loss_hits` fix** — `recommendation_metrics.py::_normalize_stop_loss_rate(params: dict) -> float` 헬퍼 추가. 3 키(`stop_loss_rate`/`intraday_stop_loss`/`overnight_stop_loss`) 후보 수집 → `_safe_float` 변환 → 음수만 인정 → `min(candidates)` 반환(절대값 큰 = 가장 보수적). 후보 없으면 0.0 (`compute_metrics` 분기 skip 보존). `compute_metrics()` 의 `_safe_float(current_params.get("stop_loss_rate"))` 단일 키 참조 1줄을 헬퍼 호출로 교체. LTV 분리 키 흡수 + 다른 5 전략(momentum/VB/donchian/bull_flag/vcp) 회귀 보존. 5/15 발화된 LTV 자문 metrics 는 소급 재계산 안 함 — 5/18 월 20:00 첫 자문부터 정상. 회귀 가드: `tests/unit/engine/test_recommendation_metrics_ltv_stop_loss.py` 8 케이스
- **사이클 1 (2026-05-17) 비중조절 사유 분리 + UI 카드 순서** — `_validate_recommendations()` 5-tuple `(validated_params, reasoning, weight, notes, weight_reasoning)` 로 확장. SYSTEM_PROMPT 에 `weight_reasoning` 필드 명시(≤1000자, 한국어, 통합 `reasoning` 과 별개). `weight=None` 이면 `weight_reasoning=None` 자동 정리, `weight` 있는데 사유 누락/null/빈문자열/비-str → `WEIGHT_REASONING_FALLBACK="(사유 미제공)"` + WARNING. 1000자 초과 truncate + WARNING. 마이그 021 `parameter_recommendations.weight_reasoning TEXT NULL` + `insert_recommendation(weight_reasoning=...)` kwarg + `RecommendationItem.weight_reasoning` + `Recommendations.tsx` 자산 배정 카드를 **최상단** 으로 이동 + amber 영역(`data-testid="weight-reasoning-{id}"`, `max-h-32 overflow-y-auto`) 으로 사유 분리 강조. 5/15 발화된 row 영향 없음 (소급 재계산 안 함). 회귀 가드: `tests/unit/engine/test_recommendation_weight_reasoning.py` 11 케이스 + `tests/unit/db/test_parameter_recommendations_weight_reasoning.py` 4 케이스 + 프론트엔드 7 케이스
- **사이클 4 (2026-05-17) 매크로 레짐 → AI 자문 user_payload 통합** — `MarketRegime.to_advisor_dict()` 12 키 dict 반환(regime/regime_desc/cycle_phase/vix/vix_level/fear_greed_score/fear_greed_label/buffett_ratio/buy_blocked/block_reason/cash_min_recommended/stock_max_recommended). raw/cash_min 원본 등 내부 필드 제외. VIX 분류 `_classify_vix()` 임계 15/25/35 (low/normal/elevated/high). Fear & Greed 분류 `_classify_fear_greed()` 임계 15/35/65/85 (극공포/공포/중립/탐욕/극탐욕). `_call_openai()` 가 `get_current_regime()` 호출 후 `regime is not None and not regime.is_empty()` 분기로 user_payload 에 `market_regime` 키 추가 — empty/None 은 graceful skip (사이클 1 의 8 필드 회귀 보존). SYSTEM_PROMPT 끝에 매크로 컨텍스트 활용 가이드 1 문단 추가(defensive/neutral/aggressive 분기 + buy_blocked=True 시 매수 임계 변경 권고 무용 + weight_reasoning/code_review_notes 에 매크로 영향 명시 권장). 운영 graceful: `DKSTOCK_REGIME_ENABLED=false` 기본 → 자문 user_payload 미포함 → 기존 동작. 5/15 자문 row 영향 없음 (소급 재계산 안 함). 회귀 가드: `tests/unit/engine/test_recommendation_market_regime_payload.py` 27 케이스(A empty 키 미포함 / B None 키 미포함 / C defensive 활성 포함 / D 12 키 / E VIX 9 / F FG 11 / G raw 제외 / H SYSTEM_PROMPT 키워드 / I 사이클 1 8 필드 회귀) + `tests/integration/test_recommendation_with_market_regime.py` 3 케이스. autouse fixture 로 모듈 싱글톤 reset — risk_on_tick 오염 차단
- **사이클 3 (2026-05-17) VB 보드별 손절 분리** — 5/15 VB `code_review_notes` 권고 반영. `PARAM_RANGES` 에 `stop_loss_main`/`stop_loss_pre_nxt` `(-15.0, 0.0)` 2 키 추가(`stop_loss_post_nxt` 는 VB POST_NXT 미사용 — 사이클 3-B 재검토). `recommendation_metrics._normalize_stop_loss_rate()` 후보 키 3→5 확장(`stop_loss_main`/`stop_loss_pre_nxt` 추가, `min(candidates)` 정책 유지) → `compute_metrics.stop_loss_hits` 가 VB 보드별 키 운영에서도 정상 카운트. `VolatilityBreakoutStrategy._get_stop_loss_for_board(params, board)` staticmethod 헬퍼 신규(우선순위: 보드별 키 음수 → top-level `stop_loss_rate` fallback) + `check_exit_signal` 손절 분기에서 `_resolve_active_board()` 호출 후 헬퍼로 임계 결정. **자율 결정 — 옵션 2 (시그니처 미변경 + VB 내부 SessionTracker 조회)** 채택: `check_exit_signal(ticker, current_price, open_price)` 시그니처 6 전략 공통 + 테스트 mock 5+ 영향 0, `risk.on_tick` 호출부 변경 0. SessionTracker 미동작 시 `_resolve_active_board()=None` → top-level fallback (graceful). 마이그 024 (적용 보류) — `strategy_config.params.stop_loss_rate` → `stop_loss_main/stop_loss_pre_nxt` 멱등 자동 복사. 5/18 첫 발화 영향 없음(코드만 + 마이그 보류 + 5/15 운영값 `stop_loss_rate=-3.5` fallback). LTV/momentum/donchian/bull_flag/vcp 영향 0. 회귀 가드: `tests/unit/engine/strategies/test_volatility_breakout_board_stop_loss.py` 6 케이스 + `tests/unit/engine/test_recommendation_metrics_board_stop_loss.py` 9 케이스 + `tests/unit/engine/test_recommendation_param_ranges_board_stop_loss.py` 4 케이스 + `tests/integration/test_vb_board_stop_loss_fallback.py` 3 케이스. 사이클 3-B(LTV 보드 × 시간 모드 4 조합) 명세: `_workspace/cycle3b_ltv_board_stop_loss_spec.md`

## 새 전략 추가
1. `strategies/` 에 `StrategyBase` 서브클래스 (`prepare/check_buy_signal/check_exit_signal/calc_buy_quantity`)
2. `scheduler.py` `__init__`에 `registry.register()` 추가
3. 필요 시 `scanner.py`에 스캔 함수 추가
4. `_workspace/00_leader_trading_rules.md`에 명세 추가

## 절대 깨지면 안 되는 규칙

- 체결통보(H0STCNI0/9) 구독 제거 금지 — 미구독 시 포지션 등록 불가 → 손절 불가
- uvicorn 단일 워커 필수 (`--workers` 금지)
- 매수 신호는 반드시 "돌파 순간" 감지 (이전 틱 < 기준가 AND 현재 틱 ≥ 기준가)
- 익일 청산은 scheduler에서 시가 수신 후 30s 안정화하여 처리 (`_next_day_clear_pending` 전략 가드 + `_pending_next_day_clear` scheduler 보류 set) — on_tick 즉시 청산 금지
- 익일 청산 갭률은 반드시 `ticker_prices[ticker]["open_price"]`(WebSocket 시가) — `high_since_buy` 폴백 금지 (전일 고가 혼입 → 갭률 0% 즉시 청산 결함). 시가 미수신이면 `_pending_next_day_clear`로 보류 후 09:00 KRX 시장가
- NXT 프리/애프터 매도 거부(`is_market_closed_rejection`) 시 `execute_sell`이 `state.positions`·DB `positions`·`_selling` 보존 — 좀비 포지션(KIS 보유 / 시스템 미보유) 차단 + NXT 시간대 거부면 `stock_master.upsert_one(ticker, nxt_tradable=False)` 사후 보강 → 다음 사이클부터 자동 KRX 다운그레이드
- 매수 시장가 거부(`is_market_order_disallowed`) 시 `execute_buy`가 `step_up(current_price, 5)` 지정가 1회 폴백 — 매핑 동기 등록 + 체결통보 race 가드는 시장가 경로와 동일 규약. 폴백 실패 시 `block_low_funds(ticker, 900s)` cooldown. 좀비 pending_buys 차단
- 매도 시장가 거부(`is_market_order_disallowed`) + `order_division==MARKET` (Phase C, 2026-05-11) 시 `execute_sell`이 `step_down(current_price, 5)` 지정가 1회 폴백 — 매핑 동기 등록 + 체결통보 race 가드는 매수 폴백과 동일. 폴백 실패 시 cooldown 등록 안 함, positions 메모리/DB **보존** (청산 의무 — 다음 사이클 자연 재트리거). 지정가 매도는 폴백 안 함 (이미 지정가). 키워드 `시장가호가불가` 포함 (APBK1943 2026-05-11 계양전기 매도 ×3 실패)
- 주문번호 매핑(`_order_qty/_order_strategy/_order_ticker/_pending_buy_orders`) 등록은 **`place_order` 응답 직후 동기 영역에서**, `await insert_trade` 진입 *전*
- 체결통보 선행 race 가드(`_completed_orders` + UPDATE 0건 보정 INSERT) 매수·매도 양쪽 모두 필수
- `_reset_daily_state()` / 체결통보 실패 시 `pending_buys`·`_selling` 정리 / 매도 재시도 로직 / `BUYABLE_CACHE_TTL=60s` / `BUY_BLOCK_DURATION=900s` / `LOW_FUNDS_COOLDOWN=900s` ↔ sync 주기(15분) 정합성 — 변경 시 잔고 sync 종료 시 `unblock_buy()` + `clear_low_funds()` 일괄 해제 동작 보존
- `Position`에 `strategy_id` 필수 (체결통보 → 올바른 전략 라우팅)
- `position_ratio`는 **전략 할당 자금 기준** (순자산 × 전략비중 × position_ratio)
- TR_ID는 `settings.get_tr_id()` 사용
- **`_confirm_breakout_open_prices` 보드 경계 정각 호출은 `board=...` 명시 의무 (2026-05-15, 결함 A)** — `SessionTracker._session_loop` 30초 주기 race 로 자동 결정 분기가 잘못된 보드로 폴백되는 결함 차단. (a) 08:00 PRE_NXT 진입 → `board="pre_nxt"` 명시. (b) 09:00:05 KRX MAIN 진입 → `board="main"` 명시. (c) 15:30 POST_NXT 진입 → `board="post_nxt"` 명시 (2026-05-12 M 기적용). 자동 결정 허용은 중간 부팅 / `now > TIME_KRX_OPEN_CONFIRM` 스캔 시작 직전 재확정 등 시점 가변 호출에 한정. 2026-05-14, 5/15 운영 사고 — 자동 결정 분기가 09:00 시점 SessionTracker 미반영(pre_nxt만 active) 으로 `board="pre_nxt"` 폴백 → `_targets[t]["boards"]["main"]` 영영 비어 KRX 메인 시간대 VB/LTV 매수 신호 0건. 회귀 가드: `tests/integration/test_post_nxt_open_price_confirm.py` Case C/D
- **VB `DEFAULT_TRADABLE_BOARDS`에 POST_NXT 추가 금지 (2026-05-15, 결함 D)** — VB 는 당일 15:20 일괄매도 정책(OVERNIGHT 거부). 기본값은 `("pre_nxt", "main")` 만. `_force_clear_main_only` 가 `MarketBoard.POST_NXT in allowed` 분기로 청산을 보류하는데, 19:50 시점엔 `buy_disabled=True` + AI자문만 호출되고 **강제 청산 코드 자체가 없음** → POST_NXT 활성 시 OVERNIGHT 자연 보유 결함. 2026-05-13~5/15 005930 멀티데이 보유 후 -3.17% 손절 사고. DB `strategy_config.params.tradable_boards` 도 함께 갱신해야 즉시 반영. 회귀 가드: `tests/unit/engine/test_vb_force_clear_at_15_20.py` 3 케이스
- **VB 익일 청산 안전망 — `_execute_next_day_clear` 대상 포함 (2026-05-15, 결함 D 잔여 fix)** — VB 정책은 당일 15:20 일괄 청산이지만 그게 누락되는 비상 상황(POST_NXT 설정 오류, 시세 미수신, 시장가 거부, 프로세스 재시작 race) 회복을 위해 안전망으로 익일 청산 대상에 추가. VB `__init__` 에 `_next_day_clear_pending=False` 초기화 (scheduler 의 30s 시가 안정화 중 on_tick race 차단). VB `check_exit_signal` 익일 청산 분기: STOP_LOSS 우선 → `is_next_day AND not _next_day_clear_pending` → NEXT_DAY_CLEAR. 회귀 가드: `tests/unit/engine/test_vb_next_day_clear_safety_net.py` 5 케이스
- **donchian_swing 일중 시세 REST 폴링 (`_swing_rest_poll_loop`) 제거 금지 (2026-05-15, 결함 B)** — 09:30~15:20 KRX 메인 시간대 60s 주기로 `_scanned_tickers ∪ positions ∪ pending_buys` 합집합 KIS `fetch_stock_detail` 폴링 → `scanner.ticker_prices` 갱신 + `ticker_last_tick` touch + `ticker_names` 보강. 보유 종목 한정 `RiskManager.on_tick` 호출 → 기존 트레일링/하드 -7% 손절 평가 재사용 (별도 청산 경로 신설 금지). WebSocket stale(2026-05-15 ratio 11~45%) 시에도 멀티데이 보유의 손절 평가가 끊기지 않도록 보강. 매수 평가는 `_swing_buy_poll_loop`(09:05~09:30) 전용 — 본 loop 는 시세 갱신 + 보유 평가만 책임. `risk.py:on_tick` 의 donchian_swing 매수 skip 가드 보존. WS 우선순위 큐(E1)와 무관 (REST 경로 — WS 슬롯 사용 안 함). 회귀 가드: `tests/unit/engine/test_swing_rest_poll.py` 5 케이스
