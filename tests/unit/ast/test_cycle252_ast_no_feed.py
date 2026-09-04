"""cycle252 Red — AST/구조 가드: no_feed 분기의 **위치·범위·의존 방향** 봉인.

> 정본 명세: `spec_cycle252_no_feed_churn.md` §2(범위/금지) / §3 G-252-1~7
> 포렌식 근거: `_workspace/forensics/stale_candidates_0904.md` ⑤A

행위 테스트(`tests/unit/engine/test_cycle252_stale_watcher_no_feed.py`)가 잡지 못하는
**구조**를 고정한다 — 분기가 `retry > MAX` 뒤로 밀리거나, HIGH 에도 걸리거나, skip 경로에
SEND/스탬프가 되살아나거나, leaf 가 scheduler/scanner 를 끌어와 의존 방향이 뒤집히는 회귀.

| ID | 검사 | 뮤테이션 표적 |
|----|------|--------------|
| G-252-1 | `no_feed_registry.py` 금지 import 0 + `stock_master` 는 lazy | leaf 오염 / 순환 import |
| G-252-2 | `stale_watcher_core.py` 의 `sys.modules.get` 출현 수 = 기준값 7 (cycle252 직전 sha 8b146ff 실측) | cycle63 D-2 카운트 가드 훼손 |
| G-252-3 | no_feed 분기가 `sub_priority` 대입 **뒤** · `retry > MAX` **앞** | 분기 이동 |
| G-252-4 | 분기 본문 토큰 0: unsubscribe/subscribe/스탬프/sleep | skip 이 skip 이 아니게 되는 회귀 |
| ~~G-252-5~~ | (폐기 — 사이클 한정 bare git diff 가드, 배포 후 삭제) | — |
| G-252-6 | 시간창 리터럴 신설 0 (두 파일) | 시각 게이트 밀반입 |
| G-252-7 | `write_log` 직접 호출 0 (두 파일) | cycle72 이중 INSERT 회귀 |

⚠️ **G-252-5 는 사이클 한정 가드 — cycle252 배포(커밋) 후 폐기 대상**이다.
bare `git diff HEAD` 를 영구 동결하면 그 파일의 모든 후속 시정이 무조건 RED 가 된다
(cycle240 이 cycle222a 가드를 재스코프해야 했던 교훈). 커밋되면 diff 가 비어 자기소멸하고,
그 시점에 이 테스트를 삭제한다.

G-252-2 는 그 반대로 **영구 가드**다 — 기준을 `HEAD` 로 두면 커밋 직후 자기 일치
검사로 전락하므로(tester F-4) cycle252 직전 sha(8b146ff)에서 실측한 **리터럴 7** 을
핀한다(cycle241 `sys.modules.get("src.engine.scheduler")` 카운트 가드와 같은 방식,
git 무관 = shallow clone 에서도 동작). 정당한 seam 추가는 그 사이클이 이 값을 갱신한다.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_REPO_ROOT = Path(__file__).resolve().parents[3]
_CORE_REL = "src/engine/stale_watcher_core.py"
_REG_REL = "src/engine/no_feed_registry.py"
_CORE = _REPO_ROOT / _CORE_REL
_REG = _REPO_ROOT / _REG_REL

_FUNC = "check_and_resubscribe_stale"

# 시간창 리터럴 — **정확 일치**만 금지한다. 설명 문장 안의 "09:05~15:20" 같은
# 부분 문자열은 서술이지 게이트가 아니다(금지 대상은 "시각으로 분기하는 코드").
_TIME_LITERALS = {"08:00", "09:00", "15:20", "15:30"}



def _tree(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"))


def _require_registry_file() -> Path:
    if not _REG.exists():  # pragma: no cover - Red 단계 경로
        pytest.fail(
            f"cycle252 §2 — 신규 leaf `{_REG_REL}` 미존재 (Red)."
        )
    return _REG


def _find_func(tree: ast.Module, name: str):
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    return None


# ===========================================================================
# G-252-1 — leaf 의존 방향 (scheduler/scanner/realtime/registry import 0)
# ===========================================================================
_BANNED_MODULE_PREFIXES = (
    "src.engine.scheduler",
    "src.engine.scanner",
    "src.engine.stale_",
    "src.engine.strategy_registry",
    "src.engine.risk",
    "src.engine.order_engine",
    "src.realtime",
)
_BANNED_FROM_SRC_ENGINE = {
    "scheduler", "scanner", "strategy_registry", "risk", "order_engine",
    "stale_watcher_core", "stale_diagnostics", "stale_universe_guard",
    "stale_session_recovery",
}


def test_g252_1_registry_has_no_banned_imports():
    """`no_feed_registry` 는 stdlib · `src.db.stock_master` · logging 만 본다.

    이 leaf 를 `stale_watcher_core` 가 모듈 레벨에서 import 하므로, leaf 가 scheduler/
    scanner/realtime 을 끌어오면 그 자리에서 순환 import 가 생기고 의존 방향(옵션 A
    단방향, G-7)이 뒤집힌다.
    """
    path = _require_registry_file()
    tree = _tree(path)
    offenders: list[str] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith(_BANNED_MODULE_PREFIXES):
                    offenders.append(f"L{node.lineno}: import {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if mod.startswith(_BANNED_MODULE_PREFIXES):
                offenders.append(f"L{node.lineno}: from {mod} import ...")
            elif mod == "src.engine":
                for alias in node.names:
                    if alias.name in _BANNED_FROM_SRC_ENGINE:
                        offenders.append(
                            f"L{node.lineno}: from src.engine import {alias.name}"
                        )

    assert offenders == [], (
        f"{_REG_REL} 에 금지 import 잔존 — 의존 방향 위반: {offenders}"
    )


def test_g252_1b_stock_master_import_is_lazy():
    """`src.db.stock_master` 는 **함수 안**에서만 import 한다.

    모듈 레벨이면 leaf import 만으로 DB 계층이 끌려와 hot path import 비용 + 테스트
    격리(모듈 patch seam)가 무너진다.
    """
    path = _require_registry_file()
    tree = _tree(path)

    func_bodies = [
        n for n in ast.walk(tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]
    inside_lines: set[int] = set()
    for f in func_bodies:
        for n in ast.walk(f):
            if isinstance(n, (ast.Import, ast.ImportFrom)):
                inside_lines.add(n.lineno)

    module_level: list[str] = []
    found = False
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            names = {a.name for a in node.names}
            if mod == "src.db.stock_master" or (
                mod == "src.db" and "stock_master" in names
            ):
                found = True
                if node.lineno not in inside_lines:
                    module_level.append(f"L{node.lineno}: from {mod} import ...")
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "src.db.stock_master":
                    found = True
                    if node.lineno not in inside_lines:
                        module_level.append(f"L{node.lineno}: import {alias.name}")

    assert found, (
        f"{_REG_REL} 에 `src.db.stock_master` import 부재 — DB 조회 경로 미배선"
    )
    assert module_level == [], (
        f"{_REG_REL} 의 stock_master import 는 lazy(함수 안) 의무 — actual={module_level}"
    )


# ===========================================================================
# G-252-2 — sys.modules.get 출현 수 불변 (cycle63 D-2 계열 카운트 가드 존중)
# ===========================================================================
# cycle252 직전 sha 8b146ff 의 `stale_watcher_core.py` 실측값(docstring 1 + 코드 6).
# `HEAD:` 기준 비교는 커밋 직후 자기 일치로 전락한다(tester F-4) — 리터럴 핀.
_BASELINE_SYS_MODULES_GET_COUNT = 7
_BASELINE_SHA_SHORT = "8b146ff"


def test_g252_2_sys_modules_get_count_matches_head():
    """`no_feed_registry` 는 **정적 import** 로 붙인다 — sys.modules seam 신설 금지.

    cycle63 D-1/D-2 가 `sys.modules.get` 출현 수를 세는 가드를 두고 있고, 새 seam 을
    끼우면 그 카운트가 조용히 어긋난다. 스펙 §2(a) 도 "sys.modules.get 출현 수 불변" 을
    명시한다. 기준은 cycle252 직전 sha 에서 실측한 리터럴(`_BASELINE_SYS_MODULES_GET_COUNT`)
    — 후속 사이클이 seam 을 정당하게 추가/제거하면 그 사이클이 이 값을 갱신한다.
    """
    cur_src = _CORE.read_text(encoding="utf-8")

    needle = "sys.modules.get"
    cur_n = cur_src.count(needle)

    assert cur_n == _BASELINE_SYS_MODULES_GET_COUNT, (
        f"`{needle}` 출현 수 변동 (기준 {_BASELINE_SHA_SHORT}={_BASELINE_SYS_MODULES_GET_COUNT} "
        f"→ 현재={cur_n}) — no_feed_registry 는 모듈 상단 정적 import 로만 붙인다 "
        "(스펙 §2(a)); 정당한 seam 변경이면 이 리터럴을 갱신한다"
    )


# ===========================================================================
# G-252-3 — 분기 위치: sub_priority 대입 뒤 · retry > MAX 앞
# ===========================================================================
def _no_feed_if_node(func):
    """test 안에 `is_no_feed(` 호출이 있는 `If` 노드."""
    for node in ast.walk(func):
        if not isinstance(node, ast.If):
            continue
        for sub in ast.walk(node.test):
            if isinstance(sub, ast.Call):
                fn = sub.func
                if isinstance(fn, ast.Attribute) and fn.attr == "is_no_feed":
                    return node
                if isinstance(fn, ast.Name) and fn.id == "is_no_feed":
                    return node
    return None


def _require_core_func():
    func = _find_func(_tree(_CORE), _FUNC)
    if func is None:  # pragma: no cover
        pytest.fail(f"`{_FUNC}` 미정의 — {_CORE_REL}")
    return func


def test_g252_3_branch_between_priority_and_retry_compare():
    """분기가 `retry > MAX_STALE_RETRIES` **뒤**로 밀리면 결함이 그대로 남는다.

    - `sub_priority` 대입 **뒤** 여야 HIGH/LOW 판정을 쓸 수 있다(§1 D1 HIGH 무접촉).
    - `retry > MAX` **앞** 이어야 force_retry cooldown/cap/SEND 경로에 아예 진입하지
      않는다(뒤에 두면 r>5 종목이 계속 SEND 를 낸다).
    """
    func = _require_core_func()
    node = _no_feed_if_node(func)
    if node is None:  # pragma: no cover - Red 단계 경로
        pytest.fail(
            f"{_CORE_REL}::{_FUNC} 에 `is_no_feed(...)` 분기 부재 — cycle252 시정 미이행"
        )

    src_lines = _CORE.read_text(encoding="utf-8").splitlines()

    # sub_priority 마지막 대입 라인
    prio_lines = [
        n.lineno for n in ast.walk(func)
        if isinstance(n, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "sub_priority" for t in n.targets)
    ]
    assert prio_lines, "`sub_priority` 대입 부재 (cycle29-R3 우선순위 분리 훼손)"
    last_prio = max(prio_lines)

    # `retry > MAX_STALE_RETRIES` 비교 라인
    cmp_lines = [
        n.lineno for n in ast.walk(func)
        if isinstance(n, ast.Compare)
        and isinstance(n.left, ast.Name) and n.left.id == "retry"
        and any(isinstance(o, ast.Gt) for o in n.ops)
        and any(
            isinstance(c, ast.Name) and c.id == "MAX_STALE_RETRIES"
            for c in n.comparators
        )
    ]
    assert cmp_lines, "`retry > MAX_STALE_RETRIES` 비교 부재"
    first_cmp = min(cmp_lines)

    assert last_prio < node.lineno < first_cmp, (
        "순서 계약 위반. 기대: sub_priority 대입 → no_feed 분기 → retry>MAX 비교. "
        f"actual: priority=L{last_prio} no_feed_if=L{node.lineno} retry_cmp=L{first_cmp}\n"
        + "\n".join(f"  L{i}: {src_lines[i-1]}"
                    for i in sorted({last_prio, node.lineno, first_cmp}))
    )


def test_g252_3b_branch_gated_on_low_priority():
    """분기 조건에 `sub_priority` 와 `"LOW"` 가 있어야 HIGH 가 구조적으로 면제된다.

    조건에서 priority 를 떼면 보유 종목까지 재등록이 끊겨 §1 D1(HIGH byte 동일)이
    무너진다 — 이 사이클이 의도적으로 지불하기로 한 비용의 반대 방향.
    """
    func = _require_core_func()
    node = _no_feed_if_node(func)
    if node is None:  # pragma: no cover
        pytest.fail(f"{_CORE_REL}::{_FUNC} 에 `is_no_feed(...)` 분기 부재")

    test_src = ast.unparse(node.test)
    assert "sub_priority" in test_src, (
        f"분기 조건에 `sub_priority` 부재 — HIGH 도 skip 된다: {test_src!r}"
    )
    assert "'LOW'" in test_src or '"LOW"' in test_src, (
        f"분기 조건에 'LOW' 리터럴 부재: {test_src!r}"
    )


# ===========================================================================
# G-252-4 — 분기 본문 토큰 0 (skip 이 진짜 skip 인가)
# ===========================================================================
_BANNED_IN_BRANCH = (
    "unsubscribe_in_pool",
    "subscribe",
    "_stale_last_resubscribe_at",
    "sleep",
)


def test_g252_4_branch_body_has_no_send_or_stamp_tokens():
    """skip 경로에 SEND·스탬프·sleep 이 되살아나면 이 사이클의 효과가 0 이 된다."""
    func = _require_core_func()
    node = _no_feed_if_node(func)
    if node is None:  # pragma: no cover
        pytest.fail(f"{_CORE_REL}::{_FUNC} 에 `is_no_feed(...)` 분기 부재")

    body_src = "\n".join(ast.unparse(stmt) for stmt in node.body)
    offenders = [tok for tok in _BANNED_IN_BRANCH if tok in body_src]
    assert offenders == [], (
        f"no_feed skip 본문에 금지 토큰 {offenders} 잔존:\n{body_src}"
    )
    assert any(isinstance(n, ast.Continue) for n in ast.walk(node)), (
        f"skip 본문에 `continue` 부재 — 아래 SEND 경로로 흘러간다:\n{body_src}"
    )


def test_g252_4b_branch_holds_retry_counter():
    """`r>5` 홀드(`MAX_STALE_RETRIES + 1`)가 본문에 있어야 universe guard 축출이 산다.

    §1 D2 — `stale_universe_guard._evaluate_universe_guard` 는
    `retries > MAX_STALE_RETRIES ∧ 거래량 < 1만` 으로 저유동 종목을 축출한다.
    """
    func = _require_core_func()
    node = _no_feed_if_node(func)
    if node is None:  # pragma: no cover
        pytest.fail(f"{_CORE_REL}::{_FUNC} 에 `is_no_feed(...)` 분기 부재")

    body_src = "\n".join(ast.unparse(stmt) for stmt in node.body)
    assert "MAX_STALE_RETRIES + 1" in body_src.replace("MAX_STALE_RETRIES+1",
                                                       "MAX_STALE_RETRIES + 1"), (
        "no_feed 분기에 `MAX_STALE_RETRIES + 1` 홀드 부재 — r 무한 climb 또는 "
        f"축출 임계 미달 회귀:\n{body_src}"
    )


# ===========================================================================
# G-252-5 / G-252-5b — 폐기 (2026-09-05 03:4x, cycle252 배포 a375f51 직후)
# 사이클 한정 bare `git diff HEAD` 가드였다. 배포 후 자기소멸했고, 5b 는 전 트리
# 화이트리스트라 다음 사이클(cycle253 `src/routes/realtime.py`)의 워킹트리에서 즉시
# RED 가 되는 클래스(cycle222a `test_a11b_stale_watcher_core_untouched` 선례)다.
# 8영역·scheduler 무접촉은 커밋 8f57bee 의 diff 로 확정됐다 — 리팩토링 리뷰
# `_workspace/refactor/2026-09-05_review.md` 카드 1.
# ===========================================================================


# ===========================================================================
# G-252-6 / G-252-7 — 시간창 리터럴 0 · write_log 0
# ===========================================================================
def _target_files() -> list[tuple[str, Path]]:
    return [(_CORE_REL, _CORE), (_REG_REL, _REG)]


@pytest.mark.parametrize("rel,path", _target_files(), ids=lambda v: str(v))
def test_g252_6_no_new_time_window_literals(rel, path):
    """시각으로 분기하는 코드 밀반입 금지 (스펙 §2 금지 목록).

    no_feed 판정은 **종목 속성**(nxt_tradable)이지 시각이 아니다. 시간창을 끼우는 순간
    cycle241 이 세션 비교로 닫은 15:30~15:40 갭 같은 사각이 다시 생긴다.
    부분 문자열(설명 문장 안의 "09:05~15:20")은 대상이 아니다 — **정확 일치**만 본다.
    """
    if not path.exists():  # pragma: no cover - Red 단계 경로
        pytest.fail(f"cycle252 §2 — `{rel}` 미존재 (Red)")

    tree = _tree(path)
    offenders = [
        f"L{n.lineno}: {n.value!r}"
        for n in ast.walk(tree)
        if isinstance(n, ast.Constant)
        and isinstance(n.value, str)
        and n.value in _TIME_LITERALS
    ]
    assert offenders == [], (
        f"{rel} 에 시간창 리터럴 신설: {offenders}"
    )


@pytest.mark.parametrize("rel,path", _target_files(), ids=lambda v: str(v))
def test_g252_7_no_direct_write_log_calls(rel, path):
    """`write_log` 직접 호출 0 — logger → `_DbLogHandler` 위임 단일 INSERT (cycle72).

    주석 안의 "write_log 제거" 서술은 대상이 아니므로 **식별자(AST)** 로만 센다.
    """
    if not path.exists():  # pragma: no cover - Red 단계 경로
        pytest.fail(f"cycle252 §2 — `{rel}` 미존재 (Red)")

    tree = _tree(path)
    offenders: list[str] = []
    for n in ast.walk(tree):
        if isinstance(n, ast.Name) and n.id == "write_log":
            offenders.append(f"L{n.lineno}: Name write_log")
        elif isinstance(n, ast.Attribute) and n.attr == "write_log":
            offenders.append(f"L{n.lineno}: Attribute .write_log")
        elif isinstance(n, ast.ImportFrom) and any(
            a.name == "write_log" for a in n.names
        ):
            offenders.append(f"L{n.lineno}: from ... import write_log")
    assert offenders == [], (
        f"{rel} 에 write_log 직접 호출/참조 잔존: {offenders}"
    )
