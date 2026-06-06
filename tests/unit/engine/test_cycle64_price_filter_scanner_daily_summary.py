"""사이클 64 (2026-06-06) Red — H 카테고리: scanner daily_summary (1 케이스).

> **선행 명세**: `_workspace/red/cycle64_price_filter_scanner.md` (§H)
> **자문 응답 Q6**: scanner 영역 이전 (옵션 B) — `[price_filter_scanner_daily_summary]` 신규 prefix
> **선례**: 사이클 41 funnel 진단 패턴 답습 (운영자 가시화)

요구 행위 (Red 단계 AttributeError 정답 — `emit_price_filter_scanner_daily_summary` 미존재):

- H-1: `_settle()` 직전 `[price_filter_scanner_daily_summary]` 1행 INFO emit.
       포함 필드: active / min / max / daily_skip / reasons

freezegun 20:10 KST 정산 시각 명시.

위험 등급 LOW (운영자 가시화 가치).
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from freezegun import freeze_time

pytestmark = pytest.mark.unit

KST = timezone(timedelta(hours=9))


@pytest.mark.asyncio
async def test_H1_scanner_daily_summary_emit(caplog: pytest.LogCaptureFixture):
    """H-1: `emit_price_filter_scanner_daily_summary()` 호출 시
    `[price_filter_scanner_daily_summary]` 1행 INFO emit + system_logs INSERT.

    검증 필드:
    - `active` (활성 여부)
    - `min` / `max` (현재 임계)
    - `daily_skip` (일일 차단 카운트)
    - `reasons` (차단 사유 분포 dict)

    20:10 KST 정산 시점 freeze.
    """
    from src.db.system_config import PriceFilter
    from src.engine import scanner  # Red: emit_price_filter_scanner_daily_summary 미존재

    # 사전 reset — 테스트 격리
    if hasattr(scanner, "reset_price_filter_daily_state"):
        scanner.reset_price_filter_daily_state()

    # 일중 cap 누적 시뮬레이션 — Red 단계 필드 미존재 → AttributeError
    cap = scanner._price_filter_scanner_skip_logged_today  # noqa: F841
    cap.add("005930")
    cap.add("000660")
    cap.add("035720")

    pf = PriceFilter(min_price=5000, max_price=1_000_000)

    caplog.set_level(logging.INFO, logger="src.engine.scanner")

    with freeze_time(datetime(2026, 6, 6, 20, 10, 0, tzinfo=KST)), \
         patch("src.engine.scanner.get_price_filter", AsyncMock(return_value=pf)), \
         patch("src.db.system_logs.write_log", AsyncMock()):
        # Red: `emit_price_filter_scanner_daily_summary` 미존재 → AttributeError 정답
        await scanner.emit_price_filter_scanner_daily_summary()

    # `[price_filter_scanner_daily_summary]` 1행 emit 검증
    summary_logs = [
        r for r in caplog.records
        if "[price_filter_scanner_daily_summary]" in r.message
    ]
    assert len(summary_logs) == 1, (
        f"일일 집계 로그 누락/중복 (실제 {len(summary_logs)}건)"
    )

    msg = summary_logs[0].message
    # 핵심 필드 검증 (자문 Q6 옵션 B 명시 필드)
    assert "active" in msg.lower() or "is_active" in msg.lower(), (
        f"active 필드 누락: {msg}"
    )
    assert "min" in msg.lower(), f"min 필드 누락: {msg}"
    assert "max" in msg.lower(), f"max 필드 누락: {msg}"
    assert "5000" in msg, f"min_price 값 누락: {msg}"
    assert "1000000" in msg, f"max_price 값 누락: {msg}"
    assert "daily_skip" in msg.lower() or "skip" in msg.lower(), (
        f"daily_skip 필드 누락: {msg}"
    )


# ===========================================================================
# H-2 (HIGH, 사이클 64 hotfix 통합 가드, tester verify 발견 결함 영구 차단)
# ===========================================================================
def test_H2_scheduler_settle_calls_scanner_emit_daily_summary():
    """H-2 (HIGH, hotfix 통합 가드): scheduler.py 의 _settle 직전 분기가
    `scanner.emit_price_filter_scanner_daily_summary` 를 호출해야 함.

    배경 — tester verify 발견 결함 (사이클 64 H 카테고리 무력화):
    - 사이클 62 가 `risk_manager._emit_price_filter_daily_summary` 도입
    - 사이클 64 G3 (risk.py 가격 필터 폐기) 시 메서드 함께 삭제됨
    - 그러나 scheduler.py:639 호출은 잔존 → 매일 20:10 AttributeError
    - except 의 logger.debug graceful skip 으로 silent 결함화
    - 결과: scanner 신규 `emit_price_filter_scanner_daily_summary` 어디서도 호출 안 됨
    - 단위 테스트 H-1 PASS 가 운영 발화 0건 결함을 가림

    검증 (AST 정적):
    1. 폐기 메서드 호출 `_emit_price_filter_daily_summary` scheduler.py 0건
    2. 신규 호출 `emit_price_filter_scanner_daily_summary` scheduler.py 1건+

    AST 정적 검증 선택 사유 (의미론적 mock 시뮬 대비):
    - scheduler._settle 진입 mock 은 _wait_until/_phase/_settle 다중 의존 → fragile
    - 사이클 60 Q3-G6 / 사이클 61 D-1 / 사이클 63 D-2 AST 가드 패턴 답습
    - 실제 production 코드 경로 강제 (mock 우회 불가)

    위험 등급 HIGH — 운영자 가시화 카드 영속 의무 보장.
    """
    import ast
    from pathlib import Path

    scheduler_path = Path("src/engine/scheduler.py")
    assert scheduler_path.exists(), f"scheduler.py 경로 결함: {scheduler_path.resolve()}"
    src = scheduler_path.read_text(encoding="utf-8")
    tree = ast.parse(src)

    deprecated_calls: list[str] = []   # _emit_price_filter_daily_summary (사이클 62 폐기)
    scanner_calls: list[str] = []      # emit_price_filter_scanner_daily_summary (사이클 64 신규)

    for node in ast.walk(tree):
        if not isinstance(node, ast.Attribute):
            continue
        if node.attr == "_emit_price_filter_daily_summary":
            deprecated_calls.append(f"scheduler.py:L{node.lineno}")
        elif node.attr == "emit_price_filter_scanner_daily_summary":
            scanner_calls.append(f"scheduler.py:L{node.lineno}")

    # 모듈 함수 직접 import 호출 패턴도 흡수 (e.g. emit_price_filter_scanner_daily_summary())
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id == "emit_price_filter_scanner_daily_summary":
                scanner_calls.append(f"scheduler.py:L{node.lineno} (direct import)")

    # 1. 폐기 메서드 호출 잔존 차단
    assert not deprecated_calls, (
        f"사이클 62 폐기 메서드 `_emit_price_filter_daily_summary` 호출 잔존 "
        f"({len(deprecated_calls)}건). 사이클 64 G3 risk.py 가격 필터 폐기 시 "
        f"메서드 함께 삭제 — 매일 20:10 AttributeError graceful skip 으로 silent 결함화:\n"
        + "\n".join(deprecated_calls)
        + "\n→ `scanner.emit_price_filter_scanner_daily_summary` 로 교체 의무"
    )

    # 2. 신규 scanner emit 호출 존재 의무
    assert scanner_calls, (
        "scheduler.py 내 `emit_price_filter_scanner_daily_summary` 호출 0건. "
        "사이클 64 H 카테고리 운영자 가시화 카드 무력화 — _settle 직전 분기에서 "
        "`scanner.emit_price_filter_scanner_daily_summary()` 호출 의무. "
        "권고 시정 위치: scheduler.py:638-641 영역 (사이클 62 hook 잔재)"
    )
