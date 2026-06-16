"""사이클 149 (2026-06-16) — AST 영구 가드.

`src/engine/market_operation_monitor.py` 모듈 전역 3 dict 분리 영속.
사이클 88 G-REJECT-3 (4 dict) + 사이클 135 (5 dict) + 사이클 149 (8 dict) 영속 의무.

통합 단일 dict 영구 차단 (책임 분리 + AST 영구 가드).

domain-expert 자문: `_workspace/domain_consult/cycle149_h0unmko0_per_ticker_subscription.md`
"""

from __future__ import annotations

import ast
from pathlib import Path


_MODULE_PATH = (
    Path(__file__).resolve().parents[3] / "src" / "engine" / "market_operation_monitor.py"
)


def test_G_AST1_three_dicts_separate_persistence() -> None:
    """HIGH — 3 dict 영구 분리 영속 (사이클 88 G-REJECT-3 영속 답습).

    `_vi_active_tickers` + `_halt_active_tickers` + `_market_op_last_event`
    모듈 전역 영역 영구 영속 = 통합 단일 dict 영구 차단.
    """
    source = _MODULE_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)

    # 모듈 전역 변수 정의 추출
    module_level_names: set[str] = set()
    for node in tree.body:
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = (
                node.targets if isinstance(node, ast.Assign) else [node.target]
            )
            for tgt in targets:
                if isinstance(tgt, ast.Name):
                    module_level_names.add(tgt.id)

    # 3 dict 영구 분리 영속 (사이클 149 명세)
    required_names = {
        "_vi_active_tickers",
        "_halt_active_tickers",
        "_market_op_last_event",
    }
    missing = required_names - module_level_names
    assert not missing, f"3 dict 영구 분리 영속 위반 — missing: {missing}"
