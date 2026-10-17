"""cycle471 — 과제 B 1·2단계: 지표 정본 `src/engine/indicators.py` 로 바꿔 끼워도 값이 같다.

옛 구현을 이 파일에 **그대로 베껴 두고**(바꾸기 직전 HEAD `145e535a` 원문) 무작위·경계 입력
수천 건에서 새 경로와 **완전히 같은 값(==)** 인지 본다. 끝자리 하나라도 다르면 매수 판정·손절선이
움직일 수 있어 근사 비교를 쓰지 않는다.
"""
from __future__ import annotations

import ast
import random
import sys
from pathlib import Path

import pytest

from src.engine import etf_trend_core as core
from src.engine import indicators as ind
from src.engine import llm_features as lf
from src.engine.strategies.donchian_swing import DonchianSwingStrategy
from src.engine.strategies.vcp_breakout import VcpBreakoutStrategy
from src.engine.strategy_base import StrategyBase

pytestmark = pytest.mark.unit
_ROOT = Path(__file__).resolve().parents[3]


# ── 옛 구현 원문 ─────────────────────────────────────────────────────────────
def old_donchian_ema(values, period):
    if not values:
        return 0.0
    k = 2 / (period + 1)
    ema = float(values[0])
    for v in values[1:]:
        ema = v * k + ema * (1 - k)
    return ema


def old_core_ema(values, span):
    a = 2.0 / (span + 1)
    out = []
    for i, v in enumerate(values):
        out.append(float(v) if i == 0 else a * v + (1 - a) * out[-1])
    return out


def old_core_true_ranges(highs, lows, closes):
    out = []
    for i in range(len(highs)):
        if i == 0:
            out.append(highs[0] - lows[0])
        else:
            pc = closes[i - 1]
            out.append(max(highs[i] - lows[i], abs(highs[i] - pc), abs(lows[i] - pc)))
    return out


def old_core_atr_wilder(tr, period=20):
    a = 1.0 / period
    out = []
    for i, v in enumerate(tr):
        out.append(float(v) if i == 0 else a * v + (1 - a) * out[-1])
    return out


def old_lf_ema(values, period):
    if period is None or period <= 0:
        return None
    try:
        vals = [float(v) for v in values]
    except (TypeError, ValueError):
        return None
    if len(vals) < period:
        return None
    result = sum(vals[:period]) / period
    alpha = 2.0 / (period + 1)
    for v in vals[period:]:
        result = result + alpha * (v - result)
    return result


def old_lf_atr_wilder(highs, lows, closes, period=14):
    try:
        h = [float(x) for x in highs]
        low = [float(x) for x in lows]
        c = [float(x) for x in closes]
    except (TypeError, ValueError):
        return None
    n = min(len(h), len(low), len(c))
    if n < period + 1:
        return None
    trs = []
    for i in range(1, n):
        tr = max(h[i] - low[i], abs(h[i] - c[i - 1]), abs(low[i] - c[i - 1]))
        trs.append(tr)
    if len(trs) < period:
        return None
    atr = sum(trs[:period]) / period
    for tr in trs[period:]:
        atr = (atr * (period - 1) + tr) / period
    return atr


def old_base_atr(highs, lows, closes, period):
    if len(highs) <= period or len(lows) <= period or len(closes) <= period + 1:
        return 0.0
    trs = []
    for i in range(period):
        tr = max(highs[i] - lows[i], abs(highs[i] - closes[i + 1]), abs(lows[i] - closes[i + 1]))
        trs.append(tr)
    return sum(trs) / period


# ── 입력 생성 ────────────────────────────────────────────────────────────────
def _bars(rng: random.Random, n: int, *, ints: bool):
    price = rng.uniform(500, 300_000)
    hs, ls, cs = [], [], []
    for _ in range(n):
        price *= 1 + rng.gauss(0, 0.03)
        price = max(price, 10)
        hi = price * (1 + abs(rng.gauss(0, 0.015)))
        lo = price * (1 - abs(rng.gauss(0, 0.015)))
        if ints:
            hi, lo, c = int(hi), int(lo), int(price)
        else:
            c = price
        hs.append(hi); ls.append(lo); cs.append(c)
    return hs, ls, cs


_CASES = [(seed, n, ints) for seed in range(60) for n in (0, 1, 2, 5, 14, 15, 21, 60, 120, 260) for ints in (True, False)]


@pytest.mark.parametrize("seed,n,ints", _CASES)
def test_all_paths_bit_identical(seed, n, ints):
    rng = random.Random(seed * 1000 + n)
    hs, ls, cs = _bars(rng, n, ints=ints)
    for p in (1, 5, 10, 14, 20, 50, 60, 150, 200):
        assert DonchianSwingStrategy._ema(cs, p) == old_donchian_ema(cs, p)
        assert VcpBreakoutStrategy._ema(cs, p) == old_donchian_ema(cs, p)
        assert lf.ema(cs, p) == old_lf_ema(cs, p)
        assert lf.atr_wilder(hs, ls, cs, p) == old_lf_atr_wilder(hs, ls, cs, p)
        assert StrategyBase._atr(hs, ls, cs, p) == old_base_atr(hs, ls, cs, p)
        assert core.ema(cs, p) == old_core_ema(cs, p)
        tr = old_core_true_ranges(hs, ls, cs)
        assert core.true_ranges(hs, ls, cs) == tr
        assert core.atr_wilder(tr, p) == old_core_atr_wilder(tr, p)


def test_edge_inputs_identical():
    for p in (0, -1, None):
        assert lf.ema([1, 2, 3], p) == old_lf_ema([1, 2, 3], p)
    assert lf.ema(["x"], 1) == old_lf_ema(["x"], 1)
    assert lf.atr_wilder([1], [1], ["x"], 1) == old_lf_atr_wilder([1], [1], ["x"], 1)
    assert DonchianSwingStrategy._ema([], 5) == 0.0
    assert core.ema([], 5) == [] and core.true_ranges([], [], []) == [] and core.atr_wilder([], 5) == []


# ── 구조 ─────────────────────────────────────────────────────────────────────
def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    mods = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.ImportFrom):
            mods.add(n.module or "")
        elif isinstance(n, ast.Import):
            mods |= {a.name for a in n.names}
    return mods


def test_indicators_leaf_is_stdlib_only():
    mods = _imports(_ROOT / "src/engine/indicators.py")
    bad = [m for m in mods if m.split(".")[0] not in sys.stdlib_module_names and m != "__future__"]
    assert bad == [] and "logging" not in mods


def test_old_bodies_are_gone_and_delegate():
    """옛 계산식 본문이 다시 생기지 않게 — 위임 자리는 `indicators` 를 부른다."""
    for rel, name in [
        ("src/engine/strategies/donchian_swing.py", "_ema"),
        ("src/engine/strategies/vcp_breakout.py", "_ema"),
        ("src/engine/strategy_base.py", "_atr"),
        ("src/engine/etf_trend_core.py", "ema"),
        ("src/engine/etf_trend_core.py", "atr_wilder"),
        ("src/engine/etf_trend_core.py", "true_ranges"),
        ("src/engine/llm_features.py", "ema"),
        ("src/engine/llm_features.py", "atr_wilder"),
    ]:
        src = (_ROOT / rel).read_text(encoding="utf-8")
        tree = ast.parse(src)
        fns = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == name]
        assert len(fns) == 1, (rel, name)
        body = ast.get_source_segment(src, fns[0])
        assert "_ind." in body, f"{rel}::{name} 가 indicators 로 위임하지 않는다"
        assert not any(isinstance(n, (ast.For, ast.While)) for n in ast.walk(fns[0])), f"{rel}::{name} 에 계산 루프가 남았다"


def test_swing_poll_data_timing_set_matches_manifest():
    """리팩토링 검토 10-17 #8 — `llm_features` 의 스윙 조회 안내 전략 집합 = 명부 `SWING_POLL_IDS`."""
    from src.engine.strategy_manifest import SWING_POLL_IDS
    got = {sid for sid, meta in lf._STRATEGY_META.items() if "data_timing" in meta}
    assert got == set(SWING_POLL_IDS)
