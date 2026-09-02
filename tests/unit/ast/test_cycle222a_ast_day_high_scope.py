"""cycle222-a — AST 영구 가드: 앵커 blind 내성의 **범위 봉인**.

이번 사이클의 의도적 8영역 접촉은 **`realtime/handler.py` 와 `engine/risk.py` 둘뿐**이다.
나머지 8영역(`websocket_pool.py` / `scanner.py` / `order_engine.py` / `session.py` /
`strategy_registry.py` / `api/order.py` / `auth/**`)은 **diff 0** 이어야 한다.

가드 목록:
- A-1 (HIGH): `risk.on_tick` hot path 계약 — 신규 `await`/DB 호출 0
- A-2 (HIGH): `risk.on_tick` 이 `ticker_prices` 에 쓰는 키 집합 불변 (4키)
- A-3 (HIGH): `risk.py` 에 `stck_hgpr`/`high_price` 문자열 0건 (`day_high` 는 **인자로만** 흐른다)
- A-4: `_run_swing_rest_poll_once` 가 `stck_hgpr` 를 읽되 `ticker_prices` 엔 안 쓴다
- A-5 (HIGH): 나머지 8영역 파일에 `day_high`/`stck_hgpr`/`high_price` 참조 0건
- A-6 (HIGH): `_apply_high_since_buy_from_candles` 경계 `buy_date < bd < today` 양쪽 strict 보존
- A-7: 샹들리에/ATR 트레일 배수 불변 (문제는 트레일 폭이 아니라 기준점)
- A-8: `_SWING_POLL_STRATEGIES` 불변 (매수 폴루프·구독 대상 산정 공유)
- A-9 (HIGH, F7): `register_tick_handler` 등록 경로 봉인 — `day_high=` 키워드를
  못 받는 핸들러가 붙으면 TypeError → handler 재-raise → WS 재연결 오발화
- A-10 (HIGH, F1): `risk` 에 **매수 이후 baseline** 경계 실재 + hot path 계약
- A-11 (HIGH, F3): 09:05 확장이 stale 중립 모드로만 돌고 stale watcher 본체에
  앵커 토큰(`day_high`/`stck_hgpr`/`high_price`) 0건 (cycle240 재스코프 — 종전
  `git diff` 영구 동결은 후속 사이클을 무조건 차단해 내용 검사로 전환)
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SRC = _REPO_ROOT / "src"

_RISK = _SRC / "engine" / "risk.py"
_SCHEDULER = _SRC / "engine" / "scheduler.py"

# 이번 사이클 diff 0 의무 — 8영역 중 handler.py / risk.py 를 **제외한** 전부
_OUT_OF_SCOPE_FILES = [
    _SRC / "engine" / "order_engine.py",
    _SRC / "engine" / "strategy_registry.py",
    _SRC / "engine" / "scanner.py",
    _SRC / "engine" / "session.py",
    _SRC / "api" / "order.py",
    _SRC / "realtime" / "websocket_pool.py",
]
_OUT_OF_SCOPE_DIRS = [_SRC / "auth"]

_PRICE_KEYS = {"current_price", "open_price", "change_rate", "prdy_ctrt"}


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def _func(tree: ast.Module, name: str):
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    return None


def _price_dict_keys(func: ast.AST) -> set[str]:
    """`<name>[ticker] = { ... }` 형태 dict 리터럴의 키 집합 수집."""
    keys: set[str] = set()
    for node in ast.walk(func):
        if not isinstance(node, ast.Assign):
            continue
        if not isinstance(node.value, ast.Dict):
            continue
        if not any(isinstance(t, ast.Subscript) for t in node.targets):
            continue
        for k in node.value.keys:
            if isinstance(k, ast.Constant) and isinstance(k.value, str):
                keys.add(k.value)
    return keys


def _str_constants(func: ast.AST) -> set[str]:
    out: set[str] = set()
    for node in ast.walk(func):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            out.add(node.value)
    return out


# ===========================================================================
# A-1 (HIGH) — hot path 계약: 신규 await / DB 호출 0
# ===========================================================================
def test_a1_on_tick_await_set_unchanged():
    """`on_tick` 본문의 await 는 `order_engine.execute_sell/execute_buy` 2건 뿐.

    앵커 갱신에 `await`/DB write 를 끼우면 on_tick 이 초당 수십~수백 호출되는
    hot path 라 이벤트 루프가 무너지고, `calc_buy_quantity`↔`pending_buys.add`
    원자성(A-ATOMIC) 전제도 흔들린다. 앵커 DB 영속은 **전략 책임**(H-1 계약:
    `update_high` / boot 훅).
    """
    tree = ast.parse(_read(_RISK))
    fn = _func(tree, "on_tick")
    assert fn is not None, "risk.on_tick 미발견"

    awaited = []
    for node in ast.walk(fn):
        if isinstance(node, ast.Await):
            awaited.append(ast.unparse(node.value).split("(")[0])

    assert sorted(awaited) == [
        "self.order_engine.execute_buy",
        "self.order_engine.execute_sell",
    ], f"on_tick await 집합 변경 감지: {sorted(awaited)}"


def test_a1b_on_tick_no_db_calls():
    tree = ast.parse(_read(_RISK))
    fn = _func(tree, "on_tick")
    body = ast.unparse(fn)
    for banned in ("pg.fetch", "pg.execute", "write_log", "update_high", "insert_"):
        assert banned not in body, f"on_tick 에 DB 경로 `{banned}` 유입 — hot path 계약 위반"


# ===========================================================================
# A-2 (HIGH) — ticker_prices 키 집합 불변
# ===========================================================================
def test_a2_on_tick_price_dict_keys_unchanged():
    """`day_high` 는 **함수 인자로만** 흐른다.

    `donchian_swing.py` 의 `daily_high = max(price_info.get("stck_hgpr", 0), ...)`
    블록이 `ticker_prices` 의 `stck_hgpr`/`high_price` 를 읽는다(현재 항상 0 폴백
    = dead read). 값이 채워지면 `daily_high` 가 커져 `ext_pct` 가 올라가고
    **donchian 매수가 더 많이 skip 된다** = 매수 행위 변경.

    ⚠️ 위치는 **심볼로만** 적는다 — 줄번호 인용(`:804-806`)은 cycle223 이 그 위에
       ~227행을 넣으면서 무관한 코드를 가리키게 됐다(실측 시점 실제 위치 `:1033`).
    """
    tree = ast.parse(_read(_RISK))
    fn = _func(tree, "on_tick")
    assert _price_dict_keys(fn) == _PRICE_KEYS


# ===========================================================================
# A-3 (HIGH) — risk.py 에 고가 키 문자열 0건
# ===========================================================================
def test_a3_risk_module_has_no_high_key_literals():
    tree = ast.parse(_read(_RISK))
    offenders = sorted(
        {c for c in _str_constants(tree) if c in ("stck_hgpr", "high_price")}
    )
    assert not offenders, (
        f"risk.py 에 고가 키 문자열 잔존 {offenders} — day_high 는 인자로만 흘러야 한다"
    )


# ===========================================================================
# A-4 — REST 폴은 stck_hgpr 를 읽되 ticker_prices 엔 쓰지 않는다
# ===========================================================================
def test_a4_swing_rest_poll_reads_stck_hgpr():
    tree = ast.parse(_read(_SCHEDULER))
    fn = _func(tree, "_run_swing_rest_poll_once")
    assert fn is not None
    assert "stck_hgpr" in _str_constants(fn), (
        "REST 폴이 같은 응답에 실려 온 stck_hgpr 를 읽지 않는다 — WS stale 구간 보강 0"
    )


def test_a4b_swing_rest_poll_price_dict_keys_unchanged():
    tree = ast.parse(_read(_SCHEDULER))
    fn = _func(tree, "_run_swing_rest_poll_once")
    assert _price_dict_keys(fn) == _PRICE_KEYS


# ===========================================================================
# A-5 (HIGH) — 범위 밖 8영역 diff 0
# ===========================================================================
def _out_of_scope_files():
    for f in _OUT_OF_SCOPE_FILES:
        if f.exists():
            yield f
    for d in _OUT_OF_SCOPE_DIRS:
        if d.exists():
            yield from sorted(d.rglob("*.py"))


@pytest.mark.parametrize("token", ["day_high", "stck_hgpr", "high_price"])
def test_a5_out_of_scope_eight_areas_untouched(token):
    """이번 사이클 의도적 8영역 접촉은 `handler.py` + `risk.py` 둘뿐이다."""
    offenders = [
        str(f.relative_to(_REPO_ROOT)) for f in _out_of_scope_files()
        if token in _read(f)
    ]
    assert not offenders, (
        f"범위 밖 8영역에 `{token}` 유입 — diff 0 절대 조건 위반: {offenders}"
    )


# ===========================================================================
# A-6 (HIGH) — 매수일 봉 배제 경계 보존
# ===========================================================================
def test_a6_candle_recovery_boundary_strict_both_sides():
    """`buy_date < bd < today` 완화 금지.

    매수 전 구간 고가·미확정 봉을 끌어들이면 **과대복구 → 조기 청산**으로 뒤집힌다.
    이번 사이클은 그 경계를 건드리지 않고 **당일 관측**으로 blind 를 메운다.
    """
    from src.engine import strategy_base as sb

    src = inspect.getsource(sb.StrategyBase._apply_high_since_buy_from_candles)
    assert "pos.buy_date < bd < today" in src, (
        "매수일 봉 배제 경계(양쪽 strict)가 변경됐다 — 과대복구 위험"
    )
    assert "<=" not in src.split("pos.buy_date")[1].split("\n")[0], (
        "경계가 `<=` 로 완화됐다"
    )


# ===========================================================================
# A-7 — 샹들리에 / ATR 트레일 배수 불변
# ===========================================================================
def test_a7_chandelier_multipliers_unchanged():
    """문제는 트레일 폭이 아니라 **기준점**이다 — 배수를 건드리면 진단이 오염된다."""
    from src.engine.strategies.kojiro import KojiroStrategy

    params = KojiroStrategy.DEFAULT_PARAMS
    assert params["trail_atr"] == 2.5, "kojiro 2.5ATR 샹들리에 불변 (domain 금기)"
    assert params["breakeven_promote_atr"] == 0.0, (
        "cycle220 브레이크이븐 플로어는 다크런치 상태 유지 (활성화는 별도 결정)"
    )


# ===========================================================================
# A-8 — _SWING_POLL_STRATEGIES 불변 (매수 폴루프·구독 대상 산정 공유)
# ===========================================================================
def test_a8_swing_poll_strategies_unchanged():
    from src.engine import scheduler as sched_mod

    assert sched_mod._SWING_POLL_STRATEGIES == ("donchian_swing", "kojiro")


# ===========================================================================
# A-9 (F7) — 콜백 시그니처 안전성 봉인
#
# `handler._handle_tick` 은 `day_high=` 를 **키워드**로 넘긴다. 기본값이 **수신 측**
# (`RiskManager.on_tick`)에 있으므로, `day_high` 를 받지 못하는 핸들러가
# `register_tick_handler` 로 등록되면 `TypeError` 가 나고 `handler.py` 의
# `except Exception: ... raise` 계약(사이클 88 G-REJECT-1 / 사이클 102 G-CALLBACK1)에
# 걸려 **재연결 trigger 가 오발화**한다.
#
# 전수 확인 결과 `src/` 안의 등록 경로는 `scheduler` 의
# `register_tick_handler(self.risk_manager.on_tick)` **한 곳뿐**이다. 방어 코드를
# 넣으면 위 raise 계약을 깨야 하므로, 대신 **등록 경로를 AST 로 봉인**한다.
# ===========================================================================

_ALLOWED_TICK_HANDLERS = {"self.risk_manager.on_tick"}


def _register_tick_handler_args(py: Path) -> list[str]:
    tree = ast.parse(_read(py))
    out: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        name = getattr(fn, "id", None) or getattr(fn, "attr", None)
        if name != "register_tick_handler":
            continue
        for a in node.args:
            out.append(ast.unparse(a))
    return out


def test_a9_only_risk_on_tick_is_registered_as_tick_handler():
    """등록 경로 전수 — `day_high` 를 못 받는 핸들러가 붙으면 재연결 폭주."""
    found: dict[str, list[str]] = {}
    for py in sorted(_SRC.rglob("*.py")):
        args = _register_tick_handler_args(py)
        if args:
            found[str(py.relative_to(_REPO_ROOT))] = args

    assert found, "register_tick_handler 등록 경로를 하나도 찾지 못했다 (가드 무효화)"
    offenders = {
        f: a for f, a in found.items()
        if set(a) - _ALLOWED_TICK_HANDLERS
    }
    assert not offenders, (
        f"허용되지 않은 tick 핸들러 등록 {offenders} — `day_high=` 키워드를 "
        "받지 못하면 TypeError → handler.py 재-raise → WS 재연결 trigger 오발화. "
        "새 핸들러를 붙이려면 `*, day_high: int = 0`(또는 `**kwargs`)를 반드시 수용하라"
    )


def test_a9b_registered_handler_accepts_day_high_keyword():
    """실제 등록 대상(`RiskManager.on_tick`)이 키워드를 수용하는지 런타임 확인."""
    from src.engine.risk import RiskManager

    sig = inspect.signature(RiskManager.on_tick)
    p = sig.parameters.get("day_high")
    assert p is not None and p.kind is inspect.Parameter.KEYWORD_ONLY
    assert p.default == 0


def test_a9c_handler_passes_day_high_as_keyword():
    """`_handle_tick` 이 positional 로 밀어 넣으면 기존 4-arg 계약이 깨진다."""
    from src.realtime import handler as handler_mod

    src = inspect.getsource(handler_mod._handle_tick)
    assert "day_high=day_high" in src, (
        "day_high 는 키워드 인자로 전달돼야 한다 (positional 추가 = 기존 계약 파괴)"
    )


# ===========================================================================
# A-10 (F1) — 매수 이후 baseline 경계가 코드에 실재하는지 봉인
# ===========================================================================

def test_a10_risk_holds_day_high_baseline_state():
    """`day_high` 채택은 **진입 시점 baseline 초과분** 으로만 한정돼야 한다.

    baseline 이 사라지면 `_apply_high_since_buy_from_candles` 의 양쪽 strict 경계
    (A-6)가 막는 것과 **같은 종류의 오염**(매수 전 구간 고가)이 tick 경로로 무제한
    유입된다 = 진입 직후 브레이크이븐/샹들리에 오발화.
    """
    from src.engine.risk import RiskManager

    src = inspect.getsource(RiskManager)
    assert "_day_high_baseline" in src, (
        "매수 시점 baseline 경계 부재 — 매수 전 고가가 앵커에 유입된다(F1)"
    )
    reset_src = inspect.getsource(RiskManager.reset_daily_state)
    assert "_day_high_baseline" in reset_src, (
        "reset_daily_state 동행 clear 부재 — 정산 후 baseline 잔류"
    )


def test_a10b_baseline_helper_is_sync_and_db_free():
    """baseline 리졸버도 hot path — `await`/DB 금지."""
    tree = ast.parse(_read(_RISK))
    fn = _func(tree, "_day_high_since_entry")
    assert fn is not None, "baseline 리졸버 `_day_high_since_entry` 부재"
    assert not isinstance(fn, ast.AsyncFunctionDef), "baseline 리졸버는 동기여야 한다"
    assert not [n for n in ast.walk(fn) if isinstance(n, ast.Await)], (
        "baseline 리졸버에 `await` 유입 — hot path 계약 위반"
    )
    # 문자열 검사는 docstring 오탐을 피해 **코드 노드** 기준으로만 한다.
    code = "\n".join(
        ast.unparse(n) for n in fn.body
        if not (isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant))
    )
    for banned in ("pg.fetch", "pg.execute", "write_log", "insert_"):
        assert banned not in code, f"baseline 리졸버에 `{banned}` 유입 — hot path 계약 위반"


# ===========================================================================
# A-11 (F3) — 확장 구간이 stale 감지를 약화시키지 않는다
# ===========================================================================

def test_a11_early_window_is_stale_neutral():
    """09:05 확장은 `ticker_last_tick` 중립 모드로만 허용된다.

    stale watcher(`stale_watcher_core.py:215`/`:450`)는 그 dict 하나만 보고 강제
    재구독을 판정하므로, 개장 러시 구간에서 REST 가 타임스탬프를 찍으면
    **이 사이클이 잡으려던 blind 를 스스로 은폐**한다.
    """
    tree = ast.parse(_read(_SCHEDULER))
    loop = _func(tree, "_swing_rest_poll_loop")
    assert loop is not None
    body = ast.unparse(loop)
    assert "SWING_REST_POLL_EARLY_START" in body, "확장 구간 상수 미사용"
    assert "preserve_last_tick" in body and "held_only" in body, (
        "확장 구간이 stale 중립 모드 없이 실행된다 (F3)"
    )


def test_a11b_stale_watcher_core_no_anchor_coupling():
    """이번(cycle222-a) 범위에서 stale watcher 는 **앵커 로직과 얽히지 않는다**.

    ⚠️ **재스코프 (cycle240)** — 종전 구현은 `git diff HEAD -- stale_watcher_core.py`
    공집합을 요구하는 **영구 동결**이었다. cycle222-a 라는 한 사이클의 범위 선언이
    수명을 넘겨, 그 파일에 대한 **모든 후속 시정**(예: cycle240 재구독 desired 교집합)을
    무조건 RED 로 만든다. 사이클 한정 스코프 가드가 영구 가드로 굳는 이 패턴은
    cycle223 G3 가 8영역에서 sha 핀 자기소멸로 이미 해결한 클래스다.

    cycle222-a 의 **실제 의도**는 "앵커(day_high) blind 시정이 stale watcher 와 얽히지
    않는다" 였다. 그 의도를 **내용 기준**(A-5 와 같은 토큰 집합)으로 보존한다 — 파일이
    다른 이유로 바뀌는 것은 허용하되, 앵커 토큰이 스며드는 것은 계속 막는다.
    """
    core = _SRC / "engine" / "stale_watcher_core.py"
    assert core.exists(), f"{core} 미존재"
    src = _read(core)
    hits = [tok for tok in ("day_high", "stck_hgpr", "high_price") if tok in src]
    assert hits == [], (
        "stale watcher 본체에 앵커 토큰이 스몄다 — 재구독 판정은 `ticker_last_tick` "
        f"하나만 본다(A-11 의도). 발견: {hits}"
    )
