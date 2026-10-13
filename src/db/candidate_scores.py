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
