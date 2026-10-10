# CLAUDE.md — src/api/ (KIS REST API)

> 이력: [`docs/history/src-api-CLAUDE.history.md`](../../docs/history/src-api-CLAUDE.history.md)

KIS OpenAPI REST 호출 모듈. 모든 호출은 `base.py` 공통 래퍼를 거친다.

## base.py — 공통 래퍼 (메인 단일)

- 메인 진입점 = `kis_get(path, tr_id, params, *, hashkey="", tr_cont=None)` · `kis_post(path, tr_id, body, *, hashkey="")` → `_request(method, path, tr_id, ...)`. `kis_request` 함수는 없다(이름은 문자열·주석(`base.py` `QuotePoolPathError` 메시지 · `krx.py` docstring)과 AST 금지 토큰에만 있다)
- 연속조회(메인) = `kis_get(..., tr_cont=…)` opt-in. 기본 `None` 이면 요청·응답이 연속조회 없는 호출과 같다. 문자열을 넘기면(첫 쪽 `""`, 다음 쪽 `"N"`) 비어 있지 않을 때 요청 헤더에 싣고 응답 헤더 `tr_cont` 를 `data["_response_headers"]["tr_cont"]` 로 돌려준다(시세 풀 `kis_get_quote` 와 같은 키). 소비처 = `trade_profit.py` · `balance.py::get_daily_orders`(cycle430)
- 헤더(`TokenManager.build_headers`) = authorization · appkey · appsecret · `tr_id`(`settings.get_tr_id(tr_id)`, 「새 API 추가 절차」 3번) · custtype("P")
- Rate Limit = `_rate_limit()` 초당 20건(시세 풀 공용) + `asyncio.Semaphore(20)` 동시 20건
- 재시도 = HTTP 오류(4xx·5xx)·네트워크 오류를 `MAX_RETRIES=3` 회까지. 백오프 `BACKOFF_BASE=0.5s × 2^(attempt-1)` + jitter `0~BACKOFF_JITTER=0.25s`
  - 🔴 **주문 경로(`order-cash`·`order-rvsecncl`)는 D2(cycle428, F-422-1) 로 재시도 범위가 좁다** — `ConnectError`·`ConnectTimeout`·`PoolTimeout`(서버에 닿지 않은 것이 보장)만 재시도하고, `ReadTimeout`·`ReadError`·`WriteError`·`RemoteProtocolError`·5xx 는 첫 회에 바로 올린다(`_ORDER_RETRY_RESTRICTED_PATHS` + `_ORDER_RETRYABLE_TRANSPORT_ERRORS`) — 응답만 잃고 앞 전송이 서버에 닿았을 수 있는 실패를 재전송하면 같은 주문을 두 번 낼 수 있다(판정 = `src/engine/CLAUDE.md` 「매도 결과 모름(UNKNOWN)」). 🔴 **그 조회 경로는 무변경** — 5xx·모든 `RequestError` 를 여전히 `MAX_RETRIES=3` 까지 재시도한다. 4xx(영구 클라이언트 에러)는 경로 무관 변경 없음(원래도 `exhausted` 로 세지 않는다)
- 토큰 만료 → `token_manager.issue()` 후 재시도(끝까지 실패 = `[api_retry_exhausted] last_status=token_expired`). 판정(`_request`·`_request_via_quote_pool` 공용) = `msg_cd ∈ _TOKEN_EXPIRED_MSG_CODES = {EGW00121, EGW00122, EGW00123}` 또는 (`"token" in msg1.lower()` ∧ `msg_cd ∉ _TOKEN_BRANCH_EXCLUDE_CODES = {EGW00120, APBK0919, APBK0918}` ∧ `"부족" not in msg1`)
  - 🔴 **`"만료" in msg1` 로 판정 금지** — `EGW00120`("기간이 만료된 code" = 예수금부족 변형, `is_insufficient_cash` 화이트리스트)을 토큰만료로 읽으면 `auth/token.py` `_ISSUE_GAP_SECS=61` 전역 직렬 락이 그리드락을 만들고 같은 주문 body 를 재전송한다(중복 체결)
  - session_key 코드 `EGW00124`~`EGW00126` 은 `issue()` 로 풀리지 않아 뺀다
  - 가드 `tests/unit/api/test_cycle181_token_expiry_whitelist.py` · `tests/unit/ast/test_cycle181_token_whitelist_ast.py`(frozenset 엔트리 + `"만료"` Compare 노드 0건)
- 메트릭 `_request_metrics`(전역 dict) = `total/http_5xx/http_4xx/network_err/kis_error/retries/retry_recovered/retry_exhausted + path별 5xx top 5`. `get_request_metrics()` 스냅샷 · `reset_request_metrics()` 는 `log_analysis_engine.py` 가 **21:30** INSERT 뒤에 부른다(cycle283 D3). **20:05 metrics 1차 스냅샷(`daily_metrics_snapshot.py`)은 리셋하지 않는다**
- **거부 응답 영구 저장** — `rt_cd != "0"` 이면 `KisApiError` raise 직전 ERROR `[kis_rejection] path= tr_id= msg_cd= msg1= body={PDNO/ORD_DVSN/ORD_UNPR/ORD_QTY/EXCG_ID_DVSN_CD/SLL_BUY_DVSN_CD}` 를 `system_logs` 에 fire-and-forget. 민감 키(CANO/ACNT_PRDT_CD) 마스킹 · `write_log` 예외 swallow(`docs/kis/error-codes.md` 4절). 접수 **뒤** 거래소 거부는 체결통보 채널로 온다 — `[order_rejected_notice]`(`src/realtime/CLAUDE.md` 「접수 전문 기록」)
- **최종 결과 기록** — 중간 시도(`retries`)와 최종 결과(`retry_recovered`/`retry_exhausted`)를 따로 센다
  - 실패 = raise 직전 ERROR `[api_retry_exhausted] path= tr_id= attempts=3 last_status={5xx 코드|network|token_expired} last_msg=` 1행(fire-and-forget). 4xx 최종 실패는 남기지 않는다
  - 성공(`attempt > 1` ∧ `rt_cd=0`) = 행 없이 `_record_api_recovered(path)` 누적 → `scheduler._api_recovered_collector_loop` 가 5분마다 `[api_retry_recovered_summary] window=300s total= by_path=` 1행(`_API_RECOVERED_COLLECTOR_WINDOW=300.0`, 빈 윈도우 skip)
- **5xx WARNING 억제** — `(path, status)` 키 60초 dedupe(`_request_5xx_dedupe`, `_REQUEST_5XX_DEDUPE_WINDOW=60.0`). WARNING 은 `_warn_http_status()` 경유만. 시세 풀은 별도(`_quote_5xx_dedupe` · `_record_quote_recovered` · `_flush_quote_recovered_collector`). **ERROR 는 억제 밖** — `[api_retry_exhausted]`·`[kis_rejection]`/`[kis_rejection_quote]` 는 건별로 남는다
  - AST 가드 3(`tests/unit/ast/test_cycle76_ast_api_retry_helper.py`): `_request` 안 `logger.warning("HTTP …")` 직접 호출 0건 · 시세 풀 `_record_5xx_for_dedupe` 호출 존재 · `[api_retry_recovered]` 직접 `write_log` 0건

## base.py — REST 시세성 호출 풀

시세성 KIS REST 호출만 보조 계좌(`kis_quote_accounts`) 라운드로빈으로 나눈다.

**자금 안전 절대 원칙**:
- 매매(`place_order`/`cancel_order`) · 잔고(`get_balance`/`get_buyable`) · 체결조회(`get_daily_orders`) · 체결통보 = 언제나 메인 단일(`kis_get`/`kis_post`)
- 풀에 오는 것 = `condition.py` 함수 전부 · `quotation.py`(`inquire_ccnl` · `inquire_acml_vol`) · `finance.fetch_financial_tr` · `market_operation.inquire_vi_status_today` · `period_chart.fetch_candle_chart` · `scanner._fetch_market_cap_page`. `krx.py` 는 KIS 밖이라 무관

**Public API** — `kis_get_quote(path, tr_id, params, *, hashkey="")`(보조 라운드로빈 + 메인 fallback) · `kis_post_quote(path, tr_id, body, *, hashkey="")` · `get_quote_request_metrics() -> dict` · `reset_quote_request_metrics() -> None`

**Path 가드** (`QuotePoolPathError` — `ValueError` 서브클래스):
- 화이트리스트 **13 path**(`_QUOTE_ALLOWED_PATHS`, 상수는 `/uapi/domestic-stock/v1` 접두 포함)만 허용: `/quotations/inquire-price` / `/quotations/inquire-daily-itemchartprice` / `/ranking/fluctuation` / `/quotations/search-stock-info` / `/quotations/chk-holiday` / `/quotations/inquire-ccnl` / `/ranking/market-cap` / `/quotations/inquire-vi-status` / `/finance/income-statement` / `/finance/balance-sheet` / `/finance/profit-ratio` / `/finance/stability-ratio` / `/finance/other-major-ratios`
- 🔴 **신규 시세 path 는 화이트리스트 등재 + AST 가드 동반이 의무**다 — 빠뜨리면 그 호출이 `QuotePoolPathError` 로 전건 실패한다
- `/quotations/volume-rank`(거래량순위 FHPST01710000) **재도입 금지** — 호출 0건 dead 로 폐기. 가드 `tests/unit/api/test_cycle179_no_volume_rank_in_quote_allowlist.py`
- 매매성 path 오염 검사는 **세그먼트 판정** — 키워드 부분일치는 `finance/balance-sheet` 를 `inquire-balance` 로 오탐한다. 가드 `tests/unit/api/test_cycle109_market_cap_allowlist.py` · `tests/unit/api/test_cycleC1_finance_allowlist.py` · `tests/unit/api/test_vi_status_quote_allowlist.py`
- 매매/잔고/체결조회 path(`/trading/order-cash` / `/trading/order-rvsecncl` / `/trading/inquire-balance` / `/trading/inquire-psbl-order` / `/trading/inquire-daily-ccld`)는 즉시 raise

**라운드로빈** — `_select_quote_label()` 이 `kis_quote_accounts.list_accounts(active_only=True)` 라벨을 `_quote_request_index`(`asyncio.Lock`)로 돌린다. 보조 0개 · 전부 active=false · DB 조회 실패 · 보조 토큰 매니저 발급 실패(`ValueError` 등) → 메인 fallback

**Per-label 격리 Rate Limit** — `_quote_semaphores: dict[label, Semaphore(18)]`(메인 20 보다 보수적), `_get_quote_semaphore(label)` lazy 생성

**메트릭 격리** — `_quote_request_metrics`(`total/http_5xx/4xx/network_err/kis_error/retries/recovered/exhausted/by_label`)는 메인 `_request_metrics` 와 분리되고 reset 도 따로다. `by_label: defaultdict(int)` 가 `main`(fallback) / `quote-1` / `quote-2` … 별로 센다

**거부 응답 로깅 분리** — 시세 풀 거부는 `[kis_rejection_quote]`. body 마스킹·주요 키 추출은 없다(시세 호출엔 민감 식별자가 없다)

**Health monitor 통합** (`src.services.quote_session_health.health_monitor`):
- 기록 = `record_success(label)`(`rt_cd=="0"` ∧ `actual_label != "main"`) · `record_failure(label, reason=f"http_{status}")`(5xx HTTPStatusError) · `record_failure(label, reason="token_issue_fail")`(보조 매니저 발급 실패). rt_cd!=0 비즈니스 거부·네트워크 에러는 기록 안 함
- **자동 비활성 임계 3종**: consecutive 5 / 5분 50% / 1분 80%(`FAST_WINDOW_SECS=60`, `FAST_MIN_CALLS=10`, `FAST_MAX_FAILURE_RATE=0.8`) → `kis_quote_accounts.update_account(active=False)` + `kis_ws_pool.disable_quote_session(label)` + `[quote_session_disabled]` 영구 1행. DB 실패면 메모리만 비활성 + WARNING
- 메인 라벨 "main" 자동 비활성 절대 금지(안전 가드)
- 운영: 5xx 가 잦은 보조 라벨은 임계 전에 Settings UI `active=false` 로 수동 비활성 권장. 되살리기 = 카드 `active=true` → **다음 영업일** `_boot()` 부터

**5xx 폭주 억제**:
- WARNING dedupe `_record_5xx_for_dedupe(path, label, status) -> bool` — 같은 키가 60초(`_QUOTE_5XX_DEDUPE_WINDOW=60.0`) 안에 다시 나면 첫 1회만 WARNING, 나머지는 카운트만(lock `_quote_5xx_dedupe_lock`)
- `_emit_5xx_dedupe_summary()` — scheduler `_5xx_dedupe_summary_loop` 가 60초마다 부른다. 만료 키는 카운트와 무관하게 전부 state 에서 지우고, 그중 카운트 ≥ 2 인 키만 INFO `[quote_pool_5xx_summary] path= label= status=500 count=N within=60s` 1행
- **메인 fallback 우선** — 라벨 선택 직후 `health_monitor.get_recent_5xx_ratio(label)` 가 `total>=FAST_MIN_CALLS(10)` ∧ `ratio>=_LABEL_FALLBACK_5XX_RATIO_THRESHOLD(0.8)` 면 `label=None`(3회 재시도 backoff 회피). `_quote_request_metrics["fast_fallback"]` +1(스냅샷·reset 포함)

## order.py — 주문

- 현금 매수 TTTC0012U · 매도 TTTC0011U · 정정·취소 TTTC0013U
- **자금 안전**: `kis_post`(메인 단일)만 쓴다. `kis_post_quote`/`kis_get_quote` import 금지 — 가드 `test_condition_quote_routing.py::test_order_module_never_imports_quote_pool`
- `place_order(..., exchange="KRX")` / `cancel_order(..., exchange="KRX")` → body `EXCG_ID_DVSN_CD` = `KRX`(기본·미지정) / `NXT` / `SOR`. 모의(VTS)는 KRX 만
- **지정가 경로** = body `ORD_DVSN=order_division.value` · `ORD_UNPR=str(price)`. `execute_buy` 의 "시장가매매불가" 폴백도 같은 경로다(`side=BUY, price=fallback_price>0, order_division=LIMIT`)
- **`OrderDivision`(cycle287) — 시각이 정한다.** `place_order` 는 값을 **검증 없이 그대로** `ORD_DVSN` 에 싣는다(화이트리스트 절대 금지 — 끼우면 `44` 가 조용히 사라진다):

  | 구간 | `ORD_DVSN` | 의미 | `ORD_UNPR` |
  |---|---|---|---|
  | 정규장·프리장 | `"01"` | 시장가(기본) | `"0"` |
  | 정규장·프리장 폴백 | `"00"` | 지정가 | 매수 `step_up(5)` / 매도 `step_down(5)` |
  | **NXT 프리마켓**(08:00~08:50) 매수 승격(cycle291) | `"27"` | GTP지정가 | `step_up(현재가,5)` — `"00"` 폴백과 **같은 값** |
  | **KRX 애프터**(16:00~20:00) 1차 | `"44"` | 최유리지정가 | `"0"` — 정본 명시 없음(근거 = `src/engine/CLAUDE.md` 「order_engine.py」 절 규칙 2) |
  | KRX 애프터 폴백 | `"41"` | 지정가 | `step_down(현재가,5)` |

  이 다섯(`00`·`01`·`27`·`41`·`44`)만 둔다 — 애프터 IOC/FOK(42/43/45/46)는 잔량 자동취소로 손절 잔여를 잃는다. 47·`29` 는 자기 방향 최우선호가라 크로스하지 않고, `28` 은 `ORD_UNPR` 규약이 현금·신용 문서 사이에서 갈린다. **애프터마켓엔 시장가(01)가 없고 ETP(ETF/ETN) 거래가 불가**(KIS 공지 verbatim). `EXCG_ID_DVSN_CD` 는 별개로 라우팅된다 — 시각·거래소 결정(`_route_exchange_by_clock`/`_apply_clock`)과 애프터 청산 호가의 정본 = 같은 절 규칙 1·2.

  **`27`(GTP지정가)은 NXT 프리마켓 매수 전용이다**(미체결은 거래소가 08:50 에 일괄취소, **매도는 `00` 그대로**). 게이트 4중(실패·예외면 `00` — fail-safe)·`27` 거부 시 같은 가격 `00` 1회 폴백의 정본 = 같은 절 규칙 4.

  **취소(`cancel_order`)의 `ORD_DVSN`** — `cancel_order(..., order_division: str | None = None)`, falsy 면 `"00"`. `order_engine` 취소 3경로(`_cancel_after_wait`/`_cancel_and_reorder`/`cancel_remaining`)는 이 인자를 **넘기지 않는다**(`41`/`44`/`27` 원주문 취소는 실적 0건이라 미검증, docstring 명시). 🔴 **원주문 호가유형 승계 전송은 매매 행위 변경이라 별도 승인 대상**이다 — 켜면 정규장 부분체결 취소가 `"00"`→`"01"` 로 바뀐다. 관측 `[after_cancel_result]`·선결 실측 = 같은 절 규칙 4 「취소 축 Stage A」.

## balance.py — 잔고/조회

- 잔고조회 TTTC8434R · 매수가능조회 TTTC8908R
- **자금 안전**: `kis_get`(메인 단일)만 쓴다. 시세 풀 함수 import 금지 — 가드 `test_balance_module_never_imports_quote_pool`
- `get_balance(afhr_flpr="N")` → `AFHR_FLPR_YN`(required) = `N` KRX 정규장 종가 / `X` NXT / `Y` KRX+NXT 통합시세(`docs/kis/README.md` 「제도 변경 공지 반영」). 호출자는 전부 `N`
- 🔴 **`get_balance()` 의 `prpr`(현재가)은 KRX 애프터마켓 체결을 반영하지 않는다** — 애프터마켓 가격으로 판단하는 코드는 `get_balance` 가 아니라 시세 조회를 쓴다(영향받는 현재 `get_balance` 소비처 = 대시보드 표시 · `account_risk_watcher` 의 `summary.net_asset`). `evlu_amt`·`nass_amt`(`summary.net_asset` 원천)도 얼었는지는 **재지 않았다**(**[추론]**) — 애프터 구간에 `evlu_amt` ↔ `prpr × hldg_qty` 를 대조해 어긋나면 별도 갱신 경로가 있다
- `get_daily_orders(target_date="", exchange="ALL", *, odno="", pdno="")`: TTTC0081R. `EXCG_ID_DVSN_CD`(required) = `ALL`(기본, KRX+NXT+SOR — NXT 체결 누락 방지) / `KRX` / `NXT` / `SOR`. keyword-only 필터 `odno`(`ODNO` — 그 주문 1건 행만, cycle373) · `pdno`(`PDNO` 종목), 둘 다 `""` 면 전체 조회와 같다. 소비처 = `engine/buying_reconcile.py`(`odno` — 전체 목록 잘림에 기대지 않는다) · `execute_sell` #1.5 재대조(`exchange="ALL", pdno=ticker` — 서버가 `PDNO` 를 무시해도 `_sell_fills_by_order` 가 다시 거른다, `src/engine/CLAUDE.md` 「매도 체결 — 주문 축과 보유 축」)
  - **연속조회(cycle430)** — 위 「연속조회(메인)」 의 `kis_get(..., tr_cont=…)` 로 쪽수 상한 없이 전 쪽을 이어 붙인다. 응답 헤더 `tr_cont` 가 `M`/`F`(실전 한 쪽 최대 100건 · 모의 15건, KIS 공지)인 동안 다음 요청에 `tr_cont="N"` + 직전 쪽의 `ctx_area_fk100`/`ctx_area_nk100` 을 그대로 되돌리고, `D`/`E`(또는 그 밖의 값)면 멈춘다. `rt_cd != "0"` 은 어느 쪽에서든 `KisApiError` 로 그대로 올라와 부분 결과를 주지 않는다. `tr_cont` 가 `M`/`F` 인데 `ctx_area_fk100`·`ctx_area_nk100` 이 둘 다 비었거나 직전 요청과 같으면(연속조회가 진행하지 않음) `DailyOrdersPaginationStuckError` + WARNING `[daily_orders_pagination_stuck] pages= rows=` 로 중단한다(잘린 목록을 돌려주지 않는다 — 소비처 6곳이 `except Exception` 으로 받아 "조회 실패 = 유지" 로 간다). 같은 행이 두 쪽에 겹쳐 와도 추측으로 dedupe 하지 않는다. 🔴 `order_engine._sell_orders_snapshot` 의 `page_full` 판정(`len(rows) >= 환경별 page_size`)은 이 변경 **전**의 전제(단일 쪽만 읽는다)로 쓰여 있다 — 지금은 한 종목 주문이 그 건수 이상이면 **실제로는 잘리지 않았는데도** `page_full` 로 오판한다(안전 방향 = 조회를 믿지 않는 쪽으로 치우친 거짓 양성, cycle430 후속 미정리)

### KIS 거부 응답 분류 헬퍼

- `is_market_closed_rejection(KisApiError) -> bool` — 장운영시간 외 / 매매 불가 시간 / 거래시간 외. `msg_cd=APBK0918` 공용이라 msg1 키워드(`_MARKET_CLOSED_KEYWORDS`)로 가른다. True 면 `is_insufficient_*` 는 False(positions 보존 결정)
- `is_insufficient_cash(KisApiError) -> bool` — 예수금 부족 매수 실패. msg_cd 화이트리스트(APBK0919/EGW00120) ∧ msg1 "부족" + "주문가능금액/예수금/현금". `APBK0918` 은 현금 키워드 동반 시만 True. 매수 락 결정용
- `is_insufficient_quantity(KisApiError) -> bool` — 보유 부족 매도 실패. msg_cd 화이트리스트 `APBK1234` ∧ msg1 "부족" + "매도가능/보유수량/잔고". `APBK0918` 은 보유 키워드 동반 시만 True. 매도 즉시 break 결정용
- **`is_sell_qty_exceeded(KisApiError) -> bool` (cycle236)** — 매도 수량 초과 = `msg_cd=APBK0400` ∧ msg1 "수량"·"초과"(정본 오류코드 사전에 없는 코드라 문구까지 맞춘다). 요청 > 매도 가능 = **부분 보유가 내재된 코드**라 `is_insufficient_quantity`(positions 통째 삭제 경로)에 **흡수 금지**가 계약. 소비 = `execute_sell` **#1.5** 잔고 재대조(`src/engine/CLAUDE.md` 「order_engine.py」 절). 검사 순서 = **closed → sell_qty_exceeded → insufficient → disallowed**(closed 우선 계약 불변)
- `is_market_order_disallowed(KisApiError) -> bool` — 시장가 거부. msg1 키워드 `_MARKET_ORDER_DISALLOWED_KEYWORDS` = `시장가매매불가` / `시장가 매매 불가` / `시장가 주문 불가` / `시장가 호가 불가` / `시장가호가불가` / `최유리/최우선지정가 주문만` / `지정가 및 최유리` / `단일가매매`. `is_insufficient_*` 2종과 상호 배타. msg_cd = APBK1943 · APBK3013(NXT 애프터 매도 · 단일가 세션 변형 — closed 미매칭이라 지정가 폴백 정상 경로). `docs/kis/error-codes.md` 4-2절 / 5-4절
  - ⚠️ **`is_market_closed_rejection` 과 이중 매칭** — APBK0918 "장운영시간이 아닙니다.([프리마켓] 시장가 매매 불가 시간)" 은 양쪽에 걸린다. `execute_sell` 이 closed 를 **먼저** 보므로 보류(포지션 보존 + 다음 09:00 TTL)가 된다 — 프리장 왜곡 시세라 지정가 즉시 매도보다 보류가 안전하다는 **의도된 계약**이다. 순서 반전은 `test_rejection_classifier_pre_market_priority.py` 가 막는다
- `order_engine._sell_not_placed_reason`(cycle385)도 세 판정을 sell_qty_exceeded → closed → disallowed 순으로 써 「안 걸렸다」를 가려 `_selling` 을 푼다(프리마켓 이중 매칭은 `market_closed`). 상세 = `src/engine/CLAUDE.md` 「매도 체결 — 주문 축과 보유 축」

## trade_profit.py — 기간별매매손익현황 TTTC8715R (트랙 C 실비용)

- `fetch_period_trade_profit(start_yyyymmdd, end_yyyymmdd, *, pdno="") -> PeriodTradeProfit(rows, summary, pages, truncated)` — HTS [0856] 「종목별」 화면과 같은 일자·종목별 `buy_amt`·`sll_amt`·`rlzt_pfls`·`fee`·`tl_tax`(output1) + 기간 합계(output2, 1원소 배열이면 dict 로 편다). 정본 = `docs/kis/domestic-stock-order.md` 「기간별매매손익현황조회」
- **실전 전용** — 모의(vts)에서는 KIS 를 부르지 않고 `RealEnvRequired`. 계좌 TR 이라 메인 `kis_get` 만 쓴다(시세 풀은 다른 계좌)
- 연속조회 = 응답 헤더 `tr_cont` 가 `M`/`F` 면 다음 쪽(헤더 `tr_cont="N"` + 본문 `ctx_area_fk100`/`ctx_area_nk100` 되돌림). `_MAX_PAGES=50` 에서 멈추면 `truncated=True`. 어느 쪽이든 `rt_cd != "0"` 은 `KisApiError` 로 올라와 부분 결과를 돌려주지 않는다
- 소비처 = `engine/trade_cost.reconcile`. 8영역 `order.py` 와 분리한 비주문 조회 모듈이다. 가드 `tests/unit/api/test_trackc_period_trade_profit.py`

## corporate_actions.py — 예탁원정보 + 계좌 기간별 권리현황 (cycle431)

액면병합·분할 등 "주문 밖 수량 변경" 대사(`src/engine/corporate_action_reconcile.py` ·
`boot_manager._reconcile_corporate_actions`)의 근거 조회. 판정(비율 계산·분류)은
이 모듈에 없다 — KIS REST 호출만.

- `fetch_face_value_change(ticker, *, today=None)` — 예탁원정보(액면교체일정,
  **HHKDB669105C0**) `/uapi/domestic-stock/v1/ksdinfo/rev-split`. 응답
  `inter_bf_face_amt`/`inter_af_face_amt`(0 패딩 문자열)가 액면가 변경 전·후 —
  r(수량 배율) = 옛/새(판정은 `corporate_action_reconcile.ratio_from_face_value`).
- `fetch_capital_decrease(ticker, *, today=None)` — 예탁원정보(자본감소일정,
  **HHKDB669106C0**) `/uapi/domestic-stock/v1/ksdinfo/cap-dcrs`. `reduce_cap_rate`×
  `comp_way=="곱하기"` 일 때만 r = `reduce_cap_rate`.
- `fetch_merger_split(ticker, *, today=None)` — 예탁원정보(합병_분할일정,
  **HHKDB669104C0**) `/uapi/domestic-stock/v1/ksdinfo/merger-split`. **감지만** —
  회사분할·합병은 새 종목이 생겨 자동 반영 범위 밖(사용자 결정).
- 셋 다 모의투자 미지원 TR 이지만 호출 자체는 `settings.get_tr_id()` 경유(변환
  실효 없음). 쿼리 창 = `[today − DEPOSITORY_LOOKBACK_DAYS(30일), today]`(`SHT_CD`
  지정 조회). 🔴 **연속조회는 CTS 가 아니라 `tr_cont` 로 한다** — 각 TR 문서 표의
  "tr_cont 를 이용한 다음조회 불가" 는 **요청 바디 `CTS` 축** 얘기다. 사용자 결정
  (2026-10-10, KIS 공식 예제)은 응답 헤더 `tr_cont` 가 `M`/`F` 면 다음 요청을
  `tr_cont="N"` + `CTS` 는 항상 빈칸으로 보낸다. 쪽수 상한 없음 — `M`/`F` 인데 새
  행이 0개(진행 없음)면 `CorporateActionPaginationStuckError`(`get_daily_orders`
  와 같은 규약).
- `fetch_period_rights(ticker="", *, start_date, end_date, right_type_cd="")` —
  기간별계좌권리현황조회(**CTRGA011R**) `/uapi/domestic-stock/v1/trading/period-rights`.
  **실전 전용**(모의 → 빈 목록, KIS 호출 0건). 🔴 **응답 목록 키는 실제 `output`**
  이다(스펙 표의 `output1` 과 다르다 — 2026-10-10 운영 탐침 실측). 연속조회는
  `balance.get_daily_orders` 와 같은 모양(`CTX_AREA_FK100`/`CTX_AREA_NK100`
  되돌림, `tr_cont` M/F). `rght_type_cd` 2자리(14 액면분할·15 액면병합·17 감자·
  11 합병·12 회사분할 등) — 21:30 사후 대사 전용(`emit_settlement_detection`,
  행 부재는 그 자체로 오류가 아니다 — 아침 반영을 막지 않는다).
- 소비처 = `boot_manager._reconcile_corporate_actions`(예탁원 3종) ·
  `corporate_action_reconcile.emit_settlement_detection`(CTRGA011R). 가드 =
  `tests/unit/api/test_cycle431_corporate_actions_api.py`.

## kis_master.py — KIS 공식 일일 마스터 파일

KIS 공식 일일 마스터 파일 cp949 fixed-width 파싱 → `list[dict]` → upsert. 매일 **16:30** KST 자동 갱신(fire-and-forget). `struct.unpack` 순수 파싱 + `httpx.AsyncClient` 메모리 처리(`io.BytesIO`, 디스크 I/O 0, pandas 없음). field_specs·필드 순서는 KIS 공식 샘플과 같다.

### URL 정본

- KOSPI: `https://new.real.download.dws.co.kr/common/master/kospi_code.mst.zip` (후미 `KOSPI_TAIL_BYTES=227`)
- KOSDAQ: `https://new.real.download.dws.co.kr/common/master/kosdaq_code.mst.zip` (후미 `KOSDAQ_TAIL_BYTES=221`)
- 후미 byte 정본은 227/221 이다 — 샘플의 228/222 는 텍스트 모드 줄바꿈 여유분
- part1 = 단축코드 9 byte(`SHORT_CODE_LEN`) + 표준코드 12 byte(`STND_CODE_LEN`) + 한글명 가변

### 함수 영역 (실제 시그니처)

- `async def download_kospi_master() -> list[dict]` — ZIP 다운로드 + 파싱(인자 없음). 키 = part1 3종(`mksc_shrn_iscd` 6자리 단축코드 / `stnd_iscd` / `hts_kor_isnm`) + part2 70(`KOSPI_FIELD_NAMES`)
- `async def download_kosdaq_master() -> list[dict]` — 동일, part2 64(`KOSDAQ_FIELD_NAMES` — 전용 `vntr_issu_yn` 벤처기업 / `invt_alrm_yn` 투자주의환기 / `ksq150_nmix_yn` KOSDAQ150)
- `async def download_master_zip(url: str) -> bytes`(SSL 옵션 C) · `def decode_korean(raw_bytes: bytes) -> str`(cp949, `UnicodeDecodeError` → `errors="replace"`)
- `def _parse_master_records(raw_bytes, tail_bytes, field_specs, field_names) -> list[dict]` — 공통 파서. `struct.unpack` + `assert struct_size == tail_bytes`
- **통합 함수 없음** — 통합·source 태깅은 호출자 `scanner._stock_master_master_load_once()` 가 `tagged_records: list[tuple[str, dict]]` 로 한다

### SSL 옵션 C

- `httpx.AsyncClient(verify=True)` 우선. `httpx.ConnectError` + SSL/certificate 키워드일 때만 `verify=False` 재시도 + WARNING(그 외 에러는 전파)
- `ssl._create_unverified_context`(무조건 검증 off)는 쓰지 않는다

### 매매 활용 키 ~30

- 진입 차단 7건(HIGH): `trht_yn` 거래정지 / `mang_issu_yn` 관리종목 / `ssts_hot_yn` 공매도과열 / `stange_runup_yn` 이상급등 / `sltr_yn` 정리매매 / `mrkt_alrm_cls_code` 시장경고(`>= "02"` 만 차단) / `invt_alrm_yn` 투자주의환기(코스닥 전용). 소비 = `scanner._is_master_blocked_for_entry` 의 master_raw 쪽. 같은 함수가 FHKST01010100 raw 4건(`mrkt_warn_cls_code >= "02"` · `short_over_yn` · `sltr_yn` · `temp_stop_yn`)도 보고 둘 중 하나라도 맞으면 막는다(OR — raw 는 master_raw 의 폴백이 아니다). 정본 `src/engine/CLAUDE.md` 「매수 진입 차단」
- 그 밖의 활용 키(시총 `prdy_avls_scal` · 재무 · 지수편입 · 시장 · 기타)와 한글 이름 = `frontend/src/pages/StockMaster.tsx::FIELD_LABELS`
- 🔴 관리종목·단기과열 **보유 청산·당일 매수 차단**은 이 마스터 키(`mang_issu_yn`·`ssts_hot_yn`·`short_over_cls_code`)를 쓰지 않는다 — 하루 늦고, `ssts_hot_yn` 은 공매도과열, `short_over_cls_code` `1` 은 예고다. 판정 = REST 전용 플래그(`src/engine/CLAUDE.md` 「종목상태 청산·당일 매수 차단」)

### 단위 환산

- `prdy_avls_scal`(마스터) = **억 원**(구조체 `.h` "전일기준 시가총액 (억)")
- `hts_avls`(FHKST01010100 `inquire_price` "HTS 시가총액") = **억 원**(cycle166). 원 환산 `× 100_000_000`
- 시총 필터는 전부 억원 기준 — `list_by_filter`(python `hts_avls × 100_000_000`) · `list_paged_by_filter`(생성 컬럼 `hts_avls_eok`, migration 039) · scanner KRX 폴백(`// 100_000_000`) · 프론트 `formatMarketCap`
- 🔴 **`hts_avls` 를 백만원으로 읽지 않는다** — 100배 어긋나 `min_market_cap=1,000억` 후보 풀이 1,734 → 80 으로 잘린다
- 시총 헬퍼 3개(`market_cap_master_to_millions` / `validate_market_cap_consistency` / `get_market_cap_millions`)는 **없다** — 호출처 0건으로 폐기, 재도입은 `tests/unit/ast/test_cycle167_ast_no_dead_market_cap_funcs.py` 가 막는다
- 회귀 가드: `tests/unit/db/test_cycle166_hts_avls_unit_correction.py` · `tests/unit/engine/scanner/test_cycle166_krx_fallback_eok_unit.py`(AST 단위 가드 = `1_000_000` 잔존 0건)

### 호출자

- `src/engine/scanner.py::_stock_master_master_load_once()` — 다운로드 + 파싱 + `stock_master.upsert_master_raw()` 배치 + emit
- 부르는 곳 = `src/engine/scheduler.py::_stock_master_master_load_task_loop()`(본체 `data_load_tasks.stock_master_master_load_task_loop`) · `src/routes/stock_master.py::refresh_master_now()`(POST `/api/stock-master/master/refresh` 수동, BackgroundTasks)

## finance.py — KIS 재무 5 TR fetch

5 TR 을 `kis_get_quote` 로 불러 `stock_master_financial` 로 정규화한다. 6자리 숫자 ticker 가드(`ValueError`).

### 5 TR 정본 (path, TR_ID)

| kind | path | TR_ID | 산출 컬럼 |
|---|---|---|---|
| income | `/finance/income-statement` | FHKST66430200 | 손익 5 |
| balance | `/finance/balance-sheet` | FHKST66430100 | 대차 7 |
| profit | `/finance/profit-ratio` | FHKST66430400 | 수익성 2 |
| stability | `/finance/stability-ratio` | FHKST66430600 | 안정성 2 |
| other | `/finance/other-major-ratios` | FHKST66430500 | 기타 2(`ebitda`/`ev_ebitda`) |

컬럼 이름·용도 = `src/db/CLAUDE.md` 「stock_master_financial.py」 절(정규화 NUMERIC 18종).

- `fetch_financial_tr(ticker, tr_key, div_cls="0") -> list[dict]`(단일 TR, output = 다기간 list, `div_cls` 0=년/1=분기) · `fetch_all_financials(ticker, div_cls="0") -> list[dict]`(5 TR 후 `stac_yymm` join 병합)
- 호출자 = `src/engine/scanner.py::_stock_master_financial_load_once()` 하나(주1회 16:40). 매매 hot path 무관

## krx.py — KRX 정식 OPEN API 클라이언트

KRX Data Marketplace(openapi.krx.co.kr) 정식 OPEN API — KIS 와 별개 시스템이다.

### 호출 규약

- **GET** · 인증 query parameter `AUTH_KEY=` · 파라미터 query string `params=`. 진입점 `fetch_krx_open_api(endpoint_path, params)` 하나, 예외 `KrxApiError`, 키 = DB 동적 로드 `get_krx_open_api_config()`(`src/db/system_config.py`)
- 응답 `{"OutBlock_1": [{...}, ...]}`(누락 시 빈 리스트)

### 함수 4종

| 함수 | endpoint | 응답 필드 수 | 용도 |
|---|---|---|---|
| `fetch_stk_bydd_trd(date)` | `/sto/stk_bydd_trd` | 15 | KOSPI 일별 매매정보(KIS market-cap 대안) |
| `fetch_ksq_bydd_trd(date)` | `/sto/ksq_bydd_trd` | 15 | KOSDAQ 일별 매매정보 |
| `fetch_stk_isu_base_info(date)` | `/sto/stk_isu_base_info` | 12 | KOSPI 종목 기본정보(CTPF1002R 대안) |
| `fetch_ksq_isu_base_info(date)` | `/sto/ksq_isu_base_info` | 12 | KOSDAQ 종목 기본정보 |

- 단위·코드 함정 — bydd_trd 의 `ISU_CD` 는 단축코드 6자리(KRX 종목코드 정합) · **`ACC_TRDVAL`** 은 원 단위(`min_trade_amount` 직접 정합) · **`MKTCAP`** 은 원 단위(KIS `hts_avls`(억원) 환산 `// 100_000_000`). isu_base_info 의 `ISU_CD` 는 12자리 표준코드라 **사용 금지**(stock_master PK 비정합)이고 **`ISU_SRT_CD`**(단축코드 6자리)를 쓴다

### 폴백 (`scanner._full_universe_load_once` → `_full_universe_load_krx_primary`)

- KRX 1차 — `_full_universe_load_krx_primary` 가 4 endpoint 를 50ms 간격으로 부른다(KIS LMS chain). `KrxApiError`(비활성 · 키 부재 · 401 · 4xx/5xx · timeout · 네트워크 · JSON 오류)는 전파되고, 매매정보 2건이 7일 연속(basDd 7개) 비어도 `KrxApiError` 다 → `_full_universe_load_once` 가 KIS market-cap 으로 자동 폴백, 양쪽 모두 실패면 raise
- 🔴 `system_config.krx_open_api_enabled` 를 끄는 것은 「제거」가 아니라 KIS 폴백으로의 **경로 변경**이다 — 폴백이 유니버스를 크게 줄인다. 끄기 전후 검증 = 루트 `CLAUDE.md` 「핵심 안전 규칙」 비활성화 심층 검증 의무

### 시장 등락 통계 (`routes/market_breadth.py`, cycle416)

- 매매정보 2건(`fetch_stk_bydd_trd`·`fetch_ksq_bydd_trd`)을 매크로 화면의 「시장 등락 통계」 가 날짜마다 부른다. 관찰 전용이고 유니버스 적재와 무관하다. 캐시·동시성·재시도·하루 상한 = `src/routes/CLAUDE.md` 엔드포인트 목록의 `/api/market/breadth` 행
- 🔴 이 클라이언트는 그 라우트를 위해 고치지 않는다 — `tests/unit/ast/test_cycle416_ast_market_breadth.py::test_g416_6_krx_client_unchanged` 가 최상위 정의 이름 집합과 각 정의 본문 sha256 을 핀한다

### 보안

- 평문 key 는 query parameter 에만 — **URL 전체 로그 금지**(endpoint_path 만 로그). `KrxApiError` 메시지에도 평문 key 노출 0건

**Rate Limit**: 키당 일일 10,000 호출. 적재는 보통 하루 4회. 시장 등락 통계는 KST 하루 1,000회 상한을 따로 건다(재시도 포함 · 프로세스 메모리 카운터라 재시작하면 0 부터). 매매정보 2건은 basDd 를 전일부터 하루씩 거슬러 최대 7번(첫 시도 포함) 부른다 — 둘 다 비었을 때만 하루 전으로 넘어가고, 하나라도 오면 멈춘다.

**회귀 가드**: `tests/unit/api/test_cycle112_krx_client.py` · `tests/unit/api/test_cycle115_krx_endpoints.py` · `tests/unit/engine/scanner/test_cycle115_full_universe_load_krx_fallback.py` · `tests/unit/ast/test_cycle115_krx_endpoint_urls.py` · `tests/unit/ast/test_cycle115_krx_no_plaintext_key.py`

## market_operation.py — 장운영정보(H0UNMKO0) 정본 + VI 현황 REST 폴백

WebSocket 장운영정보의 **파싱 정본**이다. 구독 송신 = `src/engine/market_op_subscribe.py`, 상태 축적 = `src/engine/market_operation_monitor.py`.

| 심볼 | 내용 |
|---|---|
| `MARKET_OP_TR_ID = "H0UNMKO0"` | 통합 장운영정보 TR_ID |
| `VI_STATUS_TR_ID = "FHPST01390000"` · `VI_STATUS_URL = "/uapi/domestic-stock/v1/quotations/inquire-vi-status"` | 부팅 시드용 REST 보조 폴백 |
| `@dataclass MarketOpEvent` | 논리 10칸(KIS 문서 통합 표 `[0]=TRHT_YN` … `[9]=EXCH_CLS_CODE`) + `tr_key` 의 `ticker` |
| `parse_market_op_payload(tr_key, payload) -> MarketOpEvent` | `^` 구분 페이로드 → 이벤트. 읽을 칸은 「칸 기준점」이 정한다. 없는 칸은 `""` |
| `ISCD_STAT_BLOCKING = frozenset({"58"})` · `is_iscd_stat_blocking(code) -> bool` | 종목상태구분코드(`ISCD_STAT_CLS_CODE`) 거래정지 판정 — `58`(거래정지 지정) **하나만** True |
| `is_event_blocking(event) -> bool` | stale 회피 판정 = `TRHT_YN=="Y"` · VI 활성 · 종목상태 `58` 중 하나(MRKT_TRTM 제외). 프로덕션 호출자 0(운영은 `market_operation_monitor.record_market_op_event` 가 같은 규칙을 인라인 판정) |
| `inquire_vi_status_today() -> set[str]` | 부팅 REST 1회 시드. 실패해도 매매 안전성 영향 0 |

🔴 **칸 기준점 — 라이브 프레임은 첫 칸이 종목코드다.** KIS 문서 통합 절(`docs/kis/domestic-stock-realtime.md`)은 `[0]=TRHT_YN` 이지만 라이브 `H0UNMKO0` 은 KRX·NXT 단독 표처럼 `[0]=종목코드` 다. 파서 = `off = 0 if fields[0] in ("Y","N") else 1` — `fields[0]` 이 정확히(`==`, `startswith` 아님) `"Y"`/`"N"` 이면 문서 모양, 그 밖은 라이브 모양(한 칸씩 밀림).
- `tr_key == fields[0]` 으로 판별하지 않는다 — `KisWebSocket._handle_raw` 가 `tr_key` 를 `payload.split("^")[0]` 로 뽑아 운영에서 항상 참이다.
- 칸 계산은 이 파서 **한 곳뿐**이다. `src/realtime/handler.py::_handle_market_op` 는 `payload.split` 을 하지 않고 파싱된 `event.mkop_cls_code` 를 로그·보드 콜백에 넘긴다.
- 근거 메모 = `_workspace/domain_consult/cycle359_mkop_field_offset.md`.

🔴 **거래정지는 `TRHT_YN=="Y"` 또는 종목상태 `58` 뿐이다(2026-09-25 사용자 결정).** 51(관리)·52~54(시장경고)·55(신용가능)·57(증거금100%)·59(단기과열)·00 은 정지가 아니다 — 넓게 읽으면 55·57 같은 정상 상태까지 정지로 잡혀 보유 종목이 재구독 안전망에서 빠진다. 51·59 보유 청산·당일 매수 차단은 이 파서를 쓰지 않는다(이 채널 이벤트는 힌트일 뿐 — `src/engine/CLAUDE.md` 「종목상태 청산·당일 매수 차단」 절).

🔴 **VI 칸(`VI_CLS_CODE`·`OVTM_VI_CLS_CODE`)은 블랙리스트 방식이다** — `None` 과 `_INACTIVE_VALUES = {"", "0", "N", "n", "(null)"}` 만 비활성, 그 밖은 전부 활성(KIS 가 코드를 늘려도 새 값이 활성으로 읽힌다). `"(null)"` 은 라이브 프레임이 빈 칸 대신 보내는 KIS null 토큰이다. 정지 사유 칸(`TR_SUSP_REAS_CNTT`)은 값이 **정확히** `"(null)"`(`_NULL_TOKEN`)일 때만 `""` 로 바꾼다 — 부분 치환은 실제 사유 문장 속 `(null)` 까지 깎는다.

매매 안전성 무영향 영역 — 바꾸는 것은 stale 판정의 *지연*뿐이고 `risk.on_tick`·`order_engine`·`auth` 는 건드리지 않는다.

## quotation.py — 주식현재가 체결

- `inquire_ccnl(ticker: str, market: str = "J") -> dict | None` — `FHKST01010300` 주식현재가 체결. 반환 = output 첫 row(최근 체결) 키 `last_cntg_hour`(HHMMSS) / `last_price` / `last_volume` / `last_relative_strength` + `today_volume`(각 행 `cntg_vol` 합) / `raw_count`
  - 호출처: `scheduler._evaluate_universe_guard`(본체 `stale_universe_guard.evaluate_universe_guard` — universe 제외 판단) · `scheduler._refresh_stale_ccnl_cache`(본체 `stale_diagnostics.refresh_stale_ccnl_cache` — stale 종목 UI 용 TTL 5분 캐시)
- `inquire_acml_vol(ticker: str, market: str = "J") -> int | None` — `FHKST01010100` 의 **당일 누적거래량**(`output.acml_vol`) 단건. universe stale 가드의 REST 폴백(`inquire_ccnl` 은 체결별 `cntg_vol` 합뿐이라 진짜 누적이 없다). 1순위는 항상 `tick_volume.get_observed_acml_vol`(KIS 호출 0), 관측 없는 종목만 이 폴백
- 공통: 빈 응답 / KIS 오류 / 예외 → `None`(호출자 = 「판정 근거 없음」) + 6자리 영숫자 ticker 사전 가드(`_TICKER_PATTERN`, `ValueError`)

## condition.py — 조건검색 + 영업일 + 종목 기본정보 + TTL 캐시

- 등락률순위 `_fetch_fluctuation_rank`(FHPST01700000, `/ranking/fluctuation`)로 종목 필터링(momentum 전용) + 시총/거래대금 필터
- `fetch_rising_stocks()` — 등락률 15% 이상(`MIN_CHANGE_RATE`) 종목마다 `fetch_stock_detail` 을 불러 `stck_sdpr`(거래소 기준가)가 양수면 `scanner.ticker_prev_close[ticker]` 를 덮는다(실시간 등락률 계산용)
  - 관측 **`[prev_close_overwrite] ticker= old= new= diff_pct=`**(cycle386, INFO, 행위 0) — 덮기 직전 `_observe_prev_close_overwrite(ticker, old, new)` 가 기존 값 > 0 ∧ 새 값과 다를 때만 1행, 종목당 하루 1회(`KstDailyEmitCap`, 함수 안 지연 import). 실패는 DEBUG `[prev_close_overwrite_failed]` 로 흡수(never-raise)
  - 판독 = 전일 잠정 봉 확정(`src/engine/daily_bar_finalize.py`)이 놓친 종목을 보는 두 번째 눈. 권리락·배당락 종목 말고는 0 이 정상(그날은 기준가가 전일종가와 다르다). 가드 `tests/unit/api/test_cycle386_daily_chart_summary.py`(P0~P3)
- `is_market_open(date)` — CTCA0903R(chk-holiday) `opnd_yn == "Y"`. 조회 실패 시 **True**(영업일 가정) — scheduler·strategy_funnel 등 매매 경로의 fail-open 계약
- `is_trading_day(target_date) -> bool | None` — 같은 CTCA0903R 를 **3상태**로(True=개장 / False=휴장 / None=모름 = 조회 실패·그 날짜 행 없음·예외). 「모른다」를 「개장」으로 바꾸지 않는다(`is_market_open` 과의 차이). 호출자:
  - `src/routes/market_state.py`(장운영상태 화면 — `market_ops.py` 가 그 `_resolve_trading_day` 를 재사용)
  - `src/engine/trading_calendar.py` 조회 seam `_lookup_open` — 날짜별 메모(True/False 만 캐시)로 KIS 공지 「CTCA0903R 은 가급적 1일 1회」를 지킨다(`src/engine/CLAUDE.md` `trading_calendar.py` 항목)
- `next_trading_day(after_date)` — 다음 개장일
- `add_business_days(base_date, n)` — base_date 이후 n번째 개장일. CTCA0903R 1회(~30일치)의 `opnd_yn=="Y"` n번째 row, 실패·개장일 부족 시 `base + timedelta(n+2)` 달력일 폴백. 소비 = `StrategyBase._refine_cooldown_business_days`(재진입 쿨다운 영업일 보정 — 전략 모듈의 `add_business_days` 바인딩을 먼저 찾는다)
- `fetch_daily_candles(ticker, days)` — 일봉 N영업일치. `FHKST03010100`(`/quotations/inquire-daily-itemchartprice`, 모의/실전 동일). **100일은 단일 호출 한도이지 총량 한도가 아니다**(총량은 `fetch_daily_candles_backfill` 의 날짜 윈도우 분할로 는다). `output2`(최신순), 빈 `stck_bsop_date` placeholder 제거. 윈도우 = `days + days//2 + 10`(영업일/달력일 5/7 + 마진)
- **분할 fetch (날짜 윈도우 100건 경계) + 일봉 backfill 225일**:
  - `fetch_daily_candles_ranged(ticker, start_yyyymmdd, end_yyyymmdd) -> list[dict]` — `FHKST03010100` 단일 윈도우(`FID_INPUT_DATE_1`=시작 / `FID_INPUT_DATE_2`=종료 / `FID_PERIOD_DIV_CODE="D"` / `FID_COND_MRKT_DIV_CODE="J"`). placeholder 제거, **memcache/single-flight 없음**(backfill 전용), 6자리 ticker 가드(`ValueError`). **`FID_ORG_ADJ_PRC="0"`(수정주가)은 `_fetch_daily_candles_and_cache` 와 같은 값** — DB-source ↔ KIS-source 동등성의 전제(KIS 샘플은 `"1"`)
  - `fetch_daily_candles_backfill(ticker, total_days=120, *, window=100) -> list[dict]` — 날짜 윈도우 ×`ceil(N/window)` 순차 호출 + 병합. 마지막 윈도우 `start_offset = min((i+1)*window, total_days)` 클램프 — 목표 초과 fetch 를 막아 retention 밖 재backfill churn 을 봉쇄한다. 실사용 `total_days=225` = 100/100/25(기본값 120 은 미사용 — 유일한 호출자가 값을 명시). 병합 = `stck_bsop_date` dedupe(경계 겹침) + bas_dd DESC 정렬. 윈도우 사이 50ms sleep(`_DAILY_BACKFILL_WINDOW_SLEEP_SECS`, KIS LMS chain). 윈도우 하나가 실패해도 다음 진행
  - **달력 환산은 축이 둘이고 역할이 다르다 — 합치지 않는다.**
    - ① **stride** `_WEEKEND_CAL_PER_TRADING_DAY = 7/5`(주말만) = 윈도우 시작점 간격. 🔴 **이 값을 키우면 윈도우 사이에 구멍이 생긴다** — 앞 윈도우는 공휴일 0 구간에서 100영업일 = 140달력일까지만 덮어(호출당 100건), stride 가 140 을 넘으면 그 아래가 통째로 빈다.
    - ② **depth**(마지막 윈도우 시작점)에만 휴일 보정을 비례로 얹는다 — `_DAILY_BACKFILL_HOLIDAY_MARGIN_RATIO = 0.10` + `_DAILY_BACKFILL_BASE_MARGIN_CAL = 10`. `total_days=225` → 최고 도달 **347 달력일**(< `DAILY_RETENTION_DAYS=390`) ≈ **232 영업일**이라 1회 backfill 이 target 을 **넘는다**. 가드 `tests/unit/engine/test_cycle299_backfill_target_expansion.py::test_g299_9_one_pass_reaches_target`(실도달 ≥ target)
  - `fetch_daily_candles`(캐시 경로)와 **별도 함수**다. 호출자 = `scanner._stock_master_daily_load_once`(**일봉 적재 대상 전부** 225일, `_DAILY_LOAD_VCP_BACKFILL_DAYS` — 이름의 `VCP` 는 흔적이고 대상은 index ∪ 자격 ∪ 보호 전체, cycle302). 데이터 적재 전용(매매 hot path 무관). 가드 `tests/unit/api/test_cycle172_daily_ranged_backfill.py`
- **`fetch_daily_chart_ranged_with_summary(ticker, start_yyyymmdd, end_yyyymmdd) -> tuple[dict, list[dict]]`**(cycle386) — `fetch_daily_candles_ranged` 와 TR·파라미터·6자리 가드가 같고 `(output1, output2)` 를 돌려준다(빈 응답 = `{}`·`[]`, `output2` 는 placeholder 제거). 캐시·single-flight 없음(부팅 1회용 — 두 번 부르면 KIS 도 두 번)
  - 소비처 = `src/engine/daily_bar_finalize.py` 하나 — `output1.stck_prdy_clpr`(오늘 기준 전일종가)로 헤드 봉을 교차검증한다(`src/engine/CLAUDE.md` 「저녁 데이터 적재」 절). 가드 `tests/unit/api/test_cycle386_daily_chart_summary.py`(S1~S6)
- **`inquire_stock_basics(pdno) -> StockBasics`** — `CTPF1002R` 로 NXT 거래종목(`cptt_trad_tr_psbl_yn`) · NXT 거래정지(`nxt_tr_stop_yn`) · KRX 정지 · 관리종목 파싱. 캐시 `src.db.stock_master` 24h TTL. `docs/kis/error-codes.md` 5-3절
  - 파생값 `nxt_tradable = (cptt=="Y") AND (nxt_stop=="N")` = 「KRX **에 더해** NXT 에서도 거래되나」(`False` = KRX 전용 — 루트 `CLAUDE.md` 「핵심 안전 규칙」 NXT 전제)
  - **ticker 정규화** `_normalize_ticker()` — 6자리 영숫자는 그대로, KIS `pdno` 12자리 표준코드는 끝 6자리 영숫자(`([A-Za-z0-9]{6})$`)를 뽑는다(`stock_master` PK 정합)
  - **2단 호출** — CTPF1002R → `await asyncio.sleep(0.05)`(LMS chain) → FHKST01010100(`kis_get_quote`). **CTPF1002R 실패는 전파**한다. FHKST 실패는 CTPF 단독 raw 를 반환하고 `_record_graceful_failed("fhkst01010100_failed")` 만 올린다(scanner `[stock_master_basics_refresh_summary] … graceful_failed_fhkst=N`)
  - **raw merge** — `merged_raw = dict(ctpf_output)` 에 `_FHKST_MERGE_KEYS` 33키만 덮는다(목록 밖 CTPF 키 무접촉 — `bfdy_clpr` 보존이 가드 대상). 그중 `_ZERO_VALUE_SKIP_KEYS` 15키(`acml_tr_pbmn`·`acml_vol`·`per`·`pbr` 등 — 목록 = 그 상수)는 값이 **0 이거나 비숫자·None 이면 merge 하지 않고 `continue`** — 장전 호출의 `0` 이 전일 거래대금을 지우면 `list_by_filter(acml_tr_pbmn ≥ min_trade_amount)` 가 조용히 0건이 되어 donchian/VB/LTV 후보가 사라진다
  - ⚠️ **이 함수는 기존 DB raw 를 읽지 않는다** — skip 키를 되살리는 곳은 호출자 `scanner._stock_master_basics_refresh_once` 의 `{**기존, **신규}` 머지 하나다(`upsert_one` 은 raw 통째 교체 — `src/engine/CLAUDE.md` 「basics 갱신」)
  - 가드 `tests/unit/api/test_cycle107_inquire_stock_basics_merge.py` · `test_cycle108_inquire_stock_basics_hts_avls.py` · `test_cycle144_graceful_visibility.py` · `test_cycle145_raw_preserve.py` · `tests/unit/ast/test_cycle155_ast_merge_keys.py`(33키) · `tests/unit/engine/test_cycle176_basics_refresh_raw_merge.py` · `test_cycle176_e2e_premarket_preservation.py`

### TTL 캐시 (single-flight)

목적 = KIS 부하·5xx 노출 축소:
- `fetch_stock_detail` = `_PRICE_CACHE_TTL=5s`, 키 `ticker` · `fetch_daily_candles` = `_CANDLE_CACHE_TTL=300s`, 키 `(ticker, days)`
- `asyncio.Lock` + `_inflight_*: dict[key, Task]` single-flight — 동시 N 호출이면 첫 호출만 KIS fetch, 나머지는 `await asyncio.shield(task)` 로 합류(자기 task cancel 이 inflight 로 번지지 않는다)
- 무효화 = TTL 만료 + `clear_caches()`(`_reset_daily_state` 21:30 — cycle283 D3). `_cache_epoch` bump 로 진행 중 inflight 의 stale write 차단
- **사용 범위 안전 가드**: 스캐닝/조건검사 한정. `execute_buy/execute_sell` 의 체결가/주문가 결정 경로에는 절대 쓰지 않는다(WebSocket tick 또는 직접 호출)
- **종목상태 관측 훅 `_notify_status_observer(ticker, output)` (cycle369)** — `_fetch_stock_detail_and_cache` 가 `output` 대입 **직후** · 캐시 lock **앞**에서 한 번 부른다. 훅은 `src.engine.status_exit_watch.observe_fhkst` 를 함수 안 지연 import 해 관리종목·단기과열 당일 매수 차단 레지스트리에 기록만 한다. 캐시 적중·inflight 합류는 부르지 않는다(한 조회 한 기록 = `src/engine/CLAUDE.md` 「종목상태 청산·당일 매수 차단」)
  - 🔴 **본문 전체의 `try/except Exception` 을 걷지 않는다**(DEBUG `[status_observer_failed]`, never-raise) — 훅이 예외를 흘리면 모든 `fetch_stock_detail` 소비자(VB·LTV 기준가 REST · 스윙 폴 · 급등 스캔)가 깨진다. 호출 자리·이중 try 는 AST J16 이 잠근다
- **`_PRICE_CACHE_TTL` 을 leaf 가 읽는다** — `status_exit_watch` P1 시작 = 09:00 + 이 TTL(5초)이라 장 전 캐시 값이 「장중 clean」으로 봉인되지 않는다. TTL 을 바꾸면 P1 시각도 바뀐다

## period_chart.py — 종목 차트용 기간별시세 (cycle387)

종목 차트 모달(`GET /api/stock-chart/candles`) 데이터를 KIS 에서 직접 받는다(`stock_master_daily` 는 390일 보관이라 5년을 못 채운다). **매매 경로와 섞이지 않는 읽기 전용 조회 하나**다.

- 진입점 `fetch_candle_chart(ticker, period="D", years=5, *, now_kst=None) -> CandleChart`(`src/models/candle_chart.py`). 인자 검사(라우트 검증 다음의 방어선 2): `ticker` 6자리 **ASCII** 숫자(`isascii()` ∧ `isdigit()` — `isdigit()` 만으로는 아랍-인도·전각 숫자가 통과한다) · `period` ∈ `D`/`W`/`M` · `years` 1~5 정수(`bool` 거부). 위반은 `ValueError`
- **KIS 호출은 한 곳** — `kis_get_quote(DAILY_PRICE_URL, "FHKST03010100", params)`(AST G2). `DAILY_PRICE_URL` 은 `condition.py` 상수 import(`base.py` 무변경, G5). params = `FID_COND_MRKT_DIV_CODE="J"`(KRX 정규 — `UN`/`NX` 는 정규장 종가가 없어 쓰지 않는다) · `FID_INPUT_DATE_1` = 시작일(모든 창 고정) · `FID_INPUT_DATE_2` = 커서(창마다 과거로) · `FID_PERIOD_DIV_CODE` = `D`/`W`/`M` · `FID_ORG_ADJ_PRC="0"`(수정주가 — `condition.py` 일봉 함수들과 같은 값)
- 🔴 `kis_get`·`kis_post`·`kis_request`·`_request` 를 참조하지 않고 매매·인증 모듈을 import 하지 않는다(G1·G1b). 반대로 `src/engine`·`src/realtime`·`src/auth` 도 이 모듈을 import 하지 않는다(G7) — 차트 캐시·세마포어가 매매 경로에 끼지 않게 한다
- **구간** = 오늘(KST)~`years` 년 전 같은 날(2/29 → 2/28). 시작일은 봉 단위로 맞춘다(`W` 그 주 월요일, `M` 그달 1일)
- **날짜 창 페이징** — `tr_cont` 다음 조회가 없고 한 번에 최대 `_KIS_MAX_ROWS=100` 봉이라 시작일 고정, 종료일 커서만 당긴다(다음 커서 = `D` 가장 오래된 봉 −1일, `W`·`M` 그 봉 기간 첫날 −1일). 두 창에 같은 기간 봉이 오면 **먼저 받은(더 최신 창) 값**이 남는다. 멈춤:
  - 정상 종료(`complete=true`) — 빈 창 · 100봉 미만 · 시작일 도달
  - 부분 결과(`complete=false` + `incomplete_reason`) — 커서가 앞으로 가지 않음 `no_progress` · 호출 상한 `call_cap` · 시간 예산 초과 `time_budget` · 둘째 창 이후 예외 `window_error`
  - 🔴 **첫 창 예외는 그대로 전파하고 캐시하지 않는다**(라우트가 `success=false` 로 바꾼다)
- **상수**(AST G4 가 값을 잠근다): `_MAX_CALLS_PER_FETCH = {"D": 15, "W": 4, "M": 2}` · `_WINDOW_SLEEP_SECS = 0.25` · `_FETCH_CONCURRENCY = 1` · `_QUEUE_WAIT_SECS = 20.0` · `_FETCH_TIME_BUDGET_SECS = 25.0` · `_CACHE_TTL_SECS = 600` · `_PARTIAL_CACHE_TTL_SECS = 60` · `_CACHE_MAX_ENTRIES = 32` · `_PROVISIONAL_CUTOFF = timedelta(hours=6)`
- **KIS 폭주 방지 — 순서대로 네 겹**:
  1. 캐시 — 키 `(ticker, period, years)`, LRU. TTL 은 완전·부분 결과가 다르다. 적중 = `cached=true` 사본. 저장 때 만료 항목을 걷는다
  2. single-flight — 같은 키 진행 중이면 `_inflight` task 에 `asyncio.shield` 로 합류
  3. 모듈 전역 세마포어 — 종목이 달라도 **한 번에 한 조회만** KIS 를 부른다. 대기 초과 = `ChartBusyError` + `[stock_chart_busy]` WARNING
  4. 호출 간격 `_WINDOW_SLEEP_SECS`(`_pace_chart_call` — 이름과 달리 창 사이가 아니라 **모든** 호출 사이) — 세마포어 안 `kis_get_quote` 직전마다 모듈 전역 `_last_call_at`(마지막 차트 호출 시작 시각)에서 그 간격까지 쉰다. 조회 경계를 넘어서도 지키므로(다음 조회의 첫 호출 · 월봉 포함) **어느 1초에도 4건 이하**다(`base.py` 전역 초당 20건을 주문·잔고와 나눠 쓴다). 🔴 간격을 조회 하나 안의 창 사이로 좁히지 않는다 — 세마포어를 놓는 순간 다음 조회가 곧바로 불러 전역 한도를 혼자 다 쓸 수 있다
- **정규화** — 가격 4칸 중 하나라도 0 이하이거나 구간 밖(끝날 뒤 · 봉 기간 첫날이 시작일 앞)인 행은 버리고 `dropped_bars` 로 센다. 결과는 오름차순. `volume`=`acml_vol` · `amount`=`acml_tr_pbmn`(숫자 6칸 정수 = `src/models/CLAUDE.md` `CandleBar`). `name` = 첫 창 `output1.hts_kor_isnm`(비면 `None`)
- **잠정 봉 표시** `last_bar_provisional` — 마지막 봉 기간의 마지막 평일 ≥ `(now − 6시간).date()` 면 참(KIS `J` 일봉은 D일 20:00 뒤 애프터마켓 값이고 D+1일 새벽에 정규장 값이 된다, cycle386). **값은 고치지 않고 화면이 「잠정」만 단다.** 06:00 경계 = `src/engine/daily_bar_finalize.py` 와 같은 값
- **로그** — `[stock_chart_fetch]` INFO(KIS 를 부른 조회마다: `calls`·`bars`·`dropped`·`complete`·`reason`·`elapsed_ms`) · `[stock_chart_partial]` WARNING · `[stock_chart_busy]` WARNING. 캐시 적중은 로그 없음
- 테스트 seam — `_monotonic`(시계, 모듈 전역 재조회) · `_reset_state_for_tests()`(캐시·inflight·세마포어·마지막 호출 시각 재생성 — asyncio 프리미티브는 처음 기다린 루프에 묶인다). 가드 `tests/unit/api/test_cycle387_period_chart_fetch.py` · `tests/unit/ast/test_cycle387_ast_stock_chart_scope.py`(G1~G7)

## 새 API 추가 절차

1. `docs/kis/{category}.md` 에서 TR_ID·URL·파라미터 확인. 2026-09-14 제도 변경 이후 사실은 `docs/kis/README.md` 「제도 변경 공지 반영」 절을 먼저 본다
2. 함수 추가 — 매매·잔고·체결조회는 `kis_get`/`kis_post`(메인 단일), 시세성은 `kis_get_quote` + 화이트리스트 등재 + AST 가드(위 Path 가드)
3. TR_ID 는 **실전 값**으로 넘기고 모의 TR_ID 를 코드에 적지 않는다. 모의(`KIS_ENV=vts`) 변환 = `TokenManager.build_headers` 가 메인·시세 풀 모든 요청 헤더에 `settings.get_tr_id()` 적용 — **첫 글자를 무조건 `V` 로** 바꾸고 멱등이다(주문·잔고 모듈의 `settings.get_tr_id("TTTC…")` 직접 호출과 겹쳐도 같다). 그래서 `FH`·`CT` 시세 TR 도 모의에선 `VH…`·`VT…` 다(정합 미검증)
4. 응답 모델은 `models/` 에 pydantic 으로 정의
