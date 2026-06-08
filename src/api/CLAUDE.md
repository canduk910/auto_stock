# CLAUDE.md — src/api/ (KIS REST API)

KIS OpenAPI REST 호출 모듈. 모든 호출은 `base.py` 공통 래퍼를 통한다.

> 사이클별 변경 이력: `docs/HARNESS_CHANGELOG.md`

## base.py — 공통 래퍼 (메인 단일)

- `kis_request(method, url, tr_id, ...)`: 모든 KIS API 호출의 단일 진입점
- 헤더 자동 구성: authorization, appkey, appsecret, tr_id, custtype("P")
- Rate Limit: `asyncio.Semaphore(20)` 초당 20건 제한
- 에러 처리: `rt_cd != "0"` 시 msg_cd + msg1 로깅
- 자동 재시도: 네트워크/5xx 최대 3회, 지수 백오프 (`BACKOFF_BASE=0.5s × 2^(attempt-1)`) + jitter (`0~BACKOFF_JITTER=0.25s`) — thundering herd 완화
- 토큰 만료 감지 시 자동 갱신 후 재시도
- 호출 메트릭: `_request_metrics` (전역 dict) `total/http_5xx/http_4xx/network_err/kis_error/retries/retry_recovered/retry_exhausted + path별 5xx top 5`. `get_request_metrics()` 스냅샷 / `reset_request_metrics()` 리셋. `log_analysis_engine.py` 가 20:10 INSERT 후 reset
- **거부 응답 영구 저장**: `rt_cd != "0"` 시 `KisApiError` raise 직전 `system_logs.write_log("ERROR", "[kis_rejection] path=... tr_id=... msg_cd=... msg1=... body={PDNO/ORD_DVSN/ORD_UNPR/ORD_QTY/EXCG_ID_DVSN_CD/SLL_BUY_DVSN_CD}")` fire-and-forget. 민감 키 (CANO/ACNT_PRDT_CD) 마스킹. `write_log` 예외 swallow. `docs/kis/error-codes.md` 4절
- **재시도 최종 결과 영구 저장**: 재시도 루프 끝난 직후 영문 prefix 1행 fire-and-forget. (a) `attempt > 1` + `rt_cd=0` 성공 → INFO `[api_retry_recovered] path=... tr_id=... attempts=N`. (b) `MAX_RETRIES=3` 모두 5xx/network 실패 후 raise 직전 → ERROR `[api_retry_exhausted] path=... tr_id=... attempts=3 last_status={503|network} last_msg=...`. 기존 `retries` (중간 시도) 와 분리 — *최종* 결과만
- **사이클 76 (2026-06-08) — `_request` 5xx WARNING 60s dedupe + recovered 5분 collector (api 5.80x → 1.0~1.2 시정, 사이클 18 + 74 하이브리드 답습)**: 사이클 74 운영 실증 발견 `api` 5.80x dup (29/5) + `[api_retry_recovered]` 7.00x (14/2) 시정. **시정 사이트 2 영역**: 영역 1 `_request` (메인 단일, 사이클 18 dedupe 미적용 — 5.80x 주요인) + 영역 2 `_request_via_quote_pool` (시세 풀, 사이클 18 dedupe 영속 — recovered/exhausted 만 신규). **신규 함수 7 (`src/api/base.py` +150L)**: (1) `_record_request_5xx_for_dedupe(path, status) -> bool` — 메인 5xx WARNING 60s dedupe (사이클 18 `_record_5xx_for_dedupe` 답습, Q4 메인용 분리) + (2) `_record_api_recovered(path, attempts)` — 메인 retry 성공 누적 + (3) `_record_quote_recovered(path, attempts)` — 풀 retry 성공 누적 (Q4 분리) + (4) `_flush_api_recovered_collector()` — 5분 윈도우 종료 시 `[api_retry_recovered_summary] window=300s total=N by_path={...}` 1행 emit (Q2 빈 윈도우 skip) + (5) `_flush_quote_recovered_collector()` 동일 + (6) `_warn_http_status(status, attempt, max_retries, path)` — `logger.warning("HTTP %s ...")` 헬퍼 추출 (G-AST1 통과용) + (7) 모듈 상수 `_REQUEST_5XX_DEDUPE_WINDOW=60.0` / `_API_RECOVERED_COLLECTOR_WINDOW=300.0`. **State 3 (Q4 메인/풀 분리)**: `_request_5xx_dedupe: dict[(path, status), {first_at, count}]` (메인) ↔ `_quote_5xx_dedupe: dict[(path, label, status), {...}]` (사이클 18 영속) + `_api_recovered_collector: dict[path, {count, max_attempts}]` ↔ `_quote_recovered_collector` (분리). 호출 사이트 정정: `_request` L487 `_warn_http_status` 경유 + L545 `_record_api_recovered(path, attempt)` (기존 직접 `await write_log("INFO", "[api_retry_recovered]...")` 제거) + `_request_via_quote_pool` 동일 영역 `_record_quote_recovered` 호출. **ERROR 보존 매트릭스 4 영역 individual 영속 (변경 0, 사이클 29 005935 LMS chain 진단 의무)**: R2 `[api_retry_exhausted]` 5xx 최종 실패 (L495) + R4 네트워크 최종 실패 (L523) + R7 토큰 만료 최종 실패 (L563) + R8 `[kis_rejection]` (L590 메인 + L846 quote, CLAUDE.md "절대 깨지 말 것" 영속). **신규 task** (`src/engine/scheduler.py` +34L): `_api_recovered_collector_loop` 5분 주기 (사이클 42 `_heartbeat_metrics_loop` 답습) — `connect()` 시점 task 시작 + `disconnect()` cancel + await 정리 + 마지막 flush 1회 (Q5 사이클 74 답습) + `_flush_api_recovered_collector` + `_flush_quote_recovered_collector` 순차 호출. **AST 영구 가드 3 신설**: G-AST1 (`_request` 직접 `logger.warning("HTTP ...")` 0건, 헬퍼 경유만) + G-AST2 (사이클 18 `_record_5xx_for_dedupe` 호출 영속) + G-AST3 (`[api_retry_recovered]` 직접 write_log 0건, collector 경유만). **회귀 가드 15 케이스 (4 파일)**: G-MD1~MD4 메인 60s dedupe (freezegun) + G-RC1~RC4 5분 collector (freezegun) + G-ERR1~ERR4 ERROR 보존 매트릭스 영속 + G-AST1~AST3. 사이클 17 OPSP0002 backoff (`websocket.py`) + 사이클 18 풀 dedupe 영속 (변경 0). 운영 효과 예상 (push 후 측정): dup_factor api 5.80x → 1.0~1.2, recovered 7.00x → 1.0 (5분당 1행)

## base.py — REST 시세성 호출 풀

시세성 KIS REST 호출만 보조 계좌(`kis_quote_accounts`) 라운드로빈으로 분산. 매매/잔고/체결조회는 영원히 메인 단일.

**자금 안전 절대 원칙**:
- 매매 (`place_order`/`cancel_order`) / 잔고 (`get_balance`/`get_buyable`) / 체결조회 (`get_daily_orders`) / 체결통보 → 메인 단일 (`kis_request` 그대로)
- 시세성 호출만 본 풀에 라우트: `fetch_daily_candles`, `fetch_stock_detail`, `_fetch_fluctuation_rank`, `inquire_stock_basics`, `is_market_open`, `next_trading_day`

**Public API**:
- `kis_get_quote(path, tr_id, params, *, hashkey="")` — 시세 GET (보조 라운드로빈 + 메인 fallback)
- `kis_post_quote(path, tr_id, body, *, hashkey="")` — 시세 POST (인터페이스 대칭)
- `get_quote_request_metrics() -> dict` — 격리 스냅샷 (`total/http_5xx/4xx/network_err/kis_error/retries/recovered/exhausted/by_label`)
- `reset_quote_request_metrics() -> None` — 메인 reset 과 분리

**Path 가드** (`QuotePoolPathError` raise — `ValueError` 서브클래스):
- 화이트리스트 6 path 만 허용 (사이클 32 추가): `/quotations/inquire-price` / `/quotations/inquire-daily-itemchartprice` / `/ranking/fluctuation` / `/quotations/search-stock-info` / `/quotations/chk-holiday` / `/quotations/inquire-ccnl`
- 매매/잔고/체결조회 path (`/trading/order-cash` / `/trading/order-rvsecncl` / `/trading/inquire-balance` / `/trading/inquire-psbl-order` / `/trading/inquire-daily-ccld`) 진입 시 즉시 raise — 자금 안전 정책 위반 사전 차단

**라운드로빈**:
- `_quote_request_index: int` + `asyncio.Lock` 동기화
- `_select_quote_label()` 매 호출 `(idx + 1) % len(active_labels)` 라벨 순환
- 보조 0개 또는 모든 active=false → `None` 반환 → 메인 fallback
- 보조 토큰 매니저 발급 실패 (`ValueError` 등) → 메인 fallback (graceful)

**Per-label 격리 Rate Limit**:
- `_quote_semaphores: dict[label, Semaphore(18)]` — 매니저별 18 (메인 20 보다 보수적). `_get_quote_semaphore(label)` lazy 생성

**메트릭 격리**:
- `_quote_request_metrics` dict — 메인 `_request_metrics` 와 완전 분리
- `by_label: defaultdict(int)` — `main` (fallback) / `quote-1` / `quote-2` ... 별 호출 카운트

**거부 응답 로깅 분리**: 시세 풀 거부는 `[kis_rejection_quote]` prefix — 메인 `[kis_rejection]` 과 구분. body 마스킹/주요 키 추출은 본 풀 미적용 (시세 호출은 민감 식별자 미포함)

**Health monitor 통합** (`src.services.quote_session_health.health_monitor`):
- 응답 분기에서 호출 — 성공 (`rt_cd=="0"`) + `actual_label != "main"` → `record_success(label)` / 5xx HTTPStatusError → `record_failure(label, reason=f"http_{status}")` / 보조 매니저 발급 실패 → `record_failure(label, reason="token_issue_fail")`
- KIS rt_cd!=0 비즈니스 거부 → 기록 안 함 (헬스와 무관)
- 네트워크 에러 → 기록 안 함 (클라이언트 측 이슈 가능)
- 임계 초과 시 health_monitor 가 `kis_quote_accounts.update_account(active=False)` + `kis_ws_pool.disable_quote_session(label)` + `[quote_session_disabled]` 영구 1행. DB 실패 graceful — 메모리만 비활성 + WARNING
- 메인 라벨 "main" 자동 비활성 절대 금지 (안전 가드)
- 운영자 대응: Settings UI 보조 계좌 카드 `active=true` 토글 → **다음 영업일** `_boot()` 부터 풀 재참여
- **사이클 18 (2026-05-19) FAST_WINDOW 추가**: 기존 임계 (consecutive 5 / 5분 50%) + 1분 80% (`FAST_WINDOW_SECS=60`, `FAST_MIN_CALLS=10`, `FAST_MAX_FAILURE_RATE=0.8`). 영구 결함 라벨 (ISA 등 5xx 80%+) 빠른 탈락. 운영자 안내: 5xx 빈발 보조 라벨은 Settings UI active=false 수동 비활성 권장 — 자동 임계 도달 전 운영자 개입 가능

**사이클 18 (2026-05-19) 5xx 폭주 정리** (A-1, A-3):
- **WARNING dedupe** (`_record_5xx_for_dedupe(path, label, status) -> bool`): 동일 `(path, label, status)` 키 60s 윈도우 (`_QUOTE_5XX_DEDUPE_WINDOW=60.0`) 내 재발생 시 첫 1회만 WARNING + 카운트만 누적. ISA 같은 영구 5xx 라벨에서 분당 ~30 행 WARNING → 1행 + 60s summary INFO. lock `_quote_5xx_dedupe_lock` (asyncio.Lock) 동시성 보호
- **60s summary task** (`_emit_5xx_dedupe_summary()`): scheduler `_5xx_dedupe_summary_loop` 가 60s 주기 호출. 윈도우 만료 + 카운트 ≥ 2 인 키 1행 INFO `[quote_pool_5xx_summary] path=... label=... status=500 count=N within=60s` + dedupe state clear
- **메인 fallback 우선 (A-3)**: `_request_via_quote_pool` 의 라벨 선택 직후 `health_monitor.get_recent_5xx_ratio(label)` 조회. `total>=FAST_MIN_CALLS(10)` AND `ratio>=_LABEL_FALLBACK_5XX_RATIO_THRESHOLD(0.8)` 면 `label=None` 강제 (메인 fallback). 3회 재시도 backoff (수 초) 회피 → 응답 지연 ms 단위. 메트릭 `fast_fallback` 카운터 +1 운영 가시화
- **메트릭 확장**: `_quote_request_metrics["fast_fallback"]` 신규 — 80%+ 라벨 skip 누적 카운트. `get_quote_request_metrics()` / `reset_quote_request_metrics()` 동기화

## order.py — 주문

- 현금 매수: TTTC0012U / 매도: TTTC0011U / 정정·취소: TTTC0013U
- `settings.get_tr_id()` 모의/실전 자동 변환
- **자금 안전**: 본 모듈은 `kis_post` (메인 단일) 만 사용. `kis_post_quote` / `kis_get_quote` 절대 import 안 함 — `test_condition_quote_routing.py::test_order_module_never_imports_quote_pool` 가드
- `place_order(..., exchange="KRX")` / `cancel_order(..., exchange="KRX")`: `EXCG_ID_DVSN_CD` body. `KRX`(기본) / `NXT` / `SOR`. 모의(VTS) KRX 만 허용 — SOR/NXT 실전 한정. 미지정 시 KRX (후방 호환)
- **매수 지정가 분기**: `order_engine.execute_buy` 가 "시장가매매불가" 거부 폴백 시 `place_order(side=BUY, price=fallback_price>0, order_division=LIMIT, exchange=...)`. body 는 `ORD_DVSN=order_division.value`, `ORD_UNPR=str(price)` 직렬화 — 매도 지정가와 동일 경로

## balance.py — 잔고/조회

- 잔고조회: TTTC8434R / 매수가능조회: TTTC8908R
- **자금 안전**: 본 모듈은 `kis_get` (메인 단일) 만 사용. 보조 시세 풀 함수 절대 import 안 함 — `test_balance_module_never_imports_quote_pool` 가드
- `get_balance(afhr_flpr="N")`: `AFHR_FLPR_YN` query. `N`(기본 정규장) / `Y`(시간외 단일가) / `X`(NXT 정규장) — required
- `get_daily_orders(target_date="", exchange="ALL")`: TTTC0081R. `EXCG_ID_DVSN_CD` query required — `ALL`(기본, KRX+NXT+SOR 합산) / `KRX` / `NXT` / `SOR`. NXT 체결 누락 방지 위해 기본 ALL

### KIS 거부 응답 분류 헬퍼

- `is_market_closed_rejection(KisApiError) -> bool`: 장운영시간 외 / 매매 불가 시간 / 거래시간 외. `msg_cd=APBK0918` 공용이라 msg1 키워드(`_MARKET_CLOSED_KEYWORDS`) 로 분리. True 면 `is_insufficient_*` False — positions 보존 결정
- `is_insufficient_cash(KisApiError) -> bool`: 예수금 부족 매수 실패. msg_cd 화이트리스트 (APBK0919/EGW00120) + msg1 키워드 ("부족" + "주문가능금액/예수금/현금") 동시 검사. `APBK0918` 은 현금 키워드 동반 시만 True. OrderEngine 매수 락 결정용
- `is_insufficient_quantity(KisApiError) -> bool`: 보유 부족 매도 실패. msg1 키워드 ("부족" + "매도가능/보유수량/잔고") + `APBK0918` 은 보유 키워드 동반 시만 True. 매도 즉시 break 결정용
- `is_market_order_disallowed(KisApiError) -> bool`: 시장가 거부. msg1 키워드 `_MARKET_ORDER_DISALLOWED_KEYWORDS`: `시장가매매불가` / `시장가 매매 불가` / `시장가 주문 불가` / `시장가 호가 불가` / `시장가호가불가` / `최유리/최우선지정가 주문만` / `지정가 및 최유리`. 기존 3종과 **상호 배타** — True 면 다른 3종 False. msg_cd 누적: APBK1943 (계양전기 매도) + APBK3013 (NXT 애프터 매도). `docs/kis/error-codes.md` 4-2절 / 5-4절

## quotation.py — 주식현재가 체결 (사이클 32, 2026-05-21)

- `inquire_ccnl(ticker: str, market: str = "J") -> dict | None`: KIS `FHKST01010100` 주식현재가 시세. `kis_get_quote` 경유 (시세성 풀 라우팅 + Rate Limit + 메트릭)
- 응답: output 첫 row (가장 최근 체결) + today_volume 합산. 키: `last_cntg_hour`(HHMMSS) / `last_price` / `last_volume` / `last_relative_strength` / `today_volume` / `prev_compared_rate`
- graceful: 빈 응답 / KIS 오류 / 예외 → None (호출자 보호)
- 6자리 ticker 사전 가드 (`ValueError`)
- 호출처: `scheduler._evaluate_universe_guard` (사이클 32, universe 제외 판단) + `scheduler._refresh_stale_ccnl_cache` (사이클 37, stale 종목 UI 표시용 TTL 5분 캐시)

## condition.py — 조건검색 + 영업일 + 종목 기본정보 + TTL 캐시

- **시세성 호출 풀 라우팅**: 본 모듈 6 함수 모두 `kis_get_quote` 사용 — 보조 라운드로빈 + 메인 fallback. 시그니처 변경 0 (외부 영향 없음). `from src.api.base import kis_get_quote` (메인 `kis_get` import 제거)
- 거래량순위 API (FHPST01700000) 로 종목 필터링. 시총/거래대금 필터
- `is_market_open(date)`: KIS chk-holiday API (CTCA0903R) 로 개장일 여부 (`opnd_yn == "Y"`)
- `next_trading_day(after_date)`: 다음 개장일 (휴일 다음날 자동)
- `fetch_daily_candles(ticker, days)`: 일봉 N영업일치. `FHKST03010100` (`/quotations/inquire-daily-itemchartprice`, 모의/실전 동일) — **단일 호출 최대 100일**. 응답 `output2` (최신순), `stck_bsop_date` 빈 placeholder 제거. 윈도우 = `days + days//2 + 10` (영업일/달력일 5/7 + 마진)
- **`inquire_stock_basics(pdno) -> StockBasics`**: KIS `CTPF1002R` — NXT 거래종목 (`cptt_trad_tr_psbl_yn`) + NXT 거래정지 (`nxt_tr_stop_yn`) + KRX 정지 + 관리종목 파싱 → `StockBasics` 반환. 파생값 `nxt_tradable = (cptt=="Y") AND (nxt_stop=="N")`. CTPF 접두사 TR_ID 는 모의/실전 동일. 캐시 `src.db.stock_master` 24h TTL. **ticker 정규화**: `_normalize_ticker()` 가 KIS `pdno` 12자리 표준코드 → KRX 6자리 단축코드 추출 (정규식 `(\d{6})$`). `stock_master` PK 정합성 보장. `docs/kis/error-codes.md` 5-3절

### TTL 캐시 (single-flight)

KIS 부하 + 5xx 노출 면적 축소:
- `fetch_stock_detail`: `_PRICE_CACHE_TTL=5s`, 키 = `ticker`
- `fetch_daily_candles`: `_CANDLE_CACHE_TTL=300s`(5분), 키 = `(ticker, days)` — days 별 분리. 일봉은 5분 지연 OK
- `asyncio.Lock` + `_inflight_*: dict[key, Task]` single-flight — 동시 N 호출 시 첫 호출만 KIS fetch, 나머지 task 합류
- 무효화: TTL 자동 만료 + `clear_caches()` (`_reset_daily_state` 20:10 호출). `_cache_epoch` bump 로 진행 중 inflight 의 stale write 차단
- joiner 는 `await asyncio.shield(task)` 합류 — 자기 task cancel 시 inflight cancel 전파 차단
- **사용 범위 안전 가드**: 스캐닝/조건검사 한정. `execute_buy/execute_sell` 의 체결가/주문가 결정 경로는 절대 사용 금지 (WebSocket tick 또는 직접 호출 유지)

## 새 API 추가 절차

1. `docs/kis/{category}.md` 에서 TR_ID, URL, 파라미터 확인
2. 본 디렉토리에 함수 추가 (반드시 `kis_request()` 또는 `kis_get_quote()` 사용)
3. TR_ID 는 `settings.get_tr_id("실전TR_ID")` 사용
4. 응답 모델은 `models/` 에 pydantic 으로 정의
