"""cycle344 — 대순환 MACD 관측기를 `KojiroStrategy.prepare()` 에 배선한다.

## 무엇을 고치나

cycle340 이 `kojiro_band_observe.observe_macd` 와 그 12원소 행 계약을 만들어 두고
**호출하지 않았다**(그 docstring 이 「의도된 배선 대기」라 적었다). 관측기는 불리지
않으면 표본을 한 줄도 모으지 않으므로, 진입 규약 변경 판단의 근거가 영원히 생기지
않는다. 이 사이클이 그 한 줄을 잇는다.

## 🔴 이 사이클이 바꾸지 않는 것

**매매 행위 0.** 진입·청산·수량·사이징·손절 규약 어느 것도 건드리지 않고
`DEFAULT_PARAMS` 에 키를 더하지 않는다. `prepare()` 의 산출(`get_scanned_tickers()`
순서 · `_candidates` · `_bought_today`)은 관측기가 **터져도** byte 동일해야 한다 —
`test_g344_9_prepare_identical_when_leaf_raises` 가 그 차분을 잰다.

## gc3 의 정의가 계약이다

`gc3` 는 **상태가 아니라 교차 사건(edge)** 이다 — 직전 봉 `macd3 <= sig3` 이고
이번 봉 `macd3 > sig3`. 실측 스크립트(`_workspace/domain_consult/
cycle340_kojiro_macd.md` 의 근거가 된 `macd_rule_compare.py`)가 그렇게 셌고,
`observe_macd` 의 `rule6/5/4` 가 `gc3 and all_up and stage == want` 로 그 값을 바로
쓴다. **상태(`m3 > s3`)로 바꾸면** 교차 다음 날부터 며칠씩 계속 참이라 규칙 발화가
부풀고, 나중에 그 표본으로 판단할 때 실측과 다른 수를 보게 된다.
"""
from __future__ import annotations

import pandas as pd
import pytest
from unittest.mock import AsyncMock

from src.engine.kojiro_band_observe import MACD_MARKER, reset_kojiro_band_observe_cap
from src.engine.strategy_base import StrategyConfig

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _fresh_cap():
    reset_kojiro_band_observe_cap()
    yield
    reset_kojiro_band_observe_cap()


def _mk():
    from src.engine.strategies.kojiro import KojiroStrategy
    return KojiroStrategy(
        StrategyConfig(strategy_id="kojiro", name="고지로", weight=0.2))


def _parse(line: str) -> dict[str, str]:
    body = line[line.index(MACD_MARKER) + len(MACD_MARKER):]
    return dict(tok.split("=", 1) for tok in body.split() if "=" in tok)


def _rows(caplog) -> list[dict[str, str]]:
    return [_parse(r.message) for r in caplog.records if MACD_MARKER in r.message]


# ── 행 조립 헬퍼 — 값 계약 ────────────────────────────────────────────────


def _df(macd1, macd2, macd3, sig1, sig2, sig3, *, stage=1, n=None):
    n = n or len(macd3)
    return pd.DataFrame({
        "close": [10000.0] * n, "atr": [200.0] * n, "stage": [stage] * n,
        "ema_s": [9900.0] * n, "ema_m": [9800.0] * n, "ema_l": [9700.0] * n,
        "ema_s_up": [True] * n, "ema_m_up": [True] * n, "ema_l_up": [True] * n,
        "band_width": [10.0] * n,
        "macd1": [float(x) for x in macd1],
        "macd2": [float(x) for x in macd2],
        "macd3": [float(x) for x in macd3],
        "macd1_sig": [float(x) for x in sig1],
        "macd2_sig": [float(x) for x in sig2],
        "macd3_sig": [float(x) for x in sig3],
    })


def test_g344_1_row_has_the_twelve_element_contract():
    """행 계약 = `(stage, m1, m2, m3, s1, s2, s3, gc3, bars_since, m1_up, m2_up, m3_up)`."""
    s = _mk()
    df = _df([1, 2, 3], [1, 2, 4], [0, 1, 2], [1, 1, 1], [1, 1, 1], [1, 1, 1], stage=1)
    row = s._macd_observe_row(df, 1)
    assert isinstance(row, tuple) and len(row) == 12
    stage, m1, m2, m3, s1, s2, s3, gc3, bars, u1, u2, u3 = row
    assert (stage, m1, m2, m3) == (1, 3.0, 4.0, 2.0)
    assert (s1, s2, s3) == (1.0, 1.0, 1.0)
    assert (u1, u2, u3) == (True, True, True)


def test_g344_2_golden_cross_is_an_edge_not_a_state():
    """🔴 직전 봉이 시그널 **아래**였을 때만 참이다 — 계속 위면 거짓."""
    s = _mk()
    crossed = _df([1] * 3, [1] * 3, [0, 0, 2], [0] * 3, [0] * 3, [1, 1, 1])
    assert s._macd_observe_row(crossed, 1)[7] is True, "교차한 봉인데 gc3 가 거짓이다"

    already = _df([1] * 3, [1] * 3, [2, 3, 4], [0] * 3, [0] * 3, [1, 1, 1])
    assert s._macd_observe_row(already, 1)[7] is False, (
        "직전 봉도 이미 시그널 위였다 — 교차가 아니라 상태다")


def test_g344_3_bars_since_counts_back_to_the_last_cross():
    s = _mk()
    # 교차는 index 1 에서 한 번(0 → 아래, 1 → 위), 이후 계속 위.
    df = _df([1] * 5, [1] * 5, [0, 2, 3, 4, 5], [0] * 5, [0] * 5, [1] * 5)
    row = s._macd_observe_row(df, 1)
    assert row[7] is False
    assert row[8] == 3, f"마지막 교차는 3봉 전인데 {row[8]}"


def test_g344_4_bars_since_is_none_when_no_cross_in_window():
    s = _mk()
    df = _df([1] * 4, [1] * 4, [5, 5, 5, 5], [0] * 4, [0] * 4, [1] * 4)
    assert s._macd_observe_row(df, 1)[8] is None


@pytest.mark.parametrize("m3_series, expect_up", [([1, 2], True), ([2, 1], False), ([2, 2], False)])
def test_g344_5_rising_flag_compares_last_two_bars(m3_series, expect_up):
    s = _mk()
    df = _df([1] * 2, [1] * 2, m3_series, [0] * 2, [0] * 2, [0] * 2)
    assert s._macd_observe_row(df, 1)[11] is expect_up


@pytest.mark.parametrize("broken", [
    None, "셋업이 아님", 123,
    pd.DataFrame({"close": [1.0]}),                       # macd 컬럼 전무
    pd.DataFrame({"macd3": [1.0], "macd3_sig": [0.0]}),   # 일부만
])
def test_g344_6_row_never_raises(broken):
    """🔴 `prepare` 의 ticker 루프와 같은 try 스코프라, 던지면 그 종목의 **매수 후보
    처리 자체가 스킵**된다 = 행위 변경."""
    s = _mk()
    row = s._macd_observe_row(broken, 1)
    assert isinstance(row, tuple) and len(row) == 12


# ── 배선 — prepare 가 실제로 부른다 ───────────────────────────────────────


async def _run_prepare(strat, monkeypatch, *, break_leaf=False, macd_cols=True):
    import src.engine.strategies.kojiro as kmod
    from src.db import stock_master_daily as smd

    def _full(stage_series, macd3, band_width):
        n = len(stage_series)
        base = {
            "close": [10000.0] * n, "atr": [200.0] * n, "stage": list(stage_series),
            "ema_s": [9900.0] * n, "ema_m": [9800.0] * n, "ema_l": [9700.0] * n,
            "ema_s_up": [True] * n, "ema_m_up": [True] * n, "ema_l_up": [True] * n,
            "macd3": [float(x) for x in macd3],
            "band_width": [float(x) for x in band_width],
        }
        if macd_cols:
            base |= {
                "macd1": [float(x) + 1 for x in macd3],
                "macd2": [float(x) + 2 for x in macd3],
                "macd1_sig": [0.5] * n, "macd2_sig": [0.5] * n,
                "macd3_sig": [0.5] * n,
            }
        return pd.DataFrame(base)

    ordered = [
        ("T1", _full([4, 4, 4, 6, 1], [0, 0, 2, 4, 6], [10, 10, 12, 14, 16])),
        ("T2", _full([4, 4, 6, 1, 1], [0, 0, 1, 2, 3], [10, 10, 11, 12, 13])),
    ]
    tickers = [t for t, _ in ordered]
    monkeypatch.setattr(strat, "_scan_universe", AsyncMock(return_value=tickers))
    monkeypatch.setattr(strat, "_apply_master_block_filter_in_prepare",
                        AsyncMock(return_value=(tickers, [])))
    monkeypatch.setattr(strat, "_fetch_sector", AsyncMock(return_value="미분류"))
    monkeypatch.setattr(smd, "get_recent_daily_normalized", AsyncMock(return_value=[{
        "stck_bsop_date": "20250101", "stck_oprc": "10000", "stck_hgpr": "10100",
        "stck_lwpr": "9900", "stck_clpr": "10000", "acml_vol": "1000000",
    } for _ in range(85)]))
    dfs = iter([df for _, df in ordered])
    monkeypatch.setattr(kmod, "enrich", lambda df, cfg: next(dfs))
    if break_leaf:
        def _boom(*a, **k):
            raise RuntimeError("macd leaf exploded")
        monkeypatch.setattr(kmod, "observe_macd", _boom, raising=False)
    await strat.prepare()
    return (
        list(strat.get_scanned_tickers()),
        {t: repr(v) for t, v in strat._candidates.items()},
        set(strat._bought_today),
    )


async def test_g344_7_prepare_emits_the_marker(monkeypatch, caplog):
    """🔴 배선 자체의 단언 — 이것이 없으면 「아예 안 부른다」가 조용히 통과한다."""
    import logging
    caplog.set_level(logging.WARNING, logger="src.engine.kojiro_band_observe")
    await _run_prepare(_mk(), monkeypatch)
    rows = _rows(caplog)
    assert rows, "prepare 가 MACD 관측 행을 한 줄도 남기지 않았다 — 미배선"
    assert {r["ticker"] for r in rows} == {"T1", "T2"}
    assert all(r["role"] == "candidate" for r in rows)


async def test_g344_8_row_values_come_from_the_enriched_frame(monkeypatch, caplog):
    """값이 실제 지표 프레임에서 온다 — 상수·0 으로 위장되지 않는다."""
    import logging
    caplog.set_level(logging.WARNING, logger="src.engine.kojiro_band_observe")
    await _run_prepare(_mk(), monkeypatch)
    by_t = {r["ticker"]: r for r in _rows(caplog)}
    # T1 의 마지막 봉 macd3=6 → macd1=7, macd2=8, 시그널 전부 0.5
    assert (by_t["T1"]["m1"], by_t["T1"]["m2"], by_t["T1"]["m3"]) == ("7.00", "8.00", "6.00")
    assert by_t["T1"]["s3"] == "0.50"
    assert by_t["T1"]["hist3"] == "5.50"
    assert by_t["T1"]["m3_up"] == "1"
    # T2 마지막 봉 macd3=3
    assert by_t["T2"]["m3"] == "3.00"


async def test_g344_9_prepare_identical_when_leaf_raises(monkeypatch):
    """🔴 이 사이클의 제1 계약 — 관측기가 터져도 매매 산출이 **완전 동일**하다."""
    ok = await _run_prepare(_mk(), monkeypatch, break_leaf=False)
    broken = await _run_prepare(_mk(), monkeypatch, break_leaf=True)
    assert ok == broken, "관측기 예외가 prepare 산출을 바꿨다"


async def test_g344_10_missing_macd_columns_do_not_break_prepare(monkeypatch, caplog):
    """지표 프레임에 MACD 컬럼이 없어도 후보 산출은 그대로다(fail-open).

    `enrich` 가 컬럼을 늘 주지만, 그 계약을 관측기가 **인질로 잡으면 안 된다**.
    """
    with_cols = await _run_prepare(_mk(), monkeypatch, macd_cols=True)
    without = await _run_prepare(_mk(), monkeypatch, macd_cols=False)
    assert with_cols == without


async def test_g344_12_macd_call_failure_is_attributed_to_the_macd_marker(monkeypatch, caplog):
    """🔴 MACD 관측기가 죽으면 **MACD 마커**로 흔적이 남아야 한다.

    초판은 `absorb_band_call_failure` 를 재사용했다. 그러면 MACD 가 죽은 것을 **밴드
    관측기가 죽었다고** 기록한다 — D+1 에 무엇이 멈췄는지 가릴 수 없고, 그 오귀인이
    관측기를 두는 이유 자체를 없앤다.
    """
    import logging

    from src.engine.kojiro_band_observe import MARKER as BAND_MARKER
    caplog.set_level(logging.DEBUG)
    await _run_prepare(_mk(), monkeypatch, break_leaf=True)
    traces = [r.message for r in caplog.records if "observer_failed" in r.message]
    assert any(MACD_MARKER in m for m in traces), (
        f"MACD 호출 실패 흔적이 MACD 마커로 안 남았다 — {traces}")
    assert not any(BAND_MARKER in m for m in traces), (
        "MACD 실패를 밴드 관측기 실패로 기록했다 — 오귀인")


async def test_g344_11_held_only_tickers_are_observed_as_held(monkeypatch, caplog):
    """보유 전용(후보 자격 상실) 종목도 role=held 로 남는다 — band 관측과 같은 축."""
    import logging
    caplog.set_level(logging.WARNING, logger="src.engine.kojiro_band_observe")
    strat = _mk()
    from src.engine.strategy_base import Position
    from datetime import date
    strat.state.positions["T1"] = Position(
        ticker="T1", buy_price=10000, quantity=1, order_no="o",
        strategy_id="kojiro", buy_date=date(2026, 9, 1))
    await _run_prepare(strat, monkeypatch)
    roles = {r["ticker"]: r["role"] for r in _rows(caplog)}
    assert roles.get("T2") == "candidate"
    assert "T1" in roles, "보유 종목이 관측에서 빠졌다"
