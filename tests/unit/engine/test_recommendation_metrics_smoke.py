"""recommendation_metrics.py 복구 smoke 테스트.

compute_metrics 가 import 가능하고 기본 호출에 대해 안전하게 반환하는지만 검증.
"""

from __future__ import annotations

import inspect


def test_recommendation_metrics_importable():
    from src.engine import recommendation_metrics

    assert recommendation_metrics is not None


def test_compute_metrics_signature():
    """compute_metrics(trades, performance, current_params) 시그니처 보존."""
    from src.engine.recommendation_metrics import compute_metrics

    assert callable(compute_metrics)
    sig = inspect.signature(compute_metrics)
    assert list(sig.parameters.keys()) == ["trades", "performance", "current_params"]


def test_compute_metrics_empty_inputs_safe():
    """빈 입력에 대해 0 값으로 안전하게 반환해야 한다 (분모 0 가드)."""
    from src.engine.recommendation_metrics import compute_metrics

    result = compute_metrics(trades=[], performance=[], current_params={})
    assert result["trades_count"] == 0
    assert result["buy_count"] == 0
    assert result["sell_count"] == 0
    assert result["win_rate"] == 0.0
    assert result["cumulative_return"] == 0.0
    assert result["analyzed_days"] == 0


def test_compute_metrics_basic_win_loss_count():
    """기본 매수/매도 카운트 + 승률 계산 동작."""
    from src.engine.recommendation_metrics import compute_metrics

    trades = [
        {"trade_type": "BUY", "status": "COMPLETED", "price": 10000, "quantity": 10, "profit_loss": 0},
        {"trade_type": "SELL", "status": "COMPLETED", "price": 11000, "quantity": 10, "profit_loss": 10000},
        {"trade_type": "SELL", "status": "COMPLETED", "price": 9000, "quantity": 10, "profit_loss": -10000},
    ]
    result = compute_metrics(trades=trades, performance=[], current_params={"stop_loss_rate": -7.5})
    assert result["buy_count"] == 1
    assert result["sell_count"] == 2
    assert result["win_count"] == 1
    assert result["loss_count"] == 1
    assert result["win_rate"] == 0.5
