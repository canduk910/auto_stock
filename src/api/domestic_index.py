"""국내주식업종기간별시세(FHKUP03500100) 래퍼 — 업종지수 일봉 종가. 시세 풀(`kis_get_quote`) 경유.

cycle455 — 시장 유닛 원천(코스피 종합 `0001` · 코스닥 종합 `1001`). 정본 =
`docs/kis/domestic-stock-industry.md` 「국내주식업종기간별시세(일_주_월_년)」.

실측(2026-10-14, 운영 키): `0001`·`1001`·`2001` 모두 `rt_cd=0`, 1회 **최대 50행**, output2 는
**최신 먼저**, 연속조회(`tr_cont`) 불가 — 더 과거는 종료일을 과거로 당겨 다시 부른다.
종가 = `bstp_nmix_prpr`, 날짜 = `stck_bsop_date`(YYYYMMDD). 시가·고가·저가(`bstp_nmix_oprc`·`_hgpr`·
`_lwpr`)·거래량·거래대금은 ``raw_out`` 에 날짜별로 담아 준다(화면 차트용 — 판정은 종가만 쓴다).
KIS 오류는 호출자에게 올린다
(적재 leaf `engine/domestic_index_ingest.py` 가 흡수).
"""
from __future__ import annotations

import asyncio
import math
from datetime import date, datetime, timedelta

from src.api.base import kis_get_quote

PATH = "/uapi/domestic-stock/v1/quotations/inquire-daily-indexchartprice"
TR_ID = "FHKUP03500100"  # 실전·모의 동일
MAX_ROWS_PER_CALL = 50
#: `fetch_index_daily_history` 의 호출 상한 · 창 사이 쉼(초)
HISTORY_MAX_CALLS = 6
HISTORY_SLEEP_SECS = 0.2
#: 50 영업일 ≈ 75 달력일 — 한 창이 50행을 넘겨 덮도록 넉넉히 잡는다(넘친 행은 KIS 가 자른다).
_WINDOW_CAL_DAYS = 80


def _parse_rows(rows: list) -> list[tuple[str, float]]:
    out: dict[str, float] = {}
    for r in rows or []:
        if not isinstance(r, dict):
            continue
        d = str(r.get("stck_bsop_date") or "").strip()
        if len(d) != 8 or not d.isdigit():
            continue
        try:
            datetime.strptime(d, "%Y%m%d")
            v = float(str(r.get("bstp_nmix_prpr") or "").strip())
        except (TypeError, ValueError):
            continue
        if not math.isfinite(v) or v <= 0:
            continue
        out[d] = v
    return sorted(out.items())


#: raw 에 담는 칸 — (응답 키, 저장 키)
_RAW_FIELDS = (
    ("bstp_nmix_oprc", "open"), ("bstp_nmix_hgpr", "high"), ("bstp_nmix_lwpr", "low"),
    ("acml_vol", "volume"), ("acml_tr_pbmn", "trade_amount"),
)


def _parse_raw(rows: list, keep: set[str]) -> dict[str, dict]:
    """``keep`` 날짜(종가가 유효한 행)마다 시가·고가·저가·거래량·거래대금. 못 읽는 칸은 뺀다."""
    out: dict[str, dict] = {}
    for r in rows or []:
        if not isinstance(r, dict):
            continue
        d = str(r.get("stck_bsop_date") or "").strip()
        if d not in keep:
            continue
        item: dict = {}
        for src, dst in _RAW_FIELDS:
            try:
                v = float(str(r.get(src) or "").strip())
            except (TypeError, ValueError):
                continue
            if math.isfinite(v) and v >= 0:
                item[dst] = v
        out[d] = item
    return out


async def fetch_index_daily(
    index_code: str, start: date, end: date, *, raw_out: dict | None = None,
) -> list[tuple[str, float]]:
    """KIS 1회 — ``[(YYYYMMDD, 종가)]`` 날짜 오름차순·중복 제거. 0 이하·비수치·날짜 불량 행은 버린다.

    ``raw_out`` 을 주면 남긴 날짜마다 ``{open, high, low, volume, trade_amount}`` 를 채운다.
    """
    resp = await kis_get_quote(
        PATH, TR_ID,
        params={
            "FID_COND_MRKT_DIV_CODE": "U",
            "FID_INPUT_ISCD": index_code,
            "FID_INPUT_DATE_1": start.strftime("%Y%m%d"),
            "FID_INPUT_DATE_2": end.strftime("%Y%m%d"),
            "FID_PERIOD_DIV_CODE": "D",
        },
    )
    output2 = (resp or {}).get("output2") or []
    rows = _parse_rows(output2)
    if raw_out is not None:
        raw_out.update(_parse_raw(output2, {d for d, _ in rows}))
    return rows


async def fetch_index_daily_history(
    index_code: str, end: date, min_rows: int, *, raw_out: dict | None = None,
) -> list[tuple[str, float]]:
    """``end`` 부터 과거로 50봉 창을 내려가며 ``min_rows`` 를 채운다(상한 6회). 0행 응답이면 멈춘다."""
    merged: dict[str, float] = {}
    cursor = end
    for i in range(HISTORY_MAX_CALLS):
        if i:
            await asyncio.sleep(HISTORY_SLEEP_SECS)
        rows = await fetch_index_daily(
            index_code, cursor - timedelta(days=_WINDOW_CAL_DAYS), cursor, raw_out=raw_out,
        )
        if not rows:
            break
        before = len(merged)
        merged.update(dict(rows))
        if len(merged) >= min_rows or len(merged) == before:
            break
        oldest = datetime.strptime(rows[0][0], "%Y%m%d").date()
        cursor = oldest - timedelta(days=1)
    return sorted(merged.items())
