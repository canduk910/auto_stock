"""사이클 68 hotfix AST 영구 가드 — 테스트 fixture date.today() 사용 금지.

배경:
    사이클 68 CI fail 9 케이스 root cause = CI 환경 UTC + production code KST aware 비교
    불일치. UTC 자정 너머 KST 시간대 (UTC 19:00~24:00 = KST 04:00~09:00 익일) 에서
    테스트 fixture 의 `date.today()` (UTC) 가 production `is_next_day` 의
    `datetime.now(KST).date()` 보다 1일 빠른 값 반환 → NEXT_DAY_CLEAR 오발동.

본 가드:
    `tests/unit/engine/strategies/` + `tests/integration/` 영역 fixture 코드의 `date.today()`
    호출 0건 강제. KST 일관성 = production code 와 fixture 양쪽 동일 timezone 의무.

향후 신규 테스트 작성 시 동일 silent 결함 영구 차단 — KST 헬퍼 (`_today_kst()` 또는
`datetime.now(_KST).date()` 인라인) 사용 의무.
"""
from __future__ import annotations

import re
from pathlib import Path


# 검사 대상 = 보유 포지션 / 매매 시간대 의존 fixture 영역 (사이클 68 fail 영역)
TARGET_DIRS = [
    "tests/unit/engine/strategies",
    "tests/integration",
]

# 정규식 — `date.today()` 호출 (괄호 포함, default_factory 함수 참조 제외)
DATE_TODAY_CALL = re.compile(r"\bdate\.today\s*\(\s*\)")


def test_strategies_and_integration_fixtures_must_not_use_date_today():
    """tests/unit/engine/strategies/ + tests/integration/ 의 date.today() 호출 0건."""
    project_root = Path(__file__).resolve().parents[2]
    violations: list[str] = []

    for rel_dir in TARGET_DIRS:
        dir_path = project_root / rel_dir
        if not dir_path.exists():
            continue
        for py_file in dir_path.rglob("*.py"):
            source = py_file.read_text(encoding="utf-8")
            for line_no, line in enumerate(source.splitlines(), start=1):
                stripped = line.strip()
                # 주석 라인 skip (단순 정적 분석)
                if stripped.startswith("#") or stripped.startswith('"') or stripped.startswith("'"):
                    continue
                if DATE_TODAY_CALL.search(line):
                    violations.append(
                        f"{py_file.relative_to(project_root)}:{line_no} — {stripped[:90]}"
                    )

    assert violations == [], (
        "tests/unit/engine/strategies/ 또는 tests/integration/ 의 date.today() 호출 발견 "
        "— CI UTC 환경에서 KST production code 와 1일 어긋남 위험 (사이클 68 hotfix 영속):\n"
        + "\n".join(f"  {v}" for v in violations)
        + "\n→ `datetime.now(timezone(timedelta(hours=9))).date()` 또는 `_today_kst()` 헬퍼 사용 의무"
    )
