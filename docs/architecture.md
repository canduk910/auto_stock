# 시스템 설계 문서

KIS OpenAPI 기반 주식 자동매매시스템 설계 문서. **지금 동작하는 구조만** 적는다.

> 이력: [`docs/history/docs-architecture.history.md`](history/docs-architecture.history.md)

---

## 1. 전체 아키텍처

```
+------------------+        +-------------------+        +-------------------+
|   React Frontend |  REST  |  FastAPI Backend   | KIS API|  한국투자증권      |
|   (Vite + Nginx) | <----> |  (Uvicorn)         | <----> |  OpenAPI Server   |
|   Port 80        |  /api  |  127.0.0.1:8000    |        |                   |
|   Basic Auth     |        |  ApiAuthMiddleware |        |                   |
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
                              |  AWS RDS    |              체결통보
                              |  PostgreSQL |  (asyncpg)
                              +-------------+
```

### 요청 인증 흐름

```
브라우저 / curl
   |
   | (1) https://auto.dkstock.cloud/…  ← TLS 1.2/1.3 · HSTS max-age=86400
   |     http://<EC2>:80/…            ← 301 로 https 로 보낸다.
   |                                     ACME 챌린지 경로(`/.well-known/acme-challenge/`)만 예외
   v
[nginx : frontend 컨테이너]
   |  auth_basic  "auto_stock"        ← server 레벨. SPA·/api/ 전부 덮는다.
   |  auth_basic_user_file /etc/nginx/secrets/.htpasswd   (호스트 bind mount, git 미커밋)
   |     · 무자격            → 401
   |     · 자격 + 파일 부재  → 403   (ENOENT)
   |     · 자격 + 권한 거부  → 500   (EACCES — worker uid 101 이 못 여는 경우)
   |
   | (2) location /api/ 에서 헤더 주입 (클라이언트가 보낸 동명 헤더는 **치환**된다)
   |        proxy_set_header X-API-Key "${API_AUTH_KEY}"   ← 브라우저에 노출 안 됨
   |        proxy_set_header Host      $http_host          ← 원 포트 보존(포트 탈락 시 CSRF 오탐)
   v
[FastAPI : backend 컨테이너 — 127.0.0.1:8000 (SG 오설정 2차 방어)]
   |
   |  ApiAuthMiddleware  ← **최외곽**(MetricsMiddleware 보다 바깥)
   |     · /health 만 예외, 그 외 전 경로 보호(/docs·/openapi.json 포함)
   |     · 키 미설정/불일치 → 401  (fail-closed)
   |     · 상태변경(POST/PUT/PATCH/DELETE)은 Origin 검사 추가 → cross_origin 401
   |     · 익명 401 은 하위 앱에 도달하지 않는다 = raw path 메트릭 오염 차단
   v
CORSMiddleware → 라우터
```

dev 는 nginx 를 거치지 않는다 — vite proxy 가 서버 측에서 `X-API-Key` 와 `Origin` 을
넣어 같은 관문을 통과시킨다(`frontend/vite.config.ts`).

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
│   │   ├── donchian_swing.py        # 20일 신고가 스윙 (MAIN만, 멀티데이)
│   │   ├── bull_flag_breakout.py    # 눌림목 돌파 (폴+플래그 검출)
│   │   ├── vcp_breakout.py          # 미네르비니식 VCP (멀티데이)
│   │   └── kojiro.py                # 고지로 대순환 스윙 (EMA 5/20/40, 멀티데이)
│   ├── risk.py              # RiskManager (on_tick → 보드 가드 → 전략별 신호 순회)
│   ├── order_engine.py      # OrderEngine (주문/체결/포지션 관리)
│   ├── scheduler.py         # TradingScheduler (KRX/NXT 통합 운영 08:00~20:00)
│   └── scanner.py           # 종목 스캔 + 공용 시세 캐시 + **시세 채널 리졸버** — `tick_tr_id_for(ticker, *, priority, now)` 가 프리장은 H0NXCNT0 · 정규장+애프터는 H0STCNT0 로 보내고 **정상 경로에서 통합 채널을 반환하지 않는다**(cycle294). 정본 집합 TICK_TR_IDS
│
├── db/                  # RDS PostgreSQL CRUD (asyncpg)
│   ├── pg.py                # asyncpg 풀 + 쿼리 헬퍼 (현재 DB 클라이언트 정본)
│   ├── supabase.py          # (롤백용 병존, 미사용)
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
     auth/token.py      api/base.py       db/pg.py (asyncpg)
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
│   ├── VolatilityBreakoutStrategy   (tradable_boards: main, 사이클 26 KRX ONLY)
│   │   ├── StrategyConfig (k_value_krx_main / k_value_nxt_pre[호환] / k_value_nxt_post[호환])
│   │   ├── StrategyState
│   │   ├── _targets (K, prev_range, target_offset_base,
│   │   │              boards: {board: {open_price, target_price, target_offset}})
│   │   └── _next_day_clear_pending (안전망: 15:20 청산 누락 시 익일 NXT 프리 청산)
│   ├── LongTailVolatilityStrategy   (tradable_boards: main, 사이클 26 KRX ONLY)
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

## 5. 일일 매매 스케줄 시퀀스 — KRX/NXT 통합 (매매 08:00~20:00 · 저녁 작업 ~21:30)

```
시각     Scheduler          WebSocket         OrderEngine       KIS API
─────────────────────────────────────────────────────────────────────────
07:45  run_daily() 기상       (TIME_AUTO_START)
       │
       _boot()                 (start() 안에서 즉시 — 07:45 자동 기동이면 그 직후.
       │                        TIME_BOOT(07:55) 는 런타임 미사용 상수다)
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
07:59  connect() ──────────→ WebSocket 연결        (TIME_PRESUBSCRIBE)
       │  ├─ subscribe(H0STCNI0/9, 체결통보)
       │  └─ subscribe(H0NXMKO0, "")  (실전 한정 — NXT 장운영정보)
       │  + register_board_handler(SessionTracker.on_h0nxmko0)
       │  + _session_loop() task — 30초 주기 SessionTracker.tick()
       │  _collect_presubscribe_tickers() →
       │     subscribe(tick_tr_id_for(t), 종목들)  (cycle294 — 프리장 NXT 전용 H0NXCNT0 / 정규장+애프터 KRX 전용 H0STCNT0. 통합 H0UNCNT0 는 킬스위치 off 에서만)
       │  유니버스 비어있으면 prepare() 재실행 (KIS API 일시장애 대비)
       │                         │
08:00  PRE_NXT 보드 진입       (TIME_PRE_NXT_OPEN)
       │  asyncio.create_task(_execute_next_day_clear())
       │     ← 비차단 (NEXT_DAY_STABILIZE_SECS=30s 안정화)
       │     ← 다음 영업일 NXT 프리 시가에서 청산 (Q2=B)
       │  + _confirm_breakout_open_prices(board="pre_nxt") — 0.5초/5초 폴링
       │  _phase = "pre_nxt_trading"
       │  LTV PRE_NXT 매수 시작 (k_value_nxt_pre 적용)
       │     VB 는 `DEFAULT_TRADABLE_BOARDS=("main",)` — 프리장 매수 없음
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
       │         ←───────────────┤ 실시간 체결가 (H0STCNT0 KRX 전용 / H0NXCNT0 NXT 전용 — 47필드 동일, 한 파서)
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
       │     ← 시간 가드 (2026-05-15 hotfix): 진입 시 >=15:30 이면 즉시 skip
       │        → 익일 청산 안전망 위임 (재시작 시점이 15:30 이후일 때 KRX 애프터
       │           SOR 시장가가 APBK3013 거부되던 사고 차단)
       │     ← VB/LTV 둘 다 POST_NXT 매수 비활성이라 keeps_post_nxt=False
       │     ← LTV check_force_clear()는 _limit_up_reached 제외 (상한가 모드 보유)
       │  └─ execute_sell(FORCE_CLEAR) ─────────────────────→ POST order
       │
15:30  KRX 메인 마감                          (TIME_KRX_MAIN_CLOSE)
       │  _phase = "post_nxt_trading"
       │  _confirm_breakout_open_prices(board="post_nxt")  ← LTV 상한가 모드 보유 +
       │                                                      donchian 보유 시세 확정용
       │  구독 유지: VB/LTV 보유 종목 + donchian 보유 (positions HIGH 그룹)
       │  VB 는 POST_NXT 매수 비활성(main 단독). LTV 는 코드 기본에 post_nxt 가 있고
       │  실제 활성 보드의 정본은 DB `strategy_config.params.tradable_boards` 다
       │  손절·트레일링·익일청산 평가는 보드와 무관하게 계속 돈다
       │
15:40  POST_NXT 보드 진입                     (session._BOARD_SCHEDULE)
       │  SessionTracker 보드 = post_nxt  (15:30~15:40 은 MAIN 유지 = 종가 흡수 마진)
       │  보드 경계의 정본은 `_BOARD_SCHEDULE` 이다. TIME_POST_NXT_OPEN(15:40) 은
       │  같은 값이지만 런타임 미사용 상수이고, 스케줄러의 전환·시가 확정은 위 15:30 이다
       │  시장 구간 정본 = `market_state.MARKET_TABLE`
       │     KRX 15:30~16:00 장후 시간외 종가(K5) · 16:00~20:00 애프터마켓(K6)
       │     NXT 15:30~15:40 애프터 단일가(N5) · 15:40~20:00 애프터마켓(N6)
       │
19:50  애프터 신규 매수 중단                   (TIME_NXT_POST_BUY_STOP)
       │  buy_disabled = True (모든 활성 전략)
       │
20:00  애프터 종료, unsubscribe_all() ─────→ WebSocket 구독 해제
       │                                       (TIME_NXT_POST_CLOSE)
       │
20:00  generate_recommendations()  (전략수정 AI자문 — TIME_RECOMMENDATION)
       │  ├─ collect_metrics() ──────────────────→ DB trade_history 집계
       │  ├─ OpenAI Chat Completion ─────────────→ 외부 API
       │  └─ insert_recommendation() → DB parameter_recommendations (status: pending)
       │
20:00:05 _full_universe_load_once()            (TIME_FULL_UNIVERSE_LOAD)
       │  └─ 전체 유니버스 적재 → DB stock_master (AI자문 직후 5초 마진)
       │
       │  ※ 같은 20:00 이 기동 거부 경계   (TIME_SESSION_START_CUTOFF, cycle283 D4)
       │    — 이 시각 이후 `start()` 는 거부된다. 20:00~21:30 재기동은 그날 20:30
       │      일봉 적재를 통째로 잃는다(다음 영업일 아침 immediate 가 보정하지만
       │      `_boot()` 의 prepare 보다 늦다 → `[daily_head_stale]` WARNING)
       │
20:05  run_daily_metrics_snapshot()           (TIME_METRICS_SNAPSHOT, cycle283 D5)
       │  ├─ collect_daily_log_metrics() ─────→ DB system_logs / trade_history
       │  └─ insert_log_report(model=None) → DB daily_log_reports (1차, OpenAI 미호출)
       │     ※ api_metrics·strategy_funnel 은 프로세스 메모리 전용 — 유실 노출 90분 → 5분
       │
20:30  _stock_master_daily_load_once()        (TIME_STOCK_MASTER_DAILY_LOAD, cycle283 D2)
       │  └─ KIS FHKST03010100 ──────────────→ DB stock_master_daily (~121초)
       │     ※ 09-14 KRX 애프터마켓(16:00~20:00) 종료 후 = 그날 거래량이 확정된 뒤
       │
21:30  _settle()                              (TIME_SETTLEMENT, cycle283 D3)
       │  ├─ get_balance() ─────────────────────────────────→ GET inquire-balance
       │  ├─ upsert_daily_performance() → DB (전략별 + total)
       │  ├─ generate_daily_log_report() → DB daily_log_reports (OpenAI, 완전판이
       │  │                                  20:05 1차 행을 upsert 로 덮어쓴다)
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
├─ _scan_universe(): stock_master.list_by_filter (DB 단일 조회, 사이클 108 —
│    거래량순위 API 폐기, KIS 호출 0건)
│    ├─ 시총    = raw.hts_avls (억원) JSONB 필터 ≥ min_market_cap
│    ├─ 거래대금 = raw.acml_tr_pbmn JSONB 필터 ≥ min_trade_amount
│    └─ 0종목 확정 시 ERROR 로그 + system_logs 기록
├─ get_recent_daily_normalized(): DB 우선 일봉 (사이클 173, 락/신선도/부족 시 KIS 폴백)
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
15:30 KRX 메인 마감 직후: _confirm_breakout_open_prices(board="post_nxt")  (필요 시)

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

> **DB 클라이언트**: 정본 = AWS RDS PostgreSQL + `src/db/pg.py`(asyncpg 풀). 전 db 모듈이 `pg.fetch`/`pg.execute` 네이티브 async 경유. `src/db/supabase.py` 는 롤백용 병존(미사용). asyncpg 계약 = JSONB codec(raw dict) / TIMESTAMPTZ `to_char(+09:00)` 읽기 / DATE `_kst.to_date()` / NUMERIC→Decimal.

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
│ daily_performance  (실현손익 기준 — 2026-05-15 명시화) │
├─────────────────────────────────────────────────────┤
│ date              DATE        ─┐ 복합 PK            │
│ strategy          VARCHAR(30) ─┘                    │
│ total_asset       NUMERIC                           │
│ daily_realized_pnl NUMERIC    ← SUM(SELL profit_loss)│
│ daily_profit_rate NUMERIC    ← realized/prev_asset*100│
│ cumulative_return_rate NUMERIC ← TWR 복리 누적       │
│ net_external_cashflow NUMERIC                       │
│ deposit            NUMERIC                          │
│ (매도 0건인 날은 daily_realized_pnl=daily_profit_rate=0 정상 │
│  보유 평가손익은 BalanceTable.eval_profit_loss 로 별도 표시)│
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

### 9.1 확장 테이블

| 테이블 | 마이그레이션 | 용도 |
|--------|-------------|------|
| `parameter_recommendations` | 007 (+020/021/028) | 20:00 AI 자문 — `(target_date, strategy_id)` UNIQUE + `recommended_weight/code_review_notes/applied_weight/weight_reasoning/backtest_summary JSONB`. status: pending/applied/applied_auto/partial/rejected/expired |
| `daily_log_reports` | 013 (+031) | 일일 로그 분석 (cycle283: 20:05 1차 스냅샷 + 21:30 완전판이 `ON CONFLICT (target_date) DO UPDATE` 로 같은 행) — `(target_date)` UNIQUE + summary/findings/metrics JSONB + input_tokens/output_tokens/total_tokens/latency_ms/cost_estimate_usd 5 컬럼 (사이클 31) |
| `system_logs` 인덱스 | 014 | log_level + timestamp 복합 인덱스 (조회 가속) |
| `backtest_runs` | 019 | 외부 MCP 백테스트 영속화 — `(target_date, strategy_id, params_kind)` UNIQUE. status: queued/running/completed/failed/skipped |
| `market_regime_snapshots` | 022 | dkstock.cloud 매크로 일일 스냅샷 — `_boot()` 시점 1행 + `buy_blocked/computed_cash_usage_ratio/raw_response JSONB` |
| `kis_quote_accounts` | 026 | 보조 KIS 시세 수신 계좌 (UUID PK, label UNIQUE, active=true 부분 인덱스). 60s TTL 메모리 캐시 |
| `trade_history` 부분 UNIQUE | 029 | `(ticker, order_no, trade_type) WHERE order_no IS NOT NULL AND order_no != ''` — 핑퐁 INSERT 영구 차단 (사이클 30) |
| `strategy_funnel_snapshots` | 030 (+035) | 전략별 조건검색 단계별 후보/탈락 영구 추적 — UNIQUE `(target_date, strategy_id, step_no)` + UPSERT |
| `stock_master_history` | 032 (+036) | stock_master 갱신 이력 — PK (ticker, seq=0/1) + trigger |
| `stock_master_daily` | 033 | KIS FHKST03010100 일봉 정규화 — PK (ticker, bas_dd) + OHLCV + change_rate + raw JSONB. 매일 **20:30** KST 적재(`TIME_STOCK_MASTER_DAILY_LOAD`, T-100 백필 → D-1 증분) |
| `stock_master.master_raw` | 034 | KIS 공식 일일 마스터 파일 raw JSONB + master_raw_updated_at + is_kospi200/is_kosdaq150 BOOLEAN (037, 사이클 153) |
| `pending_next_day_clear` | 038 | 익일청산큐 DB 영속화 — PK (target_date, ticker, strategy_id). 재기동 시 메모리 휘발 차단 |
| `llm_buy_evaluations` | 043 | AI 매수평가(LLM)를 주문 발화 시점에 기록 — PK (trade_date, account_no, ticker, order_no) + eval_kind('order'|'blocked'). 주문 1건 = 1행(성공·실패 모두), 매매 hot path 무관한 관측 계층. 열 정의 정본 = 루트 `CLAUDE.md` DB 스키마 표 (cycle276). 프로세스 분리 1단계가 이 테이블을 큐로 재사용한다 → 15.2 |

---

## 10. 프론트엔드 구조

```
frontend/src/
├── App.tsx                 # 라우터 (Dashboard, History, Settings)
│
├── pages/
│   ├── Dashboard.tsx       # 메인 대시보드 (전략 탭 + 컴포넌트 배치)
│   ├── History.tsx         # 거래 내역 페이지 (주문체결 / 매매손익 2 탭)
│   ├── Strategies.tsx      # 전략별 실적/스캔 깔때기
│   ├── StrategyFunnel.tsx  # 조건검색 단계별 추적 (사이클 34)
│   ├── StockMaster.tsx     # 종목마스터 (사이클 84+, KIS 마스터/일봉/필터/4 작업 trigger + 진행 배너)
│   ├── RealtimeHealth.tsx  # WebSocket 구독 슬롯 진단 (사이클 103+, 세션별 expand + CCNL 캐시)
│   ├── Recommendations.tsx # 전략수정 AI자문 (신규/이력 탭, 백테스트 비교)
│   ├── Logs.tsx            # 시스템 로그 + 일일 분석 리포트 통합 (사이클 6)
│   └── Settings.tsx        # 전략 비중/파라미터/자동시작/가격·거래대금 필터/외부 통합 토글
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

> 위 제약 중 "단일 uvicorn 워커"·"체결통보 구독 필수"는 프로세스를 가르는 순간 재설계가 필요하다. 언제 어디까지 가를지는 15장(프로세스 분리 로드맵), 특히 보류 근거 네 가지를 정리한 15.4 를 본다.

---

## 12. 배포 환경 (AWS EC2)

```
개발자 PC                    GitHub                     AWS EC2 (서울)
───────────                  ──────                     ──────────────
git push ───────────→ CI (Build & Test)
                      └─ conclusion=success 일 때만 Deploy 가 뜬다 (workflow_run)
                         ├─ appleboy/ssh-action
                         └───────────────────────────→ SSH 접속
                                                       ├─ git pull origin main
                                                       ├─ supabase/migrations/*.sql psql 적용
                                                       └─ tools/deploy/compose_up_changed.sh
                                                          (full / frontend / none — 15.7)
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
트리거: CI("CI — Build & Test") 의 workflow_run, conclusion=success + event=push (main)
        CI 자체가 *.md · docs/** · _workspace/** 만 바뀐 push 에는 뜨지 않는다 (paths-ignore)
직렬화: concurrency group `deploy-ec2` (cancel-in-progress: false)

jobs:
  deploy:
    ├─ SSH 접속 (appleboy/ssh-action) + `set -e`
    ├─ cd ~/auto_stock && git pull origin main
    ├─ supabase/migrations/*.sql 순차 psql 적용 (secret `SUPABASE_DB_URL` = RDS DSN, graceful skip)
    └─ bash tools/deploy/compose_up_changed.sh   ← 배포 모드 판정 (15.7)
```

GitHub Secrets: `EC2_HOST`, `EC2_USERNAME`, `EC2_SSH_KEY`, `SUPABASE_DB_URL`(값 = RDS DSN)

### 서버 디렉토리

```
~/auto_stock/                  # git clone (전체 소스)
├── .env                       # 환경변수 (chmod 600, git 미추적)
├── logs/                      # 로그 볼륨 마운트 (20일 보관 · 🔴 압축 금지)
├── docker-compose.prod.yml    # 프로덕션 Compose
└── (나머지 소스 파일)
```

🔴 **`logs/` 의 회전 파일을 손으로 압축하지 않는다.** `TimedRotatingFileHandler` 는 자기가 만든
이름 규칙(`auto_stock.log.YYYY-MM-DD`)의 파일만 세어서 지운다 — `.gz` 로 바꾸면 그 규칙에서
벗어나 **자동 삭제 대상에서 영구히 빠진다**(2026-09-18 실측: 37개 1.9GB 가 그렇게 남아 루트
여유가 배포 문턱 아래로 떨어졌다). 디스크가 모자라면 압축이 아니라 `src/main.py` 의
`_LOG_BACKUP_DAYS`(현재 **20**)를 줄인다.

---

## 13. 확장 인프라 — 전략 · 시세 풀 · 레짐 · 백테스트 · 자문

1~12 장이 다루지 않는 확장 계층의 현행 계약. 사이클별 도입 경위는 `docs/HARNESS_CHANGELOG.md`,
모듈 계약은 각 디렉터리 `CLAUDE.md` 가 정본이다.

### 13.1 다중 전략 확장 (7 전략)

- `bull_flag_breakout` (눌림목 돌파, `stock_master.list_by_filter` 시총·거래대금 컷 → 폴 자동 검출 + 플래그 검출 → 09:05~13:00 돌파 + 거래량 ≥ 평균×2. 5영업일 시간 청산, 3영업일 쿨다운)
- `vcp_breakout` (미네르비니식 VCP. 일봉 100일(prepare cap) → 추세 필터 + 베이스 검출 + pullback 점진 수축 + 거래량 수축 → 09:05~14:30 돌파. **멀티데이 보유**. 7영업일 쿨다운)
- `kojiro` (고지로 대순환 스윙 — EMA 5/20/40 대순환 스테이지 + ATR/종가 밴드 1.0~4.5% → strict entry(스테이지1 + 6→1 인접 + 3선 우상향 + 종가>EMA5) → 09:05~09:30 시장가(갭업/갭다운/붕괴 스킵). 청산 = 고정%(-8%)→2ATR→스테이지3→2.5ATR 트레일. **멀티데이**. 사이징은 `sizing_mode` 가 정한다 — 코드 기본 `position_ratio`, `turtle` opt-in. 지표 순수모듈 `kojiro_indicators.py`)
  - **코드 기본값 `enabled=False` 는 다크런치 잔재다. 운영 DB 는 `enabled=True` = 실매매 중**이고,
    활성 여부·비중·`sizing_mode` 의 정본은 DB `strategy_config` 다
- **코드 정본 `_MULTIDAY_STRATEGIES = frozenset({donchian_swing, vcp_breakout, kojiro})`** — `is_next_day` 항상 False. 3 전략 모두 `strategy_base.py` **리터럴에 정적 선언**한다(동적 side-effect 추가 금지 — 그 패턴은 목록을 읽는 시점마다 답이 달라진다)
- 상세: `src/engine/strategies/CLAUDE.md`

### 13.2 다중 KIS 계좌 + WebSocket 풀

- DB 테이블 `kis_quote_accounts` (UUID PK, label UNIQUE) — 보조 KIS 시세 수신 계좌
- `src/auth/token.py::get_token_manager(label=None)` async lazy 발급 + 격리 캐시 파일
- `src/realtime/websocket_pool.py::WebsocketPool` — 메인 + 보조 N 세션 풀
  - HIGH 우선순위 (보유/익일청산) → 메인 절대 보장 (`bypass_limit=True`)
  - LOW 우선순위 (스캐닝) → 보조 라운드로빈, 보조 가득 시 메인 fallback
  - 체결통보 (H0STCNI0/H0STCNI9) → **메인 단일 강제** (보조 시도 시 `QuoteSessionExecutionNoticeError`)
  - 총 슬롯 = 41 × (1 + N). 보조 0개면 메인 단독
- `src/api/base.py::kis_get_quote / kis_post_quote` — REST 시세성 호출 풀 (path 화이트리스트 5개)
- `src/services/quote_session_health.py` — 보조 세션 health monitor (5xx/토큰 발급 실패 누적 → 자동 비활성 + DB `active=false`)
- `GET /api/realtime/subscriptions` 응답에 `sessions[]` 배열 (label/subscribed/acked/fresh/stale/limit/ws_connected/reconnect_count)
- Frontend: `KisQuoteAccountsCard` (Settings) + `KisAccountPoolCard` (Dashboard) 30s 폴링

### 13.3 시장 레짐 — 관찰 전용

- `src/engine/market_regime.py` — dkstock.cloud 매크로 fetch → `MarketRegime` dataclass (regime/vix/fear_greed/buffett/cash_min)
- 🔴 **레짐은 매수를 차단하지도 축소하지도 않는다**(사이클 I, 2026-08-03). `risk.on_tick` 과 swing 폴링의
  `get_buy_block_state()` 게이트가 제거됐고, `execute_buy(soft_multiplier=…)` 는 **호출자 0건**이다
  (`order_engine.py` 의 파라미터는 vestigial, 기본 1.0). 레짐 대응 수단은 `cash_usage_ratio` 하나다
- `buy_block_mode`(`OFF`/`WARN`/`SOFT`/`HARD`)와 `BuyBlockState{mode, blocked, soft_multiplier, reasons}`,
  4 임계 OR(`regime=defensive` / `vix > vix_threshold` / `fear_greed_score > fg_high_threshold` / `< fg_low_threshold`)는
  **대시보드·AI 자문 payload 표시 전용**으로 남아 있다(매매 미소비). 운영 DB 권장값 = `OFF`(정직 표시)
- `get_buy_block_state()` 60s TTL 인스턴스 캐시 → DB 쿼리 180배 감소
- `cash_usage_ratio` 자동 조정: `clamp((100-cash_min)/100, 0.0, 1.0)`. `auto_regime_adjust=true` 시 매크로 cash_min 기반 자동 갱신
- DB `market_regime_snapshots` 일일 스냅샷 (`_boot()` 시점 1행)
- Frontend: `MarketRegimeCard` (Dashboard) + `IntegrationToggleCard::BuyBlockSection` (Settings)

### 13.4 외부 백테스트 (MCP)

- `src/engine/backtest_engine.py` + `backtest_yaml.py` — 외부 MCP 백테스트 서버 (`http://43.202.187.5:3846/mcp`)
- 20:00 AI 자문 INSERT 직후 6 전략 × 2 kind = 12 job fire-and-forget
- DB `backtest_runs` 영속화 (`(target_date, strategy_id, params_kind)` UNIQUE, status: queued/running/completed/failed/skipped)
- `parameter_recommendations.backtest_summary` JSONB 동봉 (현재 params vs 추천 params 의 8 메트릭 비교)
- YAML DSL 지원 3종: momentum / volatility_breakout / donchian_swing
- 폴백 4종: long_tail_volatility / bull_flag_breakout / vcp_breakout / kojiro — 즉시 skipped 마킹 (백테스트 DSL 미지원)
- 활성화 토글: `KIS_MCP_ENABLED` (기본 false)
- `max_drawdown` 양수(절대값) 컨벤션 — `signInverted=true`
- Frontend: `BacktestComparisonCard` (Recommendations)

### 13.5 AI 자문 계약

- `parameter_recommendations` 자문 컬럼:
  - `recommended_weight` NUMERIC (자산 배정 자문 — 0.0~1.0)
  - `weight_reasoning` TEXT (비중 변경 사유, ≤1000자, 한국어, 통합 `reasoning` 과 별개)
  - `code_review_notes` TEXT (로직 자유 텍스트, ≤2000자)
  - `applied_weight` NUMERIC (apply 시 사용자 명시 토글)
  - `backtest_summary` JSONB
- `_validate_recommendations()` 5-tuple 반환 `(validated_params, reasoning, weight, notes, weight_reasoning)`
- user_payload 12 키 (current_weight + peer_weights + peer_metrics + market_regime)
- `PARAM_RANGES` 화이트리스트: `k_value_krx_main/k_value_nxt_pre` (0.5~2.0) + `stop_loss_main/stop_loss_pre_nxt` (-15.0~0.0) + `donchian_period` (10~60) + `long_ma_period` (20~120) + `volume_multiplier`/`atr_trail_mult` (1.0~5.0)
- `min(candidates)` 손절률 정책 — 5 키 후보 (`stop_loss_rate`/`intraday_stop_loss`/`overnight_stop_loss`/`stop_loss_main`/`stop_loss_pre_nxt`)

### 13.6 운영 안정성 — stale 감시와 정합성 가드

- WebSocket stale watcher 임계: `STALE_WATCHER_INTERVAL_SECS=120` / `STALE_FRESHNESS_SECS=60` /
  `MAX_STALE_RETRIES=5` (6회 이상 stale 은 시간 기반 force_retry 경로가 받는다)
- 다중 안전망 4중: F1 (재연결 1회) + `_scan_loop` (5분) + K watcher (120s) + `_resubscribe_stale_priority` (5분 우선)
- `_subscriptions` 정합성 가드 (in-flight ACK race 차단)
- `_report_tick_coverage()` 풀 통합
- `list_accounts()` 60s TTL 메모리 캐시 — 폴링 race 차단
- 배포 창(보유 중 장중 push 금지 · 20:00~21:35 금지)의 정본은 루트 `CLAUDE.md` 운영 가이드다

### 13.7 로그 메뉴 통합

- 시스템 로그와 일일 분석 리포트가 `pages/Logs.tsx` 한 메뉴에 있다 (`?tab=system|daily-report`)
- 시스템 로그 탭: `from_date`/`to_date` 분리 date input + 레벨 토글 + 페이징 (1-base, size 50)
- `/api/logs` 응답 = `{items, total, total_pages}` dict. `?limit=50&level=ERROR` 형태도 받는다

---

## 14. 운영 계약 — 보드 · 장운영 · 적재 · 복구

1~13 장이 다루지 않는 운영 계약의 현행 사실. 도입 경위는 `docs/HARNESS_CHANGELOG.md`,
모듈 계약은 각 디렉터리 `CLAUDE.md` 가 정본이다.

### 14.1 보드 · `tradable_boards` · 시세 채널

- 매수 창의 중심은 KRX 메인 09:00~15:20 이다. VB `DEFAULT_TRADABLE_BOARDS=("main",)` (프리·애프터 매수 없음) ·
  LTV `("pre_nxt", "main", "post_nxt")` (연속 상한가 익일 청산 + 야간 매수). **실제 활성 보드의 정본은
  DB `strategy_config.params.tradable_boards`** 이고 코드 기본값은 그 폴백이다
- `tradable_boards` 는 **매수 진입 전용**이다 — 매도·손절·트레일링·익일청산·15:20 강제청산은 보드와
  무관하게 항상 돈다(유일한 예외 = LTV 프리장 청산 평가 보류, `risk._PRE_MARKET_EXIT_EVAL_STRATEGIES`)
- `MarketBoard` 3 보드: `pre_nxt` (08:00~09:00) / `main` (09:00~15:40) / `post_nxt` (15:40~20:00)
- **시세 채널은 종목마다 갈린다** — `scanner.tick_tr_id_for(ticker, *, priority, now)` 가 프리장은 `H0NXCNT0`,
  정규장+애프터는 `H0STCNT0` 를 돌려주고 **정상 경로에서 통합 채널 `H0UNCNT0` 를 반환하지 않는다**(cycle294).
  통합 채널은 `nxt_tradable=False` 종목의 체결 프레임을 보내지 않으면서 SUBSCRIBE 는 SUCCESS ACK 를
  주기 때문에 구독이 살아 있는 것처럼 보이고 프레임만 영구 0 이다 — 그것이 채널을 가른 이유다
  - 전환은 `tick_channel_clock.switch_windows()` 가 `market_state` 표에서 파생한 **창 안에서만** 일어난다
    (아침 1 + NXT 단독 연속 구간 경계 2)
  - 판정 실패의 폴백도 전용 채널이다 — L1=KRX / L2=프리 창 NXT / L3=`off` 만 통합
  - 킬스위치 `system_config.tick_channel_resolver_mode`(기본 `observe` = 행위 0) + 다이얼 5키,
    즉시 반영 `PUT /api/realtime/tick-channel-mode`
  - 정본 집합 `TICK_TR_IDS`. 상세 = `src/realtime/CLAUDE.md` 「시세 채널」 절
- 15:20 KRX 메인 강제 청산 `_force_clear_main_only` — VB 전량 + LTV 상한가 미도달분.
  진입 시각이 15:30 을 넘었으면 skip 하고 익일 청산에 넘긴다

### 14.2 종목별 H0UNMKO0 구독 + VI/거래정지 stale 회피

- `src/api/market_operation.py` — `MARKET_OP_TR_ID=H0UNMKO0` + 10 컬럼 (TRHT_YN/VI_CLS_CODE/OVTM_VI_CLS_CODE/ISCD_STAT_CLS_CODE 등). REST 폴백 `inquire_vi_status_today` (FHPST01390000)
- `src/engine/market_operation_monitor.py` — H0UNMKO0 **수신·상태 추적** + `is_ticker_stale_excluded()` hook
- `src/engine/market_op_subscribe.py` — **구독 배치**. `scheduler` 에는 5줄 위임 wrapper 만 있다
  - 대상은 **보유 + 익일청산뿐**이다
  - 🔴 **메인 세션 구독 0건** · 보조 세션 **직접** 라운드로빈 + `bypass_limit=False` — 메인에
    `bypass_limit=True` 로 직접 구독하면 메인 슬롯이 밀려 보유 종목이 tick blind 가 된다
    (2026-08-19 OPSP0008 사고)
  - 실효 상한은 `MAX_SUBSCRIPTIONS`(41)이다. 시그니처의 `cap`(기본 60) 은 vestigial
- `stale_watcher_core` VI/halt grace 회피 + REST 폴백 부팅 1회 seed

### 14.3 stock_master_daily retention

- `purge_old_rows()` T-150일 retention cron 매일 **16:15** KST(`TIME_STOCK_MASTER_DAILY_PURGE`)
  + `protected_tickers` 보호. 적재(20:30)보다 앞이라 그날 적재분은 다음 날 purge 대상이다
- `_purge_by_cutoff` 는 2-step subquery 로 지운다 — 한 번에 지우려는 chain 은 조용히 실패한 전력이 있다
- `stock_master_history` = PK (ticker, seq=0/1) + trigger (migration 036)

### 14.4 `_wait_until` 2 모드 계약

- default = 시각이 이미 지났으면 **즉시 break**(`run_daily` 의 단계 전환용)
- `advance_if_passed=True` = 다음 날로 넘긴다(`task_loop_helper` 폭주 차단용)
- 🔴 default 를 `advance_if_passed` 쪽으로 바꾸면 그날 15:20 강제청산이 통째로 건너뛰어진다
  (2026-06-17 실사고)

### 14.5 `_handle_buy_fill` 체결단가 정합

- BUY `trade_history.price` = KIS `CNTG_UNPR`(체결단가). 주문가가 아니라 체결단가가 정본이다
- UniqueViolation 이면 INSERT 대신 UPDATE 로 돌린다

### 14.6 익일청산큐 DB 영속화 + 동시호가 stale 회피

- migration 038 = `pending_next_day_clear` PK (target_date, ticker, strategy_id) — 재기동 시 메모리 휘발 차단
- `_boot()` 복구 chain + DB 실패 시 메모리 보존 graceful
- `SessionTracker.is_call_auction_now()` (08:30~09:00 / 15:20~15:30 = MKOP_CLS_CODE 110/121) → stale 재구독 skip

### 14.7 2차 `_boot` stock_master race 가드 + 5 전략 prepare 재시도 hook

- `count_active()` polling 5분 cap (10초 주기)
- 5 전략 (VB/LTV/donchian/BFB/VCP) prepare 0건 시 자동 재시도 hook 통일
- `_handle_buy_fill` 전량 체결 분기 3 영역 try/except 분리 — DB INSERT 실패 시 callback graceful

### 14.8 시가 미확정 종목 자동 재시도

- `_confirm_breakout_open_prices_if_pending` 5분 주기 hook — `_scan_loop` 통합. 미확정 종목 자동 시가 확정 재시도 (idempotent + disabled skip + graceful)
- 이중 안전망 = VB `check_buy_signal` tick fallback + `_scan_loop` 5분 재시도

---

## 15. 프로세스 분리 로드맵

매매 엔진은 지금 **한 프로세스**다. 시세 감시·전략 판정·주문·정산·관측이 같은 uvicorn 단일
워커 안에 있어서, 프롬프트 한 줄을 고치려 해도 backend 전체를 재시작해야 하고(재시작 1~5분
tick blind — 루트 `CLAUDE.md` 운영 가이드 D6 = cycle232. cycle248 이 실측한 특정 push 2건은
약 100초였다), 보유 포지션이 있으면 장중 배포 자체가 금지돼 있다. 이 장은 그 결합을 단계적으로
푸는 계획을 적는다.

| 단계 | 범위 | 상태 |
|------|------|------|
| 0 | 현재 — 컨테이너 2개(backend / frontend) | 가동 중 |
| 1 | AI 매수평가(LLM)를 `llm_worker` 로 분리 | **진행 중** (cycle279 — 워커 컨테이너 신설) |
| 2 | 20:00 자문 · 21:30 로그 분석 · 외부 백테스트 분리 (퍼널은 가를 수 없다 → 15.3) | 계획 (착수 미정) |
| 3 | 시세 감시 ↔ 전략 판정 ↔ 주문 완전 분리 | **보류** (착수하지 않는다) |
| 4 | 메시지 기반 5프로세스 (WS·REST 전송 2 + 시세·전략평가 / 주문 / 체결) | **방향 기록** (승인 전 · 3단계를 흡수한다 → 15.5) |

> 1단계가 "진행 중"인 근거는 **사용자 결정(2026-09-11 — "1단계만 진행")** 이다. 사이클 번호
> `cycle279` 는 예약해 둔 것이고 명세·코드·changelog 항목은 아직 없다. 2·3·4단계는 승인된
> 설계가 아니라 방향 기록이다.

### 15.1 0단계 — 현재 (가동 중)

```
  +------------------+          +-------------------------------------------+
  |  frontend        |   /api   |  backend  (uvicorn 단일 워커)             |
  |  nginx:alpine    |--------->|  scheduler / session / scanner            |
  |  SPA + BasicAuth |          |  strategies(7) -> risk -> order_engine    |     KIS WebSocket
  +------------------+          |  llm_buy_gate (AI 매수평가 — 7전략 shadow) |<--> (시세 · 체결통보)
                                |  recommendation_engine  (20:00 자문)      |
                                |  log_analysis_engine    (21:30 분석)      |     KIS REST
                                |  api/base.py  _semaphore = Semaphore(20)  |<--> (주문 · 잔고 · 일봉)
                                +---------------------+---------------------+
                                                      | asyncpg (db/pg.py)
                                                      v
                                          +------------------------+
                                          |   AWS RDS PostgreSQL   |
                                          +------------------------+
```

`docker-compose.prod.yml` 의 서비스는 `backend` · `frontend` 둘뿐이다. 위 상자 안의
모든 이름은 같은 이벤트 루프 위에서 돈다.

### 15.2 1단계 — AI 매수평가 분리 (진행 중 · cycle279 = llm_worker 컨테이너 신설)

여기서 "AI 매수평가"는 cycle274 가 배선하고 cycle276 이 주문 시점으로 옮긴 **관찰 기능**이다 —
매수 주문 직후에 LLM 이 점수를 매겨 **기록만** 하고 매수 여부는 바꾸지 않는다(shadow).
**7전략 전부** 켜져 있다 — cycle297(2026-09-17 `a61ded9`)이 나머지 5전략에 `"llm_gate_mode": "shadow"`
4키를 넣어 넓혔다(사용자 결정 = "모든 전략에 걸어 데이터를 쌓고 전략별로 하나씩 enforce").
배선 자체는 전략 무관이다 — `order_engine` 의 호출부 2곳(주 경로 · 지정가 폴백 경로)이 모든 전략을
같은 코드로 태우고, 갈리는 것은 `llm_gate_mode` 값 하나뿐이다(`llm_buy_gate._read_mode`).

1단계는 이 평가를 별도 컨테이너 `llm_worker` 로 뺀다. 엔진은 평가 **요청 행**만 DB 에 적고,
워커가 그 행을 선점해 일봉 조회·지표·프롬프트·모델 호출을 하고 결과를 같은 행에 채운다.
큐로 **재사용할 대상**은 신규 메시지 브로커가 아니라 평가 테이블
`llm_buy_evaluations`(`supabase/migrations/043_llm_buy_evaluations.sql`)다.

```
  +------------------+          +-------------------------------------------+
  |  frontend        |   /api   |  backend  (uvicorn 단일 워커)             |
  |  nginx + SPA     |--------->|  scheduler / scanner / strategies         |     KIS WS / REST
  +------------------+          |  risk / order_engine                      |<--> (워커는 쓰지 않는다)
                                |  execute_buy: place_order 성공 직후       |
                                |    create_task 안에서 요청 행만 남긴다    |
                                +---------------------+---------------------+
                                                      | asyncpg
                                                      v
                        +--------------------------------------------------+
                        |  llm_buy_evaluations   (migration 043)           |
                        |  지금은 결과 기록 테이블이다 — 큐로 쓰려면       |
                        |  선점 열(status/claimed_at/attempts) 추가 필요   |
                        +--------------------------------------------------+
                             |  미처리 행 선점      ^  결과 UPDATE
                             v                      |
                        +--------------------------------------------------+
                        |  llm_worker  (신규 컨테이너 — 예정)              |
                        |   stock_master_daily 일봉 조회 (DB)              |
                        |   -> 지표 -> 프롬프트 -> 모델 호출               |
                        |   -> 같은 행에 점수 · 근거 · 비용 기입           |
                        |   KIS 미호출 (api/auth/realtime import 0)        |
                        +--------------------------------------------------+
```

- **얻는 것** — 프롬프트·지표·모델을 **장중에** 고칠 수 있다. 지금은 그 한 줄을 고치려 해도
  backend 재생성이 필요하고(재시작 1~5분 tick blind — D6. cycle248 실측 2건은 약 100초),
  보유 중에는 그 배포가 금지돼 있다.
- **KIS 격리** — 워커는 KIS 를 호출하지 않는다. 현재 `src/engine/llm_buy_gate.py` 도
  `src.api` / `src.auth` / `src.realtime` 를 한 번도 import 하지 않고(실측 0건), 일봉은
  `src.db.stock_master_daily` 에서 읽는다(`llm_buy_gate.py:55`). `.token_cache` 도
  마운트하지 않는다. 이 격리가 15.4 의 보류 근거 ①②③ 을 건드리지 않는 이유다.
- **엔진 쪽 실패 흡수** — 훅은 지금도 never-raise 다(`order_engine.py:433-459` 의
  `try/except` + `logger.debug`). 워커가 죽어도 매매 영향은 0 이고 요청 행만 쌓인다.

**미확정 — cycle279 명세에서 정한다.**

| 항목 | 지금 상태 | 정해야 할 것 |
|------|-----------|--------------|
| 선점 규약 | migration 043 에 claim/status/lease 열이 **없다**. 미처리 행을 커버하는 인덱스도 없다(4개 전부 `trade_date`/`strategy_id`/`ticker`/`order_no` 축) | 선점 열 + 미처리 행 인덱스를 더하는 **가산형 마이그레이션**. `result` 등 NOT NULL 11열에 "아직 채워지지 않은 행"을 어떻게 넣을지(센티넬 여부)도 함께 |
| 요청 행을 적는 자리 | 동기 훅 안에서는 **불가**하다 — `observe_order` 는 sync·DB 금지(가드 C1-14 `tests/unit/ast/test_cycle276_ast_order_hook.py:580`)이고 훅~PENDING INSERT 사이 `await` 0건(C1-9 `:488`)·훅 자체 `await` 금지(C1-4 `:425`)다 | 오늘처럼 `asyncio.create_task` 안에서 적을지, 자리를 옮길지 |
| 워커 경로 | `src/workers/` 디렉터리는 **없다** | 워커 축 경로와 `BACKEND_RE` 제외 방식 (15.7 ⚠️) |
| 컨테이너 정의 | `docker-compose.prod.yml` 에 `llm_worker` 서비스가 **없다** | 오버레이가 아니라 **본체**에 정의 (15.7 ⚠️) |

현재(0단계) 훅 자리는 이렇다 — 1단계는 이 자리를 옮기지 않고 **뒷단만** 뗀다.

```
  execute_buy  (order_engine.py:251)
  │
  ├─ place_order (KIS 접수)
  ├─ 주문번호 매핑 등록                            ← 동기 영역
  ├─ llm_buy_gate.observe_order(...)               ← order_engine.py:434
  │   └─ 래치/캡 확인 → asyncio.create_task(...)   ← llm_buy_gate.py:759
  │        · 0단계: 같은 프로세스에서 모델 호출
  │        · 1단계: 이 task 가 요청 행만 남기고 워커가 집어 간다
  └─ PENDING INSERT
```

훅은 여기 한 곳이 아니라 **두 곳**이다 — 위의 주 경로(`:434`)와 시장가 거부 뒤 지정가 폴백
경로(`:535`). 가드 `test_c1_1_hook_appears_exactly_twice` 가 정확히 2곳임을 강제하므로 1단계도
두 자리를 같이 옮긴다.

> `llm_buy_evaluations` 의 **열 정의 정본은 루트 `CLAUDE.md` 의 DB 스키마 표**다(cycle276 —
> "주문 발화 시점에 기록, 주문 1건 = 1행"). 1단계는 그 기록 테이블에 "아직 채워지지 않은 행 = 작업
> 대기열" 이라는 의미를 하나 더 얹는 설계이므로, 착수하면 그 정본 행도 cycle279 에서 함께 고친다.

### 15.3 2단계 — 관측·분석 분리 (계획 · 착수 미정)

20:00 AI 자문, 21:30 일일 로그 분석, 외부 백테스트 연동을 워커 쪽으로 옮긴다.

```
  +---------------------------------------------+
  |  backend  (매매 전용으로 얇아진다)          |
  |  scheduler / scanner / strategies           |
  |  risk / order_engine / realtime             |
  |  ※ 퍼널 캡처는 여기 남는다 (_funnel_steps)  |
  +---------------------------------------------+
                        | asyncpg
                        v
  +---------------------------------------------+
  |       AWS RDS PostgreSQL                    |
  |   parameter_recommendations                 |
  |   daily_log_reports                         |
  |   strategy_funnel_snapshots                 |
  |   backtest_runs                             |
  +---------------------------------------------+
        ^  결과 쓰기               |  읽기
        |                          v
  +---------------------------------------------+
  |  llm_worker  (2단계에서 분석 작업 추가)     |
  |   20:00 AI 자문     recommendation_engine   |
  |   21:30 로그 분석   log_analysis_engine     |
  |   외부 백테스트 MCP                         |
  +---------------------------------------------+
```

- **얻는 것** — 리포트 로직을 장중에 고칠 수 있다. 21:30 정산 시각에 무거운 분석이
  엔진 이벤트 루프를 점유하지 않는다.
- **위험 — 균일하지 않다. 셋으로 갈린다.**

| 대상 | 위험 | 이유 |
|------|------|------|
| 21:30 로그 분석 · 외부 백테스트 | 낮음 | live registry 를 읽지 않는다. DB 를 읽어 DB 에 쓴다 |
| 20:00 AI 자문 | **중간 — 매매 행위가 바뀐다** | `recommendation_engine.py:404-406`·`:581-582` 가 `trading_scheduler.registry` 를 잡아 **살아 있는 전략 객체**를 읽고, auto_apply 는 `:626 strategy.config.weight = new_weight` · `:657 strategy.config.params[k] = v` 로 그 객체를 **직접 변이**한다. 이 in-memory 쓰기가 파라미터 즉시 반영의 유일한 경로다(루트 `CLAUDE.md` — `strategy_config` SQL UPDATE 는 다음 재시작에서만 반영). 워커로 옮기면 DB 쓰기만 남아 감액·보수적 파라미터가 **다음 재시작까지 실매매에 반영되지 않는다** |
| 퍼널 스냅샷 | 가를 수 없다 | 데이터 원천이 DB 가 아니라 **엔진 프로세스의 메모리**다. `capture_funnel_snapshots(registry, …)`(`scheduler.py:186`)가 registry 를 순회해 각 전략의 `_funnel_steps` 를 읽고(`:236`, 접근 실패 로그 `:238`), 호출자는 `_scan_loop` 안의 `:2424` 다. 워커 프로세스엔 그 객체가 없다 |

그래서 2단계의 실제 범위는 **적재·분석 쪽**이다. 퍼널은 **캡처는 엔진에 남기고 적재(영속)만**
옮길 수 있고, 20:00 자문은 적용(`auto_apply`)을 엔진 측 API(`PUT /api/strategies/{id}/params`)로
되돌리는 설계가 **선행**돼야 옮길 수 있다.

### 15.4 3단계 — 시세 감시 ↔ 전략 판정 ↔ 주문 완전 분리 (보류 — 지금 하지 않는다)

사용자 원안의 "시세 감시(데몬) → 전략 판정 → 주문" 완전 분리다. 아래 도식의 ①~④ 네 곳이
현재 코드가 **프로세스 안** 자원으로 강제하고 있는 지점이며, 그것이 보류 근거다.

```
  +------------------+   ticks   +------------------+  orders  +------------------+
  |  feed daemon     |---------->|  decision proc.  |--------->|  order proc.     |
  |  WS 구독 · 캐시  |           |  전략 판정       |    ④     |  KIS 주문 접수   |
  +--------+---------+           +--------+---------+          +--------+---------+
           |                              |                             |
           | ③ 체결통보 메인 단일         |                             | ① REST 20/s
           | ① REST 20/s  ② 토큰 발급     |                             | ② 토큰 발급
           |   (폴링 · 조건검색도 쓴다)   |                             |
           +------------------------------+-----------------------------+
                                          |
                                          v
                               +--------------------+
                               |  AWS RDS Postgres  |
                               +--------------------+
```

①②는 **양쪽 기둥에 다 걸린다** — 주문만 REST·토큰을 쓰는 게 아니라 피드·스캔 쪽도 쓴다
(donchian `_swing_rest_poll_loop` 60초 폴링, stale universe 가드의 `inquire_ccnl`, 조건검색).
보조 시세계정은 라벨마다 또 다른 세마포어를 쓴다(`src/api/base.py:346` `asyncio.Semaphore(18)`).
④는 `decision` 아래가 아니라 **두 기둥의 경계**에 있다 — `order_engine.execute_buy` 안에서
전략의 `calc_buy_quantity` 를 부르는 구간이라 전략 판정과 주문을 가로지른다.

보류 근거 — 측정된 코드 사실 네 가지:

| # | 제약 | 정본 위치 | 가르면 생기는 일 |
|---|------|-----------|------------------|
| ① | REST 초당 20건 한도가 **프로세스 안** 세마포어 | `src/api/base.py:28` — `_semaphore = asyncio.Semaphore(20)` | 두 프로세스면 계정 한도 40/s 위반. 두 프로세스 **모두** REST 를 쓴다 |
| ② | 토큰 발급 분당 1건 가드가 **프로세스 안** Lock | `src/auth/token.py:50` — `_GLOBAL_ISSUE_LOCK: asyncio.Lock \| None = None`(lazy 생성 `:55-60`) + `:52` `_ISSUE_GAP_SECS: float = 61.0` | KIS `/oauth2/tokenP` 는 분당 1개 전역 한도라 두 프로세스가 각자 발급하면 일부 403(`token.py:10`) |
| ③ | 체결통보(H0STCNI0/H0STCNI9) **메인 세션 단일 강제** | `src/realtime/websocket_pool.py:64` `_EXECUTION_NOTICE_TR_IDS` + `:109` `_enforce_main_only_execution_notice` (보조 세션 구독 시 `QuoteSessionExecutionNoticeError` `:57`) | 체결이 다른 프로세스에 도착해 손절 경로에 한 홉이 늘어난다 |
| ④ | 매수 수량 계산 ~ 대기 등록 사이 `await` 0건 규약(A-ATOMIC) | `src/engine/order_engine.py:741`(`calc_buy_quantity`) ~ `:782`(`pending_buys.add`) ~ `:784`(`pending_buy_amounts`), 가드 `tests/unit/ast/test_budget_limit_ast.py:60` | 단일 이벤트 루프 전제가 깨져 예산·중복 판정이 분산 잠금 문제가 된다. 이 경로에서 메시지 한 건 중복 = 주문 한 건 중복 |

**예상** — 지금 설계는 틱 경로를 동기적으로 막지는 않는다. 평가를 `asyncio.create_task` 로
던지고 즉시 반환하기 때문이다(`src/engine/llm_buy_gate.py:759`, 동시 실행은 `:141`
`_SEM = asyncio.Semaphore(2)` 로 2건까지). 다만 같은 이벤트 루프와 같은 asyncpg 풀은 계속
공유하고, 3단계의 남은 동기 — 전략 판정 경로가 죽을 때 WS 피드까지 같이 죽지 않게 하는 **크래시
격리**와 **독립 재시작** — 은 1·2단계가 덮지 않는다. 1·2단계가 확실히 해소하는 것은 **배포
재시작으로 생기는 중단** 쪽이다.

**착수 전제** — 위 네 제약을 프로세스 밖으로 옮기는 별도 설계(공유 레이트리미터 · 발급
잠금 · 체결통보 중계 · 분산 예산 잠금) + 중복 배달·순서 보장 규약. 사용자 승인 없이
착수하지 않는다.

### 15.5 4단계 — 메시지 기반 5프로세스 (방향 기록 · 승인 전)

사용자 원안(2026-09-15)은 **메시지 도입과 주문/체결 프로세스 분리**다. 전송 수단을 맡는 두
프로세스(시세·체결 수신 WebSocket 1개 · REST 송수신 1개)를 중심에 두고, 그 위에 업무 프로세스
셋(① 시세 및 전략평가 ② 주문 ③ 체결)이 얹혀 메시지로만 오간다.

3단계(15.4)가 업무 축(피드 / 판정 / 주문)으로 갈랐다면, 4단계는 **전송 수단 축(WS / REST)으로
먼저 가르고 업무를 그 위에 얹는다.** 분할선이 달라지는 것이 핵심이고, 그 차이가 15.4 의 보류
근거 ①②③ 을 없앤다 — REST 를 쓰는 주체가 몇이든 REST 가 나가는 프로세스는 하나뿐이기 때문이다.

> 이 절은 **승인된 설계가 아니라 방향 기록**이다(1·2·3단계와 같은 지위). "할 것이다" 가 아니라
> "이렇게 하려면 무엇이 필요하다" 로 읽는다. 아래 코드 사실은 2026-09-15 HEAD 기준 실측이다.

```
        KIS WebSocket                                        KIS REST
     (시세 · 체결통보 수신)                        (주문 · 취소 · 조회 · 토큰)
              |                                                 ^
              v                                                 |
  +-----------------------------------+      +----------------------------------+
  |  W  웹소켓 프로세스               |      |  R  REST 프로세스                |
  |   수신 · 파싱 · 라우팅만          |      |   _semaphore(20) · 라벨 (18)     |
  |   approval_key 만 (tokenP 미호출) |      |   _GLOBAL_ISSUE_LOCK · 토큰 캐시 |
  |   체결통보 = 이 프로세스의 메인   |      |   재시도 · hashkey · 거부 원문   |
  +----+-------------------------+----+      +---+------------------------+-----+
       |                         |               ^                        |
    T1 | md.tick              T2 | exec.notice   | T4 request       T5    | result
       |                         |               |                        |
       v                         v               |                        |
  +--------------------+  +--------------------+ |                        |
  |  1 시세 · 전략평가 |  |  3 체결 프로세스   | |                        |
  |   ticker_prices    |<-|   주문확인         | |                        |
  |   전략 판정·사이징 |T6|   체결처리         | |                        |
  |   A-ATOMIC 잔존    |  |   trade_history    | |                        |
  +---------+----------+  +--------------------+ |                        |
            |                                    |                        |
            | T3 order.intent                    |                        |
            v                                    |                        v
  +------------------------------------------------------------------------------+
  |  2 주문 프로세스 — 전문 조합 · 시각별 거래소/호가유형 · 취소·재주문 타이머   |
  +------------------------------------------------------------------------------+
```

도식에 **그리지 않은 화살표가 하나 더 있다** — `1 시세·전략평가 -> R`. donchian
`_swing_rest_poll_loop`(60초), stale universe 가드의 `inquire_ccnl`, 조건검색, cycle272 의
`open_price_rest`(09:00:35~) 는 주문이 아니라 **판정 입력**이라 전략평가가 R 에 직접 요청해야
한다. 즉 R 은 "주문 전용 FEP" 가 아니라 **모든 프로세스가 공유하는 단일 KIS REST 게이트웨이**다.
그래야 ①②가 성립한다.

#### 15.5.1 3단계와의 관계 — 대체가 아니라 흡수다. 3단계를 먼저 거칠 이유는 없다

| 물음 | 판단 | 근거 |
|------|------|------|
| 4단계가 3단계를 대체하나 | **아니다 — 흡수한다(상위집합)** | 15.4 의 세 기둥(feed / decision / order)이 4단계의 업무 프로세스 3개와 같은 절단면이다. 4단계가 더한 것은 전송 전담 2프로세스뿐이고, 그것이 곧 15.4 가 요구한 "공유 레이트리미터 · 발급 잠금 · 체결통보 중계" 의 가장 단순한 구현이다 |
| 3단계를 먼저 해야 하나 | **아니다 — 먼저 하면 버린다** | 3단계를 4단계 없이 하면 REST·토큰을 쓰는 프로세스가 둘이라 공유 레이트리미터와 분산 발급 잠금을 **반드시 만들어야 한다**. 4단계는 그 둘을 만들지 않고 **없앤다**. 3단계를 먼저 하면 그 공유 인프라 둘이 4단계에서 폐기된다 |
| 반대로 4단계만 부분 착수는 되나 | **송수신 2프로세스만 떼는 것은 이득이 거의 없다** | ①②③은 풀리지만 크래시 격리·독립 배포는 판정/주문을 갈라야 생긴다. 둘은 한 덩어리다 |
| 1·2단계와의 관계 | **직교. 병행 가능하고 1단계는 선행 가치가 있다** | 1·2단계가 푸는 것은 "배포 재시작 중단", 4단계가 푸는 것은 "자원 단일화 + 크래시 격리". 1단계(`llm_worker`)는 워커 배포 모드와 15.7 의 함정 2건을 **매매 영향 0인 대상**으로 먼저 겪게 해 준다 — 5프로세스에서는 그 실수가 5배가 된다 |

15.4 의 ①~④ 는 여전히 참이고, 4단계는 그중 셋에 답하는 설계안이다. 아래가 그 대조다.

| 15.4 근거 | 4단계의 답 | 판정 |
|-----------|------------|------|
| ① REST 초당 20건이 프로세스 안 세마포어 | 공유 리미터를 **만들지 않는다**. REST 가 나가는 프로세스를 1개로 고정해 `_semaphore(20)`(`src/api/base.py:28`)과 라벨별 `Semaphore(18)`(`:346`)를 그 안으로 되돌린다 | 🟢 **성립(구조적)** — 단 "정확히 1개" 가 조건. R 을 2개로 늘리면 40/s 문제가 그대로 부활한다 |
| ② 토큰 발급 분당 1건이 프로세스 안 Lock | R 이 `issue()` 를 **단독 전담**하고 `.token_cache` 볼륨도 R 에만 마운트한다 | 🟢 **성립. 그리고 예상보다 가볍다** — W 가 필요한 것은 `approval_key` 뿐이고 `get_approval_key()` 는 `/oauth2/Approval` 을 httpx 로 직접 POST 해 `_GLOBAL_ISSUE_LOCK` 을 타지 않는다(`src/auth/token.py:183-197`). `src/realtime/**` 는 `get_token()` 을 한 번도 부르지 않는다(실측) — **W 는 access_token 없이 산다** |
| ③ 체결통보 메인 세션 단일 | W 가 1개면 자동 성립 | 🟡 **형식은 만족. 그러나 ③이 지키려던 것은 오히려 나빠진다** — 15.4 는 위험을 "손절 경로에 한 홉" 이라 적었는데 4단계는 체결→포지션 반영에 **두 홉**을 만든다(15.5.5) |
| ④ 매수 수량 계산 ~ 대기 등록 `await` 0건 | 사이징을 **전략평가에 남긴다** | 🔴 **성립하지만 귀속이 다르다** — 아래 |

🔴 **"주문 프로세스가 1개면 ④가 유지된다" 는 성립하지 않는다.** A-ATOMIC 이 지키는 것은
"한 이벤트 루프" 가 아니라 **"예산을 읽는 곳과 쓰는 곳이 같은 메모리"** 다. 그 상태는 전부
전략 객체 소유다 — `state.total_investment` / `state.positions` / `state.pending_buy_amounts`
(`src/engine/strategy_base.py:93-112`, 잔여 계산은 `_calc_used_funds`·`_apply_budget_limit`)와
전 전략을 가로지르는 `registry.is_ticker_blocked_for_buy()`(`src/engine/strategy_registry.py:86-98`).
주문 프로세스는 **예산을 모른다**. 따라서 ④가 성립하는 근거는 "주문 프로세스가 1개" 가 아니라
**"시세·전략평가 프로세스가 1개이고 그 안에 전 전략의 state 가 모여 있다"** 이다.

> 파생 규약 — **전략평가 프로세스는 전략별로 쪼갤 수 없다.** 7전략 7프로세스로 가르는 순간
> `is_ticker_blocked_for_buy` 와 예산 정규화가 즉시 분산 잠금 문제가 된다. 4단계에서 프로세스
> 수를 늘리면 안 되는 지점이 여기다.

⚠️ 15.4·15.5 표의 파일:줄 앵커는 사이클마다 밀린다. 앵커가 어긋나면 **심볼 이름으로 찾는다** —
제약 자체(①~④)는 넷 다 그대로 살아 있다.

#### 15.5.2 메시지 계약 — 토픽 7종

페이로드는 **지금 코드가 그 경계에서 실제로 넘기는 값**에서 뽑았다.

| 토픽 | 방향 | 페이로드(초안) | 정본 |
|------|------|----------------|------|
| T1 `md.tick` | W → 1 | `{ticker, current_price, open_price, change_rate, day_high, acml_vol, tr_id, recv_ts}` | `handler._handle_tick` 이 `_on_tick` 에 넘기는 인자 집합(`src/realtime/handler.py:629-633`). **`tr_id` 를 반드시 싣는다** — cycle294 3단계가 종목마다 채널을 가르고 매수 축 술어가 "구독 사실" 을 읽으므로, 채널 정보가 빠지면 그 게이트가 재현 불가다 |
| T2 `exec.notice` | W → 3 | `{ticker, order_no, side, price, quantity, exec_type, recv_ts}` | `_on_execution(...)` 인자(`handler.py:698-700`). 계좌 필터와 `exec_type != "2"` drop 은 **W 에 남긴다**(잡음을 큐에 올리지 않는다) |
| T3 `order.intent` | 1 → 2 | 15.5.3 | — |
| T4 `order.request` | 2 → R | `{req_id, kind: place\|cancel, ticker, side, quantity, price, ORD_DVSN, EXCG_ID_DVSN_CD, ORGN_ODNO?}` | `place_order`/`cancel_order` body 조립 직전 값(`src/api/order.py:69-88`, `:147-158`). 계좌·hashkey·TR_ID 는 R 이 채운다 |
| T5 `order.result` | R → 2 | 성공 `{req_id, order_no, order_time}` / 실패 `{req_id, rt_cd, msg_cd, msg1, http_status}` — **분류하지 않은 원문** | 15.5.4 |
| T6 `fill.applied` | 3 → 1 | `{ticker, order_no, strategy_id, side, fill_price, total_filled, ordered_qty, is_full}` | `_handle_buy_fill`/`_handle_sell_fill` 이 지금 메모리에 반영하는 것의 데이터화 |
| T7 `sub.control` | 3 → W | `{op: subscribe\|unsubscribe, ticker, priority}` | 매도 전량 체결 뒤 `_unsubscribe_if_no_other_strategy`(`order_engine.py:1910`). **사용자 도식에 없는 화살표다** |

**지금 경계는 데이터가 아니라 살아 있는 객체를 넘긴다.** "1 → 2" 에 해당하는 코드는
`order_engine.execute_buy(ticker, current_price, strategy)`(`src/engine/risk.py:749`)이고
**세 번째 인자가 전략 객체 자체**다. 매도는 `execute_sell(ticker, signal, strategy_id)` 로
문자열 id 지만 주문 쪽이 `self.registry.get(strategy_id)` 로 다시 살아 있는 객체를 잡는다.
그래서 계약 설계의 첫 일은 페이로드 나열이 아니라 **"주문 프로세스가 전략에 대해 무엇을
알아야 하는가" 를 목록화하는 것**이다 — 최소 = `{strategy_id, params.exchange,
order_exchange_clock_mode, after_market_exit_division}`.

#### 15.5.3 T3 가 수량을 담는가 — ④의 전부가 여기서 갈린다

| 안 | 내용 | 귀결 |
|----|------|------|
| A | 전략평가가 사이징하고 `quantity` 까지 보낸다 | **채택 불가.** 예산 read(전략평가)와 `pending_buys` 등록(주문)이 프로세스 경계로 갈려 A-ATOMIC 이 구조적으로 깨진다 |
| B | 전략평가가 사이징까지 하고 **완성된 수량**을 보낸다. `pending_buys`·예산도 전략평가가 소유 | **권고.** 원자 구간이 깨지는 게 아니라 전략평가 **안으로 이동**한다. `_apply_budget_limit` 이 이미 순수 동기(A-PURE 가드가 await/DB/HTTP 금지)라 이동 비용이 0이다 |
| C | 의사만 보내고 주문 프로세스가 사이징 | **기각.** `calc_buy_quantity` 는 순수 계산이 아니다 — 터틀 분기가 `self._entry_atr[ticker] = atr` 를 **스탬프**하고 그 스탬프의 존재 여부가 ATR 손절이냐 고정% 손절이냐를 가른다(루트 `CLAUDE.md` 금기). 사본에 스탬프가 남고 청산은 원본을 읽으면 터틀 랏이 **조용히 고정% 손절로 바뀐다** = 로그에도 안 보이는 매매 행위 변경 |

⇒ B안에서 주문 프로세스가 받는 것은 "이 종목 사라" 가 아니라 **"수량 N주, 거래소 X, 호가유형
D 로 접수하라"** 는 완성된 주문 파라미터다. 이것은 사용자 골자의 "전략평가로부터 메시지를
전달받아 실제 주문전문을 조합" 과 충돌하지 않는다 — **조합은 주문 프로세스가 하되 수량은 이미
정해져 온다.**

B안이 함께 옮겨야 하는 조각 둘: 사이징 **앞**의 `get_buyable`(REST — 캐시 미스 시 R 왕복)과
사이징 **뒤**의 `max_buy_qty` 클램프. 그리고 cycle287 의 시각별 거래소·호가유형 판정
(`_apply_clock`, 동기 순수 함수 · `market_state.MARKET_TABLE` 만 읽고 시각 리터럴 0건)은
**주문 프로세스에 둔다** — 전략평가가 판정하면 의사 발생과 접수 사이에 경계를 넘을 때
(15:59:45 의사 → 16:00:05 접수) 잘못된 거래소가 박힌다.

#### 15.5.4 FEP 도식의 교훈 — 순서 보장과 파티션 키

사용자가 준 증권사 FEP 도식(`docs/order_exec_architecture.png`)의 경고문:

> 주문라인이 1개 이상이면 신규/정정/취소의 거래소 접수순서가 꼬이지 않도록 **모주문번호를
> 주문라인수로 나머지 연산해서 큐배정**한다. 단순 라운드로빈으로 처리하다가 주문량이 많을 때
> 정정은 비어있는 주문라인으로, 신규는 꽉차있는 주문라인으로 넣어서 처리하면 **정정이 신규보다
> 거래소에 먼저 접수되어 원주문없음 거부**를 받을 수도 있다.

**이 규칙을 우리에게 그대로 옮길 수 없다.** 이유 둘, 둘 다 실측이다.

1. **우리는 정정을 한 번도 보내지 않는다.** `CancelType.REVISE = "01"` 은 `src/models/order.py:36`
   에 정의만 있고 `src/` 전체 참조가 **0건**이다(유일 등장 = `src/api/order.py:113` 의 기본값
   인자 `CancelType.CANCEL`). 문자 그대로의 "정정이 신규를 추월" 은 재현되지 않는다.
2. **신규 주문 시점에 모주문번호가 없다.** `order_no` 는 `place_order` 의 **응답**으로 생긴다
   (`order_engine.py:906` → `:914`). 배정 키로 쓸 값이 그 시점에 존재하지 않으므로
   "모주문번호 mod 라인수" 는 수학적으로 성립하지 않는다.

⇒ **우리 파티션 키는 `ticker` 다.** 정당화 셋 — (가) `_order_ticker`(`order_engine.py:240`)가
`order_no → ticker` 를 갖고 있어 취소도 같은 키로 환원된다 (나) 전략 간 중복 진입을
`is_ticker_blocked_for_buy` 가 이미 막으므로 ticker 는 주문 흐름의 자연 파티션 키다
(다) 코드가 이미 ticker 로 직렬화를 전제한다(`_pending_cancel_tasks: dict[str, Task]` 가 ticker 키).

**동형 위험은 실재한다 — "취소가 원주문을 앞지른다" 로 온다.** 세 쌍이 있고 셋 다 오늘은
`await` 한 줄이 순서를 지킨다:

| 쌍 | 코드 | 순서가 뒤집히면 |
|----|------|-----------------|
| 취소 → 재주문 | `_cancel_and_reorder`: `cancel_order`(`:2445`) 직후 같은 함수에서 `place_order`(`:2505`), 사이 sleep 0 | 원주문 잔량과 재주문이 **둘 다 살아** 보유의 2배를 매도한다. 잔량이 실제로 있으므로 APBK0400 도 안 난다 |
| 원주문 → 시장가 거부 폴백(매수) | `:906` 실패 → `:1035` | 같은 종목 이중 접수 |
| 원주문 → 시장가 거부 폴백(매도) | `:1305` → `:1645` | 같은 종목 이중 접수 |

⚠️ 그래서 규약 둘이 나온다. **(가) 같은 `ticker` 의 주문·취소는 같은 큐, 그 큐 안에서 FIFO.**
우선순위를 2단(주문·취소 > 폴링·스캔)으로 나누더라도 **파티션 안에서는 한 큐여야 한다** — 큐를
가르면 위 세 쌍이 바로 재현된다. **(나) 취소→재주문 쌍만은 fire-and-forget 으로 내리면 안 된다**
(응답 확인 후 진행 = RPC). `_semaphore(20)` 은 동시 20건 in-flight 를 허용하므로, 큐만으로는
같은 순간에 둘이 날아가는 것을 못 막는다.

**세 번째 교훈 — 체결 라우팅.** FEP 는 주문 전문의 회원사사용영역에 회신 큐를 심어 체결을
되돌려 받는다. 우리는 그 키를 심을 수 없다 — KIS 체결통보가 주는 것은 `order_no` 뿐이고,
그 `order_no → 어느 체결 프로세스` 매핑은 주문 프로세스가 쥐고 있다. **사용자 골자가 체결
프로세스를 1개로 그린 것은 이 점에서 옳다.**

> 다만 우리가 **버리고 있는** 자산이 하나 있다 — KIS 체결통보는 `[3] OODER_NO`(원주문번호)와
> `[12] RFUS_YN`(거부여부)을 싣고 오는데, 우리는 그 필드를 파싱하지 않는다(`handler.py:662-668`
> 에 주석만 있고 `fields[3]`·`fields[12]` 코드 참조 0건). 4단계에서 주문↔REST 가 비동기가 되면
> **체결통보 축이 거부를 알려 주는 두 번째 채널**이 될 수 있다.

#### 15.5.5 지연 — 늘어나는 항은 하나, 줄어드는 항이 더 크다

```
  오늘(0단계) — 프로세스 경계 0. 그러나 사슬 전체가 WS 수신 루프 **안**이다.
    KIS WS -> _receive_loop -> _handle_tick -> risk.on_tick
                                                  |  (이하 같은 코루틴 · await 만)
                                                  v
                          check_exit_signal -> execute_sell -> place_order
                                                  |                 |
                                    stock_master.get        hashkey + 주문
                                    (RDS 왕복 1)            (KIS 왕복 2 = 220~300ms)
                                                  |
        그 세션은 그동안 소켓을 읽지 않는다 = 전 보유 종목 틱 + 체결통보가 줄을 선다

  4단계 — 주문 발사까지 경계 3홉. 대신 수신 루프가 막히지 않는다.
    KIS WS -> W --T1--> 1 전략평가 --T3--> 2 주문 --T4--> R -> KIS
              ^                                          |
              +-- 계속 읽는다 (다른 종목 · 체결통보)     +--T5--> 2 (order_no 회신)
```

| 항 | 오늘 | 4단계 | 출처 |
|----|------|-------|------|
| 프로세스 경계 (주문 발사까지) | 0 | 3 one-way | 코드 사슬 / 사용자 골자 |
| 홉 비용 합 | 0 | **~0.07ms** | [실측] 이 머신 2프로세스 UDS+JSON, n=20,000 — RT 중앙값 0.046ms · p90 0.056 · p99 0.120 · **max 2.59** ⇒ one-way 0.023ms |
| KIS 왕복 (주문 1건 = hashkey + 주문 2회) | **220~300ms** | 같음 | [실측] 순수 왕복 110~150ms — `_workspace/analysis/2026-09-10_cycle272_U2_rest_capacity.md:229-231` |
| RDS 왕복(`stock_master.get`, 무캐시) | 1회, 인라인 | 같음(또는 캐시로 제거) | `order_engine.py:549` |
| **수신 루프 최악 blocking** | **≈3.7초** | **0** | 매도 3회 재시도의 `sleep(1s)+sleep(2s)`(`order_engine.py:218-219`, `:1769`, `:1777`) + 3×~0.25s, 전부 `risk.on_tick` 인라인 |
| 체결 → 손절 감시 무장 | 0 | 2홉 (버스가 정한다) | `order_engine.py:2042` / `risk.py:680` |

⇒ **손절 경로에서 늘어나는 항은 ~0.07ms 하나뿐이고, 줄어드는 항은 최악 3.7초다.** 즉 지연
관점의 판정은 "홉이 싸다" 가 아니라 **"오늘의 인라인 구조가 이미 더 비싸다"** 쪽이다. 그 3.7초
동안 막히는 세션이 하필 **보유 종목 전부(HIGH)와 체결통보 전부**를 싣고 있고, `websockets` 14.2
기본 `max_queue=16` 을 코드가 덮지 않으며(`websocket.py:370-372`) `ping_interval=None` 이라
KIS PINGPONG echo 까지 같은 막힌 루프 안에 있다.

**늘어나는 항이 위험해지는 조건은 둘이고, 둘 다 프로세스 수가 아니라 설계 선택이 정한다.**

1. **버스 선택.** 체결→전략평가 2홉이 UDS/Redis 면 ~0.05ms 지만, **DB 테이블 큐 + 폴링**이면
   홉당 100ms 급이다(근거는 추측이 아니라 현행 구현 — `_log_queue_consumer` 가 빈 큐에서
   `await asyncio.sleep(0.1)`, `src/main.py:161`). ⇒ **1단계가 `llm_buy_evaluations` 를 큐로
   재사용하는 선택은 주문·체결 축(하루 O(10)건)에는 그대로 이식되지만, 틱 축(하루 1.25M~1.75M
   프레임 추정, 약 25만 배)에는 이식 불가다.** 권고 조합 = 틱 = UDS 또는 Redis Pub/Sub ·
   주문·체결 = PostgreSQL outbox + LISTEN/NOTIFY(업무 쓰기와 **같은 트랜잭션**에 메시지를 넣을 수
   있는 유일한 선택) · REST RPC = Redis list/Streams.
2. **애프터마켓 16:00~20:00 의 폴백 가격.** `execute_sell` 의 애프터 분기와 `_cancel_and_reorder`
   가 `scanner.ticker_prices[ticker]` 를 읽어 `41` 지정가를 정하는데, 4단계에서 그 dict 는
   전략평가 소유이고 가격 결정은 주문 프로세스에서 일어난다. 낡은 가격이 거부를 부르면 그 거부가
   `_AFTER_EXIT_GIVEUP_THRESHOLD = 5`(`order_engine.py:77`) 예산을 깎아 **그날 밤 손절을 포기**
   시킨다(`:485`) — 손절이 아예 일어나지 않는 유일한 경로다. ⇒ **의사 메시지가 가격을 싣고 간다**
   가 유일하게 옳은 답이다(주문 프로세스가 경계 너머로 읽거나 R 에 단건 조회하는 안은 둘 다 나쁘다).

한편 4단계가 지연을 **줄이는** 자리도 있다 — 09:00 익일청산 drain(`scheduler.py:1545-1604`)은
지금 직렬 for 루프라 마지막 종목이 `N × ~300ms` 를 기다린다. 20/s 예산이 R 한 곳에 모이면
파이프라인이 가능해진다. 실측 N 은 아직 작지만(09-08 = 1건) LTV 상한가 익일청산 전환이 N 을
키우고, **N 과 갭 위험이 같은 방향으로 커진다.**

#### 15.5.6 4단계가 새로 요구하는 것 — 15.4 표에 없는 다섯 번째 제약

🔴 **주문번호 매핑 6종과 `_completed_orders` 가 프로세스 경계를 가로지른다. 그것도 양방향이다.**

| 상태 | 쓰는 쪽 | 읽는 쪽 | 4단계에서 |
|------|---------|---------|-----------|
| `_order_qty` · `_pending_buy_orders` · `_order_strategy` · `_order_ticker` · `_order_exchange`(cycle287) · `_order_division`(cycle291) — `order_engine.py:237-249`, **전부 메모리 전용** | **주문** (`place_order` 응답 직후 동기 영역 4곳: `:912-936` · `:1046-1058` · `:1314-1320` · `:1655-1663`) | **체결** (`:1846` · `:1877` · `:2005` · `:2231`) + 취소 경로 | 주문 → 체결 |
| `_completed_orders`(`:258`) | **체결** (`:2102` · `:2281`) | **주문** (`:669` 흡수기 · `:974` · `:1089` · `:1325` · `:1664`) | **체결 → 주문 (반대 방향)** |

즉 한 주문 한 건에 대해 두 프로세스가 **서로의 상태를 쓰고 지운다.** 그리고 이 교차는 이론이
아니라 **설계된 창**이다 — 루트 `CLAUDE.md` 금기 "매핑 등록은 `place_order` 응답 직후 동기 영역,
`await insert_trade` 진입 전" 의 이유가 정확히 "체결통보가 REST 응답보다 먼저 온다" 이고, 그
race 를 흡수하는 장치가 셋이나 있다(`_completed_orders` 선행 가드 ·
`_insert_pending_buy_or_absorb_race`(`:644`, 증거가 있을 때만 UniqueViolation 흡수 `:669-670`) ·
보정 INSERT).

**4단계는 이 창을 정상 경로로 만든다.** 체결통보는 W→3 의 1홉이고 주문 응답은 2→R→KIS→R→2
왕복이므로 **체결이 먼저 도착하는 것이 기본**이 된다. 그러면 위 "동기 영역" 규약은 프로세스
경계에서 **문자 그대로 지킬 수 없다**(체결이 매핑을 보려면 메시지든 DB든 `await` 가 끼므로).
선택지 셋:

| 안 | 내용 | 평가 |
|----|------|------|
| A | 주문 → 체결 push 메시지 | 순서 보장을 요구해 가장 비싸다. 증거 없는 UniqueViolation 전파 계약(`:669-670`)이 **구조적으로 오발화**한다(cycle271 이 고친 결함의 재현) |
| B | 매핑을 DB 에 영속(outbox 와 같은 트랜잭션), 체결이 `order_no` 로 조회 | **권고.** 오늘 이 매핑은 주문 프로세스가 죽으면 소실되는데, "하나가 죽어도 나머지는 산다" 가 목표인 설계에서 소실을 허용하면 자기모순이다 |
| C | 매핑 없이 버틴다 | 폴백은 이미 있다(`:1846` ticker 보정 · `:1877` 클램프 생략) **그러나 `_order_strategy` miss 의 폴백은 `"momentum"` 하드코딩**(`:2233`)이라 오귀속이 조용히 흐른다 |

> **부팅 규약의 원형은 이미 코드에 있다.** `boot_manager.py:403-411` 이 재기동 시 KIS 당일 주문
> 조회로 `_pending_buy_orders`/`_order_qty`/`_order_strategy`/`_order_ticker` 를 재구성한다.
> 4단계 규약 = **"각 프로세스는 죽었다 살아나면 메시지 로그를 되감는 게 아니라 KIS·DB 에서
> 진실을 다시 읽는다."** 우리 진실 정본은 메시지 큐가 아니라 **KIS 계좌**이기 때문이다. 이 규약의
> 부수 효과가 크다 — **브로커에 영속성이 필요 없다**(크래시 시 큐를 버리고 재조회하면 된다).

그 밖에 4단계가 새로 요구하는 계약 둘:

- **멱등키.** 🔴 `trade_history` 부분 UNIQUE(migration 029)는 **중복 주문을 막지 못한다** —
  UNIQUE 축에 `order_no` 가 들어 있어 중복 배달로 나간 두 주문은 서로 다른 ODNO 를 받아 둘 다
  정상 INSERT 된다. 그것이 막는 것은 "같은 주문의 이중 기록"(sync 핑퐁)뿐이다. `_bought_today`
  도 못 쓴다(donchian·VCP·BFB·kojiro **4전략에만** 있고 momentum·VB·LTV 에는 없다). ⇒ **생산자가
  부여하는 `intent_id` 가 exactly-once 의 유일한 근거**여야 한다. 후보 =
  `(strategy_id, ticker, KST일자, signal_seq)` — `signal_seq` 는 오늘 존재하지 않는 신규 개념이다
  (같은 종목을 하루 두 번 사는 것을 허용해야 하므로 날짜+종목만으로는 부족하다. cycle276 이 LLM
  평가 래치 키를 (전략,종목)/일 에서 **주문번호**로 바꾼 것과 같은 이유).
- **청산 큐 제거는 체결 확정 이벤트로만.** 🔴 `_drain_pending_next_day_clear` 는
  `try: await execute_sell(...)` 뒤 `finally:`(`scheduler.py:1583`)에서 **무조건** 큐와 DB 행을
  지운다. 그런데 `execute_sell` 은 주문 없이 정상 반환하는 경로가 여럿이다(`_selling` 중복 ·
  `SellRejectionTracker` TTL 차단 · 전략/포지션 없음 · 장운영시간 외 거부 · 수량 락). 오늘도
  부분적으로 틀렸고(완충 = 다음 날 `_execute_next_day_clear` 가 재수집) **4단계에서는 100% 틀린다**
  — 메시지를 큐에 넣은 시점에서 반환하므로 거부·차단이 원리적으로 반환값에 담기지 않는다.
  따라야 할 규율의 원형은 이미 있다 — `_selling` 은 `execute_sell` 진입에 add 되고
  **`_handle_sell_fill` 전량 체결에서만** discard 된다(`:2269`).

#### 15.5.7 scheduler.py 는 여섯 번째 프로세스가 아니다

`src/engine/scheduler.py` 는 3,726L 이고 `TIME_*` 상수 26개 · 상시 `asyncio.create_task` 22개를
들고 있다. 이것을 통째로 여섯 번째 프로세스로 두면 **다섯 프로세스의 내부를 아는 가장 강한
결합점**이 남는다(오늘도 `self.order_engine._order_qty.clear()`(`:3559-3562`)처럼 남의 객체
내부를 직접 만지는 곳이 여럿이다 — 프로세스로 떼면 그 전부가 원격 호출이 된다).

권고 = **둘로 분해한다.** ① `_wait_until` · `TIME_*` 상수 · 휴장일 판정 = 다섯 프로세스가 같이
import 하는 **공통 라이브러리**(`market_state` 처럼 순수) ② "오늘 날짜 확정 / 세션 단계 전환 /
21:30 정산 개시" 만 브로드캐스트하는 **얇은 시계**. 실제 작업은 소유 프로세스가 갖는다:

| 소유 | 시각 작업 · 루프 (예시) |
|------|--------------------------|
| W | `TIME_PRESUBSCRIBE`(07:59) · `_stale_watcher_loop`(120s) · `_detect_silent_inactive_sessions` · `_evaluate_universe_guard` · `_report_tick_coverage` · `_session_health_loop` |
| R | `_boot()` 토큰 선발급(기동 직후) · `TIME_STOCK_MASTER_*`(16:10/16:30/16:40) · 일봉 적재(20:30) · 유니버스 적재(20:00:05) |
| 1 | `_scan_loop`(9:30~) · `_confirm_breakout_open_prices`(9:00:05) · `_swing_buy_poll_loop` · `_swing_rest_poll_loop` · 퍼널 캡처(16:20) |
| 2 | 익일청산 8:00 · 15:20 `_force_clear_main_only` · 19:50 NXT 매수 중단 |
| 3 | `_sync_orders_to_db` · `_sync_positions_from_balance` (KIS 진실과 장부 재대조) |

⚠️ **남는 것이 문제다.** 21:30 `_reset_daily_state`(`:3532`)는 다섯 프로세스의 상태를 한 번에
지운다. 4단계에서 이건 **분산 barrier** 가 되고, 실패 규약(한 프로세스가 ack 하지 않으면 전체
롤백인가 강행인가)이 **지금 존재하지 않는다** — 단일 프로세스라 질문 자체가 없었다. 한쪽만
지워진 채 다음 날을 맞으면 그게 루트 `CLAUDE.md` 가 금기로 못 박은 "정산 후 미초기화 →
pending_buys/positions/sold_today 잔류" 다.

#### 15.5.8 제약 — 4단계를 하려면 무엇이 필요한가

| # | 제약 | 지금 상태 | 필요한 것 |
|---|------|-----------|-----------|
| A | **R·W·1·3 을 각각 정확히 1개로 고정** | 규약 없음. compose `replicas` 는 규약이 아니라 설정이다 | "uvicorn 단일 워커 필수" 를 **"매매 상태를 든 프로세스는 역할당 정확히 1개"** 로 다시 쓰고 기동/AST 가드로 봉인. **N개로 늘릴 수 있는 축은 사실상 없다**(W=③, R=①, 1=④, 3=라우팅 키 부재, 2=늘려도 R 이 1개라 이득 0) — 4단계의 목적은 **확장성이 아니라 배포·크래시 격리**다 |
| B | **기동 순서** | `healthcheck:` 가 4개 compose 파일 **전부에 0건**(실측) | 다섯이 동시에 뜨면 여러 프로세스가 lifespan 에서 `get_token()`(`src/main.py:254`)을 불러 **제약 ②를 배포마다 위반**한다. `depends_on` 만으로는 "준비 완료" 를 못 본다 ⇒ healthcheck + `condition: service_healthy` 가 필수. W 는 보유 종목을 모르는 채 구독을 시작하면 41 슬롯 경합에서 HIGH 가 밀린다 |
| C | **토큰 캐시** | `.token_cache` 볼륨. `_cache_path.write_text` 는 원자적이지 않고 파일 잠금도 없다 | R 에만 마운트. 다른 프로세스는 `TokenManager.issue()` 경로를 아예 갖지 않는다 |
| D | **즉시 반영 킬스위치** | `PUT /api/realtime/tick-channel-mode` 와 `PUT /api/strategies/{id}/params` 가 **같은 요청 안에서 엔진 메모리를 덮는다**. 그게 장중 유일한 롤백 수단이다(D6 가 재배포를 막으므로) | 대상 프로세스로 가는 RPC 가 되어야 하고, **실패 시 "폴링이 5분 뒤 반영한다" 로 조용히 강등되면 안 된다**(사고 중 5분은 손절 사각) |
| E | **FastAPI 의 거처** | 라우트 21개 중 **7개**가 `trading_scheduler` 를 직접 잡는다(실측) — 살아 있는 registry·positions·`_candidates`·`_funnel_steps` 를 읽는다 | **전략평가 프로세스에 붙인다.** 전용 API 프로세스는 그 7개를 전부 RPC 로 만드는 일이고 얻는 게 없다. ⇒ 전략평가는 매매+API+스케줄러를 겸해 **여전히 가장 무겁고 가장 재시작하기 어렵다**(4단계가 이 프로세스를 얇게 만들지는 못한다 — 그건 2단계의 일이다) |
| F | **공용 부트스트랩** | 로깅·DB풀 부트스트랩이 `src/main.py` 모듈 로드와 lifespan 에 묶여 있다. uvicorn 없는 네 프로세스가 `src/main.py` 를 import 하면 바닥이 5배가 된다 | **공용 부트스트랩 모듈 분리가 4단계의 사실상 첫 커밋** |
| G | **관측** | ① 공유 로그 파일 `TimedRotatingFileHandler`(`src/main.py:101-113`)가 `./logs` 바인드에 붙어 있어 자정 `doRollover` 를 다섯이 경합 = **조용한 로그 유실(확정 결함)** ② `DATE_FORMAT = "%Y-%m-%d %H:%M:%S"` — **밀리초 없음**(홉 지연은 수십~수백 µs 라 인과 순서 복원 불가) ③ `system_logs` 컬럼이 `id/timestamp/log_level/message` 넷 = **출처 컬럼 없음** | 프로세스별 로그 파일 · 포맷에 `%(msecs)03d` + 프로세스 라벨 · `system_logs` 에 `process`/`trace_id` 가산 컬럼. 마커 체계(고유 499종)는 **부수지 않고 확장**한다 — 마커 뒤에 `trace=` 키를 붙이면 기존 grep 은 그대로 돌고 상관관계만 새 키로 조인한다 |
| H | **배포 모드** | `BACKEND_RE` 첫 대안이 `^src/`(`tools/deploy/compose_up_changed.sh:85`). 다섯 프로세스가 `src/engine`·`src/api`·`src/db` 를 공유하므로 **경로로 프로세스를 가르려는 시도는 구조적으로 실패한다** | **단일 이미지 + 서비스별 CMD**(빌드 1회 유지) + **메시지 스키마 모듈 1개를 정본으로 두고 그 파일 해시가 바뀌면 모드를 무조건 `full`**(버전 스큐 방어). 모드는 9종이 아니라 위험 계층 4~5종 — `full`/`frontend`/`none`/`worker`/**`engine`**(전략평가+주문+체결만, W·R 무접촉). ⚠️ 15.7 의 함정 2건(오버레이가 아닌 **본체** 정의 · `env_file: .env` 를 다섯에 다 걸면 `.env` 한 글자가 전부를 재생성)이 5배가 된다 |
| I | **장애 규약** | 지금은 "살았다/죽었다" 뿐. **부분 고장은 오늘 존재하지 않는 상태다** | W·R·1 = **fail-stop**(특히 R 이 죽으면 손절이 안 나간다) / 2·3 = 조건부 fail-open(B축 영속 + 매핑 DB화가 전제, **만료 규약 필수** — 30초 전 손절 의사를 부활 후 집행하면 그건 손절이 아니라 새 거래다) |

#### 15.5.9 미해결 — 그리고 "지금 하지 말아야 할 이유"

운영 현실 축의 결론은 **"못 돈다" 가 아니라 "지금 살 값어치가 없다"** 다. 자원은 통과한다 —
UDS+JSON 왕복을 직접 재니 25,231 msg/s(p50 39µs · p99 54µs)로 틱 피크 300~600 msg/s 대비
헤드룸 10~15배이고, import 바닥도 pandas 를 전략평가에만 지우면 145MB → 약 380MB(+235MB)라
2GB 박스에서 돌 **개연성**이 있다. 막는 것은 자원이 아니라 **상금/비용 비율**이다.

🔴 **cycle248 이 이미 장중 고통의 86% 를 없앴다.** [실측] 최근 90일 커밋 363건 중 09~15시
(D6 금지 창) 작성이 125건(34%)이지만, 그 125건이 만진 **고유 파일 510개**를 배포 판정으로
분류하면 tests·docs·tools·`_workspace` 390개(76%)가 이미 `none`(backend 무접촉), frontend
49개(10%)가 `frontend` 모드다. 남은 backend 입력은 **71개(14%)** 이고, 그중 **60개(85%)가
전략평가 귀속**인데 그 프로세스는 4단계 뒤에도 재시작이 어렵다(제약 E). ⇒ **4단계가 실제로
자유롭게 만드는 것은 REST 7 + 주문·체결 1 ≈ 장중 전체 파일 터치의 1.6%** 다.

🔴 **크래시 격리라는 두 번째 상금에 대응하는 사고가 우리 이력에 0건이다.** [실측]
`_workspace/reports/` 와 `docs/HARNESS_CHANGELOG.md` 에서 OOM·프로세스 사망·컨테이너 크래시
이력을 찾으면 실질 0건이다. 실제로 기록된 사고는 전부 다른 계열이다 — KIS 세션 두절(08-31·08-12) ·
통합 채널 무송출(cycle252/293/294) · 매핑·WHERE 결손(cycle273a/b, 필옵틱스 161580 6시간 45분) ·
배포 재시작 tick blind(08-24 `_breakout_high` 소실, 이건 cycle248 이 처리했다). 즉 크래시 격리는
**우리가 겪은 적 없는 실패 모드에 대한 보험**이고, 그 보험료가 제약 A~I 다. 게다가 4단계는
**새 실패 모드(부분 고장)를 만든다.**
*(주의 — 기록 부재는 사건 부재의 증명이 아니다. `restart: unless-stopped` 가 조용히 되살린
재기동은 리포 문서에 남지 않는다.)*

**같은 고통을 더 싸게 사는 대안 넷 — 전부 프로세스 0개 추가다.**

| # | 대안 | 왜 먼저인가 |
|---|------|-------------|
| 1 | **관측 축 선행** — 공용 부트스트랩 분리 + 프로세스 라벨 · 밀리초 · `trace=` 키 + `system_logs.process`/`trace_id` 가산 컬럼 | 행위 0, 사전 승인 범위. **4단계를 하든 안 하든 필요하다** (제약 F·G) |
| 2 | **휘발 상태 복구 실증** — 보유 중 **장외** 재시작 1회로 `recompute_held_atr`·`_rederive_breakout_high`·`high_since_buy` 복구 3경로가 실제 발화하는지 확인 | D6 고통의 본체를 직접 조준한다. 초록이면 전략평가 장중 재시작 금지를 **4단계 없이** 완화할 수 있고(= 4단계의 배포 상금이 거의 사라진다), 붉으면 **4단계로도 안 풀린다**. 복구 경로는 존재하지만 조용히 실패한 이력이 있다(cycle225 A/B) |
| 3 | **scheduler 분해**(15.5.7 ①②) | cycle292 가 이미 시작한 방향이고, 4단계의 선행조건이면서 단독으로도 라인 예산·결합도를 줄인다 |
| 4 | **1단계 `llm_worker`** | 워커 배포 모드와 15.7 의 함정 2건을 **매매 영향 0인 대상**으로 먼저 겪는다 |

**착수 판단 전에 반드시 재야 할 숫자 다섯 — 지금 전부 미확인이다.**

| # | 숫자 | 재는 법 | 왜 |
|---|------|---------|-----|
| 1 | backend 실 RSS | `GET /api/system/memory`(이미 구현, `src/routes/system.py:37-47`) 장중 1회 + 장외 1회 | 이 값 없이 "+235MB 가 들어가나" 에 답할 수 없다. 위 380MB 는 **로컬 py3.13/darwin-arm64 대리 측정**이고 프로덕션(python:3.12-slim / Graviton2)과 절대값이 다르다 |
| 2 | 박스 여유 | `free -m`(MemAvailable) + `df -h` | 상주 RSS 가 2~3배가 된 상태에서 `up --build` 가 **같은 2GB 박스에서** 도는지 |
| 3 | 프로세스 크래시 이력 | `docker inspect --format '{{.RestartCount}}'` + `journalctl -k \| grep -i oom` | 크래시 격리 상금의 유무 |
| 4 | 실제 `full` 배포 횟수·시각 | GitHub Actions deploy 로그의 `mode=full` 90일 집계(`compose_up_changed.sh:181` 이 남긴다) | 위 "하루 0.83건" 은 커밋 타임스탬프 **대리 추정**이다 |
| 5 | 틱 프레임 실측 카운터 | `[dispatch_drop_summary]` 와 같은 5분 윈도우로 `frames_total` 관측 1줄(행위 0) | 지금 쓰는 1.25M/일은 포렌식의 **부하 추정치**이고 세는 마커가 없다. 버스 설계의 1차 제약이 추정 위에 서 있다 |

**남은 열린 질문 — 사용자 결정 항목.**

1. **2단계를 건너뛰나** — 15.3 이 지적한 `recommendation_engine.py:626`/`:657` 의 살아 있는 전략
   객체 직접 변이는 4단계에서 **전략평가 프로세스 안**이면 그대로 산다. 즉 4단계가 2단계의 최대
   난점을 오히려 쉽게 만든다.
2. **`/oauth2/Approval` 에 KIS 측 발급 한도가 있나** — 우리 코드·주석은 `/oauth2/tokenP` 에
   대해서만 분당 1건을 말한다(`token.py:10`, `:47`). 없다고 전제하고 W 를 독립시켰다가 재연결
   폭주 시 403 을 맞으면 **시세와 체결통보가 동시에 끊긴다**. `kis-mcp-query` 로 확인 필요.
3. **`routes/trading.py:128-142` 의 수동 매도** — 4단계에서 어느 프로세스가 받나. 이 라우트는
   주문 엔진의 private dict 를 **프로세스 밖에서 쓰는 유일한 곳**이고, 지금도 매핑 3종만 쓰고
   `_order_exchange`·`_order_division` 과 `_completed_orders` 선행 가드가 **없다**.
4. **체결 → 포지션 반영 지연의 허용 상한** — 넘기면 "체결됐는데 손절이 안 걸린 종목" 이 생기고
   그건 손절 커버리지 위반이다. 후보 = 틱 간격(정규장 활성 종목 1초 미만).

### 15.6 지금 어디까지 됐고 다음에 무엇을 하나

**지금**: 0단계(컨테이너 2개)가 가동 중이고, 1단계는 **설계 단계에서 진행 중**이다 — 코드는
아직 한 줄도 없다(`src/workers/` 없음 · `llm_worker` 서비스 없음 · migration 043 에 선점 열 없음).
2·3단계는 착수 전이다.

**다음**: 1단계의 다음 할 일은 cycle279 명세를 써서 15.2 의 **미확정 4항목**을 확정하는 것이다.
얻는 것과 위험은 각 절(15.2 · 15.3 · 15.4)에 적혀 있고, 아래 표에는 **무엇이 있어야 그 단계가
시작되는지**만 적는다.

| 단계 | 착수 조건 |
|------|-----------|
| 1 | 착수됨 (사용자 결정 2026-09-11 "1단계만 진행"). 다음 할 일 = cycle279 명세에서 15.2 의 **미확정 4항목**(선점 규약 · 요청 행 자리 · 워커 경로 · 컨테이너 정의) 확정 |
| 2 | 1단계 워커가 실전에서 안정적으로 돌 것 + 20:00 자문 auto_apply 를 엔진 측 API 로 되돌리는 설계(15.3) + 사용자 승인 |
| 3 | 15.4 ①~④ 를 프로세스 밖으로 옮기는 별도 설계 + 중복 배달·순서 보장 규약 + 사용자 승인 |
| 4 | **3단계를 흡수하므로 3단계 선행은 불필요**(15.5.1). 대신 선행 넷 = ① 관측 축(공용 부트스트랩·프로세스 라벨·밀리초·`trace=`) ② 휘발 상태 복구 실증(장외 재시작 1회) ③ scheduler 분해 ④ 1단계 실전 + 15.5.9 의 **미확인 숫자 다섯** 실측 + 15.5.8 제약 A~I 설계 + 사용자 승인 |

### 15.7 배포 모드 — 현재 3종, 1단계 이후 4종(예정)

모드 판정의 정본은 `tools/deploy/compose_up_changed.sh` 다(`.deployed_sha` 마커와 HEAD 의
누적 diff → 모드, cycle248).

| 모드 | 트리거 경로 | compose 호출 | backend 영향 |
|------|-------------|--------------|--------------|
| `full` | `BACKEND_RE` (`tools/deploy/compose_up_changed.sh:85`) — `src/`·`requirements.txt`·`Dockerfile`·compose·`deploy.yml`·`tools/deploy/` | `up --build -d --remove-orphans` (`:190`) | 재생성 |
| `frontend` | `FRONTEND_RE` (`:93`) — `frontend/`·`tools/ops/tls_stage2/` | `up --build -d --remove-orphans --no-deps frontend` (`:194`) | 무접촉 |
| `none` | 그 외(tests·`tools/test_impact`·…) 또는 마커==HEAD | `up -d --remove-orphans` (`:198`) | 빌드 없음 |
| `worker` (미구현 · 예정) | 워커 전용 경로만 | `up --build -d --remove-orphans --no-deps llm_worker` | 무접촉 **전망** |

`worker` 모드는 `frontend` 모드와 같은 원리(`--no-deps` 로 그 서비스만 재생성)로 backend
무접촉이 될 **전망**이다. 아직 코드에는 없다 — 현재 `case "$MODE"` 는 full/frontend/none
3갈래뿐이고 그 밖은 `log "internal error: unknown mode"; exit 2` 다(`:188-203`).

⚠️ **`llm_worker` 는 `docker-compose.prod.yml` 본체에 정의한다.** TLS 처럼 오버레이
(`docker-compose.tls.yml`/`tls2.yml`)에만 두면, 그 오버레이를 붙이지 않는 `full`·`none` 배포의
`--remove-orphans`(`:190`/`:198`)가 **돌고 있던 워커 컨테이너를 orphan 으로 삭제한다**.

⚠️ **지금의 `BACKEND_RE` 는 첫 대안이 `src/` 다**(`:85`) — 워커 코드를 `src/` 아래에 그대로
두면 워커 전용 변경도 `full` 로 분류돼 backend 가 재시작된다(D6 발동). 1단계가 노리는
"backend 무접촉 배포" 가 경로 설계에 달려 있다는 뜻이라, 어떤 경로를 워커 축으로 뗄지(그리고
`BACKEND_RE` 에서 어떻게 제외할지)는 cycle279 에서 정한다. 모드 판정 불가는 전부
`full`(fail-safe)이다.

---

> 본 15장은 **계획 문서**다. 1단계는 진행 중이고, 2·3·4단계는 착수 승인 전이다.
> 4단계(15.5)는 3단계를 흡수하는 **방향 기록**이며, 착수 판단에 필요한 숫자 다섯이 아직 미실측이다.
> 코드가 실제로 들어오면 각 절의 "예정" 표기를 실제 파일 경로로 바꾼다.
