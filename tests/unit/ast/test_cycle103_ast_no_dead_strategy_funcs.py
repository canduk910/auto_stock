"""사이클 103 영역 3 — strategy.py dead code 영구 폐기 AST 영구 가드.

명세: _workspace/red/cycle103_area3_strategy_dead_code.md
영속 의무: 사이클 78 G-AST1 + 사이클 79 G-AST2 영구 영속 패턴 답습

HIGH-1: strategy.py 영역 3 모듈 함수 영역 영구 부재 AST (Red 상태)
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
STRATEGY_PY = REPO_ROOT / "src" / "engine" / "strategy.py"


def test_h1_no_dead_module_func_check_stop_loss():
    """HIGH-1.1: `check_stop_loss` 모듈 함수 영역 영구 부재 영속.

    사이클 103 영역 3 시정 의무:
    - `src/engine/strategy.py:151~171` 영역 = `check_stop_loss` 모듈 함수 영역
    - callsite 영역 = 0건 영속 확인 후 일괄 삭제 영속
    - 미래 동일 영역 재발 영구 차단
    """
    assert STRATEGY_PY.exists(), f"strategy.py 영역 영속 실패 ({STRATEGY_PY})"

    src = STRATEGY_PY.read_text(encoding="utf-8")

    # 정규식 영역 = 모듈 영역 def 영역 (들여쓰기 0건)
    pattern = re.compile(r"^def check_stop_loss\b", re.MULTILINE)
    matches = pattern.findall(src)

    assert len(matches) == 0, (
        f"[dead code 영구 폐기 영속 실패] "
        f"`def check_stop_loss(` 영역 영구 부재 영속 의무 영역 "
        f"(실제 매칭 영역: {len(matches)}건). "
        f"사이클 103 영역 3 Red 명세 영속 의무 = strategy.py:151~171 영역 영구 폐기 영속."
    )


def test_h1_no_dead_module_func_check_next_day_clear():
    """HIGH-1.2: `check_next_day_clear` 모듈 함수 영역 영구 부재 영속.

    사이클 103 영역 3 시정 의무:
    - `src/engine/strategy.py:174~207` 영역 영구 폐기 영속
    """
    src = STRATEGY_PY.read_text(encoding="utf-8")

    pattern = re.compile(r"^def check_next_day_clear\b", re.MULTILINE)
    matches = pattern.findall(src)

    assert len(matches) == 0, (
        f"[dead code 영구 폐기 영속 실패] "
        f"`def check_next_day_clear(` 영역 영구 부재 영속 의무 영역 "
        f"(실제 매칭 영역: {len(matches)}건). "
        f"사이클 103 영역 3 = strategy.py:174~207 영역 영구 폐기 영속."
    )


def test_h1_no_dead_module_func_check_buy_signal():
    """HIGH-1.3: `check_buy_signal` 모듈 함수 영역 영구 부재 영속.

    사이클 103 영역 3 시정 의무:
    - `src/engine/strategy.py:85~148` 영역 = 모듈 영역 def 영역 폐기
    - `MomentumStrategy.check_buy_signal` 클래스 메서드 영역과 분리 영속
    - (메서드 영역 = `    def check_buy_signal` 들여쓰기 4 영역, 모듈 영역 영구 영속)
    """
    src = STRATEGY_PY.read_text(encoding="utf-8")

    # 모듈 영역 def (들여쓰기 0건) = 영구 부재 영속
    pattern = re.compile(r"^def check_buy_signal\b", re.MULTILINE)
    matches = pattern.findall(src)

    assert len(matches) == 0, (
        f"[dead code 영구 폐기 영속 실패] "
        f"모듈 영역 `def check_buy_signal(` 영역 영구 부재 영속 의무 영역 "
        f"(실제 매칭 영역: {len(matches)}건). "
        f"사이클 103 영역 3 = strategy.py:85~148 영역 영구 폐기 영속 "
        f"(MomentumStrategy.check_buy_signal 클래스 메서드 영역과 분리 영속)."
    )


def test_h1_persistence_layer_unchanged():
    """HIGH-1.4 (보강): 영속 영역 (변경 0) = 영역 영속 영구 영속.

    사이클 103 영역 3 영속 영역:
    - `class Signal` enum 영역 영속
    - `class Position` dataclass 영역 영속
    - `class StrategyState` dataclass 영역 영속
    - `_prev_prdy_rate` 모듈 dict 영역 영속
    - 임계 상수 7개 영역 영속 (BUY_THRESHOLD / STOP_LOSS_RATE / GAP_UP_THRESHOLD /
      TRAILING_STOP_RATE / POSITION_RATIO / MAX_POSITIONS / DAILY_LOSS_LIMIT)
    - `calc_buy_quantity` 모듈 함수 영역 영속 (callsite 영역 영속 확인 필요)
    """
    src = STRATEGY_PY.read_text(encoding="utf-8")

    persistence_areas = [
        "class Signal",
        "class Position",
        "class StrategyState",
        "_prev_prdy_rate",
        "BUY_THRESHOLD",
        "STOP_LOSS_RATE",
        "GAP_UP_THRESHOLD",
        "TRAILING_STOP_RATE",
        "POSITION_RATIO",
        "MAX_POSITIONS",
        "DAILY_LOSS_LIMIT",
    ]

    for area in persistence_areas:
        assert area in src, (
            f"[영속 영역 영구 영속 실패] "
            f"영역 = {area!r} = strategy.py 영역 영구 영속 의무 영역 "
            f"(사이클 103 영역 3 영속 영역 영구 영속, dead code 폐기 영역과 분리)."
        )
