# KIS 주식 자동매매시스템

한국투자증권(KIS) OpenAPI 기반 주식 자동매매시스템. FastAPI 백엔드 + React 프론트엔드 + Supabase DB 웹 서비스 아키텍처.

## 시스템 아키텍처

```
[React Frontend]  ←REST API→  [FastAPI Backend]  ←KIS API→  [한국투자증권]
   (Vite)                       (Uvicorn)               │
                                    │              [WebSocket 실시간]
                                    ↓
                              [Supabase DB]
                            (PostgreSQL)
```

## 기술 스택

| 구분 | 기술 |
|------|------|
| Backend | Python 3.11+, FastAPI, httpx, websockets, pydantic |
| Frontend | React 19, TypeScript, Vite, TanStack Query/Table, Recharts, Tailwind CSS |
| Database | Supabase (PostgreSQL) |
| 외부 API | 한국투자증권 OpenAPI (REST + WebSocket) |

## 사전 준비

1. **Python 3.11+** 설치
2. **Node.js 20+** 설치
3. **한국투자증권 OpenAPI 신청** �� [KIS Developers](https://apiportal.koreainvestment.com/)에서 앱키/시크릿 발급
4. **Supabase 프로젝트 생성** — [supabase.com](https://supabase.com/)에서 프로젝트 생성 후 URL/Key 확보

## 설치 및 실행

### 1. 환��� 변수 설정

```bash
cp .env.example .env
```

`.env` 파일을 편집하여 실제 값을 입력:

```env
# KIS OpenAPI 인증
KIS_APP_KEY=발급받은_앱키
KIS_APP_SECRET=발급받은_시크릿
KIS_ACCOUNT_NO=계좌번호_8자리
KIS_ACCOUNT_PRODUCT=01
KIS_ENV=vts                    # vts(모의투자) 또는 real(실전)

# Supabase
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-anon-key
```

### 2. 데이터베이스 초기화

Supabase SQL Editor에서 마이그레이션 파일 실행:

```bash
# supabase/migrations/001_init.sql 내용을 Supabase SQL Editor에 붙여넣기 실행
```

### 3. Docker Compose로 실행 (권장)

```bash
# 개발 환경 (hot-reload 지원)
docker compose up --build

# 프로덕션 환경
docker compose -f docker-compose.prod.yml up --build -d
```

- 개발: 프론트엔드 `http://localhost:3000`, 백엔드 `http://localhost:8002`
- 프로덕션: `http://localhost:80` (Nginx 정적파��� + API 프록시)

### 3-1. 로컬 직접 실행 (Docker 없이)

```bash
# 백엔드
pip install -r requirements.txt
uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload

# 프론트엔드
cd frontend && npm install && npm run dev
```

- 백엔드: `http://localhost:8000`, API 문서: `http://localhost:8000/docs`
- 프론트엔드: `http://localhost:3000`

## 사용 방법

### 모의투자 테스트

1. `.env`에서 `KIS_ENV=vts` 확인
2. 백엔드 + 프론트엔드 실행
3. 대시보드에서 [시작] 버튼 클릭 → 확인 모달에서 승인
4. 08:25~16:10 스케줄에 따라 자동매매 진행
5. [정지] 버튼으로 ���동 중지 가능

### 대시보드 화면

| 화면 | 기능 |
|------|------|
| 메인 대시보드 | 계좌 요약, 보유 종목, 매매 실적 차트, 상태 인디케이터 |
| 거래 내역 | 매수/매도 기록 테이블 (필터, 페이징) |
| 설정 | 전략 파라미터 조정 |

### 실전 전환

```env
KIS_ENV=real
KIS_APP_KEY=실전용_앱키
KIS_APP_SECRET=실전용_시크릿
```

> **주의**: 반드시 모의투자에서 충분히 검증한 후 실전 전환하세요.

## 매매 전략

| 구분 | 규칙 |
|------|------|
### 전략 A: 상한가 모멘텀
| 구분 | 규칙 |
|------|------|
| 종목 선정 | 등락률 순위 15%+ → 시총 1,000억+, 거래대금 200억+ |
| 매수 | 전일종가 대비 +29% 돌파 순간, 할당 자금 25% 비중 |
| 손절 | 매수가 대비 -7.5% |
| 익일 청산 | 09:00 갭상승 +10% → 트레일링 스탑 -2% / 그 외 즉시 매도 |

### 전략 B: 변동성 돌파
| 구분 | 규칙 |
|------|------|
| 종목군 | 코스피+코스닥 전체, 시총/거래대금 필터, 노이즈 비율 기반 동적 K값 |
| 매수 | 시가 + (전일 Range × K값) 돌파 순간, 할당 자금 10% 비중 |
| 손절 | 매수가 대비 -3% |
| 청산 | 15:20 전량 강제 청산 (오버나잇 거부) |
| 재매수 | 당일 매도 종목 재매수 차단 |

> 프론트엔드 Settings 페이지에서 전략별 자금 비중 조절 가능

## API 엔드포인트

| Method | URL | 설명 |
|--------|-----|------|
| GET | `/health` | 헬스 체크 |
| POST | `/api/trading/start` | 자동매매 시작 |
| POST | `/api/trading/stop` | 자동매매 정지 |
| POST | `/api/trading/restart` | 자동매매 재기동 |
| POST | `/api/trading/manual-sell` | 수동 매도 (시장가) |
| GET | `/api/trading/status` | 현재 상태 조회 |
| GET | `/api/balance` | 잔고 조회 (예수금 + 보유종목) |
| GET | `/api/balance/buyable` | 매수 가능 금액 조회 |
| GET | `/api/history?page=&size=` | 거래 내역 (페이징) |
| GET | `/api/performance/summary` | 실적 요약 |
| GET | `/api/performance/daily` | 일별 실적 |
| GET | `/api/performance/monthly` | 월별 실적 |
| GET | `/api/strategies` | 전략 목록 + 비중 + 상태 + 타겟가 |
| PUT | `/api/strategies/weights` | 전략별 비중 수정 (매수금액 하한선 검증) |
| PUT | `/api/strategies/{id}/params` | 전략 파라미터 수정 |
| GET | `/api/strategies/system/auto-start` | 자동 매매 설정 조회 |
| PUT | `/api/strategies/system/auto-start` | 자동 매매 설정 변경 |
| GET | `/api/logs` | 시스템 로그 조회 |

## 프로젝트 구조

```
auto_stock/
├── src/                     # 백엔드 (FastAPI)
│   ├── main.py              # 앱 엔트리포인트
│   ├── config.py            # 환경 설정
│   ├── auth/                # KIS OAuth 인증
│   ├── api/                 # KIS REST API 호출
│   ├── realtime/            # KIS WebSocket 실시간
│   ├── engine/              # 매매 엔진 (전략/주문/리스크/스케줄러)
│   ├── db/                  # Supabase CRUD
│   ├── routes/              # FastAPI 라우트
│   └── models/              # Pydantic 데이터 모델
├── frontend/                # 프론트엔드 (React)
│   └── src/
│       ├── api/             # API 호출 함수
│       ├── components/      # UI 컴포넌트
│       ├── pages/           # 페이지
│       └── types/           # TypeScript 타입
├── supabase/migrations/     # DB 마이그레이션
├── docs/kis/                # KIS API 스펙 문서
├── Dockerfile               # 백엔드 Docker (dev/prod 멀티스테이지)
├── docker-compose.yml       # 개발 환경 Docker Compose
├── docker-compose.prod.yml  # 프로덕션 환경 Docker Compose
├── requirements.txt         # Python 의존성
└── .env                     # 환경 변수 (git 미추적)
```

## 배포 (AWS EC2)

### 서버 구성
- **인스턴스**: EC2 t4g.small (2vCPU, 2GB RAM, ARM)
- **리전**: ap-northeast-2 (서울) — KIS WebSocket 지연 최소화
- **OS**: Ubuntu 24.04 LTS, Docker 설치 완료
- **접속**: `http://<EC2_IP>` (Nginx 80포트)

### 자동 배포 (CI/CD)
`git push origin main` → GitHub Actions → EC2 자동 배포

```
git push → GitHub Actions → SSH → EC2: git pull → docker compose build → 재시작
```

GitHub Secrets 필요: `EC2_HOST`, `EC2_USERNAME`, `EC2_SSH_KEY`

### 수동 배포
```bash
ssh -i ~/.ssh/auto-stock-key.pem ubuntu@<EC2_IP>
cd ~/auto_stock
git pull origin main
docker compose -f docker-compose.prod.yml up --build -d
```

> **주의**: 로컬과 EC2에서 동시 실행 금지 — KIS API 동일 계정 동시 접속 시 충돌 발생

## 스케줄

| 시각 | 동작 |
|------|------|
| 08:20 | 자동 매매 시작 (AUTO_START 활성 시, 주말 자동 건너뜀) |
| 08:25 | 프로세스 기동, 토큰 갱신, DB 포지션/설정 복구 |
| 08:30 | WebSocket 연결, 체결통보 구독 |
| 09:00 | 모멘텀 익일 청산 |
| 09:01 | 변동성돌파 시가 확정 → Target Price 계산 |
| 09:30 | 종목 스캔 시작, 매수 감시 |
| 15:20 | 신규 매수 중단, 변동성돌파 전량 강제 청산 |
| 15:30 | WebSocket 구독 해제 |
| 16:10 | 전략별 + 합산 일일 정산, DB 실적 기록 |

**중간 시각 시작 시**: 현재 시각 이후 스케줄부터 실행 (16:10 이후 시작 거부)
