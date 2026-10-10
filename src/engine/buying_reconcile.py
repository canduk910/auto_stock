"""cycle379 ⑨A(2026-09-27) — 체결 0 으로 끝난 매수의 pending 회수 leaf.

명세 = `_workspace/red/cycle379_buying_reconcile_spec.md`.
사용자 결정 2026-09-27 「9-a 풀어준 종목 재매수가능」 — 해제 뒤 같은 날 재진입을 막지 않는다
(새 당일 차단을 만들지 않는다 — `sold_today`/`buy_blocked_until`/`low_funds_tickers` 무접촉).

`scheduler._sync_positions_from_balance` 의 `reconcile_stale_selling` 위임 **뒤**에서 불린다
(`selling_reconcile.py` 대칭 leaf — 8영역·`scheduler` import 0).

## 한 줄

15분 잔고 sync 끝에서, ``pending_buys`` 에 걸린 종목의 **자기 주문번호 행**이 KIS
일별주문체결(TTTC0081R)에서 ``tot_ccld_qty==0 ∧ rmn_qty==0`` 이고 주문 뒤
``min_age_s``(기본 300초) 가 지났으면 그 pending 을 풀고 장부 행을 CANCELLED 로
적는다. 증거가 하나라도 모자라면 **유지**한다 — 부재는 해제 근거가 아니다.

## 판정 순서 (종목 = 후보 1개)

**A. 메모리 단계** — `await` 0, KIS 호출 0.
- A1 두 전략 이상이 같은 종목을 pending 으로 들면 → 유지 ``ambiguous_owner``.
- A2 어느 전략이든 ``has_position`` 이거나 KIS ``holdings`` 에 수량>0 → 유지 ``held``
  (체결통보 유실로 실제로는 이미 체결됐을 수 있다는 신호 — 이 사이클은 유지만 한다).
- A3 연결 주문(``order_engine._pending_buy_orders`` 중 ``ticker`` 일치) 0개 → 유지
  ``no_order_no``(``execute_buy`` 의 ``await place_order`` 창).

A 를 통과한 후보가 없으면 KIS 호출 없이 반환한다.

**B. KIS 단계** — 오늘 전체 목록 1회 + 후보별 자기 주문번호 조회(패스당
``max_lookups`` 상한, 초과분은 ``deferred``). 양성 증거(전량 미체결·거부·취소 등
``tot_ccld_qty==0 ∧ rmn_qty==0`` 명시값)와 나이(``ord_tmd`` 기준, KST)가 전부
갖춰져야 해제한다. 행이 여럿(SOR)이면 수량은 합, ``ord_tmd`` 는 가장 늦은 값.

**C. 재검증 → 해제** — 마지막 KIS ``await`` 뒤, 동기 헬퍼 ``_release_if_unchanged``
에서 owners·has_position·연결 주문 집합을 다시 본다. 어긋나면 유지 ``raced``
(변이 0). 통과하면 그 자리에서 ``pending_buys``/``pending_buy_amounts``/
``_pending_buy_orders`` 셋만 지운다 — ``_order_qty``/``_order_strategy``/
``_order_ticker``/``_order_exchange``/``_order_division`` 은 **남긴다**(늦은
체결통보가 와도 올바른 전략·수량으로 포지션을 세우는 안전망, 21:30 reset 이 치운다).

**D. 장부** — 연결 주문마다 ``update_trade_status(..., CANCELLED, order_no=o)``
(``match_partial`` 미전달 — PARTIAL·COMPLETED 는 절대 안 뒤집는다). 예외는
``db=error`` 로 마커에 싣고 메모리 해제는 되돌리지 않는다(KIS 사실은 이미 확정).

## never-raise

본체 전체 ``try/except Exception`` → ``logger.exception``. ``CancelledError`` 는
``BaseException`` 서브클래스라 ``except Exception`` 이 잡지 않으므로 자연히 전파된다.

## 로거

``logging.getLogger(__name__)`` = ``src.engine.buying_reconcile`` — 신규 leaf라
옛 접두 연속성이 없다. 영속은 루트 ``_DbLogHandler``(src.* INFO 이상) 몫이고,
``write_log`` 는 import·호출 0(이중 쓰기 금지).
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from src.engine.daily_emit_cap import KstDailyEmitCap
from src.engine.observer_trace import trace_observer_failure
from src.models.trade import TradeStatus, TradeType

logger = logging.getLogger(__name__)

_KST = timezone(timedelta(hours=9))

BUYING_RECONCILE_MIN_AGE_S = 300
MAX_ORDER_LOOKUPS_PER_PASS = 10
ORD_TMD_FUTURE_TOLERANCE_S = 60

_REL_MARKER = "[buying_reconcile]"
_HOLD_MARKER = "[buying_hold]"

#: `[buying_hold]` 레벨 — 조사 신호(WARNING). 그 외(정상 상태)는 INFO(명세 §3).
_WARN_REASONS = frozenset({"held", "fill_seen", "not_found", "bad_row", "ambiguous_owner", "age_unknown"})

_hold_cap: "KstDailyEmitCap[tuple[str, str]]" = KstDailyEmitCap()
#: 그날(KST) 종목별 해제 횟수 — `release_n=` 관측 전용, 행위 무관.
_release_state: dict = {"day": None, "counts": {}}


def reset_buying_reconcile_state() -> None:
    """hold cap · 그날 해제 횟수 초기화 (테스트·운영 훅 — selling_reconcile 선례 답습)."""
    global _hold_cap
    _hold_cap = KstDailyEmitCap()
    _release_state["day"] = None
    _release_state["counts"] = {}


# ---------------------------------------------------------------------------
# 순수 파싱 헬퍼
# ---------------------------------------------------------------------------
def _parse_int_field(row: dict, key: str) -> "int | None":
    """양성 증거는 명시값이어야 한다 — 빈 문자열·비수치·부재는 전부 `None`."""
    v = row.get(key)
    if v is None:
        return None
    s = str(v).strip()
    if not s:
        return None
    try:
        return int(s)
    except ValueError:
        return None


def _parse_int_lenient(row: dict, key: str) -> int:
    """관측 전용 합산(kind/ord/rjct/cncl) — 실패는 0."""
    v = _parse_int_field(row, key)
    return v if v is not None else 0


def _parse_ord_tmd(raw, now: datetime) -> "datetime | None":
    """`HHMMSS` 를 `now` 의 날짜와 합쳐 KST datetime 으로. 실패는 `None`."""
    if raw is None:
        return None
    s = str(raw).strip()
    if len(s) != 6 or not s.isdigit():
        return None
    hour, minute, sec = int(s[0:2]), int(s[2:4]), int(s[4:6])
    if not (0 <= hour < 24 and 0 <= minute < 60 and 0 <= sec < 60):
        return None
    try:
        return datetime(now.year, now.month, now.day, hour, minute, sec, tzinfo=now.tzinfo)
    except ValueError:
        return None


def _row_matches(row: dict, ticker: str, odno: str) -> bool:
    """B5 — `odno`·`pdno` 는 `strip()` 비교, `sll_buy_dvsn_cd` 는 매수(`02`)만."""
    if str(row.get("sll_buy_dvsn_cd", "")).strip() != "02":
        return False
    if str(row.get("pdno", "")).strip() != ticker.strip():
        return False
    if str(row.get("odno", "")).strip() != odno.strip():
        return False
    return True


def _has_open_order_in_list(rows: list, ticker: str) -> bool:
    """B2 — 오늘 전체 목록에 이 종목의 열린(미체결) 매수 주문이 있는가(수동 MTS 포함)."""
    for row in rows:
        if str(row.get("sll_buy_dvsn_cd", "")).strip() != "02":
            continue
        if str(row.get("pdno", "")).strip() != ticker.strip():
            continue
        rmn = _parse_int_field(row, "rmn_qty")
        if rmn is not None and rmn > 0:
            return True
    return False


def _classify_kind(rjct_sum: int, cncl_sum: int, matched: list) -> str:
    """관측 전용(판정에 안 쓴다) — rjct>0→rejected · cncl>0→cancelled · 이름에
    「자동취소」→auto_cancel · 그 밖→zero."""
    if rjct_sum > 0:
        return "rejected"
    if cncl_sum > 0:
        return "cancelled"
    if any("자동취소" in str(r.get("sll_buy_dvsn_cd_name", "")) for r in matched):
        return "auto_cancel"
    return "zero"


def _held_qty_map(holdings) -> "dict[str, int] | None":
    """`None` = holdings 파싱 자체가 실패해 held 여부를 판정할 수 없다(보수적 유지)."""
    out: dict[str, int] = {}
    try:
        for h in holdings:
            qty = h.quantity
            if qty > 0:
                out[h.ticker] = out.get(h.ticker, 0) + qty
    except Exception:
        return None
    return out


def _next_release_n(ticker: str, now: datetime) -> int:
    """그날(KST) 그 종목의 해제 횟수 — 행위 제한 없음, 관측 전용."""
    day = now.date()
    if _release_state["day"] != day:
        _release_state["day"] = day
        _release_state["counts"] = {}
    counts = _release_state["counts"]
    n = counts.get(ticker, 0) + 1
    counts[ticker] = n
    return n


def _emit_hold(ticker: str, strategy_id: str, reason: str, *, odnos, age_s, now: datetime) -> None:
    """유지 판정 관측 1행. never-raise — 호출부 자체 폭발(모의 포함)도 흡수한다."""
    log_fn = logger.warning if reason in _WARN_REASONS else logger.info
    odno_str = ",".join(sorted(odnos)) if odnos else "-"
    age_str = str(int(age_s)) if age_s is not None else "-"
    try:
        _hold_cap.emit_once(
            (ticker, reason), log_fn,
            "[buying_hold] ticker=%s strategy=%s reason=%s odno=%s age_s=%s",
            ticker, strategy_id, reason, odno_str, age_str,
            now=now,
        )
    except Exception:
        try:
            trace_observer_failure(_HOLD_MARKER, f"{ticker}|{reason}", _hold_cap, now=now)
        except Exception:  # pragma: no cover — 2차 예외도 흡수
            pass


# ---------------------------------------------------------------------------
# 재검증 → 해제 (동기 · await 0) — G5 가 요구하는 단일 함수
# ---------------------------------------------------------------------------
def _release_if_unchanged(registry, strategy, order_engine, ticker: str, odnos):
    """마지막 KIS ``await`` 뒤 재검증 — 통과하면 이 자리에서 원자적으로 해제한다.

    ① ``t`` 가 여전히 이 전략 하나의 ``pending_buys`` 에만 있는가(다른 전략이
    가로챘거나 먼저 체결돼 지워졌으면 실패) ② 어느 전략도 ``has_position`` 이
    아닌가 ③ 연결 주문 집합이 평가 시점과 같은가. 하나라도 어긋나면 아무것도
    건드리지 않고 ``(False, None)``.

    cycle436 카드 E (커밋 ①) — ``pending_buy_amounts`` 해제는
    ``StrategyState.release_buy`` 단일 진입점을 거친다(키는 아직 ticker).
    """
    strategies = registry.all()
    owners = [s for s in strategies if ticker in s.state.pending_buys]
    if owners != [strategy]:
        return False, None
    if any(s.state.has_position(ticker) for s in strategies):
        return False, None
    current_odnos = frozenset(
        o for o, info in order_engine._pending_buy_orders.items()
        if info.get("ticker") == ticker
    )
    if current_odnos != frozenset(odnos):
        return False, None

    strategy.state.pending_buys.discard(ticker)
    # cycle436 카드 E (커밋 ①) — 단일 진입점을 거친다. 키는 아직 ticker 다.
    amount = strategy.state.release_buy(ticker)
    for o in odnos:
        order_engine._pending_buy_orders.pop(o, None)
    return True, amount


# ---------------------------------------------------------------------------
# 본체
# ---------------------------------------------------------------------------
async def _reconcile_pass(registry, order_engine, holdings, *, min_age_s: float,
                          now: datetime, max_lookups: int) -> None:
    from src.api.balance import get_daily_orders
    from src.db.trade_history import update_trade_status

    strategies = registry.all()

    owner_map: dict[str, list] = {}
    for s in strategies:
        for t in list(s.state.pending_buys):
            owner_map.setdefault(t, []).append(s)

    if not owner_map:
        return  # 후보 0 — KIS 호출 없이 반환

    held_qty = _held_qty_map(holdings)

    survivors: list = []
    for ticker, owners in owner_map.items():
        if len(owners) >= 2:
            strat_ids = ",".join(o.strategy_id for o in owners)
            _emit_hold(ticker, strat_ids, "ambiguous_owner", odnos=(), age_s=None, now=now)
            continue
        strategy = owners[0]
        if (
            held_qty is None
            or held_qty.get(ticker, 0) > 0
            or any(s.state.has_position(ticker) for s in strategies)
        ):
            _emit_hold(ticker, strategy.strategy_id, "held", odnos=(), age_s=None, now=now)
            continue
        odnos = frozenset(
            o for o, info in order_engine._pending_buy_orders.items()
            if info.get("ticker") == ticker
        )
        if not odnos:
            _emit_hold(ticker, strategy.strategy_id, "no_order_no", odnos=(), age_s=None, now=now)
            continue
        survivors.append((strategy, ticker, odnos))

    if not survivors:
        return  # A 를 통과한 후보가 없으면 KIS 호출 없이 반환

    target_date = now.strftime("%Y%m%d")
    try:
        all_rows = await get_daily_orders(target_date=target_date, exchange="ALL")
    except Exception:
        for strategy, ticker, odnos in survivors:
            _emit_hold(ticker, strategy.strategy_id, "lookup_error", odnos=odnos, age_s=None, now=now)
        return

    remaining: list = []
    for strategy, ticker, odnos in survivors:
        if _has_open_order_in_list(all_rows, ticker):
            _emit_hold(ticker, strategy.strategy_id, "open_order", odnos=odnos, age_s=None, now=now)
            continue
        remaining.append((strategy, ticker, odnos))

    lookups_used = 0
    for strategy, ticker, odnos in remaining:
        if lookups_used + len(odnos) > max_lookups:
            _emit_hold(ticker, strategy.strategy_id, "deferred", odnos=odnos, age_s=None, now=now)
            continue

        rows_by_odno: dict[str, list] = {}
        lookup_failed = False
        for o in odnos:
            lookups_used += 1
            try:
                rows_by_odno[o] = await get_daily_orders(target_date=target_date, exchange="ALL", odno=o)
            except Exception:
                lookup_failed = True
                break
        if lookup_failed:
            _emit_hold(ticker, strategy.strategy_id, "lookup_error", odnos=odnos, age_s=None, now=now)
            continue

        per_order_matched = {
            o: [r for r in rows if _row_matches(r, ticker, o)]
            for o, rows in rows_by_odno.items()
        }
        if any(not m for m in per_order_matched.values()):
            _emit_hold(ticker, strategy.strategy_id, "not_found", odnos=odnos, age_s=None, now=now)
            continue

        matched = [r for rows in per_order_matched.values() for r in rows]
        ccld_vals = [_parse_int_field(r, "tot_ccld_qty") for r in matched]
        rmn_vals = [_parse_int_field(r, "rmn_qty") for r in matched]
        if any(v is None for v in ccld_vals) or any(v is None for v in rmn_vals):
            _emit_hold(ticker, strategy.strategy_id, "bad_row", odnos=odnos, age_s=None, now=now)
            continue

        rmn_sum = sum(rmn_vals)
        if rmn_sum > 0:
            _emit_hold(ticker, strategy.strategy_id, "open_order", odnos=odnos, age_s=None, now=now)
            continue
        ccld_sum = sum(ccld_vals)
        if ccld_sum > 0:
            _emit_hold(ticker, strategy.strategy_id, "fill_seen", odnos=odnos, age_s=None, now=now)
            continue

        parsed_times = [
            t for t in (_parse_ord_tmd(r.get("ord_tmd"), now) for r in matched) if t is not None
        ]
        if not parsed_times:
            _emit_hold(ticker, strategy.strategy_id, "age_unknown", odnos=odnos, age_s=None, now=now)
            continue
        latest = max(parsed_times)
        age_s = (now - latest).total_seconds()
        if age_s < -ORD_TMD_FUTURE_TOLERANCE_S:
            _emit_hold(ticker, strategy.strategy_id, "age_unknown", odnos=odnos, age_s=age_s, now=now)
            continue
        if age_s < min_age_s:
            _emit_hold(ticker, strategy.strategy_id, "too_young", odnos=odnos, age_s=age_s, now=now)
            continue

        rjct_sum = sum(_parse_int_lenient(r, "rjct_qty") for r in matched)
        cncl_sum = sum(_parse_int_lenient(r, "cncl_cfrm_qty") for r in matched)
        ord_sum = sum(_parse_int_lenient(r, "ord_qty") for r in matched)
        kind = _classify_kind(rjct_sum, cncl_sum, matched)

        released, amount = _release_if_unchanged(registry, strategy, order_engine, ticker, odnos)
        if not released:
            _emit_hold(ticker, strategy.strategy_id, "raced", odnos=odnos, age_s=age_s, now=now)
            continue

        db_parts = []
        for o in sorted(odnos):
            try:
                affected = await update_trade_status(
                    ticker, TradeType.BUY, TradeStatus.CANCELLED,
                    strategy=strategy.strategy_id, order_no=o,
                )
                db_parts.append(str(affected))
            except Exception:
                db_parts.append("error")

        release_n = _next_release_n(ticker, now)
        logger.warning(
            "[buying_reconcile] ticker=%s strategy=%s odno=%s kind=%s ord=%s rjct=%s cncl=%s "
            "age_s=%s amount=%s db=%s release_n=%s",
            ticker, strategy.strategy_id, ",".join(sorted(odnos)), kind, ord_sum, rjct_sum, cncl_sum,
            int(age_s), amount if amount is not None else "-", ",".join(db_parts), release_n,
        )


async def reconcile_stale_buying(
    registry, order_engine, holdings, *,
    min_age_s: float = BUYING_RECONCILE_MIN_AGE_S,
    now: "datetime | None" = None,
    max_lookups: int = MAX_ORDER_LOOKUPS_PER_PASS,
) -> None:
    """체결 0 으로 끝난 매수의 pending 을 자기 주문 행의 양성 증거로만 회수한다.

    Args:
        registry: `StrategyRegistry`(읽기 + `pending_buys`/`pending_buy_amounts` 변이).
        order_engine: `OrderEngine`(`_pending_buy_orders` 읽기 + 변이).
        holdings: `get_balance()` 의 보유 목록(`.ticker`/`.quantity`) — 추가 조회 없음.
        min_age_s: 최소 경과 초(기본 300 — 거부·자동취소는 접수 후 수 초 안에 반영된다).
        now: 판정 기준 시각(KST, tz-aware). 생략 시 `datetime.now(KST)`.
        max_lookups: 패스당 주문번호 조회 상한(기본 10).
    """
    try:
        now_kst = now if now is not None else datetime.now(_KST)
        await _reconcile_pass(
            registry, order_engine, holdings,
            min_age_s=min_age_s, now=now_kst, max_lookups=max_lookups,
        )
    except Exception:
        logger.exception("[buying_reconcile_error] 매수 pending 재대조 실패 — graceful(다음 주기 재시도)")
