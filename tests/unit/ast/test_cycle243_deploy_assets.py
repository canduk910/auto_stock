"""cycle243 Red (D/Phase 1) — nginx Basic Auth 배포 자산 정적 가드.

명세: `_workspace/red/cycle243_api_auth_spec.md` §3.D(D-1~D-5, D-7, D-8) · §2.1 · §6.1

## 왜 정적 가드가 유일한 자동 가드인가 (L4)

프론트 vitest 는 jsdom+MSW, Playwright 는 vite dev server + `page.route` 모킹이라
**둘 다 nginx 를 경유하지 않는다**. Phase 1 의 실동작 검증은 배포 후 수동 curl(§6.2)
뿐이고, 리포 안에서 회귀를 잡을 수 있는 것은 이 파일의 텍스트 수준 가드가 전부다.

## 파일 분리 사유 (명세 문언과 다른 곳 — 반드시 읽을 것)

명세 §3.D 는 D-1~D-11 을 한 파일로 적었는데, §6.1 P1-1 커밋 화이트리스트는 같은
파일을 "(D-1~D-5, D-7~D-8 부분)" 으로만 담는다. 한 파일이면 **Phase 1 커밋의 CI 가
D-6/D-9/D-10/D-11(Phase 2 자산)로 빨간불**이 되어 배포가 막힌다. 그래서 Phase 2
항목은 `test_cycle243_phase2_assets.py` 로 분리했다 — 커밋 단위와 가드 단위를 일치.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parents[3]
_TEMPLATE = _ROOT / "frontend" / "nginx.conf.template"
_LEGACY_CONF = _ROOT / "frontend" / "nginx.conf"
_FE_DOCKERFILE = _ROOT / "frontend" / "Dockerfile"
_COMPOSE_PROD = _ROOT / "docker-compose.prod.yml"
_DOCKERIGNORE = _ROOT / ".dockerignore"
_ROOT_DOCKERFILE = _ROOT / "Dockerfile"
_GITIGNORE = _ROOT / ".gitignore"

HTPASSWD_PATH = "/etc/nginx/secrets/.htpasswd"


def _read(path: Path) -> str:
    if not path.exists():
        pytest.fail(f"Red — {path.relative_to(_ROOT)} 부재 (명세 §2.1)")
    return path.read_text(encoding="utf-8")


def _strip_comments(text: str) -> str:
    return "\n".join(line.split("#", 1)[0] for line in text.splitlines())


def _depth_at(text: str, idx: int) -> int:
    """idx 위치의 중괄호 중첩 깊이. server 직속 = 1, location 안 = 2."""
    return text.count("{", 0, idx) - text.count("}", 0, idx)


def _block_body(text: str, header_pattern: str) -> str | None:
    match = re.search(header_pattern, text)
    if not match:
        return None
    open_idx = text.index("{", match.start())
    depth = 0
    for i in range(open_idx, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[open_idx + 1 : i]
    return None


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text)


def _frontend_service() -> dict:
    data = yaml.safe_load(_read(_COMPOSE_PROD))
    service = (data.get("services") or {}).get("frontend")
    assert service, "docker-compose.prod.yml 에 frontend 서비스가 없다"
    return service


def _env_entries(service: dict) -> list[str]:
    env = service.get("environment") or []
    if isinstance(env, dict):
        return [f"{k}={v}" for k, v in env.items()]
    return [str(e) for e in env]


# ---------------------------------------------------------------------------
# D-1 / D-2 / D-3 — nginx 템플릿
# ---------------------------------------------------------------------------
#: `auth_basic <realm>;` — realm 은 **따옴표 문자열**이어야 한다. `auth_basic off;` 는
#: 상속을 끊어 그 경로를 무인증으로 만든다(아래 D-1-b 가 별도로 금지한다).
_AUTH_BASIC_REALM = r'\bauth_basic\s+"[^"]+"\s*;'
_AUTH_BASIC_OFF = r"\bauth_basic\s+off\s*;"


def test_template_when_present_then_auth_basic_at_server_and_api_location():
    """D-1 — `auth_basic` 이 **server 레벨과 `/api/` location 양쪽**에 있다.

    server 레벨만 두면 상속으로 걸리지만, 새 location 이 추가될 때 `auth_basic off;`
    나 별도 블록으로 조용히 새는 경로가 생긴다. 양쪽 명시가 방어 심층화 계약이다.
    M-16(둘 중 하나 삭제)이 여기서 죽는다.

    ⚠️ 패턴은 **realm 문자열까지** 요구한다. 종전의 느슨한 `auth_basic` 접두 패턴은
    `auth_basic off;`
    에도 매치해서, 이 파일이 스스로 위협으로 적어둔 우회(`off` 로 상속 끊기)를 하나도
    잡지 못했다(자기 가드 공허성 — cycle224 교훈).
    """
    text = _strip_comments(_read(_TEMPLATE))

    server_level = [
        m.start()
        for m in re.finditer(_AUTH_BASIC_REALM, text)
        if _depth_at(text, m.start()) == 1
    ]
    assert server_level, "server 레벨 auth_basic realm 부재 — 새 location 이 무인증으로 샌다"

    api_block = _block_body(text, r"location\s+/api/\s*\{")
    assert api_block is not None, "`location /api/` 블록을 찾지 못했다"
    assert re.search(_AUTH_BASIC_REALM, api_block), "/api/ location 에 auth_basic realm 부재"
    assert HTPASSWD_PATH in api_block, f"/api/ location 의 user_file 이 {HTPASSWD_PATH} 아님"

    # ③ — 파일이 아니라 **디렉터리** 를 마운트한다(bind mount 소스 부재 시 Docker 가
    # 빈 디렉터리를 만들어 "파일이 디렉터리가 되는" 상태를 막는다).
    assert f"auth_basic_user_file {HTPASSWD_PATH}" in _norm(text)


def test_template_when_present_then_no_auth_basic_off_anywhere():
    """D-1-b — `auth_basic off;` **0건**(server·location 무관).

    실 nginx 기동 검증: `location = /api/bypass { auth_basic off; ... }` 한 블록이면
    무자격 요청이 **200** 을 받는다. `/api/` 아래라면 nginx 가 유효 `X-API-Key` 까지
    주입하므로 **Phase 2 백엔드 인증도 같이** 무력화된다 — 두 층이 한 줄로 동시에
    열리는 유일한 경로라 텍스트 수준에서 원천 금지한다(실기동 가드는 리포에 없다, L4).
    """
    text = _strip_comments(_read(_TEMPLATE))
    offenders = [m.group(0) for m in re.finditer(_AUTH_BASIC_OFF, text)]
    assert not offenders, f"`auth_basic off;` 가 인증을 끊는다: {offenders}"


def test_template_when_proxying_then_preserves_original_host_port():
    """D-2-b — `proxy_set_header Host $http_host;` (≠ `$host`).

    `$host` 는 **포트를 떨어뜨린다**(실측: 클라이언트 `Host: 127.0.0.1:8080` → 업스트림
    `Host: 127.0.0.1`). 그러면 백엔드의 상태변경 Origin 검사가 `Origin:
    http://127.0.0.1:8080` 과 불일치해 **전부 `cross_origin` 401** 이 된다 — 80 이 아닌
    포트로 붙는 가장 현실적인 경로가 SSH 터널이고, 후속 F2(SG 80 을 운영자 IP 로 제한)를
    채택하면 그게 표준 접근이 된다. 실패가 조용하다(UI 401 처리 부재, L10).
    """
    normalized = _norm(_strip_comments(_read(_TEMPLATE)))
    assert "proxy_set_header Host $http_host;" in normalized, normalized
    assert "proxy_set_header Host $host;" not in normalized, (
        "`$host` 는 포트를 떨어뜨려 비-80 포트 접근의 상태변경을 전부 401 로 만든다"
    )


def test_template_when_present_then_injects_api_key_header():
    """D-2 — `proxy_set_header X-API-Key $api_key_for_user;` + 사용자별 `map` 존재.

    `proxy_set_header` 는 클라이언트가 보낸 동명 헤더를 **치환**하므로 헤더 밀반입이
    불가능하다(§2.1 주석 · 수동 검증 V7). 브라우저에는 키가 노출되지 않는다.

    cycle249 재스코프 — 치환 구문이 `proxy_set_header` 줄에서 `map $remote_user
    $api_key_for_user { ... }` 블록(Basic 사용자별 키 선택)으로 이동했다. 이 가드는
    이제 리터럴 값이 아니라 **변수 배선**(map 존재 + 주입 줄이 그 변수를 씀)을 본다.
    """
    normalized = _norm(_strip_comments(_read(_TEMPLATE)))
    assert "map $remote_user $api_key_for_user {" in normalized, normalized
    assert "proxy_set_header X-API-Key $api_key_for_user;" in normalized, normalized


def test_legacy_nginx_conf_when_migrated_then_absent():
    """D-3 — 구 `frontend/nginx.conf` 삭제.

    남겨두면 (a) Dockerfile 의 구 COPY 가 되살아나 **인증 없는 구버전이 조용히
    서빙되는 fail-open** 이 되고 (b) 다음 사람이 어느 쪽이 정본인지 알 수 없다.
    """
    assert not _LEGACY_CONF.exists(), (
        "frontend/nginx.conf 가 아직 있다 — 템플릿과 이중 정본(드리프트)"
    )


# ---------------------------------------------------------------------------
# D-4 — frontend Dockerfile
# ---------------------------------------------------------------------------
def test_frontend_dockerfile_when_templated_then_copies_into_templates_dir():
    """D-4 — `default.conf.template` 만이 스톡 `default.conf` 를 덮어쓴다.

    `nginx:alpine` 엔트리포인트 기본값 = TEMPLATE_DIR `/etc/nginx/templates` ·
    SUFFIX `.template` · OUTPUT_DIR `/etc/nginx/conf.d`. 다른 이름이면 스톡 server
    블록이 80 에 공존한다. M-17(구 COPY 부활)이 여기서 죽는다.
    """
    text = _read(_FE_DOCKERFILE)
    assert re.search(
        r"^COPY\s+nginx\.conf\.template\s+/etc/nginx/templates/default\.conf\.template\s*$",
        text,
        re.M,
    ), text
    assert not re.search(r"^COPY\s+[^\n]*conf\.d/default\.conf", text, re.M), (
        "구 `COPY nginx.conf /etc/nginx/conf.d/default.conf` 가 남아 있다"
    )


# ---------------------------------------------------------------------------
# D-5 — docker-compose.prod.yml frontend 블록
# ---------------------------------------------------------------------------
def test_compose_frontend_when_configured_then_secrets_and_filtered_envsubst():
    """D-5 — 볼륨·환경변수·**env_file 부재**.

    `NGINX_ENVSUBST_FILTER` 는 앵커(`^…$`)가 필수다 — 스크립트가 `awk … name ~ filter`
    로 **부분 일치** 평가하므로 앵커 없이 쓰면 `API_AUTH_KEY_OLD` 류까지 걸린다.
    `env_file: .env` 는 KIS·OPENAI 등 33개 비밀을 nginx 컨테이너 환경에 밀어 넣는다.
    M-18(FILTER 제거)·M-19(env_file 추가)가 여기서 죽는다.
    """
    service = _frontend_service()
    entries = _env_entries(service)

    assert "API_AUTH_KEY=${API_AUTH_KEY}" in entries, entries
    # cycle249 — 리포터 스코프 키(map $remote_user 가 소비) + FILTER 가 2변수 앵커.
    assert "API_REPORTER_KEY=${API_REPORTER_KEY}" in entries, entries
    assert "NGINX_ENVSUBST_FILTER=^API_(AUTH|REPORTER)_KEY$" in entries, entries
    assert "env_file" not in service, (
        "frontend 에 env_file 이 붙었다 — 33개 비밀이 nginx 컨테이너로 샌다"
    )

    volumes = [str(v) for v in (service.get("volumes") or [])]
    assert "./secrets:/etc/nginx/secrets:ro" in volumes, volumes


#: Phase 2 전용 가드 파일. **커밋 동반 여부**가 곧 "지금이 Phase 1 인가 Phase 2 인가"의
#: 유일한 리포 내 신호다(D-5-c 참조).
_PHASE2_GUARD = _ROOT / "tests" / "unit" / "ast" / "test_cycle243_phase2_assets.py"


def test_compose_backend_when_phase1_then_untouched_block_shape():
    """D-5-b(①의 전제) — backend 서비스 config 의 **ports 를 뺀 전 형태**를 고정한다.

    compose 재생성 조건 = (이미지 ID 변경) ∨ (서비스 config 해시 변경) ∨
    `--force-recreate`. backend 블록을 한 줄이라도 바꾸면 **백엔드가 재시작**되고
    cycle232 D6(장중 push 금지 — tick blind 손절 사각)가 즉시 되살아난다.

    ⚠️ **`ports` 는 이 가드가 볼 수 없다** — 이 사이클의 유일한 backend 변경이 바로
    그 줄이고 Phase 2 의 D-6 이 반대 값을 요구하므로 정적 가드로는 양립이 불가능하다.
    종전에는 `env_file`·`build.target` 둘만 보느라 `environment` 추가·`volumes` 변경
    같은 현실적인 실수도 통과했다(사실상 공허). 여기서는 **키 집합과 값 전부**를
    ports 만 빼고 못박고, ports 축은 D-5-c 가 Phase 짝짓기로 따로 막는다.
    """
    data = yaml.safe_load(_read(_COMPOSE_PROD))
    backend = (data.get("services") or {}).get("backend")
    assert backend, "backend 서비스가 사라졌다"

    assert set(backend) == {"build", "ports", "volumes", "env_file", "environment", "restart"}, (
        f"backend 서비스 키 집합이 바뀌었다(= config 해시 변경 = 재시작): {sorted(backend)}"
    )
    assert backend.get("build") == {"context": ".", "target": "prod"}
    assert backend.get("env_file") == ".env"
    assert backend.get("restart") == "unless-stopped"
    assert [str(v) for v in (backend.get("volumes") or [])] == [
        "./logs:/app/logs",
        "./.token_cache:/app/.token_cache",
    ]
    assert _env_entries(backend) == ["PORT=8000", "TZ=Asia/Seoul"]


def test_compose_backend_ports_when_committed_then_paired_with_phase2_guard():
    """D-5-c — backend `ports` 변경은 **Phase 2 가드 파일과 반드시 동반 커밋**된다.

    문제는 이렇다: `docker-compose.prod.yml` 한 파일이 Phase 1(frontend 블록)과
    Phase 2(backend `ports` → `127.0.0.1`)를 함께 담는데, git 은 파일 단위이고 이
    실행 환경엔 `git add -p` 가 없다. 통째 `git add` 한 번이면 Phase 1 커밋에 backend
    config 해시 변경이 딸려 가 **장중 백엔드 재시작**(13포지션 tick blind)이 된다.

    그래서 "루프백 바인딩" 과 "Phase 2 가드 파일 존재" 를 **동치**로 묶는다. Phase 1
    커밋이 ports hunk 를 실수로 데려가면(= 루프백인데 Phase 2 가드 파일은 미커밋)
    체크아웃된 트리에서 이 케이스가 FAIL 하고 CI 가 배포를 막는다. 반대 방향(Phase 2
    가드만 커밋되고 ports 는 종전)도 같은 이유로 막는다 — D-6 이 요구하는 값과
    실제 배포 상태가 갈리는 상태이기 때문이다.
    """
    data = yaml.safe_load(_read(_COMPOSE_PROD))
    backend = (data.get("services") or {}).get("backend") or {}
    ports = [str(p) for p in (backend.get("ports") or [])]

    loopback = "127.0.0.1:8000:8000" in ports
    phase2_present = _PHASE2_GUARD.exists()

    if loopback:
        assert phase2_present, (
            "backend 를 루프백에 묶는 Phase 2 변경이 Phase 2 가드 파일 없이 커밋됐다 — "
            "Phase 1 커밋에 backend config 해시 변경이 섞였다(장중 재시작 = cycle232 D6 위반)"
        )
    else:
        assert ports == ["8000:8000"], (
            f"Phase 1 상태의 backend ports 는 종전 값이어야 한다: {ports}"
        )
        assert not phase2_present, (
            "Phase 2 가드는 커밋됐는데 backend ports 가 종전이다 — D-6 과 실제 배포가 갈린다"
        )


# ---------------------------------------------------------------------------
# D-7 — 비밀 미커밋
# ---------------------------------------------------------------------------
def test_secrets_when_gitignored_then_no_htpasswd_tracked():
    """D-7 — `.gitignore` 에 `secrets/` ∧ 추적 파일에 `.htpasswd` 0건."""
    ignore = _read(_GITIGNORE)
    assert re.search(r"^/?secrets/\s*$", ignore, re.M), (
        ".gitignore 에 `secrets/` 가 없다 — htpasswd 가 커밋될 수 있다"
    )

    tracked = subprocess.run(
        ["git", "ls-files"], cwd=_ROOT, capture_output=True, text=True, check=True
    ).stdout.splitlines()
    leaked = [p for p in tracked if ".htpasswd" in p or p.startswith("secrets/")]
    assert not leaked, f"비밀 파일이 git 에 추적되고 있다: {leaked}"


# ---------------------------------------------------------------------------
# D-8 — Phase 1 무재시작 전제 고정
# ---------------------------------------------------------------------------
def test_build_context_when_phase1_then_backend_image_inputs_unchanged():
    """D-8 — `.dockerignore` 가 `frontend/` 를 제외 ∧ 루트 Dockerfile 의 COPY 입력이
    `requirements.txt` · `src/` 뿐.

    이 두 사실이 "Phase 1 파일은 어느 COPY 레이어의 입력도 아니다 → BuildKit 캐시 전부
    히트 → 동일 이미지 ID" 의 전제다(①).

    ⚠️ cycle248(2026-09-04) 정정 — 동일 이미지 ID 여도 Compose v5.1 `up --build` 는 backend
    컨테이너를 **재생성한다**(재태그 → LastTagTime 갱신, 실측). 그래서 "→ 미재생성 → D6 미적용"
    결론은 거짓이었고, 무재시작은 `tools/deploy/compose_up_changed.sh` 가 diff 로 backend 입력
    무변경을 판정해 `--no-deps frontend` 로 올릴 때만 성립한다. 이 가드의 COPY 소스 집합은 이제
    그 분류 정규식의 **정합 근거**다(`test_cycle248_deploy_pipeline.py::G-248-2` 가 교차 검사).
    """
    ignore = _read(_DOCKERIGNORE)
    assert re.search(r"^frontend/\s*$", ignore, re.M), ignore

    dockerfile = _read(_ROOT_DOCKERFILE)
    # cycle248 — 첫 소스만 캡처하던 종전 정규식은 `COPY requirements.txt pyproject.toml ./` 같은
    # 다중 소스·ADD 를 못 봤다(뮤테이션 escape). 모든 소스 토큰(dest 제외, 플래그 제거)을 본다.
    sources: list[str] = []
    for m in re.finditer(r"^\s*(COPY|ADD)\s+(.+?)\s*$", dockerfile, re.M | re.I):
        args = [t for t in m.group(2).split() if not t.startswith("--")]
        sources.extend(a[2:] if a.startswith("./") else a for a in args[:-1])
    assert set(sources) == {"requirements.txt", "src/"}, sources
