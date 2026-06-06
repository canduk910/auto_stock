"""사이클 64 (2026-06-06) Red — G 카테고리: AST 정적 가드 (2 케이스, **HIGH**).

> **선행 명세**: `_workspace/red/cycle64_price_filter_scanner.md` (§G)
> **자문 응답**: `_workspace/cycle64_price_filter_scanner_domain_response.md`
>   - G-1 (자문 Q4-3): 사이클 62 코드 완전 제거 영속 가드
>   - G-2 (자문 Q1 옵션 D): `_apply_price_filter` 호출 시 `protected_tickers=` keyword 의무
> **선례**: 사이클 60 Q3-G6 / 사이클 61 D-1 / 사이클 63 D-2 AST 가드 패턴 답습

요구 행위 (Red 단계 모두 AssertionError 정답 — risk.py 잔재 + scanner 미구현):

- G-1 (HIGH): `src/engine/risk.py` 전체에 `price_filter` 문자열 매칭 0건
- G-2 (HIGH): `_apply_price_filter` 호출 시 `protected_tickers=` keyword-only 인자 필수

위험 등급 HIGH:
- G-1 = 사이클 62 코드 cleanup 영속 가드 (잔재 코드 매수 흐름 결함 차단)
- G-2 = 호출자 깜빡 위험 차단 (early-return 가드 자동 우회 방지)

CLAUDE.md 절대 규칙 보호:
- "**WebSocket 시세 보유·익일청산 우선 보장**" — G-2 가 protected_tickers 누락 영구 차단
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit


# ===========================================================================
# G-1 (HIGH): risk.py 가격 필터 코드 완전 제거 영속 가드
# ===========================================================================
def test_G1_risk_py_no_price_filter_references():
    """G-1 (HIGH): `src/engine/risk.py` 에 가격 필터 관련 참조 0건.

    사이클 62 코드 (PRICE_FILTER_CACHE_TTL / _get_price_filter_cached /
    invalidate_price_filter_cache / _emit_price_filter_skip / _emit_price_filter_warn /
    _emit_price_filter_daily_summary / PriceFilter import 등) 완전 제거 영속 가드.

    잔재 시 risk.on_tick 매수 흐름 결함 (이중 평가 / 호환성 결함) 위험.
    """
    risk_path = Path("src/engine/risk.py")
    assert risk_path.exists(), f"risk.py 경로 결함: {risk_path.resolve()}"
    src = risk_path.read_text(encoding="utf-8")

    # 금지 문자열 — 사이클 62 코드 전부
    forbidden_strings = [
        "PriceFilter",                       # import + 타입 어노테이션
        "get_price_filter",                  # DB 헬퍼 + 캐시 분기
        "_get_price_filter_cached",          # 사이클 62 캐시 메서드
        "invalidate_price_filter_cache",     # 사이클 62 invalidate 메서드
        "_emit_price_filter_skip",           # 사이클 62 skip emit
        "_emit_price_filter_warn",           # 사이클 62 warn emit
        "_emit_price_filter_daily_summary",  # 사이클 62 일일 집계
        "_price_filter_cache",               # 사이클 62 캐시 필드
        "_price_filter_skip_logged_today",   # 사이클 62 cap 필드
        "_price_filter_warn_logged_today",   # 사이클 62 cap 필드
        "_price_filter_skip_count_today",    # 사이클 62 카운터 필드
        "_price_filter_warn_count_today",    # 사이클 62 카운터 필드
        "_price_filter_skip_reasons_today",  # 사이클 62 reasons 필드
        "PRICE_FILTER_CACHE_TTL",            # 사이클 62 상수
        "[price_filter_skip]",               # 사이클 62 로그 prefix
        "[price_filter_warn]",               # 사이클 62 로그 prefix
        "[price_filter_daily_summary]",      # 사이클 62 로그 prefix
    ]

    violations = []
    for forbidden in forbidden_strings:
        if forbidden in src:
            # 라인 번호 찾기 (가시화)
            for lineno, line in enumerate(src.splitlines(), 1):
                if forbidden in line:
                    violations.append(f"  L{lineno}: {forbidden!r} — {line.strip()[:80]}")

    assert not violations, (
        f"사이클 62 가격 필터 코드 잔재 — risk.py 에서 {len(violations)}건 발견. "
        f"사이클 64 완전 제거 가드 위반:\n" + "\n".join(violations[:20])
    )


# ===========================================================================
# G-2 (HIGH): `_apply_price_filter` 호출 시 protected_tickers keyword 의무
# ===========================================================================
def test_G2_apply_price_filter_must_pass_protected_tickers_kwarg():
    """G-2 (HIGH, Q1 옵션 D): `_apply_price_filter` 호출 시 `protected_tickers=` keyword 필수.

    호출자가 깜빡 `_apply_price_filter(candidates)` 만 호출하면 보유/익일청산 종목이
    필터링 대상에 진입 → 시세 끊김 → 손절 발화 0 결함.

    AST 정적 검증 — `scanner.py` + `scheduler.py` 양쪽 모듈 전체 스캔.
    호출 식별 방법:
    1. `Attribute` (`xxx._apply_price_filter(...)`) — 인스턴스 메서드 호출
    2. `Name` (`_apply_price_filter(...)`) — 모듈 함수 직접 호출

    위치 인자만 사용 시 검증 실패 (AST 가드).
    """
    sources = {}
    for path_str in ("src/engine/scanner.py", "src/engine/scheduler.py"):
        path = Path(path_str)
        assert path.exists(), f"경로 결함: {path.resolve()}"
        sources[path_str] = path.read_text(encoding="utf-8")

    violations = []
    for path_str, source in sources.items():
        try:
            tree = ast.parse(source)
        except SyntaxError as e:
            violations.append(f"{path_str}: SyntaxError {e}")
            continue

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            fn = node.func

            # 호출 함수명 식별
            fname = None
            if isinstance(fn, ast.Attribute) and fn.attr == "_apply_price_filter":
                fname = "_apply_price_filter"
            elif isinstance(fn, ast.Name) and fn.id == "_apply_price_filter":
                fname = "_apply_price_filter"

            if fname is None:
                continue

            # keyword 인자에 `protected_tickers` 명시 의무
            kw_keys = {kw.arg for kw in node.keywords if kw.arg is not None}
            if "protected_tickers" not in kw_keys:
                violations.append(
                    f"{path_str}:L{node.lineno} — `_apply_price_filter` 호출 시 "
                    f"`protected_tickers=` keyword 누락 (kwargs={sorted(kw_keys)})"
                )

    assert not violations, (
        f"G-2 (HIGH) 자문 옵션 D 위반 — `protected_tickers=` keyword 누락 호출 "
        f"{len(violations)}건. 보유/익일청산 보호 우회 결함 위험:\n"
        + "\n".join(violations)
    )


# ===========================================================================
# G-3 (HIGH, 사이클 64 hotfix AST 가드, tester verify 발견 결함 영구 차단)
# ===========================================================================
def test_G3_no_caller_of_deprecated_emit_price_filter_daily_summary_anywhere_in_src():
    """G-3 (HIGH, hotfix AST 가드): 사이클 62 폐기 메서드 호출 src/ 전체 0건.

    배경 — tester verify 발견 결함:
    - `risk_manager._emit_price_filter_daily_summary` 는 사이클 62 가 도입했으나
      사이클 64 G3 (risk.py 가격 필터 완전 폐기) 시 *메서드 함께 삭제* 됨.
    - 그러나 scheduler.py:639 의 호출은 잔존 → 매일 20:10 정산 직전
      `AttributeError` 발생 + except logger.debug graceful skip → silent 결함화
    - scanner 신규 `emit_price_filter_scanner_daily_summary` 어디서도 호출 안 됨
    - 결과: 사이클 64 H 카테고리 운영자 가시화 카드 *완전 무력화*

    검증 (AST 정적, src/ 전체):
    - `_emit_price_filter_daily_summary` Attribute 접근/호출 0건

    G-3 는 H-2 (scheduler 한정) 보다 더 광범위한 안전망:
    - src/ 어디서든 잔재 호출 발견 시 FAIL
    - 사이클 64 이후 신규 모듈/리팩토링 에서 폐기 메서드 호출 잔존 영구 차단

    위험 등급 HIGH — silent 결함화 (AttributeError graceful skip) 영구 차단.
    """
    import ast
    from pathlib import Path

    src_root = Path("src")
    assert src_root.exists() and src_root.is_dir(), (
        f"src/ 경로 결함: {src_root.resolve()}"
    )

    deprecated_calls: list[str] = []
    for py_file in src_root.rglob("*.py"):
        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8"))
        except SyntaxError:
            # 파일 손상 시 skip — 다른 가드에서 별도 검출
            continue
        for node in ast.walk(tree):
            # Attribute 접근 (xxx._emit_price_filter_daily_summary)
            if isinstance(node, ast.Attribute) and node.attr == "_emit_price_filter_daily_summary":
                deprecated_calls.append(f"{py_file}:L{node.lineno}")
            # 모듈 함수 직접 호출 (_emit_price_filter_daily_summary())
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                if node.func.id == "_emit_price_filter_daily_summary":
                    deprecated_calls.append(f"{py_file}:L{node.lineno} (direct call)")

    assert not deprecated_calls, (
        f"사이클 62 폐기 메서드 `_emit_price_filter_daily_summary` 호출 잔존 "
        f"({len(deprecated_calls)}건) — 사이클 64 G3 risk.py 가격 필터 폐기 시 "
        f"메서드 함께 삭제됨. 잔존 호출 = AttributeError + graceful skip 으로 "
        f"silent 결함화 (운영자 가시화 카드 무력화):\n"
        + "\n".join(deprecated_calls)
        + "\n→ `scanner.emit_price_filter_scanner_daily_summary` 로 교체 의무 (사이클 64 H 신규 prefix)"
    )
