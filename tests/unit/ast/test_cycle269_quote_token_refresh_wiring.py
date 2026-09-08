"""cycle269 — 배선·범위 AST 가드 (leaf 위임 + 무접촉 실증).

| 가드 | 내용 | 수명 |
|------|------|------|
| G-269-1 | `scheduler.py` < 3,900L (cycle257 영구 상한 리터럴과 **자동 대조**) | 영구 |
| G-269-2 | `_quote_token_refresh_task` 가 생성 1 + cancel 3 = 4곳 전부에 등재 | 영구 |
| G-269-3 | leaf 는 `scheduler` 를 import 하지 않는다 (순환 차단) | 영구 |
| G-269-4 | leaf 는 `issue()` 를 부르고 `get_token()` 을 부르지 않는다 | 영구 |
| G-269-5 | leaf 는 주계정 싱글톤(`token_manager`)을 참조하지 않는다 | 영구 |
| G-269-6 | `TokenManager._is_valid` 소스 세그먼트 sha 핀 (token.py 무접촉 계약) | 영구 |
| G-269-7 | cycle269 마커가 8영역·전략 7파일로 새지 않는다 | 영구 |
"""
from __future__ import annotations

import ast
import hashlib
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parents[3]
_SRC = _ROOT / "src"
_SCHEDULER = _SRC / "engine" / "scheduler.py"
_LEAF = _SRC / "engine" / "quote_token_refresh.py"
_TASK_ATTR = "_quote_token_refresh_task"
_MARKER = "[quote_token_refresh]"


# ===========================================================================
# G-269-1 — scheduler 라인 상한 (cycle257 리터럴과 자동 대조)
# ===========================================================================

def test_g269_1_scheduler_line_cap_matches_cycle257():
    """cycle264 가 얻은 교훈 — 사이클 자체 가드가 느슨하면(4,000) cycle257 의 진짜
    상한(3,900) 위반을 초록으로 덮는다. 그래서 리터럴을 **읽어와** 대조한다."""
    cycle257 = (
        _ROOT / "tests" / "unit" / "ast" / "test_cycle257_ast_dead_code_removed.py"
    ).read_text(encoding="utf-8")
    caps = {int(m) for m in re.findall(r"count\s*<\s*(\d{4})", cycle257)}
    assert 3900 in caps, f"cycle257 상한 리터럴이 바뀌었다 — 실측 {sorted(caps)}"

    lines = len(_SCHEDULER.read_text(encoding="utf-8").splitlines())
    assert lines < 3900, (
        f"scheduler.py {lines}L — 상한 3,900L 초과. cycle269 의 실제 로직은 leaf "
        f"(`src/engine/quote_token_refresh.py`) 에 있고 scheduler 에는 배선 2줄만 든다."
    )


# ===========================================================================
# G-269-2 — 좀비 task 차단 (cycle264 MEDIUM 재발 방지)
# ===========================================================================

def test_g269_2_task_registered_in_create_and_all_cancel_sites():
    """생성 1곳 + cancel 목록 3곳. 하나라도 빠지면 stop() 후 task 가 살아남는다."""
    src = _SCHEDULER.read_text(encoding="utf-8")

    assert src.count(f"self.{_TASK_ATTR} = asyncio.create_task(") == 1
    assert f"quote_token_refresh.task_loop(self)" in src

    tree = ast.parse(src)
    literal_sites = sum(
        1
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and node.value == _TASK_ATTR
    )
    assert literal_sites == 3, (
        f"cancel 목록 등재가 3곳이어야 한다 — 실측 {literal_sites}곳. "
        "`start()` finally · `run_daily()` · `stop()` 세 목록 전부에 이름이 있어야 "
        "stop→start 재시작에서 좀비 task 가 남지 않는다."
    )


# ===========================================================================
# G-269-3/4/5 — leaf 계약
# ===========================================================================

def test_g269_3_leaf_does_not_import_scheduler():
    tree = ast.parse(_LEAF.read_text(encoding="utf-8"))
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.append(node.module)
    assert not any("scheduler" in name for name in imported), imported


def test_g269_4_leaf_calls_issue_not_get_token():
    """`get_token()` 은 유효 토큰이면 재발급하지 않는다 — 앵커를 못 옮긴다.

    이 사이클의 존재 이유가 '만료 앵커를 고정 장외 시각으로 옮기는 것' 이므로
    호출을 `get_token()` 으로 바꾸는 뮤테이션은 기능 전체를 무력화한다.
    """
    tree = ast.parse(_LEAF.read_text(encoding="utf-8"))
    attr_calls = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    assert "issue" in attr_calls
    assert "get_token" not in attr_calls, (
        "`get_token()` 은 캐시 hit 면 no-op 이라 재발급 시각을 고정하지 못한다"
    )


def test_g269_5_leaf_never_touches_main_trading_manager():
    """주계정(매매용) 무접촉 — `token_manager` 싱글톤을 이름으로도 참조하지 않는다."""
    src = _LEAF.read_text(encoding="utf-8")
    code = "\n".join(
        line for line in src.splitlines() if not line.lstrip().startswith("#")
    )
    body = code.split('"""', 2)[-1]  # 모듈 docstring 제외 (설명문에는 나올 수 있다)
    assert "token_manager" not in body.replace("get_token_manager", ""), (
        "주계정 싱글톤 `token_manager` 참조 금지 (보조 계정 전용 사이클)"
    )


# ===========================================================================
# G-269-6 — token.py 무접촉 계약 (선제 갱신 마진 sha 핀)
# ===========================================================================

# `ast.get_source_segment(TokenManager._is_valid)` 의 sha256 (2026-09-08 HEAD).
# ⚠️ `ast.dump` 금지 — 3.12(CI)/3.13(로컬) 출력 차이로 CI 만 붉어진다(cycle256/259 실측).
_IS_VALID_SHA = "d58f356b02c8de7ee75ef1404f836a2770a849fe13a73c44ed8cbb083a581d15"


def test_g269_6_token_is_valid_pinned():
    """cycle269 는 `token.py` 를 한 글자도 고치지 않는다.

    드리프트의 수학적 원인은 `_is_valid()` 의 10분 선제 갱신 마진이지만, 이 사이클은
    그 마진을 **건드리지 않고** 스케줄로 앵커를 잡는 방식을 택했다(마진을 줄이면 만료
    직전 경합에서 매매용 REST 호출이 401 을 맞을 수 있다). 마진을 바꾸는 후속 사이클은
    행위 영향 평가 후 이 핀을 갱신한다.
    """
    src = (_SRC / "auth" / "token.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    cls = next(
        n for n in tree.body
        if isinstance(n, ast.ClassDef) and n.name == "TokenManager"
    )
    fn = next(
        n for n in cls.body
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        and n.name == "_is_valid"
    )
    actual = hashlib.sha256(
        (ast.get_source_segment(src, fn) or "").encode("utf-8")
    ).hexdigest()
    assert actual == _IS_VALID_SHA, (
        f"`TokenManager._is_valid` 가 바뀌었다 — cycle269 계약은 token.py 무접촉이다. "
        f"실측 sha={actual}"
    )


# ===========================================================================
# G-269-7 — 마커 누출 차단 (8영역 · 전략 7파일)
# ===========================================================================

_FORBIDDEN = (
    [_SRC / "engine" / f"{n}.py" for n in
     ("risk", "order_engine", "session", "scanner", "strategy_registry")]
    + [_SRC / "api" / "order.py"]
    + sorted((_SRC / "realtime").rglob("*.py"))
    + sorted((_SRC / "auth").rglob("*.py"))
    + sorted((_SRC / "engine" / "strategies").glob("*.py"))
)


@pytest.mark.parametrize("path", _FORBIDDEN, ids=lambda p: p.name)
def test_g269_7_marker_absent_from_trading_path(path: Path):
    """관측 마커도 매매 경로 파일에는 새지 않는다 (접촉 범위 실증)."""
    assert _MARKER not in path.read_text(encoding="utf-8"), path
