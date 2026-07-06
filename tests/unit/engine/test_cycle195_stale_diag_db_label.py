"""사이클 195 (2026-07-06) — stale_diagnostics quote-N 잔존 시정 회귀 가드.

확정 회귀 버그 (`stale_diagnostics.py::build_session_subscription_view`,
`[stale_watcher_detail]` capacity 로그 빌더, 관찰성 전용):
- L87-89 phantom `quote-N` label_order 생성: `get_subscriptions_by_session()` 는
  사이클 43에서 DB 라벨(gold/sub)을 반환하는데 phantom `quote-N` 은 groups 에 매칭 안 됨 →
  전부 skip 되던 noise.
- L108-114 capacity 해석 quote-N 파싱: DB 라벨(gold/sub)은 `startswith("quote-")` False →
  `ws_obj=None` → `cap_used = len(tickers)` 폴백 degrade. 세션 실측 `_subscriptions` TICK
  카운트와 groups ticker 수가 diverge 하면 capacity_used 부정확.

Green 구현 (backend-dev):
- L87-89: phantom 제거 → `label_order = ["main"]` (groups 키는 기존 로직이 append).
- L108-114: quote-N 파싱 → `disable_quote_session`(websocket_pool.py:454-458) 패턴 미러 =
  `next((q for q in _quotes if getattr(q, "_label", None) == label), None)`.
  `ws_obj is None` (미매칭) → `cap_used = len(tickers)` 폴백 보존 (graceful).
- fresh/stale 분리·ratio·stale_tickers·`_main` 분기 전부 불변.

회귀 가드 4:
- G-195-1 (핵심 divergence): 보조 `_label="gold"`, 세션 TICK 2개인데 groups gold 3개 →
  capacity_used == 2 (세션 실측). 현재 코드 미매칭 → len=3 폴백 → Red FAIL, Green 2.
- G-195-2: `_quotes=[gold, sub]` 에서 "sub" 요청 → sub 세션 TICK 카운트로 cap (인덱스 아닌
  라벨 매칭). divergence 로 Red 구분.
- G-195-3: 미매칭 라벨 → `cap_used = len(tickers)` graceful 폴백 (불변식, Green 후에도 PASS).
- G-195-4 (AST): 함수 본체에 `startswith("quote-")` / f-string `quote-{` / `.split` 0건 +
  `getattr(..., "_label")` 매칭 존재 (quote-N 재도입 영구 차단, 탐지기 self-test 동반).

Red 유효성 (현재 코드):
- G-195-1/2/4 FAIL / G-195-3 PASS (불변식) / self-test PASS.
"""
from __future__ import annotations

import ast
import importlib.util
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

pytestmark = pytest.mark.unit

KST = timezone(timedelta(hours=9))

SRC_PATH = (
    Path(__file__).resolve().parents[3]
    / "src" / "engine" / "stale_diagnostics.py"
)

# tests/unit/ast/_ast_helpers.py 재사용 (독립 로드 — 다른 프로젝트 모듈 import 0, 사이클 194 답습).
_AST_HELPERS_PATH = Path(__file__).resolve().parents[1] / "ast" / "_ast_helpers.py"
_spec = importlib.util.spec_from_file_location(
    "_ast_helpers_cycle195", _AST_HELPERS_PATH
)
_ast_helpers = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_ast_helpers)  # type: ignore[union-attr]
read_module_source = _ast_helpers.read_module_source
find_function_def = _ast_helpers.find_function_def

# TICK TR_ID (stale_diagnostics 내부 _TICK_TR_IDS 정합) — H0UNMKO0 은 非TICK(장운영정보).
_H0STCNT0 = "H0STCNT0"
_H0NXCNT0 = "H0NXCNT0"
_H0UNCNT0 = "H0UNCNT0"
_H0UNMKO0 = "H0UNMKO0"  # 非TICK


# ---------------------------------------------------------------------------
# mock 헬퍼
# ---------------------------------------------------------------------------
def _make_session(label: str, subscriptions: set) -> MagicMock:
    """`_label` + `_subscriptions`(set[(tr_id, ticker)]) 를 갖춘 세션 mock."""
    sess = MagicMock(name=f"session-{label}")
    sess._label = label
    sess._subscriptions = set(subscriptions)
    return sess


def _setup_pool(monkeypatch, *, groups, main_subs, quote_sessions):
    """kis_ws_pool mock 을 websocket_pool 모듈에 주입.

    build_session_subscription_view 가 `from src.realtime.websocket_pool import
    kis_ws_pool` 로 직접 import 하므로 그 import 지점(모듈 속성)을 patch.
    """
    pool = MagicMock(name="pool")
    pool.get_subscriptions_by_session = MagicMock(return_value=dict(groups))
    pool._main = _make_session("main", main_subs)
    pool._quotes = list(quote_sessions)
    import src.realtime.websocket_pool as wp_mod
    monkeypatch.setattr(wp_mod, "kis_ws_pool", pool)
    return pool


def _all_fresh(monkeypatch, tickers):
    """모든 ticker fresh(now-5s) — capacity_used 는 시각 무관하나 stale 분기 회피용."""
    import src.engine.scanner as scanner_mod
    now = datetime.now(KST)
    monkeypatch.setattr(
        scanner_mod,
        "ticker_last_tick",
        {t: now - timedelta(seconds=5) for t in tickers},
    )


def _make_scheduler():
    """build_session_subscription_view 가 getattr 로만 접근하는 2 dict 스텁.

    fresh 종목뿐이면 stale 분기 미진입이라 실제 미참조이나, 계약 방어로 준비.
    """
    return SimpleNamespace(_stale_retry_count={}, _stale_last_resubscribe_at={})


def _get_session(view, label):
    matches = [s for s in view if s["label"] == label]
    assert matches, f"세션 '{label}' 미포함: {[s['label'] for s in view]}"
    return matches[0]


# ---------------------------------------------------------------------------
# G-195-1: 핵심 divergence — gold capacity = 세션 실측 TICK 카운트 (len(tickers) 아님)
# ---------------------------------------------------------------------------
def test_G195_1_gold_capacity_uses_session_tick_count_not_group_len(monkeypatch):
    """보조 `_label="gold"`, 세션 _subscriptions TICK 2개(+非TICK 1) 인데 groups gold 3개.

    → capacity_used == 2 (세션 실측 TICK 카운트, H0UNMKO0 제외).
    현재 코드 = quote-N 미매칭 → cap=len(tickers)=3 폴백 → Red FAIL. Green 기대 2.
    """
    from src.engine.stale_diagnostics import build_session_subscription_view

    gold = _make_session(
        "gold",
        {(_H0STCNT0, "X"), (_H0STCNT0, "Y"), (_H0UNMKO0, "Z")},  # TICK 2 + 非TICK 1
    )
    _setup_pool(
        monkeypatch,
        groups={"main": {"M1"}, "gold": {"X", "Y", "W"}},  # gold divergence — 3 ticker
        main_subs={(_H0STCNT0, "M1")},
        quote_sessions=[gold],
    )
    _all_fresh(monkeypatch, {"M1", "X", "Y", "W"})

    view = build_session_subscription_view(_make_scheduler())
    gold_view = _get_session(view, "gold")

    assert gold_view["subscribed_count"] == 3, "subscribed_count = groups len (불변)"
    assert gold_view["capacity_used"] == 2, (
        "gold capacity_used = 세션 _subscriptions TICK 카운트(2) 기대 — "
        f"현재 코드 quote-N 미매칭 → len(tickers)=3 폴백 degrade: {gold_view}"
    )


# ---------------------------------------------------------------------------
# G-195-2: 라벨 매칭(인덱스 아님) — "sub" 요청 → sub 세션 TICK 카운트로 cap
# ---------------------------------------------------------------------------
def test_G195_2_label_match_not_index(monkeypatch):
    """_quotes=[gold(idx0), sub(idx1)] 에서 groups "sub" → sub 세션 TICK 카운트.

    인덱스 파싱이면 "sub" 를 특정 세션에 매핑할 방법이 없음 = 라벨 매칭 검증.
    sub 세션 TICK 2개 vs groups sub 4개(divergence) → Green 2, Red len=4.
    """
    from src.engine.stale_diagnostics import build_session_subscription_view

    gold = _make_session("gold", {(_H0STCNT0, "G1")})              # index 0
    sub = _make_session("sub", {(_H0STCNT0, "S1"), (_H0STCNT0, "S2")})  # index 1, TICK 2
    _setup_pool(
        monkeypatch,
        groups={"main": {"M1"}, "sub": {"S1", "S2", "S3", "S4"}},  # sub divergence — 4
        main_subs={(_H0STCNT0, "M1")},
        quote_sessions=[gold, sub],
    )
    _all_fresh(monkeypatch, {"M1", "S1", "S2", "S3", "S4"})

    view = build_session_subscription_view(_make_scheduler())
    sub_view = _get_session(view, "sub")

    assert sub_view["capacity_used"] == 2, (
        "sub capacity_used = sub 세션 TICK 카운트(2) 기대 (gold 인덱스 아님) — "
        f"현재 코드 미매칭 → len(tickers)=4 폴백: {sub_view}"
    )


# ---------------------------------------------------------------------------
# G-195-3: 미매칭 라벨 → cap_used = len(tickers) graceful 폴백 (불변식)
# ---------------------------------------------------------------------------
def test_G195_3_unmatched_label_graceful_len_fallback(monkeypatch):
    """groups 에만 있고 세션에 매칭 없는 라벨 → len(tickers) 폴백 (Green 후에도 PASS)."""
    from src.engine.stale_diagnostics import build_session_subscription_view

    gold = _make_session("gold", {(_H0STCNT0, "G1")})
    _setup_pool(
        monkeypatch,
        groups={"main": {"M1"}, "orphan": {"O1", "O2", "O3"}},  # orphan = 세션 미매칭
        main_subs={(_H0STCNT0, "M1")},
        quote_sessions=[gold],
    )
    _all_fresh(monkeypatch, {"M1", "O1", "O2", "O3"})

    view = build_session_subscription_view(_make_scheduler())
    orphan_view = _get_session(view, "orphan")

    assert orphan_view["capacity_used"] == 3, (
        f"미매칭 라벨 graceful 폴백 = len(tickers)=3: {orphan_view}"
    )


# ---------------------------------------------------------------------------
# G-195-4 (AST): quote-N 파싱 재도입 영구 차단 + _label 매칭 존재
# ---------------------------------------------------------------------------
def _count_quote_string_constants(func_node: ast.AST) -> int:
    """함수 서브트리 내 'quote-' 포함 문자열 상수 개수.

    `f"quote-{i}"`(JoinedStr 내 Constant 'quote-') + `startswith("quote-")`(Constant 'quote-')
    양쪽 포착 — phantom label_order 생성과 quote-N 분기 조건을 함께 탐지.
    """
    count = 0
    for sub in ast.walk(func_node):
        if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
            if "quote-" in sub.value:
                count += 1
    return count


def _count_split_calls(func_node: ast.AST) -> int:
    """함수 서브트리 내 `.split(...)` 속성 호출 개수 (int(label.split(...)) 파싱 잔존 탐지)."""
    count = 0
    for sub in ast.walk(func_node):
        if (
            isinstance(sub, ast.Call)
            and isinstance(sub.func, ast.Attribute)
            and sub.func.attr == "split"
        ):
            count += 1
    return count


def _has_getattr_label_match(func_node: ast.AST) -> bool:
    """함수 서브트리 내 `getattr(x, "_label", ...)` 호출 존재 여부 (DB 라벨 매칭)."""
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


def test_G195_4_ast_no_quote_n_parsing_and_label_getattr_present():
    """build_session_subscription_view 본체: quote-N 파싱 0건 + _label 매칭 존재."""
    # 탐지기 self-test — known-bad / known-good 스니펫으로 오탐/미탐 검증
    _bad_src = (
        "def f(pool):\n"
        "    order = ['main'] + [f'quote-{i}' for i in range(1, 3)]\n"
        "    for label in order:\n"
        "        if label.startswith('quote-'):\n"
        "            idx = int(label.split('-', 1)[1]) - 1\n"
        "            ws = pool._quotes[idx]\n"
    )
    _bad_node = find_function_def(_bad_src, "f")
    assert _count_quote_string_constants(_bad_node) >= 1, "self-test: 'quote-' 상수 탐지"
    assert _count_split_calls(_bad_node) >= 1, "self-test: .split 탐지"
    assert _has_getattr_label_match(_bad_node) is False, "self-test: getattr(_label) 오탐 0"

    _good_src = (
        "def g(pool):\n"
        "    for label in ['main']:\n"
        "        ws = next("
        "(q for q in pool._quotes if getattr(q, '_label', None) == label), None)\n"
    )
    _good_node = find_function_def(_good_src, "g")
    assert _count_quote_string_constants(_good_node) == 0, "self-test: 'quote-' 미탐 0"
    assert _count_split_calls(_good_node) == 0, "self-test: .split 미탐 0"
    assert _has_getattr_label_match(_good_node) is True, "self-test: getattr(_label) 탐지"

    # 실제 production 함수 검증
    source = read_module_source(SRC_PATH)
    func_node = find_function_def(source, "build_session_subscription_view")
    assert func_node is not None, "build_session_subscription_view 정의 부재"
    assert _count_quote_string_constants(func_node) == 0, (
        "build_session_subscription_view 에 'quote-' 문자열 상수 잔존 "
        "(phantom label_order 또는 startswith('quote-')) — DB 라벨 매칭으로 제거 의무"
    )
    assert _count_split_calls(func_node) == 0, (
        "build_session_subscription_view 에 .split 호출 잔존 (quote-N 인덱스 파싱) — "
        "disable_quote_session 패턴 미러 의무"
    )
    assert _has_getattr_label_match(func_node), (
        'build_session_subscription_view 에 getattr(q, "_label", ...) 매칭 부재 — '
        "DB 라벨 매칭 도입 의무 (disable_quote_session 패턴 미러)"
    )
