"""cycle413 보완 1차 Red — 거래일지 카드 비용이 실 Postgres(실 UUID 체결 id + `trade_cost_daily` 정산 행)에서
`/api/history/pnl` 과 같은 숫자인가.

판정 원문 = scratchpad `c413/fix/verdict1.md` #1 · 명세 = `_workspace/red/cycle413/journal_view_spec.md` 1-1절 「숫자는 매매손익
탭과 같아야 한다」 · 9절 T3(c).

결함(#1): `GET /api/history/journal` 이 페어의 체결 id(asyncpg `uuid.UUID`)를 문자열로 바꾼 **뒤** `overlay_pairs` 를
불러, 비용 맵(UUID 키)과 하나도 맞지 않았다 → 청산 카드 전부 수수료·세금 0 · 세후 = 세전 · 「추정」. 운영 실측에서
「손실」 필터가 19건 중 16건만 보였고 손익 부호가 뒤집힌 거래(+20 / −157)도 나왔다. 기존 통합 판(`test_cycle413_journal_pg.py`
P7)은 정산 행을 넣지 않아 「추정」 이 우연히 맞았다.

| # | 계약 (같은 거래 = 같은 숫자) |
|---|---|
| G1 | 정산된 닫힌 페어 — 카드 `pnl.net_krw` = `/pnl` `net_profit_loss` · `costs.status` = `cost_status`(=`settled`) · `fee_total` = `entry_fee + Σexits.fee` = `/pnl` `fee` · `tax_total` = `/pnl` `tax` |
| G2 | 세전 이익 · 세후 손실 페어(+1 / −19) — 카드 세후가 음수이고, `outcome=loss&basis=net` 에 들고 `outcome=win&basis=net` 에서 빠진다 |

운영 DB 에는 실행하지 않는다 — 로컬 pg 하네스(docker) 또는 CI `DATABASE_URL_TEST` 만. 라우트는 `httpx.ASGITransport`
로 같은 이벤트 루프에서 부른다(풀이 이 루프에 귀속 — cycle297 G5-3 관례).
"""

from __future__ import annotations

import importlib
from datetime import date
from decimal import Decimal

import pytest

from tests.integration.test_cycle413_journal_pg import (  # noqa: F401 — `clean_journal` 은 픽스처 재사용
    _BFB,
    _call,
    _seed,
    clean_journal,
)

pytestmark = [pytest.mark.integration, pytest.mark.slow]

_Q = {"from": "2026-10-01", "to": "2026-10-09"}


async def _cost(pool, d, pdno, *, buy_amt=0, sll_amt=0, fee=0, tl_tax=0):
    await pool.execute(
        "INSERT INTO trade_cost_daily (trad_dt, pdno, buy_amt, sll_amt, fee, tl_tax) VALUES ($1,$2,$3,$4,$5,$6)",
        d, pdno, Decimal(buy_amt), Decimal(sll_amt), Decimal(fee), Decimal(tl_tax))


async def _seed_settled(pool) -> dict:
    """`_seed` (BFB 247540 +44,000 · VB 000660 +1) 위에 KIS 정산 행을 얹는다."""
    importlib.import_module("src.engine.cost_overlay")._reset_cache_for_tests()
    ids = await _seed(pool)
    await _cost(pool, date(2026, 10, 5), "247540", buy_amt=494000, fee=701)
    await _cost(pool, date(2026, 10, 8), "247540", sll_amt=538000, fee=764, tl_tax=1071)
    # 세전 +1 · 수수료 20 → 세후 −19 (부호가 뒤집히는 거래).
    await _cost(pool, date(2026, 10, 1), "000660", buy_amt=100, sll_amt=101, fee=20)
    return ids


async def _journal(**params):
    r = await _call("GET", "/api/history/journal", params={**_Q, **params})
    assert r.status_code == 200, r.text
    return r.json()["data"]


async def _pnl_by_key():
    r = await _call("GET", "/api/history/pnl", params={"size": 200})
    assert r.status_code == 200, r.text
    return {p["pair_key"]: p for p in r.json()["data"]["pairs"]}


async def test_g1_settled_card_costs_equal_pnl_route(clean_journal):
    ids = await _seed_settled(clean_journal)
    data = await _journal(strategy=_BFB)
    assert data["cost_available"] is True
    (c,) = data["cards"]
    assert c["anchor_trade_id"] == ids["buy"]
    p = (await _pnl_by_key())[c["pair_key"]]
    assert p["cost_status"] == "settled" and p["net_profit_loss"] == pytest.approx(41464, abs=0.5)   # 기준(/pnl)

    assert c["pnl"]["gross_krw"] == 44000
    assert c["pnl"]["net_krw"] == pytest.approx(p["net_profit_loss"], abs=0.01), (
        f"카드 세후 {c['pnl']['net_krw']} ≠ 매매손익 탭 {p['net_profit_loss']} — 비용 맵 키(UUID) 불일치")
    co = c["costs"]
    assert co["status"] == p["cost_status"] == "settled", f"정산된 거래가 {co['status']!r}"
    assert co["fee_total"] == pytest.approx(p["fee"], abs=0.01)
    assert co["tax_total"] == pytest.approx(p["tax"], abs=0.01)
    assert co["entry_fee"] + sum(x["fee"] for x in co["exits"]) == pytest.approx(co["fee_total"], abs=0.01)
    assert sum(x["tax"] for x in co["exits"]) == pytest.approx(co["tax_total"], abs=0.01)
    assert co["entry_status"] == "settled" and all(x["status"] == "settled" for x in co["exits"])


async def test_g2_gross_win_net_loss_follows_net_everywhere(clean_journal):
    ids = await _seed_settled(clean_journal)
    vb_key = None
    all_cards = (await _journal())["cards"]
    for c in all_cards:
        if c["anchor_trade_id"] == ids["vb_buy"]:
            vb_key = c["pair_key"]
            assert c["pnl"]["gross_krw"] == 1
            assert c["pnl"]["net_krw"] == pytest.approx(-19, abs=0.01), f"부호가 뒤집혔다: {c['pnl']['net_krw']}"
    assert vb_key is not None
    assert (await _pnl_by_key())[vb_key]["net_profit_loss"] == pytest.approx(-19, abs=0.01)

    loss = {c["anchor_trade_id"] for c in (await _journal(outcome="loss", basis="net"))["cards"]}
    win = {c["anchor_trade_id"] for c in (await _journal(outcome="win", basis="net"))["cards"]}
    assert ids["vb_buy"] in loss, "세후 손실 거래가 「손실」 필터에서 빠졌다"
    assert ids["vb_buy"] not in win
    assert ids["buy"] in win and ids["buy"] not in loss
