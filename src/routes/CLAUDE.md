# CLAUDE.md — src/routes/ (FastAPI 라우트)

프론트엔드에 데이터를 제공하는 REST API 엔드포인트.

## 엔드포인트 목록

| Method | URL | 파일 | 설명 |
|--------|-----|------|------|
| POST | `/api/trading/start` | trading.py | 자동매매 시작 |
| POST | `/api/trading/stop` | trading.py | 자동매매 정지 |
| POST | `/api/trading/restart` | trading.py | 자동매매 재기동 |
| POST | `/api/trading/manual-sell` | trading.py | 수동 매도 (시장가) |
| GET | `/api/trading/status` | trading.py | 현재 상태. `?include=system,holdings,orders,scan,strategies` csv로 sub-section만 슬림 응답 (미지정/`all`은 전체). **사이클 18 (2026-05-19) — `strategies[*].tradable_boards: list[str]`** 추가 (DEFAULT_TRADABLE_BOARDS 또는 params.tradable_boards). ScanMonitor "돌파 (대기)" 라벨 분기 근거 |
| GET | `/api/trading/positions` | trading.py | 보유 포지션 상세만(BalanceTable 전용 분리) |
| GET | `/api/trading/orders` | trading.py | 주문 추적(pending_buys/fills/pending_cancels)만 분리 |
| GET | `/api/balance` | balance.py | 잔고 (예수금 + 보유종목, 0수량 제외). J1(2026-05-11): 각 holding 에 `stock_master.get(ticker)` join → `nxt_tradable / krx_halted / excg_dvsn_cd` 3필드 노출(Optional, 캐시 miss/예외 시 None) |
| GET | `/api/balance/buyable` | balance.py | 매수 가능 금액 |
| GET | `/api/history?page=&size=` | history.py | 거래 내역 (페이징, 종목명/주문번호 포함) |
| GET | `/api/history/pnl?page=&size=&strategy=&ticker=` | history.py | 매매손익 — 매수/매도 페어 1행 (가중평균). 보유 중은 open 페어 (미실현 손익은 ticker_prices 현재가 사용) |
| GET | `/api/performance/summary` | performance.py | 실적 요약 |
| GET | `/api/performance/daily` | performance.py | 일별 실적 (실현손익 기반 일별 수익률 + TWR 누적 + 외부 입출금) |
| POST | `/api/performance/recompute` | performance.py | trade_history 기반 daily_performance 전체 소급 재계산 (멱등) |
| GET | `/api/strategies` | strategies.py | 전략 목록 + 비중 + 상태 + 타겟가 |
| PUT | `/api/strategies/weights` | strategies.py | 전략별 비중 수정 (매수금액 하한선 검증) |
| PUT | `/api/strategies/{id}/params` | strategies.py | 전략 파라미터 수정 (DB 영속화) |
| GET | `/api/strategies/system/auto-start` | strategies.py | 자동 매매 설정 조회 |
| PUT | `/api/strategies/system/auto-start` | strategies.py | 자동 매매 설정 변경 |
| GET | `/api/strategies/system/cash-usage-ratio` | strategies.py | 매매 가용 자금 비율 조회. 응답 `{ratio: float}`, 기본 1.0 |
| PUT | `/api/strategies/system/cash-usage-ratio` | strategies.py | 매매 가용 자금 비율 변경. body `{ratio: float}` `[0.0, 1.0]`. 5% 단위 자동 보정, 응답에 보정된 ratio 포함. 다음 영업일 `_boot()` 부터 반영. 범위 외는 400 |
| GET | `/api/logs` | logs.py | 시스템 로그 조회. **사이클 6(2026-05-17)** — 쿼리 파라미터 확장: `?from_date=YYYY-MM-DD&to_date=YYYY-MM-DD&level=ERROR&page=1&size=50`. 응답 `data` 는 `{items, total, total_pages}` dict. 기존 `?limit=50&level=ERROR` 하위 호환 보존(`limit` 단독은 `size` 흡수). 422: `from_date>to_date` / `page<1` / `size>200`. KST 강제 — 백엔드 `f"{date}T00:00:00+09:00"` ~ `T23:59:59.999999+09:00` 범위 비교 |
| GET | `/api/logs/search` | logs.py | 시스템 로그 키워드 검색. **사이클 6 통합(2026-05-20)** — `?q=...&level=INFO\|WARNING\|ERROR\|CRITICAL\|ALL&start=ISO&end=ISO&limit=1~1000`. `q` 는 `min_length=1` 필수 (빈 문자열 422). `level=ALL` 또는 None 은 무필터. ILIKE substring 매칭 (대소문자 무시) `message LIKE '%q%'`. 응답 `data` 는 `{logs:[{id,timestamp,log_level,message},...], total, has_more}` dict. `has_more=true` 면 limit 초과 — UI 가 "키워드 좁히기" 안내. 검색 시 페이징 비활성 (단일 응답) — `total>len(logs)` 시 키워드 추가 좁히기 또는 limit 상향 |
| GET | `/api/recommendations` | recommendations.py | 전략수정 AI자문 목록 (최근 30일, 신규+이력 통합) |
| GET | `/api/recommendations/{id}` | recommendations.py | 단일 자문 상세 |
| POST | `/api/recommendations/{id}/apply` | recommendations.py | 선택한 키만 전략 파라미터에 적용 (status: pending/partial → applied/partial). **J4(2026-05-12)** — body 신규 옵션 `apply_weight: bool=False` 추가. true 면 `recommended_weight` 가 `strategy_config.weight` 로 반영(`save_weights`) + `applied_weight` 트래킹. recommended_weight=null 인데 apply_weight=true 면 거부. params 없이 weight 단독 적용 가능. `allocate_funds` 즉시 재호출 안 함 (다음 _boot 반영) |
| POST | `/api/recommendations/{id}/reject` | recommendations.py | 자문 전체 거절 (status → rejected) |
| GET | `/api/log-reports?days=30` | log_reports.py | 일일 로그 분석 리포트 목록 (신규순) |
| GET | `/api/log-reports/{YYYY-MM-DD}` | log_reports.py | 단일 영업일 리포트 상세 |
| POST | `/api/log-reports/run` | log_reports.py | 수동 트리거 — 즉시 분석 실행 (당일 1건만, 중복 방지) |
| GET | `/api/system/memory` | system.py | 프로세스 메모리(psutil RSS/VMS/threads/files) + (옵션) tracemalloc top 20 |
| GET | `/api/system/metrics` | system.py | 엔드포인트별 응답시간 분포 p50/p95/p99 (최근 1024개 샘플) |
| POST | `/api/system/metrics/reset` | system.py | metrics 누적 샘플 초기화 (실험 베이스라인 리셋) |
| GET | `/api/realtime/subscriptions` | realtime.py | WebSocket 구독 슬롯 사용현황 진단 (G2, 2026-05-12). `total/acked/fresh_60s/stale_60s/limit/tickers(subscribed/acked/fresh/stale, 모두 sorted)/reconnect_count/ws_connected/sessions[]`. **사이클 18 (2026-05-19) — `last_tick_map: dict[ticker, ISO_KST\|null]`** 추가. **사이클 35 (2026-05-21) — `sessions[*].tickers_detail`** 추가 (cap 200, stale 우선 정렬, 종목당 `ticker/ticker_name/stale/last_tick/retries/last_resub`). **사이클 37 (2026-05-21) — `tickers_detail` 에 `last_cntg_hour` / `today_volume` 추가** (KIS `inquire_ccnl` 캐시 TTL 5분 + cap 20, 미스 → null). UI 가 WS tick 시각과 KIS 실제 체결시각 비교하여 "WS 구독 의심" 자동 진단 (5분+ 차이 amber 강조). KIS 측 슬롯 조회 API 미존재 → 우리 측 추적 노출 |
| POST | `/api/realtime/resubscribe` | realtime.py | 60s 미수신(stale) TICK 종목 즉시 일괄 재구독 (J2, 2026-05-12). `_subscriptions` 보존 + `_send_subscribe(TICK_TR_ID, t, subscribe=True)` 만 호출(50ms sleep). 응답 `{resubscribed, tickers}` (sorted). WebSocket 끊김 시 400. F1 자동 재구독(재연결 60s 후)과 별개의 운영자 수동 트리거. 영구 로그 `[ws_manual_resubscribe] count=N tickers=[...]` |
| GET | `/api/integrations/dkstock-regime` | system_integrations.py | 외부 매크로 서버 활성 여부 조회 (사이클 5, 2026-05-17). 응답 `{enabled, source: 'db'\|'env', env_value, db_value}` — DB 우선 / .env fallback. db_value=null 이면 source='env' |
| PUT | `/api/integrations/dkstock-regime` | system_integrations.py | 외부 매크로 서버 활성 토글 (사이클 5). body `{enabled: bool}`. 활성화(true) 시 `asyncio.create_task(_refresh_market_regime_and_persist_safely())` 백그라운드 fetch 발화. 비활성화 시 메모리 regime empty reset(매수 가드 즉시 해제). DB 갱신 실패는 500. 매크로 fetch 실패는 graceful — toggle 자체는 성공 |
| GET | `/api/integrations/kis-mcp` | system_integrations.py | 외부 백테스트 서버 활성 여부 조회 (사이클 5). 응답 구조 동일 |
| PUT | `/api/integrations/kis-mcp` | system_integrations.py | 외부 백테스트 서버 활성 토글 (사이클 5). 즉시 fetch 안 함 — 백테스트는 자문 시점(20:00) 발화 |
| GET | `/api/integrations/auto-regime-adjust` | system_integrations.py | 매크로 레짐 → cash_usage_ratio 자동 갱신 토글 조회 (사이클 5 통합 위치). 사이클 2 의 `auto_regime_adjust` 키 활용 — 라우트만 통합 |
| PUT | `/api/integrations/auto-regime-adjust` | system_integrations.py | 매크로 레짐 자동 갱신 토글 (사이클 5). 다음 영업일 _boot 부터 반영. 기존 `/api/market-regime/auto-adjust` 와 동일 동작(어느 쪽 사용해도 무방, 새 라우트는 Settings UI 통합 위치) |
| GET | `/api/integrations/buy-block` | system_integrations.py | 매수 가드 현재 상태 (사이클 8, 2026-05-18). 응답 `{mode: 'OFF'\|'WARN'\|'SOFT'\|'HARD', thresholds:{vix_threshold, fg_high_threshold, fg_low_threshold, defensive_enabled}, blocked, reasons:[], soft_multiplier}`. blocked=현재 가드 발동 여부 (mode 무관, 임계 OR 평가) / reasons=발동 사유 UI 표시 |
| PUT | `/api/integrations/buy-block` | system_integrations.py | 매수 가드 부분 갱신 (사이클 8). body `{mode?, vix_threshold?, fg_high_threshold?, fg_low_threshold?, defensive_enabled?}`. Pydantic 422: mode 외 값 / VIX 범위 [10,50] 외 / FG_high [50,100] 외 / FG_low [0,50] 외. DB 갱신 실패 500. 다음 매수 신호부터 즉시 반영 |
| GET | `/api/integrations/quote-accounts?active_only=false` | kis_quote_accounts.py | 보조 KIS 시세 수신 계좌 목록 (사이클 7-A, 2026-05-17). 응답 `{accounts:[{id,label,app_key,app_secret_masked,kis_env,active,created_at,updated_at}]}`. **app_secret 평문 절대 노출 안 함** (마스킹 `****1234`) |
| POST | `/api/integrations/quote-accounts` | kis_quote_accounts.py | 보조 계좌 등록 (사이클 7-A). body `{label, app_key, app_secret, kis_env:'real'\|'vts'}`. 201/409(label 중복)/422(빈 값)/500. 매매/잔고 활용 0 — 시세 수신 풀에만 등록 |
| PUT | `/api/integrations/quote-accounts/{id}` | kis_quote_accounts.py | active 토글 / label 수정 (사이클 7-A). body `{active?, label?}`. 200/404/409. app_key/app_secret 수정 미지원(보안 감사 추적성 — 삭제 후 재등록) |
| DELETE | `/api/integrations/quote-accounts/{id}` | kis_quote_accounts.py | 계좌 제거 (사이클 7-A). 200/404 |
| GET | `/api/strategy-funnel?strategy_id=&target_date=` | strategy_funnel.py | **사이클 34 (2026-05-21)** — 특정 영업일 + 전략의 단계별 후보/탈락 종목 (`step_no` ASC). 응답: `{strategy_id, target_date, snapshots:[{step_no, step_name, survived_count, excluded_count, survived_tickers, excluded_sample}]}` |
| GET | `/api/strategy-funnel/recent?strategy_id=&days=7` | strategy_funnel.py | 최근 N영업일 추이 (사이클 34) |
| POST | `/api/strategy-funnel/snapshot` | strategy_funnel.py | 수동 trigger — 각 전략 `get_scan_stats()` + `get_scanned_tickers()` 호출해 최종 단계 (`step_no=99`) snapshot 즉시 생성 (사이클 34). 단계별 ticker 캡처 자동 hook 은 후속 사이클 |
| POST | `/api/stock-master/refresh-universe` | stock_master.py | **사이클 90 (2026-06-09)** — universe 즉시 trigger 수동 발화 + asyncio.Lock 동시 호출 차단 (409 Conflict). **사이클 110 (2026-06-11) 시정**: 사이클 101 (Q68=A+Q69=B) `fetch_top_500_universe` + `_universe_eager_refresh_loop` 폐기 시점에 import 동행 시정 누락 silent 결함 (사이클 101~108 8 사이클 동안 발견 0건). `from src.engine.scanner import _full_universe_load_once` 단일 호출. **사이클 127 (2026-06-13) — fire-and-forget 전환**: `FastAPI BackgroundTasks` 사용 (response 전송 *후* schedule, axios 디폴트 timeout silent 결함 영구 차단). asyncio.Lock 폐기 → `refresh_progress.is_running("universe")` state 기반 가드. 응답 schema 변경 `{status: "started", task_key: "universe"}`. message: `"universe refresh 시작 — 진행 상황은 /api/stock-master/refresh-progress 폴링"`. 200/409 Conflict (running 중) |
| POST | `/api/stock-master/basics/refresh` | stock_master.py | **사이클 126 (2026-06-13)** — KIS CTPF1002R + FHKST01010100 매스 보강 즉시 trigger. KRX 1차 폴백에서 `nxt_tradable=False`/`krx_halted=False`/`admin_item=False` 하드코딩 결함 시정 (매매 hot path lazy 호출에만 의존하던 영역 일일 1회 매스 갱신 의무). 2,697 종목 × ~100ms ≈ 13분 소요. 자동 task = scheduler `TIME_STOCK_MASTER_BASICS_REFRESH=16:10 KST` + start() 직후 1회. **사이클 127 — fire-and-forget BackgroundTasks 전환**. 응답 `{status: "started", task_key: "basics"}`. 200/409 |
| POST | `/api/stock-master/daily/refresh` | stock_master.py | **사이클 126** — KIS FHKST03010100 일봉 즉시 적재 trigger. `_stock_master_daily_load_once()` 호출 (사이클 122 일봉 자동 task 와 동일 함수). **사이클 127 — fire-and-forget BackgroundTasks 전환**. 응답 `{status: "started", task_key: "daily"}`. 200/409 |
| GET | `/api/stock-master/refresh-progress` | stock_master.py | **사이클 127 (2026-06-13)** — 3 작업 (universe/basics/daily) 진행 상태 통합 조회 (5초 폴링 endpoint). 응답 `{universe, basics, daily}` 각 10 키 `{status: idle\|running\|completed\|failed, total, processed, updated, skipped, failed, started_at, finished_at, elapsed_ms, error_message}`. RefreshProgressBanner 가 `refetchInterval: running 5_000 / 그 외 60_000` 으로 동적 폴링. process-local in-memory state (uvicorn 단일 워커 의무) |
| GET | `/api/stock-master/stats` | stock_master.py | **사이클 84 (2026-06-09)** — stock_master 집계. **사이클 124** 8 키 확장: `{count_all, bfdy_clpr_present, nxt_tradable_count, with_hts_avls, with_acml_tr_pbmn, total_daily_rows, last_daily_load_at, top_10_recent:[{ticker,name,refreshed_at}]}` |
| GET | `/api/stock-master/list?limit=100&offset=0&market=&min_market_cap=&min_trade_amount=&name_substr=` | stock_master.py | **사이클 84** 페이징 list (refreshed_at DESC). limit ∈ [1,1000], offset ≥ 0. **사이클 128 (2026-06-13)** 4 필터 query param 신규 + 응답 envelope: `market` (KOSPI/KOSDAQ/None) / `min_market_cap` (억원 단위, `_eok_to_won` 헬퍼 환산 후 `raw->'hts_avls'` jsonb numeric gte) / `min_trade_amount` (억원 단위, 원 환산 후 `raw->'acml_tr_pbmn'` jsonb numeric gte) / `name_substr` (대소문자 무시 substring). 응답 schema 변경 `list[dict]` → `{items, total, limit, offset}` envelope (`total` = `count="exact"` 정확). 422: 범위 외 |
| GET | `/api/stock-master/scan-pool/summary` | stock_master.py | **사이클 84** — 사이클 83 `[scan_pool_eager_refresh]` 오늘 KST 발생 카운트. 응답 `{eager_refresh_today: int}` |
| GET | `/api/stock-master/{ticker}/history?limit=100` | stock_master.py | **사이클 84** — ticker 별 변경 이력 (changed_at DESC). migration 032 `stock_master_history` 조회. 응답 `[{id, ticker, change_type, before_raw, after_raw, changed_at}]` |
| GET | `/api/stock-master/{ticker}/daily?days=30` | stock_master.py | **사이클 124 (2026-06-12)** — ticker 별 일봉 조회 (`stock_master_daily`, bas_dd DESC). days ∈ [1,100]. 응답 30 행 OHLCV. 미적재 ticker → 404 |
| GET | `/api/stock-master/{ticker}` | stock_master.py | **사이클 84** — 단건 조회. 미존재 시 404. 응답 StockBasics dict |

## 응답 형식
모든 응답은 `models/response.py`의 `ApiResponse` 래퍼 사용:
```json
{ "success": true, "data": { ... }, "message": "ok" }
```

## 프론트엔드 연동
- 프론트가 사용하는 TypeScript 타입: `frontend/src/types/`
- 응답 필드명 변경 시 반드시 프론트 타입도 동기화할 것
- 페이징 응답에 `total`, `total_pages` 필드 포함 필수
- history, performance API에 `strategy` 쿼리 파라미터 지원 (전략별 필터)
