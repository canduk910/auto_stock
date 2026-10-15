"""candidate_score_snapshots upsert (supabase/migrations/052) — 관찰 기록 전용, 매매 경로 무관."""
from __future__ import annotations

from datetime import datetime

import src.db.pg as pg
from src.db._kst import now_kst_iso, to_date

COLUMNS = (
    "target_date", "strategy_id", "ticker", "role",
    "rs_raw", "rs_pct", "sector_key", "vs_sector", "sector_pct", "in_sector_pct",
    "revision_breadth", "target_median_change", "opinion_brokers",
    "fin_quarter", "op_income_q", "op_income_q_yoy", "op_turnaround", "op_yoy_growth",
    "revenue_yoy_growth", "net_turnaround", "roe", "debt_ratio_latest", "debt_ratio_down_years",
    "ttm_op_to_max_ratio", "rs_population", "computed_at",
)
_PK = ("target_date", "strategy_id", "ticker")

_SQL = (
    f"INSERT INTO candidate_score_snapshots ({', '.join(COLUMNS)}) "
    f"VALUES ({', '.join(f'${i + 1}' for i in range(len(COLUMNS)))}) "
    f"ON CONFLICT ({', '.join(_PK)}) DO UPDATE SET "
    + ", ".join(f"{c} = EXCLUDED.{c}" for c in COLUMNS if c not in _PK)
)


def _args(row: dict) -> tuple:
    vals = []
    for c in COLUMNS:
        v = row.get(c)
        if c == "target_date":
            v = to_date(v)
        elif c == "computed_at":
            if v is None:
                v = datetime.fromisoformat(now_kst_iso())
            elif isinstance(v, str):
                v = datetime.fromisoformat(v)
        vals.append(v)
    return tuple(vals)


async def upsert_scores(rows) -> int:
    """행 일괄 upsert(PK 충돌 = 덮기). 반환 = 보낸 행 수. 예외는 전파한다(호출자가 단계별로 기록)."""
    rows = list(rows)
    if not rows:
        return 0
    await pg.executemany(_SQL, [_args(r) for r in rows])
    return len(rows)


# ── 읽기 (화면 「RS·재무 관찰」 — GET /api/rs-observe) ──────────────────────────
# 점수 칸 NULL = 「모름」 그대로 돌려준다(0 으로 채우지 않는다).

_SCORE_COLS = tuple(c for c in COLUMNS if c not in ("target_date", "computed_at"))


async def list_dates(limit: int = 60) -> list[str]:
    """기록이 있는 날짜(최근 먼저, `YYYY-MM-DD`)."""
    rows = await pg.fetch(
        "SELECT DISTINCT target_date FROM candidate_score_snapshots ORDER BY target_date DESC LIMIT $1",
        int(limit),
    )
    return [r["target_date"].isoformat() for r in rows]


async def list_snapshot(target_date, strategy_id: str | None = None) -> list[dict]:
    """그 날짜의 행(전략 지정 시 그 전략만). 종목명 = `stock_master.name`(없으면 빈 문자열)."""
    cols = ", ".join(f"s.{c}" for c in _SCORE_COLS)
    sql = (
        f"SELECT to_char(s.target_date, 'YYYY-MM-DD') AS target_date, {cols}, "
        "COALESCE(m.name, '') AS name, "
        "to_char(s.computed_at AT TIME ZONE 'Asia/Seoul', 'YYYY-MM-DD\"T\"HH24:MI:SS') || '+09:00' AS computed_at "
        "FROM candidate_score_snapshots s LEFT JOIN stock_master m ON m.ticker = s.ticker "
        "WHERE s.target_date = $1"
    )
    args: list = [to_date(target_date)]
    if strategy_id:
        sql += " AND s.strategy_id = $2"
        args.append(strategy_id)
    sql += " ORDER BY s.strategy_id, s.role, s.rs_pct DESC NULLS LAST, s.ticker"
    return [dict(r) for r in await pg.fetch(sql, *args)]
