"""L1+L5 Red — `src/db/trade_history.py` KST 시각 변환 + today 쿼리 timezone.

배경:
- 2026-05-12 005930(삼성전자) 보완 INSERT 결함 추적 결과, `_build_pnl_pairs` 가
  ISO 타임스탬프 단순 슬라이스로 시각을 노출 → UTC ISO 가 그대로 표시되어
  KST 09시 이전 매수가 "전일 23시"로 보이는 결함 발견.
- 동시에 `get_today_*` 쿼리가 TZ-naive `{today}T00:00:00` 로 비교 →
  PostgreSQL TIMESTAMPTZ가 UTC로 해석 → KST 09시 이전 매수 기록 누락.

요구 행위:

L1.
A. UTC `"2026-05-11T23:05:47+00:00"` 가 `("2026-05-12", "08:05:47")` 로 변환된다.
B. KST `"2026-05-12T08:05:47+09:00"` 가 `("2026-05-12", "08:05:47")` 로 유지된다.
C. tz-naive `"2026-05-12T08:05:47"` 가 KST 가정 → `("2026-05-12", "08:05:47")`.
D. None/빈 문자열/잘못된 ISO → `(None, None)`.

L5.
E. `get_today_buy_trades` / `get_today_sell_trades` / `get_today_trades_for_settlement`
   가 `+09:00` 명시 KST timezone 으로 `.gte("timestamp", ...)` 를 호출한다.
"""

from __future__ import annotations

from typing import Any

import pytest
from freezegun import freeze_time

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# L1 — _to_kst 헬퍼
# ---------------------------------------------------------------------------


def test_to_kst_converts_utc_iso_to_kst():
    """A. UTC ISO 가 KST 로 변환되어 (date, time) 튜플로 반환된다."""
    from src.db.trade_history import _to_kst

    date, time = _to_kst("2026-05-11T23:05:47+00:00")
    assert date == "2026-05-12"
    assert time == "08:05:47"


def test_to_kst_preserves_kst_iso():
    """B. 이미 KST 인 ISO 는 재변환 없이 동일 시각 유지."""
    from src.db.trade_history import _to_kst

    date, time = _to_kst("2026-05-12T08:05:47+09:00")
    assert date == "2026-05-12"
    assert time == "08:05:47"


def test_to_kst_assumes_kst_for_tz_naive():
    """C. tz-naive ISO 는 KST 로 가정 (DB에서 이미 KST 저장 케이스 호환)."""
    from src.db.trade_history import _to_kst

    date, time = _to_kst("2026-05-12T08:05:47")
    assert date == "2026-05-12"
    assert time == "08:05:47"


@pytest.mark.parametrize("bad", [None, "", "not-an-iso-string", "2026-05"])
def test_to_kst_handles_invalid_input(bad):
    """D. None/빈/잘못된 ISO → (None, None)."""
    from src.db.trade_history import _to_kst

    date, time = _to_kst(bad)
    assert date is None
    assert time is None


# ---------------------------------------------------------------------------
# L1 — _build_pnl_pairs 출력 검증
# ---------------------------------------------------------------------------


def _patch_pg_fetch(monkeypatch, rows: list[dict]):
    """`src.db.trade_history.pg.fetch` 가 rows 반환하도록 mock (사이클 M2a 전환)."""
    from src.db import trade_history

    async def _fetch(sql, *args):
        return list(rows)

    class _PgMock:
        fetch = staticmethod(_fetch)

    monkeypatch.setattr(trade_history, "pg", _PgMock())


@pytest.mark.asyncio
async def test_get_trade_pairs_converts_utc_timestamps_to_kst(
    monkeypatch: pytest.MonkeyPatch,
):
    """`get_trade_pairs` 가 trade_history 의 UTC ISO 를 KST 로 변환해 emit."""
    from src.db import trade_history

    # 매수 23:05 UTC = 익일 08:05 KST → 매도 23:55 UTC = 익일 08:55 KST
    fake_rows = [
        {
            "ticker": "005930",
            "ticker_name": "삼성전자",
            "trade_type": "BUY",
            "price": 70000,
            "quantity": 10,
            "status": "COMPLETED",
            "strategy": "momentum",
            "timestamp": "2026-05-11T23:05:47+00:00",
        },
        {
            "ticker": "005930",
            "ticker_name": "삼성전자",
            "trade_type": "SELL",
            "price": 71000,
            "quantity": 10,
            "status": "COMPLETED",
            "strategy": "momentum",
            "timestamp": "2026-05-11T23:55:00+00:00",
        },
    ]

    _patch_pg_fetch(monkeypatch, fake_rows)

    pairs = await trade_history.get_trade_pairs()
    assert len(pairs) == 1
    p = pairs[0]
    # 매수: 23:05 UTC → 익일 08:05 KST
    assert p["buy_date"] == "2026-05-12"
    assert p["buy_time"] == "08:05:47"
    # 매도: 23:55 UTC → 익일 08:55 KST
    assert p["sell_date"] == "2026-05-12"
    assert p["sell_time"] == "08:55:00"


@pytest.mark.asyncio
async def test_get_trade_pairs_open_position_kst(
    monkeypatch: pytest.MonkeyPatch,
):
    """open 페어(매도 없음) 의 buy_time 도 KST 로 노출."""
    from src.db import trade_history

    fake_rows = [
        {
            "ticker": "012200",
            "ticker_name": "계양전기",
            "trade_type": "BUY",
            "price": 5000,
            "quantity": 100,
            "status": "COMPLETED",
            "strategy": "donchian_swing",
            "timestamp": "2026-05-11T22:30:00+00:00",
        }
    ]

    _patch_pg_fetch(monkeypatch, fake_rows)

    pairs = await trade_history.get_trade_pairs()
    assert len(pairs) == 1
    p = pairs[0]
    assert p["status"] == "open"
    # 22:30 UTC → 익일 07:30 KST
    assert p["buy_date"] == "2026-05-12"
    assert p["buy_time"] == "07:30:00"


# ---------------------------------------------------------------------------
# L5 — _today_kst_iso 헬퍼 + get_today_* 쿼리 timezone
# ---------------------------------------------------------------------------


@freeze_time("2026-05-12 02:00:00")  # KST 11:00, UTC 02:00 → today 차이 발생
def test_today_kst_iso_returns_kst_timezone_string():
    """E. `_today_kst_iso()` 가 `+09:00` 포함 KST timezone 문자열을 반환한다."""
    from src.db.trade_history import _today_kst_iso

    iso = _today_kst_iso()
    # 형식: YYYY-MM-DDT00:00:00+09:00 — KST 11:00 시각이면 KST 오늘은 2026-05-12
    assert iso.endswith("+09:00")
    assert iso.startswith("2026-05-12T00:00:00")


def _patch_pg_capture_args(monkeypatch):
    """`pg.fetch` 호출 시 SQL + 바인딩 인자를 캡처 (빈 rows 반환).

    사이클 M2a — today_iso(`+09:00` str) 는 `datetime.fromisoformat()` 로 변환되어
    바인딩된다(asyncpg TIMESTAMPTZ 컬럼은 str 거부, M1 패턴 2). tz-aware datetime
    검증으로 KST(`+09:00`) 명시 계약을 확인한다.
    """
    from src.db import trade_history

    captured: dict[str, Any] = {}

    async def _fetch(sql, *args):
        captured["sql"] = sql
        captured["args"] = args
        return []

    class _PgMock:
        fetch = staticmethod(_fetch)

    monkeypatch.setattr(trade_history, "pg", _PgMock())
    return captured


def _assert_kst_datetime_bound(captured: dict[str, Any]) -> None:
    from datetime import datetime, timezone, timedelta

    kst = timezone(timedelta(hours=9))
    datetime_args = [a for a in captured["args"] if isinstance(a, datetime)]
    assert datetime_args, f"timestamp 바인딩(datetime) 누락. 인자={captured['args']}"
    bound = datetime_args[0]
    assert bound.tzinfo is not None, "timestamp 바인딩이 tz-aware 여야 함 (+09:00 명시)."
    assert bound.utcoffset() == timedelta(hours=9), (
        f"KST(+09:00) 명시 누락. utcoffset={bound.utcoffset()}"
    )


@pytest.mark.asyncio
async def test_get_today_buy_trades_uses_kst_timezone(
    monkeypatch: pytest.MonkeyPatch,
):
    """`get_today_buy_trades` 가 KST timezone 명시한 datetime 을 바인딩한다."""
    from src.db import trade_history

    captured = _patch_pg_capture_args(monkeypatch)

    await trade_history.get_today_buy_trades()
    assert "timestamp" in captured["sql"].lower()
    _assert_kst_datetime_bound(captured)


@pytest.mark.asyncio
async def test_get_today_sell_trades_uses_kst_timezone(
    monkeypatch: pytest.MonkeyPatch,
):
    """`get_today_sell_trades` 동일."""
    from src.db import trade_history

    captured = _patch_pg_capture_args(monkeypatch)

    await trade_history.get_today_sell_trades()
    _assert_kst_datetime_bound(captured)


@pytest.mark.asyncio
async def test_get_today_trades_for_settlement_uses_kst_timezone(
    monkeypatch: pytest.MonkeyPatch,
):
    """`get_today_trades_for_settlement` 동일."""
    from src.db import trade_history

    captured = _patch_pg_capture_args(monkeypatch)

    await trade_history.get_today_trades_for_settlement()
    _assert_kst_datetime_bound(captured)
