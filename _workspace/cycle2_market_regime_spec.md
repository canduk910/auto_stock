# 사이클 2 — 시장 레짐 필터 + dkstock.cloud 매크로 연동

작성: 2026-05-17, team-leader
사용자 확정 옵션: **1b + 2b + 3a + 4a** (self-contained 실행)

## 배경

직전 사이클 1(af4af24) — 비중조절 사유 분리 + UI 카드 순서. 5/18 월 20:00 자문 발화 검증 대기.
본 사이클은 외부 매크로 데이터 연동 + 시장 레짐 기반 매수 가드 + cash_usage_ratio 자동 조정.

## 외부 의존: `https://dkstock.cloud`

- 봇 계정: `autostock` / `AUTOSTOCK1` (대문자 필수)
- JWT Bearer, access_token ~7일 만료, refresh_token 갱신 가능
- 활용 endpoint 3개:
  - `/api/macro/macro-cycle` — regime/cycle/params(cash_min 등)
  - `/api/macro/sentiment` — vix/fear_greed/buffett
  - `/api/macro/indices` — sparkline (정보용)
- 운영 토글: `DKSTOCK_REGIME_ENABLED=false` (기본 비활성, EC2 운영자 명시 활성화)

## 매수 가드 (1b — 복합 임계 OR)

다음 중 1개 이상 발동 시 **모든 전략 매수 차단** (`risk.py` 의 `on_tick` 매수 분기 진입 전):
- `regime.regime == "defensive"` (= 방어/현금 비중 권고)
- `vix.value > 25`
- `fear_greed.score > 85` (극도 탐욕)
- `fear_greed.score < 15` (극도 공포)

**매도/손절은 영향 없음** — `check_exit_signal` 분기 그대로 작동, 보유 종목 청산 정상.

## cash_usage_ratio 자동 조정 (2b)

- `cash_usage_ratio = clamp((100 - regime.params.cash_min) / 100, 0.0, 1.0)`
- defensive (cash_min=75) → 0.25 / neutral (cash_min=50) → 0.5 / aggressive (cash_min=20) → 0.8
- 현 J3 범위 [0.5, 1.0] 5% step → **[0.0, 1.0] 확장**. step 은 0.05 유지(보정 안정성)
- `_boot()` 흐름: ① 매크로 fetch → ② snapshot INSERT → ③ `auto_regime_adjust=true` 시 자동 갱신 (운영자 수동값 덮어씀) → ④ `allocate_funds()` 호출 (기존 J3 흐름 연결)
- 운영자 토글 `auto_regime_adjust` (`system_config` 키, 기본 `true`): false 시 수동 cash_usage_ratio 그대로

## Dashboard 매크로 레짐 카드 (3a)

- 신규 컴포넌트: `frontend/src/components/MarketRegimeCard.tsx`
- 위치: Dashboard 환경 배너 직하 (자기 결정 — 사용자 검토 가능 위치)
- 노출:
  - regime + label + desc (색상: defensive=red / neutral=gray / aggressive=blue)
  - VIX 값 + level
  - Fear & Greed Score + label + 컴포넌트
  - Buffett Ratio + level
  - cycle.phase + label
  - 자동 cash_usage_ratio + auto_regime_adjust 토글 (ConfirmModal 이중 확인)
  - 매수 가드 활성 시 amber/red 배너 + block_reason
- API: `/api/market-regime/current` + `/api/market-regime/history?days=30`

## DB 테이블 (4a)

`supabase/migrations/022_market_regime_snapshots.sql` (적용 보류):
```sql
CREATE TABLE market_regime_snapshots (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  snapshot_date DATE NOT NULL,
  regime TEXT NOT NULL,
  regime_desc TEXT,
  cycle_phase TEXT,
  vix NUMERIC(8,2),
  fear_greed_score NUMERIC(5,2),
  buffett_ratio NUMERIC(8,2),
  raw_response JSONB NOT NULL,
  computed_cash_usage_ratio NUMERIC(4,3),
  buy_blocked BOOLEAN NOT NULL,
  block_reason TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(snapshot_date)
);
CREATE INDEX idx_market_regime_date ON market_regime_snapshots (snapshot_date DESC);
```

`supabase/migrations/023_cash_usage_ratio_range.sql` (적용 보류):
- 코드 영역 (DB CHECK 제약 없음) 범위만 [0.0, 1.0] 확장. SQL 은 COMMENT 갱신만.

## 안전 원칙

1. **graceful fallback**: 외부 서버 다운/timeout/토큰 만료 시 매수 가드 비활성 (기존 동작 유지). cash_usage_ratio 도 운영자 수동값 보존.
2. `DKSTOCK_REGIME_ENABLED=false` 기본값 — 운영 초기 외부 호출 0건.
3. 매도/손절 영향 없음 — 보유 종목 청산 정상.
4. `auto_regime_adjust=false` 시 cash_usage_ratio 자동 갱신 안 함.

## 산출물

### 백엔드 (신규)
- `src/services/dkstock_client.py` (~250 LOC) — JWT 로그인/리프레시/macro fetch + 24h 메모리 캐시
- `src/engine/market_regime.py` (~250 LOC) — MarketRegime 싱글톤 + `is_buy_allowed` + `cash_usage_ratio_from_regime`
- `src/db/market_regime_snapshots.py` (~100 LOC) — CRUD
- `src/routes/market_regime.py` (~80 LOC) — current/history/auto-adjust
- `src/models/market_regime.py` (~80 LOC) — Pydantic

### 백엔드 (수정)
- `src/config.py` — DKSTOCK_* 4 필드
- `src/db/system_config.py` — `get/set_auto_regime_adjust`, cash_usage_ratio 범위 [0.0, 1.0]
- `src/engine/scheduler.py::_boot()` — 매크로 fetch + snapshot + 자동 조정 통합
- `src/engine/risk.py::on_tick()` — 매수 가드 (매도 무관)
- `src/main.py` — `/api/market-regime` router 등록

### 프론트엔드 (신규)
- `frontend/src/components/MarketRegimeCard.tsx` (~250 LOC)
- `frontend/src/types/market_regime.ts`
- `frontend/src/api/market_regime.ts`

### 프론트엔드 (수정)
- `frontend/src/pages/Dashboard.tsx` — MarketRegimeCard 삽입

### 마이그
- `supabase/migrations/022_market_regime_snapshots.sql` (작성, 적용 보류)
- `supabase/migrations/023_cash_usage_ratio_range.sql` (작성, COMMENT only)

### 테스트 (Red 선)
- `tests/unit/services/test_dkstock_client.py` (7 케이스 A-G)
- `tests/unit/engine/test_market_regime.py` (9 케이스 A-I)
- `tests/unit/db/test_market_regime_snapshots.py` (3 케이스)
- `tests/integration/test_market_regime_boot.py` (1 케이스)
- `tests/unit/db/test_system_config_auto_regime.py` (3 케이스)
- `frontend/src/components/__tests__/MarketRegimeCard.test.tsx` (5+ 케이스)

### 문서
- `src/engine/CLAUDE.md` — market_regime 섹션 + risk.py 매수 가드
- `frontend/CLAUDE.md` — MarketRegimeCard
- `_workspace/00_leader_trading_rules.md` — 사이클 2 섹션
- `docs/HARNESS_CHANGELOG.md` — 1행

## 운영 활성화 절차 (커밋/배포 후)

1. EC2 `.env` 추가:
   ```
   DKSTOCK_API_URL=https://dkstock.cloud
   DKSTOCK_USERNAME=autostock
   DKSTOCK_PASSWORD=AUTOSTOCK1
   DKSTOCK_REGIME_ENABLED=false   # 1단계: false 로 코드만 배포
   ```
2. Supabase 마이그 022, 023 적용
3. `DKSTOCK_REGIME_ENABLED=true` 로 토글 + 서비스 재기동
4. Dashboard MarketRegimeCard 에서 첫 fetch 확인
5. 보수 운영 권고: 5/18 월 20:00 사이클 1 자문 검증 완료 후 활성화
