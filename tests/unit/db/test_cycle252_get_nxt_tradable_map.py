"""cycle252 Red — `stock_master.get_nxt_tradable_map()` 벌크 조회.

> 정본 명세: `spec_cycle252_no_feed_churn.md` §2 (src/db/stock_master.py) / §3 D1~D3

`no_feed_registry.ensure_fresh` 가 120s hot path 에서 쓰는 유일한 DB 창구다.
구독 종목 ~200개를 **단건 조회 200회**로 읽으면 K watcher 주기 자체가 무너지므로
`= ANY($1::text[])` 벌크 1회가 계약이다.

| ID | 계약 |
|----|------|
| D1 | SQL 에 `stock_master` · `nxt_tradable` · `= ANY(` 포함 + 인자는 list 1개 |
| D2 | 반환 dict 는 **요청 ticker 전부**가 키 (DB 미존재 = `None`) |
| D3 | 빈 입력 → `{}` 이고 `pg.fetch` **미호출** |

D2 가 핵심이다 — 반환에서 빠진 ticker 를 호출자가 "no_feed 아님" 으로 볼지
"미지" 로 볼지 갈리면 `_known` 이 매 사이클 쪼개져 무한 재조회가 된다.
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit


def _func():
    import src.db.stock_master as sm

    fn = getattr(sm, "get_nxt_tradable_map", None)
    if fn is None:  # pragma: no cover - Red 단계 경로
        pytest.fail(
            "cycle252 §2 — `src/db/stock_master.py::get_nxt_tradable_map` 미정의"
        )
    return fn


class _FetchSpy:
    def __init__(self, rows: list[dict] | None = None):
        self.rows = rows or []
        self.calls: list[tuple] = []

    async def __call__(self, sql: str, *args):
        self.calls.append((sql, args))
        return self.rows


@pytest.fixture
def spy(monkeypatch):
    import src.db.pg as pg

    s = _FetchSpy()
    monkeypatch.setattr(pg, "fetch", s)
    return s


# ===========================================================================
# D1 — SQL 형태 + 인자 전달
# ===========================================================================
async def test_d1_sql_uses_any_array_bulk_lookup(spy):
    """단건 반복이 아니라 배열 바인딩 1회."""
    fn = _func()
    spy.rows = [
        {"ticker": "003490", "nxt_tradable": False},
        {"ticker": "005930", "nxt_tradable": True},
    ]

    await fn(["003490", "005930"])

    assert len(spy.calls) == 1, (
        f"벌크 1회 — 단건 반복 금지 (actual pg.fetch 호출={len(spy.calls)})"
    )
    sql, args = spy.calls[0]
    assert "stock_master" in sql, f"SQL 에 stock_master 부재: {sql!r}"
    assert "nxt_tradable" in sql, f"SQL 에 nxt_tradable 부재: {sql!r}"
    assert "= ANY(" in sql, (
        "배열 바인딩 `= ANY($1::text[])` 필수 — IN 문자열 조립은 인젝션·플랜 캐시 "
        f"양쪽에서 열등하다. actual={sql!r}"
    )
    assert len(args) == 1, f"인자는 배열 1개 — actual={args!r}"
    assert isinstance(args[0], list), (
        f"asyncpg text[] 바인딩은 list — actual type={type(args[0]).__name__}"
    )
    assert args[0] == ["003490", "005930"], f"인자 내용 불일치 — actual={args[0]!r}"


# ===========================================================================
# D2 — 요청 ticker 전부가 키 (부재 = None)
# ===========================================================================
async def test_d2_result_covers_every_requested_ticker(spy):
    """DB 에 없는 ticker(신규 상장·마스터 미적재)는 **키는 있고 값이 None**.

    키 자체를 빠뜨리면 `no_feed_registry._known` 이 그 종목을 영원히 미지로 보고
    매 사이클 재조회한다(TTL 무력화).
    """
    fn = _func()
    spy.rows = [
        {"ticker": "003490", "nxt_tradable": False},
        {"ticker": "005930", "nxt_tradable": True},
    ]

    result = await fn(["003490", "005930", "999999"])

    assert set(result.keys()) == {"003490", "005930", "999999"}, (
        f"요청 ticker 전부가 키여야 한다 — actual keys={sorted(result.keys())}"
    )
    assert result["003490"] is False
    assert result["005930"] is True
    assert result["999999"] is None, (
        f"마스터 부재는 None (False 아님) — actual={result['999999']!r}"
    )


async def test_d2b_extra_rows_from_db_do_not_leak(spy):
    """요청하지 않은 ticker 가 응답에 섞여도 결과에 넣지 않는다(계약 = 요청 집합)."""
    fn = _func()
    spy.rows = [
        {"ticker": "003490", "nxt_tradable": False},
        {"ticker": "000660", "nxt_tradable": True},  # 요청 밖
    ]

    result = await fn(["003490"])

    assert set(result.keys()) == {"003490"}, (
        f"요청 밖 ticker 누출 — actual keys={sorted(result.keys())}"
    )


# ===========================================================================
# D3 — 빈 입력 = 쿼리 0
# ===========================================================================
async def test_d3_empty_input_skips_query(spy):
    """`= ANY('{}')` 로 DB 왕복을 낭비하지 않는다."""
    fn = _func()

    result = await fn([])

    assert result == {}, f"빈 입력 → 빈 dict — actual={result!r}"
    assert spy.calls == [], (
        f"빈 입력에 pg.fetch 호출 금지 — actual 호출={len(spy.calls)}"
    )
