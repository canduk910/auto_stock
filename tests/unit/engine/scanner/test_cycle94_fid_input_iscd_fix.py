"""사이클 94 H-1 — `_MARKET_INPUT_ISCD` "0000" 단일화 + 업종코드 영속 부재 (HIGH).

명세 (`_workspace/red/cycle94_fid_input_iscd_fix.md`):

- KIS 정본 (`examples_llm/.../volume_rank.py`) = `FID_INPUT_ISCD = "0000"` (전체)
- 사이클 89/91 결함 = `"0001"` (KOSPI 업종) / `"0002"` (KOSDAQ 업종)
- 업종코드 응답 = 단일 페이지 30건 한도 (페이징 미지원) → 60 ticker 영속
- 사이클 94 시정 = `_MARKET_INPUT_ISCD` value 가 `"0000"` 만 포함

기대 동작 (Green, backend-dev 인계):
- `_MARKET_INPUT_ISCD.values()` 가 `{"0000"}` 만 포함
- `"0001"` / `"0002"` 업종코드 부재

Red 상태 (사이클 94): production 코드 `"0001"` / `"0002"` 영속 → FAIL.

영속 의무:
- KIS MCP 정본 인용 (`mcp__kis-code-assistant__search_domestic_stock_api`)
- 사이클 91 페이징 영역 정합 (KIS "0000" 전체 영역 17+ 페이지)
- 매매 안전성 영향 0 (scanner 단계 = 매수 진입 *전*, 사이클 38 명문화 영속)
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit


@pytest.mark.xfail(
    strict=False,
    reason=(
        "사이클 96 Q50=D — 사이클 89 영역 복원 (`'0001'`/`'0002'`) + 사이클 91 페이징 결합. "
        "사이클 94 단일화 (`'0000'` 단일) 폐기 계약 — KIS 운영 실측 '0000' = 단일 페이지 30 한도 + 페이징 미지원 silent 결함. "
        "사이클 66 K-2 의미 전환 패턴."
    ),
)
def test_h1_market_input_iscd_only_contains_0000():
    """H-1.a: `_MARKET_INPUT_ISCD` value 영역에 `"0000"` 만 포함 + 업종코드 부재.

    검증 매트릭스:
    - dict.values() 가 `{"0000"}` set 와 일치
    - `"0001"` 부재 (KOSPI 업종코드 영속 결함 영구 차단)
    - `"0002"` 부재 (KOSDAQ 업종코드 영속 결함 영구 차단)

    Red 상태 (사이클 94): 사이클 89/91 영속 `{"1": "0001", "2": "0002"}` → FAIL.

    Green (backend-dev): `{"all": "0000"}` 단일화 → PASS.

    KIS MCP 정본 인용:
        FID_INPUT_ISCD = "0000" (전체) — 페이징 17+ 페이지 정상
        FID_INPUT_ISCD = "0001"/"0002" (업종코드) — 30건 한도, 페이징 미지원
    """
    from src.engine.scanner import _MARKET_INPUT_ISCD

    values_set = set(_MARKET_INPUT_ISCD.values())

    assert values_set == {"0000"}, (
        f"\n사이클 94 H-1.a 위반 — `_MARKET_INPUT_ISCD` value 영역 결함:\n"
        f"  기대: {{'0000'}} (KIS 정본 전체 영역)\n"
        f"  실제: {values_set}\n"
        f"  결함 인과:\n"
        f"    - '0001' / '0002' = KIS 업종코드 (단일 페이지 30건 한도)\n"
        f"    - '0000' = KIS 전체 (페이징 17+ 페이지 정상 = 500 ticker 영속)\n"
        f"  사이클 89/91 silent 결함 영구 시정 의무"
    )


@pytest.mark.xfail(
    strict=False,
    reason=(
        "사이클 96 Q50=D — 사이클 89 영역 복원 (`'0001'`/`'0002'`). "
        "사이클 94 H-1.b 영역 (업종코드 부재 가드) 폐기 계약 = 사이클 96 영역 복원 후 업종코드 영속 정상. "
        "사이클 66 K-2 의미 전환 패턴."
    ),
)
def test_h1_market_input_iscd_no_industry_codes():
    """H-1.b: `_MARKET_INPUT_ISCD` 에 `"0001"` / `"0002"` 업종코드 부재 영구 가드.

    AST 정적 검증 - dict literal value 직접 검증.

    영속 의무: 미래 사이클에서 업종코드 회귀 영구 차단.
    """
    from src.engine.scanner import _MARKET_INPUT_ISCD

    forbidden_codes = {"0001", "0002"}
    intersection = forbidden_codes & set(_MARKET_INPUT_ISCD.values())

    assert intersection == set(), (
        f"\n사이클 94 H-1.b 위반 — 업종코드 영속 결함:\n"
        f"  금지 코드: {forbidden_codes}\n"
        f"  잔존 영역: {intersection}\n"
        f"  KIS 업종코드 = 단일 페이지 30건 한도 = 페이징 미지원\n"
        f"  사이클 94 시정 후 영구 부재 의무"
    )
