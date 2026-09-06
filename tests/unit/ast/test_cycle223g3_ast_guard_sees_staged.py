"""사이클 223-G3 Red — **8영역 가드가 staged 변경을 못 본다** (MEDIUM, 잔여 4건 중 최중요).

## 결함

두 가드 파일(`test_cycle223_ast_donchian_exit_fix.py` · `test_cycle223f_ast_manual_apply_safeguard.py`)이
워킹트리를 이렇게 봤다:

    subprocess.run(["git", "diff", "--name-only", "--", *_EIGHT_AREAS])   ← unstaged 만

`git diff` 단독은 **인덱스와 워킹트리의 차이**만 본다. 실증: `git add src/engine/risk.py`
후 가드를 돌리면 **2 passed** 로 통과한다. 즉 **커밋하려고 stage 하는 바로 그 순간
안전망이 눈을 감는다** — 가드가 가장 필요한 시점이 정확히 사각이다.

## 결함 2 — 파일명 **영구** 면제

    _PREEXISTING = {"src/engine/risk.py", "src/realtime/handler.py"}

cycle222-a 가 커밋된 뒤에도 그 두 파일은 영원히 무시된다. F2 가 직접 쓴 문장
*"제외 결정이 한쪽 경로에만 걸리면 제외가 아니다"* 가 이 가드에 그대로 적용된다.

## 시정 계약

1. `git diff HEAD` — staged + unstaged 를 **모두** 본다. (같은 파일의 다른 diff
   호출부도 전수 동일 전환: 다른 전략 파일 diff 0 가드 포함.)
2. `git ls-files --others --exclude-standard` — 8영역 **신규(untracked)** 파일도 본다.
   같은 클래스의 사각이고 `git diff` 는 추적 파일만 보기 때문.
3. 면제는 **파일명이 아니라 그 내용 한 벌**(sha256 핀)에 건다. 파일명 면제는 영구지만
   내용 핀은 **자기소멸**한다 — cycle222-a 가 커밋되면 그 경로는 `git diff HEAD` 에
   더 이상 나타나지 않아 면제가 조회조차 되지 않고, 그 뒤 누가 같은 파일을 새로
   건드리면 sha 불일치로 FAIL 한다.

## 갱신 (cycle222-a3 G-2) — 핀 입력이 diff 텍스트 → **파일 내용 바이트**

3번의 sha 입력은 처음에 `git diff` **출력 텍스트**였다. 그 텍스트는 git config 에
따라 코드 변경 없이도 달라진다(실측: `diff.noprefix` / `diff.mnemonicPrefix` /
`diff.srcPrefix` / `diff.context` 전부 불일치). 그래서 입력을 **파일 바이트**로
바꿨다 — git config 전 축에 면역이고 자기소멸 성질은 그대로다
(면제 조회 조건은 여전히 `git diff HEAD --name-only` + `ls-files --others`).
"""

from __future__ import annotations

import ast
import hashlib
import importlib
import re
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_REPO_ROOT = Path(__file__).resolve().parents[3]
_GUARDS = (
    "tests.unit.ast.test_cycle223_ast_donchian_exit_fix",
    "tests.unit.ast.test_cycle223f_ast_manual_apply_safeguard",
)
_GUARD_FILES = (
    _REPO_ROOT / "tests" / "unit" / "ast" / "test_cycle223_ast_donchian_exit_fix.py",
    _REPO_ROOT / "tests" / "unit" / "ast" / "test_cycle223f_ast_manual_apply_safeguard.py",
)


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


# ===========================================================================
# G3-1 (AST) — 모든 `git diff` 호출부가 HEAD 기준 (전수 점검)
# ===========================================================================
@pytest.mark.parametrize("path", _GUARD_FILES, ids=lambda p: p.name)
def test_g3_1_every_git_diff_call_is_head_based(path):
    """`git diff` 리터럴을 전수 훑어 `HEAD` 인자를 강제한다.

    한 호출부만 고치면 다른 호출부가 그대로 staged 를 놓친다 — 8영역 가드와
    '다른 전략 파일 diff 0' 가드 둘 다 같은 사각을 갖고 있었다.
    """
    tree = ast.parse(_read(path))
    seqs: list[tuple[str, list[str]]] = []
    for node in ast.walk(tree):
        # (a) `subprocess.run(["git", "diff", ...])` 직접 리터럴
        if isinstance(node, ast.List):
            elts = [e.value for e in node.elts if isinstance(e, ast.Constant)]
            if elts[:1] == ["git"]:
                seqs.append((ast.unparse(node), elts[1:]))
        # (b) `_git("diff", ...)` 래퍼 경유
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
                and node.func.id == "_git":
            args = [a.value for a in node.args if isinstance(a, ast.Constant)]
            seqs.append((ast.unparse(node), args))
    diff_seqs = [(txt, a) for txt, a in seqs if a[:1] == ["diff"]]
    assert diff_seqs, f"{path.name} 에서 git diff 호출부를 찾지 못했다 (탐지기 결함)"
    for txt, args in diff_seqs:
        assert "HEAD" in args, (
            f"G3: `{txt}` 이 unstaged 만 본다 — "
            "`git add` 하는 순간 가드가 눈을 감는다 (git diff HEAD 로 전환)"
        )


@pytest.mark.parametrize("path", _GUARD_FILES, ids=lambda p: p.name)
def test_g3_2_untracked_files_in_eight_areas_are_seen(path):
    """`git diff` 는 추적 파일만 본다 — 8영역 신규 파일도 감지 대상."""
    src = _read(path)
    assert "ls-files" in src and "--others" in src, (
        "G3: 8영역에 **신규(untracked)** 파일을 떨구면 diff 가드가 통과한다 — "
        "`git ls-files --others --exclude-standard` 동반 필요"
    )


# ===========================================================================
# G3-3 — 면제는 파일명이 아니라 diff 내용(sha) 에 건다
# ===========================================================================
@pytest.mark.parametrize("path", _GUARD_FILES, ids=lambda p: p.name)
def test_g3_3_exemption_is_content_pinned_not_filename_permanent(path):
    src = _read(path)
    assert "_PREEXISTING = {" not in src, (
        "G3: 파일명 집합 면제는 **영구** 다 — cycle222-a 커밋 후에도 두 파일이 "
        "영원히 무시된다. 내용(sha) 핀으로 전환하라"
    )
    assert "_PREEXISTING_CONTENT_SHA" in src, "G3: 내용 핀 상수 부재"
    assert "_PREEXISTING_DIFF_SHA" not in src, (
        "G3/G-2: diff **텍스트** 해시 핀이 남아 있다 — git config 축(diff.noprefix "
        "등)에 코드 변경 없이 깨진다. 파일 내용 바이트 해시로 전환하라"
    )
    shas = re.findall(r'"([0-9a-f]{64})"', src)
    if shas:
        # 핀이 살아 있는 동안에만 사유·해제조건 명시 의무가 걸린다.
        assert "cycle" in src, "G3: 면제 사유(주체) 명시 의무"
        assert "삭제" in src or "비운다" in src, "G3: 해제 조건 명시 의무"
    else:
        # ✅ 빈 dict = **어떤 8영역 변경도 면제되지 않는다** = 가장 강한 상태.
        #    2026-08-22 cycle222-a 커밋(`d2def04`)으로 면제가 자기소멸했다.
        #    기전(내용 해시)은 남기고 값만 비운 것이므로, 상수 자체는 여전히 있어야
        #    한다(위 `_PREEXISTING_CONTENT_SHA in src` 단언). 여기서 추가로 확인할
        #    것은 **빈 상태가 의도된 것인지** — 누가 값만 지우고 사유를 안 남기면
        #    다음 사람이 "핀이 유실됐나" 로 오해한다.
        assert "자기소멸" in src or "비운다" in src, (
            "G3: 핀을 비웠으면 **왜** 비었는지 남겨라 — 값 유실과 구별되지 않는다"
        )


# ===========================================================================
# G3-4 (기능) — staged 변경을 실제로 잡는가 (subprocess monkeypatch)
# ===========================================================================
def _fake_git(monkeypatch, mod, *, name_only_out: str,
              content_by_path: dict | None = None):
    """`git add` 를 흉내내지 않고 git 출력·파일 내용만 갈아끼운다 (워킹트리 오염 0).

    **의미 전환 (cycle222-a3 G-2)** — 구 시그니처는 `diff_out_by_path` 로 `git diff`
    **출력 텍스트**를 갈아끼웠다. 핀 입력이 파일 바이트로 바뀌었으므로 이제
    `_read_bytes` seam 을 갈아끼운다. 검증하려는 성질("면제 파일이라도 내용이
    달라지면 FAIL")은 그대로다.
    """
    class _R:
        def __init__(self, stdout: str):
            self.stdout = stdout
            self.returncode = 0

    def fake_run(cmd, *a, **kw):
        if "ls-files" in cmd:
            return _R("")
        if "--name-only" in cmd:
            return _R(name_only_out)
        return _R("")

    monkeypatch.setattr(mod.subprocess, "run", fake_run)
    if content_by_path is not None:
        monkeypatch.setattr(
            mod, "_read_bytes",
            lambda path: content_by_path.get(path, b""),
        )


@pytest.mark.parametrize("modname", _GUARDS)
def test_g3_4_staged_eight_area_change_fails_the_guard(monkeypatch, modname):
    """stage 된 8영역 파일이 가드를 통과하면 안 된다 (실증된 사각).

    cycle235 견고화 — 내용도 페이크로 갈아끼운다. 승인 사이클 중에는 이 경로가
    `_PREEXISTING_CONTENT_SHA` 에 핀될 수 있고, 그때 "핀과 **동일한** 내용" 은
    승인된 in-flight 상태라 통과가 옳다. 셀프테스트의 의도는 "핀에 없는/핀과
    **다른** staged 변경은 반드시 FAIL" 이므로 내용 상이를 명시적으로 시뮬레이트
    (g3_5 와 같은 `_read_bytes` seam).
    """
    mod = importlib.import_module(modname)
    guard = next(getattr(mod, n) for n in dir(mod) if n.endswith("eight_areas_diff_zero"))
    _fake_git(monkeypatch, mod,
              name_only_out="src/engine/order_engine.py\n",
              content_by_path={"src/engine/order_engine.py": b"# staged change"})
    with pytest.raises(AssertionError):
        guard()


@pytest.mark.parametrize("modname", _GUARDS)
def test_g3_5_exempt_file_with_changed_content_fails_the_guard(monkeypatch, modname):
    """면제 파일이라도 **내용이 달라지면** FAIL — 파일명 영구 면제 금지.

    **의미 전환 (cycle222-a3 G-2)** — 구 이름은 `..._with_changed_diff_...` 였고
    `git diff` 출력 텍스트를 갈아끼웠다. 핀 입력이 파일 바이트로 바뀌어 이름과
    seam 이 함께 이동했다. 검증 성질은 동일하다.
    """
    mod = importlib.import_module(modname)
    guard = next(getattr(mod, n) for n in dir(mod) if n.endswith("eight_areas_diff_zero"))
    _fake_git(monkeypatch, mod,
              name_only_out="src/engine/risk.py\n",
              content_by_path={"src/engine/risk.py": b"# this cycle piled a new change"})
    with pytest.raises(AssertionError):
        guard()


@pytest.mark.parametrize("modname", _GUARDS)
def test_g3_6_untracked_eight_area_file_fails_the_guard(monkeypatch, modname):
    mod = importlib.import_module(modname)
    guard = next(getattr(mod, n) for n in dir(mod) if n.endswith("eight_areas_diff_zero"))

    class _R:
        def __init__(self, stdout: str):
            self.stdout = stdout
            self.returncode = 0   # cycle222-a3 F-G — `_git` 이 rc 를 검사한다

    def fake_run(cmd, *a, **kw):
        if "ls-files" in cmd:
            return _R("src/realtime/new_backdoor.py\n")
        return _R("")

    monkeypatch.setattr(mod.subprocess, "run", fake_run)
    with pytest.raises(AssertionError):
        guard()


# ===========================================================================
# G3-7 — 실제 워킹트리에서 두 가드는 여전히 PASS (현 상태 = cycle222-a 만)
# ===========================================================================
@pytest.mark.parametrize("modname", _GUARDS)
def test_g3_7_guard_passes_on_current_tree(modname):
    mod = importlib.import_module(modname)
    guard = next(getattr(mod, n) for n in dir(mod) if n.endswith("eight_areas_diff_zero"))
    guard()


def test_g3_8_pins_match_current_tree():
    """핀 값이 현 워킹트리 파일 **내용**과 일치한다 (핀 스테일 조기 발견).

    **의미 전환 (cycle222-a3 G-2)** — 비교 대상이 diff 텍스트 해시에서 파일 바이트
    해시로 바뀌었다. `git diff` 는 여전히 "이미 커밋됐는가"(면제 조회 조건) 를
    판정하는 데만 쓴다.
    """
    mod = importlib.import_module(_GUARDS[0])
    for path, pinned in mod._PREEXISTING_CONTENT_SHA.items():
        res = subprocess.run(["git", "diff", "HEAD", "--", path],
                             cwd=_REPO_ROOT, capture_output=True, text=True)
        assert res.returncode == 0, (   # cycle222-a3 F-G — fail-closed
            f"git diff 실패 (rc={res.returncode}) — 빈 stdout 을 '커밋됨' 으로 "
            f"오독하면 핀 스테일 탐지가 조용히 skip 된다. stderr: {res.stderr.strip()}"
        )
        out = res.stdout
        if not out:
            pytest.skip(f"{path} 가 이미 커밋됨 — 면제 항목 삭제 대상")
        assert mod._content_sha(path) == pinned, (
            f"{path} 핀 스테일 — cycle222-a 작업이 갱신됐다면 핀을 재산출하라 "
            f"(`shasum -a 256 {path}`)"
        )


# ===========================================================================
# G3-9 (사이클 263 추가, 영구) — sha 핀 **자매 가드 전수 정합**
# ===========================================================================
#
# 같은 계약(8영역 diff 0 + 내용 sha 면제)을 각자 독립된 dict 로 들고 있는 가드가
# **4개** 다. cycle263 이 한 곳(222a3)에만 핀을 등록한 채 전체 회귀를 돌려
# 7 failed(223 · 223f · 226 + 이 파일의 g3_7 2건 + 고아 cycle262 2건)를 냈다.
# "핀은 항상 N곳" 을 기계가 강제하지 않으면 이 사고는 8영역 승인 사이클마다 재현된다.
#
# 이 가드는 **영구** 다 — 8영역 변경이 없으면 공허하게 통과하고, 있으면 네 곳이
# 같은 값으로 등록됐는지 + 그 값이 현 파일 내용과 일치하는지를 잰다.
# ---------------------------------------------------------------------------
_PIN_GUARD_FILES = (
    "tests/unit/ast/test_cycle222a3_ast_followup_fixes.py",
    "tests/unit/ast/test_cycle223_ast_donchian_exit_fix.py",
    "tests/unit/ast/test_cycle223f_ast_manual_apply_safeguard.py",
    "tests/unit/engine/strategies/test_cycle226_zero_breakout_defense.py",
)
_PIN_DECL_RE = re.compile(r"^_[A-Z0-9_]+_CONTENT_SHA\s*(?::[^=]+)?=\s*\{", re.M)


def _discover_pin_guard_files() -> list[str]:
    """모듈 레벨 `*_CONTENT_SHA = {...}` 선언을 가진 테스트 파일 전수."""
    res = subprocess.run(
        ["git", "grep", "-l", "_CONTENT_SHA", "--", "tests"],
        cwd=_REPO_ROOT, capture_output=True, text=True,
    )
    assert res.returncode in (0, 1), (   # 1 = 매치 없음
        f"git grep 실패 (rc={res.returncode}) — fail-closed. stderr: {res.stderr.strip()}"
    )
    out = []
    for rel in res.stdout.split():
        src = (_REPO_ROOT / rel).read_text(encoding="utf-8")
        if _PIN_DECL_RE.search(src):
            out.append(rel)
    return sorted(out)


def _pin_dict(rel: str) -> dict[str, str]:
    """`*_CONTENT_SHA` dict 리터럴을 AST 로 추출 (import 부작용 없이)."""
    tree = ast.parse((_REPO_ROOT / rel).read_text(encoding="utf-8"))
    for node in tree.body:
        name = None
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            name = node.target.id
        elif (isinstance(node, ast.Assign) and len(node.targets) == 1
              and isinstance(node.targets[0], ast.Name)):
            name = node.targets[0].id
        if name and name.endswith("_CONTENT_SHA") and isinstance(node.value, ast.Dict):
            return {
                k.value: v.value
                for k, v in zip(node.value.keys, node.value.values)
                if isinstance(k, ast.Constant) and isinstance(v, ast.Constant)
            }
    raise AssertionError(f"{rel}: 모듈 레벨 `*_CONTENT_SHA` dict 선언을 찾지 못했다")


def test_g3_9a_pin_guard_file_set_is_complete():
    """자매 가드 목록이 실제 소스와 일치 — 새 가드가 생기면 여기 등록 의무.

    목록이 낡으면 G3-9b 가 새 가드를 검사하지 않아 "핀은 항상 N곳" 이 조용히 헐거워진다.
    """
    found = _discover_pin_guard_files()
    assert found == sorted(_PIN_GUARD_FILES), (
        f"sha 핀 자매 가드 목록 불일치 — 실측 {found} / 등록 {sorted(_PIN_GUARD_FILES)}. "
        "새 가드를 만들었으면 `_PIN_GUARD_FILES` 에 추가하라 (핀은 항상 N곳이다)"
    )


def test_g3_9b_eight_area_changes_are_pinned_in_every_sibling_guard():
    """워킹트리의 8영역 변경은 **네 가드 전부**에 **같은 값**으로 핀돼야 한다.

    한 곳만 등록하면 나머지 셋이 붉어지고(cycle263 실측 7 failed), 그 실패 문구는
    "핀을 재산출하지 마라 — 실제 변경을 되돌려라" 라서 **승인된 8영역 변경을 되돌리도록
    오도한다**. 8영역 변경이 없으면 이 가드는 공허하게 통과한다.
    """
    mod = importlib.import_module("tests.unit.ast.test_cycle222a3_ast_followup_fixes")
    eight_areas = list(mod._EIGHT_AREAS)
    tracked = subprocess.run(
        ["git", "diff", "HEAD", "--name-only", "--", *eight_areas],
        cwd=_REPO_ROOT, capture_output=True, text=True, check=True,
    ).stdout.split()
    untracked = subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard", "--", *eight_areas],
        cwd=_REPO_ROOT, capture_output=True, text=True, check=True,
    ).stdout.split()
    changed = sorted(set(tracked) | set(untracked))
    if not changed:
        return  # 8영역 무접촉 = 이 가드는 공허 (정상)

    pins = {rel: _pin_dict(rel) for rel in _PIN_GUARD_FILES}
    for path in changed:
        actual = hashlib.sha256((_REPO_ROOT / path).read_bytes()).hexdigest()
        missing = sorted(rel for rel, d in pins.items() if path not in d)
        assert missing == [], (
            f"8영역 변경 `{path}` 가 자매 가드 {missing} 에 미등록 — "
            "승인된 8영역 변경이라면 **네 곳 전부**에 같은 값으로 한시 등록하라 "
            "(커밋 직후 네 곳을 함께 비운다). 승인 없는 변경이라면 되돌려라"
        )
        wrong = sorted(rel for rel, d in pins.items() if d[path] != actual)
        assert wrong == [], (
            f"`{path}` 핀 값 불일치 {wrong} — 실제 sha={actual}. "
            "네 가드는 같은 워킹트리를 보므로 값이 갈리면 그 자체가 결함 신호다 "
            f"(`shasum -a 256 {path}`)"
        )
