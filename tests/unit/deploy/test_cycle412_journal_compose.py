"""cycle412 Red — `journal_worker` 컨테이너 compose 정적 검사(설계 관찰자안 5절 ①·⑤, 3절 「워커 컨테이너」).

| # | 계약 |
|---|---|
| W1 | `docker-compose.prod.yml` **본체**에 `journal_worker` 서비스 — 오버레이에만 두면 `--remove-orphans` 가 지운다(architecture 15.7) |
| W2 | `env_file` = `./secrets/journal_worker.env` 하나(`.env` 금지 — `.env` 를 넣으면 메인 앱키·HTS ID·운영 DSN 이 전부 들어간다) |
| W3 | `environment` = `TZ` 와 `API_REPORTER_KEY=${API_REPORTER_KEY}`(보간) 둘뿐 · `KIS_` 0 |
| W4 | 볼륨 = `./logs` 를 `:ro` 로 하나 · `.token_cache` 0 · `ports:` 0 · build context `./journal_worker` · `command` 에 backfill 0 |
| W5 | 자원 상한은 첫 배포에 — `mem_limit: 160m` · `cpus: 0.25` · json-file 10m×3 |
| W6 | TLS 오버레이(`docker-compose.tls*.yml`)는 이 서비스를 정의하지 않는다 · 개발 compose 무접촉 |
| W7 | 루트 pytest 가 워커 테스트를 모은다(`pyproject.toml` testpaths 에 `journal_worker/tests`) — 안 그러면 CI 가 워커 테스트를 안 돈다 |
| W8 | `./secrets/` 는 git 밖(.gitignore) — DSN 파일이 커밋되지 않는다 |
"""
from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parents[3]
_PROD = _ROOT / "docker-compose.prod.yml"


def _svc() -> dict:
    d = yaml.safe_load(_PROD.read_text(encoding="utf-8"))
    svc = d["services"].get("journal_worker")
    assert svc is not None, "docker-compose.prod.yml 본체에 journal_worker 서비스가 없다"
    return svc


def _svc_text() -> str:
    """서비스 블록 원문(주석 포함 — 보간 표기를 그대로 보기 위해)."""
    text = _PROD.read_text(encoding="utf-8")
    m = re.search(r"^  journal_worker:\n((?:    .*\n|\s*\n)+)", text, re.M)
    assert m, "journal_worker 블록을 찾지 못했다"
    return m.group(1)


def test_w1_defined_in_prod_body():
    _svc()


def test_w2_env_file_is_only_the_worker_secret():
    ef = _svc().get("env_file")
    files = [ef] if isinstance(ef, str) else list(ef or [])
    files = [f if isinstance(f, str) else f.get("path") for f in files]
    assert files == ["./secrets/journal_worker.env"], files


def test_w3_environment_is_tz_and_reporter_key_only():
    env = _svc().get("environment")
    if isinstance(env, dict):
        items = {k: str(v) for k, v in env.items()}
    else:
        items = dict(e.split("=", 1) for e in env)
    assert items == {"TZ": "Asia/Seoul", "API_REPORTER_KEY": "${API_REPORTER_KEY}"}, items
    assert "KIS_" not in _svc_text()


def test_w4_mounts_ports_build_command():
    svc = _svc()
    assert svc.get("volumes") == ["./logs:/app/logs:ro"], svc.get("volumes")
    assert "ports" not in svc and "expose" not in svc
    build = svc.get("build")
    ctx = build if isinstance(build, str) else (build or {}).get("context")
    assert ctx == "./journal_worker", build
    assert ".token_cache" not in _svc_text()
    cmd = svc.get("command")
    assert cmd is None or "backfill" not in str(cmd)
    assert "entrypoint" not in svc


def test_w5_resource_caps_on_first_deploy():
    svc = _svc()
    assert str(svc.get("mem_limit")) == "160m"
    assert float(svc.get("cpus")) == 0.25
    log = svc.get("logging") or {}
    assert log.get("driver") == "json-file"
    assert {k: str(v) for k, v in (log.get("options") or {}).items()} == {"max-size": "10m", "max-file": "3"}
    assert svc.get("restart") == "unless-stopped"


@pytest.mark.parametrize("name", ["docker-compose.tls.yml", "docker-compose.tls2.yml", "docker-compose.yml"])
def test_w6_overlays_and_dev_do_not_define_worker(name):
    p = _ROOT / name
    d = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    assert "journal_worker" not in (d.get("services") or {}), name


def test_w6b_other_services_untouched_by_worker_secret():
    d = yaml.safe_load(_PROD.read_text(encoding="utf-8"))
    for name, svc in d["services"].items():
        if name == "journal_worker":
            continue
        assert "journal_worker.env" not in yaml.safe_dump(svc), f"{name} 가 워커 비밀을 읽는다"
    assert d["services"]["backend"]["env_file"] == ".env"  # backend 블록은 그대로


def test_w7_worker_tests_collected_by_root_pytest():
    cfg = tomllib.loads((_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    paths = cfg["tool"]["pytest"]["ini_options"]["testpaths"]
    assert "tests" in paths and "journal_worker/tests" in paths, paths
    assert not (_ROOT / "journal_worker" / "tests" / "__init__.py").exists(), (
        "journal_worker/tests/__init__.py 를 두면 모듈 이름이 루트 tests 패키지와 부딪친다")


def test_w8_secrets_dir_is_gitignored():
    ignore = (_ROOT / ".gitignore").read_text(encoding="utf-8")
    assert re.search(r"^secrets/\s*$", ignore, re.M)
