"""잔고 조회 라우트: /api/balance/*"""

from __future__ import annotations

import logging
from datetime import date

from fastapi import APIRouter

from src.api.balance import get_balance, get_buyable
from src.db import trade_cost as trade_cost_db
from src.db import trade_history as trade_history_db
from src.db._kst import today_kst
from src.db.stock_master import get as stock_master_get
from src.engine import cost_overlay
from src.engine.etf_like import is_etf_like
from src.engine.position_buy_date import merge_buy_date, resolve_engine_buy_dates
from src.engine.position_exit_lines import build_exit_line_map
from src.engine.sector_naming import resolve_sector_name
from src.models.response import ApiResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/balance", tags=["balance"])

#: `_get_cost_range` 가 (start, end) 범위를 못 읽었을 때 캐시에 두는 표식(조회 재시도를
#: 요청 안에서 또 하지 않는다 — None 은 "아직 안 찾아봄" 과 겹쳐 쓸 수 없다, 2차 보완 F3·F8b).
_RANGE_FAILED = object()


async def _get_cost_range(
    start: date, end: date, range_cache: dict,
) -> tuple[list[dict], list[dict]] | None:
    """`(start, end)` 정산 행·체결 행을 **요청 안에서 한 번만** 읽는다(2차 보완 F8b).

    보유 종목이 여럿이고 같은 날 샀으면 `_open_pair_buy_fee` 가 같은 범위를 여러 번
    부른다 — `range_cache` 를 호출부(`balance()`)가 한 번 만들어 공유한다. 조회 실패는
    `None`(그 범위는 이 요청 안에서 다시 시도하지 않는다 — 실패를 캐시하는 것은 이
    요청-로컬 캐시에서만 안전하다, 영속 캐시(`today_window_rates`)는 F8 규약이 달라
    실패를 캐시하지 않는다).
    """
    key = (start, end)
    cached = range_cache.get(key, None)
    if cached is _RANGE_FAILED:
        return None
    if cached is not None:
        return cached
    try:
        cost_rows = await trade_cost_db.get_daily_range(start, end)
        full_trades = await trade_cost_db.get_trades_by_status(start, end)
    except Exception:
        logger.debug("[cost_overlay] 잔고 비용 범위 조회 실패(%s~%s) graceful", start, end,
                    exc_info=True)
        range_cache[key] = _RANGE_FAILED
        return None
    result = (cost_rows, full_trades)
    range_cache[key] = result
    return result


async def _open_pair_buy_fee(
    pair: dict, rates: dict, range_cache: dict,
) -> tuple[float | None, str | None]:
    """`open` 페어의 매수 수수료 — 정산 있으면 대사값, 없으면 추정 요율(cycle411 보완 M1).

    분할 매도 뒤(남은 수량 < 원 매수 수량)면 남은 수량 비율만 센다(L2 와 같은 식).
    2차 보완 F2 — 조회 범위는 매수일 **하루** 가 아니라 **매수일 ~ 오늘**(여러 날 매수가
    `buy_trade_ids` 에 섞여 있으면 하루만 보면 다른 날 매수분의 수수료를 놓친다). 2차
    보완 F3 — 비용 조회 자체가 실패하면 `(None, None)`(「모름」 ≠ 0). 페어·매수일이 없는
    경우만 `(0.0, "estimated")` graceful(계산할 근거가 원래 없다) — 3차 LOW 보완: 범위
    조회는 성공했는데 그 체결 id 를 결과에서 못 찾은 경우(데이터 불일치)도 `(None, None)`
    이다(근거가 있는데 못 찾은 것은 "없다" 가 아니라 "모른다").
    """
    ids = pair.get("buy_trade_ids") or []
    buy_date_raw = pair.get("buy_date")
    if not ids or not buy_date_raw:
        return 0.0, "estimated"
    try:
        d = date.fromisoformat(str(buy_date_raw))
    except ValueError:
        return 0.0, "estimated"
    end = max(d, today_kst())

    result = await _get_cost_range(d, end, range_cache)
    if result is None:
        return None, None
    cost_rows, full_trades = result

    costs = cost_overlay.trade_costs(cost_rows, full_trades, rates)
    entries = [costs[i] for i in ids if i in costs]
    if not entries:
        # 3차 LOW 보완 — 범위 조회 자체는 성공했는데 이 페어의 체결 id 가 그 결과에
        # 하나도 없다(데이터 불일치 — 날짜 범위 추론이 어긋났거나 상태 필터에 걸림).
        # 계산할 근거가 **있는데 못 찾은** 상태라 0 으로 지어내지 않는다 — 모른다(None).
        # (위 74·78행의 "근거가 원래 없다" 분기와는 다르다 — 거기는 기존대로 둔다.)
        return None, None

    fee_total = sum(c["fee"] for c in entries)
    total_buy_qty = sum(float(t["quantity"]) for t in full_trades if t.get("id") in ids)
    remaining_qty = float(pair.get("buy_qty") or 0)
    ratio = (remaining_qty / total_buy_qty) if total_buy_qty else 1.0
    status = cost_overlay.day_cost_status([c["cost_status"] for c in entries])
    return fee_total * ratio, status


async def _buy_fee_paid_by_ticker(
    holdings: list, rates: dict, range_cache: dict,
) -> dict[str, tuple[float | None, str | None]]:
    """보유 종목마다 `(buy_fee_paid, buy_fee_status)` (cycle411 보완 M1).

    엔진 페어(`trade_history.get_trade_pairs` 모듈 속성 경유)의 open 페어가 있으면 그
    매수 수수료, 없으면(수동 매수 등) 매입금액 × 추정 수수료율 · "estimated". 2차 보완
    F3 — open 페어 중 하나라도 비용 조회가 실패하면(「모름」) 그 종목 전체를 `(None,
    None)` 으로 둔다(알고 있는 몫과 모르는 몫을 더해 그럴듯한 숫자를 만들지 않는다).
    """
    out: dict[str, tuple[float | None, str | None]] = {}
    for h in holdings:
        try:
            pairs = await trade_history_db.get_trade_pairs(ticker=h.ticker)
        except Exception:
            logger.debug("[cost_overlay] 잔고 페어 조회 실패(ticker=%s) graceful", h.ticker,
                        exc_info=True)
            pairs = []
        open_pairs = [p for p in pairs if p.get("status") == "open"]
        if not open_pairs:
            out[h.ticker] = (float(h.purchase_amount or 0) * rates["fee_rate"], "estimated")
            continue
        fee_total = 0.0
        statuses: list[str] = []
        unknown = False
        for p in open_pairs:
            fee, status = await _open_pair_buy_fee(p, rates, range_cache)
            if fee is None:
                unknown = True
                continue
            fee_total += fee
            statuses.append(status)
        if unknown:
            out[h.ticker] = (None, None)
        else:
            out[h.ticker] = (
                fee_total,
                cost_overlay.day_cost_status(statuses) if statuses else "estimated",
            )
    return out


@router.get("", response_model=ApiResponse)
async def balance():
    """보유종목 + 계좌 요약을 반환한다.

    J1 (2026-05-11): 각 holding 에 stock_master(CTPF1002R 캐시) 필드
    `nxt_tradable / krx_halted / excg_dvsn_cd` 를 join 한다.
    보유 종목 수는 통상 10 미만이라 sequential await 비용 무시 가능.
    캐시 miss → None / 조회 예외 → 종목별 흡수 후 None.
    """
    # cycle406 L2 — `get_balance()` 소진 예외(KIS 재시도 소진 등)를 ASGI 미처리 500 으로
    # 내보내지 않는다. 내부 호출부(`portfolio.py::_net_asset_graceful` 등)는 이미 흡수하지만
    # 이 라우트는 잔고 자체가 본문이라 200+빈 데이터로 꾸밀 수 없다 — `success=False` 로
    # 흡수한다(루트 CLAUDE.md API 응답 래퍼 규약).
    try:
        holdings, summary = await get_balance()
    except Exception as exc:  # noqa: BLE001 — 원인 불문 흡수, 메시지에 남긴다
        logger.warning("[balance] get_balance 실패 — success=False 로 흡수: %s", exc, exc_info=True)
        return ApiResponse(success=False, data=None, message=f"잔고 조회 실패: {exc}")

    # cycle411 — 예상 매도비용 요율(수수료율+세율, ETF 는 수수료율만). 서버 오늘 기준
    # 30일 창(M2, `today_window_rates`)에 정산 표본이 없으면 기본값으로 떨어진다 — DB
    # 조회 실패도 같은 fail-open(「살까 말까」 가 아니라 화면 참고용 추정이라 전체
    # 잔고를 막지 않는다).
    try:
        sell_rates = await cost_overlay.today_window_rates()
    except Exception:
        logger.debug("[cost_overlay] 잔고 요율 조회 실패 graceful — 기본값", exc_info=True)
        sell_rates = {"fee_rate": cost_overlay.DEFAULT_FEE_RATE,
                     "tax_rate": cost_overlay.DEFAULT_TAX_RATE, "source": "default"}

    # cycle411 보완 M1 — 보유마다 매수 수수료(buy_fee_paid)·상태(buy_fee_status).
    # 2차 보완 F8b — `range_cache` 를 이 요청 안에서 공유해 같은 (start, end) 범위를
    # 보유 종목 수만큼 중복 조회하지 않는다(같은 날 산 종목이 여럿인 경우).
    range_cache: dict = {}
    try:
        buy_fee_by_ticker = await _buy_fee_paid_by_ticker(holdings, sell_rates, range_cache)
    except Exception:
        logger.debug("[cost_overlay] 잔고 매수수수료 조회 실패 graceful", exc_info=True)
        buy_fee_by_ticker = {}

    # cycle339 — 종목별 청산선(손절가·목표가). in-memory registry 조회뿐이라
    # DB·KIS 왕복이 0 이다. 🔴 registry 를 못 읽어도 잔고는 그대로 나가야 하므로
    # graceful — 그때는 전 종목이 `—` 로 보인다(숫자를 지어내지 않는다).
    exit_lines: dict = {}
    try:
        from src.engine.scheduler import trading_scheduler

        exit_lines = build_exit_line_map(
            trading_scheduler.registry.all(),
            [h.ticker for h in holdings],
            engine_running=bool(trading_scheduler.is_running),
        )
    except Exception:
        logger.debug("[exit_lines] registry 조회 실패 graceful", exc_info=True)

    # cycle397 — 매입일(최초 매입일). 1순위 = 엔진 포지션(엔진이 실제로 쓰는 값),
    # 2순위 = DB `positions.buy_date`(수동 보유·엔진 정지 중의 폴백). 두 출처가
    # 모두 있으면 더 이른 날짜(「최초」 규약). registry/DB 조회 실패는 모두
    # graceful — 그 종목 칸만 `None`(화면 `—`), 잔고 자체는 그대로 나간다.
    engine_buy_dates: dict[str, str] = {}
    try:
        from src.engine.scheduler import trading_scheduler

        engine_buy_dates = resolve_engine_buy_dates(trading_scheduler.registry.all())
    except Exception:
        logger.debug("[buy_date] registry 조회 실패 graceful", exc_info=True)

    db_buy_dates: dict = {}
    try:
        from src.db.positions import get_buy_dates

        db_buy_dates = await get_buy_dates([h.ticker for h in holdings])
    except Exception:
        logger.debug("[buy_date] DB 조회 실패 graceful", exc_info=True)

    enriched_holdings: list[dict] = []
    for h in holdings:
        payload = h.model_dump()
        try:
            basics = await stock_master_get(h.ticker)
        except Exception as exc:  # noqa: BLE001 — 종목별 흡수, 나머지 계속
            logger.warning(
                "stock_master 조회 실패 (ticker=%s): %s — None 으로 응답", h.ticker, exc
            )
            basics = None
        if basics is not None:
            payload["nxt_tradable"] = bool(basics.nxt_tradable)
            payload["krx_halted"] = bool(basics.krx_halted)
            payload["excg_dvsn_cd"] = basics.excg_dvsn_cd or None
        # basics is None: payload 의 nxt_tradable/krx_halted/excg_dvsn_cd 기본 None 유지
        # cycle411 — 예상 매도비용 요율(ETF 는 수수료율만). 화면이 평가금액에 곱한다.
        is_etf = is_etf_like(getattr(basics, "raw", None) if basics is not None else None, h.name)
        payload["sell_cost_rate"] = (
            sell_rates["fee_rate"] if is_etf else sell_rates["fee_rate"] + sell_rates["tax_rate"]
        )
        payload["cost_status"] = "estimated"
        # cycle411 보완 M1 — 이 종목이 낸(또는 추정한) 매수 수수료. 3차 LOW 보완 —
        # 기본값은 `(None, None)`이다. `h.ticker` 가 이 dict 에 없다는 것은
        # `_buy_fee_paid_by_ticker` 가 (그 종목이 아니라) **통째로** 예외를 내 위에서
        # `buy_fee_by_ticker = {}` 로 흡수됐다는 뜻이라 — 모든 보유종목이 "모른다" 다.
        # `(0.0, "estimated")` 로 지어내면 실패를 "수수료 0원짜리 추정" 으로 보여준다.
        fee_paid, fee_status = buy_fee_by_ticker.get(h.ticker, (None, None))
        payload["buy_fee_paid"] = fee_paid
        payload["buy_fee_status"] = fee_status
        # 섹터명 — 위에서 이미 조회한 basics.raw 를 주입해 재조회를 막는다
        # (`sector_naming` 단일 진실원: bstp_kor_isnm → master_raw → 미분류).
        payload["sector"] = await resolve_sector_name(
            h.ticker,
            basics_raw=(getattr(basics, "raw", None) if basics is not None else None),
        )
        # cycle339 — 청산선 4필드. 판정 불가는 전부 None 이고 화면이 `—` 를 그린다.
        payload.update(
            exit_lines.get(h.ticker)
            or {
                "strategy_id": None,
                "stop_price": None,
                "stop_source": None,
                "target_price": None,
                "target_source": None,
            }
        )
        # cycle397 — 매입일(최초 매입일). 판정 불가는 None(화면 `—`) — 오늘
        # 날짜로 채우지 않는다.
        payload["buy_date"] = merge_buy_date(
            engine_buy_dates.get(h.ticker), db_buy_dates.get(h.ticker)
        )
        enriched_holdings.append(payload)

    return ApiResponse(
        success=True,
        data={
            "holdings": enriched_holdings,
            "summary": summary.model_dump(),
        },
    )


@router.get("/buyable", response_model=ApiResponse)
async def buyable(ticker: str = "", price: int = 0):
    """매수 가능 금액/수량을 반환한다."""
    info = await get_buyable(ticker, price)
    return ApiResponse(success=True, data=info.model_dump())
