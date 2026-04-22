# CLAUDE.md — src/routes/ (FastAPI 라우트)

프론트엔드에 데이터를 제공하는 REST API 엔드포인트.

## 엔드포인트 목록

| Method | URL | 파일 | 설명 |
|--------|-----|------|------|
| POST | `/api/trading/start` | trading.py | 자동매매 시작 |
| POST | `/api/trading/stop` | trading.py | 자동매매 정지 |
| GET | `/api/trading/status` | trading.py | 현재 상태 |
| GET | `/api/balance` | balance.py | 잔고 (예수금 + 보유종목) |
| GET | `/api/balance/buyable` | balance.py | 매수 가능 금액 |
| GET | `/api/history?page=&size=` | history.py | 거래 내역 (페이징) |
| GET | `/api/performance/summary` | performance.py | 실적 요약 |
| GET | `/api/performance/daily` | performance.py | 일별 실적 |
| GET | `/api/performance/monthly` | performance.py | 월별 실적 |

## 응답 형식
모든 응답은 `models/response.py`의 `ApiResponse` 래퍼 사용:
```json
{ "success": true, "data": { ... }, "message": "ok" }
```

## 프론트엔드 연동
- 프론트가 사용하는 TypeScript 타입: `frontend/src/types/`
- 응답 필드명 변경 시 반드시 프론트 타입도 동기화할 것
- 페이징 응답에 `total`, `total_pages` 필드 포함 필수
