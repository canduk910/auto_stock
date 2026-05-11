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

### stock.py — 종목 기본정보 (Phase G, 2026-05-11)
- `StockBasics`: KIS `CTPF1002R`(주식기본조회) 응답 캐시 모델 — `ticker`, `name`, `excg_dvsn_cd`, `nxt_tradable`(파생: `cptt_trad_tr_psbl_yn=="Y" AND nxt_tr_stop_yn=="N"`), `krx_halted`(파생: `tr_stop_yn=="Y"`), `admin_item`(파생: `admn_item_yn=="Y"`), `raw`(원본 dict), `refreshed_at`
- `stock_master` 테이블(migration 015) 매핑 — NXT 거래가능 사전 판별용. 24h TTL
- 호출 경로: `src/api/condition.py::inquire_stock_basics(ticker)` → `src/db/stock_master.py::upsert_one/get/is_stale`

## 프론트엔드 연동
- 이 모델의 필드명 = FastAPI 응답의 JSON 키 = 프론트 TypeScript 타입의 속성명
- 필드명 변경 시 `frontend/src/types/`의 TypeScript 타입도 반드시 동기화
