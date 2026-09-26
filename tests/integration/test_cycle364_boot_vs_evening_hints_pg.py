"""cycle364 S1 round 3 (F2) — 실 Postgres 왕복: ④ 원인 힌트 3쿼리(`_boot_vs_evening_hints`).

설계 정본 = `_workspace/domain_consult/cycle364_a1_as_of_design.md` §4.3 · round 2 R2.
가짜 pg 문구 검사는 `tests/unit/engine/test_cycle364_funnel_boot_vs_evening.py` BOOT4-12 가 한다.
이 파일은 그 SQL 이 **실 PG 에서 돈다**는 것과 그 의미를 잰다 — 힌트 쿼리가 하나라도 실패하면 그 축이
`None` 이 되어 「설명 안 되는 차이」 WARNING(S2 착수 판단 근거)이 조용히 꺼진다(round 2 검토).

잰 것:
- 창 = `[evening_at, until)` — `until` 과 같은 시각은 **세지 않는다**(부팅 자신의 eager refresh 가
  준비 시작 직후에 찍혀도 새지 않는다). 하한은 경계 1초 안팎으로만 잰다(`>` / `>=` 는 고정하지
  않는다 — 같은 마이크로초에 설정이 바뀌는 일은 없다).
- 값은 **정수**(None 아님) — `$1` 이 집계 FILTER 에서 timestamptz 로 추론되고 WHERE 의
  `$1::date - interval '2 days'` 가 그 위에서 도는지(파라미터 타입 추론 순서)를 실제로 확인한다.
- `head_now` = 창 하한 날짜 −2일 이후 `max(bas_dd)`.

🔴 벽시계 의존 금지 — 모든 행 시각은 INSERT 때 명시한다.
docker/`DATABASE_URL_TEST` 없으면 `pg_harness` fixture 가 `pytest.skip` (CI 가 돌린다).
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.slow]

_KST = timezone(timedelta(hours=9))
_EVE_AT = datetime(2026, 9, 22, 21, 1, 7, tzinfo=_KST)     # 저녁 A1 99행 snapshot_at
_UNTIL = datetime(2026, 9, 23, 7, 45, 11, tzinfo=_KST)     # 부팅 준비 시작(phase=boot started_at 최솟값)
_HEAD = date(2026, 9, 22)
_HINT_MARK = "[funnel_boot_vs_evening] phase=boot hint_error="


async def _seed_strategy_config(pg, rows):
    for sid, at in rows:
        await pg.execute(
            "INSERT INTO strategy_config (strategy_id, updated_at) VALUES ($1, $2)", sid, at,
        )


async def _seed_daily(pg, rows):
    for ticker, bas_dd, at in rows:
        await pg.execute(
            "INSERT INTO stock_master_daily (ticker, bas_dd, created_at, updated_at) VALUES ($1, $2, $3, $3)",
            ticker, bas_dd, at,
        )


async def _seed_master(pg, rows):
    for ticker, at in rows:
        await pg.execute(
            "INSERT INTO stock_master (ticker, nxt_tradable, refreshed_at) VALUES ($1, FALSE, $2)",
            ticker, at,
        )


async def _hints(caplog):
    import src.engine.funnel_capture as fc

    caplog.set_level(logging.INFO)
    out = await fc._boot_vs_evening_hints(_EVE_AT, _UNTIL)
    warns = [
        r.getMessage() for r in caplog.records
        if r.levelno >= logging.WARNING and r.getMessage().startswith(_HINT_MARK)
    ]
    return out, warns


@pytest.mark.asyncio
async def test_c364_pg_hints_1_when_rows_inside_and_outside_window_then_exact_integer_counts(
    clean_strategy_config, clean_stock_master, clean_stock_master_daily, caplog,
):
    pg = clean_strategy_config
    s = timedelta(seconds=1)
    await _seed_strategy_config(pg, [
        ("in_after_evening", _EVE_AT + timedelta(minutes=10)),   # 안
        ("in_before_until", _UNTIL - s),                          # 안
        ("out_before_evening", _EVE_AT - s),                      # 밖 (저녁 캡처 전 변경)
        ("out_at_until", _UNTIL),                                 # 밖 (상한 배타)
        ("out_after_until", _UNTIL + timedelta(minutes=5)),       # 밖 (부팅 뒤 변경)
    ])
    await _seed_daily(pg, [
        ("990101", _HEAD, _EVE_AT - timedelta(minutes=30)),       # 밖 — 20:31 정규 적재(저녁 캡처가 이미 봤다)
        ("990102", _HEAD, _EVE_AT + timedelta(minutes=5)),        # 안 — 캡처 뒤 늦게 도착한 봉
        ("990103", date(2026, 9, 21), _UNTIL - timedelta(seconds=10)),  # 안 — 아침 보충 적재
        ("990104", _HEAD, _UNTIL),                                # 밖 (상한 배타)
        ("990105", _HEAD, _UNTIL + timedelta(minutes=1)),         # 밖 — 부팅 뒤
        ("990106", date(2026, 9, 18), _EVE_AT - timedelta(days=3)),  # 밖 — 오래된 봉
    ])
    await _seed_master(pg, [
        ("990201", _EVE_AT + timedelta(hours=1)),                 # 안
        ("990202", _UNTIL - s),                                   # 안
        ("990203", _EVE_AT - timedelta(hours=1)),                 # 밖
        ("990204", _UNTIL),                                       # 밖 (상한 배타)
        ("990205", _UNTIL + timedelta(seconds=30)),               # 밖 — 부팅 자신의 보유 eager refresh
    ])

    out, warns = await _hints(caplog)

    assert warns == [], f"실 PG 에서 힌트 쿼리가 실패했다 — 「설명 안 되는 차이」 WARNING 이 꺼진다: {warns}"
    for key in ("params_changed", "bars_changed_after", "sm_refreshed_after"):
        assert type(out.get(key)) is int, f"`{key}` 는 정수여야 한다(None = 쿼리 실패): {out}"
    assert out["params_changed"] == 2, f"strategy_config 창 [evening_at, until) 개수: {out}"
    assert out["bars_changed_after"] == 2, f"stock_master_daily 창 개수: {out}"
    assert out["sm_refreshed_after"] == 2, f"stock_master 창 개수(부팅 eager refresh 제외): {out}"
    assert out["head_now"] == _HEAD, f"head_now = max(bas_dd): {out}"


@pytest.mark.asyncio
async def test_c364_pg_hints_2_when_nothing_changed_in_window_then_zeros_not_none(
    clean_strategy_config, clean_stock_master, clean_stock_master_daily, caplog,
):
    """평시(저녁 캡처 뒤 아무것도 안 바뀐 밤) = 세 힌트가 **0**(정수). 이 값이어야 `same=0` 일 때
    「설명 안 되는 차이」 WARNING 이 켜진다 — None 이면 그 WARNING 은 영원히 꺼진다."""
    pg = clean_strategy_config
    await _seed_strategy_config(pg, [("momentum", _EVE_AT - timedelta(days=2))])
    await _seed_daily(pg, [
        ("990101", _HEAD, _EVE_AT - timedelta(minutes=30)),
        ("990102", date(2026, 9, 21), _EVE_AT - timedelta(days=1)),
    ])
    await _seed_master(pg, [("990201", _UNTIL + timedelta(seconds=40))])

    out, warns = await _hints(caplog)

    assert warns == [], warns
    assert (out["params_changed"], out["bars_changed_after"], out["sm_refreshed_after"]) == (0, 0, 0), out
    for key in ("params_changed", "bars_changed_after", "sm_refreshed_after"):
        assert type(out[key]) is int, out
    assert out["head_now"] == _HEAD, out
