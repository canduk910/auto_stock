"""cycle273b Red (AST) — D2(다) 무행위 3건의 **구조 계약**.

명세 = `_workspace/red/cycle273b_philoptics_no_behavior_3_spec.md`

| # | 가드 | 지키는 것 | HEAD |
|---|---|---|---|
| G-273b-AST1 | `order_engine.py` 의 `update_trade_status` 호출 **전부**가 `order_no=` 를 넘긴다 | F-1/F-2 스코프(6곳, C5/C6 포함) | GREEN(I3) |
| G-273b-AST2 | `[trade_status_multi_update]` 는 `src/db/trade_history.py` **한 곳**에만 있고 `logger.warning` 으로 낸다 | 8영역 diff 축소 + 단일 진실원 | GREEN(I3) |
| G-273b-AST3 | leaf `src/engine/selling_reconcile.py` 존재 + `[selling_hold]` 를 `logger.warning` 으로 낸다 | F-7 | **RED** |
| G-273b-AST4 | scheduler 의 `_selling` 인라인 3분기 소멸(`open_sell_tickers` 토큰 0건) + leaf 호출 존재 | 위임 실증 | **RED** |
| G-273b-AST5 | `scheduler.py` < 3,900L | cycle257 영구 상한 자매 | GREEN(3,898) |
| G-273b-AST6 | leaf 가 `KstDailyEmitCap` 과 `trace_observer_failure` 를 쓴다 | cycle258 관측 배관 표준 | **RED** |

## 규약
`ast.dump` sha 핀 금지(3.12 CI ↔ 3.13 로컬) · `git grep`/`git ls-files` 금지
(미추적 파일 실종) · 기준선 소실은 명시 FAIL(vacuous PASS 차단).
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

import src as _src_pkg

pytestmark = pytest.mark.unit

_SRC = Path(_src_pkg.__file__).resolve().parent
_ROOT = _SRC.parent
_ORDER_ENGINE = _SRC / "engine" / "order_engine.py"
_TRADE_HISTORY = _SRC / "db" / "trade_history.py"
_SCHEDULER = _SRC / "engine" / "scheduler.py"
_LEAF = _SRC / "engine" / "selling_reconcile.py"

_MULTI_MARKER = "[trade_status_multi_update]"
_HOLD_MARKER = "[selling_hold]"
_SCHEDULER_LINE_CAP = 3_900


def _py_files() -> list[Path]:
    return [p for p in _SRC.rglob("*.py") if p.is_file()]


def _calls_named(tree: ast.AST, name: str) -> list[ast.Call]:
    out = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        label = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", None)
        if label == name:
            out.append(node)
    return out


def _marker_log_calls(tree: ast.AST, marker: str) -> list[tuple[str, int]]:
    """마커 문자열을 첫 인자로 싣는 `logger.<level>(...)` 호출 목록."""
    out = []
    _LEVELS = {"debug", "info", "warning", "error", "critical", "exception"}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if not node.args:
            continue
        first = node.args[0]
        if isinstance(first, ast.Constant) and isinstance(first.value, str) \
                and first.value.startswith(marker):
            owner = node.func.value
            owner_name = getattr(owner, "id", getattr(owner, "attr", ""))
            out.append((f"{owner_name}.{node.func.attr}", node.lineno))
            continue
        # cycle258 표준 진입점 `cap.emit_once(key, logger.<level>, "<marker> ...", ...)` —
        # 마커가 3번째 위치 인자, 로거 메서드가 2번째 인자다(검증 r1/r2 MEDIUM: 직접 호출만
        # 세던 종전 매처는 표준 배관을 구조적으로 못 봤다). owner 는 args[1] 에서 읽는다.
        if node.func.attr == "emit_once" and len(node.args) >= 3:
            lg, msg = node.args[1], node.args[2]
            if isinstance(lg, ast.Attribute) and lg.attr in _LEVELS \
                    and isinstance(msg, ast.Constant) and isinstance(msg.value, str) \
                    and msg.value.startswith(marker):
                owner_name = getattr(lg.value, "id", getattr(lg.value, "attr", ""))
                out.append((f"{owner_name}.{lg.attr}", node.lineno))
    return out


# ---------------------------------------------------------------------------
# G-273b-AST1 — order_no 는 6곳 전부
# ---------------------------------------------------------------------------
def test_g273b_ast1_all_update_calls_pass_order_no():
    """GREEN(I3) — 6/6. I1(F-7) 시점 HEAD 는 0/6 이었다(워크리스트 등재).

    정본 F-2 문면은 C1·C3 두 곳이지만 코드 근거는 **6곳 전부**다. 특히 C5/C6
    (`_cancel_after_wait`·`_cancel_and_reorder` 의 CANCELLED)가 가장 위험하다 —
    부분체결 주문 A 의 타이머가 같은 ticker·strategy 의 **다른 주문 B 의 PENDING 행**
    을 CANCELLED 로 뒤집으면, B 의 체결통보는 1차 UPDATE 0 → 보정 INSERT
    UniqueViolation → 강제 UPDATE(PENDING∪PARTIAL)도 CANCELLED 를 못 집는다
    ⇒ B 행이 **영구 CANCELLED** = 정산·sync 양쪽 소실(UA §6.1).

    ⚠️ 직전 검증 HIGH#1 — 종전 매처는 `k.arg == "order_no"` 로 **키워드 이름의
    존재만** 검사하고 **바인딩된 값**은 보지 않았다. `order_no=ticker` 처럼 엉뚱한
    변수를 넘겨도(그 자리는 항상 ticker 자신으로 WHERE 를 좁히니 실질적으로
    "order_no 없음"과 동형인 결함) 이 가드는 그냥 통과시켰다 — 뮤테이션 M12
    ESCAPED 로 실측 확인. 그래서 **지역 변수 `order_no` 를 그대로 넘겼는지**까지
    고정한다.
    """
    tree = ast.parse(_ORDER_ENGINE.read_text(encoding="utf-8"))
    calls = _calls_named(tree, "update_trade_status")
    assert len(calls) >= 6, f"기준선 소실 — 호출이 6곳 미만이다({len(calls)})"

    missing = [
        c.lineno for c in calls
        if not any(
            k.arg == "order_no" and isinstance(k.value, ast.Name) and k.value.id == "order_no"
            for k in c.keywords
        )
    ]
    assert missing == [], (
        f"order_engine.py 의 update_trade_status 호출 중 order_no 를 지역 변수 order_no "
        f"그대로 넘기지 않은 지점: 줄 {missing} — 키워드 이름만이 아니라 지역 변수 "
        f"order_no 를 그대로 넘겨야 한다(WHERE 를 좁히기만 하므로 무행위 — 빠뜨리거나 "
        f"엉뚱한 변수를 넘기면 그 자리만 161580 결함이 남는다)"
    )


# ---------------------------------------------------------------------------
# G-273b-AST2 — F-3 관측은 db 한 곳 · WARNING
# ---------------------------------------------------------------------------
def test_g273b_ast2_multi_update_marker_single_site_warning():
    """GREEN(I3) — 마커가 `trade_history.update_trade_status` 한 곳에만 있다.

    관측을 `trade_history.update_trade_status` 안에 두면 (a) C1~C6 **여섯 곳 전부**를
    덮고 (b) `order_engine.py`(8영역) diff 가 늘지 않는다(cycle258 leaf 관례와 동형).
    """
    sites: list[tuple[str, str, int]] = []
    for path in _py_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for owner, lineno in _marker_log_calls(tree, _MULTI_MARKER):
            sites.append((str(path.relative_to(_ROOT)), owner, lineno))

    assert len(sites) == 1, f"{_MULTI_MARKER} emit 지점이 정확히 1곳이 아니다 — {sites}"
    rel, owner, _ln = sites[0]
    assert rel == "src/db/trade_history.py", f"emit 이 db 밖에 있다 — {rel}"
    assert owner.endswith(".warning"), (
        f"emit 레벨이 WARNING 이 아니다({owner}) — `_DbLogHandler` 가 INFO 컷이라 "
        f"debug/info 는 `system_logs` 에 도달하지 않는다"
    )


# ---------------------------------------------------------------------------
# G-273b-AST3/4/6 — F-7 leaf 위임
# ---------------------------------------------------------------------------
def test_g273b_ast3_selling_hold_marker_in_leaf_warning():
    """RED (HEAD) — leaf 부재."""
    assert _LEAF.exists(), (
        f"RED — leaf `{_LEAF.relative_to(_ROOT)}` 미구현. scheduler 3,898L/상한 3,900L "
        f"이라 인라인 관측은 불가하다(UA §7)"
    )
    tree = ast.parse(_LEAF.read_text(encoding="utf-8"))
    emits = _marker_log_calls(tree, _HOLD_MARKER)
    assert emits, f"{_HOLD_MARKER} emit 이 leaf 에 없다"
    assert all(owner.endswith(".warning") for owner, _ln in emits), (
        f"유지 관측은 WARNING 이어야 한다(INFO 는 system_logs 미적재) — {emits}"
    )


def test_g273b_ast4_scheduler_delegates_and_drops_inline_block():
    """RED (HEAD) — 인라인 3분기가 그대로 있다."""
    src = _SCHEDULER.read_text(encoding="utf-8")
    tree = ast.parse(src)

    inline_tokens = {
        node.id for node in ast.walk(tree) if isinstance(node, ast.Name)
    } | {
        node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
    }
    assert "open_sell_tickers" not in inline_tokens, (
        "scheduler 에 stale `_selling` 재대조 인라인 블록이 남아 있다 — "
        "leaf 로 옮기지 않으면 라인 상한(<3,900) 때문에 관측을 넣을 자리가 없다"
    )

    assert _calls_named(tree, "reconcile_stale_selling"), (
        "scheduler 가 leaf 진입점을 호출하지 않는다 — 재대조가 통째로 사라졌다면 "
        "stale `_selling` 이 손절을 종일 억제한다"
    )


def test_g273b_ast6_leaf_uses_standard_observation_plumbing():
    """RED (HEAD) — leaf 부재."""
    assert _LEAF.exists(), f"RED — leaf `{_LEAF.relative_to(_ROOT)}` 미구현"
    src = _LEAF.read_text(encoding="utf-8")
    assert "KstDailyEmitCap" in src, (
        "cap 은 `KstDailyEmitCap` 재사용 — 신규 cap 클래스 정의 금지(cycle258 카드 #4)"
    )
    assert "trace_observer_failure" in src, (
        "관측기 자기 실패는 `observer_trace.trace_observer_failure` 로 흔적을 남긴다"
        "(cycle258 카드 #5, 무흔적 `pass` 금지)"
    )


# ---------------------------------------------------------------------------
# G-273b-AST5 — scheduler 라인 상한 (cycle257 영구 가드 자매)
# ---------------------------------------------------------------------------
def test_g273b_ast5_scheduler_line_count_below_cap():
    """GREEN — 현재 3,898L. leaf 위임(−27행 내외)으로 여유가 늘어야 정상이다."""
    lines = _SCHEDULER.read_text(encoding="utf-8").splitlines()
    assert len(lines) < _SCHEDULER_LINE_CAP, (
        f"scheduler.py {len(lines)}L ≥ 상한 {_SCHEDULER_LINE_CAP}L — "
        f"cycle257 영구 가드와 자매(느슨한 자체 상한 재발 차단, cycle264 HIGH)"
    )
