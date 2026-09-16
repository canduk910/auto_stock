r"""cycle285 — `src/routes/market_ops.py` AST 순도 가드.

정본 = 프롬프트 §4-1("시각을 하드코딩하지 않는다") — cycle282 `test_h6`/`test_h8`
(`test_cycle282_ast_purity.py`)의 같은 원칙을 새 라우트 파일에 적용한다.

이 파일은 정성적 요구를 기계로 고정한다:
1. 라우트 소스에 `HH:MM` 형태의 시각 리터럴이 (도크스트링을 뺀) 문자열 상수에 0건
   — 시각은 전부 `scheduler.TIME_*`/`quote_token_refresh.TIME_QUOTE_TOKEN_REFRESH`
   에서 **읽는다**.
2. 분·시 산술 리터럴(`\d{1,2}\s*\*\s*60`) 도 0건 — `utils/kst.ts` 의 `9 * 60` 류
   구멍이 프론트 조사에서 지적됐다(사이클 285 조사 §4-5). 백엔드도 같은 함정을
   피한다.
3. `datetime.now(`/`.utcnow(` 호출이 **정확히 1회** — 표와 야간작업 타임라인이
   서로 다른 순간을 보면 안 된다(cycle282 H6 동형).
4. `src.engine.scheduler` 에서 최소 8개 `TIME_*` 이름을 실제로 import 한다(값을
   베껴 쓰지 않았다는 것을 이름 참조로 증명).
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parents[3]
_ROUTE_REL = "src/routes/market_ops.py"

_TIME_LITERAL = re.compile(r"(?<!\+)\b\d{1,2}:\d{2}\b")
_MINUTE_ARITH = re.compile(r"\b\d{1,2}\s*\*\s*60\b")


def _tree() -> ast.AST:
    return ast.parse((_ROOT / _ROUTE_REL).read_text(encoding="utf-8"))


def _docstring_ids(tree: ast.AST) -> set:
    ids = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if (
                node.body
                and isinstance(node.body[0], ast.Expr)
                and isinstance(node.body[0].value, ast.Constant)
                and isinstance(node.body[0].value.value, str)
            ):
                ids.add(id(node.body[0].value))
    return ids


def _string_constants(tree: ast.AST) -> list:
    """docstring 을 뺀 문자열 리터럴 전부 (cycle282 h8 의 `_string_constants` 답습)."""
    skip = _docstring_ids(tree)
    return [
        n.value
        for n in ast.walk(tree)
        if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in skip
    ]


def test_a1_no_clock_time_literals_outside_docstrings():
    """A1 — 시각 리터럴 0건(도크스트링 제외). `+09:00` 타임존 접미는 예외다."""
    hits = [s for s in _string_constants(_tree()) if _TIME_LITERAL.search(s)]
    assert not hits, (
        f"{_ROUTE_REL}: 시각 리터럴 {hits} — scheduler.TIME_* 를 읽지 않고 베꼈다"
    )


def test_a2_no_minute_arithmetic_literals():
    """A2 — `9 * 60` 류 산술 시각도 금지(프론트 조사 §4-5 의 같은 함정 방어)."""
    src = (_ROOT / _ROUTE_REL).read_text(encoding="utf-8")
    hits = _MINUTE_ARITH.findall(src)
    assert not hits, f"{_ROUTE_REL}: 분 단위 시각 산술 리터럴 {hits}"


def test_a3_reads_the_clock_exactly_once():
    """A3 — `datetime.now(` 호출 정확히 1회 (cycle282 H6 동형)."""
    tree = _tree()
    calls = [
        n for n in ast.walk(tree)
        if isinstance(n, ast.Call) and getattr(n.func, "attr", None) in ("now", "utcnow")
    ]
    assert len(calls) == 1, f"현재시각 호출 {len(calls)}회 — 정확히 1회여야 한다"
    assert getattr(calls[0].func, "attr", None) == "now", "utcnow 금지"
    assert calls[0].args or calls[0].keywords, "무인자 now() 는 컨테이너 TZ 를 따른다"


def test_a4_imports_at_least_eight_scheduler_time_constants():
    """A4 — `scheduler.TIME_*` 실제 import — 값을 베끼지 않았다는 이름 증거."""
    tree = _tree()
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "src.engine.scheduler":
            names.update(alias.name for alias in node.names)
    time_consts = {n for n in names if n.startswith("TIME_")}
    assert len(time_consts) >= 8, f"scheduler.TIME_* import 부족: {time_consts}"


def test_a5_imports_quote_token_refresh_time_constant():
    """A5 — 토큰 재발급 시각은 scheduler 밖 정본(`quote_token_refresh`)에서.

    값은 19:00(cycle270-C) → **20:45**(cycle296, 2026-09-17) 로 옮겼다. 이 가드가
    재는 것은 값이 아니라 **출처**다 — 시각 리터럴이 라우트로 새지 않는 것.
    """
    tree = _tree()
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.ImportFrom)
            and node.module == "src.engine.quote_token_refresh"
            and any(alias.name == "TIME_QUOTE_TOKEN_REFRESH" for alias in node.names)
        ):
            return
    raise AssertionError("TIME_QUOTE_TOKEN_REFRESH import 부재")


# ---------------------------------------------------------------------------
# 범위 가드 — 8영역·scheduler.py·전략·market_state.py leaf 무접촉 (프롬프트 §7)
# ---------------------------------------------------------------------------
_EIGHT_AREA_FILES = (
    "src/engine/risk.py",
    "src/engine/order_engine.py",
    "src/engine/session.py",
    "src/engine/scanner.py",
    "src/engine/strategy_registry.py",
    "src/api/order.py",
)
_STRATEGY_FILES = (
    "src/engine/strategies/momentum.py",
    "src/engine/strategies/volatility_breakout.py",
    "src/engine/strategies/long_tail_volatility.py",
    "src/engine/strategies/donchian_swing.py",
    "src/engine/strategies/bull_flag_breakout.py",
    "src/engine/strategies/vcp_breakout.py",
    "src/engine/strategies/kojiro.py",
    "src/engine/strategy_base.py",
)


def test_a6_market_ops_route_never_imports_realtime_or_auth():
    """A6 — 이 라우트는 `src.realtime`/`src.auth` 를 참조하지 않는다(읽기 전용 관측
    화면 — 8영역 진입 경로가 애초에 없다는 것을 정적으로 증명)."""
    tree = _tree()
    roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module)
        if isinstance(node, ast.Import):
            roots.update(alias.name for alias in node.names)
    for forbidden in ("src.realtime", "src.auth"):
        assert not any(m == forbidden or m.startswith(forbidden + ".") for m in roots), (
            f"{_ROUTE_REL} 가 {forbidden} 를 참조한다 — 관측 화면 범위 밖"
        )


@pytest.mark.parametrize("rel", _EIGHT_AREA_FILES + _STRATEGY_FILES + ("src/engine/scheduler.py",))
def test_a7_untouched_files_still_import_cleanly(rel: str):
    """A7 — 이 사이클이 손대지 않기로 한 파일들이 여전히 존재하고 파싱된다.

    byte 동일까지는 보장 못 하지만(다른 사이클이 그 sha 를 핀한다), 최소한 이
    사이클이 그 파일을 깨뜨리지 않았다는 스모크 신호는 준다.
    """
    path = _ROOT / rel
    assert path.exists(), f"{rel} 이 사라졌다"
    ast.parse(path.read_text(encoding="utf-8"))
