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

### 3. 백엔드 실행

```bash
# 의존성 설치
pip install -r requirements.txt

# 서버 시작
python -m src.main
# 또는
uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload
```

서버가 `http://localhost:8000`에서 실행됩니다. API 문서: `http://localhost:8000/docs`

### 4. 프론트엔드 실행

```bash
cd frontend
npm install
npm run dev
```

대시보드가 `http://localhost:5173`에서 실행됩니다.

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
| 종목 선정 | 09:30~ 시총 1,000억+, 거래대��� 200억+, 최대 40종목 |
| 매수 | 당일 시가 대비 +29.5% 도달, 투자대금 25% 비중, 시장가 |
| 당일 손절 | 매수 체결가 대비 -7.5% 즉시 시장가 전량 매도 |
| 익일 청산 | 09:00 시가 +10%↑ → 고점 -2% 트레일링 스탑 / 그 외 즉시 매도 |
| 리스크 | 일일 최대 손실 5%, 동시 보유 4종목, 15:20 매수 중단 |

## API 엔드포인트

| Method | URL | 설명 |
|--------|-----|------|
| GET | `/health` | 헬스 체크 |
| POST | `/api/trading/start` | 자동매매 시작 |
| POST | `/api/trading/stop` | 자동매매 ��지 |
| GET | `/api/trading/status` | 현재 상태 조회 |
| GET | `/api/balance` | 잔고 조회 (예수금 + 보유종목) |
| GET | `/api/balance/buyable` | 매수 가능 금액 조회 |
| GET | `/api/history?page=&size=` | 거래 내역 (페이징) |
| GET | `/api/performance/summary` | 실적 요약 |
| GET | `/api/performance/daily` | 일별 실적 |
| GET | `/api/performance/monthly` | 월별 실적 |

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
├── requirements.txt         # Python 의존성
└── .env                     # 환경 변수 (git 미추적)
```

## 스케줄

| 시각 | 동작 |
|------|------|
| 08:25 | 프로세스 기동, 토큰 갱신, DB 잔고 동기화 |
| 08:30 | WebSocket 연결 |
| 09:00 | 익일 청산 실행 (전일 보유 종목) |
| 09:30 | 종목 필터링 시작, 매수 감시 |
| 15:20 | 신규 매수 중단 |
| 15:30 | WebSocket 구독 해제 |
| 16:10 | 일��� 정산, DB 실적 기록, Sleep |
