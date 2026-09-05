"""cycle259 Red — `log_analysis_engine.py`(922L) 수집/집계 ↔ LLM 계층 분할 (리팩토링 카드 ⑦).

명세: `spec_cycle259_gate_snapshot_log_split.md` §1 ⑦ · §2 (L1~L4).
근거: `_workspace/refactor/2026-09-05_review.md` 카드 #7.

## ⚠️ L1 은 **사이클 259 한정 가드** — 커밋 후 폐기한다

`test_l1_*` 은 워킹트리의 `log_metrics_collector.py` 와 **`git show HEAD:`** 의
`log_analysis_engine.py` 를 `ast.dump` 로 비교해 "이동은 byte 동일 복사였다" 를
실증한다. 이 비교는 cycle259 가 커밋되는 순간 HEAD 에 원본 함수가 사라져 목적을
다한다 — 그 상태를 감지하면 테스트가 **명시 skip 하며 삭제를 지시**한다.
`git show HEAD:` 기준 가드를 살려두면 (a) 커밋 직후 자기 일치로 공허해지거나
(b) 누가 그 파일을 편집하는 순간 영구 동결로 변한다(리팩토링 리뷰 카드 #1·#2 가
cycle250/251/252 에서 세 번 지적한 함정). **cycle259 커밋과 함께 이 테스트를 지운다.**
행위 계약은 L2·L2b·L3·L4 가 영구 가드로 이어받는다.

## 이 파일이 못박는 계약

- L1(한시): 이동 12함수의 AST 가 HEAD 원본과 **완전 동일**(본문 diff 0).
- L2: 재export 계약 — routes 가 쓰는 3 이름(`collect_daily_log_metrics` ·
      `DAILY_LOG_FETCH_LIMIT` · `HIGH_SEVERITY_FETCH_CAP`)이 `log_analysis_engine`
      에서 계속 import 되고 collector 의 **동일 객체**이며, `routes/log_reports.py`
      의 import 문 텍스트가 리터럴로 불변이다.
- L2b(보강, 영구): **이름 해석 폐쇄** — 이동 함수(중첩 함수·lambda 포함)가 모듈
      스코프에서 해석하는 모든 비-builtin 이름이 collector 네임스페이스에 있다.
      명세 §1 의 이동 목록에는 `_normalize_message` · `_LOGS_TS_SELECT` ·
      `_PATTERN_STEP_KEYWORDS` 3개가 빠져 있는데, 빠뜨리면 import 는 성공하고
      **20:10 배치에서 NameError** 로 그날 리포트가 통째로 사라진다(단위 테스트가
      그 함수를 대역으로 갈아끼우면 영원히 안 보인다). 이름 산출은 `ast.Name(Load)`
      − 지역 바인딩이다 — `co_names` 는 전역과 **속성 이름**을 구별하지 않아
      `datetime.min.time()` 을 전역 `time` 으로 오분류했고 프로덕션에 죽은
      `import time` 을 요구했다(cycle259 적대 검증 F1 — 가드 자기결함, 셀프테스트로
      봉인). HEAD 무의존이라 커밋 후에도 공허해지지 않는다.
- L3: `collect_daily_log_metrics` 반환 키 **순서** byte 동일 + collector 경로
      monkeypatch 로 대역이 실제로 먹는다(= 기존 18 테스트의 patch 경로 갱신 기준).
- L4: `log_analysis_engine.py` < 400L + 계층 분리(LLM 심볼은 lae 에만,
      collector 에 openai/insert 0).

RED 상태(구현 전): L1/L2/L2b/L3 = `src/engine/log_metrics_collector.py` 부재로 FAIL ·
L4 = 922L 이라 FAIL.
"""

from __future__ import annotations

import ast
import builtins
import importlib
import inspect
import subprocess
import textwrap
import types
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[3]
LAE_PATH = ROOT / "src" / "engine" / "log_analysis_engine.py"
COLLECTOR_PATH = ROOT / "src" / "engine" / "log_metrics_collector.py"
COLLECTOR_MOD = "src.engine.log_metrics_collector"
LAE_MOD = "src.engine.log_analysis_engine"
LOG_REPORTS_ROUTE = ROOT / "src" / "routes" / "log_reports.py"

KST = timezone(timedelta(hours=9))

#: 카드 ⑦ 이 collector 로 옮기는 12 함수 (명세 §1 ⑦).
MOVED_FUNCTIONS = (
    "_fetch_logs_in_range",
    "_count_logs_by_level",
    "_fetch_high_severity_logs",
    "_merge_high_severity",
    "_aggregate_logs",
    "_aggregate_tick_blind",
    "_aggregate_next_day_clear",
    "_aggregate_trades",
    "_build_portfolio_risk_snapshot",
    "_collect_strategy_funnel_stages",
    "_collect_strategy_funnel",
    "collect_daily_log_metrics",
)

#: `routes/log_reports.py` 가 `log_analysis_engine` 에서 계속 가져가는 이름 중
#: collector 소유가 되는 3 (재export 계약).
REEXPORTED = ("collect_daily_log_metrics", "DAILY_LOG_FETCH_LIMIT", "HIGH_SEVERITY_FETCH_CAP")

#: `routes/log_reports.py:13` 리터럴 — 이 줄이 바뀌면 카드 ⑦ 의 "routes 무접촉" 전제가 깨진다.
LOG_REPORTS_IMPORT_LINE = (
    "from src.engine.log_analysis_engine import _validate_report, "
    "collect_daily_log_metrics, generate_daily_log_report"
)

#: `collect_daily_log_metrics` 반환 키 **순서** (cycle249 C-1 과 동일 리터럴).
#: 이 dict 가 그대로 (a) OpenAI 프롬프트 (b) `daily_log_reports.metrics` JSONB
#: (c) 20:20 클라우드 루틴 번들이다.
EXPECTED_METRIC_KEYS = [
    "target_date",
    "logs",
    "trades",
    "api_metrics",
    "strategy_funnel",
    "strategy_funnel_stages",
    "next_day_clear",
    "portfolio_risk_snapshot",
    "tick_blind",
]


def _require_collector() -> types.ModuleType:
    if not COLLECTOR_PATH.exists():  # pragma: no cover - Red 경로
        pytest.fail(
            "Red — `src/engine/log_metrics_collector.py` 미생성 (리팩토링 카드 ⑦). "
            f"수집/집계 12 함수({', '.join(MOVED_FUNCTIONS)}) + 정규식 상수 6 + "
            "`DAILY_LOG_FETCH_LIMIT`/`HIGH_SEVERITY_FETCH_CAP`/`KST` 를 이 파일로 "
            "**byte 동일 복사**로 옮긴다."
        )
    return importlib.import_module(COLLECTOR_MOD)


def _fn_nodes(source: str) -> dict[str, ast.AST]:
    tree = ast.parse(source)
    return {
        node.name: node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def _module_level_names(source: str) -> set[str]:
    """모듈 최상위에서 바인딩되는 이름 전부 (import/대입/def/class)."""
    names: set[str] = set()
    for node in ast.parse(source).body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            names.update(t.id for t in node.targets if isinstance(t, ast.Name))
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            names.update((a.asname or a.name.split(".")[0]) for a in node.names)
    return names


def _head_source() -> str | None:
    """`git show HEAD:src/engine/log_analysis_engine.py` — 실패 시 None."""
    out = subprocess.run(
        ["git", "show", "HEAD:src/engine/log_analysis_engine.py"],
        cwd=ROOT, capture_output=True, text=True,
    )
    return out.stdout if out.returncode == 0 else None


# ===========================================================================
# L1 (사이클 259 한정 — 커밋과 함께 삭제) — 이동은 byte 동일 복사였다
# ===========================================================================
# ===========================================================================
# L2 — 재export 계약 (routes 무접촉)
# ===========================================================================
def test_l2_reexported_symbols_are_the_same_objects():
    collector = _require_collector()
    lae = importlib.import_module(LAE_MOD)

    for name in REEXPORTED:
        assert hasattr(lae, name), (
            f"Red — 재export 누락 `{name}` — `routes/log_reports.py` 의 "
            "`from src.engine.log_analysis_engine import ...` 가 ImportError 로 죽는다"
        )
        assert hasattr(collector, name), f"collector 에 `{name}` 부재"
        assert getattr(lae, name) is getattr(collector, name), (
            f"`{name}` 이 collector 와 다른 객체다 — 재export 가 아니라 복제다 "
            "(patch/식별 계약이 두 벌로 갈라진다)"
        )

    assert Path(inspect.getsourcefile(lae.collect_daily_log_metrics)).name == \
        "log_metrics_collector.py", "`collect_daily_log_metrics` 가 collector 소유가 아니다"
    assert Path(inspect.getsourcefile(lae.generate_daily_log_report)).name == \
        "log_analysis_engine.py", "`generate_daily_log_report` 는 LLM 계층 잔류가 계약"
    assert Path(inspect.getsourcefile(lae._validate_report)).name == \
        "log_analysis_engine.py", "`_validate_report` 는 LLM 계층 잔류가 계약"


def test_l2_log_reports_route_import_line_is_unchanged():
    body = LOG_REPORTS_ROUTE.read_text(encoding="utf-8")
    assert LOG_REPORTS_IMPORT_LINE in body, (
        "`src/routes/log_reports.py` 의 import 문이 바뀌었다 — 카드 ⑦ 의 금기다"
        f"\n기대 리터럴: {LOG_REPORTS_IMPORT_LINE}"
    )
    assert COLLECTOR_MOD not in body, (
        "라우트가 collector 를 직접 import 한다 — 재export 계약(라우트 무접촉)이 목적이다"
    )


def test_l2c_reexports_are_declared_in_dunder_all():
    """F2 봉인 — 재export 5 심볼이 `log_analysis_engine.__all__` 에 선언돼 있다.

    본문 미사용 3(`DAILY_LOG_FETCH_LIMIT` · `HIGH_SEVERITY_FETCH_CAP` ·
    `_build_portfolio_risk_snapshot`)은 `__all__` 이 없으면 pyflakes/ruff 가 unused
    import 로 보고하고 자동 정리(`ruff --fix` 등)가 재export 를 **조용히** 지운다 —
    그 순간 `routes/log_reports.py:13` 이 ImportError 로 죽는다.
    """
    lae = importlib.import_module(LAE_MOD)
    declared = getattr(lae, "__all__", None)
    assert declared is not None, "`log_analysis_engine.__all__` 부재 — 재export 가 lint 자동 정리에 노출된다"
    required = set(REEXPORTED) | {"KST", "_build_portfolio_risk_snapshot"}
    assert required <= set(declared), f"`__all__` 에서 빠진 재export: {sorted(required - set(declared))}"
    undefined = [n for n in declared if not hasattr(lae, n)]
    assert not undefined, f"`__all__` 이 존재하지 않는 이름을 선언한다: {undefined}"


def _fn_source_node(fn) -> ast.AST:
    """함수 객체의 소스 → 최상위 def 노드 (중첩 함수·lambda 는 `ast.walk` 가 포함한다)."""
    tree = ast.parse(textwrap.dedent(inspect.getsource(fn)))
    return tree.body[0]


def _module_scope_loads(fn_node: ast.AST) -> set[str]:
    """함수가 **모듈 스코프에서 해석하는** 이름 = `ast.Name(ctx=Load)` − 지역 바인딩.

    ⚠️ `code.co_names` 를 쓰지 않는다 — 그 튜플은 전역 참조와 **속성 이름**을 구별하지
    않아(`LOAD_GLOBAL` 과 `LOAD_ATTR` 이 같은 이름 풀을 쓴다) `datetime.min.time()` 의
    `.time` 을 전역 `time` 으로 오분류했고, 그 거짓 RED 를 피하려고 프로덕션
    `log_metrics_collector.py` 에 미사용 `import time` 이 들어간 적이 있다(cycle259
    적대 검증 F1). `ast.Attribute.attr` 은 str 이라 여기서는 애초에 안 잡힌다.

    지역 바인딩(인자 · 대입 · for/with/except 대상 · 컴프리헨션 변수 · 중첩 def/class
    이름 · 함수 안 import)은 어느 중첩 스코프에서든 한 번이라도 바인딩되면 뺀다.
    `global` 선언 이름은 되살린다. 놓치는 방향의 잔여는 "같은 이름이 한 중첩 스코프에선
    지역, 다른 스코프에선 전역" 인 경우뿐이다(이동 12 함수 실측 0).
    """
    loads: set[str] = set()
    bound: set[str] = set()
    declared_global: set[str] = set()
    for node in ast.walk(fn_node):
        if isinstance(node, ast.Name):
            (loads if isinstance(node.ctx, ast.Load) else bound).add(node.id)
        elif isinstance(node, ast.arg):
            bound.add(node.arg)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node is not fn_node:
                bound.add(node.name)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            bound.update((a.asname or a.name.split(".")[0]) for a in node.names)
        elif isinstance(node, ast.Global):
            declared_global.update(node.names)
    return (loads - bound) | (loads & declared_global)


def test_l2b_guard_does_not_mistake_attribute_names_for_globals():
    """가드 자기결함 봉인(F1) — 속성 이름·지역 바인딩은 전역 참조가 아니다.

    `co_names` 로 되돌리면 `time`/`date`/`combine` 이 섞여 들어와 이 테스트가 붉어진다.
    """
    snippet = textwrap.dedent(
        """
        async def probe(target_date: date, limit=DEFAULT_LIMIT):
            start = datetime.combine(target_date, datetime.min.time(), tzinfo=KST)
            rows = [r for r in await fetch(start) if r.level]
            json = {"n": len(rows)}          # 구 모듈 이름과 같은 지역 대입
            pick = lambda r: r.timestamp.date()
            def inner(x):
                return helper(x, json)
            return inner(pick), start.time()
        """
    )
    node = ast.parse(snippet).body[0]
    got = _module_scope_loads(node) - set(dir(builtins))
    assert got == {"date", "DEFAULT_LIMIT", "datetime", "KST", "fetch", "helper"}, got
    assert "time" not in got and "combine" not in got and "timestamp" not in got, (
        "속성 이름이 전역 참조로 오분류됐다 — `co_names` 회귀"
    )
    assert "json" not in got and "rows" not in got and "inner" not in got, (
        "지역 바인딩이 전역 참조로 잡혔다 — 구 모듈 이름과 겹치는 지역 변수가 거짓 RED 를 만든다"
    )


def test_l2b_collector_namespace_resolves_every_name_the_moved_functions_use():
    """이름 해석 폐쇄 — NameError 로 20:10 리포트가 통째로 사라지는 경로 차단.

    이동 12 함수(중첩 함수·lambda 포함)가 모듈 스코프에서 해석하는 이름 전부가
    collector 네임스페이스(또는 builtins)에 있어야 한다. 명세 §1 ⑦ 의 이동 목록에서
    빠진 3(`_normalize_message` · `_LOGS_TS_SELECT` · `_PATTERN_STEP_KEYWORDS`)이 실측
    근거다 — 단위 테스트가 상위 함수를 대역으로 갈아끼우면 이 결함은 배치 실행
    전까지 보이지 않는다. 검사 우주는 "HEAD 의 구 모듈 레벨 이름" 이 아니라 "함수가
    실제로 해석하는 모든 비-builtin 이름" 이라 git 무의존이고 커밋 후에도 공허해지지
    않는다(bare HEAD 비교 가드 금지 — 리뷰 카드 #1·#2).
    """
    collector = _require_collector()
    builtin_names = set(dir(builtins))
    missing: dict[str, list[str]] = {}
    for name in MOVED_FUNCTIONS:
        fn = getattr(collector, name, None)
        assert fn is not None, f"Red — collector 에 `{name}` 부재"
        used = _module_scope_loads(_fn_source_node(inspect.unwrap(fn))) - builtin_names
        gap = sorted(n for n in used if not hasattr(collector, n))
        if gap:
            missing[name] = gap

    assert not missing, (
        "collector 네임스페이스에 없는 참조 이름이 있다 — import 는 성공하고 "
        f"**실행 시 NameError** 가 난다: {missing}"
    )


# ===========================================================================
# L3 — 반환 키 순서 byte 동일 + collector 경로 monkeypatch 유효
# ===========================================================================
def _isolate_collector(monkeypatch) -> types.ModuleType:
    """수집 하위 호출을 **collector 경로**로 대역 (DB/KIS/레지스트리 무접촉).

    ⚠️ 이 헬퍼가 곧 기존 9 테스트 파일의 patch 경로 갱신 기준이다 — 이동 후에는
    `monkeypatch.setattr(lae, "_fetch_logs_in_range", ...)` 가 **먹지 않는다**
    (collector 내부 참조는 자기 모듈 전역에서 해석된다).
    """
    collector = _require_collector()

    async def _fetch(start, end, limit=None):
        return []

    async def _high(start, end, *a, **k):
        return []

    async def _count(start, end):
        return {"WARNING": 0, "ERROR": 0, "CRITICAL": 0}

    async def _trades(d1, d2):
        return []

    async def _funnel():
        return {"momentum": {"scanned": 0}}

    async def _stages(target_date):
        return {}

    async def _snapshot(now=None):
        return None

    monkeypatch.setattr(collector, "_fetch_logs_in_range", _fetch)
    monkeypatch.setattr(collector, "_fetch_high_severity_logs", _high)
    monkeypatch.setattr(collector, "_count_logs_by_level", _count)
    monkeypatch.setattr(collector, "get_trades_in_range", _trades)
    monkeypatch.setattr(collector, "get_request_metrics", lambda: {"total": 0})
    monkeypatch.setattr(collector, "_collect_strategy_funnel", _funnel)
    monkeypatch.setattr(collector, "_collect_strategy_funnel_stages", _stages)
    monkeypatch.setattr(collector, "_build_portfolio_risk_snapshot", _snapshot)
    return collector


async def test_l3_metric_key_order_is_byte_identical(monkeypatch):
    collector = _isolate_collector(monkeypatch)
    now_kst = datetime(2026, 9, 4, 14, 0, tzinfo=KST)

    metrics = await collector.collect_daily_log_metrics(date(2026, 9, 4), now_kst=now_kst)

    assert isinstance(metrics, dict)
    assert list(metrics) == EXPECTED_METRIC_KEYS, (
        f"키 순서가 바뀌었다 — 기대 {EXPECTED_METRIC_KEYS} / 실측 {list(metrics)}. "
        "이 dict 는 그대로 OpenAI 프롬프트 본문 · `daily_log_reports.metrics` JSONB · "
        "20:20 클라우드 루틴 번들이다(순서 변경 = 계약 변경)."
    )
    assert metrics["target_date"] == "2026-09-04"
    # 대역이 실제로 먹었다 = 이동 후 patch 경로가 collector 라는 증거
    assert metrics["api_metrics"] == {"total": 0}
    assert metrics["portfolio_risk_snapshot"] is None
    assert metrics["strategy_funnel"] == {"momentum": {"scanned": 0}}


async def test_l3b_reexported_entrypoint_returns_same_shape(monkeypatch):
    """`log_analysis_engine.collect_daily_log_metrics`(재export)도 같은 결과."""
    _isolate_collector(monkeypatch)
    lae = importlib.import_module(LAE_MOD)
    now_kst = datetime(2026, 9, 4, 14, 0, tzinfo=KST)

    metrics = await lae.collect_daily_log_metrics(date(2026, 9, 4), now_kst=now_kst)

    assert list(metrics) == EXPECTED_METRIC_KEYS


# ===========================================================================
# L4 — 파일 크기 + 계층 분리
# ===========================================================================
def test_l4_log_analysis_engine_is_llm_layer_only():
    lae_src = LAE_PATH.read_text(encoding="utf-8")
    lines = len(lae_src.splitlines())
    assert lines < 400, (
        f"Red — `log_analysis_engine.py` {lines}L (기대 < 400). 카드 ⑦ 은 수집/집계 "
        "≈600L 을 `log_metrics_collector.py` 로 옮겨 LLM 호출/저장 계층만 남긴다."
    )

    # LLM 계층은 lae 에만
    for token in ("SYSTEM_PROMPT", "_call_openai", "_validate_report", "generate_daily_log_report"):
        assert token in lae_src, f"LLM 계층 심볼 `{token}` 이 lae 에서 사라졌다"

    collector_src = COLLECTOR_PATH.read_text(encoding="utf-8")
    for token in ("AsyncOpenAI", "SYSTEM_PROMPT", "insert_log_report", "openai_api_key"):
        assert token not in collector_src, (
            f"collector 에 LLM/저장 계층 심볼 `{token}` — 분할의 목적은 "
            "\"이관 2단계(OpenAI 은퇴)\" 때 삭제 범위가 파일 하나가 되는 것이다"
        )
    # 수집 계층은 collector 에만 (pg 직접 접근이 lae 로 되돌아오지 않는다)
    assert "pg.fetch(" not in lae_src, (
        "`log_analysis_engine.py` 에 `pg.fetch(` 잔존 — 수집 계층은 collector 소유다"
    )

# L1(이동 12함수 AST == HEAD 원본) 은 사이클 259 한정 가드 — 커밋 2b2e6f2 이후 시점의 HEAD 대비 byte 동일을
# tester 가 실측(하네스 bi_harness: metrics JSON sha 3자 일치)한 뒤 커밋과 함께 삭제했다(bare HEAD 비교 가드 영구화 금지 규약).
