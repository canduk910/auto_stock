"""cycle238 (P1-6) — NXT 프리장 청산 보류 게이트의 **08:00 정각 ~30초 구멍** 시정 (시정안 A).

## 확증된 결함

`RiskManager._defers_pre_market_exit` 의 유일한 판정 소스는 `session_tracker.active` 인데,
그 값의 유일한 기록자는 `SessionTracker.tick()` 이고 `tick()` 은 `_session_loop` 가
**30초 주기**로만 호출한다(`SESSION_TICK_INTERVAL = 30`). 따라서 `boards_at(07:59:xx) == ∅`
스냅샷이 **08:00:00~08:00:29 동안 그대로 살아 있고**, 그 창에 들어온 프리장 첫 틱은
게이트가 fail-open 으로 열린 채 청산 평가를 통과한다 — 실측(09-02) 로그가
`도치안 시간 기반 청산` 08:00:00 발화 → `[pre_market_exit_deferred]` 08:00:29 순서로
그 구멍을 그대로 찍었고, 실제 매도 주문이 나가 APBK0918 로 거부됐다.

## 시정 설계 (명세 §2.1)

```
whitelist(LTV) → False (불변)
by_active = PRE_NXT ∈ active ∧ MAIN ∉ active      # 기존 소스(30초 stale 캐시)
by_clock  = boards_at(_now_kst().time()) 가 PRE_NXT 단독   # 신규 소스(fresh, 같은 표)
defer     = bool(by_active) or bool(by_clock)      # OR — 둘 다 판정 불가면 False
```

- **스케줄 표 단일 소스** — 시각 폴백은 `08:00`/`09:00` 리터럴을 새로 쓰지 않고
  tracker 가 쓰는 바로 그 `session.boards_at` 를 **fresh 로** 읽는다(T-8 이 봉인).
- **KST 명시** — `_now_kst()` = `datetime.now(_KST)`. naive `datetime.now()` 금지(P2-6 부류).
- **09:00 정각은 반대 방향으로 놔둔다** — stale `active`={PRE_NXT} 가 남은 ≤30초는 OR 라
  보류가 유지된다(= 현행 라이브 행위 동일). 한 사이클에 한 엣지만 바꿔야 D+1 귀인이 되고,
  그 방향은 안전 방향이다. 대신 `reason=active_stale_hold` 로 **계량**한다(T-4).
- **fail-open 계약 보존** — 두 소스 모두 예외일 때만 False(T-7). 손절 정지가 더 위험하다.

## 결정성 seam

시각 폴백은 벽시계 의존을 불가피하게 도입한다(08:00 라이브와 단위 테스트 기본 상태가
둘 다 `active`=∅ 라 `active` 만으로는 구분 불가). 루트 `tests/conftest.py` 의 autouse
`_pin_pre_market_clock` 이 `risk._now_kst` 를 MAIN 구간으로 핀하고(T-10 이 그 계약을 고정),
이 파일은 `_clock` 픽스처(픽스처보다 뒤에 도는 monkeypatch)로 시각을 명시하거나
`@pytest.mark.real_pre_market_clock` 로 옵트아웃해 실 seam 을 검증한다(T-6/T-7/T-8/T-11).

리그(`_SpyStrategy`/`_rig`/`_active`)는 `test_risk_pre_market_exit_gate.py` 에서 **import 재사용**
한다(복붙 금지 — 두 파일의 리그가 갈리면 게이트 계약이 조용히 둘로 쪼개진다).
"""

from __future__ import annotations

import ast
import inspect
import logging
import textwrap
from datetime import datetime, timedelta, timezone

import pytest
from freezegun import freeze_time

from src.engine import risk as risk_mod
from src.engine.session import MarketBoard, boards_at, session_tracker
from src.engine.strategy_base import Signal

# 리그 재사용 — `_active` 는 fixture 라 import 만으로 이 모듈에서 사용 가능하다.
from tests.unit.engine.test_risk_pre_market_exit_gate import (  # noqa: F401
    _SpyStrategy,
    _active,
    _rig,
)

pytestmark = pytest.mark.unit

KST = timezone(timedelta(hours=9))

DIVERGENCE_MARKER = "[pre_market_exit_gate_divergence]"
DEFERRED_MARKER = "[pre_market_exit_deferred]"


def _at(hour: int, minute: int, second: int = 0, *, day: int = 2) -> datetime:
    """2026-09-02(수) 기준 KST aware datetime — 결함 실측일과 같은 날."""
    return datetime(2026, 9, day, hour, minute, second, tzinfo=KST)


@pytest.fixture
def _clock(monkeypatch: pytest.MonkeyPatch):
    """게이트 시각 seam 명시 주입 — autouse 핀보다 뒤에 적용되므로 이긴다."""

    def _set(dt: datetime) -> None:
        monkeypatch.setattr(risk_mod, "_now_kst", lambda: dt, raising=False)

    return _set


def _messages(caplog: pytest.LogCaptureFixture, marker: str) -> list[str]:
    return [r.getMessage() for r in caplog.records if marker in r.getMessage()]


# ---------------------------------------------------------------------------
# T-1 — 핵심: 08:00 정각 창(active 는 07:59 스냅샷 ∅)에서 보류돼야 한다
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_t1_clock_pre_market_when_active_is_stale_empty_then_exit_eval_deferred(
    _clock, _active
):
    """08:00:00 틱 + `active`=∅(07:59 스냅샷) — 라이브에서 실제로 매도가 나갔던 그 창."""
    _clock(_at(8, 0, 0))
    _active(set())
    rm, strat, oe = _rig("donchian_swing")

    await rm.on_tick("005930", 60_000, 60_000, 0.0)   # 왜곡된 프리장 급락 틱

    assert strat.exit_calls == [], (
        "08:00:00~29 는 `active` 가 30초 stale 이라 ∅ 다. 시각 폴백이 없으면 "
        "프리장 왜곡 틱이 청산 평가를 통과한다(09-02 실측 결함)."
    )
    oe.execute_sell.assert_not_awaited()
    assert strat.state.positions["005930"].high_since_buy == 70_000


@pytest.mark.asyncio
async def test_t1b_clock_pre_market_when_stale_empty_then_high_since_buy_not_polluted(
    _clock, _active
):
    """보류의 실익 절반은 앵커 보호다 — 프리장 왜곡 고가가 박히면 09:00 이후 조기 청산."""
    _clock(_at(8, 0, 0))
    _active(set())
    rm, strat, _ = _rig("donchian_swing", exit_signal=Signal.NONE)
    pos = strat.state.positions["005930"]

    await rm.on_tick("005930", 95_000, 95_000, 0.0)   # 왜곡된 프리장 급등 틱

    assert pos.high_since_buy == 70_000, "프리장 틱으로 트레일링 앵커가 오염되면 안 된다"


# ---------------------------------------------------------------------------
# T-2 — 관측: 기존 deferred 1회 + 신규 divergence(clock_fallback) 1회
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_t2_clock_fallback_emits_deferred_once_and_divergence_once(
    _clock, _active, caplog
):
    """D+1 판독 채널 — `reason=clock_fallback` 이 곧 '구멍을 시각이 닫았다'는 증거다.

    두 마커 모두 1회/전략/일 cap. 매 틱 폭주는 cycle237 이 실측한 하루 1만 행 부류다.
    """
    _clock(_at(8, 0, 0))
    _active(set())
    rm, _, _ = _rig("donchian_swing")

    with caplog.at_level(logging.INFO):
        for _ in range(5):
            await rm.on_tick("005930", 60_000, 60_000, 0.0)

    deferred = _messages(caplog, DEFERRED_MARKER)
    divergence = _messages(caplog, DIVERGENCE_MARKER)

    assert len(deferred) == 1, f"기존 마커 cap 무변경(1회/전략/일) — 실제 {len(deferred)}"
    assert len(divergence) == 1, (
        f"divergence 는 두 소스가 갈릴 때만 1회/(strategy, reason)/일 — 실제 {len(divergence)}"
    )
    msg = divergence[0]
    assert "reason=clock_fallback" in msg, msg
    assert "strategy=donchian_swing" in msg, msg
    assert "active=" in msg, "판독하려면 그 시점 stale 스냅샷이 로그에 있어야 한다"
    assert "clock_kst=" in msg, "판독하려면 폴백이 읽은 시각이 로그에 있어야 한다"


# ---------------------------------------------------------------------------
# T-3 — 경계는 `boards_at` 표 그대로 (새 리터럴 도입 금지)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize(
    "clock, boards, expect_defer",
    [
        (_at(8, 59, 59), set(), True),
        (_at(9, 0, 0), {MarketBoard.MAIN}, False),
    ],
    ids=["08:59:59+active=empty", "09:00:00+active=main"],
)
async def test_t3_boundary_follows_boards_at_schedule(
    clock, boards, expect_defer, _clock, _active
):
    _clock(clock)
    _active(boards)
    rm, strat, oe = _rig("donchian_swing")

    await rm.on_tick("005930", 60_000, 60_000, 0.0)

    if expect_defer:
        assert strat.exit_calls == [], "08:59:59 는 여전히 PRE_NXT 단독 구간"
        oe.execute_sell.assert_not_awaited()
    else:
        assert len(strat.exit_calls) == 1, "09:00:00 부터는 MAIN — 정상 평가 재개"
        oe.execute_sell.assert_awaited_once()


# ---------------------------------------------------------------------------
# T-4 — 09:00 정각 stale 보류 유지(OR) + 계량 마커
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_t4_stale_active_pre_at_main_clock_keeps_hold_and_emits_active_stale_hold(
    _clock, _active, caplog
):
    """team-leader 결정 — 이 방향(09:00:00~29 보류 유지)은 **바꾸지 않는다**.

    (a) 안전 방향(평가 지연 ≤30초, 사고 증거 0) (b) 한 사이클 한 엣지 (c) 개장 직후
    30초는 스프레드가 가장 넓다. 대신 계량해 clock-primary 후속 판단 근거를 남긴다.
    """
    _clock(_at(9, 0, 0))
    _active({MarketBoard.PRE_NXT})
    rm, strat, oe = _rig("donchian_swing")

    with caplog.at_level(logging.INFO):
        for _ in range(3):
            await rm.on_tick("005930", 60_000, 60_000, 0.0)

    assert strat.exit_calls == [], "OR 판정 — 현행 라이브 행위와 동일하게 보류 유지"
    oe.execute_sell.assert_not_awaited()

    divergence = _messages(caplog, DIVERGENCE_MARKER)
    assert len(divergence) == 1, f"1회/(strategy, reason)/일 — 실제 {len(divergence)}"
    assert "reason=active_stale_hold" in divergence[0], divergence[0]


# ---------------------------------------------------------------------------
# T-5 — 화이트리스트 불변 (시각 폴백이 LTV 를 잡아채면 안 된다)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_t5_ltv_whitelist_survives_clock_fallback(_clock, _active):
    """LTV 는 프리장 매매가 설계 의도 — 화이트리스트 검사가 두 소스보다 **앞**이어야 한다."""
    _clock(_at(8, 30, 0))
    _active(set())
    rm, strat, oe = _rig("long_tail_volatility")

    await rm.on_tick("005930", 60_000, 60_000, 0.0)

    assert len(strat.exit_calls) == 1, "화이트리스트 전략은 프리장에도 정상 평가"
    oe.execute_sell.assert_awaited_once()


# ---------------------------------------------------------------------------
# T-6 — 실 seam 은 tz-aware KST (naive `datetime.now()` 금지)
# ---------------------------------------------------------------------------

@pytest.mark.real_pre_market_clock
def test_t6_now_kst_seam_is_tz_aware_kst():
    assert hasattr(risk_mod, "_now_kst"), (
        "cycle238 미구현 — `src/engine/risk.py` 에 모듈 함수 `_now_kst()` 가 있어야 한다"
    )
    assert hasattr(risk_mod, "_KST"), (
        "cycle238 미구현 — `src/engine/risk.py` 에 `_KST = timezone(timedelta(hours=9))` "
        "상수가 있어야 한다(session.py:25 관례)"
    )
    now = risk_mod._now_kst()
    assert isinstance(now, datetime), f"_now_kst() 는 datetime 을 돌려줘야 한다: {now!r}"
    assert now.tzinfo is not None, "naive datetime 금지 — P2-6 부류 결함"
    assert now.utcoffset() == timedelta(hours=9), (
        f"KST(+09:00) 고정이어야 한다 — 실제 {now.utcoffset()}"
    )
    assert risk_mod._KST.utcoffset(None) == timedelta(hours=9)


# ---------------------------------------------------------------------------
# T-7 — fail-open 계약: 두 소스 모두 죽었을 때만 False
# ---------------------------------------------------------------------------

@pytest.mark.real_pre_market_clock
def test_t7_fail_open_contract_when_sources_raise(monkeypatch):
    """한쪽만 살아 있으면 그쪽 판정을 쓴다. 둘 다 죽으면 평가 유지(손절 정지가 더 위험)."""
    assert hasattr(risk_mod, "_now_kst"), (
        "cycle238 미구현 — `risk._now_kst` seam 이 있어야 예외 주입 검증이 성립한다"
    )
    rm, _, _ = _rig("donchian_swing")

    def _boom():
        raise RuntimeError("clock down")

    monkeypatch.setattr(risk_mod, "_now_kst", _boom)

    # (a) clock 판정 불가 + active=∅ → fail-open
    monkeypatch.setattr(session_tracker, "_active", frozenset())
    assert rm._defers_pre_market_exit("donchian_swing") is False, (
        "두 소스가 모두 '프리장 아님/판정 불가' 면 평가 유지"
    )

    # (b) clock 판정 불가 + active={PRE_NXT} → 살아 있는 쪽으로
    monkeypatch.setattr(session_tracker, "_active", frozenset({MarketBoard.PRE_NXT}))
    assert rm._defers_pre_market_exit("donchian_swing") is True, (
        "clock 이 죽어도 기존 소스가 살아 있으면 종전 계약대로 보류"
    )

    # (c) 두 소스 모두 판정 불가 → False
    monkeypatch.setattr(
        type(session_tracker),
        "active",
        property(lambda self: (_ for _ in ()).throw(RuntimeError("session down"))),
    )
    assert rm._defers_pre_market_exit("donchian_swing") is False, (
        "관측/판정 실패가 손절을 영구 정지시키면 안 된다 — fail-open"
    )


# ---------------------------------------------------------------------------
# T-8 — 소스 가드: 스케줄 표 단일 소스 · KST 명시 · hot path 규약
# ---------------------------------------------------------------------------

def _gate_sources() -> str:
    """게이트 + 시각 폴백 헬퍼 + 시각 seam 의 소스를 하나로 합친다."""
    fns = [risk_mod.RiskManager._defers_pre_market_exit]
    clock_fn = getattr(risk_mod, "_pre_market_only_by_clock", None)
    now_fn = getattr(risk_mod, "_now_kst", None)
    assert clock_fn is not None, (
        "cycle238 미구현 — `risk._pre_market_only_by_clock()` 모듈 헬퍼가 있어야 한다"
    )
    assert now_fn is not None, "cycle238 미구현 — `risk._now_kst()` 모듈 함수가 있어야 한다"
    fns += [clock_fn, now_fn]
    return "\n".join(textwrap.dedent(inspect.getsource(f)) for f in fns)


def _non_docstring_str_constants(tree: ast.AST) -> list[str]:
    doc_ids: set[int] = set()
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                doc_ids.add(id(body[0].value))
    return [
        n.value
        for n in ast.walk(tree)
        if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in doc_ids
    ]


@pytest.mark.real_pre_market_clock
def test_t8_gate_source_guard():
    """m5(시각 리터럴)·m6(naive now)·hot path 규약을 소스 레벨에서 봉인."""
    src = _gate_sources()
    tree = ast.parse(src)

    # 사이클 38 doctrine — `tradable_boards` 는 매수 전용 (기존 가드 승계)
    assert "tradable_boards" not in src, (
        "매수 목적의 보드 변경이 청산 규약을 조용히 바꾸는 커플링 금지"
    )

    # 스케줄 표 단일 소스 — tracker 가 쓰는 바로 그 표를 fresh 로 읽는다
    assert "boards_at" in src, (
        "시각 폴백은 `session.boards_at` 를 써야 한다 — 자체 시각 리터럴 금지"
    )
    # F2 (적대 검증) — 문자열 포함만으로는 docstring 의 "session.boards_at" 언급이
    # 가드를 충족시킨다(뮤테이션 `.hour == 8` 이 escape). **실제 호출**을 요구한다.
    boards_at_calls = [
        n for n in ast.walk(tree)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Name) and n.func.id == "boards_at"
    ]
    assert boards_at_calls, (
        "`boards_at(...)` 호출이 게이트 소스에 실재해야 한다 — docstring 언급은 소스가 아니다"
    )

    # m5 — `time(8, 0) <= t < time(9, 0)` 부류 리터럴 금지.
    # 금지 대상은 **인자를 받는 생성자 호출**(`time(8, 0)` / `datetime.time(8, 0)`)이다.
    # `_now_kst().time()` 처럼 인자 0개인 시각 **추출** 호출은 스케줄 표를 읽기 위한
    # 정당한 경로라 허용한다 — 이걸 같이 막으면 구현이 `timetz().replace(tzinfo=None)`
    # 같은 우회로 밀려 가드가 의도(표 이원화 금지)와 무관한 형태 규제가 된다.
    time_calls = [
        n for n in ast.walk(tree)
        if isinstance(n, ast.Call)
        and (
            (isinstance(n.func, ast.Name) and n.func.id == "time")
            or (isinstance(n.func, ast.Attribute) and n.func.attr == "time")
        )
        and (n.args or n.keywords)
    ]
    assert time_calls == [], (
        "`time(8, 0)` / `time(9, 0)` 같은 자체 시각 리터럴 금지 — "
        "표가 둘로 갈리면 스케줄 변경이 한쪽에만 반영된다"
    )
    literals = _non_docstring_str_constants(tree)
    bad = [s for s in literals if "08:00" in s or "09:00" in s]
    assert bad == [], f"시각 문자열 리터럴 금지(스케줄 표 단일 소스): {bad}"

    # m6 — naive `datetime.now()` 금지 (인자 0개 now 호출)
    naive_now = [
        n for n in ast.walk(tree)
        if isinstance(n, ast.Call)
        and (
            (isinstance(n.func, ast.Attribute) and n.func.attr == "now")
            or (isinstance(n.func, ast.Name) and n.func.id == "now")
        )
        and not n.args
        and not n.keywords
    ]
    assert naive_now == [], (
        "naive `datetime.now()` 금지 — tz 를 명시하지 않으면 컨테이너 TZ 에 좌우된다(P2-6)"
    )

    # hot path 규약 — logger 만 (A-1)
    assert [n for n in ast.walk(tree) if isinstance(n, ast.Await)] == [], (
        "게이트는 on_tick hot path 다 — `await` 금지"
    )
    assert "write_log(" not in src, "hot path 에서 DB 로그 금지 — `logger` 만"


# ---------------------------------------------------------------------------
# T-9 — cap: 날짜 키 자기 리셋 · 정산 동행 clear · peek→로그→mark
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_t9a_divergence_cap_resets_on_day_change(_clock, _active, caplog):
    """cap 의 날짜 키는 `_now_kst()` 에서 나와야 한다 (cycle237 `_emit_breakeven_promote` 패턴).

    프로세스가 며칠 상주하므로 어제 mark 가 오늘을 침묵시키면 D+1 판독이 죽는다.
    """
    _active(set())
    rm, _, _ = _rig("donchian_swing")

    with caplog.at_level(logging.INFO):
        _clock(_at(8, 0, 0, day=2))
        for _ in range(3):
            await rm.on_tick("005930", 60_000, 60_000, 0.0)
        _clock(_at(8, 0, 0, day=3))
        for _ in range(3):
            await rm.on_tick("005930", 60_000, 60_000, 0.0)

    divergence = _messages(caplog, DIVERGENCE_MARKER)
    assert len(divergence) == 2, (
        f"날짜가 바뀌면 자기 리셋으로 재발화해야 한다 — 실제 {len(divergence)}"
    )


@pytest.mark.asyncio
async def test_t9b_divergence_cap_cleared_by_reset_daily_state(_clock, _active, caplog):
    _clock(_at(8, 0, 0))
    _active(set())
    rm, _, _ = _rig("donchian_swing")

    with caplog.at_level(logging.INFO):
        await rm.on_tick("005930", 60_000, 60_000, 0.0)
        rm.reset_daily_state()
        await rm.on_tick("005930", 60_000, 60_000, 0.0)

    divergence = _messages(caplog, DIVERGENCE_MARKER)
    assert len(divergence) == 2, (
        f"`reset_daily_state()` 동행 clear 누락 — 정산 후 잔류 금지. 실제 {len(divergence)}"
    )


def test_t9c_logger_failure_neither_consumes_cap_nor_changes_verdict(
    _clock, _active, monkeypatch
):
    """mark-before-log 금지(cycle226 D-3) + 관측 실패 ≠ 행위 변화.

    로그 sink 가 죽었을 때 cap 이 먼저 소비되면 그 전략이 **종일 봉인**된다
    (관측기의 자기 실패가 관측 대상을 지운다). 그리고 어떤 경우에도 게이트 판정은
    바뀌지 않는다 — 여기서 예외가 새면 프리장 보류가 통째로 무너진다.
    """
    _clock(_at(8, 0, 0))
    _active(set())
    rm, _, _ = _rig("donchian_swing")

    attempts: list[tuple] = []

    def _raising_info(*args, **kwargs):
        attempts.append(args)
        raise RuntimeError("log sink down")

    monkeypatch.setattr(risk_mod.logger, "info", _raising_info)

    first = rm._defers_pre_market_exit("donchian_swing")
    second = rm._defers_pre_market_exit("donchian_swing")

    assert first is True and second is True, "관측 실패가 게이트 판정을 바꾸면 안 된다"

    divergence_attempts = [a for a in attempts if a and DIVERGENCE_MARKER in str(a[0])]
    assert len(divergence_attempts) == 2, (
        "peek → 로그 → mark 순서여야 한다. 로그가 던졌는데 cap 이 소비되면 다음 호출에서 "
        f"재시도되지 않는다 — 실제 시도 {len(divergence_attempts)}회"
    )


# ---------------------------------------------------------------------------
# T-10 — autouse 픽스처 계약 (기존 on_tick 테스트 11+ 파일 무영향의 근거)
# ---------------------------------------------------------------------------

def test_t10_autouse_fixture_pins_clock_outside_pre_market():
    assert hasattr(risk_mod, "_now_kst"), (
        "autouse `_pin_pre_market_clock` 이 `risk._now_kst` 를 핀해야 한다 "
        "(Red 단계에서는 raising=False 로 생성)"
    )
    pinned = risk_mod._now_kst()
    assert boards_at(pinned.time()) == {MarketBoard.MAIN}, (
        f"핀 시각이 MAIN 구간이 아니면 기존 테스트가 프리장 보류에 걸린다 — {pinned}"
    )


# ---------------------------------------------------------------------------
# T-11 — 실 seam 이 frozen 벽시계에서 동작하는지 (핀 없이)
# ---------------------------------------------------------------------------

@pytest.mark.real_pre_market_clock
@pytest.mark.asyncio
async def test_t11_real_seam_defers_under_frozen_wall_clock(_active):
    assert hasattr(risk_mod, "_now_kst"), "cycle238 미구현 — `risk._now_kst` 부재"
    _active(set())

    with freeze_time("2026-09-02 08:00:00+09:00"):
        # 전제 — tz-aware 조회는 08:00 KST 를 돌려준다(naive 조회는 UTC 23:00 이라 무의미).
        assert datetime.now(KST).strftime("%H:%M") == "08:00"
        rm, strat, oe = _rig("donchian_swing")
        await rm.on_tick("005930", 60_000, 60_000, 0.0)

    assert strat.exit_calls == [], "실 벽시계 seam 이 08:00 창을 닫아야 한다"
    oe.execute_sell.assert_not_awaited()


# ---------------------------------------------------------------------------
# 적대 검증 후속 (tester F1·F3·F4) — 명세 §2.1/§2.2 계약 중 뮤테이션이 빠져나간 분기
# ---------------------------------------------------------------------------

def test_f1_active_source_dead_but_clock_pre_market_then_defers(monkeypatch, _clock):
    """F1 — `active` 소스만 죽고 시각이 PRE 창이면 **보류**(한쪽 생존 = 그쪽 판정).

    뮤테이션 m14(`except: by_active=None` 을 옛 `return False` 로 환원)가 T-7 (a)~(c) 를
    전부 통과했다 — "한쪽만 살아 있으면 그쪽으로" 계약의 이 방향만 미봉인이었다.
    """
    _clock(_at(8, 0, 0))
    monkeypatch.setattr(
        type(session_tracker), "active",
        property(lambda self: (_ for _ in ()).throw(RuntimeError("tracker dead"))),
    )
    rm, _, _ = _rig("donchian_swing")
    assert rm._defers_pre_market_exit("donchian_swing") is True, (
        "tracker 가 죽어도 시각이 PRE 창이면 보류해야 한다 — 옛 fail-closed(return False) 환원 금지"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "boards, clock",
    [
        ({MarketBoard.PRE_NXT}, _at(8, 30, 0)),
        ({MarketBoard.MAIN}, _at(10, 30, 0)),
        ({MarketBoard.POST_NXT}, _at(16, 0, 0)),
        (set(), _at(21, 0, 0)),
    ],
    ids=["pre&08:30", "main&10:30", "post&16:00", "empty&21:00"],
)
async def test_f3_divergence_is_silent_when_sources_agree(boards, clock, _clock, _active, caplog):
    """F3 — 두 소스가 **일치**하면 divergence 0건. 일치 상태에서도 찍히면(뮤테이션 m12)
    `reason=clock_fallback` 이 매일 정상 PRE 틱에서 나와 D+1 "구멍을 시각이 닫았다" 판독이 죽는다.
    """
    _clock(clock)
    _active(boards)
    rm, _, _ = _rig("donchian_swing")
    with caplog.at_level(logging.INFO):
        for _ in range(3):
            await rm.on_tick("005930", 60_000, 60_000, 0.0)
    assert _messages(caplog, DIVERGENCE_MARKER) == [], (
        "일치 상태에서 divergence 발화 금지 — 마커는 '두 소스가 갈릴 때만' 이 계약"
    )


@pytest.mark.asyncio
async def test_f4_whitelist_short_circuits_before_both_sources(_clock, _active, caplog):
    """F4 — 화이트리스트(LTV) 검사는 두 소스보다 **앞**이다.

    뒤로 옮겨도 판정은 같지만(뮤테이션 m7b escape) LTV 가 divergence 계량에 섞여
    `reason=clock_fallback` 이 게이트 대상이 아닌 전략에서 찍힌다 — 판독 오염.
    """
    _clock(_at(8, 0, 0))     # 갈리는 조합: clock PRE, active ∅
    _active(set())
    rm, strat, oe = _rig("long_tail_volatility")
    with caplog.at_level(logging.INFO):
        await rm.on_tick("005930", 60_000, 60_000, 0.0)
    assert len(strat.exit_calls) == 1
    oe.execute_sell.assert_awaited_once()
    assert _messages(caplog, DIVERGENCE_MARKER) == [], (
        "화이트리스트 전략은 소스 판정 자체를 타지 않는다 — divergence 계량 대상 아님"
    )
