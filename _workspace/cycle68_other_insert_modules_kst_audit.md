# 사이클 68 — 기타 INSERT 모듈 UTC → KST 일관성 감사 보고서

**카드**: #17 (LOW, 사이클 65 hotfix H3 인계)
**작성일**: 2026-06-06 (토, KRX 휴장)
**책임**: team-leader → tdd-engineer Red → backend-dev Green → tester Verify
**선행**: 사이클 65 hotfix H2 (`src/db/system_logs.py`) + H2-bis (`src/main.py::_insert_log_to_db`)
**원칙**: 시정 + AST 가드만 (기존 UTC 데이터 백필 변환 = 카드 #18 별개 사이클)

---

## Phase 1 — 점검 대상 INSERT 모듈 표

| # | 모듈 | 테이블 | 시각 컬럼 (코드 명시) | KST 명시 여부 | DB DEFAULT |
|---|------|-------|---------------------|--------------|------------|
| 1 | `src/db/system_logs.py` | `system_logs` | `timestamp` | **KST 명시** (사이클 65 H2) | `now()` (UTC) |
| 2 | `src/main.py::_insert_log_to_db` | `system_logs` | `timestamp` | **KST 명시** (사이클 65 H2-bis) | `now()` (UTC) |
| 3 | `src/db/trade_history.py::insert_trade` | `trade_history` | `timestamp` | **KST 명시** (`datetime.now(KST)`) | `now()` (UTC) |
| 4 | `src/db/positions.py::save_position` | `positions` | `buy_date` (DATE only) | DATE — KST 무관 | `updated_at` DB DEFAULT |
| 5 | `src/db/positions.py::update_high` | `positions` | `updated_at` | **미명시 → DB DEFAULT (UTC)** | `now()` (UTC) ← 갱신 시 자동 안 됨, **stale 위험** |
| 6 | `src/db/daily_performance.py::upsert_daily_performance` | `daily_performance` | `date` (DATE only) | DATE — KST 무관 | (없음) |
| 7 | `src/db/strategy_config.py::save` | `strategy_config` | `updated_at` | **미명시 → DB DEFAULT (UTC)** | `now()` (UTC) ← 갱신 시 자동 안 됨, **stale 위험** |
| 8 | `src/db/system_config.py` (6 upsert 호출) | `system_config` | `updated_at` | **미명시 → DB DEFAULT (UTC)** | `now()` (UTC) ← 갱신 시 자동 안 됨, **stale 위험** |
| 9 | `src/db/parameter_recommendations.py::insert_recommendation` | `parameter_recommendations` | `created_at` | **미명시 → DB DEFAULT (UTC)** | `now()` (UTC) |
| 10 | `src/db/parameter_recommendations.py::update_recommendation_status` | `parameter_recommendations` | `applied_at` / `rejected_at` | **KST 명시** (`datetime.now(KST)`) | (DB DEFAULT 없음) |
| 11 | `src/db/log_reports.py::insert_log_report` | `daily_log_reports` | `created_at` | **미명시 → DB DEFAULT (UTC)** | `now()` (UTC) |
| 12 | `src/db/backtest_runs.py::insert_run` | `backtest_runs` | `created_at` | **UTC 명시** (`datetime.now(timezone.utc)`) | `now()` (UTC) |
| 13 | `src/db/backtest_runs.py::update_status` | `backtest_runs` | `completed_at` | **UTC 명시** (추정 — 동일 모듈) | (DB DEFAULT 없음) |
| 14 | `src/db/market_regime_snapshots.py::insert_snapshot` | `market_regime_snapshots` | `created_at` | **UTC 명시** (`datetime.now(timezone.utc)`) | `now()` (UTC) |
| 15 | `src/db/kis_quote_accounts.py::insert_account` | `kis_quote_accounts` | `created_at` + `updated_at` | **UTC 명시** (`datetime.now(timezone.utc)`) | `now()` (UTC) |
| 16 | `src/db/kis_quote_accounts.py::update_account` | `kis_quote_accounts` | `updated_at` | **UTC 명시** | (DB DEFAULT 없음 → 미명시 시 stale) |
| 17 | `src/db/stock_master.py::upsert_one` | `stock_master` | `refreshed_at` | **UTC 명시** (`datetime.now(timezone.utc)`) | `now()` (UTC) |
| 18 | `src/db/strategy_funnel.py::insert_snapshot` | `strategy_funnel_snapshots` | `snapshot_at` | **미명시 → DB DEFAULT (UTC)** | `now()` (UTC) |

> **DB DEFAULT 상세**: `updated_at` 컬럼의 `DEFAULT now()` 는 **INSERT 시점에만** 발화 — UPDATE/UPSERT 갱신 시 자동 갱신 안 됨 (PostgreSQL 표준). 즉 `system_config` / `strategy_config` / `positions::update_high` 가 코드에서 `updated_at` 미명시 → 첫 INSERT 후 영원히 stale UTC 시각 잔존.

---

## Phase 2 — silent 결함 분류

### HIGH (운영 분석/추적 직결, 사용자 노출)
1. **`stock_master.refreshed_at` UTC 저장** (모듈 #17) — `is_stale(ticker)` 24h TTL 판정의 baseline. UTC 저장 + KST 비교 시 9시간 오차 → TTL 만료 시점이 KST 23:00 ≠ KST 24:00 (운영자 직관 위배). **단**, `is_stale` 내부도 UTC 로 비교 (`datetime.now(timezone.utc) - refreshed_at`) → 현재 동작 자체는 정확. **사용자 노출 시점**: Settings/Admin UI 가 "마지막 갱신: 2026-06-06 12:34 UTC" 식으로 직접 표시할 경우 혼란. 현재 UI 노출 X → **자체 동작은 무영향, KST 정책 일관성만 위반**.

### MEDIUM (분석 보조 / 정책 일관성 위반)
2. **`parameter_recommendations.created_at` DB DEFAULT (UTC)** (모듈 #9) — `list_recommendations` 가 `order_by("created_at")` 사용. UTC 저장 시 KST 자정 경계 (KST 08:59 ~ 09:00 = UTC 23:59 ~ 00:00) 에서 영업일 분류 오류 잠재. 단 `target_date` (DATE) 필터링이 우선이라 실제 운영 영향 낮음.
3. **`daily_log_reports.created_at` DB DEFAULT (UTC)** (모듈 #11) — 20:10 자정 직후 정산 → KST 표시 시 9시간 차 운영자 혼란. UI 직접 노출 (Admin/Reports 페이지) 가능성.
4. **`system_config.updated_at` UTC + UPDATE 시 stale** (모듈 #8) — 설정 변경 추적 불가능 (운영자가 "마지막 수정 언제?" 묻는 영역). 6 upsert 함수 모두.
5. **`strategy_config.updated_at` UTC + UPDATE 시 stale** (모듈 #7) — 전략 비중/파라미터 변경 추적 불가능 (사이클 23 자동 적용 이력 추적용).
6. **`kis_quote_accounts.created_at`/`updated_at` UTC** (모듈 #15, 16) — 보조 시세 계좌 등록/수정 시각. UTC 명시되어 있으나 KST 정책 위반.
7. **`market_regime_snapshots.created_at` UTC** (모듈 #14) — `_boot()` 07:50 매크로 스냅샷 시각. UTC 명시. `snapshot_date` (DATE) 가 우선 키지만 운영 회고 시 시각 혼란.
8. **`backtest_runs.created_at` / `completed_at` UTC** (모듈 #12, 13) — 백테스트 실행 시각. UTC 명시. 외부 MCP job 영역, 운영 분석 시 9h 오차.

### LOW (KST 무관 / 운영 무영향)
9. **`positions.buy_date` DATE only** (모듈 #4) — `date.isoformat()` (KST 무관). 단 호출 직전 `date.today()` 사용 시 서버 timezone 의존 → **반드시 `datetime.now(KST).date()` 호출 필수** (별도 확인 필요).
10. **`positions.update_high::updated_at`** (모듈 #5) — 미명시. update 시 자동 갱신 안 됨. high_since_buy 갱신 추적 시각이 stale (정확성 운영 무영향, 디버깅 보조용).
11. **`strategy_funnel_snapshots.snapshot_at` DB DEFAULT (UTC)** (모듈 #18) — 단계별 캡처 시각. `(target_date, ..., snapshot_at)` UNIQUE 키 일부지만 동일 영업일 내 다회 trigger 시 분 단위 식별 가능 → 실용 무영향. 단 UI 표시 시 9h 오차.
12. **`daily_performance.date` DATE only** (모듈 #6) — `target_date.isoformat()`. KST 무관. 호출자 (`_settle`) 가 KST 기준 영업일 넘기는지 확인 필요.

---

## Phase 3 — 시정 범위 옵션 매트릭스

### 옵션 A: HIGH + MEDIUM 일괄 시정 (8 모듈 / 11 함수, 대규모)
**대상**: HIGH 1 + MEDIUM 7 = stock_master / parameter_recommendations / log_reports / system_config (6) / strategy_config / kis_quote_accounts (2) / market_regime_snapshots / backtest_runs (2)

**시정 패턴** (사이클 65 H2 답습):
```python
# 각 모듈에 추가:
from datetime import datetime, timezone, timedelta
KST = timezone(timedelta(hours=9))

# 페이로드에 명시:
payload["created_at"] = datetime.now(KST).isoformat()
payload["updated_at"] = datetime.now(KST).isoformat()
# (utcnow 사용처는 KST 로 교체)
```

**AST 가드 (사이클 65 H3 패턴 확장)**:
```python
# tests/unit/db/test_all_insert_modules_kst_timestamp.py (신규)
# - src/db/*.py rglob 으로 INSERT/upsert 호출 검색
# - 각 payload dict 에 created_at / updated_at / timestamp / refreshed_at 등
#   시각 컬럼 명시 시 datetime.now(KST) / datetime.now(_KST_TZ) 패턴 필수 강제
# - datetime.now(timezone.utc) / datetime.utcnow() 사용 시 FAIL
```

**위험-비용**:
- 비용: 11 함수 × 1~2 줄 = ~15 LOC 변경 + AST 가드 1 파일 (~50 LOC) + 모듈별 KST 상수 import 추가
- 위험: **회귀 0** (INSERT 페이로드에 명시 컬럼 추가 = 호환 동작). 매매 안전성 영향 0 (DB INSERT 영역 = hot path 무관)
- 운영 영향: 신규 INSERT 부터 KST 보장. **기존 UTC 행 자연 잔존** (카드 #18 별개)

### 옵션 B: HIGH 만 시정 (1 모듈)
**대상**: `stock_master.refreshed_at` 만
**비용**: 2 LOC 변경 + AST 가드 1 파일
**위험**: 0
**한계**: MEDIUM 7 항목 silent 결함 잔존 — 사이클 69+ 후속 의무

### 옵션 C: 분류 표만 산출 + 시정 보류 (운영 검토)
**비용**: 본 보고서 산출만 (변경 0)
**위험**: 0
**한계**: 카드 #17 미해결 영속 (사이클 70+ 재발주 위험)

---

## Phase 4 — 권고

**옵션 A 강력 권고**.

근거:
1. **루트 CLAUDE.md "절대 깨지 말 것"**: "모든 시각 데이터 KST 강제 — 백엔드 `_to_kst(iso)` 헬퍼 + `_today_kst_iso()` timezone 명시 (`+09:00`)" — 명문화된 정책 위반 8 모듈 한꺼번에 정합화
2. **사이클 65 hotfix 인계 의도**: H2-bis 발견 (`_insert_log_to_db` silent 결함) = "다른 모듈에도 동일 패턴 있을 것" 강한 시그널. LOW 카드 산정은 *발견 시점* 평가 — 실제로 8 모듈 silent UTC 잔존은 LOW 카테고리 상한 초과
3. **회귀 위험 0**: INSERT 페이로드에 시각 컬럼 명시 추가 = DB DEFAULT override (호환). 매매 hot path 무관
4. **사이클 65 hotfix 패턴 답습**: KST 상수 import + 페이로드 1 줄 추가 + AST 가드 — 변경 패턴 검증 완료
5. **비용 대비 효과**: ~15 LOC + AST 가드 1 파일 → 정책 일관성 100% 회복

**보류 항목** (별개 카드):
- LOW 9~12 항목 (`positions.buy_date` / `update_high::updated_at` / `strategy_funnel_snapshots.snapshot_at` / `daily_performance.date`) = 운영 무영향, 본 사이클 범위 외. 단 호출자 timezone 의존 확인 (e.g. `date.today()` → `datetime.now(KST).date()`) 은 별개 grep 점검 후 인계
- 카드 #18 (기존 UTC 데이터 백필 변환) = 별개 사이클 + DB migration 영역

---

## Phase 5 — 사용자 결정 의뢰

### 결정 1: 시정 범위
- **A**: HIGH + MEDIUM 8 모듈 일괄 시정 (권고)
- **B**: HIGH 1 모듈만 (`stock_master.refreshed_at`)
- **C**: 시정 보류 (본 보고서만)

### 결정 2 (옵션 A 채택 시): KST 상수 통일 정책
모듈마다 별도 `KST = timezone(timedelta(hours=9))` 정의 중복. 다음 중 선택:
- **2-A**: 모듈별 상수 유지 (사이클 65 답습, 변경 최소)
- **2-B**: `src/db/_kst.py` 공용 헬퍼 신규 (`KST_TZ` + `now_kst_iso()`) — 모든 db 모듈 import. 향후 silent 결함 영구 차단 (헬퍼 미사용 = AST FAIL)

### 결정 3 (옵션 A 채택 시): AST 가드 범위
- **3-A**: `src/db/*.py` 만 (사이클 65 H3 범위 유지)
- **3-B**: `src/` 전체 rglob (`src/main.py::_insert_log_to_db` 같은 위임 경로 포함 — 사이클 65 H2-bis 패턴)

### Q1+ 자유 발의
- **Q1**: LOW 9~12 항목 (`date.today()` → `datetime.now(KST).date()` 호출자 점검) 본 사이클 포함 여부
- **Q2**: 카드 #18 (기존 UTC 데이터 KST 변환 백필 migration) 사이클 69 발주 일정 (운영 영향 분석 선행 필요)
- **Q3**: `stock_master.is_stale()` 내부도 UTC 비교 → 본 시정 후 KST 비교로 통일 여부 (현재 동작 정확하나 정책 일관성)

### domain-expert 자문 필요 여부
**불필요** — DB INSERT 영역 = 매매 안전성 영역 무관, KST 정책 일관성만 영향. 발견 결함 모두 silent 영역 (사용자/시세/주문 hot path 무관).

---

## 산출물 인계 (사용자 결정 후)

1. 옵션 A 채택 시 → tdd-engineer 발주서 `_workspace/red/cycle68_other_insert_modules_kst.md` 작성
2. backend-dev Green 후 → 변경 통계 + tester verify 결과 (카테고리 분리 측정 + flakiness 3 회)
3. sync-docs → `src/db/CLAUDE.md` (모듈별 KST 명시 의무) + `CLAUDE.md` (DB 스키마 섹션 KST 의무 명시 보강) + `HARNESS_CHANGELOG.md`
