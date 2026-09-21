# DEST: /Users/koscom/Projects/auto_stock/tests/unit/ast/test_cycle273_ast_kojiro_rank.py
"""cycle273 D3 — AST 가드 (Red). 복원식 봉인 + leaf 순수성 + 무접촉 증명.

정본 = `_workspace/red/cycle273c_kojiro_rank_restore_spec.md`.

## 왜 `ast.dump` 로 핀하지 않는가
`ast.dump` 출력이 파이썬 3.12(CI)와 3.13(로컬)에서 달라 **로컬 초록·CI 실패**가 난다
(cycle256 G-250-5 · cycle259 S4a 실측). 본체 무변경 핀은 반드시
`ast.get_source_segment(src, fn)` 의 sha256 으로 잰다.

## 왜 `git grep`/`git ls-files` 를 쓰지 않는가
추적 파일만 보므로 Green 이 새로 만든 **미추적 leaf** 를 로컬에서 놓치고 CI 에서만
잡는다(cycle259 S4b). 소스 스캔은 `Path(...).rglob("*.py")` + AST 로 한다.

RED 예상: leaf 관련(C12·G-273-16/17 일부)·복원식 봉인(G-273-18) FAIL,
sha 핀(C10)·기존 카운트(G-273-17a)는 PASS.
"""
from __future__ import annotations

import ast
import hashlib
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

# 리포 루트는 `src` 패키지 위치에서 끌어온다(테스트 파일 경로 depth 에 의존하지
# 않으므로 보류 실행 위치가 달라도 같은 트리를 잰다).
import src.engine as _src_engine  # noqa: E402

_SRC = Path(_src_engine.__file__).resolve().parents[1]
_ROOT = _SRC.parent
_KOJIRO = _SRC / "engine" / "strategies" / "kojiro.py"
_LEAF = _SRC / "engine" / "kojiro_band_observe.py"

MARKER = "[kojiro_band_observe]"
MODULE_TOKEN = "kojiro_band_observe"


def _tree(path: Path) -> tuple[str, ast.Module]:
    src = path.read_text(encoding="utf-8")
    return src, ast.parse(src)


def _fn(tree: ast.Module, name: str, cls: str | None = None):
    scope = tree.body
    if cls is not None:
        scope = next(n for n in tree.body
                     if isinstance(n, ast.ClassDef) and n.name == cls).body
    return next(n for n in scope
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name)


def _call_names(tree: ast.AST) -> list[str]:
    out = []
    for n in ast.walk(tree):
        if isinstance(n, ast.Call):
            f = n.func
            out.append(getattr(f, "id", None) or getattr(f, "attr", None) or "")
    return out


# ===========================================================================
# C10 (G-273-7) — 진입/수량/청산 소스 세그먼트 sha 불변 (영구)
# ===========================================================================

_KOJIRO_PINS = {
    "check_buy_signal":
        "dda6c6fc318afec8db576826f4cfc16d03fdc6dbdd544e7accc3f8a41de9e74f",
    "calc_buy_quantity":
        "f3491400f38b3295d37767b008c8821883f8443e76efe6ca26e792bf00e3c17e",
    "check_exit_signal":
        "067a60219099b081c64172986f46528a2836b1ad457c081ac06784c4ab9af7fc",
}


@pytest.mark.parametrize("method", sorted(_KOJIRO_PINS))
def test_c10_g273_7_entry_exit_methods_pinned(method):
    """cycle273 은 **순위만** 바꾼다 — 매수·수량·청산은 한 글자도 안 바뀐다.

    핀 산출 기준 = HEAD `1df6d7d`. 이 sha 가 바뀌면 이 사이클의 제1 계약 위반이며,
    D3 가 아니라 **매매 행위 변경**이라 사용자 승인 + `domain-consult` 가 선행한다.
    """
    src, tree = _tree(_KOJIRO)
    seg = ast.get_source_segment(src, _fn(tree, method, cls="KojiroStrategy"))
    actual = hashlib.sha256(seg.encode("utf-8")).hexdigest()
    assert actual == _KOJIRO_PINS[method], (
        f"KojiroStrategy.{method} 가 바뀌었다 — 실측 sha={actual}"
    )


# ===========================================================================
# G-273-18 — 복원식 봉인 (뮤테이션 M1~M5 를 소스 레벨에서 되돌림 차단)
# ===========================================================================

def test_g273_18_restored_formula_is_present():
    """`_rank_candidate_components` 본문이 원설계 3요소를 담는다.

    ① `/ _RANK_LOOKBACK` (상수 참조 — 리터럴 `3` 하드코딩 금지)
    ② `iloc[-6:-1]` + `.mean()` (직전 5봉 평균 분모)
    ③ `> 0` 가드 (분모 <= 0 이면 0.0)
    그리고 **`1e-9` 는 사라져야 한다** — 그 엡실론이 좁은 밴드에 만점을 주던 장본인이다.
    """
    src, tree = _tree(_KOJIRO)
    fn = _fn(tree, "_rank_candidate_components", cls="KojiroStrategy")
    body = ast.get_source_segment(src, fn)

    assert "_RANK_LOOKBACK" in body, "봉 수 나눗셈이 상수 참조가 아니다(M2)"
    assert "iloc[-6:-1]" in body, "분모 창이 직전 5봉 평균이 아니다(M3)"
    assert ".mean()" in body, "분모가 평균이 아니다(M3)"
    assert "1e-9" not in body, (
        "단일봉 분모 엡실론이 남아 있다 — 이 사이클이 없앤 폭발 경로다(M4)"
    )
    # ③ 분모 가드가 `> 0` 이다(`>= 0` 은 ZeroDivision 을 되살린다 — M4)
    cmps = [n for n in ast.walk(fn) if isinstance(n, ast.Compare)]
    assert any(isinstance(c.ops[0], ast.Gt) for c in cmps), "`> 0` 가드 부재"
    assert not any(
        isinstance(c.ops[0], ast.GtE) and isinstance(c.comparators[0], ast.Constant)
        and c.comparators[0].value == 0
        for c in cmps
    ), "`>= 0` 가드는 분모 0 에서 ZeroDivisionError 를 낸다(M4)"


def test_g273_18b_close_normalization_is_present():
    """성분①이 종가로 나뉜다 — `/close` 삭제(M1) 차단."""
    src, tree = _tree(_KOJIRO)
    fn = _fn(tree, "_rank_candidate_components", cls="KojiroStrategy")
    body = ast.get_source_segment(src, fn)
    assert '"close"' in body or "'close'" in body, (
        "성분①이 종가를 읽지 않는다 — 원(₩) 단위 순위표로 되돌아갔다(M1)"
    )
    divs = [n for n in ast.walk(fn)
            if isinstance(n, ast.BinOp) and isinstance(n.op, ast.Div)]
    assert len(divs) >= 2, (
        f"나눗셈이 {len(divs)}개 — `/_RANK_LOOKBACK` 과 `/close` 둘 다 있어야 한다"
    )


def test_g273_18c_component_fn_stays_pure():
    """성분 함수는 순수하다 — `await`·DB·HTTP 0건(A-PURE 동형)."""
    _src, tree = _tree(_KOJIRO)
    fn = _fn(tree, "_rank_candidate_components", cls="KojiroStrategy")
    assert not [n for n in ast.walk(fn) if isinstance(n, ast.Await)]
    banned = {"pg", "fetch", "execute", "kis_request", "kis_get_quote", "httpx", "requests"}
    assert not (set(_call_names(fn)) & banned), "성분 함수에 I/O 가 들어왔다"


def test_g273_21_band_observe_row_stays_pure():
    """검증 라운드2 [LOW] — `_band_observe_row` 는 `prepare` 의 종목 루프 안에서
    종목마다 불린다(`test_g273_18c` 와 같은 A-PURE 사각을 메운다) — `await`·
    DB·HTTP 0건. 여기에 I/O 가 들어오면 관측이 스캔 속도·매수 타이밍을 바꾼다."""
    _src, tree = _tree(_KOJIRO)
    fn = _fn(tree, "_band_observe_row", cls="KojiroStrategy")
    assert not [n for n in ast.walk(fn) if isinstance(n, ast.Await)]
    banned = {"pg", "fetch", "execute", "kis_request", "kis_get_quote", "httpx", "requests"}
    assert not (set(_call_names(fn)) & banned), "관측 stash 헬퍼에 I/O 가 들어왔다"


# ===========================================================================
# C12 — leaf 순수성 (신규 파일)
# ===========================================================================

def _require_leaf() -> tuple[str, ast.Module]:
    assert _LEAF.exists(), (
        f"RED — 관측 leaf 미존재: {_LEAF.relative_to(_ROOT)}. "
        "Green 이 `kojiro_gap_observe.py` 구조 그대로(이름만 band) 만든다"
    )
    return _tree(_LEAF)


def test_c12_leaf_has_no_await_and_no_io():
    src, tree = _require_leaf()
    assert not [n for n in ast.walk(tree) if isinstance(n, ast.Await)], (
        "leaf 에 `await` 가 있다 — `prepare` 의 동기 구간에서 불린다"
    )
    banned_mods = {"asyncio", "httpx", "requests", "aiohttp",
                   "src.db.pg", "src.api.base", "supabase"}
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            for a in n.names:
                assert a.name not in banned_mods, f"금지 import: {a.name}"
        elif isinstance(n, ast.ImportFrom):
            assert (n.module or "") not in banned_mods, f"금지 import: {n.module}"
    assert "src.db" not in src.replace("src.db._kst", ""), "leaf 가 DB 를 만진다"


def test_c12b_leaf_writes_only_its_own_cap():
    """모듈 전역으로의 대입은 `_cap` 하나뿐 — 공유 상태 오염 0(cycle242 G-242-8 동형)."""
    _src, tree = _require_leaf()
    globals_written = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Global):
            globals_written |= set(n.names)
    assert globals_written <= {"_cap"}, f"leaf 가 다른 전역을 쓴다 — {globals_written}"
    # 모듈 레벨 대입 대상도 상수/`_cap` 뿐
    top_assigned = {
        t.id for n in tree.body if isinstance(n, ast.Assign)
        for t in n.targets if isinstance(t, ast.Name)
    } | {
        n.target.id for n in tree.body
        if isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name)
    }
    # ⚠️ cycle340 이 형제 관측기 `observe_macd`(대순환 MACD shadow)를 이 leaf 에
    # 더하며 모듈 상수 2개(`MACD_MARKER`·`_RULE_STAGES`)가 늘었다. 계약의 뜻은
    # "leaf 가 **가변 공유 상태**를 만들지 않는다" 이고 둘 다 불변 상수라 그 뜻은
    # 그대로다 — 집합만 넓히고 단언 형태는 유지한다(가변 전역은 여전히 붉어진다).
    assert top_assigned <= {
        "logger", "MARKER", "MODULE_TOKEN", "_cap",
        "MACD_MARKER", "_RULE_STAGES",
    }, (
        f"모듈 레벨 대입이 계약 밖 — {top_assigned}"
    )


def test_c12c_leaf_public_fns_never_raise_and_return_none():
    """`observe_band`·`observe_macd`·`absorb_band_call_failure` 는 본체 전체가 `try/except Exception`
    이고 반환은 `None` 고정이다(값 반환 금지 — 호출부가 그 값에 기대면 관측이 행위가 된다).
    """
    src, tree = _require_leaf()
    # cycle340 — `observe_macd` 도 같은 계약을 진다(형제 관측기).
    for name in ("observe_band", "observe_macd", "absorb_band_call_failure"):
        fn = _fn(tree, name)
        body = [s for s in fn.body if not (isinstance(s, ast.Expr)
                                           and isinstance(s.value, ast.Constant))]
        assert len(body) == 1 and isinstance(body[0], ast.Try), (
            f"{name} 본체가 단일 `try` 가 아니다 — 부분 방어는 방어가 아니다"
        )
        handlers = [h for h in body[0].handlers]
        assert any(
            h.type is None or getattr(h.type, "id", "") == "Exception" for h in handlers
        ), f"{name} 이 `Exception` 을 받지 않는다"
        for n in ast.walk(fn):
            if isinstance(n, ast.Return):
                assert n.value is None or (
                    isinstance(n.value, ast.Constant) and n.value.value is None
                ), f"{name} 이 값을 반환한다"


def test_c12d_leaf_failure_uses_observer_trace():
    """실패 흔적은 `observer_trace.trace_observer_failure` — 무흔적 `pass` 금지(cycle258)."""
    src, _tree_ = _require_leaf()
    assert "trace_observer_failure" in src, (
        "실패 경로가 흔적을 남기지 않는다 — 결측이 '이상 없음' 으로 오독된다"
    )
    assert "KstDailyEmitCap" in src, "cap 이 날짜 자기 리셋형이 아니다"


# ===========================================================================
# G-273-16 — 마커·모듈 토큰 격리 (영구)
# ===========================================================================

def test_g273_16_marker_confined_to_leaf_and_kojiro():
    """`[kojiro_band_observe]` 가 leaf·`kojiro.py` 밖 `src/` 로 새지 않는다."""
    offenders = [
        p.relative_to(_ROOT).as_posix() for p in _SRC.rglob("*.py")
        if MARKER in p.read_text(encoding="utf-8")
    ]
    assert sorted(offenders) == sorted({
        "src/engine/kojiro_band_observe.py",
        "src/engine/strategies/kojiro.py",
    }), f"마커 누출/부재 — 실측 {offenders}"


def test_g273_16b_marker_does_not_break_gap_observe_guard():
    """C13 — `kojiro_band_observe` 토큰이 `test_g268_9`(부분문자열 검색)를 안 깬다.

    `test_g268_9` 는 `"kojiro_gap_observe" in text` 로 스캔한다.
    `kojiro_band_observe` 는 그 부분문자열을 포함하지 않으므로 무충돌 — 그 사실을
    여기서 못 박는다(둘 중 하나를 개명하면 즉시 RED).
    """
    assert "kojiro_gap_observe" not in MODULE_TOKEN
    assert "[kojiro_gap_observe]" not in MARKER


# ===========================================================================
# G-273-17 — 이름 충돌 0 (cycle268 카운트 가드 회귀)
# ===========================================================================

def test_g273_17_gap_leaf_call_counts_unchanged():
    """`observe_gap` 6 · `absorb_call_failure` 6 — cycle268 가드가 세는 그 수.

    band leaf 를 같은 이름으로 만들면 이 카운트가 즉시 어긋나 `test_g268_3b`·
    `test_g268_4`·`test_g268_15b` 가 RED 가 된다(그래서 이름을 나눈다).
    """
    _src, tree = _tree(_KOJIRO)
    names = _call_names(tree)
    assert names.count("observe_gap") == 6, (
        f"observe_gap 호출 수 변동 — 실측 {names.count('observe_gap')}"
    )
    assert names.count("absorb_call_failure") == 6, (
        f"absorb_call_failure 호출 수 변동 — 실측 {names.count('absorb_call_failure')}"
    )


def test_g273_17b_band_leaf_called_exactly_once_from_prepare():
    """`observe_band` 는 `prepare` 안에서 **1회**, 흡수기도 **1회**.

    발화 지점이 늘어나면 cap 키 설계(`(ticker, role)`)가 깨지고, 줄면 배선이 죽는다.
    """
    _src, tree = _tree(_KOJIRO)
    names = _call_names(tree)
    assert names.count("observe_band") == 1, (
        f"observe_band 호출 수 — 실측 {names.count('observe_band')} (기대 1)"
    )
    assert names.count("absorb_band_call_failure") == 1
    prepare = _fn(tree, "prepare", cls="KojiroStrategy")
    assert _call_names(prepare).count("observe_band") == 1, (
        "발화 지점이 `prepare` 밖이다 — 점수 확정 뒤 1곳이 계약이다"
    )


# ===========================================================================
# G-273-19 — 신규 파라미터 키 0 / 임계 발명 금지
# ===========================================================================

def test_g273_19_no_new_default_params_key():
    """이 사이클은 `DEFAULT_PARAMS` 에 키를 만들지 않는다.

    밴드폭 최저 **관문**(`band_*_min` 류)은 이번 범위 밖이고, 키를 만들면
    `test_g268_7`(KOJIRO_PARAM_KEYS 동결)이 RED 가 되는 것이 **올바른 동작**이다.
    """
    from src.engine.strategies.kojiro import KojiroStrategy

    keys = set(KojiroStrategy.DEFAULT_PARAMS)
    forbidden = {k for k in keys if k.startswith("band_") and k.endswith("_min")}
    forbidden |= {k for k in keys if "rank_restore" in k or "band_floor" in k}
    assert not forbidden, f"관문/킬스위치 키가 생겼다 — {forbidden}"
    assert {"rank_w_macd3", "rank_w_band", "rank_w_fresh"} <= keys
    assert KojiroStrategy.DEFAULT_PARAMS["rank_w_macd3"] == 0.4
    assert KojiroStrategy.DEFAULT_PARAMS["rank_w_band"] == 0.3
    assert KojiroStrategy.DEFAULT_PARAMS["rank_w_fresh"] == 0.3


def test_g273_19b_rank_weights_stay_out_of_param_ranges():
    """랭킹 가중치는 AI 자문 자동 적용 경로 밖에 있다(리스크 정체성 상수 관례)."""
    from src.engine.recommendation_engine import PARAM_RANGES

    for k in ("rank_w_macd3", "rank_w_band", "rank_w_fresh"):
        assert k not in PARAM_RANGES


# ===========================================================================
# G-273-20 — 8영역·scheduler 무접촉 (영구 형태: 마커·import 격리)
# ===========================================================================

_EIGHT_AREA_PATHS = (
    "src/engine/risk.py", "src/engine/order_engine.py", "src/engine/session.py",
    "src/engine/scanner.py", "src/engine/strategy_registry.py", "src/api/order.py",
)


def test_g273_20_eight_areas_and_scheduler_do_not_import_the_leaf():
    """8영역·`scheduler.py` 는 이 사이클의 leaf 를 모른다 — 접촉 0 의 구조적 증거.

    (`git diff` 기반 범위 가드는 커밋 직후 공허해져 다음 편집에서 무조건 RED 가
    된다 — cycle240 A11b · cycle252 G-252-5b. 그래서 **내용 기반**으로 잰다.)
    """
    targets = [_ROOT / p for p in _EIGHT_AREA_PATHS]
    targets.append(_SRC / "engine" / "scheduler.py")
    targets += sorted((_SRC / "realtime").rglob("*.py"))
    targets += sorted((_SRC / "auth").rglob("*.py"))
    for p in targets:
        if not p.exists():
            continue
        text = p.read_text(encoding="utf-8")
        assert MODULE_TOKEN not in text, f"{p.relative_to(_ROOT)} 가 leaf 를 참조한다"
        assert MARKER not in text


def test_g273_20b_scheduler_line_cap_unchanged():
    """`scheduler.py` < 3,900L (cycle257 영구 상한) — 이 사이클은 무접촉이다."""
    n = len((_SRC / "engine" / "scheduler.py").read_text(encoding="utf-8").splitlines())
    assert n < 3900, f"scheduler.py {n}L — cycle257 상한 위반"
