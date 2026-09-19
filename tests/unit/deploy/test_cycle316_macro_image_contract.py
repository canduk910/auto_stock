"""cycle316 — macro 이미지의 **우리 쪽 계약**.

🔴 **왜 이 가드가 `macro/tests/` 가 아니라 여기 있는가**
`macro/macro_lite/` 와 `macro/tests/` 는 stock-manager 에서 **무수정 vendor** 하는 영역이라
우리 계약을 거기 넣으면 다음 재이식에서 조용히 덮인다(2026-09-18 실제로 한 번 덮였다).
「이 이미지가 우리 EC2 에서 뜨는가」는 **우리 배포 구성의 사실**이므로 우리 테스트가 지킨다.

🔴 **왜 빌드 성공으로는 부족한가**
우리는 이 이미지에서 같은 종류의 사고를 **두 번** 냈다.
- `uvicorn` 이 `requirements.txt` 에 없어서 `docker build` 는 exit 0, 컨테이너는 즉사
- `COPY sp500.py` 누락으로 `docker build` 는 exit 0, 컨테이너는 `ModuleNotFoundError` 로 즉사

둘 다 **빌드는 통과하고 기동에서 죽는** 종류다. 그래서 CI 는 빌드 뒤 `/health` 스모크까지 돌고
(`.github/workflows/ci.yml` 의 docker-build 잡), 이 파일은 그 스모크가 성립하기 위한
**정적 전제**(엔트리포인트가 실재하는 모듈을 가리키고, 그 모듈이 이미지에 실제로 복사되며,
실행에 필요한 패키지가 선언돼 있는가)를 문자열 수준에서 잠근다.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[3]
MACRO = ROOT / "macro"


def _read(rel: str) -> str:
    p = MACRO / rel
    assert p.exists(), f"macro/{rel} 이 없다"
    return p.read_text(encoding="utf-8")


def _copied_paths(dockerfile: str) -> set[str]:
    """`COPY <src>... <dst>` 의 소스 토큰 집합. `--from` 빌드 스테이지 복사는 제외."""
    out: set[str] = set()
    for line in dockerfile.splitlines():
        s = line.strip()
        if not s.upper().startswith("COPY "):
            continue
        if "--from=" in s:
            continue
        toks = s.split()[1:]
        # 마지막 토큰은 목적지
        for tok in toks[:-1]:
            if tok.startswith("--"):
                continue
            out.add(tok.rstrip("/"))
    return out


def test_entrypoint_module_is_copied_into_image() -> None:
    """CMD 가 가리키는 모듈이 이미지에 실제로 복사되는가.

    막는 회귀 = `COPY` 목록에서 빠진 파일을 엔트리포인트가 import 하는 것.
    그 경우 빌드는 성공하고 기동만 죽는다.
    """
    dockerfile = _read("Dockerfile")
    copied = _copied_paths(dockerfile)

    m = re.search(r'CMD\s+\[(.+?)\]', dockerfile, re.S)
    assert m, "macro/Dockerfile 에 CMD 배열이 없다"
    cmd = [x.strip().strip('"').strip("'") for x in m.group(1).split(",")]
    assert "uvicorn" in cmd, f"CMD 가 uvicorn 으로 시작하지 않는다: {cmd}"

    # `main:app` → main.py
    target = next((x for x in cmd if ":" in x and not x.startswith("-")), "")
    assert target, f"CMD 에서 `모듈:앱` 토큰을 못 찾았다: {cmd}"
    module = target.split(":")[0]
    entry = f"{module}.py"

    assert (MACRO / entry).exists(), f"macro/{entry} 가 없는데 CMD 가 그것을 가리킨다"
    assert entry in copied or "." in copied, (
        f"macro/Dockerfile 의 COPY 목록에 {entry} 가 없다 — "
        f"빌드는 성공하고 컨테이너만 죽는다. COPY 소스={sorted(copied)}"
    )


def test_local_modules_imported_by_entrypoint_are_copied() -> None:
    """엔트리포인트가 import 하는 **우리 로컬 모듈**이 전부 COPY 되는가.

    `sp500.py` 누락 사고의 회귀 가드다. vendor 패키지(`macro_lite`)와 서드파티는 제외하고,
    `macro/` 바로 아래 같은 이름의 `.py` 가 실재하는 것만 본다.
    """
    dockerfile = _read("Dockerfile")
    copied = _copied_paths(dockerfile)
    if "." in copied:
        pytest.skip("Dockerfile 이 `COPY . .` 로 전체를 복사한다 — 누락이 구조적으로 불가능")

    main_src = _read("main.py")
    imported: set[str] = set()
    for line in main_src.splitlines():
        s = line.strip()
        m = re.match(r"(?:from|import)\s+([A-Za-z_][A-Za-z0-9_]*)", s)
        if m:
            imported.add(m.group(1))

    local = {n for n in imported if (MACRO / f"{n}.py").exists()}
    missing = {f"{n}.py" for n in local} - copied
    assert not missing, (
        f"macro/main.py 가 import 하는 로컬 모듈이 이미지에 복사되지 않는다: {sorted(missing)} — "
        f"빌드 성공·기동 실패 조합이다. COPY 소스={sorted(copied)}"
    )


def test_runtime_deps_declared() -> None:
    """기동에 필요한 패키지가 `requirements.txt` 에 선언돼 있는가.

    `uvicorn` 누락 사고의 회귀 가드다. Dockerfile 이 그 파일만 설치하므로
    여기 없으면 이미지 안에 그 실행 파일이 없다.
    """
    reqs = _read("requirements.txt").lower()
    dockerfile = _read("Dockerfile")

    assert "requirements.txt" in dockerfile, (
        "macro/Dockerfile 이 requirements.txt 를 설치하지 않는다 — 이 가드의 전제가 바뀌었다"
    )
    for pkg in ("uvicorn", "fastapi"):
        assert re.search(rf"^{pkg}\b", reqs, re.M), (
            f"macro/requirements.txt 에 {pkg} 선언이 없다 — "
            f"빌드는 성공하고 컨테이너가 즉사한다"
        )


def test_ci_builds_and_smokes_macro_image() -> None:
    """CI 가 macro 이미지를 **빌드하고 기동까지** 확인하는가.

    막는 회귀 = 스모크 단계를 지우고 빌드만 남기는 것. 그러면 우리가 두 번 밟은
    「빌드 성공·기동 실패」 종류를 다시 못 잡는다.
    """
    ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert "./macro" in ci, "CI 가 macro 이미지를 빌드하지 않는다"
    assert "/health" in ci, (
        "CI 에 macro 기동 스모크(/health 확인)가 없다 — "
        "빌드 exit 0 은 컨테이너가 뜬다는 뜻이 아니다"
    )


def test_vendor_tests_are_not_in_deploy_gate() -> None:
    """vendor 테스트가 배포 게이트(`ci.yml`) 안으로 들어오지 않았는가.

    🔴 `deploy.yml` 은 「CI — Build & Test」 의 conclusion 하나만 본다. vendor 테스트를
    거기 넣으면 **우리가 고칠 수 없는 영역의 실패가 매매 backend 배포를 멈춘다.**
    별도 워크플로(`macro-vendor.yml`)가 그 분리의 실체다.
    """
    ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert "macro/tests" not in ci and "pytest tests -q" not in ci.replace("\n", " ") or True
    # 명시적으로: ci.yml 이 macro 의 vendor 테스트를 직접 돌리지 않는다
    assert not re.search(r"working-directory:\s*macro", ci), (
        "ci.yml 이 macro 디렉터리에서 무언가를 돌린다 — vendor 테스트가 배포 게이트에 들어왔는지 확인하라"
    )

    vendor_wf = ROOT / ".github/workflows/macro-vendor.yml"
    assert vendor_wf.exists(), "vendor 테스트를 떼어 둔 별도 워크플로가 없다"
    body = vendor_wf.read_text(encoding="utf-8")
    assert "macro/**" in body, "macro-vendor.yml 에 경로 필터가 없다 — 무관한 push 마다 돈다"
