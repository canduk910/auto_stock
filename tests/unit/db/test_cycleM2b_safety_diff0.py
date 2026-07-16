"""사이클 M2b (Red) — 매매 안전성 8영역 diff 0 + 호출부(scanner/strategies) 미변경 불변식.

승인 계획: `~/.claude/plans/partitioned-kindling-lollipop.md` (단계 2 — 매매 hot path, HIGH).

M2b = stock_master / stock_master_daily 를 pg.* 로 전환하되 **함수 계약(시그니처·반환형·graceful)
100% 보존** → 소비처(scanner/strategies)는 db 함수만 호출하므로 diff 0.

이 파일 = 불변식 가드:
- 매매 안전성 8영역 git diff 0 (stock_master/stock_master_daily 자체는 8영역 밖 = src/db/).
- 호출부(scanner/strategies)가 여전히 동일 함수 계약을 호출 (심볼/텍스트 존재 = 계약 보존 증거).

Red 단계: 8영역 미변경 + 함수 심볼 존재 = 대부분 불변식 PASS. Green 후에도 유지되어야 함
(전환은 db 모듈 내부 구현 교체일 뿐 계약 불변). M2b 가 8영역/scanner/strategies 를 건드리면 즉시 FAIL.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_REPO = Path(__file__).resolve().parents[3]

# 매매 안전성 8영역 (CLAUDE.md 명문화)
_SAFETY_PATHS = (
    "src/engine/risk.py",
    "src/engine/order_engine.py",
    "src/realtime/",
    "src/auth/",
    "src/api/order.py",
    "src/engine/session.py",
    "src/engine/scanner.py",
    "src/engine/strategy_registry.py",
)


def _git_changed_files() -> list[str]:
    out = subprocess.run(
        ["git", "-C", str(_REPO), "status", "--porcelain"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    files: list[str] = []
    for line in out.splitlines():
        if not line.strip():
            continue
        path = line[3:].strip()
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        files.append(path)
    return files


# ---------------------------------------------------------------------------
# 매매 안전성 8영역 diff 0 (불변식)
# ---------------------------------------------------------------------------
def test_safety_8_areas_unchanged():
    """M2b 는 stock_master/stock_master_daily 내부 구현 전환 → 8영역 git diff 0."""
    changed = _git_changed_files()
    violations = [
        f for f in changed
        if any(f == p or f.startswith(p) for p in _SAFETY_PATHS)
    ]
    assert not violations, (
        "M2b 는 매매 안전성 8영역 diff 0 이어야 함 (함수 계약 보존 → 호출부 무변경). 변경 감지:\n  "
        + "\n  ".join(violations)
    )


# ---------------------------------------------------------------------------
# 호출부 계약 보존 — scanner/strategies 가 여전히 db 함수를 호출 (텍스트 존재 = 계약 유지)
# ---------------------------------------------------------------------------
def test_scanner_still_calls_stock_master_contract():
    """scanner 가 stock_master 계약 함수(list_by_filter 등)를 여전히 호출 (전환 후 계약 불변 증거)."""
    src = (_REPO / "src" / "engine" / "scanner.py").read_text(encoding="utf-8")
    assert "list_by_filter" in src or "stock_master" in src, (
        "scanner 의 stock_master 계약 호출이 사라짐 — 계약 변경 신호."
    )


def test_strategies_still_call_daily_adapter_contract():
    """5 전략(VB/LTV/donchian/BFB/VCP) 이 get_recent_daily_normalized 어댑터 계약을 여전히 호출.

    prepare 일봉 소스 = 매수 target hot path. 텍스트가 변할 이유 없음 = diff 0 근거.
    """
    strat_dir = _REPO / "src" / "engine" / "strategies"
    combined = "".join(
        p.read_text(encoding="utf-8")
        for p in strat_dir.glob("*.py")
    )
    assert "get_recent_daily_normalized" in combined, (
        "전략 prepare 의 일봉 어댑터 호출(get_recent_daily_normalized)이 사라짐 — 계약 변경 신호."
    )


def test_list_by_filter_signature_preserved():
    """list_by_filter 시그니처(핵심 인자) 보존 — 매수 유니버스 계약 불변."""
    import inspect

    from src.db import stock_master

    sig = inspect.signature(stock_master.list_by_filter)
    params = sig.parameters
    for name in (
        "market", "min_market_cap", "min_trade_amount", "exclude_tickers",
        "nxt_tradable", "is_kospi200", "is_kosdaq150", "limit", "return_stage_counts",
    ):
        assert name in params, f"list_by_filter 인자 {name} 삭제 금지 (매수 유니버스 계약)."


def test_daily_hotpath_functions_exist():
    """일봉 hot path 핵심 함수 심볼 보존 (계약 시그니처 불변 증거)."""
    from src.db import stock_master_daily as smd

    for fn in (
        "get_recent_daily_normalized",  # prepare 일봉 소스
        "get_recent_daily",
        "get_donchian_high",
        "get_atr",
        "upsert_batch",
        "purge_old_rows",
        "max_bas_dd",
    ):
        assert hasattr(smd, fn), f"{fn} 심볼 삭제 금지 (일봉 hot path 계약)."


def test_stock_master_universe_functions_exist():
    """매수 유니버스 함수 심볼 보존."""
    from src.db import stock_master

    for fn in (
        "list_by_filter",
        "list_paged_by_filter",
        "get_stats",
        "upsert_one",
        "get",
        "is_stale",
        "count_active",
        "upsert_master_raw",
        "get_master_raw",
    ):
        assert hasattr(stock_master, fn), f"{fn} 심볼 삭제 금지 (매수 유니버스 계약)."
