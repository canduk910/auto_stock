"""사이클 C1 (2026-07-15) — KIS 재무 5 TR fetch (income/balance/profit/stability/other).

퀀트 재무필터 (마법공식 + F-Score-7) 데이터 계층. `src/api/condition.py::
fetch_daily_candles_ranged` 답습 (kis_get_quote 경유, 6자리 ticker 가드).

KIS 정본 5 TR (모두 output=다기간 list, 각 원소 stac_yymm 키):
    income    /finance/income-statement    FHKST66430200 → sale_account/sale_totl_prfi/bsop_prti/thtr_ntin/depr_cost
    balance   /finance/balance-sheet       FHKST66430100 → cras/fxas/total_aset/flow_lblt/total_lblt/total_cptl/cpfn
    profit    /finance/profit-ratio        FHKST66430400 → cptl_ntin_rate/sale_totl_rate
    stability /finance/stability-ratio     FHKST66430600 → lblt_rate/crnt_rate
    other     /finance/other-major-ratios  FHKST66430500 → ebitda/ev_ebitda

TR_ID 컨벤션: 5 TR 모두 FH 접두사 = 실전/모의 동일 → 환경별 TR_ID 자동 변환
헬퍼 사용 금지 (V+base[1:] 변환이 FH...→VH... 로 깨짐). FH TR_ID 직접 하드코딩
(condition.py::fetch_daily_candles_ranged 답습).

영속 의무:
- 사이클 88 G-REJECT graceful (개별 TR 실패 시 그 필드만 결측, 나머지 계속)
- 사이클 17 요청 간 asyncio.sleep(0.05) — KIS Rate Limit 안전
- 매매 안전성 무영향 — scanner 매수 진입 전 데이터 계층 (사이클 38)
"""

from __future__ import annotations

import asyncio
import logging

from src.api.base import kis_get_quote
from src.db.stock_master_financial import _safe_float

logger = logging.getLogger(__name__)

# KIS 정본 5 TR (path, TR_ID) — FH 접두사 하드코딩 (실전=모의 동일)
_TR_MAP: dict[str, tuple[str, str]] = {
    "income": ("/uapi/domestic-stock/v1/finance/income-statement", "FHKST66430200"),
    "balance": ("/uapi/domestic-stock/v1/finance/balance-sheet", "FHKST66430100"),
    "profit": ("/uapi/domestic-stock/v1/finance/profit-ratio", "FHKST66430400"),
    "stability": ("/uapi/domestic-stock/v1/finance/stability-ratio", "FHKST66430600"),
    "other": ("/uapi/domestic-stock/v1/finance/other-major-ratios", "FHKST66430500"),
}

# TR 별 정규화 컬럼 매핑 — KIS 필드명 = 스키마 컬럼명 동일이라 직접 매핑
_TR_FIELDS: dict[str, tuple[str, ...]] = {
    "income": ("sale_account", "sale_totl_prfi", "bsop_prti", "thtr_ntin", "depr_cost"),
    "balance": ("cras", "fxas", "total_aset", "flow_lblt", "total_lblt", "total_cptl", "cpfn"),
    "profit": ("cptl_ntin_rate", "sale_totl_rate"),
    "stability": ("lblt_rate", "crnt_rate"),
    "other": ("ebitda", "ev_ebitda"),
}

# 요청 간 지연 (사이클 17 KIS Rate Limit 안전)
_INTER_TR_SLEEP_SECS = 0.05


def _validate_ticker(ticker: str) -> None:
    """6자리 숫자 ticker 가드 (fetch_daily_candles_ranged 답습)."""
    if not (isinstance(ticker, str) and len(ticker) == 6 and ticker.isdigit()):
        raise ValueError(f"ticker 는 6자리 숫자여야 합니다: {ticker!r}")


async def fetch_financial_tr(ticker: str, tr_key: str, div_cls: str = "0") -> list[dict]:
    """단일 재무 TR 호출 — output list 반환.

    Args:
        ticker: KRX 6자리 단축코드.
        tr_key: "income"/"balance"/"profit"/"stability"/"other".
        div_cls: "0"=년/"1"=분기.

    Returns:
        list[dict] — KIS output (다기간, 각 원소 stac_yymm 키). 실패 시 빈 list
        (사이클 88 G-REJECT graceful).

    Raises:
        ValueError: ticker 6자리 미준수 또는 tr_key 미지원.
    """
    _validate_ticker(ticker)
    if tr_key not in _TR_MAP:
        raise ValueError(f"지원하지 않는 tr_key: {tr_key!r}")

    path, tr_id = _TR_MAP[tr_key]
    params = {
        "FID_DIV_CLS_CODE": div_cls,
        "fid_cond_mrkt_div_code": "J",
        "fid_input_iscd": ticker,
    }

    try:
        data = await kis_get_quote(path, tr_id, params)
        output = data.get("output") or []
        return output if isinstance(output, list) else []
    except Exception:
        # 사이클 88 G-REJECT graceful — 개별 TR 실패 시 빈 list
        logger.exception(
            "[finance] fetch_financial_tr 실패 graceful ticker=%s tr_key=%s",
            ticker, tr_key,
        )
        return []


def _normalize_tr_row(tr_key: str, row: dict) -> dict:
    """TR output 원소를 정규화 컬럼명 dict 로 변환 (float 캐스팅)."""
    fields = _TR_FIELDS.get(tr_key, ())
    return {f: _safe_float(row.get(f)) for f in fields}


async def fetch_all_financials(ticker: str, div_cls: str = "0") -> list[dict]:
    """5 TR 순차 호출 → stac_yymm join → 정규화 row list.

    개별 TR 실패 시 그 필드만 결측, 나머지 TR 은 계속 진행 (사이클 88 graceful).

    Args:
        ticker: KRX 6자리 단축코드.
        div_cls: "0"=년/"1"=분기.

    Returns:
        list[dict] — 정규화 row (스키마 18 컬럼 + ticker/stac_yymm/div_cls/raw).
        raw = 5 TR 원본 병합 (사이클 81 G-AST1 원본 보존).
    """
    _validate_ticker(ticker)

    # stac_yymm → 병합 대상 dict (정규화 필드 + raw 병합)
    merged: dict[str, dict] = {}

    tr_keys = list(_TR_MAP.keys())
    for idx, tr_key in enumerate(tr_keys):
        rows = await fetch_financial_tr(ticker, tr_key, div_cls=div_cls)
        for row in rows:
            stac_yymm = row.get("stac_yymm")
            if not stac_yymm:
                continue
            entry = merged.setdefault(
                stac_yymm,
                {"ticker": ticker, "stac_yymm": stac_yymm, "div_cls": div_cls, "raw": {}},
            )
            entry.update(_normalize_tr_row(tr_key, row))
            entry["raw"].update(row)

        # 요청 간 지연 (마지막 TR 뒤는 불필요하나 단순화를 위해 매 TR 후 적용)
        if idx < len(tr_keys) - 1:
            await asyncio.sleep(_INTER_TR_SLEEP_SECS)

    return list(merged.values())
