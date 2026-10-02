"""cycle397 — 잔고 화면의 **매입일(최초 매입일)** 단일 진실원.

사용자 요청(2026-10-02) = "잔고내역에 매입일을 표기하자. 혹시 여러날짜에 걸쳐
매수했다면(피라미딩으로 인해) 최초매입일로 표시."

## 두 출처

| 출처 | 값 | 비는 경우 |
|---|---|---|
| 엔진 포지션 `Position.buy_date` | 그 전략이 실제로 쓰는 값(`StrategyBase` 청산 판정·`is_next_day` 와 동일 소스) | 엔진 정지(21:30~07:45) 또는 그 종목을 들고 있는 전략이 없을 때 |
| DB `positions.buy_date` | 재시작 복구 전 영속값 — 수동 보유(엔진이 모르는 포지션)에도 있다 | 포지션 자체가 DB 에도 없을 때(매수 직후 커밋 전 race 등) |

## 최초 매입일 규약

같은 종목에 여러 원천이 서로 다른 날짜를 들고 있으면 **가장 이른 날짜**를 쓴다.
현재 코드 구조(`is_ticker_blocked_for_buy` 가 같은 전략의 동일 종목 추가 매수를
막는다)에서는 `Position.buy_date` 가 이미 그 포지션의 최초 매입일이라 사실상
갈릴 일이 없지만(값 자체는 하나), **엔진 값과 DB 값이 서로 다른 시점의 스냅샷일
수 있다**(엔진이 재시작 전 값을 메모리에 들고 있는데 DB 가 더 이른 값으로 먼저
갱신된 경우 등) — 그 경우에도 더 이른 쪽을 택해 "최초" 의미를 지킨다.

🔴 **피라미딩이 실제로 열리면 이 규약이 재검토 대상이다** — 그때는 `buy_date`
단일 필드로는 "최초" 와 "최근 추가분" 을 구분할 수 없어 `trade_history` 조회가
필요해진다(이 모듈의 범위 밖). 지금은 추가 매수 자체가 막혀 있으므로 `buy_date`
= 최초 매입일이 항상 성립한다.

## 계약

- `resolve_engine_buy_dates`: **순수·read-only·never-raise·`await`/DB/HTTP 0**.
- `merge_buy_date`: 순수 함수. 두 값 중 더 이른 것(ISO 문자열 사전식 비교 = 날짜
  비교와 동치, `YYYY-MM-DD` 형식 한정).
- **불확실하면 `None`** — 오늘 날짜로 채우지 않는다(「모름」과 「없음」을 구분).
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Any, Iterable

logger = logging.getLogger(__name__)

__all__ = ["resolve_engine_buy_dates", "merge_buy_date"]


def resolve_engine_buy_dates(strategies: Iterable[Any]) -> dict[str, str]:
    """registry 의 전 전략 포지션을 순회해 `{ticker: ISO 날짜}` 를 만든다.

    두 전략이 같은 종목을 들고 있는 비정상 상태(`is_ticker_blocked_for_buy` 가
    보통 막는다)가 되더라도, 여기서는 **가장 이른 날짜**를 취해 "최초 매입일"
    의미를 지킨다. 예외는 전부 흡수하고 지금까지 모은 것만 돌려준다.
    """
    out: dict[str, str] = {}
    try:
        for s in strategies:
            state = getattr(s, "state", None)
            positions = getattr(state, "positions", None)
            if not isinstance(positions, dict):
                continue
            for ticker, pos in positions.items():
                bd = getattr(pos, "buy_date", None)
                if not isinstance(bd, date):
                    continue
                iso = bd.isoformat()
                if ticker not in out or iso < out[ticker]:
                    out[ticker] = iso
    except Exception:
        logger.debug("[buy_date] 전략 포지션 순회 실패", exc_info=True)
    return out


def merge_buy_date(engine_iso: str | None, db_value: date | str | None) -> str | None:
    """엔진 값과 DB 값 중 **더 이른 날짜**(최초 매입일)를 고른다.

    모양이 이상한 값(빈 문자열·None·다른 타입)은 후보에서 제외한다. 후보가 하나도
    없으면 `None`("모름") — 가짜 값을 만들지 않는다.
    """
    candidates: list[str] = []
    if isinstance(engine_iso, str) and engine_iso:
        candidates.append(engine_iso)
    if isinstance(db_value, date):
        candidates.append(db_value.isoformat())
    elif isinstance(db_value, str) and db_value:
        candidates.append(db_value)
    if not candidates:
        return None
    return min(candidates)
