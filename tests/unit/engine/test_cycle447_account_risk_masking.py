"""cycle447 제안 7 — `account_risk_watcher.py` 평가 실패 로그의 계좌번호 마스킹.

`[account_risk_watch_failed]` 경고가 httpx 예외 문자열(요청 URL 전체, `CANO=`
계좌번호 포함)을 그대로 실었다(`_workspace/analysis/balance_5xx_20261011/
result.md` §4). 로그 문자열에 계좌번호가 0 이어야 한다.
"""

from __future__ import annotations

import logging
from types import SimpleNamespace

import pytest

from src.engine import account_risk_watcher as watcher

_FAKE_ACCOUNT = "12345678"


def _fake_scheduler(strategies):
    return SimpleNamespace(registry=SimpleNamespace(all=lambda: list(strategies)))


def _fake_strat(sid):
    return SimpleNamespace(
        strategy_id=sid,
        config=SimpleNamespace(params={"hard_stop_pct": -8.0}),
        state=SimpleNamespace(positions={}, total_investment=0, buy_disabled=False),
    )


@pytest.fixture(autouse=True)
def _reset_watcher_state():
    watcher.reset_state_for_test()
    yield
    watcher.reset_state_for_test()


@pytest.mark.asyncio
async def test_watch_failed_log_does_not_leak_account_number(monkeypatch, caplog):
    """`get_balance()` 예외 문자열에 계좌번호가 있어도 WARNING 에 남지 않는다."""
    from src.api import balance as balance_mod

    async def _boom(afhr_flpr="N"):
        raise RuntimeError(
            f"Server error '500' for url "
            f"'https://openapivts.koreainvestment.com:29443/uapi/domestic-stock/"
            f"v1/trading/inquire-balance?CANO={_FAKE_ACCOUNT}&ACNT_PRDT_CD=01'"
        )

    monkeypatch.setattr(balance_mod, "get_balance", _boom)
    sched = _fake_scheduler([_fake_strat("kojiro")])

    with caplog.at_level(logging.WARNING, logger="src.engine.scheduler"):
        await watcher.run_account_risk_watch_once(sched)

    joined = " | ".join(r.getMessage() for r in caplog.records)
    assert "[account_risk_watch_failed]" in joined
    assert _FAKE_ACCOUNT not in joined, f"계좌번호가 로그에 남았다: {joined}"


@pytest.mark.asyncio
async def test_watch_failed_gate_state_reasons_does_not_leak_account_number(
    monkeypatch,
):
    """대시보드에 노출되는 `get_gate_state()['reasons']` 에도 계좌번호가 없다."""
    from src.api import balance as balance_mod

    async def _boom(afhr_flpr="N"):
        raise RuntimeError(f"... CANO={_FAKE_ACCOUNT} ...")

    monkeypatch.setattr(balance_mod, "get_balance", _boom)
    sched = _fake_scheduler([_fake_strat("kojiro")])

    await watcher.run_account_risk_watch_once(sched)

    state = watcher.get_gate_state()
    joined = " | ".join(str(r) for r in state.get("reasons") or [])
    assert _FAKE_ACCOUNT not in joined, f"계좌번호가 gate_state 에 남았다: {joined}"
