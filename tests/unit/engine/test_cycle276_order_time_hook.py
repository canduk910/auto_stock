"""cycle276 Red — 주문 시점 AI 매수평가: 훅 호출부(행위 동등) + leaf `observe_order` + DB 기록.

명세 = `_workspace/red/cycle276_order_time_llm_eval_spec.md` §1-A C3 · §1-B C17~C30 · §6 · §7.
브리프 = `scratchpad/cycle276_brief.md` §3 설계 결정 1·3·4·9.

**Red 단계 — 테스트만. `src/` 미변경.** Green = backend-dev.

## 이 파일이 고정하는 Green 계약(seam 포함)

| 이름 | 계약 |
|---|---|
| `llm_buy_gate.observe_order(**kw) -> None` | 동기·never-raise·반환 항상 None. **키워드 전용** |
| `llm_buy_gate._evaluate(payload)` | async 본체. **모듈 전역 이름** = 이 파일의 payload 캡처 seam |
| `llm_buy_gate._persist_evaluation(payload, outcome)` | async. `_evaluate` 안 **단 1곳**에서 호출 |
| `llm_buy_gate._board_by_clock(order_kst)` | 시계 파생 보드(`session` 불참조) |
| `llm_buy_gate._prompt_version()` / `_feature_version()` | 12자리 hex 또는 `""`(fail-open) |
| `llm_buy_gate._get_client` / `get_recent_daily_normalized` / `build_messages` / `settings` | 모듈 전역 monkeypatch seam(cycle274 승계) |
| `src.db.llm_buy_evaluations.upsert_evaluation(**kw)` | leaf 가 **함수 내 지연 import** 로 부른다 |
| `MARKER_SCORE/FAILED/CONFIG/DAILY_CAP/PERSIST` | `[llm_buy_score]`·`[llm_buy_score_failed]`·`[llm_gate_config]`·`[llm_gate_daily_cap]`·`[llm_eval_persist]` |

`observe_signal`(cycle274) 은 **삭제**된다 — 이름이 남아 있으면 전략 원복이 미완이라는 뜻이다.

## OpenAI 실호출 금지

네트워크를 타지 않는다. 클라이언트 seam 은 모듈 전역 `_get_client()` 하나이고 모든 테스트가
그것을 fake 로 갈아끼운다. 시간은 `freeze_time` 으로 고정하고 `_monotonic` **이름만**
monkeypatch 한다(전역 `time.monotonic` 패치 금지 — cycle274 파인딩 #4).

## caplog 규약

마커는 `[llm_gate_daily_cap]` 만 WARNING 이고 나머지는 INFO 라
`caplog.set_level(logging.INFO, logger=...)` 로 **로거를 명시**한다 — CI 루트 로거는 DEBUG 라
무한정 세면 `observer_trace` 의 debug 흔적까지 잡힌다(`feedback_caplog_debug_level`).

## 모듈 부재 정책

`src.db.llm_buy_evaluations` 는 아직 없다. `pytest.importorskip` 을 쓰지 않는다 — skip 은
Red 가 아니다. 각 테스트 본문에서 `importlib` 로 열어 `ModuleNotFoundError` 로 **정직하게
FAILED** 가 되게 한다.
"""

from __future__ import annotations

import asyncio
import ast
import importlib
import inspect
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from itertools import count
from pathlib import Path
from types import SimpleNamespace

import pytest
from freezegun import freeze_time

from src.api.base import KisApiError
from src.engine.order_engine import OrderEngine
from src.engine.strategies.momentum import MomentumStrategy
from src.engine.strategy_base import StrategyConfig
from src.engine.strategy_registry import StrategyRegistry
from src.models.balance import BuyableInfo
from src.models.order import OrderResult, OrderSide

pytestmark = pytest.mark.unit

KST = timezone(timedelta(hours=9))

_ROOT = Path(__file__).resolve().parents[3]
_LEAF_PATH = _ROOT / "src" / "engine" / "llm_buy_gate.py"

_MOD = "src.engine.llm_buy_gate"
_LOGGER = "src.engine.llm_buy_gate"
_DB_MOD = "src.db.llm_buy_evaluations"

_VB = "volatility_breakout"
_LTV = "long_tail_volatility"
_TICKER = "005930"
_ORDER_NO = "0000123456"
_ORDER_NO2 = "0000123457"

# KST 2026-09-11(금) 09:04:42 == UTC 2026-09-11 00:04:42
_NOW = datetime(2026, 9, 11, 9, 4, 42, tzinfo=KST)
_UTC_090442 = "2026-09-11 00:04:42"

_PARAMS = {
    "llm_gate_mode": "shadow",
    "llm_gate_min_score": 70,
    "llm_gate_daily_call_cap": 20,
    "llm_gate_timeout_secs": 20,
}

_GOOD_JSON = (
    '{"score": 82, "rationale": "돌파 초과 12.4bp, 거래량 1.8배로 뒷받침",'
    ' "key_risks": ["되돌림", "거래대금 감소"], "invalidations": ["목표가 이탈"]}'
)

_MARKERS = (
    "[llm_buy_score]",
    "[llm_buy_score_failed]",
    "[llm_gate_config]",
    "[llm_gate_daily_cap]",
    "[llm_eval_persist]",
)

_FAILURE_REASONS_10 = (
    "timeout", "api_error", "parse_error", "schema_error",
    "no_bars", "no_key", "cap_exceeded", "disabled_model",
    "payload_error",
    # cycle276 후속 A-1 — 추론 토큰이 출력 한도를 먹어 `content=""` 로 온 경우.
    "truncated",
)

_ACCOUNT_NO = "12345678"
_ACCOUNT_PRODUCT = "01"


# ===========================================================================
# 공통 헬퍼 — leaf
# ===========================================================================
def _g():
    return importlib.import_module(_MOD)


def _db():
    """`src.db.llm_buy_evaluations` — 부재면 `ModuleNotFoundError`(= 정직한 Red)."""
    return importlib.import_module(_DB_MOD)


class _FakeCompletions:
    def __init__(self, owner: "FakeClient") -> None:
        self._o = owner

    async def create(self, **kwargs):
        return await self._o._create(**kwargs)


class _FakeChat:
    def __init__(self, owner: "FakeClient") -> None:
        self.completions = _FakeCompletions(owner)


class FakeClient:
    """`client.chat.completions.create(**kw)` 만 흉내낸다 (네트워크 0)."""

    def __init__(self, *, content: str | None = _GOOD_JSON,
                 exc: BaseException | None = None,
                 in_tok: int = 3120, out_tok: int = 210) -> None:
        self.chat = _FakeChat(self)
        self.calls: list[dict] = []
        self.content = content
        self.exc = exc
        self.in_tok = in_tok
        self.out_tok = out_tok

    async def _create(self, **kwargs):
        self.calls.append(kwargs)
        await asyncio.sleep(0)
        if self.exc is not None:
            raise self.exc
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=self.content))],
            usage=SimpleNamespace(prompt_tokens=self.in_tok, completion_tokens=self.out_tok),
        )


def _bars(n: int = 60, *, today: date | None = None) -> list[dict]:
    base = today or _NOW.date()
    out = []
    for i in range(n):
        d = base - timedelta(days=1 + i)
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
    def __init__(self, rows: list[dict] | None = None) -> None:
        self.rows = _bars() if rows is None else rows
        self.calls: list[tuple] = []

    async def __call__(self, ticker: str, days: int, *, min_required=None):
        self.calls.append((ticker, days, min_required))
        return list(self.rows)


@pytest.fixture(autouse=True)
def _reset_gate_state():
    """leaf 상태(래치·cap·일봉 캐시) 초기화.

    ⚠️ 이 픽스처는 **절대 던지지 않는다** — 던지면 Red 가 setup ERROR 로 보고돼
    "실패한 계약" 과 "돌려보지도 못한 계약" 이 구별되지 않는다.
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
    """leaf + 기본 fake 배선(모델·키·계좌·scanner). 모듈 부재면 여기서 실패한다."""
    mod = _g()
    mod.reset_llm_buy_gate_state()
    monkeypatch.setattr(
        mod, "settings",
        SimpleNamespace(
            openai_api_key="test-key",
            openai_buy_gate_model="gpt-5.6-luna",
            kis_account_no=_ACCOUNT_NO,
            kis_account_product=_ACCOUNT_PRODUCT,
        ),
    )
    from src.engine import scanner
    monkeypatch.setattr(scanner, "ticker_prices", {})
    monkeypatch.setattr(scanner, "ticker_names", {_TICKER: "삼성전자"}, raising=False)
    return mod


def _wire(mod, monkeypatch, client: FakeClient | None, bars: _BarsSpy | None = None) -> _BarsSpy:
    spy = bars or _BarsSpy()
    monkeypatch.setattr(mod, "_get_client", lambda: client)
    monkeypatch.setattr(mod, "get_recent_daily_normalized", spy)
    return spy


def _signal(**over) -> dict:
    """`state.buy_signals` 원소 — VB/LTV 가 실제로 append 하는 키 집합."""
    s = {
        "ticker": _TICKER,
        "name": "삼성전자",
        "price": 80500,
        "target_price": 80400,
        "k": 0.5,
        "board": "main",
        "change_rate": 0.6,
        "time": "09:04:41",
    }
    s.update(over)
    return s


def _observe(mod, **over) -> None:
    """명세 §6.1 의 **최소 키워드 계약**. Green 이 인자를 더 붙이려면 기본값을 준다."""
    kw = dict(
        strategy_id=_VB,
        ticker=_TICKER,
        order_no=_ORDER_NO,
        order_kst=_NOW,
        order_price_won=80500,
        ordered_qty=3,
        order_division="MARKET",
        order_path="market",
        exchange="KRX",
        current_price_won=80500,
        budget_total_won=247_949,
        budget_remaining_after_won=32_549,
        open_positions_n=1,
        params_snapshot=dict(_PARAMS),
        buy_signals_tail=[_signal()],
    )
    kw.update(over)
    assert mod.observe_order(**kw) is None, "`observe_order` 반환은 항상 None 이어야 한다"


async def _drain(rounds: int = 400) -> None:
    for _ in range(rounds):
        others = [
            t for t in asyncio.all_tasks()
            if t is not asyncio.current_task() and not t.done()
        ]
        if not others:
            return
        await asyncio.wait(others, timeout=5)


async def _spin(rounds: int = 60) -> None:
    for _ in range(rounds):
        await asyncio.sleep(0)


def _lines(caplog, marker: str) -> list[str]:
    """레벨(INFO 이상) + 로거 + 접두 3중 한정. 실패 흔적(`observer_failed`)은 제외."""
    out = []
    for r in caplog.records:
        if r.name != _LOGGER or r.levelno < logging.INFO:
            continue
        msg = r.getMessage()
        if msg.startswith(marker) and "observer_failed" not in msg:
            out.append(msg)
    return out


def _field(line: str, name: str) -> str:
    m = re.search(rf"(?:^|\s){re.escape(name)}=(\S+)", line)
    assert m is not None, f"필드 `{name}=` 이 로그에 없다: {line!r}"
    return m.group(1)


def _tasks_created(monkeypatch) -> list:
    """`asyncio.create_task` 호출 기록 — '0건' 을 직접 센다."""
    seen: list = []
    real = asyncio.create_task

    def _spy(coro, *a, **kw):
        t = real(coro, *a, **kw)
        seen.append(t)
        return t

    monkeypatch.setattr(asyncio, "create_task", _spy)
    return seen


def _capture_payload(mod, monkeypatch) -> list[dict]:
    """`_evaluate` 를 가로채 동기 접수 단계가 만든 payload 만 본다(LLM 미발화)."""
    seen: list[dict] = []

    async def _fake_evaluate(payload):
        seen.append(payload)
        return None

    monkeypatch.setattr(mod, "_evaluate", _fake_evaluate)
    return seen


def _upsert_spy(monkeypatch) -> list[dict]:
    """`src.db.llm_buy_evaluations.upsert_evaluation` 인자 기록.

    leaf 는 이 함수를 **함수 내 지연 import** 로 부르므로, 모듈 속성을 갈아끼우면
    호출 시점에 그 fake 가 잡힌다.
    """
    db = _db()
    calls: list[dict] = []

    async def _fake(**kw):
        calls.append(kw)
        return dict(kw)

    monkeypatch.setattr(db, "upsert_evaluation", _fake)
    return calls


def _leaf_src() -> str:
    assert _LEAF_PATH.exists(), "`src/engine/llm_buy_gate.py` 가 없다"
    return _LEAF_PATH.read_text(encoding="utf-8")


# ===========================================================================
# OrderEngine 하네스 — C3(훅 호출부 행위 동등)
# ===========================================================================
@dataclass
class EnvState:
    next_order_seq: count = field(default_factory=lambda: count(1))
    place_order_error: KisApiError | None = None
    buyable_max_qty: int = 999_999


def _make_env(monkeypatch):
    """`OrderEngine` + momentum 1전략 격리 환경(cycle271 하네스 축약본)."""
    from src.engine import scanner

    monkeypatch.setattr(scanner, "ticker_names", {_TICKER: "테스트종목"})
    monkeypatch.setattr(scanner, "ticker_prev_close", {_TICKER: 20_000})
    monkeypatch.setattr(scanner, "ticker_prices", {})

    from src.engine.session import MarketBoard, session_tracker
    monkeypatch.setattr(session_tracker, "_active", frozenset({MarketBoard.MAIN}))

    registry = StrategyRegistry()
    momentum = MomentumStrategy(
        StrategyConfig(
            strategy_id="momentum", name="모멘텀", weight=1.0,
            params={"exchange": "KRX"},   # stock_master 조회 경로 진입 차단
        )
    )
    registry.register(momentum)
    registry.allocate_funds(total_asset=100_000_000)

    engine = OrderEngine(registry)
    state = EnvState()
    calls = SimpleNamespace(place_order=[], inserted=[], events=[])

    async def fake_place_order(ticker, side, quantity, price=0, **kwargs):
        calls.place_order.append(
            {"ticker": ticker, "side": side, "quantity": quantity, "price": price,
             "kwargs": kwargs}
        )
        if state.place_order_error is not None:
            err = state.place_order_error
            state.place_order_error = None
            raise err
        seq = next(state.next_order_seq)
        prefix = "BUY" if side == OrderSide.BUY else "SELL"
        return OrderResult(order_no=f"{prefix}-{seq:06d}", order_time="090501",
                           krx_org_no="00950")

    async def fake_get_buyable(ticker, price):
        return BuyableInfo(cash_available=999_000_000, max_buy_amount=999_000_000,
                           max_buy_quantity=state.buyable_max_qty)

    async def fake_insert_trade(record):
        calls.events.append(("insert", record.order_no))
        calls.inserted.append({
            "ticker": record.ticker, "order_no": record.order_no,
            "trade_type": record.trade_type.value, "status": record.status.value,
            "price": float(record.price), "quantity": record.quantity,
            "strategy": record.strategy,
        })

    async def fake_update_trade_status(*a, **kw):
        return 1

    async def fake_write_log(level, message):
        return None

    monkeypatch.setattr("src.engine.order_engine.place_order", fake_place_order)
    monkeypatch.setattr("src.engine.order_engine.get_buyable", fake_get_buyable)
    monkeypatch.setattr("src.engine.order_engine.insert_trade", fake_insert_trade)
    monkeypatch.setattr("src.engine.order_engine.update_trade_status", fake_update_trade_status)
    monkeypatch.setattr("src.engine.order_engine.write_log", fake_write_log)

    return SimpleNamespace(engine=engine, registry=registry, strategy=momentum,
                           state=state, calls=calls)


def _hook_spy(monkeypatch, env, *, boom: BaseException | None = None) -> list[dict]:
    """`llm_buy_gate.observe_order` 를 스파이로 갈아끼운다.

    `raising=False` 인 이유 = Red 시점엔 그 이름이 아직 없다. 이름이 없으면 훅도 없으므로
    스파이 호출 0건으로 **정직하게 FAILED** 가 된다.
    """
    mod = _g()
    seen: list[dict] = []

    def _spy(**kw):
        seen.append(kw)
        env.calls.events.append(("hook", kw.get("order_no")))
        if boom is not None:
            raise boom
        return None

    monkeypatch.setattr(mod, "observe_order", _spy, raising=False)
    return seen


def _snapshot(env) -> dict:
    st = env.strategy.state
    e = env.engine
    return {
        "pending_buys": set(st.pending_buys),
        "pending_buy_amounts": dict(st.pending_buy_amounts),
        "cached_buyable_at": st.cached_buyable_at,
        "order_qty": dict(e._order_qty),
        "order_strategy": dict(e._order_strategy),
        "order_ticker": dict(e._order_ticker),
        "pending_buy_orders": {k: dict(v) for k, v in e._pending_buy_orders.items()},
        "inserted": [dict(r) for r in env.calls.inserted],
    }


# ===========================================================================
# C3 — 훅이 던져도 `execute_buy` 의 관측 가능한 결과가 동일하다
# ===========================================================================
async def test_c3_1_market_path_calls_hook_once_with_order_snapshot(monkeypatch):
    """C3/§7.1 — 주 경로 주문 1건 → 훅 1회. 인자는 **그 주문의 스냅샷**이다.

    `order_no` 가 인자에 없으면 PK 가 성립하지 않는다(설계 결정 3·5).
    """
    env = _make_env(monkeypatch)
    seen = _hook_spy(monkeypatch, env)

    await env.engine.execute_buy(_TICKER, 20_000, env.strategy)

    assert len(seen) == 1, f"주 경로 훅 호출 {len(seen)}건 (기대 1)"
    kw = seen[0]
    assert kw["ticker"] == _TICKER
    assert kw["order_no"] == env.calls.inserted[0]["order_no"], (
        "훅에 넘긴 주문번호가 실제 접수된 주문번호와 다르다"
    )
    assert kw["strategy_id"] == "momentum"
    assert kw["order_price_won"] == 20_000, "주 경로 기록가 = `record_price`(현재가)"
    assert kw["ordered_qty"] == env.calls.inserted[0]["quantity"]
    assert kw["order_path"] == "market", "주 경로 라벨은 `market`(cycle271 어휘와 동일)"
    assert kw["exchange"] == "KRX"
    assert isinstance(kw["order_kst"], datetime) and kw["order_kst"].tzinfo is not None, (
        "`order_kst` 는 aware datetime — TIMESTAMPTZ 바인딩의 원천이다(C34)"
    )
    assert isinstance(kw["params_snapshot"], dict)
    assert isinstance(kw["buy_signals_tail"], list)


async def test_c3_2_market_path_hook_raising_does_not_change_outcome(monkeypatch):
    """C3 (HIGH) — 훅이 예외를 던져도 매수 결과가 **한 글자도** 다르지 않다.

    비교 대상 = 반환값 · `pending_buys` · `pending_buy_amounts` · 4매핑 ·
    `insert_trade` 인자 · `cached_buyable_at`.
    """
    env_ok = _make_env(monkeypatch)
    _hook_spy(monkeypatch, env_ok)
    assert await env_ok.engine.execute_buy(_TICKER, 20_000, env_ok.strategy) is None
    baseline = _snapshot(env_ok)

    env_boom = _make_env(monkeypatch)
    seen = _hook_spy(monkeypatch, env_boom, boom=RuntimeError("관측기 폭발"))
    assert await env_boom.engine.execute_buy(_TICKER, 20_000, env_boom.strategy) is None

    assert len(seen) == 1, "훅이 호출되지 않았다 — 배선 미이행(Red)"
    assert _snapshot(env_boom) == baseline, "훅 예외가 매수 결과를 바꿨다"
    assert env_boom.strategy.state.cached_buyable_at == 0.0, (
        "매수 접수 직후 캐시 무효화(`cached_buyable_at = 0.0`)가 사라졌다"
    )


async def test_c3_3_fallback_path_calls_hook_once_with_fallback_snapshot(monkeypatch):
    """C3/§7.2 — 시장가 거부 → 지정가 5호가 폴백 경로에서도 훅 1회.

    폴백 훅만 지우는 뮤테이션(M1)은 여기서 죽는다. 가격은 `fallback_price`,
    구분은 `LIMIT`, 경로 라벨은 `fallback` 이다 — 둘 다 LIMIT 일 수 있어
    `order_division` 만으로는 두 경로가 분리되지 않는다(자문 R3).
    """
    env = _make_env(monkeypatch)
    env.state.place_order_error = KisApiError("1", "APBK1943", "시장가매매불가 종목입니다")
    seen = _hook_spy(monkeypatch, env)

    await env.engine.execute_buy(_TICKER, 20_000, env.strategy)

    assert len(seen) == 1, f"폴백 경로 훅 호출 {len(seen)}건 (기대 1)"
    kw = seen[0]
    fallback_price = env.calls.place_order[-1]["price"]
    assert fallback_price > 20_000, "폴백은 5호가 step_up 지정가여야 한다(전제 확인)"
    assert kw["order_price_won"] == fallback_price
    assert kw["order_division"] == "LIMIT"
    assert kw["order_path"] == "fallback"
    assert kw["order_no"] == env.calls.inserted[0]["order_no"]


async def test_c3_4_fallback_hook_raising_non_kis_error_does_not_change_outcome(monkeypatch):
    """C3 (HIGH·자문 CRITICAL) — 폴백 훅이 **non-`KisApiError`** 를 던져도 결과 동일.

    폴백 훅은 `except KisApiError` 핸들러 **안**의 중첩 try 안에 있다. 흡수기를
    `except KisApiError` 로 좁히면(뮤테이션 M5) `RuntimeError` 가 그대로 올라가
    `state.pending_buys` 에 ticker 가 남는 **좀비 포지션**이 된다.
    """
    env_ok = _make_env(monkeypatch)
    env_ok.state.place_order_error = KisApiError("1", "APBK1943", "시장가매매불가 종목입니다")
    _hook_spy(monkeypatch, env_ok)
    await env_ok.engine.execute_buy(_TICKER, 20_000, env_ok.strategy)
    baseline = _snapshot(env_ok)

    env_boom = _make_env(monkeypatch)
    env_boom.state.place_order_error = KisApiError("1", "APBK1943", "시장가매매불가 종목입니다")
    seen = _hook_spy(monkeypatch, env_boom, boom=RuntimeError("관측기 폭발"))
    await env_boom.engine.execute_buy(_TICKER, 20_000, env_boom.strategy)

    assert len(seen) == 1, "폴백 훅이 호출되지 않았다 — 배선 미이행(Red)"
    assert _snapshot(env_boom) == baseline, "폴백 훅 예외가 매수 결과를 바꿨다"
    assert _TICKER in env_boom.strategy.state.pending_buys, (
        "폴백 성공 뒤에는 ticker 가 pending_buys 에 남아 있어야 한다(회귀)"
    )


async def test_c3_5_hook_fires_before_pending_insert(monkeypatch):
    """C7 — 훅은 PENDING INSERT **앞**에서 발화한다(체결통보 선행 코호트 보존).

    INSERT 뒤로 옮기면 가장 빨리 체결되는 진입이 기록에서 통째로 빠진다(뮤테이션 M2).
    """
    env = _make_env(monkeypatch)
    _hook_spy(monkeypatch, env)

    await env.engine.execute_buy(_TICKER, 20_000, env.strategy)

    kinds = [k for k, _ in env.calls.events]
    assert "hook" in kinds, "훅이 호출되지 않았다(Red)"
    assert kinds.index("hook") < kinds.index("insert"), (
        f"훅이 INSERT 뒤에 발화했다: {env.calls.events}"
    )


async def test_c3_6_sell_path_does_not_call_the_hook(monkeypatch):
    """C6 — 매도는 평가 대상이 아니다. `execute_sell` 에서 훅 0건."""
    from src.engine.strategy_base import Position, Signal

    env = _make_env(monkeypatch)
    seen = _hook_spy(monkeypatch, env)
    st = env.strategy.state
    st.positions[_TICKER] = Position(
        ticker=_TICKER, buy_price=20_000, quantity=1,
        order_no="BUY-000001", strategy_id="momentum", buy_date=_NOW.date(),
    )

    import src.db.positions as positions_mod

    async def _noop(*a, **kw):
        return None

    monkeypatch.setattr(positions_mod, "delete_position", _noop, raising=False)

    try:
        await env.engine.execute_sell(_TICKER, Signal.STOP_LOSS, "momentum")
    except Exception:
        # 매도 경로의 부수 배선(포지션 영속·구독 해제) 실패는 이 케이스의 관심사가 아니다 —
        # 재는 것은 오직 "매도 중에 훅이 발화하지 않는다" 하나다.
        pass

    assert env.calls.place_order, "매도 주문 자체가 나가지 않았다(전제 확인 실패)"
    assert seen == [], f"매도 경로에서 훅이 {len(seen)}회 호출됐다"


# ===========================================================================
# C17/C18 — `observe_order` 자체 계약
# ===========================================================================
def test_c17_1_observe_order_is_sync_and_returns_none(monkeypatch):
    """C17 — 동기 함수이고 반환은 항상 `None`(await 대상이 되면 hot path 가 늘어난다)."""
    mod = _setup(monkeypatch)
    assert hasattr(mod, "observe_order"), "`observe_order` 진입점이 없다(Red)"
    assert not inspect.iscoroutinefunction(mod.observe_order), "`observe_order` 는 동기여야 한다"
    params = inspect.signature(mod.observe_order).parameters
    positional = [p for p in params.values()
                  if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)]
    assert positional == [], f"위치 인자 {[p.name for p in positional]} — 키워드 전용이어야 한다"


def test_c17_2_observe_signal_is_deleted(monkeypatch):
    """§6.4 — cycle274 진입점 `observe_signal` 은 **삭제**된다.

    이름이 남아 있으면 전략 원복이 미완이거나 두 진입점이 공존한다는 뜻이다.
    """
    mod = _setup(monkeypatch)
    assert not hasattr(mod, "observe_signal"), (
        "`observe_signal` 이 남아 있다 — 신호 시점 진입점은 이 사이클에서 사라진다"
    )


async def test_c17_3_observe_order_never_raises_on_garbage_input(monkeypatch):
    """C17 — 전 인자가 쓰레기여도 예외를 던지지 않는다(주문 경로를 절대 깨지 않는다)."""
    mod = _setup(monkeypatch)
    _wire(mod, monkeypatch, FakeClient())
    assert mod.observe_order(
        strategy_id=None, ticker=None, order_no=None, order_kst="not-a-datetime",
        order_price_won="x", ordered_qty=None, order_division=None, order_path=None,
        exchange=None, current_price_won=None, budget_total_won=None,
        budget_remaining_after_won=None, open_positions_n=None,
        params_snapshot="not-a-dict", buy_signals_tail=None,
    ) is None
    await _spin()


def test_c18_1_leaf_entry_has_no_await_or_io() -> None:
    """C18 — `observe_order` 본문에 `await`/`async for`/`async with` 0 · DB/HTTP 0.

    동기 hot path 안에서 I/O 를 하면 그 지연이 **주문 다음 문장**을 늦춘다.
    """
    tree = ast.parse(_leaf_src())
    fn = next(
        (n for n in ast.walk(tree)
         if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == "observe_order"),
        None,
    )
    assert fn is not None, "`observe_order` 정의를 찾지 못했다(Red)"
    assert not isinstance(fn, ast.AsyncFunctionDef), "`observe_order` 는 `async def` 가 아니다"
    bad = [type(n).__name__ for n in ast.walk(fn)
           if isinstance(n, (ast.Await, ast.AsyncFor, ast.AsyncWith))]
    assert not bad, f"`observe_order` 안 비동기 구문 {bad}"
    seg = ast.get_source_segment(_leaf_src(), fn) or ""
    for banned in ("pg.", "httpx", "requests.", "fetch("):
        assert banned not in seg, f"`observe_order` 안에 `{banned}`"


def test_c18_2_leaf_entry_creates_exactly_one_task() -> None:
    """C18 — `observe_order` 안 `asyncio.create_task` 호출은 **정확히 1회**."""
    tree = ast.parse(_leaf_src())
    fn = next(
        (n for n in ast.walk(tree)
         if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == "observe_order"),
        None,
    )
    assert fn is not None, "`observe_order` 정의를 찾지 못했다(Red)"
    n_tasks = sum(
        1 for n in ast.walk(fn)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
        and n.func.attr == "create_task"
    )
    assert n_tasks == 1, f"`create_task` {n_tasks}회 (기대 1)"


def test_c22_1_leaf_does_not_touch_eight_area_or_session() -> None:
    """C22 — leaf 는 8영역 모듈과 `session_tracker` 를 참조하지 않는다.

    보드는 `session` 이 아니라 시계로 푼다 — `session_tracker.active` 는 30초 stale 이라
    09:00:0x 에 `pre_nxt` 로 굳는다(cycle264 실증).
    """
    src = _leaf_src()
    banned = (
        "src.engine.risk", "src.engine.order_engine", "src.engine.strategy_registry",
        "src.engine.session", "src.realtime", "src.auth", "src.api.order",
        "session_tracker", "MarketBoard",
    )
    hits = [b for b in banned if b in src]
    assert not hits, f"leaf 가 8영역/세션을 참조한다: {hits}"


def test_c28_1_failure_reasons_have_no_empty_order_no() -> None:
    """C28 — 실패 어휘에 `empty_order_no` 가 없다(그것은 **persist 어휘**다).

    persist 사유를 평가 실패 분포에 섞으면 20:10 리포트의 실패 분류가 오염된다.
    어휘는 cycle276 후속 A-1 에서 `truncated` 가 늘어 10종이다.
    """
    mod = _g()
    assert tuple(mod._FAILURE_REASONS) == _FAILURE_REASONS_10
    assert "empty_order_no" not in mod._FAILURE_REASONS


# ===========================================================================
# C16/C19 — mode 낙하 · 카나리아 · 래치 · cap
# ===========================================================================
async def test_c19_1_mode_off_creates_no_task(monkeypatch, caplog):
    """C16 — 4키 없는 params(= momentum 등 5전략) → `create_task` 0 · 마커 0.

    훅 자체는 전략 무관이고 평가 여부는 `llm_gate_mode` 가 정한다. 키가 없으면
    아무 일도 일어나지 않는다 = 행위 0 이자 **비용 0**.
    """
    caplog.set_level(logging.INFO, logger=_LOGGER)
    mod = _setup(monkeypatch)
    _wire(mod, monkeypatch, FakeClient())
    tasks = _tasks_created(monkeypatch)

    _observe(mod, params_snapshot={"position_ratio": 0.2})
    await _spin()

    assert tasks == [], f"mode=off 인데 task {len(tasks)}건"
    assert _lines(caplog, "[llm_buy_score]") == []
    assert _lines(caplog, "[llm_buy_score_failed]") == []
    assert _lines(caplog, "[llm_eval_persist]") == []


async def test_c19_2_mode_off_still_emits_config_canary(monkeypatch, caplog):
    """C16/C19 — 카나리아는 mode 판정 **앞**이다. `mode=off` 로도 1행 남는다.

    이 행이 장중 PUT 롤백이 먹었는지 확인할 유일한 채널이다 — 여기서 사라지면
    "껐다" 와 "코드가 안 돈다" 가 구별되지 않는다.
    """
    caplog.set_level(logging.INFO, logger=_LOGGER)
    mod = _setup(monkeypatch)
    _wire(mod, monkeypatch, FakeClient())

    _observe(mod, params_snapshot={"position_ratio": 0.2})
    await _spin()

    lines = _lines(caplog, "[llm_gate_config]")
    assert len(lines) == 1, f"`[llm_gate_config]` {len(lines)}행 (기대 1)"
    assert _field(lines[0], "mode") == "off"


@pytest.mark.parametrize("strategy_id", [
    "momentum", "donchian_swing", "bull_flag_breakout", "vcp_breakout", "kojiro",
])
async def test_c19_3_five_other_strategies_now_shadow_evaluate(monkeypatch, strategy_id, caplog):
    """C16 — 🔁 cycle297 반전(2026-09-17). 원래 이 테스트는 "나머지 5전략은 task 0·기록
    0" 을 잠갔다 — 그때는 4키가 VB·LTV 에만 있었기 때문이다. 사용자 결정 "결정 2 진행"
    으로 5전략에도 같은 4키(`llm_gate_mode="shadow"` 포함)가 추가됐으므로, 이제 실제
    `DEFAULT_PARAMS` 로 훅을 태우면 **task 1건 · `[llm_buy_score]` 1행**이 남아야 한다
    (함수는 지우지 않고 기대값만 뒤집는다 — cycle274/276 소유 축 가드와 같은 패턴).
    """
    caplog.set_level(logging.INFO, logger=_LOGGER)
    mod = _setup(monkeypatch)
    _wire(mod, monkeypatch, FakeClient())
    tasks = _tasks_created(monkeypatch)

    module = importlib.import_module(f"src.engine.strategies.{strategy_id}")
    cls = next(
        obj for name, obj in vars(module).items()
        if isinstance(obj, type) and name.endswith("Strategy")
        and getattr(obj, "DEFAULT_PARAMS", None) is not None
    )
    assert cls.DEFAULT_PARAMS.get("llm_gate_mode") == "shadow", (
        f"{strategy_id}: DEFAULT_PARAMS 에 llm_gate_mode=shadow 가 없다(cycle297 회귀)"
    )
    _observe(mod, strategy_id=strategy_id, params_snapshot=dict(cls.DEFAULT_PARAMS))
    await _spin()

    assert len(tasks) == 1, f"{strategy_id}: task {len(tasks)}건 (기대 1 — cycle297 개방)"
    assert _lines(caplog, "[llm_buy_score]") != [], (
        f"{strategy_id}: `[llm_buy_score]` 가 없다 — shadow 평가가 발화하지 않았다"
    )


async def test_c21_1_empty_order_no_records_persist_error_only(monkeypatch, caplog):
    """C21 (자문 R2) — `order_no` 가 비면 평가하지 않고 **무음도 아니다**.

    task 0 · DB 0행 · `[llm_eval_persist] result=error reason=empty_order_no` 1행.
    침묵하면 "평가 안 함" 과 "주문번호를 못 받았다" 가 구별되지 않는다.
    """
    caplog.set_level(logging.INFO, logger=_LOGGER)
    mod = _setup(monkeypatch)
    _wire(mod, monkeypatch, FakeClient())
    tasks = _tasks_created(monkeypatch)

    _observe(mod, order_no="")
    await _spin()

    assert tasks == [], "빈 주문번호인데 평가 task 를 만들었다"
    lines = _lines(caplog, "[llm_eval_persist]")
    assert len(lines) == 1, f"`[llm_eval_persist]` {len(lines)}행 (기대 1)"
    assert _field(lines[0], "result") == "error"
    assert _field(lines[0], "reason") == "empty_order_no"


@pytest.mark.parametrize("bad", ["", "   ", None])
async def test_c21_2_blank_order_no_variants_never_evaluate(monkeypatch, bad):
    """C21 — `""`/공백/`None` 셋 다 같은 취급(뮤테이션 M8)."""
    mod = _setup(monkeypatch)
    _wire(mod, monkeypatch, FakeClient())
    tasks = _tasks_created(monkeypatch)

    _observe(mod, order_no=bad)
    await _spin()

    assert tasks == [], f"order_no={bad!r} 인데 평가 task {len(tasks)}건"


async def test_c20_1_latch_key_is_order_no_same_order_twice(monkeypatch):
    """C20 — 같은 주문번호로 두 번 접수하면 평가는 **1회**(중복 비용 차단)."""
    mod = _setup(monkeypatch)
    _wire(mod, monkeypatch, FakeClient())
    tasks = _tasks_created(monkeypatch)

    _observe(mod)
    _observe(mod)
    await _drain()

    assert len(tasks) == 1, f"같은 주문번호 2회 접수에 task {len(tasks)}건 (기대 1)"


async def test_c20_2_latch_allows_two_orders_same_ticker_same_day(monkeypatch):
    """C20 (HIGH) — 같은 종목을 하루 두 번 사면 **두 번 평가**한다(cycle274 와 반대).

    래치 키를 `(전략, 종목)/일` 로 되돌리는 뮤테이션(M7)이 여기서 죽는다. 09-10 000990
    처럼 12:06 첫 신호의 점수가 15:13 주문에 붙는 사고가 그 키에서 나왔다.
    """
    mod = _setup(monkeypatch)
    _wire(mod, monkeypatch, FakeClient())
    tasks = _tasks_created(monkeypatch)

    _observe(mod, order_no=_ORDER_NO)
    _observe(mod, order_no=_ORDER_NO2)
    await _drain()

    assert len(tasks) == 2, f"주문 2건에 task {len(tasks)}건 (기대 2)"


async def test_c19_4_daily_cap_peek_blocks_and_warns_once(monkeypatch, caplog):
    """C19 — 일일 cap 도달 시 평가 중단 + `[llm_gate_daily_cap]` **1회/전략/일**(WARNING)."""
    caplog.set_level(logging.INFO, logger=_LOGGER)
    mod = _setup(monkeypatch)
    _wire(mod, monkeypatch, FakeClient())
    params = dict(_PARAMS, llm_gate_daily_call_cap=1)
    tasks = _tasks_created(monkeypatch)

    _observe(mod, order_no="A1", params_snapshot=params)
    _observe(mod, order_no="A2", params_snapshot=params)
    _observe(mod, order_no="A3", params_snapshot=params)
    await _drain()

    assert len(tasks) == 1, f"cap=1 인데 task {len(tasks)}건"
    caps = [r.getMessage() for r in caplog.records
            if r.name == _LOGGER and r.levelno >= logging.WARNING
            and r.getMessage().startswith("[llm_gate_daily_cap]")]
    assert len(caps) == 1, f"`[llm_gate_daily_cap]` {len(caps)}행 (기대 1회/전략/일)"


async def test_c19_4b_daily_cap_records_persist_line_per_order(monkeypatch, caplog):
    """검증 라운드 3 #3 — cap 초과로 **건너뛴 주문마다** persist 1행(주문번호 포함).

    `[llm_gate_daily_cap]` 은 1회/전략/일이라 어느 주문이 평가를 못 받았는지 남기지
    못한다 — 그러면 "cap 때문에 평가 안 함" 과 "게이트가 off 였다" 를 주문 단위로
    구별할 수 없고(평가 유무 쪽 선택 편향), 사후 복원도 불가능하다. DB 행은 없다.
    """
    caplog.set_level(logging.INFO, logger=_LOGGER)
    mod = _setup(monkeypatch)
    _wire(mod, monkeypatch, FakeClient())
    params = dict(_PARAMS, llm_gate_daily_call_cap=1)
    tasks = _tasks_created(monkeypatch)

    _observe(mod, order_no="A1", params_snapshot=params)
    _observe(mod, order_no="A2", params_snapshot=params)
    _observe(mod, order_no="A3", params_snapshot=params)
    await _drain()

    assert len(tasks) == 1, f"cap=1 인데 task {len(tasks)}건"
    capped = [ln for ln in _lines(caplog, "[llm_eval_persist]")
              if _field(ln, "reason") == "cap_exceeded"]
    assert len(capped) == 2, (
        f"cap 초과 주문 2건에 persist {len(capped)}행 — 주문 단위 복원 불가: "
        f"{_lines(caplog, '[llm_eval_persist]')}"
    )
    assert {_field(ln, "order_no") for ln in capped} == {"A2", "A3"}, (
        f"어느 주문이 건너뛰어졌는지 남지 않았다: {capped}"
    )
    assert all(_field(ln, "result") == "error" for ln in capped)


async def test_c19_4c_mode_off_never_emits_cap_persist(monkeypatch, caplog):
    """C16 — cap 사유 persist 는 **shadow 경로 전용**이다(`mode=off` 는 여전히 마커 0행).

    5전략(4키 부재)은 `mode` 판정에서 이미 낙하하므로 cap 분기에 도달하지 않는다 —
    관측 표면이 비용 0 전략으로 번지면 안 된다.
    """
    caplog.set_level(logging.INFO, logger=_LOGGER)
    mod = _setup(monkeypatch)
    _wire(mod, monkeypatch, FakeClient())

    for ono in ("B1", "B2", "B3"):
        _observe(mod, order_no=ono, params_snapshot={"position_ratio": 0.2})
    await _spin()

    assert _lines(caplog, "[llm_eval_persist]") == []
    assert _lines(caplog, "[llm_gate_daily_cap]") == []


async def test_c19_5_cap_key_absent_means_zero_calls(monkeypatch):
    """C19 — `llm_gate_daily_call_cap` 키 부재 = **0** = 호출 안 함.

    돈을 쓰는 기능은 설정이 없으면 하지 않는다(cycle245 `max_lot_ratio_mult` 방향).
    """
    mod = _setup(monkeypatch)
    _wire(mod, monkeypatch, FakeClient())
    tasks = _tasks_created(monkeypatch)

    params = {k: v for k, v in _PARAMS.items() if k != "llm_gate_daily_call_cap"}
    _observe(mod, params_snapshot=params)
    await _spin()

    assert tasks == [], "cap 키 부재인데 평가를 시작했다"


async def test_c19_6_latch_mark_precedes_create_task(monkeypatch):
    """C19 — 래치 `mark_emitted` 가 `create_task` **앞**이다.

    뒤에 두면 같은 주문번호가 연달아 들어올 때 두 task 가 동시에 뜬다(비용 2배).
    """
    mod = _setup(monkeypatch)
    _wire(mod, monkeypatch, FakeClient())
    order: list[str] = []

    real_mark = mod._latch.mark_emitted

    def _mark(key, *, now=None):
        order.append("mark")
        return real_mark(key, now=now)

    monkeypatch.setattr(mod._latch, "mark_emitted", _mark)

    real_create = asyncio.create_task

    def _create(coro, *a, **kw):
        order.append("task")
        return real_create(coro, *a, **kw)

    monkeypatch.setattr(asyncio, "create_task", _create)

    _observe(mod)
    await _drain()

    assert order[:2] == ["mark", "task"], f"순서 {order} (기대 mark → task)"


# ===========================================================================
# C22 — `_board_by_clock`
# ===========================================================================
@pytest.mark.parametrize(("hhmmss", "expected"), [
    ((7, 59, 59), "off_hours"),
    ((8, 0, 0), "pre_nxt"),
    ((8, 59, 59), "pre_nxt"),
    ((9, 0, 0), "main"),
    ((15, 29, 59), "main"),
    ((15, 30, 0), "post_nxt"),
    ((19, 59, 59), "post_nxt"),
    ((20, 0, 0), "off_hours"),
])
def test_c22_2_board_by_clock_windows(hhmmss, expected):
    """C22 — 보드 창 경계 8점. 경계는 `[시작, 끝)` 반열림이다."""
    mod = _g()
    h, m, s = hhmmss
    got = mod._board_by_clock(datetime(2026, 9, 11, h, m, s, tzinfo=KST))
    assert got == expected, f"{h:02d}:{m:02d}:{s:02d} → {got} (기대 {expected})"


@freeze_time(_UTC_090442)
def test_c22_3_board_comes_from_argument_not_wall_clock():
    """C22 — 보드는 인자 `order_kst` 에서 나온다(벽시계 09:04 에 고정해도 무관).

    벽시계를 읽으면 판정이 도착하는 시각에 따라 같은 주문의 보드가 달라진다.
    """
    mod = _g()
    assert mod._board_by_clock(datetime(2026, 9, 11, 8, 30, 0, tzinfo=KST)) == "pre_nxt"
    assert mod._board_by_clock(datetime(2026, 9, 11, 16, 30, 0, tzinfo=KST)) == "post_nxt"


def test_c22_4_board_by_clock_never_raises():
    """C22 — 이상 입력은 예외가 아니라 값으로 흡수한다(never-raise)."""
    mod = _g()
    for bad in (None, "09:00", 0):
        assert isinstance(mod._board_by_clock(bad), str)


# ===========================================================================
# C23 — payload 는 값 복사본 (신호 역참조 포함)
# ===========================================================================
async def test_c23_1_signal_match_picks_newest_same_ticker(monkeypatch):
    """§6.1-7 — `buy_signals` 꼬리에서 **같은 종목의 최신 1건**을 찾는다."""
    mod = _setup(monkeypatch)
    _wire(mod, monkeypatch, FakeClient())
    seen = _capture_payload(mod, monkeypatch)

    tail = [
        _signal(price=79_000, target_price=78_900, time="09:01:00"),
        _signal(ticker="000660", price=1, target_price=1, time="09:02:00"),
        _signal(price=80_500, target_price=80_400, time="09:04:41"),
    ]
    _observe(mod, buy_signals_tail=tail)
    await _spin()

    assert seen, "payload 가 만들어지지 않았다(Red)"
    p = seen[0]
    assert p["signal_matched"] is True
    assert p["signal_price_won"] == 80_500
    assert p["signal_time_local"] == "09:04:41"
    assert p["strategy_board"] == "main"
    assert p["target_won"] == 80_400


async def test_c23_2_no_matching_signal_means_signal_matched_false(monkeypatch):
    """§14-4 — 매칭이 없으면 `signal_matched=False` 이고 파생 4필드는 `None`.

    없는 값을 0 으로 위장하면 회고분석이 "목표가 0원 돌파" 를 실제로 세게 된다.
    """
    mod = _setup(monkeypatch)
    _wire(mod, monkeypatch, FakeClient())
    seen = _capture_payload(mod, monkeypatch)

    _observe(mod, buy_signals_tail=[_signal(ticker="000660")])
    await _spin()

    assert seen, "payload 가 만들어지지 않았다(Red)"
    p = seen[0]
    assert p["signal_matched"] is False
    for key in ("signal_price_won", "signal_time_local", "target_won", "k",
                "breakout_excess_bp"):
        assert p[key] is None, f"매칭 없음인데 `{key}` 에 값이 있다: {p[key]!r}"


async def test_c23_3_signal_match_copies_not_references(monkeypatch):
    """C23 — 원본 신호 dict 를 나중에 변조해도 payload 는 흔들리지 않는다(값 복사)."""
    mod = _setup(monkeypatch)
    _wire(mod, monkeypatch, FakeClient())
    seen = _capture_payload(mod, monkeypatch)

    sig = _signal()
    _observe(mod, buy_signals_tail=[sig])
    await _spin()
    assert seen, "payload 가 만들어지지 않았다(Red)"

    sig["price"] = 1
    sig["target_price"] = 1
    assert seen[0]["signal_price_won"] == 80_500
    assert seen[0]["target_won"] == 80_400


async def test_c23_4_payload_drops_prev_price_and_signal_kst(monkeypatch):
    """§14-4 — `prev_price_won`·`target_offset_won`·`signal_kst` 는 **없다**.

    주문 시점에 복구 불가하거나(`prev_price` — 전략이 판정 직후 덮는다) 애초에
    존재하지 않는(`target_offset`) 값을 그럴듯하게 남기지 않는다(자문 R7).
    """
    mod = _setup(monkeypatch)
    _wire(mod, monkeypatch, FakeClient())
    seen = _capture_payload(mod, monkeypatch)

    _observe(mod)
    await _spin()

    assert seen, "payload 가 만들어지지 않았다(Red)"
    p = seen[0]
    for gone in ("prev_price_won", "target_offset_won", "signal_kst", "price_won"):
        assert gone not in p, f"payload 에 `{gone}` 이 남아 있다 — 시각 의미 이동 미반영"
    assert "order_kst" in p and "order_price_won" in p


async def test_c23_5_payload_carries_order_snapshot(monkeypatch):
    """§6.1 — 주문 스냅샷 전 필드가 payload 에 실린다(DB 열의 원천)."""
    mod = _setup(monkeypatch)
    _wire(mod, monkeypatch, FakeClient())
    seen = _capture_payload(mod, monkeypatch)

    _observe(mod)
    await _spin()

    assert seen, "payload 가 만들어지지 않았다(Red)"
    p = seen[0]
    assert p["order_no"] == _ORDER_NO
    assert p["ordered_qty"] == 3
    assert p["order_division"] == "MARKET"
    assert p["order_path"] == "market"
    assert p["exchange"] == "KRX"
    assert p["board"] == "main"
    assert p["order_price_won"] == 80_500
    assert p["current_price_won"] == 80_500
    assert p["budget_total_won"] == 247_949
    assert p["budget_remaining_after_won"] == 32_549
    assert p["open_positions_n"] == 1


async def test_c23_6_account_is_read_from_settings_not_from_caller(monkeypatch):
    """§6.1-7 — 계좌는 leaf 가 `settings` 에서 읽는다(order_engine 은 계좌를 모른다).

    호출부 인자로 받으면 8영역의 import 표면이 넓어진다(C10 증가분 1 위반).
    """
    mod = _setup(monkeypatch)
    _wire(mod, monkeypatch, FakeClient())
    seen = _capture_payload(mod, monkeypatch)

    params = inspect.signature(mod.observe_order).parameters
    assert not [p for p in params if "account" in p.lower()], (
        f"`observe_order` 시그니처에 계좌 인자: {[p for p in params if 'account' in p.lower()]}"
    )

    _observe(mod)
    await _spin()

    assert seen, "payload 가 만들어지지 않았다(Red)"
    assert seen[0]["account_no"] == _ACCOUNT_NO
    assert seen[0]["account_product"] == _ACCOUNT_PRODUCT


# ===========================================================================
# C24/C25 — `_persist_evaluation` (성공·실패 모두 1행)
# ===========================================================================
async def test_c24_1_persist_called_exactly_once_on_success(monkeypatch, caplog):
    """C24 — 정상 응답 → upsert **1회**, `result="ok"`, `reason` 없음."""
    caplog.set_level(logging.INFO, logger=_LOGGER)
    mod = _setup(monkeypatch)
    _wire(mod, monkeypatch, FakeClient())
    calls = _upsert_spy(monkeypatch)

    _observe(mod)
    await _drain()

    assert len(calls) == 1, f"upsert {len(calls)}회 (기대 1)"
    kw = calls[0]
    assert kw["result"] == "ok"
    assert kw.get("reason") in (None, "")
    assert kw["order_no"] == _ORDER_NO
    assert kw["ticker"] == _TICKER
    assert kw["strategy_id"] == _VB
    assert kw["mode"] == "shadow"
    assert kw["score"] == 82
    assert kw["min_score"] == 70
    assert kw["would_block"] is False
    assert kw["account_no"] == _ACCOUNT_NO
    assert kw["eval_kind"] == "order"
    assert kw["order_price_won"] == 80_500
    assert kw["ordered_qty"] == 3
    assert kw["order_notional_won"] == 80_500 * 3
    assert kw["board"] == "main"
    assert isinstance(kw["order_kst"], datetime)

    persists = _lines(caplog, "[llm_eval_persist]")
    assert len(persists) == 1 and _field(persists[0], "result") == "ok"


def _fail_case(mod, monkeypatch, reason: str):
    """실패 9종 중 8종을 각각 유도한다(`cap_exceeded` 는 평가 진입 전 차단이라 제외)."""
    if reason == "timeout":
        _wire(mod, monkeypatch, FakeClient(exc=asyncio.TimeoutError()))
    elif reason == "api_error":
        _wire(mod, monkeypatch, FakeClient(exc=RuntimeError("upstream 503")))
    elif reason == "parse_error":
        _wire(mod, monkeypatch, FakeClient(content="이건 JSON 이 아니다"))
    elif reason == "schema_error":
        _wire(mod, monkeypatch, FakeClient(content='{"rationale": "점수 없음"}'))
    elif reason == "no_bars":
        _wire(mod, monkeypatch, FakeClient(), _BarsSpy(rows=[]))
    elif reason == "no_key":
        _wire(mod, monkeypatch, None)
    elif reason == "disabled_model":
        _wire(mod, monkeypatch, FakeClient())
        monkeypatch.setattr(
            mod, "settings",
            SimpleNamespace(openai_api_key="test-key", openai_buy_gate_model="",
                            kis_account_no=_ACCOUNT_NO, kis_account_product=_ACCOUNT_PRODUCT),
        )
    elif reason == "payload_error":
        _wire(mod, monkeypatch, FakeClient())

        def _boom(*a, **kw):
            raise ValueError("프롬프트 조립 실패")

        monkeypatch.setattr(mod, "build_messages", _boom)
    else:  # pragma: no cover — 파라미터 오타 방어
        raise AssertionError(f"미지 실패 사유: {reason}")


@pytest.mark.parametrize("reason", [
    "timeout", "api_error", "parse_error", "schema_error",
    "no_bars", "no_key", "disabled_model", "payload_error",
])
async def test_c24_2_persist_called_on_failure(monkeypatch, reason, caplog):
    """C24/브리프 §3.4 (HIGH) — LLM 실패도 **1행 남긴다**(뮤테이션 M9).

    침묵하면 "평가 안 함" 과 "평가 실패" 가 구별되지 않는다. 그리고 실패 행에도
    **입력 payload 가 들어 있어야** 한다 — 훗날 그 주문을 다른 모델로 재채점하는
    유일한 다리이고, 실패야말로 재채점 대상이다(뮤테이션 M10).
    """
    caplog.set_level(logging.INFO, logger=_LOGGER)
    mod = _setup(monkeypatch)
    _fail_case(mod, monkeypatch, reason)
    calls = _upsert_spy(monkeypatch)

    _observe(mod)
    await _drain()

    assert len(calls) == 1, f"{reason}: upsert {len(calls)}회 (기대 1)"
    kw = calls[0]
    assert kw["result"] == "failed"
    assert kw["reason"] == reason
    assert kw["score"] is None, "실패인데 점수가 있다 — 0 위장 금지"
    assert kw["would_block"] is None
    assert kw["order_no"] == _ORDER_NO
    payload = kw.get("input_payload")
    assert isinstance(payload, dict) and payload, f"{reason}: `input_payload` 가 비었다"
    assert payload.get("payload"), f"{reason}: 실패 기록의 payload 본문이 비었다"


def test_c24_3_persist_site_count_is_one() -> None:
    """C24 — `_persist_evaluation` 호출 사이트는 **정확히 1곳**이고 `_evaluate` 안이다.

    여러 곳에서 부르면 실패 경로마다 중복 upsert 가 생기고, 어느 경로가 기록을
    책임지는지 사라진다.
    """
    src = _leaf_src()
    tree = ast.parse(src)
    sites = [
        n for n in ast.walk(tree)
        if isinstance(n, ast.Call)
        and ((isinstance(n.func, ast.Name) and n.func.id == "_persist_evaluation")
             or (isinstance(n.func, ast.Attribute) and n.func.attr == "_persist_evaluation"))
    ]
    assert len(sites) == 1, f"`_persist_evaluation` 호출 {len(sites)}곳 (기대 1)"

    evaluate = next(
        (n for n in ast.walk(tree)
         if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == "_evaluate"),
        None,
    )
    assert evaluate is not None, "`_evaluate` 정의를 찾지 못했다"
    assert evaluate.lineno <= sites[0].lineno <= (evaluate.end_lineno or sites[0].lineno), (
        "`_persist_evaluation` 호출이 `_evaluate` 밖에 있다"
    )


async def test_c25_1_persist_never_raises_when_db_fails(monkeypatch, caplog):
    """C25 — DB 기록 실패는 평가 task 를 죽이지 않고 `result=error` 1행으로 남는다.

    이 마커가 **DB 무음을 깨는 유일한 채널**이다(기록 전용 스위치를 따로 두지 않는
    이유이기도 하다 — 스위치가 늘면 "설정이 없으면 관측이 사라지는" 경로가 하나 더 생긴다).
    """
    caplog.set_level(logging.INFO, logger=_LOGGER)
    mod = _setup(monkeypatch)
    _wire(mod, monkeypatch, FakeClient())
    db = _db()

    async def _boom(**kw):
        raise RuntimeError("relation \"llm_buy_evaluations\" does not exist")

    monkeypatch.setattr(db, "upsert_evaluation", _boom)

    _observe(mod)
    await _drain()

    lines = _lines(caplog, "[llm_eval_persist]")
    assert len(lines) == 1, f"`[llm_eval_persist]` {len(lines)}행 (기대 1)"
    assert _field(lines[0], "result") == "error"
    assert _field(lines[0], "order_no") == _ORDER_NO
    assert "reason=" in lines[0], "실패 사유가 없으면 원인 추적이 불가능하다"


async def test_c29_1_key_risks_and_invalidations_are_persisted(monkeypatch):
    """C29 (뮤테이션 M16) — 모델이 준 `key_risks`/`invalidations` 를 **버리지 않는다**.

    cycle274 는 `_risks, _invalids` 로 버렸다. 그 둘이 회고분석에서 "무엇을 걱정했는데
    실제로 무엇이 터졌나" 를 볼 유일한 텍스트다.
    """
    mod = _setup(monkeypatch)
    _wire(mod, monkeypatch, FakeClient())
    calls = _upsert_spy(monkeypatch)

    _observe(mod)
    await _drain()

    assert calls, "upsert 가 호출되지 않았다(Red)"
    kw = calls[0]
    assert kw["key_risks"] == ["되돌림", "거래대금 감소"]
    assert kw["invalidations"] == ["목표가 이탈"]
    assert kw["rationale"] and "돌파 초과" in kw["rationale"], (
        "`rationale` 은 로그의 60자 절단과 무관한 **원문**이어야 한다"
    )


async def test_c29_2_score_log_format_has_no_risks_fields(monkeypatch, caplog):
    """C29 — `[llm_buy_score]` **로그 서식은 불변**(risks/invalidations 필드 추가 금지).

    20:10 리포트의 정규식 파서가 이 마커를 긁는다 — 필드가 늘면 기준선이 깨진다.
    새 값은 DB 에만 싣는다.
    """
    caplog.set_level(logging.INFO, logger=_LOGGER)
    mod = _setup(monkeypatch)
    _wire(mod, monkeypatch, FakeClient())
    _upsert_spy(monkeypatch)

    _observe(mod)
    await _drain()

    lines = _lines(caplog, "[llm_buy_score]")
    assert len(lines) == 1, f"`[llm_buy_score]` {len(lines)}행 (기대 1)"
    assert "key_risks=" not in lines[0]
    assert "invalidations=" not in lines[0]


async def test_c27_1_score_marker_has_order_no_and_renamed_fields(monkeypatch, caplog):
    """C27 (뮤테이션 M17) — `order_no=` 추가 · `slip_bp=` → `post_order_drift_bp=` 개명.

    ⚠️ 두 이름은 **부호 의미가 반대**다 — 배포 전후 로그를 절대 합산하지 말 것
    (cycle228 `would_pass` · cycle263 `skipped_fresh` 계열 사고).
    """
    caplog.set_level(logging.INFO, logger=_LOGGER)
    mod = _setup(monkeypatch)
    _wire(mod, monkeypatch, FakeClient())
    _upsert_spy(monkeypatch)

    _observe(mod)
    await _drain()

    lines = _lines(caplog, "[llm_buy_score]")
    assert len(lines) == 1
    line = lines[0]
    assert _field(line, "order_no") == _ORDER_NO
    assert "slip_bp=" not in line, "구 이름 `slip_bp=` 가 남아 있다"
    assert "post_order_drift_bp=" in line
    assert "order_kst=" in line and "signal_kst=" not in line
    assert "order_price=" in line and "signal_price=" not in line


async def test_c27_2_failed_marker_has_order_no(monkeypatch, caplog):
    """C27 — `[llm_buy_score_failed]` 에도 `order_no=` 가 실린다(주문↔실패 대조 키)."""
    caplog.set_level(logging.INFO, logger=_LOGGER)
    mod = _setup(monkeypatch)
    _fail_case(mod, monkeypatch, "timeout")
    _upsert_spy(monkeypatch)

    _observe(mod)
    await _drain()

    lines = _lines(caplog, "[llm_buy_score_failed]")
    assert len(lines) == 1, f"`[llm_buy_score_failed]` {len(lines)}행 (기대 1)"
    assert _field(lines[0], "order_no") == _ORDER_NO
    assert _field(lines[0], "reason") == "timeout"


def test_c27_3_slip_bp_is_gone_from_leaf_source() -> None:
    """C27 — 소스 전체에서 `slip_bp` 문자열 0건(개명 완료 서명)."""
    assert "slip_bp" not in _leaf_src(), "leaf 에 `slip_bp` 가 남아 있다"


def test_c26_1_markers_live_only_in_the_leaf() -> None:
    """C26 — 마커 5종은 leaf 안에서만 로깅된다.

    다른 모듈이 같은 접두로 로그를 내면 D+1 판독의 행 수 대조가 통째로 무너진다.
    """
    src_root = _ROOT / "src"
    offenders: dict[str, list[str]] = {}
    for path in src_root.rglob("*.py"):
        if path == _LEAF_PATH:
            continue
        text = path.read_text(encoding="utf-8")
        hits = [m for m in _MARKERS if m in text]
        if hits:
            offenders[path.relative_to(_ROOT).as_posix()] = hits
    assert not offenders, f"leaf 밖에서 마커가 발견됐다: {offenders}"


# ===========================================================================
# C35/C36 — `input_payload` 는 재평가 가능한 완전체
# ===========================================================================
async def test_c36_1_input_payload_is_the_three_build_messages_args(monkeypatch):
    """C36 — `{payload, tech, bars30}` **정확히 3키**. 요약·절단 금지.

    이 세 값이 `build_messages` 에 실제로 들어간 것과 같아야 훗날 **오프라인 재채점**이
    가능하다 — 그것이 "자문이 유효했는가" 를 검증할 유일한 수단이다.
    """
    mod = _setup(monkeypatch)
    _wire(mod, monkeypatch, FakeClient())
    calls = _upsert_spy(monkeypatch)

    seen_args: list[tuple] = []
    real_build = mod.build_messages

    def _spy_build(payload, tech, bars30):
        seen_args.append((payload, tech, list(bars30)))
        return real_build(payload, tech, bars30)

    monkeypatch.setattr(mod, "build_messages", _spy_build)

    _observe(mod)
    await _drain()

    assert calls, "upsert 가 호출되지 않았다(Red)"
    ip = calls[0]["input_payload"]
    assert set(ip) == {"payload", "tech", "bars30"}, f"input_payload 키 {sorted(ip)}"
    assert seen_args, "`build_messages` 가 호출되지 않았다"
    _p, tech, bars30 = seen_args[0]
    assert len(ip["bars30"]) == len(bars30) <= 30
    assert set(ip["tech"]) == set(tech), "tech 키가 절단·요약됐다"


async def test_c35_1_input_payload_is_json_serializable(monkeypatch):
    """C35 — `datetime`/`Decimal`/`set` 이 섞여도 `json.dumps` 가 성공한다.

    payload 는 `order_kst`(datetime)를 담고 있다. 사영을 빼먹으면 JSONB 바인딩이
    터지고, 그 실패가 **관측을 관측이 막는** 형태가 된다.
    """
    from decimal import Decimal

    mod = _setup(monkeypatch)
    _wire(mod, monkeypatch, FakeClient())
    calls = _upsert_spy(monkeypatch)

    _observe(mod, buy_signals_tail=[_signal(price=Decimal("80500"))])
    await _drain()

    assert calls, "upsert 가 호출되지 않았다(Red)"
    json.dumps(calls[0]["input_payload"])  # 예외 없이 통과해야 한다


async def test_c40_1_input_payload_has_no_account_number(monkeypatch):
    """C40 — 계좌번호는 `input_payload` 에 넣지 않는다(PK 열로 충분).

    리포터 키가 GET/HEAD 를 경로 무관 통과시키므로(cycle249) 응답 표면에 원문이
    실릴 경로를 원천 차단한다.
    """
    mod = _setup(monkeypatch)
    _wire(mod, monkeypatch, FakeClient())
    calls = _upsert_spy(monkeypatch)

    _observe(mod)
    await _drain()

    assert calls, "upsert 가 호출되지 않았다(Red)"
    blob = json.dumps(calls[0]["input_payload"], ensure_ascii=False)
    assert _ACCOUNT_NO not in blob, "`input_payload` 에 계좌번호 원문이 실렸다"


async def test_c30_1_raw_response_keeps_the_unparsed_content(monkeypatch):
    """§7-3 — 모델 응답 **원문**을 보존한다(파싱 실패 재분류 + 다른 파서로 재판독)."""
    mod = _setup(monkeypatch)
    _fail_case(mod, monkeypatch, "parse_error")
    calls = _upsert_spy(monkeypatch)

    _observe(mod)
    await _drain()

    assert calls, "upsert 가 호출되지 않았다(Red)"
    raw = calls[0].get("raw_response")
    assert isinstance(raw, dict) and raw.get("content") == "이건 JSON 이 아니다", (
        f"`raw_response` 가 원문을 보존하지 않는다: {raw!r}"
    )


# ===========================================================================
# C30 — 버전 고정 2열
# ===========================================================================
def test_c30_2_prompt_and_feature_version_are_12_hex():
    """C30 — 두 버전 값은 12자리 hex. 프롬프트·지표가 바뀐 전후 행을 섞어 회귀하면 안 된다.

    🔁 cycle297 — `_prompt_version` 이 `strategy_id` 인자를 받는 **전략별** 함수로
    바뀌었다(명세 §3.4). `_feature_version` 은 무인자 그대로다.
    """
    mod = _g()
    assert re.fullmatch(r"[0-9a-f]{12}", mod._prompt_version(_VB)), (
        f"_prompt_version({_VB!r}) 이 12자리 hex 가 아니다"
    )
    fv = getattr(mod, "_feature_version", None)
    assert fv is not None, "`_feature_version` 이 없다(Red)"
    val = fv()
    assert isinstance(val, str) and re.fullmatch(r"[0-9a-f]{12}", val), (
        f"_feature_version() = {val!r} (기대 12자리 hex)"
    )


def test_c30_2b_prompt_version_covers_snapshot_schema(monkeypatch):
    """검증 라운드 3 #4 — `_SNAPSHOT_KEYS` 를 바꾸면 `prompt_version` 도 바뀐다.

    모델이 읽는 것은 SYSTEM 문장만이 아니라 **user payload 의 키 집합**이다. 해시가
    두 문자열만 덮으면 스냅샷 키만 손댄 사이클이 *같은* 버전으로 다른 스키마의 행을
    만들어, §7-1 이 금지한 "프롬프트 바뀐 전후 행을 섞은 회귀" 가 조용히 가능해진다.
    """
    from src.engine import llm_features as lf

    mod = _g()
    # 버전은 전략별로 1회만 계산해 캐시한다(`_prompt_version_cache`, cycle297 —
    # `dict[str, str]` 로 확대) — 그 캐시를 비우는 것이 "다시 재려면" 의 유일한
    # seam 이다(`reset_llm_buy_gate_state` 는 래치·cap·일봉 캐시만 건드린다).
    monkeypatch.setattr(mod, "_prompt_version_cache", {})
    base = mod._prompt_version(_VB)
    assert re.fullmatch(r"[0-9a-f]{12}", base), f"prompt_version={base!r}"

    monkeypatch.setattr(lf, "_SNAPSHOT_KEYS", tuple(lf._SNAPSHOT_KEYS) + ("extra_key",))
    monkeypatch.setattr(mod, "_prompt_version_cache", {})
    changed = mod._prompt_version(_VB)

    assert changed != base, (
        "스냅샷 키를 바꿨는데 prompt_version 이 그대로다 — payload 스키마가 버전에서 빠졌다"
    )
    assert re.fullmatch(r"[0-9a-f]{12}", changed)


def test_c30_2c_payload_schema_version_literal_is_current_cycle() -> None:
    """검증 라운드 3 #4 — payload 가 스스로 싣는 `schema_version` 이 현재 스키마를 말한다.

    `_SNAPSHOT_KEYS` 가 cycle276 에서 바뀌었으므로 리터럴도 올려야 한다 — 옛 값을 두면
    payload 는 바뀌었는데 payload 자신이 "안 바뀌었다" 고 말하고, 훗날 오프라인 재채점이
    행을 잘못 층화한다.
    """
    from src.engine.llm_features import build_messages

    messages = build_messages({"strategy": _VB, "ticker": _TICKER}, {}, [])
    user = messages[1]["content"]
    payload = json.loads(user[user.index("{"):])
    assert payload["meta"]["schema_version"] == "cycle276.1", (
        f"schema_version={payload['meta']['schema_version']!r} — 스냅샷 스키마와 어긋난다"
    )


async def test_c30_3_version_computation_failure_is_fail_open(monkeypatch):
    """C30 — 버전 계산 실패는 `""` 이고 **평가는 계속된다**(fail-open).

    버전 문자열 하나 때문에 평가가 멈추면 관측이 관측을 막는 셈이다.
    """
    mod = _setup(monkeypatch)
    _wire(mod, monkeypatch, FakeClient())
    calls = _upsert_spy(monkeypatch)
    monkeypatch.setattr(mod, "_prompt_version", lambda *a, **kw: "")
    monkeypatch.setattr(mod, "_feature_version", lambda: "")

    _observe(mod)
    await _drain()

    assert len(calls) == 1, "버전이 비었다고 평가·기록이 멈췄다"
    assert calls[0]["prompt_version"] == ""
    assert calls[0]["feature_version"] == ""


async def test_c30_4_versions_are_persisted_on_success(monkeypatch):
    """C30 — 성공 행에는 두 버전이 실린다(회고 회귀의 층화 키)."""
    mod = _setup(monkeypatch)
    _wire(mod, monkeypatch, FakeClient())
    calls = _upsert_spy(monkeypatch)

    _observe(mod)
    await _drain()

    assert calls, "upsert 가 호출되지 않았다(Red)"
    assert re.fullmatch(r"[0-9a-f]{12}", calls[0]["prompt_version"] or "")
    assert re.fullmatch(r"[0-9a-f]{12}", calls[0]["feature_version"] or "")


async def test_c30_5_budget_and_positions_are_persisted(monkeypatch):
    """§7-2 — 주문 시점 제약 2열이 기록된다(차단의 반사실 분석용).

    차단의 반사실은 "그 거래의 손익이 사라진다" 가 **아니다** — 예산·`max_positions`
    가 묶여 있으면 차단이 다른 종목 매수로 대체된다. 이 두 값이 없으면 사후 복원 불가.
    """
    mod = _setup(monkeypatch)
    _wire(mod, monkeypatch, FakeClient())
    calls = _upsert_spy(monkeypatch)

    _observe(mod)
    await _drain()

    assert calls, "upsert 가 호출되지 않았다(Red)"
    assert calls[0]["budget_total_won"] == 247_949
    assert calls[0]["budget_remaining_after_won"] == 32_549
    assert calls[0]["open_positions_n"] == 1


# ===========================================================================
# cycle276 후속 A-1 — 추론 토큰이 출력 한도를 먹는다 (`truncated`)
# ===========================================================================
#
# 09-11 09:0x 실전 2건이 `[llm_buy_score_failed] reason=schema_error
# latency_ms=10047 / 5514` 로 끝났다. 운영 컨테이너에서 같은 프롬프트로 한도만 바꿔
# 재현한 실측:
#
#   한도   finish_reason   content 길이   reasoning_tokens   결과
#   3000   stop            218            202                score 43 정상
#    400   stop            270            203                score 44 정상(여유 30)
#    250   length            0            250                빈 문자열 → 실패
#    150   length            0            150                빈 문자열 → 실패
#
# `gpt-5.6-luna` 는 추론 모델이라 추론 토큰이 `max_completion_tokens` 를 함께 소비한다.
# 한도가 소진되면 `content == ""` 로 와서 파싱이 실패하는데, 그것을 `schema_error`
# ("모델이 스키마를 벗어났다")로 뭉개면 "프롬프트가 이상하다" 와 "우리가 한도를 너무
# 낮게 줬다" 가 구별되지 않는다.


class _FinishClient(FakeClient):
    """`finish_reason` 까지 실어 주는 fake — 실 OpenAI 응답 모양과 같다.

    ⚠️ 기존 `FakeClient` 는 `finish_reason` 속성이 **없다**(그 경로는 leaf 가 예외를
    흡수해 `None` 으로 본다). 그래서 이 어휘를 재는 테스트는 별도 fake 를 쓴다 —
    없는 필드를 "stop" 으로 위장하면 판별 로직을 한 번도 안 밟는다.
    """

    def __init__(self, *, finish_reason: str | None = "stop", **kw) -> None:
        super().__init__(**kw)
        self.finish_reason = finish_reason

    async def _create(self, **kwargs):
        self.calls.append(kwargs)
        await asyncio.sleep(0)
        if self.exc is not None:
            raise self.exc
        return SimpleNamespace(
            choices=[SimpleNamespace(
                message=SimpleNamespace(content=self.content),
                finish_reason=self.finish_reason,
            )],
            usage=SimpleNamespace(prompt_tokens=self.in_tok, completion_tokens=self.out_tok),
        )


def test_f1_max_completion_tokens_is_not_starved() -> None:
    """A-1 — 한도 상수가 1000 미만으로 돌아가지 못한다.

    400 은 실측 여유가 30 토큰뿐이라 추론이 조금만 길어지면 전건 실패한다. 비용은
    오르지 않는다 — 과금은 실제 사용량이고 이 상수는 상한일 뿐이다(위 표의 3000 행이
    218자·추론 202토큰).
    """
    mod = _g()
    assert mod._MAX_COMPLETION_TOKENS >= 1000, (
        f"_MAX_COMPLETION_TOKENS={mod._MAX_COMPLETION_TOKENS} — 추론 토큰이 한도를 "
        "함께 소비하므로 400 급 한도는 `content=\"\"` 전건 실패를 만든다"
    )


async def test_f2_length_finish_with_empty_content_is_truncated(monkeypatch, caplog):
    """A-1 — `finish_reason="length"` + `content=""` → `reason=truncated`.

    `schema_error` 로 분류하면 20:10 리포트가 프롬프트 문제와 한도 문제를 못 가른다.
    """
    caplog.set_level(logging.INFO, logger=_LOGGER)
    mod = _setup(monkeypatch)
    _wire(mod, monkeypatch, _FinishClient(content="", finish_reason="length"))
    calls = _upsert_spy(monkeypatch)

    _observe(mod)
    await _drain()

    lines = _lines(caplog, "[llm_buy_score_failed]")
    assert len(lines) == 1, f"실패 마커 {len(lines)}행 (기대 1)"
    assert _field(lines[0], "reason") == "truncated", lines[0]
    assert _field(lines[0], "finish") == "length", lines[0]
    assert _lines(caplog, "[llm_buy_score]") == [], "실패인데 점수 행이 나왔다"
    assert calls and calls[0]["reason"] == "truncated"
    assert calls[0]["score"] is None, "실패 행의 점수는 NULL 이다(0 위장 금지)"


async def test_f3_stop_finish_with_good_json_scores_normally(monkeypatch, caplog):
    """A-1 — 정상 응답(`finish="stop"` + 완전한 JSON)은 종전대로 점수가 난다."""
    caplog.set_level(logging.INFO, logger=_LOGGER)
    mod = _setup(monkeypatch)
    _wire(mod, monkeypatch, _FinishClient(content=_GOOD_JSON, finish_reason="stop"))

    _observe(mod)
    await _drain()

    assert _lines(caplog, "[llm_buy_score_failed]") == []
    score_lines = _lines(caplog, "[llm_buy_score]")
    assert len(score_lines) == 1, f"점수 행 {len(score_lines)}행 (기대 1)"
    assert _field(score_lines[0], "score") == "82"


async def test_f4_schema_error_is_not_relabeled_when_finish_is_stop(monkeypatch, caplog):
    """A-1 — `finish="stop"` 인데 스키마를 벗어난 응답은 여전히 `schema_error` 다.

    새 어휘가 기존 분류를 삼키면(모든 파싱 실패를 truncated 로) 프롬프트 결함이 숨는다.
    """
    caplog.set_level(logging.INFO, logger=_LOGGER)
    mod = _setup(monkeypatch)
    _wire(mod, monkeypatch, _FinishClient(content='{"rationale": "점수 없음"}',
                                          finish_reason="stop"))

    _observe(mod)
    await _drain()

    lines = _lines(caplog, "[llm_buy_score_failed]")
    assert len(lines) == 1
    assert _field(lines[0], "reason") == "schema_error"
    assert _field(lines[0], "finish") == "stop"


async def test_f5_complete_json_with_length_finish_keeps_its_score(monkeypatch, caplog):
    """A-1 — 한도에 닿았어도 **완전한 JSON** 이면 그 점수는 유효하다(실패로 바꾸지 않는다).

    재분류는 파싱이 실패한 경우에만 한다 — 유효한 판정을 버리면 모집단이 줄고 그만큼
    2주 게이트의 검정력이 사라진다.
    """
    caplog.set_level(logging.INFO, logger=_LOGGER)
    mod = _setup(monkeypatch)
    _wire(mod, monkeypatch, _FinishClient(content=_GOOD_JSON, finish_reason="length"))

    _observe(mod)
    await _drain()

    assert _lines(caplog, "[llm_buy_score_failed]") == []
    assert len(_lines(caplog, "[llm_buy_score]")) == 1


async def test_f6_pre_call_failures_log_finish_dash(monkeypatch, caplog):
    """A-1 — LLM 호출 **전**에 끝난 실패는 `finish=-` 다(`stop` 위장 금지).

    `no_key` 는 응답이 존재하지 않으므로 `finish_reason` 도 없다. 그 자리에 그럴듯한
    값을 넣으면 사후 판독이 "모델이 정상 종료했는데 실패했다" 로 오독된다.
    """
    caplog.set_level(logging.INFO, logger=_LOGGER)
    mod = _setup(monkeypatch)
    _wire(mod, monkeypatch, None)

    _observe(mod)
    await _drain()

    lines = _lines(caplog, "[llm_buy_score_failed]")
    assert len(lines) == 1
    assert _field(lines[0], "reason") == "no_key"
    assert _field(lines[0], "finish") == "-"


async def test_f7_request_carries_the_raised_token_limit(monkeypatch):
    """A-1 — 실제 요청 kwargs 의 `max_completion_tokens` 가 상수와 같다.

    상수만 올리고 호출부가 옛 리터럴을 쓰면 실전은 그대로 실패한다.
    """
    mod = _setup(monkeypatch)
    client = _FinishClient(content=_GOOD_JSON)
    _wire(mod, monkeypatch, client)

    _observe(mod)
    await _drain()

    assert client.calls, "LLM 호출이 일어나지 않았다"
    assert client.calls[0]["max_completion_tokens"] == mod._MAX_COMPLETION_TOKENS
    assert client.calls[0]["max_completion_tokens"] >= 1000


@pytest.mark.parametrize("raw", ["length", "LENGTH", " length "])
def test_f8_is_truncated_accepts_case_and_space(raw) -> None:
    """A-1 — 판별은 대소문자·공백에 둔감하고, 그 밖의 값은 전부 False(fail-open)."""
    mod = _g()
    assert mod._is_truncated(raw) is True


@pytest.mark.parametrize("raw", [None, "", "stop", "content_filter", 0, object()])
def test_f9_is_truncated_false_for_everything_else(raw) -> None:
    """A-1 — 미지 값·예외는 종전 어휘를 유지한다(판별 실패가 새 사유를 만들지 않는다)."""
    mod = _g()
    assert mod._is_truncated(raw) is False


# ===========================================================================
# cycle276 후속 B-1 — `buy_signals` 꼬리를 자르지 않는다
# ===========================================================================
async def test_f10_signal_match_survives_beyond_three_newer_signals(monkeypatch):
    """B-1 — 같은 종목 신호 뒤에 다른 종목 신호가 3건 이상 쌓여도 매칭이 성공한다.

    `order_engine` 이 `state.buy_signals[-3:]` 로 잘라 넘기던 동안, 09:0x 처럼 여러
    종목이 연달아 돌파하면 그 주문의 신호가 꼬리 밖으로 밀려 `signal_matched=False` 가
    됐다 — 목표가·k·돌파 초과폭이 통째로 `None` 이 되어 회고분석이 그 주문을 못 쓴다.
    """
    mod = _setup(monkeypatch)
    _wire(mod, monkeypatch, FakeClient())
    calls = _upsert_spy(monkeypatch)

    tail = [_signal(price=80500, target_price=80400, time="09:04:41")]
    tail += [
        _signal(ticker=f"00{i}660", name=f"기타{i}", price=1000 + i, time=f"09:04:4{i}")
        for i in range(2, 8)
    ]
    assert len(tail) == 7, "꼬리 길이 전제"

    _observe(mod, buy_signals_tail=tail)
    await _drain()

    assert calls, "upsert 가 호출되지 않았다"
    row = calls[0]
    assert row["signal_matched"] is True, (
        "꼬리가 잘려 같은 종목 신호를 못 찾았다 — `buy_signals_tail` 이 전량인지 확인"
    )
    assert row["signal_price_won"] == 80500
    assert row["target_won"] == 80400
    assert row["signal_time_local"] == "09:04:41"


def test_f11_order_engine_passes_the_whole_signal_list() -> None:
    """B-1 — `order_engine` 의 두 훅이 `buy_signals` 를 **자르지 않고** 넘긴다.

    전략이 이미 20건으로 cap 하므로 `[-3:]` 는 비용을 아끼지 못하고(dict 20개 얕은
    복사) 매칭만 잃는다. 슬라이스가 되살아나면 이 가드가 붉어진다.
    """
    src = (_ROOT / "src" / "engine" / "order_engine.py").read_text(encoding="utf-8")
    assert "buy_signals[-3:]" not in src, "`buy_signals[-3:]` 슬라이스가 되살아났다"
    assert src.count("buy_signals_tail=list(state.buy_signals),") == 2, (
        "두 매수 경로(시장가·지정가 폴백)가 전량 전달이 아니다"
    )
    # 전략 측 cap 이 20 이라는 전제가 깨지면(예: cap 제거) 이 결정의 근거가 바뀐다.
    vb = (_ROOT / "src" / "engine" / "strategies" / "volatility_breakout.py").read_text(
        encoding="utf-8"
    )
    assert "len(self.state.buy_signals) > 20" in vb, "전략 측 20건 cap 전제가 사라졌다"
