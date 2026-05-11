# 시스템 설계 문서

KIS OpenAPI 기반 주식 자동매매시스템 설계 문서.

---

## 1. 전체 아키텍처

```
+------------------+        +-------------------+        +-------------------+
|   React Frontend |  REST  |  FastAPI Backend   | KIS API|  한국투자증권      |
|   (Vite + Nginx) | <----> |  (Uvicorn)         | <----> |  OpenAPI Server   |
|   Port 80        |  /api  |  Port 8000         |        |                   |
+------------------+        +--------+----------+        +--------+----------+
                                     |                             |
                                     |                    +--------+----------+
                                     |                    |  KIS WebSocket    |
                                     |                    |  ops.koreainvest  |
                                     |                    |  :21000 (실전)    |
                                     |                    |  :31000 (모의)    |
                                     |                    +-------------------+
                                     |                             ^
                                     |                             |
                                     v                             |
                              +------+------+              실시간 시세 +
                              |  Supabase   |              체결통보
                              |  PostgreSQL |
                              +-------------+
```

### 컨테이너 구성 (Docker Compose)

```
docker network: auto_stock_default
+------------------------------------------+
|                                          |
|  +----------------+  +----------------+  |
|  |   backend      |  |   frontend     |  |
|  |   python:3.12  |  |   nginx:alpine |  |
|  |   Port 8000    |  |   Port 80      |  |
|  |   TZ=KST       |  |                |  |
|  |   단일 워커     |  |  /api → backend |  |
|  +----------------+  +----------------+  |
|                                          |
+------------------------------------------+
           |
     volumes: ./logs
     env_file: .env
```

---

## 2. 백엔드 모듈 구조

```
src/
├── main.py              # FastAPI 앱, 로깅(KST), lifespan(토큰/자동시작)
├── config.py            # Settings (pydantic-settings, .env → KIS인증 자동매핑)
│
├── auth/                # KIS 인증
│   ├── token.py         # TokenManager (발급/갱신/폐기/접속키)
│   └── hashkey.py       # POST body 해시
│
├── api/                 # KIS REST API 래퍼
│   ├── base.py          # kis_get/kis_post (Rate Limit, 재시도, 토큰갱신)
│   ├── order.py         # place_order, cancel_order
│   ├── balance.py       # get_balance, get_buyable, get_daily_orders
│   └── condition.py     # fetch_rising_stocks, fetch_stock_detail, fetch_daily_candles,
│                        # inquire_stock_basics(CTPF1002R — NXT 거래가능 사전 판별)
│
├── realtime/            # KIS WebSocket
│   ├── websocket.py     # KisWebSocket (연결/구독/재연결/Heartbeat)
│   └── handler.py       # 메시지 파싱 (시세 + 체결통보 AES 복호화)
│
├── engine/              # 매매 엔진 코어
│   ├── strategy_base.py     # StrategyBase(ABC), Signal, Position, StrategyState
│   ├── strategy_registry.py # StrategyRegistry (등록/비중/자금분배/중복방지)
│   ├── session.py           # MarketBoard enum + SessionTracker (KRX/NXT 보드 추적, tradable_boards)
│   ├── strategies/
│   │   ├── momentum.py              # 상한가 모멘텀 (KRX_OPEN+MAIN)
│   │   ├── volatility_breakout.py   # 변동성 돌파 (보드별 K값 분리)
│   │   ├── long_tail_volatility.py  # 롱테일 변동성 돌파 (VB+상한가 합성)
│   │   └── donchian_swing.py        # 20일 신고가 스윙 (MAIN만, 멀티데이)
│   ├── risk.py              # RiskManager (on_tick → 보드 가드 → 전략별 신호 순회)
│   ├── order_engine.py      # OrderEngine (주문/체결/포지션 관리)
│   ├── scheduler.py         # TradingScheduler (KRX/NXT 통합 운영 08:00~20:00)
│   └── scanner.py           # 종목 스캔 + 공용 시세 캐시 (TICK_TR_ID = H0UNCNT0)
│
├── db/                  # Supabase CRUD
│   ├── supabase.py          # 클라이언트 초기화
│   ├── trade_history.py     # 거래 내역
│   ├── positions.py         # 포지션 영속화
│   ├── daily_performance.py # 일일 실적
│   ├── strategy_config.py   # 전략 설정 영속화
│   ├── stock_master.py      # CTPF1002R 캐시 (NXT 거래가능 사전 판별, 24h TTL)
│   └── system_logs.py       # 시스템 로그
│
├── routes/              # FastAPI 라우트
│   ├── trading.py       # 시작/정지/상태/수동매도
│   ├── balance.py       # 잔고 조회
│   ├── history.py       # 거래 내역
│   ├── performance.py   # 실적 차트
│   ├── strategies.py    # 전략 설정/비중/자동시작
│   └── logs.py          # 로그 조회
│
└── models/              # Pydantic 데이터 모델
    ├── order.py         # OrderSide, OrderResult
    ├── balance.py       # StockHolding, AccountSummary
    ├── trade.py         # TradeRecord, TradeStatus
    ├── stock.py         # StockBasics (CTPF1002R 응답 + nxt_tradable 파생)
    └── response.py      # ApiResponse 공통 래퍼
```

---

## 3. 모듈 의존관계

```
                         config.py (Settings 싱글턴)
                              ^
                   모든 모듈에서 import
                              |
          +-------------------+-------------------+
          |                   |                   |
     auth/token.py      api/base.py       db/supabase.py
          ^              ^       ^              ^
          |              |       |              |
    +-----+-----+   +---+---+   |         +----+----+
    | websocket | | order  |   |         | trade_  |
    | .py       | | .py    |   |         | history |
    +-----------+ | balance|   |         | positions|
                  | .py    |   |         | daily_  |
                  | condi- |   |         | perf    |
                  | tion.py|   |         | strategy|
                  +---+----+   |         | _config |
                      |        |         +---------+
                      v        v              ^
              +-------+--------+----+         |
              |    engine/          |         |
              |  +-----------+      |         |
              |  | scheduler |------+---------+
              |  +-----+-----+      |
              |        |            |
              |  +-----v-----+     |
              |  | risk.py   |     |
              |  +-----+-----+     |
              |        |           |
              |  +-----v--------+ |
              |  | order_engine +--+
              |  +-----+--------+
              |        |
              |  +-----v-----+
              |  | strategies |
              |  | momentum   |
              |  | volatility |
              |  +------------+
              +----------------+
                      ^
                      |
               routes/*.py ──→ main.py (FastAPI)
```

---

## 4. 매매 엔진 내부 구조

```
TradingScheduler (scheduler.py)
│
├── StrategyRegistry
│   ├── MomentumStrategy             (tradable_boards: krx_open + main)
│   │   ├── StrategyConfig (id, name, weight, params{tradable_boards, exchange, ...})
│   │   └── StrategyState (positions, pending_buys, sold_today, pnl,
│   │                       cached_buyable_*, buy_blocked_until, low_funds_tickers)
│   ├── VolatilityBreakoutStrategy   (tradable_boards: pre_nxt + main + post_nxt)
│   │   ├── StrategyConfig (k_value_krx_main / k_value_nxt_pre / k_value_nxt_post)
│   │   ├── StrategyState
│   │   └── _targets (K, prev_range, target_offset_base,
│   │                  boards: {board: {open_price, target_price, target_offset}})
│   ├── LongTailVolatilityStrategy   (tradable_boards: pre_nxt + main + post_nxt)
│   │   └── + _limit_up_reached set (상한가 모드 전환 종목)
│   └── DonchianSwingStrategy        (tradable_boards: main)
│       └── _candidates / _bought_today / _scan_stats
│
├── SessionTracker (session.py — Phase 3 신설)
│   ├── _active: frozenset[MarketBoard]
│   ├── tick(now) → 시각 기반 보드 매핑 + 진입/종료 콜백 발화
│   ├── on_h0nxmko0(tr_key, code, payload) → NXT 보드 코드 기록
│   └── is_tradable(strategy_id, params) → 활성 보드 ∩ tradable_boards ≠ ∅
│
├── OrderEngine
│   ├── _order_ticker   {order_no → ticker}     # 체결통보 종목 보정
│   ├── _order_strategy {order_no → strategy_id} # 전략 라우팅
│   ├── _pending_buy_orders {order_no → info}    # 미체결 매수 추적
│   ├── _selling        set[ticker]              # 매도 중복 차단
│   ├── _filled_qty     {order_no → 누적체결수량}
│   └── _completed_orders set[order_no]          # 체결통보 선행 race 가드
│
└── RiskManager
    └── on_tick() → ticker_prices 갱신 → registry.enabled() 순회
        ├─ check_exit_signal()
        ├─ session_tracker.is_tradable(strategy)  ← 보드 가드 (Phase 8)
        ├─ registry.is_ticker_blocked_for_buy()
        └─ check_buy_signal() → execute_buy()
```

---

## 5. 일일 매매 스케줄 시퀀스 — KRX/NXT 통합 (08:00~20:00)

```
시각     Scheduler          WebSocket         OrderEngine       KIS API
─────────────────────────────────────────────────────────────────────────
07:45  run_daily() 기상       (TIME_AUTO_START)
       │
07:50  _boot()                 (TIME_BOOT)
       ├─ get_token() ──────────────────────────────────────→ POST /oauth2/tokenP
       ├─ _load_strategy_config() ←── DB strategy_config
       │   (tradable_boards / k_value_* / exchange 포함)
       ├─ get_balance() ────────────────────────────────────→ GET inquire-balance
       ├─ allocate_funds()
       ├─ strategy.prepare() ───────────────────────────────→ GET daily-price (일봉)
       │   └─ ticker_prev_close 사전 등록 (전일 종가)
       ├─ DB positions 복구 ←── DB positions
       └─ KIS 잔고 교차검증
       │
07:55  connect() ──────────→ WebSocket 연결        (TIME_PRESUBSCRIBE)
       │  ├─ subscribe(H0STCNI0/9, 체결통보)
       │  └─ subscribe(H0NXMKO0, "")  (실전 한정 — NXT 장운영정보)
       │  + register_board_handler(SessionTracker.on_h0nxmko0)
       │  + _session_loop() task — 30초 주기 SessionTracker.tick()
       │  _collect_presubscribe_tickers() →
       │     subscribe(H0UNCNT0, 종목들)  (KRX+NXT 통합 시세)
       │  유니버스 비어있으면 prepare() 재실행 (KIS API 일시장애 대비)
       │                         │
08:00  PRE_NXT 보드 진입       (TIME_PRE_NXT_OPEN)
       │  asyncio.create_task(_execute_next_day_clear())
       │     ← 비차단 (NEXT_DAY_STABILIZE_SECS=30s 안정화)
       │     ← 다음 영업일 NXT 프리 시가에서 청산 (Q2=B)
       │  + _confirm_breakout_open_prices(board="pre_nxt") — 0.5초/5초 폴링
       │  _phase = "pre_nxt_trading"
       │  VB + LTV PRE_NXT 매매 시작 (k_value_nxt_pre 적용)
       │                         │
09:00:05 KRX 메인 시가 확정    (TIME_KRX_OPEN_CONFIRM)
       │  _confirm_breakout_open_prices(board="main")  ← 보드별 별도 시가
       │  _phase = "main_trading"
       │  VB + LTV MAIN 매매 진입 (k_value_krx_main 적용)
       │                         │
09:30  scan_stocks() ───────────────────────────────────────→ GET fluctuation-rank
       │  subscribe_filtered_stocks()                        GET inquire-price
       │  _phase = "trading"  (모멘텀 매수 감시 시작)
       │  ├─ _scan_loop() 시작 (5분 주기)
       │                         │
       │         ←───────────────┤ H0UNCNT0 실시간 체결가 (KRX+NXT 통합)
       │                         │
       │  RiskManager.on_tick()  │
       │  ├─ session_tracker.is_tradable(strategy)  ← Phase 8 보드 가드
       │  ├─ check_exit_signal() │
       │  │  └─ execute_sell() ──┼──────────────────────────→ POST order (매도)
       │  │                                              EXCG_ID_DVSN_CD = exchange
       │  └─ check_buy_signal()  │
       │     ├─ _resolve_active_board()  ← 활성 보드 결정 (main 우선)
       │     └─ execute_buy() ───┼──────────────────────────→ POST order (매수)
       │                         │
       │         ←───────────────┤ H0STCNI0 체결통보 (KRX/NXT/SOR 통합)
       │                         │
       │  handle_execution_notice()
       │  ├─ _order_ticker[order_no] → 정확한 ticker
       │  ├─ _handle_buy_fill()
       │  │  ├─ Position 등록 (메모리)
       │  │  └─ save_position() → DB
       │  └─ _handle_sell_fill()
       │     ├─ Position 제거 (메모리)
       │     ├─ delete_position() → DB
       │     └─ sold_today.add(ticker)
       │
15:20  KRX 메인 신규 매수 중단 + 강제 청산  (TIME_KRX_MAIN_BUY_STOP)
       │  _force_clear_main_only()
       │     ← tradable_boards에 POST_NXT가 있는 전략 종목은 보유 유지
       │  └─ execute_sell(FORCE_CLEAR) ─────────────────────→ POST order
       │
15:30  KRX 메인 마감 → NXT 애프터 전환       (TIME_KRX_MAIN_CLOSE)
       │  _phase = "post_nxt_trading"  (구독 유지, POST_NXT 종목 시세 필요)
       │  VB + LTV POST_NXT 매매 계속 (k_value_nxt_post 적용)
       │
19:50  NXT 애프터 신규 매수 중단              (TIME_NXT_POST_BUY_STOP)
       │  buy_disabled = True (모든 활성 전략)
       │  generate_recommendations()  (전략수정 AI자문)
       │  ├─ collect_metrics() ──────────────────→ DB trade_history 집계
       │  ├─ OpenAI Chat Completion ─────────────→ 외부 API
       │  └─ insert_recommendation() → DB parameter_recommendations (status: pending)
       │
20:00  NXT 애프터 종료, unsubscribe_all() ──→ WebSocket 구독 해제
       │                                       (TIME_NXT_POST_CLOSE)
       │
20:10  _settle()                              (TIME_SETTLEMENT)
       │  ├─ get_balance() ─────────────────────────────────→ GET inquire-balance
       │  ├─ upsert_daily_performance() → DB (전략별 + total)
       │  ├─ generate_daily_log_report() → DB daily_log_reports (OpenAI)
       │  └─ disconnect() ─────→ WebSocket 종료
       │
       └── 익일 07:45까지 대기 (주말 자동 건너뜀)
```

---

## 6. 체결통보 처리 시퀀스

```
KIS WebSocket                handler.py              OrderEngine
─────────────────────────────────────────────────────────────────
H0STCNI0 수신 ──────→ dispatch_message()
(암호화된 payload)     │
                       ├─ AES-256-CBC 복호화
                       │  (iv/key: 구독 시 수신)
                       │
                       ├─ fields = payload.split("^")
                       │  order_no = fields[2]
                       │  side = fields[4]  (01:매도, 02:매수)
                       │  exec_type = fields[13]
                       │
                       ├─ exec_type != "2" → 무시 (접수통보)
                       │
                       └─ _on_execution() ──────→ handle_execution_notice()
                                                  │
                                                  ├─ ticker = _order_ticker[order_no]
                                                  │  (체결통보 ticker 필드 무시)
                                                  │
                                                  ├─ BUY → _handle_buy_fill()
                                                  │  ├─ Position 생성/갱신
                                                  │  ├─ pending_buys 제거
                                                  │  ├─ DB positions 저장
                                                  │  └─ trade_history COMPLETED
                                                  │
                                                  └─ SELL → _handle_sell_fill()
                                                     ├─ 손익 계산 (체결가 - 매수가) × 수량
                                                     ├─ Position 삭제
                                                     ├─ DB positions 삭제
                                                     ├─ sold_today 등록
                                                     ├─ _selling 해제
                                                     └─ trade_history COMPLETED
                                                        (UPDATE 0건이면 → COMPLETED 직접 INSERT
                                                         + _completed_orders.add(order_no))
```

### 체결통보 선행 race 가드

시장가 즉시체결 시 `H0STCNI0` 체결통보가 KIS REST 응답보다 먼저 도착하는 경우가 있다.
이 시점에는 `_order_ticker[order_no]` 매핑도, `trade_history`의 PENDING row도 아직 없다.

```
정상 흐름                            race 흐름
────────────                         ──────────
place_order() 응답 도착              체결통보 먼저 도착
  ↓                                    ↓
insert_trade(PENDING) + 매핑 등록      payload ticker로 우회 처리
  ↓                                    ↓
체결통보 도착                          update_trade_status → 0건 (PENDING 없음)
  ↓                                    ↓
update_trade_status → 1건 (COMPLETED) COMPLETED 직접 INSERT + _completed_orders.add
                                       ↓
                                     place_order() 응답 늦게 도착
                                       ↓
                                     execute_*가 _completed_orders 체크 → PENDING INSERT 생략
                                       ↓
                                     _completed_orders.discard(order_no)
```

→ 양쪽 흐름 모두 `trade_history`에 단일 COMPLETED row만 남는다.

---

## 7. 포지션 복구 시퀀스 (서버 재기동)

```
_boot()
│
├─ 1차: DB positions 테이블 로드
│  │
│  ├─ KIS 잔고에 있는 종목만 복구
│  │  └─ Position(buy_price, strategy_id, buy_date) 정확한 값
│  │
│  └─ KIS 잔고에 없는 DB 레코드 삭제
│     (이미 매도 완료된 종목)
│
├─ 2차: KIS 잔고에 있지만 DB에 없는 종목 보완
│  │
│  ├─ trade_history에서 전략(strategy) 조회
│  ├─ KIS 주문체결내역에서 매수일/매수가 조회
│  ├─ Position 등록 (메모리 + DB)
│  └─ 로그: "KIS 잔고 보완 복구"
│
└─ trade_history PENDING → COMPLETED 일괄 갱신
```

---

## 8. 전략 매수 신호 흐름

### 8.1 상한가 모멘텀

```
on_tick(ticker, current_price)
│
├─ prev_rate = _prev_prdy_rate[ticker]   # 이전 틱 등락률
├─ curr_rate = (current_price - prev_close) / prev_close × 100
│
├─ 조건: prev_rate < 29% AND curr_rate >= 29% AND curr_rate < 30%
│         ↑ 돌파 순간        ↑ 29% 이상         ↑ 상한가 제외
│
├─ 추가 체크:
│  ├─ has_position? → 건너뜀
│  ├─ is_buy_pending? → 건너뜀
│  ├─ is_sold_today? → 건너뜀 (당일 재매수 차단)
│  ├─ is_max_positions? → 건너뜀 (positions + pending_buys 합산)
│  └─ registry.is_ticker_held_by_any? → 건너뜀 (타 전략 중복)
│
└─ Signal.BUY → execute_buy(시장가)
```

### 8.2 변동성 돌파 (보드별 분리 — Phase 5 Q1=C)

```
prepare() 단계:
│
├─ _scan_universe(): 거래량순위 API(FHPST01710000) 응답 1건으로
│    후보 + 시총·전일 거래대금 산출
│    ├─ 시총   = stck_prpr × lstn_stcn
│    ├─ 거래대금 = prdy_vol × (stck_prpr - prdy_vrss)   ← 영업일 기준, 시간 비의존
│    └─ 0종목 확정 시 ERROR 로그 + system_logs 기록
├─ fetch_daily_candles(): 21일 일봉
├─ K값 = avg(노이즈 비율) = avg(1 - |종가-시가| / (고가-저가))
├─ target_offset_base = 전일 Range × K                  ← 보드별 K 곱 전 기본값
├─ ticker_prev_close[ticker] = candles[0].stck_clpr     (전일 종가 사전 등록)
└─ _targets[ticker] = {target_offset_base, k, prev_range, boards: {}}

보드별 시가 확정 (on_open_price_confirmed(ticker, open_price, board)):
│
├─ k_mult = params[f"k_value_{board}"]   # main / nxt_pre / nxt_post
├─ target_offset = target_offset_base × k_mult
└─ _targets[ticker]["boards"][board] = {open_price, target_price, target_offset}

08:00 NXT 프리 진입:  _confirm_breakout_open_prices(board="pre_nxt")
09:00:05 KRX 메인 시가: _confirm_breakout_open_prices(board="main")  ← 보드별 별도 시가
15:30 NXT 애프터 진입: _confirm_breakout_open_prices(board="post_nxt")  (필요 시)

on_tick(ticker, current_price)
│
├─ session_tracker.is_tradable(strategy)  ← Phase 8 보드 가드 (RiskManager)
├─ board = _resolve_active_board()         ← main 우선 → post_nxt → pre_nxt
├─ prev_price = _prev_price[ticker][board]   (보드별 이전 틱)
│
├─ 조건: prev_price < boards[board].target_price AND current_price >= target_price
│         ↑ 보드별 돌파 순간
│
├─ 동일 체크: position, pending, sold_today, max_positions
│
└─ Signal.BUY → execute_buy(시장가)
```

---

## 9. DB 스키마

```
┌─────────────────────────────────────────────────────┐
│ trade_history                                       │
├─────────────────────────────────────────────────────┤
│ id          UUID PK DEFAULT gen_random_uuid()       │
│ timestamp   TIMESTAMPTZ                             │
│ ticker      VARCHAR(20)                             │
│ ticker_name VARCHAR(50)                             │
│ trade_type  VARCHAR(4)   CHECK (BUY, SELL)          │
│ price       NUMERIC                                 │
│ quantity    INTEGER                                 │
│ profit_loss NUMERIC DEFAULT 0                       │
│ status      VARCHAR(10)  CHECK (PENDING, COMPLETED, │
│                                  PARTIAL, CANCELLED)│
│ strategy    VARCHAR(30)  DEFAULT 'momentum'         │
│ order_no    VARCHAR(20)                             │
├─────────────────────────────────────────────────────┤
│ INDEX: ticker, timestamp                            │
└─────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────┐
│ positions                                           │
├─────────────────────────────────────────────────────┤
│ ticker         VARCHAR(10) PK                       │
│ ticker_name    VARCHAR(50)                          │
│ buy_price      INTEGER                              │
│ quantity       INTEGER                              │
│ order_no       VARCHAR(20)                          │
│ strategy_id    VARCHAR(30)                          │
│ buy_date       DATE                                 │
│ high_since_buy INTEGER                              │
│ updated_at     TIMESTAMPTZ DEFAULT now()            │
└─────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────┐
│ daily_performance                                   │
├─────────────────────────────────────────────────────┤
│ date              DATE        ─┐ 복합 PK            │
│ strategy          VARCHAR(30) ─┘                    │
│ total_asset       NUMERIC                           │
│ daily_profit_rate NUMERIC                           │
└─────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────┐
│ strategy_config                                     │
├─────────────────────────────────────────────────────┤
│ strategy_id VARCHAR(30) PK                          │
│ enabled     BOOLEAN                                 │
│ weight      NUMERIC                                 │
│ params      JSONB                                   │
│ updated_at  TIMESTAMPTZ DEFAULT now()               │
└─────────────────────────────────────────────────────┘

┌──────────────────────────┐  ┌──────────────────────┐
│ system_config            │  │ system_logs          │
├──────────────────────────┤  ├──────────────────────┤
│ key   VARCHAR(50) PK     │  │ id        BIGSERIAL  │
│ value JSONB              │  │ timestamp TIMESTAMPTZ│
│ updated_at TIMESTAMPTZ   │  │ log_level VARCHAR(10)│
└──────────────────────────┘  │ message   TEXT       │
                              └──────────────────────┘

┌─────────────────────────────────────────────────────┐
│ stock_master (migration 015 — Phase G, 2026-05-11)  │
├─────────────────────────────────────────────────────┤
│ ticker       TEXT PK                                │
│ name         TEXT     DEFAULT ''                    │
│ excg_dvsn_cd TEXT     DEFAULT ''                    │
│ nxt_tradable BOOLEAN  NOT NULL                      │
│   (cptt_trad_tr_psbl_yn==Y AND nxt_tr_stop_yn==N)   │
│ krx_halted   BOOLEAN  DEFAULT FALSE                 │
│ admin_item   BOOLEAN  DEFAULT FALSE                 │
│ raw          JSONB    DEFAULT '{}'::jsonb           │
│ refreshed_at TIMESTAMPTZ DEFAULT now()              │
│   (24h 초과 시 stale → CTPF1002R 재조회)            │
├─────────────────────────────────────────────────────┤
│ INDEX: refreshed_at                                 │
└─────────────────────────────────────────────────────┘
```

---

## 10. 프론트엔드 구조

```
frontend/src/
├── App.tsx                 # 라우터 (Dashboard, History, Settings)
│
├── pages/
│   ├── Dashboard.tsx       # 메인 대시보드 (전략 탭 + 컴포넌트 배치)
│   ├── History.tsx         # 거래 내역 페이지
│   └── Settings.tsx        # 전략 비중/파라미터/자동시작 설정
│
├── components/
│   ├── ControlPanel.tsx    # 시작/정지/재기동 버튼 + 환경 배너
│   ├── ScanMonitor.tsx     # 조건검색 현황 + VB 타겟가 테이블
│   ├── OrderMonitor.tsx    # 주문처리 현황 + 보유 포지션
│   ├── BalanceTable.tsx    # 잔고 현황 (실시간 시세 + 수동매도)
│   ├── PerformanceCard.tsx # 운영 실적 카드
│   ├── ProfitChart.tsx     # 일별/월별 수익률 차트
│   ├── TradeHistoryGrid.tsx# 거래 내역 테이블 (KST, 주문번호)
│   ├── LogViewer.tsx       # 실시간 로그 뷰어
│   └── ConfirmModal.tsx    # 확인 모달 (매매/매도 안전장치)
│
├── api/
│   ├── client.ts           # axios 인스턴스 (baseURL: /api)
│   ├── trading.ts          # 매매 제어 + 수동매도 + 전략설정
│   ├── balance.ts          # 잔고 조회
│   ├── history.ts          # 거래 내역
│   └── performance.ts      # 실적 데이터
│
└── types/
    ├── trading.ts          # TradingStatusData, StrategyInfo, TradeRecord
    ├── balance.ts          # Holding, BalanceSummary
    ├── strategy.ts         # STRATEGY_COLORS, getStrategyColor()
    └── common.ts           # ApiResponse<T>
```

### 대시보드 레이아웃

```
┌──────────────────────────────────────────────┐
│  ControlPanel (시작/정지/재기동)               │
├──────────────────────────────────────────────┤
│  전략 탭 [전체] [상한가 모멘텀(N)] [변동성 돌파(N)] │
├──────────────────┬───────────────────────────┤
│  ScanMonitor     │  OrderMonitor             │
│  - 스캔 요약     │  - 투자가능금액            │
│  - 종목 리스트   │  - 매수 대기              │
│  - VB 타겟가     │  - 보유 포지션            │
│  - 매수 신호     │  - 체결 진행              │
├──────────────────┴───────────────────────────┤
│  BalanceTable                                │
│  - 예수금/총평가금/순자산/총평가손익 카드       │
│  - 잔고 내역 (실시간 시세 + 전략 라벨 + 매도)  │
├──────────────────────────────────────────────┤
│  PerformanceCard (운영일수/수익률)             │
├──────────────────────────────────────────────┤
│  ProfitChart (일별/월별 수익률 차트)           │
├──────────────────────────────────────────────┤
│  LogViewer (실시간 시스템 로그)                │
└──────────────────────────────────────────────┘
```

---

## 11. 핵심 설계 제약사항

| 제약 | 이유 |
|------|------|
| 단일 uvicorn 워커 | 다중 워커 시 스케줄러/WebSocket/포지션 상태 중복 |
| 체결통보 구독 필수 | 미구독 시 포지션 미등록 → 손절 불가 |
| DB positions가 진실의 원천 | 재기동 시 정확한 매수가/전략/매수일 복구 |
| _order_ticker 매핑 | 체결통보의 종목코드 필드가 부정확 (지점코드 혼입) |
| 돌파 순간 감지 | 이전 틱 < 기준 AND 현재 틱 >= 기준 (반복 매수 방지) |
| sold_today | 당일 매도 종목 재매수 차단 |
| 모든 TR_ID → get_tr_id() | 실전/모의 자동 변환 (T→V 접두사) |
| 비중 변경 시 매수금액 하한선 | 보유 종목 매도 전에는 비중 축소 불가 |
| 잔고 API 0수량 필터 | KIS가 매도 완료 종목도 반환하므로 제외 |
| 비주식 상품 필터 | 6자리 숫자 종목코드만 허용 (CMA/펀드 제외) |
| 로컬/EC2 동시 실행 금지 | KIS API 동일 계정 동시 접속 충돌 |

---

## 12. 배포 환경 (AWS EC2)

```
개발자 PC                    GitHub                     AWS EC2 (서울)
───────────                  ──────                     ──────────────
git push ───────────→ Actions trigger
                      ├─ appleboy/ssh-action
                      └──────────────────────────────→ SSH 접속
                                                       ├─ git pull origin main
                                                       ├─ docker compose build
                                                       └─ docker compose up -d
```

### 인프라 구성

| 항목 | 값 |
|------|---|
| 인스턴스 | EC2 t4g.small (2vCPU, 2GB, ARM) |
| 리전 | ap-northeast-2 (서울) |
| OS | Ubuntu 24.04 LTS |
| 스토리지 | 20GB gp3 |
| Elastic IP | 고정 IP 할당 |
| 보안 그룹 | 22(SSH), 80(HTTP), 443(HTTPS) |
| 키페어 | `~/.ssh/auto-stock-key.pem` (ED25519) |

### CI/CD 파이프라인

```
.github/workflows/deploy.yml
─────────────────────────────
트리거: push to main (*.md, docs/**, _workspace/** 제외)

jobs:
  deploy:
    ├─ SSH 접속 (appleboy/ssh-action)
    ├─ cd ~/auto_stock
    ├─ git pull origin main
    ├─ docker compose -f docker-compose.prod.yml up --build -d --remove-orphans
    └─ docker image prune -f
```

GitHub Secrets: `EC2_HOST`, `EC2_USERNAME`, `EC2_SSH_KEY`

### 서버 디렉토리

```
~/auto_stock/                  # git clone (전체 소스)
├── .env                       # 환경변수 (chmod 600, git 미추적)
├── logs/                      # 로그 볼륨 마운트
├── docker-compose.prod.yml    # 프로덕션 Compose
└── (나머지 소스 파일)
```
