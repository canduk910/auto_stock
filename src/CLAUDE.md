# CLAUDE.md — src/ (백엔드)

FastAPI + KIS OpenAPI + AWS RDS PostgreSQL (asyncpg). 진실의 원천은 하위 디렉토리 CLAUDE.md.

## 실행
```bash
uvicorn src.main:app --reload     # 개발 (단일 워커 필수, --workers 금지)
python -m src.main                # 직접 실행
```

## 모듈 의존 관계
```
config.py ← 모든 모듈 (settings)
auth/      ← api/base.py, realtime/websocket.py
api/base.py ← api/order, balance, condition
api/       ← engine/, routes/
realtime/websocket.py ← realtime/websocket_pool.py (메인 세션 재사용)
realtime/handler.py ← engine/risk.py(on_tick) + engine/order_engine.py(체결통보) + engine/session.py(보드 전환)
engine/session.py ← engine/risk.py, engine/scheduler.py, strategies/* (현재 보드 query)
engine/    ← routes/trading.py (시작/정지)
db/pg.py (asyncpg 풀) ← 전 db 모듈 + engine/scheduler·boot_manager·log_analysis_engine + routes
db/        ← engine/, routes/
models/    ← 모든 모듈
middleware/api_auth.py ← main.py (최외곽 미들웨어 — MetricsMiddleware 보다 바깥)
```

> **예정 (cycle279 프로세스 분리 1단계, 코드 아직 없음)** — `engine/llm_buy_gate` 가
> `db/llm_buy_evaluations` 에 요청 행을 남기면 별도 프로세스 `llm_worker` 가 그 행을 선점해 채운다.
> 위 블록의 `←`(import 방향)가 아니라 DB 를 거치는 데이터 흐름이다. 워커는 `api/`·`auth/`·`realtime/` 을
> import 하지 않는다. 상세 = `docs/architecture.md` 15.2

## 진입점

| 영역 | 진실의 원천 |
|------|------------|
| KIS OAuth/토큰 | `src/auth/CLAUDE.md` |
| KIS REST 호출·TR_ID·Rate Limit·메트릭 | `src/api/CLAUDE.md` |
| WebSocket 시세/체결통보/H0NXMKO0 | `src/realtime/CLAUDE.md` |
| 전략·주문·리스크·스케줄러·AI자문·일일 분석 | `src/engine/CLAUDE.md` |
| RDS(asyncpg) CRUD/스키마/계약 패턴 | `src/db/CLAUDE.md` |
| FastAPI 엔드포인트 카탈로그 | `src/routes/CLAUDE.md` |
| Pydantic 응답 모델 | `src/models/CLAUDE.md` |
| API 인증(`X-API-Key`)·리포터 스코프 | `src/middleware/api_auth.py` docstring + 루트 `CLAUDE.md`(핵심 안전 규칙 · 환경 변수) — **전용 CLAUDE.md 없음** |
| 외부 서비스 클라이언트(백테스트 MCP·매크로) | `src/services/` + 루트 `CLAUDE.md`(외부 통합) — **전용 CLAUDE.md 없음** |

## 공통 규칙 (전역)
- 모든 KIS REST는 `api/base.py::kis_request()` 경유 (Rate Limit 20/s, 자동 재시도, 토큰 갱신, 메트릭)
- TR_ID는 `settings.get_tr_id("실전TR_ID")` — 하드코딩 금지 (실전 T → 모의 V 자동 변환, FH 접두사는 동일)
- API 응답 래퍼: `models/response.py::ApiResponse` `{ success, data, message }`
- **API 인증은 조용히 꺼지지 않는다** — `middleware/api_auth.py::ApiAuthMiddleware` 가 `/health` 를 뺀 전 경로를
  `X-API-Key` 로 지킨다. 키 미설정·빈 문자열·비교 예외는 전부 **401(fail-closed)**. 상세·금기는 루트 `CLAUDE.md`
- DB 접근은 `db/pg.py` (asyncpg) 네이티브 async — `pg.fetch`/`pg.execute` 경유 (`src/db/CLAUDE.md` 상세). `src/db/supabase.py` 는 롤백용 병존(미사용)

## 새 KIS API 추가
1. `docs/kis/README.md`에서 스펙 파일 확인 → TR_ID/URL/요청·응답
2. `api/` 하위에 함수 추가 (반드시 `kis_request()` 사용)
3. `models/`에 응답 모델 추가 (pydantic)
4. 필요 시 `routes/`에 엔드포인트 추가
