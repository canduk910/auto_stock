"""사이클 258 카드 #5 — 관측기 자기 실패 흔적 단일화.

관측기(로그 emit 헬퍼) 자기 실패의 처리 정책이 프로젝트 전역에 4가지로
갈라져 있었다 — A. 무흔적 `pass`(strategy_base 11 + account_risk_watcher 2) ·
B. `logger.debug` 단독(stale_watcher_core · api_auth) · C. debug 스택 +
WARNING 1회/일(donchian_swing._trace_observer_failure) · D. wrapper 안 `pass`.

cycle237 적대 검증 C237-L2-1 이 "debug 단독은 `src/main.py::_DbLogHandler`
(INFO 컷)를 못 넘어 `system_logs` 에 도달하지 않아 도입 이전 무음과 구별 불가"
라고 확정했는데 그 결론이 donchian(C 형태) 한 파일에만 반영돼 있었다. 이 leaf
모듈이 C 를 모듈 함수로 승격해 정책을 하나로 만든다.

leaf 계약 — `src.*` import 는 `src.engine.daily_emit_cap` 하나뿐(AST 가드
T-8). `daily_emit_cap.KstDailyEmitCap.emit_once` 가 이 함수를 **함수 내부
(지연) import** 로 호출한다 — 반대 방향(이 모듈이 daily_emit_cap 을 모듈
최상단에서 import) 하나만 허용해 순환 임포트를 구조적으로 차단한다.
"""
from __future__ import annotations

import logging
from datetime import datetime

logger = logging.getLogger(__name__)

# 실패 흔적 전용 키 접미사 — 정상 관측 키(예: ticker 단독, `ticker|reason`)와
# 충돌하지 않게 분리한다(donchian J-2/J-3 선례 — 실패 1건이 그날의 정상 관측을
# 통째로 삼키면 안 된다).
_OBSERVER_FAILED_SUFFIX = "__observer_failed__"


def trace_observer_failure(
    marker: str,
    key: str,
    cap=None,
    *,
    now: "datetime | None" = None,
    dest_logger: "logging.Logger | None" = None,
) -> None:
    """관측기 **자기 실패**의 흔적 — debug 스택(항상) + WARNING 1회/(key)/일(cap 있을 때).

    이 함수는 관례상 **이미 `except` 블록 안**에서 호출된다(호출자가 자신의
    관측 로직 실패를 흡수하는 지점). 그래서 여기서 다시 던지면 2차 예외가
    관측을 넘어 매매 경로를 죽인다 — 모든 단계를 각각 자체 `try` 로 감싸고
    실패는 전부 흡수한다(never-raise, donchian J-3 "가장 안쪽은 어떤 경우에도
    조용히 통과한다" 계약 승계).

    Args:
        marker: 실패한 관측기의 마커 문자열(예: ``"[fallback_cap_clamped]"``).
        key: 실패 흔적 키의 기준값(보통 ticker 또는 전략 id, `"-"` 등 폴백 허용).
        cap: 호출자 자신의 `KstDailyEmitCap` 인스턴스(선택). 있으면 WARNING 을
            `f"{marker}|{key}{_OBSERVER_FAILED_SUFFIX}"` 복합 키로 **1회/(marker,
            key)/일** cap 한다 — 정상 관측 키를 **절대 공유하지 않는다**(donchian
            J-3 계약). 키에 marker 를 넣는 이유(C258-T4) = 같은 cap 인스턴스를
            공유하며 같은 key 를 쓰는 관측기 쌍이 실재한다(strategy_base
            `_lot_cap_logged` 의 config/clamped 는 둘 다 key=strategy_id,
            notional_capped/cap_skipped 는 둘 다 key=ticker · `_ratio_cap_logged`
            4쌍 동형) — key 만으로 cap 하면 같은 날 두 번째 관측기의 사망이
            WARNING 없이(debug 만) 지나가 20:10 리포트에서 보이지 않는다. 없으면
            debug 스택만 남기고 WARNING 은 내지 않는다(폭주 차단 수단이 없는
            호출부가 무제한 WARNING 을 내면 안 된다).
        now: 날짜 판정 결정성 주입(테스트 seam). 생략 시 벽시계.
        dest_logger: 이 흔적을 남길 로거. 생략 시 이 모듈 자신의 `logger`(T-4 가
            `mod.logger.debug/.warning` 를 직접 monkeypatch 하는 대상)를 쓴다 —
            호출자가 자기 모듈 로거를 넘기면(예: donchian 이 자신의 `logger`를
            전달) 기존 `caplog.at_level(..., logger=<모듈>)` 로 스코프된 회귀
            테스트와의 호환이 보존된다(donchian C 형태 승격 시 로거 정체성
            불변 요구).
    """
    log = dest_logger if dest_logger is not None else logger
    try:
        log.debug("%s observer_failed key=%s", marker, key, exc_info=True)
    except Exception:  # pragma: no cover — 2차 예외 흡수
        pass

    if cap is None:
        return

    try:
        trace_key = f"{marker}|{key}{_OBSERVER_FAILED_SUFFIX}"
        if cap.should_emit(trace_key, now=now):
            log.warning("%s observer_failed key=%s", marker, key)
            cap.mark_emitted(trace_key, now=now)
    except Exception:  # pragma: no cover — cap 자기실패도 흡수(T-4b)
        pass
