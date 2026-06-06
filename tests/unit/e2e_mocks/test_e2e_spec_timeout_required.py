"""사이클 65 hotfix #3 — e2e *.spec.ts 의 toBeVisible() timeout 명시 의무 영구 가드.

사이클 65 hotfix #2 (api-mocks 라우트 누락) 시정 후 사이클 66 push 시 e2e settings.spec.ts
재 fail. 원인 = `toBeVisible()` default 5s timeout — 사이클 64+65 카드 추가로 페이지 어셈블
지연 (mock 호출 수 ↑ + React Query 처리 시간). 다른 e2e (recommendations / trading-flow) 는
`toBeVisible({ timeout: 10000 })` 명시 영속.

본 가드는 e2e/*.spec.ts 에 `toBeVisible()` (timeout 옵션 없음) 잔존 검출 →
하위 호환 안전망. 사이클 60/64/65 hotfix AST 영구 가드 패턴 답습.
"""
import re
from pathlib import Path


def test_e2e_spec_files_must_specify_timeout_for_tobevisible():
    """e2e/*.spec.ts 의 toBeVisible() 호출은 timeout 명시 의무.

    React Query mock 응답 + Settings 페이지 다중 카드 어셈블 시간 = 5s 초과 가능성.
    recommendations/trading-flow 와 패턴 통일 (timeout: 10000).
    """
    e2e_root = Path(__file__).parent.parent.parent.parent / "e2e"
    spec_files = list(e2e_root.glob("*.spec.ts"))
    assert len(spec_files) >= 3, f"e2e/*.spec.ts 최소 3개 의무 (현재 {len(spec_files)}개)"

    # toBeVisible() 호출 중 timeout 옵션 없는 패턴 검출
    # 패턴: toBeVisible() 또는 toBeVisible(); — 빈 괄호
    no_timeout_pattern = re.compile(r"\.toBeVisible\(\s*\)")
    violations = []
    for spec_file in spec_files:
        source = spec_file.read_text()
        # 주석 단순 제거 (한 줄 //, /* */ 다중 줄 — 본 가드는 간단 정규식 기반)
        # 위반 라인 검출
        for line_no, line in enumerate(source.splitlines(), start=1):
            # 주석 라인 skip
            stripped = line.strip()
            if stripped.startswith("//") or stripped.startswith("*"):
                continue
            if no_timeout_pattern.search(line):
                violations.append(f"{spec_file.name}:{line_no} — {stripped[:80]}")

    assert violations == [], (
        f"e2e/*.spec.ts 에 toBeVisible() (timeout 옵션 없음) 잔존:\n"
        + "\n".join(f"  {v}" for v in violations)
        + "\n→ toBeVisible({ timeout: 10000 }) 또는 적절한 timeout 명시 의무 "
        + "(사이클 64+65 카드 추가로 페이지 어셈블 5s 초과 위험)"
    )
