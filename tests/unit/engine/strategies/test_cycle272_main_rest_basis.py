"""cycle272 Red — `main` 목표가 기준가 출처 게이트 (VB + LTV). 계약 C1~C4·C6·C8~C10.

명세 정본 = `_workspace/red/cycle272_rest_open_basis_spec.md`
자문 정본 = `_workspace/domain_consult/cycle272_rest_open_basis_20260910.md`
사용자 결정 D1 (2026-09-10) = *"체크할 필요가 없이 KRX시가를 쓰는게 원칙"*

**Red 단계 — 테스트만. `src/` 미변경.** Green = backend-dev.

## 왜

`board=="main"` 목표가의 기준가가 통합 채널 `H0UNCNT0` `fields[7]`(세션 시가 — 프리장
체결이 있었으면 프리장 시가)에서 온다. 3영업일 3자 대조 실측이 **ws 불일치 193/201 ·
REST 343/343 일치** 다. 그래서 `main` 기준가의 출처를 **KRX REST `stck_oprc`(`J`) 하나**로
좁힌다.

좁은 목은 `on_open_price_confirmed` **하나**다 — WS 가 이기는 세 경로(스케줄러 1차 WS
폴링 `scheduler.py:1662` · 2차 REST 폴백 `:1679` · 전략 인라인 확정 `volatility_breakout.py:901`
/ `long_tail_volatility.py:707`)가 전부 이 setter 로 수렴한다. setter 첫 문장에 출처
게이트를 달면 셋이 한 곳에서 닫히고, `source` 기본값을 **`"ws"`(불신)** 으로 두면
WS 3 호출부는 **한 글자도 고치지 않아도** 거부된다 ⇒ `check_buy_signal` byte 동일
⇒ cycle264 `_STRATEGY_PINS` 6개 전부 불변(= "여섯 가지 무접촉" 의 기계적 증거).

## 이 파일이 잠그는 것

| C | 내용 |
|---|---|
| C1 | enforce·main·source 미지정 → `boards["main"]` 미생성 ∧ `_open_confirmed[t]["main"] is not True` |
| C2 | 같은 호출에 `source="rest"` → 현행과 값이 **완전히 같다**(`k_value_krx_main` 격자 포함) |
| C3 | `mode="off"` 는 현행 행위(롤백 경로) · **두 전략 독립** |
| C4 | `pre_nxt`/`post_nxt` 는 mode×source **4조합 전부** byte 동일 |
| C6 | 모드 해석 격자 12종 — `off` 는 대소문자·공백 무시 `off` 뿐, 나머지·예외 전부 enforce |
| C8 | 목표가 부재 동안 `check_buy_signal` → `Signal.NONE` ∧ `_prev_price[t]["main"]` **미기록** |
| C9 | 게이트 관측이 폭발해도 반환값·상태 변화 동일 |
| C10 | `source` 키워드 전용 · 기본 `"ws"` (AST 리터럴 검사는 `test_cycle272_ast_main_rest_basis.py`) |

## 무접촉 6종 (사용자 D1 §범위)

전략 비중 · `position_ratio` · `max_positions` · 랏 캡(K·K_ρ) ·
`open_entry_hold_secs`(90초) · LTV 청산 규약 — **이 파일의 어떤 테스트도 그 값을 바꾸지
않는다.** 특히 C8 은 "90초 보류가 0 으로 롤백돼도 목표가 부재만으로 안전하게 떨어진다" 를
독립으로 증명해 **보류에 대한 의존을 끊는다**(자문 §7-b).

## freezegun 과 타임존 (cycle262 파일 규약 승계)

freezegun 은 naive 문자열을 **UTC** 로 동결한다. KST = UTC + 9h 이고 **KST 09:00 == UTC 00:00**.

    freeze_time("2026-09-11 01:00:00")  →  KST 2026-09-11 10:00:00

C8 은 KST 10:00 에서 잰다 — cycle229 매수컷(15:20)과 cycle262 보류창(09:00~09:01:30)
**둘 다 밖**이라 두 규약이 결과에 섞이지 않는다.

## caplog 규약

이 파일의 모든 로그 단언은 **로거명 + `levelno >= INFO` + 마커 prefix 3중 한정**이다
(CI 루트 로거가 DEBUG 라 실패 흔적 debug 행까지 잡힌다 — cycle252 T2).
"""

from __future__ import annotations

import inspect
import logging

import pytest
from freezegun import freeze_time

from src.engine.session import MarketBoard, session_tracker
from src.engine.strategies.long_tail_volatility import LongTailVolatilityStrategy
from src.engine.strategies.volatility_breakout import VolatilityBreakoutStrategy
from src.engine.strategy_base import Signal, StrategyConfig

pytestmark = pytest.mark.unit

KEY = "open_price_scope_mode"
_M_CONFIG = "[main_rest_basis_config]"

_VB_LOGGER = "src.engine.strategies.volatility_breakout"
_LTV_LOGGER = "src.engine.strategies.long_tail_volatility"
_LEAF_LOGGER = "src.engine.open_price_rest"

_TICKER = "005930"
_PRDY = 70000            # LTV `min_prdy_rate=5.0` 통과용 전일종가
_OPEN = 80000            # REST 가 준 KRX 시가
_WS_OPEN = 79000         # WS 캐시가 실어 온 오염된 프리장 시가
_PREV_RANGE = 1000
_K = 0.5                 # base = 500

_KST_1000 = "2026-09-11 01:00:00"   # KST 2026-09-11(금) 10:00:00

_ABSENT = object()       # "키 자체가 없다" 센티널


# ===========================================================================
# 리그
# ===========================================================================
def _make(cls, sid: str, *, mode=_ABSENT, enabled: bool = True):
    s = cls(StrategyConfig(strategy_id=sid, name=sid, enabled=enabled, weight=0.3))
    if mode is not _ABSENT:
        s.config.params[KEY] = mode
    else:
        s.config.params.pop(KEY, None)
    return s


@pytest.fixture
def vb(monkeypatch):
    from src.engine import scanner

    monkeypatch.setattr(scanner, "ticker_names", {_TICKER: "삼성전자"})
    monkeypatch.setattr(scanner, "ticker_prev_close", {_TICKER: _PRDY})
    monkeypatch.setattr(session_tracker, "_active", frozenset())
    return _make(VolatilityBreakoutStrategy, "volatility_breakout")


@pytest.fixture
def ltv(monkeypatch):
    from src.engine import scanner

    monkeypatch.setattr(scanner, "ticker_names", {_TICKER: "삼성전자"})
    monkeypatch.setattr(scanner, "ticker_prev_close", {_TICKER: _PRDY})
    monkeypatch.setattr(session_tracker, "_active", frozenset())
    return _make(LongTailVolatilityStrategy, "long_tail_volatility")


@pytest.fixture(params=["vb", "ltv"])
def strategy(request, monkeypatch):
    """VB·LTV 동형 계약을 한 번에 — 전략별 분기가 생기면 이 픽스처가 먼저 붉어진다."""
    from src.engine import scanner

    monkeypatch.setattr(scanner, "ticker_names", {_TICKER: "삼성전자"})
    monkeypatch.setattr(scanner, "ticker_prev_close", {_TICKER: _PRDY})
    monkeypatch.setattr(session_tracker, "_active", frozenset())
    if request.param == "vb":
        return _make(VolatilityBreakoutStrategy, "volatility_breakout")
    return _make(LongTailVolatilityStrategy, "long_tail_volatility")


def _activate(board: str) -> None:
    session_tracker._active = frozenset({MarketBoard(board)})


def _seed_target(s, ticker: str = _TICKER, *, prev_range: int = _PREV_RANGE, k: float = _K):
    """prepare() 결과 모사 — `_targets` 직접 시드 (base = prev_range × k)."""
    base = int(prev_range * k)
    s._targets[ticker] = {
        "k": k,
        "prev_range": prev_range,
        "target_offset_base": base,
        "target_offset": base,
        "target_price": 0,
        "open_price": 0,
        "boards": {},
    }
    s._open_confirmed[ticker] = {}
    return base


def _legacy_board_value(base: int, open_price: int, k_mult: float) -> dict:
    """cycle272 **이전** 코드가 만들었을 `boards[board]` 3키 — 현행 산식 그대로."""
    offset = max(int(base * k_mult), 0)
    return {
        "open_price": open_price,
        "target_price": open_price + offset,
        "target_offset": offset,
    }


def _confirmed(s, ticker: str, board: str):
    return (s._open_confirmed.get(ticker) or {}).get(board)


def _boards(s, ticker: str) -> dict:
    return (s._targets.get(ticker) or {}).get("boards") or {}


def _lines(caplog, marker: str) -> list[str]:
    """로거명 + INFO 이상 + prefix 3중 한정."""
    names = (_VB_LOGGER, _LTV_LOGGER, _LEAF_LOGGER)
    return [
        r.getMessage()
        for r in caplog.records
        if r.name in names and r.levelno >= logging.INFO
        and r.getMessage().startswith(marker)
    ]


@pytest.fixture(autouse=True)
def _reset_leaf_caps():
    """마커 cap 은 모듈 전역이라 테스트 간 누수를 끊는다(모듈 부재면 no-op = Red)."""
    def _reset():
        try:
            from src.engine import open_price_rest as leaf
        except Exception:
            return
        fn = getattr(leaf, "reset_main_rest_basis_caps", None)
        if callable(fn):
            fn()

    _reset()
    yield
    _reset()


# ===========================================================================
# C1 — enforce + main + source 미지정(=ws) → 확정하지 않는다
# ===========================================================================

def test_c1_1_enforce_main_ws_source_does_not_create_board(strategy):
    """C1 — 기본 모드(enforce)에서 `source` 미지정 호출은 `main` 을 확정하지 않는다.

    이 한 줄이 세 경로(스케줄러 1차 WS 폴링 · 전략 인라인 확정 · 그 밖의 미래 호출부)를
    **한 곳에서** 닫는다. `source` 기본값이 `"ws"`(불신)이라 호출부는 무변경이다.
    """
    _seed_target(strategy)
    strategy.on_open_price_confirmed(_TICKER, _OPEN, board="main")

    assert "main" not in _boards(strategy, _TICKER), (
        f"{strategy.strategy_id}: enforce 인데 WS 출처가 `boards['main']` 을 만들었다 — "
        f"실측 {_boards(strategy, _TICKER)!r}"
    )
    assert _confirmed(strategy, _TICKER, "main") is not True, (
        f"{strategy.strategy_id}: `_open_confirmed[{_TICKER}]['main']` 이 True 가 됐다"
    )


def test_c1_2_enforce_main_ws_source_leaves_top_level_compat_empty(strategy):
    """C1 — top-level 호환 필드(`open_price`/`target_price`)도 오염되지 않는다.

    대시보드·AI 자문이 읽는 필드다. 여기에 오염된 값이 남으면 게이트를 통과한 셈이다.
    """
    _seed_target(strategy)
    strategy.on_open_price_confirmed(_TICKER, _OPEN, board="main")

    info = strategy._targets[_TICKER]
    assert info["open_price"] == 0 and info["target_price"] == 0, (
        f"{strategy.strategy_id}: top-level 호환 필드가 WS 값으로 채워졌다 — {info!r}"
    )


def test_c1_3_enforce_main_ws_source_returns_none_and_raises_nothing(strategy):
    """C1 — 거부는 **조용한 return** 이다(예외 전파 금지).

    이 setter 는 `risk.on_tick` → `check_buy_signal` 인라인 경로에서도 불린다.
    거부가 예외면 `handler.py` `[callback_exception]` → **WS 재연결**로 번진다.
    """
    _seed_target(strategy)
    assert strategy.on_open_price_confirmed(_TICKER, _OPEN, board="main") is None


def test_c1_4_gate_emits_config_canary_once(strategy, caplog):
    """C1 — 거부 시 `[main_rest_basis_config]` 카나리아가 그날 1행 남는다.

    **fail-open 이 침묵과 짝이 되면 안 된다**(cycle245 `[ratio_cap_config]` 선례).
    운영자가 "지금 enforce 인가 off 인가" 를 로그 한 줄로 확인할 수 있어야 한다.
    """
    for name in (_VB_LOGGER, _LTV_LOGGER, _LEAF_LOGGER):
        caplog.set_level(logging.INFO, logger=name)
    _seed_target(strategy)
    strategy.on_open_price_confirmed(_TICKER, _OPEN, board="main")
    strategy.on_open_price_confirmed(_TICKER, _OPEN + 100, board="main")

    lines = _lines(caplog, _M_CONFIG)
    assert len(lines) == 1, f"카나리아는 1회/(전략,모드,emitter)/일 — 실측 {lines!r}"
    assert "mode=enforce" in lines[0] and f"strategy={strategy.strategy_id}" in lines[0]
    assert "raw=" in lines[0], (
        "오타로 롤백이 조용히 실패하는 것을 막으려면 **원문 값**을 병기해야 한다"
        f"(`mode=enforce raw=\"of\"`) — 실측 {lines[0]!r}"
    )


# ===========================================================================
# C2 — source="rest" 는 현행과 값이 완전히 같다
# ===========================================================================

@pytest.mark.parametrize("k_mult", [0.0, 0.5, 1.0, 1.2, 2.0])
def test_c2_1_rest_source_board_values_match_legacy(strategy, k_mult):
    """C2 — `source="rest"` 경로의 `boards["main"]` 3키가 **현행 산식과 동일**하다.

    게이트는 *출처*만 가른다 — 목표가 산식(`open + max(int(base × k), 0)`)에는
    한 글자도 개입하지 않는다. `k_value_krx_main` 격자로 그것을 잰다.
    """
    base = _seed_target(strategy)
    strategy.config.params["k_value_krx_main"] = k_mult

    strategy.on_open_price_confirmed(_TICKER, _OPEN, board="main", source="rest")

    assert _boards(strategy, _TICKER).get("main") == _legacy_board_value(base, _OPEN, k_mult), (
        f"{strategy.strategy_id} k={k_mult}: REST 경로가 현행과 다른 값을 만들었다 — "
        f"실측 {_boards(strategy, _TICKER).get('main')!r}"
    )
    assert _confirmed(strategy, _TICKER, "main") is True


def test_c2_2_rest_source_writes_top_level_compat(strategy):
    """C2 — top-level 호환 필드도 현행과 동일하게 채워진다(첫 확정 보드 규약)."""
    base = _seed_target(strategy)
    strategy.config.params["k_value_krx_main"] = 1.0
    strategy.on_open_price_confirmed(_TICKER, _OPEN, board="main", source="rest")

    info = strategy._targets[_TICKER]
    assert (info["open_price"], info["target_price"], info["target_offset"]) == (
        _OPEN, _OPEN + base, base,
    )


def test_c2_3_rest_source_keeps_guard_on_unknown_ticker_and_nonpositive_open(strategy):
    """C2 — 게이트가 현행 가드(미시드 종목 · `open_price <= 0`)를 **약화하지 않는다**."""
    strategy.on_open_price_confirmed("000660", _OPEN, board="main", source="rest")
    assert "000660" not in strategy._targets

    _seed_target(strategy)
    strategy.on_open_price_confirmed(_TICKER, 0, board="main", source="rest")
    assert "main" not in _boards(strategy, _TICKER)
    strategy.on_open_price_confirmed(_TICKER, -1, board="main", source="rest")
    assert "main" not in _boards(strategy, _TICKER)


# ===========================================================================
# C3 — 킬스위치 off = cycle271 이전 행위 (전략별 독립)
# ===========================================================================

def test_c3_1_mode_off_allows_ws_source(strategy):
    """C3 — `off` 는 살아 있는 롤백 경로다. WS 출처가 현행대로 확정한다."""
    base = _seed_target(strategy)
    strategy.config.params[KEY] = "off"
    strategy.config.params["k_value_krx_main"] = 1.0

    strategy.on_open_price_confirmed(_TICKER, _WS_OPEN, board="main")

    assert _boards(strategy, _TICKER).get("main") == _legacy_board_value(base, _WS_OPEN, 1.0)
    assert _confirmed(strategy, _TICKER, "main") is True


def test_c3_2_mode_is_independent_per_strategy(vb, ltv):
    """C3 — 전략별 키다. "VB 만 off" 부분 롤백이 성립한다(상호 import 금지의 실증).

    한 전략의 params 가 다른 전략의 판정에 새면 부분 롤백이 무의미해진다.
    """
    vb.config.params[KEY] = "off"
    ltv.config.params[KEY] = "enforce"
    _seed_target(vb)
    _seed_target(ltv)

    vb.on_open_price_confirmed(_TICKER, _WS_OPEN, board="main")
    ltv.on_open_price_confirmed(_TICKER, _WS_OPEN, board="main")

    assert _confirmed(vb, _TICKER, "main") is True, "VB off — 확정돼야 한다"
    assert _confirmed(ltv, _TICKER, "main") is not True, "LTV enforce — 거부돼야 한다"


def test_c3_3_mode_off_still_accepts_rest_source(strategy):
    """C3 — off 에서도 REST 출처는 당연히 확정된다(신뢰 목록은 모드와 무관)."""
    base = _seed_target(strategy)
    strategy.config.params[KEY] = "off"
    strategy.config.params["k_value_krx_main"] = 1.0
    strategy.on_open_price_confirmed(_TICKER, _OPEN, board="main", source="rest")
    assert _boards(strategy, _TICKER).get("main") == _legacy_board_value(base, _OPEN, 1.0)


def test_c3_4_default_params_declare_enforce(strategy):
    """C3 — 키는 **VB·LTV 각각의** `DEFAULT_PARAMS` 에 값 `"enforce"` 로 존재한다.

    "키 부재 = 새 행위" 는 P0-1(유령 키)의 역방향 위험이다. 소스에 키가 박혀 있으면
    DB 오버레이(`_load_strategy_config` · `PUT /params` 둘 다 `if key in params`)는
    **알려진 키만** 덮으므로 운영에서 키가 사라지는 경로는 소스 삭제뿐이다.
    """
    assert strategy.DEFAULT_PARAMS.get(KEY) == "enforce", (
        f"{strategy.strategy_id}.DEFAULT_PARAMS['{KEY}'] 가 'enforce' 여야 한다 — "
        f"실측 {strategy.DEFAULT_PARAMS.get(KEY)!r}"
    )


# ===========================================================================
# C4 — pre_nxt / post_nxt 는 mode × source 4조합 전부 byte 동일
# ===========================================================================

@pytest.mark.parametrize("board,k_key,k_mult", [
    ("pre_nxt", "k_value_nxt_pre", 0.5),
    ("pre_nxt", "k_value_nxt_pre", 1.0),
    ("post_nxt", "k_value_nxt_post", 1.0),
])
@pytest.mark.parametrize("mode", ["enforce", "off"])
@pytest.mark.parametrize("source", [None, "rest"])
def test_c4_1_non_main_boards_unchanged(strategy, board, k_key, k_mult, mode, source):
    """C4 — 게이트 스코프는 `board == "main"` 이다. 다른 보드는 **전면 무접촉**.

    LTV 의 08:00~09:00 프리장 확정·목표가·야간 매수는 그 보드의 **올바른** 기준가를
    쓴다(오염이 아니다) — 이 시정이 그것을 건드리면 안 된다.
    `_BOARD_K_KEY` 선택(`k_value_nxt_pre`/`k_value_nxt_post`)까지 함께 잰다.
    """
    base = _seed_target(strategy)
    strategy.config.params[KEY] = mode
    strategy.config.params[k_key] = k_mult
    strategy.config.params["k_value_krx_main"] = 9.0   # main 키가 새면 값이 틀어진다

    if source is None:
        strategy.on_open_price_confirmed(_TICKER, _OPEN, board=board)
    else:
        strategy.on_open_price_confirmed(_TICKER, _OPEN, board=board, source=source)

    assert _boards(strategy, _TICKER).get(board) == _legacy_board_value(base, _OPEN, k_mult), (
        f"{strategy.strategy_id} board={board} mode={mode} source={source}: "
        f"비-main 보드가 바뀌었다 — 실측 {_boards(strategy, _TICKER).get(board)!r}"
    )
    assert _confirmed(strategy, _TICKER, board) is True


def test_c4_2_non_main_board_emits_no_gate_canary(strategy, caplog):
    """C4 — 비-main 보드는 게이트 판정 자체를 받지 않는다(카나리아 0행).

    ① `board != "main"` 조기반환이 **모든 관측·`params` 접근보다 앞**이라는 C5 의
    행위 측 증거다.
    """
    for name in (_VB_LOGGER, _LTV_LOGGER, _LEAF_LOGGER):
        caplog.set_level(logging.INFO, logger=name)
    _seed_target(strategy)
    strategy.on_open_price_confirmed(_TICKER, _OPEN, board="pre_nxt")
    assert _lines(caplog, _M_CONFIG) == []


# ===========================================================================
# C6 — 모드 해석 격자
# ===========================================================================

_OFF_INPUTS = ["off", "OFF", "Off", " off ", "\toff\n"]
_ENFORCE_INPUTS = [
    _ABSENT, None, "", "  ", "enforce", "ENFORCE", " Enforce ",
    "true", "of", "offf", "0", 0, 1, [], {}, {"a": 1}, ("off",), 3.14,
]


@pytest.mark.parametrize("raw", _OFF_INPUTS)
def test_c6_1_resolve_mode_off_inputs(raw):
    """C6 — `off` 로 해석되는 것은 **대소문자·공백 무시 `off`** 뿐이다."""
    from src.engine import open_price_rest as leaf

    assert leaf.resolve_mode({KEY: raw}) == leaf.MODE_OFF, f"raw={raw!r}"


@pytest.mark.parametrize("raw", _ENFORCE_INPUTS)
def test_c6_2_resolve_mode_enforce_inputs(raw):
    """C6 — 부재·`None`·빈값·오타·타입 이상은 **전부 enforce**.

    사용자 D1 "체크할 필요가 없이 KRX 시가를 쓰는 게 원칙" 의 직역이다.
    오타(`"of"`)가 조용히 롤백을 성공시키면 그날 하루 오염된 기준가로 돌아간다.
    """
    from src.engine import open_price_rest as leaf

    params = {} if raw is _ABSENT else {KEY: raw}
    assert leaf.resolve_mode(params) == leaf.MODE_ENFORCE, f"raw={raw!r}"


def test_c6_3_resolve_mode_absorbs_params_exception():
    """C6 — `params` 접근이 예외를 던져도 **enforce** 다."""
    from src.engine import open_price_rest as leaf

    class _Boom(dict):
        def get(self, *a, **kw):
            raise RuntimeError("params 폭발")

    assert leaf.resolve_mode(_Boom()) == leaf.MODE_ENFORCE


def test_c6_4_gate_rejects_when_params_explode(strategy):
    """C6 — 전략 setter 경로에서도 `params` 폭발이 enforce(=거부)로 떨어진다.

    게이트가 터져서 **열리는** 방향(fail-open)은 이 사이클의 목적을 통째로 무효화한다.
    """
    class _Boom(dict):
        def get(self, *a, **kw):
            raise RuntimeError("params 폭발")

    _seed_target(strategy)
    boom = _Boom(strategy.config.params)
    strategy.config.params = boom

    strategy.on_open_price_confirmed(_TICKER, _OPEN, board="main")
    assert _confirmed(strategy, _TICKER, "main") is not True


def test_c6_5_gate_still_passes_rest_when_params_explode(strategy):
    """C6/C5 — `params` 가 폭발해도 **REST 경로는 구조적으로 면역**이다.

    ②(신뢰 목록 검사)가 ③(`try`/`params` 접근)보다 앞이라는 계약의 행위 측 증거.
    이 순서가 뒤집히면 "게이트 고장 = 종일 목표가 0" 이라는 P0-1 계열 사고가 성립한다.

    ⚠️ 이 전략은 `k_value_krx_main` 도 `params` 에서 읽으므로 폭발기는 `KEY` 접근만
    던지고 나머지는 정상 위임한다(게이트 순서만 재는 좁은 프로브).
    """
    base = _seed_target(strategy)

    class _BoomOnKey(dict):
        def get(self, key, default=None):
            if key == KEY:
                raise RuntimeError("모드 키 접근 폭발")
            return dict.get(self, key, default)

    strategy.config.params = _BoomOnKey(strategy.config.params)
    strategy.config.params["k_value_krx_main"] = 1.0

    strategy.on_open_price_confirmed(_TICKER, _OPEN, board="main", source="rest")
    assert _boards(strategy, _TICKER).get("main") == _legacy_board_value(base, _OPEN, 1.0)


# ===========================================================================
# C8 — 목표가가 없으면 매수 신호도 없고 baseline 도 안 쓴다
# ===========================================================================

@freeze_time(_KST_1000)
def test_c8_1_no_target_then_signal_none(strategy):
    """C8 — enforce+main 에서 목표가가 없는 동안 `check_buy_signal` 은 `Signal.NONE`.

    **이 계약은 cycle262(90초 보류)에 의존하지 않는다.** 보류가 0 으로 롤백돼도
    "목표가 없으면 신호 없음" 으로 안전하게 떨어져야 한다(자문 §7-b, 무접촉 6종 보호).
    KST 10:00 = 보류 창 밖 · 15:20 컷 밖.

    가격 시리즈는 **구(舊) 경로였다면 반드시 BUY 가 나오도록** 골랐다 — 오염된 WS 시가
    79,000 이 인라인 확정되면 목표가 79,500 이고 (79,200 기록 → 79,800 돌파) 가 정확히
    돌파 순간이다. enforce 에서는 목표선 자체가 없어 두 틱 모두 `Signal.NONE` 이어야 한다.
    """
    base = _seed_target(strategy)
    strategy.config.params["open_entry_hold_secs"] = 0   # 보류 OFF 로 두고도 성립해야 한다
    strategy.config.params["tradable_boards"] = ["main"]
    strategy.config.params["k_value_krx_main"] = 1.0
    _activate("main")

    ws_target = _WS_OPEN + base                          # 79,500 (구 경로가 그었을 선)
    assert strategy.check_buy_signal(_TICKER, ws_target - 300, _WS_OPEN) == Signal.NONE
    assert strategy.check_buy_signal(_TICKER, ws_target + 300, _WS_OPEN) == Signal.NONE, (
        f"{strategy.strategy_id}: 오염된 WS 시가로 그은 목표선에서 돌파가 났다 "
        "— 게이트가 인라인 확정을 막지 못했다"
    )


@freeze_time(_KST_1000)
def test_c8_2_no_target_then_prev_price_not_written(strategy):
    """C8 — 목표가가 없는 동안 `_prev_price[t]["main"]` 을 **쓰지 않는다**.

    조기 return 이 baseline 갱신보다 **앞**이라는 현행 구조의 재확인이다.
    (cycle233 C233-F1 = baseline 동결로 해제 후 거짓 돌파를 만든 그 결함의 반대편 —
    여기서는 아직 목표선이 없으므로 기록 자체가 없어야 하고, REST 확정 후 첫 틱이
    `prev == 0` 으로 **기록만** 하는 현행 구조가 그대로 살아난다.)
    """
    _seed_target(strategy)
    strategy.config.params["open_entry_hold_secs"] = 0
    strategy.config.params["tradable_boards"] = ["main"]
    _activate("main")

    strategy.check_buy_signal(_TICKER, 81000, _WS_OPEN)

    assert (strategy._prev_price.get(_TICKER) or {}).get("main") in (None, 0), (
        f"{strategy.strategy_id}: 목표가가 없는데 baseline 이 기록됐다 — "
        f"실측 {strategy._prev_price.get(_TICKER)!r}"
    )


@freeze_time(_KST_1000)
def test_c8_3_after_rest_confirm_breakout_still_works(strategy):
    """C8 — REST 확정 뒤에는 돌파 판정이 **현행과 동일하게** 성립한다.

    "돌파를 늦게 보는 게 아니라, 잘못 그어 둔 선을 지우고 제대로 긋고 나서 보는 것" —
    첫 틱은 `prev == 0` 이라 기록만, 두 번째 틱이 돌파다(현행 구조 불변).
    """
    base = _seed_target(strategy)
    strategy.config.params["open_entry_hold_secs"] = 0
    strategy.config.params["tradable_boards"] = ["main"]
    strategy.config.params["k_value_krx_main"] = 1.0
    _activate("main")

    strategy.on_open_price_confirmed(_TICKER, _OPEN, board="main", source="rest")
    target = _OPEN + base                                   # 80,500

    assert strategy.check_buy_signal(_TICKER, target - 300, _OPEN) == Signal.NONE  # 기록만
    assert strategy.check_buy_signal(_TICKER, target + 100, _OPEN) == Signal.BUY


# ===========================================================================
# C9 — 게이트 관측이 폭발해도 행위는 같다
# ===========================================================================

def test_c9_1_exploding_logger_does_not_change_rejection(strategy, monkeypatch):
    """C9 — 카나리아 emit 이 폭발해도 거부 결과·상태가 동일하다(cycle262 `test_c10_4` 패턴).

    **행위는 관측 밖**이다. 관측기 하나가 죽어서 오염된 기준가가 통과하면
    이 사이클 전체가 무의미해진다.
    """
    from src.engine import open_price_rest as leaf

    class _BoomLogger:
        def info(self, *a, **kw):
            raise RuntimeError("emit 폭발")

        warning = error = debug = info

    monkeypatch.setattr(leaf, "logger", _BoomLogger(), raising=False)
    _seed_target(strategy)

    strategy.on_open_price_confirmed(_TICKER, _OPEN, board="main")

    assert "main" not in _boards(strategy, _TICKER)
    assert _confirmed(strategy, _TICKER, "main") is not True


def test_c9_2_exploding_logger_does_not_change_rest_confirmation(strategy, monkeypatch):
    """C9 — 폭발기 주입 상태에서도 REST 확정은 정상 값으로 성립한다."""
    from src.engine import open_price_rest as leaf

    class _BoomLogger:
        def info(self, *a, **kw):
            raise RuntimeError("emit 폭발")

        warning = error = debug = info

    monkeypatch.setattr(leaf, "logger", _BoomLogger(), raising=False)
    base = _seed_target(strategy)
    strategy.config.params["k_value_krx_main"] = 1.0

    strategy.on_open_price_confirmed(_TICKER, _OPEN, board="main", source="rest")

    assert _boards(strategy, _TICKER).get("main") == _legacy_board_value(base, _OPEN, 1.0)


# ===========================================================================
# C10 — 시그니처 (행위 측; AST 리터럴 검사는 ast 파일)
# ===========================================================================

def test_c10_1_source_is_keyword_only(strategy):
    """C10 — `source` 는 **키워드 전용**이다.

    위치 인자를 허용하면 `on_open_price_confirmed(t, p, "main", "rest")` 같은 호출이
    생겨나고, 그러면 "누가 REST 를 자처했는가" 를 grep 으로 셀 수 없다.
    """
    _seed_target(strategy)
    with pytest.raises(TypeError):
        strategy.on_open_price_confirmed(_TICKER, _OPEN, "main", "rest")


def test_c10_2_signature_shape(strategy):
    """C10 — `(self, ticker, open_price, board="main", *, source="ws")`."""
    sig = inspect.signature(type(strategy).on_open_price_confirmed)
    params = list(sig.parameters.values())
    names = [p.name for p in params]
    assert names == ["self", "ticker", "open_price", "board", "source"], (
        f"{strategy.strategy_id}: 시그니처가 계약과 다르다 — {names}"
    )
    assert sig.parameters["board"].default == "main"
    assert sig.parameters["source"].kind is inspect.Parameter.KEYWORD_ONLY
    assert sig.parameters["source"].default == "ws", (
        "기본값은 **`ws`(불신)** 이어야 WS 3 호출부가 무변경으로 거부된다 — "
        f"실측 {sig.parameters['source'].default!r}"
    )


def test_c10_3_trusted_sources_literal_is_rest_only():
    """C10 — 신뢰 목록은 `("rest",)` **하나뿐**이다.

    채널 분리(P1-7 B) 뒤 `"ws_krx"` 가 여기에 꽂히도록 남겨 둔 seam 이다.
    지금 `"ws"` 가 들어가면 이 사이클이 통째로 무효가 된다(뮤테이션 M1).
    """
    from src.engine import open_price_rest as leaf

    assert leaf._TRUSTED_MAIN_SOURCES == ("rest",), (
        f"실측 {leaf._TRUSTED_MAIN_SOURCES!r}"
    )
