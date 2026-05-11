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
recommendation_engine.py(19:50 AI자문) / log_analysis_engine.py(20:10 일일 로그 분석)
```

## strategy_base.py

- `StrategyBase` 추상 메서드: `prepare`, `check_buy_signal`, `check_exit_signal`, `calc_buy_quantity`
- `Signal`: NONE / BUY / STOP_LOSS / NEXT_DAY_CLEAR / TRAILING_STOP / FORCE_CLEAR
- `Position`: ticker, buy_price, quantity, order_no, strategy_id, buy_date, is_next_day(프로퍼티)
- `StrategyState`: positions, pending_buys, total_investment, daily_realized_pnl, **cached_buyable_qty/at**, **buy_blocked_until**, **low_funds_tickers**, **signal_count_today / order_attempt_today / fill_count_today** + 헬퍼(`is_buy_blocked / block_buy / unblock_buy / is_buyable_cache_fresh / is_low_funds_blocked / block_low_funds / clear_low_funds`)
  - 일일 퍼널 카운터 3종은 `_reset_daily_state()`에서 0 초기화 → `metrics.strategy_funnel`로 노출

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
| `volatility_breakout` | 보드별 시가 + (전일Range × 보드별 K) 돌파. `_targets[ticker].boards[board]`에 보드별 분리 저장. `_open_confirmed[ticker]` / `_prev_price[ticker]`도 `{board: ...}` dict | -3% / 15:20 KRX 메인 청산 (POST_NXT 활성 전략은 19:50까지 보유) | PRE_NXT+MAIN+POST_NXT / `k_value_krx_main` `k_value_nxt_pre` `k_value_nxt_post` |
| `long_tail_volatility` | VB 방식 조기 진입 + 전일대비 `min_prdy_rate%`↑. `_limit_up_reached` set으로 모드 관리 | 당일 모드 -3% / 상한가 모드 -5% + 익일 갭/트레일링. 15:20은 상한가 미도달만 청산. `_next_day_clear_pending` 가드 (momentum과 동일) | PRE_NXT+MAIN+POST_NXT |
| `donchian_swing` | 코스피200+코스닥150 고정 유니버스 → 시총 컷 → 60일 일봉 → 20일 신고가 + 60일 EMA 우상향 + 거래대금 1.5×. **prepare 시 candles[0]==오늘이면 candles[1]을 전일로** (장중 재실행 시 부분봉 혼입 차단). 09:05~09:30 매수, 갭 +3%↑ 스킵, 1회만 | ATR(14)×2 Chandelier 트레일링 + -7% 하드. **시간·15:20 청산 없음** — 멀티데이 보유 (DB positions 영속화) | MAIN |

공통:
- `prepare()` 단계별 통과 카운트는 `_scan_stats`에 누적 → `get_scan_stats()` → `strategies.<id>.scan_stats`로 프론트 ScanMonitor 깔때기
- VB/LTV `_scan_universe`: 거래량순위 API(`FHPST01710000`) 응답 1건으로 후보 + 시총·전일거래대금 산출(`prdy_vol × (stck_prpr - prdy_vrss)`로 시간 의존 제거)
- VB/LTV/donchian 모두 `prev_idx` 분기 동일: `candles[0].stck_bsop_date == 오늘`이면 candles[1]을 전일로 사용
- 0종목 확정 시 `ERROR` 로그 + `system_logs` 기록

## risk.py

`on_tick()`: ticker_prices 갱신 1회 → `registry.enabled()` 순회 → 전략별 exit/buy 신호.

매수 신호 평가 *전* 가드:
- **보드 가드**: `session_tracker.is_tradable(strategy_id, params)` — 비활성 보드는 신호 평가 자체 skip
- **자금 사전 가드**: `state.is_low_funds_blocked(ticker)` 또는 `current_price > state.total_investment`(1주 매수 자금 미달)이면 skip — OrderEngine 진입 후 cooldown 등록 사후처리에서 매 틱 발생하던 "매수 수량 0 → 900s cooldown" 노이즈 제거
- **중복 가드**: `registry.is_ticker_blocked_for_buy()`
- BUY 신호 발생 시 `state.signal_count_today += 1` (퍼널 카운터)

## order_engine.py

매수/매도 실행 + 체결통보 처리 + DB positions 영속화.

매수 (`execute_buy`):
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

체결통보 race 가드:
- 주문번호 매핑(`_order_qty / _order_strategy / _order_ticker / _pending_buy_orders`)은 **`place_order` 응답 직후 동기 영역에서 등록** (`await insert_trade` 진입 *전*) — 시장가 즉시체결 시 체결통보가 await 도중 도착해도 올바른 strategy로 라우팅. 누락 시 기본값 "momentum"으로 잘못 INSERT됨
- `_completed_orders` set + `update_trade_status` 영향 row 0건 보정 INSERT — 체결통보가 REST 응답보다 먼저 도착해도 trade_history 단일 COMPLETED row 보장. `execute_buy/sell`은 응답 후 set 체크해 PENDING INSERT 생략

거래소 라우팅 (`exchange` 파라미터):
- 모든 `place_order` / `cancel_order` 호출에 `_strategy_exchange(strategy_id)` 로 조회한 전략 `exchange` 전달 (미설정 시 KRX)
- 적용: `execute_buy` / `execute_sell` / `_schedule_cancel` / `_schedule_cancel_and_reorder` / `cancel_remaining`
- 모멘텀 익일 청산이 SOR로 라우팅되면 KIS가 NXT 프리 시간(08:00~09:00)에 NXT로 자동 분배 → KRX 메인 시작 전 청산 가능

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
| `TIME_BOOT` | 07:50 | `_boot()` — DB positions 우선 복구 → KIS 잔고 교차 검증 → 미체결 주문 복구 |
| `TIME_PRESUBSCRIBE` | 07:55 | `_collect_presubscribe_tickers()` — VB/LTV/donchian + 모든 전략 보유 합집합 사전 구독 |
| `TIME_PRE_NXT_OPEN` | 08:00 | 익일 청산 task(`_execute_next_day_clear`, `NEXT_DAY_STABILIZE_SECS=30s`) + `_confirm_breakout_open_prices(board="pre_nxt")`. **시가 수신 → 갭률 트레일링 또는 NXT 지정가(`step_down(open,1)`, `EXCG_ID_DVSN_CD=NXT`, `ORD_DVSN=00`). 시가 미수신 → `_pending_next_day_clear` set 등록 후 보류** (NXT 거래불가 종목 추론) |
| `TIME_KRX_OPEN_CONFIRM` | 09:00:05 | `_confirm_breakout_open_prices(board="main")` — VB/LTV가 KRX 09:00 시가로 보드별 별도 target_price 계산. 직후 `_drain_pending_next_day_clear()` — 08:00 보류 종목을 KRX 시장가로 일괄 청산 |
| `TIME_SCAN_START` | 09:30 | 모멘텀 `scan_stocks()` + 통합 구독 |
| `TIME_KRX_MAIN_BUY_STOP` | 15:20 | `_force_clear_main_only` — POST_NXT 미활성 전략만 청산, 활성 전략은 19:50까지 보유 |
| `TIME_KRX_MAIN_CLOSE` | 15:30 | KRX 메인 마감 → NXT 애프터 전환, 구독 유지 |
| `TIME_NXT_POST_BUY_STOP` / `TIME_RECOMMENDATION` | 19:50 | `buy_disabled = True` + `generate_recommendations()` |
| `TIME_NXT_POST_CLOSE` | 20:00 | `unsubscribe_all()` |
| `TIME_SETTLEMENT` | 20:10 | `_settle()` → `generate_daily_log_report()` → `_reset_daily_state()` 순서. **퍼널 카운터 초기화는 분석 *후*** (분석이 0을 수집하지 않도록 분리) |

기타:
- WebSocket 연결 직후 **체결통보 자동 구독**(실전 H0STCNI0+HTS ID / 모의 H0STCNI9+계좌번호) + 통합 장운영정보 `H0UNMKO0`/`005930` (실전 한정, 모의 미지원)
- `_load_strategy_config()`: DB `strategy_config`에서 비중/`tradable_boards`/`exchange`/`k_value_*` 복구
- `run_daily()`: 주말+공휴일 건너뜀(KIS `chk-holiday`), 매일 시작 전 DB auto_start 재확인
- 중간 시각 시작: 현재 시각 이후 스케줄부터 실행
- `_scan_loop()`: 09:30 이후 `SCAN_INTERVAL=300s` 주기, **VB+LTV+donchian + 모든 전략 보유** 합집합 재구독 (이전엔 VB만 재구독해 swing/LTV/보유 시세 끊겨 손절 누락)
- `_sync_positions_from_balance()`: 15분 주기. **strategy 매핑은 trade_history 직전 BUY 행에서 상속** (이전 momentum 하드코딩 결함 차단). 종료 시 `unblock_buy()` + `clear_low_funds()` 일괄 해제
- `_execute_next_day_clear()`: 다음 영업일 NXT 프리 첫 거래 시가 수신 후 30s 안정화 → 갭률 트레일링 또는 NXT 지정가(`step_down(open,1)`) 매도. **시가 미수신이면 `_pending_next_day_clear` set에 `(ticker, strategy_id)` 등록 후 즉시 청산 보류** — `high_since_buy` 폴백 + 갭률 0% 즉시 청산 경로는 전일 고가 혼입 결함으로 제거. `_resolve_open_price()` 폴백은 NXT 거래가능 종목 추론용으로만 유지
- `_drain_pending_next_day_clear()`: `_confirm_breakout_open_prices(board="main")` 직후 호출. `_pending_next_day_clear` 종목을 KRX 시장가(`limit_price=0`)로 일괄 청산 → 보류 set 비움
- `_reset_daily_state()`: 전략별 positions/pending_buys/sold_today + OrderEngine 추적 상태 + scanner 글로벌 dict (ticker_prices/ticker_prev_close/ticker_market_info/ticker_names → STATIC_TICKER_NAMES로 재시드) + `_pending_next_day_clear.clear()` 전체 초기화

## scanner.py

- `scan_stocks()`: 모멘텀 등락률 순위
- `subscribe_filtered_stocks(tickers, extra_tickers)`: 합집합 구독
- `KOSPI_200_TICKERS` / `KOSDAQ_150_TICKERS`: donchian_swing 고정 유니버스
- `STATIC_TICKER_NAMES` / `_parse_static_ticker_names()`: 모듈 import 시 자기 파일을 정규식(`"(\d{6})",\s*#\s*(.+)$`)으로 파싱해 인라인 코멘트의 종목명을 dict로 추출. 모듈 로드 시 `ticker_names.update(STATIC)` — KIS `inquire-price`가 빈 종목명 응답해도 시장명으로 떨어지지 않도록 보강
- 공용 데이터: ticker_names, ticker_prices, ticker_prev_close, ticker_market_info

## log_analysis_engine.py — 일일 로그 분석

20:10 정산 직후(`_settle()` 완료, `_phase = "log_analysis"`) `generate_daily_log_report()` 호출. 호출 *후* run loop가 `_reset_daily_state()` 별도 실행 (퍼널 카운터 보존).

당일 KST 00:00~now `system_logs`(레벨/패턴/샘플) + `trade_history`(매수/매도/실현손익/전략별·상태별) → OpenAI → `daily_log_reports` INSERT.

확장 메트릭:
- `api_metrics`: `api/base.py::get_request_metrics()` (5xx/4xx/network/retries + path별 5xx top 5). INSERT 후 `reset_request_metrics()`
- `strategy_funnel`: 전략별 `{signals, orders, fills}` (registry 순회) — VB가 신호만 있고 체결 없는 패턴 등 깔때기 추적
- `trades.by_ticker_pnl` (SELL PnL 절대값 top 5) / `trades.by_hour_pnl` (KST hour별)

출력 스키마: `{summary, findings: [{category, severity, title, detail, suggestion}]}`. `(target_date)` UNIQUE → 동일 영업일 재실행 시 None. OpenAI 타임아웃 60s, 실패 시 메트릭만 보존 INSERT.

## recommendation_engine.py / recommendation_metrics.py — 19:50 AI자문

- 전략별 metrics(승률/평균손익/손절률/누적수익률) → OpenAI → `parameter_recommendations` INSERT (status: pending)
- `(target_date, strategy_id)` UNIQUE
- `/api/recommendations/{id}/apply`: 사용자 키 선택 적용 → `strategy_config.params` 갱신 + status applied/partial
- `expire_pending_before(target_date)`: 이전 영업일 pending 자동 만료

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
- NXT 프리/애프터 매도 거부(`is_market_closed_rejection`) 시 `execute_sell`이 `state.positions`·DB `positions`·`_selling` 보존 — 좀비 포지션(KIS 보유 / 시스템 미보유) 차단
- 매수 시장가 거부(`is_market_order_disallowed`) 시 `execute_buy`가 `step_up(current_price, 5)` 지정가 1회 폴백 — 매핑 동기 등록 + 체결통보 race 가드는 시장가 경로와 동일 규약. 폴백 실패 시 `block_low_funds(ticker, 900s)` cooldown. 좀비 pending_buys 차단
- 주문번호 매핑(`_order_qty/_order_strategy/_order_ticker/_pending_buy_orders`) 등록은 **`place_order` 응답 직후 동기 영역에서**, `await insert_trade` 진입 *전*
- 체결통보 선행 race 가드(`_completed_orders` + UPDATE 0건 보정 INSERT) 매수·매도 양쪽 모두 필수
- `_reset_daily_state()` / 체결통보 실패 시 `pending_buys`·`_selling` 정리 / 매도 재시도 로직 / `BUYABLE_CACHE_TTL=60s` / `BUY_BLOCK_DURATION=900s` / `LOW_FUNDS_COOLDOWN=900s` ↔ sync 주기(15분) 정합성 — 변경 시 잔고 sync 종료 시 `unblock_buy()` + `clear_low_funds()` 일괄 해제 동작 보존
- `Position`에 `strategy_id` 필수 (체결통보 → 올바른 전략 라우팅)
- `position_ratio`는 **전략 할당 자금 기준** (순자산 × 전략비중 × position_ratio)
- TR_ID는 `settings.get_tr_id()` 사용
