"""macro_lite/service.py + macro_lite/router.py 통합 테스트 (REQ-PKG-05).

FastAPI TestClient + `macro_lite.service.fetcher.*` monkeypatch로 외부 호출 차단.
5개 GET 200 + 최상위 키 shape + credit_spread partial_failure 캐시 폐기 로직 +
fetcher 예외 시 200(errors 배열) + AUTH_DEPENDENCY 기본 None + determine_regime
호출 시 previous_regime 미전달 검증.
"""

from __future__ import annotations

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

# 주의: macro_lite/__init__.py가 `from .router import router`로 패키지 네임스페이스에
# router 인스턴스를 노출하면서 `macro_lite.router`(패키지 속성)가 서브모듈 참조에서
# APIRouter 인스턴스로 재바인딩된다 — `import macro_lite.router; macro_lite.router.router`
# 패턴은 이 경우 AttributeError. 서브모듈 자체에서 직접 가져오면 __init__.py의 네임스페이스
# 재바인딩과 무관하게 항상 안전하다.
from macro_lite.router import router as _macro_router, AUTH_DEPENDENCY
from macro_lite import service


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(_macro_router)
    return TestClient(app)


def _default_yield_curve():
    return {
        "current": {"3m": 5.0, "5y": 4.0, "10y": 4.2, "30y": 4.5},
        "spread_10y_3m": -0.8,
        "history": [
            {"date": "2020-01-01", "y3m": 1.5, "y10y": 1.8, "spread": 0.3},
            {"date": "2020-06-01", "y3m": 1.4, "y10y": 1.6, "spread": 0.2},
        ],
        "inverted": True,
    }


def _default_credit_spread():
    return {
        "oas_current": 3.5,
        "oas_history_10y": [{"date": "2020-01-01", "oas": 3.5}],
        "oas_history_5y": [{"date": "2020-01-01", "oas": 3.5}],
        "oas_percentile": 40.0,
        "partial_failure": [],
    }


def _default_cycle_inputs():
    return {
        "yield_spread": 1.0,
        "yield_direction": "stable",
        "credit_direction": "stable",
        "vix_value": 18.0,
        "vix_level": "normal",
        "sector_rotation": "mixed",
        "dollar_strength": "stable",
    }


def _default_vix():
    return {"value": 18.0, "prev": 17.0, "change": 1.0, "level": "normal", "sparkline": []}


def _default_buffett():
    return {
        "ratio": 150.0,
        "market_cap_t": 43.5,
        "gdp_t": 29.0,
        "level": "overvalued",
        "description": "150% — 고평가",
    }


def _default_fear_greed():
    return {
        "score": 50,
        "label": "중립",
        "components": {"vix_score": 60, "momentum_score": 50, "breadth_score": 50},
    }


def _mock_fetchers(monkeypatch, **overrides):
    """macro_lite.service.fetcher.* 를 monkeypatch해 외부 호출을 전면 차단한다."""
    defaults = dict(
        fetch_currency_quotes=lambda: [
            {"symbol": "USDKRW=X", "name": "USD/KRW", "price": 1300.0,
             "prev_close": 1290.0, "change": 10.0, "change_pct": 0.7, "sparkline": []}
        ],
        fetch_commodity_quotes=lambda: [
            {"symbol": "GC=F", "name": "금", "price": 2000.0,
             "prev_close": 1990.0, "change": 10.0, "change_pct": 0.5, "sparkline": []}
        ],
        fetch_yield_curve_data=_default_yield_curve,
        fetch_credit_spread=_default_credit_spread,
        fetch_cycle_inputs=_default_cycle_inputs,
        fetch_vix=_default_vix,
        calc_buffett_indicator=_default_buffett,
        calc_fear_greed=_default_fear_greed,
    )
    defaults.update(overrides)
    for name, fn in defaults.items():
        monkeypatch.setattr(service.fetcher, name, fn)


# ── 5개 엔드포인트 200 + 최상위 키 shape ───────────────────────────

def test_currencies_endpoint_shape(client, monkeypatch):
    _mock_fetchers(monkeypatch)
    resp = client.get("/api/macro/currencies")
    assert resp.status_code == 200
    body = resp.json()
    assert set(body.keys()) >= {"currencies", "updated_at", "errors"}
    assert isinstance(body["currencies"], list)
    assert isinstance(body["errors"], list)


def test_commodities_endpoint_shape(client, monkeypatch):
    _mock_fetchers(monkeypatch)
    resp = client.get("/api/macro/commodities")
    assert resp.status_code == 200
    body = resp.json()
    assert set(body.keys()) >= {"commodities", "updated_at", "errors"}
    assert isinstance(body["commodities"], list)


def test_yield_curve_endpoint_shape(client, monkeypatch):
    _mock_fetchers(monkeypatch)
    resp = client.get("/api/macro/yield-curve")
    assert resp.status_code == 200
    body = resp.json()
    assert set(body.keys()) >= {"yield_curve", "updated_at", "errors"}
    yc = body["yield_curve"]
    assert "events" in yc
    assert set(yc["events"].keys()) >= {"recessions", "bear_markets"}


def test_credit_spread_endpoint_shape(client, monkeypatch):
    _mock_fetchers(monkeypatch)
    resp = client.get("/api/macro/credit-spread")
    assert resp.status_code == 200
    body = resp.json()
    assert set(body.keys()) >= {"credit_spread", "updated_at", "errors"}


def test_macro_cycle_endpoint_shape(client, monkeypatch):
    _mock_fetchers(monkeypatch)
    resp = client.get("/api/macro/macro-cycle")
    assert resp.status_code == 200
    body = resp.json()
    assert set(body.keys()) >= {"cycle", "regime", "updated_at", "errors"}
    assert body["cycle"] is not None
    assert body["regime"] is not None


# ── credit_spread partial_failure 캐시 보존/폐기 로직 ──────────────

def test_partial_failure_response_not_cached(client, monkeypatch):
    """(1) fetch_credit_spread가 partial_failure=['hy_oas'] 반환 → save_today 안 됨."""
    calls = {"n": 0}

    def fake_credit_spread():
        calls["n"] += 1
        return {"oas_current": None, "partial_failure": ["hy_oas"]}

    _mock_fetchers(monkeypatch, fetch_credit_spread=fake_credit_spread)

    resp1 = client.get("/api/macro/credit-spread")
    resp2 = client.get("/api/macro/credit-spread")
    assert resp1.status_code == 200 and resp2.status_code == 200
    # 저장되지 않았으므로 매 호출마다 fetcher 재호출
    assert calls["n"] == 2

    from macro_lite.cache import get_today
    assert get_today("credit_spread") is None


def test_existing_partial_failure_cache_is_discarded_and_refetched(client, monkeypatch):
    """(2) 미리 save_today에 partial_failure가 있으면 GET 시 캐시 폐기 후 재조회."""
    from macro_lite.cache import save_today

    save_today("credit_spread", {"oas_current": 3.0, "partial_failure": ["ig_oas"]})

    calls = {"n": 0}

    def fake_credit_spread():
        calls["n"] += 1
        return {"oas_current": 3.6, "partial_failure": []}

    _mock_fetchers(monkeypatch, fetch_credit_spread=fake_credit_spread)

    resp = client.get("/api/macro/credit-spread")
    assert resp.status_code == 200
    assert calls["n"] == 1  # 캐시 폐기 후 재조회
    assert resp.json()["credit_spread"]["oas_current"] == 3.6


def test_success_response_cached_second_call_skips_fetcher(client, monkeypatch):
    """(3) 정상 응답은 저장되어 두 번째 GET은 fetcher 미호출."""
    calls = {"n": 0}

    def fake_credit_spread():
        calls["n"] += 1
        return {"oas_current": 3.6, "oas_history_5y": [], "partial_failure": []}

    _mock_fetchers(monkeypatch, fetch_credit_spread=fake_credit_spread)

    resp1 = client.get("/api/macro/credit-spread")
    resp2 = client.get("/api/macro/credit-spread")
    assert resp1.status_code == 200 and resp2.status_code == 200
    assert calls["n"] == 1


# ── fetcher 예외 시 500 아닌 200 + errors 배열 ──────────────────────

def test_fetcher_exception_returns_200_with_errors_not_500(client, monkeypatch):
    def boom():
        raise RuntimeError("external api down")

    _mock_fetchers(monkeypatch, fetch_currency_quotes=boom)
    resp = client.get("/api/macro/currencies")
    assert resp.status_code == 200
    body = resp.json()
    assert body["currencies"] == []
    assert len(body["errors"]) >= 1


def test_macro_cycle_fetcher_exception_returns_200_with_errors(client, monkeypatch):
    def boom():
        raise RuntimeError("cycle inputs down")

    _mock_fetchers(monkeypatch, fetch_cycle_inputs=boom)
    resp = client.get("/api/macro/macro-cycle")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["errors"]) >= 1


# ── AUTH_DEPENDENCY 기본 None ───────────────────────────────────────

def test_auth_dependency_defaults_to_none():
    assert AUTH_DEPENDENCY is None


# ── get_macro_cycle이 previous_regime 없이 determine_regime 호출 ─────

def test_macro_cycle_calls_determine_regime_without_previous_regime(client, monkeypatch):
    _mock_fetchers(monkeypatch)

    captured_kwargs = {}

    def fake_determine_regime(sentiment, **kwargs):
        captured_kwargs.update(kwargs)
        return {
            "regime": "cautious",
            "regime_desc": "신중 매수",
            "params": {},
            "buffett_level": "normal",
            "fg_level": "neutral",
        }

    monkeypatch.setattr(service, "determine_regime", fake_determine_regime)

    resp = client.get("/api/macro/macro-cycle")
    assert resp.status_code == 200
    assert "previous_regime" not in captured_kwargs


# ── get_macro_cycle: oas_history_5y>=130 이면 oas_momentum_6m 주입 ────

def test_macro_cycle_injects_oas_momentum_6m_when_history_long_enough(client, monkeypatch):
    """oas_history_5y 길이 >=130 이면 get_macro_cycle이 oas_momentum_6m을
    determine_cycle_phase 호출 inputs에 주입한다 (원본 macro_service.get_macro_cycle 로직,
    fetch_cycle_inputs는 빈 dict를 반환하게 해 주입값만 순수 관찰).
    """
    history_5y = [
        {"date": f"2020-{(i // 28) + 1:02d}-{(i % 28) + 1:02d}", "oas": round(3.0 + i * 0.01, 4)}
        for i in range(130)
    ]
    expected_momentum = round((history_5y[-1]["oas"] - history_5y[0]["oas"]) / history_5y[0]["oas"] * 100, 1)

    def fake_credit_spread():
        return {
            "oas_current": history_5y[-1]["oas"],
            "oas_history_5y": history_5y,
            "oas_percentile": 40.0,
            "partial_failure": [],
        }

    _mock_fetchers(
        monkeypatch,
        fetch_credit_spread=fake_credit_spread,
        fetch_cycle_inputs=lambda: {},
    )

    captured_inputs = {}

    def fake_determine_cycle_phase(inputs):
        captured_inputs.update(inputs)
        return {"phase": "expansion", "scores": {"credit_spread": {"score": 0}}}

    monkeypatch.setattr(service, "determine_cycle_phase", fake_determine_cycle_phase)

    resp = client.get("/api/macro/macro-cycle")
    assert resp.status_code == 200
    assert "oas_momentum_6m" in captured_inputs
    assert captured_inputs["oas_momentum_6m"] == pytest.approx(expected_momentum, abs=0.05)


# ── __init__.py 네임스페이스: macro_lite.router는 서브모듈이어야 함 ────
# (결함 확정: 기존 `from .router import router`가 macro_lite.router 속성을
#  서브모듈→APIRouter 인스턴스로 재바인딩. refactor-engineer가 `from . import router`
#  로 수정 중 — 수정 전에는 아래가 FAIL(RED)이 정상.)

def test_package_router_attribute_is_submodule_not_instance():
    import macro_lite
    import macro_lite.router as rmod

    assert isinstance(rmod.router, APIRouter)

    from macro_lite import router as pkg_router
    assert pkg_router is rmod, (
        "macro_lite.router 패키지 속성이 서브모듈이 아니라 APIRouter 인스턴스로 "
        "재바인딩되어 있음 — __init__.py의 `from .router import router`를 "
        "`from . import router`로 교체해야 한다."
    )
