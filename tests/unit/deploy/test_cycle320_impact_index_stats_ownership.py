"""cycle320 — 인덱스 통계가 「마지막에 어느 도구를 돌렸나」에 달려 있던 것.

## 왜 필요한가

cycle318 이 인덱스 최신성 가드를 세우다 걸린 결함이다. `_workspace/test_index.yaml` 의
`stats.unmapped_modules`(= 어떤 테스트도 가리키지 않는 모듈 목록)를 두 도구가 서로
다르게 다뤘다.

| 도구 | 하던 일 | 결과 |
|---|---|---|
| `build_index.py` | 자기 목록으로 **덮어썼다** | 프론트 항목 5개가 매번 사라졌다 |
| `build_index_frontend.mjs` | 앞의 것에 **이어붙였다**(중복 제거 없이) | 두 번 돌리면 프론트 항목이 쌓였다(정렬이 그것을 숨긴다) |

둘 다 `backend`/`frontend` **섹션은** 정성껏 보존하면서 이 목록만 빠뜨렸다.

## 무엇을 재는가

미매핑 목록은 양쪽이 나눠 쓴다 — 각 도구는 **자기 접두사**(`src/` · `frontend/`)만 책임지고
나머지는 그대로 둔다. 그래서 어느 도구를 몇 번, 어떤 순서로 돌려도 같은 값이 나온다.

이 목록이 중요한 이유 = **테스트가 하나도 없는 모듈의 명단**이다. 조용히 짧아지면
「가려진 모듈이 줄었다」로 읽히는데 실제로는 아무것도 안 좋아진 것이다.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[3]
INDEX = ROOT / "_workspace/test_index.yaml"
BACKEND_TOOL = ROOT / "tools/test_impact/build_index.py"
FRONTEND_TOOL = ROOT / "tools/test_impact/build_index_frontend.mjs"

_BACKEND_PREFIX = "src/"
_FRONTEND_PREFIX = "frontend/"


def _unmapped(body: str) -> list[str]:
    import yaml

    data = yaml.safe_load(body) or {}
    return (data.get("stats") or {}).get("unmapped_modules") or []


def test_committed_index_lists_both_sides() -> None:
    """커밋된 인덱스에 **양쪽 미매핑**이 다 있는가.

    막는 회귀 = 한쪽 도구가 상대 목록을 지우는 것. 지워진 상태로 커밋되면
    「테스트 없는 프론트 모듈」의 명단이 조용히 사라진다.
    """
    items = _unmapped(INDEX.read_text(encoding="utf-8"))
    back = [m for m in items if m.startswith(_BACKEND_PREFIX)]
    front = [m for m in items if m.startswith(_FRONTEND_PREFIX)]
    assert back, f"백엔드 미매핑이 없다 — 목록: {items}"
    assert front, f"프론트 미매핑이 없다 — 상대 도구가 지웠다. 목록: {items}"


def test_no_duplicates() -> None:
    """같은 모듈이 두 번 적히지 않는가.

    막는 회귀 = 중복 제거 없는 이어붙이기. 정렬돼 있으면 눈으로는 안 보이고
    개수만 조용히 불어난다.
    """
    items = _unmapped(INDEX.read_text(encoding="utf-8"))
    dups = sorted({m for m in items if items.count(m) > 1})
    assert not dups, f"중복 항목: {dups}"


def _run_and_read(cmd: list[str]) -> list[str]:
    """도구를 돌려 미매핑 목록만 읽고 **원본을 되돌린다**."""
    before = INDEX.read_text(encoding="utf-8")
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as tmp:
        tmp.write(before)
        backup = Path(tmp.name)
    try:
        r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=180)
        assert r.returncode == 0, f"{cmd[0]} 실패:\n{r.stderr[-1000:]}"
        return _unmapped(INDEX.read_text(encoding="utf-8"))
    finally:
        shutil.copyfile(backup, INDEX)
        backup.unlink(missing_ok=True)


def test_backend_tool_keeps_frontend_entries() -> None:
    """백엔드 도구를 돌려도 프론트 미매핑이 남는가 — 결함이 났던 바로 그 방향."""
    after = _run_and_read(["python", str(BACKEND_TOOL)])
    assert [m for m in after if m.startswith(_FRONTEND_PREFIX)], (
        f"백엔드 도구가 프론트 미매핑을 지웠다 — 남은 목록: {json.dumps(after, ensure_ascii=False)}"
    )


def test_frontend_tool_keeps_backend_entries_without_duplicating() -> None:
    """프론트 도구를 돌려도 백엔드 미매핑이 남고, 자기 항목을 중복시키지 않는가."""
    if not (ROOT / "frontend/node_modules/js-yaml").exists():
        pytest.skip("frontend/node_modules 가 없다 — node 의존이 갖춰진 환경에서만 검사한다")

    after = _run_and_read(["node", str(FRONTEND_TOOL)])
    assert [m for m in after if m.startswith(_BACKEND_PREFIX)], (
        f"프론트 도구가 백엔드 미매핑을 지웠다 — 남은 목록: {after}"
    )
    dups = sorted({m for m in after if after.count(m) > 1})
    assert not dups, f"프론트 도구가 항목을 중복시켰다: {dups}"
