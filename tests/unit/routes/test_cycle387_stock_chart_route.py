"""cycle387 Red — `GET /api/stock-chart/candles` 라우트 계약 (R1~R10).

명세: `_workspace/red/cycle387_stock_chart_spec.md` §1.2 · §1.5 · §3.1(R1~R10)

## 봉인하는 계약 (이름·형태가 다르면 FAIL)

`src/routes/stock_chart.py`
  * `router` — `prefix="/api/stock-chart"`, GET `/candles` **하나**. `src/main.py` 가
    `app.include_router(stock_chart.router)` 로(추가 prefix 없이) 싣는다.
  * 서비스 호출은 **모듈 참조**로 한다 — `from src.api import period_chart` 후
    `period_chart.fetch_candle_chart(...)`. 이 파일은 `src.api.period_chart.fetch_candle_chart`
    를 AsyncMock 으로 갈아끼운다(`from … import fetch_candle_chart` 로 묶으면 seam 이 사라진다).
  * `ticker` 는 **쿼리**로 받는다 — `MetricsMiddleware` 가 raw path 로 키를 만든다(`src/main.py:59-69`).
  * 응답 = `ApiResponse{success, data, message}`, `data = CandleChart.model_dump(mode="json")`.
  * 실패(KIS·대기 초과·그 밖)는 **HTTP 200 + success=false + data=null**, 인자 위반은 422.

`src/models/candle_chart.py` — `CandleChart`(필드 16개, `bars: list[CandleBar]`).
`src/api/period_chart.py` — `ChartBusyError(Exception)`(메시지 한 개로 생성 가능).

인증 미들웨어는 `tests/conftest.py::_neutralize_api_auth` 가 중립화하고, R1~R8 의 독립 앱에는
미들웨어 자체가 붙지 않는다. R10 만 `real_api_auth` 로 실제 판정을 탄다.

RED: 라우트·모델·서비스 모듈 부재 → import 실패로 전 케이스 FAIL.
"""

from __future__ import annotations

import ast
import inspect
import logging
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[3]
MAIN_SRC = ROOT / "src" / "main.py"
URL = "/api/stock-chart/candles"

DATA_KEYS = {
    "ticker", "name", "period", "years", "adjusted", "market", "start_date", "end_date",
    "bars", "complete", "incomplete_reason", "last_bar_provisional", "dropped_bars",
    "kis_calls", "cached", "fetched_at",
}
BAR_NUM_KEYS = ("open", "high", "low", "close", "volume", "amount")


# ─────────────────────────────────────────────────────────────────────────────
# 헬퍼
# ─────────────────────────────────────────────────────────────────────────────

def _modules():
    from src.api import period_chart
    from src.routes import stock_chart

    return period_chart, stock_chart


def _client() -> TestClient:
    """라우터만 실은 독립 앱 — 미들웨어/lifespan 무관(`test_cycle266_daily_route_serialization.py` 패턴)."""
    _, stock_chart = _modules()
    app = FastAPI()
    app.include_router(stock_chart.router)
    return TestClient(app, raise_server_exceptions=False)


def _bars(n: int) -> list[dict]:
    from datetime import date, timedelta

    start = date(2021, 9, 28)
    out = []
    for i in range(n):
        d = start + timedelta(days=i)
        px = 70_000 + i
        out.append({
            "date": d.isoformat(), "open": px - 100, "high": px + 300, "low": px - 300,
            "close": px, "volume": 1_000_000 + i, "amount": (1_000_000 + i) * px,
        })
    return out


def _chart(*, n: int = 2, period: str = "D", **overrides: Any):
    from src.models.candle_chart import CandleChart

    payload: dict[str, Any] = {
        "ticker": "005930",
        "name": "삼성전자",
        "period": period,
        "years": 5,
        "adjusted": True,
        "market": "J",
        "start_date": "2021-09-28",
        "end_date": "2026-09-28",
        "bars": _bars(n),
        "complete": True,
        "incomplete_reason": None,
        "last_bar_provisional": True,
        "dropped_bars": 0,
        "kis_calls": 13,
        "cached": False,
        "fetched_at": "2026-09-28T16:55:02+09:00",
    }
    payload.update(overrides)
    return CandleChart.model_validate(payload)


def _patch_service(monkeypatch, *, returns=None, raises=None) -> AsyncMock:
    period_chart, _ = _modules()
    mock = AsyncMock(return_value=returns, side_effect=raises)
    monkeypatch.setattr(period_chart, "fetch_candle_chart", mock)
    return mock


def _bound(call) -> dict:
    """위치/키워드 어느 쪽으로 불러도 (ticker, period, years) 로 읽는다."""

    def _sig(ticker, period="D", years=5, *, now_kst=None):  # 명세 §1.4 시그니처
        return None

    b = inspect.signature(_sig).bind(*call.args, **call.kwargs)
    b.apply_defaults()
    return dict(b.arguments)


def _warnings(caplog, prefix: str) -> list[str]:
    return [
        r.getMessage() for r in caplog.records
        if r.levelno >= logging.WARNING and r.getMessage().startswith(prefix)
    ]


# ═════════════════════════════════════════════════════════════════════════════
# R1 — 성공 응답의 JSON 모양
# ═════════════════════════════════════════════════════════════════════════════

def test_r1_success_envelope_json_ints_and_kst(monkeypatch):
    """R1 — success=true · data 키 집합 정확 · bars 숫자 6칸 = JSON 정수 · fetched_at +09:00."""
    svc = _patch_service(monkeypatch, returns=_chart(n=1231))

    res = _client().get(URL, params={"ticker": "005930"})

    assert res.status_code == 200
    body = res.json()
    assert body["success"] is True
    assert body["message"] == "일봉 1,231개"
    data = body["data"]
    assert set(data) == DATA_KEYS
    assert data["ticker"] == "005930" and data["name"] == "삼성전자"
    assert data["adjusted"] is True and data["market"] == "J"
    assert data["start_date"] == "2021-09-28" and data["end_date"] == "2026-09-28"
    assert data["fetched_at"].endswith("+09:00")
    assert len(data["bars"]) == 1231
    for bar in data["bars"][:3] + data["bars"][-3:]:
        assert set(bar) == {"date", *BAR_NUM_KEYS}
        assert isinstance(bar["date"], str) and len(bar["date"]) == 10
        for k in BAR_NUM_KEYS:
            assert type(bar[k]) is int, f"{k}={bar[k]!r} — JSON 정수여야 한다(문자열·float·bool 금지, cycle266 계열)"

    svc.assert_awaited_once()
    args = _bound(svc.await_args)
    assert (args["ticker"], args["period"], args["years"]) == ("005930", "D", 5), "기본값 period=D · years=5"


@pytest.mark.parametrize(("period", "label"), [("D", "일봉"), ("W", "주봉"), ("M", "월봉")])
def test_r1b_message_label_per_period_and_passthrough(monkeypatch, period, label):
    """R1b — message 「{일봉|주봉|월봉} {N:,}개」 · period/years 를 그대로 넘긴다."""
    svc = _patch_service(monkeypatch, returns=_chart(n=61, period=period, years=3))

    res = _client().get(URL, params={"ticker": "000660", "period": period, "years": 3})

    body = res.json()
    assert body["success"] is True
    assert body["message"] == f"{label} 61개"
    args = _bound(svc.await_args)
    assert (args["ticker"], args["period"], args["years"]) == ("000660", period, 3)


# ═════════════════════════════════════════════════════════════════════════════
# R2 — 422 (서비스 호출 0)
# ═════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize(
    "params",
    [
        {"ticker": "00593"}, {"ticker": "0059300"}, {"ticker": "ABCDEF"}, {"ticker": ""},
        {"ticker": "0080G0"}, {},
        {"ticker": "\u0660\u0660\u0665\u0669\u0663\u0660"},   # 아랍-인도 숫자 ٠٠٥٩٣٠ (유니코드 \d 는 통과)
        {"ticker": "\uff10\uff10\uff15\uff19\uff13\uff10"},   # 전각 숫자 ００５９３０
        {"ticker": "005930", "period": "Y"}, {"ticker": "005930", "period": "d"},
        {"ticker": "005930", "years": 0}, {"ticker": "005930", "years": 6},
    ],
)
def test_r2_invalid_query_is_422_without_service_call(monkeypatch, params):
    """R2 — 6자리 **ASCII** 숫자(`^[0-9]{6}$`) · D/W/M · years 1..5 밖은 FastAPI 검증이 422 로 먼저 막는다.

    `^\\d{6}$` 는 유니코드 숫자(아랍-인도·전각)도 통과시킨다."""
    svc = _patch_service(monkeypatch, returns=_chart())
    res = _client().get(URL, params=params)
    assert res.status_code == 422
    svc.assert_not_awaited()


# ═════════════════════════════════════════════════════════════════════════════
# R3~R5 — 실패는 200 + success=false
# ═════════════════════════════════════════════════════════════════════════════

def test_r3_kis_error_is_success_false_with_msg_cd(monkeypatch, caplog):
    """R3 — `KisApiError` → 200 · success=false · data=null · message 에 msg_cd·msg1."""
    from src.api.base import KisApiError

    caplog.set_level(logging.WARNING)
    _patch_service(monkeypatch, raises=KisApiError("1", "EGW00123", "기간이 만료된 token 입니다."))

    res = _client().get(URL, params={"ticker": "005930"})

    assert res.status_code == 200
    body = res.json()
    assert body["success"] is False
    assert body["data"] is None
    assert body["message"].startswith("KIS 조회 실패")
    assert "[EGW00123]" in body["message"]
    assert "기간이 만료된 token 입니다." in body["message"]
    lines = _warnings(caplog, "[stock_chart_error] ")
    assert any("stage=first_window" in ln and "ticker=005930" in ln for ln in lines), lines


def test_r4_unexpected_error_hides_exception_text(monkeypatch, caplog):
    """R4 — 그 밖의 예외 → success=false · 예외 문자열은 응답에 싣지 않고 로그에만."""
    caplog.set_level(logging.WARNING)
    _patch_service(monkeypatch, raises=RuntimeError("SECRET-internal-detail-387"))

    res = _client().get(URL, params={"ticker": "005930", "period": "W"})

    assert res.status_code == 200
    body = res.json()
    assert body["success"] is False
    assert body["data"] is None
    assert "SECRET-internal-detail-387" not in res.text
    assert body["message"] == "차트 조회 실패 — 서버 로그 [stock_chart_error] 확인"
    lines = _warnings(caplog, "[stock_chart_error] ")
    assert any("stage=unexpected" in ln and "period=W" in ln for ln in lines), lines


def test_r5_busy_is_success_false_with_wait_message(monkeypatch):
    """R5 — `ChartBusyError` → success=false · 대기 안내 문구."""
    period_chart, _ = _modules()
    _patch_service(monkeypatch, raises=period_chart.ChartBusyError("busy"))

    res = _client().get(URL, params={"ticker": "005930"})

    assert res.status_code == 200
    body = res.json()
    assert body["success"] is False
    assert body["data"] is None
    assert body["message"] == "다른 차트 조회가 진행 중입니다 — 잠시 후 다시 시도하세요"


# ═════════════════════════════════════════════════════════════════════════════
# R6·R7 — 부분 · 빈 결과
# ═════════════════════════════════════════════════════════════════════════════

def test_r6_partial_is_success_with_incomplete_flag(monkeypatch):
    """R6 — 부분 결과 → success=true · complete=false · message 에 「일부 구간만」."""
    _patch_service(
        monkeypatch,
        returns=_chart(n=200, complete=False, incomplete_reason="window_error"),
    )
    body = _client().get(URL, params={"ticker": "005930"}).json()
    assert body["success"] is True
    assert body["data"]["complete"] is False
    assert body["data"]["incomplete_reason"] == "window_error"
    assert "일부 구간만" in body["message"]
    assert body["message"].startswith("일봉 200개")


def test_r7_empty_is_success_with_no_bars_message(monkeypatch):
    """R7 — 빈 결과 → success=true · message 「표시할 봉이 없습니다」."""
    _patch_service(monkeypatch, returns=_chart(n=0, last_bar_provisional=False))
    body = _client().get(URL, params={"ticker": "005930"}).json()
    assert body["success"] is True
    assert body["data"]["bars"] == []
    assert body["message"] == "표시할 봉이 없습니다"


# ═════════════════════════════════════════════════════════════════════════════
# R8·R9 — 메서드 · 등록
# ═════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("method", ["post", "put", "delete"])
def test_r8_only_get_is_allowed(monkeypatch, method):
    """R8 — 읽기 전용 경로 — GET 이외는 405."""
    svc = _patch_service(monkeypatch, returns=_chart())
    res = getattr(_client(), method)(URL, params={"ticker": "005930"})
    assert res.status_code == 405
    svc.assert_not_awaited()


def test_r9_router_registered_in_main_once() -> None:
    """R9 — `src/main.py` 에 `stock_chart` import 1 · `include_router(stock_chart.router)` 1 ·
    앱 경로 표에 `/api/stock-chart/candles`(선례 `test_cycle276_llm_evaluations_route.py:458-473`)."""
    text = MAIN_SRC.read_text(encoding="utf-8")
    tree = ast.parse(text)

    imported = [
        alias for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
        and node.module == "src.routes" for alias in node.names if alias.name == "stock_chart"
    ]
    assert len(imported) == 1, f"`from src.routes import (…, stock_chart)` {len(imported)}건 (기대 1)"

    includes = [
        n for n in ast.walk(tree)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
        and n.func.attr == "include_router"
        and "stock_chart" in (ast.get_source_segment(text, n) or "")
    ]
    assert len(includes) == 1, f"`include_router(stock_chart.router)` {len(includes)}건 (기대 1)"

    _, stock_chart = _modules()
    assert stock_chart.router.prefix == "/api/stock-chart"

    from src.main import app

    paths = {getattr(r, "path", "") for r in app.routes}
    assert URL in paths, "앱에 `/api/stock-chart/candles` 가 없다 — 프론트는 404 를 받는다"


# ═════════════════════════════════════════════════════════════════════════════
# R10 — 인증 무변경 (실제 authorize)
# ═════════════════════════════════════════════════════════════════════════════

@pytest.mark.real_api_auth
def test_r10_existing_auth_covers_route_and_reporter_can_read(monkeypatch):
    """R10 — 무키 401 · 운영 키 통과 · 리포터 키 GET 통과(미들웨어 코드는 그대로).

    ⚠️ `with TestClient(...)` 를 쓰지 않는다 — lifespan 이 돌면 부팅이 실제 KIS 를 부른다
    (`test_cycle282_market_state_route.py::test_g18_requires_api_key` 주석과 같은 이유).
    """
    from src.config import settings
    from src.main import app

    _patch_service(monkeypatch, returns=_chart())
    reporter_key = "cycle387REPORTERKEYzzzzzzzzzzzzzzzzzzzzzzzz"
    monkeypatch.setattr(settings, "api_reporter_key", reporter_key)
    raw = TestClient(app, raise_server_exceptions=False)

    unauth = raw.get(URL, params={"ticker": "005930"})
    operator = raw.get(URL, params={"ticker": "005930"}, headers={"X-API-Key": settings.api_auth_key})
    reporter = raw.get(URL, params={"ticker": "005930"}, headers={"X-API-Key": reporter_key})

    assert unauth.status_code == 401
    assert operator.status_code == 200, operator.text[:200]
    assert operator.json()["success"] is True
    assert reporter.status_code == 200, "리포터 스코프는 GET 전체를 읽는다(작업 지시 — 허용)"
