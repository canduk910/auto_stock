"""cycle298 — `_scan_loop` 호출부 2곳의 **인자 배정**을 봉인한다.

명세 정본 = `_workspace/red/cycle298_scan_loop_subscribe_first_spec.md` §2·§3.

배정 자체가 계약이다 — 어느 한쪽이 뒤집히면 결과가 정반대다:

| 생성 지점 | 인자 | 뒤집혔을 때 |
|---|---|---|
| 09:30~15:20 진입(`if now < TIME_KRX_MAIN_BUY_STOP:`) | **인자 없음** | 직전 인라인 `scan_stocks`+`subscribe_filtered_stocks` 와 **이중 스캔** |
| 15:30 POST_NXT 전환(`if self._scan_task is None or self._scan_task.done():`) | **`first_delay=0`** | 15:30~19:50 기동의 **5분 공백 부활** |

⚠️ 명세는 두 지점을 "`run_daily`" 라고 적었지만 **코드 사실은 `TradingScheduler.start()`** 다
(`run_daily` 는 1074~1178 의 일일 드라이버이고 `start()` 를 부른다). 가드는 코드 사실을 따른다.

가드 설계 규약:
- 코드 핀은 `ast.dump` sha 가 아니라 **`ast.get_source_segment` sha** 다
  (파이썬 3.12(CI)/3.13(로컬) 의 `ast.dump` 출력이 갈린다).
- 소스 스캔에 `git grep`/`git ls-files` 를 쓰지 않는다(미추적 파일 사각).
- 배정 판정은 **줄 번호·소스 순서가 아니라 감싸는 `if` 의 조건식**으로 한다
  (구현이 줄을 밀어도 계약은 그대로여야 한다).
"""

from __future__ import annotations

import ast
import hashlib
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_REPO = Path(__file__).resolve().parents[3]
_SCHED_REL = "src/engine/scheduler.py"
_SCHED = _REPO / _SCHED_REL

_SRC = _SCHED.read_text(encoding="utf-8")
_TREE = ast.parse(_SRC)

_GATE_MAIN = "now < TIME_KRX_MAIN_BUY_STOP"           # 09:30~15:20 진입
_GATE_POST = "self._scan_task is None or self._scan_task.done()"  # 15:30 POST_NXT 전환


def _fn(name: str) -> ast.AST:
    for node in ast.walk(_TREE):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    raise AssertionError(f"{_SCHED_REL} 에 `{name}` 이 없다")


def _seg_sha(nodes) -> str:
    text = "\n".join(ast.get_source_segment(_SRC, n) for n in nodes)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _scan_loop_creations(root: ast.AST) -> list[tuple[str, ast.Call]]:
    """`self._scan_loop(...)` 호출을 (감싸는 if 조건식, Call 노드) 로 모은다."""
    out: list[tuple[str, ast.Call]] = []

    def walk(node: ast.AST, gate: str) -> None:
        for child in ast.iter_child_nodes(node):
            next_gate = gate
            if isinstance(child, ast.If):
                test = ast.unparse(child.test)
                for stmt in child.body:
                    walk(stmt, test)
                for stmt in child.orelse:
                    walk(stmt, f"else:{test}")
                continue
            if isinstance(child, ast.Call):
                func = child.func
                if isinstance(func, ast.Attribute) and func.attr == "_scan_loop":
                    out.append((gate, child))
            walk(child, next_gate)

    walk(root, "<top>")
    return out


# ---------------------------------------------------------------------------
# G-298-1 — 시그니처: `first_delay` 는 키워드 전용, 기본값 None
# ---------------------------------------------------------------------------
def test_g298_1_scan_loop_signature_is_keyword_only_with_none_default() -> None:
    fn = _fn("_scan_loop")
    names = [a.arg for a in fn.args.kwonlyargs]
    assert "first_delay" in names, (
        "G-298-1 위반 — `_scan_loop` 에 키워드 전용 `first_delay` 가 없다. "
        f"현재 kwonly={names}, positional={[a.arg for a in fn.args.args]}"
    )
    assert not any(a.arg == "first_delay" for a in fn.args.args), (
        "G-298-1 위반 — `first_delay` 가 위치 인자다. 키워드 전용이어야 오배선이 호출 시점에 걸린다."
    )
    idx = names.index("first_delay")
    default = fn.args.kw_defaults[idx]
    assert isinstance(default, ast.Constant) and default.value is None, (
        "G-298-1 위반 — `first_delay` 기본값이 `None` 이 아니다. "
        f"실측 {ast.unparse(default) if default is not None else '<없음>'}. "
        "기본값이 현행(SCAN_INTERVAL)과 같아야 인자를 안 주는 모든 호출이 byte 동일이다."
    )


# ---------------------------------------------------------------------------
# G-298-2 — 호출부는 정확히 2곳이고, 각 게이트의 배정이 계약이다
# ---------------------------------------------------------------------------
def test_g298_2_start_creates_scan_loop_at_exactly_two_sites() -> None:
    creations = _scan_loop_creations(_fn("start"))
    gates = sorted(g for g, _ in creations)
    assert len(creations) == 2, (
        "G-298-2 위반 — `start()` 안의 `_scan_loop(...)` 생성이 2곳이 아니다. "
        f"실측 {len(creations)}곳, 게이트={gates}"
    )
    assert any(_GATE_MAIN in g for g in gates), (
        f"G-298-2 위반 — `{_GATE_MAIN}` 게이트 아래 생성이 없다. 실측 게이트={gates}"
    )
    assert any(_GATE_POST in g for g in gates), (
        f"G-298-2 위반 — `{_GATE_POST}` 게이트 아래 생성이 없다. 실측 게이트={gates}"
    )


def test_g298_2a_main_entry_site_passes_no_argument() -> None:
    """09:30 진입 지점은 **인자 없음** — 직전 인라인 구독과의 이중 스캔 회피."""
    sites = [c for g, c in _scan_loop_creations(_fn("start")) if _GATE_MAIN in g]
    assert len(sites) == 1, f"G-298-2a 위반 — `{_GATE_MAIN}` 아래 생성이 {len(sites)}곳이다"
    call = sites[0]
    assert not call.args and not call.keywords, (
        "G-298-2a 위반 — 09:30 진입 지점이 `_scan_loop` 에 인자를 준다: "
        f"`{ast.unparse(call)}`. 이 경로는 바로 앞에서 `scan_stocks()` + "
        "`subscribe_filtered_stocks()` 를 이미 동기 실행했으므로, 0 을 주면 같은 "
        "조건검색·구독을 수초 안에 두 번 한다."
    )


def test_g298_2b_post_nxt_site_passes_first_delay_zero() -> None:
    """15:30 POST_NXT 전환 지점은 **`first_delay=0`** — 이 경로엔 선행 구독이 없다."""
    sites = [c for g, c in _scan_loop_creations(_fn("start")) if _GATE_POST in g]
    assert len(sites) == 1, f"G-298-2b 위반 — `{_GATE_POST}` 아래 생성이 {len(sites)}곳이다"
    call = sites[0]
    kw = {k.arg: k.value for k in call.keywords if k.arg}
    assert "first_delay" in kw, (
        "G-298-2b 위반 — 15:30 POST_NXT 전환 지점이 `first_delay` 를 주지 않는다: "
        f"`{ast.unparse(call)}`. 이 경로에는 선행 구독이 하나도 없어 300초 대기가 곧 "
        "15:30~19:50 기동의 5분 시세 공백(= 보유 종목 손절·트레일링 평가 0회)이다."
    )
    value = kw["first_delay"]
    assert isinstance(value, ast.Constant) and value.value == 0, (
        "G-298-2b 위반 — `first_delay` 가 리터럴 0 이 아니다: "
        f"`{ast.unparse(value)}`"
    )
    assert not call.args, (
        f"G-298-2b 위반 — 위치 인자를 쓴다: `{ast.unparse(call)}`"
    )


# ---------------------------------------------------------------------------
# G-298-3 — B5: 15:20<=T<15:30 기동은 15:30 에 구독한다 (순서가 근거다)
# ---------------------------------------------------------------------------
def test_g298_3_post_nxt_creation_follows_wait_until_krx_main_close() -> None:
    """`first_delay=0` 생성은 `_wait_until(TIME_KRX_MAIN_CLOSE)` **뒤**에 있어야 한다.

    이 순서가 명세 §3 B5 의 두 줄을 동시에 성립시킨다:
      - `15:20 <= T < 15:30` 기동 → 15:30 까지 대기 후 구독(공백 = 15:30 − T, 최대 10분)
      - `15:30 <= T < 19:50` 기동 → `_wait_until` 즉시 반환 → 생성 즉시 구독(공백 ≈ 0)
    """
    start = _fn("start")
    wait_line = None
    for node in ast.walk(start):
        if isinstance(node, ast.Call) and "TIME_KRX_MAIN_CLOSE" in ast.unparse(node):
            if isinstance(node.func, ast.Attribute) and node.func.attr == "_wait_until":
                wait_line = node.lineno
                break
    assert wait_line is not None, (
        "G-298-3 위반 — `start()` 에 `_wait_until(TIME_KRX_MAIN_CLOSE)` 가 없다"
    )

    sites = [c for g, c in _scan_loop_creations(start) if _GATE_POST in g]
    assert len(sites) == 1
    assert sites[0].lineno > wait_line, (
        "G-298-3 위반 — `first_delay=0` 생성이 `_wait_until(TIME_KRX_MAIN_CLOSE)` 보다 앞이다. "
        f"생성 L{sites[0].lineno} / 대기 L{wait_line}. 앞으로 옮기면 15:20~15:30 기동이 "
        "15:20 즉시 구독으로 바뀌어 명세 §5 의 잔여 공백 서술이 거짓이 된다."
    )


# ---------------------------------------------------------------------------
# G-298-4 — B7: 19:50 cancel / 20:00 unsubscribe_all 구간 무접촉 (소스 세그먼트 sha 핀)
# ---------------------------------------------------------------------------
_EVENING_SHA = "ee4c9459af252723"


def test_g298_4_evening_shutdown_region_is_untouched() -> None:
    start = _fn("start")
    anchor = "await self._wait_until(TIME_NXT_POST_BUY_STOP)"
    found = None
    for node in ast.walk(start):
        for field in ("body", "orelse", "finalbody"):
            body = getattr(node, field, None)
            if not isinstance(body, list):
                continue
            for i, stmt in enumerate(body):
                if isinstance(stmt, ast.stmt) and ast.unparse(stmt).strip() == anchor:
                    found = (body, i)
                    break
            if found:
                break
        if found:
            break
    assert found is not None, f"G-298-4 위반 — `{anchor}` 를 찾지 못했다"

    body, i0 = found
    j = next(
        (k for k in range(i0, len(body)) if ast.unparse(body[k]).strip() == "await unsubscribe_all()"),
        None,
    )
    assert j is not None, "G-298-4 위반 — `await unsubscribe_all()` 가 같은 블록에 없다"

    actual = _seg_sha(body[i0:j + 1])
    assert actual == _EVENING_SHA, (
        "G-298-4 위반 — 19:50 매수 중단 ~ 20:00 `unsubscribe_all()` 구간이 변경됐다 "
        f"(sha {actual} ≠ {_EVENING_SHA}). cycle298 은 `first_delay` 로 루프 **진입 지연**만 "
        "바꾼다 — 19:50 cancel / 20:00 구독 해제 경로는 무접촉이 계약이다."
    )


# ---------------------------------------------------------------------------
# G-298-5 — B7: TIME_SESSION_START_CUTOFF 기동 거부 경로 무접촉 (소스 세그먼트 sha 핀)
# ---------------------------------------------------------------------------
_CUTOFF_SHA = "b1ee1473d57acd38"


def test_g298_5_session_start_cutoff_is_untouched() -> None:
    start = _fn("start")
    nodes = [
        n for n in ast.walk(start)
        if isinstance(n, ast.If) and "TIME_SESSION_START_CUTOFF" in ast.unparse(n.test)
    ]
    assert len(nodes) == 1, (
        f"G-298-5 위반 — `start()` 의 `TIME_SESSION_START_CUTOFF` 게이트가 {len(nodes)}곳이다"
    )
    actual = _seg_sha(nodes)
    assert actual == _CUTOFF_SHA, (
        "G-298-5 위반 — `TIME_SESSION_START_CUTOFF` 기동 거부 경로가 변경됐다 "
        f"(sha {actual} ≠ {_CUTOFF_SHA}). 20:00 이후 기동 거부는 cycle298 범위 밖이다."
    )


# ---------------------------------------------------------------------------
# G-298-6 — scheduler.py 라인 상한(cycle257 영구 상한 < 3,900)
# ---------------------------------------------------------------------------
def test_g298_6_scheduler_line_cap() -> None:
    lines = len(_SCHED.read_text(encoding="utf-8").splitlines())
    assert lines < 3900, (
        f"G-298-6 위반 — `{_SCHED_REL}` 가 {lines}줄로 영구 상한 3,900 을 넘었다."
    )


# ---------------------------------------------------------------------------
# G-298-7 — 자매 핀 동기: scheduler.py 를 고치면 **전부** 같은 값으로 옮긴다
#
#   `scheduler.py` 는 8영역이 아니지만 지난 10 사이클이 "무접촉" 대리 지표로
#   ① 파일 내용 sha ② 정확 라인 수를 **21곳**에 흩어 핀해 두었다. cycle292 주석의
#   경고가 정본이다 — "한 곳만 넣으면 나머지가 '코드를 되돌려라' 로 붉어져 승인된
#   변경을 되돌리도록 오도한다".
#
#   이 가드는 그 21곳을 한 번에 세어 **하나의 실패 메시지**로 만든다. 값을 느슨하게
#   고치는 것이 아니라, 재핀을 빠뜨린 자리를 이름으로 지목하는 것이 목적이다.
# ---------------------------------------------------------------------------
def _collect_scheduler_pins() -> tuple[dict[str, str], dict[str, int]]:
    sha_pins: dict[str, str] = {}
    line_pins: dict[str, int] = {}
    # 핀은 tests/unit/ast 에만 있지 않다 — tests/unit/engine/test_cycle294_stage3.py
    # 도 `assert lines == <N>` 으로 같은 계보를 핀한다. ast 만 훑으면 그 한 곳이
    # 사각이 되어, 다음 사이클이 이 가드의 지목대로 ast 만 옮겼을 때 engine 쪽이
    # "무접촉 계약 위반" 으로 홀로 붉어진다 — 이 가드가 없애려던 오도 메시지 그것이다.
    _scan_dirs = (
        Path(__file__).resolve().parent,
        Path(__file__).resolve().parents[1] / "engine",
    )
    _seen: set[Path] = set()
    for path in sorted(p for d in _scan_dirs if d.is_dir() for p in d.glob("test_*.py")):
        if path.name == Path(__file__).name or path in _seen:
            continue
        _seen.add(path)
        text = path.read_text(encoding="utf-8")
        if _SCHED_REL not in text:
            continue
        try:
            tree = ast.parse(text)
        except SyntaxError:  # pragma: no cover - 방어
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Dict):
                for key, value in zip(node.keys, node.values):
                    if (
                        isinstance(key, ast.Constant) and key.value == _SCHED_REL
                        and isinstance(value, ast.Constant)
                        and isinstance(value.value, str) and len(value.value) == 64
                    ):
                        sha_pins[f"{path.name}:{key.lineno}"] = value.value
            if isinstance(node, ast.Assign):
                for tgt in node.targets:
                    if (
                        isinstance(tgt, ast.Name) and tgt.id == "_SCHEDULER_LINES"
                        and isinstance(node.value, ast.Constant)
                        and isinstance(node.value.value, int)
                    ):
                        line_pins[f"{path.name}:{node.lineno}"] = node.value.value
            if isinstance(node, ast.Compare) and len(node.ops) == 1 and isinstance(node.ops[0], ast.Eq):
                right = node.comparators[0]
                if (
                    isinstance(right, ast.Constant) and isinstance(right.value, int)
                    and not isinstance(right.value, bool)
                    and 3000 <= right.value < 4000
                    and ast.unparse(node.left) in ("lines", "n")
                ):
                    line_pins[f"{path.name}:{node.lineno}"] = right.value
    return sha_pins, line_pins


def test_g298_7_sibling_scheduler_pins_agree_with_the_file() -> None:
    actual_sha = hashlib.sha256(_SCHED.read_bytes()).hexdigest()
    actual_lines = len(_SCHED.read_text(encoding="utf-8").splitlines())
    sha_pins, line_pins = _collect_scheduler_pins()

    assert sha_pins, "G-298-7 자기검증 실패 — `scheduler.py` 내용 sha 핀을 한 곳도 못 찾았다"
    assert line_pins, "G-298-7 자기검증 실패 — `scheduler.py` 라인 수 핀을 한 곳도 못 찾았다"

    stale_sha = {k: v for k, v in sha_pins.items() if v != actual_sha}
    stale_lines = {k: v for k, v in line_pins.items() if v != actual_lines}

    assert not stale_sha and not stale_lines, (
        "G-298-7 위반 — `scheduler.py` 무접촉 대리 핀이 파일과 어긋난다.\n"
        f"  실측 sha={actual_sha}\n"
        f"  실측 라인={actual_lines}\n"
        f"  낡은 sha 핀 {len(stale_sha)}곳: {sorted(stale_sha)}\n"
        f"  낡은 라인 핀 {len(stale_lines)}곳: {sorted(stale_lines)}\n"
        "cycle292 선례대로 **전부 한 값으로 동시에** 옮긴다 — 한 곳만 고치면 나머지가 "
        "'코드를 되돌려라' 로 붉어져 승인된 변경을 되돌리도록 오도한다."
    )
