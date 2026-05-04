# CLAUDE.md — 프로젝트 루트

## 프로젝트 개요
KIS OpenAPI 기반 주식 자동매매시스템. 다중 전략 아키텍처.
FastAPI(백엔드) + React(프론트엔드) + Supabase(DB).

## 빌드 & 실행

### Docker Compose (권장)
```bash
# 개발 환경 (hot-reload, 볼륨 마운트)
docker compose up --build

# 프로덕션 환경 (Nginx + 최적화 빌드)
docker compose -f docker-compose.prod.yml up --build -d
```
- 개발: 프론트 `http://localhost:3000`, 백엔드 `http://localhost:8002`
- 프로덕션: `http://localhost:80` (Nginx가 정적파일 + API 프록시 통합)

### 로컬 직접 실행
```bash
# 백엔드
pip install -r requirements.txt
uvicorn src.main:app --host 0.0.0.0 --port 8001 --reload

# 프론트엔드
cd frontend && npm install && npm run dev

# 프론트엔드 빌드 확인
cd frontend && npm run build
```

## 환경 변수
`.env` 파일 필수. `.env.example` 참고.
- `KIS_ENV`: `vts`(모의) 또는 `real`(실전)
- `KIS_APP_KEY_REAL/VTS`, `KIS_APP_SECRET_REAL/VTS`, `KIS_ACCOUNT_NO_REAL/VTS`: KIS 인증 (환경별 분리)
- `KIS_HTS_ID`: 실전 체결통보(H0STCNI0) 구독에 필요한 HTS ID
- `SUPABASE_URL`, `SUPABASE_KEY`: DB 연결
- `AUTO_START`: `true`이면 서버 기동 시 자동 매매 시작 (DB `system_config.auto_start`가 우선, 매일 시작 전 DB 재확인)

## 다중 전략 아키텍처

### 전략 구성
- **상한가 모멘텀** (`momentum`): 전일종가 대비 +29% 돌파 매수, -7.5% 손절, 익일 청산
- **변동성 돌파** (`volatility_breakout`): 노이즈 비율 기반 K값 → Target_Price 돌파 매수, -3% 손절, 15:20 강제 청산
- **롱테일 변동성 돌파** (`long_tail_volatility`): 변동성 돌파 방식 조기 진입 + 상한가 도달 시 익일 청산 모드 전환(롱테일 추구). 당일 손절 -3%, 상한가 모드 손절 -5%, 15:20 강제 청산(상한가 미도달 종목만)

### 핵심 파일 구조
```
src/engine/
├── strategy_base.py       # StrategyBase 추상 클래스, Signal, Position, StrategyState
├── strategy_registry.py   # StrategyRegistry (전략 등록/비중/중복 방지)
├── strategies/
│   ├── momentum.py        # 상한가 모멘텀 전략
│   ├── volatility_breakout.py  # 변동성 돌파 전략
│   └── long_tail_volatility.py # 롱테일 변동성 돌파 전략 (VB + 상한가 모멘텀 합성)
├── risk.py               # RiskManager (registry 순회, 전략별 신호 체크)
├── order_engine.py        # OrderEngine (strategy_id 태깅, 전략별 포지션)
├── scheduler.py           # TradingScheduler (registry 기반)
└── scanner.py             # 종목 스캔 (모멘텀 + 돌파 전략 공용)
```

### 새 전략 추가 방법
1. `src/engine/strategies/` 에 StrategyBase 서브클래스 작성
2. `src/engine/scheduler.py` 의 `__init__`에서 `registry.register()` 호출
3. 필요 시 스캔 로직 추가 (scanner.py)

### 전략별 자금 관리
- 프론트 Settings 페이지에서 비중 조절 → `PUT /api/strategies/weights`
- StrategyRegistry.allocate_funds()로 총 자산을 비중에 따라 분배
- 각 전략은 할당된 자금 내에서만 매매
- **`position_ratio`는 전략 할당 자금 기준** (순자산 × 전략비중 × position_ratio = 종목당 매수금액)
- Settings 페이지에서 예상 종목당 매수 금액 표시
- 전략 간 동일 종목 중복 매수 방지 (registry.is_ticker_held_by_any)

## 핵심 규칙

### 매매 파라미터 변경 시 반드시 확인
- 전략 파라미터는 `strategies/momentum.py`, `strategies/volatility_breakout.py`의 `DEFAULT_PARAMS` 딕셔너리
- 또는 프론트 Settings 페이지에서 런타임 변경 가능 (`PUT /api/strategies/{id}/params`)
- 변경 시 `_workspace/00_leader_trading_rules.md`도 동기화

### 체결통보 (매우 중요)
- WebSocket 연결 후 **체결통보(H0STCNI0/H0STCNI9) 구독 필수**
- 체결통보를 못 받으면 포지션이 등록되지 않아 손절 감시가 불가능
- 실전: H0STCNI0 (구독 키: HTS ID), 모의: H0STCNI9 (구독 키: 계좌번호)
- scheduler.py에서 WebSocket 연결 직후 자동 구독
- 체결통보 종목코드는 `fields[8]` (단, `_order_ticker[order_no]` 매핑이 우선)

### 포지션 관리
- DB `positions` 테이블이 포지션의 진실의 원천 (매수가/전략/매수일 정확)
- 체결통보 수신 시 DB 저장 (`save_position`) / 매도 시 DB 삭제 (`delete_position`)
- 재기동 시: DB positions 우선 복구 → KIS 잔고 API 교차 검증 (DB에 없는 종목 보완)
- 당일 매도 종목 재매수 차단 (`sold_today`)
- **정산(16:10) 후 `_reset_daily_state()`**: 전략별 positions/pending_buys/sold_today + OrderEngine 추적 상태 전체 초기화 → 다음 날 `_boot()`에서 DB 기반 재구성

### 매수/매도 안전장치
- `is_max_positions()`: 보유 포지션 + 매수 대기(pending_buys) 합산으로 최대 종목 수 제한
- `_selling` set: 매도 진행 중 종목 중복 매도 차단
- 돌파 순간 감지: 이전 틱 < 기준가 AND 현재 틱 >= 기준가 (매 틱 반복 매수 방지)
- 비중 변경 시: 매수금액 이하로 비중 축소 차단
- 익일 청산 시가 안정화: `_next_day_clear_pending` 플래그로 60초 대기 중 on_tick 즉시 청산 방지 (손절은 유지)
- 체결통보 처리 실패 안전장치: ticker 매핑 실패 시 `pending_buys` 제거, strategy 미발견 시 `_selling` 해제

### 코딩 컨벤션
- Python: pydantic 모델로 데이터 검증, async/await 사용
- TypeScript: 모든 API 응답은 `types/` 디렉토리의 타입 정의 사용
- API 응답: 공통 래퍼 `{ success: bool, data: T, message: str }`
- KIS API 호출: 반드시 `src/api/base.py`의 공통 래퍼를 통해 호출 (Rate Limit 관리)
- 모든 TR_ID는 `settings.get_tr_id()` 사용 (하드코딩 금지)

### 모의/실전 분리
- `.env`에서 `KIS_ENV`에 따라 `_REAL` / `_VTS` 접미사 인증 정보 자동 선택
- `config.py`의 `get_tr_id()`로 TR_ID 자동 변환 (실전 T→모의 V 접두사)
- 등락률 순위/현재가 시세/일봉 API(FH 접두사)는 모의/실전 동일 TR_ID

## DB 스키마 (Supabase)
- `trade_history`: 거래 내역 (id, timestamp, ticker, ticker_name, trade_type, price, quantity, profit_loss, status, strategy, order_no)
- `daily_performance`: 일일 실적 (date + strategy 복합PK, total_asset, daily_profit_rate)
- `positions`: 보유 포지션 영속화 (ticker PK, buy_price, quantity, strategy_id, buy_date, high_since_buy)
- `strategy_config`: 전략 설정 영속화 (strategy_id PK, enabled, weight, params JSONB)
- `system_config`: 시스템 설정 (key PK, value JSONB) — auto_start 등
- `system_logs`: 시스템 로그 (timestamp, log_level, message)
- `parameter_recommendations`: 전략수정 AI자문 이력 (id, target_date+strategy_id unique, current_params, recommended_params, applied_params, reasoning, metrics, status, created_at/applied_at/rejected_at)
- status ENUM: PENDING, COMPLETED, PARTIAL, CANCELLED (trade_history) / pending, applied, partial, rejected, expired (parameter_recommendations)

## Docker 구성
- `Dockerfile` — 백엔드 멀티스테이지 (dev: hot-reload / prod: non-root, 단일 워커)
- `frontend/Dockerfile` — 프론트엔드 멀티스테이지 (dev: Vite / prod: Nginx)
- `frontend/nginx.conf` — 프로덕션 Nginx (정적파일 서빙 + `/api` 리버스 프록시 → backend:8000)
- `docker-compose.yml` — 개발 환경 (소스 볼륨 마운트, hot-reload)
- `docker-compose.prod.yml` — 프로덕션 환경 (restart: unless-stopped, 소스 수정 영향 없음)
- **주의**: 매매 시스템은 반드시 단일 워커로 실행 (`--workers` 금지 — 다중 워커 시 스케줄/포지션 중복)
- vite 프록시 타겟: `VITE_API_URL` 환경변수로 분기 (Docker: `http://backend:8000`, 로컬: `http://localhost:8001`)
- 타임존: `TZ=Asia/Seoul` (Dockerfile + docker-compose에 설정)

## 배포 환경 (AWS EC2)
- **인스턴스**: EC2 t4g.small (ARM, 서울 리전 `ap-northeast-2`)
- **접속**: `ssh -i ~/.ssh/auto-stock-key.pem ubuntu@<EC2_IP>`
- **서비스 경로**: `~/auto_stock/` (git clone)
- **실행**: `docker compose -f docker-compose.prod.yml up --build -d`
- **자동 배포**: `git push origin main` → GitHub Actions가 EC2에 SSH 접속 → `git pull` + 빌드 + 재시작
- **CI/CD**: `.github/workflows/deploy.yml` (Docker Hub 미사용, EC2 직접 빌드)
- **GitHub Secrets**: `EC2_HOST`, `EC2_USERNAME`, `EC2_SSH_KEY`
- **주의**: 로컬과 EC2에서 동시 실행 금지 (KIS API 동일 계정 동시 접속 충돌)

## 디렉토리 역할
- `src/auth/` — KIS OAuth 인증/토큰 관리
- `src/api/` — KIS REST API 호출 (주문, 잔고, 조건검색, 일봉)
- `src/realtime/` — KIS WebSocket (시세 구독, 체결통보)
- `src/engine/` — 매매 핵심 (전략 베이스/레지스트리/개별 전략/주문/리스크/스케줄러, 16:00 AI자문 생성 엔진 `recommendation_engine.py`)
- `src/db/` — Supabase CRUD (`parameter_recommendations` 포함)
- `src/routes/` — FastAPI 엔드포인트 (trading, balance, history, performance, logs, strategies, **recommendations**)
- `src/models/` — Pydantic 데이터 모델
- `frontend/` — React 대시보드 (대시보드/거래 내역/전략수정 AI자문/설정)
