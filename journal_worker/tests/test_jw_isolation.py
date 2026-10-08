"""cycle412 Red — 워커 격리(설계 관찰자안 5절 ⑤·③·④, 3절 「워커 컨테이너」).

| # | 계약 |
|---|---|
| I1 | `journal_worker/**/*.py`(테스트 포함) 에 `src` import 0 — 하면 `Settings` 가 KIS 키를 요구하고 싱글턴이 생긴다 |
| I2 | `journal_worker/**` 어떤 파일에도 `KIS_` 문자열 0 · KIS 호스트 0 · 체결통보 TR(`H0STCNI`) 0 · websocket 라이브러리 0 |
| I3 | 워커가 읽는 환경변수는 `JOURNAL_DATABASE_URL`·`API_REPORTER_KEY` 둘뿐 · `.env`·dotenv 0 |
| I4 | `requirements.txt` 는 정확히 2줄 고정(`asyncpg==0.30.0`·`httpx==0.28.1`) |
| I5 | Dockerfile — `python:3.12-slim` · `.token_cache`·`KIS_` 0 · 기본 실행에 backfill 없음 · `src/` COPY 0 |
| I6 | 동시 요청 0 — `gather`·`create_task`·`TaskGroup`·`ensure_future` 0 |
| I7 | 문법은 `jw/grammar.py` 한 곳 — 로그 접두 리터럴(`매도 주문 접수` 등)이 다른 jw 모듈에 없다 |

왜 문자열 스캔인가 — import 는 동적일 수 있지만 KIS 자격은 결국 변수 **이름**으로 들어온다.
스캔은 `Path.rglob` 로 한다(`git ls-files` 는 미추적 새 파일을 못 본다 — cycle259 S4b).
"""
from __future__ import annotations

import ast
import re

import pytest

from jw_testkit import JW_DIR, REPO_ROOT, WORKER_ROOT, jw_sources

pytestmark = pytest.mark.unit

_DOCKERFILE = WORKER_ROOT / "Dockerfile"
_REQS = WORKER_ROOT / "requirements.txt"


def _all_worker_files():
    assert WORKER_ROOT.is_dir()
    return [
        p for p in sorted(WORKER_ROOT.rglob("*"))
        if p.is_file() and "__pycache__" not in p.parts and p.suffix not in {".pyc"}
    ]


def _all_worker_py():
    return [p for p in _all_worker_files() if p.suffix == ".py"]


def test_i0_worker_package_exists():
    assert (JW_DIR / "__init__.py").is_file(), "journal_worker/jw/ 패키지가 없다"
    for mod in ("config", "grammar", "pairing", "stops", "reconcile", "tailer", "http", "db",
                "main", "backfill", "__main__"):
        assert (JW_DIR / f"{mod}.py").is_file(), f"jw/{mod}.py 가 없다"


def test_i1_no_src_import_anywhere_in_worker():
    offenders = []
    for p in _all_worker_py():
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
    assert JW_DIR.is_dir(), "jw/ 가 없다"
    assert offenders == [], offenders


@pytest.mark.parametrize("needle", ["KIS_", "koreainvestment", "H0STCNI", ".token_cache", "token_manager"])
def test_i2_no_kis_material_in_worker_files(needle):
    assert JW_DIR.is_dir(), "jw/ 가 없다"
    hits = []
    for p in _all_worker_files():
        if p.parent.name == "fixtures":
            continue  # 실측 로그 픽스처는 운영 로그 원문이다(민감값 검사는 I8 이 따로 한다)
        if p.name in {"test_jw_isolation.py"}:
            continue  # 이 파일 자신은 금지어 목록을 담는다
        if needle in p.read_text(encoding="utf-8", errors="replace"):
            hits.append(p.relative_to(REPO_ROOT).as_posix())
    assert hits == [], f"{needle!r} 가 워커 파일에 있다: {hits}"


def test_i2b_no_websocket_library():
    srcs = jw_sources()
    assert srcs, "jw/ 가 없다"
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


def _env_keys(text: str) -> set[str]:
    keys = set()
    tree = ast.parse(text)
    for node in ast.walk(tree):
        # os.environ["X"] / os.environ.get("X") / os.getenv("X")
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


def test_i3_env_reads_are_only_dsn_and_reporter_key():
    srcs = jw_sources()
    assert srcs, "jw/ 가 없다"
    keys: set[str] = set()
    for text in srcs.values():
        keys |= _env_keys(text)
    assert keys <= {"JOURNAL_DATABASE_URL", "API_REPORTER_KEY"}, keys
    assert "JOURNAL_DATABASE_URL" in keys, "DSN 은 JOURNAL_DATABASE_URL 로 읽는다"
    assert "API_REPORTER_KEY" in keys, "리포터 키는 API_REPORTER_KEY 로 읽는다"


def test_i3b_no_dotenv_reading():
    srcs = jw_sources()
    assert srcs, "jw/ 가 없다"
    for rel, text in srcs.items():
        assert "dotenv" not in text, rel
        assert not re.search(r"""['"][^'"]*\.env['"]""", text), f"{rel}: .env 파일을 읽지 않는다"


def test_i4_requirements_exactly_two_pinned():
    assert _REQS.is_file(), "journal_worker/requirements.txt 가 없다"
    lines = [ln.split("#", 1)[0].strip() for ln in _REQS.read_text(encoding="utf-8").splitlines()]
    lines = [ln for ln in lines if ln]
    assert sorted(lines) == ["asyncpg==0.30.0", "httpx==0.28.1"], lines


def _docker_code_lines() -> list[str]:
    assert _DOCKERFILE.is_file(), "journal_worker/Dockerfile 이 없다"
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
                assert s in {"requirements.txt", "jw", "jw/"}, f"이미지에 넣는 것은 requirements.txt·jw/ 뿐: {ln}"


def test_i5b_default_command_is_run_not_backfill():
    code = _docker_code_lines()
    ep = [ln for ln in code if ln.upper().startswith("ENTRYPOINT")]
    cmd = [ln for ln in code if ln.upper().startswith("CMD")]
    assert ep == ['ENTRYPOINT ["python", "-m", "jw"]'], ep
    assert cmd == ['CMD ["run"]'], cmd
    assert all("backfill" not in ln for ln in code)


@pytest.mark.parametrize("name", ["gather", "create_task", "TaskGroup", "ensure_future", "Thread"])
def test_i6_no_concurrency_primitives(name):
    srcs = jw_sources()
    assert srcs, "jw/ 가 없다"
    for rel, text in srcs.items():
        tree = ast.parse(text)
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr == name:
                pytest.fail(f"{rel}:{node.lineno} {name} — 동시 요청은 1개만(5절 ③)")
            if isinstance(node, ast.Name) and node.id == name:
                pytest.fail(f"{rel}:{node.lineno} {name}")


@pytest.mark.parametrize("prefix", ["매도 주문 접수", "매수 주문 접수", "주문 완료", "[order_notice]",
                                    "익일 청산 보류", "손절 잔여 재주문", "5호가 폴백"])
def test_i7_grammar_literals_live_only_in_grammar_module(prefix):
    srcs = jw_sources()
    assert "jw/grammar.py" in srcs, "jw/grammar.py 가 없다"
    forms = {prefix, re.escape(prefix)}  # 정규식 안에서 이스케이프한 꼴도 같은 문구다

    def knows(text):
        return any(f in text for f in forms)

    assert knows(srcs["jw/grammar.py"]), f"grammar 가 {prefix!r} 를 모른다"
    others = [rel for rel, text in srcs.items() if rel != "jw/grammar.py" and knows(text)]
    assert others == [], f"문법은 모듈 1곳에 모은다 — {prefix!r} 가 {others} 에도 있다"


# ── I8: 실측 픽스처에 민감값이 없다 ──────────────────────────────────────────

_LINE = re.compile(r"^\d{4}-\d\d-\d\d \d\d:\d\d:\d\d \[\w+\s*\] (\S+) — ")
_ALLOWED_LOGGERS = re.compile(
    r"^src\.(engine\.order_engine|api\.order|routes\.trading|realtime\.handler|engine\.scheduler|"
    r"engine\.status_exit_watch|engine\.strategies\.\w+)$"
)


def test_i8_golden_fixture_has_no_sensitive_values():
    from jw_testkit import GOLDEN_LOG

    text = GOLDEN_LOG.read_text(encoding="utf-8")
    for pat in [r"\d{8}-\d{2}", r"tr_key", r"app_?key", r"app_?secret", r"approval_key", r"Bearer",
                r"HTS", r"CANO", r"ACNT", r"websockets", r"KIS_"]:
        assert not re.search(pat, text, re.I), f"픽스처에 민감 표지 {pat!r}"
    for i, ln in enumerate(text.splitlines(), 1):
        m = _LINE.match(ln)
        assert m, f"{i}행 형식이 운영 로그 꼴이 아니다: {ln[:80]}"
        assert _ALLOWED_LOGGERS.match(m.group(1)), f"{i}행 로거 {m.group(1)} — 필요한 로거 줄만 둔다"


# ── cycle412 보완 Red — 결함 10·11(낮음) ──────────────────────────────────────────
#
# | # | 계약 |
# |---|---|
# | I9 | Dockerfile 이 root 가 아닌 사용자로 실행한다 — 마지막 `USER` 가 root·0 이 아니고 ENTRYPOINT 앞 |
# | I10 | 빌드 문맥 `journal_worker/` 에 `.dockerignore` — 테스트(실측 로그 픽스처 포함)·`ops/`·`__pycache__`·`*.pyc`·`.env*` 를 빼고 `jw/`·`requirements.txt` 는 남긴다 |
# | I11 | `ops/role.sql` 실행 예시의 비밀번호 생성은 `openssl rand -hex` — base64 는 `/`·`+`·`=` 가 DSN 을 깨고, 즉석 생성은 값을 확인할 길이 없다 |

import fnmatch  # noqa: E402

_DOCKERIGNORE = WORKER_ROOT / ".dockerignore"
_ROLE_SQL = WORKER_ROOT / "ops" / "role.sql"


def test_i9_dockerfile_runs_as_non_root():
    code = _docker_code_lines()
    users = [i for i, ln in enumerate(code) if re.match(r"^USER\s+", ln, re.I)]
    assert users, "Dockerfile 에 USER 가 없다 — 워커가 root 로 돈다"
    last = users[-1]
    who = code[last].split(None, 1)[1].strip().split(":")[0]
    assert who not in {"root", "0"}, f"USER {who} — root 가 아니어야 한다"
    ep = next(i for i, ln in enumerate(code) if ln.upper().startswith("ENTRYPOINT"))
    assert last < ep, "USER 는 ENTRYPOINT 앞"
    assert all(not re.match(r"^(RUN|COPY|ADD)\b", ln, re.I) for ln in code[last + 1:]), (
        "USER 뒤에 RUN/COPY 가 있으면 그 단계가 다시 root 를 요구하는지 확인할 수 없다 — USER 는 빌드 단계 뒤")


def _ignored(path: str, patterns: list[str]) -> bool:
    """docker 빌드 문맥 규칙을 줄인 판정 — 마지막에 맞은 패턴이 이긴다(`!` = 다시 넣기), 디렉터리 패턴은 하위 전부."""
    verdict = False
    for raw in patterns:
        neg = raw.startswith("!")
        pat = raw[1:] if neg else raw
        pat = pat.strip().lstrip("/").rstrip("/")
        if not pat:
            continue
        parts = path.split("/")
        prefixes = ["/".join(parts[:k]) for k in range(1, len(parts) + 1)]
        hit = any(fnmatch.fnmatch(pre, pat) for pre in prefixes)
        if pat.startswith("**/"):
            sub = pat[3:]
            hit = hit or any(fnmatch.fnmatch(seg, sub) for seg in parts) or any(
                fnmatch.fnmatch("/".join(parts[k:]), sub) for k in range(len(parts)))
        if hit:
            verdict = not neg
    return verdict


def test_i10_dockerignore_keeps_context_to_the_image_inputs():
    assert _DOCKERIGNORE.is_file(), "journal_worker/.dockerignore 가 없다 — 테스트·실측 로그 픽스처까지 빌드 문맥으로 간다"
    pats = [ln.strip() for ln in _DOCKERIGNORE.read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.strip().startswith("#")]
    must_out = ["tests/test_jw_isolation.py", "tests/fixtures/golden_2026-09-17_10-07.log", "ops/role.sql",
                "jw/__pycache__/main.cpython-312.pyc", "tests/__pycache__/conftest.cpython-312.pyc", ".env",
                ".env.local"]
    must_in = ["jw/main.py", "jw/__init__.py", "requirements.txt", "Dockerfile"]
    assert [p for p in must_out if not _ignored(p, pats)] == [], pats
    assert [p for p in must_in if _ignored(p, pats)] == [], pats


def test_i11_role_sql_example_uses_hex_password():
    text = _ROLE_SQL.read_text(encoding="utf-8")
    assert "openssl rand -base64" not in text, "base64 비밀번호는 DSN 특수문자(/ + =)로 깨진다"
    assert re.search(r"openssl rand -hex \d+", text), "예시는 openssl rand -hex 로 만든 값을 쓴다"
    assert not re.search(r"journal_pw=\"?\$\(openssl", text), (
        "psql 인자 안에서 즉석 생성하면 그 값을 secrets/journal_worker.env 에 옮길 길이 없다 — 변수에 먼저 담는다")
