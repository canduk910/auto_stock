"""일일 배치 러너 — 설계서 §6 파이프라인.

사용:
    python -m kojiro.runner            # 오늘 기준 신호 계산 + 주문 큐 저장
    python -m kojiro.runner --execute  # 주문 큐 실행 (익일 아침 크론용)
"""
import argparse
import datetime as dt
import json
import logging
from dataclasses import asdict
from pathlib import Path

from .config import KisConfig, StrategyConfig
from .indicators import enrich
from .kis_client import KisApiError, KisClient
from .money import affordable, can_add_unit, unit_size
from .strategy import (Action, Position, evaluate_entry, evaluate_exit,
                       evaluate_pyramid, update_position_after_close)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
logger = logging.getLogger("runner")

STATE_FILE = Path("positions.json")   # 간단 상태 저장 (확장 시 sqlite 권장)
QUEUE_FILE = Path("order_queue.json")


def load_positions() -> dict[str, Position]:
    if STATE_FILE.exists():
        raw = json.loads(STATE_FILE.read_text())
        return {k: Position(**v) for k, v in raw.items()}
    return {}


def save_positions(positions: dict[str, Position]) -> None:
    STATE_FILE.write_text(json.dumps(
        {k: asdict(v) for k, v in positions.items()}, ensure_ascii=False, indent=2))


def compute_signals(kis: KisClient, scfg: StrategyConfig, total_capital: float) -> list[dict]:
    """장 마감 후: 전 종목 지표 계산 → 주문 큐 생성."""
    positions = load_positions()
    units_total = sum(p.units for p in positions.values())
    today = dt.date.today()
    start = (today - dt.timedelta(days=200)).strftime("%Y%m%d")
    end = today.strftime("%Y%m%d")
    queue: list[dict] = []

    for code in scfg.universe:
        try:
            df = kis.daily_chart(code, start, end)
        except KisApiError:
            continue  # 오류 종목은 스킵, 전체 배치는 계속
        if len(df) < scfg.ema_long + scfg.macd_signal:
            logger.warning("%s 데이터 부족(%d봉) → 스킵", code, len(df))
            continue
        df = enrich(df, scfg)
        last = df.iloc[-1]
        pos = positions.get(code)

        if pos and pos.qty > 0:
            update_position_after_close(pos, last["close"], last["atr"], scfg)
            sig = evaluate_exit(df, pos, scfg)
            if sig.action == Action.SELL_ALL:
                queue.append({"code": code, "side": "sell", "qty": pos.qty,
                              "price": 0, "reason": sig.reason})
            elif sig.action == Action.SELL_HALF:
                queue.append({"code": code, "side": "sell", "qty": pos.qty // 2,
                              "price": 0, "reason": sig.reason})
            else:
                pyr = evaluate_pyramid(df, pos, scfg)
                ok, why = can_add_unit(pos.units, units_total, scfg)
                if pyr.action == Action.PYRAMID and ok:
                    plan = unit_size(total_capital, last["atr"], scfg)
                    if plan.qty > 0:
                        queue.append({"code": code, "side": "buy", "qty": plan.qty,
                                      "price": 0, "units": 1.0, "reason": pyr.reason})
        else:
            sig = evaluate_entry(df, scfg)
            if sig.action in (Action.BUY, Action.BUY_EARLY):
                frac = 0.5 if sig.action == Action.BUY_EARLY else 1.0
                ok, why = can_add_unit(0, units_total, scfg, add=frac)
                if not ok:
                    logger.info("%s 진입 보류: %s", code, why)
                    continue
                plan = unit_size(total_capital, last["atr"], scfg, fraction=frac)
                if plan.qty > 0:
                    queue.append({"code": code, "side": "buy", "qty": plan.qty,
                                  "price": 0, "units": frac,
                                  "atr": float(last["atr"]),
                                  "ref_close": float(last["close"]),
                                  "reason": sig.reason})
                    units_total += frac

    save_positions(positions)  # 손절선/최고가 갱신분 저장
    QUEUE_FILE.write_text(json.dumps(queue, ensure_ascii=False, indent=2))
    logger.info("주문 큐 %d건 저장", len(queue))
    return queue


def execute_queue(kis: KisClient, scfg: StrategyConfig) -> None:
    """익일 아침: 큐 실행 + 체결 가정 후 포지션 갱신(실전은 체결통보로 확정 권장)."""
    if not QUEUE_FILE.exists():
        return
    queue = json.loads(QUEUE_FILE.read_text())
    positions = load_positions()
    bal = kis.balance()
    cash = float(bal["output2"][0]["dnca_tot_amt"])  # 예수금총금액

    for od in queue:
        try:
            if od["side"] == "buy":
                qty = affordable(od["qty"], od.get("ref_close", 0) or 1, cash)
                if qty <= 0:
                    logger.info("%s 현금 부족 → 스킵", od["code"])
                    continue
                kis.order_cash(od["code"], qty, 0, "buy")
                pos = positions.get(od["code"]) or Position(code=od["code"])
                # 단순화: 참조종가로 평단 추정 — 실전은 체결단가로 갱신할 것
                fill = od.get("ref_close", 0)
                new_qty = pos.qty + qty
                pos.avg_price = ((pos.avg_price * pos.qty + fill * qty) / new_qty
                                 if new_qty else fill)
                pos.qty = new_qty
                pos.units += od.get("units", 1.0)
                if od.get("atr"):
                    pos.entry_atr = od["atr"]
                pos.stop_price = pos.avg_price - scfg.stop_atr * pos.entry_atr
                pos.highest_close = max(pos.highest_close, fill)
                positions[od["code"]] = pos
                cash -= fill * qty
            else:
                kis.order_cash(od["code"], od["qty"], 0, "sell")
                pos = positions.get(od["code"])
                if pos:
                    pos.qty -= od["qty"]
                    if pos.qty <= 0:
                        positions.pop(od["code"], None)
                    else:
                        pos.half_sold = True
        except KisApiError as e:
            logger.error("%s 주문 실패: %s", od["code"], e)

    save_positions(positions)
    QUEUE_FILE.unlink(missing_ok=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--execute", action="store_true", help="주문 큐 실행 모드")
    ap.add_argument("--capital", type=float, default=10_000_000, help="총투자자금(원)")
    ap.add_argument("--db", help="종목마스터DB 경로 — 지정 시 스크리너가 유니버스를 자동 구성")
    ap.add_argument("--top", type=int, default=10, help="스크리너 상위 N종목만 유니버스로")
    args = ap.parse_args()

    kcfg, scfg = KisConfig(), StrategyConfig()
    kis = KisClient(kcfg)

    if args.db:
        from .datastore import SqliteStore
        from .screener import ScreenerConfig, screen
        result = screen(SqliteStore(args.db), scfg, ScreenerConfig())
        held = list(load_positions().keys())  # 보유 종목은 항상 감시 대상 유지
        picked = result.buy_candidates["code"].head(args.top).tolist() \
            if not result.buy_candidates.empty else []
        scfg.universe = list(dict.fromkeys(picked + held))
        logger.info("스크리너 유니버스 %d종목: %s", len(scfg.universe), scfg.universe)

    today = dt.date.today().strftime("%Y%m%d")
    if kis.is_holiday(today):
        logger.info("휴장일 → 종료")
        return

    if args.execute:
        execute_queue(kis, scfg)
    else:
        queue = compute_signals(kis, scfg, args.capital)
        for od in queue:
            logger.info("신호: %s", od)


if __name__ == "__main__":
    main()
