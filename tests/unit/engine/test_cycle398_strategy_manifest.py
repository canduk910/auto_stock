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
        "donchian_swing": ("swing_poll", None, False, False, "scale"),
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
    assert CLOSE_AT_1520_IDS == ("volatility_breakout", "long_tail_volatility", "etf_trend")
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
