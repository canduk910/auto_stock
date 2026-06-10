"""사이클 99 G-PURGE1 — `_fetch_fluctuation` 페이징 영역 영구 폐기 (HIGH).

명세 (`_workspace/red/cycle99_pagination_removal_60_ticker_persistence.md`):

- KIS API 전체 영역 = 페이징 미지원 영구 확정 (사이클 96 + 사이클 98 운영 실증)
- 사이클 89/91/94/96/97/98 모든 페이징 영역 시정 = 영구 무용
- 사이클 99 = 페이징 영역 영구 폐기 + 60 ticker 영구 영속 명문화

영구 폐기 영역 (5종, AST + raw text 양쪽 검증):
- `for page in range` (페이징 루프 영구 부재)
- `tr_cont` 영역 (KIS 페이징 인자 영구 부재 — 함수 시그너처 + 본체)
- `_response_headers` (KIS 응답 헤더 추출 영역 영구 부재)
- `accumulated.extend` (페이징 누적 영역 영구 부재)
- `accumulated: list[dict]` (누적 변수 영역 영구 부재)

Red 상태 (사이클 99): production `_fetch_fluctuation` 페이징 영역 5종 잔존 → FAIL.

영속 의무:
- 사이클 81 silent 결함 영구 차단 패턴 답습 (`bfdy_clpr` AST)
- 사이클 88 G-REJECT 답습 (외부 LLM 정적 검증 패턴)
- 사이클 97 H-5 답습 (volume_rank URL/TR_ID 영구 차단 패턴 확장)
- silent 결함 영구 차단 21 회 누적
"""
from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit


def _scanner_module_path() -> Path:
    """scanner.py 모듈 절대 경로."""
    import src.engine.scanner as scanner_mod
    return Path(scanner_mod.__file__)


def _fetch_fluctuation_function_source() -> str:
    """`_fetch_fluctuation` 함수 본체 source (docstring 포함, AST 추출)."""
    import src.engine.scanner as scanner_mod
    try:
        return inspect.getsource(scanner_mod._fetch_fluctuation)
    except (AttributeError, OSError, TypeError) as e:
        pytest.fail(
            f"\n사이클 99 G-PURGE1 Red 상태 — `_fetch_fluctuation` 함수 추출 실패: {e}\n"
            "  사이클 97 영역 = `_fetch_fluctuation` 신규 함수 영속 의무"
        )


def _fetch_fluctuation_function_node() -> ast.AsyncFunctionDef:
    """`_fetch_fluctuation` AST 함수 노드 추출."""
    source = _scanner_module_path().read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if (isinstance(node, ast.AsyncFunctionDef)
                and node.name == "_fetch_fluctuation"):
            return node
    pytest.fail(
        "\n사이클 99 G-PURGE1 Red 상태 — `_fetch_fluctuation` AST 노드 추출 실패.\n"
        "  사이클 97 영역 = `_fetch_fluctuation` 신규 함수 영속 의무"
    )


def test_g_purge1_pagination_legacy_areas_permanently_removed():
    """G-PURGE1: `_fetch_fluctuation` 페이징 영역 5종 영구 폐기 검증 (raw text + AST).

    영구 폐기 영역 매트릭스 (사이클 91/97 페이징 영역 영속 → 사이클 99 영구 폐기):

    | 영역 | 사이클 97 영속 | 사이클 99 영구 폐기 |
    |------|---------------|--------------------|
    | `for page in range` | 페이징 루프 | 영구 부재 |
    | `tr_cont` 영역 | KIS 페이징 인자 | 영구 부재 (시그너처 + 본체) |
    | `_response_headers` | KIS 응답 헤더 추출 | 영구 부재 |
    | `accumulated.extend` | 페이징 누적 영역 | 영구 부재 |
    | `accumulated: list[dict]` | 누적 변수 선언 | 영구 부재 |

    Red 상태 (사이클 99): 사이클 97 영역 5종 잔존 → FAIL.

    Green (backend-dev): `_fetch_fluctuation` 본체 영역 페이징 영역 영구 폐기 → PASS.
        - `accumulated: list[dict] = []` 변수 영구 폐기
        - `tr_cont = ""` 변수 영구 폐기
        - `for page in range(max_pages):` 루프 영구 폐기
        - `tr_cont=tr_cont,` 인자 영역 (kis_get_quote 호출) 영구 폐기
        - `data.get("_response_headers", {}).get("tr_cont", "")` 영역 영구 폐기
        - `if next_tr_cont != "M": break` 영역 영구 폐기
        - `tr_cont = "N"` 갱신 영역 영구 폐기
        - `await _asyncio.sleep(0.05)` 영역 영구 폐기

    영속 의무:
    - 미래 KIS API 페이징 영역 silent 결함 재도입 영구 차단
    - 사이클 89/91/94/96/97/98 모든 페이징 영역 영구 무용 영속
    """
    source = _fetch_fluctuation_function_source()

    forbidden_patterns = {
        "for page in range": (
            "페이징 루프 영구 폐기 위반",
            "Green: `for page in range(max_pages):` 루프 영구 폐기 의무",
        ),
        "_response_headers": (
            "KIS 응답 헤더 추출 영역 영구 폐기 위반",
            "Green: `data.get('_response_headers', {}).get('tr_cont', '')` 영역 영구 폐기 의무",
        ),
        "accumulated.extend": (
            "페이징 누적 영역 영구 폐기 위반",
            "Green: `accumulated.extend(output)` 영역 영구 폐기 의무 (단일 호출 = 누적 불요)",
        ),
        "accumulated: list[dict]": (
            "누적 변수 선언 영역 영구 폐기 위반",
            "Green: `accumulated: list[dict] = []` 영역 영구 폐기 의무",
        ),
    }

    violations: list[str] = []
    for pattern, (reason, fix_hint) in forbidden_patterns.items():
        if pattern in source:
            violations.append(
                f"  - 패턴 {pattern!r} 잔존: {reason}\n    {fix_hint}"
            )

    # AST 검증: tr_cont 인자 영구 폐기 (시그너처)
    node = _fetch_fluctuation_function_node()
    arg_names = [a.arg for a in node.args.args] + [a.arg for a in node.args.kwonlyargs]
    if "tr_cont" in arg_names:
        violations.append(
            f"  - 함수 시그너처 `tr_cont` 인자 잔존: KIS 페이징 인자 영구 폐기 위반\n"
            f"    현재 인자: {arg_names}\n"
            f"    Green: `tr_cont` 인자 영구 폐기 의무 (페이징 영역 영구 폐기)"
        )

    # AST 검증: max_pages 인자 영구 폐기 (페이징 마진)
    if "max_pages" in arg_names:
        violations.append(
            f"  - 함수 시그너처 `max_pages` 인자 잔존: 페이징 안전 마진 영구 폐기 위반\n"
            f"    현재 인자: {arg_names}\n"
            f"    Green: `max_pages` 인자 영구 폐기 의무 (페이징 영역 영구 폐기)"
        )

    assert not violations, (
        f"\n사이클 99 G-PURGE1 위반 — `_fetch_fluctuation` 페이징 영역 영구 폐기 의무 잔존:\n"
        + "\n".join(violations)
        + "\n\n"
        f"  KIS API 본질 한계 영구 확정 매트릭스 (사이클 96 + 사이클 98 운영 실증):\n"
        f"    - volume_rank (FHPST01710000) = tr_cont 'M' 영구 비반환\n"
        f"    - fluctuation (FHPST01700000) = tr_cont 'M' 영구 비반환\n"
        f"    - KIS API 전체 영역 = 페이징 미지원 영구 확정\n"
        f"  사이클 99 영역 영구 영속:\n"
        f"    - 60 ticker 영구 영속 수용 (KOSPI 30 + KOSDAQ 30)\n"
        f"    - 페이징 영역 영구 폐기 (사이클 91~98 모든 시정 영구 무용)\n"
        f"    - 미래 페이징 영역 재도입 silent 결함 영구 차단\n"
        f"  명세 영속: `_workspace/red/cycle99_pagination_removal_60_ticker_persistence.md`\n"
        f"  silent 결함 영구 차단 21 회 누적 (사이클 60~98 + 99)"
    )
