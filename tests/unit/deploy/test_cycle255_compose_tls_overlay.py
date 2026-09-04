"""cycle255 Red (G-255-4) — TLS 오버레이 마커가 배포 명령에 미치는 **행위** 계약.

정적 정합은 `tests/unit/ast/test_cycle255_tls_assets.py` 가 본다. 여기서는 cycle248 과
같은 방식으로 임시 git 저장소 + 가짜 `docker` 를 세워 `tools/deploy/compose_up_changed.sh`
가 실제로 어떤 인자를 넘기는지 실증한다(픽스처는 `test_cycle248_compose_up_changed.py`
에서 복제 — 두 파일이 같은 스크립트를 서로 다른 축으로 잰다).

■ 계약
1. 마커(`.tls_enabled`, 저장소 루트, git 밖) **없음** → 명령이 현행과 **byte 동일**하다.
   TLS 는 EC2 에서 인증서를 받은 뒤에만 켜진다 — 리포에 오버레이 파일이 들어온 것만으로
   배포 명령이 바뀌면 인증서 없는 상태에서 443 을 열어 frontend 가 통째로 기동 실패한다
   (같은 컨테이너라 **80 까지 내려간다**).
2. 마커 **있음** → 세 모드 전부 `-f docker-compose.prod.yml -f docker-compose.tls.yml`.
   한 호출이라도 오버레이가 빠지면 그 배포가 컨테이너를 443 없는 구성으로 되돌린다 —
   compose 는 "지정된 파일 집합"이 곧 원하는 상태이므로 누락은 조용한 롤백이다.
3. `docker-compose.tls.yml` 변경 → `full`(안전 방향 — 오버레이는 frontend 만 건드리지만
   판정 실수의 비용이 비대칭이다).
4. dry-run 은 마커 유무와 무관하게 docker 를 부르지 않고 마커도 쓰지 않는다.
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

#: TLS 활성 마커 — 호스트 파일 하나가 유일한 스위치다(git 밖, `.env` 무편집).
TLS_MARKER = ".tls_enabled"
BASE_COMPOSE = "docker-compose.prod.yml"
TLS_COMPOSE = "docker-compose.tls.yml"

#: 현행(cycle248) 명령 — 마커가 없을 때 **한 글자도** 달라지면 안 된다.
_BASELINE = {
    "full": f"compose -f {BASE_COMPOSE} up --build -d --remove-orphans",
    "frontend": f"compose -f {BASE_COMPOSE} up --build -d --remove-orphans --no-deps frontend",
    "none": f"compose -f {BASE_COMPOSE} up -d --remove-orphans",
}
#: 마커가 있을 때 — 베이스 뒤에 오버레이 `-f` 가 붙는 것 **말고는** 동일하다.
_WITH_TLS = {
    mode: cmd.replace(
        f"compose -f {BASE_COMPOSE} up", f"compose -f {BASE_COMPOSE} -f {TLS_COMPOSE} up"
    )
    for mode, cmd in _BASELINE.items()
}
#: 모드를 만드는 변경 경로.
_MODE_PATH = {"full": "src/a.py", "frontend": "frontend/index.html", "none": "docs/x.md"}

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
            TLS_COMPOSE: "services: {}\n",
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
    return ups[0]


def _arrange(repo: Path, mode: str) -> None:
    """마커를 직전 커밋으로 두고 `mode` 를 유발하는 변경 1건을 커밋한다."""
    prev = _git(repo, "rev-parse", "HEAD")
    (repo / ".deployed_sha").write_text(prev + "\n", encoding="utf-8")
    _commit(repo, {_MODE_PATH[mode]: "changed\n"})


def _enable_tls(repo: Path, content: str = "") -> None:
    """`touch .tls_enabled` 와 동치 — 내용이 아니라 **존재**가 스위치다."""
    (repo / TLS_MARKER).write_text(content, encoding="utf-8")


# ── 마커 없음 = 현행 byte 동일 ───────────────────────────────────────────────

@pytest.mark.parametrize("mode", ["full", "frontend", "none"])
def test_when_tls_marker_absent_then_compose_command_byte_identical(repo, fake_docker, mode):
    """T-255-1 — 마커 없음 → 세 모드의 명령이 cycle248 과 **완전히 같다**.

    오버레이 파일이 리포에 들어왔다는 사실만으로 배포가 443 을 열면, 인증서가 없는 EC2 에서
    nginx 가 기동 실패해 **80 까지 내려간다**(오버레이는 같은 frontend 컨테이너다).
    """
    _arrange(repo, mode)
    proc, calls = _run(repo, fake_docker)
    assert proc.returncode == 0, proc.stderr
    assert _up_call(calls) == _BASELINE[mode], (_up_call(calls), _BASELINE[mode])
    assert f"mode={mode}" in proc.stdout, proc.stdout


def test_when_tls_marker_absent_then_overlay_never_mentioned(repo, fake_docker):
    """T-255-2 — 마커 없음 → 어떤 docker 호출에도, 로그 어디에도 오버레이 파일이 없다."""
    _arrange(repo, "none")
    proc, calls = _run(repo, fake_docker)
    assert proc.returncode == 0, proc.stderr
    assert not any(TLS_COMPOSE in c for c in calls), calls
    assert TLS_COMPOSE not in proc.stdout, proc.stdout


# ── 마커 있음 = 오버레이 부착 ────────────────────────────────────────────────

@pytest.mark.parametrize("mode", ["full", "frontend", "none"])
def test_when_tls_marker_present_then_overlay_appended_in_order(repo, fake_docker, mode):
    """T-255-3 — 마커 있음 → 세 모드 전부 `-f prod -f tls`(순서 포함), 그 외는 불변.

    순서가 계약이다 — compose 는 **뒤에 오는 파일이 이긴다**. 오버레이가 먼저 오면 base 의
    `ports: ["80:80"]` 이 병합에서 443 을 덮는 방향이 되고, 무엇보다 "base 위에 얹는다"는
    의도가 뒤집힌다.
    """
    _arrange(repo, mode)
    _enable_tls(repo)
    proc, calls = _run(repo, fake_docker)
    assert proc.returncode == 0, proc.stderr
    assert _up_call(calls) == _WITH_TLS[mode], (_up_call(calls), _WITH_TLS[mode])


def test_when_tls_marker_is_empty_file_then_still_enabled(repo, fake_docker):
    """T-255-4 — `touch` 로 만든 **빈** 마커도 켜짐이다(내용 파싱 금지).

    운영 절차가 `touch .tls_enabled` 다. 내용을 읽어 판정하면 그 절차가 조용히 무효가 되고,
    운영자는 "켰는데 443 이 안 뜬다"를 nginx/인증서 쪽에서 찾게 된다.
    """
    _arrange(repo, "frontend")
    _enable_tls(repo, content="")
    proc, calls = _run(repo, fake_docker)
    assert proc.returncode == 0, proc.stderr
    assert _up_call(calls) == _WITH_TLS["frontend"], _up_call(calls)


def test_when_tls_marker_present_then_prune_still_last(repo, fake_docker):
    """T-255-5 — 오버레이가 붙어도 `docker image prune -f` 는 up **뒤** 1회 그대로."""
    _arrange(repo, "none")
    _enable_tls(repo)
    proc, calls = _run(repo, fake_docker)
    assert proc.returncode == 0, proc.stderr
    idx_up = next(i for i, c in enumerate(calls) if " up " in c)
    prunes = [i for i, c in enumerate(calls) if c.startswith("image prune -f")]
    assert prunes == [len(calls) - 1] and prunes[0] > idx_up, calls


def test_when_tls_marker_at_repo_root_then_found_from_subdirectory(repo, fake_docker):
    """T-255-6 — 하위 디렉터리에서 실행해도 저장소 루트의 마커를 본다.

    스크립트는 이미 `cd $(git rev-parse --show-toplevel)` 로 시작한다 — 마커 조회를 상대
    경로로 두면 그 규약을 자동으로 물려받는다. `$PWD` 기준으로 찾으면 수동 실행 위치에
    따라 TLS 가 꺼진 배포가 된다.
    """
    _arrange(repo, "none")
    _enable_tls(repo)
    proc, calls = _run(repo, fake_docker, cwd=repo / "src")
    assert proc.returncode == 0, proc.stderr
    assert _up_call(calls) == _WITH_TLS["none"], _up_call(calls)


@pytest.mark.parametrize("tls_on", [False, True])
def test_when_run_then_mode_line_reports_tls_state(repo, fake_docker, tls_on):
    """T-255-7 — 배포 로그 한 줄이 TLS 상태를 말한다(`tls=on` / `tls=off`).

    마커는 git 밖 호스트 파일이라 **리포만 봐서는 그날 배포가 443 을 올렸는지 알 수 없다**.
    사후 귀인(“이 배포부터 https 가 끊겼다”)의 유일한 단서가 이 토큰이다.
    """
    _arrange(repo, "none")
    if tls_on:
        _enable_tls(repo)
    proc, _ = _run(repo, fake_docker)
    assert proc.returncode == 0, proc.stderr
    expected = "tls=on" if tls_on else "tls=off"
    assert expected in proc.stdout, proc.stdout


# ── 분류 ────────────────────────────────────────────────────────────────────

def test_when_tls_overlay_file_changed_then_full(repo, fake_docker):
    """T-255-8 — `docker-compose.tls.yml` 변경 → `full`.

    오버레이는 frontend 만 정의하지만, compose 파일 변경을 `none` 으로 놓치면 **빌드 없는
    `up -d`** 가 바뀐 구성을 반영하지 못하거나 반쯤 반영한다. 판정 실수의 비용이 비대칭이라
    compose 파일은 전부 backend 축(fail-safe)으로 분류한다 — `docker-compose.prod.yml`
    과 같은 취급.
    """
    _arrange(repo, "none")  # 먼저 마커를 직전 커밋으로 두고
    _commit(repo, {TLS_COMPOSE: "services:\n  frontend:\n    ports: ['443:443']\n"})
    proc, calls = _run(repo, fake_docker)
    assert proc.returncode == 0, proc.stderr
    up = _up_call(calls)
    assert "--build" in up and "--no-deps" not in up, up
    assert "mode=full" in proc.stdout, proc.stdout


def test_when_tls_marker_present_then_classification_unaffected(repo, fake_docker):
    """T-255-9 — 마커는 **모드 판정에 개입하지 않는다**(frontend 변경은 여전히 frontend).

    마커가 모드를 full 로 끌어올리면 TLS 를 켠 날부터 모든 배포가 backend 재시작이 되어
    cycle232 D6(보유 중 장중 배포 금지)가 상시 발동한다 — cycle248 이 없앤 비용의 부활.
    """
    _arrange(repo, "frontend")
    _enable_tls(repo)
    proc, calls = _run(repo, fake_docker)
    assert proc.returncode == 0, proc.stderr
    assert "mode=frontend" in proc.stdout, proc.stdout
    assert _up_call(calls).split()[-1] == "frontend", _up_call(calls)


# ── dry-run ─────────────────────────────────────────────────────────────────

def test_when_tls_marker_and_dry_run_then_prints_overlay_and_touches_nothing(repo, fake_docker):
    """T-255-10 — dry-run 은 오버레이가 붙은 명령을 **출력만** 하고 docker·마커를 안 건드린다.

    운영자가 EC2 에서 "지금 배포하면 무엇이 뜨는가"를 미리 보는 경로다(cycle248 T-13).
    TLS 축이 그 미리보기에서 빠지면 미리보기의 의미가 없다.
    """
    _arrange(repo, "frontend")
    _enable_tls(repo)
    prev = (repo / ".deployed_sha").read_text(encoding="utf-8").strip()
    proc, calls = _run(repo, fake_docker, {"DEPLOY_DRY_RUN": "1"})
    assert proc.returncode == 0, proc.stderr
    assert calls == [], calls
    assert f"-f {BASE_COMPOSE} -f {TLS_COMPOSE}" in proc.stdout, proc.stdout
    assert (repo / ".deployed_sha").read_text(encoding="utf-8").strip() == prev
    assert not (repo / ".deployed_sha.attempt").exists()


def test_when_tls_marker_absent_and_dry_run_then_baseline_command_printed(repo, fake_docker):
    """T-255-11 — 마커 없는 dry-run 출력에도 오버레이가 없다(현행 미리보기 byte 동일 축)."""
    _arrange(repo, "full")
    proc, calls = _run(repo, fake_docker, {"DEPLOY_DRY_RUN": "1"})
    assert proc.returncode == 0, proc.stderr
    assert calls == [] and TLS_COMPOSE not in proc.stdout, proc.stdout
    assert _BASELINE["full"].replace("compose ", "docker compose ", 1) in proc.stdout, proc.stdout
