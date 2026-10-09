"""사이클 223-G3 — 8영역 승인 도장이 **모든 변경을 보는가** (메타 가드).

## 지키는 성질 (cycle223 G3 · cycle222-a3 G-2 · cycle263 G3-9 에서 온 것)

1. **staged 변경도 본다** — 옛 가드는 `git diff` 단독이라 `git add` 하는 순간 눈을 감았다.
2. **미추적 새 파일도 본다** — `git diff` 는 추적 파일만 본다.
3. **파일명으로 영구 면제하지 않는다** — 옛 `_PREEXISTING = {risk.py, handler.py}` 는
   두 파일을 영원히 무시했다. 면제·승인은 **그 파일 내용 한 벌(sha256)** 에만 건다.
4. **sha 입력은 파일 바이트다** — diff 텍스트는 git config(diff.noprefix 등)에 따라 코드
   변경 없이 달라진다(cycle222-a3 G-2).
5. **재핀 자리는 한 곳이다** — cycle263 은 자매 가드 네 곳 중 한 곳에만 핀을 넣어
   7 failed 를 냈다. 같은 sha 를 여러 파일에 두지 않는다.

## 정본 (cycle419)

이 성질들은 이제 정본 하나가 진다 — `test_cycle222a3_ast_followup_fixes.py` 의
`_APPROVED_CONTENT_SHA`(8영역 + `scheduler.py` 파일 내용 sha + 승인 사유)와
`_check_pin`·`_check_complete`. 옛 자매 가드 셋(`test_cycle223_*`·`test_cycle223f_*`·
`test_cycle226_*` 의 `git diff HEAD` 기반 8영역 diff-0 가드)은 같은 사실을 네 번 적던
것이라 cycle419 에서 걷었다. 이 파일은 정본이 위 다섯 성질을 **실제로** 갖는지
워킹트리를 건드리지 않고(내용 seam·임시 디렉터리) 확인한다.

정본이 현재 트리에서 초록인지는 정본 자신(`test_ga3_6*`)이 잰다 — 여기서 다시 재면
8영역 변경 하나에 붉은 자리가 둘이 된다.
"""

from __future__ import annotations

import ast
import hashlib
import importlib
import inspect
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_REPO_ROOT = Path(__file__).resolve().parents[3]
_CANON_MOD = "tests.unit.ast.test_cycle222a3_ast_followup_fixes"
_CANON_REL = "tests/unit/ast/test_cycle222a3_ast_followup_fixes.py"
_EMPTY_SHA = hashlib.sha256(b"").hexdigest()


def _canon():
    return importlib.import_module(_CANON_MOD)


_PIN_FUNCS = ("_read_bytes", "_content_sha", "_protected_files_on_disk", "_check_pin",
              "_check_complete")


# ===========================================================================
# G3-1 · G3-2 — 정본은 git 을 거치지 않는다 (staged·unstaged·커밋·미추적 전부를 본다)
# ===========================================================================
@pytest.mark.parametrize("fn_name", _PIN_FUNCS)
def test_g3_1_pin_gate_reads_files_not_git(fn_name):
    """`git diff`/`ls-files` 로 범위를 정하면 staged·미추적·커밋 뒤 변경 중 하나를 놓친다.

    파일 바이트를 직접 읽으면 「어떻게 바뀌었나」 와 무관하게 「지금 내용」 을 잰다.
    """
    import textwrap

    fn = ast.parse(textwrap.dedent(inspect.getsource(getattr(_canon(), fn_name))))
    names = {n.id for n in ast.walk(fn) if isinstance(n, ast.Name)}
    names |= {n.attr for n in ast.walk(fn) if isinstance(n, ast.Attribute)}
    for banned in ("subprocess", "_git", "Popen", "check_output", "system", "popen"):
        assert banned not in names, (
            f"정본 `{fn_name}` 이 `{banned}` 를 쓴다 — git 출력에 기대면 staged/미추적/커밋 뒤 "
            "변경 중 하나가 사각이 된다"
        )
    calls = [n for n in ast.walk(fn) if isinstance(n, ast.Call)]
    assert calls or fn_name == "_read_bytes", f"`{fn_name}` 이 아무것도 호출하지 않는다(탐지기 고장)"


def test_g3_2_untracked_new_file_in_eight_areas_is_seen(tmp_path, monkeypatch):
    """8영역 디렉터리에 새 파일(미추적)이 생기면 정본이 붉다 — 임시 트리로 실증."""
    mod = _canon()
    for rel in mod._APPROVED_CONTENT_SHA:
        dst = tmp_path / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(b"x")
    (tmp_path / "src" / "realtime" / "new_backdoor.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "src" / "realtime" / "__pycache__").mkdir()
    (tmp_path / "src" / "realtime" / "__pycache__" / "handler.cpython-313.pyc").write_bytes(b"c")
    monkeypatch.setattr(mod, "_REPO_ROOT", tmp_path)

    found = mod._protected_files_on_disk()
    assert "src/realtime/new_backdoor.py" in found
    assert not any("__pycache__" in f for f in found), "캐시 파일을 8영역 파일로 세면 안 된다"
    with pytest.raises(AssertionError, match="new_backdoor"):
        mod._check_complete()


def test_g3_2b_deleted_eight_area_file_is_seen(tmp_path, monkeypatch):
    """승인 목록의 파일이 사라져도 붉다(삭제도 변경이다)."""
    mod = _canon()
    paths = sorted(mod._APPROVED_CONTENT_SHA)
    for rel in paths[1:]:
        dst = tmp_path / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(b"x")
    monkeypatch.setattr(mod, "_REPO_ROOT", tmp_path)
    with pytest.raises(AssertionError):
        mod._check_complete()
    with pytest.raises(AssertionError):
        mod._check_pin(paths[0])


# ===========================================================================
# G3-3 — 면제는 파일명이 아니라 내용 한 벌(sha) 에 건다
# ===========================================================================
def test_g3_3_no_filename_exemption_left():
    """파일명 집합 면제(`_ALLOWED`·`_PREEXISTING`)는 **영구**다 — 정본에 남아 있으면 안 된다."""
    mod = _canon()
    for name in ("_ALLOWED", "_PREEXISTING", "_ALLOWED_SRC"):
        assert not hasattr(mod, name), (
            f"정본에 파일명 면제 `{name}` 가 남아 있다 — 그 파일은 영원히 검사되지 않는다"
        )
    for path, (sha, _reason) in mod._APPROVED_CONTENT_SHA.items():
        assert re.fullmatch(r"[0-9a-f]{64}", sha), f"{path}: 내용 sha 가 아니다"


@pytest.mark.parametrize(
    "path",
    ["src/engine/order_engine.py", "src/engine/risk.py", "src/realtime/handler.py",
     "src/engine/scheduler.py", "src/realtime/CLAUDE.md"],
)
def test_g3_4_changed_content_fails_the_pin(monkeypatch, path):
    """내용이 1바이트만 달라도 붉다 — staged 든 unstaged 든 커밋됐든 같다.

    `risk.py`·`handler.py` 는 옛 가드에서 파일명으로 영구 면제되던 두 파일이다(G3 결함 2).
    """
    mod = _canon()
    real = mod._read_bytes
    monkeypatch.setattr(
        mod, "_read_bytes",
        lambda p: real(p) + b"\n# changed" if p == path else real(p),
    )
    with pytest.raises(AssertionError, match="핀을 먼저 재산출하지 마라"):
        mod._check_pin(path)


def test_g3_5_same_content_passes_the_pin():
    """양성 대조군 — 도장과 같은 내용이면 통과한다(위 단언이 무조건 붉은 가짜가 아니다)."""
    mod = _canon()
    path = "src/engine/order_engine.py"
    pinned, _ = mod._APPROVED_CONTENT_SHA[path]
    assert mod._content_sha(path) == hashlib.sha256(mod._read_bytes(path)).hexdigest()
    assert len(pinned) == 64


# ===========================================================================
# G3-9 — 재핀 자리는 **한 곳**이다 (cycle263 7 failed 사고의 구조적 차단)
# ===========================================================================
_PIN_DECL_RE = re.compile(r"^_[A-Z0-9_]+_CONTENT_SHA\s*(?::[^=]+)?=\s*\{", re.M)


def _test_files() -> list[Path]:
    """`tests/` 아래 파이썬 파일 전수 — `rglob`(미추적 파일 포함, `git grep` 금지 — cycle259 S4b)."""
    return sorted(
        p for p in (_REPO_ROOT / "tests").rglob("*.py") if "__pycache__" not in p.parts
    )


def test_g3_9a_only_the_canonical_file_declares_a_content_sha_registry():
    """모듈 레벨 `*_CONTENT_SHA = {...}` 승인 도장 dict 는 정본 한 파일에만 있다."""
    found = sorted(
        p.relative_to(_REPO_ROOT).as_posix()
        for p in _test_files()
        if _PIN_DECL_RE.search(p.read_text(encoding="utf-8"))
    )
    assert found == [_CANON_REL], (
        f"승인 도장 dict 가 정본 밖에도 있다: {found}. 8영역 sha 는 "
        f"`{_CANON_REL}::_APPROVED_CONTENT_SHA` 한 곳에만 둔다"
    )


def test_g3_9b_no_other_test_file_copies_a_protected_file_sha():
    """정본의 sha 값(빈 파일 sha 제외)이 다른 테스트 파일에 문자열로 나오지 않는다.

    복사본이 하나라도 있으면 8영역 파일 하나를 고칠 때 재핀 자리가 둘이 되고, 하나만
    고친 사람은 「코드를 되돌려라」 문구를 만나 승인된 변경을 되돌리게 된다(cycle263).
    """
    mod = _canon()
    shas = {sha for sha, _ in mod._APPROVED_CONTENT_SHA.values()} - {_EMPTY_SHA}
    offenders: dict[str, list[str]] = {}
    for p in _test_files():
        rel = p.relative_to(_REPO_ROOT).as_posix()
        if rel == _CANON_REL:
            continue
        text = p.read_text(encoding="utf-8")
        hits = sorted(s[:12] for s in shas if s in text)
        if hits:
            offenders[rel] = hits
    assert offenders == {}, (
        f"8영역·scheduler 파일 sha 의 복사본: {offenders} — 정본(`{_CANON_REL}`)을 "
        "import 해서 쓰거나 지운다"
    )


def test_g3_9c_canonical_registry_is_a_literal_dict():
    """정본 dict 는 리터럴이다 — 계산으로 채우면 「현재 내용 = 승인」 이 되어 공허해진다."""
    tree = ast.parse((_REPO_ROOT / _CANON_REL).read_text(encoding="utf-8"))
    for node in tree.body:
        target = None
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            target = node.target.id
        elif isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(
            node.targets[0], ast.Name
        ):
            target = node.targets[0].id
        if target == "_APPROVED_CONTENT_SHA":
            assert isinstance(node.value, ast.Dict), "정본 도장이 dict 리터럴이 아니다"
            for v in node.value.values:
                assert isinstance(v, ast.Tuple) and all(
                    isinstance(e, ast.Constant) for e in v.elts
                ), "도장 값은 (sha 문자열, 사유 문자열) 리터럴이어야 한다"
            return
    raise AssertionError("정본에서 `_APPROVED_CONTENT_SHA` 선언을 찾지 못했다")
