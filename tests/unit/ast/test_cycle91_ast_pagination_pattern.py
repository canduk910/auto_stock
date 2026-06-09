"""사이클 91 L-1 — `_fetch_volume_rank` 정적 AST 가드 (silent 결함 영구 차단).

명세 (`_workspace/red/cycle91_volume_rank_pagination.md`):

- 사이클 89 silent 결함 (단일 호출 + slicing) 영구 재발 차단
- KIS 정본 페이징 패턴 정적 검증

검증 패턴 (`_fetch_volume_rank` 본체 source 정적 grep):
- `tr_cont` 키워드 ≥ 2 회 사용 (입력 + 추출)
- `max_pages` 변수 사용 (무한 루프 차단)
- `range(max_pages)` 패턴 사용 (페이지 루프)
- `asyncio.sleep` 호출 (Rate Limit 보호)

Red 상태 (사이클 91): production 코드 단일 호출 → AST 패턴 부재 → FAIL.

영속 의무:
- 사이클 81 `bfdy_clpr` AST 답습 (silent 결함 영구 차단 패턴)
- 사이클 88 G-REJECT 답습 (정적 검증 + 미래 재발 영구 차단)
"""
from __future__ import annotations

import ast
import inspect

import pytest

pytestmark = pytest.mark.unit


def _get_function_source(func_name: str) -> str:
    """`src.engine.scanner` 모듈에서 함수 본체 소스 추출 (정적 grep)."""
    from src.engine import scanner as scanner_mod
    func = getattr(scanner_mod, func_name, None)
    if func is None:
        return ""
    try:
        return inspect.getsource(func)
    except (TypeError, OSError):
        return ""


def test_l1_fetch_volume_rank_tr_cont_keyword_pattern():
    """L-1.a: `_fetch_volume_rank` 본체에 `tr_cont` 키워드 ≥ 2 회 사용.

    KIS 정본 페이징 패턴 = 입력 + 응답 헤더 추출 양쪽 영역.

    영속 의무: 단일 호출 silent 결함 영구 차단.
    """
    source = _get_function_source("_fetch_volume_rank")
    assert source, (
        "\n사이클 91 L-1.a 위반 — `_fetch_volume_rank` 함수 부재:\n"
        "  Green 의무: src/engine/scanner.py 에 함수 영속"
    )

    tr_cont_count = source.count("tr_cont")
    assert tr_cont_count >= 2, (
        f"\n사이클 91 L-1.a 위반 — `tr_cont` 키워드 사용 부족:\n"
        f"  실제 사용: {tr_cont_count} 회 (의무 ≥ 2)\n"
        f"  KIS 정본 패턴: 입력 `tr_cont=tr_cont` + 응답 헤더 `tr_cont` 추출\n"
        f"  silent 결함 영구 차단 의무 (사이클 89 단일 호출 패턴 재발 차단)"
    )


def test_l1_fetch_volume_rank_max_pages_guard():
    """L-1.b: `_fetch_volume_rank` 본체에 `max_pages` + `range(` 무한 루프 가드.

    KIS LMS chain 차단 영구 가드.
    """
    source = _get_function_source("_fetch_volume_rank")
    assert source, (
        "\n사이클 91 L-1.b 위반 — `_fetch_volume_rank` 함수 부재"
    )

    assert "max_pages" in source, (
        f"\n사이클 91 L-1.b 위반 — `max_pages` 무한 루프 가드 부재:\n"
        f"  Green 의무: max_pages=15 디폴트 + 루프 가드\n"
        f"  KIS LMS chain 차단 (무한 페이징 영구 차단)"
    )

    has_page_loop = (
        "for page in range" in source
        or "range(max_pages)" in source
    )
    assert has_page_loop, (
        f"\n사이클 91 L-1.b 위반 — `range(max_pages)` 페이지 루프 패턴 부재:\n"
        f"  Green 의무: `for page in range(max_pages):` 패턴\n"
        f"  KIS LMS chain 차단 영구 가드"
    )


def test_l1_fetch_volume_rank_rate_limit_sleep():
    """L-1.c: `_fetch_volume_rank` 본체에 `asyncio.sleep` 호출 (Rate Limit 보호).

    사이클 83 50ms sleep 답습.
    """
    source = _get_function_source("_fetch_volume_rank")
    assert source, (
        "\n사이클 91 L-1.c 위반 — `_fetch_volume_rank` 함수 부재"
    )

    has_sleep = (
        "asyncio.sleep" in source
        or "_asyncio.sleep" in source
        or ".sleep(" in source
    )
    assert has_sleep, (
        f"\n사이클 91 L-1.c 위반 — `asyncio.sleep` Rate Limit 보호 부재:\n"
        f"  Green 의무: 페이지 간 await asyncio.sleep(0.05) (50ms)\n"
        f"  사이클 83 답습 (KIS Rate Limit 보호)"
    )


def test_l1_fetch_volume_rank_response_headers_extraction():
    """L-1.d: `_fetch_volume_rank` 본체에서 `_response_headers` 응답 헤더 추출.

    KIS 정본 `tr_cont` 응답 헤더 추출 영역 정적 검증.
    """
    source = _get_function_source("_fetch_volume_rank")
    assert source, (
        "\n사이클 91 L-1.d 위반 — `_fetch_volume_rank` 함수 부재"
    )

    has_headers_extract = "_response_headers" in source
    assert has_headers_extract, (
        f"\n사이클 91 L-1.d 위반 — `_response_headers` 응답 헤더 추출 부재:\n"
        f"  Green 의무: data.get('_response_headers', {{}}).get('tr_cont', '')\n"
        f"  KIS 정본 패턴: 응답 헤더 tr_cont == 'M' → 다음 페이지 호출"
    )


def test_l1_fetch_volume_rank_ast_for_loop_validation():
    """L-1.e: AST 정적 분석으로 `for` 페이지 루프 영역 검증.

    silent 결함 영구 차단 (사이클 89 단일 호출 패턴 미래 재발 영구 차단).
    """
    source = _get_function_source("_fetch_volume_rank")
    assert source, (
        "\n사이클 91 L-1.e 위반 — `_fetch_volume_rank` 함수 부재"
    )

    # AST 정적 검증 — for 문 ≥ 1 개 (페이지 루프)
    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        pytest.fail(
            f"\n사이클 91 L-1.e 위반 — AST 파싱 실패:\n  {e}"
        )

    for_nodes = [n for n in ast.walk(tree) if isinstance(n, (ast.For, ast.AsyncFor))]
    assert len(for_nodes) >= 1, (
        f"\n사이클 91 L-1.e 위반 — for 루프 부재 (단일 호출 silent 결함 재발 위험):\n"
        f"  실제 for 노드: {len(for_nodes)} (의무 ≥ 1 = 페이지 루프)\n"
        f"  Green 의무: `for page in range(max_pages):` 페이지 루프\n"
        f"  silent 결함 영구 차단 (사이클 89 단일 호출 패턴 재발 영구 차단)"
    )
