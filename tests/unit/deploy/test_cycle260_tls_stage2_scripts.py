"""cycle260 Red (G-260-4 · G-260-5) — 2단계 전환 스크립트와 Basic 자격 회전 스크립트의 **행위** 계약.

두 스크립트 모두 EC2 에서 **사람이 손으로 한 번** 돌리고, 중간에 죽으면 반쪽 상태(마커는 있는데
컨테이너는 옛 설정 / 새 해시는 썼는데 아무도 그 비밀번호를 모름)를 남긴다. 그래서 cycle255
`test_cycle255_tls_enable_script.py` 와 같은 방식으로 임시 git 저장소 + 가짜
`curl`/`docker`/`sudo`/`sleep`/`openssl` 을 세워 **무엇을 어떤 순서로 부르고 어디서 멈추는지**를
실증한다.

■ 하네스가 흉내 내는 curl 인터페이스 (Green 과의 합의)
- 상태코드는 `-w '%{http_code}'` 로 받는다(문자열 그대로 stdout 마지막에 붙는다).
- 응답 헤더는 **`-D -`**(헤더를 stdout 으로 덤프)로 받는다. `-i` 도 흉내 내지만, `-o /dev/null`
  과 함께 쓰면 실제 curl 은 헤더까지 버리므로 헤더 검증에는 `-D -` 를 쓴다.
- `-D` 와 그 인자는 **공백으로 분리**한다(`-D-` 붙여쓰기는 하네스가 못 읽는다).

■ G-260-4 계약 (`tools/ops/tls_stage2_enable.sh`)
1. **사람 게이트** — `ROUTINE_HTTPS_CONFIRMED=1` 이 없으면 아무것도 부르지 않고 멈춘다. 2단계
   가동 조건은 "월 09-07 20:20 자동 리포트가 https 로 성공한 것을 사람이 확인" 이고, 그 확인을
   기계가 대신할 수 없다. 오타(`0`·`yes`)가 게이트를 통과하면 안 된다.
2. **1단계 종속** — `.tls_enabled` 와 인증서 산출물, 그리고 실제 https 401 이 모두 확인된 뒤에만
   진행한다. 443 이 없는 상태에서 80 을 301 로 바꾸면 사이트가 **도달 불가**가 된다(리다이렉트
   뒤에 서버가 없다).
3. **사후 검증 4경로** — `up -d` 는 크래시 루프여도 exit 0 이다(compose v5.1 실측). 80 `/` 301 +
   Location 도메인 고정 · ACME 경로 **404**(301 이면 90일 뒤 갱신이 깨진다) · https `/` 401 +
   HSTS · https 정적자산 HSTS(add_header 는 상속이 아니라 대체라 location 마다 따로 붙어야 한다)
   · frontend State=running 을 **같은 이터레이션**에서 본다.
4. **원복은 1단계로** — 실패하면 `.tls_stage2` 만 지우고 `-f prod -f tls` 로 돌아간다.
   `.tls_enabled` 를 지우면 443 이 함께 내려가 원복이 아니라 2단계 후퇴가 된다.
5. `disable` 은 같은 원복 절차를 사람이 부르는 경로다(게이트 불필요 — 끄는 것은 언제나 허용).

■ G-260-5 계약 (`tools/ops/rotate_basic_auth.sh`)
평문 HTTP 로 오갔던 Basic 자격을 2단계 전환 뒤에 회전한다. 사용자 목록은 **파일에서 읽고**
(하드코딩하면 `reporter` 를 빠뜨린 채 회전해 20:20 루틴이 조용히 401 이 된다), 새 비밀번호는
URL 안전 문자만 쓰고(루틴 프롬프트가 "비밀번호에 @ 가 있어 URL 에 넣으면 깨진다" 고 경고한 그
문제), 화면에 찍지 않고 600 파일로만 남기며, 검증에 실패하면 백업을 되돌린다.
"""
from __future__ import annotations

import os
import re
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
_ENABLE = _ROOT / "tools" / "ops" / "tls_stage2_enable.sh"
_ROTATE = _ROOT / "tools" / "ops" / "rotate_basic_auth.sh"

pytestmark = pytest.mark.skipif(
    shutil.which("bash") is None or shutil.which("git") is None,
    reason="bash/git 필요",
)

TLS_MARKER = ".tls_enabled"
TLS2_MARKER = ".tls_stage2"
BASE = "docker-compose.prod.yml"
TLS = "docker-compose.tls.yml"
TLS2 = "docker-compose.tls2.yml"
DOMAIN = "auto.dkstock.cloud"
HSTS_MAX_AGE = "max-age=86400"

_LEAKY_PREFIXES = ("GIT_", "FAKE_", "LE_", "ROUTINE_")


def _clean_env() -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith(_LEAKY_PREFIXES)}
    env["GIT_CONFIG_GLOBAL"] = os.devnull
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    return env


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True, text=True, env=_clean_env()
    ).stdout.strip()


def _require(path: Path) -> None:
    if not path.exists():
        pytest.fail(f"Red — {path.relative_to(_ROOT)} 부재 (명세 §범위)")


def _src(path: Path) -> str:
    _require(path)
    return path.read_text(encoding="utf-8")


def _code(path: Path) -> str:
    """주석 줄 제외 — 설명문의 단어는 검사 대상이 아니다(cycle255 G-255-5 와 같은 관례)."""
    return "\n".join(ln for ln in _src(path).splitlines() if not ln.lstrip().startswith("#"))


def _expanded(path: Path) -> str:
    """단순 리터럴 변수 대입(`VAR="literal"`)을 펼친 코드.

    스크립트가 경로·파일명을 변수로 두든 리터럴로 적든 **같은 계약**을 재기 위한 것이다 —
    가드가 작성 스타일을 강요하면 Green 이 가드를 피해 쓰게 되고, 그때 가드는 계약이 아니라
    문법 검사기가 된다. 값이 다른 변수를 품으면(`"${REPO_DIR}/secrets/.htpasswd"`) 여러 번
    돌려 펼치고, 끝내 안 풀리는 것(`${LE_LIVE_DIR:-…}`·명령 치환)은 그대로 둔다.
    """
    code = _code(path)
    env = dict(re.findall(r'^\s*([A-Z][A-Z0-9_]*)="([^"\n]*)"\s*$', code, re.M))
    for _ in range(5):
        for k, v in env.items():
            code = re.sub(r"\$\{" + k + r"\}|\$" + k + r"\b", v.replace("\\", "\\\\"), code)
    # 따옴표도 지운다 — 이 헬퍼를 쓰는 가드는 전부 부분문자열 대조라 `-f "x"` 와 `-f x` 를
    # 구별할 이유가 없다(구별하면 그것도 스타일 강요다).
    return code.replace('"', "").replace("'", "")


def _write_exec(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)


def _mode(path: Path) -> str:
    return oct(path.stat().st_mode & 0o777)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    r = tmp_path / "repo"
    r.mkdir()
    _git(r, "init", "-q")
    (r / "README.md").write_text("x\n", encoding="utf-8")
    return r


# ===========================================================================
# G-260-4 — tools/ops/tls_stage2_enable.sh
# ===========================================================================
#: 가짜 curl. URL 로 분기해 상태코드(`-w`)와 헤더(`-D -`)를 낸다.
#: `FAKE_*_HSTS` 는 `${VAR-기본}`(콜론 없음) 이라 **빈 문자열로 설정하면 헤더가 사라진다** —
#: "HSTS 가 안 붙은 응답" 을 흉내 내는 손잡이다. `FAKE_HTTPS_CODE_AFTER` 는 **2단계 마커가
#: 생긴 뒤**(= 전환 up 이후)에만 적용된다 — 전환 전 사전 점검은 통과시키고 전환 후에만 443 이
#: 죽는 상황(스니펫이 443 블록을 깨뜨린 경우)을 흉내 낸다.
_FAKE_CURL = r"""#!/usr/bin/env bash
echo "curl $*" >> "$FAKE_LOG"
url=""; wfmt=""; dump=""; inc=0; prev=""
for a in "$@"; do
  case "$prev" in -D) dump="$a" ;; -w) wfmt="$a" ;; esac
  case "$a" in
    http://*|https://*) url="$a" ;;
    --*) ;;
    -*[iI]*) inc=1 ;;
  esac
  prev="$a"
done
loc=""; hsts=""; code="000"
case "$url" in
  *acme-challenge*)   code="${FAKE_ACME_CODE:-404}" ;;
  https://*/assets/*) code="${FAKE_ASSET_CODE:-401}"; hsts="${FAKE_ASSET_HSTS-max-age=86400}" ;;
  https://*)          code="${FAKE_HTTPS_CODE:-401}"; hsts="${FAKE_HTTPS_HSTS-max-age=86400}"
                      if [ -f .tls_stage2 ] && [ -n "${FAKE_HTTPS_CODE_AFTER:-}" ]; then code="$FAKE_HTTPS_CODE_AFTER"; fi ;;
  http://*)           code="${FAKE_HTTP_CODE:-301}"; loc="${FAKE_HTTP_LOCATION-https://auto.dkstock.cloud/}" ;;
esac
head="HTTP/1.1 ${code} X
Server: nginx"
if [ -n "$loc" ];  then head="${head}
Location: ${loc}"; fi
if [ -n "$hsts" ]; then head="${head}
Strict-Transport-Security: ${hsts}"; fi
head="${head}

"
if [ -n "$dump" ]; then
  if [ "$dump" = "-" ]; then printf '%s' "$head"; else printf '%s' "$head" > "$dump"; fi
elif [ "$inc" = "1" ]; then
  printf '%s' "$head"
fi
if [ -n "$wfmt" ]; then printf '%s' "$code"; fi
exit 0
"""

#: 가짜 docker. 호출 시점의 **2단계 마커** 존재 여부를 같이 기록한다(순서 계약 검증용).
_FAKE_DOCKER = r"""#!/usr/bin/env bash
m2=0; [ -f .tls_stage2 ] && m2=1
m1=0; [ -f .tls_enabled ] && m1=1
echo "docker m1=$m1 m2=$m2 $*" >> "$FAKE_LOG"
args=" $* "
case "$args" in
  *" ps "*) printf '{"Service":"frontend","State":"%s"}\n' "${FAKE_FE_STATE:-running}"; exit 0 ;;
  *" up "*)
    case "$args" in
      *"docker-compose.tls2.yml"*) exit "${FAKE_TLS2_UP_EXIT:-0}" ;;
      *) exit "${FAKE_ROLLBACK_UP_EXIT:-0}" ;;
    esac ;;
esac
exit 0
"""

_FAKE_SUDO = '#!/usr/bin/env bash\necho "sudo $*" >> "$FAKE_LOG"\nexec "$@"\n'
_FAKE_SLEEP = "#!/usr/bin/env bash\nexit 0\n"


@pytest.fixture
def fakes(tmp_path: Path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = tmp_path / "calls.log"
    _write_exec(bin_dir / "curl", _FAKE_CURL)
    _write_exec(bin_dir / "docker", _FAKE_DOCKER)
    _write_exec(bin_dir / "sudo", _FAKE_SUDO)
    _write_exec(bin_dir / "sleep", _FAKE_SLEEP)
    return bin_dir, log


@pytest.fixture
def armed(repo: Path, tmp_path: Path) -> Path:
    """1단계가 이미 켜진 EC2 상태 — `.tls_enabled` + 발급된 인증서."""
    (repo / TLS_MARKER).write_text("", encoding="utf-8")
    live = tmp_path / "le-live"
    live.mkdir()
    (live / "fullchain.pem").write_text("cert\n", encoding="utf-8")
    return live


def _run_enable(
    repo: Path,
    fakes,
    live: Path,
    env_extra: dict[str, str] | None = None,
    *,
    args: tuple[str, ...] = (),
    confirmed: str | None = "1",
):
    bin_dir, log = fakes
    env = _clean_env()
    env["PATH"] = f"{bin_dir}{os.pathsep}{env['PATH']}"
    env["FAKE_LOG"] = str(log)
    env["LE_LIVE_DIR"] = str(live)
    if confirmed is not None:
        env["ROUTINE_HTTPS_CONFIRMED"] = confirmed
    env.update(env_extra or {})
    _require(_ENABLE)
    proc = subprocess.run(
        ["bash", str(_ENABLE), *args], cwd=repo, env=env, capture_output=True, text=True
    )
    calls = log.read_text(encoding="utf-8").splitlines() if log.exists() else []
    return proc, calls


def _ups(calls: list[str]) -> list[str]:
    return [c for c in calls if c.startswith("docker ") and " compose " in c and " up " in c]


def _switch_ups(calls: list[str]) -> list[str]:
    return [c for c in _ups(calls) if TLS2 in c]


def _rollback_ups(calls: list[str]) -> list[str]:
    return [c for c in _ups(calls) if TLS2 not in c]


def _curls(calls: list[str]) -> list[str]:
    return [c for c in calls if c.startswith("curl ")]


# ── 사람 게이트 ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("confirmed", [None, "0", "yes", ""], ids=["absent", "zero", "yes", "empty"])
def test_enable_when_routine_confirmation_missing_then_nothing_called(repo, fakes, armed, confirmed):
    """G-260-4a — `ROUTINE_HTTPS_CONFIRMED=1` 이 아니면 **아무것도 부르지 않고** 멈춘다.

    2단계 가동 조건은 "20:20 자동 리포트가 https 로 성공했다" 를 사람이 확인한 것이고, 그
    확인은 코드가 대신할 수 없다. `0`·`yes`·빈 문자열 같은 오타가 통과하면 게이트가 아니라
    장식이다(`DEPLOY_DRY_RUN` 이 오타를 exit 2 로 막는 것과 같은 규약).
    """
    proc, calls = _run_enable(repo, fakes, armed, confirmed=confirmed)
    assert proc.returncode != 0, proc.stdout + proc.stderr
    assert calls == [], calls
    assert not (repo / TLS2_MARKER).exists(), "게이트 미통과인데 마커가 생겼다"
    assert "ROUTINE_HTTPS_CONFIRMED" in (proc.stdout + proc.stderr), proc.stdout + proc.stderr


# ── 1단계 종속 사전 점검 ─────────────────────────────────────────────────────

def test_enable_when_stage1_marker_absent_then_stop_before_any_docker(repo, fakes, armed):
    """G-260-4b — `.tls_enabled` 가 없으면 멈춘다(443 부재 = 301 하면 도달 불가).

    2단계 오버레이는 배포 스크립트에서도 1단계에 종속이지만(T-260-4), 이 스크립트가 마커를
    먼저 만들어 두면 "다음 배포에서 켜지는" 시한폭탄이 된다. 여기서 막는 것이 유일한 예방이다.
    """
    (repo / TLS_MARKER).unlink()
    proc, calls = _run_enable(repo, fakes, armed)
    assert proc.returncode != 0, proc.stdout
    assert not any(c.startswith("docker ") for c in calls), calls
    assert not (repo / TLS2_MARKER).exists()


def test_enable_when_certificate_missing_then_stop_before_any_docker(repo, fakes, armed):
    """G-260-4c — 인증서 산출물이 없으면 멈춘다.

    `/etc/letsencrypt/live` 는 root 700 이라 일반 사용자의 `[ -f ]` 는 EACCES 로 거짓 '없음'을
    낸다(cycle255 첫 실행 실측) — 존재 확인은 `sudo test -f` 로 한다. 마커가 있는데 인증서만
    사라진 상태(수동 삭제·볼륨 유실)에서 2단계를 켜면 443 이 기동 실패하고 80 도 함께 죽는다.
    """
    (armed / "fullchain.pem").unlink()
    proc, calls = _run_enable(repo, fakes, armed)
    assert proc.returncode != 0, proc.stdout
    assert not any(c.startswith("docker ") for c in calls), calls
    assert not (repo / TLS2_MARKER).exists()
    assert any(c.startswith("sudo ") and " test " in f" {c} " for c in calls), (
        f"인증서 확인이 `sudo test` 가 아니다(root 700 에서 거짓 '없음'): {calls}"
    )


def test_enable_when_https_precheck_not_401_then_stop_before_marker(repo, fakes, armed):
    """G-260-4d — 전환 **전** https 가 401 이 아니면 멈춘다(마커·docker up 없음).

    1단계가 실제로 살아 있는지를 파일이 아니라 응답으로 재는 유일한 지점이다. 여기서
    통과시키고 전환하면, 그 다음 실패는 "2단계가 깼다" 로 오귀인된다.
    """
    proc, calls = _run_enable(repo, fakes, armed, {"FAKE_HTTPS_CODE": "000"})
    assert proc.returncode != 0, proc.stdout
    assert _ups(calls) == [], calls
    assert not (repo / TLS2_MARKER).exists()


# ── 정상 경로 ───────────────────────────────────────────────────────────────

def test_enable_when_all_green_then_marker_and_single_three_file_up(repo, fakes, armed):
    """G-260-4e — 정상: 마커 생성 → `-f prod -f tls -f tls2 up -d --no-deps frontend` 1회 → exit 0.

    마커가 up **앞**이어야 한다 — 뒤면 그 up 은 2단계 없는 구성이고, 마커만 남아 다음 자동
    배포가 검증 없이 2단계를 올린다(검증 창이 사라진다). `--no-deps frontend` 는 cycle232 D6:
    backend 를 건드리면 전환 창이 하루 한 번으로 줄어든다.
    """
    proc, calls = _run_enable(repo, fakes, armed)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert (repo / TLS2_MARKER).exists(), "성공 경로에서 2단계 마커가 없다"
    switch = _switch_ups(calls)
    assert len(switch) == 1, calls
    assert f"-f {BASE} -f {TLS} -f {TLS2} up -d --no-deps frontend" in switch[0], switch[0]
    assert "m2=1" in switch[0], "전환 up 시점에 2단계 마커가 없다(마커 → up 순서 위반)"
    assert "m1=1" in switch[0], "전환 up 시점에 1단계 마커가 사라졌다"
    assert _rollback_ups(calls) == [], f"성공 경로에서 원복 up 이 돌았다: {_rollback_ups(calls)}"
    assert "backend" not in switch[0], switch[0]


def test_enable_when_all_green_then_four_paths_verified_after_switch(repo, fakes, armed):
    """G-260-4f — 사후 검증 4경로 + State 조회가 전환 up **뒤**에 실제로 호출된다.

    - 80 `/` → 301(리다이렉트가 실제로 걸렸는가)
    - 80 ACME 경로 → 404(갱신 창이 살아 있는가 — 여기가 301 이면 90일 뒤 조용히 만료된다)
    - 443 `/` → 401 + HSTS(문서 응답)
    - 443 정적자산 → HSTS(add_header 는 상속이 아니라 **대체** — location 마다 따로 붙어야 한다)
    루프백 + `--resolve` SNI 로 재는 것은 cycle255 와 같은 규약(외부 DNS·방화벽에 의존하지 않는다).
    """
    proc, calls = _run_enable(repo, fakes, armed)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    idx_up = calls.index(_switch_ups(calls)[0])
    after = calls[idx_up + 1 :]

    root80 = [c for c in _curls(after) if "http://127.0.0.1/" in c and "acme-challenge" not in c]
    acme = [c for c in _curls(after) if "acme-challenge" in c]
    https_root = [c for c in _curls(after) if f"https://{DOMAIN}/" in c and "/assets/" not in c]
    https_asset = [c for c in _curls(after) if f"https://{DOMAIN}/" in c and "/assets/" in c]
    ps = [c for c in after if c.startswith("docker ") and " ps " in c and "frontend" in c]
    for name, hits in (
        ("80 루트(301)", root80), ("ACME 경로(404)", acme),
        ("443 루트(401+HSTS)", https_root), ("443 정적자산(HSTS)", https_asset),
        ("frontend State", ps),
    ):
        assert hits, f"사후 검증 '{name}' 호출이 전환 up 뒤에 없다: {after}"
    assert f"--resolve {DOMAIN}:443:127.0.0.1" in https_root[0], https_root[0]
    assert any(" -D " in f" {c} " for c in https_root + https_asset), (
        f"헤더 검증에 `-D -` 를 쓰지 않는다(HSTS 존재를 잴 수 없다): {https_root + https_asset}"
    )


def test_enable_when_all_green_then_polling_stops_at_first_iteration(repo, fakes, armed):
    """G-260-4g — 전부 통과하면 첫 이터레이션에서 끝난다(불필요한 10초 대기 없음)."""
    proc, calls = _run_enable(repo, fakes, armed)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    idx_up = calls.index(_switch_ups(calls)[0])
    n = sum(1 for c in _curls(calls[idx_up + 1 :]) if "http://127.0.0.1/" in c and "acme" not in c)
    assert n == 1, f"성공인데 폴링이 반복됐다: {n}회"


def test_enable_when_all_green_then_prints_post_activation_checklist(repo, fakes, armed):
    """G-260-4g2 (tester F-6) — 성공 시 가동 직후 필수 절차 체크리스트를 출력한다.

    80 은 2단계 가동 뒤 더 이상 자격을 *요구*하지 않을 뿐 클라이언트가 *선제로 보내는* 자격
    까지 막지는 못한다(§2 정정) — 그래서 루틴의 http 예비 경로 제거·자격 회전·브라우저
    재접속이 "언젠가 하면 되는 일"이 아니라 가동 성공의 일부로 눈에 보여야 한다. 이 목록이
    없으면 그동안 운영자는 성공 로그만 보고 세 가지를 모두 놓칠 수 있었다(tester 지적).
    """
    proc, calls = _run_enable(repo, fakes, armed)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "rotate_basic_auth.sh" in proc.stdout, proc.stdout
    assert "REPORTER_BASIC_PASSWORD" in proc.stdout, proc.stdout
    assert f"https://{DOMAIN}/" in proc.stdout, proc.stdout


# ── 사후 검증 실패 → 1단계로 원복 ────────────────────────────────────────────

@pytest.mark.parametrize(
    "env_extra",
    [
        {"FAKE_HTTP_CODE": "401"},                                  # 301 이 안 걸림(스니펫 미마운트)
        {"FAKE_HTTP_LOCATION": "https://3.38.228.74/"},             # 도메인 고정 실패(인증서 이름 불일치)
        {"FAKE_ACME_CODE": "301"},                                  # 갱신 창이 리다이렉트에 먹힘
        {"FAKE_HTTPS_HSTS": ""},                                    # 문서 응답에 HSTS 없음
        {"FAKE_ASSET_HSTS": ""},                                    # 정적자산에만 HSTS 없음(대체 함정)
        {"FAKE_HTTPS_CODE_AFTER": "000"},                           # 전환 뒤 443 이 죽음
        {"FAKE_FE_STATE": "restarting"},                            # 크래시 루프(up 은 exit 0)
        {"FAKE_HTTPS_HSTS": "max-age=0"},                           # 뮤테이션 E3c — 브라우저에 HSTS **삭제**를 지시하는 값
        {"FAKE_ASSET_HSTS": "max-age=15552000"},                    # 뮤테이션 E3c — 1주 안정 뒤 별도 결정으로만 올리기로 한 값이 미리 들어감
        {"FAKE_HTTPS_HSTS": "max-age=86400; includeSubDomains"},    # 뮤테이션 E3c — 접두 매치면 통과했을 초과 속성
    ],
    ids=["no-301", "wrong-location", "acme-redirected", "no-hsts-doc",
         "no-hsts-asset", "https-down", "restarting",
         "hsts-max-age-0-doc", "hsts-wrong-value-asset", "hsts-includesubdomains-doc"],
)
def test_enable_when_verification_fails_then_rollback_to_stage1_and_exit_1(repo, fakes, armed, env_extra):
    """G-260-4h — 사후 검증 실패 → 2단계 마커 삭제 + `-f prod -f tls` 원복 up + exit 1.

    `docker compose up -d` 는 크래시 루프여도 exit 0 이다 — 종료 코드만 믿으면 '완료'를 찍고
    마커를 남겨 다음 자동 배포가 같은 구성을 재현한다. 특히 **정적자산 HSTS 누락**은 브라우저
    개발자도구를 열지 않으면 보이지 않는데, 그 상태의 HSTS 는 사실상 꺼진 것이다.
    """
    proc, calls = _run_enable(repo, fakes, armed, env_extra)
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert not (repo / TLS2_MARKER).exists(), "검증 실패 뒤 2단계 마커가 남았다"
    assert (repo / TLS_MARKER).exists(), "원복이 1단계 마커까지 지웠다 — 443 이 함께 내려간다"
    assert len(_switch_ups(calls)) == 1, calls
    rollback = _rollback_ups(calls)
    assert len(rollback) == 1, calls
    assert f"-f {BASE} -f {TLS} up -d --no-deps frontend" in rollback[0], rollback[0]
    assert TLS2 not in rollback[0], rollback[0]
    assert "m2=0" in rollback[0], "원복 up 시점에 2단계 마커가 아직 있다(rm 이 up 뒤)"


def test_enable_when_overlay_up_fails_then_rollback_without_polling(repo, fakes, armed):
    """G-260-4i — 전환 up 이 non-zero → 폴링 없이 즉시 원복(빈 10초 낭비 금지) + exit 1."""
    proc, calls = _run_enable(repo, fakes, armed, {"FAKE_TLS2_UP_EXIT": "1"})
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert not (repo / TLS2_MARKER).exists()
    idx_up = calls.index(_switch_ups(calls)[0])
    idx_rb = calls.index(_rollback_ups(calls)[0])
    assert idx_up < idx_rb, calls
    assert not any("acme-challenge" in c for c in calls[idx_up:idx_rb]), calls


def test_enable_when_verification_fails_then_it_polled_more_than_once(repo, fakes, armed):
    """G-260-4j — 사후 검증은 단발이 아니라 폴링이다(기동 중 첫 응답을 실패로 확정하지 않는다)."""
    proc, calls = _run_enable(repo, fakes, armed, {"FAKE_HTTP_CODE": "000"})
    assert proc.returncode == 1
    n = sum(1 for c in _curls(calls) if "http://127.0.0.1/" in c and "acme" not in c)
    assert 3 <= n <= 30, f"폴링 횟수가 계약(≤10×1s, 최소 수 회) 밖이다: {n}"


def test_enable_when_rolled_back_then_stage1_health_reverified(repo, fakes, armed):
    """G-260-4k — 원복 up **뒤**에 80·443 을 다시 재고, 그 결과를 말한다.

    원복이 실제로 사이트를 되살렸는지 확인하지 않으면 "원복했다" 는 문장이 곧 거짓말이 될 수
    있다(cycle255 F1 — 오버레이 up 이 non-zero 인 컨테이너는 created 로 멈춰 80 도 000 이다).
    """
    proc, calls = _run_enable(repo, fakes, armed, {"FAKE_ACME_CODE": "301"})
    assert proc.returncode == 1
    idx_rb = calls.index(_rollback_ups(calls)[0])
    after = _curls(calls[idx_rb + 1 :])
    assert any("http://127.0.0.1/" in c for c in after), f"원복 뒤 80 재확인이 없다: {calls}"
    assert any(f"https://{DOMAIN}/" in c for c in after), f"원복 뒤 443 재확인이 없다: {calls}"


# ── disable ────────────────────────────────────────────────────────────────

def test_enable_script_when_disable_then_same_rollback_without_gate(repo, fakes, armed):
    """G-260-4l — `disable` 은 게이트 없이 원복만 한다(끄는 것은 언제나 허용).

    끄는 경로에 사람 확인 게이트를 두면, 사고가 났을 때 그 게이트가 복구를 막는다. 대신
    `.tls_enabled` 는 건드리지 않는다 — 2단계만 끄고 443 은 유지하는 것이 이 명령의 정의다.
    """
    (repo / TLS2_MARKER).write_text("", encoding="utf-8")
    proc, calls = _run_enable(repo, fakes, armed, args=("disable",), confirmed=None)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert not (repo / TLS2_MARKER).exists(), "disable 이 마커를 지우지 않았다"
    assert (repo / TLS_MARKER).exists(), "disable 이 1단계 마커까지 지웠다"
    assert _switch_ups(calls) == [], f"disable 인데 2단계 오버레이 up 이 돌았다: {calls}"
    rollback = _rollback_ups(calls)
    assert len(rollback) == 1, calls
    assert f"-f {BASE} -f {TLS} up -d --no-deps frontend" in rollback[0], rollback[0]


def test_enable_script_when_disable_and_stage1_marker_absent_then_rollback_is_prod_only(repo, fakes, armed):
    """G-260-4q (tester F-2) — `.tls_enabled` 가 없는 호스트에서 `disable` 은 prod 단독으로 원복한다.

    현행(수정 전)은 마커 유무와 무관하게 `-f prod -f tls` 를 올린다 — 1단계가 이미 원복된
    (인증서 없는/만료된) 호스트에서 443 오버레이를 올리면 nginx 가 `[emerg]` 로 기동 실패해
    같은 컨테이너의 80 까지 내려간다(cycle255 F1 과 같은 실패 계열). "끄는 것은 언제나
    허용" 이려면 끄는 경로가 어떤 호스트 상태에서도 안전해야 한다.
    """
    (repo / TLS_MARKER).unlink()
    (repo / TLS2_MARKER).write_text("", encoding="utf-8")
    proc, calls = _run_enable(repo, fakes, armed, args=("disable",), confirmed=None)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert not (repo / TLS2_MARKER).exists(), "disable 이 2단계 마커를 지우지 않았다"
    assert not (repo / TLS_MARKER).exists(), "1단계 마커가 원래 없었는데 disable 이 만들었다"
    assert _switch_ups(calls) == [], f"disable 인데 2단계 오버레이 up 이 돌았다: {calls}"
    rollback = _rollback_ups(calls)
    assert len(rollback) == 1, calls
    assert TLS not in rollback[0], (
        f"1단계 마커가 없는데 443 오버레이를 올린다(인증서 없으면 80 까지 죽는다): {rollback[0]}"
    )
    assert re.search(rf"-f {re.escape(BASE)} up -d --no-deps frontend\b", rollback[0]), rollback[0]


# ── 정적 계약 ───────────────────────────────────────────────────────────────

def test_enable_script_when_present_then_bash_syntax_ok_and_strict_mode():
    """G-260-4m — `bash -n` 통과 + `set -euo pipefail`.

    중단 규약이 없으면 실패한 사전 점검 뒤에도 계속 진행해 반쪽 상태를 만든다.
    """
    _require(_ENABLE)
    proc = subprocess.run(["bash", "-n", str(_ENABLE)], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    assert re.search(r"^set -euo pipefail\s*$", _src(_ENABLE), re.M), "`set -euo pipefail` 부재"


def test_enable_script_when_present_then_never_removes_stage1_marker_in_code():
    """G-260-4n — 코드가 `.tls_enabled` 를 지우지 않는다(설명문에서 언급하는 것은 허용).

    1단계 마커를 지우면 443 이 함께 내려간다 — 그것은 2단계 원복이 아니라 TLS 전체 후퇴다.
    두 마커의 수명은 독립이어야 `rm .tls_stage2` 한 줄이 완전하고 안전한 원복이 된다.
    """
    code = _expanded(_ENABLE)
    offenders = re.findall(r"^[^\n]*\brm\b[^\n]*\.tls_enabled[^\n]*$", code, re.M)
    assert not offenders, f"코드가 1단계 마커를 지운다: {offenders}"


def test_enable_script_when_present_then_all_ups_are_frontend_only():
    """G-260-4o — 모든 `docker compose … up` 은 `--no-deps frontend`(backend 무접촉).

    전환·원복 둘 다 장중에 돌 수 있어야 한다 — backend 를 건드리면 cycle232 D6(보유 중 재시작
    금지)에 걸려 전환 창이 하루 한 번으로 줄어든다.

    원복 up 은 (tester F-2 시정으로) `${FILES[@]}` 조건부 배열이라 리터럴 `-f` 토큰이 소스에
    없다 — 그 한 줄은 구조로만(배열 사용·`--no-deps frontend`·backend 부재) 검사하고, 파일
    체인의 순서·내용은 **행위 테스트**(G-260-4e/f·G-260-4q)가 실증한다. `_expanded` 는 따옴표를
    지우므로 `"${FILES[@]}"` 는 `${FILES[@]}` 로 남는다.
    """
    lines = [
        ln.strip()
        for ln in _expanded(_ENABLE).splitlines()
        if "docker compose" in ln and " up " in ln and not re.match(r"\s*(log|echo)\b", ln)
    ]
    assert lines, "`docker compose … up` 호출이 없다"
    static_ups = [ln for ln in lines if "${FILES[@]}" not in ln]
    dynamic_ups = [ln for ln in lines if "${FILES[@]}" in ln]

    for up in lines:
        assert re.search(r"--no-deps\s+frontend\b", up), f"backend 를 건드리는 up: {up}"
        assert "backend" not in up, up

    assert len(dynamic_ups) == 1, (
        f"원복 up 은 `${{FILES[@]}}` 조건부 배열로 정확히 1줄이어야 한다(F-2 시정): {dynamic_ups}"
    )

    for up in static_ups:
        assert f"-f {BASE}" in up, f"base compose 가 빠진 up: {up}"
        assert f"-f {TLS}" in up, f"1단계 오버레이가 빠진 up(443 이 내려간다): {up}"
    switch = [u for u in static_ups if TLS2 in u]
    assert len(switch) == 1, f"2단계 전환 up 은 정확히 1줄이어야 한다: {switch}"
    idx_base = switch[0].index(f"-f {BASE}")
    assert idx_base < switch[0].index(f"-f {TLS}") < switch[0].index(f"-f {TLS2}"), (
        f"compose 파일 순서가 prod → tls → tls2 가 아니다(뒤에 오는 파일이 이긴다): {switch[0]}"
    )


def test_enable_script_when_present_then_rollback_files_array_is_stage1_conditional():
    """G-260-4r (tester F-2) — 원복의 `FILES` 배열 구성이 `.tls_enabled`(STAGE1) 존재에 조건부다.

    구조 가드 — 실제 분기 **행위**는 G-260-4q(부재 → prod 단독)·G-260-4e/f(존재 → prod+tls)가
    실증한다. 여기서는 "조건 없이 항상 두 파일을 넣는" 뮤턴트가 소스에 남지 않았는지만 잰다.
    `_expanded` 는 `${STAGE1}`·`${BASE}`·`${TLS}` 자체를 리터럴로 치환해버려 이 검사에 맞지
    않는다 — 원본 토큰을 보존하는 `_code`(주석만 제거)를 쓴다.
    """
    code = _code(_ENABLE)
    assert re.search(r'if\s*\[\s*-f\s*"?\$\{STAGE1\}"?\s*\]\s*;\s*then', code), (
        "원복이 STAGE1 마커 존재를 조건으로 두지 않는다"
    )
    assert re.search(r'FILES=\(-f\s*"?\$\{BASE\}"?\)', code), (
        "STAGE1 부재 분기에서 FILES 를 base 단독으로 두지 않는다"
    )
    assert re.search(r'FILES=\(-f\s*"?\$\{BASE\}"?\s*-f\s*"?\$\{TLS\}"?\)', code), (
        "STAGE1 존재 분기에서 FILES 를 base+tls 로 두지 않는다"
    )


def test_enable_script_when_scanned_then_no_secret_literals():
    """G-260-4p — 스크립트에 비밀값 리터럴이 없다(git 커밋 대상)."""
    src = _src(_ENABLE)
    assert not re.search(r"BEGIN [A-Z ]*PRIVATE KEY", src), "개인키가 스크립트에 있다"
    offenders = re.findall(
        r"^\s*(?:export\s+)?(?:API_\w*KEY|PASSWORD|PASSWD|SECRET)\s*=\s*[\"']?[A-Za-z0-9_\-]{8,}",
        src, re.M,
    )
    assert not offenders, f"비밀값 리터럴로 보이는 대입이 있다: {offenders}"


# ===========================================================================
# G-260-5 — tools/ops/rotate_basic_auth.sh
# ===========================================================================
#: 가짜 openssl. `rand` 는 호출마다 다른 비밀번호를 내고 그 목록을 파일에 남긴다
#: (가짜 curl 이 "유효 자격" 판정에 쓴다). `passwd -apr1 -stdin` 은 stdin 을 소비한다.
_FAKE_OPENSSL = r"""#!/usr/bin/env bash
echo "openssl $*" >> "$FAKE_LOG"
case "$1" in
  rand)
    n=$(( $(cat "$FAKE_PW_SEQ" 2>/dev/null || echo 0) + 1 ))
    printf '%s' "$n" > "$FAKE_PW_SEQ"
    pw="rotpw${n}AAAABBBBCCCCDD"
    printf '%s\n' "$pw"
    printf '%s\n' "$pw" >> "$FAKE_PW_LOG"
    ;;
  passwd)
    read -r p || true
    printf 'APR1FAKE.%s\n' "$p"
    ;;
esac
exit 0
"""

#: 가짜 curl(회전용). `-u user:pass` 의 비밀번호가 이번 실행에서 **생성된** 것이면 성공 코드,
#: 아니면 거부 코드를 낸다 — "새 자격은 통과, 잘못된 자격은 401" 을 흉내 낸다.
#: **2단계 인지** — 요청 URL 이 `http://` 이고 `.tls_stage2` 마커가 있으면 자격과 무관하게
#: 301(실 nginx 실측: rewrite 단계 return 이 access 단계보다 앞이라 Basic Auth 를 아예 안
#: 본다). `.tls_stage2` 가 없으면 종전과 동일하게 자격으로만 판정한다(회귀 방지).
_FAKE_CURL_AUTH = r"""#!/usr/bin/env bash
echo "curl $*" >> "$FAKE_LOG"
cred=""; prev=""; url=""
for a in "$@"; do
  case "$prev" in -u) cred="$a" ;; esac
  case "$a" in http://*|https://*) url="$a" ;; esac
  prev="$a"
done
case "$url" in
  http://*)
    if [ -f .tls_stage2 ]; then printf '301'; exit 0; fi ;;
esac
pw="${cred#*:}"
code="${FAKE_INVALID_CODE:-401}"
if [ -n "$pw" ] && [ -f "$FAKE_PW_LOG" ] && grep -Fxq "$pw" "$FAKE_PW_LOG"; then
  code="${FAKE_NEW_CODE:-200}"
fi
printf '%s' "$code"
exit 0
"""

_DEFAULT_USERS = ("alpha", "bravo")


@pytest.fixture
def rotate_fakes(tmp_path: Path):
    bin_dir = tmp_path / "rbin"
    bin_dir.mkdir()
    log = tmp_path / "rotate.log"
    _write_exec(bin_dir / "openssl", _FAKE_OPENSSL)
    _write_exec(bin_dir / "curl", _FAKE_CURL_AUTH)
    _write_exec(bin_dir / "sudo", _FAKE_SUDO)
    _write_exec(bin_dir / "sleep", _FAKE_SLEEP)
    return bin_dir, log, tmp_path


def _seed_htpasswd(repo: Path, users=_DEFAULT_USERS) -> Path:
    secrets = repo / "secrets"
    secrets.mkdir(exist_ok=True)
    secrets.chmod(0o755)
    ht = secrets / ".htpasswd"
    ht.write_text("".join(f"{u}:$apr1$old$hash{i}\n" for i, u in enumerate(users)), encoding="utf-8")
    ht.chmod(0o644)
    return ht


def _run_rotate(repo: Path, rotate_fakes, env_extra: dict[str, str] | None = None):
    bin_dir, log, tmp = rotate_fakes
    env = _clean_env()
    env["PATH"] = f"{bin_dir}{os.pathsep}{env['PATH']}"
    env["FAKE_LOG"] = str(log)
    env["FAKE_PW_SEQ"] = str(tmp / "pwseq")
    env["FAKE_PW_LOG"] = str(tmp / "pwlog")
    env.update(env_extra or {})
    _require(_ROTATE)
    proc = subprocess.run(["bash", str(_ROTATE)], cwd=repo, env=env, capture_output=True, text=True)
    calls = log.read_text(encoding="utf-8").splitlines() if log.exists() else []
    generated = (tmp / "pwlog").read_text(encoding="utf-8").split() if (tmp / "pwlog").exists() else []
    return proc, calls, generated


def _backups(repo: Path) -> list[Path]:
    return sorted((repo / "secrets").glob(".htpasswd.bak-*"))


def _rotated(repo: Path) -> list[Path]:
    return sorted(p for p in (repo / "secrets").glob(".rotated-*") if not p.name.endswith(".FAILED"))


def _rotated_failed(repo: Path) -> list[Path]:
    return sorted((repo / "secrets").glob(".rotated-*.FAILED"))


# ── 검증 대상(스킴·경로) — tester 후속 F-1/F-5 ───────────────────────────────

def test_rotate_when_no_tls_then_verifies_root_path_over_http_loopback(repo, rotate_fakes):
    """G-260-5m — TLS 마커가 없으면 종전대로 http 루프백을 쓰되, 경로는 `/`(`/api/health` 아님).

    `/api/health` 는 백엔드에 라우트가 없다(`/health` 만 등록, `EXEMPT_PATHS` 도 `/health`
    뿐) — nginx 인증을 통과해도 FastAPI 가 404 를 낸다. 그 경로로는 TLS 단계와 무관하게
    한 번도 200 이 나올 수 없었다(tester 실측, 라우트 테이블 조회로 확인).
    """
    _seed_htpasswd(repo)
    proc, calls, generated = _run_rotate(repo, rotate_fakes)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    verify = [c for c in calls if c.startswith("curl ") and " -u " in c]
    assert verify, calls
    assert all("http://127.0.0.1/" in c for c in verify), verify
    assert not any("/api/health" in c for c in verify), f"여전히 존재하지 않는 라우트를 두드린다: {verify}"


def test_rotate_when_stage1_active_then_verifies_over_https_sni_loopback(repo, rotate_fakes):
    """G-260-5n (F-1/F-5) — `.tls_enabled` 가 있으면 검증은 https(도메인 SNI, 루프백 고정)로 간다.

    1단계부터 https 로 전환해두면 이후 2단계(80→301)가 켜져도 이 스크립트는 계속 통한다.
    """
    ht = _seed_htpasswd(repo)
    (repo / TLS_MARKER).write_text("", encoding="utf-8")
    proc, calls, generated = _run_rotate(repo, rotate_fakes)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert all("$apr1$old$" not in ln for ln in ht.read_text(encoding="utf-8").splitlines())
    verify = [c for c in calls if c.startswith("curl ") and " -u " in c]
    assert verify, calls
    assert all(f"https://{DOMAIN}/" in c for c in verify), f"1단계인데 검증이 https 가 아니다: {verify}"
    assert all(f"--resolve {DOMAIN}:443:127.0.0.1" in c for c in verify), verify
    assert not any("/api/health" in c for c in verify), verify
    # G-260-5d 의 "127.0.0.1 포함" 계약은 `--resolve` 인자로도 계속 만족한다(과교정 방지).
    assert all("127.0.0.1" in c for c in verify), verify


def test_rotate_when_stage1_and_stage2_active_then_still_succeeds(repo, rotate_fakes):
    """G-260-5o (F-1 핵심 회귀) — 2단계(http→https 301)까지 켜진 최악의 조합에서도 회전이 성공한다.

    현행(수정 전) 스크립트는 `http://127.0.0.1/api/health` 하나만 두드려 이 조합에서 새
    자격·틀린 자격·무자격 전부 301 을 받는다 — 두 검증 축이 동시에 실패해 백업을 복원하고
    exit 1 이 된다(회전이 자기 사용 시점에 구조적으로 불가능했다). https 로 전환하면 막힌다.
    """
    ht = _seed_htpasswd(repo)
    (repo / TLS_MARKER).write_text("", encoding="utf-8")
    (repo / TLS2_MARKER).write_text("", encoding="utf-8")
    proc, calls, generated = _run_rotate(repo, rotate_fakes)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert all("$apr1$old$" not in ln for ln in ht.read_text(encoding="utf-8").splitlines()), (
        "2단계가 켜진 조합에서 회전이 실패해 백업이 복원됐다"
    )
    assert not _rotated_failed(repo), "성공했는데 실패 표식 파일이 남았다"


def test_rotate_when_verification_fails_then_rotated_file_marked_failed(repo, rotate_fakes):
    """G-260-5p — 검증 실패 시 `.rotated-*` 를 `.FAILED` 로 개명한다(600 유지, 비밀번호는 무효).

    개명하지 않으면 운영자가 실패 로그를 놓치고 그 안의(적용되지 않은) 비밀번호를 그대로
    클라우드 환경에 넣어 다음 자동 리포트가 조용히 401 이 될 수 있다.
    """
    _seed_htpasswd(repo)
    proc, _calls, generated = _run_rotate(repo, rotate_fakes, {"FAKE_NEW_CODE": "401"})
    assert proc.returncode != 0, proc.stdout + proc.stderr
    failed = _rotated_failed(repo)
    assert len(failed) == 1, f"실패 표식 파일이 정확히 1개가 아니다: {failed}"
    assert _mode(failed[0]) == "0o600", _mode(failed[0])
    assert _rotated(repo) == [], "실패했는데 `.rotated-*`(비개명) 가 남아 있다 — 오인 위험"
    blob = proc.stdout + proc.stderr
    for pw in generated:
        assert pw not in blob, f"실패 진단문에 비밀번호가 찍혔다: {pw!r}"


# ── 정상 경로 ───────────────────────────────────────────────────────────────

def test_rotate_when_all_green_then_every_user_in_file_gets_a_new_password(repo, rotate_fakes):
    """G-260-5a — 사용자 목록을 **파일에서 읽어** 전원을 회전한다(하드코딩 0).

    운영 htpasswd 에는 `ubuntu` 와 `reporter` 가 있고, `reporter` 를 빠뜨리면 20:20 자동 리포트
    루틴이 다음 날 조용히 401 이 된다(그날 리포트가 통째로 사라진다). 그래서 하네스는 이름이
    전혀 다른 사용자로 확인한다 — 스크립트가 파일을 읽지 않으면 여기서 0명이 회전된다.
    """
    users = ("alpha", "bravo", "charlie")
    ht = _seed_htpasswd(repo, users)
    proc, calls, generated = _run_rotate(repo, rotate_fakes)
    assert proc.returncode == 0, proc.stdout + proc.stderr

    assert len(generated) == len(users), f"생성된 비밀번호 수가 사용자 수와 다르다: {generated}"
    assert len(set(generated)) == len(generated), f"사용자끼리 비밀번호가 같다: {generated}"

    new_lines = ht.read_text(encoding="utf-8").splitlines()
    assert [ln.split(":", 1)[0] for ln in new_lines] == list(users), new_lines
    assert all("$apr1$old$" not in ln for ln in new_lines), f"해시가 그대로다: {new_lines}"
    assert all(re.search(r"passwd\b.*-apr1", c) for c in calls if c.startswith("openssl passwd")), calls


def test_rotate_when_all_green_then_backup_and_rotated_file_permissions(repo, rotate_fakes):
    """G-260-5b — 백업 644 · 새 htpasswd 644 · 회전 결과 600.

    ⚠️ nginx worker 는 컨테이너 안 **uid 101**, 호스트 파일은 uid 1000 소유다 — `.htpasswd` 를
    600 으로 두면 자격 요청이 전부 **500** 이 된다(cycle243 §10.1 F2 실측, `.token_cache` root
    소유 사고와 동일 계열). 반대로 평문 비밀번호가 담기는 `.rotated-*` 는 **600** 이어야 한다.
    """
    ht = _seed_htpasswd(repo)
    original = ht.read_text(encoding="utf-8")
    proc, _calls, generated = _run_rotate(repo, rotate_fakes)
    assert proc.returncode == 0, proc.stdout + proc.stderr

    backups = _backups(repo)
    assert len(backups) == 1, f"백업이 1개가 아니다: {backups}"
    assert backups[0].read_text(encoding="utf-8") == original, "백업 내용이 원본과 다르다"
    assert _mode(backups[0]) == "0o644", _mode(backups[0])
    assert _mode(ht) == "0o644", f"새 htpasswd 권한이 644 가 아니다(600 이면 전면 500): {_mode(ht)}"

    rotated = _rotated(repo)
    assert len(rotated) == 1, f"회전 결과 파일이 1개가 아니다: {rotated}"
    assert _mode(rotated[0]) == "0o600", f"평문 비밀번호 파일이 600 이 아니다: {_mode(rotated[0])}"
    body = rotated[0].read_text(encoding="utf-8")
    for user in _DEFAULT_USERS:
        assert user in body, f"회전 결과에 {user} 가 없다: {body!r}"
    for pw in generated:
        assert pw in body, "회전 결과 파일에 새 비밀번호가 없다(운영자가 갱신할 값이 사라진다)"


def test_rotate_when_all_green_then_password_never_printed_to_stdout(repo, rotate_fakes):
    """G-260-5c — 생성된 비밀번호가 stdout/stderr 에 **한 번도** 찍히지 않는다.

    운영자는 이 스크립트를 SSH 세션에서 돌린다 — 화면에 찍히면 스크롤백·터미널 로그·화면
    공유에 남는다. 전달 경로는 600 파일 하나뿐이고, 그래서 사용 절차의 마지막이 그 파일 삭제다.
    """
    _seed_htpasswd(repo)
    proc, _calls, generated = _run_rotate(repo, rotate_fakes)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    blob = proc.stdout + proc.stderr
    for pw in generated:
        assert pw not in blob, f"비밀번호가 화면에 찍혔다: {pw!r}"


def test_rotate_when_all_green_then_new_and_invalid_credentials_are_probed(repo, rotate_fakes):
    """G-260-5d — 검증은 두 축이다: 새 자격 200 **그리고** 잘못된 자격 401.

    새 자격만 확인하면 "auth_basic 이 통째로 빠져 아무 자격이나 200" 인 구성을 성공으로 본다.
    (옛 자격은 해시만 남아 있어 스크립트가 평문을 알 수 없다 — 그래서 '옛 자격' 대신 **의도적으로
    틀린 자격**으로 인증이 여전히 강제되는지 잰다.)
    파일은 요청 시점에 열리므로 nginx reload 는 필요 없다 — 루프백으로 즉시 재면 된다.
    """
    _seed_htpasswd(repo)
    proc, calls, generated = _run_rotate(repo, rotate_fakes)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    creds = [c.split(" -u ", 1)[1].split()[0] for c in calls if c.startswith("curl ") and " -u " in c]
    assert creds, f"자격을 실은 curl 이 없다: {calls}"
    valid = [c for c in creds if c.split(":", 1)[-1] in generated]
    invalid = [c for c in creds if c.split(":", 1)[-1] not in generated]
    assert len(valid) >= len(_DEFAULT_USERS), f"새 자격 검증이 사용자 수보다 적다: {creds}"
    assert invalid, f"잘못된 자격 검증(401 기대)이 없다: {creds}"
    assert all("127.0.0.1" in c or "localhost" in c for c in calls if c.startswith("curl ")), calls


# ── 실패 → 백업 복원 ─────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "env_extra",
    [{"FAKE_NEW_CODE": "401"}, {"FAKE_INVALID_CODE": "200"}],
    ids=["new-cred-rejected", "auth-not-enforced"],
)
def test_rotate_when_verification_fails_then_backup_restored(repo, rotate_fakes, env_extra):
    """G-260-5e — 검증 실패 → 원본 htpasswd 복원 + exit≠0.

    회전이 반쯤 성공한 상태(파일은 새 해시, 아무도 그 비밀번호로 못 들어감)는 **대시보드도
    20:20 루틴도 동시에 막힌** 상태다. 되돌릴 수 있을 때 되돌려야 한다.
    `FAKE_INVALID_CODE=200` 은 "인증이 아예 안 걸린 구성" — 이것을 성공으로 보면 회전이
    보안을 없애는 절차가 된다.
    """
    ht = _seed_htpasswd(repo)
    original = ht.read_text(encoding="utf-8")
    proc, _calls, generated = _run_rotate(repo, rotate_fakes, env_extra)
    assert proc.returncode != 0, proc.stdout + proc.stderr
    assert ht.read_text(encoding="utf-8") == original, "검증 실패인데 htpasswd 가 복원되지 않았다"
    assert _mode(ht) == "0o644", _mode(ht)
    # 실패 경로의 진단 메시지가 비밀번호를 흘리지 않는다(성공 경로만 막으면 절반이다).
    blob = proc.stdout + proc.stderr
    for pw in generated:
        assert pw not in blob, f"실패 진단문에 비밀번호가 찍혔다: {pw!r}"


def test_rotate_when_htpasswd_missing_then_stop_and_write_nothing(repo, rotate_fakes):
    """G-260-5f — 자격 파일이 없으면 아무것도 만들지 않고 멈춘다.

    `secrets/` 는 git 밖이라 잘못된 호스트(또는 로컬 개발기)에서 실행될 수 있다. 빈 목록으로
    진행하면 사용자 0명짜리 htpasswd 를 써서 **모든 자격을 무효화**한다.
    """
    (repo / "secrets").mkdir()
    proc, calls, generated = _run_rotate(repo, rotate_fakes)
    assert proc.returncode != 0, proc.stdout + proc.stderr
    assert generated == [], f"자격 파일이 없는데 비밀번호를 만들었다: {generated}"
    assert _backups(repo) == [] and _rotated(repo) == [], (_backups(repo), _rotated(repo))
    assert not (repo / "secrets" / ".htpasswd").exists()


# ── 정적 계약 ───────────────────────────────────────────────────────────────

def test_rotate_script_when_present_then_bash_syntax_ok_and_strict_mode():
    """G-260-5g — `bash -n` 통과 + `set -euo pipefail`."""
    _require(_ROTATE)
    proc = subprocess.run(["bash", "-n", str(_ROTATE)], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    assert re.search(r"^set -euo pipefail\s*$", _src(_ROTATE), re.M), "`set -euo pipefail` 부재"


def test_rotate_script_when_present_then_url_safe_password_and_stdin_hash():
    """G-260-5h — `openssl rand -base64 18` + `+/=` 제거 · `openssl passwd -apr1 -stdin`.

    - `+/=` 제거는 장식이 아니다 — 클라우드 루틴이 자격을 URL(`https://user:pass@host/…`)에
      넣는데 `@`·`/`·`+` 가 있으면 파싱이 깨진다(루틴 프롬프트가 실제로 경고한 문제).
    - 비밀번호를 **argv 로 넘기지 않는다**(`openssl passwd -apr1 "$PW"` · `htpasswd -b`) —
      argv 는 같은 호스트의 다른 사용자에게 `ps` 로 보이고 셸 히스토리에도 남는다.
    - `htpasswd` 는 EC2 에 없다(apache2-utils 미설치) — `openssl passwd` 가 유일한 수단이다.
    """
    code = _code(_ROTATE)
    assert re.search(r"openssl\s+rand\s+-base64\s+\d+", code), "`openssl rand -base64 <n>` 부재"
    assert re.search(r"tr\s+-d\s+['\"][^'\"]*[+/=]", code), (
        "`+/=` 제거가 없다 — URL 에 넣을 수 없는 비밀번호가 나온다"
    )
    assert re.search(r"openssl\s+passwd\b[^\n|]*-apr1", code), "`openssl passwd -apr1` 부재"
    assert re.search(r"openssl\s+passwd\b[^\n|]*-stdin", code), (
        "`-stdin` 없이 해시한다 — 비밀번호가 argv 로 새어 `ps`·히스토리에 남는다"
    )
    assert not re.search(r"\bhtpasswd\b\s+[^\n]*-\w*b", code), "`htpasswd -b` 금지(argv 유출)"


def test_rotate_script_when_present_then_no_password_on_stdout_only_file_redirect():
    """G-260-5i — `$NEW_*` 비밀번호 변수를 출력하는 줄에는 반드시 파일 리다이렉트가 있다.

    변수 이름은 `NEW_` 접두로 통일한다(합의) — 그래야 이 계약을 기계가 잴 수 있다.
    `echo`/`printf`/`log` 로 그냥 찍으면 SSH 스크롤백에 평문이 남는다. 행위 가드
    (G-260-5c)가 실행 시점을 잡고, 이 가드는 **아직 안 밟은 분기**(실패 경로의 안내문 등)까지 잡는다.
    """
    code = _code(_ROTATE)
    assert re.search(r"^\s*(?:local\s+)?NEW_\w+=", code, re.M), (
        "새 비밀번호를 담는 `NEW_*` 변수가 없다(이름 규약 — 가드가 기댈 유일한 표식)"
    )
    offenders = []
    for i, ln in enumerate(code.splitlines(), 1):
        if not re.match(r"\s*(echo|printf|log)\b", ln):
            continue
        if not re.search(r"\$\{?NEW_\w+", ln):
            continue
        if not re.search(r">>?\s*[\"']?\S", ln.split("#", 1)[0]):
            offenders.append((i, ln.strip()[:90]))
    assert not offenders, f"비밀번호를 파일 리다이렉트 없이 출력한다: {offenders}"


def test_rotate_script_when_present_then_user_list_is_not_hardcoded():
    """G-260-5j — 운영 사용자 이름(`ubuntu`·`reporter`)이 코드에 리터럴로 없다.

    행위 가드(G-260-5a)가 "파일에서 읽는가" 를 이미 잰다. 이 가드는 그 위에 얹는 것으로,
    "파일도 읽지만 목록을 하드코딩으로 보강" 하는 절충안을 막는다 — 그 절충안은 htpasswd 에
    사용자를 하나 더 넣은 날 회전에서 빠지거나, 지운 날 유령 사용자를 되살린다.
    안내 문구(`echo`/`log`)에서 이름을 언급하는 것은 허용한다.
    """
    offenders = []
    for i, ln in enumerate(_code(_ROTATE).splitlines(), 1):
        if re.match(r"\s*(echo|printf|log)\b", ln):
            continue
        if re.search(r"\b(ubuntu|reporter)\b", ln):
            offenders.append((i, ln.strip()[:90]))
    assert not offenders, f"사용자 목록을 하드코딩한다: {offenders}"


def test_rotate_script_when_present_then_atomic_replace_not_truncating_write():
    """G-260-5k — htpasswd 교체는 임시파일 + `mv` 다(직접 truncate 금지).

    `> secrets/.htpasswd` 로 직접 쓰면 그 순간부터 파일이 비어 있고, 루프 도중 스크립트가
    죽으면 **아무도 로그인할 수 없는 상태**로 남는다(대시보드 + 20:20 루틴 동시 중단).
    `mv` 는 같은 파일시스템에서 원자적이라 그 창이 없다.
    """
    code = _expanded(_ROTATE)
    assert re.search(r"^\s*mv\b[^\n]*\.htpasswd\s*$", code, re.M), (
        "임시파일을 `mv` 로 htpasswd 자리에 옮기는 줄이 없다 — 교체가 원자적이지 않다"
    )
    truncating = re.findall(r"^[^\n#]*(?<!>)>\s*\S*\.htpasswd\s*$", code, re.M)
    assert not truncating, f"htpasswd 를 직접 truncate 한다: {truncating}"


def test_rotate_script_when_scanned_then_no_secret_literals():
    """G-260-5l — 스크립트에 비밀값 리터럴이 없다(git 커밋 대상)."""
    src = _src(_ROTATE)
    assert not re.search(r"BEGIN [A-Z ]*PRIVATE KEY", src), "개인키가 스크립트에 있다"
    offenders = re.findall(
        r"^\s*(?:export\s+)?(?:API_\w*KEY|PASSWORD|PASSWD|SECRET)\s*=\s*[\"']?[A-Za-z0-9_\-]{8,}",
        src, re.M,
    )
    assert not offenders, f"비밀값 리터럴로 보이는 대입이 있다: {offenders}"
