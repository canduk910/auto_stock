"""사이클 89 M-6 — 사이클 81 `bfdy_clpr` 키 시정 영속.

명세 (`_workspace/red/cycle89_stock_master_500_universe.md`):

domain-expert 자문 영속:
- 사이클 81 silent 결함 차단 = `prdy_clpr` → `bfdy_clpr` 키 시정 영속
- 500 universe 적재 후 `_apply_price_filter` 정확 발화
- `bfdy_clpr` 키 = CTPF1002R 응답 정본 키 (전일종가)

기대 동작 (Green, 사이클 90):
- 500 universe 적재 → CTPF1002R 응답 `bfdy_clpr` 키 보존
- `_apply_price_filter` 에서 `basics.raw.get("bfdy_clpr", 0)` 호출 (사이클 81 시정 영속)
- 사이클 89 시정해도 `prdy_clpr` 키 침범 0 (silent 결함 영구 차단)

Red 상태 (사이클 89): `_apply_price_filter` 본체에 `prdy_clpr` 키 등장 시 FAIL
(사이클 81 silent 결함 영구 차단 위반).

영속 의무:
- 사이클 81 영속 (silent 결함 영구 차단 19회 누적)
- 사이클 31 R6 영속 (가격필터 정상 발화로 R6 우회 자연 차단)
- 매매 안전성 영향 0 (scanner 단계 영역)
"""
from __future__ import annotations

import inspect

import pytest

pytestmark = pytest.mark.unit


def test_m6_cycle81_bfdy_clpr_key_persists_in_apply_price_filter():
    """M-6: 사이클 81 `bfdy_clpr` 키 시정 영속 (`prdy_clpr` 키 영구 차단).

    검증 매트릭스:
    - `_apply_price_filter` 본체에 `bfdy_clpr` 키 등장 ≥ 1건
    - `_apply_price_filter` 본체에 `prdy_clpr` 키 등장 0건 (silent 결함 영구 차단)

    Red 상태 (사이클 89): `prdy_clpr` 키 등장 시 FAIL (사이클 81 영속 위반).

    Green (사이클 90): backend-dev 가 사이클 89 시정해도 사이클 81 `bfdy_clpr` 키 영속 → PASS.

    영속 의무:
    - 사이클 81 silent 결함 영구 차단 패턴 영속
    - 사이클 89 신규 함수 영역에서 동일 silent 결함 재발 방지
    """
    try:
        from src.engine.scanner import _apply_price_filter
    except ImportError:
        pytest.fail(
            "\n사이클 89 M-6 위반 — 사이클 64 `_apply_price_filter` 헬퍼 부재:\n"
            "  영속 의무: 사이클 89 시정해도 사이클 64/81 헬퍼 영역 무변경"
        )

    source = inspect.getsource(_apply_price_filter)

    # 가드 1: `bfdy_clpr` 키 등장 ≥ 1건 (사이클 81 시정 영속)
    bfdy_count = source.count("bfdy_clpr")
    assert bfdy_count >= 1, (
        f"\n사이클 89 M-6 위반 — `_apply_price_filter` 본체에 `bfdy_clpr` 키 누락:\n"
        f"  현재 등장 횟수: {bfdy_count} (≥ 1 필요)\n"
        f"  영속 의무: 사이클 81 silent 결함 영구 차단 패턴 영속\n"
        f"  - CTPF1002R 응답 정본 키 = `bfdy_clpr` (전일종가)"
    )

    # 가드 2: `prdy_clpr` 키 등장 0건 (사이클 81 silent 결함 영구 차단)
    # 단, 주석/docstring 내 시정 이력 참조는 허용 (사이클 81 시정 이력 영구 기록 영역)
    # 따라서 코드 영역만 검사 — 정확한 검사를 위해 단순 substring count 가 아닌
    # AST 분석 도입 가능하나 단순 substring 으로 대체 (`prdy_clpr` 문자열 등장 = 사이클 81 위반 위험)
    # docstring/주석 내 `prdy_clpr` 등장 = 사이클 81 시정 이력 참조 허용
    code_lines = [
        line for line in source.split("\n")
        if not line.strip().startswith("#") and '"""' not in line
    ]
    code_text = "\n".join(code_lines)
    prdy_count = code_text.count('"prdy_clpr"') + code_text.count("'prdy_clpr'")
    assert prdy_count == 0, (
        f"\n사이클 89 M-6 위반 — `_apply_price_filter` 코드 영역에 `prdy_clpr` 키 발견:\n"
        f"  현재 등장 횟수: {prdy_count} (= 0 필요)\n"
        f"  영속 의무: 사이클 81 silent 결함 영구 차단 패턴 영속\n"
        f"  - CTPF1002R 응답에 `prdy_clpr` 키 부재 → graceful 통과 = 가격필터 무용 영역\n"
        f"  - 사이클 81 시정 영속 (`bfdy_clpr` 단독 사용)"
    )
