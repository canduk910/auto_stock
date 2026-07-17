"""고지로 대순환 스윙 전략 (`src/engine/strategies/kojiro.py`) 회귀 테스트.

검증 포인트 (계획 §6):
- prepare: strict entry (스테이지1+6→1인접+3선우상향+종가>EMA5) + ATR밴드 게이트 + 보유 stage3 마킹.
  (지표 수학은 kojiro_indicators 골든이 검증 → 여기선 enrich 패치로 결정 로직 결정론 검증)
- check_buy: 09:05~09:30 KST 시각독립 + 갭업/갭다운/붕괴 스킵 + stage!=1 미매수.
- check_exit: 우선순위(고정%→2ATR→stage3→트레일) + ATR `_candidates` 소스(당일매수 커버)
  + ATR=0 고정% backstop + tighten-only floor + 일봉fetch/enrich/pandas 0건.
- 멀티데이: check_force_clear==[] + on_position_closed pop.
"""

from __future__ import annotations

import ast
from datetime import datetime, timezone, timedelta

import pandas as pd
import pytest
from freezegun import freeze_time

from src.engine.strategies.kojiro import KojiroStrategy, FUNNEL_STAGES, _stage_recently
from src.engine.strategy_base import Position, Signal, StrategyConfig

pytestmark = pytest.mark.unit

KST = timezone(timedelta(hours=9))


@pytest.fixture
def kojiro():
    return KojiroStrategy(StrategyConfig(strategy_id="kojiro", name="고지로 대순환", weight=0.2))


def _seed_candidate(strategy, ticker, *, prev_close=10000, atr=200.0, stage=1,
                    ema_s=9900.0, ema_m=9800.0, ema_l=9700.0):
    strategy._candidates[ticker] = {
        "prev_close": prev_close, "atr": atr, "stage": stage,
        "ema_s": ema_s, "ema_m": ema_m, "ema_l": ema_l,
        "atr_ratio": atr / prev_close,
    }


def _pos(strategy, ticker, *, buy_price=10000, high_since_buy=0, buy_date=None):
    p = Position(
        ticker=ticker, buy_price=buy_price, quantity=10, order_no="O1",
        strategy_id="kojiro",
        buy_date=buy_date or datetime.now(KST).date(),
        high_since_buy=high_since_buy,
    )
    strategy.state.positions[ticker] = p
    return p


def _enriched(stage_series, *, close=10000, atr=200.0, ema_s=9900.0,
              ema_m=9800.0, ema_l=9700.0, all_up=True):
    """enrich 반환 대체 DataFrame — 전략 결정 로직 결정론 검증용."""
    n = len(stage_series)
    return pd.DataFrame({
        "close": [close] * n, "atr": [atr] * n, "stage": list(stage_series),
        "ema_s": [ema_s] * n, "ema_m": [ema_m] * n, "ema_l": [ema_l] * n,
        "ema_s_up": [all_up] * n, "ema_m_up": [all_up] * n, "ema_l_up": [all_up] * n,
    })


def _dummy_candles(n=85):
    # DESC (idx0=최신). 날짜는 오늘 아님 → prev_idx=0.
    return [{
        "stck_bsop_date": "20250101", "stck_oprc": "10000", "stck_hgpr": "10100",
        "stck_lwpr": "9900", "stck_clpr": "10000", "acml_vol": "1000000",
    } for _ in range(n)]


async def _run_prepare(kojiro, monkeypatch, ticker, enriched_df):
    """공통: _scan_universe/master_block/일봉/enrich 패치 후 prepare 실행."""
    from unittest.mock import AsyncMock
    import src.engine.strategies.kojiro as kmod
    monkeypatch.setattr(kojiro, "_scan_universe", AsyncMock(return_value=[ticker]))
    monkeypatch.setattr(kojiro, "_apply_master_block_filter_in_prepare",
                        AsyncMock(return_value=([ticker], [])))
    monkeypatch.setattr("src.db.stock_master_daily.get_recent_daily_normalized",
                        AsyncMock(return_value=_dummy_candles()))
    monkeypatch.setattr(kmod, "enrich", lambda df, cfg: enriched_df)
    await kojiro.prepare()


# ── DEFAULT_PARAMS / 상수 ──

def test_default_params_identity_constants():
    p = KojiroStrategy.DEFAULT_PARAMS
    assert p["tradable_boards"] == ["main"]
    assert (p["ema_short"], p["ema_mid"], p["ema_long"]) == (5, 20, 40)
    assert p["atr_period"] == 20
    assert p["stop_atr"] == 2.0 and p["trail_atr"] == 2.5
    assert p["hard_stop_pct"] == -8.0
    assert p["atr_ratio_min"] == 0.01 and p["atr_ratio_max"] == 0.045
    assert p["gap_up_skip_pct"] == 5.0 and p["gap_down_skip_pct"] == -4.0
    # obs-M: atr_trail_mult(전역 PARAM_RANGES 키) 재사용 금지
    assert "atr_trail_mult" not in p
    assert len(FUNNEL_STAGES) == 9


def test_stage_recently_adjacent_transition():
    assert _stage_recently([5, 6, 1], 6, 1, 3) is True
    assert _stage_recently([6, 2, 1], 6, 1, 3) is False   # 인접 아님
    assert _stage_recently([1, 1, 1], 6, 1, 3) is False
    assert _stage_recently([6, 1, 1, 1, 1], 6, 1, 3) is False  # within=3 밖


# ── prepare: strict entry 등록 ──

async def test_prepare_registers_fresh_stage1_61_candidate(kojiro, monkeypatch):
    await _run_prepare(kojiro, monkeypatch, "005930",
                       _enriched([2, 3, 6, 1], close=10000, atr=200.0))
    assert "005930" in kojiro._candidates
    info = kojiro._candidates["005930"]
    assert info["stage"] == 1
    assert kojiro.get_scan_stats()["strict_entry_pass"] == 1
    assert kojiro.get_scan_stats()["final_prepared"] == 1


async def test_prepare_excludes_band_out_of_range(kojiro, monkeypatch):
    # ATR/종가 = 600/10000 = 6% > 4.5% → 밴드 탈락
    await _run_prepare(kojiro, monkeypatch, "005930",
                       _enriched([6, 1], close=10000, atr=600.0))
    assert "005930" not in kojiro._candidates
    assert kojiro.get_scan_stats()["band_pass"] == 0


async def test_prepare_excludes_no_61_transition(kojiro, monkeypatch):
    # 스테이지1이지만 6→1 인접 없음 (오래 머문 stage1) → strict 탈락
    await _run_prepare(kojiro, monkeypatch, "005930",
                       _enriched([1, 1, 1, 1], close=10000, atr=200.0))
    assert "005930" not in kojiro._candidates
    assert kojiro.get_scan_stats()["stage1_uptrend_pass"] == 1  # stage1+allup 통과
    assert kojiro.get_scan_stats()["strict_entry_pass"] == 0    # 6→1 인접 실패


async def test_prepare_excludes_stage_none_tie(kojiro, monkeypatch):
    await _run_prepare(kojiro, monkeypatch, "005930",
                       _enriched([6, None], close=10000, atr=200.0))
    assert "005930" not in kojiro._candidates
    assert kojiro.get_scan_stats()["stage_valid_pass"] == 0


async def test_prepare_marks_held_stage3_even_if_not_buy_candidate(kojiro, monkeypatch):
    _pos(kojiro, "005930", buy_price=10000)
    # 보유 + stage3 → 매수후보 아니지만 _candidates(exit용) + _held_stage3=True
    await _run_prepare(kojiro, monkeypatch, "005930",
                       _enriched([2, 3], close=10000, atr=200.0))
    assert "005930" in kojiro._candidates        # exit ATR/stage 소스
    assert kojiro._held_stage3["005930"] is True
    assert kojiro.get_scan_stats()["strict_entry_pass"] == 0  # 매수후보 아님


# ── check_buy_signal ──

def test_buy_within_kst_window_no_gap(kojiro):
    _seed_candidate(kojiro, "005930", prev_close=10000)
    with freeze_time(datetime(2026, 5, 8, 9, 10, tzinfo=KST)):
        assert kojiro.check_buy_signal("005930", 10100, 10050) == Signal.BUY
    assert "005930" in kojiro._bought_today


def test_buy_before_0905_kst_none(kojiro):
    _seed_candidate(kojiro, "005930")
    with freeze_time(datetime(2026, 5, 8, 9, 4, tzinfo=KST)):
        assert kojiro.check_buy_signal("005930", 10100, 10050) == Signal.NONE


def test_buy_after_0930_kst_none(kojiro):
    _seed_candidate(kojiro, "005930")
    with freeze_time(datetime(2026, 5, 8, 9, 31, tzinfo=KST)):
        assert kojiro.check_buy_signal("005930", 10100, 10050) == Signal.NONE


def test_buy_time_gate_is_kst_aware_not_naive(kojiro):
    # KST 09:10 == UTC 00:10. naive 코드라면 UTC 00:10 로 창 밖 → NONE 오작동.
    # KST-aware 라면 09:10 → BUY. (entry-L: naive datetime.now() 금지 증명)
    _seed_candidate(kojiro, "005930", prev_close=10000)
    with freeze_time(datetime(2026, 5, 8, 0, 10, tzinfo=timezone.utc)):
        assert kojiro.check_buy_signal("005930", 10100, 10050) == Signal.BUY


def test_buy_gap_up_skip_and_marked(kojiro):
    _seed_candidate(kojiro, "005930", prev_close=10000)
    with freeze_time(datetime(2026, 5, 8, 9, 10, tzinfo=KST)):
        # 시가 10600 → 갭 +6% ≥ 5% → 스킵 + 영구 마킹
        assert kojiro.check_buy_signal("005930", 10700, 10600) == Signal.NONE
    assert "005930" in kojiro._bought_today


def test_buy_gap_down_skip_and_marked(kojiro):
    _seed_candidate(kojiro, "005930", prev_close=10000)
    with freeze_time(datetime(2026, 5, 8, 9, 10, tzinfo=KST)):
        # 시가 9500 → 갭 -5% ≤ -4% → 스킵 (falling knife 방어)
        assert kojiro.check_buy_signal("005930", 9550, 9500) == Signal.NONE
    assert "005930" in kojiro._bought_today


def test_buy_collapsing_below_open_transient_none(kojiro):
    _seed_candidate(kojiro, "005930", prev_close=10000)
    with freeze_time(datetime(2026, 5, 8, 9, 10, tzinfo=KST)):
        # 현재가 < 시가 (붕괴 중) → transient NONE, 마킹 안 함(창 내 재시도)
        assert kojiro.check_buy_signal("005930", 9900, 10050) == Signal.NONE
    assert "005930" not in kojiro._bought_today


def test_buy_stage_not_1_none(kojiro):
    # 보유 재채움된 stage3 데이터는 매수 후보 아님
    _seed_candidate(kojiro, "005930", stage=3)
    with freeze_time(datetime(2026, 5, 8, 9, 10, tzinfo=KST)):
        assert kojiro.check_buy_signal("005930", 10100, 10050) == Signal.NONE


def test_buy_gates_position_pending_soldtoday(kojiro):
    _seed_candidate(kojiro, "005930")
    with freeze_time(datetime(2026, 5, 8, 9, 10, tzinfo=KST)):
        _pos(kojiro, "005930")
        assert kojiro.check_buy_signal("005930", 10100, 10050) == Signal.NONE
        del kojiro.state.positions["005930"]
        kojiro.state.sold_today.add("005930")
        assert kojiro.check_buy_signal("005930", 10100, 10050) == Signal.NONE


# ── check_exit_signal (우선순위 + ATR 소스) ──

def test_exit_fixed_pct_hard_stop_first(kojiro):
    _pos(kojiro, "005930", buy_price=10000)
    # ATR 없음(_candidates 미존재)이어도 -8% 고정 backstop 발화
    assert kojiro.check_exit_signal("005930", 9100, 0) == Signal.STOP_LOSS


def test_exit_atr_stop_from_candidates_covers_same_day_buy(kojiro):
    # ★ safety-H1: 당일 매수 종목도 _candidates ATR 로 즉시 손절 커버
    _pos(kojiro, "005930", buy_price=10000)
    _seed_candidate(kojiro, "005930", atr=200.0)  # 2ATR stop = 10000-400 = 9600
    # -8% 미도달(9700>9200)이지만 2ATR(9600) 도달
    assert kojiro.check_exit_signal("005930", 9600, 0) == Signal.STOP_LOSS


def test_exit_atr_zero_falls_back_to_fixed_pct(kojiro):
    # ★ restart-H1: ATR=0(재계산 실패) → 2ATR 무력 → 고정% backstop 만 유지
    _pos(kojiro, "005930", buy_price=10000)  # _candidates 없음 → atr=0
    assert kojiro.check_exit_signal("005930", 9500, 0) == Signal.NONE   # -5% > -8%
    assert kojiro.check_exit_signal("005930", 9200, 0) == Signal.STOP_LOSS  # -8%


def test_exit_atr_stop_tighten_only_floor(kojiro):
    # ★ restart-H3: 변동성 팽창(ATR↑)에도 손절선 loosen 금지
    _pos(kojiro, "005930", buy_price=10000)
    _seed_candidate(kojiro, "005930", atr=200.0)  # base=9600 → floor=9600
    assert kojiro.check_exit_signal("005930", 9700, 0) == Signal.NONE  # 9700>9600
    # ATR 팽창 450 → base=9100 (looser) 이지만 floor=9600 유지
    kojiro._candidates["005930"]["atr"] = 450.0
    assert kojiro.check_exit_signal("005930", 9550, 0) == Signal.STOP_LOSS  # 9550<=9600(floor)


def test_exit_stage3_trailing_stop(kojiro):
    _pos(kojiro, "005930", buy_price=10000, high_since_buy=10000)
    _seed_candidate(kojiro, "005930", atr=200.0)
    kojiro._held_stage3["005930"] = True
    # -8%/2ATR/트레일 미도달이어도 stage3 → 청산
    assert kojiro.check_exit_signal("005930", 9800, 0) == Signal.TRAILING_STOP


def test_exit_chandelier_trailing(kojiro):
    _pos(kojiro, "005930", buy_price=10000, high_since_buy=12000)
    _seed_candidate(kojiro, "005930", atr=200.0)  # trail = 12000 - 2.5*200 = 11500
    assert kojiro.check_exit_signal("005930", 11600, 0) == Signal.NONE
    assert kojiro.check_exit_signal("005930", 11500, 0) == Signal.TRAILING_STOP


def test_exit_none_when_healthy(kojiro):
    _pos(kojiro, "005930", buy_price=10000, high_since_buy=10500)
    _seed_candidate(kojiro, "005930", atr=200.0)
    assert kojiro.check_exit_signal("005930", 10400, 0) == Signal.NONE


# ── 멀티데이/청산 훅 ──

def test_check_force_clear_empty(kojiro):
    assert kojiro.check_force_clear() == []


def test_on_position_closed_pops_state(kojiro):
    _seed_candidate(kojiro, "005930")
    kojiro._held_stage3["005930"] = True
    kojiro._stop_floor["005930"] = 9600
    kojiro.on_position_closed("005930")
    assert "005930" not in kojiro._held_stage3
    assert "005930" not in kojiro._stop_floor


def test_calc_buy_quantity_position_ratio(kojiro):
    kojiro.state.total_investment = 10_000_000
    # 0.20 * 10M = 2M / 10000 = 200주
    assert kojiro.calc_buy_quantity(10000) == 200


# ── AST 안전 가드: check_exit 에 일봉fetch/enrich/pandas/funnel hook 0건 ──

def test_check_exit_no_daily_fetch_or_enrich_or_funnel():
    import inspect
    import textwrap
    src = textwrap.dedent(inspect.getsource(KojiroStrategy.check_exit_signal))
    tree = ast.parse(src)
    forbidden = {"get_recent_daily_normalized", "fetch_daily_candles", "enrich",
                 "_record_funnel_step", "_record_funnel_pipeline_step"}
    called = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            called.add(node.id)
        if isinstance(node, ast.Attribute):
            called.add(node.attr)
    assert not (forbidden & called), f"check_exit 금지 호출: {forbidden & called}"


def test_check_buy_no_funnel_hook():
    import inspect
    src = inspect.getsource(KojiroStrategy.check_buy_signal)
    assert "_record_funnel_step" not in src
    assert "_record_funnel_pipeline_step" not in src
