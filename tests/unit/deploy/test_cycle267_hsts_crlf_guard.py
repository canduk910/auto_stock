"""cycle267 Red (G-267) — TLS 2단계 가동 스크립트의 **HSTS 검사식**이 실제 CRLF 헤더를 읽는가.

■ 무엇이 고장났었나
`tools/ops/tls_stage2_enable.sh` 의 사후 검증은 HSTS 헤더를 이렇게 쟀다:

    printf '%s' "${RDOC}" | grep -qiE '^Strict-Transport-Security: max-age=86400\\r?$'

**GNU grep 의 `-E` 는 패턴 안의 `\\r` 을 캐리지 리턴이 아니라 리터럴 문자 `r` 로 해석한다**
(`\\` 뒤의 평범한 문자는 그 문자 자체 — GNU grep 3.11 실측). 그래서 이 패턴이 실제로 찾는 것은
`…max-age=86400` 뒤에 문자 `r` 이 0개 또는 1개 오고 줄이 끝나는 경우다. HTTP/1.1 응답 헤더는
CRLF 로 끝나므로(RFC 9112 §2.2 — `frontend/nginx.tls.conf.template` 은 `listen 443 ssl;` =
HTTP/2 아님) 줄 끝에는 언제나 CR 이 남아 있고, **HSTS 가 정상적으로 실려 있어도 이 패턴은 절대
매치되지 않는다**. 2026-09-07 21:0x EC2 실 가동이 이것 때문에 실패했다:

    [tls_stage2] 실패: 사후 검증 미통과 — 80=301 acme=404 443=401 state="State":"running"

80·ACME·443 상태코드·컨테이너 State 는 전부 통과했고 HSTS 두 줄만 걸렸다. 스크립트의 자동
원복이 설계대로 돌아 피해는 0 이고, nginx 스니펫 3파일과 템플릿은 정상이다.

■ 왜 cycle260 가드가 못 잡았나 — **단언이 약했던 게 아니라 입력이 현실과 달랐다**
`test_cycle260_tls_stage2_scripts.py::_FAKE_CURL` 이 헤더를 LF 로만 조립해서, `\\r?` 의 `?` 가
항상 "없음" 으로 매치됐다. 그 결과 `max-age=0`·`max-age=15552000`·`includeSubDomains`·헤더 부재
10개 뮤테이션 케이스가 전부 초록이었다. cycle267 이 그 하네스를 **기본 CRLF** 로 고쳤다.

■ 왜 이 파일이 자체 `grep` 심을 세우는가 (읽고 지나치지 말 것)
`\\r` 의 해석은 **grep 구현마다 다르다**:

    GNU grep 3.11 (EC2 운영 · GitHub Actions ubuntu)  →  리터럴 `r`     → 매치 안 됨(결함 발현)
    BSD grep 2.6.0-FreeBSD (macOS `/usr/bin/grep`)    →  캐리지 리턴    → 매치 됨(결함 은폐)
    ugrep (개발기 셸 별칭)                             →  캐리지 리턴    → 매치 됨(결함 은폐)

즉 이 결함은 **로컬 초록 · CI 붉음** 계열이다(cycle256 `ast.dump` sha 핀, cycle252 caplog 레벨과
같은 함정). 호스트가 무엇을 깔았는지에 따라 가드의 판정이 뒤집히면 그것은 가드가 아니다. 그래서
`fakes_gnu` 픽스처가 **운영 환경(GNU) 의미론을 강제하는 얇은 `grep` 심**을 PATH 앞에 세운다 —
패턴 인자에서 `\\r`·`\\n`·`\\t` 의 백슬래시를 떼고 진짜 grep 에 넘기는 것이 전부다(GNU 가
문서화한 "`\\` + 평범한 문자 = 그 문자" 규칙 그대로). 확정된 시정형은 이스케이프를 **한 개도**
쓰지 않으므로 이 심은 시정 후 무연산이고, 되돌아간 뮤턴트에서만 붉어진다.

■ 확정된 시정형 (Green 계약)
    HSTS_VALUE="max-age=86400"
    hsts_ok() { printf '%s' "$1" | tr -d '\\r' | grep -qiE "^Strict-Transport-Security: ${HSTS_VALUE}$"; }

CR 을 **먼저 제거**한 뒤 정확 값으로 앵커 매치한다. `tr -d '\\r'` 는 셸·grep 의 이스케이프
해석에 전혀 의존하지 않아(`tr` 자신의 POSIX 이스케이프다) CRLF·LF 양쪽에서 동일하게 동작한다.
계약 = (a) `max-age=86400` **정확히만** 통과(접두 매치 금지) (b) CRLF·LF 양쪽 동작
(c) 헤더명 대소문자 무관 (d) 초과 속성(`; includeSubDomains`)이 붙으면 실패.
"""
from __future__ import annotations

import importlib.util
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
_ENABLE = _ROOT / "tools" / "ops" / "tls_stage2_enable.sh"
_OPS_DIR = _ROOT / "tools" / "ops"
_C260_AST = _ROOT / "tests" / "unit" / "ast" / "test_cycle260_tls_stage2_assets.py"

pytestmark = pytest.mark.skipif(
    shutil.which("bash") is None or shutil.which("git") is None or shutil.which("sed") is None,
    reason="bash/git/sed 필요",
)

TLS_MARKER = ".tls_enabled"
TLS2_MARKER = ".tls_stage2"
BASE = "docker-compose.prod.yml"
TLS = "docker-compose.tls.yml"
TLS2 = "docker-compose.tls2.yml"
DOMAIN = "auto.dkstock.cloud"
HSTS_VALUE = "max-age=86400"


# ---------------------------------------------------------------------------
# cycle260 하네스 재사용 — 가짜 curl/docker/sudo/sleep 의 **단일 원본**은 저쪽이다.
# 복제하면 한쪽만 고쳐진 날 두 파일이 서로 다른 현실을 흉내 내게 된다. `tests/unit/deploy`
# 에는 `__init__.py` 가 없어 패키지 import 가 성립하지 않으므로 파일 경로로 로드한다
# (pytest 의 import 모드에 기대지 않는다 — 단독 실행에서도 같아야 한다).
# ---------------------------------------------------------------------------
def _load_c260():
    path = Path(__file__).with_name("test_cycle260_tls_stage2_scripts.py")
    if not path.exists():  # pragma: no cover - 방어
        pytest.fail(f"Red — cycle260 하네스 부재: {path}")
    spec = importlib.util.spec_from_file_location("_c260_harness", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


_C260 = _load_c260()

#: GNU grep 3.11 의미론 심 — 패턴 인자의 `\r`·`\n`·`\t` 앞 백슬래시를 떼고 진짜 grep 에 넘긴다.
#: 운영(EC2)·CI(ubuntu)는 GNU 라 이 심이 무연산에 가깝고, 개발기(macOS BSD grep / ugrep)에서만
#: 판정을 운영과 일치시킨다. 백슬래시가 든 인자에만 손대므로 옵션·파일명·이스케이프 없는
#: 패턴(`"^Location: …"`·`'"State":"[a-z]*"'`)은 그대로 지나간다.
_GNU_GREP_SHIM = """#!/usr/bin/env bash
args=()
for a in "$@"; do
  case "$a" in
    *\\\\*) args+=("$(printf '%s' "$a" | sed 's/\\\\\\([rnt]\\)/\\1/g')") ;;
    *)     args+=("$a") ;;
  esac
done
exec {real_grep} "${{args[@]}}"
"""


def _real_grep() -> str:
    found = shutil.which("grep")
    if not found:  # pragma: no cover - 방어
        pytest.skip("grep 부재")
    return found


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    r = tmp_path / "repo"
    r.mkdir()
    _C260._git(r, "init", "-q")
    (r / "README.md").write_text("x\n", encoding="utf-8")
    return r


@pytest.fixture
def fakes_gnu(tmp_path: Path):
    """cycle260 의 가짜 curl/docker/sudo/sleep + **GNU 의미론 grep 심**."""
    bin_dir = tmp_path / "gbin"
    bin_dir.mkdir()
    log = tmp_path / "calls.log"
    _C260._write_exec(bin_dir / "curl", _C260._FAKE_CURL)
    _C260._write_exec(bin_dir / "docker", _C260._FAKE_DOCKER)
    _C260._write_exec(bin_dir / "sudo", _C260._FAKE_SUDO)
    _C260._write_exec(bin_dir / "sleep", _C260._FAKE_SLEEP)
    _C260._write_exec(bin_dir / "grep", _GNU_GREP_SHIM.format(real_grep=_real_grep()))
    return bin_dir, log


@pytest.fixture
def armed(repo: Path, tmp_path: Path) -> Path:
    (repo / TLS_MARKER).write_text("", encoding="utf-8")
    live = tmp_path / "le-live"
    live.mkdir()
    (live / "fullchain.pem").write_text("cert\n", encoding="utf-8")
    return live


def _run_enable(repo: Path, fakes, live: Path, env_extra: dict[str, str] | None = None):
    return _C260._run_enable(repo, fakes, live, env_extra)


def _src() -> str:
    if not _ENABLE.exists():  # pragma: no cover - 방어
        pytest.fail(f"Red — {_ENABLE} 부재")
    return _ENABLE.read_text(encoding="utf-8")


def _code(text: str) -> str:
    """줄 전체가 주석인 줄 제거 — 설명문의 단어는 검사 대상이 아니다(cycle260 관례)."""
    return "\n".join(ln for ln in text.splitlines() if not ln.lstrip().startswith("#"))


# ===========================================================================
# G-267-1 — 실입력 양방향(CRLF·LF): 스크립트 전체 행위
# ===========================================================================
_EOLS = ["crlf", "lf"]

#: HSTS 축 뮤테이션 — 문서 응답과 정적자산 응답 **각각**. `add_header` 는 상속이 아니라
#: 대체라 location 마다 따로 붙어야 하고, 정적자산만 누락된 상태는 개발자도구를 열지 않으면
#: 보이지 않는다(cycle260 G-260-4h 와 같은 근거, 여기서는 EOL 축을 곱한다).
_HSTS_FAILURES = [
    ({"FAKE_HTTPS_HSTS": ""}, "absent-doc"),
    ({"FAKE_ASSET_HSTS": ""}, "absent-asset"),
    ({"FAKE_HTTPS_HSTS": "max-age=0"}, "max-age-0-doc"),
    ({"FAKE_ASSET_HSTS": "max-age=0"}, "max-age-0-asset"),
    ({"FAKE_HTTPS_HSTS": "max-age=864000"}, "864000-doc"),
    ({"FAKE_ASSET_HSTS": "max-age=864000"}, "864000-asset"),
    ({"FAKE_HTTPS_HSTS": "max-age=15552000"}, "15552000-doc"),
    ({"FAKE_ASSET_HSTS": "max-age=15552000"}, "15552000-asset"),
    ({"FAKE_HTTPS_HSTS": "max-age=86400; includeSubDomains"}, "includesubdomains-doc"),
    ({"FAKE_ASSET_HSTS": "max-age=86400; includeSubDomains"}, "includesubdomains-asset"),
]


@pytest.mark.parametrize("eol", _EOLS)
def test_enable_when_hsts_present_with_either_line_ending_then_activation_succeeds(
    repo, fakes_gnu, armed, eol
):
    """G-267-1a (핵심) — 정상 HSTS 응답이면 **CRLF·LF 양쪽**에서 가동이 성공한다.

    `crlf` 가 현실이다(HTTP/1.1 응답 헤더는 CRLF 로 끝난다). 이 케이스가 현행 스크립트에서
    붉은 것이 2026-09-07 EC2 가동 실패의 재현이며, 이 파일이 존재하는 이유다. `lf` 는
    "CR 을 지우는 시정이 CR 없는 입력까지 깨뜨리지 않는가" 를 재는 반대 방향 축이다 —
    한쪽만 통과하는 검사식은 다음 사고의 씨앗이다(예: `\\r` 을 필수로 만드는 시정).
    """
    proc, calls = _run_enable(repo, fakes_gnu, armed, {"FAKE_HEADER_EOL": eol})
    assert proc.returncode == 0, (
        f"[eol={eol}] HSTS 가 정상인데 가동이 실패했다 — 검사식이 실입력을 못 읽는다.\n"
        + proc.stdout + proc.stderr
    )
    assert (repo / TLS2_MARKER).exists(), f"[eol={eol}] 성공 경로인데 2단계 마커가 없다"
    assert (repo / TLS_MARKER).exists(), f"[eol={eol}] 1단계 마커가 사라졌다"
    switch = _C260._switch_ups(calls)
    assert len(switch) == 1, calls
    assert _C260._rollback_ups(calls) == [], (
        f"[eol={eol}] 성공 경로에서 원복 up 이 돌았다: {_C260._rollback_ups(calls)}"
    )


@pytest.mark.parametrize("eol", _EOLS)
@pytest.mark.parametrize(
    "env_extra", [f[0] for f in _HSTS_FAILURES], ids=[f[1] for f in _HSTS_FAILURES]
)
def test_enable_when_hsts_wrong_with_either_line_ending_then_rollback_and_exit_1(
    repo, fakes_gnu, armed, env_extra, eol
):
    """G-267-1b — 잘못된/없는 HSTS 는 **CRLF·LF 양쪽**에서 실패 + 마커 삭제 + 1단계 원복.

    값 축의 계약이 곧 정확 매치다 — `max-age=0` 은 브라우저에 HSTS **삭제**를 지시하는 값이고,
    `max-age=864000`·`15552000` 은 1주 안정 뒤 별도 결정으로만 올리기로 한 값이며,
    `; includeSubDomains` 는 접두 매치였다면 통과했을 초과 속성이다(서브도메인 전체를 되돌릴
    수 없게 잠근다). CRLF 축을 곱하는 이유는 cycle260 이 LF 만 재서 이 10건이 전부 초록이었기
    때문이다 — 값 단언은 이미 있었고, 없던 것은 **현실적인 입력**이다.
    """
    env = dict(env_extra)
    env["FAKE_HEADER_EOL"] = eol
    proc, calls = _run_enable(repo, fakes_gnu, armed, env)
    assert proc.returncode == 1, f"[eol={eol}] 잘못된 HSTS 를 통과시켰다\n" + proc.stdout + proc.stderr
    assert not (repo / TLS2_MARKER).exists(), f"[eol={eol}] 검증 실패 뒤 2단계 마커가 남았다"
    assert (repo / TLS_MARKER).exists(), (
        f"[eol={eol}] 원복이 1단계 마커까지 지웠다 — 443 이 함께 내려간다"
    )
    rollback = _C260._rollback_ups(calls)
    assert len(rollback) == 1, calls
    assert f"-f {BASE} -f {TLS} up -d --no-deps frontend" in rollback[0], rollback[0]
    assert TLS2 not in rollback[0], rollback[0]


# ===========================================================================
# G-267-2 — 검사식(`hsts_ok`) 자체의 격리 단위 검정 (이 요구의 정본)
# ===========================================================================
def _extract_hsts_ok() -> str:
    """스크립트에서 `hsts_ok` 정의 + 단순 리터럴 대입만 뽑아 실행 가능한 조각으로 만든다.

    스크립트 전체를 source 하면 `git rev-parse`·`cd`·사전 점검이 함께 돈다 — 검사식 하나만
    격리해서 재려면 부작용 없는 줄만 골라야 한다. `VAR="리터럴"`(변수·명령치환 없음)과
    함수 정의만 가져온다.
    """
    code = _code(_src())
    if not re.search(r"^\s*hsts_ok\s*\(\)", code, re.M):
        pytest.fail(
            "Red — `hsts_ok` 헬퍼가 없다. HSTS 검사는 `tr -d '\\r'` 로 CR 을 먼저 지운 뒤 "
            "정확 값으로 앵커 매치하는 이름 있는 헬퍼여야 한다(명세 §확정된 시정 설계)."
        )
    lines = code.splitlines()
    picked = [ln for ln in lines if re.match(r'^\s*[A-Z][A-Z0-9_]*="[^"$`\\]*"\s*$', ln)]

    body: list[str] = []
    depth_open = False
    for ln in lines:
        if not body and re.match(r"^\s*hsts_ok\s*\(\)", ln):
            body.append(ln)
            depth_open = "}" not in ln.split("{", 1)[-1]
            if not depth_open:
                break
            continue
        if body:
            body.append(ln)
            if re.match(r"^\s*\}\s*$", ln):
                break
    return "\n".join(picked + body)


#: (헤더 덤프, 통과해야 하는가, 라벨)
_HSTS_CASES = [
    ("HTTP/1.1 401 X\r\nServer: nginx\r\nStrict-Transport-Security: max-age=86400\r\n\r\n",
     True, "crlf-정상"),
    ("HTTP/1.1 401 X\nServer: nginx\nStrict-Transport-Security: max-age=86400\n\n",
     True, "lf-정상"),
    ("HTTP/1.1 401 X\r\nstrict-transport-security: max-age=86400\r\n\r\n",
     True, "crlf-소문자-헤더명"),
    ("HTTP/1.1 401 X\r\nStrict-Transport-Security: max-age=0\r\n\r\n",
     False, "crlf-max-age-0"),
    ("HTTP/1.1 401 X\r\nStrict-Transport-Security: max-age=864000\r\n\r\n",
     False, "crlf-864000-접두"),
    ("HTTP/1.1 401 X\r\nStrict-Transport-Security: max-age=15552000\r\n\r\n",
     False, "crlf-15552000"),
    ("HTTP/1.1 401 X\r\nStrict-Transport-Security: max-age=86400; includeSubDomains\r\n\r\n",
     False, "crlf-includeSubDomains"),
    ("HTTP/1.1 401 X\r\nServer: nginx\r\n\r\n", False, "crlf-헤더-완전-부재"),
    ("", False, "빈-응답"),
]


@pytest.mark.parametrize(
    "dump,should_pass", [(c[0], c[1]) for c in _HSTS_CASES], ids=[c[2] for c in _HSTS_CASES]
)
def test_hsts_ok_when_given_real_header_dump_then_exact_match_semantics(
    tmp_path, dump, should_pass
):
    """G-267-2 — `hsts_ok` 를 격리 실행해 6종 입력의 종료코드를 직접 잰다(요구의 정본).

    행위 가드(G-267-1)는 스크립트 전체를 통과해야 여기에 닿는다 — 그래서 다른 검증 축이
    먼저 깨지면 원인이 섞인다. 이 테스트는 검사식 **한 줄만** 떼어내 실입력 `\\r\\n` 종단
    문자열에 직접 물린다:
      · CRLF/LF 정상 → 통과(계약 b)
      · 헤더명 소문자 → 통과(계약 c — `-i` 유지. nginx 는 대소문자를 보존하지만
        HTTP 헤더명은 규격상 대소문자 무관이라 검사가 서식에 기대면 안 된다)
      · `864000` → 실패(계약 a — 끝 앵커가 없으면 `86400` 의 접두 매치로 통과한다)
      · `; includeSubDomains` → 실패(계약 d)
      · 부재/빈 응답 → 실패
    GNU 의미론 심을 PATH 앞에 세워 개발기(BSD grep·ugrep)와 운영(GNU grep)의 판정이
    갈리지 않게 한다 — 이 결함 자체가 그 divergence 로 CI 에서만 드러난 계열이다.
    """
    snippet = _extract_hsts_ok()
    bin_dir = tmp_path / "sbin"
    bin_dir.mkdir()
    _C260._write_exec(bin_dir / "grep", _GNU_GREP_SHIM.format(real_grep=_real_grep()))

    script = snippet + '\nhsts_ok "$1"\n'
    env = dict(os.environ)
    env["PATH"] = f"{bin_dir}{os.pathsep}{env['PATH']}"
    proc = subprocess.run(
        ["bash", "-c", script, "_", dump], capture_output=True, text=True, env=env
    )
    ok = proc.returncode == 0
    assert ok is should_pass, (
        f"hsts_ok 판정이 계약과 다르다(기대 {'통과' if should_pass else '실패'}, "
        f"실측 rc={proc.returncode}) — 입력={dump!r}\nstderr={proc.stderr}"
    )


# ===========================================================================
# G-267-3 — 회귀 계열 차단(영구): grep 패턴에 백슬래시 이스케이프 금지
# ===========================================================================
def _strip_ansi_c(line: str) -> str:
    """`$'...'`(ANSI-C 인용) 구간 제거 — 그 안의 이스케이프는 **셸이** 해석하므로 안전하다."""
    return re.sub(r"\$'(?:[^'\\]|\\.)*'", "", line)


_QUOTED = re.compile(r"'([^']*)'|\"([^\"]*)\"")
_BAD_ESCAPE = re.compile(r"\\[rnt]")
#: 파이프라인·리스트 구분자. 마스킹된 줄에서만 쓴다(따옴표 안의 `|` 에 걸리지 않도록).
_SEGMENT_SPLIT = re.compile(r"\|\||&&|[|;()]")


def _grep_pattern_literals(line: str) -> list[str]:
    """한 줄에서 **grep 자신의 인자인** 따옴표 리터럴만 뽑는다.

    줄 단위로 훑으면 같은 파이프라인의 이웃 명령까지 잡힌다 — 확정된 시정형
    `… | tr -d '\\r' | grep -qiE "…"` 이 정확히 그 모양이고, `tr` 의 `'\\r'` 은 `tr` 자신이
    POSIX 규격대로 해석하는 **정답**이지 결함이 아니다. 그래서 리터럴을 자리표시자로 가린
    뒤 파이프라인 구분자로 쪼개고, `grep` 이 명령어인 조각만 되돌려 검사한다.
    """
    holes: list[str] = []

    def _mask(m: re.Match[str]) -> str:
        holes.append(m.group(1) if m.group(1) is not None else m.group(2))
        return f"\x00{len(holes) - 1}\x00"

    masked = _QUOTED.sub(_mask, _strip_ansi_c(line))
    out: list[str] = []
    for seg in _SEGMENT_SPLIT.split(masked):
        # 리다이렉션·대입을 건너뛴 뒤 첫 낱말이 grep 인 조각만 본다(`grep` 이 인자로
        # 등장하는 `crontab -l | grep -v channel_probe.sh` 류의 문자열은 제외된다).
        if not re.match(r"\s*(?:[A-Za-z_][A-Za-z0-9_]*=\S*\s+)*(?:command\s+)?grep\b", seg):
            continue
        for idx in re.findall(r"\x00(\d+)\x00", seg):
            out.append(holes[int(idx)])
    return out


def test_ops_scripts_when_scanned_then_no_backslash_escapes_in_grep_patterns():
    """G-267-3 (영구) — `tools/ops/*.sh` 의 grep 패턴 인자에 `\\r`·`\\n`·`\\t` 가 없다.

    **GNU grep 의 `-E`/`-G` 는 이 이스케이프를 캐리지리턴·개행·탭이 아니라 리터럴 문자
    `r`·`n`·`t` 로 해석한다**(`\\` + 평범한 문자 = 그 문자, GNU grep 3.11 실측). BSD grep
    (macOS)·ugrep 은 반대로 제어문자로 해석해서, 같은 패턴이 개발기에서는 매치되고 운영
    EC2 에서는 매치되지 않는다 — 로컬 초록·CI/운영 붉음 계열의 정확한 원인이다.

    **CRLF 를 재려면 패턴에 이스케이프를 쓰지 말고 `tr -d '\\r'` 로 정규화하라.** `tr` 의
    이스케이프는 `tr` 자신이 POSIX 규격대로 해석하므로 구현 간 차이가 없다.

    (`grep -P` 는 PCRE 라 `\\r` 이 캐리지 리턴이지만, 이 저장소의 운영 스크립트는 `-P` 를
    쓰지 않고 alpine/busybox 환경에서는 `-P` 자체가 없다 — 예외를 두지 않는다.)
    """
    scripts = sorted(_OPS_DIR.glob("*.sh"))
    assert scripts, f"검사 대상이 없다: {_OPS_DIR}"
    offenders: list[str] = []
    for path in scripts:
        for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if raw.lstrip().startswith("#"):
                continue
            if not re.search(r"\bgrep\b", raw):
                continue
            for literal in _grep_pattern_literals(raw):
                if _BAD_ESCAPE.search(literal):
                    offenders.append(f"{path.name}:{lineno}: {raw.strip()[:110]}")
    assert not offenders, (
        "grep 패턴에 백슬래시 이스케이프가 있다 — GNU grep 은 이를 리터럴 문자로 읽어 "
        "제어문자를 절대 매치하지 못한다. `tr -d '\\r'` 로 정규화하라:\n  "
        + "\n  ".join(offenders)
    )


# ===========================================================================
# G-267-4 — 설계 핀
# ===========================================================================
def test_enable_script_when_present_then_normalizes_cr_before_matching():
    """G-267-4a — `tr -d '\\r'` 정규화가 존재하고, 옛 `\\r?$` 패턴은 0건이다.

    행위 가드가 "무엇을 하는가" 를 재고, 이 핀은 "어떻게 해야 하는가" 를 고정한다 — 다른
    방식(`grep -P`·`sed`·`${VAR%$'\\r'}`)으로 우회하면 구현·환경 의존이 다시 들어온다.
    """
    code = _code(_src())
    assert re.search(r"\btr\s+-d\s+'\\r'", code), (
        "Red — `tr -d '\\r'` 정규화가 없다(CR 을 지우지 않으면 어떤 앵커 매치도 실패한다)"
    )
    stale = [ln.strip() for ln in code.splitlines() if r"\r?" in ln]
    assert not stale, f"Red — 옛 `\\r?$` 패턴이 남아 있다: {stale}"


def test_enable_script_when_present_then_single_hsts_literal_matching_ast_guard():
    """G-267-4b — HSTS 값 리터럴이 `max-age=86400` 하나뿐이고 cycle260 AST 핀과 일치한다.

    스니펫(`tools/ops/tls_stage2/*.conf`)이 내보내는 값과 스크립트가 검사하는 값이 어긋나면
    가동이 영원히 실패하거나(엄격) 아무것도 못 잡는다(느슨). 두 자리의 정본은 cycle260 AST
    가드의 `HSTS_MAX_AGE` 이므로 **파일에서 읽어** 대조한다 — 여기에 숫자를 또 적으면
    핀이 세 곳으로 늘어나 다음 상향(1주 안정 후 HSTS 값 조정) 때 한 곳이 남는다.
    """
    ast_src = _C260_AST.read_text(encoding="utf-8")
    m = re.search(r"^HSTS_MAX_AGE\s*=\s*(\d+)\s*$", ast_src, re.M)
    assert m, f"cycle260 AST 가드에서 HSTS_MAX_AGE 를 못 읽었다: {_C260_AST}"
    expected = f"max-age={m.group(1)}"
    assert expected == HSTS_VALUE, (
        f"cycle260 AST 핀({expected})과 이 파일의 상수({HSTS_VALUE})가 어긋났다 — 둘 다 고쳐라"
    )
    ages = sorted(set(re.findall(r"max-age=(\d+)", _code(_src()))))
    assert ages == [m.group(1)], f"스크립트의 max-age 리터럴이 {expected} 하나가 아니다: {ages}"


def test_hsts_ok_when_defined_then_pattern_is_anchored_and_escape_free():
    """G-267-4c — `hsts_ok` 의 grep 패턴이 끝 앵커 `$` 로 닫히고 이스케이프가 없다.

    끝 앵커가 없으면 `max-age=864000`·`max-age=86400; includeSubDomains` 가 접두로 통과한다
    (G-267-2 가 행위로 잡고, 이 핀은 아직 안 밟은 분기까지 소스에서 잡는다).
    """
    snippet = _extract_hsts_ok()
    grep_lines = [ln for ln in snippet.splitlines() if re.search(r"\bgrep\b", ln)]
    assert grep_lines, f"Red — hsts_ok 안에 grep 호출이 없다: {snippet!r}"
    patterns: list[str] = []
    for ln in grep_lines:
        for literal in _grep_pattern_literals(ln):
            if "Strict-Transport-Security" in literal:
                patterns.append(literal)
    assert patterns, f"Red — HSTS 헤더명을 담은 패턴을 못 찾았다: {grep_lines}"
    for pat in patterns:
        assert not _BAD_ESCAPE.search(pat), f"패턴에 백슬래시 이스케이프가 있다: {pat!r}"
        assert pat.startswith("^"), f"패턴에 시작 앵커가 없다: {pat!r}"
        assert pat.endswith("$"), (
            f"패턴에 끝 앵커가 없다 — 접두 매치로 초과 값이 통과한다: {pat!r}"
        )
