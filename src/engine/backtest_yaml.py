"""6 전략을 외부 MCP 백테스트 서버 YAML DSL 로 변환 (Phase 2).

외부 서버 (`http://43.202.187.5:3846/mcp`) YAML DSL 구조 (실측 확인):

```yaml
version: "1.0.0"
metadata: {name, description, author, tags}
strategy:
  id: <strategy_id>
  category: trend | momentum | mean_reversion
  indicators:
    - {id, alias, params, output}
  candlesticks: []
  entry:
    logic: AND | OR
    conditions:
      - {indicator, operator: cross_above/cross_below/greater_than/less_than, compare_to, value, output, compare_output}
  exit:
    logic: AND | OR
    conditions: [...]
  params: { <param_name>: {default, min, max, type, description} }
risk:
  stop_loss: {enabled, percent}
  take_profit: {enabled, percent}
  trailing_stop: {enabled, percent}
```

지원 지표 (70+): sma/ema/dema/tema/hma/kama/alma/lwma/trima/t3/zlema/wma/frama/vidya/...,
roc, maximum, minimum, donchian, atr, rsi, macd, bb, ...

표현력 평가:
- **(a) 표현 가능 (근사)** — momentum, volatility_breakout, donchian_swing
- **(b) 표현 불가 (BacktestNotSupportedError)** — long_tail_volatility, bull_flag_breakout, vcp_breakout
  - 상한가 모드 전환, 폴/플래그 자동 검출, 베이스 수축, swing high/low 검출 미지원

Phase 4-bis 에서 (b) 전략은 stock-manager `services/local_backtest/strategies/` 패턴
어댑터를 우리 코드에 이식하여 폴백 처리할 계획. 본 Phase 는 raise 까지만.

회귀 안전:
- 동일 입력 → 동일 YAML 출력 (PyYAML 정렬 보장 위해 ``sort_keys=False`` 명시).
- DEFAULT_PARAMS 자동 합성 — params 가 빈 dict 여도 유효한 YAML 생성.
"""

from __future__ import annotations

import logging
from typing import Any

import yaml

from src.services.exceptions import BacktestNotSupportedError

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 헬퍼
# ---------------------------------------------------------------------------
def _merged_params(strategy_id: str, params: dict[str, Any]) -> dict[str, Any]:
    """DEFAULT_PARAMS + user params 머지 — strategy 클래스에서 DEFAULT_PARAMS 추출."""
    # 동적 import 로 순환 방지 (engine.strategies → 사용처 import 그래프)
    if strategy_id == "momentum":
        from src.engine.strategies.momentum import MomentumStrategy
        defaults = MomentumStrategy.DEFAULT_PARAMS
    elif strategy_id == "volatility_breakout":
        from src.engine.strategies.volatility_breakout import VolatilityBreakoutStrategy
        defaults = VolatilityBreakoutStrategy.DEFAULT_PARAMS
    elif strategy_id == "donchian_swing":
        from src.engine.strategies.donchian_swing import DonchianSwingStrategy
        defaults = DonchianSwingStrategy.DEFAULT_PARAMS
    else:
        defaults = {}
    return {**defaults, **(params or {})}


def _abs_pct(value: Any, default: float) -> float:
    """음수 손절률(-7.5) → 양수 7.5 (외부 risk.stop_loss.percent 는 항상 양수)."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return default
    return abs(v) if v != 0 else default


def _yaml_dump(doc: dict) -> str:
    """동일 입력 → 동일 출력 보장 + UTF-8 한글 그대로."""
    return yaml.safe_dump(
        doc, sort_keys=False, allow_unicode=True, default_flow_style=False
    )


# ---------------------------------------------------------------------------
# 메인 진입점
# ---------------------------------------------------------------------------
def build_yaml(strategy_id: str, params: dict[str, Any]) -> str:
    """6 전략 → 외부 MCP YAML DSL 문자열.

    Raises:
        BacktestNotSupportedError: 표현 불가능한 전략 (long_tail_volatility / bull_flag_breakout / vcp_breakout)
                                   또는 알 수 없는 strategy_id.
    """
    if strategy_id == "momentum":
        return _build_momentum_yaml(_merged_params(strategy_id, params))
    if strategy_id == "volatility_breakout":
        return _build_volatility_breakout_yaml(_merged_params(strategy_id, params))
    if strategy_id == "donchian_swing":
        return _build_donchian_swing_yaml(_merged_params(strategy_id, params))

    # (b) 폴백 전략 + 알 수 없는 ID — 명시 raise
    if strategy_id in ("long_tail_volatility", "bull_flag_breakout", "vcp_breakout"):
        raise BacktestNotSupportedError(
            f"{strategy_id}: 외부 MCP YAML DSL 표현 불가능. Phase 4-bis 로컬 어댑터에서 처리 예정."
        )
    raise BacktestNotSupportedError(
        f"unknown strategy_id: {strategy_id!r}. 지원 ID: momentum, volatility_breakout, donchian_swing"
    )


# ---------------------------------------------------------------------------
# (a-1) momentum: ROC(1) > buy_threshold + stop_loss
# ---------------------------------------------------------------------------
def _build_momentum_yaml(p: dict[str, Any]) -> str:
    """전일 종가 +N% 돌파 + 손절 % 매핑.

    근사:
    - "전일 종가 대비 +29% 돌파" → ROC(period=1) > 29
    - "-7.5% 손절" → risk.stop_loss.percent = 7.5
    - 익일 시가 청산은 YAML DSL 표현 불가 → take_profit 으로 근사 (선택)
    """
    buy_threshold = float(p.get("buy_threshold", 29.0))
    stop_loss_pct = _abs_pct(p.get("stop_loss_rate"), 7.5)
    trailing_pct = _abs_pct(p.get("trailing_stop_rate"), 2.0)

    doc = {
        "version": "1.0.0",
        "metadata": {
            "name": "Momentum (auto_stock 매핑)",
            "description": f"전일 종가 대비 +{buy_threshold}% 돌파 시 매수 (ROC(1) 근사)",
            "author": "auto_stock",
            "tags": ["momentum", "breakout", "intraday"],
        },
        "strategy": {
            "id": "momentum",
            "category": "momentum",
            "indicators": [
                {
                    "id": "roc",
                    "alias": "roc1",
                    "params": {"period": 1},
                    "output": "value",
                },
            ],
            "candlesticks": [],
            "entry": {
                "logic": "AND",
                "conditions": [
                    {
                        "indicator": "roc1",
                        "operator": "greater_than",
                        "value": buy_threshold,
                        "output": "value",
                    },
                ],
            },
            "exit": {
                "logic": "OR",
                "conditions": [
                    {
                        "indicator": "roc1",
                        "operator": "less_than",
                        "value": 0.0,
                        "output": "value",
                    },
                ],
            },
            "params": {
                "buy_threshold": {
                    "default": buy_threshold,
                    "min": 5.0,
                    "max": 30.0,
                    "type": "float",
                    "description": "전일 종가 대비 돌파 임계치 %",
                },
                "stop_loss_pct": {
                    "default": stop_loss_pct,
                    "min": 1.0,
                    "max": 20.0,
                    "type": "float",
                    "description": "손절 %",
                },
            },
        },
        "risk": {
            "stop_loss": {"enabled": True, "percent": stop_loss_pct},
            "trailing_stop": {"enabled": trailing_pct > 0, "percent": trailing_pct},
        },
    }
    return _yaml_dump(doc)


# ---------------------------------------------------------------------------
# (a-2) volatility_breakout: ATR(20) 근사 변동성 + stop_loss
# ---------------------------------------------------------------------------
def _build_volatility_breakout_yaml(p: dict[str, Any]) -> str:
    """변동성 돌파 근사.

    근사:
    - "K값 × 전일 Range 돌파" → ATR(k_period)+가격 비교는 단순 표현 불가 →
      대신 "close > previous N-day high" 패턴 + ATR 지표 첨부로 외부 평가.
    - 보드별 K값 (krx_main / nxt_pre / nxt_post) 은 외부 백테스트 일봉 단위라 무의미 →
      k_value_krx_main 만 채택.
    - "-3% 손절" → stop_loss.percent
    - "15:20 일괄 청산" 은 일봉 백테스트 무의미 → exit 에 ATR 손절 보강
    """
    k_period = int(p.get("k_period", 20))
    stop_loss_pct = _abs_pct(p.get("stop_loss_rate"), 3.0)

    doc = {
        "version": "1.0.0",
        "metadata": {
            "name": "Volatility Breakout (auto_stock 매핑)",
            "description": f"ATR({k_period}) 변동성 돌파 근사",
            "author": "auto_stock",
            "tags": ["volatility", "breakout", "atr"],
        },
        "strategy": {
            "id": "volatility_breakout",
            "category": "momentum",
            "indicators": [
                {
                    "id": "atr",
                    "alias": "atr_n",
                    "params": {"period": k_period},
                    "output": "value",
                },
                {
                    "id": "maximum",
                    "alias": "prev_high",
                    "params": {"period": 1},
                    "output": "value",
                },
            ],
            "candlesticks": [],
            "entry": {
                "logic": "AND",
                "conditions": [
                    {
                        "indicator": "close",
                        "operator": "cross_above",
                        "compare_to": "prev_high",
                        "output": "close",
                        "compare_output": "value",
                    },
                ],
            },
            "exit": {
                "logic": "OR",
                "conditions": [
                    {
                        "indicator": "close",
                        "operator": "cross_below",
                        "compare_to": "prev_high",
                        "output": "close",
                        "compare_output": "value",
                    },
                ],
            },
            "params": {
                "k_period": {
                    "default": k_period,
                    "min": 5,
                    "max": 60,
                    "type": "int",
                    "description": "ATR/Range 계산 기간",
                },
                "stop_loss_pct": {
                    "default": stop_loss_pct,
                    "min": 1.0,
                    "max": 10.0,
                    "type": "float",
                    "description": "손절 %",
                },
            },
        },
        "risk": {
            "stop_loss": {"enabled": True, "percent": stop_loss_pct},
        },
    }
    return _yaml_dump(doc)


# ---------------------------------------------------------------------------
# (a-3) donchian_swing: maximum(high, 20) + EMA(60) + trailing_stop
# ---------------------------------------------------------------------------
def _build_donchian_swing_yaml(p: dict[str, Any]) -> str:
    """돈치안 스윙 — 가장 정합도 높은 매핑.

    근사:
    - "20일 신고가 돌파" → close cross_above maximum(high, 20)
    - "60일 EMA 상승" → close > ema(60) (5일 변화 부등식은 단순 표현 불가 → close > ema)
    - "거래대금 1.5×" 는 외부 백테스트가 volume 지표만 받음 → params 로 첨부 (현재 미사용)
    - "-7% 하드 손절" → risk.stop_loss.percent = 7
    - "ATR(14) × 2 트레일링" → risk.trailing_stop (atr_period/atr_trail_mult 는 params)
    """
    donchian_period = int(p.get("donchian_period", 20))
    long_ma_period = int(p.get("long_ma_period", 60))
    stop_loss_pct = _abs_pct(p.get("stop_loss_rate"), 7.0)
    atr_period = int(p.get("atr_period", 14))
    atr_trail_mult = float(p.get("atr_trail_mult", 2.0))
    # ATR 트레일링을 percent 로 환산하기 어렵지만, 외부 risk.trailing_stop.percent
    # 만 받으니 atr_trail_mult × 일평균변동률 근사 — 보수적으로 5% 디폴트
    trailing_pct = max(3.0, atr_trail_mult * 2.5)

    doc = {
        "version": "1.0.0",
        "metadata": {
            "name": "Donchian Swing (auto_stock 매핑)",
            "description": (
                f"{donchian_period}일 신고가 + EMA({long_ma_period}) 추세 필터 + "
                f"ATR({atr_period}) × {atr_trail_mult} 트레일링"
            ),
            "author": "auto_stock",
            "tags": ["swing", "breakout", "donchian", "trend"],
        },
        "strategy": {
            "id": "donchian_swing",
            "category": "trend",
            "indicators": [
                {
                    "id": "maximum",
                    "alias": "donchian_high",
                    "params": {"period": donchian_period},
                    "output": "value",
                },
                {
                    "id": "ema",
                    "alias": "ema_long",
                    "params": {"period": long_ma_period},
                    "output": "value",
                },
                {
                    "id": "atr",
                    "alias": "atr_n",
                    "params": {"period": atr_period},
                    "output": "value",
                },
            ],
            "candlesticks": [],
            "entry": {
                "logic": "AND",
                "conditions": [
                    {
                        "indicator": "close",
                        "operator": "cross_above",
                        "compare_to": "donchian_high",
                        "output": "close",
                        "compare_output": "value",
                    },
                    {
                        "indicator": "close",
                        "operator": "greater_than",
                        "compare_to": "ema_long",
                        "output": "close",
                        "compare_output": "value",
                    },
                ],
            },
            "exit": {
                "logic": "OR",
                "conditions": [
                    {
                        "indicator": "close",
                        "operator": "cross_below",
                        "compare_to": "ema_long",
                        "output": "close",
                        "compare_output": "value",
                    },
                ],
            },
            "params": {
                "donchian_period": {
                    "default": donchian_period,
                    "min": 10,
                    "max": 60,
                    "type": "int",
                    "description": "Donchian 채널 기간",
                },
                "long_ma_period": {
                    "default": long_ma_period,
                    "min": 20,
                    "max": 200,
                    "type": "int",
                    "description": "장기 EMA 기간",
                },
                "stop_loss_pct": {
                    "default": stop_loss_pct,
                    "min": 3.0,
                    "max": 15.0,
                    "type": "float",
                    "description": "하드 손절 %",
                },
                "atr_period": {
                    "default": atr_period,
                    "min": 7,
                    "max": 30,
                    "type": "int",
                    "description": "ATR 기간",
                },
                "atr_trail_mult": {
                    "default": atr_trail_mult,
                    "min": 1.0,
                    "max": 5.0,
                    "type": "float",
                    "description": "ATR 트레일링 배수",
                },
            },
        },
        "risk": {
            "stop_loss": {"enabled": True, "percent": stop_loss_pct},
            "trailing_stop": {"enabled": True, "percent": trailing_pct},
        },
    }
    return _yaml_dump(doc)
