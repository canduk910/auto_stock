"""사이클 97 H-4 — 사이클 89/91/94/96 영역 (`_fetch_volume_rank` / `_VOLUME_RANK_*` / `_MARKET_INPUT_ISCD`) 전수 폐기 (HIGH).

명세 (`_workspace/red/cycle97_fluctuation_api_replacement.md`):

- 사이클 89/91/94/96 영역 전수 폐기 (volume_rank 단일 페이지 30 한도 + 페이징 미지원)
- 사이클 97 신규 영역 = `_fetch_fluctuation` + `_FLUCTUATION_URL` + `_FLUCTUATION_TR_ID`
- 폐기 영역:
  - `_VOLUME_RANK_URL` 상수
  - `_VOLUME_RANK_TR_ID` 상수
  - `_fetch_volume_rank` 함수
  - `_MARKET_INPUT_ISCD` dict (사이클 96 영역 — `_FLUCTUATION_MARKET_INPUT_ISCD` 로 영역 전환)

기대 동작 (Green, backend-dev 인계):
- 모듈 attribute 부재 검증 (hasattr False)
- 사이클 89/91/94/96 회귀 silent 결함 영구 차단

Red 상태 (사이클 97): production 코드 영속 → 4 가드 모두 FAIL.

영속 의무:
- 사이클 66 K-2 의미 전환 패턴 답습 (폐기 가드 → 미래 회귀 영구 차단)
- 사이클 89/91/94/96 영역 silent 결함 영구 차단
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit


def test_h4_volume_rank_url_deprecated():
    """H-4.a: `_VOLUME_RANK_URL` 상수 영역 영구 폐기.

    사이클 89/91/94/96 영역 silent 결함 영구 차단 (모듈 attribute 부재 의무).

    Red 상태 (사이클 97): production 코드 영속 → FAIL.
    Green (backend-dev): `_VOLUME_RANK_URL` 상수 삭제 → PASS.
    """
    import src.engine.scanner as scanner_mod

    assert not hasattr(scanner_mod, "_VOLUME_RANK_URL"), (
        "\n사이클 97 H-4.a 위반 — `_VOLUME_RANK_URL` 상수 영속:\n"
        "  사이클 89/91/94/96 영역 전수 폐기 의무\n"
        "  현재 값: " + repr(getattr(scanner_mod, "_VOLUME_RANK_URL", None)) + "\n"
        "  Green (backend-dev): scanner.py 에서 상수 삭제 의무\n"
        "  사이클 97 시정 = `_FLUCTUATION_URL` 로 영역 전환"
    )


def test_h4_volume_rank_tr_id_deprecated():
    """H-4.b: `_VOLUME_RANK_TR_ID` 상수 영역 영구 폐기.

    KIS TR_ID = FHPST01710000 (volume_rank) → 폐기.
    KIS 신규 TR_ID = FHPST01700000 (fluctuation) → 영속.

    Red 상태 (사이클 97): production 코드 영속 → FAIL.
    """
    import src.engine.scanner as scanner_mod

    assert not hasattr(scanner_mod, "_VOLUME_RANK_TR_ID"), (
        "\n사이클 97 H-4.b 위반 — `_VOLUME_RANK_TR_ID` 상수 영속:\n"
        "  사이클 89 영역 silent 결함 영구 차단 의무\n"
        "  현재 값: " + repr(getattr(scanner_mod, "_VOLUME_RANK_TR_ID", None)) + "\n"
        "  사이클 97 시정 = `_FLUCTUATION_TR_ID` (FHPST01700000) 로 영역 전환"
    )


def test_h4_fetch_volume_rank_function_deprecated():
    """H-4.c: `_fetch_volume_rank` 함수 영역 영구 폐기.

    Red 상태 (사이클 97): production 코드 영속 → FAIL.
    Green (backend-dev): 함수 삭제 → PASS.
    """
    import src.engine.scanner as scanner_mod

    assert not hasattr(scanner_mod, "_fetch_volume_rank"), (
        "\n사이클 97 H-4.c 위반 — `_fetch_volume_rank` 함수 영속:\n"
        "  사이클 89/91/96 영역 silent 결함 영구 차단 의무\n"
        "  사이클 97 시정 = `_fetch_fluctuation` 로 영역 전환\n"
        "  Green (backend-dev): scanner.py 에서 함수 삭제 의무"
    )


def test_h4_market_input_iscd_deprecated():
    """H-4.d: `_MARKET_INPUT_ISCD` dict 영역 영구 폐기.

    사이클 96 영역 dict → 사이클 97 `_FLUCTUATION_MARKET_INPUT_ISCD` 로 영역 전환
    (단순 이름 변경 아닌 영역 분리 — KIS API 영역 차별 명확화).

    Red 상태 (사이클 97): production 코드 영속 → FAIL.
    Green (backend-dev): `_MARKET_INPUT_ISCD` 삭제 + `_FLUCTUATION_MARKET_INPUT_ISCD` 신규 → PASS.
    """
    import src.engine.scanner as scanner_mod

    assert not hasattr(scanner_mod, "_MARKET_INPUT_ISCD"), (
        "\n사이클 97 H-4.d 위반 — `_MARKET_INPUT_ISCD` dict 영속:\n"
        "  사이클 96 영역 dict → 사이클 97 `_FLUCTUATION_MARKET_INPUT_ISCD` 영역 전환 의무\n"
        "  현재 값: " + repr(getattr(scanner_mod, "_MARKET_INPUT_ISCD", None)) + "\n"
        "  Green (backend-dev): scanner.py 에서 dict 삭제 의무"
    )
