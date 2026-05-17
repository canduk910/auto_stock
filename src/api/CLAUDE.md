# CLAUDE.md — src/api/ (KIS REST API)

KIS OpenAPI REST 호출 모��. 모든 호출은 base.py의 공통 래퍼를 통한다.

## 모듈별 역할

### base.py — 공통 래퍼
- `kis_request(method, url, tr_id, ...)`: 모든 KIS API 호출의 단일 진입점
- 헤더 자동 구성: authorization, appkey, appsecret, tr_id, custtype("P")
- Rate Limit: `asyncio.Semaphore` 기반 초당 20건 제한
- 에러 처리: `rt_cd != "0"` 시 msg_cd + msg1 로깅
- 자동 재시도: 네트워크 오류 최대 3회, 지수 백오프(`BACKOFF_BASE=0.5s × 2^(attempt-1)`) + jitter(`0~BACKOFF_JITTER=0.25s` random) — thundering herd 완화
- 토큰 만료 감지 시 자동 갱신 후 재시도
- 호출 메트릭: `_request_metrics`(전역 dict)에 total/http_5xx/http_4xx/network_err/kis_error/retries + path별 5xx 카운트 누적. `get_request_metrics()` 스냅샷 / `reset_request_metrics()` 리셋. 일일 로그 분석(`log_analysis_engine.py`)이 20:10 INSERT 후 reset 호출
- **거부 응답 영구 저장(Phase A1)**: `rt_cd != "0"` 시 `KisApiError` raise 직전에 `system_logs.write_log("ERROR", "[kis_rejection] path=... tr_id=... msg_cd=... msg1=... body={PDNO/ORD_DVSN/ORD_UNPR/ORD_QTY/EXCG_ID_DVSN_CD/SLL_BUY_DVSN_CD}")` fire-and-forget 호출. 민감 키(CANO/ACNT_PRDT_CD) 마스킹. `write_log` 예외는 swallow — raise 흐름 보존. 운영 trace를 영구 보존해 새 거부 사례(예: "시장가매매불가") 진단 자료 누적. `docs/kis/error-codes.md` 4절 참조.
- **재시도 최종 결과 영구 저장(PR-B, 2026-05-14)**: `_request` 재시도 루프가 끝난 직후 다음 두 케이스를 영문 prefix 1행으로 fire-and-forget 저장 + `_request_metrics` 카운터 +1. (a) `attempt > 1` 에서 `rt_cd=0` 성공 → INFO `[api_retry_recovered] path=... tr_id=... attempts=N` + `retry_recovered`. (b) `MAX_RETRIES=3` 모두 5xx/network 실패 후 raise 직전 → ERROR `[api_retry_exhausted] path=... tr_id=... attempts=3 last_status={503|network} last_msg=...` + `retry_exhausted`. 기존 `retries`(중간 시도 카운트)와 분리 — *최종* 결과만 카운트. `reset_request_metrics()` 가 신규 키도 0 으로 초기화. `get_request_metrics()` 스냅샷에 두 키 추가 → `log_analysis_engine` 의 `metrics.api_metrics` 로 그대로 노출.

### base.py — REST 시세성 호출 풀 (사이클 7-C, 2026-05-18)

시세성 KIS REST 호출만 보조 계좌(`kis_quote_accounts`) 라운드로빈으로 분산. 매매/잔고/체결조회는 영원히 메인 단일.

**자금 안전 절대 원칙**:
- 매매 (`place_order`/`cancel_order`) / 잔고 (`get_balance`/`get_buyable`) / 체결조회 (`get_daily_orders`) / 체결통보 → 메인 단일 (`kis_request` 그대로)
- 시세성 호출만 본 풀에 라우트: `fetch_daily_candles`, `fetch_stock_detail`, `_fetch_fluctuation_rank`, `inquire_stock_basics`, `is_market_open`, `next_trading_day`

**Public API**:
- `kis_get_quote(path, tr_id, params, *, hashkey="")` — 시세 GET (보조 라운드로빈 + 메인 fallback)
- `kis_post_quote(path, tr_id, body, *, hashkey="")` — 시세 POST (인터페이스 대칭)
- `get_quote_request_metrics() -> dict` — 격리 스냅샷 (total/http_5xx/4xx/network_err/kis_error/retries/recovered/exhausted/by_label)
- `reset_quote_request_metrics() -> None` — 메인 reset 과 분리

**Path 가드** (`QuotePoolPathError` raise — `ValueError` 서브클래스):
- 화이트리스트 5 path 만 허용: `/quotations/inquire-price`, `/quotations/inquire-daily-itemchartprice`, `/ranking/fluctuation`, `/quotations/search-stock-info`, `/quotations/chk-holiday`
- 매매/잔고/체결조회 path(`/trading/order-cash`, `/trading/order-rvsecncl`, `/trading/inquire-balance`, `/trading/inquire-psbl-order`, `/trading/inquire-daily-ccld`) 진입 시 즉시 raise — 자금 안전 정책 위반 사전 차단

**라운드로빈**:
- 모듈 변수 `_quote_request_index: int` + `asyncio.Lock` 로 동기화
- `_select_quote_label()` 가 매 호출마다 `(idx + 1) % len(active_labels)` — 라벨 순환
- 보조 0개 또는 모든 active=false → `None` 반환 → 메인 fallback (`token_manager` + `_semaphore=20` 그대로)
- 보조 토큰 매니저 발급 실패 (`ValueError` 등) → 메인 fallback (graceful)

**Per-label 격리 Rate Limit**:
- `_quote_semaphores: dict[label, Semaphore(18)]` — 매니저별 18 (메인 20 보다 보수적 여유)
- `_get_quote_semaphore(label)` lazy 생성 + `_quote_semaphores_lock` 동기화
- 메인 fallback 은 메인 `_semaphore` 그대로 사용

**메트릭 격리**:
- `_quote_request_metrics` dict — 메인 `_request_metrics` 와 완전 분리. 시세 풀 호출이 메인 카운터에 누출되지 않음
- `by_label: defaultdict(int)` — `"main"`(fallback) / `"quote-1"` / `"quote-2"` ... 별 호출 카운트

**거부 응답 로깅 분리**:
- 시세 풀 거부는 `[kis_rejection_quote]` prefix — 메인 `[kis_rejection]` 과 구분 가능
- 메인의 body 마스킹/주요 키 추출은 본 풀에서 미적용 (시세 호출은 민감 식별자 미포함)

**운영 점진 활성화**: 사이클 7-A (보조 계좌 DB) + 7-B (WS 풀) 완료 후 본 사이클이 REST 마무리. 보조 0개 시 메인 only 동작 (회귀 0).

### order.py — 주문
- 현금 매수: TTTC0012U, 매도: TTTC0011U
- 정정/취소: TTTC0013U
- `settings.get_tr_id()`로 모의/실전 자동 변환
- **자금 안전 (사이클 7-C, 2026-05-18)**: 본 모듈은 `kis_post` (메인 단일) 만 사용. `kis_post_quote` / `kis_get_quote` 절대 import 안 함 — `tests/unit/api/test_condition_quote_routing.py::test_order_module_never_imports_quote_pool` 가드
- `place_order(..., exchange="KRX")` / `cancel_order(..., exchange="KRX")`: 거래소ID 구분(`EXCG_ID_DVSN_CD`) body 필드. `KRX`(기본) / `NXT` / `SOR`. 모의투자(VTS)는 KRX만 허용 — SOR/NXT는 실전 한정. 호출자 미지정 시 KRX로 동작(후방 호환)
- **매수 지정가 분기**: 그동안 매수는 항상 시장가(`price=0`)로 호출됐으나, `order_engine.execute_buy`가 "시장가매매불가" 거부 폴백 시 `place_order(side=BUY, price=fallback_price>0, order_division=LIMIT, exchange=...)` 조합으로 호출. body는 `ORD_DVSN=order_division.value`, `ORD_UNPR=str(price)`로 그대로 직렬화 — 매도 지정가와 동일 경로, 추가 보정 불필요.

### balance.py — 잔고/조회
- 잔고조회: TTTC8434R
- 매수가능조회: TTTC8908R
- **자금 안전 (사이클 7-C, 2026-05-18)**: 본 모듈은 `kis_get` (메인 단일) 만 사용. 보조 시세 풀 함수 절대 import 안 함 — `test_condition_quote_routing.py::test_balance_module_never_imports_quote_pool` 가드
- `get_balance(afhr_flpr="N")`: `AFHR_FLPR_YN` query param. `N`(기본, 정규장) / `Y`(시간외 단일가) / `X`(NXT 정규장) — required
- `get_daily_orders(target_date="", exchange="ALL")`: TTTC0081R 주식일별주문체결조회. `EXCG_ID_DVSN_CD` query param required — `ALL`(기본, KRX+NXT+SOR 합산) / `KRX` / `NXT` / `SOR`. KIS 명세 갱신(2026-05-08)에서 required로 강제 — NXT 체결 누락 방지 위해 기본값 ALL
- `is_market_closed_rejection(KisApiError) -> bool`: KIS 응답이 '장운영시간 외' / '매매 불가 시간' / '거래시간 외' 류의 시간 거부인지 판단. KIS 가 동일 `msg_cd=APBK0918` 로 보유부족·자금부족·시간외 거부를 모두 내보내므로 msg1 키워드(`_MARKET_CLOSED_KEYWORDS`)로 분리. NXT 프리/애프터에서 시장가 매도가 거부될 때 이 함수가 True 면 `is_insufficient_*` 는 False 로 떨어져 positions 보존 결정에 사용된다.
- `is_insufficient_cash(KisApiError) -> bool`: 매수 실패 응답이 '주문가능금액 부족'(예수금 부족) 사유인지 식별. msg_cd 화이트리스트(APBK0919/EGW00120) + msg1 키워드("부족" + "주문가능금액/예수금/현금") 동시 검사. `APBK0918` 은 시간외 거부와 공용이라 msg1 현금 키워드가 동반될 때만 True. OrderEngine 매수 락 결정용.
- `is_insufficient_quantity(KisApiError) -> bool`: 매도 실패 응답이 '매도가능수량 부족'(보유 부족) 사유인지 식별. msg1 키워드("부족" + "매도가능/보유수량/잔고") 가드 + `APBK0918` 은 보유부족 키워드가 동반될 때만 True. 시간외 거부에서는 False 로 떨어져 메모리/DB positions 보존. 매도 즉시 break 결정용.
- `is_market_order_disallowed(KisApiError) -> bool`: KIS 응답이 '시장가매매불가' 류의 거부인지 판단. msg1 키워드(`_MARKET_ORDER_DISALLOWED_KEYWORDS`: "시장가매매불가" / "시장가 매매 불가" / "시장가 주문 불가" / "시장가 호가 불가" / **"시장가호가불가"** / **"최유리/최우선지정가 주문만"** / **"지정가 및 최유리"**)로 매칭. 기존 3종 분류와 **상호 배타** — 이 함수가 True 이면 다른 3종은 모두 False. `execute_buy`가 이 거부에 대해 `step_up(current_price, 5)` 가격으로 지정가 1회 폴백, `execute_sell`이 시장가 매도일 때 `step_down(current_price, 5)` 지정가 1회 폴백(Phase C, 2026-05-11). 매수와 매도 양쪽 폴백 분기에서 동일 헬퍼 사용. msg_cd 는 운영 trace 누적 후 화이트리스트화 예정 — APBK1943 (2026-05-11 계양전기 매도 ×3 실패 원문) + **APBK3013** (2026-05-11 NXT 애프터 16시대 매도 ×3 실패 원문, Phase H1) 확정 추가. (`docs/kis/error-codes.md` 4-2절 / 5-4절).

### condition.py — 조건검색 + 영업일 체크 + 종목 기본정보 + TTL 캐시
- **사이클 7-C (2026-05-18) — 시세성 호출 풀 라우팅**: 본 모듈의 모든 KIS REST 호출(6 함수)이 `kis_get_quote` 로 변경. 보조 계좌 라운드로빈 + 메인 fallback. 시그니처 변경 0 — 외부 호출자 영향 없음. 매매/잔고와의 격리: `from src.api.base import kis_get_quote` (메인 `kis_get` import 제거)
- 거래량순위 API로 종목 필터링 (FHPST01700000)
- 시총/거래대금 필터 적용
- `is_market_open(date)`: KIS chk-holiday API(CTCA0903R)로 개장일 여부 (`opnd_yn == "Y"`)
- `next_trading_day(after_date)`: 다음 개장일 조회 (휴일 다음날 자동 산정)
- `fetch_daily_candles(ticker, days)`: 일봉 N영업일치 조회. **`FHKST03010100`(`/quotations/inquire-daily-itemchartprice`, 모의/실전 동일 TR_ID) 사용 — 단일 호출당 최대 100일 응답**. 이전 `FHKST01010400`(`inquire-daily-price`)은 약 30일로만 응답이 제한되어 60일 EMA 사용처(donchian_swing)에서 모든 종목이 길이 컷에 탈락하던 결함을 차단. 응답은 `output2` 배열(최신순), `stck_bsop_date`가 비어있는 placeholder 행은 제거하여 반환. 달력일 윈도우는 영업일/달력일 비율(5/7) + 마진 = `days + days//2 + 10`
- **`inquire_stock_basics(pdno) -> StockBasics`** (Phase G, 2026-05-11): KIS `CTPF1002R` 주식기본조회 — NXT 거래종목여부(`cptt_trad_tr_psbl_yn`) + NXT 거래정지여부(`nxt_tr_stop_yn`) + KRX 정지(`tr_stop_yn`) + 관리종목(`admn_item_yn`) 파싱 후 `src.models.stock.StockBasics` 반환. 파생값 `nxt_tradable = (cptt=="Y") AND (nxt_stop=="N")`. CTPF 접두사 TR_ID 는 모의/실전 동일. 캐시는 `src.db.stock_master` (24h TTL). `docs/kis/error-codes.md` 5-3절 필드 매핑 표 참조. **Phase G2 (2026-05-13)**: 반환 `ticker` 는 KIS `pdno` (12자리 표준코드 `00000A000100`) 를 모듈 헬퍼 `_normalize_ticker()` 로 KRX 6자리 단축코드로 정규화한 값 — `stock_master` PK 정합성 (`positions.ticker` 가 6자리) 을 보장. 정규식 `(\d{6})$` 로 마지막 6자리 추출, 빈/형식불일치는 빈 문자열. 12자리 그대로 저장돼 `stock_master.get(ticker)` 항상 miss → Phase G 사전 차단 무력화되던 운영 결함 차단
- **TTL 캐시 (PR-C, 2026-05-14)**: 동일 ticker 반복 조회로 인한 KIS 부하 + 5xx 노출 면적 축소. (a) `fetch_stock_detail`: `_PRICE_CACHE_TTL=5s`, 키 = `ticker`. swing pull(1분 주기) 매 호출 신선. (b) `fetch_daily_candles`: `_CANDLE_CACHE_TTL=300s`(5분), 키 = `(ticker, days)` — days 별 분리(60 vs 21 등). 일봉은 장중 분 단위 갱신 — 5분 지연은 일봉 기반 전략 시뮬레이션 정확도 무영향. 두 함수 모두 `asyncio.Lock` + `_inflight_*: dict[key, Task]` 로 **single-flight** — 동시 N 호출 시 첫 호출만 KIS fetch, 나머지는 task 합류로 KIS 호출 정확히 1회. 무효화: TTL 자동 만료 + `clear_caches()` 헬퍼(스케줄러 `_reset_daily_state` 가 매일 20:10 정산 후 호출). **사용 범위 안전 가드**: 스캐닝/조건검사 한정 — `execute_buy/execute_sell` 의 체결가/주문가 결정 경로는 절대 사용 금지(WebSocket tick 또는 직접 호출 유지)
- **PR-C2 (2026-05-14) — Task + shield + epoch 가드 재설계** (Copilot 리뷰 8건): single-flight 공유 객체를 `asyncio.Future` → `asyncio.Task` 로 전환하고, joiner 는 `await asyncio.shield(task)` 로 합류한다. (1) 자기 task cancel 시 inflight task 자체로의 cancel 전파 차단 — 다른 joiner 가 `CancelledError` 잘못 받거나 fetch 담당이 `set_result/set_exception` 시점에 `InvalidStateError` 터지는 결함 차단. (2) `asyncio.get_event_loop()` 미사용 — Task 패턴은 loop 직접 참조 불필요(Py 3.12+ deprecation 회피). (3) helper 안에 `except` 없음 — `CancelledError` 가 `Exception` 분기로 잘못 흡수되는 경로 자체 제거(joiner 가 await 로 예외를 정상 회수해 "Future exception was never retrieved" 운영 잡음도 무발생). (4) `clear_caches()` 가 `_cache_epoch` bump — `_fetch_*_and_cache` helper 가 시작 시점 epoch 를 캡처해 완료 시점 `_cache_epoch` 와 일치할 때만 cache write. 진행 중 inflight 가 새 영업일 캐시에 stale write 하던 결함 차단. inflight task 자체는 cancel 안 함(이미 호출자가 await 중 — unexpected `CancelledError` 전파 위험). inflight 정리는 helper `finally` 에서 `_inflight_*[key] is asyncio.current_task()` 일 때만 pop — race 안전. 회귀 테스트: `tests/unit/api/test_condition_cache.py` 17건 (cancel 안전성/epoch race/get_running_loop 사용/Future exception 미발생 × 2 함수)

## 새 API 추가 절차
1. `docs/kis/{category}.md`에서 TR_ID, URL, 파라미터 확인
2. 이 디렉토리에 함수 추가 (반드시 `kis_request()` 사용)
3. TR_ID�� `settings.get_tr_id("실전TR_ID")` 사용
4. 응답 ��델은 `models/`에 pydantic으��� 정���
