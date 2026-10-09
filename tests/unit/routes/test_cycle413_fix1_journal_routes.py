"""cycle413 보완 1차 Red — 거래일지 라우트 `GET /api/history/journal` 결함 회귀(라우트 단위, 빠른 판).

판정 원문 = scratchpad `c413/fix/verdict1.md` #1·#8 · 명세 = `_workspace/red/cycle413/journal_view_spec.md` 1-1절.
실 Postgres 판(실 UUID + `trade_cost_daily`)은 `tests/integration/test_cycle413_fix1_journal_pg.py` 다 — 이 파일은
같은 결함을 DB 없이 CI 전 구간에서 잡는다.

| # | 결함 → 계약 |
|---|---|
| F1 | 실 DB 는 `get_trade_pairs` 의 `*_trade_ids` 와 `trade_cost.get_trades_by_status` 의 `id` 를 **`uuid.UUID`** 로 준다. 라우트가 페어 id 를 문자열로 바꾼 **뒤** `overlay_pairs` 를 부르면 비용 맵(UUID 키)과 하나도 안 맞아 청산 카드 전부 수수료·세금 0 · 세후 = 세전 · 「추정」 이 된다. `/pnl` 과 같은 거래는 같은 숫자 — 카드 `net_krw` = `/pnl` `net_profit_loss` · `costs.status` = `cost_status` · `fee_total` = `entry_fee + Σexits.fee` = `/pnl` `fee` · 이익/손실 필터·손익 정렬도 그 세후 값으로 |
| F8 | 체결 행 조회(`get_trades_by_ids`)가 실패해도 카드 `opened_at`·`closed_at`·`held_days` 는 페어로 채우고(TS non-null) MFE/MAE 는 `lookup_failed` |

기존 단위 판(`test_cycle413_journal_routes.py`)은 id 를 처음부터 문자열로 넣어서 F1 을 못 잡았다 — 이 파일의
`db_uuid` 픽스처는 실 asyncpg 와 같은 타입(UUID)을 돌려준다. `get_trades_by_ids` 는 실 SQL 이 `id::text` 라 문자열 그대로.
"""

from __future__ import annotations

import importlib
import uuid

import pytest
from freezegun import freeze_time

from tests.unit.routes.test_cycle413_journal_routes import (  # noqa: F401 — `db` 는 픽스처 재사용
    FROZEN,
    T,
    _anchors,
    _card,
    _client,
    _get,
    _ok,
    db,
)

pytestmark = pytest.mark.unit

_ID_KEYS = ("buy_trade_ids", "sell_trade_ids", "partial_sell_trade_ids")


@pytest.fixture
def db_uuid(db, monkeypatch):  # noqa: F811 — 위에서 가져온 `db` 픽스처 위에 쌓는다
    """실 asyncpg 와 같은 id 타입 — 페어 id 목록·비용 원천 체결 행 id 가 `uuid.UUID`."""
    routes = importlib.import_module("src.routes.history")
    orig_pairs = routes.get_trade_pairs

    async def get_trade_pairs(strategy=None, ticker=None):
        rows = await orig_pairs(strategy=strategy, ticker=ticker)
        for p in rows:
            for k in _ID_KEYS:
                p[k] = [uuid.UUID(str(i)) for i in (p.get(k) or [])]
        return rows

    monkeypatch.setattr(routes, "get_trade_pairs", get_trade_pairs)

    tc = importlib.import_module("src.db.trade_cost")
    orig_status = tc.get_trades_by_status

    async def get_trades_by_status(start, end, statuses=("COMPLETED", "PARTIAL")):
        rows = await orig_status(start, end, statuses)
        for t in rows:
            t["id"] = uuid.UUID(str(t["id"]))
        return rows

    monkeypatch.setattr(tc, "get_trades_by_status", get_trades_by_status)
    return db


def _pnl_pairs():
    with freeze_time(FROZEN):
        body = _ok(_client().get("/api/history/pnl", params={"size": 200}))
    return {p["pair_key"]: p for p in body["pairs"]}


# ── F1 UUID 비용 키 ────────────────────────────────────────────────────────────

def test_f1_uuid_ids_card_costs_equal_pnl_route(db_uuid):
    j = _ok(_get(size=100))
    assert j["cost_available"] is True
    pairs = _pnl_pairs()
    checked = 0
    for c in j["cards"]:
        if c["status"] != "closed":
            continue
        p = pairs[c["pair_key"]]
        co = c["costs"]
        assert c["pnl"]["net_krw"] == pytest.approx(p["net_profit_loss"], abs=0.01), (
            f"{c['pair_key']}: 카드 세후 {c['pnl']['net_krw']} ≠ 매매손익 탭 {p['net_profit_loss']}")
        assert co["status"] == p["cost_status"], c["pair_key"]
        assert co["fee_total"] == pytest.approx(p["fee"], abs=0.01), c["pair_key"]
        assert co["tax_total"] == pytest.approx(p["tax"], abs=0.01), c["pair_key"]
        assert co["entry_fee"] + sum(x["fee"] for x in co["exits"]) == pytest.approx(co["fee_total"], abs=0.01)
        checked += 1
    assert checked == 4


def test_f1_uuid_ids_settled_pair_is_net_of_costs(db_uuid):
    """P1 BFB — 정산 수수료 701+764 · 세금 1,071 → 세후 41,464 [정산] (세전 44,000 이 아니다)."""
    c = _card(_ok(_get()), 1)
    assert c["pnl"]["gross_krw"] == 44000
    assert c["pnl"]["net_krw"] == pytest.approx(41464, abs=0.5), "세후가 세전과 같다 — 비용이 하나도 안 붙었다"
    co = c["costs"]
    assert co["status"] == "settled", f"정산된 거래가 {co['status']!r} 로 나온다"
    assert co["fee_total"] == pytest.approx(1465, abs=0.01) and co["tax_total"] == pytest.approx(1071, abs=0.01)
    assert co["paid_total"] == pytest.approx(2536, abs=0.01)


def test_f1_uuid_ids_loss_filter_uses_net(db_uuid):
    """P2 momentum = 세전 +4,000 / 세후 −160 — 「손실(세후)」 필터에 들어야 한다(실측: 19건 중 16건만 보였다)."""
    data = _ok(_get(outcome="loss", basis="net"))
    assert set(_anchors(data)) == {T[3], T[5]}


def test_f1_uuid_ids_pnl_sort_uses_net(db_uuid):
    assert _anchors(_ok(_get(sort="pnl_asc", basis="net"))) == [T[i] for i in (5, 3, 10, 1, 7)]


def test_f1_response_ids_are_strings(db_uuid):
    """가드 — 응답의 `anchor_trade_id`·`trade_ids` 는 문자열(메모 키·체결 행과 잇는 값)."""
    for c in _ok(_get(size=100))["cards"]:
        assert isinstance(c["anchor_trade_id"], str)
        for ln in c["entry"]["orders"] + c["exits"]:
            assert all(isinstance(i, str) for i in ln["trade_ids"])
    p1 = _card(_ok(_get()), 1)
    assert p1["entry"]["orders"][0]["trade_ids"] == [T[1]] and p1["exits"][0]["trade_ids"] == [T[2]]


# ── F8 체결 행 조회 실패 ───────────────────────────────────────────────────────

def test_f8_fill_lookup_failure_keeps_dates_and_marks_excursion_failed(db):  # noqa: F811
    db.fail.add("get_trades_by_ids")
    data = _ok(_get())
    for c in data["cards"]:
        assert isinstance(c["opened_at"], str) and c["opened_at"].endswith("+09:00"), c["pair_key"]
        assert isinstance(c["held_days"], int), c["pair_key"]
        assert c["excursion"]["na"] == "lookup_failed", (c["pair_key"], c["excursion"]["na"])
    p1 = _card(data, 1)
    assert p1["opened_at"].startswith("2026-10-05T09:12:03")
    assert p1["closed_at"].startswith("2026-10-08T14:31:20") and p1["held_days"] == 3
    p4 = _card(data, 7)   # 보유 중 고지로 10-06 매수 · 시계 10-09
    assert p4["closed_at"] is None and p4["held_days"] == 3
