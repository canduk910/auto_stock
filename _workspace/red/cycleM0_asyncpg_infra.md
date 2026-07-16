# 사이클 M0 (Red) — Supabase→RDS 이전 단계 M0: asyncpg 인프라

승인 계획: `~/.claude/plans/partitioned-kindling-lollipop.md` (단계 0 인프라).

## 목표 (이 단계 = 행위 변화 0)
`src/db/pg.py` 신규 (asyncpg 풀 + 헬퍼) + `config.database_url` + `.env.example` + `main.py` lifespan
init/close_pool 배선 + `requirements.txt` asyncpg. **아직 어느 db 모듈도 pg 미사용** = supabase.py
병존, 순수 추가. 매매 안전성 8영역 diff 0 + 어느 db 모듈도(supabase.py 포함) 미변경.

## 미러 대상 (정본)
- `src/db/supabase.py` — `execute_with_retry(build, *, retries=1, op="")` (사이클187, httpx 예외군
  캐치, read 전용, 0.2s backoff, write_log 미호출). pg 의 `_with_retry` 가 asyncpg 예외군으로 대체.
- `src/config.py` L36-37 `supabase_url`/`supabase_key` (병존, 삭제 금지).
- `src/main.py` lifespan (L187 부근).
- `src/db/_kst.py` (`now_kst_iso`).

## Red 대상 (production 미존재 → import/함수 부재로 FAIL)

### `src/db/pg.py` (신규)
- `init_pool()` / `close_pool()` — `asyncpg.create_pool(dsn=settings.database_url,
  min_size=2, max_size=10, max_inactive_connection_lifetime=300.0, command_timeout=30.0,
  init=_init_conn)`. 전역 `_pool`.
- **`_init_conn(conn)` — 3설정 (최우선)**:
  1. JSONB + JSON codec 2회 `set_type_codec(..., encoder=json.dumps, decoder=json.loads,
     schema="pg_catalog")`. ⚠️ 미등록 시 asyncpg JSONB→str → system_config dict 기대 silent 폴백.
  2. `SET TIME ZONE 'Asia/Seoul'`.
- 헬퍼: `fetch→list[dict]`(dict(record) 변환) / `fetchrow→dict|None` / `fetchval→스칼라` /
  `execute→str` / `executemany→None`.
- `_with_retry(coro_factory, *, op="")` — asyncpg 연결 예외군 재시도, **read 전용**(쓰기 미경유
  AST), write_log 미호출(logger.warning 단독), 0.2s backoff, 소진 시 raise.

## 회귀 가드 파일
1. `tests/unit/db/test_cycleM0_pg_helpers.py` — 헬퍼 반환형 계약 + init_pool create_pool 인자
   + _with_retry asyncpg 예외 재시도/write_log 미호출.
2. `tests/unit/db/test_cycleM0_init_conn_codec.py` — `_init_conn` JSONB+JSON codec 2회 등록
   + SET TIME ZONE (mock conn).
3. `tests/unit/ast/test_cycleM0_ast_pg_retry.py` — read 헬퍼만 `_with_retry` 경유 + 쓰기 미경유
   + `_with_retry` write_log 호출 0.
4. `tests/unit/db/test_cycleM0_config_and_safety.py` — config.database_url 존재 + 매매 안전성
   8영역 diff 0 + 어느 db 모듈도 미변경(git).

## Red 유효성 (예상 FAIL)
- pg.py 미존재 → 1/2/3 import 또는 함수 부재 FAIL.
- config.database_url 미존재 → 4 FAIL.
- 안전성/미변경 가드는 현재도 PASS(불변식) — Green 후에도 보존.

## 매매 안전성
pg.py 는 아직 어느 모듈도 사용 안 함 → 행위 변화 0. 8영역(risk/order_engine/realtime/auth/
api.order/session/scanner/strategy_registry) diff 0.
