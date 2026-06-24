# 사이클 175 — system_logs retention PostgREST row-cap silent 결함 항구 시정 (루프 배치)

## 작업지시서 (team-leader → tdd-engineer Red → backend-dev Green → tester 검증)

### 위험 등급
**HIGH (운영 안정성 — DB 용량 드라이버)** / 매매 안전성 8영역 **무관** (system_logs 는 순수 관찰성).

### 배경 (메인 세션 진단 확정)

`src/db/system_logs.py::_purge_by_cutoff` (L217~273) 는 사이클 150 시정으로 2-step 구조:
```
SELECT("id")...lt("timestamp", cutoff).limit(MAX_PURGE_BATCH=100_000)  # id 수집
→ DELETE().in_("id", ids)                                              # 배치 삭제
```
상수 `MAX_PURGE_BATCH = 100_000` (L28) 이나 **Supabase PostgREST `db-max-rows=1000` 기본 cap 이 SELECT 를 1000행으로 silent 절단** → 1회 호출당 최대 1000행만 삭제.

`purge_old_logs()` 는 하루 1회(20:10 settlement)만 호출 → INFO 30K+/일 생성 vs 1000/일 삭제 → 640K+ 적체 → system_logs 242MB 비대.

운영 로그 증거: `[log_retention] info_deleted=1000 high_deleted=1000` 매일 정확히 1000 (= PostgREST row-cap 절단).

사이클 150 이 사이클 6 `.limit()` AttributeError 결함을 고쳤으나 **PostgREST row-cap 이라는 또 다른 silent cap** 에 걸린 것.

### 사용자 승인 시정 방식 = 루프 배치 (no-migration)

`_purge_by_cutoff` 가 SELECT-배치 + DELETE 를 **drained 까지 루프**:
1. 매 iteration: SELECT(id, limit=배치) → ids 빈 리스트면 종료 → DELETE in_(ids) → 누적 count
2. **안전 max iterations 가드** (런어웨이 차단). 도달 시 graceful 종료 + 부분삭제 누적 반환
3. 반환 = 전 iteration 누적 삭제 수

**제약 (절대)**:
- migration / RPC / PostgREST 설정 변경 **금지** — supabase-py SELECT.limit + DELETE.in_ 2-step 구조 유지 (사이클 150 답습)
- DELETE chain `.limit()` **미사용 보존** (사이클 6 AttributeError 결함 영구 차단)
- `cutoff_iso=None → RuntimeError` 방어 코드 **보존** (WHERE 누락 차단)
- `purge_old_logs()` 반환 스키마 `{info_deleted, high_deleted, elapsed_ms}` + emit `[log_retention] info_deleted=N high_deleted=M elapsed_ms=K` **보존** (이제 N/M 이 1000 cap 안 걸림)
- scheduler L867~878 graceful try/except + `[log_retention_skip]` **보존** (변경 0)

### 구현 명세 (backend-dev)

#### 배치 크기 결정
- 효과 cap 이 1000 이므로 SELECT `.limit(배치)` 의 배치 = **1000 권장** (정직 — 어차피 PostgREST 가 1000 으로 cap 하므로 100_000 으로 두면 "100_000 요청 → 1000 수신" 의 silent gap 영속). 신규 상수 `PURGE_SELECT_BATCH = 1000` 도입 또는 `MAX_PURGE_BATCH` 의미 재정의 중 backend-dev 판단.
  - **단, `MAX_PURGE_BATCH = 100_000` 상수 자체는 폐기 금지** — 기존 테스트 E 케이스 (`test_purge_applies_max_batch_cap`) 가 `== 100_000` 단언 + `src/db/CLAUDE.md` 명세. `MAX_PURGE_BATCH` 는 **1회 purge 호출의 전체 안전 cap** (= max_iterations × batch 상한) 으로 의미 재정의하거나, 별도 `PURGE_SELECT_BATCH=1000` 신규 + `MAX_PURGE_BATCH` 보존 후 max_iterations 가드로 활용. backend-dev 가 의미 전환 최소화 방향 선택.
- 권장 설계: `PURGE_SELECT_BATCH = 1000` (per-iteration SELECT limit) + `PURGE_MAX_ITERATIONS = 2000` (런어웨이 차단, 2000×1000 = 2M 행 = 충분히 큼) + `MAX_PURGE_BATCH = 100_000` 보존 (의미 = 단일 purge 호출 누적 상한 cap, 도달 시 종료 — 기존 E 케이스 PASS 보존).

#### 루프 구조 (`_purge_by_cutoff` 본체)
```
total_deleted = 0
for _ in range(PURGE_MAX_ITERATIONS):
    ids = SELECT(id)...limit(PURGE_SELECT_BATCH).execute()  # to_thread
    if not ids: break
    DELETE().in_("id", ids).execute()                       # to_thread
    total_deleted += len(ids)  (또는 count 보정, 기존 로직 답습)
    if total_deleted >= MAX_PURGE_BATCH: break              # 누적 상한 cap (안전)
    if len(ids) < PURGE_SELECT_BATCH: break                 # 마지막 페이지 (선택 최적화)
return total_deleted
```
- to_thread 위임 보존 (`asyncio.to_thread`)
- count 보정 로직 (기존 L267~273 `count <= 0 → len(ids)`) 답습

#### 기존 테스트 Fake 보강 의무 (중요)
기존 `tests/unit/db/test_system_logs_retention.py` 의 `_FakeTable.select` 은 `idx==0→info / idx==1→high` 단 2회 SELECT 가정. **루프 전환 시 같은 그룹에서 SELECT 가 여러 번 호출** → `idx` 카운터 그룹 매핑 깨짐.
- backend-dev 또는 tdd-engineer 가 `_FakeSupabase` Fake 를 **그룹 상태 유지형** 으로 보강 (SELECT 호출마다 남은 ids drain 하여 다음 SELECT 는 줄어든 결과 반환, ids 소진 시 빈 리스트).
- 기존 테스트 의미 전환 발생 시 사이클 66 K-2 패턴 (xfail strict=False + docstring 의미 전환 명시) 적용. **단 가능하면 Fake 보강으로 기존 테스트 전수 PASS 보존** (회귀 0 우선).

### TDD Red 테스트 명세 (tdd-engineer)

신규 `tests/unit/db/test_cycle175_log_retention_loop.py`:

| 케이스 | 검증 | 위험 |
|--------|------|------|
| G-175-LOOP-1 | cutoff 통과 행 N > 배치크기(1000) mock 시 **전량 삭제** (루프 ceil(N/batch) 회) — 예: 2500 행 → 3 iteration → total_deleted=2500 | **HIGH** |
| G-175-LOOP-2 | DELETE in_ 호출 횟수 = ceil(rows/batch) — 2500 행 → DELETE 3회 (SELECT 도 3~4회) | HIGH |
| G-175-CAP-1 | 안전 max iterations 도달 시 graceful 종료 + 부분삭제 누적 반환 (런어웨이 차단) — 무한 ids mock + PURGE_MAX_ITERATIONS 작게 patch → 루프 종료 + 부분 count 반환 (예외 0) | **HIGH** |
| G-175-EMPTY-1 | 빈 결과 (첫 SELECT ids 빈 리스트) → 0 반환 + DELETE 0회 | MEDIUM |
| G-175-NONE-1 | `cutoff_iso=None` → RuntimeError 보존 (방어 코드 회귀 0) | **HIGH** |
| G-175-ACCUM-1 | 누적 상한 `MAX_PURGE_BATCH` 도달 시 종료 (의미 보존) 또는 신규 상한 검증 | MEDIUM |
| G-175-AST-1 | AST 정적: `_purge_by_cutoff` 본체 = SELECT.limit + DELETE.in_ 2-step 구조 보존 + DELETE chain `.limit()` **미사용** (`delete()....limit(` 패턴 0건, 사이클 6 결함 영구 차단) + for/while 루프 존재 | **HIGH** |
| G-175-RETURN-1 | `purge_old_logs()` 반환 스키마 `{info_deleted, high_deleted, elapsed_ms}` 보존 + `[log_retention]` emit 보존 (info_deleted=2500 같은 1000 초과 값 정상 반환) | MEDIUM |

**회귀 가드**: 기존 `tests/unit/db/test_system_logs_retention.py` 8 케이스 전수 PASS (Fake 보강으로) 또는 의미 전환 명시 (사이클 66 K-2).

### mock 패턴
- respx 아닌 **supabase client mock** (기존 retention 테스트 `_FakeSupabase` 패턴 답습)
- freezegun (cutoff 시각 고정 케이스)

### tester 검증
1. 백엔드 전체 `python -m pytest -q` PASS + flakiness 0 (가능하면 3회)
2. 매매 안전성: `git diff -- src/engine/risk.py src/engine/order_engine.py src/realtime/ src/auth/ src/api/order.py` = **0 라인** (system_logs 는 관찰성, 매매 hot path 무관)
3. 사이클 175 격리 신규 케이스 전수 PASS × 3회 동일

### 문서 갱신 의무
- `CLAUDE.md` 루트 하네스 이력 표 1줄
- `docs/HARNESS_CHANGELOG.md` 신규 사이클 175 행 (verbatim 상세)
- `src/db/CLAUDE.md` retention 절 갱신 (PostgREST row-cap → 루프 배치 시정 명세 + 신규 상수)

### 커밋/푸시
**절대 금지** — 사용자 명시 승인 전. 구현·검증·문서까지만, 작업 트리 보존.

### 운영 효과 (push 후, D+1)
- 20:10 settlement `[log_retention] info_deleted=N` 에서 N 이 1000 초과 값으로 정상 표시 (적체 드레인)
- 재적체 방지 (메인 세션이 raw SQL + VACUUM FULL 로 backlog 665K → 368MB 이미 드레인)
