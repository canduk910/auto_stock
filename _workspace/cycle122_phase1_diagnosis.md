# 사이클 122 Phase 1 진단 — KIS 일봉 도입 + stock_master_daily 정규화

작성: 2026-06-12 (금) team-leader
모델: opus
대상: 사용자 결정 의제 (Q1~Q4) + domain-expert 자문 의제 (A1~A6)

---

## 0. 사용자 결정 (확정)

1. 데이터 출처: **KIS `inquire_daily_itemchartprice`** (FHKST03010100, 종목당 호출)
2. DB 구조: **신규 테이블 `stock_master_daily`** (정규화)
3. 활용 전략: donchian (20일 신고가) / VCP (base 패턴 + Pullback) / VB (ATR)
4. domain-expert 자문 의무

---

## 1. KIS MCP 정본 검증 (FHKST03010100)

### 정본 출처
- URL: `https://github.com/koreainvestment/open-trading-api/tree/main/examples_llm/domestic_stock/inquire_daily_itemchartprice/inquire_daily_itemchartprice.py`
- API 명: `국내주식기간별시세(일/주/월/년)` `[v1_국내주식-016]`

### 엔드포인트 영역
| 항목 | 값 |
|------|----|
| URL | `/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice` |
| TR_ID (real/demo) | `FHKST03010100` (FH 접두사 시세성 = 모의/실전 동일) |
| 1회 응답 최대 | **100일** (KIS 공식 한도, 사이클 33 기록 영속) |
| `fid_org_adj_prc` | `0` (수정주가) / `1` (원주가) — 우리 결정: **`0` 수정주가** (액면분할/배당 흡수, donchian 신고가 정합) |
| `fid_period_div_code` | `D` (일봉) / `W` / `M` / `Y` |

### 요청 파라미터 영역
```
FID_COND_MRKT_DIV_CODE: J (KRX) / NX (NXT) / UN (통합) — 우리 결정: J 단독
FID_INPUT_ISCD: 종목코드 6자리 (예: 005930)
FID_INPUT_DATE_1: 조회 시작일자 (YYYYMMDD)
FID_INPUT_DATE_2: 조회 종료일자 (YYYYMMDD, 최대 100일)
FID_PERIOD_DIV_CODE: D
FID_ORG_ADJ_PRC: 0
```

### 응답 영역
- `output1` (object, dict) — 종목 메타 (현재가/HTS시총/PER/EPS 등) — **본 사이클 미사용**
- `output2` (array of dict, 최신순) — 일봉 시계열 (핵심 영역)

`output2` 핵심 필드 (chk 파일 COLUMN_MAPPING 정본 인용):
```
stck_bsop_date     주식 영업 일자 (YYYYMMDD, 영업일 기준 + KIS 일봉)
stck_clpr          주식 종가
stck_oprc          주식 시가2
stck_hgpr          주식 최고가
stck_lwpr          주식 최저가
acml_vol           누적 거래량 (당일 일봉 종가 기준 = 일일 거래량 정합)
acml_tr_pbmn       누적 거래 대금 (원 단위)
flng_cls_code      락 구분 코드 (액면분할/유상증자 등)
prtt_rate          분할 비율 (액면분할 시점 감지용)
mod_yn             변경 여부 (수정주가 흡수 여부)
prdy_vrss_sign     전일 대비 부호 (1 상한, 2 상승, 3 보합, 4 하한, 5 하락)
prdy_vrss          전일 대비
revl_issu_reas     재평가사유코드
```

### 기존 코드 영역 영속 (`src/api/condition.py:445`)

이미 `fetch_daily_candles(ticker, days=21)` 가 동일 KIS API 호출 영역:
- TTL 캐시 `_CANDLE_CACHE_TTL=300s` + single-flight + epoch 가드 (PR-C2 사이클 14)
- 호출 패턴: VCP/donchian/VB/LTV/BFB 5 전략 prepare 영역 (전수 활용)
- 윈도우: `days + days // 2 + 10` 달력일 (영업일/달력일 5/7 + 마진)

**중요**: 본 사이클 = `fetch_daily_candles` 재사용 + 영속화 (memcache → DB) 영역. 신규 KIS API 도입 0건.

### Rate Limit / KIS 안전 영역
- 메인 단일 `kis_request` 영역 = `asyncio.Semaphore(20)` 초당 20건 + 자동 재시도 3회 (지수 백오프)
- 시세성 풀 `kis_get_quote` 영역 = 보조 라운드로빈 + per-label `Semaphore(18)` + 메인 fallback
- 본 API 화이트리스트 영속 (`src/api/base.py:64`): `/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice` 등록 영속

---

## 2. 신규 테이블 `stock_master_daily` 스키마 설계

### 의도
- VCP/donchian/VB 전략의 일봉 기반 매수 신호 사전 시뮬레이션 영역 영속화
- 현재 = 매 사이클마다 KIS 호출 (5분 캐시) → 운영 부담 + 시세성 풀 흡수 5분 윈도우 만료 시 재호출
- 신규 = 매일 16:00 KST 일괄 적재 + DB 조회 (Supabase) → KIS 호출 1/일 + ms 단위 조회

### 컬럼 영역 (`supabase/migrations/033_stock_master_daily.sql`)
```sql
CREATE TABLE IF NOT EXISTS stock_master_daily (
    ticker         TEXT NOT NULL,
    bas_dd         DATE NOT NULL,
    open_price     INTEGER NOT NULL DEFAULT 0,
    high_price     INTEGER NOT NULL DEFAULT 0,
    low_price      INTEGER NOT NULL DEFAULT 0,
    close_price    INTEGER NOT NULL DEFAULT 0,
    volume         BIGINT NOT NULL DEFAULT 0,
    trade_value    BIGINT NOT NULL DEFAULT 0,
    change_rate    NUMERIC(8,4) NOT NULL DEFAULT 0,
    flng_cls_code  TEXT NOT NULL DEFAULT '',
    prtt_rate      NUMERIC(8,4) NOT NULL DEFAULT 0,
    raw            JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (ticker, bas_dd)
);

-- 최근 N일 조회 인덱스 (donchian 20일 / VCP 60~120일 / VB 14일 ATR)
CREATE INDEX IF NOT EXISTS idx_stock_master_daily_ticker_bas_dd
    ON stock_master_daily (ticker, bas_dd DESC);

-- 영업일 전체 조회 인덱스 (적재 진단 + 회고 분석용)
CREATE INDEX IF NOT EXISTS idx_stock_master_daily_bas_dd
    ON stock_master_daily (bas_dd DESC);

COMMENT ON TABLE stock_master_daily IS
    'KIS FHKST03010100 일봉 정규화 테이블 (사이클 122). 매일 16:00 KST 적재 + donchian/VCP/VB 전략 영역 활용.';
COMMENT ON COLUMN stock_master_daily.ticker IS 'KRX 6자리 단축코드 (stock_master.ticker 와 정합)';
COMMENT ON COLUMN stock_master_daily.bas_dd IS '영업일 기준일 (KIS stck_bsop_date)';
COMMENT ON COLUMN stock_master_daily.flng_cls_code IS '락 구분 코드 (액면분할/배당 등) — VCP 종가 라인 진단';
COMMENT ON COLUMN stock_master_daily.prtt_rate IS '분할 비율 — 액면분할 시점 감지용';
COMMENT ON COLUMN stock_master_daily.raw IS 'KIS output2 row 원본 (사이클 81 G-AST1 raw merge 영속 답습)';
```

### 설계 결정 영역
- **PK = `(ticker, bas_dd)` 복합** — 동일 영업일 재적재 시 ON CONFLICT 영역 영구 영속
- **수정주가 (`FID_ORG_ADJ_PRC=0`)** 채택 — 액면분할/배당 흡수 영역 + donchian/VCP 신고가 라인 정합
- **`flng_cls_code` + `prtt_rate`** 영구 보존 — 액면분할 발생 시 추적 가능 (카드 #15 LOW Q7-2 답습 영역)
- **`raw` JSONB** — 사이클 81 G-AST1 raw merge 영속 답습 (미래 신규 키 흡수 영역)
- **`updated_at` 컬럼** — 동일 영업일 재적재 시 갱신 추적 (사이클 32 R4 stale 가드 답습)

### Supabase 부하 영역
- 2,700 종목 × 100일 적재 (백필 가정) = 270,000 행 = ~30MB (raw JSONB 평균 100B × 27만 행)
- 일일 적재 (사이클 122 의무 영역) = 2,700 종목 × 1일 = 2,700 행/일 = ~0.3MB/일
- 1년 적재 = ~100MB (Supabase 무료 tier 500MB = 안전)
- 90일 retention (사이클 6 답습) = ~30MB 영구 안정

---

## 3. 활용 전략 영역 데이터 매트릭스

| 전략 | 필요 데이터 | 활용 함수 | 일봉 조회 영역 |
|------|-----------|----------|------|
| donchian | 20일 신고가 (close_price MAX) | `get_donchian_high(ticker, days=20)` | 사이클 122 신규 |
| donchian | 60일 EMA (close_price 평균) | `get_recent_daily(ticker, days=60)` | 사이클 122 신규 |
| VCP | 베이스 검출 (60일 패턴) | `get_recent_daily(ticker, days=120)` | 사이클 122 신규 |
| VCP | 베이스 ATR | `get_atr(ticker, days=14)` | 사이클 122 신규 |
| VB | 14일 ATR (high - low + 갭) | `get_atr(ticker, days=14)` | 사이클 122 신규 |
| VB | 전일 Range (K값 계산용) | `get_recent_daily(ticker, days=2)` | 사이클 122 신규 |

### 신규 헬퍼 영역 (`src/db/stock_master_daily.py`)
```python
async def upsert_daily(ticker: str, bas_dd: date, ohlcv: dict) -> None
async def upsert_daily_batch(rows: list[dict]) -> int  # 100건 단위 batch
async def get_recent_daily(ticker: str, days: int = 20) -> list[dict]  # bas_dd DESC
async def get_donchian_high(ticker: str, days: int = 20) -> int | None
async def get_atr(ticker: str, days: int = 14) -> float | None
async def count_all() -> int  # UI 진단 영역
async def count_by_ticker(ticker: str) -> int  # 적재 진단
async def get_last_bas_dd(ticker: str) -> date | None  # 점진 적재 영역
```

---

## 4. 스케줄러 통합 영역

### 시점 결정 (Q1 의제)
- **옵션 A**: 매일 16:00 KST 1회 일괄 적재 (KRX 메인 종료 30분 후, KIS LMS chain 안전 마진)
- **옵션 B**: 시간대 분산 (16:00 KOSPI + 16:30 KOSDAQ + 17:00 우선주, KIS 부담 분산)
- **옵션 C**: 매일 20:00 KST 일괄 적재 (사이클 100/106 stock_master 갱신 영역과 통합)

**team-leader 권고**: 옵션 A (16:00 KST 일괄, 사이클 106 답습 + KRX 메인 종료 후 안전 영역)

### 의존성 영역
- `_full_universe_load_once` (사이클 101+106 영속) 완료 후 호출 의무 (stock_master ~2,800 종목 PK 의존)
- 사이클 106 lifecycle race 차단 패턴 답습 (start() 직후 즉시 1회 + while 루프 + asyncio.sleep)

### 추정 소요 영역
- 2,700 종목 × 1 KIS 호출 + 50ms sleep (사이클 83/91/97/107 답습) = 약 4.5분
- KIS LMS chain 안전 마진 (사이클 17 OPSP0002 backoff 영속)

---

## 5. 사용자 결정 의제

### Q1: 갱신 주기
- A. 매일 16:00 KST 1회 일괄 (team-leader 권고, KRX 메인 종료 30분 후)
- B. 시간대 분산 (16:00 KOSPI + 16:30 KOSDAQ)
- C. 매일 20:00 KST 일괄 (사이클 100/106 영역과 통합)

### Q2: 일봉 기간
- A. T-20일 (donchian 최소 + 빠른 적재, ~1초/종목 × 2,700 = ~45분 → 너무 길음 — 적합 X)
- B. T-60일 (donchian 60일 EMA + VCP base 일부, **권고**)
- C. T-100일 (KIS 1회 호출 한도 = 단일 호출 영역, VCP 120일 EMA 부분 가능 — 권고 강함)

**team-leader 권고**: **C. T-100일** (KIS 1회 호출 한도 활용 + VCP `effective_ema_long` ~95 안정 영역 + 사이클 33 KIS_DAILY_CANDLES_MAX 영속 패턴)

### Q3: 신규 적재 vs 점진 적재
- A. 신규 적재 (T-100일 전수, 사이클 122 = 약 4.5분 소요 / 270,000 행)
- B. 점진 적재 (사이클 122 = D-1 신규 적재 / 사이클 123+ = D-1 신규 행만 매일 1행 추가)

**team-leader 권고**: **B 옵션 (사이클 122 = T-100일 백필 + 사이클 123+ = 일일 1행 추가)** — KIS 호출 최소화 + DB 부하 분산

### Q4: VCP/donchian/VB 활용 시점
- A. 사이클 122 통합 (DB 적재 + 5 전략 prepare 영역 전환 동시)
- B. 별개 사이클 (사이클 122 = DB 적재만 / 사이클 123+ = 전략 prepare 전환)

**team-leader 권고**: **B 옵션 (사이클 122 = DB 적재 + 헬퍼 함수 영역만 / 사이클 123+ = 전략 prepare 전환)** — 회귀 위험 분리 + 운영 1일 데이터 적재 실측 의무 (D+1 측정)

---

## 6. domain-expert 자문 의제 (HIGH 영역)

### A1: 사이클 49 VCP Pullback 시정 영속 영향 평가
- 사이클 49 시정 = `_check_pullback_sequence` ATR threshold ZigZag + state machine
- 신규 일봉 영역 도입 시 VCP Pullback 영역 영향 평가 의무
- 기대: ATR 영역 = 사이클 49 영속 (DB 조회 영역 변경만, 알고리즘 무변경)

### A2: LMS chain 위험 평가
- 2,700 종목 × 100ms = 4.5분 소요 (이상적)
- KIS OPSP0002 backoff 영속 (사이클 17, 300s)
- 16:00 KST 시점 = KRX 메인 종료 30분 후 (사용자 거래 종료 영역, 안전)

### A3: DB 부담 평가
- 적재 부하 (Supabase HTTP/2 stale connection 우려, 사이클 26 답습)
- 회피 영역 = batch upsert (100건 단위) + 50ms sleep (KIS 호출 영역과 동시)

### A4: 갱신 주기 권고
- 매일 16:00 KST 1회 vs 시간대 분산
- domain-expert 영역 = 매매 의사결정 영역 (단순 일봉 = 16:00 안정 영역 가정)

### A5: 일봉 적재 실패 시 graceful 영역 영향
- 사이클 88 G-REJECT 영속 (외부 LLM 단순 graceful 추천 거부, 영역 단위 graceful 의무)
- 일봉 적재 실패 시 = 5 전략 prepare 영역 영향 (donchian/VCP/VB/LTV/BFB)
- 회피 영역 = stock_master_daily 미존재 시 KIS 호출 fallback (사이클 81 G-AST1 graceful 답습)

### A6: D+1 운영 측정 의무
- 사이클 122 push + EC2 자동 배포 후 익일 (D+1) 16:00 KST 영역 실측
- 측정 영역: `[stock_master_daily_load] start/complete total=N elapsed_ms=K kospi=L kosdaq=M`
- stock_master_daily count_all() ≥ 2,700 영구 영속 영역 확인

---

## 7. 영속 의무 매트릭스

- 사이클 17 OPSP0002 backoff 영속 (300s, KIS LMS chain 차단)
- 사이클 32 R4 universe guard 영속 (보유/익일청산 절대 보호)
- 사이클 38 명문화 영속 (scanner 매수 진입 전 영역 한정)
- 사이클 49 VCP Pullback ATR ZigZag 영속
- 사이클 81 G-AST1 raw JSONB merge 영속 (사이클 122 신규 테이블 raw 컬럼 답습)
- 사이클 88 G-REJECT 영속 (graceful 영역 단위 의무)
- 사이클 101+106 `_full_universe_load_*` lifecycle race 차단 영속 (사이클 122 task loop 답습)
- 사이클 107 inquire_stock_basics merge 패턴 영속 (raw JSONB 통합 영역)
- 사이클 117 basDd 전일 영업일 영속 (적재 시점 정합)
- 사이클 119/120/121 영속
- CLAUDE.md "절대 깨지 말 것" 8 영역 영속

---

## 8. Phase 2.5 분해 (사용자 결정 후)

### 영역 1 (DB, backend-dev)
- `supabase/migrations/033_stock_master_daily.sql` 신규 (Supabase MCP `apply_migration` 적용 영역, 사이클 84 답습)
- `src/db/stock_master_daily.py` 신규 (CRUD + 활용 함수 8종)

### 영역 2 (API 호출, backend-dev)
- 기존 `src/api/condition.py::fetch_daily_candles` 재사용 (KIS 호출 영역 100% 답습)
- 신규 함수 0건 (사이클 122 = 기존 영역 재사용 영구 영속)

### 영역 3 (스케줄러 통합, backend-dev)
- `src/engine/scheduler.py`
- 신규 task: `_stock_master_daily_load_task_loop` (사이클 106 lifecycle race 차단 패턴 답습)
- TIME_STOCK_MASTER_DAILY_LOAD = time(16, 0) 신규 상수

### 영역 4 (테스트, tester)
- 회귀 가드 영역:
  - HIGH 5: DB upsert + KIS 호출 패턴 영속 + 활용 함수 (3) + graceful
  - MEDIUM 3: 영업일 캘린더 (사이클 117 답습) + Rate Limit + 갱신 주기
  - AST 2: KIS TR_ID 영속 + DB schema 영속

---

## 9. 매매 안전성 평가

- scanner 단계 매수 진입 전 일봉 데이터 조회 영역 영구 영속
- 매도/익일청산/15:20 강제청산 hot path 무관 영구 영속
- 사이클 49 VCP Pullback 영속 (DB 조회 영역 변경만 + 알고리즘 무변경)
- 사이클 88 G-REJECT 영속 (graceful 영역 단위)
- 사이클 32 R4 영속 (보유/익일청산 절대 보호)

---

## 10. 결론 및 다음 행동

### 결정 의제 → 사용자 확인
- Q1: 갱신 주기 (team-leader 권고 A. 매일 16:00 KST)
- Q2: 일봉 기간 (team-leader 권고 C. T-100일, KIS 1회 호출 한도 활용)
- Q3: 신규 vs 점진 적재 (team-leader 권고 B. T-100일 백필 + 일일 1행 추가)
- Q4: 전략 활용 시점 (team-leader 권고 B. 사이클 122 = DB 적재만 + 사이클 123+ = 전략 전환)

### 다음 단계
1. domain-expert 자문 (A1~A6) 의무
2. 사용자 결정 (Q1~Q4) 확인
3. Phase 2.5 분해 (영역 1~4) 후 tdd-engineer Red 명세 → backend-dev Green
4. D+1 운영 실측 의무 (2026-06-13 토 또는 다음 영업일 16:00 KST)
