"""cycle243 라운드 2 Red (D-15~D-17) — 운영 문서·비밀 레시피 정적 가드.

명세: `_workspace/red/cycle243_api_auth_spec.md` §7(정본 문서 갱신) · §10.1 F7·F11 ·
§10.2 · §6.3(롤백) · §8(후속 F1~F9)

## 왜 문서에 회귀 가드를 거는가

라운드 1 이 F7(문서 미갱신)·F11(비밀 argv 유출)을 "시정" 으로 선언했지만 **둘 다
문서 본문에만 반영되고 잔재가 남았다**(라운드 2 확증):

* F7 — `_workspace/00_URGENT_WORKLIST.md` 는 curl 자격 치환 5줄만 바뀌었고 §7 이 약속한
  "신규 항목(cycle243 배포·후속 F1~F8) 등재" 가 없다. 그런데 명세 §7 상태란은 그 파일을
  "갱신 완료" 로 적어 **false green** 이다. 루트 `CLAUDE.md` 는 워크리스트를 "다른 작업을
  시작하기 전에 먼저 읽는다" 로 지정하므로, 이 사이클 최대 잔여 위험(L1 TLS 부재 ·
  후속 F2 SG 80 제한)이 **사이클 전용 Red 문서에만** 존재하게 된다. Red 문서는 아카이브된다.
* F11 — `.gitignore` 는 리포에 **상시 추적되는 유일한 htpasswd 생성 레시피**인데
  `openssl passwd -apr1 '<PASSWORD>'`(argv) 형태가 그대로다. 키 회전(후속 F5) 시점에
  운영자가 실제로 복사할 가능성이 가장 높은 줄이다.

두 축 모두 "본문 어딘가에 적었다" 로는 재발을 막지 못한다 — 텍스트 가드로 못박는다.
D 그룹(§3.D)과 같은 계열이지만 **배포 자산이 아니라 운영 문서**를 보므로 파일을 나눈다
(Phase 1/2 커밋 화이트리스트와 무관하게 항상 커밋된다).
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parents[3]
_WORKLIST = _ROOT / "_workspace" / "00_URGENT_WORKLIST.md"
_MONDAY = _ROOT / "_workspace" / "monday_0831_guide.md"


def _read(path: Path) -> str:
    if not path.exists():
        pytest.fail(f"Red — {path.relative_to(_ROOT)} 부재")
    return path.read_text(encoding="utf-8")


def _section(text: str, heading_pattern: str) -> str | None:
    """`## …` 헤딩 하나의 본문(다음 동급 이상 헤딩 직전까지)."""
    match = re.search(heading_pattern, text, re.M)
    if match is None:
        return None
    rest = text[match.end() :]
    nxt = re.search(r"^##\s", rest, re.M)
    return rest[: nxt.start()] if nxt else rest


# ---------------------------------------------------------------------------
# D-15 (F11 잔여) — 비밀이 argv 에 실리는 레시피 0건
# ---------------------------------------------------------------------------
def test_secret_recipes_when_tracked_then_never_pass_password_via_argv():
    """D-15 — **운영자용** 추적 파일의 `openssl passwd` 가 전부 `-stdin` 이고 인용 리터럴이 없다.

    argv 는 같은 호스트의 다른 사용자에게 `ps aux` 로 보이고 셸 히스토리에도 남는다.

    제외 2종 — 둘 다 "가드가 **자기 자신의 서술**을 위반으로 세는" 경우다:
      - `tests/` : 가드 자신이 탐지 문자열을 포함한다.
      - `_workspace/red/` : 설계 명세는 적대 검증 표(§10.1 F11 · §10.2 · §11 뮤테이션
        목록)에서 **금지형을 인용해야만** 왜 금지인지 적을 수 있다. 인용을 위반으로
        세면 결함을 문서화할수록 가드가 붉어진다.

    ⚠️ 이 제외는 cycle244 에서 **실패를 보고 추가**한 것이다. 종전 구현은
    `git grep`(= 추적 파일만 검색) 으로 전 트리를 훑었는데, 명세가 아직 untracked
    이던 Docs 단계에서는 초록이었다가 **커밋되는 순간 붉어졌다**(실측: 스위트
    6,240 PASS → 커밋 후 1 failed). "커밋 전까지만 초록인 가드" 는 cycle222-a 의
    `git diff` 영구 동결(cycle240 이 재스코프)과 같은 부류다.

    운영자가 실제로 복사할 경로(`.gitignore` · `CLAUDE.md` · `README.md` ·
    `_workspace/monday_0831_guide.md` · `frontend/CLAUDE.md`)는 그대로 검사 범위에
    남으므로 가드의 목적은 보존된다 — 아래 D-15b 가 그 범위의 비공허성을 못박는다.
    """
    proc = subprocess.run(
        ["git", "grep", "-nI", "openssl passwd", "--", ".",
         ":(exclude)tests/", ":(exclude)_workspace/red/"],
        cwd=_ROOT,
        capture_output=True,
        text=True,
    )
    assert proc.returncode in (0, 1), proc.stderr
    hits = [line for line in proc.stdout.splitlines() if line.strip()]

    offenders: list[str] = []
    for hit in hits:
        # `openssl passwd` 뒤 첫 인용 리터럴 = 비밀 argv (플래그는 `-` 로 시작)
        if re.search(r"openssl\s+passwd\s+(?:-\S+\s+)*['\"]", hit):
            offenders.append(hit)
        elif "-stdin" not in hit:
            offenders.append(hit)
    assert not offenders, (
        "비밀이 argv 로 넘어가는 htpasswd 레시피가 추적 파일에 남아 있다 "
        f"(`-stdin` + `read -s` 형태여야 한다, §10.2 F11): {offenders}"
    )


def test_secret_recipe_guard_when_scoped_then_not_vacuous():
    """D-15b (cycle244) — D-15 의 제외가 가드를 공허하게 만들지 않았음을 못박는다.

    D-15 는 "위반이 없다" 를 단언하므로, 검사 범위에 `openssl passwd` 가 **한 줄도
    없어도** 초록이다. `_workspace/red/` 를 제외한 뒤 그 상태가 되면 가드는 살아
    있는 척하는 죽은 코드가 된다. 그래서 운영자 경로에 레시피가 **실재**하고
    그것이 `-stdin` 형태임을 여기서 직접 확인한다.
    """
    proc = subprocess.run(
        ["git", "grep", "-nI", "openssl passwd", "--", ".",
         ":(exclude)tests/", ":(exclude)_workspace/red/"],
        cwd=_ROOT,
        capture_output=True,
        text=True,
    )
    assert proc.returncode in (0, 1), proc.stderr
    hits = [line for line in proc.stdout.splitlines() if line.strip()]
    assert hits, (
        "운영자 경로에 htpasswd 생성 레시피가 하나도 없다 — D-15 가 공허해졌다. "
        "`.gitignore` 주석의 생성 절차가 삭제됐는지 확인하라."
    )
    assert all("-stdin" in h for h in hits), hits


# ---------------------------------------------------------------------------
# D-16 (F7 잔여) — 워크리스트 등재
# ---------------------------------------------------------------------------
def test_worklist_when_cycle243_then_deployment_and_followups_registered():
    """D-16 — 표준 우선순위 문서에 cycle243 절이 있고 L1/F1(HTTPS)·F2(SG 80)를 담는다.

    §7 이 이 파일을 "갱신 완료" 로 표기하는 근거가 실제로 존재해야 한다.
    """
    worklist = _read(_WORKLIST)
    section = _section(worklist, r"^##\s+.*cycle243.*$")
    assert section is not None, (
        "`_workspace/00_URGENT_WORKLIST.md` 에 cycle243 절(`## … cycle243 …`)이 없다 — "
        "명세 §7 상태란의 '갱신 완료' 가 false green (§10.1 F7)"
    )

    for token, why in (
        ("TLS", "L1(TLS 부재) 이 표준 문서에 없다"),
        ("HTTPS", "후속 F1(HTTPS 도입) 이 표준 문서에 없다"),
        ("보안그룹", "후속 F2(SG 80 인바운드 IP 제한) 가 표준 문서에 없다"),
        ("Phase 2", "Phase 2(백엔드 fail-closed) 배포 항목이 없다"),
    ):
        assert token in section, f"{why} — cycle243 절 본문에 `{token}` 부재"

    followups = {f"F{n}" for n in range(1, 6)}
    missing = sorted(f for f in followups if not re.search(rf"\b{f}\b", section))
    assert not missing, f"후속 항목 미등재: {missing} (§8 F1~F9)"


# ---------------------------------------------------------------------------
# D-17 — 비상 절차서의 401 복구 조치
# ---------------------------------------------------------------------------
def test_emergency_guide_when_fail_closed_401_then_recovery_command_present():
    """D-17 — 비상 매도 절차의 401 분기에 **복구 명령**이 있고 잘못된 안심 문구가 없다.

    이 가이드는 자동 청산이 실패했을 때 사람이 손으로 파는 경로다. 그 경로가 401 로
    막혔을 때 "자동 청산이 살아 있다" 로 끝내면 운영자를 대기시킨다 — 401 은 곧
    비상 경로 차단이므로 즉시 복구 명령이 이어져야 한다. 최단 복구는 `.env` 키 주입 +
    compose up(수십 초)이지 `git revert` 왕복(5~10분)이 아니다.
    """
    guide = _read(_MONDAY)
    idx = guide.find("401 이 오면")
    assert idx != -1, "비상 가이드에 401 분기가 없다"
    block = guide[idx : idx + 1600]
    # 문장이 줄바꿈·들여쓰기로 쪼개져도 잡히도록 공백을 접는다
    flat = re.sub(r"\s+", " ", guide)

    assert "15:20 자동 청산 경로는 살아 있다" not in flat, (
        "401 분기가 '자동 청산은 살아 있다' 로 끝난다 — 이 가이드는 그 자동 청산이 "
        "실패했을 때 쓰는 문서다(모순 안심 문구)"
    )
    assert re.search(r">>\s*(~/auto_stock/)?\.env", block), (
        "401 복구 절차에 `.env` 키 주입(`>> .env`)이 없다"
    )
    assert "docker-compose.prod.yml up -d" in block, (
        "401 복구 절차에 compose 재적용 명령이 없다 — 최단 복구 경로가 문서에 없다"
    )
    assert "tick blind" in block, (
        "복구가 백엔드 재생성을 동반한다는 비용(장중 tick blind, cycle232 D6)이 없다"
    )
