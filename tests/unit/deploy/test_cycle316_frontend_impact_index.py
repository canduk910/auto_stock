"""cycle316 후속 B — 프론트 영향 인덱스가 **여러 줄 import 를 놓치지 않는가**.

🔴 왜 이 가드가 필요한가
`tools/test_impact/build_index_frontend.mjs` 의 `IMPORT_RE` 는 `^...$` 한 줄 전제에
`.+?`(개행 불포함)를 써서 **여러 줄로 쓴 import 문을 통째로 놓친다**.

```ts
import {
  foo,
  bar,
} from './module'     // ← 종전 정규식은 이 의존을 못 본다
```

놓친 의존은 인덱스에서 사라지고, 그러면 그 모듈만 고치는 PR 에서
`affected.py --target=frontend` 가 **빈 목록**을 돌려줘 회귀 테스트가 **조용히 건너뛰어진다**.
테스트가 붉어지는 것보다 나쁘다 — 아무 일도 안 일어난 것처럼 보인다.

발견 경위 = cycle315 에서 신규 `utils/marketRegime.ts` 의 테스트가 인덱스에 안 잡혔고,
그때는 import 를 한 줄로 바꿔 우회했다. 근본은 이 정규식이다.

이 테스트는 **저장소 실물**을 스캔한다 — 픽스처를 쓰면 정규식이 고쳐졌는지만 보고
실제 소스에 어떤 형태가 있는지는 못 본다.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[3]
TOOL = ROOT / "tools/test_impact/build_index_frontend.mjs"
FRONT_SRC = ROOT / "frontend/src"

#: 한 줄 전제 — 종전 구현. 비교용 기준선이다.
_ONE_LINE = re.compile(
    r"^\s*import\s+(?:.+?\s+from\s+)?[\"']([^\"']+)[\"']", re.M
)
#: 개행을 넘는 형태 — 올바른 형태.
_MULTI_LINE = re.compile(
    r"^\s*import\s+(?:[\s\S]+?\s+from\s+)?[\"']([^\"']+)[\"']", re.M
)


def _ts_files() -> list[Path]:
    return [
        p
        for p in FRONT_SRC.rglob("*")
        if p.suffix in (".ts", ".tsx") and p.is_file()
    ]


def test_tool_regex_crosses_newlines() -> None:
    """도구의 `IMPORT_RE` 가 개행을 넘는가.

    막는 회귀 = `[\\s\\S]` 를 `.` 로 되돌리는 것. `.` 는 개행에 안 걸린다.
    """
    src = TOOL.read_text(encoding="utf-8")
    m = re.search(r"const IMPORT_RE = (/.+/[a-z]*);", src)
    assert m, "build_index_frontend.mjs 에서 IMPORT_RE 를 못 찾았다"
    pattern = m.group(1)
    assert "[\\s\\S]" in pattern or "[^]" in pattern, (
        f"IMPORT_RE 가 개행을 넘지 못한다: {pattern}\n"
        "여러 줄 import 를 놓치면 그 모듈의 회귀 테스트가 조용히 건너뛰어진다."
    )


def test_tool_regex_parses_a_multiline_sample() -> None:
    """도구의 정규식을 **꺼내서** 여러 줄 샘플에 직접 돌린다.

    소스에 여러 줄 import 가 있는 것 자체는 금지가 아니다 — 문제는 도구가 그것을
    **못 읽는** 것이다. 그래서 소스를 세지 않고 정규식의 파싱 능력을 잰다.
    """
    src = TOOL.read_text(encoding="utf-8")
    m = re.search(r"const IMPORT_RE = (/.+/[a-z]*);", src)
    assert m, "IMPORT_RE 를 못 찾았다"

    sample = (
        "import React from 'react'\n"
        "import {\n"
        "  alpha,\n"
        "  beta,\n"
        "} from './multi-line-dep'\n"
        "import type { Gamma } from './type-dep'\n"
    )
    probe = (
        "const RE = %s;\n"
        "const text = %r;\n"
        "const out = [];\n"
        "let m; RE.lastIndex = 0;\n"
        "while ((m = RE.exec(text))) out.push(m[1]);\n"
        "console.log(JSON.stringify(out));\n"
    ) % (m.group(1), sample)

    r = subprocess.run(
        ["node", "--input-type=module", "-e", probe],
        capture_output=True, text=True, timeout=60,
    )
    assert r.returncode == 0, f"정규식 프로브 실패:\n{r.stderr[-1000:]}"
    found = set(eval(r.stdout.strip()))  # noqa: S307 — 우리가 만든 JSON 배열
    assert "./multi-line-dep" in found, (
        f"여러 줄 import 를 못 읽는다. 파싱 결과={sorted(found)}\n"
        "`.` 는 개행에 안 걸린다 — `[\\s\\S]` 여야 한다."
    )
    # 회귀 대조군 — 한 줄 import 도 여전히 읽혀야 한다.
    assert "react" in found and "./type-dep" in found, sorted(found)


def test_index_covers_a_known_multiline_importer() -> None:
    """인덱스를 실제로 만들어 **여러 줄 import 로 연결된 의존**이 들어오는지 본다.

    정규식만 보면 「고쳤다」는 것만 알고 「인덱스에 반영됐다」는 것은 모른다.
    """
    index = ROOT / "_workspace/test_index.yaml"
    if not index.exists():
        pytest.skip("test_index.yaml 이 없다 — 먼저 생성한다")

    # 여러 줄 import 를 실제로 쓰는 파일을 하나 고른다.
    sample: tuple[str, str] | None = None
    for f in _ts_files():
        if "__tests__" in str(f):
            continue
        text = f.read_text(encoding="utf-8")
        extra = set(_MULTI_LINE.findall(text)) - set(_ONE_LINE.findall(text))
        rel_deps = [d for d in extra if d.startswith(".")]
        if rel_deps:
            sample = (str(f.relative_to(ROOT)), rel_deps[0])
            break

    if sample is None:
        pytest.skip("여러 줄 import 를 쓰는 소스가 없다 — 이 가드의 전제가 사라졌다")

    body = index.read_text(encoding="utf-8")
    src_rel, _dep = sample
    assert src_rel in body, (
        f"{src_rel} 가 영향 인덱스에 없다 — "
        "`node tools/test_impact/build_index_frontend.mjs` 로 재생성했는지 확인하라"
    )


def test_tool_runs_and_is_deterministic() -> None:
    """도구가 실제로 돌고, 두 번 돌려도 같은 결과인가."""
    r = subprocess.run(
        ["node", str(TOOL)], cwd=ROOT, capture_output=True, text=True, timeout=180
    )
    assert r.returncode == 0, f"build_index_frontend.mjs 실패:\n{r.stderr[-2000:]}"
