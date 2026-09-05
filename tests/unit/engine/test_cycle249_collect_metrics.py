"""cycle249 Red (C) — `collect_daily_log_metrics` 추출은 **행위 byte 동일**이어야 한다.

명세: `_workspace/red/cycle249_reporter_scope_spec.md` §C · §H(엔진)

## 왜 추출하는가

20:20 클라우드 루틴이 읽을 번들이 `generate_daily_log_report` 의 "1. 데이터 수집"
블록과 **같은 것**이어야 한다. 두 벌로 갈라지면 병행 기간(OpenAI ↔ Claude) 비교가
성립하지 않고, "같은 날인데 두 리포트의 사실이 다르다" 는 진단 불가능한 상태가 된다.

## 그래서 이 파일이 지키는 것

1. 반환 dict 의 **키 집합과 순서**가 종전 `metrics` 와 정확히 같다. 이 dict 는 그대로
   (a) OpenAI 프롬프트 본문(`json.dumps(metrics, …)`)이고 (b) `daily_log_reports.metrics`
   JSONB 다. 키가 하나 늘거나 순서가 바뀌면 프롬프트 텍스트가 달라져 **모델 출력이
   달라지고**, 과거 행과의 스키마 비교도 어긋난다.
2. `now_kst` 기본값 규칙 — 오늘이면 `datetime.now(KST)`, 과거면 그 날 23:59:59 KST.
   과거 날짜에 `now()` 를 쓰면 수집 윈도우가 "그 날 00:00 ~ 오늘 지금" 이 되어 여러
   날치 로그가 한 날 리포트로 섞인다(집계·귀인이 통째로 거짓이 된다).
3. `generate_daily_log_report` 가 **실제로 그 함수를 호출**하고, OpenAI 와 INSERT 에
   넘기는 metrics 가 **같은 객체**다. 복붙 잔존(추출은 했는데 원본 블록도 그대로)을
   잡는 유일한 축이다.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone

import pytest
from freezegun import freeze_time

import src.engine.log_analysis_engine as lae
import src.engine.log_metrics_collector as collector  # cycle259 카드 ⑦ — 이동처

pytestmark = pytest.mark.unit

KST = timezone(timedelta(hours=9))

#: 종전 `generate_daily_log_report` 의 metrics 조립 순서(소스 리터럴 그대로).
#: 순서까지 못박는 이유 = 이 dict 가 그대로 프롬프트 본문이 된다(파일 docstring 1).
EXPECTED_METRIC_KEYS = [
    "target_date",
    "logs",
    "trades",
    "api_metrics",
    "strategy_funnel",
    "strategy_funnel_stages",
    "next_day_clear",
    "portfolio_risk_snapshot",
    "tick_blind",
]


def _collector():
    fn = getattr(lae, "collect_daily_log_metrics", None)
    if fn is None:  # pragma: no cover - Red 경로
        pytest.fail(
            "Red — src/engine/log_analysis_engine.py 에 "
            "`collect_daily_log_metrics(target_date, *, now_kst=None)` 미구현"
        )
    return fn


@pytest.fixture
def isolated(monkeypatch):
    """수집 하위 호출을 전부 결정론적 대역으로 — DB/KIS/레지스트리 무접촉.

    반환 dict 로 각 호출의 인자를 되돌려 받아 시간 윈도우를 검증한다.
    """
    seen: dict = {"fetch_args": [], "count_args": [], "trades_args": []}

    async def _fetch(start, end, limit=None):
        seen["fetch_args"].append((start, end, limit))
        return []

    async def _high(start, end, *a, **k):
        return []

    async def _count(start, end):
        seen["count_args"].append((start, end))
        return {"WARNING": 0, "ERROR": 0, "CRITICAL": 0}

    async def _trades(d1, d2):
        seen["trades_args"].append((d1, d2))
        return []

    async def _funnel():
        return {"momentum": {"scanned": 0}}

    async def _stages(target_date):
        seen.setdefault("stages_args", []).append(target_date)
        return {}

    async def _snapshot(now=None):
        return None

    monkeypatch.setattr(collector, "_fetch_logs_in_range", _fetch)
    monkeypatch.setattr(collector, "_fetch_high_severity_logs", _high)
    monkeypatch.setattr(collector, "_count_logs_by_level", _count)
    monkeypatch.setattr(collector, "get_trades_in_range", _trades)
    monkeypatch.setattr(collector, "get_request_metrics", lambda: {"total": 0})
    monkeypatch.setattr(collector, "_collect_strategy_funnel", _funnel)
    monkeypatch.setattr(collector, "_collect_strategy_funnel_stages", _stages)
    monkeypatch.setattr(collector, "_build_portfolio_risk_snapshot", _snapshot)
    return seen


# ---------------------------------------------------------------------------
# C-1 ~ C-2 — 반환 계약
# ---------------------------------------------------------------------------
@freeze_time("2026-09-04 05:00:00")  # KST 14:00
async def test_collect_when_called_then_metric_keys_identical(isolated):
    """C-1 — 키 집합·**순서** 정확 일치.

    dict 는 삽입 순서를 보존하므로 `list(metrics)` 비교가 프롬프트 텍스트의 안정성을
    직접 검증한다. 새 키를 추가하는 변경은 이 가드를 **의도적으로** 갱신해야 하고,
    그때 OpenAI 병행 비교의 기준선이 이동함을 함께 인지하게 된다.
    """
    metrics = await _collector()(date(2026, 9, 4))

    assert isinstance(metrics, dict)
    assert list(metrics.keys()) == EXPECTED_METRIC_KEYS, list(metrics.keys())
    assert metrics["target_date"] == "2026-09-04"


@freeze_time("2026-09-04 05:00:00")
async def test_collect_when_called_then_subtrees_wired(isolated):
    """C-2 — 각 하위 집계가 실제로 배선돼 있다(빈 껍데기 반환 금지).

    키만 맞추고 값이 전부 `{}` 인 구현은 "초록인데 번들이 비어 있는" 최악의 형태다.
    """
    metrics = await _collector()(date(2026, 9, 4))

    assert metrics["api_metrics"] == {"total": 0}
    assert metrics["strategy_funnel"] == {"momentum": {"scanned": 0}}
    assert set(metrics["logs"]) >= {"total_logs", "level_counts", "truncated"}
    assert "level_counts_actual" in metrics["logs"], (
        "DB 집계 총계(level_counts_actual)가 빠지면 표본 절단과 실제 총계를 구분할 수 없다"
    )
    assert set(metrics["trades"]) >= {"trades_total", "realized_pnl"}
    assert set(metrics["tick_blind"]) == {
        "boot_count",
        "downtime_secs_total",
        "market_blind_secs_total",
    }


# ---------------------------------------------------------------------------
# C-3 ~ C-5 — now_kst 기본값
# ---------------------------------------------------------------------------
@freeze_time("2026-09-04 05:00:00")  # KST 14:00
async def test_collect_when_today_then_now_is_wall_clock(isolated):
    """C-3 — 오늘이면 창의 끝은 **지금**(장중 수동 호출·`run_now` 경로 보존)."""
    await _collector()(date(2026, 9, 4))

    start, end, _ = isolated["fetch_args"][0]
    assert start == datetime(2026, 9, 4, 0, 0, tzinfo=KST)
    assert end == datetime.now(KST)
    assert end.utcoffset() == timedelta(hours=9), end


@freeze_time("2026-09-04 05:00:00")
async def test_collect_when_past_date_then_end_of_that_day(isolated):
    """C-4 — 과거 날짜면 창의 끝은 **그 날 23:59:59 KST**.

    `now()` 를 쓰면 8/31 번들이 8/31 00:00 ~ 9/4 14:00 을 집계한다 — 나흘치 로그가
    하루 리포트로 섞여 "그날 ERROR 40건" 같은 거짓 사실이 저장된다.
    """
    await _collector()(date(2026, 8, 31))

    start, end, _ = isolated["fetch_args"][0]
    assert start == datetime(2026, 8, 31, 0, 0, tzinfo=KST)
    assert end == datetime.combine(date(2026, 8, 31), time(23, 59, 59), tzinfo=KST)


@freeze_time("2026-09-04 05:00:00")
async def test_collect_when_now_kst_given_then_respected(isolated):
    """C-5 — 명시 `now_kst` 는 그대로 쓴다(호출자 주입 seam 보존).

    `generate_daily_log_report` 가 `_now_kst` 를 받아 넘기는 기존 테스트 경로
    (`test_b2_b4_log_analysis_data_collection`)가 이 seam 위에 서 있다.
    """
    pinned = datetime(2026, 8, 31, 16, 10, 0, tzinfo=KST)
    await _collector()(date(2026, 8, 31), now_kst=pinned)

    _, end, _ = isolated["fetch_args"][0]
    assert end == pinned


@freeze_time("2026-09-04 05:00:00")
async def test_collect_when_called_then_trades_window_is_target_date(isolated):
    """C-6 — 거래 조회는 **대상일 단일 날짜** 범위(원본 `get_trades_in_range(d, d)`)."""
    await _collector()(date(2026, 8, 31))
    assert isolated["trades_args"][0] == (date(2026, 8, 31), date(2026, 8, 31))


# ---------------------------------------------------------------------------
# C-7 ~ C-9 — generate_daily_log_report 와의 동일성
# ---------------------------------------------------------------------------
async def test_generate_when_run_then_delegates_to_collector(monkeypatch):
    """C-7 — `generate_daily_log_report` 가 `collect_daily_log_metrics` 를 **호출**하고,
    그 반환을 OpenAI·INSERT 에 **같은 객체**로 넘긴다.

    추출 리팩터의 전형적 실패는 "함수는 만들었는데 원본 블록도 그대로" 다. 그 상태는
    두 경로가 서로 다른 metrics 를 만들어도 아무 테스트가 붉지 않는다 — 여기서 잡는다.
    """
    sentinel = {"target_date": "2026-08-31", "logs": {}, "sentinel": object()}
    calls: list[tuple] = []
    captured: dict = {}

    async def _fake_collect(target_date, *, now_kst=None):
        calls.append((target_date, now_kst))
        return sentinel

    async def _fake_call_openai(client, metrics, model):
        captured["openai_metrics"] = metrics
        return ({"summary": "요약", "findings": []}, lae._OpenAIMeta())

    async def _fake_insert(**kwargs):
        captured["insert_metrics"] = kwargs.get("metrics")
        return {"id": "row-1"}

    monkeypatch.setattr(lae, "collect_daily_log_metrics", _fake_collect, raising=False)
    monkeypatch.setattr(lae, "_call_openai", _fake_call_openai)
    monkeypatch.setattr(lae, "insert_log_report", _fake_insert)
    monkeypatch.setattr(lae.settings, "openai_api_key", "dummy-key")

    pinned = datetime(2026, 8, 31, 20, 10, 0, tzinfo=KST)
    await lae.generate_daily_log_report(_now_kst=pinned)

    assert calls, "generate_daily_log_report 가 collect_daily_log_metrics 를 호출하지 않았다"
    assert calls[0][0] == date(2026, 8, 31)
    # cycle249 뮤테이션 렌즈 M20c 봉인 — `collect_daily_log_metrics(target_date)` 로
    # `now_kst=` 전달이 누락되면 값이 `None` 으로 재계산돼(스케줄러 경로는 동일해
    # 보이지만) 장중 수동 호출·`run_now` 의 `_now_kst` 주입 seam 이 무력화된다.
    # `==` 가 아니라 `is` — `datetime.now(KST)` 로 새로 만든 값도 `pinned` 과
    # `==` 는 우연히 같을 수 있으나(freezegun) 반드시 **동일 객체**가 넘어가야 한다.
    assert calls[0][1] is pinned, (
        "generate_daily_log_report 가 collect_daily_log_metrics 에 now_kst 를 그대로 "
        "넘기지 않았다(재계산/누락 — `_now_kst` 주입 seam 붕괴)"
    )
    assert captured.get("openai_metrics") is sentinel, "OpenAI 로 다른 metrics 가 갔다"
    assert captured.get("insert_metrics") is sentinel, "INSERT 로 다른 metrics 가 갔다"


@freeze_time("2026-09-04 05:00:00")  # KST 14:00
async def test_generate_when_now_kst_omitted_then_collector_gets_aware_default(
    monkeypatch,
):
    """C-7b (M20c 회귀) — `_now_kst` 생략 시에도 `collect_daily_log_metrics` 는 **None
    이 아닌** aware datetime 을 받는다.

    C-7 이 봉인하는 것과 반대 방향의 변조 — `now_kst` 를 무조건 넘기되 값을 `None`
    으로 흘려보내면(예: 과도한 `if _now_kst: ... else: metrics = await
    collect_daily_log_metrics(target_date)`) `collect_daily_log_metrics` 내부 기본값
    분기가 "오늘이 아닌 과거 날짜" 취급으로 오인해 창의 끝이 `23:59:59` 로 굳는다
    (§C now_kst 기본값 규칙 — 과거 폴백은 오늘 실행에선 절대 밟으면 안 되는 경로).
    """
    calls: list[tuple] = []

    async def _fake_collect(target_date, *, now_kst=None):
        calls.append((target_date, now_kst))
        return {"target_date": target_date.isoformat(), "logs": {}}

    async def _fake_call_openai(client, metrics, model):
        return ({"summary": "요약", "findings": []}, lae._OpenAIMeta())

    async def _fake_insert(**kwargs):
        return {"id": "row-1"}

    monkeypatch.setattr(lae, "collect_daily_log_metrics", _fake_collect, raising=False)
    monkeypatch.setattr(lae, "_call_openai", _fake_call_openai)
    monkeypatch.setattr(lae, "insert_log_report", _fake_insert)
    monkeypatch.setattr(lae.settings, "openai_api_key", "dummy-key")

    await lae.generate_daily_log_report()  # _now_kst 생략 — 기본 datetime.now(KST)

    assert calls, "generate_daily_log_report 가 collect_daily_log_metrics 를 호출하지 않았다"
    now_kst_arg = calls[0][1]
    assert now_kst_arg is not None, (
        "now_kst=None 이 그대로 전달됐다 — collect_daily_log_metrics 가 오늘을 과거 "
        "날짜로 오인해 창의 끝을 23:59:59 로 고정한다"
    )
    assert isinstance(now_kst_arg, datetime), now_kst_arg
    assert now_kst_arg.tzinfo == KST, now_kst_arg


async def test_generate_when_openai_key_missing_then_no_collection(monkeypatch):
    """C-8 — OpenAI 키/패키지 검사가 **수집보다 앞**(호출 순서 보존).

    순서가 뒤집히면 키 없는 개발 환경·병행 종료 후에도 매일 20:10 에 로그 3만 건 조회가
    돈다(무의미한 DB 부하). 명세 §C 의 "검사 후 호출" 문언이 여기서 행위로 봉인된다.
    """
    called = {"n": 0}

    async def _fake_collect(target_date, *, now_kst=None):
        called["n"] += 1
        return {}

    monkeypatch.setattr(lae, "collect_daily_log_metrics", _fake_collect, raising=False)
    monkeypatch.setattr(lae.settings, "openai_api_key", "")

    out = await lae.generate_daily_log_report()

    assert out is None
    assert called["n"] == 0, "OPENAI_API_KEY 미설정인데 수집이 실행됐다"


@freeze_time("2026-09-04 05:00:00")
async def test_collect_when_run_then_logs_input_summary(isolated, caplog):
    """C-9 — "로그 분석 리포트 입력" INFO 가 추출 후에도 남는다(문구 보존).

    운영자가 매일 이 한 줄로 "수집이 돌았는가 · 표본이 몇 건인가" 를 확인한다.
    리팩터가 로그를 흘리면 관측이 조용히 사라진다(cycle243 이 반복 강조한 실패 형태).
    """
    import logging

    # cycle259 카드 ⑦ — 이 INFO 는 `collect_daily_log_metrics` 본문에서 나가고, 그
    # 함수가 `log_metrics_collector.py` 로 옮겨 로거 이름도 그 모듈 것으로 바뀐다.
    with caplog.at_level(logging.INFO, logger="src.engine.log_metrics_collector"):
        await _collector()(date(2026, 9, 4))

    assert any("로그 분석 리포트 입력" in r.getMessage() for r in caplog.records), [
        r.getMessage() for r in caplog.records
    ]
