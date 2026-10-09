"""cycle297 Red — G2: 범위 봉인(AST) — 4키 소유 7전략 · 매매 산식 무접촉 · leaf 순수성 · 라우트 등록 순서.

명세 = `_workspace/red/cycle297_llm_gate_all_strategies_spec.md` §5.1 G2.

**Red 단계 — 테스트만. `src/` 미변경.** Green = backend-dev.

## 이 파일이 지키는 것

cycle297 은 5전략의 `DEFAULT_PARAMS` 에 LLM 4키를 더하는 것 **외에** 전략 파일을 건드리지
않는다. "매매 행위 변경 0" 은 말로 하는 약속이 아니라 **세그먼트 sha 로 기계 증명**되어야
한다 — cycle290 이 28핀으로 잰 `check_buy_signal`/`check_exit_signal`/`calc_buy_quantity`/
`prepare` 가 그 축이고, 이 파일은 그 dict 를 **import 해서 재사용**한다(리터럴 복제 금지 —
두 벌이 되면 한쪽만 갱신돼 봉인이 조용히 공허해진다).

## 상대 갈래(cycle296)와의 경계 — `src/auth/**` 는 여기서 핀하지 않는다

이 세션에는 갈래가 둘이다. cycle296 이 `src/auth/token.py` 와 `src/engine/quote_token_refresh.py`
를 고친다. 8영역 전체를 byte 핀으로 잠그면 **상대 갈래의 정당한 변경이 이 파일을 붉게 만든다** —
그건 봉인이 아니라 잡음이다. 그래서 `_BASE_SHA` 는 297 이 절대 건드리지 않으면서 296 도
건드리지 않는 파일만 담고, `src/auth/**` 는 **명시적으로 제외**한다(제외 사실 자체를 아래
`test_g2_9b` 가 문서화한다 — 조용한 구멍으로 남기지 않는다).

## 양성 대조군

- G2-1 : "정확히 7" — 5전략에 새는 것(과소)과 8번째 파일이 갖는 것(과다)을 양방향으로 잡는다.
- G2-2 : 4키 **값**까지 대조 + 기존 키 목록 **전수 핀**(추가만 허용, 삭제·개명은 붉다).
- G2-3 : cycle290 핀 재사용 — "무접촉" 의 기계 증거.
- G2-8 : leaf 가 순수함(import 0)뿐 아니라 **함수가 실제로 정의돼 있는지**도 잰다.
"""

from __future__ import annotations

import ast
import hashlib
import importlib
from pathlib import Path

import pytest

from tests import _strategy_census as census

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parents[3]
_STRATEGY_DIR = _ROOT / "src" / "engine" / "strategies"
_RECO = _ROOT / "src" / "engine" / "recommendation_engine.py"
_CATALOG = _ROOT / "src" / "engine" / "param_catalog.py"
_FEATURES = _ROOT / "src" / "engine" / "llm_features.py"
_GATE = _ROOT / "src" / "engine" / "llm_buy_gate.py"
_RETRO = _ROOT / "src" / "engine" / "llm_retrospective.py"
_ROUTE = _ROOT / "src" / "routes" / "llm_evaluations.py"

_KEYS = (
    "llm_gate_mode",
    "llm_gate_min_score",
    "llm_gate_daily_call_cap",
    "llm_gate_timeout_secs",
)

#: 4키의 **값**까지 7전략 전부 동일해야 한다(M14: kojiro cap=0).
_KEY_VALUES = {
    "llm_gate_mode": "shadow",
    "llm_gate_min_score": 70,
    "llm_gate_daily_call_cap": 20,
    "llm_gate_timeout_secs": 20,
}

_NEW_FIVE = ("momentum", "donchian_swing", "bull_flag_breakout", "vcp_breakout", "kojiro")

#: cycle382(2026-09-27) — 시장 유닛(단계형) 모드. 4키(llm_gate_*) **뒤**에 붙는
#: 또 다른 축(사용자 결정 09-27) — 터틀 4전략에만 붙는다("momentum" 은 제외).
_CYCLE382_KEY = ("market_unit_mode",)
_CYCLE382_AFFECTED_SIDS = frozenset({
    "donchian_swing", "bull_flag_breakout", "vcp_breakout", "kojiro",
})


#: 🔁 cycle384 재핀 — buy_paused 공통 파라미터(사용자 결정 09-27 「돈키언 신규매수 중지」).
#: 7전략 공통 1키 — 말미가 아니라 `max_lot_ratio_mult` **바로 다음 줄**이 계약이다(명세 §8.1:
#: 「`"max_lot_ratio_mult": 2.5,` 다음 줄에 `"buy_paused": False,`」). 기본 false = 행위 변경 0.
_CYCLE384_KEY = "buy_paused"
_CYCLE384_AFTER = "max_lot_ratio_mult"
#: 🔁 cycle399 재핀 — 공통 섀도 모드 shadow_mode(사용자 승인 10-02 R1). 7전략 공통 1키 — `buy_paused` **바로 다음 줄**.
_CYCLE399_KEY = "shadow_mode"
#: 🔁 cycle405 재핀 — donchian 깡토식 청산·사이징 신규 7키. donchian 단독 — **말미**
#: (`market_unit_mode` 다음)가 계약이다(명세 §7.1 — 한 사이클 diff 를 한 덩어리로 묶는다).
_CYCLE405_KEYS = (
    "kk_r_floor_pct", "kk_r_atr_mult", "kk_breakeven_r", "kk_time_exit_bars",
    "kk_time_exit_min_r", "kk_max_hold_bars", "max_daily_entries",
)
_CYCLE405_AFFECTED_SIDS = frozenset({"donchian_swing"})


def _expected_keys_g2(sid: str) -> tuple[str, ...]:
    expected = _BASELINE_KEYS[sid] + _KEYS
    if sid in _CYCLE382_AFFECTED_SIDS:
        expected += _CYCLE382_KEY
    if sid in _CYCLE405_AFFECTED_SIDS:
        expected += _CYCLE405_KEYS
    i = expected.index(_CYCLE384_AFTER) + 1
    return expected[:i] + (_CYCLE384_KEY, _CYCLE399_KEY) + expected[i:]


#: 리팩토링 카드 #1 — 소유 기대값 = **전략 명부 전부**(`tests/_strategy_census.py`).
#: 7개 고정 목록이면 규약을 지켜 4키를 가진 여덟째 전략이 거짓으로 붉는다.
_ALL_STRATEGY_RELS = tuple(sorted(census.STRATEGY_RELS))


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _tree(path: Path) -> tuple[ast.Module, str]:
    src = _read(path)
    return ast.parse(src), src


def _default_params_dict_node(path: Path) -> ast.Dict | None:
    tree, _src = _tree(path)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(t, ast.Name) and t.id == "DEFAULT_PARAMS" for t in node.targets):
            continue
        if isinstance(node.value, ast.Dict):
            return node.value
    return None


def _default_params_keys(path: Path) -> tuple[str, ...]:
    node = _default_params_dict_node(path)
    if node is None:
        return ()
    return tuple(k.value for k in node.keys if isinstance(k, ast.Constant))


def _default_params_items(path: Path) -> dict:
    node = _default_params_dict_node(path)
    if node is None:
        return {}
    out = {}
    for k, v in zip(node.keys, node.values):
        if isinstance(k, ast.Constant):
            out[k.value] = v.value if isinstance(v, ast.Constant) else ast.unparse(v)
    return out


# ===========================================================================
# G2-1 — 4키 소유 전략 파일 = **정확히 명부 전부** (cycle274 C10-3 · cycle276 C6-3a 의 반전)
# ===========================================================================
@pytest.mark.parametrize("key", _KEYS)
def test_g2_1_four_keys_live_in_exactly_seven_strategy_files(key: str) -> None:
    """G2-1 — glob 전수에서 그 키를 `DEFAULT_PARAMS` 에 가진 파일 = 전략 명부 전부.

    cycle274/276 은 같은 축을 `{VB, LTV}` 로 잠갔다 — 이 사이클이 그 두 단언을 **반전**한다
    (삭제·skip 금지, 명세 §5.2). 여기서 '정확히' 인 이유 =
    - 과소(M12: momentum 만 누락) → 그 전략만 조용히 `mode=off` 로 남아 표본이 영영 안 쌓인다.
    - 과다(전략 아닌 파일이 같은 키를 가짐) → 4키의 소유 축이 흐려진다.
    """
    owners: list[str] = []
    for path in sorted(_STRATEGY_DIR.rglob("*.py")):
        for k in _default_params_keys(path):
            if k == key:
                owners.append(path.relative_to(_ROOT).as_posix())
    assert sorted(set(owners)) == sorted(_ALL_STRATEGY_RELS), (
        f"`{key}` 보유 전략 {sorted(set(owners))} (기대 = 명부 전부, "
        f"빠짐 {sorted(set(_ALL_STRATEGY_RELS) - set(owners))}). "
        "새 전략이면 그 파일의 `DEFAULT_PARAMS` 에 4키(`llm_gate_mode`·`llm_gate_min_score`·"
        "`llm_gate_daily_call_cap`·`llm_gate_timeout_secs`)를 다른 전략과 같은 값으로 넣어라. "
        "전략이 아닌 파일이 갖고 있으면 지워라"
    )


#: 반전 대상 = cycle274/276 이 같은 축을 `{VB, LTV}` 로 잠근 두 테스트(명세 §5.2).
_INVERSION_TARGETS: tuple[tuple[str, str], ...] = (
    ("tests/unit/ast/test_cycle274_ast_llm_gate.py",
     "test_c10_3_key_lives_in_exactly_vb_and_ltv_default_params"),
    ("tests/unit/ast/test_cycle276_ast_order_hook.py",
     "test_c6_3a_four_keys_live_in_exactly_vb_and_ltv"),
)


@pytest.mark.parametrize("rel,fn_name", _INVERSION_TARGETS)
def test_g2_1b_prior_ownership_guards_are_inverted_not_deleted(rel: str, fn_name: str) -> None:
    """G2-1b — cycle274/276 의 소유 축 가드를 **지우거나 skip 하지 않는다**(명세 §5.2).

    소유 집합이 넓어질 때 가장 싼 길은 불편한 단언을 지우는 것이다 — 그러면 다음 사이클이
    8번째 파일에 키를 새로 흘려도 아무도 모른다. 축은 남기고 **기대값만** 7전략으로 뒤집는다.

    여기서는 (a) 함수가 여전히 존재하고 (b) `skip`/`xfail` 마커가 붙지 않았음만 잰다.
    그 함수가 실제로 초록인지는 `tests/unit/ast/` 버킷 실행 자체가 증명한다.
    """
    path = _ROOT / rel
    assert path.exists(), f"{rel} 가 사라졌다 — 소유 축 가드는 유지한다"
    tree, _src = _tree(path)
    fns = [n for n in ast.walk(tree)
           if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == fn_name]
    assert fns, f"{rel}::{fn_name} 가 삭제됐다 — 기대값만 뒤집어야 한다"

    decs = [ast.unparse(d) for d in fns[0].decorator_list]
    banned = [d for d in decs if "skip" in d or "xfail" in d]
    assert not banned, f"{rel}::{fn_name} 에 회피 마커가 붙었다 — {banned}"


# ===========================================================================
# G2-2 — 5전략 `DEFAULT_PARAMS` = 기존 키 전수 + 4키(말미), 값은 VB 와 동일
# ===========================================================================
#: cycle297 착수 시점(HEAD `a4580b6`)의 `DEFAULT_PARAMS` 키 **전수**.
#: 🔴 이 목록에서 키가 사라지거나 이름이 바뀌면 붉다 — cycle278 `_DEFAULT_PARAMS_SHA` 는
#: Green 이 재핀하므로 "4키만 더했다" 를 증명하지 못한다. 그 증명은 이 목록이 한다.
_BASELINE_KEYS: dict[str, tuple[str, ...]] = {
    "momentum": (
        "tradable_boards", "exchange", "buy_threshold", "stop_loss_rate", "gap_up_threshold",
        "trailing_stop_rate", "position_ratio", "max_positions", "daily_loss_limit",
        "max_lot_ratio_mult", "order_exchange_clock_mode", "after_market_exit_division",
    ),
    "donchian_swing": (
        "tradable_boards", "exchange", "donchian_period", "long_ma_period", "volume_period",
        "volume_multiplier", "atr_period", "atr_trail_mult", "min_market_cap",
        "min_trade_amount", "max_scan_stocks", "exclude_tickers", "nxt_tradable",
        "gap_skip_threshold", "stop_loss_rate", "position_ratio", "max_positions",
        "daily_loss_limit", "breakout_fail_n_days", "max_breakout_extension_pct",
        "sizing_mode", "risk_pct", "stop_atr", "turtle_backstop_pct", "min_vol_floor_pct",
        "max_lot_units", "breakeven_promote_atr", "channel_exit_period", "max_lot_ratio_mult",
        "order_exchange_clock_mode", "after_market_exit_division",
    ),
    "bull_flag_breakout": (
        "tradable_boards", "exchange", "pole_lookback_min", "pole_lookback_max",
        "pole_min_return", "pole_max_red_ratio", "flag_lookback_min", "flag_lookback_max",
        "flag_retracement_max", "flag_volume_ratio", "breakout_volume_mult", "entry_start",
        "entry_end", "max_breakout_extension_pct", "position_ratio", "max_positions",
        "stop_loss_rate", "atr_period", "atr_trail_mult", "breakeven_promote_atr",
        "max_hold_days", "reentry_cooldown_days", "sizing_mode", "risk_pct", "stop_atr",
        "turtle_backstop_pct", "min_vol_floor_pct", "max_lot_units", "turtle_min_stop_pct",
        "min_market_cap", "min_trade_amount", "max_scan_stocks", "daily_loss_limit",
        "breakout_retention_minutes", "max_lot_ratio_mult", "order_exchange_clock_mode",
        "after_market_exit_division",
    ),
    # cycle300 — `daily_fetch_depth_mode` 1키 추가(일봉 읽기 깊이 스위치, 기본 `cap100`).
    # 말미가 아니라 `long_ema_uptrend_days` **바로 뒤**에 둔 것은 의도다 — 이 키는 추세
    # 필터 3선이 몇 봉으로 계산되는지를 정하므로 EMA 키들과 한 덩어리로 읽혀야 한다.
    "vcp_breakout": (
        "tradable_boards", "exchange", "ema_short", "ema_mid", "ema_long",
        "long_ema_uptrend_days", "daily_fetch_depth_mode",
        "base_min_days", "base_max_days", "base_depth_pct",
        "pullback_count_min", "pullback_count_max", "last_pullback_max", "min_swing_atr_mult",
        "volume_contraction_ratio", "breakout_volume_mult", "entry_start", "entry_end",
        "max_breakout_extension_pct", "position_ratio", "max_positions", "stop_loss_rate",
        "atr_period", "atr_trail_mult", "breakeven_promote_atr", "reentry_cooldown_days",
        "sizing_mode", "risk_pct", "stop_atr", "turtle_backstop_pct", "min_vol_floor_pct",
        "turtle_min_stop_pct", "max_lot_units", "min_market_cap", "min_trade_amount",
        "max_scan_stocks", "daily_loss_limit", "max_lot_ratio_mult",
        "order_exchange_clock_mode", "after_market_exit_division",
    ),
    "kojiro": (
        "tradable_boards", "exchange", "ema_short", "ema_mid", "ema_long", "macd_signal",
        "atr_period", "slope_lookback", "stage1_freshness", "atr_ratio_min", "atr_ratio_max",
        "stop_atr", "trail_atr", "hard_stop_pct", "breakeven_promote_atr", "gap_up_skip_pct",
        "gap_down_skip_pct", "min_market_cap", "min_trade_amount", "max_scan_stocks",
        "exclude_tickers", "nxt_tradable", "position_ratio", "max_positions",
        "daily_loss_limit", "max_positions_per_sector", "max_open_risk_pct", "rank_w_macd3",
        "rank_w_band", "rank_w_fresh", "sizing_mode", "risk_pct", "min_vol_floor_pct",
        "max_units_per_stock", "max_units_total", "max_lot_units", "max_lot_ratio_mult",
        "order_exchange_clock_mode", "after_market_exit_division",
    ),
}


@pytest.mark.parametrize("sid", _NEW_FIVE)
def test_g2_2a_five_strategies_keep_every_baseline_key_and_add_exactly_four(sid: str) -> None:
    """G2-2 — 키 목록 == 착수 시점 전수 + 4키. **순서까지** 잰다(4키는 말미).

    '기존 키 하나 삭제 + 4키 추가' 를 개수만으로는 못 잡는다 — 전수 비교가 유일한 방법이다.
    4키를 말미(`after_market_exit_division` 다음)에 두는 것은 diff 를 한 덩어리로 묶어
    리뷰에서 "그 외 무접촉" 을 눈으로 확인할 수 있게 하는 계약이다.
    """
    path = _STRATEGY_DIR / f"{sid}.py"
    got = _default_params_keys(path)
    expected = _expected_keys_g2(sid)
    assert got == expected, (
        f"{sid}: DEFAULT_PARAMS 키 순서/구성이 다르다\n"
        f"  추가됨: {sorted(set(got) - set(expected))}\n"
        f"  사라짐: {sorted(set(expected) - set(got))}\n"
        f"  실측  : {got}"
    )


@pytest.mark.parametrize("sid", _NEW_FIVE)
def test_g2_2b_four_key_values_match_vb_exactly(sid: str) -> None:
    """G2-2 — 4키의 **값**이 VB 와 같다(M14: `daily_call_cap=0` 이면 그 전략만 조용히 무호출).

    기대값을 리터럴로 쓰는 대신 VB 파일에서 읽어 대조한다 — 두 벌 관리를 피하고,
    VB 가 바뀌면 5전략도 같이 바뀌어야 한다는 계약을 구조로 강제한다.
    """
    vb = _default_params_items(_STRATEGY_DIR / "volatility_breakout.py")
    got = _default_params_items(_STRATEGY_DIR / f"{sid}.py")
    for key in _KEYS:
        assert key in got, f"{sid}: `{key}` 부재"
        assert got[key] == vb[key] == _KEY_VALUES[key], (
            f"{sid}.{key} = {got[key]!r} (VB={vb[key]!r}, 기대={_KEY_VALUES[key]!r})"
        )


# ===========================================================================
# G2-3 — 매매 산식 4메서드 **무접촉** (cycle290 핀 재사용)
# ===========================================================================
def _cycle290():
    return importlib.import_module("tests.unit.ast.test_cycle290_ast_scope")


def test_g2_3a_cycle290_segment_pins_are_reused_not_copied() -> None:
    """G2-3 **양성 대조군** — cycle290 핀 dict 가 실제로 import 되고 28개다.

    리터럴 복제를 막는 장치다 — 복제하면 한쪽만 갱신돼 봉인이 조용히 공허해진다.
    """
    pins = _cycle290()._SEGMENT_SHA
    assert len(pins) == 28, f"cycle290 `_SEGMENT_SHA` 가 28개가 아니다 — {len(pins)}"
    assert {m for _sid, m in pins} == {
        "check_buy_signal", "check_exit_signal", "calc_buy_quantity", "prepare",
    }


@pytest.mark.parametrize("sid", _NEW_FIVE)
@pytest.mark.parametrize(
    "method", ["check_buy_signal", "check_exit_signal", "calc_buy_quantity", "prepare"]
)
def test_g2_3b_trading_methods_are_byte_identical(sid: str, method: str) -> None:
    """G2-3 — 5전략의 매매 산식 4메서드가 cycle290 핀과 **같다**(M16: 한 줄 추가).

    "매매 행위 변경 0" 의 기계 증거. `ast.get_source_segment` 의 sha 로 재는 이유 =
    `ast.dump` 는 파이썬 3.12(CI)와 3.13(로컬)의 출력이 달라 로컬 초록·CI 실패를 만든다
    (cycle256 G-250-5 실측).
    """
    pins = _cycle290()._SEGMENT_SHA
    key = (sid, method)
    assert key in pins, f"cycle290 핀에 {key} 가 없다"

    path = _STRATEGY_DIR / f"{sid}.py"
    tree, src = _tree(path)
    fns = [
        n for n in ast.walk(tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == method
    ]
    assert fns, f"{sid}.{method} 부재"
    got = _sha(ast.get_source_segment(src, fns[0]) or "")
    assert got == pins[key], (
        f"{sid}.{method} 세그먼트가 바뀌었다 — cycle297 은 `DEFAULT_PARAMS` 4키만 더한다. "
        f"🔴 핀을 갱신하지 말고 코드를 되돌려라. 현재 sha={got}"
    )


# ===========================================================================
# G2-4 — 4키는 `PARAM_RANGES`/`INT_PARAMS` 밖 (런타임 + 소스 이중, 7전략 문맥)
# ===========================================================================
@pytest.mark.parametrize("key", _KEYS)
def test_g2_4a_keys_stay_out_of_param_ranges_runtime(key: str) -> None:
    """G2-4 — AI 자문이 게이트 임계·비용 cap 을 자동 튜닝하면 안 된다(M15).

    7전략으로 넓어지면 `_validate_recommendations` 가 훑는 전략 수도 7배가 된다 —
    편입 사고의 폭발 반경이 그만큼 커졌다.
    """
    from src.engine.recommendation_engine import INT_PARAMS, PARAM_RANGES

    assert key not in PARAM_RANGES
    assert key not in INT_PARAMS


@pytest.mark.parametrize("key", _KEYS)
def test_g2_4b_keys_have_no_literal_in_recommendation_engine(key: str) -> None:
    """G2-4 — 런타임 dict 만 보면 조건부 편입(`if ...: PARAM_RANGES[K] = ...`)을 놓친다."""
    hits = [i for i, line in enumerate(_read(_RECO).splitlines(), 1) if key in line]
    assert not hits, f"`recommendation_engine.py` 에 `{key}` 리터럴(lines {hits})"


# ===========================================================================
# G2-5 — `param_catalog` 4키 `applies_to` == 7전략
# ===========================================================================
@pytest.mark.parametrize("key", _KEYS)
def test_g2_5_catalog_applies_to_is_all_seven(key: str) -> None:
    """G2-5 — 카탈로그 어휘가 `DEFAULT_PARAMS` 소유 집합과 일치한다(M13: `_VBLTV` 잔존).

    cycle278 의 `test_applies_to_when_compared_then_matches_default_params_exactly` 와
    같은 축이지만, 이 파일은 **기대값을 직접 못박아** 그 테스트가 사라지거나 느슨해져도
    남는다. 어긋나면 5전략 화면에서 4키가 안 보이고 `PUT .../params` 가 `unknown_key` 422 다
    (cycle287 이 장중 킬스위치를 못 쓰게 됐던 그 결함 계열).
    """
    from src.engine.param_catalog import PARAM_SPECS, STRATEGY_IDS

    specs = [s for s in PARAM_SPECS if s.key == key]
    assert len(specs) == 1, f"`{key}` 스펙 {len(specs)}건"
    assert tuple(specs[0].applies_to) == tuple(STRATEGY_IDS), (
        f"`{key}`.applies_to = {specs[0].applies_to} (기대 = STRATEGY_IDS 7전략)"
    )


# ===========================================================================
# G2-6 — 프롬프트 3요소 **불변** (VB·LTV payload byte 동일의 소스 축)
# ===========================================================================
#: cycle297 착수 시점(HEAD `a4580b6`) `ast.get_source_segment` sha256.
#: 🔴 `SYSTEM_PROMPT` 재작문·`_SNAPSHOT_KEYS` 확장(M25)은 이 사이클 범위 밖이다.
_PROMPT_SEGMENT_SHA: dict[str, str] = {
    "SYSTEM_PROMPT":
        "028d08e51905fad680d4a16c1219aaa13a2719f9dbe8e4e58274f93cad1eeb71",
    "_USER_PREAMBLE":
        "1aa37f98cd96031ea90b2d66283944f0f999a3a880df4a582175cbd6c955e589",
    "_SNAPSHOT_KEYS":
        "ee4cf91ab50d99662c456c058b40c50894a00759c3c10a2bc729d2cf46aeee82",
}


@pytest.mark.parametrize("name", sorted(_PROMPT_SEGMENT_SHA))
def test_g2_6_prompt_building_blocks_are_frozen(name: str) -> None:
    """G2-6 — 세 모듈 상수의 소스 세그먼트가 바뀌지 않았다.

    **양성 대조군** = 세그먼트가 실제로 존재하고 비어 있지 않아야 한다(상수를 통째로 지우면
    `ast.get_source_segment` 가 못 찾아 `assert node` 에서 먼저 붉다).
    """
    tree, src = _tree(_FEATURES)
    nodes = [
        n for n in tree.body
        if isinstance(n, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == name for t in n.targets)
    ]
    assert len(nodes) == 1, f"`{name}` 모듈 레벨 대입이 {len(nodes)}건"
    seg = ast.get_source_segment(src, nodes[0]) or ""
    assert seg.strip(), f"`{name}` 세그먼트가 비었다"
    got = _sha(seg)
    assert got == _PROMPT_SEGMENT_SHA[name], (
        f"`{name}` 이 바뀌었다 — cycle297 은 프롬프트 본문/스냅샷 키를 건드리지 않는다. "
        f"🔴 핀을 갱신하지 말고 코드를 되돌려라. 현재 sha={got}"
    )


# ===========================================================================
# G2-7 — `_prompt_version(strategy_id)` 배선 (AST)
# ===========================================================================
def test_g2_7a_prompt_version_takes_one_positional_argument() -> None:
    """G2-7 — 시그니처에 인자 1개(M10: `strategy_id` 무시).

    런타임 단언(G1-10)과 짝이다 — 인자를 받되 쓰지 않는 구현은 G1-10 이, 인자 자체가 없는
    구현은 여기가 잡는다.
    """
    tree, _src = _tree(_GATE)
    fns = [n for n in ast.walk(tree)
           if isinstance(n, ast.FunctionDef) and n.name == "_prompt_version"]
    assert len(fns) == 1, f"`_prompt_version` 정의 {len(fns)}건"
    args = fns[0].args
    names = [a.arg for a in args.posonlyargs + args.args]
    assert len(names) == 1, f"`_prompt_version{tuple(names)}` — 인자 1개여야 한다"


def test_g2_7b_persist_evaluation_passes_strategy_id_to_prompt_version() -> None:
    """G2-7 — `_persist_evaluation` 안의 `_prompt_version(...)` 호출이 **인자를 준다**.

    함수만 고치고 호출부를 안 고치면 `TypeError` 가 나거나(다행) 기본값으로 조용히
    전역 버전이 박힌다(불행). 호출부를 AST 로 직접 잰다.
    """
    tree, _src = _tree(_GATE)
    calls = [
        n for n in ast.walk(tree)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
        and n.func.id == "_prompt_version"
    ]
    assert calls, "`_prompt_version` 호출이 없다"
    bare = [c.lineno for c in calls if not c.args and not c.keywords]
    assert not bare, f"`_prompt_version()` 무인자 호출이 남아 있다 (lines {bare})"


# ===========================================================================
# G2-8 — 신규 leaf `llm_retrospective.py` 순수성
# ===========================================================================
def test_g2_8a_retrospective_leaf_exists_with_two_public_functions() -> None:
    """G2-8 **양성 대조군** — leaf 가 있고 두 함수가 실제로 정의돼 있다.

    "import 가 없다" 만 재면 **빈 파일도 통과**한다(cycle292 교훈).
    """
    assert _RETRO.exists(), f"신규 leaf 부재: {_RETRO}"
    tree, _src = _tree(_RETRO)
    names = {n.name for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    assert {"join_pairs_with_evaluations", "aggregate"} <= names, (
        f"leaf 공개 함수 부족 — 실측 {sorted(names)}"
    )


def test_g2_8b_retrospective_leaf_imports_nothing_from_src() -> None:
    """G2-8 — `src.*` import 0(M24: `src.db.pg` import).

    순수 함수라야 실 PG 없이 표만 넣어 골든 테스트를 쓸 수 있고, 라우트가 바뀌어도
    조인·집계 정의가 흔들리지 않는다.
    """
    tree, _src = _tree(_RETRO)
    bad: list[str] = []
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            bad += [f"{n.lineno}:{a.name}" for a in n.names if a.name.startswith("src")]
        elif isinstance(n, ast.ImportFrom):
            mod = n.module or ""
            if mod.startswith("src") or n.level:
                bad.append(f"{n.lineno}:{mod or '.'*n.level}")
    assert not bad, f"leaf 가 프로젝트 모듈을 import 한다 — {bad}"


def test_g2_8c_retrospective_leaf_has_no_io_and_no_await() -> None:
    """G2-8 — `await`·`async def`·`pg`·`httpx`·`requests` 0건 + 모듈 최상단 부작용 0.

    최상단에 남길 수 있는 것 = import·상수 대입·함수/클래스 정의뿐이다.
    """
    tree, src = _tree(_RETRO)
    assert not [n.lineno for n in ast.walk(tree) if isinstance(n, ast.Await)], "await 가 있다"
    assert not [n.lineno for n in ast.walk(tree)
                if isinstance(n, ast.AsyncFunctionDef)], "async def 가 있다"
    for token in ("pg.", "httpx", "requests", "asyncpg", "open("):
        assert token not in src, f"leaf 에 I/O 토큰 `{token}` 이 있다"

    allowed = (ast.Import, ast.ImportFrom, ast.Assign, ast.AnnAssign,
               ast.FunctionDef, ast.ClassDef, ast.Expr, ast.If)
    bad = [type(n).__name__ for n in tree.body if not isinstance(n, allowed)]
    assert not bad, f"모듈 최상단 부작용 — {bad}"


# ===========================================================================
# G2-9 — `scheduler.py` 라인 상한 (cycle257 영구 상한 복창)
# ===========================================================================
#: 8영역 + `scheduler.py` 파일 내용 sha 는 정본 `test_cycle222a3_ast_followup_fixes.py::
#: _APPROVED_CONTENT_SHA` 한 곳에만 둔다(cycle419 — 이 파일의 G2-9 파일 핀·정확 줄 수 핀은 걷었다).


def test_g2_9b_scheduler_line_budget() -> None:
    """G2-9 — `scheduler.py` 라인 상한 3,900 미만(cycle257 영구 상한, 루트 CLAUDE.md 8영역 절)."""
    sched = _ROOT / "src/engine/scheduler.py"
    n = len(_read(sched).splitlines())
    assert n < 3900, f"`scheduler.py` 라인 상한 3,900 초과 — {n}L"


# ===========================================================================
# G2-10 — 라우트 등록 순서: `/retrospective` 가 `/{order_no}` **앞**
# ===========================================================================
def _route_decorator_linenos() -> dict[str, int]:
    tree, _src = _tree(_ROUTE)
    out: dict[str, int] = {}
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for dec in node.decorator_list:
            if not isinstance(dec, ast.Call):
                continue
            func = dec.func
            if not (isinstance(func, ast.Attribute) and func.attr == "get"):
                continue
            if not (isinstance(func.value, ast.Name) and func.value.id == "router"):
                continue
            if dec.args and isinstance(dec.args[0], ast.Constant):
                out[str(dec.args[0].value)] = dec.lineno
    return out


def test_g2_10_retrospective_route_is_registered_before_order_no() -> None:
    """G2-10 — `"/retrospective"` 데코레이터 lineno < `"/{order_no}"` 데코레이터 lineno.

    FastAPI 는 **등록 순서대로** 매칭하므로 뒤에 두면 `retrospective` 가 주문번호로 잡혀
    404 가 된다(M22). **양성 대조군** = 두 경로가 둘 다 실제로 존재해야 한다 — 하나가
    사라지면 `KeyError` 로 먼저 붉다.
    """
    decs = _route_decorator_linenos()
    assert "/retrospective" in decs, f"`/retrospective` 라우트 부재 — 실측 {sorted(decs)}"
    assert "/{order_no}" in decs, f"`/{{order_no}}` 라우트 부재 — 실측 {sorted(decs)}"
    assert decs["/retrospective"] < decs["/{order_no}"], (
        f"등록 순서가 뒤집혔다 — /retrospective@{decs['/retrospective']} "
        f"vs /{{order_no}}@{decs['/{order_no}']}"
    )
