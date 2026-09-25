# CLAUDE.md — src/api/ (KIS REST API)

> 이력: [`docs/history/src-api-CLAUDE.history.md`](../../docs/history/src-api-CLAUDE.history.md)

KIS OpenAPI REST 호출 모듈. 모든 호출은 `base.py` 공통 래퍼를 통한다. **지금 동작하는 규칙만** 적는다 — 바뀐 경위는 위 history, 사이클별 보고 원문은 [`docs/HARNESS_CHANGELOG.md`](../../docs/HARNESS_CHANGELOG.md) 에 있다.

## base.py — 공통 래퍼 (메인 단일)

- `kis_request(method, url, tr_id, ...)`: 모든 KIS API 호출의 단일 진입점
- 헤더 자동 구성: authorization, appkey, appsecret, tr_id, custtype("P")
- Rate Limit: `asyncio.Semaphore(20)` 초당 20건 제한
- 에러 처리: `rt_cd != "0"` 시 msg_cd + msg1 로깅
- 자동 재시도: 네트워크/5xx 최대 3회, 지수 백오프 (`BACKOFF_BASE=0.5s × 2^(attempt-1)`) + jitter (`0~BACKOFF_JITTER=0.25s`) — thundering herd 완화
- 토큰 만료 감지 시 자동 갱신 후 재시도. 판정은 `_request` 와 `_request_via_quote_pool` 이 공유한다 — `msg_cd` 가 `_TOKEN_EXPIRED_MSG_CODES = {EGW00121, EGW00122, EGW00123}`(access token 3종) 에 있거나, `"token" in msg1.lower()` 이면서 `msg_cd` 가 `_TOKEN_BRANCH_EXCLUDE_CODES = {EGW00120, APBK0919, APBK0918}` 에 없고 `"부족" not in msg1` 일 때 참이다. 참이면 `token_manager.issue()` 후 재시도하고, 끝까지 실패하면 `[api_retry_exhausted] last_status=token_expired`
  - 🔴 **`"만료" in msg1` 로 판정 금지** — `EGW00120`("기간이 만료된 code", 이 프로젝트에서는 예수금부족 변형 = `is_insufficient_cash` 화이트리스트)을 토큰만료로 오분류하면 `auth/token.py` `_ISSUE_GAP_SECS=61` 전역 직렬 락이 그리드락을 만들고 동일 주문 body 를 재전송한다(중복 체결)
  - session_key 코드 `EGW00124`~`EGW00126` 은 `issue()` 로 해소되지 않아 화이트리스트에서 제외한다
  - 가드 `tests/unit/api/test_cycle181_token_expiry_whitelist.py` · `tests/unit/ast/test_cycle181_token_whitelist_ast.py`(frozenset 엔트리 검사 + `"만료"` Compare 노드 0건)
- 호출 메트릭: `_request_metrics` (전역 dict) `total/http_5xx/http_4xx/network_err/kis_error/retries/retry_recovered/retry_exhausted + path별 5xx top 5`. `get_request_metrics()` 스냅샷 / `reset_request_metrics()` 리셋. `log_analysis_engine.py` 가 **21:30** INSERT 후 reset(cycle283 D3). **20:05 metrics 1차 스냅샷(`daily_metrics_snapshot.py`)은 리셋하지 않는다**
- **거부 응답 영구 저장**: `rt_cd != "0"` 시 `KisApiError` raise 직전 `system_logs.write_log("ERROR", "[kis_rejection] path=... tr_id=... msg_cd=... msg1=... body={PDNO/ORD_DVSN/ORD_UNPR/ORD_QTY/EXCG_ID_DVSN_CD/SLL_BUY_DVSN_CD}")` fire-and-forget. 민감 키 (CANO/ACNT_PRDT_CD) 마스킹. `write_log` 예외 swallow. `docs/kis/error-codes.md` 4절
- **재시도 최종 결과 영구 저장**: 재시도 루프 끝난 직후 영문 prefix 1행 fire-and-forget. (a) `attempt > 1` + `rt_cd=0` 성공 → INFO `[api_retry_recovered] path=... tr_id=... attempts=N`. (b) `MAX_RETRIES=3` 모두 5xx/network 실패 후 raise 직전 → ERROR `[api_retry_exhausted] path=... tr_id=... attempts=3 last_status={503|network} last_msg=...`. 기존 `retries` (중간 시도) 와 분리 — *최종* 결과만
- **5xx 로그 억제 · 재시도 성공 집계**: 메인 `_request` 의 5xx WARNING 은 `(path, status)` 키로 60초 dedupe 한다(`_request_5xx_dedupe`, `_REQUEST_5XX_DEDUPE_WINDOW=60.0`). WARNING 은 헬퍼 `_warn_http_status()` 경유만 쓴다. 재시도 성공은 `_record_api_recovered(path, attempts)` 로 누적하고 `scheduler._api_recovered_collector_loop` 가 5분마다 `[api_retry_recovered_summary] window=300s total= by_path=` 1행을 남긴다(`_API_RECOVERED_COLLECTOR_WINDOW=300.0`, 빈 윈도우는 skip). 시세 풀은 `_quote_5xx_dedupe`(`(path, label, status)`) · `_record_quote_recovered` · `_flush_quote_recovered_collector` 로 분리돼 있다
  - **ERROR 는 억제 밖**이다 — `[api_retry_exhausted]`(5xx·네트워크·토큰 최종 실패) 와 `[kis_rejection]`/`[kis_rejection_quote]` 는 건별로 남는다
  - AST 가드 3: `_request` 안에서 `logger.warning("HTTP …")` 직접 호출 0건(헬퍼 경유만) · 시세 풀 `_record_5xx_for_dedupe` 호출 존재 · `[api_retry_recovered]` 직접 `write_log` 0건(collector 경유만)

## base.py — REST 시세성 호출 풀

시세성 KIS REST 호출만 보조 계좌(`kis_quote_accounts`) 라운드로빈으로 분산. 매매/잔고/체결조회는 영원히 메인 단일.

**자금 안전 절대 원칙**:
- 매매 (`place_order`/`cancel_order`) / 잔고 (`get_balance`/`get_buyable`) / 체결조회 (`get_daily_orders`) / 체결통보 → 메인 단일 (`kis_request` 그대로)
- 시세성 호출만 본 풀에 라우트: `condition.py` 함수 전부(`is_market_open` · `next_trading_day` · `is_trading_day` · `add_business_days` · `_fetch_fluctuation_rank` · `inquire_stock_basics` · `fetch_stock_detail` · `fetch_daily_candles` · `fetch_daily_candles_ranged`) · `quotation.py`(`inquire_ccnl` · `inquire_acml_vol`) · `finance.fetch_financial_tr` · `market_operation.inquire_vi_status_today` · `scanner._fetch_market_cap_page`. `krx.py` 는 KIS 밖 시스템이라 무관

**Public API**:
- `kis_get_quote(path, tr_id, params, *, hashkey="")` — 시세 GET (보조 라운드로빈 + 메인 fallback)
- `kis_post_quote(path, tr_id, body, *, hashkey="")` — 시세 POST (인터페이스 대칭)
- `get_quote_request_metrics() -> dict` — 격리 스냅샷 (`total/http_5xx/4xx/network_err/kis_error/retries/recovered/exhausted/by_label`)
- `reset_quote_request_metrics() -> None` — 메인 reset 과 분리

**Path 가드** (`QuotePoolPathError` raise — `ValueError` 서브클래스):
- 화이트리스트 **13 path**(`_QUOTE_ALLOWED_PATHS`) 만 허용: `/quotations/inquire-price` / `/quotations/inquire-daily-itemchartprice` / `/ranking/fluctuation` / `/quotations/search-stock-info` / `/quotations/chk-holiday` / `/quotations/inquire-ccnl` / `/ranking/market-cap` / `/quotations/inquire-vi-status` / `/finance/income-statement` / `/finance/balance-sheet` / `/finance/profit-ratio` / `/finance/stability-ratio` / `/finance/other-major-ratios` (상수는 `/uapi/domestic-stock/v1` 접두를 포함한 전체 경로)
- 🔴 **신규 시세 path 는 화이트리스트 등재 + AST 가드 동반이 의무**다 — 빠뜨리면 그 호출이 `QuotePoolPathError` 로 전건 실패한다(market-cap · finance · vi-status 에서 세 번 반복된 결함. vi-status 가 빠져 있던 동안 매 부팅·재시작마다 VI 시드가 100% 실패했다)
- `/quotations/volume-rank`(거래량순위 FHPST01710000) **재도입 금지** — 호출 0건 dead 로 폐기했다. 가드 `tests/unit/api/test_cycle179_no_volume_rank_in_quote_allowlist.py`
- 매매성 path 오염 검사는 **세그먼트 판정**으로 한다 — 키워드 부분일치는 `finance/balance-sheet` 를 `inquire-balance` 로 오탐한다. 가드 `tests/unit/api/test_cycle109_market_cap_allowlist.py` · `tests/unit/api/test_cycleC1_finance_allowlist.py` · `tests/unit/api/test_vi_status_quote_allowlist.py`
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
- **자동 비활성 임계 3종**: consecutive 5 / 5분 50% / 1분 80%(`FAST_WINDOW_SECS=60`, `FAST_MIN_CALLS=10`, `FAST_MAX_FAILURE_RATE=0.8`). 영구 결함 라벨(ISA 등 5xx 80% 이상)을 빠르게 탈락시킨다. 운영자 안내: 5xx 가 잦은 보조 라벨은 자동 임계 도달 전에 Settings UI `active=false` 로 수동 비활성 권장

**5xx 폭주 억제**:
- **WARNING dedupe** (`_record_5xx_for_dedupe(path, label, status) -> bool`): 동일 `(path, label, status)` 키 60s 윈도우 (`_QUOTE_5XX_DEDUPE_WINDOW=60.0`) 내 재발생 시 첫 1회만 WARNING + 카운트만 누적. ISA 같은 영구 5xx 라벨에서 분당 ~30 행 WARNING → 1행 + 60s summary INFO. lock `_quote_5xx_dedupe_lock` (asyncio.Lock) 동시성 보호
- **60s summary task** (`_emit_5xx_dedupe_summary()`): scheduler `_5xx_dedupe_summary_loop` 가 60s 주기 호출. 윈도우 만료 + 카운트 ≥ 2 인 키 1행 INFO `[quote_pool_5xx_summary] path=... label=... status=500 count=N within=60s` + dedupe state clear
- **메인 fallback 우선**: `_request_via_quote_pool` 의 라벨 선택 직후 `health_monitor.get_recent_5xx_ratio(label)` 조회. `total>=FAST_MIN_CALLS(10)` AND `ratio>=_LABEL_FALLBACK_5XX_RATIO_THRESHOLD(0.8)` 면 `label=None` 강제 (메인 fallback). 3회 재시도 backoff (수 초) 회피 → 응답 지연 ms 단위. 메트릭 `fast_fallback` 카운터 +1 운영 가시화
- **메트릭 확장**: `_quote_request_metrics["fast_fallback"]` — 80%+ 라벨 skip 누적 카운트. `get_quote_request_metrics()` / `reset_quote_request_metrics()` 동기화

## order.py — 주문

- 현금 매수: TTTC0012U / 매도: TTTC0011U / 정정·취소: TTTC0013U
- `settings.get_tr_id()` 모의/실전 자동 변환
- **자금 안전**: 본 모듈은 `kis_post` (메인 단일) 만 사용. `kis_post_quote` / `kis_get_quote` 절대 import 안 함 — `test_condition_quote_routing.py::test_order_module_never_imports_quote_pool` 가드
- `place_order(..., exchange="KRX")` / `cancel_order(..., exchange="KRX")`: `EXCG_ID_DVSN_CD` body. `KRX`(기본) / `NXT` / `SOR`. 모의(VTS) KRX 만 허용 — SOR/NXT 실전 한정. 미지정 시 KRX (후방 호환)
- **매수 지정가 분기**: `order_engine.execute_buy` 가 "시장가매매불가" 거부 폴백 시 `place_order(side=BUY, price=fallback_price>0, order_division=LIMIT, exchange=...)`. body 는 `ORD_DVSN=order_division.value`, `ORD_UNPR=str(price)` 직렬화 — 매도 지정가와 동일 경로
- **`OrderDivision`(cycle287, 2026-09-12) — 시각이 정한다.** `place_order` 는 값을 **검증 없이 그대로** `ORD_DVSN` 에 흘려보낸다(화이트리스트 절대 금지 — 끼워 넣으면 `44` 가 조용히 사라진다). 표:

  | 구간 | `ORD_DVSN` | 의미 | `ORD_UNPR` |
  |---|---|---|---|
  | 정규장·프리장 | `"01"` | 시장가(기본) | `"0"` |
  | 정규장·프리장 폴백 | `"00"` | 지정가 | 매수 `step_up(5)` / 매도 `step_down(5)` |
  | **NXT 프리마켓**(08:00~08:50) 매수 승격(cycle291, 2026-09-13) | `"27"` | GTP지정가 | `step_up(현재가,5)` — `"00"` 폴백과 **같은 값**(가격 행위 변경 0). 정본에 규약이 없어 지정가 비대칭 판정으로 골랐다(§3) |
  | **KRX 애프터**(16:00~20:00, 2026-09-14 신설) 1차 | `"44"` | 최유리지정가 | `"0"`(**정본 명시 없음** — 현금주문 문서는 "시장가 등" 비열거형, 신용주문 문서는 열거형이지만 최유리(03)·최우선(04)를 그 열거에서 뺀다. §4-A 비대칭 판단: 틀리면 즉시 거부돼 관측 가능. 현재가를 넣었는데 실제로 0이 필요했다면 상한가 기준 주문금액 산정 위험) |
  | KRX 애프터 폴백 | `"41"` | 지정가 | `step_down(현재가,5)`(우리가 가격을 통제) |

  41~47 전체가 애프터 전용이지만 `OrderDivision` 은 `41`/`44` 둘만 갖는다 — IOC/FOK(42/43/45/46)는 잔량 자동취소로 손절 잔여를 잃고, 47(최우선지정가)은 자기 방향 최우선호가라 크로스하지 않아 체결 보장이 없다. 27~29(NXT GTP) 전체도 같은 규율로 `27` 하나만 갖는다 — `28`(GTP최유리)은 `ORD_UNPR` 규약이 현금·신용 문서 사이에서 갈리고 얇은 프리마켓 호가에서 1레벨에 멈추며, `29`(GTP최우선)는 자기 방향 최우선호가라 크로스하지 않는다(cycle291 §3). **애프터마켓엔 시장가(01)가 없고 ETP(ETF/ETN) 거래가 불가**(KIS 공지 verbatim). `EXCG_ID_DVSN_CD` 는 이 코드와 별개로 라우팅된다 — 시각·거래소 결정 로직(`_route_exchange_by_clock`/`_apply_clock`)은 `src/engine/CLAUDE.md` §order_engine.py 「cycle287」 절이 정본.

  **`27`(GTP지정가) — cycle291(2026-09-13, 사용자 결정 "(나)안")**: NXT 프리마켓(08:00~08:50) 매수 미체결을 거래소가 08:50 에 일괄취소하도록 위임하는 전용호가. 지금 프리장에 보내는 `00`(지정가)은 그 자동취소를 받지 못해 미체결이 NXT 정규장(09:00:30~)으로 새고, 새는 방향이 역선택 쪽으로만 치우친다(폐기된 프리장 목표가가 잡는 체결은 가설이 깨진 방향에서만 일어난다) — 자문 §1. **매도는 여전히 `00`**이다(자문 §2) — GTP 매도는 08:50 자동취소가 `_selling` 을 해제 주체가 도착하는 ≈09:45(`_scan_loop`)까지 잠가 손절 재평가를 억제하고, 현행 `00`은 오히려 09:00:30 NXT 정규장에서 시세 아래 지정가라 거의 확실히 체결돼 안전망으로 기능한다 — 루트 CLAUDE.md 「매도/손절/Trailing 은 PRE/MAIN/POST 무관 항상 작동」 저촉 판정. 게이트 4중(§실전·NXT 전용·`market_state` 그 시각 유효·프리장 판정) 중 하나라도 실패·예외면 `00`이 그대로 나가 fail-safe. `27` 거부는 우리 분류기 어디에도 안 걸려 미분류로 처리되므로 "우리가 27을 보냈다"는 사실 자체를 게이트로 삼아 같은 가격 `00` 1회 폴백을 강제한다(폴백 없이 raise 하면 `risk.on_tick` 이 죽는다, cycle229 실증). 상세 = `src/engine/CLAUDE.md` §order_engine.py 「cycle291」 절.

  **취소(`cancel_order`)의 `ORD_DVSN`** — 시그니처는 `cancel_order(..., order_division: str | None = None)` 이고 falsy 면 `"00"` 이다. `order_engine` 의 취소 3경로(`_cancel_after_wait`/`_cancel_and_reorder`/`cancel_remaining`)는 이 인자를 **전달하지 않는다** — 애프터 `41`/`44` · GTP `27` 원주문의 취소가 `"00"` 으로 정상 처리되는지는 실적 0건이라 미검증이다(docstring 에 명시). 관측은 매 시도마다 1행 남는다 — `[after_cancel_result] ticker= order_no= ord_dvsn= orig_dvsn= dvsn_src=map|absent exchange= result=ok|error err=`(`ord_dvsn` = 실제 전송값, `orig_dvsn` = 원주문이 실었던 호가유형 = `OrderEngine._order_division` 매핑, `_order_exchange` 와 대칭). 🔴 **원주문 호가유형 승계 전송은 매매 행위 변경이라 별도 승인 대상**이다 — 정본에 "취소 시 원주문 호가유형을 승계하라" 는 규약이 없고(국내주식 정정취소 필드표에 그 문장이 없다. 선물옵션만 `[취소] 01 로 입력` 고정값을 명시), 켜면 실적 있는 정규장 부분체결 취소의 `ORD_DVSN` 이 `"00"`→`"01"`(원주문 시장가)로 바뀐다. 전환 선결 조건 = `orig_dvsn` 이 `41|44|27` 인 행만 `result=error` 로 층화되는 실측.

## balance.py — 잔고/조회

- 잔고조회: TTTC8434R / 매수가능조회: TTTC8908R
- **자금 안전**: 본 모듈은 `kis_get` (메인 단일) 만 사용. 보조 시세 풀 함수 절대 import 안 함 — `test_balance_module_never_imports_quote_pool` 가드
- `get_balance(afhr_flpr="N")`: `AFHR_FLPR_YN` query. `N`(기본 정규장) / `Y`(시간외 단일가) / `X`(NXT 정규장) — required
- 🔴 **`get_balance()` 의 `prpr`(현재가)은 KRX 애프터마켓 체결을 반영하지 않는다 (2026-09-14 라이브 실측).** 16:00~20:00 내내 보유 11종목의 `prpr` 이 전부 무변동이었는데, 같은 종목 `004020` 을 `quotation.inquire_ccnl` 로 조회하면 `last_cntg_hour=195947`(19:59:47 체결)이 나온다 — **REST 시세 조회는 그 체결을 본다.** **실측 범위는 `prpr` 하나다** — `evlu_amt`(평가금액)·`nass_amt`(순자산, `summary.net_asset` 의 원천)는 KIS 가 서버에서 계산해 내려주는 별도 필드라 같이 얼었는지 **재지 않았다**. 얼었다고 보는 것이 자연스럽지만(같은 현재가에서 파생될 것이므로) 그건 **[추론]** 이다. 확인 방법 = 애프터 구간에 `evlu_amt` 와 `prpr × hldg_qty` 를 대조한다 — 어긋나면 별도 갱신 경로가 있다는 뜻이다. ⚠️ 2026-09-14 제도 변경으로 그 창이 연속 체결 구간이 됐으니, 애프터마켓 가격을 근거로 판단하는 코드는 `get_balance` 가 아니라 시세 조회를 써야 한다(현재 소비처 = 대시보드 표시 · `account_risk_watcher` 의 `summary.net_asset`)
- `get_daily_orders(target_date="", exchange="ALL")`: TTTC0081R. `EXCG_ID_DVSN_CD` query required — `ALL`(기본, KRX+NXT+SOR 합산) / `KRX` / `NXT` / `SOR`. NXT 체결 누락 방지 위해 기본 ALL

### KIS 거부 응답 분류 헬퍼

- `is_market_closed_rejection(KisApiError) -> bool`: 장운영시간 외 / 매매 불가 시간 / 거래시간 외. `msg_cd=APBK0918` 공용이라 msg1 키워드(`_MARKET_CLOSED_KEYWORDS`) 로 분리. True 면 `is_insufficient_*` False — positions 보존 결정
- `is_insufficient_cash(KisApiError) -> bool`: 예수금 부족 매수 실패. msg_cd 화이트리스트 (APBK0919/EGW00120) + msg1 키워드 ("부족" + "주문가능금액/예수금/현금") 동시 검사. `APBK0918` 은 현금 키워드 동반 시만 True. OrderEngine 매수 락 결정용
- `is_insufficient_quantity(KisApiError) -> bool`: 보유 부족 매도 실패. msg1 키워드 ("부족" + "매도가능/보유수량/잔고") + `APBK0918` 은 보유 키워드 동반 시만 True. 매도 즉시 break 결정용
- **`is_sell_qty_exceeded(KisApiError) -> bool` (cycle236, N2)**: 매도 수량 초과 — `msg_cd=APBK0400` ∧ msg1 "수량"·"초과" 동시(보수 매칭 — 정본 오류코드 사전 부재라 실측 3건(08-28 257720, TTTC0011U)이 근거). 의미 = "요청 > 매도 가능" = **부분 보유가 내재된 코드** → `is_insufficient_quantity`(positions 통째 삭제 경로)에 **흡수 금지**가 계약. 소비 = `execute_sell` **#1.5**(closed 다음·insufficient 앞): `get_balance` 재대조 → 오염(held<positions) = **held(보유 실체)로 보정**+재시도 자기 치유 / 부분·전량 잠김(held≥positions ∧ sellable<held) = 보존+중단(`_selling` **유지** — 열린 기주문 실재, stale 은 selling_reconcile 180s 소관) / 실보유 0 = insufficient 경로 재사용 / 재대조 실패 = 일반 재시도. 검사 순서 = **closed → sell_qty_exceeded → insufficient → disallowed**(closed 우선 계약 불변)
- `is_market_order_disallowed(KisApiError) -> bool`: 시장가 거부. msg1 키워드 `_MARKET_ORDER_DISALLOWED_KEYWORDS`: `시장가매매불가` / `시장가 매매 불가` / `시장가 주문 불가` / `시장가 호가 불가` / `시장가호가불가` / `최유리/최우선지정가 주문만` / `지정가 및 최유리` / `단일가매매`. ⚠️ **`is_market_closed_rejection` 과 이중 매칭이 실재한다** — APBK0918 "장운영시간이 아닙니다.([프리마켓] 시장가 매매 불가 시간)" 은 양쪽 키워드에 동시 매칭한다. `execute_sell` 은 closed 를 **먼저** 검사하므로 이중 매칭 = 보류(포지션 보존 + 다음 09:00 TTL) — 프리장 왜곡 시세라 지정가 폴백 즉시 매도보다 보류가 안전하다는 **의도된 계약**이고, 순서 반전은 가드가 막는다(`test_rejection_classifier_pre_market_priority.py`). `is_insufficient_*` 2종과는 상호 배타. msg_cd 누적: APBK1943 (계양전기 매도) + APBK3013 (NXT 애프터 매도 · 단일가 세션 변형 — closed 미매칭이라 지정가 폴백 정상 경로). `docs/kis/error-codes.md` 4-2절 / 5-4절

## kis_master.py — KIS 공식 일일 마스터 파일

KIS 공식 다운로드 (`https://new.real.download.dws.co.kr/common/master/`) 일일 마스터 파일 (`kospi_code.mst.zip` / `kosdaq_code.mst.zip`) cp949 fixed-width 파싱 → `list[dict]` → upsert. 매일 **16:30** KST 자동 갱신 (fire-and-forget).

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

### SSL 옵션 C

- `httpx.AsyncClient(verify=True)` 우선 (운영 보안)
- 폴백: `httpx.ConnectError` + SSL/certificate 키워드 시만 `verify=False` 재시도 + WARNING 로그 (그 외 에러는 전파)
- `ssl._create_unverified_context` (사용자 샘플 무조건 검증 off) 영구 폐기

### 매매 활용 키 ~30

- 진입 차단 7건 (HIGH): `trht_yn` 거래정지 / `mang_issu_yn` 관리종목 / `ssts_hot_yn` 공매도과열 / `stange_runup_yn` 이상급등 / `sltr_yn` 정리매매 / `mrkt_alrm_cls_code` 시장경고 / `invt_alrm_yn` 투자주의환기 (코스닥 전용)
- 시총: `prdy_avls_scal` 전일 시가총액 (**억 원**). 시총 필터는 `list_by_filter` / `list_paged_by_filter` 가 `raw.hts_avls`(억원) 기준 직접 수행
- 재무: `roe` / `sale_account` 매출액 / `bsop_prfi` 영업이익 / `op_prfi` 경상이익 / `thtr_ntin` 당기순이익
- 지수편입: `kospi200_apnt_cls_code` / `kospi100_issu_yn` / `kospi50_issu_yn` / `ksq150_nmix_yn` / `krx300_issu_yn` / `krx_issu_yn`
- 시장 영역: `lstn_stcn` 상장주수 (천주) / `cpfn` 자본금 / `marg_rate` 증거금비율 / `crdt_able` 신용가능
- 기타: `stck_lstn_date` 상장일자 / `po_prc` 공모가 / `prst_cls_code` 우선주 / `byps_lstn_yn` 우회상장 / `flng_cls_code` 락구분 / `short_over_cls_code` 단기과열 / `insn_pbnt_yn` 불성실공시

### 단위 환산

- `prdy_avls_scal` (KIS 마스터) = **억 원** (구조체 `.h` 명세 "전일기준 시가총액 (억)" 기준. 1 억 = 100,000,000 원 = 100 백만원)
- `hts_avls` (KIS FHKST01010100 `inquire_price` "HTS 시가총액") = **억 원**(사이클 166 확정). 원 환산 = `× 100_000_000`
- 시총 필터 경로가 전부 억원 기준이다 — `list_by_filter`(python `hts_avls × 100_000_000`) · `list_paged_by_filter`(생성 컬럼 `hts_avls_eok`, migration 039) · scanner KRX 폴백(`// 100_000_000`) · 프론트 `formatMarketCap`
- 🔴 **`hts_avls` 를 백만원으로 읽지 않는다** — 100배 어긋나 `min_market_cap=1,000억` 에서 후보 풀이 1,734 → 80 으로 잘린다(95.4% 축소)
- 시총 헬퍼 3개(`market_cap_master_to_millions` / `validate_market_cap_consistency` / `get_market_cap_millions`)는 **없다** — 호출처 0건으로 폐기했고 재도입은 AST 가드가 막는다 (`tests/unit/ast/test_cycle167_ast_no_dead_market_cap_funcs.py`)
- 회귀 가드: `tests/unit/db/test_cycle166_hts_avls_unit_correction.py` · `tests/unit/engine/scanner/test_cycle166_krx_fallback_eok_unit.py` (AST 단위 가드 = `1_000_000` 잔존 0건)

### 호출자

- `src/engine/scanner.py::_stock_master_master_load_once()` — 다운로드 + 파싱 + `stock_master.upsert_master_raw()` 배치 + emit
- `src/engine/scheduler.py::_stock_master_master_load_task_loop()` — 16:30 KST 자동 task lifecycle
- `src/routes/stock_master.py::refresh_master_now()` — POST `/api/stock-master/master/refresh` 수동 trigger (BackgroundTasks fire-and-forget)

## finance.py — KIS 재무 5 TR fetch

퀀트 재무필터 (마법공식 EV/EBITDA·ROC + F-Score-7) 원천 데이터. KIS 재무 5 TR 을 `kis_get_quote` 시세성 풀 경유로 호출 → `stock_master_financial` 정규화. `fetch_daily_candles_ranged` 답습 (6자리 ticker 가드).

### 5 TR 정본 (path, TR_ID)

| kind | path | TR_ID | 산출 컬럼 |
|------|------|-------|----------|
| income | `/finance/income-statement` | FHKST66430200 | sale_account / sale_totl_prfi / bsop_prti / thtr_ntin / depr_cost |
| balance | `/finance/balance-sheet` | FHKST66430100 | cras / fxas / total_aset / flow_lblt / total_lblt / total_cptl / cpfn |
| profit | `/finance/profit-ratio` | FHKST66430400 | cptl_ntin_rate / sale_totl_rate |
| stability | `/finance/stability-ratio` | FHKST66430600 | lblt_rate / crnt_rate |
| other | `/finance/other-major-ratios` | FHKST66430500 | ebitda / ev_ebitda |

- **TR_ID 컨벤션 = FH 접두사 직접 하드코딩** (`settings.get_tr_id()` 미사용) — 5 TR 모두 FH 접두사 = 실전/모의 동일이나, 헬퍼의 V+base[1:] 변환이 `FH...` → `VH...` 로 깨짐 → 직접 하드코딩. 응답 output = 다기간 list
- `fetch_financial_tr(ticker, tr_key, div_cls="0") -> list[dict]` — 단일 TR fetch (`div_cls` 0=년/1=분기)
- `fetch_all_financials(ticker, div_cls="0") -> list[dict]` — 5 TR 호출 후 `stac_yymm` join 병합
- **시세성 풀 화이트리스트 13 path 필수** (base.py `_QUOTE_ALLOWED_PATHS` — finance 5 path, 위 base.py 절 참조)
- 호출자: `src/engine/scanner.py::_stock_master_financial_load_once()` (주1회 16:40) + 관찰 훅 `volatility_breakout._apply_quant_filter_in_prepare` (오프라인)
- 매매 hot path 무관 (재무 데이터 적재 = 매수 진입 전)

## krx.py — KRX 정식 OPEN API 클라이언트

KRX Data Marketplace (openapi.krx.co.kr) 정식 OPEN API 호출 모듈. KIS OpenAPI 와 완전 분리된 별개 시스템.

### 호출 규약

- **GET** + 인증은 **query parameter `AUTH_KEY=`** + 파라미터도 **query string `params=`**. 외부 정본 2건(`raccoonyy/pykrx-openapi/src/pykrx_openapi/client.py` 의 `self.session.get(url, params=params, timeout=self.timeout)` · `seobaeksol/krx-rs/docs/krx-api-reference/KRX_API_Spec.md`)이 독립 일치
- `fetch_krx_open_api(endpoint_path, params)` 단일 진입점 · 예외 `KrxApiError` · 키는 DB 동적 로드 `get_krx_open_api_config()` (`src/db/system_config.py`)
- 응답 형식: `{"OutBlock_1": [{...}, ...]}` JSON 배열 (누락 시 빈 리스트 graceful)

### 함수 4종

| 함수 | endpoint | 응답 필드 수 | 용도 |
|------|----------|------------|------|
| `fetch_stk_bydd_trd(date)` | `/sto/stk_bydd_trd` | 15 | KOSPI 일별 매매정보 (KIS market-cap 영역 대안) |
| `fetch_ksq_bydd_trd(date)` | `/sto/ksq_bydd_trd` | 15 | KOSDAQ 일별 매매정보 |
| `fetch_stk_isu_base_info(date)` | `/sto/stk_isu_base_info` | 12 | KOSPI 종목 기본정보 (CTPF1002R 영역 대안) |
| `fetch_ksq_isu_base_info(date)` | `/sto/ksq_isu_base_info` | 12 | KOSDAQ 종목 기본정보 |

**bydd_trd 핵심 15 필드**:
- `ISU_CD` (단축코드 6자리, KRX 종목코드 정합) / `ISU_NM` / `MKT_NM` / `SECT_TP_NM`
- 가격: `TDD_CLSPRC` / `TDD_OPNPRC` / `TDD_HGPRC` / `TDD_LWPRC` / `CMPPREVDD_PRC` / `FLUC_RT`
- 거래: `ACC_TRDVOL` / **`ACC_TRDVAL`** (원 단위, `min_trade_amount` 직접 정합)
- 시총: **`MKTCAP`** (원 단위) → KIS `hts_avls`(억원) 환산 `// 100_000_000`
- 상장: `LIST_SHRS`

**isu_base_info 12 필드** (ticker 정합):
- `ISU_CD` (12자리 표준코드, **사용 금지** — stock_master PK 비정합)
- **`ISU_SRT_CD`** (단축코드 6자리, KRX 종목코드 정합)
- `ISU_NM` / `ISU_ABBRV` / `ISU_ENG_NM` / `LIST_DD` (상장일)
- `MKT_TP_NM` / `SECUGRP_NM` (증권구분) / `SECT_TP_NM` / `KIND_STKCERT_TP_NM` (보통주/우선주)
- `PARVAL` (액면가) / `LIST_SHRS`

### 폴백 (호출자 `src/engine/scanner.py::_full_universe_load_once`)

- KRX 1차 우선 호출 (4 endpoint + 50ms sleep = KIS LMS chain 안전 마진)
- 4 endpoint 모두 `KrxApiError`(비활성/401/4xx/5xx/네트워크 예외) 를 호출자에게 전파 → KIS market-cap 자동 폴백
- 양쪽 모두 실패 시 raise

### 보안

- 평문 key 는 query parameter 에만 쓴다 — **URL 전체 로그 금지** (endpoint_path 만 로그)
- `KrxApiError` 메시지에도 평문 key 노출 0건

**Rate Limit**: 키당 일일 10,000 호출 (현재 4 호출/일).

**회귀 가드**: `tests/unit/api/test_cycle112_krx_client.py` · `tests/unit/api/test_cycle115_krx_endpoints.py` · `tests/unit/engine/scanner/test_cycle115_full_universe_load_krx_fallback.py` · `tests/unit/ast/test_cycle115_krx_endpoint_urls.py` (endpoint 경로 상수) · `tests/unit/ast/test_cycle115_krx_no_plaintext_key.py` (평문 key 노출)

## market_operation.py — 장운영정보(H0UNMKO0) 정본 + VI 현황 REST 폴백

WebSocket 장운영정보의 **파싱 정본**이 여기 있다. 구독을 보내는 쪽은 `src/engine/market_op_subscribe.py`,
받은 상태를 쌓는 쪽은 `src/engine/market_operation_monitor.py` 다 — 셋의 역할이 다르다.

| 심볼 | 내용 |
|---|---|
| `MARKET_OP_TR_ID = "H0UNMKO0"` | 통합 장운영정보 TR_ID |
| `VI_STATUS_TR_ID = "FHPST01390000"` · `VI_STATUS_URL = "/uapi/domestic-stock/v1/quotations/inquire-vi-status"` | 부팅 시드용 REST 보조 폴백. 이 path 는 시세 풀 화이트리스트에 **있어야 한다**(2026-08-04 추가 — 없던 동안 매 부팅 `QuotePoolPathError` 로 VI 시드가 100% 실패했다) |
| `@dataclass MarketOpEvent` | 논리 10칸의 파싱 결과. 칸 이름과 순서는 KIS 문서 통합 표(`[0]=TRHT_YN` … `[9]=EXCH_CLS_CODE`)를 따른다. `ticker` 는 `tr_key` 에서 온다 |
| `parse_market_op_payload(tr_key, payload) -> MarketOpEvent` | `^` 구분 페이로드 → 이벤트. 실제로 몇 번째 칸을 읽을지는 아래 「칸 기준점」이 정한다. 없는 칸은 `""` |
| `ISCD_STAT_BLOCKING = frozenset({"58"})` · `is_iscd_stat_blocking(code) -> bool` | 종목상태구분코드(`ISCD_STAT_CLS_CODE`)의 거래정지 판정. `58`(거래정지 지정 종목) **하나만** True |
| `is_event_blocking(event) -> bool` | stale 회피 판정 = `TRHT_YN=="Y"` · VI 활성(`VI_CLS_CODE`·`OVTM_VI_CLS_CODE`) · 종목상태 `58` 중 하나(MRKT_TRTM 제외). 프로덕션 호출자는 0 이다 — 운영 경로는 `market_operation_monitor.record_market_op_event` 가 같은 규칙을 인라인으로 판정한다 |
| `inquire_vi_status_today() -> set[str]` | 부팅 REST 1회 시드. graceful — 실패해도 매매 안전성 영향 0 |

🔴 **칸 기준점 — 라이브 프레임은 첫 칸이 종목코드다.** KIS 문서 통합 절(`docs/kis/domestic-stock-realtime.md`)은
종목코드 칸 없이 `[0]=TRHT_YN` 으로 적혀 있다. 라이브 `H0UNMKO0` 프레임은 KRX·NXT 단독 표처럼
`[0]=종목코드` 다(EC2 실측 2026-09-21~23, 17건 전수). 그래서 파서는
`off = 0 if fields[0] in ("Y","N") else 1` 로 기준점을 정한다. `fields[0]` 이 정확히(`==`, `startswith` 아님)
`"Y"`/`"N"` 이면 문서 모양, 그 밖은 전부 라이브 모양(한 칸씩 밀림)이다.
- `tr_key == fields[0]` 으로 판별하지 않는다 — `KisWebSocket._handle_raw` 가 `tr_key` 를
  `payload.split("^")[0]` 로 뽑으므로 운영 경로에서는 항상 참이라 판별력이 없다.
- 칸 계산은 이 파서 **한 곳뿐**이다. `src/realtime/handler.py::_handle_market_op` 는 `payload.split` 을 직접 하지
  않고, 파싱된 `event.mkop_cls_code` 를 로그와 보드 콜백에 넘긴다.
- 근거 메모 = `_workspace/domain_consult/cycle359_mkop_field_offset.md`.

🔴 **거래정지는 `TRHT_YN=="Y"` 또는 종목상태 `58` 뿐이다(2026-09-25 사용자 결정).** 51(관리)·52~54(시장경고)·
55(신용가능)·57(증거금100%)·59(단기과열)·00 은 정지가 아니다. 종목상태를 비활성 블랙리스트로 넓게 읽으면
55·57 같은 정상 상태까지 정지로 잡혀, 보유 종목이 재구독 안전망에서 빠진다.
51·59 보유 종목의 청산·신규 매수 차단은 이 모듈에 없다(별도 사이클, `domain-consult` 선행).

🔴 **VI 칸(`VI_CLS_CODE`·`OVTM_VI_CLS_CODE`)은 블랙리스트 방식이다.** `None` 과
`_INACTIVE_VALUES = {"", "0", "N", "n", "(null)"}` 은 비활성, 그 밖은 전부 활성이다.
KIS 가 코드를 늘려도 새 값이 자동으로 "활성" 으로 읽히게 하려는 의도다.
`"(null)"` 은 KIS null 토큰이다 — 라이브 프레임은 일부 빈 칸을 빈 문자열 대신 이 글자 그대로 보낸다(실측 17건 모두 정지 사유 칸이 `(null)`).
정지 사유 칸(`TR_SUSP_REAS_CNTT`)도 값이 **정확히** `"(null)"`(`_NULL_TOKEN`)이면 `""` 로 바꾼다.
부분 문자열 치환은 하지 않는다 — 실제 사유 문장 안의 `(null)` 까지 깎인다.

매매 안전성 무영향이 명문화된 영역이다 — 이 모듈이 바꾸는 것은 stale 판정의 *지연*뿐이고
`risk.on_tick`·`order_engine`·`auth` 는 건드리지 않는다.

## quotation.py — 주식현재가 체결

- `inquire_ccnl(ticker: str, market: str = "J") -> dict | None`: KIS `FHKST01010300` 주식현재가 체결. `kis_get_quote` 경유 (시세성 풀 라우팅 + Rate Limit + 메트릭)
  - 응답: output 첫 row (가장 최근 체결) + today_volume 합산. 키: `last_cntg_hour`(HHMMSS) / `last_price` / `last_volume` / `last_relative_strength` / `today_volume` / `prev_compared_rate`
  - 호출처: `scheduler._evaluate_universe_guard` (universe 제외 판단) + `scheduler._refresh_stale_ccnl_cache` (stale 종목 UI 표시용 TTL 5분 캐시)
- `inquire_acml_vol(ticker: str, market: str = "J") -> int | None`: KIS `FHKST01010100` 주식현재가 시세의 **당일 누적거래량**(`output.acml_vol`) 단건. universe stale 가드의 REST 폴백 — `inquire_ccnl`(FHKST01010300)은 체결 1건의 거래량(`cntg_vol`) 합만 주고 진짜 누적거래량이 없다. 1순위는 항상 `tick_volume.get_observed_acml_vol`(KIS 호출 0)이고, 실측 관측이 없는 종목만 이 폴백을 탄다
- 공통: graceful (빈 응답 / KIS 오류 / 예외 → `None` — 호출자가 "판정 근거 없음" 으로 처리) + 6자리 ticker 사전 가드 (`ValueError`)

## condition.py — 조건검색 + 영업일 + 종목 기본정보 + TTL 캐시

- **시세성 호출 풀 라우팅**: 본 모듈 함수는 `kis_get_quote` 사용 — 보조 라운드로빈 + 메인 fallback
- 등락률순위 API (FHPST01700000, `/ranking/fluctuation`) 로 종목 필터링 (momentum 전용 — `거래량순위`(FHPST01710000)와 다른 TR). 시총/거래대금 필터
- `is_market_open(date)`: KIS chk-holiday API (CTCA0903R) 로 개장일 여부 (`opnd_yn == "Y"`). 조회 실패 시 **True**(영업일 가정) — scheduler·strategy_funnel 등 매매 경로의 fail-open 계약
- `is_trading_day(target_date) -> bool | None`: 같은 CTCA0903R 호출을 **3상태**로 감싼 함수 — True=개장 / False=휴장 / None=모름(조회 실패·그 날짜 행 없음·예외). 「모른다」를 「개장」으로 바꾸지 않는 것이 `is_market_open` 과의 차이다. 호출자 = `src/routes/market_state.py`(장운영상태 화면, `market_ops.py` 가 그 `_resolve_trading_day` 를 재사용) + `src/engine/trading_calendar.py` 의 조회 seam `_lookup_open`(부팅 즉시 실행 영업일 슬롯 게이트 · 6전략 prepare `expected_head` — None 이면 게이트는 실행 쪽, 어댑터는 달력 판정 쪽으로 떨어진다). KIS 공지 「CTCA0903R 은 가급적 1일 1회」는 그 leaf 의 날짜별 메모(True/False 만 캐시)가 지킨다 — 상세 = `src/engine/CLAUDE.md` `trading_calendar.py` 항목
- `next_trading_day(after_date)`: 다음 개장일 (휴일 다음날 자동)
- `add_business_days(base_date, n)`: base_date 이후 n번째 개장일 date. CTCA0903R 1회 호출(~30일치)에서 `opnd_yn=="Y"` n번째 row. 실패/개장일 부족 시 `base + timedelta(n+2)` 달력일 폴백 graceful. BFB/VCP 재진입 쿨다운 영업일 정정용 (`_refine_cooldown_business_days` 소비)
- `fetch_daily_candles(ticker, days)`: 일봉 N영업일치. `FHKST03010100` (`/quotations/inquire-daily-itemchartprice`, 모의/실전 동일) — **100일은 단일 호출 한도이지 총량 한도가 아니다**(총량은 아래 `fetch_daily_candles_backfill` 의 날짜 윈도우 분할로 늘린다). 응답 `output2` (최신순), `stck_bsop_date` 빈 placeholder 제거. 윈도우 = `days + days//2 + 10` (영업일/달력일 5/7 + 마진)
- **분할 fetch (날짜 윈도우 100건 경계) + VCP backfill 225일**:
  - `fetch_daily_candles_ranged(ticker, start_yyyymmdd, end_yyyymmdd) -> list[dict]`: KIS `FHKST03010100` 단일 윈도우 조회 (`FID_INPUT_DATE_1`=시작 / `FID_INPUT_DATE_2`=종료 / `FID_PERIOD_DIV_CODE="D"` / `FID_ORG_ADJ_PRC="0"` / `FID_COND_MRKT_DIV_CODE="J"`). `kis_get_quote` 경유 (시세성 풀 + Rate Limit + 메트릭). output2 (최신순) + `stck_bsop_date` 빈 placeholder 제거. **memcache/single-flight 미사용** (backfill 전용). 6자리 ticker 가드 (`ValueError`). **`FID_ORG_ADJ_PRC="0"` (수정주가) = `_fetch_daily_candles_and_cache` 와 같은 값** — DB-source ↔ KIS-source 동등성의 전제다 (KIS 정본 샘플은 `"1"` 예시이나 이 코드베이스는 `"0"` 을 쓴다)
  - `fetch_daily_candles_backfill(ticker, total_days=120, *, window=100) -> list[dict]`: N일 backfill = 날짜 윈도우 ×`ceil(N/window)` 순차 호출 + 병합. **이 함수가 KIS 100일 한도를 총량 한도에서 풀어 주는 자리다.** 마지막 윈도우 `start_offset = min((i+1)*window, total_days)` 클램프 — 목표 초과 fetch 를 막아 retention 밖 재backfill churn 을 봉쇄한다. 실사용 `total_days=225` = 100일 윈도우 ×3 (100/100/25, 최고 도달 **347 달력일** < `DAILY_RETENTION_DAYS=390`, 경계 겹침은 dedupe). 시그니처 기본값 120 은 호출되지 않는 폴백이다 — 유일한 호출자가 값을 항상 명시한다. 중복 `stck_bsop_date` dedupe + bas_dd DESC 정렬. 윈도우 간 50ms sleep (`_DAILY_BACKFILL_WINDOW_SLEEP_SECS`, KIS LMS chain). 개별 윈도우 실패 graceful (다음 윈도우 진행)
  - **달력 환산은 축이 둘이고 역할이 다르다 — 합치지 않는다.** ① **stride** `_WEEKEND_CAL_PER_TRADING_DAY = 7/5`(주말만) = 윈도우 시작점 간격. 🔴 **이 값을 키우면 윈도우 사이에 구멍이 생긴다** — KIS 가 한 호출에 100건까지만 주므로 앞 윈도우는 공휴일 0 구간에서 정확히 100영업일 = 140달력일까지만 덮는다. stride 가 140 을 넘으면 그 아래가 통째로 비고 어느 윈도우도 다시 집지 않는다. ② **depth**(마지막 윈도우 시작점)에만 휴일 보정을 비례로 얹는다 — `_DAILY_BACKFILL_HOLIDAY_MARGIN_RATIO = 0.10` + `_DAILY_BACKFILL_BASE_MARGIN_CAL = 10`. `total_days=225` → 347 달력일 = 실측 비율(1.479)로 **약 232 영업일**이라 1회 backfill 이 target 을 **넘는다**(공휴일 0 인 해 247 · 밀집한 해 228 로 어느 쪽도 목표 위). 가드 = `tests/unit/engine/test_cycle299_backfill_target_expansion.py::test_g299_9_one_pass_reaches_target`(실도달 ≥ target)
  - **`fetch_daily_candles` 와 별도 함수**다 (그쪽은 memcache 5분 + single-flight + `asyncio.shield` 유지). 호출자 = `scanner._stock_master_daily_load_once` (**일봉 적재 대상 전부** 225일, `_DAILY_LOAD_VCP_BACKFILL_DAYS` — 이름의 `VCP` 는 이 깊이를 처음 요구한 전략의 흔적이고 대상은 index ∪ 자격 ∪ 보호 전체다, cycle302). 매매 hot path 무관 — 데이터 적재 한정, 매수 진입 전 영역. 가드 `tests/unit/api/test_cycle172_daily_ranged_backfill.py`
- **`inquire_stock_basics(pdno) -> StockBasics`**: KIS `CTPF1002R` — NXT 거래종목 (`cptt_trad_tr_psbl_yn`) + NXT 거래정지 (`nxt_tr_stop_yn`) + KRX 정지 + 관리종목 파싱 → `StockBasics` 반환. 파생값 `nxt_tradable = (cptt=="Y") AND (nxt_stop=="N")`. CTPF 접두사 TR_ID 는 모의/실전 동일. 캐시 `src.db.stock_master` 24h TTL. **ticker 정규화**: `_normalize_ticker()` 가 KIS `pdno` 12자리 표준코드 → KRX 6자리 단축코드 추출 (정규식 `(\d{6})$`). `stock_master` PK 정합성 보장. `docs/kis/error-codes.md` 5-3절
  - **2단 호출**: CTPF1002R → `await asyncio.sleep(0.05)` (KIS LMS chain 안전 마진) → FHKST01010100 (`kis_get_quote`). FHKST 실패는 graceful — CTPF 단독 raw 를 반환하고 `_record_graceful_failed("fhkst01010100_failed")` 카운터만 올린다(scanner summary 의 `[stock_master_basics_refresh_summary] … graceful_failed_fhkst=N` 로 가시화). **CTPF1002R 실패는 전파**한다
  - **raw merge**: `merged_raw = dict(ctpf_output)` 에 `_FHKST_MERGE_KEYS` 35키만 덮어쓴다 — 목록 밖 CTPF 키는 건드리지 않는다(`bfdy_clpr` 보존이 가드 대상). 그중 `_ZERO_VALUE_SKIP_KEYS` 15키(`acml_tr_pbmn`·`acml_vol`·`per`·`pbr`·`vol_tnrt`·`prdy_vrss_vol_rate`·`hts_frgn_ehrt`·`frgn_ntby_qty`·`w52_hgpr`·`w52_lwpr`·`d250_hgpr`·`d250_lwpr`·`eps`·`bps`·`whol_loan_rmnd_rate`)는 값이 **0 이거나 비숫자·None 이면 merge 하지 않고 `continue`** 한다 — 장전 호출의 `0` 이 전일 거래대금을 지우면 `list_by_filter(acml_tr_pbmn ≥ min_trade_amount)` 가 조용히 0건이 되어 donchian/VB/LTV 후보가 사라진다
  - ⚠️ **이 함수는 기존 DB raw 를 읽지 않는다** — 그래서 보존의 주체는 호출자 `scanner._stock_master_basics_refresh_once` 의 `{**기존, **신규}` 머지다. skip 된 키를 기존 DB 값에서 되살리는 곳이 거기 하나뿐이고, `upsert_one` 은 raw 를 통째로 교체한다
  - 가드 `tests/unit/api/test_cycle107_inquire_stock_basics_merge.py` · `test_cycle108_hts_avls.py` · `test_cycle144_graceful_visibility.py` · `test_cycle145_raw_preserve.py` · `tests/unit/engine/test_cycle176_basics_refresh_raw_merge.py` · `test_cycle176_e2e_premarket_preservation.py`

### TTL 캐시 (single-flight)

KIS 부하 + 5xx 노출 면적 축소:
- `fetch_stock_detail`: `_PRICE_CACHE_TTL=5s`, 키 = `ticker`
- `fetch_daily_candles`: `_CANDLE_CACHE_TTL=300s`(5분), 키 = `(ticker, days)` — days 별 분리. 일봉은 5분 지연 OK
- `asyncio.Lock` + `_inflight_*: dict[key, Task]` single-flight — 동시 N 호출 시 첫 호출만 KIS fetch, 나머지 task 합류
- 무효화: TTL 자동 만료 + `clear_caches()` (`_reset_daily_state` 21:30 호출 — cycle283 D3). `_cache_epoch` bump 로 진행 중 inflight 의 stale write 차단
- joiner 는 `await asyncio.shield(task)` 합류 — 자기 task cancel 시 inflight cancel 전파 차단
- **사용 범위 안전 가드**: 스캐닝/조건검사 한정. `execute_buy/execute_sell` 의 체결가/주문가 결정 경로는 절대 사용 금지 (WebSocket tick 또는 직접 호출 유지)

## 새 API 추가 절차

1. `docs/kis/{category}.md` 에서 TR_ID, URL, 파라미터 확인
2. 본 디렉토리에 함수 추가 (반드시 `kis_request()` 또는 `kis_get_quote()` 사용)
3. TR_ID 는 `settings.get_tr_id("실전TR_ID")` 사용
4. 응답 모델은 `models/` 에 pydantic 으로 정의
