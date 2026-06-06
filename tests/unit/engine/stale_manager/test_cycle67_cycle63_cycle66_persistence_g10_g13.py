"""사이클 67 Red — 사이클 63 Q4=B + 사이클 66 시정 영속 G-10~G-13 (4 케이스).

> **설계 카드**: `_workspace/cycle67_stale_manager_decomposition_design_card.md`
> **자문 응답**: `_workspace/cycle67_stale_manager_decomposition_domain_response.md`

G-10~G-13 = 사이클 63 Q4=B + 사이클 66 시정 영속 검증:
- G-10: `emit_stale_session_detail(scheduler, ...)` 시그너처 영속
        (사이클 63 Q4=B 직접 호출 영속, *유일한 사이클 60 답습 안 함 영역*)
- G-11: `resubscribe_stale_priority` 본체에 사이클 66 시정 영속
        (HIGH 우선 + cap 후 LOW, `high_targets` / `low_targets` 변수명 영속)
- G-12: try/except 4중 가드 영속 (사이클 66 Q2 본체 패턴)
- G-13: caplog `set_level(logger="src.engine.scheduler")` 영속
        (분해 후 4 sub-module 동일 logger → caplog 일관성, 1 테스트 케이스 실행)

Red 시점 결과:
- G-10, G-11, G-12: FAIL (stale_watcher_core 미존재 또는 분해 후 시그너처/본체 변경 위험)
- G-13: 분해 전엔 `src.engine.stale_manager` logger 발화 — sub-module 분해 후
        `src.engine.scheduler` binding 영속 필수 (자문 §4 Q4 caplog logger 갱신 권고).
        분해 전 본 테스트는 `src.engine.scheduler` logger 발화 검증 시도 → 사이클 66 본체가
        `src.engine.scheduler` logger 사용 중이므로 PASS 가능 (사이클 66 K-10 패턴 동형).

Green 시점 결과: 전수 PASS.
"""
from __future__ import annotations

import ast
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from freezegun import freeze_time

pytestmark = pytest.mark.unit

KST = timezone(timedelta(hours=9))
REPO_ROOT = Path(__file__).resolve().parents[4]
SRC_ENGINE = REPO_ROOT / "src" / "engine"


# ===========================================================================
# G-10 — emit_stale_session_detail(scheduler, ...) 시그너처 영속 (Q4=B)
# ===========================================================================
def test_G10_emit_stale_session_detail_signature_persisted():
    """G-10 (사이클 63 Q4=B 영속): `emit_stale_session_detail(scheduler, stale_tickers, now)`
    시그너처 영속 (3 인자, 첫 인자=scheduler).

    Q4=B = 사이클 60 답습 안 하는 *유일 영역* — `check_and_resubscribe_stale` 본체가
    wrapper 우회 + 모듈 함수 직접 호출 (1 hop 단축). 시그너처 변경 시 cross-module call
    깨짐 + Q4=B 영속 위반.

    AST 정적 검증:
    - `stale_diagnostics.py` (또는 facade 영속 stale_manager.py) 의
      `emit_stale_session_detail` 함수 정의 발견 → arg 수 ≥ 3 (scheduler / stale_tickers / now)
      + 첫 arg 이름 == 'scheduler' (positional 또는 키워드).

    Red 단계: stale_diagnostics 미존재 → stale_manager.py 본체 검증으로 자연 PASS.
    Green 단계: stale_diagnostics.py 의 함수 시그너처 영속 = PASS.
    """
    # 분해 후엔 stale_diagnostics.py 가 진실의 원천. 분해 전엔 stale_manager.py.
    candidate_paths = [
        SRC_ENGINE / "stale_diagnostics.py",
        SRC_ENGINE / "stale_manager.py",
    ]
    source = None
    chosen_path = None
    for p in candidate_paths:
        if p.exists():
            source = p.read_text(encoding="utf-8")
            chosen_path = p
            break

    assert source is not None, "stale_diagnostics.py / stale_manager.py 모두 미존재"

    tree = ast.parse(source)
    target = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "emit_stale_session_detail":
            target = node
            break

    assert target is not None, (
        f"{chosen_path}: `emit_stale_session_detail` 함수 정의 누락. "
        f"사이클 63 Q4=B 영속 의무 위반"
    )

    arg_names = [a.arg for a in target.args.args]
    assert len(arg_names) >= 3, (
        f"`emit_stale_session_detail` 인자 수 = {len(arg_names)} (기대 ≥ 3). "
        f"시그너처: ({', '.join(arg_names)}). Q4=B cross-module call 깨짐."
    )
    assert arg_names[0] == "scheduler", (
        f"첫 인자명 = '{arg_names[0]}' (기대 'scheduler'). "
        f"사이클 60 A1 패턴 (scheduler 첫 인자) 영속 위반."
    )


# ===========================================================================
# G-11 — 사이클 66 시정 본체 변수명 영속 (high_targets / low_targets)
# ===========================================================================
def test_G11_resubscribe_stale_priority_cycle66_fix_variable_names_persisted():
    """G-11 (사이클 66 시정 영속): `resubscribe_stale_priority` 본체에
    `high_targets` / `low_targets` 변수 + `high_tickers` set 영속.

    사이클 66 시정 본체 (priority 분리 *먼저*, cap *나중*):
        high_targets = [t for t in stale_tickers if t in high_tickers]
        low_targets = [t for t in stale_tickers if t not in high_tickers]
        targets = high_targets + low_targets[: max(0, cap - len(high_targets))]

    분해 후 본체 위치 = `stale_watcher_core.py::resubscribe_stale_priority`.

    AST 검증:
    1. 변수 `high_tickers` (set) 정의 영속
    2. 변수 `high_targets` (list) 정의 영속
    3. 변수 `low_targets` (list) 정의 영속

    Red 단계: stale_watcher_core 미존재 → stale_manager.py 본체 검증으로 자연 PASS
              (사이클 66 시정 본체가 stale_manager.py 잔존).
    Green 단계: stale_watcher_core.py 본체 영속 = PASS.
    """
    candidate_paths = [
        SRC_ENGINE / "stale_watcher_core.py",
        SRC_ENGINE / "stale_manager.py",
    ]
    source = None
    chosen_path = None
    for p in candidate_paths:
        if p.exists():
            source = p.read_text(encoding="utf-8")
            chosen_path = p
            break

    assert source is not None, "stale_watcher_core.py / stale_manager.py 모두 미존재"

    tree = ast.parse(source)
    target = None
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "resubscribe_stale_priority":
            target = node
            break

    assert target is not None, (
        f"{chosen_path}: `resubscribe_stale_priority` 함수 정의 누락. "
        f"사이클 63 A3 이주 영속 위반"
    )

    func_source = ast.unparse(target)
    assert "high_tickers" in func_source, (
        "`high_tickers` set 변수 누락. 사이클 66 시정 본체 패턴 위반."
    )
    assert "high_targets" in func_source, (
        "`high_targets` list 변수 누락. 사이클 66 시정 = priority 분리 *먼저* 패턴 위반."
    )
    assert "low_targets" in func_source, (
        "`low_targets` list 변수 누락. 사이클 66 시정 = LOW 잔여 cap 채움 패턴 위반."
    )
    # 결함 패턴 (사이클 63 K-2) 영구 차단
    assert "stale_tickers[:cap]" not in func_source, (
        "`stale_tickers[:cap]` 패턴 잔존 = 사이클 63 결함 (priority 분리 *전* cap 적용). "
        "사이클 66 시정 의무 위반 — 사이클 29 005935 사고 패턴 재현 위험."
    )


# ===========================================================================
# G-12 — try/except 4중 가드 영속 (사이클 66 Q2 본체 패턴)
# ===========================================================================
def test_G12_high_tickers_construction_try_except_quadruple_guard():
    """G-12 (사이클 66 Q2 try/except 4중 가드 영속): `high_tickers.update(...)` 호출이
    try 블록 내부.

    사이클 66 Q2 본체 패턴:
        high_tickers: set[str] = set()
        try:                                  # outer try
            for s in scheduler.registry.all():
                try:                          # inner try (positions)
                    high_tickers.update(s.state.positions.keys())
                except Exception:
                    pass
        except Exception:
            pass
        try:                                  # NDC try
            high_tickers.update(t for (t, _sid) in scheduler._pending_next_day_clear)
        except Exception:
            pass

    AST 검증:
    - `high_tickers.update(...)` 호출 노드 모두가 ast.Try 블록 *하위* 위치
    - 최소 2회 update 호출 (positions + NDC)

    Red 단계: stale_watcher_core 미존재 → stale_manager.py 검증 자연 PASS.
    Green 단계: 사이클 66 본체 패턴 이주 후 영속 = PASS.
    """
    candidate_paths = [
        SRC_ENGINE / "stale_watcher_core.py",
        SRC_ENGINE / "stale_manager.py",
    ]
    source = None
    chosen_path = None
    for p in candidate_paths:
        if p.exists():
            source = p.read_text(encoding="utf-8")
            chosen_path = p
            break

    assert source is not None

    tree = ast.parse(source)
    target = None
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "resubscribe_stale_priority":
            target = node
            break

    assert target is not None, f"{chosen_path}: `resubscribe_stale_priority` 누락"

    # AST 부모 추적: high_tickers.update(...) 호출 위치
    update_calls_in_try: list[ast.Call] = []
    update_calls_outside_try: list[ast.Call] = []

    def _walk_with_in_try(node, in_try: bool):
        if isinstance(node, ast.Try):
            in_try = True
        if isinstance(node, ast.Call):
            func = node.func
            # high_tickers.update(...) 매칭
            if (
                isinstance(func, ast.Attribute)
                and func.attr == "update"
                and isinstance(func.value, ast.Name)
                and func.value.id == "high_tickers"
            ):
                if in_try:
                    update_calls_in_try.append(node)
                else:
                    update_calls_outside_try.append(node)
        for child in ast.iter_child_nodes(node):
            _walk_with_in_try(child, in_try)

    _walk_with_in_try(target, in_try=False)

    assert len(update_calls_in_try) >= 2, (
        f"`high_tickers.update(...)` 호출 중 try 블록 내부 = {len(update_calls_in_try)} "
        f"(기대 ≥ 2 — positions + NDC). 사이클 66 Q2 try/except 4중 가드 영속 위반."
    )
    assert len(update_calls_outside_try) == 0, (
        f"`high_tickers.update(...)` 호출 중 try 블록 외부 = {len(update_calls_outside_try)} "
        f"(기대 0). 사이클 66 Q2 본체 답습 위반 — silent 실패 위험."
    )


# ===========================================================================
# G-13 — caplog set_level(logger="src.engine.scheduler") 영속 (실행 검증)
# ===========================================================================
@pytest.mark.asyncio
@freeze_time("2026-06-08 10:00:00", tz_offset=-9)
async def test_G13_caplog_scheduler_logger_consistent_after_decomposition(caplog):
    """G-13 (자문 §4 Q4 영속): 분해 후 `[stale_priority_resubscribe_cap_exceeded]` WARNING 이
    `src.engine.scheduler` logger 로 발화.

    Q3 옵션 A: 4 sub-module 모두 `logging.getLogger("src.engine.scheduler")` binding.
    Q4 옵션 B: caplog logger 인자도 `src.engine.scheduler` 단일 영속.

    사이클 66 K-10 패턴 (HIGH > cap → WARNING 발화) 답습 + caplog 일관성 검증.

    Red 단계: 현재 stale_manager.py 본체가 이미 `src.engine.scheduler` logger 사용 →
              PASS 가능. 본 테스트는 분해 *후* 동일 행위 영속 보장 의무.
    Green 단계: 분해 후 stale_watcher_core 도 동일 logger 영속 = PASS.
    """
    from src.engine import stale_manager
    from src.engine.scheduler import TradingScheduler
    from src.engine.stale_tracker import StaleTrackerState

    base = datetime(2026, 6, 8, 10, 0, 0, tzinfo=KST)

    sched = TradingScheduler.__new__(TradingScheduler)
    object.__setattr__(sched, "_stale_state", StaleTrackerState())
    object.__setattr__(sched, "_pending_next_day_clear", set())

    # HIGH 12 > cap=10 → WARNING 발화 강제
    high_tickers = [f"00{i:04d}" for i in range(1, 13)]
    strategy_state = MagicMock()
    strategy_state.positions = {t: MagicMock() for t in high_tickers}
    strategy = MagicMock(state=strategy_state)
    sched.registry = MagicMock(all=lambda: [strategy])

    stale_dt = base - timedelta(seconds=120)
    ticker_last_tick = {t: stale_dt for t in high_tickers}

    mock_pool = MagicMock()
    mock_pool.subscribe = AsyncMock(return_value=None)

    caplog.set_level(logging.WARNING, logger="src.engine.scheduler")

    with patch("asyncio.sleep", new=AsyncMock(return_value=None)), \
         patch("src.realtime.websocket_pool.kis_ws_pool", mock_pool), \
         patch("src.engine.scanner.ticker_last_tick", new=ticker_last_tick):
        await stale_manager.resubscribe_stale_priority(sched, cap=10)

    # WARNING 발화가 src.engine.scheduler logger 로 잡혔는지 검증
    cap_exceeded_warnings = [
        r for r in caplog.records
        if r.levelno == logging.WARNING
        and "[stale_priority_resubscribe_cap_exceeded]" in r.getMessage()
        and r.name == "src.engine.scheduler"
    ]
    assert len(cap_exceeded_warnings) == 1, (
        f"`src.engine.scheduler` logger 로 WARNING 1회 발화 의무 (Q3 옵션 A + Q4 옵션 B 영속). "
        f"실제 발화 수: {len(cap_exceeded_warnings)}. "
        f"전체 records (logger / msg): "
        f"{[(r.name, r.getMessage()) for r in caplog.records if r.levelno >= logging.WARNING]}. "
        f"분해 후 4 sub-module 모두 `logging.getLogger('src.engine.scheduler')` binding 의무."
    )
