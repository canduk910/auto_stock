"""프로세스 가동 하트비트 + 부팅 tick blind 계측 (cycle234 — G2 대체 조치 ①).

자문 정본 = `_workspace/domain_consult/cycle232_risk_control_review.md` §3.5-γ:
서버 스탑(역지정가) 도입을 보류하는 대신, 그 장치가 커버했을 사각(프로세스 부재
동안의 보유 종목 tick blind)을 **숫자로** 만든다 — `market_blind_secs` 의 주간
분포가 0 에 수렴하면 서버 스탑의 편익도 0 에 수렴한다(G2 재검토의 정량 근거).

기제 = 60s 하트비트(`system_config.set_task_last_success` — 사이클 193 마커 인프라
재사용, 신규 테이블 0) + 부팅 시 직전 하트비트와의 갭 로그. blind 계측 오차 상한 =
하트비트 간격(60s). 배선 = `boot_manager.boot()` 이 `report_boot_blind_gap()` 1회 +
`ensure_heartbeat_loop()` 스폰(cycle233 watcher 동형 자기 종료 루프 — scheduler.py
무접촉: 라인 상한 가드 <4,000L 존중, cancel 목록/task_attrs 불요).

**관측 전용** — 매매 행위 무관. 어떤 실패도 부팅/매매를 막지 않는다(never-raise).
`downtime_secs` 는 프로세스 부재 축만 — WS 재연결 blind 는 stale watcher/fresh_ratio
계측 소관(중복 금지).
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, time, timedelta
from typing import Any

from src.db._kst import KST

# 운영 grep 연속성 — scheduler 네임스페이스 (stale_manager/account_risk_watcher 선례)
logger = logging.getLogger("src.engine.scheduler")

HEARTBEAT_TASK_LABEL = "engine_alive_heartbeat"
HEARTBEAT_INTERVAL_SECS = 60  # blind 계측 오차 상한

_hb_task = None  # asyncio.Task — 중복 스폰 방지 (boot 는 매 영업일 재실행)

# 멀티데이 갭 순회 상한 — 마커 오염(연 단위 과거값)이 부팅을 잡아먹지 않게
_MAX_OVERLAP_DAYS = 400

_MARKET_OPEN = time(9, 0)
_MARKET_CLOSE = time(15, 30)

# cycle366 (P6-b) — 확장 blind 창. `market_blind_secs`(위 09:00~15:30) 는 그대로 두고
# NXT 프리마켓(N1)·KRX 애프터마켓(K6)만 별도로 잰다(`src/engine/session.py` 시장 시간표
# 근사 — 이 leaf 는 `session.py`/`market_state.py` 를 import 하지 않는다, 기존 09:00~15:30
# 근사와 같은 설계 원칙). 09-14 KRX 애프터마켓 신설 이후 그 구간의 다운타임이 기존
# `market_blind_secs` 에 전혀 안 잡히던 사각을 메운다 — 참고용 관측이라 기존 필드의
# 판정(WARNING/INFO 분기 기준)은 바꾸지 않는다.
_PRE_MARKET_OPEN = time(8, 0)
_PRE_MARKET_CLOSE = time(8, 50)
_AFTER_MARKET_OPEN = time(16, 0)
_AFTER_MARKET_CLOSE = time(20, 0)


def reset_state_for_test() -> None:
    """테스트 전용 — 모듈 상태 초기화."""
    global _hb_task
    _hb_task = None


def _weekday_window_overlap_secs(
    start: datetime, end: datetime, window_open: time, window_close: time,
) -> int:
    """`[start, end]` 이 **평일** `[window_open, window_close)` KST 와 겹치는 초 — 공용 코어.

    `market_blind_overlap_secs`/`after_market_blind_overlap_secs`/
    `pre_market_blind_overlap_secs` 가 창만 바꿔 재사용한다(cycle366, 행위 보존 리팩토링
    — 세 함수의 로직 중복을 걷어내되 기존 `market_blind_overlap_secs` 의 반환값은
    한 비트도 바뀌지 않는다). 멀티데이 지원(일 단위 순회, 상한 `_MAX_OVERLAP_DAYS`).
    주말 제외. **공휴일은 미고려 근사**(보수적 과대계상 방향). 역전/None 입력은 0
    (never-raise 소비처 계약).
    """
    try:
        if start is None or end is None or end <= start:
            return 0
        start = start.astimezone(KST)
        end = end.astimezone(KST)
        total = 0
        day = start.date()
        last_day = end.date()
        for _ in range(_MAX_OVERLAP_DAYS):
            if day > last_day:
                break
            if day.weekday() < 5:  # 월~금
                w_open = datetime.combine(day, window_open, tzinfo=KST)
                w_close = datetime.combine(day, window_close, tzinfo=KST)
                lo = max(start, w_open)
                hi = min(end, w_close)
                if hi > lo:
                    total += int((hi - lo).total_seconds())
            day += timedelta(days=1)
        return total
    except Exception:
        return 0


def market_blind_overlap_secs(start: datetime, end: datetime) -> int:
    """다운 구간 [start, end] 이 **평일 09:00~15:30 KST** 와 겹치는 초.

    멀티데이 지원(일 단위 순회, 상한 400일). 주말 제외. **공휴일은 미고려 근사** —
    공휴일 다운을 장중 blind 로 과대계상하는 방향(보수)이라 편익 정량화에 안전.
    역전/None 입력은 0 (never-raise 소비처 계약).
    """
    return _weekday_window_overlap_secs(start, end, _MARKET_OPEN, _MARKET_CLOSE)


def after_market_blind_overlap_secs(start: datetime, end: datetime) -> int:
    """(cycle366 P6-b) [start, end] 이 **평일 16:00~20:00 KST(KRX 애프터마켓)** 와 겹치는 초.

    `market_blind_secs` 와 별도 값 — 기존 계측 용도(G2 서버 스탑 재검토)는 무변경이고,
    09-14 KRX 애프터마켓 신설 이후의 다운타임을 참고용으로 추가한다.
    """
    return _weekday_window_overlap_secs(start, end, _AFTER_MARKET_OPEN, _AFTER_MARKET_CLOSE)


def pre_market_blind_overlap_secs(start: datetime, end: datetime) -> int:
    """(cycle366 P6-b) [start, end] 이 **평일 08:00~08:50 KST(NXT 프리마켓)** 와 겹치는 초."""
    return _weekday_window_overlap_secs(start, end, _PRE_MARKET_OPEN, _PRE_MARKET_CLOSE)


async def record_heartbeat() -> None:
    """가동 마커 기록 — 실패는 debug 흔적만 (다음 주기가 재시도)."""
    try:
        from src.db import system_config  # noqa: PLC0415 — lazy (부팅 전 import 부작용 회피)
        from src.db._kst import now_kst_iso
        await system_config.set_task_last_success(
            HEARTBEAT_TASK_LABEL, now_kst_iso())
    except Exception:
        logger.debug("[heartbeat_record_failed] 하트비트 기록 실패", exc_info=True)


async def report_boot_blind_gap() -> None:
    """부팅 시 직전 하트비트와의 갭 = 프로세스 부재 blind 을 1행으로 남긴다.

    `market_blind_secs > 0`(장중 다운 = 보유 종목 손절 사각 실측) → WARNING,
    그 외 INFO. 미래 마커(시계 역행/오염)는 0 clamp. 보고 직후 하트비트를 재기록해
    다음 재시작의 기준점을 세운다. never-raise — 계측 실패가 부팅을 막지 않는다.
    """
    try:
        from src.db import system_config
        raw = await system_config.get_task_last_success(HEARTBEAT_TASK_LABEL)
        now = datetime.now(KST)
        if not raw:
            logger.info("[tick_blind_boot] first_boot — 직전 하트비트 없음 (계측 시작)")
        else:
            last = datetime.fromisoformat(str(raw))
            if last.tzinfo is None:
                last = last.replace(tzinfo=KST)
            gap = int((now - last).total_seconds())
            if gap < 0:
                gap = 0  # 미래 마커 방어 (사이클 193 음수 방어 선례)
            market = market_blind_overlap_secs(last, now) if gap > 0 else 0
            # cycle366 (P6-b) — 확장 blind 초, 참고용(WARNING/INFO 분기는 `market` 만 본다).
            after_market = after_market_blind_overlap_secs(last, now) if gap > 0 else 0
            pre_market = pre_market_blind_overlap_secs(last, now) if gap > 0 else 0
            log_fn = logger.warning if market > 0 else logger.info
            log_fn(
                "[tick_blind_boot] downtime_secs=%d market_blind_secs=%d "
                "after_market_blind_secs=%d pre_market_blind_secs=%d "
                "last_alive=%s — 프로세스 부재 blind (하트비트 60s 해상도·공휴일 "
                "미고려 근사. market>0 = 장중 다운 실측 = G2 서버 스탑 편익의 분자. "
                "after_market/pre_market = 애프터마켓·NXT 프리마켓 겹침 참고용)",
                gap, market, after_market, pre_market, raw,
            )
        try:
            await record_heartbeat()
        except Exception:
            pass
    except Exception:
        logger.debug(
            "[tick_blind_boot_failed] 계측 실패 — 관측 전용이라 부팅 계속",
            exc_info=True,
        )


async def heartbeat_loop(scheduler: Any) -> None:
    """자기 종료 하트비트 루프 — `scheduler._running` False 면 스스로 끝난다.

    cycle233 `account_risk_watcher.watch_loop` 동형(cancel 불요, 종료 지연 ≤60s).
    """
    while getattr(scheduler, "_running", False):
        await record_heartbeat()
        await asyncio.sleep(HEARTBEAT_INTERVAL_SECS)


def ensure_heartbeat_loop(scheduler: Any) -> None:
    """하트비트 루프 스폰 (idempotent) — 살아있는 루프가 있으면 no-op."""
    global _hb_task
    if _hb_task is not None and not _hb_task.done():
        return
    _hb_task = asyncio.create_task(heartbeat_loop(scheduler))
