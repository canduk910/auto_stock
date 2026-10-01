> 원본: `src/CLAUDE.md` · 이관: 2026-10-01

정본은 [`src/CLAUDE.md`](../../src/CLAUDE.md). 이 파일은 거기서 걷어낸 원문을
**고치지 않고** 옮겨 둔 것이다(append-only). 사이클 축으로 찾으려면
[`docs/HARNESS_CHANGELOG.md`](../HARNESS_CHANGELOG.md) 로 간다.

---

## 2026-10-01 sync-docs 압축 — 정본에서 이관

정본은 코드 import 전수 대조로 아래 서술을 다시 썼다(의존 도식 정정 · leaf 설명은 `src/engine/CLAUDE.md` 「모듈 맵」 으로 · `kis_request()` 는 코드에 없는 이름). 아래는 그 전 원문이다.

### 출처: 「모듈 의존 관계」

````
```
config.py ← 모든 모듈 (settings)
auth/      ← api/base.py, realtime/websocket.py
api/base.py ← api/order, balance, condition
api/       ← engine/, routes/
realtime/websocket.py ← realtime/websocket_pool.py (메인 세션 재사용)
realtime/handler.py ← engine/risk.py(on_tick) + engine/order_engine.py(체결통보) + engine/session.py(보드 전환)
engine/session.py ← engine/risk.py, engine/scheduler.py, strategies/* (현재 보드 query)
engine/    ← routes/trading.py (시작/정지)
db/pg.py (asyncpg 풀) ← 전 db 모듈 + engine/scheduler·boot_manager·log_analysis_engine + routes
db/        ← engine/, routes/
models/    ← 모든 모듈
middleware/api_auth.py ← main.py (최외곽 미들웨어 — MetricsMiddleware 보다 바깥)

engine/market_state.py → engine/tick_channel_clock.py (시장 시간표 파생 — 시각 리터럴 0건)
engine/tick_channel_mode.py ← engine/{scanner,tick_channel_clock,tick_channel_switch,no_feed_registry,stale_watcher_core}.py
                              + realtime/websocket.py, routes/realtime.py   (킬스위치 — 어디서든 읽는다)
engine/tick_channel_clock.py ← engine/{scanner,risk,tick_channel_switch}.py, routes/realtime.py
engine/tick_channel_switch.py ← engine/stale_watcher_core.py (120초 트리거 — 유일 호출자), routes/realtime.py
engine/market_op_subscribe.py ← engine/scheduler.py (5줄 위임 wrapper)
engine/trading_calendar.py ← engine/{task_loop_helper,strategy_base,funnel_capture,status_exit_watch}.py   (휴장일 판정 leaf — api/condition.is_trading_day 를 지연 import)
engine/funnel_capture.py ← engine/{scheduler,boot_manager}.py   (라이브 prepare 단일 입구 · 저녁 미리보기 — 8영역 import 0)
engine/etf_like.py ← db/stock_master.py · engine/scanner.py(모듈 상단) + strategies/{volatility_breakout,long_tail_volatility,donchian_swing,bull_flag_breakout,vcp_breakout,kojiro}.py(함수 안 import)
                     (ETF/ETN 판정 leaf — 표준 라이브러리만 import. db → engine 역방향은 SQL 빌더가 같은 상수를 읽어야 해서다)
engine/status_exit_watch.py ← engine/scheduler.py(모듈 상단) + engine/strategy_base.py · api/condition.py · routes/system_integrations.py(함수 안 지연 import)
                              (관리종목·단기과열 보유 청산 + 당일 매수 차단 leaf — 최상위 import 는 표준 라이브러리뿐. condition.py 관측 훅의
                               api → engine 역방향은 같은 파일 fetch_rising_stocks 의 scanner 지연 import 와 같은 선례다)
engine/daily_bar_finalize.py ← engine/boot_manager.py(함수 안 import)
                              (전일 잠정 봉 확정 leaf — 최상위 import 는 db/{positions,stock_master_daily,system_config}·db/_kst 뿐,
                               api/condition 은 함수 안 지연 import. 8영역·scheduler·scanner·strategies import 0)
engine/daily_emit_cap.py ← api/condition.py(함수 안 지연 import — `[prev_close_overwrite]` 1회/일 cap. api → engine 역방향만 적는다)
```

> **시세 채널 리졸버 (cycle293·294, 2026-09-14)** — 어느 종목을 어느 WebSocket 채널로 구독할지는
> `engine/scanner.py::tick_tr_id_for(ticker, *, priority, now)` 하나가 정한다. 시각축은
> `engine/tick_channel_clock.py`(시장 시간표 파생, **시각 리터럴 0건**), 살아 있는 구독의 전환은
> `engine/tick_channel_switch.py`, 킬스위치는 `engine/tick_channel_mode.py` +
> `PUT /api/realtime/tick-channel-mode` 다. 상세 = `src/realtime/CLAUDE.md` 「시세 채널」 절

> **예정 (cycle279 프로세스 분리 1단계, 코드 아직 없음)** — `engine/llm_buy_gate` 가
> `db/llm_buy_evaluations` 에 요청 행을 남기면 별도 프로세스 `llm_worker` 가 그 행을 선점해 채운다.
> 위 블록의 `←`(import 방향)가 아니라 DB 를 거치는 데이터 흐름이다. 워커는 `api/`·`auth/`·`realtime/` 을
> import 하지 않는다. 상세 = `docs/architecture.md` 15.2
````

### 출처: 「진입점」 (표의 마지막 두 행)

````
| API 인증(`X-API-Key`)·리포터 스코프 | `src/middleware/api_auth.py` docstring + 루트 `CLAUDE.md`(핵심 안전 규칙 · 환경 변수) — **전용 CLAUDE.md 없음** |
| 외부 서비스 클라이언트(백테스트 MCP·매크로) | `src/services/` + 루트 `CLAUDE.md`(외부 통합) — **전용 CLAUDE.md 없음** |
````

### 출처: 「공통 규칙 (전역)」

````
- 모든 KIS REST는 `api/base.py::kis_request()` 경유 (Rate Limit 20/s, 자동 재시도, 토큰 갱신, 메트릭)
- TR_ID는 `settings.get_tr_id("실전TR_ID")` — 하드코딩 금지 (실전 T → 모의 V 자동 변환, FH 접두사는 동일)
- API 응답 래퍼: `models/response.py::ApiResponse` `{ success, data, message }`
- **API 인증은 조용히 꺼지지 않는다** — `middleware/api_auth.py::ApiAuthMiddleware` 가 `/health` 를 뺀 전 경로를
  `X-API-Key` 로 지킨다. 키 미설정·빈 문자열·비교 예외는 전부 **401(fail-closed)**. 상세·금기는 루트 `CLAUDE.md`
- DB 접근은 `db/pg.py` (asyncpg) 네이티브 async — `pg.fetch`/`pg.execute` 경유 (`src/db/CLAUDE.md` 상세). `src/db/supabase.py` 는 롤백용 병존(미사용)
````

### 출처: 「새 KIS API 추가」

````
1. `docs/kis/README.md`에서 스펙 파일 확인 → TR_ID/URL/요청·응답
2. `api/` 하위에 함수 추가 (반드시 `kis_request()` 사용)
3. `models/`에 응답 모델 추가 (pydantic)
4. 필요 시 `routes/`에 엔드포인트 추가
````

---

## 2026-10-02 sync-docs 압축 2차 — 정본에서 이관

정본을 줄이면서 TR_ID 모의 변환 상세와 「새 KIS API 추가」 의 스펙·래퍼 단계는 `src/api/CLAUDE.md` 「새 API 추가 절차」 절 링크로,
`llm_worker` 인용 블록은 루트 「디렉토리 역할」(`src/workers/` → `docs/architecture.md` 15.2) 링크로 대체했다. 시세 채널 리졸버 인용 블록은
「진입점」 표의 한 행으로 옮겼다. engine leaf 블록(import 하는 쪽 전수)·`docs/kis` 스냅샷 경고·handler 콜백 3종 이름은 2차 검증 지적으로
정본에 다시 남겼다 — `src/engine/CLAUDE.md` 「모듈 맵」 에는 importer 전수 목록이 없기 때문이다. 아래는 그 전(1차 반영본) 원문이다.

### 출처: 「모듈 의존 관계」

````
`A ← B` = B 가 A 를 import 한다. 첫 블록은 계층 사이 대표 경로다. engine leaf 블록은 leaf 일부만 적는다.
그 블록 각 줄의 import 하는 쪽 목록과 아래 역방향 목록은 전수다.
leaf 전체 목록과 각 leaf 가 하는 일·import 계약은 `src/engine/CLAUDE.md` 「모듈 맵」 절이 정본이다.

```
config.py ← 모든 모듈 (settings)
auth/ ← api/base.py, realtime/websocket.py 등
api/base.py ← api/ 의 다른 모듈(kis_master·krx 제외) + engine·routes 일부
api/ ← engine/, routes/ + db/{stock_master,stock_master_daily}.py · realtime/handler.py (함수 안)
realtime/websocket.py ← realtime/websocket_pool.py (메인 세션 재사용)
realtime/handler.py ← realtime/websocket.py(set_aes_keys) · engine/scheduler.py (dispatch_message 를 WS 접속에 넘기고 콜백 3종 등록 = risk.on_tick · order_engine.handle_execution_notice · session_tracker.on_h0nxmko0)
engine/session.py ← engine/{risk,order_engine,scheduler,open_price_rest,stale_watcher_core}.py · strategies/{volatility_breakout,long_tail_volatility}.py
engine/ ← routes/ (시작/정지 = routes/trading.py)
db/pg.py (asyncpg 풀) ← db/ 전 모듈(_kst·supabase 제외) · main.py(풀 init/close) · engine/{funnel_capture,log_metrics_collector}.py · routes/market_ops.py
db/ ← engine/, routes/ + api·auth·realtime·services 일부
models/ ← api/, db/, engine/, routes/
services/ ← engine/{market_regime,backtest_*}.py · routes/{backtest,system_integrations}.py · api/base.py · main.py
middleware/api_auth.py ← main.py (최외곽 미들웨어 — MetricsMiddleware 보다 바깥)
```

engine leaf (일부 — 각 줄의 import 하는 쪽은 전수):
```
engine/market_state.py ← engine/{tick_channel_clock,order_engine}.py · routes/market_state.py
engine/tick_channel_mode.py ← engine/{scanner,tick_channel_clock,tick_channel_switch,no_feed_registry,stale_watcher_core}.py
                              + realtime/websocket.py, routes/realtime.py   (킬스위치 — 어디서든 읽는다)
engine/tick_channel_clock.py ← engine/{scanner,risk,stale_watcher_core,tick_channel_mode,tick_channel_switch}.py, routes/realtime.py
engine/tick_channel_switch.py ← engine/stale_watcher_core.py (120초 트리거 — 유일한 실행 호출자)
                                + engine/tick_channel_mode.py (테스트 초기화 reset_state_for_test 만)
engine/market_op_subscribe.py ← engine/scheduler.py (5줄 위임 wrapper)
engine/trading_calendar.py ← engine/{task_loop_helper,strategy_base,funnel_capture,status_exit_watch,market_unit,log_metrics_collector}.py · db/stock_master_daily.py(함수 안)
engine/funnel_capture.py ← engine/{scheduler,boot_manager}.py
engine/etf_like.py ← db/stock_master.py · engine/scanner.py(모듈 상단) + strategies/{volatility_breakout,long_tail_volatility,donchian_swing,bull_flag_breakout,vcp_breakout,kojiro}.py(함수 안 import)
engine/status_exit_watch.py ← engine/scheduler.py(모듈 상단) + engine/strategy_base.py · api/condition.py · routes/system_integrations.py(함수 안 지연 import)
engine/daily_bar_finalize.py ← engine/boot_manager.py(함수 안 import)
```

역방향(engine 을 import 하는 아래 계층, 전수) = `api/condition.py` · `db/{stock_master,stock_master_daily,trade_history}.py` ·
`realtime/{handler,websocket,websocket_pool}.py`. 모듈 상단 import 는 `db/stock_master.py → engine/etf_like`(SQL 빌더가 같은 판정 상수를 읽는다)와
`realtime/{handler,websocket}.py → engine/daily_emit_cap` 뿐이고, 두 대상은 표준 라이브러리만 import 하는 leaf 라 순환이 없다. 나머지는 함수 안 import 다.

> **시세 채널 리졸버** — 어느 종목을 어느 WebSocket 채널로 구독할지는 `engine/scanner.py::tick_tr_id_for(ticker, *, priority, now)` 하나가 정한다.
> 킬스위치 = `PUT /api/realtime/tick-channel-mode`. 상세 = `src/realtime/CLAUDE.md` 「시세 채널」 절

> `llm_worker`(프로세스 분리 1단계)는 아직 코드가 없다. DB 를 거치는 데이터 흐름과 import 제약(`api/`·`auth/`·`realtime/` 0건)은
> `docs/architecture.md` 15.2 가 정본이다.
````

### 출처: 「진입점」 (`src/services/` 목록)

````
`src/services/` 모듈:
- `mcp_client.py` — 외부 백테스트 MCP 클라이언트(JSON-RPC). `KIS_MCP_ENABLED=false` 면 `call_tool` = `ConfigError`, `health_check` = `False`
- `macro_client.py` — 매크로 레짐 클라이언트(우리 `macro` 컨테이너, 인증 없음). 비활성이면 `ConfigError`. 활성 판정·변수명 유지 = 루트 `CLAUDE.md` 「환경 변수」 `DKSTOCK_REGIME_ENABLED`
- `quote_session_health.py` — 실패가 쌓인 보조 시세 계정을 자동 비활성한다(`health_monitor`, 메인 제외). 임계·호출 지점 = `src/api/CLAUDE.md` 「base.py — REST 시세성 호출 풀」 절
- `exceptions.py` — 공용 예외 `ConfigError`(설정상 제공 불가) · `ExternalAPIError`(통신 오류) · `BacktestNotSupportedError`(MCP YAML 로 표현 못 하는 전략)
````

### 출처: 「공통 규칙 (전역)」

````
- KIS REST 는 `api/base.py` 래퍼만 거친다 — `kis_get()`·`kis_post()`(메인 단일: 매매·잔고·체결조회) 또는 `kis_get_quote()`·`kis_post_quote()`(시세성: 보조 풀 라운드로빈, `_QUOTE_ALLOWED_PATHS` 밖 path 는 `QuotePoolPathError`). Rate Limit(메인 초당 20건)·재시도(`MAX_RETRIES=3`)·토큰 갱신·메트릭이 여기서 붙는다
- TR_ID 는 **실전 값**으로 넘기고 모의 TR_ID 를 코드에 적지 않는다. 모의(`KIS_ENV=vts`) 변환 함수는 `settings.get_tr_id()`(첫 글자 → `V`)이고, `TokenManager.build_headers` 가 메인·시세 풀 두 경로의 모든 요청 헤더에 적용한다(주문·잔고 모듈의 직접 호출과 겹쳐도 결과가 같다)
- KIS 명세에서 `FH…` 시세 TR 은 모의 TR_ID 가 실전과 같다(`docs/kis/domestic-stock-quote.md` — 예 `FHKST01010100`). `get_tr_id` 는 접두사를 가리지 않아 vts 에서 `VH…` 로 나간다 — **코드 결함 의심**(운영은 `real` 이라 영향은 vts 뿐이다)
- API 응답 래퍼: `models/response.py::ApiResponse` `{ success, data, message }`
- **API 인증은 조용히 꺼지지 않는다** — `middleware/api_auth.py::ApiAuthMiddleware` 가 `/health` 를 뺀 전 경로를 `X-API-Key` 로 지킨다. 키 미설정·빈 문자열·비교 예외는 전부 **401(fail-closed)**. 금기 = 루트 `CLAUDE.md` 「핵심 안전 규칙」 의 API 인증 항목
- DB 접근은 `db/pg.py`(asyncpg) 네이티브 async — `pg.fetch`/`pg.execute` 경유(상세 `src/db/CLAUDE.md`). `db/supabase.py` 는 롤백용 병존이고 런타임은 참조하지 않는다. 단 `SUPABASE_URL`·`SUPABASE_KEY` 는 `config.py` 의 필수 필드라 비우면 기동이 실패한다(루트 `CLAUDE.md` 「환경 변수」)
````

### 출처: 「새 KIS API 추가」

````
1. `docs/kis/README.md` 에서 스펙 파일을 찾는다(TR_ID·URL·요청·응답). ⚠️ `docs/kis/*.md` 는 2026-09-11 스냅샷이다 — 09-14 제도 변경 뒤 사실은 루트 `CLAUDE.md` 「기본 진입점」 의 KIS 스펙 시간 경계 순서로 본다
2. `api/` 에 함수를 추가한다 — `kis_get()`/`kis_post()`, 시세성이면 `kis_get_quote()`(path 를 `_QUOTE_ALLOWED_PATHS` 에 넣는다. 매매·잔고·체결조회 path 는 넣지 않는다)
3. `models/` 에 응답 모델(pydantic)을 추가한다 — 필드명 = 응답 JSON 키 = `frontend/src/types/` 속성명
4. 필요하면 `routes/` 에 엔드포인트를 추가한다
````
