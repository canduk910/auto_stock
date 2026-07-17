"""멀티데이 전략 등록 정합 — `_MULTIDAY_STRATEGIES` 단일 리터럴 선언 (2026-07).

배경: vcp_breakout 이 import 시점 side-effect 로 `Position._MULTIDAY_STRATEGIES`
를 동적 변형(`Position._MULTIDAY_STRATEGIES = frozenset(... | {"vcp_breakout"})`)
하던 취약 패턴을 리터럴 단일 선언으로 통합. import-order 의존 + 비명시(리뷰어
오판 유발) 제거. 런타임 집합 `{donchian_swing, vcp_breakout, kojiro}` 불변.

계약:
- strategy_base 리터럴에 3 전략 모두 명시 (import-order 독립).
- vcp_breakout.py 는 `_MULTIDAY_STRATEGIES` 동적 변형 0건 (AST 가드).
- 런타임(전 전략 import) 집합 = {donchian_swing, vcp_breakout, kojiro}.
- 3 전략 모두 `is_next_day` 항상 False (익일청산 오매도 차단).
"""

from __future__ import annotations

import ast
import inspect
from datetime import date, timedelta

import pytest

from src.engine.strategy_base import Position

pytestmark = pytest.mark.unit

_EXPECTED = frozenset({"donchian_swing", "vcp_breakout", "kojiro"})


def _multiday_literal_members() -> set[str]:
    """strategy_base.py 소스에서 `_MULTIDAY_STRATEGIES = frozenset({...})` 리터럴 문자열 추출."""
    import src.engine.strategy_base as sb
    tree = ast.parse(inspect.getsource(sb))
    for node in ast.walk(tree):
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) \
                and node.target.id == "_MULTIDAY_STRATEGIES":
            call = node.value
            # frozenset({...}) 형태
            if isinstance(call, ast.Call) and call.args and isinstance(call.args[0], ast.Set):
                return {e.value for e in call.args[0].elts if isinstance(e, ast.Constant)}
    return set()


def test_strategy_base_literal_declares_all_three():
    # import-order 독립 — 리터럴 자체에 3 전략 명시 (동적 추가 의존 제거)
    assert _multiday_literal_members() == set(_EXPECTED)


def test_vcp_breakout_no_dynamic_multiday_mutation():
    # vcp_breakout.py 가 Position._MULTIDAY_STRATEGIES 를 동적 변형하지 않음
    import src.engine.strategies.vcp_breakout as vcp_mod
    tree = ast.parse(inspect.getsource(vcp_mod))
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Attribute) and t.attr == "_MULTIDAY_STRATEGIES":
                    pytest.fail("vcp_breakout.py 가 _MULTIDAY_STRATEGIES 동적 변형 — 리터럴로 이전 필요")


def test_runtime_multiday_set_after_all_imports():
    import src.engine.scheduler  # noqa: F401 — 전 전략 import 유발
    assert Position._MULTIDAY_STRATEGIES == _EXPECTED


@pytest.mark.parametrize("sid", ["donchian_swing", "vcp_breakout", "kojiro"])
def test_multiday_position_is_next_day_false(sid):
    import src.engine.scheduler  # noqa: F401 — 동적 추가 여부와 무관하게 런타임 정합 보장
    yesterday = date.today() - timedelta(days=3)
    pos = Position(ticker="005930", buy_price=10000, quantity=1, order_no="O",
                   strategy_id=sid, buy_date=yesterday)
    assert pos.is_next_day is False
