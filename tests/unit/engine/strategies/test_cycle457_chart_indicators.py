"""cycle457 — 거래일지 차트 지표 `chart_indicators` 가 전략의 실제 계산과 같은 값을 내는가.

사용자 지시(2026-10-15): 「기술적지표 계산함수를 설마 새로 만든거야? 전략에서도 사용할텐데 … 명백히 소스
중복아닌가」 → 차트 지표는 전략 객체가 매수·청산 판정에 쓰는 **같은 함수**로 계산한다.

| # | 계약 |
|---|---|
| P1 | donchian — 차트 마지막 봉의 돌파선·EMA·ATR = 같은 일봉으로 돌린 `prepare()` 의 `_candidates` 값 |
| P2 | VB·LTV — 다음 날 봉의 목표가 = 시가 + `prepare()` 가 낸 `target_offset_base` × `k_value_krx_main` |
| P3 | VCP — 추세 EMA 3선 = `_check_trend_filter` 가 같은 일봉·같은 실효 장기선으로 낸 값 |
| P4 | kojiro — EMA·MACD·ATR = `prepare()` 와 같은 100봉 창의 `enrich` 마지막 행 |
| P5 | etf_trend — `etf_trend_core` 의 `breakout_line`·`ema`·`atr_wilder` 를 같은 창으로 부른 값 |
| P6 | 모든 전략 — 선마다 series 길이 = 봉 수, `start_index` 앞은 None |
| P7 | 꺼낸 함수가 prepare 안에서 쓰인다(차트와 판정이 같은 함수를 공유) |
"""

from __future__ import annotations

import ast
import inspect
from datetime import date

import pytest
from freezegun import freeze_time

from src.engine import etf_trend_core as core
from src.engine.kojiro_indicators import enrich
from src.engine.strategies.etf_trend import EtfTrendStrategy
from src.engine.strategies.kojiro import KOJIRO_FETCH_DAYS, KojiroStrategy
from src.engine.strategy_base import StrategyConfig
from tests.unit.engine.strategies import _cycle364_harness as H

pytestmark = pytest.mark.unit

_HEAD = date(2026, 9, 21)
_NOW = "2026-09-22T07:50:00+09:00"


def _bars_asc(candles_desc: list[dict]) -> list[dict]:
    out = []
    for c in reversed(candles_desc):
        d = c["stck_bsop_date"]
        out.append({
            "date": f"{d[:4]}-{d[4:6]}-{d[6:]}", "open": int(c["stck_oprc"]), "high": int(c["stck_hgpr"]),
            "low": int(c["stck_lwpr"]), "close": int(c["stck_clpr"]), "volume": int(c["acml_vol"]),
        })
    return out


async def _prepared(sid: str, depth: int | None = None):
    """하네스 어댑터는 요청 봉 수를 무시하고 전부 돌려준다 — 운영처럼 `depth` 봉만 넘긴다."""
    s = H.make_strategy(sid)
    cands = H.universe(_HEAD)
    if depth is not None:
        cands = {t: (rows[:depth] if rows else rows) for t, rows in cands.items()}
    with freeze_time(_NOW):
        await H.run_prepare(s, cands)
    return s, cands


@pytest.mark.asyncio
async def test_p1_donchian_matches_prepare_candidates():
    s, cands = await _prepared("donchian_swing")
    assert s._candidates, "하네스가 donchian 후보를 만들지 못했다"
    for t, info in s._candidates.items():
        bars = _bars_asc(cands[t])
        r = s.chart_indicators(bars)
        assert int(r["series"]["donchian_high"][-1]) == info["donchian_high"]
        assert int(r["series"]["ema"][-1]) == info["ema60"]
        assert int(r["series"]["atr"][-1]) == info["atr"]


@pytest.mark.asyncio
@pytest.mark.parametrize("sid", ["volatility_breakout", "long_tail_volatility"])
async def test_p2_vb_target_matches_prepare_offset(sid):
    probe = H.make_strategy(sid)
    s, cands = await _prepared(sid, int(probe.config.params["k_period"]) + 2)
    assert s._targets
    k_mult = float(s.config.params.get("k_value_krx_main", 1.0))
    for t, info in s._targets.items():
        bars = _bars_asc(cands[t]) + [{"date": "2026-09-22", "open": 50_000, "high": 50_500,
                                        "low": 49_500, "close": 50_100, "volume": 1}]
        r = s.chart_indicators(bars)
        want = 50_000 + max(int(info["target_offset_base"] * k_mult), 0)
        assert r["series"]["vb_target"][-1] == want, t


@pytest.mark.asyncio
async def test_p3_vcp_trend_emas_match_trend_filter():
    s = H.make_strategy("vcp_breakout")
    candles = H.trend_series(_HEAD, 300, base=10_000, step=50, hi=30, lo=60)
    fetch_days = s._daily_fetch_days()
    window = candles[:fetch_days]
    eff = s._effective_ema_long(len(window))
    trend = s._check_trend_filter(window, effective_ema_long=eff)
    assert trend is not None, "상승 합성 봉은 추세 필터를 통과해야 한다"
    r = s.chart_indicators(_bars_asc(candles))
    assert int(r["series"]["ema_short"][-1]) == trend["ema50"]
    assert int(r["series"]["ema_mid"][-1]) == trend["ema150"]
    assert int(r["series"]["ema_long"][-1]) == trend["ema200"]
    # cap100 기본이면 장기선 제목이 실효 기간(설정 200 아님)이고 안내가 붙는다
    assert r["lines"][2]["title"] == f"EMA{eff}"
    assert any("daily_fetch_depth_mode" in n for n in r["notes"])


def test_p4_kojiro_matches_enrich_on_prepare_window():
    s = KojiroStrategy(StrategyConfig(strategy_id="kojiro", name="kojiro", params={}, enabled=True))
    candles = H.trend_series(_HEAD, 140, base=50_003, step=45, hi=500, lo=520, growth=1.03)
    bars = _bars_asc(candles)
    r = s.chart_indicators(bars)
    last = enrich(s._build_ohlc_df(list(reversed(candles[:KOJIRO_FETCH_DAYS]))), s._ind_cfg).iloc[-1]
    for k in ("ema_s", "ema_m", "ema_l", "macd1", "macd2", "macd3", "atr"):
        assert r["series"][k][-1] == pytest.approx(float(last[k])), k


def test_p5_etf_trend_uses_core_functions():
    s = EtfTrendStrategy(StrategyConfig(strategy_id="etf_trend", name="etf", params={}, enabled=True))
    bars = _bars_asc(H.trend_series(_HEAD, 260, base=10_000, step=20, hi=80, lo=90))
    r = s.chart_indicators(bars)
    w = bars[-int(s.config.params["daily_fetch_rows"]):]
    highs, lows, closes = [b["high"] for b in w], [b["low"] for b in w], [b["close"] for b in w]
    j = len(w) - 1
    assert r["series"]["breakout_line"][-1] == core.breakout_line(highs, j)
    assert r["series"]["ema60"][-1] == pytest.approx(core.ema(closes, 60)[j])
    assert r["series"]["atr20"][-1] == pytest.approx(core.atr_wilder(core.true_ranges(highs, lows, closes), 20)[j])
    assert r["series"]["channel_low"][-1] == core.channel_low(lows[:-1])


@pytest.mark.parametrize("sid", list(H.STRATEGIES) + ["etf_trend"])
def test_p6_series_shape_and_start_index(sid):
    if sid == "etf_trend":
        s = EtfTrendStrategy(StrategyConfig(strategy_id=sid, name=sid, params={}, enabled=True))
    else:
        s = H.make_strategy(sid)
    bars = _bars_asc(H.trend_series(_HEAD, 300, base=10_000, step=50, hi=30, lo=60))
    r = s.chart_indicators(bars, 200)
    assert r["lines"], sid
    for line in r["lines"]:
        assert line["pane"] in ("price", "atr", "macd")
        vals = r["series"][line["key"]]
        assert len(vals) == len(bars)
        assert all(v is None for v in vals[:200]), (sid, line["key"])
        assert any(v is not None for v in vals[200:]), (sid, line["key"])


def _method_src(cls, name: str) -> str:
    return inspect.getsource(getattr(cls, name))


def test_p7_extracted_helpers_are_used_by_prepare():
    from src.engine.strategies.donchian_swing import DonchianSwingStrategy
    from src.engine.strategies.long_tail_volatility import LongTailVolatilityStrategy
    from src.engine.strategies.vcp_breakout import VcpBreakoutStrategy
    from src.engine.strategies.volatility_breakout import VolatilityBreakoutStrategy

    d = _method_src(DonchianSwingStrategy, "prepare")
    assert "self._prior_high(highs, " in d and "self._ema_recent(closes, " in d
    assert "self._channel_low_of(" in _method_src(DonchianSwingStrategy, "_recompute_channel_low")
    v = _method_src(VcpBreakoutStrategy, "prepare")
    assert "self._daily_fetch_days()" in v and "self._effective_ema_long(" in v
    assert "self._trend_emas(" in _method_src(VcpBreakoutStrategy, "_check_trend_filter")
    for cls in (VolatilityBreakoutStrategy, LongTailVolatilityStrategy):
        p = _method_src(cls, "prepare")
        assert "self._noise_k(" in p and "self._target_offset_base(" in p
        assert "self._board_target_offset(" in _method_src(cls, "on_open_price_confirmed")
    # 차트 메서드에 판정 밖 계산식(직접 max/min/sum)이 없다 — 전략 함수만 부른다
    for cls in (DonchianSwingStrategy, VcpBreakoutStrategy):
        tree = ast.parse(inspect.cleandoc("\n" + _method_src(cls, "chart_indicators")))
        names = {n.func.id for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
        assert not names & {"sum", "min"}, (cls.__name__, names)
