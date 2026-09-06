"""cycle263 접촉 범위 가드 (C9) — ⚠️ **커밋 후 삭제 의무** ⚠️

이 파일은 cycle263 **작업 중에만** 유효한 사이클 한정 가드다. 워킹트리 diff 로 범위를
재기 때문에 커밋되는 순간 공허해지고(diff 소멸), 그 뒤 다음 편집에서 무조건 붉어진다
(cycle240 A11b · cycle252 G-252-5b · **cycle262 실사고** — 커밋 후 남은 `test_c12_*` 가
cycle263 의 diff 를 재서 붉어졌고 cycle263 이 삭제했다). **cycle263 커밋 직후 이 파일을
삭제한다.** 그때까지의 안전망으로 `_skip_if_cycle_committed()` 가 HEAD 에 시정이 들어온
순간 자기 은퇴하므로(cycle253 패턴), 삭제를 잊어도 다음 사이클을 막지 않는다.

계약 C9 — cycle263 이 바꾸는 런타임 파일은 다음 둘뿐이다:
- `src/engine/data_load_tasks.py` — (가) 신선도 게이트 인자 + 주석 정정 (8영역 밖)
- `src/engine/scanner.py`         — (다) 오늘봉 시각 필터 (8영역, 09-06 카드 ④ 승인)

특히 diff 0 이어야 하는 것: `src/engine/{risk,order_engine,session,strategy_registry}.py` ·
`src/engine/scheduler.py` · `src/engine/strategies/*.py` (7 전략) · `src/api/order.py` ·
`src/realtime/**` · `src/auth/**` · `src/db/**` · `frontend/src/**` ·
`supabase/migrations/**`.

8영역 자체의 영구 가드는 **자매 4곳**이 각자 독립된 dict 로 들고 있다 —
`tests/unit/ast/test_cycle222a3_ast_followup_fixes.py`(`_APPROVED_CONTENT_SHA`) ·
`tests/unit/ast/test_cycle223_ast_donchian_exit_fix.py` ·
`tests/unit/ast/test_cycle223f_ast_manual_apply_safeguard.py`(`_PREEXISTING_CONTENT_SHA`) ·
`tests/unit/engine/strategies/test_cycle226_zero_breakout_defense.py`(`_ALLOWED_CONTENT_SHA`).
Green 이 `scanner.py` 를 바꾸면 **네 곳 전부**에 `"src/engine/scanner.py": "<sha256>"` 를
**같은 값으로** 한시 등록해야 통과한다(커밋 직후 네 곳을 함께 비운다). 한 곳만 등록하면
나머지 셋이 붉어지고 그 실패 문구가 "실제 변경을 되돌려라" 라서 **승인된 8영역 변경을
되돌리도록 오도한다** — cycle263 이 실제로 그 사고를 냈고, 재발 방지로
`test_cycle223g3_ast_guard_sees_staged.py::test_g3_9*`(영구)가 "핀은 항상 4곳" 을 강제한다.
이 파일은 그 가드들이 **보지 않는** 범위(scheduler·전략·db·frontend·migrations)를 덮는다.

미추적 파일 함정: `git diff HEAD --name-only` 는 **추적 파일만** 본다. Green 이 새로
만든 파일은 `git ls-files --others` 로만 보이므로 둘을 합집합한다(cycle259 S4b 교훈).
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_REPO_ROOT = Path(__file__).resolve().parents[3]

# 이 가드가 감시하는 범위 (런타임 산출물만 — tests/·docs/·_workspace/ 와
# 디렉토리 `CLAUDE.md` 는 자유, 아래 `_is_runtime_file` 참조)
_WATCHED = ("src", "frontend/src", "supabase/migrations")

# cycle263 명세가 허용한 변경 파일 (C9)
_ALLOWED = {
    "src/engine/data_load_tasks.py",
    "src/engine/scanner.py",
}

# C9 는 **런타임 파일** 범위 계약이다 — 디렉토리 `CLAUDE.md`(정본 문서) 갱신은 오히려
# 이 사이클의 **의무**다(적대 검증 MEDIUM: `src/engine/CLAUDE.md` 가 이 사이클이 뒤집은
# 게이트 정책을 반대로 서술하고 있었다). 문서를 범위 위반으로 잡으면 "코드와 반대되는
# 주석을 그대로 두라" 는 뜻이 되어, 이 사이클의 `test_A2`(주석 정정 의무)와 정면 충돌한다.
# ⚠️ 예외는 **`CLAUDE.md` 파일명 정확 일치**뿐이다 — 아무 `.md` 나 허용하면 `src/` 밑에
# 문서로 위장한 산출물을 넣는 구멍이 된다. (배포 모드 판정은 별개다: `src/**` 는 확장자
# 무관 이미지 입력이라 `CLAUDE.md` 수정도 full 모드다 — cycle248.)
def _is_runtime_file(rel: str) -> bool:
    return not rel.endswith("/CLAUDE.md")


def _cycle263_committed() -> bool:
    """HEAD 의 `scanner.py` 에 이미 오늘봉 커트오프 상수가 있으면 True — 은퇴 신호."""
    res = subprocess.run(
        ["git", "grep", "-q", "_DAILY_LOAD_TODAY_BAR_CUTOFF", "HEAD",
         "--", "src/engine/scanner.py"],
        cwd=_REPO_ROOT, capture_output=True, text=True,
    )
    return getattr(res, "returncode", 1) == 0


def _skip_if_cycle_committed() -> None:
    """사이클 한정 diff 가드의 자기 은퇴 — 고아 가드가 다음 사이클을 붉히지 않게 한다."""
    if _cycle263_committed():
        pytest.skip(
            "cycle263 이 HEAD 에 커밋됨 — 사이클 한정 diff 가드 자기 은퇴. "
            "이 파일을 삭제하라 (cycle262 test_c12_* 고아 선례)."
        )


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout


def test_cycle263_touches_only_two_runtime_files():
    """C9 — 워킹트리 런타임 변경은 data_load_tasks.py · scanner.py 둘뿐.

    ⚠️ 사이클 한정 — 커밋되면 `_skip_if_cycle_committed` 가 은퇴시킨다(파일 삭제 대상).
    """
    _skip_if_cycle_committed()
    tracked = _git("diff", "HEAD", "--name-only", "--", *_WATCHED).split()
    untracked = _git(
        "ls-files", "--others", "--exclude-standard", "--", *_WATCHED
    ).split()
    changed = sorted(
        r for r in (set(tracked) | set(untracked)) if _is_runtime_file(r)
    )

    unexpected = sorted(set(changed) - _ALLOWED)
    assert unexpected == [], (
        f"C9 위반 — cycle263 범위 밖 런타임 변경: {unexpected}. "
        "허용 = src/engine/data_load_tasks.py · src/engine/scanner.py "
        "(scheduler.py · 전략 7파일 · src/db/** · realtime/auth/order 는 diff 0 의무)"
    )
