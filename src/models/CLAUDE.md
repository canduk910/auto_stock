# CLAUDE.md — src/models/ (데이터 모델)

> 이력: [`docs/history/src-models-CLAUDE.history.md`](../../docs/history/src-models-CLAUDE.history.md)

Pydantic 모델 — API 요청·응답, DB 행 매핑, 내부 구조. 엔드포인트 동작(거부·422·DB 실패)과 응답 칸의 뜻은 `src/routes/CLAUDE.md` 가 정본이다. 「소비처 없음」 = `src/` 어디도 import 하지 않는다.

## 모듈별 역할

### response.py — API 공통 응답
- `ApiResponse`: `{ success: bool, data: Any, message: str }` — 모든 FastAPI 응답의 래퍼

### order.py — 주문
- `OrderSide`(`BUY`/`SELL`) · `CancelType`(`01` 정정 / `02` 취소) · `OrderResult{order_no, order_time, krx_org_no}`(KIS `ODNO`·`ORD_TMD`·`KRX_FWDG_ORD_ORGNO`) · `OrderRequest`(소비처 없음)
- `OrderDivision`(KIS `ORD_DVSN`) = `LIMIT="00"` · `MARKET="01"` · `KRX_AFTER_LIMIT="41"`(애프터 지정가, 폴백) · `KRX_AFTER_BEST="44"`(애프터 최유리지정가, 1차) · `NXT_GTP_LIMIT="27"`(NXT 프리마켓 GTP 지정가, 매수 전용). 다른 코드를 넣지 않는 이유 = 클래스 주석

### balance.py — 잔고
- `StockHolding` = 보유 1행 + `stock_master` 조인 `nxt_tradable`·`krx_halted`·`excg_dvsn_cd`(미캐시·조회 예외 = `None`, 프론트 「확인중」)
- `AccountSummary.net_asset`(KIS `nass_amt`) = `_boot()` 전략 자금 배분 기준 · `BuyableInfo` = `cash_available`·`max_buy_amount`·`max_buy_quantity`

### trade.py — 거래 기록
- `TradeType`(`BUY`/`SELL`) · `TradeStatus`(`PENDING`/`COMPLETED`/`PARTIAL`/`CANCELLED`) · `TradeRecord` = `trade_history` 행
- ⚠️ `TradeRecord.strategy` 기본값이 `"momentum"` 이다 — 전략을 넘기지 않은 INSERT 는 momentum 으로 귀속된다

### kis_quote_account.py — 보조 시세 계좌
- `KisQuoteAccount` = `kis_quote_accounts` 행 응답. **`app_secret` 평문 필드가 없다** — `from_row()` 가 항상 `app_secret_masked` 로 바꾼다
- `KisQuoteAccountCreate{label, app_key, app_secret, kis_env}`(빈 값은 `field_validator` strip 으로 거부) · `KisQuoteAccountUpdate{active?, label?}`(`app_key`·`app_secret` 수정 불가)
- `mask_secret(secret)` = 마지막 4자리만(`****1234`), 8자리 미만·빈 값은 `****`(길이 누출 차단). `krx_open_api.py` 에 같은 규칙의 함수가 따로 있다

### stock.py — 종목 기본정보
- `StockBasics` = KIS `CTPF1002R` 캐시(`stock_master`) — `ticker`·`name`·`excg_dvsn_cd`·`raw` + 파생 `nxt_tradable`(`cptt_trad_tr_psbl_yn=="Y" AND nxt_tr_stop_yn=="N"`)·`krx_halted`(`tr_stop_yn=="Y"`)·`admin_item`(`admn_item_yn=="Y"`)
- `nxt_tradable=False` 는 「KRX 전용」이지 「살 수 없다」가 아니다 — 주문 거래소 선택에만 쓰고 매수 여부 판단에는 쓰지 않는다(루트 「핵심 안전 규칙」)
- 24h TTL 의 `refreshed_at` 은 모델이 아니라 테이블 열이다. 캐시 흐름 = `src/db/CLAUDE.md` 「stock_master.py」 절

### recommendation.py — 20:00 AI 자문
- `ApplyRequest{keys, apply_weight}` = `POST /api/recommendations/{id}/apply` 본문. 거부 경로(`recommended_weight` null · `[weight_sum_violation]` · `[weight_zero_guard]`) = routes 「`POST /api/recommendations/{id}/apply` — AI 자문 적용」 절
- `RecommendationItem`(`parameter_recommendations` 행, `status` = `pending`/`applied`/`rejected`/`partial`/`expired`) — 소비처 없음(라우트는 DB 행 dict 를 낸다)

### market_regime.py — 매크로 레짐
- 출처 = 우리 `macro` 컨테이너. 레짐은 관찰 전용이라 `/current` 의 `buy_blocked` 는 항상 `False` 다(루트 「외부 통합」)
- `MarketRegimeCurrent`(`/current`) — 레짐 칸(`fear_greed_score` 등) + `enabled`(DB `system_config.dkstock_regime_enabled` 우선 / `.env` fallback) + `etf_*` 4칸 · `MarketRegimeSnapshotItem`(`/history`, `raw_response` 는 DB 열에만) · `AutoAdjustRequest{enabled}`

### system_integrations.py — 외부 통합 토글 · 매수 가드(표시 전용) · 종목상태 킬스위치
- `IntegrationToggleStatus{enabled, source, env_value, db_value}` · `IntegrationToggleRequest{enabled}` — `/api/integrations/{dkstock-regime,kis-mcp,auto-regime-adjust,etf-regime}` 공통. `enabled` 출처:
  - `dkstock-regime`·`kis-mcp` = DB 우선 / `.env` fallback
  - `auto-regime-adjust` = DB(판독 불가 = `False`). 응답 `env_value=True` 는 고정값
  - `etf-regime` = DB 전용(키 부재·조회 실패 = `False`, `source` 는 항상 `"db"`)
- `BuyBlockMode`(`OFF`/`WARN`/`SOFT`/`HARD`) · `BuyBlockThresholdsModel` · `BuyBlockStatusResponse` · `BuyBlockUpdateRequest`(범위 밖 422 — vix [10, 50] · fg_high [50, 100] · fg_low [0, 50])
- `AutoApplyRequest{enabled}` · `AutoApplyStatus{enabled}` — AI 자문 자동 적용 토글
- `StatusExitModeRequest{sell_mode, buy_block_mode}`(cycle369) — 두 필드 `Optional[StatusExitMode]`(= `Literal["enforce", "observe", "off"]`)라 어휘 밖은 422(둘 다 없을 때의 422 는 라우트). 이 `buy_block_mode` 는 종목상태(관리·단기과열) 매수 차단으로 레짐 `BuyBlockMode` 와 다른 축이다

### backtest.py — 외부 MCP 백테스트
- `McpHealthResponse{enabled, reachable, tools_count, error}` · `BacktestMetrics`(8 메트릭 = `COMPARE_METRIC_KEYS`, 누락 `None`) · `compute_metric_diff(current, recommended)`(메트릭별 `recommended − current`, 어느 쪽이든 숫자가 아니면 그 키를 뺀다)
- `BacktestRun` · `BacktestSummary` · `BacktestSummaryByStrategy` — 소비처 없음. 매매 hot path 무관

### candle_chart.py — 종목 차트 응답
- `GET /api/stock-chart/candles` 의 `data` = `api/period_chart.py::fetch_candle_chart` 반환형. 프론트 짝 = `frontend/src/types/stock-chart.ts`(`StockChartBar` · `StockChartData`, 필드명 1:1)
- `CandleBar{date, open, high, low, close, volume, amount}` — `date` = `YYYY-MM-DD`(KRX 영업일 = KST 날짜), 숫자 6칸은 `int`(문자열이면 프론트 수치 렌더가 깨진다)
- `CandleChart`(16필드) = `ticker` · `name`(Optional) · `period`(`Literal["D","W","M"]`) · `years` · `adjusted` · `market` · `start_date` · `end_date` · `bars` · `complete` · `incomplete_reason` · `last_bar_provisional` · `dropped_bars` · `kis_calls` · `cached` · `fetched_at`(`+09:00`)
- `start_date`·`end_date` 는 요청 구간이지 첫·끝 봉 날짜가 아니다 — 상장이 늦거나 수집이 잘리면 첫 봉이 `start_date` 보다 늦다
- `incomplete_reason` = `IncompleteReason`(`call_cap`·`time_budget`·`window_error`·`no_progress`) — 뜻 = `src/api/CLAUDE.md` 「period_chart.py」 절

### krx_open_api.py — KRX 정식 OPEN API 키 관리
- `KrxOpenApiConfig` = `system_config` 3키(`krx_open_api_key`·`krx_open_api_base_url`·`krx_open_api_enabled`). 평문 키를 담아 `db/system_config.py` → `api/krx.py` · `_build_krx_open_api_status`(마스킹 직전) 안에서만 쓴다 — 응답·로그에 내지 않는다. `KrxOpenApiStatus`(`key_masked`) · `KrxOpenApiUpdateRequest`(부분 갱신)
- ⚠️ 실측 없이 끄지 않는다 — `krx_open_api_enabled=false` 면 유니버스 적재 주 소스 `scanner._full_universe_load_krx_primary` 가 KIS 폴백으로 밀린다(루트 「비활성화 시 심층 검증 의무」)

## 프론트엔드 연동
- 필드명 = FastAPI 응답 JSON 키 = 프론트 TypeScript 타입 속성명. 바꾸면 `frontend/src/types/` 도 반드시 같이 바꾼다
