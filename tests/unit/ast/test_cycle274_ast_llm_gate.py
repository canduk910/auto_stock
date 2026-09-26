"""cycle274 Red — AST/구조 가드 (행위 0 의 **기계 증명**).

정본 = `_workspace/domain_consult/cycle274_llm_buy_gate_20260910.md`
(§9 C1 · C5 · C10 · C15 · C16 · C17 · C18 · §10 leaf import 한정)

🔁 **2026-09-11 cycle276 승계** — 관측 훅이 전략의 `check_buy_signal` 에서
`order_engine.execute_buy`(주문 접수 직후)로 **옮겨졌다**. 그래서
① 전략 배선을 재던 C1 그룹은 이 파일에서 **삭제**하고(그 자리를
`test_cycle276_ast_order_hook.py::test_c6_*` 가 "배선 0건" 으로 대신 잰다),
② leaf 진입점 이름이 `observe_signal` → `observe_order` 로 바뀌었으며,
③ `wait_for`/`CancelledError` 계약은 `_evaluate` → `_evaluate_core` 로 내려갔고,
④ `order_engine.py` 는 이 사이클의 **승인된** 8영역 변경이라 `_BASE_SHA` 를 재핀했다.
살아남은 케이스(C5 본체 계약 · §10 import 한정 · C10 4키 · C17 read-only ·
C15/C16 무접촉)는 여전히 유효한 영구 가드다.

## 왜 `git grep`/`git ls-files` 로 소스를 스캔하지 않는가

추적 파일만 보므로 Green 이 새로 만든 **미추적** 파일을 로컬에서 못 보고 CI(커밋 후)
에서만 잡는다(cycle259 S4b). 소스 스캔은 `Path(...).rglob` + AST 로 한다.

## 왜 `ast.dump` 의 sha 를 핀하지 않는가

3.12(CI) / 3.13(로컬) 출력이 달라 로컬 초록·CI 실패가 난다(cycle256 G-250-5 ·
cycle259 S4a). 본체 무변경 핀은 `ast.get_source_segment` 의 sha256 또는 파일
내용 sha256 으로 잰다.

## ⚠️ 사이클 한정 — 커밋 후 정리 의무

`test_c15_*`(8영역 내용 sha 핀)는 **브랜치 base `4ca3463` 의 blob sha** 를 고정한 것이라
cycle274 의 "8영역 무접촉" 증거로만 유효하다. 이후 8영역을 **정당하게** 바꾸는 사이클이
오면 그 사이클이 이 dict 를 갱신하거나 이 테스트를 삭제한다(고아 가드 방지 — cycle240
A11b · cycle252 G-252-5b). `bare git diff HEAD` 를 쓰지 않는 이유도 같다: 커밋 직후
공허해지고 다음 편집에서 무조건 붉어진다.
"""

from __future__ import annotations

import ast
import hashlib
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parents[3]
_SRC = _ROOT / "src"
_STRATEGY_DIR = _SRC / "engine" / "strategies"

_LEAF_GATE = _SRC / "engine" / "llm_buy_gate.py"
_LEAF_FEATURES = _SRC / "engine" / "llm_features.py"
_VB = _STRATEGY_DIR / "volatility_breakout.py"
_LTV = _STRATEGY_DIR / "long_tail_volatility.py"
_RECO = _SRC / "engine" / "recommendation_engine.py"
_SCHEDULER = _SRC / "engine" / "scheduler.py"

_VB_REL = "src/engine/strategies/volatility_breakout.py"
_LTV_REL = "src/engine/strategies/long_tail_volatility.py"

_KEYS = (
    "llm_gate_mode",
    "llm_gate_min_score",
    "llm_gate_daily_call_cap",
    "llm_gate_timeout_secs",
)

# cycle276 — DB 기록 채널 `[llm_eval_persist]` 를 더해 **5종**이다(C26).
_MARKERS = (
    "[llm_buy_score]",
    "[llm_buy_score_failed]",
    "[llm_gate_config]",
    "[llm_gate_daily_cap]",
    "[llm_eval_persist]",
)

_REASONS = (
    "timeout", "api_error", "parse_error", "schema_error",
    "no_bars", "no_key", "cap_exceeded", "disabled_model",
)


# ---------------------------------------------------------------------------
# 헬퍼
# ---------------------------------------------------------------------------
def _read(path: Path) -> str:
    assert path.exists(), (
        f"{path.relative_to(_ROOT)} 가 없다 — 자문 §10 파일 목록 미이행(Red)"
    )
    return path.read_text(encoding="utf-8")


def _tree(path: Path) -> tuple[ast.Module, str]:
    src = _read(path)
    return ast.parse(src), src


def _func(tree: ast.Module, name: str):
    for n in ast.walk(tree):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name:
            return n
    return None


def _method(tree: ast.Module, cls_name: str, name: str):
    for cls in ast.walk(tree):
        if isinstance(cls, ast.ClassDef) and cls.name == cls_name:
            for n in cls.body:
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name:
                    return n
    return None


def _parents(tree: ast.AST) -> dict[int, ast.AST]:
    out: dict[int, ast.AST] = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            out[id(child)] = parent
    return out


def _content_sha(rel: str) -> str:
    return hashlib.sha256((_ROOT / rel).read_bytes()).hexdigest()


def _method_segment(module_path: Path, cls_name: str, method: str) -> str:
    src = _read(module_path)
    tree = ast.parse(src)
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == cls_name)
    fn = next(
        n for n in cls.body
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == method
    )
    return ast.get_source_segment(src, fn) or ""


_STRATEGY_META = {
    "vb": (_VB, "VolatilityBreakoutStrategy"),
    "ltv": (_LTV, "LongTailVolatilityStrategy"),
}
_KINDS = ("vb", "ltv")


# ===========================================================================
# C5 — `observe_order` 본체: await/DB/HTTP 0, `create_task` 정확 1회 (HIGH)
#
# 🔁 cycle276 — 진입점 이름이 `observe_signal` → `observe_order` 다(신호 시점 →
#    주문 접수 시점). 계약 자체는 한 글자도 완화되지 않았다.
# ===========================================================================
def _observe_fn():
    tree, _src = _tree(_LEAF_GATE)
    fn = _func(tree, "observe_order")
    assert fn is not None, "`observe_order` 가 leaf 에 없다"
    return fn


def test_c5_1_observe_is_sync_def() -> None:
    """C5 (HIGH) — `observe_order` 는 **동기** 함수다(`async def` 금지)."""
    tree, _src = _tree(_LEAF_GATE)
    fn = _func(tree, "observe_order")
    assert isinstance(fn, ast.FunctionDef), "`async def observe_order` 은 계약 위반"


def test_c5_2_no_await_in_observe() -> None:
    """C5 (HIGH) — 본체에 `Await`/`AsyncFor`/`AsyncWith` 0건.

    `check_buy_signal` 은 동기이고 틱마다 돈다. 여기서 한 번 기다리면 그 틱의
    나머지 전략 평가가 전부 밀린다.
    """
    bad = [
        type(n).__name__ for n in ast.walk(_observe_fn())
        if isinstance(n, (ast.Await, ast.AsyncFor, ast.AsyncWith))
    ]
    assert bad == [], f"동기 hot path 에 비동기 구문: {bad}"


def test_c5_3_no_db_or_http_in_observe() -> None:
    """C5 (HIGH) — DB/HTTP 호출 흔적 0건(`pg.`·`fetch`·`httpx`·`client.`)."""
    fn = _observe_fn()
    seg = ast.get_source_segment(_read(_LEAF_GATE), fn) or ""
    for token in ("pg.", "httpx", "get_recent_daily", "chat.completions"):
        assert token not in seg, f"`observe_order` 안에 `{token}` — 동기 경로 오염"


def test_c5_4_create_task_called_exactly_once() -> None:
    """C5 (HIGH) — `asyncio.create_task` Call 이 정확히 1개.

    2개면 같은 신호가 두 번 평가돼 비용·표본이 모두 어긋난다.
    """
    calls = [
        n for n in ast.walk(_observe_fn())
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
        and n.func.attr == "create_task"
    ]
    assert len(calls) == 1, f"`create_task` {len(calls)}건 (기대 1)"


def test_c5_5_latch_mark_precedes_create_task() -> None:
    """C5 (뮤테이션 '래치 mark 를 create_task 뒤로 이동' 킬).

    mark 가 `create_task` **앞**에 있어야 중복 발사가 구조적으로 막힌다. 런타임
    테스트로는 이 순서를 구별할 수 없다(둘 사이에 양보가 없어 결과가 같다) —
    그래서 **줄 순서** 로만 잰다.
    """
    fn = _observe_fn()
    # 검증 라운드 2 HIGH — `_daily_cap_warned.mark_emitted`(cap 경고 래치)는 항상
    # create_task 앞이라 `min(marks)` 판정이 미끼에 속았다. **래치 인스턴스
    # `_latch` 의 mark 만** 모으고, 그 **전부**가 첫 create_task 앞이어야 한다.
    marks = [
        n.lineno for n in ast.walk(fn)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
        and n.func.attr == "mark_emitted"
        and isinstance(n.func.value, ast.Name) and n.func.value.id == "_latch"
    ]
    tasks = [
        n.lineno for n in ast.walk(fn)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
        and n.func.attr == "create_task"
    ]
    assert marks, "`_latch.mark_emitted` 호출이 없다"
    assert tasks, "`create_task` 호출이 없다"
    assert max(marks) < min(tasks), (
        f"`_latch.mark_emitted`(lines {marks}) 가 create_task(line {min(tasks)}) 뒤에 있다 — 중복 발사"
    )


def test_c5_6_observe_body_is_wrapped_in_try_except_exception() -> None:
    """C5/§5.2 — 본체 전체가 `try/except Exception` 하나. never-raise 의 구조적 근거.

    좁은 튜플(`except (TypeError, ValueError)`)은 `int(inf)` 의 `OverflowError` 에서
    뚫린다(cycle262 적대 검증 HIGH). 뮤테이션 `except Exception` → 좁은 튜플을 죽인다.
    """
    fn = _observe_fn()
    tries = [n for n in fn.body if isinstance(n, ast.Try)]
    assert tries, "`observe_order` 본체에 최상위 `try` 가 없다"
    handlers = [h for t in tries for h in t.handlers]
    assert any(
        isinstance(h.type, ast.Name) and h.type.id == "Exception" for h in handlers
    ), "`except Exception` 이 없다(좁은 예외 튜플은 OverflowError 를 놓친다)"


def test_c5_7_observe_returns_none_only() -> None:
    """C5/§5.2 — 반환은 항상 `None`(값을 돌려주면 호출부가 언젠가 그것을 읽는다)."""
    fn = _observe_fn()
    bad = [
        n.lineno for n in ast.walk(fn)
        if isinstance(n, ast.Return) and n.value is not None
        and not (isinstance(n.value, ast.Constant) and n.value.value is None)
    ]
    assert bad == [], f"값을 돌려주는 return: line {bad}"


def test_c5_8_observe_leaves_a_trace_on_failure() -> None:
    """C5/cycle258 카드 #5 — 흡수기가 `trace_observer_failure` 를 부른다(무흔적 pass 금지)."""
    seg = ast.get_source_segment(_read(_LEAF_GATE), _observe_fn()) or ""
    assert "trace_observer_failure" in seg


def test_c5_9_evaluate_uses_wait_for_with_timeout() -> None:
    """C5/§4.4 — LLM 콜이 `asyncio.wait_for(..., timeout=...)` 로 감싸여 있다.

    `AsyncOpenAI` 기본 타임아웃은 **600s** 다. 지정하지 않으면 task 가 10분 산다.
    🔁 cycle276 — 콜 본체가 `_evaluate` → `_evaluate_core` 로 내려갔다(`_evaluate` 는
    outcome 을 받아 DB 에 1행 기록하는 얇은 진입점이 됐다).
    """
    tree, src = _tree(_LEAF_GATE)
    fn = _func(tree, "_evaluate_core")
    assert fn is not None, "`_evaluate_core` 부재"
    calls = [
        n for n in ast.walk(fn)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
        and n.func.attr == "wait_for"
    ]
    assert calls, "`asyncio.wait_for` 미사용"
    assert any(kw.arg == "timeout" for c in calls for kw in c.keywords), (
        "`wait_for` 에 `timeout=` 키워드가 없다"
    )


def test_c5_10_evaluate_reraises_cancelled_error() -> None:
    """C5/§5.3 — `asyncio.CancelledError` 는 re-raise(cycle272 `open_price_rest` 계약).

    🔁 cycle276 — 본체가 `_evaluate_core` 로 내려갔다(진입점 `_evaluate` 도 같은 계약을
    지키지만, 취소가 갇히면 안 되는 자리는 실제 await 가 있는 core 다).
    """
    src = _read(_LEAF_GATE)
    fn = _func(ast.parse(src), "_evaluate_core")
    assert fn is not None, "`_evaluate_core` 부재"
    seg = ast.get_source_segment(src, fn) or ""
    assert "CancelledError" in seg, "`CancelledError` 분기 부재 — 취소가 본체에 갇힌다"
    assert "raise" in seg


def test_c5_11_semaphore_is_two() -> None:
    """C5/§5.4 (뮤테이션 '세마포어 무제한' 킬) — 전역 `Semaphore(2)` 리터럴."""
    src = _read(_LEAF_GATE)
    assert re.search(r"Semaphore\(\s*2\s*\)", src), "전역 `asyncio.Semaphore(2)` 부재"


def test_c5_12_max_retries_zero_and_no_temperature() -> None:
    """C5/§4.4 — SDK 재시도 0(지연 3배화 방지) · `temperature` 미지정.

    gpt-5 계열은 1 이외 `temperature` 를 거부할 수 있고 거부는 fail-open 으로
    흡수되지만 그러면 게이트가 **조용히 죽는다**(§11 Q10).
    """
    src = _read(_LEAF_GATE)
    assert re.search(r"max_retries\s*=\s*0", src), "`max_retries=0` 부재"
    # 주석·docstring 은 세지 않는다 — **실제 인자**만 본다(문자열 검사는 설명문까지 잡는다).
    tree = ast.parse(src)
    bad = [
        n.lineno for n in ast.walk(tree)
        if isinstance(n, ast.Call)
        for kw in n.keywords if kw.arg == "temperature"
    ]
    assert not bad, f"`temperature=` 를 인자로 넘긴다(§4.4 위반): line {bad}"


# ===========================================================================
# leaf import 한정 (§10) + 마커 스코프
# ===========================================================================
_ALLOWED_LEAF_IMPORTS = {
    "src.engine.daily_emit_cap",
    "src.engine.observer_trace",
    "src.engine.llm_features",
    "src.config",
    "src.db.stock_master_daily",
}


def test_g1_1_leaf_module_level_src_imports_are_limited() -> None:
    """§10 — leaf 의 **모듈 최상단** `src.*` import 는 허용 목록으로 한정된다.

    `scanner` 는 함수 내 **지연 import** 여야 한다(순환 차단 — cycle268/272 선례).
    이 한정이 곧 "leaf 는 8영역을 모듈 로드 시점에 끌어오지 않는다" 의 증거다.
    """
    tree, _src = _tree(_LEAF_GATE)
    mods = set()
    for n in tree.body:      # 최상단만
        if isinstance(n, ast.ImportFrom) and (n.module or "").startswith("src"):
            mods.add(n.module)
        elif isinstance(n, ast.Import):
            mods |= {a.name for a in n.names if a.name.startswith("src")}
    extra = mods - _ALLOWED_LEAF_IMPORTS
    assert not extra, f"leaf 모듈 최상단 import 위반: {sorted(extra)}"


def test_g1_2_features_module_imports_no_src() -> None:
    """§10 — `llm_features` 는 **순수 함수** 모듈이다. `src.*` import 0건."""
    tree, _src = _tree(_LEAF_FEATURES)
    mods = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.ImportFrom) and (n.module or "").startswith("src"):
            mods.add(n.module)
        elif isinstance(n, ast.Import):
            mods |= {a.name for a in n.names if a.name.startswith("src")}
    assert not mods, f"`llm_features` 가 `src.*` 를 import 한다: {sorted(mods)}"


def test_g1_3_scanner_is_lazy_imported_inside_a_function() -> None:
    """§7.2 — `scanner` 는 함수 안에서만 import 된다(모듈 최상단 금지)."""
    tree, _src = _tree(_LEAF_GATE)
    top = {
        n.module for n in tree.body
        if isinstance(n, ast.ImportFrom) and n.module
    }
    assert not any("scanner" in (m or "") for m in top), "scanner 모듈 최상단 import"
    inner = [
        n for n in ast.walk(tree)
        if isinstance(n, ast.ImportFrom) and "scanner" in (n.module or "")
    ]
    assert inner, "`scanner` 지연 import 가 없다 — `slip_bp` 를 어디서 읽나"


def test_g1_4_markers_live_only_in_the_leaf() -> None:
    """§7.1 — 마커 4종 문자열은 leaf 한 파일에만 존재한다(전략·8영역으로 새지 않는다).

    소스 스캔은 `rglob`(미추적 파일 포함) — `git grep` 은 Green 이 새로 만든 파일을
    로컬에서 놓친다(cycle259 S4b).
    """
    offenders: dict[str, list[str]] = {}
    for path in _SRC.rglob("*.py"):
        if path == _LEAF_GATE:
            continue
        text = path.read_text(encoding="utf-8")
        hits = [m for m in _MARKERS if m in text]
        if hits:
            offenders[path.relative_to(_ROOT).as_posix()] = hits
    assert not offenders, f"cycle274 마커가 leaf 밖에 있다: {offenders}"


def test_g1_5_failure_reason_vocabulary_is_complete() -> None:
    """§7.1 ② — 실패 사유 8종이 전부 leaf 소스에 리터럴로 존재한다.

    어휘가 빠지면 그 실패는 다른 사유로 뭉뚱그려져 **실패 분포가 왜곡**되고,
    2주 뒤 "실패율 <10%" 게이트가 무엇을 잰 것인지 알 수 없게 된다.
    """
    src = _read(_LEAF_GATE)
    missing = [r for r in _REASONS if f'"{r}"' not in src and f"'{r}'" not in src]
    assert not missing, f"실패 사유 리터럴 누락: {missing}"


def test_g1_6_no_openai_call_at_import_time() -> None:
    """§4.4 — 모듈 최상단에서 `AsyncOpenAI()` 를 만들지 않는다(지연 import 싱글톤).

    `recommendation_engine._call_openai` 는 콜마다 새로 만든다(하루 4번이면 무해).
    hot path 는 커넥션 풀을 재사용해야 하지만, **import 시점**에 만들면 키가 없는
    테스트/CLI 환경에서 모듈 로드 자체가 실패한다.
    """
    tree, _src = _tree(_LEAF_GATE)
    top_calls = [
        n for n in tree.body
        if isinstance(n, (ast.Assign, ast.Expr))
        for c in ast.walk(n)
        if isinstance(c, ast.Call) and isinstance(c.func, ast.Name)
        and c.func.id == "AsyncOpenAI"
    ]
    assert not top_calls, "모듈 최상단에서 AsyncOpenAI 를 생성한다"


# ===========================================================================
# C10 — `PARAM_RANGES` / `INT_PARAMS` 미편입 (런타임 + 소스 이중, G-242-1 답습)
# ===========================================================================
@pytest.mark.parametrize("key", _KEYS)
def test_c10_1_runtime_dicts_exclude_key(key: str) -> None:
    """C10 (HIGH) — 4키 전부 `PARAM_RANGES`·`INT_PARAMS` 밖.

    `_validate_recommendations` 가 화이트리스트 밖 키를 버리므로 미편입이 곧 AI
    자동 튜닝 차단이다. 임계 70 을 최근 손실로 최적화하면 n≤20 에 과적합한다
    (cycle223 선례). `llm_gate_daily_call_cap` 은 **비용 다이얼**이기도 하다.
    """
    from src.engine.recommendation_engine import INT_PARAMS, PARAM_RANGES

    assert key not in PARAM_RANGES
    assert key not in INT_PARAMS


@pytest.mark.parametrize("key", _KEYS)
def test_c10_2_recommendation_engine_source_has_no_key_literal(key: str) -> None:
    """C10 — 런타임 dict 만 보면 조건부 편입(`if ...: PARAM_RANGES[K] = ...`)을 놓친다."""
    text = _read(_RECO)
    hits = [i for i, line in enumerate(text.splitlines(), 1) if key in line]
    assert not hits, f"`recommendation_engine.py` 에 `{key}` 리터럴(lines {hits})"


#: cycle297(2026-09-17) — 5전략 LLM 매수평가 shadow 확대(사용자 결정 "결정 2 진행")로
#: 소유 축이 {VB, LTV} → **7전략 전부**로 뒤집혔다. 이 가드는 삭제·skip 되지 않고
#: 기대값만 반전된다(cycle297 명세 §5.2 — cycle297 자체 가드 `test_g2_1b` 가 이 함수의
#: 존재와 무회피 마커를 별도로 잠근다).
_ALL_SEVEN_STRATEGY_RELS = frozenset(
    f"src/engine/strategies/{name}.py"
    for name in (
        "momentum", "volatility_breakout", "long_tail_volatility",
        "donchian_swing", "bull_flag_breakout", "vcp_breakout", "kojiro",
    )
)


@pytest.mark.parametrize("key", _KEYS)
def test_c10_3_key_lives_in_exactly_vb_and_ltv_default_params(key: str) -> None:
    """C10/§6.2 — 전략 glob 전수에서 이 키를 `DEFAULT_PARAMS` 에 가진 파일 = **7전략 전부**.

    🔁 cycle297(2026-09-17) 반전 — 원래 이 가드는 소유를 {VB, LTV} 로 잠갔다(§11 Q8).
    사용자 결정 "결정 2 진행" 으로 5전략이 추가됐고, 그 소유 축 가드는 지우지 않고
    **기대값만** 7전략으로 뒤집는다(cycle297 명세 §5.2 — 함수명은 유지, 삭제·skip 금지).
    """
    owners: dict[str, object] = {}
    for path in _STRATEGY_DIR.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Assign):
                continue
            if not any(isinstance(t, ast.Name) and t.id == "DEFAULT_PARAMS"
                       for t in node.targets):
                continue
            if not isinstance(node.value, ast.Dict):
                continue
            for k, v in zip(node.value.keys, node.value.values):
                if isinstance(k, ast.Constant) and k.value == key:
                    owners[path.relative_to(_ROOT).as_posix()] = getattr(v, "value", v)
    assert set(owners) == _ALL_SEVEN_STRATEGY_RELS, (
        f"`{key}` 소유 전략이 7전략 전부가 아니다 — 실측 {sorted(owners)}"
    )


def test_c10_4_config_declares_buy_gate_model() -> None:
    """C10 자매/§6.3 — `src/config.py` 에 `openai_buy_gate_model` 1키(기본 `gpt-5.6-luna`).

    20:00 자문 모델(`openai_recommend_model`)과 **분리**한다 — 한쪽을 더 싼 모델로
    옮기고 싶을 때 다른 쪽이 딸려가면 안 된다. `openai_api_key` 는 재사용.
    """
    from src.config import settings

    assert getattr(settings, "openai_buy_gate_model", None) == "gpt-5.6-luna"
    assert hasattr(settings, "openai_recommend_model")
    assert settings.openai_recommend_model == "gpt-5.6-luna"


def test_c10_5_no_new_killswitch_boolean_param() -> None:
    """C10/§6.2 — 킬스위치는 `llm_gate_mode` 하나다(`*_enabled` 불리언 신설 금지).

    끄는 수단이 둘이면 "무엇이 이겼는지" 를 로그로 판정할 수 없다(cycle264 계약).
    """
    for path in (_VB, _LTV):
        src = _read(path)
        assert "llm_gate_enabled" not in src
        assert "llm_buy_gate_enabled" not in src


# ===========================================================================
# C17 — leaf read-only (AST): scanner/params 전역에 대입하지 않는다
# ===========================================================================
_READONLY_NAMES = (
    "ticker_prices", "ticker_names", "ticker_market_info", "ticker_prev_close",
    "_targets", "params",
)


def test_c17_3_leaf_never_assigns_to_readonly_state() -> None:
    """C17 (HIGH) — leaf 는 읽기 전용 상태에 **대입하지 않는다**.

    `scanner.ticker_prices[...] = ...` · `.update(...)` · `.pop(...)` 전부 금지.
    8영역을 파일로 건드리지 않아도 그 **상태**를 바꾸면 같은 사고다(cycle242 G-242-8 동형).
    """
    tree, _src = _tree(_LEAF_GATE)
    bad: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.Assign, ast.AugAssign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for t in targets:
                if isinstance(t, ast.Subscript):
                    base = t.value
                    name = getattr(base, "attr", getattr(base, "id", ""))
                    if name in _READONLY_NAMES:
                        bad.append(f"line {node.lineno}: {name}[...] 대입")
                if isinstance(t, ast.Attribute) and t.attr in _READONLY_NAMES:
                    bad.append(f"line {node.lineno}: .{t.attr} 대입")
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            base = node.func.value
            name = getattr(base, "attr", getattr(base, "id", ""))
            if name in _READONLY_NAMES and node.func.attr in {
                "update", "pop", "clear", "setdefault", "popitem", "__setitem__",
            }:
                bad.append(f"line {node.lineno}: {name}.{node.func.attr}()")
    assert not bad, f"leaf 가 읽기 전용 상태를 변경한다: {bad}"


def test_c17_4_leaf_does_not_import_eight_area_modules() -> None:
    """C17 — leaf 가 `risk`/`order_engine`/`strategy_registry`/`session`/`realtime`/`auth`
    를 import 하지 않는다(8영역 무접촉의 두 번째 증거)."""
    src = _read(_LEAF_GATE)
    banned = (
        "src.engine.risk", "src.engine.order_engine", "src.engine.strategy_registry",
        "src.engine.session", "src.realtime", "src.auth", "src.api.order",
    )
    hits = [b for b in banned if b in src]
    assert not hits, f"leaf 가 8영역 모듈을 참조한다: {hits}"


# ===========================================================================
# C15 — 8영역 + scheduler + strategy_base + 나머지 전략 5파일 내용 sha 불변 (HIGH)
#
# ⚠️ 사이클 한정. 값은 브랜치 base `4ca3463` 의 blob sha256 (`git show 4ca3463:<path>`).
# 재핀(2026-09-11 03:1x, main 병합 시): order_engine.py·risk.py·scheduler.py 3건은 cycle273 그룹 1
# (커밋 39db6c0·2c1f190·a60f43e·dad24bc, 병합 133d6bc)이 바꾼 것이지 cycle274 가 아니다 —
# `git diff 4ca3463 aa31761 -- <path>` 를 눈으로 확인한 뒤 병합 결과(=aa31761 의 내용)로 재핀했다.
# ===========================================================================
# 🔁 2026-09-11 (cycle283) 재핀 — 저녁 창 재설계가 `scanner.py`(8영역, 사용자 승인)와
#    `scheduler.py`(라인 상한 승인 대상)를 바꿨다. 이 사이클의 변경이 아니라 **다른
#    사이클의 승인된 변경**이므로 값만 현재 워킹트리로 재산출한다(cycle274→cycle276
#    승계 때와 같은 절차). 나머지 핀은 불변이다.
# 🔁 2026-09-12 (cycle286, C4-a) 재핀 — `nxt_tradable=False` 사후 보강 판정축 교체가
#    또 다른 사이클(cycle286)의 사용자 명시 8영역 승인 하에 `order_engine.py` 를
#    바꿨다. 값만 현재 워킹트리로 재산출한다(같은 승계 절차).
_BASE_SHA = {
    "src/engine/risk.py": "79fddbec8cf9315c5172fc6634c4f4ea77f525d9ff9a3aba48f321affeb4d3e8",
    # 🔁 2026-09-25 (cycle358) 재핀 — 카드 D(관측 전용). PARTIAL/CANCELLED UPDATE
    # `affected==0` 무흔적에 `[trade_status_update_miss]` WARNING 추가(사용자 승인,
    # 워크리스트 ⑨). 매매·상태전이 로직 무변경, A-ATOMIC 구간은 byte 동일.
    "src/engine/order_engine.py": "118ebf38fd9004bf37cebf065199b949d9093d98ab9792b710b06345b5a119e3",
    "src/engine/session.py":
        "36257d86af1c26a868dc991a74a9eb139c98a9358d739d24600f5be2f9c5666c",
    # 🔁 cycle302(2026-09-18) 재핀 — 사용자 승인 일봉 backfill **대상** 확대
    #    (분기에서 지수 소속 판정 제거 · `vcp_universe_tickers` 집합 소멸.
    #    목표 깊이 상수는 불변). 값만 옮긴다 — 단언은 그대로다.
    #    구 값은 cycle299 기준선(3b7366cc…)이다.
    # 🔁 2026-09-25 (cycle363 F-1) 재핀 — `_scan_pool_eager_refresh_loop` upsert 전 기존 raw 머지(사이클 176 basics 경로 답습, 사용자 승인 8영역). 장전 0값 키(acml_tr_pbmn 등)가 raw 통째 교체로 지워지던 결함 시정. 나머지 7영역 diff 0.
    "src/engine/scanner.py":
        "2c104fba38dd1e942b091bfac14cb7d152d766676405e9fd66fe27e75cb3f5a6",
    "src/engine/strategy_registry.py":
        "d794696e54ffdc36efa6df917879d780e86bc1f373bb3b5d8dcbc0beac8cef8b",
    "src/api/order.py":
        "08c5cafd7b8678ec0d0fa85f856fdea3cce38ad92488c6d74c03cd13faa415bb",
    # ⚠️ cycle292(2026-09-14) 재핀 — `_subscribe_market_operation_tickers` 176줄을
    # 신규 leaf `src/engine/market_op_subscribe.py` 로 추출(행위 변경 0 · 5줄 위임
    # wrapper · 3,897→3,726L, 사용자 승인). 여섯 자매 핀(cycle274/276/278/282/290/291)
    # 을 **한 값으로 동시에** 옮겼다 — 한 곳만 넣으면 나머지가 "코드를 되돌려라" 로
    # 붉어져 승인된 변경을 되돌리도록 오도한다. 직전 값 =
    # `50658e06062a0d38afecab1baa08871b89212e295cc95f2a3af62a2ae076115d`.
    # 🔁 cycle364(2026-09-26) 재핀 — 저녁 A1 미리보기(`prepare(as_of=)`) 도입, 저녁 캡처
    # 본체를 leaf `funnel_capture.py` 로 이관(순감 약 35줄, 사용자 승인 D3).
    # 🔁 cycle369 재핀 — 관리종목51·단기과열59 청산·매수차단 leaf 배선(값만 이동)
    "src/engine/scheduler.py": "acaddd23f935fdd288cca8c3dfd1bbcd62b134a9b80cdd922a1f73acfd1deb8a",
    # 🔁 cycle369 R2 재핀 — buy-block 게이트(`_status_buy_blocked` 승격) + STATUS_EXIT Signal + Q7 edge-baseline clear 배선(전략 7파일은 무변경, 배선은 이 파일)
    "src/engine/strategy_base.py":
        "e9b379dcae6e4db664b2f159442b11bac3bf00be6e4481680332da494b61bf8e",
    # 🔁 cycle296(2026-09-17) 재핀 — 사용자 승인 `issue()` 매니저 단위 in-flight 합류(`src/auth/**`). 같은 값을 10곳 동시 갱신했다.
    "src/auth/token.py":
        "4125c271b4147e59922f4f000e523429fb4bbef37058dc754fd92b9475ec58f1",
    "src/auth/hashkey.py":
        "7c2aacc703839bdc274b463ee48777006504d70e4d59a1e57120ac5b612396d2",
    # 🔁 cycle368(2026-09-25) 재핀 — 장운영정보 칸 밀림 수정 세트. USER DECISION: 칸
    #    기준점 판별(`parse_market_op_payload` 단일 판별자)을 handler 에도 적용해
    #    handler 가 더 이상 `payload.split` 을 직접 하지 않고 파싱된
    #    `event.mkop_cls_code` 를 쓴다. MAIN-SESSION DECISION(적대적 검토 뒤, 사용자
    #    승인 범위 안): 두 import(`parse_market_op_payload`·`record_market_op_event`)를
    #    각자의 try 안에 둔다 — HEAD 도 이미 import 를 (하나의) try 안에 두어 보드
    #    콜백은 원래도 안전했고, 이번 변경은 그 try 를 파싱/기록 둘로 나눠 한쪽이
    #    깨져도 다른 쪽 결과가 살아남게 한 것이지 없던 보호를 처음 넣은 게 아니다.
    #    docstring 을 현재 계약만 서술하도록 다시 썼다(세션 행위 영향은 AB1 조건부
    #    라는 서술 포함). 그 밖 로직 무변경. 직전 값 =
    #    `37b1755210c83cdb2a462e6a37f919b326f8b48bee73d924adcc277d770a8d17`.
    "src/realtime/handler.py":
        "cc8af0de831e98d79f558d0c56f1360ce5ee5438ec59f23dbe79ca6725d472bc",
    "src/realtime/websocket.py":
        "d4c443bde2ed7aeafba3e9471db0ca4efc15a654610555435145a9b305150c5b",
    "src/realtime/websocket_pool.py":
        "8b02442bcf5f558d6f7095b47d2016f004e3746e07ddc91dae8768b1dd46a10d",
    # 🔁 cycle290(킬스위치 등재, 2026-09-13) 재핀 — `DEFAULT_PARAMS` 말미에 키 2개
    #    추가뿐, 그 외는 불변(세그먼트 sha 는 `test_cycle290_ast_scope.py` 가 잠근다).
    # 🔁 cycle364(2026-09-26) 재핀 — `prepare(as_of=)` 시그니처 확장(+ donchian·kojiro
    #    PV-1, vcp P3).
    # 🔁 cycle364 round 2 — PV-1 BFB·VCP 확대 + keep/skip 분리(R1).
    "src/engine/strategies/momentum.py":
        "38743ab1ecdb4aa9bcd6ac37e5d28f75501d2d4eceb2e70f3aace44d00d502a1",
    "src/engine/strategies/donchian_swing.py":
        "31bd41bb0e435a0185649dee3aa309622d2044d9978cf3d9ddb687a778327ea7",
    "src/engine/strategies/kojiro.py":
        "66758fb3fce62d509d6d6750cb8ff903df09f1671e8b2d11c139e1cde9da6038",
    "src/engine/strategies/vcp_breakout.py":
        "a609ded41a916563c6706aac16fe1867845687233c195b7dab478d336cc94b37",
    "src/engine/strategies/bull_flag_breakout.py":
        "f44c3757db0c9bced8754f34723cc94e7956057b4405903900d519fb4e5b28d8",
}


@pytest.mark.parametrize("rel", sorted(_BASE_SHA))
def test_c15_1_untouchable_files_are_byte_identical(rel: str) -> None:
    """C15 (HIGH) — 8영역·`scheduler.py`·`strategy_base.py`·나머지 전략 5파일 **byte 동일**.

    이 사이클의 제1 계약은 "매매 행위를 한 글자도 바꾸지 않는다" 다.
    ⚠️ **핀을 먼저 재산출하지 마라** — 그 순간 실제 변경이 새 스냅샷으로 봉인된다.
      1) `git diff 4ca3463 -- <path>` 를 눈으로 읽어라.
      2) cycle274 범위 밖 변경이면 되돌려라.
      3) 이 사이클은 이 파일들을 **바꾸지 않는다** — 재산출할 일이 없다.
    """
    assert _content_sha(rel) == _BASE_SHA[rel], (
        f"{rel} 이 base(4ca3463) 와 다르다 — 8영역 무접촉 위반"
    )


def test_c15_2_realtime_and_auth_have_no_new_python_files() -> None:
    """C15 — `src/realtime/**`·`src/auth/**` 에 신규 `.py` 가 생기지 않았다."""
    seen = {
        p.relative_to(_ROOT).as_posix()
        for d in ("realtime", "auth") for p in (_SRC / d).rglob("*.py")
        if p.name != "__init__.py"
    }
    assert seen <= set(_BASE_SHA), f"8영역 디렉터리에 신규 파일: {sorted(seen - set(_BASE_SHA))}"


# ===========================================================================
# C16 — `scheduler.py` 정확 라인 핀 (cycle274 무접촉 → cycle292 추출 후 재핀)
# ===========================================================================
def test_c16_1_scheduler_line_count_unchanged() -> None:
    """C16 — `scheduler.py` 정확 라인 핀 = cycle274 무접촉의 대리 지표.

    cycle292(2026-09-14)가 `_subscribe_market_operation_tickers` 176줄을 신규 leaf
    `src/engine/market_op_subscribe.py` 로 추출(행위 변경 0 · 5줄 위임 wrapper)해
    3,897 → 3,726 으로 줄었다. 🔴 정확 핀을 상한 핀(`< 3900`)으로 완화하지 않는다 —
    그러면 확보한 174줄 예산의 무단 증식을 아무도 못 잡는다.
    """
    lines = len(_read(_SCHEDULER).splitlines())
    assert lines == 3781, f"scheduler.py {lines}L (기대 3,785 — cycle283 저녁 창 재설계 뒤 3,897 → cycle292 leaf 추출 → cycle298 재핀 3,795 → cycle354 order_no 매핑 폴백 추가 재핀 3,812 → cycle364 저녁 캡처 leaf 이관 재핀 3,777 → cycle369 재핀 — 관리종목51·단기과열59 청산·매수차단 task 배선 +4)"


def test_c16_2_scheduler_line_cap_is_not_looser_than_cycle257() -> None:
    """C16 — 자체 상한이 cycle257 의 **영구** 상한(3,900)보다 느슨하지 않다.

    cycle264 가 자기 상한을 4,000 으로 느슨하게 두는 바람에 cycle257 영구 가드
    위반을 초록으로 덮을 뻔했다(적대 검증 HIGH). 두 수가 갈라지면 항상 **더 조인
    쪽**이 정본이다.
    """
    mine = {int(c) for c in re.findall(
        r"assert lines [<=]=? (\d+)", Path(__file__).read_text(encoding="utf-8"),
    )}
    theirs = {int(c) for c in re.findall(
        r"assert count < (\d+)",
        (_ROOT / "tests" / "unit" / "ast"
         / "test_cycle257_ast_dead_code_removed.py").read_text(encoding="utf-8"),
    )}
    assert mine and theirs
    assert min(mine) <= min(theirs), f"cycle274 상한({sorted(mine)}) > cycle257({sorted(theirs)})"


# ===========================================================================
# C18 — sha 핀 재핀: `check_buy_signal` 2핀 갱신 · 나머지 4핀 불변 (HIGH)
# ===========================================================================
_PINS_FILE = _ROOT / "tests" / "unit" / "ast" / "test_cycle264_scope_and_pins.py"

# base(4ca3463) 시점의 `ast.get_source_segment` sha256 — cycle264 `_STRATEGY_PINS` 원문.
_BASE_METHOD_SHA = {
    ("vb", "check_buy_signal"):
        "e620ae0d14a71f916550ee13f57edff12e1b84c12b8a4712b29583b44b56f20a",
    ("vb", "check_exit_signal"):
        "86593b038e4cf8121ae47069fb368346edc50d9692b29db4cbdcc8897421b72e",
    ("vb", "calc_buy_quantity"):
        "6d24ef3f3afd211ae6123623075b08320cdc08c9cd48a6db965355305ad4e732",
    ("ltv", "check_buy_signal"):
        "fb1e7460e5d6906aacd9dd6cbc1037fb7327759c24ca4df055773ba1f22cac2a",
    ("ltv", "check_exit_signal"):
        "c8b0e6a8c8705d49bb6f12f82f505d426a5bdeb81413f8b2e0276eabb7dd9cad",
    ("ltv", "calc_buy_quantity"):
        "1149ecc8ea37fb1ba164cc1fd88e6525111d5142168ca879f1026c7890905b81",
}

_FROZEN = [k for k in _BASE_METHOD_SHA if k[1] != "check_buy_signal"]


def _current_method_sha(kind: str, method: str) -> str:
    path, cls_name = _STRATEGY_META[kind]
    return hashlib.sha256(_method_segment(path, cls_name, method).encode("utf-8")).hexdigest()


@pytest.mark.parametrize("key", sorted(_FROZEN))
def test_c18_1_exit_and_qty_methods_are_frozen(key) -> None:
    """C18 (HIGH) — `check_exit_signal`·`calc_buy_quantity` **4핀 불변**.

    그 4핀 불변이 "청산·수량 규약 무접촉" 의 기계적 증거다. LLM 게이트는 진입
    관측이지 청산·사이징에 손대는 사이클이 아니다.
    """
    kind, method = key
    assert _current_method_sha(kind, method) == _BASE_METHOD_SHA[key], (
        f"{kind}.{method} 이 바뀌었다 — cycle274 범위 밖(청산·수량 무접촉 위반)"
    )


# 🔁 cycle276 — `test_c18_2_check_buy_signal_must_change` 는 **삭제**했다. cycle274 가
#    "이 메서드는 반드시 바뀐다" 고 요구했지만 cycle276 이 훅을 order_engine 으로 옮기며
#    두 메서드를 cycle272 값으로 **되돌렸다**. 그 복귀는 이제
#    `test_cycle276_ast_order_hook.py::test_c6_1_strategy_methods_return_to_cycle272_sha`
#    가 6/6 으로 잰다(고아 가드 방지 — cycle240 A11b · cycle252 G-252-5b).


@pytest.mark.parametrize("kind", _KINDS)
def test_c18_3_cycle264_pins_are_repinned_to_current(kind: str) -> None:
    """C18 (HIGH) — cycle264 `_STRATEGY_PINS` 의 `check_buy_signal` 2핀이 **현재값으로 갱신**.

    핀을 갱신하지 않으면 cycle264 가드가 붉어지고, 갱신을 잊은 채 그 가드를
    삭제하면 무접촉 증거가 통째로 사라진다. 갱신은 **승인 항목**이다(자문 §5.1).
    """
    text = _read(_PINS_FILE)
    module = "volatility_breakout" if kind == "vb" else "long_tail_volatility"
    m = re.search(
        rf'\(\s*"{module}"\s*,\s*"\w+"\s*,\s*"check_buy_signal"\s*\)\s*:\s*\n?\s*"([0-9a-f]{{64}})"',
        text,
    )
    assert m, f"`_STRATEGY_PINS` 에서 {module}.check_buy_signal 핀을 찾지 못했다"
    assert m.group(1) == _current_method_sha(kind, "check_buy_signal"), (
        f"{module}.check_buy_signal 핀이 현재 소스와 다르다 — 재핀 누락"
    )


@pytest.mark.parametrize("key", sorted(_FROZEN))
def test_c18_4_cycle264_frozen_pins_are_untouched(key) -> None:
    """C18 — cycle264 `_STRATEGY_PINS` 의 나머지 4핀 문자열이 **손대지 않았다**.

    "2 갱신 · 4 불변" 을 파일 텍스트 수준에서도 못박는다(재핀 김에 6개를 다
    재산출하는 사고 차단 — 09-05 카드 #3 계열).
    """
    kind, method = key
    module = "volatility_breakout" if kind == "vb" else "long_tail_volatility"
    text = _read(_PINS_FILE)
    m = re.search(
        rf'\(\s*"{module}"\s*,\s*"\w+"\s*,\s*"{method}"\s*\)\s*:\s*\n?\s*"([0-9a-f]{{64}})"',
        text,
    )
    assert m, f"`_STRATEGY_PINS` 에서 {module}.{method} 핀을 찾지 못했다"
    assert m.group(1) == _BASE_METHOD_SHA[key], f"{module}.{method} 핀이 변조됐다"


def test_c18_5_sibling_content_pin_covers_vb_and_ltv() -> None:
    """C18/`test_g3_9*` 4곳 규약 — 전략 파일 sha 를 고정한 **자매 핀**도 재핀 대상이다.

    `test_cycle223_ast_donchian_exit_fix.py::_CYCLE228_STRATEGY_CONTENT_SHA` 가 VB·LTV
    파일 내용 sha 를 들고 있다(cycle273 이 남긴 스냅샷). Green 이 두 파일을 바꾸면
    그 dict 도 현재값으로 갱신되어야 한다 — 아니면 그 가드가 붉어진다.
    """
    text = (_ROOT / "tests" / "unit" / "ast"
            / "test_cycle223_ast_donchian_exit_fix.py").read_text(encoding="utf-8")
    for rel in (_VB_REL, _LTV_REL):
        m = re.search(rf'"{re.escape(rel)}"\s*:\s*\n?\s*"([0-9a-f]{{64}})"', text)
        if m is None:
            continue          # dict 가 비워졌으면 재핀 의무 없음(그 편이 정상)
        assert m.group(1) == _content_sha(rel), (
            f"`_CYCLE228_STRATEGY_CONTENT_SHA[{rel}]` 가 현재 소스와 다르다 — 자매 핀 재핀 누락"
        )
