"""kojiro 후보 점수 랭킹 (원설계 §9④) 회귀 가드.

score = w_macd3·norm(macd3기울기) + w_band·norm(띠폭확장) + w_fresh·norm(신선도),
후보 풀 min-max 정규화. **매수 후보 정렬만** — 자격(strict entry)/청산 임계 무변경.
이미 계산되나 dormant 였던 enrich 지표(macd3/band_width)를 배선한다.
"""
from __future__ import annotations

import inspect
from unittest.mock import AsyncMock

import pandas as pd
import pytest

from src.engine.strategies.kojiro import (
    KojiroStrategy, _stage_transition_distance, _RANK_LOOKBACK,
)
from src.engine.strategy_base import StrategyConfig
from src.engine.recommendation_engine import PARAM_RANGES

pytestmark = pytest.mark.unit


def _mk(**params):
    return KojiroStrategy(StrategyConfig(strategy_id="kojiro", name="고지로", weight=0.1, params=params))


# ── (a) 6→1 전환 거리 헬퍼 ──

def test_stage_transition_distance():
    assert _stage_transition_distance([4, 5, 6, 1], 6, 1, 5) == 0   # 마지막 봉으로 전환
    assert _stage_transition_distance([4, 6, 1, 1], 6, 1, 5) == 1   # 전환 후 1봉
    assert _stage_transition_distance([6, 1, 1, 1], 6, 1, 5) == 2
    assert _stage_transition_distance([1, 1, 1], 6, 1, 5) is None   # 전환 없음
    assert _stage_transition_distance([6, 1, 1, 1, 1, 1, 1], 6, 1, 3) is None  # 창 밖
    assert _stage_transition_distance([6, 1, 6, 1], 6, 1, 5) == 0   # 최근 전환 채택(최소 거리)


# ── (b) 점수 계산: min-max 정규화 + 가중합 ──

def test_score_candidates_minmax_weighted():
    s = _mk()  # 기본 0.4/0.3/0.3
    raw = {
        "A": (10.0, 0.5, 4.0),   # 전 성분 최고 → 1.0
        "B": (0.0, 0.0, 0.0),    # 전 성분 최저 → 0.0
        "C": (5.0, 0.25, 2.0),   # 중앙 → 0.5
    }
    sc = s._score_candidates(raw, s.config.params)
    assert sc["A"] == pytest.approx(1.0)
    assert sc["B"] == pytest.approx(0.0)
    assert sc["C"] == pytest.approx(0.5, abs=0.02)


def test_score_single_and_equal_neutral():
    s = _mk()
    assert s._score_candidates({"A": (1.0, 2.0, 3.0)}, s.config.params)["A"] == pytest.approx(0.5)
    eq = s._score_candidates({"A": (1.0, 1.0, 1.0), "B": (1.0, 1.0, 1.0)}, s.config.params)
    assert eq["A"] == pytest.approx(0.5) and eq["B"] == pytest.approx(0.5)


def test_score_weights_normalized_when_sum_ne_one():
    # 합 3 → 각 1/3 로 정규화 → 결과는 균등가중과 동일 (극단은 여전히 1.0/0.0)
    s = _mk(rank_w_macd3=1.0, rank_w_band=1.0, rank_w_fresh=1.0)
    raw = {"A": (10.0, 0.5, 4.0), "B": (0.0, 0.0, 0.0)}
    sc = s._score_candidates(raw, s.config.params)
    assert sc["A"] == pytest.approx(1.0) and sc["B"] == pytest.approx(0.0)


def test_score_empty():
    assert _mk()._score_candidates({}, _mk().config.params) == {}


# ── (c) 컴포넌트 추출 (enrich dormant 지표 배선) ──

def test_rank_components_from_enriched():
    s = _mk()
    # len 5, _RANK_LOOKBACK=3 → li=4, pi=1
    df = pd.DataFrame({
        "macd3": [0.0, 1.0, 2.0, 3.0, 5.0],          # slope = 5 - 1 = 4
        "band_width": [10.0, 10.0, 12.0, 14.0, 15.0],  # exp = (15-10)/10 = 0.5
    })
    stages = [4, 5, 6, 1, 1]                           # 6→1 dist 1 → fresh = 5-1 = 4
    m3s, be, fr = s._rank_candidate_components(df, stages, within=5)
    assert m3s == pytest.approx(4.0)
    assert be == pytest.approx(0.5, abs=0.01)
    assert fr == pytest.approx(4.0)
    assert _RANK_LOOKBACK == 3


def test_rank_components_failsafe_missing_columns():
    # 지표 컬럼 부재(테스트 스텁/방어) → 신선도만, macd3/band=0 (fail-safe, no crash)
    s = _mk()
    df = pd.DataFrame({"close": [1, 2, 3]})
    m3s, be, fr = s._rank_candidate_components(df, [6, 1, 1], within=5)
    assert m3s == 0.0 and be == 0.0
    assert fr == pytest.approx(4.0)   # dist 1 → 5-1


# ── (d) DEFAULT_PARAMS + PARAM_RANGES ──

def test_rank_weights_default_params():
    p = KojiroStrategy.DEFAULT_PARAMS
    assert p["rank_w_macd3"] == 0.4 and p["rank_w_band"] == 0.3 and p["rank_w_fresh"] == 0.3


def test_rank_weights_excluded_from_param_ranges():
    for k in ("rank_w_macd3", "rank_w_band", "rank_w_fresh"):
        assert k not in PARAM_RANGES


# ── (e) 통합: get_scanned_tickers score DESC ──

def _full_enriched(stage_series, macd3, band_width, *, close=10000, atr=200.0):
    n = len(stage_series)
    return pd.DataFrame({
        "close": [close] * n, "atr": [atr] * n, "stage": list(stage_series),
        "ema_s": [9900.0] * n, "ema_m": [9800.0] * n, "ema_l": [9700.0] * n,
        "ema_s_up": [True] * n, "ema_m_up": [True] * n, "ema_l_up": [True] * n,
        "macd3": list(macd3), "band_width": list(band_width),
    })


async def _run_prepare_multi(kojiro, monkeypatch, ordered):
    """ordered = [(ticker, enriched_df), ...] — enrich 를 ticker 순서대로 반환."""
    import src.engine.strategies.kojiro as kmod
    from src.db import stock_master_daily as smd
    tickers = [t for t, _ in ordered]
    monkeypatch.setattr(kojiro, "_scan_universe", AsyncMock(return_value=tickers))
    monkeypatch.setattr(kojiro, "_apply_master_block_filter_in_prepare",
                        AsyncMock(return_value=(tickers, [])))
    monkeypatch.setattr(kojiro, "_fetch_sector", AsyncMock(return_value="미분류"))
    monkeypatch.setattr(smd, "get_recent_daily_normalized",
                        AsyncMock(return_value=[{
                            "stck_bsop_date": "20250101", "stck_oprc": "10000",
                            "stck_hgpr": "10100", "stck_lwpr": "9900",
                            "stck_clpr": "10000", "acml_vol": "1000000",
                        } for _ in range(85)]))
    dfs = iter([df for _, df in ordered])
    monkeypatch.setattr(kmod, "enrich", lambda df, cfg: next(dfs))
    await kojiro.prepare()


async def test_get_scanned_tickers_ranked_desc(kojiro_strat, monkeypatch):
    # T1 최고(가파른 macd3·띠확장·최신 6→1), T3 최저
    ordered = [
        ("T1", _full_enriched([4, 4, 4, 6, 1], [0, 0, 2, 4, 6], [10, 10, 12, 14, 16])),
        ("T2", _full_enriched([4, 4, 6, 1, 1], [0, 0, 1, 2, 3], [10, 10, 11, 12, 13])),
        ("T3", _full_enriched([4, 6, 1, 1, 1], [0, 0, 0, 0, 0], [10, 10, 10, 10, 10])),
    ]
    await _run_prepare_multi(kojiro_strat, monkeypatch, ordered)
    assert kojiro_strat.get_scanned_tickers() == ["T1", "T2", "T3"]
    # score 저장 확인 + 단조
    scores = [kojiro_strat._candidates[t]["score"] for t in ("T1", "T2", "T3")]
    assert scores[0] > scores[1] > scores[2]


# ── (f) 회귀: 후보 ≤ 슬롯(단일) → score 세팅 + set 보존 ──

async def test_single_candidate_preserves_set_and_scores(kojiro_strat, monkeypatch):
    ordered = [("SOLO", _full_enriched([4, 4, 4, 6, 1], [0, 1, 2, 3, 4], [10, 11, 12, 13, 14]))]
    await _run_prepare_multi(kojiro_strat, monkeypatch, ordered)
    assert kojiro_strat.get_scanned_tickers() == ["SOLO"]
    assert "score" in kojiro_strat._candidates["SOLO"]  # 단일 → 0.5 중립
    assert kojiro_strat._candidates["SOLO"]["score"] == pytest.approx(0.5)


# ── (g) SAFETY: 청산 hot path 무접촉 ──

def test_check_exit_has_no_rank_logic():
    src = inspect.getsource(KojiroStrategy.check_exit_signal)
    for tok in ("score", "_score_candidates", "_rank_candidate", "macd3", "band_width"):
        assert tok not in src, f"check_exit_signal 에 랭킹 로직 누출: {tok}"


@pytest.fixture
def kojiro_strat():
    return KojiroStrategy(StrategyConfig(strategy_id="kojiro", name="고지로", weight=0.2))
