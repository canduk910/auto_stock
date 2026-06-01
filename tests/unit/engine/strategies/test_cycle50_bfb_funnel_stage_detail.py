"""사이클 50 (2026-06-01) — BFB `_detect_pole_and_flag` 단계별 사유 정밀화 회귀.

[배경 — 확정 진단]
2026-06-01 대시보드 BFB 조건검색 퍼널 4단계 "폴 검출"에서 22~25종목 → 0 전멸.
운영 funnel DB(`strategy_funnel_snapshots`) 05/29(24→0)·06/01(25→0) 2영업일 연속.

근본 원인 3 (진단 인프라 결함): `_detect_pole_and_flag` 가 4개 sub-condition
(폴 상승률/음봉비율/플래그 조정폭/거래량수축)을 한 함수에서 평가하고 실패 시 `None` 만
반환 → funnel step 5(플래그)/6(거래량수축)/7(ATR) 가 survived=0 AND excluded=0 →
어느 조건이 바인딩인지 계측 자체가 불가능.

[시정 — 단계별 실패 사유 반환]
사이클 49 VCP `last_pullback_pct 항상 기록` 동일 계열. 행위 보존(검출 결과 무변경 —
통과/탈락 종목 동일), 계측만 추가.

- 신규 `_detect_pole_and_flag_detailed(candles) -> (result, fail_stage, detail)`:
  * result: 기존 dict | None (통과 시 dict, 실패 시 None) — **행위 완전 보존**
  * fail_stage: 통과 시 "" / 실패 시 가장 멀리 도달한 sub-condition 이름
    ("pole_return" / "pole_red_ratio" / "flag_retracement" / "volume_contraction")
  * detail: 가장 멀리 도달한 조합의 측정 수치 dict (best_return / red_ratio /
    retracement / vol_ratio 등)
- `_detect_pole_and_flag(candles) -> dict | None`: 기존 시그니처/계약 그대로 유지
  (detailed 의 result 만 반환하는 thin wrapper) — 모든 기존 호출처/테스트 무영향

본 테스트는 Red 단계로 작성 — 시정 전 모두 FAIL (메서드/키 부재).
"""

from __future__ import annotations

import pytest

from src.engine.strategies.bull_flag_breakout import BullFlagBreakoutStrategy
from src.engine.strategy_base import StrategyConfig

pytestmark = pytest.mark.unit


@pytest.fixture
def strat():
    return BullFlagBreakoutStrategy(
        StrategyConfig(strategy_id="bull_flag_breakout", name="눌림목 돌파", weight=0.0)
    )


def _candle(close: int, high: int, low: int, open_: int, vol: int) -> dict:
    return {
        "stck_clpr": str(close),
        "stck_hgpr": str(high),
        "stck_lwpr": str(low),
        "stck_oprc": str(open_),
        "acml_vol": str(vol),
    }


def _flat_candle(price: int, vol: int) -> dict:
    return _candle(price, price, price, price, vol)


# ---------------------------------------------------------------------------
# 폴/플래그 합성 빌더 (최신순 index 0).
# 구조: [flag 구간(최신)] + [pole 구간] + [패딩(오래된)].
#   pole 구간: 저가 base → 고가 peak 까지 상승 (음봉 ratio 제어).
#   flag 구간: peak 근처에서 소폭 조정 + 거래량 제어 (수축 여부 제어).
# ---------------------------------------------------------------------------
def _build_candles(
    *,
    pole_len: int = 5,
    flag_len: int = 4,
    pole_start: int = 10_000,
    pole_high: int = 13_000,   # +30% 폴
    pole_red_count: int = 0,
    flag_low: int = 12_500,    # 얕은 조정
    pole_vol: int = 1_000_000,
    flag_vol: int = 500_000,
    pad: int = 20,
) -> list[dict]:
    """최신순 일봉 리스트 생성. flag(index 0..flag_len-1) → pole → padding."""
    candles: list[dict] = []

    # flag 구간 (최신) — flag_high≈pole_high 근처, 전 봉이 flag_low 까지 조정.
    # 조정 폭(retracement) = (pole_high - min(flag_lows))/pole_width 는 flag_low 로 확정.
    for _ in range(flag_len):
        candles.append(_candle(
            close=pole_high - 200, high=pole_high, low=flag_low,
            open_=pole_high - 100, vol=flag_vol,
        ))

    # pole 구간 — 가장 옛날 종가 = pole_start, 고점 = pole_high
    # 음봉 개수 = pole_red_count (open>close)
    for j in range(pole_len):
        # pole 구간은 index flag_len..flag_len+pole_len-1
        # 마지막(가장 옛날) 봉의 종가 = pole_start
        is_oldest = (j == pole_len - 1)
        close = pole_start if is_oldest else (pole_start + (pole_high - pole_start) * (pole_len - 1 - j) // pole_len)
        is_red = j < pole_red_count
        if is_red:
            open_ = close + 100  # open>close → 음봉
        else:
            open_ = max(1, close - 100)  # 양봉
        candles.append(_candle(
            close=close, high=pole_high if j == 0 else close + 50,
            low=max(1, close - 50), open_=open_, vol=pole_vol,
        ))

    # 패딩 (오래된 봉)
    for _ in range(pad):
        candles.append(_flat_candle(pole_start, pole_vol))

    return candles


# ---------------------------------------------------------------------------
# RED 1 — detailed 메서드 존재 + 3-tuple 반환 계약
# ---------------------------------------------------------------------------
def test_detailed_method_exists_and_returns_triple(strat):
    candles = _build_candles()
    assert hasattr(strat, "_detect_pole_and_flag_detailed"), (
        "시정 — `_detect_pole_and_flag_detailed` 신규 메서드가 있어야 함"
    )
    out = strat._detect_pole_and_flag_detailed(candles)
    assert isinstance(out, tuple) and len(out) == 3, (
        "(result, fail_stage, detail) 3-tuple 반환이어야 함"
    )
    result, fail_stage, detail = out
    assert isinstance(fail_stage, str)
    assert isinstance(detail, dict)


# ---------------------------------------------------------------------------
# RED 2 — 행위 보존: wrapper 의 dict|None 계약 유지
# ---------------------------------------------------------------------------
def test_wrapper_preserves_dict_or_none_contract(strat):
    """`_detect_pole_and_flag` 는 detailed 의 result 만 반환 (기존 계약)."""
    # 통과 케이스: 모든 조건 만족 (폴 +30%, 음봉 0, 얕은 조정, 거래량 수축 50%)
    ok = _build_candles(pole_vol=1_000_000, flag_vol=400_000)
    res = strat._detect_pole_and_flag(ok)
    det_res, _, _ = strat._detect_pole_and_flag_detailed(ok)
    assert res == det_res, "wrapper 와 detailed 의 result 가 동일해야 함 (행위 보존)"


# ---------------------------------------------------------------------------
# RED 3 — 거래량 수축 바인딩: 폴/음봉/조정 모두 통과인데 거래량만 미수축
# ---------------------------------------------------------------------------
def test_volume_contraction_is_binding_stage(strat):
    """폴 상승률·음봉·플래그 조정폭 모두 통과하지만 거래량이 수축 안 됨(flag_vol≈pole_vol)
    → fail_stage == "volume_contraction" + result is None.

    이것이 06/01 운영 가설 (거래량순위 종목 = 거래량 폭발 ⊥ 수축) 의 단위 재현.
    """
    candles = _build_candles(
        pole_start=10_000, pole_high=13_000,  # +30% 폴 (임계 15% 통과)
        pole_red_count=0,                       # 음봉 0% (임계 45% 통과)
        flag_low=12_500,                        # 얕은 조정 (38.2% 통과)
        pole_vol=1_000_000,
        flag_vol=1_000_000,                     # 거래량 수축 X (flag==pole)
    )
    result, fail_stage, detail = strat._detect_pole_and_flag_detailed(candles)
    assert result is None, "거래량 미수축 → 검출 실패 (행위 보존)"
    assert fail_stage == "volume_contraction", (
        f"거래량 수축이 바인딩이어야 함. 실제 fail_stage={fail_stage} detail={detail}"
    )
    # 측정 수치 노출 — vol_ratio = flag_avg / pole_avg ≈ 1.0
    assert "vol_ratio" in detail and detail["vol_ratio"] >= 0.6, (
        f"거래량 비율 측정값 노출 필요. detail={detail}"
    )


# ---------------------------------------------------------------------------
# RED 4 — 폴 상승률 바인딩: 상승률이 임계 미달
# ---------------------------------------------------------------------------
def test_pole_return_is_binding_stage(strat):
    """폴 상승률이 임계(15%) 미달 → fail_stage == "pole_return"."""
    candles = _build_candles(
        pole_start=10_000, pole_high=10_500,   # +5% 폴 (임계 15% 미달)
        pole_red_count=0, flag_low=10_400,
        pole_vol=1_000_000, flag_vol=300_000,
    )
    result, fail_stage, detail = strat._detect_pole_and_flag_detailed(candles)
    assert result is None
    assert fail_stage == "pole_return", (
        f"폴 상승률이 바인딩이어야 함. 실제={fail_stage} detail={detail}"
    )
    assert "best_return" in detail, f"best_return 측정값 노출 필요. detail={detail}"


# ---------------------------------------------------------------------------
# RED 5 — 통과 케이스: fail_stage == "" (빈 문자열)
# ---------------------------------------------------------------------------
def test_pass_case_empty_fail_stage(strat):
    candles = _build_candles(pole_vol=1_000_000, flag_vol=300_000)
    result, fail_stage, detail = strat._detect_pole_and_flag_detailed(candles)
    assert result is not None, "모든 조건 만족 → dict 반환"
    assert fail_stage == "", f"통과 시 fail_stage 는 빈 문자열. 실제={fail_stage}"


# ---------------------------------------------------------------------------
# RED 6 — prepare funnel hook: 거래량 수축 단계(step 6) excluded 에 사유 기록
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_prepare_records_volume_contraction_excluded(strat, monkeypatch):
    """prepare() 가 거래량 수축 탈락 종목을 step 6(거래량 수축) excluded 에 수치 사유로 기록.

    근본 원인 3 시정 핵심 — funnel step 5/6 가 survived/excluded 0 이던 결함을
    실제 바인딩 단계에 사유 분배로 교체.
    """
    # 유니버스 = 1종목 (거래량 미수축 케이스)
    async def _fake_scan_universe():
        strat._scan_stats["universe_candidates"] = 1
        strat._scan_stats["universe_filtered"] = 1
        return ["005930"]

    monkeypatch.setattr(strat, "_scan_universe", _fake_scan_universe)

    vol_fail_candles = _build_candles(
        pole_start=10_000, pole_high=13_000, pole_red_count=0,
        flag_low=12_500, pole_vol=1_000_000, flag_vol=1_000_000,  # 미수축
    )

    async def _fake_fetch(ticker, days=21):
        return vol_fail_candles

    import src.api.condition as cond_mod
    monkeypatch.setattr(cond_mod, "fetch_daily_candles", _fake_fetch)

    await strat.prepare()

    # funnel step 6 (거래량 수축) 에 005930 이 excluded 로 기록되어야 함
    steps = {s["step_no"]: s for s in strat._funnel_steps}
    assert 6 in steps, "step 6(거래량 수축) funnel 단계가 기록되어야 함"
    step6 = steps[6]
    excluded_tickers = [e.get("ticker") for e in step6.get("excluded", [])]
    assert "005930" in excluded_tickers, (
        f"거래량 미수축 종목이 step 6 excluded 에 기록되어야 함. "
        f"step6 excluded={step6.get('excluded')}"
    )
    # 사유에 측정 수치(거래량 비율) 포함
    reason = next(
        (e.get("reason", "") for e in step6["excluded"] if e.get("ticker") == "005930"),
        "",
    )
    assert "거래량" in reason or "vol" in reason.lower(), (
        f"step 6 사유에 거래량 수축 미달 명시 필요. reason={reason!r}"
    )
