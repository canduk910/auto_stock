"""cycle350 B1 — `insert_snapshot` 이 덮어쓸 때 `snapshot_at` 을 DB 시계로 갱신한다.

정본 = `_workspace/red/cycle350_evening_funnel_spec.md` §4 B1.

이 파일은 **로컬 가드**다 — 가짜 `pg` 로 SQL 문자열과 바인딩 인자만 잡는다. 「두 번째
쓰기 뒤 그 행의 `snapshot_at` 이 실제로 두 번째 쓰기 시각이 된다」는 의미 검증은 실 PG
왕복(`tests/integration/test_cycle350_funnel_snapshot_at_pg.py`)이 한다. 둘 다 필요한
이유: 이 파일은 docker 없이도 돌고(빠른 피드백), 왕복은 SQL 이 실제로 그 뜻인지를 잰다.

검증 대상:
- B1-1 `ON CONFLICT ... DO UPDATE SET` 에 `snapshot_at` 대입이 있다.
- B1-3 그 우변은 DB 시계(`now()`) 다 — 애플리케이션 시계(바인딩 `$N`·파이썬 `datetime`)
  를 섞지 않는다.
- B1-2 나머지 UPSERT 의미 불변 — INSERT 컬럼 목록(첫 INSERT 는 기본값 `now()`)·기존
  `col = EXCLUDED.col` 6개·충돌 키·`RETURNING *`.

🔴 「잠정이 확정을 덮는다」(is_provisional FALSE → TRUE 덮어쓰기 허용)를 단언하는 테스트는
**만들지 않는다** — 보류 중인 ③-b(명세 §2)가 뒤집을 결함이라 봉인하면 안 된다. 그래서
`DO UPDATE` 뒤 `WHERE` 절의 유무도 이 파일은 보지 않는다.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from unittest.mock import AsyncMock, patch

import pytest

pytestmark = pytest.mark.unit

_D = date(2026, 9, 14)

#: migration 030 이후 INSERT 가 명시하는 10 컬럼 — `snapshot_at` 은 **없다**(기본값 now()).
_INSERT_COLUMNS = [
    "id", "target_date", "strategy_id", "step_no", "step_name",
    "survived_count", "excluded_count", "survived_tickers", "excluded_sample",
    "is_provisional",
]

#: cycle145·171 이 세운 기존 덮어쓰기 6개 — B1 이 건드리면 안 된다.
_EXISTING_SET_COLUMNS = (
    "step_name", "survived_count", "excluded_count",
    "survived_tickers", "excluded_sample", "is_provisional",
)

#: B1-3 — DB 시계 표현. `CURRENT_TIMESTAMP` 는 PostgreSQL 에서 `now()` 와 같은 값이다
#: (둘 다 트랜잭션 시작 시각). 그 밖의 표현(바인딩 파라미터·EXCLUDED 참조)은 명세 밖이다.
_DB_NOW_RHS = re.compile(r"^(now\(\s*\)|current_timestamp)$", re.IGNORECASE)


async def _capture_upsert(**overrides):
    """`insert_snapshot` 1회 호출 → (sql, bound_args). 가짜 `pg.fetchrow` 가 잡는다."""
    from src.db import strategy_funnel

    kwargs = dict(
        target_date=_D,
        strategy_id="vcp_breakout",
        step_no=99,
        step_name="최종",
        survived_tickers=["005930"],
        is_provisional=True,
    )
    kwargs.update(overrides)
    with patch.object(strategy_funnel, "pg", create=True) as pg_mod:
        pg_mod.fetchrow = AsyncMock(return_value={"id": "x"})
        pg_mod.execute = AsyncMock(return_value="INSERT 0 1")
        out = await strategy_funnel.insert_snapshot(**kwargs)
    assert out == {"id": "x"}, "RETURNING 행 dict 반환 계약이 깨졌다"
    assert pg_mod.fetchrow.await_count == 1, "UPSERT 는 fetchrow 1회여야 한다"
    assert not pg_mod.execute.await_count, "UPSERT 외 별도 execute 가 생겼다(B1 범위 밖)"
    call = pg_mod.fetchrow.await_args
    return call.args[0], call.args[1:]


def _norm(sql: str) -> str:
    return re.sub(r"\s+", " ", sql).strip()


def _set_assignments(sql: str) -> dict[str, str]:
    """`DO UPDATE SET` 절의 `col = rhs` 대입을 dict 로. 끝은 `WHERE`/`RETURNING`."""
    flat = _norm(sql)
    m = re.search(r"DO UPDATE SET (.*?)(?: WHERE | RETURNING |$)", flat, re.IGNORECASE)
    assert m, f"`DO UPDATE SET` 절을 찾지 못했다: {flat}"
    body = m.group(1)
    parts: list[str] = []
    depth = 0
    buf = ""
    for ch in body:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append(buf)
            buf = ""
        else:
            buf += ch
    if buf.strip():
        parts.append(buf)
    out: dict[str, str] = {}
    for p in parts:
        lhs, sep, rhs = p.partition("=")
        assert sep, f"대입이 아닌 SET 조각: {p!r}"
        key = lhs.strip().lower()
        assert key not in out, f"SET 절에 `{key}` 대입이 두 번 있다"
        out[key] = rhs.strip()
    return out


# ===========================================================================
# B1-1 / B1-3 — 덮어쓸 때 snapshot_at 을 DB now() 로 갱신 (Red 대상)
# ===========================================================================
@pytest.mark.asyncio
async def test_c350_b1_1_conflict_update_when_same_key_then_set_clause_assigns_snapshot_at():
    """B1-1 — 같은 `(target_date, strategy_id, step_no)` 로 덮어쓰면 `snapshot_at` 이
    갱신돼야 한다. 대입이 없으면 행은 **최초 INSERT 시각**에 영원히 고정되고,
    `market_ops` 는 07:57 부팅 잠정 행을 16:21 저녁 쓰기 뒤에도 07:57 로 본다(명세 §4)."""
    sql, _ = await _capture_upsert()
    assignments = _set_assignments(sql)
    assert "snapshot_at" in assignments, (
        "insert_snapshot 의 `DO UPDATE SET` 에 `snapshot_at` 대입이 없다 (Red — cycle350 B1-1 "
        "미구현). 덮어쓴 행의 snapshot_at 이 최초 INSERT 시각에 고정된다"
    )


@pytest.mark.asyncio
async def test_c350_b1_3_snapshot_at_refresh_when_overwritten_then_uses_db_clock_not_app_clock():
    """B1-3 — 우변은 DB `now()` 하나. 애플리케이션 시계(파이썬 `datetime` 바인딩)를 섞으면
    컨테이너·DB 시계가 어긋날 때 같은 테이블 안에서 INSERT(`DEFAULT now()`)와 UPDATE 가
    서로 다른 시계를 쓰게 된다."""
    sql, args = await _capture_upsert()
    assignments = _set_assignments(sql)
    rhs = assignments.get("snapshot_at")
    assert rhs is not None, (
        "`DO UPDATE SET` 에 `snapshot_at` 대입이 없다 (Red — cycle350 B1-3 미구현)"
    )
    assert _DB_NOW_RHS.match(rhs), (
        f"`snapshot_at = {rhs}` — 명세 B1-3 은 `snapshot_at = now()` (DB 시계) 다"
    )
    assert not any(isinstance(a, datetime) for a in args), (
        f"바인딩 인자에 파이썬 datetime 이 있다 — 애플리케이션 시계를 섞었다: {args}"
    )


# ===========================================================================
# B1-2 — 나머지 UPSERT 의미 불변 (보존 — 지금도 초록이어야 한다)
# ===========================================================================
@pytest.mark.asyncio
async def test_c350_b1_2_first_insert_when_new_key_then_column_list_unchanged_and_default_now():
    """B1-1 후단 — 첫 INSERT 는 지금처럼 컬럼 기본값 `now()` 를 탄다. INSERT 컬럼 목록에
    `snapshot_at` 을 넣거나 바인딩 수를 바꾸면 호출자 무변경 계약이 흔들린다."""
    sql, args = await _capture_upsert()
    flat = _norm(sql)
    m = re.search(
        r"INSERT INTO strategy_funnel_snapshots \((.*?)\) VALUES \((.*?)\)", flat, re.IGNORECASE
    )
    assert m, f"INSERT 문을 찾지 못했다: {flat}"
    cols = [c.strip() for c in m.group(1).split(",")]
    assert cols == _INSERT_COLUMNS, f"INSERT 컬럼 목록이 바뀌었다: {cols}"
    assert "snapshot_at" not in cols, "첫 INSERT 는 기본값 now() — 컬럼 목록에 넣지 않는다"
    assert len(args) == len(_INSERT_COLUMNS), f"바인딩 인자 수 변경: {len(args)}"


@pytest.mark.asyncio
async def test_c350_b1_2_conflict_update_when_overwritten_then_existing_assignments_preserved():
    """B1-2 — 기존 6개 `col = EXCLUDED.col`(마지막 쓰기가 이김) · 충돌 키 · `RETURNING *`
    불변. `is_provisional` 도 그대로 `EXCLUDED` 를 따른다(이 대입의 **존재**만 본다 —
    어느 방향 덮어쓰기가 허용되는지는 ③-b 소관이라 여기서 단언하지 않는다)."""
    sql, _ = await _capture_upsert()
    flat = _norm(sql)
    assert "ON CONFLICT (target_date, strategy_id, step_no) DO UPDATE SET" in flat, (
        "충돌 키가 바뀌었다(cycle145 migration 035 계약)"
    )
    assert re.search(r"RETURNING \*", flat), "RETURNING * 가 사라졌다 — 반환형 계약"
    assignments = _set_assignments(sql)
    for col in _EXISTING_SET_COLUMNS:
        assert assignments.get(col, "").replace(" ", "").lower() == f"excluded.{col}", (
            f"기존 덮어쓰기 `{col} = EXCLUDED.{col}` 가 바뀌었다: {assignments.get(col)!r}"
        )
