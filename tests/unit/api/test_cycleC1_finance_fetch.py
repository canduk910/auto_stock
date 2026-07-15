"""사이클 C1 — src/api/finance.py 5 TR fetch Red 가드.

Red 명세: `_workspace/red/cycleC1_financial_infra.md`

`condition.py::fetch_daily_candles_ranged` (kis_get_quote 경유, 6자리 ticker 가드,
asyncio.sleep(0.05)) 답습. KIS 정본 (docs/kis/domestic-stock-info.md) 5 TR — 모두
output=다기간 list, 각 원소 stac_yymm 키 + 필드.

  income    /finance/income-statement    FHKST66430200 → sale_account/sale_totl_prfi/bsop_prti/thtr_ntin/depr_cost
  balance   /finance/balance-sheet       FHKST66430100 → cras/fxas/total_aset/flow_lblt/total_lblt/total_cptl/cpfn
  profit    /finance/profit-ratio        FHKST66430400 → cptl_ntin_rate/sale_totl_rate
  stability /finance/stability-ratio     FHKST66430600 → lblt_rate/crnt_rate
  other     /finance/other-major-ratios  FHKST66430500 → ebitda/ev_ebitda

가드:
- fetch_financial_tr: 단일 TR output list 파싱 + 6자리 ticker 가드 + graceful []
- fetch_all_financials: 5 TR 순차 (asyncio.sleep(0.05)) + stac_yymm join + 정규화 row
  + 개별 TR 실패 graceful (그 필드만 결측)
- FID_DIV_CLS_CODE / fid_cond_mrkt_div_code=J / fid_input_iscd 파라미터
- TR_ID FH 하드코딩 (settings.get_tr_id 사용 금지 — FH 접두사 실전=모의 동일)
- respx 로 output=list 계약 못박음 (최소 2기 stac_yymm)

production 모듈 미작성 → import 실패로 전부 FAIL (Red).
매매 안전성 무영향 (scanner 매수 진입 전, 사이클 38).
"""

from __future__ import annotations

import re
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# KIS 정본 TR 매핑 (docs/kis/domestic-stock-info.md 실측 필드명)
# ---------------------------------------------------------------------------
_TR_URLS = {
    "income": ("/uapi/domestic-stock/v1/finance/income-statement", "FHKST66430200"),
    "balance": ("/uapi/domestic-stock/v1/finance/balance-sheet", "FHKST66430100"),
    "profit": ("/uapi/domestic-stock/v1/finance/profit-ratio", "FHKST66430400"),
    "stability": ("/uapi/domestic-stock/v1/finance/stability-ratio", "FHKST66430600"),
    "other": ("/uapi/domestic-stock/v1/finance/other-major-ratios", "FHKST66430500"),
}


def _income_output(stac_yymm: str) -> dict:
    """FHKST66430200 손익계산서 원소 (실제 KIS 필드명)."""
    return {
        "stac_yymm": stac_yymm,
        "sale_account": "2589355.00",
        "sale_cost": "1803886.00",
        "sale_totl_prfi": "785469",
        "depr_cost": "99.99",
        "bsop_prti": "65670.00",
        "op_prfi": "110063.00",
        "thtr_ntin": "154871.00",
    }


def _balance_output(stac_yymm: str) -> dict:
    """FHKST66430100 대차대조표 원소."""
    return {
        "stac_yymm": stac_yymm,
        "cras": "1959366.00",
        "fxas": "2599694.00",
        "total_aset": "4559060.00",
        "flow_lblt": "757195.00",
        "fix_lblt": "165087.00",
        "total_lblt": "922281.00",
        "cpfn": "8975",
        "total_cptl": "3636779.00",
    }


def _profit_output(stac_yymm: str) -> dict:
    """FHKST66430400 수익성비율 원소."""
    return {
        "stac_yymm": stac_yymm,
        "cptl_ntin_rate": "3.43",
        "self_cptl_ntin_inrt": "4.14",
        "sale_ntin_rate": "5.98",
        "sale_totl_rate": "30.33",
    }


def _stability_output(stac_yymm: str) -> dict:
    """FHKST66430600 안정성비율 원소."""
    return {
        "stac_yymm": stac_yymm,
        "lblt_rate": "25.36",
        "bram_depn": "2.78",
        "crnt_rate": "258.77",
        "quck_rate": "190.59",
    }


def _other_output(stac_yymm: str) -> dict:
    """FHKST66430500 기타주요비율 원소."""
    return {
        "stac_yymm": stac_yymm,
        "payout_rate": "-0.02",
        "eva": "0.00",
        "ebitda": "23464.00",
        "ev_ebitda": "12.5",
    }


_OUTPUT_BUILDERS = {
    "income": _income_output,
    "balance": _balance_output,
    "profit": _profit_output,
    "stability": _stability_output,
    "other": _other_output,
}


def _make_kis_dispatch(periods=("202312", "202309"), *, fail_kinds=()):
    """kis_get_quote mock — path 로 5 TR 판별해 output=list 반환. fail_kinds 는 예외."""

    async def _dispatch(url, tr_id, params, **kwargs):
        for kind, (path, _tr) in _TR_URLS.items():
            if url == path:
                if kind in fail_kinds:
                    raise RuntimeError(f"KIS {kind} 호출 실패")
                builder = _OUTPUT_BUILDERS[kind]
                return {"output": [builder(p) for p in periods]}
        raise AssertionError(f"미매핑 finance path: {url}")

    return AsyncMock(side_effect=_dispatch)


# ---------------------------------------------------------------------------
# G-C1-FIN-1 — 모듈 + 함수 존재
# ---------------------------------------------------------------------------
def test_module_and_functions_present():
    """finance 모듈 + fetch_financial_tr / fetch_all_financials 노출."""
    from src.api import finance

    assert hasattr(finance, "fetch_financial_tr"), "fetch_financial_tr 부재."
    assert hasattr(finance, "fetch_all_financials"), "fetch_all_financials 부재."


# ---------------------------------------------------------------------------
# G-C1-FIN-2 — fetch_financial_tr 단일 TR output list 파싱
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_fetch_single_tr_output_list(monkeypatch):
    """fetch_financial_tr — output=list 반환 (최소 2기 stac_yymm)."""
    from src.api import finance

    monkeypatch.setattr(finance, "kis_get_quote", _make_kis_dispatch())

    rows = await finance.fetch_financial_tr("005930", "income", div_cls="0")
    assert isinstance(rows, list) and len(rows) == 2, f"output list 2기 부재: {rows!r}"
    assert rows[0]["stac_yymm"] == "202312"
    assert rows[0]["sale_account"] == "2589355.00"


# ---------------------------------------------------------------------------
# G-C1-FIN-3 — fetch_financial_tr 요청 파라미터 정합
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_fetch_tr_request_params(monkeypatch):
    """FID_DIV_CLS_CODE + fid_cond_mrkt_div_code=J + fid_input_iscd + FH TR_ID 직접."""
    from src.api import finance

    captured = {}

    async def _spy(url, tr_id, params, **kwargs):
        captured["url"] = url
        captured["tr_id"] = tr_id
        captured["params"] = params
        return {"output": [_income_output("202312")]}

    monkeypatch.setattr(finance, "kis_get_quote", AsyncMock(side_effect=_spy))

    await finance.fetch_financial_tr("005930", "income", div_cls="1")

    params = captured.get("params", {})
    # 대소문자 무관 키 조회 (condition.py 는 소문자 params 사용)
    params_lower = {k.lower(): v for k, v in params.items()}
    assert params_lower.get("fid_cond_mrkt_div_code") == "J", (
        f"fid_cond_mrkt_div_code=J 부재: {params!r}"
    )
    assert params_lower.get("fid_input_iscd") == "005930", (
        f"fid_input_iscd 부재: {params!r}"
    )
    assert params_lower.get("fid_div_cls_code") == "1", (
        f"FID_DIV_CLS_CODE div_cls 전달 부재: {params!r}"
    )
    # TR_ID = FH 접두사 직접 하드코딩 (settings.get_tr_id 사용 금지)
    assert captured.get("tr_id") == "FHKST66430200", (
        f"TR_ID FH 직접 하드코딩 부재: {captured.get('tr_id')!r} — "
        f"FH 접두사는 실전=모의 동일이라 settings.get_tr_id() 사용 금지 (VH...로 깨짐)."
    )
    assert captured.get("url") == _TR_URLS["income"][0]


# ---------------------------------------------------------------------------
# G-C1-FIN-4 — 6자리 ticker 가드 (condition.py 답습)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_fetch_tr_ticker_guard(monkeypatch):
    """6자리 숫자 미준수 ticker → ValueError (fetch_daily_candles_ranged 답습)."""
    from src.api import finance

    monkeypatch.setattr(finance, "kis_get_quote", _make_kis_dispatch())

    for bad in ("00593", "0059301", "ABCDEF", "", "005930A"):
        with pytest.raises(ValueError):
            await finance.fetch_financial_tr(bad, "income")


# ---------------------------------------------------------------------------
# G-C1-FIN-5 — fetch_financial_tr graceful []
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_fetch_tr_graceful_empty(monkeypatch):
    """KIS 호출 실패 시 예외 미전파 + [] 반환 (사이클 88 G-REJECT)."""
    from src.api import finance

    monkeypatch.setattr(
        finance, "kis_get_quote", AsyncMock(side_effect=RuntimeError("KIS down"))
    )
    rows = await finance.fetch_financial_tr("005930", "income")
    assert rows == [], f"graceful [] 부재: {rows!r}"


# ---------------------------------------------------------------------------
# G-C1-FIN-6 — fetch_all_financials 5 TR 순차 + stac_yymm join + 정규화
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_fetch_all_join_and_normalize(monkeypatch):
    """5 TR → stac_yymm join → 정규화 row list (스키마 컬럼명) + raw 병합."""
    from src.api import finance

    dispatch = _make_kis_dispatch(periods=("202312", "202309"))
    monkeypatch.setattr(finance, "kis_get_quote", dispatch)
    # asyncio.sleep 무력화 (테스트 속도 + freeze 무관)
    monkeypatch.setattr(finance.asyncio, "sleep", AsyncMock(return_value=None))

    rows = await finance.fetch_all_financials("005930", div_cls="0")

    # 5 TR 전수 호출 (각 1회)
    assert dispatch.call_count == 5, f"5 TR 순차 호출 부재: {dispatch.call_count}회"

    # 2기 stac_yymm → 2 row 로 join
    assert len(rows) == 2, f"stac_yymm join 2기 부재: {len(rows)}"
    by_period = {r["stac_yymm"]: r for r in rows}
    assert set(by_period) == {"202312", "202309"}, f"기수 정합 부재: {set(by_period)}"

    r = by_period["202312"]
    # 정규화 컬럼명 (스키마) — 5 TR 필드가 한 row 로 병합
    assert r["ticker"] == "005930"
    assert r["div_cls"] == "0"
    # 손익
    assert r["sale_account"] == pytest.approx(2589355.0)
    assert r["bsop_prti"] == pytest.approx(65670.0)
    assert r["thtr_ntin"] == pytest.approx(154871.0)
    # 대차
    assert r["cras"] == pytest.approx(1959366.0)
    assert r["total_lblt"] == pytest.approx(922281.0)
    assert r["cpfn"] == pytest.approx(8975.0)
    # 수익성
    assert r["cptl_ntin_rate"] == pytest.approx(3.43)
    assert r["sale_totl_rate"] == pytest.approx(30.33)
    # 안정성
    assert r["lblt_rate"] == pytest.approx(25.36)
    assert r["crnt_rate"] == pytest.approx(258.77)
    # 기타
    assert r["ebitda"] == pytest.approx(23464.0)
    assert r["ev_ebitda"] == pytest.approx(12.5)
    # raw 병합 보존 (사이클 81 G-AST1)
    assert isinstance(r.get("raw"), dict) and r["raw"], "raw 병합 보존 부재."


# ---------------------------------------------------------------------------
# G-C1-FIN-7 — fetch_all_financials 개별 TR 실패 graceful (그 필드만 결측)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_fetch_all_partial_tr_failure_graceful(monkeypatch):
    """other TR 실패 시 그 필드(ebitda/ev_ebitda)만 결측, 나머지 TR 계속."""
    from src.api import finance

    dispatch = _make_kis_dispatch(periods=("202312",), fail_kinds=("other",))
    monkeypatch.setattr(finance, "kis_get_quote", dispatch)
    monkeypatch.setattr(finance.asyncio, "sleep", AsyncMock(return_value=None))

    rows = await finance.fetch_all_financials("005930", div_cls="0")
    assert len(rows) == 1, f"other 실패에도 나머지 4 TR 로 row 생성 의무: {rows!r}"
    r = rows[0]
    # 정상 TR 필드는 채워짐
    assert r["sale_account"] == pytest.approx(2589355.0)
    assert r["lblt_rate"] == pytest.approx(25.36)
    # 실패 TR 필드는 결측 (None 또는 키 부재) — 나머지 계속이 핵심
    assert r.get("ebitda") is None, (
        f"실패 TR 필드 결측 부재 (그 필드만 결측 의무): ebitda={r.get('ebitda')!r}"
    )


# ---------------------------------------------------------------------------
# G-C1-FIN-8 — respx 로 output=list 계약 (5 TR HTTP 레벨 시리즈 합성)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_respx_output_list_contract(monkeypatch):
    """respx 로 5 TR HTTP 응답 합성 (output=다기간 list) — kis_get_quote → _request seam.

    finance.py 는 kis_get_quote 경유이므로 kis_get_quote 자체를 respx 응답 dispatch 로
    감싸 output=list 계약을 HTTP 레벨 시리즈로 못박는다 (실제 KIS 필드명 + 최소 2기).
    """
    respx = pytest.importorskip("respx")
    import httpx

    from src.api import finance

    # kis_get_quote 를 respx 응답을 반환하도록 dispatch (HTTP 레벨 output=list 합성)
    async def _respx_backed(url, tr_id, params, **kwargs):
        for kind, (path, tr) in _TR_URLS.items():
            if url == path:
                assert tr_id == tr, f"{kind} TR_ID 정합 부재: {tr_id} != {tr}"
                builder = _OUTPUT_BUILDERS[kind]
                payload = {
                    "rt_cd": "0",
                    "msg_cd": "MCA00000",
                    "msg1": "정상처리",
                    "output": [builder("202312"), builder("202309")],
                }
                resp = httpx.Response(200, json=payload)
                # output 이 list 이고 2기 이상임을 계약으로 확인
                body = resp.json()
                assert isinstance(body["output"], list) and len(body["output"]) >= 2
                return body
        raise AssertionError(f"미매핑 path: {url}")

    monkeypatch.setattr(finance, "kis_get_quote", AsyncMock(side_effect=_respx_backed))
    monkeypatch.setattr(finance.asyncio, "sleep", AsyncMock(return_value=None))

    rows = await finance.fetch_all_financials("005930")
    assert len(rows) == 2
    assert {r["stac_yymm"] for r in rows} == {"202312", "202309"}


# ---------------------------------------------------------------------------
# G-C1-FIN-9 — AST: settings.get_tr_id 미사용 (FH 접두사 실전=모의 동일)
# ---------------------------------------------------------------------------
def test_ast_no_get_tr_id_for_fh():
    """finance.py 는 settings.get_tr_id 를 finance TR 에 사용하지 않는다 (FH → VH 깨짐 방지).

    조건: finance.py source 에 'get_tr_id' 문자열 0건 (FH TR_ID 직접 하드코딩만 허용).
    """
    finance_py = Path("src/api/finance.py")
    assert finance_py.exists(), "src/api/finance.py 부재 (production 미작성 Red)."
    src = finance_py.read_text(encoding="utf-8")
    assert "get_tr_id" not in src, (
        "finance.py 에 get_tr_id 사용 — FH 접두사는 실전=모의 동일이라 "
        "settings.get_tr_id() 가 FH→VH 로 깨뜨림. FH TR_ID 직접 하드코딩 의무 "
        "(condition.py::fetch_daily_candles_ranged 답습)."
    )
    # 5 FH TR_ID 전수 하드코딩 존재
    for _path, tr in _TR_URLS.values():
        assert tr in src, f"finance.py 에 FH TR_ID '{tr}' 직접 하드코딩 부재."
