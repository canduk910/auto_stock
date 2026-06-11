"""롱테일 변동성 돌파 전략.

변동성 돌파 진입 + 상한가 도달 시 익일 청산으로 롱테일(긴 우측 보상) 추구.
- 대상: 시총/거래대금 필터 + 연속상한가 제외
- 매수: 시가 + (전일Range × K) 돌파 시 (변동성 돌파 방식)
- 당일 상한가 미도달: 당일 손절(-3%) + 15:20 강제 청산
- 당일 상한가 도달(+29%): 익일 청산 모드 전환 — 손절(-5%), 갭상승 +10% 트레일링/-2%
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timedelta, timezone

from src.engine.strategy_base import Signal, StrategyBase, StrategyConfig

KST = timezone(timedelta(hours=9))

logger = logging.getLogger(__name__)


def _empty_scan_stats() -> dict:
    """사이클 21 — LTV 단계별 깔때기 카운트 dict (10 키).

    VB 의 9 키 + `consecutive_limit_pass` (연속상한가 제외 통과) 추가.
    """
    return {
        "universe_candidates": 0,
        "universe_filtered": 0,
        "price_filtered": 0,
        "mcap_pass": 0,
        "trade_amount_pass": 0,
        "candle_fetch_ok": 0,
        "consecutive_limit_pass": 0,  # LTV 전용 — 연속상한가 N일 미해당 통과
        "k_value_computed": 0,
        "final_prepared": 0,
        "last_run_at": None,
    }


class LongTailVolatilityStrategy(StrategyBase):
    """롱테일 변동성 돌파 전략."""

    # 매매 가능 보드 — PRE_NXT + MAIN + POST_NXT 3보드 (사이클 38, 2026-05-22: 사용자 의도 복원).
    #
    # 사이클 26 (2026-05-20): KRX ONLY 변경 (`("main",)`) — SK하이닉스 시가 결함 추적 중 도입.
    # 사이클 38 (2026-05-22): 사용자 운영 의도 복원 — LTV 연속 상한가 익일 청산 모드 + 야간 매수.
    # - PRE_NXT(08:00~09:00) 매수 가능: 야간 NXT 프리 진입 (사용자 운영 정책).
    # - MAIN(09:00~15:20) 매수 가능: KRX 메인 시간대.
    # - POST_NXT(15:40~19:50) 매수 가능: 연속 상한가 종목 익일 청산 모드 진입.
    #
    # `tradable_boards` 는 **매수 진입 전용** — 매도/손절/Trailing/익일청산/상한가 손절 모니터링은
    # 어떤 시간대에서도 보드 가드 *없이* 항상 작동 (`risk.on_tick` 의 `check_exit_signal` 분기).
    DEFAULT_TRADABLE_BOARDS = ("pre_nxt", "main", "post_nxt")

    DEFAULT_PARAMS = {
        "tradable_boards": list(DEFAULT_TRADABLE_BOARDS),
        # 진입 조건
        "k_period": 20,
        "min_prdy_rate": 5.0,                        # 전일대비 최소 등락률
        # 보드별 K값 곱 (Phase 5 Q1=C: 보드별 분리)
        "k_value_krx_main": 1.0,
        "k_value_nxt_pre": 1.0,
        "k_value_nxt_post": 1.0,
        "exchange": "KRX",
        # 종목 필터
        "min_market_cap": 100_000_000_000,            # 시총 1,000억
        "min_trade_amount": 20_000_000_000,           # 거래대금 200억
        "max_scan_stocks": 100,
        "exclude_consecutive_limit": 2,               # 연속 상한가 N일 이상 제외
        # 당일 청산 (상한가 미도달)
        "intraday_stop_loss": -3.0,
        # 익일 청산 (상한가 도달)
        "limit_up_threshold": 29.0,                   # 이 이상 → 익일 청산 모드
        "overnight_stop_loss": -5.0,
        "gap_up_threshold": 10.0,
        "trailing_stop_rate": -2.0,
        # 자금 관리
        "position_ratio": 0.15,
        "max_positions": 6,
        "daily_loss_limit": -5.0,
    }

    def __init__(self, config: StrategyConfig):
        merged = {**self.DEFAULT_PARAMS, **config.params}
        config.params = merged
        super().__init__(config)
        # VB와 동일 — 종목별 타겟 가격/K값 (Phase 5: 보드별 분리)
        self._targets: dict[str, dict] = {}
        self._open_confirmed: dict[str, dict[str, bool]] = {}
        self._prev_price: dict[str, dict[str, int]] = {}
        self._scanned_tickers: list[str] = []
        # 상한가 도달 → 익일 청산 모드 종목
        self._limit_up_reached: set[str] = set()
        # 익일 청산 시가 안정화 대기 플래그
        self._next_day_clear_pending = False
        # 사이클 21 — 단계별 카운트 (ScanMonitor 깔때기)
        self._scan_stats: dict = _empty_scan_stats()

    async def prepare(self) -> None:
        """장 시작 전: 종목 스캔 → K값 계산 → 연속상한가 필터링."""
        import asyncio

        from src.api.condition import fetch_daily_candles

        # 사이클 21 — 매 prepare 마다 카운트 초기화
        stats = _empty_scan_stats()
        self._scan_stats = stats

        tickers = await self._scan_universe()
        k_period = self.config.params["k_period"]
        consecutive_limit = self.config.params["exclude_consecutive_limit"]
        today_str = datetime.now(timezone(timedelta(hours=9))).date().strftime("%Y%m%d")
        prepared = 0

        # 일봉 fetch 병렬화 (KIS Rate Limit semaphore가 자동 직렬화)
        async def _fetch_one(ticker: str):
            try:
                return ticker, await fetch_daily_candles(ticker, days=k_period + 2)
            except Exception as e:
                logger.warning("롱테일 일봉 fetch 실패: %s — %s", ticker, e)
                return ticker, None

        fetched = await asyncio.gather(*[_fetch_one(t) for t in tickers])

        # 사이클 21 — 일봉 fetch 성공 카운트
        stats["candle_fetch_ok"] = sum(1 for _, c in fetched if c is not None)

        for ticker, candles in fetched:
            if candles is None:
                continue
            try:
                if len(candles) < 2:
                    continue

                # candles[0]의 거래일이 오늘이면 candles[1]을 "전일"로 사용
                prev_idx = 1 if candles[0].get("stck_bsop_date") == today_str else 0
                if len(candles) <= prev_idx + 1:
                    continue

                # 연속상한가 체크 (전일 기준 최근 N일 연속 +25% 이상이면 제외)
                if consecutive_limit > 0 and self._is_consecutive_limit_up(
                    candles, consecutive_limit, start=prev_idx,
                ):
                    logger.debug("연속상한가 제외: %s (%d일 이상)", ticker, consecutive_limit)
                    continue
                # 사이클 21 — 연속상한가 통과 카운트 (탈락 종목은 미증가)
                stats["consecutive_limit_pass"] += 1

                # 노이즈 비율 계산 (전일 이전 k_period일)
                noise_list = []
                for c in candles[prev_idx + 1 :]:
                    high = int(c.get("stck_hgpr", "0"))
                    low = int(c.get("stck_lwpr", "0"))
                    open_p = int(c.get("stck_oprc", "0"))
                    close_p = int(c.get("stck_clpr", "0"))
                    rng = high - low
                    if rng > 0:
                        noise = 1 - abs(close_p - open_p) / rng
                        noise_list.append(noise)

                if not noise_list:
                    continue

                k = sum(noise_list) / len(noise_list)

                # 전일 Range
                prev = candles[prev_idx]
                prev_high = int(prev.get("stck_hgpr", "0"))
                prev_low = int(prev.get("stck_lwpr", "0"))
                prev_range = prev_high - prev_low
                if prev_range <= 0:
                    logger.debug(
                        "롱테일 prev_range=0 skip: %s (date=%s)",
                        ticker, prev.get("stck_bsop_date"),
                    )
                    continue

                target_offset = int(prev_range * k)
                if target_offset <= 0:
                    logger.debug(
                        "롱테일 target_offset=0 skip: %s (k=%.4f, range=%d)",
                        ticker, k, prev_range,
                    )
                    continue

                self._targets[ticker] = {
                    "k": round(k, 4),
                    "prev_range": prev_range,
                    "target_offset_base": target_offset,
                    # backwards-compat
                    "target_offset": target_offset,
                    "target_price": 0,
                    "open_price": 0,
                    # 보드별 시가/타겟 (Phase 5)
                    "boards": {},
                }
                self._open_confirmed[ticker] = {}

                # 09:30 scan_stocks() 이전에도 등락률 필터(min_prdy_rate)가 동작하도록 전일종가 사전 등록
                from src.engine.scanner import ticker_prev_close
                prev_close = int(prev.get("stck_clpr", "0"))
                if prev_close > 0:
                    ticker_prev_close[ticker] = prev_close

                prepared += 1

            except Exception as e:
                logger.warning("롱테일 변동성 돌파 prepare 실패: %s — %s", ticker, e)
                continue

        self._scanned_tickers = list(self._targets.keys())
        # 사이클 21 — K값/최종 카운트 + last_run_at
        stats["k_value_computed"] = prepared
        stats["final_prepared"] = len(self._scanned_tickers)
        stats["last_run_at"] = datetime.now(KST).isoformat()
        logger.info("롱테일 변동성 돌파 준비 완료: %d/%d종목", prepared, len(tickers))

    @staticmethod
    def _is_consecutive_limit_up(candles: list[dict], threshold: int, start: int = 0) -> bool:
        """start 인덱스부터 N일 연속 상한가(+25% 이상) 여부를 판별한다.

        start는 "전일"을 가리키는 인덱스(보통 0 또는 1). 오늘 부분봉이 [0]에 끼면 start=1로 호출.
        """
        if start >= len(candles):
            return False
        count = 0
        for c in candles[start : start + threshold]:
            close_p = int(c.get("stck_clpr", "0"))
            open_p = int(c.get("stck_oprc", "0"))
            if open_p <= 0:
                break
            rate = (close_p - open_p) / open_p * 100
            if rate >= 25.0:
                count += 1
            else:
                break
        return count >= threshold

    async def _scan_universe(self) -> list[str]:
        """stock_master DB 기반으로 시총·거래대금 조건 종목을 스캔한다 (사이클 108).

        사이클 108 (Plan Phase A) — 사전 적재된 stock_master (~2,800종목,
        사이클 101/106 _full_universe_load_task_loop) 를 DB 필터링으로 대체한다.
        LTV 전용 consecutive_limit_pass 카운터는 prepare() 에서 관리하므로
        _scan_universe 는 VB 와 동일 구조로 단순화한다.
        KIS API 직접 호출 0건.
        """
        from src.db import stock_master as _sm_mod
        from src.engine.scanner import ETF_KEYWORDS, ticker_names

        min_mcap = self.config.params.get("min_market_cap", 100_000_000_000)
        min_trade = self.config.params.get("min_trade_amount", 20_000_000_000)
        max_stocks = self.config.params.get("max_scan_stocks", 100)

        rows = await _sm_mod.list_by_filter(
            min_market_cap=min_mcap,
            min_trade_amount=min_trade,
            nxt_tradable=True,
            limit=max_stocks,
        )

        # 사이클 21 — 후보 수
        self._scan_stats["universe_candidates"] = len(rows)

        filtered: list[str] = []
        for row in rows:
            ticker = row.get("ticker", "")
            # 종목코드 형식 검증 — ETF·ETN·신주인수권 등 알파벳 포함 코드 차단
            if not ticker or not (len(ticker) == 6 and ticker.isdigit()):
                continue
            name = row.get("name", "") or (row.get("raw") or {}).get("prdt_abrv_name", "")
            if any(kw in name for kw in ETF_KEYWORDS):
                continue
            if name:
                ticker_names[ticker] = name
            filtered.append(ticker)

        logger.info(
            "롱테일 변동성 돌파 유니버스 확정: %d/%d종목 (stock_master DB, 시총 %d억+, 거래대금 %d억+)",
            len(filtered), len(rows), min_mcap // 100_000_000, min_trade // 100_000_000,
        )
        # 사이클 21 — universe 필터 통과
        self._scan_stats["universe_filtered"] = len(filtered)

        if not filtered:
            from src.db.system_logs import write_log

            msg = (
                f"롱테일 변동성 돌파 유니버스 0종목 — stock_master {len(rows)}건 중 "
                f"시총 {min_mcap // 100_000_000}억+ / 거래대금 "
                f"{min_trade // 100_000_000}억+ / ETF 제외 후 통과 없음"
            )
            logger.error(msg)
            try:
                await write_log("ERROR", msg)
            except Exception:
                logger.exception("system_logs 기록 실패")

        return filtered

    def get_scanned_tickers(self) -> list[str]:
        """스캔된 종목 리스트를 반환한다 (WebSocket 구독용)."""
        return self._scanned_tickers

    def get_scan_stats(self) -> dict:
        """사이클 21 — 단계별 스캔 통계 (ScanMonitor 깔때기).

        donchian_swing.get_scan_stats() 와 동일 시그니처.
        외부 수정 격리를 위해 사본 반환.
        """
        return dict(self._scan_stats)

    def get_targets_status(self) -> dict[str, dict]:
        """종목별 타겟 가격 정보 (활성 보드 필터링 — VB와 동일 형식 + `limit_up_reached`).

        2026-05-13 작업 1: 활성 보드(`session_tracker.active`) ∩ 전략 `tradable_boards` 에
        속하는 보드만 노출. 교집합 공집합 → `boards={}` + top-level 0. session 모듈
        장애 시 fallback → 모든 보드 노출 (외부 호환 + 운영자 시야 보존).
        `limit_up_reached` 키는 필터링과 무관하게 항상 보존.
        """
        # 활성 보드 ∩ tradable_boards = 노출 보드 집합
        visible: set[str] | None
        try:
            from src.engine.session import session_tracker, parse_tradable_boards

            active = session_tracker.active  # frozenset[MarketBoard]
            tradable_raw = self.config.params.get("tradable_boards")
            tradable = parse_tradable_boards(tradable_raw) if tradable_raw else None
            if not tradable:
                tradable = parse_tradable_boards(list(self.DEFAULT_TRADABLE_BOARDS))
            visible = {b.value for b in (active & tradable)}
        except Exception:
            visible = None

        _BOARD_PRIORITY = ("main", "post_nxt", "pre_nxt")

        result = {}
        for ticker, info in self._targets.items():
            board_states = self._open_confirmed.get(ticker, {})
            all_boards = info.get("boards", {})
            limit_up = ticker in self._limit_up_reached

            if visible is None:
                # fallback — 기존 모든 보드 노출
                exposed_boards = {
                    board: {
                        "open_price": b.get("open_price", 0),
                        "target_price": b.get("target_price", 0),
                        "target_offset": b.get("target_offset", 0),
                        "confirmed": board_states.get(board, False),
                    }
                    for board, b in all_boards.items()
                }
                result[ticker] = {
                    "k": info.get("k", 0),
                    "target_price": info.get("target_price", 0),
                    "open_price": info.get("open_price", 0),
                    "target_offset": info.get("target_offset", 0),
                    "limit_up_reached": limit_up,
                    "boards": exposed_boards,
                    "open_confirmed": board_states,
                }
                continue

            exposed_boards = {
                board: {
                    "open_price": b.get("open_price", 0),
                    "target_price": b.get("target_price", 0),
                    "target_offset": b.get("target_offset", 0),
                    "confirmed": board_states.get(board, False),
                }
                for board, b in all_boards.items()
                if board in visible
            }
            exposed_confirmed = {b: v for b, v in board_states.items() if b in visible}

            if not exposed_boards:
                result[ticker] = {
                    "k": info.get("k", 0),
                    "target_price": 0,
                    "open_price": 0,
                    "target_offset": 0,
                    "limit_up_reached": limit_up,
                    "boards": {},
                    "open_confirmed": {},
                }
                continue

            top_board: str | None = None
            for cand in _BOARD_PRIORITY:
                if cand in exposed_boards and exposed_boards[cand]["confirmed"]:
                    top_board = cand
                    break
            if top_board is None:
                for cand in _BOARD_PRIORITY:
                    if cand in exposed_boards:
                        top_board = cand
                        break
            top = exposed_boards[top_board] if top_board else {}

            result[ticker] = {
                "k": info.get("k", 0),
                "target_price": top.get("target_price", 0),
                "open_price": top.get("open_price", 0),
                "target_offset": top.get("target_offset", 0),
                "limit_up_reached": limit_up,
                "boards": exposed_boards,
                "open_confirmed": exposed_confirmed,
            }
        return result

    _BOARD_K_KEY = {
        "main": "k_value_krx_main",
        "pre_nxt": "k_value_nxt_pre",
        "post_nxt": "k_value_nxt_post",
    }

    def _resolve_active_board(self) -> str | None:
        from src.engine.session import session_tracker, MarketBoard

        active = session_tracker.active
        if not active:
            return None
        allowed = self.config.params.get("tradable_boards") or list(self.DEFAULT_TRADABLE_BOARDS)
        for candidate in ("main", "post_nxt", "pre_nxt"):
            if candidate in allowed and MarketBoard(candidate) in active:
                return candidate
        return None

    def on_open_price_confirmed(self, ticker: str, open_price: int, board: str = "main") -> None:
        """보드별 시가 확정 + Target 계산."""
        info = self._targets.get(ticker)
        if not info or open_price <= 0:
            return
        base = info.get("target_offset_base", info.get("target_offset", 0))
        k_key = self._BOARD_K_KEY.get(board, "k_value_krx_main")
        k_mult = float(self.config.params.get(k_key, 1.0))
        target_offset = max(int(base * k_mult), 0)
        info.setdefault("boards", {})[board] = {
            "open_price": open_price,
            "target_price": open_price + target_offset,
            "target_offset": target_offset,
        }
        self._open_confirmed.setdefault(ticker, {})[board] = True
        if not info.get("open_price"):
            info["open_price"] = open_price
            info["target_price"] = open_price + target_offset
            info["target_offset"] = target_offset

    def check_buy_signal(
        self, ticker: str, current_price: int, open_price: int,
    ) -> Signal:
        """현재 활성 보드의 Target Price 돌파 시 매수."""
        from src.engine.scanner import t, ticker_names, ticker_prev_close

        if self.state.buy_disabled:
            return Signal.NONE
        if self.state.has_position(ticker) or self.state.is_buy_pending(ticker) or self.state.is_sold_today(ticker):
            return Signal.NONE
        if self.is_max_positions():
            return Signal.NONE
        if self.is_daily_loss_exceeded():
            return Signal.NONE

        info = self._targets.get(ticker)
        if not info:
            return Signal.NONE

        board = self._resolve_active_board()
        if board is None:
            return Signal.NONE

        confirmed = self._open_confirmed.get(ticker, {}).get(board, False)
        if not confirmed and open_price > 0:
            self.on_open_price_confirmed(ticker, open_price, board=board)

        board_info = info.get("boards", {}).get(board)
        if not board_info:
            return Signal.NONE

        target = board_info.get("target_price", 0)
        if target <= 0:
            return Signal.NONE

        # 전일대비 등락률 필터 (보드 무관)
        prev_close = ticker_prev_close.get(ticker, 0)
        if prev_close > 0:
            prdy_rate = (current_price - prev_close) / prev_close * 100
            min_rate = self.config.params["min_prdy_rate"]
            if prdy_rate < min_rate:
                return Signal.NONE

        prev = self._prev_price.setdefault(ticker, {}).get(board, 0)
        self._prev_price[ticker][board] = current_price

        if prev == 0:
            return Signal.NONE

        # 돌파 순간 감지
        if prev < target and current_price >= target:
            board_open = board_info.get("open_price", 0)
            change_rate = round((current_price - board_open) / board_open * 100, 1) if board_open > 0 else 0
            logger.info(
                "롱테일 변동성 돌파 매수 신호 [%s]: %s 현재가(%d) >= 목표가(%d), K=%.4f",
                board, t(ticker), current_price, target, info["k"],
            )
            self.state.buy_signals.append({
                "ticker": ticker,
                "name": ticker_names.get(ticker, ""),
                "price": current_price,
                "target_price": target,
                "k": info["k"],
                "board": board,
                "change_rate": change_rate,
                "time": datetime.now().strftime("%H:%M:%S"),
            })
            if len(self.state.buy_signals) > 20:
                self.state.buy_signals.pop(0)
            return Signal.BUY

        return Signal.NONE

    def check_exit_signal(
        self, ticker: str, current_price: int, open_price: int,
    ) -> Signal:
        """2단계 청산: 당일 모드(손절 -3%) / 익일 모드(손절 -5% + 트레일링)."""
        from src.engine.scanner import t, ticker_prev_close

        pos = self.state.positions.get(ticker)
        if not pos:
            return Signal.NONE

        loss_rate = (current_price - pos.buy_price) / pos.buy_price * 100

        # --- 익일 청산 모드 (상한가 도달 후 전환된 종목) ---
        if ticker in self._limit_up_reached:
            if pos.is_next_day:
                # 시가 안정화 대기 중에는 청산 판단 억제
                if self._next_day_clear_pending:
                    # 손절만 유지
                    if loss_rate <= self.config.params["overnight_stop_loss"]:
                        logger.info("롱테일VB 익일 손절: %s %.1f%%", t(ticker), loss_rate)
                        return Signal.STOP_LOSS
                    return Signal.NONE

                gap_threshold = self.config.params["gap_up_threshold"]
                trailing_rate = self.config.params["trailing_stop_rate"]
                gap_rate = (open_price - pos.buy_price) / pos.buy_price * 100 if pos.buy_price > 0 else 0

                if gap_rate < gap_threshold:
                    logger.info("롱테일VB 익일 즉시 청산: %s 갭률 %.1f%%", t(ticker), gap_rate)
                    return Signal.NEXT_DAY_CLEAR

                # 갭상승 → 트레일링 스탑
                pos.high_since_buy = max(pos.high_since_buy, current_price)
                drop_rate = (current_price - pos.high_since_buy) / pos.high_since_buy * 100
                if drop_rate <= trailing_rate:
                    logger.info("롱테일VB 트레일링 스탑: %s 고점(%d) 대비 %.1f%%", t(ticker), pos.high_since_buy, drop_rate)
                    return Signal.TRAILING_STOP
                return Signal.NONE

            # 당일 (상한가 도달 후) — overnight 손절만 적용
            if loss_rate <= self.config.params["overnight_stop_loss"]:
                logger.info("롱테일VB 손절(상한가 모드): %s %.1f%%", t(ticker), loss_rate)
                return Signal.STOP_LOSS
            return Signal.NONE

        # --- 당일 모드 (상한가 미도달) ---
        # 손절
        if loss_rate <= self.config.params["intraday_stop_loss"]:
            logger.info("롱테일VB 당일 손절: %s %.1f%%", t(ticker), loss_rate)
            return Signal.STOP_LOSS

        # 상한가 도달 체크 → 모드 전환
        prev_close = ticker_prev_close.get(ticker, 0)
        if prev_close > 0:
            prdy_rate = (current_price - prev_close) / prev_close * 100
            threshold = self.config.params["limit_up_threshold"]
            if prdy_rate >= threshold:
                self._limit_up_reached.add(ticker)
                logger.info(
                    "롱테일VB 상한가 모드 전환: %s 등락률 %.1f%% >= %.1f%%",
                    t(ticker), prdy_rate, threshold,
                )

        return Signal.NONE

    def check_force_clear(self) -> list[str]:
        """15:20 강제 청산 대상 — 상한가 모드가 아닌 종목만."""
        return [
            ticker for ticker in self.state.positions
            if ticker not in self._limit_up_reached
        ]

    def calc_buy_quantity(self, current_price: int) -> int:
        """할당 자금의 position_ratio 비중. 비중 기준 0주여도 잔여 자금이 1주 살 수 있으면 1주."""
        if current_price <= 0:
            return 0
        ratio = self.config.params["position_ratio"]
        amount = int(self.state.total_investment * ratio)
        qty = amount // current_price
        if qty > 0:
            return qty
        return self._fallback_one_share(current_price)
