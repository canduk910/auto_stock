"""cycle297 검증 후속 — 프로덕션 **배선**을 재는 가드(순수 함수 단위 테스트의 사각).

명세 = `_workspace/red/cycle297_llm_gate_all_strategies_spec.md` §3.2 · §3.3 · §3.4.

## 왜 이 파일이 따로 있나

검증 2렌즈가 같은 결함을 독립으로 잡았다 — **`_resolve_stop_loss_pct` 가 정의와 골든
테스트만 있고 프로덕션 호출이 0건**이었다(`grep -rn "_resolve_stop_loss_pct(" src/` 가
`def` 한 줄만). 명세 §3.3 이 요구한 "`_evaluate` 의 `compute_technicals` **뒤** 1곳" 이
빠졌는데, G1-9 가 그 함수를 **직접** 부르므로 전수 초록이었다. 순수 함수만 재는 테스트는
"계산이 맞는가" 는 잡아도 "그 계산이 실제로 쓰이는가" 는 구조적으로 못 잡는다.

그래서 이 파일은 전부 **`observe_order` → `_evaluate` → `build_messages`/`upsert` 를
실제로 태우고** 모델이 읽는 값과 DB 에 들어가는 값을 잰다. 두 번째 축(W2)도 같은
성질이다 — `_SNAPSHOT_NA_KEYS` 는 "그 전략에 돌파선이 없다" 고 선언할 뿐, 그 선언이
전략 파일의 `buy_signals` 와 맞는지는 재지 않는다.

## 재는 것

| | 무엇 | 없으면 생기는 일 |
|---|---|---|
| W1 | `stop_loss_pct` 가 `atr14_pct` 로 재해석돼 **프롬프트에 실린다** | turtle 라이브인 donchian·kojiro 가 실제 손절과 다른 고정값으로 채점된다(판단 기준 4 오발동) |
| W2 | `target_won` 이 그 전략의 **진짜 돌파선**이다 | BFB 는 측정 이동 목표가를 기준으로 `breakout_excess_bp` 를 내 큰 음수가 상시가 되고, VB 에서 "+bp=추격" 이던 잣대가 뒤집힌다 |
| W3 | `prompt_version` 이 **그 주문의 전략**으로 계산된다 | 전략별 버전 축이 조용히 사라져 `by_prompt_version` 집계가 무의미해진다 |
| W4 | `_read_stop_loss_pct` 가 **라이브 params** 를 읽는다 | PUT 으로 손절을 바꿔도 프롬프트는 옛 값을 말한다 |

## 양성 대조군

부정 단언("VB 는 안 바뀐다", "momentum 엔 돌파선이 없다") 옆에 항상 **바뀌어야 할 것이
실제로 바뀌었는지**를 같은 테스트 안에서 잰다 — 배선이 통째로 죽어도 초록이 되지 않게.
"""

from __future__ import annotations

import ast
import asyncio
import gc
import importlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.unit

KST = timezone(timedelta(hours=9))

_GATE_MOD = "src.engine.llm_buy_gate"
_FEATURES_MOD = "src.engine.llm_features"

_NOW = datetime(2026, 9, 17, 9, 12, 30, tzinfo=KST)
_TICKER = "005930"
_ORDER_NO = "0000123456"
_ACCOUNT_NO = "12345678"

_GOOD_JSON = json.dumps(
    {
        "score": 61,
        "rationale": "돌파 거래량 1.8배, 손절폭 대비 ATR 양호",
        "key_risks": ["되돌림"],
        "invalidations": ["거래량 급감"],
    },
    ensure_ascii=False,
)


def _gate():
    return importlib.import_module(_GATE_MOD)


def _lf():
    return importlib.import_module(_FEATURES_MOD)


def _strategy_ids() -> tuple[str, ...]:
    from src.engine.param_catalog import STRATEGY_IDS

    return tuple(STRATEGY_IDS)


def _default_params(sid: str) -> dict:
    """그 전략의 실제 `DEFAULT_PARAMS` 복사본(손으로 쓴 픽스처 금지 — 괴리가 결함을 가린다)."""
    from src.engine.strategies.bull_flag_breakout import BullFlagBreakoutStrategy
    from src.engine.strategies.donchian_swing import DonchianSwingStrategy
    from src.engine.strategies.kojiro import KojiroStrategy
    from src.engine.strategies.long_tail_volatility import LongTailVolatilityStrategy
    from src.engine.strategies.momentum import MomentumStrategy
    from src.engine.strategies.vcp_breakout import VcpBreakoutStrategy
    from src.engine.strategies.volatility_breakout import VolatilityBreakoutStrategy

    table = {
        "momentum": MomentumStrategy,
        "volatility_breakout": VolatilityBreakoutStrategy,
        "long_tail_volatility": LongTailVolatilityStrategy,
        "donchian_swing": DonchianSwingStrategy,
        "bull_flag_breakout": BullFlagBreakoutStrategy,
        "vcp_breakout": VcpBreakoutStrategy,
        "kojiro": KojiroStrategy,
    }
    return dict(table[sid].DEFAULT_PARAMS)


# ---------------------------------------------------------------------------
# 하네스 — `observe_order` 부터 `upsert_evaluation` 까지 실제로 태운다
# ---------------------------------------------------------------------------
class _FakeCompletions:
    def __init__(self, owner) -> None:
        self._owner = owner

    async def create(self, **kwargs):
        self._owner.calls.append(kwargs)
        await asyncio.sleep(0)
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content=_GOOD_JSON), finish_reason="stop",
                )
            ],
            usage=SimpleNamespace(prompt_tokens=3000, completion_tokens=200),
        )


class _FakeClient:
    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.chat = SimpleNamespace(completions=_FakeCompletions(self))


def _bars(n: int = 60) -> list[dict]:
    out = []
    for i in range(n):
        px = 80_000 + (n - i) * 10
        out.append(
            {
                "stck_bsop_date": (_NOW.date() - timedelta(days=1 + i)).strftime("%Y%m%d"),
                "stck_oprc": str(px - 30),
                "stck_hgpr": str(px + 80),
                "stck_lwpr": str(px - 90),
                "stck_clpr": str(px),
                "acml_vol": str(500_000 + i),
            }
        )
    return out


@pytest.fixture(autouse=True)
def _reset_state():
    """leaf 상태(래치·cap·일봉 캐시·버전 캐시) 초기화 + **GC 확정**.

    ⚠️ 이 픽스처는 절대 던지지 않는다 — 던지면 setup ERROR 로 보고돼 "실패한 계약" 과
    "돌려보지도 못한 계약" 이 구별되지 않는다.

    🔴 `gc.collect()` 가 있는 이유(이 파일의 결함이 아니다) — `tests/unit/engine/` 에는
    **KIS `oauth2/tokenP` 를 실제로 때리는 선재 테스트가 11개** 있고(이 환경에서 403),
    그 실패가 `auth/token.py` 의 합류(coalescing) Future 에 `set_exception` 으로 심긴 뒤
    **대기자가 0명이면 아무도 회수하지 않는다**. 그러면 그 Future 가 GC 될 때 asyncio 가
    `ERROR: Future exception was never retrieved` 를 남기고, 하필 그때 실행 중인 테스트가
    `assert not errors` 를 하면(`test_market_op_subscribe_socket_guard.py`) 엉뚱한 곳이
    붉어진다. 이 파일은 async task 를 많이 만들어 그 GC 시점을 옮긴다 —
    **여기서 확정적으로 거둬** 남의 테스트로 떠넘기지 않는다.

    이 한 줄은 증상을 자기 범위 안에 묶을 뿐 원인을 고치지 않는다. 근본 시정은 두 갈래다 —
    ① 선재 테스트 11개가 실제 네트워크를 타지 않게 하기 ② `issue()` 가 대기자 없는 Future 의
    예외를 회수하기(`fut.add_done_callback(lambda f: f.exception())`). 둘 다 이 사이클 밖이다.
    """
    def _try():
        try:
            _gate().reset_llm_buy_gate_state()
        except Exception:  # pragma: no cover — 픽스처는 절대 던지지 않는다
            pass

    _try()
    yield
    _try()
    gc.collect()


class _Harness:
    """`build_messages` 인자와 `upsert_evaluation` kwargs 를 그대로 붙잡는다."""

    def __init__(self) -> None:
        self.messages_args: list[tuple] = []
        self.upserts: list[dict] = []
        self.client = _FakeClient()


def _setup(monkeypatch, *, tech: dict | None = None) -> _Harness:
    mod = _gate()
    h = _Harness()

    monkeypatch.setattr(
        mod,
        "settings",
        SimpleNamespace(
            openai_api_key="test-key",
            openai_buy_gate_model="gpt-5.6-luna",
            kis_account_no=_ACCOUNT_NO,
            kis_account_product="01",
        ),
    )
    monkeypatch.setattr(mod, "_get_client", lambda: h.client)

    async def _fake_bars(ticker, days, *, min_required=None):
        return _bars()

    monkeypatch.setattr(mod, "get_recent_daily_normalized", _fake_bars)

    if tech is not None:
        monkeypatch.setattr(mod, "compute_technicals", lambda *a, **kw: dict(tech))

    real_build = _lf().build_messages

    def _spy_build(payload, tech_in, bars30):
        h.messages_args.append((dict(payload), dict(tech_in or {}), list(bars30 or [])))
        return real_build(payload, tech_in, bars30)

    monkeypatch.setattr(mod, "build_messages", _spy_build)

    import src.db.llm_buy_evaluations as _db

    async def _fake_upsert(**kwargs):
        h.upserts.append(dict(kwargs))
        return True

    monkeypatch.setattr(_db, "upsert_evaluation", _fake_upsert)

    from src.engine import scanner

    monkeypatch.setattr(scanner, "ticker_prices", {}, raising=False)
    monkeypatch.setattr(scanner, "ticker_names", {_TICKER: "삼성전자"}, raising=False)
    monkeypatch.setattr(scanner, "ticker_market_info", {}, raising=False)
    return h


def _shadow_params(sid: str, **over) -> dict:
    p = _default_params(sid)
    p["llm_gate_mode"] = "shadow"
    p.update(over)
    return p


def _observe(mod, *, strategy_id, params, signal, order_price=80_500) -> None:
    assert (
        mod.observe_order(
            strategy_id=strategy_id,
            ticker=_TICKER,
            order_no=_ORDER_NO,
            order_kst=_NOW,
            order_price_won=order_price,
            ordered_qty=3,
            order_division="MARKET",
            order_path="market",
            exchange="KRX",
            current_price_won=order_price,
            budget_total_won=1_000_000,
            budget_remaining_after_won=500_000,
            open_positions_n=1,
            params_snapshot=dict(params),
            buy_signals_tail=[signal],
        )
        is None
    ), "`observe_order` 반환은 항상 None 이어야 한다"


async def _drain(rounds: int = 200) -> None:
    for _ in range(rounds):
        others = [
            t for t in asyncio.all_tasks()
            if t is not asyncio.current_task() and not t.done()
        ]
        if not others:
            return
        await asyncio.wait(others, timeout=5)


def _snapshot_of(h: _Harness) -> dict:
    """모델이 실제로 읽은 user 메시지의 `snapshot` 블록."""
    assert h.messages_args, "`build_messages` 가 호출되지 않았다 — 평가가 돌지 않았다"
    payload, tech, bars30 = h.messages_args[-1]
    content = _lf().build_messages(payload, tech, bars30)[1]["content"]
    return json.loads(content[content.index("{"):])["snapshot"]


# ===========================================================================
# W1 — `_resolve_stop_loss_pct` 가 `_evaluate` 에 **배선**돼 있다 (검증 HIGH #1)
# ===========================================================================
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "sid,over,atr14_pct,expected",
    [
        # donchian turtle — `max(-(stop_atr×atr), backstop)` = 타이트한 쪽
        ("donchian_swing",
         {"sizing_mode": "turtle", "stop_atr": 2.0, "turtle_backstop_pct": -9.0,
          "stop_loss_rate": -7.0},
         3.0, -6.0),
        # ATR 결측 → 고정% 로 fail-open(0.0 위장 금지)
        ("donchian_swing",
         {"sizing_mode": "turtle", "stop_atr": 2.0, "turtle_backstop_pct": -9.0,
          "stop_loss_rate": -7.0},
         None, -7.0),
        # 비-터틀 donchian 은 재해석을 타지 않는다(DB 토글이 손절 규약을 바꾸면 안 된다)
        ("donchian_swing",
         {"sizing_mode": "position_ratio", "stop_atr": 2.0, "turtle_backstop_pct": -9.0,
          "stop_loss_rate": -7.0},
         3.0, -7.0),
        # kojiro — sizing_mode 무관, 항상 `max(hard_stop_pct, -(stop_atr×atr))`
        ("kojiro", {"stop_atr": 2.0, "hard_stop_pct": -8.0}, 3.0, -6.0),
        ("kojiro", {"stop_atr": 2.0, "hard_stop_pct": -8.0}, 5.0, -8.0),
        # momentum — ATR 손절 전략이 아니다(고정 % 그대로)
        ("momentum", {"stop_loss_rate": -7.5}, 3.0, -7.5),
        # VB — 배선이 기존 두 전략의 값을 바꾸지 않는다(byte 동일 축의 런타임 짝)
        ("volatility_breakout", {"stop_loss_rate": -3.0}, 3.0, -3.0),
    ],
)
async def test_w1a_prompt_stop_loss_pct_is_resolved_from_live_atr(
    monkeypatch, sid, over, atr14_pct, expected,
) -> None:
    """W1 (검증 HIGH #1) — 모델이 읽는 `stop_loss_pct` 가 그 시점 `atr14_pct` 로 재해석된다.

    순수 함수 골든(G1-9)만으로는 **호출부가 없어도** 전수 초록이다. 여기서는
    `observe_order` → `_evaluate` → `build_messages` 를 실제로 태워 프롬프트에 들어간
    값을 읽는다. 배선을 지우면 donchian(atr=3.0)이 −6.0 대신 −7.0 으로 나와 붉다.
    """
    mod = _gate()
    h = _setup(monkeypatch, tech={"atr14_pct": atr14_pct, "pos_in_ch20_pct": 80.0})
    _observe(mod, strategy_id=sid, params=_shadow_params(sid, **over),
             signal={"ticker": _TICKER, "price": 80_400, "time": "09:12:20"})
    await _drain()

    got = _snapshot_of(h)["stop_loss_pct"]
    assert got == pytest.approx(expected), (
        f"{sid} atr14_pct={atr14_pct}: 프롬프트 stop_loss_pct={got} != {expected} — "
        "`_evaluate` 의 `_resolve_stop_loss_pct` 배선을 확인하라"
    )
    assert got < 0.0, "손절폭이 0.0/양수로 실렸다 — 판단 기준 4 를 항상 발동시키는 거짓말"


@pytest.mark.asyncio
async def test_w1b_resolved_stop_loss_reaches_the_persisted_input_payload(
    monkeypatch,
) -> None:
    """W1 — 재해석 결과가 `input_payload.payload` 에도 담긴다(오프라인 재채점의 다리).

    **양성 대조군** = 같은 행의 `tech.atr14_pct` 도 함께 담겨 있어야 한다. 둘이 있어야
    나중에 "이 손절폭이 어떻게 나왔나" 를 손으로 검산할 수 있다.
    """
    mod = _gate()
    h = _setup(monkeypatch, tech={"atr14_pct": 3.0})
    sid = "donchian_swing"
    _observe(
        mod, strategy_id=sid,
        params=_shadow_params(sid, sizing_mode="turtle", stop_atr=2.0,
                              turtle_backstop_pct=-9.0, stop_loss_rate=-7.0),
        signal={"ticker": _TICKER, "price": 80_400, "time": "09:12:20"},
    )
    await _drain()

    assert len(h.upserts) == 1, f"upsert {len(h.upserts)}회 (기대 1)"
    ip = h.upserts[0]["input_payload"]
    assert ip["payload"]["stop_loss_pct"] == pytest.approx(-6.0)
    assert ip["tech"]["atr14_pct"] == pytest.approx(3.0), "검산 근거(ATR)가 함께 없다"


@pytest.mark.asyncio
async def test_w1c_stop_params_never_leaks_into_the_model_or_the_db(monkeypatch) -> None:
    """W1 — 배선용 원시 params(`_stop_params`)는 프롬프트에도 DB 에도 안 실린다.

    프롬프트 = `snapshot_keys_for` 화이트리스트가 막고, DB = `_PAYLOAD_EXCLUDED_KEYS` 가
    막는다. 후자가 없으면 VB·LTV `input_payload` 키 집합이 배포 전후로 갈려 §7 D+1
    대조("키 집합 동일")가 무너진다.

    **양성 대조군** = 같은 호출에서 `stop_loss_pct` 는 두 곳 모두에 실제로 있다.
    """
    mod = _gate()
    h = _setup(monkeypatch, tech={"atr14_pct": 3.0})
    sid = "kojiro"
    _observe(mod, strategy_id=sid,
             params=_shadow_params(sid, stop_atr=2.0, hard_stop_pct=-8.0),
             signal={"ticker": _TICKER, "price": 80_400, "time": "09:12:20"})
    await _drain()

    snapshot = _snapshot_of(h)
    assert "_stop_params" not in snapshot
    assert "stop_loss_pct" in snapshot, "양성 대조군 실패 — 손절폭 자체가 안 실렸다"

    payload_json = h.upserts[0]["input_payload"]["payload"]
    assert "_stop_params" not in payload_json, (
        "`_stop_params` 가 input_payload 에 실렸다 — `_PAYLOAD_EXCLUDED_KEYS` 확인"
    )
    assert "stop_loss_pct" in payload_json


def _gate_src() -> str:
    return Path(_gate().__file__).read_text(encoding="utf-8")


def test_w1d_evaluate_core_calls_the_resolver_exactly_where_atr_exists() -> None:
    """W1 — AST: `_evaluate_core` 안에 `_resolve_stop_loss_pct` 호출과 `payload["stop_loss_pct"]`
    대입이 **둘 다** 있다.

    런타임 가드(W1a)가 주 방어선이고 이것은 "왜 여기에 있는가" 를 못박는 구조 가드다 —
    호출만 있고 대입이 없거나(계산만 하고 버림), 대입만 있고 호출이 없는(고정값 재대입)
    두 반쪽 회귀를 각각 잡는다.
    """
    tree = ast.parse(_gate_src())
    fn = next(
        (n for n in ast.walk(tree)
         if isinstance(n, ast.AsyncFunctionDef) and n.name == "_evaluate_core"),
        None,
    )
    assert fn is not None, "`_evaluate_core` 가 사라졌다"

    calls = [
        n for n in ast.walk(fn)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
        and n.func.id == "_resolve_stop_loss_pct"
    ]
    assert len(calls) == 1, f"`_resolve_stop_loss_pct` 호출 {len(calls)}건 (기대 1)"

    assigns = [
        t for n in ast.walk(fn) if isinstance(n, ast.Assign) for t in n.targets
        if isinstance(t, ast.Subscript) and isinstance(t.value, ast.Name)
        and t.value.id == "payload"
        and isinstance(t.slice, ast.Constant) and t.slice.value == "stop_loss_pct"
    ]
    assert assigns, "`payload[\"stop_loss_pct\"]` 대입이 없다 — 계산만 하고 버린다"


# ===========================================================================
# W2 — `target_won` 은 그 전략의 **진짜 돌파선**이다 (검증 HIGH #2)
# ===========================================================================
#: 전략별 `buy_signals` 의 돌파선 키(=`_BREAKOUT_LINE_KEYS` 기대값).
#: 출처 = 각 전략 파일의 `self.state.buy_signals.append({...})` 리터럴.
_EXPECTED_BREAKOUT_KEYS: dict[str, tuple[str, ...]] = {
    "volatility_breakout": ("target_price",),
    "long_tail_volatility": ("target_price",),
    "bull_flag_breakout": ("flag_high",),
    "donchian_swing": ("donchian_high",),
    "vcp_breakout": ("base_high",),
    "momentum": (),
    "kojiro": (),
}

#: "돌파선일 수 있는" 후보 키 — 빈 매핑 전략이 이 중 무엇도 싣지 않음을 잰다(양성 대조군).
_BREAKOUT_KEY_CANDIDATES = ("target_price", "flag_high", "donchian_high", "base_high")

_STRATEGY_FILE = {
    "momentum": "momentum.py",
    "volatility_breakout": "volatility_breakout.py",
    "long_tail_volatility": "long_tail_volatility.py",
    "donchian_swing": "donchian_swing.py",
    "bull_flag_breakout": "bull_flag_breakout.py",
    "vcp_breakout": "vcp_breakout.py",
    "kojiro": "kojiro.py",
}


def _buy_signal_dicts(sid: str) -> list[ast.Dict]:
    """그 전략 파일의 `buy_signals.append({...})` dict 리터럴 전부."""
    path = Path("src/engine/strategies") / _STRATEGY_FILE[sid]
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out: list[ast.Dict] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr != "append":
            continue
        base = node.func.value
        if not (isinstance(base, ast.Attribute) and base.attr == "buy_signals"):
            continue
        for arg in node.args:
            if isinstance(arg, ast.Dict):
                out.append(arg)
    return out


def _buy_signal_keys(sid: str) -> set[str]:
    keys: set[str] = set()
    for d in _buy_signal_dicts(sid):
        for k in d.keys:
            if isinstance(k, ast.Constant) and isinstance(k.value, str):
                keys.add(k.value)
    return keys


def test_w2a_breakout_line_map_covers_exactly_the_seven_strategies() -> None:
    """W2 — `_BREAKOUT_LINE_KEYS` 가 7전략 전수를 명시한다(미등록 = 조용한 `target_price` 폴백).

    폴백 자체는 남겨도 되지만 **등록된 전략이 그 길로 떨어지면** BFB 처럼 뜻이 다른 키를
    읽게 된다. 키 집합을 못박아 새 전략이 추가될 때 붉어지게 한다.
    """
    got = _gate()._BREAKOUT_LINE_KEYS
    assert set(got) == set(_strategy_ids()), (
        f"`_BREAKOUT_LINE_KEYS` 키 {sorted(got)} != STRATEGY_IDS {sorted(_strategy_ids())}"
    )
    assert {k: tuple(v) for k, v in got.items()} == _EXPECTED_BREAKOUT_KEYS


@pytest.mark.parametrize("sid", sorted(_EXPECTED_BREAKOUT_KEYS))
def test_w2b_mapped_key_actually_exists_in_that_strategys_buy_signals(sid: str) -> None:
    """W2 (검증 HIGH #2) — 매핑한 키가 그 전략의 `buy_signals` 에 **실제로** 있다.

    없는 키를 매핑하면 `target_won` 이 영구 `None` 인데 `_SNAPSHOT_NA_KEYS` 는 "있다" 고
    선언해 결측 3개 규칙이 다시 조용히 발동한다. 선언과 사실을 같은 테스트에서 맞댄다.

    **양성 대조군** = 빈 매핑 전략(momentum·kojiro)은 후보 4키 중 **무엇도** 싣지 않는다.
    """
    keys = _buy_signal_keys(sid)
    assert keys, f"{sid}: `buy_signals.append({{...}})` 리터럴을 못 찾았다"
    mapped = _EXPECTED_BREAKOUT_KEYS[sid]
    if mapped:
        for key in mapped:
            assert key in keys, (
                f"{sid}: 매핑한 돌파선 키 `{key}` 가 buy_signals 에 없다 — {sorted(keys)}"
            )
    else:
        leaked = sorted(k for k in _BREAKOUT_KEY_CANDIDATES if k in keys)
        assert not leaked, (
            f"{sid}: 돌파선 개념이 없다고 선언했는데 buy_signals 에 {leaked} 가 있다"
        )


def test_w2c_bfb_target_price_is_a_measured_move_not_the_breakout_line() -> None:
    """W2 — BFB 의 `target_price` 는 **계산된 측정 이동 목표가**다(돌파선이 아니다).

    이 사이클의 HIGH 결함이 정확히 여기였다 — `target_price` 라는 **이름이 같다는 이유로**
    VB 와 같은 뜻으로 읽었다. 소스에서 그 값이 `flag_high + (pole_high - pole_start)`
    꼴의 `BinOp` 임을 확인해, 누군가 "정리" 하며 `target_price` 에 돌파선을 넣으면
    이 테스트가 먼저 붉어지고 매핑을 다시 보게 한다.
    """
    dicts = _buy_signal_dicts("bull_flag_breakout")
    assert dicts, "BFB `buy_signals` 리터럴을 못 찾았다"
    found = None
    for d in dicts:
        for k, v in zip(d.keys, d.values):
            if isinstance(k, ast.Constant) and k.value == "target_price":
                found = v
    assert found is not None, "BFB `buy_signals` 에 `target_price` 가 없다"
    assert isinstance(found, ast.BinOp), (
        "BFB `target_price` 가 더 이상 계산식이 아니다 — `_BREAKOUT_LINE_KEYS` 재검토"
    )
    src = ast.dump(found)
    assert "pole_high" in src and "pole_start" in src, (
        f"BFB `target_price` 가 폴 높이를 더하지 않는다 — {src}"
    )


@pytest.mark.parametrize("sid", sorted(_EXPECTED_BREAKOUT_KEYS))
def test_w2d_na_keys_agree_with_the_breakout_line_map(sid: str) -> None:
    """W2 — 「해당 없음」 선언과 돌파선 매핑이 **서로 모순되지 않는다**.

    돌파선이 있으면 `target_won`/`breakout_excess_bp` 는 NA 가 아니고, 없으면 NA 다.
    두 모듈이 갈리면 `entry_rule`("돌파선 대비 +4% 초과 추격 금지")과
    `not_applicable`("목표가 개념이 없다")이 같은 프롬프트 안에서 모순된다 —
    그게 이 사이클 검증이 잡은 MEDIUM 이다.
    """
    na = set(_lf()._SNAPSHOT_NA_KEYS.get(sid, ()))
    has_line = bool(_EXPECTED_BREAKOUT_KEYS[sid])
    for key in ("target_won", "breakout_excess_bp"):
        assert (key not in na) is has_line, (
            f"{sid}: 돌파선 {'있음' if has_line else '없음'}인데 `{key}` NA={key in na}"
        )
    assert "k" in na or sid in ("volatility_breakout", "long_tail_volatility"), (
        f"{sid}: 변동성 돌파식 k 는 이 전략에 없다 — NA 여야 한다"
    )


def test_w2e_read_breakout_line_prefers_the_real_line_over_the_target(monkeypatch) -> None:
    """W2 — 같은 신호에 두 키가 다 있어도 BFB 는 `flag_high` 를 고른다(순수 함수 단위).

    `or` 폴백 체인이 아니라 **전략별 명시 매핑**이라는 사실을 잰다 — 체인이면 키 부재에
    우연히 기대는 것이라, 어느 전략이 나중에 `target_price` 를 추가하는 날 조용히 뜻이 바뀐다.
    """
    read = _gate()._read_breakout_line
    sig = {"flag_high": 10_000, "target_price": 11_500, "donchian_high": 9_000,
           "base_high": 8_000}
    assert read("bull_flag_breakout", sig) == 10_000
    assert read("volatility_breakout", sig) == 11_500
    assert read("donchian_swing", sig) == 9_000
    assert read("vcp_breakout", sig) == 8_000
    assert read("momentum", sig) is None
    assert read("kojiro", sig) is None
    # 미등록 전략은 종전 동작(`target_price`) 유지 — 신규 전략이 조용히 죽지 않는다.
    assert read("brand_new_strategy", sig) == 11_500


@pytest.mark.asyncio
async def test_w2f_donchian_prompt_carries_a_real_breakout_excess(monkeypatch) -> None:
    """W2 (검증 HIGH #2) — donchian 주문의 프롬프트에 **실제 돌파선 초과폭**이 실린다.

    배선 전에는 `target_won`/`breakout_excess_bp` 가 키 자체로 빠져 있었고(`_SNAPSHOT_NA_KEYS`),
    BFB 는 측정 이동 목표가 대비 큰 음수가 실렸다. 여기서는 두 전략의 값을 **직접 계산해**
    대조한다.
    """
    mod = _gate()
    h = _setup(monkeypatch, tech={"atr14_pct": 2.0})
    sid = "donchian_swing"
    _observe(
        mod, strategy_id=sid, params=_shadow_params(sid), order_price=80_400,
        signal={"ticker": _TICKER, "price": 80_400, "donchian_high": 80_000,
                "atr": 1_500, "time": "09:12:20"},
    )
    await _drain()

    snapshot = _snapshot_of(h)
    assert snapshot["target_won"] == 80_000, "돌파선이 프롬프트에 안 실렸다"
    expected_bp = (80_400 / 80_000 - 1.0) * 10_000
    assert snapshot["breakout_excess_bp"] == pytest.approx(expected_bp)
    assert expected_bp > 0, "돌파선 위 주문인데 초과폭이 음수다 — 잣대가 뒤집혔다"
    assert "k" not in snapshot, "donchian 에 변동성 돌파식 k 가 실렸다"


@pytest.mark.asyncio
async def test_w2g_bfb_prompt_uses_flag_high_not_the_measured_move(monkeypatch) -> None:
    """W2 (검증 HIGH #2 의 핵심 사례) — BFB 는 `flag_high` 기준으로 채점된다.

    측정 이동 목표가(11,500)를 기준으로 삼으면 10,050원 주문이 −1,260bp 로 실려
    "판단 기준 1: 초과폭이 작으면 되돌림 위험" 이 정반대로 읽힌다.
    """
    mod = _gate()
    h = _setup(monkeypatch, tech={"atr14_pct": 2.0})
    sid = "bull_flag_breakout"
    _observe(
        mod, strategy_id=sid, params=_shadow_params(sid), order_price=10_050,
        signal={"ticker": _TICKER, "price": 10_050, "flag_high": 10_000,
                "target_price": 11_500, "atr": 200, "time": "09:12:20"},
    )
    await _drain()

    snapshot = _snapshot_of(h)
    assert snapshot["target_won"] == 10_000, (
        f"BFB 가 측정 이동 목표가를 돌파선으로 읽었다 — target_won={snapshot['target_won']}"
    )
    assert snapshot["breakout_excess_bp"] == pytest.approx(50.0)
    assert h.upserts[0]["target_won"] == 10_000, "DB 열에도 돌파선이 들어가야 한다"


# ===========================================================================
# W3 — `prompt_version` 배선 (검증 MEDIUM)
# ===========================================================================
@pytest.mark.asyncio
async def test_w3a_persist_stamps_the_strategys_own_prompt_version(monkeypatch) -> None:
    """W3 — `_persist_evaluation` 이 **그 주문의 전략**으로 버전을 계산한다.

    AST 가드(G2-7b)는 "무인자 호출이 없다" 만 재므로 `_prompt_version(payload["ticker"])`
    같은 오배선을 통과시킨다. 그러면 모든 행이 미등록 sid 해시 하나로 찍혀 전략별 버전
    축이 조용히 사라진다.

    **양성 대조군** = 미등록 인자로 계산한 값과 **다름**을 함께 잰다.
    """
    mod = _gate()
    h = _setup(monkeypatch, tech={"atr14_pct": 2.0})
    sid = "vcp_breakout"
    _observe(mod, strategy_id=sid, params=_shadow_params(sid),
             signal={"ticker": _TICKER, "price": 80_400, "base_high": 80_000,
                     "time": "09:12:20"})
    await _drain()

    got = h.upserts[0]["prompt_version"]
    assert got == mod._prompt_version(sid), f"prompt_version={got} != {mod._prompt_version(sid)}"
    assert got != mod._prompt_version(""), "미등록 sid 와 같은 값 — 인자가 안 넘어간다"
    assert got != mod._prompt_version(_TICKER), "종목코드로 계산됐다"


def test_w3b_prompt_version_reflects_the_strategys_snapshot_keys() -> None:
    """W3 — 해시 blob 이 `_SNAPSHOT_KEYS` 전체가 아니라 `snapshot_keys_for(sid)` 를 쓴다.

    전체 튜플을 쓰면 `_SNAPSHOT_NA_KEYS` 를 고쳐 **모델이 보는 키 집합이 바뀌어도**
    버전이 그대로라, "프롬프트 바뀐 전후 행을 섞지 않는다" 가 NA 축에서 뚫린다.

    **양성 대조군** = 건드리지 않은 다른 전략의 버전은 불변이다.
    """
    mod, lf = _gate(), _lf()
    mod.reset_llm_buy_gate_state()
    before_bfb = mod._prompt_version("bull_flag_breakout")
    before_koj = mod._prompt_version("kojiro")

    original = dict(lf._SNAPSHOT_NA_KEYS)
    try:
        lf._SNAPSHOT_NA_KEYS["bull_flag_breakout"] = ("k", "target_won")
        mod.reset_llm_buy_gate_state()
        after_bfb = mod._prompt_version("bull_flag_breakout")
        after_koj = mod._prompt_version("kojiro")
    finally:
        lf._SNAPSHOT_NA_KEYS.clear()
        lf._SNAPSHOT_NA_KEYS.update(original)
        mod.reset_llm_buy_gate_state()

    assert after_bfb != before_bfb, (
        "NA 키를 바꿨는데 prompt_version 이 그대로다 — blob 이 전략별 키 집합을 안 읽는다"
    )
    assert after_koj == before_koj, "건드리지 않은 전략의 버전이 흔들렸다"


# ===========================================================================
# W4 — `_read_stop_loss_pct` 가 라이브 params 를 읽는다 (검증 LOW)
# ===========================================================================
@pytest.mark.parametrize(
    "sid,key",
    [
        ("momentum", "stop_loss_rate"),
        ("volatility_breakout", "stop_loss_rate"),
        ("long_tail_volatility", "intraday_stop_loss"),
        ("donchian_swing", "stop_loss_rate"),
        ("bull_flag_breakout", "stop_loss_rate"),
        ("vcp_breakout", "stop_loss_rate"),
        ("kojiro", "hard_stop_pct"),
    ],
)
def test_w4_stop_loss_pct_follows_the_live_param_override(sid: str, key: str) -> None:
    """W4 — DB 오버라이드(`PUT /api/strategies/{id}/params`)가 관측값에 반영된다.

    `_read_exit_rule` 쪽은 G1-8c 가 잡지만 `stop_loss_pct` 축엔 짝이 없었다 —
    잘못된 키를 읽는 뮤테이션(예: `params.get("stop_loss_rate_typo", -7.0)`)이
    기본값과 구분되지 않아 통과했다. `-11.25` 는 어떤 기본값과도 겹치지 않는 표식이다.

    **양성 대조군** = 기본값 호출도 함께 재서, 항상 오버라이드만 돌려주는 구현을 막는다.
    """
    gate = _gate()
    base = gate._read_stop_loss_pct(sid, _default_params(sid))
    assert base < 0.0, f"{sid}: 기본 손절폭이 음수가 아니다 — {base}"

    params = _default_params(sid)
    params[key] = -11.25
    got = gate._read_stop_loss_pct(sid, params)
    assert got == pytest.approx(-11.25), (
        f"{sid}: `{key}=-11.25` 오버라이드가 stop_loss_pct 에 반영되지 않았다 — {got}"
    )
