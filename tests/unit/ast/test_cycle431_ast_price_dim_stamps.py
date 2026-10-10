"""cycle431 — 가격 차원 스탬프 전수 분류 가드(액면병합·분할 대사, 사용자 결정 2026-10-10 안1).

전략 파일의 모든 `self._X: dict[str, ...] = {}`(ticker 키 dict) 속성을 전수
분류(가격·거래량·무차원/구조)한다. 분류표에 없는 새 속성이 생기면 **FAIL** 한다
— 새 전략·새 스탬프가 추가될 때 `StrategyBase.on_scale_event` 의 `_PRICE_DIM_*`
선언을 함께 갱신하라는 신호다(`src/engine/corporate_action_reconcile.py`
docstring 의 "전수 점검"이 이 파일이다).

가격 차원으로 분류된 속성은 그 전략 클래스의 `_PRICE_DIM_SIMPLE_ATTRS` /
`_PRICE_DIM_BOARD_ATTRS` / `_PRICE_DIM_NESTED_ATTRS` 에 실제로 등재돼 있는지도
함께 확인한다(선언 따로 분류 따로 드리프트 차단).
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_REPO_ROOT = Path(__file__).resolve().parents[3]
_STRAT_DIR = _REPO_ROOT / "src/engine/strategies"

_DICT_DECL = re.compile(r"self\.(_[a-zA-Z0-9_]+)\s*:\s*dict\[")

# (파일, 속성) → 분류. "price_simple"/"price_board"/"price_nested:<키,...>" 는
# `on_scale_event` 가 옮긴다 — 그 밖(거래량·무차원·구조)은 눈금 사건과 무관해
# 건드리지 않는다(바꾸면 비율·불·날짜·문자열이 오염된다).
_CLASSIFICATION: dict[tuple[str, str], str] = {
    # bull_flag_breakout.py
    ("bull_flag_breakout.py", "_candidates"): "transient_skip",
    ("bull_flag_breakout.py", "_prev_price"): "price_simple",
    ("bull_flag_breakout.py", "_partial_exit"): "skip_bool",
    ("bull_flag_breakout.py", "_cooldown_until"): "skip_date",
    ("bull_flag_breakout.py", "_breakout_first_seen"): "skip_datetime",
    ("bull_flag_breakout.py", "_entry_atr"): "price_simple",
    ("bull_flag_breakout.py", "_position_setup"): "price_nested:flag_low,flag_high,pole_high,pole_start,atr14",
    ("bull_flag_breakout.py", "_vol_latch"): "skip_structural",
    # donchian_swing.py
    ("donchian_swing.py", "_candidates"): "price_nested:prev_close,atr,ema60,donchian_high",
    ("donchian_swing.py", "_entry_atr"): "price_simple",
    ("donchian_swing.py", "_breakout_high"): "price_simple",
    ("donchian_swing.py", "_channel_low"): "price_simple",
    ("donchian_swing.py", "_scan_stage_counts"): "skip_structural",
    # etf_trend.py
    ("etf_trend.py", "_candidates"): "transient_skip",
    ("etf_trend.py", "_candidate_closes"): "transient_skip",
    ("etf_trend.py", "_breakout_line"): "price_simple",
    ("etf_trend.py", "_entry_atr"): "price_simple",
    ("etf_trend.py", "_hsb_closed"): "price_simple",
    ("etf_trend.py", "_channel_low"): "price_simple",
    ("etf_trend.py", "_bars_since_buy"): "skip_count",
    # kojiro.py
    ("kojiro.py", "_candidates"): "price_nested:prev_close,atr,ema_s,ema_m,ema_l",
    ("kojiro.py", "_held_stage3"): "skip_structural",
    ("kojiro.py", "_stop_floor"): "price_simple",
    ("kojiro.py", "_position_sectors"): "skip_structural",
    ("kojiro.py", "_position_atr"): "price_simple",
    ("kojiro.py", "_scan_stage_counts"): "skip_structural",
    # long_tail_volatility.py
    ("long_tail_volatility.py", "_targets"): "transient_skip",
    ("long_tail_volatility.py", "_open_confirmed"): "skip_bool",
    ("long_tail_volatility.py", "_prev_price"): "price_board",
    ("long_tail_volatility.py", "_cooldown_until"): "skip_date",
    # momentum.py
    ("momentum.py", "_prev_prdy_rate"): "skip_rate",
    # vcp_breakout.py
    ("vcp_breakout.py", "_candidates"): "transient_skip",
    ("vcp_breakout.py", "_prev_price"): "price_simple",
    ("vcp_breakout.py", "_cooldown_until"): "skip_date",
    ("vcp_breakout.py", "_entry_atr"): "price_simple",
    ("vcp_breakout.py", "_position_setup"): "price_nested:base_low,atr14,ema50",
    ("vcp_breakout.py", "_vol_latch"): "skip_structural",
    # volatility_breakout.py
    ("volatility_breakout.py", "_targets"): "transient_skip",
    ("volatility_breakout.py", "_open_confirmed"): "skip_bool",
    ("volatility_breakout.py", "_prev_price"): "price_board",
    ("volatility_breakout.py", "_cooldown_until"): "skip_date",
    ("volatility_breakout.py", "_failed_breakout_count"): "skip_count",
}


def _discover_ticker_dict_attrs() -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    for path in sorted(_STRAT_DIR.glob("*.py")):
        if path.name == "__init__.py":
            continue
        text = path.read_text(encoding="utf-8")
        for m in _DICT_DECL.finditer(text):
            found.append((path.name, m.group(1)))
    return found


def test_every_ticker_dict_attr_is_classified():
    """새 전략·새 스탬프가 분류표 없이 생기면 FAIL — `_CLASSIFICATION` 갱신 신호."""
    found = _discover_ticker_dict_attrs()
    assert found, "전략 파일에서 ticker 키 dict 속성을 하나도 못 찾았다 — 탐지기 회귀 의심"
    unclassified = sorted(set(found) - set(_CLASSIFICATION.keys()))
    assert not unclassified, (
        f"분류표에 없는 ticker 키 dict 속성: {unclassified}\n"
        "`tests/unit/ast/test_cycle431_ast_price_dim_stamps.py::_CLASSIFICATION` 에 "
        "분류를 추가하라 — 가격 차원이면 'price_simple'/'price_board'/'price_nested:…' 로 "
        "분류하고 `StrategyBase.on_scale_event` 가 옮기도록 그 전략의 "
        "`_PRICE_DIM_*` 선언도 함께 갱신한다."
    )


def _strategy_class_for(filename: str):
    import importlib

    module_map = {
        "bull_flag_breakout.py": ("bull_flag_breakout", "BullFlagBreakoutStrategy"),
        "donchian_swing.py": ("donchian_swing", "DonchianSwingStrategy"),
        "etf_trend.py": ("etf_trend", "EtfTrendStrategy"),
        "kojiro.py": ("kojiro", "KojiroStrategy"),
        "long_tail_volatility.py": ("long_tail_volatility", "LongTailVolatilityStrategy"),
        "momentum.py": ("momentum", "MomentumStrategy"),
        "vcp_breakout.py": ("vcp_breakout", "VcpBreakoutStrategy"),
        "volatility_breakout.py": ("volatility_breakout", "VolatilityBreakoutStrategy"),
    }
    mod_name, cls_name = module_map[filename]
    mod = importlib.import_module(f"src.engine.strategies.{mod_name}")
    return getattr(mod, cls_name)


@pytest.mark.parametrize(
    "filename,attr", sorted(k for k, v in _CLASSIFICATION.items() if v == "price_simple")
)
def test_price_simple_attr_declared_on_class(filename, attr):
    cls = _strategy_class_for(filename)
    assert attr in cls._PRICE_DIM_SIMPLE_ATTRS, (
        f"{filename}:{attr} 는 가격 차원인데 {cls.__name__}._PRICE_DIM_SIMPLE_ATTRS 에 없다"
    )


@pytest.mark.parametrize(
    "filename,attr", sorted(k for k, v in _CLASSIFICATION.items() if v == "price_board")
)
def test_price_board_attr_declared_on_class(filename, attr):
    cls = _strategy_class_for(filename)
    assert attr in cls._PRICE_DIM_BOARD_ATTRS, (
        f"{filename}:{attr} 는 보드별 가격 차원인데 {cls.__name__}._PRICE_DIM_BOARD_ATTRS 에 없다"
    )


@pytest.mark.parametrize(
    "filename,attr,keys",
    sorted(
        (k[0], k[1], v.split(":", 1)[1])
        for k, v in _CLASSIFICATION.items()
        if v.startswith("price_nested:")
    ),
)
def test_price_nested_attr_declared_on_class(filename, attr, keys):
    cls = _strategy_class_for(filename)
    assert attr in cls._PRICE_DIM_NESTED_ATTRS, (
        f"{filename}:{attr} 는 중첩 가격 차원인데 {cls.__name__}._PRICE_DIM_NESTED_ATTRS 에 없다"
    )
    declared_keys = set(cls._PRICE_DIM_NESTED_ATTRS[attr])
    expected_keys = set(keys.split(","))
    assert expected_keys <= declared_keys, (
        f"{filename}:{attr} 의 가격 키 {expected_keys - declared_keys} 가 "
        f"{cls.__name__}._PRICE_DIM_NESTED_ATTRS[{attr!r}] 에 없다"
    )
