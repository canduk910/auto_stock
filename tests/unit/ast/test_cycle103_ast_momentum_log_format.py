"""사이클 103 영역 2 — momentum.py 손절 로그 메시지 영역 AST 영구 가드.

명세: _workspace/red/cycle103_area2_momentum_log_threshold.md
영속 의무: 사이클 89 G-AST + 사이클 102 G-DOC1 영구 영속 패턴 답습

HIGH-2: momentum.py 영역 AST `"%.1f%% (임계: %.1f%%)"` 형식 영역 영속 (Red 상태)
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
MOMENTUM_PY = REPO_ROOT / "src" / "engine" / "strategies" / "momentum.py"


def test_h2_ast_log_format_includes_threshold():
    """HIGH-2: momentum.py 손절 로그 메시지 영역 = 임계 동행 영구 영속.

    사이클 103 영역 2 시정 영역:
    - 메시지: "손절 신호: %s 매수가(%d) 대비 %.1f%% (임계: %.1f%%, 현재가: %d)"
    - 기존 (사이클 102 이전): "...%.1f%% (현재가: %d)" 영역 폐기 영구 차단
    """
    assert MOMENTUM_PY.exists(), f"momentum.py 영역 영속 실패 ({MOMENTUM_PY})"

    src = MOMENTUM_PY.read_text(encoding="utf-8")

    # 사이클 103 영역 2 = 임계 영역 명시 영속 (정적 grep)
    expected_pattern = "%.1f%% (임계: %.1f%%, 현재가:"
    assert expected_pattern in src, (
        f"[손절 로그 영역 임계 동행 영구 영속 실패] "
        f"momentum.py 영역에 신규 메시지 형식 영역 부재 "
        f"(기대 패턴: {expected_pattern!r}). "
        f"사이클 103 영역 2 Red 명세 영속 의무 = momentum.py:127 영역 시정 의무 영속."
    )


def test_h2_ast_legacy_format_removed():
    """HIGH-2 (보강): 사이클 102 이전 메시지 영역 = 영구 폐기 영속.

    사이클 103 영역 2 시정 후:
    - 폐기 영역: "%.1f%% (현재가: %d)" 영역 = 손절 신호 영역에서 폐기 의무
    - momentum.py 영역 = 손절 영역 (L127) + 익일 청산 영역 (L148) + 트레일링 영역 (L158)
    - 손절 영역만 신규 형식 (임계 동행), 익일/트레일링은 기존 형식 유지 영속
    """
    src = MOMENTUM_PY.read_text(encoding="utf-8")

    # 손절 신호 영역 메시지 (L127) 검색
    # "손절 신호: %s 매수가(%d) 대비 %.1f%%" 영역 = 신규 형식 영역
    # "...%.1f%% (현재가: %d)" 영역 (구 형식) 이 손절 신호 영역에 영속하면 = 영구 차단
    lines = src.splitlines()

    for i, line in enumerate(lines):
        if "손절 신호:" in line:
            # 손절 신호 영역 메시지 영속 (다음 1줄 영역 영속 = 인자 영역)
            assert "임계:" in line, (
                f"[손절 신호 영역 임계 동행 영구 영속 실패] "
                f"line {i + 1}: {line!r}. "
                f"사이클 103 영역 2 = momentum.py:127 영역 시정 영구 영속 의무 영역."
            )


def test_h2_ast_stop_loss_arg_present():
    """HIGH-2 (추가 보강): logger.info 호출 영역 = stop_loss 인자 영역 영속.

    사이클 103 영역 2 시정:
    - logger.info 호출 인자 영역 = (msg, ticker, buy_price, loss_rate, **stop_loss**, current_price)
    - args 영역 ≥5건 영속
    - `stop_loss` 변수 영역 = `self.config.params["stop_loss_rate"]` (L124) 영역 영속
    """
    src = MOMENTUM_PY.read_text(encoding="utf-8")

    # logger.info("손절 신호: ...") 영역 = "stop_loss" 변수 영역 영속 영역
    # `stop_loss = self.config.params["stop_loss_rate"]` (L124) 영역 영속
    assert 'stop_loss = self.config.params["stop_loss_rate"]' in src, (
        "[stop_loss 변수 영역 영속 실패] "
        "L124 영역 영속 의무 영속 (`stop_loss = self.config.params[\"stop_loss_rate\"]`)."
    )

    # 손절 영역 logger.info 호출 영역 = `stop_loss` 변수 영역 인자 영역 영속
    # (사이클 103 영역 2 시정 후) `t(ticker), pos.buy_price, loss_rate, stop_loss, current_price,`
    # 영역 영속
    has_stop_loss_in_args = False
    in_stop_loss_logger = False
    for line in src.splitlines():
        if "손절 신호:" in line:
            in_stop_loss_logger = True
            continue
        if in_stop_loss_logger:
            if "stop_loss" in line and ("loss_rate" in line or "buy_price" in line):
                has_stop_loss_in_args = True
                break
            if ")" in line and "logger.info" not in line:
                # logger.info 호출 영역 종료
                break

    assert has_stop_loss_in_args, (
        "[손절 로그 args 영역 stop_loss 인자 영구 영속 실패] "
        "사이클 103 영역 2 시정 의무 = logger.info args 영역에 `stop_loss` 변수 영역 추가 영속."
    )
