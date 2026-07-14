"""사이클 210 Red (AST) — _CONSERVATIVE_KEYS 정의에 ratchet 키 문자열 부재.

> Red memo: `_workspace/red/cycle210_auto_apply_ratchet_block.md`
> 선례: 사이클 209/208 (PARAM_RANGES dict 리터럴 AST 키 검사 패턴 답습)

G-210-4: recommendation_engine.py `_CONSERVATIVE_KEYS` 할당의 set/frozenset 리터럴
  키 목록에 손절/일일한도/비중 문자열 부재 (소스 텍스트 substring 이 아닌 AST 노드
  검사 — 주석/docstring/`_STOP_LOSS_KEYS` 언급 false-positive 차단).

Red 유효성 (production 미변경 = `_CONSERVATIVE_KEYS` 에 7키 잔존):
  - G-210-4 (키 부재 단언) = FAIL (현재 L952-960 에 7키 잔존)
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_RECO = (
    Path(__file__).resolve().parents[3]
    / "src" / "engine" / "recommendation_engine.py"
)

_RATCHET_KEYS = frozenset({
    "stop_loss_rate",
    "daily_loss_limit",
    "intraday_stop_loss",
    "overnight_stop_loss",
    "stop_loss_main",
    "stop_loss_pre_nxt",
    "position_ratio",
})


def _extract_conservative_keys_literal() -> list[str]:
    """`_CONSERVATIVE_KEYS = frozenset({...})` 리터럴의 문자열 키를 AST 로 추출.

    frozenset(set_literal) / plain set literal 양쪽 포괄. plain Assign 과
    AnnAssign(타입 어노테이션 동반) 양쪽 포괄.
    """
    src = _RECO.read_text(encoding="utf-8")
    tree = ast.parse(src)
    keys: list[str] = []
    found_def = False

    def _collect_from(value: ast.AST) -> None:
        nonlocal keys
        target: ast.AST | None = None
        # frozenset({...}) 호출 형태
        if isinstance(value, ast.Call) and isinstance(value.func, ast.Name) \
                and value.func.id == "frozenset":
            if value.args:
                target = value.args[0]
        else:
            target = value
        # set 리터럴 {...} 의 elts
        if isinstance(target, ast.Set):
            for elt in target.elts:
                if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                    keys.append(elt.value)

    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            if any(isinstance(t, ast.Name) and t.id == "_CONSERVATIVE_KEYS"
                   for t in node.targets):
                found_def = True
                _collect_from(node.value)
        elif isinstance(node, ast.AnnAssign):
            if isinstance(node.target, ast.Name) \
                    and node.target.id == "_CONSERVATIVE_KEYS":
                found_def = True
                if node.value is not None:
                    _collect_from(node.value)

    assert found_def, "_CONSERVATIVE_KEYS 정의를 찾지 못함"
    return keys


def test_g210_4_conservative_keys_literal_no_ratchet_keys():
    """_CONSERVATIVE_KEYS set/frozenset 리터럴에 ratchet 키 문자열 부재.

    Red: 현재 리터럴에 7키 잔존 → FAIL.
    """
    keys = _extract_conservative_keys_literal()
    leaked = _RATCHET_KEYS & set(keys)
    assert not leaked, (
        f"_CONSERVATIVE_KEYS 리터럴에 ratchet 키 잔존 금지 (사이클 210): "
        f"{sorted(leaked)}"
    )
