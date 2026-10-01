# CLAUDE.md — src/ (백엔드)

> 이력: [`docs/history/src-CLAUDE.history.md`](../docs/history/src-CLAUDE.history.md)

FastAPI + KIS OpenAPI + AWS RDS PostgreSQL (asyncpg). 진실의 원천은 하위 디렉토리 CLAUDE.md 다.

## 실행
```bash
uvicorn src.main:app --reload     # 개발 (단일 워커 필수, --workers 금지)
python -m src.main                # 직접 실행
```

## 모듈 의존 관계

`A ← B` = B 가 A 를 import 한다. 첫 블록은 계층 사이 대표 경로, 둘째 블록은 engine leaf 일부다.
둘째 블록 각 줄의 import 하는 쪽과 아래 역방향 목록은 전수다. leaf 전체·하는 일·import 계약 = `src/engine/CLAUDE.md` 「모듈 맵」 절.

```
config.py ← 모든 모듈 (settings)
auth/ ← api/base.py, realtime/websocket.py 등
api/base.py ← api/ 의 다른 모듈(kis_master·krx 제외) + engine·routes 일부
api/ ← engine/, routes/ + db/{stock_master,stock_master_daily}.py · realtime/handler.py (함수 안)
realtime/websocket.py ← realtime/websocket_pool.py (메인 세션 재사용)
realtime/handler.py ← realtime/websocket.py(set_aes_keys) · engine/scheduler.py(dispatch_message 를 WS 접속에 넘기고 콜백 3종 등록 = risk.on_tick · order_engine.handle_execution_notice · session_tracker.on_h0nxmko0)
engine/session.py ← engine/{risk,order_engine,scheduler,open_price_rest,stale_watcher_core}.py · strategies/{volatility_breakout,long_tail_volatility}.py
engine/ ← routes/ (시작/정지 = routes/trading.py)
db/pg.py (asyncpg 풀) ← db/ 전 모듈(_kst·supabase 제외) · main.py(풀 init/close) · engine/{funnel_capture,log_metrics_collector}.py · routes/market_ops.py
db/ ← engine/, routes/ + api·auth·realtime·services 일부
models/ ← api/, db/, engine/, routes/
services/ ← engine/{market_regime,backtest_*}.py · routes/{backtest,system_integrations}.py · api/base.py · main.py
middleware/api_auth.py ← main.py (최외곽 미들웨어 — MetricsMiddleware 보다 바깥)
```

```
engine/market_state.py ← engine/{tick_channel_clock,order_engine}.py · routes/market_state.py
engine/tick_channel_mode.py ← engine/{scanner,tick_channel_clock,tick_channel_switch,no_feed_registry,stale_watcher_core}.py + realtime/websocket.py, routes/realtime.py (킬스위치 — 어디서든 읽는다)
engine/tick_channel_clock.py ← engine/{scanner,risk,stale_watcher_core,tick_channel_mode,tick_channel_switch}.py, routes/realtime.py
engine/tick_channel_switch.py ← engine/stale_watcher_core.py (120초 트리거 — 유일한 실행 호출자) + engine/tick_channel_mode.py (테스트 초기화 reset_state_for_test 만)
engine/market_op_subscribe.py ← engine/scheduler.py (5줄 위임 wrapper)
engine/trading_calendar.py ← engine/{task_loop_helper,strategy_base,funnel_capture,status_exit_watch,market_unit,log_metrics_collector}.py · db/stock_master_daily.py(함수 안)
engine/funnel_capture.py ← engine/{scheduler,boot_manager}.py
engine/etf_like.py ← db/stock_master.py · engine/scanner.py(모듈 상단) + strategies/{volatility_breakout,long_tail_volatility,donchian_swing,bull_flag_breakout,vcp_breakout,kojiro}.py(함수 안)
engine/status_exit_watch.py ← engine/scheduler.py(모듈 상단) + engine/strategy_base.py · api/condition.py · routes/system_integrations.py(함수 안)
engine/daily_bar_finalize.py ← engine/boot_manager.py(함수 안)
```

역방향(engine 을 import 하는 아래 계층, 전수) = `api/condition.py` · `db/{stock_master,stock_master_daily,trade_history}.py` · `realtime/{handler,websocket,websocket_pool}.py`.
모듈 상단 import 는 `db/stock_master.py → engine/etf_like` · `realtime/{handler,websocket}.py → engine/daily_emit_cap` 둘뿐이고 나머지는 함수 안이다. 두 대상은 표준 라이브러리만 쓰는 leaf 라 순환이 없다.

## 진입점

| 영역 | 진실의 원천 |
|------|------------|
| KIS OAuth/토큰 | `src/auth/CLAUDE.md` |
| KIS REST 호출·TR_ID·Rate Limit·메트릭 | `src/api/CLAUDE.md` |
| WebSocket 시세/체결통보/H0NXMKO0 | `src/realtime/CLAUDE.md` |
| 시세 채널 리졸버 `engine/scanner.py::tick_tr_id_for` (어느 종목을 어느 채널로 구독하나 · 킬스위치 `PUT /api/realtime/tick-channel-mode`) | `src/realtime/CLAUDE.md` 「시세 채널」 절 |
| 전략·주문·리스크·스케줄러·AI자문·일일 분석 | `src/engine/CLAUDE.md` |
| RDS(asyncpg) CRUD/스키마/계약 패턴 | `src/db/CLAUDE.md` |
| FastAPI 엔드포인트 카탈로그 | `src/routes/CLAUDE.md` |
| Pydantic 응답 모델 | `src/models/CLAUDE.md` |
| API 인증(`X-API-Key`)·리포터 스코프 = `middleware/api_auth.py` | 그 파일 docstring + 루트 `CLAUDE.md` 「핵심 안전 규칙」·「환경 변수」 (전용 CLAUDE.md 없음) |
| 외부 서비스 클라이언트 = `services/` | 아래 목록 + 루트 「외부 통합」 (전용 CLAUDE.md 없음) |

`src/services/`:
- `mcp_client.py` — 백테스트 MCP 클라이언트(JSON-RPC). `KIS_MCP_ENABLED=false` 면 `call_tool` = `ConfigError`, `health_check` = `False`
- `macro_client.py` — 매크로 레짐 클라이언트(우리 `macro` 컨테이너, 인증 없음). 비활성이면 `ConfigError`. 활성 판정·변수명 유지 = 루트 「환경 변수」 `DKSTOCK_REGIME_ENABLED`
- `quote_session_health.py` — 실패가 쌓인 보조 시세 계정을 자동 비활성한다(`health_monitor`, 메인 제외). 임계 = `src/api/CLAUDE.md` 「base.py — REST 시세성 호출 풀」 절
- `exceptions.py` — `ConfigError`(설정상 제공 불가) · `ExternalAPIError`(통신 오류) · `BacktestNotSupportedError`(MCP YAML 로 표현 못 하는 전략)

## 공통 규칙 (전역)
- KIS REST 는 `api/base.py` 래퍼만 거친다 — 메인 단일 `kis_get()`·`kis_post()`(매매·잔고·체결조회) / 시세성 `kis_get_quote()`·`kis_post_quote()`(보조 풀 라운드로빈, `_QUOTE_ALLOWED_PATHS` 밖 path = `QuotePoolPathError`). Rate Limit(메인 초당 20건)·재시도(`MAX_RETRIES=3`)·토큰 갱신·메트릭이 여기서 붙는다
- TR_ID 는 실전 값으로 넘기고 모의 TR_ID 를 코드에 적지 않는다(모의 변환 = `src/api/CLAUDE.md` 「새 API 추가 절차」 3번). ⚠️ **코드 결함 의심** — KIS 명세의 `FH…` 시세 TR 은 모의 TR_ID 가 실전과 같은데(`docs/kis/domestic-stock-quote.md`), `get_tr_id` 는 vts 에서 `VH…` 로 보낸다(운영은 `real` 이라 영향은 vts 뿐)
- API 응답 래퍼 = `models/response.py::ApiResponse` `{ success, data, message }`
- **API 인증은 조용히 꺼지지 않는다** — `middleware/api_auth.py::ApiAuthMiddleware` 가 `/health` 를 뺀 전 경로를 `X-API-Key` 로 지킨다. 키 미설정·빈 문자열·비교 예외 = **401(fail-closed)**. 금기 = 루트 「핵심 안전 규칙」
- DB = `db/pg.py`(asyncpg) `pg.fetch`/`pg.execute` 경유(`src/db/CLAUDE.md`). `db/supabase.py` 는 롤백용 병존이고 런타임은 참조하지 않는다(그래도 `SUPABASE_*` 는 필수 설정 — 루트 「환경 변수」)

## 새 KIS API 추가
정본 = `src/api/CLAUDE.md` 「새 API 추가 절차」 절(스펙 찾기·래퍼 선택·TR_ID). 계층을 건너는 단계는 아래다.
⚠️ `docs/kis/*.md` 는 2026-09-11 스냅샷이다 — 09-14 제도 변경 뒤 사실은 루트 `CLAUDE.md` 「기본 진입점」 의 KIS 스펙 시간 경계 순서로 본다.
1. `api/` 함수 — 시세성이면 path 를 `_QUOTE_ALLOWED_PATHS` 에 넣는다. 매매·잔고·체결조회 path 는 넣지 않는다
2. `models/` pydantic 응답 모델 — 필드명 = 응답 JSON 키 = `frontend/src/types/` 속성명
3. 필요하면 `routes/` 엔드포인트
