"""사이클 M3a (Red) — src/db/kis_quote_accounts.py asyncpg 전환 계약 가드.

승인 계획: `~/.claude/plans/partitioned-kindling-lollipop.md` (단계 3 — 분석·관찰, 비 hot-path).

현행 kis_quote_accounts.py = supabase-py 체인 + `execute_with_retry`(read 4함수, 사이클 189).
이 증분 = `pg.*` 전환. **함수 계약(시그니처·반환형·graceful·캐시) 100% 보존** → 호출부 diff 0.

⚠️ 절대 보존 계약 (캐시 3중 + 평문 격리):
- read 4함수 `list_accounts`/`get_account`/`get_account_by_label`/`get_credentials_for_token_manager`
  = `pg._with_retry` 경유 (사이클 189 정책 = read 만 retry).
- `list_accounts` 60s TTL 메모리 캐시: TTL 내 hit(DB fetch 0) / TTL 만료 fresh / DB 예외+캐시 있음
  → **stale 반환** (graceful) / 캐시 없음 → 빈 리스트. INSERT/UPDATE/DELETE 직후 invalidate.
- **평문 credential 은 `get_credentials_for_token_manager` 만 노출** (app_secret 평문). 다른 함수는
  `KisQuoteAccount.from_row()` 마스킹. 로그/응답 노출 금지.
- insert → LabelConflictError (label UNIQUE) / ValueError (빈 값·kis_env 부적합).
- 쓰기(insert/update/delete) = `_with_retry` 미경유 (사이클 189 정책 = 멱등 우려).

Red 유효성: production 미변경(supabase 체인 + execute_with_retry) → pg mock 미발화 → 계약 단언 FAIL.
"""

from __future__ import annotations

import time
from datetime import datetime
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

pytestmark = pytest.mark.unit


def _row(label="quote-1", *, active=True, secret="abcdefgh1234"):
    aid = str(uuid4())
    now = datetime.fromisoformat("2026-07-16T16:00:00+09:00")
    return {
        "id": aid,
        "label": label,
        "app_key": "APPKEY-XXX",
        "app_secret": secret,
        "kis_env": "real",
        "active": active,
        "created_at": now,
        "updated_at": now,
    }


@pytest.fixture(autouse=True)
def _clear_cache_and_neutralize_supabase(monkeypatch):
    """캐시 무효화 + 현행 supabase 경로 중립화 (Red 단계 실 DNS hang 차단).

    Red 시점 production 은 아직 supabase/execute_with_retry 를 호출한다 → 실 Supabase
    로 나가 httpx ConnectError/60s timeout 유발. Green 전환 후엔 pg 만 남아 이 중립화가
    무해(존재하지 않는 심볼 patch=create=True). 목적 = 테스트가 *계약 단언* 으로 FAIL
    하게 만들어 Red 의도를 선명히 하는 것 (실 DNS 노이즈/hang 제거).
    """
    from src.db import kis_quote_accounts as kqa

    async def _fast_retry(build, *, op: str = ""):
        raise Exception("execute_with_retry 중립화 (M3a Red)")

    async def _fast_to_thread(fn, *a, **k):
        raise Exception("to_thread 중립화 (M3a Red)")

    # 현행 supabase read(execute_with_retry) + 쓰기(asyncio.to_thread) 경로를 즉시
    # 예외로 중립화 → production 이 실 Supabase(DNS) 로 나가 hang 하는 것을 차단.
    # Green 후엔 이 심볼들이 사라지므로 create=True(raising=False) 로 무해.
    monkeypatch.setattr(kqa, "supabase", None, raising=False)
    monkeypatch.setattr(kqa, "execute_with_retry", _fast_retry, raising=False)
    monkeypatch.setattr(kqa.asyncio, "to_thread", _fast_to_thread, raising=False)

    kqa.invalidate_list_cache()
    yield
    kqa.invalidate_list_cache()


# ---------------------------------------------------------------------------
# list_accounts — pg._with_retry read + from_row 마스킹 + created_at ASC
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_list_accounts_uses_pg_fetch_masked():
    """list_accounts → pg.fetch(SELECT ... ORDER BY created_at) → KisQuoteAccount(마스킹)."""
    from src.db import kis_quote_accounts as kqa

    rows = [_row("quote-1"), _row("quote-2")]
    with patch.object(kqa, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(return_value=rows)
        pg_mod._with_retry = AsyncMock(side_effect=lambda f, **k: f())
        out = await kqa.list_accounts()

    assert len(out) == 2, "list_accounts → 2건 KisQuoteAccount."
    # 평문 app_secret 노출 안 함 — 마스킹 필드만
    assert all(a.app_secret_masked.startswith("****") for a in out), (
        "app_secret 평문 노출 금지 — from_row 마스킹 필수."
    )
    assert not any(hasattr(a, "app_secret") for a in out), "평문 app_secret 필드 부재 계약."
    sql = pg_mod.fetch.await_args.args[0]
    assert "kis_quote_accounts" in sql and "ORDER BY" in sql.upper(), "created_at ASC 정렬 누락."


@pytest.mark.asyncio
async def test_list_accounts_active_only_filter():
    """active_only=True → WHERE active = true 필터."""
    from src.db import kis_quote_accounts as kqa

    with patch.object(kqa, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(return_value=[_row("q", active=True)])
        pg_mod._with_retry = AsyncMock(side_effect=lambda f, **k: f())
        await kqa.list_accounts(active_only=True)

    sql = pg_mod.fetch.await_args.args[0].lower()
    passed = pg_mod.fetch.await_args.args[1:]
    assert "active" in sql, "active_only=True → active 필터 SQL 누락."


@pytest.mark.asyncio
async def test_list_accounts_uses_with_retry():
    """read 는 retry-보유 accessor(pg.fetch) 경유 (사이클 189 정책 = read retry).

    계약: list_accounts read 는 pg.fetch 를 태운다. pg.fetch 자체가 내부에서
    pg._with_retry 를 경유하는 것은 M0 pg.py 계약(test_cycleM0_* 이 별도 보증)이므로,
    여기서는 read 함수가 retry-보유 accessor 를 *사용* 함만 단언한다 (read 함수가
    pg._with_retry 를 직접 호출하지는 않음 — 이중 retry 방지).
    """
    from src.db import kis_quote_accounts as kqa

    with patch.object(kqa, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(return_value=[])
        await kqa.list_accounts()

    assert pg_mod.fetch.await_count >= 1, (
        "list_accounts read 는 retry-보유 accessor(pg.fetch) 경유 (사이클 189 = read retry)."
    )


# ---------------------------------------------------------------------------
# 60s TTL 캐시 — hit / 만료 / invalidate (계약 절대 보존)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_list_accounts_cache_hit_skips_db(monkeypatch):
    """TTL 내 재호출 → DB fetch 0 (캐시 hit). 시계 monotonic freeze."""
    from src.db import kis_quote_accounts as kqa

    clock = {"t": 1000.0}
    monkeypatch.setattr(kqa.time, "monotonic", lambda: clock["t"], raising=False)

    with patch.object(kqa, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(return_value=[_row("q")])
        pg_mod._with_retry = AsyncMock(side_effect=lambda f, **k: f())
        await kqa.list_accounts()          # 1st — DB
        clock["t"] += 30.0                 # TTL(60s) 내
        await kqa.list_accounts()          # 2nd — 캐시 hit

    assert pg_mod.fetch.await_count == 1, "TTL 내 재호출은 캐시 hit (DB fetch 0)."


@pytest.mark.asyncio
async def test_list_accounts_cache_expires_after_ttl(monkeypatch):
    """TTL(60s) 만료 → fresh fetch (DB 2회)."""
    from src.db import kis_quote_accounts as kqa

    clock = {"t": 1000.0}
    monkeypatch.setattr(kqa.time, "monotonic", lambda: clock["t"], raising=False)

    with patch.object(kqa, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(return_value=[_row("q")])
        pg_mod._with_retry = AsyncMock(side_effect=lambda f, **k: f())
        await kqa.list_accounts()
        clock["t"] += 61.0                 # TTL 만료
        await kqa.list_accounts()

    assert pg_mod.fetch.await_count == 2, "TTL 만료 후 fresh fetch 필요."


@pytest.mark.asyncio
async def test_list_accounts_db_error_returns_stale_cache(monkeypatch):
    """⚠️ DB 예외 + 캐시 있음 → stale 반환 (graceful, 사이클 14-D 계약 절대 보존)."""
    from src.db import kis_quote_accounts as kqa

    clock = {"t": 1000.0}
    monkeypatch.setattr(kqa.time, "monotonic", lambda: clock["t"], raising=False)

    with patch.object(kqa, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(return_value=[_row("cached-quote")])
        pg_mod._with_retry = AsyncMock(side_effect=lambda f, **k: f())
        first = await kqa.list_accounts()   # 캐시 채움
        assert len(first) == 1

        clock["t"] += 61.0                  # TTL 만료 → fresh 시도
        pg_mod.fetch = AsyncMock(side_effect=Exception("connection lost"))
        pg_mod._with_retry = AsyncMock(side_effect=Exception("connection lost"))
        stale = await kqa.list_accounts()   # DB 예외 → stale 반환

    assert len(stale) == 1 and stale[0].label == "cached-quote", (
        "DB 예외 시 stale 캐시 반환 (graceful) — 빈 리스트로 무너지면 안 됨 (사이클 14-D)."
    )


@pytest.mark.asyncio
async def test_list_accounts_db_error_no_cache_returns_empty(monkeypatch):
    """DB 예외 + 캐시 없음 → 빈 리스트 (회귀 보존)."""
    from src.db import kis_quote_accounts as kqa

    monkeypatch.setattr(kqa.time, "monotonic", lambda: 1000.0, raising=False)

    with patch.object(kqa, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(side_effect=Exception("boom"))
        pg_mod._with_retry = AsyncMock(side_effect=Exception("boom"))
        out = await kqa.list_accounts()

    assert out == [], "DB 예외 + 캐시 없음 → 빈 리스트."


@pytest.mark.asyncio
async def test_insert_invalidates_list_cache(monkeypatch):
    """INSERT 직후 캐시 invalidate → 다음 list_accounts fresh fetch (운영 토글 즉시 반영).

    ⚠️ 단일 mock 의 호출 이력으로 검증: list_accounts 는 pg.fetch 를, insert_account 의
    사전 label 검사(get_account_by_label)는 pg.fetchrow 를 태운다. mid-test 로 fetch mock
    을 재할당하면 await_count 가 0 부터 다시 세어져 오판하므로, fetch/fetchrow 를 각각 단일
    mock 으로 유지하고 invalidate 경계를 넘어 fetch 카운트가 *증가* 함을 확인한다.
    """
    from src.db import kis_quote_accounts as kqa

    clock = {"t": 1000.0}
    monkeypatch.setattr(kqa.time, "monotonic", lambda: clock["t"], raising=False)

    inserted = _row("new-quote")
    with patch.object(kqa, "pg", create=True) as pg_mod:
        # fetch = list_accounts 전용 (내용 무관, 발화 횟수만 관찰). 재할당 금지.
        pg_mod.fetch = AsyncMock(return_value=[])
        # fetchrow = get_account_by_label 전용: 사전검사 miss(None) → INSERT 후 재조회(inserted)
        pg_mod.fetchrow = AsyncMock(side_effect=[None, inserted])
        pg_mod.execute = AsyncMock(return_value="INSERT 0 1")

        await kqa.list_accounts()          # 캐시 채움 (fetch 1회)
        cnt_before = pg_mod.fetch.await_count
        assert cnt_before == 1, "list_accounts 는 pg.fetch 1회로 캐시를 채운다."

        # INSERT — 사전검사(fetchrow None) + execute INSERT + invalidate + 재조회(fetchrow inserted)
        await kqa.insert_account("new-quote", "APPKEY", "SECRET1234", "real")

        # 캐시 무효화됐으므로 다음 list 는 fresh fetch (TTL 내라도)
        clock["t"] += 5.0                  # TTL 내지만 invalidate 됐어야
        await kqa.list_accounts()

    assert pg_mod.fetch.await_count > cnt_before, (
        "INSERT 직후 invalidate → TTL 내라도 다음 list 는 fresh fetch (pg.fetch 재발화)."
    )


# ---------------------------------------------------------------------------
# get_account / get_account_by_label — WHERE + None + _with_retry
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_get_account_uses_pg_where_id():
    """get_account(id) → pg.fetch/fetchrow(WHERE id = $1) → KisQuoteAccount."""
    from src.db import kis_quote_accounts as kqa

    row = _row("q")
    with patch.object(kqa, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(return_value=[row])
        pg_mod.fetchrow = AsyncMock(return_value=row)
        pg_mod._with_retry = AsyncMock(side_effect=lambda f, **k: f())
        out = await kqa.get_account(row["id"])

    assert out is not None and out.label == "q"
    sql = _first_sql(pg_mod)
    assert "kis_quote_accounts" in sql and "id" in sql, "get_account WHERE id 누락."


@pytest.mark.asyncio
async def test_get_account_missing_returns_none():
    """미존재 → None."""
    from src.db import kis_quote_accounts as kqa

    with patch.object(kqa, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(return_value=[])
        pg_mod.fetchrow = AsyncMock(return_value=None)
        pg_mod._with_retry = AsyncMock(side_effect=lambda f, **k: f())
        out = await kqa.get_account("nope")

    assert out is None, "미존재 id → None."


@pytest.mark.asyncio
async def test_get_account_by_label_uses_pg_where_label():
    """get_account_by_label → WHERE label = $1."""
    from src.db import kis_quote_accounts as kqa

    row = _row("quote-9")
    with patch.object(kqa, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(return_value=[row])
        pg_mod.fetchrow = AsyncMock(return_value=row)
        pg_mod._with_retry = AsyncMock(side_effect=lambda f, **k: f())
        out = await kqa.get_account_by_label("quote-9")

    assert out is not None and out.label == "quote-9"
    sql = _first_sql(pg_mod)
    assert "label" in sql, "get_account_by_label WHERE label 누락."


@pytest.mark.asyncio
async def test_get_account_exception_graceful_none():
    """read 예외 → None graceful (기존 try/except 계약)."""
    from src.db import kis_quote_accounts as kqa

    with patch.object(kqa, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(side_effect=Exception("boom"))
        pg_mod.fetchrow = AsyncMock(side_effect=Exception("boom"))
        pg_mod._with_retry = AsyncMock(side_effect=Exception("boom"))
        out = await kqa.get_account("x")

    assert out is None, "read 예외 → None graceful."


# ---------------------------------------------------------------------------
# get_credentials_for_token_manager — ⚠️ 평문 노출 (유일 노출 함수) + active 필터
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_get_credentials_returns_plaintext_secret():
    """⚠️ get_credentials_for_token_manager → app_secret 평문 dict 반환 (유일 노출 함수)."""
    from src.db import kis_quote_accounts as kqa

    row = _row("quote-1", secret="PLAINTEXT-SECRET-0000")
    with patch.object(kqa, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(return_value=[row])
        pg_mod.fetchrow = AsyncMock(return_value=row)
        pg_mod._with_retry = AsyncMock(side_effect=lambda f, **k: f())
        out = await kqa.get_credentials_for_token_manager("quote-1")

    assert out is not None
    assert out["app_secret"] == "PLAINTEXT-SECRET-0000", (
        "토큰 매니저 전용 함수는 app_secret 평문 반환 (마스킹 금지 — 유일 예외)."
    )
    assert out["app_key"] == "APPKEY-XXX" and out["kis_env"] == "real"
    # active 필터 정합
    sql = _first_sql(pg_mod)
    assert "label" in sql and "active" in sql.lower(), (
        "get_credentials → WHERE label AND active 필터 누락."
    )


@pytest.mark.asyncio
async def test_get_credentials_missing_returns_none():
    """미존재/비활성 → None."""
    from src.db import kis_quote_accounts as kqa

    with patch.object(kqa, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(return_value=[])
        pg_mod.fetchrow = AsyncMock(return_value=None)
        pg_mod._with_retry = AsyncMock(side_effect=lambda f, **k: f())
        out = await kqa.get_credentials_for_token_manager("nope")

    assert out is None, "미존재/비활성 → None."


@pytest.mark.asyncio
async def test_credentials_reads_use_with_retry():
    """get_credentials_for_token_manager 도 read 4함수 중 하나 → retry-보유 accessor 경유.

    계약: read 는 pg.fetch(또는 fetchrow) 를 태운다. pg.fetch 가 내부에서 pg._with_retry
    를 경유하는 것은 M0 pg.py 계약이 별도 보증 (test_cycleM0_*).
    """
    from src.db import kis_quote_accounts as kqa

    row = _row("quote-1")
    with patch.object(kqa, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(return_value=[row])
        pg_mod.fetchrow = AsyncMock(return_value=row)
        await kqa.get_credentials_for_token_manager("quote-1")

    assert (pg_mod.fetch.await_count + pg_mod.fetchrow.await_count) >= 1, (
        "get_credentials read 는 retry-보유 accessor(pg.fetch/fetchrow) 경유 (read 4함수, 사이클 189)."
    )


# ---------------------------------------------------------------------------
# insert_account — LabelConflictError / ValueError / created_at datetime
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_insert_account_empty_value_raises_valueerror():
    """빈 label/app_key/app_secret → ValueError (DB 미발화)."""
    from src.db import kis_quote_accounts as kqa

    with patch.object(kqa, "pg", create=True) as pg_mod:
        pg_mod.execute = AsyncMock(return_value="INSERT 0 1")
        pg_mod.fetch = AsyncMock(return_value=[])
        pg_mod.fetchrow = AsyncMock(return_value=None)
        pg_mod._with_retry = AsyncMock(side_effect=lambda f, **k: f())
        with pytest.raises(ValueError):
            await kqa.insert_account("", "APPKEY", "SECRET", "real")


@pytest.mark.asyncio
async def test_insert_account_invalid_env_raises_valueerror():
    """kis_env 부적합 → ValueError."""
    from src.db import kis_quote_accounts as kqa

    with patch.object(kqa, "pg", create=True) as pg_mod:
        pg_mod.execute = AsyncMock(return_value="INSERT 0 1")
        pg_mod.fetch = AsyncMock(return_value=[])
        pg_mod.fetchrow = AsyncMock(return_value=None)
        pg_mod._with_retry = AsyncMock(side_effect=lambda f, **k: f())
        with pytest.raises(ValueError):
            await kqa.insert_account("q", "APPKEY", "SECRET", "paper")


@pytest.mark.asyncio
async def test_insert_account_label_conflict_precheck_raises():
    """사전 label 검사 (get_account_by_label 존재) → LabelConflictError."""
    from src.db import kis_quote_accounts as kqa

    existing = _row("dup")
    with patch.object(kqa, "pg", create=True) as pg_mod:
        pg_mod.execute = AsyncMock(return_value="INSERT 0 1")
        pg_mod.fetch = AsyncMock(return_value=[existing])
        pg_mod.fetchrow = AsyncMock(return_value=existing)
        pg_mod._with_retry = AsyncMock(side_effect=lambda f, **k: f())
        with pytest.raises(kqa.LabelConflictError):
            await kqa.insert_account("dup", "APPKEY", "SECRET", "real")


@pytest.mark.asyncio
async def test_insert_account_db_unique_conflict_raises_label_conflict():
    """INSERT race → DB unique 위반 메시지 → LabelConflictError 변환 (사후)."""
    from src.db import kis_quote_accounts as kqa

    with patch.object(kqa, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(return_value=[])          # 사전검사 miss
        pg_mod.fetchrow = AsyncMock(return_value=None)
        pg_mod.execute = AsyncMock(
            side_effect=Exception("duplicate key value violates unique constraint")
        )
        pg_mod._with_retry = AsyncMock(side_effect=lambda f, **k: f())
        with pytest.raises(kqa.LabelConflictError):
            await kqa.insert_account("race", "APPKEY", "SECRET1234", "real")


@pytest.mark.asyncio
async def test_insert_account_created_at_datetime():
    """INSERT created_at/updated_at TIMESTAMPTZ → datetime 바인딩 (M1 패턴 2, str 금지)."""
    from src.db import kis_quote_accounts as kqa

    inserted = _row("q")
    with patch.object(kqa, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(return_value=[inserted])
        pg_mod.fetchrow = AsyncMock(side_effect=[None, inserted])  # 사전검사 miss → RETURNING
        pg_mod.execute = AsyncMock(return_value="INSERT 0 1")
        pg_mod._with_retry = AsyncMock(side_effect=lambda f, **k: f())
        await kqa.insert_account("q", "APPKEY", "SECRET1234", "real")

    args = _insert_args(pg_mod)
    assert any(isinstance(a, datetime) for a in args), (
        "created_at/updated_at 은 datetime 바인딩 (fromisoformat(now_kst_iso())) — str 금지."
    )


# ---------------------------------------------------------------------------
# 쓰기는 _with_retry 미경유 (사이클 189 정책)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_insert_does_not_use_with_retry():
    """insert_account 쓰기(INSERT)는 _with_retry 미경유 — 사전검사 read 만 경유 허용.

    최소 계약: INSERT 발화 자체(pg.execute/fetchrow RETURNING)는 _with_retry 를 태우지 않는다.
    사전 label 검사(get_account_by_label)는 read 라 _with_retry 를 태울 수 있으므로,
    여기선 INSERT 발화 mock(execute)이 _with_retry 인자로 감싸지지 않음을 SQL 로 확인.
    """
    from src.db import kis_quote_accounts as kqa

    inserted = _row("q")
    retry_calls = []

    async def _track_retry(f, **k):
        retry_calls.append(k.get("op", ""))
        return await f() if callable(f) else f

    with patch.object(kqa, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(return_value=[])
        pg_mod.fetchrow = AsyncMock(side_effect=[None, inserted])
        pg_mod.execute = AsyncMock(return_value="INSERT 0 1")
        pg_mod._with_retry = AsyncMock(side_effect=_track_retry)
        await kqa.insert_account("q", "APPKEY", "SECRET1234", "real")

    # INSERT 발화한 execute 는 _with_retry op 목록에 INSERT 관련이 없어야 함
    assert not any("insert" in (op or "").lower() for op in retry_calls), (
        "쓰기(insert)는 _with_retry 미경유 (사이클 189 정책 = 멱등 우려)."
    )


# ---------------------------------------------------------------------------
# update_account / delete_account — 부분 갱신 + invalidate
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_update_account_active_partial():
    """update_account(active=False) → UPDATE + updated_at datetime + 재조회 반환."""
    from src.db import kis_quote_accounts as kqa

    current = _row("q", active=True)
    updated = _row("q", active=False)
    updated["id"] = current["id"]
    with patch.object(kqa, "pg", create=True) as pg_mod:
        # get_account: current → (update 후) updated
        pg_mod.fetchrow = AsyncMock(side_effect=[current, updated])
        pg_mod.fetch = AsyncMock(side_effect=[[current], [updated]])
        pg_mod.execute = AsyncMock(return_value="UPDATE 1")
        pg_mod._with_retry = AsyncMock(side_effect=lambda f, **k: f())
        out = await kqa.update_account(current["id"], active=False)

    assert out is not None and out.active is False, "active 부분 갱신 반영."
    all_sql = _collect_sql(pg_mod)
    assert any("UPDATE kis_quote_accounts" in s for s in all_sql), "UPDATE SQL 누락."


@pytest.mark.asyncio
async def test_update_account_missing_returns_none():
    """미존재 id → None (변경 없음)."""
    from src.db import kis_quote_accounts as kqa

    with patch.object(kqa, "pg", create=True) as pg_mod:
        pg_mod.fetchrow = AsyncMock(return_value=None)
        pg_mod.fetch = AsyncMock(return_value=[])
        pg_mod.execute = AsyncMock(return_value="UPDATE 0")
        pg_mod._with_retry = AsyncMock(side_effect=lambda f, **k: f())
        out = await kqa.update_account("nope", active=False)

    assert out is None, "미존재 id → None."


@pytest.mark.asyncio
async def test_delete_account_existing_returns_true():
    """delete_account 존재 → DELETE + True."""
    from src.db import kis_quote_accounts as kqa

    current = _row("q")
    with patch.object(kqa, "pg", create=True) as pg_mod:
        pg_mod.fetchrow = AsyncMock(return_value=current)
        pg_mod.fetch = AsyncMock(return_value=[current])
        pg_mod.execute = AsyncMock(return_value="DELETE 1")
        pg_mod._with_retry = AsyncMock(side_effect=lambda f, **k: f())
        out = await kqa.delete_account(current["id"])

    assert out is True, "존재 → 삭제 True."
    all_sql = _collect_sql(pg_mod)
    assert any("DELETE FROM kis_quote_accounts" in s for s in all_sql), "DELETE SQL 누락."


@pytest.mark.asyncio
async def test_delete_account_missing_returns_false():
    """미존재 → False."""
    from src.db import kis_quote_accounts as kqa

    with patch.object(kqa, "pg", create=True) as pg_mod:
        pg_mod.fetchrow = AsyncMock(return_value=None)
        pg_mod.fetch = AsyncMock(return_value=[])
        pg_mod.execute = AsyncMock(return_value="DELETE 0")
        pg_mod._with_retry = AsyncMock(side_effect=lambda f, **k: f())
        out = await kqa.delete_account("nope")

    assert out is False, "미존재 → False."


# ---------------------------------------------------------------------------
# 계약 보존 불변식 — supabase / execute_with_retry 미참조 (pg 단독)
#
# ⚠️ 소스 파일 정적 검사 (런타임 hasattr 금지): autouse `_clear_cache_and_neutralize_supabase`
# fixture 가 `monkeypatch.setattr(kqa, "supabase", None)` + `execute_with_retry` 를 *생성*
# 하므로 런타임 `hasattr` 는 항상 True → 계약 검증 불가. 실제 계약("전환 후 supabase /
# execute_with_retry 를 코드에서 참조하지 않는다")은 소스 AST 로만 검증 가능 (docstring/
# 주석의 'supabase' 문자열은 파싱 무시).
# ---------------------------------------------------------------------------
def test_kis_quote_accounts_no_supabase_after_transition():
    """전환 후 supabase / execute_with_retry 심볼 잔존 금지 (pg._with_retry 로 대체).

    소스 AST 검사 — import/코드 참조 부재 + src.db.pg import 존재.
    (fixture 오염 회피 = 이 테스트는 autouse fixture 무관 = 소스 텍스트만 검사.)
    """
    from src.db import kis_quote_accounts as kqa

    _assert_no_supabase_reference_in_source(
        kqa, forbidden_names=("supabase", "execute_with_retry")
    )
    assert _source_imports_pg(kqa), "kis_quote_accounts 가 src.db.pg 를 import 해야 함."


def test_cache_symbols_preserved():
    """캐시 계약 심볼 보존 — invalidate_list_cache / _LIST_CACHE_TTL / _list_cache."""
    from src.db import kis_quote_accounts as kqa

    assert hasattr(kqa, "invalidate_list_cache"), "invalidate_list_cache 심볼 삭제 금지."
    assert hasattr(kqa, "_LIST_CACHE_TTL"), "_LIST_CACHE_TTL 삭제 금지 (60s 캐시 계약)."
    assert kqa._LIST_CACHE_TTL == 60.0, "TTL 60s 계약 보존."
    assert hasattr(kqa, "_list_cache"), "_list_cache 삭제 금지."


def test_plaintext_only_via_credentials_function():
    """평문 credential 은 get_credentials_for_token_manager 만 노출 (다른 read 는 마스킹).

    소스 텍스트 정적 검증 — app_secret 평문 dict 반환은 credentials 함수 영역에만 존재.
    """
    import inspect

    from src.db import kis_quote_accounts as kqa

    cred_src = inspect.getsource(kqa.get_credentials_for_token_manager)
    assert '"app_secret"' in cred_src or "app_secret" in cred_src, (
        "credentials 함수는 app_secret 평문 반환."
    )
    # list/get 함수는 from_row 마스킹 경유 (평문 dict 직접 반환 아님)
    list_src = inspect.getsource(kqa.list_accounts)
    assert "from_row" in list_src or "KisQuoteAccount" in list_src, (
        "list_accounts 는 from_row 마스킹 경유 (평문 노출 금지)."
    )


# ---------------------------------------------------------------------------
# 헬퍼 — 소스 AST 정적 검사 (supabase / execute_with_retry 미참조 계약)
# ---------------------------------------------------------------------------
def _source_imports_pg(mod) -> bool:
    """소스가 `import src.db.pg as pg` (또는 `from src.db import pg`) 를 하는지 AST 로 검증."""
    import ast
    import inspect

    tree = ast.parse(inspect.getsource(mod))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "src.db.pg":
                    return True
        elif isinstance(node, ast.ImportFrom):
            if node.module == "src.db" and any(a.name == "pg" for a in node.names):
                return True
    return False


def _assert_no_supabase_reference_in_source(mod, *, forbidden_names) -> None:
    """소스 AST 에 forbidden 심볼의 import / 코드 참조(Name) 가 없음을 단언.

    docstring/주석의 'supabase' 문자열은 파싱 대상이 아니므로 자연 무시된다.
    """
    import ast
    import inspect

    forbidden = set(forbidden_names)
    tree = ast.parse(inspect.getsource(mod))
    offenders: list[str] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                base = alias.name.split(".")[0]
                if base in forbidden or alias.name in forbidden:
                    offenders.append(f"import {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            mod_base = (node.module or "").split(".")[0]
            if mod_base in forbidden:
                offenders.append(f"from {node.module} import ...")
            for alias in node.names:
                if alias.name in forbidden:
                    offenders.append(f"from {node.module} import {alias.name}")
        elif isinstance(node, ast.Name) and node.id in forbidden:
            offenders.append(f"name {node.id}")

    assert not offenders, (
        f"전환 후 supabase/execute_with_retry 코드 참조 잔존 금지 (pg 단독). 발견: {offenders}"
    )


# ---------------------------------------------------------------------------
# 헬퍼 — SQL·인자 수집 (await_args_list 순회, isinstance(m, AsyncMock) 가드로 오탐 차단)
# ---------------------------------------------------------------------------
def _collect_sql(pg_mod) -> list[str]:
    sqls: list[str] = []
    for name in ("fetch", "fetchrow", "execute", "fetchval"):
        m = getattr(pg_mod, name, None)
        if not isinstance(m, AsyncMock):
            continue
        for c in m.await_args_list:
            if c.args:
                sqls.append(c.args[0])
    return sqls


def _first_sql(pg_mod) -> str:
    sqls = _collect_sql(pg_mod)
    return sqls[0] if sqls else ""


def _insert_args(pg_mod) -> tuple:
    """INSERT 를 실제 발화한 mock 의 바인딩 인자."""
    for name in ("execute", "fetchrow", "fetch"):
        m = getattr(pg_mod, name, None)
        if not isinstance(m, AsyncMock):
            continue
        for c in m.await_args_list:
            if c.args and "INSERT" in c.args[0].upper():
                return c.args[1:]
    return ()
