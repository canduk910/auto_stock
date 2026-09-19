"""cycle319 — 병렬 작업이 남의 파일을 덮어쓴 것을 잡는 값싼 덫.

## 왜 필요한가

2026-09-19 실측 사고 — 동시에 돌던 다른 작업이 `src/routes/market_regime.py` 의 내용을
**`src/engine/market_regime.py` 에 썼다.** 750줄짜리 매매 모듈이 123줄짜리 라우트 파일이 됐다.
이름이 같은 두 파일이 서로 다른 계층에 있었던 것이 화근이다.

사용자가 그때 짚은 것이 정확하다 —

> "원래 git 의 취지가 각자 개발중인 소스 보존인데 지금 상황에서는 동일 수준에서 권한이
>  있어서 전적으로 네게 의지해야하네?"

맞다. 같은 작업 디렉터리를 공유하면 git 은 아무것도 지켜 주지 않는다. git 이 지키는 것은
**커밋된 것**이고, 커밋 전 편집본끼리는 나중에 쓴 쪽이 이긴다.

## 무엇을 재는가

덮어쓰기는 거의 항상 **다른 파일의 내용이 통째로 복사된** 모습을 한다. 그래서
`src/` 안에 내용이 완전히 같은 파일 쌍이 생기면 붉어진다. 실측 기준선은 **0쌍**이다.

⚠️ **이것은 덫이지 울타리가 아니다.** 부분 덮어쓰기나 내용을 섞어 쓴 경우는 못 잡는다.
진짜 방어는 두 가지고 둘 다 사람이 하는 일이다(루트 `CLAUDE.md` 「병렬 작업」 절):

  1. 파일을 **쓰는** 에이전트를 동시에 띄울 때는 `isolation: "worktree"` 로 격리한다.
  2. 띄우기 **전에** `git add -A` 로 스냅샷을 만든다 — 그러면 덮어써도
     `git checkout -- <path>` 한 줄로 돌아온다(그 사고의 실제 복구 경로다).

이미 있는 `_SRC_TREE_DIGEST` 핀(cycle287)도 `src/` 변경을 전부 붉히지만,
그건 **의도한 변경에서도 붉으므로** 재핀이 반사적이 되면 사고를 통과시킨다.
이 덫은 의도한 변경에서는 조용하고 덮어쓰기에서만 운다.
"""
from __future__ import annotations

import collections
import hashlib
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"

#: 내용이 거의 없는 파일은 뺀다 — 빈 `__init__.py` 들은 원래 서로 같다.
_MIN_BYTES = 200


def _content_groups() -> dict[str, list[str]]:
    groups: dict[str, list[str]] = collections.defaultdict(list)
    for p in sorted(SRC.rglob("*.py")):
        body = p.read_bytes()
        if len(body.strip()) < _MIN_BYTES:
            continue
        groups[hashlib.sha256(body).hexdigest()].append(str(p.relative_to(ROOT)))
    return groups


def test_no_two_src_modules_share_content() -> None:
    """`src/` 안에 내용이 똑같은 파일 쌍이 없는가.

    막는 회귀 = 동시 작업이 한 모듈에 다른 모듈의 내용을 쓰는 것. 실측 사고에서
    `src/engine/market_regime.py` 가 `src/routes/market_regime.py` 의 사본이 됐고,
    그 상태로 배포됐다면 매크로 레짐 수신이 통째로 사라졌다.
    """
    dups = {h: v for h, v in _content_groups().items() if len(v) > 1}
    assert not dups, (
        "내용이 똑같은 모듈 쌍이 있다 — 덮어쓰기를 의심한다.\n"
        + "\n".join("  " + " == ".join(v) for v in dups.values())
        + "\n  복구 = `git checkout -- <덮어써진 파일>` (커밋 전 스냅샷이 있을 때)"
    )


def test_guard_has_something_to_look_at() -> None:
    """검사 대상이 실제로 있는가 — 공허 통과 방지.

    경로가 틀리면 `rglob` 이 빈 목록을 돌려주고 위 단언이 **항상 초록**이 된다.
    """
    groups = _content_groups()
    assert sum(len(v) for v in groups.values()) > 100, (
        f"검사한 파일이 너무 적다 ({sum(len(v) for v in groups.values())}개) — 경로를 확인한다"
    )


def test_same_named_modules_differ() -> None:
    """이름이 같고 계층이 다른 모듈들이 서로 다른가 — 사고가 난 바로 그 모양.

    같은 파일명이 여러 계층에 있는 것 자체는 정상이다(`market_regime.py` 가
    `engine/` 과 `routes/` 에 각각 있다). 그 둘의 **내용이 같아지는 것**이 사고다.
    이름별로 좁혀 보면 위 전수 검사보다 사고를 더 정확한 말로 알려 준다.
    """
    by_name: dict[str, list[Path]] = collections.defaultdict(list)
    for p in sorted(SRC.rglob("*.py")):
        if len(p.read_bytes().strip()) >= _MIN_BYTES:
            by_name[p.name].append(p)

    collided = [
        (name, [str(p.relative_to(ROOT)) for p in paths])
        for name, paths in by_name.items()
        if len(paths) > 1
        and len({hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}) < len(paths)
    ]
    assert not collided, (
        "이름이 같은 모듈끼리 내용이 같아졌다 — 계층을 헷갈린 덮어쓰기다.\n"
        + "\n".join(f"  {name}: {', '.join(paths)}" for name, paths in collided)
    )
