"""cycle276 Red — 실 Postgres 왕복: 마이그레이션 043 + `llm_buy_evaluations` upsert/조회/조인.

명세 = `_workspace/red/cycle276_order_time_llm_eval_spec.md` §11.1 (B105~B112) · C31~C34.

**Red 단계 — 테스트만. `src/` 미변경.** Green = backend-dev.

## 왜 실 PG 인가 (mock 으로는 못 잡는 것)

- **JSONB codec** — asyncpg 는 JSONB 를 기본 `str` 로 준다. `pg._init_conn` 의 codec 이
  없으면 `input_payload` 가 문자열로 돌아오고 `isinstance(x, dict)` 분기가 전부 조용히
  폴백한다(계획 3대 리스크 1순위).
- **TIMESTAMPTZ str 바인딩** — `now_kst_iso()`(str)를 넘기면 **mock 은 전건 초록**인데 실
  PG 에서만 `DataError` 다(cycle273a HIGH#1). 이 파일이 그 차이를 잰다.
- **DATE str 바인딩** — 같은 계열(M6 라이브 핫픽스).
- **재적용 idempotency** — CI/deploy 가 같은 DB 에 전 마이그레이션을 **반복 적용**한다.
  `IF NOT EXISTS` 가 빠지면 두 번째 적용부터 조용히 실패한다.
- **NUMERIC → Decimal** — 라우트가 `float` 사영을 해야 하는 이유의 원천(cycle266 흰 화면).

docker / `DATABASE_URL_TEST` 가 없으면 `pg_harness` fixture 가 `pytest.skip` 한다(통합은 옵셔널).

## 격리 fixture

`clean_llm_buy_evaluations` 는 이 파일에 지역 정의한다 — 기존 `pg_harness.py` 의 `clean_<table>`
관례를 따르되, Green 이 그 파일로 옮겨도 이름이 같아 충돌하지 않는다(옮기면 이 정의를 지운다).
`pg_harness._apply_migrations` 는 `*.sql` glob 이라 043 이 생기면 **자동으로** 적용된다.
"""

from __future__ import annotations

import importlib
import json
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.slow]

KST = timezone(timedelta(hours=9))

_ROOT = Path(__file__).resolve().parents[2]
_MIGRATION_043 = _ROOT / "supabase" / "migrations" / "043_llm_buy_evaluations.sql"

_DB_MOD = "src.db.llm_buy_evaluations"
_TABLE = "llm_buy_evaluations"

_TRADE_DATE = date(2026, 9, 11)
_TRADE_DATE_STR = "2026-09-11"
_ORDER_KST = datetime(2026, 9, 11, 9, 1, 31, 32000, tzinfo=KST)
_EVALUATED_AT = datetime(2026, 9, 11, 9, 1, 34, 512000, tzinfo=KST)

_ACCOUNT = "12345678"
_TICKER = "005930"
_ORDER_NO = "0000123456"

_PAYLOAD = {
    "payload": {"ticker": _TICKER, "order_kst": "09:01:31", "board": "main"},
    "tech": {"rsi14": 61.2, "pos_in_ch20_pct": 88.0},
    "bars30": [[20260910, 71000, 71900, 70800, 71500, 1234567]],
}


def _mod():
    """`src.db.llm_buy_evaluations` — 부재면 `ModuleNotFoundError`(= 정직한 Red)."""
    return importlib.import_module(_DB_MOD)


@pytest.fixture
async def clean_llm_buy_evaluations(pg_pool):
    """`llm_buy_evaluations` 를 비운 상태로 시작·종료 (테스트 격리).

    ⚠️ 테이블 부재(=043 미작성, Red 시점)는 **삼킨다** — 여기서 던지면 전 케이스가
    setup `ERROR` 로 보고돼 "실패한 계약" 과 "돌려보지도 못한 계약" 이 구별되지 않는다.
    테이블이 없다는 사실은 각 테스트 **본문**에서 정직한 `FAILED` 로 드러난다.
    """
    async def _wipe():
        try:
            await pg_pool.execute(f"DELETE FROM {_TABLE}")
        except Exception:
            pass

    await _wipe()
    yield pg_pool
    await _wipe()


def _kwargs(**over) -> dict:
    kw = dict(
        trade_date=_TRADE_DATE,
        account_no=_ACCOUNT,
        ticker=_TICKER,
        order_no=_ORDER_NO,
        eval_kind="order",
        account_product="01",
        strategy_id="volatility_breakout",
        mode="shadow",
        result="ok",
        reason=None,
        score=62,
        min_score=70,
        would_block=True,
        rationale="돌파 초과가 얇다",
        key_risks=["되돌림"],
        invalidations=["목표가 이탈"],
        model="gpt-5.6-luna",
        tokens_in=3120,
        tokens_out=210,
        cost_usd=0.004380,
        latency_ms=3120,
        verdict_lag_ms=3480,
        eval_to_order_lag_ms=3480,
        order_kst=_ORDER_KST,
        evaluated_at=_EVALUATED_AT,
        order_price_won=71_800,
        ordered_qty=3,
        order_notional_won=215_400,
        order_division="MARKET",
        order_path="market",
        exchange="KRX",
        board="main",
        current_price_won=71_800,
        signal_matched=True,
        signal_price_won=71_800,
        signal_time_local="09:01:31",
        strategy_board="main",
        target_won=71_650,
        k=0.5,
        breakout_excess_bp=20.9,
        post_order_drift_bp=-13.9,
        drift_price_won=71_700,
        tick_age_s=1.2,
        budget_total_won=247_949,
        budget_remaining_after_won=32_549,
        open_positions_n=1,
        prompt_version="a1b2c3d4e5f6",
        feature_version="0f1e2d3c4b5a",
        bars_count=59,
        input_payload=_PAYLOAD,
        raw_response={"content": "{\"score\":62}"},
    )
    kw.update(over)
    return kw


# ===========================================================================
# B105 — 마이그레이션 재적용 idempotency
# ===========================================================================
async def test_i1_migration_043_applies_twice_without_error(pg_pool):
    """C31 (뮤테이션 M13) — 043 을 **두 번** 실행해도 오류 0.

    `deploy.yml` 은 매 push 마다 전 마이그레이션을 재적용하고 `ON_ERROR_STOP=0 + || true`
    로 오류를 삼킨다 — idempotent 가 아니면 두 번째 배포부터 **조용히** 실패하고 운영에는
    테이블이 없는 채로 남는다(031·042 선례).
    """
    assert _MIGRATION_043.exists(), "043_llm_buy_evaluations.sql 이 없다(Red)"
    sql = _MIGRATION_043.read_text(encoding="utf-8")
    await pg_pool.execute(sql)
    await pg_pool.execute(sql)   # 재적용 — 예외가 나면 여기서 죽는다

    row = await pg_pool.fetchrow(
        "SELECT count(*) AS n FROM information_schema.tables WHERE table_name = $1", _TABLE
    )
    assert row["n"] == 1, "테이블이 만들어지지 않았다"


async def test_i2_indexes_exist_after_migration(pg_pool):
    """§2 — 인덱스 4개가 실제로 만들어졌다(이름 오타는 실 DB 에서만 드러난다)."""
    rows = await pg_pool.fetch(
        "SELECT indexname FROM pg_indexes WHERE tablename = $1", _TABLE
    )
    names = {r["indexname"] for r in rows}
    for idx in ("idx_llm_eval_trade_date", "idx_llm_eval_strategy_date",
                "idx_llm_eval_ticker_date", "idx_llm_eval_order_no"):
        assert idx in names, f"인덱스 `{idx}` 가 실 DB 에 없다 (있는 것: {sorted(names)})"


# ===========================================================================
# B106~B108 — 타입 왕복
# ===========================================================================
async def test_i3_upsert_roundtrip_jsonb_dict_in_dict_out(clean_llm_buy_evaluations):
    """C34/C36 — `input_payload` dict → **dict** 복원(JSONB codec 실증).

    문자열로 돌아오면 훗날 오프라인 재채점이 `json.loads` 한 겹을 더 벗겨야 하고,
    그 사실을 아무도 기록해 두지 않는다.
    """
    mod = _mod()
    await mod.upsert_evaluation(**_kwargs())
    row = await mod.get_by_order(_ORDER_NO)

    assert row is not None, "저장한 행을 다시 읽지 못했다"
    payload = row["input_payload"]
    assert isinstance(payload, dict), f"JSONB 가 {type(payload).__name__} 로 돌아왔다 — codec 미등록"
    assert payload["tech"]["rsi14"] == 61.2
    assert payload["bars30"][0][0] == 20260910
    assert isinstance(row["key_risks"], list) and row["key_risks"] == ["되돌림"]
    assert isinstance(row["raw_response"], dict)


async def test_i4_upsert_roundtrip_date_column(clean_llm_buy_evaluations):
    """C34 (M6) — `trade_date` 를 **문자열로 넘겨도** DATE 왕복이 성립한다.

    시정 전이었다면 asyncpg 가 `'str' object has no attribute 'toordinal'` 로 죽었다.
    """
    mod = _mod()
    await mod.upsert_evaluation(**_kwargs(trade_date=_TRADE_DATE_STR))
    row = await mod.get_by_order(_ORDER_NO)

    assert row is not None
    assert row["trade_date"] == _TRADE_DATE


async def test_i5_upsert_roundtrip_timestamptz_renders_kst(clean_llm_buy_evaluations):
    """C34 — `order_kst` 가 `+09:00` ISO 로 사영된다(프론트 렌더 계약의 원천).

    `pg.init_pool` 의 `server_settings` 가 세션 타임존을 KST 로 고정한다 — 그 배선이
    깨지면 `to_char(...,'+09:00')` 이 UTC 기준으로 렌더돼 **날짜가 하루 밀린다**
    (M2a 실측 사고).
    """
    mod = _mod()
    await mod.upsert_evaluation(**_kwargs())
    row = await mod.get_by_order(_ORDER_NO)

    assert row is not None
    iso = row.get("order_kst_iso")
    assert isinstance(iso, str) and iso.endswith("+09:00"), f"order_kst_iso={iso!r}"
    assert iso.startswith("2026-09-11T09:01:31"), f"KST 시각이 밀렸다: {iso!r}"
    assert isinstance(row["order_kst"], datetime)
    assert row["order_kst"].astimezone(KST).hour == 9


async def test_i6_str_timestamp_binding_is_rejected_by_pg(clean_llm_buy_evaluations, pg_pool):
    """C34 (cycle273a HIGH#1) — TIMESTAMPTZ 에 **str** 을 넘기면 실 PG 가 거부한다.

    이 케이스는 우리 코드가 아니라 **DB 의 성질**을 못박는다: mock 테스트가 str 바인딩을
    통과시키는 이유가 여기 있고, 그래서 `upsert_evaluation` 이 `datetime` 으로 강제해야 한다.
    """
    with pytest.raises(Exception) as exc:
        await pg_pool.execute(
            f"INSERT INTO {_TABLE} "
            "(trade_date, account_no, ticker, order_no, strategy_id, mode, result, "
            " min_score, order_kst, order_price_won, ordered_qty, order_notional_won, "
            " order_division, order_path, board) "
            "VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15)",
            _TRADE_DATE, _ACCOUNT, _TICKER, "STRBIND", "volatility_breakout", "shadow",
            "ok", 70, "2026-09-11T09:01:31+09:00", 71_800, 3, 215_400,
            "MARKET", "market", "main",
        )
    assert "str" in str(exc.value).lower() or "datetime" in str(exc.value).lower(), (
        f"예상과 다른 예외: {exc.value!r}"
    )


async def test_i14_str_timestamp_arg_survives_real_pg(clean_llm_buy_evaluations):
    """C34 — `upsert_evaluation(order_kst=now_kst_iso())`(**str**)가 실 PG 에서 성립한다.

    `test_i6` 은 DB 의 성질만 못박고 `upsert_evaluation` 의 변환 코드(`_to_dt`)를 한 번도
    지나가지 않는다 — 그래서 그 변환을 지운 뮤테이션이 전건 초록이었다(검증 라운드 3 #1).
    이 케이스는 문자열을 **모듈 경유**로 넣어 강제 변환이 실제로 일어나는지 잰다.
    """
    from src.db._kst import now_kst_iso

    mod = _mod()
    iso = now_kst_iso()
    await mod.upsert_evaluation(**_kwargs(order_kst=iso, evaluated_at=iso))
    row = await mod.get_by_order(_ORDER_NO)

    assert row is not None, "str 시각 인자로 저장한 행을 읽지 못했다"
    assert isinstance(row["order_kst"], datetime), (
        f"order_kst={type(row['order_kst']).__name__} — TIMESTAMPTZ 왕복이 깨졌다"
    )
    out = row.get("order_kst_iso")
    assert isinstance(out, str) and out.endswith("+09:00"), f"order_kst_iso={out!r}"
    assert out.startswith(iso[:19]), f"KST 시각이 밀렸다: 넣은 값 {iso!r} → 읽은 값 {out!r}"


async def test_i15_unsupported_timestamp_type_raises_typeerror(clean_llm_buy_evaluations, pg_pool):
    """C34 — TIMESTAMPTZ 에 미지 타입(int)이 오면 **TypeError**(asyncpg `DataError` 아님).

    조용히 흘려보내면 `_persist_evaluation` 이 흡수해 `reason=DataError` 한 줄만 남고
    어느 열이 문제인지 잃는다. 던지는 예외의 **정체**가 계약이다.
    """
    mod = _mod()
    with pytest.raises(TypeError) as exc:
        await mod.upsert_evaluation(**_kwargs(order_no="INTBIND", evaluated_at=5))

    assert "TIMESTAMPTZ" in str(exc.value), f"예상과 다른 예외: {exc.value!r}"
    row = await pg_pool.fetchrow(
        f"SELECT count(*) AS n FROM {_TABLE} WHERE order_no = $1", "INTBIND"
    )
    assert row["n"] == 0, "타입 위반인데 행이 들어갔다"


async def test_i7_numeric_returns_decimal(clean_llm_buy_evaluations):
    """C34/§4 — `NUMERIC` 열은 `Decimal` 로 돌아온다.

    이것이 라우트가 `float` 사영을 해야 하는 이유다 — pydantic v2 가 `Decimal` 을
    JSON 문자열로 내보내면 프론트의 `toFixed` 가 죽는다(cycle266).
    """
    mod = _mod()
    await mod.upsert_evaluation(**_kwargs())
    row = await mod.get_by_order(_ORDER_NO)

    assert row is not None
    assert isinstance(row["cost_usd"], Decimal), f"cost_usd={type(row['cost_usd']).__name__}"
    assert isinstance(row["k"], Decimal)
    assert isinstance(row["post_order_drift_bp"], Decimal)
    assert float(row["post_order_drift_bp"]) == pytest.approx(-13.9)


# ===========================================================================
# B110 — PK upsert
# ===========================================================================
async def test_i8_conflict_updates_instead_of_duplicating(clean_llm_buy_evaluations, pg_pool):
    """C32 — 같은 PK 로 두 번 쓰면 **1행**이고 값이 갱신된다(`created_at` 은 보존).

    평가는 주문당 1회지만 재시도·재기동이 같은 PK 를 다시 쓸 수 있다 — 그때 행이
    불어나면 회고분석의 분모가 조용히 부푼다.
    """
    mod = _mod()
    await mod.upsert_evaluation(**_kwargs(score=62, result="ok"))
    first = await mod.get_by_order(_ORDER_NO)
    await mod.upsert_evaluation(**_kwargs(score=88, rationale="재평가"))

    rows = await pg_pool.fetch(f"SELECT * FROM {_TABLE} WHERE order_no = $1", _ORDER_NO)
    assert len(rows) == 1, f"같은 PK 로 {len(rows)}행이 생겼다"
    assert rows[0]["score"] == 88
    assert rows[0]["rationale"] == "재평가"
    assert rows[0]["created_at"] == first["created_at"], "`created_at` 이 갱신에 밀렸다"


async def test_i9_same_order_no_on_two_dates_are_two_rows(clean_llm_buy_evaluations, pg_pool):
    """C32 — KIS ODNO 는 **하루 단위로만** 유일하다 → 날짜가 다르면 별개 행이다.

    PK 에서 `trade_date` 를 빼면(뮤테이션 M11) 다음 날 같은 주문번호가 어제 행을 덮는다.
    """
    mod = _mod()
    await mod.upsert_evaluation(**_kwargs(trade_date=date(2026, 9, 10)))
    await mod.upsert_evaluation(**_kwargs(trade_date=date(2026, 9, 11)))

    rows = await pg_pool.fetch(f"SELECT * FROM {_TABLE} WHERE order_no = $1", _ORDER_NO)
    assert len(rows) == 2, f"날짜가 다른 두 평가가 {len(rows)}행이다"

    latest = await mod.get_by_order(_ORDER_NO)
    assert latest["trade_date"] == date(2026, 9, 11), "날짜 미지정 조회가 최신을 고르지 않았다"

    narrowed = await mod.get_by_order(_ORDER_NO, trade_date=date(2026, 9, 10))
    assert narrowed["trade_date"] == date(2026, 9, 10)


async def test_i10_list_by_order_nos_batch(clean_llm_buy_evaluations):
    """§4 — 배치 조회가 존재하는 것만 돌려준다(없는 번호는 결과에서 그냥 빠진다)."""
    mod = _mod()
    await mod.upsert_evaluation(**_kwargs(order_no="AAA"))
    await mod.upsert_evaluation(**_kwargs(order_no="BBB", ticker="000660"))

    rows = await mod.list_by_order_nos(["AAA", "BBB", "ZZZ"])
    assert {r["order_no"] for r in rows} == {"AAA", "BBB"}
    assert await mod.list_by_order_nos([]) == []


# ===========================================================================
# B111 — `trade_history` 3축 조인 + 체결 상태 분류
# ===========================================================================
async def test_i11_join_with_trade_history_three_axes(
    clean_llm_buy_evaluations, clean_trade_history, pg_pool
):
    """§9.3 (자문 R4) — 조인은 `(trade_date, ticker, order_no)` **3축**이다.

    그리고 `trade_history.status` 를 함께 읽어 **체결/부분체결/취소/미체결**을 분리한다 —
    미체결을 손익 0 으로 섞으면 회고 회귀가 통째로 오염된다.
    """
    mod = _mod()
    statuses = {
        "F-COMPLETED": "COMPLETED",
        "F-PARTIAL": "PARTIAL",
        "F-CANCELLED": "CANCELLED",
        "F-PENDING": "PENDING",
    }
    for order_no, status in statuses.items():
        await mod.upsert_evaluation(**_kwargs(order_no=order_no))
        await pg_pool.execute(
            "INSERT INTO trade_history "
            "(ticker, ticker_name, trade_type, price, quantity, status, strategy, "
            " order_no, timestamp) "
            "VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)",
            _TICKER, "삼성전자", "BUY", 71_800, 3, status, "volatility_breakout",
            order_no, _ORDER_KST,
        )

    rows = await pg_pool.fetch(
        f"""
        SELECT e.order_no, t.status
          FROM {_TABLE} e
          JOIN trade_history t
            ON t.ticker = e.ticker
           AND t.order_no = e.order_no
           AND t.trade_type = 'BUY'
           AND (t.timestamp AT TIME ZONE 'Asia/Seoul')::date = e.trade_date
         WHERE e.trade_date = $1
        """,
        _TRADE_DATE,
    )
    got = {r["order_no"]: r["status"] for r in rows}
    assert got == statuses, f"3축 조인 결과가 다르다: {got}"


async def test_i12_all_53_columns_exist_in_live_table(pg_pool):
    """§3 — 실 DB 열 전수 확인(SQL 텍스트 검사만으로는 오타·타입 오류를 못 잡는다)."""
    rows = await pg_pool.fetch(
        "SELECT column_name FROM information_schema.columns WHERE table_name = $1", _TABLE
    )
    names = {r["column_name"] for r in rows}
    expected = {
        "trade_date", "account_no", "ticker", "order_no", "eval_kind", "account_product",
        "strategy_id", "mode", "result", "reason", "score", "min_score", "would_block",
        "rationale", "key_risks", "invalidations", "model", "tokens_in", "tokens_out",
        "cost_usd", "latency_ms", "verdict_lag_ms", "eval_to_order_lag_ms", "order_kst",
        "evaluated_at", "order_price_won", "ordered_qty", "order_notional_won",
        "order_division", "order_path", "exchange", "board", "current_price_won",
        "signal_matched", "signal_price_won", "signal_time_local", "strategy_board",
        "target_won", "k", "breakout_excess_bp", "post_order_drift_bp", "drift_price_won",
        "tick_age_s", "budget_total_won", "budget_remaining_after_won", "open_positions_n",
        "prompt_version", "feature_version", "bars_count", "input_payload", "raw_response",
        "created_at", "updated_at",
    }
    assert len(expected) == 53
    assert expected <= names, f"실 DB 에 없는 열: {sorted(expected - names)}"


async def test_i13_failed_row_keeps_payload_and_null_score(clean_llm_buy_evaluations):
    """브리프 §3.4 (뮤테이션 M9/M10) — 실패 행도 **payload 를 담고** 점수는 NULL 이다.

    실패야말로 훗날 재채점 대상이다. 점수를 0 으로 위장하면 분포가 0 근처로 왜곡된다.
    """
    mod = _mod()
    await mod.upsert_evaluation(**_kwargs(
        result="failed", reason="timeout", score=None, would_block=None,
        rationale=None, key_risks=None, invalidations=None, raw_response=None,
    ))
    row = await mod.get_by_order(_ORDER_NO)

    assert row is not None
    assert row["result"] == "failed" and row["reason"] == "timeout"
    assert row["score"] is None and row["would_block"] is None
    assert isinstance(row["input_payload"], dict) and row["input_payload"]
    json.dumps(row["input_payload"])


# ===========================================================================
# cycle276 후속 B-2 / B-4 — 실 PG 로만 잡히는 두 계약
# ===========================================================================
async def test_i16_batch_returns_both_dates_for_same_order_no(clean_llm_buy_evaluations):
    """B-2 — 같은 주문번호가 **두 날짜**에 있으면 배치 조회가 둘 다 돌려준다.

    KIS ODNO 는 하루 단위로만 유일하다(PK 선두가 `trade_date` 인 이유). 종전 구현은
    `trade_date DESC` 첫 등장만 남겨 09-08 행을 지웠고, 그 날짜의 거래 행은 버튼이
    비활성인데 상세 조회(`get_by_order(..., trade_date="2026-09-08")`)로는 멀쩡히
    읽혔다 — 실 PG 로 재현한 그 비대칭을 여기서 잠근다.
    """
    mod = _mod()
    older = date(2026, 9, 8)
    await mod.upsert_evaluation(**_kwargs(score=62))
    await mod.upsert_evaluation(**_kwargs(
        trade_date=older, score=88,
        order_kst=_ORDER_KST.replace(day=8), evaluated_at=_EVALUATED_AT.replace(day=8),
    ))

    rows = await mod.list_by_order_nos([_ORDER_NO])
    pairs = {(r["trade_date"], r["score"]) for r in rows}
    assert pairs == {(_TRADE_DATE, 62), (older, 88)}, f"실측 {sorted(pairs)}"

    # 상세도 날짜별로 각각 읽힌다 = 배치와 상세의 날짜 축이 같다.
    newer_row = await mod.get_by_order(_ORDER_NO, trade_date=_TRADE_DATE_STR)
    older_row = await mod.get_by_order(_ORDER_NO, trade_date="2026-09-08")
    assert newer_row is not None and newer_row["score"] == 62
    assert older_row is not None and older_row["score"] == 88

    # 날짜로 좁힌 배치는 그 날짜 1행만.
    only_older = await mod.list_by_order_nos([_ORDER_NO], trade_date="2026-09-08")
    assert [r["score"] for r in only_older] == [88]


async def test_i17_signal_time_column_is_not_named_kst(pg_pool):
    """B-4 — 열 이름은 `signal_time_local` 이고 `signal_time_kst` 는 **없다**.

    그 열이 담는 값은 전략의 `datetime.now()`(6전략, tz 인자 없음)가 만든 tz-naive 로컬
    시각 문자열이다. EC2 컨테이너의 `TZ=Asia/Seoul` 전제에서만 KST 와 같고 값 자체는
    KST 를 **보장하지 않는다** — 이름이 사실과 다르면 훗날 그 문자열을 KST 로 단정해
    파싱하는 코드가 붙는다(마이그레이션 043 은 아직 운영 미적용이라 개명 비용 0).
    """
    rows = await pg_pool.fetch(
        "SELECT column_name FROM information_schema.columns WHERE table_name = $1", _TABLE
    )
    names = {r["column_name"] for r in rows}
    assert "signal_time_local" in names, "`signal_time_local` 열이 없다"
    assert "signal_time_kst" not in names, "구 이름 `signal_time_kst` 가 남아 있다"
