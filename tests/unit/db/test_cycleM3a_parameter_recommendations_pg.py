"""사이클 M3a (Red) — src/db/parameter_recommendations.py asyncpg 전환 계약 가드.

승인 계획: `~/.claude/plans/partitioned-kindling-lollipop.md` (단계 3 — 분석·관찰, 비 hot-path).

현행 parameter_recommendations.py = supabase-py 체인 + `asyncio.to_thread`. 이 증분 = `pg.*` 전환.
**함수 계약(시그니처·반환형·graceful 폴백) 100% 보존** → 호출부(recommendation_engine 등) diff 0.

핵심 계약 (18 호출):
- insert_recommendation → INSERT ... RETURNING. JSONB(current/recommended_params/metrics) 바인딩 +
  recommended_weight/applied_weight NUMERIC nullable + created_at TIMESTAMPTZ = datetime(M1 패턴 2).
  (target_date, strategy_id) UNIQUE 충돌 → None (duplicate/unique/23505 메시지 분기 보존).
- list_recommendations(days=30) → SELECT ... WHERE target_date >= $1 ORDER BY created_at DESC → list[dict].
- get_recommendation(id) → SELECT ... WHERE id = $1 → dict | None.
- update_recommendation_status(id, status, ...) → UPDATE. applied/partial/applied_auto 시 applied_at 자동,
  rejected 시 rejected_at 자동. dict 반환 (RETURNING). applied_params/applied_weight 조건부 SET.
- update_backtest_summary(id, summary) → UPDATE backtest_summary JSONB. 미존재/예외 → {} graceful.
- list_recommendations_pending_backtest(target_date) → backtest_summary IS NULL.
- list_pending_by_date(target_date) → status='pending'.
- expire_pending_before(target_date) → UPDATE status='expired' WHERE pending AND target_date < $ → int(affected).

Red 유효성: production 미변경(supabase 체인) → pg mock 미발화 → 계약 단언 FAIL.
"""

from __future__ import annotations

from datetime import date, datetime
from unittest.mock import AsyncMock, patch

import pytest

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _neutralize_supabase(monkeypatch):
    """현행 supabase(asyncio.to_thread) 경로 중립화 — Red 단계 실 DNS hang/노이즈 차단.

    Red 시점 production 은 supabase 를 호출 → 실 Supabase 로 나가 httpx ConnectError.
    to_thread 를 즉시 예외로 중립화 → 테스트가 *계약 단언* 으로 FAIL (의도 선명).
    Green 전환 후엔 무해 (심볼 사라짐, raising=False).
    """
    from src.db import parameter_recommendations as pr

    async def _fast_to_thread(fn, *a, **k):
        raise Exception("to_thread 중립화 (M3a Red)")

    monkeypatch.setattr(pr, "supabase", None, raising=False)
    monkeypatch.setattr(pr.asyncio, "to_thread", _fast_to_thread, raising=False)
    yield


# ---------------------------------------------------------------------------
# insert_recommendation — JSONB + NUMERIC nullable + TIMESTAMPTZ datetime + RETURNING
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_insert_recommendation_uses_pg_insert_returning():
    """insert_recommendation → pg.fetchrow/execute INSERT INTO parameter_recommendations RETURNING."""
    from src.db import parameter_recommendations as pr

    inserted = {"id": "uuid-1", "strategy_id": "momentum", "status": "pending"}
    with patch.object(pr, "pg", create=True) as pg_mod:
        pg_mod.fetchrow = AsyncMock(return_value=inserted)
        pg_mod.execute = AsyncMock(return_value="INSERT 0 1")
        pg_mod.fetch = AsyncMock(return_value=[inserted])
        out = await pr.insert_recommendation(
            target_date=date(2026, 7, 16),
            strategy_id="momentum",
            current_params={"k": 1.3},
            recommended_params={"k": 1.45},
            reasoning="근거",
            metrics={"win_rate": 0.5},
            recommended_weight=0.28,
            code_review_notes="리뷰",
            weight_reasoning="비중 사유",
        )

    assert out == inserted, "insert_recommendation → 삽입 dict 반환 계약."
    all_sql = _collect_sql(pg_mod)
    assert any("INSERT INTO parameter_recommendations" in s for s in all_sql), (
        "INSERT INTO parameter_recommendations SQL 누락."
    )
    args = _insert_args(pg_mod)
    assert date(2026, 7, 16) in args, "target_date DATE 바인딩 누락."
    assert "momentum" in args, "strategy_id 바인딩 누락."
    # current_params / recommended_params / metrics = JSONB (dict 또는 json.dumps)
    assert _has_jsonb_binding(args, {"k": 1.3}), "current_params JSONB 바인딩 누락."
    assert _has_jsonb_binding(args, {"k": 1.45}), "recommended_params JSONB 바인딩 누락."
    assert _has_jsonb_binding(args, {"win_rate": 0.5}), "metrics JSONB 바인딩 누락."


@pytest.mark.asyncio
async def test_insert_recommendation_created_at_is_datetime():
    """created_at TIMESTAMPTZ 바인딩은 datetime (M1 패턴 2 — asyncpg str 불가)."""
    from src.db import parameter_recommendations as pr

    with patch.object(pr, "pg", create=True) as pg_mod:
        pg_mod.fetchrow = AsyncMock(return_value={"id": "x"})
        pg_mod.execute = AsyncMock(return_value="INSERT 0 1")
        pg_mod.fetch = AsyncMock(return_value=[{"id": "x"}])
        await pr.insert_recommendation(
            target_date=date(2026, 7, 16),
            strategy_id="momentum",
            current_params={},
            recommended_params={},
            reasoning="r",
            metrics={},
        )

    args = _insert_args(pg_mod)
    assert any(isinstance(a, datetime) for a in args), (
        "created_at 은 datetime 바인딩 (fromisoformat(now_kst_iso())) — str 금지."
    )


@pytest.mark.asyncio
async def test_insert_recommendation_weight_none_binds_none():
    """recommended_weight/applied_weight NUMERIC nullable — None 전달 시 None 바인딩 (INSERT applied_weight=None 계약)."""
    from src.db import parameter_recommendations as pr

    with patch.object(pr, "pg", create=True) as pg_mod:
        pg_mod.fetchrow = AsyncMock(return_value={"id": "x"})
        pg_mod.execute = AsyncMock(return_value="INSERT 0 1")
        pg_mod.fetch = AsyncMock(return_value=[{"id": "x"}])
        await pr.insert_recommendation(
            target_date=date(2026, 7, 16),
            strategy_id="momentum",
            current_params={},
            recommended_params={},
            reasoning="r",
            metrics={},
            recommended_weight=None,
        )

    args = _insert_args(pg_mod)
    # applied_weight 는 INSERT 시점 항상 None — None 바인딩 존재 확인
    assert any(a is None for a in args), (
        "applied_weight/recommended_weight NUMERIC nullable → None 바인딩 계약 보존."
    )


@pytest.mark.asyncio
async def test_insert_recommendation_unique_conflict_returns_none():
    """(target_date, strategy_id) UNIQUE 충돌 → None (duplicate/unique/23505 분기 보존)."""
    from src.db import parameter_recommendations as pr

    exc = Exception("duplicate key value violates unique constraint (23505)")
    with patch.object(pr, "pg", create=True) as pg_mod:
        pg_mod.fetchrow = AsyncMock(side_effect=exc)
        pg_mod.execute = AsyncMock(side_effect=exc)
        pg_mod.fetch = AsyncMock(side_effect=exc)
        out = await pr.insert_recommendation(
            target_date=date(2026, 7, 16),
            strategy_id="momentum",
            current_params={},
            recommended_params={},
            reasoning="r",
            metrics={},
        )

    assert out is None, "UNIQUE 충돌 → None 계약 보존."


@pytest.mark.asyncio
async def test_insert_recommendation_generic_exception_returns_none():
    """비-중복 예외도 None (기존 logger.exception + return None graceful 계약)."""
    from src.db import parameter_recommendations as pr

    with patch.object(pr, "pg", create=True) as pg_mod:
        pg_mod.fetchrow = AsyncMock(side_effect=Exception("boom"))
        pg_mod.execute = AsyncMock(side_effect=Exception("boom"))
        pg_mod.fetch = AsyncMock(side_effect=Exception("boom"))
        out = await pr.insert_recommendation(
            target_date=date(2026, 7, 16),
            strategy_id="momentum",
            current_params={},
            recommended_params={},
            reasoning="r",
            metrics={},
        )

    assert out is None, "일반 예외 → None graceful 계약 보존."


# ---------------------------------------------------------------------------
# list_recommendations — SELECT WHERE target_date >= cutoff ORDER BY created_at DESC
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_list_recommendations_uses_pg_fetch_order_desc():
    """list_recommendations(days) → pg.fetch(... WHERE target_date >= $1 ORDER BY created_at DESC)."""
    from src.db import parameter_recommendations as pr

    rows = [{"id": "a", "status": "pending"}]
    with patch.object(pr, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(return_value=rows)
        out = await pr.list_recommendations(days=7)

    assert out == rows, "list_recommendations → list[dict] 반환 계약."
    sql = pg_mod.fetch.await_args.args[0]
    assert "parameter_recommendations" in sql and "SELECT" in sql.upper()
    assert "ORDER BY" in sql.upper() and "DESC" in sql.upper(), "created_at DESC 정렬 누락."
    # cutoff 파라미터(target_date - days) 바인딩 존재
    passed = pg_mod.fetch.await_args.args[1:]
    assert len(passed) >= 1, "cutoff(days 기반) 파라미터 바인딩 누락."


@pytest.mark.asyncio
async def test_list_recommendations_empty_returns_empty_list():
    """0건 → [] (result.data or [] 대응)."""
    from src.db import parameter_recommendations as pr

    with patch.object(pr, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(return_value=[])
        out = await pr.list_recommendations()

    assert out == [], "0건 → 빈 리스트."


# ---------------------------------------------------------------------------
# get_recommendation — SELECT WHERE id = $1 → dict | None
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_get_recommendation_uses_pg_fetchrow_where_id():
    """get_recommendation(id) → pg.fetchrow(... WHERE id = $1) → dict."""
    from src.db import parameter_recommendations as pr

    row = {"id": "uuid-9", "status": "pending"}
    with patch.object(pr, "pg", create=True) as pg_mod:
        pg_mod.fetchrow = AsyncMock(return_value=row)
        pg_mod.fetch = AsyncMock(return_value=[row])
        out = await pr.get_recommendation("uuid-9")

    assert out == row, "get_recommendation → 단일 dict 반환."
    sql = _collect_sql(pg_mod)[0]
    assert "parameter_recommendations" in sql and "id" in sql
    # id 바인딩 존재
    passed = _first_await_args(pg_mod)
    assert "uuid-9" in passed, "id 바인딩 누락."


@pytest.mark.asyncio
async def test_get_recommendation_missing_returns_none():
    """미존재 → None (fetchrow None / 빈 fetch 대응)."""
    from src.db import parameter_recommendations as pr

    with patch.object(pr, "pg", create=True) as pg_mod:
        pg_mod.fetchrow = AsyncMock(return_value=None)
        pg_mod.fetch = AsyncMock(return_value=[])
        out = await pr.get_recommendation("nope")

    assert out is None, "미존재 → None."


# ---------------------------------------------------------------------------
# update_recommendation_status — applied_at / rejected_at 자동 + 조건부 페이로드
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_update_status_applied_sets_applied_at():
    """status='applied' → UPDATE + applied_at datetime 바인딩 (자동 기록 계약)."""
    from src.db import parameter_recommendations as pr

    updated = {"id": "u1", "status": "applied"}
    with patch.object(pr, "pg", create=True) as pg_mod:
        pg_mod.fetchrow = AsyncMock(return_value=updated)
        pg_mod.execute = AsyncMock(return_value="UPDATE 1")
        pg_mod.fetch = AsyncMock(return_value=[updated])
        out = await pr.update_recommendation_status(
            "u1", "applied", applied_params={"k": 2.0}, applied_weight=0.4,
        )

    assert out == updated, "update_recommendation_status → dict 반환 계약."
    all_sql = _collect_sql(pg_mod)
    assert any("UPDATE parameter_recommendations" in s for s in all_sql), "UPDATE SQL 누락."
    args = _update_args(pg_mod)
    assert any(isinstance(a, datetime) for a in args), (
        "applied_at 은 datetime 바인딩 — str 금지 (applied/partial/applied_auto 자동 기록)."
    )
    # applied_params JSONB + applied_weight NUMERIC 바인딩
    assert _has_jsonb_binding(args, {"k": 2.0}), "applied_params JSONB 바인딩 누락."
    assert any(a == 0.4 for a in args), "applied_weight NUMERIC 바인딩 누락."


@pytest.mark.asyncio
async def test_update_status_applied_auto_sets_applied_at():
    """status='applied_auto' (사이클 23) → applied_at 자동 기록."""
    from src.db import parameter_recommendations as pr

    with patch.object(pr, "pg", create=True) as pg_mod:
        pg_mod.fetchrow = AsyncMock(return_value={"id": "u1"})
        pg_mod.execute = AsyncMock(return_value="UPDATE 1")
        pg_mod.fetch = AsyncMock(return_value=[{"id": "u1"}])
        await pr.update_recommendation_status("u1", "applied_auto")

    args = _update_args(pg_mod)
    assert any(isinstance(a, datetime) for a in args), (
        "applied_auto → applied_at datetime 자동 기록 (운영자 수동 applied 와 동형)."
    )


@pytest.mark.asyncio
async def test_update_status_rejected_sets_rejected_at():
    """status='rejected' → rejected_at 자동 기록 (applied_at 아님)."""
    from src.db import parameter_recommendations as pr

    with patch.object(pr, "pg", create=True) as pg_mod:
        pg_mod.fetchrow = AsyncMock(return_value={"id": "u1"})
        pg_mod.execute = AsyncMock(return_value="UPDATE 1")
        pg_mod.fetch = AsyncMock(return_value=[{"id": "u1"}])
        await pr.update_recommendation_status("u1", "rejected")

    all_sql = _collect_sql(pg_mod)
    joined = " ".join(all_sql)
    assert "rejected_at" in joined, "rejected 상태 → rejected_at SET 누락."
    args = _update_args(pg_mod)
    assert any(isinstance(a, datetime) for a in args), "rejected_at datetime 바인딩 누락."


@pytest.mark.asyncio
async def test_update_status_empty_result_returns_empty_dict():
    """UPDATE 0건 (미존재 id) → 빈 dict {} (기존 result.data[0] if ... else {} 계약)."""
    from src.db import parameter_recommendations as pr

    with patch.object(pr, "pg", create=True) as pg_mod:
        pg_mod.fetchrow = AsyncMock(return_value=None)
        pg_mod.execute = AsyncMock(return_value="UPDATE 0")
        pg_mod.fetch = AsyncMock(return_value=[])
        out = await pr.update_recommendation_status("nope", "applied")

    assert out == {}, "미존재 id → {} 계약 보존."


# ---------------------------------------------------------------------------
# update_backtest_summary — backtest_summary JSONB + 미존재/예외 graceful {}
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_update_backtest_summary_jsonb_binding():
    """update_backtest_summary → UPDATE backtest_summary = $ (JSONB dict 바인딩)."""
    from src.db import parameter_recommendations as pr

    summary = {"current": {"momentum": {"win": 0.5}}, "recommended": {}, "diff": {}}
    updated = {"id": "u1", "backtest_summary": summary}
    with patch.object(pr, "pg", create=True) as pg_mod:
        pg_mod.fetchrow = AsyncMock(return_value=updated)
        pg_mod.execute = AsyncMock(return_value="UPDATE 1")
        pg_mod.fetch = AsyncMock(return_value=[updated])
        out = await pr.update_backtest_summary("u1", summary)

    assert out == updated, "update_backtest_summary → 갱신 dict 반환."
    all_sql = _collect_sql(pg_mod)
    assert any("backtest_summary" in s for s in all_sql), "backtest_summary UPDATE SQL 누락."
    args = _update_args(pg_mod)
    assert _has_jsonb_binding(args, summary), "backtest_summary JSONB dict 바인딩 누락."


@pytest.mark.asyncio
async def test_update_backtest_summary_missing_returns_empty_dict():
    """미존재 id (0건) → {} graceful (예외 전파 안 함)."""
    from src.db import parameter_recommendations as pr

    with patch.object(pr, "pg", create=True) as pg_mod:
        pg_mod.fetchrow = AsyncMock(return_value=None)
        pg_mod.execute = AsyncMock(return_value="UPDATE 0")
        pg_mod.fetch = AsyncMock(return_value=[])
        out = await pr.update_backtest_summary("nope", {"x": 1})

    assert out == {}, "미존재 id → {} graceful."


@pytest.mark.asyncio
async def test_update_backtest_summary_exception_returns_empty_dict():
    """예외 → {} graceful (기존 try/except 계약 보존)."""
    from src.db import parameter_recommendations as pr

    with patch.object(pr, "pg", create=True) as pg_mod:
        pg_mod.fetchrow = AsyncMock(side_effect=Exception("boom"))
        pg_mod.execute = AsyncMock(side_effect=Exception("boom"))
        pg_mod.fetch = AsyncMock(side_effect=Exception("boom"))
        out = await pr.update_backtest_summary("u1", {"x": 1})

    assert out == {}, "예외 → {} graceful (호출자 리포트 무중단)."


# ---------------------------------------------------------------------------
# list_recommendations_pending_backtest / list_pending_by_date — WHERE 조합
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_list_pending_backtest_filters_null_summary():
    """list_recommendations_pending_backtest → WHERE target_date=$ AND backtest_summary IS NULL."""
    from src.db import parameter_recommendations as pr

    rows = [{"id": "a"}]
    with patch.object(pr, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(return_value=rows)
        out = await pr.list_recommendations_pending_backtest(date(2026, 7, 16))

    assert out == rows
    sql = pg_mod.fetch.await_args.args[0].upper()
    assert "BACKTEST_SUMMARY IS NULL" in sql, "backtest_summary IS NULL 필터 누락."
    assert date(2026, 7, 16) in pg_mod.fetch.await_args.args[1:], "target_date 바인딩 누락."


@pytest.mark.asyncio
async def test_list_pending_by_date_filters_pending_status():
    """list_pending_by_date → WHERE target_date=$ AND status='pending'."""
    from src.db import parameter_recommendations as pr

    rows = [{"id": "a", "status": "pending"}]
    with patch.object(pr, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(return_value=rows)
        out = await pr.list_pending_by_date(date(2026, 7, 16))

    assert out == rows
    passed = pg_mod.fetch.await_args.args[1:]
    assert date(2026, 7, 16) in passed, "target_date 바인딩 누락."
    sql = pg_mod.fetch.await_args.args[0]
    assert "status" in sql and ("pending" in sql or "pending" in str(passed)), (
        "status='pending' 필터 누락."
    )


# ---------------------------------------------------------------------------
# expire_pending_before — UPDATE status='expired' → int(affected) (execute "UPDATE N" 파싱)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_expire_pending_before_returns_affected_count():
    """expire_pending_before → UPDATE ... status='expired' → int(affected 행수) ('UPDATE 3' 파싱)."""
    from src.db import parameter_recommendations as pr

    with patch.object(pr, "pg", create=True) as pg_mod:
        pg_mod.execute = AsyncMock(return_value="UPDATE 3")
        pg_mod.fetch = AsyncMock(return_value=[{"id": "a"}, {"id": "b"}, {"id": "c"}])
        out = await pr.expire_pending_before(date(2026, 7, 16))

    assert out == 3, "expire_pending_before → 만료 행수 int 반환 ('UPDATE 3' 파싱 또는 RETURNING count)."
    all_sql = _collect_sql(pg_mod)
    joined = " ".join(all_sql).upper()
    assert "UPDATE PARAMETER_RECOMMENDATIONS" in joined, "UPDATE SQL 누락."
    assert "EXPIRED" in joined or "'expired'" in " ".join(all_sql), "status='expired' SET 누락."


@pytest.mark.asyncio
async def test_expire_pending_before_zero_affected():
    """만료 대상 0건 → 0 반환."""
    from src.db import parameter_recommendations as pr

    with patch.object(pr, "pg", create=True) as pg_mod:
        pg_mod.execute = AsyncMock(return_value="UPDATE 0")
        pg_mod.fetch = AsyncMock(return_value=[])
        out = await pr.expire_pending_before(date(2026, 7, 16))

    assert out == 0, "0건 만료 → 0."


# ---------------------------------------------------------------------------
# 계약 보존 불변식 — supabase 미참조 (pg 단독)
#
# ⚠️ 소스 파일 정적 검사 (런타임 hasattr 금지): autouse `_neutralize_supabase`
# fixture 가 `monkeypatch.setattr(pr, "supabase", None, raising=False)` 로 심볼을
# *생성* 하므로 런타임 `hasattr(pr, "supabase")` 는 항상 True → 계약을 검증할 수 없다.
# 실제 계약("전환 후 supabase 를 코드에서 참조하지 않는다")은 소스의 import/이름
# 참조로만 검증 가능 → `ast` 파싱으로 판정 (docstring/주석의 'supabase' 문자열은 무시).
# ---------------------------------------------------------------------------
def test_parameter_recommendations_no_supabase_after_transition():
    """전환 후 parameter_recommendations.py 는 supabase 를 참조하지 않는다 (pg 단독).

    소스 AST 검사 — supabase import 부재 + supabase/execute_with_retry 코드 참조 부재
    + src.db.pg import 존재. (fixture 오염 회피 = 이 테스트는 autouse fixture 무관.)
    """
    from src.db import parameter_recommendations as pr

    _assert_no_supabase_reference_in_source(pr, forbidden_names=("supabase",))
    assert _source_imports_pg(pr), "parameter_recommendations 가 src.db.pg 를 import 해야 함."


# ---------------------------------------------------------------------------
# 헬퍼 — 소스 AST 정적 검사 (supabase 미참조 계약)
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
    """소스 AST 에 forbidden 심볼의 import / 코드 참조(Name/Attribute) 가 없음을 단언.

    docstring/주석의 'supabase' 문자열은 파싱 대상이 아니므로 자연 무시된다
    (전환 이력 서술 "supabase-py → src.db.pg" 는 참조가 아님).
    """
    import ast
    import inspect

    forbidden = set(forbidden_names)
    tree = ast.parse(inspect.getsource(mod))
    offenders: list[str] = []

    for node in ast.walk(tree):
        # import supabase / from ... import supabase / execute_with_retry
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
        # 코드 참조: 이름(Name) 또는 속성 접근(Attribute) 의 루트 이름
        elif isinstance(node, ast.Name) and node.id in forbidden:
            offenders.append(f"name {node.id}")

    assert not offenders, (
        f"전환 후 supabase/execute_with_retry 코드 참조 잔존 금지 (pg 단독). 발견: {offenders}"
    )


# ---------------------------------------------------------------------------
# 헬퍼 — 발화 경로 SQL·인자 수집 (Green 구현 자유도)
#
# ⚠️ isinstance(m, AsyncMock) 가드: `patch.object(pr, "pg", create=True)` 는 순수
# MagicMock 을 만들어, 테스트가 설정하지 않은 accessor(예: fetchval)도 auto-child
# MagicMock 으로 존재한다. 그 미설정 accessor 의 `.await_args` 는 MagicMock(None 아님)
# 이라 `.args[0]` 가 MagicMock 을 반환 → join/in 비교에서 TypeError 유발. 실제 발화한
# AsyncMock 만 검사해 오탐을 차단한다.
# ---------------------------------------------------------------------------
def _collect_sql(pg_mod) -> list[str]:
    from unittest.mock import AsyncMock

    sqls: list[str] = []
    for name in ("fetchrow", "execute", "fetch", "fetchval"):
        m = getattr(pg_mod, name, None)
        if isinstance(m, AsyncMock) and m.await_args is not None:
            sqls.append(m.await_args.args[0])
    return sqls


def _first_await_args(pg_mod) -> tuple:
    from unittest.mock import AsyncMock

    for name in ("fetchrow", "fetch", "execute"):
        m = getattr(pg_mod, name, None)
        if isinstance(m, AsyncMock) and m.await_args is not None:
            return m.await_args.args[1:]
    return ()


def _insert_args(pg_mod) -> tuple:
    """INSERT 를 실제 발화한 mock(fetchrow 우선, 없으면 execute/fetch)의 바인딩 인자."""
    from unittest.mock import AsyncMock

    for name in ("fetchrow", "execute", "fetch"):
        m = getattr(pg_mod, name, None)
        if isinstance(m, AsyncMock) and m.await_args is not None:
            sql = m.await_args.args[0]
            if "INSERT" in sql.upper():
                return m.await_args.args[1:]
    return ()


def _update_args(pg_mod) -> tuple:
    """UPDATE 를 실제 발화한 mock 의 바인딩 인자."""
    from unittest.mock import AsyncMock

    for name in ("fetchrow", "execute", "fetch"):
        m = getattr(pg_mod, name, None)
        if isinstance(m, AsyncMock) and m.await_args is not None:
            sql = m.await_args.args[0]
            if "UPDATE" in sql.upper():
                return m.await_args.args[1:]
    return ()


def _has_jsonb_binding(args: tuple, expected) -> bool:
    """JSONB 컬럼 바인딩이 dict/list 원본 또는 json.dumps 문자열로 포함되는지."""
    import json

    dumped = json.dumps(expected)
    for a in args:
        if a == expected:
            return True
        if isinstance(a, str) and a == dumped:
            return True
    return False
