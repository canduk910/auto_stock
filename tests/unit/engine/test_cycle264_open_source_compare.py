"""cycle264 — `[open_source_compare]`(C2) + `[breakout_open_confirm]` 표시 버그(C3).

**행위 변경 0.** 이 파일이 잠그는 것은 관측 두 개뿐이다.

## C2 — 09:05 3자 대조 shadow

그날 목표가를 만든 시가(`strategy._targets[t]["boards"]["main"]["open_price"]`)와
같은 시각 KRX REST 시가(`fetch_stock_detail(t)["stck_oprc"]`)를 나란히 남긴다.
익일 오프라인에서 `stock_master_daily` KRX 시가까지 합쳐 3자 대조하면 카드 ①의
미검증 전제가 한 번에 닫힌다.

- **왜 09:05 인가** — KRX 시가는 프린트되면 하루 종일 불변이라 언제 읽어도 같다.
  09:00~09:01:30 에 140건을 쏘면 전역 20건/초 한도를 **매수 주문과 다툰다**.
  09:05 는 공짜다.
- **throttle 5건/초** — 스캔·폴 루프와 경합 금지.
- **read-only** — `target_if_rest` 는 `rest_oprc + board["target_offset"]` **산술**이다.
  `on_open_price_confirmed(ticker, rest_oprc)` 로 계산하면 그 순간 `_targets` 가
  바뀌어 **매매 행위가 바뀐다**(C4 위반). 이 파일이 그것을 잰다.

## C3 — `[breakout_open_confirm]` 은 운영자와 조사자를 정반대로 오도했다

`_emit_breakout_open_confirm` 이 `_open_confirmed` 를 직접 세지 않고
`get_targets_status()` 를 거치는데, 그 함수는 `session_tracker.active ∩
tradable_boards` 로 보드를 가린다(`volatility_breakout.py:708-719`). 09:00:05~
09:00:2x 에는 세션 트래커가 30초 주기 stale 캐시라 `active={PRE_NXT}` 이고 VB 의
`tradable_boards=["main"]` 이라 **교집합 ∅** → `open_price: 0` 으로 덮인다.
그래서 같은 순간 비필터 로그가 "VB 51/65종목" 인데 마커는 `confirmed=0 empty=65`
였고, 그 위에 조사 하나가 틀린 인과를 세웠다.

시정 = **현행 필드를 남기고** `truth_confirmed`/`truth_total` 을 **추가**한다
(하위 호환 — 과거 로그와의 대조가 끊기면 안 된다).

## 구현 계약 (이름 정본)

관측 본체는 leaf `src/engine/open_price_observe.py` 에 산다 — `scheduler.py` 의 실제
강제 상한이 **3,900L**(cycle257 영구 가드)이라 본체를 거기 두면 3,979L 로 붉어진다.
cycle233(`account_risk_watcher`)·cycle259(`log_metrics_collector`) 위임 패턴 답습.

- `open_price_observe.TIME_OPEN_SOURCE_COMPARE = time(9, 5, 30)`
  (09:05 **정각**은 `_swing_buy_poll_loop` 매수 폴링 창 개시와 겹친다 → 30초 오프셋)
- `open_price_observe._OPEN_SOURCE_COMPARE_MAX_PER_SEC = 5`
- `open_price_observe._open_source_compare_cap` — `KstDailyEmitCap`((strategy_id, ticker))
- `open_price_observe.reset_open_source_compare_cap()`
- `open_price_observe.run_open_source_compare_once(sched)` — 본체(async, never-raise)
- `open_price_observe.open_source_compare_task_loop(sched)` — 대기 → 준비확인 → 본체 1회
- `open_price_observe.count_board_confirmed(strategy, board)` — C3 `truth_*` 산출
- `open_price_observe.mark_confirmed_via_rest/was_confirmed_via_rest` — `used_src` 라벨
- `TradingScheduler._run_open_source_compare_once()` — 얇은 위임(테스트·운영 단일 seam)
- `TradingScheduler._open_source_compare_task` — task 핸들(관례 `_*_task`,
  stop()/start() finally/run_daily() finally **세 곳** cancel 등재 의무)
"""

from __future__ import annotations

import asyncio
import copy
import logging
from datetime import time
from pathlib import Path
from unittest.mock import patch

import pytest
from freezegun import freeze_time

pytestmark = pytest.mark.unit

_LOGGER_NAME = "src.engine.scheduler"
# cycle264 적대 검증 HIGH 처리 — 09:05 대조 본체는 leaf 모듈로 이관됐다.
# 근거: `scheduler.py` 실제 상한은 계약서의 4,000L 이 아니라 cycle257 이 내린
# **3,900L** 이고, 본체를 scheduler 에 두면 3,979L 로 그 영구 가드가 붉어진다.
_LOGGER_OBSERVE = "src.engine.open_price_observe"
_LOGGER_NAMES = (_LOGGER_NAME, _LOGGER_OBSERVE)
_MARK_COMPARE = "[open_source_compare] "
_MARK_CONFIRM = "[breakout_open_confirm] "

_SCHEDULER_PATH = Path(__file__).resolve().parents[3] / "src" / "engine" / "scheduler.py"
_OBSERVE_PATH = (
    Path(__file__).resolve().parents[3] / "src" / "engine" / "open_price_observe.py"
)


# ---------------------------------------------------------------------------
# 공통 픽스처
# ---------------------------------------------------------------------------

def _lines(caplog, marker: str) -> list[str]:
    """로거명 + INFO 이상 + prefix 3중 한정 (CI 루트 로거 DEBUG 내성)."""
    return [
        r.getMessage()
        for r in caplog.records
        if r.name in _LOGGER_NAMES
        and r.levelno >= logging.INFO
        and r.getMessage().startswith(marker)
    ]


def _set_info(caplog) -> None:
    """scheduler + leaf 두 로거를 INFO 로 연다(마커가 두 모듈에 나뉘어 산다)."""
    for name in _LOGGER_NAMES:
        caplog.set_level(logging.INFO, logger=name)


def _field(line: str, key: str) -> str:
    token = f"{key}="
    idx = line.index(f" {token}") + 1
    rest = line[idx + len(token):]
    return rest.split(" ")[0]


def _reset_compare_cap() -> None:
    from src.engine import open_price_observe as obs_mod

    fn = getattr(obs_mod, "reset_open_source_compare_cap", None)
    if callable(fn):
        fn()


def _board(open_price: int, offset: int) -> dict:
    return {
        "open_price": open_price,
        "target_price": open_price + offset,
        "target_offset": offset,
    }


def _make_sched(*, vb_targets: dict | None = None, ltv_targets: dict | None = None,
                vb_enabled: bool = True, ltv_enabled: bool = True):
    """VB/LTV 가 등록된 최소 TradingScheduler (기존 scheduler 테스트 패턴 답습)."""
    from src.engine.scheduler import TradingScheduler
    from src.engine.strategy_base import StrategyConfig
    from src.engine.strategy_registry import StrategyRegistry
    from src.engine.strategies.volatility_breakout import VolatilityBreakoutStrategy
    from src.engine.strategies.long_tail_volatility import LongTailVolatilityStrategy

    with patch("src.engine.scheduler.token_manager"), \
         patch("src.engine.scheduler.kis_ws"), \
         patch("src.engine.scheduler.kis_ws_pool"):
        sched = TradingScheduler.__new__(TradingScheduler)
        sched.registry = StrategyRegistry()
        sched._pending_next_day_clear = set()
        sched._running = True
        sched._phase = "main_trading"

        vb = VolatilityBreakoutStrategy(StrategyConfig(
            strategy_id="volatility_breakout", name="변동성 돌파",
            enabled=vb_enabled, weight=0.3,
        ))
        for t, info in (vb_targets or {}).items():
            vb._targets[t] = info
            vb._open_confirmed[t] = {
                b: True for b, bi in (info.get("boards") or {}).items()
                if bi.get("open_price", 0) > 0
            }
        sched.registry.register(vb)

        ltv = LongTailVolatilityStrategy(StrategyConfig(
            strategy_id="long_tail_volatility", name="롱테일 변동성 돌파",
            enabled=ltv_enabled, weight=0.3,
        ))
        for t, info in (ltv_targets or {}).items():
            ltv._targets[t] = info
            ltv._open_confirmed[t] = {
                b: True for b, bi in (info.get("boards") or {}).items()
                if bi.get("open_price", 0) > 0
            }
        sched.registry.register(ltv)

        return sched


def _target(open_price: int, offset: int, *, extra_boards: dict | None = None) -> dict:
    boards = {"main": _board(open_price, offset)}
    boards.update(extra_boards or {})
    return {
        "k": 0.5,
        "prev_range": 1000,
        "target_offset_base": offset,
        "target_offset": offset,
        "target_price": open_price + offset,
        "open_price": open_price,
        "boards": boards,
    }


@pytest.fixture(autouse=True)
def _clean_cap():
    _reset_compare_cap()
    yield
    _reset_compare_cap()


@pytest.fixture
def rest_stub(monkeypatch):
    """`fetch_stock_detail` 스텁.

    `_confirm_breakout_open_prices` 선례처럼 함수 안 지연 import 를 쓰면 원본
    모듈 패치로 충분하지만, 모듈 최상단 import 로 구현될 수도 있으므로 양쪽을
    모두 덮는다(구현 자유도 보존).

    `order` = REST 호출과 `asyncio.sleep` 을 **한 리스트에 시간순**으로 담는
    프로브(throttle 검증용).
    """
    from src.api import condition as cond
    from src.engine import scheduler as sched_mod

    calls: list[str] = []
    order: list[tuple[str, object]] = []
    table: dict[str, object] = {}

    async def _fake(ticker: str) -> dict:
        calls.append(ticker)
        order.append(("rest", ticker))
        value = table.get(ticker, {"stck_oprc": "0"})
        if isinstance(value, Exception):
            raise value
        return value  # type: ignore[return-value]

    monkeypatch.setattr(cond, "fetch_stock_detail", _fake)
    if hasattr(sched_mod, "fetch_stock_detail"):
        monkeypatch.setattr(sched_mod, "fetch_stock_detail", _fake)
    return type("RestStub", (), {"calls": calls, "order": order, "table": table})()


@pytest.fixture
def sleep_spy(monkeypatch):
    """`asyncio.sleep` 스파이 — 실제 대기 없이 호출 순서/총량만 기록."""
    events: list[tuple[str, float]] = []
    real_sleep = asyncio.sleep

    async def _fake(secs=0, *a, **kw):
        events.append(("sleep", float(secs or 0)))
        return await real_sleep(0)

    monkeypatch.setattr(asyncio, "sleep", _fake)
    return events


# ===========================================================================
# C2 — 09:05 발화 계약
# ===========================================================================

def test_c2_schedule_constant_is_0905_30():
    """C2 — 09:05**:30**.

    - 09:00~09:01:30 은 cycle262 진입 보류 창 + 매수 주문 구간이라 REST 100~140건을
      쏘면 전역 20건/초 한도를 매수와 다툰다.
    - 09:05:00 **정각**은 `_swing_buy_poll_loop` 의 `BUY_WINDOW_START` 와 겹친다
      (donchian/kojiro 매수 평가 폴링이 정각에 깨어난다). 실피해는 작지만 C2 계약
      문언이 "스캔·폴 루프와 경합 금지" 이므로 폴 정각을 피한다(적대 검증 LOW #7).
    - KRX 시가는 프린트되면 종일 불변이라 30초 늦춰도 관측 가치 손실은 0 이다.
    """
    from src.engine import open_price_observe as obs_mod

    assert getattr(obs_mod, "TIME_OPEN_SOURCE_COMPARE", None) == time(9, 5, 30), (
        "`TIME_OPEN_SOURCE_COMPARE = time(9, 5, 30)` 계약"
    )


@pytest.mark.asyncio
async def test_c2_task_waits_until_0905_then_runs_once(monkeypatch):
    """C2 — task 는 09:05:30 까지 기다렸다가 본체를 **정확히 1회** 부른다.

    ⚠️ `advance_if_passed=True` 금지 — 09:06 재시작이면 내일까지 기다려
    그날의 관측이 통째로 사라진다(KRX 시가는 하루 종일 불변이므로 늦은 시작은
    즉시 실행이 정답이다).
    """
    from src.engine import open_price_observe as obs_mod

    # 준비 상태(= main 보드 시가 확정)가 있어야 본체로 넘어간다 — 아래 별도 테스트 참조
    sched = _make_sched(vb_targets={"000720": _target(111600, 2000)})

    waited: list[tuple] = []
    ran: list[int] = []

    async def _fake_wait(target, **kw):
        waited.append((target, kw))

    async def _fake_once(*a, **kw):
        ran.append(1)

    monkeypatch.setattr(sched, "_wait_until", _fake_wait)
    monkeypatch.setattr(sched, "_run_open_source_compare_once", _fake_once)

    await obs_mod.open_source_compare_task_loop(sched)

    assert [w[0] for w in waited] == [obs_mod.TIME_OPEN_SOURCE_COMPARE], (
        f"09:05:30 대기가 없다. 실측={waited!r}"
    )
    assert not waited[0][1].get("advance_if_passed"), (
        "advance_if_passed=True 면 09:06 재시작이 그날 관측을 통째로 버린다"
    )
    assert ran == [1], f"본체는 정확히 1회 — 실측 {len(ran)}회"


@pytest.mark.asyncio
async def test_c2_task_waits_for_targets_then_runs(monkeypatch):
    """C2 — 09:05:30 도달 시 `main` 시가가 아직 0 이면 **기다렸다가** 본체를 부른다.

    적대 검증 MEDIUM #6: task 는 `_boot()` 직후(시가 확정 **이전**)에 생성되고
    `_wait_until(advance_if_passed=False)` 는 시각이 지났으면 즉시 반환한다. 그래서
    09:05:30 이후 재시작(배포·크래시 복구)에서는 본체가 곧바로 도는데 그 시점
    `_targets[...]['boards']['main']['open_price']` 는 아직 0 이다(확정은
    `scan_stocks()` 뒤 `_confirm_breakout_open_prices` 에서 일어난다) ⇒ 전 종목
    skip → 그날 0행. `advance_if_passed=False` 로 막으려던 결과가 배치 때문에
    그대로 발생한다.
    """
    from src.engine import open_price_observe as obs_mod

    sched = _make_sched(vb_targets={"000720": _target(0, 2000)})   # 미확정 상태로 시작
    vb = sched.registry.get("volatility_breakout")
    ran: list[int] = []

    async def _fake_wait(*a, **kw):
        return None

    async def _fake_once():
        ran.append(1)

    ticks: list[int] = []
    real_sleep = asyncio.sleep

    async def _fake_sleep(secs=0, *a, **kw):
        ticks.append(len(ticks))
        if len(ticks) == 2:      # 2회 폴링 뒤 시가 확정이 도착한 상황
            vb._targets["000720"]["boards"]["main"]["open_price"] = 111600
        return await real_sleep(0)

    monkeypatch.setattr(sched, "_wait_until", _fake_wait)
    monkeypatch.setattr(sched, "_run_open_source_compare_once", _fake_once)
    monkeypatch.setattr(asyncio, "sleep", _fake_sleep)

    await obs_mod.open_source_compare_task_loop(sched)
    assert ran == [1], f"확정이 늦게 도착했는데 본체가 안 돌았다(그날 0행). 실측={ran!r}"
    assert len(ticks) >= 2, "준비 상태 폴링이 없다"


@pytest.mark.asyncio
async def test_c2_task_logs_reason_when_targets_never_confirm(monkeypatch, caplog):
    """C2 — 준비 대기 타임아웃은 **침묵하지 않는다**(cycle224 교훈).

    행이 0개인 날과 "확정이 끝내 안 왔다" 를 구별할 수 있어야 판독이 성립한다.
    """
    from src.engine import open_price_observe as obs_mod

    _set_info(caplog)
    sched = _make_sched(vb_targets={"000720": _target(0, 2000)})
    ran: list[int] = []

    async def _fake_wait(*a, **kw):
        return None

    async def _fake_once():
        ran.append(1)

    real_sleep = asyncio.sleep

    async def _fake_sleep(secs=0, *a, **kw):
        return await real_sleep(0)

    monkeypatch.setattr(sched, "_wait_until", _fake_wait)
    monkeypatch.setattr(sched, "_run_open_source_compare_once", _fake_once)
    monkeypatch.setattr(asyncio, "sleep", _fake_sleep)

    await obs_mod.open_source_compare_task_loop(sched)

    assert ran == [], "미확정인데 본체를 돌렸다"
    lines = _lines(caplog, _MARK_COMPARE)
    assert len(lines) == 1 and "reason=no_confirmed_target" in lines[0], (
        f"준비 타임아웃이 무음이다 — 그날 0행의 이유를 남겨야 한다. 실측={lines!r}"
    )


@pytest.mark.asyncio
async def test_c2_task_stops_when_scheduler_stops(monkeypatch):
    """C2 — `_running=False` 면 준비 폴링도 본체 호출도 하지 않는다(좀비 차단)."""
    from src.engine import open_price_observe as obs_mod

    sched = _make_sched(vb_targets={"000720": _target(111600, 2000)})
    sched._running = False
    ran: list[int] = []

    async def _fake_wait(*a, **kw):
        return None

    async def _fake_once():
        ran.append(1)

    monkeypatch.setattr(sched, "_wait_until", _fake_wait)
    monkeypatch.setattr(sched, "_run_open_source_compare_once", _fake_once)
    await obs_mod.open_source_compare_task_loop(sched)
    assert ran == [], "정지 상태에서 본체가 돌았다"


@pytest.mark.asyncio
async def test_c2_body_aborts_midway_when_scheduler_stops(rest_stub, sleep_spy, caplog):
    """C2 — 종목 루프 도중 `stop()` 이 불리면 남은 REST 버스트를 즉시 끊는다.

    100~140 종목 × 0.2초 = 최대 ~28초 버스트다. 그 도중 정지 요청이 들어와도
    계속 쏘면 `stop()` 이 사실상 무력해진다(적대 검증 MEDIUM).
    """
    _set_info(caplog)
    tickers = [f"{i:06d}" for i in range(1, 9)]
    sched = _make_sched(vb_targets={t: _target(10000, 100) for t in tickers})
    for t in tickers:
        rest_stub.table[t] = {"stck_oprc": "10500"}

    async def _watch():          # 2건 처리 뒤 정지 요청
        while len(rest_stub.calls) < 2:
            await asyncio.sleep(0)
        sched._running = False

    await asyncio.gather(sched._run_open_source_compare_once(), _watch())

    assert len(rest_stub.calls) < len(tickers), (
        f"정지 요청 뒤에도 전 종목을 다 쐈다: {rest_stub.calls!r}"
    )


def test_c2_task_is_created_in_start():
    """C2 — `start()` 가 백그라운드 task 를 만든다(메인 루프는 09:30 까지 블록된다)."""
    import ast

    src = _SCHEDULER_PATH.read_text(encoding="utf-8")
    tree = ast.parse(src)
    start = next(
        n for n in ast.walk(tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == "start"
    )
    seg = ast.get_source_segment(src, start) or ""
    assert "open_source_compare_task_loop(self)" in seg, (
        "`start()` 에서 `asyncio.create_task(open_price_observe."
        "open_source_compare_task_loop(self))` 가 필요하다 — 메인 루프는 09:00:05 "
        "확정 뒤 곧장 09:30 까지 `_wait_until` 로 블록되므로 인라인 호출은 09:05:30 "
        "에 발화할 수 없다"
    )
    assert "self._open_source_compare_task = " in seg, (
        "task 핸들 속성명은 관례 `_*_task` 다 — `_*_task_handle` 은 cycle79 가드의 "
        "수집 패턴(`endswith('_task')`)에 잡히지 않아 cancel 누락이 조용히 지나간다"
    )


# ===========================================================================
# C2 — 로그 내용 계약
# ===========================================================================

@pytest.mark.asyncio
async def test_c2_emits_one_line_per_ticker_with_all_fields(rest_stub, sleep_spy, caplog):
    """C2 — VB 2종목 → 2행 + 8필드. `delta_bp` 산식 = (rest-used)/used*10000."""
    _set_info(caplog)
    sched = _make_sched(vb_targets={
        "000720": _target(111600, 2000),
        "001450": _target(52900, 700),
    })
    rest_stub.table["000720"] = {"stck_oprc": "115000"}
    rest_stub.table["001450"] = {"stck_oprc": "52000"}

    await sched._run_open_source_compare_once()

    lines = sorted(_lines(caplog, _MARK_COMPARE))
    assert len(lines) == 2, f"종목 2개 → 2행. 실측={lines!r}"

    by_ticker = {_field(l, "ticker"): l for l in lines}
    a = by_ticker["000720"]
    assert _field(a, "strategy") == "volatility_breakout"
    assert _field(a, "board") == "main"
    assert _field(a, "used_open") == "111600"
    assert _field(a, "rest_oprc") == "115000"
    assert _field(a, "delta_bp") == f"{(115000 - 111600) / 111600 * 10000:.1f}"
    assert _field(a, "target_used") == "113600"      # 111600 + 2000
    assert _field(a, "target_if_rest") == "117000"   # 115000 + 2000
    assert _field(a, "used_src") == "ws"             # REST 폴백 표시가 없으면 ws
    assert _field(a, "reason") == "ok"

    b = by_ticker["001450"]
    assert _field(b, "delta_bp") == f"{(52000 - 52900) / 52900 * 10000:.1f}", (
        "하향 델타는 음수로 남아야 한다(부호 소실 금지)"
    )
    assert _field(b, "target_if_rest") == "52700"


@pytest.mark.asyncio
async def test_c2_used_open_comes_from_targets_not_scanner_cache(
    rest_stub, sleep_spy, caplog, monkeypatch,
):
    """C2 — `used_open` 은 **그날 목표가를 만든 값**(`_targets`)이다.

    `scanner.ticker_prices["open_price"]` 는 마지막 틱의 값이라 09:05 시점에는
    이미 다른 수일 수 있다. 그 값을 쓰면 이 관측은 "목표가가 무엇을 썼나" 가
    아니라 "지금 캐시가 무엇인가" 를 재게 된다.
    """
    from src.engine import scanner

    _set_info(caplog)
    monkeypatch.setattr(scanner, "ticker_prices", {
        "000720": {"current_price": 120000, "open_price": 999999, "change_rate": 1.0},
    })
    sched = _make_sched(vb_targets={"000720": _target(111600, 2000)})
    rest_stub.table["000720"] = {"stck_oprc": "115000"}

    await sched._run_open_source_compare_once()

    lines = _lines(caplog, _MARK_COMPARE)
    assert len(lines) == 1
    assert _field(lines[0], "used_open") == "111600", (
        f"`_targets[...]['boards']['main']['open_price']` 가 정본이다: {lines[0]!r}"
    )


@pytest.mark.asyncio
async def test_c2_is_read_only_targets_unchanged(rest_stub, sleep_spy, caplog):
    """C2/C4 — 관측이 `_targets`/`_open_confirmed` 를 **한 글자도** 바꾸지 않는다.

    `target_if_rest` 를 `on_open_price_confirmed(t, rest_oprc)` 로 구하면 그 순간
    보드 목표가가 REST 시가 기준으로 갈아끼워진다 = 매매 행위 변경 = C4 위반.
    """
    _set_info(caplog)
    sched = _make_sched(vb_targets={"000720": _target(111600, 2000)},
                        ltv_targets={"000880": _target(123000, 1500)})
    rest_stub.table["000720"] = {"stck_oprc": "115000"}
    rest_stub.table["000880"] = {"stck_oprc": "127000"}

    vb = sched.registry.get("volatility_breakout")
    ltv = sched.registry.get("long_tail_volatility")
    before = (
        copy.deepcopy(vb._targets), copy.deepcopy(vb._open_confirmed),
        copy.deepcopy(ltv._targets), copy.deepcopy(ltv._open_confirmed),
    )

    await sched._run_open_source_compare_once()

    assert len(_lines(caplog, _MARK_COMPARE)) == 2, "관측 자체는 나와야 한다"
    after = (
        vb._targets, vb._open_confirmed, ltv._targets, ltv._open_confirmed,
    )
    assert before == after, (
        "shadow 관측이 전략 상태를 변경했다 — 이 사이클의 제1 계약(행위 변경 0) 위반"
    )


@pytest.mark.asyncio
async def test_c2_cap_one_per_ticker_strategy_per_day(rest_stub, sleep_spy, caplog):
    """C2 — 1회/(ticker,strategy)/일. 두 번째 호출은 REST 조차 쏘지 않는다."""
    _set_info(caplog)
    sched = _make_sched(vb_targets={"000720": _target(111600, 2000)})
    rest_stub.table["000720"] = {"stck_oprc": "115000"}

    await sched._run_open_source_compare_once()
    first_calls = len(rest_stub.calls)
    await sched._run_open_source_compare_once()

    assert len(_lines(caplog, _MARK_COMPARE)) == 1, "재호출이 중복 행을 남겼다"
    assert len(rest_stub.calls) == first_calls, (
        "cap 판정이 REST 호출 **뒤**에 있다 — 재호출이 KIS 한도를 헛되이 태운다"
    )


@pytest.mark.asyncio
async def test_c2_same_ticker_two_strategies_both_emit(rest_stub, sleep_spy, caplog):
    """C2 — cap key 는 (strategy, ticker) 다. 같은 종목을 두 전략이 잡으면 2행."""
    _set_info(caplog)
    sched = _make_sched(
        vb_targets={"000720": _target(111600, 2000)},
        ltv_targets={"000720": _target(111600, 3000)},
    )
    rest_stub.table["000720"] = {"stck_oprc": "115000"}

    await sched._run_open_source_compare_once()

    lines = _lines(caplog, _MARK_COMPARE)
    assert {_field(l, "strategy") for l in lines} == {
        "volatility_breakout", "long_tail_volatility",
    }, f"전략별 1행씩 = 2행이어야 한다. 실측={lines!r}"


@pytest.mark.asyncio
async def test_c2_cap_resets_across_kst_day(rest_stub, sleep_spy, caplog):
    """C2 — cap 은 KST 일자 경계에서 자기 리셋(`KstDailyEmitCap`)."""
    _set_info(caplog)
    sched = _make_sched(vb_targets={"000720": _target(111600, 2000)})
    rest_stub.table["000720"] = {"stck_oprc": "115000"}

    with freeze_time("2026-09-07 09:05:00+09:00"):
        await sched._run_open_source_compare_once()
        await sched._run_open_source_compare_once()
    assert len(_lines(caplog, _MARK_COMPARE)) == 1

    with freeze_time("2026-09-08 09:05:00+09:00"):
        await sched._run_open_source_compare_once()
    assert len(_lines(caplog, _MARK_COMPARE)) == 2


# ===========================================================================
# C2 — throttle / graceful / 스코프
# ===========================================================================

@pytest.mark.asyncio
async def test_c2_throttle_max_5_rest_per_second(rest_stub, caplog, monkeypatch):
    """C2 — REST 는 **5건/초** 상한이다. 스캔·폴 루프와 경합하면 안 된다."""
    from src.engine import open_price_observe as obs_mod

    assert getattr(obs_mod, "_OPEN_SOURCE_COMPARE_MAX_PER_SEC", None) == 5, (
        "throttle 상수 `_OPEN_SOURCE_COMPARE_MAX_PER_SEC = 5` 계약"
    )

    _set_info(caplog)
    tickers = [f"{i:06d}" for i in range(1, 13)]   # 12 종목
    sched = _make_sched(vb_targets={t: _target(10000 + i, 100) for i, t in enumerate(tickers)})
    for t in tickers:
        rest_stub.table[t] = {"stck_oprc": "10500"}

    # REST 호출과 sleep 을 **한 리스트에 시간순**으로 담아 상한을 잰다
    real_sleep = asyncio.sleep

    async def _sleep(secs=0, *a, **kw):
        rest_stub.order.append(("sleep", float(secs or 0)))
        return await real_sleep(0)

    monkeypatch.setattr(asyncio, "sleep", _sleep)
    await sched._run_open_source_compare_once()

    assert len(_lines(caplog, _MARK_COMPARE)) == 12

    # 어떤 sleep 사이에도 REST 가 5건을 넘지 않는다
    run = worst = 0
    for kind, _ in rest_stub.order:
        if kind == "rest":
            run += 1
            worst = max(worst, run)
        else:
            run = 0
    assert worst <= 5, (
        f"연속 REST {worst}건 — 5건/초 상한 위반 (order={rest_stub.order!r})"
    )

    # 총 대기 >= (n-1)/5 초 — 12건이면 2.2초
    slept = sum(v for kind, v in rest_stub.order if kind == "sleep")
    assert slept >= (12 - 1) / 5, (
        f"총 sleep {slept}s < 2.2s — 12건을 5건/초로 쏘려면 최소 2.2초가 든다"
    )


@pytest.mark.asyncio
async def test_c2_rest_failure_is_per_ticker_graceful(rest_stub, sleep_spy, caplog):
    """C2 — 한 종목 REST 실패가 나머지를 죽이지 않는다 + 실패도 이유가 붙어 남는다."""
    _set_info(caplog)
    sched = _make_sched(vb_targets={
        "000720": _target(111600, 2000),
        "000880": _target(123000, 1500),
        "001450": _target(52900, 700),
    })
    rest_stub.table["000720"] = RuntimeError("KIS 5xx")
    rest_stub.table["000880"] = {"stck_oprc": "127000"}
    rest_stub.table["001450"] = {"stck_oprc": "52000"}

    await sched._run_open_source_compare_once()

    lines = _lines(caplog, _MARK_COMPARE)
    by_ticker = {_field(l, "ticker"): l for l in lines}
    assert set(by_ticker) == {"000720", "000880", "001450"}, (
        f"실패 종목도 이유가 붙은 1행으로 남는다(무음 금지). 실측={lines!r}"
    )
    assert _field(by_ticker["000720"], "reason") == "rest_error"
    assert _field(by_ticker["000880"], "reason") == "ok"
    assert _field(by_ticker["001450"], "reason") == "ok", (
        "한 종목의 REST 실패가 뒤따르는 종목을 죽였다"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "rest_value,expected_reason",
    [
        ({"stck_oprc": "0"}, "rest_zero"),
        ({"stck_oprc": ""}, "rest_zero"),
        ({}, "rest_zero"),
        ({"stck_oprc": "abc"}, "rest_error"),
    ],
)
async def test_c2_rest_gives_nothing_still_leaves_a_row(
    rest_value, expected_reason, rest_stub, sleep_spy, caplog,
):
    """C2 — REST 시가가 0/부재/비숫자여도 **행을 남긴다**(`reason` 태그).

    적대 검증 MEDIUM #11: 침묵하면 "REST 가 전부 일치했다" 와 "REST 가 N 종목에서
    아무것도 못 줬다" 가 구별되지 않는다. `logger.debug` 단독은 `_DbLogHandler`
    (INFO 컷)를 못 넘어 `system_logs` 에 도달하지 않는다(cycle237 C237-L2-1).
    그리고 이 결측은 **무작위가 아니다** — 09:05 에 아직 체결이 없어
    `stck_oprc="0"` 인 저유동 종목이야말로 오염된 프리장 `[7]` 을 쓰고 있을
    확률이 가장 높은 코호트다. 침묵하면 월요일 판독이 그 방향으로 편향된다.
    """
    _set_info(caplog)
    sched = _make_sched(vb_targets={"000720": _target(111600, 2000)})
    rest_stub.table["000720"] = rest_value

    await sched._run_open_source_compare_once()
    lines = _lines(caplog, _MARK_COMPARE)
    assert len(lines) == 1, f"결측도 1행이다(무음 금지). 실측={lines!r}"
    line = lines[0]
    assert _field(line, "reason") == expected_reason, line
    # 미측정임을 0 으로 표시하고 `reason` 이 그 0 을 "값" 이 아니라고 말한다
    assert _field(line, "rest_oprc") == "0"
    assert _field(line, "delta_bp") == "0.0"
    assert _field(line, "target_if_rest") == "0"
    assert _field(line, "used_open") == "111600", "used_open 은 여전히 진실이다"


@pytest.mark.asyncio
async def test_c2_skips_unconfirmed_ticker_without_rest_call(rest_stub, sleep_spy, caplog):
    """C2 — `used_open <= 0`(미확정)은 대조 대상이 아니다. REST 도 쏘지 않는다.

    커버리지(몇 종목이 미확정인가)는 `[breakout_open_confirm] truth_*` 가 센다.
    """
    _set_info(caplog)
    sched = _make_sched(vb_targets={
        "000720": _target(0, 2000),          # boards.main.open_price = 0
        "000880": {"k": 0.5, "boards": {}},  # boards 자체가 없음
        "001450": _target(52900, 700),
    })
    rest_stub.table["001450"] = {"stck_oprc": "52000"}

    await sched._run_open_source_compare_once()

    assert {_field(l, "ticker") for l in _lines(caplog, _MARK_COMPARE)} == {"001450"}
    assert rest_stub.calls == ["001450"], (
        f"미확정 종목에 REST 를 쐈다 — 09:05 한도를 헛되이 태운다: {rest_stub.calls!r}"
    )


@pytest.mark.asyncio
async def test_c2_scope_is_vb_ltv_main_board_only(rest_stub, sleep_spy, caplog):
    """C2 — 대상은 VB·LTV 의 `main` 보드뿐. 다른 보드/전략은 건드리지 않는다."""
    _set_info(caplog)
    sched = _make_sched(vb_targets={
        # main 없음 + pre_nxt 만 확정 → 대조 대상 아님
        "000720": {"k": 0.5, "boards": {"pre_nxt": _board(111600, 2000)}},
        "001450": _target(52900, 700),
    })
    rest_stub.table["000720"] = {"stck_oprc": "115000"}
    rest_stub.table["001450"] = {"stck_oprc": "52000"}

    await sched._run_open_source_compare_once()

    lines = _lines(caplog, _MARK_COMPARE)
    assert {_field(l, "ticker") for l in lines} == {"001450"}
    assert all(_field(l, "board") == "main" for l in lines)


@pytest.mark.asyncio
async def test_c2_disabled_strategy_is_skipped(rest_stub, sleep_spy, caplog):
    """C2 — `enabled=False` 전략은 대상이 아니다."""
    _set_info(caplog)
    sched = _make_sched(
        vb_targets={"000720": _target(111600, 2000)}, vb_enabled=False,
        ltv_targets={"000880": _target(123000, 1500)},
    )
    rest_stub.table["000720"] = {"stck_oprc": "115000"}
    rest_stub.table["000880"] = {"stck_oprc": "127000"}

    await sched._run_open_source_compare_once()
    assert {_field(l, "strategy") for l in _lines(caplog, _MARK_COMPARE)} == {
        "long_tail_volatility",
    }


@pytest.mark.asyncio
async def test_c2_never_raises_even_if_everything_explodes(rest_stub, sleep_spy, monkeypatch):
    """C5 — 본체는 never-raise. 09:05 백그라운드 task 가 죽어도 매매는 무관해야 한다."""
    from src.engine import open_price_observe as obs_mod

    sched = _make_sched(vb_targets={"000720": _target(111600, 2000)})
    rest_stub.table["000720"] = {"stck_oprc": "115000"}

    class _Boom:
        def __getattr__(self, _n):
            def _b(*_a, **_kw):
                raise RuntimeError("boom")
            return _b

    monkeypatch.setattr(obs_mod, "logger", _Boom())
    await sched._run_open_source_compare_once()   # 예외가 새면 실패

    monkeypatch.setattr(sched, "registry", _Boom())
    await sched._run_open_source_compare_once()


def test_c2_body_never_writes_db():
    """C2 — 09:05 관측 leaf 는 `logger` 만 쓴다(`write_log` 금지 — 20:10 리포트가 파싱한다)."""
    import ast

    src = _OBSERVE_PATH.read_text(encoding="utf-8")
    tree = ast.parse(src)
    called = {
        c.func.id for c in ast.walk(tree)
        if isinstance(c, ast.Call) and isinstance(c.func, ast.Name)
    } | {
        c.func.attr for c in ast.walk(tree)
        if isinstance(c, ast.Call) and isinstance(c.func, ast.Attribute)
    }
    assert "write_log" not in called, "관측은 logger 로만 남긴다(leaf 전수)"
    node = next(
        (n for n in ast.walk(tree)
         if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
         and n.name == "run_open_source_compare_once"),
        None,
    )
    assert node is not None, "`run_open_source_compare_once` 미구현"


def test_c2_scheduler_keeps_thin_delegate_seam():
    """C2 — scheduler 는 얇은 위임 메서드만 남긴다(테스트·운영 단일 seam 보존).

    본체를 leaf 로 밀었더라도 `sched._run_open_source_compare_once()` 호출 지점은
    유지된다 — task 루프도 그 seam 을 거치므로 monkeypatch 한 곳으로 전체를 잡는다.
    """
    import ast

    src = _SCHEDULER_PATH.read_text(encoding="utf-8")
    tree = ast.parse(src)
    node = next(
        (n for n in ast.walk(tree)
         if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
         and n.name == "_run_open_source_compare_once"),
        None,
    )
    assert node is not None, "`TradingScheduler._run_open_source_compare_once` 위임 미구현"
    seg = ast.get_source_segment(src, node) or ""
    assert "open_price_observe.run_open_source_compare_once(self)" in seg, seg


def test_c2_cap_is_kst_daily_emit_cap():
    """C2 — cap 은 cycle258 `KstDailyEmitCap` 재사용."""
    from src.engine import open_price_observe as obs_mod
    from src.engine.daily_emit_cap import KstDailyEmitCap

    cap = getattr(obs_mod, "_open_source_compare_cap", None)
    assert isinstance(cap, KstDailyEmitCap), f"실측={type(cap)!r}"
    assert callable(getattr(obs_mod, "reset_open_source_compare_cap", None))


# ===========================================================================
# C2 — `used_src` (시가 확정 출처) 라벨 — 적대 검증 MEDIUM #5
# ===========================================================================

@pytest.mark.asyncio
async def test_c2_used_src_is_rest_when_open_came_from_rest_fallback(
    rest_stub, sleep_spy, caplog,
):
    """C2 — 09:00:05 REST 폴백으로 확정된 종목은 `used_src=rest` 다.

    **이것이 없으면 이 사이클이 만든 계기가 거짓 결론을 낸다.** `used_open` 을
    채운 주체는 두 갈래다 — (a) 09:00:05 1차 WS 폴링(`ticker_prices`, 오염 가설의
    대상) 또는 (b) 5초 경과 후 2차 KIS REST 폴백. (b) 로 채워진 종목은 09:05:30
    대조가 **REST↔REST** 라 `delta_bp=0.0` 이 산술적으로 보장된다 — 오염이 없어서
    0 인 게 아니라 같은 소스를 두 번 읽어서 0 이다. 이 필드가 없으면 월요일 판독이
    그 행들을 "오염 없음" 으로 세어 정반대 결론에 도달한다.
    """
    from src.engine import open_price_observe as obs_mod

    _set_info(caplog)
    sched = _make_sched(vb_targets={
        "000720": _target(111600, 2000),
        "001450": _target(52900, 700),
    })
    rest_stub.table["000720"] = {"stck_oprc": "111600"}   # REST↔REST = delta 0
    rest_stub.table["001450"] = {"stck_oprc": "52000"}

    obs_mod.mark_confirmed_via_rest("volatility_breakout", "000720", "main")

    await sched._run_open_source_compare_once()

    by_ticker = {_field(l, "ticker"): l for l in _lines(caplog, _MARK_COMPARE)}
    assert _field(by_ticker["000720"], "used_src") == "rest", (
        "REST 폴백으로 확정된 종목이 ws 로 표시됐다 — delta_bp=0.0 이 '오염 없음' "
        f"으로 오독된다: {by_ticker['000720']!r}"
    )
    assert _field(by_ticker["000720"], "delta_bp") == "0.0"
    assert _field(by_ticker["001450"], "used_src") == "ws", "무표시는 ws 다"


@pytest.mark.asyncio
async def test_c2_used_src_label_is_board_and_strategy_scoped():
    """C2 — 출처 라벨 키는 `(strategy_id, ticker, board)` 다(스코프 혼선 차단)."""
    from src.engine import open_price_observe as obs_mod

    obs_mod.mark_confirmed_via_rest("volatility_breakout", "000720", "main")
    assert obs_mod.was_confirmed_via_rest("volatility_breakout", "000720", "main")
    assert not obs_mod.was_confirmed_via_rest("long_tail_volatility", "000720", "main")
    assert not obs_mod.was_confirmed_via_rest("volatility_breakout", "000720", "pre_nxt")
    assert not obs_mod.was_confirmed_via_rest("volatility_breakout", "001450", "main")


@pytest.mark.asyncio
async def test_c2_confirm_open_prices_rest_fallback_marks_source(monkeypatch):
    """C2 — `_confirm_breakout_open_prices` 의 **2차 폴백 분기**가 라벨을 심는다.

    1차 WS 폴링으로 확정된 종목에는 심지 않는다(그것이 `ws`).

    cycle272 — `open_price_scope_mode` 기본 `enforce` 에서는 1차 WS 폴링 자체가
    거부돼(`source` 기본값 불신 `"ws"`) 이 시나리오("WS 로 확정된 종목")가
    성립하지 않는다. 이 테스트는 **레거시(off) 경로 회귀 가드**로 재분류한다
    — WS 라벨 분기 자체(cycle264 의 제1 계약)는 `mode="off"` 에서 여전히
    살아 있어야 한다.
    """
    from src.engine import open_price_observe as obs_mod
    from src.engine import scanner
    from src.api import condition as cond

    sched = _make_sched(vb_targets={
        "000720": _target(0, 2000),        # WS 캐시로 확정될 종목
        "001450": _target(0, 700),         # REST 폴백으로 확정될 종목
    })
    vb = sched.registry.get("volatility_breakout")
    vb.config.params["open_price_scope_mode"] = "off"  # cycle272 — 레거시 WS 경로 회귀 가드
    vb._open_confirmed = {"000720": {}, "001450": {}}

    monkeypatch.setattr(scanner, "ticker_prices", {
        "000720": {"current_price": 112000, "open_price": 111600, "change_rate": 0.0},
    })

    async def _fake_detail(ticker: str) -> dict:
        return {"stck_oprc": "52900"}

    monkeypatch.setattr(cond, "fetch_stock_detail", _fake_detail)

    real_sleep = asyncio.sleep
    monkeypatch.setattr(asyncio, "sleep", lambda *_a, **_kw: real_sleep(0))

    await sched._confirm_breakout_open_prices(board="main", max_wait_s=1.0, interval_s=0.5)

    assert obs_mod.was_confirmed_via_rest("volatility_breakout", "001450", "main"), (
        "REST 폴백 분기가 출처 라벨을 심지 않았다"
    )
    assert not obs_mod.was_confirmed_via_rest("volatility_breakout", "000720", "main"), (
        "WS 캐시로 확정된 종목에 rest 라벨이 붙었다"
    )


@pytest.mark.asyncio
async def test_c2_source_label_never_breaks_confirm_loop(monkeypatch):
    """C2 — 출처 라벨이 터져도 시가 확정 루프는 죽지 않는다(관측 < 매매)."""
    # cycle272 이후: 09:00:35~09:05:00 창은 leaf 가 main 기준가를 전담하고 이 백스톱 루프는
    # VB·LTV 를 건너뛴다(open_price_rest.owns_board = now < 09:05). 이 테스트의 계약은 백스톱
    # 경로 자체이므로 시각과 무관하게 백스톱을 강제한다 — 실제 벽시계에 두면 00:00~09:05 KST
    # 실행(CI 00:04 실측, 2026-09-11)에서 확정 0 으로 붉어지는 시각 의존 결함이었다.
    from src.engine import open_price_rest as _opr
    monkeypatch.setattr(_opr, "owns_board", lambda *_a, **_k: False)
    from src.engine import open_price_observe as obs_mod
    from src.engine import scanner
    from src.api import condition as cond

    sched = _make_sched(vb_targets={"001450": _target(0, 700)})
    vb = sched.registry.get("volatility_breakout")
    vb._open_confirmed = {"001450": {}}
    monkeypatch.setattr(scanner, "ticker_prices", {})

    async def _fake_detail(ticker: str) -> dict:
        return {"stck_oprc": "52900"}

    monkeypatch.setattr(cond, "fetch_stock_detail", _fake_detail)

    class _BoomCap:
        def mark_emitted(self, *_a, **_kw):
            raise RuntimeError("cap boom")

        def should_emit(self, *_a, **_kw):
            raise RuntimeError("cap boom")

    monkeypatch.setattr(obs_mod, "_via_rest_marks", _BoomCap())
    real_sleep = asyncio.sleep
    monkeypatch.setattr(asyncio, "sleep", lambda *_a, **_kw: real_sleep(0))

    await sched._confirm_breakout_open_prices(board="main", max_wait_s=1.0, interval_s=0.5)

    assert vb._targets["001450"]["boards"]["main"]["open_price"] == 52900, (
        "관측 라벨의 실패가 시가 확정을 삼켰다 — 그 순간 그날 목표가가 통째로 사라진다"
    )


# ===========================================================================
# C3 — `[breakout_open_confirm]` 표시 버그 회귀 가드
# ===========================================================================

@pytest.mark.asyncio
async def test_c3_truth_fields_added_and_legacy_fields_preserved(caplog):
    """C3 — 기존 필드(`confirmed`/`empty`/`sample`) 보존 + `truth_*` 추가.

    기존 필드를 지우거나 의미를 바꾸면 과거 로그와의 대조가 끊긴다.
    """
    from src.engine.session import MarketBoard, session_tracker

    _set_info(caplog)
    sched = _make_sched(vb_targets={
        "000720": _target(111600, 2000),
        "000880": _target(123000, 1500),
        "001450": _target(0, 700),           # 미확정
    })
    vb = sched.registry.get("volatility_breakout")

    # 정상(main 활성) 상황 — 기존 필드도 진실을 말한다
    session_tracker._active = frozenset({MarketBoard.MAIN})
    try:
        sched._emit_breakout_open_confirm("main", vb)
    finally:
        session_tracker._active = frozenset()

    lines = _lines(caplog, _MARK_CONFIRM)
    assert len(lines) == 1
    line = lines[0]
    assert "board=main" in line
    assert "strategy=volatility_breakout" in line
    assert _field(line, "confirmed") == "2"
    assert _field(line, "empty") == "1"
    assert "sample=" in line
    assert _field(line, "truth_confirmed") == "2"
    assert _field(line, "truth_total") == "3"


@pytest.mark.asyncio
async def test_c3_stale_board_masking_regression(caplog):
    """C3 회귀 — **표시 버그 재현**: 세션 트래커 stale 캐시가 보드를 가려도
    `truth_*` 는 실제 확정 수를 보인다.

    09:00:05~09:00:2x 재현: `session_tracker.active = {PRE_NXT}` ∩ VB
    `tradable_boards = {main}` = ∅ → `get_targets_status()` 가 전 종목
    `open_price: 0` 으로 덮는다 → 기존 필드는 `confirmed=0 empty=3`.
    같은 순간 비필터 로그는 "3/3종목" 이라고 말한다.

    이 로그 때문에 조사 하나가 정반대 인과를 세웠다(자문 §1.1/§1.3).
    """
    from src.engine.session import MarketBoard, session_tracker

    _set_info(caplog)
    sched = _make_sched(vb_targets={
        "000720": _target(111600, 2000),
        "000880": _target(123000, 1500),
        "001450": _target(52900, 700),
    })
    vb = sched.registry.get("volatility_breakout")

    session_tracker._active = frozenset({MarketBoard.PRE_NXT})
    try:
        status = vb.get_targets_status()
        assert all(v["open_price"] == 0 for v in status.values()), (
            "전제 재현 실패 — stale 보드 가리기가 발생해야 이 테스트가 의미 있다"
        )
        sched._emit_breakout_open_confirm("main", vb)
    finally:
        session_tracker._active = frozenset()

    lines = _lines(caplog, _MARK_CONFIRM)
    assert len(lines) == 1
    line = lines[0]
    # 기존 필드는 (하위 호환을 위해) 여전히 가려진 값을 말한다
    assert _field(line, "confirmed") == "0"
    assert _field(line, "empty") == "3"
    # 진실 필드가 그 침묵을 깬다
    assert _field(line, "truth_confirmed") == "3", (
        f"`_open_confirmed` 를 직접 세지 않았다 — 이것이 표시 버그의 본체다: {line!r}"
    )
    assert _field(line, "truth_total") == "3"


@pytest.mark.asyncio
async def test_c3_truth_counts_board_scoped(caplog):
    """C3 — `truth_confirmed` 는 **그 board 의** `_open_confirmed` 만 센다."""
    from src.engine.session import MarketBoard, session_tracker

    _set_info(caplog)
    sched = _make_sched(vb_targets={
        "000720": _target(111600, 2000, extra_boards={"pre_nxt": _board(110000, 2000)}),
        "000880": {"k": 0.5, "boards": {"pre_nxt": _board(123000, 1500)}},
    })
    vb = sched.registry.get("volatility_breakout")

    session_tracker._active = frozenset({MarketBoard.PRE_NXT})
    try:
        sched._emit_breakout_open_confirm("main", vb)
    finally:
        session_tracker._active = frozenset()

    line = _lines(caplog, _MARK_CONFIRM)[0]
    assert _field(line, "truth_confirmed") == "1", (
        "000880 은 main 미확정이므로 truth_confirmed 는 1 이다"
    )
    assert _field(line, "truth_total") == "2"


@pytest.mark.asyncio
async def test_c3_strategy_without_targets_is_zero_not_crash(caplog):
    """C3 — `_targets`/`_open_confirmed` 가 없는 전략 스텁도 안전하다(0/0).

    기존 회귀 테스트(`test_observability_logs.py`)가 그런 스텁을 쓴다 — 깨뜨리지 않는다.
    """
    from src.engine.scheduler import TradingScheduler
    from src.engine.strategy_base import Signal, StrategyBase, StrategyConfig

    class _Stub(StrategyBase):
        async def prepare(self): pass
        def check_buy_signal(self, *a): return Signal.NONE
        def check_exit_signal(self, *a): return Signal.NONE
        def calc_buy_quantity(self, p): return 0
        def get_targets_status(self):
            return {"V1": {"boards": {"main": {"open_price": 10000}}, "open_price": 10000}}

    _set_info(caplog)
    sched = TradingScheduler.__new__(TradingScheduler)
    stub = _Stub(StrategyConfig(strategy_id="volatility_breakout", name="VB", weight=0.3))

    sched._emit_breakout_open_confirm("main", stub)

    line = _lines(caplog, _MARK_CONFIRM)[0]
    assert _field(line, "confirmed") == "1"
    assert _field(line, "truth_confirmed") == "0"
    assert _field(line, "truth_total") == "0"


@pytest.mark.asyncio
async def test_c3_status_failure_leaves_truth_only_row(caplog):
    """C3 — `get_targets_status()` 가 터져도 **정정 계측기는 살아남는다**.

    적대 검증 LOW #13: `truth_*` 는 `_targets`·`_open_confirmed` 만 읽으면 되는데
    계산이 `get_targets_status()` **뒤**에 있으면 early return 에 함께 쓸려 간다 —
    그 함수가 오도한다는 것이 C3 의 존재 이유인데, 더 심하게 고장 난 경우에
    정정 계측기까지 침묵하는 것은 뒤집힌 우선순위다.

    레거시 필드는 `-1` sentinel(= 미측정)이라 과거 로그 대조도 끊기지 않는다
    (`confirmed=-1` 은 예전 포맷에 존재할 수 없는 값이다).
    """
    from src.engine.scheduler import TradingScheduler

    _set_info(caplog)
    sched = TradingScheduler.__new__(TradingScheduler)

    class _Boom:
        strategy_id = "volatility_breakout"
        _targets = {"A": {}, "B": {}}
        _open_confirmed = {"A": {"main": True}}

        def get_targets_status(self):
            raise RuntimeError("status boom")

    sched._emit_breakout_open_confirm("main", _Boom())
    lines = _lines(caplog, _MARK_CONFIRM)
    assert len(lines) == 1, f"status 실패가 정정 계측기까지 삼켰다. 실측={lines!r}"
    line = lines[0]
    assert _field(line, "confirmed") == "-1" and _field(line, "empty") == "-1", line
    assert _field(line, "truth_confirmed") == "1", line
    assert _field(line, "truth_total") == "2", line


@pytest.mark.asyncio
async def test_c3_truth_block_absorbs_hostile_attribute(caplog):
    """C3 — `_targets`/`_open_confirmed` 가 **던져도** emit 은 통과한다(흡수기 잠금).

    적대 검증 MEDIUM: 뮤턴트 `except Exception: raise` 가 전 케이스를 통과했다
    (ESCAPED). 이 흡수기가 사라졌을 때의 폭발 반경은 관측 실패가 아니라 **그날
    매매 전체**다 — `_emit_breakout_open_confirm` 은 `_confirm_breakout_open_prices`
    안에서 try 없이 불리고, 그 함수는 `start()` 에서 09:00:05 에 await 되며,
    `start()` 의 except 가 KisApiError 가 아닌 예외를 받으면 finally 로 떨어져
    백그라운드 task 전부 cancel + `kis_ws.disconnect()` 를 하고 `run_daily` 가
    같은 경로로 재진입한다 = **크래시 루프**.

    `getattr(strategy, '_targets')` 는 private 속성 직접 접근이라 전략 리팩터가
    이 속성을 `@property` 로 바꾸는 순간 실제로 던질 수 있다.
    """
    from src.engine.scheduler import TradingScheduler

    _set_info(caplog)
    sched = TradingScheduler.__new__(TradingScheduler)

    class _Hostile:
        strategy_id = "volatility_breakout"

        @property
        def _targets(self):
            raise RuntimeError("property boom")

        @property
        def _open_confirmed(self):
            raise RuntimeError("property boom")

        def get_targets_status(self):
            return {"V1": {"boards": {"main": {"open_price": 10000}}, "open_price": 10000}}

    sched._emit_breakout_open_confirm("main", _Hostile())   # 예외가 새면 실패

    lines = _lines(caplog, _MARK_CONFIRM)
    assert len(lines) == 1, f"흡수기가 없어 emit 이 통째로 사라졌다: {lines!r}"
    assert _field(lines[0], "confirmed") == "1", "레거시 필드는 정상 동작을 유지한다"
    assert _field(lines[0], "truth_confirmed") == "0"
    assert _field(lines[0], "truth_total") == "0"


@pytest.mark.asyncio
async def test_c3_truth_total_denominator_is_targets_not_open_confirmed(caplog):
    """C3 — `truth_total` 분모는 **`_targets`** 다(`_open_confirmed` 가 아니다).

    적대 검증 MEDIUM(M29 ESCAPED): 분모를 `_open_confirmed` 로 바꿔치기해도 기존
    케이스가 전부 통과했다. `_targets` 에는 있는데 `_open_confirmed` 에 항목이
    **아예 없는** 종목이 곧 '미확정' 이고, 그것이야말로 이 수치가 세려는 대상이다.
    """
    from src.engine.scheduler import TradingScheduler

    _set_info(caplog)
    sched = TradingScheduler.__new__(TradingScheduler)

    class _Partial:
        strategy_id = "volatility_breakout"
        _targets = {"A": {}, "B": {}, "C": {}}
        _open_confirmed = {"A": {"main": True}}      # B/C 는 키 자체가 없다

        def get_targets_status(self):
            return {}

    sched._emit_breakout_open_confirm("main", _Partial())
    line = _lines(caplog, _MARK_CONFIRM)[0]
    assert _field(line, "truth_total") == "3", (
        f"분모가 `_open_confirmed`(1) 로 바뀌었다 — 미확정 2종목이 사라진다: {line!r}"
    )
    assert _field(line, "truth_confirmed") == "1", line
