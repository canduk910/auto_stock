"""보드별 시가 확정 — `_confirm_breakout_open_prices` 흐름 검증.

핵심 행위:
- 대상: VB / LTV 중 enabled + 해당 board 가 tradable_boards 에 포함된 전략만
- 각 종목에 대해 ticker_prices[ticker]["open_price"] 폴링 (최대 max_wait_s)
- 받으면 strategy.on_open_price_confirmed(ticker, open_price, board=board)
- 시간 초과 시 KIS API 폴백 — fetch_stock_detail
- board 미지정 시 SessionTracker 활성 보드 우선순위 (main → post_nxt → pre_nxt)
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration


def _seed_target(strategy, ticker, prev_range=1000, k=0.5):
    base = int(prev_range * k)
    strategy._targets[ticker] = {
        "k": k, "prev_range": prev_range, "target_offset_base": base,
        "target_offset": base, "target_price": 0, "open_price": 0, "boards": {},
    }
    strategy._open_confirmed[ticker] = {}


@pytest.mark.asyncio
async def test_confirm_main_board_when_open_price_in_cache_then_target_set(scheduler_env):
    """cycle272 — 레거시(off) 경로 회귀 가드. `main` 기준가 기본값은 `enforce`
    (KRX REST 단일 출처)라 WS 캐시 확정은 `mode="off"` 명시로만 재현된다."""
    sched = scheduler_env.scheduler
    vb = sched.registry.get("volatility_breakout")
    vb.config.enabled = True
    vb.config.params["k_value_krx_main"] = 1.0
    vb.config.params["open_price_scope_mode"] = "off"
    _seed_target(vb, "005930", prev_range=1000, k=0.5)  # base 500

    from src.engine import scanner
    scanner.ticker_prices["005930"] = {"open_price": 80000}

    await sched._confirm_breakout_open_prices(board="main", max_wait_s=0.5, interval_s=0.5)

    # main 보드 target 등록
    board_info = vb._targets["005930"]["boards"]["main"]
    assert board_info["open_price"] == 80000
    assert board_info["target_price"] == 80500
    assert vb._open_confirmed["005930"]["main"] is True


@pytest.mark.asyncio
async def test_confirm_skips_strategy_when_board_not_in_tradable(scheduler_env):
    """tradable_boards 에 main 이 없는 전략은 main 보드 확정 대상에서 제외."""
    sched = scheduler_env.scheduler
    vb = sched.registry.get("volatility_breakout")
    vb.config.enabled = True
    vb.config.params["tradable_boards"] = ["pre_nxt"]  # main 미포함
    _seed_target(vb, "005930")

    from src.engine import scanner
    scanner.ticker_prices["005930"] = {"open_price": 80000}

    await sched._confirm_breakout_open_prices(board="main", max_wait_s=0.5, interval_s=0.5)

    # main 보드 확정 발생 X
    assert "main" not in vb._open_confirmed.get("005930", {})


@pytest.mark.asyncio
async def test_confirm_falls_back_to_kis_api_when_open_price_missing(scheduler_env, monkeypatch):
    """ticker_prices 에 open_price 없으면 KIS fetch_stock_detail 폴백."""
    sched = scheduler_env.scheduler
    vb = sched.registry.get("volatility_breakout")
    vb.config.enabled = True
    vb.config.params["k_value_krx_main"] = 1.0
    _seed_target(vb, "005930", prev_range=1000, k=0.5)

    # ticker_prices 에는 시가 없음
    from src.engine import scanner
    scanner.ticker_prices.pop("005930", None)

    # KIS API 폴백 모킹
    fetch_calls = []

    async def fake_fetch_stock_detail(ticker):
        fetch_calls.append(ticker)
        return {"stck_oprc": "82000"}

    import src.api.condition as condition_mod
    monkeypatch.setattr(condition_mod, "fetch_stock_detail", fake_fetch_stock_detail)

    await sched._confirm_breakout_open_prices(board="main", max_wait_s=0.5, interval_s=0.5)

    # KIS 폴백으로 시가 82000 확정
    assert fetch_calls == ["005930"]
    board_info = vb._targets["005930"]["boards"]["main"]
    assert board_info["open_price"] == 82000


@pytest.mark.asyncio
async def test_confirm_when_board_arg_omitted_then_uses_active_board(scheduler_env, monkeypatch):
    """board=None 일 때 SessionTracker 활성 보드 자동 결정."""
    sched = scheduler_env.scheduler
    from src.engine.session import session_tracker, MarketBoard

    monkeypatch.setattr(session_tracker, "_active", frozenset({MarketBoard.PRE_NXT}))

    vb = sched.registry.get("volatility_breakout")
    vb.config.enabled = True
    vb.config.params["k_value_nxt_pre"] = 1.0
    vb.config.params["tradable_boards"] = ["pre_nxt", "main", "post_nxt"]
    _seed_target(vb, "005930", prev_range=1000, k=0.5)

    from src.engine import scanner
    scanner.ticker_prices["005930"] = {"open_price": 79000}

    await sched._confirm_breakout_open_prices(max_wait_s=0.5, interval_s=0.5)

    # pre_nxt 보드로 확정됨
    assert "pre_nxt" in vb._open_confirmed["005930"]


@pytest.mark.asyncio
async def test_confirm_does_nothing_when_no_enabled_strategy(scheduler_env):
    sched = scheduler_env.scheduler
    # 어느 전략도 enabled X (default)
    await sched._confirm_breakout_open_prices(board="main", max_wait_s=0.5, interval_s=0.5)
    # 외부 호출 없음
    assert scheduler_env.calls.fetch_stock_detail == []


# ---------------------------------------------------------------------------
# PR-H (P4, 2026-05-15) — 시가 확정 호출 idempotent 강화
#
# 결함 (운영 로그 2026-05-15 15:30~16:39):
# - 15:30 정상 (VB+LTV 시가 확정 1회)
# - 15:41~16:39 동안 LTV 만 4번 prepare + 시가 재확정 (VB 1회)
# - 5번 EC2 재시작 직후 매번 LTV 만 재호출
#
# 진단 결과 — 코드 분기는 VB/LTV 동등 처리:
# - scheduler.py 내 모든 prepare/confirm 호출 분기는 `for sid in ("vb","ltv")` 동등
# - LTV-only 발화의 진짜 원인은 운영 데이터 의존 (LTV `_scanned_tickers` 빈 케이스)
# - prepare 자체는 `_open_confirmed[ticker]={}` 매번 reset 하므로 비-멱등
# - `_confirm_breakout_open_prices` 는 _is_confirmed 체크로 사실상 idempotent 이지만
#   매번 INFO 로그 + `_emit_breakout_open_confirm` 가 발화 → 운영 노이즈
#
# Fix: 호출 시점에 모든 대상 종목이 이미 confirmed 면 early-return + 로그 skip
#   - 1차 폴링 / 2차 KIS API 폴백 / 종합 INFO 로그 / _emit_breakout_open_confirm 모두 skip
#   - KIS API 호출 0회 → Rate Limit 부담 감소
#   - INFO 로그 0행 → 운영 가시성 노이즈 차단
#   - 비-idempotent 전제(부분 확정)는 기존 분기 그대로 (안전 보존)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_confirm_is_idempotent_when_all_already_confirmed(scheduler_env, monkeypatch, caplog):
    """모든 종목이 이미 해당 board 로 confirmed 면 1차 폴링/2차 폴백/INFO 로그 모두 skip.

    cycle272 — 레거시(off) 경로 회귀 가드(WS 캐시 확정 전제, 주석 참조 위).
    """
    import logging
    sched = scheduler_env.scheduler
    vb = sched.registry.get("volatility_breakout")
    vb.config.enabled = True
    vb.config.params["k_value_krx_main"] = 1.0
    vb.config.params["tradable_boards"] = ["main"]
    vb.config.params["open_price_scope_mode"] = "off"
    _seed_target(vb, "005930", prev_range=1000, k=0.5)
    _seed_target(vb, "000660", prev_range=2000, k=0.5)

    # 1차 호출 — 시가 확정 (정상 경로)
    from src.engine import scanner
    scanner.ticker_prices["005930"] = {"open_price": 80000}
    scanner.ticker_prices["000660"] = {"open_price": 70000}
    await sched._confirm_breakout_open_prices(board="main", max_wait_s=0.5, interval_s=0.5)

    # 모두 confirmed 상태 검증
    assert vb._open_confirmed["005930"]["main"] is True
    assert vb._open_confirmed["000660"]["main"] is True

    # 2차 호출 — 모두 이미 confirmed → KIS API 호출 0건 + INFO 로그 0행
    fetch_calls = []
    async def fake_fetch(ticker):
        fetch_calls.append(ticker)
        return {"stck_oprc": "0"}

    import src.api.condition as condition_mod
    monkeypatch.setattr(condition_mod, "fetch_stock_detail", fake_fetch)

    caplog.clear()
    caplog.set_level(logging.INFO, logger="src.engine.scheduler")
    await sched._confirm_breakout_open_prices(board="main", max_wait_s=0.5, interval_s=0.5)

    # KIS API 폴백 호출 0건 — 모두 confirmed 면 폴백 자체가 발화 안 함
    assert fetch_calls == [], (
        f"모두 confirmed → 2차 KIS API 폴백 skip 필수, 실제 호출 {fetch_calls}"
    )
    # INFO 로그 "시가 확정 [...]" / "[breakout_open_confirm]" 모두 skip
    msgs = "\n".join(r.message for r in caplog.records if r.levelname == "INFO")
    assert "시가 확정" not in msgs, (
        f"모두 confirmed 인 idempotent 호출에서는 종합 INFO 로그 skip, msgs={msgs!r}"
    )
    assert "[breakout_open_confirm]" not in msgs, (
        f"_emit_breakout_open_confirm 도 skip, msgs={msgs!r}"
    )


@pytest.mark.asyncio
async def test_confirm_proceeds_when_partially_confirmed(scheduler_env):
    """일부만 confirmed 면 미확정 종목에 대해서만 진행 — INFO 로그 정상 노출.

    cycle272 — 레거시(off) 경로 회귀 가드(WS 캐시 확정 전제, 주석 참조 위).
    """
    sched = scheduler_env.scheduler
    vb = sched.registry.get("volatility_breakout")
    vb.config.enabled = True
    vb.config.params["k_value_krx_main"] = 1.0
    vb.config.params["tradable_boards"] = ["main"]
    vb.config.params["open_price_scope_mode"] = "off"
    _seed_target(vb, "005930", prev_range=1000, k=0.5)
    _seed_target(vb, "000660", prev_range=2000, k=0.5)

    # 005930 만 미리 confirmed 상태로 설정 (직접 시가 등록)
    from src.engine import scanner
    scanner.ticker_prices["005930"] = {"open_price": 80000}
    await sched._confirm_breakout_open_prices(board="main", max_wait_s=0.5, interval_s=0.5)
    assert vb._open_confirmed["005930"]["main"] is True
    # 000660 는 시가 미수신
    assert not vb._open_confirmed.get("000660", {}).get("main")

    # 두 번째 호출 — 000660 시가 들어오면 처리되어야 함
    scanner.ticker_prices["000660"] = {"open_price": 70000}
    await sched._confirm_breakout_open_prices(board="main", max_wait_s=0.5, interval_s=0.5)
    # 추가로 confirmed 되어야 함
    assert vb._open_confirmed["000660"]["main"] is True
