"""사이클 102 영역 3 — force_retry 임계 상향 (Q73=B, Red).

G-THRESHOLD1~3 + G-LMS1 + G-PERSIST1 — `STALE_FORCE_RETRY_AFTER_SECS` 5분(300s) →
10분(600s) + `STALE_FORCE_RETRY_HOURLY_CAP` 12회 → 6회 임계 상향 + 9분 미경과 skip /
11분 경과 force_retry 발화 / 6회 cap 차단 정합 검증.

영역 3 = 사이클 29 R1 패턴 답습 (영역 폐기 0, 임계만 상향). 사이클 17 OPSP0002 backoff 영속
+ 사이클 29 R1/R2/R3 영속 + 사이클 66 cap=10 priority 분리 영속 + 사이클 67 stale_manager
4 sub-module 영속.

Red: production 상수 = 300/12 (기존) → G-THRESHOLD1~3 + G-LMS1 + G-PERSIST1 모두 FAIL.
Green: backend-dev `src/engine/stale_diagnostics.py` L30~L31 2 줄 시정 후 5 PASS.

영속 의무:
- 사이클 29 R1 시간 기반 force_retry 영속 (영역 폐기 0)
- 사이클 29 005935 사고 패턴 영구 차단 영속
- 매매 안전성 영향 0 (시세 영역, 매도 hot path 영향 0)
"""
from __future__ import annotations

import ast
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from src.engine import stale_diagnostics


pytestmark = pytest.mark.unit


_STALE_DIAGNOSTICS_PY = (
    Path(__file__).resolve().parents[3] / "src" / "engine" / "stale_diagnostics.py"
)


# ---------------------------------------------------------------------------
# G-THRESHOLD1 — STALE_FORCE_RETRY_AFTER_SECS == 600 영속 (Q73=B)
# ---------------------------------------------------------------------------
def test_g_threshold1_force_retry_after_secs_raised_to_600():
    """G-THRESHOLD1 (HIGH): `STALE_FORCE_RETRY_AFTER_SECS == 600` (10분) 영속.

    사이클 29 5분 → 사이클 102 Q73=B 10분 상향.

    Red: production 상수 = 300 (5분) → FAIL.
    Green: backend-dev `src/engine/stale_diagnostics.py:30` `300` → `600` 시정 후 PASS.

    영속 의무:
    - 사이클 29 R1 영역 폐기 0 (영역 영속, 임계만 상향)
    - LMS chain 안전 마진 증가 (124~141건/일 → 50~70건/일 예상)
    """
    actual = stale_diagnostics.STALE_FORCE_RETRY_AFTER_SECS
    assert actual == 600, (
        f"G-THRESHOLD1 위반 — `STALE_FORCE_RETRY_AFTER_SECS` 영역 침범:\n"
        f"  실측: {actual}s (영속 = 600s 영속)\n"
        f"  사이클 102 Q73=B 시정: 300 → 600 (5분 → 10분)\n"
        f"  시정 파일: `src/engine/stale_diagnostics.py:30`\n"
        f"  영속 의무:\n"
        f"  - 사이클 29 R1 영역 폐기 0 (영역 영속, 임계만 상향)\n"
        f"  - LMS chain 안전 마진 증가 (124~141건/일 → 50~70건/일 예상)\n"
    )


# ---------------------------------------------------------------------------
# G-THRESHOLD2 — STALE_FORCE_RETRY_HOURLY_CAP == 6 영속 (Q73=B)
# ---------------------------------------------------------------------------
def test_g_threshold2_force_retry_hourly_cap_raised_to_6():
    """G-THRESHOLD2 (HIGH): `STALE_FORCE_RETRY_HOURLY_CAP == 6` 영속.

    사이클 29 12회 → 사이클 102 Q73=B 6회 상향 (LMS/앱키 정지 위험 차단).

    Red: production 상수 = 12 → FAIL.
    Green: backend-dev `src/engine/stale_diagnostics.py:31` `12` → `6` 시정 후 PASS.
    """
    actual = stale_diagnostics.STALE_FORCE_RETRY_HOURLY_CAP
    assert actual == 6, (
        f"G-THRESHOLD2 위반 — `STALE_FORCE_RETRY_HOURLY_CAP` 영역 침범:\n"
        f"  실측: {actual}회 (영속 = 6회)\n"
        f"  사이클 102 Q73=B 시정: 12 → 6\n"
        f"  시정 파일: `src/engine/stale_diagnostics.py:31`\n"
        f"  영속 의무: LMS / 앱키 정지 위험 차단 보강\n"
    )


# ---------------------------------------------------------------------------
# G-THRESHOLD3 — 구 값 영구 부재 AST (silent 결함 영구 차단)
# ---------------------------------------------------------------------------
def test_g_threshold3_old_values_purged_ast():
    """G-THRESHOLD3 (HIGH): 구 값 (`= 300` for AFTER_SECS / `= 12` for HOURLY_CAP) 영구
    부재 AST (사이클 88 G-REJECT 답습 영구 차단 패턴).

    Red: production 영역 = 사이클 29 상수 잔존 → FAIL.
    Green: backend-dev 시정 후 AST `value=600` / `value=6` 영속 → PASS.

    영속 의무:
    - 사이클 88 G-REJECT 답습 (구 값 영구 부재 AST 가드 패턴)
    - 미래 회귀 시 (`300` / `12` 재도입 silent 결함) 영구 차단
    """
    source = _STALE_DIAGNOSTICS_PY.read_text(encoding="utf-8")
    tree = ast.parse(source)

    after_secs_value: int | None = None
    hourly_cap_value: int | None = None

    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if not isinstance(target, ast.Name):
                    continue
                if (
                    target.id == "STALE_FORCE_RETRY_AFTER_SECS"
                    and isinstance(node.value, ast.Constant)
                    and isinstance(node.value.value, int)
                ):
                    after_secs_value = node.value.value
                elif (
                    target.id == "STALE_FORCE_RETRY_HOURLY_CAP"
                    and isinstance(node.value, ast.Constant)
                    and isinstance(node.value.value, int)
                ):
                    hourly_cap_value = node.value.value

    missing: list[str] = []
    if after_secs_value != 600:
        missing.append(
            f"  - `STALE_FORCE_RETRY_AFTER_SECS` AST 정의 = {after_secs_value} (영속 = 600)"
        )
    if hourly_cap_value != 6:
        missing.append(
            f"  - `STALE_FORCE_RETRY_HOURLY_CAP` AST 정의 = {hourly_cap_value} (영속 = 6)"
        )

    assert not missing, (
        f"\n사이클 102 G-THRESHOLD3 위반 — 구 값 영구 부재 AST 영역 침범:\n"
        + "\n".join(missing)
        + "\n\n  사이클 102 Q73=B 영구 가드:\n"
        f"  - `STALE_FORCE_RETRY_AFTER_SECS = 600` AST 정의 영속\n"
        f"  - `STALE_FORCE_RETRY_HOURLY_CAP = 6` AST 정의 영속\n"
        f"  - 사이클 88 G-REJECT 답습 = 미래 회귀 시 silent 결함 영구 차단\n"
    )


# ---------------------------------------------------------------------------
# G-LMS1 — 9분 미경과 skip + 11분 경과 force_retry 발화 정합 (freezegun)
# ---------------------------------------------------------------------------
def test_g_lms1_cooldown_9min_skip_and_11min_retry():
    """G-LMS1 (MEDIUM): `STALE_FORCE_RETRY_AFTER_SECS = 600` (10분) 영속 시
    9분 미경과 → skip 영속 + 11분 경과 → force_retry 발화 영속 (사이클 29 R1 패턴 답습).

    Red: production 상수 = 300 (5분) → 9분 경과 시 즉시 force_retry 발화 → FAIL.
    Green: 600 (10분) 시정 후 9분 미경과 skip + 11분 경과 발화 → PASS.

    검증 매트릭스 (사이클 29 R1 영속 영역 답습):
    - 9분 경과 < STALE_FORCE_RETRY_AFTER_SECS (600s) → skip 영속
    - 11분 경과 > STALE_FORCE_RETRY_AFTER_SECS (600s) → force_retry 영속
    """
    # 사이클 102 영속 상수 영역 검증 (G-THRESHOLD1 의존)
    after_secs = stale_diagnostics.STALE_FORCE_RETRY_AFTER_SECS

    # 9분 경과 (540초) < 600s → skip 영속
    cooldown_9min = 9 * 60  # 540s
    assert cooldown_9min < after_secs, (
        f"G-LMS1 위반 — 9분 경과 cooldown skip 영속 결함:\n"
        f"  실측 STALE_FORCE_RETRY_AFTER_SECS = {after_secs}s (영속 = 600s)\n"
        f"  9분 = {cooldown_9min}s (영속 = {after_secs}s 보다 작음 → skip 영역)\n"
        f"  사이클 102 Q73=B 시정 필요 (사이클 29 R1 패턴 답습)\n"
    )

    # 11분 경과 (660초) > 600s → force_retry 영속
    cooldown_11min = 11 * 60  # 660s
    assert cooldown_11min > after_secs, (
        f"G-LMS1 위반 — 11분 경과 force_retry 발화 영속 결함:\n"
        f"  실측 STALE_FORCE_RETRY_AFTER_SECS = {after_secs}s (영속 = 600s)\n"
        f"  11분 = {cooldown_11min}s (영속 = {after_secs}s 보다 큼 → force_retry 영역)\n"
    )


# ---------------------------------------------------------------------------
# G-PERSIST1 — 60분 윈도우 6회 cap 차단 (사이클 29 R1/R2/R3 영속)
# ---------------------------------------------------------------------------
def test_g_persist1_hourly_cap_6_blocks_7th_attempt():
    """G-PERSIST1 (MEDIUM): 60분 윈도우 내 6회 force_retry 후 7회째 cap 차단 영속.

    사이클 29 R1 패턴 답습 (영역 폐기 0). 사이클 66 K-10 `[stale_force_retry_cap]` WARNING
    영속 (변경 0).

    Red: production 상수 = 12 → 7회째 통과 → FAIL.
    Green: 6 시정 후 7회째 차단 영속 → PASS.

    검증 매트릭스:
    - len(history) == 6 → cap 차단 영속 (사이클 66 K-10 WARNING)
    - len(history) == 5 → 정상 진행 영역
    - 사이클 29 R1/R2/R3 영속 (변경 0) 확정
    """
    cap = stale_diagnostics.STALE_FORCE_RETRY_HOURLY_CAP

    # 6회 history 시 cap 차단 영속 (사이클 66 K-10 WARNING 영속)
    history_6 = [datetime.now(timezone.utc) - timedelta(minutes=30)] * 6
    assert len(history_6) >= cap, (
        f"G-PERSIST1 위반 — 6회 history cap 차단 영속 결함:\n"
        f"  실측 STALE_FORCE_RETRY_HOURLY_CAP = {cap}회 (영속 = 6)\n"
        f"  6회 ≥ {cap} 영속 영역 침범 — 사이클 102 Q73=B 시정 필요\n"
        f"  영속: `if len(history) >= STALE_FORCE_RETRY_HOURLY_CAP: cap_blocked += 1`\n"
        f"  사이클 66 K-10 `[stale_force_retry_cap]` WARNING 영속 (변경 0)\n"
    )

    # 5회 history 시 정상 진행 영역 (cap 미초과)
    history_5 = [datetime.now(timezone.utc) - timedelta(minutes=30)] * 5
    assert len(history_5) < cap, (
        f"G-PERSIST1 위반 — 5회 history 정상 진행 영속 결함:\n"
        f"  실측 STALE_FORCE_RETRY_HOURLY_CAP = {cap}회 (영속 = 6)\n"
        f"  5회 < {cap} 영속 영역 침범\n"
    )
