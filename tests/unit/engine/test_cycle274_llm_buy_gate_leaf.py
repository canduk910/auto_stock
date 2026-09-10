"""cycle274 Red — `src/engine/llm_buy_gate.py` leaf (관측 배선 · 실패 규약 · 자원 상한).

정본 = `_workspace/domain_consult/cycle274_llm_buy_gate_20260910.md`
(§5.2 `observe_signal` · §5.3 `_evaluate` · §5.4 자원 상한 · §6.2 키 · §6.4 출력 검증 ·
§7.1 마커 4종 · §7.2 `slip_bp` · §9 C4·C6·C7·C8·C11·C12·C14)

**Red 단계 — 테스트만. `src/` 미변경.** Green = backend-dev.
`src.engine.llm_buy_gate` 는 아직 없으므로 전 케이스가 RED 다. 수집이 죽지 않도록
모듈은 **함수 안에서 `importlib`** 로 연다 — `pytest.importorskip` 은 쓰지 않는다
(skip 은 Red 가 아니고, Green 이 leaf 를 만드는 순간 그대로 초록이 되어야 한다).

## OpenAI 실호출 금지

이 파일은 **네트워크를 타지 않는다.** 클라이언트 seam 은 모듈 전역 `_get_client()`
하나이고 모든 테스트가 그것을 fake 로 갈아끼운다(§4.4 "모듈 전역 싱글톤").
`_get_client()` 는 키가 비면 **`None`** 을 돌려주고 그 경우 `reason=no_key` 다.

## 이 파일이 고정하는 Green 계약

| 이름 | 계약 |
|---|---|
| `observe_signal(**kw) -> None` | 동기·never-raise·반환 항상 None. 인자는 **전부 키워드**(아래 `_observe`) |
| `_evaluate(payload)` | async 본체. 세마포어 `_SEM`(2) → `_bars_cached` → `build_messages` → `wait_for(create)` |
| `_get_client()` | 모듈 전역 싱글톤 반환, 키 없으면 `None` |
| `get_recent_daily_normalized` | **모듈 전역 이름**으로 보유(= 이 파일의 monkeypatch seam) |
| `settings` | 모듈 전역 이름(`from src.config import settings`) |
| `reset_llm_buy_gate_state()` | 래치·일일 cap·일봉 캐시 일괄 초기화(테스트·운영 훅, cycle264/268 선례) |
| `_bars_cache` / `_BARS_CACHE_MAX` | `(ticker, KST date)` dict + 상한 **400** |
| `_bars_cached(ticker, *, now_kst)` | 캐시 경유 일봉(오늘 봉 폐기 후) |
| `_tasks` | 진행 중 task 강참조 set(완료 시 discard — asyncio GC 방지) |
| `_latch` | `KstDailyEmitCap[(strategy, ticker)]` **별도 인스턴스** |
| `build_messages` | `llm_features` 에서 가져온 **모듈 전역 이름**(monkeypatch seam) |
| `MARKER_SCORE/FAILED/CONFIG/DAILY_CAP` | `[llm_buy_score]` / `[llm_buy_score_failed]` / `[llm_gate_config]` / `[llm_gate_daily_cap]` |

## 인자 확장 규칙

이 파일의 `_observe()` 가 넘기는 키워드 집합이 **최소 계약**이다. Green 이 인자를
더 붙여도 좋지만(예: `acml_vol_shares` — 자문 §3.3 이 `tick_volume.get_observed_acml_vol`
을 출처로 적었으나 §10 leaf import 한정에 `tick_volume` 이 없어, 전략이 넘기거나 leaf 가
**함수 내 지연 import** 로 읽어야 한다) **반드시 기본값을 준다** — 기본값 없는 필수 인자를
추가하면 이 파일 전체가 `TypeError` 로 죽는다.

## caplog 규약

마커는 전부 **INFO**(cap 만 WARNING)라 `caplog.set_level(logging.INFO, logger=...)`
로 로거를 명시한다 — CI 루트 로거는 DEBUG 라 무한정 세면 `observer_trace` 의 debug
흔적까지 잡힌다(`feedback_caplog_debug_level` 교훈).
"""

from __future__ import annotations

import asyncio
import importlib
import json
import logging
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from freezegun import freeze_time

pytestmark = pytest.mark.unit

KST = timezone(timedelta(hours=9))

_MOD = "src.engine.llm_buy_gate"
_LOGGER = "src.engine.llm_buy_gate"

# UTC 동결 시각 ↔ KST (KST 09:00 == UTC 00:00)
_UTC_090442 = "2026-09-11 00:04:42"      # KST 2026-09-11(금) 09:04:42
_UTC_NEXT_090442 = "2026-09-14 00:04:42"  # KST 2026-09-14(월) 09:04:42

_NOW = datetime(2026, 9, 11, 9, 4, 42, tzinfo=KST)
_NOW_NEXT = datetime(2026, 9, 14, 9, 4, 42, tzinfo=KST)

_VB = "volatility_breakout"
_LTV = "long_tail_volatility"
_TICKER = "005930"

_PARAMS = {
    "llm_gate_mode": "shadow",
    "llm_gate_min_score": 70,
    "llm_gate_daily_call_cap": 20,
    "llm_gate_timeout_secs": 20,
}

_GOOD_JSON = (
    '{"score": 82, "rationale": "돌파 초과 12.4bp, 거래량 1.8배로 뒷받침",'
    ' "key_risks": ["되돌림"], "invalidations": ["목표가 이탈"]}'
)


# ---------------------------------------------------------------------------
# 모듈 로더 — 부재면 ModuleNotFoundError 로 **실패**(skip 금지)
# ---------------------------------------------------------------------------
def _g():
    return importlib.import_module(_MOD)


# ---------------------------------------------------------------------------
# fake OpenAI 클라이언트 (네트워크 0)
# ---------------------------------------------------------------------------
class _FakeCompletions:
    def __init__(self, owner: "FakeClient") -> None:
        self._o = owner

    async def create(self, **kwargs):
        return await self._o._create(**kwargs)


class _FakeChat:
    def __init__(self, owner: "FakeClient") -> None:
        self.completions = _FakeCompletions(owner)


class FakeClient:
    """`client.chat.completions.create(**kw)` 만 흉내낸다."""

    def __init__(
        self,
        *,
        content: str | None = _GOOD_JSON,
        exc: BaseException | None = None,
        gate: "asyncio.Event | None" = None,
        in_tok: int = 1000,
        out_tok: int = 100,
    ) -> None:
        self.chat = _FakeChat(self)
        self.calls: list[dict] = []
        self.content = content
        self.exc = exc
        self.gate = gate
        self.in_tok = in_tok
        self.out_tok = out_tok
        self.inflight = 0
        self.max_inflight = 0

    async def _create(self, **kwargs):
        self.calls.append(kwargs)
        self.inflight += 1
        self.max_inflight = max(self.max_inflight, self.inflight)
        try:
            if self.gate is not None:
                await self.gate.wait()
            else:
                await asyncio.sleep(0)
            if self.exc is not None:
                raise self.exc
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content=self.content))],
                usage=SimpleNamespace(
                    prompt_tokens=self.in_tok, completion_tokens=self.out_tok,
                ),
            )
        finally:
            self.inflight -= 1


def _resp(content: str | None, *, in_tok: int = 1000, out_tok: int = 100):
    return FakeClient(content=content, in_tok=in_tok, out_tok=out_tok)


# ---------------------------------------------------------------------------
# 일봉 스텁 — KIS 원본 키. 날짜는 오늘(KST) 이전으로만.
# ---------------------------------------------------------------------------
def _bars(n: int = 60, *, today: date | None = None, include_today: bool = False) -> list[dict]:
    base = today or _NOW.date()
    out = []
    for i in range(n):
        d = base - timedelta(days=(0 if include_today else 1) + i)
        px = 1000 + (n - i) * 5
        out.append({
            "stck_bsop_date": d.strftime("%Y%m%d"),
            "stck_oprc": str(px - 3),
            "stck_hgpr": str(px + 8),
            "stck_lwpr": str(px - 9),
            "stck_clpr": str(px),
            "acml_vol": str(500_000 + i),
        })
    return out


class _BarsSpy:
    def __init__(self, rows: list[dict] | None = None, exc: BaseException | None = None) -> None:
        self.rows = _bars() if rows is None else rows
        self.exc = exc
        self.calls: list[tuple] = []

    async def __call__(self, ticker: str, days: int, *, min_required=None):
        self.calls.append((ticker, days, min_required))
        if self.exc is not None:
            raise self.exc
        return list(self.rows)


# ---------------------------------------------------------------------------
# 픽스처
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _reset_gate_state():
    """leaf 상태(래치·cap·일봉 캐시) 초기화. 모듈 부재는 여기서 삼킨다.

    ⚠️ 이 픽스처는 **절대 던지지 않는다** — 던지면 Red 가 `ERROR`(setup 실패)로
    보고돼 "실패한 계약" 과 "돌려보지도 못한 계약" 이 구별되지 않는다. 모듈 부재는
    각 테스트 **본문**의 `_setup()` 에서 `ModuleNotFoundError` 로 터져 정직한
    `FAILED` 가 된다.
    """
    def _try_reset():
        try:
            importlib.import_module(_MOD).reset_llm_buy_gate_state()
        except Exception:
            pass

    _try_reset()
    yield
    _try_reset()


def _setup(monkeypatch):
    """leaf 모듈 + 기본 fake 배선(모델·키·scanner). 모듈 부재면 여기서 **실패**한다."""
    mod = _g()
    mod.reset_llm_buy_gate_state()
    monkeypatch.setattr(
        mod, "settings",
        SimpleNamespace(openai_api_key="test-key", openai_buy_gate_model="gpt-5.6-luna"),
    )
    from src.engine import scanner
    monkeypatch.setattr(scanner, "ticker_prices", {})
    return mod


def _wire(mod, monkeypatch, client: FakeClient | None, bars: _BarsSpy | None = None) -> _BarsSpy:
    spy = bars or _BarsSpy()
    monkeypatch.setattr(mod, "_get_client", lambda: client)
    monkeypatch.setattr(mod, "get_recent_daily_normalized", spy)
    return spy


def _observe(mod, **over) -> None:
    kw = dict(
        strategy_id=_VB,
        ticker=_TICKER,
        name="삼성전자",
        board="main",
        price_won=80500,
        board_open_won=80000,
        target_won=80400,
        target_offset_won=400,
        k=0.5,
        prev_price_won=80200,
        prdy_close_won=70000,
        market_cap_eok=5_000_000,
        trade_amount_eok=3_000,
        budget_won=247_949,
        params_snapshot=dict(_PARAMS),
        now_kst=_NOW,
    )
    kw.update(over)
    assert mod.observe_signal(**kw) is None, "`observe_signal` 반환은 항상 None 이어야 한다"


async def _drain(rounds: int = 400) -> None:
    """이 테스트가 만든 background task 가 전부 끝날 때까지 양보한다."""
    for _ in range(rounds):
        others = [
            t for t in asyncio.all_tasks()
            if t is not asyncio.current_task() and not t.done()
        ]
        if not others:
            return
        await asyncio.wait(others, timeout=5)


async def _spin(rounds: int = 80) -> None:
    for _ in range(rounds):
        await asyncio.sleep(0)


def _lines(caplog, marker: str) -> list[str]:
    """레벨(INFO 이상) + 로거 + prefix 3중 한정. 실패 흔적(`observer_failed`)은 제외."""
    out = []
    for r in caplog.records:
        if r.name != _LOGGER or r.levelno < logging.INFO:
            continue
        msg = r.getMessage()
        if msg.startswith(marker) and "observer_failed" not in msg:
            out.append(msg)
    return out


def _field(line: str, name: str) -> str:
    import re
    m = re.search(rf"(?:^|\s){re.escape(name)}=(\S+)", line)
    assert m is not None, f"필드 `{name}=` 이 로그에 없다: {line!r}"
    return m.group(1)


def _absorbed(seen: list, caplog) -> bool:
    """흔적이 남았는가 — 모듈 전역 스파이 또는 `observer_failed` 로그 레코드.

    Green 이 `trace_observer_failure` 를 모듈 전역 이름으로 부르든
    (`observer_trace.trace_observer_failure` 처럼) 속성 경유로 부르든, 혹은
    `KstDailyEmitCap.emit_once` 의 내부 흡수기를 타든 **어느 경로로도 흔적은 남아야
    한다**(cycle258 카드 #5 — 무흔적 `pass` 금지). 경로를 강제하지 않고 흔적만 잰다.
    """
    if seen:
        return True
    return any("observer_failed" in r.getMessage() for r in caplog.records)


def _tasks_created(monkeypatch, mod) -> list:
    """`asyncio.create_task` 호출 기록 — C9 의 '0건' 을 직접 센다."""
    seen: list = []
    real = asyncio.create_task

    def _spy(coro, *a, **kw):
        t = real(coro, *a, **kw)
        seen.append(t)
        return t

    monkeypatch.setattr(asyncio, "create_task", _spy)
    return seen


# ===========================================================================
# C4 — 실패 3종에서 행위 0 + `[llm_buy_score_failed] reason=` 정확 1행
# ===========================================================================
_FAIL_CASES = [
    pytest.param(FakeClient(exc=asyncio.TimeoutError()), "timeout", id="timeout"),
    pytest.param(FakeClient(exc=RuntimeError("upstream 503")), "api_error", id="api_error"),
    pytest.param(FakeClient(content="이건 JSON 이 아니다"), "parse_error", id="parse_error"),
    pytest.param(FakeClient(content='{"score": 82'), "parse_error", id="truncated-json"),
    pytest.param(FakeClient(content="[82]"), "schema_error", id="top-level-not-dict"),
    pytest.param(FakeClient(content='{"rationale":"x"}'), "schema_error", id="score-key-absent"),
]


@pytest.mark.parametrize("client,reason", _FAIL_CASES)
@freeze_time(_UTC_090442)
async def test_c4_1_failure_reasons(monkeypatch, caplog, client, reason) -> None:
    """C4 (HIGH) — 타임아웃·API 예외·파싱 실패 각각에서 `reason=` 이 정확히 1행.

    실패가 침묵하면 실패 분포가 왜곡되고(§7.1 ②), 2주 뒤 "실패율 <10%" 게이트를
    판정할 근거가 사라진다. 실패해도 매매 행위는 구조적으로 0 이다 — 아무도
    반환값을 읽지 않는다.
    """
    gate = _setup(monkeypatch)
    caplog.set_level(logging.INFO, logger=_LOGGER)
    _wire(gate, monkeypatch, client)
    _observe(gate)
    await _drain()

    failed = _lines(caplog, gate.MARKER_FAILED)
    assert len(failed) == 1, f"실패 마커가 1행이 아니다: {failed}"
    assert _field(failed[0], "reason") == reason
    assert _field(failed[0], "strategy") == _VB
    assert _field(failed[0], "ticker") == _TICKER
    assert _lines(caplog, gate.MARKER_SCORE) == [], "실패인데 점수 행이 나왔다"


@freeze_time(_UTC_090442)
async def test_c4_2_no_bars_reason(monkeypatch, caplog) -> None:
    """C4 — 일봉 30봉 미만이면 LLM 을 부르지 않고 `reason=no_bars`.

    돈을 쓰는 호출이라 판단 재료가 없으면 **부르지 않는 것**이 계약이다.
    """
    gate = _setup(monkeypatch)
    caplog.set_level(logging.INFO, logger=_LOGGER)
    client = FakeClient()
    _wire(gate, monkeypatch, client, _BarsSpy(rows=_bars(29)))
    _observe(gate)
    await _drain()

    failed = _lines(caplog, gate.MARKER_FAILED)
    assert len(failed) == 1 and _field(failed[0], "reason") == "no_bars"
    assert client.calls == [], "봉이 없는데 OpenAI 를 불렀다"


@freeze_time(_UTC_090442)
async def test_c4_3_no_key_reason(monkeypatch, caplog) -> None:
    """C4/§6.5 층3 — `_get_client()` 가 None(키 부재)이면 `reason=no_key`."""
    gate = _setup(monkeypatch)
    caplog.set_level(logging.INFO, logger=_LOGGER)
    _wire(gate, monkeypatch, None)
    _observe(gate)
    await _drain()

    failed = _lines(caplog, gate.MARKER_FAILED)
    assert len(failed) == 1 and _field(failed[0], "reason") == "no_key"


@freeze_time(_UTC_090442)
async def test_c4_4_disabled_model_reason(monkeypatch, caplog) -> None:
    """C4 — 모델명이 비면 `reason=disabled_model` + 호출 0건(§7.1 ② 사유 어휘).

    `openai_buy_gate_model` 을 빈 값으로 두는 것이 **재배포 없는 정지 수단**이다.
    """
    gate = _setup(monkeypatch)
    caplog.set_level(logging.INFO, logger=_LOGGER)
    monkeypatch.setattr(
        gate, "settings",
        SimpleNamespace(openai_api_key="test-key", openai_buy_gate_model="   "),
    )
    client = FakeClient()
    _wire(gate, monkeypatch, client)
    _observe(gate)
    await _drain()

    failed = _lines(caplog, gate.MARKER_FAILED)
    assert len(failed) == 1 and _field(failed[0], "reason") == "disabled_model"
    assert client.calls == []


@freeze_time(_UTC_090442)
async def test_c4_5_bars_db_exception_is_absorbed(monkeypatch, caplog) -> None:
    """C4 — 일봉 조회 자체가 던져도 task 밖으로 예외가 새지 않고 실패 1행만 남는다."""
    gate = _setup(monkeypatch)
    caplog.set_level(logging.INFO, logger=_LOGGER)
    _wire(gate, monkeypatch, FakeClient(), _BarsSpy(exc=RuntimeError("pool dead")))
    _observe(gate)
    await _drain()
    assert len(_lines(caplog, gate.MARKER_FAILED)) == 1


@freeze_time(_UTC_090442)
async def test_c4_6_failed_marker_carries_latency_and_model(monkeypatch, caplog) -> None:
    """C4 — 실패 행에도 `latency_ms`·`model` 이 실린다(§7.1 ② 형식)."""
    gate = _setup(monkeypatch)
    caplog.set_level(logging.INFO, logger=_LOGGER)
    _wire(gate, monkeypatch, FakeClient(exc=RuntimeError("x")))
    _observe(gate)
    await _drain()
    line = _lines(caplog, gate.MARKER_FAILED)[0]
    assert _field(line, "latency_ms").isdigit()
    assert _field(line, "model") == "gpt-5.6-luna"


@freeze_time(_UTC_090442)
async def test_c4_7_failed_latch_is_keyed_by_reason(monkeypatch, caplog) -> None:
    """C4/§7.1 ② — 실패 래치 키에 **사유가 들어간다**.

    같은 종목이 타임아웃 뒤 파싱 실패를 낼 수 있고, 두 번째가 침묵하면 실패 분포가
    왜곡된다. 래치(1회/(전략,종목)/일)를 리셋하고 다른 사유로 재발사하면 2행이어야 한다.
    """
    gate = _setup(monkeypatch)
    caplog.set_level(logging.INFO, logger=_LOGGER)
    _wire(gate, monkeypatch, FakeClient(exc=asyncio.TimeoutError()))
    _observe(gate)
    await _drain()

    gate.reset_llm_buy_gate_state()
    _wire(gate, monkeypatch, FakeClient(content="not json"))
    _observe(gate)
    await _drain()

    reasons = sorted(_field(l, "reason") for l in _lines(caplog, gate.MARKER_FAILED))
    assert reasons == ["parse_error", "timeout"]


@pytest.mark.slow
@freeze_time(_UTC_090442, real_asyncio=True)
async def test_c4_8_real_timeout_is_enforced(monkeypatch, caplog) -> None:
    """C4 (뮤테이션 '타임아웃 인자 제거' 킬) — 응답이 오지 않으면 실제로 잘린다.

    `AsyncOpenAI` 기본 타임아웃은 **600s** 다(§4.4). 지정하지 않으면 task 가 10분 산다.
    `llm_gate_timeout_secs=1` 로 조여 1초 안에 `reason=timeout` 이 나오는지 실측한다.

    ⚠️ **테스트 인프라 시정(Green 단계)** — freezegun 은 기본적으로
    `time.monotonic()`/`time.perf_counter()` 까지 동결한다(실측:
    `freeze_time()` 안에서 real `time.sleep(0.05)` 를 해도 monotonic 차분이
    0.0). asyncio 이벤트루프의 내부 시계가 바로 이 monotonic 이라, 동결 상태로는
    `asyncio.wait_for` 의 타임아웃이 **영원히 발화하지 않는다**(만료 시각이
    "동결된 지금"보다 항상 미래로 남는다) — 이 테스트가 검증하려는 계약(1초
    타임아웃 실제 발화)과 freezegun 기본 동작이 직접 충돌해 원래 데코레이터로는
    pytest-timeout(60s) 까지 무조건 걸린다(구현 정오와 무관). `real_asyncio=True`
    는 asyncio 쪽 시계만 실시간으로 열어 두고 `datetime.now()`/`time.time()`
    등 나머지는 그대로 동결한다 — 이 파일의 다른 KST 시각 단언(§freezegun ↔
    KST)은 무접촉이다. 검증 자체(1s 컷 → `reason=timeout`)는 바뀌지 않았다.
    """
    gate = _setup(monkeypatch)
    caplog.set_level(logging.INFO, logger=_LOGGER)
    never = asyncio.Event()
    client = FakeClient(gate=never)
    _wire(gate, monkeypatch, client)
    params = dict(_PARAMS, llm_gate_timeout_secs=1)
    _observe(gate, params_snapshot=params)
    await asyncio.wait_for(_drain(), timeout=20)

    failed = _lines(caplog, gate.MARKER_FAILED)
    assert len(failed) == 1 and _field(failed[0], "reason") == "timeout"
    never.set()


@freeze_time(_UTC_090442)
async def test_c4_9_cancelled_error_is_reraised_not_swallowed(monkeypatch, caplog) -> None:
    """C4/§5.3 — `asyncio.CancelledError` 는 **re-raise**(cycle272 `open_price_rest` 계약).

    task 취소가 본체에 갇히면 종료 시퀀스가 그 task 를 영원히 기다린다. 취소는
    실패 마커로 위장되지도 않는다.
    """
    gate = _setup(monkeypatch)
    caplog.set_level(logging.INFO, logger=_LOGGER)
    never = asyncio.Event()
    _wire(gate, monkeypatch, FakeClient(gate=never))
    created = _tasks_created(monkeypatch, gate)
    _observe(gate)
    await _spin()
    assert len(created) == 1
    created[0].cancel()
    with pytest.raises(asyncio.CancelledError):
        await created[0]
    assert created[0].cancelled()
    assert _lines(caplog, gate.MARKER_FAILED) == [], "취소가 실패 마커로 위장됐다"
    never.set()


# ===========================================================================
# 성공 경로 — `[llm_buy_score]` 형식 (§7.1 ①)
# ===========================================================================
@freeze_time(_UTC_090442)
async def test_m1_1_score_line_fields(monkeypatch, caplog) -> None:
    """§7.1 ① — 성공 1행에 판정·비용·지연·반사실이 **한 행에** 실린다.

    2주 뒤 판독은 이 한 행의 grep 으로 이뤄진다. 필드가 흩어지면 조인이 성립하지 않는다.
    """
    gate = _setup(monkeypatch)
    caplog.set_level(logging.INFO, logger=_LOGGER)
    from src.engine import scanner
    monkeypatch.setattr(scanner, "ticker_prices", {_TICKER: {"current_price": 80900}})
    _wire(gate, monkeypatch, _resp(_GOOD_JSON))
    _observe(gate)
    await _drain()

    lines = _lines(caplog, gate.MARKER_SCORE)
    assert len(lines) == 1, f"성공 행이 1행이 아니다: {lines}"
    line = lines[0]
    assert "\n" not in line, "관측 행은 1행이어야 한다(개행 금지)"
    for name in (
        "strategy", "ticker", "board", "mode", "score", "min_score", "would_block",
        "signal_price", "target", "excess_bp", "k", "signal_kst", "mins_from_open",
        "verdict_price", "slip_bp", "verdict_lag_ms", "latency_ms", "model",
        "tokens_in", "tokens_out", "cost_usd", "bars", "rsi14", "pos_ch20", "volr",
    ):
        _field(line, name)
    assert _field(line, "score") == "82"
    assert _field(line, "min_score") == "70"
    assert _field(line, "mode") == "shadow"
    assert "rationale=" in line


@freeze_time(_UTC_090442)
async def test_m1_2_would_block_is_the_counterfactual(monkeypatch, caplog) -> None:
    """§7.1 ① — `would_block = score < min_score` 가 **shadow 판정의 반사실 정본**이다.

    score 는 항상 **원값**으로 남긴다(임계를 바꿔 가며 재판독해야 하므로).
    """
    gate = _setup(monkeypatch)
    caplog.set_level(logging.INFO, logger=_LOGGER)
    _wire(gate, monkeypatch, _resp('{"score": 41}'))
    _observe(gate)
    await _drain()
    line = _lines(caplog, gate.MARKER_SCORE)[0]
    assert _field(line, "score") == "41"
    assert _field(line, "would_block").lower() == "true"


@freeze_time(_UTC_090442)
async def test_m1_3_would_block_false_at_threshold(monkeypatch, caplog) -> None:
    """§7.1 ① — 경계값 `score == min_score` 는 통과(사용자 발의 "70점 이상")."""
    gate = _setup(monkeypatch)
    caplog.set_level(logging.INFO, logger=_LOGGER)
    _wire(gate, monkeypatch, _resp('{"score": 70}'))
    _observe(gate)
    await _drain()
    assert _field(_lines(caplog, gate.MARKER_SCORE)[0], "would_block").lower() == "false"


@freeze_time(_UTC_090442)
async def test_m1_4_numeric_string_score_is_accepted(monkeypatch, caplog) -> None:
    """§6.4 6 — 숫자 문자열 `"85"` 는 int 변환에 성공하므로 **유효**하다."""
    gate = _setup(monkeypatch)
    caplog.set_level(logging.INFO, logger=_LOGGER)
    _wire(gate, monkeypatch, _resp('{"score": "85"}'))
    _observe(gate)
    await _drain()
    assert _field(_lines(caplog, gate.MARKER_SCORE)[0], "score") == "85"


@freeze_time(_UTC_090442)
async def test_m1_5_rationale_is_truncated_and_single_line(monkeypatch, caplog) -> None:
    """§6.4 10 — `rationale` 은 개행·`|` 제거 후 60자 절단(로그 1행 계약 — 검증 라운드 2 LOW: `_DbLogHandler` 500자 컷 안에 구조화 필드+rationale 이 다 들어가도록 120→60)."""
    gate = _setup(monkeypatch)
    caplog.set_level(logging.INFO, logger=_LOGGER)
    long = "가" * 400
    _wire(gate, monkeypatch, _resp('{"score": 82, "rationale": "A|B\\n\\nC' + long + '"}'))
    _observe(gate)
    await _drain()
    line = _lines(caplog, gate.MARKER_SCORE)[0]
    assert "\n" not in line
    body = line.split("rationale=", 1)[1]
    assert "|" not in body
    assert len(body.strip().strip("'")) <= 60


@freeze_time(_UTC_090442)
async def test_m1_6_missing_optional_fields_still_valid(monkeypatch, caplog) -> None:
    """§6.4 9 — `rationale`/`key_risks`/`invalidations` 는 **선택**. 없어도 score 는 유효."""
    gate = _setup(monkeypatch)
    caplog.set_level(logging.INFO, logger=_LOGGER)
    _wire(gate, monkeypatch, _resp('{"score": 55}'))
    _observe(gate)
    await _drain()
    assert len(_lines(caplog, gate.MARKER_SCORE)) == 1
    assert _lines(caplog, gate.MARKER_FAILED) == []


@freeze_time(_UTC_090442)
async def test_m1_7_latency_ms_and_verdict_lag_ms_are_independent(monkeypatch, caplog) -> None:
    """검증 파인딩 #4 (MEDIUM) — `latency_ms`(LLM 호출 구간만)와 `verdict_lag_ms`
    (신호 접수→판정 도착 전체, 세마포어 대기·DB fetch 포함)는 **서로 다른
    값**이어야 한다. 종전 구현은 `_emit_score` 가 같은 `t_start` 를 두 번 읽어
    로그의 두 필드가 항상 동일했다(enforce 전환 판정의 1차 입력 두 개가
    사실상 하나였다, §7.1/§7.7-2). 전역 `time.monotonic` 을 직접 patch 하면
    asyncio 이벤트루프 내부 타이머까지 오염되므로 leaf 전용 `_monotonic()`
    이름만 patch 한다(`open_price_rest._monotonic` 선례와 동일 안전장치).
    """
    gate = _setup(monkeypatch)
    caplog.set_level(logging.INFO, logger=_LOGGER)
    _wire(gate, monkeypatch, _resp(_GOOD_JSON))

    # 성공 경로 호출 순서 = t_start(①) → t_call(②, LLM 호출 직전) →
    # latency 계산(③, 응답 도착 직후) → verdict_lag 계산(④, `_emit_score` 안).
    # 값은 전부 2의 거듭제곱 분모(0.5/0.625/0.875)로 골라 `int((b-a)*1000)`
    # 부동소수점 절삭 오차(예: `0.6-0.5` = 0.09999999999999998)를 피한다.
    ticks = iter([0.0, 0.5, 0.625, 0.875])
    monkeypatch.setattr(gate, "_monotonic", lambda: next(ticks))

    _observe(gate)
    await _drain()
    line = _lines(caplog, gate.MARKER_SCORE)[0]
    latency = int(_field(line, "latency_ms"))
    verdict_lag = int(_field(line, "verdict_lag_ms"))
    assert latency == 125, f"latency_ms 기대 125, 실제 {latency}"
    assert verdict_lag == 875, f"verdict_lag_ms 기대 875, 실제 {verdict_lag}"
    assert latency != verdict_lag, "두 필드가 여전히 같은 값이면 회귀"


@freeze_time(_UTC_090442)
async def test_m1_8_name_is_sanitized_in_score_line(monkeypatch, caplog) -> None:
    """검증 파인딩 #5 (MEDIUM) — 종목명이 `[llm_buy_score]` 로그에서 `rationale`
    과 **같은 헬퍼**(`_clean_line_field`)로 정제된다. 개행이 든 이름 하나가
    로그 한 행을 둘로 쪼개면 §7.3 SQL 판정(`regexp_match(message,'score=...')`)
    이 위조 행(`score=100 would_block=False` 등)을 그대로 읽는다."""
    gate = _setup(monkeypatch)
    caplog.set_level(logging.INFO, logger=_LOGGER)
    _wire(gate, monkeypatch, _resp(_GOOD_JSON))
    _observe(gate, name="삼성\n\nA|B")
    await _drain()
    lines = _lines(caplog, gate.MARKER_SCORE)
    assert len(lines) == 1, f"개행 포함 이름이 로그 행을 쪼갰다: {lines}"
    assert "\n" not in lines[0]
    name_field = _field(lines[0], "name")
    assert "|" not in name_field and "\r" not in name_field


# ===========================================================================
# §7.2 — `slip_bp` (이 자문의 핵심 신설 필드)
# ===========================================================================
@freeze_time(_UTC_090442)
async def test_m2_1_slip_bp_from_scanner_prices(monkeypatch, caplog) -> None:
    """§7.2 (핵심) — 판정 도착 순간의 현재가 대비 신호가 이동폭을 bp 로 남긴다.

    enforce 의 진짜 비용은 API 요금이 아니라 **진입 지연**이다. 신호가 80,500 →
    판정 시 80,900 ⇒ (400/80500)×10000 = 49.7bp.
    """
    gate = _setup(monkeypatch)
    caplog.set_level(logging.INFO, logger=_LOGGER)
    from src.engine import scanner
    monkeypatch.setattr(scanner, "ticker_prices", {_TICKER: {"current_price": 80900}})
    _wire(gate, monkeypatch, _resp(_GOOD_JSON))
    _observe(gate)
    await _drain()
    line = _lines(caplog, gate.MARKER_SCORE)[0]
    assert _field(line, "verdict_price") == "80900"
    assert float(_field(line, "slip_bp")) == pytest.approx(400 / 80500 * 10000, abs=0.05)


@freeze_time(_UTC_090442)
async def test_m2_2_slip_bp_absent_ticker_is_none_sentinel(monkeypatch, caplog) -> None:
    """§7.2 — `scanner.ticker_prices` 에 종목이 없으면 `verdict_price=0` + `slip_bp=none`.

    0bp 로 위장하면 "이동이 없었다" 와 "잴 수 없었다" 가 같은 값이 된다.
    """
    gate = _setup(monkeypatch)
    caplog.set_level(logging.INFO, logger=_LOGGER)
    from src.engine import scanner
    monkeypatch.setattr(scanner, "ticker_prices", {})
    _wire(gate, monkeypatch, _resp(_GOOD_JSON))
    _observe(gate)
    await _drain()
    line = _lines(caplog, gate.MARKER_SCORE)[0]
    assert _field(line, "verdict_price") == "0"
    assert _field(line, "slip_bp").lower() == "none"


@freeze_time(_UTC_090442)
async def test_c17_1_leaf_does_not_mutate_scanner_prices(monkeypatch, caplog) -> None:
    """C17 (HIGH) — leaf 는 `scanner.ticker_prices` 를 **읽기만** 한다(8영역 read-only).

    호출 전후 dict 가 내용·식별자 모두 동일해야 한다.
    """
    gate = _setup(monkeypatch)
    caplog.set_level(logging.INFO, logger=_LOGGER)
    from src.engine import scanner
    prices = {_TICKER: {"current_price": 80900}}
    monkeypatch.setattr(scanner, "ticker_prices", prices)
    snapshot = {k: dict(v) for k, v in prices.items()}
    _wire(gate, monkeypatch, _resp(_GOOD_JSON))
    _observe(gate)
    await _drain()
    assert prices is scanner.ticker_prices
    assert {k: dict(v) for k, v in prices.items()} == snapshot


@freeze_time(_UTC_090442)
async def test_c17_2_leaf_does_not_mutate_params_snapshot(monkeypatch, caplog) -> None:
    """C17 — `params_snapshot` 도 변경하지 않는다(전략 `config.params` 오염 금지)."""
    gate = _setup(monkeypatch)
    caplog.set_level(logging.INFO, logger=_LOGGER)
    params = dict(_PARAMS)
    before = dict(params)
    _wire(gate, monkeypatch, _resp(_GOOD_JSON))
    _observe(gate, params_snapshot=params)
    await _drain()
    assert params == before


# ===========================================================================
# C14 — 출력 검증 8케이스 (§6.4). **클램프 금지.**
# ===========================================================================
_SCORE_GRID = [
    pytest.param('{"score": null}', id="none"),
    pytest.param('{"score": "abc"}', id="abc"),
    pytest.param('{"score": 0}', id="zero-below-range"),
    pytest.param('{"score": 101}', id="101-above-range"),
    pytest.param('{"score": true}', id="bool-true-is-not-int"),
    pytest.param('{"score": 1e999}', id="inf-overflowerror"),
    pytest.param('{"score": NaN}', id="nan"),
    pytest.param('{"rationale": "키 자체가 없다"}', id="key-absent"),
]


@pytest.mark.parametrize("content", _SCORE_GRID)
@freeze_time(_UTC_090442)
async def test_c14_1_invalid_score_is_schema_error(monkeypatch, caplog, content) -> None:
    """C14 (HIGH) — 8케이스 전부 `schema_error` + 점수 행 0 + 행위 0.

    ⚠️ **클램프하지 않는다.** 0/101 을 1/100 으로 자르면 "모델이 척도를 벗어났다" 는
    사실 자체가 지워지고, 보정 곡선이 그 오염 위에서 그려진다(§7.5).
    ⚠️ `1e999` 는 **표준 유효 JSON** 이라 `json.loads` 가 `inf` 를 만든다 —
    `int(inf)` 는 `OverflowError` 이므로 좁은 튜플 `(TypeError, ValueError)` 로 잡으면
    뚫린다(cycle262 적대 검증 HIGH 와 정확히 같은 함정). `except Exception` 이 계약이다.
    """
    gate = _setup(monkeypatch)
    caplog.set_level(logging.INFO, logger=_LOGGER)
    _wire(gate, monkeypatch, _resp(content))
    _observe(gate)
    await _drain()

    failed = _lines(caplog, gate.MARKER_FAILED)
    assert len(failed) == 1, f"실패 1행이 아니다: {failed}"
    assert _field(failed[0], "reason") == "schema_error"
    assert _lines(caplog, gate.MARKER_SCORE) == [], "범위 밖 점수가 클램프되어 기록됐다"


@pytest.mark.parametrize(
    "content,expected",
    [('{"score": 1}', "1"), ('{"score": 100}', "100")],
    ids=["lower-bound-1", "upper-bound-100"],
)
@freeze_time(_UTC_090442)
async def test_c14_2_range_boundaries_are_inclusive(monkeypatch, caplog, content, expected) -> None:
    """C14 (뮤테이션 `1<=s<=100` → `0<=s<=100` 킬) — 1 과 100 은 **유효**하다.

    경계 양쪽(0/101 은 위 격자에서 거부, 1/100 은 여기서 통과)을 함께 고정해야
    비교 연산자 한 글자 변조가 잡힌다.
    """
    gate = _setup(monkeypatch)
    caplog.set_level(logging.INFO, logger=_LOGGER)
    _wire(gate, monkeypatch, _resp(content))
    _observe(gate)
    await _drain()
    assert _field(_lines(caplog, gate.MARKER_SCORE)[0], "score") == expected


@freeze_time(_UTC_090442)
async def test_c14_3_float_score_is_truncated_to_int(monkeypatch, caplog) -> None:
    """C14/§6.4 6 — float 82.6 은 int 로 변환되어 유효하다(로그는 정수)."""
    gate = _setup(monkeypatch)
    caplog.set_level(logging.INFO, logger=_LOGGER)
    _wire(gate, monkeypatch, _resp('{"score": 82.6}'))
    _observe(gate)
    await _drain()
    assert _field(_lines(caplog, gate.MARKER_SCORE)[0], "score").isdigit()


@freeze_time(_UTC_090442)
async def test_c14_4_empty_content_is_schema_error(monkeypatch, caplog) -> None:
    """C14/§6.4 1 — content 가 None·빈 문자열이면 `schema_error`."""
    gate = _setup(monkeypatch)
    caplog.set_level(logging.INFO, logger=_LOGGER)
    _wire(gate, monkeypatch, _resp(None))
    _observe(gate)
    await _drain()
    failed = _lines(caplog, gate.MARKER_FAILED)
    assert len(failed) == 1 and _field(failed[0], "reason") == "schema_error"


# ===========================================================================
# C6 — 래치 1회/(전략,종목)/일 (거절도 래치)
# ===========================================================================
@freeze_time(_UTC_090442)
async def test_c6_1_same_ticker_same_day_calls_once(monkeypatch, caplog) -> None:
    """C6 (HIGH) — 같은 (전략,종목,일자)의 두 번째 신호는 task 0 · 점수행 1.

    없으면 한 종목이 하루 6콜을 먹는다(09-10 DB하이텍 000990 실측 — 목표가 위
    톱질 6회). 래치는 비용 통제이자 표본 왜곡 방지다.
    """
    gate = _setup(monkeypatch)
    caplog.set_level(logging.INFO, logger=_LOGGER)
    client = _resp(_GOOD_JSON)
    _wire(gate, monkeypatch, client)
    created = _tasks_created(monkeypatch, gate)
    _observe(gate)
    _observe(gate)
    await _drain()
    assert len(created) == 1, f"래치가 두 번째 발사를 막지 못했다(task={len(created)})"
    assert len(client.calls) == 1
    assert len(_lines(caplog, gate.MARKER_SCORE)) == 1


@freeze_time(_UTC_090442)
async def test_c6_2_low_score_also_latches(monkeypatch, caplog) -> None:
    """C6 — **거절(저점수)도 래치**된다(재평가 금지 = shadow 규약, §11 Q9)."""
    gate = _setup(monkeypatch)
    caplog.set_level(logging.INFO, logger=_LOGGER)
    client = _resp('{"score": 12}')
    _wire(gate, monkeypatch, client)
    _observe(gate)
    await _drain()
    _observe(gate)
    await _drain()
    assert len(client.calls) == 1


@freeze_time(_UTC_090442)
async def test_c6_3_other_ticker_is_not_latched(monkeypatch, caplog) -> None:
    """C6 — 래치 키는 (전략, 종목)이다. 다른 종목은 막히지 않는다."""
    gate = _setup(monkeypatch)
    caplog.set_level(logging.INFO, logger=_LOGGER)
    client = _resp(_GOOD_JSON)
    _wire(gate, monkeypatch, client)
    _observe(gate)
    _observe(gate, ticker="000660")
    await _drain()
    assert len(client.calls) == 2


@freeze_time(_UTC_090442)
async def test_c6_4_other_strategy_is_not_latched(monkeypatch, caplog) -> None:
    """C6 — 같은 종목이라도 전략이 다르면 별개 평가다(VB·LTV 는 규약이 다르다)."""
    gate = _setup(monkeypatch)
    caplog.set_level(logging.INFO, logger=_LOGGER)
    client = _resp(_GOOD_JSON)
    _wire(gate, monkeypatch, client)
    _observe(gate, strategy_id=_VB)
    _observe(gate, strategy_id=_LTV)
    await _drain()
    assert len(client.calls) == 2


async def test_c6_5_latch_resets_next_kst_day(monkeypatch, caplog) -> None:
    """C6 — KST 날짜가 바뀌면 다시 1회 평가한다(`KstDailyEmitCap` 자기 리셋)."""
    gate = _setup(monkeypatch)
    caplog.set_level(logging.INFO, logger=_LOGGER)
    client = _resp(_GOOD_JSON)
    _wire(gate, monkeypatch, client)
    with freeze_time(_UTC_090442):
        _observe(gate, now_kst=_NOW)
        await _drain()
    with freeze_time(_UTC_NEXT_090442):
        _observe(gate, now_kst=_NOW_NEXT)
        await _drain()
    assert len(client.calls) == 2


# ===========================================================================
# C7 — 일일 cap (전략별)
# ===========================================================================
@freeze_time(_UTC_090442)
async def test_c7_1_cap_blocks_third_signal(monkeypatch, caplog) -> None:
    """C7 (뮤테이션 `>=` → `>` 킬) — cap=2 면 **3번째** 종목에서 task 0.

    비교가 `>` 로 변조되면 3번째가 통과해 client.calls 가 3 이 된다.
    """
    gate = _setup(monkeypatch)
    caplog.set_level(logging.INFO, logger=_LOGGER)
    client = _resp(_GOOD_JSON)
    _wire(gate, monkeypatch, client)
    created = _tasks_created(monkeypatch, gate)
    params = dict(_PARAMS, llm_gate_daily_call_cap=2)
    for tk in ("005930", "000660", "035720"):
        _observe(gate, ticker=tk, params_snapshot=params)
    await _drain()
    assert len(created) == 2, f"cap=2 인데 task {len(created)}"
    assert len(client.calls) == 2


@freeze_time(_UTC_090442)
async def test_c7_2_cap_marker_is_warning_once_per_strategy(monkeypatch, caplog) -> None:
    """C7/§7.1 ④ — cap 도달은 `[llm_gate_daily_cap]` **WARNING 1회/전략/일**."""
    gate = _setup(monkeypatch)
    caplog.set_level(logging.INFO, logger=_LOGGER)
    _wire(gate, monkeypatch, _resp(_GOOD_JSON))
    params = dict(_PARAMS, llm_gate_daily_call_cap=1)
    for tk in ("005930", "000660", "035720"):
        _observe(gate, ticker=tk, params_snapshot=params)
    await _drain()

    caps = _lines(caplog, gate.MARKER_DAILY_CAP)
    assert len(caps) == 1, f"cap 마커가 1행이 아니다: {caps}"
    recs = [r for r in caplog.records
            if r.name == _LOGGER and r.getMessage().startswith(gate.MARKER_DAILY_CAP)]
    assert recs[0].levelno == logging.WARNING


@freeze_time(_UTC_090442)
async def test_c7_3_cap_is_per_strategy(monkeypatch, caplog) -> None:
    """C7 — cap 은 **전략별**이다. VB 가 소진돼도 LTV 는 자기 예산을 쓴다."""
    gate = _setup(monkeypatch)
    caplog.set_level(logging.INFO, logger=_LOGGER)
    client = _resp(_GOOD_JSON)
    _wire(gate, monkeypatch, client)
    params = dict(_PARAMS, llm_gate_daily_call_cap=1)
    _observe(gate, strategy_id=_VB, ticker="005930", params_snapshot=params)
    _observe(gate, strategy_id=_VB, ticker="000660", params_snapshot=params)
    _observe(gate, strategy_id=_LTV, ticker="035720", params_snapshot=params)
    await _drain()
    assert len(client.calls) == 2


@freeze_time(_UTC_090442)
async def test_c7_4_cap_absent_key_means_zero(monkeypatch, caplog) -> None:
    """C7/§6.2 — `llm_gate_daily_call_cap` **키 부재 = 0 = 호출 안 함**.

    이 기능은 *매수를 막는 통제*가 아니라 **돈을 쓰는 기능**이다. "설정이 없으면
    안 한다" 가 옳다(cycle272 `open_price_scope_mode` 의 부재=enforce 와 **반대**).
    """
    gate = _setup(monkeypatch)
    caplog.set_level(logging.INFO, logger=_LOGGER)
    client = _resp(_GOOD_JSON)
    _wire(gate, monkeypatch, client)
    created = _tasks_created(monkeypatch, gate)
    params = {k: v for k, v in _PARAMS.items() if k != "llm_gate_daily_call_cap"}
    _observe(gate, params_snapshot=params)
    await _drain()
    assert created == [] and client.calls == []


@pytest.mark.parametrize(
    "raw", [None, "", "abc", -1, float("inf"), float("nan"), 999],
    ids=["none", "empty", "garbage", "negative", "inf", "nan", "over-200"],
)
@freeze_time(_UTC_090442)
async def test_c7_5_cap_clamp_grid(monkeypatch, caplog, raw) -> None:
    """C7/§6.2 — cap 은 `[0, 200]` 클램프, 파싱 실패는 **0**(= 호출 안 함).

    `int(float("inf"))` 는 `OverflowError` 라 좁은 튜플로는 못 잡는다 —
    여기서도 `except Exception` 이 계약이다(cycle262 HIGH 계열).
    """
    gate = _setup(monkeypatch)
    caplog.set_level(logging.INFO, logger=_LOGGER)
    client = _resp(_GOOD_JSON)
    _wire(gate, monkeypatch, client)
    _observe(gate, params_snapshot=dict(_PARAMS, llm_gate_daily_call_cap=raw))
    await _drain()
    expected = 1 if raw == 999 else 0
    assert len(client.calls) == expected


# ===========================================================================
# C8 — 세마포어 2
# ===========================================================================
@freeze_time(_UTC_090442)
async def test_c8_1_at_most_two_inflight_calls(monkeypatch, caplog) -> None:
    """C8 (뮤테이션 '세마포어 무제한' 킬) — 10 신호 동시 발사 시 진행 중 콜 ≤ 2.

    09:01:30 보류 해제 순간 다수 종목이 동시에 돌파한다(09-08 실측 09:01:34 /
    09:01:42). 무제한이면 OpenAI 커넥션이 순간적으로 10개가 된다.
    """
    gate = _setup(monkeypatch)
    caplog.set_level(logging.INFO, logger=_LOGGER)
    hold = asyncio.Event()
    client = FakeClient(gate=hold)
    _wire(gate, monkeypatch, client)
    params = dict(_PARAMS, llm_gate_daily_call_cap=50)
    for i in range(10):
        _observe(gate, ticker=f"00{i:04d}", params_snapshot=params)
    await _spin(120)
    assert client.max_inflight <= 2, f"동시 콜 {client.max_inflight} > 2"
    assert client.max_inflight >= 2, "세마포어 슬롯이 채워지지 않았다(테스트 무의미)"
    hold.set()
    await _drain()
    assert len(client.calls) == 10


# ===========================================================================
# C11 — 일봉 캐시 `(ticker, KST date)`
# ===========================================================================
@freeze_time(_UTC_090442)
async def test_c11_1_bars_fetched_once_per_ticker_per_day(monkeypatch, caplog) -> None:
    """C11 — 같은 종목을 두 전략이 평가해도 DB 조회는 **1회**.

    일봉은 하루 안에 변하지 않는다. 종목당 DB 1회가 계약이다(§3.1).
    """
    gate = _setup(monkeypatch)
    caplog.set_level(logging.INFO, logger=_LOGGER)
    spy = _wire(gate, monkeypatch, _resp(_GOOD_JSON))
    _observe(gate, strategy_id=_VB)
    await _drain()
    _observe(gate, strategy_id=_LTV)
    await _drain()
    assert len(spy.calls) == 1, f"일봉 조회가 {len(spy.calls)}회"


async def test_c11_2_cache_key_includes_kst_date(monkeypatch, caplog) -> None:
    """C11 — 날짜가 바뀌면 캐시를 버리고 다시 읽는다(어제 봉으로 오늘 판정 금지)."""
    gate = _setup(monkeypatch)
    caplog.set_level(logging.INFO, logger=_LOGGER)
    spy = _wire(gate, monkeypatch, _resp(_GOOD_JSON))
    with freeze_time(_UTC_090442):
        _observe(gate, now_kst=_NOW)
        await _drain()
    with freeze_time(_UTC_NEXT_090442):
        _observe(gate, now_kst=_NOW_NEXT)
        await _drain()
    assert len(spy.calls) == 2


@freeze_time(_UTC_090442)
async def test_c11_3_fetch_window_is_60_bars(monkeypatch, caplog) -> None:
    """C11/§3.2 — 60봉을 읽는다(MACD 26일 EMA warm-up 이 그 유일한 이유) · `min_required=30`.

    ⚠️ `min_required > days` 조합은 어떤 전략에서도 성립할 수 없다(§8.5 VB k_period=15
    결함) — 여기서는 `30 <= 60` 이라 그 함정에 걸리지 않는다.
    """
    gate = _setup(monkeypatch)
    caplog.set_level(logging.INFO, logger=_LOGGER)
    spy = _wire(gate, monkeypatch, _resp(_GOOD_JSON))
    _observe(gate)
    await _drain()
    ticker, days, min_required = spy.calls[0]
    assert ticker == _TICKER
    assert days == 60
    assert min_required == 30


@freeze_time(_UTC_090442)
async def test_c11_4_today_bar_is_discarded(monkeypatch, caplog) -> None:
    """C11/§3.4 — `bas_dd == 오늘(KST)` 인 봉은 **버린다**(cycle263 껍데기 봉 계열).

    장중 부분봉이 `[0]` 에 앉으면 '전일봉' 계약이 깨지고 전일 레인지·갭이 오염된다.
    """
    gate = _setup(monkeypatch)
    caplog.set_level(logging.INFO, logger=_LOGGER)
    rows = _bars(60, include_today=True)
    assert rows[0]["stck_bsop_date"] == _NOW.date().strftime("%Y%m%d")
    _wire(gate, monkeypatch, _resp(_GOOD_JSON), _BarsSpy(rows=rows))
    _observe(gate)
    await _drain()
    line = _lines(caplog, gate.MARKER_SCORE)[0]
    assert _field(line, "bars") == "59", "오늘 봉이 버려지지 않았다"


@freeze_time(_UTC_090442)
async def test_c11_5_cache_is_bounded_at_400(monkeypatch) -> None:
    """C11/§5.3 — 캐시 상한 **400 종목**. 무한 성장은 장기 실행 프로세스의 누수다."""
    gate = _setup(monkeypatch)
    mod = gate
    assert mod._BARS_CACHE_MAX == 400
    spy = _BarsSpy()
    monkeypatch.setattr(mod, "get_recent_daily_normalized", spy)
    for i in range(401):
        await mod._bars_cached(f"{i:06d}", now_kst=_NOW)
    assert len(mod._bars_cache) <= 400, f"캐시 {len(mod._bars_cache)} > 400"


async def test_c11_6_stale_date_entries_are_purged_wholesale_on_day_change(monkeypatch, caplog) -> None:
    """검증 파인딩 #8 (LOW) — §5.3 계약 = "(ticker, KST date) 키 dict, 날짜
    바뀌면 **통째 폐기**". 종전 구현은 날짜를 키에만 넣고 옛 날짜 항목을 지우지
    않아(정확성 영향은 없었지만 — 옛 날짜 키는 다시 조회되지 않는다) 다중
    날짜가 무한정 누적됐다. `test_c11_2` 는 재조회(2회)만 보고 옛 항목의 실제
    폐기는 보지 않았다 — 이 테스트는 `_bars_cache` 내부를 직접 들여다본다."""
    gate = _setup(monkeypatch)
    caplog.set_level(logging.INFO, logger=_LOGGER)
    _wire(gate, monkeypatch, _resp(_GOOD_JSON))
    with freeze_time(_UTC_090442):
        _observe(gate, now_kst=_NOW)
        await _drain()
    old_day = _NOW.strftime("%Y%m%d")
    assert any(k[1] == old_day for k in gate._bars_cache), "첫 날 캐시가 채워지지 않았다"

    with freeze_time(_UTC_NEXT_090442):
        _observe(gate, now_kst=_NOW_NEXT)
        await _drain()
    new_day = _NOW_NEXT.strftime("%Y%m%d")
    assert not any(k[1] == old_day for k in gate._bars_cache), (
        f"옛 날짜({old_day}) 캐시 항목이 폐기되지 않았다: {list(gate._bars_cache)}"
    )
    assert all(k[1] == new_day for k in gate._bars_cache)


# ===========================================================================
# §7.1 ③ — `[llm_gate_config]` 카나리아
# ===========================================================================
@freeze_time(_UTC_090442)
async def test_m3_1_config_marker_once_per_strategy_value_day(monkeypatch, caplog) -> None:
    """§7.1 ③ — 적용값 카나리아 1회/(전략, mode, min_score)/일 + 필드 7종."""
    gate = _setup(monkeypatch)
    caplog.set_level(logging.INFO, logger=_LOGGER)
    _wire(gate, monkeypatch, _resp(_GOOD_JSON))
    _observe(gate)
    _observe(gate, ticker="000660")
    await _drain()

    cfg = _lines(caplog, gate.MARKER_CONFIG)
    assert len(cfg) == 1, f"config 카나리아가 1행이 아니다: {cfg}"
    for name in ("strategy", "mode", "min_score", "daily_cap", "timeout_s", "model", "src"):
        _field(cfg[0], name)
    assert _field(cfg[0], "mode") == "shadow"
    assert _field(cfg[0], "src") in {"default", "override"}


@freeze_time(_UTC_090442)
async def test_m3_2_config_marker_refires_when_value_changes(monkeypatch, caplog) -> None:
    """§7.1 ③ — **값이 키다.** 장중 PUT 롤백이 같은 날 새 행을 내야 롤백이 먹었는지 보인다.

    ⚠️ 그래서 `mode="off"` 로 내린 뒤에도 카나리아는 **한 행 더** 나와야 한다 —
    자문 §5.2 의 "mode == off → 즉시 return" 은 그 카나리아 **뒤**의 순서다
    (관측 없는 롤백은 확인할 방법이 없고, 그러면 카나리아의 존재 이유가 사라진다).
    """
    gate = _setup(monkeypatch)
    caplog.set_level(logging.INFO, logger=_LOGGER)
    _wire(gate, monkeypatch, _resp(_GOOD_JSON))
    _observe(gate)
    await _drain()
    _observe(gate, ticker="000660", params_snapshot=dict(_PARAMS, llm_gate_mode="off"))
    await _drain()

    modes = [_field(l, "mode") for l in _lines(caplog, gate.MARKER_CONFIG)]
    assert modes == ["shadow", "off"], f"롤백이 카나리아에 보이지 않는다: {modes}"


@freeze_time(_UTC_090442)
async def test_m3_3_cost_usd_uses_luna_unit_price(monkeypatch, caplog) -> None:
    """§8.3 — `gpt-5.6-luna` 단가(입력 $1.00/1M · 출력 $6.00/1M)로 콜당 비용을 남긴다.

    검산(09-10 실측 행): `in 7302 · out 1572 → 0.016734` 와 정확히 일치하는 식이다.
    여기서는 in 1000 / out 100 ⇒ 0.001 + 0.0006 = **0.001600**.
    """
    gate = _setup(monkeypatch)
    caplog.set_level(logging.INFO, logger=_LOGGER)
    _wire(gate, monkeypatch, _resp(_GOOD_JSON, in_tok=1000, out_tok=100))
    _observe(gate)
    await _drain()
    line = _lines(caplog, gate.MARKER_SCORE)[0]
    assert _field(line, "tokens_in") == "1000"
    assert _field(line, "tokens_out") == "100"
    assert float(_field(line, "cost_usd")) == pytest.approx(0.0016, abs=1e-9)


@freeze_time(_UTC_090442)
async def test_m3_4_missing_usage_does_not_break_the_line(monkeypatch, caplog) -> None:
    """§7.1 ① — `usage` 가 없는 응답에도 점수 행은 나온다(토큰 0 으로 기록)."""
    gate = _setup(monkeypatch)
    caplog.set_level(logging.INFO, logger=_LOGGER)
    client = FakeClient()

    async def _no_usage(**kwargs):
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=_GOOD_JSON))],
        )

    client._create = _no_usage
    _wire(gate, monkeypatch, client)
    _observe(gate)
    await _drain()
    assert len(_lines(caplog, gate.MARKER_SCORE)) == 1


@freeze_time(_UTC_090442)
async def test_m3_5_unregistered_model_cost_usd_is_negative_one(monkeypatch, caplog) -> None:
    """검증 파인딩 #9 (LOW) — 단가 표(`log_analysis_engine._OPENAI_PRICING`,
    정본 하나뿐)에 없는 모델은 비용을 하드코딩된 잘못된 단가로 조용히 찍지
    않고 **`-1.0`**(모른다)으로 정직하게 남긴다. 모델을 바꾸면 그 단가 표
    하나만 갱신하면 되고, 이 leaf 가 별도 사본을 들고 있지 않아야 한다."""
    gate = _setup(monkeypatch)
    caplog.set_level(logging.INFO, logger=_LOGGER)
    monkeypatch.setattr(
        gate, "settings",
        SimpleNamespace(openai_api_key="test-key", openai_buy_gate_model="unregistered-model-xyz"),
    )
    _wire(gate, monkeypatch, _resp(_GOOD_JSON))
    _observe(gate)
    await _drain()
    line = _lines(caplog, gate.MARKER_SCORE)[0]
    assert _field(line, "model") == "unregistered-model-xyz"
    assert float(_field(line, "cost_usd")) == pytest.approx(-1.0, abs=1e-9)


# ===========================================================================
# §4.4 — 호출 파라미터
# ===========================================================================
@freeze_time(_UTC_090442)
async def test_m4_1_call_uses_json_object_and_no_temperature(monkeypatch, caplog) -> None:
    """§4.4 — `response_format=json_object` · `temperature` **미지정** · `max_retries` 0.

    gpt-5 계열은 1 이외 `temperature` 를 거부할 수 있고, 거부는 fail-open 으로
    흡수되지만 그러면 게이트가 **조용히 죽는다**(§11 Q10).
    """
    gate = _setup(monkeypatch)
    caplog.set_level(logging.INFO, logger=_LOGGER)
    client = _resp(_GOOD_JSON)
    _wire(gate, monkeypatch, client)
    _observe(gate)
    await _drain()
    kw = client.calls[0]
    assert kw["response_format"] == {"type": "json_object"}
    assert "temperature" not in kw, "gpt-5 계열은 temperature 를 거부할 수 있다(§4.4)"
    assert kw["model"] == "gpt-5.6-luna"
    assert isinstance(kw["messages"], list) and len(kw["messages"]) == 2


@freeze_time(_UTC_090442)
async def test_m4_2_call_caps_completion_tokens(monkeypatch, caplog) -> None:
    """§4.4 — 출력 상한 400. ⚠️ `max_tokens` 는 gpt-5 계열에서 거부될 수 있다."""
    gate = _setup(monkeypatch)
    caplog.set_level(logging.INFO, logger=_LOGGER)
    client = _resp(_GOOD_JSON)
    _wire(gate, monkeypatch, client)
    _observe(gate)
    await _drain()
    kw = client.calls[0]
    assert kw.get("max_completion_tokens") == 400
    assert "max_tokens" not in kw


@freeze_time(_UTC_090442)
async def test_m4_3_real_observe_signal_path_produces_a_non_empty_payload(monkeypatch, caplog) -> None:
    """검증 파인딩 #1 (CRITICAL) — **생산자 출력**(픽스처 payload 가 아니라
    실제 `observe_signal` → `_evaluate` → `build_messages` 경로가 만든 것)을
    파싱해 `snapshot`/`technicals`/`recent_bars_desc` 가 실제로 채워졌는지
    확인한다. 종전 결함은 `payload["now_kst"]`(datetime)가 snapshot 스프레드로
    새 `json.dumps` 가 TypeError, 그 예외를 `build_messages` 가 조용히
    `"{}"` 로 삼켜 **운영의 모든 LLM 호출이 빈 페이로드를 보내면서도** 이
    파일의 기존 테스트(`len(kw["messages"]) == 2` 만 보고 내용은 안 봤다)를
    전부 초록으로 통과시켰다 — 이 테스트는 내용을 본다.
    """
    gate = _setup(monkeypatch)
    caplog.set_level(logging.INFO, logger=_LOGGER)
    from src.engine import scanner
    monkeypatch.setattr(scanner, "ticker_prices", {_TICKER: {"current_price": 80900}})
    client = _resp(_GOOD_JSON)
    _wire(gate, monkeypatch, client)
    _observe(gate)
    await _drain()

    assert len(client.calls) == 1, "실제 경로가 LLM 을 호출하지 않았다(조용한 실패 회귀?)"
    content = client.calls[0]["messages"][1]["content"]
    obj = json.loads(content[content.index("{"):])  # preamble 뒤 JSON 블록

    assert obj["snapshot"], "snapshot 이 비어 있다 — '{}' 조용한 폴백 회귀"
    assert obj["technicals"], "technicals 가 비어 있다"
    assert len(obj["recent_bars_desc"]) == 30
    for key in (
        "prdy_ctrt_pct", "intraday_ctrt_pct", "acml_vol_shares",
        "vol_ratio_vs_avg20", "vol_ratio_time_norm",
    ):
        assert key in obj["snapshot"], f"실제 생산자 payload 에 `{key}` 부재(검증 파인딩 #2)"
    for leaked in ("min_score", "mode", "model", "daily_cap", "timeout_s", "now_kst"):
        assert leaked not in obj["snapshot"], f"운영 설정값 `{leaked}` 가 실제 경로에서 샜다"

    # 실패 행이 함께 남지 않았어야 한다 — 성공과 실패가 동시에 찍히면 그 자체가 결함.
    assert _lines(caplog, gate.MARKER_FAILED) == []


# ===========================================================================
# C12 — 관측 never-raise (cap · 로거 · 페이로드 조립)
# ===========================================================================
@freeze_time(_UTC_090442)
def test_c12_1_cap_explosion_is_absorbed_with_trace(monkeypatch, caplog) -> None:
    """C12 (HIGH) — 래치 cap 이 터져도 `observe_signal` 은 던지지 않고 흔적을 남긴다.

    무흔적 `pass` 는 금지다(cycle258 카드 #5) — 관측기가 죽어도 아무도 모르면
    이 마커의 **결측이 '신호가 없었다' 로 오독된다**.
    """
    gate = _setup(monkeypatch)
    seen: list = []
    monkeypatch.setattr(gate, "trace_observer_failure", lambda *a, **k: seen.append(a))

    class _Boom:
        def should_emit(self, *a, **k):
            raise RuntimeError("cap dead")

        def mark_emitted(self, *a, **k):
            raise RuntimeError("cap dead")

    monkeypatch.setattr(gate, "_latch", _Boom())
    _observe(gate)
    assert _absorbed(seen, caplog), "실패 흔적(`trace_observer_failure`)이 남지 않았다"


@freeze_time(_UTC_090442)
def test_c12_2_logger_explosion_is_absorbed(monkeypatch, caplog) -> None:
    """C12 — 로거가 터져도 `observe_signal` 은 None 을 돌려준다."""
    gate = _setup(monkeypatch)
    seen: list = []
    monkeypatch.setattr(gate, "trace_observer_failure", lambda *a, **k: seen.append(a))
    monkeypatch.setattr(
        gate.logger, "info",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("log dead")),
    )
    _observe(gate)
    assert _absorbed(seen, caplog)


@freeze_time(_UTC_090442)
async def test_c12_3_create_task_explosion_is_absorbed(monkeypatch, caplog) -> None:
    """C12 — `create_task` 자체가 터져도 예외가 매매 경로로 새지 않는다.

    **비동기 테스트다.** 루프가 없는 동기 컨텍스트에서는 `observe_signal` 이
    `create_task` 에 도달하기 전에 조용히 return 하므로(§5.2, `test_c12_5`) 이
    분기가 검증되지 않는다.
    """
    gate = _setup(monkeypatch)
    seen: list = []
    monkeypatch.setattr(gate, "trace_observer_failure", lambda *a, **k: seen.append(a))
    monkeypatch.setattr(
        asyncio, "create_task",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("task refused")),
    )
    _observe(gate)
    assert _absorbed(seen, caplog)


@freeze_time(_UTC_090442)
def test_c12_4_hostile_params_object_is_absorbed(monkeypatch) -> None:
    """C12 — `params_snapshot.get` 이 던져도 예외가 밖으로 나가지 않는다.

    흔적 경로는 강제하지 않는다 — 읽기 헬퍼가 자체 fail-open 으로 흡수해 `off` 로
    낙하하는 구현도 계약 안이다(§6.2 "파싱 실패 → 기본값"). 여기서 지키는 것은
    **never-raise** 하나다(`_observe` 가 None 을 돌려주는 것으로 확인).
    """
    gate = _setup(monkeypatch)

    class _Hostile(dict):
        def get(self, *a, **k):
            raise RuntimeError("params dead")

    _observe(gate, params_snapshot=_Hostile())


def test_c12_5_no_running_loop_is_silent(monkeypatch) -> None:
    """C12/§5.2 — 실행 중 루프가 없으면(테스트·CLI) 조용히 return 한다. 예외 0."""
    gate = _setup(monkeypatch)
    _wire(gate, monkeypatch, _resp(_GOOD_JSON))
    with freeze_time(_UTC_090442):
        _observe(gate)   # 동기 컨텍스트 = 루프 없음


@freeze_time(_UTC_090442)
async def test_c12_6_build_messages_explosion_is_absorbed(monkeypatch, caplog) -> None:
    """C12 — 페이로드 조립(`build_messages`, json.dumps 포함)이 터져도 실패 1행만 남는다.

    검증 파인딩 #10 (LOW) — 이 실패는 **`reason=payload_error`** 로만 분류된다.
    LLM 출력 검증 실패(`schema_error`)와 같은 어휘로 뭉개면 20:10 리포트가
    "우리 코드가 페이로드를 못 만든다"와 "모델이 이상한 걸 준다"를 구별할 수
    없다. 그리고 블로커 #1(now_kst 가 snapshot 으로 새던 결함)이 **만약** 이
    경로를 탔다면 적어도 실패 행 1건은 남았을 것이다 — 종전 구현은 이 예외
    자체를 `"{}"` 로 조용히 삼켜 실패 행조차 남기지 않았다.
    """
    gate = _setup(monkeypatch)
    caplog.set_level(logging.INFO, logger=_LOGGER)
    _wire(gate, monkeypatch, _resp(_GOOD_JSON))
    monkeypatch.setattr(
        gate, "build_messages",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("dumps dead")),
    )
    _observe(gate)
    await _drain()
    failed = _lines(caplog, gate.MARKER_FAILED)
    assert len(failed) == 1
    assert _field(failed[0], "reason") == "payload_error"


# ===========================================================================
# C9 (leaf 측) — mode 격자. `enforce` 는 이 사이클에 **미구현** ⇒ off 낙하.
# ===========================================================================
_MODE_OFF_GRID = [
    pytest.param("enforce", id="enforce-not-implemented"),
    pytest.param("ENFORCE", id="ENFORCE-uppercase"),
    pytest.param("", id="empty-string"),
    pytest.param(None, id="none"),
    pytest.param(123, id="int-123"),
    pytest.param("off", id="explicit-off"),
    pytest.param("nonsense", id="unknown-value"),
]


@pytest.mark.parametrize("raw", _MODE_OFF_GRID)
@freeze_time(_UTC_090442)
async def test_c9_1_leaf_mode_falls_back_to_off(monkeypatch, caplog, raw) -> None:
    """C9 (HIGH) — `shadow` 외 모든 값은 `off` 로 낙하 ⇒ `create_task` **0건**.

    `enforce` 를 포함한다 — 이 사이클에 enforce 는 **구현되지 않았고**, 미구현
    모드를 DB 에 넣었을 때 조용히 shadow 로 동작하면 그것이 곧 무허가 행위 변경이다.
    """
    gate = _setup(monkeypatch)
    caplog.set_level(logging.INFO, logger=_LOGGER)
    client = _resp(_GOOD_JSON)
    _wire(gate, monkeypatch, client)
    created = _tasks_created(monkeypatch, gate)
    _observe(gate, params_snapshot=dict(_PARAMS, llm_gate_mode=raw))
    await _drain()
    assert created == [], f"mode={raw!r} 인데 task 가 생성됐다"
    assert client.calls == []


@freeze_time(_UTC_090442)
async def test_c9_2_mode_absent_key_means_off(monkeypatch, caplog) -> None:
    """C9/§6.2 — `llm_gate_mode` **키 부재 = off**(돈을 쓰는 기능은 설정 없으면 안 한다)."""
    gate = _setup(monkeypatch)
    caplog.set_level(logging.INFO, logger=_LOGGER)
    client = _resp(_GOOD_JSON)
    _wire(gate, monkeypatch, client)
    params = {k: v for k, v in _PARAMS.items() if k != "llm_gate_mode"}
    _observe(gate, params_snapshot=params)
    await _drain()
    assert client.calls == []


@freeze_time(_UTC_090442)
async def test_c9_3_trailing_space_shadow_is_accepted(monkeypatch, caplog) -> None:
    """C9 — `"shadow "`(뒤 공백)는 **정상 shadow** 로 읽는다(대소문자·공백 정규화).

    DB/PUT 로 손입력되는 값이라 공백 한 칸이 게이트를 통째로 끄면 안 된다 —
    `"ENFORCE"` 가 off 로 낙하하는 것과 정규화 규칙은 **같고**, 낙하 여부만 다르다.
    """
    gate = _setup(monkeypatch)
    caplog.set_level(logging.INFO, logger=_LOGGER)
    client = _resp(_GOOD_JSON)
    _wire(gate, monkeypatch, client)
    _observe(gate, params_snapshot=dict(_PARAMS, llm_gate_mode="shadow "))
    await _drain()
    assert len(client.calls) == 1


@pytest.mark.parametrize(
    "raw,expected",
    [(None, 70), ("", 70), ("abc", 70), (0, 70), (101, 70), (55, 55), ("55", 55)],
    ids=["none", "empty", "garbage", "zero", "over-100", "int-55", "str-55"],
)
@freeze_time(_UTC_090442)
async def test_c9_4_min_score_clamp_grid(monkeypatch, caplog, raw, expected) -> None:
    """C9/§6.2 — `llm_gate_min_score` 는 `[1,100]`, 파싱 실패·범위 밖 → **70**."""
    gate = _setup(monkeypatch)
    caplog.set_level(logging.INFO, logger=_LOGGER)
    _wire(gate, monkeypatch, _resp(_GOOD_JSON))
    _observe(gate, params_snapshot=dict(_PARAMS, llm_gate_min_score=raw))
    await _drain()
    assert _field(_lines(caplog, gate.MARKER_SCORE)[0], "min_score") == str(expected)


@pytest.mark.parametrize(
    "raw,expected",
    [(None, 20), ("abc", 20), (0, 1), (999, 60), (5, 5), (float("inf"), 20)],
    ids=["none", "garbage", "zero-clamps-to-1", "over-60", "int-5", "inf"],
)
@freeze_time(_UTC_090442)
async def test_c9_5_timeout_clamp_grid(monkeypatch, caplog, raw, expected) -> None:
    """C9/§6.2 — `llm_gate_timeout_secs` 는 `[1,60]`, 파싱 실패 → **20**.

    하한이 1 인 이유 = 0 이면 모든 콜이 즉시 타임아웃돼 게이트가 조용히 전멸한다.
    """
    gate = _setup(monkeypatch)
    caplog.set_level(logging.INFO, logger=_LOGGER)
    seen: list = []
    real_wait_for = asyncio.wait_for

    async def _spy(aw, timeout=None):
        seen.append(timeout)
        return await real_wait_for(aw, timeout)

    monkeypatch.setattr(asyncio, "wait_for", _spy)
    _wire(gate, monkeypatch, _resp(_GOOD_JSON))
    _observe(gate, params_snapshot=dict(_PARAMS, llm_gate_timeout_secs=raw))
    await _drain()
    assert expected in seen, f"적용 타임아웃 {seen} 에 {expected} 없음"


# ===========================================================================
# 자원 위생 — task 참조 보존
# ===========================================================================
@freeze_time(_UTC_090442)
async def test_c8_2_task_reference_is_held_until_done(monkeypatch, caplog) -> None:
    """C8/§5.4 — 전역 task set 이 강참조를 들고 있다가 완료 시 discard 한다.

    asyncio 는 task 참조가 사라지면 GC 한다 — 참조를 안 들면 관측이 무작위로 증발한다.
    """
    gate = _setup(monkeypatch)
    caplog.set_level(logging.INFO, logger=_LOGGER)
    hold = asyncio.Event()
    _wire(gate, monkeypatch, FakeClient(gate=hold))
    _observe(gate)
    await _spin()
    assert len(gate._tasks) == 1, "진행 중 task 의 강참조가 없다"
    hold.set()
    await _drain()
    assert len(gate._tasks) == 0, "완료 task 가 set 에서 제거되지 않았다(누수)"
