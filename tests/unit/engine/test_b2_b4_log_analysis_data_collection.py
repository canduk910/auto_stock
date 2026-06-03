"""사이클 53 Red — B-2 + B-4 통합 시정 (log_analysis 데이터 수집 결함).

배경 (운영 실측, 2026-06-01 자동 리포트):
    - **B-2 (HIGH)**: `[next_day_clear_drained]` 가 정상 발화 (system_logs 영구 기록) 했으나
      `daily_log_reports.metrics.next_day_clear.drained_success = 0` 으로 오집계.
      064400 (LG씨엔에스, momentum) 익일 청산 KST 2026-06-01 09:00:18 result=success
      구체적 로그 존재. 실측: `total_logs=1000` (Supabase PostgREST default 페이지 한도).
    - **B-4 (MEDIUM)**: 064400 SELL `trade_history` 정상 INSERT (timestamp=2026-05-31T23:20 UTC
      = KST 2026-06-01 08:20, +30,100원 COMPLETED) 했으나 `trades.trades_total=4` 오집계
      (064400 momentum 제외 — VB 4건만 카운트).

진단 (메인 세션 확정):
    - **B-2 root cause**: `src/engine/log_analysis_engine.py:69 _fetch_logs_in_range(start, end, limit=5000)`
      이 Supabase PostgREST default 1000 페이지 한도에 잘림. limit=5000 전달해도 1000건만 fetch.
      `drained` 가 *최신* 로그라 오름차순 1000 cap 에서 끝부분 잘려나감.
    - **B-4 root cause**: `src/db/trade_history.py:336 get_trades_in_range` 의 timestamp 문자열
      `f"{date}T00:00:00"` (TZ suffix 없음) → PostgREST UTC 해석 → KST 00:00~09:00 거래 누락.

시정 명세 (Green 단계):
    - **S-1**: `_fetch_logs_in_range` `.range(offset, offset+999)` 루프 페이지네이션,
      `limit` 파라미터는 *총* 한도 의미로 보존 (limit=5000 → 5페이지 cap).
    - **S-2**: `get_trades_in_range` start/end 문자열에 `+09:00` 명시 (또는
      `datetime.combine(date, time.min/max, KST).isoformat()`).
    - **S-3**: `recommendation_engine` 등 호출처 기존 테스트 PASS 회귀 확인 (별도 검증).

5 시나리오 (모두 *현재* FAIL — Red):
    S1: `_fetch_logs_in_range` 가 mock 1500건 fetch 시 모든 1500건 반환 (현재 1000 cap → FAIL)
    S2: 1500건 중 1001~1500 위치의 `[next_day_clear_drained]…result=success` 가 카운트됨
        (현재 1000 cap 에 잘려 0 → FAIL)
    S3: `get_trades_in_range(date(2026,6,1), date(2026,6,1))` 가 UTC 23:20 (= KST 06/01 08:20)
        timestamp 거래 *포함* 반환 (현재 TZ 없는 query 로 UTC 해석 → 누락 → FAIL)
    S4: UTC 자정 boundary 4 거래 중 KST 6/1 영업일 (b)+(c) 만 정확 반환
        (현재 UTC 해석으로 (a) 잘못 포함 + (b) 누락 → FAIL)
    S5: 통합 — `generate_daily_log_report` 가 064400 시나리오 mock 데이터로 호출 시
        `next_day_clear.drained_success=1` AND `trades.trades_total=5` 정확 집계
        (현재 둘 다 잘못 → FAIL)

mock 패턴 (사이클 52 / `tests/unit/db/test_trade_history_kst.py` 동일):
    - Supabase mock: fluent class chain (table().select().gte().lte()…execute())
    - OpenAI mock: `_call_openai` 전체 stub (LLM 응답 무관 — 본 사이클은 데이터 수집만 검증)
    - freezegun: 사용 안 함 (`date()` 입력 명시 — freezegun KST 함정 회피)

Red 상태 (Green 구현 전):
    - S1: page 1 만 (.range(0,999)) 반환 → 1000건만 합산 → FAIL
    - S2: 1001~1500 에 있는 drained 로그가 page 2 미진입 → drained_success=0 → FAIL
    - S3: `T00:00:00` (TZ 없음) → PostgREST UTC 가정 → UTC 2026-06-01T00:00 ~ T23:59 윈도우 →
      `2026-05-31T23:20:00+00:00` (UTC) 가 윈도우 *밖* → 누락 → FAIL
    - S4: 동일 결함 → (a) UTC 5/31 14:59:59 가 6/1 윈도우 밖, (b) UTC 5/31 15:00 가 6/1 윈도우 밖 → FAIL
    - S5: S2 + S3 합산 결함 → FAIL
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone
from typing import Any

import pytest

from src.db import trade_history
from src.engine import log_analysis_engine as lae

pytestmark = pytest.mark.unit

KST = timezone(timedelta(hours=9))


# ---------------------------------------------------------------------------
# 헬퍼 — Supabase fluent mock with .range() 페이지네이션 지원
# ---------------------------------------------------------------------------
class _FakeRangeSelect:
    """`.range(offset, end)` 호출을 추적하며 페이지네이션을 시뮬레이션하는 mock.

    Supabase PostgREST 의 실제 동작 모사:
    - `.limit(N)` 단독 사용 시 default 1000 cap (서버 강제).
    - `.range(offset, end_inclusive)` 사용 시 해당 슬라이스 반환.
    - 두 가지 다 호출되면 `.range()` 가 우선 (Green 의도 시그너처).

    `_range_calls`: 호출 인자 ledger (검증용)
    `_all_range_calls`: `_FakeRangeSupabase` 가 페이지마다 공유하는 전체 누적 리스트.
    """

    def __init__(self, rows: list[dict], all_range_calls: list[tuple[int, int]]) -> None:
        self._rows = rows
        self._range_calls: list[tuple[int, int]] = []
        self._all_range_calls = all_range_calls  # 페이지 간 공유 누적 리스트
        self._limit_value: int | None = None
        self._sliced: list[dict] | None = None

    def gte(self, *_a, **_k):
        return self

    def lte(self, *_a, **_k):
        return self

    def eq(self, *_a, **_k):
        return self

    def in_(self, *_a, **_k):
        return self

    def order(self, *_a, **_k):
        return self

    def limit(self, n: int):
        # Supabase PostgREST 의 default cap 동작: .limit(N) 만 사용 시 N 이 5000 이라도
        # 서버가 1000 으로 강제 cap (이게 본 사이클 결함의 정체).
        # 그러나 `.range()` 와 함께 사용되면 .range() 가 우선.
        self._limit_value = n
        # 결함 시뮬레이션: limit 단독 호출 시 1000 cap 강제
        if self._sliced is None:
            cap = min(n, 1000)
            self._sliced = list(self._rows[:cap])
        return self

    def range(self, offset: int, end_inclusive: int):
        self._range_calls.append((offset, end_inclusive))
        self._all_range_calls.append((offset, end_inclusive))  # 공유 누적 — 페이지 간 추적
        # PostgREST .range() 의미: [offset, end_inclusive] inclusive 슬라이스
        self._sliced = list(self._rows[offset : end_inclusive + 1])
        return self

    def execute(self):
        data = self._sliced if self._sliced is not None else list(self._rows[:1000])
        return type("R", (), {"data": data})()


class _FakeRangeTable:
    def __init__(self, rows: list[dict], select_holder: dict, all_range_calls: list) -> None:
        self._rows = rows
        self._select_holder = select_holder
        self._all_range_calls = all_range_calls

    def select(self, *_a, **_k):
        # 페이지마다 새 인스턴스 생성. 공유 all_range_calls 로 전체 range 호출 추적.
        sel = _FakeRangeSelect(self._rows, self._all_range_calls)
        self._select_holder["select"] = sel
        return sel


class _FakeRangeSupabase:
    def __init__(self, rows: list[dict]) -> None:
        self._rows = rows
        self.select_holder: dict = {}
        self.all_range_calls: list[tuple[int, int]] = []  # 페이지 간 누적 range 호출 ledger

    def table(self, _name: str):
        return _FakeRangeTable(self._rows, self.select_holder, self.all_range_calls)


# ---------------------------------------------------------------------------
# 헬퍼 — trade_history 용 mock (gte/lte 인자 캡처)
# ---------------------------------------------------------------------------
class _FakeTradesSelect:
    def __init__(self, rows: list[dict], captured: dict) -> None:
        self._rows = rows
        self._captured = captured
        self._gte_iso: str | None = None
        self._lte_iso: str | None = None

    def gte(self, col: str, val: str):
        if col == "timestamp":
            self._captured.setdefault("gte_calls", []).append(val)
            self._gte_iso = val
        return self

    def lte(self, col: str, val: str):
        if col == "timestamp":
            self._captured.setdefault("lte_calls", []).append(val)
            self._lte_iso = val
        return self

    def eq(self, *_a, **_k):
        return self

    def in_(self, *_a, **_k):
        return self

    def order(self, *_a, **_k):
        return self

    def execute(self):
        # 실제 PostgREST 의 timestamp 비교 시뮬레이션:
        # - gte/lte 문자열을 datetime 으로 파싱 (TZ 없으면 UTC 가정 — PostgREST 의 결함적 동작)
        # - row.timestamp 도 동일하게 파싱
        # - [gte, lte] 범위 inclusive 필터
        def _parse(iso: str | None) -> datetime | None:
            if not iso:
                return None
            try:
                # PostgREST TIMESTAMPTZ 비교: TZ suffix 없으면 UTC 가정 (결함의 정체)
                dt = datetime.fromisoformat(iso)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt
            except ValueError:
                return None

        gte_dt = _parse(self._gte_iso)
        lte_dt = _parse(self._lte_iso)

        filtered: list[dict] = []
        for r in self._rows:
            ts = r.get("timestamp")
            row_dt = _parse(ts if isinstance(ts, str) else None)
            if row_dt is None:
                continue
            if gte_dt and row_dt < gte_dt:
                continue
            if lte_dt and row_dt > lte_dt:
                continue
            filtered.append(r)
        return type("R", (), {"data": filtered})()


class _FakeTradesTable:
    def __init__(self, rows: list[dict], captured: dict) -> None:
        self._rows = rows
        self._captured = captured

    def select(self, *_a, **_k):
        return _FakeTradesSelect(self._rows, self._captured)


class _FakeTradesSupabase:
    def __init__(self, rows: list[dict]) -> None:
        self._rows = rows
        self.captured: dict = {}

    def table(self, _name: str):
        return _FakeTradesTable(self._rows, self.captured)


# ---------------------------------------------------------------------------
# 데이터 생성 헬퍼 — system_logs 1500건 (1001~1500 위치에 drained 1건 삽입)
# ---------------------------------------------------------------------------
def _make_log(idx: int, message: str, level: str = "INFO") -> dict:
    return {
        "timestamp": f"2026-06-01T{(idx // 60) % 24:02d}:{idx % 60:02d}:00+09:00",
        "log_level": level,
        "message": message,
    }


def _build_1500_logs_with_drained_at_1200() -> list[dict]:
    """1500건 system_logs 생성. position 1200 (1001~1500 구간) 에 drained success 1건 삽입.

    Red 검증 의도: page 1 (.range(0, 999)) 만 fetch 하는 결함 코드는 idx<=999 까지만 보임.
    Green 후엔 .range(1000, 1999) 도 추가 fetch 하여 idx=1200 drained 포착.
    """
    logs: list[dict] = []
    for i in range(1500):
        if i == 1200:
            logs.append(
                _make_log(
                    i,
                    "[next_day_clear_drained] ticker=064400 strategy=momentum result=success elapsed_ms=56",
                )
            )
        elif i == 800:
            # page 1 안 (회귀 가드용) — deferred 1건도 같이 검증
            logs.append(
                _make_log(
                    i,
                    "[next_day_clear_deferred] ticker=064400 strategy=momentum reason=nxt_open_missing",
                )
            )
        else:
            logs.append(_make_log(i, f"일상 로그 {i}"))
    return logs


# ===========================================================================
# S1 — `_fetch_logs_in_range` 페이지네이션 회귀 가드
# ===========================================================================
@pytest.mark.asyncio
async def test_s1_when_supabase_has_1500_logs_then_fetch_returns_all_1500(
    monkeypatch: pytest.MonkeyPatch,
):
    """결함 차단: Supabase 가 1500건 보유할 때 `_fetch_logs_in_range(limit=5000)` 가
    모든 1500건 합산 반환 (현재 1000 cap → FAIL).

    Green 명세:
    - `.range(0, 999)` → `.range(1000, 1999)` → ... 루프
    - limit 파라미터를 *총* 한도로 보존 (limit=5000 이면 최대 5페이지)
    - 빈 페이지 또는 <1000 건 페이지 도달 시 종료
    """
    rows = _build_1500_logs_with_drained_at_1200()
    fake_supabase = _FakeRangeSupabase(rows)
    monkeypatch.setattr(lae, "supabase", fake_supabase)

    start = datetime(2026, 6, 1, 0, 0, 0, tzinfo=KST)
    end = datetime(2026, 6, 1, 23, 59, 59, tzinfo=KST)
    result = await lae._fetch_logs_in_range(start, end, limit=5000)

    assert len(result) == 1500, (
        f"페이지네이션 결함: fetched={len(result)} 건 (기대 1500). "
        f".range() 루프 미구현 — limit=5000 전달해도 PostgREST default 1000 cap 에 잘림. "
        f"Green: `.range(offset, offset+999)` 루프 + limit 를 *총* 한도로 cap."
    )

    # range 호출 ledger 검증 — 최소 2회 (page 1: 0~999, page 2: 1000~1999)
    # 페이지마다 새 select 인스턴스를 사용하므로 all_range_calls (공유 누적) 로 검증.
    range_calls = fake_supabase.all_range_calls
    assert len(range_calls) >= 2, (
        f".range() 호출 횟수 {len(range_calls)} (기대 ≥2). "
        f"Green: 페이지당 1000건씩 합산하는 루프 필요. 호출 ledger: {range_calls}"
    )
    # 첫 페이지 (0, 999) 검증
    assert range_calls[0] == (0, 999), f"첫 .range() 인자 {range_calls[0]} != (0, 999)"


# ===========================================================================
# S2 — next_day_clear 집계 정확성 (1001~1500 구간 drained 포착)
# ===========================================================================
@pytest.mark.asyncio
async def test_s2_when_drained_log_at_position_1200_then_aggregate_counts_it(
    monkeypatch: pytest.MonkeyPatch,
):
    """결함 차단: idx=1200 위치의 `[next_day_clear_drained]…result=success` 가
    `_aggregate_next_day_clear` 결과에 drained_success=1 로 카운트됨.

    현재 결함: `_fetch_logs_in_range` 가 1000건만 반환 → idx=1200 미포함 → 0건.

    이 시나리오는 S1 의 페이지네이션이 Green 되어야 통과 (구조적 의존).
    실측 사고 (2026-06-01 자동 리포트의 `drained_success=0`) 와 동일 시나리오.
    """
    rows = _build_1500_logs_with_drained_at_1200()
    fake_supabase = _FakeRangeSupabase(rows)
    monkeypatch.setattr(lae, "supabase", fake_supabase)

    start = datetime(2026, 6, 1, 0, 0, 0, tzinfo=KST)
    end = datetime(2026, 6, 1, 23, 59, 59, tzinfo=KST)
    fetched = await lae._fetch_logs_in_range(start, end, limit=5000)

    # 페이지네이션 후 1500건이 와야 drained 가 포착됨
    next_day_metrics = lae._aggregate_next_day_clear(fetched)

    assert next_day_metrics["drained_success"] == 1, (
        f"drained_success={next_day_metrics['drained_success']} (기대 1). "
        f"실측 사고 시나리오 — idx=1200 의 drained 로그가 페이지네이션 결함으로 fetch 누락. "
        f"`_fetch_logs_in_range` 가 1000건만 반환 → 1001~1500 구간 drained 미포착. "
        f"fetched={len(fetched)}"
    )
    # 회귀 가드: 800 위치 deferred (page 1 안) 는 결함 코드도 잡아야 함
    assert next_day_metrics["deferred"] == 1, (
        f"deferred={next_day_metrics['deferred']} (기대 1, page 1 안 ledger 회귀 가드)"
    )


# ===========================================================================
# S3 — `get_trades_in_range` KST 경계 (UTC 23:20 거래 포함)
# ===========================================================================
@pytest.mark.asyncio
async def test_s3_when_utc_2320_trade_then_kst_today_includes_it(
    monkeypatch: pytest.MonkeyPatch,
):
    """결함 차단: UTC `2026-05-31T23:20:00` (= KST 2026-06-01 08:20) 거래가
    `get_trades_in_range(date(2026,6,1), date(2026,6,1))` 결과에 포함됨.

    Green 명세:
    - start_iso = `2026-06-01T00:00:00+09:00` (또는 `datetime.combine(date, time.min, KST).isoformat()`)
    - end_iso = `2026-06-01T23:59:59.999999+09:00`

    현재 결함: `f"{date}T00:00:00"` (TZ 없음) → PostgREST UTC 가정 →
    UTC 2026-06-01T00:00~T23:59 윈도우 → UTC 5/31 23:20 거래가 윈도우 *밖* → 누락.

    실측 사고 (2026-06-01 자동 리포트의 `trades_total=4`) 와 동일 시나리오.
    """
    rows = [
        {
            "ticker": "064400",
            "ticker_name": "LG씨엔에스",
            "trade_type": "SELL",
            "price": 5_900,
            "quantity": 100,
            "status": "COMPLETED",
            "strategy": "momentum",
            "profit_loss": 30_100,
            "timestamp": "2026-05-31T23:20:00+00:00",  # UTC = KST 2026-06-01 08:20
        },
    ]
    fake_supabase = _FakeTradesSupabase(rows)
    monkeypatch.setattr(trade_history, "supabase", fake_supabase)

    target = date(2026, 6, 1)
    result = await trade_history.get_trades_in_range(target, target)

    assert len(result) == 1, (
        f"KST timezone 결함: fetched={len(result)} 건 (기대 1). "
        f"UTC 23:20 (= KST 익일 08:20) 거래가 누락됨. "
        f"`get_trades_in_range` 의 start_iso/end_iso 에 `+09:00` 누락 → PostgREST UTC 해석."
    )
    assert result[0]["ticker"] == "064400"
    assert result[0]["profit_loss"] == 30_100

    # gte/lte 호출 인자가 KST timezone 명시
    captured = fake_supabase.captured
    gte_calls = captured.get("gte_calls", [])
    lte_calls = captured.get("lte_calls", [])
    assert gte_calls, "gte('timestamp', ...) 호출 자체가 없음"
    assert lte_calls, "lte('timestamp', ...) 호출 자체가 없음"
    assert gte_calls[0].endswith("+09:00"), (
        f"start_iso 에 KST timezone 미명시: {gte_calls[0]} "
        f"(기대 suffix `+09:00`). Green: `datetime.combine(start_date, time.min, KST).isoformat()` "
        f"또는 `f\"{{date}}T00:00:00+09:00\"`"
    )
    assert lte_calls[0].endswith("+09:00"), (
        f"end_iso 에 KST timezone 미명시: {lte_calls[0]} (기대 suffix `+09:00`)"
    )


# ===========================================================================
# S4 — UTC 자정 boundary 회귀 가드 (4 거래 → KST 6/1 영업일 2건만)
# ===========================================================================
@pytest.mark.asyncio
async def test_s4_when_utc_midnight_boundary_then_only_kst_target_date_returned(
    monkeypatch: pytest.MonkeyPatch,
):
    """결함 차단: UTC 자정 직전/직후 4 거래 → KST 6/1 영업일 (b)+(c) 만 정확 반환.

    - (a) `2026-05-31T14:59:59+00:00` = KST 5/31 23:59:59 — *5/31* 영업일 (제외)
    - (b) `2026-05-31T15:00:00+00:00` = KST 6/1 00:00:00 — *6/1* 영업일 (포함)
    - (c) `2026-06-01T14:59:59+00:00` = KST 6/1 23:59:59 — *6/1* 영업일 (포함)
    - (d) `2026-06-01T15:00:00+00:00` = KST 6/2 00:00:00 — *6/2* 영업일 (제외)

    현재 결함: TZ 없는 query → UTC 해석 →
    - UTC 윈도우 `2026-06-01T00:00~T23:59` → (c), (d) 만 포함, (a), (b) 제외.
    - 즉 결함 코드는 (c)+(d) 2건 반환 — 본 테스트는 (b)+(c) 기대라 FAIL (정확히 다른 조합).
    """
    rows = [
        {
            "ticker": "AAAAAA",
            "trade_type": "SELL",
            "strategy": "momentum",
            "profit_loss": 100,
            "status": "COMPLETED",
            "timestamp": "2026-05-31T14:59:59+00:00",  # KST 5/31 23:59:59 (제외)
        },
        {
            "ticker": "BBBBBB",
            "trade_type": "SELL",
            "strategy": "momentum",
            "profit_loss": 200,
            "status": "COMPLETED",
            "timestamp": "2026-05-31T15:00:00+00:00",  # KST 6/1 00:00:00 (포함)
        },
        {
            "ticker": "CCCCCC",
            "trade_type": "SELL",
            "strategy": "momentum",
            "profit_loss": 300,
            "status": "COMPLETED",
            "timestamp": "2026-06-01T14:59:59+00:00",  # KST 6/1 23:59:59 (포함)
        },
        {
            "ticker": "DDDDDD",
            "trade_type": "SELL",
            "strategy": "momentum",
            "profit_loss": 400,
            "status": "COMPLETED",
            "timestamp": "2026-06-01T15:00:00+00:00",  # KST 6/2 00:00:00 (제외)
        },
    ]
    fake_supabase = _FakeTradesSupabase(rows)
    monkeypatch.setattr(trade_history, "supabase", fake_supabase)

    target = date(2026, 6, 1)
    result = await trade_history.get_trades_in_range(target, target)

    returned_tickers = sorted(r["ticker"] for r in result)
    assert returned_tickers == ["BBBBBB", "CCCCCC"], (
        f"KST boundary 결함: returned_tickers={returned_tickers} "
        f"(기대 ['BBBBBB', 'CCCCCC']). UTC 해석으로 (a)+(b)+(c)+(d) 조합이 잘못 잘림. "
        f"Green: start/end ISO 에 `+09:00` 명시 → UTC 윈도우 [2026-05-31T15:00+00:00, "
        f"2026-06-01T14:59:59.999999+00:00] 으로 변환되어 정확."
    )


# ===========================================================================
# S5 — generate_daily_log_report 통합 (064400 시나리오 종합)
# ===========================================================================
@pytest.mark.asyncio
async def test_s5_when_064400_scenario_then_report_metrics_accurate(
    monkeypatch: pytest.MonkeyPatch,
):
    """결함 차단: 064400 시나리오 mock 데이터로 `generate_daily_log_report()` 호출 시
    `next_day_clear.drained_success=1` AND `trades.trades_total=5` AND `realized_pnl=56,100` 정확.

    시나리오 (2026-06-01 실측 재현):
    - system_logs: 1500건 중 deferred 1건 (idx=800) + drained success 1건 (idx=1200)
    - trade_history: 064400 SELL UTC 23:20 +30,100 + VB 4건 (KST 영업일 내) = 5건

    현재 결함 합산:
    - drained_success = 0 (B-2: 1000 cap)
    - trades_total = 4 (B-4: KST 6/1 08:20 거래 누락)
    - realized_pnl = 26,000 (VB 4건 합산만, 064400 +30,100 누락)

    Green 후:
    - drained_success = 1 / trades_total = 5 / realized_pnl >= 56,100
    """
    # --- system_logs mock ---
    logs_rows = _build_1500_logs_with_drained_at_1200()
    fake_logs_supabase = _FakeRangeSupabase(logs_rows)
    monkeypatch.setattr(lae, "supabase", fake_logs_supabase)

    # --- trade_history mock (5건) ---
    trades_rows = [
        {
            "ticker": "064400",
            "ticker_name": "LG씨엔에스",
            "trade_type": "SELL",
            "price": 5_900,
            "quantity": 100,
            "status": "COMPLETED",
            "strategy": "momentum",
            "profit_loss": 30_100,
            "timestamp": "2026-05-31T23:20:00+00:00",  # UTC = KST 6/1 08:20
        },
        # VB 4건 (KST 6/1 정규장 — UTC 환산: 6/1 00:30~06:20)
        {
            "ticker": "AAAAAA",
            "trade_type": "SELL",
            "price": 10_000,
            "quantity": 10,
            "status": "COMPLETED",
            "strategy": "volatility_breakout",
            "profit_loss": 6_000,
            "timestamp": "2026-06-01T00:30:00+00:00",  # KST 09:30
        },
        {
            "ticker": "BBBBBB",
            "trade_type": "SELL",
            "price": 20_000,
            "quantity": 5,
            "status": "COMPLETED",
            "strategy": "volatility_breakout",
            "profit_loss": 5_000,
            "timestamp": "2026-06-01T02:00:00+00:00",  # KST 11:00
        },
        {
            "ticker": "CCCCCC",
            "trade_type": "SELL",
            "price": 15_000,
            "quantity": 8,
            "status": "COMPLETED",
            "strategy": "volatility_breakout",
            "profit_loss": 8_000,
            "timestamp": "2026-06-01T04:00:00+00:00",  # KST 13:00
        },
        {
            "ticker": "DDDDDD",
            "trade_type": "SELL",
            "price": 8_000,
            "quantity": 20,
            "status": "COMPLETED",
            "strategy": "volatility_breakout",
            "profit_loss": 7_000,
            "timestamp": "2026-06-01T06:20:00+00:00",  # KST 15:20
        },
    ]
    fake_trades_supabase = _FakeTradesSupabase(trades_rows)
    monkeypatch.setattr(trade_history, "supabase", fake_trades_supabase)

    # --- OpenAI / insert mock ---
    captured_metrics: dict = {}

    async def _fake_call_openai(metrics: dict) -> dict:
        captured_metrics["metrics"] = metrics
        return {"summary": "test", "findings": []}

    async def _fake_insert(*_args, **_kwargs):
        return {"id": "row-1"}

    async def _empty_funnel() -> dict:
        return {}

    monkeypatch.setattr(lae, "_call_openai", _fake_call_openai)
    monkeypatch.setattr(lae, "insert_log_report", _fake_insert)
    monkeypatch.setattr(lae, "_collect_strategy_funnel", _empty_funnel)
    monkeypatch.setattr(lae.settings, "openai_api_key", "dummy-key")

    # api_metrics 도 차단 (외부 영향 없음)
    monkeypatch.setattr(lae, "get_request_metrics", lambda: {})
    monkeypatch.setattr(lae, "reset_request_metrics", lambda: None)

    # 날짜 고정 — 테스트 데이터가 2026-06-01 기준이므로 _now_kst 로 override.
    # generate_daily_log_report 가 datetime.now(KST) 를 사용하면 실행 날짜에 따라
    # trade_history 의 timestamp 필터 범위가 달라져 mock 데이터가 제외됨.
    _fixed_now_kst = datetime(2026, 6, 1, 20, 10, 0, tzinfo=KST)
    await lae.generate_daily_log_report(_now_kst=_fixed_now_kst)

    metrics = captured_metrics.get("metrics")
    assert metrics is not None, "generate_daily_log_report 가 _call_openai 호출 안 함"

    # 핵심 1: drained_success 정확 카운트
    ndc = metrics.get("next_day_clear", {})
    assert ndc.get("drained_success") == 1, (
        f"B-2 결함: drained_success={ndc.get('drained_success')} (기대 1). "
        f"실측 사고 — 1500건 system_logs 중 idx=1200 drained 가 1000 cap 에 잘림. "
        f"_fetch_logs_in_range 페이지네이션 누락."
    )

    # 핵심 2: trades_total 정확 카운트 (5건)
    trades = metrics.get("trades", {})
    assert trades.get("trades_total") == 5, (
        f"B-4 결함: trades_total={trades.get('trades_total')} (기대 5). "
        f"실측 사고 — 064400 SELL UTC 23:20 (= KST 6/1 08:20) 가 KST timezone 누락 query 로 제외. "
        f"VB 4건만 카운트."
    )

    # 핵심 3: realized_pnl 정확 합산 (064400 30,100 + VB 26,000 = 56,100)
    assert trades.get("realized_pnl", 0) >= 56_100, (
        f"realized_pnl={trades.get('realized_pnl')} (기대 ≥56,100). "
        f"064400 +30,100 누락으로 26,000 으로 잘못 집계."
    )


# ===========================================================================
# S6 (사이클 53.1) — 운영 부피 18,000건 시나리오 drained 정확 집계
# ===========================================================================
def _build_18000_logs_with_drained_at_7668() -> list[dict]:
    """18,000건 system_logs 생성. position 7668 (사이클 53 실측 위치) 에 drained success 1건.

    Red 검증 의도: 사이클 53 페이지네이션 구조는 작동하지만 `generate_daily_log_report` 가
    `_fetch_logs_in_range(start, now)` 호출 시 `limit` 인자 생략 → 디폴트 `limit=5000`
    → 5페이지 cap = 5000건만 fetch → 7668번 drained 누락.

    Green: 호출 측 `_fetch_logs_in_range(start_kst, now_kst, limit=30000)` 명시 (또는
    디폴트 5000 → 30000 상향). 운영 부피 18,000 × 1.6배 마진.
    """
    logs: list[dict] = []
    for i in range(18000):
        # idx 분포: 0~17999, 분 단위 wrap 으로 timestamp 생성 (정렬 안정성)
        ts_min = i % 60
        ts_hour = (i // 60) % 24
        ts = f"2026-06-01T{ts_hour:02d}:{ts_min:02d}:00+09:00"
        if i == 7668:
            msg = (
                "[next_day_clear_drained] ticker=064400 strategy=momentum "
                "result=success elapsed_ms=56"
            )
            logs.append({"timestamp": ts, "log_level": "INFO", "message": msg})
        else:
            logs.append({"timestamp": ts, "log_level": "INFO", "message": f"운영 로그 {i}"})
    return logs


@pytest.mark.asyncio
async def test_s6_when_18000_logs_then_generate_report_counts_drained_at_7668(
    monkeypatch: pytest.MonkeyPatch,
):
    """결함 차단 (사이클 53.1): 운영 실측 18,435건/일 부피 시나리오에서
    `generate_daily_log_report` 가 ASC 7668번 위치의 drained success 1건을 정확 카운트.

    실측 사고 (2026-06-01 자동 리포트):
    - 사이클 53 시정 후 페이지네이션 구조 + KST timezone 모두 OK
    - 그러나 `generate_daily_log_report` 의 `_fetch_logs_in_range(start, now)` 호출이
      `limit` 생략 → 디폴트 `limit=5000` → 5페이지 cap = 5000건만 fetch
    - 운영 부피 18,435건/일 → 7668번 위치 drained 누락 → `drained_success=0` 잔존

    Green 명세 (호출 측 명시 권장):
    - `_fetch_logs_in_range(start_kst, now_kst, limit=30000)` 명시
    - 또는 디폴트 `limit=5000` → `limit=30000` 자체 상향
    - 운영 부피 18,000 × 1.6배 마진. PostgREST 한도 1000 페이지의 30페이지 fetch
    """
    # --- system_logs mock (18,000건, idx=7668 에 drained) ---
    logs_rows = _build_18000_logs_with_drained_at_7668()
    fake_logs_supabase = _FakeRangeSupabase(logs_rows)
    monkeypatch.setattr(lae, "supabase", fake_logs_supabase)

    # --- trade_history mock (S5 와 동일한 5건 재활용) ---
    trades_rows = [
        {
            "ticker": "064400",
            "ticker_name": "LG씨엔에스",
            "trade_type": "SELL",
            "price": 5_900,
            "quantity": 100,
            "status": "COMPLETED",
            "strategy": "momentum",
            "profit_loss": 30_100,
            "timestamp": "2026-05-31T23:20:00+00:00",
        },
        {
            "ticker": "AAAAAA",
            "trade_type": "SELL",
            "price": 10_000,
            "quantity": 10,
            "status": "COMPLETED",
            "strategy": "volatility_breakout",
            "profit_loss": 6_000,
            "timestamp": "2026-06-01T00:30:00+00:00",
        },
        {
            "ticker": "BBBBBB",
            "trade_type": "SELL",
            "price": 20_000,
            "quantity": 5,
            "status": "COMPLETED",
            "strategy": "volatility_breakout",
            "profit_loss": 5_000,
            "timestamp": "2026-06-01T02:00:00+00:00",
        },
        {
            "ticker": "CCCCCC",
            "trade_type": "SELL",
            "price": 15_000,
            "quantity": 8,
            "status": "COMPLETED",
            "strategy": "volatility_breakout",
            "profit_loss": 8_000,
            "timestamp": "2026-06-01T04:00:00+00:00",
        },
        {
            "ticker": "DDDDDD",
            "trade_type": "SELL",
            "price": 8_000,
            "quantity": 20,
            "status": "COMPLETED",
            "strategy": "volatility_breakout",
            "profit_loss": 7_000,
            "timestamp": "2026-06-01T06:20:00+00:00",
        },
    ]
    fake_trades_supabase = _FakeTradesSupabase(trades_rows)
    monkeypatch.setattr(trade_history, "supabase", fake_trades_supabase)

    # --- OpenAI / insert / strategy_funnel / api_metrics mock ---
    captured_metrics: dict = {}

    async def _fake_call_openai(metrics: dict) -> dict:
        captured_metrics["metrics"] = metrics
        return {"summary": "test", "findings": []}

    async def _fake_insert(*_args, **_kwargs):
        return {"id": "row-1"}

    async def _empty_funnel() -> dict:
        return {}

    monkeypatch.setattr(lae, "_call_openai", _fake_call_openai)
    monkeypatch.setattr(lae, "insert_log_report", _fake_insert)
    monkeypatch.setattr(lae, "_collect_strategy_funnel", _empty_funnel)
    monkeypatch.setattr(lae.settings, "openai_api_key", "dummy-key")
    monkeypatch.setattr(lae, "get_request_metrics", lambda: {})
    monkeypatch.setattr(lae, "reset_request_metrics", lambda: None)

    # 날짜 고정 — target_date=2026-06-01
    _fixed_now_kst = datetime(2026, 6, 1, 20, 10, 0, tzinfo=KST)
    await lae.generate_daily_log_report(_now_kst=_fixed_now_kst)

    metrics = captured_metrics.get("metrics")
    assert metrics is not None, "generate_daily_log_report 가 _call_openai 호출 안 함"

    # 핵심 1: total_logs >= 18,000 — 페이지네이션이 운영 부피 완전 fetch
    logs_metrics = metrics.get("logs", {})
    total_logs = logs_metrics.get("total_logs", 0)
    assert total_logs >= 18_000, (
        f"운영 부피 결함 (사이클 53.1): total_logs={total_logs} (기대 ≥18,000). "
        f"`generate_daily_log_report` 의 `_fetch_logs_in_range(start, now)` 호출이 "
        f"`limit` 생략 → 디폴트 `limit=5000` → 5페이지 cap. "
        f"Green: 호출 측 `limit=30000` 명시 또는 디폴트 상향."
    )

    # 핵심 2: drained_success=1 — 7668번 위치 drained 정확 포착
    ndc = metrics.get("next_day_clear", {})
    assert ndc.get("drained_success") == 1, (
        f"잔여 결함 (사이클 53.1): drained_success={ndc.get('drained_success')} "
        f"(기대 1). 운영 실측 — idx=7668 의 drained 가 limit=5000 cap 으로 미진입. "
        f"total_logs={total_logs}. 사이클 53 페이지네이션 구조는 OK 인데 호출 측 "
        f"`limit` 인자가 운영 부피 부족."
    )
