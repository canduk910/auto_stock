"""cycle270 — revoke→issue 호출 구조 · 심볼 격리 AST 가드 (C6/C8).

| 가드 | 내용 | 수명 |
|------|------|------|
| G-270-1 | leaf 가 `refresh_quote_tokens_once` 안에서 `await .revoke()` → `await .issue()` 순서로 부른다 | 영구 |
| G-270-2 | leaf 가 `src.auth.token` **내부 심볼**을 import·참조하지 않는다 | 영구 |
| G-270-3 | `TokenManager.revoke` 소스 세그먼트 sha 핀 (cycle270 계약이 이 의미론에 기댄다) | 영구 |
| G-270-4 | leaf 가 61초 직렬화를 **우회하지 않는다** (자체 sleep·전역 시각 조작 0) | 영구 |

cycle269 의 `test_g269_6_token_is_valid_pinned`(`_is_valid` 핀 = token.py 무접촉)는
그대로 유효하다 — cycle270 도 `token.py` 를 한 글자도 고치지 않는다.

⚠️ 핀은 `ast.dump` 가 아니라 `ast.get_source_segment` 의 sha256 이다
(3.12(CI)/3.13(로컬) `ast.dump` 출력 차이로 CI 만 붉어진 cycle256/259 실측).
"""
from __future__ import annotations

import ast
import hashlib
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parents[3]
_SRC = _ROOT / "src"
_LEAF = _SRC / "engine" / "quote_token_refresh.py"
_TOKEN = _SRC / "auth" / "token.py"
_ONCE_FN = "refresh_quote_tokens_once"


def _leaf_tree() -> ast.Module:
    return ast.parse(_LEAF.read_text(encoding="utf-8"))


def _once_fn(tree: ast.Module) -> ast.AsyncFunctionDef:
    return next(
        n
        for n in ast.walk(tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == _ONCE_FN
    )


# ===========================================================================
# G-270-1 — 호출 순서 계약
# ===========================================================================

def test_g270_1_revoke_is_awaited_before_issue():
    """폐기가 발급보다 **앞서야** 앵커가 옮겨진다.

    KIS `/oauth2/tokenP` 는 유효 토큰이 있으면 같은 토큰·같은 만료를 돌려준다
    (09-10 실측: 15:45 강제 발급 7/7 의 expired 가 14:2x~14:5x 자연 재발급과 동일).
    순서가 뒤집히면 방금 발급한 토큰을 폐기해 **토큰만 사라지고** 앵커는 그대로다.
    """
    fn = _once_fn(_leaf_tree())

    awaited: list[tuple[int, str]] = []
    for node in ast.walk(fn):
        if (
            isinstance(node, ast.Await)
            and isinstance(node.value, ast.Call)
            and isinstance(node.value.func, ast.Attribute)
            and node.value.func.attr in ("revoke", "issue")
        ):
            awaited.append((node.lineno, node.value.func.attr))

    names = [a for _, a in sorted(awaited)]
    assert "revoke" in names, (
        f"`{_ONCE_FN}` 안에 `await ....revoke()` 가 없다 — `issue()` 단독은 앵커를 "
        "못 옮긴다(cycle269 가 이미 반증됐다)"
    )
    assert "issue" in names, f"`{_ONCE_FN}` 안에 `await ....issue()` 가 없다"
    assert names.index("revoke") < names.index("issue"), (
        f"revoke 가 issue 보다 뒤에 있다 — 실측 순서 {names}"
    )


# ===========================================================================
# G-270-2 — token.py 내부 심볼 격리
# ===========================================================================

_FORBIDDEN_TOKEN_SYMBOLS = (
    "_is_valid",
    "_GLOBAL_ISSUE_LOCK",
    "_LAST_ISSUE_AT",
    "_ISSUE_GAP_SECS",
    "reset_global_issue_state",
    "_get_global_issue_lock",
    "_TOKEN_CACHE_DIR",
    "_TOKEN_CACHE_PATH",
    "_QUOTE_TOKEN_CACHE_PREFIX",
    "_safe_cache_filename",
    "_save_cache",
    "_load_cache",
    "_delete_cache",
)


def test_g270_2_leaf_touches_only_public_manager_api():
    """leaf 는 `get_token_manager` 하나만 빌린다.

    캐시 파일 경로·전역 lock·만료 마진 같은 **내부 구현**에 손대는 순간 이 사이클은
    '스케줄로 앵커를 잡는다' 가 아니라 'token.py 를 우회한다' 가 되고, token.py
    무접촉 계약(g269_6)이 무의미해진다.

    식별자는 AST 에서만 센다(주석·docstring 은 설명문이라 제외).
    """
    tree = _leaf_tree()

    imported_from_token: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and (node.module or "").startswith(
            "src.auth.token"
        ):
            imported_from_token += [a.name for a in node.names]
        elif isinstance(node, ast.Import):
            for a in node.names:
                assert a.name != "src.auth.token", (
                    "모듈 통째 import 금지 — 내부 심볼 접근 경로가 열린다"
                )

    assert imported_from_token == ["get_token_manager"], (
        f"`src.auth.token` 에서 가져오는 이름은 `get_token_manager` 뿐이어야 한다 — "
        f"실측 {imported_from_token}"
    )

    identifiers = {
        node.id for node in ast.walk(tree) if isinstance(node, ast.Name)
    } | {
        node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
    }
    leaked = sorted(identifiers & set(_FORBIDDEN_TOKEN_SYMBOLS))
    assert not leaked, f"token.py 내부 심볼 참조: {leaked}"


# ===========================================================================
# G-270-3 — revoke 의미론 핀
# ===========================================================================

# `ast.get_source_segment(TokenManager.revoke)` 의 sha256 (2026-09-10 HEAD).
_REVOKE_SHA = "0d454ce0587a25bd7976ce4776576decee56cc5bf7518fbf77ae2315e62d968a"


def test_g270_3_token_revoke_pinned():
    """cycle270 은 `revoke()` 의 **현재 의미론**에 기댄다.

    구체적으로 (a) 토큰이 없으면 조용히 return (b) 성공 시 `access_token=""` +
    `token_expired=None` + 캐시 파일 삭제. 이 중 하나라도 바뀌면 "폐기 후 발급이
    새 앵커를 만든다" 는 전제가 흔들리므로 이 핀이 재검토를 강제한다.
    이 사이클도 `token.py` 는 **한 글자도 고치지 않는다**.
    """
    src = _TOKEN.read_text(encoding="utf-8")
    tree = ast.parse(src)
    cls = next(
        n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "TokenManager"
    )
    fn = next(
        n
        for n in cls.body
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == "revoke"
    )
    actual = hashlib.sha256(
        (ast.get_source_segment(src, fn) or "").encode("utf-8")
    ).hexdigest()
    assert actual == _REVOKE_SHA, (
        f"`TokenManager.revoke` 가 바뀌었다 — cycle270 의 앵커 이동 전제를 다시 "
        f"검증하고 핀을 갱신하라. 실측 sha={actual}"
    )


# ===========================================================================
# G-270-4 — 61초 직렬화 무우회
# ===========================================================================

def test_g270_4_leaf_does_not_bypass_issue_serialization():
    """분당 1개 한도 직렬화는 `issue()` 내부 전역 lock 하나가 유일한 지점이다.

    leaf 가 스스로 sleep 을 넣거나 `_LAST_ISSUE_AT` 를 만지면 그 계약이 두 곳으로
    갈라진다(그리고 KIS 한도 위반은 앱키 정지로 이어진다). 7계정 × 61s ≈ 7분은
    **정상**이며 줄여야 할 값이 아니다.
    """
    tree = _leaf_tree()

    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.append(node.module)
    assert not any(name.split(".")[0] == "asyncio" for name in imported), (
        f"leaf 에 asyncio import 금지 (자체 sleep·gap 조작 경로) — 실측 {imported}"
    )

    called = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    } | {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "sleep" not in called, "leaf 가 직접 sleep 하면 직렬화 계약이 이원화된다"
