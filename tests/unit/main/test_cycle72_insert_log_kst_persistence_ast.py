"""사이클 72 G-8 — `_insert_log_to_db` KST 강제 영속 (Red 단계).

사이클 65 H2-bis 영속 회귀 가드 강화:
- `src/main.py:126` 의 `datetime.now(KST).isoformat()` 패턴 영속
- `+09:00` suffix 영속 (KST timestamp DB 저장 보장)

Red 단계 = 사이클 65 H2-bis 영속 → **PASS 보장** (이미 시정됨).
Green 단계 후에도 PASS 유지 — 사이클 72 옵션 A' / D / G-6 / G-7 시정이 본 영속 깨뜨리지 않음.

본 가드 의미:
- 사이클 65 hotfix 가 silent 회귀 (UTC 로 되돌아감) 영구 차단
- 사이클 72 시정이 `_insert_log_to_db` 본체를 건드리면 즉시 FAIL 발화
"""
from __future__ import annotations

import ast
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

_MAIN_PATH = Path(__file__).resolve().parents[3] / "src" / "main.py"


@pytest.mark.xfail(
    reason="사이클M3b — _insert_log_to_db 가 async def 로 전환(pg.execute await 의무) + "
    "isoformat() str 대신 datetime.now(KST) 객체 바인딩(asyncpg TIMESTAMPTZ 계약). "
    "동일 KST/타임스탬프 계약은 test_cycleM3b_main_seam_pg.py::"
    "test_insert_log_helper_uses_pg_execute_kst 가 이관 단언.",
    strict=False,
)
def test_g_8_insert_log_to_db_uses_kst_isoformat() -> None:
    """G-8: `_insert_log_to_db` 가 `datetime.now(KST).isoformat()` 패턴 사용 영속."""
    source = _MAIN_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)

    # `_insert_log_to_db` 함수 찾기 (동기 FunctionDef — M3b 이후 AsyncFunctionDef 로 전환)
    func_def = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "_insert_log_to_db":
            func_def = node
            break
    assert func_def is not None, (
        "src/main.py 에 `_insert_log_to_db` 함수 미정의 — 사이클 65 H2-bis 영속 깨짐"
    )

    # 본체에 `datetime.now(KST).isoformat()` 패턴 (정규식 추출)
    func_source = ast.get_source_segment(source, func_def) or ""
    assert "datetime.now(KST).isoformat()" in func_source, (
        f"`_insert_log_to_db` 본체에 `datetime.now(KST).isoformat()` 부재 — "
        f"사이클 65 hotfix H2-bis 회귀 (UTC 저장 결함 재발).\n"
        f"본체:\n{func_source}"
    )

    # 추가: timestamp 키가 payload 에 포함되는지 확인
    assert re.search(r'["\']timestamp["\']\s*:', func_source), (
        "`_insert_log_to_db` payload 에 'timestamp' 키 부재 — "
        "KST timestamp 강제 영속 깨짐"
    )


def test_g_8_kst_tz_constant_is_plus_9_hours() -> None:
    """G-8 보강: src/main.py `KST` 상수가 `+09:00` 임을 정적 검증.

    사이클 53 KST `+09:00` 패턴 영속.
    """
    source = _MAIN_PATH.read_text(encoding="utf-8")
    # `KST = timezone(timedelta(hours=9))` 패턴
    assert re.search(
        r"KST\s*=\s*timezone\s*\(\s*timedelta\s*\(\s*hours\s*=\s*9\s*\)\s*\)",
        source,
    ), (
        "src/main.py 에 `KST = timezone(timedelta(hours=9))` 정의 부재 — "
        "사이클 65 hotfix H2-bis 영속 깨짐 (KST `+09:00` 회귀)"
    )

    # 추가: 실제 datetime.now(KST).isoformat() 가 +09:00 suffix 를 생성하는지 동적 검증
    from src.main import KST as main_kst  # type: ignore[import-untyped]
    iso = datetime.now(main_kst).isoformat()
    assert iso.endswith("+09:00"), (
        f"`datetime.now(KST).isoformat()` = {iso!r} — "
        f"`+09:00` suffix 누락 (KST tzinfo 결함)"
    )
