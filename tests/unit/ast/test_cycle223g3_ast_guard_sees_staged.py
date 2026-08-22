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
    """stage 된 8영역 파일이 가드를 통과하면 안 된다 (실증된 사각)."""
    mod = importlib.import_module(modname)
    guard = next(getattr(mod, n) for n in dir(mod) if n.endswith("eight_areas_diff_zero"))
    _fake_git(monkeypatch, mod, name_only_out="src/engine/order_engine.py\n")
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
