"""종목투자의견(FHKST663300C0) · 종목추정실적(HHKST668300C0) 래퍼 — 시세 풀(`kis_get_quote`) 경유.

정본 = `docs/kis/domestic-stock-info.md`. 정규화·집계는 순수 함수(`src.engine.fundamental_score`) 몫.
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any

from src.api.base import kis_get_quote
from src.config import settings

logger = logging.getLogger(__name__)

_OPINION_PAGE_SIZE = 100  # 응답 최대 행수 — 도달하면 잘렸을 수 있다

OPINION_PATH = "/uapi/domestic-stock/v1/quotations/invest-opinion"
OPINION_TR_ID = "FHKST663300C0"
ESTIMATE_PATH = "/uapi/domestic-stock/v1/quotations/estimate-perform"
ESTIMATE_TR_ID = "HHKST668300C0"  # 실전 전용(모의 미지원)


def _to_int(v: Any) -> int | None:
    try:
        s = str(v).strip()
        return int(float(s)) if s else None
    except (TypeError, ValueError):
        return None


def _to_float(v: Any) -> float | None:
    try:
        s = str(v).strip()
        return float(s) if s else None
    except (TypeError, ValueError):
        return None


def _to_date(v: Any) -> date | None:
    try:
        return datetime.strptime(str(v).strip(), "%Y%m%d").date()
    except (TypeError, ValueError):
        return None


async def inquire_invest_opinion(ticker: str, date_from: date, date_to: date) -> list[dict]:
    """종목투자의견 — 정규화 dict 목록(원본 행은 `raw`). 실전 전용(모의면 호출 없이 []). KIS 오류는 전파한다."""
    if not settings.is_production:
        return []
    resp = await kis_get_quote(
        OPINION_PATH, OPINION_TR_ID,
        params={
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_COND_SCR_DIV_CODE": "16633",
            "FID_INPUT_ISCD": ticker,
            "FID_INPUT_DATE_1": date_from.strftime("%Y%m%d"),
            "FID_INPUT_DATE_2": date_to.strftime("%Y%m%d"),
        },
    )
    rows = resp.get("output") or []
    if len(rows) >= _OPINION_PAGE_SIZE:
        logger.warning(
            "[invest_opinion_truncated] %s %s~%s rows=%d — 응답 상한 도달, 기간을 쪼개 재조회 필요",
            ticker, date_from.strftime("%Y%m%d"), date_to.strftime("%Y%m%d"), len(rows),
        )
    out: list[dict] = []
    for row in rows:
        out.append({
            "bsop_date": _to_date(row.get("stck_bsop_date")),
            "mbcr_name": row.get("mbcr_name"),
            "invt_opnn": row.get("invt_opnn"),
            "rgbf_invt_opnn": row.get("rgbf_invt_opnn"),
            "hts_goal_prc": _to_int(row.get("hts_goal_prc")),
            "stck_prdy_clpr": _to_int(row.get("stck_prdy_clpr")),
            "dprt": _to_float(row.get("dprt")),
            "raw": row,
        })
    return out


async def inquire_estimate_perform(ticker: str) -> dict | None:
    """종목추정실적 — 실전 전용(모의면 호출 없이 None). `output1` 한글명은 해석하지 않고 raw 로 보관."""
    if not settings.is_production:
        return None
    resp = await kis_get_quote(ESTIMATE_PATH, ESTIMATE_TR_ID, params={"SHT_CD": ticker})
    months = [r.get("dt") for r in (resp.get("output4") or []) if r.get("dt")]
    raw = {k: v for k, v in resp.items() if k != "_response_headers"}
    return {"ticker": ticker, "raw": raw, "settle_months": months}
