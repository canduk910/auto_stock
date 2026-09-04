"""cycle248 — 선택적 배포 파이프라인의 **정합** 가드 (텍스트 수준).

행위 계약은 `tests/unit/deploy/test_cycle248_compose_up_changed.py` 가 가짜 docker 로 실증한다.
여기서는 그 스크립트가 배포 경로에 실제로 물려 있고, 분류 정규식이 이미지 입력의 구성적
정의(루트 Dockerfile COPY 소스 — cycle243 D-8 가 고정)와 어긋나지 않음을 못박는다.

⚠️ 실패 방향이 비대칭이다: backend 입력을 분류에서 놓치면 stale backend 가 **조용히** 돈다.
그래서 G-248-2 는 "Dockerfile 에 COPY 소스를 추가하면 이 가드가 붉어진다"는 방향으로 짜여 있다 —
분류 정규식을 같이 넓히기 전엔 배포 로직이 통과하지 못한다.
"""
from __future__ import annotations

import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]
_DEPLOY_YML = _ROOT / ".github" / "workflows" / "deploy.yml"
_SCRIPT = _ROOT / "tools" / "deploy" / "compose_up_changed.sh"
_DOCKERFILE = _ROOT / "Dockerfile"
_GITIGNORE = _ROOT / ".gitignore"


def _read(p: Path) -> str:
    assert p.is_file(), f"없다: {p}"
    return p.read_text(encoding="utf-8")


def _code_lines(text: str) -> list[str]:
    return [ln for ln in text.splitlines() if not ln.lstrip().startswith("#")]


def _dockerfile_copy_sources(text: str) -> list[str]:
    """루트 Dockerfile 의 COPY/ADD **모든** 소스 토큰(마지막 = dest 제외, `--flag` 제거, `./` 정규화).

    종전 정규식은 첫 소스만 캡처해 `COPY requirements.txt pyproject.toml ./` 같은 다중 소스와
    `ADD`·소문자 `copy` 를 못 봤다(뮤테이션 M37 escape). 스테이지 간 복사(`--from=`)는 빌드
    컨텍스트 밖이라 건너뛰되, 루트 Dockerfile 에는 없어야 한다(있으면 여기서 붉어져 재검토).
    JSON 배열 형식(`COPY ["a","b"]`)은 이 리포에서 쓰지 않으며 등장하면 실패시킨다.
    """
    out: list[str] = []
    for m in re.finditer(r"^\s*(COPY|ADD)\s+(.+?)\s*$", text, re.M | re.I):
        line = m.group(2)
        assert not line.lstrip().startswith("["), f"JSON 배열 COPY 는 가드가 파싱하지 않는다: {line!r}"
        tokens = line.split()
        flags = [t for t in tokens if t.startswith("--")]
        assert not any(f.startswith("--from") for f in flags), (
            f"루트 Dockerfile 에 스테이지 간 COPY 가 생겼다 — 분류 규칙 재검토 필요: {line!r}"
        )
        args = [t for t in tokens if not t.startswith("--")]
        assert len(args) >= 2, f"COPY/ADD 인자 부족: {line!r}"
        for src in args[:-1]:
            out.append(src[2:] if src.startswith("./") else src)
    return out


def test_dockerfile_copy_parser_when_probed_then_sees_all_sources_and_add():
    """G-248-2b — 파서 자체의 계약(자기 가드 공허성 차단): 다중 소스·ADD·소문자·플래그·`./` 정규화."""
    text = (
        "FROM python:3.12-slim\n"
        "COPY requirements.txt pyproject.toml ./\n"
        "add tests/ ./tests/\n"
        "COPY --chown=app:app ./src/ ./src/\n"
    )
    assert _dockerfile_copy_sources(text) == ["requirements.txt", "pyproject.toml", "tests/", "src/"]


def _backend_re() -> str:
    m = re.search(r"^BACKEND_RE='([^']+)'\s*$", _read(_SCRIPT), re.M)
    assert m, "스크립트에 BACKEND_RE='…' 한 줄 정의가 없다"
    return m.group(1)


def _frontend_re() -> str:
    m = re.search(r"^FRONTEND_RE='([^']+)'\s*$", _read(_SCRIPT), re.M)
    assert m, "스크립트에 FRONTEND_RE='…' 한 줄 정의가 없다"
    return m.group(1)


def test_deploy_yml_when_deploying_then_calls_selector_and_has_no_bare_compose_up():
    """G-248-1 — deploy.yml 은 `git pull` 뒤 선택 스크립트를 호출하고, 무조건 `up --build` 를
    직접 쓰지 않는다(그 한 줄이 돌아오면 cycle248 전체가 무효)."""
    code = "\n".join(_code_lines(_read(_DEPLOY_YML)))
    assert re.search(r"^\s*bash tools/deploy/compose_up_changed\.sh\s*$", code, re.M), code
    # 하이픈 표기(`docker-compose`)·다중 공백도 같은 우회다(뮤테이션 M33 escape 봉인).
    assert not re.search(r"docker(?:-|\s+)compose\b.*\bup\b", code), (
        "deploy.yml 이 compose up 을 직접 호출한다 — 선택 스크립트를 우회하는 경로"
    )
    pull = code.find("git pull origin main")
    call = code.find("bash tools/deploy/compose_up_changed.sh")
    assert 0 <= pull < call, "스크립트 호출은 git pull 뒤여야 새 로직이 실행된다"


def test_deploy_yml_when_ssh_script_then_set_e_before_git_pull():
    """G-248-11 — ssh 스크립트 블록은 `git pull` **앞**에 `set -e` 를 둔다.

    appleboy/ssh-action v1 은 set -e 를 주입하지 않는다(README: script_stop 제거). 없으면
    `git pull` 실패가 구 HEAD 로 이어져 선택 스크립트가 `already_deployed` 로 초록 배포를 만든다
    (적대 검증 재현). 스크립트 자신의 `set -euo pipefail` 은 pull 을 지키지 못한다.
    """
    import yaml
    d = yaml.safe_load(_read(_DEPLOY_YML))
    script = d["jobs"]["deploy"]["steps"][0]["with"]["script"]
    lines = [ln.strip() for ln in script.splitlines() if ln.strip() and not ln.strip().startswith("#")]
    assert "set -e" in lines, lines[:5]
    assert lines.index("set -e") < lines.index("git pull origin main"), lines[:5]


def test_backend_regex_when_dockerfile_copy_sources_then_all_matched():
    """G-248-2 — 루트 Dockerfile 의 **모든** COPY 소스가 backend 정규식에 매치된다.

    COPY 소스가 늘면(예: `COPY tests/ …`) 여기서 붉어진다 — 그게 이 가드의 존재 이유다.
    """
    pat = re.compile(_backend_re())
    sources = _dockerfile_copy_sources(_read(_DOCKERFILE))
    assert sources, "Dockerfile 에 COPY/ADD 가 없다?"
    for src in sources:
        probe = src if not src.endswith("/") else src + "anything.py"
        assert pat.search(probe), (
            f"Dockerfile COPY/ADD 소스 {src!r} 가 backend 분류에서 빠져 있다 → 그 경로 변경이 "
            "none/frontend 로 오분류돼 stale backend 가 조용히 돈다"
        )


def test_backend_regex_when_probed_then_exact_positive_and_negative_set():
    """G-248-3 — backend 정규식의 양성/음성 대표 집합(앵커 계약)."""
    pat = re.compile(_backend_re())
    for p in ["src/a.py", "src/x/y/z.py", "requirements.txt", "Dockerfile",
              "docker-compose.prod.yml", ".dockerignore", ".github/workflows/deploy.yml",
              "tools/deploy/compose_up_changed.sh"]:
        assert pat.search(p), f"양성이어야 한다: {p}"
    for p in ["srcs/a.py", "requirements-dev.txt", "frontend/Dockerfile", "docker-compose.yml",
              ".github/workflows/ci.yml", "tools/test_impact/a.py", "tests/unit/x.py",
              "docs/a.md", "CLAUDE.md", "pyproject.toml", "supabase/migrations/1.sql"]:
        assert not pat.search(p), f"음성이어야 한다: {p}"


def test_frontend_regex_when_probed_then_anchored_to_frontend_dir():
    """G-248-4 — frontend 정규식은 `frontend/` 접두에 앵커된다."""
    pat = re.compile(_frontend_re())
    assert pat.search("frontend/index.html") and pat.search("frontend/src/a.ts")
    assert not pat.search("frontendx/a.js") and not pat.search("src/frontend/a.py")


def test_script_when_modes_then_flags_match_contract():
    """G-248-5 — 모드별 compose 플래그: frontend 는 `--no-deps … frontend` 로 끝나고 `--build`,
    none 은 `--build`·`--no-deps` 없음, full 은 `--build` 있고 서비스 지정 없음."""
    code = _code_lines(_read(_SCRIPT))
    ups = [ln.strip() for ln in code if "docker compose" in ln and " up " in ln]
    assert len(ups) == 3, ups
    for u in ups:  # 공통 계약(뮤테이션 M14/M22 escape 봉인)
        assert " -d " in f" {u} " or u.endswith(" -d"), f"`-d` 누락: {u}"
        assert "--remove-orphans" in u, f"`--remove-orphans` 누락: {u}"
    full = [u for u in ups if "--no-deps" not in u and "--build" in u]
    fe = [u for u in ups if "--no-deps" in u]
    none = [u for u in ups if "--build" not in u]
    assert len(full) == 1 and len(fe) == 1 and len(none) == 1, ups
    assert fe[0].split()[-1] == "frontend" and "--build" in fe[0], fe
    assert not full[0].split()[-1] in {"frontend", "backend"}, full
    assert "--no-deps" not in none[0], none


def test_script_when_written_then_strict_mode_and_marker_after_compose():
    """G-248-6 — `set -euo pipefail` + 마커 기록은 compose 호출 **뒤**(성공 시에만)."""
    text = _read(_SCRIPT)
    assert re.search(r"^set -euo pipefail\s*$", text, re.M)
    code = "\n".join(_code_lines(text))
    last_up = max(m.start() for m in re.finditer(r"docker compose .*\bup\b", code))
    write = code.find('> "$MARKER"')
    assert write > last_up > 0, "마커 기록이 compose 호출보다 앞에 있으면 실패 배포가 '성공'으로 남는다"


def test_gitignore_when_marker_used_then_ignored():
    """G-248-7 — 마커 파일은 git 밖이다(EC2 `git pull` 이 충돌하지 않게)."""
    ignore = _read(_GITIGNORE)
    assert re.search(r"^\.deployed_sha\s*$", ignore, re.M)
    assert re.search(r"^\.deployed_sha\.attempt\s*$", ignore, re.M), "시도 마커도 git 밖이어야 한다"


def test_script_when_undecidable_then_falls_back_to_full():
    """G-248-8 — 판정 불가 사유 3종(marker_missing · marker_unknown_commit · diff_failed)이
    모두 MODE=full 로 배선돼 있다(텍스트 수준 — 행위는 T-1/T-2 가 실증)."""
    code = "\n".join(_code_lines(_read(_SCRIPT)))
    for reason in ("marker_missing", "previous_attempt_failed", "marker_unknown_commit", "diff_failed"):
        assert re.search(r'MODE="full";\s*REASON="' + reason + '"', code), reason


def test_script_when_diffing_then_nul_separated_not_quoted():
    """G-248-12 — diff 는 `-z` + NUL→개행이다. 기본 core.quotePath 는 한글·`"`·`\\` 경로를 C-quote 로
    감싸 `^src/` 앵커를 빗나가게 한다(적대 검증 3렌즈 독립 재현 — T-3 의 4 경로가 행위 실증)."""
    code = "\n".join(_code_lines(_read(_SCRIPT)))
    m = re.search(r"git diff --name-only --no-renames -z .*\| tr '\\0' '\\n'", code)
    assert m, "diff 가 -z | tr '\\0' '\\n' 형태가 아니다"


def test_script_when_deploying_then_attempt_marker_brackets_compose():
    """G-248-13 — 시도 마커는 compose 호출 **앞**에 쓰고, 성공 마커 기록 **뒤**에 지운다."""
    code = "\n".join(_code_lines(_read(_SCRIPT)))
    first_up = min(m.start() for m in re.finditer(r"docker compose .*\bup\b", code))
    attempt_write = code.find('> "$ATTEMPT"')
    marker_write = code.find('> "$MARKER"')
    attempt_rm = code.find('rm -f "$ATTEMPT"')
    assert 0 < attempt_write < first_up, "시도 마커 기록이 compose 앞에 없다"
    assert first_up < marker_write < attempt_rm, "시도 마커 삭제는 성공 마커 기록 뒤여야 한다"


def test_deploy_yml_when_concurrent_pushes_then_serialized_not_cancelled():
    """G-248-9 — Deploy 는 `concurrency.group` 으로 직렬화되고 `cancel-in-progress` 는 false 다
    (진행 중 배포를 취소하면 compose 가 중간에 끊겨 시도 마커만 남은 반쪽 상태가 된다).
    GitHub 은 그룹당 대기 1건만 유지하고 더 오래된 대기 run 을 취소하지만, 살아남은 run 의 누적
    diff 가 그 변경을 흡수하므로 유실이 아니라 지연이다. YAML 파서로 검사(키 순서·주석 비민감)."""
    import yaml
    d = yaml.safe_load(_read(_DEPLOY_YML))
    conc = d.get("concurrency")
    assert isinstance(conc, dict) and conc.get("group"), d.keys()
    assert conc.get("cancel-in-progress") is False, conc


def test_script_when_listing_changed_files_then_no_head_in_pipeline():
    """G-248-10 — 스크립트의 파이프라인에 `head` 가 없다(pipefail + SIGPIPE 중단 함정, T-16 실증)."""
    code = "\n".join(_code_lines(_read(_SCRIPT)))
    assert not re.search(r"\|\s*head\b", code), "pipefail 아래 `| head` 는 40행 초과 diff 에서 스크립트를 죽인다"
