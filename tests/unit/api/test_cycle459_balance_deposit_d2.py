"""cycle459 — 잔고 요약에 D+1·D+2 예수금 싣기 (사용자 결정 2026-10-15).

KIS 주식잔고조회(TTTC8434R) output2 의 `nxdy_excc_amt`(익일정산금액 = D+1 예수금)·
`prvs_rcdl_excc_amt`(가수도정산금액 = D+2 예수금)를 같은 응답에서 읽는다(추가 KIS 호출 0).
칸이 없거나 숫자가 아니면 `None` — 0 으로 채우지 않는다(「모름」 ≠ 「0원」).

고정 데이터 = `docs/kis/domestic-stock-order.md` 주식잔고조회 응답 예시 모양(문자열 숫자).
"""

from __future__ import annotations

import pytest

from src.api import balance as balance_mod


def _kis_response(output2: list[dict]) -> dict:
    return {
        "rt_cd": "0",
        "msg_cd": "KIOK0510",
        "msg1": "조회가 완료되었습니다",
        "ctx_area_fk100": "",
        "ctx_area_nk100": "",
        "output1": [
            {
                "pdno": "005930", "prdt_name": "삼성전자",
                "hldg_qty": "10", "ord_psbl_qty": "10",
                "pchs_avg_pric": "70000.0000", "pchs_amt": "700000",
                "prpr": "72000", "evlu_amt": "720000",
                "evlu_pfls_amt": "20000", "evlu_pfls_rt": "2.86",
            }
        ],
        "output2": output2,
    }


_OUTPUT2_REAL_SHAPE = {
    "dnca_tot_amt": "346455",
    "nxdy_excc_amt": "296455",
    "prvs_rcdl_excc_amt": "1046455",
    "cma_evlu_amt": "0",
    "bfdy_buy_amt": "0",
    "thdt_buy_amt": "50000",
    "nxdy_auto_rdpt_amt": "0",
    "bfdy_sll_amt": "750000",
    "thdt_sll_amt": "0",
    "d2_auto_rdpt_amt": "0",
    "bfdy_tlex_amt": "0",
    "thdt_tlex_amt": "0",
    "tot_loan_amt": "0",
    "scts_evlu_amt": "720000",
    "tot_evlu_amt": "1766455",
    "nass_amt": "1766455",
    "fncg_gld_auto_rdpt_yn": "",
    "pchs_amt_smtl_amt": "700000",
    "evlu_amt_smtl_amt": "720000",
    "evlu_pfls_smtl_amt": "20000",
    "tot_stln_slng_chgs": "0",
    "bfdy_tot_asst_evlu_amt": "1746455",
    "asst_icdc_amt": "20000",
    "asst_icdc_erng_rt": "1.14517700",
}


def _patch_kis(monkeypatch, response: dict):
    async def _fake_kis_get(url, tr_id, params, *args, **kwargs):
        return response

    monkeypatch.setattr(balance_mod, "kis_get", _fake_kis_get)


@pytest.mark.asyncio
async def test_summary_carries_d1_d2_deposit_from_same_response(monkeypatch):
    _patch_kis(monkeypatch, _kis_response([dict(_OUTPUT2_REAL_SHAPE)]))
    _, summary = await balance_mod.get_balance()
    assert summary.deposit == 346_455
    assert summary.deposit_d1 == 296_455
    assert summary.deposit_d2 == 1_046_455
    assert isinstance(summary.deposit_d2, int)


@pytest.mark.asyncio
async def test_missing_fields_are_none_not_zero(monkeypatch):
    row = dict(_OUTPUT2_REAL_SHAPE)
    del row["nxdy_excc_amt"]
    del row["prvs_rcdl_excc_amt"]
    _patch_kis(monkeypatch, _kis_response([row]))
    _, summary = await balance_mod.get_balance()
    assert summary.deposit_d1 is None
    assert summary.deposit_d2 is None


@pytest.mark.asyncio
@pytest.mark.parametrize("bad", ["", "   ", "abc", None])
async def test_non_numeric_fields_are_none(monkeypatch, bad):
    row = dict(_OUTPUT2_REAL_SHAPE)
    row["nxdy_excc_amt"] = bad
    row["prvs_rcdl_excc_amt"] = bad
    _patch_kis(monkeypatch, _kis_response([row]))
    _, summary = await balance_mod.get_balance()
    assert summary.deposit_d1 is None
    assert summary.deposit_d2 is None


@pytest.mark.asyncio
async def test_decimal_string_and_negative_parse(monkeypatch):
    """KIS 가 소수점 붙은 문자열·음수(미수)를 줘도 정수 원으로 읽는다."""
    row = dict(_OUTPUT2_REAL_SHAPE)
    row["nxdy_excc_amt"] = "-12345"
    row["prvs_rcdl_excc_amt"] = "500000.00000000"
    _patch_kis(monkeypatch, _kis_response([row]))
    _, summary = await balance_mod.get_balance()
    assert summary.deposit_d1 == -12_345
    assert summary.deposit_d2 == 500_000


@pytest.mark.asyncio
async def test_empty_output2_gives_none(monkeypatch):
    _patch_kis(monkeypatch, _kis_response([]))
    _, summary = await balance_mod.get_balance()
    assert summary.deposit == 0
    assert summary.deposit_d1 is None
    assert summary.deposit_d2 is None


def test_summary_model_defaults_keep_old_constructors_working():
    from src.models.balance import AccountSummary

    s = AccountSummary(
        deposit=1, stock_eval_amount=0, total_eval_amount=0, net_asset=0,
        purchase_total=0, eval_total=0, profit_loss_total=0,
    )
    assert s.deposit_d1 is None and s.deposit_d2 is None
    dumped = s.model_dump()
    assert "deposit_d1" in dumped and "deposit_d2" in dumped
