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
#
# 사이클 173 (2026-06-22) 의미 전환 (사이클 66 K-2 패턴): 172 docstring 이 명시한
# "173 전환 시 본 가드 의미 전환 예정" 실현. 173 = 5 전략 prepare 가 어댑터를
# 연결 (매수 target 행위 보존 + 동등성 게이트). → 호출 발생이 정상.
# 173 의 호출 검증은 tests/unit/engine/strategies/test_cycle173_prepare_db_equivalence.py
# (AST: 5 전략 get_recent_daily_normalized 호출 + min_required= 명시) 가 영속.
# ---------------------------------------------------------------------------
@pytest.mark.xfail(
    strict=False,
    reason="사이클 173 — 5 전략 prepare 어댑터 연결 (172 docstring 명시 전환, 호출 발생 정상)",
)
def test_safety2_prepare_no_adapter_call():
    """[의미 전환 173] 172 = 어댑터 정의만 (호출 0) → 173 = prepare 연결 (호출 발생).

    173 전환으로 5 전략이 get_recent_daily_normalized 호출 → 본 가드 xfail 전환.
    173 호출 검증 = test_cycle173_prepare_db_equivalence.py (AST min_required 명시).
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
    """어댑터 경로 — raw JSONB 변형 0 (그대로 추출 반환).

    사이클 173 (2026-06-22): raw 추출이 어댑터 본체 → `_extract_raw` 헬퍼로 위임
    (락/신선도 게이트 추가 + 추출 DRY). raw 추출/보존 의무는 헬퍼 + 어댑터 경로
    전체에서 검증 (변형 0 영속).
    """
    from src.db import stock_master_daily as _smd

    # 어댑터 본체 + raw 추출 헬퍼 (_extract_raw) 합산 — raw 추출 존재 + 변형 0
    adapter_src = inspect.getsource(_smd.get_recent_daily_normalized)
    helper_src = inspect.getsource(_smd._extract_raw)
    combined = adapter_src + "\n" + helper_src

    assert ".get(\"raw\")" in combined or '["raw"]' in combined or ".get('raw')" in combined, \
        "어댑터 경로는 raw JSONB 추출 (KIS 원본 키 보존, 헬퍼 위임 포함)"
    # raw 변형 (덮어쓰기/키 주입) 패턴 부재 — KIS 원본 키 보존 (사이클 81 G-AST1)
    assert 'raw["' not in combined and "raw[" not in combined.replace('r.get("raw")', ''), \
        "raw JSONB 키 주입/덮어쓰기 금지 (KIS 원본 키 보존)"


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
