"""cycle292 (2026-09-14) AST 영구 가드 — VI 구독 leaf 추출의 **구조 계약**.

명세 = `_workspace/red/cycle292_scheduler_market_op_leaf_spec.md`

`scheduler._subscribe_market_operation_tickers`(176줄)를 신규 leaf
`src/engine/market_op_subscribe.py::subscribe_market_operation_tickers` 로 추출했다.
목적은 `scheduler.py` 라인 상한(cycle257 A4 = **3,900 미만**) 예산 확보이고
**행위 변경 0** 이다 — 본체는 라인 단위 동일(`self.` → `scheduler.` 6곳 + 4칸 dedent 뿐).

| # | 가드 | 지키는 것 |
|---|---|---|
| G-292-1 | leaf 의 **함수-로컬 import 5줄** — 6심볼이 함수 안에서만 import 된다 | monkeypatch seam(§2.5 단일 최대 위험) |
| G-292-2 | leaf logger 이름 `"src.engine.scheduler"` | `system_logs` 접두 = 운영 grep 사슬 |
| G-292-3 | scheduler wrapper 는 **위임만** 한다(본체 재인라인 금지) | 두 번째 사본 차단 |
| G-292-4 | `cap` 기본값 60 · KEYWORD_ONLY — wrapper **와** leaf 양쪽 | 요약 로그 `cap=%d` |
| G-292-5 | 마커 5종이 leaf **밖** `src/**` 에 0건 | D+1 판독 세대 합산 차단 |
| G-292-6 | `scheduler.py` 정확 라인 핀 + 영구 상한 | cycle292 자신의 후속 기준선 |
| G-292-7 | leaf 는 scheduler 를 import 하지 않는다 | `data_load_tasks` 배너 계약(순환 0) |
| G-292-8 | 요약 로그 **서식 + 인자 순서** 고정 | D+1 판독 계약(`main_tick`↔`main_total` 스왑 차단) |
| G-292-9 | 메인 세션 **별칭·수집 금지** + 구독 owner 출처 증명 | 이름 기반 봉인의 별칭 우회 차단 (구현은 `test_cycle221_ast_market_op_no_main.py` — 그 파일이 "메인 0건" 의 집이다) |

## 규약
`ast.dump` sha 핀 금지(3.12 CI ↔ 3.13 로컬 출력 차이로 CI 만 붉어진다) ·
`git grep`/`git ls-files` 금지(미추적 파일 실종) ·
**기준선 소실은 명시 FAIL**(vacuous PASS 차단 — 모든 테스트가 `_LEAF.exists()` 를 먼저 통과).
모듈 레벨 sha dict 이름은 `_BASE_SHA` 다 — `*_CONTENT_SHA` 로 지으면
`test_cycle223g3_ast_guard_sees_staged.py::test_g3_9a` 의 `_PIN_GUARD_FILES`(고정 4개)와
불일치해 즉시 붉어진다.

## 🔴 왜 부정 단언만으로는 부족한가

cycle221 의 봉인(`kis_ws.subscribe` 0건 · `bypass_limit=True` 0건 ·
`kis_ws_pool.subscribe/unsubscribe` 0건)은 전부 **"…가 없어야 한다"** 형태다. 본체가
scheduler 를 떠나면 `_get_function_node(tree, "_subscribe_market_operation_tickers")` 는
남은 **위임 wrapper 노드**를 찾아내고, 그 노드에 대한 부정 단언은 **전부 참**이 된다 —
08-19 실사고(메인 45/41 → OPSP0008 117건 → 보유 4종목 ~58분 tick blind) 재발 방지 가드가
조용히 공허해진다. 그래서 cycle292 는 (a) 그 가드들을 leaf 로 재조준하고 각각 양성
대조군을 심었으며(`test_cycle221_ast_market_op_no_main.py` ·
`test_cycle214_ast_h0unmko0_pool.py` · `test_market_op_subscribe_import_path_guard.py` ·
`test_market_op_subscribe_socket_guard.py`) (b) wrapper 쪽은 여기 G-292-3 이
**양성 단언**으로 잠근다. wrapper 에 부정 단언을 걸면 그 자체가 공허해진다.
"""

from __future__ import annotations

import ast
import hashlib
import inspect
from pathlib import Path

import pytest

import src as _src_pkg

pytestmark = pytest.mark.unit

_SRC = Path(_src_pkg.__file__).resolve().parent
_ROOT = _SRC.parent
_SCHEDULER = _SRC / "engine" / "scheduler.py"
_LEAF = _SRC / "engine" / "market_op_subscribe.py"

_LEAF_FN = "subscribe_market_operation_tickers"
_WRAPPER_FN = "_subscribe_market_operation_tickers"

#: 함수-로컬로만 import 되어야 하는 6심볼. 최상단으로 올리면 테스트 4파일의
#: `monkeypatch.setattr("src.realtime.websocket.kis_ws", …)` 류 patch 가 leaf 가 보는
#: 참조를 더는 바꾸지 못하고, 실제 `kis_ws` 를 만나 `_ws is None` → `return 0` 조기
#: 반환이 부정 단언 6케이스를 **조용히 초록**으로 통과시킨다(명세 §2.5).
_FUNCTION_LOCAL_SYMBOLS = frozenset({
    "ConnectionClosedError",
    "State",
    "MARKET_OP_TR_ID",
    "MAX_SUBSCRIPTIONS",
    "kis_ws",
    "kis_ws_pool",
})

#: 운영 로그 마커 5종 — leaf 안에만 존재해야 한다.
_MARKERS = (
    "[market_op_subscribe_skip]",
    "[market_op_no_quote_session]",
    "[market_op_subscribe]",
    "[market_op_subscribe_summary]",
    "[market_op_subscribe_no_slot]",
)

#: `_DbLogHandler.emit` 이 `[{record.name}]` 로 적재한다 — 이름이 갈리면 위 마커의
#: `system_logs` 접두가 통째로 바뀐다 = 판독 사슬 파괴 = 행위 변경(명세 §4).
_LOGGER_NAME = "src.engine.scheduler"

#: `scheduler.py` 정확 라인 수 + cycle257 이 세운 영구 상한.
_SCHEDULER_LINES = 3812  # cycle354 재핀 — order_no 매핑 폴백 추가 (`_sync_orders_to_db`)
_SCHEDULER_LINE_CAP = 3_900

#: cycle292 가 만진 **전부**인 프로덕션 3파일의 내용 sha. 붉어지면 핀을 갱신하기 전에
#: "행위 변경 0" 계약이 여전히 성립하는지(§3.1 금지 목록) 먼저 확인한다.
#: 셋째 파일은 **docstring 1곳**만 바뀌었다(코드/AST 불변) — 적대 검증이
#: `get_market_op_active_tickers()` docstring 의 소비처 서술 2개가 둘 다 거짓임을
#: 확인했다(프로덕션 호출자 0건 · 델타는 `scheduler._market_op_subs` 로 잰다).
_BASE_SHA = {
    "src/engine/scheduler.py":
        "3461242a47080379c8d48dc5efd5799ce5fac173803a95476547ea4758b40a81",
    "src/engine/market_op_subscribe.py":
        "7d58f9464c1ed35e4fa8706d801beb5a6b5c062d5a2941f0db6482d028d3d4ac",
    # 🔁 cycle368(2026-09-25) 재핀 — halt 판정을 `_is_code_active` → `is_iscd_stat_blocking`
    # (58 단독, USER DECISION)으로 좁히고, VI·거래정지 둘 다 마지막 활성 프레임 뒤 600초
    # 지연 해제를 받는다(VI 수명은 USER DECISION, 거래정지도 같은 수명을 받는 것과 만료
    # sweep 을 `record_market_op_event` 첫머리에 두는 것은 적대적 검토 뒤 MAIN-SESSION
    # DECISION, 사용자 승인 범위 안). 신규 `_now()` 시계 + `datetime`/`timezone` import +
    # 신규 dict 2(`_vi_last_active_at`·`_halt_last_active_at`, 서로 완전 독립) + 신규
    # 상수 2(`VI_ACTIVE_TTL_SECONDS`·`HALT_ACTIVE_TTL_SECONDS`) + `is_iscd_stat_blocking`
    # import. sweep 호출부 = `record_market_op_event` 첫머리 + 읽기 함수 5곳
    # (`is_ticker_stale_excluded`·`get_market_op_active_tickers`·`get_halt_active_tickers`·
    # `get_circuit_breaker_state`·`get_market_op_state_summary`, 기존 `get_vi_active_tickers`
    # 는 그대로 VI sweep 만 부른다). `seed_vi_active_from_rest` 도 시드 시각을 스탬프한다.
    # `iscd_stat_active_count` 는 표시 집합(`_ISCD_STAT_DISPLAY_CODES`)으로 센다. 방어적
    # 분기 — 활성 집합에 시각 없이 있는 종목은 무기한 유지하지 않고 발견 시각을 찍어
    # 그로부터 TTL 뒤 해제한다(`reset_market_op_state` 가 새 dict 2 개도 clear). 나머지
    # leaf 는 무접촉이다. 직전 값 =
    # `b9bd158b1503546a2d214b1269b2ae961f7c09241035149081e65eb61ac4c509`.
    "src/engine/market_operation_monitor.py":
        "49de2441198cf1dee2c34deed50ded6fb8a5536bec0f475a0feba8237c977961",
}


# ---------------------------------------------------------------------------
# 공통 — 기준선 소실은 명시 FAIL
# ---------------------------------------------------------------------------
def _require_baseline() -> None:
    assert _LEAF.exists(), (
        f"leaf 부재: {_LEAF} — cycle292 의 기준선이 사라졌다. 이 파일의 모든 단언이 "
        "공허해지므로 시끄럽게 실패시킨다"
    )
    assert _SCHEDULER.exists(), f"scheduler 부재: {_SCHEDULER}"


def _leaf_src() -> str:
    _require_baseline()
    return _LEAF.read_text(encoding="utf-8")


def _leaf_tree() -> ast.Module:
    return ast.parse(_leaf_src())


def _function_node(tree: ast.AST, name: str) -> ast.AST:
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    raise AssertionError(f"함수 {name} 미발견 — 기준선 소실(공허 초록 차단)")


def _imported_names(node: ast.AST) -> set[str]:
    """`node` 하위의 `Import`/`ImportFrom` 이 바인딩하는 이름 집합."""
    out: set[str] = set()
    for n in ast.walk(node):
        if isinstance(n, (ast.Import, ast.ImportFrom)):
            for alias in n.names:
                out.add(alias.asname or alias.name.split(".")[0])
    return out


def _module_level_import_nodes(tree: ast.Module) -> list[ast.stmt]:
    return [n for n in tree.body if isinstance(n, (ast.Import, ast.ImportFrom))]


# ===========================================================================
# G-292-1 — 함수-로컬 import 5줄 (§2.5 단일 최대 위험)
# ===========================================================================
def test_g292_1_six_symbols_are_imported_inside_the_function_only() -> None:
    """G-292-1 — 6심볼이 leaf **함수 안**에서 import 되고 모듈 최상단에는 없다.

    `test_market_op_subscribe_import_path_guard.py` 는 import **경로**만 보므로
    최상단 승격을 못 막는다. 승격되면 테스트 4파일의 원천 모듈 monkeypatch 가
    무력화되고 조기 반환이 부정 단언 6케이스를 조용히 초록으로 만든다.
    """
    tree = _leaf_tree()
    fn = _function_node(tree, _LEAF_FN)

    inside = _imported_names(fn)
    missing = sorted(_FUNCTION_LOCAL_SYMBOLS - inside)
    assert not missing, (
        f"함수-로컬 import 에서 사라진 심볼: {missing} — "
        "monkeypatch seam 이 끊기면 실제 kis_ws 를 만나 return 0 조기 반환한다"
    )

    top = set()
    for node in _module_level_import_nodes(tree):
        for alias in node.names:
            top.add(alias.asname or alias.name.split(".")[0])
    leaked = sorted(_FUNCTION_LOCAL_SYMBOLS & top)
    assert not leaked, (
        f"모듈 최상단으로 승격된 심볼: {leaked} — import 시점 바인딩이라 "
        "`monkeypatch.setattr('src.realtime.websocket.kis_ws', …)` 가 더는 걸리지 않는다. "
        "함수 안으로 되돌려라(명세 §2.5 · 금기 5)"
    )


def test_g292_1b_two_realtime_imports_stay_split() -> None:
    """G-292-1b — `kis_ws`←websocket / `kis_ws_pool`←websocket_pool **두 줄 분리** 유지.

    2026-07-24 에 이 한 줄이 합쳐져 있어서 cycle214 가 배포 이래 완전 미작동이었다
    (매 호출 ImportError, 하루 117건 = 일일 ERROR 94%). `kis_ws_pool` 은
    `websocket_pool.py` 에만 있고 `websocket.py` 에 재노출 0건이다.
    """
    fn = _function_node(_leaf_tree(), _LEAF_FN)
    frm: dict[str, set[str]] = {}
    for n in ast.walk(fn):
        if isinstance(n, ast.ImportFrom) and n.module:
            frm.setdefault(n.module, set()).update(a.name for a in n.names)

    ws = {m: names for m, names in frm.items() if m.endswith("realtime.websocket")}
    pool = {m: names for m, names in frm.items() if m.endswith("realtime.websocket_pool")}
    assert ws, "`from src.realtime.websocket import …` 가 사라졌다"
    assert pool, "`from src.realtime.websocket_pool import …` 가 사라졌다"
    assert all("kis_ws_pool" not in names for names in ws.values()), (
        "`kis_ws_pool` 을 `src.realtime.websocket` 에서 import 하면 매 호출 ImportError "
        "(2026-07-24 사고 — cycle214 전면 미작동)"
    )
    assert any("kis_ws_pool" in names for names in pool.values()), (
        "`kis_ws_pool` 은 `src.realtime.websocket_pool` 에서 import 해야 한다"
    )


# ===========================================================================
# G-292-2 — logger 정체성 (§4)
# ===========================================================================
def test_g292_2_leaf_logger_identity_is_scheduler() -> None:
    """G-292-2 — leaf logger 이름은 `"src.engine.scheduler"` 다.

    `src/main.py::_DbLogHandler.emit` 이 `f"[{record.name}] …"` 로 `system_logs` 에
    적재하므로, 이름이 갈리면 마커 5종의 접두가 `[src.engine.market_op_subscribe]` 로
    바뀌어 운영 grep·판독 문서 인용이 파괴된다 = 행위 변경 0 위반.
    판별 기준(명세 §4.2) = **옮겨 온 기존 마커**는 이름 고정, 새로 만드는 마커는
    `__name__`. cycle292 의 마커 5종은 cycle149/214/221 부터 쌓여 있던 기존 마커다.
    자매 = `test_cycle273b_selling_hold_observe.py::test_f7_logger_identity_is_scheduler`.
    """
    from src.engine import market_op_subscribe as leaf_mod

    assert leaf_mod.logger.name == _LOGGER_NAME, (
        f"leaf logger 이름 {leaf_mod.logger.name!r} != {_LOGGER_NAME!r} — "
        "system_logs 접두가 갈린다(사이클 60 I1 영속)"
    )
    src = _leaf_src()
    assert f'getLogger("{_LOGGER_NAME}")' in src, (
        "명시 바인딩 리터럴이 소스에 있어야 한다(런타임 재바인딩으로 우회 금지)"
    )
    assert "getLogger(__name__)" not in src, (
        "`__name__` 바인딩 금지 — 루트 로거가 WARNING(30) 이라 caplog 스코프 6곳의 "
        "INFO 단언이 캡처 자체를 못 한다(명세 §4.1-2)"
    )


# ===========================================================================
# G-292-3 — 위임 실재 + 본체 재인라인 금지
# ===========================================================================
def test_g292_3_scheduler_wrapper_delegates_and_holds_no_body() -> None:
    """G-292-3 — scheduler wrapper 는 leaf 를 **정확히 1회** 부르고 본체를 안 갖는다.

    이 가드가 없으면 누군가 leaf 를 남긴 채 scheduler 에 **두 번째 사본**을 인라인해도
    아무도 못 잡는다(leaf 쪽 가드는 초록, scheduler 쪽은 보는 사람이 없다).
    🔴 `State`/`state` 문자열 0건은 D4 거짓 초록 차단이다 — wrapper docstring 에
    "소켓 state 가드는 leaf 로 위임" 같은 문장을 넣으면
    `test_market_op_subscribe_socket_guard.py` 의 `inspect.getsource` 부분문자열 검사가
    **실제 가드를 전혀 검증하지 않고** 통과한다.
    """
    _require_baseline()
    sched_src = _SCHEDULER.read_text(encoding="utf-8")
    fn = _function_node(ast.parse(sched_src), _WRAPPER_FN)

    delegations = [
        n for n in ast.walk(fn)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Attribute)
        and n.func.attr == _LEAF_FN
    ]
    assert len(delegations) == 1, (
        f"leaf 위임 호출이 {len(delegations)}건 (정확히 1건이어야 한다) — "
        "위임이 사라졌거나 두 번 부른다"
    )
    owner = delegations[0].func.value
    assert isinstance(owner, ast.Name) and owner.id == "market_op_subscribe", (
        "위임 owner 는 모듈 `market_op_subscribe` 여야 한다"
    )

    # 본체가 다시 인라인되면 이 식별자들이 wrapper 안에 나타난다.
    names = {n.id for n in ast.walk(fn) if isinstance(n, ast.Name)}
    attrs = {n.attr for n in ast.walk(fn) if isinstance(n, ast.Attribute)}
    forbidden = (names | attrs) & {
        "kis_ws", "kis_ws_pool", "MARKET_OP_TR_ID", "MAX_SUBSCRIPTIONS",
        "State", "ConnectionClosedError",
    }
    assert not forbidden, (
        f"wrapper 안에 본체 심볼 재등장: {sorted(forbidden)} — 두 번째 사본 금지"
    )
    assert not [
        n for n in ast.walk(fn)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
        and n.func.attr in {"subscribe", "unsubscribe"}
    ], "wrapper 는 구독 SEND 를 하지 않는다(본체는 leaf)"

    wrapper_src = ast.get_source_segment(sched_src, fn) or ""
    assert wrapper_src, "wrapper 소스 세그먼트 추출 실패"
    for token in ("State", "state"):
        assert token not in wrapper_src, (
            f"wrapper 소스에 {token!r} 가 있다 — `inspect.getsource` 부분문자열 검사를 "
            "docstring 한 단어로 통과시키는 거짓 초록 경로다(명세 §5.1-b · D4)"
        )
    for marker in _MARKERS:
        assert marker not in wrapper_src, f"wrapper 에 마커 {marker} 재등장 금지"


# ===========================================================================
# G-292-4 — `cap` 시그니처 양쪽
# ===========================================================================
@pytest.mark.parametrize("which", ["wrapper", "leaf"])
def test_g292_4_cap_default_is_60_keyword_only(which: str) -> None:
    """G-292-4 — `cap` 기본값 60 · KEYWORD_ONLY 가 wrapper **와** leaf 양쪽에 있다.

    `cap` 은 vestigial 이지만 (a) `test_cycle214_h0unmko0_pool.py::
    test_G_214_4_cap_default_is_60` 이 wrapper 시그니처를 단언하고 (b) 요약 로그의
    `cap=%d` 인자로 실제 쓰인다. wrapper 만 핀하면 leaf 에서 조용히 사라질 수 있다.
    """
    _require_baseline()
    if which == "wrapper":
        from src.engine.scheduler import TradingScheduler

        target = TradingScheduler._subscribe_market_operation_tickers
    else:
        from src.engine import market_op_subscribe as leaf_mod

        target = leaf_mod.subscribe_market_operation_tickers

    params = inspect.signature(target).parameters
    assert "cap" in params, f"{which}: `cap` 파라미터 제거 금지(cycle214 시그니처 가드)"
    assert params["cap"].default == 60, f"{which}: cap 기본값 {params['cap'].default} != 60"
    assert params["cap"].kind is inspect.Parameter.KEYWORD_ONLY, (
        f"{which}: `cap` 은 keyword-only 여야 한다(`*` 뒤)"
    )
    assert "candidate_tickers" in params, f"{which}: `candidate_tickers` 파라미터 필수"


# ===========================================================================
# G-292-5 — 마커 5종의 거처
# ===========================================================================
def test_g292_5_markers_live_only_in_the_leaf() -> None:
    """G-292-5 — 마커 5종이 leaf 에 존재하고 `src/**` 중 leaf 밖 0건.

    마커가 두 곳에서 나오면 D+1 판독이 두 세대를 합산한다.
    선례 = `test_cycle274_ast_llm_gate.py::test_g1_4_markers_live_only_in_the_leaf`.
    """
    leaf_src = _leaf_src()
    for marker in _MARKERS:
        assert marker in leaf_src, f"leaf 에 마커 {marker} 부재 — 관측 소실"

    offenders: list[str] = []
    for py in sorted(_SRC.rglob("*.py")):
        if py.resolve() == _LEAF.resolve():
            continue
        text = py.read_text(encoding="utf-8")
        for marker in _MARKERS:
            if marker in text:
                offenders.append(f"{py.relative_to(_ROOT).as_posix()}:{marker}")
    assert offenders == [], (
        "마커는 leaf 한 곳에만 산다 — 두 세대 합산 차단. 위반: " + ", ".join(offenders)
    )


def test_g292_5b_leaf_writes_no_db_and_adds_no_io() -> None:
    """G-292-5b — leaf 는 `write_log`/DB/HTTP 를 쓰지 않는다(이동만 했다).

    원 함수는 `write_log` 0건이었다. 추출을 기회로 관측을 DB 로 늘리면 5분 사이클마다
    쓰기가 붙는다 = 행위 변경(명세 금기 8).
    """
    tree = _leaf_tree()
    called = {
        n.func.attr if isinstance(n.func, ast.Attribute) else getattr(n.func, "id", "")
        for n in ast.walk(tree) if isinstance(n, ast.Call)
    }
    assert "write_log" not in called, "leaf 에 `write_log` 금지 — 원 함수는 DB 에 쓰지 않았다"
    modules = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.ImportFrom) and n.module:
            modules.add(n.module)
        elif isinstance(n, ast.Import):
            modules.update(a.name for a in n.names)
    forbidden = {m for m in modules if m.startswith(("src.db", "httpx", "aiohttp", "requests"))}
    assert not forbidden, f"leaf 에 DB/HTTP import 금지: {sorted(forbidden)}"


# ===========================================================================
# G-292-6 — 라인 상한 + 정확 핀 + 내용 sha
# ===========================================================================
def test_g292_6_scheduler_line_count_is_pinned_under_the_permanent_cap() -> None:
    """G-292-6 — `scheduler.py` 정확 라인 핀 + cycle257 영구 상한(3,900 미만).

    cycle292 가 확보한 예산은 **174줄**이다(3,726 → 3,900). 🔴 정확 핀을 상한 핀으로
    바꾸지 않는다 — 그러면 그 174줄의 무단 증식을 아무도 못 잡는다. 예산을 확보하자고
    예산 감시자를 끄는 일이다.
    """
    _require_baseline()
    lines = len(_SCHEDULER.read_text(encoding="utf-8").splitlines())
    assert lines < _SCHEDULER_LINE_CAP, (
        f"scheduler.py {lines}L ≥ 영구 상한 {_SCHEDULER_LINE_CAP} (cycle257 A4)"
    )
    assert lines == _SCHEDULER_LINES, (
        f"scheduler.py {lines}L (cycle292 기준선 {_SCHEDULER_LINES}) — 정당한 변경이면 "
        "이 값과 자매 라인 핀 6곳(cycle274/276/286/287/290/291)을 함께 옮긴다"
    )


@pytest.mark.parametrize("rel", sorted(_BASE_SHA))
def test_g292_6b_touched_files_content_sha(rel: str) -> None:
    """G-292-6b — cycle292 가 만진 2파일의 내용 sha.

    붉어지면 먼저 "행위 변경 0"(§3.1 금지 목록 — 로그 문구·레벨·필드 순서·`%` 인자
    순서·호출 순서·예외 분기·`pop`↔`unsubscribe` 순서·커서 전진 조건·`sleep` 자리)이
    여전히 성립하는지 확인하고, 그다음에 값을 옮긴다.
    """
    _require_baseline()
    got = hashlib.sha256((_ROOT / rel).read_bytes()).hexdigest()
    assert got == _BASE_SHA[rel], f"{rel} 가 바뀌었다. 현재 sha={got}"


# ===========================================================================
# G-292-7 — leaf 는 scheduler 를 import 하지 않는다
# ===========================================================================
def test_g292_7_leaf_does_not_import_scheduler() -> None:
    """G-292-7 — leaf 가 scheduler 를 import 하지 않는다(순환 0).

    정본 = `data_load_tasks.py` 배너("이 모듈은 scheduler 를 import 하지 않는다").
    scheduler 인스턴스는 **첫 인자로만** 받는다. cycle61 이 stale 계열에 넣은
    `sys.modules.get("src.engine.scheduler")` seam 은 이번엔 불필요하고(원천 모듈
    monkeypatch 로 충분), 만들면 cycle61 D-2 의 "`sys.modules.get` 출현 6건 고정"
    가드까지 건드리게 되어 해롭다.
    """
    tree = _leaf_tree()
    offenders: list[str] = []
    for n in ast.walk(tree):
        if isinstance(n, ast.ImportFrom) and (n.module or "").startswith("src.engine.scheduler"):
            offenders.append(f"ImportFrom:{n.lineno}")
        if isinstance(n, ast.Import):
            offenders += [
                f"Import:{n.lineno}" for a in n.names
                if a.name.startswith("src.engine.scheduler")
            ]
    assert offenders == [], f"leaf → scheduler import 금지(순환). 위반: {offenders}"
    assert "sys.modules" not in _leaf_src(), (
        "`sys.modules.get(\"src.engine.scheduler\")` seam 금지 — 원천 모듈 monkeypatch 로 "
        "충분하고, 만들면 cycle61 D-2 의 출현 횟수 고정 가드를 건드린다"
    )
    fn = _function_node(tree, _LEAF_FN)
    first = (fn.args.posonlyargs + fn.args.args)[0]
    assert first.arg == "scheduler", (
        f"첫 인자명이 {first.arg!r} — `scheduler` 여야 한다"
        "(`stale_watcher_core.resubscribe_stale_priority(scheduler, cap=…)` 동형)"
    )


# ===========================================================================
# G-292-8 — 요약 로그 서식·인자 순서 (D+1 판독 계약)
# ===========================================================================
#: `[market_op_subscribe_summary]` INFO 한 줄의 **완성된** 포맷 문자열.
#: 필드 이름·순서·`%d` 개수·`main_direct=0` 리터럴까지 전부 계약이다 — 운영자가 이 줄을
#: awk/grep 으로 쪼개 D+1 판독에 쓴다. 순서만 뒤집혀도 값의 의미가 조용히 바뀐다.
_SUMMARY_FORMAT = (
    "[market_op_subscribe_summary] high=%d low_skipped=%d placed=%d released=%d "
    "skipped_no_slot=%d main_direct=0 sessions=%d main_tick=%d main_total=%d "
    "main_over=%d cap=%d"
)
#: 그 포맷에 물리는 인자식의 **원문 순서**. 포맷만 핀하면 인자 쪽 스왑
#: (`main_tick` ↔ `main_total`)이 통과한다 — 둘 다 `%d` 라 타입으로도 안 걸린다.
_SUMMARY_ARG_SOURCES = (
    "len(high_tickers)", "low_skipped", "subscribed", "released",
    "skipped_no_slot", "len(quotes)", "main_tick", "main_total", "main_over", "cap",
)


def _summary_info_call() -> tuple[str, ast.Call]:
    """leaf 안의 `[market_op_subscribe_summary]` **INFO** 호출 노드를 찾는다."""
    src = _leaf_src()
    fn = _function_node(ast.parse(src), _LEAF_FN)
    found = []
    for node in ast.walk(fn):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (isinstance(func, ast.Attribute) and func.attr == "info"):
            continue
        if not (isinstance(func.value, ast.Name) and func.value.id == "logger"):
            continue
        if not node.args:
            continue
        first = node.args[0]
        if isinstance(first, ast.Constant) and isinstance(first.value, str) \
                and first.value.startswith("[market_op_subscribe_summary]"):
            found.append(node)
    assert len(found) == 1, (
        f"`[market_op_subscribe_summary]` INFO 호출이 {len(found)}건 — 정확히 1건이어야 "
        "한다(0 = 요약 로그 소실 = D+1 판독 불가 / 2+ = 같은 마커 중복 발화)"
    )
    return src, found[0]


def test_g292_8_summary_log_format_and_arg_order_are_pinned() -> None:
    """G-292-8 — 요약 로그의 **필드 순서**와 **인자 순서**를 고정한다.

    적대 검증(cycle292 가드무력화 렌즈)이 잡은 커버리지 공백이다 — `main_tick` 과
    `main_total` 을 서로 바꾸는 뮤테이션이 파일 sha 핀과 cycle287 트리 digest **에서만**
    붉어졌다. 그 둘은 "무언가 바뀌었다" 만 말하고 **무엇이 왜 위험한지**는 말하지 못하며,
    핀이 정당하게 갱신되는 사이클에 함께 쓸려 들어간다. 값만 보는 행위 테스트
    (`test_summary_reports_main_occupancy`)는 마커 개명은 잡아도 순서 교환은 못 잡는다.

    왜 이 줄이 계약인가 — `main_total`(메인 세션 총 구독) vs `main_tick`(그중 시세)의
    차이가 08-19 사고의 진단축이다(메인 45/41 초과를 `[priority_drop]` 이 포화 시에만
    찍어 묻혀 있었고, 이 훅이 5분마다 무조건 찍게 만든 것이 시정이었다). 두 값이 뒤집히면
    `main_over` 판독이 반대로 읽힌다.
    """
    src, call = _summary_info_call()

    fmt = call.args[0].value
    assert fmt == _SUMMARY_FORMAT, (
        "요약 로그 서식이 바뀌었다 — 필드 이름·순서·`main_direct=0` 리터럴은 D+1 판독 "
        f"계약이다.\n  기대: {_SUMMARY_FORMAT!r}\n  실제: {fmt!r}"
    )
    assert fmt.count("%d") == len(_SUMMARY_ARG_SOURCES)

    got = tuple(
        (ast.get_source_segment(src, a) or "").strip() for a in call.args[1:]
    )
    assert got == _SUMMARY_ARG_SOURCES, (
        "요약 로그 인자 순서가 바뀌었다 — 전부 `%d` 라 타입으로는 안 걸리고 값의 의미만 "
        f"조용히 뒤집힌다.\n  기대: {_SUMMARY_ARG_SOURCES}\n  실제: {got}"
    )
