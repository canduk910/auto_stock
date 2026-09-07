# CLAUDE.md — src/models/ (데이터 모델)

Pydantic 기반 데이터 모델. API 요청/응답, DB 레코드, 내부 데이터 구조 정의.

## 모듈별 역할

### response.py — API 공통 응답
- `ApiResponse`: `{ success: bool, data: Any, message: str }` — 모든 FastAPI 응답의 래퍼

### order.py — 주문 모델
- 매수/매도 요청 파라미터
- KIS 주문 API 응답 파싱 모델

### balance.py — 잔고 모델
- `Holding`: 보유종목 정보 (종목명, 수량, 매입가, 현재가, 손익)
- `BalanceSummary`: 계좌 요약 (예수��, 평가금, 총손익)

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

### backtest.py — 외부 MCP 백테스트 (Phase 1~2)
- `backtest_runs` 테이블 매핑 + MCP job 요청/응답. 소비 = `engine/backtest_engine.py` · `routes/backtest.py`
- 매매 hot path 무관

### krx_open_api.py — KRX 정식 OPEN API 키 관리 (사이클 112, 2026-06-12)
- ⚠️ 이 키는 `scanner._full_universe_load_krx_primary`(20:00/07:48 전체 유니버스 적재 **주 소스**)가 쓴다.
  2026-08-08 에 "무효 키·낭비"로 오판해 껐다가 적재가 3,577 → 60종목으로 degrade 된 선례가 있다
  (루트 `CLAUDE.md` 「비활성화 시 심층 검증 의무」). **끄기 전에 소비처를 grep 하고, 끈 뒤 산출물을 실측한다**

## 프론트엔드 연동
- 이 모델의 필드명 = FastAPI 응답의 JSON 키 = 프론트 TypeScript 타입의 속성명
- 필드명 변경 시 `frontend/src/types/`의 TypeScript 타입도 반드시 동기화
