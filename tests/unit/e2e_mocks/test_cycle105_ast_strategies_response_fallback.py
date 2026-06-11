"""사이클 105 — `Strategies.tsx` 응답 형식 fallback silent 결함 영구 차단 AST 가드.

> **선례 (사이클 78 G-AST1 + 79 G-AST2 + 75 pytest AST + 102 G-DOC1 답습)**:
> - 사이클 78/79: AST 영구 가드 패턴 (미래 silent 결함 영구 차단)
> - 사이클 75: pytest AST + 정규식 grep 패턴 직접 답습
> - 사이클 81 G-AST1: 키 명명 영구 가드 패턴 답습
>
> **결함 배경 (사이클 104 발견 + 시정)**:
>   `/api/strategies` GET 응답 형식이 백엔드 영역에서 양 형식 가능:
>     (1) 내포 형식: `{ strategies: { momentum: {...}, ... } }`
>     (2) 플랫 형식: `{ momentum: {...}, ... }` (사이클 104 영역 실제 응답)
>   사이클 103 api-mocks 가 내포 형식 핸들러 추가 → LIFO 우선 매칭 →
>   Settings.tsx `getStrategies()` 가 내포 형식 받음 → `name = undefined` →
>   "상한가 모멘텀" 미렌더 → settings.spec.ts 1/13 FAIL.
>
>   사이클 104 시정 (frontend/src/pages/Strategies.tsx L157):
>     `const raw = data?.strategies ?? data`
>     ↑ 양 형식 graceful 처리 (내포 형식 미존재 시 data 자체를 플랫 형식으로 fallback).
>
> **영구 차단 의무**: 미래 fallback 제거 회귀 시 즉시 검출 영구 차단.
>   본 가드 = 사이클 104 시정 영속 영구 영속 + 응답 형식 양 영역 graceful 영구 영속.

검증 방법: `frontend/src/pages/Strategies.tsx` 텍스트 정적 grep.
"""
import re
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent.parent
STRATEGIES_PAGE_PATH = REPO_ROOT / "frontend" / "src" / "pages" / "Strategies.tsx"


def test_strategies_page_exists():
    """`Strategies.tsx` 파일 존재 의무 (방어 가드, 사이클 75 답습)."""
    assert STRATEGIES_PAGE_PATH.exists(), (
        f"Strategies.tsx 파일 누락: {STRATEGIES_PAGE_PATH}. "
        "사이클 103 신규 페이지 영역 영속 의무 — "
        "본 가드의 검증 대상 파일이 사라짐 시 본 테스트 갱신 의무."
    )


def test_cycle105_g_sf1_strategies_response_fallback_required():
    """사이클 105 G-SF1 (HIGH) — `Strategies.tsx` 본체에 `data?.strategies ?? data`
    fallback 영속 의무.

    사이클 104 silent 결함 2 (응답 형식 양 영역 graceful 누락) 영구 차단:
      - 백엔드 응답 형식이 내포 (`{strategies: {...}}`) + 플랫
        (`{momentum: {...}, ...}`) 양 형식 가능
      - fallback 없으면 한쪽 형식에서 카드 미렌더 (사이클 104 fail 시나리오)
      - 미래 fallback 제거 회귀 시 즉시 PASS → FAIL 검출
    """
    source = STRATEGIES_PAGE_PATH.read_text(encoding="utf-8")

    # `data?.strategies ?? data` 또는 동등 변형 (공백 변동 호환):
    #   - `data?.strategies ?? data`
    #   - `data?.strategies??data`
    #   - `data.strategies ?? data` (optional chaining 없이)
    # 정규식: `data\??\.strategies\s*\?\?\s*data`
    fallback_pattern = re.compile(
        r"data\??\.strategies\s*\?\?\s*data", re.MULTILINE
    )

    matches = fallback_pattern.findall(source)
    assert matches, (
        "사이클 105 G-SF1: `frontend/src/pages/Strategies.tsx` 본체에 "
        "`data?.strategies ?? data` (또는 동등 변형) fallback 패턴 미발견 — "
        "사이클 104 silent 결함 2 (응답 형식 양 영역 graceful 누락) 회귀 위험. "
        "사이클 104 시정 영역 (L157 근방): "
        "`const raw = data?.strategies ?? data` 영구 영속 의무. "
        "위반 시 백엔드 응답이 내포 (`{strategies: {...}}`) → 플랫 "
        "(`{momentum: {...}, ...}`) 전환 시 카드 미렌더 결함 재발 위험."
    )


def test_cycle105_g_sf1_fallback_comment_documents_intent():
    """사이클 105 G-SF1-bis (MEDIUM) — fallback 영역 주석에 사이클 104 시정 영역
    의도 명문화 영속 (한국어 + 영문 양 호환).

    사이클 102 G-DOC1 답습: 미래 유지보수 시 의도 영역 영구 영속.
    """
    source = STRATEGIES_PAGE_PATH.read_text(encoding="utf-8")

    # 의도 명문화 키워드 (3 중 최소 1 영속 영역):
    #   - "플랫" (한국어 의도 영역)
    #   - "내포" (한국어 의도 영역)
    #   - "fallback" (영문 의도 영역)
    intent_keywords = ["플랫", "내포", "fallback"]
    has_intent = any(kw in source for kw in intent_keywords)

    assert has_intent, (
        "사이클 105 G-SF1-bis: `Strategies.tsx` 본체에 응답 형식 fallback 의도 "
        "영역 주석 키워드 (플랫 / 내포 / fallback 중 최소 1) 미발견 — "
        "사이클 102 G-DOC1 영역 답습 영구 영속 의무. "
        "미래 유지보수 시 의도 영역 영구 영속 영역 = 사이클 104 silent 결함 2 "
        "재발 영구 차단 영역 영구 영속."
    )
