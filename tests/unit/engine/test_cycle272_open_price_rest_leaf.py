"""cycle272 Red — 행위 leaf `src/engine/open_price_rest.py`. 계약 C11~C23·C25.

명세 정본 = `_workspace/red/cycle272_rest_open_basis_spec.md`
자문 정본 = `_workspace/domain_consult/cycle272_rest_open_basis_20260910.md`

**Red 단계 — 테스트만. `src/` 미변경.** Green = backend-dev.

## ⚠️ 이 leaf 는 관측 leaf 가 아니라 **행위 leaf** 다

cycle264 `open_price_observe.py` 는 "행위 변경 0" 이 첫 계약인 관측 leaf 였다. 이 모듈은
반대다 — **목표가를 실제로 세운다.** 그래서 `never-raise` 는 **관측에만** 적용되고,
확보 실패(`rest_zero`/`rest_error`)는 침묵하지 않고 **계수·기록**한다. 침묵하면
"REST 가 전부 일치했다" 와 "REST 가 N 종목에서 아무것도 못 줬다" 가 구별되지 않는다
(cycle237 C237-L2-1 동형).

## 왜 09:00:35 를 R1 으로 두는가 (자문 §2, 실측)

첫 MAIN 체결 누적 분포가 **09:00:05 에 12~21% → 09:00:30 에 96.9~97.8%** 다.
09:00:05 에 전 종목을 훑으면 5분의 4가 재시도 대기열로 밀리고 그 대기열 자체가
랜덤엔드 취약성이다. R1 을 09:00:35 로 두면 한 라운드로 ~97% 가 끝난다.
`+5초` 는 `SWING_REST_POLL_EARLY_START = 09:00:30`(보유 종목 폴)과 같은 순간을 피하려는
것이고, 곡선이 그 뒤로 평평하므로 5초는 아무것도 잃지 않는다.
재시도 간격 하한은 **5초**다 — `fetch_stock_detail` 캐시 TTL 이 5초라 그보다 짧은
재시도는 같은 캐시값을 다시 읽어 무의미하다. 30초는 이 계약을 넉넉히 만족한다.

## 이 파일이 잠그는 것

| C | 내용 |
|---|---|
| C11 | 라운드 시각 09:00:35·…·09:04:35(fast 9) → 300초 간격 15:20 까지(slow) |
| C12 | 대상 = main∈boards ∧ enforce ∧ 미확정 · **`config.enabled` 미사용**(비활성 전략도 스윕) |
| C13 | 공통 종목 한 라운드 fetch **정확히 1회** ∧ 확정은 두 전략 모두에 |
| C14 | 확정 시 setter(`source="rest"`) **와** `mark_confirmed_via_rest` **둘 다** |
| C15 | `"0"`/`""`/`"abc"` → `rest_zero` · 예외 → `rest_error` **분리 계수**, 둘 다 미확정 |
| C16 | 종목 간 `sleep(0.05)` 실삽입 ∧ 어떤 1초 반열린 구간도 REST ≤ 20건 |
| C17 | 벽시계 45초 초과 → 라운드 절단 + `truncated=1`, 다음 라운드는 정상 발화 |
| C18 | 라운드 예외에도 task 생존 · `CancelledError` re-raise |
| C19 | `_targets` 비면 REST 0콜 · 준비 폴링 90초 초과 시 `skipped reason=no_target` 1행 |
| C20 | `scanner.ticker_prices` **읽기 전용** — 라운드 전후 스냅샷 동일 |
| C21 | 마지막 fast 라운드 직후 미확정마다 `[main_rest_basis_unresolved]` 1회/(전략,종목)/일 |
| C22 | task 속성 `_main_rest_basis_task` ∧ 세 취소 목록 전부 등재 |
| C23 | `owns_board` True 동안 confirm 은 그 전략을 빼고, 둘 다 빠지면 WS 폴링 0초·REST 0콜 |
| C25 | 09:05:00 이후 `owns_board` False → 2차 REST 폴백이 백스톱 확정 · 예외는 False(fail-open) |

## 무접촉 6종

전략 비중 · `position_ratio` · `max_positions` · 랏 캡(K·K_ρ) · `open_entry_hold_secs` ·
LTV 청산 규약 — 이 파일의 어떤 테스트도 그 값을 바꾸지 않는다.

## caplog 규약

로거명(`src.engine.open_price_rest` · `src.engine.scheduler`) + `levelno >= INFO` +
마커 prefix **3중 한정**(CI 루트 로거 DEBUG 차이 — cycle252 T2).
"""

from __future__ import annotations

import ast
import asyncio
import copy
import logging
from datetime import time
from pathlib import Path
from unittest.mock import patch

import pytest

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parents[3]
_SCHEDULER_PATH = _ROOT / "src" / "engine" / "scheduler.py"

_LEAF_LOGGER = "src.engine.open_price_rest"
_SCHED_LOGGER = "src.engine.scheduler"
_LOGGER_NAMES = (_LEAF_LOGGER, _SCHED_LOGGER)

_M_CONFIG = "[main_rest_basis_config]"
_M_ROUND = "[main_rest_basis_round]"
_M_CONFIRMED = "[main_rest_basis_confirmed]"
_M_UNRESOLVED = "[main_rest_basis_unresolved]"

KEY = "open_price_scope_mode"
_T1, _T2, _T3 = "005930", "000660", "035720"


# ===========================================================================
# 리그
# ===========================================================================

def _lines(caplog, marker: str) -> list[str]:
    return [
        r.getMessage()
        for r in caplog.records
        if r.name in _LOGGER_NAMES and r.levelno >= logging.INFO
        and r.getMessage().startswith(marker)
    ]


def _open_info(caplog) -> None:
    for name in _LOGGER_NAMES:
        caplog.set_level(logging.INFO, logger=name)


def _field(line: str, key: str) -> str:
    token = f" {key}="
    idx = line.index(token) + len(token)
    return line[idx:].split(" ")[0]


def _target(offset: int = 500, *, boards: dict | None = None) -> dict:
    return {
        "k": 0.5,
        "prev_range": 1000,
        "target_offset_base": offset,
        "target_offset": offset,
        "target_price": 0,
        "open_price": 0,
        "boards": dict(boards or {}),
    }


def _make_sched(*, vb_targets=None, ltv_targets=None,
                vb_enabled=True, ltv_enabled=True,
                vb_mode="enforce", ltv_mode="enforce",
                vb_boards=None, ltv_boards=None):
    """VB/LTV 가 등록된 최소 `TradingScheduler` (cycle264 픽스처 패턴 답습)."""
    from src.engine.scheduler import TradingScheduler
    from src.engine.strategies.long_tail_volatility import LongTailVolatilityStrategy
    from src.engine.strategies.volatility_breakout import VolatilityBreakoutStrategy
    from src.engine.strategy_base import StrategyConfig
    from src.engine.strategy_registry import StrategyRegistry

    with patch("src.engine.scheduler.token_manager"), \
         patch("src.engine.scheduler.kis_ws"), \
         patch("src.engine.scheduler.kis_ws_pool"):
        sched = TradingScheduler.__new__(TradingScheduler)
        sched.registry = StrategyRegistry()
        sched._pending_next_day_clear = set()
        sched._running = True
        sched._phase = "main_trading"

        for cls, sid, name, targets, enabled, mode, boards in (
            (VolatilityBreakoutStrategy, "volatility_breakout", "변동성 돌파",
             vb_targets, vb_enabled, vb_mode, vb_boards),
            (LongTailVolatilityStrategy, "long_tail_volatility", "롱테일 변동성 돌파",
             ltv_targets, ltv_enabled, ltv_mode, ltv_boards),
        ):
            s = cls(StrategyConfig(strategy_id=sid, name=name, enabled=enabled, weight=0.3))
            s.config.params[KEY] = mode
            s.config.params["k_value_krx_main"] = 1.0
            s.config.params["tradable_boards"] = list(boards or ["main"])
            for t, info in (targets or {}).items():
                s._targets[t] = info
                s._open_confirmed[t] = {
                    b: True for b, bi in (info.get("boards") or {}).items()
                    if (bi or {}).get("open_price", 0) > 0
                }
            sched.registry.register(s)
        return sched


@pytest.fixture(autouse=True)
def _reset_caps():
    def _reset():
        try:
            from src.engine import open_price_rest as leaf
        except Exception:
            return
        fn = getattr(leaf, "reset_main_rest_basis_caps", None)
        if callable(fn):
            fn()
        try:
            from src.engine import open_price_observe as obs
            obs.reset_open_source_compare_cap()
        except Exception:
            pass

    _reset()
    yield
    _reset()


@pytest.fixture
def rest_stub(monkeypatch):
    """`fetch_stock_detail` 스텁 + 호출 타임스탬프 프로브.

    leaf 가 함수 안 지연 import 를 쓰든 모듈 최상단 import 를 쓰든 양쪽을 덮는다
    (구현 자유도 보존, cycle264 선례).
    """
    from src.api import condition as cond

    state = {
        "calls": [],          # ticker 순서
        "stamps": [],         # 가짜 벽시계 기준 호출 시각(초)
        "table": {},          # ticker -> dict | Exception
        "cost_s": 0.0,        # 1콜당 소모 시간(가짜 시계)
        "clock": [0.0],
    }

    async def _fake(ticker: str) -> dict:
        state["calls"].append(ticker)
        state["stamps"].append(state["clock"][0])
        state["clock"][0] += state["cost_s"]
        value = state["table"].get(ticker, {"stck_oprc": "0"})
        if isinstance(value, BaseException):
            raise value
        return value

    monkeypatch.setattr(cond, "fetch_stock_detail", _fake)
    try:
        from src.engine import open_price_rest as leaf
        if hasattr(leaf, "fetch_stock_detail"):
            monkeypatch.setattr(leaf, "fetch_stock_detail", _fake)
        monkeypatch.setattr(leaf, "_fetch_stock_detail", _fake, raising=False)
        monkeypatch.setattr(leaf, "_monotonic", lambda: state["clock"][0], raising=False)
    except Exception:
        pass  # 모듈 부재 = Red. 각 테스트가 자기 import 로 명시 실패한다

    real_sleep = asyncio.sleep

    async def _fake_sleep(secs=0, *a, **kw):
        state.setdefault("sleeps", []).append(float(secs or 0))
        state["clock"][0] += float(secs or 0)
        return await real_sleep(0)

    monkeypatch.setattr(asyncio, "sleep", _fake_sleep)
    state.setdefault("sleeps", [])
    return state


# ===========================================================================
# C11 — 라운드 일정
# ===========================================================================

def test_c11_1_constants():
    """C11 — 상수 정본.

    - R1 = 09:00:35 (프린트 무릎 09:00:30 + 폴 정각 회피 5초)
    - 라운드 간격 30초 (캐시 TTL 5초의 6배)
    - fast 9회 → 마지막 09:04:35 (09:05:00 `_swing_buy_poll_loop` 정각 ·
      09:05:30 cycle264 대조 배치 **둘 다** 피한다)
    - slow 300초, 종료 15:20 (VB 매수컷과 같은 시각 — 그 뒤에 목표가를 세울 이유가 없다)
    - handoff 09:05:00 (이후 스케줄러 백스톱 부활)
    """
    from src.engine import open_price_rest as leaf

    assert leaf.TIME_MAIN_REST_BASIS_R1 == time(9, 0, 35)
    assert leaf.MAIN_REST_BASIS_ROUND_INTERVAL_S == 30.0
    assert leaf.MAIN_REST_BASIS_FAST_ROUNDS == 9
    assert leaf.MAIN_REST_BASIS_SLOW_INTERVAL_S == 300.0
    assert leaf.TIME_MAIN_REST_BASIS_STOP == time(15, 20)
    assert leaf.TIME_MAIN_REST_BASIS_HANDOFF == time(9, 5, 0)
    assert leaf._TICKER_SLEEP_S == 0.05
    assert leaf._ROUND_WALL_CLOCK_MAX_S == 45.0


def test_c11_2_fast_round_times_exact():
    """C11 — fast 9라운드가 **정확히** 09:00:35 … 09:04:35 다."""
    from src.engine import open_price_rest as leaf

    fast = [row for row in leaf.round_schedule() if row[2] == "fast"]
    assert [row[3] for row in fast] == [
        time(9, 0, 35), time(9, 1, 5), time(9, 1, 35), time(9, 2, 5), time(9, 2, 35),
        time(9, 3, 5), time(9, 3, 35), time(9, 4, 5), time(9, 4, 35),
    ], f"실측 {[str(r[3]) for r in fast]}"
    assert [row[0] for row in fast] == list(range(1, 10))
    assert {row[1] for row in fast} == {9}, "fast 분모는 9 (`round=1/9 kind=fast` 판독 규약)"


def test_c11_3_slow_rounds_every_300s_until_1520():
    """C11 — slow 라운드는 마지막 fast 로부터 300초 간격이고 **15:20 을 넘지 않는다**.

    슬로우 라운드의 존재 이유 = ① 재-prepare(`_reprepare_breakout_if_empty`)로 되살아난
    미확정 종목 회수 ② **킬스위치 카나리아의 종일 채널**(PUT 롤백 후 5분 안에
    `mode=off` 행이 뜨는 근거).
    """
    from src.engine import open_price_rest as leaf

    slow = [row for row in leaf.round_schedule() if row[2] == "slow"]
    assert slow, "slow 라운드가 하나도 없다"
    assert slow[0][3] == time(9, 9, 35), f"첫 slow 실측 {slow[0][3]}"
    assert slow[-1][3] <= time(15, 20), f"마지막 slow 가 15:20 을 넘었다 — {slow[-1][3]}"
    secs = [r[3].hour * 3600 + r[3].minute * 60 + r[3].second for r in slow]
    assert all(b - a == 300 for a, b in zip(secs, secs[1:])), "slow 간격이 300초가 아니다"
    assert {row[1] for row in slow} == {len(slow)}


def test_c11_4_no_round_after_stop():
    from src.engine import open_price_rest as leaf

    assert all(row[3] <= leaf.TIME_MAIN_REST_BASIS_STOP for row in leaf.round_schedule())


@pytest.mark.asyncio
async def test_c11_5_task_loop_waits_each_scheduled_time(monkeypatch):
    """C11 — task 루프가 일정의 **모든** 시각을 순서대로 대기하고 라운드를 1회씩 부른다.

    ⚠️ `advance_if_passed=True` 금지 — 09:06 재시작이면 내일까지 기다려 그날 확보가
    통째로 사라진다(KRX 시가는 종일 불변이라 늦은 시작은 즉시 실행이 정답).
    """
    from src.engine import open_price_rest as leaf

    sched = _make_sched(vb_targets={_T1: _target()})
    waited: list[tuple] = []
    ran: list[tuple] = []

    async def _fake_wait(target, **kw):
        waited.append((target, kw))

    async def _fake_round(_s, *, round_no, total_rounds, kind):
        ran.append((round_no, total_rounds, kind))
        return {"pending": 0}

    monkeypatch.setattr(sched, "_wait_until", _fake_wait)
    monkeypatch.setattr(leaf, "run_main_rest_basis_round", _fake_round)

    await leaf.main_rest_basis_task_loop(sched)

    schedule = leaf.round_schedule()
    assert [w[0] for w in waited] == [row[3] for row in schedule], (
        f"대기 시각이 일정과 다르다 — 실측 {[str(w[0]) for w in waited][:12]}"
    )
    assert not any(w[1].get("advance_if_passed") for w in waited), (
        "advance_if_passed=True 면 늦은 재시작이 그날 확보를 통째로 버린다"
    )
    assert ran == [(r[0], r[1], r[2]) for r in schedule]


# ===========================================================================
# C12 — 라운드 대상 판정
# ===========================================================================

@pytest.mark.asyncio
async def test_c12_1_only_unconfirmed_main_tickers_are_fetched(rest_stub):
    """C12 — 이미 `main` 확정된 종목은 다시 조회하지 않는다."""
    from src.engine import open_price_rest as leaf

    sched = _make_sched(vb_targets={
        _T1: _target(),
        _T2: _target(boards={"main": {"open_price": 70000, "target_price": 70500,
                                      "target_offset": 500}}),
    })
    rest_stub["table"] = {_T1: {"stck_oprc": "80000"}}

    await leaf.run_main_rest_basis_round(sched, round_no=1, total_rounds=9, kind="fast")

    assert rest_stub["calls"] == [_T1], f"실측 {rest_stub['calls']}"


@pytest.mark.asyncio
async def test_c12_2_disabled_strategy_is_still_swept(rest_stub):
    """C12 — **`config.enabled` 는 대상 판정에 쓰이지 않는다**(자문 D-9).

    09-10 17:07 부로 VB·LTV 가 `enabled=False weight=0` 이다. `config.enabled` 로 거르면
    금요일 실측이 통째로 0행이 된다. 비활성 전략은 `check_buy_signal` 자체가 불리지
    않으므로 **매매 위험 0** 이고, 이 결정 덕분에 **비중을 한 글자도 안 건드리고**
    REST 확보·오염 shadow·게이트·부하를 검증할 수 있다.
    """
    from src.engine import open_price_rest as leaf

    sched = _make_sched(vb_targets={_T1: _target()}, ltv_targets={_T2: _target()},
                        vb_enabled=False, ltv_enabled=False)
    rest_stub["table"] = {_T1: {"stck_oprc": "80000"}, _T2: {"stck_oprc": "50000"}}

    await leaf.run_main_rest_basis_round(sched, round_no=1, total_rounds=9, kind="fast")

    assert sorted(rest_stub["calls"]) == sorted([_T1, _T2]), (
        f"비활성 전략이 스윕에서 빠졌다 — 실측 {rest_stub['calls']}"
    )
    vb = sched.registry.get("volatility_breakout")
    assert (vb._open_confirmed.get(_T1) or {}).get("main") is True


@pytest.mark.asyncio
async def test_c12_3_strategy_without_main_board_excluded(rest_stub):
    """C12 — `main ∉ get_tradable_boards` 인 전략은 대상이 아니다."""
    from src.engine import open_price_rest as leaf

    sched = _make_sched(ltv_targets={_T2: _target()}, ltv_boards=["pre_nxt", "post_nxt"],
                        vb_targets={})
    await leaf.run_main_rest_basis_round(sched, round_no=1, total_rounds=9, kind="fast")
    assert rest_stub["calls"] == []


@pytest.mark.asyncio
async def test_c12_4_mode_off_strategy_excluded(rest_stub):
    """C12 — `off` 전략은 구(舊) 경로(WS·인라인)를 타므로 leaf 가 손대지 않는다."""
    from src.engine import open_price_rest as leaf

    sched = _make_sched(vb_targets={_T1: _target()}, vb_mode="off", ltv_targets={})
    await leaf.run_main_rest_basis_round(sched, round_no=1, total_rounds=9, kind="fast")
    assert rest_stub["calls"] == []


def test_c12_5_select_strategies_signature():
    """C12 — 대상 전략 선별이 **공개 함수**여야 D+1 판독·회귀 검증이 가능하다."""
    from src.engine import open_price_rest as leaf

    sched = _make_sched(vb_targets={_T1: _target()}, ltv_mode="off")
    picked = [sid for sid, _s in leaf.select_strategies(sched.registry)]
    assert picked == ["volatility_breakout"], f"실측 {picked}"


# ===========================================================================
# C13 — 합집합 distinct
# ===========================================================================

@pytest.mark.asyncio
async def test_c13_1_common_ticker_fetched_once_and_confirms_both(rest_stub):
    """C13 — VB·LTV 공통 종목은 한 라운드에 **정확히 1회** 조회하고 **둘 다** 확정한다.

    5초 캐시에 기대지 않는다 — 스윕이 15~28초라 TTL 밖이라서, 접지 않으면 같은 종목을
    두 번 쏜다(전역 20건/초 예산 낭비 + D+1 판독의 `calls` 축 왜곡).
    """
    from src.engine import open_price_rest as leaf

    sched = _make_sched(vb_targets={_T1: _target(500)}, ltv_targets={_T1: _target(700)})
    rest_stub["table"] = {_T1: {"stck_oprc": "80000"}}

    await leaf.run_main_rest_basis_round(sched, round_no=1, total_rounds=9, kind="fast")

    assert rest_stub["calls"] == [_T1], f"실측 {rest_stub['calls']}"
    vb = sched.registry.get("volatility_breakout")
    ltv = sched.registry.get("long_tail_volatility")
    assert vb._targets[_T1]["boards"]["main"]["target_price"] == 80500
    assert ltv._targets[_T1]["boards"]["main"]["target_price"] == 80700


# ===========================================================================
# C14 — 확정 경로
# ===========================================================================

@pytest.mark.asyncio
async def test_c14_1_confirm_uses_source_rest_keyword(rest_stub, monkeypatch):
    """C14 — 확정은 `on_open_price_confirmed(..., board="main", source="rest")` 다.

    `source` 를 빼면 게이트가 **자기 자신을 거부**해 그날 목표가가 0 이 된다.
    """
    from src.engine import open_price_rest as leaf

    sched = _make_sched(vb_targets={_T1: _target()})
    rest_stub["table"] = {_T1: {"stck_oprc": "80000"}}
    vb = sched.registry.get("volatility_breakout")

    seen: list[tuple] = []
    original = vb.on_open_price_confirmed

    def _spy(ticker, open_price, board="main", **kw):
        seen.append((ticker, open_price, board, kw))
        return original(ticker, open_price, board=board, **kw)

    monkeypatch.setattr(vb, "on_open_price_confirmed", _spy)

    await leaf.run_main_rest_basis_round(sched, round_no=1, total_rounds=9, kind="fast")

    assert seen == [(_T1, 80000, "main", {"source": "rest"})], f"실측 {seen!r}"
    assert vb._targets[_T1]["boards"]["main"]["open_price"] == 80000


@pytest.mark.asyncio
async def test_c14_2_marks_confirmed_via_rest(rest_stub):
    """C14 — cycle264 `used_src` 라벨도 같이 찍는다.

    이 라벨이 빠지면 `[open_source_compare] used_src` 가 전부 `ws` 로 보이고,
    시정 후의 **결함 서명**("ws 행이 한 줄이라도 있으면 게이트를 뚫었다") 이 무의미해진다.
    """
    from src.engine import open_price_observe as obs
    from src.engine import open_price_rest as leaf

    sched = _make_sched(vb_targets={_T1: _target()})
    rest_stub["table"] = {_T1: {"stck_oprc": "80000"}}

    await leaf.run_main_rest_basis_round(sched, round_no=1, total_rounds=9, kind="fast")

    assert obs.was_confirmed_via_rest("volatility_breakout", _T1, "main") is True


@pytest.mark.asyncio
async def test_c14_3_confirmed_marker_carries_ws_shadow(rest_stub, monkeypatch, caplog):
    """C14 — `[main_rest_basis_confirmed]` 가 **shadow**(옛 코드가 그 순간 썼을 값)를 병기한다.

    시정 후 cycle264 `[open_source_compare] delta_bp` 는 REST↔REST 라 **산술적으로 0** 이다.
    그래서 오염 규모의 정본을 이 마커로 옮긴다 — REST 조회 **직전** `ticker_prices` 를
    읽어 `ws_open`/`ws_src`/`delta_bp`/`target_ws`/`target_rest` 를 남기면 3일치 판독의
    `delta_bp` 중앙값 73.7~118.4bp 와 **같은 축에서 이어 읽을 수 있다**.

    ⚠️ 한계(판독문에 그대로 남길 것) — leaf 가 읽는 시각은 09:00:35 이고 옛 코드가 읽던
    시각은 09:00:05~14 다. `[7]` 이 일-스코프 상수라 그 30초 사이에 안 바뀌는 것이
    결함의 본질이므로 실무상 같은 값이지만 **동일 시각 대조는 아니다**.
    """
    from src.engine import open_price_rest as leaf
    from src.engine import scanner

    _open_info(caplog)
    monkeypatch.setattr(scanner, "ticker_prices", {_T1: {"open_price": 79000}})
    sched = _make_sched(vb_targets={_T1: _target(500)})
    rest_stub["table"] = {_T1: {"stck_oprc": "80000"}}

    await leaf.run_main_rest_basis_round(sched, round_no=1, total_rounds=9, kind="fast")

    lines = _lines(caplog, _M_CONFIRMED)
    assert len(lines) == 1, f"1회/(전략,종목)/일 — 실측 {lines!r}"
    line = lines[0]
    for token in ("strategy=", "ticker=", "board=main", "round=", "rest_open=",
                  "ws_open=", "ws_src=", "delta_bp=", "target_rest=", "target_ws="):
        assert token in line, f"필드 누락 {token!r} — {line!r}"
    assert _field(line, "rest_open") == "80000"
    assert _field(line, "ws_open") == "79000"
    assert _field(line, "ws_src") == "cache"
    assert _field(line, "target_rest") == "80500"
    assert _field(line, "target_ws") == "79500"


@pytest.mark.asyncio
async def test_c14_4_ws_src_absent_when_no_cache(rest_stub, monkeypatch, caplog):
    """C14 — WS 캐시에 시가가 없던 종목은 `ws_src=absent` 다.

    **오염이 아니라 부재**였던 코호트 — 채널 분리(P1-7 B)가 못 고치는 부분의 크기를
    처음으로 재는 축이다(`nxt_false` 무송출 코호트가 여기 잡힌다).
    """
    from src.engine import open_price_rest as leaf
    from src.engine import scanner

    _open_info(caplog)
    monkeypatch.setattr(scanner, "ticker_prices", {})
    sched = _make_sched(vb_targets={_T1: _target(500)})
    rest_stub["table"] = {_T1: {"stck_oprc": "80000"}}

    await leaf.run_main_rest_basis_round(sched, round_no=1, total_rounds=9, kind="fast")

    line = _lines(caplog, _M_CONFIRMED)[0]
    assert _field(line, "ws_src") == "absent"
    assert _field(line, "ws_open") == "0"


# ===========================================================================
# C15 — 실패 계수 분리
# ===========================================================================

@pytest.mark.asyncio
@pytest.mark.parametrize("payload", [
    {"stck_oprc": "0"}, {"stck_oprc": ""}, {"stck_oprc": "abc"},
    {"stck_oprc": None}, {}, None,
])
async def test_c15_1_non_positive_open_counts_as_rest_zero(rest_stub, payload):
    """C15 — 미프린트(`"0"`)·빈값·비숫자·부재는 전부 `rest_zero` 이고 **확정하지 않는다**.

    "그 종목은 그 시점 매수 불가" 가 설계다 — **틀린 목표선으로 들어간 포지션은
    손절선까지 틀리지만, 안 들어간 종목은 기회비용만 남는다.**
    """
    from src.engine import open_price_rest as leaf

    sched = _make_sched(vb_targets={_T1: _target()})
    rest_stub["table"] = {_T1: payload}

    stats = await leaf.run_main_rest_basis_round(
        sched, round_no=1, total_rounds=9, kind="fast",
    )

    assert stats["zero"] == 1 and stats["err"] == 0 and stats["ok"] == 0, f"실측 {stats!r}"
    vb = sched.registry.get("volatility_breakout")
    assert (vb._open_confirmed.get(_T1) or {}).get("main") is not True
    assert "main" not in (vb._targets[_T1].get("boards") or {})


@pytest.mark.asyncio
@pytest.mark.parametrize("exc", [
    RuntimeError("boom"), asyncio.TimeoutError(), ValueError("bad"),
])
async def test_c15_2_exception_counts_as_rest_error(rest_stub, exc):
    """C15 — 예외는 `rest_error` 로 **분리** 계수된다.

    현행 `_confirm_breakout_open_prices` 2차 폴백은 한 `except` 로 삼켜 둘을 구분할 수
    없다. 이 분리가 O-1(미프린트 vs 예외)을 **하루 만에** 가른다.
    """
    from src.engine import open_price_rest as leaf

    sched = _make_sched(vb_targets={_T1: _target()})
    rest_stub["table"] = {_T1: exc}

    stats = await leaf.run_main_rest_basis_round(
        sched, round_no=1, total_rounds=9, kind="fast",
    )

    assert stats["err"] == 1 and stats["zero"] == 0 and stats["ok"] == 0, f"실측 {stats!r}"
    vb = sched.registry.get("volatility_breakout")
    assert (vb._open_confirmed.get(_T1) or {}).get("main") is not True


@pytest.mark.asyncio
async def test_c15_3_cancelled_error_is_not_absorbed(rest_stub):
    """C15 — `CancelledError` 는 `rest_error` 로 삼키지 않는다(취소가 라운드에 갇히면 안 된다)."""
    from src.engine import open_price_rest as leaf

    sched = _make_sched(vb_targets={_T1: _target()})
    rest_stub["table"] = {_T1: asyncio.CancelledError()}

    with pytest.raises(asyncio.CancelledError):
        await leaf.run_main_rest_basis_round(sched, round_no=1, total_rounds=9, kind="fast")


@pytest.mark.asyncio
async def test_c15_4_round_marker_fields(rest_stub, caplog):
    """C15/C21 — `[main_rest_basis_round]` 가 판독에 필요한 전 필드를 싣는다.

    이 마커가 `[breakout_open_confirm] truth_*` 의 **대체 커버리지 채널**이다
    (`owns_board` 때문에 그 마커는 09:00:1x 에 사라진다 — 의도된 침묵).
    """
    from src.engine import open_price_rest as leaf

    _open_info(caplog)
    sched = _make_sched(vb_targets={_T1: _target(), _T2: _target(), _T3: _target()},
                        ltv_targets={})
    rest_stub["table"] = {
        _T1: {"stck_oprc": "80000"},
        _T2: {"stck_oprc": "0"},
        _T3: RuntimeError("boom"),
    }

    await leaf.run_main_rest_basis_round(sched, round_no=1, total_rounds=9, kind="fast")

    lines = [ln for ln in _lines(caplog, _M_ROUND) if "strategy=volatility_breakout" in ln]
    assert len(lines) == 1, f"fast 라운드는 전략별 1행 — 실측 {_lines(caplog, _M_ROUND)!r}"
    line = lines[0]
    assert _field(line, "round") == "1/9"
    assert _field(line, "kind") == "fast"
    assert _field(line, "board") == "main"
    assert _field(line, "total") == "3"
    assert _field(line, "ok") == "1"
    assert _field(line, "zero") == "1"
    assert _field(line, "err") == "1"
    assert _field(line, "calls") == "3"
    assert _field(line, "truncated") == "0"
    assert "elapsed_ms=" in line and "mode=enforce" in line and "pending=" in line


@pytest.mark.asyncio
async def test_c15_5_slow_round_is_silent_when_nothing_pending(rest_stub, caplog):
    """C15 — slow 라운드는 `pending>0` 일 때만 행을 남긴다(종일 5분 로그 폭주 차단)."""
    from src.engine import open_price_rest as leaf

    _open_info(caplog)
    sched = _make_sched(vb_targets={
        _T1: _target(boards={"main": {"open_price": 80000, "target_price": 80500,
                                      "target_offset": 500}}),
    })

    await leaf.run_main_rest_basis_round(sched, round_no=1, total_rounds=75, kind="slow")

    assert _lines(caplog, _M_ROUND) == []
    assert rest_stub["calls"] == []


# ===========================================================================
# C16 — throttle
# ===========================================================================

@pytest.mark.asyncio
async def test_c16_1_sleep_between_tickers(rest_stub):
    """C16 — 종목 사이에 `asyncio.sleep(0.05)` 가 **실제로** 삽입된다.

    sleep 을 지우는 뮤테이션이 이 테스트로 KILL 된다.
    """
    from src.engine import open_price_rest as leaf

    tickers = [f"{i:06d}" for i in range(1, 11)]
    sched = _make_sched(vb_targets={t: _target() for t in tickers})
    rest_stub["table"] = {t: {"stck_oprc": "80000"} for t in tickers}

    await leaf.run_main_rest_basis_round(sched, round_no=1, total_rounds=9, kind="fast")

    ticks = [s for s in rest_stub["sleeps"] if s == leaf._TICKER_SLEEP_S]
    assert len(ticks) >= len(tickers) - 1, (
        f"종목 간 sleep 이 부족하다 — 실측 {rest_stub['sleeps']!r}"
    )


@pytest.mark.asyncio
async def test_c16_2_never_exceeds_20_calls_per_second(rest_stub):
    """C16 — 어떤 **반열린 1초 구간** `[t, t+1)` 에서도 REST 호출이 20건을 넘지 않는다.

    전역 리미터는 20건/초(메인·보조 7계정 공용, `src/api/base.py:437-451`)이고 09:00~09:01:30
    창의 실제 매수 트래픽은 09-08·09-09 실측 **BUY 0건**이라 다툴 상대는 없지만, 설계가
    한도에 닿는 것 자체가 회귀 신호다(실측 순차 상한은 sleep 0.05 에서 6~9건/초).
    """
    from src.engine import open_price_rest as leaf

    tickers = [f"{i:06d}" for i in range(1, 141)]      # 설계 상한 N=140
    sched = _make_sched(vb_targets={t: _target() for t in tickers})
    rest_stub["table"] = {t: {"stck_oprc": "80000"} for t in tickers}
    rest_stub["cost_s"] = 0.0                          # 최악(무한대 빠른 REST)

    await leaf.run_main_rest_basis_round(sched, round_no=1, total_rounds=9, kind="fast")

    stamps = rest_stub["stamps"]
    assert len(stamps) == 140

    # ⚠️ 가짜 시계 누산(0.05 × N)의 부동소수 드리프트가 경계를 흔든다 —
    #    설계가 정확히 20건/초에 닿아 있어서 float 비교로는 21 이 나온다.
    #    ms 격자로 반올림해 잰다(0.05s = 50ms 간격 대비 충분히 미세한 해상도).
    ms = [round(s * 1000) for s in stamps]
    worst = max(sum(1 for m in ms if a <= m < a + 1000) for a in ms)
    assert worst <= 20, f"1초 반열린 구간 최대 {worst}건 — 전역 한도 20 초과"

    gaps = [b - a for a, b in zip(ms, ms[1:])]
    assert gaps and min(gaps) >= round(leaf._TICKER_SLEEP_S * 1000), (
        f"연속 호출 최소 간격이 {min(gaps)}ms — 버스트가 있다(sleep 누락/조건부 삽입)"
    )


# ===========================================================================
# C17 — 라운드 벽시계 상한
# ===========================================================================

@pytest.mark.asyncio
async def test_c17_1_round_truncates_past_wall_clock_max(rest_stub, caplog):
    """C17 — 벽시계 45초를 넘으면 그 라운드를 끊고 `truncated=1` 로 남긴다.

    라운드가 다음 라운드(30초 뒤)를 침범하면 같은 종목에 중복 요청이 겹친다.
    네트워크 열화 같은 비상 상황의 안전판이다.
    """
    from src.engine import open_price_rest as leaf

    _open_info(caplog)
    tickers = [f"{i:06d}" for i in range(1, 21)]
    sched = _make_sched(vb_targets={t: _target() for t in tickers})
    rest_stub["table"] = {t: {"stck_oprc": "80000"} for t in tickers}
    rest_stub["cost_s"] = 5.0                       # 1콜 5초 → 10콜이면 50초

    stats = await leaf.run_main_rest_basis_round(
        sched, round_no=1, total_rounds=9, kind="fast",
    )

    assert stats["truncated"] == 1, f"실측 {stats!r}"
    assert stats["calls"] < len(tickers), "절단됐는데 전 종목을 다 쐈다"
    line = [ln for ln in _lines(caplog, _M_ROUND) if "strategy=volatility_breakout" in ln][0]
    assert _field(line, "truncated") == "1"


@pytest.mark.asyncio
async def test_c17_2_next_round_still_fires_after_truncation(rest_stub, monkeypatch):
    """C17 — 절단된 라운드가 task 를 멈추지 않는다. 다음 라운드가 예정대로 돈다."""
    from src.engine import open_price_rest as leaf

    sched = _make_sched(vb_targets={_T1: _target()})
    ran: list[int] = []

    async def _fake_round(_s, *, round_no, total_rounds, kind):
        ran.append(round_no)
        return {"pending": 1, "truncated": 1}

    async def _fake_wait(target, **kw):
        return None

    monkeypatch.setattr(sched, "_wait_until", _fake_wait)
    monkeypatch.setattr(leaf, "run_main_rest_basis_round", _fake_round)

    await leaf.main_rest_basis_task_loop(sched)

    assert ran[:3] == [1, 2, 3]


# ===========================================================================
# C18 — lifecycle
# ===========================================================================

@pytest.mark.asyncio
async def test_c18_1_round_exception_does_not_kill_task(monkeypatch):
    """C18 — 라운드 본체 예외에도 task 는 죽지 않고 다음 라운드가 돈다."""
    from src.engine import open_price_rest as leaf

    sched = _make_sched(vb_targets={_T1: _target()})
    ran: list[int] = []

    async def _boom(_s, *, round_no, total_rounds, kind):
        ran.append(round_no)
        raise RuntimeError("라운드 폭발")

    async def _fake_wait(target, **kw):
        return None

    monkeypatch.setattr(sched, "_wait_until", _fake_wait)
    monkeypatch.setattr(leaf, "run_main_rest_basis_round", _boom)

    await leaf.main_rest_basis_task_loop(sched)      # 예외가 새어 나오면 FAIL

    assert len(ran) == len(leaf.round_schedule()), f"실측 {len(ran)}회"


@pytest.mark.asyncio
async def test_c18_2_cancelled_error_is_reraised(monkeypatch):
    """C18 — `CancelledError` 는 re-raise. 흡수하면 `stop()` 이 좀비 task 를 남긴다."""
    from src.engine import open_price_rest as leaf

    sched = _make_sched(vb_targets={_T1: _target()})

    async def _cancel(_s, *, round_no, total_rounds, kind):
        raise asyncio.CancelledError()

    async def _fake_wait(target, **kw):
        return None

    monkeypatch.setattr(sched, "_wait_until", _fake_wait)
    monkeypatch.setattr(leaf, "run_main_rest_basis_round", _cancel)

    with pytest.raises(asyncio.CancelledError):
        await leaf.main_rest_basis_task_loop(sched)


@pytest.mark.asyncio
async def test_c18_3_stopped_scheduler_ends_loop(monkeypatch):
    """C18 — `_running=False` 면 남은 REST 버스트를 즉시 끊는다."""
    from src.engine import open_price_rest as leaf

    sched = _make_sched(vb_targets={_T1: _target()})
    sched._running = False
    ran: list[int] = []

    async def _fake_round(_s, *, round_no, total_rounds, kind):
        ran.append(round_no)
        return {"pending": 0}

    async def _fake_wait(target, **kw):
        return None

    monkeypatch.setattr(sched, "_wait_until", _fake_wait)
    monkeypatch.setattr(leaf, "run_main_rest_basis_round", _fake_round)

    await leaf.main_rest_basis_task_loop(sched)
    assert ran == []


# ===========================================================================
# C19 — 준비 폴링 / 빈 대상
# ===========================================================================

@pytest.mark.asyncio
async def test_c19_1_empty_targets_zero_rest_calls(rest_stub, caplog):
    """C19 — `_targets` 가 비면 REST 0콜로 지나간다(헛된 KIS 호출 0)."""
    from src.engine import open_price_rest as leaf

    _open_info(caplog)
    sched = _make_sched(vb_targets={}, ltv_targets={})

    stats = await leaf.run_main_rest_basis_round(
        sched, round_no=1, total_rounds=9, kind="fast",
    )

    assert rest_stub["calls"] == []
    assert stats["calls"] == 0 and stats["total"] == 0


@pytest.mark.asyncio
async def test_c19_2_ready_poll_timeout_is_not_silent(monkeypatch, caplog):
    """C19 — 준비 폴링 90초 초과 시 `skipped reason=no_target` 1행을 남기고 **일정 루프로 낙하**한다.

    task 는 `_boot()` 완료 직후(prepare **이후**)에 만들어지므로 비어 있는 경우는 boot
    prepare 실패(07:59 재-prepare 가 채움) 또는 장중 재시작뿐이다. 종전 서술("prepare 이전")은
    사실과 반대였다(cycle272 tester MEDIUM #1). `_wait_until(advance_if_passed=False)` `_wait_until(advance_if_passed=False)`
    는 시각이 지났으면 즉시 반환한다. 그래서 09:00:35 이후 재시작이면 본체가 곧바로 도는데
    그 시점 `_targets` 는 아직 비어 있을 수 있다(cycle264 MEDIUM #6 동형). 조용히 지나가면
    "확보 0" 과 "대상 0" 이 구별되지 않는다(cycle224 교훈).
    """
    from src.engine import open_price_rest as leaf

    _open_info(caplog)
    sched = _make_sched(vb_targets={}, ltv_targets={})
    ran: list[int] = []

    async def _fake_wait(target, **kw):
        return None

    async def _fake_round(_s, **kw):
        ran.append(1)
        return {"pending": 0}

    async def _fast_sleep(secs=0, *a, **kw):
        return None

    monkeypatch.setattr(sched, "_wait_until", _fake_wait)
    monkeypatch.setattr(leaf, "run_main_rest_basis_round", _fake_round)
    monkeypatch.setattr(asyncio, "sleep", _fast_sleep)

    await leaf.main_rest_basis_task_loop(sched)

    skipped = [ln for ln in _lines(caplog, _M_ROUND) if "reason=no_target" in ln]
    assert len(skipped) == 1, f"skipped 행이 1행이어야 한다 — 실측 {_lines(caplog, _M_ROUND)!r}"
    assert "waited_s=" in skipped[0]
    assert leaf._READY_POLL_INTERVAL_S == 2.0 and leaf._READY_POLL_MAX_S == 90.0
    # cycle272 tester MEDIUM #1 — 타임아웃은 **종결이 아니다**: 마커 1행 뒤 일정 루프로
    # 낙하해 라운드가 호출돼야 한다(07:59 재-prepare 뒤 R1 이 살아야 한다). `return` 을
    # 되살리는 뮤테이션은 여기서 죽는다.
    assert ran, "준비 폴링 타임아웃 뒤에도 일정 루프로 낙하해 라운드가 호출돼야 한다"


# ===========================================================================
# C20 — read-only
# ===========================================================================

@pytest.mark.asyncio
async def test_c20_1_ticker_prices_is_read_only(rest_stub, monkeypatch):
    """C20 — leaf 는 `scanner.ticker_prices` 를 **읽기만** 한다.

    `scanner.py` 는 8영역이다. leaf 가 그 dict 를 건드리면 접촉 0 계약이 깨진다.
    """
    from src.engine import open_price_rest as leaf
    from src.engine import scanner

    prices = {_T1: {"open_price": 79000, "current_price": 79500},
              _T2: {"open_price": 0}}
    monkeypatch.setattr(scanner, "ticker_prices", prices)
    before = copy.deepcopy(prices)

    sched = _make_sched(vb_targets={_T1: _target(), _T2: _target()})
    rest_stub["table"] = {_T1: {"stck_oprc": "80000"}, _T2: {"stck_oprc": "0"}}

    await leaf.run_main_rest_basis_round(sched, round_no=1, total_rounds=9, kind="fast")

    assert prices == before, f"ticker_prices 가 변경됐다 — before={before!r} after={prices!r}"


# ===========================================================================
# C21 — unresolved
# ===========================================================================

@pytest.mark.asyncio
async def test_c21_1_unresolved_emitted_after_last_fast_round(rest_stub, caplog):
    """C21 — 빠른 창 마지막 라운드 직후 미확정 종목마다 `[main_rest_basis_unresolved]` 1행.

    **커버리지 손실 정본**이다. 0 이 아니면 "고치려다 매수를 잃고 있다" 는 뜻이고,
    두 자릿수면 설계 전제(09:00:30 무릎 97%)가 그날 깨진 것이라 재시도 일정을 재검토한다.
    `reason` 분포가 O-1(미프린트 vs 예외)을 가른다.
    """
    from src.engine import open_price_rest as leaf

    _open_info(caplog)
    sched = _make_sched(vb_targets={_T1: _target(), _T2: _target()})
    rest_stub["table"] = {_T1: {"stck_oprc": "0"}, _T2: RuntimeError("boom")}

    await leaf.run_main_rest_basis_round(sched, round_no=9, total_rounds=9, kind="fast")

    lines = _lines(caplog, _M_UNRESOLVED)
    assert len(lines) == 2, f"실측 {lines!r}"
    reasons = {_field(ln, "ticker"): _field(ln, "reason") for ln in lines}
    assert reasons == {_T1: "rest_zero", _T2: "rest_error"}, f"실측 {reasons!r}"
    assert all("rounds=" in ln and "board=main" in ln for ln in lines)


@pytest.mark.asyncio
async def test_c21_2_unresolved_not_emitted_before_last_fast_round(rest_stub, caplog):
    """C21 — 중간 라운드에서는 계수만 하고 unresolved 를 찍지 않는다(아직 회수 중이다)."""
    from src.engine import open_price_rest as leaf

    _open_info(caplog)
    sched = _make_sched(vb_targets={_T1: _target()})
    rest_stub["table"] = {_T1: {"stck_oprc": "0"}}

    for r in (1, 5, 8):
        await leaf.run_main_rest_basis_round(sched, round_no=r, total_rounds=9, kind="fast")

    assert _lines(caplog, _M_UNRESOLVED) == []


@pytest.mark.asyncio
async def test_c21_3_unresolved_capped_once_per_strategy_ticker_per_day(rest_stub, caplog):
    """C21 — 1회/(전략,종목)/일 cap."""
    from src.engine import open_price_rest as leaf

    _open_info(caplog)
    sched = _make_sched(vb_targets={_T1: _target()})
    rest_stub["table"] = {_T1: {"stck_oprc": "0"}}

    await leaf.run_main_rest_basis_round(sched, round_no=9, total_rounds=9, kind="fast")
    await leaf.run_main_rest_basis_round(sched, round_no=9, total_rounds=9, kind="fast")

    assert len(_lines(caplog, _M_UNRESOLVED)) == 1


@pytest.mark.asyncio
async def test_c21_4_leaf_config_canary_is_value_sensitive(rest_stub, caplog):
    """C21/킬스위치 — `[main_rest_basis_config]` cap 키는 **값-민감**(`cfg|<mode>`)이다.

    장중 유일 롤백 수단인 `PUT /api/strategies/{id}/params` 는 in-memory `config.params` 를
    즉시 덮는다. 단일 키면 그날 첫 행이 cap 을 소진해 **바뀐 값을 확인할 마커가 0행**이
    된다(cycle245 R1 사각). 슬로우 라운드가 5분 주기이므로 PUT 후 5분 안에 `mode=off` 행이
    떠야 롤백이 먹혔는지 확인된다.
    """
    from src.engine import open_price_rest as leaf

    _open_info(caplog)
    sched = _make_sched(vb_targets={_T1: _target()}, ltv_targets={})
    rest_stub["table"] = {_T1: {"stck_oprc": "0"}}

    await leaf.run_main_rest_basis_round(sched, round_no=1, total_rounds=9, kind="fast")
    await leaf.run_main_rest_basis_round(sched, round_no=2, total_rounds=9, kind="fast")
    first = _lines(caplog, _M_CONFIG)
    assert len(first) == 1 and "mode=enforce" in first[0], f"실측 {first!r}"

    # 장중 PUT 롤백 모사 — 값이 바뀌면 새 행이 떠야 한다
    sched.registry.get("volatility_breakout").config.params[KEY] = "off"
    await leaf.run_main_rest_basis_round(sched, round_no=3, total_rounds=9, kind="fast")

    after = _lines(caplog, _M_CONFIG)
    assert len(after) == 2 and "mode=off" in after[1], (
        f"값-민감 cap 이 아니면 롤백 확인 채널이 죽는다 — 실측 {after!r}"
    )
    assert "emitter=leaf" in after[0] and "raw=" in after[0]


# ===========================================================================
# C22 — task lifecycle (scheduler AST)
# ===========================================================================

def _sched_tree() -> ast.Module:
    return ast.parse(_SCHEDULER_PATH.read_text(encoding="utf-8"))


def test_c22_1_task_attr_name_is_conventional():
    """C22 — task 속성명은 `_main_rest_basis_task` 다.

    `_*_task_handle` 은 cycle79 수집기에 안 잡혀 세 cancel 목록 어디에도 없는 채로
    모든 가드가 초록이었던 전례가 있다(cycle264 적대 검증 MEDIUM).
    """
    from tests.unit.ast.test_cycle264_scope_and_pins import _create_task_attrs

    created = _create_task_attrs(_sched_tree())
    assert "_main_rest_basis_task" in created, f"실측 {sorted(created)}"


@pytest.mark.parametrize("fn_name", ["stop", "start", "run_daily"])
def test_c22_2_task_registered_in_all_three_cancel_lists(fn_name):
    """C22 — `stop()` · `start()` finally · `run_daily()` finally **세 목록 전부**.

    좀비 task 는 stop→start 재진입에서 되살아나 같은 본체를 두 번 돌린다
    (= 같은 종목에 REST 이중 스윕).
    """
    from tests.unit.ast.test_cycle264_scope_and_pins import _cancel_tuple_strings

    assert "_main_rest_basis_task" in _cancel_tuple_strings(_sched_tree(), fn_name), (
        f"`TradingScheduler.{fn_name}` 취소 목록에 `_main_rest_basis_task` 누락"
    )


# ===========================================================================
# C23 / C25 — owns_board 와 스케줄러 백스톱
# ===========================================================================

def test_c23_1_owns_board_time_boundary(monkeypatch):
    """C23/C25 — `owns_board` 는 09:05:00 **배타** 경계다.

    09:04:59.999 True / 09:05:00.000 False. 경계 뮤테이션(`<` → `<=`)이 여기서 KILL 된다.
    """
    from datetime import datetime, timedelta, timezone

    from src.engine import open_price_rest as leaf

    kst = timezone(timedelta(hours=9))
    sched = _make_sched(vb_targets={_T1: _target()})
    vb = sched.registry.get("volatility_breakout")

    before = datetime(2026, 9, 11, 9, 4, 59, 999000, tzinfo=kst)
    at = datetime(2026, 9, 11, 9, 5, 0, 0, tzinfo=kst)
    assert leaf.owns_board(vb, "main", now=before) is True
    assert leaf.owns_board(vb, "main", now=at) is False


def test_c23_2_owns_board_scope_and_mode():
    """C23 — `main` 이 아니거나 `off` 면 소유하지 않는다(스케줄러가 계속 담당)."""
    from datetime import datetime, timedelta, timezone

    from src.engine import open_price_rest as leaf

    kst = timezone(timedelta(hours=9))
    now = datetime(2026, 9, 11, 9, 1, 0, tzinfo=kst)
    sched = _make_sched(vb_targets={_T1: _target()}, ltv_mode="off")
    vb = sched.registry.get("volatility_breakout")
    ltv = sched.registry.get("long_tail_volatility")

    assert leaf.owns_board(vb, "main", now=now) is True
    assert leaf.owns_board(vb, "pre_nxt", now=now) is False
    assert leaf.owns_board(vb, "post_nxt", now=now) is False
    assert leaf.owns_board(ltv, "main", now=now) is False


def test_c23_3_owns_board_exception_is_fail_open():
    """C23 — 판정 예외는 **False(fail-open)** — 스케줄러가 계속 담당한다.

    True 로 떨어지면 leaf 도 스케줄러도 아무도 확정하지 않는 구멍이 생긴다.
    """
    from datetime import datetime, timedelta, timezone

    from src.engine import open_price_rest as leaf

    kst = timezone(timedelta(hours=9))

    class _Boom:
        @property
        def config(self):
            raise RuntimeError("config 폭발")

    assert leaf.owns_board(
        _Boom(), "main", now=datetime(2026, 9, 11, 9, 1, tzinfo=kst),
    ) is False


@pytest.mark.asyncio
async def test_c23_4_confirm_main_returns_immediately_while_leaf_owns(rest_stub, monkeypatch):
    """C23 — `owns_board` True 면 `_confirm_breakout_open_prices(board="main")` 은
    두 전략을 대상에서 빼고 **WS 폴링 0초·REST 0콜**로 즉시 반환한다.

    부수 효과 = `_drain_pending_next_day_clear`(익일청산 시장가)가 **09:00:14 → 09:00:05**
    로 ~9초 앞당겨진다. 개장 직후 변동성 구간의 시장가 청산이 빨라지는 것은 슬리피지
    관점에서 유리하다(자문 §7-c).
    """
    from src.engine import open_price_rest as leaf
    from src.engine import scanner

    monkeypatch.setattr(scanner, "ticker_prices", {_T1: {"open_price": 79000}})
    monkeypatch.setattr(leaf, "owns_board", lambda *a, **kw: True)

    sched = _make_sched(vb_targets={_T1: _target()}, ltv_targets={_T1: _target()})
    rest_stub["sleeps"].clear()

    await sched._confirm_breakout_open_prices(board="main")

    assert rest_stub["calls"] == [], "leaf 가 소유 중인데 스케줄러가 REST 를 쐈다"
    assert rest_stub["sleeps"] == [], "leaf 가 소유 중인데 WS 폴링이 돌았다"
    vb = sched.registry.get("volatility_breakout")
    assert (vb._open_confirmed.get(_T1) or {}).get("main") is not True


@pytest.mark.asyncio
async def test_c25_1_scheduler_backstop_confirms_via_rest_after_handoff(rest_stub, monkeypatch):
    """C25 — 09:05:00 이후 `owns_board` False → 스케줄러 2차 REST 폴백이 **백스톱**으로 확정한다.

    같은 호출의 1차 WS 폴링은 게이트가 **전부 거부**하므로(기본 `source="ws"`) 확정 0 이고,
    2차 폴백만이 `source="rest"` 를 명시해 통과한다. 그래서 최종 기준가는 **WS 캐시 값이
    아니라 REST 값**이어야 한다 — 이 대비가 S4(`scheduler.py:1679`)의 유일한 행위 증거다.
    """
    from src.engine import open_price_rest as leaf
    from src.engine import scanner

    monkeypatch.setattr(scanner, "ticker_prices", {_T1: {"open_price": 79000}})
    monkeypatch.setattr(leaf, "owns_board", lambda *a, **kw: False)

    sched = _make_sched(vb_targets={_T1: _target(500)}, ltv_targets={})
    rest_stub["table"] = {_T1: {"stck_oprc": "80000"}}

    await sched._confirm_breakout_open_prices(board="main", max_wait_s=0.0)

    vb = sched.registry.get("volatility_breakout")
    board = (vb._targets[_T1].get("boards") or {}).get("main")
    assert board is not None, "백스톱이 확정하지 못했다 — 09:35 이후 목표가 구멍"
    assert board["open_price"] == 80000, (
        f"WS 캐시 값(79000)이 기준가가 됐다 — 게이트를 뚫었다. 실측 {board!r}"
    )
