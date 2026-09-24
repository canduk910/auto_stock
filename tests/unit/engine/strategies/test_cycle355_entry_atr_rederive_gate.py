"""cycle355 — 재시작 `_entry_atr` 재도출은 **터틀로 사는 전략**에서만 (BFB·VCP 사이징 출처 게이트).

## 사고 (2026-09-23 실측)

BFB 운영 설정은 `sizing_mode=position_ratio`, `stop_loss_rate=-5`, `turtle_backstop_pct=-7`.
position_ratio 매수는 `_entry_atr` 스탬프 **없이** 시작한다(스탬프는 `_turtle_buy_quantity`
성공 경로에서만 찍힌다). 그런데 아침 부팅 훅 `recompute_high_since_buy` 가
`ticker not in self._entry_atr` 만 보고 `_rederive_entry_atr` 를 불러, 매수 다음 날 아침
모든 BFB 보유분에 스탬프를 찍었다. 스탬프가 찍히면 `check_exit_signal` §1 이 ATR 경로로
넘어가고, 이 종목군(ATR 4.8~7.5%)에서는 −7% backstop 이 실제 손절선이 된다.

    09-22 39,450 매수(100840) → 09-23 07:46 [bfb_entry_atr_rederive] 100840 entry_atr=2371
    → 10:50 [bfb_turtle_backstop] 100840 −7.1% ≤ −7.0% 매도 (규약대로면 −5%)

재도출 함수의 docstring 은 「재시작으로 **소실된**」 스탬프를 되살린다고 적는다. position_ratio
랏은 처음부터 스탬프가 없었다 — 소실된 것이 없으니 되살릴 것도 없다.

## 게이트

랏별 사이징 기록이 없으므로, 재도출은 **그 전략이 지금 `sizing_mode="turtle"` 일 때만** 한다.
donchian `recompute_held_atr` 가 Phase 2A-2 부터 쓰던 게이트와 같다(그쪽은 무접촉).
운영 BFB·VCP 는 한 번도 turtle 로 산 적이 없으므로(다크런치) 이 게이트는 두 전략의
**모든 랏**에 대해 정확하다.

in-memory 스탬프가 살아 있으면(같은 프로세스가 터틀로 산 랏) 게이트와 무관하게 미접촉이다.
"""

from __future__ import annotations

import ast
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from src.engine.strategies.bull_flag_breakout import BullFlagBreakoutStrategy
from src.engine.strategies.donchian_swing import DonchianSwingStrategy
from src.engine.strategies.vcp_breakout import VcpBreakoutStrategy
from src.engine.strategy_base import Position, Signal, StrategyConfig

pytestmark = pytest.mark.unit

_KST = timezone(timedelta(hours=9))
_STRATEGIES_DIR = Path(__file__).resolve().parents[4] / "src" / "engine" / "strategies"


def _today() -> date:
    return datetime.now(_KST).date()


# 100840 재현 — 매수가 39,450, 매수일 이전 14봉 True Range ≈ 2,400 (ATR ≈ 6%).
BUY = 39_450
TICKER = "100840"


def _candles(n: int = 80, *, rng: int = 2_400) -> list[dict]:
    """KIS 일봉 (최신순). 매수일 이전 구간의 봉 폭을 `rng` 로 고정해 entry ATR ≈ rng."""
    out = []
    for i in range(n):
        close = BUY + (i % 3) * 10  # 거의 평탄 — ema/채널 청산이 끼어들지 않게
        out.append({
            "stck_bsop_date": (_today() - timedelta(days=i)).strftime("%Y%m%d"),
            "stck_hgpr": str(close + rng // 2), "stck_lwpr": str(close - rng // 2),
            "stck_clpr": str(close), "stck_oprc": str(close), "acml_vol": "100000",
        })
    return out


def _patch_io(monkeypatch, candles=None):
    monkeypatch.setattr(
        "src.api.condition.fetch_daily_candles", AsyncMock(return_value=candles or _candles()),
    )
    monkeypatch.setattr("src.db.positions.update_high", AsyncMock())
    monkeypatch.setattr("src.db.system_logs.write_log", AsyncMock())


def _bfb(**params) -> BullFlagBreakoutStrategy:
    s = BullFlagBreakoutStrategy(
        StrategyConfig(strategy_id="bull_flag_breakout", name="눌림목", weight=0.15, params=params),
    )
    s.state.total_investment = 1_000_000
    return s


def _vcp(**params) -> VcpBreakoutStrategy:
    s = VcpBreakoutStrategy(
        StrategyConfig(strategy_id="vcp_breakout", name="VCP", weight=0.15, params=params),
    )
    s.state.total_investment = 1_000_000
    return s


def _hold(s, *, sid: str, days_ago: int = 1) -> Position:
    pos = Position(
        ticker=TICKER, buy_price=BUY, quantity=4, order_no="O",
        strategy_id=sid, buy_date=_today() - timedelta(days=days_ago),
        high_since_buy=BUY,
    )
    s.state.positions[TICKER] = pos
    return pos


# ---------------------------------------------------------------------------
# G1 — position_ratio 랏은 다음 날 아침에도 스탬프가 찍히지 않는다 (사고 재현)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_g1_bfb_position_ratio_lot_is_not_stamped_on_boot(monkeypatch):
    s = _bfb(sizing_mode="position_ratio")
    _hold(s, sid="bull_flag_breakout", days_ago=1)
    _patch_io(monkeypatch)

    await s.recompute_high_since_buy()

    assert TICKER not in s._entry_atr, (
        "position_ratio 로 산 랏에 재도출 스탬프가 찍혔다 — −5% 고정 손절이 −7% backstop 으로 넓어진다"
    )


@pytest.mark.asyncio
async def test_g1_bfb_100840_replay_stops_at_minus_5(monkeypatch):
    """09-23 100840 을 그대로 재현 — 부팅 훅 뒤 −5.07% 에서 손절이 나야 한다."""
    s = _bfb(sizing_mode="position_ratio", stop_loss_rate=-5.0, turtle_backstop_pct=-7.0,
             turtle_min_stop_pct=-4.0)
    _hold(s, sid="bull_flag_breakout", days_ago=1)
    _patch_io(monkeypatch)

    await s.recompute_high_since_buy()

    price = 37_450  # −5.07%
    assert s.check_exit_signal(TICKER, price, BUY) == Signal.STOP_LOSS, (
        "부팅 뒤 position_ratio 랏은 −5% 에서 손절해야 한다 (사고 당시엔 −7.1% 까지 버텼다)"
    )


@pytest.mark.asyncio
async def test_g1_vcp_position_ratio_lot_is_not_stamped_on_boot(monkeypatch):
    s = _vcp(sizing_mode="position_ratio")
    _hold(s, sid="vcp_breakout", days_ago=1)
    _patch_io(monkeypatch)

    await s.recompute_high_since_buy()

    assert TICKER not in s._entry_atr, (
        "VCP position_ratio 랏에 재도출 스탬프가 찍혔다 — −7% 고정 손절이 ATR 경로(−5%~−9%)로 바뀐다"
    )


@pytest.mark.asyncio
async def test_g1_default_params_are_position_ratio_and_not_stamped(monkeypatch):
    """코드 기본값(다크런치 = position_ratio)에서도 같은 결과여야 한다."""
    for s, sid in ((_bfb(), "bull_flag_breakout"), (_vcp(), "vcp_breakout")):
        assert s.config.params["sizing_mode"] == "position_ratio"
        _hold(s, sid=sid, days_ago=2)
        _patch_io(monkeypatch)
        await s.recompute_high_since_buy()
        assert TICKER not in s._entry_atr, f"{sid}: 기본값(position_ratio)인데 스탬프가 찍혔다"


# ---------------------------------------------------------------------------
# G2 — turtle 로 사는 전략의 재시작 복구는 그대로 산다
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize("factory,sid", [(_bfb, "bull_flag_breakout"), (_vcp, "vcp_breakout")])
async def test_g2_turtle_strategy_still_rederives_after_restart(factory, sid, monkeypatch):
    s = factory(sizing_mode="turtle")
    _hold(s, sid=sid, days_ago=2)
    _patch_io(monkeypatch)

    await s.recompute_high_since_buy()

    assert s._entry_atr.get(TICKER, 0) > 0, (
        f"{sid}: turtle 전략의 재시작 소실분 재도출이 사라졌다 — ATR 손절이 고정%로 무단 강등된다"
    )


# ---------------------------------------------------------------------------
# G3 — 살아 있는 in-memory 스탬프는 설정과 무관하게 미접촉 (같은 프로세스가 터틀로 산 랏)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize("factory,sid", [(_bfb, "bull_flag_breakout"), (_vcp, "vcp_breakout")])
async def test_g3_live_stamp_untouched_even_if_config_is_position_ratio(factory, sid, monkeypatch):
    s = factory(sizing_mode="position_ratio")
    _hold(s, sid=sid, days_ago=2)
    s._entry_atr[TICKER] = 1_234.0
    _patch_io(monkeypatch)

    await s.recompute_high_since_buy()

    assert s._entry_atr[TICKER] == 1_234.0, f"{sid}: 살아 있는 터틀 스탬프를 지웠다/덮었다"


# ---------------------------------------------------------------------------
# G4 — 건너뛴 사실을 운영자가 볼 수 있다 (월요일 07:46 확인 근거)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_g4_skip_is_logged_with_label_and_mode(monkeypatch, caplog):
    import logging

    s = _bfb(sizing_mode="position_ratio")
    _hold(s, sid="bull_flag_breakout", days_ago=1)
    _patch_io(monkeypatch)

    with caplog.at_level(logging.INFO, logger="src.engine.strategy_base"):
        await s.recompute_high_since_buy()

    msgs = [r.getMessage() for r in caplog.records]
    assert any(
        m.startswith("[bfb_entry_atr_rederive_skip]") and TICKER in m and "position_ratio" in m
        for m in msgs
    ), msgs
    assert not any(m.startswith("[bfb_entry_atr_rederive]") for m in msgs), (
        "건너뛰었는데 재도출 로그가 찍혔다"
    )


# ---------------------------------------------------------------------------
# G5 — 게이트 판정 헬퍼 (단일 진실원)
# ---------------------------------------------------------------------------

def test_g5_gate_helper_semantics():
    assert _bfb(sizing_mode="turtle")._entry_atr_rederive_allowed(TICKER) is True
    assert _bfb(sizing_mode="position_ratio")._entry_atr_rederive_allowed(TICKER) is False
    assert _vcp(sizing_mode="turtle")._entry_atr_rederive_allowed(TICKER) is True
    assert _vcp()._entry_atr_rederive_allowed(TICKER) is False


def test_g5_gate_helper_never_raises_on_odd_params():
    s = _bfb()
    s.config.params["sizing_mode"] = None
    assert s._entry_atr_rederive_allowed(TICKER) is False
    s.config.params.pop("sizing_mode")
    assert s._entry_atr_rederive_allowed(TICKER) is False


# ---------------------------------------------------------------------------
# G6 — 구조 가드: 전략 파일의 모든 `_rederive_entry_atr` 호출은 turtle 게이트 아래에 있다
# ---------------------------------------------------------------------------

def _enclosing_if_tests(tree: ast.AST, target: ast.AST) -> list[str]:
    parents: dict[ast.AST, ast.AST] = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parents[child] = node
    out: list[str] = []
    cur = target
    while cur in parents:
        cur = parents[cur]
        if isinstance(cur, ast.If):
            out.append(ast.unparse(cur.test))
        if isinstance(cur, (ast.FunctionDef, ast.AsyncFunctionDef)):
            break
    return out


def test_g6_every_rederive_call_site_is_gated_by_turtle():
    sites = []
    for path in sorted(_STRATEGIES_DIR.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "_rederive_entry_atr"
            ):
                tests = _enclosing_if_tests(tree, node)
                gated = any(
                    "_entry_atr_rederive_allowed" in t or "'turtle'" in t or '"turtle"' in t
                    for t in tests
                )
                sites.append((path.name, node.lineno, gated))
    names = {s[0] for s in sites}
    assert {"bull_flag_breakout.py", "vcp_breakout.py", "donchian_swing.py"} <= names, (
        f"탐지기 자기검증 실패 — 호출부 3곳을 못 찾았다: {sites}"
    )
    ungated = [(n, ln) for n, ln, g in sites if not g]
    assert not ungated, (
        f"turtle 게이트 없이 `_rederive_entry_atr` 를 부르는 곳: {ungated} — "
        "position_ratio 랏이 다음 날 아침 ATR 손절로 넘어간다(cycle355 사고)"
    )


# ---------------------------------------------------------------------------
# G7 — donchian 무접촉 확인 (이미 turtle 게이트를 갖고 있다)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize("mode,stamped", [("turtle", True), ("position_ratio", False)])
async def test_g7_donchian_behaviour_unchanged(mode, stamped, monkeypatch):
    """donchian 은 이미 같은 게이트다 — turtle(운영)이면 재도출, position_ratio 면 미재도출."""
    s = DonchianSwingStrategy(
        StrategyConfig(strategy_id="donchian_swing", name="20일 신고가", weight=0.15,
                       params={"sizing_mode": mode}),
    )
    s.state.total_investment = 1_000_000
    _hold(s, sid="donchian_swing", days_ago=3)
    _patch_io(monkeypatch)

    await s.recompute_held_atr()

    assert (s._entry_atr.get(TICKER, 0) > 0) is stamped, (mode, dict(s._entry_atr))
