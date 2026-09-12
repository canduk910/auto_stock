# 시스템 설계 문서

KIS OpenAPI 기반 주식 자동매매시스템 설계 문서.

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

### 요청 인증 흐름 (cycle243, 2026-09-03)

```
브라우저 / curl
   |
   | (1) http://<EC2>:80/…            ← 평문 HTTP (TLS 없음 = 알려진 한계 L1, 후속 F1)
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
│   │   └── kojiro.py                # 고지로 대순환 스윙 (EMA 5/20/40, 멀티데이, 2026-07 다크런치)
│   ├── risk.py              # RiskManager (on_tick → 보드 가드 → 전략별 신호 순회)
│   ├── order_engine.py      # OrderEngine (주문/체결/포지션 관리)
│   ├── scheduler.py         # TradingScheduler (KRX/NXT 통합 운영 08:00~20:00)
│   └── scanner.py           # 종목 스캔 + 공용 시세 캐시 (TICK_TR_ID=H0UNCNT0 현행 유일 활성 채널. 사이클 26 시간대별 분기는 미배선으로 cycle257 삭제 — 속성 기반 재분리는 P1-7 B)
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

## 5. 일일 매매 스케줄 시퀀스 — KRX/NXT 통합 (08:00~20:00)

```
시각     Scheduler          WebSocket         OrderEngine       KIS API
─────────────────────────────────────────────────────────────────────────
07:45  run_daily() 기상       (TIME_AUTO_START)
       │
07:55  _boot()                 (TIME_BOOT)
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
       │     ← 시간 가드 (2026-05-15 hotfix): 진입 시 >=15:30 이면 즉시 skip
       │        → 익일 청산 안전망 위임 (재시작 시점이 15:30 이후일 때 KRX 애프터
       │           SOR 시장가가 APBK3013 거부되던 사고 차단)
       │     ← VB/LTV 둘 다 POST_NXT 매수 비활성이라 keeps_post_nxt=False
       │     ← LTV check_force_clear()는 _limit_up_reached 제외 (상한가 모드 보유)
       │  └─ execute_sell(FORCE_CLEAR) ─────────────────────→ POST order
       │
15:30  KRX 메인 마감 → NXT 애프터 전환       (TIME_KRX_MAIN_CLOSE)
       │  _phase = "post_nxt_trading"
       │  _confirm_breakout_open_prices(board="post_nxt")  ← LTV 상한가 모드 보유 +
       │                                                      donchian 보유 시세 확정용
       │  구독 유지: VB/LTV 보유 종목 + donchian 보유 (positions HIGH 그룹)
       │  매수는 VB/LTV 둘 다 POST_NXT 비활성 — 손절 평가만 risk.on_tick 청산 분기로 작동
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
       │  ※ 같은 20:00 이 기동 거부 경계   (TIME_SESSION_START_CUTOFF, cycle283 D4)
       │    — 이 시각 이후 `start()` 는 거부된다. 20:00~21:30 재기동은 그날 20:30
       │      일봉 적재를 통째로 잃는다(다음 영업일 아침 immediate 가 보정하지만
       │      07:55 prepare 보다 늦다 → `[daily_head_stale]` WARNING)
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

> **DB 클라이언트 (Supabase→RDS 이전 M0~M6)**: 현재 정본 = AWS RDS PostgreSQL + `src/db/pg.py`(asyncpg 풀). 전 db 모듈이 `pg.fetch`/`pg.execute` 네이티브 async 경유. `src/db/supabase.py` 는 롤백용 병존(미사용). asyncpg 계약 = JSONB codec(raw dict) / TIMESTAMPTZ `to_char(+09:00)` 읽기 / DATE `_kst.to_date()` / NUMERIC→Decimal. 스키마(테이블 구조·마이그레이션)는 이전 전후 동일.

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

### 9.1 신규 테이블 (사이클 15~165 누적)

| 테이블 | 마이그레이션 | 용도 |
|--------|-------------|------|
| `parameter_recommendations` | 007 (+020/021/028) | 20:00 AI 자문 — `(target_date, strategy_id)` UNIQUE + `recommended_weight/code_review_notes/applied_weight/weight_reasoning/backtest_summary JSONB`. status: pending/applied/applied_auto/partial/rejected/expired |
| `daily_log_reports` | 013 (+031) | 일일 로그 분석 (cycle283: 20:05 1차 스냅샷 + 21:30 완전판이 `ON CONFLICT (target_date) DO UPDATE` 로 같은 행) — `(target_date)` UNIQUE + summary/findings/metrics JSONB + input_tokens/output_tokens/total_tokens/latency_ms/cost_estimate_usd 5 컬럼 (사이클 31) |
| `system_logs` 인덱스 | 014 | log_level + timestamp 복합 인덱스 (조회 가속) |
| `backtest_runs` | 019 | 외부 MCP 백테스트 영속화 — `(target_date, strategy_id, params_kind)` UNIQUE. status: queued/running/completed/failed/skipped |
| `market_regime_snapshots` | 022 | dkstock.cloud 매크로 일일 스냅샷 — `_boot()` 시점 1행 + `buy_blocked/computed_cash_usage_ratio/raw_response JSONB` |
| `kis_quote_accounts` | 026 | 보조 KIS 시세 수신 계좌 (UUID PK, label UNIQUE, active=true 부분 인덱스). 60s TTL 메모리 캐시 |
| `trade_history` 부분 UNIQUE | 029 | `(ticker, order_no, trade_type) WHERE order_no IS NOT NULL AND order_no != ''` — 핑퐁 INSERT 영구 차단 (사이클 30) |
| `strategy_funnel_snapshots` | 030 (+035) | 전략별 조건검색 단계별 후보/탈락 영구 추적 — UPSERT 전환 (사이클 145, snapshot_at 키 폐기) |
| `stock_master_history` | 032 (+036) | stock_master 갱신 이력 — PK (ticker, seq=0/1) + trigger 재설계 (사이클 150, 92K→4,358 row -96.9%) |
| `stock_master_daily` | 033 | KIS FHKST03010100 일봉 정규화 — PK (ticker, bas_dd) + OHLCV + change_rate + raw JSONB. 매일 16:00 KST 적재 (T-100 백필 → D-1 증분) |
| `stock_master.master_raw` | 034 | KIS 공식 일일 마스터 파일 raw JSONB + master_raw_updated_at + is_kospi200/is_kosdaq150 BOOLEAN (037, 사이클 153) |
| `pending_next_day_clear` | 038 | 익일청산큐 DB 영속화 — PK (target_date, ticker, strategy_id). 재기동 시 메모리 휘발 차단 (사이클 162) |
| `llm_buy_evaluations` | 043 | AI 매수평가(LLM) 주문 시점 기록 — PK (trade_date, account_no, ticker, order_no) + eval_kind('order'|'blocked'). 주문 1건 = 1행(성공·실패 모두), 매매 hot path 무관한 관측 계층. 열 정의 정본 = 루트 `CLAUDE.md` DB 스키마 표 (cycle276). 프로세스 분리 1단계가 이 테이블을 큐로 재사용한다 → 15.2 |

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
│   └── Settings.tsx        # 전략 비중/파라미터/자동시작/가격·거래대금 필터/매수 가드 4모드/외부 통합 토글
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

---

## 13. 사이클 5~14 추가 인프라 (2026-05-17 ~ 5/18)

본 절은 본문(1~12 섹션) 작성 이후 도입된 인프라를 요약. 상세는 `docs/HARNESS_CHANGELOG.md` 와 각 디렉토리 CLAUDE.md.

### 13.1 다중 전략 확장 (7 전략)

- 신규: `bull_flag_breakout` (눌림목 돌파, `stock_master.list_by_filter` 시총·거래대금 컷 → 폴 자동 검출 + 플래그 검출 → 09:05~13:00 돌파 + 거래량 ≥ 평균×2. 5영업일 시간 청산, 3영업일 쿨다운)
- 신규: `vcp_breakout` (미네르비니식 VCP. 일봉 100일(prepare cap) → 추세 필터 + 베이스 검출 + pullback 점진 수축 + 거래량 수축 → 09:05~14:30 돌파. **멀티데이 보유**. 7영업일 쿨다운)
- 신규: `kojiro` (고지로 대순환 스윙, 2026-07 Phase 1 다크런치 `enabled=False`. EMA 5/20/40 대순환 스테이지 + ATR/종가 밴드 1.0~4.5% → strict entry(스테이지1 + 6→1 인접 + 3선 우상향 + 종가>EMA5) → 09:05~09:30 시장가(갭업/갭다운/붕괴 스킵). 청산 = 고정%(-8%)→2ATR→스테이지3→2.5ATR 트레일. **멀티데이**. Phase1 = position_ratio, 터틀 유닛 sizing/피라미딩 = Phase 2. 지표 순수모듈 `kojiro_indicators.py`)
- **코드 정본 `_MULTIDAY_STRATEGIES = frozenset({donchian_swing, vcp_breakout, kojiro})`** — `is_next_day` 항상 False. 3 전략 모두 `strategy_base.py` 리터럴에 정적 선언 (2026-07 — vcp 동적 side-effect 추가 패턴을 리터럴로 통합)
- 상세: `src/engine/strategies/CLAUDE.md`

### 13.2 다중 KIS 계좌 + WebSocket 풀

- DB 테이블 `kis_quote_accounts` (UUID PK, label UNIQUE) — 보조 KIS 시세 수신 계좌
- `src/auth/token.py::get_token_manager(label=None)` async lazy 발급 + 격리 캐시 파일
- `src/realtime/websocket_pool.py::WebsocketPool` — 메인 + 보조 N 세션 풀
  - HIGH 우선순위 (보유/익일청산) → 메인 절대 보장 (`bypass_limit=True`)
  - LOW 우선순위 (스캐닝) → 보조 라운드로빈, 보조 가득 시 메인 fallback
  - 체결통보 (H0STCNI0/H0STCNI9) → **메인 단일 강제** (보조 시도 시 `QuoteSessionExecutionNoticeError`)
  - 총 슬롯 = 41 × (1 + N). 보조 0개 시 메인 only (회귀 0)
- `src/api/base.py::kis_get_quote / kis_post_quote` — REST 시세성 호출 풀 (path 화이트리스트 5개)
- `src/services/quote_session_health.py` — 보조 세션 health monitor (5xx/토큰 발급 실패 누적 → 자동 비활성 + DB `active=false`)
- 응답 확장: `GET /api/realtime/subscriptions` 에 `sessions[]` 배열 (label/subscribed/acked/fresh/stale/limit/ws_connected/reconnect_count)
- Frontend: `KisQuoteAccountsCard` (Settings) + `KisAccountPoolCard` (Dashboard) 30s 폴링

### 13.3 시장 레짐 + 매수 가드 (4 모드)

- `src/engine/market_regime.py` — dkstock.cloud 매크로 fetch → `MarketRegime` dataclass (regime/vix/fear_greed/buffett/cash_min)
- 4 모드 매수 가드 (DB `buy_block_mode`): `OFF` / `WARN` (로그만) / `SOFT` (`execute_buy(soft_multiplier=0.5)` — 수량 절반 축소) / `HARD` (매수 skip)
- 4 임계 OR: `regime=defensive` (toggle) / `vix > vix_threshold` / `fear_greed_score > fg_high_threshold` / `< fg_low_threshold`
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

### 13.5 AI 자문 고도화

- `parameter_recommendations` 신규 컬럼:
  - `recommended_weight` NUMERIC (자산 배정 자문 — 0.0~1.0)
  - `weight_reasoning` TEXT (비중 변경 사유, ≤1000자, 한국어, 통합 `reasoning` 과 별개)
  - `code_review_notes` TEXT (로직 자유 텍스트, ≤2000자)
  - `applied_weight` NUMERIC (apply 시 사용자 명시 토글)
  - `backtest_summary` JSONB
- `_validate_recommendations()` 5-tuple 반환 `(validated_params, reasoning, weight, notes, weight_reasoning)`
- user_payload 12 키 추가 (current_weight + peer_weights + peer_metrics + market_regime)
- `PARAM_RANGES` 화이트리스트 확장: `k_value_krx_main/k_value_nxt_pre` (0.5~2.0) + `stop_loss_main/stop_loss_pre_nxt` (-15.0~0.0) + `donchian_period` (10~60) + `long_ma_period` (20~120) + `volume_multiplier`/`atr_trail_mult` (1.0~5.0)
- `min(candidates)` 손절률 정책 — 5 키 후보 (`stop_loss_rate`/`intraday_stop_loss`/`overnight_stop_loss`/`stop_loss_main`/`stop_loss_pre_nxt`)

### 13.6 운영 안정성 (사이클 9 / 11 / 13 / 14)

- WebSocket stale watcher 임계 보수화 → 회복 강화:
  - `STALE_WATCHER_INTERVAL_SECS=120` / `STALE_FRESHNESS_SECS=60` / `MAX_STALE_RETRIES=5` (6회 이상 stale → 시간 기반 force_retry 경로 위임. 구 `STALE_FORCE_REREGISTER_AFTER` 는 2026-08-19 dead 상수로 제거)
  - 다중 안전망: F1 (재연결 1회) + `_scan_loop` (5분) + K watcher (120s) + `_resubscribe_stale_priority` (5분 우선) = 4중
- `_subscriptions` 정합성 가드 (in-flight ACK race 차단)
- `_report_tick_coverage()` 풀 통합 — 사이클 11 짝궁 누락 fix
- `list_accounts()` 60s TTL 메모리 캐시 — 폴링 race + supabase HTTP/2 stale connection 결함 차단
- 운영 점진 활성화: 보조 0개 → 1 → 5 (코드 배포 / 첫 등록 / 점진 추가). KRX 메인 시간 중 빈번한 push 자제 (재시작 race), NXT 애프터 또는 익일 boot 전 push 권장

### 13.7 사이클 6 — 로그 메뉴 통합

- 기존 `pages/LogReports.tsx` + Dashboard 의 `LogViewer` → `pages/Logs.tsx` 통합 메뉴 (`?tab=system|daily-report`)
- 시스템 로그 탭: `from_date`/`to_date` 분리 date input + 레벨 토글 + 페이징 (1-base, size 50)
- `/api/logs` 응답 확장: `{items, total, total_pages}` dict (기존 `?limit=50&level=ERROR` 하위 호환)

---

## 14. 사이클 26~165 추가 인프라 (2026-05-20 ~ 6-19)

상세는 `docs/HARNESS_CHANGELOG.md` 와 각 디렉토리 CLAUDE.md. 본 절은 본문(1~13) 이후 도입된 핵심 사실 요약.

### 14.1 사이클 26 — KRX ONLY 매매 정책 + 3 보드 + 사전 구독 마진

- 매매 정책 = KRX 메인 09:00~15:20 단독. VB/LTV `tradable_boards=("main",)` (PRE_NXT/POST_NXT 매수 비활성)
- `MarketBoard` 3 보드: `pre_nxt` (08:00~09:00) / `main` (09:00~15:40) / `post_nxt` (15:40~20:00)
- 시세 채널 시간대별 6 구간 분기 + 사전 구독 마진(50초) 종목별 원자 전환은 **108일간 미배선으로 cycle257 에서 삭제** — 실제 구독은 처음부터 `TICK_TR_ID=H0UNCNT0`(통합) 단일. 속성 기반 재분리는 P1-7 B
- 15:20 KRX 메인 강제 청산 (`_force_clear_main_only`) 영속 — VB 전량 + LTV 상한가 미도달

### 14.2 사이클 149 — 종목별 H0UNMKO0 구독 + VI/거래정지 stale 회피

- `src/api/market_operation.py` — `MARKET_OP_TR_ID=H0UNMKO0` + 10 컬럼 (TRHT_YN/VI_CLS_CODE/OVTM_VI_CLS_CODE/ISCD_STAT_CLS_CODE 등). REST 폴백 `inquire_vi_status_today` (FHPST01390000)
- `src/engine/market_operation_monitor.py` — `is_ticker_stale_excluded()` hook. 보유+익일청산+후보 합집합 (HIGH bypass + LOW cap=20)
- `stale_watcher_core` VI/halt grace 회피 + REST 폴백 부팅 1회 seed

### 14.3 사이클 150 — SUPABASE 용량 정합

- migration 036 = stock_master_history PK (ticker, seq=0/1) + trigger 재설계 → 92K→4,358 row -96.9%
- `purge_old_rows()` T-150일 retention cron 매일 16:15 KST + protected_tickers 보호
- `_purge_by_cutoff` 2-step subquery — supabase-py DELETE chain `.limit()` 미지원 silent 24일 영구 차단

### 14.4 사이클 160 — `_wait_until` 본질 복원 (HIGH 매매 안전성)

- 2 모드 분기: default 즉시 break (run_daily phase 전환) + `advance_if_passed=True` (task_loop_helper 폭주 차단)
- 사이클 152 hotfix 가 깨뜨린 본질 복원 = 6/17 15:20 강제청산 누락 사고 (알테오젠/알지노믹스) 영속 차단

### 14.5 사이클 161 — `_handle_buy_fill` 체결단가 정합

- BUY trade_history.price = KIS CNTG_UNPR (체결단가) 강제 — 사이클 147 SELL fallback chain 패턴 답습
- UniqueViolation → 강제 UPDATE chain 영속

### 14.6 사이클 162 — 익일청산큐 DB 영속화 + 동시호가 stale 회피

- migration 038 = `pending_next_day_clear` PK (target_date, ticker, strategy_id) — 재기동 시 메모리 휘발 차단
- `_boot()` 복구 chain + DB 실패 시 메모리 보존 graceful
- `SessionTracker.is_call_auction_now()` (08:30~09:00 / 15:20~15:30 = MKOP_CLS_CODE 110/121) → stale 재구독 skip

### 14.7 사이클 163 — 2차 _boot stock_master race 가드 + 5 전략 prepare 재시도 hook

- `count_active()` polling 5분 cap (10초 주기) — 사이클 158 hook 90초 부족 영속 시정
- 5 전략 (VB/LTV/donchian/BFB/VCP) prepare 0건 시 자동 재시도 hook 통일
- `_handle_buy_fill` 전량 체결 분기 3 영역 try/except 분리 — DB INSERT 실패 시 callback graceful

### 14.8 사이클 164 — 시가대기 silent 결함 시정

- `_confirm_breakout_open_prices_if_pending` 5분 주기 hook — `_scan_loop` 통합. 미확정 종목 자동 시가 확정 재시도 (idempotent + disabled skip + graceful)
- 이중 안전망 = VB `check_buy_signal` tick fallback + `_scan_loop` 5분 재시도

### 14.9 사이클 165 — docstring 보강 + CLAUDE.md 반복 단어 정리

- 6 파일 docstring 보강 (+96L) — TR_ID 분기 / msg_cd 누적 / KIS MCP 정본 fields 매핑 / 가드 계층 / 가드 매트릭스 인용
- 4 CLAUDE.md 반복 단어 30건 → 0건 정리 (의미 보존)
- 행위 변경 0 / 백엔드 풀 3,040 PASS

---

> 본 14장은 13장 이후 도입된 인프라의 요약. 14.1 (KRX ONLY 보드 전환) 영역 도식 갱신 + 14.6 (동시호가 시각 분기) 시퀀스 다이어그램은 별도 사이클로 위임.


---

## 15. 프로세스 분리 로드맵 (2026-09-11)

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

> 1단계가 "진행 중"인 근거는 **사용자 결정(2026-09-11 — "1단계만 진행")** 이다. 사이클 번호
> `cycle279` 는 예약해 둔 것이고 명세·코드·changelog 항목은 아직 없다(리포 안의 실재 최신
> 사이클은 cycle278). 2·3단계는 승인된 설계가 아니라 방향 기록이다.

### 15.1 0단계 — 현재 (가동 중)

```
  +------------------+          +-------------------------------------------+
  |  frontend        |   /api   |  backend  (uvicorn 단일 워커)             |
  |  nginx:alpine    |--------->|  scheduler / session / scanner            |
  |  SPA + BasicAuth |          |  strategies(7) -> risk -> order_engine    |     KIS WebSocket
  +------------------+          |  llm_buy_gate (AI 매수평가 — VB·LTV 만)   |<--> (시세 · 체결통보)
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
VB·LTV 두 전략의 매수 주문 직후에 LLM 이 점수를 매겨 **기록만** 하고 매수 여부는 바꾸지 않는다
(shadow). 켜져 있는 전략은 그 둘뿐이다(`volatility_breakout.py:155` · `long_tail_volatility.py:138`
의 `"llm_gate_mode": "shadow"`, 나머지 5 전략은 키 부재 = off).

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
| 워커 경로 | `src/workers/` 디렉터리는 **없다** | 워커 축 경로와 `BACKEND_RE` 제외 방식 (15.6 ⚠️) |
| 컨테이너 정의 | `docker-compose.prod.yml` 에 `llm_worker` 서비스가 **없다** | 오버레이가 아니라 **본체**에 정의 (15.6 ⚠️) |

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
> "주문 시점 기록, 주문 1건 = 1행"). 1단계는 그 기록 테이블에 "아직 채워지지 않은 행 = 작업
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
| ③ | 체결통보(H0STCNI0/H0STCNI9) **메인 세션 단일 강제** | `src/realtime/websocket_pool.py:59` `_EXECUTION_NOTICE_TR_IDS` + `:62` `_enforce_main_only_execution_notice` (보조 세션 구독 시 `QuoteSessionExecutionNoticeError` `:52`) | 체결이 다른 프로세스에 도착해 손절 경로에 한 홉이 늘어난다 |
| ④ | 매수 수량 계산 ~ 대기 등록 사이 `await` 0건 규약(A-ATOMIC) | `src/engine/order_engine.py:314`(`calc_buy_quantity`) ~ `:355`(`pending_buys.add`), 가드 `tests/unit/ast/test_budget_limit_ast.py:60` | 단일 이벤트 루프 전제가 깨져 예산·중복 판정이 분산 잠금 문제가 된다. 이 경로에서 메시지 한 건 중복 = 주문 한 건 중복 |

**예상** — 지금 설계는 틱 경로를 동기적으로 막지는 않는다. 평가를 `asyncio.create_task` 로
던지고 즉시 반환하기 때문이다(`src/engine/llm_buy_gate.py:759`, 동시 실행은 `:141`
`_SEM = asyncio.Semaphore(2)` 로 2건까지). 다만 같은 이벤트 루프와 같은 asyncpg 풀은 계속
공유하고, 3단계의 남은 동기 — 전략 판정 경로가 죽을 때 WS 피드까지 같이 죽지 않게 하는 **크래시
격리**와 **독립 재시작** — 은 1·2단계가 덮지 않는다. 1·2단계가 확실히 해소하는 것은 **배포
재시작으로 생기는 중단** 쪽이다.

**착수 전제** — 위 네 제약을 프로세스 밖으로 옮기는 별도 설계(공유 레이트리미터 · 발급
잠금 · 체결통보 중계 · 분산 예산 잠금) + 중복 배달·순서 보장 규약. 사용자 승인 없이
착수하지 않는다.

### 15.5 지금 어디까지 됐고 다음에 무엇을 하나

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

### 15.6 배포 모드 — 현재 3종, 1단계 이후 4종(예정)

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
`BACKEND_RE` 에서 어떻게 제외할지)는 cycle279 에서 정한다. 모드 판정 불가는 종전대로 전부
`full`(fail-safe)이다.

---

> 본 15장은 **계획 문서**다. 1단계는 진행 중이고, 2·3단계는 착수 승인 전이다.
> 코드가 실제로 들어오면 각 절의 "예정" 표기를 실제 파일 경로로 바꾼다.
