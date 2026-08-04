"""일일 로그 리포트 표본 절단 감지 + ERROR/CRITICAL 전량 보장 — 회귀 가드.

결함 (2026-08-04 발견, 08-03 실측):
`_fetch_logs_in_range(limit=30000)` 는 `ORDER BY timestamp ASC` 라 상한 초과 시
**이른 시각부터** 채우고 조용히 끊는다. 08-03 총 로그 97,353건 → 리포트가 실제로
본 구간은 **07:45~09:47 두 시간**뿐이었고, 그 뒤(사이클 I 배포 11:20 / 정산 20:10 /
21:03 까지)는 전부 시야 밖이었다. 그럼에도 리포트는 완전한 하루인 것처럼 산출됐다.

두 가지가 겹친 결함이다:
  1. **조용함** — 잘렸다는 신호가 metrics 에도 AI 프롬프트에도 없다.
  2. **편향** — ASC 고정이라 하루 판단에 가장 중요한 최근 시간대가 먼저 버려진다.

평시(~18,000건/일)엔 상한이 안 걸리고, **폭주가 난 날 = 리포트가 가장 필요한 날**
에만 발동한다.

시정 규약:
  - 진짜 총계는 원문 fetch 와 무관하게 `SELECT log_level, count(*) GROUP BY` 로 구한다.
  - `len(logs) >= limit` 이면 `truncated=True` + 실제 커버 구간(첫/마지막 로그 시각)을
    metrics 에 명시하고, AI 프롬프트가 이를 볼 수 있게 한다.
  - **ERROR/CRITICAL 은 별도 쿼리로 전량 확보** — 가장 중요한 신호는 절대 잘리지 않는다.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from src.engine import log_analysis_engine as lae

pytestmark = pytest.mark.unit

KST = timezone(timedelta(hours=9))


def _row(ts: str, level: str, msg: str) -> dict:
    return {"timestamp": ts, "log_level": level, "message": msg}


# ---------------------------------------------------------------------------
# T-1 — 절단 감지: fetch 건수가 limit 에 도달하면 truncated=True
# ---------------------------------------------------------------------------
def test_aggregate_marks_truncated_when_limit_reached():
    logs = [_row(f"2026-08-03T0{7 + i // 500}:00:00.0+09:00", "WARNING", "x") for i in range(1000)]
    m = lae._aggregate_logs(logs, fetch_limit=1000)
    assert m["truncated"] is True
    assert m["fetched_logs"] == 1000


def test_aggregate_not_truncated_below_limit():
    logs = [_row("2026-08-03T07:00:00.0+09:00", "INFO", "x") for _ in range(10)]
    m = lae._aggregate_logs(logs, fetch_limit=1000)
    assert m["truncated"] is False


def test_aggregate_backward_compatible_without_limit():
    """fetch_limit 미전달 시 기존 계약 보존 (truncated 판정 불가 → False)."""
    logs = [_row("2026-08-03T07:00:00.0+09:00", "ERROR", "boom")]
    m = lae._aggregate_logs(logs)
    assert m["total_logs"] == 1
    assert m["truncated"] is False


# ---------------------------------------------------------------------------
# T-2 — 커버 구간 명시: 실제로 본 첫/마지막 로그 시각
# ---------------------------------------------------------------------------
def test_aggregate_reports_covered_window():
    logs = [
        _row("2026-08-03T07:45:00.0+09:00", "INFO", "a"),
        _row("2026-08-03T09:47:12.0+09:00", "WARNING", "b"),
    ]
    m = lae._aggregate_logs(logs, fetch_limit=2)
    assert m["covered_from"].startswith("2026-08-03T07:45")
    assert m["covered_to"].startswith("2026-08-03T09:47")


def test_covered_window_none_when_empty():
    m = lae._aggregate_logs([], fetch_limit=100)
    assert m["covered_from"] is None and m["covered_to"] is None
    assert m["truncated"] is False


# ---------------------------------------------------------------------------
# T-3 — 진짜 총계는 SQL count(*) 로 (원문 fetch 절단과 무관)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_count_logs_by_level_uses_group_by(monkeypatch):
    captured = {}

    async def fake_fetch(sql, *args):
        captured["sql"] = sql
        return [
            {"log_level": "WARNING", "cnt": 89427},
            {"log_level": "INFO", "cnt": 7912},
            {"log_level": "ERROR", "cnt": 14},
        ]

    monkeypatch.setattr(lae.pg, "fetch", fake_fetch)
    start = datetime(2026, 8, 3, 0, 0, tzinfo=KST)
    end = datetime(2026, 8, 3, 23, 59, tzinfo=KST)
    out = await lae._count_logs_by_level(start, end)

    assert out == {"WARNING": 89427, "INFO": 7912, "ERROR": 14}
    assert "group by" in captured["sql"].lower()
    assert "count(" in captured["sql"].lower()


@pytest.mark.asyncio
async def test_count_logs_by_level_graceful_on_failure(monkeypatch):
    """집계 쿼리 실패는 리포트를 막지 않는다 (사이클 88 G-REJECT)."""
    async def boom(sql, *args):
        raise RuntimeError("db down")

    monkeypatch.setattr(lae.pg, "fetch", boom)
    out = await lae._count_logs_by_level(
        datetime(2026, 8, 3, tzinfo=KST), datetime(2026, 8, 3, 23, 59, tzinfo=KST),
    )
    assert out == {}


# ---------------------------------------------------------------------------
# T-4 — ERROR/CRITICAL 전량 확보 (별도 쿼리, cap 무관)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_fetch_high_severity_filters_error_and_critical(monkeypatch):
    captured = {}

    async def fake_fetch(sql, *args):
        captured["sql"] = sql
        captured["args"] = args
        return [_row("2026-08-03T18:06:00.0+09:00", "ERROR", "boom")]

    monkeypatch.setattr(lae.pg, "fetch", fake_fetch)
    rows = await lae._fetch_high_severity_logs(
        datetime(2026, 8, 3, tzinfo=KST), datetime(2026, 8, 3, 23, 59, tzinfo=KST),
    )
    assert len(rows) == 1
    sql = captured["sql"].upper()
    assert "ERROR" in sql and "CRITICAL" in sql


@pytest.mark.asyncio
async def test_fetch_high_severity_graceful(monkeypatch):
    async def boom(sql, *args):
        raise RuntimeError("db down")

    monkeypatch.setattr(lae.pg, "fetch", boom)
    rows = await lae._fetch_high_severity_logs(
        datetime(2026, 8, 3, tzinfo=KST), datetime(2026, 8, 3, 23, 59, tzinfo=KST),
    )
    assert rows == []


# ---------------------------------------------------------------------------
# T-5 — 병합: 절단된 원문 + 전량 ERROR 를 합쳐도 중복 집계되지 않는다
# ---------------------------------------------------------------------------
def test_merge_high_severity_dedupes():
    truncated = [
        _row("2026-08-03T07:45:00.0+09:00", "INFO", "a"),
        _row("2026-08-03T07:49:00.0+09:00", "ERROR", "vi fail"),
    ]
    high = [
        _row("2026-08-03T07:49:00.0+09:00", "ERROR", "vi fail"),   # 이미 포함 — 중복
        _row("2026-08-03T18:06:00.0+09:00", "ERROR", "vi fail"),   # cap 밖 — 신규
    ]
    merged = lae._merge_high_severity(truncated, high)
    assert len(merged) == 3, "동일 (시각, 레벨, 메시지) 는 1건으로"
    errs = [r for r in merged if r["log_level"] == "ERROR"]
    assert len(errs) == 2
    # 시간 오름차순 유지 (소비처 계약)
    assert [r["timestamp"] for r in merged] == sorted(r["timestamp"] for r in merged)


def test_merge_preserves_when_nothing_extra():
    truncated = [_row("2026-08-03T07:45:00.0+09:00", "INFO", "a")]
    assert lae._merge_high_severity(truncated, []) == truncated


# ---------------------------------------------------------------------------
# T-6 — 커버 구간은 ERROR/CRITICAL 병합분에 오염되지 않는다 (역-오인 차단)
# ---------------------------------------------------------------------------
def test_covered_window_excludes_merged_high_severity():
    """상한에 걸린 WARNING 은 09:47 까지인데, 전량 병합된 18:06 ERROR 때문에
    covered_to 가 18:06 으로 보이면 '오후까지 다 봤다' 는 역-오인이 생긴다."""
    logs = [
        _row("2026-08-03T07:45:00.0+09:00", "WARNING", "a"),
        _row("2026-08-03T09:47:00.0+09:00", "WARNING", "b"),
        _row("2026-08-03T18:06:00.0+09:00", "ERROR", "vi fail"),   # cap 밖 병합분
    ]
    m = lae._aggregate_logs(logs, fetch_limit=2)
    assert m["covered_to"].startswith("2026-08-03T09:47"), (
        "커버 구간에 ERROR 병합분이 섞이면 안 된다"
    )
    assert m["truncated"] is True, "절단 판정은 capped 레벨 건수(2) 기준"
    assert m["level_counts"]["ERROR"] == 1, "집계에는 ERROR 가 포함되어야 한다"


def test_all_high_severity_day_falls_back_to_overall_window():
    """전량이 ERROR 인 희소한 날 — 커버 구간이 None 이 되지 않고 폴백."""
    logs = [_row("2026-08-03T18:06:00.0+09:00", "ERROR", "boom")]
    m = lae._aggregate_logs(logs, fetch_limit=100)
    assert m["covered_from"].startswith("2026-08-03T18:06")
    assert m["truncated"] is False
