# CLAUDE.md — src/api/ (KIS REST API)

KIS OpenAPI REST 호출 모듈. 모든 호출은 `base.py` 공통 래퍼를 통한다.

> 사이클별 변경 이력: `docs/HARNESS_CHANGELOG.md`

## base.py — 공통 래퍼 (메인 단일)

- `kis_request(method, url, tr_id, ...)`: 모든 KIS API 호출의 단일 진입점
- 헤더 자동 구성: authorization, appkey, appsecret, tr_id, custtype("P")
- Rate Limit: `asyncio.Semaphore(20)` 초당 20건 제한
- 에러 처리: `rt_cd != "0"` 시 msg_cd + msg1 로깅
- 자동 재시도: 네트워크/5xx 최대 3회, 지수 백오프 (`BACKOFF_BASE=0.5s × 2^(attempt-1)`) + jitter (`0~BACKOFF_JITTER=0.25s`) — thundering herd 완화
- 토큰 만료 감지 시 자동 갱신 후 재시도. **사이클 181 (2026-06-28) — 토큰만료 분기 msg_cd 화이트리스트 전환 (base-1 HIGH)**: `_request` + `_request_via_quote_pool` 양쪽 토큰 분기 조건이 `"token" in msg1.lower() or "만료" in msg1` 순수 substring 이라 `EGW00120`("기간이 만료된 code", 본 프로젝트는 예수금부족 변형으로 활용 = `is_insufficient_cash` 화이트리스트)의 "만료" 를 토큰만료로 오분류 → 불필요 `token_manager.issue()`(`auth/token.py` `_ISSUE_GAP_SECS=61` 전역 직렬 락 → ~N×61초 그리드락 = 아침 잔고500 halt 증폭) + 동일 주문 body 재전송(중복 체결). 시정 = 모듈 frozenset `_TOKEN_EXPIRED_MSG_CODES = {EGW00121, EGW00122, EGW00123}`(access token 3종, `issue()` 가 올바른 복구 — session_key EGW00124~126 제외 = 재발급 미해소 footgun) + `_TOKEN_BRANCH_EXCLUDE_CODES = {EGW00120, APBK0919, APBK0918}` + 조건 `msg_cd in 화이트리스트 OR ("token" in msg1.lower() AND msg_cd not in 배제 AND "부족" not in msg1)` (hybrid = 화이트리스트 주 + 영문 "token" 폴백 보험). `"만료" in msg1` 절 영구 폐기. 토큰 분기 본체(`issue()`+`continue`+`[api_retry_exhausted] last_status=token_expired` R7) 변경 0. 회귀 가드 `tests/unit/api/test_cycle181_token_expiry_whitelist.py`(12) + `tests/unit/ast/test_cycle181_token_whitelist_ast.py`(3, frozenset 엔트리 검사 = 사이클 167/179 패턴 + `"만료"` Compare 노드 0건). 매매 안전성 8영역 diff 0 (base.py = 주문 공통 래퍼이나 토큰 분기 외 변경 0 + api 전수 235 PASS)
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
- 화이트리스트 **7 path** 만 허용 (사이클 32 추가 → 사이클 89 `/quotations/volume-rank` 추가 → 사이클 109 `/ranking/market-cap` 추가 → **사이클 179 `/quotations/volume-rank` 폐기**): `/quotations/inquire-price` / `/quotations/inquire-daily-itemchartprice` / `/ranking/fluctuation` / `/quotations/search-stock-info` / `/quotations/chk-holiday` / `/quotations/inquire-ccnl` / `/ranking/market-cap`. 사이클 109 시정 = 사이클 101 도입 시점 silent 결함 (`_MARKET_CAP_URL` 화이트리스트 부재 → `_fetch_market_cap_page` → `QuotePoolPathError` raise → `_full_universe_load_once` total=0). **사이클 179 (2026-06-26) — `/quotations/volume-rank` (거래량순위 FHPST01710000) 폐기**: 사이클 108 에서 VB/LTV/BFB `_scan_universe` 가 `stock_master.list_by_filter`(DB) 로 전환되며 거래량순위 호출 0건 dead → 화이트리스트 잔존 path 제거. 재도입 영구 차단 = `tests/unit/api/test_cycle179_no_volume_rank_in_quote_allowlist.py` (frozenset 엔트리 검사, 사이클 167 dead code 폐기 패턴). 신규 path 추가 시 AST 정적 가드 의무 (`tests/unit/api/test_cycle109_market_cap_allowlist.py` 답습)
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

## kis_master.py — KIS 공식 일일 마스터 파일 (사이클 129, 2026-06-14)

KIS 공식 다운로드 (`https://new.real.download.dws.co.kr/common/master/`) 일일 마스터 파일 (`kospi_code.mst.zip` / `kosdaq_code.mst.zip`) cp949 fixed-width 파싱 → `list[dict]` → upsert. 매일 16:30 KST 자동 갱신 (사이클 122/126 task 패턴 답습 + 사이클 127 fire-and-forget).

> **구현 방식 (KIS 공식 샘플 대비 의도된 변경)**: KIS 정제 샘플 (`kis_kospi_code_mst.py` / 구조체 `.h`) 의 pandas (`read_csv` + `read_fwf` + Excel 출력) + 디스크 파일 방식을 폐기하고, **`struct.unpack` 순수 파싱 + `httpx.AsyncClient` 메모리 처리 (`io.BytesIO`, 디스크 I/O 0)** 로 이식. field_specs / 필드 순서는 샘플과 100% 일치, 후미 byte 만 정본 정합값(227/221)으로 보정 (샘플 228/222 는 텍스트 모드 줄바꿈 여유분). pandas 의존성 없음.

### URL 정본 (KIS 공식 저장소 검증 확정)

- KOSPI: `https://new.real.download.dws.co.kr/common/master/kospi_code.mst.zip` (cp949, part2 70 컬럼, 후미 `KOSPI_TAIL_BYTES=227`)
- KOSDAQ: `https://new.real.download.dws.co.kr/common/master/kosdaq_code.mst.zip` (cp949, part2 64 컬럼, 후미 `KOSDAQ_TAIL_BYTES=221`)
- part1 = 단축코드 9 byte (`SHORT_CODE_LEN`) + 표준코드 12 byte (`STND_CODE_LEN`) + 한글명 가변

### 함수 영역 (실제 시그니처)

- `async def download_kospi_master() -> list[dict]` — KOSPI ZIP 다운로드 + cp949 파싱 통합 (인자 없음). record 키 = part1 3종 (`mksc_shrn_iscd` 6자리 단축코드 / `stnd_iscd` / `hts_kor_isnm`) + part2 70 컬럼 (`KOSPI_FIELD_NAMES`)
- `async def download_kosdaq_master() -> list[dict]` — KOSDAQ 동일 (part2 64 컬럼 `KOSDAQ_FIELD_NAMES`, KOSDAQ 전용 `vntr_issu_yn` 벤처기업 / `invt_alrm_yn` 투자주의환기 / `ksq150_nmix_yn` KOSDAQ150 포함)
- `async def download_master_zip(url: str) -> bytes` — ZIP bytes 다운로드 (SSL 옵션 C)
- `def _parse_master_records(raw_bytes, tail_bytes, field_specs, field_names) -> list[dict]` — KOSPI/KOSDAQ 공통 fixed-width 파서 (내부 헬퍼). `struct.unpack` + `assert struct_size == tail_bytes` 정합 가드
- `def decode_korean(raw_bytes: bytes) -> str` — cp949 디코드 (`UnicodeDecodeError` → `errors="replace"` graceful)
- **통합 함수 없음** — KOSPI/KOSDAQ 각각 호출. 통합·source 태깅은 호출자 `scanner._stock_master_master_load_once()` 가 `tagged_records: list[tuple[str, dict]]` 로 수행

### SSL 옵션 C (사이클 129 domain-consult 채택)

- `httpx.AsyncClient(verify=True)` 우선 (운영 보안)
- 폴백: `httpx.ConnectError` + SSL/certificate 키워드 시만 `verify=False` 재시도 + WARNING 로그 (그 외 에러는 전파)
- `ssl._create_unverified_context` (사용자 샘플 무조건 검증 off) 영구 폐기

### 매매 활용 키 ~30 (사이클 129 domain-consult 의제 4 확정)

- 진입 차단 7건 (HIGH): `trht_yn` 거래정지 / `mang_issu_yn` 관리종목 / `ssts_hot_yn` 공매도과열 / `stange_runup_yn` 이상급등 / `sltr_yn` 정리매매 / `mrkt_alrm_cls_code` 시장경고 / `invt_alrm_yn` 투자주의환기 (코스닥 전용)
- 시총: `prdy_avls_scal` 전일 시가총액 (**억 원**). 시총 필터는 `list_by_filter` / `list_paged_by_filter` 가 `raw.hts_avls`(억원) 기준 직접 수행 (사이클 166 억원 정합)
- 재무: `roe` / `sale_account` 매출액 / `bsop_prfi` 영업이익 / `op_prfi` 경상이익 / `thtr_ntin` 당기순이익
- 지수편입: `kospi200_apnt_cls_code` / `kospi100_issu_yn` / `kospi50_issu_yn` / `ksq150_nmix_yn` / `krx300_issu_yn` / `krx_issu_yn`
- 시장 영역: `lstn_stcn` 상장주수 (천주) / `cpfn` 자본금 / `marg_rate` 증거금비율 / `crdt_able` 신용가능
- 기타: `stck_lstn_date` 상장일자 / `po_prc` 공모가 / `prst_cls_code` 우선주 / `byps_lstn_yn` 우회상장 / `flng_cls_code` 락구분 / `short_over_cls_code` 단기과열 / `insn_pbnt_yn` 불성실공시

### 단위 환산 (사이클 129 Q12, × 100)

- `prdy_avls_scal` (KIS 마스터) = **억 원** (구조체 `.h` 명세 "전일기준 시가총액 (억)" 기준. 1 억 = 100,000,000 원 = 100 백만원)
- `hts_avls` (KIS API FHKST01010100 inquire_price "HTS 시가총액", 사이클 116) = **억원** (사이클 166 확정 — 아래 참조)
- **사이클 167 — 시총 헬퍼 3개 dead code 폐기**: `market_cap_master_to_millions` / `validate_market_cap_consistency` / `get_market_cap_millions` 영구 폐기 (callsite 0건). 실제 시총 필터는 `list_by_filter` / `list_paged_by_filter` 가 `raw.hts_avls`(억원) 직접 비교 (사이클 166). AST 영구 가드 = `tests/unit/ast/test_cycle167_ast_no_dead_market_cap_funcs.py`.
- ✅ **단위 확정 (운영 DB 실측 검증 완료, 사이클 164 인계 종결)**: 대형주 6종목 전수에서 `종가 × 상장주수(천주) ÷ prdy_avls_scal = 정확히 100,000` → 실제 시총(원) = `prdy_avls_scal × 10⁸` → **`prdy_avls_scal` = 억원 확정**. `× 100` 환산 정확. **사이클 164 "백만원 의심" = false alarm 기각**.
- ✅ **hts_avls 단위 충돌 종결 (사이클 166, 2026-06-19)**: 운영 DB 대형주 9종목 전수 `실제시총(원) / hts_avls ≈ 10⁸` → **`hts_avls` = 억원 확정**. median 933(=933억원) 분포도 한국 상장사 중앙값과 정합. 사이클 108/128 "백만원" 가정은 silent 결함 (100배 어긋남 → min_market_cap=1,000억 시 후보 풀 1,734 → 80, 95.4% 축소). **시정**: `list_by_filter` (python `hts_avls × 100_000_000`) + `list_paged_by_filter` (jsonb `min_market_cap // 100_000_000`) + scanner KRX 폴백 (`// 100_000_000`) + 프론트 `formatMarketCap` 모두 억원 통일. DB 재적재 불필요 (16:10 KIS task 가 억원으로 덮어씀). `get_market_cap_millions` / `validate_market_cap_consistency` / `market_cap_master_to_millions` 는 production 미사용 → **사이클 167 dead code 폐기**. 회귀 가드: `tests/unit/db/test_cycle166_hts_avls_unit_correction.py` + `tests/unit/engine/scanner/test_cycle166_krx_fallback_eok_unit.py` (AST 단위 가드 `1_000_000` 잔존 0건) + `tests/unit/ast/test_cycle167_ast_no_dead_market_cap_funcs.py` (3 함수 폐기 가드).

### 호출자

- `src/engine/scanner.py::_stock_master_master_load_once()` — 다운로드 + 파싱 + `stock_master.upsert_master_raw()` 배치 + emit
- `src/engine/scheduler.py::_stock_master_master_load_task_loop()` — 16:30 KST 자동 task lifecycle
- `src/routes/stock_master.py::refresh_master_now()` — POST `/api/stock-master/master/refresh` 수동 trigger (BackgroundTasks fire-and-forget)

## krx.py — KRX 정식 OPEN API 클라이언트 (사이클 112 + 사이클 115)

KRX Data Marketplace (openapi.krx.co.kr) 정식 OPEN API 호출 모듈. KIS OpenAPI 와 완전 분리된 별개 시스템.

### 사이클 115 (2026-06-12) — 4 endpoint 함수 실제 통합 + 사이클 112 추상 결함 3건 시정

사용자 결정 (확정): Q1=양쪽 통합 (bydd_trd + isu_base_info) + Q3=C 폴백 영속 (KRX 1차 + KIS 자동 폴백).

외부 검증 정본 (2건 독립 일치):
- `seobaeksol/krx-rs/docs/krx-api-reference/KRX_API_Spec.md` (응답 schema 28KB)
- `raccoonyy/pykrx-openapi/src/pykrx_openapi/client.py` (정본 코드 인용):
  `response = self.session.get(url, params=params, timeout=self.timeout)`
  `params = {"AUTH_KEY": self.api_key, "basDd": bas_dd}`

**사이클 112 추상 결함 3건 시정**:

| 항목 | 사이클 112 (결함) | 사이클 115 (정본 영구 영속) |
|------|------------------|---------------------|
| HTTP method | POST | **GET** |
| 인증 위치 | HTTP header `AUTH_KEY:` | **query parameter `AUTH_KEY=`** |
| 파라미터 위치 | JSON body | **query string `params=`** |

**신규 함수 4종**:

| 함수 | endpoint | 응답 필드 수 | 용도 |
|------|----------|------------|------|
| `fetch_stk_bydd_trd(date)` | `/sto/stk_bydd_trd` | 15 | KOSPI 일별 매매정보 (KIS market-cap 영역 대안) |
| `fetch_ksq_bydd_trd(date)` | `/sto/ksq_bydd_trd` | 15 | KOSDAQ 일별 매매정보 |
| `fetch_stk_isu_base_info(date)` | `/sto/stk_isu_base_info` | 12 | KOSPI 종목 기본정보 (CTPF1002R 영역 대안) |
| `fetch_ksq_isu_base_info(date)` | `/sto/ksq_isu_base_info` | 12 | KOSDAQ 종목 기본정보 |

응답 형식: `{"OutBlock_1": [{...}, ...]}` JSON 배열 (누락 시 빈 리스트 graceful).

**bydd_trd 핵심 15 필드** (사이클 108 직접 정합):
- `ISU_CD` (단축코드 6자리, KRX 종목코드 정합) / `ISU_NM` / `MKT_NM` / `SECT_TP_NM`
- 가격: `TDD_CLSPRC` / `TDD_OPNPRC` / `TDD_HGPRC` / `TDD_LWPRC` / `CMPPREVDD_PRC` / `FLUC_RT`
- 거래: `ACC_TRDVOL` / **`ACC_TRDVAL`** (원 단위, 사이클 108 `min_trade_amount` 직접 정합)
- 시총: **`MKTCAP`** (원 단위) → KIS `hts_avls` (억원) 환산 `// 100_000_000` (사이클 116 → 166 정정, 단위 혼재 제거)
- 상장: `LIST_SHRS`

**isu_base_info 12 필드** (ticker 정합):
- `ISU_CD` (12자리 표준코드, **사용 금지** — stock_master PK 비정합)
- **`ISU_SRT_CD`** (단축코드 6자리, KRX 종목코드 정합)
- `ISU_NM` / `ISU_ABBRV` / `ISU_ENG_NM` / `LIST_DD` (상장일)
- `MKT_TP_NM` / `SECUGRP_NM` (증권구분) / `SECT_TP_NM` / `KIND_STKCERT_TP_NM` (보통주/우선주)
- `PARVAL` (액면가) / `LIST_SHRS`

**Q3=C 폴백 패턴** (호출자 `src/engine/scanner.py::_full_universe_load_once`):
- KRX 1차 우선 호출 (4 endpoint + 50ms sleep × 3건 = KIS LMS chain 안전 마진 답습)
- KrxApiError (비활성/401/4xx/5xx/네트워크 예외) 시 KIS market-cap 자동 폴백 (사이클 101+109+110 영속)
- 양쪽 모두 실패 시 raise (사이클 110 graceful 패턴 영속)

**보안**:
- 평문 key 는 query parameter 에만 사용 — URL 전체 로그 금지 (endpoint_path 만 로그)
- KrxApiError 메시지에도 평문 key 노출 0건
- 사이클 17 KIS 인증 보안 패턴 답습 + 사이클 112 영속

**graceful 정책 영속**: 4 endpoint 모두 `KrxApiError` 전파 → 호출자 (사이클 115 영역 2) Q3=C 폴백 의무. 사이클 88 G-REJECT 영속.

**Rate Limit 영속**: 키당 일일 10,000 호출 (4 호출/일 = 0.04% 영역, 무관).

**회귀 가드 23 케이스 영속**:
- `tests/unit/api/test_cycle112_krx_client.py` (5, 사이클 115 GET method 시정 영속)
- `tests/unit/api/test_cycle115_krx_endpoints.py` (6, HIGH-2 4 endpoint + graceful + 전파)
- `tests/unit/engine/scanner/test_cycle115_full_universe_load_krx_fallback.py` (5, HIGH-3 폴백 + HIGH-4 Rate Limit + MEDIUM-1 raw merge)
- `tests/unit/ast/test_cycle115_krx_endpoint_urls.py` (4, AST 영구 가드)
- `tests/unit/ast/test_cycle115_krx_no_plaintext_key.py` (3, 보안 영구 가드)

### 사이클 112 (2026-06-12) — 인프라 사전 구성

KRX 키 관리 인프라 + Supabase 저장 + 마스킹. 본 사이클 = 인프라만 (호출 0건, 호출 사이트는 사이클 115 영속).

- `KrxApiError` 예외 클래스 (사이클 88 G-REJECT 영속)
- `fetch_krx_open_api(endpoint_path, params)` 추상 (사이클 115 시정 = GET + query params + AUTH_KEY query 영속)
- Supabase 동적 키 로드 (`get_krx_open_api_config()`)

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
- `add_business_days(base_date, n)` (사이클 191): base_date 이후 n번째 개장일 date. CTCA0903R 1회 호출(~30일치)에서 `opnd_yn=="Y"` n번째 row. 실패/개장일 부족 시 `base + timedelta(n+2)` 달력일 폴백 graceful. BFB/VCP 재진입 쿨다운 영업일 정정용 (`_refine_cooldown_business_days` 소비)
- `fetch_daily_candles(ticker, days)`: 일봉 N영업일치. `FHKST03010100` (`/quotations/inquire-daily-itemchartprice`, 모의/실전 동일) — **단일 호출 최대 100일**. 응답 `output2` (최신순), `stck_bsop_date` 빈 placeholder 제거. 윈도우 = `days + days//2 + 10` (영업일/달력일 5/7 + 마진)
- **사이클 172 (2026-06-22) — 분할 fetch (날짜 윈도우 100건 경계) + 220일 backfill (VCP 220일 확보, 사이클 173 prepare DB일봉 전환 선행)**:
  - `fetch_daily_candles_ranged(ticker, start_yyyymmdd, end_yyyymmdd) -> list[dict]`: KIS `FHKST03010100` 단일 윈도우 조회 (`FID_INPUT_DATE_1`=시작 / `FID_INPUT_DATE_2`=종료 / `FID_PERIOD_DIV_CODE="D"` / `FID_ORG_ADJ_PRC="0"` / `FID_COND_MRKT_DIV_CODE="J"`, KIS MCP 정본 재확인 완료). `kis_get_quote` 경유 (시세성 풀 + Rate Limit + 메트릭). output2 (최신순) + `stck_bsop_date` 빈 placeholder 제거. **memcache/single-flight 미사용** (backfill 전용, 16:00 daily task 만 호출). 6자리 ticker 가드 (`ValueError`). **`FID_ORG_ADJ_PRC="0"` (수정주가) = 기존 `_fetch_daily_candles_and_cache` 정합** — 사이클 173 DB-source vs KIS-source 동등성 게이트 보장 (정본 샘플 "1" 예시이나 본 코드베이스는 사이클 14부터 "0" 사용).
  - `fetch_daily_candles_backfill(ticker, total_days=220, *, window=100) -> list[dict]`: N일 backfill = 날짜 윈도우 ×`ceil(N/window)` 순차 호출 + 병합. 220일 = 100일 윈도우 ×3 (T-308~T-215 / T-215~T-126 / T-126~T 영업일 환산, 경계 겹침 → dedupe). 중복 `stck_bsop_date` dedupe + bas_dd DESC 정렬. 윈도우 간 50ms sleep (`_DAILY_BACKFILL_WINDOW_SLEEP_SECS`, 사이클 17 KIS LMS chain). 개별 윈도우 실패 graceful (사이클 88 G-REJECT, 다음 윈도우 진행).
  - **기존 `fetch_daily_candles` 변경 0** (memcache 5분 + single-flight + `asyncio.shield` 영속) — 별도 함수. 호출자 = `scanner._stock_master_daily_load_once` (VCP universe 220일 분기, 16:00 daily task 만). **매매 안전성 무영향** (데이터 적재 한정, scanner 매수 진입 전 영역, 사이클 38 명문화). 회귀 가드 = `tests/unit/api/test_cycle172_daily_ranged_backfill.py` (RANGE 4 + BACKFILL 4 + AST).
- **`inquire_stock_basics(pdno) -> StockBasics`**: KIS `CTPF1002R` — NXT 거래종목 (`cptt_trad_tr_psbl_yn`) + NXT 거래정지 (`nxt_tr_stop_yn`) + KRX 정지 + 관리종목 파싱 → `StockBasics` 반환. 파생값 `nxt_tradable = (cptt=="Y") AND (nxt_stop=="N")`. CTPF 접두사 TR_ID 는 모의/실전 동일. 캐시 `src.db.stock_master` 24h TTL. **ticker 정규화**: `_normalize_ticker()` 가 KIS `pdno` 12자리 표준코드 → KRX 6자리 단축코드 추출 (정규식 `(\d{6})$`). `stock_master` PK 정합성 보장. `docs/kis/error-codes.md` 5-3절
- **사이클 145 (2026-06-16) — `inquire_stock_basics` FHKST01010100 raw 0 덮어쓰기 금지 graceful (결함 #2, HIGH 매매 안전성 직결)**: 운영 사례 (Supabase MCP 진단) = 2026-06-16 07:54~07:59 KST = boot `force=True` (장 시작 *전*) 시점 + stock_master 2,697 ticker 중 `acml_tr_pbmn > 0` = **3 종목만** 잔존 silent 결함. 근본 원인 = FHKST01010100 응답 `acml_tr_pbmn=0` + `acml_vol=0` 정상 (장 시작 전 거래 없음) → `inquire_stock_basics` merge 영역에서 기존 raw 덮어쓰기 → `stock_master.list_by_filter(acml_tr_pbmn ≥ min_trade_amount=20_000_000_000)` 0건 silent → donchian/VB/LTV 후보 0 결함. **시정 (+20L net)**: merge 영역에서 `("acml_tr_pbmn", "acml_vol")` 키 = `int(str(value).replace(",", "") or 0) == 0` 가드 → 0 값 `continue` skip → 기존 raw 키 보존 (전일 영업일 거래대금 보존). `("lstn_stcn", "prdy_vrss", "hts_avls")` = 변경 0 (정상 덮어쓰기). 비숫자 = `except (ValueError, TypeError)` graceful → 정상 그대로 merge. **사이클 81 G-AST1 강화** (raw 덮어쓰기 금지 영속) + 사이클 88 G-REJECT graceful 영속. **회귀 가드 4 케이스 (`tests/unit/api/test_cycle145_raw_preserve.py`)**: G-145-RAW-1 (acml_tr_pbmn=0 응답 → 기존 raw 키 보존 + 다른 정상 키 정상 merge `hts_avls` / `lstn_stcn`) + G-145-RAW-2 (acml_tr_pbmn>0 정상 응답 → 정상 덮어쓰기) + G-145-RAW-3 (acml_vol=0 시 동일 보존) + G-145-RAW-4 (AST 정적 가드 = `numeric_value == 0`). **영속 의무 매트릭스**: 사이클 81 G-AST1 강화 + 사이클 88 G-REJECT graceful 영속 + 사이클 107 CTPF1002R + FHKST01010100 merge 패턴 영속 (변경 0 = 0 가드 추가만) + 사이클 108 list_by_filter (`acml_tr_pbmn ≥ min_trade_amount`) 정합 영속 + 사이클 122~144 영속 (영향 0). **매매 안전성 직접 검증**: scanner 매수 진입 *전* 한정 (사이클 38 명문화 영속) + stock_master raw 보존 → list_by_filter 정상 작동 → donchian/VB/LTV 후보 영속 → 매매 안전성 영향 0 (기존 raw 보존). **D+1 운영 효과 (2026-06-17~)**: 16:30 `_stock_master_master_load_once` 자동 발화 + 16:10 `_stock_master_basics_refresh_once` 자동 발화 = 거래대금 정상 적재 → list_by_filter 정상 작동 → donchian/VB/LTV `prepare()` 호출 시 유의미한 후보 영속.
  - **⚠️ 사이클 176 (2026-06-25) 정정 — 사이클 145 "기존 raw 키 보존" 은 사실상 no-op 이었음**: `inquire_stock_basics` 가 `merged_raw = dict(ctpf_output)` 로 raw 를 **CTPF 에서 신규 빌드** (기존 DB raw 미read) → CTPF 에 거래대금 키 부재 + FHKST 0 skip → merged_raw 거래대금 부재 → `upsert_one` raw 통째 교체 → 거래대금 영구 소멸. cycle 145 의 `continue` skip 은 "0 값을 merged_raw 에 *안 넣는다*" 일 뿐, *기존 DB raw 와 머지* 가 아니므로 보존 효과 0. 운영 실측 (2026-06-25) = 거래대금 보유 6/3573, VB/LTV/donchian/BFB universe 0 race. **실제 시정 = `src/engine/scanner.py::_stock_master_basics_refresh_once` 가 기존 DB raw 를 보관 → upsert 전 `{**기존, **신규}` 머지** (`_ZERO_VALUE_SKIP_KEYS` 15키 기존 값 보존, 새 키 우선). 회귀 가드 = `tests/unit/engine/test_cycle176_basics_refresh_raw_merge.py` (5).
  - **사이클 177 (2026-06-26) — None/비숫자 하드닝**: 사이클 176 정밀검증(end-to-end `test_cycle176_e2e_premarket_preservation.py` 5건) 중 발견 — skip-키 `value=None` 시 cycle 145 가드 `float("None")` ValueError → `except: pass`(merge) → `merged_raw[key]=None` → 기존 거래대금 None 덮어씀(소실, FHKST 는 장전 "0" 반환이라 이론적). 하드닝 = 가드 except 분기 `pass` → **`continue`** (skip-키 15개 전부 숫자 필드 → 비숫자/None=junk → 덮어쓰지 않고 기존값 보존). cycle 145 `if numeric_value == 0.0: continue` 불변(G-145-RAW-4 유지), cycle 155 비숫자-merge 단언은 비-skip 키 한정이라 회귀 0.
- **사이클 144 (2026-06-16) — `inquire_stock_basics` graceful 분기 가시화 강화 (카드 #27 LOW)**: 사이클 130 권고 카드 #27 (NEW LOW, 사이클 129/132 인계) 종결. **현행 silent fail**: 사이클 107 도입 FHKST01010100 호출 실패가 `try/except: logger.exception` + `price_data = {}` graceful fallback 만 영역 = scanner `_stock_master_basics_refresh_once` summary 가시화 불가 (사이클 129 OPSQ1002 SESSION FULL graceful 처리 silent). **시정 (production +53L)**: `condition.py` 모듈 전역 `_graceful_failed_counter: dict[str, int]` 신규 + `_graceful_failed_lock: asyncio.Lock` (FastAPI 동시 요청 + BackgroundTasks 동시성 보호) + 3 헬퍼 (`_record_graceful_failed(reason: str)` 비동기 카운터 증가 / `get_graceful_failed_counts() -> dict` 스냅샷 사본 반환 / `reset_graceful_failed_counts()` 초기화). `inquire_stock_basics` FHKST01010100 except 분기에 `_record_graceful_failed("fhkst01010100_failed")` 호출 신규 (try/except 외부 영향 0). **scanner summary +21L**: `_stock_master_basics_refresh_once` 시작 시 `reset_graceful_failed_counts()` 호출 (단일 task 측정 의무) + 종료 시 `get_graceful_failed_counts()` 수집 + `summary["graceful_failed"]` 키 ("fhkst01010100_failed" 카운터) + emit 로그 `[stock_master_basics_refresh_summary] ... graceful_failed_fhkst=%d ...` 필드 추가. **회귀 가드 10 케이스 (`tests/unit/api/test_cycle144_graceful_visibility.py`)**: G-144-COUNTER-1~4 (모듈 전역 dict + 카운터 증가 + snapshot + reset 영속) + G-144-INT-1~3 (FHKST01010100 RuntimeError → 카운터 +1 + 양쪽 정상 → 변경 0 + KisApiError "OPSQ1002 SESSION FULL" → 카운터 +1, 사이클 129 가시화 직접 검증) + G-144-SUMMARY-1~2 (summary `graceful_failed` 키 + emit `graceful_failed_fhkst=N` 필드) + G-144-AST-1 (inquire_stock_basics graceful 분기 `_record_graceful_failed` 호출 ≥ 1건 AST 정적 가드, 미래 동일 silent 결함 영구 차단). **영속 의무 매트릭스**: 사이클 17 KIS LMS chain (변경 0) + 사이클 38 명문화 (logging 한정) + 사이클 79 G-AST2 / 81 G-AST1 (영향 0) + 사이클 88 G-REJECT graceful 영속 (강화 = silent → 가시화) + 사이클 107 `inquire_stock_basics` CTPF1002R + FHKST01010100 merge 패턴 영속 (변경 0 = except 분기 카운터 호출만 추가) + 사이클 122~143 영속 (영향 0) + CLAUDE.md "절대 깨지 말 것" 8 영역 영속. **매매 안전성 무영향 확정**: logging + 카운터 한정 (process-local in-memory, uvicorn 단일 워커 영속 의무) + `src/engine/risk.py` / `src/engine/order_engine.py` / `src/realtime/` / `src/auth/` 변경 0 + 매수 진입 hot path 영향 0 + 매도/익일청산/15:20 강제청산 hot path 무관. **운영 효과**: 6/16 KST 16:10 `_stock_master_basics_refresh_task` 자동 발화에 `[stock_master_basics_refresh_summary]` 로그에서 `graceful_failed_fhkst=N` 필드 = 운영자 즉시 진단 ("FHKST01010100 KIS SESSION FULL N건 graceful 처리") + Loki 파싱에서 사이클 129 silent 결함 추세 측정 가능. **사이클 129 OPSQ1002 SESSION FULL 인계 종결**: 사이클 132 카드 #27 silent fail 가시화 결핍 시정 완료. team-leader 자체 결정 (사용자 결정 Q1=A 사이클 143 commit `ed8298b` + CI success 4분 26초 + EC2 Deploy success 35초 영속).
- **사이클 108 (2026-06-11) — `inquire_stock_basics` `hts_avls` 5번째 키 보강 (Plan Phase A 완료, 시총 데이터 확보)**: 사이클 104 인계 Q5=B (LOW 위험 자문 생략) + 사이클 107 raw 보강 의존성 해소 완료 → Plan Phase A 데이터 활용 가능 → 사이클 108 = `inquire_stock_basics` `hts_avls` 1 키 보강 + `stock_master.list_by_filter()` 신규 메서드 + VB/LTV/BFB `_scan_universe()` 전환 통합. 사용자 결정 Q1=A 시총 = `hts_avls` (KIS FHKST01010100, 백만원 단위, KIS 정본 인용 의무 = `chk_inquire_price.py` + 사이클 98 G-DOC1 답습). **시정 (production 1 파일, +1L 순증)**: 사이클 107 4 키 (`acml_tr_pbmn` + `lstn_stcn` + `acml_vol` + `prdy_vrss`) → 사이클 108 5 키 보강 = `hts_avls` 추가 (FHKST01010100 응답 = 시가총액 백만원 단위). for loop 4 키 → 5 키 (`if key not in merged_raw` 덮어쓰기 금지 영속). **CTPF1002R 기존 키 덮어쓰기 금지 설계**: 사이클 81 G-AST1 정합 (`bfdy_clpr` + 사이클 100 3 prefix OR + 사이클 101 `_full_universe_load_once` 자동 반영 영속 + `hts_avls` 덮어쓰기 금지). KIS MCP 정본 = `chk_inquire_price.py` main 호출 인용 의무 (사이클 98 G-DOC1 답습). **회귀 가드 (HIGH)**: `tests/unit/api/test_cycle108_hts_avls.py` = `hts_avls` 5번째 키 영속 + 덮어쓰기 금지 + AST 영구 가드. **호출**: `stock_master.upsert_one(ticker, ...)` 경로 + 사이클 101 `_full_universe_load_once` 배치 호출 (2,800 종목 × 2 KIS 호출 + 50ms sleep = 약 5분 소요). **운영 효과 (push + EC2 자동 배포 후)**: `inquire_stock_basics` 1회 호출 → stock_master.raw 에 `acml_tr_pbmn` + `lstn_stcn` + `acml_vol` + `prdy_vrss` + `hts_avls` 자동 포함 → 사이클 108 `stock_master.list_by_filter(min_market_cap=, min_trade_amount=)` 데이터 의존성 해소. **영속 의무 매트릭스**: 사이클 32 R4 universe guard 영속 + 사이클 38 명문화 영속 (`inquire_stock_basics` = 매수/매도 진입 직전 lazy 호출 + 매수 진입 전 한정 영속) + 사이클 81 G-AST1 영속 (`bfdy_clpr` + `hts_avls` 덮어쓰기 금지 영속) + 사이클 88 G-REJECT 영속 + 사이클 98 G-DOC1 영속 (KIS 정본 인용 의무 = `chk_inquire_price.py`) + 사이클 101 영속 (`_full_universe_load_once` 자동 반영) + 사이클 102 G-REJECT 영속 + 사이클 106 영속 확인 (lifecycle race 차단) + 사이클 107 영속 확인 (raw 보강 4 키). **매매 안전성 무영향 확정** (`inquire_stock_basics` = 종목 마스터 캐시 한정 + 매수/매도 진입 직전 lazy 호출 + 매매 hot path 직접 영향 0 + Rate Limit 50ms sleep KIS LMS chain 안전)
- **사이클 107 (2026-06-11) — `inquire_stock_basics` raw 보강 (CTPF1002R + FHKST01010100 merge, Plan Phase A 데이터 의존성 영구 해소)**: **Phase 1 진단 결정적 발견 (KIS MCP 정본 확정)**: CTPF1002R 응답 67 컬럼 = 3 키 (`acml_tr_pbmn` 누적 거래 대금 + `lstn_stcn` 상장 주수 + `prdy_vol` 전일 거래량) **모두 부재 확정**. FHKST01010100 (`inquire_price` 주식현재가 시세, KIS 정본 `chk_inquire_price.py` 인용 의무 = 사이클 98 G-DOC1 답습) 응답 = 3 키 모두 **존재 확정** (`acml_tr_pbmn` + `lstn_stcn` + `acml_vol` 누적 거래량 (`prdy_vol` 동등) + `prdy_vrss` 전일 대비). **시정 (production 1 파일, +44L 순증)**: `inquire_stock_basics` 본체 보강 = CTPF1002R 호출 *후* `await asyncio.sleep(0.05)` Rate Limit (사이클 83/91/97 답습 영속 = KIS LMS chain 안전) → FHKST01010100 추가 호출 (`kis_get_quote(STOCK_PRICE_URL, "FHKST01010100", ...)` 시세성 풀 라우팅 + 메인 fallback) → try/except graceful (`price_data = {}` fallback + `[inquire_stock_basics] FHKST01010100 호출 실패 graceful` 로그) → `merged_raw = dict(ctpf_output)` + for loop 4 키 조건부 merge (`acml_tr_pbmn` + `lstn_stcn` + `acml_vol` + `prdy_vrss`, `if key not in merged_raw` 덮어쓰기 금지). **CTPF1002R 기존 키 덮어쓰기 금지 설계** = 사이클 81 G-AST1 정합 (`bfdy_clpr` 영속). **graceful fallback**: FHKST01010100 RuntimeError / KisApiError = CTPF1002R 단독 raw 반환 (호출자 보호). CTPF1002R 에러 = 전파. **회귀 가드 12 신규 (HIGH 4 케이스, `tests/unit/api/test_cycle107_inquire_stock_basics_merge.py`)**: HIGH-1 양쪽 API 호출 + CTPF 선행 순서 (2 sub-case) + HIGH-2 raw 3 키 포함 + `bfdy_clpr` 보존 + 덮어쓰기 금지 (3 sub-case) + HIGH-3 graceful fallback (RuntimeError / KisApiError / CTPF 에러 전파, 3 sub-case) + HIGH-4 AST 영구 가드 (FHKST01010100 문자열 + inquire-price URL + 60줄 윈도우 + 3 키 merge, 4 sub-case). **운영 효과**: `inquire_stock_basics` 1회 호출 → stock_master.raw 에 `acml_tr_pbmn` + `lstn_stcn` + `acml_vol` 자동 포함 / 2,800 종목 × 2 KIS 호출 + 50ms sleep = 약 5분 소요 (사이클 101 `_full_universe_load_task_loop` 배치 시 적용) / 향후 Plan Phase A (사이클 108+) `list_by_filter(min_market_cap=, min_trade_amount=)` 데이터 의존성 해소. **영속 의무 매트릭스 9 영역 전수 영속**: 사이클 32 R4 / 38 명문화 / 81 G-AST1 (`bfdy_clpr` 덮어쓰기 금지) / 88 G-REJECT / 98 G-DOC1 (KIS 정본 `chk_inquire_price.py` 인용 의무) / 101 영속 (`_full_universe_load_once` → `inquire_stock_basics` 호출 자동 반영) / 102 G-REJECT / 106 영속 (`_full_universe_load_task_loop` 변경 0) / CLAUDE.md "절대 깨지 말 것" 8 영역. **매매 안전성 무영향 확정** (종목 마스터 캐시 한정 + 매수/매도 진입 직전 lazy 호출 + 매매 hot path 직접 영향 0 + Rate Limit 50ms sleep KIS LMS chain 안전)

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
