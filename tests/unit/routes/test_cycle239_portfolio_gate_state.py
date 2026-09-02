"""cycle239 Red — `GET /api/portfolio/risk` 의 `account_gate` 신선도 노출.

명세 = `_workspace/red/cycle239_gate_freshness_spec.md` §4.3.

배경: 대시보드가 `get_gate_state()` 를 그대로 노출하는데(라우트 소비처 단 1곳,
기존 커버리지 **0**) 반환값만 고치고 상태를 안 고치면 화면은 계속 `level=block` 을
보고한다 = **행위-관측 괴리**. 판독 서명은
`level=block ∧ stale=true ∧ effective_gated=false` = "동결됐다가 fail-open 으로 풀림".

라우트는 **diff 0 기대** — 신규 4키가 사본 dict 로 자연 전파된다.
검증 패턴 = 라우트 함수 직접 await (TestClient 금지, 사이클 127 anyio portal hang).
"""

from __future__ import annotations

import pytest

from src.engine import account_risk_watcher as watcher

# 리그 재사용 — 복붙 금지.
from tests.unit.engine.test_cycle239_gate_freshness import _Clock, _evaluate_block
from tests.unit.routes.test_cycleH_portfolio_route import _install_fakes

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _reset_watcher_state():
    watcher.reset_state_for_test()
    yield
    watcher.reset_state_for_test()


@pytest.mark.asyncio
async def test_route_when_never_evaluated_then_gate_reports_stale(monkeypatch):
    """미평가(부팅 직후·프로세스 재시작) = '아직 평가 없음' 의 정직 표시."""
    pf = _install_fakes(monkeypatch, net_asset=1_000_000)

    resp = await pf.get_portfolio_risk()

    assert resp.success is True
    gate = resp.data.get("account_gate")
    assert isinstance(gate, dict), "account_gate 미노출"
    for key in ("stale", "age_secs", "stale_max_secs", "effective_gated"):
        assert key in gate, f"신선도 키 누락: {key}"
    assert gate["stale"] is True
    assert gate["age_secs"] is None
    assert gate["stale_max_secs"] == 900
    assert gate["effective_gated"] is False
    assert gate["level"] == "ok"


@pytest.mark.asyncio
async def test_route_when_gate_frozen_then_level_and_effective_diverge(monkeypatch):
    """동결 서명 — `level=block` 은 사실로 보존, `effective_gated=false` 가 행위."""
    clock = _Clock()
    await _evaluate_block(monkeypatch, clock)
    clock.advance(901)

    pf = _install_fakes(monkeypatch, net_asset=1_000_000)
    resp = await pf.get_portfolio_risk()

    gate = resp.data["account_gate"]
    assert gate["level"] == "block", "마지막 평가 사실이 지워지면 동결을 식별 못 한다"
    assert gate["stale"] is True
    assert gate["effective_gated"] is False
    assert gate["age_secs"] >= 901


@pytest.mark.asyncio
async def test_route_when_gate_state_raises_then_still_200(monkeypatch):
    """관측 실패가 운영 화면을 죽이면 안 된다 (기존 graceful 분기 보존)."""
    pf = _install_fakes(monkeypatch, net_asset=1_000_000)

    def _boom():
        raise RuntimeError("게이트 상태 조회 실패")

    monkeypatch.setattr(watcher, "get_gate_state", _boom)

    resp = await pf.get_portfolio_risk()

    assert resp.success is True
    assert isinstance(resp.data, dict)
