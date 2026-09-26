"""cycle364 S1 Red — ③-b: 잠정 쓰기는 확정 행을 덮지 못한다 (SQL 문구 · 반환 전파, 가짜 pg).

설계 정본 = `_workspace/domain_consult/cycle364_a1_as_of_design.md` §2.6 · §6.2 ③-b · M7.
실 PG 의미는 `tests/integration/test_cycle364_funnel_protect_confirmed_pg.py` 가 잰다(로컬
docker 없으면 skip — 이 파일이 로컬에서 M7 을 잡는 유일한 그물이다).

────────────────────────────────────────────────────────────────────────────
Green 이 맞춰야 하는 계약 (`src/db/strategy_funnel.py::insert_snapshot`)
────────────────────────────────────────────────────────────────────────────
- `ON CONFLICT (target_date, strategy_id, step_no) DO UPDATE SET … WHERE NOT
  (strategy_funnel_snapshots.is_provisional = FALSE AND EXCLUDED.is_provisional = TRUE)`
  — 마이그레이션 없음. 기존 SET 대입 7개(cycle350 `snapshot_at = now()` 포함)·컬럼 10개·
  바인딩 10개·`RETURNING *` 불변.
- 거부되면 `RETURNING` 이 비어 `fetchrow` 가 None → `insert_snapshot` 이 None 을 돌려주고
  (예외 아님) `capture_funnel_snapshots` 의 저장 수에서 빠진다.
- 이유: A1 뒤 평일 저녁 쓰기는 미래 날짜라 오늘 키를 치지 않는다 — cycle350 이 ③-b 단독
  배포를 막았던 「평일 저녁 쓰기 전부 거부」 사유가 사라졌다(§2.6). 남는 충돌 = 장중 재기동의
  +600초 캡처·수동 경로가 오늘 09:35 확정 행을 덮는 것 → 막는다.

Red 유효성: 현행 `DO UPDATE SET` 에 WHERE 가 없다 → 문구 단언이 붉다.
"""

from __future__ import annotations

import re
from datetime import date, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest

pytestmark = pytest.mark.unit

_D = date(2026, 9, 22)


def _norm(sql: str) -> str:
    return re.sub(r"\s+", " ", sql).strip()


async def _capture_sql(fetchrow_return):
    from src.db import strategy_funnel

    with patch.object(strategy_funnel, "pg", create=True) as pg_mod:
        pg_mod.fetchrow = AsyncMock(return_value=fetchrow_return)
        out = await strategy_funnel.insert_snapshot(
            target_date=_D, strategy_id="vcp_breakout", step_no=99, step_name="최종",
            survived_tickers=["990101"], is_provisional=True,
        )
    call = pg_mod.fetchrow.await_args
    return out, call.args[0], call.args[1:]


async def test_c364_3b_1_upsert_when_conflict_then_update_guarded_by_confirmed_row_protection():
    _, sql, _ = await _capture_sql({"id": "x"})
    flat = _norm(sql)
    m = re.search(r"DO UPDATE SET (.*?) RETURNING", flat, re.IGNORECASE)
    assert m, f"`DO UPDATE SET … RETURNING` 을 찾지 못했다: {flat}"
    tail = m.group(1)
    guard = re.search(
        r"\bWHERE NOT \(\s*strategy_funnel_snapshots\.is_provisional\s*=\s*FALSE\s+AND\s+"
        r"EXCLUDED\.is_provisional\s*=\s*TRUE\s*\)",
        tail, re.IGNORECASE,
    )
    assert guard, (
        "잠정 쓰기가 확정 행을 덮는 것을 막는 WHERE 가 없다 (Red — cycle364 ③-b / M7). 기대: "
        "`WHERE NOT (strategy_funnel_snapshots.is_provisional = FALSE AND EXCLUDED.is_provisional = TRUE)`"
    )


async def test_c364_3b_2_upsert_when_guard_added_then_existing_assignments_and_columns_kept():
    _, sql, args = await _capture_sql({"id": "x"})
    flat = _norm(sql)
    assert "ON CONFLICT (target_date, strategy_id, step_no) DO UPDATE SET" in flat
    for col in ("step_name", "survived_count", "excluded_count", "survived_tickers",
                "excluded_sample", "is_provisional"):
        assert re.search(rf"\b{col} = EXCLUDED\.{col}\b", flat), f"기존 대입 `{col}` 소실"
    assert re.search(r"\bsnapshot_at = now\(\)", flat, re.IGNORECASE), "cycle350 B1 대입 소실"
    assert "RETURNING *" in flat
    assert len(args) == 10, f"바인딩 10개 불변 (실측 {len(args)})"


async def test_c364_3b_3_upsert_when_rejected_then_returns_none_without_raising():
    out, _, _ = await _capture_sql(None)
    assert out is None, "거부(RETURNING 0행) = None — 예외로 바꾸지 않는다"


async def test_c364_3b_4_capture_when_row_rejected_then_not_counted(monkeypatch):
    from src.engine.scheduler import capture_funnel_snapshots
    from unittest.mock import MagicMock

    async def _rejected(**kw):
        return None

    monkeypatch.setattr("src.db.strategy_funnel.insert_snapshot", _rejected)
    m = MagicMock()
    m.strategy_id = "vcp_breakout"
    m._funnel_steps = []
    m.get_scanned_tickers = MagicMock(return_value=["990101"])
    reg = MagicMock()
    reg.all = MagicMock(return_value=[m])
    saved = await capture_funnel_snapshots(reg, is_provisional=True)
    assert saved == 0, "보호로 거부된 행을 저장 수에 세면 market_ops·요약이 거짓이 된다"
