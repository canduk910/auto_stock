"""Red — `GET /api/history/pnl` 응답 `data.summary` 실현손익 요약 바.

명세: team-lead 메시지 「매매손익 (1) 실현손익 요약 바」 + Red 메모
`_workspace/red/pnl_summary_kojiro_filter.md`.

대상: `src.routes.history.trade_pnl(...) -> ApiResponse`.
- 기존 `pairs/page/size/total/total_pages` 계약 **불변**.
- 신규 `summary` dict — **슬라이스 전 전체 pairs 중 `status == 'closed'` 만** 집계
  (필터 `strategy`/`ticker` 는 `get_trade_pairs` 가 이미 반영):
    realized_total_krw : float  — closed profit_loss 합 (원)
    realized_rate_pct  : float(round 2) — 가중 = realized_total / Σ(buy_price×buy_qty of closed) × 100 (분모 0 → 0.0)
    win_count/loss_count/even_count : int — closed profit_loss > / < / == 0
    win_rate_pct       : float(round 1) — wins/(wins+losses)×100 (분모 0 → 0.0)
    closed_count       : int — closed 페어 수
  - open 페어 제외(미실현 미포함). Decimal/float 혼용 안전. 빈 결과 → 전부 0.

검증 패턴: TestClient 지양, 라우트 함수 직접 await (사이클 127 anyio portal hang 차단).
`get_trade_pairs` 는 `src.routes.history` 모듈 네임스페이스에서 monkeypatch —
라우트가 module-level 로 이미 import 함(`from src.db.trade_history import get_trade_pairs`).

RED 상태: 현재 `trade_pnl` 응답 `data` 에 `summary` 키 부재 → `data["summary"]`
KeyError 로 전 케이스 실패.
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from src.routes import history as hist

pytestmark = pytest.mark.unit


def _pair(
    *,
    buy_price,
    buy_qty,
    profit_loss,
    status: str = "closed",
    profit_rate=0.0,
    strategy: str = "momentum",
    ticker: str = "005930",
    sell_price=None,
    sell_qty=None,
) -> dict:
    """get_trade_pairs 반환 페어 스키마 대역 (필요한 키만 정확히 재현)."""
    return {
        "buy_date": "2026-08-01",
        "buy_time": "09:00:00",
        "sell_date": "2026-08-01" if status == "closed" else None,
        "sell_time": "10:00:00" if status == "closed" else None,
        "ticker": ticker,
        "ticker_name": "종목명",
        "buy_price": buy_price,
        "buy_qty": buy_qty,
        "sell_price": sell_price,
        "sell_qty": sell_qty,
        "profit_loss": profit_loss,
        "profit_rate": profit_rate,
        "status": status,
        "strategy": strategy,
    }


def _install_pairs(monkeypatch, pairs: list[dict], *, capture: dict | None = None):
    """라우트가 소비하는 get_trade_pairs 를 fake 로 교체.

    실제 get_trade_pairs 처럼 strategy/ticker 필터를 반영해 반환한다.
    capture 를 주면 라우트가 넘긴 인자를 기록(전달 계약 검증용).
    """
    async def _fake(strategy=None, ticker=None):
        if capture is not None:
            capture["strategy"] = strategy
            capture["ticker"] = ticker
        out = list(pairs)
        if strategy:
            out = [p for p in out if p.get("strategy") == strategy]
        if ticker:
            out = [p for p in out if p.get("ticker") == ticker]
        return out

    monkeypatch.setattr(hist, "get_trade_pairs", _fake, raising=True)


# ===========================================================================
# (a) closed 3건 — 합·승/패/보합·승률·가중손익율 정확
# ===========================================================================
@pytest.mark.asyncio
async def test_summary_aggregates_closed_pairs(monkeypatch):
    pairs = [
        _pair(buy_price=10000, buy_qty=1, profit_loss=1000.0),   # 승
        _pair(buy_price=10000, buy_qty=1, profit_loss=-400.0),   # 패
        _pair(buy_price=10000, buy_qty=1, profit_loss=0.0),      # 보합
    ]
    _install_pairs(monkeypatch, pairs)

    resp = await hist.trade_pnl(page=1, size=50, ticker=None, strategy=None)

    assert resp.success is True
    s = resp.data["summary"]
    assert s["closed_count"] == 3
    # 실현 합계 = 1000 - 400 + 0 = 600
    assert s["realized_total_krw"] == 600.0
    assert s["win_count"] == 1
    assert s["loss_count"] == 1
    assert s["even_count"] == 1
    # 승률 = 1/(1+1) × 100 = 50.0 (round 1)
    assert s["win_rate_pct"] == 50.0
    # 가중 손익율 = 600 / (10000×3) × 100 = 2.0 (round 2)
    assert s["realized_rate_pct"] == 2.0


# ===========================================================================
# (a') Decimal/float 혼용 안전 + realized_total_krw float 타입
# ===========================================================================
@pytest.mark.asyncio
async def test_summary_decimal_and_float_mixed(monkeypatch):
    pairs = [
        _pair(buy_price=Decimal("10000"), buy_qty=2, profit_loss=Decimal("1500")),
        _pair(buy_price=20000.0, buy_qty=1, profit_loss=-500.0),
    ]
    _install_pairs(monkeypatch, pairs)

    resp = await hist.trade_pnl(page=1, size=50, ticker=None, strategy=None)

    s = resp.data["summary"]
    # 실현 = 1500 - 500 = 1000, float 로 정규화
    assert s["realized_total_krw"] == 1000.0
    assert isinstance(s["realized_total_krw"], float)
    # 분모 = 10000×2 + 20000×1 = 40000, rate = 1000/40000×100 = 2.5
    assert s["realized_rate_pct"] == 2.5
    assert isinstance(s["realized_rate_pct"], float)
    assert s["win_count"] == 1
    assert s["loss_count"] == 1
    assert s["even_count"] == 0


# ===========================================================================
# (b) strategy 필터 — 해당 전략 closed 만 집계 + 라우트가 인자 전달
# ===========================================================================
@pytest.mark.asyncio
async def test_summary_reflects_strategy_filter(monkeypatch):
    pairs = [
        _pair(buy_price=10000, buy_qty=1, profit_loss=1000.0, strategy="momentum"),
        _pair(buy_price=10000, buy_qty=1, profit_loss=-300.0, strategy="kojiro"),
        _pair(buy_price=10000, buy_qty=1, profit_loss=500.0, strategy="kojiro"),
    ]
    capture: dict = {}
    _install_pairs(monkeypatch, pairs, capture=capture)

    resp = await hist.trade_pnl(page=1, size=50, ticker=None, strategy="kojiro")

    # 라우트가 strategy 를 get_trade_pairs 로 전달 (필터는 DB 계층이 담당)
    assert capture["strategy"] == "kojiro"
    s = resp.data["summary"]
    assert s["closed_count"] == 2          # kojiro 2건만
    assert s["realized_total_krw"] == 200.0  # -300 + 500
    assert s["win_count"] == 1
    assert s["loss_count"] == 1
    # 가중 = 200 / (10000×2) × 100 = 1.0
    assert s["realized_rate_pct"] == 1.0


# ===========================================================================
# (c) open 페어는 summary 제외 (미실현 미포함, profit_loss None 도 안전)
# ===========================================================================
@pytest.mark.asyncio
async def test_summary_excludes_open_pairs(monkeypatch):
    pairs = [
        _pair(buy_price=10000, buy_qty=1, profit_loss=1000.0, status="closed"),
        # open — 큰 미실현 이익이라도 집계 제외
        _pair(buy_price=10000, buy_qty=1, profit_loss=99999.0, status="open"),
        # open — 시세 미수신 profit_loss None (집계 접근 전에 제외돼야 함)
        _pair(buy_price=10000, buy_qty=1, profit_loss=None, status="open"),
    ]
    _install_pairs(monkeypatch, pairs)

    resp = await hist.trade_pnl(page=1, size=50, ticker=None, strategy=None)

    s = resp.data["summary"]
    assert s["closed_count"] == 1                 # open 2건 제외
    assert s["realized_total_krw"] == 1000.0      # open profit_loss 미포함
    assert s["win_count"] == 1
    assert s["loss_count"] == 0
    assert s["even_count"] == 0
    # 가중 분모 = closed 만 = 10000 → 1000/10000×100 = 10.0
    assert s["realized_rate_pct"] == 10.0


# ===========================================================================
# (d) 페어 0건 → summary 전부 0
# ===========================================================================
@pytest.mark.asyncio
async def test_summary_empty_all_zero(monkeypatch):
    _install_pairs(monkeypatch, [])

    resp = await hist.trade_pnl(page=1, size=50, ticker=None, strategy=None)

    s = resp.data["summary"]
    assert s["realized_total_krw"] == 0
    assert s["realized_rate_pct"] == 0.0
    assert s["win_count"] == 0
    assert s["loss_count"] == 0
    assert s["even_count"] == 0
    assert s["win_rate_pct"] == 0.0
    assert s["closed_count"] == 0


# ===========================================================================
# (d') 분모 0 (buy_price 이상치) → realized_rate_pct 0.0 (division guard)
# ===========================================================================
@pytest.mark.asyncio
async def test_summary_zero_denominator_rate_is_zero(monkeypatch):
    pairs = [_pair(buy_price=0, buy_qty=0, profit_loss=500.0)]
    _install_pairs(monkeypatch, pairs)

    resp = await hist.trade_pnl(page=1, size=50, ticker=None, strategy=None)

    s = resp.data["summary"]
    assert s["realized_rate_pct"] == 0.0    # 0 나눗셈 가드
    assert s["realized_total_krw"] == 500.0
    assert s["closed_count"] == 1


# ===========================================================================
# (d'') 승/패 0 (전부 보합) → win_rate_pct 0.0 (division guard)
# ===========================================================================
@pytest.mark.asyncio
async def test_summary_win_rate_zero_when_no_win_loss(monkeypatch):
    pairs = [
        _pair(buy_price=10000, buy_qty=1, profit_loss=0.0),
        _pair(buy_price=10000, buy_qty=1, profit_loss=0.0),
    ]
    _install_pairs(monkeypatch, pairs)

    resp = await hist.trade_pnl(page=1, size=50, ticker=None, strategy=None)

    s = resp.data["summary"]
    assert s["even_count"] == 2
    assert s["win_rate_pct"] == 0.0    # wins + losses == 0
    assert s["realized_total_krw"] == 0.0


# ===========================================================================
# (e) 기존 pairs/total/page 계약 불변 (회귀 핵심) + summary 는 슬라이스 전 전체 기준
# ===========================================================================
@pytest.mark.asyncio
async def test_existing_pairs_pagination_contract_unchanged(monkeypatch):
    pairs = [
        _pair(buy_price=1, buy_qty=1, profit_loss=0.0, ticker=f"{i:06d}")
        for i in range(150)
    ]
    _install_pairs(monkeypatch, pairs)

    resp = await hist.trade_pnl(page=2, size=50, ticker=None, strategy=None)

    data = resp.data
    # 기존 계약 불변
    assert data["page"] == 2
    assert data["size"] == 50
    assert data["total"] == 150
    assert data["total_pages"] == 3
    assert len(data["pairs"]) == 50        # 슬라이스 유지
    for key in ("pairs", "page", "size", "total", "total_pages"):
        assert key in data, f"기존 계약 키 누락: {key}"
    # summary 는 페이지 슬라이스 전 전체(150 closed) 기준
    assert data["summary"]["closed_count"] == 150
