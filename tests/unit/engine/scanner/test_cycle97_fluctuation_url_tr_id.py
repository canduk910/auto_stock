"""사이클 97 H-1 — `_FLUCTUATION_URL` + `_FLUCTUATION_TR_ID` AST 상수 정합 (HIGH).

명세 (`_workspace/red/cycle97_fluctuation_api_replacement.md`):

- 사이클 89/91/94/96 영역 전수 폐기 (KIS volume_rank 단일 페이지 30 한도 + 페이징 미지원)
- KIS fluctuation API 신규 도입:
  - URL = `/uapi/domestic-stock/v1/ranking/fluctuation`
  - TR_ID = `FHPST01700000`
- KIS 정본 (open-trading-api/examples_llm/domestic_stock/fluctuation/fluctuation.py)

기대 동작 (Green, backend-dev 인계):
- `_FLUCTUATION_URL` 상수 영역 신규 도입 + KIS 정본 URL 영속
- `_FLUCTUATION_TR_ID` 상수 영역 신규 도입 + KIS 정본 TR_ID 영속

Red 상태 (사이클 97): production 코드 신규 상수 부재 → ImportError → FAIL.

영속 의무:
- KIS 정본 영역 영구 정합 (docstring + chk 정본 영구 명문화)
- 사이클 38 명문화 영속 (매수 진입 전용)
- 매매 안전성 영향 0
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit


@pytest.mark.xfail(
    strict=False,
    reason=(
        "사이클 101 Q68=A — `_FLUCTUATION_URL` 상수 영구 폐기 (fluctuation API → market_cap API 전환). "
        "사이클 97 시점 URL 상수 도입 검증 의도 영속 보존 (사이클 66 K-2 패턴 답습)."
    ),
)
def test_h1_fluctuation_url_constant_present():
    """H-1.a: `_FLUCTUATION_URL` 상수 영속 + KIS 정본 URL 영구 정합.

    KIS 정본 (open-trading-api/examples_llm/domestic_stock/fluctuation/fluctuation.py):
        API_URL = "/uapi/domestic-stock/v1/ranking/fluctuation"

    Red 상태 (사이클 97): 신규 상수 부재 → ImportError → FAIL.

    Green (backend-dev): scanner.py 에 `_FLUCTUATION_URL = "..."` 영역 신규 도입.
    """
    try:
        from src.engine.scanner import _FLUCTUATION_URL
    except ImportError:
        pytest.fail(
            "\n사이클 97 H-1.a Red 상태 — `_FLUCTUATION_URL` 상수 부재.\n"
            "  Green (backend-dev): scanner.py 에 신규 상수 도입 의무.\n"
            "    `_FLUCTUATION_URL = '/uapi/domestic-stock/v1/ranking/fluctuation'`\n"
            "  KIS 정본: open-trading-api/examples_llm/domestic_stock/fluctuation/fluctuation.py"
        )

    expected_url = "/uapi/domestic-stock/v1/ranking/fluctuation"
    assert _FLUCTUATION_URL == expected_url, (
        f"\n사이클 97 H-1.a 위반 — `_FLUCTUATION_URL` 영역 불일치:\n"
        f"  기대: {expected_url!r} (KIS 정본 영구 정합)\n"
        f"  실제: {_FLUCTUATION_URL!r}\n"
        f"  KIS 정본 (chk_fluctuation.py): `/uapi/domestic-stock/v1/ranking/fluctuation`"
    )


@pytest.mark.xfail(
    strict=False,
    reason=(
        "사이클 101 Q68=A — `_FLUCTUATION_TR_ID` 상수 영구 폐기 (fluctuation API → market_cap API 전환). "
        "사이클 97 시점 TR_ID 상수 도입 검증 의도 영속 보존 (사이클 66 K-2 패턴 답습)."
    ),
)
def test_h1_fluctuation_tr_id_constant_present():
    """H-1.b: `_FLUCTUATION_TR_ID` 상수 영속 + KIS 정본 TR_ID 영구 정합.

    KIS 정본:
        tr_id = "FHPST01700000"  # 국내주식 등락률 순위

    Red 상태 (사이클 97): 신규 상수 부재 → ImportError → FAIL.

    Green (backend-dev): scanner.py 에 `_FLUCTUATION_TR_ID = "..."` 영역 신규 도입.
    """
    try:
        from src.engine.scanner import _FLUCTUATION_TR_ID
    except ImportError:
        pytest.fail(
            "\n사이클 97 H-1.b Red 상태 — `_FLUCTUATION_TR_ID` 상수 부재.\n"
            "  Green (backend-dev): scanner.py 에 신규 상수 도입 의무.\n"
            "    `_FLUCTUATION_TR_ID = 'FHPST01700000'`"
        )

    expected_tr_id = "FHPST01700000"
    assert _FLUCTUATION_TR_ID == expected_tr_id, (
        f"\n사이클 97 H-1.b 위반 — `_FLUCTUATION_TR_ID` 영역 불일치:\n"
        f"  기대: {expected_tr_id!r} (KIS 정본 v1_국내주식-088 등락률 순위)\n"
        f"  실제: {_FLUCTUATION_TR_ID!r}\n"
        f"  KIS 정본: FHPST01700000 (국내주식 등락률 순위)"
    )


@pytest.mark.xfail(
    strict=False,
    reason=(
        "사이클 101 Q68=A — `_FLUCTUATION_MARKET_INPUT_ISCD` dict 영구 폐기 (fluctuation API → market_cap API 전환). "
        "사이클 97 시점 dict 도입 검증 의도 영속 보존 (사이클 66 K-2 패턴 답습)."
    ),
)
def test_h1_fluctuation_market_input_iscd_dict_present():
    """H-1.c: `_FLUCTUATION_MARKET_INPUT_ISCD` dict 영속 + KOSPI/KOSDAQ 매핑 영구 정합.

    KIS 정본 (fluctuation docstring):
        fid_input_iscd (str): 입력 종목코드 (0000: 전체)
        - "0001" = KOSPI
        - "0002" = KOSDAQ

    Red 상태 (사이클 97): 신규 dict 부재 → ImportError → FAIL.

    Green (backend-dev): scanner.py 에 신규 dict 도입.
        `_FLUCTUATION_MARKET_INPUT_ISCD = {"kospi": "0001", "kosdaq": "0002"}`
    """
    try:
        from src.engine.scanner import _FLUCTUATION_MARKET_INPUT_ISCD
    except ImportError:
        pytest.fail(
            "\n사이클 97 H-1.c Red 상태 — `_FLUCTUATION_MARKET_INPUT_ISCD` dict 부재.\n"
            "  Green (backend-dev): scanner.py 에 신규 dict 도입 의무.\n"
            "    `_FLUCTUATION_MARKET_INPUT_ISCD: dict[str, str] = {'kospi': '0001', 'kosdaq': '0002'}`"
        )

    expected = {"kospi": "0001", "kosdaq": "0002"}
    assert _FLUCTUATION_MARKET_INPUT_ISCD == expected, (
        f"\n사이클 97 H-1.c 위반 — `_FLUCTUATION_MARKET_INPUT_ISCD` 영역 불일치:\n"
        f"  기대: {expected}\n"
        f"  실제: {_FLUCTUATION_MARKET_INPUT_ISCD}\n"
        f"  KIS 정본: 0001 = KOSPI, 0002 = KOSDAQ"
    )
