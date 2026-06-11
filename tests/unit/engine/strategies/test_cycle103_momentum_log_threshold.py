"""사이클 103 영역 2 — momentum.py:127 손절 로그 임계 동행 emit 회귀 가드.

명세: _workspace/red/cycle103_area2_momentum_log_threshold.md
영속 의무: 사이클 38 명문화 / 사이클 89 한글 친숙 용어 / 사이클 102 G-DOC1

HIGH-1: momentum.py:127 logger.info 호출 영역 임계 인자 영구 영속 (Red 상태)
"""

from __future__ import annotations

import logging

import pytest

from src.engine.strategies.momentum import MomentumStrategy
from src.engine.strategy_base import Position, Signal, StrategyConfig


@pytest.fixture
def strategy():
    """MomentumStrategy 인스턴스 (디폴트 params)."""
    cfg = StrategyConfig(
        strategy_id="momentum",
        name="상한가 모멘텀",
        weight=0.25,
        params={},  # DEFAULT_PARAMS 사용 (stop_loss_rate=-7.5)
    )
    return MomentumStrategy(cfg)


def test_h1_logger_args_include_stop_loss_threshold(caplog, strategy, monkeypatch):
    """HIGH-1: 손절 발화 시 logger.info 인자에 stop_loss 임계값 포함 영속.

    사이클 103 영역 2 Red 명세:
    - 메시지 형식: "손절 신호: %s 매수가(%d) 대비 %.1f%% (임계: %.1f%%, 현재가: %d)"
    - args 영역 ≥5건 (ticker / buy_price / loss_rate / stop_loss / current_price)
    - stop_loss = self.config.params["stop_loss_rate"] (디폴트 -7.5)
    """
    # 보유 포지션 등록 (매수가 10000, 손절 임계 -7.5% = 9250)
    pos = Position(
        ticker="005930",
        buy_price=10000,
        quantity=10,
        order_no="20260611-001",
        strategy_id="momentum",
    )
    strategy.state.positions["005930"] = pos

    # scanner.t / ticker_prev_close 의존 mocking (graceful)
    import src.engine.scanner as scanner_mod

    monkeypatch.setattr(scanner_mod, "t", lambda x: f"종목명({x})", raising=False)

    # 손절 임계 초과 시점 (현재가 9000 = -10%, 임계 -7.5% 초과)
    caplog.set_level(logging.INFO, logger="src.engine.strategies.momentum")

    signal = strategy.check_exit_signal(
        ticker="005930",
        current_price=9000,
        open_price=10000,
    )

    # Signal.STOP_LOSS 반환 영속
    assert signal == Signal.STOP_LOSS, f"손절 신호 발화 영역 영속 실패 (실제: {signal})"

    # logger 호출 영역 영속
    stop_loss_records = [
        r for r in caplog.records if "손절 신호" in r.getMessage()
    ]
    assert len(stop_loss_records) >= 1, "[손절 신호] 로그 발화 영역 영속 실패"

    record = stop_loss_records[0]

    # 핵심 영역 = args 영역 5건 영속 (사이클 103 영역 2 시정)
    assert len(record.args) >= 5, (
        f"손절 로그 args 영역 ≥5건 영속 실패 "
        f"(실제: {len(record.args)}건, 사이클 103 영역 2 = stop_loss 임계 인자 추가 영역)"
    )

    # stop_loss 인자 값 영속 (디폴트 -7.5)
    # args 순서: (ticker, buy_price, loss_rate, stop_loss, current_price)
    expected_stop_loss = strategy.config.params["stop_loss_rate"]
    assert expected_stop_loss == -7.5, "디폴트 stop_loss_rate=-7.5 영속 실패"

    # args[3] = stop_loss 영역 (사이클 103 영역 2 신규 추가)
    assert record.args[3] == expected_stop_loss, (
        f"stop_loss 인자 영역 영속 실패 "
        f"(기대: {expected_stop_loss}, 실제 args[3]: {record.args[3]})"
    )

    # "임계:" 문자열 영역 영속 (사이클 89 한글 친숙 용어 답습)
    assert "임계" in record.getMessage(), (
        f"한글 라벨 [임계:] 영역 영속 실패 "
        f"(실제 메시지: {record.getMessage()})"
    )


def test_h1_logger_message_format_template(caplog, strategy, monkeypatch):
    """HIGH-1 (보강): 메시지 템플릿 영역 영속 (사이클 103 영역 2 시정 영역).

    메시지: "손절 신호: %s 매수가(%d) 대비 %.1f%% (임계: %.1f%%, 현재가: %d)"
    """
    pos = Position(
        ticker="000660",
        buy_price=50000,
        quantity=2,
        order_no="20260611-002",
        strategy_id="momentum",
    )
    strategy.state.positions["000660"] = pos

    import src.engine.scanner as scanner_mod

    monkeypatch.setattr(scanner_mod, "t", lambda x: f"종목명({x})", raising=False)

    caplog.set_level(logging.INFO, logger="src.engine.strategies.momentum")

    # -10% 손실 (45000)
    strategy.check_exit_signal(
        ticker="000660",
        current_price=45000,
        open_price=50000,
    )

    stop_loss_records = [
        r for r in caplog.records if "손절 신호" in r.getMessage()
    ]
    assert len(stop_loss_records) >= 1

    # 메시지 영역에 "임계:" 영역 영속 (사이클 103 영역 2 = 한글 친숙 용어 답습)
    msg = stop_loss_records[0].getMessage()
    assert "임계:" in msg, f"[임계:] 영역 영속 실패 (메시지: {msg})"
    assert "현재가:" in msg, f"[현재가:] 영역 영속 실패 (메시지: {msg})"
