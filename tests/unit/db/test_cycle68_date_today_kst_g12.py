"""사이클 68 G-12 — `date.today()` 호출자 KST 점검 (Q1, LOW).

> **Q1 채택**: LOW 9~12 항목 (DATE only 호출자 `date.today()` KST 점검) 본 사이클 포함.
>   `date.today()` 는 서버 timezone 의존 → KST 영업일과 어긋날 위험.
>   허용: `datetime.now(KST).date()` 또는 `_today_kst()` 헬퍼.
>
> Red 시점: `src/` 전체 12+건 잔존 → **FAIL** 의무 (시정 의무 가시화).
>
> Green 후: backend-dev 가 `datetime.now(KST).date()` 또는 `_today_kst()` 헬퍼로 교체.

검증 방식: `src/` 전체 `*.py` 정규식 검색. `date.today()` (또는 alias `_date.today()`)
호출이 있는 모든 위치 수집 → 위반 리스트로 보고.

> **회귀 위험 영역** (대표):
> - `src/db/parameter_recommendations.py:79` `list_recommendations` cutoff 계산
> - `src/engine/strategy_base.py:50` / `strategy.py:47` `is_overnight` 익일 청산 판정
> - `src/engine/scheduler.py:1723,2832` 매크로 스냅샷 + 정산 date
> - `src/engine/boot_manager.py:84` _boot 영업일 결정
> - `src/engine/backtest_engine.py:152` 백테스트 end_date 기본
> - `src/engine/strategies/volatility_breakout.py:105` / `long_tail_volatility.py:114` today_str
> - `src/api/balance.py:190` / `src/api/condition.py:368` KIS 호출 영업일
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit


# 본 가드 적용 예외 (테스트 코드 / 백테스트 보조 / 기록 보관용 등)
_G12_EXEMPT_FILES: frozenset[str] = frozenset({
    # 향후 예외 추가 시 명시. 현재 0건.
})


def test_g12_no_date_today_in_src():
    """G-12 (LOW) — `src/` 전체에 `date.today()` 호출 0건 의무.

    서버 timezone 의존 → KST 영업일 어긋남 위험.
    허용 패턴:
    - `datetime.now(KST).date()`
    - `_today_kst()` (헬퍼 도입 시)
    - `now_kst_iso()` 파생

    현재 (Red): `src/` 전체 12+건 잔존 → 시정 의무 가시화.
    Green 후: backend-dev 가 일괄 교체 → PASS 전환.
    """
    src_root = Path("src")
    assert src_root.exists(), f"src/ 경로 결함: {src_root.resolve()}"

    # `date.today()` 또는 `_date.today()` 또는 다른 alias 모두 검출
    # word boundary 로 'datetime' / 'datetime.date' 등 다른 패턴 회피
    pattern = re.compile(r"(?<![\w\.])(?:date|_date)\.today\s*\(\s*\)")

    violations: list[str] = []
    files_scanned = 0

    for py_file in src_root.rglob("*.py"):
        rel = py_file.relative_to(src_root)
        if str(rel) in _G12_EXEMPT_FILES:
            continue
        files_scanned += 1
        try:
            source = py_file.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for lineno, line in enumerate(source.splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if pattern.search(line):
                violations.append(f"{rel}:L{lineno} — {stripped}")

    assert files_scanned > 0, "src/ 스캔 파일 0건 — 가드 적용 범위 회귀 의심"

    assert not violations, (
        f"`date.today()` / `_date.today()` 사용 금지 — 서버 timezone 의존 → "
        f"KST 영업일 어긋남 위험. 허용: `datetime.now(KST).date()` 또는 "
        f"`_today_kst()` 헬퍼.\n사이클 68 Q1 시정 의무 (Green 단계 backend-dev).\n"
        f"위반 {len(violations)}건:\n" + "\n".join(violations)
    )
