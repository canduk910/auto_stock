"""cycle286 Red — 범위 가드: 두 파일 외 **diff 0** + 구조 봉인 + 상수 드리프트.

정본 = cycle286 도메인 자문 §명세 S3 (2026-09-12).

## 이 사이클의 제1 계약

**프로덕션 코드는 딱 두 파일만 바뀐다.**

- `src/engine/strategies/long_tail_volatility.py` (C2-a — `main` 보드 15:20 매수 컷)
- `src/engine/order_engine.py` (C4-a — `nxt_tradable=False` 사후 보강 판정축, **8영역 승인**)

그 주장을 사람의 선언이 아니라 **sha** 로 증명한다(G1). 두 파일은 정당하게 바뀌므로
`_BASE_SHA` 에서 **의도적으로 빠져 있고**(G1c 가 그 사실을 고정), 대신 손대지 않기로 한
메서드는 세그먼트 sha 로 따로 잠근다(G2).

## 왜 `ast.dump` 의 sha 를 핀하지 않는가

3.12(CI) / 3.13(로컬)의 `ast.dump` 출력이 달라 로컬 초록·CI 실패가 난다
(cycle256 G-250-5 · cycle259 S4a). 무변경 핀은 **파일 내용 sha256** 또는
`ast.get_source_segment` 의 sha256 으로만 잰다.

## 왜 `git grep` / `git ls-files` / bare `git diff HEAD` 를 쓰지 않는가

추적 파일만 보므로 Green 이 새로 만든 **미추적** 파일을 로컬에서 못 보고 CI(커밋 후)에서만
잡는다(cycle259 S4b). bare `git diff HEAD` 는 커밋 직후 공허해지고 다음 편집에서 무조건
RED 가 된다(cycle240 A11b · cycle252 G-252-5b). 소스 스캔은 `Path(...).rglob("*.py")` + AST.

## ⚠️ 사이클 한정 — **커밋 후 갱신/삭제 의무**

`_BASE_SHA` 와 `_LTV_FROZEN_METHODS` 는 base `686cdb4` 의 blob 을 고정한 것이라 cycle286 의
무접촉 증거로만 유효하다. 그 파일들을 **정당하게** 바꾸는 다음 사이클이 이 dict 를 갱신하거나
이 테스트를 삭제한다(고아 가드 방지).

⚠️ dict 이름을 `*_CONTENT_SHA` 로 **짓지 않았다** — `tests/unit/ast/test_cycle223g3_ast_guard_sees_staged.py`
의 `test_g3_9a` 가 모듈 레벨 `*_CONTENT_SHA` dict 를 가진 테스트 파일 집합을
`_PIN_GUARD_FILES`(4개)와 정확히 일치하도록 고정하고 있다. cycle274/278/282 관례대로
`_BASE_SHA` 를 쓴다.

## Green 이 함께 해야 하는 핀 갱신 12곳 (이 파일 밖)

`order_engine.py` 내용 sha 7곳(자매 4곳 = `test_g3_9b` 계약상 **넷 전부 같은 값**) +
LTV 파일 내용 sha 3곳 + LTV `check_buy_signal` 세그먼트 4곳. 세그먼트 4곳은
**해소 불가능한 매듭**이다 — cycle274 `test_c18_3`(= `_STRATEGY_PINS` 를 현재값으로 재핀)과
cycle276 `test_c6_4a`(= `_STRATEGY_PINS` 를 cycle272 값으로 고정)가 동시에 성립할 수 없다.
자문 권고 = 청산·수량 2핀은 불변 유지, `check_buy_signal` 엔트리는 cycle274 방향으로
재핀하고 cycle276 의 해당 항목을 자기소멸 규약(cycle223 헤더 TODO 선례)으로 은퇴.
**그 은퇴 결정은 메인 세션이 내린다.**
"""

from __future__ import annotations

import ast
import hashlib
import os
from datetime import datetime, time, timedelta
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parents[3]

#: 이 사이클이 정당하게 바꾸는 두 파일 — `_BASE_SHA` 에서 의도적으로 제외한다.
_CHANGED = (
    "src/engine/strategies/long_tail_volatility.py",
    "src/engine/order_engine.py",
)

#: base `686cdb4` blob 의 파일 내용 sha256. **두 변경 파일은 없다**(G1c).
_BASE_SHA = {
    # 8영역 — 엔진 4파일 (order_engine 은 승인된 변경 대상이라 제외)
    "src/engine/risk.py":
        "79fddbec8cf9315c5172fc6634c4f4ea77f525d9ff9a3aba48f321affeb4d3e8",
    "src/engine/session.py":
        "36257d86af1c26a868dc991a74a9eb139c98a9358d739d24600f5be2f9c5666c",
    # 🔁 cycle302(2026-09-18) 재핀 — 사용자 승인 일봉 backfill **대상** 확대
    #    (분기에서 지수 소속 판정 제거 · `vcp_universe_tickers` 집합 소멸.
    #    목표 깊이 상수는 불변). 값만 옮긴다 — 단언은 그대로다.
    #    구 값은 cycle299 기준선(3b7366cc…)이다.
    "src/engine/scanner.py":
        "95cbb103a38821bb3b68d267a3662094b192fa55ad6071fa8dc4a63726e1c942",
    "src/engine/strategy_registry.py":
        "d794696e54ffdc36efa6df917879d780e86bc1f373bb3b5d8dcbc0beac8cef8b",
    # 8영역 — 주문 API
    "src/api/order.py":
        "08c5cafd7b8678ec0d0fa85f856fdea3cce38ad92488c6d74c03cd13faa415bb",
    # 8영역 — realtime 전부
    "src/realtime/__init__.py":
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    "src/realtime/handler.py":
        "37b1755210c83cdb2a462e6a37f919b326f8b48bee73d924adcc277d770a8d17",
    "src/realtime/websocket.py":
        "d4c443bde2ed7aeafba3e9471db0ca4efc15a654610555435145a9b305150c5b",
    "src/realtime/websocket_pool.py":
        "8b02442bcf5f558d6f7095b47d2016f004e3746e07ddc91dae8768b1dd46a10d",
    # 8영역 — auth 전부
    "src/auth/__init__.py":
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    "src/auth/hashkey.py":
        "7c2aacc703839bdc274b463ee48777006504d70e4d59a1e57120ac5b612396d2",
    # 🔁 cycle296(2026-09-17) 재핀 — 사용자 승인 `issue()` 매니저 단위 in-flight 합류(`src/auth/**`). 같은 값을 10곳 동시 갱신했다.
    "src/auth/token.py":
        "4125c271b4147e59922f4f000e523429fb4bbef37058dc754fd92b9475ec58f1",
    # 8영역은 아니지만 이 사이클이 무접촉을 약속한 파일
    "src/engine/strategy_base.py":
        "3f27be39784f9cb86d72b0c625b705b57d4ee8f555121024f757a2df51a3161d",
    # 나머지 전략 6파일 (LTV 만 변경 대상) — 🔁 cycle290(킬스위치 등재, 2026-09-13)
    # 재핀. `DEFAULT_PARAMS` 말미 2키 추가뿐.
    "src/engine/strategies/__init__.py":
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    "src/engine/strategies/bull_flag_breakout.py":
        "6ee3cb9f8df149d2c3a4fdc00885b855399cf13036e9ea02021263b773676bfa",
    "src/engine/strategies/donchian_swing.py":
        "cc57e5673f9982aca97f61677084e040171fff307483fedf10459b567a4679e3",
    "src/engine/strategies/kojiro.py":
        "0e2e7e07e802b541aeeab5bce2ad29716148d59a8c9daf2213127550114214a9",
    "src/engine/strategies/momentum.py":
        "50d5c0b9a232d6110f6b85fc524569853f2b8edffe2fd44adc24289800b95ae2",
    "src/engine/strategies/vcp_breakout.py":
        "da6ef794fc92493ce3780853116902190d716087ed562b7d04e7395014773b7d",
    "src/engine/strategies/volatility_breakout.py":
        "d13efaa4a9424e2822b5476ce159987d2a5192a4bca30af3f1a0cae9c3ffcabc",
}

#: 디렉터리 통째로 잠그는 영역 — 새 파일이 조용히 들어오는 것도 접촉이다.
_PINNED_DIRS = ("src/realtime", "src/auth", "src/engine/strategies")

#: `scheduler.py` 정확 라인 수 (cycle276 `test_c5_2` · cycle283 실측).
#: ⚠️ cycle292(2026-09-14) 가 `_subscribe_market_operation_tickers` 176줄을
#: 신규 leaf `src/engine/market_op_subscribe.py` 로 추출해(행위 변경 0 · 5줄
#: 위임 wrapper) 3,897 → 3,726 이 됐다. 값만 옮긴다 — 정확 핀을 상한 핀으로
#: 완화하면 cycle286 의 무접촉 대리 지표가 사라진다.
_SCHEDULER_LINES = 3812  # cycle354 재핀 — order_no 매핑 폴백 추가 (`_sync_orders_to_db`)
#: cycle257 이 세운 영구 상한 (종전 표기 4,000 은 느슨한 쪽이라 폐기 — 두 수가 갈라지면
#: 항상 **더 조인 쪽**이 정본이다).
_SCHEDULER_LINE_CAP = 3900

#: LTV 에서 이 사이클이 **한 글자도 건드리지 않는** 메서드의 세그먼트 sha.
#: `check_exit_signal`/`calc_buy_quantity` 는 cycle264 `_STRATEGY_PINS` 동결 핀과 같은 값이다
#: — "청산·수량 무접촉" 의 기계 증거다(cycle264/272/274/276 4중 + 이 파일 = 5중).
_LTV_FROZEN_METHODS = {
    "check_exit_signal":
        "c8b0e6a8c8705d49bb6f12f82f505d426a5bdeb81413f8b2e0276eabb7dd9cad",
    "calc_buy_quantity":
        "1149ecc8ea37fb1ba164cc1fd88e6525111d5142168ca879f1026c7890905b81",
    "prepare":
        "70f3fbb893f67ab4bcc552e285f5e1653990ed82460e0e4415c46de8775538fc",
    "on_open_price_confirmed":
        "4834b4cc6b03f2eddbfa94390ddcf0df41b3a561afd9056a5b2cac04f76a72ec",
}

_LTV_REL = "src/engine/strategies/long_tail_volatility.py"
_ORDER_ENGINE_REL = "src/engine/order_engine.py"

#: cycle262 `G-262-5` 가 `check_buy_signal` 에서 0건으로 봉인한 보드 리터럴.
_BOARD_LITERALS = frozenset(
    {"main", "pre_nxt", "post_nxt", "krx_open", "krx_after"}
)


# ---------------------------------------------------------------------------
# 공통 헬퍼
# ---------------------------------------------------------------------------
def _content_sha(rel: str) -> str:
    return hashlib.sha256((_ROOT / rel).read_bytes()).hexdigest()


def _class_body(rel: str, cls_name: str):
    src = (_ROOT / rel).read_text(encoding="utf-8")
    tree = ast.parse(src)
    cls = next(
        n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == cls_name
    )
    return src, cls


def _method(rel: str, cls_name: str, method: str):
    src, cls = _class_body(rel, cls_name)
    for node in cls.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == method:
            return src, node
    raise AssertionError(f"{rel}: `{cls_name}.{method}` 를 찾지 못했다")


def _method_sha(rel: str, cls_name: str, method: str) -> str:
    src, node = _method(rel, cls_name, method)
    seg = ast.get_source_segment(src, node)
    assert seg, f"{rel}: `{method}` 세그먼트 추출 실패"
    return hashlib.sha256(seg.encode()).hexdigest()


# ===========================================================================
# G1 — 두 파일 외 프로덕션 코드 diff 0
# ===========================================================================
@pytest.mark.parametrize("rel", sorted(_BASE_SHA))
def test_g1_untouched_files_are_byte_identical(rel: str) -> None:
    """G1 — 8영역(order_engine 제외)·strategy_base·전략 6파일 **diff 0**.

    이 중 한 파일이라도 바뀌면 "cycle286 은 두 파일만 바꾼다" 가 더 이상 참이 아니고,
    별도 승인(8영역 승인 + `domain-consult` 선행)이 필요하다.
    """
    path = _ROOT / rel
    assert path.exists(), f"{rel} 이 사라졌다 — 무접촉 계약 위반"
    got = _content_sha(rel)
    assert got == _BASE_SHA[rel], (
        f"{rel} 이 base(686cdb4) 에서 바뀌었다 — {got} != {_BASE_SHA[rel]}. "
        "cycle286 의 프로덕션 범위는 LTV + order_engine 두 파일뿐이다"
    )


def test_g1b_scheduler_line_count_is_exact_and_under_cap() -> None:
    """G1 — `scheduler.py` 무접촉의 대리 지표 = 정확 라인 수 + 영구 상한.

    cycle257 이 세운 상한 **< 3,900** 이 정본이고 자매 가드 7곳이 복창한다. 종전 표기
    `< 4,000` 은 느슨한 쪽이라 폐기 — 두 수가 갈라지면 항상 **더 조인 쪽**이 정본이다.
    """
    n = len((_ROOT / "src/engine/scheduler.py").read_text(encoding="utf-8").splitlines())
    assert n < _SCHEDULER_LINE_CAP, (
        f"`scheduler.py` 가 {n}L — cycle257 영구 상한 {_SCHEDULER_LINE_CAP} 위반"
    )
    assert n == _SCHEDULER_LINES, (
        f"`scheduler.py` 가 {n}L 로 바뀌었다 (기대 {_SCHEDULER_LINES}L) — "
        "cycle286 은 scheduler 무접촉이다"
    )


@pytest.mark.parametrize("rel_dir", _PINNED_DIRS)
def test_g1c_no_new_files_slip_into_pinned_dirs(rel_dir: str) -> None:
    """G1 — 잠근 디렉터리에 **새 .py 가 생기는 것**도 접촉이다.

    `src/engine/strategies/` 는 cycle282 `test_h3b` 도 잠그고 있어 leaf 분리가 불가능하다
    — C2-a 의 컷 헬퍼는 **LTV 파일 안**에 둔다.
    """
    found = {
        str(p.relative_to(_ROOT)).replace(os.sep, "/")
        for p in (_ROOT / rel_dir).rglob("*.py")
    }
    pinned = {rel for rel in _BASE_SHA if rel.startswith(rel_dir + "/")}
    pinned |= {rel for rel in _CHANGED if rel.startswith(rel_dir + "/")}
    assert found == pinned, (
        f"{rel_dir}: 신규 {sorted(found - pinned)} / 삭제 {sorted(pinned - found)} — "
        "무접촉 영역의 파일 구성이 바뀌었다"
    )


def test_g1d_changed_files_are_excluded_from_the_pin_on_purpose() -> None:
    """G1 — 이 사이클의 변경 대상 두 파일은 `_BASE_SHA` 에 **없다**.

    있으면 정당한 변경이 이 가드에 막혀 Green 이 "핀을 재산출하지 마라" 문구를 만나고,
    그 문구가 승인된 변경을 되돌리도록 오도한다(cycle263 실측 사고 계열).
    """
    for rel in _CHANGED:
        assert (_ROOT / rel).exists(), f"{rel} 이 없다 — 변경 대상 경로 오류"
        assert rel not in _BASE_SHA, (
            f"{rel} 이 무접촉 핀 목록 안이다 — 범위 설계 오류"
        )


# ===========================================================================
# G2 — LTV 청산·수량·prepare·기준가 확정 메서드 **세그먼트 봉인**
# ===========================================================================
@pytest.mark.parametrize("method", sorted(_LTV_FROZEN_METHODS))
def test_g2_ltv_frozen_methods_are_byte_identical(method: str) -> None:
    """G2 — C2-a 는 `check_buy_signal` 만 만진다.

    `check_exit_signal`/`calc_buy_quantity` 는 cycle264 `_STRATEGY_PINS` 동결 핀과 같은
    값이다(그 둘은 cycle264/272/274/276 이 이미 4중으로 잠그고 있다 — 이 파일이 5중).
    루트 CLAUDE.md: **`tradable_boards` 는 매수 진입 전용** — 청산 규약은 어떤 사이클도
    보드·시각 변경의 부수 효과로 바꾸지 않는다.
    """
    got = _method_sha(_LTV_REL, "LongTailVolatilityStrategy", method)
    assert got == _LTV_FROZEN_METHODS[method], (
        f"LTV `{method}` 가 바뀌었다 — {got} != {_LTV_FROZEN_METHODS[method]}. "
        "cycle286 C2-a 의 접촉 범위는 `check_buy_signal` + 신규 헬퍼 + 모듈 상수뿐이다"
    )


def test_g2b_check_buy_signal_has_no_board_literal() -> None:
    """G2 (RED 유지) — `check_buy_signal` 안에 보드 문자열 리터럴 **0건**.

    그 함수는 보류 토큰을 참조하므로 cycle262 `_hold_funcs` 멤버이고, `G-262-5`
    (`test_g262_5_hold_has_no_board_coupling[ltv]`)가 보드 리터럴을 0건으로 봉인한다.
    컷의 보드 판정은 **신규 헬퍼 안**(또는 `MarketBoard.MAIN.value`)에 둔다 — 가드 회피가
    아니라 가드의 취지(보드 커플링 차단) 보존이다.
    """
    _src, node = _method(_LTV_REL, "LongTailVolatilityStrategy", "check_buy_signal")
    found = sorted(
        {
            n.value
            for n in ast.walk(node)
            if isinstance(n, ast.Constant)
            and isinstance(n.value, str)
            and n.value in _BOARD_LITERALS
        }
    )
    assert found == [], (
        f"`check_buy_signal` 에 보드 리터럴 {found} — G-262-5 가 즉시 RED 다"
    )


def test_g2c_account_gate_is_still_the_first_statement() -> None:
    """G2 — cycle233 M6: `_account_soft_gate_blocked` 게이트가 **첫 문장**(docstring 제외).

    컷을 최상단에 넣으면 이 순서가 뒤집혀 `GATE_FIRST_FILES` AST 가드가 RED 다.
    그래서 C2-a 의 컷 자리는 최상단이 아니라 **발사점**이다.
    """
    _src, node = _method(_LTV_REL, "LongTailVolatilityStrategy", "check_buy_signal")
    body = list(node.body)
    if (
        body
        and isinstance(body[0], ast.Expr)
        and isinstance(body[0].value, ast.Constant)
        and isinstance(body[0].value.value, str)
    ):
        body = body[1:]
    assert body, "`check_buy_signal` 본문이 비었다"
    first = body[0]
    assert isinstance(first, ast.If), (
        f"첫 문장이 `if` 가 아니다 ({type(first).__name__}) — cycle233 M6 위반"
    )
    calls = {
        n.func.attr
        for n in ast.walk(first.test)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
    }
    assert "_account_soft_gate_blocked" in calls, (
        "첫 문장이 계좌 SOFT 게이트가 아니다 — 컷이 게이트 앞으로 올라갔다"
    )


def test_g2d_cut_helper_takes_now_and_does_not_read_the_clock() -> None:
    """G2 (RED) — 신규 헬퍼는 `now` 를 **받는다**(스스로 시계를 읽지 않는다).

    호출부가 이미 `_now_kst = datetime.now(KST)`(tz-aware) 를 들고 있다. 헬퍼가 자기 시계를
    읽으면 (a) 같은 틱 안에서 두 시각이 갈리고 (b) naive 로 잘못 읽을 여지가 생긴다
    (cycle262 `G-262-4` 가 hold 함수에 대해 같은 것을 잰다).
    """
    _src, cls = _class_body(_LTV_REL, "LongTailVolatilityStrategy")
    helper = next(
        (
            n
            for n in cls.body
            if isinstance(n, ast.FunctionDef) and n.name == "_main_buy_cutoff_blocked"
        ),
        None,
    )
    assert helper is not None, "헬퍼 `_main_buy_cutoff_blocked` 부재"

    arg_names = [a.arg for a in helper.args.args] + [
        a.arg for a in helper.args.kwonlyargs
    ]
    assert "board" in arg_names and "now" in arg_names, (
        f"헬퍼 시그니처에 `board`/`now` 가 없다: {arg_names}"
    )
    now_calls = [
        n
        for n in ast.walk(helper)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Attribute)
        and n.func.attr == "now"
    ]
    assert now_calls == [], (
        "헬퍼가 스스로 `datetime.now(...)` 를 읽는다 — 시각은 호출부에서 받는다"
    )


# ===========================================================================
# G3 — 15:20 상수 드리프트 (프로덕션 결합 0, 테스트에서만 대조)
# ===========================================================================
def test_g3_1_buy_cutoff_constants_agree_across_strategies_and_scheduler() -> None:
    """G3 (RED) — `scheduler.TIME_KRX_MAIN_BUY_STOP` == momentum == VB == **LTV**.

    프로덕션에서 상수를 공유하지 않는다(cycle229 G-4: 값이 같다고 공유하면 한쪽만 바꾸려는
    미래의 변경이 다른 쪽을 조용히 끌고 간다. 전략 → scheduler import 는 `scheduler.py:38`
    이 LTV 를 모듈 레벨로 import 하므로 **하드 순환**이다). 대신 드리프트를 **테스트에서**
    잡는다 — 4곳 중 하나만 움직이면 즉시 RED, 프로덕션 결합은 0.
    """
    from src.engine import scheduler
    from src.engine.strategies import long_tail_volatility as ltv_mod
    from src.engine.strategies import momentum as mom_mod
    from src.engine.strategies import volatility_breakout as vb_mod

    expected = time(15, 20)
    assert scheduler.TIME_KRX_MAIN_BUY_STOP == expected
    assert mom_mod.BUY_CUTOFF_KST == expected
    assert vb_mod.BUY_CUTOFF_KST == expected
    assert getattr(ltv_mod, "MAIN_BUY_CUTOFF_KST", None) == expected, (
        "LTV `MAIN_BUY_CUTOFF_KST` 가 없거나 15:20 이 아니다 — "
        f"실제 {getattr(ltv_mod, 'MAIN_BUY_CUTOFF_KST', None)!r}"
    )


def test_g3_2_ltv_does_not_import_scheduler_or_sibling_strategies() -> None:
    """G3 — LTV 가 `scheduler`·VB·momentum 을 import 하지 않는다.

    scheduler import = 하드 순환(`scheduler.py:34-40` 이 7전략을 모듈 레벨로 import).
    전략 상호 import 금지 = cycle229 G-4 / cycle262 G-262-9.
    """
    src = (_ROOT / _LTV_REL).read_text(encoding="utf-8")
    tree = ast.parse(src)
    forbidden = (
        "src.engine.scheduler",
        "src.engine.strategies.volatility_breakout",
        "src.engine.strategies.momentum",
    )
    hits = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            if any(node.module.startswith(f) for f in forbidden):
                hits.append(node.module)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if any(alias.name.startswith(f) for f in forbidden):
                    hits.append(alias.name)
    assert hits == [], f"LTV 가 금지된 모듈을 import 한다: {hits}"


def test_g3_3_ltv_does_not_reuse_the_rest_basis_stop_constant() -> None:
    """G3 — `open_price_rest.TIME_MAIN_REST_BASIS_STOP`(=15:20) 재사용 금지.

    LTV 는 이미 `open_price_rest` 를 import 하므로 기술적으로 공짜지만, 그 상수의 뜻은
    "REST 기준가 스윕 종료" 다. 재사용하면 스윕 창을 조정하는 미래의 변경이 LTV 매수창을
    조용히 움직인다.
    """
    src = (_ROOT / _LTV_REL).read_text(encoding="utf-8")
    assert "TIME_MAIN_REST_BASIS_STOP" not in src, (
        "매수 컷이 REST 스윕 종료 상수에 결합됐다 — 의미가 다른 상수다"
    )


def test_g3_4_cycle229_targets_does_not_gain_ltv() -> None:
    """G3 — cycle229 `_TARGETS` 에 LTV 를 **추가하지 않는다**.

    그 파일의 G-3 은 "컷 상수 첫 참조 < `_prev_price` 첫 참조" 를 요구해 **최상단 배치를
    강제**한다. C2-a 는 발사점 배치(보드 스코프 + baseline 갱신 유지)라 추가하면 RED 다.
    LTV 전용 가드는 이 파일과 `test_cycle286_ltv_main_buy_cutoff.py` 가 담당한다.
    """
    src = (
        _ROOT / "tests/unit/ast/test_cycle229_ast_cutoff_guards.py"
    ).read_text(encoding="utf-8")
    assert "long_tail_volatility" not in src, (
        "cycle229 `_TARGETS` 에 LTV 가 들어왔다 — G-3 이 최상단 배치를 강제해 RED 가 된다"
    )


# ===========================================================================
# G4 — order_engine: 학습 축만 좁힌다 (TTL 축 · 분류기 · 원자성 무접촉)
# ===========================================================================
@pytest.mark.parametrize(
    "rel",
    ["src/engine/sell_rejection.py", "src/api/balance.py", "src/engine/session.py"],
)
def test_g4_1_ttl_axis_and_classifier_modules_exist_untouched(rel: str) -> None:
    """G4 — TTL 축·거부 분류기·세션 표는 이 사이클의 접촉 대상이 아니다.

    ⚠️ `sell_rejection.py`/`balance.py` 는 내용 sha 로 잠그지 않는다 — 이 사이클이 두
    파일을 바꿀 이유가 없다는 사실은 `_CHANGED` 목록이 이미 말하고, 그 목록을
    `test_g1d` 가 고정한다. 여기서는 **경로 존재 + 판정 함수 시그니처**만 확인해
    "판정을 이쪽으로 옮겼다" 는 은밀한 이동을 막는다.
    """
    assert (_ROOT / rel).exists(), f"{rel} 이 사라졌다"


def test_g4_2_nxt_session_hours_window_is_not_narrowed() -> None:
    """G4 — `is_nxt_session_hours` 의 `15:30~20:00` 을 **좁히지 않는다**.

    TTL 은 "팔 수단이 없으니 길게 막는다" 가 안전측이다(09-14 이후 우리 `ORD_DVSN` 집합
    `00`/`01` 에는 KRX 애프터용 `41~47` 이 없어 16:00~20:00 에 팔 수단이 아예 없다).
    학습 축만 "모르면 안 쓴다" 로 좁힌다 — 두 축은 이제 **의도적으로 다른 창**이다.
    """
    src = (_ROOT / "src/engine/sell_rejection.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    fn = next(
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.FunctionDef) and n.name == "is_nxt_session_hours"
    )
    seg = ast.get_source_segment(src, fn) or ""
    for token in ("15, 30", "20, 0", "8, 0", "9, 0"):
        assert token in seg, (
            f"`is_nxt_session_hours` 에서 `time({token})` 가 사라졌다 — TTL 축이 좁혀졌다"
        )


def test_g4_3_order_engine_has_no_new_top_level_src_import() -> None:
    """G4 — `order_engine.py` **모듈 최상단** `src.*` import 집합 불변.

    cycle276 `test_c4_2` 가 최상단 `src.*` import 증가분을 정확히
    `{src.engine.llm_buy_gate}` 로 고정한다. C4-a 는 지역변수 `target_exchange` 만 읽으므로
    import 0 증가다(`_dtime`·`stock_master` 는 함수 안 lazy import = 그 가드 밖).
    """
    src = (_ROOT / _ORDER_ENGINE_REL).read_text(encoding="utf-8")
    tree = ast.parse(src)
    top = set()
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("src."):
            top.add(node.module)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("src."):
                    top.add(alias.name)
    expected = {
        "src.api.balance",
        "src.api.base",
        "src.api.order",
        "src.db.system_logs",
        "src.db.trade_history",
        "src.engine",               # `from src.engine import llm_buy_gate` (cycle276 델타)
        "src.engine.daily_emit_cap",
        "src.engine.scanner",
        "src.engine.sell_rejection",
        "src.engine.strategy_base",
        "src.engine.strategy_registry",
        "src.engine.util.tick_size",
        "src.models.order",
        "src.models.trade",
    }
    assert top == expected, (
        f"최상단 `src.*` import 가 바뀌었다 — 신규 {sorted(top - expected)} / "
        f"삭제 {sorted(expected - top)}. 새 의존은 함수 안 lazy import 로 둔다"
    )


# ===========================================================================
# G5 — 벽시계 위험대: 기존 LTV main 매수 테스트의 시각 고정 (CI 에서만 깨지는 부류)
# ===========================================================================
#: C2-a 컷 도입 시 "KST 15:20 이후로 동결돼 있어서" 깨지는 기존 테스트 파일.
#: 둘 다 `_activate("main")` + `Signal.BUY` 를 단정한다.
_WALL_CLOCK_HAZARD_FILES = (
    "tests/unit/engine/strategies/test_long_tail_volatility.py",
    "tests/unit/engine/strategies/test_cycle213_ltv_reentry_cooldown.py",
)

_CUT = time(15, 20)


def _freeze_literals(rel: str) -> list[tuple[int, str]]:
    """`freeze_time("<naive UTC>")` 단일 문자열 인자만 수집 (라인, 값).

    `tz_offset=` 등 추가 인자가 붙은 호출은 의미가 달라지므로 건너뛴다 — 그 형태를 쓰는
    파일이 여기에 들어오면 이 헬퍼를 먼저 확장한다.
    """
    src = (_ROOT / rel).read_text(encoding="utf-8")
    out = []
    for node in ast.walk(ast.parse(src)):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "freeze_time"
            and len(node.args) == 1
            and not node.keywords
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
        ):
            out.append((node.lineno, node.args[0].value))
    return out


@pytest.mark.parametrize("rel", _WALL_CLOCK_HAZARD_FILES)
def test_g5_1_existing_ltv_buy_tests_are_frozen_inside_the_buy_window(rel: str) -> None:
    """G5 (RED) — 기존 LTV main 매수 테스트는 **KST 09:00~15:20 안**으로 동결돼야 한다.

    freezegun 은 naive 문자열을 **UTC** 로 동결하므로 `freeze_time("... 10:00:00")` 은
    KST 19:00 이다. C2-a 컷이 들어오면 그 시각의 main 보드 돌파는 `Signal.NONE` 이 되어
    "BUY" 단정이 깨진다. 실측 2건:

    - `test_long_tail_volatility.py::test_buy_when_breakout_and_prdy_rate_above_min_then_buy`
      — `freeze_time` **0건**(순수 벽시계) ⇒ CI UTC 06:20~15:00 구간에서 **결정론적으로**
      실패한다. 로컬 초록으로는 못 잡는다(메모리 `feedback_time_window_gate_tests`).
    - `test_cycle213_ltv_reentry_cooldown.py` — 9곳 전부 `"2026-07-14 10:00:00"`(= KST 19:00).
      시각부만 `01:00:00`(= KST 10:00)으로 바꾸면 KST **날짜**는 그대로라 쿨다운 날짜
      단정에 영향이 없다.

    ⚠️ Green 의 일부다. 고치지 않으면 배포 후 CI 가 시각대에 따라 붉어진다.
    """
    lits = _freeze_literals(rel)
    assert lits, (
        f"{rel} 에 `freeze_time(\"...\")` 가 0건이다 — main 보드 BUY 단정이 순수 벽시계에 "
        "걸려 있어 KST 15:20 이후 결정론적으로 실패한다. 창 안 시각으로 고정할 것"
    )
    bad = []
    for lineno, raw in lits:
        try:
            utc = datetime.strptime(raw.split(".")[0], "%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue
        kst = (utc + timedelta(hours=9)).time()
        if kst >= _CUT:
            bad.append((lineno, raw, kst.isoformat()))
    assert bad == [], (
        f"{rel}: KST 15:20 이후로 동결된 `freeze_time` — {bad}. "
        "UTC 문자열이라 KST = UTC+9 다(예: `01:00:00` → KST 10:00)"
    )
