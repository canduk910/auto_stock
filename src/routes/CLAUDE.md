# CLAUDE.md — src/routes/ (FastAPI 라우트)

프론트엔드에 데이터를 제공하는 REST API 엔드포인트.

## 엔드포인트 목록

| Method | URL | 파일 | 설명 |
|--------|-----|------|------|
| POST | `/api/trading/start` | trading.py | 자동매매 시작 |
| POST | `/api/trading/stop` | trading.py | 자동매매 정지 |
| POST | `/api/trading/restart` | trading.py | 자동매매 재기동 |
| POST | `/api/trading/manual-sell` | trading.py | 수동 매도 (시장가) |
| GET | `/api/trading/status` | trading.py | 현재 상태. `?include=system,holdings,orders,scan,strategies` csv로 sub-section만 슬림 응답 (미지정/`all`은 전체) |
| GET | `/api/trading/positions` | trading.py | 보유 포지션 상세만(BalanceTable 전용 분리) |
| GET | `/api/trading/orders` | trading.py | 주문 추적(pending_buys/fills/pending_cancels)만 분리 |
| GET | `/api/balance` | balance.py | 잔고 (예수금 + 보유종목, 0수량 제외) |
| GET | `/api/balance/buyable` | balance.py | 매수 가능 금액 |
| GET | `/api/history?page=&size=` | history.py | 거래 내역 (페이징, 종목명/주문번호 포함) |
| GET | `/api/history/pnl?page=&size=&strategy=&ticker=` | history.py | 매매손익 — 매수/매도 페어 1행 (가중평균). 보유 중은 open 페어 (미실현 손익은 ticker_prices 현재가 사용) |
| GET | `/api/performance/summary` | performance.py | 실적 요약 |
| GET | `/api/performance/daily` | performance.py | 일별 실적 (실현손익 기반 일별 수익률 + TWR 누적 + 외부 입출금) |
| POST | `/api/performance/recompute` | performance.py | trade_history 기반 daily_performance 전체 소급 재계산 (멱등) |
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
| GET | `/api/log-reports?days=30` | log_reports.py | 일일 로그 분석 리포트 목록 (신규순) |
| GET | `/api/log-reports/{YYYY-MM-DD}` | log_reports.py | 단일 영업일 리포트 상세 |
| POST | `/api/log-reports/run` | log_reports.py | 수동 트리거 — 즉시 분석 실행 (당일 1건만, 중복 방지) |
| GET | `/api/system/memory` | system.py | 프로세스 메모리(psutil RSS/VMS/threads/files) + (옵션) tracemalloc top 20 |
| GET | `/api/system/metrics` | system.py | 엔드포인트별 응답시간 분포 p50/p95/p99 (최근 1024개 샘플) |
| POST | `/api/system/metrics/reset` | system.py | metrics 누적 샘플 초기화 (실험 베이스라인 리셋) |
| GET | `/api/realtime/subscriptions` | realtime.py | WebSocket 구독 슬롯 사용현황 진단 (G2, 2026-05-12). `total/acked/fresh_60s/stale_60s/limit/tickers(subscribed/acked/fresh/stale, 모두 sorted)/reconnect_count/ws_connected`. KIS 측 슬롯 조회 API 미존재 → 우리 측 추적 노출 |

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
