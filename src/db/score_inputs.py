"""RS·재무 관찰 기록용 일괄 읽기 (매매 경로 무관 — 2단계 `rs_fundamental_observe` 전용).

모두 읽기 전용 · 쿼리 1회. 예외는 호출자(관찰 태스크)가 단계별로 잡는다(조용한 빈 결과로 바꾸지 않는다).
"""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import date, timedelta

import src.db.pg as pg
from src.db._kst import to_date

_LOOKBACK_CAL_DAYS = 320  # 200봉(≈285 달력일) + 여유 — 오래된 봉까지 스캔하지 않는다
_FINANCIAL_COLUMNS = ("ticker", "stac_yymm", "div_cls", "sale_account", "bsop_prti", "thtr_ntin", "lblt_rate")


async def recent_closes_bulk(before: date | str, n: int = 200) -> dict[str, list[float]]:
    """`before − 320일 <= bas_dd < before` 종목별 최근 n봉 종가 — 오래된→최신. 창 함수 1쿼리."""
    rows = await pg.fetch(
        """
        SELECT ticker, bas_dd, close_price
        FROM (
            SELECT ticker, bas_dd, close_price,
                   row_number() OVER (PARTITION BY ticker ORDER BY bas_dd DESC) AS rn
            FROM stock_master_daily
            WHERE bas_dd < $1 AND bas_dd >= $3
        ) t
        WHERE rn <= $2
        """,
        to_date(before), int(n), to_date(before) - timedelta(days=_LOOKBACK_CAL_DAYS),
    )
    per: dict[str, list[tuple[date, float]]] = defaultdict(list)
    for r in rows or []:
        if r.get("close_price") is None:
            continue
        per[r["ticker"]].append((r["bas_dd"], float(r["close_price"])))
    return {t: [c for _d, c in sorted(items, key=lambda x: x[0])] for t, items in per.items()}


async def master_raw_map(tickers) -> dict[str, dict]:
    """`stock_master.master_raw` 일괄 — 행이 없거나 raw 가 비면 키 없음."""
    tickers = list(tickers)
    if not tickers:
        return {}
    rows = await pg.fetch(
        "SELECT ticker, master_raw FROM stock_master WHERE ticker = ANY($1::text[])", tickers,
    )
    out: dict[str, dict] = {}
    for r in rows or []:
        raw = r.get("master_raw")
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except ValueError:
                continue
        if isinstance(raw, dict):
            out[r["ticker"]] = raw
    return out


async def sector_name_map(tickers) -> dict[str, str]:
    """KIS 업종 한글명 `stock_master.raw.bstp_kor_isnm` 일괄 — 행이 없거나 이름이 비면 키 없음."""
    tickers = list(tickers)
    if not tickers:
        return {}
    rows = await pg.fetch(
        "SELECT ticker, raw->>'bstp_kor_isnm' AS isnm FROM stock_master "
        "WHERE ticker = ANY($1::text[])",
        tickers,
    )
    out: dict[str, str] = {}
    for r in rows or []:
        name = str(r.get("isnm") or "").strip()
        if name:
            out[r["ticker"]] = name
    return out


async def financial_rows_bulk(tickers) -> dict[str, list[dict]]:
    """`stock_master_financial` 분기("1")·연간("0") 행 일괄 — 종목별 list."""
    tickers = list(tickers)
    if not tickers:
        return {}
    rows = await pg.fetch(
        f"SELECT {', '.join(_FINANCIAL_COLUMNS)} FROM stock_master_financial "
        "WHERE ticker = ANY($1::text[]) ORDER BY ticker, stac_yymm",
        tickers,
    )
    out: dict[str, list[dict]] = defaultdict(list)
    for r in rows or []:
        out[r["ticker"]].append(dict(r))
    return dict(out)
