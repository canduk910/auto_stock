"""사이클 156 Q0 — VB/LTV/BFB 영역 nxt_tradable 강제 필터 제거.

사용자 의도 확정:
- nxt_tradable 값은 주문 발사 시점 NXT/KRX 분기용 (사이클 54 _strategy_exchange_async)
- 유니버스 스캔 영역에서 nxt_tradable=True 강제 적용 = 후보 풀 83.8% 영구 축소 silent

운영 DB 실측 (2026-06-17):
- total = 3,573 / nxt_true = 579 (16.2%) / nxt_false = 2,994 (83.8%)
- 시정 후 후보 풀 ~5.2배 확장 예상

회귀 가드:
- G-156-Q0-VB / LTV / BFB: list_by_filter 호출 영역 nxt_tradable 인자 부재 확인
- G-156-Q0-DONCHIAN: donchian 영역 변경 0 (이미 사이클 121 제거)
- G-156-Q0-SAFETY: 주문 시점 분기 메커니즘 변경 0 (order_engine + sell_rejection)
"""

from __future__ import annotations

import ast
import pathlib

import pytest

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[4]
_VB_PATH = _REPO_ROOT / "src" / "engine" / "strategies" / "volatility_breakout.py"
_LTV_PATH = _REPO_ROOT / "src" / "engine" / "strategies" / "long_tail_volatility.py"
_BFB_PATH = _REPO_ROOT / "src" / "engine" / "strategies" / "bull_flag_breakout.py"
_DONCHIAN_PATH = _REPO_ROOT / "src" / "engine" / "strategies" / "donchian_swing.py"
_ORDER_ENGINE_PATH = _REPO_ROOT / "src" / "engine" / "order_engine.py"


def _find_list_by_filter_calls(src: str) -> list[ast.Call]:
    """소스 영역에서 list_by_filter 호출 노드 영역 추출."""
    tree = ast.parse(src)
    calls = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr == "list_by_filter":
                calls.append(node)
    return calls


def _has_nxt_tradable_kwarg(call: ast.Call) -> bool:
    return any(kw.arg == "nxt_tradable" for kw in call.keywords)


@pytest.mark.parametrize(
    "path,label",
    [
        (_VB_PATH, "VB"),
        (_LTV_PATH, "LTV"),
        (_BFB_PATH, "BFB"),
    ],
)
def test_g_156_q0_no_nxt_tradable_in_list_by_filter(path: pathlib.Path, label: str):
    """G-156-Q0-{VB,LTV,BFB} — list_by_filter 영역 nxt_tradable 인자 부재."""
    src = path.read_text(encoding="utf-8")
    calls = _find_list_by_filter_calls(src)
    assert calls, f"{label} 영역 list_by_filter 호출 부재"
    offending = [c for c in calls if _has_nxt_tradable_kwarg(c)]
    assert not offending, (
        f"{label} 영역 list_by_filter 영역 nxt_tradable 인자 잔존 — 사이클 156 Q0 결함"
    )


def test_g_156_q0_donchian_unchanged():
    """G-156-Q0-DONCHIAN — donchian 영역 list_by_filter nxt_tradable 인자 영역 영속 (None 디폴트, 사이클 121 영역)."""
    src = _DONCHIAN_PATH.read_text(encoding="utf-8")
    calls = _find_list_by_filter_calls(src)
    assert calls, "donchian 영역 list_by_filter 호출 부재"
    # donchian = nxt_tradable=nxt_tradable_param (None 디폴트) 영역 영속 영영 = OK
    # 또는 인자 부재 영역도 OK
    # 의도된 결함 = nxt_tradable=True 강제 영역 부재 검증
    for call in calls:
        for kw in call.keywords:
            if kw.arg == "nxt_tradable":
                # value 영역 영영 True 상수 영영 아닌지 확인
                if isinstance(kw.value, ast.Constant):
                    assert kw.value.value is not True, (
                        "donchian 영역 nxt_tradable=True 강제 적용 결함"
                    )


def test_g_156_q0_safety_order_engine_unchanged():
    """G-156-Q0-SAFETY — 주문 시점 NXT 분기 메커니즘 변경 0 (사이클 54 영속)."""
    src = _ORDER_ENGINE_PATH.read_text(encoding="utf-8")
    # 사이클 54 영역 영구 영속 키워드 영역 = _strategy_exchange_async + nxt_downgrade
    assert "_strategy_exchange" in src, (
        "order_engine 영역 _strategy_exchange 영역 부재 — 주문 시점 NXT 분기 영역 결함"
    )
    assert "nxt_downgrade" in src, (
        "order_engine 영역 [nxt_downgrade] 로그 영역 부재 — 사이클 54 영영 영역 결함"
    )


def test_g_156_q0_step_conditions_label_updated():
    """G-156-Q0-LABEL — funnel step_conditions 영역에서 'nxt_tradable=True' 문자열 영역 영영 영영."""
    for path, label in [(_VB_PATH, "VB"), (_LTV_PATH, "LTV")]:
        src = path.read_text(encoding="utf-8")
        assert "nxt_tradable=True" not in src, (
            f"{label} 영역 'nxt_tradable=True' 문자열 잔존 — 사이클 156 Q0 영역 영영 결함"
        )
