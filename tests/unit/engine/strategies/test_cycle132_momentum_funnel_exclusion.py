"""사이클 132 (2026-06-15) — momentum funnel 영구 제외 명시 격리 가드.

사용자 결정 영속:
- Q2=C momentum funnel 영구 제외 + UI 안내 동행

배경:
- momentum 전략 = 실시간 본질 영역 (전일종가 +29% 돌파 순간만 매수)
- prepare() 영역 = empty stub (사이클 21 momentum scan_filter_stats 영역 활용)
- funnel snapshot 영역 = 사이클 39+41 자동 hook 대상 외 (BFB/VCP/donchian 한정 영속)
- 사용자 결정 = momentum funnel 영구 제외 명시 + UI 안내 동행

영속 의무:
- 사이클 38 명문화 (실시간 본질 영역 = 매수 진입 전 후보 풀 영역 외)
- 사이클 39+41 funnel 자동 hook = BFB/VCP/donchian 한정 영속
- 사이클 89 한글 친숙 용어 영속
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from src.engine.strategies.momentum import MomentumStrategy
from src.engine.strategy_base import StrategyConfig


_MOMENTUM_PY = Path("src/engine/strategies/momentum.py")


# =============================================================================
# G-132-A — momentum prepare() empty stub 영구 영속
# =============================================================================


class TestMomentumPrepareEmptyStub:
    """momentum prepare() 영구 영속 = empty stub + funnel 미적재 영구 영속."""

    @pytest.mark.asyncio
    async def test_g_132_a1_prepare_does_not_record_funnel(self):
        """G-132-A1 — momentum.prepare() 호출 후 _funnel_steps 미적재 영구 영속.

        사이클 39+41 _record_funnel_step hook 호출 0건 영구 영속.
        실시간 본질 영역 = funnel 적재 영역 외.
        """
        config = StrategyConfig(
            strategy_id="momentum",
            name="모멘텀",
            enabled=True,
            weight=0.25,
            params={},
        )
        strategy = MomentumStrategy(config)

        # prepare() 호출 (empty stub)
        await strategy.prepare()

        # _funnel_steps 미적재 영구 영속 의무
        funnel_steps = getattr(strategy, "_funnel_steps", None)
        assert funnel_steps is None or len(funnel_steps) == 0, (
            f"momentum prepare() 후 _funnel_steps 적재 영역 영구 영속 위반 — "
            f"got {funnel_steps}. 실시간 본질 영역 = funnel 미적재 의무 영속."
        )


# =============================================================================
# G-132-B — momentum docstring "실시간 본질" 영구 영속 AST 가드
# =============================================================================


class TestMomentumDocstringPersistence:
    """momentum prepare() docstring 영구 영속 = 사이클 132 Q2=C 명시 영구 영속."""

    def test_g_132_b1_prepare_docstring_real_time_essence(self):
        """G-132-B1 — momentum prepare() docstring 영구 영속 = "실시간" 영역 명시.

        사이클 132 Q2=C 영구 영속 명시 의무.
        docstring 영역 영속 = "실시간" 또는 "funnel 미적재" 영역 명시 의무.
        """
        source = _MOMENTUM_PY.read_text(encoding="utf-8")
        tree = ast.parse(source)

        # MomentumStrategy 클래스 영역 찾기
        prepare_node = None
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == "MomentumStrategy":
                for inner in node.body:
                    if isinstance(inner, ast.AsyncFunctionDef) and inner.name == "prepare":
                        prepare_node = inner
                        break

        assert prepare_node is not None, (
            "MomentumStrategy.prepare() 영역 부재 — momentum 영역 영구 영속 위반"
        )

        # docstring 추출
        docstring = ast.get_docstring(prepare_node) or ""
        # "실시간" 또는 "funnel" 키워드 영속 의무 (사이클 132 Q2=C 영속)
        has_real_time_marker = "실시간" in docstring
        has_funnel_marker = "funnel" in docstring.lower()
        assert has_real_time_marker or has_funnel_marker, (
            f"momentum prepare() docstring 영역 영구 영속 위반 — "
            f'"실시간" 또는 "funnel" 키워드 영속 의무. '
            f"got docstring={docstring!r}. 사이클 132 Q2=C 영속."
        )


# =============================================================================
# G-132-C — momentum funnel 미적재 영속 운영 정합 영역
# =============================================================================


class TestMomentumFunnelExclusionPersistence:
    """momentum 영역 funnel 자동 hook 영역 영속 미진입 영구 영속.

    사이클 39+41 funnel 자동 hook = BFB/VCP/donchian 한정 영속.
    momentum 영역 = 자동 hook 영역 외 영구 영속 의무.
    """

    def test_g_132_c1_momentum_no_record_funnel_step_call(self):
        """G-132-C1 — momentum.py 본체 영역 _record_funnel_step 호출 0건 영구 영속.

        사이클 39+41 funnel 자동 hook = BFB/VCP/donchian 한정 영속.
        momentum 영역 = 호출 0건 영구 영속 의무 (Q2=C 영속).
        """
        source = _MOMENTUM_PY.read_text(encoding="utf-8")
        tree = ast.parse(source)

        record_funnel_calls = 0
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Attribute) and func.attr == "_record_funnel_step":
                    record_funnel_calls += 1
                elif isinstance(func, ast.Name) and func.id == "_record_funnel_step":
                    record_funnel_calls += 1

        assert record_funnel_calls == 0, (
            f"momentum.py 본체 영역 _record_funnel_step 호출 영구 영속 위반 — "
            f"got {record_funnel_calls} 건. 사이클 132 Q2=C 영구 제외 영속 의무."
        )
