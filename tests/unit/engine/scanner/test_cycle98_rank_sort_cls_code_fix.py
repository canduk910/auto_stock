"""사이클 98 G-FIX1 — `FID_RANK_SORT_CLS_CODE` 1줄 silent 결함 영구 시정 (HIGH).

명세 (`_workspace/red/cycle98_fid_rank_sort_cls_code_fix.md`):

- 사이클 97 backend-dev Green 단계 silent 결함:
  KIS fluctuation.py docstring 영역 `(0000: 등락률순)` 영역 거짓 안내 인용
- KIS 정본 영역 (chk_fluctuation.py main 호출):
  `fid_rank_sort_cls_code="0"` (1자리)
- 운영 실증 (Supabase MCP, 2026-06-10 16:36 KST 사이클 97 push 직후):
  `OPSQ2002: ERROR INVALID INPUT_FILED_SIZE [FID_RANK_SORT_CLS_CODE] [4]`
  → universe = 0 ticker 영구 영역

기대 동작 (Green, backend-dev 인계):
- `_fetch_fluctuation(market="kospi", top_n=250)` 호출
  → KIS 요청 params 영역 `FID_RANK_SORT_CLS_CODE == "0"` (1자리)
- KIS chk_fluctuation.py main 호출 영역 정본 영속

Red 상태 (사이클 98): production 영역 `"0000"` 영속 → FAIL.

KIS MCP 정본 인용 (chk_fluctuation.py main 영역):
    result = fluctuation(
        fid_cond_mrkt_div_code="J",
        fid_cond_scr_div_code="20170",
        fid_input_iscd="0000",
        fid_rank_sort_cls_code="0",      # ← 1자리 ✓ (KIS 정본)
        fid_input_cnt_1="0",
        ...
    )

영속 의무:
- 사이클 38 명문화 영속 (매수 진입 전용 영역)
- 사이클 81 `bfdy_clpr` 1줄 시정 패턴 답습
- 사이클 97 영역 fluctuation API 영속
- silent 결함 영구 차단 20 회 누적 (사이클 60/64/65#1/65#2/65#3/66/67/68/72/73/77/77#2/78/79/80/80#2/80#3/80#4/81/98)
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

pytestmark = pytest.mark.unit


@pytest.mark.xfail(
    strict=False,
    reason=(
        "사이클 101 Q68=A — `_fetch_fluctuation` 함수 자체 영구 폐기 "
        "(fluctuation API → market_cap FHPST01740000 전환). "
        "사이클 98 시점 FID_RANK_SORT_CLS_CODE 1자리 시정 검증 의도 영속 보존 (사이클 66 K-2 패턴 답습)."
    ),
)
@pytest.mark.asyncio
async def test_g_fix1_rank_sort_cls_code_one_digit_kis_official():
    """G-FIX1: `_fetch_fluctuation` 호출 시 `FID_RANK_SORT_CLS_CODE == "0"` (1자리, KIS 정본).

    KIS chk_fluctuation.py main 호출 영역 정본:
        fid_rank_sort_cls_code="0"      # ← 1자리

    검증 매트릭스:
    - kis_get_quote mock 으로 params 수집
    - 첫 호출 params["FID_RANK_SORT_CLS_CODE"] == "0" (1자리 영역, KIS 정본 정합)
    - 사이클 97 영역 `"0000"` (4자리, KIS docstring 거짓 안내 인용 결함) 영구 차단

    Red 상태 (사이클 98 Red): production 영역 `"0000"` → FAIL.

    Green (backend-dev): `src/engine/scanner.py:1529` 1줄 시정
        `"FID_RANK_SORT_CLS_CODE": "0000"` → `"FID_RANK_SORT_CLS_CODE": "0"`
        → PASS.

    운영 영속 의무:
    - OPSQ2002 영구 차단 (사이클 97 push 직후 16:36 KST 영구 발화)
    - universe = 0 ticker 영구 영역 해소 (다음 영업일 09:00 전 push 의무)
    - KIS LMS/앱키 정지 chain 차단 (KIS 거부 누적 회피)
    """
    from src.engine.scanner import _fetch_fluctuation

    captured_params: list[dict] = []

    async def _fake_kis_get_quote(*args, **kwargs):
        captured_params.append(kwargs.get("params", {}))
        return {"rt_cd": "0", "output": [], "_response_headers": {"tr_cont": ""}}

    with patch("src.api.base.kis_get_quote",
               new=AsyncMock(side_effect=_fake_kis_get_quote)):
        await _fetch_fluctuation(market="kospi", top_n=250)

    assert captured_params, (
        "\n사이클 98 G-FIX1 위반 — `_fetch_fluctuation` 가 `kis_get_quote` 호출 없음"
    )

    first_params = captured_params[0]
    actual = first_params.get("FID_RANK_SORT_CLS_CODE")

    assert actual == "0", (
        f"\n사이클 98 G-FIX1 위반 — `FID_RANK_SORT_CLS_CODE` 1자리 정본 영역 결함:\n"
        f"  기대: '0' (1자리, KIS chk_fluctuation.py main 호출 영역 정본 영속)\n"
        f"  실제: {actual!r} (사이클 97 영역 KIS docstring 거짓 안내 인용 결함)\n"
        f"  운영 실증: OPSQ2002 ERROR INVALID INPUT_FILED_SIZE [FID_RANK_SORT_CLS_CODE] [4]\n"
        f"  KIS 정본: chk_fluctuation.py main 영역 `fid_rank_sort_cls_code=\"0\"`\n"
        f"  시정 영역: src/engine/scanner.py:1529 → `\"FID_RANK_SORT_CLS_CODE\": \"0\"`\n"
        f"  영구 차단 의무: 다음 영업일 (2026-06-11) 09:00 전 push 의무 (universe=0 해소)"
    )
