"""Phase 0 — TIME_RECOMMENDATION 시점 19:50 → 20:00 이동 회귀 가드.

배경 (Plan: `/Users/koscom/.claude/plans/backtest-integration-mcp.md`):
- 19:50 자문 + (Phase 3 에서 추가될) 백테스트 검증 정합성 사전 확보를 위해
  AI자문 호출 시점을 19:50 → 20:00 으로 이동.
- `TIME_NXT_POST_BUY_STOP=19:50` 은 NXT 애프터 매수 중단 안전 마감 시점으로 그대로 유지.
- 20:00 동시 발화: `generate_recommendations()` + `unsubscribe_all()` — 둘 다
  `asyncio.create_task` 백그라운드 비동기로 race 없음.

검증 방식:
- 상수 값 직접 비교 (행위 1~3)
- `TradingScheduler.start()` 소스 AST 정적 검사 — 무한 루프를 실행하지 않고
  19:50 / 20:00 분기 안에서 `generate_recommendations` 호출 위치를 검증 (행위 4, 5)
- 행위 6 (자문 except 핸들러 보존) 은 기존 `test_scheduler_recommendation_failure.py`
  가 이미 보호하므로 본 파일은 시각 이동에만 집중

회귀 보호 5 케이스:
- A: `TIME_RECOMMENDATION == time(20, 0)`
- B: `TIME_NXT_POST_BUY_STOP == time(19, 50)` (변경되지 않음)
- C: `TIME_RECOMMENDATION < TIME_SETTLEMENT` (20:00 < 20:10)
- D: 20:00 분기 (`TIME_NXT_POST_CLOSE` 대기 이후) 에 `generate_recommendations` 호출 존재
- E: 19:50 분기 (`TIME_NXT_POST_BUY_STOP` ~ `TIME_NXT_POST_CLOSE` 사이) 에는
     `generate_recommendations` 호출이 *없다*
"""

from __future__ import annotations

import ast
import inspect
import textwrap
from datetime import time as dtime

import pytest

from src.engine import scheduler as scheduler_mod
from src.engine.scheduler import TradingScheduler


pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# AST helpers
# ---------------------------------------------------------------------------
def _start_func_ast() -> ast.AsyncFunctionDef:
    src = textwrap.dedent(inspect.getsource(TradingScheduler.start))
    module = ast.parse(src)
    assert isinstance(module.body[0], ast.AsyncFunctionDef)
    return module.body[0]


def _collect_wait_until_calls(func: ast.AsyncFunctionDef) -> list[tuple[int, str]]:
    """`await self._wait_until(<NAME>)` 의 (lineno, NAME) 추출."""
    out: list[tuple[int, str]] = []
    for node in ast.walk(func):
        if not isinstance(node, ast.Call):
            continue
        f = node.func
        if not (
            isinstance(f, ast.Attribute)
            and f.attr == "_wait_until"
            and isinstance(f.value, ast.Name)
            and f.value.id == "self"
        ):
            continue
        if not node.args:
            continue
        arg = node.args[0]
        if isinstance(arg, ast.Name):
            out.append((node.lineno, arg.id))
        elif isinstance(arg, ast.Attribute):
            out.append((node.lineno, arg.attr))
    return out


def _collect_generate_recommendations_calls(func: ast.AsyncFunctionDef) -> list[int]:
    """`generate_recommendations(...)` 호출 라인 번호 리스트.

    `await generate_recommendations()` 와 `asyncio.create_task(generate_recommendations())` 양쪽 모두 포착.
    """
    out: list[int] = []
    for node in ast.walk(func):
        if not isinstance(node, ast.Call):
            continue
        f = node.func
        # 직접 호출: generate_recommendations(...)
        if isinstance(f, ast.Name) and f.id == "generate_recommendations":
            out.append(node.lineno)
        # 속성 호출: anything.generate_recommendations(...)
        elif isinstance(f, ast.Attribute) and f.attr == "generate_recommendations":
            out.append(node.lineno)
    return out


@pytest.fixture(scope="module")
def start_ast() -> ast.AsyncFunctionDef:
    return _start_func_ast()


# ---------------------------------------------------------------------------
# Case A — TIME_RECOMMENDATION 상수 = 20:00
# ---------------------------------------------------------------------------
def test_time_recommendation_constant_is_20_00():
    """AI자문 시점은 20:00 으로 이동되어야 한다 (Phase 0)."""
    assert scheduler_mod.TIME_RECOMMENDATION == dtime(20, 0), (
        f"TIME_RECOMMENDATION={scheduler_mod.TIME_RECOMMENDATION!r} — "
        "Phase 0 사양(20:00) 위반. backtest 검증 정합성 깨짐."
    )


# ---------------------------------------------------------------------------
# Case B — TIME_NXT_POST_BUY_STOP 은 19:50 그대로 (안전 규칙 보존)
# ---------------------------------------------------------------------------
def test_time_nxt_post_buy_stop_remains_19_50():
    """NXT 애프터 매수 중단은 19:50 그대로. 자문 시각 이동과 분리되어야 한다."""
    assert scheduler_mod.TIME_NXT_POST_BUY_STOP == dtime(19, 50), (
        f"TIME_NXT_POST_BUY_STOP={scheduler_mod.TIME_NXT_POST_BUY_STOP!r} — "
        "CLAUDE.md 핵심 안전 규칙 위반 (NXT 매수 중단은 19:50 고정)."
    )


# ---------------------------------------------------------------------------
# Case C — 자문 시각이 정산 시각보다 앞이어야 함
# ---------------------------------------------------------------------------
def test_recommendation_strictly_before_settlement():
    """TIME_RECOMMENDATION < TIME_SETTLEMENT 순서 보장 (20:00 < 21:30, cycle283)."""
    assert scheduler_mod.TIME_RECOMMENDATION < scheduler_mod.TIME_SETTLEMENT, (
        "자문 시각이 정산 시각 이후이면 metrics 수집/INSERT 가 깨질 수 있다."
    )
    # cycle283 재기준선 — 원 단언의 *의도* 는 "자문(OpenAI ~3분)이 끝날 시간을 주고
    # 정산이 온다" 는 **간격 하한**이었고, 20:10 하드핀은 그 시절의 유일한 값이었다.
    # 정산이 21:30 으로 옮겨지면서(사용자 결정 D3 — 일봉 적재 20:30 뒤로 밀기 위함)
    # 그 간격은 10분 → 90분이 됐다. 값을 뒤집는 대신 **의도를 재표현**한다:
    #   (a) 정산은 여전히 정확한 값에 핀(우발적 드리프트 차단)
    #   (b) 자문↔정산 간격이 OpenAI 수용 마진(10분) 이상
    # 그리고 이제 그 사이에 **일봉 적재(20:30)** 가 끼므로 그 순서도 함께 잠근다.
    assert scheduler_mod.TIME_SETTLEMENT == dtime(21, 30), (
        "TIME_SETTLEMENT 가 21:30 이 아니면 자문 ↔ 적재 ↔ 정산 순서 가정이 깨짐."
    )
    _rec = scheduler_mod.TIME_RECOMMENDATION
    _set = scheduler_mod.TIME_SETTLEMENT
    gap_min = (_set.hour * 60 + _set.minute) - (_rec.hour * 60 + _rec.minute)
    assert gap_min >= 10, (
        f"자문↔정산 간격 {gap_min}분 — OpenAI 호출(전략당 30s × 6 ≈ 3분) 수용 마진 부족"
    )
    assert _rec <= scheduler_mod.TIME_STOCK_MASTER_DAILY_LOAD < _set, (
        "일봉 적재가 자문↔정산 사이에 있어야 한다 — 정산 뒤면 매일 0회 발화하고, "
        "자문 앞이면 애프터마켓(~20:00) 물량을 못 담는다"
    )


# ---------------------------------------------------------------------------
# Case D — 20:00 분기에 generate_recommendations 호출 존재
# ---------------------------------------------------------------------------
def test_generate_recommendations_called_in_20_00_branch(start_ast):
    """`TIME_NXT_POST_CLOSE`(20:00) 대기 이후 `TIME_SETTLEMENT`(20:10) 대기 이전 구간에
    `generate_recommendations(...)` 호출이 존재해야 한다."""
    waits = _collect_wait_until_calls(start_ast)
    rec_calls = _collect_generate_recommendations_calls(start_ast)

    post_close_lines = [ln for ln, name in waits if name == "TIME_NXT_POST_CLOSE"]
    settlement_lines = [ln for ln, name in waits if name == "TIME_SETTLEMENT"]
    assert post_close_lines, "TIME_NXT_POST_CLOSE 대기 라인 없음 — 회귀"
    assert settlement_lines, "TIME_SETTLEMENT 대기 라인 없음 — 회귀"

    post_close_line = post_close_lines[0]
    settlement_line = settlement_lines[0]

    in_20_00_branch = [ln for ln in rec_calls if post_close_line < ln < settlement_line]
    assert in_20_00_branch, (
        "20:00 분기(TIME_NXT_POST_CLOSE 대기 ~ TIME_SETTLEMENT 대기 사이) 에 "
        "`generate_recommendations(...)` 호출이 없음. Phase 0 분기 이동 누락."
    )


# ---------------------------------------------------------------------------
# Case E — 19:50 분기에는 generate_recommendations 호출이 *없다*
# ---------------------------------------------------------------------------
def test_generate_recommendations_NOT_called_in_19_50_branch(start_ast):
    """`TIME_NXT_POST_BUY_STOP`(19:50) 대기 이후 `TIME_NXT_POST_CLOSE`(20:00) 대기 이전
    구간에는 `generate_recommendations(...)` 호출이 *없어야* 한다.

    19:50 분기는 `buy_disabled = True` + NXT 애프터 매수 중단 로그만 남기고,
    자문 호출은 전부 20:00 분기로 이동되었어야 한다."""
    waits = _collect_wait_until_calls(start_ast)
    rec_calls = _collect_generate_recommendations_calls(start_ast)

    post_buy_stop_lines = [ln for ln, name in waits if name == "TIME_NXT_POST_BUY_STOP"]
    post_close_lines = [ln for ln, name in waits if name == "TIME_NXT_POST_CLOSE"]
    assert post_buy_stop_lines, "TIME_NXT_POST_BUY_STOP 대기 라인 없음 — 회귀"
    assert post_close_lines, "TIME_NXT_POST_CLOSE 대기 라인 없음 — 회귀"

    post_buy_stop_line = post_buy_stop_lines[0]
    post_close_line = post_close_lines[0]

    in_19_50_branch = [
        ln for ln in rec_calls if post_buy_stop_line < ln < post_close_line
    ]
    assert not in_19_50_branch, (
        f"19:50 분기(TIME_NXT_POST_BUY_STOP 대기 ~ TIME_NXT_POST_CLOSE 대기 사이) 에 "
        f"`generate_recommendations(...)` 호출 잔존 라인={in_19_50_branch}. "
        f"Phase 0 자문 시점 이동 미완료 — 19:50 호출 분기를 제거해야 함."
    )
