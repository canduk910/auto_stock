"""시스템 기동 본체 — scheduler._boot() 위임 대상.

사이클 51 (2026-06-01, refactor-review 카드 #1 분해 1차) — scheduler.py 의 274L
`_boot()` 본체를 형제 모듈로 추출. 사이클 48 `stale_tracker.py` 와 동일 패턴.

배경:
- scheduler.py 4,142L / 21 개 80L+ 함수의 모듈 비대화 카드 #1 단계적 분해
- _boot() 는 책임이 독립적 (토큰 사전 발급 → 잔고 → 매크로 → DB 포지션 복구 → KIS 잔고 보완 → PENDING 정리 → 미체결 복구 → stock_master eager)
- 호출자(scheduler) 1 곳뿐이므로 scheduler 인스턴스 인자로 받는 함수 시그니처 채택
- 외부 import 경로(`from src.engine.scheduler import ...`) 변경 0 — 16+ 곳 영향 없음

안전 가드:
- scheduler 의 메서드/속성은 모두 `scheduler.X` 로 접근 (행위 보존)
- lazy import 위치 보존 (DB/positions/supabase) — 순환 import 회피 패턴 동일
- 모든 안전 규칙 (CLAUDE.md `_boot` 영역) 호출 순서 100% 보존
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from typing import TYPE_CHECKING

from src.api.balance import get_balance, get_daily_orders
from src.auth.token import token_manager
from src.db.system_logs import write_log

if TYPE_CHECKING:
    from src.engine.scheduler import TradingScheduler

logger = logging.getLogger(__name__)


async def boot(scheduler: "TradingScheduler") -> None:
    """시스템 기동: 토큰 갱신, 잔고 동기화 + 포지션 복구.

    1차: DB positions 테이블에서 포지션 복구 (정확한 매수가/전략/매수일)
    2차: KIS 잔고 API와 교차 검증 — DB에 없지만 KIS에 있으면 보완 등록

    사이클 20 (2026-05-20) — 진입 초입에 `_preissue_all_tokens()` 호출:
    - 메인 + 보조 N 매니저 토큰을 분당 1개 한도 직렬화로 사전 발급
    - 캐시 hit 시 0초 / miss 시 N분 boot 지연 (07:50 라 KRX 영향 0)
    """
    # 사이클 20 — 모든 매니저 사전 순차 발급 (KIS 분당 1개 한도)
    await scheduler._preissue_all_tokens()

    await token_manager.get_token()

    # DB에서 전략 설정(비중/파라미터) 로드
    await scheduler._load_strategy_config()

    holdings, summary = await get_balance()

    # 사이클 2 (2026-05-17): 시장 레짐 fetch + snapshot INSERT + cash_usage_ratio 자동 조정.
    # `DKSTOCK_REGIME_ENABLED=false` 면 empty regime (graceful, 외부 호출 0건).
    # 외부 fetch 실패 시에도 empty regime → 매수 가드 비활성 + 운영자 수동 cash_usage_ratio 보존.
    # `auto_regime_adjust=true` 면 레짐 cash_min 기반 자동 갱신, false 면 수동값 그대로.
    await scheduler._refresh_market_regime_and_persist()
    ratio = await scheduler._resolve_cash_usage_ratio()

    # J3 (2026-05-12): 매매 가용 자금 비율 적용 — `system_config.cash_usage_ratio`.
    # 변경 즉시 적용 안 함, 다음 _boot() 부터 반영. Settings UI 안내 "다음 영업일부터 반영".
    available_for_trading = int(summary.net_asset * ratio)
    scheduler.registry.allocate_funds(available_for_trading)
    logger.info(
        "[cash_usage_ratio] net_asset=%d ratio=%.2f available=%d",
        summary.net_asset, ratio, available_for_trading,
    )
    # 사이클 72 hotfix G-6: write_log 제거 — logger.info → _DbLogHandler 위임 단일 INSERT

    # 전략별 prepare 호출
    for strategy in scheduler.registry.enabled():
        try:
            await strategy.prepare()
        except Exception:
            logger.exception("전략 prepare 실패: %s", strategy.strategy_id)

    from src.engine.strategy_base import Position
    from src.engine.scanner import ticker_names

    _KST = timezone(timedelta(hours=9))
    today = datetime.now(_KST).date()
    yesterday = today - timedelta(days=1)

    # 1차: DB positions 테이블에서 포지션 복구
    from src.db.positions import load_all as load_db_positions
    db_positions = await load_db_positions()
    db_restored = 0

    # KIS 잔고의 실제 보유종목 (6자리 영숫자 — ETF·ETN·신주인수권 등 알파벳 포함 종목 포함)
    kis_tickers = {
        h.ticker for h in holdings
        if h.quantity > 0 and len(h.ticker) == 6 and h.ticker.isalnum()
    }

    for row in db_positions:
        ticker = row["ticker"]
        # KIS 잔고에도 있는 종목만 복구 (이미 매도된 종목 방지)
        if ticker not in kis_tickers:
            from src.db.positions import delete_position
            await delete_position(ticker)
            logger.info("DB 포지션 정리 (KIS 미보유): %s", ticker)
            continue

        strategy_id = row["strategy_id"]
        target = scheduler.registry.get(strategy_id) or scheduler.registry.get("momentum")
        if not target:
            continue

        buy_dt = date.fromisoformat(row["buy_date"]) if row.get("buy_date") else yesterday
        target.state.positions[ticker] = Position(
            ticker=ticker,
            buy_price=row["buy_price"],
            quantity=row["quantity"],
            order_no=row.get("order_no", ""),
            strategy_id=target.strategy_id,
            buy_date=buy_dt,
            high_since_buy=row.get("high_since_buy", 0),
        )
        if row.get("ticker_name"):
            ticker_names[ticker] = row["ticker_name"]
        db_restored += 1
        logger.info(
            "DB 포지션 복구: %s %d주 @ %d (%s, 전략: %s)",
            row.get("ticker_name") or ticker, row["quantity"], row["buy_price"],
            "당일매수" if buy_dt == today else "익일청산",
            target.strategy_id,
        )

    # 2차: KIS 잔고에 있지만 DB에 없는 종목 보완
    db_tickers = {row["ticker"] for row in db_positions}
    kis_only = 0
    for h in holdings:
        if h.quantity <= 0:
            continue
        if not (len(h.ticker) == 6 and h.ticker.isalnum()):
            continue
        if h.ticker in db_tickers:
            continue
        if scheduler.registry.is_ticker_held_by_any(h.ticker):
            continue

        # DB에 없는 종목 — trade_history에서 전략 확인 + KIS 주문체결내역으로 매수일 판정
        buy_price = int(h.avg_price)
        buy_dt = yesterday  # 기본 전일 매수로 간주
        strategy_id = "momentum"

        # trade_history에서 전략 정보 조회
        try:
            from src.db.supabase import supabase as _sb
            th_result = _sb.table("trade_history").select("strategy").eq(
                "ticker", h.ticker
            ).eq("trade_type", "BUY").order(
                "timestamp", desc=True
            ).limit(1).execute()
            if th_result.data:
                strategy_id = th_result.data[0].get("strategy", "momentum")
        except Exception:
            pass

        try:
            orders = await get_daily_orders()
            for order in orders:
                if order.get("pdno") == h.ticker and order.get("sll_buy_dvsn_cd") == "02":
                    avg = int(order.get("avg_prvs", "0"))
                    if avg > 0:
                        buy_price = avg
                    buy_dt = today
                    break
        except Exception:
            pass

        target = scheduler.registry.get(strategy_id)
        if target:
            target.state.positions[h.ticker] = Position(
                ticker=h.ticker,
                buy_price=buy_price,
                quantity=h.quantity,
                order_no="",
                strategy_id=strategy_id,
                buy_date=buy_dt,
            )
            if h.name:
                ticker_names[h.ticker] = h.name
            # DB에도 저장
            from src.db.positions import save_position
            await save_position(
                ticker=h.ticker, ticker_name=h.name,
                buy_price=buy_price, quantity=h.quantity,
                order_no="", strategy_id=strategy_id, buy_date=buy_dt,
            )
            kis_only += 1
            logger.warning(
                "KIS 잔고 보완 복구: %s %d주 @ %d (%s, 전략: %s)",
                h.name or h.ticker, h.quantity, buy_price,
                "당일매수" if buy_dt == today else "익일청산",
                strategy_id,
            )

    # PENDING 매수 기록 일괄 COMPLETED 처리
    try:
        from src.db.supabase import supabase
        for ticker in kis_tickers:
            supabase.table("trade_history").update(
                {"status": "COMPLETED"}
            ).eq("ticker", ticker).eq(
                "trade_type", "BUY"
            ).eq("status", "PENDING").execute()
    except Exception:
        pass

    # 당일 전체 주문 내역 조회 (DB 동기화 + 미체결 복구에 공용)
    all_orders: list[dict] = []
    try:
        all_orders = await get_daily_orders()
    except Exception:
        logger.warning("당일 주문내역 조회 실패")

    # DB에 누락된 체결 내역 동기화
    try:
        await scheduler._sync_orders_to_db(all_orders)
    except Exception:
        logger.warning("DB 동기화 실패")

    # 미체결 매수 주문의 전략 매핑 (DB 포지션 + trade_history 기반)
    db_strategy_map: dict[str, str] = {
        row["ticker"]: row["strategy_id"]
        for row in db_positions if row.get("strategy_id")
    }
    try:
        from src.db.supabase import supabase as _sb2
        th_buys = _sb2.table("trade_history").select("ticker, strategy").eq(
            "trade_type", "BUY"
        ).gte(
            "timestamp", today.isoformat()
        ).execute()
        for row in (th_buys.data or []):
            if row["ticker"] not in db_strategy_map:
                db_strategy_map[row["ticker"]] = row.get("strategy", "momentum")
            # 당일 매수 종목을 해당 전략 sold_today에 시드 — 서버 재기동 race로 같은 종목이
            # 짧은 시간에 여러 번 매수되던 결함 차단(모멘텀 `_prev_prdy_rate` 휘발 + 보유 가드 race).
            # 의미적으론 매도가 아니지만 모든 전략의 check_buy_signal이 sold_today를 가드로 사용하므로
            # 같은 영업일 재매수 차단 효과 즉시 확보.
            seed_sid = row.get("strategy") or "momentum"
            seed_strategy = scheduler.registry.get(seed_sid)
            if seed_strategy:
                seed_strategy.state.sold_today.add(row["ticker"])
    except Exception:
        pass

    # 미체결 매수 주문 복구 → pending_buys에 등록하여 중복 주문 방지
    unfilled_count = 0
    for order in all_orders:
        if order.get("sll_buy_dvsn_cd") != "02":  # 매수만
            continue
        rmn_qty = int(order.get("rmn_qty", "0"))
        if rmn_qty <= 0:
            continue
        ticker = order.get("pdno", "")
        if not ticker:
            continue
        # 이미 어떤 전략에 포지션이 있으면 건너뜀
        if scheduler.registry.is_ticker_held_by_any(ticker):
            continue
        # 미체결 매수 주문 존재 → 해당 전략의 pending_buys에 등록
        strategy_id = db_strategy_map.get(ticker, "momentum")
        target_strategy = scheduler.registry.get(strategy_id) or scheduler.registry.get("momentum")
        order_unpr = int(order.get("ord_unpr", "0"))
        if target_strategy:
            target_strategy.state.pending_buys.add(ticker)
            # 잔여 자금 폴백 계산용 — pending_buys 와 동기 등록 (2026-05-11 P1)
            target_strategy.state.pending_buy_amounts[ticker] = order_unpr * rmn_qty
        order_no = order.get("odno", "")
        scheduler.order_engine._pending_buy_orders[order_no] = {
            "ticker": ticker,
            "price": order_unpr,
            "quantity": rmn_qty,
            "strategy_id": strategy_id,
        }
        scheduler.order_engine._order_qty[order_no] = int(order.get("ord_qty", "0"))
        scheduler.order_engine._order_strategy[order_no] = strategy_id
        scheduler.order_engine._order_ticker[order_no] = ticker
        unfilled_count += 1
        logger.info("미체결 주문 복구: %s %d주 (주문번호: %s, 전략: %s)", ticker, rmn_qty, order_no, strategy_id)

    total_pos = sum(len(s.state.positions) for s in scheduler.registry.all())
    await write_log(
        "INFO",
        f"기동 완료: 순자산 {summary.net_asset:,}원, "
        f"보유 {total_pos}종목 (DB복구: {db_restored}, KIS복원: {kis_only}, 미체결: {unfilled_count})",
    )
    logger.info(
        "기동 완료: 순자산 %s, 보유 %d종목 (DB복구: %d, KIS복원: %d, 미체결: %d)",
        summary.net_asset, total_pos, db_restored, kis_only, unfilled_count,
    )

    # I3 (2026-05-12): 보유 + 익일청산 후보 ticker 의 stock_master 캐시 eager 갱신.
    # Phase G lazy 한계 — 첫 사이클 캐시 miss 시 SOR/NXT 그대로 발사 → KIS 거부.
    # 2026-05-12 09:00:12 KST 계양전기(012200) NEXT_DAY_CLEAR SOR 거부 사례 대응.
    try:
        await scheduler._eager_refresh_stock_master_for_held_positions()
    except Exception:
        logger.exception("[stock_master_eager] _boot 후 eager 갱신 실패 — lazy 경로로 자연 보강")

    # 사이클 149 (2026-06-16) — 부팅 시점 VI 활성 종목 REST 보조 폴백 seed.
    # 자문 의제 4 (자문 채택) = inquire_vi_status REST 1회 호출 + graceful.
    # 부팅 시점 = 07:50 KST = 장 시작 *전* = VI 활성 거의 없음. 결함 시 영향 0.
    # WebSocket H0UNMKO0 구독 시점 *이전* VI 활성 종목 stale 회피 보장.
    try:
        from src.api.market_operation import inquire_vi_status_today
        from src.engine.market_operation_monitor import seed_vi_active_from_rest
        vi_seed = await inquire_vi_status_today()
        seed_vi_active_from_rest(vi_seed)
        logger.info("[market_op_boot_seed] vi_active=%d", len(vi_seed))
    except Exception:
        logger.exception("[market_op_boot_seed] REST 폴백 실패 graceful — WebSocket 수신만으로 충분")

    # 사이클 162 (2026-06-17) — 익일청산큐 DB 영속화 복구 (의제 D).
    # 사용자 보고 사고: 알테오젠 (196170, VB) + 알지노믹스 (476830, LTV) 6/17 15:20 강제청산 누락.
    # 근본 원인 후보 = `_pending_next_day_clear` 메모리 휘발 (EC2 재기동 시).
    # domain-expert 자문 산출물 `_workspace/domain_consult/cycle162_pending_persist_and_call_auction.md`.
    # 사이클 149 VI seed 패턴 답습 = 부팅 마지막 단계 + graceful (실패 시 메모리 set 보존).
    try:
        from src.db.pending_next_day_clear import load_pending_ndc
        restored = await load_pending_ndc(today)
        scheduler._pending_next_day_clear.update(restored)
        logger.info(
            "[pending_ndc_boot_restore] count=%d target_date=%s",
            len(restored), today.isoformat(),
        )
    except Exception:
        logger.exception("[pending_ndc_boot_restore] DB 복구 실패 graceful — 메모리 set 보존")
