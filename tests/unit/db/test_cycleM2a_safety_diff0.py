"""사이클 M2a (Red) — 매매 안전성 8영역 diff 0 + 호출부 미변경 불변식.

승인 계획: `~/.claude/plans/partitioned-kindling-lollipop.md` (단계 2 — 매매 hot path, HIGH).

M2a = system_config / trade_history 를 pg.* 로 전환하되 **함수 계약(시그니처·반환형·graceful)
100% 보존** → 소비처(risk/order_engine/scheduler 등 8영역)는 db 함수만 호출하므로 diff 0.

이 파일 = 불변식 가드:
- 매매 안전성 8영역 git diff 0 (system_config/trade_history 자체는 8영역 밖 = src/db/).
- 호출부가 여전히 동일 함수 계약을 호출 (함수 심볼 존재 = 시그니처 계약 보존 증거).

Red 단계: 8영역 미변경 + 함수 심볼 존재 = 대부분 불변식 PASS. Green 후에도 유지되어야 함
(전환은 db 모듈 내부 구현 교체일 뿐 계약 불변). M2a 가 8영역을 건드리면 즉시 FAIL.
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
@pytest.mark.skip(reason="RDS 이전(M0~M6) 완료 은퇴 — 워킹트리 git status 기반 8영역 가드는 마이그레이션 종료 후 dead(커밋 시 항상 통과, 로컬 미커밋 8영역 작업마다 오발화). 실 8영역 보호는 각 변경의 git diff 규율로 대체.")
def test_safety_8_areas_unchanged():
    """M2a 는 system_config/trade_history 내부 구현 전환 → 8영역 git diff 0."""
    changed = _git_changed_files()
    violations = [
        f for f in changed
        if any(f == p or f.startswith(p) for p in _SAFETY_PATHS)
    ]
    assert not violations, (
        "M2a 는 매매 안전성 8영역 diff 0 이어야 함 (함수 계약 보존 → 호출부 무변경). 변경 감지:\n  "
        + "\n  ".join(violations)
    )


# ---------------------------------------------------------------------------
# 호출부 계약 보존 — 소비처가 여전히 동일 함수를 호출 (심볼 존재 = 계약 유지)
# ---------------------------------------------------------------------------
def test_order_engine_still_calls_trade_history_contract():
    """order_engine 이 trade_history 의 계약 함수를 여전히 호출 (전환 후 계약 불변 증거).

    함수 시그니처가 보존되므로 호출부 텍스트가 변할 이유 없음 = diff 0 근거.
    """
    src = (_REPO / "src" / "engine" / "order_engine.py").read_text(encoding="utf-8")
    # 매매 hot path 핵심 호출 계약 (전환 전후 불변)
    assert "update_trade_status" in src or "trade_history" in src, (
        "order_engine 의 trade_history 계약 호출이 사라짐 — 계약 변경 신호."
    )


def test_scheduler_still_calls_system_config_contract():
    """scheduler/boot 이 system_config 계약 함수를 여전히 호출 (cash_usage_ratio 등)."""
    boot = (_REPO / "src" / "engine" / "boot_manager.py").read_text(encoding="utf-8")
    sched = (_REPO / "src" / "engine" / "scheduler.py").read_text(encoding="utf-8")
    combined = boot + sched
    assert "get_cash_usage_ratio" in combined or "system_config" in combined, (
        "boot/scheduler 의 system_config 계약 호출이 사라짐 — 계약 변경 신호."
    )


def test_trade_history_sync_functions_exist():
    """sync 함수(dedupe 없음/CANCELLED 제외) 심볼 보존 — scheduler _sync_orders_to_db 계약."""
    from src.db import trade_history

    assert hasattr(trade_history, "get_today_buy_trades_for_sync"), (
        "get_today_buy_trades_for_sync 심볼 삭제 금지 (사이클 30 sync 계약)."
    )
    assert hasattr(trade_history, "get_today_sell_trades_for_sync"), (
        "get_today_sell_trades_for_sync 심볼 삭제 금지 (사이클 30 sync 계약)."
    )
    # 포지션 복구용(dedupe)과 절대 혼용 금지 — 별도 심볼 병존
    assert hasattr(trade_history, "get_today_buy_trades"), (
        "포지션 복구용 get_today_buy_trades (dedupe) 병존 — sync 와 구분 계약."
    )


def test_system_config_hotpath_read_functions_exist():
    """매수 파라미터 read 함수 심볼 보존 (계약 시그니처 불변 증거)."""
    from src.db import system_config

    for fn in (
        "get_cash_usage_ratio",
        "get_auto_regime_adjust",
        "get_buy_block_mode",
        "get_buy_block_thresholds",
    ):
        assert hasattr(system_config, fn), f"{fn} 심볼 삭제 금지 (매수 파라미터 계약)."
