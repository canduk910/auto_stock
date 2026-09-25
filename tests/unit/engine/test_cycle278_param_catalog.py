"""cycle278 Red — 파라미터 카탈로그 데이터 계약 (C1~C10 · B01~B24).

정본 명세 = `_workspace/red/cycle278_param_catalog_ui_spec.md` §1 · §3.1 · §7.1.
대상 = `src/engine/param_catalog.py` (103 키의 **단일 진실원**, cycle290 이 99→101 ·
cycle300 이 101→102 · cycle352 가 102→103).

이 사이클은 **사람이 값을 고칠 수단**을 만든다. 값은 한 글자도 바꾸지 않는다 —
전략 7파일 · `strategy_base.py` · `PARAM_RANGES`/`INT_PARAMS` 는 무접촉이고,
그 무접촉은 `tests/unit/ast/test_cycle278_ast_catalog_guards.py` 가 sha 로 잠근다.

## 이 파일이 잠그는 것

* **C1** 7 전략 `DEFAULT_PARAMS` 키 합집합 ≡ 카탈로그 키 집합 (어느 쪽에만 있어도 실패).
  신규 전략·신규 키가 조용히 화면 밖으로 새어 나가는 것이 이 사이클이 고치는 결함이다.
* **C3** `applies_to` 는 그 키를 실제로 가진 전략 집합과 **정확히** 같고 순서는
  `STRATEGY_IDS` 순이며, 빈 `applies_to`(유령 키)는 0건이다.
* **C4/C5** `auto_tunable` ⊆ `PARAM_RANGES` — 카탈로그가 AI 자동 튜닝 집합을 **넓히지 못한다**.
  `range_src="param_ranges"` 인 키의 (min, max) 는 `PARAM_RANGES` 원문과 정확히 같다.
* **C6** 103키(cycle352 이후) × `applies_to` 전수에 대해 **그 전략의 기본값이 카탈로그 범위·자료형 안**이다.
  (기본값이 범위 밖이면 운영자가 아무것도 안 바꾸고 저장만 눌러도 422 가 된다.)
* **C9** `range_src="none"` 이면 `min`/`max` 는 `None` 이다 — 근거 없는 범위를 숫자로 위장하지 않는다.
  특히 `max_scan_stocks`(PARAM_RANGES 상한 500 vs bfb/vcp/kojiro 기본값 4000)를 파생시키면
  3 전략이 전면 저장 불가가 된다(HAZARD-1).
* **C7/C7b/C8** `deprecated` 8키(전부 `editable=False`) · `risk="identity"` 16키
  (cycle290 이 13→15, cycle300 이 15→16) ·
  `deprecated_for` ⊆ `applies_to`.
* **C10** 모듈 순수성 — `src.*` import 0 · 모듈 레벨 부작용 0 · 재로드해도 같은 데이터.

## Red 상태 (작성 시점)

`param_catalog.py` 는 Red 설계 단계에서 이미 작성됐다(명세 §1). 따라서 이 파일의 대부분은
**작성 시점에 초록**이고, 역할은 Green(라우트·화면)이 카탈로그를 건드려 계약을 깨는 것을
막는 **회귀 가드**다. 뮤테이션 M1·M2·M7·M13 이 여기서 죽는다.
"""

from __future__ import annotations

import ast
import dataclasses
import importlib
import re
from functools import lru_cache
from pathlib import Path

import pytest

from src.engine import param_catalog as pc

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parents[3]
_CATALOG_PATH = _ROOT / "src" / "engine" / "param_catalog.py"
_STRATEGY_DIR = _ROOT / "src" / "engine" / "strategies"

#: (전략 id, 파일명, 클래스명) — `STRATEGY_IDS` 와 같은 순서.
_STRATEGY_META: tuple[tuple[str, str, str], ...] = (
    ("momentum", "momentum.py", "MomentumStrategy"),
    ("volatility_breakout", "volatility_breakout.py", "VolatilityBreakoutStrategy"),
    ("long_tail_volatility", "long_tail_volatility.py", "LongTailVolatilityStrategy"),
    ("donchian_swing", "donchian_swing.py", "DonchianSwingStrategy"),
    ("bull_flag_breakout", "bull_flag_breakout.py", "BullFlagBreakoutStrategy"),
    ("vcp_breakout", "vcp_breakout.py", "VcpBreakoutStrategy"),
    ("kojiro", "kojiro.py", "KojiroStrategy"),
)

#: 브리프 3-1 이 못 박은 리스크 정체성 상수 13키. 카탈로그가 2단계 확인 대상을
#: 임의로 넓히거나 좁히지 못한다(C7b).
#: 🔁 cycle290(킬스위치 등재, 2026-09-13) — 청산 수단을 끄는 스위치 2개
#: (`order_exchange_clock_mode`·`after_market_exit_division`)가 추가돼 13→15.
#: 기존 모드 킬스위치(`open_price_scope_mode`·`llm_gate_mode`)와 같은 등급이다.
_BRIEF_IDENTITY_KEYS = frozenset({
    "max_positions",
    "max_lot_units",
    "max_lot_ratio_mult",
    "risk_pct",
    "max_open_risk_pct",
    "sizing_mode",
    "tradable_boards",
    "open_entry_hold_secs",
    "open_price_scope_mode",
    "llm_gate_mode",
    "llm_gate_min_score",
    "llm_gate_daily_call_cap",
    "llm_gate_timeout_secs",
    "order_exchange_clock_mode",
    "after_market_exit_division",
    # cycle300 — 일봉 읽기 깊이. 추세 필터 3선이 몇 봉으로 계산되는지를 정하므로
    # 화면에서 바꾸려면 2단계 확인을 받아야 한다(진입 정체성 축).
    "daily_fetch_depth_mode",
})

#: 명세 §1.3 — **어느 전략에서도** 행위 참조 0건인 잔존 키 8개.
_EXPECTED_DEPRECATED_KEYS = frozenset({
    "max_units_per_stock",
    "max_units_total",
    "quant_min_f_score",
    "quant_max_mf_rank",
    "quant_filter_enabled",
    "rs_filter_enabled",
    "rsi_filter_enabled",
    "rsi_extreme_max",
})

_ALL_SPEC_KEYS = [s.key for s in pc.PARAM_SPECS]


# ---------------------------------------------------------------------------
# 헬퍼 — DEFAULT_PARAMS 추출 (AST: 키 / import: 값)
# ---------------------------------------------------------------------------
def _default_params_keys_via_ast(file_name: str, cls_name: str) -> tuple[str, ...]:
    """`DEFAULT_PARAMS` 의 키를 **AST 로** 뽑는다(값은 `list(...)` 호출을 포함하므로 키만).

    `git grep`/`git ls-files` 를 쓰지 않는 이유 = 추적 파일만 보므로 Green 이 새로 만든
    미추적 파일을 로컬에서 못 보고 CI 에서만 잡는다(cycle259 S4b).
    """
    path = _STRATEGY_DIR / file_name
    src = path.read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if not (isinstance(node, ast.ClassDef) and node.name == cls_name):
            continue
        for stmt in node.body:
            if not isinstance(stmt, ast.Assign):
                continue
            if not any(getattr(t, "id", None) == "DEFAULT_PARAMS" for t in stmt.targets):
                continue
            assert isinstance(stmt.value, ast.Dict), f"{file_name}: DEFAULT_PARAMS 가 dict 리터럴이 아니다"
            keys: list[str] = []
            for k in stmt.value.keys:
                assert isinstance(k, ast.Constant) and isinstance(k.value, str), (
                    f"{file_name}: DEFAULT_PARAMS 키가 문자열 리터럴이 아니다 — 카탈로그 대조 불가"
                )
                keys.append(k.value)
            return tuple(keys)
    raise AssertionError(f"{file_name}::{cls_name} 에서 DEFAULT_PARAMS 를 찾지 못했다")


@lru_cache(maxsize=1)
def _ast_keys() -> dict[str, tuple[str, ...]]:
    return {sid: _default_params_keys_via_ast(fn, cn) for sid, fn, cn in _STRATEGY_META}


@lru_cache(maxsize=1)
def _defaults() -> dict[str, dict]:
    """전략 클래스의 `DEFAULT_PARAMS` **값**(읽기 전용으로만 쓴다)."""
    from src.engine.strategies.bull_flag_breakout import BullFlagBreakoutStrategy
    from src.engine.strategies.donchian_swing import DonchianSwingStrategy
    from src.engine.strategies.kojiro import KojiroStrategy
    from src.engine.strategies.long_tail_volatility import LongTailVolatilityStrategy
    from src.engine.strategies.momentum import MomentumStrategy
    from src.engine.strategies.vcp_breakout import VcpBreakoutStrategy
    from src.engine.strategies.volatility_breakout import VolatilityBreakoutStrategy

    classes = {
        "momentum": MomentumStrategy,
        "volatility_breakout": VolatilityBreakoutStrategy,
        "long_tail_volatility": LongTailVolatilityStrategy,
        "donchian_swing": DonchianSwingStrategy,
        "bull_flag_breakout": BullFlagBreakoutStrategy,
        "vcp_breakout": VcpBreakoutStrategy,
        "kojiro": KojiroStrategy,
    }
    return {sid: dict(cls.DEFAULT_PARAMS) for sid, cls in classes.items()}


def _key_set_mismatch(
    default_keys: frozenset[str], catalog_keys: frozenset[str]
) -> tuple[frozenset[str], frozenset[str]]:
    """(카탈로그 결손, 유령 키). **양방향**이라 어느 쪽에만 있어도 드러난다."""
    return default_keys - catalog_keys, catalog_keys - default_keys


def _param_ranges() -> dict:
    from src.engine.recommendation_engine import PARAM_RANGES

    return PARAM_RANGES


# ===========================================================================
# C1 · C2 — 키 집합 동일성 (M1 을 죽인다)
# ===========================================================================
def test_catalog_when_compared_to_default_params_then_key_sets_identical():
    """B01/C1 — 7 전략 `DEFAULT_PARAMS` 키 합집합 ≡ `all_keys()`.

    한쪽 방향(부분집합)만 보면 신규 키 누락이나 유령 키 중 하나를 놓친다.
    """
    union: set[str] = set()
    for keys in _ast_keys().values():
        union |= set(keys)

    missing, ghost = _key_set_mismatch(frozenset(union), frozenset(pc.all_keys()))
    assert not missing, f"카탈로그에 없는 DEFAULT_PARAMS 키: {sorted(missing)} — 화면에서 편집 불가"
    assert not ghost, f"어느 전략에도 없는 유령 키: {sorted(ghost)}"


def test_catalog_when_counted_then_102_specs_no_duplicates():
    """B02/C2 — 스펙 103개(cycle290 킬스위치 2키로 99→101, cycle300 깊이 스위치로 101→102,
    cycle352 15:20 상한가 유지 확인 킬스위치로 102→103), 키 중복 0."""
    assert len(pc.PARAM_SPECS) == 103, f"스펙 {len(pc.PARAM_SPECS)}개 (기대 103)"
    keys = [s.key for s in pc.PARAM_SPECS]
    dupes = sorted({k for k in keys if keys.count(k) > 1})
    assert not dupes, f"중복 키: {dupes}"
    assert len(pc.SPEC_BY_KEY) == 103


def test_catalog_when_key_missing_from_default_params_then_fails():
    """B03/C1 — **가드 자신의 검증**: 키가 빠지면 대조 헬퍼가 반드시 보고한다.

    B01 의 단언을 부분집합 검사로 약화시키는 뮤테이션(M1 변형)을 여기서 죽인다.
    """
    catalog = frozenset(pc.all_keys())
    victim = sorted(catalog)[0]

    missing, ghost = _key_set_mismatch(catalog, catalog - {victim})
    assert missing == {victim} and not ghost, "카탈로그 결손을 탐지하지 못한다"

    missing2, ghost2 = _key_set_mismatch(catalog - {victim}, catalog)
    assert not missing2 and ghost2 == {victim}, "유령 키를 탐지하지 못한다"


def test_ast_extracted_keys_match_imported_default_params():
    """B01b — AST 추출기(키 대조의 입력) 자체가 클래스 실물과 일치한다."""
    imported = _defaults()
    for sid, keys in _ast_keys().items():
        assert set(keys) == set(imported[sid]), (
            f"{sid}: AST 추출 키가 클래스 `DEFAULT_PARAMS` 와 다르다 — 추출기 결함"
        )


# ===========================================================================
# C3 — applies_to (M2 를 죽인다)
# ===========================================================================
@pytest.mark.parametrize("key", _ALL_SPEC_KEYS)
def test_applies_to_when_compared_then_matches_default_params_exactly(key: str):
    """B04/C3 — 101키(cycle290 이후) 전수: `applies_to` ≡ 그 키를 가진 전략 집합."""
    spec = pc.get_spec(key)
    expected = tuple(sid for sid, _f, _c in _STRATEGY_META if key in _ast_keys()[sid])
    assert spec.applies_to == expected, (
        f"{key}: applies_to={spec.applies_to} 기대={expected} — "
        "화면에서 그 전략의 키가 사라지거나 없는 키가 나타난다"
    )


def test_applies_to_when_ordered_then_follows_strategy_ids_order():
    """B05/C3 — `applies_to` 순서는 `STRATEGY_IDS` 순."""
    order = {sid: i for i, sid in enumerate(pc.STRATEGY_IDS)}
    for spec in pc.PARAM_SPECS:
        idx = [order[sid] for sid in spec.applies_to]
        assert idx == sorted(idx), f"{spec.key}: applies_to 순서가 STRATEGY_IDS 와 다르다"
        assert set(spec.applies_to) <= set(pc.STRATEGY_IDS), f"{spec.key}: 미지 전략 id"


def test_applies_to_when_empty_then_none():
    """B06/C3 — 유령 키(빈 `applies_to`) 0건."""
    empty = [s.key for s in pc.PARAM_SPECS if not s.applies_to]
    assert not empty, f"어느 전략에도 적용되지 않는 키: {empty}"


def test_keys_for_strategy_when_called_then_matches_default_params():
    """C12 전제 — `keys_for_strategy(sid)` ≡ 그 전략의 `DEFAULT_PARAMS` 키 집합.

    스키마 응답의 전략별 `keys` 가 이 헬퍼에서 나온다.
    """
    for sid, keys in _ast_keys().items():
        assert set(pc.keys_for_strategy(sid)) == set(keys), f"{sid}: keys_for_strategy 불일치"


# ===========================================================================
# C4 · C5 — auto_tunable 과 PARAM_RANGES (M7 을 죽인다)
# ===========================================================================
def test_auto_tunable_when_compared_then_subset_of_param_ranges():
    """B07/C4 — 카탈로그가 AI 자동 튜닝 집합을 **넓히지 않는다**.

    UI 편집 가능성과 AI 자동 조정 가능성은 별개다. 카탈로그가 `auto_tunable=True` 를
    임의로 붙이면 자문 적용 경로가 그 키를 밤새 흔들 수 있게 된다.
    """
    extra = set(pc.auto_tunable_keys()) - set(_param_ranges())
    assert not extra, f"PARAM_RANGES 밖인데 auto_tunable=True: {sorted(extra)}"


def test_auto_tunable_when_param_ranges_key_exists_in_defaults_then_marked_true():
    """B08/C5 — `PARAM_RANGES` ∩ (전략 기본값 존재) 24키는 전부 `auto_tunable=True`."""
    union: set[str] = set()
    for keys in _ast_keys().values():
        union |= set(keys)
    live = set(_param_ranges()) & union
    assert len(live) == 24, f"PARAM_RANGES ∩ DEFAULT_PARAMS = {len(live)}키 (기대 24)"
    not_marked = sorted(live - set(pc.auto_tunable_keys()))
    assert not not_marked, f"PARAM_RANGES 키인데 auto_tunable=False: {not_marked}"

    ghost = sorted(set(_param_ranges()) - union)
    assert ghost == ["stop_loss_main", "stop_loss_pre_nxt"], (
        f"PARAM_RANGES 유령 키 목록이 바뀌었다: {ghost} — 카탈로그 24 ↔ PARAM_RANGES 26 의 차이 근거"
    )


def test_range_src_param_ranges_when_read_then_bounds_equal_param_ranges_verbatim():
    """B09/C5 — `range_src="param_ranges"` 키는 원문과 **정확히** 같은 (min, max)."""
    ranges = _param_ranges()
    for spec in pc.PARAM_SPECS:
        if spec.range_src != "param_ranges":
            continue
        assert spec.key in ranges, f"{spec.key}: range_src=param_ranges 인데 PARAM_RANGES 에 없다"
        lo, hi = ranges[spec.key]
        assert (spec.min, spec.max) == (lo, hi), (
            f"{spec.key}: 카탈로그 ({spec.min}, {spec.max}) ≠ PARAM_RANGES ({lo}, {hi})"
        )
        assert spec.auto_tunable is True, f"{spec.key}: PARAM_RANGES 복사본인데 auto_tunable=False"


# ===========================================================================
# C6 — 기본값이 범위·자료형과 모순되지 않는다 (M13 을 죽인다)
# ===========================================================================
@pytest.mark.parametrize("key", _ALL_SPEC_KEYS)
def test_defaults_when_checked_then_within_catalog_range(key: str):
    """B10/C6 — 101키(cycle290 이후) × `applies_to` 전수: 기본값이 `[min, max]` 안.

    기본값이 범위 밖이면 운영자가 **아무것도 바꾸지 않고 저장만 눌러도** 422 다.
    """
    spec = pc.get_spec(key)
    defaults = _defaults()
    for sid in spec.applies_to:
        value = defaults[sid][key]
        if spec.type not in ("int", "float", "percent"):
            continue
        assert isinstance(value, (int, float)) and not isinstance(value, bool), (
            f"{sid}.{key}: 수치 타입인데 기본값 {value!r}"
        )
        if spec.min is not None:
            assert value >= spec.min, f"{sid}.{key}: 기본값 {value} < min {spec.min}"
        if spec.max is not None:
            assert value <= spec.max, f"{sid}.{key}: 기본값 {value} > max {spec.max}"


def test_defaults_when_type_int_then_default_is_int_not_float():
    """B11/C6 — `type="int"` 키의 기본값은 `int`(그리고 `bool` 이 아니다)."""
    defaults = _defaults()
    for spec in pc.PARAM_SPECS:
        if spec.type != "int":
            continue
        for sid in spec.applies_to:
            value = defaults[sid][spec.key]
            assert isinstance(value, int) and not isinstance(value, bool), (
                f"{sid}.{spec.key}: type=int 인데 기본값 {value!r}"
            )


def test_defaults_when_type_enum_then_default_in_choices():
    """B12/C6 — `type="enum"` 기본값은 `choices` 안."""
    defaults = _defaults()
    for spec in pc.PARAM_SPECS:
        if spec.type != "enum":
            continue
        allowed = [c.value for c in spec.choices]
        for sid in spec.applies_to:
            assert defaults[sid][spec.key] in allowed, (
                f"{sid}.{spec.key}: 기본값 {defaults[sid][spec.key]!r} ∉ {allowed}"
            )


def test_defaults_when_type_str_then_default_matches_pattern():
    """B13/C6 — `type="str"` 기본값이 `pattern` 을 통과한다(`entry_start`/`entry_end`).

    형식이 깨지면 `int()` 캐스트가 `check_buy_signal` 안에서 예외를 던져
    `risk.on_tick` 으로 전파된다(HAZARD-8) — 그래서 pattern 은 선택이 아니라 필수다.
    """
    defaults = _defaults()
    seen = []
    for spec in pc.PARAM_SPECS:
        if spec.type != "str":
            continue
        assert spec.pattern, f"{spec.key}: type=str 인데 pattern 이 없다"
        for sid in spec.applies_to:
            value = defaults[sid][spec.key]
            assert isinstance(value, str) and re.match(spec.pattern, value), (
                f"{sid}.{spec.key}: 기본값 {value!r} 이 {spec.pattern} 불일치"
            )
        seen.append(spec.key)
    assert set(seen) == {"entry_start", "entry_end"}, f"str 키 목록이 바뀌었다: {seen}"


def test_defaults_when_type_list_str_then_items_valid():
    """B14/C6 — `list_str` 기본값의 각 항목이 `choices` 또는 `pattern` 을 만족한다."""
    defaults = _defaults()
    for spec in pc.PARAM_SPECS:
        if spec.type != "list_str":
            continue
        allowed = [c.value for c in spec.choices]
        for sid in spec.applies_to:
            value = defaults[sid][spec.key]
            assert isinstance(value, list), f"{sid}.{spec.key}: list 가 아니다 — {value!r}"
            for item in value:
                if allowed:
                    assert item in allowed, f"{sid}.{spec.key}: {item!r} ∉ {allowed}"
                elif spec.pattern:
                    assert re.match(spec.pattern, str(item)), (
                        f"{sid}.{spec.key}: {item!r} 이 {spec.pattern} 불일치"
                    )


# ===========================================================================
# C9 — 범위를 지어내지 않는다 (HAZARD-1 / M13)
# ===========================================================================
def test_max_scan_stocks_when_read_then_range_is_none_not_param_ranges():
    """B15/C9 — `max_scan_stocks` 는 `range_src="none"` 이고 min/max 가 없다.

    `PARAM_RANGES["max_scan_stocks"] = (10, 500)` 인데 bfb·vcp·kojiro 기본값이 4000 이다.
    카탈로그 범위를 PARAM_RANGES 에서 파생시키면 **3 전략이 저장 전면 422** 가 된다.
    """
    spec = pc.get_spec("max_scan_stocks")
    assert spec.range_src == "none", f"range_src={spec.range_src}"
    assert spec.min is None and spec.max is None, f"({spec.min}, {spec.max}) — 근거 없는 범위"

    lo, hi = _param_ranges()["max_scan_stocks"]
    defaults = _defaults()
    over = {sid: defaults[sid]["max_scan_stocks"] for sid in spec.applies_to
            if defaults[sid]["max_scan_stocks"] > hi}
    assert over, "PARAM_RANGES 상한을 넘는 기본값이 사라졌다 — HAZARD-1 전제 재확인 필요"
    assert (lo, hi) == (10, 500)


def test_range_src_none_when_read_then_bounds_are_none():
    """B15b/C9 — `range_src="none"` 인 모든 키(9키)가 min/max 를 갖지 않는다."""
    offenders = [
        (s.key, s.min, s.max) for s in pc.PARAM_SPECS
        if s.range_src == "none" and not (s.min is None and s.max is None)
    ]
    assert not offenders, f"근거 없는 범위를 숫자로 위장: {offenders}"
    assert len([s for s in pc.PARAM_SPECS if s.range_src == "none"]) == 9


# ===========================================================================
# C7 · C7b · C8 — deprecated / identity
# ===========================================================================
def test_deprecated_when_true_then_editable_false():
    """B16/C7 — `deprecated=True` 면 `editable=False`.

    값이 바뀌어도 매매가 안 바뀌는 입력란은 운영자를 속인다.
    """
    bad = [s.key for s in pc.PARAM_SPECS if s.deprecated and s.editable]
    assert not bad, f"deprecated 인데 편집 가능: {bad}"


def test_deprecated_when_listed_then_exactly_eight_keys():
    """B17/C7 — `deprecated` 집합은 정확히 8키(명세 §1.3)."""
    assert frozenset(pc.deprecated_keys()) == _EXPECTED_DEPRECATED_KEYS, (
        f"deprecated={sorted(pc.deprecated_keys())} 기대={sorted(_EXPECTED_DEPRECATED_KEYS)}"
    )


def test_deprecated_for_when_set_then_subset_of_applies_to():
    """B18/C8 — `deprecated_for` ⊆ `applies_to`."""
    for spec in pc.PARAM_SPECS:
        assert set(spec.deprecated_for) <= set(spec.applies_to), (
            f"{spec.key}: deprecated_for={spec.deprecated_for} ⊄ applies_to={spec.applies_to}"
        )


def test_k_value_nxt_post_when_read_then_not_globally_deprecated_but_inactive_for_vb():
    """B19/C8 — §0 정정-2: `k_value_nxt_*` 는 **VB 에서만** 무효다.

    LTV 는 `("pre_nxt","main","post_nxt")` 라 야간 목표가에 실제로 곱한다.
    전역 `deprecated` 로 올리면 LTV 화면에 거짓말을 한다(M16).
    """
    for key in ("k_value_nxt_pre", "k_value_nxt_post"):
        spec = pc.get_spec(key)
        assert spec.deprecated is False, f"{key}: 전역 deprecated 로 올리면 LTV 화면이 거짓말한다"
        assert spec.deprecated_for == ("volatility_breakout",), spec.deprecated_for
        assert "long_tail_volatility" in spec.applies_to
        assert spec.editable is True


def test_identity_when_listed_then_exactly_sixteen_brief_keys():
    """B20/C7b — `risk="identity"` 는 브리프의 16키(cycle290 이 13→15, cycle300 이 15→16)와 정확히 일치한다.

    화면의 2단계 확인 대상을 카탈로그가 임의로 넓히거나 좁히지 못한다.
    """
    got = frozenset(pc.identity_keys())
    assert got == _BRIEF_IDENTITY_KEYS, (
        f"추가={sorted(got - _BRIEF_IDENTITY_KEYS)} 누락={sorted(_BRIEF_IDENTITY_KEYS - got)}"
    )


def test_enum_when_typed_then_choices_non_empty():
    """B21/C6 — `type="enum"` 은 `choices` 없이 성립하지 않는다."""
    for spec in pc.PARAM_SPECS:
        if spec.type == "enum":
            assert spec.choices, f"{spec.key}: enum 인데 choices 가 비었다"
        if spec.choices:
            values = [c.value for c in spec.choices]
            assert len(values) == len(set(map(repr, values))), f"{spec.key}: choices 값 중복"


def test_unit_when_read_then_within_closed_vocabulary():
    """B22/C14 — `unit` 은 닫힌 어휘 12종 안. 화면 포맷터가 **키가 아니라 unit** 으로 분기한다."""
    bad = sorted({s.unit for s in pc.PARAM_SPECS} - set(pc.UNITS))
    assert not bad, f"닫힌 어휘 밖 unit: {bad}"


def test_spec_fields_when_read_then_group_type_risk_range_src_closed_vocab():
    """B22b/C14 — `group`/`type`/`risk`/`range_src` 도 닫힌 어휘 안."""
    for spec in pc.PARAM_SPECS:
        assert spec.group in pc.GROUP_IDS, f"{spec.key}: group={spec.group}"
        assert spec.type in pc.TYPES, f"{spec.key}: type={spec.type}"
        assert spec.risk in pc.RISKS, f"{spec.key}: risk={spec.risk}"
        assert spec.range_src in pc.RANGE_SOURCES, f"{spec.key}: range_src={spec.range_src}"
    assert len(pc.GROUPS) == len(pc.GROUP_IDS) == 7


# ===========================================================================
# C10 — 모듈 순수성
# ===========================================================================
def test_module_when_parsed_then_no_src_imports_and_no_side_effects():
    """B23/C10 — `src.*` import 0 · 모듈 레벨 부작용 0 · I/O 호출 0.

    카탈로그가 엔진을 import 하면 라우트·테스트·도구가 그 무게를 함께 진다.
    """
    tree = ast.parse(_CATALOG_PATH.read_text(encoding="utf-8"))

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert not alias.name.startswith("src."), f"src.* import: {alias.name}"
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            assert not mod.startswith("src"), f"src.* import: {mod}"

    allowed = (ast.Import, ast.ImportFrom, ast.Assign, ast.AnnAssign,
               ast.ClassDef, ast.FunctionDef)
    for stmt in tree.body:
        if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant):
            continue  # docstring
        assert isinstance(stmt, allowed), (
            f"모듈 레벨 실행문: {type(stmt).__name__} (line {stmt.lineno}) — import 만으로 부작용이 생긴다"
        )

    banned = {"open", "print", "requests", "logging", "getenv", "environ"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            fn = node.func
            name = getattr(fn, "id", None) or getattr(fn, "attr", None)
            assert name not in banned, f"금지 호출 {name}() (line {node.lineno})"


def test_module_when_imported_twice_then_specs_identical_objects():
    """B24/C10 — 재import 는 같은 객체, 재로드는 같은 **값** — 부작용 0."""
    again = importlib.import_module("src.engine.param_catalog")
    assert again is pc and again.PARAM_SPECS is pc.PARAM_SPECS

    # ⚠️ `reload` 는 **같은 모듈 객체**에 새 속성을 심는다 — 비교 대상을 먼저 붙잡지 않으면
    #    단언이 자기 자신과의 비교가 되어 공허해진다.
    before_keys = pc.all_keys()
    before_specs = [dataclasses.asdict(s) for s in pc.PARAM_SPECS]
    before_identity = pc.identity_keys()

    # `reload` 는 `ParamSpec` 클래스 자체를 새로 만든다(dataclass `__eq__` 는 클래스 동일성을
    # 요구하므로 인스턴스 직접 비교는 항상 False 다) — 필드 값으로 비교한다.
    reloaded = importlib.reload(pc)
    assert reloaded.all_keys() == before_keys, "재로드가 다른 키 목록을 만든다"
    assert [dataclasses.asdict(s) for s in reloaded.PARAM_SPECS] == before_specs, (
        "재로드가 다른 데이터를 만든다 — 모듈 로드에 부작용이 있다"
    )
    assert reloaded.identity_keys() == before_identity
