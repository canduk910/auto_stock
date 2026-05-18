"""사이클 13-E-3 Red — `.claude/hooks/session-start.sh` idempotency 검증 (Test N).

명세 (`_workspace/cycle13e3_stop_zombie_and_hook_idempotency_spec.md` §4 Patch B, §5 Test N):

PR #12 Copilot 리뷰 ② — `.claude/hooks/session-start.sh:27`:
> 세션 시작마다 `PYTHONPATH` export 라인을 무조건 append(`>>`)해서 같은 세션/프로젝트에서
> hook 이 여러 번 실행되면 `${CLAUDE_ENV_FILE}` 이 중복 라인으로 계속 커질 수 있습니다.

현재 (line 26~27):
    # pytest 가 src/ 를 import 할 때 PYTHONPATH 가 cwd 인지 확인
    echo 'export PYTHONPATH="${PYTHONPATH:-}:."' >> "${CLAUDE_ENV_FILE:-/dev/null}"

기대 동작 (Green Patch B):
- 라인 추가 *전* `grep -qxF` 로 기존 존재 여부 확인
- 동일 라인이 이미 있으면 추가 안 함 (idempotent)
- 결과: hook 을 N 회 실행해도 ``CLAUDE_ENV_FILE`` 에 동일 라인 정확히 1 개

Red 단계:
- 현재 `>>` 무조건 append → 3 회 실행 시 동일 라인 3 개 → 본 테스트 `grep -cxF == 1` assert fail

부작용 격리 전략 (명세 §5 권장 패턴):
- 진짜 `pip` / `npm` / `python3` 호출이 일어나면 CI 환경 의존성 + 시간 비용 발생
- ``tmp_path/bin/`` 에 ``pip`` / ``npm`` / ``python3`` 빈 wrapper 스크립트 (exit 0) 를 만들고
  ``PATH=$tmp_path/bin`` 으로 shadow 한다 → hook 의 install 명령은 즉시 종료, env 파일 부작용 없음
- ``CLAUDE_ENV_FILE`` 은 ``tmp_path/env`` (실제 사용자 영구 파일 격리)
- ``CLAUDE_PROJECT_DIR`` 은 ``tmp_path/project`` (cd 가능한 임의 디렉토리)
- ``CLAUDE_CODE_REMOTE=true`` 가 없으면 hook 이 line 6~9 에서 ``exit 0`` 으로 조기 종료 → 테스트 무력화

안전 가드 (CLAUDE.md):
- session-start.sh 본 코드 수정 금지 (Green 은 backend-dev)
- 매매 로직과 무관 — 자금 안전 영향 0
- bash 미설치 환경 (`shutil.which("bash") is None`) → skip
- timeout 30s 가드 — install 명령이 shadow 통과해도 빠르게 종료
"""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

pytestmark = [pytest.mark.integration]


# 검증 대상 라인 — session-start.sh 가 추가하는 PYTHONPATH export 라인 (정확 문자열)
EXPECTED_LINE = 'export PYTHONPATH="${PYTHONPATH:-}:."'

# 프로젝트 루트 (auto_stock/) — `.claude/hooks/session-start.sh` 위치 산출용
PROJECT_ROOT = Path(__file__).resolve().parents[2]
HOOK_PATH = PROJECT_ROOT / ".claude" / "hooks" / "session-start.sh"


def _install_shadow_wrapper(bin_dir: Path, name: str) -> None:
    """``bin_dir/<name>`` 에 모든 인자를 무시하고 exit 0 하는 wrapper 를 생성한다.

    session-start.sh 의 ``python3 -m pip install ...`` / ``npm install ...`` 라인이
    실제 인터넷 fetch + 패키지 설치를 일으키지 않도록 PATH shadow.
    """
    wrapper = bin_dir / name
    wrapper.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    wrapper.chmod(wrapper.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


@pytest.fixture
def isolated_hook_env(tmp_path: Path) -> dict[str, str | Path]:
    """session-start.sh 부작용 격리 환경 구성.

    구성요소:
    - ``tmp_path/bin/`` : pip / npm / python3 shadow wrappers (PATH 최우선)
    - ``tmp_path/env``  : ``CLAUDE_ENV_FILE`` 위치 — 검증 대상 파일
    - ``tmp_path/project/`` : ``CLAUDE_PROJECT_DIR`` (cd 가능, 본 코드 무관)

    반환: ``{"env": dict[str,str], "env_file": Path}`` — subprocess 호출에 그대로 사용
    """
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for cmd in ("pip", "npm", "python3"):
        _install_shadow_wrapper(bin_dir, cmd)

    env_file = tmp_path / "env"
    env_file.touch()  # 빈 파일로 시작

    project_dir = tmp_path / "project"
    project_dir.mkdir()

    # PATH 는 shadow bin 우선 + 최소 시스템 (bash 가 필요한 것만)
    # /usr/bin:/bin 은 grep/echo/cd 등 coreutils 보장
    env = {
        "CLAUDE_CODE_REMOTE": "true",
        "CLAUDE_ENV_FILE": str(env_file),
        "CLAUDE_PROJECT_DIR": str(project_dir),
        "PATH": f"{bin_dir}:/usr/bin:/bin",
        "HOME": str(tmp_path),  # ~/ 참조 격리
    }
    return {"env": env, "env_file": env_file}


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash 미설치 환경 — hook 실행 불가")
def test_session_start_hook_appends_pythonpath_line_only_once(
    isolated_hook_env: dict,
) -> None:
    """Red: ``session-start.sh`` 를 3 회 실행한 후 ``CLAUDE_ENV_FILE`` 에 PYTHONPATH export
    라인이 **정확히 1 개** 만 존재해야 한다 (idempotent).

    명세 §4 Patch B — 라인 추가 *전* ``grep -qxF`` 가드 적용 시 hook 다회 실행에도 누적 0.

    Red 상태: 현재 session-start.sh:27 은 ``>>`` 무조건 append → 3 회 실행 = 라인 3 개 →
    ``grep -cxF == 1`` assert fail.

    부작용 격리:
    - ``PATH`` 에 ``tmp_path/bin`` 우선 → ``pip`` / ``npm`` / ``python3`` 가 noop
    - ``CLAUDE_ENV_FILE`` 은 ``tmp_path/env`` (사용자 영구 파일 무관)
    - ``CLAUDE_PROJECT_DIR`` 은 ``tmp_path/project`` (hook cd 대상)
    """
    assert HOOK_PATH.exists(), (
        f"session-start.sh 미발견: {HOOK_PATH}. 경로 변경 또는 hook 삭제 여부 확인 필요."
    )

    env = isolated_hook_env["env"]
    env_file: Path = isolated_hook_env["env_file"]

    # hook 3 회 연속 실행 — 명세 §5 Test N 권장 횟수
    for iteration in range(3):
        result = subprocess.run(
            ["bash", str(HOOK_PATH)],
            env=env,
            cwd=str(PROJECT_ROOT),  # cd 안에서 frontend/ 등 상대경로 참조 가능하게
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, (
            f"session-start.sh 실행 실패 (iteration={iteration}, rc={result.returncode}).\n"
            f"stdout: {result.stdout}\n"
            f"stderr: {result.stderr}\n"
            f"hook 본문 자체 오류 또는 shadow wrapper 누락 의심."
        )

    # 검증: env_file 에 EXPECTED_LINE 이 정확히 1 회만 등장
    # ``grep -cxF`` : -c=count, -x=whole line match, -F=fixed string (escape 무관)
    grep_result = subprocess.run(
        ["grep", "-cxF", EXPECTED_LINE, str(env_file)],
        check=False,
        capture_output=True,
        text=True,
    )
    # grep -c 는 매치 0 일 때 rc=1, 매치 ≥1 일 때 rc=0 — 둘 다 stdout 에 count 출력
    count_str = grep_result.stdout.strip() or "0"
    try:
        count = int(count_str)
    except ValueError:
        pytest.fail(
            f"grep -cxF stdout 파싱 실패: {count_str!r}. "
            f"rc={grep_result.returncode}, stderr={grep_result.stderr!r}"
        )

    # 디버깅 도움 — fail 시 env_file 전체 내용도 첨부
    env_file_content = env_file.read_text(encoding="utf-8")

    assert count == 1, (
        f"session-start.sh 가 ``{EXPECTED_LINE}`` 라인을 {count} 회 추가했음 — 기대값 1.\n"
        f"명세 §4 Patch B — `grep -qxF \"$LINE\" \"$FILE\" || echo \"$LINE\" >> \"$FILE\"` "
        f"idempotent 가드 필수.\n"
        f"--- CLAUDE_ENV_FILE 내용 ---\n{env_file_content}\n--- end ---"
    )


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash 미설치 환경 — hook 실행 불가")
def test_session_start_hook_skip_when_not_remote(tmp_path: Path) -> None:
    """sanity: ``CLAUDE_CODE_REMOTE`` 미설정 시 hook 이 즉시 ``exit 0`` 으로 종료한다.

    명세 §4 Patch B 의 idempotent 가드가 line 27 이외에 부작용을 주지 않는지 확인 +
    Test N 환경에서 ``CLAUDE_CODE_REMOTE=true`` 가 필수 조건임을 회귀 가드.
    """
    env_file = tmp_path / "env"
    env_file.touch()

    env = {
        "CLAUDE_ENV_FILE": str(env_file),
        "CLAUDE_PROJECT_DIR": str(tmp_path),
        "PATH": "/usr/bin:/bin",
        "HOME": str(tmp_path),
        # CLAUDE_CODE_REMOTE 의도적으로 미설정 → hook line 6~9 분기로 skip
    }

    result = subprocess.run(
        ["bash", str(HOOK_PATH)],
        env=env,
        cwd=str(PROJECT_ROOT),
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0
    assert "not in remote env" in result.stdout or "skip" in result.stdout, (
        f"hook 이 비-remote 분기 메시지를 출력해야 함. stdout: {result.stdout!r}"
    )
    # CLAUDE_CODE_REMOTE 미설정 시 env_file 에 라인 추가가 일어나면 안 됨
    assert env_file.read_text(encoding="utf-8") == "", (
        f"비-remote 환경에서 hook 이 CLAUDE_ENV_FILE 에 쓰기를 수행함 — exit 0 분기 회귀.\n"
        f"내용: {env_file.read_text(encoding='utf-8')!r}"
    )
