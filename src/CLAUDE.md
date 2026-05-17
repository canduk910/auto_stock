# CLAUDE.md — src/ (백엔드)

FastAPI + KIS OpenAPI + Supabase. 진실의 원천은 하위 디렉토리 CLAUDE.md.

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
realtime/websocket.py ← realtime/websocket_pool.py (사이클 7-B — 메인 세션 재사용)
realtime/handler.py ← engine/risk.py(on_tick) + engine/order_engine.py(체결통보) + engine/session.py(보드 전환)
engine/session.py ← engine/risk.py, engine/scheduler.py, strategies/* (현재 보드 query)
engine/    ← routes/trading.py (시작/정지)
db/        ← engine/, routes/
models/    ← 모든 모듈
```

## 진입점

| 영역 | 진실의 원천 |
|------|------------|
| KIS OAuth/토큰 | `src/auth/CLAUDE.md` |
| KIS REST 호출·TR_ID·Rate Limit·메트릭 | `src/api/CLAUDE.md` |
| WebSocket 시세/체결통보/H0NXMKO0 | `src/realtime/CLAUDE.md` |
| 전략·주문·리스크·스케줄러·AI자문·일일 분석 | `src/engine/CLAUDE.md` |
| Supabase CRUD/스키마/멀티스레드 정책 | `src/db/CLAUDE.md` |
| FastAPI 엔드포인트 카탈로그 | `src/routes/CLAUDE.md` |
| Pydantic 응답 모델 | `src/models/CLAUDE.md` |

## 공통 규칙 (전역)
- 모든 KIS REST는 `api/base.py::kis_request()` 경유 (Rate Limit 20/s, 자동 재시도, 토큰 갱신, 메트릭)
- TR_ID는 `settings.get_tr_id("실전TR_ID")` — 하드코딩 금지 (실전 T → 모의 V 자동 변환, FH 접두사는 동일)
- API 응답 래퍼: `models/response.py::ApiResponse` `{ success, data, message }`
- Supabase SDK는 동기 → 모든 `.execute()`는 `asyncio.to_thread()` 위임 (`src/db/CLAUDE.md` 상세)

## 새 KIS API 추가
1. `docs/kis/README.md`에서 스펙 파일 확인 → TR_ID/URL/요청·응답
2. `api/` 하위에 함수 추가 (반드시 `kis_request()` 사용)
3. `models/`에 응답 모델 추가 (pydantic)
4. 필요 시 `routes/`에 엔드포인트 추가
