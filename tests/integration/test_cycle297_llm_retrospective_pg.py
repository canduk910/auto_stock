"""cycle297 Red — G5: 실 Postgres 왕복 — `get_trade_pairs` ↔ `llm_buy_evaluations` 조인.

명세 = `_workspace/red/cycle297_llm_gate_all_strategies_spec.md` §3.5 · §5.1 G5.

**Red 단계 — 테스트만. `src/` 미변경.** Green = backend-dev.

## 왜 실 PG 인가 (목으로는 못 잡는 것)

- **`buy_order_nos` 는 페어링 알고리즘의 산출물이다.** 목으로 "매수 2건 페어" 를 손으로
  만들면 실제 `get_trade_pairs` 가 그 모양을 만드는지 한 번도 검증하지 않게 된다 —
  cycle266 이 3개월 은폐로 실증한 목 괴리 패턴이다. 한 페어 매수 2건 이상은 운영 DB
  실측 9건이라 가설이 아니라 사실이다.
- **날짜 타입.** `trade_date` 는 DATE 컬럼이라 asyncpg 가 `datetime.date` 로 주는데
  `get_trade_pairs` 의 `sell_date` 는 `_to_kst` 산출 **문자열**이다. 두 축을 비교하는
  코드가 목에서는 둘 다 문자열이라 통과하고 실 PG 에서만 터진다(cycle273a HIGH 와 동형).
- **TIMESTAMPTZ 바인딩.** `timestamp` 를 str 로 넘기면 목은 전건 초록, 실 PG 는 `DataError`.

docker / `DATABASE_URL_TEST` 가 없으면 `pg_harness` fixture 가 `pytest.skip` 한다(통합은 옵셔널).
"""

from __future__ import annotations

import importlib
from datetime import date, datetime, timedelta, timezone

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.slow]

KST = timezone(timedelta(hours=9))

_RETRO_MOD = "src.engine.llm_retrospective"
_TRADE_DB_MOD = "src.db.trade_history"
_EVAL_DB_MOD = "src.db.llm_buy_evaluations"

_TICKER = "005930"
_STRATEGY = "donchian_swing"
_ACCOUNT = "12345678"

_BUY_ONO_1 = "0000123456"
_BUY_ONO_2 = "0000123457"
_SELL_ONO = "0000999999"

_BUY_DATE = date(2026, 9, 11)
_SELL_DATE = date(2026, 9, 15)
_OTHER_DATE = date(2026, 8, 20)      # 같은 주문번호의 **다른 날짜** 평가

_SINCE = "2026-09-10"
_UNTIL = "2026-09-17"


def _retro():
    return importlib.import_module(_RETRO_MOD)


@pytest.fixture
async def clean_retro_tables(pg_pool):
    """`trade_history` + `llm_buy_evaluations` 격리.

    `pg_harness.py` 로 옮겨도 이름이 같아 충돌하지 않는다(옮기면 이 정의를 지운다).
    """
    await pg_pool.execute("DELETE FROM llm_buy_evaluations")
    await pg_pool.execute("DELETE FROM trade_history")
    yield pg_pool
    await pg_pool.execute("DELETE FROM llm_buy_evaluations")
    await pg_pool.execute("DELETE FROM trade_history")


async def _insert_trade(pool, *, trade_type, order_no, price, qty, ts: datetime, status="COMPLETED"):
    await pool.execute(
        "INSERT INTO trade_history "
        "(ticker, ticker_name, trade_type, price, quantity, strategy, status, order_no, timestamp) "
        "VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)",
        _TICKER, "삼성전자", trade_type, price, qty, _STRATEGY, status, order_no, ts,
    )


async def _insert_eval(*, order_no, trade_date, score, would_block, prompt_version="pv0000000001"):
    """`upsert_evaluation` 필수 인자 전부를 채운다(043 의 NOT NULL 축)."""
    db = importlib.import_module(_EVAL_DB_MOD)
    await db.upsert_evaluation(
        trade_date=trade_date,
        account_no=_ACCOUNT,
        ticker=_TICKER,
        order_no=order_no,
        strategy_id=_STRATEGY,
        mode="shadow",
        result="ok",
        score=score,
        min_score=70,
        would_block=would_block,
        order_kst=datetime(2026, 9, 11, 9, 5, 12, tzinfo=KST),
        order_price_won=80_000,
        ordered_qty=10,
        order_notional_won=800_000,
        order_division="01",
        order_path="primary",
        board="main",
        prompt_version=prompt_version,
        feature_version="fv0000000001",
        model="gpt-5.6-luna",
        input_payload={"payload": {"ticker": _TICKER}},
    )


# ===========================================================================
# G5-1 — 한 페어 매수 2건 → 평가 2개, primary = 첫 매수
# ===========================================================================
async def test_g5_1_two_buys_one_sell_joins_both_evaluations(clean_retro_tables) -> None:
    """G5-1 — 실 `get_trade_pairs` 가 만든 `buy_order_nos` 로 조인이 성립한다.

    **양성 대조군** = 페어가 정확히 1건이고 `buy_order_nos` 가 시간 오름차순 2개인지
    먼저 확인한다 — 페어링 자체가 깨지면 조인 단언이 공허해진다.
    """
    pool = clean_retro_tables
    trade_db = importlib.import_module(_TRADE_DB_MOD)

    await _insert_trade(pool, trade_type="BUY", order_no=_BUY_ONO_1, price=80_000, qty=10,
                        ts=datetime(2026, 9, 11, 9, 5, 12, tzinfo=KST))
    await _insert_trade(pool, trade_type="BUY", order_no=_BUY_ONO_2, price=81_000, qty=5,
                        ts=datetime(2026, 9, 11, 9, 20, 3, tzinfo=KST))
    await _insert_trade(pool, trade_type="SELL", order_no=_SELL_ONO, price=77_200, qty=15,
                        ts=datetime(2026, 9, 15, 10, 31, 2, tzinfo=KST))

    pairs = await trade_db.get_trade_pairs()
    closed = [p for p in pairs if p["status"] == "closed"]
    assert len(closed) == 1, f"페어링이 기대와 다르다 — {pairs}"
    assert closed[0]["buy_order_nos"] == [_BUY_ONO_1, _BUY_ONO_2]

    await _insert_eval(order_no=_BUY_ONO_1, trade_date=_BUY_DATE, score=42, would_block=True)
    await _insert_eval(order_no=_BUY_ONO_2, trade_date=_BUY_DATE, score=88, would_block=False)

    eval_db = importlib.import_module(_EVAL_DB_MOD)
    ev_rows = await eval_db.list_by_order_nos([_BUY_ONO_1, _BUY_ONO_2])
    assert len(ev_rows) == 2

    rows = _retro().join_pairs_with_evaluations(
        closed, ev_rows, since_date=_SINCE, until_date=_UNTIL
    )
    assert len(rows) == 1
    assert {e["order_no"] for e in rows[0]["evaluations"]} == {_BUY_ONO_1, _BUY_ONO_2}
    assert rows[0]["primary"]["order_no"] == _BUY_ONO_1
    assert rows[0]["primary"]["score"] == 42


# ===========================================================================
# G5-2 — 같은 주문번호의 다른 날짜 평가는 붙지 않는다
# ===========================================================================
async def test_g5_2_same_order_no_different_date_is_not_attached(clean_retro_tables) -> None:
    """G5-2 (M17, 실 PG) — DATE 컬럼과 `_to_kst` 문자열의 **타입 경계**를 함께 잰다.

    목에서는 양쪽이 문자열이라 통과하는 비교가 여기서는 `date` vs `str` 이다 —
    정규화를 빼먹은 구현은 "아무것도 안 붙는다"(전건 `primary=None`)로 조용히 실패한다.
    """
    pool = clean_retro_tables
    trade_db = importlib.import_module(_TRADE_DB_MOD)
    eval_db = importlib.import_module(_EVAL_DB_MOD)

    await _insert_trade(pool, trade_type="BUY", order_no=_BUY_ONO_1, price=80_000, qty=10,
                        ts=datetime(2026, 9, 11, 9, 5, 12, tzinfo=KST))
    await _insert_trade(pool, trade_type="SELL", order_no=_SELL_ONO, price=77_200, qty=10,
                        ts=datetime(2026, 9, 15, 10, 31, 2, tzinfo=KST))

    # 같은 ODNO 가 3주 전에도 있었다(KIS ODNO 는 하루 단위로만 유일하다).
    await _insert_eval(order_no=_BUY_ONO_1, trade_date=_OTHER_DATE, score=91, would_block=False)
    await _insert_eval(order_no=_BUY_ONO_1, trade_date=_BUY_DATE, score=42, would_block=True)

    pairs = [p for p in await trade_db.get_trade_pairs() if p["status"] == "closed"]
    ev_rows = await eval_db.list_by_order_nos([_BUY_ONO_1])
    assert len(ev_rows) == 2, "두 날짜 행이 둘 다 조회돼야 한다(접지 않는다)"

    rows = _retro().join_pairs_with_evaluations(
        pairs, ev_rows, since_date=_SINCE, until_date=_UNTIL
    )
    primary = rows[0]["primary"]
    assert primary is not None, "올바른 날짜 평가가 붙지 않았다 — date/str 정규화 누락 의심"
    assert primary["score"] == 42, f"08-20 행(score=91)이 붙었다 — {primary}"


# ===========================================================================
# G5-3 — 라우트 왕복 (실 풀 + TestClient)
# ===========================================================================
async def test_g5_3_route_roundtrip_returns_200_without_account_no(clean_retro_tables) -> None:
    """G5-3 — 실 DB 를 붙인 채 회고 라우트 핸들러가 200(형) 응답을 만든다.

    순수 함수 단위 테스트(G3)와 목 라우트 테스트(G4) 사이의 배관이 실제로 이어지는지
    — `get_trade_pairs()` 를 부르고, `buy_order_nos` 합집합으로 `list_by_order_nos()` 를
    부르고, leaf 로 넘기는 그 순서 — 를 한 번 태워 확인한다.

    ⚠️ **`TestClient` 가 아니라 라우트 함수를 직접 `await` 한다** — `TestClient` 는
    anyio 로 별도 이벤트 루프를 띄우는데 `pg_pool` fixture 가 연 asyncpg 풀은 이
    테스트 함수의 루프에 귀속돼 있어 `attached to a different loop` 로 죽는다
    (cycle285 `test_c285_pg_4_route_end_to_end_over_real_pg` 의 동일 관례 — 실측
    확인됨, `_workspace/red/cycle297_llm_gate_all_strategies_spec.md` G5 계약은
    "라우트 왕복" 이지 "TestClient 경유" 가 아니다).
    """
    pool = clean_retro_tables
    await _insert_trade(pool, trade_type="BUY", order_no=_BUY_ONO_1, price=80_000, qty=10,
                        ts=datetime(2026, 9, 11, 9, 5, 12, tzinfo=KST))
    await _insert_trade(pool, trade_type="SELL", order_no=_SELL_ONO, price=77_200, qty=10,
                        ts=datetime(2026, 9, 15, 10, 31, 2, tzinfo=KST))
    await _insert_eval(order_no=_BUY_ONO_1, trade_date=_BUY_DATE, score=42, would_block=True)

    route = importlib.import_module("src.routes.llm_evaluations")

    resp = await route.llm_evaluation_retrospective(days=90, cost_pct=0.25, strategy=None)

    assert resp.success is True
    body = resp.model_dump_json() if hasattr(resp, "model_dump_json") else str(resp.data)
    assert _ACCOUNT not in body, "실 DB 왕복 응답에 계좌번호가 실렸다"
    data = resp.data
    assert data["aggregate"]["overall"]["n_pairs"] >= 1
