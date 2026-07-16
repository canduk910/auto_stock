"""사이클 M3b (Red) — system_logs 실 Postgres 왕복 검증 (관찰성 척추 + main seam).

승인 계획: `~/.claude/plans/partitioned-kindling-lollipop.md` (단계 3 — 분석·관찰 + main seam).

mock 단위로 못 잡는 **실 SQL · KST timestamp to_char(+09:00) 왕복 · purge 루프 배치 drained ·
get_logs count/페이징 정합 · ILIKE 검색 · never-raise** 안전망.
docker/DATABASE_URL_TEST 없으면 pg_harness fixture skip.

⚠️ 핵심 (관찰성 척추 3대 불변식):
1. **never-raise** (사이클190) — write_log 는 실 PG 라도 예외를 호출자에 전파하지 않는다.
2. **KST timestamp** (사이클65 H2) — write_log INSERT 후 get_logs 조회 시 timestamp `+09:00`.
3. **purge 루프 배치** (사이클175) — 1000행 초과 실 삭제 drained (PostgREST 1000 cap 무관).

Red 유효성: production(system_logs) 이 아직 pg 미사용(supabase 호출) → 실 PG 왕복 경로 없음 →
전부 FAIL/에러.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.slow]

KST = timezone(timedelta(hours=9))


@pytest.fixture(autouse=True)
def _neutralize_supabase_path(monkeypatch):
    """Red 단계 실 Supabase(DNS) 접촉 차단 — system_logs 가 전환 전까지 supabase 를 호출하면
    실 네트워크로 나가 httpx ConnectError/timeout 을 유발한다. supabase 경로를 즉시 예외로
    중립화 → 통합 테스트가 *왕복 계약* 단언으로 빠르게 FAIL(Red).

    Green 전환 후엔 system_logs 가 pg 만 쓰므로 이 심볼이 사라져 무해(raising=False).
    """
    async def _fast_to_thread(fn, *a, **k):
        raise Exception("supabase to_thread 중립화 (M3b Red integration)")

    from src.db import system_logs as _mod

    monkeypatch.setattr(_mod, "supabase", None, raising=False)
    if hasattr(_mod, "asyncio"):
        monkeypatch.setattr(_mod.asyncio, "to_thread", _fast_to_thread, raising=False)
    yield


# ===========================================================================
# write_log — INSERT + KST timestamp 왕복 (to_char +09:00)
# ===========================================================================
@pytest.mark.asyncio
async def test_write_log_and_get_logs_kst_roundtrip(clean_system_logs):
    """⚠️ write_log → get_logs 왕복 — timestamp KST(+09:00) str 반환 (사이클65 H2)."""
    from src.db import system_logs as sl

    await sl.write_log("INFO", "M3b 왕복 테스트 메시지")

    out = await sl.get_logs(limit=10)
    assert out["total"] == 1, "write_log 1건 → get_logs total 1."
    item = out["items"][0]
    assert item["log_level"] == "INFO"
    assert item["message"] == "M3b 왕복 테스트 메시지"
    # KST timestamp — str 이면 +09:00, datetime 이면 utcoffset 9h
    ts = item["timestamp"]
    if isinstance(ts, str):
        assert ts.endswith("+09:00"), f"timestamp KST +09:00 str 계약 위반: {ts}"
    else:
        assert ts.utcoffset() == timedelta(hours=9), f"timestamp KST 위반: {ts}"


@pytest.mark.asyncio
async def test_write_log_never_raises_real_pg(clean_system_logs):
    """⚠️ 사이클190 — pg.execute 가 실 예외 raise 해도 write_log 는 미전파 (실 경로).

    ⚠️ 모듈 전역 `pg.execute` 를 직접 교체하면 fixture teardown 의 DELETE 까지 오염되므로
    try/finally 로 즉시 원복 (teardown 안전).
    """
    from src.db import system_logs as sl
    import src.db.pg as pg

    async def _boom(*a, **k):
        raise Exception("simulated connection lost")

    orig = getattr(pg, "execute", None)
    pg.execute = _boom
    try:
        # 예외 전파되면 실패
        result = await sl.write_log("ERROR", "never-raise 실 경로")
    finally:
        if orig is not None:
            pg.execute = orig
    assert result is None, "write_log never-raise (실 PG 예외 삼킴)."


# ===========================================================================
# get_logs — count 정확 + 페이징 + KST 기간 필터
# ===========================================================================
@pytest.mark.asyncio
async def test_get_logs_count_and_paging(clean_system_logs):
    """get_logs count 정확 (PostgREST 1000 cap 무관) + LIMIT/OFFSET 페이징."""
    from src.db import system_logs as sl

    for i in range(25):
        await sl.write_log("INFO", f"페이징 로그 {i:02d}")

    page1 = await sl.get_logs(limit=10, page=1, size=10)
    assert page1["total"] == 25, "정확 count 25 (별도 SELECT count(*))."
    assert page1["total_pages"] == 3, "ceil(25/10)=3."
    assert len(page1["items"]) == 10, "page1 = 10건."

    page3 = await sl.get_logs(limit=10, page=3, size=10)
    assert len(page3["items"]) == 5, "page3 = 잔여 5건 (OFFSET 정합)."


@pytest.mark.asyncio
async def test_get_logs_level_filter(clean_system_logs):
    """get_logs → log_level 필터 (count 도 필터 반영)."""
    from src.db import system_logs as sl

    await sl.write_log("INFO", "정보 로그")
    await sl.write_log("ERROR", "에러 로그 A")
    await sl.write_log("ERROR", "에러 로그 B")

    out = await sl.get_logs(log_level="ERROR")
    assert out["total"] == 2, "ERROR 만 2건 (count 필터 반영)."
    assert all(i["log_level"] == "ERROR" for i in out["items"])


@pytest.mark.asyncio
async def test_get_logs_date_range_kst_boundary(clean_system_logs):
    """⚠️ get_logs from_date/to_date KST +09:00 경계 — 오늘 KST 로그 포함."""
    from src.db import system_logs as sl

    await sl.write_log("INFO", "오늘 KST 로그")

    today = datetime.now(KST).date()
    out = await sl.get_logs(from_date=today, to_date=today)
    assert out["total"] >= 1, (
        "오늘 KST 범위 필터에 방금 INSERT 한 로그 포함 의무 (KST 00:00~09:00 누락 방지)."
    )


# ===========================================================================
# search_logs — ILIKE 실 검색 + clamp + has_more
# ===========================================================================
@pytest.mark.asyncio
async def test_search_logs_ilike_real(clean_system_logs):
    """search_logs → ILIKE substring 실 매칭 (대소문자 무시)."""
    from src.db import system_logs as sl

    await sl.write_log("INFO", "[매수] 삼성전자 신호 감지")
    await sl.write_log("INFO", "[매도] SK하이닉스 청산")
    await sl.write_log("WARNING", "[매수] 잔고 부족")

    out = await sl.search_logs("매수")
    assert out["total"] == 2, "매수 substring 2건."
    assert all("매수" in r["message"] for r in out["logs"])


@pytest.mark.asyncio
async def test_search_logs_empty_q_raises(clean_system_logs):
    """빈 q → ValueError (실 경로도 라우트 이중 안전망 계약)."""
    from src.db import system_logs as sl

    with pytest.raises(ValueError):
        await sl.search_logs("  ")


# ===========================================================================
# purge — ⚠️ 사이클175 루프 배치 drained (1000행 초과 실 삭제) + retention 경계
# ===========================================================================
@pytest.mark.asyncio
async def test_purge_loop_drains_above_1000(clean_system_logs, pg_pool):
    """⚠️ 사이클175 — INFO 1500행(> PURGE_SELECT_BATCH 1000) 을 실 PG 에서 전량 삭제 (drained).

    PostgREST 1000 cap 이 asyncpg 에는 없으므로 1500 전량 삭제 확인 (silent 절단 소멸 실증).
    """
    from src.db import system_logs as sl

    # 과거(3일 전) INFO 1500행 직접 삽입 — retention(INFO 2일) 대상
    old_ts = datetime.now(KST) - timedelta(days=3)
    rows = [("INFO", f"old info {i}", old_ts) for i in range(1500)]
    await pg_pool.executemany(
        "INSERT INTO system_logs (log_level, message, timestamp) VALUES ($1, $2, $3)",
        rows,
    )
    # 최근 INFO 1행 (retention 보존 대상)
    await sl.write_log("INFO", "최근 로그 (보존)")

    result = await sl.purge_old_logs()
    assert result["info_deleted"] == 1500, (
        f"1000 초과 전량 삭제 (drained 루프) — cap 잔존 시 1000: {result}"
    )

    # 최근 로그(보존 대상) + purge_old_logs 자체가 emit 하는 [log_retention] 1행 = 2행 잔존.
    # (purge_old_logs 는 삭제 통계를 write_log 로 영구 기록 — 사이클6 계약,
    # test_purge_old_logs_emits_retention_log 가 그 emit 존재를 별도 검증)
    remaining = await pg_pool.fetchval("SELECT count(*) FROM system_logs")
    assert remaining == 2, f"보존 로그 1행 + [log_retention] emit 1행 = 2행 잔존해야 함: {remaining}"


@pytest.mark.asyncio
async def test_purge_retention_boundary_info_2days_high_30days(clean_system_logs, pg_pool):
    """⚠️ retention 경계 — INFO 2일 / HIGH 30일 (경계 안쪽 보존, 바깥 삭제)."""
    from src.db import system_logs as sl

    now = datetime.now(KST)
    rows = [
        # INFO 3일 전 → 삭제 (2일 초과)
        ("INFO", "info old", now - timedelta(days=3)),
        # INFO 1일 전 → 보존
        ("INFO", "info fresh", now - timedelta(days=1)),
        # ERROR 40일 전 → 삭제 (30일 초과)
        ("ERROR", "error old", now - timedelta(days=40)),
        # ERROR 20일 전 → 보존
        ("ERROR", "error fresh", now - timedelta(days=20)),
    ]
    await pg_pool.executemany(
        "INSERT INTO system_logs (log_level, message, timestamp) VALUES ($1, $2, $3)",
        rows,
    )

    result = await sl.purge_old_logs()
    assert result["info_deleted"] == 1, f"INFO 2일 초과 1건 삭제: {result}"
    assert result["high_deleted"] == 1, f"HIGH 30일 초과 1건 삭제: {result}"

    # 보존 확인 (info fresh + error fresh + [log_retention] emit 1행)
    fresh_msgs = await pg_pool.fetch(
        "SELECT message FROM system_logs WHERE message IN ('info fresh', 'error fresh')"
    )
    assert len(fresh_msgs) == 2, "retention 경계 안쪽 로그 보존 의무."


@pytest.mark.asyncio
async def test_purge_cutoff_none_raises_real(clean_system_logs):
    """⚠️ 사이클175 절대 보존 — cutoff_iso=None → RuntimeError (실 경로도 WHERE 누락 차단)."""
    from src.db import system_logs as sl

    with pytest.raises(RuntimeError, match="cutoff"):
        await sl._purge_by_cutoff(cutoff_iso=None, level_filter="INFO")


@pytest.mark.asyncio
async def test_purge_old_logs_emits_retention_log(clean_system_logs, pg_pool):
    """purge_old_logs → [log_retention] INFO 1행 emit (실 write_log 경로)."""
    from src.db import system_logs as sl

    await sl.purge_old_logs()

    emitted = await pg_pool.fetch(
        "SELECT message FROM system_logs WHERE message LIKE '[log_retention]%'"
    )
    assert emitted, "[log_retention] emit 로그 실 INSERT 의무."


# ===========================================================================
# system_config.get_auto_start — seam ② 실 PG 왕복
# ===========================================================================
@pytest.mark.asyncio
async def test_get_auto_start_real_pg_roundtrip(clean_system_config, pg_pool):
    """⚠️ seam ② — get_auto_start 실 PG 왕복 (JSONB {"value": true} codec)."""
    from src.db import system_config as sc

    # 키 부재 → False
    assert await sc.get_auto_start() is False, "키 부재 → False."

    # value=True 저장 후 → True
    # ⚠️ jsonb 파라미터는 Python dict 로 바인딩 (asyncpg custom codec 이 인코더를 통해
    # json.dumps 를 전담 — `_init_conn` docstring 계약). 문자열 리터럴을 `$2::jsonb` 로
    # 캐스트해도 codec 이 그 문자열 자체를 재차 json.dumps 하여 이중 인코딩(문자열의
    # 문자열)이 되므로 사용 금지 — `tests/integration/test_cycleM2b_universe_daily_roundtrip.py`
    # 의 `_insert_master` dict 바인딩 패턴과 동일하게 정정.
    await pg_pool.execute(
        "INSERT INTO system_config (key, value) VALUES ($1, $2::jsonb) "
        "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value",
        "auto_start", {"value": True},
    )
    assert await sc.get_auto_start() is True, "value True → auto_start True (JSONB codec)."
