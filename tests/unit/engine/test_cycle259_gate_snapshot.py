"""cycle259 Red — `account_gate` 스냅샷 단일 소유자 `get_gate_snapshot()` (리팩토링 카드 ⑥).

명세: `spec_cycle259_gate_snapshot_log_split.md` §1 ⑥ · §2 (S1~S4).
근거: `_workspace/refactor/2026-09-05_review.md` 카드 #6.

## 왜 이 테스트가 필요한가

같은 값(계좌 SOFT 게이트 상태)을 두 소비자가 **서로 다른 형상**으로 내보내고 있다.

- `log_analysis_engine._build_portfolio_risk_snapshot` → `dict(get_gate_state())` +
  `_eval_timeout_count()` = **9키** (20:10 리포트 · bundle API · JSONB)
- `routes/portfolio.py::get_portfolio_risk` → `get_gate_state()` = **8키**
  (`/api/portfolio/risk` — 타임아웃 횟수 부재)

조립 로직이 두 벌이라 한쪽만 고치면 조용히 갈라지고, `_eval_timeout_count()` 는
private 접근자인데 `log_analysis_engine` 이 모듈 경계 밖에서 읽는다. cycle233 활성화
게이트(AND)의 실측 판독이 이 두 채널을 오가므로 형상 불일치는 판독 사고로 이어진다.

## 이 파일이 못박는 계약

- S1: `get_gate_snapshot()` = `get_gate_state()` 8키 ∪ `{eval_timeouts_today}` = **9키**,
      값은 두 소스와 동일하고 반환 dict 는 **복사본**(변조가 watcher 내부로 새지 않는다).
      두 소스에 **위임**한다(S1b — 소스를 patch 하면 반영된다). 위임이 아니라 로직을
      복제하면 cycle251 T2/T2b graceful 계약이 무음으로 깨진다.
- S2: **무발화** — `is_soft_gated()` 호출 0 ∧ stale 상태에서도 `_emit_cap` 미소비.
      `is_soft_gated()` 는 stale 시 `gate_stale` cap 을 소비하는 **쓰기 경로**다.
      관측 read 가 그걸 선소비하면 장중 진짜 hang 의 WARNING 이 그날 무음이 된다
      (cycle233 F1 / cycle239 R1 이 두 번 고친 결함의 재현).
- S3: 두 소비자(20:10 리포트 빌더 · `/api/portfolio/risk`)가 **같은 dict 형상**을 낸다.
      + S3b: 두 소비자 소스에 `get_gate_snapshot` 호출 정확히 1 · `get_gate_state` /
      `_eval_timeout_count` / `is_soft_gated` 0 (AST — 소스 파일은 함수 객체에서
      역추적하므로 카드 ⑦ 의 파일 이동에 영향받지 않는다).
- S4: `get_gate_state()` 본체 `ast.dump` **sha256 리터럴 핀** (byte 불변 — 프론트
      `AccountGate` 8필드 계약) + `_eval_timeout_count` 모듈 밖 호출 0.

RED 상태(구현 전): S1a/S1b/S2a/S2b = `get_gate_snapshot` 부재로 FAIL ·
S3 = 라우트가 8키라 FAIL · S3b = 두 소비자가 구 접근자를 부르므로 FAIL ·
S4b = `log_analysis_engine:619` 가 `_eval_timeout_count()` 를 부르므로 FAIL ·
S4a(sha 핀) 는 watcher 무접촉이라 지금도 GREEN(영구 가드).
"""

from __future__ import annotations

import ast
import hashlib
import inspect
import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from src.engine import account_risk_watcher as arw
from src.engine import log_analysis_engine as lae

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[3]
WATCHER_SRC = ROOT / "src" / "engine" / "account_risk_watcher.py"

#: `get_gate_state()` 8키 = 프론트 `AccountGate` 필수 8필드 (cycle239 4키 + 원 4키).
GATE_KEYS = {
    "level",
    "reasons",
    "open_risk_pct",
    "evaluated_at",
    "age_secs",
    "stale",
    "stale_max_secs",
    "effective_gated",
}

#: `get_gate_snapshot()` = 위 8키 + cycle250 타임아웃 셈 1키.
SNAPSHOT_KEYS = GATE_KEYS | {"eval_timeouts_today"}

_BUILDER = "_build_portfolio_risk_snapshot"
_ROUTE_FN = "get_portfolio_risk"


def _snapshot_fn():
    """`get_gate_snapshot` 접근자 — 부재 시 Red 로 명시 실패."""
    fn = getattr(arw, "get_gate_snapshot", None)
    if fn is None:  # pragma: no cover - Red 경로
        pytest.fail(
            "Red — `src/engine/account_risk_watcher.py` 에 공개 "
            "`get_gate_snapshot() -> dict` 미구현 (리팩토링 카드 ⑥). "
            "= `get_gate_state()` 8키 + `eval_timeouts_today`, 무발화 read."
        )
    return fn


@pytest.fixture
def fresh_gate(monkeypatch):
    """결정론 게이트 상태 — 평가 100초 전, 활성, warn 레벨.

    `_now_mono` seam 을 고정해 `age_secs` 가 호출 간 흔들리지 않게 한다(두 소비자
    비교가 시각 때문에 깨지면 안 된다).
    """
    arw.reset_state_for_test()
    monkeypatch.setattr(arw, "_now_mono", lambda: 10_000.0)
    arw._evaluated_mono = 9_900.0  # age = 100.0s (< 900 → fresh)
    arw._gate_active = True
    arw._gate_state = {
        "level": "warn",
        "reasons": ["open_risk_pct=5.10 >= warn_pct=5.00"],
        "open_risk_pct": 5.10,
        "evaluated_at": "2026-09-07T10:30:00+09:00",
    }
    yield
    arw.reset_state_for_test()


@pytest.fixture
def snapshot_deps(monkeypatch):
    """20:10 빌더 + `/api/portfolio/risk` 의 하위 의존(잔고·registry·섹터)만 대역.

    게이트 접근자는 **실물 그대로** — 이 사이클이 검증하는 배선이 그 사이에 있다.
    """
    import src.api.balance as balance_mod
    import src.engine.sector_naming as sector_mod
    import src.routes.portfolio as portfolio_mod
    from src.engine.scheduler import trading_scheduler

    async def _fake_get_balance():
        return ([], SimpleNamespace(net_asset=100_000_000))

    async def _fake_resolve(_tickers):
        return {}

    fake_registry = SimpleNamespace(all=lambda: [])

    # 20:10 빌더 경로 (lazy import — 원 모듈을 갈아끼운다)
    monkeypatch.setattr(balance_mod, "get_balance", _fake_get_balance)
    monkeypatch.setattr(sector_mod, "resolve_sector_names", _fake_resolve)
    monkeypatch.setattr(trading_scheduler, "registry", fake_registry)
    # 라우트 경로 (모듈 레벨 import — 라우트 네임스페이스를 갈아끼운다)
    monkeypatch.setattr(portfolio_mod, "get_balance", _fake_get_balance)
    monkeypatch.setattr(portfolio_mod, "resolve_sector_names", _fake_resolve)
    monkeypatch.setattr(portfolio_mod, "trading_scheduler", SimpleNamespace(registry=fake_registry))
    yield


# ===========================================================================
# S1 — 9키 · 값 정합 · 복사본 · 두 소스 위임
# ===========================================================================
def test_s1a_snapshot_when_called_then_nine_keys_match_both_sources(fresh_gate):
    fn = _snapshot_fn()
    arw._bump_eval_timeout_count()
    arw._bump_eval_timeout_count()

    snap = fn()

    assert isinstance(snap, dict)
    assert set(snap) == SNAPSHOT_KEYS, (
        f"키 집합 불일치 — 기대 {sorted(SNAPSHOT_KEYS)} / 실측 {sorted(snap)}. "
        "`get_gate_state()` 8키 + `eval_timeouts_today` 정확히 9키가 계약이다"
    )

    state = arw.get_gate_state()
    for key in GATE_KEYS:
        assert snap[key] == state[key], (
            f"`{key}` 가 `get_gate_state()` 와 다르다: {snap[key]!r} != {state[key]!r}"
        )
    assert snap["age_secs"] == 100 and snap["stale"] is False
    assert snap["effective_gated"] is True
    assert snap["level"] == "warn"

    assert snap["eval_timeouts_today"] == arw._eval_timeout_count() == 2
    assert isinstance(snap["eval_timeouts_today"], int)
    assert not isinstance(snap["eval_timeouts_today"], bool)

    # 복사본 계약 — 반환 dict 변조가 watcher 내부로 새지 않는다
    assert snap is not arw._gate_state
    snap["level"] = "MUTATED"
    snap["eval_timeouts_today"] = 999
    assert arw.get_gate_state()["level"] == "warn", (
        "반환 dict 가 watcher 내부 `_gate_state` 를 그대로 실었다 — 소비자가 스냅샷을 "
        "만지면 게이트 상태가 오염된다 (`dict(...)` 복사가 계약)"
    )
    assert arw._eval_timeout_count() == 2


def test_s1b_snapshot_when_sources_patched_then_delegates_to_them(fresh_gate, monkeypatch):
    """두 소스에 **위임**한다 — 로직 복제 금지.

    cycle251 T2/T2b 는 `arw.get_gate_state` / `arw._eval_timeout_count` 를 patch 해
    graceful(키 미부착)을 잰다. 스냅샷이 `_gate_state` 를 직접 읽는 복제 구현이면
    그 patch 가 통과해버려 계약이 무음으로 사라진다.
    """
    fn = _snapshot_fn()
    origin = {
        "level": "block",
        "reasons": ["sentinel"],
        "open_risk_pct": 9.9,
        "evaluated_at": "2026-09-07T11:00:00+09:00",
        "age_secs": 7,
        "stale": False,
        "stale_max_secs": 900,
        "effective_gated": True,
    }
    monkeypatch.setattr(arw, "get_gate_state", lambda: origin)
    monkeypatch.setattr(arw, "_eval_timeout_count", lambda: 7)

    snap = fn()

    assert snap["level"] == "block" and snap["reasons"] == ["sentinel"], (
        "`get_gate_state()` 에 위임하지 않는다 — 조립 로직이 두 벌이 되면 카드 ⑥ 이 "
        "없애려던 형상 갈라짐이 그대로 남는다"
    )
    assert snap["eval_timeouts_today"] == 7, (
        "`_eval_timeout_count()` 에 위임하지 않는다 (모듈 내부 변수 직접 읽기 금지)"
    )
    assert snap is not origin, "소스 dict 를 그대로 반환했다 — 복사본이어야 한다"
    assert "eval_timeouts_today" not in origin, "소스 dict 를 제자리에서 오염시켰다"


# ===========================================================================
# S2 — 무발화 (is_soft_gated 0 · cap 미소비)
# ===========================================================================
def test_s2a_snapshot_when_called_then_is_soft_gated_never_called(fresh_gate, monkeypatch):
    fn = _snapshot_fn()
    spy = MagicMock(return_value=False)
    monkeypatch.setattr(arw, "is_soft_gated", spy)

    fn()

    assert spy.call_count == 0, (
        "`get_gate_snapshot()` 이 `is_soft_gated()` 를 불렀다 — stale 이면 `gate_stale` "
        "cap 을 **선소비**해 그날 장중 진짜 hang 의 WARNING 이 무음이 된다 "
        "(cycle233 F1 / cycle239 R1 동형). 스냅샷은 무발화 read 계약이다."
    )


def test_s2b_snapshot_when_gate_stale_then_emit_cap_untouched():
    """실물 상태로 stale 을 만들어 cap 소비를 직접 관측한다 (스파이 없는 2차 증거)."""
    arw.reset_state_for_test()
    try:
        fn = _snapshot_fn()
        arw._gate_active = True
        arw._evaluated_mono = None  # 미평가 → stale
        before = set(arw._emit_cap._emitted)
        assert before == set()

        snap = fn()

        assert set(arw._emit_cap._emitted) == before, (
            f"`_emit_cap` 이 소비됐다 ({sorted(arw._emit_cap._emitted)}) — 관측 read 가 "
            "쓰기 경로(`is_soft_gated` → `_emit_stale_release`)를 탔다"
        )
        # 동결 서명 보존 (cycle239 계약) — level 은 마지막 평가값 그대로
        assert snap["stale"] is True
        assert snap["effective_gated"] is False
        assert snap["level"] == "ok"
        assert snap["eval_timeouts_today"] == 0
    finally:
        arw.reset_state_for_test()


# ===========================================================================
# S3 — 두 소비자가 같은 dict 형상
# ===========================================================================
async def test_s3_two_consumers_when_built_then_identical_gate_shape(fresh_gate, snapshot_deps):
    """20:10 리포트 빌더 ↔ `/api/portfolio/risk` 형상 동일 (9키).

    현행 RED = 라우트가 8키(`eval_timeouts_today` 부재). 프론트는 cycle256 이
    `eval_timeouts_today?` 를 선반영해 두었으므로 키 1개 **추가만** 이다.
    """
    import src.routes.portfolio as portfolio_mod

    arw._bump_eval_timeout_count()

    builder = getattr(lae, _BUILDER)
    report_snapshot = await builder()
    assert report_snapshot is not None and "account_gate" in report_snapshot, (
        "20:10 빌더가 `account_gate` 를 붙이지 않았다 (cycle251 회귀)"
    )
    report_gate = report_snapshot["account_gate"]

    resp = await getattr(portfolio_mod, _ROUTE_FN)()
    route_snapshot = resp.data
    assert isinstance(route_snapshot, dict) and "account_gate" in route_snapshot, (
        "`/api/portfolio/risk` 가 `account_gate` 를 붙이지 않았다 (cycle233 회귀)"
    )
    route_gate = route_snapshot["account_gate"]

    assert set(report_gate) == SNAPSHOT_KEYS, (
        f"리포트 게이트 키 {sorted(report_gate)} != 기대 9키"
    )
    assert set(route_gate) == SNAPSHOT_KEYS, (
        f"Red — 라우트 게이트 키 {sorted(route_gate)} != 기대 9키. "
        "`/api/portfolio/risk` 는 `eval_timeouts_today` 없이 8키만 낸다 — 같은 값을 "
        "두 형상으로 내보내는 것이 카드 ⑥ 이 없애려는 결함이다"
    )
    assert set(report_gate) == set(route_gate), (
        f"두 소비자 형상 불일치: 리포트만 {sorted(set(report_gate) - set(route_gate))} / "
        f"라우트만 {sorted(set(route_gate) - set(report_gate))}"
    )
    assert report_gate["eval_timeouts_today"] == route_gate["eval_timeouts_today"] == 1
    assert report_gate["level"] == route_gate["level"] == "warn"
    assert report_gate is not route_gate


def _fn_node(path: Path, name: str):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    raise AssertionError(f"{path.name} 에 {name} 부재")


def _call_count(node: ast.AST, name: str) -> int:
    """`name(...)` / `mod.name(...)` **정확 일치** 호출 수."""
    count = 0
    for sub in ast.walk(node):
        if not isinstance(sub, ast.Call):
            continue
        fn = sub.func
        if isinstance(fn, ast.Name) and fn.id == name:
            count += 1
        elif isinstance(fn, ast.Attribute) and fn.attr == name:
            count += 1
    return count


def _body_without_docstring(fn) -> list[ast.stmt]:
    body = list(fn.body)
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
        body = body[1:]
    return body


def test_s3b_both_consumers_call_snapshot_once_and_nothing_else():
    """두 소비자 소스 봉인 — `get_gate_snapshot` 1회, 구 접근자 0회.

    소스 파일은 **함수 객체에서 역추적**한다(`inspect.getsourcefile`) — 카드 ⑦ 이
    `_build_portfolio_risk_snapshot` 을 `log_metrics_collector.py` 로 옮겨도 이
    가드는 따라간다(리터럴 경로 상수를 쓰면 이동 때마다 거짓 RED 가 된다 —
    cycle251 `LAE_SRC` 가 지금 그 상태다).
    """
    import src.routes.portfolio as portfolio_mod

    builder_file = Path(inspect.getsourcefile(getattr(lae, _BUILDER)))
    route_file = Path(inspect.getsourcefile(getattr(portfolio_mod, _ROUTE_FN)))

    for path, name in ((builder_file, _BUILDER), (route_file, _ROUTE_FN)):
        node = _fn_node(path, name)
        code = "\n".join(ast.unparse(stmt) for stmt in _body_without_docstring(node))

        assert _call_count(node, "get_gate_snapshot") == 1, (
            f"Red — `{path.name}::{name}` 이 `get_gate_snapshot()` 을 정확히 1회 "
            f"부르지 않는다 (실측 {_call_count(node, 'get_gate_snapshot')}). "
            "스냅샷 조립은 watcher 단일 소유다."
        )
        assert _call_count(node, "get_gate_state") == 0, (
            f"`{path.name}::{name}` 이 `get_gate_state()` 를 직접 부른다 — 조립이 "
            "두 벌로 남는다(카드 ⑥ 의 표적)"
        )
        assert _call_count(node, "_eval_timeout_count") == 0, (
            f"`{path.name}::{name}` 이 private `_eval_timeout_count()` 를 모듈 밖에서 "
            "읽는다 — 경계 위반"
        )
        assert "is_soft_gated" not in code, (
            f"`{path.name}::{name}` 본문에 `is_soft_gated` 식별자 — 그 함수는 "
            "`gate_stale` cap 을 소비하는 쓰기 경로다 (설명은 docstring 에)"
        )


# ===========================================================================
# S4 — get_gate_state 본체 sha 리터럴 핀 + private 접근자 외부 호출 0
# ===========================================================================
#: `ast.dump(get_gate_state)` 의 sha256. **리터럴 핀** — HEAD 대비 `git show` 비교는
#: 커밋 직후 자기 일치로 전락하고(공허) 그 뒤 어떤 편집이든 영구 동결로 변한다
#: (리팩토링 리뷰 카드 #2 가 cycle250/251 에서 지적한 그 함정). 정당한 변경 시
#: 이 한 줄을 갱신하되 **프론트 `AccountGate` 8필드 · 라우트 · 리포트 3곳 동기**를
#: 함께 확인한다.
_GET_GATE_STATE_AST_SHA = "923bf376c49ac762f561845b6201913d904d05520a46f1e743d6d9586339101a"


def test_s4a_get_gate_state_body_is_byte_stable():
    node = _fn_node(WATCHER_SRC, "get_gate_state")
    got = hashlib.sha256(ast.dump(node).encode("utf-8")).hexdigest()
    assert got == _GET_GATE_STATE_AST_SHA, (
        f"`get_gate_state()` 본체가 변경됐다 (sha {got}). 카드 ⑥ 은 **추가만** 한다 — "
        "이 함수는 프론트 `AccountGate` 8필드 계약의 원천이라 byte 불변이다. "
        "의도한 변경이라면 이 리터럴을 갱신하고 프론트 타입·라우트·리포트를 함께 본다."
    )


def test_s4b_private_timeout_accessor_has_no_callers_outside_watcher():
    """`_eval_timeout_count` 는 watcher **내부용** — 모듈 밖 호출 0 (§1 ⑥)."""
    out = subprocess.run(
        ["git", "grep", "-n", "_eval_timeout_count", "--", "src"],
        cwd=ROOT, capture_output=True, text=True,
    )
    # git grep: 0=매치 있음 · 1=매치 없음 · >1=실행 실패(무매치로 오독하면 fail-open)
    if out.returncode > 1:  # pragma: no cover - git 부재 환경
        pytest.skip(f"git grep 실행 실패(rc={out.returncode}) — 외부 호출 0 판정 불가")
    hits = [
        line for line in out.stdout.splitlines()
        if line.strip() and not line.startswith("src/engine/account_risk_watcher.py:")
    ]
    assert hits == [], (
        "Red — private 접근자 `_eval_timeout_count` 를 watcher 밖에서 참조한다:\n  "
        + "\n  ".join(hits)
        + "\n두 소비자는 공개 `get_gate_snapshot()` 만 쓴다 (카드 ⑥)."
    )
