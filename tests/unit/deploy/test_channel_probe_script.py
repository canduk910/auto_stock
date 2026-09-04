"""tools/ops/channel_probe.sh 정적 가드 — D8(2026-09-05 사용자 승인) 월요일 자동 프로브 스크립트.

스크립트는 EC2 에서만 실제 실행되므로 여기서는 (1) bash 문법 (2) 안전 속성만 잠근다:
루프백 기본 주소 · 운영 키 미출력 · H0STCNT0 기본 · 종료 시 무조건 DELETE(trap) ·
in_desired_now 즉시 해제 · cron 1회성 자기 제거 · bypass/HIGH 문구 없음.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "tools" / "ops" / "channel_probe.sh"


def _src() -> str:
    assert SCRIPT.exists(), f"{SCRIPT} 부재"
    return SCRIPT.read_text(encoding="utf-8")


def _code() -> str:
    """주석 줄(선행 공백 + #)을 뺀 코드만 — 설명문에 등장하는 채널 이름·용어는 검사 대상이 아니다."""
    return "\n".join(l for l in _src().splitlines() if not l.lstrip().startswith("#"))


def test_bash_syntax_ok():
    proc = subprocess.run(["bash", "-n", str(SCRIPT)], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr


def test_loopback_default_and_key_not_printed():
    s = _src()
    assert 'BASE="${PROBE_BASE:-http://127.0.0.1:8000}"' in s, "기본 주소는 루프백이어야 한다"
    # 키는 헤더로만 전달 — echo/log/printf 인자에 key() 호출이 들어가면 안 된다
    for m in re.finditer(r"(log|echo|printf)[^\n]*\$\(key\)", s):
        raise AssertionError(f"운영 키가 출력 경로에 등장: {m.group(0)[:80]}")


def test_probe_contract_tokens():
    s = _src()
    assert 'TR_ID="${PROBE_TR_ID:-H0STCNT0}"' in s
    code = _code()
    assert "H0UNCNT0" not in code, "라이브 채널을 프로브로 쓰면 안 된다"
    assert "/api/realtime/channel-probe" in s
    assert re.search(r"api DELETE \"/api/realtime/channel-probe/\$t\"", s), "해제 경로 부재"
    assert "trap 'log \"trap: 종료 전 해제\"; stop_all' EXIT" in s, "종료 시 무조건 해제(trap) 부재"
    assert "in_desired_now" in s, "후보 편입 즉시 해제 로직 부재"
    assert "bypass_limit" not in code and "HIGH" not in code, "프로브 스크립트는 슬롯 우선순위를 건드리지 않는다"


def test_cron_is_one_shot_self_removing():
    s = _src()
    assert "crontab -l | grep -v channel_probe.sh | crontab -" in s, "cron 자기 제거 부재"
    assert 'local spec="${1:-30 9 7 9 *}"' in s, "기본 cron = 2026-09-07 09:30 1회"
