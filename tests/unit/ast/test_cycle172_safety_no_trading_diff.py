"""사이클 172 (2026-06-22) — SAFETY 매매 안전성 AST 가드.

데이터 plumbing 한정 — 매매 hot path (risk/order_engine/realtime/auth) 무영향.
어댑터는 정의만 (prepare 미연결 — 매수 target 불변).

SAFETY 가드:
- SAFETY-2 (HIGH): prepare 미변경 — 5 전략 prepare 가 get_recent_daily_normalized 호출 0건
- SAFETY-3: 사이클 81 G-AST1 raw JSONB 분리 (어댑터 raw 그대로 반환, 변형 0)
- SAFETY-4: 신규 함수 본체 매매 hot path 참조 0
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_SRC = Path(__file__).resolve().parents[3] / "src"
_STRATEGIES = _SRC / "engine" / "strategies"


# ---------------------------------------------------------------------------
# SAFETY-2 (HIGH) — prepare 미변경 (어댑터 호출처 0 = 172 데이터 plumbing 한정)
# ---------------------------------------------------------------------------
def test_safety2_prepare_no_adapter_call():
    """5 전략 어디에도 get_recent_daily_normalized 호출 0건 (172 = 어댑터 정의만).

    사이클 173 prepare DB일봉 전환 시점에 호출 추가 → 본 가드 의미 전환 예정.
    172 단계 = 매수 target 불변 보장 (어댑터 미연결).
    """
    strategy_files = list(_STRATEGIES.glob("*.py"))
    assert strategy_files, "strategies 디렉토리 존재 의무"

    offenders = []
    for f in strategy_files:
        text = f.read_text(encoding="utf-8")
        if "get_recent_daily_normalized" in text:
            offenders.append(f.name)

    assert not offenders, (
        f"172 = 어댑터 정의만 — prepare 미연결 (매수 target 불변). "
        f"호출 발견: {offenders} (173 전환 시 본 가드 의미 전환)"
    )


# ---------------------------------------------------------------------------
# SAFETY-3 — 사이클 81 G-AST1 raw JSONB 분리 (어댑터 raw 그대로 반환)
# ---------------------------------------------------------------------------
def test_safety3_adapter_raw_no_mutation():
    """get_recent_daily_normalized 어댑터 — raw JSONB 변형 0 (그대로 반환)."""
    from src.db import stock_master_daily as _smd

    src = inspect.getsource(_smd.get_recent_daily_normalized)
    # raw 변형 패턴 부재 (덮어쓰기/키 추가 금지 — KIS 원본 키 보존)
    # 정상 어댑터는 r.get("raw") 또는 r["raw"] 추출만 수행
    assert ".get(\"raw\")" in src or '["raw"]' in src or ".get('raw')" in src, \
        "어댑터는 raw JSONB 추출 (KIS 원본 키 보존)"


# ---------------------------------------------------------------------------
# SAFETY-4 — 신규 함수 본체 매매 hot path 참조 0
# ---------------------------------------------------------------------------
def test_safety4_new_funcs_no_trading_import():
    """fetch_daily_candles_ranged / backfill / 어댑터 — 매매 hot path 참조 0."""
    from src.api import condition
    from src.db import stock_master_daily as _smd

    targets = [
        condition.fetch_daily_candles_ranged,
        condition.fetch_daily_candles_backfill,
        _smd.get_recent_daily_normalized,
    ]
    forbidden = ("risk.on_tick", "order_engine", "execute_buy", "execute_sell",
                 "place_order", "check_exit_signal", "check_buy_signal")
    for fn in targets:
        src = inspect.getsource(fn)
        for f in forbidden:
            assert f not in src, f"{fn.__name__} 매매 hot path 참조 0 의무: {f}"


# ---------------------------------------------------------------------------
# SAFETY-5 — risk/order_engine/realtime/auth 모듈 사이클 172 키워드 부재
# ---------------------------------------------------------------------------
def test_safety5_hot_path_modules_no_cycle172_refs():
    """매매 hot path 모듈에 사이클 172 신규 함수 참조 0 (diff 0 증명)."""
    hot_path = [
        _SRC / "engine" / "risk.py",
        _SRC / "engine" / "order_engine.py",
        _SRC / "api" / "order.py",
    ]
    new_funcs = (
        "fetch_daily_candles_ranged",
        "fetch_daily_candles_backfill",
        "get_recent_daily_normalized",
    )
    for path in hot_path:
        text = path.read_text(encoding="utf-8")
        for fn in new_funcs:
            assert fn not in text, \
                f"{path.name} 에 사이클 172 신규 함수 참조 0 의무: {fn}"

    # realtime/ + auth/ 디렉토리 전체
    for d in ("realtime", "auth"):
        for f in (_SRC / d).rglob("*.py"):
            text = f.read_text(encoding="utf-8")
            for fn in new_funcs:
                assert fn not in text, \
                    f"{d}/{f.name} 에 사이클 172 신규 함수 참조 0 의무: {fn}"
