"""계좌 통합 리스크 감시자 (cycle233, G3′ 패키지 — SOFT Σ상한 순간 게이트).

자문 정본 = `_workspace/domain_consult/cycle232_risk_control_review.md` §2.5-γ.
배선 = `boot_manager.boot()` 부팅 직후 동기 1회 + `ensure_watch_loop` 가 스폰하는
**자기 종료 루프**(`watch_loop`, 5분 — `_running` False 시 ≤60s 자연 종료라
cancel 목록/task_attrs 불요). scheduler.py 는 무접촉(라인 상한 가드 <4,000L 존중).

계약 (사용자 결정 D1·D2, 2026-08-29):
- **Σ상한 = 순간 게이트** — 평가마다 재계산(양방향). 전략별 일일손실 플래그와
  **이원화**되어 있어 이 모듈은 전략 state 의 어떤 필드도 쓰지 않는다(AST G-4 가
  해당 필드명 토큰 0 을 봉인 — risk.py 가 세운 차단을 지우는 회귀의 구조적 차단).
  소비처는 `StrategyBase._account_soft_gate_blocked`(check_buy_signal 최상단) 뿐
  — **청산·손절 경로는 구조적으로 차단 불가능**하다.
- **fail-open + LOUD**: 평가 실패 시 게이트 False + `[account_risk_watch_failed]`
  WARNING. 조용히 닫히면 "도입 이전 무음과 구별 불가"(D2).
- 다크런치: `system_config.get_account_risk_block_pct()` 기본 None → level 은
  warn 까지만 도달 가능. 활성화 = DB `account_risk_block_pct` 한 줄(권고 6.0).
- 리스크 척도 = **실효 손절선 병기 값**(`portfolio_risk` stop_price_of 주입) —
  프록시 단독으로 임계를 걸면 "잰 적 없는 값에 상한"(자문 §정정 2).

로그 (cap 은 날짜 키 자기 리셋 — scheduler 훅 미의존. **전이 로그는 cap 밖**:
희소 사건이고 flapping 자체가 관측해야 할 신호다 — 적대 검증 F5):
- `[account_risk_gate] transition=entered` WARNING = block 진입 전이(cap 밖) /
  `transition=reconfirm` WARNING 1회/일 = 지속 재확인 / `released` INFO = 해제 전이
  (평가 실패로 인한 해제는 `released reason=eval_failure` WARNING, cap 밖).
- `[account_risk_watch] level=warn` WARNING 1회/일 — 관측 경보(기본 4%).
- `[account_risk_watch]` INFO 1회/일 — 요약(pct·coverage·over_cap).
- `[account_risk_watch_failed]` WARNING 1회/일 — 평가 실패(fail-open).
관측 순서 규약 = **peek → 로그 → mark** (cycle226 D-3 — 관측기 자기실패가
관측 대상을 지우면 안 된다: 로그가 던져도 cap 은 미소비라 다음 평가가 재시도).
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any, Optional

from src.db._kst import KST
from src.engine.daily_emit_cap import DailyEmitCap

# 운영 grep 연속성 — 감시자 로그는 scheduler 네임스페이스로 (stale_manager 선례)
logger = logging.getLogger("src.engine.scheduler")

# ── 모듈 상태 (uvicorn 단일 워커 전제 — refresh_progress 선례) ──────────────
_gate_active: bool = False
_gate_state: dict = {"level": "ok", "reasons": [], "open_risk_pct": None,
                     "evaluated_at": None}
_emit_cap: DailyEmitCap[str] = DailyEmitCap[str]()
_emit_day: str = ""


_WATCH_INTERVAL_SECS = 300  # 5분 주기 (collector flush 케이던스 정합)
_watch_task = None  # asyncio.Task — 중복 스폰 방지 참조 (boot 는 매 영업일 재실행)


async def watch_loop(scheduler: Any) -> None:
    """자기 종료 감시 루프 — `scheduler._running` False 면 스스로 끝난다.

    scheduler.py 라인 상한 가드(재비대 방지 < 4,000L)를 존중해 주기 배선을
    scheduler 밖에 둔다 — cancel 목록·task_attrs 등록 불요(자연 종료 ≤ 60s).
    스폰은 `ensure_watch_loop`(boot_manager) 단일 지점, 중복 스폰 방지 내장.
    """
    while getattr(scheduler, "_running", False):
        await run_account_risk_watch_once(scheduler)
        for _ in range(_WATCH_INTERVAL_SECS // 60):
            if not getattr(scheduler, "_running", False):
                break
            await asyncio.sleep(60)


def ensure_watch_loop(scheduler: Any) -> None:
    """감시 루프 스폰 (idempotent) — 살아있는 루프가 있으면 no-op.

    boot() 가 매 영업일 07:55 재실행되므로 중복 스폰 가드가 필수다.
    """
    global _watch_task
    if _watch_task is not None and not _watch_task.done():
        return
    _watch_task = asyncio.create_task(watch_loop(scheduler))


def is_soft_gated() -> bool:
    """SOFT Σ상한 순간 게이트 상태 — True 면 신규 매수 신호만 차단."""
    return _gate_active


def get_gate_state() -> dict:
    """관측용 상태 사본 (대시보드/진단)."""
    return dict(_gate_state)


def reset_state_for_test() -> None:
    """테스트 전용 — 모듈 상태 초기화."""
    global _gate_active, _gate_state, _emit_cap, _emit_day
    _gate_active = False
    _gate_state = {"level": "ok", "reasons": [], "open_risk_pct": None,
                   "evaluated_at": None}
    _emit_cap = DailyEmitCap[str]()
    _emit_day = ""


def _peek_emit(key: str) -> bool:
    """1회/(key)/일 cap 의 **판정만** — mark 는 로그 성공 후 `_mark_emitted`.

    mark-before-log 는 로그 자기실패가 그날 관측을 지운다(cycle226 D-3 동형,
    적대 검증 F4). 날짜 키 자기 리셋(`_reset_daily_state` 훅 미의존).
    """
    global _emit_day
    today = datetime.now(KST).date().isoformat()
    if _emit_day != today:
        _emit_day = today
        _emit_cap.reset_daily()
    return _emit_cap.should_emit(key)


def _mark_emitted(key: str) -> None:
    _emit_cap.mark_emitted(key)


async def run_account_risk_watch_once(scheduler: Any) -> Optional[dict]:
    """계좌 Σ오픈리스크 1회 평가 → 순간 게이트 갱신 + 관측 로그.

    실패는 **fail-open** — 게이트 False + WARNING 후 None 반환 (매매 지속).
    """
    global _gate_active, _gate_state
    try:
        from src.api import balance as balance_mod
        from src.db import system_config
        from src.engine import portfolio_risk
        from src.engine.account_risk_guard import evaluate_soft_gate

        strategies = list(scheduler.registry.all())

        _holdings, summary = await balance_mod.get_balance()
        net_asset = int(getattr(summary, "net_asset", 0) or 0)

        hard_stop_pcts: dict[str, float] = {}
        strat_by_id: dict[str, Any] = {}
        for s in strategies:
            sid = getattr(s, "strategy_id", None) or "unknown"
            strat_by_id[sid] = s
            params = getattr(getattr(s, "config", None), "params", None)
            hard_stop_pcts[sid] = portfolio_risk.extract_hard_stop_pct(params)

        def _stop_of(sid: str, ticker: str) -> Optional[int]:
            strat = strat_by_id.get(sid)
            fn = getattr(strat, "get_effective_stop_price", None)
            if not callable(fn):
                return None
            try:
                return fn(ticker)
            except Exception:
                return None

        snapshot = portfolio_risk.compute_portfolio_risk_snapshot(
            strategies,
            net_asset=net_asset,
            hard_stop_pcts=hard_stop_pcts,
            sector_of={},
            stop_price_of=_stop_of,
        )
        effective = snapshot.get("effective") or {}
        eff_pct = effective.get("open_risk_effective_pct_of_net")
        coverage = effective.get("coverage") or {}

        over_cap = portfolio_risk.compute_over_cap_positions(strategies)

        warn_pct = await system_config.get_account_risk_warn_pct()
        block_pct = await system_config.get_account_risk_block_pct()
        verdict = evaluate_soft_gate(eff_pct, warn_pct=warn_pct, block_pct=block_pct)
        level = verdict["level"]

        was_active = _gate_active
        _gate_active = level == "block"
        _gate_state = {
            "level": level,
            "reasons": list(verdict.get("reasons") or []),
            "open_risk_pct": eff_pct,
            "open_risk_proxy_pct": snapshot.get("open_risk_pct_of_net"),
            "net_asset": net_asset,
            "coverage": coverage,
            "over_cap_count": len(over_cap),
            "warn_pct": warn_pct,
            "block_pct": block_pct,
            "evaluated_at": datetime.now(KST).isoformat(),
        }

        if _gate_active:
            if not was_active:
                # 전이는 cap 밖 — 희소 사건이고 flapping 자체가 관측 신호(F5)
                logger.warning(
                    "[account_risk_gate] level=block transition=entered eff_pct=%s "
                    "block_pct=%s reasons=%s — 신규 매수 신호만 차단(청산·손절 무관)",
                    eff_pct, block_pct, verdict.get("reasons"),
                )
            elif _peek_emit("gate_block"):
                logger.warning(
                    "[account_risk_gate] level=block transition=reconfirm eff_pct=%s "
                    "block_pct=%s — 지속 중 (1회/일 재확인)",
                    eff_pct, block_pct,
                )
                _mark_emitted("gate_block")
        elif was_active:
            logger.info(
                "[account_risk_gate] released — eff_pct=%s < block_pct=%s",
                eff_pct, block_pct,
            )
        elif level == "warn":
            if _peek_emit("watch_warn"):
                logger.warning(
                    "[account_risk_watch] level=warn eff_pct=%s warn_pct=%s "
                    "proxy_pct=%s — 설계 천장(스윙 3.55%%) 밖 사건 관측",
                    eff_pct, warn_pct, snapshot.get("open_risk_pct_of_net"),
                )
                _mark_emitted("watch_warn")
        else:
            if _peek_emit("watch_summary"):
                logger.info(
                    "[account_risk_watch] level=ok eff_pct=%s proxy_pct=%s "
                    "coverage=%s/%s over_cap=%d net=%d",
                    eff_pct, snapshot.get("open_risk_pct_of_net"),
                    coverage.get("effective_positions"),
                    coverage.get("total_positions"),
                    len(over_cap), net_asset,
                )
                _mark_emitted("watch_summary")
        return _gate_state
    except Exception as exc:
        was_active = _gate_active
        _gate_active = False  # fail-open — 판정 실패가 매수를 막지 않는다
        _gate_state = {"level": "error", "reasons": [str(exc)[:150]],
                       "open_risk_pct": None,
                       "evaluated_at": datetime.now(KST).isoformat()}
        try:
            if was_active:
                # 실패로 인한 해제 전이도 명시 (F5 — 무음 해제 금지, cap 밖)
                logger.warning(
                    "[account_risk_gate] released reason=eval_failure — "
                    "평가 실패로 fail-open 해제. %s", type(exc).__name__,
                )
            if _peek_emit("watch_failed"):
                logger.warning(
                    "[account_risk_watch_failed] 평가 실패 — fail-open(게이트 해제 상태 유지). "
                    "%s: %s", type(exc).__name__, str(exc)[:150],
                )
                _mark_emitted("watch_failed")
        except Exception:
            pass
        return None
