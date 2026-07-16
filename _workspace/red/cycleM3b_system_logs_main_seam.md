# Red 메모 — 사이클 M3b (Supabase→RDS 이전, 마지막 db 모듈 + main seam)

승인 계획: `~/.claude/plans/partitioned-kindling-lollipop.md` (단계 3 — 분석·관찰 + main seam)
브랜치: `db-migration-rds` (M0·M1·M2·M3a Green 완료)

**이게 마지막 db 모듈.** 이후 `supabase.py` 는 병존(롤백용) 유지 — 삭제 금지 (라이브 vts 검증 며칠 후 별도 사이클).

⚠️ **로깅 척추 — 극도 주의**. system_logs 는 관찰성 척추이자 매매 프로세스 안전망.
**3대 불변식 절대 보존**: dedupe(500ms) / KST(+09:00) / never-raise.

---

## 이 증분 = 2 영역

### ① `src/db/system_logs.py` (361L) — supabase 체인 → `pg.*`
### ② `src/main.py` seam 2곳 (호출부 diff 0 유일 예외)
- `_DbLogHandler` (동기 handler → async INSERT): ThreadPoolExecutor 폐기 → 큐 producer + async consumer
- lifespan auto_start 인라인 supabase 조회 → `system_config.get_auto_start()` 헬퍼 추출

---

## 작성한 Red 테스트 (4 파일 + 하네스 2)

| 파일 | 케이스 | 성격 |
|---|---|---|
| `tests/unit/db/test_cycleM3b_system_logs_pg.py` | 33 | system_logs pg 전환 단위 계약 (mock `pg.*`) |
| `tests/unit/main/test_cycleM3b_main_seam_pg.py` | 18 | `_DbLogHandler` 큐 + consumer + `get_auto_start` + lifespan seam |
| `tests/unit/db/test_cycleM3b_safety_diff0.py` | 7 | 8영역 diff 0 + main seam-only + supabase 병존 |
| `tests/integration/test_cycleM3b_system_logs_roundtrip.py` | 13 | 실 PG 왕복 (KST/purge drained/count/ILIKE/never-raise/get_auto_start) |
| `tests/integration/pg_harness.py` | +`clean_system_logs` fixture | 격리 |
| `tests/integration/conftest.py` | +re-export | 격리 |

---

## Red 확인 결과 (production 미변경)

### 단위 (mock pg)
```
tests/unit/db/test_cycleM3b_system_logs_pg.py      20 failed, 13 passed
tests/unit/main/test_cycleM3b_main_seam_pg.py      16 failed,  2 passed
tests/unit/db/test_cycleM3b_safety_diff0.py         0 failed,  7 passed  (전부 불변식)
합계                                                36 failed, 22 passed
```

### 통합 (실 postgres:15, docker 가용)
```
tests/integration/test_cycleM3b_system_logs_roundtrip.py   9 failed, 3 passed
```

**FAIL = pg 계약 단언** (production 이 아직 supabase → `pg.*` mock 미발화 / `to_thread 중립화` /
`get_auto_start` AttributeError). Green 전환 후 PASS 로 뒤집힘.

**PASS = 보존 불변식** (Green 통과 후에도 유지 의무):
- write_log never-raise (사이클190) + 실패 시 debug 단독·WARNING 미발화 (재귀 차단)
- safe_write_log graceful (사이클56-E)
- 빈 q → ValueError / cutoff_iso=None → RuntimeError (사이클175)
- retention/purge 상수 (INFO 2·HIGH 30·MAX 100_000·SELECT_BATCH 1000·MAX_ITER 2000)
- write_log/get_logs/search_logs/safe_write_log 시그니처
- `_DEDUPE_TTL_SECS=0.5` + `_dedupe_cache`
- 매매 안전성 8영역 diff 0 + main seam-only + supabase.py 병존

**git status 확인**: 8영역 파일 변경 0 (production 미변경 = Red 전제 성립).

---

## Green 계약 (backend-dev 인계)

### ① system_logs.py
- `write_log` → `pg.execute("INSERT INTO system_logs (log_level, message, timestamp) VALUES ($1,$2,$3)")`.
  - ⚠️ **never-raise 보존**: INSERT try/except Exception → `logger.debug("[write_log_failed]")` 단독 (WARNING 이상 금지). 72곳 호출처 시그니처 불변.
  - ⚠️ **KST 보존**: timestamp = `datetime.fromisoformat(now_kst_iso())` (asyncpg TIMESTAMPTZ = datetime, str 금지, utcoffset 9h).
- `get_logs` → `pg.fetch`(items, ORDER BY timestamp DESC + LIMIT/OFFSET) + `pg.fetchval`(count="exact"→`SELECT count(*)`). log_level 필터 + from/to_date KST `+09:00` 경계. **count 쿼리도 동일 필터 반영**(total 정합).
- `search_logs` → `message ILIKE $1` (`%q%`) + level ALL/None 무필터 + start/end gte/lte + limit 1~1000 clamp + 빈 q ValueError. `{logs,total,has_more}`.
- `_purge_by_cutoff` → **루프 배치** (사이클175 보존): `pg.fetch("SELECT id ... WHERE timestamp<$1 [AND log_level = $2 | = ANY($2)] LIMIT PURGE_SELECT_BATCH")` + `pg.execute("DELETE FROM system_logs WHERE id = ANY($1::bigint[])")` drained 까지 루프 + 안전 cap 3중. **cutoff_iso=None → RuntimeError 절대 보존**.
- `purge_old_logs` → `{info_deleted, high_deleted, elapsed_ms}` + `[log_retention]` emit. 1000 초과 값 정상.
- supabase import/참조 0 (pg 단독) + `import src.db.pg as pg`.
- ⚠️ 읽기 재시도(사이클189)는 M2a 정책 계승 = `pg.fetch/fetchval` 자체가 `_with_retry` 내포 → 별도 조치 불요. 쓰기(execute)는 retry 미경유.

### ② main.py
- `_DbLogHandler.emit` → 큐 producer: `record.name.startswith("src.")` 필터 → dedupe(500ms monotonic) → `_LOG_QUEUE.put_nowait((level, message))`. **never-raise**(QueueFull/예외 삼킴, WARNING 이상 미발화). `_LOG_DB_EXECUTOR` (ThreadPoolExecutor) 폐기.
- async consumer 코루틴 (`_log_queue_consumer` 등) — lifespan 에서 `asyncio.create_task` 로 기동 (`init_pool` 이후) + 종료 시 정리. 큐 drain → `_insert_log_to_db(level, message)` (async, pg.execute INSERT, KST timestamp, never-raise).
  - 권고: `_insert_log_to_db` 를 `async def` 로 전환해 consumer/write_log 와 KST·never-raise 계약 일원화. (consumer 가 INSERT 를 인라인 처리하면 해당 케이스 설계 조정 필요 — 테스트 skip 대신 assert 로 강제했으므로 헬퍼 유지 권장.)
- `system_config.get_auto_start() -> bool` 신규 (M2a pg 기반): `auto_start` 키 value → `raw is True or raw == "true"`, 부재/예외 → False graceful.
- lifespan auto_start 블록 → `auto_start = await get_auto_start()` (try/except .env 폴백 유지) — `supabase.table("system_config")` 인라인 제거.
- **seam 2곳 외 lifespan 로직 불변**: init_pool/close_pool/token_manager/`_load_strategy_config`/run_daily.

---

## Green 시 의미 전환 (xfail 은퇴) — supabase→pg 패턴 전환

아래 기존 테스트는 supabase 체인/AST 기반이라 Green 후 자연 실패 → **xfail 마커로 은퇴**.
단 dedupe/KST/never-raise **실질 계약은 본 M3b 신규 테스트로 대체 단언**(회귀 가드 유지).

| 기존 테스트 | 은퇴 사유 | 대체 |
|---|---|---|
| `tests/unit/main/test_cycle72_db_log_dedupe.py` (3) | `_LOG_DB_EXECUTOR.submit` mock | M3b main_seam `test_emit_dedupe_*` (큐 producer dedupe) |
| `tests/unit/main/test_cycle72_db_log_dedupe_structure_ast.py` | `_DEDUPE_TTL_SECS`/`time.monotonic` AST — **부분 보존 가능**(상수 유지) | 상수 케이스 유지 / executor AST 은퇴 |
| `tests/unit/main/test_cycle72_insert_log_kst_persistence_ast.py` (2) | `_insert_log_to_db` supabase INSERT AST | M3b main_seam `test_insert_log_helper_uses_pg_execute_kst` |
| `tests/unit/db/test_cycle190_write_log_never_raise.py` (5+parametrize) | supabase chain mock (`mock.table...insert...execute`) | M3b system_logs `test_write_log_never_raises_*` (pg.execute) |
| `tests/unit/db/test_cycle175_log_retention_loop.py` (전체) | supabase chain fake + `.select().delete().in_().limit()` AST | M3b system_logs `test_purge_*` (pg.fetch SELECT + pg.execute DELETE ANY) |
| `tests/unit/db/test_system_logs_kst_timestamp.py` (2) | `supabase.table("system_logs").insert(...)` AST scan (call_count>=2) | M3b `test_write_log_timestamp_is_kst_datetime` + main_seam `test_insert_log_helper_uses_pg_execute_kst` |

> ⚠️ Green 담당은 위 6 파일을 무조건 삭제하지 말 것 — **KST/never-raise/purge/dedupe 실질 계약이
> M3b 신규 테스트로 이관됐는지 대조 후** xfail 마커(사이클66 K-2 패턴)로 은퇴. `test_cycle72_db_log_dedupe_structure_ast.py` 의 `_DEDUPE_TTL_SECS==0.5` 상수 단언은 보존 가능(살아남는 부분).

---

## 검증 명령

```bash
# 단위 (mock pg) — Green 후 전량 PASS 목표
python -m pytest tests/unit/db/test_cycleM3b_system_logs_pg.py tests/unit/main/test_cycleM3b_main_seam_pg.py tests/unit/db/test_cycleM3b_safety_diff0.py -q

# 통합 (실 postgres:15)
python -m pytest tests/integration/test_cycleM3b_system_logs_roundtrip.py -q

# 보존 불변식 (Green 후에도 유지 의무)
python -m pytest tests/unit/db/test_cycleM3b_safety_diff0.py -q

# 8영역 diff 0 직접 확인
git diff --stat -- src/engine/risk.py src/engine/order_engine.py src/realtime/ src/auth/ src/api/order.py src/engine/session.py src/engine/scanner.py src/engine/strategy_registry.py
```
