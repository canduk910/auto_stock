"""cycle322 — `src/` 안 문서 한 줄이 매매 서버를 재시작시키던 것 (사용자 결정 D2 = B안).

## 무엇이 문제였나

2026-09-19 실측 — 커밋 `4b862d9` 가 바꾼 파일은 **테스트 1개**뿐인데 배포가
`mode=full reason=backend_inputs_changed` 로 판정해 **매매 백엔드를 재생성**했다.
누적 diff 안의 `src/db/CLAUDE.md` **한 줄**이 원인이었다.

토요일이라 무해했지만 평일 09:00~15:30 이면 **D6(보유 중 장중 push 금지) 위반**이다.
실질 비용 = 디렉터리별 `CLAUDE.md` 를 고치는 문서 동기화(`/sync-docs` 는 코드 변경마다 필수)가
**장외 창에만 묶인다.**

## 왜 「정규식만 좁히기」(C안)가 아닌가

`src/**/*.md` 가 **실제로 이미지 안에 있었기 때문**이다(EC2 실측: `/app/src` 아래 `.md` 9개).
분류만 좁히면 "안 바뀌었다"고 판정하면서 이미지는 바뀌는 상태가 된다 — 지금보다 나쁘다.
그래서 B안 = **`.dockerignore` 로 실제로 빼고, 그 다음에 분류에서도 뺀다.**

## 이 파일이 지키는 계약 — 「정직한 제외」

분류에서 빼는 경로는 **반드시** `.dockerignore` 가 이미지에서도 빼야 한다.
그 둘이 갈라지는 순간 stale 이미지가 조용히 돈다. 한쪽만 고치면 여기서 붉어진다.

## 실측 근거 (2026-09-20)

- 도커 패턴은 `/` 를 넘지 않는다 — 루트 `.dockerignore` 의 `*.md` 는 `README.md` 만 잡고
  `src/db/CLAUDE.md` 는 못 잡는다. 빈 컨텍스트 빌드로 확인했다(`**/*.md` 를 넣으면 빠진다).
- 런타임 소비처 **0건** — `open`/`read_text`/`Path`/`glob` × `.md` 전수 grep 결과,
  그 9개를 읽는 코드가 없다. 전부 docstring 안 **언급**이다(비활성화 심층 검증 의무).
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parents[3]
_SCRIPT = _ROOT / "tools/deploy/compose_up_changed.sh"
_DOCKERIGNORE = _ROOT / ".dockerignore"


def _read(p: Path) -> str:
    assert p.is_file(), f"없다: {p}"
    return p.read_text(encoding="utf-8")


def _named_re(name: str) -> str:
    m = re.search(rf"^{name}='([^']+)'\s*$", _read(_SCRIPT), re.M)
    assert m, f"스크립트에 {name}='…' 한 줄 정의가 없다"
    return m.group(1)


def test_script_defines_image_excluded_re() -> None:
    """이미지에서 빠지는 경로 목록이 **이름 있는 한 줄**로 정의되는가.

    막는 회귀 = 필터를 파이프라인 안에 인라인으로 흩뿌리는 것. 이름이 있어야
    아래 정직성 가드가 그것을 읽어 `.dockerignore` 와 대조할 수 있다.
    """
    pat = _named_re("IMAGE_EXCLUDED_RE")
    assert pat.startswith("^"), f"앵커가 계약이다 (`xsrc/` 가 새면 안 된다): {pat}"


def test_image_excluded_paths_are_actually_excluded_from_the_image() -> None:
    """🔴 **정직성 계약** — 분류에서 빼는 경로를 `.dockerignore` 도 빼는가.

    막는 회귀 = `.dockerignore` 의 줄을 지우고 필터만 남기는 것. 그러면 배포가
    "이미지 입력 안 바뀜" 이라고 말하면서 실제 이미지는 바뀐다 —
    **stale backend 가 조용히 도는** 바로 그 상태다.

    지금 빼는 것은 `src/**/*.md` 하나뿐이라, `.dockerignore` 에 중첩 `.md` 를
    제외하는 줄이 있는지만 본다. 대상이 늘면 이 가드부터 같이 늘린다.
    """
    pat = _named_re("IMAGE_EXCLUDED_RE")
    assert ".md" in pat, f"현재 계약은 `.md` 제외뿐이다 — 늘렸다면 이 가드도 늘린다: {pat}"

    lines = [ln.strip() for ln in _read(_DOCKERIGNORE).splitlines()]
    assert "**/*.md" in lines, (
        "`.dockerignore` 에 `**/*.md` 가 없다 — 분류는 `src/**/*.md` 를 빼는데 "
        "이미지에는 들어간다. 그 둘이 갈라지면 stale 이미지가 조용히 돈다.\n"
        f"  현재 .dockerignore: {lines}"
    )
    # 루트 전용 `*.md` 만으로는 부족하다는 것이 이 가드의 존재 이유다
    # (도커 패턴은 `/` 를 넘지 않는다 — 실측 확인).
    assert "*.md" in lines, "루트 `.md` 제외도 유지한다(둘은 서로 대체하지 않는다)"


def test_filter_is_applied_to_backend_hits() -> None:
    """필터가 **backend 판정에 실제로 걸리는가**.

    막는 회귀 = 상수만 정의해 두고 파이프라인에 안 끼우는 것(공허한 선언).
    """
    body = _read(_SCRIPT)
    m = re.search(r"^\s*BACKEND_HITS=.*$", body, re.M)
    assert m, "BACKEND_HITS 대입 줄이 없다"
    line = m.group(0)
    assert "IMAGE_EXCLUDED_RE" in line, (
        f"BACKEND_HITS 계산에 IMAGE_EXCLUDED_RE 가 안 걸린다 — 선언만 하고 안 쓴다: {line.strip()}"
    )
    assert "grep -vE" in line, f"제외는 `grep -vE` 로 한다: {line.strip()}"


@pytest.mark.parametrize(
    "path,backend_expected",
    [
        # 이미지 입력이 **아닌** 것 — 분류에서 빠져야 한다
        ("src/db/CLAUDE.md", False),
        ("src/CLAUDE.md", False),
        ("src/engine/strategies/CLAUDE.md", False),
        # 이미지 입력인 것 — 반드시 남아야 한다
        ("src/db/pg.py", True),
        ("src/engine/scheduler.py", True),
        ("src/a.py", True),
        ("requirements.txt", True),
        ("Dockerfile", True),
        (".dockerignore", True),
        ("tools/deploy/compose_up_changed.sh", True),
    ],
)
def test_classification_probe_set(path: str, backend_expected: bool) -> None:
    """분류의 양성/음성 대표 집합.

    🔴 `.md` 가 아닌 `src/` 파일이 하나라도 빠지면 **stale backend** 다 —
    그쪽 실패가 이쪽(문서가 재시작을 부르는 것)보다 훨씬 위험하므로,
    음성 목록은 `.md` 로만 이뤄져 있어야 한다.
    """
    backend = re.compile(_named_re("BACKEND_RE"))
    excluded = re.compile(_named_re("IMAGE_EXCLUDED_RE"))

    hit = bool(backend.search(path)) and not excluded.search(path)
    assert hit is backend_expected, (
        f"{path}: backend 판정={hit}, 기대={backend_expected}"
    )


def test_exclusion_never_touches_non_src_backend_axes() -> None:
    """제외가 **`src/` 밖 backend 축**을 건드리지 않는가.

    막는 회귀 = `IMAGE_EXCLUDED_RE` 를 `.*\\.md$` 처럼 넓게 적는 것. 그러면 언젠가
    `tools/deploy/README.md` 같은 것이 생겼을 때 배포 스크립트 축이 흔들린다.
    """
    excluded = re.compile(_named_re("IMAGE_EXCLUDED_RE"))
    for p in ["tools/deploy/notes.md", "Dockerfile", "requirements.txt",
              "docker-compose.prod.yml", ".github/workflows/deploy.yml"]:
        assert not excluded.search(p), (
            f"{p} 가 제외 목록에 걸린다 — 제외는 `src/` 안 `.md` 로만 한정한다"
        )


def test_dockerfile_copy_contract_still_holds() -> None:
    """cycle248 G-248-2 의 전제가 유지되는가 — COPY 소스는 여전히 backend 축이다.

    이 가드는 그 계약을 **대체하지 않는다.** COPY 는 `src/` 를 통째로 담고,
    우리는 그중 `.md` 만 `.dockerignore` 로 덜어낸 것이다.
    """
    dockerfile = _read(_ROOT / "Dockerfile")
    assert re.search(r"^\s*COPY\s+src/\s", dockerfile, re.M), (
        "Dockerfile 이 `COPY src/` 를 더 이상 쓰지 않는다 — 이 사이클의 전제가 바뀌었다"
    )
    backend = re.compile(_named_re("BACKEND_RE"))
    assert backend.search("src/anything.py"), "COPY 소스가 backend 축에서 빠졌다"
