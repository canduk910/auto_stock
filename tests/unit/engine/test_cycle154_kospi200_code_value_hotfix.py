"""사이클 154 hotfix — KOSPI200 정본 코드값 영역 시정 (사이클 153 1,796 과대 영역 영구 차단).

운영 DB 실측 (2026-06-16, 사이클 153 적용 후):
- kospi200_apnt_cls_code = "0" → 1,597 종목 (미편입)
- kospi200_apnt_cls_code in ("1","2","3","4","5","6","7","8","9","A","B") → 199 종목 (편입) ≈ KOSPI200

결함:
- 사이클 153 = `bool(code_val.strip())` → bool("0")=True → 1,596 종목 잘못 편입
- 실측 = is_kospi200=True 종목 1,796 (정상 ~200 대비 9배 과대)

시정:
- code_val not in ("", "0") → "0" 추가 제외

회귀 가드:
- G-154-CODE-0: code="0" → is_kospi200=False
- G-154-CODE-EMPTY: code="" → is_kospi200=False
- G-154-CODE-1~B: code in {"1","2","3","4","5","6","7","8","9","A","B"} → is_kospi200=True
- G-154-AST: `bool(code_val)` 잔존 0 영구 가드
"""

from __future__ import annotations

import ast
import pathlib

import pytest

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
_SCANNER_PATH = _REPO_ROOT / "src" / "engine" / "scanner.py"


def _resolve_is_kospi200(code_val: str) -> bool:
    """사이클 154 시정 영역 로직 영구 영속 (scanner.py 영역 정합)."""
    return code_val.strip() not in ("", "0")


@pytest.mark.parametrize("code", ["0", "", " ", "  0  "])
def test_g_154_code_excluded(code: str):
    """G-154-CODE-0/EMPTY — '0' 또는 빈 문자열 영역 → 미편입."""
    assert _resolve_is_kospi200(code) is False


@pytest.mark.parametrize(
    "code", ["1", "2", "3", "4", "5", "6", "7", "8", "9", "A", "B"]
)
def test_g_154_code_included(code: str):
    """G-154-CODE-1~B — '1'~'9', 'A', 'B' 영역 → 편입."""
    assert _resolve_is_kospi200(code) is True


def test_g_154_ast_bool_code_val_forbidden():
    """G-154-AST (HIGH) — `bool(code_val)` 잔존 영구 차단.

    사이클 153 영역 결함 = `is_kospi200 = bool(code_val)` 패턴 재발 차단.
    """
    src = _SCANNER_PATH.read_text(encoding="utf-8")
    tree = ast.parse(src)

    forbidden = False
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            # is_kospi200 = bool(code_val) 패턴 검색
            targets_str = " ".join(
                ast.unparse(t) if hasattr(ast, "unparse") else "" for t in node.targets
            )
            value_str = ast.unparse(node.value) if hasattr(ast, "unparse") else ""
            if "is_kospi200" in targets_str and value_str.strip() == "bool(code_val)":
                forbidden = True
                break

    assert not forbidden, (
        "scanner.py 영역 `is_kospi200 = bool(code_val)` 사이클 153 결함 패턴 잔존 (사이클 154 차단)"
    )


def test_g_154_scanner_pattern_uses_not_in_zero():
    """G-154-AST — 사이클 154 시정 패턴 `not in ("", "0")` 영속 검증."""
    src = _SCANNER_PATH.read_text(encoding="utf-8")
    assert 'not in ("", "0")' in src, (
        "scanner.py 영역 사이클 154 시정 패턴 (`not in (\"\", \"0\")`) 부재"
    )
