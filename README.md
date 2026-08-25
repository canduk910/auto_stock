# KIS 주식 자동매매시스템

한국투자증권(KIS) OpenAPI 기반 주식 자동매매시스템. FastAPI 백엔드 + React 프론트엔드 + AWS RDS PostgreSQL(asyncpg) 웹 서비스 아키텍처.

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
                          │  AWS RDS (PostgreSQL)  │  20:00  │   OpenAI     │
                          │  asyncpg (src/db/pg.py)│ ◀─────→ │  GPT          │
                          │  positions / strategy  │  20:10  │  (자문 +     │
                          │  parameter_recommend.  │ ◀─────→ │   로그 분석) │
                          │  daily_log_reports     │         └──────────────┘
                          │  daily_performance     │
                          └────────────────────────┘
```

## 기술 스택

| 구분 | 기술 |
|------|------|
| Backend | Python 3.11+, FastAPI, httpx, websockets, pydantic, asyncpg |
| Frontend | React 19, TypeScript, Vite, TanStack Query/Table, Recharts, Tailwind CSS |
| Database | AWS RDS PostgreSQL (asyncpg 직접 드라이버) |
| 외부 API | 한국투자증권 OpenAPI (REST + WebSocket) |

## 사전 준비

1. **Python 3.11+** 설치
2. **Node.js 20+** 설치
3. **한국투자증권 OpenAPI 신청** — [KIS Developers](https://apiportal.koreainvestment.com/)에서 앱키/시크릿 발급
4. **PostgreSQL 준비** — AWS RDS PostgreSQL 인스턴스(또는 로컬 postgres) 확보 후 asyncpg DSN(`DATABASE_URL`) 구성

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

# DB (AWS RDS PostgreSQL — asyncpg DSN, 현재 정본)
DATABASE_URL=postgresql://user:pass@host:5432/dbname?sslmode=require

# Supabase — 런타임 미사용 (src/db/supabase.py 롤백용 병존, 어느 db 모듈도 참조 안 함)
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-anon-key
```

### 2. 데이터베이스 초기화

`supabase/migrations/` 하위 마이그레이션 파일을 대상 PostgreSQL(RDS)에 **번호 순으로 모두 실행** (psql 등. 디렉토리명은 supabase/ 로 유지 — 스키마 SQL 정본):

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
014_system_logs_index.sql             # system_logs 조회 인덱스
015_stock_master.sql                  # KIS CTPF1002R 캐시 (NXT 거래가능 사전 판별, 24h TTL)
016_recommendation_weights_review.sql # 자산배정 + 로직 자문 컬럼 (J4)
018_register_bull_flag_and_vcp.sql    # 신규 전략 2종 등록 (bull_flag_breakout / vcp_breakout)
019_backtest_runs.sql                 # 외부 MCP 백테스트 실행 영속화 (Phase 2)
020_parameter_recommendations_backtest.sql  # parameter_recommendations.backtest_summary JSONB (Phase 3)
021_weight_reasoning.sql              # parameter_recommendations.weight_reasoning 별도 사유 (사이클 1)
022_market_regime_snapshots.sql       # dkstock.cloud 매크로 일일 스냅샷 (사이클 2)
023_cash_usage_ratio_range.sql        # cash_usage_ratio 범위 [0.5, 1.0] → [0.0, 1.0] 확장 (사이클 2)
024_vb_board_stop_loss_defaults.sql   # VB 보드별 손절 디폴트 자동 복사 (사이클 3)
025_external_integration_toggles.sql  # dkstock-regime / kis-mcp 외부 통합 DB-only 토글 (사이클 5)
026_kis_quote_accounts.sql            # 보조 KIS 시세 수신 계좌 (사이클 7-A, 풀 슬롯 41 × (1 + N) 확장)
027_buy_block_mode.sql                # 매수 가드 4 모드 (OFF/WARN/SOFT/HARD) + 4 임계값 (사이클 8)
028_auto_apply_status.sql             # parameter_recommendations.status 에 'applied_auto' 분리 (사이클 23 P3, AI 자문 자동 적용)
029_trade_history_dedupe_unique.sql   # (ticker, order_no, trade_type) 부분 UNIQUE 인덱스 (사이클 30, 042700 핑퐁 INSERT 영구 차단)
030_strategy_funnel_snapshots.sql     # 조건검색 단계별 후보/탈락 종목 영구 추적 (사이클 34)
031_daily_log_reports_openai_meta.sql # daily_log_reports 토큰/지연/비용 5 컬럼 (input/output/total_tokens, latency_ms, cost_estimate_usd)
032_stock_master_history.sql          # stock_master 갱신 이력 (사이클 84)
033_stock_master_daily.sql            # KIS FHKST03010100 일봉 정규화 (PK ticker+bas_dd + OHLCV + raw JSONB, 사이클 122)
034_stock_master_master_raw.sql       # stock_master.master_raw JSONB + master_raw_updated_at (사이클 129, KIS 공식 일일 마스터 파일)
035_strategy_funnel_snapshots_upsert.sql  # strategy_funnel UPSERT 전환 (사이클 145, snapshot_at 키 폐기)
036_stock_master_history_seq.sql      # stock_master_history seq 컬럼 (사이클 150)
037_stock_master_kospi200_kosdaq150.sql   # is_kospi200/is_kosdaq150 BOOLEAN + 부분 인덱스 (사이클 153)
038_pending_next_day_clear.sql        # 익일청산큐 DB 영속화 PK(target_date, ticker, strategy_id) (사이클 162, 재기동 보호)
041_stock_master_financial.sql        # KIS 재무 5 TR 정규화 PK(ticker, stac_yymm, div_cls) + 18 NUMERIC + raw JSONB (사이클 C1, 마법공식·F-Score-7 원천)
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
| 메인 대시보드 | 계좌 요약, 보유 종목, 매매 실적 차트, 상태 인디케이터, 조건검색 현황(전략별 스캔/타겟/스윙 깔때기), **`KisAccountPoolCard` 세션별 expand** (사이클 35/37 — main/quote-N 종목 테이블 + WS tick / KIS 체결시각 / WS 의심 amber 배지) |
| 조건검색 추적 (`/strategy-funnel`) | **사이클 34** — 전략 dropdown + 날짜 picker + 단계별 expand 가능한 테이블 (통과/탈락 종목 + 탈락 사유 sample) + 수동 trigger 버튼 |
| 거래 내역 | **두 탭** — 주문체결내역(매수/매도 raw 행, 필터·페이징) / 매매손익(매수·매도 페어 1행, 가중평균. 보유 중은 open 페어로 미실현 손익 표시) |
| 전략수정 AI자문 | 20:00 OpenAI 자동 생성 자문 — 신규 자문 탭(승인/거절) + 이력 탭(상태/전략 필터). 자산 배정/로직 자문/비중 변경 사유(`weight_reasoning`) 별도 카드 + 백테스트 비교 카드(`BacktestComparisonCard`) |
| 일일 로그 분석 | 20:10 정산 직후 OpenAI가 system_logs+trade_history 분석한 운영 개선 리포트 (영업일 리스트 + findings + 메트릭) |
| **종목마스터 (`/stock-master`)** | **사이클 84+** — KIS 마스터 (시총/거래대금/NXT가능/거래정지/관리종목/KOSPI200·KOSDAQ150 플래그) + 일봉/시총 분포 카드 + 시장/시총/거래대금/종목명 필터 + 4 작업 수동 trigger 버튼 (유니버스/기본정보/일봉/공식 마스터). 상단 `RefreshProgressBanner` 5초 폴링 진행률 (사이클 127) |
| **실시간 건강도 (`/realtime-health`)** | **사이클 103+** — WebSocket 구독 슬롯 (total/acked/fresh_60s/stale_60s/limit) + 세션별 종목 expand + KIS `inquire_ccnl` 캐시 (last_cntg_hour/today_volume, TTL 5분) + 수동 재구독 버튼. **사이클 186** — 5번째 카드 "장운영상태" (VI 활성/거래정지/종목상태 이상 + 서킷브레이커 휴리스틱 배지 + 종목별 상세, 관찰성 전용·표시만) |
| 설정 | 전략 파라미터 조정, 자금 비중, 자동 시작 토글, 가격/거래대금 필터, 매수 가드 4모드, 외부 통합 토글 |

### 실전 전환

```env
KIS_ENV=real
KIS_APP_KEY=실전용_앱키
KIS_APP_SECRET=실전용_시크릿
```

> **주의**: 반드시 모의투자에서 충분히 검증한 후 실전 전환하세요.

## 매매 전략

```
                ┌──────────────────────────────────────────────────────────────────────────────────────────┐
                │                          StrategyRegistry (자금 분배)                                     │
                │                       순자산 × weight = 전략별 할당 자금                                  │
                └────┬───────────────┬───────────────┬────────────────┬───────────────┬───────────────┬────┘
                     │               │               │                │               │               │
                     ▼               ▼               ▼                ▼               ▼               ▼
              ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
              │ momentum     │ │ volatility_  │ │ long_tail_   │ │ donchian_    │ │ bull_flag_   │ │ vcp_breakout │
              │ (상한가)     │ │ breakout     │ │ volatility   │ │ swing        │ │ breakout     │ │ (미네르비니) │
              ├──────────────┤ ├──────────────┤ ├──────────────┤ ├──────────────┤ ├──────────────┤ ├──────────────┤
              │ 진입 09:30~  │ │ 진입 09:00:05│ │ 진입 09:00:05│ │ 진입 09:05~  │ │ 진입 09:05~  │ │ 진입 09:05~  │
              │ 시그널: +29% │ │ 시그널: 시가 │ │ 시그널: 시가 │ │   09:30 시장가│ │   13:00      │ │   14:30      │
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
| 종목 선정 | 등락률 순위 15%+ → 시총 1,000억+, 거래대금 200억+ |
| 매매 가능 보드 | KRX_OPEN(08:30~) + MAIN(09:00~15:20) — 상한가 +29%는 KRX 기준이라 NXT 보드 제외 |
| 매수 | 전일종가 대비 +29% 돌파 순간, 할당 자금 25% 비중 |
| 손절 | 매수가 대비 -7.5% |
| 익일 청산 | 다음 영업일 NXT 프리(08:00) 시가 + 30초 안정화 후 갭상승 +10% → 트레일링 스탑 -2% / 그 외 즉시 매도 |

### 전략 B: 변동성 돌파 (`volatility_breakout`)
| 구분 | 규칙 |
|------|------|
| 종목군 | 코스피+코스닥 전체, 시총/거래대금 필터, 노이즈 비율 기반 동적 K값 |
| 매매 가능 보드 | **MAIN only (09:00:05~15:20)** — 사이클 26 (2026-05-20) KRX ONLY 정책. KRX 09:00 시가 + (전일 Range × `k_value_krx_main`, 기본 1.0). PRE_NXT/POST_NXT 매수 비활성 (보유 종목 손절/트레일링 매도는 보드 가드 무관 작동). `k_value_nxt_pre`/`k_value_nxt_post` 키는 DB/AI 자문 호환 보존만 |
| 매수 | KRX 09:00 시가 + (전일 Range × K값) 돌파 순간, 할당 자금 10% 비중 |
| 손절 | 매수가 대비 -3% |
| 청산 | **15:20 KRX 메인 일괄 청산** (OVERNIGHT 거부). 익일 청산 안전망: 15:20 청산이 누락된 비상 상황(시세 미수신/시장가 거부/재시작 race)에서만 다음 영업일 `_execute_next_day_clear`로 NXT 프리 청산 — WARNING 로그 노출 |
| 재매수 | 당일 매도 종목 재매수 차단 |

### 전략 C: 롱테일 변동성 돌파 (`long_tail_volatility`)
| 구분 | 규칙 |
|------|------|
| 종목군 | 변동성 돌파와 동일 + 연속상한가 종목 제외 |
| 매매 가능 보드 | **MAIN only (09:00:05~15:20)** — 사이클 26 KRX ONLY. PRE_NXT/POST_NXT 매수 비활성. 상한가 모드 종목의 POST_NXT 시간대 손절 모니터링은 `risk.on_tick` 청산 평가가 보드 가드 무관 작동 |
| 매수 | 변동성 돌파 + 전일대비 ≥ `min_prdy_rate` (기본 5%) |
| 당일 청산 | 손절 -3%, **15:20 일괄 청산** (상한가 미도달 종목, `check_force_clear()`가 `_limit_up_reached` 제외) |
| 모드 전환 | 당일 +29% 도달 → 익일 청산 모드(`_limit_up_reached` set 등록) |
| 익일 청산 | 손절 -5%, 다음 영업일 NXT 프리 시가(08:00) 갭상승 +10% → 트레일링 -2% / 그 외 즉시 매도 (30초 안정화). POST_NXT 시간대 시세 모니터링 손절 평가는 그대로 작동 |

### 전략 D: 20일 신고가 스윙 (`donchian_swing`)
| 구분 | 규칙 |
|------|------|
| 종목군 | **코스피200 + 코스닥150 고정 유니버스** + 시총 컷 (거래량순위 API 미사용 — 추세추종 부적합 + 시점 의존 제거) |
| 매매 가능 보드 | MAIN(09:00~15:20)만 — 추세추종은 일중 변동성 필요. NXT 프리/애프터 비활성 |
| 진입 조건 | 어제 종가가 20일 신고가 돌파 + 60일 EMA 우상향 + 종가>EMA + 거래대금 ≥ 20일평균×1.5 |
| 매수 | 다음 영업일 09:05~09:30 시장가, 1종목당 1회. **시가 갭상승 +3%↑ 시 스킵** (추격 방지) |
| 손절 | 매수가 대비 -7% 하드 손절 |
| 청산 | ATR(14)×2 Chandelier 트레일링 (`high_since_buy − ATR×2`) — 시간 청산 없음 |
| 보유 | 멀티데이 (평균 5~15 영업일). DB `positions` 영속화로 일자 넘어 유지 |
| 종목명 | KIS `hts_kor_isnm` 우선 + `scanner.STATIC_TICKER_NAMES`(KOSPI200/KOSDAQ150 인라인 코멘트 자동 파싱)로 fallback |

### 전략 E: 눌림목 돌파 (`bull_flag_breakout`, 2026-05-15 추가)
| 구분 | 규칙 |
|------|------|
| 종목군 | `stock_master.list_by_filter` (**전체 상장 확대 유니버스** — 시총 ≥ 100억 + 거래대금 ≥ 15억, ETF/ETN 제외) — 사이클 108 KIS 순위 API 폐기 / 2026-08-08 확대(지수 무제약 유지, 거래대금 20억→15억, `max_scan_stocks` 100→4000) |
| 매매 가능 보드 | MAIN(09:05~13:00) |
| 진입 조건 | **폴 자동 검출**(직전 3~10영업일 누적 +15%↑, 음봉 비율 ≤ 45%) + **플래그 자동 검출**(2~10영업일 횡보, 조정 폭 ≤ 폴 폭의 50%, 거래량 < 폴 평균의 60%) → 플래그 상단(`flag_high`) 돌파 + 당일 거래량 ≥ `flag_avg_volume × 2` |
| 매수 | 종목당 1회 + 3영업일 쿨다운. 부분봉 가드(`candles[0]==오늘`이면 [1]부터) |
| 손절 | 매수가 대비 -5% / 플래그 하단(`flag_low`) 이탈 → STOP_LOSS |
| 청산 | 측정된 이동(`flag_high + (pole_high - pole_start)`) 도달 → 1차 절반 청산(`_partial_exit` 마킹, 1차 구현은 전량) → 잔여 `high_since_buy − ATR×2` 트레일링 / 5영업일 시간 청산 (캘린더일 +2 보정) |
| 보유 | 단기 (평균 1~5 영업일) |

### 전략 F: 변동성 수축 돌파 (`vcp_breakout`, 미네르비니식, 2026-05-15 추가)
| 구분 | 규칙 |
|------|------|
| 종목군 | **전체 상장 확대 유니버스**(2026-08-08 확대 — 지수 제약 제거 `is_kospi200/is_kosdaq150=None`) → 시총 ≥ 100억 + 거래대금 ≥ 10억 컷, 100일 일봉(prepare cap) |
| 매매 가능 보드 | MAIN(09:05~14:30) |
| 진입 조건 | **추세 필터**(종가 > 50EMA > 60EMA > 120EMA + 장기 EMA 1개월(20영업일) 우상향, 사이클 48 KIS 100일 한도) → **베이스 자동 검출**(25~75영업일, 깊이 ≤ 30%) → **pullback 점진 수축**(ATR threshold ZigZag 검출 `min_swing_atr_mult=0.5`, 2~4회, 직전 대비 폭 감소, 마지막 ≤ 12%) → **거래량 수축**(마지막 5일 평균 < 베이스 직전 20일 평균 × 70%) → 베이스 상단(`base_high`) 돌파 + 당일 거래량 ≥ 20일 평균 × 1.5 |
| 매수 | 종목당 1회 + 7영업일 쿨다운 |
| 손절 | 매수가 대비 -7% / 베이스 하단(`base_low`) 이탈 → STOP_LOSS |
| 청산 | `high_since_buy − ATR×2` 트레일링 / 50일 EMA 이탈 → TRAILING_STOP. **시간·15:20 청산 없음** — 멀티데이 보유 (`Position._MULTIDAY_STRATEGIES` 멤버) |
| 보유 | 멀티데이 (VCP 통상 2~6주) |

### 전략 G: 고지로 대순환 스윙 (`kojiro`, 이동평균선 대순환, 2026-07 Phase 1 다크런치)
| 구분 | 규칙 |
|------|------|
| 종목군 | **전체 상장**(`is_kospi200/is_kosdaq150=None`, `max_scan_stocks≥3577`) → 시총/거래대금 컷 → 일봉 100일(`min_required=80`) → **ATR/종가 변동성 밴드 1.0~6.0%**(비협상 판별 필터, 2026-07-20 상한 4.5→6.0 백테스트 PF 0.86→1.60) |
| 매매 가능 보드 | MAIN(09:05~09:30) |
| 진입 조건 | **strict entry(4조건 AND)**: ① 현재 스테이지1(EMA 단기>중기>장기) ② 최근 5영업일 내 6→1 전환 인접(신선도 `stage1_freshness=5`) ③ EMA 5/20/40 모두 우상향 ④ 전일 종가 > EMA5. 갭업 ≥5% / 갭다운 ≤-4% / 장중 붕괴(현재가<시가) 스킵 |
| 매수 | 종목당 1회 (조기진입·터틀 유닛 sizing·피라미딩 = Phase 2 연기, Phase1 = position_ratio) |
| 손절 | 고정 % -8%(ATR 독립 backstop) / 2ATR 하드손절(tighten-only) → STOP_LOSS |
| 청산 | 스테이지3 진입(추세 종료, 익일 아침 발화) / `high_since_buy − 2.5×ATR` 트레일링 → TRAILING_STOP. **시간·15:20 청산 없음** — 멀티데이 |
| 보유 | 멀티데이 (`_MULTIDAY_STRATEGIES` 멤버). 지표 순수모듈 `kojiro_indicators.py`(Wilder ATR ewm(1/20)) |

> 프론트엔드 Settings 페이지에서 전략별 자금 비중 조절 가능. 대시보드 "조건검색 현황 → 20일 신고가 스윙" 탭에서 8단계 깔때기 통계 + 후보 종목 진입상태(보유 중 / 진입 대기 / 갭 스킵 / 장 시작 전 / 진입 시간 종료) 시각화. 신규 3 전략(`bull_flag_breakout`/`vcp_breakout`/`kojiro`)은 초기 `enabled=false, weight=0` 등록 — Settings 에서 수동 활성화 권장 (백테스트/모의 검증 후)

### 매매 안전장치
| 항목 | 동작 |
|------|------|
| 종목코드 형식 비대칭 | 진입 단계는 6자리 숫자만(`isdigit`) — ETF·신주인수권·임시 코드 매수 차단. 사후처리(체결통보·잔고 sync)는 6자리 영숫자(`isalnum`) 허용 — 외부 경로로 들어와도 좀비 포지션 방지 |
| 매수가능 캐시 | 60초 TTL — KIS `get_buyable()` 호출을 매 틱 → 분당 1회로 축소 |
| 잔고부족 매수 락 | 900초 — `is_insufficient_cash` 응답 또는 `max_buy_quantity≤0` 시 다음 잔고 sync까지 매수 차단 |
| 매도 잔고부족 즉시 break | `is_insufficient_quantity` 응답 시 3회 재시도 생략 + 메모리·DB positions 정리 |
| 체결통보 race 가드 | 시장가 즉시체결 시 체결통보가 REST 응답보다 먼저 와도 `_completed_orders` set + 보정 INSERT로 PENDING 잔존 차단 |
| 진입 차단 | VB/LTV `_scan_universe`의 `list_by_filter` 후보 + `scanner.scan_stocks` 모두 `ticker.isdigit()` 검증 |
| 보드 가드 | `RiskManager.on_tick`에서 매수 신호 평가 전 `session_tracker.is_tradable(strategy_id, params)`로 현재 활성 보드가 전략 `tradable_boards`에 포함됐는지 확인 — 비활성 보드에서는 신호 평가 자체 skip |
| 매수 수량 1주 fallback (전략 잔여 자금 기준) | `position_ratio × total_investment // current_price = 0`이어도 **전략 잔여 자금**(= `total_investment` − 해당 전략 보유 `buy_price×qty` 합 − 해당 전략 `pending_buy_amounts` 합)이 1주 살 수 있으면 1주 매수. 4개 전략 모두 `StrategyBase._fallback_one_share()` 공통 헬퍼 호출. 기존 고정 `total_investment` 직접 비교 → 자금 90% 점유 후 추가 1주 매수로 **전략 한도 초과**하던 결함 차단(2026-05-11 P1) |
| NXT 거래가능 사전 판별 (Phase G) | KIS `CTPF1002R` 응답 `cptt_trad_tr_psbl_yn=="Y" AND nxt_tr_stop_yn=="N"`로 `nxt_tradable` 파생. `stock_master` 테이블(24h TTL)에 캐시. `OrderEngine._strategy_exchange_async`가 `nxt_tradable=False`면 NXT/SOR → KRX 강제 다운그레이드 + `[nxt_downgrade]` 로그. `scheduler._execute_next_day_clear`는 1순위 판별로 사용 → 시가 폴링/안정화 거치지 않고 즉시 보류(NXT 주문 시도 0). `execute_sell`이 NXT 시간대 매도 거부 받으면 `stock_master.upsert_one(nxt_tradable=False)` 사후 보강 |
| 매도 거부 단일 정책 (사이클 55 / R-1, 사이클 52/54 통합) | `src/engine/sell_rejection.py::SellRejectionTracker` 가 `execute_sell` 4 분류 거부를 단일 정책 객체로 흡수. **진입 게이트**: `is_blocked(ticker, now_kst)` TTL 미경과 시 KIS 호출 없이 조용히 skip (INFO `[market_closed_blocked]` 1줄/ticker/일 cap). **2단계 TTL** (Q1): `is_market_closed_rejection` (APBK0918/KIOK0320) → KRX 메인(09:00~15:30) 거부 = **5분 TTL** (손절 의무 보호), NXT 시간대(08:00~09:00/15:30~20:00) 거부 = **다음 KST 09:00 TTL**. **30초 TTL + NXT 익일 청산 전환** (Q2): `is_market_order_disallowed` (APBK1943/APBK3013) 폴백(`step_down` 5호가 지정가 1회) 결과 무관 30초 TTL, NXT 폴백 *실패* 시 `_pending_next_day_clear.add((ticker, strategy_id))` 자동 등록 → 다음 09:00 KRX 시장가 일괄 청산. **reconciliation** (Q3): `is_insufficient_quantity` 즉시 positions 제거 + `[positions_reconciliation]` INFO + 1회 `get_balance()` → 실제 잔량 > 0 시 INFO 권고 (자동 재등록 미구현, 운영자 수동 확인). **history deque** (Q5, N=20/ticker, V-1 사전 인프라). 호환 layer: `OrderEngine._market_closed_blocked` / `_market_closed_blocked_logged_today` property 위임 (기존 코드/테스트 무변경). `OrderEngine.reset_daily_state()` → `tracker.reset_daily()` 일괄 clear. 2026-05-31 운영 진단 (10분간 500+건 매도 거부 폭주) 이 시정 출발점 |

## NXT/KRX 통합 운영 (08:00~20:00)

KIS OpenAPI가 NXT(넥스트레이드 ATS) 주문/시세를 정식 지원함에 따라 KRX 메인장 외 NXT 프리/애프터 시간대까지 매매 가능. **사이클 26 (2026-05-20) — 매매 정책 KRX ONLY + 시세 채널 시간대별 전환**: 신규 매수는 KRX 메인 09:00~15:20 단독, PRE_NXT/POST_NXT 는 보유 종목 매도(손절/트레일링)만. 보드 단순화 5→3 + 시세 채널 시간대별 분리 + 종목별 원자 전환.

| 항목 | 사용 |
|------|------|
| 시세 채널 (시간대별, 사이클 26) | `H0STCNT0` (KRX 단독) + `H0NXCNT0` (NXT 단독) — `scanner.get_active_tick_tr_ids(now_t)` 가 6 구간 분기: PRE_NXT 08:00~08:59:09 {H0NXCNT0} / **KRX 사전 마진 08:59:10~08:59:59 {H0NXCNT0, H0STCNT0}** / MAIN 09:00~15:30 {H0STCNT0} / 종가 흡수 15:30~15:39:09 {H0STCNT0} / **NXT 사전 마진 15:39:10~15:39:59 {H0STCNT0, H0NXCNT0}** / POST_NXT 15:40~19:59 {H0NXCNT0}. `H0UNCNT0` (통합) TR_ID 는 하위 호환 보존만 |
| 통합 장운영정보 | `H0UNMKO0` / 대표 종목 `005930` 구독 (실전 한정). `MKOP_CLS_CODE`(110/112/121/129/130~159) 시장 전체 공통이라 1종목으로 보드 전환 수신. SessionTracker 가 시각 기반 tick + H0UNMKO0 코드 동시 사용 |
| 주문 라우팅 | `place_order(..., exchange=...)` body 에 `EXCG_ID_DVSN_CD` (`KRX`/`NXT`/`SOR`). 모의(VTS) 는 KRX 만 허용 — SOR/NXT 는 실전 한정. 사이클 26 신규 매수는 전략 `tradable_boards=("main",)` 로 KRX 만 유효 |
| 조회 거래소 옵션 | `get_balance(afhr_flpr=...)` — `N`(정규장)/`Y`(시간외)/`X`(NXT 정규장). `get_daily_orders(exchange="ALL")` — KRX+NXT+SOR 합산 |
| 보드 추상화 (사이클 26, 3 보드) | `src/engine/session.py::MarketBoard` enum 활성 3 보드: `pre_nxt` (08:00~09:00) / `main` (09:00~15:40) / `post_nxt` (15:40~20:00). `_BOARD_SCHEDULE` 도 3 구간. `krx_open`/`krx_after` enum 값은 *호환성 보존* (실제 스케줄 미사용). `SessionTracker` 30s 주기 tick + `register_board_handler` 콜백 |
| 전략별 매매 가능 보드 | `DEFAULT_TRADABLE_BOARDS` — `momentum`: KRX_OPEN+MAIN (코드 enum 유지, 활성 보드는 MAIN) / **`volatility_breakout`·`long_tail_volatility`: MAIN only (사이클 26 KRX ONLY)** / `donchian_swing`·`bull_flag_breakout`·`vcp_breakout`·`kojiro`: MAIN only |
| VB/LTV K값 | `k_value_krx_main` (기본 1.0) — KRX 09:00 시가 기준 단독 사용. `k_value_nxt_pre`/`k_value_nxt_post` 키는 DB/AI 자문 응답 호환 보존만 (사이클 26 PRE_NXT 매수 제거) |
| 종목 단위 원자 전환 (사이클 26) | `TradingScheduler._atomic_board_transition(ticker, stale_tr_id, new_tr_id, ack_timeout_secs=2.0)` — (1) unsubscribe (2) `_subscriptions_acked` 에서 (stale_tr_id, ticker) 제거 polling (timeout 2s) (3) new_tr_id 가 None 아니면 subscribe (4) 50ms sleep. `_board_transition_loop(stale, new, tickers, priority_groups)` — HIGH (positions / next_day_clear) 우선, 전체 순회, `[board_transition_complete]` INFO |
| 사전 구독 마진 (사이클 26) | `TIME_KRX_MAIN_OPEN_PRESUBSCRIBE=08:59:10` (KRX 채널 50초 사전 마진) / `TIME_POST_NXT_OPEN_PRESUBSCRIBE=15:39:10` (NXT 채널 50초 사전 마진). 보유 + 익일청산 + 매수 후보 합집합 사전 구독 → 09:00 KRX 첫 체결 tick 즉시 수신 보장 |
| 익일 청산 시점 | 다음 영업일 NXT 프리 첫 거래(08:00 부근) + 30초 안정화 후 청산 (`NEXT_DAY_STABILIZE_SECS=30`). 대상: `momentum`, `long_tail_volatility` 상한가 모드, `volatility_breakout` 안전망 |
| 15:20 강제 청산 | `_force_clear_main_only` — `tradable_boards` 에 POST_NXT 가 있는 전략은 보유 유지 (현재 해당 없음). **시간 가드 (2026-05-15 hotfix)**: 함수 진입 시 `>=15:30` 이면 즉시 skip + 익일 청산 안전망 위임 |
| 스윙 일중 시세 REST 폴링 | `_swing_rest_poll_loop` — **2단 창**(사이클 222-a): **09:05~09:30 = 보유 종목 전용 + stale 중립**(REST 가 `ticker_last_tick` 을 갱신하면 개장 러시 blind 종목이 '신선'으로 보여 강제 재구독이 안 걸린다) / **09:30~15:20 = 전체 폴**(후보 포함 + `last_tick` 갱신). 대상 전략 = `_SWING_POLL_STRATEGIES = ("donchian_swing", "kojiro")` — **BFB·VCP 는 비멤버라 REST 보강이 없고 틱으로만 매수 평가한다**(미구독 = 매수 기회 완전 상실). 60s 주기로 `_scanned_tickers ∪ positions ∪ pending_buys` 합집합을 `fetch_stock_detail` 폴링 → `scanner.ticker_prices` 갱신 + `ticker_last_tick` touch + `ticker_names` 보강. 보유 종목만 `RiskManager.on_tick` 호출로 기존 트레일링/-7% 손절 평가 재사용. WS stale 시 ATR 트레일링 평가 끊김 차단 (2026-05-15 결함 B) |

## API 엔드포인트

| Method | URL | 설명 |
|--------|-----|------|
| GET | `/health` | 헬스 체크 |
| POST | `/api/trading/start` | 자동매매 시작 |
| POST | `/api/trading/stop` | 자동매매 정지 |
| POST | `/api/trading/restart` | 자동매매 재기동 |
| POST | `/api/trading/manual-sell` | 수동 매도 (시장가) |
| GET | `/api/trading/status` | 현재 상태 조회 |
| GET | `/api/balance` | 잔고 조회 (예수금 + 보유종목, 종목별 NXT/KRX 거래시장 정보 join) |
| GET | `/api/balance/buyable` | 매수 가능 금액 조회 |
| GET | `/api/history?page=&size=` | 거래 내역 (페이징) |
| GET | `/api/history/pnl?page=&size=&strategy=&ticker=` | 매매손익 — 매수/매도 페어 1행 (포지션 0 사이클 단위 가중평균). 보유 중은 open 페어 (미실현 손익은 `ticker_prices` 현재가) |
| GET | `/api/performance/summary` | 실적 요약 (TWR 누적 + 일평균 실현 수익률) |
| GET | `/api/performance/daily` | 일별 실적 (실현손익 기반 + TWR 누적 + 외부 입출금) |
| POST | `/api/performance/recompute` | trade_history 기반 daily_performance 전체 소급 재계산 (멱등) |
| GET | `/api/strategies` | 전략 목록 + 비중 + 상태 + 타겟가 + 스윙 `scan_stats` 깔때기 |
| PUT | `/api/strategies/weights` | 전략별 비중 수정 (매수금액 하한선 검증). body `{weights: {strategy_id: ratio}}` — **단위는 비율 `0.0~1.0`, 퍼센트(0~100) 금지**(2026-08-18 확정). 범위 위반 422, Σ>1.0 은 `success=false`(저장 미수행), 부분 payload(Σ<1) 허용. `GET /api/strategies` 의 `weight` 와 단위가 같아 왕복 항등 |
| PUT | `/api/strategies/{id}/params` | 전략 파라미터 수정 |
| GET | `/api/strategies/system/auto-start` | 자동 매매 설정 조회 |
| PUT | `/api/strategies/system/auto-start` | 자동 매매 설정 변경 |
| GET | `/api/strategies/system/cash-usage-ratio` | 매매 가용 자금 비율 조회 (J3, 2026-05-12) |
| PUT | `/api/strategies/system/cash-usage-ratio` | 매매 가용 자금 비율 변경 (50~100% / 5% 단위, 다음 영업일 반영) |
| GET | `/api/logs` | 시스템 로그 조회 |
| GET | `/api/recommendations` | 전략수정 AI자문 목록 (최근 30일) |
| GET | `/api/recommendations/{id}` | 단일 자문 상세 |
| POST | `/api/recommendations/{id}/apply` | 선택한 키만 전략 파라미터에 적용. **J4(2026-05-12)** — body 옵션 `apply_weight: bool=False`. true 면 `recommended_weight` 가 strategy_config.weight 로 반영 (다음 영업일 _boot 부터). 자동 적용 없음, 운영자 명시 토글에서만 |
| POST | `/api/recommendations/{id}/reject` | 자문 전체 거절 |
| GET | `/api/log-reports?days=30` | 일일 로그 분석 리포트 목록 |
| GET | `/api/log-reports/{YYYY-MM-DD}` | 단일 영업일 리포트 상세 |
| POST | `/api/log-reports/run` | 수동 트리거 — 즉시 분석 실행 (영업일당 1건 UNIQUE) |
| GET | `/api/realtime/subscriptions` | WebSocket 구독 슬롯 진단 (total/acked/fresh_60s/stale_60s/limit/tickers/reconnect_count/ws_connected) + **사이클 35/37**: `sessions[*].tickers_detail` (ticker/ticker_name/stale/last_tick/retries/last_resub/`last_cntg_hour`/`today_volume`). KIS `inquire_ccnl` 캐시(TTL 5분 + cap 20)로 KIS 실제 체결시각 동봉 — WS 구독 의심 진단용 |
| POST | `/api/realtime/resubscribe` | stale(60s 미수신) TICK 구독 종목 즉시 일괄 재구독 (J2). 응답 `{resubscribed, tickers}`. F1 자동 재구독과 별개의 운영자 수동 트리거 (ScanMonitor 인라인 버튼). WebSocket 끊김 시 400 |
| GET | `/api/realtime/market-operation` | **사이클 186** 장운영상태 (VI/거래정지/종목상태/서킷브레이커) 현황 (관찰성 전용). summary(`vi_active_count`/`halt_active_count`/`iscd_stat_active_count` + `circuit_breaker` 휴리스틱) + `details`(종목별 vi_code/halt_yn/halt_reason/mkop_cls_code, cap 200). cycle 149 H0UNMKO0 모니터 소스. RealtimeHealth 5번째 카드 노출. 매수 가드 미연계 |
| GET | `/api/strategy-funnel?strategy_id=&target_date=` | **사이클 34**: 전략별 조건검색 단계별 후보/탈락 종목 (`survived_tickers` cap 200 / `excluded_sample` cap 20) |
| GET | `/api/strategy-funnel/recent?strategy_id=&days=7` | 최근 N영업일 추이 |
| POST | `/api/strategy-funnel/snapshot` | 수동 trigger — 각 전략 `get_scan_stats()` + `get_scanned_tickers()` 로 최종 단계 (`step_no=99`) 즉시 snapshot 생성 |
| GET | `/api/stock-master/stats` | **사이클 84+** — KIS 마스터 분포 (전체/거래정지/관리종목/NXT가능/KOSPI200/KOSDAQ150 등) |
| GET | `/api/stock-master/list?market=&min_market_cap=&min_trade_amount=&ticker_name=&page=&size=` | 종목마스터 페이징 목록 (사이클 128 — 4 필터 + PostgREST 1000행 cap 해소, count="exact") |
| POST | `/api/stock-master/refresh-universe` | 전체 종목 풀 수동 갱신 (BackgroundTasks, 사이클 90/127) |
| POST | `/api/stock-master/basics/refresh` | KIS CTPF1002R 매스 보강 수동 trigger (BackgroundTasks, 사이클 126/127) |
| POST | `/api/stock-master/daily/refresh` | 일봉 적재 수동 trigger (KIS FHKST03010100, 사이클 122/127) |
| POST | `/api/stock-master/master/refresh` | KIS 공식 일일 마스터 파일 다운로드 + master_raw 갱신 (사이클 129) |
| GET | `/api/stock-master/refresh-progress` | 4 작업 통합 진행률 (5초 폴링 endpoint, 사이클 127/129) |

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
│   ├── db/                  # RDS PostgreSQL CRUD (asyncpg, pg.py)
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
│   ├── agents/              # 7개 전문 에이전트 정의 (사이클 27, 2026-05-21)
│   └── skills/              # 9개 도메인 스킬
├── Dockerfile               # 백엔드 Docker (dev/prod 멀티스테이지)
├── docker-compose.yml       # 개발 환경 Docker Compose
├── docker-compose.prod.yml  # 프로덕션 환경 Docker Compose
├── requirements.txt         # Python 의존성
└── .env                     # 환경 변수 (git 미추적)
```

## 에이전트팀 (Claude Code 하네스)

이 프로젝트는 Claude Code의 서브에이전트 + 스킬 시스템을 활용한 **다중 에이전트 협업 구조**로 개발·운영된다. 사용자 요청 유형에 따라 오케스트레이터 스킬이 적합한 에이전트와 스킬을 자동 호출한다.

### 에이전트 (`.claude/agents/`) — 7명 (사이클 27, 2026-05-21 확장)

| 에이전트 | 역할 | 모델 | 호출 시점 |
|---------|------|------|---------|
| **team-leader** | 트레이더 출신 팀장 — 매매 규칙 *정의 + 감독*, 작업 분배, 산출물 검수. 모든 사용자 요청의 1차 진입점 | opus | 전체 요청 |
| **domain-expert** *(신규 사이클 27)* | 데이/스윙 트레이더 출신 *깊이있는 자문* — 신규 전략, 파라미터 결정, 시장 미시구조, 보드 행태, 시장 레짐, KIS 거부 해석 | opus | Phase 2.5 명세 분해 *전* + 사이클 중 행위 영향 평가 |
| **tdd-engineer** | Red 테스트 선작성 + Green 검증 + 영향 인덱스 갱신 (KIS MCP 응답 시리즈 합성 포함) | opus | 모든 코드 변경의 TDD 사이클 입구 |
| **backend-dev** | FastAPI + KIS OpenAPI + 매매 엔진 + WebSocket + Supabase. 신규 API 통합 시 KIS MCP 정본 확인 | sonnet | Red 테스트 수신 후 Green 구현 |
| **frontend-dev** | React 트레이딩 대시보드 (구동 관리, 실적/잔고, 거래 내역, Settings) | sonnet | UI Red 테스트 수신 후 Green 구현 |
| **tester** | 사후 통합/경계면/E2E/안전성. KIS MCP 응답을 정본으로 양쪽 동시 읽기 | opus | 모듈 완성 후 통합 검증 |
| **refactor-expert** *(신규 사이클 27)* | *주기적* 코드 품질 검토 — 중복/명명/모듈 비대화/dead code/아키텍처 드리프트. 카드 단위 분할 + 위험 등급 + 회귀 가드 동반 | opus | Phase 4.5 — 사이클 5회 누적 또는 명시 요청 |

### 스킬 (`.claude/skills/`) — 9개

| 스킬 | 용도 | 트리거 키워드 |
|------|------|--------------|
| **auto-trading-orchestrator** | 7명 에이전트 조율 — TDD 사이클 + 도메인 자문 + 리팩토링 검토 통합 | "자동매매 시스템 구축", "전략 추가", "리팩토링", "도메인 자문" |
| **tdd-cycle** | Red→Green→Refactor 사이클 표준화 (pytest+respx+freezegun / vitest+RTL+MSW) | "TDD", "테스트 먼저", "Red/Green", "회귀 테스트" |
| **test-impact-index** | source↔test 정적 의존성 인덱스 (백엔드 Python AST + 프론트엔드 TS imports) | "영향 테스트", "변경 영향 분석", "인덱스 재생성" |
| **kis-api-integration** | KIS OAuth/REST/WebSocket/TR_ID 변환 등 연동 코드 | "KIS API", "주식 주문", "잔고 조회", "실시간 시세" |
| **trading-dashboard** | React 대시보드 화면 구현 | "대시보드", "화면", "UI", "차트" |
| **trading-test** | KIS 연동/주문 흐름/DB 정합성 통합 테스트 + Playwright E2E | "테스트", "검증", "QA", "정합성 확인" |
| **domain-consult** *(신규 사이클 27)* | domain-expert 자문 요청 흐름 — 매매 의사결정 깊이 자문 | "도메인 자문", "트레이더 시각", "파라미터 근거", "시장 미시구조" |
| **refactor-review** *(신규 사이클 27)* | refactor-expert 주기적 검토 흐름 — 행위 보존 카드 단위 권고 | "리팩토링", "코드 정리", "중복 제거", "구조 개선", "모듈 분해" |
| **kis-mcp-query** *(신규 사이클 27)* | KIS Code Assistant MCP (`mcp__kis-code-assistant__*`) 활용 가이드 — 공식 저장소 `koreainvestment/open-trading-api` 기반. backend-dev / tdd-engineer / tester / refactor-expert 공유 | "KIS 응답 재확인", "TR_ID 확인", "KIS 스펙 정본" |

### 협업 규약

- **CLAUDE.md 계층**: 루트 `CLAUDE.md` + 디렉토리별 `CLAUDE.md` (`src/`, `src/engine/`, `src/api/`, `src/db/`, `src/routes/`, `src/realtime/`, `src/auth/`, `frontend/`) 가 모듈별 컨벤션·금지사항·연동 규칙의 진실의 원천
- **단일 책임**: 각 에이전트는 자신의 역할 범위 안에서만 파일 수정. 경계면 변경(API 응답 스키마 등)은 backend-dev 가 정의 → frontend-dev 가 타입 동기화
- **검수 흐름**: 매매 규칙 변경 → (선택) domain-expert 자문 → team-leader 명세 → tdd-engineer Red → backend-dev/frontend-dev Green → tester 검증 → (사이클 5회 누적) refactor-expert 검토
- **KIS MCP 통합**: 신규 API 통합 / 응답 분기 / 회귀 시나리오 합성 / 응답 처리 통일 시 `kis-mcp-query` 스킬 — `docs/kis/` 로컬 캐시와 MCP 응답 불일치 시 *MCP 가 정본*

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

## 스케줄 — KRX/NXT 통합 운영 (08:00~20:00)

```
 부팅            NXT 프리      KRX 메인           KRX 마감 → NXT 애프터              정산
─────────────┬────────┬─────────────────────┬──────────────────────┬────────────
 07:45 07:55 07:59│08:00       09:00:05  09:30   15:20  15:30          19:50  20:00 20:10
  │    │    │    │    │           │       │      │     │              │      │     │
  ▼    ▼    ▼    ▼    ▼           ▼       ▼      ▼     ▼              ▼      ▼     ▼
 자동 prepare WS 사전 익일청산   KRX 시가  모멘텀  KRX  KRX 마감       NXT 애프터  정산
 시작 토큰   연결 구독 (NXT 08:00 확정+VB/  스캔+   메인  → NXT 애프터   매수중단    +DB
      포지션      돌파 +30초 안정) LTV MAIN 매매   매수  전환 (구독 유지)+AI자문    적재
      복구       종목  + VB/LTV  매매 진입 시작   중단  POST_NXT 매매            (OpenAI)
                       PRE_NXT                  +KRX  활성 (VB/LTV)              일일
                       매매 시작                메인                              로그
                                                강제                              분석
                                                청산
                                                (POST_NXT
                                                미활성
                                                전략만)
```

| 시각 | 동작 |
|------|------|
| 07:45 | 자동 매매 시작 (AUTO_START 활성 시, 주말+공휴일 자동 건너뜀 — KIS chk-holiday API) |
| 07:55 | `_boot()` — 토큰 사전 순차 발급 (사이클 20: 메인+보조 N 분당 1개 한도 직렬화) → DB 포지션 복구 → KIS 잔고 교차 검증 → 미체결 복구 → `stock_master` eager 갱신 (보유+익일청산) → 매크로 fetch + `market_regime_snapshots` INSERT → `cash_usage_ratio` 자동 조정 → 전략 prepare |
| 07:59 | 사전 구독 — 돌파(VB/LTV) + 스윙(donchian) 스캔 종목 + 보유 포지션. WebSocket 연결 + 체결통보 + (실전) `H0UNMKO0` 구독. 유니버스 비어있으면 prepare 재실행 |
| 08:00 | NXT 프리 진입 — 익일 청산 백그라운드 (`NEXT_DAY_STABILIZE_SECS=30s` 안정화 후 NXT 시가 청산). 사이클 26: VB/LTV PRE_NXT 매수 제거됨 (`tradable_boards=("main",)`) — `_confirm_breakout_open_prices(board="pre_nxt")` 호출 안 함 |
| **08:59:10** | **사이클 26 신규 — KRX 채널 사전 구독 마진 (50초)**: `_board_transition_loop("H0NXCNT0", "H0STCNT0", 보유+익일청산)` 종목별 원자 전환 + 매수 후보 신규 KRX subscribe. 09:00 KRX 첫 체결 tick 즉시 수신 보장 |
| 09:00:05 | KRX 메인 시가 확정 — `_confirm_breakout_open_prices(board="main")` VB/LTV target_price 계산 (KRX 09:00 시가 + 전일Range × `k_value_krx_main`). 직후 `_drain_pending_next_day_clear()` — 08:00 보류 종목 KRX 시장가 일괄 청산 |
| 09:05~09:30 | donchian 스윙 진입창 — 시장가 1주문/종목, 갭 +3%↑ 스킵 |
| 09:30 | 모멘텀(상한가) 종목 스캔 시작, 매수 감시. 5분 주기 `_scan_loop` 시작 — 모멘텀+돌파+스윙+보유 합집합 시세 재구독 |
| 15:20 | KRX 메인 신규 매수 중단 + 강제 청산 (`_force_clear_main_only`) — VB 전체 + LTV 상한가 미도달 청산. 시간 가드(2026-05-15 hotfix): `>=15:30` 진입 시 skip + 익일 청산 안전망 위임 |
| 15:30 | KRX 메인 마감 (15:30~15:39:59 종가 흡수 마진 — MAIN 보드 유지). 사이클 26: `_confirm_breakout_open_prices(board="post_nxt")` 호출 제거 (VB/LTV `tradable_boards` 에 post_nxt 없음 → 시가 확정 대상 없음) |
| **15:39:10** | **사이클 26 신규 — NXT 채널 사전 구독 마진 (50초)**: `_board_transition_loop("H0STCNT0", "H0NXCNT0", 보유+익일청산)` 종목별 원자 전환 + 매수 후보 KRX unsubscribe |
| **15:40** | **사이클 26 — POST_NXT 진입** (기존 15:30 → 15:40 변경). 매도만 (VB/LTV `tradable_boards=("main",)`) |
| 16:40 | (장 마감 후 데이터 계층) 퀀트 재무 5 TR 주1회 적재 — `_stock_master_financial_load_task_loop` (마스터 16:30 후 stagger, 주1회 신선도 게이트). 매매 무관 (사이클 C1~C3, 마법공식·F-Score-7 원천) |
| 19:50 | NXT 애프터 신규 매수 중단 + 전략수정 AI 자문 생성 (OpenAI → `parameter_recommendations`) + 직후 `auto_apply_recommendations()` (사이클 23, 감액만 + 50% cap, `auto_apply_enabled=true` 시) |
| 20:00 | NXT 애프터 종료, WebSocket 구독 해제 |
| 20:10 | 전략별 + 합산 일일 정산, DB 실적 기록. 직후 일일 로그 분석 리포트 생성 (OpenAI → `daily_log_reports`). 직후 `purge_old_logs()` (INFO 2일 / WARNING+ 30일 retention 자동 정리, 사이클 6) |

**중간 시각 시작 시**: 현재 시각 이후 스케줄부터 실행 (20:10 이후 시작 거부)

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

