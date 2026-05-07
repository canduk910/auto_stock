# KIS 주식 자동매매시스템

한국투자증권(KIS) OpenAPI 기반 주식 자동매매시스템. FastAPI 백엔드 + React 프론트엔드 + Supabase DB 웹 서비스 아키텍처.

## 시스템 아키텍처

```
            ┌────────────────────────┐                       ┌────────────────────────┐
            │   React Frontend       │                       │   한국투자증권 (KIS)   │
            │   - 대시보드 / 거래내역 │                       │   - REST: 주문/잔고    │
            │   - AI자문 / 설정      │                       │   - WS:   실시간 시세  │
            └─────────────┬──────────┘                       └────────┬───────────────┘
                          │ REST + 5s polling                          │
                          ▼                                            │
            ┌─────────────────────────────────────────────────────────┴──┐
            │                FastAPI Backend (단일 워커)                  │
            │  ┌────────────┐  ┌──────────────┐  ┌────────────────────┐ │
            │  │ Routes     │  │ Engine       │  │ Realtime           │ │
            │  │ trading/   │→ │ Scheduler    │→ │ WebSocket Handler  │ │
            │  │ strategies │  │ Registry     │  │ (체결가/체결통보)  │ │
            │  │ history    │  │ RiskManager  │  └────────────────────┘ │
            │  │ recommend. │  │ OrderEngine  │                         │
            │  └────────────┘  │ Strategies   │                         │
            │                  │  ├ momentum  │  ┌────────────────────┐ │
            │                  │  ├ vol_break │  │ Auth / Token       │ │
            │                  │  ├ long_tail │  └────────────────────┘ │
            │                  │  └ donchian_ │                         │
            │                  │    swing     │                         │
            │                  └──────────────┘                         │
            └──────────────────────────┬──────────────────────────────────┘
                                       │ async CRUD
                                       ▼
                          ┌────────────────────────┐         ┌──────────────┐
                          │  Supabase (PostgreSQL) │  16:00  │   OpenAI     │
                          │  trade_history         │ ◀─────→ │  GPT          │
                          │  positions / strategy  │  16:10  │  (자문 +     │
                          │  parameter_recommend.  │ ◀─────→ │   로그 분석) │
                          │  daily_log_reports     │         └──────────────┘
                          │  daily_performance     │
                          └────────────────────────┘
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
3. **한국투자증권 OpenAPI 신청** — [KIS Developers](https://apiportal.koreainvestment.com/)에서 앱키/시크릿 발급
4. **Supabase 프로젝트 생성** — [supabase.com](https://supabase.com/)에서 프로젝트 생성 후 URL/Key 확보

## 설치 및 실행

### 1. 환경 변수 설정

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

Supabase SQL Editor에서 `supabase/migrations/` 하위 마이그레이션 파일을 **번호 순으로 모두 실행**:

```
001_init.sql                          # 기본 테이블
003_trade_history_columns.sql         # trade_history 컬럼 보강
004_strategy_config.sql               # 전략 설정 영속화
005_system_config.sql                 # auto_start 등 시스템 설정
006_positions.sql                     # 포지션 영속화
007_parameter_recommendations.sql     # AI 자문 이력
008_rename_momentum_breakout.sql      # 전략명 정리
009_performance_cashflow.sql          # 외부 입출금 + TWR
010_recompute_performance_fn.sql      # daily_performance 일괄 재계산 RPC
011_register_donchian_swing.sql       # 20일 신고가 스윙 전략 등록
012_recompute_prev_asset_fallback.sql # 분모 0 함정 차단
013_daily_log_reports.sql             # 일일 로그 분석 리포트
```

### 3. Docker Compose로 실행 (권장)

```bash
# 개발 환경 (hot-reload 지원)
docker compose up --build

# 프로덕션 환경
docker compose -f docker-compose.prod.yml up --build -d
```

- 개발: 프론트엔드 `http://localhost:3000`, 백엔드 `http://localhost:8002`
- 프로덕션: `http://localhost:80` (Nginx 정적파일 + API 프록시)

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
4. 08:20~16:10 스케줄에 따라 자동매매 진행
5. [정지] 버튼으로 수동 중지 가능

### 대시보드 화면

| 화면 | 기능 |
|------|------|
| 메인 대시보드 | 계좌 요약, 보유 종목, 매매 실적 차트, 상태 인디케이터, 조건검색 현황(전략별 스캔/타겟/스윙 깔때기) |
| 거래 내역 | 매수/매도 기록 테이블 (필터, 페이징) |
| 전략수정 AI자문 | 16:00 OpenAI 자동 생성 자문 — 신규 자문 탭(승인/거절) + 이력 탭(상태/전략 필터) |
| 일일 로그 분석 | 16:10 정산 직후 OpenAI가 system_logs+trade_history 분석한 운영 개선 리포트 (영업일 리스트 + findings + 메트릭) |
| 설정 | 전략 파라미터 조정, 자금 비중, 자동 시작 토글 |

### 실전 전환

```env
KIS_ENV=real
KIS_APP_KEY=실전용_앱키
KIS_APP_SECRET=실전용_시크릿
```

> **주의**: 반드시 모의투자에서 충분히 검증한 후 실전 전환하세요.

## 매매 전략

```
                ┌──────────────────────────────────────────────────────────────┐
                │              StrategyRegistry (자금 분배)                    │
                │           순자산 × weight = 전략별 할당 자금                 │
                └────┬───────────────┬───────────────┬────────────────┬────────┘
                     │               │               │                │
                     ▼               ▼               ▼                ▼
              ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
              │ momentum     │ │ volatility_  │ │ long_tail_   │ │ donchian_    │
              │ (상한가)     │ │ breakout     │ │ volatility   │ │ swing        │
              ├──────────────┤ ├──────────────┤ ├──────────────┤ ├──────────────┤
              │ 진입 09:30~  │ │ 진입 09:00:05│ │ 진입 09:00:05│ │ 진입 09:05~  │
              │ 시그널: +29% │ │ 시그널: 시가 │ │ 시그널: 시가 │ │   09:30 시장가│
              │   돌파       │ │  + Range×K   │ │  + Range×K   │ │ 시그널: 20일 │
              │ 손절 -7.5%   │ │ 손절 -3%     │ │ 당일 -3%     │ │   신고가+추세│
              │ 익일 청산    │ │ 15:20 강제   │ │ 상한가 도달→ │ │ 손절 -7%     │
              │ (갭/트레일)  │ │   청산       │ │   익일 청산  │ │ ATR×2 트레일 │
              │ 당일 매매    │ │ 당일 매매    │ │ 당일 또는    │ │ 멀티데이     │
              │              │ │              │ │ 익일 청산    │ │  (5~15일)    │
              └──────┬───────┘ └──────┬───────┘ └──────┬───────┘ └──────┬───────┘
                     │                │                │                │
                     └────────────────┴────────┬───────┴────────────────┘
                                               ▼
                                    ┌───────────────┐  ┌───────────────┐
                                    │ RiskManager   │  │ OrderEngine   │
                                    │ on_tick(시세) │→ │ KIS 주문 실행 │
                                    │ → 신호 판단   │  │ 포지션 관리   │
                                    └───────────────┘  └───────────────┘
```

### 전략 A: 상한가 모멘텀 (`momentum`)
| 구분 | 규칙 |
|------|------|
| 종목 선정 | 등락률 순위 15%+ → 시총 1,000억+, 거래대금 200억+ |
| 매수 | 전일종가 대비 +29% 돌파 순간, 할당 자금 25% 비중 |
| 손절 | 매수가 대비 -7.5% |
| 익일 청산 | 09:00 갭상승 +10% → 트레일링 스탑 -2% / 그 외 즉시 매도 |

### 전략 B: 변동성 돌파 (`volatility_breakout`)
| 구분 | 규칙 |
|------|------|
| 종목군 | 코스피+코스닥 전체, 시총/거래대금 필터, 노이즈 비율 기반 동적 K값 |
| 매수 | 시가 + (전일 Range × K값) 돌파 순간, 할당 자금 10% 비중 |
| 손절 | 매수가 대비 -3% |
| 청산 | 15:20 전량 강제 청산 (오버나잇 거부) |
| 재매수 | 당일 매도 종목 재매수 차단 |

### 전략 C: 롱테일 변동성 돌파 (`long_tail_volatility`)
| 구분 | 규칙 |
|------|------|
| 종목군 | 변동성 돌파와 동일 + 연속상한가 종목 제외 |
| 매수 | 변동성 돌파 + 전일대비 ≥ `min_prdy_rate` (기본 5%) |
| 당일 청산 | 손절 -3%, 15:20 강제 청산 (상한가 미도달 종목만) |
| 모드 전환 | 당일 +29% 도달 → 익일 청산 모드로 전환 |
| 익일 청산 | 손절 -5%, 갭상승 +10% → 트레일링 -2% / 그 외 즉시 매도 |

### 전략 D: 20일 신고가 스윙 (`donchian_swing`)
| 구분 | 규칙 |
|------|------|
| 종목군 | **코스피200 + 코스닥150 고정 유니버스** + 시총 컷 (거래량순위 API 미사용 — 추세추종 부적합 + 시점 의존 제거) |
| 진입 조건 | 어제 종가가 20일 신고가 돌파 + 60일 EMA 우상향 + 종가>EMA + 거래대금 ≥ 20일평균×1.5 |
| 매수 | 다음 영업일 09:05~09:30 시장가, 1종목당 1회. **시가 갭상승 +3%↑ 시 스킵** (추격 방지) |
| 손절 | 매수가 대비 -7% 하드 손절 |
| 청산 | ATR(14)×2 Chandelier 트레일링 (`high_since_buy − ATR×2`) — 시간 청산 없음 |
| 보유 | 멀티데이 (평균 5~15 영업일). DB `positions` 영속화로 일자 넘어 유지 |
| 종목명 | KIS `hts_kor_isnm` 우선 + `scanner.STATIC_TICKER_NAMES`(KOSPI200/KOSDAQ150 인라인 코멘트 자동 파싱)로 fallback |

> 프론트엔드 Settings 페이지에서 전략별 자금 비중 조절 가능. 대시보드 "조건검색 현황 → 20일 신고가 스윙" 탭에서 8단계 깔때기 통계 + 후보 종목 진입상태(보유 중 / 진입 대기 / 갭 스킵 / 장 시작 전 / 진입 시간 종료) 시각화

### 매매 안전장치
| 항목 | 동작 |
|------|------|
| 종목코드 형식 비대칭 | 진입 단계는 6자리 숫자만(`isdigit`) — ETF·신주인수권·임시 코드 매수 차단. 사후처리(체결통보·잔고 sync)는 6자리 영숫자(`isalnum`) 허용 — 외부 경로로 들어와도 좀비 포지션 방지 |
| 매수가능 캐시 | 60초 TTL — KIS `get_buyable()` 호출을 매 틱 → 분당 1회로 축소 |
| 잔고부족 매수 락 | 900초 — `is_insufficient_cash` 응답 또는 `max_buy_quantity≤0` 시 다음 잔고 sync까지 매수 차단 |
| 매도 잔고부족 즉시 break | `is_insufficient_quantity` 응답 시 3회 재시도 생략 + 메모리·DB positions 정리 |
| 체결통보 race 가드 | 시장가 즉시체결 시 체결통보가 REST 응답보다 먼저 와도 `_completed_orders` set + 보정 INSERT로 PENDING 잔존 차단 |
| 진입 차단 | VB/LTV `_scan_universe`의 거래량순위 후보 + `scanner.scan_stocks` 모두 `ticker.isdigit()` 검증 |

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
| GET | `/api/performance/summary` | 실적 요약 (TWR 누적 + 일평균 실현 수익률) |
| GET | `/api/performance/daily` | 일별 실적 (실현손익 기반 + TWR 누적 + 외부 입출금) |
| POST | `/api/performance/recompute` | trade_history 기반 daily_performance 전체 소급 재계산 (멱등) |
| GET | `/api/strategies` | 전략 목록 + 비중 + 상태 + 타겟가 + 스윙 `scan_stats` 깔때기 |
| PUT | `/api/strategies/weights` | 전략별 비중 수정 (매수금액 하한선 검증) |
| PUT | `/api/strategies/{id}/params` | 전략 파라미터 수정 |
| GET | `/api/strategies/system/auto-start` | 자동 매매 설정 조회 |
| PUT | `/api/strategies/system/auto-start` | 자동 매매 설정 변경 |
| GET | `/api/logs` | 시스템 로그 조회 |
| GET | `/api/recommendations` | 전략수정 AI자문 목록 (최근 30일) |
| GET | `/api/recommendations/{id}` | 단일 자문 상세 |
| POST | `/api/recommendations/{id}/apply` | 선택한 키만 전략 파라미터에 적용 |
| POST | `/api/recommendations/{id}/reject` | 자문 전체 거절 |
| GET | `/api/log-reports?days=30` | 일일 로그 분석 리포트 목록 |
| GET | `/api/log-reports/{YYYY-MM-DD}` | 단일 영업일 리포트 상세 |
| POST | `/api/log-reports/run` | 수동 트리거 — 즉시 분석 실행 (영업일당 1건 UNIQUE) |

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
├── .claude/                 # Claude Code 하네스 (에이전트팀 + 스킬)
│   ├── agents/              # 4개 전문 에이전트 정의
│   └── skills/              # 4개 도메인 스킬
├── Dockerfile               # 백엔드 Docker (dev/prod 멀티스테이지)
├── docker-compose.yml       # 개발 환경 Docker Compose
├── docker-compose.prod.yml  # 프로덕션 환경 Docker Compose
├── requirements.txt         # Python 의존성
└── .env                     # 환경 변수 (git 미추적)
```

## 에이전트팀 (Claude Code 하네스)

이 프로젝트는 Claude Code의 서브에이전트 + 스킬 시스템을 활용한 **다중 에이전트 협업 구조**로 개발·운영된다. 사용자 요청 유형에 따라 오케스트레이터 스킬이 적합한 에이전트와 스킬을 자동 호출한다.

### 구성도

```
                    ┌─────────────────────────────────────────┐
                    │  사용자 요청 (자연어)                   │
                    │  "전략 추가해줘" / "버그 수정" / "테스트"│
                    └──────────────────┬──────────────────────┘
                                       ▼
                  ┌────────────────────────────────────────────┐
                  │  auto-trading-orchestrator (스킬)          │
                  │  요청 분류 → 적합한 에이전트/스킬 호출     │
                  └─┬──────────────┬──────────────┬──────────┬─┘
                    │              │              │          │
                    ▼              ▼              ▼          ▼
           ┌──────────────┐ ┌──────────────┐ ┌──────────┐ ┌────────┐
           │ team-leader  │ │ backend-dev  │ │ frontend │ │ tester │
           │ (트레이더    │ │ (FastAPI +   │ │ -dev     │ │  (QA)  │
           │  출신 팀장)  │ │  KIS 엔진)   │ │ (React)  │ │        │
           │ 매매 규칙    │ │              │ │          │ │ E2E /  │
           │ 검수·지시    │ │              │ │          │ │ 정합성 │
           └──────┬───────┘ └──────┬───────┘ └────┬─────┘ └───┬────┘
                  │                │              │           │
                  └────────────────┼──────────────┼───────────┘
                                   ▼              ▼
                  ┌────────────────────────────────────────────┐
                  │  도메인 스킬 (재사용 지식 모듈)            │
                  │  ┌──────────────────┐ ┌─────────────────┐ │
                  │  │ kis-api-         │ │ trading-        │ │
                  │  │ integration      │ │ dashboard       │ │
                  │  │ (OAuth, REST,    │ │ (React 화면 +   │ │
                  │  │  WebSocket,      │ │  TanStack Query)│ │
                  │  │  TR_ID 변환)     │ └─────────────────┘ │
                  │  └──────────────────┘ ┌─────────────────┐ │
                  │                       │ trading-test    │ │
                  │                       │ (E2E + DB 정합) │ │
                  │                       └─────────────────┘ │
                  └────────────────────────────────────────────┘
```

### 에이전트 (`.claude/agents/`)

| 에이전트 | 역할 | 호출 시점 |
|----------|------|-----------|
| **team-leader** | 트레이더 출신 팀장 — 매매 전략·리스크 규칙·주문 흐름을 현업 관점에서 지시·검수 | 트레이딩 시스템 전체 구축/확장, 신 전략 추가, 매매 규칙 변경 |
| **backend-dev** | FastAPI 기반 REST API + KIS OpenAPI 연동 + 매매 엔진 + WebSocket + Supabase | API 추가, 전략 구현, 주문/잔고 로직, DB CRUD |
| **frontend-dev** | React 트레이딩 대시보드 — 구동 관리, 실적/잔고, 거래 내역, Settings | 화면 추가/수정, 차트, 폼, 상태 관리 |
| **tester** | KIS 연동 정합성, FastAPI↔React 경계면, Supabase 스키마, 주문 흐름 E2E, 매매 안전성 | 통합 테스트, 회귀 검증, 정합성 점검 |

### 스킬 (`.claude/skills/`)

| 스킬 | 용도 | 트리거 키워드 |
|------|------|----------------|
| **auto-trading-orchestrator** | 4개 에이전트를 조율해 시스템 전체 구축/확장 | "자동매매 시스템 구축", "전략 추가", "트레이딩 시스템 개발" |
| **kis-api-integration** | OAuth/REST/WebSocket/TR_ID 변환 등 KIS OpenAPI 연동 코드 | "KIS API", "주식 주문", "잔고 조회", "실시간 시세", "토큰 발급" |
| **trading-dashboard** | React 대시보드 화면 구현 (시작/정지·실적·잔고·차트) | "대시보드", "화면", "UI", "차트", "프론트엔드" |
| **trading-test** | KIS 연동/주문 흐름/DB 정합성 통합 테스트 | "테스트", "검증", "QA", "버그", "정합성 확인" |

### 협업 규약

- **CLAUDE.md 계층**: 루트 `CLAUDE.md` + 디렉토리별 `CLAUDE.md`(`src/`, `src/engine/`, `src/api/`, `src/db/`, `src/routes/`, `src/realtime/`, `frontend/` 등)에 모듈별 코딩 컨벤션·금지사항·연동 규칙을 명시. 모든 에이전트가 작업 전 해당 컨텍스트를 자동 로드.
- **단일 책임**: 각 에이전트는 자신의 역할 범위 안에서만 파일 수정. 경계면 변경(예: API 응답 스키마)은 backend-dev가 정의 → frontend-dev가 타입 동기화.
- **검수 흐름**: 매매 규칙 변경은 team-leader가 사양 결정 → backend-dev 구현 → tester 검증.

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

```
   장 전 준비           동시호가 종료      정규 거래        장 마감 후
─────────────────┬──────────────────┬────────────────┬─────────────────────
 08:20  08:25 08:30 08:55│09:00:00 09:00:05  09:30      15:20  15:30  16:00 16:10
   │     │     │    │    │   │       │        │          │     │     │    │
   ▼     ▼     ▼    ▼    ▼   ▼       ▼        ▼          ▼     ▼     ▼    ▼
 자동  prepare  WS  사전  익일 시가확정 돌파매매   모멘텀     매수  WS    AI   정산
 매매  토큰    연결 구독  청산 (5초폴) 시작(VB/  스캔+매매   중단  해제  자문 +DB
 시작  포지션       돌파  60초  + 매매  LTV)      시작       VB/LTV     생성 적재
       복구         종목  대기  진입             모멘텀      강제      (OpenAI)
                          (백그)                 09:30~     청산
                          ↓
                    ┌─ 모멘텀 익일 청산 (갭/트레일링) ─┐
                    │  60초 시가 안정화 후 매매 처리   │
                    └──────────────────────────────────┘
```

| 시각 | 동작 |
|------|------|
| 08:20 | 자동 매매 시작 (AUTO_START 활성 시, 주말+공휴일 자동 건너뜀 — KIS chk-holiday API) |
| 08:25 | 프로세스 기동, 토큰 갱신, DB 포지션/설정 복구, 전략 prepare(일봉/K값/전일종가/도치안 단계별 통계) |
| 08:30 | WebSocket 연결, 체결통보 구독 |
| 08:55 | 사전 구독 — 돌파(VB/LTV) + 스윙(donchian) 스캔 종목 + 보유 포지션 (09:00 시가 즉시 수신용). 유니버스가 비어있으면 prepare 재실행 |
| 09:00:00 | 모멘텀 익일 청산(백그라운드 60초 안정화) + 돌파 시가 확정(0.5초 폴링) 동시 시작 |
| 09:00:05 | 변동성돌파(VB) / 롱테일 변동성 돌파(LTV) 매매 시작 (시가 확정 직후) |
| 09:05~09:30 | 도치안 스윙(donchian) 진입창 — 시장가 1주문/종목, 갭 +3%↑ 스킵 |
| 09:30 | 모멘텀(상한가) 종목 스캔 시작, 매수 감시. 5분 주기 `_scan_loop` 시작 — 모멘텀+돌파+스윙+보유 합집합 시세 재구독 |
| 15:20 | 신규 매수 중단, VB + LTV(상한가 미도달 종목) 전량 강제 청산. 도치안은 강제 청산 없음(추세 보유) |
| 15:30 | WebSocket 구독 해제 |
| 16:00 | 전략수정 AI자문 생성 (OpenAI → `parameter_recommendations`) |
| 16:10 | 전략별 + 합산 일일 정산, DB 실적 기록. 직후 일일 로그 분석 리포트 생성 (OpenAI → `daily_log_reports`) |

**중간 시각 시작 시**: 현재 시각 이후 스케줄부터 실행 (16:10 이후 시작 거부)

### 전략수정 AI자문 사이클

```
  16:00 (당일)                                            다음 영업일
 ──────────────────────────────────────────────────────────────────►
  ┌──────────────────┐    ┌──────────────────┐    ┌─────────────────┐
  │ generate_recom-  │    │  /recommendations │    │ Settings 적용   │
  │ mendations()     │ ─► │  신규 탭(최근    │ ─► │ → strategy_     │
  │  trade_history → │    │   target_date)   │    │   config.params │
  │  metrics 집계 → │    │  status 무관     │    │   갱신          │
  │  OpenAI GPT →    │    │  pending/applied/│    │  (다음 사이클   │
  │  validate +      │    │  rejected/expired│    │   부터 반영)    │
  │  DB INSERT       │    │   배지 표시      │    └─────────────────┘
  └──────────────────┘    └──────────────────┘
                                  │
                                  ▼
                          ┌──────────────────┐
                          │  이력 탭         │
                          │  이전 target_date│
                          │  + 상태/전략     │
                          │   필터           │
                          └──────────────────┘
```

### 일일 로그 분석 사이클

```
  16:10 정산 직후                                                     사용자
 ──────────────────────────────────────────────────────────────────────►
  ┌────────────────────────┐    ┌──────────────────┐    ┌─────────────────┐
  │ generate_daily_log_   │    │ /log-reports     │    │ 우상단 "지금     │
  │ report()              │    │ 좌측: 영업일     │    │  분석 실행"     │
  │  당일 KST 00:00~now   │ ─► │ 우측: 총평 +     │ ◀─ │  버튼 (수동      │
  │  system_logs 집계 →   │    │ findings + 메트릭│    │  트리거,         │
  │  trade_history 집계 → │    │ (severity 색상   │    │  영업일당 1건)   │
  │  OpenAI JSON →        │    │  + category 칩)  │    │                  │
  │  daily_log_reports    │    │                  │    └─────────────────┘
  │  INSERT (UNIQUE)      │    └──────────────────┘
  └────────────────────────┘
```

