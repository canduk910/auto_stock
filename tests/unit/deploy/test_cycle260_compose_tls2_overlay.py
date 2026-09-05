"""cycle260 Red (G-260-3) — 2단계 오버레이 마커가 배포 명령에 미치는 **행위** 계약.

정적 정합은 `tests/unit/ast/test_cycle260_tls_stage2_assets.py` 가 본다. 여기서는 cycle248/255
와 같은 방식으로 임시 git 저장소 + 가짜 `docker` 를 세워 `tools/deploy/compose_up_changed.sh`
가 실제로 어떤 인자를 넘기는지 실증한다(픽스처는 `test_cycle255_compose_tls_overlay.py` 에서
복제 — 세 파일이 같은 스크립트를 서로 다른 축으로 잰다).

■ 계약 — 마커는 **두 개**이고 조합은 네 가지다
1. 둘 다 없음        → cycle248 과 **byte 동일**(`-f prod`).
2. `.tls_enabled` 만  → cycle255 와 **byte 동일**(`-f prod -f tls`). 2단계 준비가 리포에 들어온
                        것만으로 1단계 명령이 달라지면, 준비가 곧 가동이다.
3. 둘 다             → `-f prod -f tls -f tls2` (그 순서). compose 는 **뒤에 오는 파일이 이긴다** —
                        base 위에 1단계를 얹고 그 위에 2단계를 얹는 것이 의도다.
4. `.tls_stage2` 만   → **무시**하고 1과 동일 + 로그 `tls2=ignored_no_tls`.
   443 이 없는데 80 을 https 로 301 하면 사이트가 통째로 접속 불가가 된다(무한 리다이렉트가
   아니라 아예 도달 불가 — 443 을 아무도 듣지 않는다). 그래서 2단계는 1단계에 **종속**이고,
   그 종속을 조용히 삼키지 않고 로그로 말한다(마커는 git 밖이라 리포만 봐서는 안 보인다).
5. `docker-compose.tls2.yml` 변경 → `full`(다른 compose 파일과 동일 — 판정 실수의 비용이 비대칭).
6. 마커는 **모드 판정(full/frontend/none)에 개입하지 않는다** — 개입하면 2단계를 켠 날부터
   모든 배포가 backend 재시작이 되어 cycle248 이 없앤 비용이 부활한다(cycle232 D6 상시 발동).
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

#: 1단계(cycle255) 마커 — 443 오버레이.
TLS_MARKER = ".tls_enabled"
#: 2단계(cycle260) 마커 — 스니펫 디렉터리 오버레이. `.tls_enabled` 와 **함께** 있을 때만 유효.
TLS2_MARKER = ".tls_stage2"
BASE_COMPOSE = "docker-compose.prod.yml"
TLS_COMPOSE = "docker-compose.tls.yml"
TLS2_COMPOSE = "docker-compose.tls2.yml"

#: cycle248 명령 — 마커가 없을 때 **한 글자도** 달라지면 안 된다.
_BASELINE = {
    "full": f"compose -f {BASE_COMPOSE} up --build -d --remove-orphans",
    "frontend": f"compose -f {BASE_COMPOSE} up --build -d --remove-orphans --no-deps frontend",
    "none": f"compose -f {BASE_COMPOSE} up -d --remove-orphans",
}


def _with(chain: str) -> dict[str, str]:
    return {
        mode: cmd.replace(f"compose -f {BASE_COMPOSE} up", f"compose {chain} up")
        for mode, cmd in _BASELINE.items()
    }


#: cycle255 계약 — 1단계만 켠 상태.
_WITH_TLS = _with(f"-f {BASE_COMPOSE} -f {TLS_COMPOSE}")
#: cycle260 계약 — 1·2단계 모두 켠 상태.
_WITH_TLS2 = _with(f"-f {BASE_COMPOSE} -f {TLS_COMPOSE} -f {TLS2_COMPOSE}")

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
            TLS2_COMPOSE: "services: {}\n",
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


def _markers(repo: Path, *names: str) -> None:
    """`touch <marker>` 와 동치 — 내용이 아니라 **존재**가 스위치다."""
    for n in names:
        (repo / n).write_text("", encoding="utf-8")


# ── 조합 1·2·3: 명령 체인 ────────────────────────────────────────────────────

@pytest.mark.parametrize("mode", ["full", "frontend", "none"])
def test_when_both_markers_present_then_three_file_chain_in_order(repo, fake_docker, mode):
    """T-260-1 — 두 마커 → 세 모드 전부 `-f prod -f tls -f tls2`(순서 포함), 그 외는 불변.

    순서가 계약이다 — compose 는 뒤에 오는 파일이 이긴다. 2단계 오버레이가 1단계 앞에 오면
    "1단계 위에 스니펫을 얹는다" 는 의도가 뒤집히고, 병합 결과가 예측 불가가 된다.
    """
    _arrange(repo, mode)
    _markers(repo, TLS_MARKER, TLS2_MARKER)
    proc, calls = _run(repo, fake_docker)
    assert proc.returncode == 0, proc.stderr
    assert _up_call(calls) == _WITH_TLS2[mode], (_up_call(calls), _WITH_TLS2[mode])


@pytest.mark.parametrize("mode", ["full", "frontend", "none"])
def test_when_only_tls_marker_then_cycle255_command_byte_identical(repo, fake_docker, mode):
    """T-260-2 — 1단계 마커만 → cycle255 명령과 **byte 동일**(2단계 파일은 등장조차 안 한다).

    준비 커밋이 리포에 들어온 것만으로 1단계 배포 명령이 달라지면, 그 순간부터 모든 배포가
    검증되지 않은 구성으로 나간다. 준비는 아무것도 바꾸지 않아야 한다.
    """
    _arrange(repo, mode)
    _markers(repo, TLS_MARKER)
    proc, calls = _run(repo, fake_docker)
    assert proc.returncode == 0, proc.stderr
    assert _up_call(calls) == _WITH_TLS[mode], (_up_call(calls), _WITH_TLS[mode])
    assert not any(TLS2_COMPOSE in c for c in calls), calls


@pytest.mark.parametrize("mode", ["full", "frontend", "none"])
def test_when_no_marker_then_cycle248_command_byte_identical(repo, fake_docker, mode):
    """T-260-3 — 마커 0개 → cycle248 명령과 byte 동일(두 오버레이 모두 미등장)."""
    _arrange(repo, mode)
    proc, calls = _run(repo, fake_docker)
    assert proc.returncode == 0, proc.stderr
    assert _up_call(calls) == _BASELINE[mode], (_up_call(calls), _BASELINE[mode])
    assert not any(TLS_COMPOSE in c or TLS2_COMPOSE in c for c in calls), calls


# ── 조합 4: 2단계 마커 단독 = 무시 ───────────────────────────────────────────

@pytest.mark.parametrize("mode", ["full", "frontend", "none"])
def test_when_only_stage2_marker_then_ignored_and_baseline_command(repo, fake_docker, mode):
    """T-260-4 — 2단계 마커 **단독**은 무시하고 기본 명령을 낸다(443 부재 방어).

    443 을 아무도 듣지 않는 상태에서 80 이 https 로 301 하면 사이트가 **도달 불가**가 된다
    (리다이렉트 뒤에 서버가 없다). 마커 파일 하나를 잘못 만든 실수가 전면 장애가 되면 안 되고,
    스크립트가 조용히 켜 주는 것도(1단계 마커를 자동 생성) 안 된다 — 인증서 없이 443 오버레이를
    올리면 nginx 가 기동 실패해 **80 까지 내려간다**.
    """
    _arrange(repo, mode)
    _markers(repo, TLS2_MARKER)
    proc, calls = _run(repo, fake_docker)
    assert proc.returncode == 0, proc.stderr
    assert _up_call(calls) == _BASELINE[mode], (_up_call(calls), _BASELINE[mode])
    assert not any(TLS2_COMPOSE in c for c in calls), calls


def test_when_only_stage2_marker_then_log_says_ignored_no_tls(repo, fake_docker):
    """T-260-5 — 무시할 때 로그가 **왜** 무시했는지 말한다(`tls2=ignored_no_tls`).

    마커는 git 밖 호스트 파일이라 리포만 봐서는 그날 배포가 무엇을 올렸는지 알 수 없다.
    조용히 무시하면 운영자는 "2단계를 켰는데 301 이 안 걸린다" 를 nginx·인증서 쪽에서 찾는다.
    """
    _arrange(repo, "none")
    _markers(repo, TLS2_MARKER)
    proc, _ = _run(repo, fake_docker)
    assert proc.returncode == 0, proc.stderr
    assert "tls2=ignored_no_tls" in proc.stdout, proc.stdout
    assert "tls=off" in proc.stdout, proc.stdout


@pytest.mark.parametrize(
    "markers,expected",
    [
        ((), "tls=off tls2=off"),
        ((TLS_MARKER,), "tls=on tls2=off"),
        ((TLS_MARKER, TLS2_MARKER), "tls=on tls2=on"),
        ((TLS2_MARKER,), "tls=off tls2=ignored_no_tls"),
    ],
    ids=["none", "tls-only", "both", "stage2-only"],
)
def test_when_run_then_mode_line_reports_both_marker_states(repo, fake_docker, markers, expected):
    """T-260-6 — 배포 로그 한 줄이 **두 마커 상태를 모두** 말한다.

    사후 귀인("이 배포부터 https 리다이렉트가 걸렸다"/"끊겼다")의 유일한 단서다. cycle255 가
    넣은 `tls=` 토큰의 서식·위치는 그대로 두고 `tls2=` 를 **뒤에** 붙인다 — 기존 로그를 grep
    하는 절차가 깨지지 않는다.
    """
    _arrange(repo, "none")
    _markers(repo, *markers)
    proc, _ = _run(repo, fake_docker)
    assert proc.returncode == 0, proc.stderr
    assert expected in proc.stdout, proc.stdout


# ── 마커 취급 규약 ───────────────────────────────────────────────────────────

def test_when_stage2_marker_is_empty_file_then_still_enabled(repo, fake_docker):
    """T-260-7 — `touch .tls_stage2` 로 만든 **빈** 마커도 켜짐이다(내용 파싱 금지).

    운영 절차가 `touch` 다. 내용을 읽어 판정하면 그 절차가 조용히 무효가 된다(cycle255 T-255-4
    와 같은 축).
    """
    _arrange(repo, "frontend")
    (repo / TLS_MARKER).write_text("", encoding="utf-8")
    (repo / TLS2_MARKER).write_text("", encoding="utf-8")
    proc, calls = _run(repo, fake_docker)
    assert proc.returncode == 0, proc.stderr
    assert _up_call(calls) == _WITH_TLS2["frontend"], _up_call(calls)


def test_when_markers_at_repo_root_then_found_from_subdirectory(repo, fake_docker):
    """T-260-8 — 하위 디렉터리에서 실행해도 저장소 루트의 두 마커를 본다.

    스크립트는 `cd $(git rev-parse --show-toplevel)` 로 시작한다 — 마커 조회를 상대 경로로
    두면 그 규약을 물려받는다. `$PWD` 기준이면 수동 실행 위치에 따라 2단계가 꺼진 배포가 된다.
    """
    _arrange(repo, "none")
    _markers(repo, TLS_MARKER, TLS2_MARKER)
    proc, calls = _run(repo, fake_docker, cwd=repo / "src")
    assert proc.returncode == 0, proc.stderr
    assert _up_call(calls) == _WITH_TLS2["none"], _up_call(calls)


def test_when_both_markers_present_then_prune_still_last(repo, fake_docker):
    """T-260-9 — 오버레이가 둘 붙어도 `docker image prune -f` 는 up **뒤** 1회 그대로."""
    _arrange(repo, "none")
    _markers(repo, TLS_MARKER, TLS2_MARKER)
    proc, calls = _run(repo, fake_docker)
    assert proc.returncode == 0, proc.stderr
    idx_up = next(i for i, c in enumerate(calls) if " up " in c)
    prunes = [i for i, c in enumerate(calls) if c.startswith("image prune -f")]
    assert prunes == [len(calls) - 1] and prunes[0] > idx_up, calls


# ── 분류 ────────────────────────────────────────────────────────────────────

def test_when_stage2_overlay_file_changed_then_full(repo, fake_docker):
    """T-260-10 — `docker-compose.tls2.yml` 변경 → `full`.

    compose 파일 변경을 `none` 으로 놓치면 **빌드 없는 `up -d`** 가 바뀐 구성을 반영하지
    못하거나 반쯤 반영한다. 판정 실수의 비용이 비대칭이라 compose 파일은 전부 backend 축
    (fail-safe)으로 분류한다 — `docker-compose.prod.yml`·`.tls.yml` 과 같은 취급.
    """
    _arrange(repo, "none")
    _commit(repo, {TLS2_COMPOSE: "services:\n  frontend:\n    volumes: []\n"})
    proc, calls = _run(repo, fake_docker)
    assert proc.returncode == 0, proc.stderr
    up = _up_call(calls)
    assert "--build" in up and "--no-deps" not in up, up
    assert "mode=full" in proc.stdout, proc.stdout


def test_when_snippet_dir_changed_then_frontend_axis_not_backend(repo, fake_docker):
    """T-260-11 (tester F-8 강화) — 스니펫(`tools/ops/tls_stage2/*.conf`) 변경은 frontend 축이다.

    `tools/ops/` 는 운영 스크립트 디렉터리이고 backend 이미지 입력이 아니다(이미지 입력은
    `requirements.txt`·`src/` — cycle248 D-8). 스니펫을 backend 축으로 분류하면 헤더 한 글자를
    고칠 때마다 backend 가 재시작돼 cycle232 D6 가 발동한다. 반대로 `none`(빌드 없는 `up -d`)
    으로 두면 볼륨은 이미 새 파일을 담고 있어도 **실행 중인 nginx 가 옛 설정을 계속 문다**
    (nginx 는 기동·reload 시점에만 읽는다) — 그래서 스니펫 변경은 반드시 `frontend` 모드
    (`--no-deps frontend`, cycle248 실측대로 이미지 동일해도 컨테이너 재생성)를 타야 한다.
    """
    _arrange(repo, "none")
    _commit(repo, {"tools/ops/tls_stage2/tls-loc-hsts.conf": "add_header X 1;\n"})
    proc, calls = _run(repo, fake_docker)
    assert proc.returncode == 0, proc.stderr
    assert "mode=frontend" in proc.stdout, (
        f"스니펫 변경이 frontend 재기동을 유발하지 않는다 — none 이면 옛 nginx 설정이 계속 산다: {proc.stdout}"
    )
    up = _up_call(calls)
    assert up.split()[-1] == "frontend" and "--build" in up, up


@pytest.mark.parametrize(
    "markers", [(TLS_MARKER,), (TLS_MARKER, TLS2_MARKER), (TLS2_MARKER,)],
    ids=["tls-only", "both", "stage2-only"],
)
def test_when_markers_present_then_classification_unaffected(repo, fake_docker, markers):
    """T-260-12 — 마커는 **모드 판정에 개입하지 않는다**(frontend 변경은 여전히 frontend).

    마커가 모드를 full 로 끌어올리면 2단계를 켠 날부터 모든 배포가 backend 재시작이 되어
    cycle232 D6(보유 중 장중 배포 금지)가 상시 발동한다 — cycle248 이 없앤 비용의 부활.
    """
    _arrange(repo, "frontend")
    _markers(repo, *markers)
    proc, calls = _run(repo, fake_docker)
    assert proc.returncode == 0, proc.stderr
    assert "mode=frontend" in proc.stdout, proc.stdout
    assert _up_call(calls).split()[-1] == "frontend", _up_call(calls)


# ── dry-run ─────────────────────────────────────────────────────────────────

def test_when_both_markers_and_dry_run_then_prints_chain_and_touches_nothing(repo, fake_docker):
    """T-260-13 — dry-run 은 세 파일 체인을 **출력만** 하고 docker·마커를 안 건드린다.

    운영자가 EC2 에서 "지금 배포하면 무엇이 뜨는가" 를 미리 보는 경로다(cycle248 T-13).
    2단계 축이 미리보기에서 빠지면 미리보기의 의미가 없다.
    """
    _arrange(repo, "frontend")
    _markers(repo, TLS_MARKER, TLS2_MARKER)
    prev = (repo / ".deployed_sha").read_text(encoding="utf-8").strip()
    proc, calls = _run(repo, fake_docker, {"DEPLOY_DRY_RUN": "1"})
    assert proc.returncode == 0, proc.stderr
    assert calls == [], calls
    assert f"-f {BASE_COMPOSE} -f {TLS_COMPOSE} -f {TLS2_COMPOSE}" in proc.stdout, proc.stdout
    assert (repo / ".deployed_sha").read_text(encoding="utf-8").strip() == prev
    assert not (repo / ".deployed_sha.attempt").exists()


def test_when_stage2_marker_only_and_dry_run_then_no_overlay_in_preview(repo, fake_docker):
    """T-260-14 — 무시되는 2단계 마커는 dry-run 미리보기에도 등장하지 않는다."""
    _arrange(repo, "full")
    _markers(repo, TLS2_MARKER)
    proc, calls = _run(repo, fake_docker, {"DEPLOY_DRY_RUN": "1"})
    assert proc.returncode == 0, proc.stderr
    assert calls == [] and TLS2_COMPOSE not in proc.stdout.replace("tls2=ignored_no_tls", ""), proc.stdout
    assert _BASELINE["full"].replace("compose ", "docker compose ", 1) in proc.stdout, proc.stdout
