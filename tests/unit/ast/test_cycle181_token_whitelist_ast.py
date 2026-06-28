"""사이클 181 — 정적 가드: 토큰만료 화이트리스트 frozenset + "만료" substring 폐기.

설계 (Green 목표):
- `src/api/base.py` 모듈-레벨 `_TOKEN_EXPIRED_MSG_CODES = frozenset({"EGW00121","EGW00122","EGW00123"})`
  (access token 3종만 — `token_manager.issue()` access token 재발급이 *올바른 복구* 인 코드).
- session_key 3종 (EGW00124/00125/00126) **미포함** (issue() 로 해소 불가 = footgun, 자문 정정 1).
- 예수금부족 변형 EGW00120 **미포함**.
- 토큰 분기 `"만료" in msg1` 절 영구 폐기.

가드 방식 (사이클 167/179 dead-code 패턴 답습):
- frozenset 엔트리 검사 = **실 객체 멤버십** (source 텍스트 전수 스캔 아님 — 주석/문서 false-positive 차단).
- `"만료"` 잔존 검사 = **AST Compare 노드** (`Compare(left=Const("만료"), op=In)`) — 주석의
  "윈도우 만료" / "토큰 만료 감지" 등 텍스트 false-positive 를 구조적으로 배제.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_BASE_PY = Path(__file__).resolve().parents[3] / "src" / "api" / "base.py"


# ===========================================================================
# G-181-AST-1: 화이트리스트 frozenset 존재 + access token 3종 포함
# ===========================================================================
def test_g181_ast1_token_expired_msg_codes_includes_access_token_three():
    """`_TOKEN_EXPIRED_MSG_CODES` 에 EGW00121/00122/00123 포함 (frozenset 엔트리 검사).

    현재 코드: 심볼 부재 → ImportError → FAIL (Red).
    """
    from src.api.base import _TOKEN_EXPIRED_MSG_CODES

    for code in ("EGW00121", "EGW00122", "EGW00123"):
        assert code in _TOKEN_EXPIRED_MSG_CODES, (
            f"access token 만료 코드 {code} 가 _TOKEN_EXPIRED_MSG_CODES 에 누락"
        )


# ===========================================================================
# G-181-AST-2: 예수금부족(EGW00120) + session_key(EGW00124~126) 미포함
# ===========================================================================
def test_g181_ast2_token_expired_msg_codes_excludes_non_token_codes():
    """`_TOKEN_EXPIRED_MSG_CODES` 에 EGW00120 + EGW00124/00125/00126 미포함.

    EGW00120 = 예수금부족 변형 (오발화 뿌리). EGW00124~126 = session_key (issue() 무관, footgun).
    현재 코드: 심볼 부재 → ImportError → FAIL (Red).
    """
    from src.api.base import _TOKEN_EXPIRED_MSG_CODES

    for code in ("EGW00120", "EGW00124", "EGW00125", "EGW00126"):
        assert code not in _TOKEN_EXPIRED_MSG_CODES, (
            f"{code} 는 토큰만료 화이트리스트에 포함되면 안 됨 "
            f"(EGW00120=예수금부족 오발화 / EGW0012[456]=session_key footgun)"
        )


# ===========================================================================
# G-181-AST-3: 토큰 분기 `"만료" in msg1` substring 폐기 (AST Compare 노드 0건)
# ===========================================================================
def test_g181_ast3_no_manryo_substring_compare_in_base():
    """base.py AST 에 `Compare(left=Const("만료"), op=In)` 0건.

    현재 코드: L560 + L866 의 `"만료" in msg1` 2건 잔존 → FAIL (Red).
    주석/문서의 "만료" 텍스트는 AST Compare 노드가 아니므로 false-positive 0.
    """
    tree = ast.parse(_BASE_PY.read_text(encoding="utf-8"))

    offending: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Compare):
            continue
        if not any(isinstance(op, ast.In) for op in node.ops):
            continue
        left = node.left
        if isinstance(left, ast.Constant) and left.value == "만료":
            offending.append(getattr(node, "lineno", -1))

    assert offending == [], (
        f"토큰 분기 `\"만료\" in msg1` substring 잔존 (lineno={offending}) — "
        f"화이트리스트 전환으로 영구 폐기 의무 (오발화 뿌리)"
    )
