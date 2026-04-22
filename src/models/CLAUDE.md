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

## 프론트엔드 연동
- 이 모델의 필드명 = FastAPI 응답의 JSON 키 = 프론트 TypeScript 타입의 속성명
- 필드명 변경 시 `frontend/src/types/`의 TypeScript 타입도 반드시 동기화
