> 원본: `src/api/CLAUDE.md` · 이관: 2026-09-17

KIS REST 호출 정본에서 걷어낸 경위·실측 수치·결정 근거. 규약 = [`README.md`](README.md).
원문 그대로 옮긴다(append-only). 사이클별 보고 원문은 [`../HARNESS_CHANGELOG.md`](../HARNESS_CHANGELOG.md) 에 있다.

절 제목은 **이관 시점의 정본 절 제목**이다.

---

## base.py — 공통 래퍼 (메인 단일)

### 2026-06-28 사이클 181 — 토큰만료 분기 msg_cd 화이트리스트 전환 경위

원문(`src/api/CLAUDE.md:14`, 2026-09-17 이관):

---

- 토큰 만료 감지 시 자동 갱신 후 재시도. **사이클 181 (2026-06-28) — 토큰만료 분기 msg_cd 화이트리스트 전환 (base-1 HIGH)**: `_request` + `_request_via_quote_pool` 양쪽 토큰 분기 조건이 `"token" in msg1.lower() or "만료" in msg1` 순수 substring 이라 `EGW00120`("기간이 만료된 code", 본 프로젝트는 예수금부족 변형으로 활용 = `is_insufficient_cash` 화이트리스트)의 "만료" 를 토큰만료로 오분류 → 불필요 `token_manager.issue()`(`auth/token.py` `_ISSUE_GAP_SECS=61` 전역 직렬 락 → ~N×61초 그리드락 = 아침 잔고500 halt 증폭) + 동일 주문 body 재전송(중복 체결). 시정 = 모듈 frozenset `_TOKEN_EXPIRED_MSG_CODES = {EGW00121, EGW00122, EGW00123}`(access token 3종, `issue()` 가 올바른 복구 — session_key EGW00124~126 제외 = 재발급 미해소 footgun) + `_TOKEN_BRANCH_EXCLUDE_CODES = {EGW00120, APBK0919, APBK0918}` + 조건 `msg_cd in 화이트리스트 OR ("token" in msg1.lower() AND msg_cd not in 배제 AND "부족" not in msg1)` (hybrid = 화이트리스트 주 + 영문 "token" 폴백 보험). `"만료" in msg1` 절 영구 폐기. 토큰 분기 본체(`issue()`+`continue`+`[api_retry_exhausted] last_status=token_expired` R7) 변경 0. 회귀 가드 `tests/unit/api/test_cycle181_token_expiry_whitelist.py`(12) + `tests/unit/ast/test_cycle181_token_whitelist_ast.py`(3, frozenset 엔트리 검사 = 사이클 167/179 패턴 + `"만료"` Compare 노드 0건). 매매 안전성 8영역 diff 0 (base.py = 주문 공통 래퍼이나 토큰 분기 외 변경 0 + api 전수 235 PASS)

---

→ CHANGELOG: 사이클 181 행. 현행 판정 규칙은 정본에 남겼다.

### 2026-09-11 cycle283 — 메트릭 reset 시각 종전 표기(20:10)

원문(`src/api/CLAUDE.md:15`, 2026-09-17 이관):

---

- 호출 메트릭: `_request_metrics` (전역 dict) `total/http_5xx/http_4xx/network_err/kis_error/retries/retry_recovered/retry_exhausted + path별 5xx top 5`. `get_request_metrics()` 스냅샷 / `reset_request_metrics()` 리셋. `log_analysis_engine.py` 가 **21:30** INSERT 후 reset (cycle283 D3, 종전 20:10 — **20:05 1차 스냅샷은 리셋하지 않는다**)

---

→ CHANGELOG: cycle283 D3 행

### 2026-06-08 사이클 76 — 5xx WARNING dedupe + recovered 5분 collector 도입 경위

원문(`src/api/CLAUDE.md:18`, 2026-09-17 이관):

---

- **사이클 76 (2026-06-08) — `_request` 5xx WARNING 60s dedupe + recovered 5분 collector (api 5.80x → 1.0~1.2 시정, 사이클 18 + 74 하이브리드 답습)**: 사이클 74 운영 실증 발견 `api` 5.80x dup (29/5) + `[api_retry_recovered]` 7.00x (14/2) 시정. **시정 사이트 2 영역**: 영역 1 `_request` (메인 단일, 사이클 18 dedupe 미적용 — 5.80x 주요인) + 영역 2 `_request_via_quote_pool` (시세 풀, 사이클 18 dedupe 영속 — recovered/exhausted 만 신규). **신규 함수 7 (`src/api/base.py` +150L)**: (1) `_record_request_5xx_for_dedupe(path, status) -> bool` — 메인 5xx WARNING 60s dedupe (사이클 18 `_record_5xx_for_dedupe` 답습, Q4 메인용 분리) + (2) `_record_api_recovered(path, attempts)` — 메인 retry 성공 누적 + (3) `_record_quote_recovered(path, attempts)` — 풀 retry 성공 누적 (Q4 분리) + (4) `_flush_api_recovered_collector()` — 5분 윈도우 종료 시 `[api_retry_recovered_summary] window=300s total=N by_path={...}` 1행 emit (Q2 빈 윈도우 skip) + (5) `_flush_quote_recovered_collector()` 동일 + (6) `_warn_http_status(status, attempt, max_retries, path)` — `logger.warning("HTTP %s ...")` 헬퍼 추출 (G-AST1 통과용) + (7) 모듈 상수 `_REQUEST_5XX_DEDUPE_WINDOW=60.0` / `_API_RECOVERED_COLLECTOR_WINDOW=300.0`. **State 3 (Q4 메인/풀 분리)**: `_request_5xx_dedupe: dict[(path, status), {first_at, count}]` (메인) ↔ `_quote_5xx_dedupe: dict[(path, label, status), {...}]` (사이클 18 영속) + `_api_recovered_collector: dict[path, {count, max_attempts}]` ↔ `_quote_recovered_collector` (분리). 호출 사이트 정정: `_request` L487 `_warn_http_status` 경유 + L545 `_record_api_recovered(path, attempt)` (기존 직접 `await write_log("INFO", "[api_retry_recovered]...")` 제거) + `_request_via_quote_pool` 동일 영역 `_record_quote_recovered` 호출. **ERROR 보존 매트릭스 4 영역 individual 영속 (변경 0, 사이클 29 005935 LMS chain 진단 의무)**: R2 `[api_retry_exhausted]` 5xx 최종 실패 (L495) + R4 네트워크 최종 실패 (L523) + R7 토큰 만료 최종 실패 (L563) + R8 `[kis_rejection]` (L590 메인 + L846 quote, CLAUDE.md "절대 깨지 말 것" 영속). **신규 task** (`src/engine/scheduler.py` +34L): `_api_recovered_collector_loop` 5분 주기 (사이클 42 `_heartbeat_metrics_loop` 답습) — `connect()` 시점 task 시작 + `disconnect()` cancel + await 정리 + 마지막 flush 1회 (Q5 사이클 74 답습) + `_flush_api_recovered_collector` + `_flush_quote_recovered_collector` 순차 호출. **AST 영구 가드 3 신설**: G-AST1 (`_request` 직접 `logger.warning("HTTP ...")` 0건, 헬퍼 경유만) + G-AST2 (사이클 18 `_record_5xx_for_dedupe` 호출 영속) + G-AST3 (`[api_retry_recovered]` 직접 write_log 0건, collector 경유만). **회귀 가드 15 케이스 (4 파일)**: G-MD1~MD4 메인 60s dedupe (freezegun) + G-RC1~RC4 5분 collector (freezegun) + G-ERR1~ERR4 ERROR 보존 매트릭스 영속 + G-AST1~AST3. 사이클 17 OPSP0002 backoff (`websocket.py`) + 사이클 18 풀 dedupe 영속 (변경 0). 운영 효과 예상 (push 후 측정): dup_factor api 5.80x → 1.0~1.2, recovered 7.00x → 1.0 (5분당 1행)

---

→ CHANGELOG: 사이클 76 행 (선행 = 사이클 18 · 74)

## base.py — REST 시세성 호출 풀

### 2026-05~2026-08 — 시세 풀 화이트리스트 path 누적·폐기 경위

원문(`src/api/CLAUDE.md:35`, 2026-09-17 이관):

---

- 화이트리스트 **13 path** 만 허용 (사이클 32 추가 → 사이클 89 `/quotations/volume-rank` 추가 → 사이클 109 `/ranking/market-cap` 추가 → **사이클 179 `/quotations/volume-rank` 폐기** → **사이클 C1 finance 5 path 추가** → **2026-08-04 `/quotations/inquire-vi-status` 추가**): `/quotations/inquire-price` / `/quotations/inquire-daily-itemchartprice` / `/ranking/fluctuation` / `/quotations/search-stock-info` / `/quotations/chk-holiday` / `/quotations/inquire-ccnl` / `/ranking/market-cap` / `/finance/income-statement` / `/finance/balance-sheet` / `/finance/profit-ratio` / `/finance/stability-ratio` / `/finance/other-major-ratios`. 사이클 109 시정 = 사이클 101 도입 시점 silent 결함 (`_MARKET_CAP_URL` 화이트리스트 부재 → `_fetch_market_cap_page` → `QuotePoolPathError` raise → `_full_universe_load_once` total=0). **사이클 179 (2026-06-26) — `/quotations/volume-rank` (거래량순위 FHPST01710000) 폐기**: 사이클 108 에서 VB/LTV/BFB `_scan_universe` 가 `stock_master.list_by_filter`(DB) 로 전환되며 거래량순위 호출 0건 dead → 화이트리스트 잔존 path 제거. 재도입 영구 차단 = `tests/unit/api/test_cycle179_no_volume_rank_in_quote_allowlist.py` (frozenset 엔트리 검사, 사이클 167 dead code 폐기 패턴). **사이클 C1 (2026-07-15) — 퀀트 재무필터 5 TR path 추가**: `src/api/finance.py::fetch_financial_tr` (5 TR — income/balance/profit/stability/other) 가 `kis_get_quote` 경유 → 화이트리스트 필수. 회귀 가드 `tests/unit/api/test_cycleC1_finance_allowlist.py` (frozenset 엔트리 + AST + 매매/잔고/체결 path 오염 미발생 검증). 신규 path 추가 시 AST 정적 가드 의무 (`tests/unit/api/test_cycle109_market_cap_allowlist.py` 답습) **2026-08-04 — `/quotations/inquire-vi-status` (VI 현황 FHPST01390000) 추가**: `market_operation.inquire_vi_status_today` 가 `kis_get_quote` 경유인데 사이클 149 도입 시점부터 화이트리스트에 없어 **매 부팅/재시작 QuotePoolPathError → VI 시드 100% 실패 + ERROR/traceback**(08-03 ERROR 15건 중 8건). 사이클 109 market-cap / C1 finance 와 **동일 클래스의 세 번째 누락**이며 코드 주석이 스스로 "화이트리스트 추가 의무"라 적어둔 채 미이행 상태였다. KIS 정본 = "변동성완화장치(VI) 현황" subcategory 업종/기타 = 시세성, 요청 파라미터 `FID_*` 전용(계좌·주문 식별자 없음) → 자금 안전 정책 부합. 실사용 = `stale_watcher_core.is_ticker_stale_excluded` (VI 발동 종목 stale 제외 → 강제 재구독 억제 = KIS LMS chain 위험 완화). **장중 재배포 시점**에 실효. 회귀 가드 `tests/unit/api/test_vi_status_quote_allowlist.py`(3, 화이트리스트 엔트리 + TR_ID 고정 + 매매성 path 오염 검사는 **세그먼트 판정** — 키워드 부분일치는 `finance/balance-sheet` 를 `inquire-balance` 로 오탐한다).

---

→ CHANGELOG: 사이클 32 · 89 · 109 · 179 · C1 행 + 2026-08-04 vi-status 행

### 2026-05-19 사이클 18 — FAST_WINDOW 추가 · 5xx 폭주 정리(A-1, A-3) 카드 서술

원문(`src/api/CLAUDE.md:60,62-66`, 2026-09-17 이관):

---

- **사이클 18 (2026-05-19) FAST_WINDOW 추가**: 기존 임계 (consecutive 5 / 5분 50%) + 1분 80% (`FAST_WINDOW_SECS=60`, `FAST_MIN_CALLS=10`, `FAST_MAX_FAILURE_RATE=0.8`). 영구 결함 라벨 (ISA 등 5xx 80%+) 빠른 탈락. 운영자 안내: 5xx 빈발 보조 라벨은 Settings UI active=false 수동 비활성 권장 — 자동 임계 도달 전 운영자 개입 가능

**사이클 18 (2026-05-19) 5xx 폭주 정리** (A-1, A-3):
- **WARNING dedupe** (`_record_5xx_for_dedupe(path, label, status) -> bool`): 동일 `(path, label, status)` 키 60s 윈도우 (`_QUOTE_5XX_DEDUPE_WINDOW=60.0`) 내 재발생 시 첫 1회만 WARNING + 카운트만 누적. ISA 같은 영구 5xx 라벨에서 분당 ~30 행 WARNING → 1행 + 60s summary INFO. lock `_quote_5xx_dedupe_lock` (asyncio.Lock) 동시성 보호
- **60s summary task** (`_emit_5xx_dedupe_summary()`): scheduler `_5xx_dedupe_summary_loop` 가 60s 주기 호출. 윈도우 만료 + 카운트 ≥ 2 인 키 1행 INFO `[quote_pool_5xx_summary] path=... label=... status=500 count=N within=60s` + dedupe state clear
- **메인 fallback 우선 (A-3)**: `_request_via_quote_pool` 의 라벨 선택 직후 `health_monitor.get_recent_5xx_ratio(label)` 조회. `total>=FAST_MIN_CALLS(10)` AND `ratio>=_LABEL_FALLBACK_5XX_RATIO_THRESHOLD(0.8)` 면 `label=None` 강제 (메인 fallback). 3회 재시도 backoff (수 초) 회피 → 응답 지연 ms 단위. 메트릭 `fast_fallback` 카운터 +1 운영 가시화
- **메트릭 확장**: `_quote_request_metrics["fast_fallback"]` 신규 — 80%+ 라벨 skip 누적 카운트. `get_quote_request_metrics()` / `reset_quote_request_metrics()` 동기화

---

→ CHANGELOG: 사이클 18 행

## order.py — 주문

### 2026-09-13 cycle291 — 취소 `ORD_DVSN` Stage A/B 명명과 전환 계획

원문(`src/api/CLAUDE.md:89`, 2026-09-17 이관):

---

  **취소(`cancel_order`)의 `ORD_DVSN` — Stage A(cycle291) 로 opt-in 인자가 생겼다.** 기본은 여전히 `"00"` 하드코딩과 **byte 동일**(`order_division: str | None = None`, falsy 는 `"00"`)이다 — 애프터·GTP 원주문 취소가 이 값으로 정상 처리되는지는 all-time 0건이라 여전히 미검증(docstring에 명시). 관측은 확장됐다 — `order_engine.py` 의 취소 3경로(`_cancel_after_wait`/`_cancel_and_reorder`/`cancel_remaining`)가 매 시도마다 `[after_cancel_result] ticker= order_no= ord_dvsn= orig_dvsn= dvsn_src=map|absent exchange= result=ok|error err=` 1행을 남긴다(`ord_dvsn`=실제 전송값[Stage A는 항상 `"00"`], `orig_dvsn`=원주문이 실제로 실었던 호가유형[`OrderEngine._order_division` 매핑, `_order_exchange` 와 완전 대칭]). **호출자 3곳은 아직 `order_division` 을 전달하지 않는다**(Stage A) — 정본에 "취소 시 원주문 호가유형을 승계하라" 는 규약이 없고(국내주식 정정취소 필드표엔 그 문장이 없다, 선물옵션만 `[취소] 01 로 입력` 고정값을 명시), 전송을 켜면 실적 있는 정규장 부분체결 취소의 `ORD_DVSN` 이 `00`→`01`(원주문 시장가)로 바뀌어 "정규장 byte 동일" 을 위반한다. Stage B(실제 전송) 전환은 D+1 이후 `orig_dvsn` 이 `41|44|27` 인 행만 `result=error` 로 층화되는 실측 + **매매 행위 변경 = 별도 승인**이 필요하다.

---

→ CHANGELOG: cycle291 행

## balance.py — 잔고/조회 · KIS 거부 응답 분류 헬퍼

### 2026-08-06 — `is_market_order_disallowed` ↔ `is_market_closed_rejection` 「상호 배타」 서술 정정 경위

원문(`src/api/CLAUDE.md:105`, 2026-09-17 이관):

---

- `is_market_order_disallowed(KisApiError) -> bool`: 시장가 거부. msg1 키워드 `_MARKET_ORDER_DISALLOWED_KEYWORDS`: `시장가매매불가` / `시장가 매매 불가` / `시장가 주문 불가` / `시장가 호가 불가` / `시장가호가불가` / `최유리/최우선지정가 주문만` / `지정가 및 최유리`. ⚠️ **`is_market_closed_rejection` 과 이중 매칭 실재** (2026-08-06 정정 — 종전 "상호 배타" 서술은 프리마켓 msg1 에서 거짓): APBK0918 "장운영시간이 아닙니다.([프리마켓] 시장가 매매 불가 시간)" 은 양쪽 키워드에 동시 매칭. `execute_sell` 은 closed 를 **먼저** 검사하므로 이중 매칭 = 보류(포지션 보존 + 다음 09:00 TTL) — 프리장 왜곡 시세라 지정가 폴백 즉시 매도보다 보류가 안전하다는 **의도된 계약**(순서 반전 금지 가드 `test_rejection_classifier_pre_market_priority.py`). `is_insufficient_*` 2종과는 상호 배타 유지. msg_cd 누적: APBK1943 (계양전기 매도) + APBK3013 (NXT 애프터 매도 — closed 미매칭이라 지정가 폴백 정상 경로). `docs/kis/error-codes.md` 4-2절 / 5-4절

---

→ CHANGELOG: 2026-08-06 행 · cycle229(P1-5) 행

## kis_master.py — KIS 공식 일일 마스터 파일

### 2026-06-14 사이클 129 — 절 제목·자동 갱신 서술의 사이클 꼬리표

원문(`src/api/CLAUDE.md:107,109,128,134,143`, 2026-09-17 이관):

---

## kis_master.py — KIS 공식 일일 마스터 파일 (사이클 129, 2026-06-14)

KIS 공식 다운로드 (`https://new.real.download.dws.co.kr/common/master/`) 일일 마스터 파일 (`kospi_code.mst.zip` / `kosdaq_code.mst.zip`) cp949 fixed-width 파싱 → `list[dict]` → upsert. 매일 16:30 KST 자동 갱신 (사이클 122/126 task 패턴 답습 + 사이클 127 fire-and-forget).

### SSL 옵션 C (사이클 129 domain-consult 채택)

### 매매 활용 키 ~30 (사이클 129 domain-consult 의제 4 확정)

### 단위 환산 (사이클 129 Q12, × 100)

---

→ CHANGELOG: 사이클 129 행

### 2026-06-19~06-21 사이클 164/166/167 — 시총 단위(억원) 확정 경위와 dead code 폐기

원문(`src/api/CLAUDE.md:137,145-149`, 2026-09-17 이관):

---

- 시총: `prdy_avls_scal` 전일 시가총액 (**억 원**). 시총 필터는 `list_by_filter` / `list_paged_by_filter` 가 `raw.hts_avls`(억원) 기준 직접 수행 (사이클 166 억원 정합)

- `prdy_avls_scal` (KIS 마스터) = **억 원** (구조체 `.h` 명세 "전일기준 시가총액 (억)" 기준. 1 억 = 100,000,000 원 = 100 백만원)
- `hts_avls` (KIS API FHKST01010100 inquire_price "HTS 시가총액", 사이클 116) = **억원** (사이클 166 확정 — 아래 참조)
- **사이클 167 — 시총 헬퍼 3개 dead code 폐기**: `market_cap_master_to_millions` / `validate_market_cap_consistency` / `get_market_cap_millions` 영구 폐기 (callsite 0건). 실제 시총 필터는 `list_by_filter` / `list_paged_by_filter` 가 `raw.hts_avls`(억원) 직접 비교 (사이클 166). AST 영구 가드 = `tests/unit/ast/test_cycle167_ast_no_dead_market_cap_funcs.py`.
- ✅ **단위 확정 (운영 DB 실측 검증 완료, 사이클 164 인계 종결)**: 대형주 6종목 전수에서 `종가 × 상장주수(천주) ÷ prdy_avls_scal = 정확히 100,000` → 실제 시총(원) = `prdy_avls_scal × 10⁸` → **`prdy_avls_scal` = 억원 확정**. `× 100` 환산 정확. **사이클 164 "백만원 의심" = false alarm 기각**.
- ✅ **hts_avls 단위 충돌 종결 (사이클 166, 2026-06-19)**: 운영 DB 대형주 9종목 전수 `실제시총(원) / hts_avls ≈ 10⁸` → **`hts_avls` = 억원 확정**. median 933(=933억원) 분포도 한국 상장사 중앙값과 정합. 사이클 108/128 "백만원" 가정은 silent 결함 (100배 어긋남 → min_market_cap=1,000억 시 후보 풀 1,734 → 80, 95.4% 축소). **시정**: `list_by_filter` (python `hts_avls × 100_000_000`) + `list_paged_by_filter` (jsonb `min_market_cap // 100_000_000`) + scanner KRX 폴백 (`// 100_000_000`) + 프론트 `formatMarketCap` 모두 억원 통일. DB 재적재 불필요 (16:10 KIS task 가 억원으로 덮어씀). `get_market_cap_millions` / `validate_market_cap_consistency` / `market_cap_master_to_millions` 는 production 미사용 → **사이클 167 dead code 폐기**. 회귀 가드: `tests/unit/db/test_cycle166_hts_avls_unit_correction.py` + `tests/unit/engine/scanner/test_cycle166_krx_fallback_eok_unit.py` (AST 단위 가드 `1_000_000` 잔존 0건) + `tests/unit/ast/test_cycle167_ast_no_dead_market_cap_funcs.py` (3 함수 폐기 가드).

---

→ CHANGELOG: 사이클 164 · 166 · 167 행. 현행 단위(`prdy_avls_scal`·`hts_avls` = 억원)는 정본에 남겼다.

## finance.py — KIS 재무 5 TR fetch

### 2026-07-15 사이클 C1 — 절 제목의 사이클 꼬리표

원문(`src/api/CLAUDE.md:157`, 2026-09-17 이관):

---

## finance.py — KIS 재무 5 TR fetch (사이클 C1, 2026-07-15)

---

→ CHANGELOG: 사이클 C1 행

## krx.py — KRX 정식 OPEN API 클라이언트

### 2026-06-12 사이클 112 → 115 — 인프라 사전 구성 · 추상 결함 3건 대조표 · 회귀 가드 케이스 수

원문(`src/api/CLAUDE.md:178,182-199,211,215,225-228,233,235,237,239-252`, 2026-09-17 이관):

---

## krx.py — KRX 정식 OPEN API 클라이언트 (사이클 112 + 사이클 115)

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


**bydd_trd 핵심 15 필드** (사이클 108 직접 정합):

- 시총: **`MKTCAP`** (원 단위) → KIS `hts_avls` (억원) 환산 `// 100_000_000` (사이클 116 → 166 정정, 단위 혼재 제거)

**Q3=C 폴백 패턴** (호출자 `src/engine/scanner.py::_full_universe_load_once`):
- KRX 1차 우선 호출 (4 endpoint + 50ms sleep × 3건 = KIS LMS chain 안전 마진 답습)
- KrxApiError (비활성/401/4xx/5xx/네트워크 예외) 시 KIS market-cap 자동 폴백 (사이클 101+109+110 영속)
- 양쪽 모두 실패 시 raise (사이클 110 graceful 패턴 영속)

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

---

→ CHANGELOG: 사이클 112 · 115 행. 현행 호출 규약·필드 목록·가드 파일명은 정본에 남겼다.

## market_operation.py · quotation.py — 절 제목의 사이클 꼬리표

### 2026-05-21 사이클 32 · 2026-06-16 사이클 149 — 도입 사이클 표기

원문(`src/api/CLAUDE.md:254,274,280`, 2026-09-17 이관):

---

## market_operation.py — 장운영정보(H0UNMKO0) 정본 + VI 현황 REST 폴백 (사이클 149, 2026-06-16)

## quotation.py — 주식현재가 체결 (사이클 32, 2026-05-21)

- 호출처: `scheduler._evaluate_universe_guard` (사이클 32, universe 제외 판단) + `scheduler._refresh_stale_ccnl_cache` (사이클 37, stale 종목 UI 표시용 TTL 5분 캐시)

---

→ CHANGELOG: 사이클 32 · 37 · 149 행

## condition.py — 조건검색 + 영업일 + 종목 기본정보 + TTL 캐시

### 2026-06-22 사이클 172 → 2026-07-07 사이클 196 — 분할 fetch 도입과 120일 수렴 경위

원문(`src/api/CLAUDE.md:284,288,290-293`, 2026-09-17 이관):

---

- **시세성 호출 풀 라우팅**: 본 모듈 6 함수 모두 `kis_get_quote` 사용 — 보조 라운드로빈 + 메인 fallback. 시그니처 변경 0 (외부 영향 없음). `from src.api.base import kis_get_quote` (메인 `kis_get` import 제거)

- `add_business_days(base_date, n)` (사이클 191): base_date 이후 n번째 개장일 date. CTCA0903R 1회 호출(~30일치)에서 `opnd_yn=="Y"` n번째 row. 실패/개장일 부족 시 `base + timedelta(n+2)` 달력일 폴백 graceful. BFB/VCP 재진입 쿨다운 영업일 정정용 (`_refine_cooldown_business_days` 소비)

- **사이클 172 (2026-06-22) 도입 → 사이클 196 (2026-07-07) 120일 수렴 — 분할 fetch (날짜 윈도우 100건 경계) + VCP backfill (도입 220일 → 현재 120일)**:
  - `fetch_daily_candles_ranged(ticker, start_yyyymmdd, end_yyyymmdd) -> list[dict]`: KIS `FHKST03010100` 단일 윈도우 조회 (`FID_INPUT_DATE_1`=시작 / `FID_INPUT_DATE_2`=종료 / `FID_PERIOD_DIV_CODE="D"` / `FID_ORG_ADJ_PRC="0"` / `FID_COND_MRKT_DIV_CODE="J"`, KIS MCP 정본 재확인 완료). `kis_get_quote` 경유 (시세성 풀 + Rate Limit + 메트릭). output2 (최신순) + `stck_bsop_date` 빈 placeholder 제거. **memcache/single-flight 미사용** (backfill 전용, 16:00 daily task 만 호출). 6자리 ticker 가드 (`ValueError`). **`FID_ORG_ADJ_PRC="0"` (수정주가) = 기존 `_fetch_daily_candles_and_cache` 정합** — 사이클 173 DB-source vs KIS-source 동등성 게이트 보장 (정본 샘플 "1" 예시이나 본 코드베이스는 사이클 14부터 "0" 사용).
  - `fetch_daily_candles_backfill(ticker, total_days=120, *, window=100) -> list[dict]`: N일 backfill = 날짜 윈도우 ×`ceil(N/window)` 순차 호출 + 병합. **사이클 196 (2026-07-07) — 마지막 윈도우 `start_offset = min((i+1)*window, total_days)` 클램프** (목표 초과 fetch 차단, retention 밖 churn 원천 봉쇄). 120일 = 100일 윈도우 ×2 (T-150~T / T-178~T-140 영업일 환산, 마지막 윈도우 total_days 에서 정지 = 최고 도달 ≈178 cal일 < retention 230, 경계 겹침 → dedupe). 중복 `stck_bsop_date` dedupe + bas_dd DESC 정렬. 윈도우 간 50ms sleep (`_DAILY_BACKFILL_WINDOW_SLEEP_SECS`, 사이클 17 KIS LMS chain). 개별 윈도우 실패 graceful (사이클 88 G-REJECT, 다음 윈도우 진행).
  - **기존 `fetch_daily_candles` 변경 0** (memcache 5분 + single-flight + `asyncio.shield` 영속) — 별도 함수. 호출자 = `scanner._stock_master_daily_load_once` (VCP universe **120일 분기**, 사이클 196 수렴, 16:00 daily task 만). **매매 안전성 무영향** (데이터 적재 한정, scanner 매수 진입 전 영역, 사이클 38 명문화). 회귀 가드 = `tests/unit/api/test_cycle172_daily_ranged_backfill.py` (RANGE 4 + BACKFILL 4 + AST).

---

→ CHANGELOG: 사이클 172 · 173 · 191 · 196 행

### 2026-06-11~06-26 사이클 107/108/144/145/176/177 — `inquire_stock_basics` raw 보강 경위

원문(`src/api/CLAUDE.md:294-300`, 2026-09-17 이관):

---

- **`inquire_stock_basics(pdno) -> StockBasics`**: KIS `CTPF1002R` — NXT 거래종목 (`cptt_trad_tr_psbl_yn`) + NXT 거래정지 (`nxt_tr_stop_yn`) + KRX 정지 + 관리종목 파싱 → `StockBasics` 반환. 파생값 `nxt_tradable = (cptt=="Y") AND (nxt_stop=="N")`. CTPF 접두사 TR_ID 는 모의/실전 동일. 캐시 `src.db.stock_master` 24h TTL. **ticker 정규화**: `_normalize_ticker()` 가 KIS `pdno` 12자리 표준코드 → KRX 6자리 단축코드 추출 (정규식 `(\d{6})$`). `stock_master` PK 정합성 보장. `docs/kis/error-codes.md` 5-3절
- **사이클 145 (2026-06-16) — `inquire_stock_basics` FHKST01010100 raw 0 덮어쓰기 금지 graceful (결함 #2, HIGH 매매 안전성 직결)**: 운영 사례 (Supabase MCP 진단) = 2026-06-16 07:54~07:59 KST = boot `force=True` (장 시작 *전*) 시점 + stock_master 2,697 ticker 중 `acml_tr_pbmn > 0` = **3 종목만** 잔존 silent 결함. 근본 원인 = FHKST01010100 응답 `acml_tr_pbmn=0` + `acml_vol=0` 정상 (장 시작 전 거래 없음) → `inquire_stock_basics` merge 영역에서 기존 raw 덮어쓰기 → `stock_master.list_by_filter(acml_tr_pbmn ≥ min_trade_amount=20_000_000_000)` 0건 silent → donchian/VB/LTV 후보 0 결함. **시정 (+20L net)**: merge 영역에서 `("acml_tr_pbmn", "acml_vol")` 키 = `int(str(value).replace(",", "") or 0) == 0` 가드 → 0 값 `continue` skip → 기존 raw 키 보존 (전일 영업일 거래대금 보존). `("lstn_stcn", "prdy_vrss", "hts_avls")` = 변경 0 (정상 덮어쓰기). 비숫자 = `except (ValueError, TypeError)` graceful → 정상 그대로 merge. **사이클 81 G-AST1 강화** (raw 덮어쓰기 금지 영속) + 사이클 88 G-REJECT graceful 영속. **회귀 가드 4 케이스 (`tests/unit/api/test_cycle145_raw_preserve.py`)**: G-145-RAW-1 (acml_tr_pbmn=0 응답 → 기존 raw 키 보존 + 다른 정상 키 정상 merge `hts_avls` / `lstn_stcn`) + G-145-RAW-2 (acml_tr_pbmn>0 정상 응답 → 정상 덮어쓰기) + G-145-RAW-3 (acml_vol=0 시 동일 보존) + G-145-RAW-4 (AST 정적 가드 = `numeric_value == 0`). **영속 의무 매트릭스**: 사이클 81 G-AST1 강화 + 사이클 88 G-REJECT graceful 영속 + 사이클 107 CTPF1002R + FHKST01010100 merge 패턴 영속 (변경 0 = 0 가드 추가만) + 사이클 108 list_by_filter (`acml_tr_pbmn ≥ min_trade_amount`) 정합 영속 + 사이클 122~144 영속 (영향 0). **매매 안전성 직접 검증**: scanner 매수 진입 *전* 한정 (사이클 38 명문화 영속) + stock_master raw 보존 → list_by_filter 정상 작동 → donchian/VB/LTV 후보 영속 → 매매 안전성 영향 0 (기존 raw 보존). **D+1 운영 효과 (2026-06-17~)**: 16:30 `_stock_master_master_load_once` 자동 발화 + 16:10 `_stock_master_basics_refresh_once` 자동 발화 = 거래대금 정상 적재 → list_by_filter 정상 작동 → donchian/VB/LTV `prepare()` 호출 시 유의미한 후보 영속.
  - **⚠️ 사이클 176 (2026-06-25) 정정 — 사이클 145 "기존 raw 키 보존" 은 사실상 no-op 이었음**: `inquire_stock_basics` 가 `merged_raw = dict(ctpf_output)` 로 raw 를 **CTPF 에서 신규 빌드** (기존 DB raw 미read) → CTPF 에 거래대금 키 부재 + FHKST 0 skip → merged_raw 거래대금 부재 → `upsert_one` raw 통째 교체 → 거래대금 영구 소멸. cycle 145 의 `continue` skip 은 "0 값을 merged_raw 에 *안 넣는다*" 일 뿐, *기존 DB raw 와 머지* 가 아니므로 보존 효과 0. 운영 실측 (2026-06-25) = 거래대금 보유 6/3573, VB/LTV/donchian/BFB universe 0 race. **실제 시정 = `src/engine/scanner.py::_stock_master_basics_refresh_once` 가 기존 DB raw 를 보관 → upsert 전 `{**기존, **신규}` 머지** (`_ZERO_VALUE_SKIP_KEYS` 15키 기존 값 보존, 새 키 우선). 회귀 가드 = `tests/unit/engine/test_cycle176_basics_refresh_raw_merge.py` (5).
  - **사이클 177 (2026-06-26) — None/비숫자 하드닝**: 사이클 176 정밀검증(end-to-end `test_cycle176_e2e_premarket_preservation.py` 5건) 중 발견 — skip-키 `value=None` 시 cycle 145 가드 `float("None")` ValueError → `except: pass`(merge) → `merged_raw[key]=None` → 기존 거래대금 None 덮어씀(소실, FHKST 는 장전 "0" 반환이라 이론적). 하드닝 = 가드 except 분기 `pass` → **`continue`** (skip-키 15개 전부 숫자 필드 → 비숫자/None=junk → 덮어쓰지 않고 기존값 보존). cycle 145 `if numeric_value == 0.0: continue` 불변(G-145-RAW-4 유지), cycle 155 비숫자-merge 단언은 비-skip 키 한정이라 회귀 0.
- **사이클 144 (2026-06-16) — `inquire_stock_basics` graceful 분기 가시화 강화 (카드 #27 LOW)**: 사이클 130 권고 카드 #27 (NEW LOW, 사이클 129/132 인계) 종결. **현행 silent fail**: 사이클 107 도입 FHKST01010100 호출 실패가 `try/except: logger.exception` + `price_data = {}` graceful fallback 만 영역 = scanner `_stock_master_basics_refresh_once` summary 가시화 불가 (사이클 129 OPSQ1002 SESSION FULL graceful 처리 silent). **시정 (production +53L)**: `condition.py` 모듈 전역 `_graceful_failed_counter: dict[str, int]` 신규 + `_graceful_failed_lock: asyncio.Lock` (FastAPI 동시 요청 + BackgroundTasks 동시성 보호) + 3 헬퍼 (`_record_graceful_failed(reason: str)` 비동기 카운터 증가 / `get_graceful_failed_counts() -> dict` 스냅샷 사본 반환 / `reset_graceful_failed_counts()` 초기화). `inquire_stock_basics` FHKST01010100 except 분기에 `_record_graceful_failed("fhkst01010100_failed")` 호출 신규 (try/except 외부 영향 0). **scanner summary +21L**: `_stock_master_basics_refresh_once` 시작 시 `reset_graceful_failed_counts()` 호출 (단일 task 측정 의무) + 종료 시 `get_graceful_failed_counts()` 수집 + `summary["graceful_failed"]` 키 ("fhkst01010100_failed" 카운터) + emit 로그 `[stock_master_basics_refresh_summary] ... graceful_failed_fhkst=%d ...` 필드 추가. **회귀 가드 10 케이스 (`tests/unit/api/test_cycle144_graceful_visibility.py`)**: G-144-COUNTER-1~4 (모듈 전역 dict + 카운터 증가 + snapshot + reset 영속) + G-144-INT-1~3 (FHKST01010100 RuntimeError → 카운터 +1 + 양쪽 정상 → 변경 0 + KisApiError "OPSQ1002 SESSION FULL" → 카운터 +1, 사이클 129 가시화 직접 검증) + G-144-SUMMARY-1~2 (summary `graceful_failed` 키 + emit `graceful_failed_fhkst=N` 필드) + G-144-AST-1 (inquire_stock_basics graceful 분기 `_record_graceful_failed` 호출 ≥ 1건 AST 정적 가드, 미래 동일 silent 결함 영구 차단). **영속 의무 매트릭스**: 사이클 17 KIS LMS chain (변경 0) + 사이클 38 명문화 (logging 한정) + 사이클 79 G-AST2 / 81 G-AST1 (영향 0) + 사이클 88 G-REJECT graceful 영속 (강화 = silent → 가시화) + 사이클 107 `inquire_stock_basics` CTPF1002R + FHKST01010100 merge 패턴 영속 (변경 0 = except 분기 카운터 호출만 추가) + 사이클 122~143 영속 (영향 0) + CLAUDE.md "절대 깨지 말 것" 8 영역 영속. **매매 안전성 무영향 확정**: logging + 카운터 한정 (process-local in-memory, uvicorn 단일 워커 영속 의무) + `src/engine/risk.py` / `src/engine/order_engine.py` / `src/realtime/` / `src/auth/` 변경 0 + 매수 진입 hot path 영향 0 + 매도/익일청산/15:20 강제청산 hot path 무관. **운영 효과**: 6/16 KST 16:10 `_stock_master_basics_refresh_task` 자동 발화에 `[stock_master_basics_refresh_summary]` 로그에서 `graceful_failed_fhkst=N` 필드 = 운영자 즉시 진단 ("FHKST01010100 KIS SESSION FULL N건 graceful 처리") + Loki 파싱에서 사이클 129 silent 결함 추세 측정 가능. **사이클 129 OPSQ1002 SESSION FULL 인계 종결**: 사이클 132 카드 #27 silent fail 가시화 결핍 시정 완료. team-leader 자체 결정 (사용자 결정 Q1=A 사이클 143 commit `ed8298b` + CI success 4분 26초 + EC2 Deploy success 35초 영속).
- **사이클 108 (2026-06-11) — `inquire_stock_basics` `hts_avls` 5번째 키 보강 (Plan Phase A 완료, 시총 데이터 확보)**: 사이클 104 인계 Q5=B (LOW 위험 자문 생략) + 사이클 107 raw 보강 의존성 해소 완료 → Plan Phase A 데이터 활용 가능 → 사이클 108 = `inquire_stock_basics` `hts_avls` 1 키 보강 + `stock_master.list_by_filter()` 신규 메서드 + VB/LTV/BFB `_scan_universe()` 전환 통합. 사용자 결정 Q1=A 시총 = `hts_avls` (KIS FHKST01010100, 백만원 단위, KIS 정본 인용 의무 = `chk_inquire_price.py` + 사이클 98 G-DOC1 답습). **시정 (production 1 파일, +1L 순증)**: 사이클 107 4 키 (`acml_tr_pbmn` + `lstn_stcn` + `acml_vol` + `prdy_vrss`) → 사이클 108 5 키 보강 = `hts_avls` 추가 (FHKST01010100 응답 = 시가총액 백만원 단위). for loop 4 키 → 5 키 (`if key not in merged_raw` 덮어쓰기 금지 영속). **CTPF1002R 기존 키 덮어쓰기 금지 설계**: 사이클 81 G-AST1 정합 (`bfdy_clpr` + 사이클 100 3 prefix OR + 사이클 101 `_full_universe_load_once` 자동 반영 영속 + `hts_avls` 덮어쓰기 금지). KIS MCP 정본 = `chk_inquire_price.py` main 호출 인용 의무 (사이클 98 G-DOC1 답습). **회귀 가드 (HIGH)**: `tests/unit/api/test_cycle108_hts_avls.py` = `hts_avls` 5번째 키 영속 + 덮어쓰기 금지 + AST 영구 가드. **호출**: `stock_master.upsert_one(ticker, ...)` 경로 + 사이클 101 `_full_universe_load_once` 배치 호출 (2,800 종목 × 2 KIS 호출 + 50ms sleep = 약 5분 소요). **운영 효과 (push + EC2 자동 배포 후)**: `inquire_stock_basics` 1회 호출 → stock_master.raw 에 `acml_tr_pbmn` + `lstn_stcn` + `acml_vol` + `prdy_vrss` + `hts_avls` 자동 포함 → 사이클 108 `stock_master.list_by_filter(min_market_cap=, min_trade_amount=)` 데이터 의존성 해소. **영속 의무 매트릭스**: 사이클 32 R4 universe guard 영속 + 사이클 38 명문화 영속 (`inquire_stock_basics` = 매수/매도 진입 직전 lazy 호출 + 매수 진입 전 한정 영속) + 사이클 81 G-AST1 영속 (`bfdy_clpr` + `hts_avls` 덮어쓰기 금지 영속) + 사이클 88 G-REJECT 영속 + 사이클 98 G-DOC1 영속 (KIS 정본 인용 의무 = `chk_inquire_price.py`) + 사이클 101 영속 (`_full_universe_load_once` 자동 반영) + 사이클 102 G-REJECT 영속 + 사이클 106 영속 확인 (lifecycle race 차단) + 사이클 107 영속 확인 (raw 보강 4 키). **매매 안전성 무영향 확정** (`inquire_stock_basics` = 종목 마스터 캐시 한정 + 매수/매도 진입 직전 lazy 호출 + 매매 hot path 직접 영향 0 + Rate Limit 50ms sleep KIS LMS chain 안전)
- **사이클 107 (2026-06-11) — `inquire_stock_basics` raw 보강 (CTPF1002R + FHKST01010100 merge, Plan Phase A 데이터 의존성 영구 해소)**: **Phase 1 진단 결정적 발견 (KIS MCP 정본 확정)**: CTPF1002R 응답 67 컬럼 = 3 키 (`acml_tr_pbmn` 누적 거래 대금 + `lstn_stcn` 상장 주수 + `prdy_vol` 전일 거래량) **모두 부재 확정**. FHKST01010100 (`inquire_price` 주식현재가 시세, KIS 정본 `chk_inquire_price.py` 인용 의무 = 사이클 98 G-DOC1 답습) 응답 = 3 키 모두 **존재 확정** (`acml_tr_pbmn` + `lstn_stcn` + `acml_vol` 누적 거래량 (`prdy_vol` 동등) + `prdy_vrss` 전일 대비). **시정 (production 1 파일, +44L 순증)**: `inquire_stock_basics` 본체 보강 = CTPF1002R 호출 *후* `await asyncio.sleep(0.05)` Rate Limit (사이클 83/91/97 답습 영속 = KIS LMS chain 안전) → FHKST01010100 추가 호출 (`kis_get_quote(STOCK_PRICE_URL, "FHKST01010100", ...)` 시세성 풀 라우팅 + 메인 fallback) → try/except graceful (`price_data = {}` fallback + `[inquire_stock_basics] FHKST01010100 호출 실패 graceful` 로그) → `merged_raw = dict(ctpf_output)` + for loop 4 키 조건부 merge (`acml_tr_pbmn` + `lstn_stcn` + `acml_vol` + `prdy_vrss`, `if key not in merged_raw` 덮어쓰기 금지). **CTPF1002R 기존 키 덮어쓰기 금지 설계** = 사이클 81 G-AST1 정합 (`bfdy_clpr` 영속). **graceful fallback**: FHKST01010100 RuntimeError / KisApiError = CTPF1002R 단독 raw 반환 (호출자 보호). CTPF1002R 에러 = 전파. **회귀 가드 12 신규 (HIGH 4 케이스, `tests/unit/api/test_cycle107_inquire_stock_basics_merge.py`)**: HIGH-1 양쪽 API 호출 + CTPF 선행 순서 (2 sub-case) + HIGH-2 raw 3 키 포함 + `bfdy_clpr` 보존 + 덮어쓰기 금지 (3 sub-case) + HIGH-3 graceful fallback (RuntimeError / KisApiError / CTPF 에러 전파, 3 sub-case) + HIGH-4 AST 영구 가드 (FHKST01010100 문자열 + inquire-price URL + 60줄 윈도우 + 3 키 merge, 4 sub-case). **운영 효과**: `inquire_stock_basics` 1회 호출 → stock_master.raw 에 `acml_tr_pbmn` + `lstn_stcn` + `acml_vol` 자동 포함 / 2,800 종목 × 2 KIS 호출 + 50ms sleep = 약 5분 소요 (사이클 101 `_full_universe_load_task_loop` 배치 시 적용) / 향후 Plan Phase A (사이클 108+) `list_by_filter(min_market_cap=, min_trade_amount=)` 데이터 의존성 해소. **영속 의무 매트릭스 9 영역 전수 영속**: 사이클 32 R4 / 38 명문화 / 81 G-AST1 (`bfdy_clpr` 덮어쓰기 금지) / 88 G-REJECT / 98 G-DOC1 (KIS 정본 `chk_inquire_price.py` 인용 의무) / 101 영속 (`_full_universe_load_once` → `inquire_stock_basics` 호출 자동 반영) / 102 G-REJECT / 106 영속 (`_full_universe_load_task_loop` 변경 0) / CLAUDE.md "절대 깨지 말 것" 8 영역. **매매 안전성 무영향 확정** (종목 마스터 캐시 한정 + 매수/매도 진입 직전 lazy 호출 + 매매 hot path 직접 영향 0 + Rate Limit 50ms sleep KIS LMS chain 안전)

---

→ CHANGELOG: 사이클 107 · 108 · 144 · 145 · 155 · 176 · 177 행. 현행 계약(merge 키·0 skip·graceful·보존 주체)은 정본에 남겼다.


## condition.py — 일봉 분할 fetch

### 2026-09-17 cycle299 — "단일 호출 최대 100일" 이 총량 한도로 읽히던 문장

🔴 이 항목이 이 사이클 문서 작업의 핵심이다. `fetch_daily_candles` 설명의 "**단일 호출 최대 100일**"
은 사실이지만, 읽는 쪽에서 "KIS 가 100일까지만 준다" 로 굳었다. 그 오해가 넉 달 동안 200일 EMA 를
막았다 — 정작 `fetch_daily_candles_backfill` 이 사이클 172 부터 날짜 윈도우를
`ceil(total_days/window)` 개로 쪼개 순차 호출·병합하고 있었다. 정본은 "100일은 호출당 한도이지
총량 한도가 아니다" 로 고쳤다.

원문(`src/api/CLAUDE.md:270-274` 중 바뀐 부분, 2026-09-17 이관):

---

- `fetch_daily_candles(ticker, days)`: 일봉 N영업일치. `FHKST03010100` (`/quotations/inquire-daily-itemchartprice`, 모의/실전 동일) — **단일 호출 최대 100일**.
- **분할 fetch (날짜 윈도우 100건 경계) + VCP backfill 120일**:
  - `fetch_daily_candles_backfill(ticker, total_days=120, *, window=100) -> list[dict]`: … 120일 = 100일 윈도우 ×2 (최고 도달 ≈178 달력일 < `DAILY_RETENTION_DAYS=230`, 경계 겹침은 dedupe).
  - **`fetch_daily_candles` 와 별도 함수**다 … 호출자 = `scanner._stock_master_daily_load_once` (VCP universe 120일).

---

새 값 = 실사용 `total_days=220`, 윈도우 3개(100/100/20), 최고 도달 318 달력일 <
`DAILY_RETENTION_DAYS=380`. 시그니처 기본값 120 은 남았지만 호출되지 않는 폴백이다(유일한 호출자
`scanner._stock_master_daily_load_once` 가 `_DAILY_LOAD_VCP_BACKFILL_DAYS` 를 항상 명시 전달한다).
1회 호출이 target 에 약 8영업일 모자라는 달력 환산 편차는 `src-engine-CLAUDE.history.md` 의 같은
날짜 항목에 적었다.

→ CHANGELOG: cycle299 행

### cycle299 (2026-09-18) — 목표를 220 → 225, 보존을 380 → 390 으로 다시 올린 경위

사이클 안에서 값이 한 번 더 움직였다. 앞 항목에 380/220 으로 적힌 서술은 그 시점의 기록이고,
확정값은 **retention 390 달력일 · VCP backfill target 225 영업일** 이다.

- **왜 225 인가** — VCP 추세 필터의 `effective_ema_long = min(ema_long, 보유 − uptrend_days(20) − 5)`
  에 운영 DB 값(`ema_short=50` / `ema_mid=150` / `ema_long=200`)을 넣고 보유 영업일을 움직이면,
  보유 220 에서는 실효 장기선이 **195** 에 그치고 **225 에서 정확히 200** 이 된다. 미네르비니 원전의
  200EMA 를 형식이 아니라 값으로 성립시키는 최소 깊이가 225 다. 같은 계산에서 mid↔long 간격도
  220 의 45 에서 225 의 50 으로 벌어진다(보유 100 이면 간격 10 = 사실상 동전던지기였다).
- **왜 retention 도 함께 올렸나** — 가드 `G-299-3c`(`retained_trading(retention) >= target + 30`)
  때문이다. 환산 앵커 230cal ⇄ 154영업일로 `retained(380) = 254` 인데 `225 + 30 = 255` 라 **1 모자라
  FAIL** 한다. 3c 를 만족하는 retention 최소값은 **381** 이고, 여유를 두어 390 을 택했다
  (`retained(390) = 261` → 마진 **36 영업일**, 사이클196 의 34 보다 크다).
- **실측(가드 헬퍼 `_capture_backfill_reach_cal` 로 확인)** — `total_days=225` 의 윈도우는 3개
  (100/100/25), 최고 도달 **325 달력일** < retention 390(여유 65cal). 1회 backfill 실도달은
  `trading_days_in(325) = 217` 영업일이라 target 에 **8 영업일** 모자라고, 이 부족분은 220 일 때와
  같다(둘 다 8). 전이 기간과 비용 추정은 앞 항목과 동일하다.
- **재핀** — `scanner.py` 가 다시 바뀌어 8영역 sha 핀 13곳(`_PIN_GUARD_FILES` 4 + 기준선 9)과
  `test_cycle287::_SRC_TREE_DIGEST` 를 같은 값으로 한 번 더 옮겼다. 단언은 약화되지 않았다.

### cycle299 (2026-09-18, 이어서) — 달력 환산을 고쳐 1회 backfill 이 목표를 넘게 했다

사용자 요청("데이터 지금 바로 채울 수는 없어?")으로, 별건으로 미뤄 두었던 환산식을 이 사이클에서 고쳤다.

- **고친 것** — `fetch_daily_candles_backfill` 의 **깊이**(마지막 윈도우 시작점) 환산에만 휴일 보정을
  비례로 얹었다: `int(n*7/5) + int(n*0.10) + 10`. 상수 3개를 이름으로 뽑고 근거를 주석에 남겼다
  (`_WEEKEND_CAL_PER_TRADING_DAY` / `_DAILY_BACKFILL_HOLIDAY_MARGIN_RATIO` / `_DAILY_BACKFILL_BASE_MARGIN_CAL`).
- **왜 계수를 통째로 올리지 않았나** — `3/2`(=1.50) 제안은 **stride 까지 함께 키운다**. KIS 가 한 호출에
  100건까지만 주므로 앞 윈도우는 공휴일이 하나도 없는 구간에서 정확히 100영업일 = **140 달력일**까지만
  덮는다. stride 가 140 을 넘는 순간 다음 윈도우의 머리가 그 바닥보다 아래로 내려가 **사이 구간이 통째로
  비고**, 빈 날짜는 어느 윈도우도 다시 집지 않는다(`3/2` 면 stride 150 > 140). 그래서 stride 는 7/5 로
  두고 깊이에만 보정을 얹는 형태를 택했다. 구멍 검사는 공휴일 0 이라는 최악 가정으로 확인했다.
- **실측** — `total_days=225` → 윈도우 3개 `[(0,160), (140,310), (280,347)]`, 최고 도달 **347 달력일**.
  실측 비율(앵커 230cal ⇄ 154영업일 = 1.479)로 **232 영업일**이라 목표 225 를 **7 넘는다**. 공휴일이
  없는 해(1.40)에는 247, 밀집한 해(1.52)에도 228 로 어느 쪽도 목표 위다. 전이 기간이 사라졌다.
- **가드** — `retention 390` 기준 3a(347 < 390, 여유 43) · 3b(347+30 = 377 ≤ 390) · 3c(261 ≥ 255) 전부
  통과라 retention 은 옮기지 않았다. `G-299-9` 는 "부족분 ≤ 10"(음수에서 공허해진다)에서
  **"실도달 ≥ target"** 으로 부등식을 뒤집어 강화했다.
- **`scanner.py` 무접촉** — 변경을 `condition.py` 에 가둬 8영역 sha 핀 13곳을 다시 옮기지 않았다.
  움직인 것은 `test_cycle287::_SRC_TREE_DIGEST` 하나다.
- **호출자** — `fetch_daily_candles_backfill` 의 프로덕션 호출자는 `scanner._stock_master_daily_load_once`
  **하나뿐**임을 `grep` 으로 재확인했다. 별도 함수 `fetch_daily_candles` 는 무접촉이다.

## market_operation.py — 장운영정보(H0UNMKO0) 정본 + VI 현황 REST 폴백

### 2026-09-26 cycle368 — 칸 기준점·종목상태 `58` 단독·`(null)` 비활성 반영으로 교체한 표 행과 주의문

정본 원문(`src/api/CLAUDE.md:244-250`, 2026-09-26 이관):

---

| `@dataclass MarketOpEvent` | KIS 10컬럼 전수 파싱 결과 |
| `parse_market_op_payload(tr_key, payload) -> MarketOpEvent` | `^` 구분 페이로드 → 이벤트 |
| `is_event_blocking(event) -> bool` | stale 회피 판정 = VI 활성 + 거래정지 + 종목상태 이상(MRKT_TRTM 제외) |
| `inquire_vi_status_today() -> set[str]` | 부팅 REST 1회 시드. graceful — 실패해도 매매 안전성 영향 0 |

🔴 **`VI_CLS_CODE` 의 `"0"`/`""`/`None` 은 전부 비활성이다**(truthy 매핑 = 블랙리스트 방식).
KIS 가 코드를 늘려도 새 값이 자동으로 "활성" 으로 읽히게 하려는 의도다.

---

경위: cycle359 조사가 라이브 `H0UNMKO0` 프레임의 첫 칸이 종목코드라 파서가 모든 칸을 한 칸씩 밀려 읽는다는
것을 찾았다(가짜 VI → 보유 종목이 stale 재구독에서 빠짐). 2026-09-25 사용자 결정 「칸 위치는 바로 잡아.
거래정지 판정은 58만 봐」로 파서 기준점과 종목상태 판정을 바꿨다. 종목상태를 `_is_code_active` 로 넓게 읽던
판정은 55(신용가능)·57(증거금100%)까지 「이상」으로 잡던 두 번째 덫이라 폐기했다. `(null)` 비활성과 정지 사유
정규화는 적대적 검토 뒤 메인 세션 결정(사용자 승인 범위 안)이다.

→ CHANGELOG: cycle368 행

## balance.py — 잔고/조회

### 2026-09-27 cycle385 부록 R — `get_daily_orders` 서명에 `pdno` 추가

정본 원문(`get_daily_orders` 항목):

- `get_daily_orders(target_date="", exchange="ALL", *, odno="")`: TTTC0081R. `EXCG_ID_DVSN_CD` query required — `ALL`(기본, KRX+NXT+SOR 합산) / `KRX` / `NXT` / `SOR`. NXT 체결 누락 방지 위해 기본 ALL. `odno`(keyword-only)는 `ODNO` 필터라 그 주문 1건의 행만 돌려준다(cycle373 실측). 기본값 `""` 이면 params 가 전체 목록 조회와 같다. 소비처 = `engine/buying_reconcile.py`(자기 주문 행 조회 — 전체 목록의 첫 쪽 잘림에 기대지 않는다)

경위: cycle385 부록 R(적대 검토 F-1)이 `execute_sell` #1.5 재대조에 주문별 크레딧을 넣으면서 그 종목 매도 주문만 읽으려고 keyword-only `pdno=""` 를 더했다(params `"PDNO": pdno`). 기본값 호출의 params 는 byte 동일하다(`tests/unit/api/test_cycle385r_daily_orders_pdno.py`). `PDNO` 필터가 실제로 서버에서 먹는지는 운영에서 재지 않았고, 소비처가 행을 다시 거른다.

→ CHANGELOG: cycle385 행

## 2026-10-01 sync-docs 압축 — 정본에서 이관

정본(`src/api/CLAUDE.md`)을 코드와 대조해 정정·압축하면서 바뀌거나 빠진 원문이다. 절마다 원문 줄을 그대로 옮기고 바뀐 점을 한 문단으로 적는다.

### base.py — 공통 래퍼 (메인 단일)

정본 원문(바뀌거나 빠진 줄만, 원래 순서):

---

- `kis_request(method, url, tr_id, ...)`: 모든 KIS API 호출의 단일 진입점
- 헤더 자동 구성: authorization, appkey, appsecret, tr_id, custtype("P")
- Rate Limit: `asyncio.Semaphore(20)` 초당 20건 제한
- 자동 재시도: 네트워크/5xx 최대 3회, 지수 백오프 (`BACKOFF_BASE=0.5s × 2^(attempt-1)`) + jitter (`0~BACKOFF_JITTER=0.25s`) — thundering herd 완화
- **재시도 최종 결과 영구 저장**: 재시도 루프 끝난 직후 영문 prefix 1행 fire-and-forget. (a) `attempt > 1` + `rt_cd=0` 성공 → INFO `[api_retry_recovered] path=... tr_id=... attempts=N`. (b) `MAX_RETRIES=3` 모두 5xx/network 실패 후 raise 직전 → ERROR `[api_retry_exhausted] path=... tr_id=... attempts=3 last_status={503|network} last_msg=...`. 기존 `retries` (중간 시도) 와 분리 — *최종* 결과만
- **5xx 로그 억제 · 재시도 성공 집계**: 메인 `_request` 의 5xx WARNING 은 `(path, status)` 키로 60초 dedupe 한다(`_request_5xx_dedupe`, `_REQUEST_5XX_DEDUPE_WINDOW=60.0`). WARNING 은 헬퍼 `_warn_http_status()` 경유만 쓴다. 재시도 성공은 `_record_api_recovered(path, attempts)` 로 누적하고 `scheduler._api_recovered_collector_loop` 가 5분마다 `[api_retry_recovered_summary] window=300s total= by_path=` 1행을 남긴다(`_API_RECOVERED_COLLECTOR_WINDOW=300.0`, 빈 윈도우는 skip). 시세 풀은 `_quote_5xx_dedupe`(`(path, label, status)`) · `_record_quote_recovered` · `_flush_quote_recovered_collector` 로 분리돼 있다
  - AST 가드 3: `_request` 안에서 `logger.warning("HTTP …")` 직접 호출 0건(헬퍼 경유만) · 시세 풀 `_record_5xx_for_dedupe` 호출 존재 · `[api_retry_recovered]` 직접 `write_log` 0건(collector 경유만)

---

바뀐 점: 코드 대조 정정 — `kis_request` 라는 함수는 없다(`grep -rn "def kis_request" src` 0건; 진입점은 `kis_get`/`kis_post` → `_request`). Rate Limit 은 `_rate_limit()`(초당 20) + `Semaphore(20)`(동시 20) 둘이다. 재시도는 4xx 도 포함한다(`except httpx.HTTPStatusError` 에 4xx 조기 raise 없음). 건별 `[api_retry_recovered]` INFO 는 cycle76 부터 없고 5분 collector 만 남는다. `_record_api_recovered` 의 시그니처는 `(path)` 하나다. 주문 POST 재전송·접수 후 거부 채널 두 조건은 루트 CLAUDE.md 에만 있던 것을 이 절로 옮겼다.

### base.py — REST 시세성 호출 풀

정본 원문(바뀌거나 빠진 줄만, 원래 순서):

---

- 매매 (`place_order`/`cancel_order`) / 잔고 (`get_balance`/`get_buyable`) / 체결조회 (`get_daily_orders`) / 체결통보 → 메인 단일 (`kis_request` 그대로)
- 🔴 **신규 시세 path 는 화이트리스트 등재 + AST 가드 동반이 의무**다 — 빠뜨리면 그 호출이 `QuotePoolPathError` 로 전건 실패한다(market-cap · finance · vi-status 에서 세 번 반복된 결함. vi-status 가 빠져 있던 동안 매 부팅·재시작마다 VI 시드가 100% 실패했다)
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
- 응답 분기에서 호출 — 성공 (`rt_cd=="0"`) + `actual_label != "main"` → `record_success(label)` / 5xx HTTPStatusError → `record_failure(label, reason=f"http_{status}")` / 보조 매니저 발급 실패 → `record_failure(label, reason="token_issue_fail")`
- KIS rt_cd!=0 비즈니스 거부 → 기록 안 함 (헬스와 무관)
- 네트워크 에러 → 기록 안 함 (클라이언트 측 이슈 가능)
- 임계 초과 시 health_monitor 가 `kis_quote_accounts.update_account(active=False)` + `kis_ws_pool.disable_quote_session(label)` + `[quote_session_disabled]` 영구 1행. DB 실패 graceful — 메모리만 비활성 + WARNING
- 운영자 대응: Settings UI 보조 계좌 카드 `active=true` 토글 → **다음 영업일** `_boot()` 부터 풀 재참여
- **자동 비활성 임계 3종**: consecutive 5 / 5분 50% / 1분 80%(`FAST_WINDOW_SECS=60`, `FAST_MIN_CALLS=10`, `FAST_MAX_FAILURE_RATE=0.8`). 영구 결함 라벨(ISA 등 5xx 80% 이상)을 빠르게 탈락시킨다. 운영자 안내: 5xx 가 잦은 보조 라벨은 자동 임계 도달 전에 Settings UI `active=false` 로 수동 비활성 권장
- **WARNING dedupe** (`_record_5xx_for_dedupe(path, label, status) -> bool`): 동일 `(path, label, status)` 키 60s 윈도우 (`_QUOTE_5XX_DEDUPE_WINDOW=60.0`) 내 재발생 시 첫 1회만 WARNING + 카운트만 누적. ISA 같은 영구 5xx 라벨에서 분당 ~30 행 WARNING → 1행 + 60s summary INFO. lock `_quote_5xx_dedupe_lock` (asyncio.Lock) 동시성 보호
- **메인 fallback 우선**: `_request_via_quote_pool` 의 라벨 선택 직후 `health_monitor.get_recent_5xx_ratio(label)` 조회. `total>=FAST_MIN_CALLS(10)` AND `ratio>=_LABEL_FALLBACK_5XX_RATIO_THRESHOLD(0.8)` 면 `label=None` 강제 (메인 fallback). 3회 재시도 backoff (수 초) 회피 → 응답 지연 ms 단위. 메트릭 `fast_fallback` 카운터 +1 운영 가시화
- **메트릭 확장**: `_quote_request_metrics["fast_fallback"]` — 80%+ 라벨 skip 누적 카운트. `get_quote_request_metrics()` / `reset_quote_request_metrics()` 동기화

---

바뀐 점: 압축 — 라운드로빈·메트릭 격리·health monitor·5xx 억제 bullet 을 합쳤다. `(kis_request 그대로)` → `(kis_get/kis_post)` 정정. vi-status 누락 사고 서술과 ISA 실측 서술을 뺐다.

### order.py — 주문

정본 원문(바뀌거나 빠진 줄만, 원래 순서):

---

- **매수 지정가 분기**: `order_engine.execute_buy` 가 "시장가매매불가" 거부 폴백 시 `place_order(side=BUY, price=fallback_price>0, order_division=LIMIT, exchange=...)`. body 는 `ORD_DVSN=order_division.value`, `ORD_UNPR=str(price)` 직렬화 — 매도 지정가와 동일 경로
- **`OrderDivision`(cycle287, 2026-09-12) — 시각이 정한다.** `place_order` 는 값을 **검증 없이 그대로** `ORD_DVSN` 에 흘려보낸다(화이트리스트 절대 금지 — 끼워 넣으면 `44` 가 조용히 사라진다). 표:
  | **NXT 프리마켓**(08:00~08:50) 매수 승격(cycle291, 2026-09-13) | `"27"` | GTP지정가 | `step_up(현재가,5)` — `"00"` 폴백과 **같은 값**(가격 행위 변경 0). 정본에 규약이 없어 지정가 비대칭 판정으로 골랐다(§3) |
  | **KRX 애프터**(16:00~20:00, 2026-09-14 신설) 1차 | `"44"` | 최유리지정가 | `"0"`(**정본 명시 없음** — 현금주문 문서는 "시장가 등" 비열거형, 신용주문 문서는 열거형이지만 최유리(03)·최우선(04)를 그 열거에서 뺀다. §4-A 비대칭 판단: 틀리면 즉시 거부돼 관측 가능. 현재가를 넣었는데 실제로 0이 필요했다면 상한가 기준 주문금액 산정 위험) |
  41~47 전체가 애프터 전용이지만 `OrderDivision` 은 `41`/`44` 둘만 갖는다 — IOC/FOK(42/43/45/46)는 잔량 자동취소로 손절 잔여를 잃고, 47(최우선지정가)은 자기 방향 최우선호가라 크로스하지 않아 체결 보장이 없다. 27~29(NXT GTP) 전체도 같은 규율로 `27` 하나만 갖는다 — `28`(GTP최유리)은 `ORD_UNPR` 규약이 현금·신용 문서 사이에서 갈리고 얇은 프리마켓 호가에서 1레벨에 멈추며, `29`(GTP최우선)는 자기 방향 최우선호가라 크로스하지 않는다(cycle291 §3). **애프터마켓엔 시장가(01)가 없고 ETP(ETF/ETN) 거래가 불가**(KIS 공지 verbatim). `EXCG_ID_DVSN_CD` 는 이 코드와 별개로 라우팅된다 — 시각·거래소 결정 로직(`_route_exchange_by_clock`/`_apply_clock`)은 `src/engine/CLAUDE.md` §order_engine.py 「cycle287」 절이 정본.
  **`27`(GTP지정가) — cycle291(2026-09-13, 사용자 결정 "(나)안")**: NXT 프리마켓(08:00~08:50) 매수 미체결을 거래소가 08:50 에 일괄취소하도록 위임하는 전용호가. 지금 프리장에 보내는 `00`(지정가)은 그 자동취소를 받지 못해 미체결이 NXT 정규장(09:00:30~)으로 새고, 새는 방향이 역선택 쪽으로만 치우친다(폐기된 프리장 목표가가 잡는 체결은 가설이 깨진 방향에서만 일어난다) — 자문 §1. **매도는 여전히 `00`**이다(자문 §2) — GTP 매도는 08:50 자동취소가 `_selling` 을 해제 주체가 도착하는 ≈09:45(`_scan_loop`)까지 잠가 손절 재평가를 억제하고, 현행 `00`은 오히려 09:00:30 NXT 정규장에서 시세 아래 지정가라 거의 확실히 체결돼 안전망으로 기능한다 — 루트 CLAUDE.md 「매도/손절/Trailing 은 PRE/MAIN/POST 무관 항상 작동」 저촉 판정. 게이트 4중(§실전·NXT 전용·`market_state` 그 시각 유효·프리장 판정) 중 하나라도 실패·예외면 `00`이 그대로 나가 fail-safe. `27` 거부는 우리 분류기 어디에도 안 걸려 미분류로 처리되므로 "우리가 27을 보냈다"는 사실 자체를 게이트로 삼아 같은 가격 `00` 1회 폴백을 강제한다(폴백 없이 raise 하면 `risk.on_tick` 이 죽는다, cycle229 실증). 상세 = `src/engine/CLAUDE.md` §order_engine.py 「cycle291」 절.
  **취소(`cancel_order`)의 `ORD_DVSN`** — 시그니처는 `cancel_order(..., order_division: str | None = None)` 이고 falsy 면 `"00"` 이다. `order_engine` 의 취소 3경로(`_cancel_after_wait`/`_cancel_and_reorder`/`cancel_remaining`)는 이 인자를 **전달하지 않는다** — 애프터 `41`/`44` · GTP `27` 원주문의 취소가 `"00"` 으로 정상 처리되는지는 실적 0건이라 미검증이다(docstring 에 명시). 관측은 매 시도마다 1행 남는다 — `[after_cancel_result] ticker= order_no= ord_dvsn= orig_dvsn= dvsn_src=map|absent exchange= result=ok|error err=`(`ord_dvsn` = 실제 전송값, `orig_dvsn` = 원주문이 실었던 호가유형 = `OrderEngine._order_division` 매핑, `_order_exchange` 와 대칭). 🔴 **원주문 호가유형 승계 전송은 매매 행위 변경이라 별도 승인 대상**이다 — 정본에 "취소 시 원주문 호가유형을 승계하라" 는 규약이 없고(국내주식 정정취소 필드표에 그 문장이 없다. 선물옵션만 `[취소] 01 로 입력` 고정값을 명시), 켜면 실적 있는 정규장 부분체결 취소의 `ORD_DVSN` 이 `"00"`→`"01"`(원주문 시장가)로 바뀐다. 전환 선결 조건 = `orig_dvsn` 이 `41|44|27` 인 행만 `result=error` 로 층화되는 실측.

---

바뀐 점: 압축 — GTP `27` 의 채택 근거·매도 제외 이유와 `44` 의 `ORD_UNPR="0"` 비대칭 판단은 정본이 `src/engine/CLAUDE.md` 「order_engine.py」 절 규칙 2·4 라 링크로 줄였다. 취소 `ORD_DVSN` 승계 규약 부재의 문서 대조 근거(정정취소 필드표·선물옵션 고정값)를 뺐다.

### balance.py — 잔고/조회

정본 원문(바뀌거나 빠진 줄만, 원래 순서):

---

- `get_balance(afhr_flpr="N")`: `AFHR_FLPR_YN` query. `N`(기본 정규장) / `Y`(시간외 단일가) / `X`(NXT 정규장) — required
- 🔴 **`get_balance()` 의 `prpr`(현재가)은 KRX 애프터마켓 체결을 반영하지 않는다 (2026-09-14 라이브 실측).** 16:00~20:00 내내 보유 11종목의 `prpr` 이 전부 무변동이었는데, 같은 종목 `004020` 을 `quotation.inquire_ccnl` 로 조회하면 `last_cntg_hour=195947`(19:59:47 체결)이 나온다 — **REST 시세 조회는 그 체결을 본다.** **실측 범위는 `prpr` 하나다** — `evlu_amt`(평가금액)·`nass_amt`(순자산, `summary.net_asset` 의 원천)는 KIS 가 서버에서 계산해 내려주는 별도 필드라 같이 얼었는지 **재지 않았다**. 얼었다고 보는 것이 자연스럽지만(같은 현재가에서 파생될 것이므로) 그건 **[추론]** 이다. 확인 방법 = 애프터 구간에 `evlu_amt` 와 `prpr × hldg_qty` 를 대조한다 — 어긋나면 별도 갱신 경로가 있다는 뜻이다. ⚠️ 2026-09-14 제도 변경으로 그 창이 연속 체결 구간이 됐으니, 애프터마켓 가격을 근거로 판단하는 코드는 `get_balance` 가 아니라 시세 조회를 써야 한다(현재 소비처 = 대시보드 표시 · `account_risk_watcher` 의 `summary.net_asset`)
- `get_daily_orders(target_date="", exchange="ALL", *, odno="", pdno="")`: TTTC0081R. `EXCG_ID_DVSN_CD` query required — `ALL`(기본, KRX+NXT+SOR 합산) / `KRX` / `NXT` / `SOR`. NXT 체결 누락 방지 위해 기본 ALL. `odno`(keyword-only)는 `ODNO` 필터라 그 주문 1건의 행만 돌려준다(cycle373 실측). `pdno`(keyword-only)는 `PDNO` 종목 필터다. 둘 다 기본값 `""` 이면 params 가 전체 목록 조회와 같다. 필터 인자 소비처 = `engine/buying_reconcile.py`(`odno` — 자기 주문 행 조회. 전체 목록의 첫 쪽 잘림에 기대지 않는다) · `engine/order_engine.py` `execute_sell` #1.5 재대조(`exchange="ALL", pdno=ticker` — 그 종목 매도 주문별 누적 체결 `tot_ccld_qty` 로 재대조 크레딧을 적는다. 서버가 `PDNO` 를 무시해도 되도록 `_sell_fills_by_order` 가 `pdno`·`sll_buy_dvsn_cd` 로 행을 다시 거른다)
- `is_insufficient_quantity(KisApiError) -> bool`: 보유 부족 매도 실패. msg1 키워드 ("부족" + "매도가능/보유수량/잔고") + `APBK0918` 은 보유 키워드 동반 시만 True. 매도 즉시 break 결정용
- **`is_sell_qty_exceeded(KisApiError) -> bool` (cycle236, N2)**: 매도 수량 초과 — `msg_cd=APBK0400` ∧ msg1 "수량"·"초과" 동시(보수 매칭 — 정본 오류코드 사전 부재라 실측 3건(08-28 257720, TTTC0011U)이 근거). 의미 = "요청 > 매도 가능" = **부분 보유가 내재된 코드** → `is_insufficient_quantity`(positions 통째 삭제 경로)에 **흡수 금지**가 계약. 소비 = `execute_sell` **#1.5**(closed 다음·insufficient 앞): `get_balance` 재대조 → 오염(held<positions) = **held(보유 실체)로 보정**+재시도 자기 치유 / 부분·전량 잠김(held≥positions ∧ sellable<held) = 보존+중단(`_selling` **유지** — 열린 기주문 실재, stale 은 selling_reconcile 180s 소관) / 실보유 0 = insufficient 경로 재사용 / 재대조 실패 = 일반 재시도. 검사 순서 = **closed → sell_qty_exceeded → insufficient → disallowed**(closed 우선 계약 불변)
- `is_market_order_disallowed(KisApiError) -> bool`: 시장가 거부. msg1 키워드 `_MARKET_ORDER_DISALLOWED_KEYWORDS`: `시장가매매불가` / `시장가 매매 불가` / `시장가 주문 불가` / `시장가 호가 불가` / `시장가호가불가` / `최유리/최우선지정가 주문만` / `지정가 및 최유리` / `단일가매매`. ⚠️ **`is_market_closed_rejection` 과 이중 매칭이 실재한다** — APBK0918 "장운영시간이 아닙니다.([프리마켓] 시장가 매매 불가 시간)" 은 양쪽 키워드에 동시 매칭한다. `execute_sell` 은 closed 를 **먼저** 검사하므로 이중 매칭 = 보류(포지션 보존 + 다음 09:00 TTL) — 프리장 왜곡 시세라 지정가 폴백 즉시 매도보다 보류가 안전하다는 **의도된 계약**이고, 순서 반전은 가드가 막는다(`test_rejection_classifier_pre_market_priority.py`). `is_insufficient_*` 2종과는 상호 배타. msg_cd 누적: APBK1943 (계양전기 매도) + APBK3013 (NXT 애프터 매도 · 단일가 세션 변형 — closed 미매칭이라 지정가 폴백 정상 경로). `docs/kis/error-codes.md` 4-2절 / 5-4절

---

바뀐 점: 정정 — `AFHR_FLPR_YN` 값 의미가 2026-09-14 제도 변경으로 `N` KRX 정규장 종가 / `X` NXT / `Y` KRX+NXT 통합시세가 됐다(`docs/kis/README.md` 「제도 변경 공지 반영」). `is_insufficient_quantity` 의 msg_cd 화이트리스트 `APBK1234` 누락 보강. `is_sell_qty_exceeded` 의 #1.5 소비 분기 서술은 cycle385 부분 잠김 판매(`fire = sellable − (held − eff)`) 이전 모양이라 engine 「order_engine.py」 절 링크로 바꿨다. `prpr` 실측(004020 `last_cntg_hour=195947`) 서술을 줄였다.

### kis_master.py — KIS 공식 일일 마스터 파일

정본 원문(바뀌거나 빠진 줄만, 원래 순서):

---

> **구현 방식 (KIS 공식 샘플 대비 의도된 변경)**: KIS 정제 샘플 (`kis_kospi_code_mst.py` / 구조체 `.h`) 의 pandas (`read_csv` + `read_fwf` + Excel 출력) + 디스크 파일 방식을 폐기하고, **`struct.unpack` 순수 파싱 + `httpx.AsyncClient` 메모리 처리 (`io.BytesIO`, 디스크 I/O 0)** 로 이식. field_specs / 필드 순서는 샘플과 100% 일치, 후미 byte 만 정본 정합값(227/221)으로 보정 (샘플 228/222 는 텍스트 모드 줄바꿈 여유분). pandas 의존성 없음.
### URL 정본 (KIS 공식 저장소 검증 확정)
- `ssl._create_unverified_context` (사용자 샘플 무조건 검증 off) 영구 폐기
- 진입 차단 7건 (HIGH): `trht_yn` 거래정지 / `mang_issu_yn` 관리종목 / `ssts_hot_yn` 공매도과열 / `stange_runup_yn` 이상급등 / `sltr_yn` 정리매매 / `mrkt_alrm_cls_code` 시장경고 / `invt_alrm_yn` 투자주의환기 (코스닥 전용)
- 기타: `stck_lstn_date` 상장일자 / `po_prc` 공모가 / `prst_cls_code` 우선주 / `byps_lstn_yn` 우회상장 / `flng_cls_code` 락구분 / `short_over_cls_code` 단기과열 / `insn_pbnt_yn` 불성실공시
- `src/engine/scheduler.py::_stock_master_master_load_task_loop()` — 16:30 KST 자동 task lifecycle

---

바뀐 점: 압축 — 샘플 대비 구현 설명·URL 검증 경위를 줄였다. 진입 차단 7건의 소비처(`scanner._is_master_blocked_for_entry`)와 청산 판정 금지 키 경고를 보강했다. 호출자 줄에 위임 본체(`data_load_tasks`)를 적었다.

### finance.py — KIS 재무 5 TR fetch

정본 원문(바뀌거나 빠진 줄만, 원래 순서):

---

퀀트 재무필터 (마법공식 EV/EBITDA·ROC + F-Score-7) 원천 데이터. KIS 재무 5 TR 을 `kis_get_quote` 시세성 풀 경유로 호출 → `stock_master_financial` 정규화. `fetch_daily_candles_ranged` 답습 (6자리 ticker 가드).
- **TR_ID 컨벤션 = FH 접두사 직접 하드코딩** (`settings.get_tr_id()` 미사용) — 5 TR 모두 FH 접두사 = 실전/모의 동일이나, 헬퍼의 V+base[1:] 변환이 `FH...` → `VH...` 로 깨짐 → 직접 하드코딩. 응답 output = 다기간 list
- **시세성 풀 화이트리스트 13 path 필수** (base.py `_QUOTE_ALLOWED_PATHS` — finance 5 path, 위 base.py 절 참조)
- 호출자: `src/engine/scanner.py::_stock_master_financial_load_once()` (주1회 16:40) + 관찰 훅 `volatility_breakout._apply_quant_filter_in_prepare` (오프라인)

---

바뀐 점: 정정 — 「FH 직접 하드코딩으로 `VH` 깨짐을 피한다」는 근거는 성립하지 않는다. `TokenManager.build_headers` 가 모든 요청 헤더에 `settings.get_tr_id()` 를 적용하므로 모의에서는 FH 도 `VH` 로 나간다(`src/auth/token.py` `build_headers`). VB 관찰 훅은 finance.py 호출자가 아니라 `stock_master_financial` DB 소비자다(`grep fetch_all_financials` = scanner 하나).

### krx.py — KRX 정식 OPEN API 클라이언트

정본 원문(바뀌거나 빠진 줄만, 원래 순서):

---

- **GET** + 인증은 **query parameter `AUTH_KEY=`** + 파라미터도 **query string `params=`**. 외부 정본 2건(`raccoonyy/pykrx-openapi/src/pykrx_openapi/client.py` 의 `self.session.get(url, params=params, timeout=self.timeout)` · `seobaeksol/krx-rs/docs/krx-api-reference/KRX_API_Spec.md`)이 독립 일치
### 폴백 (호출자 `src/engine/scanner.py::_full_universe_load_once`)
- KRX 1차 우선 호출 (4 endpoint + 50ms sleep = KIS LMS chain 안전 마진)
- 4 endpoint 모두 `KrxApiError`(비활성/401/4xx/5xx/네트워크 예외) 를 호출자에게 전파 → KIS market-cap 자동 폴백
**Rate Limit**: 키당 일일 10,000 호출 (현재 4 호출/일).

---

바뀐 점: 정정·압축 — 외부 정본 2건 대조 경위를 뺐다. 폴백 호출 구조는 `_full_universe_load_once` → `_full_universe_load_krx_primary` 다. 「현재 4 호출/일」은 빈 응답 재시도(최대 7회)를 빠뜨린 값이라 고쳤다. `krx_open_api_enabled` 비활성 = 경로 변경 경고는 루트 「비활성화 심층 검증」 사례를 이 절에 링크로 옮겼다.

### market_operation.py — 장운영정보(H0UNMKO0) 정본 + VI 현황 REST 폴백

정본 원문(바뀌거나 빠진 줄만, 원래 순서):

---

| `VI_STATUS_TR_ID = "FHPST01390000"` · `VI_STATUS_URL = "/uapi/domestic-stock/v1/quotations/inquire-vi-status"` | 부팅 시드용 REST 보조 폴백. 이 path 는 시세 풀 화이트리스트에 **있어야 한다**(2026-08-04 추가 — 없던 동안 매 부팅 `QuotePoolPathError` 로 VI 시드가 100% 실패했다) |
`[0]=종목코드` 다(EC2 실측 2026-09-21~23, 17건 전수). 그래서 파서는
`"(null)"` 은 KIS null 토큰이다 — 라이브 프레임은 일부 빈 칸을 빈 문자열 대신 이 글자 그대로 보낸다(실측 17건 모두 정지 사유 칸이 `(null)`).

---

바뀐 점: 압축 — 실측 건수(17건 전수)와 2026-08-04 화이트리스트 추가 경위를 뺐다.

### quotation.py — 주식현재가 체결

정본 원문(바뀌거나 빠진 줄만, 원래 순서):

---

  - 응답: output 첫 row (가장 최근 체결) + today_volume 합산. 키: `last_cntg_hour`(HHMMSS) / `last_price` / `last_volume` / `last_relative_strength` / `today_volume` / `prev_compared_rate`
  - 호출처: `scheduler._evaluate_universe_guard` (universe 제외 판단) + `scheduler._refresh_stale_ccnl_cache` (stale 종목 UI 표시용 TTL 5분 캐시)
- 공통: graceful (빈 응답 / KIS 오류 / 예외 → `None` — 호출자가 "판정 근거 없음" 으로 처리) + 6자리 ticker 사전 가드 (`ValueError`)

---

바뀐 점: 정정 — `inquire_ccnl` 반환 키에 `prev_compared_rate` 는 없고 `raw_count` 가 있다. 호출처 본체는 `stale_universe_guard.evaluate_universe_guard`·`stale_diagnostics.refresh_stale_ccnl_cache` 다. ticker 가드는 6자리 영숫자(`_TICKER_PATTERN`)다.

### condition.py — 조건검색 + 영업일 + 종목 기본정보 + TTL 캐시

정본 원문(바뀌거나 빠진 줄만, 원래 순서):

---

- `fetch_rising_stocks()` 는 등락률 15% 이상 종목마다 `fetch_stock_detail` 을 불러, `stck_sdpr`(거래소 기준가)가 양수면 `scanner.ticker_prev_close[ticker]` 를 그 값으로 덮는다(실시간 등락률 계산용).
- `is_trading_day(target_date) -> bool | None`: 같은 CTCA0903R 호출을 **3상태**로 감싼 함수 — True=개장 / False=휴장 / None=모름(조회 실패·그 날짜 행 없음·예외). 「모른다」를 「개장」으로 바꾸지 않는 것이 `is_market_open` 과의 차이다. 호출자 = `src/routes/market_state.py`(장운영상태 화면, `market_ops.py` 가 그 `_resolve_trading_day` 를 재사용) + `src/engine/trading_calendar.py` 의 조회 seam `_lookup_open`(부팅 즉시 실행 영업일 슬롯 게이트 · 6전략 prepare `expected_head` — None 이면 게이트는 실행 쪽, 어댑터는 달력 판정 쪽으로 떨어진다). KIS 공지 「CTCA0903R 은 가급적 1일 1회」는 그 leaf 의 날짜별 메모(True/False 만 캐시)가 지킨다 — 상세 = `src/engine/CLAUDE.md` `trading_calendar.py` 항목
- `add_business_days(base_date, n)`: base_date 이후 n번째 개장일 date. CTCA0903R 1회 호출(~30일치)에서 `opnd_yn=="Y"` n번째 row. 실패/개장일 부족 시 `base + timedelta(n+2)` 달력일 폴백 graceful. BFB/VCP 재진입 쿨다운 영업일 정정용 (`_refine_cooldown_business_days` 소비)
- **분할 fetch (날짜 윈도우 100건 경계) + VCP backfill 225일**:
  - `fetch_daily_candles_ranged(ticker, start_yyyymmdd, end_yyyymmdd) -> list[dict]`: KIS `FHKST03010100` 단일 윈도우 조회 (`FID_INPUT_DATE_1`=시작 / `FID_INPUT_DATE_2`=종료 / `FID_PERIOD_DIV_CODE="D"` / `FID_ORG_ADJ_PRC="0"` / `FID_COND_MRKT_DIV_CODE="J"`). `kis_get_quote` 경유 (시세성 풀 + Rate Limit + 메트릭). output2 (최신순) + `stck_bsop_date` 빈 placeholder 제거. **memcache/single-flight 미사용** (backfill 전용). 6자리 ticker 가드 (`ValueError`). **`FID_ORG_ADJ_PRC="0"` (수정주가) = `_fetch_daily_candles_and_cache` 와 같은 값** — DB-source ↔ KIS-source 동등성의 전제다 (KIS 정본 샘플은 `"1"` 예시이나 이 코드베이스는 `"0"` 을 쓴다)
  - **달력 환산은 축이 둘이고 역할이 다르다 — 합치지 않는다.** ① **stride** `_WEEKEND_CAL_PER_TRADING_DAY = 7/5`(주말만) = 윈도우 시작점 간격. 🔴 **이 값을 키우면 윈도우 사이에 구멍이 생긴다** — KIS 가 한 호출에 100건까지만 주므로 앞 윈도우는 공휴일 0 구간에서 정확히 100영업일 = 140달력일까지만 덮는다. stride 가 140 을 넘으면 그 아래가 통째로 비고 어느 윈도우도 다시 집지 않는다. ② **depth**(마지막 윈도우 시작점)에만 휴일 보정을 비례로 얹는다 — `_DAILY_BACKFILL_HOLIDAY_MARGIN_RATIO = 0.10` + `_DAILY_BACKFILL_BASE_MARGIN_CAL = 10`. `total_days=225` → 347 달력일 = 실측 비율(1.479)로 **약 232 영업일**이라 1회 backfill 이 target 을 **넘는다**(공휴일 0 인 해 247 · 밀집한 해 228 로 어느 쪽도 목표 위). 가드 = `tests/unit/engine/test_cycle299_backfill_target_expansion.py::test_g299_9_one_pass_reaches_target`(실도달 ≥ target)
  - **`fetch_daily_candles` 와 별도 함수**다 (그쪽은 memcache 5분 + single-flight + `asyncio.shield` 유지). 호출자 = `scanner._stock_master_daily_load_once` (**일봉 적재 대상 전부** 225일, `_DAILY_LOAD_VCP_BACKFILL_DAYS` — 이름의 `VCP` 는 이 깊이를 처음 요구한 전략의 흔적이고 대상은 index ∪ 자격 ∪ 보호 전체다, cycle302). 매매 hot path 무관 — 데이터 적재 한정, 매수 진입 전 영역. 가드 `tests/unit/api/test_cycle172_daily_ranged_backfill.py`
- **`inquire_stock_basics(pdno) -> StockBasics`**: KIS `CTPF1002R` — NXT 거래종목 (`cptt_trad_tr_psbl_yn`) + NXT 거래정지 (`nxt_tr_stop_yn`) + KRX 정지 + 관리종목 파싱 → `StockBasics` 반환. 파생값 `nxt_tradable = (cptt=="Y") AND (nxt_stop=="N")`. CTPF 접두사 TR_ID 는 모의/실전 동일. 캐시 `src.db.stock_master` 24h TTL. **ticker 정규화**: `_normalize_ticker()` 가 KIS `pdno` 12자리 표준코드 → KRX 6자리 단축코드 추출 (정규식 `(\d{6})$`). `stock_master` PK 정합성 보장. `docs/kis/error-codes.md` 5-3절
  - **raw merge**: `merged_raw = dict(ctpf_output)` 에 `_FHKST_MERGE_KEYS` 35키만 덮어쓴다 — 목록 밖 CTPF 키는 건드리지 않는다(`bfdy_clpr` 보존이 가드 대상). 그중 `_ZERO_VALUE_SKIP_KEYS` 15키(`acml_tr_pbmn`·`acml_vol`·`per`·`pbr`·`vol_tnrt`·`prdy_vrss_vol_rate`·`hts_frgn_ehrt`·`frgn_ntby_qty`·`w52_hgpr`·`w52_lwpr`·`d250_hgpr`·`d250_lwpr`·`eps`·`bps`·`whol_loan_rmnd_rate`)는 값이 **0 이거나 비숫자·None 이면 merge 하지 않고 `continue`** 한다 — 장전 호출의 `0` 이 전일 거래대금을 지우면 `list_by_filter(acml_tr_pbmn ≥ min_trade_amount)` 가 조용히 0건이 되어 donchian/VB/LTV 후보가 사라진다
  - 가드 `tests/unit/api/test_cycle107_inquire_stock_basics_merge.py` · `test_cycle108_hts_avls.py` · `test_cycle144_graceful_visibility.py` · `test_cycle145_raw_preserve.py` · `tests/unit/engine/test_cycle176_basics_refresh_raw_merge.py` · `test_cycle176_e2e_premarket_preservation.py`
- `asyncio.Lock` + `_inflight_*: dict[key, Task]` single-flight — 동시 N 호출 시 첫 호출만 KIS fetch, 나머지 task 합류
- joiner 는 `await asyncio.shield(task)` 합류 — 자기 task cancel 시 inflight cancel 전파 차단
- **종목상태 관측 훅 `_notify_status_observer(ticker, output)` (cycle369)** — `_fetch_stock_detail_and_cache` 가 KIS 응답의 `output` 대입 **직후** · 캐시 lock **앞**에서 한 번 부른다. 훅은 `src.engine.status_exit_watch.observe_fhkst` 를 함수 안에서 지연 import 해 부르고, 관리종목·단기과열 당일 매수 차단 레지스트리에 기록만 한다. 캐시 적중·inflight 합류 경로는 부르지 않는다(첫 조회가 이미 기록했다). leaf 자신의 패스가 부른 조회는 leaf 가 기록을 건너뛴다(패스가 직접 기록한다 — 한 조회 한 기록). 🔴 **본문 전체의 `try/except Exception` 을 걷지 않는다**(DEBUG `[status_observer_failed]`, never-raise) — 훅이 예외를 흘리면 모든 `fetch_stock_detail` 소비자(VB·LTV 기준가 REST · 스윙 폴 · 급등 스캔)가 깨진다. 호출 자리·이중 try 는 AST J16 이 잠근다

---

바뀐 점: 정정 — `_FHKST_MERGE_KEYS` 는 33키다(`tests/unit/ast/test_cycle155_ast_merge_keys.py` 가 33 을 단언). `_normalize_ticker` 정규식은 `([A-Za-z0-9]{6})$` 이고 6자리 영숫자는 그대로 둔다. 가드 파일명 `test_cycle108_hts_avls.py` → `test_cycle108_inquire_stock_basics_hts_avls.py`. `add_business_days` 소비는 BFB/VCP 한정이 아니라 `StrategyBase._refine_cooldown_business_days`(5전략) 다. 공휴일 0·밀집 해 도달 계산(247·228)을 뺐다.

### period_chart.py — 종목 차트용 기간별시세 (cycle387)

정본 원문(바뀌거나 빠진 줄만, 원래 순서):

---

     순간 다음 조회가 곧바로 KIS 를 부르고, 가짜 지연 50ms 재현에서 월봉 40종목 연속 조회가 첫 1초에 20건(전역 한도 전부)을 쓴다

---

바뀐 점: 압축 — 호출 간격 금기의 재현 수치(가짜 지연 50ms · 월봉 40종목 · 첫 1초 20건)를 뺐다.

### 새 API 추가 절차

정본 원문(바뀌거나 빠진 줄만, 원래 순서):

---

1. `docs/kis/{category}.md` 에서 TR_ID, URL, 파라미터 확인
2. 본 디렉토리에 함수 추가 (반드시 `kis_request()` 또는 `kis_get_quote()` 사용)
3. TR_ID 는 `settings.get_tr_id("실전TR_ID")` 사용

---

바뀐 점: 정정 — `kis_request()` 는 없다. TR_ID 모의 변환은 `build_headers` 가 모든 요청에 적용한다.

→ CHANGELOG: 해당 없음(문서 정비, 코드 변경 없음)

### balance.py — 잔고/조회 (2026-10-01 추가 압축)

정본 원문:

---

- 위 세 판정(`is_sell_qty_exceeded` · `is_market_closed_rejection` · `is_market_order_disallowed`)은 `order_engine._sell_not_placed_reason` 도 쓴다(cycle385). 매도 발사 예외가 「우리 주문이 거래소에 안 걸렸다」를 확정하는지 가르는 함수이고, 손절 잔여 재주문과 `POST /api/trading/manual-sell` 이 그 결과로 `_selling` 을 푼다. 그 함수는 sell_qty_exceeded → closed → disallowed 순으로 본다. closed 가 disallowed 보다 먼저인 것은 `execute_sell` 과 같아서, 프리마켓 이중 매칭은 `market_closed` 다. 상세 = `src/engine/CLAUDE.md` 「매도 체결 — 주문 축과 보유 축」

---

바뀐 점: `_sell_not_placed_reason` 의 소비자 나열(손절 잔여 재주문 · `POST /api/trading/manual-sell`)을 줄이고 engine 「매도 체결 — 주문 축과 보유 축」 절 링크로 넘겼다. krx.py 필드 목록(bydd_trd 15 · isu_base_info 12)은 줄바꿈만 합쳤고 내용은 그대로다.

→ CHANGELOG: 해당 없음(문서 정비, 코드 변경 없음)

## 2026-10-02 sync-docs 압축 2차 — 정본에서 이관

정본(`src/api/CLAUDE.md`)을 57,088 → 45,999 바이트로 줄인 2차 압축에서 **정본을 떠난 정보가 있는 원문 줄**이다. 같은 파일 안의 반복을 지우거나 문장만 다듬은 줄은 옮기지 않았다(뜻이 정본에 남는다). 절마다 원문 줄을 그대로 옮기고 바뀐 점을 적는다.

### (머리말)

정본 원문(정본을 떠난 정보가 있는 줄만, 원래 순서):

---

KIS OpenAPI REST 호출 모듈. 모든 호출은 `base.py` 공통 래퍼를 통한다. **지금 동작하는 규칙만** 적는다 — 바뀐 경위는 위 history, 사이클별 보고 원문은 [`docs/HARNESS_CHANGELOG.md`](../../docs/HARNESS_CHANGELOG.md) 에 있다.

---

바뀐 점: 머리말에서 「지금 동작하는 규칙만 적는다」 선언과 CHANGELOG 안내를 뺐다. 같은 규약이 루트 `CLAUDE.md` 「문서 규약」 절에 있다. 이력 링크 1줄은 그대로다.

### base.py — 공통 래퍼 (메인 단일)

정본 원문(정본을 떠난 정보가 있는 줄만, 원래 순서):

---

- 자동 재시도: HTTP 오류(4xx·5xx)·네트워크 오류는 `MAX_RETRIES=3` 회까지 시도한다. 지수 백오프 `BACKOFF_BASE=0.5s × 2^(attempt-1)` + jitter `0~BACKOFF_JITTER=0.25s`(thundering herd 완화)

---

바뀐 점: 재시도 jitter 의 목적 설명(「thundering herd 완화」)을 뺐다. 상수·횟수·백오프 식은 그대로다. 같은 절의 `rt_cd != "0"` 로깅 한 줄(「에러 처리」)은 「거부 응답 영구 저장」과 같은 내용이라 지웠다.

### base.py — REST 시세성 호출 풀

정본 원문(정본을 떠난 정보가 있는 줄만, 원래 순서):

---

- 시세성 호출만 본 풀에 라우트: `condition.py` 함수 전부(`is_market_open` · `next_trading_day` · `is_trading_day` · `add_business_days` · `_fetch_fluctuation_rank` · `inquire_stock_basics` · `fetch_stock_detail` · `fetch_daily_candles` · `fetch_daily_candles_ranged` · `fetch_daily_chart_ranged_with_summary`) · `quotation.py`(`inquire_ccnl` · `inquire_acml_vol`) · `finance.fetch_financial_tr` · `market_operation.inquire_vi_status_today` · `period_chart.fetch_candle_chart` · `scanner._fetch_market_cap_page`. `krx.py` 는 KIS 밖 시스템이라 무관
- 🔴 **신규 시세 path 는 화이트리스트 등재 + AST 가드 동반이 의무**다 — 빠뜨리면 그 호출이 `QuotePoolPathError` 로 전건 실패한다(market-cap · finance · vi-status 에서 세 번 반복된 결함)
- 기록 = 성공 (`rt_cd=="0"`) + `actual_label != "main"` → `record_success(label)` / 5xx HTTPStatusError → `record_failure(label, reason=f"http_{status}")` / 보조 매니저 발급 실패 → `record_failure(label, reason="token_issue_fail")`. KIS rt_cd!=0 비즈니스 거부·네트워크 에러는 기록하지 않는다(헬스와 무관 · 클라이언트 측 이슈 가능)
- **자동 비활성 임계 3종**: consecutive 5 / 5분 50% / 1분 80%(`FAST_WINDOW_SECS=60`, `FAST_MIN_CALLS=10`, `FAST_MAX_FAILURE_RATE=0.8`). 영구 결함 라벨(5xx 80% 이상)을 빠르게 탈락시킨다

---

바뀐 점: 시세 풀로 가는 `condition.py` 함수 10개 나열을 「`condition.py` 함수 전부」로 줄였다(함수 이름은 condition.py 절에 남는다). 화이트리스트 누락 금기의 경위(「market-cap · finance · vi-status 에서 세 번 반복된 결함」)와 헬스 기록·임계의 목적 설명을 뺐다. 임계값·식별자·금기 문장은 그대로다.

### order.py — 주문

정본 원문(정본을 떠난 정보가 있는 줄만, 원래 순서):

---

- `place_order(..., exchange="KRX")` / `cancel_order(..., exchange="KRX")`: `EXCG_ID_DVSN_CD` body. `KRX`(기본) / `NXT` / `SOR`. 모의(VTS) KRX 만 허용 — SOR/NXT 실전 한정. 미지정 시 KRX (후방 호환)
  | **NXT 프리마켓**(08:00~08:50) 매수 승격(cycle291) | `"27"` | GTP지정가 | `step_up(현재가,5)` — `"00"` 폴백과 **같은 값**(가격 행위 변경 0) |
  | KRX 애프터 폴백 | `"41"` | 지정가 | `step_down(현재가,5)`(우리가 가격을 통제) |
  `OrderDivision` 은 위 다섯(`00`·`01`·`27`·`41`·`44`)만 갖는다. 애프터의 IOC/FOK(42/43/45/46)는 잔량 자동취소로 손절 잔여를 잃고, 47(최우선지정가)·GTP `29`(GTP최우선)는 자기 방향 최우선호가라 크로스하지 않는다. `28`(GTP최유리)은 `ORD_UNPR` 규약이 현금·신용 문서 사이에서 갈린다. **애프터마켓엔 시장가(01)가 없고 ETP(ETF/ETN) 거래가 불가**(KIS 공지 verbatim). `EXCG_ID_DVSN_CD` 는 이 코드와 별개로 라우팅된다 — 시각·거래소 결정(`_route_exchange_by_clock`/`_apply_clock`)과 애프터 청산 호가의 정본은 `src/engine/CLAUDE.md` 「order_engine.py」 절 규칙 1·2다.
  **`27`(GTP지정가)은 NXT 프리마켓 매수 전용이다.** 미체결을 거래소가 08:50 에 일괄취소한다. **매도는 `00` 그대로다.** 게이트 4중이 하나라도 실패·예외면 `00` 이 그대로 나간다(fail-safe). `27` 거부는 같은 가격 `00` 1회로 폴백한다. 게이트·폴백·매도 제외 이유의 정본 = `src/engine/CLAUDE.md` 「order_engine.py」 절 규칙 4.
  **취소(`cancel_order`)의 `ORD_DVSN`** — 시그니처는 `cancel_order(..., order_division: str | None = None)` 이고 falsy 면 `"00"` 이다. `order_engine` 의 취소 3경로(`_cancel_after_wait`/`_cancel_and_reorder`/`cancel_remaining`)는 이 인자를 **전달하지 않는다** — 애프터 `41`/`44` · GTP `27` 원주문의 취소가 `"00"` 으로 정상 처리되는지는 실적 0건이라 미검증이다(docstring 에 명시). 🔴 **원주문 호가유형 승계 전송은 매매 행위 변경이라 별도 승인 대상**이다 — 정본에 승계 규약이 없고, 켜면 실적 있는 정규장 부분체결 취소의 `ORD_DVSN` 이 `"00"`→`"01"`(원주문 시장가)로 바뀐다. 관측 `[after_cancel_result]`(`orig_dvsn=`·`dvsn_src=`)과 전환 선결 실측 = `src/engine/CLAUDE.md` 「order_engine.py」 절 규칙 4 「취소 축 Stage A」.

---

바뀐 점: `OrderDivision` 에서 47·`28`·`29` 를 뺀 이유(대안 비교)를 여기로 옮기고, 정본에는 IOC/FOK 가 손절 잔여를 잃는다는 이유 하나만 남겼다. 표의 「가격 행위 변경 0」「우리가 가격을 통제」 설명, `27` 게이트·폴백의 상세, 취소 축의 「정본에 승계 규약이 없고」와 `orig_dvsn=`·`dvsn_src=` 필드는 정본 위치인 `src/engine/CLAUDE.md` 「order_engine.py」 절 규칙 4(「취소 축 Stage A」)로 넘겼다. 승계 전송 금기와 그 이유 한 문장은 남겼다.

### balance.py — 잔고/조회

정본 원문(정본을 떠난 정보가 있는 줄만, 원래 순서):

---

- 🔴 **`get_balance()` 의 `prpr`(현재가)은 KRX 애프터마켓 체결을 반영하지 않는다** — 16:00~20:00 보유 종목 `prpr` 이 전부 무변동이었고, 같은 시각 `quotation.inquire_ccnl` 은 그 체결을 봤다(2026-09-14 실측). 애프터마켓 가격으로 판단하는 코드는 `get_balance` 가 아니라 시세 조회를 쓴다(현재 소비처 = 대시보드 표시 · `account_risk_watcher` 의 `summary.net_asset`)
  - `engine/buying_reconcile.py`(`odno`) — 자기 주문 행 조회. 전체 목록의 첫 쪽 잘림에 기대지 않는다
  - `engine/order_engine.py` `execute_sell` #1.5 재대조(`exchange="ALL", pdno=ticker`) — 매도 주문별 누적 체결 `tot_ccld_qty` 로 재대조 크레딧을 적는다. 서버가 `PDNO` 를 무시해도 되도록 `_sell_fills_by_order` 가 행을 다시 거른다(상세 = `src/engine/CLAUDE.md` 「매도 체결 — 주문 축과 보유 축」)

---

바뀐 점: `prpr` 애프터마켓 미반영 금기의 근거 실측(2026-09-14, 16:00~20:00 보유 종목 무변동 · `inquire_ccnl` 은 체결을 봄)을 옮겼다. `get_daily_orders` 소비처 두 줄은 한 줄로 합치고 `tot_ccld_qty` 크레딧 설명은 `src/engine/CLAUDE.md` 「매도 체결 — 주문 축과 보유 축」으로 넘겼다.

### KIS 거부 응답 분류 헬퍼

정본 원문(정본을 떠난 정보가 있는 줄만, 원래 순서):

---

- `is_market_order_disallowed(KisApiError) -> bool`: 시장가 거부. msg1 키워드 `_MARKET_ORDER_DISALLOWED_KEYWORDS`: `시장가매매불가` / `시장가 매매 불가` / `시장가 주문 불가` / `시장가 호가 불가` / `시장가호가불가` / `최유리/최우선지정가 주문만` / `지정가 및 최유리` / `단일가매매`. `is_insufficient_*` 2종과는 상호 배타. msg_cd 누적: APBK1943 (계양전기 매도) + APBK3013 (NXT 애프터 매도 · 단일가 세션 변형 — closed 미매칭이라 지정가 폴백 정상 경로). `docs/kis/error-codes.md` 4-2절 / 5-4절
- 위 세 판정(`is_sell_qty_exceeded` · `is_market_closed_rejection` · `is_market_order_disallowed`)은 `order_engine._sell_not_placed_reason`(cycle385)도 쓴다 — 매도 발사 예외가 「우리 주문이 거래소에 안 걸렸다」를 확정하는지 가르고, 그 결과로 `_selling` 을 푼다. 순서 = sell_qty_exceeded → closed → disallowed(closed 가 먼저라 프리마켓 이중 매칭은 `market_closed`). 상세 = `src/engine/CLAUDE.md` 「매도 체결 — 주문 축과 보유 축」

---

바뀐 점: APBK1943 의 출처 사례(「계양전기 매도」)를 옮겼다. 키워드 8종·msg_cd·검사 순서는 그대로다. `_sell_not_placed_reason` 소비자 설명은 순서와 `_selling` 해제만 남기고 `src/engine/CLAUDE.md` 「매도 체결 — 주문 축과 보유 축」으로 넘겼다.

### kis_master.py — KIS 공식 일일 마스터 파일

정본 원문(정본을 떠난 정보가 있는 줄만, 원래 순서):

---

> **구현 방식**: KIS 공식 샘플의 pandas + 디스크 파일 방식 대신 **`struct.unpack` 순수 파싱 + `httpx.AsyncClient` 메모리 처리 (`io.BytesIO`, 디스크 I/O 0)** 다. pandas 의존성 없음. field_specs / 필드 순서는 샘플과 100% 일치하고, 후미 byte 만 정본값(227/221)이다(샘플 228/222 는 텍스트 모드 줄바꿈 여유분).

---

바뀐 점: 구현 방식의 대안 비교(KIS 샘플의 pandas + 디스크 파일 방식 대신)를 옮겼다. 정본에는 현재 구현(`struct.unpack` · `httpx.AsyncClient` · `io.BytesIO` · pandas 없음)과 후미 byte 227/221(샘플 228/222 는 줄바꿈 여유분)만 남겼다.

### 매매 활용 키 ~30

정본 원문(정본을 떠난 정보가 있는 줄만, 원래 순서):

---

- 시총: `prdy_avls_scal` 전일 시가총액 (**억 원**). 시총 필터는 `list_by_filter` / `list_paged_by_filter` 가 `raw.hts_avls`(억원) 기준 직접 수행
- 재무: `roe` / `sale_account` 매출액 / `bsop_prfi` 영업이익 / `op_prfi` 경상이익 / `thtr_ntin` 당기순이익
- 지수편입: `kospi200_apnt_cls_code` / `kospi100_issu_yn` / `kospi50_issu_yn` / `ksq150_nmix_yn` / `krx300_issu_yn` / `krx_issu_yn`
- 시장 영역: `lstn_stcn` 상장주수 (천주) / `cpfn` 자본금 / `marg_rate` 증거금비율 / `crdt_able` 신용가능
- 기타: `stck_lstn_date` 상장일자 / `po_prc` 공모가 / `prst_cls_code` 우선주 / `byps_lstn_yn` 우회상장 / `flng_cls_code` 락구분 / `short_over_cls_code` 단기과열구분 / `insn_pbnt_yn` 불성실공시

---

바뀐 점: 진입 차단 7건과 관리종목·단기과열 금기는 정본에 남겼다. 나머지 활용 키 목록(시총·재무·지수편입·시장·기타)과 한글 이름은 `frontend/src/pages/StockMaster.tsx::FIELD_LABELS` 에 같은 키가 모두 있어 그 위치를 가리키게 했다(2026-10-02 grep 확인).

### 단위 환산

정본 원문(정본을 떠난 정보가 있는 줄만, 원래 순서):

---

- `prdy_avls_scal` (KIS 마스터) = **억 원** (구조체 `.h` 명세 "전일기준 시가총액 (억)" 기준. 1 억 = 100,000,000 원 = 100 백만원)
- 🔴 **`hts_avls` 를 백만원으로 읽지 않는다** — 100배 어긋나 `min_market_cap=1,000억` 에서 후보 풀이 1,734 → 80 으로 잘린다(95.4% 축소)

---

바뀐 점: 「1 억 = 100,000,000 원 = 100 백만원」 환산 예와 금기의 실측 비율(95.4% 축소)을 옮겼다. 금기 문장과 1,734 → 80 은 남겼다.

### finance.py — KIS 재무 5 TR fetch

정본 원문(정본을 떠난 정보가 있는 줄만, 원래 순서):

---

퀀트 재무필터 (마법공식 EV/EBITDA·ROC + F-Score-7) 원천 데이터. KIS 재무 5 TR 을 `kis_get_quote` 시세성 풀 경유로 호출 → `stock_master_financial` 정규화. 6자리 숫자 ticker 가드(`ValueError`).
| kind | path | TR_ID | 산출 컬럼 |
|------|------|-------|----------|
| income | `/finance/income-statement` | FHKST66430200 | sale_account / sale_totl_prfi / bsop_prti / thtr_ntin / depr_cost |
| balance | `/finance/balance-sheet` | FHKST66430100 | cras / fxas / total_aset / flow_lblt / total_lblt / total_cptl / cpfn |
| profit | `/finance/profit-ratio` | FHKST66430400 | cptl_ntin_rate / sale_totl_rate |
| stability | `/finance/stability-ratio` | FHKST66430600 | lblt_rate / crnt_rate |
| other | `/finance/other-major-ratios` | FHKST66430500 | ebitda / ev_ebitda |
- 호출자: `src/engine/scanner.py::_stock_master_financial_load_once()` 하나(주1회 16:40). 적재된 `stock_master_financial` 은 VB 관찰 훅 `volatility_breakout._apply_quant_filter_in_prepare` 가 DB 로 읽는다

---

바뀐 점: 재무 5 TR 의 용도와 산출 컬럼 18종은 `src/db/CLAUDE.md` 「stock_master_financial.py」 절(정규화 NUMERIC 18종)과 같은 내용이라, 표의 컬럼 칸을 그룹 이름(손익 5 · 대차 7 · 수익성 2 · 안정성 2 · 기타 2)으로 줄이고 그 절을 가리키게 했다. 적재 테이블을 VB 관찰 훅이 읽는다는 문장도 db 절에 있어 뺐다.

### krx.py — KRX 정식 OPEN API 클라이언트

정본 원문(정본을 떠난 정보가 있는 줄만, 원래 순서):

---

- **bydd_trd 핵심 15 필드**: `ISU_CD`(단축코드 6자리, KRX 종목코드 정합) / `ISU_NM` / `MKT_NM` / `SECT_TP_NM` · 가격 `TDD_CLSPRC` / `TDD_OPNPRC` / `TDD_HGPRC` / `TDD_LWPRC` / `CMPPREVDD_PRC` / `FLUC_RT` · 거래 `ACC_TRDVOL` / **`ACC_TRDVAL`**(원 단위, `min_trade_amount` 직접 정합) · 시총 **`MKTCAP`**(원 단위 → KIS `hts_avls`(억원) 환산 `// 100_000_000`) · 상장 `LIST_SHRS`
- **isu_base_info 12 필드**(ticker 정합): `ISU_CD`(12자리 표준코드, **사용 금지** — stock_master PK 비정합) / **`ISU_SRT_CD`**(단축코드 6자리, KRX 종목코드 정합) / `ISU_NM` / `ISU_ABBRV` / `ISU_ENG_NM` / `LIST_DD`(상장일) / `MKT_TP_NM` / `SECUGRP_NM`(증권구분) / `SECT_TP_NM` / `KIND_STKCERT_TP_NM`(보통주/우선주) / `PARVAL`(액면가) / `LIST_SHRS`
**회귀 가드**: `tests/unit/api/test_cycle112_krx_client.py` · `tests/unit/api/test_cycle115_krx_endpoints.py` · `tests/unit/engine/scanner/test_cycle115_full_universe_load_krx_fallback.py` · `tests/unit/ast/test_cycle115_krx_endpoint_urls.py` (endpoint 경로 상수) · `tests/unit/ast/test_cycle115_krx_no_plaintext_key.py` (평문 key 노출)

---

바뀐 점: bydd_trd 15 필드 · isu_base_info 12 필드 목록을 옮겼다. 정본에는 단위·코드 함정(`ISU_CD` 6자리/12자리 · `ACC_TRDVAL` · `MKTCAP` 원 단위 · `ISU_SRT_CD` 사용)만 남겼다. 회귀 가드 두 파일 뒤의 설명 괄호를 뺐다.

### market_operation.py — 장운영정보(H0UNMKO0) 정본 + VI 현황 REST 폴백

정본 원문(정본을 떠난 정보가 있는 줄만, 원래 순서):

---

| `VI_STATUS_TR_ID = "FHPST01390000"` · `VI_STATUS_URL = "/uapi/domestic-stock/v1/quotations/inquire-vi-status"` | 부팅 시드용 REST 보조 폴백. 이 path 는 시세 풀 화이트리스트에 **있어야 한다**(빠지면 매 부팅 `QuotePoolPathError` 로 VI 시드가 전건 실패한다) |
🔴 **칸 기준점 — 라이브 프레임은 첫 칸이 종목코드다.** KIS 문서 통합 절(`docs/kis/domestic-stock-realtime.md`)은
종목코드 칸 없이 `[0]=TRHT_YN` 으로 적혀 있다. 라이브 `H0UNMKO0` 프레임은 KRX·NXT 단독 표처럼
`[0]=종목코드` 다(실측 2026-09-21~23). 그래서 파서는
`off = 0 if fields[0] in ("Y","N") else 1` 로 기준점을 정한다. `fields[0]` 이 정확히(`==`, `startswith` 아님)
`"Y"`/`"N"` 이면 문서 모양, 그 밖은 전부 라이브 모양(한 칸씩 밀림)이다.
51·59 보유 종목의 청산·당일 매수 차단은 이 파서를 쓰지 않는다 — `src/engine/status_exit_watch.py` 가
REST `FHKST01010100` 의 전용 플래그(`mang_issu_cls_code`·`short_over_yn`)로 판정하고, 이 채널의 마지막
이벤트는 힌트로 읽기만 한다(상세 = `src/engine/CLAUDE.md` 「종목상태 청산·당일 매수 차단」 절).

---

바뀐 점: 칸 기준점의 실측 기간(2026-09-21~23)을 옮겼다. 판별식·금기·근거 메모 경로는 그대로다. 51·59 판정의 REST 전용 플래그 이름(`mang_issu_cls_code`·`short_over_yn`)은 정본 위치인 `src/engine/CLAUDE.md` 「종목상태 청산·당일 매수 차단」 절로 넘겼다. VI_STATUS 행의 「빠지면 매 부팅 VI 시드 전건 실패」는 Path 가드 절의 일반 금기와 같아 뺐다.

### condition.py — 조건검색 + 영업일 + 종목 기본정보 + TTL 캐시

정본 원문(정본을 떠난 정보가 있는 줄만, 원래 순서):

---

  - `src/engine/trading_calendar.py` 의 조회 seam `_lookup_open`(부팅 즉시 실행 영업일 슬롯 게이트 · 6전략 prepare `expected_head` — None 이면 게이트는 실행 쪽, 어댑터는 달력 판정 쪽으로 떨어진다)
  - KIS 공지 「CTCA0903R 은 가급적 1일 1회」는 그 leaf 의 날짜별 메모(True/False 만 캐시)가 지킨다 — 상세 = `src/engine/CLAUDE.md` `trading_calendar.py` 항목
    - ② **depth**(마지막 윈도우 시작점)에만 휴일 보정을 비례로 얹는다 — `_DAILY_BACKFILL_HOLIDAY_MARGIN_RATIO = 0.10` + `_DAILY_BACKFILL_BASE_MARGIN_CAL = 10`. `total_days=225` → 347 달력일 = 실측 비율(1.479)로 **약 232 영업일**이라 1회 backfill 이 target 을 **넘는다**. 가드 = `tests/unit/engine/test_cycle299_backfill_target_expansion.py::test_g299_9_one_pass_reaches_target`(실도달 ≥ target)
  - **`fetch_daily_candles` 와 별도 함수**다 (그쪽은 memcache 5분 + single-flight + `asyncio.shield` 유지). 호출자 = `scanner._stock_master_daily_load_once` (**일봉 적재 대상 전부** 225일, `_DAILY_LOAD_VCP_BACKFILL_DAYS` — 이름의 `VCP` 는 이 깊이를 처음 요구한 전략의 흔적이고 대상은 index ∪ 자격 ∪ 보호 전체다, cycle302). 매매 hot path 무관 — 데이터 적재 한정. 가드 `tests/unit/api/test_cycle172_daily_ranged_backfill.py`
  - 캐시·single-flight 없음(부팅 1회용) — 두 번 부르면 KIS 도 두 번이다. 형제 `fetch_daily_candles_ranged` 는 반환형·호출자 그대로다.
  - 파생값 `nxt_tradable = (cptt=="Y") AND (nxt_stop=="N")` — 「KRX **에 더해** NXT 에서도 거래되나」 다. NXT 는 대체거래소라 자체 상장이 없으므로 `nxt_tradable=False` 는 「KRX 전용」이고, 그 종목도 KRX 에서 정상 매매된다
  - **raw merge**: `merged_raw = dict(ctpf_output)` 에 `_FHKST_MERGE_KEYS` 33키만 덮어쓴다 — 목록 밖 CTPF 키는 건드리지 않는다(`bfdy_clpr` 보존이 가드 대상). 그중 `_ZERO_VALUE_SKIP_KEYS` 15키(`acml_tr_pbmn`·`acml_vol`·`per`·`pbr`·`vol_tnrt`·`prdy_vrss_vol_rate`·`hts_frgn_ehrt`·`frgn_ntby_qty`·`w52_hgpr`·`w52_lwpr`·`d250_hgpr`·`d250_lwpr`·`eps`·`bps`·`whol_loan_rmnd_rate`)는 값이 **0 이거나 비숫자·None 이면 merge 하지 않고 `continue`** 한다 — 장전 호출의 `0` 이 전일 거래대금을 지우면 `list_by_filter(acml_tr_pbmn ≥ min_trade_amount)` 가 조용히 0건이 되어 donchian/VB/LTV 후보가 사라진다
  - ⚠️ **이 함수는 기존 DB raw 를 읽지 않는다** — 그래서 보존의 주체는 호출자 `scanner._stock_master_basics_refresh_once` 의 `{**기존, **신규}` 머지다. skip 된 키를 기존 DB 값에서 되살리는 곳이 거기 하나뿐이고, `upsert_one` 은 raw 를 통째로 교체한다

---

바뀐 점: `_lookup_open` 이 쓰이는 곳(슬롯 게이트·6전략 prepare `expected_head`)의 상세는 `src/engine/CLAUDE.md` `trading_calendar.py` 항목으로 넘겼다. depth 환산의 실측 비율(1.479)과 `_DAILY_LOAD_VCP_BACKFILL_DAYS` 이름의 경위를 줄였다. 「형제 함수는 그대로다」 변경 서술을 뺐다. `nxt_tradable` 뜻은 루트 `CLAUDE.md` 「핵심 안전 규칙」 NXT 전제 항목을 가리키게 했다. `_ZERO_VALUE_SKIP_KEYS` 15키 전체 목록은 옮기고 정본에는 대표 4키와 「목록 = 그 상수」만 남겼다. raw 보존 설명은 `src/engine/CLAUDE.md` 「basics 갱신」을 가리키게 했다.

### TTL 캐시 (single-flight)

정본 원문(정본을 떠난 정보가 있는 줄만, 원래 순서):

---

- `fetch_daily_candles`: `_CANDLE_CACHE_TTL=300s`(5분), 키 = `(ticker, days)` — days 별 분리. 일봉은 5분 지연 OK
- **종목상태 관측 훅 `_notify_status_observer(ticker, output)` (cycle369)** — `_fetch_stock_detail_and_cache` 가 KIS 응답의 `output` 대입 **직후** · 캐시 lock **앞**에서 한 번 부른다. 훅은 `src.engine.status_exit_watch.observe_fhkst` 를 함수 안에서 지연 import 해 부르고, 관리종목·단기과열 당일 매수 차단 레지스트리에 기록만 한다. 캐시 적중·inflight 합류 경로는 부르지 않는다(첫 조회가 이미 기록했다). leaf 자신의 패스가 부른 조회는 leaf 가 기록을 건너뛴다(패스가 직접 기록한다 — 한 조회 한 기록)

---

바뀐 점: 「일봉은 5분 지연 OK」 판단 근거를 뺐다. 관측 훅의 「한 조회 한 기록」 상세는 `src/engine/CLAUDE.md` 「종목상태 청산·당일 매수 차단」으로 넘겼다. 호출 자리·이중 try 금기(AST J16)는 그대로다.

### period_chart.py — 종목 차트용 기간별시세 (cycle387)

정본 원문(정본을 떠난 정보가 있는 줄만, 원래 순서):

---

  결과는 오래된 것부터(오름차순). 숫자 6칸(`open`·`high`·`low`·`close`·`volume`=`acml_vol`·`amount`=`acml_tr_pbmn`)은 JSON 정수다.

---

바뀐 점: 숫자 6칸이 JSON 정수라는 계약은 `src/models/CLAUDE.md` `CandleBar` 와 같아 그쪽을 가리키게 했다. 폭주 방지 네 겹의 산문 속 숫자(32 · 600초 · 60초 · 20초 · 0.25초)는 바로 위 「상수」 줄과 겹쳐 상수 이름으로 대신했다. 상수 값은 그대로다.

→ CHANGELOG: 해당 없음(문서 정비, 코드 변경 없음)
