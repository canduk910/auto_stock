"""cycle403 Red — `EtfTrendStrategy`(`src/engine/strategies/etf_trend.py`) 행위: 신호 순서 · 사이징 · 청산 · 15:20 · 복구 · prepare.

명세 정본 = `_workspace/cycle403_etf_trend_spec.md` §4~§8 · §10-3~§10-7 (L4~L11)
설계 = `_workspace/design/2026-09-27_etf_trend_strategy.md` §3·§4·§5·§7.4

## Green 이 맞출 계약 (명세 §4~§7 이름 그대로 — 테스트가 직접 읽고 쓰는 상태)

| 이름 | 모양 |
|---|---|
| `EtfTrendStrategy(StrategyConfig)` | `DEFAULT_PARAMS` 를 `config.params` 에 병합(donchian 과 같은 모양) |
| `_candidates[t]` | `dict` — 키 `prev_close` · `line` · `n` · `atr`(= n, 사이징 ATR 키) · `atr20` · `tv20` · `ema60` · `cluster_key` |
| `_cluster_pairs` | `set`/`frozenset` of `frozenset({a, b})` — 상관 > 0.9 쌍(prepare 가 매일 새로 만든다) |
| `_bought_today` | `set[str]` |
| `_breakout_line[t]` · `_entry_atr[t]` · `_hsb_closed[t]` · `_channel_low[t]` · `_bars_since_buy[t]` | 멀티데이 보유 상태 dict |
| `_scanned_tickers` · `get_scanned_tickers()` | 후보, `tv20` 내림차순 |
| `check_buy_signal` · `calc_buy_quantity` · `check_exit_signal` · `get_effective_stop_price` · `check_force_clear` · `async recompute_held_atr` · `async prepare(*, as_of=None)` · `on_position_closed` · `_reset_daily_state` | 명세 §4~§8 |
| 일봉 seam | `src.db.stock_master_daily.get_recent_daily(ticker, days)` (DB 정규화 행, bas_dd DESC). 모듈 최상위에서 이름으로 가져오면 그 이름도 이 파일이 바꿔 끼운다 |
| 유니버스 seam | `src.db.stock_master.list_etf_trend_universe(min_market_cap_eok=500)` — 위와 같은 규칙 |
| 마커 | `[etf_trend_skip] … reason=<사유> …`(INFO) · `[etf_trend_exit] reason=… entry_n=… hold_bars=…`(INFO) · `[etf_trend_1520_check] held=… below=… missing_line=… stale=…`(INFO) · `[etf_trend_1520_stale]`(WARNING) · `[etf_trend_1520_error]`(WARNING) · `[etf_trend_close_print_exit]`(WARNING) · `[etf_trend_recover_skip]`(WARNING) · `[etf_trend_universe]`·`[etf_trend_signal]`(INFO) — 모든 마커 줄에 종목코드가 `ticker=` 또는 본문으로 들어간다 |

시계 = `_cycle369_support.frozen_datetime_class` 로 **전략 모듈 · `strategy_base` · `daily_emit_cap`** 의
`datetime` 이름을 같은 KST 시계로 바꾼다 — naive `datetime.now()`(진입창) 과 aware `datetime.now(KST)`(시장 유닛 ·
일일 cap · 15:20 나이 · 15:30 종가 틱 관측) 가 같은 KST 를 본다. freezegun `tz_offset=9` 는 naive 만 맞추고
aware `now(KST)` 를 9시간 더 민다(실측: naive 15:30:05 → aware 다음날 00:30:05) — 그래서 쓰지 않는다
(cycle384 `_cycle384_support` 와 같은 방식). **계약: `etf_trend.py` 는 `from datetime import datetime` 으로
`datetime` 클래스를 모듈 속성으로 둔다**(donchian 과 같은 모양).
"""
from __future__ import annotations

import importlib
import logging
from contextlib import ExitStack, contextmanager
from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest

from src.engine.strategy_base import Position, Signal, StrategyConfig

pytestmark = pytest.mark.unit

KST = timezone(timedelta(hours=9))
DAY = date(2026, 9, 28)             # 월
SID = "etf_trend"
T = "990403"                        # 합성 종목 — 실종목과 겹치지 않는다
U = "990404"
V = "990405"
SB_LOGGER = "src.engine.strategy_base"


# ===========================================================================
# 공용
# ===========================================================================
@contextmanager
def at(h: int, m: int = 0, s: int = 0, *, day: date = DAY, extra_modules=()):
    """KST 벽시계 고정 — naive now() 와 aware now(KST) 가 같은 시각(창 안·밖 두 시각 검증용)."""
    from src.engine import daily_emit_cap, strategy_base
    from tests.unit.engine._cycle369_support import Clock, frozen_datetime_class, kst

    cls()  # Red — 모듈 부재면 여기서 사유를 밝히고 실패
    mod = importlib.import_module("src.engine.strategies.etf_trend")
    assert isinstance(getattr(mod, "datetime", None), type), (
        "계약 — etf_trend.py 는 `from datetime import datetime`(클래스)을 모듈 속성으로 둔다"
    )
    clock = Clock(kst(h, m, s, day=day))
    frozen = frozen_datetime_class(clock)
    with ExitStack() as st:
        for m_ in (mod, strategy_base, daily_emit_cap, *extra_modules):
            st.enter_context(patch.object(m_, "datetime", frozen))
        yield clock


def cls():
    try:
        from src.engine.strategies.etf_trend import EtfTrendStrategy
    except ImportError as exc:  # pragma: no cover — Red 단계
        pytest.fail(f"[Red] src/engine/strategies/etf_trend.py 미존재 — {exc}")
    return EtfTrendStrategy


def snapshot(m: float, *, ok: bool = True):
    from tests.unit.engine._cycle382_support import snapshot as _snap

    return _snap(m, DAY, ok=ok)


def cand(prev_close=10_000, line=9_900, n=200.0, **kw) -> dict:
    d = {"prev_close": prev_close, "line": line, "n": n, "atr": n, "atr20": n * 1.05,
         "tv20": 3e9, "ema60": int(prev_close * 0.95), "cluster_key": None}
    d.update(kw)
    return d


def make(*, budget: int = 1_000_000, m: float | None = 1.0, shadow: bool = False, **params):
    """BUY 가 나는 기본 상태 — 섀도 끔 · 시장 유닛 m=1 스냅샷 · 후보 T."""
    s = cls()(StrategyConfig(strategy_id=SID, name="ETF 추세", params={"shadow_mode": shadow, **params}))
    s.state.total_investment = budget
    if m is not None:
        s._market_unit_snaps[DAY] = snapshot(m)
    s._candidates[T] = cand()
    return s


# 기본 입력 — 시가 10,050(갭 아님: < 10,300 · ≤ 9,900×1.04=10,296) · 현재가 10,100(≥ 시가)
OPEN = 10_050
PX = 10_100


@pytest.fixture(autouse=True)
def _isolate(monkeypatch, caplog):
    from src.engine import scanner

    monkeypatch.setattr(scanner, "ticker_prices", {}, raising=False)
    monkeypatch.setattr(scanner, "ticker_last_tick", {}, raising=False)
    monkeypatch.setattr(scanner, "ticker_prev_close", {}, raising=False)
    try:
        from src.engine import account_risk_watcher

        account_risk_watcher.reset_state_for_test()
    except Exception:
        pass
    caplog.set_level(logging.INFO)
    yield


def msgs(caplog, marker: str, *, min_level: int = logging.INFO) -> list[str]:
    return [
        r.getMessage() for r in caplog.records
        if r.levelno >= min_level and r.getMessage().startswith(marker + " ")
    ]


def field(line: str, key: str) -> str:
    tok = f"{key}="
    for part in line.split():
        if part.startswith(tok):
            return part[len(tok):]
    raise AssertionError(f"`{key}=` 없음: {line}")


def skips(caplog, reason: str | None = None) -> list[str]:
    out = msgs(caplog, "[etf_trend_skip]")
    return [ln for ln in out if reason is None or field(ln, "reason") == reason]


def pos(ticker=T, *, buy_price=10_000, qty=10, days_ago=3, high=None) -> Position:
    p = Position(ticker=ticker, buy_price=buy_price, quantity=qty, order_no="O-" + ticker,
                 strategy_id=SID, buy_date=DAY - timedelta(days=days_ago))
    if high is not None:
        p.high_since_buy = high
    return p


# ===========================================================================
# §5 check_buy_signal — 양성 대조 · 순서
# ===========================================================================
def test_positive_control_buys_and_stamps():
    s = make()
    with at(9, 10):
        assert s.check_buy_signal(T, PX, OPEN) == Signal.BUY
        assert T in s._bought_today
        assert s._breakout_line[T] == 9_900
        assert s.state.buy_signals and s.state.buy_signals[-1]["ticker"] == T
        assert s.check_buy_signal(T, PX, OPEN) == Signal.NONE, "종목당 하루 1회"
    row = s.state.buy_signals[-1]
    for key in ("name", "price", "line", "atr", "change_rate", "time"):
        assert key in row, f"buy_signals 항목에 화면이 읽는 키 {key} 없음(donchian 과 맞춘다)"


def test_buy_signals_capped_at_20():
    s = make(max_positions=100)
    with at(9, 10):
        for i in range(25):
            t = f"99{i:04d}"
            s._candidates[t] = cand()
            assert s.check_buy_signal(t, PX, OPEN) == Signal.BUY
    assert len(s.state.buy_signals) == 20


def test_account_soft_gate_is_first(monkeypatch, caplog):
    """게이트가 막으면 갭 래치도 skip 마커도 없다 — 첫 문장이다."""
    s = make()
    monkeypatch.setattr(s, "_account_soft_gate_blocked", lambda ticker=None: True)
    with at(9, 10):
        assert s.check_buy_signal(T, PX, 10_400) == Signal.NONE
    assert T not in s._bought_today
    assert skips(caplog) == []


@pytest.mark.parametrize("blocker", [
    "buy_disabled", "held", "pending", "sold_today", "bought_today", "max_positions", "daily_loss",
])
def test_basic_blockers_before_gap_latch(blocker, caplog):
    """보유·주문중·당일매도·래치·개수·일일손실 → NONE, 갭 판정보다 앞(래치·skip 마커 없음)."""
    s = make(max_positions=4)
    if blocker == "buy_disabled":
        s.state.buy_disabled = True
    elif blocker == "held":
        s.state.positions[T] = pos()
    elif blocker == "pending":
        s.state.pending_buys.add(T)
    elif blocker == "sold_today":
        s.state.sold_today.add(T)
    elif blocker == "bought_today":
        s._bought_today.add(T)
    elif blocker == "max_positions":
        for i in range(4):
            s.state.positions[f"98{i:04d}"] = pos(f"98{i:04d}")
    elif blocker == "daily_loss":
        s.state.daily_realized_pnl = -1_000_000
    before = set(s._bought_today)
    with at(9, 10):
        assert s.check_buy_signal(T, PX, 10_400) == Signal.NONE
    assert s._bought_today == before
    assert skips(caplog) == []


def test_no_candidate_none():
    s = make()
    s._candidates.clear()
    with at(9, 10):
        assert s.check_buy_signal(T, PX, OPEN) == Signal.NONE


@pytest.mark.parametrize("hms,want", [
    pytest.param((9, 4, 59), Signal.NONE, id="before_0905"),
    pytest.param((9, 5, 0), Signal.BUY, id="at_0905"),
    pytest.param((9, 30, 0), Signal.BUY, id="at_0930"),
    pytest.param((9, 31, 0), Signal.NONE, id="after_0930"),
    pytest.param((13, 0, 0), Signal.NONE, id="afternoon"),
])
def test_entry_window(hms, want):
    s = make()
    with at(*hms):
        assert s.check_buy_signal(T, PX, OPEN) == want


def test_window_precedes_gap_latch(caplog):
    s = make()
    with at(9, 40):
        assert s.check_buy_signal(T, PX, 10_400) == Signal.NONE
    assert T not in s._bought_today and skips(caplog) == []


@pytest.mark.parametrize("open_price,line,reason", [
    pytest.param(10_300, 9_900, "gap_up", id="gap_up"),
    pytest.param(10_000, 9_600, "gap_over_line", id="gap_over_line"),
])
def test_gap_skip_latches_for_the_day(open_price, line, reason, caplog):
    s = make()
    s._candidates[T] = cand(line=line)
    with at(9, 10):
        assert s.check_buy_signal(T, open_price + 50, open_price) == Signal.NONE
        assert T in s._bought_today, "갭 스킵은 그날 래치"
        assert s.check_buy_signal(T, PX, OPEN) == Signal.NONE, "래치 뒤 정상 시가여도 그날은 안 산다"
    got = skips(caplog, reason)
    assert len(got) == 1 and T in got[0]


def test_collapse_skip_does_not_latch(caplog):
    s = make()
    with at(9, 10):
        for _ in range(3):
            assert s.check_buy_signal(T, OPEN - 1, OPEN) == Signal.NONE
        assert T not in s._bought_today, "붕괴는 래치 없음 — 다음 폴에서 다시 본다"
    with at(9, 11):
        assert s.check_buy_signal(T, PX, OPEN) == Signal.BUY
    assert len(skips(caplog, "collapse")) == 1, "skip 마커는 (종목, 사유)당 하루 1회"


@pytest.mark.parametrize("where", ["positions", "pending_buys"])
def test_cluster_held_blocks_without_latch(where, caplog):
    s = make()
    s._cluster_pairs = {frozenset({T, U})}
    if where == "positions":
        s.state.positions[U] = pos(U)
    else:
        s.state.pending_buys.add(U)
    with at(9, 10):
        assert s.check_buy_signal(T, PX, OPEN) == Signal.NONE
        assert T not in s._bought_today
        assert len(skips(caplog, "cluster_held")) == 1
        if where == "positions":
            del s.state.positions[U]
        else:
            s.state.pending_buys.discard(U)
        assert s.check_buy_signal(T, PX, OPEN) == Signal.BUY, "같은 묶음이 비면 산다(래치 없음)"


def test_cluster_other_pair_does_not_block():
    s = make()
    s._cluster_pairs = {frozenset({U, V})}
    s.state.positions[U] = pos(U)
    with at(9, 10):
        assert s.check_buy_signal(T, PX, OPEN) == Signal.BUY


@pytest.mark.parametrize("mode,snap,want,reason", [
    pytest.param("shadow", None, Signal.NONE, "market_unit_unavailable", id="shadow_not_computed"),
    pytest.param("shadow", "fail", Signal.NONE, "market_unit_unavailable", id="shadow_snapshot_failed"),
    pytest.param("enforce", None, Signal.NONE, "market_unit_unavailable", id="enforce_not_computed"),
    pytest.param("shadow", 0.0, Signal.NONE, "zero_state", id="shadow_zero"),
    pytest.param("enforce", 0.0, Signal.NONE, "zero_state", id="enforce_zero"),
    pytest.param("off", None, Signal.BUY, None, id="off_ignores_unavailable"),
    pytest.param("off", 0.0, Signal.BUY, None, id="off_ignores_zero"),
    pytest.param("shadow", 0.5, Signal.BUY, None, id="shadow_half_no_lot_cut"),
    pytest.param("shadow", 1.0, Signal.BUY, None, id="shadow_full"),
])
def test_market_unit_filter_is_signal_definition(mode, snap, want, reason, caplog):
    """L4 — shadow·enforce 모두 결손·m=0 은 신호 단계에서 거른다(터틀 4전략의 fail-open 과 다르다)."""
    s = make(m=None, market_unit_mode=mode)
    if snap == "fail":
        s._market_unit_snaps[DAY] = snapshot(1.0, ok=False)
    elif snap is not None:
        s._market_unit_snaps[DAY] = snapshot(snap)
    with at(9, 10):
        assert s.check_buy_signal(T, PX, OPEN) == want
    if reason:
        assert len(skips(caplog, reason)) == 1
        assert T not in s._bought_today


def test_market_unit_enforce_reduced_lot_rounds_to_zero_blocks():
    """enforce ∧ m<1 의 랏 축소는 터틀 4전략과 같은 `_market_unit_blocks_entry` 경로."""
    s = make(budget=500_000, m=0.5, market_unit_mode="enforce")
    s._candidates[T] = cand(prev_close=100_000, line=99_000, n=2_000.0)
    with at(9, 10):
        # m=1 이면 pr 상한 125,000//101,000 = 1주 → m=0.5 면 62,500//101,000 = 0주
        assert s.check_buy_signal(T, 101_000, 100_500) == Signal.NONE


def test_rounds_to_zero_is_filtered_at_signal(caplog):
    """L5 — 정상 랏 0주면 신호 단계 NONE(수량 0 을 흘리지 않는다)."""
    s = make(budget=250_000)
    s._candidates[T] = cand(prev_close=120_000, line=118_000, n=2_400.0)
    with at(9, 10):
        assert s.check_buy_signal(T, 120_500, 120_000) == Signal.NONE
    assert len(skips(caplog, "rounds_to_zero")) == 1


def test_no_budget_shadow_off_is_no_budget(caplog):
    s = make(budget=0)
    with at(9, 10):
        assert s.check_buy_signal(T, PX, OPEN) == Signal.NONE
    assert len(skips(caplog, "no_budget")) == 1
    assert msgs(caplog, "[shadow_buy]") == []


def test_no_budget_shadow_on_records_shadow_buy(caplog):
    """S1 은 비중 0 → 예산 0. 섀도면 랏 판정을 건너뛰어 [shadow_buy] 가 기록의 유일한 길이다."""
    s = make(budget=0, shadow=True)
    with at(9, 10):
        assert s.check_buy_signal(T, PX, OPEN) == Signal.NONE
    got = msgs(caplog, "[shadow_buy]")
    assert len(got) == 1, got
    assert field(got[0], "strategy") == SID and field(got[0], "ticker") == T
    assert field(got[0], "level") == "9900", "돌파선이 오프라인 재현용으로 남아야 한다"
    assert skips(caplog, "no_budget") == [] and skips(caplog, "rounds_to_zero") == []


def test_no_budget_shadow_on_also_emits_buy_eval(caplog):
    """팀장 검토 B — 예산 0 경로(S1 의 유일한 경로)에서도 [etf_trend_buy_eval] 이 찍힌다."""
    s = make(budget=0, shadow=True)
    with at(9, 10):
        assert s.check_buy_signal(T, PX, OPEN) == Signal.NONE
    got = msgs(caplog, "[etf_trend_buy_eval]")
    assert len(got) == 1, got
    assert field(got[0], "ticker") == T


def test_check_buy_signal_never_stamps_entry_atr_or_calls_gate(monkeypatch):
    """팀장 검토 A — 신호 단계 랏 판정은 순수 계산이다: `_entry_atr` 미스탬프·`_apply_budget_limit` 미호출."""
    s = make()
    monkeypatch.setattr(s, "_apply_budget_limit",
                        lambda *a, **k: pytest.fail("관문 호출 — 신호 단계는 관문을 거치지 않는다"))
    with at(9, 10):
        assert s.check_buy_signal(T, PX, OPEN) == Signal.BUY
    assert T not in s._entry_atr, "신호 단계에서 _entry_atr 가 스탬프됐다 — 상태 변경은 calc_buy_quantity 에서만"


def test_shadow_with_budget_leaves_no_state(caplog):
    s = make(shadow=True)
    sigs = list(s.state.buy_signals)
    with at(9, 10):
        assert s.check_buy_signal(T, PX, OPEN) == Signal.NONE
    assert len(msgs(caplog, "[shadow_buy]")) == 1
    assert T not in s._bought_today
    assert T not in getattr(s, "_breakout_line", {})
    assert s.state.buy_signals == sigs


def test_shadow_after_earlier_filters(caplog):
    """섀도는 마지막 거름 — 갭·묶음·시장 유닛이 이기면 [shadow_buy] 가 없다."""
    s = make(shadow=True, market_unit_mode="shadow", m=0.0)
    with at(9, 10):
        assert s.check_buy_signal(T, PX, OPEN) == Signal.NONE
    assert msgs(caplog, "[shadow_buy]") == []


def test_default_params_strategy_is_shadow():
    """기본값 그대로(섀도 켜짐)면 BUY 가 나지 않는다 — S1 은 주문 0."""
    s = cls()(StrategyConfig(strategy_id=SID, name="ETF 추세", params={}))
    s.state.total_investment = 1_000_000
    s._market_unit_snaps[DAY] = snapshot(1.0)
    s._candidates[T] = cand()
    with at(9, 10):
        assert s.check_buy_signal(T, PX, OPEN) == Signal.NONE


# ===========================================================================
# §6 calc_buy_quantity
# ===========================================================================
def test_calc_zero_price_or_no_ticker_or_no_candidate():
    s = make()
    assert s.calc_buy_quantity(0, T) == 0
    assert s.calc_buy_quantity(PX, None) == 0
    assert s.calc_buy_quantity(PX, U) == 0


def test_calc_unit_zero_returns_zero_without_fallback(monkeypatch):
    s = make(budget=250_000)
    s._candidates[T] = cand(prev_close=120_000, line=118_000, n=2_400.0)
    monkeypatch.setattr(s, "_fallback_one_share",
                        lambda *a, **k: pytest.fail("1주 폴백 호출 — 이 전략은 폴백 금지(L5)"))
    with at(9, 10):
        assert s.calc_buy_quantity(120_500, T) == 0
    assert T not in s._entry_atr, "0주인데 진입 N 이 찍혔다"


def test_calc_unit_goes_through_gate_and_stamps_n(monkeypatch):
    from src.engine.turtle_sizing import compute_unit_qty_guarded

    s = make()
    seen: list[int] = []
    real = s._apply_budget_limit

    def spy(qty, price, ticker=None):
        seen.append(qty)
        return real(qty, price, ticker)

    monkeypatch.setattr(s, "_apply_budget_limit", spy)
    want = compute_unit_qty_guarded(1_000_000, 200.0, PX, 0.01, remaining_budget=1_000_000,
                                    min_vol_pct=0.0, position_ratio=0.25)
    with at(9, 10):
        got = s.calc_buy_quantity(PX, T)
    assert want > 0 and seen == [want], f"관문에 넘긴 수량 {seen} != 유닛 {want}"
    assert got == want
    assert s._entry_atr[T] == 200.0, "사이징 N 과 손절 N 이 같은 값(커플링 불변식)"


def test_calc_min_vol_floor_is_zero():
    """L6 — N/가격 0.5% 도 산다(donchian floor 1.0 이면 0주)."""
    s = make()
    s._candidates[T] = cand(n=50.0)
    with at(9, 10):
        assert s.calc_buy_quantity(10_000, T) == 25           # min(유닛 200, 비중 상한 25)


def test_calc_enforce_half_uses_market_unit_lots():
    s = make(m=0.5, market_unit_mode="enforce")
    with at(9, 10):
        assert s.calc_buy_quantity(10_000, T) == 12            # 예산×0.5 → 비중 상한 125,000//10,000
    assert s._entry_atr[T] == 200.0


def test_calc_shadow_half_does_not_cut():
    s = make(m=0.5, market_unit_mode="shadow")
    with at(9, 10):
        assert s.calc_buy_quantity(10_000, T) == 25


# ===========================================================================
# §7.1 check_exit_signal — 선 1~4 경계
# ===========================================================================
def held(*, n=200.0, hsb=None, bars=0, chan=None, high=None, **kw):
    s = make()
    s.state.positions[T] = pos(high=high, **kw)
    if n is not None:
        s._entry_atr[T] = n
    if hsb is not None:
        s._hsb_closed[T] = hsb
    s._bars_since_buy[T] = bars
    if chan is not None:
        s._channel_low[T] = chan
    s._breakout_line[T] = 9_900
    return s


@pytest.mark.parametrize("kw,price,want,reason", [
    pytest.param({}, 9_600, Signal.STOP_LOSS, "hard", id="hard_at_line"),
    pytest.param({}, 9_601, Signal.NONE, None, id="hard_above"),
    pytest.param({"n": 600.0}, 9_100, Signal.STOP_LOSS, "hard", id="backstop_governs"),
    pytest.param({"n": None}, 9_100, Signal.STOP_LOSS, "hard", id="no_n_backstop_only"),
    pytest.param({"n": None}, 9_101, Signal.NONE, None, id="no_n_above_backstop"),
    pytest.param({"hsb": 10_300, "bars": 1}, 10_000, Signal.STOP_LOSS, "breakeven", id="breakeven_at_trigger"),
    pytest.param({"hsb": 10_300, "bars": 1}, 10_001, Signal.NONE, None, id="breakeven_above"),
    pytest.param({"hsb": 10_299, "bars": 1}, 9_939, Signal.TRAILING_STOP, "trail", id="trail_below_be_trigger"),
    pytest.param({"hsb": 11_000, "bars": 2}, 10_640, Signal.TRAILING_STOP, "trail", id="trail_at_line"),
    pytest.param({"hsb": 11_000, "bars": 2}, 10_641, Signal.NONE, None, id="trail_above"),
    pytest.param({"bars": 1, "chan": 9_800}, 9_799, Signal.TRAILING_STOP, "channel", id="channel_below"),
    pytest.param({"bars": 1, "chan": 9_800}, 9_800, Signal.NONE, None, id="channel_equal_not_exit"),
    pytest.param({"bars": 0, "chan": 9_800}, 9_799, Signal.NONE, None, id="channel_not_on_buy_day"),
])
def test_exit_lines(kw, price, want, reason, caplog):
    s = held(**kw)
    with at(10, 0):
        assert s.check_exit_signal(T, price, 10_000) == want
    got = msgs(caplog, "[etf_trend_exit]")
    if reason:
        assert len(got) == 1 and field(got[0], "reason") == reason, got
        field(got[0], "entry_n")
        field(got[0], "hold_bars")
    else:
        assert got == []


def test_intraday_high_does_not_raise_line():
    """선은 완성봉 고가로만 — 장중 high_since_buy 가 높아도 매수일엔 하드만."""
    s = held(high=20_000)
    with at(10, 0):
        assert s.check_exit_signal(T, 9_700, 10_000) == Signal.NONE


def test_exit_signal_repeats_but_marker_once(caplog):
    s = held()
    with at(10, 0):
        for _ in range(3):
            assert s.check_exit_signal(T, 9_500, 10_000) == Signal.STOP_LOSS
    assert len(msgs(caplog, "[etf_trend_exit]")) == 1, "마커는 1회/종목/일, 신호는 cap 밖"


def test_no_position_none():
    s = make()
    with at(10, 0):
        assert s.check_exit_signal(T, 1, 10_000) == Signal.NONE


def test_close_print_exit_signals_and_warns(caplog):
    """15:30 종가 틱 — 시각 게이트 없이 신호, 관측만 WARNING."""
    s = held()
    with at(15, 30, 5):
        assert s.check_exit_signal(T, 9_500, 10_000) == Signal.STOP_LOSS
    assert len(msgs(caplog, "[etf_trend_close_print_exit]", min_level=logging.WARNING)) == 1


def test_no_close_print_warning_intraday(caplog):
    s = held()
    with at(14, 0):
        assert s.check_exit_signal(T, 9_500, 10_000) == Signal.STOP_LOSS
    assert msgs(caplog, "[etf_trend_close_print_exit]", min_level=logging.WARNING) == []


# ===========================================================================
# §7.3 get_effective_stop_price — read-only 미러
# ===========================================================================
@pytest.mark.parametrize("kw,want", [
    pytest.param({}, 9_600, id="hard"),
    pytest.param({"hsb": 10_300, "bars": 1}, 10_000, id="breakeven"),
    pytest.param({"hsb": 11_000, "bars": 2}, 10_640, id="trail"),
    pytest.param({"hsb": 11_000, "bars": 2, "chan": 10_700}, 10_700, id="channel_highest"),
    pytest.param({"n": None}, 9_100, id="backstop"),
])
def test_effective_stop_mirror(kw, want, caplog):
    s = held(**kw)
    before = (dict(s._entry_atr), dict(s._hsb_closed), dict(s._channel_low), dict(s._bars_since_buy))
    with at(10, 0):
        assert s.get_effective_stop_price(T) == want
    assert (dict(s._entry_atr), dict(s._hsb_closed), dict(s._channel_low), dict(s._bars_since_buy)) == before
    assert msgs(caplog, "[etf_trend_exit]") == []


def test_effective_stop_none_without_position():
    s = make()
    assert s.get_effective_stop_price(T) is None


# ===========================================================================
# §7.2 check_force_clear — 15:20 돌파 실패, never-raise
# ===========================================================================
def _tick(monkeypatch, ticker: str, price: int | None, age_s: float | None):
    from src.engine import scanner

    if price is not None:
        scanner.ticker_prices[ticker] = {"current_price": price}
    if age_s is not None:
        scanner.ticker_last_tick[ticker] = datetime(2026, 9, 28, 15, 20, 30, tzinfo=KST) - timedelta(seconds=age_s)


def three_held(monkeypatch):
    s = make()
    for t, bars in ((T, 2), (U, 2), (V, 1)):
        s.state.positions[t] = pos(t)
        s._breakout_line[t] = 10_000
        s._bars_since_buy[t] = bars
        s._entry_atr[t] = 200.0
    _tick(monkeypatch, T, 9_900, 10)      # 돌파선 아래 · D+2 → 판다
    _tick(monkeypatch, U, 10_100, 10)     # 돌파선 위 → 안 판다
    _tick(monkeypatch, V, 9_000, 10)      # 아래지만 D+1 → 안 판다
    return s


def test_force_clear_returns_only_below_line(monkeypatch, caplog):
    s = three_held(monkeypatch)
    with at(15, 20, 30):
        assert s.check_force_clear() == [T]
    exits = [ln for ln in msgs(caplog, "[etf_trend_exit]") if field(ln, "reason") == "breakout_fail_1520"]
    assert len(exits) == 1 and T in exits[0]
    for k in ("price", "line", "age_s"):
        field(exits[0], k)
    summ = msgs(caplog, "[etf_trend_1520_check]")
    assert len(summ) == 1
    assert field(summ[0], "held") == "3" and field(summ[0], "below") == "1"
    field(summ[0], "missing_line")
    field(summ[0], "stale")


def test_force_clear_never_returns_all_holdings(monkeypatch):
    s = three_held(monkeypatch)
    _tick(monkeypatch, T, 10_000, 10)     # 같으면 실패 아님(<)
    with at(15, 20, 30):
        assert s.check_force_clear() == []


@pytest.mark.parametrize("price,age", [
    pytest.param(9_900, 181, id="stale_tick"),
    pytest.param(None, None, id="no_price"),
    pytest.param(0, 10, id="zero_price"),
    pytest.param(9_900, None, id="no_tick_time"),
])
def test_force_clear_stale_or_missing_price_does_not_sell(price, age, monkeypatch, caplog):
    from src.engine import scanner

    s = make()
    s.state.positions[T] = pos()
    s._breakout_line[T] = 10_000
    s._bars_since_buy[T] = 3
    scanner.ticker_prices.pop(T, None)
    scanner.ticker_last_tick.pop(T, None)
    _tick(monkeypatch, T, price, age)
    with at(15, 20, 30):
        assert s.check_force_clear() == []
        assert s.check_force_clear() == []
    warns = msgs(caplog, "[etf_trend_1520_stale]", min_level=logging.WARNING)
    assert len(warns) == 1 and T in warns[0], "낡음·결측 WARNING 1회/종목/일"


def test_force_clear_fresh_at_180s_still_judges(monkeypatch):
    s = make()
    s.state.positions[T] = pos()
    s._breakout_line[T] = 10_000
    s._bars_since_buy[T] = 3
    _tick(monkeypatch, T, 9_900, 180)
    with at(15, 20, 30):
        assert s.check_force_clear() == [T]


def test_force_clear_missing_line_skips_with_warning(monkeypatch, caplog):
    s = make()
    s.state.positions[T] = pos()
    s._bars_since_buy[T] = 3
    s._breakout_line.pop(T, None)
    _tick(monkeypatch, T, 1, 10)
    with at(15, 20, 30):
        assert s.check_force_clear() == []
    warns = [r.getMessage() for r in caplog.records
             if r.levelno >= logging.WARNING and r.getMessage().startswith("[etf_trend") and T in r.getMessage()]
    assert warns, "돌파선 결측은 팔지 않고 WARNING"


def test_force_clear_never_raises(caplog):
    class Exploding(dict):
        def _boom(self, *a, **k):
            raise RuntimeError("boom")

        items = keys = values = __iter__ = __len__ = get = __contains__ = __getitem__ = _boom

    s = make()
    s.state.positions = Exploding()
    with at(15, 20, 30):
        assert s.check_force_clear() == []
    assert len(msgs(caplog, "[etf_trend_1520_error]", min_level=logging.WARNING)) == 1


def test_force_clear_one_ticker_error_does_not_blank_the_rest(monkeypatch, caplog):
    """팀장 검토 C — 종목 단위 예외(예: naive tick_time 뺄셈)가 다른 종목 판정까지 비우지 않는다."""
    from src.engine import scanner

    s = make()
    for t in (T, U):
        s.state.positions[t] = pos(t)
        s._breakout_line[t] = 10_000
        s._bars_since_buy[t] = 3
    scanner.ticker_prices[T] = {"current_price": 9_900}
    scanner.ticker_last_tick[T] = datetime(2026, 9, 28, 15, 20, 20)  # naive — now(KST) 와 뺄셈 TypeError
    scanner.ticker_prices[U] = {"current_price": 9_900}
    scanner.ticker_last_tick[U] = datetime(2026, 9, 28, 15, 20, 20, tzinfo=KST)
    with at(15, 20, 30):
        assert s.check_force_clear() == [U], "T 하나가 예외여도 U 는 정상 판정돼야 한다"
    warns = msgs(caplog, "[etf_trend_1520_stale]", min_level=logging.WARNING)
    assert any(T in w for w in warns), warns


# ===========================================================================
# §7.5 · §8 — 상태 수명
# ===========================================================================
def test_on_position_closed_pops_multiday_state():
    s = held(hsb=11_000, bars=2, chan=9_800)
    s.on_position_closed(T)
    for name in ("_entry_atr", "_breakout_line", "_hsb_closed", "_channel_low", "_bars_since_buy"):
        assert T not in getattr(s, name), f"{name} 가 청산 뒤 남았다"


def test_reset_daily_state_keeps_multiday_state():
    s = held(hsb=11_000, bars=2, chan=9_800)
    s._bought_today.add(U)
    s._reset_daily_state()
    assert U not in s._bought_today
    for name in ("_entry_atr", "_breakout_line", "_hsb_closed", "_channel_low", "_bars_since_buy"):
        assert T in getattr(s, name), f"{name} 가 일일 리셋에 지워졌다(멀티데이 상태)"


# ===========================================================================
# 일봉 합성 — DB 정규화 행(bas_dd DESC)
# ===========================================================================
def weekdays_asc(last: date, n: int) -> list[date]:
    out: list[date] = []
    d = last
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d -= timedelta(days=1)
    return list(reversed(out))


def bars(n: int, last: date, *, base=10_000.0, step=0.002, breakout=True, tv=3e9, scale=1.0):
    """오름차순 (date, o, h, l, c, tv) — 완만한 상승 + ±0.3% 톱니, 마지막 봉 돌파 + 거래대금 2배."""
    dates = weekdays_asc(last, n)
    out = []
    prev = base
    for i, d in enumerate(dates):
        c = base * (1 + step * i) * (1.003 if i % 2 else 0.997)
        o = prev
        h, lo = max(o, c) * 1.01, min(o, c) * 0.99
        v = tv
        out.append([d, o, h, lo, c, v])
        prev = c
    if breakout:
        prior_hi = max(r[2] for r in out[-21:-1])
        c = prior_hi * 1.01
        out[-1][4] = c
        out[-1][2] = c * 1.005
        out[-1][5] = tv * 2
    return [(d, o * scale, h * scale, lo * scale, c * scale, v) for d, o, h, lo, c, v in out]


def to_rows(ticker: str, asc) -> list[dict]:
    return [
        {"ticker": ticker, "bas_dd": d, "open_price": int(o), "high_price": int(h), "low_price": int(lo),
         "close_price": int(c), "volume": 1000, "trade_value": int(v), "change_rate": 0.0, "raw": {}}
        for d, o, h, lo, c, v in reversed(asc)
    ]


class Daily:
    def __init__(self, table: dict[str, list[dict]]):
        self.table = table
        self.calls: list[tuple] = []

    async def __call__(self, ticker, days=20, *a, **k):
        self.calls.append((ticker, days))
        return [dict(r) for r in self.table.get(ticker, [])][: max(1, days)]


def install_daily(monkeypatch, daily: Daily):
    import importlib

    monkeypatch.setattr("src.db.stock_master_daily.get_recent_daily", daily)
    mod = importlib.import_module("src.engine.strategies.etf_trend")
    if hasattr(mod, "get_recent_daily"):
        monkeypatch.setattr(mod, "get_recent_daily", daily)
    kis = AsyncMock(side_effect=AssertionError("KIS 일봉 폴백 호출 — 이 전략은 DB 만 읽는다"))
    monkeypatch.setattr("src.api.condition.fetch_daily_candles", kis)
    return kis


# ===========================================================================
# §7.4 recompute_held_atr — 부팅 복구 한 곳
# ===========================================================================
LAST = date(2026, 9, 25)          # DAY(월) 직전 금요일 = 최신 완성봉


def _expected(asc, buy_date):
    idx_sig = max(i for i, r in enumerate(asc) if r[0] < buy_date)
    highs = [r[2] for r in asc]
    lows = [r[3] for r in asc]
    closes = [r[4] for r in asc]
    line = max(highs[idx_sig - 20:idx_sig])
    trs = [max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1]))
           for i in range(idx_sig - 13, idx_sig + 1)]
    n = sum(trs) / 14
    after = [r for r in asc if r[0] >= buy_date]
    return {
        "line": line, "n": n, "hsb": max(r[2] for r in after), "bars": len(after),
        "chan": min(r[3] for r in asc[-10:]),
    }


def k200_rows(asc) -> list[dict]:
    """069500 달력 — 종목과 같은 날짜(§11 `_bars_since_buy` 는 이 달력으로 센다)."""
    return to_rows("069500", [(r[0], 10_000, 10_100, 9_900, 10_000, 1e10) for r in asc])


async def _recompute(s, monkeypatch, table):
    table = dict(table)
    if "069500" not in table:
        tk = next(iter(table))
        table["069500"] = k200_rows([(r["bas_dd"],) for r in reversed(table[tk])])
    daily = Daily(table)
    kis = install_daily(monkeypatch, daily)
    monkeypatch.setattr("src.db.positions.update_high", AsyncMock())
    monkeypatch.setattr("src.db.system_logs.write_log", AsyncMock())
    await s.recompute_held_atr()
    kis.assert_not_awaited()
    return daily


def int_bars(*a, **k):
    """DB 에 들어가는 값과 같은 정수 봉 — 기대값을 DB 행과 같은 입력으로 계산한다."""
    return [(d, int(o), int(h), int(lo), int(c), int(v)) for d, o, h, lo, c, v in bars(*a, **k)]


@pytest.mark.asyncio
async def test_recompute_restores_line_n_hsb_bars_channel(monkeypatch):
    asc = int_bars(60, LAST, breakout=False)
    buy_date = asc[-4][0]                                    # 매수일 포함 완성봉 4개
    want = _expected(asc, buy_date)
    s = make(sizing_mode="turtle")
    s.state.positions[T] = pos(days_ago=(DAY - buy_date).days, buy_price=asc[-4][1])
    with at(7, 50):
        await _recompute(s, monkeypatch, {T: to_rows(T, asc)})
    assert s._breakout_line[T] == want["line"]
    assert s._entry_atr[T] == pytest.approx(want["n"], rel=1e-9), (
        "§11 — 복구 N 은 leaf n14(매수일 이전 봉) float, 정수 절삭 아님", s._entry_atr[T], want["n"])
    assert s._hsb_closed[T] == want["hsb"]
    assert s._bars_since_buy[T] == want["bars"] == 4
    assert s._channel_low[T] == want["chan"]
    hs_after = [r[2] for r in asc if buy_date < r[0] < DAY]
    assert s.state.positions[T].high_since_buy == max(hs_after), "high_since_buy 위임 복구(매수일 다음 봉부터)"


@pytest.mark.asyncio
async def test_recompute_does_not_overwrite_buy_time_values(monkeypatch):
    asc = int_bars(60, LAST, breakout=False)
    buy_date = asc[-3][0]
    s = make(sizing_mode="turtle")
    s.state.positions[T] = pos(days_ago=(DAY - buy_date).days)
    s._breakout_line[T] = 12_345
    s._entry_atr[T] = 111.0
    with at(7, 50):
        await _recompute(s, monkeypatch, {T: to_rows(T, asc)})
    assert s._breakout_line[T] == 12_345 and s._entry_atr[T] == 111.0
    assert s._bars_since_buy[T] == 3


@pytest.mark.asyncio
async def test_recompute_n_only_when_turtle(monkeypatch):
    asc = int_bars(60, LAST, breakout=False)
    s = make(sizing_mode="position_ratio")
    s.state.positions[T] = pos(days_ago=(DAY - asc[-3][0]).days)
    with at(7, 50):
        await _recompute(s, monkeypatch, {T: to_rows(T, asc)})
    assert T not in s._entry_atr, "cycle355 게이트 — turtle 이 아니면 N 을 되살리지 않는다"
    assert T in s._breakout_line


@pytest.mark.asyncio
async def test_recompute_short_history_warns_and_leaves_blank(monkeypatch, caplog):
    asc = int_bars(12, LAST, breakout=False)
    s = make(sizing_mode="turtle")
    s.state.positions[T] = pos(days_ago=(DAY - asc[-2][0]).days)
    with at(7, 50):
        await _recompute(s, monkeypatch, {T: to_rows(T, asc)})
    assert T not in s._breakout_line and T not in s._entry_atr
    warns = msgs(caplog, "[etf_trend_recover_skip]", min_level=logging.WARNING)
    assert warns and T in warns[0]


@pytest.mark.asyncio
async def test_recompute_reads_daily_fetch_rows(monkeypatch):
    asc = int_bars(60, LAST, breakout=False)
    s = make(sizing_mode="turtle")
    s.state.positions[T] = pos(days_ago=(DAY - asc[-3][0]).days)
    with at(7, 50):
        daily = await _recompute(s, monkeypatch, {T: to_rows(T, asc)})
    assert (T, 225) in daily.calls, f"일봉은 daily_fetch_rows(225) 만큼 DB 에서 읽는다: {daily.calls}"


# ===========================================================================
# §4 prepare — 유니버스 → 일봉 품질 → 신호 → 묶음 → 순서
# ===========================================================================
A, A2, B, C, D = "990411", "990412", "990413", "990414", "990415"


@pytest.mark.asyncio
async def test_prepare_builds_candidates_clusters_and_order(monkeypatch, caplog):
    import importlib

    import numpy as np
    import pandas as pd

    asc_a = bars(150, LAST)
    asc_a2 = bars(150, LAST, scale=2.0, tv=4e9)              # 같은 모양 → 상관 1.0, 거래대금 더 큼
    asc_b = bars(150, LAST, breakout=False)                  # 돌파 없음
    asc_d = bars(150, LAST - timedelta(days=1))              # 최신 봉이 069500 보다 하루 늦다
    asc_k = bars(150, LAST, breakout=False)
    table = {A: to_rows(A, asc_a), A2: to_rows(A2, asc_a2), B: to_rows(B, asc_b), C: [],
             D: to_rows(D, asc_d), "069500": to_rows("069500", asc_k)}
    universe = [{"ticker": t, "name": f"합성{t}", "hts_avls_eok": 1_000} for t in (A, A2, B, C, D)]

    async def fake_universe(min_market_cap_eok: int = 500):
        return [dict(u) for u in universe]

    monkeypatch.setattr("src.db.stock_master.list_etf_trend_universe", fake_universe, raising=False)
    mod = importlib.import_module("src.engine.strategies.etf_trend")
    if hasattr(mod, "list_etf_trend_universe"):
        monkeypatch.setattr(mod, "list_etf_trend_universe", fake_universe)
    install_daily(monkeypatch, Daily(table))

    s = make()
    refresh = AsyncMock()
    monkeypatch.setattr(s, "_refresh_market_unit", refresh)
    with at(7, 45):
        await s.prepare()

    refresh.assert_awaited()
    assert set(s._candidates) == {A, A2}, f"후보 {sorted(s._candidates)}"
    assert s.get_scanned_tickers() == [A2, A], "20일 거래대금 내림차순"

    # 기대값 — 재현 지표(pandas) 로 독립 계산
    def rep_vals(asc):
        df = pd.DataFrame({"h": [r[2] for r in asc], "l": [r[3] for r in asc], "c": [r[4] for r in asc]})
        hi_prev20 = df["h"].shift(1).rolling(20, min_periods=20).max().iloc[-1]
        prev_c = df["c"].shift(1)
        tr = np.nanmax(np.vstack([df["h"] - df["l"], (df["h"] - prev_c).abs(), (df["l"] - prev_c).abs()]), axis=0)
        tr[0] = np.nan
        n14 = pd.Series(tr).rolling(14, min_periods=14).mean().iloc[-1]
        return hi_prev20, n14, df["c"].iloc[-1]

    rows_a = list(reversed(table[A]))
    ia = [(r["bas_dd"], r["open_price"], r["high_price"], r["low_price"], r["close_price"], r["trade_value"])
          for r in rows_a]
    line, n14, close = rep_vals(ia)
    info = s._candidates[A]
    assert info["line"] == pytest.approx(line, rel=1e-9)
    assert info["n"] == pytest.approx(n14, rel=1e-9)
    assert info["atr"] == info["n"], "사이징 ATR 키 = N"
    assert info["prev_close"] == pytest.approx(close)
    assert frozenset({A, A2}) in s._cluster_pairs

    assert len(msgs(caplog, "[etf_trend_universe]")) == 1
    assert len(msgs(caplog, "[etf_trend_signal]")) == 1

    # 팀장 검토 D — 깔때기 단계 기록(FUNNEL_STAGES 7단계, C 의 돌파 미달 B 는 4단계에서 탈락).
    steps = {st["step_no"]: st for st in s._funnel_steps}
    assert set(steps) == {1, 2, 3, 4, 5, 6, 99}
    assert {row["ticker"] for row in steps[1]["survived"]} == {A, A2, B, C, D}
    assert {row["ticker"] for row in steps[2]["survived"]} == {A, A2, B}, "C(빈 일봉)·D(최신봉 불일치) 는 일봉 품질에서 탈락"
    assert {row["ticker"] for row in steps[4]["survived"]} == {A, A2}, "B 는 돌파 미달로 4단계에서 탈락"
    assert steps[99]["survived_count"] == 2


@pytest.mark.asyncio
async def test_prepare_rebuilds_state_daily(monkeypatch):
    """묶음·후보는 매일 새로 — 어제 상태가 남지 않는다."""
    import importlib

    async def empty_universe(min_market_cap_eok: int = 500):
        return []

    monkeypatch.setattr("src.db.stock_master.list_etf_trend_universe", empty_universe, raising=False)
    mod = importlib.import_module("src.engine.strategies.etf_trend")
    if hasattr(mod, "list_etf_trend_universe"):
        monkeypatch.setattr(mod, "list_etf_trend_universe", empty_universe)
    install_daily(monkeypatch, Daily({"069500": to_rows("069500", bars(150, LAST, breakout=False))}))
    s = make()
    s._cluster_pairs = {frozenset({U, V})}
    monkeypatch.setattr(s, "_refresh_market_unit", AsyncMock())
    with at(7, 45):
        await s.prepare()
    assert s._candidates == {} and not s._cluster_pairs and s.get_scanned_tickers() == []


# ===========================================================================
# §8 — 대시보드가 부르는 공개 메서드(registry.get_status) 는 다른 스윙 전략과 같은 모양
# ===========================================================================
def test_dashboard_surface_shapes():
    s = make()
    s._scanned_tickers = [T]
    assert s.get_scanned_tickers() == [T]
    stats = s.get_scan_stats()
    assert isinstance(stats, dict)
    targets = s.get_targets_status()
    assert set(targets) == {T}
    row = targets[T]
    assert row["prev_close"] == 10_000
    assert row["target_price"] == 9_900, "공용 표의 목표가 칸 = 돌파선"


# ===========================================================================
# §11 domain-expert 자문 반영 — L7 보강 · L8 수정 · 복구 덮어쓰기 · 069500 달력 · 관측
# ===========================================================================
def test_open_unknown_none_without_latch(caplog):
    """L7 보강 — 시가 결측(0)이면 갭·붕괴를 판정하지 않고 NONE(무래치) — 갭 검사 없이 BUY 금지."""
    s = make()
    with at(9, 10):
        assert s.check_buy_signal(T, PX, 0) == Signal.NONE
        assert T not in s._bought_today
        assert s.check_buy_signal(T, PX, -1) == Signal.NONE
    assert len(skips(caplog, "open_unknown")) == 1
    with at(9, 11):
        assert s.check_buy_signal(T, PX, OPEN) == Signal.BUY, "시가가 들어오면 다시 본다(래치 없음)"


def test_open_unknown_before_gap_and_collapse(caplog):
    s = make()
    with at(9, 10):
        assert s.check_buy_signal(T, 1, 0) == Signal.NONE
    assert skips(caplog, "collapse") == [] and skips(caplog, "gap_up") == []


def test_cluster_pool_includes_sold_today(caplog):
    """L8 수정 — 이 전략이 당일 매도한 같은 묶음 종목도 그날 묶음 보유로 친다(dedup exit_day_holds=True)."""
    s = make()
    s._cluster_pairs = {frozenset({T, U})}
    s.state.sold_today.add(U)
    with at(9, 10):
        assert s.check_buy_signal(T, PX, OPEN) == Signal.NONE
    assert len(skips(caplog, "cluster_held")) == 1
    assert T not in s._bought_today


def test_buy_eval_marker_with_shadow_buy(caplog):
    """관측 — [shadow_buy] 와 함께 [etf_trend_buy_eval] 1회/종목/일."""
    s = make(shadow=True)
    with at(9, 10):
        for _ in range(3):
            assert s.check_buy_signal(T, PX, OPEN) == Signal.NONE
    got = msgs(caplog, "[etf_trend_buy_eval]")
    assert len(got) == 1 and T in got[0], got
    assert field(got[0], "open_price") == str(OPEN)
    assert field(got[0], "current_price") == str(PX)
    assert field(got[0], "prev_close") == "10000"
    assert field(got[0], "line") == "9900"
    for k in ("N", "m", "cluster"):
        field(got[0], k)


@pytest.mark.asyncio
async def test_recompute_overwrites_daily_state_on_every_boot(monkeypatch):
    """§11 — hsb·bars·channel 은 매 부팅 다시 계산해 덮는다. 돌파선·N 만 기존 값 유지."""
    asc = int_bars(61, LAST + timedelta(days=3), breakout=False)   # 마지막 = 09-28(월) 봉
    day1, day2 = asc[:-1], asc
    buy_date = day1[-3][0]
    s = make(sizing_mode="turtle")
    s.state.positions[T] = pos(days_ago=(DAY - buy_date).days)
    s._hsb_closed[T] = 99_999                    # 낡은 값 — 덮여야 한다
    s._channel_low[T] = 1
    s._bars_since_buy[T] = 42
    with at(7, 50):
        await _recompute(s, monkeypatch, {T: to_rows(T, day1)})
    line1, n1 = s._breakout_line[T], s._entry_atr[T]
    assert s._bars_since_buy[T] == 3
    assert s._hsb_closed[T] == max(r[2] for r in day1 if r[0] >= buy_date)
    assert s._channel_low[T] == min(r[3] for r in day1[-10:])
    with at(7, 50, day=DAY + timedelta(days=1)):
        await _recompute(s, monkeypatch, {T: to_rows(T, day2)})
    assert s._bars_since_buy[T] == 4, "다음 부팅에서 완성봉 1개 증가"
    assert s._hsb_closed[T] == max(r[2] for r in day2 if r[0] >= buy_date)
    assert s._channel_low[T] == min(r[3] for r in day2[-10:])
    assert s._breakout_line[T] == line1 and s._entry_atr[T] == n1, "돌파선·N 은 덮지 않는다"


@pytest.mark.asyncio
async def test_recompute_bars_counted_on_k200_calendar(monkeypatch):
    """§11 — bars = 069500 달력에서 날짜 ≥ 매수일 봉 수(종목 봉에 구멍이 있어도)."""
    asc = int_bars(60, LAST, breakout=False)
    buy_date = asc[-4][0]
    holed = [r for r in asc if r[0] != asc[-2][0]]           # 매수 뒤 하루가 종목에 없다
    s = make(sizing_mode="turtle")
    s.state.positions[T] = pos(days_ago=(DAY - buy_date).days)
    with at(7, 50):
        await _recompute(s, monkeypatch, {T: to_rows(T, holed), "069500": k200_rows(asc)})
    assert s._bars_since_buy[T] == 4
    assert s._hsb_closed[T] == max(r[2] for r in holed if r[0] >= buy_date), "hsb 는 종목이 가진 봉으로"


@pytest.mark.asyncio
async def test_recompute_head_stale_warns_and_uses_k200_count(monkeypatch, caplog):
    asc = int_bars(60, LAST, breakout=False)
    buy_date = asc[-4][0]
    stale = asc[:-1]                                          # 종목 최신 봉이 069500 보다 하루 늦다
    s = make(sizing_mode="turtle")
    s.state.positions[T] = pos(days_ago=(DAY - buy_date).days)
    with at(7, 50):
        await _recompute(s, monkeypatch, {T: to_rows(T, stale), "069500": k200_rows(asc)})
    warns = [ln for ln in msgs(caplog, "[etf_trend_recover_skip]", min_level=logging.WARNING)
             if field(ln, "reason") == "head_stale"]
    assert len(warns) == 1 and T in warns[0]
    assert s._bars_since_buy[T] == 4, "값은 069500 달력으로 센 것"
    assert s._channel_low[T] == min(r[3] for r in stale[-10:])


# ===========================================================================
# 팀장 검토 2차 라운드 — HIGH-1 · MED-1 · MED-2 · LOW-2 · LOW-3 · LOW-4
# ===========================================================================
@pytest.mark.asyncio
async def test_recompute_adds_cluster_pairs_for_held_against_cached_candidates(monkeypatch):
    """팀장 검토 HIGH-1 — prepare() 는 positions 복구 전에 돈다(boot_manager). positions 가
    비어 있는 그 시점에 prepare 가 캐시해 둔 후보 종가를 recompute_held_atr() 가 (positions
    복구 뒤) 재사용해 보유×후보 상관을 마저 완성한다. `_cluster_pairs` 를 직접 주입하지 않고
    ①prepare(positions 비어 있음) → ②positions 복구 → ③recompute_held_atr → ④묶음 재현한다."""
    import importlib

    asc_a = bars(150, LAST)              # 후보 A — 돌파 신호 봉(유니버스)
    asc_u = bars(150, LAST)              # 보유 U — A 와 완전히 같은 가격 계열(상관 1.0)
    table = {
        A: to_rows(A, asc_a), U: to_rows(U, asc_u),
        "069500": to_rows("069500", bars(150, LAST, breakout=False)),
    }
    universe = [{"ticker": A, "name": "합성A", "hts_avls_eok": 1_000}]

    async def fake_universe(min_market_cap_eok: int = 500):
        return [dict(u) for u in universe]

    monkeypatch.setattr("src.db.stock_master.list_etf_trend_universe", fake_universe, raising=False)
    mod = importlib.import_module("src.engine.strategies.etf_trend")
    if hasattr(mod, "list_etf_trend_universe"):
        monkeypatch.setattr(mod, "list_etf_trend_universe", fake_universe)
    daily = Daily(table)
    install_daily(monkeypatch, daily)

    s = make()
    monkeypatch.setattr(s, "_refresh_market_unit", AsyncMock())
    with at(7, 45):
        await s.prepare()                                  # ① positions 비어 있음
    assert A in s._candidates and not s._cluster_pairs, "풀 크기 1(후보뿐) — 아직 묶을 상대가 없다"
    assert A in s._candidate_closes, "후보 종가는 prepare 단계에서 캐시된다(HIGH-1)"

    s.state.positions[U] = pos(U, days_ago=3)              # ② positions 복구(부팅 순서상 여기서 생김)
    daily.calls.clear()
    monkeypatch.setattr("src.db.positions.update_high", AsyncMock())
    monkeypatch.setattr("src.db.system_logs.write_log", AsyncMock())
    with at(7, 50):
        await s.recompute_held_atr()                       # ③

    assert frozenset({A, U}) in s._cluster_pairs, "④ 보유(U)×후보(A) 가 같은 묶음으로 잡혀야 한다"
    assert all(t != A for t, _ in daily.calls), (
        f"후보 종가는 prepare 캐시를 재사용한다 — recompute 가 후보를 다시 읽으면 안 됨: {daily.calls}"
    )


def test_rebuy_pops_stale_multiday_state():
    """팀장 검토 MED-1 — BUY 확정 자리에서 옛 멀티데이 상태를 지운다(재매수 때 잔존 금지)."""
    s = make(sizing_mode="turtle")
    s._hsb_closed[T] = 99_999
    s._channel_low[T] = 1
    s._bars_since_buy[T] = 42
    with at(9, 10):
        assert s.check_buy_signal(T, PX, OPEN) == Signal.BUY
    assert T not in s._hsb_closed and T not in s._channel_low and T not in s._bars_since_buy


@pytest.mark.asyncio
async def test_recompute_pops_hsb_when_no_bars_since_buy(monkeypatch):
    """팀장 검토 MED-1 — recompute 에서 매수일 이후 봉이 하나도 없으면 옛 hsb 를 남기지 않는다."""
    asc = int_bars(60, LAST, breakout=False)
    s = make(sizing_mode="turtle")
    s.state.positions[T] = pos(T, days_ago=0)   # buy_date=DAY, 모든 봉(≤LAST)이 그 전 — after 가 빈다
    s._hsb_closed[T] = 99_999
    with at(7, 50):
        await _recompute(s, monkeypatch, {T: to_rows(T, asc)})
    assert T not in s._hsb_closed, "매수일 이후 완성봉이 없으면 옛 hsb 값을 지운다"


def test_clean_rows_drops_non_positive_ohlc():
    """팀장 검토 MED-2 — O/H/L/C ≤ 0 봉은 prepare·recompute 두 자리에서 같은 헬퍼로 거른다."""
    good = {"bas_dd": date(2026, 9, 1), "open_price": 100, "high_price": 110,
            "low_price": 90, "close_price": 105}
    rows = [
        good,
        {**good, "bas_dd": date(2026, 9, 2), "open_price": 0},
        {**good, "bas_dd": date(2026, 9, 3), "high_price": -1},
        {**good, "bas_dd": date(2026, 9, 4), "low_price": 0},
        {**good, "bas_dd": date(2026, 9, 5), "close_price": 0},
    ]
    out = cls()._clean_rows(rows)
    assert out == [good]


@pytest.mark.asyncio
async def test_recompute_one_ticker_error_does_not_block_others(monkeypatch, caplog):
    """팀장 검토 LOW-2 — recompute_held_atr 종목 루프, 한 종목 예외가 나머지 종목 복구를 끊지 않는다."""
    asc_ok = int_bars(60, LAST, breakout=False)
    bad = to_rows(U, asc_ok)
    bad[3]["bas_dd"] = None   # 날짜 비교 TypeError 유발 — OHLC 는 정상이라 _clean_rows 는 못 거른다
    buy_date = asc_ok[-3][0]
    s = make(sizing_mode="turtle")
    s.state.positions[T] = pos(T, days_ago=(DAY - buy_date).days)
    s.state.positions[U] = pos(U, days_ago=(DAY - buy_date).days)
    with at(7, 50):
        await _recompute(s, monkeypatch, {T: to_rows(T, asc_ok), U: bad})
    assert T in s._breakout_line and T in s._entry_atr, "T 는 U 의 예외와 무관하게 정상 복구돼야 한다"
    warns = msgs(caplog, "[etf_trend_recover_skip]", min_level=logging.WARNING)
    assert any(U in w and field(w, "reason") == "ticker_error" for w in warns), warns


def test_sizing_mode_invalid_skips_check_buy_signal_with_warning(caplog):
    """팀장 검토 LOW-3 — 터틀 전용. PUT 오조작(position_ratio)이면 신호 단계에서 거부."""
    s = make(sizing_mode="position_ratio")
    with at(9, 10):
        assert s.check_buy_signal(T, PX, OPEN) == Signal.NONE
    assert T not in s._bought_today
    warns = msgs(caplog, "[etf_trend_skip]", min_level=logging.WARNING)
    assert any(T in w and field(w, "reason") == "sizing_mode_invalid" for w in warns), warns


def test_calc_buy_quantity_sizing_mode_invalid_returns_zero(caplog):
    """팀장 검토 LOW-3 — calc_buy_quantity 도 같은 거부(비중 경로를 열지 않는다)."""
    s = make(sizing_mode="position_ratio")
    with at(9, 10):
        assert s.calc_buy_quantity(PX, T) == 0
    assert T not in s._entry_atr
    warns = msgs(caplog, "[etf_trend_skip]", min_level=logging.WARNING)
    assert any(T in w and field(w, "reason") == "sizing_mode_invalid" for w in warns), warns


def test_1520_check_marker_includes_checked_field(monkeypatch, caplog):
    """팀장 검토 LOW-4 — [etf_trend_1520_check] 에 실제로 가격까지 "판단"한 수(checked=) 를 남긴다."""
    s = three_held(monkeypatch)
    with at(15, 20, 30):
        s.check_force_clear()
    summ = msgs(caplog, "[etf_trend_1520_check]")
    assert len(summ) == 1
    assert field(summ[0], "checked") == "2", "V 는 D+1(bars<min_bars) 이라 가격 판단 전에 continue"


@pytest.mark.asyncio
async def test_recompute_warns_when_k200_totally_unavailable(monkeypatch, caplog):
    """팀장 검토 LOW-4 — 069500 자체가 0봉(판단 근거 없음)일 때만 경고한다."""
    asc = int_bars(60, LAST, breakout=False)
    s = make(sizing_mode="turtle")
    s.state.positions[T] = pos(T, days_ago=(DAY - asc[-3][0]).days)
    with at(7, 50):
        await _recompute(s, monkeypatch, {T: to_rows(T, asc), "069500": []})
    warns = msgs(caplog, "[etf_trend_recover_skip]", min_level=logging.WARNING)
    assert any("069500" in w and field(w, "reason") == "k200_unavailable" for w in warns), warns
