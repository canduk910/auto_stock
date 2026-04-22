# CLAUDE.md — 프로젝트 루트

## 프로젝트 개요
KIS OpenAPI 기반 주식 자동매매시스템. FastAPI(백엔드) + React(프론트엔드) + Supabase(DB) 아키텍처.

## 빌드 & 실행

```bash
# 백엔드
pip install -r requirements.txt
uvicorn src.main:app --reload

# 프론트엔드
cd frontend && npm install && npm run dev

# 프론트엔드 빌드 확인
cd frontend && npm run build
```

## 환경 ���수
`.env` 파일 필수. `.env.example` 참고. 주�� 변수:
- `KIS_ENV`: `vts`(모의) 또는 `real`(실전)
- `KIS_APP_KEY`, `KIS_APP_SECRET`, `KIS_ACCOUNT_NO`: KIS 인증
- `SUPABASE_URL`, `SUPABASE_KEY`: DB 연결

## 핵심 규칙

### 매매 로직 수정 시 반드시 확인
- 매수 기준은 "전일종가" 대비 +29% 돌파 순간 (시가 아님)
- 상한가(+30%) 종목은 매수 제외
- 손절 기준은 "매수 체결가" 대비 -7.5% (시가 아님)
- 트레일링 스탑은 "당일 고점" 대비 -2%
- 익일 청산 갭상승 판단은 "매수 체결가" 대비 시가 +10%
- 매매 파라미터(29%, 7.5%, 10%, 2%, 25%)를 변경하면 strategy.py + risk.py + _workspace/00_leader_trading_rules.md 모두 동기화

### 코딩 컨벤션
- Python: pydantic 모델로 데이터 검증, async/await 사용
- TypeScript: 모든 API 응답은 `types/` 디렉토리의 타입 정의 사용
- API 응답: 공통 래퍼 `{ success: bool, data: T, message: str }`
- KIS API 호출: 반드시 `src/api/base.py`의 공통 래퍼를 통해 ��출 (Rate Limit 관리)

### 모의/실전 분리
- `.env`에서 `KIS_ENV`에 따라 `_REAL` / `_VTS` 접미사 인증 정보 자동 선택
- `config.py`의 `get_tr_id()`로 TR_ID 자동 변환 (실전 T→모의 V 접두사)
- 도메인 URL도 `kis_base_url` computed field로 자동 결정
- 새 API 추가 시 TR_ID 하드코딩 금지, 반드시 `settings.get_tr_id()` 사용
- 등락률 순위/현재가 시세 API(FH 접두사)는 모의/실전 동일 TR_ID

### KIS API 스펙
- `docs/kis/README.md` — 전체 API 목록 + 프로젝트 사용 API
- `docs/kis/{category}.md` — 카테고리별 상세 ���펙 (TR_ID, URL, Request/Response)
- API 구현 시 반드시 해당 스펙 파일을 먼저 읽을 것

## DB 스키마 (Supabase)
- `trade_history`: 거래 내역 (id, timestamp, ticker, trade_type, price, quantity, profit_loss, status)
- `daily_performance`: 일일 실적 (date, total_asset, daily_profit_rate)
- `system_logs`: 시스템 로그 (timestamp, log_level, message)
- status ENUM: PENDING, COMPLETED, PARTIAL, CANCELLED

## 디렉토리 역할
- `src/auth/` — KIS OAuth 인증/토큰 관리
- `src/api/` — KIS REST API 호출 (주문, 잔고, 조건검색)
- `src/realtime/` — KIS WebSocket (시세 구독, 체결통보)
- `src/engine/` — 매매 핵심 로직 (전략, 주문 엔진, 리스크, 스케줄러)
- `src/db/` — Supabase CRUD
- `src/routes/` — FastAPI 엔드포인트 (프론트엔드 연동)
- `src/models/` — Pydantic 데이터 모델
- `frontend/` — React 대시보드
