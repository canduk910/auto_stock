"""사이클 H Red — 포트폴리오 리스크 순수함수 (extract_hard_stop_pct / compute_portfolio_risk_snapshot).

명세: `_workspace/cycleH_portfolio_risk_phase1_spec.md` §1 + §TDD (a)(b).
Red 메모: `_workspace/red/cycleH_portfolio_risk.md`.

대상 신규 모듈 `src.engine.portfolio_risk` (DB/HTTP/시계/registry/kojiro import 0 — quant_score /
te_metrics / ta_indicators 선례). 순수함수이므로 실호출(결정적 입력 → 결정적 출력), mock 없음.

핵심 계약 (구현 전 Red 고정):
- extract_hard_stop_pct(params, *, default=-7.0): 후보 7키(stop_loss_rate/intraday_stop_loss/
  overnight_stop_loss/stop_loss_main/stop_loss_pre_nxt/turtle_backstop_pct/hard_stop_pct) 中
  **음수만** → min (최대 계획 손실). 후보 0건/None → default -7.0 (0.0 금지 = 리스크 0 오인 차단).
- compute_portfolio_risk_snapshot(strategies, *, net_asset, hard_stop_pcts, sector_of):
  포지션 리스크 프록시 = buy_price×quantity×|hard_stop_pct|/100 (int). 반환 스키마 §1 그대로.
  net_asset<=0 → pct 0.0. by_strategy = 전달된 전 전략(0 포지션 포함). by_sector = 포지션有만.
  top_sector = risk_won 최대(포지션 0 → None). **배제 0 — 입력 positions dict 무변경.**

RED 상태: `src.engine.portfolio_risk` 모듈 부재 → ImportError 로 전 케이스 실패.
"""
from __future__ import annotations

import copy
from types import SimpleNamespace

import pytest

from src.engine.strategy_base import Position, StrategyState

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# 헬퍼 — mock 전략 (state.positions 만 있으면 됨, SimpleNamespace 스텁)
# ---------------------------------------------------------------------------
def _pos(ticker: str, buy_price: int, quantity: int, strategy_id: str) -> Position:
    return Position(
        ticker=ticker,
        buy_price=buy_price,
        quantity=quantity,
        order_no=f"ORD-{ticker}",
        strategy_id=strategy_id,
    )


def _strategy(strategy_id: str, positions: list[Position]):
    """state.positions 만 노출하는 스텁 (registry.all() 원소 대역)."""
    state = StrategyState(strategy_id=strategy_id)
    for p in positions:
        state.positions[p.ticker] = p
    return SimpleNamespace(strategy_id=strategy_id, state=state)


# ===========================================================================
# (a) extract_hard_stop_pct — 7키 min / 양수 무시 / 결측 default -7.0 / None
# ===========================================================================
class TestExtractHardStopPct:
    def test_module_and_symbol(self):
        from src.engine.portfolio_risk import extract_hard_stop_pct  # noqa: F401

    def test_donchian_like_min_of_negatives(self):
        """donchian: stop_loss_rate -7.0 + turtle_backstop_pct -9.0 → min = -9.0."""
        from src.engine.portfolio_risk import extract_hard_stop_pct

        params = {"stop_loss_rate": -7.0, "turtle_backstop_pct": -9.0, "stop_atr": 2.0}
        assert extract_hard_stop_pct(params) == -9.0

    def test_kojiro_like_hard_stop_pct(self):
        """kojiro: hard_stop_pct -8.0 (stop_atr 는 후보 키 아님 → 무시)."""
        from src.engine.portfolio_risk import extract_hard_stop_pct

        params = {"hard_stop_pct": -8.0, "stop_atr": 2.0, "trail_atr": 2.5}
        assert extract_hard_stop_pct(params) == -8.0

    def test_ltv_like_overnight(self):
        """LTV: intraday -3.0 / overnight -5.0 / main None → min = -5.0."""
        from src.engine.portfolio_risk import extract_hard_stop_pct

        params = {
            "intraday_stop_loss": -3.0,
            "overnight_stop_loss": -5.0,
            "stop_loss_main": None,
        }
        assert extract_hard_stop_pct(params) == -5.0

    def test_positive_values_ignored(self):
        """양수 후보는 무시 — 음수만 채택. 양수 5.0 + 음수 -3.0 → -3.0."""
        from src.engine.portfolio_risk import extract_hard_stop_pct

        assert extract_hard_stop_pct({"stop_loss_rate": 5.0, "hard_stop_pct": -3.0}) == -3.0

    def test_all_positive_falls_back_to_default(self):
        """음수 후보 0건(양수만) → default -7.0 (0.0 금지)."""
        from src.engine.portfolio_risk import extract_hard_stop_pct

        assert extract_hard_stop_pct({"stop_loss_rate": 5.0}) == -7.0

    def test_empty_dict_default(self):
        from src.engine.portfolio_risk import extract_hard_stop_pct

        assert extract_hard_stop_pct({}) == -7.0

    def test_none_input_default(self):
        """None 입력 → default -7.0 (리스크 0 오인 차단)."""
        from src.engine.portfolio_risk import extract_hard_stop_pct

        assert extract_hard_stop_pct(None) == -7.0

    def test_none_valued_keys_skipped(self):
        """None 값 키는 후보 제외 — {stop_loss_rate: None, hard_stop_pct: -4.0} → -4.0."""
        from src.engine.portfolio_risk import extract_hard_stop_pct

        assert extract_hard_stop_pct({"stop_loss_rate": None, "hard_stop_pct": -4.0}) == -4.0

    def test_multiple_negatives_takes_min(self):
        from src.engine.portfolio_risk import extract_hard_stop_pct

        params = {
            "stop_loss_main": -3.0,
            "stop_loss_pre_nxt": -4.0,
            "stop_loss_rate": -2.0,
        }
        assert extract_hard_stop_pct(params) == -4.0

    def test_custom_default_override(self):
        """default 인자 override — 결측 시 그 값 반환 (fail-open 파라미터화)."""
        from src.engine.portfolio_risk import extract_hard_stop_pct

        assert extract_hard_stop_pct({}, default=-10.0) == -10.0
        assert extract_hard_stop_pct(None, default=-12.5) == -12.5

    def test_all_seven_candidate_keys_recognized(self):
        """7 후보 키 전부 스캔 대상임을 개별 검증 (키별 단독 → 그 값 반환)."""
        from src.engine.portfolio_risk import extract_hard_stop_pct

        for key in (
            "stop_loss_rate",
            "intraday_stop_loss",
            "overnight_stop_loss",
            "stop_loss_main",
            "stop_loss_pre_nxt",
            "turtle_backstop_pct",
            "hard_stop_pct",
        ):
            assert extract_hard_stop_pct({key: -6.0}) == -6.0, f"후보 키 미인식: {key}"


# ===========================================================================
# (b) compute_portfolio_risk_snapshot — 결정적 다전략 집계
# ===========================================================================
# 결정론적 시나리오 (수치 고정):
#   donchian(-9.0): 005930 10,000×10=100,000  / 000660 20,000×5=100,000
#   vcp(-7.0):      035720  5,000×20=100,000
#   kojiro(-8.0):   051910 40,000×2 = 80,000
#   momentum:       포지션 0 (by_strategy 0 포함 검증)
# 섹터: 005930/000660 → "반도체"(동일 섹터 합산), 035720 → "미분류-035720"(독립),
#       051910 → "에너지화학"
NET_ASSET = 1_000_000
_HARD_STOP_PCTS = {
    "donchian_swing": -9.0,
    "vcp_breakout": -7.0,
    "kojiro": -8.0,
    "momentum": -7.5,
}
_SECTOR_OF = {
    "005930": "반도체",
    "000660": "반도체",
    "035720": "미분류-035720",
    "051910": "에너지화학",
}


def _scenario_strategies():
    return [
        _strategy(
            "donchian_swing",
            [_pos("005930", 10_000, 10, "donchian_swing"),
             _pos("000660", 20_000, 5, "donchian_swing")],
        ),
        _strategy("vcp_breakout", [_pos("035720", 5_000, 20, "vcp_breakout")]),
        _strategy("kojiro", [_pos("051910", 40_000, 2, "kojiro")]),
        _strategy("momentum", []),  # 0 포지션 전략
    ]


class TestComputeSnapshotTotals:
    def test_module_and_symbol(self):
        from src.engine.portfolio_risk import compute_portfolio_risk_snapshot  # noqa: F401

    def test_top_level_aggregates(self):
        from src.engine.portfolio_risk import compute_portfolio_risk_snapshot

        snap = compute_portfolio_risk_snapshot(
            _scenario_strategies(),
            net_asset=NET_ASSET,
            hard_stop_pcts=_HARD_STOP_PCTS,
            sector_of=_SECTOR_OF,
        )
        # notional = 100,000 + 100,000 + 100,000 + 80,000
        assert snap["total_notional_won"] == 380_000
        # risk = 9,000 + 9,000 + 7,000 + 6,400
        assert snap["total_open_risk_won"] == 31_400
        assert snap["concurrent_positions"] == 4
        # 31,400 / 1,000,000 × 100 = 3.14
        assert snap["open_risk_pct_of_net"] == 3.14

    def test_risk_proxy_formula_per_position(self):
        """리스크 프록시 = buy_price×quantity×|pct|/100 (int) 단일 포지션 검증."""
        from src.engine.portfolio_risk import compute_portfolio_risk_snapshot

        snap = compute_portfolio_risk_snapshot(
            [_strategy("kojiro", [_pos("051910", 40_000, 2, "kojiro")])],
            net_asset=NET_ASSET,
            hard_stop_pcts={"kojiro": -8.0},
            sector_of={"051910": "에너지화학"},
        )
        # 40,000 × 2 × 8 / 100 = 6,400
        assert snap["total_open_risk_won"] == 6_400
        assert snap["total_notional_won"] == 80_000


class TestComputeSnapshotByStrategy:
    def test_all_strategies_included_zero_position_zero(self):
        """by_strategy 는 전달된 전 전략 포함 — 0 포지션 전략도 0 dict."""
        from src.engine.portfolio_risk import compute_portfolio_risk_snapshot

        snap = compute_portfolio_risk_snapshot(
            _scenario_strategies(),
            net_asset=NET_ASSET,
            hard_stop_pcts=_HARD_STOP_PCTS,
            sector_of=_SECTOR_OF,
        )
        bs = snap["by_strategy"]
        assert set(bs.keys()) == {"donchian_swing", "vcp_breakout", "kojiro", "momentum"}
        assert bs["donchian_swing"] == {"positions": 2, "notional_won": 200_000, "risk_won": 18_000}
        assert bs["vcp_breakout"] == {"positions": 1, "notional_won": 100_000, "risk_won": 7_000}
        assert bs["kojiro"] == {"positions": 1, "notional_won": 80_000, "risk_won": 6_400}
        # 0 포지션 전략도 0 으로 명시 포함
        assert bs["momentum"] == {"positions": 0, "notional_won": 0, "risk_won": 0}

    def test_missing_hard_stop_pct_uses_default(self):
        """hard_stop_pcts 결측 전략은 default -7.0 적용."""
        from src.engine.portfolio_risk import compute_portfolio_risk_snapshot

        snap = compute_portfolio_risk_snapshot(
            [_strategy("vcp_breakout", [_pos("035720", 5_000, 20, "vcp_breakout")])],
            net_asset=NET_ASSET,
            hard_stop_pcts={},  # 결측 → default -7.0
            sector_of={"035720": "미분류-035720"},
        )
        # 5,000 × 20 × 7 / 100 = 7,000
        assert snap["total_open_risk_won"] == 7_000


class TestComputeSnapshotBySector:
    def test_same_sector_aggregates_and_unclassified_independent(self):
        from src.engine.portfolio_risk import compute_portfolio_risk_snapshot

        snap = compute_portfolio_risk_snapshot(
            _scenario_strategies(),
            net_asset=NET_ASSET,
            hard_stop_pcts=_HARD_STOP_PCTS,
            sector_of=_SECTOR_OF,
        )
        by_sector = snap["by_sector"]
        # 포지션 있는 섹터만 (0 포지션 전략은 섹터 미기여)
        assert set(by_sector.keys()) == {"반도체", "미분류-035720", "에너지화학"}
        # 반도체 = 005930 + 000660 합산
        assert by_sector["반도체"] == {"positions": 2, "notional_won": 200_000, "risk_won": 18_000}
        # 미분류 독립
        assert by_sector["미분류-035720"] == {"positions": 1, "notional_won": 100_000, "risk_won": 7_000}
        assert by_sector["에너지화학"] == {"positions": 1, "notional_won": 80_000, "risk_won": 6_400}

    def test_ticker_missing_from_sector_of_treated_unclassified(self):
        """sector_of 결측 ticker 는 '미분류-{ticker}' 독립 취급 (fail-open)."""
        from src.engine.portfolio_risk import compute_portfolio_risk_snapshot

        snap = compute_portfolio_risk_snapshot(
            [_strategy("kojiro", [_pos("999999", 1_000, 3, "kojiro")])],
            net_asset=NET_ASSET,
            hard_stop_pcts={"kojiro": -8.0},
            sector_of={},  # 결측
        )
        assert "미분류-999999" in snap["by_sector"]
        assert snap["by_sector"]["미분류-999999"]["positions"] == 1


class TestComputeSnapshotTopSector:
    def test_top_sector_max_risk_with_share(self):
        from src.engine.portfolio_risk import compute_portfolio_risk_snapshot

        snap = compute_portfolio_risk_snapshot(
            _scenario_strategies(),
            net_asset=NET_ASSET,
            hard_stop_pcts=_HARD_STOP_PCTS,
            sector_of=_SECTOR_OF,
        )
        top = snap["top_sector"]
        assert top is not None
        assert top["sector"] == "반도체"
        assert top["risk_won"] == 18_000
        # 18,000 / 31,400 × 100 = 57.32 (round 2)
        assert top["risk_share_pct"] == 57.32

    def test_top_sector_none_when_no_positions(self):
        from src.engine.portfolio_risk import compute_portfolio_risk_snapshot

        snap = compute_portfolio_risk_snapshot(
            [_strategy("momentum", [])],
            net_asset=NET_ASSET,
            hard_stop_pcts={"momentum": -7.5},
            sector_of={},
        )
        assert snap["top_sector"] is None


class TestComputeSnapshotEdgeCases:
    def test_net_asset_zero_pct_zero(self):
        from src.engine.portfolio_risk import compute_portfolio_risk_snapshot

        snap = compute_portfolio_risk_snapshot(
            _scenario_strategies(),
            net_asset=0,
            hard_stop_pcts=_HARD_STOP_PCTS,
            sector_of=_SECTOR_OF,
        )
        assert snap["open_risk_pct_of_net"] == 0.0
        # 리스크 집계 자체는 그대로 (pct 만 0)
        assert snap["total_open_risk_won"] == 31_400

    def test_net_asset_negative_pct_zero(self):
        from src.engine.portfolio_risk import compute_portfolio_risk_snapshot

        snap = compute_portfolio_risk_snapshot(
            _scenario_strategies(),
            net_asset=-500_000,
            hard_stop_pcts=_HARD_STOP_PCTS,
            sector_of=_SECTOR_OF,
        )
        assert snap["open_risk_pct_of_net"] == 0.0

    def test_empty_strategies_zero_snapshot(self):
        from src.engine.portfolio_risk import compute_portfolio_risk_snapshot

        snap = compute_portfolio_risk_snapshot(
            [],
            net_asset=NET_ASSET,
            hard_stop_pcts={},
            sector_of={},
        )
        assert snap["total_notional_won"] == 0
        assert snap["total_open_risk_won"] == 0
        assert snap["concurrent_positions"] == 0
        assert snap["open_risk_pct_of_net"] == 0.0
        assert snap["by_strategy"] == {}
        assert snap["by_sector"] == {}
        assert snap["top_sector"] is None

    def test_all_strategies_zero_positions_zero_snapshot(self):
        """전략은 있으나 포지션 0 → by_strategy 0 포함, by_sector 빈, top None."""
        from src.engine.portfolio_risk import compute_portfolio_risk_snapshot

        snap = compute_portfolio_risk_snapshot(
            [_strategy("momentum", []), _strategy("kojiro", [])],
            net_asset=NET_ASSET,
            hard_stop_pcts={"momentum": -7.5, "kojiro": -8.0},
            sector_of={},
        )
        assert snap["concurrent_positions"] == 0
        assert snap["by_strategy"] == {
            "momentum": {"positions": 0, "notional_won": 0, "risk_won": 0},
            "kojiro": {"positions": 0, "notional_won": 0, "risk_won": 0},
        }
        assert snap["by_sector"] == {}
        assert snap["top_sector"] is None

    def test_malformed_position_skipped_graceful(self):
        """필드 결손(buy_price/quantity None) 포지션은 skip + 나머지 계속 집계."""
        from src.engine.portfolio_risk import compute_portfolio_risk_snapshot

        good = _pos("051910", 40_000, 2, "kojiro")
        broken = SimpleNamespace(ticker="BROKEN", buy_price=None, quantity=None,
                                 strategy_id="kojiro")
        state = StrategyState(strategy_id="kojiro")
        state.positions["051910"] = good
        state.positions["BROKEN"] = broken  # type: ignore[assignment]
        strat = SimpleNamespace(strategy_id="kojiro", state=state)

        snap = compute_portfolio_risk_snapshot(
            [strat],
            net_asset=NET_ASSET,
            hard_stop_pcts={"kojiro": -8.0},
            sector_of={"051910": "에너지화학"},
        )
        # 정상 1건만 집계 (6,400), broken skip
        assert snap["total_open_risk_won"] == 6_400
        assert snap["concurrent_positions"] == 1
        assert "에너지화학" in snap["by_sector"]

    def test_strategy_without_state_positions_graceful(self):
        """state/positions 미보유 스텁도 getattr 방어로 skip (AttributeError 금지)."""
        from src.engine.portfolio_risk import compute_portfolio_risk_snapshot

        bare = SimpleNamespace(strategy_id="ghost")  # state 없음
        snap = compute_portfolio_risk_snapshot(
            [bare],
            net_asset=NET_ASSET,
            hard_stop_pcts={"ghost": -7.0},
            sector_of={},
        )
        assert snap["concurrent_positions"] == 0
        # by_strategy 는 전달 전략 포함 (0)
        assert snap["by_strategy"]["ghost"] == {"positions": 0, "notional_won": 0, "risk_won": 0}


class TestComputeSnapshotNoMutation:
    def test_input_positions_dict_unchanged(self):
        """배제 0 — 입력 strategies/positions dict 무변경 (관찰 전용 계약)."""
        from src.engine.portfolio_risk import compute_portfolio_risk_snapshot

        strategies = _scenario_strategies()
        # 깊은 스냅샷 (positions dict + Position 필드 값)
        before = {
            s.strategy_id: {
                t: (p.ticker, p.buy_price, p.quantity, p.strategy_id)
                for t, p in s.state.positions.items()
            }
            for s in strategies
        }
        before_keys = {s.strategy_id: set(s.state.positions.keys()) for s in strategies}

        compute_portfolio_risk_snapshot(
            strategies,
            net_asset=NET_ASSET,
            hard_stop_pcts=_HARD_STOP_PCTS,
            sector_of=_SECTOR_OF,
        )

        after = {
            s.strategy_id: {
                t: (p.ticker, p.buy_price, p.quantity, p.strategy_id)
                for t, p in s.state.positions.items()
            }
            for s in strategies
        }
        after_keys = {s.strategy_id: set(s.state.positions.keys()) for s in strategies}
        assert after == before, "입력 positions 필드 값 변경 발생 (배제 0 위반)"
        assert after_keys == before_keys, "입력 positions dict 키 변경 발생 (배제 0 위반)"

    def test_input_sector_of_and_hard_stop_unchanged(self):
        from src.engine.portfolio_risk import compute_portfolio_risk_snapshot

        sector_of = dict(_SECTOR_OF)
        hard = dict(_HARD_STOP_PCTS)
        sector_before = copy.deepcopy(sector_of)
        hard_before = copy.deepcopy(hard)

        compute_portfolio_risk_snapshot(
            _scenario_strategies(),
            net_asset=NET_ASSET,
            hard_stop_pcts=hard,
            sector_of=sector_of,
        )
        assert sector_of == sector_before, "입력 sector_of 변경 (배제 0 위반)"
        assert hard == hard_before, "입력 hard_stop_pcts 변경 (배제 0 위반)"
