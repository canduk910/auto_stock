"""출처 모를 보유의 주인 판정·채택·재판정·백업 청산 (cycle461 ⑦-F1 안 U).

사용자 결정 2026-10-10(정본 `_workspace/00_URGENT_WORKLIST.md` 「10-10 저녁 사용자 결정 — ⑦-F1·J-4」)
+ 2026-10-15 「구현 시작하자」. 자문 = `_workspace/domain_consult/2026-10-10_f1_unknown_holding_liquidation.md`.

KIS 잔고에는 있는데 어느 전략 장부에도 없는 보유(체결통보 누락 · 권리 입고 · 사람이 산 것)를
누가 맡을지 정한다. 두 감지 자리가 이 모듈 하나를 공유한다 — 07:45 부팅 KIS 잔고 보완 복구
(`boot_manager.boot`)와 15분 잔고 동기화(`scheduler._sync_positions_from_balance`).

판정(`classify_owner`, 순수):

| 조회 결과 | 배정 | reason |
|---|---|---|
| 열린 왕복 주인이 등록·켜짐 | 그 전략 | `owner` |
| 열린 왕복 주인이 등록·꺼짐 | `unknown` | `owner_disabled` — 같은 청산 경로(사용자 결정 ④) |
| 열린 왕복 주인이 미등록(지운 전략 id) · `unknown` 자신 | `unknown` | `owner_unregistered` |
| 열린 왕복 없음(0건 · 끝난 왕복뿐) | `unknown` | `no_owner` |
| DB 조회 실패 | `unknown` | `lookup_failed` — **팔지 않는다**(판정 보류, 다음 15분에 재판정) |

- 권리 입고(분할 신주·주식배당·무상증자·공모주)는 열린 왕복이 없으니 `no_owner` 로 즉시 매도
  대상이다(사용자 결정 ③ — 자문 권고 「사람에게 넘김」과 다르다). CTRGA 를 조회하지 않는다.
- 계좌(끝 5334)는 자동매매 전용이라 「사람 몫」 을 따로 가르지 않는다(사용자 결정 ②).
- 「팔아도 되는가」 는 `unknown` 전략의 메모리 `_reasons[ticker]` 가 `SELLABLE_REASONS` 에 있을
  때뿐이다. 재시작으로 사유를 잃은 보유(DB 에서 복구된 `unknown` 행)는 사유가 없어 팔지 않고,
  `rejudge_unknown_positions` 가 다시 판정한다(부팅 · 15분 동기화).

🔴 8영역·`scheduler` import 0. 주문은 `order_engine.execute_sell` 공개 함수로만 낸다(백업 청산).
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

logger = logging.getLogger(__name__)

_KST = timezone(timedelta(hours=9))

#: 전용 전략 id — 화면 표시명 「비식별 보유」(`frontend/src/utils/strategyMeta.ts`).
UNKNOWN_STRATEGY_ID = "unknown"

#: 매도해도 되는 사유. 그 밖(`lookup_failed`·사유 없음)은 판정 보류 — 팔지 않는다.
SELLABLE_REASONS = frozenset({"no_owner", "owner_disabled", "owner_unregistered"})
#: 판정 보류 사유.
REASON_LOOKUP_FAILED = "lookup_failed"
#: 주인 전략이 맡았다는 표시(`unknown` 이 아님).
REASON_OWNER = "owner"

#: 주인을 모르는데 `unknown` 전략이 레지스트리에 없을 때(테스트 레지스트리 등) 떨어지는 곳 —
#: 운영에서는 명부(`strategy_manifest`)가 늘 `unknown` 을 등록한다.
_LEGACY_FALLBACK_ID = "momentum"


def is_unknown_strategy_id(strategy_id: Any) -> bool:
    return strategy_id == UNKNOWN_STRATEGY_ID


def classify_owner(status: str, owner: str | None, registry: Any) -> tuple[str, str]:
    """조회 결과 → (배정 전략 id, reason). 순수·never-raise."""
    try:
        if status == "error":
            return (UNKNOWN_STRATEGY_ID, REASON_LOOKUP_FAILED)
        if status != "found" or not owner:
            return (UNKNOWN_STRATEGY_ID, "no_owner")
        if owner == UNKNOWN_STRATEGY_ID:
            return (UNKNOWN_STRATEGY_ID, "owner_unregistered")
        target = registry.get(owner)
        if target is None:
            return (UNKNOWN_STRATEGY_ID, "owner_unregistered")
        if getattr(target.config, "enabled", False) is True:
            return (owner, REASON_OWNER)
        return (UNKNOWN_STRATEGY_ID, "owner_disabled")
    except Exception:
        logger.exception("[unknown_holding_classify_failed] status=%s owner=%s", status, owner)
        return (UNKNOWN_STRATEGY_ID, REASON_LOOKUP_FAILED)


async def resolve_owner(registry: Any, ticker: str) -> tuple[str, str, str | None]:
    """DB 열린 왕복 조회 + 판정 → (배정 전략 id, reason, 조회된 주인 id 또는 None). never-raise."""
    from src.db import trade_history as _th

    try:
        status, owner = await _th.get_open_roundtrip_owner(ticker)
    except Exception as exc:
        logger.error(
            "[unknown_holding_lookup_failed] ticker=%s err=%s — 판정 보류(팔지 않는다), 다음 동기화에 재판정",
            ticker, type(exc).__name__,
        )
        return (UNKNOWN_STRATEGY_ID, REASON_LOOKUP_FAILED, None)
    sid, reason = classify_owner(status, owner, registry)
    return (sid, reason, owner)


def resolve_target(registry: Any, strategy_id: str) -> Any:
    """배정 전략 객체. `unknown` 이 미등록이면 옛 폴백(momentum)으로 떨어지고 ERROR 를 남긴다."""
    target = registry.get(strategy_id)
    if target is not None:
        return target
    if strategy_id == UNKNOWN_STRATEGY_ID:
        logger.error(
            "[unknown_holding_unregistered] unknown 전략이 레지스트리에 없다 — %s 로 폴백",
            _LEGACY_FALLBACK_ID,
        )
    return registry.get(_LEGACY_FALLBACK_ID)


def note_adopted(
    target: Any, ticker: str, reason: str, *, path: str, owner: str | None = None,
) -> None:
    """채택 기록 — `unknown` 이면 사유를 남기고 마커를 낸다. never-raise.

    🔴 `write_log` 를 또 쓰지 않는다 — `logger.*` 가 루트 `_DbLogHandler` 로 system_logs 에 들어간다.
    """
    try:
        if not is_unknown_strategy_id(getattr(target, "strategy_id", None)):
            return
        reasons = getattr(target, "_reasons", None)
        if isinstance(reasons, dict):
            reasons[ticker] = reason
        if reason == REASON_LOOKUP_FAILED:
            logger.error(
                "[unknown_holding_adopted] path=%s ticker=%s reason=%s owner=%s — 판정 보류(팔지 않는다)",
                path, ticker, reason, owner or "-",
            )
        else:
            logger.warning(
                "[unknown_holding_adopted] path=%s ticker=%s reason=%s owner=%s",
                path, ticker, reason, owner or "-",
            )
    except Exception:
        logger.exception("[unknown_holding_note_failed] ticker=%s", ticker)


#: `[unknown_holding_adopt_skipped]` 1회/(날짜, 종목, 사유) — 15분마다 같은 줄이 쌓이지 않게.
_ADOPT_SKIP_EMITTED: set[tuple[Any, str, str]] = set()


def _emit_adopt_skipped(ticker: str, reason: str) -> None:
    try:
        key = (now_kst().date(), ticker, reason)
        if key in _ADOPT_SKIP_EMITTED:
            return
        if len(_ADOPT_SKIP_EMITTED) > 2000:
            _ADOPT_SKIP_EMITTED.clear()
        _ADOPT_SKIP_EMITTED.add(key)
        logger.warning("[unknown_holding_adopt_skipped] ticker=%s reason=%s — 방금 팔렸거나 매도 중", ticker, reason)
    except Exception:
        logger.debug("[unknown_holding_adopt_skipped] emit 실패", exc_info=True)


def _adopt_block_reason(registry: Any, order_engine: Any, ticker: str) -> str | None:
    """입양을 막는 사유 — 동기(await 0). 호출 뒤 입양까지 await 를 두지 않는다(D2)."""
    if registry.is_ticker_held_by_any(ticker):
        return "held"
    if registry.is_ticker_sold_today_by_any(ticker):
        return "sold_today"
    if order_engine is not None and ticker in getattr(order_engine, "_selling", ()):
        return "selling"
    return None


async def adopt_balance_only_holding(
    registry: Any, holding: Any, *, order_engine: Any = None, path: str = "sync",
) -> None:
    """15분 동기화 — 장부에 없는 KIS 보유를 판정해 올리고 DB 에도 저장한다(재시작 뒤 표시 유지).

    🔴 잔고 스냅샷은 이미 낡았을 수 있다 — 호출부의 await(PENDING 정리)·이 함수의 조회 await
    동안 매도 체결통보가 보유를 닫았을 수 있다. 그래서 조회 **뒤**에 보유·당일 매도·매도 중을
    다시 보고, 그 판정과 입양 사이에는 await 를 두지 않는다(cycle461 검수 D2 — 방금 판 종목을
    unknown 으로 다시 입양해 또 파는 경로).
    """
    from datetime import date as _date

    from src.engine.strategy_base import Position
    from src.engine.scanner import ticker_names

    ticker = holding.ticker
    sid, reason, owner = await resolve_owner(registry, ticker)
    buy_date: _date | None = None
    if reason == REASON_OWNER:
        # L1 — 주인 입양이면 그 열린 왕복의 첫 BUY 날짜(익일청산·보유일 판정의 기준).
        try:
            from src.db import trade_history as _th

            buy_date = await _th.get_open_roundtrip_first_buy_date(ticker)
        except Exception:
            buy_date = None
        if buy_date is None:
            logger.warning(
                "[unknown_holding_buy_date_unknown] ticker=%s owner=%s — 첫 매수일 모름, 오늘로 둔다",
                ticker, sid,
            )
    # ── 여기부터 입양까지 await 0 ──
    block = _adopt_block_reason(registry, order_engine, ticker)
    if block is not None:
        if block != "held":
            _emit_adopt_skipped(ticker, block)
        return
    target = resolve_target(registry, sid)
    if target is None:
        return
    actual_sid = target.strategy_id
    buy_price = int(holding.avg_price)
    pos = Position(
        ticker=ticker, buy_price=buy_price, quantity=holding.quantity,
        order_no="", strategy_id=actual_sid,
    )
    if buy_date is not None:
        pos.buy_date = buy_date
    target.state.positions[ticker] = pos
    if holding.name:
        ticker_names[ticker] = holding.name
    note_adopted(target, ticker, reason, path=path, owner=owner)
    logger.warning(
        "포지션 동기화 (체결통보 누락 보완): %s %d주 @ %d (전략: %s)",
        holding.name or ticker, holding.quantity, buy_price, actual_sid,
    )
    try:
        from src.db.positions import save_position

        await save_position(
            ticker=ticker, ticker_name=holding.name or "", buy_price=buy_price,
            quantity=holding.quantity, order_no="", strategy_id=actual_sid,
            buy_date=pos.buy_date,
        )
    except Exception:
        logger.warning("[unknown_holding_save_failed] ticker=%s strategy=%s", ticker, actual_sid)


async def rejudge_unknown_positions(registry: Any, order_engine: Any, *, path: str = "sync") -> None:
    """`unknown` 보유 중 팔 사유가 없는 것(판정 보류·재시작으로 사유 잃음)을 다시 판정한다.

    주인이 켜진 전략으로 확인되면 그 전략으로 옮기고 DB 행도 옮긴다. never-raise.
    """
    unknown = registry.get(UNKNOWN_STRATEGY_ID)
    if unknown is None:
        return
    reasons = getattr(unknown, "_reasons", None)
    if not isinstance(reasons, dict):
        return
    selling = getattr(order_engine, "_selling", set()) if order_engine is not None else set()
    for ticker, pos in list(unknown.state.positions.items()):
        try:
            if reasons.get(ticker) in SELLABLE_REASONS or ticker in selling:
                continue
            sid, reason, owner = await resolve_owner(registry, ticker)
            # await 뒤 — 그 사이 체결통보가 포지션을 닫았거나 바꿨으면 손대지 않는다.
            if unknown.state.positions.get(ticker) is not pos or ticker in selling:
                continue
            if sid == UNKNOWN_STRATEGY_ID:
                if reasons.get(ticker) != reason:
                    note_adopted(unknown, ticker, reason, path=f"{path}_rejudge", owner=owner)
                continue
            target = registry.get(sid)
            if target is None or target.state.has_position(ticker):
                logger.warning(
                    "[unknown_holding_reassign_skipped] ticker=%s owner=%s — 주인이 없거나 이미 보유",
                    ticker, sid,
                )
                continue
            unknown.state.positions.pop(ticker, None)
            reasons.pop(ticker, None)
            pos.strategy_id = sid
            target.state.positions[ticker] = pos
            logger.warning(
                "[unknown_holding_reassigned] path=%s ticker=%s owner=%s qty=%d", path, ticker, sid, pos.quantity,
            )
            try:
                from src.db.positions import save_position
                from src.engine.scanner import ticker_names

                await save_position(
                    ticker=ticker, ticker_name=ticker_names.get(ticker, ""), buy_price=pos.buy_price,
                    quantity=pos.quantity, order_no=pos.order_no or "", strategy_id=sid,
                    buy_date=pos.buy_date, high_since_buy=pos.high_since_buy,
                )
            except Exception:
                logger.warning("[unknown_holding_save_failed] ticker=%s strategy=%s", ticker, sid)
        except Exception:
            logger.exception("[unknown_holding_rejudge_failed] ticker=%s", ticker)


async def backup_fire(registry: Any, order_engine: Any) -> None:
    """15분 동기화 백업 청산 — 틱이 안 오는 종목도 창 안이면 판다. never-raise.

    판정·횟수 상한·간격·모드는 `unknown` 전략의 `check_exit_signal` 하나가 정한다(틱 경로와 공유).
    """
    from src.engine.strategy_base import Signal

    unknown = registry.get(UNKNOWN_STRATEGY_ID)
    if unknown is None or order_engine is None:
        return
    for ticker in list(unknown.state.positions.keys()):
        try:
            if ticker in order_engine._selling:
                continue
            signal = unknown.check_exit_signal(ticker, 0, 0)
            if signal != Signal.NONE:
                await order_engine.execute_sell(ticker, signal, UNKNOWN_STRATEGY_ID)
        except Exception:
            logger.exception("[unknown_exit_backup_failed] ticker=%s", ticker)


async def sync_pass(registry: Any, order_engine: Any) -> None:
    """15분 동기화 끝 — 재판정 → 백업 청산. never-raise."""
    try:
        await rejudge_unknown_positions(registry, order_engine, path="sync")
        await backup_fire(registry, order_engine)
    except Exception:
        logger.exception("[unknown_holding_sync_pass_failed]")


def now_kst() -> datetime:
    """시각 seam — 테스트가 monkeypatch 한다."""
    return datetime.now(_KST)
