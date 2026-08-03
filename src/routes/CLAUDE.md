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
| GET | `/api/strategies/te?months=3` | strategies.py | **사이클 F (2026-08-02)** — 전략별 TE(트레이딩 예지치)/RR비율 최근 N개월(months×30일) 지표 (관찰 전용). 응답 `data: TeRrMetrics[]`(7전략) 19필드: strategy_id/n/win/loss/even/win_rate/avg_win_pct/avg_loss_pct/te_pct/te_krw_avg/realized_sum_krw/rr/required_rr/rr_margin/rr_available/sample_tier/verdict/structure_tag/single_trade_dominant. 소스=`get_trade_pairs`(진입가 기준·청산왕복). **전용 엔드포인트 + 5분 monotonic 캐시**(months 키, `invalidate_te_cache()`) — 기존 `/api/strategies`(빈번 폴링) 무변경. 전략별 예외 격리. 매매 8영역 diff 0 (read-only) |
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
| GET | `/api/realtime/market-operation` | realtime.py | **사이클 186 (2026-06-29)** 장운영상태(VI/거래정지/종목상태/서킷브레이커) 현황 (관찰성 전용). `market_operation_monitor.get_market_op_state_summary()`(`vi_active_count`/`halt_active_count`/`iscd_stat_active_count`/`last_event_count`/`vi_active_sample`/`halt_active_sample` + `circuit_breaker`) + `details`(cap 200, 종목별 `{ticker,vi_code,ovtm_vi_code,halt_yn,halt_reason,iscd_stat,mkop_cls_code,exch_code,received_at}`). `circuit_breaker` = 휴리스틱 `{suspected,reasons,halt_ratio,halted,observed,representative_mkop_cls_code,halt_reasons_sample}` (CB 전용 필드 부재 → MKOP_CLS_CODE/사유 기반 best-effort + raw 계측). 데이터 소스 = cycle 149 H0UNMKO0 종목별 구독. RealtimeHealth 페이지 5번째 카드 노출. **매수 가드 미연계(표시만)** |
| GET | `/api/integrations/dkstock-regime` | system_integrations.py | 외부 매크로 서버 활성 여부 조회 (사이클 5, 2026-05-17). 응답 `{enabled, source: 'db'\|'env', env_value, db_value}` — DB 우선 / .env fallback. db_value=null 이면 source='env' |
| PUT | `/api/integrations/dkstock-regime` | system_integrations.py | 외부 매크로 서버 활성 토글 (사이클 5). body `{enabled: bool}`. 활성화(true) 시 `asyncio.create_task(_refresh_market_regime_and_persist_safely())` 백그라운드 fetch 발화. 비활성화 시 메모리 regime empty reset(매수 가드 즉시 해제). DB 갱신 실패는 500. 매크로 fetch 실패는 graceful — toggle 자체는 성공 |
| GET | `/api/integrations/kis-mcp` | system_integrations.py | 외부 백테스트 서버 활성 여부 조회 (사이클 5). 응답 구조 동일 |
| PUT | `/api/integrations/kis-mcp` | system_integrations.py | 외부 백테스트 서버 활성 토글 (사이클 5). 즉시 fetch 안 함 — 백테스트는 자문 시점(20:00) 발화 |
| GET | `/api/integrations/auto-regime-adjust` | system_integrations.py | 매크로 레짐 → cash_usage_ratio 자동 갱신 토글 조회 (사이클 5 통합 위치). 사이클 2 의 `auto_regime_adjust` 키 활용 — 라우트만 통합 |
| PUT | `/api/integrations/auto-regime-adjust` | system_integrations.py | 매크로 레짐 자동 갱신 토글 (사이클 5). 다음 영업일 _boot 부터 반영. 기존 `/api/market-regime/auto-adjust` 와 동일 동작(어느 쪽 사용해도 무방, 새 라우트는 Settings UI 통합 위치) |
| GET | `/api/integrations/etf-regime` | system_integrations.py | 지수ETF 고지로 스테이지 레짐 관찰 토글 (사이클 I, 2026-08-03). 응답 `{enabled, source:'db', env_value:false, db_value}` (dkstock-regime 미러, .env fallback 없음 — `etf_regime_enabled` 기본 false). **관찰 opt-in — 매수 미개입**(레짐 게이트 제거) |
| PUT | `/api/integrations/etf-regime` | system_integrations.py | ETF 레짐 관찰 토글 (사이클 I). body `{enabled: bool}`. DB 갱신 실패 500. 대시보드 MarketRegimeCard ETF 스테이지 표시 근거 |
| GET | `/api/integrations/buy-block` | system_integrations.py | 매수 가드 현재 상태 (사이클 8, 2026-05-18). 응답 `{mode: 'OFF'\|'WARN'\|'SOFT'\|'HARD', thresholds:{vix_threshold, fg_high_threshold, fg_low_threshold, defensive_enabled}, blocked, reasons:[], soft_multiplier, data_available, guard_inert}`. **사이클 I (2026-08-03) — 매수 게이트 제거**: mode/blocked 는 이제 매매에 영향 없는 **표시 전용**(risk.py/scheduler 게이트 폐지, 레짐 관찰 전용). 운영 DB `buy_block_mode=OFF` 권장(정직 표시). blocked=임계 OR 평가 결과(참고) / reasons=발동 사유 UI 표시. **사이클 D (2026-07-31)**: `data_available`=매크로 데이터 실유입 여부(`regime.has_regime_data`) / `guard_inert`=`mode != "OFF" and not data_available`(가드 설정됐으나 데이터 없어 무력 = false sense of protection). 프론트 red 무력 배너(`buy-block-guard-inert`) 근거. **사이클 E-1 (2026-07-31, 관찰 전용)**: `etf_kospi_stage`/`etf_kosdaq_stage`(int\|null, KODEX200/코스닥150 고지로 스테이지) + `etf_defensive`(bool\|null, 신선 지수 방어 OR) + `etf_enabled`(bool, `etf_regime_enabled` 다크런치 토글). 소스=`get_current_etf_signal()`(재계산 X). **E-1 은 관찰 노출만 — 매수 가드 미연동**(block 통합은 E-2) |
| PUT | `/api/integrations/buy-block` | system_integrations.py | 매수 가드 부분 갱신 (사이클 8). body `{mode?, vix_threshold?, fg_high_threshold?, fg_low_threshold?, defensive_enabled?}`. Pydantic 422: mode 외 값 / VIX 범위 [10,50] 외 / FG_high [50,100] 외 / FG_low [0,50] 외. DB 갱신 실패 500. 다음 매수 신호부터 즉시 반영 |
| GET | `/api/integrations/quote-accounts?active_only=false` | kis_quote_accounts.py | 보조 KIS 시세 수신 계좌 목록 (사이클 7-A, 2026-05-17). 응답 `{accounts:[{id,label,app_key,app_secret_masked,kis_env,active,created_at,updated_at}]}`. **app_secret 평문 절대 노출 안 함** (마스킹 `****1234`) |
| POST | `/api/integrations/quote-accounts` | kis_quote_accounts.py | 보조 계좌 등록 (사이클 7-A). body `{label, app_key, app_secret, kis_env:'real'\|'vts'}`. 201/409(label 중복)/422(빈 값)/500. 매매/잔고 활용 0 — 시세 수신 풀에만 등록 |
| PUT | `/api/integrations/quote-accounts/{id}` | kis_quote_accounts.py | active 토글 / label 수정 (사이클 7-A). body `{active?, label?}`. 200/404/409. app_key/app_secret 수정 미지원(보안 감사 추적성 — 삭제 후 재등록) |
| DELETE | `/api/integrations/quote-accounts/{id}` | kis_quote_accounts.py | 계좌 제거 (사이클 7-A). 200/404 |
| GET | `/api/strategy-funnel?strategy_id=&target_date=` | strategy_funnel.py | **사이클 34 (2026-05-21)** — 특정 영업일 + 전략의 단계별 후보/탈락 종목 (`step_no` ASC). 응답: `{strategy_id, target_date, snapshots:[{step_no, step_name, survived_count, excluded_count, survived_tickers, excluded_sample}], is_business_day, holiday_note}`. **사이클 132 (2026-06-15)** — `is_business_day: bool` + `holiday_note: str \| null` 영역 추가 (휴장일 UI 안내, Q3=A 영속). KIS `chk-holiday` 영구 재사용 (사이클 17 영속, 신규 호출 0건). 영업일 = `(true, null)` / 휴장일 = `(false, "오늘은 휴장일 — 영업일 데이터 미수신")` / 호출 실패 = graceful `(true, null)` (사이클 88 G-REJECT 답습) |
| GET | `/api/strategy-funnel/recent?strategy_id=&days=7` | strategy_funnel.py | 최근 N영업일 추이 (사이클 34) |
| POST | `/api/strategy-funnel/snapshot` | strategy_funnel.py | 수동 trigger — 각 전략 prepare 결과(`_funnel_steps`) snapshot 즉시 생성 (사이클 34). **사이클 171 (2026-06-22)** — 종전 최종 단계 (`step_no=99`) 단독 → `scheduler.capture_funnel_snapshots(registry, is_provisional=False)` 공통 헬퍼 위임 (09:30 자동 hook 과 동일 단계별 + step_no=99 전체 캡처). 운영자 "지금 각 단계 후보 보기" 니즈 충족. 응답 `{target_date, saved_count, count}` (saved_count = 저장 row 수). is_provisional=False (확정 — 잠정은 16:20 저녁 task) |
| POST | `/api/stock-master/refresh-universe` | stock_master.py | **사이클 90 (2026-06-09)** — universe 즉시 trigger 수동 발화 + asyncio.Lock 동시 호출 차단 (409 Conflict). **사이클 110 (2026-06-11) 시정**: 사이클 101 (Q68=A+Q69=B) `fetch_top_500_universe` + `_universe_eager_refresh_loop` 폐기 시점에 import 동행 시정 누락 silent 결함 (사이클 101~108 8 사이클 동안 발견 0건). `from src.engine.scanner import _full_universe_load_once` 단일 호출. **사이클 127 (2026-06-13) — fire-and-forget 전환**: `FastAPI BackgroundTasks` 사용 (response 전송 *후* schedule, axios 디폴트 timeout silent 결함 영구 차단). asyncio.Lock 폐기 → `refresh_progress.is_running("universe")` state 기반 가드. 응답 schema 변경 `{status: "started", task_key: "universe"}`. message: `"universe refresh 시작 — 진행 상황은 /api/stock-master/refresh-progress 폴링"`. 200/409 Conflict (running 중) |
| POST | `/api/stock-master/basics/refresh` | stock_master.py | **사이클 126 (2026-06-13)** — KIS CTPF1002R + FHKST01010100 매스 보강 즉시 trigger. KRX 1차 폴백에서 `nxt_tradable=False`/`krx_halted=False`/`admin_item=False` 하드코딩 결함 시정 (매매 hot path lazy 호출에만 의존하던 영역 일일 1회 매스 갱신 의무). 2,697 종목 × ~100ms ≈ 13분 소요. 자동 task = scheduler `TIME_STOCK_MASTER_BASICS_REFRESH=16:10 KST` + start() 직후 1회. **사이클 127 — fire-and-forget BackgroundTasks 전환**. 응답 `{status: "started", task_key: "basics"}`. 200/409 |
| POST | `/api/stock-master/daily/refresh` | stock_master.py | **사이클 126** — KIS FHKST03010100 일봉 즉시 적재 trigger. `_stock_master_daily_load_once()` 호출 (사이클 122 일봉 자동 task 와 동일 함수). **사이클 127 — fire-and-forget BackgroundTasks 전환**. 응답 `{status: "started", task_key: "daily"}`. 200/409 |
| POST | `/api/stock-master/master/refresh` | stock_master.py | **사이클 129 (2026-06-14)** — KIS 공식 일일 마스터 파일 (`kospi_code.mst` / `kosdaq_code.mst`) 다운로드 + cp949 파싱 + `master_raw` 배치 upsert 즉시 trigger. KOSPI 70 컬럼 + KOSDAQ 64 컬럼 (KOSDAQ 전용 `invt_alrm_yn` 투자주의환기 / 벤처기업 / KOSDAQ150 3건) 매스 적재. 자동 task = scheduler `TIME_STOCK_MASTER_MASTER_LOAD=16:30 KST` + start() 직후 1회. **fire-and-forget BackgroundTasks** (사이클 127 패턴). 응답 `{status: "started", task_key: "master"}`. 200/409 |
| GET | `/api/stock-master/refresh-progress` | stock_master.py | **사이클 127 (2026-06-13)** — 작업 진행 상태 통합 조회 (5초 폴링 endpoint). **사이클 129 — 4 작업 확장 (universe/basics/daily/master)**. 응답 `{universe, basics, daily, master}` 각 10 키 `{status: idle\|running\|completed\|failed, total, processed, updated, skipped, failed, started_at, finished_at, elapsed_ms, error_message}`. RefreshProgressBanner 가 `refetchInterval: running 5_000 / 그 외 60_000` 으로 동적 폴링. process-local in-memory state (uvicorn 단일 워커 의무) |
| GET | `/api/stock-master/stats` | stock_master.py | **사이클 84 (2026-06-09)** — stock_master 집계. **사이클 124** 8 키 확장: `{count_all, bfdy_clpr_present, nxt_tradable_count, with_hts_avls, with_acml_tr_pbmn, total_daily_rows, last_daily_load_at, top_10_recent:[{ticker,name,refreshed_at}]}` |
| GET | `/api/stock-master/list?limit=100&offset=0&market=&min_market_cap=&min_trade_amount=&name_substr=` | stock_master.py | **사이클 84** 페이징 list (refreshed_at DESC). limit ∈ [1,1000], offset ≥ 0. **사이클 128 (2026-06-13)** 4 필터 query param 신규 + 응답 envelope: `market` (KOSPI/KOSDAQ/None) / `min_market_cap` (억원 단위, `_eok_to_won` 헬퍼 환산 후 시총 비교) / `min_trade_amount` (억원 단위, 원 환산 후 거래대금 비교) / `name_substr` (대소문자 무시 substring). 응답 schema 변경 `list[dict]` → `{items, total, limit, offset}` envelope (`total` = `count="exact"` 정확). 422: 범위 외. **사이클 168 (2026-06-20)** — `min_market_cap` / `min_trade_amount` 필터 0건 silent 결함 시정. raw.hts_avls / raw.acml_tr_pbmn 가 운영 DB 에 jsonb *문자열* 로 저장되어 종전 jsonb numeric gte 가 항상 false (number > string 정렬) → 어떤 임계든 0건. migration 039 생성 컬럼 `hts_avls_eok`(억원) / `acml_tr_pbmn_won`(원) STORED + 인덱스로 전환. `list_paged_by_filter` `.gte("hts_avls_eok", min_market_cap//100_000_000)` / `.gte("acml_tr_pbmn_won", min_trade_amount)`. market/name 필터는 정상이라 영향 0 |
| GET | `/api/stock-master/scan-pool/summary` | stock_master.py | **사이클 84** — 사이클 83 `[scan_pool_eager_refresh]` 오늘 KST 발생 카운트. 응답 `{eager_refresh_today: int}` |
| GET | `/api/stock-master/{ticker}/history?limit=100` | stock_master.py | **사이클 84** — ticker 별 변경 이력 (changed_at DESC). `stock_master_history` 조회 (`list_history` = `select("*")` pass-through). **사이클 150 (migration 036)** 스키마 재설계: `(ticker, seq)` PK. `id`/`before_raw`/`after_raw` 제거 → `seq INT`(0=최신본 / 1=직전본) + `raw JSONB` 신설 (92K→7,146 row 용량 절감). `change_type` = INSERT/UPDATE/DELETE 3종 (trigger `OLD.raw IS DISTINCT FROM NEW.raw` 조건, 'TTL_REFRESH' 미발화). 현재 응답 schema `[{ticker, seq, change_type, raw, changed_at}]`. **사이클 169 (2026-06-20)** — 프론트 UI 변경이력 탭이 사이클 150 신 스키마에 미동기화(`item.before_raw`/`after_raw` 참조)되어 빈 화면이던 회귀 시정 (백엔드 변경 0, 프론트 단독) |
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
