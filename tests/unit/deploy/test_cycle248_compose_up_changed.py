"""cycle248 — 선택적 배포 스크립트 `tools/deploy/compose_up_changed.sh` 의 행위 계약.

■ 발단 (2026-09-04 실측)
`deploy.yml` 의 `docker compose up --build -d` 는 Compose v5.1 에서 **이미지 ID 가 동일해도**
`build:` 가 있는 서비스를 전부 재생성한다(빌드가 이미지를 재태그해 LastTagTime 이 컨테이너보다
새로워진다 — EC2 v5.1.3·로컬 v5.1.1 재현). 그래서 프론트·문서만 바꾼 push 도 백엔드를
~100초 tick blind 로 몰았고(13db0d9 19:20 · b985938 09-02 15:48), cycle243 의 "Phase 1 은
무재시작" 전제가 거짓이었다.

■ 계약
- 마커(`.deployed_sha`, 마지막 **성공** 배포 SHA)와 HEAD 의 diff 로 모드를 고른다.
- `full`     : backend 입력(src/ · requirements.txt · Dockerfile · compose · .dockerignore ·
               deploy.yml · tools/deploy/) 변경 → `up --build -d --remove-orphans` (현행 동일)
- `frontend` : frontend/ 만 변경 → `up --build -d --no-deps frontend` (backend 무접촉 — 실측)
- `none`     : 둘 다 아님(docs/tests/_workspace/…) 또는 마커==HEAD(재실행) → `up -d --remove-orphans`
               (빌드 없음 = Running, 재생성 0 — 실측)
- 판정 불가(마커 없음 · 마커 SHA 미지 · diff 실패) → **`full`** (fail-safe = 현행 동작).
- 마커는 compose 가 **성공한 뒤에만** 쓴다. 실패하면 다음 배포가 같은 diff 를 다시 본다.
- 스크립트는 실행 위치의 git 저장소를 본다(테스트는 임시 저장소 + 가짜 `docker` 로 실행).
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
    """호출 환경의 git/배포 변수 누출 차단.

    `GIT_DIR`/`GIT_WORK_TREE` 가 상속되면 임시 저장소 커밋이 **다른 저장소**에 들어가고(적대 검증
    재현), 전역 `core.quotePath=false` 는 quoting 회귀(T-3 한글 경로)를 그 머신에서만 초록으로
    위장한다. 전역/시스템 git 설정을 끊고 배포 스크립트 변수도 걷어낸다.
    """
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
    """files: path → 내용(None 이면 삭제). 커밋 SHA 반환."""
    for rel, content in files.items():
        p = repo / rel
        if content is None:
            p.unlink()
            _git(repo, "rm", "-q", "--cached", rel)
            continue
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        _git(repo, "add", rel)
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
    _commit(r, {"README.md": "x\n", "src/a.py": "a\n", "frontend/index.html": "<x/>\n"}, "init")
    return r


@pytest.fixture
def fake_docker(tmp_path: Path):
    """PATH 앞에 세우는 가짜 `docker` — 호출 인자를 로그에 남기고 FAKE_DOCKER_EXIT 로 종료."""
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


def _run(repo: Path, fake_docker, env_extra: dict[str, str] | None = None, cwd: Path | None = None):
    bin_dir, log = fake_docker
    env = _clean_env()
    env["PATH"] = f"{bin_dir}{os.pathsep}{env['PATH']}"
    env.update(env_extra or {})
    proc = subprocess.run(
        ["bash", str(_SCRIPT)], cwd=cwd or repo, env=env, capture_output=True, text=True
    )
    calls = log.read_text(encoding="utf-8").splitlines() if log.exists() else []
    return proc, calls


def _up_call(calls: list[str]) -> str:
    ups = [c for c in calls if c.startswith("compose ") and " up " in c]
    assert len(ups) == 1, f"compose up 호출이 정확히 1회여야 한다: {calls}"
    up = ups[0]
    # 세 모드 공통 계약 — `-d`(attach 금지: 빠지면 ssh 스텝이 반환하지 않는다) + `--remove-orphans`(현행 유지).
    assert " -d " in f" {up} " or up.endswith(" -d"), f"`-d` 가 없다: {up}"
    assert "--remove-orphans" in up, f"`--remove-orphans` 가 없다: {up}"
    return up


def _attempt(repo: Path) -> str | None:
    p = repo / ".deployed_sha.attempt"
    return p.read_text(encoding="utf-8").strip() if p.exists() else None


def _marker(repo: Path) -> str | None:
    p = repo / ".deployed_sha"
    return p.read_text(encoding="utf-8").strip() if p.exists() else None


# ── 판정 불가 → full ────────────────────────────────────────────────────────

def test_when_marker_missing_then_full_deploy(repo, fake_docker):
    """T-1 — 마커 없음(첫 배포·마커 유실) → 현행과 동일한 전체 `up --build`."""
    proc, calls = _run(repo, fake_docker)
    assert proc.returncode == 0, proc.stderr
    up = _up_call(calls)
    assert "--build" in up and "--no-deps" not in up and not up.rstrip().endswith("frontend")
    assert "mode=full" in proc.stdout and "reason=marker_missing" in proc.stdout


def test_when_marker_unknown_sha_then_full_deploy(repo, fake_docker):
    """T-2 — 마커 SHA 가 저장소에 없음(히스토리 재작성 등) → full."""
    (repo / ".deployed_sha").write_text("0" * 40 + "\n", encoding="utf-8")
    proc, calls = _run(repo, fake_docker)
    assert proc.returncode == 0, proc.stderr
    assert "--build" in _up_call(calls) and "--no-deps" not in _up_call(calls)
    assert "reason=marker_unknown_commit" in proc.stdout


# ── 분류 ────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "path",
    [
        "src/engine/x.py",
        "src/new_dir/deep/y.py",
        "requirements.txt",
        "Dockerfile",
        "docker-compose.prod.yml",
        ".dockerignore",
        ".github/workflows/deploy.yml",
        "tools/deploy/compose_up_changed.sh",
        # git 기본 core.quotePath 가 C-quote("src/\\355…")로 감싸 `^src/` 앵커를 빗나가게 하던 경로들 —
        # 적대 검증이 mode=none 오분류를 재현했다. `-z` 출력엔 quoting 이 없어야 한다.
        "src/한글모듈.py",
        'src/we"ird.py',
        "src/back\\slash.py",
        "src/with space.py",
    ],
)
def test_when_backend_input_changed_then_full(repo, fake_docker, path):
    """T-3 — backend 이미지·구성 입력 또는 배포 로직 자체가 바뀌면 full(양 서비스 재생성)."""
    prev = _git(repo, "rev-parse", "HEAD")
    (repo / ".deployed_sha").write_text(prev + "\n", encoding="utf-8")
    _commit(repo, {path: "changed\n"})
    proc, calls = _run(repo, fake_docker)
    assert proc.returncode == 0, proc.stderr
    up = _up_call(calls)
    assert "--build" in up and "--no-deps" not in up, up
    assert "mode=full" in proc.stdout, proc.stdout


@pytest.mark.parametrize(
    "path",
    ["frontend/index.html", "frontend/src/api/client.ts", "frontend/nginx.conf.template",
     "frontend/Dockerfile", "frontend/CLAUDE.md", "frontend/public/한글자산.svg"],
)
def test_when_only_frontend_changed_then_frontend_no_deps(repo, fake_docker, path):
    """T-4 — frontend/ 만 변경 → `--no-deps frontend` (backend 컨테이너 무접촉)."""
    prev = _git(repo, "rev-parse", "HEAD")
    (repo / ".deployed_sha").write_text(prev + "\n", encoding="utf-8")
    _commit(repo, {path: "changed\n"})
    proc, calls = _run(repo, fake_docker)
    assert proc.returncode == 0, proc.stderr
    up = _up_call(calls)
    assert "--build" in up and "--no-deps" in up and up.split()[-1] == "frontend", up
    assert "mode=frontend" in proc.stdout


@pytest.mark.parametrize(
    "path",
    ["docs/x.md", "tests/unit/test_x.py", "_workspace/y.md", "CLAUDE.md", "README.md",
     "pyproject.toml", "requirements-dev.txt", "supabase/migrations/999_x.sql",
     "tools/test_impact/z.py", "e2e/a.spec.ts", "srcs/not_src.py", "frontendx/not_fe.js",
     ".github/workflows/ci.yml", "docs/한글문서.md"],
)
def test_when_no_image_input_changed_then_reconcile_without_build(repo, fake_docker, path):
    """T-5 — 어느 이미지 입력도 아니면 빌드 없는 `up -d`(Running, 재생성 0).

    `srcs/`·`frontendx/`·`requirements-dev.txt`·`ci.yml` 은 접두 오매칭 함정 — 정규식이
    `^src/`·`^frontend/`·`^requirements\\.txt$`·정확한 워크플로 경로로 앵커돼야 한다.
    """
    prev = _git(repo, "rev-parse", "HEAD")
    (repo / ".deployed_sha").write_text(prev + "\n", encoding="utf-8")
    _commit(repo, {path: "changed\n"})
    proc, calls = _run(repo, fake_docker)
    assert proc.returncode == 0, proc.stderr
    up = _up_call(calls)
    assert "--build" not in up and "--no-deps" not in up, up
    assert "mode=none" in proc.stdout


def test_when_frontend_and_docs_changed_then_frontend(repo, fake_docker):
    """T-6a — frontend + 비입력 혼합 → frontend."""
    prev = _git(repo, "rev-parse", "HEAD")
    (repo / ".deployed_sha").write_text(prev + "\n", encoding="utf-8")
    _commit(repo, {"frontend/index.html": "c\n", "docs/n.md": "c\n", "tests/t.py": "c\n"})
    proc, calls = _run(repo, fake_docker)
    assert "--no-deps" in _up_call(calls) and "mode=frontend" in proc.stdout


def test_when_frontend_and_backend_changed_then_full(repo, fake_docker):
    """T-6b — frontend + backend 혼합 → full(backend 가 하나라도 있으면 전체)."""
    prev = _git(repo, "rev-parse", "HEAD")
    (repo / ".deployed_sha").write_text(prev + "\n", encoding="utf-8")
    _commit(repo, {"frontend/index.html": "c\n", "src/a.py": "c\n"})
    proc, calls = _run(repo, fake_docker)
    up = _up_call(calls)
    assert "--build" in up and "--no-deps" not in up and "mode=full" in proc.stdout


def test_when_backend_file_deleted_then_full(repo, fake_docker):
    """T-7 — 삭제도 변경이다(`--name-only` 가 삭제 경로를 포함해야 한다)."""
    prev = _git(repo, "rev-parse", "HEAD")
    (repo / ".deployed_sha").write_text(prev + "\n", encoding="utf-8")
    _commit(repo, {"src/a.py": None})
    proc, calls = _run(repo, fake_docker)
    assert "mode=full" in proc.stdout, proc.stdout


def test_when_backend_file_renamed_then_full(repo, fake_docker):
    """T-7b — 이름 변경은 양쪽 경로가 모두 잡혀야 한다(`--no-renames`). 여기서는 src 밖으로
    옮겨도 원 경로 `src/a.py` 가 diff 에 남아 full 이어야 한다."""
    prev = _git(repo, "rev-parse", "HEAD")
    (repo / ".deployed_sha").write_text(prev + "\n", encoding="utf-8")
    (repo / "docs").mkdir()
    _git(repo, "mv", "src/a.py", "docs/a.py")
    _git(repo, "commit", "-q", "-m", "mv")
    proc, calls = _run(repo, fake_docker)
    assert "mode=full" in proc.stdout, proc.stdout


def test_when_multiple_commits_since_marker_then_union_of_all(repo, fake_docker):
    """T-8 — 마커 이후 커밋이 여럿이면 **누적** diff 로 판정한다(중간 커밋의 src 변경을 놓치면
    안 된다 — 이전 배포 실패로 마커가 뒤처진 경우가 정확히 이 상황)."""
    prev = _git(repo, "rev-parse", "HEAD")
    (repo / ".deployed_sha").write_text(prev + "\n", encoding="utf-8")
    _commit(repo, {"src/b.py": "b\n"}, "backend change")
    _commit(repo, {"docs/n.md": "n\n"}, "docs only on top")
    proc, calls = _run(repo, fake_docker)
    assert "mode=full" in proc.stdout, proc.stdout


# ── 재실행·마커·실패 ─────────────────────────────────────────────────────────

def test_when_marker_equals_head_then_reconcile_without_build(repo, fake_docker):
    """T-9 — 마커==HEAD(이 SHA 는 이미 성공 배포됨 — 수동 재실행) → 빌드 없는 `up -d`.
    전체 재빌드로 떨어뜨리면 재실행 한 번이 백엔드 재시작이 된다."""
    head = _git(repo, "rev-parse", "HEAD")
    (repo / ".deployed_sha").write_text(head + "\n", encoding="utf-8")
    proc, calls = _run(repo, fake_docker)
    assert proc.returncode == 0, proc.stderr
    assert "--build" not in _up_call(calls)
    assert "mode=none" in proc.stdout and "reason=already_deployed" in proc.stdout


def test_when_compose_succeeds_then_marker_written_to_head(repo, fake_docker):
    """T-10 — 성공 후 마커 = HEAD."""
    prev = _git(repo, "rev-parse", "HEAD")
    (repo / ".deployed_sha").write_text(prev + "\n", encoding="utf-8")
    head = _commit(repo, {"docs/n.md": "n\n"})
    proc, _ = _run(repo, fake_docker)
    assert proc.returncode == 0 and _marker(repo) == head
    assert _attempt(repo) is None, "성공 뒤 시도 마커가 남아 있으면 다음 배포가 불필요한 full"


def test_when_compose_fails_then_nonzero_and_marker_untouched(repo, fake_docker):
    """T-11 — compose 실패 → 비0 종료 + 마커 **불변**(다음 배포가 같은 diff 를 다시 본다)."""
    prev = _git(repo, "rev-parse", "HEAD")
    (repo / ".deployed_sha").write_text(prev + "\n", encoding="utf-8")
    _commit(repo, {"src/a.py": "c\n"})
    proc, calls = _run(repo, fake_docker, {"FAKE_DOCKER_EXIT": "1"})
    assert proc.returncode != 0
    assert _marker(repo) == prev
    assert not any(c.startswith("image prune") for c in calls), "실패 후 prune 까지 진행하면 안 된다"
    head = _git(repo, "rev-parse", "HEAD")
    assert _attempt(repo) == head, "실패한 시도는 시도 마커로 남아야 다음 배포가 full 로 복구한다"


def test_when_previous_attempt_failed_then_full_even_if_tree_unchanged(repo, fake_docker):
    """T-17 — 시도 마커가 남아 있으면(직전 배포 중간 사망) 마커==HEAD 여도 **full**.

    compose 는 실패해도 이미지 태그를 부분 전진시킨다(적대 검증 실측: frontend 빌드 실패 +
    backend 태그는 새 이미지). 그 뒤 revert 로 HEAD 트리가 마커 트리와 같아지면 diff 는 0 인데
    none 의 `up -d` 가 backend 를 main 에 없는 이미지로 교체한다. 시도 마커가 그 구멍을 막는다.
    """
    head = _git(repo, "rev-parse", "HEAD")
    (repo / ".deployed_sha").write_text(head + "\n", encoding="utf-8")
    (repo / ".deployed_sha.attempt").write_text(head + "\n", encoding="utf-8")
    proc, calls = _run(repo, fake_docker)
    assert proc.returncode == 0, proc.stderr
    up = _up_call(calls)
    assert "--build" in up and "--no-deps" not in up
    assert "mode=full" in proc.stdout and "reason=previous_attempt_failed" in proc.stdout
    assert _attempt(repo) is None and _marker(repo) == head


def test_when_missing_marker_and_first_full_deploy_succeeds_then_marker_created(repo, fake_docker):
    """T-12 — 첫 배포(마커 없음)도 성공하면 마커를 만든다(다음부터 선택 배포)."""
    head = _git(repo, "rev-parse", "HEAD")
    proc, _ = _run(repo, fake_docker)
    assert proc.returncode == 0 and _marker(repo) == head


def test_when_dry_run_then_no_docker_calls_and_no_marker_write(repo, fake_docker):
    """T-13 — `DEPLOY_DRY_RUN=1` 은 명령을 출력만 하고 docker 호출·마커 기록을 하지 않는다
    (운영자가 EC2 에서 판정을 미리 볼 때 마커를 오염시키면 안 된다)."""
    prev = _git(repo, "rev-parse", "HEAD")
    (repo / ".deployed_sha").write_text(prev + "\n", encoding="utf-8")
    _commit(repo, {"frontend/index.html": "c\n"})
    proc, calls = _run(repo, fake_docker, {"DEPLOY_DRY_RUN": "1"})
    assert proc.returncode == 0, proc.stderr
    assert calls == [], calls
    assert "--no-deps frontend" in proc.stdout and "mode=frontend" in proc.stdout
    assert _marker(repo) == prev and _attempt(repo) is None


@pytest.mark.parametrize("value", ["true", "TRUE", "yes", "on"])
def test_when_dry_run_spelled_true_then_still_dry(repo, fake_docker, value):
    """T-13b — `true`/`yes`/`on` 도 dry-run 이다. 종전엔 리터럴 `1` 만 인정해 `DEPLOY_DRY_RUN=true`
    가 **실배포 + 마커 기록**이었다(적대 검증 재현) — 장중 '미리보기'가 backend 재시작이 되는 오타."""
    prev = _git(repo, "rev-parse", "HEAD")
    (repo / ".deployed_sha").write_text(prev + "\n", encoding="utf-8")
    _commit(repo, {"src/a.py": "c\n"})
    proc, calls = _run(repo, fake_docker, {"DEPLOY_DRY_RUN": value})
    assert proc.returncode == 0, proc.stderr
    assert calls == [] and _marker(repo) == prev and _attempt(repo) is None


def test_when_dry_run_unknown_value_then_refuses_before_any_action(repo, fake_docker):
    """T-13c — 미지 값(`maybe`)은 exit 2 로 거부 — 아무 docker 호출도, 마커 기록도 없이."""
    prev = _git(repo, "rev-parse", "HEAD")
    (repo / ".deployed_sha").write_text(prev + "\n", encoding="utf-8")
    proc, calls = _run(repo, fake_docker, {"DEPLOY_DRY_RUN": "maybe"})
    assert proc.returncode == 2, (proc.returncode, proc.stderr)
    assert calls == [] and _marker(repo) == prev and _attempt(repo) is None


def test_when_run_from_subdirectory_then_uses_repo_root_marker(repo, fake_docker):
    """T-19 — 하위 디렉터리에서 실행해도 저장소 루트의 마커를 읽고 쓴다(`src/.deployed_sha` 금지)."""
    prev = _git(repo, "rev-parse", "HEAD")
    (repo / ".deployed_sha").write_text(prev + "\n", encoding="utf-8")
    head = _commit(repo, {"docs/n.md": "n\n"})
    proc, calls = _run(repo, fake_docker, cwd=repo / "src")
    assert proc.returncode == 0, proc.stderr
    assert "mode=none" in proc.stdout
    assert _marker(repo) == head and not (repo / "src" / ".deployed_sha").exists()


def test_when_run_then_prune_after_successful_up(repo, fake_docker):
    """T-14 — 성공 경로는 `docker image prune -f` 를 up **뒤에** 1회 호출한다(현행 유지)."""
    proc, calls = _run(repo, fake_docker)
    assert proc.returncode == 0
    idx_up = next(i for i, c in enumerate(calls) if " up " in c)
    prunes = [i for i, c in enumerate(calls) if c.startswith("image prune -f")]
    assert prunes == [len(calls) - 1] and prunes[0] > idx_up, calls


def test_when_run_then_changed_files_are_logged(repo, fake_docker):
    """T-15 — 판정 근거(변경 파일·히트)가 배포 로그에 남는다 — 사후 귀인용."""
    prev = _git(repo, "rev-parse", "HEAD")
    (repo / ".deployed_sha").write_text(prev + "\n", encoding="utf-8")
    _commit(repo, {"frontend/index.html": "c\n", "docs/n.md": "n\n"})
    proc, _ = _run(repo, fake_docker)
    assert "frontend/index.html" in proc.stdout and "changed=2" in proc.stdout


def test_when_many_files_changed_then_no_sigpipe_abort_and_truncated_log(repo, fake_docker):
    """T-16 — 변경 목록이 **파이프 버퍼(64KB)를 넘어도** 스크립트가 끝까지 돈다.

    pipefail 아래서 `printf … | head -40` 은 head 가 40행 뒤 닫힐 때 printf 가 아직 쓰고 있으면
    SIGPIPE(141) → 파이프라인 실패 → `set -e` 중단이다. 출력이 버퍼 안에 다 들어가는 작은 diff 는
    printf 가 먼저 끝나 잠복한다 — 그래서 이 테스트는 긴 경로 2,500개(≈300KB)로 버퍼를 넘긴다.
    로그는 40행에서 자르고 잔여 수를 남긴다. 2,500 파일 중 src 1 → full.
    """
    prev = _git(repo, "rev-parse", "HEAD")
    (repo / ".deployed_sha").write_text(prev + "\n", encoding="utf-8")
    long_dir = "docs/" + "/".join(["very_long_directory_name_segment"] * 3)
    files = {f"{long_dir}/file_{i:04d}.md": "x\n" for i in range(2499)}
    files["src/zz.py"] = "z\n"
    _commit(repo, files)
    proc, calls = _run(repo, fake_docker)
    assert proc.returncode == 0, proc.stderr
    assert "mode=full" in proc.stdout and "changed=2500" in proc.stdout
    assert "(+2460 more)" in proc.stdout, proc.stdout[-500:]
    assert proc.stdout.count("changed: ") == 40
    assert _up_call(calls)
