"""사이클 101 G-AGE1 — `[stock_master_age_warning]` 7일 이상 WARNING (MEDIUM).

명세 (`_workspace/red/cycle101_market_cap_full_universe_load.md`):

**domain-expert A5 영속 (사이클 89 적시성 손실 보강)**:
- 사이클 101 = 매일 20:00:05 일괄 단독 영역 → 적시성 손실 (5분 주기 영구 폐기)
- 신규 IPO 종목 영역 = 전일 적재 영역 부재 = `bfdy_clpr=0` graceful 통과 위험
- `[stock_master_age_warning] ticker=X loaded_at=Y age_days=Z` 7일 이상 WARNING emit 의무

검증 매트릭스:
- G-AGE1-A: `_emit_stock_master_age_warning` 또는 동급 헬퍼 함수 영속 (Red = 부재)
- G-AGE1-B: 7일 이상 age → WARNING `[stock_master_age_warning]` emit 영속
- G-AGE1-C: 7일 미만 age → emit 0건 영속 (cap 영역)

Red 상태: 신규 함수 부재.
Green (backend-dev): scanner 또는 scheduler 영역에 7일 age 체크 + WARNING emit 영속.

영속 의무:
- 사이클 89 적시성 손실 보강 (domain-expert A5)
- 사이클 102+ 운영자 수동 적재 영역 후속 카드 인계
- 매매 안전성 영역 영향 0 (로깅 영역만)
"""
from __future__ import annotations

import logging

import pytest

pytestmark = pytest.mark.unit


def test_g_age1_a_stock_master_age_warning_helper_exists() -> None:
    """G-AGE1-A: `_emit_stock_master_age_warning` 또는 동급 헬퍼 함수 영속 (MEDIUM).

    Red 상태: 신규 함수 부재.
    Green (backend-dev): scanner 또는 stock_master_metrics 영역에 정의.
    """
    import src.engine.scanner as scanner_mod
    import src.engine.stock_master_metrics as metrics_mod

    # 다음 중 하나의 위치에 정의 영속:
    candidates = [
        getattr(scanner_mod, "_emit_stock_master_age_warning", None),
        getattr(metrics_mod, "emit_stock_master_age_warning", None),
        getattr(metrics_mod, "_emit_stock_master_age_warning", None),
        getattr(scanner_mod, "emit_stock_master_age_warning", None),
    ]

    assert any(c is not None for c in candidates), (
        "\n사이클 101 G-AGE1-A Red — `_emit_stock_master_age_warning` 부재.\n"
        "  Green (backend-dev): scanner.py 또는 stock_master_metrics.py 영역에 정의 의무.\n"
        "  domain-expert A5 영속: 사이클 89 적시성 손실 보강 의무.\n"
        "  emit prefix: [stock_master_age_warning] ticker=X loaded_at=Y age_days=Z"
    )


def test_g_age1_b_seven_days_emits_warning(caplog: pytest.LogCaptureFixture) -> None:
    """G-AGE1-B: 7일 이상 age → WARNING emit 영속 (MEDIUM).

    검증 매트릭스 (domain-expert A5 영속):
    - age_days >= 7 → `[stock_master_age_warning]` WARNING emit
    - age_days < 7 → emit 0건

    Red 상태: 신규 함수 부재 또는 emit 0건.
    Green (backend-dev): 7일 임계 + WARNING emit 영속.
    """
    import src.engine.scanner as scanner_mod
    import src.engine.stock_master_metrics as metrics_mod

    helper = (
        getattr(scanner_mod, "_emit_stock_master_age_warning", None)
        or getattr(metrics_mod, "emit_stock_master_age_warning", None)
        or getattr(metrics_mod, "_emit_stock_master_age_warning", None)
        or getattr(scanner_mod, "emit_stock_master_age_warning", None)
    )
    if helper is None:
        pytest.fail("G-AGE1-B Red — 헬퍼 부재 (G-AGE1-A 영속)")

    caplog.set_level(logging.WARNING, logger="src.engine.scheduler")

    import asyncio
    import inspect

    # 8일 age — WARNING emit 의무
    async def _exec():
        if inspect.iscoroutinefunction(helper):
            await helper(ticker="005930", age_days=8)
        else:
            helper(ticker="005930", age_days=8)

    asyncio.run(_exec())

    warning_records = [
        rec for rec in caplog.records
        if "[stock_master_age_warning]" in rec.getMessage()
        and rec.levelno >= logging.WARNING
    ]
    assert len(warning_records) >= 1, (
        f"\n사이클 101 G-AGE1-B 위반 — `[stock_master_age_warning]` WARNING emit 0건:\n"
        f"  기대: age_days=8 → WARNING emit ≥1건\n"
        f"  실제: {len(warning_records)}건\n"
        f"  Green (backend-dev): logger.warning('[stock_master_age_warning] ...') 영속"
    )
