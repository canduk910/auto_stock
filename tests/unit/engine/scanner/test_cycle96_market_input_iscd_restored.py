"""사이클 96 H-1 — `_MARKET_INPUT_ISCD` 사이클 89 영역 복원 (`"0001"`/`"0002"`) (HIGH).

명세 (`_workspace/red/cycle96_resurrect_industry_code_with_pagination.md`):

- 단일 근본 원인 = KIS API "0000" 응답 단일 페이지 30 한도 + 페이징 미지원 silent 결함
- 사이클 94 단일화 (`{"all": "0000"}`) 폐기 = 운영 실측 universe 미적재
- 사이클 89 영역 복원 (`{"kospi": "0001", "kosdaq": "0002"}`) + 사이클 91 페이징 결합

기대 동작 (Green, backend-dev 인계):
- `_MARKET_INPUT_ISCD.values()` 가 `{"0001", "0002"}` 만 포함
- `"0000"` 부재 (사이클 94 영역 결함 영구 차단)
- key 영역 = `{"kospi", "kosdaq"}` (사이클 89 `"1"`/`"2"` 명명 갱신 영역)

Red 상태 (사이클 96): production 코드 `{"all": "0000"}` 영속 → FAIL.

영속 의무:
- KIS 운영 실측 영역 (docstring 영역 불일치 영구 명문화)
- 사이클 91 페이징 영역 정합 (`"0001"`/`"0002"` = 17 페이지 페이징 정상)
- 매매 안전성 영향 0 (scanner 단계 = 매수 진입 *전*, 사이클 38 명문화 영속)
"""
from __future__ import annotations

import pytest

pytestmark = [
    pytest.mark.unit,
    pytest.mark.xfail(
        strict=False,
        reason=(
            "사이클 97 Q53=A — `_MARKET_INPUT_ISCD` 영역 폐기 + `_FLUCTUATION_MARKET_INPUT_ISCD` 영역 전환. "
            "KIS fluctuation API 영역 신규 도입 (key 영역 = 'kospi'/'kosdaq' 영속, value 영역 = '0001'/'0002' 영속). "
            "사이클 97 H-1.c (FLUCTUATION dict) 가드로 영역 흡수. "
            "사이클 66 K-2 의미 전환 패턴 영속."
        ),
    ),
]


def test_h1_market_input_iscd_contains_restored_industry_codes():
    """H-1.a: `_MARKET_INPUT_ISCD` value 영역에 `"0001"` / `"0002"` 복원.

    검증 매트릭스:
    - dict.values() 가 `{"0001", "0002"}` set 와 일치
    - `"0000"` 부재 (사이클 94 단일화 영역 영구 차단)

    Red 상태 (사이클 96): 사이클 94 영속 `{"all": "0000"}` → FAIL.

    Green (backend-dev): `{"kospi": "0001", "kosdaq": "0002"}` 영역 복원 → PASS.

    KIS 운영 실측 (READ-ONLY 영구 기록):
        "0000" 응답 = 단일 페이지 30 한도 + 페이징 미지원 (docstring 영역 불일치)
        "0001"/"0002" 응답 = 페이징 정상 + 각 17 페이지 누적 가능
    """
    from src.engine.scanner import _MARKET_INPUT_ISCD

    values_set = set(_MARKET_INPUT_ISCD.values())

    assert values_set == {"0001", "0002"}, (
        f"\n사이클 96 H-1.a 위반 — `_MARKET_INPUT_ISCD` value 영역 결함:\n"
        f"  기대: {{'0001', '0002'}} (사이클 89 영역 복원 + 사이클 91 페이징 영역 결합)\n"
        f"  실제: {values_set}\n"
        f"  결함 인과:\n"
        f"    - '0000' = KIS docstring 영역 (운영 실측 단일 페이지 30 한도 silent 결함)\n"
        f"    - '0001'/'0002' = KIS 업종코드 (운영 실측 페이징 정상 17 페이지)\n"
        f"  사이클 94 단일화 영역 silent 결함 영구 시정 의무"
    )


def test_h1_market_input_iscd_no_zero_market_code():
    """H-1.b: `_MARKET_INPUT_ISCD` 에 `"0000"` 부재 영구 가드.

    AST 정적 검증 - dict literal value 직접 검증.

    영속 의무: 사이클 94 영역 회귀 영구 차단.
    """
    from src.engine.scanner import _MARKET_INPUT_ISCD

    forbidden_codes = {"0000"}
    intersection = forbidden_codes & set(_MARKET_INPUT_ISCD.values())

    assert intersection == set(), (
        f"\n사이클 96 H-1.b 위반 — '0000' 영속 결함:\n"
        f"  금지 코드: {forbidden_codes}\n"
        f"  잔존 영역: {intersection}\n"
        f"  KIS 운영 실측: '0000' = 단일 페이지 30 한도 = 페이징 미지원\n"
        f"  사이클 96 영역 복원 후 영구 부재 의무"
    )


def test_h1_market_input_iscd_keys_kospi_kosdaq():
    """H-1.c: `_MARKET_INPUT_ISCD` key 영역 = `{"kospi", "kosdaq"}`.

    사이클 89 `"1"`/`"2"` 명명에서 의미 명확 `"kospi"`/`"kosdaq"` 영역으로 갱신
    (영역 복원 시 사용자 가독성 영속).

    영속 의무: 사이클 96 영역 복원 시 key 명명 영역 영속 가시화.
    """
    from src.engine.scanner import _MARKET_INPUT_ISCD

    keys_set = set(_MARKET_INPUT_ISCD.keys())

    assert keys_set == {"kospi", "kosdaq"}, (
        f"\n사이클 96 H-1.c 위반 — `_MARKET_INPUT_ISCD` key 영역 결함:\n"
        f"  기대: {{'kospi', 'kosdaq'}}\n"
        f"  실제: {keys_set}\n"
        f"  사이클 89 영역 복원 + 명명 가독성 갱신"
    )
