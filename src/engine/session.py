"""세션/보드 추상화 — KRX/NXT 매매 시간대 정책.

KRX(09:00~15:30) + NXT(08:00~20:00) 통합 운영 시 어느 보드(세션 단계)가
현재 활성인지 추적하고, 각 전략이 어느 보드에서 매매 가능한지 판정한다.

활성 보드 결정:
- 1차: 시각 기반 매핑 (`_BOARD_SCHEDULE`) — 항상 동작
- 2차: `H0NXMKO0`(NXT 장운영정보) 실시간 메시지로 정확도 보강 — 메시지 필드
       명세 미확정이라 코드 기록만 하고 향후 운영 데이터로 점진 정확화

전략별 매매 허용 보드는 `DEFAULT_PARAMS["tradable_boards"]` (Phase 8) 또는
`_DEFAULT_TRADABLE_BOARDS` fallback에서 가져온다.
"""

from __future__ import annotations

import logging
from datetime import datetime, time
from enum import Enum
from typing import Awaitable, Callable

logger = logging.getLogger(__name__)


class MarketBoard(str, Enum):
    """매매 가능 보드 구분.

    사이클 26 (2026-05-20): KRX_OPEN / KRX_AFTER 보드 비활성화.
    - KRX_OPEN (08:30~09:00): 제거 — PRE_NXT 단독 구간으로 통합
    - KRX_AFTER (15:30~18:00): 제거 — 15:30~15:39:59 는 MAIN 유지, 15:40~ 는 POST_NXT
    enum 값 자체는 호환성을 위해 유지 (DB 파라미터, 외부 참조 코드 영향 0).
    """

    PRE_NXT = "pre_nxt"          # NXT 프리마켓 (08:00~09:00)
    KRX_OPEN = "krx_open"        # (사이클 26: 비활성, 호환성 보존) KRX 동시호가
    MAIN = "main"                # KRX 메인 (09:00~15:39:59)
    KRX_AFTER = "krx_after"      # (사이클 26: 비활성, 호환성 보존) KRX 시간외
    POST_NXT = "post_nxt"        # NXT 애프터마켓 (15:40~20:00)


# 시각 기반 보드 매핑 — H0NXMKO0 미수신 시 fallback (NXT 통상 시간 기준)
# (start, end, active_boards) — start <= now < end
#
# 사이클 26 (2026-05-20) 변경:
#   Before: 5 보드 (PRE/KRX_OPEN/MAIN/KRX_AFTER/POST)
#   After:  3 보드 (PRE/MAIN/POST) — 시간대별 명확화
#
# 시각표:
#   08:00~08:59:59 → PRE_NXT (시세: H0NXCNT0)
#   09:00~15:39:59 → MAIN    (시세: H0STCNT0, 09:00:05 시가 확정, 15:20 강제 청산)
#   15:40~19:59:59 → POST_NXT (시세: H0NXCNT0)
#   20:00~         → 장 종료 (보드 없음)
#
# 갭 구간:
#   15:30~15:39:59 — MAIN 유지 (종가 결정 지연 흡수 10분 마진)
#   08:59:10 사전 마진 — scheduler 가 H0STCNT0 추가 subscribe 시작 (보드는 PRE_NXT 유지)
#   15:39:10 사전 마진 — scheduler 가 H0NXCNT0 추가 subscribe 시작 (보드는 MAIN 유지)
_BOARD_SCHEDULE: list[tuple[time, time, frozenset[MarketBoard]]] = [
    # PRE_NXT: 08:00~08:59:59 (KRX_OPEN 구간 통합 — 시세 채널 H0NXCNT0)
    (time(8, 0), time(9, 0), frozenset({MarketBoard.PRE_NXT})),
    # MAIN: 09:00~15:39:59 (buy_stop 구간 15:20~15:30 포함, 15:30~15:40 갭 마진 포함)
    (time(9, 0), time(15, 40), frozenset({MarketBoard.MAIN})),
    # POST_NXT: 15:40~19:59:59 (사이클 26: 15:30 → 15:40 으로 변경)
    (time(15, 40), time(20, 0), frozenset({MarketBoard.POST_NXT})),
]


# 전략별 매매 허용 보드 fallback (DEFAULT_PARAMS["tradable_boards"]가 우선)
# 사이클 26 (2026-05-20): VB/LTV fallback 을 MAIN 단독으로 변경
# 사이클 38 (2026-05-22): LTV fallback 사용자 의도 복원 — PRE_NXT + MAIN + POST_NXT.
# VB 는 그대로 MAIN 단독 (사용자 정책 부합, 15:20 일괄 청산 + OVERNIGHT 결함 차단).
_DEFAULT_TRADABLE_BOARDS: dict[str, frozenset[MarketBoard]] = {
    "momentum": frozenset({MarketBoard.KRX_OPEN, MarketBoard.MAIN}),
    # VB: 사이클 26 — KRX ONLY (POST_NXT OVERNIGHT 결함 + 15:20 일괄 청산 정책)
    "volatility_breakout": frozenset({MarketBoard.MAIN}),
    # LTV: 사이클 38 — PRE_NXT + MAIN + POST_NXT (연속 상한가 익일 청산 + 야간 매수)
    "long_tail_volatility": frozenset(
        {MarketBoard.PRE_NXT, MarketBoard.MAIN, MarketBoard.POST_NXT}
    ),
    "donchian_swing": frozenset({MarketBoard.MAIN}),
}


def boards_at(now_t: time) -> frozenset[MarketBoard]:
    """지정 시각에 활성인 보드 집합 (시각 기반)."""
    for start, end, boards in _BOARD_SCHEDULE:
        if start <= now_t < end:
            return boards
    return frozenset()


def parse_tradable_boards(value) -> frozenset[MarketBoard]:
    """DEFAULT_PARAMS / strategy_config의 tradable_boards 값을 파싱.

    list/tuple/set의 각 항목은 `MarketBoard` enum 값(`"main"`, `"pre_nxt"` 등) 문자열.
    None/빈 값이면 빈 frozenset 반환 (호출자가 fallback 결정).
    """
    if not value:
        return frozenset()
    boards: set[MarketBoard] = set()
    for v in value:
        try:
            boards.add(MarketBoard(v))
        except ValueError:
            logger.warning("tradable_boards 알 수 없는 값 무시: %s", v)
    return frozenset(boards)


def get_tradable_boards(strategy_id: str, params: dict | None = None) -> frozenset[MarketBoard]:
    """전략의 매매 허용 보드.

    `params["tradable_boards"]`가 명시돼 있으면 우선, 없으면 `_DEFAULT_TRADABLE_BOARDS` fallback.
    """
    if params:
        explicit = parse_tradable_boards(params.get("tradable_boards"))
        if explicit:
            return explicit
    return _DEFAULT_TRADABLE_BOARDS.get(strategy_id, frozenset())


# 보드 진입/종료 콜백 시그니처
BoardEnterCallback = Callable[[MarketBoard], Awaitable[None]]
BoardExitCallback = Callable[[MarketBoard], Awaitable[None]]


class SessionTracker:
    """현재 활성 보드를 추적하고 진입/종료 이벤트를 콜백으로 발화."""

    def __init__(self) -> None:
        self._active: frozenset[MarketBoard] = frozenset()
        self._on_enter: list[BoardEnterCallback] = []
        self._on_exit: list[BoardExitCallback] = []
        # 마지막으로 받은 H0NXMKO0 코드 — 향후 정확한 보드 매핑 도입 시 사용
        self._last_nxt_mkop_code: str = ""

    @property
    def active(self) -> frozenset[MarketBoard]:
        return self._active

    @property
    def last_nxt_mkop_code(self) -> str:
        return self._last_nxt_mkop_code

    def is_active(self, board: MarketBoard) -> bool:
        return board in self._active

    def is_tradable(self, strategy_id: str, params: dict | None = None) -> bool:
        """전략이 현재 활성 보드 중 적어도 하나에서 매매 가능한지."""
        if not self._active:
            return False
        allowed = get_tradable_boards(strategy_id, params)
        return bool(allowed & self._active)

    def register_on_enter(self, cb: BoardEnterCallback) -> None:
        self._on_enter.append(cb)

    def register_on_exit(self, cb: BoardExitCallback) -> None:
        self._on_exit.append(cb)

    async def tick(self, now: datetime | None = None) -> None:
        """현재 시각 기준 활성 보드 갱신 + 변동 시 콜백 발화."""
        now = now or datetime.now()
        next_active = boards_at(now.time())

        entered = next_active - self._active
        exited = self._active - next_active
        self._active = next_active

        for board in entered:
            logger.info("[Session] 보드 진입: %s", board.value)
            for cb in self._on_enter:
                try:
                    await cb(board)
                except Exception:
                    logger.exception("[Session] 진입 콜백 실패: %s", board.value)

        for board in exited:
            logger.info("[Session] 보드 종료: %s", board.value)
            for cb in self._on_exit:
                try:
                    await cb(board)
                except Exception:
                    logger.exception("[Session] 종료 콜백 실패: %s", board.value)

    async def on_h0nxmko0(self, tr_key: str, mkop_cls_code: str, payload: str) -> None:
        """장운영정보(H0UNMKO0/H0STMKO0/H0NXMKO0) 메시지 수신.

        KIS MKOP_CLS_CODE 매핑(공통):
          110: 장전 동시호가 개시 / 112: 장개시 (09:00) / 121: 장후 동시호가 개시
          129: 장마감 (15:30) / 130-139: 장개시전시간외 (08:00-09:00)
          140-149: 시간외 종가 매매 (15:30-16:00) / 150-159: 시간외 단일가 (16:00-18:00)

        통합(H0UNMKO0)/KRX(H0STMKO0)/NXT(H0NXMKO0) 동일 메시지 포맷이라 본 콜백을 공용한다.
        실시간 코드를 기록만 해두고, tick()의 시각 기반 매핑이 보드 결정을 담당.
        (보드 코드 → 보드 enum 매핑 도입은 운영 데이터로 시각/코드 정합성 확인 후)
        """
        self._last_nxt_mkop_code = mkop_cls_code
        logger.debug(
            "[Session] 장운영정보: tr_key=%s, MKOP_CLS_CODE=%s", tr_key, mkop_cls_code,
        )


# 전역 인스턴스 — scheduler/risk가 import해서 사용
session_tracker = SessionTracker()
