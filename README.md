# KIS 주식 자동매매시스템

한국투자증권(KIS) OpenAPI 기반 주식 자동매매시스템. FastAPI 백엔드 + React 프론트엔드 + AWS RDS PostgreSQL(asyncpg) 웹 서비스 아키텍처.

## 시스템 아키텍처

```
            ┌────────────────────────┐                       ┌────────────────────────┐
            │   React Frontend       │                       │   한국투자증권 (KIS)   │
            │   - 대시보드/거래내역  │                       │   - REST: 주문/잔고    │
            │   - AI자문 / 설정      │                       │   - WS:   실시간 시세  │
            └─────────────┬──────────┘                       └────────┬───────────────┘
                          │ REST + 5s polling                         │
                          ▼                                           │
            ┌─────────────────────────────────────────────────────────┴───┐
            │                FastAPI Backend (단일 워커)                  │
            │  ┌────────────┐  ┌──────────────┐  ┌──────────────────────┐ │
            │  │ Routes     │  │ Engine       │  │ Realtime             │ │
            │  │ trading/   │→ │ Scheduler    │→ │ WebsocketPool        │ │
            │  │ strategies │  │ Registry     │  │  (메인+보조 세션)    │ │
            │  │ history    │  │ RiskManager  │  │ 체결가 H0STCNT0(KRX) │ │
            │  │ recommend. │  │ OrderEngine  │  │        H0NXCNT0(NXT) │ │
            │  └────────────┘  │ TickChannel* │  │ 체결통보 H0STCNI0    │ │
            │                  │ Strategies   │  └──────────────────────┘ │
            │                  │  ├ momentum  │  ┌──────────────────────┐ │
            │                  │  ├ vol_break │  │ Auth / Token         │ │
            │                  │  ├ long_tail │  └──────────────────────┘ │
            │                  │  ├ donchian  │                           │
            │                  │  ├ bull_flag │                           │
            │                  │  ├ vcp_break │                           │
            │                  │  └ kojiro    │                           │
            │                  └──────────────┘                           │
            └──────────────────────────┬──────────────────────────────────┘
                                       │ async CRUD
                                       ▼
                          ┌────────────────────────┐         ┌──────────────┐
                          │  AWS RDS (PostgreSQL)  │  20:00  │   OpenAI     │
                          │  asyncpg (src/db/pg.py)│ ◀─────→ │  GPT         │
                          │  positions / strategy  │  21:30  │  (자문 +     │
                          │  parameter_recommend.  │ ◀─────→ │   로그 분석) │
                          │  daily_log_reports     │         └──────────────┘
                          │  daily_performance     │
                          └────────────────────────┘
```

\* `TickChannel` 은 시세 채널 결정을 묶어 부르는 이름이고, 실제 모듈은
`src/engine/tick_channel_clock.py`(전환 시각 계산) · `tick_channel_switch.py`(전환 실행) ·
`tick_channel_mode.py`(모드·킬스위치) 셋이다.

## 기술 스택

| 구분 | 기술 |
|------|------|
| Backend | Python 3.11+, FastAPI, httpx, websockets, pydantic, asyncpg, pandas, openai |
| Frontend | React 19, TypeScript, Vite, React Router 7, TanStack Query/Table, axios, Recharts, Tailwind CSS 4 |
| Database | AWS RDS PostgreSQL (asyncpg 직접 드라이버) |
| 외부 API | 한국투자증권 OpenAPI (REST + WebSocket) · OpenAI (전략수정 AI자문 · 일일 로그 분석 · AI 매수평가) · 백테스트 MCP (`KIS_MCP_ENABLED`, 기본 off) — 매크로 레짐은 외부가 아니라 **자체 `macro` 컨테이너**다(`DKSTOCK_REGIME_ENABLED`, 변수명만 유지) |

## 사전 준비

1. **Python 3.11+** 설치 — Docker 이미지와 CI 는 **3.12** 를 쓴다(`python:3.12-slim`)
2. **Node.js 20+** 설치 — 프론트 이미지와 CI 는 **22** 를 쓴다(`node:22-alpine`)
3. **한국투자증권 OpenAPI 신청** — [KIS Developers](https://apiportal.koreainvestment.com/)에서 앱키/시크릿 발급
4. **PostgreSQL 준비** — AWS RDS PostgreSQL 인스턴스(또는 로컬 postgres) 확보 후 asyncpg DSN(`DATABASE_URL`) 구성
5. **API 인증 키 생성** — `python3 -c "import secrets;print(secrets.token_urlsafe(32))"` 로 만들어 `.env` 의 `API_AUTH_KEY=` 에 넣는다. 없으면 `/health` 를 뺀 전 경로가 401 이다(값이 없으면 막는 fail-closed 설계). 프로덕션(:80)은 nginx Basic Auth 자격 파일 `secrets/.htpasswd` 도 함께 필요하다 — 「배포 전 호스트 준비」 참조
6. **OpenAI API 키** (선택) — 20:00 전략수정 AI자문 · 21:30 일일 로그 분석 · AI 매수평가가 쓴다. 없으면 그 세 기능만 WARNING 을 남기고 건너뛴다(매매 자체는 돈다)

## 설치 및 실행

### 1. 환경 변수 설정

```bash
cp .env.example .env
```

`.env` 파일을 편집하여 실제 값을 입력:

```env
# KIS OpenAPI 인증 — 값은 접미사 키(_VTS / _REAL)에 넣는다
KIS_ENV=vts                    # vts(모의투자) 또는 real(실전)
KIS_APP_KEY_VTS=발급받은_앱키
KIS_APP_SECRET_VTS=발급받은_시크릿
KIS_ACCOUNT_NO_VTS=계좌번호_8자리
KIS_ACCOUNT_PRODUCT_VTS=01
# 실전(KIS_ENV=real)은 같은 4키를 _REAL 로 + KIS_HTS_ID_REAL → 아래 「실전 전환」 절

# DB (AWS RDS PostgreSQL — asyncpg DSN, 현재 정본)
DATABASE_URL=postgresql://user:pass@host:5432/dbname?sslmode=require

# Supabase — 런타임 미사용이지만 설정은 필수다 (src/config.py 의 supabase_url/supabase_key 가
#            기본값 없는 필드라 비우거나 지우면 기동 자체가 실패한다. src/db/supabase.py 롤백용
#            병존 — 어느 db 모듈도 값을 참조하지 않으므로 플레이스홀더 그대로 둬도 된다)
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-anon-key

# API 인증 (cycle243 / cycle249)
API_AUTH_KEY=                  # 필수. python3 -c "import secrets;print(secrets.token_urlsafe(32))"
API_ALLOWED_ORIGINS=           # 빈 값 = same-origin 전용(prod 는 비운다). * 는 무시된다
API_REPORTER_KEY=              # 빈 값 = 리포터 역할 비활성. 운영 키와 다른 값이어야 한다

# OpenAI (20:00 전략수정 AI자문 · 21:30 일일 로그 분석 · AI 매수평가 공용 키, 모델은 축이 둘)
OPENAI_API_KEY=
OPENAI_RECOMMEND_MODEL=gpt-5.6-luna    # 20:00 전략수정 AI자문
OPENAI_BUY_GATE_MODEL=gpt-5.6-luna     # AI 매수평가 (한쪽만 싼 모델로 옮길 수 있게 분리)
```

- ⚠️ **접미사 없는 키에 실제 값을 넣으면 무시된다.** `src/config.py` 가
  `os.getenv(f"{key}{_suffix}") or os.getenv(key)` 로 접미사 키를 **먼저** 읽고, `cp .env.example .env`
  로 만든 `.env` 에는 `KIS_APP_KEY_VTS=your_app_key_here` 같은 플레이스홀더가 이미 채워져 있어
  그쪽이 이긴다 → KIS 인증 실패. 대상 5키 = `KIS_APP_KEY` · `KIS_APP_SECRET` ·
  `KIS_ACCOUNT_NO` · `KIS_ACCOUNT_PRODUCT` · `KIS_HTS_ID`.
- `API_AUTH_KEY` 는 **필수**다. 없으면 `/health` 를 뺀 전 경로가 401 이다(아래 노트 박스).
- `API_REPORTER_KEY` 는 자동 리포트 루틴 전용 키다 — GET/HEAD 전체 +
  `POST /api/log-reports/{date}/external` **한 경로**만 통과하고 그 밖의 요청은 403 이다.

### 2. 데이터베이스 초기화

`supabase/migrations/` 하위 마이그레이션 파일을 대상 PostgreSQL(RDS)에 **번호 순으로 모두 실행**한다 (디렉토리명은 supabase/ 로 유지 — 스키마 SQL 정본). 목록을 손으로 고르지 말고 디렉터리를 전수 적용한다 — CI(`tests/integration/pg_harness.py`)와 자동 배포(`.github/workflows/deploy.yml`)도 `*.sql` 전수 적용이라 그것이 정본 집합이다:

```bash
# .env 는 파일일 뿐이라 셸에는 값이 없다 — 먼저 셸로 읽어들인다
set -a; source .env; set +a
psql "$DATABASE_URL" -c 'select 1'   # 접속 확인 (psql 미설치면 여기서 멈춘다)

# 한 파일이라도 실패하면 즉시 중단 — 부분 적용된 스키마를 남기지 않는다
for f in supabase/migrations/*.sql; do
  echo "apply $f"; psql -v ON_ERROR_STOP=1 "$DATABASE_URL" -f "$f" || break
done
```

파일 목록 (현재 `001`~`043`, 실제 집합은 디렉터리가 정본):

```
001_init.sql                          # 기본 테이블
002_multi_strategy.sql                # trade_history.strategy 컬럼 + daily_performance (date, strategy) 복합PK
003_trade_history_columns.sql         # trade_history 컬럼 보강
004_strategy_config.sql               # 전략 설정 영속화
005_system_config.sql                 # auto_start 등 시스템 설정
006_positions.sql                     # 포지션 영속화
007_parameter_recommendations.sql     # 전략수정 AI자문 이력
008_rename_momentum_breakout.sql      # 전략명 정리
009_performance_cashflow.sql          # 외부 입출금 + TWR
010_recompute_performance_fn.sql      # daily_performance 일괄 재계산 RPC
011_register_donchian_swing.sql       # 20일 신고가 스윙 전략 등록
012_recompute_prev_asset_fallback.sql # 분모 0 함정 차단
013_daily_log_reports.sql             # 일일 로그 분석 리포트
014_system_logs_index.sql             # system_logs 조회 인덱스
015_stock_master.sql                  # KIS CTPF1002R 캐시 (NXT 거래가능 사전 판별, 24h TTL)
016_recommendation_weights_review.sql # 자산배정 + 로직 자문 컬럼 (J4)
017_stock_master_ticker_normalize.sql # ticker 6자리 정규화 (12자리 pdno row 삭제 — NXT 사전판별 복구, Phase G2)
018_register_bull_flag_and_vcp.sql    # 신규 전략 2종 등록 (bull_flag_breakout / vcp_breakout)
019_backtest_runs.sql                 # 외부 MCP 백테스트 실행 영속화 (Phase 2)
020_parameter_recommendations_backtest.sql  # parameter_recommendations.backtest_summary JSONB (Phase 3)
021_weight_reasoning.sql              # parameter_recommendations.weight_reasoning 별도 사유 (cycle1)
022_market_regime_snapshots.sql       # 매크로 레짐 일일 스냅샷 (cycle2, 출처는 cycle315 부터 자체 macro 컨테이너)
023_cash_usage_ratio_range.sql        # cash_usage_ratio 범위 [0.5, 1.0] → [0.0, 1.0] 확장 (cycle2)
024_vb_board_stop_loss_defaults.sql   # VB 보드별 손절 디폴트 자동 복사 (cycle3)
025_external_integration_toggles.sql  # dkstock-regime(= 매크로 레짐) / kis-mcp 통합 DB-only 토글 (cycle5)
026_kis_quote_accounts.sql            # 보조 KIS 시세 수신 계좌 (cycle7-A, 풀 슬롯 41 × (1 + N) 확장)
027_buy_block_mode.sql                # 매수 가드 4 모드 (OFF/WARN/SOFT/HARD) + 4 임계값 (cycle8)
028_auto_apply_status.sql             # parameter_recommendations.status 에 'applied_auto' 분리 (cycle23 P3, AI 자문 자동 적용)
029_trade_history_dedupe_unique.sql   # (ticker, order_no, trade_type) 부분 UNIQUE 인덱스 (cycle30, 042700 핑퐁 INSERT 영구 차단)
030_strategy_funnel_snapshots.sql     # 조건검색 단계별 후보/탈락 종목 영구 추적 (cycle34)
031_daily_log_reports_openai_meta.sql # daily_log_reports 토큰/지연/비용 5 컬럼 (input/output/total_tokens, latency_ms, cost_estimate_usd)
032_stock_master_history.sql          # stock_master 갱신 이력 (cycle84)
033_stock_master_daily.sql            # KIS FHKST03010100 일봉 정규화 (PK ticker+bas_dd + OHLCV + raw JSONB, cycle122)
034_stock_master_master_raw.sql       # stock_master.master_raw JSONB + master_raw_updated_at (cycle129, KIS 공식 일일 마스터 파일)
035_strategy_funnel_snapshots_upsert.sql  # strategy_funnel UPSERT 전환 (cycle145, snapshot_at 키 폐기)
036_stock_master_history_seq.sql      # stock_master_history seq 컬럼 (cycle150)
037_stock_master_kospi200_kosdaq150.sql   # is_kospi200/is_kosdaq150 BOOLEAN + 부분 인덱스 (cycle153)
038_pending_next_day_clear.sql        # 익일청산큐 DB 영속화 PK(target_date, ticker, strategy_id) (cycle162, 재기동 보호)
039_stock_master_numeric_generated_cols.sql  # stock_master 시총/거래대금 numeric 생성 컬럼 + 인덱스 (cycle168, UI 필터 0건 시정)
040_funnel_provisional.sql            # strategy_funnel_snapshots.is_provisional (cycle171, 저녁 잠정 캡처 구분)
041_stock_master_financial.sql        # KIS 재무 5 TR 정규화 PK(ticker, stac_yymm, div_cls) + 18 NUMERIC + raw JSONB (cycleC1, 마법공식·F-Score-7 원천)
042_daily_log_reports_external.sql    # daily_log_reports ext_* 6컬럼 (cycle249 외부 리포터 루틴 쓰기 대상)
043_llm_buy_evaluations.sql           # AI 매수평가(LLM) — 주문이 나갈 때 남기는 기록 PK(trade_date, account_no, ticker, order_no) (cycle276, 관측 전용 — 매매 hot path 무관)
```

### 3. Docker Compose로 실행 (권장)

```bash
# 개발 환경 (hot-reload 지원)
docker compose up --build
```

- 개발: 프론트엔드 `http://localhost:3000`, 백엔드 `http://localhost:8002`

**프로덕션은 호스트 준비가 먼저다.** prod compose 의 frontend 는 호스트 디렉터리 두 개
(`secrets/`·`certbot-www/`)를 bind mount 하고, nginx 는 사이트 전체에 Basic Auth 를 건다
(`frontend/nginx.conf.template`). 준비를 빠뜨리면 사이트가 **403** 또는 **500** 으로 열린다 —
절차와 권한 값은 「배포 (AWS EC2)」 → 「배포 전 호스트 준비」에 한 번만 적어 두었다.
준비가 끝났으면:

```bash
docker compose -f docker-compose.prod.yml up --build -d
```

- 프로덕션: `http://localhost:80` (Nginx 정적파일 + API 프록시, 사이트 전체 Basic Auth). HTTPS(443)는 코드·절차만 준비된 상태이고 호스트 마커 파일로 켠다 — 아래 「TLS (HTTPS)」 절.
- **EC2 에서는 이 compose 명령을 직접 쓰지 않는다.** `bash tools/deploy/compose_up_changed.sh` 가 변경 경로로 모드를 고르고 TLS 오버레이까지 붙인다 — 아래 「수동 배포」 절.

### 3-1. 로컬 직접 실행 (Docker 없이)

```bash
# 백엔드 — .env 의 API_AUTH_KEY 가 채워져 있어야 한다(없으면 전 경로 401)
pip install -r requirements.txt
uvicorn src.main:app --host 0.0.0.0 --port 8001 --reload

# 프론트엔드 — vite 프록시가 서버 측에서 X-API-Key 를 넣으므로
#             .env 가 아니라 '프로세스 환경'에 같은 키를 실어 준다
cd frontend && npm install
API_AUTH_KEY="$(grep '^API_AUTH_KEY=' ../.env | cut -d= -f2-)" npm run dev
```

- 백엔드: `http://localhost:8001`, API 문서: `http://localhost:8001/docs`
- 프론트엔드: `http://localhost:3000`
- **포트는 8001 이어야 한다.** vite dev server 의 `/api` 프록시 타겟이
  `process.env.VITE_API_URL || 'http://localhost:8001'` 이고(`frontend/vite.config.ts`), 이 경로에는
  `VITE_API_URL` 이 없다 — 8000 에 띄우면 대시보드의 `/api` 호출이 전부 실패한다.

> **API 인증 (cycle243) — `.env` 에 `API_AUTH_KEY` 가 없으면 아무것도 안 열린다.**
> 백엔드는 **fail-closed** 라 키 미설정 시 `/health` 를 뺀 **전 경로**(`/docs`·
> `/openapi.json` 포함)가 401 이고, 기동 로그에 `[api_auth_key_missing]` CRITICAL 이
> 찍힌다. 개발용 기본키·모드 분기 예외는 두지 않는다.
> ```bash
> python3 -c "import secrets;print(secrets.token_urlsafe(32))"   # → .env 의 API_AUTH_KEY=
>
> # .env 에 넣은 값을 셸로 읽어들인 뒤 확인한다
> set -a; source .env; set +a
> curl -H "X-API-Key: $API_AUTH_KEY" http://localhost:8001/api/trading/status
> ```
> `npm run dev` 대시보드는 vite proxy 가 서버 측에서 헤더를 넣으므로 브라우저 설정이
> 필요 없다(`API_AUTH_KEY=… npm run dev` 로 프로세스 환경에만 넣으면 된다).
> **프로덕션(:80)** 은 nginx Basic Auth 가 앞단에 있어 `-u <USER>:<PASS>` 를 쓰고,
> X-API-Key 는 nginx 가 주입한다 — 포트마다 필요한 인증이 다르다.

### 3-2. 테스트 실행

```bash
pip install -r requirements-dev.txt    # 1회
python -m pytest -q                    # 백엔드 전체

cd frontend && npm install && npm test # 프론트엔드 전체
cd .. && npx playwright install && npx playwright test --config=e2e/playwright.config.ts  # E2E
```

- 백엔드 테스트는 DB·KIS 접속 없이 돈다 — KIS 호출은 가짜 응답으로 대체되고, 실 Postgres 가
  필요한 통합 테스트는 docker 도 `DATABASE_URL_TEST` 도 없으면 `skip` 한다
  (`tests/integration/pg_harness.py`).
- 변경한 부분에 걸린 테스트만 돌리려면:
  `pytest $(python tools/test_impact/affected.py origin/main --target=backend)`

## 사용 방법

### 모의투자 테스트

1. `.env`에서 `KIS_ENV=vts` 확인
2. 백엔드 + 프론트엔드 실행 — 「3. Docker Compose」(권장) 또는 「3-1. 로컬 직접 실행」 중 하나. 어느 쪽이든 브라우저로 `http://localhost:3000` 을 연다
3. 대시보드에서 [시작] 버튼 클릭 → 확인 모달에서 승인
4. 스케줄에 따라 자동매매 진행 — 07:45 자동 시작 + 부팅(`_boot()`) → 08:00 NXT 프리 진입 → 09:00~15:30 KRX 정규장(15:20 신규 매수 중단 + 강제 청산) → 15:40 NXT 애프터 보드(`post_nxt`) 진입 → 16:00 부터 주문·시세 거래소가 KRX 애프터마켓으로 전환(16:00~20:00 실시간 체결. 보드는 20:00 까지 `post_nxt` 그대로다) → 19:50 신규 매수 중단 → 20:00 매매 종료 → 21:30 정산 + 일일 로그 분석
5. [정지] 버튼으로 수동 중지 가능

### 대시보드 화면

메뉴는 상위 7개 2단 구성이다(cycle288) — 대시보드 · 거래 내역 · 로그 · **종목**{조건검색 추적, 종목마스터} · **전략**{전략 현황, 전략수정 AI자문} · 설정 · **운영상태**{장운영상태, 실시간 상태}. 아래 표의 화면 이름은 그 메뉴 라벨과 같다.

| 화면 | 기능 |
|------|------|
| 대시보드 (`/`) | 계좌 요약, 보유 종목(섹터·거래시장 + **종목별 손절가·목표가** — 값이 불확실하면 `—` 이고 고정%손절 근사는 「근사」 꼬리표가 붙는다), 매매 실적 차트, 상태 인디케이터, 조건검색 현황(전략별 스캔/타겟/스윙 깔때기), **`KisAccountPoolCard` 세션별 expand** (cycle35/37 — main/quote-N 종목 테이블 + WS tick / KIS 체결시각 / WS 의심 amber 배지) |
| 조건검색 추적 (`/strategy-funnel`) | 전략 dropdown + 날짜 picker + 단계별로 펼칠 수 있는 테이블(통과·탈락 종목 + 탈락 사유 표본) + 수동 실행 버튼 (cycle34) |
| 거래 내역 (`/history`) | **두 탭** — 주문체결내역(매수/매도 raw 행, 필터·페이징) / 매매손익(매수·매도 페어 1행, 가중평균. 보유 중은 open 페어로 미실현 손익 표시). 두 그리드 각 행 맨 끝에 **AI 매수평가 점수 배지 + 버튼 + 팝업**(`LlmScoreBadge` · `LlmEvaluationModal`) — 점수는 배지로 목록에서 바로 읽고(기록 없음 `·` / 평가 실패 `–` / 통과·차단은 색으로 구분), 버튼을 누르면 그 주문이 나갈 때 기록된 매수평가(사유·핵심 위험·무효화 조건·주문 스냅샷)를 주문번호로 조회한다. 메뉴의 「전략수정 AI자문」(20:00 파라미터 추천)과는 **다른 기능**이다. 기록이 없는 행의 버튼은 비활성이다(cycle276). ⚠️ 화면의 열 이름·버튼 라벨은 아직 「AI 자문」 이고 팝업 제목만 「AI 매수평가」 다 |
| 전략 현황 (`/strategies`) | 전략별 손절 임계 가시화 (`stop_loss_rate` 손절 임계 · `daily_loss_limit` 일일 손실 한도 · `trailing_stop_rate` 트레일링 임계 · `position_ratio` 종목당 포지션 비율) (cycle103) |
| 전략수정 AI자문 (`/recommendations`) | 20:00 OpenAI 자동 생성 자문 — 신규 자문 탭(승인/거절) + 이력 탭(상태/전략 필터). 자산 배정/로직 자문/비중 변경 사유(`weight_reasoning`) 별도 카드 + 백테스트 비교 카드(`BacktestComparisonCard`) |
| 로그 (`/logs`) | **두 탭** — 시스템 로그(기간·레벨·페이징) / 일일 로그 분석. 일일 로그 분석 = **21:30** 정산 직후 OpenAI 가 system_logs+trade_history 를 분석한 운영 개선 리포트(영업일 리스트 + findings + 메트릭). 20:05 metrics 1차 스냅샷이 같은 행을 먼저 채우고 21:30 완전판이 upsert 로 덮어쓴다. 구 `/log-reports` 북마크는 `/logs?tab=daily-report` 로 리다이렉트된다 |
| 종목마스터 (`/stock-master`) | KIS 마스터(시총·거래대금·NXT가능·거래정지·관리종목·KOSPI200/KOSDAQ150 플래그) + 일봉·시총 분포 카드 + 4종 필터(시장·시총·거래대금·종목명) + 수동 실행 버튼 4개(유니버스·기본정보·일봉·공식 마스터). 상단 진행률 배너(`RefreshProgressBanner`)는 5초마다 갱신된다 (cycle84+·127) |
| 장운영상태 (`/market-state`) | 「지금 시장은」(실시간 VI · 거래정지 · 서킷브레이커**(추정)** 배지 + 관측 커버리지 "이벤트 수신 N종목 기준" 항상 표시) + 「오늘 야간작업」 타임라인(`GET /api/market-ops` 14행 시각순, 상태 어휘 10종) + 장 운영 시간표 + 주문유형 카탈로그. 읽기 전용 — 작업 재실행 버튼은 없다 (cycle282·285) |
| 실시간 상태 (`/realtime-health`) | WebSocket 구독 슬롯(total/acked/fresh_60s/stale_60s/limit) + 세션별 종목 expand + KIS `inquire_ccnl` 캐시(last_cntg_hour·today_volume, TTL 5분) + 수동 재구독 버튼. 다섯 번째 카드 **「장운영 요약」**(VI 활성·거래정지·종목상태 이상 + 서킷브레이커 추정 배지 + 종목별 상세, 관찰 전용). 독립 화면 **장운영상태(`/market-state`)** 의 「지금 시장은」 과 **같은 응답**(`GET /api/realtime/market-operation`)을 쓰는 축약판이다 (cycle103+·186) |
| 설정 (`/settings`) | 전략 파라미터 조정, 자금 비중, 자동 시작 토글, 가격/거래대금 필터, 매수 가드 4모드(**표시/관찰 전용** — 매수를 차단·축소하지 않는다), 외부 통합 토글 |

### 실전 전환

```env
KIS_ENV=real
KIS_APP_KEY_REAL=실전용_앱키
KIS_APP_SECRET_REAL=실전용_시크릿
KIS_ACCOUNT_NO_REAL=실전_계좌번호
KIS_ACCOUNT_PRODUCT_REAL=01
KIS_HTS_ID_REAL=실전용_HTS_ID
```

- **접미사 키가 무접미사 키를 이긴다.** `src/config.py` 가 `KIS_ENV` 값으로 접미사를 고르고
  (`real`→`_REAL`, 그 밖→`_VTS`) `os.getenv(f"{key}{_suffix}") or os.getenv(key)` 순으로 읽는다.
  `.env.example` 에서 출발했다면 `KIS_APP_KEY_REAL=your_app_key_here` 같은 플레이스홀더가 이미
  있으므로, 무접미사 `KIS_APP_KEY=` 에 실전 키를 넣어도 조용히 무시된다 — **접미사 키 쪽을 고친다.**
- **`KIS_HTS_ID_REAL` 은 실전 필수다.** 실전 체결통보는 `H0STCNI0` + HTS ID 로 구독하므로
  미설정이면 부팅이 `RuntimeError("KIS_HTS_ID_REAL 미설정")` 으로 거부된다(체결통보 미구독 =
  포지션 등록·손절 불가라 조용히 넘어가지 않는다).
- `KIS_APP_KEY` · `KIS_APP_SECRET` · `KIS_ACCOUNT_NO` 는 기본값 없는 필수 설정이라 하나라도
  비면 설정 검증 단계에서 기동이 실패한다. **`SUPABASE_URL` · `SUPABASE_KEY` 도 같은 필수
  필드다** — 런타임에서 값을 읽는 db 모듈은 없지만 `src/config.py::Settings` 가 기본값 없이
  선언하므로, 「미사용」 이라고 지우면 기동이 실패한다(플레이스홀더 그대로 두면 된다).

> ⚠️ **실전 전환 전 확인** — 모의투자(`KIS_ENV=vts`)에서 최소 한 영업일 전체 주기(07:45 시작
> → 21:30 정산)를 돌려 체결·손절·정산이 모두 기록되는 것을 확인한 뒤에 전환한다.

## 매매 전략

> 이 문서에서 **보드(board)** 는 하루를 거래 시간대로 자른 단위를 말한다 — `pre_nxt`(NXT 프리
> 08:00~09:00) · `main`(KRX 정규장 09:00~15:40) · `post_nxt`(애프터 15:40~20:00).
> 전략마다 「어느 보드에서 새로 살 수 있는가」가 다르고, **매도·손절은 보드와 무관하게 항상
> 작동한다** — 유일한 예외는 NXT 프리장(08:00~09:00)의 **청산 평가 보류**다. 그 구간에는
> 틱이 왜곡돼 허깨비 손절이 나오므로 평가를 09:00 KRX 시세까지 미루고, 화이트리스트
> `risk._PRE_MARKET_EXIT_EVAL_STRATEGIES` 에 든 전략(현재 LTV 하나)만 보류 없이 평가한다.
> 보류하는 것은 **평가**이고 주문이 아니다 — 주문만 미루면 허깨비 신호가 09:00 에 실매도로 바뀐다.

```
                ┌───────────────────────────────────────────────────────────────────────────────────────────┐
                │                          StrategyRegistry (자금 분배)                                     │
                │                       순자산 × weight = 전략별 할당 자금                                  │
                └────┬───────────────┬───────────────┬────────────────┬───────────────┬───────────────┬─────┘
                     │               │               │                │               │               │
                     ▼               ▼               ▼                ▼               ▼               ▼
              ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
              │ momentum     │ │ volatility_  │ │ long_tail_   │ │ donchian_    │ │ bull_flag_   │ │ vcp_breakout │
              │ (상한가)     │ │ breakout     │ │ volatility   │ │ swing        │ │ breakout     │ │ (미네르비니) │
              ├──────────────┤ ├──────────────┤ ├──────────────┤ ├──────────────┤ ├──────────────┤ ├──────────────┤
              │ 진입 09:30~  │ │ 진입 09:01:30│ │ 진입 09:01:30│ │ 진입 09:05~  │ │ 진입 09:05~  │ │ 진입 09:05~  │
              │ 시그널: +29% │ │ 시그널: 시가 │ │ 시그널: 시가 │ │  09:30 시장가│ │   13:00      │ │   14:30      │
              │   돌파       │ │  + Range×K   │ │  + Range×K   │ │ 시그널: 20일 │ │ 시그널: 폴+  │ │ 시그널: VCP  │
              │ 손절 -7.5%   │ │ 보드별 손절  │ │ 당일 -3%     │ │   신고가+추세│ │   플래그 돌파│ │   베이스 돌파│
              │ 익일 청산    │ │ 15:20 강제   │ │ 상한가 도달→ │ │ 손절 -7%     │ │ 손절 -5%     │ │ 손절 -7%     │
              │ (갭/트레일)  │ │   청산       │ │   익일 청산  │ │ ATR×2 트레일 │ │ 측정된 이동+ │ │ ATR×2+50EMA  │
              │ 당일 매매    │ │ 당일 매매    │ │ 당일 또는    │ │ 멀티데이     │ │ ATR×2 트레일 │ │   이탈       │
              │              │ │              │ │ 익일 청산    │ │  (5~15일)    │ │ 5일 시간청산 │ │ 멀티데이     │
              └──────┬───────┘ └──────┬───────┘ └──────┬───────┘ └──────┬───────┘ └──────┬───────┘ └──────┬───────┘
                     │                │                │                │                │                │
                     └────────────────┴────────────────┴────────┬───────┴────────────────┴────────────────┘
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
| 종목군 | 등락률 순위 15%+ → 시총 1,000억+, 거래대금 200억+ |
| 매매 가능 보드 | **MAIN 단독**(09:00~15:39:59). 코드 기본값 `("krx_open","main")` 의 `krx_open` 은 옛 값이 호환용으로 남은 것이고, `_BOARD_SCHEDULE` 이 그 보드를 내보내지 않는다. 매수는 모듈 상수 `BUY_CUTOFF_KST = 15:20`(DB 설정으로 못 바꾼다)에서 끊긴다. 상한가 +29%는 KRX 기준이라 NXT 보드 제외 |
| 진입 조건 | 전일종가 대비 +29%(상한가) 돌파 |
| 매수 | 돌파 순간, 할당 자금 25% 비중 |
| AI 매수평가 | **적용** — 매수 주문 접수 직후 `llm_buy_gate.observe_order` 가 점수를 `llm_buy_evaluations` 에 남긴다(주문 1건 = 1행, 실패도 1행). `llm_gate_mode` 기본 `"shadow"` = 기록만, 매수 차단 없음. cycle297(2026-09-17)이 **7전략 전부**로 넓혔다 |
| 손절 | 매수가 대비 -7.5% |
| 청산 | **익일 청산** — 다음 영업일 NXT 프리(08:00) 시가 + 30초 안정화 후 갭상승 +10% → 트레일링 스탑 -2% / 그 외 즉시 매도. 전체 조건은 「NXT/KRX 통합 운영」의 「익일 청산 시점」 행에 있다 |
| 보유 기간 | 1영업일 (당일 매수 → 다음 영업일 NXT 프리 청산) |

### 전략 B: 변동성 돌파 (`volatility_breakout`)
| 구분 | 규칙 |
|------|------|
| 종목군 | 코스피+코스닥 전체, 시총/거래대금 필터, 노이즈 비율 기반 동적 K값 |
| 매매 가능 보드 | **MAIN only** — KRX ONLY 정책(cycle26). 시가 확정 09:00:05 / **매수 개시 09:01:30 ~ 15:20** — `open_entry_hold_secs = 90` 이 09:00 직후 90초 동안 신규 진입을 보류한다(0 = OFF, 장중 롤백 = `PUT {"open_entry_hold_secs":0}`). 목표가 = KRX 09:00 시가 + (전일 Range × `k_value_krx_main`, 기본 1.0). PRE_NXT/POST_NXT 매수 비활성 (보유 종목 손절/트레일링 매도는 보드 가드 무관 작동). `k_value_nxt_pre`/`k_value_nxt_post` 키는 DB/AI 자문 호환 보존만 |
| 진입 조건 | 현재가가 목표가(= KRX 09:00 시가 + 전일 Range × K값)를 돌파 |
| 매수 | 돌파 순간, 할당 자금 10% 비중. 기준가는 **KRX REST `stck_oprc`(시장 `J`) 단일 출처**다(`open_price_scope_mode = "enforce"`) — WebSocket 이 실어 온 시가는 거부되고, REST 로 시가가 아직 프린트되지 않은 종목은 그 시점 매수가 불가하다. `pre_nxt`/`post_nxt` 보드는 이 게이트 스코프 밖. **당일 매도한 종목은 재매수하지 않는다** |
| AI 매수평가 | 매수 주문이 KIS 에 접수된 **직후** `llm_buy_gate.observe_order` 가 LLM 점수를 `llm_buy_evaluations` 테이블에 남긴다(주문 1건 = 1행, 실패도 1행). `llm_gate_mode` 기본 `"shadow"` = **기록만 하고 매수를 막지 않는다**(`enforce` 미구현 — `shadow` 외 모든 값은 `off` 로 낙하). 롤백 = `PUT /api/strategies/{id}/params {"llm_gate_mode":"off"}` |
| 손절 | 매수가 대비 -3% |
| 청산 | **15:20 KRX 메인 일괄 청산** — 오버나이트 보유를 하지 않는다. 15:20 청산이 어떤 사정으로 누락되면 다음 영업일 NXT 프리에서 청산하는 안전망이 돈다(WARNING 로그). 두 규칙의 전체 조건은 「NXT/KRX 통합 운영」의 「15:20 강제 청산」·「익일 청산 시점」 행에 있다 |
| 보유 기간 | 당일 (오버나이트 없음) |

### 전략 C: 롱테일 변동성 돌파 (`long_tail_volatility`)
| 구분 | 규칙 |
|------|------|
| 종목군 | 변동성 돌파와 동일 + 연속상한가 종목 제외 |
| 매매 가능 보드 | **PRE_NXT(08:00~09:00) + MAIN + POST_NXT(15:40~20:00)** — 7 전략 중 LTV 만 세 보드 전부에서 신규 매수한다(연속 상한가 익일청산 + 야간 매수, cycle38). MAIN 은 시가 확정 09:00:05 / 매수 개시 09:01:30(`open_entry_hold_secs = 90`) ~ 모듈 상수 `MAIN_BUY_CUTOFF_KST = 15:20`, POST_NXT 매수는 19:50 `TIME_NXT_POST_BUY_STOP` 에서 끊긴다. 단 이 세 보드는 `DEFAULT_TRADABLE_BOARDS` **코드 기본값**이고 실제 허용 보드는 DB `strategy_config.params.tradable_boards` 가 덮어쓴다(운영 실측 `["main","pre_nxt"]` = 야간 매수는 이미 꺼진 상태). 상한가 모드 종목의 POST_NXT 시간대 손절 모니터링은 `risk.on_tick` 청산 평가가 보드 가드 무관 작동 |
| 진입 조건 | 변동성 돌파(목표가 = 보드별 시가 + 전일 Range × K값) + 전일대비 ≥ `min_prdy_rate`(기본 5%) |
| 매수 | 돌파 순간. `main` 보드 기준가는 VB 와 같은 **KRX REST `stck_oprc` 단일 출처**(`open_price_scope_mode`) — `pre_nxt`/`post_nxt` 보드는 스코프 밖 |
| AI 매수평가 | VB 와 동일 — 매수 주문 접수 직후 `llm_buy_gate.observe_order` 가 점수를 `llm_buy_evaluations` 에 기록한다. `llm_gate_mode` 기본 `"shadow"` = 기록만, 매수 차단 없음 |
| 손절 | 당일 모드 -3% / 익일 청산 모드 -5% |
| 청산 (당일 모드) | **15:20 일괄 청산** — 상한가 미도달 종목만이고, `check_force_clear()` 가 `_limit_up_reached` 종목을 제외한다 |
| 청산 (익일 청산 모드) | 다음 영업일 NXT 프리 시가(08:00) + 30초 안정화 후 갭상승 +10% → 트레일링 -2% / 그 외 즉시 매도. POST_NXT 시간대 시세 모니터링 손절 평가는 그대로 작동한다 |
| 모드 전환 | 당일 +29% 도달 → 익일 청산 모드(`_limit_up_reached` set 등록) |
| 보유 기간 | 당일 또는 1영업일 (상한가 도달 여부가 정한다) |

### 전략 D: 20일 신고가 스윙 (`donchian_swing`)
| 구분 | 규칙 |
|------|------|
| 종목군 | **코스피200 + 코스닥150 고정 유니버스** + 시총 컷 (거래량순위 API 미사용 — 추세추종 부적합 + 시점 의존 제거) |
| 매매 가능 보드 | MAIN 단독 — 추세추종은 일중 변동성 필요. NXT 프리/애프터 비활성. 보드 구간은 09:00~15:39:59, 실제 매수 창은 09:05~09:30(아래 매수 행) |
| 진입 조건 | 어제 종가가 20일 신고가 돌파 + 60일 EMA 우상향 + 종가>EMA + 거래대금 ≥ 20일평균×1.5 |
| 매수 | 다음 영업일 09:05~09:30 시장가, 1종목당 1회. **시가 갭상승 +3%↑ 시 스킵** (추격 방지) |
| AI 매수평가 | **적용** — 매수 주문 접수 직후 `llm_buy_gate.observe_order` 가 점수를 `llm_buy_evaluations` 에 남긴다(주문 1건 = 1행, 실패도 1행). `llm_gate_mode` 기본 `"shadow"` = 기록만, 매수 차단 없음. cycle297(2026-09-17)이 **7전략 전부**로 넓혔다 |
| 손절 | 매수가 대비 -7% 하드 손절. 터틀 매수(`_entry_atr` 스탬프가 있는 랏)는 대신 **2×ATR 하드손절 + -9% backstop**을 타고, 고점이 `매수가 + 1.5×entry_atr` 에 닿으면 손절선이 매수가로 승격된다(`breakeven_promote_atr`, 좁히는 방향만) |
| 청산 | 코드 평가 순서대로 ① **시간 청산** — `breakout_fail_n_days`(기본 5 **영업일**) 이상 보유 + 현재가 < 돌파고점 → STOP_LOSS ② **채널 이탈** — 최근 `channel_exit_period`(기본 10)일 저가 하회 → TRAILING_STOP ③ **ATR(14)×2 Chandelier 트레일링**(`high_since_buy − ATR×2`) → TRAILING_STOP |
| 보유 기간 | 멀티데이 (평균 5~15 영업일). DB `positions` 영속화로 일자 넘어 유지 |
| 종목명 | KIS `hts_kor_isnm` 우선 + `scanner.STATIC_TICKER_NAMES`(KOSPI200/KOSDAQ150 인라인 코멘트 자동 파싱)로 fallback |

### 전략 E: 눌림목 돌파 (`bull_flag_breakout`)
| 구분 | 규칙 |
|------|------|
| 종목군 | `stock_master.list_by_filter` — **전체 상장 유니버스**(시총 ≥ 100억 + 거래대금 ≥ 15억, ETF/ETN 제외, `max_scan_stocks` 4000). 지수 제약 없음 |
| 매매 가능 보드 | MAIN(09:05~13:00) |
| 진입 조건 | **폴 자동 검출**(직전 3~10영업일 누적 +15%↑, 음봉 비율 ≤ 45%) + **플래그 자동 검출**(2~10영업일 횡보, 조정 폭 ≤ 폴 폭의 50%, 거래량 < 폴 평균의 60%) → 플래그 상단(`flag_high`) 돌파 + 당일 거래량 ≥ `flag_avg_volume × 2`. 거래량은 **실시간 틱 누적(`tick_volume`) 단일 출처**이고 미관측은 매수 거부다(fail-closed). 거래량을 채워도 **추격 상한 `max_breakout_extension_pct` = 5.0%**(돌파선 대비 현재가)를 넘으면 매수하지 않는다 |
| 매수 | 종목당 1회 + 3영업일 쿨다운. 부분봉 가드(`candles[0]==오늘`이면 [1]부터) |
| AI 매수평가 | **적용** — 매수 주문 접수 직후 `llm_buy_gate.observe_order` 가 점수를 `llm_buy_evaluations` 에 남긴다(주문 1건 = 1행, 실패도 1행). `llm_gate_mode` 기본 `"shadow"` = 기록만, 매수 차단 없음. cycle297(2026-09-17)이 **7전략 전부**로 넓혔다 |
| 손절 | 매수가 대비 -5% / 플래그 하단(`flag_low`) 이탈 → STOP_LOSS |
| 청산 | 측정된 이동(`flag_high + (pole_high - pole_start)`) 도달 → 1차 절반 청산(`_partial_exit` 마킹, 1차 구현은 전량) → 잔여 `high_since_buy − ATR×2` 트레일링 / 5영업일 시간 청산 (캘린더일 +2 보정) |
| 보유 기간 | 단기 (평균 1~5 영업일) |

### 전략 F: 변동성 수축 돌파 (`vcp_breakout`, 미네르비니식)
| 구분 | 규칙 |
|------|------|
| 종목군 | **전체 상장 유니버스**(지수 제약 없음 — `is_kospi200/is_kosdaq150=None`) → 시총 ≥ 100억 + 거래대금 ≥ 10억 컷, 일봉은 `daily_fetch_depth_mode` 가 정한다(기본 `"cap100"`=100봉 / `"full"`=`장기EMA+베이스최대+10`) |
| 매매 가능 보드 | MAIN(09:05~14:30) |
| 진입 조건 | **추세 필터**(종가 > 50EMA > 150EMA > 200EMA + 장기 EMA 1개월(20영업일) 우상향 — 런타임 장기선은 읽은 봉 수가 정한다 — `effective_ema_long = min(장기EMA 설정값, 가용길이 − 25)` 이고 그 값이 30 미만이면 후보에서 탈락한다. `daily_fetch_depth_mode="cap100"`(기본, 100봉)에서 설정 50/150/200 은 실효 **50/65/75** 로 계산되고, `"full"` + 보유 225봉이면 설정 그대로 **50/150/200** 이다) → **베이스 자동 검출**(25~75영업일, 깊이 ≤ 30%) → **pullback 점진 수축**(ATR threshold ZigZag 검출 `min_swing_atr_mult=1.0`, 2~4회, 직전 대비 폭 감소, 마지막 ≤ 12%) → **거래량 수축**(마지막 5일 평균 < 베이스 직전 20일 평균 × 70%) → 베이스 상단(`base_high`) 돌파 + 당일 거래량 ≥ 20일 평균 × 1.5. 거래량은 **실시간 틱 누적(`tick_volume`) 단일 출처**이고 미관측은 매수 거부다(fail-closed). 거래량을 채워도 **추격 상한 `max_breakout_extension_pct` = 7.5%** 를 넘으면 매수하지 않는다 |
| 매수 | 종목당 1회 + 7영업일 쿨다운 |
| AI 매수평가 | **적용** — 매수 주문 접수 직후 `llm_buy_gate.observe_order` 가 점수를 `llm_buy_evaluations` 에 남긴다(주문 1건 = 1행, 실패도 1행). `llm_gate_mode` 기본 `"shadow"` = 기록만, 매수 차단 없음. cycle297(2026-09-17)이 **7전략 전부**로 넓혔다 |
| 손절 | 매수가 대비 -7% / 베이스 하단(`base_low`) 이탈 → STOP_LOSS |
| 청산 | `high_since_buy − ATR×2` 트레일링 / 50일 EMA 이탈 → TRAILING_STOP. **시간·15:20 청산 없음** — 멀티데이 보유 (`Position._MULTIDAY_STRATEGIES` 멤버) |
| 보유 기간 | 멀티데이 (VCP 통상 2~6주) |

### 전략 G: 고지로 대순환 스윙 (`kojiro`, 이동평균선 대순환)
| 구분 | 규칙 |
|------|------|
| 종목군 | **전체 상장**(`is_kospi200/is_kosdaq150=None`, `max_scan_stocks≥3577`) → 시총/거래대금 컷 → 일봉 100일(`min_required=80`) → **ATR/종가 변동성 밴드 1.0~6.0%**(비협상 판별 필터. 상한 6.0 의 근거 = 백테스트 PF 1.60) |
| 매매 가능 보드 | MAIN(09:05~09:30) |
| 진입 조건 | **strict entry(4조건 AND)**: ① 현재 스테이지1(EMA 단기>중기>장기) ② 최근 5영업일 내 6→1 전환 인접(신선도 `stage1_freshness=5`) ③ EMA 5/20/40 모두 우상향 ④ 전일 종가 > EMA5. 갭업 ≥5% / 갭다운 ≤-4% / 장중 붕괴(현재가<시가) 스킵 |
| 매수 | 종목당 1회. **터틀 유닛 sizing 은 배선까지 완료된 opt-in** — DB `sizing_mode = "turtle"` 이면 `compute_unit_qty_guarded`(유닛 리스크 `risk_pct` 0.5%)가 수량을 정하고, 코드 기본값은 `position_ratio` 다. Phase 2 로 연기된 것은 조기진입·피라미딩뿐이며, `max_units_per_stock`/`max_units_total` 은 소비처 0건(미배선)이라 리스크 한도로 오인하면 안 된다 |
| AI 매수평가 | **적용** — 매수 주문 접수 직후 `llm_buy_gate.observe_order` 가 점수를 `llm_buy_evaluations` 에 남긴다(주문 1건 = 1행, 실패도 1행). `llm_gate_mode` 기본 `"shadow"` = 기록만, 매수 차단 없음. cycle297(2026-09-17)이 **7전략 전부**로 넓혔다 |
| 손절 | 고정 % -8%(ATR 독립 backstop) / 2ATR 하드손절(tighten-only) → STOP_LOSS |
| 청산 | 스테이지3 진입(추세 종료, 익일 아침 발화) / `high_since_buy − 2.5×ATR` 트레일링 → TRAILING_STOP. **시간·15:20 청산 없음** — 멀티데이 |
| 보유 기간 | 멀티데이 (`_MULTIDAY_STRATEGIES` 멤버). 지표 순수모듈 `kojiro_indicators.py`(Wilder ATR ewm(1/20)) |

> 프론트엔드 Settings 페이지에서 전략별 자금 비중 조절 가능. 대시보드 "조건검색 현황 → 20일 신고가 스윙" 탭에서 8단계 깔때기 통계 + 후보 종목 진입상태(보유 중 / 진입 대기 / 갭 스킵 / 장 시작 전 / 진입 시간 종료) 시각화. `bull_flag_breakout`·`vcp_breakout`·`kojiro` 는 **코드 등록 기본값**이 `enabled=False, weight=0.0` 이다 — Settings 에서 수동 활성화 권장 (백테스트/모의 검증 후). ⚠️ **가동 여부와 비중의 정본은 DB `strategy_config`(= Settings 화면)** 다. 부팅 시 `_load_strategy_config` 가 DB 행으로 `enabled`/`weight` 를 무조건 덮어쓰므로, 위 표의 코드 기본값을 현재 운영 상태로 읽으면 안 된다

### 매매 안전장치

> **자주 나오는 말** — **fail-open**: 판단에 필요한 값이 없으면 **막지 않고 현행대로 둔다**
> (잘못 막으면 매매가 통째로 멈추는 자리에 쓴다). **fail-closed**: 값이 없으면 **하지 않는다**
> (잘못 나가면 돈이 나가는 자리에 쓴다). **stale**: 시세가 한동안 안 들어와 값이 낡은 상태.
> **race**: 두 일이 거의 동시에 끝나 순서가 뒤집히는 상황. **래치**: 한 번 켜지면 그날은 계속
> 켜져 있는 표시.

| 항목 | 동작 |
|------|------|
| 체결통보 구독 (제거 금지) | 메인 세션이 `H0STCNI0`(실전)/`H0STCNI9`(모의) 체결통보를 단독 구독한다. 미구독이면 체결을 받지 못해 포지션 등록과 손절이 아예 불가하다 |
| 주문번호 매핑 (제거 금지) | `_order_qty`/`_order_strategy`/`_order_ticker`/`_order_exchange`/`_pending_buy_orders` 등록은 `place_order` 응답 직후 **동기 영역**에서 끝난다(`await insert_trade` 진입 전). 시장가 즉시체결로 체결통보가 REST 응답보다 먼저 와도 매핑이 보장된다 — 누락되면 그 거래가 기본값 전략("momentum")으로 잘못 기록된다 |
| WebSocket 구독 한도 | `MAX_SUBSCRIPTIONS = 41`(KIS 공식 한도, 세션당). 보유·익일청산 종목(HIGH)은 `bypass_limit=True` 로 한도 검사를 건너뛰어 **절대 보장**하고, 후순위(LOW)만 drop 하면서 `[priority_drop]` 로 남긴다. HIGH 단독으로 41 을 넘으면 ERROR |
| 일일 상태 초기화 (제거 금지) | 정산 뒤 `_reset_daily_state()` 가 전 전략의 positions·pending_buys·pending_buy_amounts·sold_today 와 주문번호 매핑·매도 거부 트래커를 일괄 clear 한다. 빠뜨리면 그 상태가 다음 날까지 잔류한다 |
| 종목코드 형식 비대칭 | 진입 단계는 6자리 숫자만(`isdigit`) — ETF·신주인수권·임시 코드 매수 차단. 사후처리(체결통보·잔고 sync)는 6자리 영숫자(`isalnum`) 허용 — 외부 경로로 들어와도 좀비 포지션 방지 |
| 매수가능 캐시 | 60초 TTL — KIS `get_buyable()` 호출을 매 틱 → 분당 1회로 축소 |
| 잔고부족 매수 락 | 900초 — `is_insufficient_cash` 응답 또는 `max_buy_quantity≤0` 시 다음 잔고 sync까지 매수 차단 |
| 매도 잔고부족 즉시 break | `is_insufficient_quantity` 응답 시 3회 재시도 생략 + 메모리·DB positions 정리 |
| 체결통보 race 가드 | 시장가 즉시체결 시 체결통보가 REST 응답보다 먼저 와도 `_completed_orders` set + 보정 INSERT로 PENDING 잔존 차단 |
| 진입 차단 | VB/LTV `_scan_universe`의 `list_by_filter` 후보 + `scanner.scan_stocks` 모두 `ticker.isdigit()` 검증 |
| 보드 가드 | `RiskManager.on_tick`에서 매수 신호 평가 전 `session_tracker.is_tradable(strategy_id, params)`로 현재 활성 보드가 전략 `tradable_boards`에 포함됐는지 확인 — 비활성 보드에서는 신호 평가 자체 skip |
| 매수 수량 1주 fallback (전략 잔여 자금 기준) | `position_ratio × total_investment // current_price = 0`이어도 **전략 잔여 자금**(= `total_investment` − 해당 전략 보유 `buy_price×qty` 합 − 해당 전략 `pending_buy_amounts` 합)이 1주를 감당하면 1주 매수. **7 전략 전부** `calc_buy_quantity()` 의 모든 return 이 `StrategyBase._apply_budget_limit()` 공통 관문을 지나고, 비중 기준 0주일 때 그 관문이 `_fallback_one_share()` 로 위임한다(**분기 순서가 계약** — 전략이 이 헬퍼를 직접 부르지는 않는다). 기존 고정 `total_investment` 직접 비교 → 자금 90% 점유 후 추가 1주 매수로 **전략 한도 초과**하던 결함 차단(2026-05-11 P1). ⚠️ 1주 폴백은 무조건이 아니다 — 아래 두 랏 상한이 폴백 **뒤에** 걸린다 |
| 랏당 최대 유닛 상한 (`max_lot_units`, K=2.0) | `sizing_mode="turtle"` 전략의 **모든** 매수 랏을 `floor(K × 예산 × risk_pct ÷ ATR)` 주 이하로 자르고, 그 값이 0 이면 매수하지 않는다. `min` 연산이라 수량을 늘리는 방향은 없다. ATR 결측·모호(`atr`↔`atr14` 불일치)·`risk_pct ≤ 0`·예외는 fail-open(현행 수량 유지 + `[fallback_cap_skipped]` WARNING) |
| 랏 명목 상한 (`max_lot_ratio_mult`, K_ρ=2.5) | **7 전략 모든 랏**의 명목을 `cap_qty = int(K_ρ × int(예산 × position_ratio)) // 현재가` 로 자르고, **1주도 못 사면 매수하지 않는다**. 비중 수량·터틀 수량은 이미 명목 상한 안이라 항등적으로 무접촉이고 **실효 대상은 1주 폴백 랏**이다 — 주가가 컷오프보다 비싼 종목은 폴백 매수가 막힌다. 키 부재 = OFF, 판정 실패는 fail-open(`[ratio_cap_skipped]`) |
| 시각이 거래소를 정한다 | `_route_exchange_by_clock` 이 시각 리터럴 없이 `market_state.MARKET_TABLE` 에서 경계를 파생해 주문 거래소를 고른다 — 프리장 08:00~09:00 은 base(NXT) 유지, 정규장과 KRX 애프터마켓은 KRX. 호가유형도 구간별로 갈린다: 프리장 매수는 `step_up(현재가,5)` 지정가 `00`(실전·NXT·시행일 이후면 NXT 프리마켓 전용호가 GTP `27` 로 승격 — 미체결 잔량을 거래소가 프리마켓 종료 08:50 에 일괄취소하고, 거부되면 같은 가격 `00` 으로 1회 재주문) / 프리장 매도는 `step_down(현재가,5)` / 정규장은 시장가 `01` → 거부 시 지정가 `00`. 킬스위치 = 전략 `DEFAULT_PARAMS` 의 `order_exchange_clock_mode`(기본 `enforce`) |
| KRX 애프터마켓 청산 호가유형 | KRX 애프터마켓(16:00~20:00)에서 청산은 **최유리지정가 `44`(`ORD_UNPR=0`) → 거부 시 `41` 지정가 + `step_down(현재가,5)`** 로 나간다. `44` 는 시장가가 아니라 반대편 최우선호가 지정가라 실질 최악이 1틱이다. 킬스위치 = `after_market_exit_division`(기본 `"44"`, 허용값 `44`/`41`). 종목당 5회 실패면 그날 포기 래치 + `[after_exit_giveup]` CRITICAL, NXT 폴백 실패는 익일 청산으로 전환 |
| NXT 거래가능 사전 판별 (Phase G) | KIS `CTPF1002R` 응답 `cptt_trad_tr_psbl_yn=="Y" AND nxt_tr_stop_yn=="N"`로 `nxt_tradable` 파생. `stock_master` 테이블(24h TTL)에 캐시. `OrderEngine._strategy_exchange_async`가 `nxt_tradable=False`면 NXT/SOR → KRX 강제 다운그레이드 + `[nxt_downgrade]` 로그. `scheduler._execute_next_day_clear`는 1순위 판별로 사용 → 시가 폴링/안정화 거치지 않고 즉시 보류(NXT 주문 시도 0). `execute_sell`이 NXT 시간대 매도 거부 받으면 `stock_master.upsert_one(nxt_tradable=False)` 사후 보강 |
| 매도 거부 단일 정책 | KIS 가 매도를 거부하는 네 가지 상황을 `src/engine/sell_rejection.py::SellRejectionTracker` 한 곳에서 처리한다. 거부 종류마다 **다시 시도하지 않는 시간(TTL)** 이 다르고, 마지막 수단은 익일 청산이다 — 표 아래 「매도 거부 처리 규칙」 참조 |

#### 매도 거부 처리 규칙

- **장 시간이 아니라는 거부**(`is_market_closed_rejection`) — 판정은 msg_cd 가 아니라 msg1 의
  「장운영시간이 아닙니다」 류 키워드다(같은 APBK0918 이 보유부족·자금부족에도 쓰인다. 실제로
  받은 msg_cd 는 APBK0918 · KIOK0320 둘). KRX 정규장(09:00~15:30)에서 받았으면 **5분** 뒤
  재시도하고(일시 장애로 보고 손절 의무를 지킨다), NXT 시간대(08:00~09:00 / 15:30~20:00)에서
  받았으면 **다음 KST 09:00** 까지 쉰다.
- **시장가를 못 받는다는 거부**(`is_market_order_disallowed` — APBK1943 / APBK3013) — `step_down`
  5호가 지정가로 **한 번** 더 시도하고, 결과와 무관하게 **30초** 쉰다. NXT 시간대 폴백이
  실패하면 `_pending_next_day_clear` 에 등록해 다음 영업일 09:00 KRX 시장가 일괄 청산으로 넘긴다.
- **잔고가 모자란다는 거부**(`is_insufficient_quantity`) — 보유 목록에서 즉시 빼고
  (`[positions_reconciliation]` INFO) 잔고를 **1회** 다시 읽는다. 실제 잔량이 남아 있으면 로그로
  알리고 **자동 재등록은 하지 않는다**(운영자 확인).
- 재시도를 쉬는 동안(`is_blocked`)은 KIS 를 부르지 않고 조용히 건너뛴다 — 종목·일자당 INFO
  1줄(`[market_closed_blocked]`)만 남는다. TTL 이 자연 만료되면 게이트가 스스로 풀린다.
- 위 상태는 `OrderEngine.reset_daily_state()` 가 정산 때 일괄 clear 한다. 2026-05-31 에 10분 동안
  매도 거부 500건이 쏟아진 운영 사고가 이 정책의 출발점이다.

## NXT/KRX 통합 운영 (08:00~20:00)

KIS OpenAPI 가 NXT(넥스트레이드 ATS) 주문·시세를 정식 지원하므로 KRX 메인장 밖 NXT 프리/애프터 시간대에도 매매한다. 2026-09-14 부터는 KRX 애프터마켓(16:00~20:00, 실시간 연속체결)이 신설돼 그 시간대 주문·시세가 KRX 로 나간다.

**매매 정책 = KRX ONLY · 보드 3개**(`pre_nxt`/`main`/`post_nxt`). 신규 매수는 KRX 메인 단독이 원칙이고(`momentum`·`volatility_breakout`·`donchian_swing`·`bull_flag_breakout`·`vcp_breakout`·`kojiro` 의 `tradable_boards` 가 MAIN 계열), PRE_NXT/POST_NXT 의 나머지 활동은 보유 종목 매도(손절/트레일링)다. **예외 = `long_tail_volatility`** — `tradable_boards=("pre_nxt","main","post_nxt")` 로 PRE_NXT·POST_NXT 신규 매수를 한다(cycle38). LTV 의 MAIN 보드 매수는 모듈 상수 `MAIN_BUY_CUTOFF_KST = 15:20` 에서 끊긴다 — 보드 자체는 15:39:59 까지 MAIN 이지만 15:20 뒤 체결은 오버나이트로 남기 때문이다(cycle286).

| 항목 | 사용 |
|------|------|
| 시세 채널 | **KRX 전용 `H0STCNT0` + NXT 전용 `H0NXCNT0` 2채널**(cycle293·294). `H0…` 는 KIS 가 실시간 데이터 종류마다 붙인 코드다. **어느 채널을 쓸지는 시각이 정한다** — 프리장은 NXT, 정규장·애프터마켓은 KRX(`scanner.tick_tr_id_for(ticker, *, priority, now)`). 통합 채널 `H0UNCNT0` 은 `stock_master.nxt_tradable=False` 종목의 체결을 아예 보내지 않아 폐기했다. ⚠️ **다만 그 폐기가 실제로 적용되는 모드는 `enforce` 뿐이다.** 통합 채널이 그대로 나가는 분기가 셋 남아 있다 — `off`(롤백) · `observe`(다크런치 = **배포 기본값**) · `enforce_low` × HIGH(보유·익일청산은 스코프 밖). 즉 **배포만으로는 아무 일도 일어나지 않는다** — 07:45 부팅 전에 `system_config.tick_channel_resolver_mode` 를 `enforce` 로 올려야 2채널이 실제로 적용된다. 전환 창은 `tick_channel_clock.switch_windows()` 가 시장 시간표에서 파생한다(시각 리터럴 0건). **전환은 아침 창(`pre_to_krx`) 1회뿐이고 후보(LOW)·보유(HIGH)가 같다.** 15:30~16:00 은 완전 휴식이라 주문을 내지 않으므로, 그 20분의 KRX 커버리지 공백은 수용한 비용이다(사용자 결정 2026-09-15 — 되돌리기 전에 `_workspace/00_URGENT_WORKLIST.md` 를 확인한다). 끄는 방법 = `PUT /api/realtime/tick-channel-mode`(`system_config.tick_channel_resolver_mode`) |
| 통합 장운영정보 / VI | `H0UNMKO0` — ① **보드 전환 수신용** 대표 종목 `005930` 1건 (실전 한정). `MKOP_CLS_CODE`(110/112/121/129/130~159) 가 시장 전체 공통이라 1종목으로 전체 보드 전환을 받는다. ② **VI·서킷브레이커 수신용 HIGH 종목**(보유 + 익일청산) — leaf `src/engine/market_op_subscribe.py::subscribe_market_operation_tickers` 가 보조 세션에 델타 배치한다. 후보(LOW)는 구독하지 않고 관측 카운트만 남긴다. SessionTracker 가 시각 기반 tick + H0UNMKO0 코드 동시 사용 |
| 주문 라우팅 | `place_order(..., exchange=...)` body 에 `EXCG_ID_DVSN_CD` (`KRX`/`NXT`/`SOR`). 모의(VTS) 는 KRX 만 허용 — SOR/NXT 는 실전 한정. **시각이 거래소를 정한다**(cycle287): `order_engine._route_exchange_by_clock(base, *, side, mode, now)` 가 `market_state.MARKET_TABLE` 에서 경계를 뽑아 판정한다(그 함수 안 시각 리터럴 0건) — 프리장(PRE_NXT 활성 ∧ MAIN 비활성)은 base(NXT/SOR) 유지(`pre_nxt_keep`), 그 밖에는 KRX 가 받는 주문유형이 있으면 `("KRX", "krx_by_clock")`, 없고 NXT 만 있으면 base 유지(`krx_unsupported_keep`), 예외는 fail-open(`probe_error`). 실행값 = 15:45·15:55 `krx_unsupported_keep` / 16:05·19:00 `krx_by_clock`. 킬스위치 `order_exchange_clock_mode`(기본 `enforce`)·`after_market_exit_division`(기본 `"44"`) 은 `param_catalog` 등재라(둘 다 `risk="identity"` = 화면 저장 시 2단계 확인, `auto_tunable=False`) `PUT /api/strategies/{id}/params` 로 장중 조정된다 |
| 조회 거래소 옵션 | `get_balance(afhr_flpr=...)` — `N`(정규장)/`Y`(시간외)/`X`(NXT 정규장). `get_daily_orders(exchange="ALL")` — KRX+NXT+SOR 합산 |
| 보드 추상화 (cycle26, 3 보드) | `src/engine/session.py::MarketBoard` enum 활성 3 보드: `pre_nxt` (08:00~09:00) / `main` (09:00~15:40) / `post_nxt` (15:40~20:00). `_BOARD_SCHEDULE` 도 3 구간. `krx_open`/`krx_after` enum 값은 *호환성 보존* (실제 스케줄 미사용). `SessionTracker` 30s 주기 tick + `register_board_handler` 콜백 |
| 전략별 매매 가능 보드 | `DEFAULT_TRADABLE_BOARDS` — `momentum`: KRX_OPEN+MAIN (코드 enum 유지, 활성 보드는 MAIN) / **`volatility_breakout`: MAIN only** / **`long_tail_volatility`: PRE_NXT+MAIN+POST_NXT (연속 상한가 익일 청산 + 야간 매수)** / `donchian_swing`·`bull_flag_breakout`·`vcp_breakout`·`kojiro`: MAIN only. `session.py` 의 fallback dict `_DEFAULT_TRADABLE_BOARDS` 는 momentum·VB·LTV·donchian 4전략만 담고, BFB·VCP·kojiro 는 각 전략 파일의 `DEFAULT_PARAMS["tradable_boards"]`(전부 `("main",)`) 로 결정된다 |
| VB/LTV K값 | `k_value_krx_main` (기본 1.0) — KRX 09:00 시가 기준. 보드별 K 키는 `_BOARD_K_KEY` 가 고른다(`main`→`k_value_krx_main` / `pre_nxt`→`k_value_nxt_pre` / `post_nxt`→`k_value_nxt_post`). **VB 는** 보드가 `("main",)` 라 뒤 두 키가 곱해지는 경로가 없어 DB/AI 자문 응답 호환 보존만이고(`param_catalog` `deprecated_for=("volatility_breakout",)`), **LTV 는 프리·애프터 목표가에 실제로 곱한다** |
| 익일 청산 시점 | 다음 영업일 NXT 프리 첫 거래(08:00 부근) + 30초 안정화 후 청산 (`NEXT_DAY_STABILIZE_SECS=30`). 대상 = `momentum` · `long_tail_volatility` 상한가 모드 · `volatility_breakout` **안전망**(VB 는 오버나이트를 하지 않는다 — 시세 미수신·시장가 거부·재시작 race 로 15:20 청산이 누락된 비상 상황에서만 `_execute_next_day_clear` 가 받아 WARNING 과 함께 청산한다) |
| 15:20 강제 청산 | `_force_clear_main_only` — 대상은 VB·LTV 두 전략이고 각 전략의 `check_force_clear()` 가 목록을 정한다. VB = 전량. LTV = `_limit_up_reached`(상한가 모드) 종목만 제외하고 나머지는 청산한다 — **POST_NXT 가 `tradable_boards` 에 있어도 보유가 유지되지 않는다**(cycle142). **시간 가드**: 함수 진입 시 `>=15:30` 이면 즉시 skip + 익일 청산 안전망 위임 |
| 스윙 일중 시세 REST 폴링 | `_swing_rest_poll_loop` — **2단 창**(cycle222-a): **09:00:30~09:30 = 보유 종목 전용 + stale 중립**(`SWING_REST_POLL_EARLY_START` — 09:00:30 부터 도는 이유는 WS 무송출(no_feed) 보유 종목의 시가 직후 손절 사각을 줄이기 위해서다. 'stale 중립' 인 이유는 REST 가 `ticker_last_tick` 을 갱신하면 개장 러시 blind 종목이 '신선'으로 보여 강제 재구독이 안 걸리기 때문이다) / **09:30~15:20 = 전체 폴**(후보 포함 + `last_tick` 갱신). 대상 전략 = `_SWING_POLL_STRATEGIES = ("donchian_swing", "kojiro")` — **BFB·VCP 는 비멤버라 REST 보강이 없고 틱으로만 매수 평가한다**(미구독 = 매수 기회 완전 상실). 60s 주기로 `_scanned_tickers ∪ positions ∪ pending_buys` 합집합을 `fetch_stock_detail` 폴링 → `scanner.ticker_prices` 갱신 + `ticker_last_tick` touch + `ticker_names` 보강. 보유 종목만 `RiskManager.on_tick` 호출로 기존 트레일링/-7% 손절 평가 재사용. WS stale 시 ATR 트레일링 평가 끊김 차단 (2026-05-15 결함 B) |

## API 엔드포인트

> **인증 전제** — 아래 전 경로는 `X-API-Key` 헤더가 필수다. `/health` 만 예외다
> (`src/middleware/api_auth.py::EXEMPT_PATHS`). 상태변경(POST/PUT/PATCH/DELETE)은 Origin
> 검사도 통과해야 한다. 상세 = 위 「API 인증 (cycle243)」 절.

| Method | URL | 설명 |
|--------|-----|------|
| GET | `/health` | 헬스 체크 — 무인증으로 통과하는 유일한 경로 |
| POST | `/api/trading/start` | 자동매매 시작 |
| POST | `/api/trading/stop` | 자동매매 정지 |
| POST | `/api/trading/restart` | 자동매매 재기동 |
| POST | `/api/trading/manual-sell` | 수동 매도 (시장가) |
| GET | `/api/trading/status` | 현재 상태 조회 |
| GET | `/api/trading/positions` | 보유 포지션 상세만 (BalanceTable 전용 분리) |
| GET | `/api/trading/orders` | 주문 추적 상태만 (OrderMonitor 전용 분리) |
| GET | `/api/balance` | 잔고 조회 (예수금 + 보유종목, 종목별 NXT/KRX 거래시장 정보 join) |
| GET | `/api/balance/buyable` | 매수 가능 금액 조회 |
| GET | `/api/history?page=&size=` | 거래 내역 (페이징) |
| GET | `/api/history/pnl?page=&size=&strategy=&ticker=` | 매매손익 — 매수/매도 페어 1행 (포지션 0 사이클 단위 가중평균). 보유 중은 open 페어 (미실현 손익은 `ticker_prices` 현재가) |
| GET | `/api/llm-evaluations?order_nos=<CSV>&trade_date=` | **cycle276** AI 매수평가 배치 요약 — 키는 `"<trade_date>\|<order_no>"` 복합 키다(같은 주문번호가 여러 날짜에 있으면 날짜마다 한 키). 거래 내역 두 그리드의 AI 매수평가 버튼 활성 판정용. CSV 는 공백·중복 제거 후 1~200개(0개·초과 422), `trade_date` 형식 위반 422 |
| GET | `/api/llm-evaluations/{order_no}?trade_date=` | **cycle276** 단건 상세 (모달 본문) — 화이트리스트 53키 사영, 계좌번호는 `account_no_masked` 로만 나간다. 기록 없음 404 / DB 예외 500 (두 경우를 섞지 않는다) |
| GET | `/api/performance/summary` | 실적 요약 (TWR 누적 + 일평균 실현 수익률) |
| GET | `/api/performance/daily` | 일별 실적 (실현손익 기반 + TWR 누적 + 외부 입출금) |
| POST | `/api/performance/recompute` | trade_history 기반 daily_performance 전체 소급 재계산 (멱등) |
| GET | `/api/strategies` | 전략 목록 + 비중 + 상태 + 타겟가 + 스윙 `scan_stats` 깔때기 |
| GET | `/api/strategies/params-schema` | cycle278 파라미터 카탈로그 전체 + 전략별 적용 키·현재값·기본값. 편집 폼은 **이 한 응답**으로 렌더한다 (키·범위·선택지 프론트 하드코딩 금지) |
| GET | `/api/strategies/te?months=3` | cycleF 전략별 TE(트레이딩 예지치)/RR(손익비) 최근 N개월(`months`×30일) 지표 — 관찰 전용, 5분 프로세스 캐시. 전략별 계산 실패는 그 전략만 빈 값으로 격리 |
| PUT | `/api/strategies/weights` | 전략별 비중 수정 (매수금액 하한선 검증). body `{weights: {strategy_id: ratio}}` — **단위는 비율 `0.0~1.0`, 퍼센트(0~100) 금지**(2026-08-18 확정). 범위 위반 422, Σ>1.0 은 `success=false`(저장 미수행), 부분 payload(Σ<1) 허용. `GET /api/strategies` 의 `weight` 와 단위가 같아 왕복 항등 |
| PUT | `/api/strategies/{id}/params` | 전략 파라미터 수정 (부분 dict **병합** — 요청에 없는 키는 보존). **미지 키·읽기 전용 키·자료형·선택지·범위·예산 불변식 위반은 422 다**(cycle278). 오류가 하나라도 있으면 아무것도 저장하지 않는다. 알 수 없는 전략 id 는 200 + `success=false` |
| GET | `/api/strategies/system/auto-start` | 자동 매매 설정 조회 |
| PUT | `/api/strategies/system/auto-start` | 자동 매매 설정 변경 |
| GET | `/api/strategies/system/cash-usage-ratio` | 매매 가용 자금 비율 조회 (J3, 2026-05-12) |
| PUT | `/api/strategies/system/cash-usage-ratio` | 매매 가용 자금 비율 변경 — body `{ratio}` 는 **비율 `0.0~1.0`**(퍼센트 아님), `0.05` 단위로 자동 반올림한다. 범위 밖이면 400. 다음 영업일 `_boot()` 부터 반영. 하한이 0.0 인 이유 = 방어 레짐 자동 조정이 0.25 를 넣기 때문이다 |
| GET | `/api/logs` | 시스템 로그 조회 |
| GET | `/api/logs/search?q=&level=&start=&end=&limit=` | 시스템 로그 키워드 검색 (대소문자 무시 부분일치). `limit` 1~1000 / 기본 200. 응답 `{logs, total, has_more}` |
| GET | `/api/recommendations` | 전략수정 AI자문 목록 (최근 30일) |
| GET | `/api/recommendations/{id}` | 단일 자문 상세 |
| POST | `/api/recommendations/{id}/apply` | 선택한 키만 전략 파라미터에 적용. **J4(2026-05-12)** — body 옵션 `apply_weight: bool=False`. true 면 `recommended_weight` 가 strategy_config.weight 로 반영 (다음 영업일 _boot 부터). 자동 적용 없음, 운영자 명시 토글에서만 |
| POST | `/api/recommendations/{id}/reject` | 자문 전체 거절 |
| GET | `/api/log-reports?days=30` | 일일 로그 분석 리포트 목록 |
| GET | `/api/log-reports/bundle?date=` | 분석 입력 번들 — 20:20 KST 클라우드 루틴이 읽는 유일한 입력 경로 |
| GET | `/api/log-reports/{YYYY-MM-DD}` | 단일 영업일 리포트 상세 |
| POST | `/api/log-reports/run?force=0` | 수동 트리거 — 즉시 분석 실행. **기본은 비파괴다**(cycle283): 오늘 **완성** 리포트가 이미 있으면 재분석을 실행조차 하지 않고 `success=false` 를 돌려준다. 막지 않는 네 경우 = 행이 없음 · 20:05 1차 스냅샷만 있는 구간(`metrics.snapshot_pass`) · `summary` 가 비었거나 OpenAI 실패 placeholder 인 날 · `model` 이 비어 LLM 경로가 돌지 않은 행. 덮어쓰려면 `?force=1` — 단 21:30 정산 뒤의 force 는 `api_metrics`/`strategy_funnel` 을 0 으로 덮는다 |
| POST | `/api/log-reports/{YYYY-MM-DD}/external` | 외부 분석 결과 저장 — 리포터 스코프 키(`API_REPORTER_KEY`)의 **유일한 쓰기 경로**(cycle249). findings 는 OpenAI 경로와 같은 정규화기를 거친다 |
| GET | `/api/system/memory` | 프로세스 메모리 (RSS/VMS·스레드·열린 파일·소켓). `MEMORY_PROFILE=true` 면 tracemalloc top 20 동봉 |
| GET | `/api/system/metrics` | endpoint 별 응답시간 분포 (p50/p95/p99 + count/min/max) — `MetricsMiddleware` 누적값 |
| POST | `/api/system/metrics/reset` | 누적 metrics 초기화 (실험 베이스라인 리셋용) |
| GET | `/api/system/price-filter` | 가격 필터 조회 — `{min_price, max_price}`, 0 = 비활성 |
| PUT | `/api/system/price-filter` | 가격 필터 부분 갱신 (cycle64 — `None` 인 키는 기존 값 보존). scanner 캐시를 즉시 무효화해 **즉시 반영**된다. 음수·`max_price < min_price` 는 400, 미지 키는 422 |
| GET | `/api/system/trade-amount-filter` | 거래대금 필터 조회 — `{min_amount}`, 0 = 전체 통과 |
| PUT | `/api/system/trade-amount-filter` | 거래대금 필터 부분 갱신 (cycle65 — 작전주·저유동성 차단). scanner 캐시 즉시 무효화, 음수는 400, 미지 키는 422 |
| GET | `/api/realtime/subscriptions` | WebSocket 구독 슬롯 진단 (total/acked/fresh_60s/stale_60s/limit/tickers/reconnect_count/ws_connected) + cycle35/37: `sessions[*].tickers_detail` (ticker/ticker_name/stale/last_tick/retries/last_resub/`last_cntg_hour`/`today_volume`). KIS `inquire_ccnl` 캐시(TTL 5분 + cap 20)로 KIS 실제 체결시각 동봉 — WS 구독 의심 진단용 |
| POST | `/api/realtime/resubscribe` | stale(60s 미수신) TICK 구독 종목 즉시 일괄 재구독 (J2). 응답 `{resubscribed, tickers}`. F1 자동 재구독과 별개의 운영자 수동 트리거 (ScanMonitor 인라인 버튼). WebSocket 끊김 시 400 |
| POST | `/api/realtime/channel-probe` | **cycle253** KRX/NXT 단독 채널(`H0STCNT0`/`H0NXCNT0`) 프로브 시작. body `{ticker, tr_id}`. 이미 라이브 구독·보유·익일청산·매수 후보인 종목은 409 로 배제한다 — 프레임이 실제로 오면 `risk.on_tick` 이 그대로 돌기 때문 |
| GET | `/api/realtime/channel-probe` | 진행 중인 프로브 상태 폴링 (읽기 전용, 구독 변경 0) |
| DELETE | `/api/realtime/channel-probe/{ticker}` | 프로브 종료 — 세션 전수 순회로 구독 해제. 프로브가 없으면 404 (조용한 200 금지). 응답 `removed_from` = 실제 해제된 세션 라벨 |
| GET | `/api/realtime/market-operation` | 장운영상태(VI·거래정지·종목상태·서킷브레이커) 현황 — 관찰 전용, 매수 가드와 연결되지 않는다. `summary`(`vi_active_count`/`halt_active_count`/`iscd_stat_active_count` + `circuit_breaker` 휴리스틱) + `details`(종목별 vi_code/halt_yn/halt_reason/mkop_cls_code, cap 200). `H0UNMKO0` 모니터가 원천이다(cycle149·186). 장운영상태 화면의 「지금 시장은」 과 실시간 상태 화면의 「장운영 요약」 카드가 이 한 응답을 함께 쓴다 |
| GET·PUT | `/api/realtime/tick-channel-mode` | **시세 채널 장중 킬스위치.** GET 은 현재 모드·전환 다이얼·그날 전환 창을 돌려준다. PUT body `{mode}` ∈ `off`/`observe`/`enforce_low`/`enforce` (어휘 밖 값은 422). DB 저장과 엔진 메모리 반영이 **같은 요청에서** 끝나 재시작이 필요 없다. 선택 필드는 `switch_enabled`(전환만 정지) **하나**뿐이고 생략하면 현행 값 무접촉. ⚠️ **그 둘 밖의 키는 422 가 아니라 조용히 무시된다** — 같은 요청의 `mode` 킬스위치까지 막으면 안 되기 때문이다(pydantic `extra=ignore`). 모르는 키를 보내면 `success:true` 를 받고 아무 일도 일어나지 않는다 |
| GET | `/api/market-state?on_date=` | cycle282 거래소 장 운영 표 전체 + KRX·NXT 커서 + 주문유형 카탈로그. 표는 코드 상수라 DB 장애와 무관하게 살아 있다 — 휴장일 조회 실패는 `is_trading_day=null` + 200. `on_date` 로 다른 날짜 미리보기(오늘 ±365일, 범위 밖 422 · 그 날짜에 유효 행 0 이면 404 · **오늘** 표가 비면 500) |
| GET | `/api/market-ops` | cycle285 「오늘 야간작업」 타임라인 14행 (상태 10종 — 예정/진행/완료/실패/건너뜀 2종(신선·주간)/덮어씀/미발화/휴장/확인불가). 예정 시각은 `scheduler.TIME_*` 에서만 읽는다(시각 리터럴 0건). 읽기 전용 — 재실행 버튼 없음 |
| GET | `/api/backtest/mcp/health` | 외부 MCP 백테스트 서버 헬스체크. `KIS_MCP_ENABLED=false`(기본)면 외부 호출 0회로 `reachable=false`. 어떤 경우에도 200 (graceful) |
| GET | `/api/market-regime/current` | 현재 매크로 레짐 + `cash_usage_ratio` + `auto_regime_adjust` + ETF 레짐(관찰). 🔴 `buy_blocked` 는 **항상 false** — 레짐은 매수에 개입하지 않는다(cycleI). `block_reason` 은 관찰용 사유로만 남는다 |
| GET | `/api/market-regime/history?days=30` | `market_regime_snapshots` 최근 N일 (`days` 는 1~365 로 클램프) |
| GET | `/api/strategy-funnel?strategy_id=&target_date=` | cycle34: 전략별 조건검색 단계별 후보/탈락 종목 (`survived_tickers` cap 200 / `excluded_sample` cap 20) |
| GET | `/api/strategy-funnel/recent?strategy_id=&days=7` | 최근 N영업일 추이 |
| POST | `/api/strategy-funnel/snapshot` | 수동 trigger — `scheduler.capture_funnel_snapshots(registry, is_provisional=False)` 로 09:30 자동 hook 과 같은 단계별 + `step_no=99` 캡처. prepare 는 재실행하지 않고 최근 결과(`_funnel_steps`)만 담는다. 응답 `{target_date, saved_count, count}` |
| GET·PUT | `/api/integrations/dkstock-regime` | 매크로 레짐 활성 토글(출처 = 자체 `macro` 컨테이너. 슬러그·변수명은 DB 행과 짝이라 유지). DB 우선 / `.env` fallback. 활성화 시 백그라운드 fetch 발화, 비활성화 시 메모리 레짐 리셋. 매크로 fetch 실패는 graceful(토글 자체는 성공) |
| GET·PUT | `/api/integrations/kis-mcp` | 외부 백테스트 MCP 서버 활성 토글. 즉시 fetch 없음 — 백테스트는 20:00 자문 시점에 발화한다 |
| GET·PUT | `/api/integrations/auto-regime-adjust` | 매크로 레짐에 따라 `cash_usage_ratio` 를 자동 갱신할지 토글. 다음 영업일 `_boot` 부터 반영. **새로 쓰는 코드는 이 경로를 쓴다**(Settings 화면도 이쪽). 별칭 `PUT /api/market-regime/auto-adjust` 는 같은 키·같은 동작으로 남아 있다 |
| GET·PUT | `/api/integrations/etf-regime` | 지수ETF 고지로 스테이지 레짐 **관찰** 토글 (기본 false, `.env` fallback 없음). 매수에 개입하지 않는다 |
| GET·PUT | `/api/integrations/buy-block` | 매수 가드 모드(`OFF`/`WARN`/`SOFT`/`HARD`) + 임계값 4종. **표시 전용**이다 — 매수 게이트는 없다(cycleI). PUT 범위 위반 422 (VIX [10,50] · FG_high [50,100] · FG_low [0,50]) |
| GET·PUT | `/api/integrations/auto-apply` | 전략수정 AI자문 자동 적용 토글 (기본 false). ON 이면 20:00 자문 직후 비중 감액(50% cap) + 보수적 파라미터를 자동 적용한다 |
| GET·PUT | `/api/integrations/krx-open-api` | KRX 정식 OPEN API 설정 (활성·`base_url`·key). **응답은 key 마스킹 전용**(`****1234`, 평문 미노출). 이 토글이 `scanner._full_universe_load_krx_primary`(전체 유니버스 적재 **주 소스**)를 켠다 — 끄면 KIS 시가총액 폴백으로 degrade 한다(2026-08-08 실측 3,577→60종목) |
| GET·POST | `/api/integrations/quote-accounts?active_only=false` | 보조 KIS 시세 수신 계좌 목록·등록 (cycle7-A). **app_secret 평문은 절대 노출하지 않는다**(마스킹). POST 201 / label 중복 409 / 빈 값 422. 매매·잔고 활용 0 — 시세 수신 풀 전용 |
| PUT·DELETE | `/api/integrations/quote-accounts/{account_id}` | 보조 계좌 `active` 토글·`label` 수정 / 계좌 제거. 200/404/409. `app_key`·`app_secret` 수정은 미지원 — 삭제 후 재등록한다(감사 추적성) |
| GET | `/api/portfolio/risk` | 전 전략 포트폴리오 리스크 **관찰 스냅샷** (cycleH Phase 1). 매수 차단 0 — registry·순자산·섹터 조회가 전부 graceful 이라 이 라우트의 실패가 매매를 멈추지 않는다 |
| GET | `/api/stock-master/stats` | cycle84+ — KIS 마스터 분포 (전체/거래정지/관리종목/NXT가능/KOSPI200/KOSDAQ150 등) |
| GET | `/api/stock-master/list?market=&min_market_cap=&min_trade_amount=&name_substr=&limit=&offset=` | 종목마스터 페이징 목록 (cycle128 — 4 필터). `limit` 1~1000 / 기본 100, `offset` 기본 0, 응답에 `total` 동봉. 시가총액·거래대금 단위는 **억원** |
| POST | `/api/stock-master/refresh-universe` | 전체 종목 풀 수동 갱신 (BackgroundTasks, cycle90/127) |
| POST | `/api/stock-master/basics/refresh` | KIS CTPF1002R 매스 보강 수동 trigger (BackgroundTasks, cycle126/127) |
| POST | `/api/stock-master/daily/refresh` | 일봉 적재 수동 trigger (KIS FHKST03010100, cycle122/127) |
| POST | `/api/stock-master/master/refresh` | KIS 공식 일일 마스터 파일 다운로드 + master_raw 갱신 (cycle129) |
| GET | `/api/stock-master/refresh-progress` | 4 작업 통합 진행률 (5초 폴링 endpoint, cycle127/129) |
| GET | `/api/stock-master/scan-pool/summary` | 오늘 KST `[scan_pool_eager_refresh]` 발생 카운트 (cycle83) |
| GET | `/api/stock-master/{ticker}/history` | 종목별 마스터 변경 이력 (`changed_at` DESC, `limit` 1~1000 / 기본 100) |
| GET | `/api/stock-master/{ticker}/daily` | 종목 일봉 최근 N일 (`days` 1~100 / 기본 30). 미적재 404 · DB 예외 500 (404 위장 금지) |
| GET | `/api/stock-master/{ticker}` | 종목마스터 단건 조회. 미존재 404. POST 전용 경로를 GET 하면 405 |

## 프로젝트 구조

```
auto_stock/
├── src/                       # 백엔드 (FastAPI)
│   ├── main.py                # 앱 엔트리포인트
│   ├── config.py              # 환경 설정
│   ├── auth/                  # KIS OAuth 인증
│   ├── api/                   # KIS REST API 호출
│   ├── realtime/              # KIS WebSocket 실시간 (시세·체결통보 + 세션 풀)
│   ├── engine/                # 매매 엔진 (전략/주문/리스크/스케줄러)
│   ├── db/                    # RDS PostgreSQL CRUD (asyncpg, pg.py)
│   ├── middleware/            # API 인증(X-API-Key) 최외곽 미들웨어
│   ├── services/              # 외부 서비스 클라이언트 (백테스트 MCP · 매크로 레짐 · 보조 세션 health)
│   ├── routes/                # FastAPI 라우트
│   └── models/                # Pydantic 데이터 모델
├── frontend/                  # 프론트엔드 (React)
│   └── src/
│       ├── api/               # API 호출 함수
│       ├── components/        # UI 컴포넌트
│       ├── contexts/          # 전역 상태 (TradingStatusContext, 5초 폴링)
│       ├── pages/             # 페이지
│       ├── utils/             # 공통 유틸 (KST 포맷 등)
│       └── types/             # TypeScript 타입
├── tests/                     # 백엔드 테스트 (pytest)
├── e2e/                       # Playwright E2E
├── tools/                     # 배포 판정(deploy) · TLS 운영(ops) · 영향 인덱스(test_impact)
├── supabase/migrations/       # DB 마이그레이션
├── docs/
│   ├── kis/                   # KIS API 스펙 문서
│   ├── architecture.md        # 시스템 흐름 도식 (정본)
│   ├── HARNESS_CHANGELOG.md   # 사이클별 변경 이력 (verbatim 정본)
│   └── backtest-monitoring.md # 외부 백테스트 운영 가이드
├── .github/workflows/         # CI · 자동 배포 · 영향 인덱스
├── .claude/                   # Claude Code 하네스 (에이전트팀 + 스킬 + 슬래시 명령)
│   ├── agents/                # 8개 전문 에이전트 정의
│   ├── skills/                # 10개 도메인 스킬
│   └── commands/              # 슬래시 명령 (/sync-docs)
├── Dockerfile                 # 백엔드 Docker (dev/prod 멀티스테이지)
├── docker-compose.yml         # 개발 환경 Docker Compose
├── docker-compose.prod.yml    # 프로덕션 환경 Docker Compose
├── docker-compose.tls.yml     # TLS 1단계 오버레이 (443 병행)
├── docker-compose.tls2.yml    # TLS 2단계 오버레이 (80→443 + HSTS)
├── requirements.txt           # Python 의존성
├── requirements-dev.txt       # 테스트/개발 전용 의존성
├── pyproject.toml             # pytest 설정 (마커 · 테스트당 60s timeout)
└── .env                       # 환경 변수 (git 미추적)
```

> **문서 안의 번호·기호 읽는 법** — `cycleNNN` 은 이 프로젝트의 개발 사이클(변경 단위) 번호이고
> (초기 사이클 일부는 `cycleI`·`cycleC1` 처럼 글자를 쓴다), 원문 이력은
> [`docs/HARNESS_CHANGELOG.md`](docs/HARNESS_CHANGELOG.md) 에 있다. `D6`·`Q1`·`P1`·`J4`·`INV-1`
> 같은 기호는 그 사이클 안에서 쓰인 결정·항목 번호라 **본문을 읽는 데 필요하지 않다** —
> 근거를 되짚을 때만 changelog 에서 찾는다.

## 에이전트팀 (Claude Code 하네스)

이 프로젝트는 Claude Code의 서브에이전트 + 스킬 시스템을 활용한 **다중 에이전트 협업 구조**로 개발·운영된다. 사용자 요청 유형에 따라 오케스트레이터 스킬이 적합한 에이전트와 스킬을 자동 호출한다.

### 에이전트 (`.claude/agents/`) — 8명

| 에이전트 | 역할 | 모델 | 호출 시점 |
|---------|------|------|---------|
| **team-leader** | 트레이더 출신 팀장 — 매매 규칙 *정의 + 감독*, 작업 분배, 산출물 검수. 모든 사용자 요청의 1차 진입점 | opus | 전체 요청 |
| **domain-expert** | 데이/스윙 트레이더 출신 *깊이있는 자문* — 신규 전략, 파라미터 결정, 시장 미시구조, 보드 행태, 시장 레짐, KIS 거부 해석 | opus | Phase 2.5 명세 분해 *전* + 사이클 중 행위 영향 평가 |
| **tdd-engineer** | Red 테스트 선작성 + Green 검증 + 영향 인덱스 갱신 (KIS MCP 응답 시리즈 합성 포함) | opus | 모든 코드 변경의 TDD 사이클 입구 |
| **backend-dev** | FastAPI + KIS OpenAPI + 매매 엔진 + WebSocket + RDS PostgreSQL(asyncpg, `src/db/pg.py`). 신규 API 통합 시 KIS MCP 정본 확인 | sonnet | Red 테스트 수신 후 Green 구현 |
| **frontend-dev** | React 트레이딩 대시보드 (구동 관리, 실적/잔고, 거래 내역, Settings) | sonnet | UI Red 테스트 수신 후 Green 구현 |
| **tester** | 사후 통합/경계면/E2E/안전성. KIS MCP 응답을 정본으로 양쪽 동시 읽기 | opus | 모듈 완성 후 통합 검증 |
| **refactor-expert** | *주기적* 코드 품질 검토 — 중복/명명/모듈 비대화/dead code/아키텍처 드리프트. 카드 단위 분할 + 위험 등급 + 회귀 가드 동반 | opus | Phase 4.5 — 사이클 5회 누적 또는 명시 요청 |
| **report-writer** | 긴 작업 주기 끝의 쉬운 말 보고서(HTML 아티팩트) + 원문 md + 결정 카드. 두 번째 임무 = `/sync-docs` 문서 동기화 실행 주체 | opus | Phase 5 — 사이클 3회 이상 연속 · 자율 진행 구간 종료 · 사용자 "리포트" 요청 (`cycle-report` 스킬) / Phase 4.8 문서 동기화 |

### 스킬 (`.claude/skills/`) — 10개

| 스킬 | 용도 | 트리거 키워드 |
|------|------|--------------|
| **auto-trading-orchestrator** | 8명 에이전트 조율 — TDD 사이클 + 도메인 자문 + 리팩토링 검토 통합 | "자동매매 시스템 구축", "전략 추가", "리팩토링", "도메인 자문" |
| **tdd-cycle** | Red→Green→Refactor 사이클 표준화 (pytest+respx+freezegun / vitest+RTL+MSW) | "TDD", "테스트 먼저", "Red/Green", "회귀 테스트" |
| **test-impact-index** | source↔test 정적 의존성 인덱스 (백엔드 Python AST + 프론트엔드 TS imports) | "영향 테스트", "변경 영향 분석", "인덱스 재생성" |
| **kis-api-integration** | KIS OAuth/REST/WebSocket/TR_ID 변환 등 연동 코드 | "KIS API", "주식 주문", "잔고 조회", "실시간 시세" |
| **trading-dashboard** | React 대시보드 화면 구현 | "대시보드", "화면", "UI", "차트" |
| **trading-test** | KIS 연동/주문 흐름/DB 정합성 통합 테스트 + Playwright E2E | "테스트", "검증", "QA", "정합성 확인" |
| **domain-consult** | domain-expert 자문 요청 흐름 — 매매 의사결정 깊이 자문 | "도메인 자문", "트레이더 시각", "파라미터 근거", "시장 미시구조" |
| **refactor-review** | refactor-expert 주기적 검토 흐름 — 행위 보존 카드 단위 권고 | "리팩토링", "코드 정리", "중복 제거", "구조 개선", "모듈 분해" |
| **kis-mcp-query** | KIS Code Assistant MCP (`mcp__kis-code-assistant__*`) 활용 가이드 — 공식 저장소 `koreainvestment/open-trading-api` 기반. backend-dev / tdd-engineer / tester / refactor-expert 공유 | "KIS 응답 재확인", "TR_ID 확인", "KIS 스펙 정본" |
| **cycle-report** | report-writer 호출 흐름 — 주기 마무리 보고서(쉬운 말 아티팩트 + 원문 md + 결정 카드) | "리포트", "보고서", "정리해 줘" |

### 협업 규약

- **CLAUDE.md 계층**: 루트 `CLAUDE.md` + 디렉토리별 `CLAUDE.md` (`src/`, `src/engine/`, `src/engine/strategies/`, `src/api/`, `src/db/`, `src/routes/`, `src/realtime/`, `src/auth/`, `src/models/`, `frontend/`) 가 모듈별 컨벤션·금지사항·연동 규칙의 진실의 원천
- **단일 책임**: 각 에이전트는 자신의 역할 범위 안에서만 파일 수정. 경계면 변경(API 응답 스키마 등)은 backend-dev 가 정의 → frontend-dev 가 타입 동기화
- **검수 흐름**: 매매 규칙 변경 → (선택) domain-expert 자문 → team-leader 명세 → tdd-engineer Red → backend-dev/frontend-dev Green → tester 검증 → (사이클 5회 누적) refactor-expert 검토 → `/sync-docs` 문서 동기화 (Phase 4.8 — 코드가 바뀐 사이클은 커밋 **전** 필수, 실행 주체 = report-writer) → (트리거 충족 시) `cycle-report` 로 report-writer 마무리 보고 (Phase 5)
- **KIS MCP 통합**: 신규 API 통합 / 응답 분기 / 회귀 시나리오 합성 / 응답 처리 통일 시 `kis-mcp-query` 스킬 — `docs/kis/` 로컬 캐시와 MCP 응답 불일치 시 *MCP 가 정본*

## 프로세스 구성과 분리 로드맵

현재 운영 프로세스는 컨테이너 2개다 (`docker-compose.prod.yml`).

```
            ┌────────────────────┐        ┌──────────────────────────────┐
            │  frontend          │  /api  │  backend (uvicorn 단일 워커) │        ┌───────────────────┐
            │  nginx + SPA       │───────▶│  시세 감시 · 전략 판정 ·     │◀──────▶│  KIS OpenAPI      │
            │  Basic Auth        │        │  주문 · 정산 · 관측이 한 곳  │        │  REST · WebSocket │
            └────────────────────┘        └───────────────┬──────────────┘        └───────────────────┘
                                                          │ asyncpg
                                                          ▼
                                             ┌────────────────────────┐
                                             │   AWS RDS PostgreSQL   │
                                             └────────────────────────┘
```

매매에 필요한 모든 일이 한 프로세스 안에 있어서, 프롬프트 한 줄만 고쳐도 backend 전체를
재시작해야 한다(재시작 1~5분 동안 시세를 못 받는다). 그래서 보유 포지션이 있는 장중에는
배포 자체가 금지돼 있다. 그 결합을 단계적으로 푸는 계획이 아래다.

| 단계 | 무엇을 떼나 | 상태 |
|------|-------------|------|
| 1 | **AI 매수평가** — 매수 주문 직후 LLM 이 점수를 매겨 기록만 하는 관찰 기능(실매매 미개입)을 `llm_worker` 컨테이너로 분리. 큐는 별도 메시지 브로커가 아니라 `llm_buy_evaluations` 테이블(043) | **진행 중** |
| 2 | 20:00 전략수정 AI자문 · 21:30 로그 분석 · 외부 백테스트 | 계획 |
| 3 | 시세 감시 ↔ 전략 판정 ↔ 주문 완전 분리 | **보류** |

3단계를 보류한 이유는 REST 초당 20건 한도, 토큰 발급 분당 1건 가드, 체결통보의 메인 세션
단일 강제, 매수 수량 계산의 원자성 — 이 네 가지가 모두 **한 프로세스 안에서만** 성립하는
장치이기 때문이다. 가르려면 넷을 프로세스 밖으로 옮기는 별도 설계가 먼저 필요하다.

단계별 도식(0~3단계)과 근거가 되는 파일·행은
[`docs/architecture.md` 15장 — 프로세스 분리 로드맵](docs/architecture.md#15-프로세스-분리-로드맵-2026-09-11) 에 있다.

## 배포 (AWS EC2)

### 서버 구성
- **인스턴스**: EC2 t4g.small (2vCPU, 2GB RAM, ARM)
- **리전**: ap-northeast-2 (서울) — KIS WebSocket 지연 최소화
- **OS**: Ubuntu 24.04 LTS, Docker 설치 완료
- **접속**: `http://<EC2_IP>` (Nginx 80포트, 사이트 전체 Basic Auth). TLS 활성 시 `https://auto.dkstock.cloud` (443 병행)

#### 배포 전 호스트 준비 (하드 게이트)
prod compose 의 frontend 는 호스트 디렉터리 두 개를 bind mount 한다. 아래를 먼저 만들지
않으면 사이트가 403/500 으로 열리지 않거나 인증서 첫 발급이 막힌다. **이미 구축된 서버라면
0번은 건너뛰고 1) 부터 확인한다.**

```bash
# 0) 최초 1회 — 코드 받기 + 환경 변수 배치 (Docker 는 설치돼 있다고 가정)
git clone <repo-url> ~/auto_stock
cd ~/auto_stock
cp .env.example .env && vi .env      # KIS 키·DATABASE_URL·API_AUTH_KEY 를 채운다

# 1) nginx Basic Auth 자격 — 비밀은 argv 에 싣지 않는다(ps·셸 히스토리 노출)
mkdir -p secrets && chmod 755 secrets
read -r -p 'basic auth user: ' AUTH_USER
read -r -s -p 'basic auth password: ' AUTH_PASS; echo
printf '%s:%s\n' "$AUTH_USER" "$(printf '%s' "$AUTH_PASS" | openssl passwd -apr1 -stdin)" \
  > secrets/.htpasswd
chmod 644 secrets/.htpasswd; unset AUTH_PASS

# 2) ACME(HTTP-01) 챌린지 webroot — TLS 첫 발급의 전제
mkdir -p certbot-www
```

- 권한 `755 secrets` + `644 secrets/.htpasswd` 는 **필수**다. nginx worker 는 컨테이너 안 **uid 101**, 호스트 파일은 `ubuntu`(uid 1000) 소유라 `700`/`600` 이면 자격 요청이 전부 **500** 이 된다.
- 자격 파일이 아예 없으면 자격을 보낸 요청이 **403** 이다. 무자격 요청은 어느 상태에서도 401 이라 그것만으로는 결손을 판별할 수 없다.
- `certbot-www` 를 미리 만들지 않으면 Docker 가 bind mount 소스를 `root:root` 로 만들어 `ubuntu` 가 쓰지 못한다.
- `secrets/` 는 **git 커밋 금지** (`.gitignore` 등재).

### 자동 배포 (CI/CD)
`git push origin main` → CI(`CI — Build & Test`) 성공 → Deploy(`workflow_run` 트리거) → EC2 자동 배포.

```
git push → CI 성공 → Deploy → SSH → EC2
                                     ├─ git pull
                                     ├─ psql 로 supabase/migrations/*.sql 순차 적용
                                     └─ bash tools/deploy/compose_up_changed.sh (모드 판정)
```

- **CI 가 실패하면 배포는 자동 skip** 된다 (Deploy 조건 = CI `conclusion == success` + `event == push`).
- `**.md` · `docs/**` · `_workspace/**` 만 바꾼 push 는 CI `paths-ignore` 때문에 **CI/Deploy 자체가 뜨지 않는다**.
- 배포는 동시성 그룹 `deploy-ec2` 로 직렬화된다 (진행 중 run 은 취소하지 않는다).

GitHub Secrets 필요: `EC2_HOST`, `EC2_USERNAME`, `EC2_SSH_KEY`, `SUPABASE_DB_URL`
— `SUPABASE_DB_URL` 은 이름만 유지하고 **값은 RDS DSN** 이다. `git pull` 직후
`supabase/migrations/*.sql` 을 psql 로 순차 적용하며, secret 또는 psql 이 없으면 graceful skip 한다.

#### 선택적 배포 (cycle248)
EC2 는 모든 push 에 `up --build` 를 돌지 않는다. `compose_up_changed.sh` 가 마커
`.deployed_sha`(마지막 **성공** 배포 SHA)와 HEAD 의 누적 diff 를 보고 세 모드 중 하나를 고른다.

| 모드 | 조건 (변경 경로) | 실행 | backend |
|------|------------------|------|---------|
| `full` | `src/` · `requirements.txt` · `Dockerfile` · `.dockerignore` · `docker-compose.prod.yml`/`.tls.yml`/`.tls2.yml` · `.github/workflows/deploy.yml` · `tools/deploy/` 중 하나라도 | `up --build -d --remove-orphans` | 재생성 |
| `frontend` | `frontend/` 또는 `tools/ops/tls_stage2/` 만 | `up --build -d --remove-orphans --no-deps frontend` | 무접촉 |
| `none` | 위 두 축 어느 것도 아님(docs·tests 등) 또는 마커 == HEAD | `up -d --remove-orphans` (빌드 없음) | 재생성 0 |

- **판정 불가는 전부 `full`** 이다(fail-safe) — 마커 없음 · 마커 SHA 미지 · 직전 시도 마커(`.deployed_sha.attempt`) 잔존 · diff 실패.
- `.tls_enabled` 가 있으면 모든 compose 호출에 `-f docker-compose.tls.yml` 이, `.tls_stage2` 도 함께 있으면 `-f docker-compose.tls2.yml` 까지 base 뒤에 붙는다. 두 마커는 **모드 판정에는 개입하지 않는다**.
- `.env` 는 git 밖이라 스크립트가 못 본다 — `.env` 를 손댄 뒤에는 운영자가 직접 재생성한다.
- 모드를 미리 확인: 로컬에서 `git diff --name-only <EC2 의 .deployed_sha 값> HEAD` 를 위 표에 대보거나, EC2 에서 `DEPLOY_DRY_RUN=1 bash tools/deploy/compose_up_changed.sh` (docker 미호출 · 마커 미기록).

### TLS (HTTPS)
도메인 `auto.dkstock.cloud`. 두 단계 모두 EC2 에서 운영자가 1회 수동 실행하고, 호스트
마커 파일(git 밖)의 존재 여부가 스위치다.

| 단계 | 명령 | 마커 | 효과 |
|------|------|------|------|
| 1 | `LE_EMAIL=<메일> bash tools/ops/tls_enable.sh` | `.tls_enabled` | certbot 발급 → 443 병행 (80 유지, 리다이렉트 없음) |
| 2 | `ROUTINE_HTTPS_CONFIRMED=1 bash tools/ops/tls_stage2_enable.sh` | `.tls_stage2` | http→https 301 + HSTS |
| 후속 | `bash tools/ops/rotate_basic_auth.sh` | — | Basic 자격 회전 |

- 1단계는 **DNS A 레코드(`auto.dkstock.cloud` → EC2 공인 IP)를 먼저 등록한 뒤** 실행한다. `dig` 대조가 certbot 호출보다 앞이라 DNS 가 틀리면 Let's Encrypt rate limit 을 쓰지 않고 멈춘다. 발급 산출물을 확인한 **뒤에만** 마커를 만든다(순서가 뒤집히면 인증서 없는 443 오버레이가 붙어 80 까지 내려간다).
- 2단계는 1단계에 **종속**이다 — `.tls_enabled` 없이 301 만 켜면 리다이렉트 뒤에 듣는 서버가 없어 사이트가 도달 불가가 된다. 사람 게이트 `ROUTINE_HTTPS_CONFIRMED` 가 정확히 `1` 이 아니면 아무것도 하지 않는다.
- 두 스크립트 모두 **frontend 컨테이너만** 재기동하고(backend 무접촉), 사후 검증에 실패하면 마커를 지우고 앞 단계로 **원복까지 실행**한다.
- 자격 회전은 새 비밀번호를 화면에 찍지 않고 `secrets/.rotated-<타임스탬프>`(권한 600) 로만 남긴다. 운영자가 그 값으로 자동 리포트 루틴의 자격과 브라우저 로그인을 갱신해야 회전이 끝난다.
- 수동 원복: 2단계만 끄기 `bash tools/ops/tls_stage2_enable.sh disable` / TLS 전체 끄기 `rm -f .tls_enabled && docker compose -f docker-compose.prod.yml up -d --no-deps frontend`.

### 수동 배포
```bash
ssh -i ~/.ssh/auto-stock-key.pem ubuntu@<EC2_IP>
cd ~/auto_stock
git pull origin main
bash tools/deploy/compose_up_changed.sh   # 자동 배포와 같은 판정 · 같은 compose 파일 조합
```

> ⚠️ **수동 배포는 이 스크립트로 한다.** `docker compose ... up --build` 를 직접 실행했거나
> EC2 에서 git 을 손으로 움직였으면(reset/checkout/revert/stash) 반드시
> `rm ~/auto_stock/.deployed_sha` — 마커는 "이 git SHA 가 성공 배포됐다" 만 뜻하고 실행 중
> 이미지와 대조하지 않는다. 지우지 않으면 다음 자동 배포의 판정(diff · `already_deployed`)이
> 실제 이미지 상태와 어긋나 **stale backend 가 조용히 계속 돌 수 있다**. 마커는 compose 성공
> 뒤에만 쓰이므로 수동 compose 실행은 마커를 전진시키지도 않는다.

> ⚠️ raw compose 를 직접 써야 하면 `.tls_enabled`/`.tls_stage2` 가 있는 서버에서는
> `-f docker-compose.prod.yml -f docker-compose.tls.yml [-f docker-compose.tls2.yml]` 를 **모두**
> 붙인다. base 파일 단독 실행은 TLS 원복 명령과 같아서 443 이 내려간다.

> **주의**: 로컬과 EC2에서 동시 실행 금지 — KIS API 동일 계정 동시 접속 시 충돌 발생

> **배포 금지 창**: 보유 포지션이 있으면 KRX 메인 **09:00~15:30** push 금지 — backend 재생성
> 1~5분이 tick blind 라 손절 사각이 생긴다(cycle232 D6). **20:00~21:35** 도 금지 —
> `TIME_SESSION_START_CUTOFF`(20:00) 가 그 창의 재기동을 **거부**해서, 재기동 시점 이후의
> 저녁 작업(20:05 metrics 스냅샷 · 20:30 일봉 적재 · 21:30 정산과 일일 로그 분석 · 로그
> retention)이 그날치 통째로 결손된다(cycle283 D8). 장외 배포 창 =
> **15:30~16:00 · 21:35~익일 07:45**. 16:00~20:00 은 KRX 애프터마켓 실시간 연속체결
> 구간이라 재시작이 같은 tick blind 를 만들고, 08:00~08:50 NXT 프리장도 실매매 구간이다.
> 모드가 `full` 인지 불확실하면 full 로 간주한다.

## 스케줄 — KRX/NXT 통합 운영 (08:00~20:00)

```
 부팅               NXT 프리           KRX 메인           애프터(NXT→KRX)    저녁 블록
 ──────────────────┼──────────────────┼──────────────────┼──────────────────┼──────────────────
 07:45~07:59       │08:00~09:00       │09:00~15:40       │15:40~20:00       │20:00~21:30
 07:45 자동 시작   │08:00 익일 청산   │09:00:05 시가 확정│15:40 NXT 애프터  │20:00 애프터 종료
       _boot 즉시  │08:00 PRE_NXT 매수│09:30 모멘텀 스캔 │      (매수 LTV)  │20:00 AI자문+적용
 07:59 사전 구독   │      (LTV)       │15:20 매수 중단   │16:00 KRX 애프터  │20:05 metrics
                   │                  │      + 강제 청산 │      마켓 개시   │20:30 일봉 적재
                   │                  │15:30 KRX 마감    │19:50 매수 중단   │21:30 정산+로그
                   │                  │                  │                  │      분석+정리
```

| 시각 | 동작 |
|------|------|
| 07:45 | 자동 매매 시작 (AUTO_START 활성 시, 주말+공휴일 자동 건너뜀 — KIS chk-holiday API) |
| 07:45 직후 | `_boot()` — `start()` 안에서 즉시 돈다(자동 기동이면 07:45 직후, 수동 재기동이면 그 시각). 토큰 사전 순차 발급 (cycle20: 메인+보조 N 분당 1개 한도 직렬화) → DB 포지션 복구 → KIS 잔고 교차 검증 → 미체결 복구 → `stock_master` eager 갱신 (보유+익일청산) → 매크로 fetch + `market_regime_snapshots` INSERT → `cash_usage_ratio` 자동 조정 → 전략 prepare |
| 07:59 | 사전 구독 — 돌파(VB/LTV) + 스윙(donchian) 스캔 종목 + 보유 포지션. WebSocket 연결 + 체결통보 + (실전) `H0UNMKO0` 구독. 유니버스 비어있으면 prepare 재실행 |
| 08:00 | NXT 프리 진입 — 익일 청산 백그라운드 (`NEXT_DAY_STABILIZE_SECS=30s` 안정화 후 NXT 시가 청산) + `_confirm_breakout_open_prices(board="pre_nxt")` 로 NXT 프리 시가 확정(후보가 있으면 phase `pre_nxt_trading`). 프리장에서 신규 매수하는 전략은 **LTV 하나**다(`tradable_boards=("pre_nxt","main","post_nxt")`) |
| 09:00:05 | KRX 메인 시가 확정 — `_confirm_breakout_open_prices(board="main")` VB/LTV target_price 계산 (KRX 09:00 시가 + 전일Range × `k_value_krx_main`). 직후 `_drain_pending_next_day_clear()` — 08:00 보류 종목 KRX 시장가 일괄 청산 |
| 09:05~09:30 | donchian 스윙 진입창 — 시장가 1주문/종목, 갭 +3%↑ 스킵 |
| 09:30 | 모멘텀(상한가) 종목 스캔 시작, 매수 감시. 5분 주기 `_scan_loop` 시작 — 모멘텀+돌파+스윙+보유 합집합 시세 재구독 |
| 15:20 | KRX 메인 신규 매수 중단 + 강제 청산 (`_force_clear_main_only`) — VB 전체 + LTV 상한가 미도달 청산. 시간 가드: `>=15:30` 진입 시 skip + 익일 청산 안전망 위임 |
| 15:30 | KRX 메인 마감 (15:30~15:39:59 종가 흡수 마진 — MAIN 보드 유지). 직후 `_confirm_breakout_open_prices(board="post_nxt")` 로 POST_NXT 시가 확정 폴링 (`board` 명시 = SessionTracker 30초 전환 race 회피). LTV 의 `tradable_boards` 에 post_nxt 가 있어 확정 대상이 실제로 존재한다 — 누락되면 화면에 "시가 대기" 종목이 잠복한다 (2026-05-12 운영 사고) |
| 15:40 | **POST_NXT 진입**. VB 는 매도만이고, **LTV 는 POST_NXT 신규 매수를 한다**(연속 상한가 종목 익일 청산 모드 진입) |
| 16:00 | **KRX 애프터마켓 개시** (16:00~20:00 실시간 연속체결). 보드는 `post_nxt` 그대로지만 **주문 거래소가 이 시각부터 KRX 로 바뀐다** — 「매매 안전장치」의 「시각이 거래소를 정한다」·「KRX 애프터마켓 청산 호가유형」 참조. 15:40~16:00 은 KRX 에 연속 체결이 없어 NXT 애프터만 열려 있다 |
| 16:10 | (장 마감 후 데이터 계층) `stock_master` basics 보강 — KIS CTPF1002R 매스 (`TIME_STOCK_MASTER_BASICS_REFRESH`) |
| 16:15 | `stock_master_daily` retention purge (`TIME_STOCK_MASTER_DAILY_PURGE`) — 적재(20:30)보다 **앞**이라 그날 적재분은 다음 날 purge 대상이다. 전일까지의 경계만 다루므로 행위 무영향 |
| 16:20 | 저녁 잠정 funnel 캡처 (`TIME_EVENING_FUNNEL_CAPTURE`, 운영자 밤 후보 확인용) |
| 16:30 | KIS 종목 마스터 파일 적재 — `kospi_code.mst` / `kosdaq_code.mst` (`TIME_STOCK_MASTER_MASTER_LOAD`) |
| 16:40 | 퀀트 재무 5 TR 주1회 적재 — `_stock_master_financial_load_task_loop` (마스터 16:30 후 stagger, 주1회 신선도 게이트). 매매 무관 (cycleC1~C3, 마법공식·F-Score-7 원천) |
| 19:50 | NXT 애프터 신규 매수 중단 (`TIME_NXT_POST_BUY_STOP` — 전 전략 `buy_disabled=True`. 이 시각에 하는 일은 매수 중단뿐이다) |
| 20:00 | NXT 애프터 종료 + WebSocket 구독 해제(`unsubscribe_all`) → 전략수정 AI 자문 생성 (OpenAI → `parameter_recommendations`, `TIME_RECOMMENDATION`) → 직후 `auto_apply_recommendations()` (cycle23, 감액만 + 50% cap, `auto_apply_enabled=true` 시) |
| 20:00:05 | 전체 유니버스 적재 (`TIME_FULL_UNIVERSE_LOAD` — 전략수정 AI자문 직후 5초 마진) |
| 20:05 | metrics 1차 스냅샷 (`TIME_METRICS_SNAPSHOT` → `daily_metrics_snapshot.run_daily_metrics_snapshot`, OpenAI 미호출). `api_metrics`·`strategy_funnel` 은 프로세스 메모리 전용이라, 21:30 정산 전에 재시작이 나면 통째로 사라진다. 이 스냅샷이 그 유실 노출을 5분으로 줄인다 |
| 20:30 | `stock_master_daily` 일봉 적재 (`TIME_STOCK_MASTER_DAILY_LOAD` — KRX 애프터마켓(16:00~20:00) 동안 일봉 거래량이 계속 늘어 그 뒤에 적재한다) |
| 21:30 | 전략별 + 합산 일일 정산 (`TIME_SETTLEMENT` — 일봉 적재 20:30 뒤), DB 실적 기록. 직후 일일 로그 분석 리포트 생성 (OpenAI → `daily_log_reports`). 직후 `purge_old_logs()` (INFO 2일 / WARNING+ 30일 retention 자동 정리, cycle6) |

**중간 시각 시작 시**: 현재 시각 이후 스케줄부터 실행. **20:00**(`TIME_SESSION_START_CUTOFF`) 이후 시작은 거부한다 — 정산 시각(21:30)과 분리된 별도 경계다. 그 창의 재기동은 그날 20:30 일봉 적재 · `_settle()` · 일일 로그 분석 · retention 정리를 통째로 잃는다.

### 전략수정 AI자문 사이클

```
  20:00 (당일)                                            다음 영업일
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
  21:30 정산 직후                                                     사용자
 ──────────────────────────────────────────────────────────────────────►
  ┌────────────────────────┐    ┌──────────────────┐    ┌─────────────────┐
  │ generate_daily_log_   │    │ /logs (분석 탭)  │    │ 우상단 "지금     │
  │ report()              │    │ 좌측: 영업일     │    │  분석 실행"     │
  │  당일 KST 00:00~now   │ ─► │ 우측: 총평 +     │ ◀─ │  버튼 (수동      │
  │  system_logs 집계 →   │    │ findings + 메트릭│    │  트리거,         │
  │  trade_history 집계 → │    │ (severity 색상   │    │  영업일당 1건)   │
  │  OpenAI JSON →        │    │  + category 칩)  │    │                  │
  │  daily_log_reports    │    │                  │    └─────────────────┘
  │  upsert (UNIQUE)      │    └──────────────────┘
  └────────────────────────┘
```

