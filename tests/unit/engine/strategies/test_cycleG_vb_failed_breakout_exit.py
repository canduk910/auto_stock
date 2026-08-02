"""사이클 G Part A — VB 실패 돌파 조기청산 (C2, avg_loss↓) 회귀 가드 (Red).

명세: `_workspace/red/_behaviors_cycleG_vb_rr_20260802.md` Part A (G-A1~A6).
계획: `~/.claude/plans/luminous-drifting-widget.md` Part A.

돌파 후 현재가가 돌파선(`target_price`) 아래 `buffer_pct`% 로 `confirm_ticks` 연속
재이탈하면 −3% 손절을 기다리지 않고 조기 청산(STOP_LOSS) → |avg_loss| 직접 축소.
donchian `breakout_fail_n_days` / BFB `flag_low` 재이탈과 동형 논리.

**default-off** (`failed_breakout_exit_enabled=False`) → 활성 전까지 byte-identical
(BFB 사이클 C `breakeven_promote_atr=0` 선례). 매매 8영역 diff 0.

Red 가드 매트릭스:
- G-A1 (파라미터): DEFAULT_PARAMS 3키(enabled=False/buffer=-0.5/confirm_ticks=2) +
  PARAM_RANGES/INT_PARAMS 미편입(AST) — 진입/청산 정체성 상수.
- G-A2 (상태): `_failed_breakout_count` dict + prepare transient clear(AST) +
  on_position_closed 정리(런타임).
- G-A3 (발화, RED): enabled=True + 현재가 < target×(1+buffer/100) 가 confirm_ticks
  연속 → STOP_LOSS. confirm_ticks−1 후 회복 → 미발화(카운터 리셋).
- G-A4 (default-off byte-identical, HIGH): enabled=False → 조기청산 무발화, 기존
  손절/익일안전망만. **현행 코드 = GREEN 기준선** (분기 미진입, 활성 시 RED).
- G-A5 (승자 미간섭, HIGH): 현재가 target 위 유지 → 카운터 0, 무발화.
- G-A6 (경계): confirm_ticks−1 재이탈 후 회복 → 미발화. buffer 정확 적용.
- SAFETY (AST): check_buy_signal 본체 diff 0 (조기청산은 check_exit 분기 한정).

매매 안전성: 조기청산 = 손절 조기화 (데이트레이드 15:20 캡 무관). 활성 전 byte-identical.
freeze_time 미사용 — positions/_targets 합성 (사이클 187 hang 교훈).
"""

from __future__ import annotations

import ast
from datetime import datetime, timedelta, timezone

_KST = timezone(timedelta(hours=9))


def _today_kst():
    """CI UTC 환경에서 KST production code 와 1일 어긋남 방지 (사이클 68 hotfix 영속)."""
    return datetime.now(_KST).date()
from pathlib import Path

import pytest

from src.engine.session import MarketBoard, session_tracker
from src.engine.strategies.volatility_breakout import VolatilityBreakoutStrategy
from src.engine.strategy_base import Position, Signal, StrategyConfig

pytestmark = pytest.mark.unit

_REPO_ROOT = Path(__file__).resolve().parents[4]
_VB_SRC = _REPO_ROOT / "src" / "engine" / "strategies" / "volatility_breakout.py"
_RECO_SRC = _REPO_ROOT / "src" / "engine" / "recommendation_engine.py"


@pytest.fixture
def vb(monkeypatch):
    """scanner 격리 + session_tracker 활성 보드 초기화한 VB 인스턴스."""
    from src.engine import scanner

    monkeypatch.setattr(scanner, "ticker_names", {"005930": "삼성전자"})
    monkeypatch.setattr(scanner, "ticker_prev_close", {})
    monkeypatch.setattr(session_tracker, "_active", frozenset())
    return VolatilityBreakoutStrategy(
        StrategyConfig(strategy_id="volatility_breakout", name="변동성 돌파", weight=0.3)
    )


def _activate(board: str):
    session_tracker._active = frozenset({MarketBoard(board)})


def _seed_target(strategy, ticker, *, prev_range=500, k=1.0):
    """prepare() 결과를 모사 — _targets dict 직접 시드 (test_volatility_breakout 답습)."""
    target_offset_base = int(prev_range * k)
    strategy._targets[ticker] = {
        "k": k,
        "prev_range": prev_range,
        "target_offset_base": target_offset_base,
        "target_offset": target_offset_base,
        "target_price": 0,
        "open_price": 0,
        "boards": {},
    }
    strategy._open_confirmed[ticker] = {}


def _prime(strategy, ticker, *, open_price, base_offset, buy_price, is_next_day=False):
    """MAIN 보드 시가 확정 + target_price 세팅 + 보유 포지션 시드.

    target_price = open_price + base_offset (k_value_krx_main=1.0 기본).
    on_open_price_confirmed 로 boards["main"] 및 top-level 양쪽 세팅 (활성보드/폴백 커버).
    """
    _seed_target(strategy, ticker, prev_range=base_offset, k=1.0)
    strategy.config.params["k_value_krx_main"] = 1.0
    _activate("main")
    strategy.on_open_price_confirmed(ticker, open_price, board="main")
    buy_date = _today_kst() - timedelta(days=1) if is_next_day else _today_kst()
    strategy.state.positions[ticker] = Position(
        ticker=ticker, buy_price=buy_price, quantity=1,
        order_no="O1", strategy_id="volatility_breakout", buy_date=buy_date,
    )


def _method_source(name: str) -> str:
    src = _VB_SRC.read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return ast.get_source_segment(src, node) or ""
    return ""


# ---------------------------------------------------------------------------
# G-A1 — 파라미터 (DEFAULT_PARAMS 3키 + PARAM_RANGES/INT_PARAMS 미편입)
# ---------------------------------------------------------------------------
class TestFailedBreakoutParams:
    def test_default_params_three_keys(self):
        p = VolatilityBreakoutStrategy.DEFAULT_PARAMS
        assert p.get("failed_breakout_exit_enabled") is False, (
            f"failed_breakout_exit_enabled != False (default-off): "
            f"{p.get('failed_breakout_exit_enabled')}"
        )
        assert p.get("failed_breakout_buffer_pct") == -0.5, (
            f"failed_breakout_buffer_pct != -0.5 (재이탈 버퍼): "
            f"{p.get('failed_breakout_buffer_pct')}"
        )
        assert p.get("failed_breakout_confirm_ticks") == 2, (
            f"failed_breakout_confirm_ticks != 2 (연속 확인): "
            f"{p.get('failed_breakout_confirm_ticks')}"
        )

    def test_params_not_in_param_ranges(self):
        """진입/청산 정체성 상수 — AI 자동튜닝 제외 (사이클 198/208/212 선례)."""
        reco_src = _RECO_SRC.read_text(encoding="utf-8")
        for token in (
            "failed_breakout_exit_enabled",
            "failed_breakout_buffer_pct",
            "failed_breakout_confirm_ticks",
        ):
            assert token not in reco_src, (
                f"recommendation_engine.py 에 '{token}' 등장 — "
                "PARAM_RANGES/INT_PARAMS 편입 금지 위반 (청산 정체성 상수)."
            )


# ---------------------------------------------------------------------------
# G-A2 — 상태 (_failed_breakout_count dict + prepare clear + on_position_closed 정리)
# ---------------------------------------------------------------------------
class TestFailedBreakoutState:
    def test_count_dict_initialized(self, vb):
        assert hasattr(vb, "_failed_breakout_count"), (
            "VolatilityBreakoutStrategy.__init__ 에 _failed_breakout_count dict 부재 (G-A2)."
        )
        assert vb._failed_breakout_count == {}, (
            f"_failed_breakout_count 초기값 != {{}}: {vb._failed_breakout_count}"
        )

    def test_prepare_clears_count(self):
        """prepare() transient clear 지점 (_targets/_open_confirmed 옆, vb.py:144-146)."""
        body = _method_source("prepare")
        assert body, "prepare 미발견."
        assert "_failed_breakout_count.clear()" in body, (
            "prepare() 에 _failed_breakout_count.clear() 부재 — "
            "전일 stale 카운터 누적 차단 위반 (G-A2)."
        )

    def test_on_position_closed_cleans_count(self, vb):
        """청산(매도 체결) 시 per-ticker 카운터 정리 (on_position_closed, vb.py:979-986)."""
        _prime(vb, "005930", open_price=80000, base_offset=500, buy_price=80500)
        vb._failed_breakout_count["005930"] = 3
        vb.on_position_closed("005930")
        assert "005930" not in vb._failed_breakout_count, (
            "on_position_closed 후 _failed_breakout_count 에 종목 잔존 — "
            "재진입 시 stale 카운터 누설 (G-A2)."
        )


# ---------------------------------------------------------------------------
# G-A3 — 조기청산 발화 (RED: enabled=True + confirm_ticks 연속 재이탈)
# ---------------------------------------------------------------------------
class TestFailedBreakoutFires:
    def test_fires_after_confirm_ticks(self, vb):
        vb.config.params["failed_breakout_exit_enabled"] = True
        vb.config.params["failed_breakout_buffer_pct"] = -0.5
        vb.config.params["failed_breakout_confirm_ticks"] = 2
        # target_price = 80000 + 500 = 80500, buy_price = 80500 (돌파 직후 매수)
        _prime(vb, "005930", open_price=80000, base_offset=500, buy_price=80500)
        # threshold = 80500 * 0.995 = 80097.5. current 80000 < threshold = 재이탈.
        # loss_rate = (80000-80500)/80500 = -0.62% > -3% → 손절 미발동.
        # 1차 재이탈 — 카운터=1 (confirm_ticks=2 미달, 미발화)
        assert vb.check_exit_signal("005930", 80000, 80000) == Signal.NONE
        # 2차 재이탈 — 카운터=2 >= confirm_ticks → 조기청산
        assert vb.check_exit_signal("005930", 80000, 80000) == Signal.STOP_LOSS, (
            "confirm_ticks 연속 재이탈인데 조기청산 미발화 (G-A3 RED)."
        )

    def test_single_tick_when_confirm_one(self, vb):
        vb.config.params["failed_breakout_exit_enabled"] = True
        vb.config.params["failed_breakout_buffer_pct"] = -0.5
        vb.config.params["failed_breakout_confirm_ticks"] = 1
        _prime(vb, "005930", open_price=80000, base_offset=500, buy_price=80500)
        # confirm_ticks=1 → 첫 재이탈 즉시 발화
        assert vb.check_exit_signal("005930", 80000, 80000) == Signal.STOP_LOSS


# ---------------------------------------------------------------------------
# G-A4 — default-off byte-identical (HIGH): enabled=False → 조기청산 무발화
# ---------------------------------------------------------------------------
class TestDefaultOffByteIdentical:
    def test_disabled_no_early_exit_on_reentry(self, vb):
        # 기본 enabled=False (미설정) — 재이탈이어도 조기청산 안 함
        _prime(vb, "005930", open_price=80000, base_offset=500, buy_price=80500)
        # target 80500 아래로 재이탈. loss -0.62% (손절 미달) → 반복해도 NONE
        assert vb.check_exit_signal("005930", 80000, 80000) == Signal.NONE
        assert vb.check_exit_signal("005930", 80000, 80000) == Signal.NONE, (
            "enabled=False 인데 조기청산 발화 — default-off byte-identical 위반 (G-A4 HIGH)."
        )

    def test_disabled_stop_loss_still_fires(self, vb):
        """조기청산 비활성이어도 기존 −3% 손절은 정상 발동."""
        _prime(vb, "005930", open_price=80000, base_offset=500, buy_price=100000)
        # loss = (97000-100000)/100000 = -3% → 손절
        assert vb.check_exit_signal("005930", 97000, 80000) == Signal.STOP_LOSS

    def test_disabled_next_day_clear_still_fires(self, vb):
        """조기청산 비활성이어도 익일 청산 안전망은 정상 발동."""
        _prime(
            vb, "005930", open_price=80000, base_offset=500,
            buy_price=80000, is_next_day=True,
        )
        vb._next_day_clear_pending = False
        # current 81000 (target 80500 위, 승자 + 손절 미달) → 익일안전망만 발화
        assert vb.check_exit_signal("005930", 81000, 80000) == Signal.NEXT_DAY_CLEAR


# ---------------------------------------------------------------------------
# G-A5 — 승자 미간섭 (HIGH): 현재가 target 위 유지 → 무발화
# ---------------------------------------------------------------------------
class TestWinnerUntouched:
    def test_winner_above_target_no_exit(self, vb):
        vb.config.params["failed_breakout_exit_enabled"] = True
        vb.config.params["failed_breakout_buffer_pct"] = -0.5
        vb.config.params["failed_breakout_confirm_ticks"] = 2
        _prime(vb, "005930", open_price=80000, base_offset=500, buy_price=80500)
        # target 80500 위 유지 — 재이탈 아님 → 무발화
        assert vb.check_exit_signal("005930", 81000, 80000) == Signal.NONE
        assert vb.check_exit_signal("005930", 82000, 80000) == Signal.NONE
        assert vb.check_exit_signal("005930", 83000, 80000) == Signal.NONE, (
            "target 위 승자인데 조기청산 발화 — 재이탈만 트리거 위반 (G-A5 HIGH)."
        )


# ---------------------------------------------------------------------------
# G-A6 — 경계 (카운터 리셋 + buffer 정확)
# ---------------------------------------------------------------------------
class TestBoundaryConditions:
    def test_counter_resets_on_recovery(self, vb):
        vb.config.params["failed_breakout_exit_enabled"] = True
        vb.config.params["failed_breakout_buffer_pct"] = -0.5
        vb.config.params["failed_breakout_confirm_ticks"] = 2
        _prime(vb, "005930", open_price=80000, base_offset=500, buy_price=80500)
        # 1차 재이탈 (카운터=1)
        assert vb.check_exit_signal("005930", 80000, 80000) == Signal.NONE
        # 회복 (target 위) → 카운터 리셋
        assert vb.check_exit_signal("005930", 80600, 80000) == Signal.NONE
        # 다시 재이탈 (카운터=1, confirm_ticks=2 미달 — 리셋됐으므로 미발화)
        assert vb.check_exit_signal("005930", 80000, 80000) == Signal.NONE, (
            "confirm_ticks−1 재이탈 후 회복했는데 다음 재이탈에 즉시 발화 — "
            "카운터 리셋 위반 (G-A6)."
        )

    def test_buffer_exact_threshold(self, vb):
        vb.config.params["failed_breakout_exit_enabled"] = True
        vb.config.params["failed_breakout_buffer_pct"] = -0.5
        vb.config.params["failed_breakout_confirm_ticks"] = 1
        _prime(vb, "005930", open_price=80000, base_offset=500, buy_price=80500)
        # threshold = 80500 * (1 + (-0.5)/100) = 80097.5
        # 80098 > 80097.5 → 재이탈 미달 (미발화, 카운터 리셋)
        assert vb.check_exit_signal("005930", 80098, 80000) == Signal.NONE, (
            "buffer 임계 위(80098 > 80097.5)인데 조기청산 발화 — buffer 부정확 (G-A6)."
        )
        # 80097 < 80097.5 → 재이탈 (confirm_ticks=1 → 즉시 발화)
        assert vb.check_exit_signal("005930", 80097, 80000) == Signal.STOP_LOSS, (
            "buffer 임계 아래(80097 < 80097.5)인데 조기청산 미발화 — buffer 부정확 (G-A6)."
        )


# ---------------------------------------------------------------------------
# SAFETY (AST) — check_buy_signal 본체 diff 0 (조기청산은 check_exit 분기 한정)
# ---------------------------------------------------------------------------
class TestBuySignalUnchanged:
    def test_check_buy_signal_no_failed_breakout_token(self):
        body = _method_source("check_buy_signal")
        assert body, "check_buy_signal 미발견."
        for token in ("failed_breakout", "_failed_breakout_count"):
            assert token not in body, (
                f"check_buy_signal 본체에 '{token}' 인젝션 — 매수 로직 diff 0 위반 (SAFETY). "
                "조기청산은 check_exit_signal 분기 전용."
            )
