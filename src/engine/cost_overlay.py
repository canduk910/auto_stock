"""실적 화면에 실비용(수수료·세금) 합치기 — 순수 계산 leaf (cycle411).

명세 = `_workspace/design/2026-10-08_cycle411_cost_overlay.md` (사용자 결정 10-08 Q1~Q4).
Red 메모 = `_workspace/red/cycle411/cost_overlay.md`.

🔴 **8영역(`src/engine/{risk,order_engine,session,scanner,strategy_registry}.py`·
`src/api/order.py`·`src/realtime/**`·`src/auth/**`)·`scheduler.py` 무접촉** — 이 leaf 는 그
어느 것도 import 하지 않는다(`tests/unit/ast/test_cycle411_ast_scope.py::test_e1`). DB 저장값·
마이그레이션도 건드리지 않는다. `trade_history.profit_loss` 의미(세전) 불변.

- `estimate_rates` — `trade_cost_daily` 정산 행으로 수수료·세율을 추정한다(없으면 기본값
  0.142%/0.199%, 사용자 결정 10-08 Q1).
- `trade_costs` — 체결 행(`trade_history`) 단위 비용. 정산 행이 있으면 `trade_cost.allocate_rows`
  (key="id")로 나누고, 없으면 추정 요율 × 체결금액(세금은 매도만, ETF/ETN 매도는 0)을 쓴다.
  정산값이 있으면 ETF 라도 그 값이 정본이다(KIS 가 낸 세금을 0 으로 덮지 않는다).
- `net_twr` — `daily_performance` 행에 일별 비용을 얹어 net TWR(시간가중수익률)을 재누적한다.
  분모는 가장 가까운 이전 0 아닌 `total_asset`(DB 함수 `recompute_daily_performance` 와 같은 식).
- `day_cost_status` — 그날 체결 상태 목록을 settled/estimated/mixed 로 접는다.
- `overlay_pairs` — **async 어댑터**(설계 문서 「새 leaf … 순수 함수 + async 어댑터」). `get_trade_pairs`
  출력(`buy_trade_ids`/`sell_trade_ids` 병행 리스트, cycle411 DB 추가)에 위 순수 함수들로
  fee·tax·net_profit_loss·net_profit_rate·cost_bp·slippage_won·cost_status·allocated 를
  채운다. `/api/history/pnl`·`/api/strategies/te` 가 공유한다. DB 조회 실패 = None(호출부가
  기존 응답을 유지).
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from typing import Iterable

from src.db import trade_cost as trade_cost_db
from src.db._kst import today_kst
from src.engine import trade_cost
from src.engine.etf_like import is_etf_like

logger = logging.getLogger(__name__)

#: 사용자 결정 10-08 Q1 — 최근 30달력일 `trade_cost_daily` 표본이 없을 때의 기본값.
DEFAULT_FEE_RATE = 0.00142
DEFAULT_TAX_RATE = 0.00199

#: cycle411 보완 M2 — 추정 요율 창 길이(달력일). 화면 날짜 범위가 아니라 항상 이 길이다.
RATE_WINDOW_DAYS = 30

# ── 2차 보완 F8 — `today_window_rates()` KST 하루 단위 메모리 캐시 ──────────────
_window_rate_cache: dict[tuple[date, int], dict] = {}

# ── 2차 보완 F6 · 3차 LOW 보완 — 경고 dedupe. 키 = (kind, trad_dt, pdno), **날짜
# 없이** 프로세스 수명 동안 1회(날짜가 바뀌어도 다시 경고하지 않는다 — 3차 검증에서
# "KST 오늘" 을 키에 넣어 매일 재경고하던 것을 LOW 결함으로 지목·시정). 다시 보고
# 싶으면 `_reset_cache_for_tests()`.
_warned_keys: set[tuple[str, object, str]] = set()


def _reset_cache_for_tests() -> None:
    """요율 캐시·경고 dedupe 를 비운다 — 테스트 간 메모리 오염을 막는다(2차 보완 위생).

    `tests/conftest.py::_reset_cost_overlay_memo`(autouse) 가 매 테스트 전·후에 부른다.
    """
    _window_rate_cache.clear()
    _warned_keys.clear()


def _warn_once(kind: str, trad_dt, pdno: str) -> bool:
    """`(kind, trad_dt, pdno)` 당 프로세스 수명 동안 한 번만 True — 그 뒤는 조용하다.

    3차 LOW 보완 — 키에 날짜를 넣지 않는다. 같은 (trad_dt, pdno) 는 다음 KST 날짜에도
    다시 경고하지 않는다(매일 쌓이는 과거 정산 행에 대한 재경고는 신호가 아니라 잡음).
    """
    key = (kind, trad_dt, pdno)
    if key in _warned_keys:
        return False
    _warned_keys.add(key)
    return True


def _num(v) -> Decimal:
    if isinstance(v, Decimal):
        return v
    if v is None:
        return Decimal(0)
    try:
        return Decimal(str(v))
    except InvalidOperation:
        return Decimal(0)


def estimate_rates(cost_rows: list[dict]) -> dict:
    """정산 행으로 수수료·세율을 추정한다 — 표본 없으면 기본값(사용자 결정 10-08 Q1)."""
    if not cost_rows:
        return {"fee_rate": DEFAULT_FEE_RATE, "tax_rate": DEFAULT_TAX_RATE, "source": "default"}

    fee_sum = sum((_num(c.get("fee")) for c in cost_rows), Decimal(0))
    tax_sum = sum((_num(c.get("tl_tax")) for c in cost_rows), Decimal(0))
    vol = sum((_num(c.get("buy_amt")) + _num(c.get("sll_amt")) for c in cost_rows), Decimal(0))
    sell_vol = sum((_num(c.get("sll_amt")) for c in cost_rows), Decimal(0))

    fee_rate = float(fee_sum / vol) if vol else DEFAULT_FEE_RATE
    tax_rate = float(tax_sum / sell_vol) if sell_vol else DEFAULT_TAX_RATE
    return {"fee_rate": fee_rate, "tax_rate": tax_rate, "source": "measured"}


async def today_window_rates(window_days: int = RATE_WINDOW_DAYS) -> dict:
    """서버 오늘(KST) 기준 최근 `window_days`일 정산 행으로 요율을 추정한다(cycle411 보완 M2).

    화면/계산 범위의 날짜(screen range)가 아니라 **항상 이 창**이다 — 모든 라우트
    (`/api/costs/{today,daily}` · `/api/history` · `/api/history/pnl` ·
    `/api/performance/daily`·`summary` · `/api/strategies/te` · `/api/balance`) 공통.

    2차 보완 F8 — 결과를 **KST 날짜 단위로 메모리 캐시**한다(같은 날 두 번째 호출부터는
    DB 를 읽지 않는다, 다음 날은 다시 읽는다). 조회 실패(예외)는 캐시하지 않는다 —
    다음 호출이 다시 시도한다(`_window_rate_cache` 에 쓰기 전에 예외가 전파된다).
    """
    today = today_kst()
    cache_key = (today, window_days)
    cached = _window_rate_cache.get(cache_key)
    if cached is not None:
        return cached
    rows = await trade_cost_db.get_daily_range(today - timedelta(days=window_days), today)
    rates = estimate_rates(rows)
    _window_rate_cache[cache_key] = rates
    return rates


async def stock_master_etf_flags(trades: list[dict]) -> dict[str, bool]:
    """체결 행들의 종목코드마다 구분 코드로 ETF 를 판정한다(M3, 2차 보완 F1 — 일괄 조회).

    `src.db.stock_master` **모듈 속성 경유**(테스트가 그 모듈의 `get_etf_group_codes` 를
    간다) — 종목마다 `stock_master.get()` 을 직렬로 부르던 것을 **`pg.fetch` 1회**(고유
    종목 전부)로 바꾼다(`stock_master.get` 호출 0). 코드가 없는·조회 실패 종목은 결과에서
    제외한다 — `trade_costs(..., etf_flags=...)` 의 `etf_tickers`→이름 폴백이 대신한다.
    """
    from src.db import stock_master

    names: dict[str, str | None] = {}
    for t in trades:
        tk = t.get("ticker")
        if tk and tk not in names:
            names[tk] = t.get("ticker_name")
    if not names:
        return {}

    try:
        codes = await stock_master.get_etf_group_codes(list(names.keys()))
    except Exception:
        logger.debug("[cost_overlay] stock_master 일괄 조회 실패 — 이름 폴백", exc_info=True)
        return {}

    out: dict[str, bool] = {}
    for tk, code in codes.items():
        if not code:
            continue
        out[tk] = is_etf_like({"scty_grp_id_cd": code}, names.get(tk))
    return out


def _is_etf(
    ticker: str,
    ticker_name: str | None,
    etf_tickers: frozenset[str],
    etf_flags: dict[str, bool] | None = None,
) -> bool:
    if etf_flags is not None and ticker in etf_flags:
        return etf_flags[ticker]
    if ticker in etf_tickers:
        return True
    return is_etf_like(None, ticker_name)


def trade_costs(
    cost_rows: list[dict],
    trades: list[dict],
    rates: dict,
    etf_tickers: frozenset[str] = frozenset(),
    etf_flags: dict[str, bool] | None = None,
) -> dict:
    """체결 행(`id`) 단위 비용 — 정산 행이 있으면 대사값, 없으면 추정 요율.

    반환 = `{id: {"fee": float, "tax": float, "cost_status": "settled"|"estimated",
    "allocated": bool}}`. `allocated` = 같은 날·종목 정산 1행을 2개 이상 체결 행이 나눠
    받았을 때만 True(추정 행은 항상 False — 사용자 결정 10-08 §6).

    `etf_flags`(cycle411 보완 M3) — `{ticker: bool}`. 판정이 있는 종목은 그 값만 보고
    (이름 키워드 폴백보다 우선), 없는 종목은 `etf_tickers` → 이름 폴백(기존대로).
    """
    settled_rows = trade_cost.allocate_rows(cost_rows, trades, key="id")
    settled_by_id = {r["id"]: r for r in settled_rows if r["id"] is not None}

    # 2차 보완 F5(a) — 「매도 없음」은 정산 행의 `sll_amt` 가 아니라 **그 (날짜, 종목)의
    # 체결 집합**으로 판정한다. 정산 행에 매도금액·세금이 있어도 실제 체결(trade_history)
    # 에 SELL 이 없으면(예: 당일 KIS 정산 지연·수기 조정·배분 오류) allocate_rows 의
    # sell_share→total_share 폴백이 그 세금을 매수 행에 몰아준다 — 몰지 않고 미배분으로
    # 둔다(id 단위에서만 — 전략 귀속 `attribute`/`allocate_rows(key="strategy")` 는 트랙 C
    # 요약 행위 보존, H2c).
    sell_fill_keys = {
        (t.get("trade_date"), str(t.get("ticker") or ""))
        for t in trades
        if str(t.get("trade_type") or "").upper() == "SELL"
        and _num(t.get("price")) * _num(t.get("quantity")) > 0
    }

    # 2차 보완 F5(b) — 짝이 되는 체결이 **하나도 없는** 정산 행은 비용이 조용히 사라지지
    # 않게 경고한다(반환 dict 에는 아무것도 더하지 않는다 — 귀속할 체결 id 가 없다).
    # `no_sell_tax_keys` 보다 **먼저** 계산한다 — 체결이 전혀 없는 키는 "매도 없이 잡힌
    # 세금"(아래)도 동시에 참이라, 먼저 걷어내지 않으면 같은 정산 행에 경고가 두 줄
    # 남는다(3차 LOW 보완 — 「짝 자체가 없음」 과 「짝은 있는데 매도가 아님」 은 서로 다른
    # 사실이라 하나만 보인다 — 더 근본적인 unmatched_cost 가 이긴다).
    trade_keys = {(t.get("trade_date"), str(t.get("ticker") or "")) for t in trades}
    unmatched_cost_keys = {
        (c.get("trad_dt"), str(c.get("pdno") or ""))
        for c in cost_rows
        if (c.get("trad_dt"), str(c.get("pdno") or "")) not in trade_keys
    }
    for key in unmatched_cost_keys:
        if _warn_once("unmatched_cost", key[0], key[1]):
            logger.warning(
                "[cost_overlay_unmatched_cost] trad_dt=%s pdno=%s — 짝 체결 없음, 비용 미배정",
                key[0], key[1],
            )

    no_sell_tax_keys = {
        (c.get("trad_dt"), str(c.get("pdno") or ""))
        for c in cost_rows
        if _num(c.get("tl_tax")) > 0
        and (c.get("trad_dt"), str(c.get("pdno") or "")) not in sell_fill_keys
        and (c.get("trad_dt"), str(c.get("pdno") or "")) not in unmatched_cost_keys
    }
    for key in no_sell_tax_keys:
        if _warn_once("tax_unallocated", key[0], key[1]):
            logger.warning(
                "[cost_overlay_tax_unallocated] trad_dt=%s pdno=%s — 매도 체결 없이 잡힌 세금, 미배분",
                key[0], key[1],
            )
    if no_sell_tax_keys:
        for r in settled_by_id.values():
            if (r.get("trad_dt"), str(r.get("pdno") or "")) in no_sell_tax_keys:
                r["tl_tax"] = 0.0

    out: dict = {}
    for t in trades:
        tid = t.get("id")
        if tid in settled_by_id:
            r = settled_by_id[tid]
            out[tid] = {
                "fee": r["fee"],
                "tax": r["tl_tax"],
                "cost_status": "settled",
                "allocated": bool(r["estimated"]),
            }
            continue

        price = _num(t.get("price"))
        qty = _num(t.get("quantity"))
        amt = float(price * qty)
        side = str(t.get("trade_type") or "").upper()
        fee = amt * rates["fee_rate"]
        tax = 0.0
        if side == "SELL" and not _is_etf(
            str(t.get("ticker") or ""), t.get("ticker_name"), etf_tickers, etf_flags
        ):
            tax = amt * rates["tax_rate"]
        out[tid] = {"fee": fee, "tax": tax, "cost_status": "estimated", "allocated": False}
    return out


def _settlement_id_groups(cost_rows: list[dict], trades: list[dict]) -> dict[int, frozenset[int]]:
    """정산 행이 있는 (날짜, 종목) 마다 그 체결 id 집합 — 페어 밖 배분 판정용(F11).

    `trade_costs(...)[id]["allocated"]`(= `allocate_rows(key="id")` 의 `estimated`)는 "이
    id 가 정산 1행을 다른 id 와 나눠 받았나" 만 말해 **같은 페어 안의 매수·매도** 도
    True 로 잡는다(당일 매수→당일 매도 단일 페어가 늘 "배분"으로 보이던 결함). 이
    함수는 (날짜,종목)별 **실제 id 집합**을 돌려줘, 그 집합이 한 페어의 id 전부를
    넘어서는지(=페어 밖 체결과 나눴는지)를 호출부가 직접 비교하게 한다.
    """
    cost_keys = {(c.get("trad_dt"), str(c.get("pdno") or "")) for c in cost_rows}
    groups: dict[tuple, set[int]] = {}
    for t in trades:
        tid = t.get("id")
        if tid is None:
            continue
        key = (t.get("trade_date"), str(t.get("ticker") or ""))
        if key not in cost_keys:
            continue
        groups.setdefault(key, set()).add(tid)
    out: dict[int, frozenset[int]] = {}
    for ids in groups.values():
        frozen = frozenset(ids)
        for tid in ids:
            out[tid] = frozen
    return out


def _pair_allocated_outside(own_ids: set[int], id_groups: dict[int, frozenset[int]]) -> bool:
    """`own_ids`(한 페어의 체결 id 전부) 중 하나라도 정산 그룹이 페어 밖으로 넘치면 True.

    (F11, 결정 6 갱신) — 같은 날 사고 판 단일 페어(정산 1행을 자기 매수·매도 행만 나눠
    받음)는 False. 다른 전략·다른 페어의 체결과 나눠 받았을 때만 True.
    """
    for tid in own_ids:
        group = id_groups.get(tid)
        if group and not group.issubset(own_ids):
            return True
    return False


def day_cost_status(statuses: Iterable[str]) -> str:
    """그날 체결 상태 목록을 settled/estimated/mixed 로 접는다."""
    uniq = set(statuses)
    if not uniq or uniq == {"settled"}:
        return "settled"
    if uniq == {"estimated"}:
        return "estimated"
    return "mixed"


def net_twr(records: list[dict], costs_by_date: dict) -> list[dict]:
    """`daily_performance` 행(오름차순)에 일별 비용을 얹어 net TWR 을 재누적한다.

    반환 행 = `date, daily_fee, daily_tax, daily_net_pnl, net_daily_profit_rate,
    net_cumulative_return_rate, cost_status`. 분모는 가장 가까운 이전 0 아닌
    `total_asset`(DB 함수 `recompute_daily_performance` 와 같은 식). 비용 0 이면 net 일·누적
    = gross 일·누적(N2).
    """
    out: list[dict] = []
    prev_nonzero_asset: float | None = None
    cum = 1.0
    for rec in records:
        d = rec["date"]
        cost = costs_by_date.get(d, {})
        fee = float(cost.get("fee") or 0.0)
        tax = float(cost.get("tax") or 0.0)
        cost_status = cost.get("cost_status")

        gross_pnl = float(rec.get("daily_realized_pnl") or 0.0)
        net_pnl = gross_pnl - fee - tax

        asset = float(rec.get("total_asset") or 0.0)
        denom = prev_nonzero_asset if prev_nonzero_asset else asset
        if fee == 0.0 and tax == 0.0:
            # N2 — 비용이 없으면 기존 daily_profit_rate 를 그대로 쓴다(부동소수 재계산 오차 없음).
            net_rate = float(rec.get("daily_profit_rate") or 0.0)
        else:
            net_rate = (net_pnl / denom * 100) if denom else 0.0

        cum *= 1 + net_rate / 100
        out.append({
            "date": d,
            "daily_fee": fee,
            "daily_tax": tax,
            "daily_net_pnl": net_pnl,
            "net_daily_profit_rate": net_rate,
            "net_cumulative_return_rate": (cum - 1) * 100,
            "cost_status": cost_status,
        })

        if asset != 0:
            prev_nonzero_asset = asset
    return out


async def overlay_pairs(pairs: list[dict]) -> dict[int, dict] | None:
    """페어마다 fee·tax·net_profit_loss·net_profit_rate·cost_bp·slippage_won·cost_status·
    allocated 를 채운다(async 어댑터, `/api/history/pnl`·`/api/strategies/te` 공유).

    거래 단위 귀속 — `buy_trade_ids`·`sell_trade_ids`(cycle411 DB 추가)로 체결 행 비용을
    모아 더한다(수수료 = 매수+매도 전부, 세금 = 매도 행만 — 매수 행의 세금은 이미 0).
    보유 중(open) 페어 = 낸 매수 수수료(정산/추정) × 남은 수량 비율 + 예상 매도비용(현재가
    추정, 사용자 결정 10-08 §3·§5 — 현재가는 `buy_price + profit_loss/buy_qty` 로 페어
    안에서만 역산한다, scanner 시세 캐시에 의존하지 않는다). 분할 매도 뒤(`partial_sell_trade_ids`,
    cycle411 보완 L2) 판 몫은 `partial_fee`(매수 수수료 × 판 비율 + 매도 수수료)·`partial_tax`
    (매도세)로 따로 낸다 — 총합 보존(보유 몫 낸 수수료 + 판 몫 = 정산 합). 추정 행의 `allocated`
    는 항상 False(§6).

    요율은 화면 날짜 범위가 아니라 **서버 오늘 기준 30일 창**(M2, `today_window_rates`)이고,
    ETF 판정은 `stock_master` 구분 코드 우선(M3, `stock_master_etf_flags`)이다. `slippage_won`
    은 그 페어 체결 행 중 `order_price` 가 하나도 없으면 `None`(M4, 있으면 덮인 행만 합산).

    비용 조회가 실패하면 `[cost_overlay_unavailable]` WARNING 을 남기고 None 을 돌려준다
    (호출부가 기존 응답을 그대로 둔다 — 사용자 결정 10-08 §2).

    돌아오는 `{id: trade}` 맵은 `slippage_n`(order_price 덮인 체결 행 수) 집계용.
    """
    dates: list[date] = []
    for p in pairs:
        for key in ("buy_date", "sell_date"):
            raw = p.get(key)
            if not raw:
                continue
            try:
                dates.append(date.fromisoformat(str(raw)))
            except ValueError:
                pass
    if not dates:
        return {}
    # cycle411 보완 L2 — open 페어의 분할 매도(`partial_sell_trade_ids`)는 날짜를 모른다
    # (매수일 이후 ~ 지금 사이). 상한을 "오늘"까지 넓혀 그 체결·정산 행을 범위 안에 둔다.
    dates.append(today_kst())

    try:
        cost_rows = await trade_cost_db.get_daily_range(min(dates), max(dates))
        trades = await trade_cost_db.get_trades_by_status(
            min(dates), max(dates), ["COMPLETED", "PARTIAL"])
        rates = await today_window_rates()
        etf_flags = await stock_master_etf_flags(trades)
    except Exception:
        logger.warning("[cost_overlay_unavailable] 실비용 조회 실패", exc_info=True)
        return None

    costs = trade_costs(cost_rows, trades, rates, etf_flags=etf_flags)
    trades_by_id = {t["id"]: t for t in trades if t.get("id") is not None}
    id_groups = _settlement_id_groups(cost_rows, trades)

    for p in pairs:
        buy_ids = list(p.get("buy_trade_ids") or [])
        sell_ids = list(p.get("sell_trade_ids") or [])
        partial_ids = list(p.get("partial_sell_trade_ids") or [])
        ids = buy_ids + sell_ids
        entries = [costs[i] for i in ids if i in costs]

        ticker = p.get("ticker") or ""
        etf_flag = etf_flags.get(ticker)
        is_etf = etf_flag if etf_flag is not None else is_etf_like(None, p.get("ticker_name"))

        if p.get("status") == "open":
            buy_entries = [costs[i] for i in buy_ids if i in costs]
            buy_fee_total = sum(c["fee"] for c in buy_entries)

            total_buy_qty = sum(
                float(trades_by_id[i]["quantity"]) for i in buy_ids if i in trades_by_id
            )
            remaining_qty = float(p.get("buy_qty") or 0)
            ratio_remaining = (remaining_qty / total_buy_qty) if total_buy_qty else 1.0
            ratio_sold = 1.0 - ratio_remaining

            # 분할 매도 뒤(`partial_sell_trade_ids`) 판 몫 — 현재가(2차 보완 B1) 와
            # 무관하게 **이미 낸** 비용이라 그대로 집계한다.
            partial_entries = [costs[i] for i in partial_ids if i in costs]
            p["partial_fee"] = buy_fee_total * ratio_sold + sum(c["fee"] for c in partial_entries)
            p["partial_tax"] = sum(c["tax"] for c in partial_entries)

            pl = p.get("profit_loss")
            if pl is None:
                # 2차 보완 B1 — 현재가를 모르면(21:30 이후·재기동 직후·휴장일) 예상
                # 매도비용·순손익을 0 으로 치지 않는다. fee·tax 자체를 모른다로 둔다.
                fee = None
                tax = None
            else:
                buy_price = float(p.get("buy_price") or 0)
                cur_price = (
                    (buy_price * remaining_qty + float(pl)) / remaining_qty
                    if remaining_qty else 0.0
                )
                est_sell_amt = cur_price * remaining_qty
                fee_est = est_sell_amt * rates["fee_rate"]
                tax_est = 0.0 if is_etf else est_sell_amt * rates["tax_rate"]
                fee = buy_fee_total * ratio_remaining + fee_est
                tax = tax_est
            cost_status, allocated = "estimated", False
        else:
            fee = sum(c["fee"] for c in entries)
            tax = sum(c["tax"] for c in entries)
            statuses = [c["cost_status"] for c in entries] or ["estimated"]
            cost_status = day_cost_status(statuses)
            # 2차 보완 F11(결정 6 갱신) — 페어 밖 체결과 나눴을 때만 True.
            own_ids = set(buy_ids) | set(sell_ids) | set(partial_ids)
            allocated = _pair_allocated_outside(own_ids, id_groups)

        p["fee"] = fee
        p["tax"] = tax
        p["cost_status"] = cost_status
        p["allocated"] = allocated

        if fee is None or tax is None:
            # B1 — fee·tax 를 모르면 그에 의존하는 칸도 전부 모른다(0 으로 치지 않는다).
            p["net_profit_loss"] = None
            p["net_profit_rate"] = None
            p["cost_bp"] = None
        else:
            p["net_profit_loss"] = float(p.get("profit_loss") or 0.0) - fee - tax

            buy_amt = float(p.get("buy_price") or 0) * float(p.get("buy_qty") or 0)
            p["net_profit_rate"] = (
                round(p["net_profit_loss"] / buy_amt * 100, 4) if buy_amt else None
            )

            proceeds = (float(p.get("sell_price") or 0) * float(p.get("sell_qty") or 0)
                        if p.get("sell_qty") else 0.0)
            denom = (buy_amt + proceeds) / 2 if proceeds else buy_amt
            p["cost_bp"] = round((fee + tax) / denom * 1e4, 4) if denom else None

        slip = 0.0
        covered = False
        for i in (p.get("buy_trade_ids") or []):
            t = trades_by_id.get(i)
            if t and t.get("order_price") is not None:
                covered = True
                slip += (float(t["price"]) - float(t["order_price"])) * float(t["quantity"])
        for i in (p.get("sell_trade_ids") or []):
            t = trades_by_id.get(i)
            if t and t.get("order_price") is not None:
                covered = True
                slip += (float(t["order_price"]) - float(t["price"])) * float(t["quantity"])
        p["slippage_won"] = slip if covered else None

    return trades_by_id
