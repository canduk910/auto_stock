"""cycle455 — 국내 종합지수 일봉 적재 leaf(시장 유닛 원천: 코스피 `0001` · 코스닥 `1001`).

명세 = `_workspace/red/cycle455_market_unit_by_market_spec.md` §3.4·§3.5.

- ``ensure_fresh(*, phase, now_kst=None) -> dict`` — never-raise(``CancelledError`` 만 전파).
  시장마다 DB 행 수가 ``TARGET_ROWS``(260) 미만이면 과거로 내려가며 전체 적재, 아니면 증분
  (``max_bas_dd − 7일`` ~ 오늘). 오늘 봉은 ``TODAY_BAR_CUTOFF``(15:40 KST) 전이면 버린다(장중 미확정).
- 지수 코드 정본 = ``market_unit.INDEX_CODE_BY_MARKET``(여기서 다시 적지 않는다).
- 배선 = ``boot_manager.boot()`` 부팅 1회(prepare 앞) · ``data_load_tasks`` 20:30 일봉 적재 뒤.
- 🔴 8영역·``scheduler``·``src.realtime``·``src.auth`` import 0.
"""
from __future__ import annotations

import asyncio
import logging
import time as _time
from datetime import datetime, time, timedelta

from src.db._kst import KST

logger = logging.getLogger(__name__)

#: 화면 차트(120봉) + 판정 창(80봉)을 덮는 행 수. history 상한(50행 × 6회 = 300) 안.
TARGET_ROWS = 260
INCREMENTAL_BACK_DAYS = 7
TODAY_BAR_CUTOFF = time(15, 40)
_PREFIX = "[domestic_index_ingest] "


def _now_kst() -> datetime:
    return datetime.now(KST)


async def _ingest_one(market: str, code: str, now: datetime) -> dict:
    import src.api.domestic_index as api
    import src.db.domestic_index as db

    today = now.date()
    raw: dict[str, dict] = {}
    have = await db.count(code)
    if have < TARGET_ROWS:
        rows = await api.fetch_index_daily_history(code, today, TARGET_ROWS, raw_out=raw)
    else:
        head = await db.max_bas_dd(code)
        start = (head or today) - timedelta(days=INCREMENTAL_BACK_DAYS)
        rows = await api.fetch_index_daily(code, start, today, raw_out=raw)
    if now.time() < TODAY_BAR_CUTOFF:
        today_s = today.strftime("%Y%m%d")
        rows = [r for r in rows if r[0] < today_s]
    upserted = await db.upsert_many(code, rows, raw_by_date=raw)
    return {"fetched": len(rows), "upserted": upserted,
            "rows": await db.count(code), "head": await db.max_bas_dd(code)}


async def ensure_fresh(*, phase: str, now_kst: datetime | None = None) -> dict:
    """두 시장 지수를 최신으로. 요약 dict 를 돌려준다. never-raise."""
    from src.engine.market_unit import INDEX_CODE_BY_MARKET

    started = _time.monotonic()
    now = now_kst or _now_kst()
    summary: dict = {"phase": phase, "fetched": 0, "upserted": 0, "failed": 0}
    for market, code in INDEX_CODE_BY_MARKET.items():
        try:
            res = await _ingest_one(market, code, now)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.warning("%sfailed market=%s code=%s", _PREFIX, market, code, exc_info=True)
            summary["failed"] += 1
            summary[f"{market}_rows"] = "-"
            summary[f"{market}_head"] = "-"
            continue
        summary["fetched"] += res["fetched"]
        summary["upserted"] += res["upserted"]
        summary[f"{market}_rows"] = res["rows"]
        head = res["head"]
        summary[f"{market}_head"] = head.isoformat() if head else "-"
    summary["elapsed_ms"] = int((_time.monotonic() - started) * 1000)
    log = logger.warning if summary["failed"] else logger.info
    try:
        log(
            "%sphase=%s kospi_rows=%s kospi_head=%s kosdaq_rows=%s kosdaq_head=%s "
            "fetched=%d upserted=%d failed=%d elapsed_ms=%d",
            _PREFIX, phase, summary.get("kospi_rows", "-"), summary.get("kospi_head", "-"),
            summary.get("kosdaq_rows", "-"), summary.get("kosdaq_head", "-"),
            summary["fetched"], summary["upserted"], summary["failed"], summary["elapsed_ms"],
        )
    except Exception:
        pass
    return summary
