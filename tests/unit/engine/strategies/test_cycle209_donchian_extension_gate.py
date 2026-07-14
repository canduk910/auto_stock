"""사이클 209 Red — donchian `max_breakout_extension_pct` 0.5→4.0 복원 + 진입 게이트 정합.

> 자문: `_workspace/domain_consult/cycle209_donchian_extension_gate.md`
> 선례: 사이클 208 (박스 수축 필터 제거) · 사이클 198 (BFB flag_lookback_min AI 과튜닝 차단)

배경: 사이클 208 로 박스 필터 제거 → 최종 후보(S-Oil)는 생겼으나, extension 가드
(운영 DB 0.5%, AI 가 default 3.0 → 하한 0.5 로 과튜닝) 가 2차 병목. donchian 후보 =
"어제 종가 > 직전20일 신고가"(이미 돌파) → 오늘 대개 기준가 위에서 열림 → ext_pct 항상 양수 →
0.5% 면 정상 1~3% 돌파까지 상시 스킵. 자문 권고 = default 4.0 + PARAM_RANGES 제외 +
불변식 extension ≥ gap.

요구 행위:
1. G-209-1: DEFAULT_PARAMS["max_breakout_extension_pct"] == 4.0
2. G-209-3 (HIGH): 정상 돌파(ext ~2~3%, ≤4.0) + gap<3% + 창(09:05~09:30) → BUY.
   실측 DB값 0.5 재현 = ext 2% 후보가 0.5 에선 스킵 / 4.0 에선 BUY 전환 대조.
4. G-209-4: 불변식 extension(4.0) ≥ gap_skip_threshold(3.0)
5. G-209-5: S-Oil 유형(ext 6.45%) 은 max_ext=4.0 에서도 여전히 스킵 (뒷북 추격 차단 보존)

Red 유효성 (production 미변경 = DEFAULT_PARAMS default 3.0 stash 상태):
  - G-209-1 (4.0 단언) = FAIL (현재 3.0)
  - G-209-3 ext 3.5% BUY 케이스 = FAIL (default 3.0 stash 시 3.5 > 3.0 스킵)
  - G-209-4 불변식 (4.0 ≥ 3.0) = FAIL (현재 3.0, 3.0 ≥ 3.0 은 참이나 default 값 자체 단언 동반)
  - G-209-3 0.5 재현 대조 (params 명시 주입) = PASS (default 무관, params 직접 주입)
  - G-209-5 6.45% 스킵 = PASS (4.0/3.0 무관 항상 스킵, 불변식 보존)
"""
from __future__ import annotations

import pytest
from freezegun import freeze_time

from src.engine.strategies.donchian_swing import DonchianSwingStrategy
from src.engine.strategy_base import Signal, StrategyConfig

pytestmark = pytest.mark.unit


def _make_strat(max_ext: float | None = None):
    """전략 생성. max_ext=None 이면 DEFAULT_PARAMS 값 그대로 사용 (default 검증용)."""
    strat = DonchianSwingStrategy(
        StrategyConfig(strategy_id="donchian_swing", name="도치안", weight=0.0)
    )
    if max_ext is not None:
        strat.config.params["max_breakout_extension_pct"] = max_ext
    return strat


def _seed_candidate(strat, ticker, donchian_high=10_000, prev_close=9_800):
    strat._candidates[ticker] = {
        "prev_close": prev_close,
        "atr": 200,
        "ema60": 9_500,
        "donchian_high": donchian_high,
    }


# ===========================================================================
# G-209-1 — DEFAULT_PARAMS default 4.0
# ===========================================================================
def test_g209_1_default_params_extension_is_4():
    """DEFAULT_PARAMS["max_breakout_extension_pct"] == 4.0 (0.5→4.0 복원, default 3.0→4.0 상향).

    Red: 현재 코드 default 3.0 → FAIL.
    """
    assert DonchianSwingStrategy.DEFAULT_PARAMS["max_breakout_extension_pct"] == 4.0


# ===========================================================================
# G-209-4 — 불변식 extension ≥ gap_skip_threshold (두 게이트 모순 방지 명문화)
# ===========================================================================
def test_g209_4_invariant_extension_ge_gap():
    """max_breakout_extension_pct(4.0) >= gap_skip_threshold(3.0).

    갭 가드가 "3% 까지 허용" 해놓고 extension 이 그보다 낮으면 즉시 차단 = 논리 모순.
    extension ≥ gap 이어야 갭으로 열린 만큼 extension 이 수용. (자문 (b))

    Red: 현재 default extension 3.0 == gap 3.0 은 부등식 자체는 참이나,
    4.0 복원 후에만 "여유" 확보. 본 케이스는 default 값 4.0 을 전제로 하므로
    3.0 stash 상태선 3.0 >= 3.0 (참) 이지만 값이 4.0 이 아님을 G-209-1 이 잡음.
    여기선 두 파라미터의 정합 관계만 단언.
    """
    dp = DonchianSwingStrategy.DEFAULT_PARAMS
    ext = float(dp["max_breakout_extension_pct"])
    gap = float(dp["gap_skip_threshold"])
    assert ext >= gap, (
        f"불변식 위반: max_breakout_extension_pct({ext}) < gap_skip_threshold({gap}) "
        f"— 갭 통과 종목이 extension 서 모순 차단됨"
    )
    # 4.0 복원 = gap 대비 최소 +1%p 여유 (자문 권고 핵심)
    assert ext >= gap + 1.0, (
        f"extension({ext}) 은 gap({gap}) 대비 최소 +1%p 여유 필요 (갭+장중 소폭 수용)"
    )


# ===========================================================================
# G-209-3 (HIGH) — 정상 돌파 통과 (핵심 행위)
# ===========================================================================
@freeze_time("2026-05-20 09:10:00")  # 09:10 (naive, 컨테이너 TZ) → 09:05~09:30 창 내
def test_g209_3_normal_breakout_ext_3_5_pct_buys_with_default(monkeypatch):
    """ext 3.5% (≤4.0) + gap<3% + 창 내 → BUY (default 4.0 전제).

    donchian_high=10_000, daily_high=10_350 → ext=(10350-10000)/10000*100=3.5% ≤ 4.0.
    Red: default 3.0 stash 시 3.5 > 3.0 → 스킵 → NONE = FAIL.
    Green: default 4.0 → 3.5 ≤ 4.0 → BUY.
    """
    strat = _make_strat()  # DEFAULT_PARAMS 그대로 (default 4.0 검증)
    ticker = "010950"
    _seed_candidate(strat, ticker, donchian_high=10_000, prev_close=9_950)

    # daily_high = 10_350 → ext 3.5%
    monkeypatch.setattr(
        "src.engine.scanner.ticker_prices",
        {ticker: {"stck_hgpr": "10350", "high_price": "0"}},
    )
    # gap: open 10_050 vs prev_close 9_950 → (10050-9950)/9950*100 ≈ 1.0% < 3.0% 통과
    sig = strat.check_buy_signal(ticker, 10_200, 10_050)
    assert sig == Signal.BUY, (
        "ext 3.5% ≤ 4.0 + gap 1% + 창 내 → BUY 여야 함 (default 4.0 복원)"
    )


@freeze_time("2026-05-20 09:10:00")
def test_g209_3_db_value_0_5_reproduction_then_4_0_unblocks(monkeypatch):
    """실측 DB값 0.5 재현 대조 — ext 2% 후보가 0.5 에선 스킵 / 4.0 에선 BUY.

    같은 후보/시세로 max_breakout_extension_pct 만 0.5 → 4.0 교체 시 행위 전환.
    (params 직접 주입 → default 무관, 현재 코드에서도 재현 가능 = PASS 대조 케이스)
    """
    ticker = "010950"

    # daily_high = 10_200 → ext = (10200-10000)/10000*100 = 2.0%
    prices = {ticker: {"stck_hgpr": "10200", "high_price": "0"}}
    monkeypatch.setattr("src.engine.scanner.ticker_prices", prices)

    # (1) DB값 0.5 재현 → ext 2.0% > 0.5% → 스킵 (donchian_extension_skip)
    strat_05 = _make_strat(max_ext=0.5)
    _seed_candidate(strat_05, ticker, donchian_high=10_000, prev_close=9_950)
    sig_05 = strat_05.check_buy_signal(ticker, 10_100, 10_050)
    assert sig_05 == Signal.NONE, "0.5% 임계에선 ext 2% 후보 스킵 (실측 DB 병목 재현)"

    # (2) 4.0 주입 → ext 2.0% ≤ 4.0% → BUY 전환
    strat_40 = _make_strat(max_ext=4.0)
    _seed_candidate(strat_40, ticker, donchian_high=10_000, prev_close=9_950)
    sig_40 = strat_40.check_buy_signal(ticker, 10_100, 10_050)
    assert sig_40 == Signal.BUY, "4.0% 임계에선 동일 ext 2% 후보 BUY 전환"


# ===========================================================================
# G-209-5 — 추격 차단 보존 (S-Oil 유형 6.45% 는 4.0 에서도 스킵)
# ===========================================================================
@freeze_time("2026-05-20 09:10:00")
def test_g209_5_soil_type_6_45_pct_still_skips_at_4_0(monkeypatch):
    """S-Oil(010950) 재현 — donchian_high 134800 / daily_high 143500 = +6.45% → 4.0 에서도 스킵.

    뒷북 추격 방지 순기능 보존. 값 복원의 목표는 "S-Oil 을 사게 하는 것" 이 아니라
    "정상 돌파가 통과할 창을 여는 것".
    """
    ticker = "010950"
    strat = _make_strat(max_ext=4.0)
    _seed_candidate(strat, ticker, donchian_high=134_800, prev_close=135_500)

    # daily_high = 143_500 → ext = (143500-134800)/134800*100 ≈ 6.45% > 4.0%
    monkeypatch.setattr(
        "src.engine.scanner.ticker_prices",
        {ticker: {"stck_hgpr": "143500", "high_price": "0"}},
    )
    # gap 회피용 open 은 prev_close 근처 (gap 가드보다 extension 가드에서 잡히게)
    sig = strat.check_buy_signal(ticker, 143_000, 136_000)
    assert sig == Signal.NONE, "ext 6.45% > 4.0 → 스킵 (뒷북 추격 차단 순기능 보존)"


@freeze_time("2026-05-20 09:10:00")
def test_g209_5_soil_type_also_skips_at_default_3_0_stash(monkeypatch):
    """대조 — 6.45% 는 default 3.0 stash 상태에서도 스킵 (4.0/3.0 무관 = 불변 보존).

    이 케이스는 default 값과 무관하게 항상 PASS (extension 가드 순기능이 값 변경에
    영향받지 않음을 확인 — Red stash 시에도 PASS).
    """
    ticker = "010950"
    strat = _make_strat()  # default (3.0 stash / 4.0 green 무관)
    _seed_candidate(strat, ticker, donchian_high=134_800, prev_close=135_500)
    monkeypatch.setattr(
        "src.engine.scanner.ticker_prices",
        {ticker: {"stck_hgpr": "143500", "high_price": "0"}},
    )
    sig = strat.check_buy_signal(ticker, 143_000, 136_000)
    assert sig == Signal.NONE
