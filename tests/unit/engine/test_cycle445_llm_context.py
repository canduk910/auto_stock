"""cycle445 B — 전 전략 `llm_context()` 를 AI 매수평가 입력에 (사용자 결정 2026-10-11).

워크리스트·`_workspace/00_URGENT_WORKLIST.md` 참조. 원래 VCP 단독으로 미뤄졌던
제안("핵심값 추가")을 cycle349 의 "`_candidates` 에 새 키를 추가하지 않는다" 결정과
충돌하지 않는 별도 경로(`StrategyBase.llm_context(ticker) -> dict`)로 전 전략에
확대한다.

이 파일이 고정하는 것:
1. `StrategyBase.llm_context` 기본값은 빈 dict — 재정의 안 한 전략은 핵심값이 없다.
2. 핵심값을 내는 6전략(donchian·BFB·VCP·kojiro·etf_trend·VB·LTV·ndx2x) 각각의
   override 가 기존 상태(`_candidates`/`_targets`/`_decision`)를 읽기만 하고,
   상태가 없거나 예외가 나면 빈 dict 로 떨어진다(never-raise).
3. `llm_buy_gate._read_strategy_llm_context` 가 레지스트리에서 전략 객체를 찾아
   `llm_context(ticker)` 를 부르고, 실패·부재는 전부 빈 dict.
4. `observe_order` 의 payload 에 `strategy_llm_context` 키가 실린다.
5. `llm_features.build_messages` 가 그 값을 `user_obj["strategy_metrics"]` 로
   옮기되, 비어 있으면 그 키 자체를 뺀다(0 위장 금지, null 결측 카운트 오염 방지).
6. `llm_buy_gate._prompt_version` 이 `llm_features.LLM_CONTEXT_SCHEMA_VERSION` 을
   해시 blob 에 포함해, 이 스키마가 바뀌면 전 전략 버전이 한 번 갈린다.
"""

from __future__ import annotations

import importlib

import pytest

pytestmark = pytest.mark.unit

_GATE_MOD = "src.engine.llm_buy_gate"
_FEATURES_MOD = "src.engine.llm_features"


def _gate():
    return importlib.import_module(_GATE_MOD)


def _features():
    return importlib.import_module(_FEATURES_MOD)


# ===========================================================================
# 1 — StrategyBase 기본값
# ===========================================================================
def test_strategy_base_default_llm_context_is_empty():
    from src.engine.strategy_base import StrategyBase

    class _Bare(StrategyBase):
        def prepare(self, *, as_of=None):
            raise NotImplementedError

        def check_buy_signal(self, ticker, current_price, open_price):
            raise NotImplementedError

        def check_exit_signal(self, ticker, current_price):
            raise NotImplementedError

        def calc_buy_quantity(self, current_price, ticker=None):
            raise NotImplementedError

    inst = _Bare.__new__(_Bare)
    assert StrategyBase.llm_context(inst, "005930") == {}


# ===========================================================================
# 2 — 전략별 override
# ===========================================================================
def test_donchian_llm_context_reads_candidates():
    from src.engine.strategies.donchian_swing import DonchianSwingStrategy

    inst = DonchianSwingStrategy.__new__(DonchianSwingStrategy)
    inst._candidates = {
        "005930": {"prev_close": 70000, "atr": 1200, "ema60": 69000, "donchian_high": 71000},
    }
    out = inst.llm_context("005930")
    assert out == {"atr": 1200, "ema60": 69000}


def test_donchian_llm_context_missing_ticker_is_empty():
    from src.engine.strategies.donchian_swing import DonchianSwingStrategy

    inst = DonchianSwingStrategy.__new__(DonchianSwingStrategy)
    inst._candidates = {}
    assert inst.llm_context("005930") == {}


def test_donchian_llm_context_never_raises_on_bad_state():
    from src.engine.strategies.donchian_swing import DonchianSwingStrategy

    inst = DonchianSwingStrategy.__new__(DonchianSwingStrategy)
    inst._candidates = None  # 상태 오염 — .get() 이 AttributeError
    assert inst.llm_context("005930") == {}


def test_bull_flag_breakout_llm_context_reads_candidates():
    from src.engine.strategies.bull_flag_breakout import BullFlagBreakoutStrategy

    inst = BullFlagBreakoutStrategy.__new__(BullFlagBreakoutStrategy)
    inst._candidates = {
        "005930": {
            "pole_start": 60000, "pole_high": 70000, "flag_high": 68000,
            "flag_low": 65000, "flag_avg_volume": 900000, "pole_len": 5, "flag_len": 3,
            "atr14": 1500, "prev_close": 67000,
        },
    }
    out = inst.llm_context("005930")
    assert out == {
        "atr14": 1500, "pole_high": 70000, "pole_start": 60000, "flag_avg_volume": 900000,
    }


def test_vcp_breakout_llm_context_reads_candidates():
    from src.engine.strategies.vcp_breakout import VcpBreakoutStrategy

    inst = VcpBreakoutStrategy.__new__(VcpBreakoutStrategy)
    inst._candidates = {
        "005930": {
            "base_high": 80000, "base_low": 72000, "last_pullback_pct": 8.5,
            "atr14": 1100, "ema50": 75000, "ema150": 70000, "ema200": 68000,
            "prev_close": 79000, "avg_volume_20": 500000,
        },
    }
    out = inst.llm_context("005930")
    assert out == {
        "atr14": 1100, "ema50": 75000, "ema150": 70000, "ema200": 68000,
        "avg_volume_20": 500000, "base_low": 72000, "last_pullback_pct": 8.5,
    }


def test_kojiro_llm_context_reads_candidates():
    from src.engine.strategies.kojiro import KojiroStrategy

    inst = KojiroStrategy.__new__(KojiroStrategy)
    inst._candidates = {
        "005930": {
            "prev_close": 70000, "atr": 1300, "stage": 1, "ema_s": 69500,
            "ema_m": 68000, "ema_l": 66000, "atr_ratio": 1.8, "sector": "반도체",
            "name": "삼성전자",
        },
    }
    out = inst.llm_context("005930")
    assert out == {
        "atr": 1300, "atr_ratio": 1.8, "stage": 1, "ema_s": 69500, "ema_m": 68000, "ema_l": 66000,
    }


def test_etf_trend_llm_context_reads_candidates():
    from src.engine.strategies.etf_trend import EtfTrendStrategy

    inst = EtfTrendStrategy.__new__(EtfTrendStrategy)
    inst._candidates = {
        "069500": {
            "prev_close": 30000, "line": 30500, "n": 400, "atr": 400,
            "atr20": 410, "tv20": 2_000_000_000, "ema60": 29800, "cluster_key": None,
        },
    }
    out = inst.llm_context("069500")
    assert out == {"atr": 400, "atr20": 410, "tv20": 2_000_000_000, "ema60": 29800}


def test_vb_llm_context_reads_prev_range():
    from src.engine.strategies.volatility_breakout import VolatilityBreakoutStrategy

    inst = VolatilityBreakoutStrategy.__new__(VolatilityBreakoutStrategy)
    inst._targets = {
        "005930": {"k": 0.5, "prev_range": 1500, "target_offset_base": 750},
    }
    out = inst.llm_context("005930")
    assert out == {"prev_range": 1500}


def test_vb_llm_context_missing_is_empty():
    from src.engine.strategies.volatility_breakout import VolatilityBreakoutStrategy

    inst = VolatilityBreakoutStrategy.__new__(VolatilityBreakoutStrategy)
    inst._targets = {}
    assert inst.llm_context("005930") == {}


def test_ltv_llm_context_reads_prev_range():
    from src.engine.strategies.long_tail_volatility import LongTailVolatilityStrategy

    inst = LongTailVolatilityStrategy.__new__(LongTailVolatilityStrategy)
    inst._targets = {
        "005930": {"k": 0.5, "prev_range": 1800},
    }
    out = inst.llm_context("005930")
    assert out == {"prev_range": 1800}


def test_momentum_llm_context_default_empty():
    """momentum 은 override 가 없다 — 기본값(빈 dict) 그대로."""
    from src.engine.strategies.momentum import MomentumStrategy

    inst = MomentumStrategy.__new__(MomentumStrategy)
    assert inst.llm_context("005930") == {}


def test_ndx2x_llm_context_reads_decision():
    from src.engine import ndx2x_core
    from src.engine.strategies.ndx2x_riskoff import Ndx2xRiskoffStrategy

    inst = Ndx2xRiskoffStrategy.__new__(Ndx2xRiskoffStrategy)
    inst._decision = ndx2x_core.DailyDecision(
        t7=0.012, r4=-0.08, cell="00", desired_state="2x", reason="t7_up",
    )
    out = inst.llm_context("418660")
    assert out == {"t7": 0.012, "r4": -0.08, "cell": "00", "desired_state": "2x"}


def test_ndx2x_llm_context_no_decision_is_empty():
    from src.engine.strategies.ndx2x_riskoff import Ndx2xRiskoffStrategy

    inst = Ndx2xRiskoffStrategy.__new__(Ndx2xRiskoffStrategy)
    inst._decision = None
    assert inst.llm_context("418660") == {}


# ===========================================================================
# 3 — llm_buy_gate._read_strategy_llm_context (레지스트리 조회)
# ===========================================================================
def test_read_strategy_llm_context_happy_path(monkeypatch):
    mod = _gate()

    class _FakeStrategy:
        def llm_context(self, ticker):
            return {"atr": 999, "ticker_seen": ticker}

    class _FakeRegistry:
        def get(self, sid):
            return _FakeStrategy() if sid == "kojiro" else None

    class _FakeScheduler:
        registry = _FakeRegistry()

    from src.engine import scheduler as sched_mod
    monkeypatch.setattr(sched_mod, "trading_scheduler", _FakeScheduler())

    out = mod._read_strategy_llm_context("kojiro", "005930")
    assert out == {"atr": 999, "ticker_seen": "005930"}


def test_read_strategy_llm_context_unknown_strategy_is_empty(monkeypatch):
    mod = _gate()

    class _FakeRegistry:
        def get(self, sid):
            return None

    class _FakeScheduler:
        registry = _FakeRegistry()

    from src.engine import scheduler as sched_mod
    monkeypatch.setattr(sched_mod, "trading_scheduler", _FakeScheduler())

    assert mod._read_strategy_llm_context("no_such_strategy", "005930") == {}


def test_read_strategy_llm_context_missing_method_is_empty(monkeypatch):
    mod = _gate()

    class _FakeStrategy:
        pass  # llm_context 없음

    class _FakeRegistry:
        def get(self, sid):
            return _FakeStrategy()

    class _FakeScheduler:
        registry = _FakeRegistry()

    from src.engine import scheduler as sched_mod
    monkeypatch.setattr(sched_mod, "trading_scheduler", _FakeScheduler())

    assert mod._read_strategy_llm_context("momentum", "005930") == {}


def test_read_strategy_llm_context_exception_is_empty(monkeypatch):
    mod = _gate()

    class _FakeStrategy:
        def llm_context(self, ticker):
            raise RuntimeError("boom")

    class _FakeRegistry:
        def get(self, sid):
            return _FakeStrategy()

    class _FakeScheduler:
        registry = _FakeRegistry()

    from src.engine import scheduler as sched_mod
    monkeypatch.setattr(sched_mod, "trading_scheduler", _FakeScheduler())

    assert mod._read_strategy_llm_context("kojiro", "005930") == {}


def test_read_strategy_llm_context_non_dict_return_is_empty(monkeypatch):
    mod = _gate()

    class _FakeStrategy:
        def llm_context(self, ticker):
            return "not-a-dict"

    class _FakeRegistry:
        def get(self, sid):
            return _FakeStrategy()

    class _FakeScheduler:
        registry = _FakeRegistry()

    from src.engine import scheduler as sched_mod
    monkeypatch.setattr(sched_mod, "trading_scheduler", _FakeScheduler())

    assert mod._read_strategy_llm_context("kojiro", "005930") == {}


def test_read_strategy_llm_context_registry_access_error_is_empty(monkeypatch):
    mod = _gate()

    class _ExplodingScheduler:
        @property
        def registry(self):
            raise RuntimeError("registry not ready")

    from src.engine import scheduler as sched_mod
    monkeypatch.setattr(sched_mod, "trading_scheduler", _ExplodingScheduler())

    assert mod._read_strategy_llm_context("kojiro", "005930") == {}


# ===========================================================================
# 4 — observe_order payload 에 strategy_llm_context 가 실린다
# ===========================================================================
async def test_observe_order_payload_includes_strategy_llm_context(monkeypatch):
    from datetime import datetime, timedelta, timezone
    from types import SimpleNamespace

    mod = _gate()
    mod.reset_llm_buy_gate_state()

    KST = timezone(timedelta(hours=9))
    now = datetime(2026, 10, 11, 9, 5, 0, tzinfo=KST)

    monkeypatch.setattr(
        mod, "settings",
        SimpleNamespace(
            openai_api_key="test-key", openai_buy_gate_model="gpt-6-luna",
            kis_account_no="12345678", kis_account_product="01",
        ),
    )
    from src.engine import scanner
    monkeypatch.setattr(scanner, "ticker_prices", {}, raising=False)
    monkeypatch.setattr(scanner, "ticker_names", {}, raising=False)

    seen: list = []

    async def _fake_evaluate(payload):
        seen.append(payload)
        return None

    monkeypatch.setattr(mod, "_evaluate", _fake_evaluate)
    monkeypatch.setattr(
        mod, "_read_strategy_llm_context",
        lambda sid, ticker: {"atr": 1234, "stage": 1},
    )

    assert mod.observe_order(
        strategy_id="kojiro", ticker="005930", order_no="ORD-1", order_kst=now,
        order_price_won=70000, ordered_qty=5, order_division="MARKET",
        order_path="market", exchange="KRX", current_price_won=70000,
        budget_total_won=1_000_000, budget_remaining_after_won=500_000,
        open_positions_n=1,
        params_snapshot={"llm_gate_mode": "shadow", "llm_gate_daily_call_cap": 20},
        buy_signals_tail=[],
    ) is None

    import asyncio
    for _ in range(10):
        await asyncio.sleep(0)

    assert len(seen) == 1
    assert seen[0]["strategy_llm_context"] == {"atr": 1234, "stage": 1}


# ===========================================================================
# 5 — llm_features.build_messages 가 strategy_metrics 블록을 옮긴다
# ===========================================================================
def _base_payload(**over) -> dict:
    p = {
        "strategy": "kojiro", "ticker": "005930", "name": "삼성전자",
        "board": "main", "order_kst": "09:05:00", "mins_from_krx_open": 5,
        "order_price_won": 70000, "board_open_won": 69500, "target_won": None,
        "k": None, "breakout_excess_bp": None, "prdy_close_won": 69000,
        "prdy_ctrt_pct": 1.4, "intraday_ctrt_pct": 0.7, "acml_vol_shares": 1000000,
        "vol_ratio_vs_avg20": None, "vol_ratio_time_norm": None,
        "order_division": "MARKET", "order_path": "market", "exchange": "KRX",
        "stop_loss_pct": -8.0, "budget_won": 1_000_000, "position_ratio": 0.1,
        "market_cap_eok": 1000, "trade_amount_eok": 50, "exit_rule": "",
    }
    p.update(over)
    return p


def test_build_messages_includes_strategy_metrics_when_present():
    feat = _features()
    payload = _base_payload(strategy_llm_context={"atr": 1300, "stage": 1})
    user_obj_json = feat.build_messages(payload, {}, [])[1]["content"]
    import json as _json
    obj = _json.loads(user_obj_json[user_obj_json.index("{"):])
    assert obj["strategy_metrics"] == {"atr": 1300, "stage": 1}


def test_build_messages_omits_strategy_metrics_when_empty():
    feat = _features()
    payload = _base_payload(strategy_llm_context={})
    user_obj_json = feat.build_messages(payload, {}, [])[1]["content"]
    import json as _json
    obj = _json.loads(user_obj_json[user_obj_json.index("{"):])
    assert "strategy_metrics" not in obj


def test_build_messages_omits_strategy_metrics_when_absent():
    feat = _features()
    payload = _base_payload()
    payload.pop("strategy_llm_context", None)
    user_obj_json = feat.build_messages(payload, {}, [])[1]["content"]
    import json as _json
    obj = _json.loads(user_obj_json[user_obj_json.index("{"):])
    assert "strategy_metrics" not in obj


def test_build_messages_omits_strategy_metrics_when_not_a_dict():
    feat = _features()
    payload = _base_payload(strategy_llm_context="not-a-dict")
    user_obj_json = feat.build_messages(payload, {}, [])[1]["content"]
    import json as _json
    obj = _json.loads(user_obj_json[user_obj_json.index("{"):])
    assert "strategy_metrics" not in obj


def test_llm_context_schema_version_constant_exists():
    feat = _features()
    assert isinstance(feat.LLM_CONTEXT_SCHEMA_VERSION, str)
    assert feat.LLM_CONTEXT_SCHEMA_VERSION


# ===========================================================================
# 6 — _prompt_version 이 LLM_CONTEXT_SCHEMA_VERSION 변화를 반영한다
# ===========================================================================
def test_prompt_version_changes_when_schema_version_changes(monkeypatch):
    mod = _gate()
    feat = _features()

    monkeypatch.setattr(mod, "settings", type("S", (), {"openai_buy_gate_model": "gpt-6-luna"})())
    monkeypatch.setattr(mod, "_prompt_version_cache", {})
    before = mod._prompt_version("kojiro")

    monkeypatch.setattr(feat, "LLM_CONTEXT_SCHEMA_VERSION", "strategy_metrics_v2")
    monkeypatch.setattr(mod, "_prompt_version_cache", {})
    after = mod._prompt_version("kojiro")

    assert before != after, "LLM_CONTEXT_SCHEMA_VERSION 이 바뀌어도 prompt_version 이 그대로다"
