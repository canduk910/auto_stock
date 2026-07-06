"""사이클 194 (2026-07-06) — 보조 세션 강제 재연결 label DB 라벨 매칭 회귀 가드.

확정 회귀 버그:
- `stale_session_recovery.py::force_reconnect_session` 의 else 분기(L169-178)가 구식
  `int(label.replace("quote-", "")) - 1` 인덱스 파싱을 사용 → DB 라벨("gold"/"sub")을 받으면
  `int("gold")` ValueError → "알 수 없는 label" WARNING → return False.
- 사이클 43(commit 29abc23, "세션 라벨 통일")이 `_session_label` / `get_session_status` /
  `disable_quote_session` 은 DB 라벨 매칭으로 이주했으나 **이 함수만 누락** = 보조 세션
  silent-inactive 시 덜 파괴적인 1차 복구(강제 재연결)가 절대 발화하지 못함.

Green 구현 (backend-dev):
- else 분기를 `disable_quote_session`(websocket_pool.py:454-458) 패턴 미러링:
  `matched = next((q for q in quotes if getattr(q, "_label", None) == label), None)`.
- cap 검사(L155-163) / `ws_obj is None` 가드(L180) / `_ws.close()`(L193) / state 갱신(L199-200)
  / "main" 분기(L167-168) 전부 불변. `matched is None` → 기존 WARNING + return False 보존.

회귀 가드 4:
- G-194-1: `_label="gold"` 보조 1개 → close 발화 + first_seen pop + recovery_count append + True
- G-194-2: `_quotes=[gold, sub]` 에서 "sub" 요청 → **sub** 세션 close (인덱스 아닌 라벨 매칭)
- G-194-3: 진짜 미존재 라벨 → "알 수 없는 label" WARNING + return False + 어떤 close 도 미호출
- G-194-4: AST — `force_reconnect_session` 본체에 `int(label` / `replace("quote-` 0건 +
  `getattr(..., "_label"` 매칭 존재 (quote-N 인덱스 파싱 재도입 영구 차단, 탐지기 self-test 동반)

Red 유효성 (현재 코드):
- G-194-1/2 FAIL (int("gold")/int("sub") ValueError → False)
- G-194-3 PASS (int("nonexistent") ValueError → 동일 WARNING + False = 매칭 실패 graceful 불변식)
- G-194-4 FAIL (현재 `int(label...)` + `replace("quote-"...)` 잔존)
"""
from __future__ import annotations

import ast
import importlib.util
import logging
import types
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = pytest.mark.unit

KST = timezone(timedelta(hours=9))
NOW = datetime(2026, 7, 6, 15, 0, 0, tzinfo=KST)

SRC_PATH = (
    Path(__file__).resolve().parents[3]
    / "src" / "engine" / "stale_session_recovery.py"
)

# tests/unit/ast/_ast_helpers.py 재사용 (독립 로드 — 다른 프로젝트 모듈 import 0).
_AST_HELPERS_PATH = Path(__file__).resolve().parents[1] / "ast" / "_ast_helpers.py"
_spec = importlib.util.spec_from_file_location(
    "_ast_helpers_cycle194", _AST_HELPERS_PATH
)
_ast_helpers = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_ast_helpers)  # type: ignore[union-attr]
read_module_source = _ast_helpers.read_module_source
find_function_def = _ast_helpers.find_function_def


def _make_quote_session(label: str) -> tuple[MagicMock, AsyncMock]:
    """`_label` + `_ws.close()` AsyncMock 을 갖춘 보조 세션 mock 생성."""
    ws = AsyncMock()
    ws.close = AsyncMock()
    session = MagicMock()
    session._ws = ws
    session._label = label
    return session, ws


def _make_sched(first_seen: dict | None = None) -> types.SimpleNamespace:
    """force_reconnect_session 이 참조하는 2 dict 만 갖춘 mock scheduler.

    실제 dict 필수 — 함수 본체가 `.setdefault(label, [])` / `.pop(label, None)` 호출
    (MagicMock 은 setdefault 가 MagicMock 반환 → 오동작).
    """
    return types.SimpleNamespace(
        _silent_inactive_recovery_count={},
        _silent_inactive_first_seen=dict(first_seen or {}),
    )


# ---------------------------------------------------------------------------
# G-194-1: _label="gold" 보조 1개 → close + first_seen pop + recovery append + True
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_G194_1_gold_session_reconnect():
    """DB 라벨 gold 보조 세션 silent-inactive → 해당 _ws.close() 강제 발화 + state 갱신."""
    from src.engine.stale_session_recovery import force_reconnect_session

    gold_session, gold_ws = _make_quote_session("gold")
    sched = _make_sched({"gold": NOW})

    with patch("src.engine.scheduler.kis_ws_pool") as mock_pool:
        mock_pool._quotes = [gold_session]
        result = await force_reconnect_session(sched, "gold")

    assert result is True, "gold 라벨 매칭 → reconnect 성공"
    gold_ws.close.assert_awaited_once()
    assert "gold" not in sched._silent_inactive_first_seen, "first_seen pop"
    assert len(sched._silent_inactive_recovery_count["gold"]) == 1, "history append"


# ---------------------------------------------------------------------------
# G-194-2: _quotes=[gold, sub] 에서 "sub" 요청 → sub 세션 close (인덱스 아닌 라벨 매칭)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_G194_2_sub_session_label_match_not_index():
    """복수 보조 세션에서 라벨로 정확 매칭 (인덱스 파싱이면 sub 를 찾을 방법 없음)."""
    from src.engine.stale_session_recovery import force_reconnect_session

    gold_session, gold_ws = _make_quote_session("gold")
    sub_session, sub_ws = _make_quote_session("sub")
    sched = _make_sched({"sub": NOW})

    with patch("src.engine.scheduler.kis_ws_pool") as mock_pool:
        mock_pool._quotes = [gold_session, sub_session]
        result = await force_reconnect_session(sched, "sub")

    assert result is True, "sub 라벨 매칭 → reconnect 성공"
    sub_ws.close.assert_awaited_once()
    gold_ws.close.assert_not_awaited(), "라벨 매칭이라 첫 세션(gold) 오발화 0"
    assert "sub" not in sched._silent_inactive_first_seen, "first_seen pop"


# ---------------------------------------------------------------------------
# G-194-3: 진짜 미존재 라벨 → "알 수 없는 label" WARNING + False + close 미호출 (불변식)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_G194_3_nonexistent_label_graceful(caplog):
    """매칭 실패 시 기존 graceful(WARNING + return False) 보존 — Green 후에도 불변."""
    from src.engine.stale_session_recovery import force_reconnect_session

    gold_session, gold_ws = _make_quote_session("gold")
    sched = _make_sched({})

    with patch("src.engine.scheduler.kis_ws_pool") as mock_pool:
        mock_pool._quotes = [gold_session]
        with caplog.at_level(logging.WARNING, logger="src.engine.scheduler"):
            result = await force_reconnect_session(sched, "nonexistent")

    assert result is False, "미존재 라벨 → False"
    gold_ws.close.assert_not_awaited()
    assert any(
        "알 수 없는 label" in r.getMessage() for r in caplog.records
    ), "알 수 없는 label WARNING 발화"


# ---------------------------------------------------------------------------
# G-194-4 (AST): quote-N 인덱스 파싱 재도입 영구 차단 + _label 매칭 존재
# ---------------------------------------------------------------------------
def _has_int_label_parsing(func_node: ast.AST) -> bool:
    """함수 본체에 `int(...)` 호출 노드 존재 여부 (label→정수 인덱스 파싱 탐지)."""
    for sub in ast.walk(func_node):
        if (
            isinstance(sub, ast.Call)
            and isinstance(sub.func, ast.Name)
            and sub.func.id == "int"
        ):
            return True
    return False


def _has_replace_quote_n(func_node: ast.AST) -> bool:
    """함수 본체에 `.replace("quote-", ...)` 호출 노드 존재 여부."""
    for sub in ast.walk(func_node):
        if (
            isinstance(sub, ast.Call)
            and isinstance(sub.func, ast.Attribute)
            and sub.func.attr == "replace"
            and sub.args
            and isinstance(sub.args[0], ast.Constant)
            and isinstance(sub.args[0].value, str)
            and sub.args[0].value.startswith("quote-")
        ):
            return True
    return False


def _has_getattr_label_match(func_node: ast.AST) -> bool:
    """함수 본체에 `getattr(x, "_label", ...)` 호출 노드 존재 여부 (DB 라벨 매칭)."""
    for sub in ast.walk(func_node):
        if (
            isinstance(sub, ast.Call)
            and isinstance(sub.func, ast.Name)
            and sub.func.id == "getattr"
            and len(sub.args) >= 2
            and isinstance(sub.args[1], ast.Constant)
            and sub.args[1].value == "_label"
        ):
            return True
    return False


def test_G194_4_ast_no_quote_n_index_parsing():
    """force_reconnect_session 본체: int(label)/replace("quote-") 0건 + _label 매칭 존재."""
    # 탐지기 self-test — known-bad / known-good 스니펫으로 오탐/미탐 검증
    _bad_src = (
        "def f(label):\n"
        "    idx = int(label.replace('quote-', '')) - 1\n"
        "    return idx\n"
    )
    _bad_node = find_function_def(_bad_src, "f")
    assert _has_int_label_parsing(_bad_node) is True, "self-test: int() 탐지"
    assert _has_replace_quote_n(_bad_node) is True, "self-test: replace('quote-') 탐지"
    assert _has_getattr_label_match(_bad_node) is False, "self-test: getattr(_label) 오탐 0"

    _good_src = (
        "def g(label):\n"
        "    m = next((q for q in quotes if getattr(q, '_label', None) == label), None)\n"
        "    return m\n"
    )
    _good_node = find_function_def(_good_src, "g")
    assert _has_int_label_parsing(_good_node) is False, "self-test: int() 미탐 0"
    assert _has_replace_quote_n(_good_node) is False, "self-test: replace 미탐 0"
    assert _has_getattr_label_match(_good_node) is True, "self-test: getattr(_label) 탐지"

    # 실제 production 함수 검증
    source = read_module_source(SRC_PATH)
    func_node = find_function_def(source, "force_reconnect_session")
    assert func_node is not None, "force_reconnect_session 정의 부재"
    assert not _has_int_label_parsing(func_node), (
        "int(label...) 인덱스 파싱 잔존 — quote-N 파서 재도입 영구 차단"
    )
    assert not _has_replace_quote_n(func_node), (
        'replace("quote-"...) 잔존 — quote-N 파서 재도입 영구 차단'
    )
    assert _has_getattr_label_match(func_node), (
        'getattr(..., "_label") DB 라벨 매칭 부재 — disable_quote_session 패턴 미러링 의무'
    )
