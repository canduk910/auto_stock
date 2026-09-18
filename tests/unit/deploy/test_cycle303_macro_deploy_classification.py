"""cycle303 — macro_lite 이식 1단계, 배포 분류 macro 축의 **행위** 계약.

`tools/deploy/compose_up_changed.sh` 가 cycle248(backend/frontend/none 3분류)에서
macro 서비스를 추가하며 backend/frontend/macro 3축 + 서비스 목록 일반화로 넓어졌다.
여기서는 그 넓어진 축이 실제로 무엇을 만드는지 가짜 `docker` 로 실증한다(정적 정합은
`tests/unit/ast/test_cycle248_deploy_pipeline.py::test_script_when_modes_then_flags_match_contract`
와 `tests/unit/ast/test_cycle303_macro_isolation.py` 가 본다).

픽스처는 `test_cycle248_compose_up_changed.py`/`test_cycle255_compose_tls_overlay.py` 와
같은 방식으로 이 파일에 복제한다(이 디렉터리의 기존 관례 — 공유 conftest 를 새로 만들지
않는다).

■ 계약
1. `macro/` 만 변경 → `mode=macro`, `up … --no-deps macro`(backend/frontend 무접촉).
2. `frontend/` + `macro/` 만 변경(그 외 축 무변경) → `mode=frontend+macro`,
   `up … --no-deps frontend macro` — **두 서비스가 한 호출에** 실린다.
3. `macro/` + backend 입력(`src/` 등) → `mode=full`(backend 축이 항상 이긴다, cycle248 불변).
4. `macrox/`(접두 오매칭) 변경 → `mode=none` — `MACRO_RE='^macro/'` 가 정확히 앵커돼 있다.
"""
from __future__ import annotations

import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
_SCRIPT = _ROOT / "tools" / "deploy" / "compose_up_changed.sh"

pytestmark = pytest.mark.skipif(
    shutil.which("bash") is None or shutil.which("git") is None,
    reason="bash/git 필요",
)

_LEAKY_PREFIXES = ("GIT_",)
_LEAKY_KEYS = {"DEPLOY_MARKER", "DEPLOY_DRY_RUN", "COMPOSE_FILE_PATH", "FAKE_DOCKER_EXIT"}


def _clean_env() -> dict[str, str]:
    env = {
        k: v for k, v in os.environ.items()
        if not k.startswith(_LEAKY_PREFIXES) and k not in _LEAKY_KEYS
    }
    env["GIT_CONFIG_GLOBAL"] = os.devnull
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    return env


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True, text=True, env=_clean_env()
    ).stdout.strip()


def _commit(repo: Path, files: dict[str, str | None], msg: str = "c") -> str:
    to_add: list[str] = []
    for rel, content in files.items():
        p = repo / rel
        if content is None:
            p.unlink()
            _git(repo, "rm", "-q", "--cached", rel)
            continue
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        to_add.append(rel)
    if to_add:
        _git(repo, "add", "--", *to_add)
    _git(repo, "commit", "-q", "--allow-empty", "-m", msg)
    return _git(repo, "rev-parse", "HEAD")


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    r = tmp_path / "repo"
    r.mkdir()
    _git(r, "init", "-q")
    _git(r, "checkout", "-q", "-b", "main")
    _git(r, "config", "user.email", "t@example.com")
    _git(r, "config", "user.name", "t")
    _git(r, "config", "commit.gpgsign", "false")
    _commit(
        r,
        {
            "README.md": "x\n",
            "src/a.py": "a\n",
            "frontend/index.html": "<x/>\n",
            "macro/main.py": "m\n",
        },
        "init",
    )
    return r


@pytest.fixture
def fake_docker(tmp_path: Path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = tmp_path / "docker.log"
    exe = bin_dir / "docker"
    exe.write_text(
        "#!/usr/bin/env bash\n"
        f'echo "$*" >> "{log}"\n'
        'exit "${FAKE_DOCKER_EXIT:-0}"\n',
        encoding="utf-8",
    )
    exe.chmod(exe.stat().st_mode | stat.S_IEXEC)
    return bin_dir, log


def _run(repo: Path, fake_docker, env_extra: dict[str, str] | None = None):
    bin_dir, log = fake_docker
    env = _clean_env()
    env["PATH"] = f"{bin_dir}{os.pathsep}{env['PATH']}"
    env.update(env_extra or {})
    proc = subprocess.run(
        ["bash", str(_SCRIPT)], cwd=repo, env=env, capture_output=True, text=True
    )
    calls = log.read_text(encoding="utf-8").splitlines() if log.exists() else []
    return proc, calls


def _up_call(calls: list[str]) -> str:
    ups = [c for c in calls if c.startswith("compose ") and " up " in c]
    assert len(ups) == 1, f"compose up 호출이 정확히 1회여야 한다: {calls}"
    up = ups[0]
    assert " -d " in f" {up} " or up.endswith(" -d"), f"`-d` 가 없다: {up}"
    assert "--remove-orphans" in up, f"`--remove-orphans` 가 없다: {up}"
    return up


def _prime_marker(repo: Path) -> str:
    """HEAD 를 마커로 찍어 두어(이미 성공 배포된 상태) 다음 커밋이 diff 판정을 받게 한다."""
    prev = _git(repo, "rev-parse", "HEAD")
    (repo / ".deployed_sha").write_text(prev + "\n", encoding="utf-8")
    return prev


# ── macro 단독 ────────────────────────────────────────────────────────────

def test_when_macro_only_changed_then_macro_mode_no_deps_macro(repo, fake_docker):
    _prime_marker(repo)
    _commit(repo, {"macro/macro_lite/service.py": "changed\n"})
    proc, calls = _run(repo, fake_docker)
    assert proc.returncode == 0, proc.stderr
    up = _up_call(calls)
    assert "--build" in up and "--no-deps" in up, up
    assert up.split()[-1] == "macro", up
    assert "backend" not in up and "frontend" not in up, up
    assert "mode=macro" in proc.stdout, proc.stdout


@pytest.mark.parametrize(
    "path",
    ["macro/Dockerfile", "macro/requirements.txt", "macro/data/oas_history_seed.json",
     "macro/tests/test_x.py", "macro/pytest.ini"],
)
def test_when_any_macro_subpath_changed_then_macro_mode(repo, fake_docker, path):
    """MACRO_RE='^macro/' 가 macro/ 밑 어디든 잡는다(하위 경로 한정 누락 방지)."""
    _prime_marker(repo)
    _commit(repo, {path: "changed\n"})
    proc, calls = _run(repo, fake_docker)
    assert proc.returncode == 0, proc.stderr
    up = _up_call(calls)
    assert up.split()[-1] == "macro", up
    assert "mode=macro" in proc.stdout, proc.stdout


# ── frontend + macro 조합 ────────────────────────────────────────────────

def test_when_frontend_and_macro_changed_then_frontend_plus_macro_mode(repo, fake_docker):
    _prime_marker(repo)
    _commit(repo, {"frontend/index.html": "c\n", "macro/main.py": "c2\n"})
    proc, calls = _run(repo, fake_docker)
    assert proc.returncode == 0, proc.stderr
    up = _up_call(calls)
    assert "--build" in up and "--no-deps" in up, up
    tail = up.split()
    # --no-deps 뒤에 두 서비스가 모두 실린다(순서는 frontend, macro — 스크립트의 append 순서).
    idx = tail.index("--no-deps")
    assert tail[idx + 1 :] == ["frontend", "macro"], up
    assert "backend" not in up, up
    assert "mode=frontend+macro" in proc.stdout, proc.stdout


def test_when_frontend_and_macro_and_docs_changed_then_still_frontend_plus_macro(repo, fake_docker):
    """비입력(docs/) 혼합이 서비스 목록을 오염시키지 않는다."""
    _prime_marker(repo)
    _commit(repo, {"frontend/src/x.ts": "c\n", "macro/macro_lite/cache.py": "c\n", "docs/n.md": "c\n"})
    proc, calls = _run(repo, fake_docker)
    up = _up_call(calls)
    tail = up.split()
    idx = tail.index("--no-deps")
    assert tail[idx + 1 :] == ["frontend", "macro"], up
    assert "mode=frontend+macro" in proc.stdout, proc.stdout


# ── macro + backend → full (backend 축이 항상 이긴다) ──────────────────────

def test_when_macro_and_backend_changed_then_full(repo, fake_docker):
    _prime_marker(repo)
    _commit(repo, {"macro/main.py": "c\n", "src/engine/x.py": "c\n"})
    proc, calls = _run(repo, fake_docker)
    up = _up_call(calls)
    assert "--build" in up and "--no-deps" not in up, up
    assert "mode=full" in proc.stdout, proc.stdout
    assert "reason=backend_inputs_changed" in proc.stdout, proc.stdout


def test_when_macro_and_requirements_txt_changed_then_full(repo, fake_docker):
    """backend 이미지 입력(루트 requirements.txt)은 macro/ 와 섞여도 항상 full 이 이긴다."""
    _prime_marker(repo)
    _commit(repo, {"macro/main.py": "c\n", "requirements.txt": "c\n"})
    proc, calls = _run(repo, fake_docker)
    up = _up_call(calls)
    assert "--no-deps" not in up, up
    assert "mode=full" in proc.stdout, proc.stdout


# ── 접두 오매칭 음성 ─────────────────────────────────────────────────────

def test_when_macrox_prefix_changed_then_no_macro_axis_hit(repo, fake_docker):
    """`macrox/` 는 `^macro/` 에 매치하지 않는다 — 어느 이미지 입력도 아니므로 none."""
    _prime_marker(repo)
    _commit(repo, {"macrox/z.py": "c\n"})
    proc, calls = _run(repo, fake_docker)
    up = _up_call(calls)
    assert "--build" not in up and "--no-deps" not in up, up
    assert "mode=none" in proc.stdout, proc.stdout


def test_when_macrox_and_frontend_changed_then_frontend_only(repo, fake_docker):
    """macro 오매칭 경로가 frontend 단독 모드에 macro 를 끼워넣지 않는다."""
    _prime_marker(repo)
    _commit(repo, {"macrox/z.py": "c\n", "frontend/index.html": "c\n"})
    proc, calls = _run(repo, fake_docker)
    up = _up_call(calls)
    assert up.split()[-1] == "frontend", up
    assert "macro" not in up.split(), up
    assert "mode=frontend" in proc.stdout, proc.stdout


# ── dry-run ──────────────────────────────────────────────────────────────

def test_when_macro_only_and_dry_run_then_no_docker_calls(repo, fake_docker):
    _prime_marker(repo)
    _commit(repo, {"macro/main.py": "c\n"})
    proc, calls = _run(repo, fake_docker, {"DEPLOY_DRY_RUN": "1"})
    assert proc.returncode == 0, proc.stderr
    assert calls == [], calls
    assert "mode=macro" in proc.stdout and "--no-deps macro" in proc.stdout, proc.stdout
