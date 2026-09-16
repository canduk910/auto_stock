"""cycle285 — `GET /api/market-ops` 야간작업 현황 라우트 계약.

정본 = 프롬프트 §반드시 지킬 것(4-1~4-5) + 사이클 285 조사 결과.

## 검증 대상

1. 상태 전수 — `scheduled`/`running`/`done`/`failed`/`skipped_fresh`/`skipped_weekly`/
   `overwritten`/`holiday`/`unknown` 이 각 재료 조합에서 정확히 나온다.
2. 휴장일(`is_trading_day=False`) → 전 작업 `holiday`(§4-4 확장 — "실패로 보이면
   안 된다").
3. 휴장 여부 확인 불가(`is_trading_day=None`) → 증거 없는 `not_fired` 만 `unknown`
   으로 바뀌고, 이미 증거로 증명된 `done`/`scheduled`/`skipped_*` 는 그대로다
   (있는 사실을 숨기지 않는다).
4. 각 데이터 소스(마커/진행률/집계쿼리/log_report/trading_day/engine) 가 개별
   실패해도 응답은 여전히 200 이고 `evidence_errors` 에 그 소스가 기록된다
   (never-raise + 섹션별 graceful degrade).
5. 시각은 `scheduler.TIME_*` 에서만 읽는다 — 응답의 `scheduled_at` 문자열이 그
   상수와 일치한다.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.unit

_KST = timezone(timedelta(hours=9))
PATH = "/api/market-ops"

_EXPECTED_TASK_IDS = {
    "stock_master_basics_refresh",
    "stock_master_daily_purge",
    "evening_funnel_capture",
    "stock_master_master_load",
    "stock_master_financial_load",
    "quote_token_refresh",
    "nxt_post_buy_stop",
    "recommendation",
    "full_universe_load",
    "metrics_snapshot",
    "cloud_report_routine",
    "stock_master_daily_load",
    "settlement",
    "log_analysis",
}

_IDLE_PROGRESS = {
    "status": "idle", "total": 0, "processed": 0, "updated": 0, "skipped": 0,
    "failed": 0, "started_at": None, "finished_at": None, "elapsed_ms": 0,
    "error_message": None,
}

_EMPTY_COMBINED = {
    "rec_rows": 0, "rec_last_at": None, "perf_rows": 0, "daily_head": None,
    "daily_today_rows": 0, "daily_tail": None, "funnel_rows": 0,
    "funnel_last_at": None, "sm_refreshed_last": None, "sm_master_last": None,
}


@pytest.fixture
def client():
    from src.main import app

    return TestClient(app)


@pytest.fixture
def mo(monkeypatch):
    """모듈을 반환하며 기본 목(early-morning, 정상 개장, 증거 0)을 깐다."""
    import src.routes.market_ops as _mo

    monkeypatch.setattr(_mo, "_resolve_trading_day", AsyncMock(return_value=(True, "kis")))
    monkeypatch.setattr(
        _mo.system_config, "get_task_last_success_bulk", AsyncMock(return_value={})
    )
    monkeypatch.setattr(
        _mo.refresh_progress,
        "get_all_progress",
        lambda: {k: dict(_IDLE_PROGRESS) for k in ("universe", "basics", "daily", "master", "financial")},
    )
    monkeypatch.setattr(_mo.pg, "fetchrow", AsyncMock(return_value=dict(_EMPTY_COMBINED)))
    monkeypatch.setattr(_mo, "get_log_report", AsyncMock(return_value=None))
    monkeypatch.setattr(_mo.trading_scheduler, "_running", False, raising=False)
    monkeypatch.setattr(_mo.trading_scheduler, "_phase", "idle", raising=False)
    return _mo


def _at(client, moment: datetime, expect: int = 200):
    import src.routes.market_ops as _mo

    frozen = moment

    class _FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return frozen

    orig = _mo.datetime
    _mo.datetime = _FrozenDatetime
    try:
        res = client.get(PATH)
    finally:
        _mo.datetime = orig
    assert res.status_code == expect, f"{res.status_code} != {expect}: {res.text[:300]}"
    return res.json()["data"]


# ===========================================================================
# G0 — 라우트 존재 + 응답 골격
# ===========================================================================
def test_g0_route_registered_and_top_level_shape(client, mo):
    data = _at(client, datetime(2026, 9, 14, 1, 0, tzinfo=_KST))
    assert set(data) == {
        "as_of_kst", "is_trading_day", "trading_day_source", "engine", "tasks",
        "evidence_errors",
    }
    assert {t["id"] for t in data["tasks"]} == _EXPECTED_TASK_IDS
    assert len(data["tasks"]) == len(_EXPECTED_TASK_IDS), "task id 중복"


def test_g0b_every_task_row_has_the_contract_keys(client, mo):
    data = _at(client, datetime(2026, 9, 14, 1, 0, tzinfo=_KST))
    for t in data["tasks"]:
        assert set(t) == {
            "id", "label_ko", "scheduled_at", "status", "last_success_at",
            "evidence", "note",
        }


# ===========================================================================
# G1 — 시각 이전 = 전부 scheduled, 시각은 scheduler.TIME_* 에서 읽는다
# ===========================================================================
def test_g1_all_scheduled_before_any_time_fires(client, mo):
    data = _at(client, datetime(2026, 9, 14, 0, 30, tzinfo=_KST))
    by_id = {t["id"]: t for t in data["tasks"]}
    for tid in _EXPECTED_TASK_IDS - {"cloud_report_routine"}:
        assert by_id[tid]["status"] == "scheduled", f"{tid}: {by_id[tid]}"
    assert by_id["cloud_report_routine"]["scheduled_at"] is None
    assert by_id["cloud_report_routine"]["status"] == "unknown"


def test_g1b_scheduled_at_matches_scheduler_constants(client, mo):
    from src.engine import scheduler as sched
    from src.engine.quote_token_refresh import TIME_QUOTE_TOKEN_REFRESH

    data = _at(client, datetime(2026, 9, 14, 0, 30, tzinfo=_KST))
    by_id = {t["id"]: t for t in data["tasks"]}

    def hms(t):
        return t.strftime("%H:%M") if t.second == 0 else t.strftime("%H:%M:%S")

    assert by_id["stock_master_basics_refresh"]["scheduled_at"] == hms(
        sched.TIME_STOCK_MASTER_BASICS_REFRESH
    )
    assert by_id["stock_master_daily_load"]["scheduled_at"] == hms(
        sched.TIME_STOCK_MASTER_DAILY_LOAD
    )
    assert by_id["settlement"]["scheduled_at"] == hms(sched.TIME_SETTLEMENT)
    assert by_id["quote_token_refresh"]["scheduled_at"] == hms(TIME_QUOTE_TOKEN_REFRESH)
    assert by_id["full_universe_load"]["scheduled_at"] == hms(sched.TIME_FULL_UNIVERSE_LOAD)


# ===========================================================================
# G2 — 마커 없는 4 task 는 시각이 지나도 '실패'가 아니라 'unknown'
# ===========================================================================
def test_g2_markerless_tasks_never_report_failed(client, mo):
    data = _at(client, datetime(2026, 9, 14, 23, 59, tzinfo=_KST))
    by_id = {t["id"]: t for t in data["tasks"]}
    assert by_id["quote_token_refresh"]["status"] == "unknown"
    assert by_id["stock_master_daily_purge"]["status"] == "unknown"
    assert "failed" != by_id["quote_token_refresh"]["status"]


# ===========================================================================
# G3 — progress 기반 상태 전수 (running/done/skipped_fresh/failed/not_fired)
# ===========================================================================
def test_g3_progress_running_today(client, mo, monkeypatch):
    today_iso = "2026-09-14T16:05:00+09:00"
    prog = {k: dict(_IDLE_PROGRESS) for k in ("universe", "basics", "daily", "master", "financial")}
    prog["basics"] = {**_IDLE_PROGRESS, "status": "running", "started_at": today_iso}
    monkeypatch.setattr(mo.refresh_progress, "get_all_progress", lambda: prog)
    data = _at(client, datetime(2026, 9, 14, 16, 6, tzinfo=_KST))
    by_id = {t["id"]: t for t in data["tasks"]}
    assert by_id["stock_master_basics_refresh"]["status"] == "running"


def test_g3b_progress_done_today(client, mo, monkeypatch):
    today_iso = "2026-09-14T16:12:00+09:00"
    prog = {k: dict(_IDLE_PROGRESS) for k in ("universe", "basics", "daily", "master", "financial")}
    prog["basics"] = {
        **_IDLE_PROGRESS, "status": "completed", "started_at": today_iso,
        "finished_at": today_iso, "total": 100, "updated": 100,
    }
    monkeypatch.setattr(mo.refresh_progress, "get_all_progress", lambda: prog)
    data = _at(client, datetime(2026, 9, 14, 16, 13, tzinfo=_KST))
    by_id = {t["id"]: t for t in data["tasks"]}
    assert by_id["stock_master_basics_refresh"]["status"] == "done"


def test_g3c_progress_failed_today(client, mo, monkeypatch):
    today_iso = "2026-09-14T16:12:00+09:00"
    prog = {k: dict(_IDLE_PROGRESS) for k in ("universe", "basics", "daily", "master", "financial")}
    prog["basics"] = {
        **_IDLE_PROGRESS, "status": "failed", "started_at": today_iso,
        "finished_at": today_iso, "error_message": "KIS 타임아웃",
    }
    monkeypatch.setattr(mo.refresh_progress, "get_all_progress", lambda: prog)
    data = _at(client, datetime(2026, 9, 14, 16, 13, tzinfo=_KST))
    by_id = {t["id"]: t for t in data["tasks"]}
    assert by_id["stock_master_basics_refresh"]["status"] == "failed"
    assert by_id["stock_master_basics_refresh"]["evidence"]["error_message"] == "KIS 타임아웃"


def test_g3d_progress_skipped_fresh(client, mo, monkeypatch):
    today_iso = "2026-09-14T20:32:00+09:00"
    prog = {k: dict(_IDLE_PROGRESS) for k in ("universe", "basics", "daily", "master", "financial")}
    prog["daily"] = {
        **_IDLE_PROGRESS, "status": "completed", "started_at": today_iso,
        "finished_at": today_iso, "total": 1000, "skipped": 1000, "updated": 0,
    }
    monkeypatch.setattr(mo.refresh_progress, "get_all_progress", lambda: prog)
    data = _at(client, datetime(2026, 9, 14, 20, 35, tzinfo=_KST))
    by_id = {t["id"]: t for t in data["tasks"]}
    assert by_id["stock_master_daily_load"]["status"] == "skipped_fresh"


def test_g3e_stale_yesterday_progress_is_not_fired_not_done(client, mo, monkeypatch):
    """§3 조사 발견 — `refresh_progress` 는 일일 초기화가 없다. 어제 값이 오늘
    '완료' 로 오독되면 안 된다."""
    yesterday_iso = "2026-09-13T16:12:00+09:00"
    prog = {k: dict(_IDLE_PROGRESS) for k in ("universe", "basics", "daily", "master", "financial")}
    prog["basics"] = {
        **_IDLE_PROGRESS, "status": "completed", "started_at": yesterday_iso,
        "finished_at": yesterday_iso, "total": 100, "updated": 100,
    }
    monkeypatch.setattr(mo.refresh_progress, "get_all_progress", lambda: prog)
    data = _at(client, datetime(2026, 9, 14, 18, 0, tzinfo=_KST))
    by_id = {t["id"]: t for t in data["tasks"]}
    assert by_id["stock_master_basics_refresh"]["status"] == "not_fired"


def test_g3f_marker_today_promotes_stale_progress_to_done(client, mo, monkeypatch):
    """재시작이 진행률 메모리를 비워도, 오늘자 마커가 있으면 done 이다."""
    monkeypatch.setattr(
        mo.system_config,
        "get_task_last_success_bulk",
        AsyncMock(return_value={"stock_master_basics_refresh": "2026-09-14T16:12:00+09:00"}),
    )
    data = _at(client, datetime(2026, 9, 14, 18, 0, tzinfo=_KST))
    by_id = {t["id"]: t for t in data["tasks"]}
    assert by_id["stock_master_basics_refresh"]["status"] == "done"


# ===========================================================================
# G4 — 주 1회 게이트(재무 적재)
# ===========================================================================
def test_g4_weekly_gate_within_168h_is_not_a_failure(client, mo, monkeypatch):
    monkeypatch.setattr(
        mo.system_config,
        "get_task_last_success_bulk",
        AsyncMock(return_value={"stock_master_financial_load": "2026-09-10T16:40:00+09:00"}),
    )
    data = _at(client, datetime(2026, 9, 14, 17, 0, tzinfo=_KST))
    by_id = {t["id"]: t for t in data["tasks"]}
    assert by_id["stock_master_financial_load"]["status"] == "skipped_weekly"


def test_g4b_weekly_gate_expired_is_not_fired(client, mo, monkeypatch):
    monkeypatch.setattr(
        mo.system_config,
        "get_task_last_success_bulk",
        AsyncMock(return_value={"stock_master_financial_load": "2026-09-01T16:40:00+09:00"}),
    )
    data = _at(client, datetime(2026, 9, 14, 17, 0, tzinfo=_KST))
    by_id = {t["id"]: t for t in data["tasks"]}
    assert by_id["stock_master_financial_load"]["status"] == "not_fired"


# ===========================================================================
# G5 — metrics_snapshot 3구간 (§4-4 확장)
# ===========================================================================
def test_g5_metrics_snapshot_pass_true(client, mo, monkeypatch):
    """실제 저장 값은 정수 `1` 이다(`daily_metrics_snapshot.py`) — `is True` 항등
    비교로 되돌리면 이 케이스가 영원히 실패로 조용히 오분류된다."""
    monkeypatch.setattr(
        mo, "get_log_report",
        AsyncMock(return_value={"metrics": {"snapshot_pass": 1}, "summary": "", "model": None}),
    )
    data = _at(client, datetime(2026, 9, 14, 20, 10, tzinfo=_KST))
    by_id = {t["id"]: t for t in data["tasks"]}
    assert by_id["metrics_snapshot"]["status"] == "done"


def test_g5b_metrics_snapshot_pass_false(client, mo, monkeypatch):
    monkeypatch.setattr(
        mo, "get_log_report",
        AsyncMock(return_value={"metrics": {"snapshot_pass": False}, "summary": "", "model": None}),
    )
    data = _at(client, datetime(2026, 9, 14, 20, 10, tzinfo=_KST))
    by_id = {t["id"]: t for t in data["tasks"]}
    assert by_id["metrics_snapshot"]["status"] == "failed"


def test_g5c_metrics_snapshot_overwritten_after_settlement(client, mo, monkeypatch):
    """21:30 완전판이 `snapshot_pass` 키를 지운다 — 그 뒤에는 'overwritten' 이 정상."""
    monkeypatch.setattr(
        mo, "get_log_report",
        AsyncMock(return_value={
            "metrics": {"api_metrics": {}}, "summary": "오늘 요약", "model": "gpt-5.6",
        }),
    )
    data = _at(client, datetime(2026, 9, 14, 21, 45, tzinfo=_KST))
    by_id = {t["id"]: t for t in data["tasks"]}
    assert by_id["metrics_snapshot"]["status"] == "overwritten"
    # settlement 자체는 metrics_snapshot 과 무관한 별도 산출물(perf_rows) 판정 —
    # 기본 목은 0행이라 21:30 을 지난 지금 not_fired 가 정확하다(교차 오염 없음 확인).
    assert by_id["settlement"]["status"] == "not_fired"


def test_g5d_metrics_snapshot_no_row_yet_is_not_fired(client, mo):
    data = _at(client, datetime(2026, 9, 14, 20, 10, tzinfo=_KST))
    by_id = {t["id"]: t for t in data["tasks"]}
    assert by_id["metrics_snapshot"]["status"] == "not_fired"


# ===========================================================================
# G6 — log_analysis: OpenAI 빈 응답 placeholder → failed (오분류 차단)
# ===========================================================================
def test_g6_log_analysis_openai_empty_is_failed_not_done(client, mo, monkeypatch):
    from src.engine.log_analysis_engine import OPENAI_EMPTY_RESPONSE_SUMMARY

    monkeypatch.setattr(
        mo, "get_log_report",
        AsyncMock(return_value={
            "metrics": None, "summary": OPENAI_EMPTY_RESPONSE_SUMMARY, "model": "gpt-5.6",
        }),
    )
    data = _at(client, datetime(2026, 9, 14, 21, 45, tzinfo=_KST))
    by_id = {t["id"]: t for t in data["tasks"]}
    assert by_id["log_analysis"]["status"] == "failed"


def test_g6b_log_analysis_complete_report_is_done(client, mo, monkeypatch):
    monkeypatch.setattr(
        mo, "get_log_report",
        AsyncMock(return_value={
            "metrics": {"api_metrics": {}}, "summary": "오늘 요약", "model": "gpt-5.6",
        }),
    )
    data = _at(client, datetime(2026, 9, 14, 21, 45, tzinfo=_KST))
    by_id = {t["id"]: t for t in data["tasks"]}
    assert by_id["log_analysis"]["status"] == "done"
    assert by_id["log_analysis"]["evidence"]["has_api_metrics"] is True


# ===========================================================================
# G7 — placeholder 20:20 루틴 행 (upsert_external_report INSERT 경로)
# ===========================================================================
def test_g7_cloud_routine_placeholder_row_is_not_done(client, mo, monkeypatch):
    """20:20 루틴이 만드는 placeholder 행(`summary=''`)은 완료가 아니다."""
    monkeypatch.setattr(
        mo, "get_log_report",
        AsyncMock(return_value={
            "metrics": {}, "summary": "", "model": None, "ext_provider": None,
            "ext_created_at": None,
        }),
    )
    data = _at(client, datetime(2026, 9, 14, 20, 25, tzinfo=_KST))
    by_id = {t["id"]: t for t in data["tasks"]}
    assert by_id["cloud_report_routine"]["status"] == "unknown"


def test_g7b_cloud_routine_done_when_ext_created_at_present(client, mo, monkeypatch):
    monkeypatch.setattr(
        mo, "get_log_report",
        AsyncMock(return_value={
            "metrics": {}, "summary": "요약", "model": "gpt", "ext_provider": "openai",
            "ext_created_at": "2026-09-14T20:34:00+09:00",
        }),
    )
    data = _at(client, datetime(2026, 9, 14, 20, 40, tzinfo=_KST))
    by_id = {t["id"]: t for t in data["tasks"]}
    assert by_id["cloud_report_routine"]["status"] == "done"


# ===========================================================================
# G8 — 휴장일: 전부 holiday (§4-4)
# ===========================================================================
#: 이 세 행은 raw 상태가 **literally** `not_fired`/`scheduled` 가 아니다(`_no_evidence_status`
#: 는 "unknown", `_milestone_status` 는 시각이 지나면 "done") — 그래서 §4-4 시정
#: (holiday 치환을 not_fired/scheduled 로 좁힌 것) 아래에서는 휴장과 무관하게 그
#: 값을 그대로 유지한다. "이미 증명된 사실은 휴장 여부와 무관하게 보존한다" 는
#: 원칙이 "증거가 아예 없다는 사실" 에도 똑같이 적용된다 — 마커·산출물이 아예 없는
#: 작업이라는 사실은 휴장이라고 사라지지 않는다.
#: cycle296 — 토큰 강제 재발급 시각은 `quote_token_refresh` 정본에서만 읽는다(리터럴 금지).
from src.engine.quote_token_refresh import TIME_QUOTE_TOKEN_REFRESH as _QUOTE_T

_HOLIDAY_EXEMPT = {
    "cloud_report_routine": "unknown",
    "stock_master_daily_purge": "unknown",
    "quote_token_refresh": "unknown",
    "nxt_post_buy_stop": "done",
}


def test_g8_holiday_overrides_every_task(client, mo, monkeypatch):
    """휴장 확정이면 **아직 증거가 없는**(`not_fired`/`scheduled`) 행만 `holiday` 로
    바뀐다(cycle285 검증 honest 렌즈 MEDIUM #2 시정) — 이미 증명된 사실(그리고 "증거
    자체가 없다" 는 사실)은 휴장 여부와 무관하게 보존한다."""
    monkeypatch.setattr(mo, "_resolve_trading_day", AsyncMock(return_value=(False, "kis")))
    # ⚠️ cycle296 (2026-09-17) — `quote_token_refresh` 기대값은 **T 에 따라 달라진다**.
    #   `_HOLIDAY_EXEMPT` 의 `unknown` 세 행은 "마커가 아예 없다" 가 아니라 **"예정 시각이
    #   이미 지났는데 증거가 없다"**(`_no_evidence_status`)일 때만 unknown 이다. 예정 시각
    #   **전**이면 `scheduled` 이고, 그건 §4-4 설계상 휴장 치환 대상이 맞다.
    #   토큰 강제 재발급 T 가 19:00 → 20:45 로 옮겨지면서 이 조회 시각(20:30)이 T 앞이 된다.
    #   조회 시각을 전부 뒤(23:00)로 미는 방법은 `metrics_snapshot` 의 판정을 함께 흔들어
    #   이 가드의 다른 행을 망가뜨린다(실측) — 그래서 **그 한 행만 T 로 계산**한다.
    at = datetime(2026, 9, 13, 20, 30, tzinfo=_KST)
    expected = dict(_HOLIDAY_EXEMPT)
    if at.timetz() < _QUOTE_T.replace(tzinfo=_KST):
        expected["quote_token_refresh"] = "holiday"
    data = _at(client, at)
    assert data["is_trading_day"] is False
    by_id = {t["id"]: t for t in data["tasks"]}
    for tid, t in by_id.items():
        if tid in expected:
            assert t["status"] == expected[tid], t
        else:
            assert t["status"] == "holiday", t


def test_g8a_status_of_a_markerless_task_flips_at_its_scheduled_time(client, mo):
    """G8-a(cycle296 신설) — 마커 없는 행의 상태는 **예정 시각을 경계로** 갈린다.

    `scheduled`(시각 전) → `unknown`(시각 후). 위 G8 의 `_HOLIDAY_EXEMPT` 가 "이 행은
    언제 물어도 unknown" 이라는 뜻으로 오독되지 않도록 경계 자체를 잰다 — T 를 옮기는
    사이클은 이 경계도 함께 옮긴다(cycle296 이 19:00 → 20:45).

    양성 대조군 = 두 상태가 **실제로 다르다**(둘 다 같은 값이면 경계가 사라진 것).
    """
    base = datetime(2026, 9, 14, tzinfo=_KST)
    t_dt = base.replace(hour=_QUOTE_T.hour, minute=_QUOTE_T.minute)
    before = {t["id"]: t for t in _at(client, t_dt - timedelta(minutes=15))["tasks"]}
    after = {t["id"]: t for t in _at(client, t_dt + timedelta(minutes=30))["tasks"]}

    assert before["quote_token_refresh"]["status"] == "scheduled"
    assert after["quote_token_refresh"]["status"] == "unknown"
    assert before["quote_token_refresh"]["status"] != after["quote_token_refresh"]["status"]


def test_g8b_holiday_even_with_leftover_evidence(client, mo, monkeypatch):
    """휴장일에 어제 자료가 evidence 에 남아 있어도 status 는 holiday 다(§4-4)."""
    monkeypatch.setattr(mo, "_resolve_trading_day", AsyncMock(return_value=(False, "kis")))
    monkeypatch.setattr(
        mo.system_config,
        "get_task_last_success_bulk",
        AsyncMock(return_value={"stock_master_basics_refresh": "2026-09-11T16:12:00+09:00"}),
    )
    data = _at(client, datetime(2026, 9, 13, 20, 30, tzinfo=_KST))
    by_id = {t["id"]: t for t in data["tasks"]}
    assert by_id["stock_master_basics_refresh"]["status"] == "holiday"


# ===========================================================================
# G9 — 휴장 여부 확인 불가: 증거 없는 not_fired 만 unknown, 증거 있는 done 은 보존
# ===========================================================================
def test_g9_unknown_trading_day_only_reclassifies_not_fired(client, mo, monkeypatch):
    monkeypatch.setattr(mo, "_resolve_trading_day", AsyncMock(return_value=(None, "unknown")))
    monkeypatch.setattr(
        mo.system_config,
        "get_task_last_success_bulk",
        AsyncMock(return_value={"stock_master_basics_refresh": "2026-09-14T16:12:00+09:00"}),
    )
    data = _at(client, datetime(2026, 9, 14, 18, 0, tzinfo=_KST))
    by_id = {t["id"]: t for t in data["tasks"]}
    # 증거(오늘자 마커)가 있으니 done 이 유지된다 — "모른다" 가 "있는 사실" 을 지우지 않는다.
    assert by_id["stock_master_basics_refresh"]["status"] == "done"
    # 증거가 없는 다른 지난 시각 작업은 unknown 으로 낮춰진다.
    assert by_id["stock_master_master_load"]["status"] == "unknown"
    # 아직 시각이 안 지난 작업은 여전히 scheduled.
    assert by_id["stock_master_daily_load"]["status"] == "scheduled"


# ===========================================================================
# G10 — never-raise: 데이터 소스별 개별 실패는 200 + evidence_errors 로만 남는다
# ===========================================================================
@pytest.mark.parametrize(
    "attr, target",
    [
        ("trading_day", None),
        ("markers", None),
        ("progress", None),
        ("artifacts", None),
        ("log_report", None),
    ],
)
def test_g10_each_source_failure_is_graceful(client, mo, monkeypatch, attr, target):
    if attr == "trading_day":
        monkeypatch.setattr(mo, "_resolve_trading_day", AsyncMock(side_effect=RuntimeError("boom")))
    elif attr == "markers":
        monkeypatch.setattr(
            mo.system_config, "get_task_last_success_bulk", AsyncMock(side_effect=RuntimeError("boom"))
        )
    elif attr == "progress":
        def _raise():
            raise RuntimeError("boom")

        monkeypatch.setattr(mo.refresh_progress, "get_all_progress", _raise)
    elif attr == "artifacts":
        monkeypatch.setattr(mo.pg, "fetchrow", AsyncMock(side_effect=RuntimeError("boom")))
    elif attr == "log_report":
        monkeypatch.setattr(mo, "get_log_report", AsyncMock(side_effect=RuntimeError("boom")))

    data = _at(client, datetime(2026, 9, 14, 18, 0, tzinfo=_KST), expect=200)
    assert attr in data["evidence_errors"]
    assert len(data["tasks"]) == len(_EXPECTED_TASK_IDS)


def test_g10b_all_sources_failing_at_once_still_200(client, mo, monkeypatch):
    monkeypatch.setattr(mo, "_resolve_trading_day", AsyncMock(side_effect=RuntimeError("a")))
    monkeypatch.setattr(
        mo.system_config, "get_task_last_success_bulk", AsyncMock(side_effect=RuntimeError("b"))
    )

    def _raise():
        raise RuntimeError("c")

    monkeypatch.setattr(mo.refresh_progress, "get_all_progress", _raise)
    monkeypatch.setattr(mo.pg, "fetchrow", AsyncMock(side_effect=RuntimeError("d")))
    monkeypatch.setattr(mo, "get_log_report", AsyncMock(side_effect=RuntimeError("e")))
    data = _at(client, datetime(2026, 9, 14, 18, 0, tzinfo=_KST), expect=200)
    assert set(data["evidence_errors"]) == {
        "trading_day", "markers", "progress", "artifacts", "log_report",
    }
    # trading_day 조회 자체가 실패 → None 유지 → not_fired 만 unknown 으로.
    assert data["is_trading_day"] is None


# ===========================================================================
# G11 — 엔진 상태(§5 조사 헤드 정보) 노출
# ===========================================================================
def test_g11_engine_block_reflects_scheduler_state(client, mo, monkeypatch):
    monkeypatch.setattr(mo.trading_scheduler, "_running", True, raising=False)
    monkeypatch.setattr(mo.trading_scheduler, "_phase", "main_trading", raising=False)
    monkeypatch.setattr(
        mo.system_config,
        "get_task_last_success_bulk",
        AsyncMock(return_value={"engine_alive_heartbeat": "2026-09-14T18:00:00+09:00"}),
    )
    data = _at(client, datetime(2026, 9, 14, 18, 0, tzinfo=_KST))
    assert data["engine"] == {
        "running": True, "phase": "main_trading",
        "heartbeat_at": "2026-09-14T18:00:00+09:00",
    }


# ===========================================================================
# G12 — 적대 검증 시정: 예정 시각보다 몇 시간 이른 "오늘" 증거는 그 행의 답이 아니다
# (HIGH #2/#3 test 렌즈 + MEDIUM #2 scope 렌즈)
# ===========================================================================
def test_g12_full_universe_boot_immediate_run_does_not_fake_2005_done(client, mo, monkeypatch):
    """`full_universe_load` 는 신선도 게이트가 없어 매일 07:5x 부팅 즉시실행이 도는데,
    그 완료 증거가 20:00:05 예정 실행의 '완료' 로 오인되면 안 된다(HIGH #2 재현)."""
    boot_iso = "2026-09-14T07:50:00+09:00"
    prog = {k: dict(_IDLE_PROGRESS) for k in ("universe", "basics", "daily", "master", "financial")}
    prog["universe"] = {
        **_IDLE_PROGRESS, "status": "completed", "started_at": boot_iso,
        "finished_at": boot_iso, "total": 3577, "updated": 120,
    }
    monkeypatch.setattr(mo.refresh_progress, "get_all_progress", lambda: prog)
    data = _at(client, datetime(2026, 9, 14, 10, 0, tzinfo=_KST))
    by_id = {t["id"]: t for t in data["tasks"]}
    assert by_id["full_universe_load"]["status"] == "scheduled"


def test_g12b_daily_load_catchup_marker_does_not_fake_2030_done_all_day(client, mo, monkeypatch):
    """전날 20:30 적재가 실패해 다음날 07:5x catch-up 이 쓴 마커가, 오늘 20:30 행을
    하루 종일 '완료' 로 보여주면 안 된다(HIGH #3 재현 — cycle283 D8 이 경계하는 사고
    를 이 화면이 오히려 가리는 결함)."""
    catchup_iso = "2026-09-14T07:55:00+09:00"
    monkeypatch.setattr(
        mo.system_config,
        "get_task_last_success_bulk",
        AsyncMock(return_value={"stock_master_daily_load": catchup_iso}),
    )
    data = _at(client, datetime(2026, 9, 14, 22, 0, tzinfo=_KST))
    by_id = {t["id"]: t for t in data["tasks"]}
    assert by_id["stock_master_daily_load"]["status"] == "not_fired"


def test_g12c_manual_refresh_before_scheduled_time_does_not_fake_done(client, mo, monkeypatch):
    """운영자가 16:10 예정 작업을 11:00 에 수동 새로고침 버튼으로 미리 돌려도, 그
    증거가 16:10 행을 아직 안 온 시각에 '완료' 로 보여주면 안 된다(scope MEDIUM #2)."""
    manual_iso = "2026-09-14T11:00:00+09:00"
    prog = {k: dict(_IDLE_PROGRESS) for k in ("universe", "basics", "daily", "master", "financial")}
    prog["basics"] = {
        **_IDLE_PROGRESS, "status": "completed", "started_at": manual_iso,
        "finished_at": manual_iso, "total": 2700, "updated": 2700,
    }
    monkeypatch.setattr(mo.refresh_progress, "get_all_progress", lambda: prog)
    data = _at(client, datetime(2026, 9, 14, 11, 30, tzinfo=_KST))
    by_id = {t["id"]: t for t in data["tasks"]}
    assert by_id["stock_master_basics_refresh"]["status"] == "scheduled"


def test_g12d_evidence_within_grace_window_still_counts(client, mo, monkeypatch):
    """예정 시각보다 살짝 이른 정상 지터(2시간 이내)까지 걸러내면 안 된다 — 관대한
    쪽 경계도 함께 잰다."""
    near_iso = "2026-09-14T14:30:00+09:00"  # 16:10 예정보다 1시간 40분 이르다
    prog = {k: dict(_IDLE_PROGRESS) for k in ("universe", "basics", "daily", "master", "financial")}
    prog["basics"] = {
        **_IDLE_PROGRESS, "status": "completed", "started_at": near_iso,
        "finished_at": near_iso, "total": 2700, "updated": 2700,
    }
    monkeypatch.setattr(mo.refresh_progress, "get_all_progress", lambda: prog)
    data = _at(client, datetime(2026, 9, 14, 15, 0, tzinfo=_KST))
    by_id = {t["id"]: t for t in data["tasks"]}
    assert by_id["stock_master_basics_refresh"]["status"] == "done"


# ===========================================================================
# G13 — 저녁 잠정 퍼널 캡처는 `is_provisional=TRUE` 산출물만 본다 (HIGH #1)
# ===========================================================================
def test_g13_combined_sql_filters_funnel_rows_by_is_provisional():
    """09:30 자동 캡처·스캐너 필터 훅(둘 다 `is_provisional=False`)이 16:20 저녁
    캡처의 '성공' 으로 오인되지 않는지는 실 SQL 문구로 잰다(라우트가 `pg.fetchrow`
    를 목으로 완전히 대체하는 단위 테스트라 SQL 자체는 여기서만 검증 가능하다 —
    실 PG 왕복은 `tests/integration/test_cycle285_market_ops_pg_roundtrip.py`)."""
    import src.routes.market_ops as mo

    sql = mo._COMBINED_SQL
    assert "strategy_funnel_snapshots" in sql
    # funnel_rows / funnel_last_at 서브쿼리 두 곳 모두 is_provisional 필터를 갖는다.
    funnel_clauses = [
        seg for seg in sql.split("SELECT") if "strategy_funnel_snapshots" in seg
    ]
    assert len(funnel_clauses) == 2, funnel_clauses
    for clause in funnel_clauses:
        assert "is_provisional = TRUE" in clause, clause


# ===========================================================================
# G14 — metrics_snapshot 'overwritten' 은 실재하는 완전판 증거를 요구한다 (HIGH, honest+test)
# ===========================================================================
def test_g14_overwritten_requires_a_real_complete_report_not_just_any_row(client, mo, monkeypatch):
    """20:20 클라우드 루틴이 만든 placeholder 행(`summary=""`, `model=None`)만
    있고 21:30 완전판 증거가 없는데도 '완료(최종반영)' 로 보이면 안 된다."""
    monkeypatch.setattr(
        mo, "get_log_report",
        AsyncMock(return_value={
            "metrics": {}, "summary": "", "model": None, "ext_created_at": None,
        }),
    )
    data = _at(client, datetime(2026, 9, 14, 22, 0, tzinfo=_KST))
    by_id = {t["id"]: t for t in data["tasks"]}
    assert by_id["metrics_snapshot"]["status"] == "unknown"


def test_g14b_overwritten_still_fires_when_the_complete_report_is_real(client, mo, monkeypatch):
    """진짜 완전판(summary+model 채워짐)이 있으면 여전히 'overwritten' 이다 —
    G14 시정이 정상 경로까지 막지 않는다는 회귀 방지."""
    monkeypatch.setattr(
        mo, "get_log_report",
        AsyncMock(return_value={
            "metrics": {"api_metrics": {}}, "summary": "오늘 요약", "model": "gpt-5.6",
        }),
    )
    data = _at(client, datetime(2026, 9, 14, 22, 0, tzinfo=_KST))
    by_id = {t["id"]: t for t in data["tasks"]}
    assert by_id["metrics_snapshot"]["status"] == "overwritten"


# ===========================================================================
# G15 — 경계 시각 정각 케이스 (test 렌즈 LOW #8 — 뮤테이션 `<`→`<=`/`>=`→`>` 방어)
# ===========================================================================
def test_g15_scheduled_boundary_exact_second_is_not_yet_fired(client, mo):
    """정각(예정 시각과 완전히 같은 순간)은 아직 '지나지 않은' 쪽이 아니다
    (`now_t < scheduled` 가 거짓이라 `not_fired` 로 떨어진다 — `scheduled` 로
    남는 것은 그 직전 1틱뿐)."""
    data = _at(client, datetime(2026, 9, 14, 16, 10, 0, tzinfo=_KST))
    by_id = {t["id"]: t for t in data["tasks"]}
    assert by_id["stock_master_basics_refresh"]["status"] == "not_fired"


def test_g15b_one_microsecond_before_boundary_is_still_scheduled(client, mo):
    data = _at(client, datetime(2026, 9, 14, 16, 9, 59, 999999, tzinfo=_KST))
    by_id = {t["id"]: t for t in data["tasks"]}
    assert by_id["stock_master_basics_refresh"]["status"] == "scheduled"


def test_g15c_settlement_boundary_exact_second_treats_overwritten_branch_as_active(client, mo, monkeypatch):
    """`now_t >= TIME_SETTLEMENT` 의 정각 경계 — 완전판 증거가 있으면 이 순간부터
    바로 `overwritten` 이어야 한다(`>` 로 뒤집히면 이 틱만 새는 뮤테이션을 잡는다)."""
    monkeypatch.setattr(
        mo, "get_log_report",
        AsyncMock(return_value={
            "metrics": {"api_metrics": {}}, "summary": "오늘 요약", "model": "gpt-5.6",
        }),
    )
    data = _at(client, datetime(2026, 9, 14, 21, 30, 0, tzinfo=_KST))
    by_id = {t["id"]: t for t in data["tasks"]}
    assert by_id["metrics_snapshot"]["status"] == "overwritten"


# ===========================================================================
# G16 — 주 1회 게이트: 미래 마커(시계 스큐)는 흡수하지 않는다 (test 렌즈 LOW #9)
# ===========================================================================
def test_g16_weekly_gate_future_marker_is_not_treated_as_freshly_skipped(client, mo, monkeypatch):
    """마커 시각이 `as_of` 보다 미래(시계 스큐·오기록)면 나이가 음수라 `skipped_weekly`
    로 흡수하지 않는다 — `0 <= age_h` 하한 가드가 실제로 방어하는지 잰다."""
    future_iso = "2026-09-15T09:00:00+09:00"  # as_of(09-14 17:00) 보다 미래
    monkeypatch.setattr(
        mo.system_config,
        "get_task_last_success_bulk",
        AsyncMock(return_value={"stock_master_financial_load": future_iso}),
    )
    data = _at(client, datetime(2026, 9, 14, 17, 0, tzinfo=_KST))
    by_id = {t["id"]: t for t in data["tasks"]}
    assert by_id["stock_master_financial_load"]["status"] != "skipped_weekly"
