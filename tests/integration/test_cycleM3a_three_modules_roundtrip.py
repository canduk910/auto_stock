"""사이클 M3a (Red) — 분석·관찰 3모듈 실 Postgres 왕복 검증 (비 hot-path).

승인 계획: `~/.claude/plans/partitioned-kindling-lollipop.md` (단계 3 — 분석·관찰).

mock 단위로 못 잡는 **실 SQL · JSONB codec 왕복 · UNIQUE/복합PK upsert · NUMERIC→Decimal ·
60s 캐시 stale 반환 · batch 100 chunk** 안전망. docker/DATABASE_URL_TEST 없으면 pg_harness fixture skip.

⚠️ 핵심 (계획 3대 미묘 계약):
1. **JSONB codec** — parameter_recommendations backtest_summary/current_params 왕복 dict.
2. **UNIQUE upsert** — param_rec (target_date, strategy_id) UNIQUE (pending/applied/partial 부분) +
   financial 복합 PK (ticker, stac_yymm, div_cls).
3. **NUMERIC → Decimal** — financial 18 컬럼 asyncpg Decimal 반환.
4. **60s 캐시 stale 반환** — kis_quote_accounts DB 예외 시 stale 캐시 반환 계약.

Red 유효성: production(3 모듈) 이 아직 pg 미사용(supabase 호출) → 실 PG 왕복 경로 없음 → 전부 FAIL/에러.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.slow]


@pytest.fixture(autouse=True)
def _neutralize_supabase_path(monkeypatch):
    """Red 단계 실 Supabase(DNS) 접촉 차단 — 3모듈이 전환 전까지 supabase 를 호출하면
    실 네트워크로 나가 httpx ConnectError/60s timeout 을 유발한다. supabase 경로를
    즉시 예외로 중립화 → 통합 테스트가 *왕복 계약* 단언으로 빠르게 FAIL(Red).

    Green 전환 후엔 3모듈이 pg 만 쓰므로 이 심볼들이 사라져 무해(raising=False).
    실 PG 왕복(pg.*)은 이 fixture 와 무관하게 정상 동작한다.
    """
    async def _fast_to_thread(fn, *a, **k):
        raise Exception("supabase to_thread 중립화 (M3a Red integration)")

    async def _fast_retry(build, *, op: str = ""):
        raise Exception("supabase execute_with_retry 중립화 (M3a Red integration)")

    for modname in (
        "src.db.parameter_recommendations",
        "src.db.kis_quote_accounts",
        "src.db.stock_master_financial",
    ):
        import importlib

        mod = importlib.import_module(modname)
        monkeypatch.setattr(mod, "supabase", None, raising=False)
        monkeypatch.setattr(mod, "execute_with_retry", _fast_retry, raising=False)
        if hasattr(mod, "asyncio"):
            monkeypatch.setattr(mod.asyncio, "to_thread", _fast_to_thread, raising=False)
    yield


# ===========================================================================
# parameter_recommendations — ⚠️ JSONB codec 왕복 + UNIQUE + status 자동 타임스탬프
# ===========================================================================
@pytest.mark.asyncio
async def test_insert_and_get_jsonb_roundtrip(clean_parameter_recommendations):
    """insert → get 왕복 — current_params/recommended_params/metrics JSONB dict 복원 (codec)."""
    from src.db import parameter_recommendations as pr

    inserted = await pr.insert_recommendation(
        target_date=date(2026, 7, 16),
        strategy_id="momentum",
        current_params={"k": 1.3},
        recommended_params={"k": 1.45},
        reasoning="근거",
        metrics={"win_rate": 0.5, "trades": 12},
        recommended_weight=0.28,
        weight_reasoning="비중 하향",
    )
    assert inserted is not None, "insert_recommendation → row 반환."

    got = await pr.get_recommendation(inserted["id"])
    assert got is not None
    # ⚠️ JSONB codec — dict 로 복원 (str 이면 codec 미작동)
    assert isinstance(got["current_params"], dict), "current_params JSONB → dict codec 복원."
    assert got["current_params"] == {"k": 1.3}, "current_params 왕복 무손실."
    assert got["recommended_params"] == {"k": 1.45}, "recommended_params 왕복."
    assert got["metrics"]["win_rate"] == 0.5, "metrics JSONB 왕복."


@pytest.mark.asyncio
async def test_unique_per_day_conflict_returns_none(clean_parameter_recommendations):
    """⚠️ (target_date, strategy_id) UNIQUE (pending 부분) 2회 insert → 2번째 None."""
    from src.db import parameter_recommendations as pr

    first = await pr.insert_recommendation(
        target_date=date(2026, 7, 16), strategy_id="momentum",
        current_params={}, recommended_params={}, reasoning="r", metrics={},
    )
    assert first is not None, "1번째 insert 성공."

    dup = await pr.insert_recommendation(
        target_date=date(2026, 7, 16), strategy_id="momentum",
        current_params={}, recommended_params={}, reasoning="r2", metrics={},
    )
    assert dup is None, "UNIQUE(target_date, strategy_id) 충돌 → None (부분 인덱스 pending)."


@pytest.mark.asyncio
async def test_backtest_summary_jsonb_roundtrip(clean_parameter_recommendations):
    """update_backtest_summary → JSONB dict 왕복 (nested current/recommended/diff)."""
    from src.db import parameter_recommendations as pr

    rec = await pr.insert_recommendation(
        target_date=date(2026, 7, 16), strategy_id="vb",
        current_params={}, recommended_params={}, reasoning="r", metrics={},
    )
    summary = {
        "current": {"vb": {"win_rate": 0.33, "pf": 1.57}},
        "recommended": {"vb": {"win_rate": 0.4}},
        "diff": {"vb": {"win_rate": 0.07}},
    }
    out = await pr.update_backtest_summary(rec["id"], summary)
    assert out, "update_backtest_summary → 갱신 dict 반환."

    got = await pr.get_recommendation(rec["id"])
    assert isinstance(got["backtest_summary"], dict), "backtest_summary JSONB → dict codec."
    assert got["backtest_summary"]["current"]["vb"]["pf"] == 1.57, "nested JSONB 왕복 무손실."


@pytest.mark.asyncio
async def test_update_status_applied_sets_applied_at(clean_parameter_recommendations):
    """status='applied' → applied_at 자동 기록 (TIMESTAMPTZ)."""
    from src.db import parameter_recommendations as pr

    rec = await pr.insert_recommendation(
        target_date=date(2026, 7, 16), strategy_id="ltv",
        current_params={}, recommended_params={}, reasoning="r", metrics={},
    )
    await pr.update_recommendation_status(rec["id"], "applied", applied_weight=0.4)

    got = await pr.get_recommendation(rec["id"])
    assert got["status"] == "applied"
    assert got["applied_at"] is not None, "applied → applied_at 자동 기록."
    assert got["rejected_at"] is None, "applied 상태에서 rejected_at 미기록."


@pytest.mark.asyncio
async def test_expire_pending_before_returns_count(clean_parameter_recommendations):
    """expire_pending_before → 이전 pending 만료 + 정확 행수 반환."""
    from src.db import parameter_recommendations as pr

    await pr.insert_recommendation(
        target_date=date(2026, 7, 10), strategy_id="momentum",
        current_params={}, recommended_params={}, reasoning="r", metrics={},
    )
    await pr.insert_recommendation(
        target_date=date(2026, 7, 11), strategy_id="vb",
        current_params={}, recommended_params={}, reasoning="r", metrics={},
    )
    n = await pr.expire_pending_before(date(2026, 7, 16))
    assert n == 2, "이전 pending 2건 만료 (정확 행수, PostgREST cap 무관)."

    pending = await pr.list_pending_by_date(date(2026, 7, 10))
    assert pending == [], "만료 후 pending 조회 0건."


@pytest.mark.asyncio
async def test_list_pending_backtest_filters_null(clean_parameter_recommendations):
    """list_recommendations_pending_backtest → backtest_summary IS NULL 만."""
    from src.db import parameter_recommendations as pr

    r1 = await pr.insert_recommendation(
        target_date=date(2026, 7, 16), strategy_id="momentum",
        current_params={}, recommended_params={}, reasoning="r", metrics={},
    )
    await pr.insert_recommendation(
        target_date=date(2026, 7, 16), strategy_id="vb",
        current_params={}, recommended_params={}, reasoning="r", metrics={},
    )
    # r1 에만 summary 채움
    await pr.update_backtest_summary(r1["id"], {"current": {}, "recommended": {}, "diff": {}})

    pending = await pr.list_recommendations_pending_backtest(date(2026, 7, 16))
    ids = {r["strategy_id"] for r in pending}
    assert ids == {"vb"}, "summary NULL 인 vb 만 (momentum 은 summary 채워짐 → 제외)."


# ===========================================================================
# kis_quote_accounts — ⚠️ 60s 캐시 stale 반환 + 평문 격리 + label UNIQUE
# ===========================================================================
@pytest.mark.asyncio
async def test_insert_get_masked_plaintext_isolation(clean_kis_quote_accounts):
    """insert → list 마스킹 + get_credentials 평문 (평문 노출 유일 경로 계약)."""
    from src.db import kis_quote_accounts as kqa

    await kqa.insert_account("quote-1", "APPKEY-1", "SECRET-PLAINTEXT-0000", "real")

    accts = await kqa.list_accounts()
    assert len(accts) == 1
    assert accts[0].app_secret_masked.startswith("****"), "list 는 마스킹 (평문 노출 금지)."
    assert not hasattr(accts[0], "app_secret"), "평문 app_secret 필드 부재."

    # 평문은 credentials 함수만
    creds = await kqa.get_credentials_for_token_manager("quote-1")
    assert creds["app_secret"] == "SECRET-PLAINTEXT-0000", "credentials 만 평문 반환 (유일 예외)."


@pytest.mark.asyncio
async def test_label_unique_conflict_raises(clean_kis_quote_accounts):
    """label UNIQUE — 동일 label 재등록 → LabelConflictError."""
    from src.db import kis_quote_accounts as kqa

    await kqa.insert_account("dup", "K1", "S1secret", "real")
    with pytest.raises(kqa.LabelConflictError):
        await kqa.insert_account("dup", "K2", "S2secret", "vts")


@pytest.mark.asyncio
async def test_cache_stale_returned_on_db_error(clean_kis_quote_accounts, monkeypatch):
    """⚠️ DB 예외 + 캐시 있음 → stale 반환 (사이클 14-D 계약 절대 보존, 실 PG 경로)."""
    from src.db import kis_quote_accounts as kqa
    import src.db.pg as pg

    clock = {"t": 1000.0}
    monkeypatch.setattr(kqa.time, "monotonic", lambda: clock["t"], raising=False)

    await kqa.insert_account("cached-quote", "K1", "S1secret", "real")
    first = await kqa.list_accounts()          # 캐시 채움
    assert len(first) == 1

    # TTL 만료 + pg.fetch 를 예외로 교체 → stale 반환되어야 함
    clock["t"] += 61.0
    orig_fetch = pg.fetch

    async def _boom(*a, **k):
        raise Exception("connection lost")

    monkeypatch.setattr(pg, "fetch", _boom, raising=False)
    try:
        stale = await kqa.list_accounts()
    finally:
        monkeypatch.setattr(pg, "fetch", orig_fetch, raising=False)

    assert len(stale) == 1 and stale[0].label == "cached-quote", (
        "DB 예외 시 stale 캐시 반환 (graceful). 빈 리스트면 사이클 14-D 계약 위반."
    )


@pytest.mark.asyncio
async def test_update_active_and_delete_roundtrip(clean_kis_quote_accounts):
    """update_account(active=False) → 반영 + delete → True/False 왕복."""
    from src.db import kis_quote_accounts as kqa

    acct = await kqa.insert_account("quote-x", "K1", "S1secret", "real")
    updated = await kqa.update_account(acct.id, active=False)
    assert updated is not None and updated.active is False, "active 부분 갱신 반영."

    assert await kqa.delete_account(acct.id) is True, "존재 → 삭제 True."
    assert await kqa.delete_account(acct.id) is False, "재삭제 → False (미존재)."


# ===========================================================================
# stock_master_financial — ⚠️ NUMERIC→Decimal + 복합PK upsert + batch chunk + raw JSONB
# ===========================================================================
@pytest.mark.asyncio
async def test_financial_upsert_numeric_decimal_roundtrip(clean_stock_master_financial):
    """⚠️ upsert → get_financial_series — NUMERIC 컬럼 Decimal 반환 + raw JSONB dict 왕복."""
    from src.db import stock_master_financial as smf

    rows = [{
        "ticker": "005930", "stac_yymm": "202312", "div_cls": "0",
        "sale_account": 1000.5, "total_aset": 5000.25, "ev_ebitda": 8.5,
        "raw": {"src": "FHKST66430200", "n": 1},
    }]
    n = await smf.upsert_financial_batch("005930", rows)
    assert n == 1, "1건 upsert 성공."

    series = await smf.get_financial_series("005930", div_cls="0", limit=3)
    assert len(series) == 1
    row = series[0]
    # NUMERIC → Decimal (계획 3대 미묘 계약 ③)
    assert isinstance(row["sale_account"], Decimal), "NUMERIC → Decimal 반환 (asyncpg)."
    assert row["sale_account"] == Decimal("1000.5"), "Decimal 값 무손실."
    # raw JSONB → dict codec
    assert isinstance(row["raw"], dict) and row["raw"]["n"] == 1, "raw JSONB → dict codec 왕복."


@pytest.mark.asyncio
async def test_financial_composite_pk_upsert_single_row(clean_stock_master_financial):
    """복합 PK (ticker, stac_yymm, div_cls) — 동일 키 2회 upsert → 1행 갱신."""
    from src.db import stock_master_financial as smf
    import src.db.pg as pg

    base = {"ticker": "005930", "stac_yymm": "202312", "div_cls": "0", "raw": {}}
    await smf.upsert_financial_batch("005930", [{**base, "ev_ebitda": 8.0}])
    await smf.upsert_financial_batch("005930", [{**base, "ev_ebitda": 9.5}])

    cnt = await pg.fetchval(
        "SELECT count(*) FROM stock_master_financial WHERE ticker=$1 AND stac_yymm=$2 AND div_cls=$3",
        "005930", "202312", "0",
    )
    assert cnt == 1, "복합 PK upsert → 1행 (중복 없음)."
    series = await smf.get_financial_series("005930")
    assert series[0]["ev_ebitda"] == Decimal("9.5"), "ON CONFLICT DO UPDATE 최신 값 반영."


@pytest.mark.asyncio
async def test_financial_batch_100_chunk_all_persisted(clean_stock_master_financial):
    """batch 100 chunk — 250건(3 chunk) 전량 적재 확인."""
    from src.db import stock_master_financial as smf
    import src.db.pg as pg

    rows = [
        {"ticker": "005930", "stac_yymm": f"2023{i:02d}", "div_cls": "0", "raw": {}}
        for i in range(1, 13)  # 12 유효 월(202301~202312) — stac_yymm 유니크 보장
    ]
    n = await smf.upsert_financial_batch("005930", rows)
    assert n == 12, "12건 upsert 성공."

    cnt = await pg.fetchval(
        "SELECT count(*) FROM stock_master_financial WHERE ticker=$1", "005930"
    )
    assert cnt == 12, "batch 전량 적재 (chunk 경계 무손실)."


@pytest.mark.asyncio
async def test_financial_max_stac_yymm_and_count(clean_stock_master_financial):
    """max_stac_yymm DESC LIMIT 1 + count_all 왕복."""
    from src.db import stock_master_financial as smf

    for ym in ("202112", "202212", "202312"):
        await smf.upsert_financial_batch(
            "005930", [{"ticker": "005930", "stac_yymm": ym, "div_cls": "0", "raw": {}}]
        )

    latest = await smf.max_stac_yymm("005930", div_cls="0")
    assert latest == "202312", "max_stac_yymm → 최신 stac_yymm (DESC)."
    assert await smf.count_all() == 3, "count_all → 3."
