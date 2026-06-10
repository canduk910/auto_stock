"""사이클 97 H-3 — `FID_INPUT_CNT_1` 파라미터 사용자 제어 영역 검증 (HIGH).

명세 (`_workspace/red/cycle97_fluctuation_api_replacement.md`):

- KIS fluctuation API 의 결정적 영역 = `fid_input_cnt_1` (조회할 종목 수)
- volume_rank (단일 페이지 30 한도) 와 영역 차별
- 사이클 97 = top_n=250 → `FID_INPUT_CNT_1 = "250"` 영역 정합

기대 동작 (Green, backend-dev 인계):
- `_fetch_fluctuation(top_n=250)` 호출 → KIS 요청 파라미터 `FID_INPUT_CNT_1 = "250"`
- `_fetch_fluctuation(top_n=100)` 호출 → KIS 요청 파라미터 `FID_INPUT_CNT_1 = "100"`
- 사용자 영구 제어 영역 (KIS 정본 영구 정합)

Red 상태 (사이클 97): `_fetch_fluctuation` 신규 함수 미존재 → ImportError → FAIL.

영속 의무:
- KIS 정본 fluctuation docstring: "입력 수1 (조회할 종목 수)" 영구 정합
- 사이클 89 단일 페이지 30 한도 영역 폐기 (volume_rank silent 결함)
- 매매 안전성 영향 0
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_h3_fid_input_cnt_1_passes_top_n():
    """H-3.a: `_fetch_fluctuation(top_n=250)` → KIS 요청 `FID_INPUT_CNT_1 == "250"`.

    검증 매트릭스:
    - kis_get_quote mock 으로 params 수집
    - 첫 호출 params["FID_INPUT_CNT_1"] = "250" (str 영역)
    - 사용자 영구 제어 영역 확정

    Red 상태 (사이클 97): `_fetch_fluctuation` 함수 미존재 → FAIL.

    Green (backend-dev): `FID_INPUT_CNT_1 = str(top_n)` 영역 영속 의무.
    """
    try:
        from src.engine.scanner import _fetch_fluctuation
    except ImportError:
        pytest.fail(
            "\n사이클 97 H-3.a Red 상태 — `_fetch_fluctuation` 함수 부재"
        )

    captured_params: list[dict] = []

    async def _fake_kis_get_quote(*args, **kwargs):
        captured_params.append(kwargs.get("params", {}))
        return {"rt_cd": "0", "output": [], "_response_headers": {"tr_cont": ""}}

    with patch("src.api.base.kis_get_quote",
               new=AsyncMock(side_effect=_fake_kis_get_quote)):
        # 사이클 99 — top_n=30 영구 영속 (KIS API 단일 페이지 한도, 페이징 미지원 영구 확정)
        await _fetch_fluctuation(market="kospi", top_n=30)

    assert captured_params, (
        "\n사이클 97 H-3.a 위반 — `_fetch_fluctuation` 가 `kis_get_quote` 호출 없음"
    )

    first_params = captured_params[0]
    # 사이클 99 — top_n=30 영구 영속 (사이클 97 top_n=250 영역 갱신)
    assert first_params.get("FID_INPUT_CNT_1") == "30", (
        f"\n사이클 97 H-3.a (사이클 99 갱신) 위반 — `FID_INPUT_CNT_1` 사용자 제어 영역 결함:\n"
        f"  기대: '30' (str 영역, top_n=30 사이클 99 영구 영속)\n"
        f"  실제: {first_params.get('FID_INPUT_CNT_1')!r}\n"
        f"  KIS 정본: 'fid_input_cnt_1 (str): 입력 수1 (조회할 종목 수)'\n"
        f"  사이클 99 — KIS API 단일 페이지 한도 30 영구 영속"
    )


@pytest.mark.asyncio
async def test_h3_fid_input_cnt_1_user_controlled_value():
    """H-3.b: `_fetch_fluctuation(top_n=N)` → KIS 요청 `FID_INPUT_CNT_1 == str(N)` (사용자 제어).

    검증 매트릭스:
    - top_n=100 호출 → params["FID_INPUT_CNT_1"] = "100"
    - top_n=500 호출 → params["FID_INPUT_CNT_1"] = "500"
    - 사용자 영구 제어 영역 (volume_rank 30 한도 영역과 차별)

    Red 상태 (사이클 97): 함수 미존재 → FAIL.

    Green (backend-dev): top_n 인자 → str 변환 → FID_INPUT_CNT_1 전달.
    """
    try:
        from src.engine.scanner import _fetch_fluctuation
    except ImportError:
        pytest.fail(
            "\n사이클 97 H-3.b Red 상태 — `_fetch_fluctuation` 함수 부재"
        )

    captured_params_100: list[dict] = []
    captured_params_500: list[dict] = []

    async def _fake_kis_get_quote_100(*args, **kwargs):
        captured_params_100.append(kwargs.get("params", {}))
        return {"rt_cd": "0", "output": [], "_response_headers": {"tr_cont": ""}}

    async def _fake_kis_get_quote_500(*args, **kwargs):
        captured_params_500.append(kwargs.get("params", {}))
        return {"rt_cd": "0", "output": [], "_response_headers": {"tr_cont": ""}}

    # 사이클 99 — top_n=30 영구 영속 (KIS API 단일 페이지 한도)
    # top_n=100/500 영역 → 30 영구 영속으로 갱신 (사이클 91 페이징 영역 폐기)
    with patch("src.api.base.kis_get_quote",
               new=AsyncMock(side_effect=_fake_kis_get_quote_100)):
        await _fetch_fluctuation(market="kospi", top_n=30)

    with patch("src.api.base.kis_get_quote",
               new=AsyncMock(side_effect=_fake_kis_get_quote_500)):
        await _fetch_fluctuation(market="kospi", top_n=30)

    # 사이클 99 — FID_INPUT_CNT_1 = "30" 영구 영속 (사이클 97 top_n=100/500 영역 갱신)
    assert captured_params_100 and captured_params_100[0].get("FID_INPUT_CNT_1") == "30", (
        f"\n사이클 97 H-3.b (사이클 99 갱신) 위반 — top_n=30 → FID_INPUT_CNT_1 결함:\n"
        f"  기대: '30' (사이클 99 영구 영속)\n"
        f"  실제: {captured_params_100[0].get('FID_INPUT_CNT_1') if captured_params_100 else 'NO_CALL'!r}"
    )

    assert captured_params_500 and captured_params_500[0].get("FID_INPUT_CNT_1") == "30", (
        f"\n사이클 97 H-3.b (사이클 99 갱신) 위반 — top_n=30 → FID_INPUT_CNT_1 결함:\n"
        f"  기대: '30' (사이클 99 영구 영속)\n"
        f"  실제: {captured_params_500[0].get('FID_INPUT_CNT_1') if captured_params_500 else 'NO_CALL'!r}"
    )


@pytest.mark.asyncio
async def test_h3_fid_cond_scr_div_code_strict_20170():
    """H-3.c: `FID_COND_SCR_DIV_CODE = "20170"` KIS 정본 강제 검증 영역 영속.

    KIS 정본 fluctuation.py:
        if fid_cond_scr_div_code != "20170":
            raise ValueError("조건 화면 분류 코드 확인요망!!!")

    Red 상태 (사이클 97): 함수 미존재 → FAIL.

    Green (backend-dev): params["FID_COND_SCR_DIV_CODE"] = "20170" 영구 영속.
    """
    try:
        from src.engine.scanner import _fetch_fluctuation
    except ImportError:
        pytest.fail(
            "\n사이클 97 H-3.c Red 상태 — `_fetch_fluctuation` 함수 부재"
        )

    captured_params: list[dict] = []

    async def _fake_kis_get_quote(*args, **kwargs):
        captured_params.append(kwargs.get("params", {}))
        return {"rt_cd": "0", "output": [], "_response_headers": {"tr_cont": ""}}

    with patch("src.api.base.kis_get_quote",
               new=AsyncMock(side_effect=_fake_kis_get_quote)):
        # 사이클 99 — top_n=30 영구 영속
        await _fetch_fluctuation(market="kospi", top_n=30)

    assert captured_params, (
        "\n사이클 97 H-3.c 위반 — kis_get_quote 호출 없음"
    )

    first = captured_params[0]
    assert first.get("FID_COND_SCR_DIV_CODE") == "20170", (
        f"\n사이클 97 H-3.c 위반 — KIS 정본 강제 검증 영역 위반:\n"
        f"  기대: '20170'\n"
        f"  실제: {first.get('FID_COND_SCR_DIV_CODE')!r}\n"
        f"  KIS 정본: fluctuation.py `if fid_cond_scr_div_code != \"20170\": raise ValueError(...)`"
    )

    assert first.get("FID_COND_MRKT_DIV_CODE") == "J", (
        f"\n사이클 97 H-3.c 위반 — `FID_COND_MRKT_DIV_CODE` 영역 위반:\n"
        f"  기대: 'J' (KRX 메인)\n"
        f"  실제: {first.get('FID_COND_MRKT_DIV_CODE')!r}"
    )


# ----------------------------------------------------------------------------
# 사이클 98 G-REG1 — 사이클 97 영역 회귀 가드 갱신 (LOW)
#
# 명세 (`_workspace/red/cycle98_fid_rank_sort_cls_code_fix.md`):
# - 사이클 97 영역 회귀 가드 영역 한계 = `FID_RANK_SORT_CLS_CODE` 검증 0건
# - KIS 정본 영역 (chk_fluctuation.py main) = `fid_rank_sort_cls_code="0"` (1자리)
# - 사이클 98 영역 = 사이클 97 영역 1줄 시정 + 회귀 가드 갱신 영역 영속
# ----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cycle98_g_reg1_fid_rank_sort_cls_code_one_digit_persistence():
    """G-REG1: 사이클 97 영역 회귀 가드 갱신 — `FID_RANK_SORT_CLS_CODE == "0"` 영속 검증.

    KIS chk_fluctuation.py main 호출 영역 정본:
        fid_rank_sort_cls_code="0"      # ← 1자리 ✓ (KIS 정본)

    사이클 97 영역 H-3.c 검증 영역 = `FID_COND_SCR_DIV_CODE` + `FID_COND_MRKT_DIV_CODE` 한정
    사이클 98 영역 추가 검증 = `FID_RANK_SORT_CLS_CODE == "0"` 영속 (1자리, KIS 정본 정합)

    Red 상태 (사이클 98): production 영역 `"0000"` (4자리) 영속 → FAIL.

    Green (backend-dev): `src/engine/scanner.py:1529` 1줄 시정
        `"FID_RANK_SORT_CLS_CODE": "0000"` → `"FID_RANK_SORT_CLS_CODE": "0"`
        → PASS.

    영속 의무:
    - 사이클 97 영역 영속 (사이클 98 = 사이클 97 영역 1줄 시정만)
    - KIS 정본 영역 영구 정합
    - silent 결함 영구 차단 20 회 누적
    """
    from src.engine.scanner import _fetch_fluctuation

    captured_params: list[dict] = []

    async def _fake_kis_get_quote(*args, **kwargs):
        captured_params.append(kwargs.get("params", {}))
        return {"rt_cd": "0", "output": [], "_response_headers": {"tr_cont": ""}}

    with patch("src.api.base.kis_get_quote",
               new=AsyncMock(side_effect=_fake_kis_get_quote)):
        # 사이클 99 — top_n=30 영구 영속 (사이클 98 top_n=250 영역 갱신)
        await _fetch_fluctuation(market="kospi", top_n=30)

    assert captured_params, (
        "\n사이클 98 G-REG1 위반 — `_fetch_fluctuation` 가 `kis_get_quote` 호출 없음"
    )

    first = captured_params[0]
    actual = first.get("FID_RANK_SORT_CLS_CODE")

    assert actual == "0", (
        f"\n사이클 98 G-REG1 위반 — `FID_RANK_SORT_CLS_CODE` 1자리 영속 결함:\n"
        f"  기대: '0' (1자리, KIS chk_fluctuation.py main 정본 영속)\n"
        f"  실제: {actual!r}\n"
        f"  KIS 정본: chk_fluctuation.py main 영역 `fid_rank_sort_cls_code=\"0\"`\n"
        f"  운영 실증: OPSQ2002 INVALID INPUT_FILED_SIZE [FID_RANK_SORT_CLS_CODE] [4]\n"
        f"  시정 영역: src/engine/scanner.py:1529 → `\"FID_RANK_SORT_CLS_CODE\": \"0\"`"
    )
