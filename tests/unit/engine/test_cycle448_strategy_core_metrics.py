"""cycle448 — 전략별 핵심값 분포 leaf (`src/engine/strategy_core_metrics.py`).

사용자 결정(2026-10-11): 「주간 자문에는 전략 핵심값 분포가 필요하다」.
전략마다 그날 후보·보유 종목의 `llm_context(ticker)` 값을 모아 키별 분포(숫자 6개 요약
또는 범주 빈도표)를 낸다. never-raise + 매매 경로 무접촉(duck-typing, `src.*` import 0).
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.engine import strategy_core_metrics as scm

pytestmark = pytest.mark.unit


# ─────────────────────────────────────────────────────────────────────────────
# 순수 함수 — 숫자 분포
# ─────────────────────────────────────────────────────────────────────────────

def test_summarize_numeric_basic_six_fields():
    out = scm.summarize_numeric([1, 2, 3, 4, 5])
    assert out == {
        "kind": "numeric", "n": 5, "median": 3.0, "p25": 2.0, "p75": 4.0, "min": 1.0, "max": 5.0,
    }


def test_summarize_numeric_single_value():
    out = scm.summarize_numeric([42])
    assert out["n"] == 1
    assert out["median"] == out["p25"] == out["p75"] == out["min"] == out["max"] == 42.0


def test_summarize_numeric_empty_is_none():
    assert scm.summarize_numeric([]) is None


def test_summarize_numeric_ignores_nonfinite_and_bool():
    out = scm.summarize_numeric([1, 2, float("nan"), float("inf"), True, False, 3])
    assert out["n"] == 3, out
    assert out["min"] == 1.0 and out["max"] == 3.0


def test_summarize_numeric_payload_size_is_fixed_regardless_of_sample_count():
    small = scm.summarize_numeric([1, 2, 3])
    large = scm.summarize_numeric(list(range(1, 501)))
    assert set(small) == set(large) == {"kind", "n", "median", "p25", "p75", "min", "max"}


# ─────────────────────────────────────────────────────────────────────────────
# 순수 함수 — 범주 빈도표
# ─────────────────────────────────────────────────────────────────────────────

def test_summarize_categorical_counts():
    out = scm.summarize_categorical(["2x", "1x", "2x", "2x"])
    assert out == {"kind": "categorical", "n": 4, "counts": {"2x": 3, "1x": 1}}


def test_summarize_categorical_skips_none_and_empty_is_none():
    assert scm.summarize_categorical([None, None]) is None
    out = scm.summarize_categorical([None, "a"])
    assert out == {"kind": "categorical", "n": 1, "counts": {"a": 1}}


# ─────────────────────────────────────────────────────────────────────────────
# build_key_distributions — 숫자 vs 범주 자동 분류
# ─────────────────────────────────────────────────────────────────────────────

def test_build_key_distributions_classifies_numeric_and_categorical_separately():
    rows = [
        {"atr": 120.0, "stage": 3, "cell": "B2"},
        {"atr": 150.0, "stage": 6, "cell": "A1"},
        {"atr": 90.0, "stage": 3},
    ]
    out = scm.build_key_distributions(rows)
    assert out["atr"]["kind"] == "numeric" and out["atr"]["n"] == 3
    assert out["stage"]["kind"] == "numeric" and out["stage"]["n"] == 3
    assert out["cell"]["kind"] == "categorical" and out["cell"]["counts"] == {"B2": 1, "A1": 1}


def test_build_key_distributions_mixed_type_key_falls_back_to_categorical():
    rows = [{"k": 1}, {"k": "oops"}, {"k": 2}]
    out = scm.build_key_distributions(rows)
    assert out["k"]["kind"] == "categorical"
    assert out["k"]["n"] == 3


def test_build_key_distributions_ignores_none_and_non_dict_rows():
    rows = [{"a": 1}, None, {"a": None}, "not-a-dict", {}]
    out = scm.build_key_distributions(rows)
    assert out == {"a": {"kind": "numeric", "n": 1, "median": 1.0, "p25": 1.0, "p75": 1.0, "min": 1.0, "max": 1.0}}


def test_build_key_distributions_empty_rows_is_empty_dict():
    assert scm.build_key_distributions([]) == {}


# ─────────────────────────────────────────────────────────────────────────────
# 수집기 — 가짜 전략 (duck typing)
# ─────────────────────────────────────────────────────────────────────────────

class _Pos:
    def __init__(self, buy_price):
        self.buy_price = buy_price


def _strategy(
    *, strategy_id="fake", scanned=(), llm_context_map=None, positions=None, fixed_ticker=None,
    scanned_raises=False, llm_context_raises_for=(),
):
    llm_context_map = llm_context_map or {}

    def _get_scanned():
        if scanned_raises:
            raise RuntimeError("boom")
        return list(scanned)

    def _llm_context(ticker):
        if ticker in llm_context_raises_for:
            raise RuntimeError("boom")
        return dict(llm_context_map.get(ticker, {}))

    ns = SimpleNamespace(
        strategy_id=strategy_id,
        get_scanned_tickers=_get_scanned,
        llm_context=_llm_context,
        state=SimpleNamespace(positions=positions or {}),
    )
    if fixed_ticker is not None:
        ns.FIXED_TICKER = fixed_ticker
    return ns


def test_collect_candidates_and_holdings_build_separate_distributions():
    strat = _strategy(
        scanned=["A", "B"],
        llm_context_map={
            "A": {"atr14": 100.0, "ema50": 1000.0},
            "B": {"atr14": 200.0},
            "H1": {"atr14": 50.0},
        },
        positions={"H1": _Pos(buy_price=10000.0)},
    )
    out = scm.collect_strategy_core_metrics(strat)
    assert out["candidates"]["n_tickers"] == 2
    assert out["candidates"]["n_with_context"] == 2
    assert out["candidates"]["keys"]["atr14"]["n"] == 2
    assert "ema50" in out["candidates"]["keys"]

    assert out["holdings"]["n_tickers"] == 1
    assert out["holdings"]["n_with_context"] == 1
    hk = out["holdings"]["keys"]
    assert hk["atr14"]["n"] == 1
    # 보유는 매수가 대비 ATR 비율이 더해진다 — 50/10000*100 = 0.5%
    assert hk["atr14_pct_of_buy_price"]["n"] == 1
    assert hk["atr14_pct_of_buy_price"]["median"] == 0.5


def test_candidates_without_context_are_excluded_from_distribution_but_counted():
    strat = _strategy(scanned=["A", "B"], llm_context_map={"A": {"atr": 10.0}})
    out = scm.collect_strategy_core_metrics(strat)
    assert out["candidates"]["n_tickers"] == 2
    assert out["candidates"]["n_with_context"] == 1, "B 는 llm_context 가 빈 dict"
    assert out["candidates"]["keys"]["atr"]["n"] == 1


def test_fixed_ticker_fallback_when_get_scanned_tickers_is_empty():
    """ndx2x_riskoff 류 — get_scanned_tickers() 가 항상 빈 목록인 1종목 전략."""
    strat = _strategy(scanned=[], fixed_ticker="418660", llm_context_map={"418660": {"t7": 1.2}})
    out = scm.collect_strategy_core_metrics(strat)
    assert out["candidates"]["n_tickers"] == 1
    assert out["candidates"]["keys"]["t7"]["n"] == 1


def test_momentum_like_strategy_without_overrides_yields_empty_keys():
    """momentum 은 llm_context 를 재정의하지 않는다 — 항상 빈 dict."""
    strat = _strategy(scanned=["A", "B", "C"], llm_context_map={})
    out = scm.collect_strategy_core_metrics(strat)
    assert out["candidates"]["n_tickers"] == 3
    assert out["candidates"]["n_with_context"] == 0
    assert out["candidates"]["keys"] == {}


def test_no_get_scanned_tickers_and_no_fixed_ticker_is_empty_candidates():
    ns = SimpleNamespace(strategy_id="bare", state=SimpleNamespace(positions={}))
    out = scm.collect_strategy_core_metrics(ns)
    assert out["candidates"] == {"n_tickers": 0, "n_with_context": 0, "keys": {}}
    assert out["holdings"] == {"n_tickers": 0, "n_with_context": 0, "keys": {}}


def test_never_raise_on_scanned_tickers_exception():
    strat = _strategy(scanned_raises=True, fixed_ticker=None)
    out = scm.collect_strategy_core_metrics(strat)
    assert out["candidates"]["n_tickers"] == 0


def test_never_raise_on_llm_context_exception_for_one_ticker_does_not_kill_others():
    strat = _strategy(
        scanned=["A", "B"],
        llm_context_map={"B": {"atr": 5.0}},
        llm_context_raises_for=("A",),
    )
    out = scm.collect_strategy_core_metrics(strat)
    assert out["candidates"]["n_tickers"] == 2
    assert out["candidates"]["n_with_context"] == 1
    assert out["candidates"]["keys"]["atr"]["n"] == 1


def test_never_raise_on_totally_broken_strategy_object():
    class _Broken:
        strategy_id = "broken"

        def __getattr__(self, name):
            raise RuntimeError("always broken")

    out = scm.collect_strategy_core_metrics(_Broken())
    assert out == {
        "candidates": {"n_tickers": 0, "n_with_context": 0, "keys": {}},
        "holdings": {"n_tickers": 0, "n_with_context": 0, "keys": {}},
    }


def test_buy_price_missing_or_nonpositive_skips_ratio_augmentation():
    strat = _strategy(
        scanned=[],
        llm_context_map={"H1": {"atr": 10.0}, "H2": {"atr": 20.0}},
        positions={"H1": _Pos(buy_price=0), "H2": _Pos(buy_price=None)},
    )
    out = scm.collect_strategy_core_metrics(strat)
    hk = out["holdings"]["keys"]
    assert hk["atr"]["n"] == 2
    assert "atr_pct_of_buy_price" not in hk


def test_collect_all_core_metrics_isolates_per_strategy_failures():
    good = _strategy(strategy_id="good", scanned=["A"], llm_context_map={"A": {"atr": 1.0}})

    class _BadStrategy:
        strategy_id = "bad"

        def __getattr__(self, name):
            raise RuntimeError("boom")

    out = scm.collect_all_core_metrics([good, _BadStrategy()])
    assert set(out) == {"good", "bad"}
    assert out["good"]["candidates"]["keys"]["atr"]["n"] == 1
    assert out["bad"]["candidates"] == {"n_tickers": 0, "n_with_context": 0, "keys": {}}


def test_collect_all_core_metrics_skips_entries_without_strategy_id():
    out = scm.collect_all_core_metrics([SimpleNamespace(strategy_id=123), SimpleNamespace()])
    assert out == {}


def test_has_any_keys():
    empty = {"candidates": {"n_tickers": 0, "n_with_context": 0, "keys": {}},
              "holdings": {"n_tickers": 0, "n_with_context": 0, "keys": {}}}
    assert scm.has_any_keys(empty) is False
    assert scm.has_any_keys(None) is False
    full = {"candidates": {"keys": {"atr": {"kind": "numeric"}}}, "holdings": {"keys": {}}}
    assert scm.has_any_keys(full) is True
