"""cycle228-A (RED) — AST 영구 가드 (명세 A8).

| # | 가드 | 지키는 것 |
|---|---|---|
| G-1 | BFB·VCP 전 파일에서 `ticker_prices` 참조 **0건** | 게이트/래치가 유령 키 dict 로 되돌아가지 않는다 + donchian `ext_pct` 커플링 유입 차단 |
| G-2 | 게이트가 `tick_volume.get_observed_acml_vol` 경유 | 소스 전환의 실체 |
| G-3 | `check_buy_signal` 에 `_vol_latch` 재평가 경로 존재 | 래치 배선이 조용히 빠지지 않는다 |
| G-4 | `max_breakout_extension_pct` 가 PARAM_RANGES·INT_PARAMS **미편입** | 정체성 상수가 AI 야간 튜닝에 노출되지 않는다 |
| G-5 | 추격 판정식에 `daily_high`/`stck_hgpr`/`high_price` 토큰 0건 | donchian 구현 이식 시 딸려오는 커플링 차단 |
| G-6 | `_vol_gate_observe` 마커·훅 전 소스 0건 | cycle227 관측 훅 은퇴(의미 반전) |
| G-7 | `prepare` 가 `_check_extension_cap_invariant` 를 호출 | 헬퍼가 배선 없이 죽지 않는다 |
| G-8 | A5 한글 리터럴 byte 보존 | 운영자 grep 이력 연속성 |

## G-1 이 왜 "게이트 블록 한정" 이 아니라 파일 전체인가

착수 시점 실측: `ticker_prices` 는 BFB·VCP 각 파일에서 **거래량 컷 블록 2줄에만**
등장한다(`bull_flag_breakout.py:923-924` / `vcp_breakout.py:1036-1037`).
A1 전환이 그 4줄을 제거하므로 전환 후 정답은 **파일 전체 0건**이고, 그게 블록 범위를
말로 정의하는 것보다 훨씬 견고하다(블록 경계가 이동해도 가드가 공허해지지 않는다 —
cycle224 자기 가드 공허성 교훈).

## cycle227 AST-2 는 이 사이클이 **의미 전환**한다

`test_cycle227_ast_acml_vol_guards.py::test_AST2_existing_volume_gate_block_is_byte_identical`
은 게이트 블록을 byte pin 했다. Stage 0 봉인이 목적이었고, 이제 그 봉인을 푸는 것이
이 사이클이다. 그 가드의 갱신은 **Green 단계에서** 수행한다(Red 는 기존 테스트 무수정).
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from tests.unit.ast._ast_helpers import read_module_source as _read

pytestmark = pytest.mark.unit

_REPO_ROOT = Path(__file__).resolve().parents[3]

_STRATEGY_FILES = {
    "bfb": "src/engine/strategies/bull_flag_breakout.py",
    "vcp": "src/engine/strategies/vcp_breakout.py",
}
_ALL_SRC = sorted(
    p for p in (_REPO_ROOT / "src").rglob("*.py") if "__pycache__" not in p.parts
)


def _tree(rel: str) -> tuple[ast.Module, str]:
    src = _read(_REPO_ROOT / rel)
    return ast.parse(src), src


def _func(tree: ast.Module, name: str):
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    return None


# ===========================================================================
# G-1 — `ticker_prices` 참조 0건
# ===========================================================================

@pytest.mark.parametrize("rel", list(_STRATEGY_FILES.values()), ids=list(_STRATEGY_FILES))
def test_g1_no_ticker_prices_reference(rel):
    """G-1 — 전환 후 두 전략 파일은 `ticker_prices` 를 **전혀** 참조하지 않는다."""
    tree, src = _tree(rel)
    hits = [
        node.lineno for node in ast.walk(tree)
        if (isinstance(node, ast.Name) and node.id == "ticker_prices")
        or (isinstance(node, ast.Attribute) and node.attr == "ticker_prices")
        or (isinstance(node, ast.alias) and node.name == "ticker_prices")
    ]
    assert hits == [], (
        f"{rel} 에 `ticker_prices` 참조 잔존 (lines {hits}). 게이트 소스는 "
        "`tick_volume` 이고, 추격 판정은 `current_price` 다 — 그 dict 를 다시 읽으면 "
        "donchian `ext_pct` 커플링과 유령 키 결함이 함께 돌아온다"
    )


# ===========================================================================
# G-2 / G-3 — 게이트 소스 · 래치 배선
# ===========================================================================

@pytest.mark.parametrize("rel", list(_STRATEGY_FILES.values()), ids=list(_STRATEGY_FILES))
def test_g2_gate_reads_tick_volume(rel):
    _, src = _tree(rel)
    assert "get_observed_acml_vol" in src, (
        f"{rel} 이 관측 모듈을 읽지 않는다 — 게이트 소스 전환(A1) 미수행"
    )


@pytest.mark.parametrize("rel", list(_STRATEGY_FILES.values()), ids=list(_STRATEGY_FILES))
def test_g3_check_buy_signal_has_latch_path(rel):
    """G-3 — 래치 재평가는 `check_buy_signal` 안에 있어야 한다.

    edge-crossing 이 소진된 뒤에도 도달해야 하므로 다른 진입점에 두면 무의미하다.
    """
    tree, _ = _tree(rel)
    fn = _func(tree, "check_buy_signal")
    assert fn is not None, f"{rel} 에 `check_buy_signal` 미발견"
    assert "_vol_latch" in ast.unparse(fn), (
        f"{rel}::check_buy_signal 에 `_vol_latch` 경로가 없다 — 래치 미배선"
    )


# ===========================================================================
# G-4 — 정체성 상수는 AI 튜닝 대상이 아니다
# ===========================================================================

def test_g4_extension_cap_not_ai_tunable():
    """G-4 — `max_breakout_extension_pct` 는 PARAM_RANGES·INT_PARAMS 미편입.

    `stop_loss_rate` 는 PARAM_RANGES 멤버(−15.0~0.0)라 매일 밤 AI 가 흔들 수 있다.
    캡까지 튜닝 대상이 되면 추격 상한이 조용히 몇 배가 된다
    (사이클 208/209/212 선례 — 진입 정체성 상수 제외).
    """
    from src.engine.recommendation_engine import INT_PARAMS, PARAM_RANGES

    assert "max_breakout_extension_pct" not in PARAM_RANGES
    assert "max_breakout_extension_pct" not in INT_PARAMS


@pytest.mark.parametrize(
    "rel,expected",
    [(_STRATEGY_FILES["bfb"], 5.0), (_STRATEGY_FILES["vcp"], 7.5)],
    ids=["bfb", "vcp"],
)
def test_g4_extension_cap_literal_in_default_params(rel, expected):
    """G-4 — 값은 **리터럴**로 못박는다(런타임 `stop_loss_rate` 도출 금지)."""
    tree, _ = _tree(rel)
    found: list[float] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            for k, v in zip(node.keys, node.values):
                if (
                    isinstance(k, ast.Constant)
                    and k.value == "max_breakout_extension_pct"
                    and isinstance(v, ast.Constant)
                ):
                    found.append(v.value)
    assert found == [expected], (
        f"{rel} 의 `max_breakout_extension_pct` 리터럴이 {found} 다 ({expected} 기대). "
        "런타임 도출이면 AI 가 stop_loss_rate 를 넓히는 순간 캡이 함께 넓어진다"
    )


# ===========================================================================
# G-5 — 추격 판정은 current_price 단독
# ===========================================================================

@pytest.mark.parametrize("rel", list(_STRATEGY_FILES.values()), ids=list(_STRATEGY_FILES))
def test_g5_extension_check_has_no_daily_high_tokens(rel):
    """G-5 — `daily_high` / `stck_hgpr` / `high_price` 토큰 0건.

    donchian 은 `daily_high = max(stck_hgpr, high_price, current_price, open_price)` 로
    판정하는데, 그 기준은 *한 번 치솟았다 돌파선으로 되돌아온* 종목을 영구 차단한다 —
    그게 바로 retest-and-go, 가장 좋은 진입이다. 잘못된 방향으로 엄격하다.
    """
    tree, _ = _tree(rel)
    fn = _func(tree, "check_buy_signal")
    assert fn is not None
    body = ast.unparse(fn)
    for token in ("daily_high", "stck_hgpr", "high_price"):
        assert token not in body, (
            f"{rel}::check_buy_signal 에 `{token}` 유입 — 추격 판정은 current_price 단독"
        )


# ===========================================================================
# G-6 — cycle227 관측 훅 은퇴
# ===========================================================================

def test_g6_observe_marker_retired_from_all_sources():
    """G-6 — `_vol_gate_observe` 는 전 소스에서 사라진다.

    같은 마커에서 `would_pass=True` 의 매매 귀결이 **미매수 → 매수**로 반전되므로,
    마커를 남기면 경계일을 모르는 사람이 과거 로그에서 없던 체결을 읽는다.
    """
    violations: list[str] = []
    for path in _ALL_SRC:
        src = _read(path)
        if "_vol_gate_observe" in src:
            violations.append(str(path.relative_to(_REPO_ROOT)))
    assert violations == [], f"관측 마커/훅 잔존: {violations}"


# ===========================================================================
# G-7 — 불변식 헬퍼 배선
# ===========================================================================

@pytest.mark.parametrize("rel", list(_STRATEGY_FILES.values()), ids=list(_STRATEGY_FILES))
def test_g7_prepare_calls_extension_cap_invariant(rel):
    """G-7 — 헬퍼는 `prepare()` 에서 호출돼야 부팅 관찰이 실제로 일어난다.

    단위 테스트가 `prepare()` 본체를 돌릴 수 없어(DB/KIS + 0건 시 `asyncio.sleep(30)`)
    행위는 헬퍼 직접 호출로 검증하고, **배선은 여기서** 검증한다
    (cycle224 가 쓴 hoist + AST 가드 조합).
    """
    tree, _ = _tree(rel)
    fn = _func(tree, "prepare")
    assert fn is not None, f"{rel} 에 `prepare` 미발견"
    calls = [
        n for n in ast.walk(fn)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Attribute)
        and n.func.attr == "_check_extension_cap_invariant"
    ]
    assert calls, (
        f"{rel}::prepare 가 `_check_extension_cap_invariant` 를 호출하지 않는다 — "
        "헬퍼만 있고 배선이 없으면 부팅 관찰이 영원히 안 일어난다"
    )


# ===========================================================================
# G-8 — A5 한글 리터럴 byte 보존
# ===========================================================================

_KOREAN_LITERALS = (
    "BFB 돌파 1차 감지(retention 대기 시작): %s flag_high(%d) retention=%d분",
    "BFB 돌파 후퇴(retention 대기 종료): %s",
)


@pytest.mark.parametrize("literal", _KOREAN_LITERALS, ids=["seen", "retreat"])
def test_g8_korean_transition_literals_preserved(literal):
    """G-8 — cap 만 씌우고 **문구는 안 건드린다**.

    H-1 F4 선례(`_HIGH_RECOVER_LABEL`) — 접두사가 바뀌어 운영자 한글 grep 이력이
    끊긴 적이 있다. 8/26 의 473행이 이 문구로 집계돼 있고, cap 효과 검증(473→~20)이
    같은 grep 으로 이뤄져야 한다.
    """
    _, src = _tree(_STRATEGY_FILES["bfb"])
    assert literal in src, f"한글 리터럴 변형 감지: {literal!r}"


# ===========================================================================
# G-9 — 구 게이트 4줄 소멸 (전환의 실체)
# ===========================================================================

@pytest.mark.parametrize("rel", list(_STRATEGY_FILES.values()), ids=list(_STRATEGY_FILES))
def test_g9_legacy_gate_expression_removed(rel):
    """G-9 — `info_price.get("acml_vol", ...)` 구 판정식이 사라진다."""
    _, src = _tree(rel)
    assert 'info_price.get("acml_vol"' not in src, (
        f"{rel} 에 구 게이트 판정식 잔존 — A1 소스 전환 미완"
    )
