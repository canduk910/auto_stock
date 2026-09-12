"""cycle264 — 접촉 범위(C7) + 행위 불변 핀(C4) 가드.

## ⚠️ 이 파일의 절반은 **사이클 한정**이다 — 커밋 후 삭제/갱신 의무

- `test_c7_working_tree_touches_only_allowed_files` (범위 가드)
  → **cycle264 커밋(38f2560) 직후 삭제 완료.** bare `git diff HEAD` 는 커밋 뒤
    공허해지고 다음 편집에서 무조건 RED 가 된다(cycle240 A11b · cycle252 G-252-5b).
- `test_c4_strategy_entry_methods_pinned` (전략 7파일 무접촉 sha 핀)
  → ✅ **cycle272(기준가 시정)가 VB/LTV 를 실제로 바꿨지만 이 핀은 갱신하지
    않았다** — `source` 기본값을 `"ws"`(불신)로 둬 이 여섯 메서드는 손대지
    않는 설계를 택했다(자문 §9 O-I, 예고 문장을 이 사실에 맞춰 정정한다).
    cycle264 안에서 sha 가 바뀌면 계약 위반이다.

나머지(`scheduler.py` 라인 상한, 8영역 무접촉)는 영구 가드다.

## 왜 `git grep`/`git ls-files` 로 소스를 스캔하지 않는가

추적 파일만 보므로 Green 이 새로 만든 미추적 파일을 로컬에서는 못 보고
CI(커밋 후)에서만 잡는다(cycle259 S4b). 소스 스캔은 `Path(...).rglob` + AST 로
한다. 여기서 `git` 을 쓰는 곳은 **워킹트리 diff 범위 판정** 한 곳뿐이고,
그것은 git 없이는 정의되지 않는 질문이다.
"""

from __future__ import annotations

import ast
import hashlib
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parents[3]
_SRC = _ROOT / "src"

# C7 — 이 사이클이 만질 수 있는 소스 파일 (정본)
#
# ⚠️ 3번째 파일 `src/engine/open_price_observe.py` 는 **적대 검증 HIGH 처리로 추가된
#    범위 확대**다(team-leader 보고 대상). 근거: `scheduler.py` 의 실제 강제 상한은
#    계약서가 적은 4,000L 이 아니라 cycle257 이 내린 **3,900L** 이고(정본 =
#    `test_cycle257_ast_dead_code_removed.py::TestA4SchedulerLineCount`), 09:05 대조
#    본체를 scheduler 에 두면 3,979L 로 그 영구 가드가 붉어진다(실측 `1 failed /
#    7,276 passed`). 감축 필요량 80L 은 주석 다이어트로 확보 불가 ⇒ cycle233
#    (`account_risk_watcher`)·cycle259(`log_metrics_collector`) 의 leaf 위임 패턴을
#    답습해 관측 본체만 leaf 로 뺐다. 8영역·전략 파일은 여전히 무접촉이다.
_ALLOWED_SRC = {
    "src/realtime/handler.py",
    "src/engine/scheduler.py",
    "src/engine/open_price_observe.py",
    # 정본 문서 동반 개정 — `src/realtime/**` 글롭이 .md 도 8영역으로 잡으므로
    # 형제 sha 핀 4곳에 함께 등록했다(커밋 후 같이 비운다).
    "src/realtime/CLAUDE.md",
}

# 8영역 (CLAUDE.md 정본) + 이 사이클이 특별히 지키는 파일
_UNTOUCHABLE_GLOBS = (
    "src/engine/risk.py",
    "src/engine/order_engine.py",
    "src/engine/session.py",
    "src/engine/scanner.py",
    "src/engine/strategy_registry.py",
    "src/api/order.py",
)
_UNTOUCHABLE_DIRS = ("src/auth/", "src/realtime/", "src/engine/strategies/")


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=_ROOT, capture_output=True, text=True, check=True,
    ).stdout


# ===========================================================================
# C7 — 접촉 범위 (⚠️ 사이클 한정 — cycle264 커밋 직후 삭제)
# ===========================================================================

def test_c7_scheduler_line_cap():
    """C7 — `scheduler.py` 는 **3,900L** 상한이다(4,000 이 아니다).

    ⚠️ 이 단언이 4,000 이던 동안 cycle264 초안(3,979L)은 여기서 **초록**이면서
    cycle257 의 `test_line_count_below_3900` 을 붉혔다 — 사이클 자체 가드가 진짜
    예산보다 느슨해 위반을 덮은 것이다(적대 검증 HIGH). 두 수가 갈라지면 항상
    **더 조인 쪽**이 정본이다.
    """
    lines = (_SRC / "engine" / "scheduler.py").read_text(encoding="utf-8").count("\n") + 1
    assert lines < 3900, (
        f"scheduler.py {lines}L — 상한 3,900L 초과(cycle257 영구 가드와 동일 예산). "
        "관측 본체는 leaf `src/engine/open_price_observe.py` 로 민다"
    )


def test_c7_scheduler_line_cap_matches_cycle257_guard():
    """C7 — 이 파일의 상한 리터럴이 cycle257 영구 가드의 상한과 **같은 수**여야 한다.

    자체 가드가 리포의 실제 예산보다 느슨해 위반을 초록으로 덮던 그 결함의 재발
    차단이다. cycle257 가드가 상한을 바꾸면 이 테스트가 그 사실을 알린다.
    """
    import re

    mine = _ROOT / "tests" / "unit" / "ast" / "test_cycle264_scope_and_pins.py"
    theirs = _ROOT / "tests" / "unit" / "ast" / "test_cycle257_ast_dead_code_removed.py"
    caps_mine = set(re.findall(r"assert lines < (\d+)", mine.read_text(encoding="utf-8")))
    caps_theirs = set(re.findall(r"assert count < (\d+)", theirs.read_text(encoding="utf-8")))
    assert caps_mine, "cycle264 라인 상한 단언을 찾지 못했다"
    strictest = min(int(c) for c in caps_theirs) if caps_theirs else None
    assert strictest is not None, "cycle257 라인 상한 단언을 찾지 못했다"
    assert min(int(c) for c in caps_mine) <= strictest, (
        f"cycle264 상한({sorted(caps_mine)})이 cycle257 의 가장 조인 상한"
        f"({strictest})보다 느슨하다 — 느슨한 자체 가드는 위반을 초록으로 덮는다"
    )


# ===========================================================================
# C7 — 신규 background task lifecycle (영구, 적대 검증 MEDIUM 처리)
# ===========================================================================

def _create_task_attrs(tree: ast.AST) -> set[str]:
    """`self._X = asyncio.create_task(...)` 의 attribute 전수.

    ⚠️ 이름 패턴(`endswith("_task")`) 으로 거르지 **않는다** — cycle79/83 가드가
    그 제약을 두는 바람에 cycle264 초안의 `_open_source_compare_task_handle` 이
    수집 집합에서 통째로 빠졌고, 세 cancel 목록 어디에도 없는 채로 모든 가드가
    초록이었다(적대 검증 MEDIUM, 속성명을 바꿔도 아무 테스트도 붉어지지 않았다).
    """
    found: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Call):
            continue
        func = node.value.func
        if not (
            isinstance(func, ast.Attribute)
            and func.attr == "create_task"
            and isinstance(func.value, ast.Name)
            and func.value.id == "asyncio"
        ):
            continue
        for target in node.targets:
            if (
                isinstance(target, ast.Attribute)
                and isinstance(target.value, ast.Name)
                and target.value.id == "self"
            ):
                found.add(target.attr)
    return found


def _cancel_tuple_strings(tree: ast.AST, fn_name: str) -> set[str]:
    """`TradingScheduler.<fn_name>` 안 모든 `for ... in (...)` 튜플의 문자열 union."""
    out: set[str] = set()
    for cls in ast.walk(tree):
        if not isinstance(cls, ast.ClassDef) or cls.name != "TradingScheduler":
            continue
        for fn in cls.body:
            if (
                not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef))
                or fn.name != fn_name
            ):
                continue
            for node in ast.walk(fn):
                if isinstance(node, ast.For) and isinstance(node.iter, ast.Tuple):
                    for elt in node.iter.elts:
                        if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                            out.add(elt.value)
    return out


def test_c7_every_create_task_is_cancelled_everywhere():
    """C7 — `create_task` 로 만든 모든 self 속성이 **세 cancel 목록 전부**에 있다.

    세 곳 = `stop()` · `start()` finally · `run_daily()` finally(사이클 13-E-2/79/83
    통일 의무). 좀비 task 는 stop→start 재진입에서 되살아나 같은 본체를 두 번 돌린다.
    """
    tree = ast.parse((_SRC / "engine" / "scheduler.py").read_text(encoding="utf-8"))
    created = _create_task_attrs(tree)
    assert created, "scheduler.py 에서 create_task 대입을 하나도 못 찾았다(수집기 고장)"
    for fn_name in ("stop", "start", "run_daily"):
        missing = created - _cancel_tuple_strings(tree, fn_name)
        assert not missing, (
            f"`TradingScheduler.{fn_name}` 의 task cancel 튜플에 누락: {sorted(missing)}"
        )


def test_c7_open_source_compare_task_registered():
    """C7 — cycle264 task 속성이 관례 이름(`_*_task`)이고 세 목록에 등재됐다."""
    tree = ast.parse((_SRC / "engine" / "scheduler.py").read_text(encoding="utf-8"))
    created = _create_task_attrs(tree)
    assert "_open_source_compare_task" in created, (
        f"cycle264 task 속성명 계약 위반(`_*_task_handle` 은 cycle79 가드에 "
        f"보이지 않는다). 실측={sorted(created)}"
    )
    for fn_name in ("stop", "start", "run_daily"):
        assert "_open_source_compare_task" in _cancel_tuple_strings(tree, fn_name), (
            f"`{fn_name}` cancel 목록 누락"
        )


# ===========================================================================
# C4 — 진입/청산/수량 메서드 무변경 (✅ cycle272 가 확인 — 핀은 불변으로 남았다)
# ===========================================================================

# `ast.get_source_segment` 의 sha256 (2026-09-06 HEAD).
# ⚠️ `ast.dump` 를 쓰지 않는 이유 = 3.12(CI) / 3.13(로컬) 출력이 달라 CI 만 붉어진다
#    (cycle256 G-250-5 · cycle259 S4a 실측).
_STRATEGY_PINS = {
    # 🔁 cycle276 (2026-09-11) — cycle274 가 갱신했던 `check_buy_signal` 2핀을
    # **cycle272 값으로 되돌린다**. 관측 훅이 전략에서 `order_engine.execute_buy`
    # (주문 접수 직후)로 옮겨져 전략 6메서드가 전부 무접촉으로 복귀했기 때문이다 —
    # 그 복귀가 "전략에 죽은 배선이 남지 않았다" 의 유일한 기계적 증거다.
    # 나머지 4핀(`check_exit_signal`/`calc_buy_quantity`)은 처음부터 불변이다.
    # 값-출처 = `ast.get_source_segment` sha256.
    # 🔁 cycle286 (2026-09-12, C2-a) — LTV `check_buy_signal` 이 **다시, 정당하게**
    # 바뀐다(main 보드 15:20 매수 컷 발사점 게이트, 8영역 밖 승인 항목). 이 항목만
    # 현재값으로 재핀한다 — VB `check_buy_signal` 은 이 사이클 무접촉이라 cycle272
    # 값 그대로 남는다. `test_cycle276_ast_order_hook.py::test_c6_1`/`test_c6_4a` 의
    # "cycle272 값으로 복귀" 불변식은 이 항목에 한해 자기소멸했다(그 파일 배너 참조).
    ("volatility_breakout", "VolatilityBreakoutStrategy", "check_buy_signal"):
        "e620ae0d14a71f916550ee13f57edff12e1b84c12b8a4712b29583b44b56f20a",
    ("volatility_breakout", "VolatilityBreakoutStrategy", "check_exit_signal"):
        "86593b038e4cf8121ae47069fb368346edc50d9692b29db4cbdcc8897421b72e",
    ("volatility_breakout", "VolatilityBreakoutStrategy", "calc_buy_quantity"):
        "6d24ef3f3afd211ae6123623075b08320cdc08c9cd48a6db965355305ad4e732",
    # 🔁 2026-09-12 (cycle286 검증 반영) — `[ltv_main_buy_cutoff]` 마커에 `now=` 필드
    # 병기(적대 검증 LOW-3/behavior)로 세그먼트가 다시 바뀌어 재핀했다. 진입 판정
    # 로직·발사점 위치·baseline 계약은 byte 동일이고 로그 포맷 1줄만 늘었다.
    ("long_tail_volatility", "LongTailVolatilityStrategy", "check_buy_signal"):
        "6c70101fe4abc9e5afc7f7e4a47af46ce5ebdf68fd84c2a18e22a46cb4546d1b",
    ("long_tail_volatility", "LongTailVolatilityStrategy", "check_exit_signal"):
        "c8b0e6a8c8705d49bb6f12f82f505d426a5bdeb81413f8b2e0276eabb7dd9cad",
    ("long_tail_volatility", "LongTailVolatilityStrategy", "calc_buy_quantity"):
        "1149ecc8ea37fb1ba164cc1fd88e6525111d5142168ca879f1026c7890905b81",
}


def _method_segment(module: str, cls_name: str, method: str) -> str:
    path = _SRC / "engine" / "strategies" / f"{module}.py"
    src = path.read_text(encoding="utf-8")
    tree = ast.parse(src)
    cls = next(
        n for n in tree.body
        if isinstance(n, ast.ClassDef) and n.name == cls_name
    )
    fn = next(
        n for n in cls.body
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == method
    )
    return ast.get_source_segment(src, fn) or ""


@pytest.mark.parametrize("key", sorted(_STRATEGY_PINS))
def test_c4_strategy_entry_methods_pinned(key):
    """C4 — 같은 입력에 대한 진입/청산/수량 산출이 cycle264 전후 동일하다.

    관측만 넣는 사이클이므로 이 여섯 메서드는 **문자 그대로** 동결이다.
    ✅ cycle272(기준가 시정)가 `on_open_price_confirmed` 의 `source` 기본값을
    `"ws"`(불신)로 둬 이 여섯은 손대지 않았다 — 6/6 불변이 "무접촉 6종"의
    기계적 증거다(자문 §9 O-I, 예고와 달리 핀은 갱신되지 않는다).
    """
    module, cls_name, method = key
    actual = hashlib.sha256(
        _method_segment(module, cls_name, method).encode("utf-8")
    ).hexdigest()
    assert actual == _STRATEGY_PINS[key], (
        f"{module}.{cls_name}.{method} 가 바뀌었다 — cycle264 의 제1 계약은 "
        f"'매매 행위를 한 글자도 바꾸지 않는다' 다. 실측 sha={actual}"
    )


# ===========================================================================
# C7 — realtime 의 다른 파일 / 전략 파일에 cycle264 마커가 새지 않는다 (영구)
# ===========================================================================

_CYCLE264_MARKERS = ("[open_scope_observe]", "[open_source_compare]")


def test_c7_markers_live_only_in_two_files():
    """C7 — cycle264 마커 문자열이 허용된 두 파일 밖에 나타나지 않는다.

    소스 스캔은 `rglob`(미추적 파일 포함) — `git grep` 은 Green 이 새로 만든
    파일을 로컬에서 놓친다(cycle259 S4b).
    """
    offenders: dict[str, list[str]] = {}
    for path in _SRC.rglob("*.py"):
        rel = path.relative_to(_ROOT).as_posix()
        if rel in _ALLOWED_SRC:
            continue
        text = path.read_text(encoding="utf-8")
        hits = [m for m in _CYCLE264_MARKERS if m in text]
        if hits:
            offenders[rel] = hits
    assert not offenders, (
        f"cycle264 관측 마커가 접촉 범위 밖으로 샜다: {offenders}"
    )


def test_c7_no_killswitch_param_introduced():
    """금기 — 이 파일(cycle264 관측)에는 킬스위치 파라미터를 만들지 않는다.

    `open_price_scope_mode` 는 이 금지 목록에서 **빠졌다** — cycle272(기준가
    시정)가 그 이름으로 실제 킬스위치를 `DEFAULT_PARAMS` 에 도입했다(사용자
    결정 D1). 관측 자체의 킬스위치(`open_scope_observe_enabled`·
    `open_source_compare_enabled`)는 여전히 금지다 — 관측은 끄고 켤 대상이
    아니다.
    """
    banned = ("open_scope_observe_enabled", "open_source_compare_enabled")
    offenders: dict[str, list[str]] = {}
    for path in _SRC.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        hits = [b for b in banned if b in text]
        if hits:
            offenders[path.relative_to(_ROOT).as_posix()] = hits
    assert not offenders, (
        f"cycle264 는 관측 전용이다 — 킬스위치/모드 파라미터 금지: {offenders}"
    )
