"""cycle249 Red (E) — 분석 입력 번들 GET + 외부 리포트 POST 라우트 계약.

명세: `_workspace/red/cycle249_reporter_scope_spec.md` §E · §H(라우트)

## 무엇을 위한 두 엔드포인트인가

20:10 OpenAI 경로를 **Claude Code 클라우드 루틴(매일 20:20 KST)** 으로 이관한다.
루틴은 DB/EC2 에 직접 닿지 못하므로 백엔드가 (a) 분석 입력을 GET 으로 내주고
(b) 분석 결과를 POST 로 받아야 한다. OpenAI 경로는 병행 기간 동안 **byte 동일**로
남는다(비교용) — 그래서 저장 컬럼도 기존 것을 덮지 않는 `ext_*` 6컬럼이다.

## 봉인하는 seam (이름·형태가 다르면 FAIL)

`src/routes/log_reports.py`
  * `GET  /api/log-reports/bundle?date=YYYY-MM-DD`
      - **`/{target_date}` 보다 앞에 선언**(FastAPI 는 선언 순서로 매칭한다 — 뒤에 두면
        `bundle` 이 날짜 파라미터로 잡혀 "날짜 형식 오류" 가 된다)
      - `data = {target_date, collected_at, metrics, process_scoped_keys}`
      - 예외는 `logger.exception` + `success=False` (500 으로 새지 않는다 — 루틴이
        HTTP 오류와 "그날 데이터가 비었다" 를 구분할 수 있어야 재시도 정책이 선다)
  * `POST /api/log-reports/{target_date}/external` — `ExternalReportIn` 바디,
    리포터 스코프의 **유일한 쓰기 경로**
  * 모듈 레벨 이름 `collect_daily_log_metrics` / `upsert_external_report` (monkeypatch seam)

기존 3 엔드포인트(list/get/run)는 무변경이어야 한다.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from freezegun import freeze_time

pytestmark = pytest.mark.unit

KST = timezone(timedelta(hours=9))

BUNDLE = "/api/log-reports/bundle"

#: 기존 `generate_daily_log_report` 가 만드는 metrics 를 흉내낸 최소 표본.
FAKE_METRICS = {
    "target_date": "2026-09-04",
    "logs": {"total_logs": 3, "level_counts": {"WARNING": 1}},
    "trades": {"trades_total": 0},
    "api_metrics": {"total": 10},
    "strategy_funnel": {"momentum": {"step1": 1}},
    "strategy_funnel_stages": {},
    "next_day_clear": {},
    "portfolio_risk_snapshot": None,
    "tick_blind": {"boot_count": 0},
}


# ---------------------------------------------------------------------------
# Red 헬퍼 — 미구현을 수집 에러가 아니라 케이스별 FAIL 로 보고한다
# ---------------------------------------------------------------------------
def _routes():
    try:
        import src.routes.log_reports as mod
    except Exception as exc:  # pragma: no cover - Red 경로
        pytest.fail(f"Red — src/routes/log_reports.py import 실패: {exc!r}")
    return mod


def _client() -> TestClient:
    from src.main import app

    return TestClient(app)


def _patch_collect(monkeypatch, fake):
    """`collect_daily_log_metrics` seam 을 **양쪽**에 건다.

    라우트가 `from … import collect_daily_log_metrics`(모듈 전역 바인딩)로 쓰든
    `lae.collect_daily_log_metrics`(모듈 경유)로 쓰든 잡히게 한다 — 배선 형태를
    이 파일이 강제하지 않기 위해서다.
    """
    import src.engine.log_analysis_engine as lae

    monkeypatch.setattr(lae, "collect_daily_log_metrics", fake, raising=False)
    mod = _routes()
    if hasattr(mod, "collect_daily_log_metrics"):
        monkeypatch.setattr(mod, "collect_daily_log_metrics", fake)
    else:
        pytest.fail(
            "Red — src/routes/log_reports.py 에 모듈 레벨 `collect_daily_log_metrics` 가 없다"
        )
    return fake


def _patch_upsert(monkeypatch, fake):
    import src.db.log_reports as db_mod

    monkeypatch.setattr(db_mod, "upsert_external_report", fake, raising=False)
    mod = _routes()
    if hasattr(mod, "upsert_external_report"):
        monkeypatch.setattr(mod, "upsert_external_report", fake)
    else:
        pytest.fail(
            "Red — src/routes/log_reports.py 에 모듈 레벨 `upsert_external_report` 가 없다"
        )
    return fake


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


def _target_date_of(call: tuple[tuple, dict]) -> date:
    args, kwargs = call
    if "target_date" in kwargs:
        return kwargs["target_date"]
    assert args, f"target_date 인자가 전달되지 않았다: {call!r}"
    return args[0]


# ---------------------------------------------------------------------------
# E-1 ~ E-5 — bundle GET
# ---------------------------------------------------------------------------
@freeze_time("2026-09-04 05:00:00")  # KST 14:00
def test_bundle_when_no_date_then_today_kst(monkeypatch):
    """E-1 — `date` 미지정이면 **오늘(KST)**.

    루틴은 20:20 KST 에 파라미터 없이 부른다. 서버가 UTC 로 오늘을 계산하면 20:20 KST
    (= 11:20 UTC) 는 같은 날이라 조용히 맞는 것처럼 보이지만, 자정 근처 재시도에서
    **전날 리포트를 오늘 것으로 저장**한다. 모든 시각은 KST 강제(루트 CLAUDE.md).
    """
    rec = _Recorder(result=FAKE_METRICS)
    _patch_collect(monkeypatch, rec)

    resp = _client().get(BUNDLE)

    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True, body
    assert body["data"]["target_date"] == "2026-09-04"
    assert len(rec.calls) == 1, rec.calls
    assert _target_date_of(rec.calls[0]) == date(2026, 9, 4)


@freeze_time("2026-09-04 05:00:00")
def test_bundle_when_ok_then_data_shape(monkeypatch):
    """E-2 — `data` 4키 + `collected_at` KST + 프로세스 스코프 표식.

    `api_metrics`/`strategy_funnel` 은 **프로세스의 현재 스냅샷**이라 과거 날짜를
    조회해도 "그 날의 값" 이 아니다. 그 사실을 응답에 실어 두지 않으면 루틴이 과거
    번들을 그날의 사실로 읽고 **거짓 인과**("그날 API 실패가 많았다")를 리포트에 쓴다.
    """
    rec = _Recorder(result=FAKE_METRICS)
    _patch_collect(monkeypatch, rec)

    body = _client().get(BUNDLE).json()

    data = body["data"]
    assert set(data) == {"target_date", "collected_at", "metrics", "process_scoped_keys"}, data
    assert data["metrics"] == FAKE_METRICS
    assert data["process_scoped_keys"] == [
        "api_metrics",
        "strategy_funnel",
        "portfolio_risk_snapshot",
    ], data
    assert "+09:00" in data["collected_at"], (
        f"collected_at 이 KST 오프셋 명시가 아니다: {data['collected_at']!r}"
    )


@freeze_time("2026-09-04 05:00:00")
def test_bundle_when_past_date_then_passed_through(monkeypatch):
    """E-3 — 과거 날짜는 그대로 전달된다(now_kst 기본값은 엔진이 정한다).

    라우트가 `now_kst=datetime.now()` 를 강제로 밀어 넣으면 과거 날짜 번들의 수집
    윈도우가 "그 날 00:00 ~ 오늘 지금" 이 되어 **여러 날치 로그가 한 날 리포트로**
    섞인다. 라우트는 날짜만 넘기고, 넘긴다면 그 날 23:59:59 KST 여야 한다.
    """
    rec = _Recorder(result=FAKE_METRICS)
    _patch_collect(monkeypatch, rec)

    body = _client().get(BUNDLE, params={"date": "2026-08-31"}).json()

    assert body["success"] is True, body
    assert body["data"]["target_date"] == "2026-08-31"
    args, kwargs = rec.calls[0]
    assert _target_date_of(rec.calls[0]) == date(2026, 8, 31)
    if kwargs.get("now_kst") is not None:
        assert kwargs["now_kst"] == datetime.combine(
            date(2026, 8, 31), time(23, 59, 59), tzinfo=KST
        ), kwargs["now_kst"]


@freeze_time("2026-09-04 05:00:00")
@pytest.mark.parametrize("bad", ["2026-13-45", "20260904", "yesterday", "2026-09-04T10:00"])
def test_bundle_when_bad_date_then_success_false(monkeypatch, bad):
    """E-4 — 형식 오류는 `success=False`(500 아님).

    인터넷 노출면이므로 파싱 예외가 스택트레이스와 함께 새면 안 되고, 루틴 쪽에서는
    "재시도해도 소용없는 입력 오류" 를 HTTP 200 봉투로 구분할 수 있어야 한다.
    """
    rec = _Recorder(result=FAKE_METRICS)
    _patch_collect(monkeypatch, rec)

    resp = _client().get(BUNDLE, params={"date": bad})

    assert resp.status_code == 200
    assert resp.json()["success"] is False
    assert rec.calls == [], "형식 오류인데 수집을 실행했다"


@freeze_time("2026-09-04 05:00:00")
def test_bundle_when_future_date_then_success_false(monkeypatch):
    """E-5 — 미래 날짜 거부.

    미래 날짜는 항상 빈 번들을 만든다 — 그걸 200/success=True 로 주면 루틴이 "그날은
    사고가 없었다" 는 **거짓 초록 리포트**를 저장한다.
    """
    rec = _Recorder(result=FAKE_METRICS)
    _patch_collect(monkeypatch, rec)

    body = _client().get(BUNDLE, params={"date": "2026-09-05"}).json()

    assert body["success"] is False, body
    assert rec.calls == []


@freeze_time("2026-09-04 05:00:00")
def test_bundle_when_collect_raises_then_graceful(monkeypatch):
    """E-6 — 수집 예외 → `success=False` + HTTP 200.

    DB 일시 장애가 500 으로 새면 nginx/루틴 쪽 재시도 로직이 인증 실패와 뒤섞인다.
    기존 `run_now` 의 graceful 규약과 같은 형태다.
    """
    rec = _Recorder(boom=RuntimeError("pg down"))
    _patch_collect(monkeypatch, rec)

    resp = _client().get(BUNDLE)

    assert resp.status_code == 200
    assert resp.json()["success"] is False


@freeze_time("2026-09-04 05:00:00")
def test_bundle_when_declared_then_not_captured_by_target_date(monkeypatch):
    """E-7 — `/bundle` 이 `/{target_date}` 에 잡히지 않는다(선언 순서 계약).

    FastAPI 는 선언 순서로 매칭한다. `bundle` 을 뒤에 두면 `get_report("bundle")` 이
    실행돼 "날짜 형식 오류" 를 돌려준다 — 조용히 틀린 200 이라 배포 후에야 드러난다.
    """
    rec = _Recorder(result=FAKE_METRICS)
    _patch_collect(monkeypatch, rec)
    mod = _routes()
    get_rec = _Recorder(result=None)
    monkeypatch.setattr(mod, "get_log_report", get_rec)

    body = _client().get(BUNDLE).json()

    assert get_rec.calls == [], "`/bundle` 이 `/{target_date}` 라우트로 캡처됐다"
    assert body["success"] is True
    assert "metrics" in body["data"]


# ---------------------------------------------------------------------------
# E-8 ~ E-13 — external POST
# ---------------------------------------------------------------------------
def _external_path(d: str = "2026-09-04") -> str:
    return f"/api/log-reports/{d}/external"


def _payload(**over) -> dict:
    body = {
        "provider": "claude-code",
        "model": "claude-opus-5",
        "summary": "체결 0건, WARNING 12건 — donchian 청산 로그가 대부분.",
        "findings": [
            {
                "category": "trading",
                "severity": "high",
                "title": "매도 거부 반복",
                "detail": "APBK0918 3회",
                "suggestion": "익일 청산 전환 확인",
            }
        ],
        "report_md": "# 리포트\n본문",
    }
    body.update(over)
    return body


def test_external_when_valid_then_upsert_called(monkeypatch):
    """E-8 — 정상 바디 → `upsert_external_report` 호출 + 반환 행 그대로.

    저장 실패를 200/success=True 로 삼키면 루틴은 성공으로 알고 재시도하지 않는다 =
    그날 분석이 통째로 사라진다.
    """
    row = {"target_date": "2026-09-04", "ext_provider": "claude-code"}
    rec = _Recorder(result=row)
    _patch_upsert(monkeypatch, rec)

    resp = _client().post(_external_path(), json=_payload())

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["success"] is True, body
    assert body["data"] == row
    assert len(rec.calls) == 1
    _, kwargs = rec.calls[0]
    assert kwargs["target_date"] == date(2026, 9, 4)
    assert kwargs["provider"] == "claude-code"
    assert kwargs["model"] == "claude-opus-5"
    assert kwargs["report_md"].startswith("# 리포트")


def test_external_when_findings_dirty_then_normalized(monkeypatch):
    """E-9 — findings 는 `_validate_report` 규약으로 **정규화**되어 저장된다.

    루틴 출력은 LLM 자유 문자열이다. 미검증 저장은 (a) 대시보드가 모르는 severity 로
    렌더 깨짐 (b) 초장문 detail 이 JSONB 를 부풀림 (c) 카테고리 집계가 오염 을 부른다.
    기존 OpenAI 경로와 **같은 정규화기**를 쓰는 것이 계약이다 — 두 벌이 되면 병행
    기간의 비교가 성립하지 않는다.
    """
    rec = _Recorder(result={"ok": True})
    _patch_upsert(monkeypatch, rec)

    payload = _payload(
        findings=[
            {
                "category": "해킹",          # 미등록 → etc
                "severity": "URGENT",        # 미등록 → medium
                "title": "가" * 500,          # 200 절단
                "detail": "나" * 3000,        # 1500 절단
                "suggestion": "다" * 2000,    # 1000 절단
            }
        ]
    )
    resp = _client().post(_external_path(), json=payload)

    assert resp.status_code == 200, resp.text
    assert resp.json()["success"] is True
    _, kwargs = rec.calls[0]
    stored = kwargs["findings"]
    assert len(stored) == 1, stored
    item = stored[0]
    assert item["category"] == "etc", item
    assert item["severity"] == "medium", item
    assert len(item["title"]) == 200, len(item["title"])
    assert len(item["detail"]) == 1500, len(item["detail"])
    assert len(item["suggestion"]) == 1000, len(item["suggestion"])


@pytest.mark.parametrize(
    ("over", "why"),
    [
        ({"provider": ""}, "provider 빈 문자열"),
        ({"provider": "p" * 41}, "provider 상한 초과"),
        ({"model": ""}, "model 빈 문자열"),
        ({"model": "m" * 81}, "model 상한 초과"),
        ({"summary": ""}, "summary 빈 문자열"),
        ({"summary": "s" * 4001}, "summary 상한 초과"),
        ({"findings": [{"title": "t", "detail": "d"}] * 51}, "findings 51개"),
        ({"report_md": "x" * 200_001}, "report_md 상한 초과"),
        ({"findings": "not-a-list"}, "findings 타입 오류"),
    ],
)
def test_external_when_body_invalid_then_422(monkeypatch, over, why):
    """E-10 — 바디 검증은 pydantic 이 **422** 로 거부한다(무음 저장 금지).

    이 경로는 리포터 스코프의 유일한 쓰기다. 검증 없는 저장은 인증을 통과한 뒤의
    유일한 남은 방어선을 없애는 것과 같다.
    """
    rec = _Recorder(result={"ok": True})
    _patch_upsert(monkeypatch, rec)

    resp = _client().post(_external_path(), json=_payload(**over))

    assert resp.status_code == 422, f"{why} 가 통과했다: {resp.status_code} {resp.text[:200]}"
    assert rec.calls == [], f"{why} 인데 저장을 시도했다"


def test_external_when_report_md_absent_then_none(monkeypatch):
    """E-11 — `report_md` 는 선택(없으면 None).

    루틴이 요약만 보내는 초기 단계에서도 저장이 성립해야 한다.
    """
    rec = _Recorder(result={"ok": True})
    _patch_upsert(monkeypatch, rec)

    payload = _payload()
    payload.pop("report_md")
    resp = _client().post(_external_path(), json=payload)

    assert resp.status_code == 200, resp.text
    _, kwargs = rec.calls[0]
    assert kwargs["report_md"] is None


@pytest.mark.parametrize("bad", ["2026-13-45", "20260904", "bundle"])
def test_external_when_bad_date_then_success_false(monkeypatch, bad):
    """E-12 — 경로 날짜 형식 오류 → `success=False`, 저장 미수행."""
    rec = _Recorder(result={"ok": True})
    _patch_upsert(monkeypatch, rec)

    resp = _client().post(_external_path(bad), json=_payload())

    assert resp.status_code == 200, resp.text
    assert resp.json()["success"] is False
    assert rec.calls == []


def test_external_when_upsert_raises_then_success_false(monkeypatch):
    """E-13 — 저장 예외 → `success=False` + HTTP 200(500 으로 새지 않는다)."""
    rec = _Recorder(boom=RuntimeError("pg down"))
    _patch_upsert(monkeypatch, rec)

    resp = _client().post(_external_path(), json=_payload())

    assert resp.status_code == 200, resp.text
    assert resp.json()["success"] is False


# ---------------------------------------------------------------------------
# E-14 — 기존 3 엔드포인트 무변경
# ---------------------------------------------------------------------------
def test_existing_endpoints_when_scoped_added_then_unchanged(monkeypatch):
    """E-14 — list/get/run 3 엔드포인트가 그대로 살아 있다(회귀 가드)."""
    mod = _routes()
    paths = {
        (route.path, tuple(sorted(route.methods)))
        for route in mod.router.routes
        if hasattr(route, "methods")
    }
    assert ("/api/log-reports", ("GET",)) in paths, paths
    assert ("/api/log-reports/{target_date}", ("GET",)) in paths, paths
    assert ("/api/log-reports/run", ("POST",)) in paths, paths
    assert ("/api/log-reports/bundle", ("GET",)) in paths, paths
    assert ("/api/log-reports/{target_date}/external", ("POST",)) in paths, paths
