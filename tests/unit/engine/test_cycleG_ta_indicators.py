"""사이클 G Part B — ta_indicators 순수함수 (rsi / relative_strength) 회귀 가드 (Red).

명세: `_workspace/red/_behaviors_cycleG_vb_rr_20260802.md` Part B (G-B1/B2).
계획: `~/.claude/plans/luminous-drifting-widget.md` Part B.

신규 모듈 `src/engine/ta_indicators.py` — DB/HTTP/시계 미접촉 순수함수
(quant_score / kojiro_indicators 선례, 8영역 미접촉).

**⚠️ kojiro_indicators.py atr/ema 재사용 금지** — ATR 이원화(kojiro 정체성).
본 모듈은 RSI/RS 전용 순수함수를 독립 정의한다.

순수함수이므로 실호출 (mock 금지) — 결정적 시리즈로 검증.

Red 가드 매트릭스:
- G-B1 (RSI): `rsi(closes, period=14) -> float|None`. Wilder 평균. 연속 상승 → RSI 高
  (all-gains → 100), 연속 하락 → 低 (all-losses → 0), 데이터 부족 → None. 결정적.
- G-B2 (RS): `relative_strength(stock_closes, index_closes, period=20) -> float|None`.
  종목 수익률 > 지수 수익률 → 양수, 반대 → 음수, 부족 → None. 결정적.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit


def _lin(start: float, end: float, n: int) -> list[float]:
    """start→end 균일 선형 시리즈 (n개, 시간 오름차순 ASC)."""
    if n == 1:
        return [start]
    step = (end - start) / (n - 1)
    return [round(start + step * i, 4) for i in range(n)]


# ---------------------------------------------------------------------------
# G-B1 — RSI 순수함수 (Wilder)
# ---------------------------------------------------------------------------
class TestRsi:
    def test_module_and_signature(self):
        from src.engine.ta_indicators import rsi  # noqa: F401 — 모듈/심볼 존재 검증

    def test_rising_series_high(self):
        from src.engine.ta_indicators import rsi

        # 15개 연속 상승 (14 delta 모두 +) → avg_loss=0 → RSI=100 근접
        closes = list(range(10, 25))  # 10..24
        r = rsi(closes, period=14)
        assert r is not None, "연속 상승 시리즈인데 RSI None 반환."
        assert r > 90, f"연속 상승인데 RSI 낮음: {r} (100 근접 기대)."

    def test_all_gains_equals_100(self):
        from src.engine.ta_indicators import rsi

        closes = list(range(10, 30))  # 20 연속 상승
        r = rsi(closes, period=14)
        assert r == pytest.approx(100.0), (
            f"all-gains (avg_loss=0) 인데 RSI != 100: {r}."
        )

    def test_falling_series_low(self):
        from src.engine.ta_indicators import rsi

        closes = list(range(24, 9, -1))  # 24..10 연속 하락
        r = rsi(closes, period=14)
        assert r is not None, "연속 하락 시리즈인데 RSI None 반환."
        assert r < 10, f"연속 하락인데 RSI 높음: {r} (0 근접 기대)."

    def test_all_losses_equals_0(self):
        from src.engine.ta_indicators import rsi

        closes = list(range(30, 10, -1))  # 20 연속 하락
        r = rsi(closes, period=14)
        assert r == pytest.approx(0.0), (
            f"all-losses (avg_gain=0) 인데 RSI != 0: {r}."
        )

    def test_insufficient_data_none(self):
        from src.engine.ta_indicators import rsi

        # period=14 인데 delta 3개 뿐 → 계산 불가
        assert rsi([10, 11, 12], period=14) is None, (
            "데이터 부족(3개)인데 RSI None 아님 — 부족 시 None 규약 위반."
        )

    def test_strong_uptrend_higher_than_weak(self):
        """더 강한 상승 시리즈가 더 높은 RSI (monotonic 관계)."""
        from src.engine.ta_indicators import rsi

        strong = list(range(10, 25))  # 순상승
        # 톱니 (상승弱, 하락 섞임): +2/-1 반복
        weak = [10.0]
        for i in range(14):
            weak.append(weak[-1] + (2.0 if i % 2 == 0 else -1.0))
        r_strong = rsi(strong, period=14)
        r_weak = rsi(weak, period=14)
        assert r_strong is not None and r_weak is not None
        assert r_strong > r_weak, (
            f"강한 상승 RSI({r_strong}) 가 약한 상승 RSI({r_weak}) 이하 — monotonic 위반."
        )

    def test_deterministic(self):
        from src.engine.ta_indicators import rsi

        closes = [44.3, 44.1, 44.2, 43.6, 44.3, 44.8, 45.1, 45.4,
                  45.8, 46.1, 45.9, 46.0, 45.6, 46.3, 46.3, 46.0]
        first = rsi(closes, period=14)
        second = rsi(closes, period=14)
        assert first == second, f"동일 입력 RSI 비결정적: {first} != {second}."


# ---------------------------------------------------------------------------
# G-B2 — 상대강도 RS 순수함수
# ---------------------------------------------------------------------------
class TestRelativeStrength:
    def test_module_and_signature(self):
        from src.engine.ta_indicators import relative_strength  # noqa: F401

    def test_outperform_positive(self):
        from src.engine.ta_indicators import relative_strength

        # 종목 +20%, 지수 +5% — 전 구간 균일 상승 (어떤 window 든 종목 우위)
        stock = _lin(100.0, 120.0, 25)
        index = _lin(100.0, 105.0, 25)
        rs = relative_strength(stock, index, period=20)
        assert rs is not None, "충분한 데이터인데 RS None 반환."
        assert rs > 0, f"종목(+20%) > 지수(+5%) 인데 RS 양수 아님: {rs}."

    def test_underperform_negative(self):
        from src.engine.ta_indicators import relative_strength

        # 종목 -10%, 지수 +5%
        stock = _lin(100.0, 90.0, 25)
        index = _lin(100.0, 105.0, 25)
        rs = relative_strength(stock, index, period=20)
        assert rs is not None
        assert rs < 0, f"종목(-10%) < 지수(+5%) 인데 RS 음수 아님: {rs}."

    def test_insufficient_stock_none(self):
        from src.engine.ta_indicators import relative_strength

        # period=20 인데 2개 뿐 → None
        assert relative_strength([100.0, 101.0], _lin(100.0, 105.0, 25), period=20) is None, (
            "종목 데이터 부족(2개)인데 RS None 아님."
        )

    def test_insufficient_index_none(self):
        from src.engine.ta_indicators import relative_strength

        assert relative_strength(_lin(100.0, 120.0, 25), [100.0, 101.0], period=20) is None, (
            "지수 데이터 부족(2개)인데 RS None 아님."
        )

    def test_deterministic(self):
        from src.engine.ta_indicators import relative_strength

        stock = _lin(100.0, 118.0, 25)
        index = _lin(100.0, 108.0, 25)
        first = relative_strength(stock, index, period=20)
        second = relative_strength(stock, index, period=20)
        assert first == second, f"동일 입력 RS 비결정적: {first} != {second}."
