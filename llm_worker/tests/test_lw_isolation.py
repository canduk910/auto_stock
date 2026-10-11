"""cycle446 Red — 청산 AI 섀도 워커 격리(설계 §1.2 「`journal_worker` 선례를 그대로 따른다」).

| # | 계약 |
|---|---|
| I1 | `llm_worker/**/*.py`(테스트 포함) 에 `src` import 0 |
| I2 | `llm_worker/**` 어떤 파일에도 `KIS_` 문자열 0 · KIS 호스트 0 · 체결통보 TR(`H0STCNI`) 0 |
| I2b | websocket 라이브러리 0(`websockets`·`websocket`·`aiohttp`) |
| I3 | 워커가 읽는 환경변수는 `LLM_DATABASE_URL`·`OPENAI_API_KEY`·`API_REPORTER_KEY`·`EXIT_AI_MODE`·`EXIT_AI_MODEL` 다섯뿐 · `.env`·dotenv 0 |
| I4 | `requirements.txt` 는 정확히 3줄 고정(asyncpg·httpx·openai) |
| I5 | Dockerfile — `python:3.12-slim` · `KIS_`·`.token_cache`·`.env` 0 · `src/` COPY 0 |
| I6 | 동시 요청 0 — `gather`·`create_task`·`TaskGroup`·`ensure_future`·`Thread` 0 |
| I9 | Dockerfile — root 가 아닌 사용자로 실행, `USER` 는 `ENTRYPOINT` 앞 |
| I10 | `.dockerignore` — tests·ops·`__pycache__`·`.env*` 를 빼고 `lw/`·`requirements.txt` 는 남긴다 |
| I11 | `ops/role.sql` 실행 예시의 비밀번호 생성은 `openssl rand -hex` |
"""
from __future__ import annotations

import ast
import re

import pytest

from lw_testkit import LW_DIR, REPO_ROOT, WORKER_ROOT, all_worker_files, all_worker_py, ignored, lw_sources

pytestmark = pytest.mark.unit

_DOCKERFILE = WORKER_ROOT / "Dockerfile"
_REQS = WORKER_ROOT / "requirements.txt"
_DOCKERIGNORE = WORKER_ROOT / ".dockerignore"
_ROLE_SQL = WORKER_ROOT / "ops" / "role.sql"


def test_i0_worker_package_exists():
    assert (LW_DIR / "__init__.py").is_file(), "llm_worker/lw/ 패키지가 없다"
    for mod in ("config", "http", "db", "features", "prompt", "targets", "bars",
                "exit_shadow", "outcome", "schedule", "__main__"):
        assert (LW_DIR / f"{mod}.py").is_file(), f"lw/{mod}.py 가 없다"


def test_i1_no_src_import_anywhere_in_worker():
    offenders = []
    for p in all_worker_py():
        tree = ast.parse(p.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            elif (isinstance(node, ast.Call) and isinstance(node.func, (ast.Attribute, ast.Name))
                  and getattr(node.func, "attr", getattr(node.func, "id", "")) in
                  {"import_module", "__import__"}
                  and node.args and isinstance(node.args[0], ast.Constant)
                  and isinstance(node.args[0].value, str)):
                names = [node.args[0].value]
            else:
                continue
            for n in names:
                if n == "src" or n.startswith("src."):
                    offenders.append(f"{p.relative_to(REPO_ROOT)}:{node.lineno} {n}")
    assert LW_DIR.is_dir(), "lw/ 가 없다"
    assert offenders == [], offenders


@pytest.mark.parametrize("needle", ["KIS_", "koreainvestment", "H0STCNI", ".token_cache", "token_manager"])
def test_i2_no_kis_material_in_worker_files(needle):
    assert LW_DIR.is_dir(), "lw/ 가 없다"
    hits = []
    for p in all_worker_files():
        if p.name == "test_lw_isolation.py":
            continue  # 이 파일 자신은 금지어 목록을 담는다
        if needle in p.read_text(encoding="utf-8", errors="replace"):
            hits.append(p.relative_to(REPO_ROOT).as_posix())
    assert hits == [], f"{needle!r} 가 워커 파일에 있다: {hits}"


def test_i2b_no_websocket_library():
    srcs = lw_sources()
    assert srcs, "lw/ 가 없다"
    for rel, text in srcs.items():
        tree = ast.parse(text)
        for node in ast.walk(tree):
            mods = []
            if isinstance(node, ast.Import):
                mods = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                mods = [node.module or ""]
            for m in mods:
                assert not m.startswith(("websockets", "websocket", "aiohttp")), f"{rel}: {m}"


def _env_keys(text: str) -> set:
    keys = set()
    tree = ast.parse(text)
    for node in ast.walk(tree):
        if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Attribute) \
                and node.value.attr == "environ" and isinstance(node.slice, ast.Constant):
            keys.add(str(node.slice.value))
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr == "getenv" or (
                node.func.attr == "get" and isinstance(node.func.value, ast.Attribute)
                and node.func.value.attr == "environ"
            ):
                if node.args and isinstance(node.args[0], ast.Constant):
                    keys.add(str(node.args[0].value))
    return keys


def test_i3_env_reads_are_limited_to_five_keys():
    offenders_text = ""
    keys: set = set()
    for p in all_worker_py():
        text = p.read_text(encoding="utf-8")
        if "test_lw_isolation.py" in p.name:
            continue
        keys |= _env_keys(text)
        offenders_text += text
    allowed = {"LLM_DATABASE_URL", "OPENAI_API_KEY", "API_REPORTER_KEY", "EXIT_AI_MODE", "EXIT_AI_MODEL"}
    assert keys <= allowed, keys
    assert {"LLM_DATABASE_URL", "OPENAI_API_KEY"} <= keys, keys


def test_i3b_no_dotenv_reading():
    srcs = lw_sources()
    assert srcs, "lw/ 가 없다"
    for rel, text in srcs.items():
        assert "dotenv" not in text, rel
        assert not re.search(r"""['"][^'"]*\.env['"]""", text), f"{rel}: .env 파일을 읽지 않는다"


def test_i4_requirements_exactly_three_pinned():
    assert _REQS.is_file(), "llm_worker/requirements.txt 가 없다"
    lines = [ln.split("#", 1)[0].strip() for ln in _REQS.read_text(encoding="utf-8").splitlines()]
    lines = [ln for ln in lines if ln]
    assert sorted(lines) == sorted(["asyncpg==0.30.0", "httpx==0.28.1", "openai==1.54.4"]), lines


def _docker_code_lines() -> list:
    assert _DOCKERFILE.is_file(), "llm_worker/Dockerfile 이 없다"
    return [ln.strip() for ln in _DOCKERFILE.read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.strip().startswith("#")]


def test_i5_dockerfile_base_and_no_secrets():
    code = _docker_code_lines()
    assert code[0] == "FROM python:3.12-slim", code[0]
    joined = "\n".join(code)
    assert "KIS_" not in joined and ".token_cache" not in joined and ".env" not in joined
    for ln in code:
        if re.match(r"^(COPY|ADD)\b", ln, re.I):
            srcs = [t for t in ln.split()[1:-1] if not t.startswith("--")]
            for s in srcs:
                s = s[2:] if s.startswith("./") else s
                assert s in {"requirements.txt", "lw", "lw/"}, f"이미지에 넣는 것은 requirements.txt·lw/ 뿐: {ln}"


@pytest.mark.parametrize("name", ["gather", "create_task", "TaskGroup", "ensure_future", "Thread"])
def test_i6_no_concurrency_primitives(name):
    srcs = lw_sources()
    assert srcs, "lw/ 가 없다"
    for rel, text in srcs.items():
        tree = ast.parse(text)
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr == name:
                pytest.fail(f"{rel}:{node.lineno} {name} — 동시 요청은 1개만")
            if isinstance(node, ast.Name) and node.id == name:
                pytest.fail(f"{rel}:{node.lineno} {name}")


def test_i9_dockerfile_runs_as_non_root():
    code = _docker_code_lines()
    users = [i for i, ln in enumerate(code) if re.match(r"^USER\s+", ln, re.I)]
    assert users, "Dockerfile 에 USER 가 없다 — 워커가 root 로 돈다"
    last = users[-1]
    who = code[last].split(None, 1)[1].strip().split(":")[0]
    assert who not in {"root", "0"}, f"USER {who} — root 가 아니어야 한다"
    ep = next(i for i, ln in enumerate(code) if ln.upper().startswith("ENTRYPOINT"))
    assert last < ep, "USER 는 ENTRYPOINT 앞"


def test_i10_dockerignore_keeps_context_to_the_image_inputs():
    assert _DOCKERIGNORE.is_file(), "llm_worker/.dockerignore 가 없다"
    pats = [ln.strip() for ln in _DOCKERIGNORE.read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.strip().startswith("#")]
    must_out = ["tests/test_lw_isolation.py", "ops/role.sql", "lw/__pycache__/main.cpython-312.pyc",
               "tests/__pycache__/conftest.cpython-312.pyc", ".env", ".env.local"]
    must_in = ["lw/exit_shadow.py", "lw/__init__.py", "requirements.txt", "Dockerfile"]
    assert [p for p in must_out if not ignored(p, pats)] == [], pats
    assert [p for p in must_in if ignored(p, pats)] == [], pats


def test_i11_role_sql_example_uses_hex_password():
    text = _ROLE_SQL.read_text(encoding="utf-8")
    assert "openssl rand -base64" not in text, "base64 비밀번호는 DSN 특수문자(/ + =)로 깨진다"
    assert re.search(r"openssl rand -hex \d+", text), "예시는 openssl rand -hex 로 만든 값을 쓴다"
    assert not re.search(r"llm_pw=\"?\$\(openssl", text), (
        "psql 인자 안에서 즉석 생성하면 그 값을 secrets/llm_worker.env 에 옮길 길이 없다 — 변수에 먼저 담는다")


def test_i12_code_stays_root_owned_and_read_only_for_runtime_user():
    code = _docker_code_lines()
    bad = []
    for ln in code:
        if re.match(r"^(COPY|ADD)\b", ln, re.I) and re.search(r"--ch(own|mod)\b", ln):
            bad.append(f"COPY 소유권/권한 지정: {ln}")
        if re.match(r"^RUN\b", ln, re.I):
            if re.search(r"\bchown\b", ln):
                bad.append(f"chown: {ln}")
            if re.search(r"\buseradd\b", ln) and re.search(r"(-d|--home(-dir)?)[\s=]+/app\b", ln):
                bad.append(f"실행 사용자 홈이 코드 디렉터리: {ln}")
    assert bad == [], "실행 사용자가 자기 코드를 쓸 수 있다 — " + " | ".join(bad)
