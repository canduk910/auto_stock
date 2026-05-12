"""구독 종목 출처별 카운터 로깅 (Phase B).

결함 배경: 2026-05-11 운영. system_logs 패턴 분석 결과
    "실시간 시세 구독 완료: 28종목 (모멘텀: 7, 기타: 23)"
"기타 23"이 무엇인지(VB? LTV? swing? 보유?) 즉시 모름. 알고 보니 23은 모두 donchian_swing
고정 유니버스였고 **VB/LTV 후보는 0건**이었으나 로그상 식별 불가능했다.

본 테스트는 `subscribe_filtered_stocks(tickers, extra_tickers, source_counts=...)` 가 다음
출처별 카운터를 로그에 노출함을 검증한다:

    [scanner] 실시간 시세 구독 완료: total=N (vb=A, ltv=B, swing=C, momentum=D, positions=E)

- `total` 은 합집합(dedupe) 후 실제 구독 개수
- `vb/ltv/swing/momentum/positions` 는 합집합 *전* 원본 출처별 개수 (중복 가능)
- 영문 라벨 유지 (Grafana/Loki 안정성)
- `source_counts=None` 이면 기존 "기타" 라벨 fallback (외부 호출자 호환성)
"""

from __future__ import annotations

import logging
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from src.engine import scanner as scanner_module

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _patch_ws_subscribe():
    """kis_ws.subscribe 를 호출 흔적만 남기는 AsyncMock 으로 교체."""
    with patch.object(scanner_module.kis_ws, "subscribe", new=AsyncMock()) as mock:
        yield mock


# ---------------------------------------------------------------------------
# Case A: 5개 카운터 모두 활성, 중복 없음
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_source_counts_all_labels_present(caplog):
    """VB/LTV/swing/momentum/positions 모두 분리 노출되어야 한다."""
    caplog.set_level(logging.INFO, logger="src.engine.scanner")

    source_counts = {
        "vb": 2,
        "ltv": 0,
        "swing": 3,
        "momentum": 0,
        "positions": 1,
    }
    # tickers 인자는 momentum 후보, extra 인자는 합집합 보강
    await scanner_module.subscribe_filtered_stocks(
        [],
        extra_tickers=["A", "B", "S1", "S2", "S3", "P1"],
        source_counts=source_counts,
    )

    msg = "\n".join(record.message for record in caplog.records)
    assert "vb=2" in msg
    assert "ltv=0" in msg
    assert "swing=3" in msg
    assert "momentum=0" in msg
    assert "positions=1" in msg
    assert "total=6" in msg
    # 기존 라벨 제거 확인
    assert "모멘텀:" not in msg
    assert "기타:" not in msg


# ---------------------------------------------------------------------------
# Case B: VB/LTV 0건도 명시적으로 노출 (어제 사고 즉시 진단 가능)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_source_counts_zero_values_explicit(caplog):
    """vb=0, ltv=0 이어도 라벨이 명시적으로 노출되어야 한다 (어제 사고 케이스)."""
    caplog.set_level(logging.INFO, logger="src.engine.scanner")

    source_counts = {
        "vb": 0,
        "ltv": 0,
        "swing": 23,
        "momentum": 7,
        "positions": 0,
    }
    await scanner_module.subscribe_filtered_stocks(
        ["005930", "000660", "035420", "035720", "005380", "000270", "068270"],
        extra_tickers=[f"S{i}" for i in range(23)],
        source_counts=source_counts,
    )

    msg = "\n".join(record.message for record in caplog.records)
    assert "vb=0" in msg, "VB 0건도 명시적으로 노출되어야 어제 사고 즉시 진단 가능"
    assert "ltv=0" in msg, "LTV 0건도 명시적으로 노출되어야 어제 사고 즉시 진단 가능"
    assert "swing=23" in msg
    assert "momentum=7" in msg
    assert "positions=0" in msg
    assert "total=30" in msg


# ---------------------------------------------------------------------------
# Case C: 출처 간 중복 종목 → total 은 dedupe 카운트, 출처별은 원본 유지
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_source_counts_duplicates_unique_total(caplog):
    """동일 종목이 VB+swing 양쪽에 있어도 total 은 dedupe 후 카운트."""
    caplog.set_level(logging.INFO, logger="src.engine.scanner")

    # "005930" 이 VB / swing 양쪽에 등장. 합집합 후엔 1번만 카운트.
    source_counts = {
        "vb": 2,        # 원본 ["005930", "000660"]
        "ltv": 0,
        "swing": 2,     # 원본 ["005930", "035420"]
        "momentum": 0,
        "positions": 0,
    }
    await scanner_module.subscribe_filtered_stocks(
        [],
        extra_tickers=["005930", "000660", "035420"],  # dedupe 후 3개
        source_counts=source_counts,
    )

    msg = "\n".join(record.message for record in caplog.records)
    assert "vb=2" in msg, "출처별 카운트는 dedupe 전 원본 유지"
    assert "swing=2" in msg, "출처별 카운트는 dedupe 전 원본 유지"
    assert "total=3" in msg, "total 은 합집합 후 dedupe 카운트"


# ---------------------------------------------------------------------------
# Case D: source_counts=None → 기존 "기타" 라벨 fallback (외부 호환성)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_source_counts_none_fallback_compat(caplog):
    """source_counts 인자를 주지 않으면 기존 표기로 동작 (외부 호출자 호환성).

    내부 호출자 3곳은 모두 source_counts dict 를 넘기지만, 외부 도구/임시 디버깅에서
    구 시그니처로 호출해도 깨지지 않아야 한다.
    """
    caplog.set_level(logging.INFO, logger="src.engine.scanner")

    await scanner_module.subscribe_filtered_stocks(
        ["005930", "000660"],
        extra_tickers=["035420", "035720"],
        # source_counts 인자 생략
    )

    msg = "\n".join(record.message for record in caplog.records)
    # fallback 경로는 모멘텀/기타 표기로 동작 — 외부 호환성 유지
    assert ("모멘텀:" in msg) or ("momentum_legacy" in msg) or ("other" in msg), (
        "source_counts=None 이면 기존 표기 또는 호환 라벨로 fallback 해야 함"
    )
    # 합집합 종목 수는 어떤 형식이든 노출되어야 한다
    assert "4" in msg


# ---------------------------------------------------------------------------
# Case E: source_counts dict 가 빈 dict / 일부 키 누락 — 누락 키는 0 처리
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_source_counts_missing_keys_default_zero(caplog):
    """키 누락 시 0 으로 처리 (KeyError 발생 금지)."""
    caplog.set_level(logging.INFO, logger="src.engine.scanner")

    # vb 만 들어 있는 dict
    source_counts = {"vb": 5}
    await scanner_module.subscribe_filtered_stocks(
        [],
        extra_tickers=["A", "B", "C", "D", "E"],
        source_counts=source_counts,
    )

    msg = "\n".join(record.message for record in caplog.records)
    assert "vb=5" in msg
    assert "ltv=0" in msg
    assert "swing=0" in msg
    assert "momentum=0" in msg
    assert "positions=0" in msg
    assert "total=5" in msg
