"""cycle398 PR2(리팩토링 카드 #3) — 등록 명부의 원형(평가 방식) 칸 + 파생 집합 + 교차 검사.

설계 = `_workspace/refactor/2026-10-02_cards_2_3_design.md` §3. 자문 = `_workspace/domain_consult/cycle398_refactor_cards_2_3.md` §2·§3(a).
사용자 결정(10-02): A 원형 선언 = 등록 명부(`StrategyEntry`) 필수 칸(기본값 없음) · B `risk.py:88` 리터럴 유지 + 교차 검사(8영역 무접촉) ·
C 명부에 없는 전략 파일 = 테스트 실패(PR0) · D PR1·PR2 분리.

행위 동일 증명 본체는 `tests/unit/engine/test_cycle398_strategy_wiring_golden.py`(G1~G9, 128 켜짐 조합 전부 초록) 다.
이 파일은 그 골든이 다루지 않는 것 — 명부 칸 자체의 모양(필수 칸 누락 시 실패)과, 명부 파생 집합이
다른 8영역·리터럴 상수와 **갈라지지 않는지**(교차 검사) — 를 담는다.
"""
from __future__ import annotations

import dataclasses

import pytest

from src.engine.strategy_manifest import (
    BREAKOUT_IDS,
    BREAKOUT_SUBSCRIBE_ORDER,
    CLOSE_AT_1520_IDS,
    MARKET_UNIT_SCALE_IDS,
    OPEN_PRICE_TARGET_IDS,
    STRATEGY_MANIFEST,
    SWING_POLL_IDS,
    StrategyEntry,
    _validate_manifest,
)

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# 필수 칸 — 기본값 없음, 누락은 TypeError
# ---------------------------------------------------------------------------
def test_strategy_entry_has_no_defaults():
    """`StrategyEntry` 의 모든 필드가 기본값 없음 — 새 전략이 칸 하나를 빠뜨리면 import 시 터진다."""
    for f in dataclasses.fields(StrategyEntry):
        assert f.default is dataclasses.MISSING, f"{f.name} 에 기본값이 있다 — 명세 위반(카드 #3 ②)"
        assert f.default_factory is dataclasses.MISSING, f"{f.name} 에 default_factory 가 있다"


def test_strategy_entry_missing_field_raises_typeerror():
    """칸 하나(`market_unit_policy`)를 빠뜨리면 `TypeError`(dataclass 필수 인자 누락)."""
    from src.engine.strategies.momentum import MomentumStrategy

    with pytest.raises(TypeError):
        StrategyEntry(  # noqa: missing market_unit_policy on purpose
            cls=MomentumStrategy, strategy_id="momentum", name="상한가 모멘텀",
            enabled=True, weight=1.0, eval_driver="tick_scan",
            breakout_rank=None, open_price_target=False, close_at_1520=False,
        )


def test_strategy_entry_full_fields_ok():
    from src.engine.strategies.momentum import MomentumStrategy

    e = StrategyEntry(
        cls=MomentumStrategy, strategy_id="momentum", name="상한가 모멘텀",
        enabled=True, weight=1.0, eval_driver="tick_scan",
        breakout_rank=None, open_price_target=False, close_at_1520=False,
        market_unit_policy="none",
    )
    assert e.strategy_id == "momentum"


# ---------------------------------------------------------------------------
# 명부 값 — 현행 리터럴과 순서까지 같다(설계 §3.2 표)
# ---------------------------------------------------------------------------
def test_manifest_eval_driver_columns_match_current_literals():
    got = {e.strategy_id: (e.eval_driver, e.breakout_rank, e.open_price_target,
                           e.close_at_1520, e.market_unit_policy) for e in STRATEGY_MANIFEST}
    assert got == {
        "momentum": ("tick_scan", None, False, False, "none"),
        "volatility_breakout": ("tick_breakout", 2, True, True, "none"),
        "long_tail_volatility": ("tick_breakout", 3, True, True, "none"),
        "donchian_swing": ("swing_poll", None, False, True, "scale"),   # cycle405 — 15:20 시간 청산
        "bull_flag_breakout": ("tick_breakout", 0, False, False, "scale"),
        "vcp_breakout": ("tick_breakout", 1, False, False, "scale"),
        "kojiro": ("swing_poll", None, False, False, "scale"),
        "etf_trend": ("swing_poll", None, False, True, "scale"),
    }


def test_derived_sets_match_current_scheduler_literals():
    """파생 집합 네 개가 지금 `scheduler.py` 에 있던 리터럴과 순서까지 같다(설계 §3.3)."""
    assert SWING_POLL_IDS == ("donchian_swing", "kojiro", "etf_trend")
    assert BREAKOUT_IDS == ("volatility_breakout", "long_tail_volatility", "bull_flag_breakout", "vcp_breakout")
    assert BREAKOUT_SUBSCRIBE_ORDER == ("bull_flag_breakout", "vcp_breakout", "volatility_breakout", "long_tail_volatility")
    assert OPEN_PRICE_TARGET_IDS == ("volatility_breakout", "long_tail_volatility")


def test_close_at_1520_ids_value_same_as_open_price_target_but_independent_field():
    """`CLOSE_AT_1520_IDS` 는 지금 값이 `OPEN_PRICE_TARGET_IDS` 와 같지만(VB·LTV) 독립된 선언이다.

    모듈 docstring·설계 §3.3 의 「값이 우연히 같은 다른 사실을 합치지 않는다」 규약 — 필드가
    분리돼 있어야 ETF 가 `open_price_target` 을 건드리지 않고 `close_at_1520` 만 켤 수 있다.
    """
    assert CLOSE_AT_1520_IDS == ("volatility_breakout", "long_tail_volatility", "donchian_swing", "etf_trend")
    assert CLOSE_AT_1520_IDS != OPEN_PRICE_TARGET_IDS  # cycle403 — etf_trend 가 갈라놓았다(독립 축 증거)
    fields = {f.name for f in dataclasses.fields(StrategyEntry)}
    assert {"open_price_target", "close_at_1520"} <= fields, "두 축이 같은 칸으로 합쳐지면 안 된다"


def test_market_unit_scale_ids_registration_order():
    assert MARKET_UNIT_SCALE_IDS == (
        "donchian_swing", "bull_flag_breakout", "vcp_breakout", "kojiro", "etf_trend",
    )


# ---------------------------------------------------------------------------
# 명부 불변식 — import 시 raise(assert 아님)
# ---------------------------------------------------------------------------
def _entry(sid, *, eval_driver, breakout_rank=None, open_price_target=False,
           close_at_1520=False, market_unit_policy="none"):
    from src.engine.strategies.momentum import MomentumStrategy

    return StrategyEntry(
        cls=MomentumStrategy, strategy_id=sid, name=sid, enabled=False, weight=0.0,
        eval_driver=eval_driver, breakout_rank=breakout_rank, open_price_target=open_price_target,
        close_at_1520=close_at_1520, market_unit_policy=market_unit_policy,
    )


def test_validate_manifest_rejects_duplicate_strategy_id():
    bad = (_entry("a", eval_driver="tick_scan"), _entry("a", eval_driver="tick_scan"))
    with pytest.raises(ValueError, match="strategy_id 중복"):
        _validate_manifest(bad)


def test_validate_manifest_rejects_duplicate_breakout_rank():
    bad = (
        _entry("a", eval_driver="tick_breakout", breakout_rank=0),
        _entry("b", eval_driver="tick_breakout", breakout_rank=0),
    )
    with pytest.raises(ValueError, match="breakout_rank 중복"):
        _validate_manifest(bad)


def test_validate_manifest_rejects_tick_breakout_without_rank():
    bad = (_entry("a", eval_driver="tick_breakout", breakout_rank=None),)
    with pytest.raises(ValueError, match="eval_driver=='tick_breakout'"):
        _validate_manifest(bad)


def test_validate_manifest_rejects_rank_without_tick_breakout():
    bad = (_entry("a", eval_driver="tick_scan", breakout_rank=0),)
    with pytest.raises(ValueError, match="eval_driver=='tick_breakout'"):
        _validate_manifest(bad)


def test_validate_manifest_rejects_open_price_target_without_tick_breakout():
    bad = (_entry("a", eval_driver="swing_poll", open_price_target=True),)
    with pytest.raises(ValueError, match="open_price_target=True"):
        _validate_manifest(bad)


def test_validate_manifest_accepts_current_manifest():
    _validate_manifest(STRATEGY_MANIFEST)  # raise 하지 않으면 통과


# ---------------------------------------------------------------------------
# 교차 검사 — 명부 파생이 8영역·다른 리터럴과 갈라지지 않는다(설계 §5.3)
# ---------------------------------------------------------------------------
def test_cross_scheduler_swing_poll_is_manifest_derived():
    from src.engine import scheduler

    assert scheduler._SWING_POLL_STRATEGIES == SWING_POLL_IDS


def test_cross_risk_tick_buy_eval_skip_equals_manifest_swing_poll():
    """결정 B — `risk.py:88` 은 리터럴로 유지하지만 명부의 `swing_poll` 집합과 갈라지면 안 된다.

    폴형 전략을 추가했는데 `risk.py:88` 를 깜빡하면 이 테스트가 붉어진다.
    """
    from src.engine import risk

    assert risk._TICK_BUY_EVAL_SKIP_STRATEGIES == frozenset(SWING_POLL_IDS)


def test_cross_param_catalog_strategy_ids_equals_manifest_order():
    from src.engine import param_catalog

    assert param_catalog.STRATEGY_IDS == tuple(e.strategy_id for e in STRATEGY_MANIFEST)


def test_cross_param_catalog_turtle4_equals_market_unit_scale_ids():
    """cycle403 — `_TURTLE4` 를 `_TURTLE_SIZED`(5전략, etf_trend 추가)로 개명."""
    from src.engine import param_catalog

    assert param_catalog._TURTLE_SIZED == MARKET_UNIT_SCALE_IDS


def test_cross_param_catalog_vbltv_equals_open_price_target_ids():
    from src.engine import param_catalog

    assert param_catalog._VBLTV == OPEN_PRICE_TARGET_IDS


def test_cross_open_price_rest_basis_strategies_equals_open_price_target_ids():
    from src.engine import open_price_rest

    assert open_price_rest._BASIS_STRATEGIES == OPEN_PRICE_TARGET_IDS


def test_cross_status_exit_watch_group_matches_manifest_axes():
    """그룹1=시가목표가(VB·LTV) · 그룹2=나머지 돌파(BFB·VCP) · 그룹3 ⊇ 스윙 폴(donchian·kojiro)."""
    from src.engine import status_exit_watch

    group = status_exit_watch._GROUP
    assert {sid for sid, g in group.items() if g == 1} == set(OPEN_PRICE_TARGET_IDS)
    assert {sid for sid, g in group.items() if g == 2} == set(BREAKOUT_IDS) - set(OPEN_PRICE_TARGET_IDS)
    assert set(SWING_POLL_IDS) <= {sid for sid, g in group.items() if g == 3}


def test_cross_market_unit_turtle_files_matches_market_unit_scale_ids():
    """`tests/unit/ast/test_cycle382_ast_market_unit.py::TURTLE_FILES` 와 같은 전략 집합.

    cycle403 — `etf_trend` 는 `MARKET_UNIT_SCALE_IDS`(시장 유닛 적용 대상)에는 들지만
    cycle382 `TURTLE_FILES` 에는 **일부러** 넣지 않는다. 그 AST 모음은 `donchian_swing`
    의 내부 구조(별도 `_scan_universe` 메서드·`_turtle_buy_quantity` 분리 함수 등)를
    전제로 짠 정밀 구조 검사라, 구조가 다른 `etf_trend` 를 끼워 넣으면 "시장 유닛 적용"
    과 무관한 donchian 고유 관례(함수 이름 등)까지 강제하게 된다. 행위 검증은
    `tests/unit/engine/test_cycle403_etf_trend_strategy.py`/`test_cycle403_etf_trend_wiring.py`
    가 이미 전담한다.
    """
    from tests.unit.ast.test_cycle382_ast_market_unit import TURTLE_FILES

    assert set(TURTLE_FILES.values()) | {"etf_trend"} == set(MARKET_UNIT_SCALE_IDS)


def test_cross_cycle382_support_turtle4_matches_ast_turtle_files():
    """리팩토링 카드 #3(cycle421) — 시장 유닛 행위 테스트의 픽스처 목록(`_cycle382_support.TURTLE4`)도
    위 AST 목록과 같은 이유로 `etf_trend` 를 일부러 뺀다(후보 dict·`_scan_universe`·`_turtle_buy_quantity`
    등 donchian 모양 픽스처 — cycle421 실측: 넣으면 14건이 픽스처 모양 탓으로 붉다). 두 목록이 갈라지면
    여기서 붉어진다 — 새 `"scale"` 전략은 위 단언(명부 ↔ AST 목록)에서 먼저 결정을 강요받는다.
    """
    from tests.unit.ast.test_cycle382_ast_market_unit import TURTLE_FILES
    from tests.unit.engine._cycle382_support import TURTLE4

    assert set(TURTLE4) == set(TURTLE_FILES.values())


def test_cross_multiday_and_status_gate_sids_subset_of_manifest():
    from src.engine import strategy_base

    manifest_ids = {e.strategy_id for e in STRATEGY_MANIFEST}
    assert strategy_base.Position._MULTIDAY_STRATEGIES <= manifest_ids
    assert strategy_base._ALWAYS_STATUS_GATE_CANDIDATE_SIDS <= manifest_ids


def test_cross_default_tradable_boards_keys_subset_of_manifest():
    from src.engine import session

    manifest_ids = {e.strategy_id for e in STRATEGY_MANIFEST}
    assert set(session._DEFAULT_TRADABLE_BOARDS) <= manifest_ids


def test_cross_strategy_census_equals_manifest():
    """결정 C — 전략 디렉터리 파일 집합 == 등록 명부 id 집합(PR0 와 같은 단언, 명부 축에서 한 번 더)."""
    from tests._strategy_census import STRATEGY_IDS

    assert set(STRATEGY_IDS) == {e.strategy_id for e in STRATEGY_MANIFEST}


# ---------------------------------------------------------------------------
# 원형 계약 (리팩토링 카드 #4, cycle421) — 명부 칸이 약속하는 메서드·표식을 클래스가 실제로 갖는다
#
# `scheduler.py` 는 원형별 메서드·표식을 **이름으로** 찾고, 없으면 `hasattr`/`getattr(…, set())`
# 로 조용히 건너뛴다. 칸만 채우고 메서드를 빠뜨린 새 전략은 예외 없이 무매매(또는 거름 없음)가
# 된다. 아래 표가 「scheduler 를 읽어야 아는 약속」 을 실패 메시지로 바꾼다.
#
# | 명부 칸 | 요구 | scheduler/엔진이 읽는 자리 | 빠지면 |
# |---|---|---|---|
# | `eval_driver="tick_breakout"` | `get_scanned_tickers()` | `_collect_breakout_tickers` · `_reprepare_breakout_if_empty` (hasattr) | 구독 0 = 무매매 |
# | `eval_driver="swing_poll"` | `get_scanned_tickers()` | `_swing_buy_poll_loop` · `_collect_swing_tickers` | 예외 로그 뒤 후보 0 = 무매매 |
# | 〃 | 인스턴스 `_bought_today: set` | `_swing_buy_poll_loop` (`getattr(…, set())`) | 폴 중복 진입 거름이 조용히 빈다 |
# | 〃 | `async recompute_held_atr()` | `_boot` 보유 재계산 (hasattr) | 재시작 뒤 보유 ATR·단계 미복구 |
# | `open_price_target=True` | `on_open_price_confirmed()` · `get_targets_status()` · 인스턴스 `_targets`·`_open_confirmed: dict` | `_confirm_breakout_open_prices` (hasattr 둘 다) · 재시도 | 시가 목표가 미확정 = 무매매 |
# | `close_at_1520=True` | `check_force_clear()` | `_force_clear_main_only` (hasattr) | 15:20 청산이 조용히 안 나간다 |
# | `market_unit_policy="scale"` | 클래스 `_MARKET_UNIT_ATR_KEY` ∈ `StrategyBase._SIZING_ATR_KEYS` · `DEFAULT_PARAMS["market_unit_mode"]` · 소스에서 `self._refresh_market_unit` · `self._market_unit_sizing` · `self._market_unit_blocks_entry` 호출 | `StrategyBase` 시장 유닛 헬퍼 · PUT params | 축소 없음(조용히 m=1) |
# | `market_unit_policy="none"` | `_MARKET_UNIT_ATR_KEY is None` · `market_unit_mode` 키 없음 | PUT params `unknown_key` | 끄지 못할 키가 화면에 뜬다 |
#
# `eval_driver="tick_scan"`(momentum)은 전략 메서드가 아니라 `scanner.scan_stocks()` 전역을 쓴다 — 요구 없음.
# 「정의」 = 전략 쪽 클래스 체인(`StrategyBase` 제외)에 있다. `StrategyBase` 에 기본 구현이 생겨도
# 그것으로 통과하지 않는다(빈 기본값 = 조용한 무매매의 재현이다). `force_clear_signal` 은 선택이다
# (없으면 `resolve_force_clear_signal` 이 `FORCE_CLEAR` 로 떨어진다).
# ---------------------------------------------------------------------------
_MU_CALLS = ("_refresh_market_unit", "_market_unit_sizing", "_market_unit_blocks_entry")


def _defined_by_strategy(cls, name: str) -> bool:
    """`StrategyBase`·`object` 를 뺀 클래스 체인이 `name` 을 정의하는가(상속받은 기본값은 아니다)."""
    from src.engine.strategy_base import StrategyBase

    for k in cls.__mro__:
        if k is StrategyBase or k is object:
            return False
        if name in vars(k):
            return True
    return False


def _self_calls(cls) -> set[str]:
    """클래스 소스 안 `self.<이름>(…)` 호출 이름들(AST — 주석·docstring 제외)."""
    import ast
    import inspect
    import textwrap

    tree = ast.parse(textwrap.dedent(inspect.getsource(cls)))
    return {
        n.func.attr for n in ast.walk(tree)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
        and isinstance(n.func.value, ast.Name) and n.func.value.id == "self"
    }


def _archetype_violations(e: StrategyEntry) -> list[str]:
    """명부 행 하나의 원형 계약 위반 목록(빈 목록 = 통과). 메시지는 「무엇이 · 어느 칸 때문에」."""
    import inspect

    from src.engine.strategy_base import StrategyBase, StrategyConfig

    cls = e.cls
    out: list[str] = []

    def need_method(name: str, why: str, *, coroutine: bool = False) -> None:
        if not _defined_by_strategy(cls, name) or not callable(getattr(cls, name, None)):
            out.append(f"{name}() 없음 ({why})")
        elif coroutine and not inspect.iscoroutinefunction(getattr(cls, name)):
            out.append(f"{name}() 가 async 가 아니다 ({why} — scheduler 가 await 한다)")

    inst = cls(StrategyConfig(strategy_id=e.strategy_id, name=e.name))

    def need_instance(name: str, typ: type, why: str) -> None:
        if not isinstance(vars(inst).get(name), typ):
            out.append(f"인스턴스 {name}: {typ.__name__} 없음 ({why})")

    if e.eval_driver == "tick_breakout":
        need_method("get_scanned_tickers", "eval_driver=tick_breakout — 돌파 구독 후보")
    if e.eval_driver == "swing_poll":
        need_method("get_scanned_tickers", "eval_driver=swing_poll — 폴 후보")
        need_instance("_bought_today", set, "eval_driver=swing_poll — 폴 중복 진입 거름")
        need_method("recompute_held_atr", "eval_driver=swing_poll — 재시작 보유 재계산", coroutine=True)
    if e.open_price_target:
        need_method("on_open_price_confirmed", "open_price_target=True — 시가 확정 통지")
        need_method("get_targets_status", "open_price_target=True — 시가 확정 계측")
        need_instance("_targets", dict, "open_price_target=True — 목표가 표")
        need_instance("_open_confirmed", dict, "open_price_target=True — 보드별 시가 확정")
    if e.close_at_1520:
        need_method("check_force_clear", "close_at_1520=True — 15:20 청산 대상")

    defaults = getattr(cls, "DEFAULT_PARAMS", {}) or {}
    atr_key = getattr(cls, "_MARKET_UNIT_ATR_KEY", None)
    if e.market_unit_policy == "scale":
        if not _defined_by_strategy(cls, "_MARKET_UNIT_ATR_KEY") or atr_key not in StrategyBase._SIZING_ATR_KEYS:
            out.append(f"_MARKET_UNIT_ATR_KEY={atr_key!r} — market_unit_policy=scale 은 "
                       f"{StrategyBase._SIZING_ATR_KEYS} 중 하나를 클래스에 둔다")
        if "market_unit_mode" not in defaults:
            out.append("DEFAULT_PARAMS 에 market_unit_mode 없음 (market_unit_policy=scale — 킬스위치)")
        missing = [c for c in _MU_CALLS if c not in _self_calls(cls)]
        if missing:
            out.append(f"시장 유닛 헬퍼 호출 없음 {missing} (market_unit_policy=scale)")
    else:
        if atr_key is not None:
            out.append(f"_MARKET_UNIT_ATR_KEY={atr_key!r} — market_unit_policy=none 인데 값이 있다")
        if "market_unit_mode" in defaults:
            out.append("DEFAULT_PARAMS 에 market_unit_mode 가 있다 (market_unit_policy=none — 끄지 못할 키)")
    return out


@pytest.mark.parametrize("entry", STRATEGY_MANIFEST, ids=lambda e: e.strategy_id)
def test_archetype_contract_every_manifest_entry_has_what_its_columns_promise(entry):
    """카드 #4 — 명부 행마다 원형 칸이 약속하는 메서드·표식을 그 클래스가 실제로 갖는다."""
    assert _archetype_violations(entry) == [], (
        f"{entry.strategy_id}({entry.cls.__name__}) 원형 계약 위반 — scheduler 는 이것들을 "
        f"이름으로 찾고 없으면 조용히 건너뛴다: {_archetype_violations(entry)}"
    )


def _bare_class():
    """원형 메서드를 하나도 갖지 않은 최소 전략(음성 대조용)."""
    from src.engine.strategy_base import Signal, StrategyBase

    class _BareStrategy(StrategyBase):
        async def prepare(self, *, as_of=None):  # pragma: no cover
            return None

        def check_buy_signal(self, ticker, current_price, open_price):  # pragma: no cover
            return Signal.NONE

        def check_exit_signal(self, ticker, current_price, open_price):  # pragma: no cover
            return Signal.NONE

        def calc_buy_quantity(self, current_price, ticker=None):  # pragma: no cover
            return self._apply_budget_limit(0, current_price, ticker)

    return _BareStrategy


def _bare_entry(**cols) -> StrategyEntry:
    base = dict(eval_driver="tick_scan", breakout_rank=None, open_price_target=False,
                close_at_1520=False, market_unit_policy="none")
    base.update(cols)
    return StrategyEntry(cls=_bare_class(), strategy_id="zz_bare", name="zz_bare",
                         enabled=False, weight=0.0, **base)


@pytest.mark.parametrize(("cols", "must_name"), [
    (dict(eval_driver="swing_poll"), ("get_scanned_tickers", "_bought_today", "recompute_held_atr")),
    (dict(eval_driver="tick_breakout", breakout_rank=9), ("get_scanned_tickers",)),
    (dict(eval_driver="tick_breakout", breakout_rank=9, open_price_target=True),
     ("on_open_price_confirmed", "get_targets_status", "_targets", "_open_confirmed")),
    (dict(close_at_1520=True), ("check_force_clear",)),
    (dict(market_unit_policy="scale"), ("_MARKET_UNIT_ATR_KEY", "market_unit_mode", "_refresh_market_unit")),
], ids=["swing_poll", "tick_breakout", "open_price_target", "close_at_1520", "scale"])
def test_archetype_contract_negative_control_bare_class_is_flagged(cols, must_name):
    """음성 대조 — 칸만 채우고 메서드를 빠뜨린 전략은 위반으로 잡힌다(검사가 공허하지 않다)."""
    got = _archetype_violations(_bare_entry(**cols))
    for name in must_name:
        assert any(name in v for v in got), f"{cols}: {name} 누락을 잡지 못했다 — {got}"


def test_archetype_contract_bare_tick_scan_none_has_no_requirements():
    """대조 — 요구가 없는 원형(tick_scan · none)은 빈 클래스도 통과한다(검사가 무조건 붉지 않다)."""
    assert _archetype_violations(_bare_entry()) == []


def test_archetype_contract_base_class_default_does_not_satisfy(monkeypatch):
    """「상속 아님」 — `StrategyBase` 에 빈 기본 구현이 생겨도 그것으로 통과하지 않는다."""
    from src.engine.strategy_base import StrategyBase

    monkeypatch.setattr(StrategyBase, "get_scanned_tickers", lambda self: [], raising=False)
    monkeypatch.setattr(StrategyBase, "check_force_clear", lambda self: [], raising=False)
    got = _archetype_violations(_bare_entry(eval_driver="tick_breakout", breakout_rank=9, close_at_1520=True))
    assert any("get_scanned_tickers" in v for v in got), got
    assert any("check_force_clear" in v for v in got), got


def test_archetype_contract_sync_recompute_is_flagged():
    """`recompute_held_atr` 가 동기 함수면 scheduler 의 `await` 가 TypeError — 원형 위반으로 잡는다."""
    bare = _bare_class()

    class _SyncRecompute(bare):
        def __init__(self, config):
            super().__init__(config)
            self._bought_today: set[str] = set()

        def get_scanned_tickers(self):  # pragma: no cover
            return []

        def recompute_held_atr(self):  # pragma: no cover
            return None

    e = dataclasses.replace(_bare_entry(eval_driver="swing_poll"), cls=_SyncRecompute)
    got = _archetype_violations(e)
    assert got == [next(v for v in got if "recompute_held_atr" in v)], got
    assert "async" in got[0]
