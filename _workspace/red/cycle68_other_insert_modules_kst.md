# 사이클 68 Red 명세 — 기타 INSERT 모듈 UTC → KST 일관성 (카드 #17)

**발주**: team-leader Phase 1~4 + 사용자 결정 (결정 1=A / 결정 2=2-B / 결정 3=3-B + Q1/Q2/Q3 모두 채택)
**책임**: tdd-engineer Red → backend-dev Green → tester Verify
**선행 사이클**: 65 hotfix H2 (`system_logs.py:44`) + H2-bis (`main.py:126`) + H3 (AST 영구 가드 2 케이스)
**원칙**: Red 만 작성 (Green 코드 작성 금지)

---

## 시정 범위 (옵션 A — HIGH 1 + MEDIUM 7 일괄)

| # | 모듈 | 함수 | 위험 | 현재 상태 |
|---|------|------|-----|----------|
| 1 | `src/db/stock_master.py` | `_to_row` (`refreshed_at`) | **HIGH** | `datetime.now(timezone.utc)` ← 시정 대상 |
| 2 | `src/db/parameter_recommendations.py` | `insert_recommendation` (`created_at`) | MEDIUM | 미명시 → DB DEFAULT UTC ← 시정 대상 |
| 3 | `src/db/log_reports.py` | `insert_log_report` (`created_at`) | MEDIUM | 미명시 → DB DEFAULT UTC ← 시정 대상 |
| 4 | `src/db/system_config.py` | 6 upsert (`updated_at`) | MEDIUM | 미명시 ← 시정 대상 |
| 5 | `src/db/strategy_config.py` | `save` (`updated_at`) | MEDIUM | 미명시 ← 시정 대상 |
| 6 | `src/db/kis_quote_accounts.py` | `insert_account` + `update_account` (`created_at`/`updated_at`) | MEDIUM | `datetime.now(timezone.utc)` ← 시정 대상 |
| 7 | `src/db/market_regime_snapshots.py` | `insert_snapshot` (`created_at`) | MEDIUM | `_now_iso()` UTC ← 시정 대상 |
| 8 | `src/db/backtest_runs.py` | `insert_run` + `update_status` (`created_at`/`completed_at`) | MEDIUM | `_now_iso()` UTC ← 시정 대상 |

---

## Red 테스트 매트릭스 (12+ 케이스)

### G-1 — `src/db/_kst.py` 공용 헬퍼 모듈 (결정 2-B)

파일: `tests/unit/db/test_cycle68_kst_helper_module_g1.py`

| 케이스 | 검증 |
|-------|------|
| G-1a | `from src.db._kst import now_kst_iso, KST` import 성공 |
| G-1b | `now_kst_iso()` 호출 결과가 `+09:00` suffix 포함 ISO 문자열 |
| G-1c | `KST` 가 `timezone(timedelta(hours=9))` 또는 `ZoneInfo("Asia/Seoul")` 동등 객체 |

### G-2~G-9 — 모듈별 KST timestamp 명시 검증 (단위 mock 캡처)

파일: `tests/unit/db/test_cycle68_kst_timestamp_per_module_g2_g9.py`

| 케이스 | 모듈 | 함수 | 검증 |
|-------|------|------|------|
| G-2 | stock_master | `upsert_one` | INSERT/UPSERT payload `refreshed_at` 값이 KST `+09:00` suffix |
| G-3 | parameter_recommendations | `insert_recommendation` | INSERT payload 에 `created_at` 키 명시 + KST 값 |
| G-4 | log_reports | `insert_log_report` | INSERT payload 에 `created_at` 키 명시 + KST 값 |
| G-5 | system_config | `set_cash_usage_ratio` | UPSERT payload 에 `updated_at` 키 명시 + KST 값 |
| G-6 | strategy_config | `save` | UPSERT payload 에 `updated_at` 키 명시 + KST 값 |
| G-7 | kis_quote_accounts | `insert_account` | INSERT payload `created_at`/`updated_at` 값 KST |
| G-8 | market_regime_snapshots | `insert_snapshot` | INSERT payload `created_at` 값 KST |
| G-9 | backtest_runs | `insert_run` | INSERT payload `created_at` 값 KST |

### G-10 — AST 정적 가드 (결정 3-B, `src/` 전체 rglob)

파일: `tests/unit/db/test_cycle68_kst_global_ast_guard_g10.py`

| 케이스 | 검증 |
|-------|------|
| G-10a | `src/` 전체 `*.py` 에서 `datetime.utcnow()` 호출 0건 (deprecated naive) |
| G-10b | `src/db/*.py` INSERT/UPSERT payload 영역 내 `datetime.now(timezone.utc)` 호출 0건 (= 코드 시정 의무) |

### G-11 — `stock_master.is_stale()` KST 비교 통일 (Q3)

파일: `tests/unit/db/test_cycle68_stock_master_is_stale_kst_g11.py`

| 케이스 | 검증 |
|-------|------|
| G-11 | `is_stale()` 내부 비교 시 `datetime.now(KST)` 사용 (현재 `datetime.now(timezone.utc)`) — AST 검증 |

### G-12 — LOW DATE only 호출자 KST 점검 (Q1)

파일: `tests/unit/db/test_cycle68_date_today_kst_g12.py`

| 케이스 | 검증 |
|-------|------|
| G-12 | `src/` 전체 `*.py` 에서 `date.today()` 호출 0건 (서버 timezone 의존 → `datetime.now(KST).date()` 또는 `_today_kst()` 헬퍼 사용 의무). 단, 본 사이클은 신규 헬퍼 도입 없이 *발견 + 영구 가드* 만 수행 (시정은 backend-dev) |

---

## Red 검증 의무 (현재 Green 전 상태)

| 케이스 | 예상 결과 (현재) |
|-------|----------------|
| G-1a~c | **FAIL** (`src/db/_kst.py` 미존재) |
| G-2 | **FAIL** (`datetime.now(timezone.utc).isoformat()` 잔존) |
| G-3 | **FAIL** (`created_at` 키 미명시) |
| G-4 | **FAIL** (`created_at` 키 미명시) |
| G-5 | **FAIL** (`updated_at` 키 미명시 in `system_config` upsert payload) |
| G-6 | **FAIL** (`updated_at` 키 미명시 in `strategy_config` upsert) |
| G-7 | **FAIL** (`datetime.now(timezone.utc).isoformat()` 잔존) |
| G-8 | **FAIL** (`_now_iso()` UTC) |
| G-9 | **FAIL** (`_now_iso()` UTC) |
| G-10a | **PASS 가능** (현재 `datetime.utcnow()` 사용 0건 — 검증만) |
| G-10b | **FAIL** (`datetime.now(timezone.utc)` 6+건 잔존 — 시정 의무 가시화) |
| G-11 | **FAIL** (`datetime.now(timezone.utc)` 사용) |
| G-12 | **FAIL** (`date.today()` 12+건 잔존 — 시정 의무 가시화) |

총 **12+ 케이스 중 12 FAIL** 예상 (G-10a 1 케이스만 현재 PASS 가능).

---

## 산출물

- `tests/unit/db/test_cycle68_kst_helper_module_g1.py`
- `tests/unit/db/test_cycle68_kst_timestamp_per_module_g2_g9.py`
- `tests/unit/db/test_cycle68_kst_global_ast_guard_g10.py`
- `tests/unit/db/test_cycle68_stock_master_is_stale_kst_g11.py`
- `tests/unit/db/test_cycle68_date_today_kst_g12.py`
- `_workspace/red/cycle68_other_insert_modules_kst.md` (본 문서)

---

## 안전 규칙 (CLAUDE.md "절대 깨지 말 것" 영속)

- **Green 코드 작성 금지** — `src/db/_kst.py` 미작성 + 8 모듈 변경 0 (backend-dev 단계)
- **KST 강제** + **매도 안전성** + **WebSocket 4중 안전망** 영향 0 (DB INSERT = hot path 무관)
- **사이클 65 hotfix H2/H2-bis 영속**: `system_logs.py:44` + `main.py:126` 변경 0 의무 (이미 KST 정상)
