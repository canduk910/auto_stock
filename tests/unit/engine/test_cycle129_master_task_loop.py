"""사이클 129 — 16:30 KST 마스터 task lifecycle Red 회귀 가드.

배경:
- domain-consult 의제 5 채택 — 옵션 A 16:30 KST 단일 task
- 사이클 122/126 task 패턴 답습 (start() 직후 1회 + while 루프)
- 사이클 79 G-AST2 task_attrs 3곳 영속

회귀 가드 3 케이스:
- G-TL1: TIME_STOCK_MASTER_MASTER_LOAD = time(16, 30)
- G-TL2: _stock_master_master_load_task_loop 함수 영속
- G-TL3: task_attrs 3곳 영속 (`_stock_master_master_load_task`, 사이클 79 G-AST2)
"""
from __future__ import annotations


def test_g_tl1_time_constant_16_30():
    """G-TL1: TIME_STOCK_MASTER_MASTER_LOAD = time(16, 30) 영속.

    domain-consult 의제 5 옵션 A 채택 — 16:30 KST 단일 task.
    """
    from datetime import time

    from src.engine import scheduler

    assert hasattr(scheduler, "TIME_STOCK_MASTER_MASTER_LOAD"), (
        "G-TL1: TIME_STOCK_MASTER_MASTER_LOAD 상수 부재"
    )
    assert scheduler.TIME_STOCK_MASTER_MASTER_LOAD == time(16, 30), (
        f"G-TL1: 시각 16:30 위반 (실제 {scheduler.TIME_STOCK_MASTER_MASTER_LOAD})"
    )


def test_g_tl2_task_loop_function_exists():
    """G-TL2: _stock_master_master_load_task_loop 함수 영속.

    사이클 122/126 task 패턴 답습.
    """
    from src.engine.scheduler import TradingScheduler

    assert hasattr(TradingScheduler, "_stock_master_master_load_task_loop"), (
        "G-TL2: TradingScheduler._stock_master_master_load_task_loop 메서드 부재"
    )


def test_g_tl3_task_attrs_3_sites():
    """G-TL3: task_attrs 3곳 영속 (`_stock_master_master_load_task`, 사이클 79 G-AST2).

    사이클 79 G-AST2 패턴 답습 — start() / stop() / connect() finally 3곳.
    """
    from pathlib import Path

    scheduler_src = (
        Path(__file__).resolve().parents[3] / "src/engine/scheduler.py"
    ).read_text(encoding="utf-8")

    # 인스턴스 변수 영역 (None 초기화)
    assert "_stock_master_master_load_task" in scheduler_src, (
        "G-TL3: _stock_master_master_load_task 인스턴스 변수 영역 부재"
    )

    # 카운트 검증 — task_attrs 3곳 등장 영역 (start / stop / connect/run_daily finally)
    occurrences = scheduler_src.count("_stock_master_master_load_task")
    assert occurrences >= 4, (
        f"G-TL3: _stock_master_master_load_task 등장 영역 부족 "
        f"(실제 {occurrences}, 기대 ≥4 — 인스턴스 + start + stop + finally)"
    )
