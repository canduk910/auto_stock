"""cycle369 round 2 Red — 매수 차단 쪽 정확성·관측. Q6(메모리 위생) · Q8 · Q9 · Q10.

| 절 | main-session 결정 | round-1 결함 |
|---|---|---|
| Q6 | P0 가 **모든** 날짜별 저장소에서 다른 날 항목을 지운다 | P0 가 `_unknown_attempts`·`_fires` 만 비웠다 — `_emitted`·`_skip_counts`·`_pre_seen`·`_in_seen`·`_buy_flags`·`_armed`·`_passes` 가 날마다 자란다 |
| Q8 | 패스가 한 조회는 **한 번만** 기록한다. `src` 는 패스 이름(`p0`/`p1`/`inc`/`sell`) | 관측 훅(src=fetch) + 패스(src=p1) 이중 기록 → 모름 3회 상한이 실제로는 2회 조회에서 끝나고, 차단의 `src` 가 늘 `fetch` |
| Q9 | P1 시작 = `BUY_OPEN_TIME + condition._PRICE_CACHE_TTL`(09:00:05) · P1 순서 = `scanner.ticker_prices` 로 +29% 에 가까운 순 → VB·LTV → BFB·VCP · P1 은 스윙(donchian·kojiro)을 읽지 않는다 | 08:59:55~09:00:00 조회가 5초 캐시로 09:00:00~05 P1 에 돌아와 「장중 clean」 으로 봉인된다(tester 발견 1). 09:00 에 급등 목록이 비어 P1 이 진입 09:05 인 BFB·VCP 를 먼저 읽는다 |
| Q10 | `[status_block_armed] cand=` 와 스냅샷 `cand` 는 `buy_targets` 멤버십 · skip 로그·카운트는 그 전략의 후보일 때만(momentum·VB 발사점은 항상) · `_passes[kind]` 를 패스 끝에 기록 · `[status_block_summary]` 에 `skips=` · 모름이 상한에 닿으면 `[status_block_unknown]` 을 한 번 더 | `cand=0` 리터럴 · 후보 아닌 전략도 skip 기록 · `passes` 항상 `{}` · `giveup=1` 이 영영 안 보인다 |
| 🔁 R3 F1 | P0 창의 위쪽 끝 = `BUY_OPEN_TIME`(09:00:00) — P1 만 09:00:05 | R2 가 P0 창을 09:00:05 까지 늘려 09:00:00~05 재시작이 캐시된 장 전 clean 을 「장중 clean」 으로 봉인(tester replay F2 · Q9l) |
| 🔁 R3 F5 | `cand` = `buy_targets(reg)` 멤버십 | 보유·주문중·당일매도 종목이 후보 구조에 남아 있으면 `cand=1` |
| 🔁 R3 F6 | Q6 퍼지에 발사 종목 · INC 스윙 포함 · momentum 급등 목록 cand · P0 armed cand | 생존 돌연변이 Q6c3 · Q9f · Q10k · Q10l |

Q9 의 스윙 제외 근거 = 스윙 매수 폴(09:05~09:30)이 매수 평가 **직전에** 같은 조회를 해 관측 훅이
기록한다(J13 — 추가 호출 0 으로 결정적). P1 25초 예산을 거기에 쓸 이유가 없다.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta

import pytest

from tests.unit.engine._cycle369_support import (
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
    field,
    hold,
    holder,
    kst,
    leaf,
    lines,
    make_sched,
    open_info,
    overheat,
    record,
)

pytestmark = [
    pytest.mark.unit,
    pytest.mark.real_status_watch,
    pytest.mark.usefixtures("no_real_kis"),
]

_T = "005160"


@pytest.fixture(autouse=True)
def _info(caplog, db_modes, monkeypatch):
    open_info(caplog)
    from src.engine import scanner

    monkeypatch.setattr(scanner, "ticker_prev_close", {})
    monkeypatch.setattr(scanner, "ticker_prices", {})
    try:
        from src.engine import account_risk_watcher

        account_risk_watcher.reset_state_for_test()
    except Exception:
        pass


@pytest.fixture
def quote(monkeypatch):
    """`condition.kis_get_quote` 교체 — **진짜** `fetch_stock_detail` → 캐시 → 관측 훅 경로."""
    from src.api import condition

    state = {"table": {}, "calls": []}

    async def _fake(url, tr_id, params, *a, **k):
        t = params.get("fid_input_iscd")
        state["calls"].append(t)
        out = state["table"].get(t)
        if out is None:
            out = clean(t)
        return {"output": dict(out), "rt_cd": "0", "msg_cd": "MCA00000", "msg1": "정상처리"}

    condition.clear_caches()
    monkeypatch.setattr(condition, "kis_get_quote", _fake)
    yield state
    condition.clear_caches()


def _armed_lines(caplog):
    return lines(caplog, "[status_block_armed]", min_level=logging.WARNING)


# ===========================================================================
# Q8 — 한 조회 = 한 기록 · src = 패스
# ===========================================================================
@pytest.mark.asyncio
@pytest.mark.parametrize("kind,hms,expected_phase", [
    ("p0", (8, 45, 0), "pre"),
    ("p1", (9, 0, 5), "in"),
])
async def test_q8_pass_fetch_is_recorded_with_pass_src(clock, quote, dblog, caplog, kind, hms, expected_phase):
    """패스가 새로 조회한 값의 차단 `src` 는 그 패스다 — 관측 훅이 먼저 `fetch` 로 적어 버리면 안 된다."""
    sched = make_sched(cand("bull_flag_breakout", scanned=[_T], candidates=[_T]))
    quote["table"][_T] = overheat(_T)
    clock.set(*hms)
    if kind == "p0":
        await leaf().run_pre_pass(sched)
    else:
        await leaf().run_buy_pass(sched, kind="p1")
    assert quote["calls"] == [_T], "전제 — 진짜 조회 경로(훅 포함)를 탔다"
    armed = _armed_lines(caplog)
    assert len(armed) == 1
    assert field(armed[0], "src") == kind, f"패스 조회인데 src={field(armed[0], 'src')}"
    assert field(armed[0], "phase") == expected_phase
    assert blocks_by_ticker()[_T]["src"] == kind


@pytest.mark.asyncio
async def test_q8_sell_pass_fetch_src_is_sell(clock, quote, dblog, caplog):
    s = holder("bull_flag_breakout")
    hold(s, _T)
    sched = make_sched(s)
    quote["table"][_T] = overheat(_T)
    clock.set(10, 0, 30)
    await leaf().run_sell_pass(sched)
    armed = _armed_lines(caplog)
    assert armed and field(armed[0], "src") == "sell"


@pytest.mark.asyncio
async def test_q8_unknown_counts_once_per_fetch(clock, quote, dblog, caplog):
    """모름 3회 상한 = **조회 3번**. 훅 + 패스가 한 조회를 두 번 세면 2번 조회로 giveup 한다.

    그러면 09:00~09:01 시세 풀이 잠깐 흔들린 종목의 장 전 차단이 장중 확인 없이 하루 종일 남는다.
    """
    from src.api import condition

    sched = make_sched(cand("bull_flag_breakout", scanned=["043090"], candidates=["043090"]))
    quote["table"]["043090"] = LIVE["043090"]
    clock.set(9, 0, 5)
    await leaf().run_buy_pass(sched, kind="p1")
    for m in (1, 2, 3, 4):
        condition.clear_caches()                       # 5초 캐시 만료(가짜 시계와 무관한 실시간 캐시)
        clock.set(9, m, 5)
        await leaf().run_buy_pass(sched, kind="inc")
    n = quote["calls"].count("043090")
    assert n == 3, f"모름 재시도는 조회 3번이어야 한다 — 실제 {n}번(이중 기록이면 2)"


@pytest.mark.asyncio
async def test_q8_hook_only_read_keeps_src_fetch(clock, quote, dblog, caplog):
    """대조 — 패스 밖(급등 스캔·기준가 REST·스윙 폴)의 조회는 여전히 `src=fetch`."""
    from src.api import condition

    quote["table"][_T] = overheat(_T)
    clock.set(9, 40)
    await condition.fetch_stock_detail(_T)
    armed = _armed_lines(caplog)
    assert armed and field(armed[0], "src") == "fetch"


# ===========================================================================
# Q9 — P1 은 09:00:05 · 순서 · 스윙 제외
# ===========================================================================
class _Recorder:
    """패스를 기록기로 바꾸고 가짜 시계로 루프를 돌린다(J26 `_LoopRig` 동형 · 이 파일 전용)."""

    def __init__(self, clock, sched, monkeypatch, *, horizon: datetime):
        self.events: list[tuple[str, datetime]] = []
        lf = leaf()

        async def _pre(s, *a, **k):
            self.events.append(("p0", clock.now))

        async def _buy(s, *a, **k):
            self.events.append((str(k.get("kind", a[0] if a else "?")), clock.now))

        async def _sell(s, *a, **k):
            self.events.append(("sell", clock.now))

        async def _seed(*a, **k):
            return {}

        monkeypatch.setattr(lf, "run_pre_pass", _pre)
        monkeypatch.setattr(lf, "run_buy_pass", _buy)
        monkeypatch.setattr(lf, "run_sell_pass", _sell)
        monkeypatch.setattr(lf, "_load_fire_counts", _seed, raising=False)

        async def _sleep(secs, *a, **k):
            clock.advance(max(float(secs), 0.001))
            if clock.now >= horizon:
                sched._running = False

        async def _wait_until(target, *a, **k):
            tgt = clock.now.replace(hour=target.hour, minute=target.minute,
                                    second=target.second, microsecond=0)
            clock.now = tgt if tgt > clock.now else clock.now + timedelta(milliseconds=1)
            if clock.now >= horizon:
                sched._running = False

        monkeypatch.setattr(lf, "_sleep", _sleep, raising=False)
        sched._wait_until = _wait_until
        self.sched = sched

    def of(self, kind):
        return [t for k, t in self.events if k == kind]

    async def run(self):
        await asyncio.wait_for(leaf().task_loop(self.sched), timeout=20.0)


@pytest.mark.asyncio
@pytest.mark.parametrize("start", [(8, 59, 58), (9, 0, 0), (9, 0, 2)], ids=["0859_58", "0900_00", "0900_02"])
async def test_q9_p1_waits_for_price_cache_ttl_after_open(clock, dblog, monkeypatch, start):
    """P1 첫 실행은 09:00:00 + 캐시 TTL(5초) 이후 — 장 전 조회의 캐시가 장중 clean 으로 봉인되지 않게."""
    from src.api import condition

    ttl = float(condition._PRICE_CACHE_TTL)
    p1_start = kst(9, 0, 0) + timedelta(seconds=ttl)
    assert p1_start == kst(9, 0, 5), "전제 — 현행 캐시 TTL 5초(바뀌면 이 테스트가 먼저 붉어진다)"
    sched = make_sched(cand("bull_flag_breakout", candidates=["200001"]))
    clock.set(*start)
    rig = _Recorder(clock, sched, monkeypatch, horizon=kst(9, 0, 20))
    await rig.run()
    p1 = rig.of("p1")
    assert len(p1) == 1, p1
    assert p1_start <= p1[0] <= p1_start + timedelta(seconds=2), (
        f"P1 이 {p1[0].time()} 에 돌았다 — {p1_start.time()} 전이면 5초 캐시가 장 전 값을 장중 판정으로 봉인한다"
    )


@pytest.mark.asyncio
async def test_q9_p1_order_closeness_then_vb_ltv_then_bfb_vcp_without_swing(clock, fetch, dblog, monkeypatch):
    """P1 읽는 순서 = (1) `scanner.ticker_prices` 등락률이 +29% 에 가까운 순 → (2) 값 없는 종목은
    VB·LTV → BFB·VCP. 스윙(donchian·kojiro) 후보는 P1 이 읽지 않는다(스윙 폴의 훅이 덮는다).
    """
    from src.engine import scanner

    mom = holder("momentum")
    vb = cand("volatility_breakout", scanned=["300001", "300002"], targets=["300001", "300002"])
    ltv = cand("long_tail_volatility", targets=["300003"])
    bfb = cand("bull_flag_breakout", scanned=["200001"], candidates=["200001"])
    vcp = cand("vcp_breakout", candidates=["200002"])
    don = cand("donchian_swing", scanned=["400001"], candidates=["400001"])
    koj = cand("kojiro", scanned=["400002"], candidates=["400002"])
    sched = make_sched(mom, vb, ltv, bfb, vcp, don, koj)

    universe = ["100001", "200001", "200002", "300001", "300002", "300003", "400001", "400002"]
    monkeypatch.setattr(scanner, "ticker_prev_close", {t: 10000 for t in universe})

    def _px(rate):
        cur = int(10000 * (1 + rate / 100))
        return {"current_price": cur, "open_price": 10000, "change_rate": rate, "prdy_ctrt": rate}

    monkeypatch.setattr(scanner, "ticker_prices", {
        "200001": _px(28.0),     # BFB 후보지만 +29% 에 가장 가깝다
        "300002": _px(20.0),
        "100001": _px(10.0),     # 급등 목록(prev_close 에만 있는 종목)
        "400001": _px(28.5),     # 스윙 — 가까워도 P1 은 읽지 않는다
    })
    clock.set(9, 0, 5)
    await leaf().run_buy_pass(sched, kind="p1")
    assert fetch.calls == ["200001", "300002", "100001", "300001", "300003", "200002"], fetch.calls


@pytest.mark.asyncio
async def test_q9_swing_candidates_still_readable_by_hook_and_other_passes(clock, fetch, dblog):
    """스윙 제외는 **P1 한정**이다 — 스윙 후보도 `buy_targets` 에는 남는다(P0 는 읽는다)."""
    don = cand("donchian_swing", scanned=["400001"], candidates=["400001"])
    sched = make_sched(don)
    assert "400001" in leaf().buy_targets(sched.registry)
    clock.set(8, 45)
    await leaf().run_pre_pass(sched)
    assert "400001" in fetch.calls


# ===========================================================================
# Q10 — 관측 필드가 실제 값을 싣는다
# ===========================================================================
@pytest.mark.asyncio
async def test_q10_armed_cand_reflects_buy_targets_membership(clock, fetch, dblog, caplog):
    """`cand=1` = 그 순간 enabled 전략 후보(진입 필터가 놓친 첫날 = 운영 KPI). 리터럴 0 금지."""
    sched = make_sched(cand("bull_flag_breakout", scanned=[_T, "200001"], candidates=[_T, "200001"]))
    fetch.table[_T] = overheat(_T)
    clock.set(9, 0, 5)
    await leaf().run_buy_pass(sched, kind="p1")          # _T 해당(후보) · 200001 clean
    clock.set(9, 40)
    leaf().observe_fhkst("200001", overheat("200001"))   # 후보 — 훅이 뒤늦게 해당으로 읽음
    leaf().observe_fhkst("294140", LIVE["294140"])       # 어느 전략 후보도 아님
    cand_by = {field(m, "ticker"): field(m, "cand") for m in _armed_lines(caplog)}
    assert cand_by == {_T: "1", "200001": "1", "294140": "0"}, cand_by
    blocks = blocks_by_ticker()
    assert int(blocks[_T]["cand"]) == 1 and int(blocks["200001"]["cand"]) == 1
    assert int(blocks["294140"]["cand"]) == 0


@pytest.mark.asyncio
async def test_q10_held_ticker_block_is_not_a_candidate(clock, fetch, dblog, caplog):
    """보유 종목(청산 패스가 읽음)은 `buy_targets` 밖 — `cand=0`."""
    s = holder("bull_flag_breakout")
    hold(s, _T)
    sched = make_sched(s)
    fetch.table[_T] = overheat(_T)
    clock.set(10, 0, 30)
    await leaf().run_sell_pass(sched)
    armed = _armed_lines(caplog)
    assert armed and field(armed[0], "cand") == "0"


@pytest.mark.parametrize("sid,kw,counts", [
    pytest.param("bull_flag_breakout", dict(candidates=[]), False, id="bfb_not_candidate"),
    pytest.param("bull_flag_breakout", dict(candidates=[_T]), True, id="bfb_candidate"),
    pytest.param("vcp_breakout", dict(candidates=[]), False, id="vcp_not_candidate"),
    pytest.param("long_tail_volatility", dict(targets=[]), False, id="ltv_not_target"),
    pytest.param("long_tail_volatility", dict(targets=[_T]), True, id="ltv_target"),
    pytest.param("momentum", None, True, id="momentum_fire_point_always"),
    pytest.param("volatility_breakout", dict(targets=[]), True, id="vb_fire_point_always"),
])
def test_q10_skip_counted_only_for_that_strategys_candidates(clock, caplog, sid, kw, counts):
    """막기는 늘 막는다. **기록**만 「그 전략이 실제로 사려 했나」로 거른다.

    첫 문장 게이트 전략(LTV·BFB·VCP)은 후보가 아닌 종목의 틱에도 게이트를 지난다 — 그대로 세면
    `skips{sid:n}` 로 「어느 전략이 사려 했나」를 알 수 없다. momentum·VB 는 게이트가 발사점이라 항상 센다.
    """
    s = holder(sid) if kw is None else cand(sid, **kw)
    record(_T, overheat(_T), kst(10, 0), src="p1")
    clock.set(10, 0)
    assert s._account_soft_gate_blocked(_T) is True, "후보 여부와 무관하게 막기는 막는다"
    assert s._account_soft_gate_blocked(_T) is True
    skip_lines = [m for m in lines(caplog, "[status_block_buy_skip]") if field(m, "strategy") == sid]
    skips = blocks_by_ticker()[_T]["skips"]
    if counts:
        assert len(skip_lines) == 1 and skips.get(sid) == 2, (skip_lines, skips)
    else:
        assert skip_lines == [] and sid not in skips, (
            f"{sid} 는 이 종목을 후보로 가진 적이 없는데 skip 으로 기록됐다: {skips}"
        )


@pytest.mark.asyncio
async def test_q10_p1_pass_record_has_real_counts(clock, fetch, dblog):
    """`_passes[kind]` 를 패스 끝에 기록 → GET `today.passes` 가 더는 `{}` 가 아니다."""
    tickers = [_T, "043090", "200001", "005930"]
    sched = make_sched(cand("bull_flag_breakout", scanned=tickers, candidates=tickers))
    fetch.table[_T] = LIVE["005160"]                       # 해당
    fetch.table["043090"] = LIVE["043090"]                 # 모름(플래그 None)
    fetch.table["200001"] = RuntimeError("pool down")      # 조회 실패
    clock.set(9, 0, 5)
    await leaf().run_buy_pass(sched, kind="p1")
    passes = leaf().snapshot()["passes"]
    assert "p1" in passes, f"P1 기록 없음: {passes}"
    p = passes["p1"]
    assert int(p["targets"]) == 4 and int(p["read"]) == 4
    assert int(p["flagged"]) == 1
    assert int(p["fetch_fail"]) == 1
    assert int(p["unknown"]) in (1, 2), "043090(모름) — fetch_fail 포함 여부는 구현 선택"
    assert int(p["truncated"]) == 0
    assert int(p["elapsed_ms"]) >= 0
    assert str(p["at"]).startswith(DAY.isoformat())


@pytest.mark.asyncio
async def test_q10_p0_and_inc_pass_records(clock, fetch, dblog):
    s = cand("bull_flag_breakout", scanned=["200001"], candidates=["200001"])
    sched = make_sched(s)
    clock.set(8, 45)
    await leaf().run_pre_pass(sched)
    clock.set(9, 0, 5)
    await leaf().run_buy_pass(sched, kind="p1")
    s._candidates["200009"] = {"prev_close": 1}
    s._scanned.append("200009")
    clock.set(9, 1, 5)
    await leaf().run_buy_pass(sched, kind="inc")
    passes = leaf().snapshot()["passes"]
    assert int(passes["p0"]["read"]) == 1
    assert int(passes["inc"]["read"]) == 1


@pytest.mark.asyncio
async def test_q10_summary_carries_skips(clock, fetch, dblog):
    """`[status_block_summary]` 는 매수 차단의 **유일한 영속 기록** — skip 횟수가 거기 실려야 한다."""
    mom = holder("momentum")
    bfb = cand("bull_flag_breakout", scanned=[_T], candidates=[_T])
    sched = make_sched(bfb, mom)
    fetch.table[_T] = overheat(_T)
    clock.set(9, 0, 5)
    await leaf().run_buy_pass(sched, kind="p1")
    mom._account_soft_gate_blocked(_T)
    mom._account_soft_gate_blocked(_T)
    clock.set(9, 1, 5)
    await leaf().run_buy_pass(sched, kind="inc")
    rows = dblog.lines("[status_block_summary]")
    assert rows, "요약이 한 번도 안 남았다"
    assert "momentum:2" in field(rows[-1], "skips"), rows[-1]


def test_q10_unknown_logged_again_when_giving_up(clock, caplog):
    """모름 첫 회 + 상한 도달(giveup) 때 한 번 더 — `giveup=1` 이 실제로 보인다."""
    for m in (0, 1, 2, 3):
        record("043090", LIVE["043090"], kst(9, m, 5), src="inc")
    ul = lines(caplog, "[status_block_unknown]")
    assert len(ul) == 2, ul
    assert (field(ul[0], "attempts"), field(ul[0], "giveup")) == ("1", "0")
    assert (field(ul[1], "attempts"), field(ul[1], "giveup")) == ("3", "1")


# ===========================================================================
# Q6 — P0 가 다른 날 항목을 전부 지운다 (메모리 위생)
# ===========================================================================
_STATIC = {"_GROUP"}


def _stale_containers(day) -> list[str]:
    """모듈 전역 dict·set·list 중 `day` 흔적(`date` repr 또는 ISO)이 남은 것."""
    lf = leaf()
    marks = (f"{day.year}, {day.month}, {day.day}", day.isoformat())
    out = []
    for name, val in vars(lf).items():
        if name.startswith("__") or name in _STATIC:
            continue
        if isinstance(val, (dict, set, list)):
            r = repr(val)
            if any(mk in r for mk in marks):
                out.append(name)
    return out


@pytest.mark.asyncio
async def test_q6_p0_purges_other_days_from_every_per_day_container(clock, fetch, dblog):
    tickers = [_T, "043090"]
    bfb = cand("bull_flag_breakout", scanned=list(tickers), candidates=list(tickers))
    mom = holder("momentum")
    hold(bfb, "016790")
    hold(bfb, "000545")                                # 🔁 R3 F6 — 실제로 쏘는 종목(발사 횟수 `_fires` 에 D 흔적)
    sched = make_sched(bfb, mom)
    fetch.table[_T] = LIVE["005160"]
    fetch.table["043090"] = LIVE["043090"]
    fetch.table["016790"] = LIVE["016790"]
    fetch.table["000545"] = LIVE["000545"]

    clock.set(8, 45)
    await leaf().run_pre_pass(sched)
    clock.set(9, 0, 5)
    await leaf().run_buy_pass(sched, kind="p1")
    mom._account_soft_gate_blocked(_T)                 # skip 카운트
    clock.set(9, 0, 30)
    await leaf().run_sell_pass(sched)                  # 016790 정지 대기 arm · 000545 발사
    assert sched.order_engine.fired() == [("000545", "bull_flag_breakout")], "전제 — D 에 한 번 쐈다"
    assert "_fires" in _stale_containers(DAY), "전제 — 발사 횟수 저장소에 D 흔적이 있다(🔁 R3 F6)"
    assert _stale_containers(DAY), "전제 — D 의 흔적이 있다"

    bfb._candidates.clear()
    bfb._scanned.clear()
    del bfb.state.positions["016790"]
    del bfb.state.positions["000545"]
    clock.set(8, 45, day=NEXT_DAY)
    await leaf().run_pre_pass(sched)
    left = _stale_containers(DAY)
    assert not left, f"D+1 P0 뒤에도 D 항목이 남은 저장소: {left} — 프로세스 수명 동안 자란다"


# ===========================================================================
# 🔁 cycle369 R3 F1 — P0 창의 위쪽 끝은 `BUY_OPEN_TIME`(09:00:00) · P1 만 09:00:05
#
# R2 Q9 가 P1 을 09:00:05 로 옮기면서 `due_actions` 가 같은 `p1_time` 을 P0 창의 위쪽 끝으로
# 썼다(`pre_time <= t < p1_time`). 그래서 09:00:00~05 에 시작한 루프(in-process 재시작 —
# `/api/trading/restart` 는 condition 5초 캐시를 비우지 않는다)가 P0 를 돌고, 08:59:5x 에 다른
# 소비자가 채운 캐시의 **장 전 clean** 을 `now>=09:00` 으로 기록해 「장중 clean」 으로 봉인했다.
# 그러면 P1 이 그 종목을 건너뛰어 지정 첫날 매수가 막히지 않는다(tester replay F2 · 리뷰 Q9l).
# ===========================================================================
def test_f1_planner_p0_window_ends_at_buy_open_time():
    lf = leaf()
    kw = dict(pre_time=lf.PRE_PASS_TIME, p1_time=lf._p1_start_time(), pre_done=False, p1_done=False,
              last_sell_at=None, last_inc_at=None)
    assert lf._p1_start_time() > lf.BUY_OPEN_TIME, "전제 — P1 은 09:00 + 캐시 TTL"
    assert lf.due_actions(kst(8, 59, 59), **kw) == ["pre"]
    for hms in ((9, 0, 0), (9, 0, 2), (9, 0, 4)):
        assert lf.due_actions(kst(*hms), **kw) == [], (
            f"{hms} — 09:00 이후인데 P0 가 돈다: 장 전 캐시 값이 「장중 clean」 으로 봉인된다"
        )
    assert lf.due_actions(kst(9, 0, 5), **kw) == ["buy_open"]


class _RealLoopF1:
    """실제 `task_loop` + 실제 패스 + **실제** condition 캐시·관측 훅. 대기만 가짜 시계로 전진."""

    def __init__(self, clock, sched, monkeypatch, *, horizon: datetime):
        lf = leaf()

        async def _no_seed(*a, **k):
            return {}

        async def _sleep(secs, *a, **k):
            clock.advance(max(float(secs), 0.001))
            if clock.now >= horizon:
                sched._running = False

        async def _wait_until(target, *a, **k):
            tgt = clock.now.replace(hour=target.hour, minute=target.minute,
                                    second=target.second, microsecond=0)
            clock.now = tgt if tgt > clock.now else clock.now + timedelta(milliseconds=1)
            if clock.now >= horizon:
                sched._running = False

        monkeypatch.setattr(lf, "_load_fire_counts", _no_seed, raising=False)
        monkeypatch.setattr(lf, "_sleep", _sleep, raising=False)
        sched._wait_until = _wait_until
        self.sched = sched

    async def run(self):
        await asyncio.wait_for(leaf().task_loop(self.sched), timeout=20.0)


@pytest.mark.asyncio
@pytest.mark.parametrize("prime,restart", [
    pytest.param((8, 59, 58), (9, 0, 2), id="primed_0859_58_restart_0900_02"),   # tester replay F2
    pytest.param((8, 59, 56), (9, 0, 0), id="primed_0859_56_restart_0900_00"),
    pytest.param((8, 59, 59), (9, 0, 3), id="primed_0859_59_restart_0900_03"),
])
async def test_f1_restart_in_first_5s_does_not_seal_cached_pre_session_clean(
    clock, quote, dblog, caplog, monkeypatch, prime, restart,
):
    """08:59:5x 캐시(장 전 clean) + 09:00:00~05 재시작 → 그 종목은 P1(09:00:05) 이 **새로** 읽어 막힌다."""
    from types import SimpleNamespace

    from src.api import condition

    # condition 5초 캐시를 가짜 시계에 묶는다(실시간 monotonic 이면 캐시가 테스트 내내 산다)
    monkeypatch.setattr(condition, "time", SimpleNamespace(monotonic=lambda: clock.now.timestamp()))
    sched = make_sched(cand("bull_flag_breakout", scanned=[_T], candidates=[_T]))

    quote["table"][_T] = clean(_T)                     # 장 전 값(전날 기준 — 지정 전)
    clock.set(*prime)
    await condition.fetch_stock_detail(_T)            # 같은 프로세스의 다른 소비자가 캐시를 채운다
    assert quote["calls"] == [_T], "전제 — 캐시 채움 1콜"
    quote["table"][_T] = overheat(_T)                  # 장중 값 = 단기과열 지정 첫날

    clock.set(*restart)
    await _RealLoopF1(clock, sched, monkeypatch, horizon=kst(9, 0, 20)).run()

    assert leaf().buy_gate(_T, "bull_flag_breakout") is True, (
        "09:00 직후 재시작의 P0 가 캐시된 장 전 clean 을 「장중 clean」 으로 봉인했다 — "
        "P1 이 그 종목을 건너뛰어 지정 첫날 매수가 뚫린다"
    )
    assert quote["calls"].count(_T) == 2, f"P1 이 캐시가 아닌 새 값을 읽어야 한다: {quote['calls']}"
    armed = [m for m in _armed_lines(caplog) if field(m, "ticker") == _T]
    assert armed and field(armed[-1], "phase") == "in" and field(armed[-1], "src") == "p1", armed


@pytest.mark.asyncio
async def test_f1_restart_before_open_still_runs_p0_control(clock, quote, dblog, monkeypatch):
    """대조 — 08:59:50 재시작은 P0 를 돈다(창 위쪽 끝을 당긴 것이지 P0 를 없앤 것이 아니다)."""
    from types import SimpleNamespace

    from src.api import condition

    monkeypatch.setattr(condition, "time", SimpleNamespace(monotonic=lambda: clock.now.timestamp()))
    sched = make_sched(cand("bull_flag_breakout", scanned=[_T], candidates=[_T]))
    quote["table"][_T] = overheat(_T)
    clock.set(8, 59, 50)
    await _RealLoopF1(clock, sched, monkeypatch, horizon=kst(8, 59, 55)).run()
    assert quote["calls"] == [_T], "08:59:50 재시작인데 P0 가 돌지 않았다"
    assert leaf().buy_gate(_T, "bull_flag_breakout") is True


# ===========================================================================
# 🔁 cycle369 R3 F5 — `cand` = `buy_targets(reg)` 멤버십 (보유·주문중·당일매도는 절대 1 이 아니다)
#
# R2 의 `_is_global_candidate` 는 전략 후보 구조만 봐서, 보유 종목이 BFB `_candidates` 에 남아
# 있거나 momentum 이 켜져 `ticker_prev_close` 에 있으면 청산 패스의 armed 줄이 `cand=1` 이 됐다
# (tester 탐침). `cand=1` KPI = 「진입 필터가 놓친 첫날」 이 부풀려진다.
# ===========================================================================
@pytest.mark.asyncio
async def test_f5_held_ticker_is_never_cand_even_if_still_in_candidates(clock, fetch, dblog, caplog, monkeypatch):
    from src.engine import scanner

    bfb = cand("bull_flag_breakout", scanned=[_T], candidates=[_T])
    hold(bfb, _T)
    sched = make_sched(bfb, holder("momentum"))
    monkeypatch.setattr(scanner, "ticker_prev_close", {_T: 10000})
    fetch.table[_T] = overheat(_T)
    clock.set(10, 0, 30)
    await leaf().run_sell_pass(sched)
    armed = [m for m in _armed_lines(caplog) if field(m, "ticker") == _T]
    assert armed and field(armed[0], "src") == "sell"
    assert field(armed[0], "cand") == "0", (
        f"보유 종목이 cand=1 로 찍혔다(BFB `_candidates`·momentum 급등 목록에 남아 있어도 buy_targets 밖): {armed[0]}"
    )
    assert int(blocks_by_ticker()[_T]["cand"]) == 0, "스냅샷 cand 도 buy_targets 멤버십이어야 한다"


@pytest.mark.asyncio
@pytest.mark.parametrize("state", ["pending", "sold_today"])
async def test_f5_pending_or_sold_today_ticker_is_not_cand(clock, fetch, dblog, caplog, state):
    """주문중·당일매도 종목도 `buy_targets` 밖 — 후보 구조에 남아 있어도 `cand=0`."""
    bfb = cand("bull_flag_breakout", scanned=[_T, "200001"], candidates=[_T, "200001"])
    getattr(bfb.state, "pending_buys" if state == "pending" else "sold_today").add(_T)
    sched = make_sched(bfb)
    clock.set(9, 0, 5)
    await leaf().run_buy_pass(sched, kind="p1")        # 패스가 registry 를 기억한다
    assert _T not in fetch.calls, "전제 — buy_targets 가 그 종목을 뺀다"
    clock.set(9, 40)
    leaf().observe_fhkst(_T, overheat(_T))             # 패스 밖 조회(훅)
    armed = [m for m in _armed_lines(caplog) if field(m, "ticker") == _T]
    assert armed and field(armed[0], "cand") == "0", armed
    assert int(blocks_by_ticker()[_T]["cand"]) == 0


# ===========================================================================
# 🔁 cycle369 R3 F6 — 생존 돌연변이 봉인 (Q9f · Q10k · Q10l)
# ===========================================================================
@pytest.mark.asyncio
async def test_q9f_inc_reads_swing_candidates_that_p1_skipped(clock, fetch, dblog):
    """스윙 제외는 **P1 한정** — INC 는 `buy_targets(registry)`(스윙 포함)를 읽는다(명세 §4.3 INC 행)."""
    don = cand("donchian_swing", scanned=["400001"], candidates=["400001"])
    bfb = cand("bull_flag_breakout", scanned=["200001"], candidates=["200001"])
    sched = make_sched(don, bfb)
    clock.set(9, 0, 5)
    await leaf().run_buy_pass(sched, kind="p1")
    assert "400001" not in fetch.calls, "전제 — P1 은 스윙을 읽지 않는다"
    clock.set(9, 1, 5)
    await leaf().run_buy_pass(sched, kind="inc")
    assert "400001" in fetch.calls, f"INC 가 스윙 후보를 빼먹었다: {fetch.calls}"


@pytest.mark.asyncio
@pytest.mark.parametrize("mom_enabled,expected", [(True, "1"), (False, "0")], ids=["momentum_on", "momentum_off"])
async def test_q10k_momentum_surge_list_membership_is_cand(clock, fetch, dblog, caplog, monkeypatch,
                                                           mom_enabled, expected):
    """momentum 이 켜져 있으면 `ticker_prev_close`(급등 목록)만의 종목도 후보 — 꺼져 있으면 아니다."""
    from src.engine import scanner

    bfb = cand("bull_flag_breakout", scanned=["200001"], candidates=["200001"])
    sched = make_sched(bfb, holder("momentum", enabled=mom_enabled))
    monkeypatch.setattr(scanner, "ticker_prev_close", {_T: 10000})
    clock.set(9, 0, 5)
    await leaf().run_buy_pass(sched, kind="p1")        # 패스가 registry 를 기억한다
    clock.set(9, 40)
    leaf().observe_fhkst(_T, overheat(_T))
    armed = [m for m in _armed_lines(caplog) if field(m, "ticker") == _T]
    assert armed and field(armed[0], "cand") == expected, armed
    assert str(int(blocks_by_ticker()[_T]["cand"])) == expected


@pytest.mark.asyncio
async def test_q10l_p0_armed_lines_carry_real_cand(clock, fetch, dblog, caplog):
    """P0(장 전)의 armed 줄 — 후보 종목 `cand=1`, 보유 전용 종목 `cand=0`."""
    bfb = cand("bull_flag_breakout", scanned=["200001"], candidates=["200001"])
    hold(bfb, _T)
    sched = make_sched(bfb)
    fetch.table["200001"] = overheat("200001")
    fetch.table[_T] = overheat(_T)
    clock.set(8, 45)
    await leaf().run_pre_pass(sched)
    by = {field(m, "ticker"): (field(m, "src"), field(m, "phase"), field(m, "cand")) for m in _armed_lines(caplog)}
    assert by.get("200001") == ("p0", "pre", "1"), by
    assert by.get(_T) == ("p0", "pre", "0"), by

