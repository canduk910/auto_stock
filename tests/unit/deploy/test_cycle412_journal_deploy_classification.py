"""cycle412 Red — 배포 분류 `journal` 축의 **행위** 계약(설계 관찰자안 4절 · 6절 「배포 분류 테스트」).

`tools/deploy/compose_up_changed.sh` 에 `JOURNAL_RE='^journal_worker/'` 축을 더하고 선택 배포 조합을
일반화한다(지금은 `frontend|macro|frontend+macro` 리터럴). 선례 = `test_cycle303_macro_deploy_classification.py`
(픽스처도 이 디렉터리 관례대로 복제한다 — 공유 conftest 를 새로 만들지 않는다).

| # | 계약 |
|---|---|
| J1 | `journal_worker/` 만 변경 → `mode=journal` `reason=journal_only`, `up … --no-deps journal_worker`(backend·frontend·macro 무접촉) |
| J2 | 하위 경로 어디든(Dockerfile·requirements·jw/·ops/·tests/) journal |
| J3 | 조합 — `frontend+journal` · `macro+journal` · `frontend+macro+journal`(축 순서 frontend→macro→journal, 서비스 한 호출) |
| J4 | journal + backend 입력(`src/`·`docker-compose.prod.yml`) → full(backend 축이 항상 이긴다) |
| J5 | `journal_workerx/` 접두 오매칭 = none |
| J6 | 기존 조합 불변 — `frontend+macro` `reason=frontend_and_macro_only` |
| J7 | dry-run — docker 호출 0, 미리보기에 `--no-deps journal_worker` |
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
            "journal_worker/jw/main.py": "j\n",
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



def _no_deps_tail(up: str) -> list[str]:
    toks = up.split()
    return toks[toks.index("--no-deps") + 1:]


def test_j1_journal_only(repo, fake_docker):
    _prime_marker(repo)
    _commit(repo, {"journal_worker/jw/grammar.py": "changed\n"})
    proc, calls = _run(repo, fake_docker)
    assert proc.returncode == 0, proc.stderr
    up = _up_call(calls)
    assert "--build" in up and _no_deps_tail(up) == ["journal_worker"], up
    assert "backend" not in up and "frontend" not in up.split() and "macro" not in up.split(), up
    assert "mode=journal " in proc.stdout and "reason=journal_only" in proc.stdout, proc.stdout


@pytest.mark.parametrize("path", ["journal_worker/Dockerfile", "journal_worker/requirements.txt",
                                  "journal_worker/jw/main.py", "journal_worker/ops/role.sql",
                                  "journal_worker/tests/test_jw_x.py"])
def test_j2_any_journal_subpath(repo, fake_docker, path):
    _prime_marker(repo)
    _commit(repo, {path: "changed\n"})
    proc, calls = _run(repo, fake_docker)
    assert _no_deps_tail(_up_call(calls)) == ["journal_worker"]
    assert "mode=journal " in proc.stdout, proc.stdout


@pytest.mark.parametrize("files,mode,reason,services", [
    ({"frontend/index.html": "c\n", "journal_worker/jw/main.py": "c\n"},
     "frontend+journal", "frontend_and_journal_only", ["frontend", "journal_worker"]),
    ({"macro/main.py": "c\n", "journal_worker/jw/main.py": "c\n"},
     "macro+journal", "macro_and_journal_only", ["macro", "journal_worker"]),
    ({"frontend/index.html": "c\n", "macro/main.py": "c\n", "journal_worker/jw/main.py": "c\n",
      "docs/n.md": "c\n"},
     "frontend+macro+journal", "frontend_and_macro_and_journal_only", ["frontend", "macro", "journal_worker"]),
])
def test_j3_combinations(repo, fake_docker, files, mode, reason, services):
    _prime_marker(repo)
    _commit(repo, files)
    proc, calls = _run(repo, fake_docker)
    assert proc.returncode == 0, proc.stderr
    assert _no_deps_tail(_up_call(calls)) == services
    assert f"mode={mode} " in proc.stdout and f"reason={reason}" in proc.stdout, proc.stdout


@pytest.mark.parametrize("other", ["src/engine/x.py", "docker-compose.prod.yml", "requirements.txt"])
def test_j4_backend_wins(repo, fake_docker, other):
    _prime_marker(repo)
    _commit(repo, {"journal_worker/jw/main.py": "c\n", other: "c\n"})
    proc, calls = _run(repo, fake_docker)
    up = _up_call(calls)
    assert "--build" in up and "--no-deps" not in up, up
    assert "mode=full" in proc.stdout and "reason=backend_inputs_changed" in proc.stdout


def test_j5_prefix_mismatch_is_none(repo, fake_docker):
    _prime_marker(repo)
    _commit(repo, {"journal_workerx/z.py": "c\n", "src_journal_worker/z.py": "c\n"})
    proc, calls = _run(repo, fake_docker)
    up = _up_call(calls)
    assert "--build" not in up and "--no-deps" not in up, up
    assert "mode=none" in proc.stdout


def test_j6_existing_frontend_macro_unchanged(repo, fake_docker):
    _prime_marker(repo)
    _commit(repo, {"frontend/index.html": "c\n", "macro/main.py": "c\n"})
    proc, calls = _run(repo, fake_docker)
    assert _no_deps_tail(_up_call(calls)) == ["frontend", "macro"]
    assert "mode=frontend+macro " in proc.stdout and "reason=frontend_and_macro_only" in proc.stdout


def test_j7_dry_run(repo, fake_docker):
    _prime_marker(repo)
    _commit(repo, {"journal_worker/jw/main.py": "c\n"})
    proc, calls = _run(repo, fake_docker, {"DEPLOY_DRY_RUN": "1"})
    assert proc.returncode == 0, proc.stderr
    assert calls == [], calls
    assert "--no-deps journal_worker" in proc.stdout and "mode=journal " in proc.stdout
