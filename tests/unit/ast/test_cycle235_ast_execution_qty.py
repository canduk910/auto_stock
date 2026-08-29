"""cycle235 R7 — 체결통보 수량 소스 정본 봉인 (KIS ccnl_notice 26컬럼)."""

from __future__ import annotations

import re
from pathlib import Path

SRC = Path(__file__).resolve().parents[3] / "src"


class TestQuantitySourcePinned:
    def test_quantity_reads_fields_9_cntg_qty(self):
        text = (SRC / "realtime" / "handler.py").read_text(encoding="utf-8")
        # 수량 대입이 fields[9](CNTG_QTY 정본)에서 온다
        assert re.search(r"quantity\s*=\s*int\(fields\[9\]", text), (
            "체결수량 소스가 fields[9](CNTG_QTY) 가 아니다 — KIS 정본 위반"
        )

    def test_quantity_never_reads_fields_16(self):
        text = (SRC / "realtime" / "handler.py").read_text(encoding="utf-8")
        assert not re.search(r"quantity\s*=\s*int\(fields\[16\]", text), (
            "fields[16] 은 ODER_QTY(주문수량) — 체결수량으로 재오독 금지 "
            "(257720 실사고: 부분/분할 체결에서 positions 과대)"
        )
