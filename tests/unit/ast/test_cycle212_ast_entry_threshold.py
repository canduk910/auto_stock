"""사이클 212 Red (AST) — buy_threshold/donchian_period PARAM_RANGES·INT_PARAMS 리터럴 부재.

> 선례: 사이클 208/209 (PARAM_RANGES 제외 AST 가드 — dict/set 리터럴 키 노드 검사).

G-212-4: recommendation_engine.py 소스의 PARAM_RANGES dict 리터럴 + INT_PARAMS set
  리터럴에 'buy_threshold' / 'donchian_period' 문자열 키 부재.
  소스 텍스트 substring 이 아닌 AST 할당 노드의 리터럴 키만 검사 →
  docstring/주석/다른 dict 언급 false-positive 차단 (사이클 209/167 패턴 답습).

Red 유효성 (production 미변경):
  - PARAM_RANGES 리터럴에 'buy_threshold'/'donchian_period' 잔존 → FAIL
  - INT_PARAMS 리터럴에 'donchian_period' 잔존 → FAIL
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

_FORBIDDEN = ("buy_threshold", "donchian_period")


def _collect_named_literal_str_keys(src: str, name: str) -> list[str]:
    """`name = {...}` (Assign/AnnAssign) 할당의 dict/set 리터럴 str 키 목록.

    dict 는 keys, set 은 elts 를 str Constant 로 수집.
    """
    tree = ast.parse(src)
    keys: list[str] = []
    for node in ast.walk(tree):
        value = None
        if isinstance(node, ast.Assign):
            if any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
                value = node.value
        elif isinstance(node, ast.AnnAssign):
            if isinstance(node.target, ast.Name) and node.target.id == name:
                value = node.value
        if isinstance(value, ast.Dict):
            for k in value.keys:
                if isinstance(k, ast.Constant) and isinstance(k.value, str):
                    keys.append(k.value)
        elif isinstance(value, ast.Set):
            for e in value.elts:
                if isinstance(e, ast.Constant) and isinstance(e.value, str):
                    keys.append(e.value)
    return keys


def test_g212_4_param_ranges_literal_absent():
    """PARAM_RANGES dict 리터럴에 buy_threshold/donchian_period 키 부재 (AST)."""
    src = _RECO.read_text(encoding="utf-8")
    keys = _collect_named_literal_str_keys(src, "PARAM_RANGES")
    assert keys, "PARAM_RANGES dict 리터럴 파싱 실패"
    for forbidden in _FORBIDDEN:
        assert forbidden not in keys, (
            f"PARAM_RANGES dict 리터럴에 '{forbidden}' 키 잔존 금지 (사이클 212 제거)"
        )


def test_g212_4_int_params_literal_absent_donchian_period():
    """INT_PARAMS set 리터럴에 donchian_period 키 부재 (AST)."""
    src = _RECO.read_text(encoding="utf-8")
    keys = _collect_named_literal_str_keys(src, "INT_PARAMS")
    assert keys, "INT_PARAMS set 리터럴 파싱 실패"
    assert "donchian_period" not in keys, (
        "INT_PARAMS set 리터럴에 'donchian_period' 잔존 금지 (사이클 212 제거)"
    )


def test_g212_4_detector_self_test():
    """탐지기 self-test — 존재하는 키는 정상 검출.

    의미 전환 (2026-08-03 예산 이중제한): INT_PARAMS 의 self-test 앵커가
    `max_positions` 였으나 해당 키가 PARAM_RANGES/INT_PARAMS 에서 제거됐다
    (동시보유 슬롯 수 = 리스크 정체성 상수, position_ratio 와의 곱 교차검증 부재로
    예산 200% 조합 사고 발생). 앵커를 잔존 키 `k_period` 로 교체 — 탐지기 검증
    의도는 동일하게 보존된다.
    """
    src = _RECO.read_text(encoding="utf-8")
    pr = _collect_named_literal_str_keys(src, "PARAM_RANGES")
    ip = _collect_named_literal_str_keys(src, "INT_PARAMS")
    assert "stop_loss_rate" in pr, "탐지기 결함 — 존재 키 미검출 (PARAM_RANGES)"
    assert "k_period" in ip, "탐지기 결함 — 존재 키 미검출 (INT_PARAMS)"
