# CLAUDE.md — src/routes/ (FastAPI 라우트)

프론트엔드에 데이터를 제공하는 REST API 엔드포인트.

## 엔드포인트 목록

| Method | URL | 파일 | 설명 |
|--------|-----|------|------|
| POST | `/api/trading/start` | trading.py | 자동매매 시작 |
| POST | `/api/trading/stop` | trading.py | 자동매매 정지 |
| POST | `/api/trading/restart` | trading.py | 자동매매 재기동 |
| POST | `/api/trading/manual-sell` | trading.py | 수동 매도 (시장가) |
| GET | `/api/trading/status` | trading.py | 현재 상태 |
| GET | `/api/balance` | balance.py | 잔고 (예수금 + 보유종목, 0수량 제외) |
| GET | `/api/balance/buyable` | balance.py | 매수 가능 금액 |
| GET | `/api/history?page=&size=` | history.py | 거래 내역 (페이징, 종목명/주문번호 포함) |
| GET | `/api/performance/summary` | performance.py | 실적 요약 |
| GET | `/api/performance/daily` | performance.py | 일별 실적 (실현손익 기반 일별 수익률 + TWR 누적 + 외부 입출금) |
| GET | `/api/strategies` | strategies.py | 전략 목록 + 비중 + 상태 + 타겟가 |
| PUT | `/api/strategies/weights` | strategies.py | 전략별 비중 수정 (매수금액 하한선 검증) |
| PUT | `/api/strategies/{id}/params` | strategies.py | 전략 파라미터 수정 (DB 영속화) |
| GET | `/api/strategies/system/auto-start` | strategies.py | 자동 매매 설정 조회 |
| PUT | `/api/strategies/system/auto-start` | strategies.py | 자동 매매 설정 변경 |
| GET | `/api/logs` | logs.py | 시스템 로그 조회 |
| GET | `/api/recommendations` | recommendations.py | 전략수정 AI자문 목록 (최근 30일, 신규+이력 통합) |
| GET | `/api/recommendations/{id}` | recommendations.py | 단일 자문 상세 |
| POST | `/api/recommendations/{id}/apply` | recommendations.py | 선택한 키만 전략 파라미터에 적용 (status: pending/partial → applied/partial) |
| POST | `/api/recommendations/{id}/reject` | recommendations.py | 자문 전체 거절 (status → rejected) |

## 응답 형식
모든 응답은 `models/response.py`의 `ApiResponse` 래퍼 사용:
```json
{ "success": true, "data": { ... }, "message": "ok" }
```

## 프론트엔드 연동
- 프론트가 사용하는 TypeScript 타입: `frontend/src/types/`
- 응답 필드명 변경 시 반드시 프론트 타입도 동기화할 것
- 페이징 응답에 `total`, `total_pages` 필드 포함 필수
- history, performance API에 `strategy` 쿼리 파라미터 지원 (전략별 필터)
