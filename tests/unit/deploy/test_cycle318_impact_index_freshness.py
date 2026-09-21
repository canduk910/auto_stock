"""cycle318 — 영향 인덱스가 **낡았는지** 아무도 안 알려주던 것.

## 왜 필요한가

`_workspace/test_index.yaml` 은 「이 모듈을 고치면 어느 테스트가 영향받는가」의 지도다.
PR 빠른 피드백(`affected.py`)이 그것만 보고 돌 테스트를 고른다.

그런데 **그 지도가 낡아도 아무 일도 일어나지 않는다.** 신규 모듈·테스트가 인덱스에 없으면
`affected.py` 가 **빈 목록**을 돌려주고, 그러면 회귀 테스트가 **조용히 건너뛰어진다** —
붉어지는 것보다 나쁘다. 아무 일도 안 일어난 것처럼 보인다.

실측(2026-09-19) — cycle317b 를 커밋한 직후 인덱스를 재생성하니 **661줄 차이**가 났다.
그날 만든 신규 테스트가 통째로 빠져 있었다. 같은 날 cycle316 후속 B 가
「여러 줄 import 를 놓쳐 39파일 46건이 인덱스에서 사라진」 결함을 고쳤는데,
**고쳐도 재생성을 안 하면 같은 결과**다.

## 무엇을 재는가

도구를 돌려 **현재 인덱스와 다른지** 본다. 다르면 재생성이 밀린 것이다.

⚠️ **재생성 순서는 CLAUDE.md 「테스트 실행」 절이 정본이다** — `build_index.py` 먼저,
`build_index_frontend.mjs` 나중. 순서를 뒤집으면 내용은 같은데 들여쓰기가 통째로 바뀌어
diff 가 12만 줄이 된다(실측). 이 가드는 그 포맷 차이를 보지 않지만, 사람이 읽을 diff 는 봐야 한다.

⚠️ 백엔드 인덱스만 본다. 프론트 인덱스는 `js-yaml`(= `frontend/node_modules`)이 필요한데
CI 의 `backend-test` 잡은 npm install 을 하지 않는다 — 같은 날 그 전제를 틀려
CI 를 한 번 붉혔다. 프론트는 node 의존이 있을 때만 검사한다.
"""
from __future__ import annotations

import functools
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

#: 🔴 이 파일만 전역 60초 타임아웃(`pyproject.toml`)을 올린다.
#:
#: 전역 60초는 **mock 누락으로 외부 호출이 무한 hang 하는 것**을 잡는 안전망이고
#: 그 뜻은 그대로 둔다. 그런데 이 파일의 테스트는 `build_index.py` 를 **subprocess 로
#: 실제 실행**해 인덱스를 통째로 재생성한다 — 로컬 11초, 느린 CI 러너에서는 그 몇 배다.
#: 2026-09-22 실측: 로컬 11.4초인데 CI 에서 60초를 넘겨 `test_backend_index_is_fresh` 가
#: **Timeout 으로 붉어지고 Deploy 가 skip** 됐다(코드 결함 0). 게다가 이 비용은
#: **코드베이스가 커질수록 자란다** — 올려 두지 않으면 같은 일이 계속 난다.
#:
#: 🔴 안전망은 사라지지 않는다 — `_regenerate_into_copy` 의 `subprocess.run(timeout=180)`
#: 이 그대로 있어, 빌드 도구가 진짜로 매달리면 **그쪽이 먼저** 잡는다.

# 🔴 **두 마크를 한 대입에 담는다.** `pytestmark` 를 두 번 대입하면 **뒤엣것이
# 앞엣것을 덮어** 앞의 마크가 조용히 사라진다(2026-09-22 실측 — 타임아웃 마크를
# 따로 대입했다가 `timeout(2)` 돌연변이가 **통과**해서 드러났다).
pytestmark = [pytest.mark.unit, pytest.mark.timeout(240)]

ROOT = Path(__file__).resolve().parents[3]
INDEX = ROOT / "_workspace/test_index.yaml"
BACKEND_TOOL = ROOT / "tools/test_impact/build_index.py"
FRONTEND_TOOL = ROOT / "tools/test_impact/build_index_frontend.mjs"

#: 🔴 **글자 그대로 비교하면 이 가드는 영원히 붉다.** 실측(2026-09-19)으로 확인한
#: 「내용이 같아도 파일이 달라지는」 이유가 셋이다.
#:
#:  1. **생성 시각** — 두 도구가 돌 때마다 지금 시각을 적는다
#:     (`build_index.py:165` KST isoformat · `build_index_frontend.mjs:153` ISO Z).
#:  2. **들여쓰기** — 백엔드는 PyYAML, 프론트는 js-yaml 이라 목록 들여쓰기가 다르다
#:     (4칸 ↔ 6칸). 뒤에 도는 쪽이 파일 전체를 자기 방식으로 다시 쓴다.
#:  3. **`stats.unmapped_modules` 소유권** — 각 도구가 **자기 쪽 미매핑 목록만** 적고
#:     상대 쪽 항목을 지운다. 그래서 커밋된 값은 「마지막에 어느 도구를 돌렸는가」에 달렸다.
#:     (사소한 결함이지만 이 사이클의 범위는 아니다 — 가드는 이것 때문에 붉으면 안 된다.)
#:
#: 셋 다 **지도의 내용과는 무관**하다. 그래서 파일을 파싱해서 **그 도구가 소유한 구역만**
#: 비교한다. 이게 정확히 `affected.py` 가 읽는 것이고, 낡으면 회귀 테스트가 빠지는 것이다.
_OWNED_SECTION = {"backend": "backend", "frontend": "frontend"}


def _section(body: str, key: str) -> dict:
    """인덱스를 파싱해 한 구역만 돌려준다."""
    import yaml

    data = yaml.safe_load(body)
    assert isinstance(data, dict), "인덱스가 매핑이 아니다"
    assert key in data, f"인덱스에 `{key}` 구역이 없다 — 도구가 구조를 바꿨다"
    return data[key]


@functools.lru_cache(maxsize=1)
def _regenerate_into_copy() -> tuple[str, str]:
    """인덱스를 임시로 재생성하고 (현재, 새로 만든 것)을 돌려준다.

    🔴 **원본을 건드리지 않는다.** 테스트가 저장소 파일을 바꾸면 그 자체가 부작용이고,
    병렬 실행에서 다른 테스트와 충돌한다. 그래서 백업 → 재생성 → 비교 → 복원 순으로 간다.

    한 번 돌리는 데 ~11초라 결과를 캐시한다. 한 실행 안에서는 소스가 안 바뀌니 안전하다.
    """
    before = INDEX.read_text(encoding="utf-8")
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as tmp:
        tmp.write(before)
        backup = Path(tmp.name)
    try:
        r = subprocess.run(
            ["python", str(BACKEND_TOOL)],
            cwd=ROOT, capture_output=True, text=True, timeout=180,
        )
        assert r.returncode == 0, f"build_index.py 실패:\n{r.stderr[-1500:]}"
        after = INDEX.read_text(encoding="utf-8")
    finally:
        shutil.copyfile(backup, INDEX)
        backup.unlink(missing_ok=True)
    return before, after


def test_backend_index_is_fresh() -> None:
    """백엔드 영향 인덱스가 최신인가.

    막는 회귀 = 모듈·테스트를 추가하고 `python tools/test_impact/build_index.py` 를
    안 돌리는 것. 그러면 그 모듈만 고치는 PR 에서 회귀 테스트가 조용히 건너뛰어진다.
    """
    raw_before, raw_after = _regenerate_into_copy()
    before = _section(raw_before, "backend")
    after = _section(raw_after, "backend")
    if before == after:
        return
    pytest.fail(_explain("backend", before, after, "python tools/test_impact/build_index.py"))


def _explain(key: str, before: dict, after: dict, cmd: str) -> str:
    """무엇이 어긋났는지 짚어 준다 — 「다르다」만으로는 고칠 수가 없다."""
    missing = sorted(set(after) - set(before))
    extra = sorted(set(before) - set(after))
    changed = sorted(k for k in set(before) & set(after) if before[k] != after[k])
    lines = [
        f"{key} 영향 인덱스가 낡았다 — `{cmd}` 를 돌리고 커밋한다.",
        f"  인덱스에 없는 모듈 {len(missing)} · 사라진 모듈 {len(extra)} · 내용이 바뀐 모듈 {len(changed)}",
    ]
    for label, items in (("없는 모듈", missing), ("사라진 모듈", extra), ("바뀐 모듈", changed)):
        if items:
            lines.append(f"  {label}: " + ", ".join(items[:5]) + (" …" if len(items) > 5 else ""))
    return "\n".join(lines)


def test_frontend_index_is_fresh() -> None:
    """프론트 영향 인덱스가 최신인가.

    ⚠️ `js-yaml`(= `frontend/node_modules`)이 필요하다. CI 의 backend-test 잡은
    npm install 을 하지 않으므로 거기서는 skip 한다 — 같은 날 그 전제를 틀려 CI 를 붉혔다.
    """
    if not (ROOT / "frontend/node_modules/js-yaml").exists():
        pytest.skip("frontend/node_modules 가 없다 — node 의존이 갖춰진 환경에서만 검사한다")

    before = INDEX.read_text(encoding="utf-8")
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as tmp:
        tmp.write(before)
        backup = Path(tmp.name)
    try:
        r = subprocess.run(
            ["node", str(FRONTEND_TOOL)],
            cwd=ROOT, capture_output=True, text=True, timeout=180,
        )
        assert r.returncode == 0, f"build_index_frontend.mjs 실패:\n{r.stderr[-1500:]}"
        after = INDEX.read_text(encoding="utf-8")
    finally:
        shutil.copyfile(backup, INDEX)
        backup.unlink(missing_ok=True)

    b, a = _section(before, "frontend"), _section(after, "frontend")
    if b != a:
        pytest.fail(_explain("frontend", b, a, "node tools/test_impact/build_index_frontend.mjs"))


def test_index_is_tracked_and_not_empty() -> None:
    """인덱스가 git 에 있고 비어 있지 않은가 — 가드의 전제."""
    assert INDEX.exists(), "test_index.yaml 이 없다"
    body = INDEX.read_text(encoding="utf-8")
    assert len(body) > 1000, f"인덱스가 비정상적으로 작다 ({len(body)}자)"

    r = subprocess.run(
        ["git", "ls-files", "--error-unmatch", str(INDEX.relative_to(ROOT))],
        cwd=ROOT, capture_output=True, text=True, timeout=30,
    )
    assert r.returncode == 0, "test_index.yaml 이 git 추적 대상이 아니다"


def test_both_sections_survive_either_tool() -> None:
    """한쪽 도구를 돌려도 **다른 쪽 구역이 살아남는가** — 가드의 전제.

    막는 회귀 = 백엔드 도구가 프론트 구역을 통째로 지우는 것(혹은 그 반대).
    그러면 `affected.py --target=frontend` 가 빈 목록을 돌려주고
    프론트 회귀 테스트가 **조용히 전부 건너뛰어진다**.
    """
    _, after = _regenerate_into_copy()  # 백엔드 도구만 돌린 결과
    fe = _section(after, "frontend")
    assert len(fe) > 50, f"백엔드 도구가 프론트 구역을 훼손했다 (모듈 {len(fe)}개)"


def test_guard_catches_a_stale_index() -> None:
    """가드가 **낡은 인덱스를 실제로 잡는가** — 돌연변이 검증.

    이게 없으면 「비교가 늘 같아서 초록」인 상태와 「진짜 최신이라 초록」인 상태가
    구별되지 않는다. 모듈 하나를 일부러 빼고 같은 비교를 태워 본다.
    """
    body = INDEX.read_text(encoding="utf-8")
    fresh = _section(body, "backend")
    stale = dict(fresh)
    victim = sorted(stale)[0]
    del stale[victim]

    assert stale != fresh, "모듈을 지웠는데도 같다고 나온다"
    msg = _explain("backend", stale, fresh, "python tools/test_impact/build_index.py")
    assert victim in msg, f"어느 모듈이 빠졌는지 안 알려 준다:\n{msg}"
