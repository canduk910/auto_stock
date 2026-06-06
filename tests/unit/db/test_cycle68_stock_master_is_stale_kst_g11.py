"""사이클 68 G-11 — `stock_master.is_stale()` 내부 비교 KST 통일 (Q3).

> **Q3 채택**: `is_stale()` 내부도 UTC 비교 → KST 비교 통일.
>   현재 동작 자체는 정확 (UTC vs UTC) 하나 KST 정책 일관성 위반.
>   사이클 68 시정 후 baseline 도 KST → 비교도 KST 로 통일.
>
> Red 시점: `is_stale` 함수 본문에 `datetime.now(timezone.utc)` 존재 (line 121).
> Green 후: `datetime.now(KST)` 또는 `now_kst_iso` 기반 KST 비교로 교체.

검증 방식: AST 정적 파싱 — `is_stale` 함수 본문 내 `datetime.now(...)` 호출의
인자가 `timezone.utc` 가 아닌 KST 표현이어야 함.

> **회귀 위험**: refreshed_at 이 KST 로 저장되는 시점부터 (G-2 시정 후) 비교 baseline
>   도 KST 로 통일하지 않으면 9h 오차 발생 가능 — 단 fromisoformat 으로 파싱된
>   tz-aware datetime 끼리 비교는 timezone 무관 정확. 본 가드는 *정책 일관성* 목적.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit


_KST_NOW_PATTERNS = [
    re.compile(r"datetime\.now\(\s*KST\s*\)"),
    re.compile(r"datetime\.now\(\s*_KST(_TZ)?\s*\)"),
    re.compile(r"datetime\.now\(\s*timezone\(\s*timedelta\(\s*hours\s*=\s*9\s*\)\s*\)\s*\)"),
    re.compile(r"now_kst_iso\s*\("),
]


def test_g11_is_stale_uses_kst_comparison():
    """G-11 — `stock_master.is_stale()` 내부 비교가 KST baseline 사용 의무.

    현재 (Red): `datetime.now(timezone.utc) - refreshed_at` (line 121).
    Green: `datetime.now(KST) - refreshed_at` 또는 동등 표현.
    """
    src_path = Path("src/db/stock_master.py")
    assert src_path.exists(), f"stock_master.py 경로 결함: {src_path.resolve()}"

    source = src_path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    is_stale_fn: ast.AsyncFunctionDef | ast.FunctionDef | None = None
    for node in ast.walk(tree):
        if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)) and node.name == "is_stale":
            is_stale_fn = node
            break

    assert is_stale_fn is not None, "is_stale 함수 미존재"

    body_src = ast.unparse(is_stale_fn)

    # `datetime.now(timezone.utc)` 잔존 검증 → FAIL
    utc_now_pattern = re.compile(r"datetime\.now\(\s*timezone\.utc\s*\)")
    utc_matches = utc_now_pattern.findall(body_src)

    # KST 표현 존재 확인
    has_kst_now = any(pat.search(body_src) for pat in _KST_NOW_PATTERNS)

    assert not utc_matches, (
        f"`is_stale` 본문에 `datetime.now(timezone.utc)` 잔존 — "
        f"사이클 68 Q3 시정 의무 (정책 일관성 통일).\n"
        f"잔존 {len(utc_matches)}건. 본문 발췌:\n{body_src}"
    )
    assert has_kst_now, (
        f"`is_stale` 본문에 KST 비교 baseline 누락 — "
        f"`datetime.now(KST)` 또는 동등 표현 의무.\n본문:\n{body_src}"
    )
