"""cycle255 회귀 (F1·F2·F4 시정) — `tools/ops/tls_enable.sh` 의 **행위** 계약.

정적 정합은 `tests/unit/ast/test_cycle255_tls_assets.py` G-255-5 가 본다. 여기서는 임시 git
저장소 + 가짜 `dig`/`curl`/`sudo`/`certbot`/`docker`/`sleep` 으로 스크립트를 실제로 돌려
어떤 순서로 무엇을 호출하고 어디서 멈추는지를 실증한다(cycle248/255 deploy 테스트와 같은 방식).

■ 계약 (적대 검증 확증 F1·F2·F4)
1. 오버레이 `up` 이 non-zero → 마커 삭제 + **prod 단독 up 을 실행** + exit 1. "80 은 살아있다"
   문구는 그 원복 up 이 성공한 뒤에만 나온다(원복 up 도 실패하면 수동 조치 안내).
2. 오버레이 `up` 이 0 이어도 사후 검증(80 401 ∧ 443 401 ∧ State=running)을 폴링으로 재고,
   하나라도 실패하면 1 과 같은 원복 + exit 1. (`docker compose up -d` 는 크래시 루프여도 0.)
3. probe 디렉터리는 `sudo install -d -o $(id -u)` 로 준비하고 그 뒤에 probe 를 쓴다(F2 —
   root:root `certbot-www` 에서 ubuntu `mkdir -p` 는 EACCES).
4. `certonly` 에 `--deploy-hook`(절대경로 docker + `--project-directory` + 절대경로 -f 둘 +
   `exec -T frontend nginx -s reload`)이 붙고, 전환 뒤 훅 1회 실행 + `certbot renew --dry-run`
   으로 갱신 경로를 검증한다. 갱신 검증 실패는 WARNING 이지 원복이 아니다(exit 0).
5. 사전 점검(DNS·probe·certbot·산출물) 실패는 certbot/docker 를 더 부르지 않고 마커도 없다.
"""
from __future__ import annotations

import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
_SCRIPT = _ROOT / "tools" / "ops" / "tls_enable.sh"

pytestmark = pytest.mark.skipif(
    shutil.which("bash") is None or shutil.which("git") is None or shutil.which("install") is None,
    reason="bash/git/install 필요",
)

MARKER = ".tls_enabled"
BASE = "docker-compose.prod.yml"
TLS = "docker-compose.tls.yml"
DOMAIN = "auto.dkstock.cloud"

_LEAKY_PREFIXES = ("GIT_", "FAKE_", "LE_")


def _clean_env() -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith(_LEAKY_PREFIXES)}
    env["GIT_CONFIG_GLOBAL"] = os.devnull
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    return env


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True, text=True, env=_clean_env()
    ).stdout.strip()


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    r = tmp_path / "repo"
    r.mkdir()
    _git(r, "init", "-q")
    (r / "README.md").write_text("x\n", encoding="utf-8")
    return r


_FAKES = {
    # A 레코드 — 기본은 기대 IP.
    "dig": '#!/usr/bin/env bash\necho "dig $*" >> "$FAKE_LOG"\nprintf \'%s\\n\' "${FAKE_DIG_IP:-3.38.228.74}"\n',
    # curl — URL 로 분기해 `-w %{http_code}` 처럼 코드만 찍는다.
    "curl": (
        "#!/usr/bin/env bash\n"
        'echo "curl $*" >> "$FAKE_LOG"\n'
        'url=""; for a in "$@"; do case "$a" in http://*|https://*) url="$a";; esac; done\n'
        'case "$url" in\n'
        '  *acme-challenge/probe*) printf \'%s\' "${FAKE_PROBE_CODE:-200}" ;;\n'
        '  https://*) printf \'%s\' "${FAKE_HTTPS_CODE:-401}" ;;\n'
        '  http://*) printf \'%s\' "${FAKE_HTTP_CODE:-401}" ;;\n'
        "esac\n"
        "exit 0\n"
    ),
    # sudo — 기록만 하고 그대로 실행(install 은 실제 coreutils, certbot 은 아래 가짜).
    "sudo": '#!/usr/bin/env bash\necho "sudo $*" >> "$FAKE_LOG"\nexec "$@"\n',
    # certbot — certonly 는 LE_LIVE_DIR 에 fullchain.pem 을 만든다(마커 존재 여부도 함께 기록).
    "certbot": (
        "#!/usr/bin/env bash\n"
        'm=0; [ -f .tls_enabled ] && m=1\n'
        'echo "certbot marker=$m $*" >> "$FAKE_LOG"\n'
        'case "$1" in\n'
        "  certonly)\n"
        '    [ "${FAKE_CERTBOT_EXIT:-0}" = "0" ] || exit "${FAKE_CERTBOT_EXIT}"\n'
        '    if [ "${FAKE_CERTBOT_NO_OUTPUT:-0}" = "0" ]; then mkdir -p "$LE_LIVE_DIR" && : > "$LE_LIVE_DIR/fullchain.pem"; fi ;;\n'
        '  renew) exit "${FAKE_RENEW_EXIT:-0}" ;;\n'
        "esac\n"
        "exit 0\n"
    ),
    # docker — compose up/ps/exec 를 흉내 낸다. 호출 시점의 마커 존재 여부를 같이 기록한다.
    "docker": (
        "#!/usr/bin/env bash\n"
        'm=0; [ -f .tls_enabled ] && m=1\n'
        'echo "docker marker=$m $*" >> "$FAKE_LOG"\n'
        'args=" $* "\n'
        'case "$args" in\n'
        '  *" ps "*) printf \'{"Service":"frontend","State":"%s"}\\n\' "${FAKE_FE_STATE:-running}"; exit 0 ;;\n'
        '  *" up "*)\n'
        '    case "$args" in\n'
        '      *"docker-compose.tls.yml"*) exit "${FAKE_TLS_UP_EXIT:-0}" ;;\n'
        '      *) exit "${FAKE_BASE_UP_EXIT:-0}" ;;\n'
        "    esac ;;\n"
        '  *" exec "*) exit "${FAKE_EXEC_EXIT:-0}" ;;\n'
        "esac\n"
        "exit 0\n"
    ),
    # sleep — 폴링 루프를 즉시 돌린다(10×1s 를 기다리지 않는다).
    "sleep": "#!/usr/bin/env bash\nexit 0\n",
}


@pytest.fixture
def fakes(tmp_path: Path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = tmp_path / "calls.log"
    for name, body in _FAKES.items():
        exe = bin_dir / name
        exe.write_text(body, encoding="utf-8")
        exe.chmod(exe.stat().st_mode | stat.S_IEXEC)
    return bin_dir, log


def _run(repo: Path, fakes, env_extra: dict[str, str] | None = None, *, email: str | None = "ops@example.com"):
    bin_dir, log = fakes
    env = _clean_env()
    env["PATH"] = f"{bin_dir}{os.pathsep}{env['PATH']}"
    env["FAKE_LOG"] = str(log)
    env["LE_LIVE_DIR"] = str(repo.parent / "le-live")
    if email is not None:
        env["LE_EMAIL"] = email
    env.update(env_extra or {})
    proc = subprocess.run(["bash", str(_SCRIPT)], cwd=repo, env=env, capture_output=True, text=True)
    calls = log.read_text(encoding="utf-8").splitlines() if log.exists() else []
    return proc, calls


def _ups(calls: list[str]) -> list[str]:
    return [c for c in calls if c.startswith("docker ") and " compose " in c and " up " in c]


def _switch_ups(calls: list[str]) -> list[str]:
    return [c for c in _ups(calls) if TLS in c]


def _rollback_ups(calls: list[str]) -> list[str]:
    return [c for c in _ups(calls) if TLS not in c]


# ── 정상 경로 ──────────────────────────────────────────────────────────────

def test_when_all_green_then_switch_once_no_rollback_and_marker_kept(repo, fakes):
    """E-1 — 전부 정상: 오버레이 up 1회(마커 존재 상태) · 원복 up 0회 · 마커 유지 · exit 0."""
    proc, calls = _run(repo, fakes)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert (repo / MARKER).exists(), "성공 경로에서 마커가 없다"
    switch = _switch_ups(calls)
    assert len(switch) == 1, calls
    assert f"-f {BASE} -f {TLS} up -d --no-deps frontend" in switch[0], switch[0]
    assert "marker=1" in switch[0], "전환 up 시점에 마커가 없다(발급 성공 뒤 마커 → up 순서 위반)"
    assert _rollback_ups(calls) == [], f"성공 경로에서 원복 up 이 돌았다: {_rollback_ups(calls)}"
    assert "완료" in proc.stdout and "WARNING" not in proc.stdout, proc.stdout


def test_when_all_green_then_health_probes_use_loopback_and_sni(repo, fakes):
    """E-2 — 사후 검증 3축이 실제로 호출된다(80 loopback · 443 `--resolve` SNI · compose ps)."""
    proc, calls = _run(repo, fakes)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    http = [c for c in calls if c.startswith("curl ") and "http://127.0.0.1/api/health" in c]
    https = [c for c in calls if c.startswith("curl ") and f"https://{DOMAIN}/api/health" in c]
    ps = [c for c in calls if c.startswith("docker ") and " ps " in c and "frontend" in c]
    assert http and https and ps, calls
    assert f"--resolve {DOMAIN}:443:127.0.0.1" in https[0], https[0]
    assert f"-f {BASE} -f {TLS} ps --format json frontend" in ps[0], ps[0]
    # 세 축이 전환 up 뒤에 온다.
    idx_up = calls.index(_switch_ups(calls)[0])
    assert all(calls.index(c) > idx_up for c in (http[0], https[0], ps[0])), calls


def test_when_certbot_www_missing_then_prepared_with_sudo_install_before_probe(repo, fakes):
    """E-3 (F2) — probe 디렉터리는 `sudo install -d -m 755 -o <uid> -g <gid>` 로 만들고 그 뒤 probe.

    root:root `certbot-www`(prod compose bind mount 가 만든다)에서 ubuntu 의 `mkdir -p` 는
    EACCES 다. sudo 없는 mkdir 이 끼어들면 첫 실행이 certbot 도 부르기 전에 죽는다.
    """
    assert not (repo / "certbot-www").exists()
    proc, calls = _run(repo, fakes)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    installs = [c for c in calls if c.startswith("sudo install -d")]
    assert len(installs) == 1, calls
    line = installs[0]
    assert f"-o {os.getuid()}" in line and f"-g {os.getgid()}" in line and "-m 755" in line, line
    assert line.rstrip().endswith("certbot-www/.well-known/acme-challenge"), line
    probe = next(c for c in calls if c.startswith("curl ") and "acme-challenge/probe" in c)
    assert calls.index(line) < calls.index(probe), "probe 가 디렉터리 준비보다 앞이다"
    assert (repo / "certbot-www" / ".well-known" / "acme-challenge").is_dir()
    assert not (repo / "certbot-www" / ".well-known" / "acme-challenge" / "probe").exists(), "probe 파일이 남았다"


def test_when_certbot_www_exists_then_still_ok(repo, fakes):
    """E-4 — 이미 있는 `certbot-www`(배포가 먼저 만든 경우)도 그대로 진행한다."""
    (repo / "certbot-www").mkdir()
    proc, _ = _run(repo, fakes)
    assert proc.returncode == 0, proc.stdout + proc.stderr


# ── F4: 갱신 훅 ───────────────────────────────────────────────────────────

def test_when_issuing_then_deploy_hook_is_absolute_and_reloads_nginx(repo, fakes):
    """E-5 (F4) — certonly 에 `--deploy-hook` 이 붙고 훅은 cwd/PATH/TTY 무관하게 적힌다.

    certbot 이 renewal conf 에 이 문자열을 영속시킨다 — timer(cwd `/`, root)가 실행하므로
    상대경로 `-f` 나 `docker`(PATH 의존)는 'no configuration file'/command not found 다.
    """
    proc, calls = _run(repo, fakes)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    certonly = next(c for c in calls if c.startswith("certbot ") and " certonly " in c)
    assert "marker=0" in certonly, "certonly 시점에 마커가 이미 있다(발급 성공 뒤 마커 계약 위반)"
    assert "--deploy-hook" in certonly, certonly
    hook = certonly.split("--deploy-hook", 1)[1].strip()
    repo_abs = str(repo.resolve())
    assert hook.startswith(str(next(p for p in [Path(fakes[0]) / "docker"]))), (
        f"훅의 docker 가 절대경로가 아니다: {hook}"
    )
    assert f"--project-directory {repo_abs}" in hook, hook
    assert f"-f {repo_abs}/{BASE} -f {repo_abs}/{TLS}" in hook, hook
    assert hook.endswith("exec -T frontend nginx -s reload"), hook
    assert f"-w {repo_abs}/certbot-www" in certonly, f"webroot 가 절대경로가 아니다: {certonly}"
    assert "--standalone" not in certonly


def test_when_switched_then_hook_executed_once_and_renew_dry_run_after(repo, fakes):
    """E-6 (F4) — 전환 뒤 reload 훅을 1회 실행하고 `certbot renew --dry-run` 을 돌린다(그 순서)."""
    proc, calls = _run(repo, fakes)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    execs = [c for c in calls if c.startswith("docker ") and " exec -T frontend nginx -s reload" in c]
    assert len(execs) == 1, calls
    renews = [c for c in calls if c.startswith("certbot ") and " renew " in c and "--dry-run" in c]
    assert len(renews) == 1, calls
    idx_up = calls.index(_switch_ups(calls)[0])
    assert idx_up < calls.index(execs[0]) < calls.index(renews[0]), calls


@pytest.mark.parametrize("env_key", ["FAKE_EXEC_EXIT", "FAKE_RENEW_EXIT"])
def test_when_renewal_check_fails_then_warning_only_no_rollback(repo, fakes, env_key):
    """E-7 (F4) — 갱신 경로 검증 실패는 WARNING 이지 원복이 아니다(인증서 90일 유효)."""
    proc, calls = _run(repo, fakes, {env_key: "1"})
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert (repo / MARKER).exists(), "갱신 검증 실패가 전환을 되돌렸다"
    assert _rollback_ups(calls) == [], calls
    assert "WARNING" in proc.stdout, proc.stdout
    assert "완료" in proc.stdout, proc.stdout


# ── F1: 전환 실패 → 원복 실행 ────────────────────────────────────────────

def test_when_overlay_up_fails_then_marker_removed_and_base_only_up_executed(repo, fakes):
    """E-8 (F1 ②) — 오버레이 up non-zero → 마커 삭제 → prod 단독 up **실행** → exit 1.

    F1 실측: 443 선점으로 up 이 non-zero 면 컨테이너는 created 로 멈춰 80 도 000 이다.
    안내문만으로는 80 이 돌아오지 않는다 — base 단독 up 이 Recreate 해야 200 이 된다.
    """
    proc, calls = _run(repo, fakes, {"FAKE_TLS_UP_EXIT": "1"})
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert not (repo / MARKER).exists(), "실패 뒤 마커가 남았다(다음 자동 배포가 같은 오버레이를 재현)"
    rollback = _rollback_ups(calls)
    assert len(rollback) == 1, calls
    assert f"-f {BASE} up -d --no-deps frontend" in rollback[0] and TLS not in rollback[0], rollback[0]
    assert "marker=0" in rollback[0], "원복 up 시점에 마커가 아직 있다(rm 이 up 뒤)"
    assert calls.index(_switch_ups(calls)[0]) < calls.index(rollback[0]), calls
    # 갱신 검증은 돌지 않는다.
    assert not any(" renew " in c for c in calls), calls
    assert "80 은 다시 살아있다" in proc.stdout, proc.stdout
    assert proc.stdout.index("원복 실행") < proc.stdout.index("80 은 다시 살아있다"), proc.stdout


def test_when_overlay_up_fails_then_health_not_polled(repo, fakes):
    """E-9 — up 이 non-zero 면 사후 검증 폴링 없이 즉시 원복한다(빈 폴링 10초 낭비 금지)."""
    proc, calls = _run(repo, fakes, {"FAKE_TLS_UP_EXIT": "1"})
    assert proc.returncode == 1
    assert not any("http://127.0.0.1/api/health" in c for c in calls), calls


def test_when_rollback_up_also_fails_then_no_alive_claim_but_manual_steps(repo, fakes):
    """E-10 (F1) — 원복 up 도 실패하면 '80 은 살아있다' 를 말하지 않고 수동 조치를 안내한다."""
    proc, calls = _run(repo, fakes, {"FAKE_TLS_UP_EXIT": "1", "FAKE_BASE_UP_EXIT": "1"})
    assert proc.returncode == 1
    assert not (repo / MARKER).exists()
    assert len(_rollback_ups(calls)) == 1, calls
    assert "80 은 다시 살아있다" not in proc.stdout, proc.stdout
    assert "수동 조치" in proc.stdout and f"docker compose -f {BASE} up -d --no-deps frontend" in proc.stdout, proc.stdout


@pytest.mark.parametrize(
    "env_extra",
    [
        {"FAKE_HTTP_CODE": "000"},               # 80 이 죽음(크래시 루프의 실제 증상)
        {"FAKE_HTTPS_CODE": "000"},              # 443 만 안 뜸(인증서 경로 오류 등)
        {"FAKE_FE_STATE": "restarting"},         # 응답은 어쩌다 401 이어도 State 가 running 이 아님
        {"FAKE_HTTP_CODE": "200"},               # 무인증 200 = Basic Auth 가 빠진 구성(성공으로 보면 안 된다)
    ],
    ids=["http-down", "https-down", "restarting", "http-unauth-200"],
)
def test_when_health_check_fails_then_rollback_executed_even_though_up_returned_zero(repo, fakes, env_extra):
    """E-11 (F1 ①) — up 이 0 이어도 사후 검증 실패 → 원복 up 실행 + 마커 삭제 + exit 1.

    `docker compose up -d` 는 크래시 루프 컨테이너에서도 exit 0 이다(compose v5.1 실측) —
    종전 스크립트는 이 경로에서 '완료' 를 찍고 마커를 남겼다.
    """
    proc, calls = _run(repo, fakes, env_extra)
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert not (repo / MARKER).exists(), "사후 검증 실패 뒤 마커가 남았다"
    assert len(_switch_ups(calls)) == 1 and len(_rollback_ups(calls)) == 1, calls
    assert "사후 검증 미통과" in proc.stdout, proc.stdout
    assert not any(" renew " in c for c in calls), "실패 경로에서 갱신 검증이 돌았다"
    assert "[tls_enable] 완료" not in proc.stdout, proc.stdout  # 성공 토큰(원복 완료 와 구별)


def test_when_health_check_fails_then_it_polled_more_than_once(repo, fakes):
    """E-12 — 사후 검증은 단발이 아니라 폴링이다(기동 중 첫 요청 000 을 실패로 확정하지 않는다)."""
    proc, calls = _run(repo, fakes, {"FAKE_HTTP_CODE": "000"})
    assert proc.returncode == 1
    n = sum(1 for c in calls if c.startswith("curl ") and "http://127.0.0.1/api/health" in c)
    assert 3 <= n <= 30, f"폴링 횟수가 계약(≤10×1s, 최소 수 회) 밖이다: {n}"


def test_when_health_ok_then_polling_stops_early(repo, fakes):
    """E-13 — 셋 다 통과하면 첫 이터레이션에서 끝난다(불필요한 10초 대기 없음)."""
    proc, calls = _run(repo, fakes)
    assert proc.returncode == 0
    n = sum(1 for c in calls if c.startswith("curl ") and "http://127.0.0.1/api/health" in c)
    assert n == 1, calls


# ── 사전 점검 실패 = certbot/docker 미호출 ────────────────────────────────

def test_when_dns_mismatch_then_stop_before_certbot(repo, fakes):
    """E-14 — A 레코드 불일치 → certbot·docker 0회, 마커 없음, exit 1(rate limit 무소모)."""
    proc, calls = _run(repo, fakes, {"FAKE_DIG_IP": "1.2.3.4"})
    assert proc.returncode == 1
    assert not any(c.startswith(("certbot ", "docker ")) for c in calls), calls
    assert not (repo / MARKER).exists()


def test_when_probe_not_200_then_stop_before_certbot_and_probe_removed(repo, fakes):
    """E-15 — 챌린지 경로가 200 이 아니면 certbot 을 부르지 않고 probe 파일도 지운다."""
    proc, calls = _run(repo, fakes, {"FAKE_PROBE_CODE": "401"})
    assert proc.returncode == 1
    assert not any(c.startswith(("certbot ", "docker ")) for c in calls), calls
    assert not (repo / "certbot-www" / ".well-known" / "acme-challenge" / "probe").exists()
    assert not (repo / MARKER).exists()


@pytest.mark.parametrize("env_extra", [{"FAKE_CERTBOT_EXIT": "1"}, {"FAKE_CERTBOT_NO_OUTPUT": "1"}],
                         ids=["certbot-nonzero", "certbot-zero-but-no-fullchain"])
def test_when_issue_fails_then_no_marker_and_no_docker(repo, fakes, env_extra):
    """E-16 — 발급 실패(종료 코드 또는 산출물 부재) → 마커 없음 · docker 0회 · exit 1."""
    proc, calls = _run(repo, fakes, env_extra)
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert not (repo / MARKER).exists()
    assert not any(c.startswith("docker ") for c in calls), calls


def test_when_email_missing_then_nothing_called(repo, fakes):
    """E-17 — LE_EMAIL 부재 → 어떤 외부 명령도 부르지 않고 exit 1."""
    proc, calls = _run(repo, fakes, email=None)
    assert proc.returncode == 1
    assert calls == [], calls
    assert "LE_EMAIL" in proc.stderr
