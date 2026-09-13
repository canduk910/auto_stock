"""cycle290 Red — 범위 가드: **전략 7파일 `DEFAULT_PARAMS` + `param_catalog` 외 diff 0**.

정본 = cycle290 도메인 자문 §S1·§S3·§S4 (2026-09-13) + 브리프 제약.

## 이 사이클의 제1 계약

**프로덕션 코드는 `src/engine/strategies/*.py` 7파일의 `DEFAULT_PARAMS` 와
`src/engine/param_catalog.py` 만 바뀐다.**

`order_engine.py` 는 이미 두 키를 읽는 코드를 갖고 있으므로 **손댈 이유가 없다** —
그래서 cycle287 과 달리 이 파일이 핀 목록에 **들어 있다**(S1).

⚠️ 반대로 **`src/models/order.py` 는 일부러 핀하지 않는다** — cycle287
`test_s4b_models_order_is_not_pinned_anywhere` 가 "어느 sha 핀 dict 에도 그 경로가
키로 등장하지 않는다" 를 계약으로 잠갔다(`OrderDivision` enum 확장의 가드 비용을 0 으로
유지하려는 의도). 초안에서 그 파일을 `_BASE_SHA` 에 넣었다가 그 가드가 즉시 잡아냈다. 주석 정직화조차 8영역
승인 사유이므로 이번 사이클에서는 `src/engine/CLAUDE.md` 가 대신 기록한다(자문 §S3-2).

`param_validation.py` 도 무접촉이다 — **등재만으로 판정이 통해야** 한다. 검증 로직을
고쳐 통과시키는 것은 이 사이클이 고치려는 것과 반대 방향이다(S1).

## 왜 세그먼트 sha 를 따로 잠그는가 (S2)

`DEFAULT_PARAMS` 는 클래스 **속성**이라 메서드 세그먼트에 포함되지 않는다. 따라서
7 전략의 `check_buy_signal`·`check_exit_signal`·`calc_buy_quantity`·`prepare` 28
세그먼트는 이 사이클에서 **하나도 깨지지 않아야** 한다. 하나라도 붉어지면 핀을 옮기지
말고 **코드를 되돌려라** — `DEFAULT_PARAMS` 밖을 건드렸다는 신호다.

## 왜 `ast.dump` 의 sha 를 핀하지 않는가

3.12(CI)/3.13(로컬)의 `ast.dump` 출력이 달라 로컬 초록·CI 실패가 난다
(cycle256 G-250-5 · cycle259 S4a). 무변경 핀은 **파일 내용 sha256** 또는
`ast.get_source_segment` 의 sha256 으로만 잰다.

## 왜 `git grep`/`git ls-files`/bare `git diff HEAD` 를 쓰지 않는가

추적 파일만 보므로 Green 이 만든 **미추적** 파일을 로컬에서 못 보고 CI 에서만 잡는다
(cycle259 S4b). bare `git diff HEAD` 는 커밋 직후 공허해지고 다음 편집에서 무조건 RED 가
된다(cycle240 A11b · cycle252 G-252-5b). 스캔은 `Path(...).rglob("*.py")` + AST.

## ⚠️ dict 이름을 `*_CONTENT_SHA` 로 짓지 않았다

`test_cycle223g3_ast_guard_sees_staged.py::test_g3_9a` 가 모듈 레벨 `*_CONTENT_SHA`
dict 를 가진 테스트 파일 집합을 `_PIN_GUARD_FILES`(4개)로 고정한다. cycle274/278/282/
286/287 관례대로 `_BASE_SHA` 를 쓴다.

## ⚠️ 사이클 한정 — 다음 사이클의 갱신 의무

`_BASE_SHA` · `_SEGMENT_SHA` · `_ENGINE_PY_FILES` 는 cycle290 착수 시점(HEAD `b985938`
기준 워크트리)의 blob 을 고정한 것이라 cycle290 의 무접촉 증거로만 유효하다. 그 파일들을
**정당하게** 바꾸는 다음 사이클이 이 dict 를 갱신한다(고아 가드 방지).
"""

from __future__ import annotations

import ast
import hashlib
from functools import lru_cache
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parents[3]

_STRATEGY_META: tuple[tuple[str, str], ...] = (
    ("momentum", "MomentumStrategy"),
    ("volatility_breakout", "VolatilityBreakoutStrategy"),
    ("long_tail_volatility", "LongTailVolatilityStrategy"),
    ("donchian_swing", "DonchianSwingStrategy"),
    ("bull_flag_breakout", "BullFlagBreakoutStrategy"),
    ("vcp_breakout", "VcpBreakoutStrategy"),
    ("kojiro", "KojiroStrategy"),
)

#: cycle287 이 만들고 cycle290 이 등재하는 두 키.
_NEW_PARAM_KEYS: tuple[str, ...] = (
    "order_exchange_clock_mode",
    "after_market_exit_division",
)


@lru_cache(maxsize=64)
def _src(rel: str) -> str:
    return (_ROOT / rel).read_text(encoding="utf-8")


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ===========================================================================
# S1 — 프로덕션 무접촉 파일의 내용 sha
#
# cycle287 의 `_BASE_SHA` 와 달리 `order_engine.py`·`api/order.py`·`models/order.py`
# 가 **들어 있다** — cycle290 은 그 셋을 읽기만 한다.
# ===========================================================================
_BASE_SHA: dict[str, str] = {
    # 8영역 — 엔진 5파일 전부 (order_engine 포함! cycle290 은 무접촉)
    "src/engine/order_engine.py":
        "33033e740205ff01c6b1eb8090a35dfd6c9f88cc3f4172da45663b45aab3bd32",
    "src/engine/risk.py":
        "19f48b4a4f7c3b4aa47b99a1426d22ec26884277a9f711c279753d6d7452dcc7",
    "src/engine/session.py":
        "36257d86af1c26a868dc991a74a9eb139c98a9358d739d24600f5be2f9c5666c",
    "src/engine/scanner.py":
        "fa8c0377f850b031d1983923957eb92ea593dc0eb9c1423359d8561efde78fb9",
    "src/engine/strategy_registry.py":
        "d794696e54ffdc36efa6df917879d780e86bc1f373bb3b5d8dcbc0beac8cef8b",
    # 8영역 — api/order
    "src/api/order.py":
        "10a8a1dd57a702f78b31fdc84acb38f12a36f3a0688e6abcf801fc130f10154f",
    # 8영역 — realtime 전부
    "src/realtime/__init__.py":
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    "src/realtime/handler.py":
        "23768e6d89ed54b626cce2645a07cc5472ce10120c0b1c81f5d6436ff521ed47",
    "src/realtime/websocket.py":
        "1589cffb955e5af28ad0f145860bcc127ea8fda2b25d6817bd79c079472d5c4f",
    "src/realtime/websocket_pool.py":
        "bd1108dd40da4e72eab10581485b1b032e58af7c06754a9118fc7fafc20c8de7",
    # 8영역 — auth 전부
    "src/auth/__init__.py":
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    "src/auth/hashkey.py":
        "7c2aacc703839bdc274b463ee48777006504d70e4d59a1e57120ac5b612396d2",
    "src/auth/token.py":
        "049341c7286b57a06337b6bc73ff4b0269efffad8f4554d97f275e7b8ec30a54",
    # 8영역은 아니지만 이 사이클이 무접촉을 약속한 파일
    "src/engine/scheduler.py":
        "50658e06062a0d38afecab1baa08871b89212e295cc95f2a3af62a2ae076115d",
    "src/engine/strategy_base.py":
        "869dc20ca561adc561a9ebe9fdb5fe5a3e097f7ec176fdf274d577d509de9252",
    # 🔴 등재만으로 판정이 통해야 한다 — 검증 로직을 고쳐 통과시키면 안 된다.
    "src/engine/param_validation.py":
        "b4c5c029800191523bcc511919d6de3774e9ab49ca2fc0a0558ee3907868ee17",
    # 시각 표의 유일 정본 — 바꾸면 픽스처 동기 사슬이 통째로 딸려 온다(cycle282 i1~i3).
    "src/engine/market_state.py":
        "7cef2efeb55a7184391ac2cc447c90102fdd7ba507fd6e3834d24a8ad9ce006b",
}

#: cycle257 이 세운 영구 상한(정본). 종전 표기 `4,000` 은 느슨한 쪽이라 폐기됐다.
_SCHEDULER_LINE_CAP = 3900
_SCHEDULER_LINES = 3897


@pytest.mark.parametrize("rel", sorted(_BASE_SHA))
def test_g290_1_untouched_production_files_are_byte_identical(rel: str) -> None:
    """S1 — 무접촉 약속 파일의 내용 sha 가 착수 시점과 같다.

    🔴 `order_engine.py` 가 이 목록에 있는 것이 cycle287 과의 차이다 — 두 키를 읽는
    코드는 **이미 있다**. 주석이 낡았더라도 그 파일을 고치는 것은 8영역 승인 사안이고,
    자매 4핀(`test_cycle222a3`·`test_cycle223`·`test_cycle223f`·`test_cycle226`)과
    무조건 3핀까지 함께 붉어진다.
    """
    got = _sha(_src(rel))
    assert got == _BASE_SHA[rel], (
        f"{rel} 가 바뀌었다 — cycle290 은 전략 7파일 `DEFAULT_PARAMS` 와 "
        f"`param_catalog.py` 만 바꾼다. 현재 sha={got}"
    )


def test_g290_1b_scheduler_line_count_is_under_the_permanent_cap() -> None:
    """S1 — `scheduler.py` 라인 상한(cycle257 정본 3,900) 유지 + 착수 시점 값 고정."""
    lines = len(_src("src/engine/scheduler.py").splitlines())
    assert lines == _SCHEDULER_LINES, f"scheduler.py = {lines}L (착수 시점 {_SCHEDULER_LINES}L)"
    assert lines < _SCHEDULER_LINE_CAP, f"라인 상한 {_SCHEDULER_LINE_CAP} 초과: {lines}"


# ===========================================================================
# S2 — 전략 7파일의 진입·청산·사이징·준비 메서드 세그먼트 sha (28핀)
#
# 🔴 이 핀들은 cycle290 에서 **하나도 깨지지 않아야 한다.** 깨지면 핀을 옮기지 말고
#    코드를 되돌려라 — `DEFAULT_PARAMS`(클래스 속성) 밖을 건드린 것이다.
# ===========================================================================
_FROZEN_METHODS: tuple[str, ...] = (
    "check_buy_signal", "check_exit_signal", "calc_buy_quantity", "prepare",
)

_SEGMENT_SHA: dict[tuple[str, str], str] = {
    ("momentum", "check_buy_signal"):
        "d6af3d3867266d1bec2528aff385e2801565f2cfc76356fe1b4b03cdcbe4ccc9",
    ("momentum", "check_exit_signal"):
        "33c06df9546f40e91b1857300f0da8480eb671c1c8778454691248c9e90b9ef1",
    ("momentum", "calc_buy_quantity"):
        "1149ecc8ea37fb1ba164cc1fd88e6525111d5142168ca879f1026c7890905b81",
    ("momentum", "prepare"):
        "ca7a6e64c6d3032f0fbc752610b17f545afb43fda358dff64eb510e0b8395f81",
    ("volatility_breakout", "check_buy_signal"):
        "e620ae0d14a71f916550ee13f57edff12e1b84c12b8a4712b29583b44b56f20a",
    ("volatility_breakout", "check_exit_signal"):
        "86593b038e4cf8121ae47069fb368346edc50d9692b29db4cbdcc8897421b72e",
    ("volatility_breakout", "calc_buy_quantity"):
        "6d24ef3f3afd211ae6123623075b08320cdc08c9cd48a6db965355305ad4e732",
    ("volatility_breakout", "prepare"):
        "4f67ae86a6e8b81473ebd04bf072ad579845700290bf511377a5ba8c67778190",
    ("long_tail_volatility", "check_buy_signal"):
        "6c70101fe4abc9e5afc7f7e4a47af46ce5ebdf68fd84c2a18e22a46cb4546d1b",
    ("long_tail_volatility", "check_exit_signal"):
        "c8b0e6a8c8705d49bb6f12f82f505d426a5bdeb81413f8b2e0276eabb7dd9cad",
    ("long_tail_volatility", "calc_buy_quantity"):
        "1149ecc8ea37fb1ba164cc1fd88e6525111d5142168ca879f1026c7890905b81",
    ("long_tail_volatility", "prepare"):
        "70f3fbb893f67ab4bcc552e285f5e1653990ed82460e0e4415c46de8775538fc",
    ("donchian_swing", "check_buy_signal"):
        "c872af3dcc790942c4d954e47f2c2a9a64983b92fc0647c2e3605ab743a91ebc",
    ("donchian_swing", "check_exit_signal"):
        "86ae465f87a03bac0b3a418338f7a01e40c2f6992ef609791f915590dd5b85f4",
    ("donchian_swing", "calc_buy_quantity"):
        "35c9046669290d945e78282e50b87ee04bae9d6b276e3648004b3b89f95b4c5b",
    ("donchian_swing", "prepare"):
        "13ff9171d7fe8afea150b41b3228c51dd9ba168f17970524f76f00b2283a3a2a",
    ("bull_flag_breakout", "check_buy_signal"):
        "b39b26fb398ca352edaf91816b4aed04cd50f47aef29d13a8b82af0f6580ed7d",
    ("bull_flag_breakout", "check_exit_signal"):
        "eacb8a79407a37fb80227f977c54a7faac247ce525d3bfa10e54341965fd8796",
    ("bull_flag_breakout", "calc_buy_quantity"):
        "7b66c61590c8ccf51583c3121bf6519ff24c3529811ee856c730fbd8de7a850a",
    ("bull_flag_breakout", "prepare"):
        "cb0d01540a75049fcb06f90a24d35c606c2dc425599346fc0bf6ec4cde25dd9c",
    ("vcp_breakout", "check_buy_signal"):
        "66dbac6020acb0a8c5a97aaa7b1a0a768ecb574339d6c07e7ef5106462da00a6",
    ("vcp_breakout", "check_exit_signal"):
        "2fc8da7094dfa43a3baa824fb0c5d5864fd4ef89bd6786f5ff790216a00eabad",
    ("vcp_breakout", "calc_buy_quantity"):
        "2678212b154c25f00d8cb3a14ad819ad9e92a12787ff42b3635ac32399685e56",
    ("vcp_breakout", "prepare"):
        "7f2e5681f5fec0833d9adee9b7e51d2bdc567bfaa695cafaf1734a000e3cbaf8",
    ("kojiro", "check_buy_signal"):
        "dda6c6fc318afec8db576826f4cfc16d03fdc6dbdd544e7accc3f8a41de9e74f",
    ("kojiro", "check_exit_signal"):
        "067a60219099b081c64172986f46528a2836b1ad457c081ac06784c4ab9af7fc",
    ("kojiro", "calc_buy_quantity"):
        "f3491400f38b3295d37767b008c8821883f8443e76efe6ca26e792bf00e3c17e",
    ("kojiro", "prepare"):
        "336acbb1d525a0cd8e8303152f046894561995ec2f074198112394a100c9bec7",
}


def _class_node(module: str, cls_name: str) -> tuple[str, ast.ClassDef]:
    rel = f"src/engine/strategies/{module}.py"
    src = _src(rel)
    tree = ast.parse(src)
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == cls_name:
            return src, node
    raise AssertionError(f"{rel} 에 클래스 {cls_name} 부재")


@pytest.mark.parametrize("module, cls_name", _STRATEGY_META)
@pytest.mark.parametrize("method", _FROZEN_METHODS)
def test_g290_2_strategy_entry_exit_segments_are_byte_identical(
    module: str, cls_name: str, method: str
) -> None:
    """S2 — 진입·청산·사이징·준비 세그먼트 **28개** 전부 무변경.

    `DEFAULT_PARAMS` 는 클래스 속성이라 이 세그먼트 안에 없다 ⇒ 두 키 등재는 이
    핀들을 건드리지 않는다. **붉어지면 핀을 옮기지 말고 코드를 되돌려라.**
    """
    src, cls = _class_node(module, cls_name)
    fns = [
        s for s in cls.body
        if isinstance(s, (ast.FunctionDef, ast.AsyncFunctionDef)) and s.name == method
    ]
    assert fns, f"{module}.{cls_name}.{method} 부재"
    seg = ast.get_source_segment(src, fns[0]) or ""
    got = _sha(seg)
    assert got == _SEGMENT_SHA[(module, method)], (
        f"{module}.{method} 세그먼트가 바뀌었다 — cycle290 은 `DEFAULT_PARAMS` 만 "
        f"건드린다. 🔴 핀을 갱신하지 말고 코드를 되돌려라. 현재 sha={got}"
    )


# ===========================================================================
# S3 — `src/engine/` 아래 신규 `.py` 금지 (cycle287 `_PINNED_DIRS` 계약 승계)
# ===========================================================================
_ENGINE_PY_FILES: dict[str, tuple[str, ...]] = {
    "src/engine": (
        "__init__.py", "account_risk_guard.py", "account_risk_watcher.py",
        "backtest_engine.py", "backtest_orchestration.py", "backtest_yaml.py",
        "boot_manager.py", "daily_emit_cap.py", "daily_metrics_snapshot.py",
        "data_load_tasks.py", "kojiro_band_observe.py", "kojiro_gap_observe.py",
        "kojiro_indicators.py", "llm_buy_gate.py", "llm_features.py",
        "log_analysis_engine.py", "log_metrics_collector.py",
        "market_operation_monitor.py", "market_regime.py", "market_state.py",
        "metrics_collector.py", "no_feed_registry.py", "observer_trace.py",
        "open_price_observe.py", "open_price_rest.py", "order_engine.py",
        "param_catalog.py", "param_validation.py", "portfolio_risk.py",
        "quant_score.py", "quote_token_refresh.py", "recommendation_engine.py",
        "recommendation_metrics.py", "refresh_progress.py", "risk.py", "scanner.py",
        "scheduler.py", "sector_naming.py", "sell_rejection.py",
        "selling_reconcile.py", "session.py", "stale_diagnostics.py",
        "stale_manager.py", "stale_session_recovery.py", "stale_tracker.py",
        "stale_universe_guard.py", "stale_watcher_core.py",
        "stock_master_basics_metrics.py", "stock_master_daily_metrics.py",
        "stock_master_master_metrics.py", "stock_master_metrics.py", "strategy.py",
        "strategy_base.py", "strategy_registry.py", "ta_indicators.py",
        "task_loop_helper.py", "te_metrics.py", "tick_volume.py",
        "turtle_sizing.py", "uptime_monitor.py",
    ),
    "src/engine/strategies": (
        "__init__.py", "bull_flag_breakout.py", "donchian_swing.py", "kojiro.py",
        "long_tail_volatility.py", "momentum.py", "vcp_breakout.py",
        "volatility_breakout.py",
    ),
}


@pytest.mark.parametrize("rel_dir", sorted(_ENGINE_PY_FILES))
def test_g290_3_no_new_module_under_src_engine(rel_dir: str) -> None:
    """S3 — 이 사이클은 신규 모듈을 만들지 않는다(등재는 기존 파일 편집이다).

    cycle287 `_PINNED_DIRS` + `_SRC_TREE_FILES=148` 이 같은 계약을 잠근다 — 신규
    `.py` 를 만들면 그 가드까지 함께 붉어진다.
    """
    got = tuple(sorted(p.name for p in (_ROOT / rel_dir).glob("*.py")))
    assert got == _ENGINE_PY_FILES[rel_dir], (
        f"{rel_dir} 의 `.py` 파일 집합이 바뀌었다 — 신규: "
        f"{sorted(set(got) - set(_ENGINE_PY_FILES[rel_dir]))} / 삭제: "
        f"{sorted(set(_ENGINE_PY_FILES[rel_dir]) - set(got))}"
    )


# ===========================================================================
# S4 — 두 키는 `PARAM_RANGES`/`INT_PARAMS` 소스 리터럴로도 등장하지 않는다
#
# cycle287 `test_s5` 는 **런타임 dict** 를 검사한다. 여기서는 소스 텍스트로 이중
# 봉인한다(cycle242 G-242-1 · cycle245 G-245-1 관례). AI 자문이 청산 수단을 끄는
# 스위치를 뒤집는 경로는 열려서는 안 된다.
# ===========================================================================
@pytest.mark.parametrize("key", _NEW_PARAM_KEYS)
def test_g290_4_new_keys_absent_from_recommendation_engine_source(key: str) -> None:
    """S4 — `recommendation_engine.py` 소스에 두 키 문자열이 0건.

    `PARAM_RANGES`/`INT_PARAMS`/`_CONSERVATIVE_KEYS` 어디에도 넣지 않는다 —
    `_validate_recommendations`·`auto_apply`·수동 적용 4중 차단의 상류가 이것이다.
    """
    src = _src("src/engine/recommendation_engine.py")
    assert key not in src, (
        f"`{key}` 가 recommendation_engine.py 에 들어왔다 — AI 자문이 킬스위치를 "
        f"뒤집을 수 있게 된다"
    )


@pytest.mark.parametrize("dict_name", ["PARAM_RANGES", "INT_PARAMS"])
@pytest.mark.parametrize("key", _NEW_PARAM_KEYS)
def test_g290_4b_new_keys_absent_from_param_ranges_literals(
    dict_name: str, key: str
) -> None:
    """S4 — 소스 AST 로도 두 dict 리터럴의 키 집합에 없다(문자열 grep 보완)."""
    src = _src("src/engine/recommendation_engine.py")
    tree = ast.parse(src)
    for node in ast.walk(tree):
        # `PARAM_RANGES: dict[...] = {...}` 는 `AnnAssign`, `INT_PARAMS = {...}` 는
        # **set 리터럴**이다 — 둘 다 잡아야 가드가 공허해지지 않는다.
        if isinstance(node, ast.AnnAssign):
            names = [getattr(node.target, "id", None)]
        elif isinstance(node, ast.Assign):
            names = [getattr(t, "id", None) for t in node.targets]
        else:
            continue
        if dict_name not in names:
            continue
        value = node.value
        if isinstance(value, ast.Dict):
            literals = {
                k.value for k in value.keys
                if isinstance(k, ast.Constant) and isinstance(k.value, str)
            }
        elif isinstance(value, ast.Set):
            literals = {
                e.value for e in value.elts
                if isinstance(e, ast.Constant) and isinstance(e.value, str)
            }
        else:
            pytest.fail(
                f"{dict_name} 의 값이 dict/set 리터럴이 아니다 ({type(value).__name__}) "
                f"— 이 가드의 전제가 깨졌다"
            )
        assert literals, f"{dict_name} 리터럴이 비었다 — 가드가 공허해졌다"
        assert key not in literals, f"`{key}` 가 {dict_name} 리터럴에 있다"
        return
    pytest.fail(f"{dict_name} 대입문을 찾지 못했다 — 가드가 공허해졌다")


# ===========================================================================
# S5 — 문서 동기화 의무 (cycle272 `test_g272_28f` 패턴)
# ===========================================================================
_DOC_TARGETS: tuple[str, ...] = (
    "_workspace/00_leader_trading_rules.md",
    "src/engine/CLAUDE.md",
    "src/engine/strategies/CLAUDE.md",
)


@pytest.mark.parametrize("rel", _DOC_TARGETS)
@pytest.mark.parametrize("key", _NEW_PARAM_KEYS)
def test_g290_5_docs_declare_the_two_keys(rel: str, key: str) -> None:
    """S5 (RED) — 신규 `DEFAULT_PARAMS` 키는 문서 3곳에 기재된다.

    루트 CLAUDE.md 금기: "`DEFAULT_PARAMS` 변경 시
    `_workspace/00_leader_trading_rules.md` 동기화". cycle272 가 세운 선례는
    `src/engine/strategies/CLAUDE.md` 까지 요구한다. `src/engine/CLAUDE.md` 는
    「장중 킬스위치 없음」 절이 **거짓이 되는** 곳이라 함께 잠근다.
    """
    assert key in _src(rel), f"{rel} 에 `{key}` 기재 없음"


def test_g290_5b_engine_doc_no_longer_claims_the_killswitch_is_absent() -> None:
    """S5 (RED) — `src/engine/CLAUDE.md` 의 「장중 킬스위치 없음」 주장이 사라졌다.

    cycle287 이 정직하게 적어 둔 그 문장은 cycle290 으로 **거짓**이 된다. 지우지 말고
    "cycle290 이 등재로 열었다 + 그 전까지 왜 없었는지" 로 전환하라(자문 §S3-2).
    """
    doc = _src("src/engine/CLAUDE.md")
    assert "장중 킬스위치 없음" not in doc, (
        "cycle287 의 「장중 킬스위치 없음」 표제가 그대로 남아 있다 — cycle290 이후 "
        "거짓이다. 이력으로 전환하라"
    )
    # ⚠️ 문서 전체에 대한 `"cycle290" in doc` 전수 검사는 공허하다 — 이 사이클 자신이
    # 다른 문맥에서 "cycle290" 을 여러 번 언급하므로 OR 의 오른쪽이 항상 참이 되어
    # 미래에 「미등재」가 되살아나도 이 단언이 영원히 통과한다(검증 발견 LOW-5).
    # 그래서 **"미등재" 가 나오는 그 줄 자체**에 이력 표시가 있는지를 잰다.
    for line in doc.splitlines():
        if "미등재" not in line:
            continue
        assert "cycle290" in line, (
            f"「미등재」 문구가 있는 줄에 cycle290 이력 표시가 없다 — 문서가 코드와 "
            f"갈렸다: {line[:120]!r}"
        )


# ===========================================================================
# S6 — cycle287 이 예고한 계약 반전 (그 파일을 갱신하지 않으면 붉어진다)
# ===========================================================================
_CYCLE287_SCOPE = "tests/unit/ast/test_cycle287_ast_scope.py"


@pytest.mark.parametrize("rel", [f"src/engine/strategies/{m}.py" for m, _ in _STRATEGY_META])
@pytest.mark.parametrize("key", _NEW_PARAM_KEYS)
def test_g290_6_two_keys_present_in_every_strategy_source(rel: str, key: str) -> None:
    """S6 (RED) — 두 키가 전략 **7파일 소스 전부**에 있다.

    cycle287 `test_s5b` 의 정반대다(그쪽은 "어느 전략 파일에도 없다"를 단언했다).
    라우팅·애프터 청산은 `strategy_id` 로 params 를 조회하는 **전 전략 공통 경로**라
    일부만 등재하면 나머지 전략은 여전히 `unknown_key` 422 = 그 전략 포지션의 장중
    롤백 수단이 없다.
    """
    assert key in _src(rel), f"{rel} 에 `{key}` 부재 — 그 전략은 장중에 끌 수 없다"


def test_g290_6b_cycle287_scope_guard_was_updated() -> None:
    """S6 (RED) — cycle287 범위 가드의 낡은 계약 문구가 갱신됐다.

    🔴 `test_s7_new_keys_cannot_be_put_at_runtime` 은 **초록인 채로 거짓이 된다** —
    합성 dict `{"exchange": ..., "tradable_boards": ...}` 를 `current_params` 로 넘기고
    `param_validation` 의 판정이 `key not in current_params **or** spec is None` 이라,
    등재와 무관하게 영원히 `unknown_key` 다. 즉 그 가드는 등재 후에도 실패하지 않으면서
    "장중 킬스위치는 존재하지 않는다" 는 거짓 주장을 계속 지킨다.

    Green 은 그 테스트를 **실 `DEFAULT_PARAMS` 기반 "PUT 이 통한다" 가드로 재작성**하고
    (단언을 지우거나 skip 하지 말고 **강화 방향으로 반전**), `test_s5b` 도 존재 단언으로
    뒤집고, 파일 배너의 그 문장을 정직화해야 한다. 이 테스트가 그 의무의 forcing
    function 이다.
    """
    src = _src(_CYCLE287_SCOPE)
    assert "장중 킬스위치는 존재하지 않는다" not in src, (
        "cycle287 배너/S7 docstring 의 「장중 킬스위치는 존재하지 않는다」 가 남아 있다 "
        "— cycle290 이 열었으므로 거짓이다"
    )
    assert '(key, "unknown_key") in codes' not in src, (
        "`test_s7` 이 여전히 `unknown_key` 를 단언한다 — 그 단언은 합성 dict 때문에 "
        "등재 후에도 **초록인 채로 거짓**이다. 실 `DEFAULT_PARAMS` 를 current_params 로 "
        "넘기고 200 + accepted 를 단언하는 방향으로 재작성하라"
    )
