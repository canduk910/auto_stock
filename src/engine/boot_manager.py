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

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

from src.api.balance import get_balance, get_daily_orders
from src.auth.token import token_manager
from src.config import settings
from src.db._kst import to_date
from src.db.system_logs import write_log

if TYPE_CHECKING:
    from src.engine.scheduler import TradingScheduler

logger = logging.getLogger(__name__)

# 사이클 163 (2026-06-18) — prepare 호출 *전* stock_master 적재 대기 cap.
# 6/18 08:22~08:27 KST 운영 사고 영역 영구 차단.
# 사이클 134 task_loop_helper stagger (full_universe=0초 / basics=240 / daily=480 / master=720)
# vs 사이클 158 VB hook (90초) — 본 가드는 적재 본체 완료까지 5분 cap polling.
BOOT_PREPARE_STOCK_MASTER_WAIT_SECS = 300
BOOT_PREPARE_STOCK_MASTER_POLL_SECS = 10

#: `[daily_head_stale]` 관측 전용 KST (cycle283 — 달력일 판정 금지, 주말 갭 오탐 차단)
_HEAD_STALE_KST = timezone(timedelta(hours=9))

#: 직전 영업일 역산 상한 (일). 한국 최장 연휴 + 주말도 10일 안에 들어온다.
#: 상한에 닿으면 그 시점 후보를 그대로 쓴다 — 무한 루프 대신 현행(주말만 건너뛰기) 근사.
_HEAD_STALE_MAX_BACKTRACK_DAYS = 10


async def _previous_trading_day(today):
    """`today` 직전 **영업일**을 돌려준다 (주말 + KIS 휴장일 역산).

    주말만 건너뛰면 **공휴일 다음 영업일 아침마다 오탐**한다(연 10~15회). 그리고
    그 오탐은 진짜 결손(전날 저녁 적재 유실)과 출력이 **글자 하나 다르지 않다** —
    월요일이 공휴일이면 화요일 아침의 `head=금 / expected=월` 이 두 경우 모두에서
    같은 값이 되기 때문이다. 달력일 간격(`today - head`)으로도 구분되지 않는다
    (둘 다 4일). 휴장일 달력이 유일한 판별 수단이라 KIS `chk-holiday` 를 쓴다.

    비용: 정상일에는 호출 **1회**(첫 후보가 영업일이면 즉시 반환). 월요일 아침은
    주말을 호출 없이 건너뛰므로 역시 1회. 부팅 경로(07:55)라 매매 예산 영향 0.

    fail-open: `is_market_open` 은 조회 실패 시 스스로 `True`(영업일 가정)를 돌려주고,
    그마저 예외가 되면 여기서 현행 근사(주말만 건너뛴 후보)로 떨어진다 — 관측 하나가
    부팅 경로를 흔들면 안 된다.
    """
    from src.api.condition import is_market_open

    expected = today - timedelta(days=1)
    for _ in range(_HEAD_STALE_MAX_BACKTRACK_DAYS):
        if expected.weekday() >= 5:  # 5=토, 6=일 — 달력일 기준이면 매주 월요일 오탐
            expected -= timedelta(days=1)
            continue
        try:
            opened = await is_market_open(expected)
        except Exception:
            logger.debug("[daily_head_stale] 휴장일 조회 실패 — 주말 근사로 폴백", exc_info=True)
            return expected
        if opened:
            return expected
        expected -= timedelta(days=1)
    return expected


async def emit_daily_head_staleness() -> None:
    """일봉 헤드가 직전 영업일보다 오래됐으면 `[daily_head_stale]` WARNING 1행 (cycle283).

    **관측 전용 — 행위 변경 0.** 적재를 부르지 않는다(07:55~07:59 에 KIS 전량 호출을
    끼워 넣는 것은 별도 사이클·별도 승인 대상이다).

    왜 필요한가 (자문 R1): cycle283 D4 가 기동 거부 경계를 20:00 로 두면서 **20:00~21:30
    재기동은 그날 20:30 일봉 적재를 통째로 잃는다**(`start()` 가 거부되면 그날
    `_stock_master_daily_load_task` 자체가 생성되지 않는다). 보정 자체는 이미 존재한다 —
    다음 영업일 아침 일봉 immediate(`start()` +240초)가 실행돼 7일 증분으로 D-1 을 덮는다.
    마커가 직전 영업일 20:30 슬롯보다 이르므로 영업일 슬롯 게이트가 `reason=stale` 로
    실행을 고른다(cycle363 — `task_loop_helper` 의 `[immediate_gate]`).
    없는 것은 보정이 아니라 **순서**다: 그 보정이 `_boot()` 의 `prepare()` 보다 늦다.
    6전략 prepare 는 `expected_head`(직전 영업일, cycle363)로 하루 밀린 헤드를 알아채
    그 종목을 KIS 로 폴백하므로 목표가·신고가는 맞는 값으로 계산된다 — 대가는 전 종목
    폴백으로 prepare 가 느려지는 것이다. 휴장일 조회가 실패한 날(`expected_head=None`
    → 달력 판정)은 헤드가 하루 밀린 채로 읽히고, 재prepare 는 `_scanned_tickers` 가
    공집합일 때만 시도되므로 "하루 밀린" 상태는 재시도 대상이 아니다 ⇒ VB/LTV 목표가
    (`K×(prev_high − prev_low)`)와 donchian 신고가(`max(highs[1:21])`)가 밀린 값으로
    돌 수 있다(+600초 재준비는 적재 완료를 기다리지 않는다). 사람이 07:56 에 알면 09:00 전에
    `POST /api/stock-master/daily/refresh` + `POST /api/trading/restart` 로 복구할 수 있다.

    무음 조건(오탐 차단): 헤드 == 직전 영업일(정상) · 주말 갭(월요일 아침의 금요일 헤드) ·
    **공휴일 갭**(연휴 다음 영업일 아침 — `_previous_trading_day` 가 KIS 휴장일로 역산) ·
    빈 테이블(`None`, 최초 부팅/초기화는 `[stock_master_daily_load_*]` 계열이 말한다) ·
    조회 실패(never-raise — 관측이 매매를 끊으면 안 된다).
    """
    try:
        from src.db import stock_master_daily

        head = await stock_master_daily.max_bas_dd(None)
        if head is None:
            return
        today = datetime.now(_HEAD_STALE_KST).date()
        expected = await _previous_trading_day(today)
        if head >= expected:
            return
        logger.warning(
            "[daily_head_stale] max_bas_dd=%s expected=%s — 저녁 일봉 적재가 결손됐다. "
            "09:00 전에 POST /api/stock-master/daily/refresh 후 재기동을 검토하라",
            head.isoformat(), expected.isoformat(),
        )
    except Exception:
        logger.debug("[daily_head_stale] 관측 실패 graceful", exc_info=True)




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

    # 불변식 런타임 가드 (2026-08-08) — 실행 params 로 position_ratio × max_positions
    # ≤ 1.0 검증. 운영자 수동 DB apply 가 불변식을 우회하는 사각 차단(kojiro 1.2
    # 위반이 그 경로). 관찰 WARNING 만 — 매수/청산 미개입, fail-open.
    # cycle326 — 운영 DB ↔ 코드 기본값 드리프트 관측(값 변경 0 · never-raise).
    # `_load_strategy_config` 가 DB params 를 키별로 덮으므로 한 번 박힌 값은 계속 살고,
    # 그 차이를 알리는 것이 없었다(2026-09-20 전수 실측 39키). 그 무지가 실제 오판을
    # 만들었다 — LTV 상한가 손절을 코드값으로 읽어 「느슨해진다」고 보고했는데 DB 는 반대였다.
    # 🔴 차이를 고치지 않는다. 대부분 운영자가 의도로 넣은 값이고 되돌리는 것이 곧 사고다.
    try:
        from src.engine.param_drift import collect_param_drift
        _drift = collect_param_drift(scheduler.registry.all())
        if _drift:
            _sample = " · ".join(
                f"{d['strategy_id']}.{d['key']}={d['live']}(코드 {d['code']})"
                for d in _drift[:5]
            )
            logger.warning(
                "[param_drift] count=%d — 운영 DB 가 코드 기본값과 다르다(DB 가 정본). "
                "예: %s%s",
                len(_drift), _sample, " …" if len(_drift) > 5 else "",
            )
        else:
            logger.info("[param_drift] count=0 — 운영 DB 와 코드 기본값이 일치한다")
    except Exception:
        logger.exception("[param_drift] 관측 실패 — 부팅은 계속한다")

    try:
        from src.engine.portfolio_risk import check_budget_invariant
        for v in check_budget_invariant(scheduler.registry.all()):
            logger.warning(
                "[budget_invariant_violation] strategy=%s ratio=%.4f max_positions=%d "
                "product=%.4f > 1.0 — 운영자 DB 값 재확인 필요(부분매수로 흡수되나 정직도 위반)",
                v["strategy_id"], v["ratio"], v["max_positions"], v["product"],
            )
    except Exception:
        logger.exception("[budget_invariant_guard] 검증 실패 graceful — 부팅 계속")

    holdings, summary = await get_balance()

    # 시장 레짐 fetch + snapshot INSERT + cash_usage_ratio 자동 조정.
    # 출처는 우리 `macro` 컨테이너다. 토글이 꺼져 있거나 fetch 가 실패하면 empty regime 이고
    # 그때는 운영자가 정한 `cash_usage_ratio` 가 그대로 쓰인다.
    # `auto_regime_adjust=true` 면 레짐 cash_min 기반 자동 갱신, false 면 수동값 그대로.
    #
    # 🔴 **부팅 상한을 따로 건다.** 이 호출은 인라인 await 이고 바로 다음 줄이 자금 배분이다 —
    # macro 가 차가우면 첫 macro-cycle 이 100초를 넘긴 실측이 있어, 상한이 없으면 재시작 직후
    # 시세가 안 들어오는 창이 그만큼 길어진다. 레짐은 관찰 지표라 부팅을 붙잡을 값어치가 없다.
    # 상한에 걸리면 그날 레짐은 empty 로 가고 다음 갱신 기회(Settings 토글·다음 부팅)에 다시 받는다.
    # ⚠️ `_refresh_market_regime_and_persist` 는 `scheduler.py`(8영역 인접, 승인 대상)에 있어
    #    인자를 더하지 않고 호출 쪽에서 감싼다.
    try:
        await asyncio.wait_for(
            scheduler._refresh_market_regime_and_persist(),
            timeout=settings.macro_api_boot_timeout_secs,
        )
    except asyncio.TimeoutError:
        logger.warning(
            "[market_regime] 부팅 상한 %.1fs 초과 — 이번 부팅은 레짐 없이 진행한다",
            settings.macro_api_boot_timeout_secs,
        )
    except Exception:
        logger.exception("[market_regime] 부팅 중 레짐 갱신 실패 — 부팅은 계속한다")

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

    # 사이클 163 (2026-06-18) — prepare 호출 *전* stock_master 적재 대기 가드.
    # 6/18 08:22~08:27 운영 사고 (4분 27초 race) 영역 영구 차단.
    # 사이클 158 VB hook (90초) 한계 보완 — 5분 cap polling.
    # 사이클 88 G-REJECT graceful 영속 — count_active 예외 시 0 폴백 → 대기 진입.
    from src.db.stock_master import count_active as _count_active

    waited = 0
    while waited < BOOT_PREPARE_STOCK_MASTER_WAIT_SECS:
        try:
            cnt = await _count_active()
        except Exception:
            logger.exception("[boot_prepare_wait] count_active 예외 graceful")
            cnt = 0
        if cnt > 0:
            if waited > 0:
                logger.info(
                    "[boot_prepare_wait] stock_master count=%d (waited=%ds)",
                    cnt, waited,
                )
            break
        await asyncio.sleep(BOOT_PREPARE_STOCK_MASTER_POLL_SECS)
        waited += BOOT_PREPARE_STOCK_MASTER_POLL_SECS
    else:
        logger.warning(
            "[boot_prepare_wait_timeout] stock_master 0건 — %ds 대기 후 prepare 진행 (graceful)",
            BOOT_PREPARE_STOCK_MASTER_WAIT_SECS,
        )

    # cycle283 — prepare **앞** 관측 1행 `[daily_head_stale]` (행위 0, never-raise).
    # 20:00~21:30 재기동으로 그날 저녁 적재를 잃으면 이 prepare 가 하루 밀린 전일봉을
    # 읽고 그 상태가 종일 고정된다. 관측이 prepare 뒤면 이미 굳은 뒤라 소용이 없다.
    await emit_daily_head_staleness()

    # 전략별 prepare 호출 — wrapper 가 never-raise 라 이 자리에 try/except 를 두지
    # 않는다(cycle364 R7). 실패 로그는 `funnel_capture` 의 `[live_prepare]` 행이
    # 옛 문구(「전략 prepare 실패」, phase=boot)를 그대로 담아 남긴다.
    from src.engine import funnel_capture as _fc
    for strategy in scheduler.registry.enabled():
        await _fc.live_prepare_one(strategy, phase="boot")

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

        # asyncpg 는 positions.buy_date(DATE) 를 date 객체로 반환 → date.fromisoformat(date객체)
        # 는 TypeError (2026-07-20 크래시루프 사고). to_date 로 date/str/None 안전 파싱.
        buy_dt = to_date(row.get("buy_date")) or yesterday
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
            from src.db.trade_history import get_recent_buy_strategy
            fetched_strategy = await get_recent_buy_strategy(h.ticker)
            if fetched_strategy:
                strategy_id = fetched_strategy
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
        from src.db.trade_history import mark_pending_buys_completed
        for ticker in kis_tickers:
            await mark_pending_buys_completed(ticker)
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
        from src.db.trade_history import get_today_buys_ticker_strategy
        th_buys_rows = await get_today_buys_ticker_strategy()
        for row in th_buys_rows:
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

    # P1.5 (2026-08-06) — bull_flag_breakout 재시작 복구.
    #
    # BFB 는 익일청산 대상도 15:20 강제청산 대상도 아니고 `check_force_clear()==[]`
    # 이라 `max_hold_days` 까지 **실질 멀티데이 보유**다(종전 문서의 "BFB 는 익일
    # 청산"은 거짓). 그런데 `_entry_atr`·`high_since_buy` 복구가 둘 다 없어서,
    # 재시작하면 ATR 하드손절이 고정 % 로 무단 강등되고 트레일링 기준점이 매수가로
    # 리셋된다.
    #
    # **여기(boot_manager)에 배선하는 이유**: (1) DB positions 복구가 **끝난 뒤**라
    # 보유 종목이 확정돼 있고 (2) `scheduler.py` 는 매매 안전성 8영역이라 diff 0 을
    # 지켜야 한다. `_SWING_POLL_STRATEGIES` 에 BFB 를 넣는 방법은 그 상수가 매수
    # 폴루프·구독 대상에도 쓰여 **매수 행위가 바뀌므로 금지**.
    _bfb = scheduler.registry.get("bull_flag_breakout")
    if _bfb is not None and hasattr(_bfb, "recompute_high_since_buy"):
        try:
            await _bfb.recompute_high_since_buy()
        except Exception:
            logger.exception("bull_flag_breakout recompute_high_since_buy 실패")

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

    # cycle364 R2 — ④ 저녁 목록 ↔ 부팅 목록 대조는 백그라운드 task 다. `_boot()` 는
    # WebSocket 연결 *전*에 await 되므로, 여기서 동기로 기다리면(최대 10초 상한 +
    # DB 3쿼리) 보유 중 재기동의 틱 공백이 그만큼 늘어난다. 스폰만 하고(await 없음)
    # 실제 실행은 WS 연결 단계가 시작된 뒤로 미룬다(leaf 안 `_sleep` seam 대기).
    _fc.spawn_funnel_boot_vs_evening(scheduler, phase="boot")

    # cycle233 — 계좌 리스크 감시 부팅 동기 1회 (자문 cycle232 §2.5-γ 반례 2 요구사항:
    # 이게 없으면 07:55 부팅 ~ 첫 주기 평가 사이 09:05 매수창이 무평가로 열린다)
    # + 5분 자기 종료 감시 루프 스폰(idempotent — scheduler 라인 상한 가드 존중,
    # cancel 불요 = `_running` False 시 ≤60s 자연 종료). watcher 내부 fail-open.
    # cycle250 — guarded(타임아웃 300s)로 교체: 같은 hang 이 부팅 자체를 막던
    # 것을 차단한다(타임아웃이면 wrapper 가 fail-open 후처리를 마치고 None
    # 반환 — 아래 except 는 그 밖의 예외만 흡수).
    try:
        from src.engine import account_risk_watcher
        await account_risk_watcher.run_account_risk_watch_once_guarded(scheduler)
        account_risk_watcher.ensure_watch_loop(scheduler)
    except Exception:
        logger.exception("[account_risk_watch] 부팅 동기 평가 실패 graceful — 부팅 계속")

    # cycle234 — tick blind 계측 (G2 대체 조치 ①): 직전 하트비트와의 갭 보고 +
    # 60s 하트비트 루프 스폰. 관측 전용 — market_blind_secs 주간 분포가 서버 스탑
    # 재검토(cycle232 G2 게이트)의 정량 근거다. never-raise + 이중 graceful.
    try:
        from src.engine import uptime_monitor
        await uptime_monitor.report_boot_blind_gap()
        uptime_monitor.ensure_heartbeat_loop(scheduler)
    except Exception:
        logger.exception("[tick_blind_boot] 계측 배선 실패 graceful — 부팅 계속")
