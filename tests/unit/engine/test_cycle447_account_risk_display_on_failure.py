"""cycle447 제안 4(축소 적용) — 계좌 위험 게이트 평가 실패 시 디스플레이 보존.

정본 = `_workspace/analysis/balance_5xx_20261011/result.md` 제안 4.

🔴 **전체 리터럴 구현은 하지 않는다** — "직전 값을 쓴다" 를 `_gate_active`
(매수 게이트 그 자체)에도 적용하면 cycle233/239 의 하드코딩된 안전 계약
("F5 — 활성 게이트가 평가 실패로 풀릴 때 무음 해제 금지" ·
"R6 — get_balance 예외 → 게이트 False + LOUD WARNING", `test_cycle233_
watcher_gate.py::test_failure_releases_active_gate_loudly`/
`test_fail_open_on_balance_error`)을 뒤집는다 — 매수 게이트 행위를 바꾸는
변경이라 domain-consult + 사용자 승인이 별도로 필요하다(루트 CLAUDE.md
「여전히 승인이 필요한 것」). 그래서 이 사이클은 **`_gate_active` 는 항상
무조건 fail-open** 그대로 두고, **디스플레이 상태(`get_gate_state()`
의 level/reasons)만** 신선도(900초) 안에서는 직전 성공 평가값을 보존한다
— 한도를 넘으면 기존처럼(level=error) 그대로다. 실 프로덕션에서
`account_risk_block_pct` 가 다크런치(None)라 `_gate_active` 가 애초에
항상 False 이므로, 이 변경의 실질 효과는 "순간적인 5xx 가 대시보드를
갑자기 error 로 깜빡이지 않는다" 뿐이다.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.engine import account_risk_watcher as watcher


def _fake_scheduler(strategies):
    return SimpleNamespace(registry=SimpleNamespace(all=lambda: list(strategies)))


def _fake_strat(sid, positions=None, *, hard_stop=-8.0, stop_of=None):
    s = SimpleNamespace(
        strategy_id=sid,
        config=SimpleNamespace(params={"hard_stop_pct": hard_stop}),
        state=SimpleNamespace(positions=positions or {}, total_investment=0,
                              buy_disabled=False),
    )
    if stop_of is not None:
        s.get_effective_stop_price = stop_of
    return s


def _patch_balance(monkeypatch, *, net_asset=1_000_000):
    async def _fake(afhr_flpr="N"):
        return [], SimpleNamespace(net_asset=net_asset)

    from src.api import balance as balance_mod
    monkeypatch.setattr(balance_mod, "get_balance", _fake)


def _patch_thresholds(monkeypatch, *, warn=4.0, block=None):
    from src.db import system_config as sc

    async def _warn():
        return warn

    async def _block():
        return block

    monkeypatch.setattr(sc, "get_account_risk_warn_pct", _warn)
    monkeypatch.setattr(sc, "get_account_risk_block_pct", _block)


@pytest.fixture(autouse=True)
def _reset_watcher_state():
    watcher.reset_state_for_test()
    yield
    watcher.reset_state_for_test()


@pytest.mark.asyncio
async def test_single_transient_failure_keeps_prior_level_display(monkeypatch):
    """직전 평가가 `level=ok` 로 신선할 때 단발 실패는 디스플레이를 바꾸지 않는다."""
    _patch_balance(monkeypatch)
    _patch_thresholds(monkeypatch, warn=4.0, block=None)
    sched = _fake_scheduler([_fake_strat("kojiro")])

    await watcher.run_account_risk_watch_once(sched)
    assert watcher.get_gate_state()["level"] == "ok"

    from src.api import balance as balance_mod

    async def _boom(afhr_flpr="N"):
        raise RuntimeError("KIS down")

    monkeypatch.setattr(balance_mod, "get_balance", _boom)
    await watcher.run_account_risk_watch_once(sched)

    state = watcher.get_gate_state()
    assert state["level"] == "ok", (
        f"신선한 직전 평가가 있는데 단발 실패로 level 이 바뀌었다: {state['level']}"
    )
    # 매수 게이트 자체는 그대로 fail-open 계약(F5/R6) — 바뀌지 않는다.
    assert watcher.is_soft_gated() is False


@pytest.mark.asyncio
async def test_gate_active_still_fails_open_immediately_even_when_display_kept(
    monkeypatch,
):
    """🔴 F5/R6 불변 — 활성 게이트가 평가 실패로 풀릴 때 `_gate_active` 는 항상
    즉시 False(디스플레이 보존과 무관하게)."""
    pos = {"A": SimpleNamespace(buy_price=50_000, quantity=10)}
    sched = _fake_scheduler([_fake_strat("kojiro", pos, stop_of=lambda t: 40_000)])
    _patch_balance(monkeypatch, net_asset=1_000_000)
    _patch_thresholds(monkeypatch, warn=4.0, block=6.0)  # 실효 10% >= 6% → block

    await watcher.run_account_risk_watch_once(sched)
    assert watcher.is_soft_gated() is True

    from src.api import balance as balance_mod

    async def _boom(afhr_flpr="N"):
        raise RuntimeError("KIS down")

    monkeypatch.setattr(balance_mod, "get_balance", _boom)
    await watcher.run_account_risk_watch_once(sched)

    assert watcher.is_soft_gated() is False, (
        "디스플레이 보존 로직이 매수 게이트(_gate_active) 까지 지키면 안 된다"
    )


@pytest.mark.asyncio
async def test_display_falls_back_to_error_once_stale(monkeypatch):
    """900초(= 3×주기) 를 넘긴 뒤 실패는 기존처럼 `level=error` 로 떨어진다."""
    _patch_balance(monkeypatch)
    _patch_thresholds(monkeypatch, warn=4.0, block=None)
    sched = _fake_scheduler([_fake_strat("kojiro")])

    await watcher.run_account_risk_watch_once(sched)
    assert watcher.get_gate_state()["level"] == "ok"

    from src.api import balance as balance_mod

    async def _boom(afhr_flpr="N"):
        raise RuntimeError("KIS down")

    monkeypatch.setattr(balance_mod, "get_balance", _boom)

    # 마지막 성공 스탬프를 신선도 한도(900s) 밖으로 밀어 둔다.
    base_mono = watcher._evaluated_mono
    assert base_mono is not None
    monkeypatch.setattr(
        watcher, "_now_mono", lambda: base_mono + watcher._GATE_STALE_MAX_SECS + 1,
    )
    await watcher.run_account_risk_watch_once(sched)

    state = watcher.get_gate_state()
    assert state["level"] == "error", (
        f"신선도 한도를 넘겼는데도 직전 값을 유지했다: {state['level']}"
    )
