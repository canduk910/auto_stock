"""사이클 196 (2026-07-07) — fetch_daily_candles_backfill 윈도우 클램프 회귀 가드.

배경 (사이클 192 D+1 실측): `fetch_daily_candles_backfill(total_days, window=100)` 의
윈도우 루프가 `start_offset = (i + 1) * window` 로 마지막 윈도우를 목표(total_days) 초과
overshoot → 실제 fetch 범위가 목표보다 큼 (total_days=220 시 3번째 윈도우 300영업일 =
≈430 cal일 도달, retention 230cal 초과 → 매 load churn).

시정 (P2): `start_offset = min((i + 1) * window, total_days)` 로 목표 초과 fetch 차단.

Group A 회귀 가드 (condition.py):
- A-1 (핵심): total_days=120 — 마지막 윈도우 start_offset ≤ 120 (≈178cal 도달, 290cal 아님)
- A-2 (regression): total_days=220 — 3 윈도우 유지 + 마지막 start_offset=220 (318cal 도달, 430 아님)
- A-3 (불변식): total_days=100 — 1 윈도우 start_offset=min(100,100)=100 불변 (150cal)
- A-4 (AST/불변): 함수 본체에 `min(..., total_days)` 클램프 존재 (목표 초과 fetch 재도입 영구 차단)

Red 유효성 (production 미변경 = clamp 부재):
- A-1/A-2/A-4 FAIL (마지막 윈도우 overshoot / min 클램프 부재)
- A-3 PASS (단일 윈도우 = 클램프 no-op 불변식)

날짜 검증 방식 (사이클 176/180 교훈 — 절대 날짜 하드코딩 회피 / 사이클 187 freezegun 금지):
- `fetch_daily_candles_ranged` mock 으로 (start, end) 캡처.
- 윈도우 0 의 end_offset=0 → win_end = today - 0 = **today** → 캡처된 첫 윈도우 end 가
  함수 내부 today 와 정확히 동일 → 외부 시계 의존 0 (deterministic).
- 각 윈도우 start 를 `offset = (today - start).days` 로 환산 → 클램프 경계
  `int(total_days*7/5)+10` 이하 단언 (source win_start = today - (int(start_offset*7/5)+10)).
"""

from __future__ import annotations

import ast
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from tests.unit.ast._ast_helpers import find_function_def, read_module_source

pytestmark = pytest.mark.unit


def _parse(yyyymmdd: str):
    """캡처된 YYYYMMDD 문자열 → date."""
    return datetime.strptime(yyyymmdd, "%Y%m%d").date()


def _clamp_boundary_cal(total_days: int) -> int:
    """source win_start 오프셋 상한 (달력일) = int(total_days*7/5)+10.

    클램프 적용 시 마지막 윈도우 start_offset == total_days → start_cal 이 이 값에 정확 수렴.
    """
    return int(total_days * 7 / 5) + 10


def _has_min_clamp_with_total_days(func_node: ast.AST) -> bool:
    """함수 노드 서브트리에 `min(..., total_days, ...)` 호출 존재 여부 (A-4 detector)."""
    for sub in ast.walk(func_node):
        if not (isinstance(sub, ast.Call) and isinstance(sub.func, ast.Name)
                and sub.func.id == "min"):
            continue
        for arg in sub.args:
            for inner in ast.walk(arg):
                if isinstance(inner, ast.Name) and inner.id == "total_days":
                    return True
    return False


async def _capture_windows(monkeypatch, total_days: int, window: int = 100):
    """fetch_daily_candles_backfill 실행 + 윈도우 (start, end) 캡처 반환."""
    from src.api import condition

    calls: list[tuple[str, str]] = []

    async def fake_ranged(ticker, start, end):
        calls.append((start, end))
        return []  # 반환값 무관 — 호출 인자(start/end) 만 검증

    monkeypatch.setattr(condition, "fetch_daily_candles_ranged", fake_ranged)
    # 윈도우 간 sleep 실호출 회피 (사이클 172 패턴, freezegun 금지)
    monkeypatch.setattr(condition.asyncio, "sleep", AsyncMock())

    await condition.fetch_daily_candles_backfill("005930", total_days=total_days, window=window)
    return calls


# ---------------------------------------------------------------------------
# A-1 (핵심) — total_days=120 → 마지막 윈도우 start_offset ≤ 120 클램프
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_a1_total_120_last_window_clamped(monkeypatch):
    """total_days=120 — 모든 윈도우 start_offset ≤ 120 (마지막 ≈178cal, 290cal 아님).

    Red (clamp 부재): 윈도우 1 start_offset=200 → 290cal > 178 경계 → FAIL.
    Green (clamp): 윈도우 1 start_offset=min(200,120)=120 → 178cal = 경계 → PASS.
    """
    calls = await _capture_windows(monkeypatch, total_days=120, window=100)

    # ceil(120/100) = 2 윈도우 (클램프는 윈도우 개수 불변 — start_offset 만 변경)
    assert len(calls) == 2, "ceil(120/100) = 2 윈도우"

    # 윈도우 0 end_offset=0 → win_end == today (함수 내부 today 정확 복원, 시계 의존 0)
    today = _parse(calls[0][1])
    boundary_cal = _clamp_boundary_cal(120)  # = 178

    for start, _end in calls:
        offset = (today - _parse(start)).days
        assert offset <= boundary_cal, (
            f"윈도우 start_offset 클램프 초과: offset={offset}cal > 경계 {boundary_cal}cal "
            f"(clamp 부재 = 목표 초과 fetch)"
        )

    # 마지막 윈도우가 정확히 클램프 경계(178cal, start_offset=120)에 수렴 — 290cal 아님
    last_offset = (today - _parse(calls[-1][0])).days
    assert last_offset == boundary_cal, (
        f"마지막 윈도우 start_offset=min(200,120)=120 → {boundary_cal}cal 도달 의무 "
        f"(clamp 부재 시 200 → 290cal): 실제 {last_offset}cal"
    )


# ---------------------------------------------------------------------------
# A-2 (regression) — total_days=220 → 3 윈도우 유지 + 마지막 start_offset=220 (318cal)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_a2_total_220_three_windows_clamped(monkeypatch):
    """total_days=220 — 3 윈도우 유지, 마지막 start_offset=220 (318cal, 430 아님).

    Red (clamp 부재): 윈도우 2 start_offset=300 → 430cal > 318 경계 → FAIL.
    Green (clamp): 윈도우 2 start_offset=min(300,220)=220 → 318cal = 경계 → PASS.
    """
    calls = await _capture_windows(monkeypatch, total_days=220, window=100)

    assert len(calls) == 3, "ceil(220/100) = 3 윈도우 유지 (사이클 172 회귀 보존)"

    today = _parse(calls[0][1])
    boundary_cal = _clamp_boundary_cal(220)  # = 318

    for start, _end in calls:
        offset = (today - _parse(start)).days
        assert offset <= boundary_cal, (
            f"윈도우 start_offset 클램프 초과: offset={offset}cal > 경계 {boundary_cal}cal"
        )

    last_offset = (today - _parse(calls[-1][0])).days
    assert last_offset == boundary_cal, (
        f"마지막 윈도우 start_offset=min(300,220)=220 → {boundary_cal}cal 도달 의무 "
        f"(clamp 부재 시 300 → 430cal): 실제 {last_offset}cal"
    )


# ---------------------------------------------------------------------------
# A-3 (불변식) — total_days=100 → 1 윈도우 start_offset=min(100,100)=100 불변
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_a3_total_100_single_window_invariant(monkeypatch):
    """total_days=100 — 단일 윈도우 start_offset=min(100,100)=100 불변 (150cal).

    클램프 no-op 불변식 — Red/Green 모두 PASS ((0+1)*100 == 100 == min(100,100)).
    """
    calls = await _capture_windows(monkeypatch, total_days=100, window=100)

    assert len(calls) == 1, "ceil(100/100) = 1 윈도우"

    today = _parse(calls[0][1])
    boundary_cal = _clamp_boundary_cal(100)  # = 150

    last_offset = (today - _parse(calls[0][0])).days
    assert last_offset == boundary_cal, (
        f"단일 윈도우 start_offset=100 → {boundary_cal}cal (클램프 no-op 불변): 실제 {last_offset}cal"
    )


# ---------------------------------------------------------------------------
# A-4 (AST/불변) — 함수 본체에 min(..., total_days) 클램프 존재 (재도입 영구 차단)
# ---------------------------------------------------------------------------
def test_a4_ast_clamp_present():
    """fetch_daily_candles_backfill 본체에 `min(..., total_days)` 클램프 존재 의무.

    Red (clamp 부재): min 호출 자체가 없음 (num_windows 는 max() 사용) → FAIL.
    Green (clamp): start_offset = min((i+1)*window, total_days) → PASS.
    """
    src_path = Path(__file__).resolve().parents[3] / "src" / "api" / "condition.py"
    source = read_module_source(src_path)
    node = find_function_def(source, "fetch_daily_candles_backfill")
    assert node is not None, "fetch_daily_candles_backfill 함수 정의 존재 의무"

    assert _has_min_clamp_with_total_days(node), (
        "fetch_daily_candles_backfill 본체에 min(..., total_days) 클램프 존재 의무 "
        "(사이클 196 — 목표 초과 fetch 재도입 영구 차단)"
    )


def test_a4_selftest_detector():
    """A-4 detector self-test — 클램프 유/무 정확 판정 (사이클 167/172 self-test 패턴)."""
    yes_tree = ast.parse(
        "def f(total_days, window, i):\n"
        "    start_offset = min((i + 1) * window, total_days)\n"
    )
    no_tree = ast.parse(
        "def f(total_days, window, i):\n"
        "    start_offset = (i + 1) * window\n"
    )
    yes_fn = next(n for n in ast.walk(yes_tree) if isinstance(n, ast.FunctionDef))
    no_fn = next(n for n in ast.walk(no_tree) if isinstance(n, ast.FunctionDef))

    assert _has_min_clamp_with_total_days(yes_fn) is True, "클램프 존재 → True"
    assert _has_min_clamp_with_total_days(no_fn) is False, "클램프 부재 → False (Red 재현)"
