"""cycle369 Red — 당일 매수 차단(지정 첫날 포함). 명세 §4 · §5 · §6.

사용자 결정(2026-09-26 11시 ①) 「지정 첫날 매수를 막는거지」 → 보유하지 않은 후보가
지정 첫날(T+1) 사는 것을 막는다. 자문 §4(c) 「새 차단 목록은 두지 않는다」는 첫날에
대해 **폐기**됐다.

## 레지스트리 규칙 (명세 §4.3 `record_read`)

1. 6자리 숫자가 아니면 무시
2. 모름 → `(날짜, 종목)` 시도 +1 · `[status_block_unknown]` 1회/일 · 상태 불변 · 3회면 그날 INC 제외
3. 장 전(`now.time() < 09:00`) 해당 → `phase=pre` 차단. 장 전 clean 은 「판정 완료」가 **아니다**(K16)
4. 장중 해당 → `phase=in`(생성·승격) · 장중 clean → `pre` 면 해제(`reason=pre_session_stale`),
   `in` 이면 유지(`[status_block_flip_ignored]`)

## 패스

| 패스 | 시각 | 대상 |
|---|---|---|
| P0 | 08:45 (enabled 전략 `pre_nxt` 면 07:59) | 보유 ∪ `buy_targets` |
| P1 | 09:00:00 · 벽시계 상한 25초 | `buy_targets` − 오늘 장중 판정 완료 |
| INC | P1 뒤 60초마다 · `< 15:20` | `buy_targets` − 장중 판정 완료 − 모름 3회 소진 |

**미검사 = fail-open** (K15) — 읽지 못한 종목은 막지 않는다.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, time, timedelta

import pytest

from tests.unit.engine._cycle369_support import (
    ALL_SIDS,
    DAY,
    LIVE,
    NEXT_DAY,
    blocks_by_ticker,
    cand,
    clean,
    clock,  # noqa: F401 — pytest 픽스처
    db_modes,  # noqa: F401
    dblog,  # noqa: F401
    fetch,  # noqa: F401
    fhkst,
    field,
    gate,
    hold,
    holder,
    kst,
    leaf,
    lines,
    make_sched,
    managed,
    open_info,
    overheat,
    record,
    records,
)

pytestmark = [
    pytest.mark.unit,
    pytest.mark.real_status_watch,
    pytest.mark.usefixtures("no_real_kis"),
]


@pytest.fixture(autouse=True)
def _info(caplog, db_modes):
    open_info(caplog)


# ===========================================================================
# J1 · J2 · J9 — 레지스트리 수명
# ===========================================================================
def test_j1_in_session_flag_blocks_all_seven_strategies_once_logged(clock, caplog):
    clock.set(10, 0)
    record("294140", LIVE["294140"], kst(10, 0), src="p1")
    record("294140", LIVE["294140"], kst(10, 1), src="inc")
    for sid in ALL_SIDS:
        assert gate("294140", sid) is True, f"{sid} 가 막히지 않았다"
    armed = records(caplog, "[status_block_armed]", min_level=logging.WARNING)
    assert len(armed) == 1, "무장 로그는 (날짜, 종목) 1회"
    assert field(armed[0].getMessage(), "phase") == "in"
    b = blocks_by_ticker()["294140"]
    assert b["phase"] == "in" and b["reason"] == "managed"


def test_j1b_in_session_block_is_fixed_for_the_day(clock, caplog):
    """M27 — 장중 차단은 장중 clean 으로 풀리지 않는다(지정·해제는 다음 날 효력)."""
    clock.set(10, 0)
    record("005160", LIVE["005160"], kst(10, 0), src="p1")
    clock.set(10, 5)
    record("005160", clean("005160"), kst(10, 5), src="inc")
    record("005160", clean("005160"), kst(10, 6), src="fetch")
    assert gate("005160") is True
    assert len(lines(caplog, "[status_block_flip_ignored]")) == 1


def test_j2_pre_session_block_released_by_in_session_clean(clock, caplog):
    """J2 · M26 — 장 전 차단 → 09:00 전 게이트 True → 장중 clean → 해제."""
    record("005160", LIVE["005160"], kst(8, 45), src="p0")
    clock.set(8, 50)
    assert gate("005160") is True, "장 전 해당이면 보수적으로 막는다"
    assert blocks_by_ticker()["005160"]["phase"] == "pre"
    clock.set(9, 0, 5)
    record("005160", clean("005160"), kst(9, 0, 5), src="p1")
    assert gate("005160") is False, "장 전 값이 전날 것이었다 — 장중 clean 이면 풀어야 한다"
    rel = lines(caplog, "[status_block_released]")
    assert len(rel) == 1 and field(rel[0], "reason") == "pre_session_stale"


def test_j2b_pre_session_block_promoted_by_in_session_flag(clock):
    record("005160", LIVE["005160"], kst(8, 45), src="p0")
    record("005160", LIVE["005160"], kst(9, 0, 1), src="p1")
    clock.set(9, 0, 5)
    assert blocks_by_ticker()["005160"]["phase"] == "in"
    record("005160", clean("005160"), kst(9, 10), src="inc")
    clock.set(9, 10)
    assert gate("005160") is True, "승격된 장중 차단은 그날 고정"


def test_j9_block_expires_lazily_next_day(clock):
    """J9 · M18 — 날짜 키 지연 만료. `_reset_daily_state` 호출 없이 다음 날 풀린다."""
    record("294140", LIVE["294140"], kst(10, 0), src="p1")
    clock.set(10, 0)
    assert gate("294140") is True
    clock.set(9, 10, day=NEXT_DAY)
    assert gate("294140") is False


def test_j9b_non_six_digit_tickers_are_ignored(clock):
    record("0000A1", LIVE["294140"], kst(10, 0), src="fetch")
    record("12345", LIVE["294140"], kst(10, 0), src="fetch")
    clock.set(10, 0)
    assert gate("0000A1") is False and gate("12345") is False
    assert blocks_by_ticker() == {}


def test_j9c_unknown_read_is_not_a_block(clock, caplog):
    """J4 · M17 — 모름은 막지 않는다(fail-open)."""
    record("043090", LIVE["043090"], kst(9, 0), src="p1")
    clock.set(9, 1)
    assert gate("043090") is False
    assert len(lines(caplog, "[status_block_unknown]")) == 1


def test_j9d_fetch_fail_is_unknown_not_clean(clock):
    """모름이 장 전 차단을 풀면 안 된다 — 모름은 상태를 바꾸지 않는다."""
    record("005160", LIVE["005160"], kst(8, 45), src="p0")
    record("005160", None, kst(9, 0, 5), src="p1")
    clock.set(9, 1)
    assert gate("005160") is True


def test_j9e_out_of_vocabulary_flag_is_unknown_and_reported(clock, caplog):
    """규칙 밖 값(`"1"`)은 None 취급 → 모름(막지 않음) + `[status_exit_unknown_value]` 1회/일(명세 §2)."""
    out = fhkst("123450", iscd="55", mang="1", short_over="N")
    record("123450", out, kst(10, 0), src="p1")
    record("123450", out, kst(10, 1), src="inc")
    clock.set(10, 1)
    assert gate("123450") is False
    uv = lines(caplog, "[status_exit_unknown_value]")
    assert len(uv) == 1 and "123450" in uv[0]


# ===========================================================================
# J5 · J6 · J7 — 판정 규칙이 매수 차단에서도 같다
# ===========================================================================
@pytest.mark.parametrize("output,expected", [
    (fhkst("035760", iscd="55", mang="N", short_over="N", ssts_hot_yn="Y"), False),  # J5 공매도과열
    (LIVE["356680"], False),                                                           # J6 예고
    (fhkst("123450", iscd="51", mang=None, short_over="N"), True),                     # J7 A11 폴백
    (fhkst("123450", iscd="59", mang="N", short_over=None), True),                     # J7 A13 폴백
    (fhkst("123450", iscd="51", mang="N", short_over="N"), False),                     # A12 명시 N
    (LIVE["016790"], True),                                                            # 관리+정지 — 가격·정지 무관하게 막는다
])
def test_j5_to_j7_same_rules_on_buy_side(clock, output, expected):
    t = output.get("stck_shrn_iscd", "123450")
    record(t, output, kst(10, 0), src="p1")
    clock.set(10, 0)
    assert gate(t) is expected


# ===========================================================================
# J8 — 게이트 모드 · fail-open
# ===========================================================================
def test_j8_enforce_blocks_and_logs_skip_once_per_strategy(clock, caplog):
    record("005160", LIVE["005160"], kst(10, 0), src="p1")
    clock.set(10, 0)
    for _ in range(3):
        assert gate("005160", "momentum") is True
    assert gate("005160", "volatility_breakout") is True
    skips = lines(caplog, "[status_block_buy_skip]")
    assert len(skips) == 2, "(날짜, 종목, 전략) 1회"
    assert blocks_by_ticker()["005160"]["skips"].get("momentum") == 3


def test_j8_observe_never_blocks_but_logs(clock, caplog):
    record("005160", LIVE["005160"], kst(10, 0), src="p1")
    leaf().apply_mode("buy", "observe")
    clock.set(10, 0)
    assert gate("005160") is False
    assert gate("005160") is False
    assert len(lines(caplog, "[status_block_buy_would_skip]")) == 1
    assert lines(caplog, "[status_block_buy_skip]") == []


def test_j8_off_never_blocks(clock):
    record("005160", LIVE["005160"], kst(10, 0), src="p1")
    leaf().apply_mode("buy", "off")
    clock.set(10, 0)
    assert gate("005160") is False


def test_j8_buy_gate_never_raises(clock, monkeypatch):
    record("005160", LIVE["005160"], kst(10, 0), src="p1")

    def _boom():
        raise RuntimeError("clock broken")

    monkeypatch.setattr(leaf(), "_now_kst", _boom)
    assert leaf().buy_gate("005160", "momentum") is False


def test_j8_status_buy_blocked_fail_open_with_debug_trace(clock, monkeypatch, caplog):
    """M20 — `_status_buy_blocked` 는 판정 예외에서 False(fail-closed 금지) + DEBUG 흔적."""
    s = holder("momentum")

    def _boom(*a, **k):
        raise RuntimeError("leaf broken")

    monkeypatch.setattr(leaf(), "buy_gate", _boom)
    caplog.set_level(logging.DEBUG, logger="src.engine.strategy_base")
    assert s._status_buy_blocked("005160") is False
    assert s._account_soft_gate_blocked("005160") is False, "상태 판정 실패가 매수 경로를 닫았다"
    trace = [r for r in caplog.records
             if r.name == "src.engine.strategy_base"
             and r.getMessage().startswith("[status_block_gate_failed]")]
    assert trace, "완전 무음 fail-open 금지 — DEBUG 흔적"


def test_j8_none_ticker_short_circuits(monkeypatch):
    s = holder("momentum")
    called = []
    monkeypatch.setattr(leaf(), "buy_gate", lambda *a, **k: called.append(a) or True)
    assert s._status_buy_blocked(None) is False
    assert called == []


def test_j8_account_gate_consumes_status_gate(clock):
    """공통 게이트 `_account_soft_gate_blocked` 가 상태 차단을 본다(7전략 배선 = cycle233 G-1)."""
    s = holder("bull_flag_breakout")
    record("294140", LIVE["294140"], kst(10, 0), src="p1")
    clock.set(10, 0)
    assert s._account_soft_gate_blocked("294140") is True
    assert s._account_soft_gate_blocked("005930") is False


# ===========================================================================
# J17 — buy_targets
# ===========================================================================
def test_j17_buy_targets_union_minus_blocked_ordered(monkeypatch):
    from src.engine import scanner

    mom = holder("momentum")
    bfb = cand("bull_flag_breakout", scanned=["200001"], candidates=["200001", "200003"])
    vcp = cand("vcp_breakout", candidates=["200002"])
    vb = cand("volatility_breakout", scanned=["300001", "300003"], targets=["300001", "300003"])
    ltv = cand("long_tail_volatility", targets=["300002", "300004"])
    don = cand("donchian_swing", scanned=["400001"], candidates=["400001"])
    koj = cand("kojiro", enabled=False, scanned=["400009"], candidates=["400009"])  # 꺼진 전략
    hold(ltv, "300003")                          # 보유
    vb.state.pending_buys.add("300004")          # 주문 중
    don.state.sold_today.add("200003")           # 당일 매도
    monkeypatch.setattr(scanner, "ticker_prev_close", {
        "100002": 5000, "100001": 7000, "200001": 9000, "12345": 1, "0000A1": 1,
    })
    monkeypatch.setattr(scanner, "ticker_prices", {})   # 등락률 정렬(Q9)이 끼지 않게 — 그룹 순서만 잰다
    reg = make_sched(mom, bfb, vcp, vb, ltv, don, koj).registry

    got = leaf().buy_targets(reg)

    # 🔁 cycle369 R2 Q9 — 그룹 순서를 VB·LTV → BFB·VCP 로 바꿨다(09:00 에 급등 목록이 비어 있고
    # BFB·VCP 첫 매수는 09:05 라 5분 여유가 있다. P1 의 등락률 정렬·스윙 제외는
    # `test_cycle369_r2_buy_observability.py::test_q9_*` 가 잰다).
    assert got == [
        "100001", "100002",          # ① momentum 급등 목록(다른 후보에 없는 prev_close 키)
        "300001", "300002",          # ② VB·LTV
        "200001", "200002",          # ③ BFB·VCP
        "400001",                    # ④ donchian·kojiro(꺼진 kojiro 제외)
    ], got
    assert len(got) == len(set(got)), "중복 조회"


def test_j17b_prev_close_ignored_when_momentum_disabled(monkeypatch):
    from src.engine import scanner

    mom = holder("momentum", enabled=False)
    bfb = cand("bull_flag_breakout", candidates=["200001"])
    monkeypatch.setattr(scanner, "ticker_prev_close", {"100001": 7000})
    got = leaf().buy_targets(make_sched(mom, bfb).registry)
    assert got == ["200001"]


def test_j17c_buy_targets_does_not_mutate_strategy_state(monkeypatch):
    from src.engine import scanner

    bfb = cand("bull_flag_breakout", candidates=["200001"])
    before = dict(bfb._candidates)
    monkeypatch.setattr(scanner, "ticker_prev_close", {})
    leaf().buy_targets(make_sched(bfb).registry)
    assert bfb._candidates == before


# ===========================================================================
# J20 — P0 시각
# ===========================================================================
def test_j20_pre_pass_time():
    base = make_sched(cand("bull_flag_breakout"), holder("momentum")).registry
    assert leaf().pre_pass_time(base) == time(8, 45)
    nxt = make_sched(cand("long_tail_volatility", boards=("pre_nxt", "main"))).registry
    assert leaf().pre_pass_time(nxt) == time(7, 59)
    off = make_sched(cand("long_tail_volatility", enabled=False, boards=("pre_nxt", "main"))).registry
    assert leaf().pre_pass_time(off) == time(8, 45), "꺼진 전략의 pre_nxt 는 무시"


# ===========================================================================
# 패스 — P0 · P1 · INC
# ===========================================================================
def _cand_sched(*tickers, sid="bull_flag_breakout"):
    return make_sched(cand(sid, scanned=list(tickers), candidates=list(tickers)))


@pytest.mark.asyncio
async def test_j3_pre_clean_does_not_count_p1_rereads(clock, fetch, dblog, caplog):
    """J3 · K16 · M25 — 장 전 clean 을 판정 완료로 세면 첫날을 놓친다."""
    sched = _cand_sched("005160")
    fetch.table["005160"] = clean("005160")
    clock.set(8, 45)
    await leaf().run_pre_pass(sched)
    assert gate("005160", "bull_flag_breakout") is False

    fetch.table["005160"] = LIVE["005160"]
    clock.set(9, 0, 0)
    await leaf().run_buy_pass(sched, kind="p1")
    assert fetch.count("005160") == 2, "P1 이 장 전 clean 종목을 건너뛰었다"
    clock.set(9, 0, 30)
    assert gate("005160", "bull_flag_breakout") is True
    chk = lines(caplog, "[status_block_pre_session_check]")
    assert len(chk) == 1
    assert field(chk[0], "pre") == "N" and field(chk[0], "in") == "Y"


@pytest.mark.asyncio
async def test_j3b_p0_reads_holdings_and_candidates(clock, fetch, dblog):
    s = cand("bull_flag_breakout", candidates=["200001"])
    hold(s, "005160")
    sched = make_sched(s)
    clock.set(8, 45)
    await leaf().run_pre_pass(sched)
    assert sorted(set(fetch.calls)) == ["005160", "200001"]


@pytest.mark.asyncio
async def test_j4_j19_unknown_retried_three_times_then_given_up(clock, fetch, dblog, caplog):
    sched = _cand_sched("043090")
    fetch.table["043090"] = LIVE["043090"]
    clock.set(9, 0, 0)
    await leaf().run_buy_pass(sched, kind="p1")
    for m in (1, 2, 3, 4):
        clock.set(9, m, 0)
        await leaf().run_buy_pass(sched, kind="inc")
    assert fetch.count("043090") == 3, "모름 재시도 상한 3회/일"
    assert gate("043090", "bull_flag_breakout") is False
    # 🔁 cycle369 R2 Q10 — 첫 회 + 상한 도달(giveup=1) 때 한 번 더(giveup 이 보여야 한다)
    unk = lines(caplog, "[status_block_unknown]")
    assert len(unk) == 2 and field(unk[-1], "giveup") == "1", unk


@pytest.mark.asyncio
async def test_inc_reads_only_new_targets(clock, fetch, dblog):
    s = cand("bull_flag_breakout", candidates=["200001"])
    sched = make_sched(s)
    clock.set(9, 0, 0)
    await leaf().run_buy_pass(sched, kind="p1")
    clock.set(9, 1, 0)
    await leaf().run_buy_pass(sched, kind="inc")
    assert fetch.calls == ["200001"], "INC 가 이미 장중 판정한 종목을 다시 읽었다(비용)"
    s._candidates["200009"] = {"prev_close": 1}   # 장중 재-prepare 로 새 후보
    s._scanned.append("200009")
    clock.set(9, 2, 0)
    await leaf().run_buy_pass(sched, kind="inc")
    assert fetch.calls == ["200001", "200009"]


@pytest.mark.asyncio
async def test_p1_skips_tickers_already_judged_in_session_by_hook(clock, fetch, dblog, caplog):
    sched = _cand_sched("005160", "294140")
    clock.set(9, 0, 0)
    leaf().observe_fhkst("294140", LIVE["294140"])   # 급등 스캔 등이 먼저 읽었다
    await leaf().run_buy_pass(sched, kind="p1")
    assert fetch.calls == ["005160"]
    p1 = [m for m in lines(caplog, "[status_block_pass]") if field(m, "kind") == "p1"]
    assert p1 and field(p1[-1], "skipped_seen") == "1"


@pytest.mark.asyncio
async def test_p1_rereads_tickers_seen_only_before_open_by_hook(clock, fetch, dblog):
    """장 전(08:59) 훅 기록은 판정 완료가 아니다 — P1 이 다시 읽는다."""
    sched = _cand_sched("005160")
    clock.set(8, 59)
    leaf().observe_fhkst("005160", clean("005160"))
    fetch.table["005160"] = LIVE["005160"]
    clock.set(9, 0, 0)
    await leaf().run_buy_pass(sched, kind="p1")
    assert fetch.calls == ["005160"]
    assert gate("005160", "bull_flag_breakout") is True


@pytest.mark.asyncio
async def test_j18_p1_wall_clock_cap_25s_then_inc_continues(clock, fetch, dblog, caplog, monkeypatch):
    """J18 · K21 · M32 — P1 이 25초를 넘기면 끊고(`truncated=1`) 나머지는 INC 가 읽는다.

    09:00:30 첫 청산 패스가 P1 때문에 밀리지 않게 하는 상한이다.
    """
    lf = leaf()
    fake = [0.0]
    monkeypatch.setattr(lf, "_monotonic", lambda: fake[0])
    fetch.on_call = lambda _t: fake.__setitem__(0, fake[0] + 10.0)
    tickers = ["100001", "100002", "100003", "100004", "100005"]
    sched = _cand_sched(*tickers)
    clock.set(9, 0, 0)
    await lf.run_buy_pass(sched, kind="p1")
    first = list(fetch.calls)
    assert first == tickers[:3], first
    p1 = [m for m in lines(caplog, "[status_block_pass]") if field(m, "kind") == "p1"]
    assert p1 and field(p1[-1], "truncated") == "1"

    clock.set(9, 1, 0)
    await lf.run_buy_pass(sched, kind="inc")
    assert fetch.calls[3:] == tickers[3:], "잘린 나머지를 INC 가 읽어야 한다"


@pytest.mark.asyncio
async def test_p1_paces_between_calls(clock, fetch, dblog, monkeypatch):
    """종목 간 0.05초 페이싱(`open_price_rest._TICKER_SLEEP_S` 선례) — 시세 풀 한도 보호.

    페이싱은 `asyncio.sleep` 이든 `_sleep` seam 이든 된다(둘 다 엿본다).
    """
    lf = leaf()
    slept: list[float] = []
    real_sleep = asyncio.sleep

    async def _spy(secs, *a, **k):
        slept.append(float(secs))
        await real_sleep(0)

    monkeypatch.setattr(asyncio, "sleep", _spy)
    monkeypatch.setattr(lf, "_sleep", _spy, raising=False)
    sched = _cand_sched("100001", "100002", "100003")
    clock.set(9, 0, 0)
    await lf.run_buy_pass(sched, kind="p1")
    assert len(fetch.calls) == 3
    assert sum(1 for s in slept if s >= 0.05) >= 2, f"페이싱 없음: {slept}"


# ===========================================================================
# J22 — 영속 요약
# ===========================================================================
@pytest.mark.asyncio
async def test_j22_summary_written_only_on_change(clock, fetch, dblog):
    sched = _cand_sched("005160", "005930")
    fetch.table["005160"] = LIVE["005160"]
    clock.set(9, 0, 0)
    await leaf().run_buy_pass(sched, kind="p1")
    assert len(dblog.lines("[status_block_summary]")) == 1
    clock.set(9, 1, 0)
    await leaf().run_buy_pass(sched, kind="inc")
    assert len(dblog.lines("[status_block_summary]")) == 1, "변화가 없으면 쓰지 않는다"


@pytest.mark.asyncio
async def test_j22b_no_summary_when_all_clean(clock, fetch, dblog):
    sched = _cand_sched("005930")
    clock.set(9, 0, 0)
    await leaf().run_buy_pass(sched, kind="p1")
    assert dblog.lines("[status_block_summary]") == []


# ===========================================================================
# E6 · E7 — 두 킬스위치 축
# ===========================================================================
@pytest.mark.asyncio
async def test_e6_buy_off_reads_nothing_but_hook_still_records(clock, fetch, dblog, db_modes):
    db_modes(buy="off")
    sched = _cand_sched("005160")
    fetch.table["005160"] = LIVE["005160"]
    clock.set(8, 45)
    await leaf().run_pre_pass(sched)
    clock.set(9, 0, 0)
    await leaf().run_buy_pass(sched, kind="p1")
    clock.set(9, 1, 0)
    await leaf().run_buy_pass(sched, kind="inc")
    assert fetch.calls == [], "매수 차단 off = 후보 조회 0"
    leaf().observe_fhkst("294140", LIVE["294140"])
    assert "294140" in blocks_by_ticker(), "off 에서도 관측 훅 기록은 계속(비용 0)"
    assert gate("294140") is False


@pytest.mark.asyncio
async def test_e7_axes_are_independent_sell_off_buy_on(clock, fetch, dblog, db_modes):
    db_modes(sell="off", buy=None)
    s = cand("bull_flag_breakout", candidates=["005160"])
    hold(s, "294140")
    sched = make_sched(s)
    fetch.table["005160"] = LIVE["005160"]
    fetch.table["294140"] = LIVE["294140"]
    clock.set(9, 0, 0)
    await leaf().run_buy_pass(sched, kind="p1")
    clock.set(9, 0, 30)
    await leaf().run_sell_pass(sched)
    assert gate("005160", "bull_flag_breakout") is True
    assert sched.order_engine.calls == []
    assert fetch.count("294140") == 0


@pytest.mark.asyncio
async def test_e7b_axes_are_independent_sell_on_buy_off(clock, fetch, dblog, db_modes):
    db_modes(sell=None, buy="off")
    s = cand("bull_flag_breakout", candidates=["005160"])
    hold(s, "294140")
    sched = make_sched(s)
    fetch.table["005160"] = LIVE["005160"]
    fetch.table["294140"] = LIVE["294140"]
    clock.set(9, 0, 0)
    await leaf().run_buy_pass(sched, kind="p1")
    clock.set(9, 0, 30)
    await leaf().run_sell_pass(sched)
    assert fetch.count("005160") == 0
    assert sched.order_engine.fired() == [("294140", "bull_flag_breakout")]


# ===========================================================================
# J21 · J26 — task_loop (planner) : 가짜 시계로 하루를 돌린다
#
# 루프는 `_now_kst()` 로 시각을 읽고 **`_sleep(seconds)` 또는 `sched._wait_until(t)`**
# 로만 기다린다(둘 다 이 가짜 시계를 전진시킨다). 패스 본체는 모듈 전역 이름
# `run_pre_pass`·`run_buy_pass(kind=...)`·`run_sell_pass` 로 부른다(여기서 기록기로 교체).
# ===========================================================================
class _LoopRig:
    def __init__(self, clock, sched, monkeypatch, *, horizon=None):
        self.events: list[tuple[str, datetime]] = []
        self.clock = clock
        self.sched = sched
        self.horizon = horizon
        self.spins = 0
        lf = leaf()

        async def _pre(s, *a, **k):
            self.events.append(("p0", clock.now))

        async def _buy(s, *a, **k):
            self.events.append((str(k.get("kind", a[0] if a else "?")), clock.now))

        async def _sell(s, *a, **k):
            self.events.append(("sell", clock.now))

        monkeypatch.setattr(lf, "run_pre_pass", _pre)
        monkeypatch.setattr(lf, "run_buy_pass", _buy)
        monkeypatch.setattr(lf, "run_sell_pass", _sell)

        async def _sleep(secs, *a, **k):
            self._spin()
            clock.advance(max(float(secs), 0.001))
            self._check_horizon()

        async def _wait_until(target, *a, **k):
            self._spin()
            tgt = clock.now.replace(hour=target.hour, minute=target.minute,
                                    second=target.second, microsecond=0)
            if tgt > clock.now:
                clock.now = tgt
            else:
                clock.advance(0.001)
            self._check_horizon()

        monkeypatch.setattr(lf, "_sleep", _sleep, raising=False)
        sched._wait_until = _wait_until

        async def _no_seed(*a, **k):
            return {}

        # 🔁 cycle369 R2 Q4 — task_loop 시작 때 읽는 발사 횟수 seam 을 막아 DB 에 닿지 않게(밀폐)
        monkeypatch.setattr(lf, "_load_fire_counts", _no_seed, raising=False)

    def _spin(self):
        self.spins += 1
        if self.spins > 400_000:
            raise AssertionError("루프가 시계를 전진시키지 않고 돈다")

    def _check_horizon(self):
        if self.horizon is not None and self.clock.now >= self.horizon:
            self.sched._running = False

    def of(self, kind):
        return [t for k, t in self.events if k == kind]

    async def run(self, timeout=30.0):
        await asyncio.wait_for(leaf().task_loop(self.sched), timeout=timeout)


def _within(t: datetime, start: datetime, tol_s: float = 2.0) -> bool:
    return start <= t <= start + timedelta(seconds=tol_s)


@pytest.mark.asyncio
async def test_j21_restart_mid_session_runs_p1_and_sell_immediately(clock, dblog, monkeypatch):
    """10:31:00 재시작 → 즉시 P1 + 즉시 청산 1회. 다음 청산 칸은 10:35:30(격자 09:00:30 + k·300s)."""
    sched = _cand_sched("200001")
    clock.set(10, 31, 0)
    rig = _LoopRig(clock, sched, monkeypatch, horizon=kst(10, 31, 50))
    await rig.run()
    assert len(rig.of("p1")) == 1 and _within(rig.of("p1")[0], kst(10, 31))
    assert len(rig.of("sell")) == 1 and _within(rig.of("sell")[0], kst(10, 31))
    assert rig.of("p0") == [], "09:00 이후 재시작에 장 전 패스는 없다"
    assert rig.of("inc") == [], "INC 는 P1 뒤 60초부터"


@pytest.mark.asyncio
async def test_j21b_restart_before_open_runs_p0_immediately(clock, dblog, monkeypatch):
    sched = _cand_sched("200001")
    clock.set(8, 50, 0)
    rig = _LoopRig(clock, sched, monkeypatch, horizon=kst(8, 50, 30))
    await rig.run()
    assert len(rig.of("p0")) == 1 and _within(rig.of("p0")[0], kst(8, 50))
    assert rig.of("p1") == [] and rig.of("sell") == []


@pytest.mark.asyncio
async def test_j21c_start_after_close_reads_nothing_and_exits(clock, dblog, monkeypatch, caplog):
    sched = _cand_sched("200001")
    clock.set(15, 40, 0)
    rig = _LoopRig(clock, sched, monkeypatch)
    await rig.run(timeout=5.0)
    assert rig.events == []
    ex = lines(caplog, "[status_exit_loop_exit]")
    assert ex and field(ex[-1], "reason") == "after_close"


@pytest.mark.asyncio
async def test_j21d_not_running_exits_immediately(clock, dblog, monkeypatch, caplog):
    sched = _cand_sched("200001")
    sched._running = False
    clock.set(10, 0, 0)
    rig = _LoopRig(clock, sched, monkeypatch)
    await rig.run(timeout=2.0)
    assert rig.events == []
    ex = lines(caplog, "[status_exit_loop_exit]")
    assert ex and field(ex[-1], "reason") == "running_false"


@pytest.mark.asyncio
async def test_j26_full_day_schedule(clock, dblog, monkeypatch, caplog):
    """J26 — 07:45 부팅부터 루프 종료까지 하루치 일정.

    P0 08:45 · P1 09:00:05(🔁 cycle369 R2 Q9 — 09:00 + 캐시 TTL 5초) · 청산 09:00:30 + k·300s(마지막 15:25:30, 78회) ·
    INC 60초마다 `< 15:20` · 15:28 이후 아무것도 없음 · `[status_exit_loop_exit] reason=after_close`.
    """
    sched = _cand_sched("200001")
    clock.set(7, 45, 0)
    rig = _LoopRig(clock, sched, monkeypatch)
    await rig.run(timeout=40.0)

    p0, p1, sells, incs = rig.of("p0"), rig.of("p1"), rig.of("sell"), rig.of("inc")
    assert len(p0) == 1 and _within(p0[0], kst(8, 45)), p0
    assert len(p1) == 1 and _within(p1[0], kst(9, 0, 5)), p1

    slots = [kst(9, 0, 30) + timedelta(seconds=300 * k) for k in range(78)]
    assert slots[-1] == kst(15, 25, 30)
    assert len(sells) == 78, f"청산 패스 {len(sells)}회 (기대 78)"
    for slot in slots:
        # 청산 패스는 칸 시작부터 5초 안(루프 틱 크기 자유) · P0/P1 은 2초 안(첫날 공백 최소화)
        assert sum(1 for t in sells if _within(t, slot, 5.0)) == 1, f"격자 칸 {slot.time()} 누락/중복"
    assert all(t < kst(15, 28) for _k, t in rig.events), "15:28 이후 패스"

    assert incs, "INC 가 한 번도 없었다"
    assert incs[0] >= p1[0] + timedelta(seconds=59.9)
    assert all(t < kst(15, 20) for t in incs), "INC 는 15:20 매수 컷 전까지"
    gaps = [(b - a).total_seconds() for a, b in zip(incs, incs[1:])]
    assert min(gaps) >= 59.9, "INC 간격 60초"
    assert len(incs) >= 370, len(incs)

    ex = lines(caplog, "[status_exit_loop_exit]")
    assert ex and field(ex[-1], "reason") == "after_close"


@pytest.mark.asyncio
async def test_j26b_pre_nxt_strategy_moves_p0_to_0759(clock, dblog, monkeypatch):
    sched = make_sched(cand("long_tail_volatility", boards=("pre_nxt", "main"), targets=["300001"]))
    clock.set(7, 45, 0)
    rig = _LoopRig(clock, sched, monkeypatch, horizon=kst(8, 0, 30))
    await rig.run()
    p0 = rig.of("p0")
    assert len(p0) == 1 and _within(p0[0], kst(7, 59)), p0
