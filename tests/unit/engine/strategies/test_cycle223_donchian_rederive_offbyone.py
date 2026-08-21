"""사이클 223 Red (S2) — `_rederive_breakout_high` off-by-one 시정.

> 자문: `_workspace/domain_consult/donchian_exit_retune.md` §2-6 / §4 C0

## 결함

매수 경로와 재시작 복구 경로가 **서로 다른 돌파선**을 만든다.

    :320  매수   prior_high = max(highs[1: donchian_period + 1])   ← 신호일(전일) 봉 제외
    :657  재도출 highs = [... for c in prior[:donchian_period]]      ← 신호일 봉 포함

`prior = [c for c in candles if str(c["stck_bsop_date"]) < buy_dd]` 이고 candles 는
DESC 이므로 `prior[0]` = 매수일 직전 봉 = **신호일 봉**이다. 신호일은 정의상 20일
신고가를 돌파한 날이므로 이 봉을 포함하면 재도출선이 라이브선보다 **항상 높거나 같다**
(실측 19/19, 중앙값 +5.3%). 그 결과 시간청산이 "돌파 실패"가 아니라 "돌파일 장중 고가
미탈환"을 판정하며 과대발화한다 — 판정 반전 8/19, 그 8건이 승자 5건을 전부 포함.

실측:
  095340 라이브 163,500 → 재도출 172,300(08-18 고가). `169,600 < 172,300` 성립해 조기청산.
  078930 라이브 106,400 → 재도출 113,000(08-13 고가). `112,900 < 113,000` 성립해 조기청산.

## 요구 행위 (구현 계약)

- `prior[:donchian_period]` → **`prior[1: donchian_period + 1]`** (매수 경로와 동일 산식)
- 길이 가드 `len(prior) < donchian_period` → **`donchian_period + 1`**
  (안 하면 IndexError 가 아니라 **조용한 과소 표본** — 19봉으로 20일 신고가를 만든다)
- 매수 경로 `:320` 은 **불변**(정답 쪽) · 매수일 이후 봉 제외 계약도 불변

## Red 유효성 (production 미변경)

- S2-1/S2-2/S2-5 (신호일 제외 값) = FAIL (현재 신호일 봉이 최고가로 잡힘)
- S2-3 (prior==period → 미복구) = FAIL (현재 20봉이면 복구해 버림)
- S2-4 (prior==period+1 → 복구) = PASS (경계 상한 회귀 가드)
- S2-6 (매수 후 봉 제외) = PASS (기존 계약 보존 확인)
"""
from __future__ import annotations

import datetime as _dt

import pytest

from src.engine.strategies.donchian_swing import DonchianSwingStrategy
from src.engine.strategy_base import Position, StrategyConfig

pytestmark = pytest.mark.unit

_PERIOD = 20


def _mk() -> DonchianSwingStrategy:
    return DonchianSwingStrategy(
        StrategyConfig(strategy_id="donchian_swing", name="도치안", weight=0.2)
    )


def _pos(ticker: str, buy_date: _dt.date, buy_price: int = 100_000) -> Position:
    p = Position(ticker=ticker, buy_price=buy_price, quantity=1, order_no="O",
                 strategy_id="donchian_swing", buy_date=buy_date)
    p.high_since_buy = buy_price
    return p


def _bdays_desc(end: _dt.date, n: int) -> list[_dt.date]:
    """`end`(포함)부터 과거로 주말 제외 n 영업일 — 내림차순(idx0=최신)."""
    out: list[_dt.date] = []
    d = end
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d -= _dt.timedelta(days=1)
    return out


def _candle(d: _dt.date, high: int) -> dict:
    return {
        "stck_bsop_date": d.strftime("%Y%m%d"),
        "stck_hgpr": str(high),
        "stck_lwpr": str(int(high * 0.95)),
        "stck_clpr": str(int(high * 0.98)),
        "acml_vol": "1000000",
    }


def _live_prior_high(candles_from_signal_day: list[dict], period: int = _PERIOD) -> int:
    """매수 경로(`prepare` :320) 산식을 그대로 재현 — 비교 기준(정답)."""
    highs = [int(c["stck_hgpr"]) for c in candles_from_signal_day]
    return max(highs[1: period + 1])


def _build_095340() -> tuple[list[dict], list[dict]]:
    """095340 실측 근사 — 신호일(08-18) 고가 172,300 / 진짜 돌파선 163,500.

    Returns: (전체 candles DESC, 신호일부터의 candles DESC = 라이브 prepare 시야)
    """
    signal_day = _dt.date(2026, 8, 18)
    prior_days = _bdays_desc(signal_day, 25)   # idx0 = 신호일
    prior: list[dict] = []
    for i, d in enumerate(prior_days):
        if i == 0:
            high = 172_300          # 신호일 봉 — 재도출이 잘못 집어오는 값
        elif i == 5:
            high = 163_500          # 진짜 직전 20일 신고가
        elif i == 21:
            high = 999_999          # 창(1..20) 밖 decoy — 상한 경계 검증
        else:
            high = 150_000
        prior.append(_candle(d, high))
    # 매수일(08-19) 이후 봉 — 재도출에서 반드시 제외되어야 함
    post = [_candle(_dt.date(2026, 8, 20), 200_000), _candle(_dt.date(2026, 8, 19), 200_000)]
    return post + prior, prior


# ===========================================================================
# S2-1 (핵심) — 신호일 봉 제외 → 라이브 돌파선과 동일 값
# ===========================================================================
def test_s2_1_rederive_excludes_signal_day_bar_095340():
    """095340: 재도출선이 172,300(신호일 고가) 이 아니라 163,500 이어야 한다."""
    s = _mk()
    candles, _ = _build_095340()
    pos = _pos("095340", _dt.date(2026, 8, 19), buy_price=162_500)

    s._rederive_breakout_high("095340", pos, candles, _PERIOD)

    assert s._breakout_high.get("095340") == 163_500, (
        "S2-1: 신호일(08-18) 봉을 포함하면 172,300 = 유령 돌파선. "
        f"기대 163,500, got {s._breakout_high.get('095340')}"
    )


def test_s2_2_rederive_matches_live_prior_high_formula():
    """재도출선 ≡ 매수 경로 `max(highs[1: period+1])` (동일 산식 불변식)."""
    s = _mk()
    candles, from_signal = _build_095340()
    pos = _pos("095340", _dt.date(2026, 8, 19), buy_price=162_500)

    s._rederive_breakout_high("095340", pos, candles, _PERIOD)

    live = _live_prior_high(from_signal, _PERIOD)
    assert live == 163_500, "테스트 픽스처 결함 — 라이브 산식 기준값 불일치"
    assert s._breakout_high.get("095340") == live, (
        f"S2-2: 재도출선({s._breakout_high.get('095340')}) 은 라이브선({live}) 과 "
        "동일해야 한다 (매수/복구 경로 정합성)"
    )


def test_s2_5_rederive_excludes_signal_day_bar_078930():
    """078930: 재도출선이 113,000(신호일 08-13 고가) 이 아니라 106,400."""
    s = _mk()
    signal_day = _dt.date(2026, 8, 13)
    days = _bdays_desc(signal_day, 24)
    prior = []
    for i, d in enumerate(days):
        high = 113_000 if i == 0 else (106_400 if i == 12 else 100_000)
        prior.append(_candle(d, high))
    candles = [_candle(_dt.date(2026, 8, 14), 130_000)] + prior
    pos = _pos("078930", _dt.date(2026, 8, 14), buy_price=110_300)

    s._rederive_breakout_high("078930", pos, candles, _PERIOD)

    assert s._breakout_high.get("078930") == 106_400, (
        f"S2-5: 기대 106,400, got {s._breakout_high.get('078930')}"
    )


# ===========================================================================
# S2-3 / S2-4 — 길이 가드 경계 (조용한 과소 표본 차단)
# ===========================================================================
def test_s2_3_no_rederive_when_prior_equals_period():
    """prior 가 정확히 period(20)개면 재도출하지 않는다 (신호일 제외 시 19봉 = 과소 표본).

    Red: 현행 가드 `len(prior) < donchian_period` 는 20봉을 통과시켜
    **신호일 포함 20봉** 으로 복구해 버린다.
    """
    s = _mk()
    signal_day = _dt.date(2026, 8, 18)
    prior = [_candle(d, 172_300 if i == 0 else 150_000)
             for i, d in enumerate(_bdays_desc(signal_day, _PERIOD))]
    assert len(prior) == _PERIOD
    pos = _pos("095340", _dt.date(2026, 8, 19))

    s._rederive_breakout_high("095340", pos, prior, _PERIOD)

    assert "095340" not in s._breakout_high, (
        "S2-3: prior 20봉(=period) 은 신호일 제외 시 19봉뿐 → 미복구가 계약. "
        f"got {s._breakout_high.get('095340')}"
    )


def test_s2_4_rederive_when_prior_equals_period_plus_one():
    """prior 가 period+1(21)개면 재도출한다 (경계 하한 — 과잉 차단 회귀 방지)."""
    s = _mk()
    signal_day = _dt.date(2026, 8, 18)
    prior = []
    for i, d in enumerate(_bdays_desc(signal_day, _PERIOD + 1)):
        high = 172_300 if i == 0 else (163_500 if i == _PERIOD else 150_000)
        prior.append(_candle(d, high))
    assert len(prior) == _PERIOD + 1
    pos = _pos("095340", _dt.date(2026, 8, 19))

    s._rederive_breakout_high("095340", pos, prior, _PERIOD)

    assert s._breakout_high.get("095340") == 163_500, (
        "S2-4: prior 21봉이면 [1:21] 창이 정확히 20봉 → 복구 의무. "
        f"got {s._breakout_high.get('095340')}"
    )


# ===========================================================================
# S2-6 (회귀 보존) — 매수일 이후 봉 제외 계약 불변
# ===========================================================================
def test_s2_6_post_buy_bars_still_excluded():
    """매수일 당일/이후 봉(고가 200,000)은 재도출에 절대 유입되지 않는다."""
    s = _mk()
    candles, _ = _build_095340()
    pos = _pos("095340", _dt.date(2026, 8, 19), buy_price=162_500)

    s._rederive_breakout_high("095340", pos, candles, _PERIOD)

    got = s._breakout_high.get("095340", 0)
    assert got not in (200_000, 999_999), (
        f"S2-6: 매수 후 봉/창 밖 decoy 유입 금지 — got {got}"
    )
    assert got > 0


def test_s2_7_graceful_on_malformed_candles():
    """봉 파싱 실패는 예외 전파 없이 미복구 (fail-safe 계약 보존)."""
    s = _mk()
    bad = [{"stck_bsop_date": "20260818", "stck_hgpr": None} for _ in range(_PERIOD + 5)]
    pos = _pos("095340", _dt.date(2026, 8, 19))
    s._rederive_breakout_high("095340", pos, bad, _PERIOD)   # 예외 없이 반환
    assert s._breakout_high.get("095340", 0) == 0
