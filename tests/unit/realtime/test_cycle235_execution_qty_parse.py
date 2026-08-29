"""cycle235 R1 — 체결통보 수량 파싱 정본 정합 (KIS ccnl_notice 26컬럼).

정본: fields[9]=CNTG_QTY(체결수량·증분) / fields[16]=ODER_QTY(주문수량).
현행 handler 는 fields[16] 을 수량으로 오독 — 단일 전량 체결(두 값 동일)에선
잠복하다 부분/분할 체결에서 positions 과대(257720 실사고 3주 vs 실체결 2주).
"""

from __future__ import annotations

import pytest

from src.realtime import handler as handler_mod

pytestmark = pytest.mark.unit


def _payload(*, order_no="0000411400", side="02", ticker="257720",
             cntg_qty="1", oder_qty="2", price="51100", exec_type="2") -> str:
    """KIS 정본 26컬럼 순서로 payload 구성 (^ 구분)."""
    fields = [""] * 26
    fields[0] = "HTSID"
    fields[1] = ""              # 계좌 — 빈 값이면 계좌 필터 통과
    fields[2] = order_no
    fields[4] = side            # 02=매수
    fields[8] = ticker
    fields[9] = cntg_qty        # CNTG_QTY 체결수량 (정본)
    fields[10] = price          # CNTG_UNPR
    fields[11] = "091551"
    fields[13] = exec_type      # CNTG_YN 1:접수 2:체결
    fields[16] = oder_qty       # ODER_QTY 주문수량 (정본)
    return "^".join(fields)


@pytest.fixture
def captured(monkeypatch):
    calls: list[tuple] = []

    async def _cb(ticker, order_no, side, price, quantity):
        calls.append((ticker, order_no, side, price, quantity))

    monkeypatch.setattr(handler_mod, "_on_execution", _cb)
    # 계좌 필터 비활성 (빈 target → skip)
    from src import config
    monkeypatch.setattr(config.settings, "kis_account_no", "", raising=False)
    return calls


class TestR1QuantitySource:
    @pytest.mark.asyncio
    async def test_quantity_is_cntg_qty_not_oder_qty(self, captured):
        """fields[9]=1(체결) vs fields[16]=2(주문) → 콜백 quantity 는 1 이어야 한다."""
        await handler_mod._handle_execution(_payload(cntg_qty="1", oder_qty="2"))
        assert len(captured) == 1
        ticker, order_no, side, price, quantity = captured[0]
        assert (ticker, side, price) == ("257720", "BUY", 51_100)
        assert quantity == 1, (
            "fields[16](ODER_QTY 주문수량)을 체결수량으로 오독 — 257720 실사고의 뿌리"
        )

    @pytest.mark.asyncio
    async def test_acceptance_notice_skipped(self, captured):
        """접수 통보(CNTG_YN=1)는 콜백 미발화 (기존 계약 보존)."""
        await handler_mod._handle_execution(_payload(exec_type="1"))
        assert captured == []

    @pytest.mark.asyncio
    async def test_short_payload_ignored(self, captured):
        await handler_mod._handle_execution("a^b^c")
        assert captured == []

    @pytest.mark.asyncio
    async def test_sell_side_mapped(self, captured):
        await handler_mod._handle_execution(
            _payload(side="01", cntg_qty="2", oder_qty="3"))
        assert captured and captured[0][2] == "SELL" and captured[0][4] == 2
