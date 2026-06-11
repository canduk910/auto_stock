"""사이클 98 G-INT1 — `_fetch_fluctuation` 통합 mock 시나리오 (MEDIUM).

명세 (`_workspace/red/cycle98_fid_rank_sort_cls_code_fix.md`):

- 사이클 97 영역 통합 테스트 0건 (mock 한정 = TDD PASS / 운영 실증 = KIS 거부)
- 사이클 98 영역 신규 통합 mock 시나리오 영역 영구 보강
- 정상 응답 영역 + OPSQ2002 거부 영역 graceful 양쪽 검증

검증 매트릭스 (2 시나리오):

1. **정상 응답 시나리오** (G-INT1-A):
   - KIS API 응답 영역 = `{rt_cd: "0", output: [...]}` (≥1건)
   - `_fetch_fluctuation` 호출 → `len(result) >= 1` 영속
   - KIS 정본 영역 정합 (`FID_RANK_SORT_CLS_CODE == "0"` 1자리)

2. **OPSQ2002 거부 시나리오** (G-INT1-B):
   - KIS API 응답 영역 = `KisApiError("OPSQ2002 INVALID INPUT_FILED_SIZE [FID_RANK_SORT_CLS_CODE] [4]")`
   - `_fetch_fluctuation` 호출 → graceful 누적분 반환 (예외 미전파)
   - 사이클 17/29 LMS chain 차단 영속

Red 상태 (사이클 98): 통합 테스트 0건 신규 → FAIL (G-INT1-A: production 거짓 영역 PASS 가능, G-INT1-B: graceful 영역 정합 검증).

영속 의무:
- 사이클 38 명문화 영속 (매수 진입 전용 영역)
- 사이클 97 영역 graceful (KisApiError + Exception 양쪽 except 분기) 영속
- KIS 거부 응답 영역 영속 (`[kis_rejection_quote]` ERROR 영구 기록)
- silent 결함 영구 차단 20 회 누적
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

pytestmark = pytest.mark.integration


@pytest.mark.xfail(
    strict=False,
    reason=(
        "사이클 101 Q68=A — `_fetch_fluctuation` 함수 자체 영구 폐기 "
        "(fluctuation API → market_cap FHPST01740000 전환). "
        "사이클 98 시점 통합 mock 시나리오 검증 의도 영속 보존 (사이클 66 K-2 패턴 답습)."
    ),
)
@pytest.mark.asyncio
async def test_g_int1_a_normal_response_with_kis_official_params():
    """G-INT1-A: 정상 응답 시나리오 — KIS API 영역 정합 + result ≥1건 영속.

    검증 매트릭스:
    - KIS API mock 영역 = output ≥3건 (정상 응답 영역)
    - `_fetch_fluctuation(market="kospi", top_n=10)` 호출
    - 결과 영역 = output 그대로 반환 (≥3건)
    - 첫 호출 params 영역 = KIS 정본 정합:
      * `FID_COND_MRKT_DIV_CODE == "J"`
      * `FID_COND_SCR_DIV_CODE == "20170"`
      * `FID_INPUT_ISCD == "0001"` (KOSPI)
      * `FID_RANK_SORT_CLS_CODE == "0"` (1자리, KIS 정본)
      * `FID_INPUT_CNT_1 == "10"` (top_n)

    Red 상태 (사이클 98): production 영역 `"0000"` 영속 → `FID_RANK_SORT_CLS_CODE` 검증 FAIL.

    Green (backend-dev): 1줄 시정 후 → PASS.
    """
    from src.engine.scanner import _fetch_fluctuation

    captured_params: list[dict] = []

    mock_output = [
        {"stck_shrn_iscd": "005930", "stck_prpr": "70000", "prdy_ctrt": "5.0"},
        {"stck_shrn_iscd": "000660", "stck_prpr": "120000", "prdy_ctrt": "4.5"},
        {"stck_shrn_iscd": "035720", "stck_prpr": "50000", "prdy_ctrt": "3.2"},
    ]

    async def _fake_kis_get_quote(*args, **kwargs):
        captured_params.append(kwargs.get("params", {}))
        return {
            "rt_cd": "0",
            "output": mock_output,
            "_response_headers": {"tr_cont": ""},  # 마지막 페이지
        }

    with patch("src.api.base.kis_get_quote",
               new=AsyncMock(side_effect=_fake_kis_get_quote)):
        result = await _fetch_fluctuation(market="kospi", top_n=10)

    # (1) 결과 영역 검증
    assert len(result) == 3, (
        f"\n사이클 98 G-INT1-A 위반 — 결과 영역 결함:\n"
        f"  기대: ≥3건 (mock output 영역)\n"
        f"  실제: {len(result)}건\n"
        f"  KIS API 정상 응답 영역 graceful 누적분 영속 의무"
    )

    # (2) KIS 정본 영역 정합 검증 (5 키 전수)
    assert captured_params, (
        "\n사이클 98 G-INT1-A 위반 — `kis_get_quote` 호출 영역 부재"
    )

    first_params = captured_params[0]

    expected_kis_official = {
        "FID_COND_MRKT_DIV_CODE": "J",          # KRX
        "FID_COND_SCR_DIV_CODE": "20170",       # 등락률 (KIS ValueError 영속)
        "FID_INPUT_ISCD": "0001",               # KOSPI
        "FID_RANK_SORT_CLS_CODE": "0",          # 1자리, KIS 정본 정합 (사이클 98 시정)
        "FID_INPUT_CNT_1": "10",                # top_n 사용자 제어 영역
    }

    for key, expected_value in expected_kis_official.items():
        actual_value = first_params.get(key)
        assert actual_value == expected_value, (
            f"\n사이클 98 G-INT1-A 위반 — KIS 정본 영역 정합 결함 ({key}):\n"
            f"  기대: {expected_value!r}\n"
            f"  실제: {actual_value!r}\n"
            f"  KIS 정본 영역: chk_fluctuation.py main 호출 영역\n"
            f"  결함 영역: src/engine/scanner.py L1529 (FID_RANK_SORT_CLS_CODE 1줄 시정 의무)"
        )


@pytest.mark.xfail(
    strict=False,
    reason=(
        "사이클 101 Q68=A — `_fetch_fluctuation` 함수 자체 영구 폐기 "
        "(fluctuation API → market_cap FHPST01740000 전환). "
        "사이클 98 시점 OPSQ2002 graceful 검증 의도 영속 보존 (사이클 66 K-2 패턴 답습)."
    ),
)
@pytest.mark.asyncio
async def test_g_int1_b_opsq2002_rejection_graceful():
    """G-INT1-B: OPSQ2002 거부 시나리오 영역 graceful 영속 검증.

    운영 실증 (Supabase MCP, 2026-06-10 16:36 KST 사이클 97 push 직후):
        OPSQ2002: ERROR INVALID INPUT_FILED_SIZE [FID_RANK_SORT_CLS_CODE] [4]

    검증 매트릭스:
    - KIS API mock 영역 = `KisApiError("OPSQ2002 ...")` raise
    - `_fetch_fluctuation` 호출 → graceful 누적분 반환 (예외 미전파)
    - 결과 영역 = [] (누적분 0건, 사이클 97 영역 graceful 영속)
    - 사이클 17/29 KIS LMS chain 차단 영속 (graceful 흡수 후 break)

    Red 상태 (사이클 98 Red): graceful 영역 정합 검증 — 사이클 97 영역 except 분기 영속
    (production 영역 graceful 영속 영역 = PASS 영역 영속 의무).

    Green (backend-dev): 1줄 시정 후 OPSQ2002 영구 차단 = mock 시나리오 = 미래 회귀 가드.

    영속 의무:
    - graceful 누적분 반환 영속 (KisApiError + Exception 양쪽 except 분기)
    - 매매 hot path 영향 0 (universe 0 ticker 영구 영역 = 매수 진입 차단)
    - 사이클 38 명문화 영속 (scanner 단계 = 매수 진입 전용)
    """
    from src.engine.scanner import _fetch_fluctuation
    from src.api.base import KisApiError

    call_count = {"n": 0}

    async def _fake_kis_get_quote(*args, **kwargs):
        call_count["n"] += 1
        # 사이클 97 영역 운영 실증 거부 영역 시뮬레이션
        raise KisApiError(
            "OPSQ2002 ERROR INVALID INPUT_FILED_SIZE [FID_RANK_SORT_CLS_CODE] [4]"
        )

    with patch("src.api.base.kis_get_quote",
               new=AsyncMock(side_effect=_fake_kis_get_quote)):
        # graceful 영역 영속 = 예외 미전파
        result = await _fetch_fluctuation(market="kospi", top_n=250)

    # (1) graceful 영역 결과 = 빈 리스트 (누적분 0건)
    assert result == [], (
        f"\n사이클 98 G-INT1-B 위반 — graceful 영역 결함:\n"
        f"  기대: [] (KisApiError 영역 graceful 누적분 0건 반환)\n"
        f"  실제: {result!r}\n"
        f"  사이클 97 영역 except 분기 영속 의무 (KisApiError + Exception 양쪽)"
    )

    # (2) 첫 호출 즉시 break (graceful 영역 영속) = 호출 횟수 정확 1회
    assert call_count["n"] == 1, (
        f"\n사이클 98 G-INT1-B 위반 — graceful 영역 break 결함:\n"
        f"  기대: 1회 (첫 거부 즉시 break, 사이클 17/29 LMS chain 차단)\n"
        f"  실제: {call_count['n']}회 (재시도 영역 결함 = KIS LMS 위험)"
    )
