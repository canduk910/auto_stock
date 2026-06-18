"""사이클 163 (2026-06-18) — 4 전략 (LTV/donchian/BFB/VCP) prepare 자동 재시도 hook 회귀 가드.

의제 #5 영역 — 사이클 158 VB 패턴 답습 (cap 3회 + 30초 sleep).
6/18 08:24:24 운영 사고 영구 차단 (LTV/donchian/BFB 0건 race 영역 hook 부재 결함).
"""
from __future__ import annotations

import ast
import pathlib

import pytest


_STRATEGY_FILES = {
    "ltv": "src/engine/strategies/long_tail_volatility.py",
    "donchian": "src/engine/strategies/donchian_swing.py",
    "bfb": "src/engine/strategies/bull_flag_breakout.py",
    "vcp": "src/engine/strategies/vcp_breakout.py",
}


def _find_prepare_function(tree: ast.AST) -> ast.AsyncFunctionDef | None:
    """클래스 내부 async def prepare 찾기."""
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "prepare":
            return node
    return None


def _has_retry_hook(prepare_node: ast.AsyncFunctionDef) -> tuple[bool, bool, bool]:
    """prepare() 영역에 자동 재시도 hook 영속 확인.

    영속 영역 3 의무:
    1. `for retry_attempt in range(3):` 영역
    2. `await asyncio.sleep(30)` 영역
    3. `prepare_retry` 키워드 (사이클 158 VB 패턴 답습)
    """
    src = ast.unparse(prepare_node)
    has_range_3_retry = "range(3)" in src and "retry_attempt" in src
    has_sleep_30 = "asyncio.sleep(30)" in src
    has_retry_prefix = "prepare_retry" in src
    return has_range_3_retry, has_sleep_30, has_retry_prefix


@pytest.mark.parametrize("sid,path", _STRATEGY_FILES.items())
def test_G163_RETRY_hook_present(sid: str, path: str):
    """G-163-LTV-RETRY / G-163-DONCHIAN-RETRY / G-163-BFB-RETRY / G-163-VCP-RETRY:
    4 전략 prepare() 영역 자동 재시도 hook 영속 (사이클 158 VB 패턴 답습).
    """
    repo_root = pathlib.Path(__file__).resolve().parents[4]
    src = (repo_root / path).read_text(encoding="utf-8")
    tree = ast.parse(src)
    prepare_node = _find_prepare_function(tree)
    assert prepare_node is not None, f"{sid}: prepare() 함수 없음"

    has_range, has_sleep, has_prefix = _has_retry_hook(prepare_node)
    assert has_range, f"{sid}: `for retry_attempt in range(3)` 영역 부재"
    assert has_sleep, f"{sid}: `asyncio.sleep(30)` 영역 부재"
    assert has_prefix, f"{sid}: `prepare_retry` prefix 부재"
