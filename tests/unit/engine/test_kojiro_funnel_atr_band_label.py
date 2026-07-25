"""회귀 가드 (결함 2, LOW) — kojiro 퍼널 step5 ATR 밴드 라벨 드리프트.

DEFAULT_PARAMS 는 `atr_ratio_max: 0.06`(6.0%, 2026-07-20 백테스트로 0.045→0.06 상향).
그러나 퍼널 라벨 `FunnelStage(5, "ATR/종가 변동성 밴드 통과 (1.0~4.5%)")` 와 모듈 docstring
`ATR/종가 밴드 1.0~4.5%` 가 낡은 4.5% 를 그대로 표기 → `/strategy-funnel` step5 라벨이
"1.0~4.5%" 로 나와 운영자 오인 소지. (런타임 필터는 이미 params 파생 → 실필터는 6.0% 정상.)

Red: 현재 step5 라벨이 "4.5" 포함 / "6.0" 미포함 → FAIL.
Green: 라벨/주석의 "4.5%" → "6.0%" (즉 "1.0~6.0%") 로 atr_ratio_max=0.06 정합.
"""

from __future__ import annotations

from pathlib import Path

from src.engine.strategies.kojiro import FUNNEL_STAGES, KojiroStrategy

_KOJIRO_PATH = (
    Path(__file__).resolve().parents[3]
    / "src"
    / "engine"
    / "strategies"
    / "kojiro.py"
)


def _step5_label() -> str:
    for stage in FUNNEL_STAGES:
        if stage.step_no == 5:
            return stage.step_name
    raise AssertionError("FUNNEL_STAGES 에 step_no=5 미발견")


def test_funnel_step5_label_matches_atr_ratio_max() -> None:
    """step5 라벨의 상한 % 표기가 DEFAULT_PARAMS['atr_ratio_max'] 와 정합."""
    label = _step5_label()
    atr_max = KojiroStrategy.DEFAULT_PARAMS["atr_ratio_max"]  # 0.06
    atr_min = KojiroStrategy.DEFAULT_PARAMS["atr_ratio_min"]  # 0.01
    upper_pct = f"{atr_max * 100:.1f}"  # "6.0"
    lower_pct = f"{atr_min * 100:.1f}"  # "1.0"

    assert "4.5" not in label, (
        f"step5 라벨이 낡은 4.5% 를 표기 (atr_ratio_max={atr_max} → {upper_pct}%): {label!r}"
    )
    assert upper_pct in label, (
        f"step5 라벨에 상한 {upper_pct}% 가 없음 (atr_ratio_max={atr_max}): {label!r}"
    )
    assert lower_pct in label, (
        f"step5 라벨에 하한 {lower_pct}% 가 없음 (atr_ratio_min={atr_min}): {label!r}"
    )


def test_kojiro_source_has_no_stale_atr_band_string() -> None:
    """kojiro.py 소스에 낡은 "1.0~4.5%" 문자열이 라벨·docstring 어디에도 없어야 한다.

    (line~10 docstring 과 line~50 FunnelStage 라벨 양쪽 드리프트를 한 번에 차단.)
    """
    source = _KOJIRO_PATH.read_text(encoding="utf-8")
    assert "1.0~4.5%" not in source, (
        "kojiro.py 에 낡은 ATR 밴드 표기 '1.0~4.5%' 잔존 "
        "(atr_ratio_max=0.06 → '1.0~6.0%' 로 갱신할 것)"
    )
