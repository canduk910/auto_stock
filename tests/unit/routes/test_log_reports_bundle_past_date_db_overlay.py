"""C3 Red — 과거 날짜 log-reports 번들의 프로세스 스코프 3키 DB 오버레이.

## 배경 (`_workspace/reports/2026-09-25_day_decisions_and_cycles_352_366.md` §5-3)

09-23 백필 실행(09-25 16:28, `GET /api/log-reports/bundle?date=2026-09-23` 수동 호출 —
20:20 KST 클라우드 루틴의 과거일 백필 경로)이 `api_metrics`/`strategy_funnel`/
`portfolio_risk_snapshot` 3키를 **0(빈 값)** 으로 돌려줬다 — DB(`daily_log_reports`
09-23 행)에는 그날 20:05/21:30 이 이미 정확히 채워 둔 값이 있는데도.

## 원인

`collect_daily_log_metrics(target_date)` 는 이 3키를 **지금 이 프로세스**의 상태에서
읽는다 — `api_metrics = get_request_metrics()`(프로세스 전역 카운터, 정산 때 리셋),
`strategy_funnel = await _collect_strategy_funnel()`(레지스트리 `state.*_today` 인메모리
카운터, 자정 리셋), `portfolio_risk_snapshot`(현재 잔고·포지션 스냅샷). 셋 다 **오늘**
기준이라, 과거 날짜를 넘겨도 그 날짜로 필터링되지 않고 호출 시점(대개 그날과 무관한
0에 가까운 값)을 돌려준다. `src/routes/CLAUDE.md` 의 `_PROCESS_SCOPED_KEYS` 표식이
바로 이 사실을 표시하려던 것이다.

`generate_daily_log_report`(21:30 완전판)·`run_daily_metrics_snapshot`(20:05 1차
스냅샷)은 항상 **오늘** 날짜로만 이 함수를 부르므로 이 3키가 정확하다 — 그 값 그대로
`daily_log_reports.metrics` 에 저장된다. 즉 **과거 날짜의 정답은 이미 DB 에 있다.**

## 고침

`GET /api/log-reports/bundle?date=<과거>` 는 `collect_daily_log_metrics` 로 나머지
키(로그·거래·funnel 단계별 등 — 이미 `target_date` 필터링이라 정확하다)를 그대로 얻은
뒤, 그 날짜의 `daily_log_reports` 행이 있으면 3키만 그 행의 저장값으로 **덮어쓴다**.
행이 없거나·`metrics` 모양이 다르거나·DB 조회가 실패하면 **fail-open**(프로세스 값
유지, 번들 자체는 여전히 success=True) — 과거 값 복원 실패로 번들 전체가 죽으면 안
된다. **오늘 날짜 조회는 이 오버레이를 아예 시도하지 않는다**(byte 동일 보존 — 20:20
루틴의 매일 호출 경로 무변경, `test_cycle249_log_reports_bundle_external.py` E-1/E-2 와
공존).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from freezegun import freeze_time

pytestmark = pytest.mark.unit

KST = timezone(timedelta(hours=9))

BUNDLE = "/api/log-reports/bundle"

#: `collect_daily_log_metrics` 가 "지금 이 프로세스" 에서 만들어 낸 값 — 과거 날짜
#: 조회에서는 틀린 값이다(09-23 백필 실측을 흉내낸 표본: 3키가 비어 있다).
PROCESS_STATE_METRICS = {
    "target_date": "2026-09-23",
    "logs": {"total_logs": 7, "level_counts": {"WARNING": 2}},
    "trades": {"trades_total": 3},
    "api_metrics": {},
    "strategy_funnel": {},
    "strategy_funnel_stages": {"momentum": {"step1": 12}},
    "next_day_clear": {},
    "portfolio_risk_snapshot": None,
    "tick_blind": {"boot_count": 0},
}

#: 그날(09-23) 20:05/21:30 이 실제로 저장해 둔 `daily_log_reports.metrics` — 정답.
STORED_METRICS = {
    "target_date": "2026-09-23",
    "logs": {"total_logs": 999},  # 과거 값 오염 여부 확인용(오버레이가 이 키를 건드리면 안 된다)
    "api_metrics": {"total": 128, "errors": 3},
    "strategy_funnel": {"momentum": {"signals": 5, "orders": 2, "fills": 1}},
    "portfolio_risk_snapshot": {"total_open_risk_krw": 543_210},
}


def _routes():
    try:
        import src.routes.log_reports as mod
    except Exception as exc:  # pragma: no cover - Red 경로
        pytest.fail(f"Red — src/routes/log_reports.py import 실패: {exc!r}")
    return mod


def _client() -> TestClient:
    from src.main import app

    return TestClient(app)


class _Recorder:
    """호출 인자를 기록하는 async 대역."""

    def __init__(self, result=None, boom: BaseException | None = None):
        self.calls: list[tuple[tuple, dict]] = []
        self.result = result
        self.boom = boom

    async def __call__(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        if self.boom is not None:
            raise self.boom
        return self.result


def _patch_collect(monkeypatch, fake):
    import src.engine.log_analysis_engine as lae

    monkeypatch.setattr(lae, "collect_daily_log_metrics", fake, raising=False)
    mod = _routes()
    monkeypatch.setattr(mod, "collect_daily_log_metrics", fake)
    return fake


def _patch_get_log_report(monkeypatch, fake):
    import src.db.log_reports as db_mod

    monkeypatch.setattr(db_mod, "get_log_report", fake, raising=False)
    mod = _routes()
    if not hasattr(mod, "get_log_report"):
        pytest.fail("Red — src/routes/log_reports.py 에 모듈 레벨 `get_log_report` 가 없다")
    monkeypatch.setattr(mod, "get_log_report", fake)
    return fake


@freeze_time("2026-09-25 07:00:00")  # KST 16:00 — 09-25 백필 실측 시각대
def test_bundle_when_past_date_then_process_scoped_keys_overlaid_from_db(monkeypatch):
    """과거 날짜 번들은 3키를 DB 저장값으로 덮어쓴다(나머지 키는 그대로)."""
    collect = _patch_collect(monkeypatch, _Recorder(result=dict(PROCESS_STATE_METRICS)))
    get_report = _patch_get_log_report(
        monkeypatch,
        _Recorder(result={"target_date": date(2026, 9, 23), "metrics": STORED_METRICS}),
    )

    body = _client().get(BUNDLE, params={"date": "2026-09-23"}).json()

    assert body["success"] is True, body
    metrics = body["data"]["metrics"]
    assert metrics["api_metrics"] == {"total": 128, "errors": 3}, metrics["api_metrics"]
    assert metrics["strategy_funnel"] == {
        "momentum": {"signals": 5, "orders": 2, "fills": 1}
    }, metrics["strategy_funnel"]
    assert metrics["portfolio_risk_snapshot"] == {"total_open_risk_krw": 543_210}, metrics[
        "portfolio_risk_snapshot"
    ]
    # 3키 밖은 `collect_daily_log_metrics` 값 그대로 — DB 행의 `logs`(오염 표본)로
    # 덮이지 않는다(오버레이가 3키 스코프를 넘지 않는다는 것의 증거).
    assert metrics["logs"] == PROCESS_STATE_METRICS["logs"], metrics["logs"]
    assert metrics["strategy_funnel_stages"] == PROCESS_STATE_METRICS["strategy_funnel_stages"]

    assert len(collect.calls) == 1
    assert len(get_report.calls) == 1
    args, kwargs = get_report.calls[0]
    called_date = kwargs.get("target_date", args[0] if args else None)
    assert called_date == date(2026, 9, 23), get_report.calls


@freeze_time("2026-09-25 07:00:00")
def test_bundle_when_today_then_db_overlay_not_attempted(monkeypatch):
    """오늘 날짜 조회는 DB 오버레이를 시도하지 않는다 — byte 동일 보존.

    프로세스 값이 이미 정확한 오늘 조회에서까지 DB 를 왕복하면 20:20 루틴의 매일
    호출 경로에 불필요한 지연·장애점이 하나 더 생긴다.
    """
    today_metrics = dict(PROCESS_STATE_METRICS)
    today_metrics["target_date"] = "2026-09-25"
    _patch_collect(monkeypatch, _Recorder(result=today_metrics))
    get_report = _patch_get_log_report(monkeypatch, _Recorder(result=None))

    body = _client().get(BUNDLE).json()

    assert body["success"] is True, body
    assert body["data"]["target_date"] == "2026-09-25"
    assert get_report.calls == [], "오늘 날짜인데 DB 오버레이(get_log_report)를 호출했다"
    assert body["data"]["metrics"] == today_metrics


@freeze_time("2026-09-25 07:00:00")
def test_bundle_when_past_date_and_no_db_row_then_process_values_kept(monkeypatch):
    """저장 행이 아직 없으면(fail-open) 프로세스 값을 그대로 둔다 — 번들은 여전히 성공."""
    _patch_collect(monkeypatch, _Recorder(result=dict(PROCESS_STATE_METRICS)))
    _patch_get_log_report(monkeypatch, _Recorder(result=None))

    body = _client().get(BUNDLE, params={"date": "2026-08-01"}).json()

    assert body["success"] is True, body
    assert body["data"]["metrics"]["api_metrics"] == {}
    assert body["data"]["metrics"]["strategy_funnel"] == {}
    assert body["data"]["metrics"]["portfolio_risk_snapshot"] is None


@freeze_time("2026-09-25 07:00:00")
def test_bundle_when_past_date_and_db_lookup_raises_then_graceful(monkeypatch):
    """DB 조회 예외는 번들 전체를 죽이지 않는다 — 프로세스 값으로 fail-open."""
    _patch_collect(monkeypatch, _Recorder(result=dict(PROCESS_STATE_METRICS)))
    _patch_get_log_report(monkeypatch, _Recorder(boom=RuntimeError("pg down")))

    resp = _client().get(BUNDLE, params={"date": "2026-08-01"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True, body
    assert body["data"]["metrics"]["api_metrics"] == {}


@freeze_time("2026-09-25 07:00:00")
def test_bundle_when_stored_metrics_missing_some_keys_then_partial_overlay(monkeypatch):
    """저장 행에 3키 중 일부만 있으면(예: 오래된 스키마) 있는 키만 덮는다."""
    _patch_collect(monkeypatch, _Recorder(result=dict(PROCESS_STATE_METRICS)))
    _patch_get_log_report(
        monkeypatch,
        _Recorder(
            result={
                "target_date": date(2026, 8, 1),
                "metrics": {"api_metrics": {"total": 42}},
            }
        ),
    )

    body = _client().get(BUNDLE, params={"date": "2026-08-01"}).json()

    metrics = body["data"]["metrics"]
    assert metrics["api_metrics"] == {"total": 42}
    # strategy_funnel/portfolio_risk_snapshot 은 저장 행에 없으므로 프로세스 값 유지.
    assert metrics["strategy_funnel"] == {}
    assert metrics["portfolio_risk_snapshot"] is None


@freeze_time("2026-09-25 07:00:00")
def test_bundle_when_stored_metrics_not_a_dict_then_process_values_kept(monkeypatch):
    """저장 행의 `metrics` 가 dict 가 아니면(모양 오염) 전부 fail-open."""
    _patch_collect(monkeypatch, _Recorder(result=dict(PROCESS_STATE_METRICS)))
    _patch_get_log_report(
        monkeypatch,
        _Recorder(result={"target_date": date(2026, 8, 1), "metrics": None}),
    )

    body = _client().get(BUNDLE, params={"date": "2026-08-01"}).json()

    metrics = body["data"]["metrics"]
    assert metrics["api_metrics"] == {}
    assert metrics["strategy_funnel"] == {}
    assert metrics["portfolio_risk_snapshot"] is None
