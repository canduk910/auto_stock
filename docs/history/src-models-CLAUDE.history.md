> 원본: `src/models/CLAUDE.md` · 이관: 2026-10-01

정본은 [`src/models/CLAUDE.md`](../../src/models/CLAUDE.md). 이 파일은 거기서 걷어낸 원문을
**고치지 않고** 옮겨 둔 것이다(append-only). 사이클 축으로 찾으려면
[`docs/HARNESS_CHANGELOG.md`](../HARNESS_CHANGELOG.md) 로 간다.

---

## 2026-10-01 sync-docs 압축 — 정본에서 이관

정본은 코드 대조로 클래스명·필드·소비처를 다시 썼고 절 표제의 시점 꼬리(사이클·날짜)를 뺐다. 아래는 그 전 원문이다
(`response.py` 절과 「프론트엔드 연동」 절은 그대로 남아 있어 옮기지 않았다).

### 출처: 머리말

````
Pydantic 기반 데이터 모델. API 요청/응답, DB 레코드, 내부 데이터 구조 정의.
````

### 출처: 「모듈별 역할」 (order.py ~ krx_open_api.py)

````
### order.py — 주문 모델
- 매수/매도 요청 파라미터
- KIS 주문 API 응답 파싱 모델

### balance.py — 잔고 모델
- `Holding`: 보유종목 정보 (종목명, 수량, 매입가, 현재가, 손익)
- `BalanceSummary`: 계좌 요약 (예수금, 평가금, 총손익)

### trade.py — 거래 기록 모델
- `TradeStatus`: PENDING, COMPLETED, PARTIAL, CANCELLED
- `TradeRecord`: trade_history 테이블 매핑

### kis_quote_account.py — 보조 시세 계좌 모델 (사이클 7-A, 2026-05-17)
- `KisQuoteAccount`: `kis_quote_accounts` row 응답 — `id`(UUID), `label`, `app_key`, `app_secret_masked`("****1234" 형식), `kis_env`("real"/"vts"), `active`, `created_at`, `updated_at`. **app_secret 평문 필드 자체가 없음** — `from_row()` 가 항상 마스킹 변환
- `KisQuoteAccountCreate`: POST 요청 본문 — `{label, app_key, app_secret, kis_env}`. 빈 값 거부 (`field_validator` strip)
- `KisQuoteAccountUpdate`: PUT 요청 본문 — `{active?, label?}`. app_key/app_secret 수정 미지원
- `mask_secret(secret)`: 마지막 4자리만 노출 헬퍼 (8자리 미만은 `****` 로 통일 — 길이 정보 누출 차단)

### stock.py — 종목 기본정보 (Phase G, 2026-05-11)
- `StockBasics`: KIS `CTPF1002R`(주식기본조회) 응답 캐시 모델 — `ticker`, `name`, `excg_dvsn_cd`, `nxt_tradable`(파생: `cptt_trad_tr_psbl_yn=="Y" AND nxt_tr_stop_yn=="N"`), `krx_halted`(파생: `tr_stop_yn=="Y"`), `admin_item`(파생: `admn_item_yn=="Y"`), `raw`(원본 dict), `refreshed_at`
- `stock_master` 테이블(migration 015) 매핑 — NXT 거래가능 사전 판별용. 24h TTL
- 호출 경로: `src/api/condition.py::inquire_stock_basics(ticker)` → `src/db/stock_master.py::upsert_one/get/is_stale`

### recommendation.py — 20:00 AI 자문 모델
- `parameter_recommendations` 테이블 매핑. `recommended_weight` / `code_review_notes` /
  `applied_weight` / `weight_reasoning` / `backtest_summary`(JSONB) 포함
- 소비 = `engine/recommendation_engine.py` · `routes/recommendations.py` · 프론트 '전략수정 AI자문' 화면

### market_regime.py — 매크로 레짐 응답 (사이클 2, 2026-05-17)
- dkstock.cloud 응답 매핑. `regime` / `cycle_phase` / `vix` / `fear_greed` / `buffett_ratio` /
  `computed_cash_usage_ratio` / `raw_response`
- ⚠️ **레짐은 매수를 차단·축소하지 않는다**(사이클 I, 2026-08-03 게이트 제거 — 관찰 전용).
  `buy_blocked` 는 표시 전용 잔존 필드다

### system_integrations.py — 외부 통합 토글 (사이클 5, 2026-05-17)
- `KIS_MCP_ENABLED` / `DKSTOCK_REGIME_ENABLED` / `etf_regime_enabled` / `auto_regime_adjust` /
  `auto_apply` 등 Settings UI 즉시 토글의 요청·응답 모델
- `StatusExitModeRequest{sell_mode, buy_block_mode}` (cycle369) — `PUT /api/integrations/status-exit` 요청.
  두 필드 모두 `Optional[Literal["enforce", "observe", "off"]]` 라 어휘 밖 값은 422 다. 둘 다 없을 때의 422 는
  라우트가 낸다

### backtest.py — 외부 MCP 백테스트 (Phase 1~2)
- `backtest_runs` 테이블 매핑 + MCP job 요청/응답. 소비 = `engine/backtest_engine.py` · `routes/backtest.py`
- 매매 hot path 무관

### candle_chart.py — 종목 차트 응답 (cycle387)
- `GET /api/stock-chart/candles` 응답 `data` 이자 `src/api/period_chart.py::fetch_candle_chart` 의 반환형
- `CandleBar{date, open, high, low, close, volume, amount}` — `date` 는 `YYYY-MM-DD`(KRX 영업일 = KST 날짜), 숫자 6칸은
  전부 `int` 라 JSON 정수로 나간다(문자열로 나가면 프론트 수치 렌더가 깨진다 — cycle266 계열)
- `CandleChart`(16필드) = `ticker` · `name`(Optional) · `period`(`Literal["D","W","M"]`) · `years` · `adjusted` · `market` ·
  `start_date` · `end_date`(요청 구간이지 첫 봉 날짜가 아니다) · `bars` · `complete` · `incomplete_reason` · `last_bar_provisional` ·
  `dropped_bars` · `kis_calls` · `cached` · `fetched_at`(`+09:00`)
- `IncompleteReason = Literal["call_cap", "time_budget", "window_error", "no_progress"]` — 뜻은 `src/api/CLAUDE.md` 「period_chart.py」 절
- 프론트 짝 = `frontend/src/types/stock-chart.ts`(`StockChartBar` · `StockChartData`, 필드명 1:1)

### krx_open_api.py — KRX 정식 OPEN API 키 관리 (사이클 112, 2026-06-12)
- ⚠️ 이 키는 `scanner._full_universe_load_krx_primary`(20:00/07:48 전체 유니버스 적재 **주 소스**)가 쓴다.
  2026-08-08 에 "무효 키·낭비"로 오판해 껐다가 적재가 3,577 → 60종목으로 degrade 된 선례가 있다
  (루트 `CLAUDE.md` 「비활성화 시 심층 검증 의무」). **끄기 전에 소비처를 grep 하고, 끈 뒤 산출물을 실측한다**
````

---

## 2026-10-02 sync-docs 압축 2차 — 정본에서 이관

정본을 줄이면서 `src/routes/CLAUDE.md`(엔드포인트 경로·거부 경로·응답 칸의 뜻)·`src/db/CLAUDE.md`(stock_master 캐시 흐름)·
루트 `CLAUDE.md`(`nxt_tradable` 전제·비활성화 검증 의무)에 이미 있는 서술을 링크로 대체하고, 필드 나열·소비처 목록을 줄였다.
`candle_chart.py` 의 `CandleChart` 16필드 이름·프론트 타입 이름·`start_date`·`end_date` 한정은 2차 검증 지적으로 정본에 다시 남겼다
(필드명 1:1 계약을 문서로 대조하려면 이름이 있어야 한다). 아래는 그 전(1차 반영본) 원문이다(`response.py` 절은 그대로라 옮기지 않았다).

### 출처: 머리말

````
Pydantic 모델 — API 요청·응답, DB 행 매핑, 내부 데이터 구조. 「소비」 = 그 모델을 import 하는 `src/` 모듈이다.
````

### 출처: 「모듈별 역할」 (order.py)

````
### order.py — 주문
- `OrderSide`(`BUY`/`SELL`) · `CancelType`(`01` 정정 / `02` 취소) · `OrderResult{order_no, order_time, krx_org_no}`(KIS 응답 `ODNO`·`ORD_TMD`·`KRX_FWDG_ORD_ORGNO`)
- `OrderDivision` = KIS `ORD_DVSN` 다섯 값 — `LIMIT="00"` · `MARKET="01"` · `KRX_AFTER_LIMIT="41"`(KRX 애프터마켓 지정가, 폴백) · `KRX_AFTER_BEST="44"`(애프터마켓 최유리지정가, 1차) · `NXT_GTP_LIMIT="27"`(NXT 프리마켓 GTP 지정가, 매수 전용). 나머지 코드를 넣지 않는 이유 = 클래스 주석
- `OrderRequest` 는 소비처가 없다
````

### 출처: 「모듈별 역할」 (balance.py ~ krx_open_api.py)

````
### balance.py — 잔고
- `StockHolding`: 보유종목 1행(종목·수량·매도가능수량·평균단가·매입·평가·손익) + `stock_master` 조인 3칸 `nxt_tradable`·`krx_halted`·`excg_dvsn_cd`(미캐시·조회 예외면 `None` — 프론트는 「확인중」)
- `AccountSummary`: 계좌 요약(예수금·평가금·순자산·총손익). `net_asset`(= KIS `nass_amt`)이 `_boot()` 의 전략 자금 배분 기준이다
- `BuyableInfo`: 주문가능(`cash_available`·`max_buy_amount`·`max_buy_quantity`)

### trade.py — 거래 기록
- `TradeType`(`BUY`/`SELL`) · `TradeStatus`(`PENDING`/`COMPLETED`/`PARTIAL`/`CANCELLED`)
- `TradeRecord`: `trade_history` 행 매핑. `strategy` 기본값이 `"momentum"` 이라 전략을 넘기지 않은 INSERT 는 momentum 으로 귀속된다

### kis_quote_account.py — 보조 시세 계좌
- `KisQuoteAccount`: `kis_quote_accounts` 행 응답 — `id`(UUID)·`label`·`app_key`·`app_secret_masked`("****1234")·`kis_env`("real"/"vts")·`active`·`created_at`·`updated_at`. **`app_secret` 평문 필드가 없다** — `from_row()` 가 항상 마스킹한다
- `KisQuoteAccountCreate`: POST 본문 `{label, app_key, app_secret, kis_env}`. 빈 값은 `field_validator`(strip)가 거부한다
- `KisQuoteAccountUpdate`: PUT(`/api/integrations/quote-accounts/{id}`) 본문 `{active?, label?}`. `app_key`·`app_secret` 은 수정하지 않는다(삭제 후 재등록)
- `mask_secret(secret)`: 마지막 4자리만 노출. 8자리 미만·빈 값은 `****`(길이 정보 누출 차단). `krx_open_api.py` 에 같은 규칙의 함수가 따로 있다

### stock.py — 종목 기본정보
- `StockBasics`: KIS `CTPF1002R`(주식기본조회) 캐시 모델 — `ticker` · `name` · `excg_dvsn_cd` · `nxt_tradable`(파생: `cptt_trad_tr_psbl_yn=="Y" AND nxt_tr_stop_yn=="N"`) · `krx_halted`(파생: `tr_stop_yn=="Y"`) · `admin_item`(파생: `admn_item_yn=="Y"`) · `raw`(원본 dict)
- `nxt_tradable` = 「KRX 에 더해 NXT 에서도 거래되나」. NXT 는 자체 상장이 없어 `False` 는 「KRX 전용」이지 「살 수 없다」가 아니다. 주문 거래소 선택에만 쓰고 매수 여부 판단에는 쓰지 않는다(루트 `CLAUDE.md` 「핵심 안전 규칙」 의 `nxt_tradable` 용도 항목)
- `stock_master` 테이블(migration 015) 매핑 — NXT 거래가능 사전 판별용. 24h TTL 의 기준 `refreshed_at` 은 모델이 아니라 테이블 열이다(`db/stock_master.py::is_stale(max_age_hours=24)`)
- 호출 경로: `api/condition.py::inquire_stock_basics(pdno)` → `db/stock_master.py::upsert_one/get/is_stale`

### recommendation.py — 20:00 AI 자문
- `ApplyRequest{keys, apply_weight}` = `POST /api/recommendations/{id}/apply` 본문. `apply_weight=True` 면 `strategy_config.weight` 를 `recommended_weight` 로 바꾸고, 그 값이 null 이면 `success=false` 로 거부한다. 거부 경로는 둘 더 있다 — 증액으로 Σ>1 이 되면 쓰기 전에 전체를 거부한다(`[weight_sum_violation]`). 보유 중인 전략의 비중 0 은 비중만 거부하고 파라미터는 적용한다(`[weight_zero_guard]` — 루트 `CLAUDE.md` 「핵심 안전 규칙」 의 보유 전략 끄기 금지 항목). 소비 = `routes/recommendations.py`
- `RecommendationItem` = `parameter_recommendations` 행 모양(`status` 5종 `pending`/`applied`/`rejected`/`partial`/`expired`). 소비처가 없다 — 라우트는 DB 행 dict 를 그대로 낸다

### market_regime.py — 매크로 레짐
- 출처 = 우리 `macro` 컨테이너(`services/macro_client.py`)
- `MarketRegimeCurrent` = `GET /api/market-regime/current` 응답 — 레짐 칸(`regime`·`regime_desc`·`cycle_phase`·`vix`·`fear_greed_score`·`buffett_ratio`·`cash_min`·`buy_blocked`·`block_reason`) + `auto_regime_adjust`·`cash_usage_ratio` + `enabled`(DB `system_config.dkstock_regime_enabled` 우선 / `.env` fallback) + 지수ETF 스테이지 관찰 `etf_*` 4칸
- `MarketRegimeSnapshotItem` = `GET /api/market-regime/history` 행(`market_regime_snapshots`, `computed_cash_usage_ratio` 포함). `raw_response` 는 DB 열이고 모델에는 없다
- `AutoAdjustRequest{enabled}` = `PUT /api/market-regime/auto-adjust`
- ⚠️ **레짐은 매수를 차단·축소하지 않는다**(관찰 전용 — 루트 `CLAUDE.md` 「외부 통합」). `/current` 의 `buy_blocked` 는 항상 `False` 이고 `block_reason` 은 관찰용 경보 사유다

### system_integrations.py — 외부 통합 토글 · 매수 가드(표시 전용) · 종목상태 킬스위치
- `IntegrationToggleStatus{enabled, source: "db"|"env", env_value, db_value}` · `IntegrationToggleRequest{enabled}` — `/api/integrations/{dkstock-regime,kis-mcp,auto-regime-adjust,etf-regime}` GET/PUT 공통. `enabled` 출처는 경로마다 다르다 — `dkstock-regime`·`kis-mcp` = DB 우선 / `.env` fallback · `auto-regime-adjust` = DB(판독 불가는 `db/system_config.py::get_auto_regime_adjust` 가 `False` 로 읽는다. 응답의 `env_value=True` 는 고정값이다) · `etf-regime` = DB 전용(키 부재·조회 실패 `False`, `source` 는 항상 `"db"`)
- `BuyBlockMode`(`OFF`/`WARN`/`SOFT`/`HARD`) · `BuyBlockThresholdsModel` · `BuyBlockStatusResponse` · `BuyBlockUpdateRequest`(범위 밖 422 — vix [10, 50] · fg_high [50, 100] · fg_low [0, 50]) — `GET/PUT /api/integrations/buy-block`. **표시 전용**이다(레짐은 매수를 막지 않는다)
- `AutoApplyRequest{enabled}` · `AutoApplyStatus{enabled}` — `GET/PUT /api/integrations/auto-apply`(AI 자문 자동 적용 토글)
- `StatusExitModeRequest{sell_mode, buy_block_mode}`(cycle369) — `PUT /api/integrations/status-exit` 요청. 두 필드 모두 `Optional[StatusExitMode]`(= `Literal["enforce", "observe", "off"]`)라 어휘 밖 값은 422 다. 둘 다 없을 때의 422 는 라우트가 낸다. 이 `buy_block_mode` 는 종목상태(관리·단기과열) 매수 차단이고 위 레짐 `BuyBlockMode` 와 다른 축이다

### backtest.py — 외부 MCP 백테스트
- `McpHealthResponse{enabled, reachable, tools_count, error}` = `GET /api/backtest/mcp/health`. 소비 = `routes/backtest.py`
- `BacktestMetrics` = MCP 결과 8 메트릭(`COMPARE_METRIC_KEYS` 와 같은 8키, 누락은 `None`). 소비 = `engine/backtest_engine.py`
- `compute_metric_diff(current, recommended)` = 메트릭별 `recommended − current`(어느 쪽이든 숫자가 아니면 그 키를 뺀다). 소비 = `engine/backtest_orchestration.py`
- `BacktestRun` · `BacktestSummary` · `BacktestSummaryByStrategy` = `backtest_runs` 행과 `parameter_recommendations.backtest_summary` JSONB 의 모양을 적은 모델이다. 소비처가 없다
- 매매 hot path 무관

### candle_chart.py — 종목 차트 응답
- `GET /api/stock-chart/candles` 응답 `data` 이자 `src/api/period_chart.py::fetch_candle_chart` 의 반환형
- `CandleBar{date, open, high, low, close, volume, amount}` — `date` 는 `YYYY-MM-DD`(KRX 영업일 = KST 날짜), 숫자 6칸은
  전부 `int` 라 JSON 정수로 나간다(문자열로 나가면 프론트 수치 렌더가 깨진다 — cycle266 계열)
- `CandleChart`(16필드) = `ticker` · `name`(Optional) · `period`(`Literal["D","W","M"]`) · `years` · `adjusted` · `market` ·
  `start_date` · `end_date`(요청 구간이지 첫 봉 날짜가 아니다) · `bars` · `complete` · `incomplete_reason` · `last_bar_provisional` ·
  `dropped_bars` · `kis_calls` · `cached` · `fetched_at`(`+09:00`)
- `IncompleteReason = Literal["call_cap", "time_budget", "window_error", "no_progress"]` — 뜻은 `src/api/CLAUDE.md` 「period_chart.py」 절
- 프론트 짝 = `frontend/src/types/stock-chart.ts`(`StockChartBar` · `StockChartData`, 필드명 1:1)

### krx_open_api.py — KRX 정식 OPEN API 키 관리
- `system_config` 3키(`krx_open_api_key`·`krx_open_api_base_url`·`krx_open_api_enabled`) 모델 — `KrxOpenApiConfig`(평문 키 포함, `db/system_config.py` → `api/krx.py` · `routes/system_integrations.py::_build_krx_open_api_status`(마스킹 직전) 내부 전용 — 응답·로그 노출 금지) · `KrxOpenApiStatus`(`GET /api/integrations/krx-open-api` 응답, `key_masked`) · `KrxOpenApiUpdateRequest`(PUT 부분 갱신)
- ⚠️ 이 키는 전체 유니버스 적재의 **주 소스** `scanner._full_universe_load_krx_primary` 가 쓴다. `krx_open_api_enabled=false` 면 적재가 KIS 폴백으로 밀린다. **끄기 전에 소비처를 grep 하고, 끈 뒤 산출물을 실측한다**(루트 `CLAUDE.md` 「비활성화 시 심층 검증 의무」)
````

### 출처: 「프론트엔드 연동」

````
## 프론트엔드 연동
- 이 모델의 필드명 = FastAPI 응답의 JSON 키 = 프론트 TypeScript 타입의 속성명
- 필드명 변경 시 `frontend/src/types/`의 TypeScript 타입도 반드시 동기화
````
