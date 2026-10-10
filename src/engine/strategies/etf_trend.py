"""ETF 추세 전략 — 국내주식형 1배 ETF 20일 신고가 돌파(cycle403).

명세 = `_workspace/cycle403_etf_trend_spec.md`. 설계 = `_workspace/design/2026-09-27_etf_trend_strategy.md`.
도메인 자문 = `_workspace/domain_consult/cycle403_etf_trend_impl_review.md`(§11 이 §2·§5·§7 을 덮는다).

국내 지수·업종 ETF(코스피200·코스닥150·반도체·2차전지 등) 가운데 거래가 충분한 것만 골라,
종가가 직전 20일 고가를 넘고 60일 EMA 가 상승 중이며 거래대금이 1.5배 이상 붙은 ETF 를
다음 날 아침(09:05~09:30) 산다. 산 뒤에는 변동성 N(TR14 단순평균) 기반 손절·본전 승격·
트레일링·10일 채널 이탈로 청산하고, 매수 이틀째 거래일부터는 15:20 에 돌파선 아래로 떨어져
있으면 그날 마감 동시호가에서 정리한다(돌파 실패). 지표·신호·청산 시뮬레이션의 순수 계산은
leaf `src/engine/etf_trend_core.py` 가 맡는다(재현 동등성 보장).

- **섀도 시작(S1, L3)** — 이 전략은 `shadow_mode=True` 로 등록된다. 공통 섀도 관문
  (`StrategyBase._shadow_buy_intercepted`)이 BUY 를 `[shadow_buy]` 기록으로 바꾼다.
- **시장 유닛(L4)** — `market_unit_mode != "off"` 이면 결손·m≤0 을 **신호 정의**로 거른다
  (shadow 에서도 거른다). 랏 축소는 `enforce` 일 때만(터틀 4전략과 같은
  `_market_unit_blocks_entry`/`_market_unit_sizing` 경로).
- **1주 폴백 금지(L5)** — 유닛이 0 이면 관문 앞에서 리터럴 `0` 을 돌려준다.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta, timezone

from src.db.stock_master import list_etf_trend_universe
from src.db.stock_master_daily import get_recent_daily
from src.engine import etf_trend_core as core
from src.engine.daily_emit_cap import KstDailyEmitCap
from src.engine.strategy_base import FunnelStage, Signal, StrategyBase, StrategyConfig
from src.engine.turtle_sizing import compute_unit_qty_guarded

KST = timezone(timedelta(hours=9))
logger = logging.getLogger(__name__)

#: §5 L11 — 매수 평가 창(09:05~09:30, donchian 과 같은 모양). naive `datetime.now()`.
_ENTRY_WINDOW_START = time(9, 5)
_ENTRY_WINDOW_END = time(9, 30)

#: §3 묶음 상관 창·문턱(L12).
_QUALITY_WINDOW_MIN_FOR_LINE = 20  # breakout_line 이 성립하려면 신호봉 앞에 20봉 필요

#: §4 prepare 깔때기 단계(팀장 검토 D) — SQL 이 이미 합친 앞 네 조건(전체→국내주식형·1배→
#: 투자유의 제외→시총)은 1단계로 합친다.
FUNNEL_STAGES: tuple[FunnelStage, ...] = (
    FunnelStage(1, "ETF 전체 → 국내주식형·1배 → 투자유의 제외 → 시총 500억 통과"),
    FunnelStage(2, "일봉 품질 통과(일봉 수 · 최신봉 신선도 · 최근 거래일 결손 0)"),
    FunnelStage(3, "유동성·ATR 밴드 통과"),
    FunnelStage(4, "20일 신고가 돌파"),
    FunnelStage(5, "EMA60 우상향 통과"),
    FunnelStage(6, "거래대금 확대 통과"),
    FunnelStage(99, "최종 후보"),
)


class EtfTrendStrategy(StrategyBase):
    """ETF 추세(20일 신고가 돌파) 전략."""

    DEFAULT_TRADABLE_BOARDS = ("main",)
    _MARKET_UNIT_ATR_KEY = "atr"
    _PREPARE_LOG_LABEL = "et"
    _ENTRY_ATR_REDERIVE_LABEL = "et"

    # cycle431 — 액면병합·분할 대사 가격 차원 스탬프 선언(사용자 결정 2026-10-10 안1).
    _PRICE_DIM_SIMPLE_ATTRS = ("_entry_atr", "_breakout_line", "_hsb_closed", "_channel_low")

    DEFAULT_PARAMS = {
        # ── donchian 과 같은 뜻 = 같은 이름(L12) ──────────────────────────
        # 🔴 팀장 검토 MED-3 — donchian_period·long_ma_period·volume_period·atr_period·
        # channel_exit_period·atr_band_period 는 여기 두지 않는다. leaf(`etf_trend_core.py`)
        # 가 재현 측정값(20·60·20·14·10·20)을 상수로 고정해 돌리므로, 이 키를 PUT 해도
        # 동작이 바뀌지 않는다 — 바뀌지 않는 키를 화면에 두면 운영자가 속는다.
        "volume_multiplier": 1.5,
        "atr_trail_mult": 1.8,
        "gap_skip_threshold": 3.0,
        "stop_atr": 2.0,
        "turtle_backstop_pct": -9.0,
        "breakeven_promote_atr": 1.5,
        "sizing_mode": "turtle",
        "risk_pct": 0.01,
        "position_ratio": 0.25,
        "max_positions": 4,
        "min_vol_floor_pct": 0.0,
        "min_market_cap": 50_000_000_000,
        "exchange": "KRX",
        "tradable_boards": list(DEFAULT_TRADABLE_BOARDS),
        # ── 새 키(L12) ────────────────────────────────────────────────
        "gap_over_line_pct": 4.0,
        "min_trade_amount_20d": 2_000_000_000,
        "min_price": 1_000,
        "max_price": 500_000,
        "atr_ratio_min": 0.01,
        "atr_ratio_max": 0.06,
        "min_bars": 100,
        "quality_window": 60,
        "daily_fetch_rows": 225,
        "cluster_corr_window": 120,
        "cluster_corr_min_obs": 60,
        "cluster_corr_threshold": 0.9,
        "breakout_fail_min_bars": 2,
        "breakout_fail_price_max_age_secs": 180,
        # ── 공통 키 ───────────────────────────────────────────────────
        "max_lot_units": 2.0,
        "max_lot_ratio_mult": 2.5,
        "market_unit_mode": "shadow",
        "buy_paused": False,
        "shadow_mode": True,          # L3 — 이 전략만 섀도 시작(S1)
        "order_exchange_clock_mode": "enforce",
        "after_market_exit_division": "44",
        "daily_loss_limit": -8.0,
        "llm_gate_mode": "shadow",
        "llm_gate_min_score": 70,
        "llm_gate_daily_call_cap": 20,
        "llm_gate_timeout_secs": 20,
    }

    def __init__(self, config: StrategyConfig):
        merged = {**self.DEFAULT_PARAMS, **config.params}
        config.params = merged
        super().__init__(config)
        self._candidates: dict[str, dict] = {}
        self._cluster_pairs: set[frozenset] = set()
        # 팀장 검토 HIGH-1 — prepare() 는 부팅 때 positions 복구 **전**에 돈다(boot_manager).
        # 그 시점엔 묶음 계산이 후보끼리만 가능하다. recompute_held_atr(positions 복구 **후**)
        # 가 보유×후보 상관을 추가로 계산할 때 후보 종가를 다시 읽지 않도록 여기 캐시한다.
        self._candidate_closes: dict[str, dict] = {}
        self._scanned_tickers: list[str] = []
        self._bought_today: set[str] = set()
        # 멀티데이 보유 상태(§7) — on_position_closed 에서만 pop, _reset_daily_state 무접촉.
        self._breakout_line: dict[str, float] = {}
        self._entry_atr: dict[str, float] = {}
        self._hsb_closed: dict[str, float] = {}
        self._channel_low: dict[str, float] = {}
        self._bars_since_buy: dict[str, int] = {}
        self._scan_stats: dict = {"universe": 0, "candidates": 0, "clusters": 0, "last_run_at": None}
        # 관측 cap — 전부 날짜 키 자기 리셋(KstDailyEmitCap 내장).
        self._skip_logged: "KstDailyEmitCap[str]" = KstDailyEmitCap[str]()
        self._exit_logged: "KstDailyEmitCap[str]" = KstDailyEmitCap[str]()
        self._close_print_logged: "KstDailyEmitCap[str]" = KstDailyEmitCap[str]()
        self._stale_1520_logged: "KstDailyEmitCap[str]" = KstDailyEmitCap[str]()
        self._buy_eval_logged: "KstDailyEmitCap[str]" = KstDailyEmitCap[str]()
        self._universe_logged: "KstDailyEmitCap[str]" = KstDailyEmitCap[str]()

    # ------------------------------------------------------------------
    # §5 check_buy_signal — 순서가 계약
    # ------------------------------------------------------------------
    def check_buy_signal(self, ticker: str, current_price: int, open_price: int) -> Signal:
        if self._account_soft_gate_blocked(ticker):
            return Signal.NONE
        if self.state.buy_disabled:
            return Signal.NONE
        if self.state.has_position(ticker) or self.state.is_buy_pending(ticker):
            return Signal.NONE
        if self.state.is_sold_today(ticker):
            return Signal.NONE
        if ticker in self._bought_today:
            return Signal.NONE
        if self.is_max_positions():
            return Signal.NONE
        if self.is_daily_loss_exceeded():
            return Signal.NONE
        info = self._candidates.get(ticker)
        if info is None:
            return Signal.NONE
        now_t = datetime.now().time()
        if not (_ENTRY_WINDOW_START <= now_t <= _ENTRY_WINDOW_END):
            return Signal.NONE
        # L7 보강(§11) — 시가 결측(0 이하)이면 갭·붕괴를 판정하지 않는다(무래치).
        if open_price is None or open_price <= 0:
            self._emit_skip(ticker, "open_unknown")
            return Signal.NONE
        params = self.config.params
        gap_reason = core.gap_skip_reason(
            open_price, info["prev_close"], info["line"],
            gap_pct=float(params["gap_skip_threshold"]),
            over_line_pct=float(params["gap_over_line_pct"]),
        )
        if gap_reason is not None:
            self._bought_today.add(ticker)
            self._emit_skip(ticker, gap_reason)
            return Signal.NONE
        if current_price < open_price:
            self._emit_skip(ticker, "collapse")
            return Signal.NONE
        if self._cluster_blocked(ticker):
            self._emit_skip(ticker, "cluster_held")
            return Signal.NONE
        view = self._market_unit_view()
        if view.mode != "off":
            if view.state == "unavailable":
                self._emit_skip(ticker, "market_unit_unavailable")
                return Signal.NONE
            if view.m <= 0:
                self._emit_skip(ticker, "zero_state")
                return Signal.NONE
            if view.mode == "enforce" and self._market_unit_blocks_entry(ticker, current_price):
                return Signal.NONE
        # L5 — 예산 0 이면 랏 판정을 건너뛰고: 섀도 켜짐이면 섀도 관문으로(S1 비중 0 의
        # 유일한 기록 경로), 섀도 꺼짐이면 이 자리에서 바로 no_budget. 섀도 관문은 이
        # 함수 안에서 **한 곳**(AST S02)뿐이라 예산 0 분기가 그 뒤로 직행하는 쪽으로
        # 합류시킨다(먼저 반환하면 그 호출 자체가 두 번째 호출이 되어 S02 가 붉어진다).
        budget = int(self.state.total_investment)
        no_budget = budget <= 0
        if no_budget and not StrategyBase.shadow_mode_on(self):
            self._emit_skip(ticker, "no_budget")
            return Signal.NONE
        if not no_budget:
            # 팀장 검토 LOW-3 — 이 전략은 터틀 전용(비중 경로를 열지 않는다, L5). PUT 오조작
            # 등으로 sizing_mode 가 "turtle" 이 아니면 랏을 계산하지 않고 그대로 거른다.
            if not self._sizing_mode_ok():
                self._emit_sizing_mode_invalid(ticker)
                return Signal.NONE
            # L5 — 신호 단계 랏 판정은 순수 계산(스탬프 없음·관문 미경유). enforce
            # 축소는 이미 위 _market_unit_blocks_entry 가 걸러서 여기 닿지 않는다.
            qty = self._pure_turtle_qty(current_price, info)
            if qty <= 0:
                self._emit_skip(ticker, "rounds_to_zero")
                return Signal.NONE
        self._emit_buy_eval(ticker, open_price, current_price, info, view)
        if self._shadow_buy_intercepted(ticker, current_price, open_price, level=info["line"]):
            return Signal.NONE
        self._bought_today.add(ticker)
        self._breakout_line[ticker] = info["line"]
        # 팀장 검토 MED-1 — 재매수 때 이전 보유분의 멀티데이 상태가 새 매수에 섞이지
        # 않게 한다(on_position_closed 가 정상적으로 불렸어도 이중 안전).
        self._hsb_closed.pop(ticker, None)
        self._channel_low.pop(ticker, None)
        self._bars_since_buy.pop(ticker, None)
        self.state.buy_signals.append({
            "ticker": ticker,
            "name": "",
            "price": current_price,
            "open_price": open_price,
            "line": info["line"],
            "atr": info.get("atr"),
            "change_rate": 0,
            "time": datetime.now().strftime("%H:%M:%S"),
        })
        if len(self.state.buy_signals) > 20:
            self.state.buy_signals.pop(0)
        return Signal.BUY

    def _cluster_blocked(self, ticker: str) -> bool:
        """L8(§11 수정) — 묶음 캡. 풀 = 보유 ∪ 주문중 ∪ 이 전략의 당일 매도 종목."""
        if not self._cluster_pairs:
            return False
        pool = set(self.state.positions) | set(self.state.pending_buys) | set(self.state.sold_today)
        for other in pool:
            if other == ticker:
                continue
            if frozenset({ticker, other}) in self._cluster_pairs:
                return True
        return False

    def _emit_skip(self, ticker: str, reason: str, *, level: int = logging.INFO) -> None:
        key = f"{ticker}|{reason}"
        try:
            if not self._skip_logged.should_emit(key):
                return
            logger.log(level, "[etf_trend_skip] ticker=%s reason=%s", ticker, reason)
            self._skip_logged.mark_emitted(key)
        except Exception:
            logger.debug("[etf_trend_skip_failed] ticker=%s", ticker, exc_info=True)

    def _sizing_mode_ok(self) -> bool:
        """팀장 검토 LOW-3 — 이 전략은 `sizing_mode="turtle"` 전용이다(L5, 1주 폴백 금지).

        PUT 으로 다른 값이 들어오면 비중(position_ratio) 경로가 조용히 열려 L5 를
        깨므로, 랏 계산 자체를 거부한다.
        """
        try:
            return self.config.params.get("sizing_mode") == "turtle"
        except Exception:
            return False

    def _emit_sizing_mode_invalid(self, ticker: str) -> None:
        try:
            self._emit_skip(ticker, "sizing_mode_invalid", level=logging.WARNING)
        except Exception:
            logger.debug("[etf_trend_skip_failed] ticker=%s", ticker, exc_info=True)

    def _pure_turtle_qty(self, current_price: int, info: dict) -> int:
        """L5 — 설계 랏(순수 계산). `await`/상태 변경/`_apply_budget_limit` 없음.

        `check_buy_signal` 의 rounds_to_zero 판정 전용(섀도 관문보다 먼저) — 신호 단계에서
        실제 매수 때와 같은 공식으로 "0주가 될 것" 을 미리 보되, `_entry_atr` 스탬프나
        관문 관측 로그 같은 부작용은 내지 않는다(팀장 검토 A). `calc_buy_quantity` 의
        비-시장유닛 분기와 같은 식 — 중복 수식을 두지 않는다.
        """
        if not self._sizing_mode_ok():  # 팀장 검토 LOW-3
            return 0
        n = info.get("atr")
        if n is None or current_price <= 0:
            return 0
        params = self.config.params
        budget = int(self.state.total_investment)
        remaining = max(0, budget - self._calc_used_funds())
        return compute_unit_qty_guarded(
            budget, float(n), current_price, float(params["risk_pct"]),
            remaining_budget=remaining, min_vol_pct=float(params["min_vol_floor_pct"]),
            position_ratio=float(params["position_ratio"]),
        )

    def _emit_buy_eval(self, ticker: str, open_price: int, current_price: int, info: dict, view) -> None:
        key = ticker
        try:
            if not self._buy_eval_logged.should_emit(key):
                return
            logger.info(
                "[etf_trend_buy_eval] ticker=%s open_price=%d current_price=%d prev_close=%d "
                "line=%d N=%.4f m=%.2f cluster=%s",
                ticker, int(open_price), int(current_price), int(info.get("prev_close", 0)),
                int(info.get("line", 0)), float(info.get("n") or 0.0), float(view.m),
                info.get("cluster_key") or "-",
            )
            self._buy_eval_logged.mark_emitted(key)
        except Exception:
            logger.debug("[etf_trend_buy_eval_failed] ticker=%s", ticker, exc_info=True)

    # ------------------------------------------------------------------
    # §6 calc_buy_quantity — 관문 경유, 1주 폴백 없음
    # ------------------------------------------------------------------
    def calc_buy_quantity(self, current_price: int, ticker: str | None = None) -> int:
        if current_price <= 0 or ticker is None:
            return 0
        info = self._candidates.get(ticker)
        if info is None:
            return 0
        if not self._sizing_mode_ok():  # 팀장 검토 LOW-3 — 터틀 전용, 비중 경로 금지
            self._emit_sizing_mode_invalid(ticker)
            return 0
        lots = self._market_unit_sizing(current_price, ticker)
        if lots is not None:
            if lots.path != "turtle":  # 방어 2중 — _market_unit_lots 가 비중 경로로 떨어지면 거부
                self._emit_sizing_mode_invalid(ticker)
                return 0
            if lots.lot_after <= 0:
                return 0
            self._entry_atr[ticker] = lots.atr
            return self._apply_budget_limit(lots.design_after, current_price, ticker)
        n = info.get("atr")  # = _MARKET_UNIT_ATR_KEY, 시장 유닛 경로와 같은 키(AST G-242-8)
        if n is None:
            return 0
        qty = self._pure_turtle_qty(current_price, info)
        if qty <= 0:
            return 0
        self._entry_atr[ticker] = float(n)
        return self._apply_budget_limit(qty, current_price, ticker)

    # ------------------------------------------------------------------
    # §7.1 check_exit_signal — 선 1~4
    # ------------------------------------------------------------------
    def check_exit_signal(self, ticker: str, current_price: int, open_price: int) -> Signal:
        pos = self.state.positions.get(ticker)
        if pos is None:
            return Signal.NONE
        params = self.config.params
        n = self._entry_atr.get(ticker)
        hsb = self._hsb_closed.get(ticker)
        bars = self._bars_since_buy.get(ticker, 0)
        chan = self._channel_low.get(ticker)
        e = pos.buy_price
        hard = core.hard_stop(e, n, backstop_pct=float(params["turtle_backstop_pct"]),
                               stop_atr=float(params["stop_atr"]))
        candidates: list[tuple[str, float]] = [("hard", hard)]
        if hsb is not None and n:
            if hsb >= e + float(params["breakeven_promote_atr"]) * n:
                candidates.append(("breakeven", float(e)))
            candidates.append(("trail", hsb - float(params["atr_trail_mult"]) * n))
        reason, line = max(candidates, key=lambda c: c[1])
        signal: Signal | None = None
        if current_price <= line:
            signal = Signal.STOP_LOSS if reason in ("hard", "breakeven") else Signal.TRAILING_STOP
        elif bars >= 1 and chan and chan > 0 and current_price < chan:
            signal, reason = Signal.TRAILING_STOP, "channel"
        if signal is None:
            return Signal.NONE
        self._emit_exit(ticker, reason, n, bars)
        if datetime.now(KST).time() >= time(15, 30):
            self._emit_close_print_exit(ticker)
        return signal

    def _emit_exit(self, ticker: str, reason: str, n: float | None, bars: int) -> None:
        key = ticker
        try:
            if not self._exit_logged.should_emit(key):
                return
            n_s = "-" if n is None else f"{n:.4f}"
            logger.info("[etf_trend_exit] ticker=%s reason=%s entry_n=%s hold_bars=%d",
                        ticker, reason, n_s, bars)
            self._exit_logged.mark_emitted(key)
        except Exception:
            logger.debug("[etf_trend_exit_failed] ticker=%s", ticker, exc_info=True)

    def _emit_close_print_exit(self, ticker: str) -> None:
        key = ticker
        try:
            if not self._close_print_logged.should_emit(key):
                return
            logger.warning("[etf_trend_close_print_exit] ticker=%s — 15:30 종가 틱 청산 신호", ticker)
            self._close_print_logged.mark_emitted(key)
        except Exception:
            logger.debug("[etf_trend_close_print_exit_failed] ticker=%s", ticker, exc_info=True)

    # ------------------------------------------------------------------
    # §7.3 get_effective_stop_price — read-only 미러
    # ------------------------------------------------------------------
    def get_effective_stop_price(self, ticker: str) -> int | None:
        pos = self.state.positions.get(ticker)
        if pos is None:
            return None
        try:
            params = self.config.params
            n = self._entry_atr.get(ticker)
            hsb = self._hsb_closed.get(ticker)
            bars = self._bars_since_buy.get(ticker, 0)
            chan = self._channel_low.get(ticker)
            line = core.stop_line(
                pos.buy_price, n, hsb,
                backstop_pct=float(params["turtle_backstop_pct"]),
                stop_atr=float(params["stop_atr"]),
                breakeven_atr=float(params["breakeven_promote_atr"]),
                trail_atr=float(params["atr_trail_mult"]),
            )
            if bars >= 1 and chan:
                line = max(line, chan)
            return int(line)
        except Exception:
            return None

    # ------------------------------------------------------------------
    # §7.2 check_force_clear — 15:20 돌파 실패, never-raise
    # ------------------------------------------------------------------
    def check_force_clear(self) -> list[str]:
        try:
            from src.engine import scanner

            params = self.config.params
            min_bars = int(params["breakout_fail_min_bars"])
            max_age = float(params["breakout_fail_price_max_age_secs"])
            now = datetime.now(KST)
            out: list[str] = []
            held = 0
            checked = 0
            below = 0
            missing_line = 0
            stale = 0
            for ticker in list(self.state.positions.keys()):
                held += 1
                try:
                    line = self._breakout_line.get(ticker)
                    bars = self._bars_since_buy.get(ticker, 0)
                    if line is None or line <= 0:
                        missing_line += 1
                        self._emit_1520_stale(ticker, "missing_line")
                        continue
                    if bars < min_bars:
                        continue
                    price_info = scanner.ticker_prices.get(ticker) or {}
                    price = price_info.get("current_price")
                    tick_time = scanner.ticker_last_tick.get(ticker)
                    if price is None or price <= 0 or tick_time is None:
                        stale += 1
                        self._emit_1520_stale(ticker, "missing")
                        continue
                    age = (now - tick_time).total_seconds()
                    if age > max_age:
                        stale += 1
                        self._emit_1520_stale(ticker, "stale")
                        continue
                    # 팀장 검토 LOW-4 — 여기까지 온 종목만 실제로 "판단"한 것이다.
                    checked += 1
                    if price < line:
                        below += 1
                        out.append(ticker)
                        logger.info(
                            "[etf_trend_exit] ticker=%s reason=breakout_fail_1520 price=%d line=%d age_s=%.1f",
                            ticker, int(price), int(line), age,
                        )
                except Exception:
                    # 팀장 검토 C — 한 종목의 예외가 나머지 종목 판정까지 비우면 안 된다.
                    logger.warning("[etf_trend_1520_stale] ticker=%s reason=ticker_error", ticker, exc_info=True)
                    continue
            logger.info(
                "[etf_trend_1520_check] held=%d checked=%d below=%d missing_line=%d stale=%d",
                held, checked, below, missing_line, stale,
            )
            return out
        except Exception:
            logger.warning("[etf_trend_1520_error] check_force_clear 예외 — 빈 목록 반환", exc_info=True)
            return []

    def _emit_1520_stale(self, ticker: str, reason: str) -> None:
        key = ticker
        try:
            if not self._stale_1520_logged.should_emit(key):
                return
            logger.warning("[etf_trend_1520_stale] ticker=%s reason=%s", ticker, reason)
            self._stale_1520_logged.mark_emitted(key)
        except Exception:
            pass

    def force_clear_signal(self, ticker: str) -> Signal:
        """cycle402 병합 반영(§12) — 15:20 돌파 실패 청산 사유 = 추세 이탈."""
        return Signal.TREND_EXIT

    # ------------------------------------------------------------------
    # §7.5 · §8 — 상태 수명
    # ------------------------------------------------------------------
    def on_position_closed(self, ticker: str) -> None:
        self._entry_atr.pop(ticker, None)
        self._breakout_line.pop(ticker, None)
        self._hsb_closed.pop(ticker, None)
        self._channel_low.pop(ticker, None)
        self._bars_since_buy.pop(ticker, None)

    def _reset_daily_state(self) -> None:
        self._bought_today.clear()

    # ------------------------------------------------------------------
    # §8 — 대시보드 공개 메서드
    # ------------------------------------------------------------------
    def get_scanned_tickers(self) -> list[str]:
        return list(self._scanned_tickers)

    def get_scan_stats(self) -> dict:
        return dict(self._scan_stats)

    def get_targets_status(self) -> dict:
        out = {}
        for t in self._scanned_tickers:
            info = self._candidates.get(t) or {}
            out[t] = {
                "prev_close": info.get("prev_close"),
                "target_price": info.get("line"),
            }
        return out

    @staticmethod
    def _clean_rows(rows: list[dict]) -> list[dict]:
        """팀장 검토 MED-2 — O/H/L/C ≤ 0 인 봉을 제거한다(재현과 같은 전제: 양의 OHLC).

        `prepare`·`recompute_held_atr` 양쪽의 모든 일봉 fetch 가 이 헬퍼 하나를 거친다 —
        데이터 품질 결함(0 또는 음수 가격) 한 봉이 ATR·돌파선·EMA 를 오염시키지 않게.
        """
        out = []
        for r in rows:
            try:
                if (r.get("open_price", 0) > 0 and r.get("high_price", 0) > 0
                        and r.get("low_price", 0) > 0 and r.get("close_price", 0) > 0):
                    out.append(r)
            except Exception:
                continue
        return out

    # ------------------------------------------------------------------
    # §4 prepare — 07:45
    # ------------------------------------------------------------------
    async def prepare(self, *, as_of: date | None = None) -> None:
        as_of_date, preview = self._resolve_prepare_as_of(as_of)
        await self._refresh_market_unit(as_of_date=as_of_date, preview=preview)
        keep = self._preview_keep_tickers() if preview else set()
        skip = self._preview_skip_tickers() if preview else set()

        self._candidates = {t: v for t, v in self._candidates.items() if t in keep}
        self._cluster_pairs = set()
        self._reset_funnel_steps(FUNNEL_STAGES)

        params = self.config.params
        fetch_rows = int(params["daily_fetch_rows"])
        min_bars = int(params["min_bars"])
        quality_window = int(params["quality_window"])

        try:
            universe = await list_etf_trend_universe(int(params["min_market_cap"] // 100_000_000))
        except Exception:
            logger.warning("[etf_trend_universe] 유니버스 조회 실패 graceful", exc_info=True)
            universe = []
        universe_tickers = [u["ticker"] for u in universe if u.get("ticker")]

        try:
            k200_rows = self._clean_rows(await get_recent_daily("069500", fetch_rows))
        except Exception:
            k200_rows = []
        k200_asc = list(reversed(k200_rows))
        k200_dates = [r["bas_dd"] for r in k200_asc]
        k200_head = k200_dates[-1] if k200_dates else None

        asc_cache: dict[str, list] = {}

        async def _asc_for(ticker: str) -> list | None:
            if ticker in asc_cache:
                return asc_cache[ticker]
            try:
                rows = self._clean_rows(await get_recent_daily(ticker, fetch_rows))
            except Exception:
                return None
            asc = list(reversed(rows))
            asc_cache[ticker] = asc
            return asc

        candidates: dict[str, dict] = {}
        # 팀장 검토 D — 깔때기 단계별 생존 집합(FUNNEL_STAGES 와 1:1).
        quality_tickers: list[str] = []
        data_gap_excluded: list[dict] = []
        liquidity_band_tickers: list[str] = []
        breakout_tickers: list[str] = []
        ema_tickers: list[str] = []
        volume_tickers: list[str] = []
        for ticker in universe_tickers:
            if preview and ticker in skip:
                continue
            asc = await _asc_for(ticker)
            if not asc or len(asc) < min_bars:
                data_gap_excluded.append({"ticker": ticker, "name": "", "reason": "일봉 결손/부족"})
                continue
            dates = [r["bas_dd"] for r in asc]
            if k200_head is not None and dates[-1] != k200_head:
                data_gap_excluded.append({"ticker": ticker, "name": "", "reason": "최신 봉 신선도 불일치"})
                continue
            if k200_dates:
                recent_k200 = k200_dates[-quality_window:]
                if not all(d in set(dates) for d in recent_k200):
                    data_gap_excluded.append({"ticker": ticker, "name": "", "reason": "최근 거래일 결손"})
                    continue
            quality_tickers.append(ticker)
            j = len(asc) - 1
            highs = [r["high_price"] for r in asc]
            lows = [r["low_price"] for r in asc]
            closes = [r["close_price"] for r in asc]
            tv = [r["trade_value"] for r in asc]
            sig = core.entry_signal(
                highs, lows, closes, tv, j,
                min_trade_amount_20d=float(params["min_trade_amount_20d"]),
                min_price=float(params["min_price"]), max_price=float(params["max_price"]),
                atr_ratio_min=float(params["atr_ratio_min"]), atr_ratio_max=float(params["atr_ratio_max"]),
                min_bars=min_bars, volume_multiplier=float(params["volume_multiplier"]),
            )
            if sig.stage in ("liquidity", "band"):
                continue
            liquidity_band_tickers.append(ticker)
            if sig.stage == "breakout":
                continue
            breakout_tickers.append(ticker)
            if sig.stage == "ema":
                continue
            ema_tickers.append(ticker)
            if sig.stage == "volume":
                continue
            volume_tickers.append(ticker)
            if not sig.ok:
                continue  # "n"(ATR 산출 실패) — 거의 발생하지 않는다
            candidates[ticker] = {
                "prev_close": sig.close, "line": sig.line, "n": sig.n, "atr": sig.n,
                "atr20": sig.atr20, "tv20": sig.tv20, "ema60": sig.ema60, "cluster_key": None,
            }

        self._candidates = candidates
        self._record_funnel_pipeline_step(
            FUNNEL_STAGES[0], survived=universe_tickers,
            step_conditions="SQL 유니버스 쿼리(EF∧과세01∧추적배수1∧투자유의아님∧시총≥500억∧6자리숫자)",
        )
        self._record_funnel_pipeline_step(
            FUNNEL_STAGES[1], survived=quality_tickers, excluded=data_gap_excluded[:20],
            step_conditions=f"일봉 ≥{min_bars}봉 · 최신봉=KODEX200(069500) 최신봉 · 최근{quality_window}봉 결손 0",
        )
        self._record_funnel_pipeline_step(
            FUNNEL_STAGES[2], survived=liquidity_band_tickers,
            step_conditions="20일 평균 거래대금·가격 범위·ATR20/종가 밴드 통과",
        )
        self._record_funnel_pipeline_step(
            FUNNEL_STAGES[3], survived=breakout_tickers, step_conditions="종가 > 직전 20봉 고가(돌파선)",
        )
        self._record_funnel_pipeline_step(
            FUNNEL_STAGES[4], survived=ema_tickers, step_conditions="EMA60 우상향 + 종가 > EMA60",
        )
        self._record_funnel_pipeline_step(
            FUNNEL_STAGES[5], survived=volume_tickers,
            step_conditions=f"거래대금 ≥ 직전 20봉 평균 × {float(params['volume_multiplier']):.1f}",
        )
        self._record_funnel_pipeline_step(
            FUNNEL_STAGES[6], survived=list(candidates), step_conditions="모든 조건 통과 — 매수 후보",
        )

        # 팀장 검토 HIGH-1 — 후보 종가를 풀 크기와 무관하게 전부 캐시한다. prepare() 는
        # 부팅 때 positions 복구 **전**에 돌아 이 시점의 풀은 후보뿐이지만, recompute_held_atr
        # (positions 복구 **후**)가 이 캐시를 재사용해 보유×후보 상관을 마저 계산한다.
        self._candidate_closes = {
            t: {r["bas_dd"]: r["close_price"] for r in asc_cache[t]}
            for t in candidates if t in asc_cache
        }

        # 묶음 — 후보 ∪ 보유 종목 사이 모든 쌍의 상관(§4.5, 인트라데이 재-prepare 때는
        # positions 가 이미 채워져 있어 여기서도 보유×후보가 반영된다).
        pool = set(candidates) | set(self.state.positions)
        cluster_pairs: set[frozenset] = set()
        if len(pool) >= 2:
            closes_by_ticker: dict[str, dict] = dict(self._candidate_closes)
            for t in pool - set(closes_by_ticker):
                asc = await _asc_for(t)
                if not asc:
                    continue
                closes_by_ticker[t] = {r["bas_dd"]: r["close_price"] for r in asc}
            pool_list = sorted(closes_by_ticker)
            for i, a in enumerate(pool_list):
                for b in pool_list[i + 1:]:
                    try:
                        corr = core.return_correlation(
                            closes_by_ticker[a], closes_by_ticker[b], calendar=k200_dates,
                            window=int(params["cluster_corr_window"]),
                            min_obs=int(params["cluster_corr_min_obs"]),
                        )
                    except Exception:
                        corr = None
                    if corr is not None and corr > float(params["cluster_corr_threshold"]):
                        cluster_pairs.add(frozenset({a, b}))
        self._cluster_pairs = cluster_pairs

        self._scanned_tickers = sorted(candidates, key=lambda t: -(candidates[t].get("tv20") or 0))
        self._bought_today.clear()
        self._scan_stats = {
            "universe": len(universe_tickers), "candidates": len(candidates),
            "clusters": len(cluster_pairs), "last_run_at": datetime.now(KST).isoformat(),
        }
        mu_view = self._market_unit_view()
        logger.info(
            "[etf_trend_universe] universe=%d quality=%d data_gap=%d liquidity_band=%d breakout=%d "
            "ema=%d volume=%d candidates=%d clusters=%d m=%.2f",
            len(universe_tickers), len(quality_tickers), len(data_gap_excluded),
            len(liquidity_band_tickers), len(breakout_tickers), len(ema_tickers), len(volume_tickers),
            len(candidates), len(cluster_pairs), float(mu_view.m),
        )
        logger.info(
            "[etf_trend_signal] candidates=%s",
            ",".join(f"{t}(line={candidates[t]['line']:.0f} N={candidates[t]['n']:.1f} "
                     f"tv20={candidates[t]['tv20']:.0f})" for t in self._scanned_tickers),
        )

        # 복구는 recompute_held_atr 하나(§7.4) — `scheduler._boot()` 가 `_SWING_POLL_STRATEGIES`
        # 루프에서 positions 복구 **뒤**에 자동으로 부른다(etf_trend 는 명부에 swing_poll 로
        # 등록돼 있어 그 루프에 자동 편입된다). prepare() 자신은 여기서 다시 부르지 않는다 —
        # 이 시점(positions 복구 전)에 불러 봐야 보유분이 비어 있어 무의미하다(팀장 검토 HIGH-1).

    # ------------------------------------------------------------------
    # §7.4 recompute_held_atr — 부팅 복구 한 곳
    # ------------------------------------------------------------------
    async def recompute_held_atr(self) -> None:
        positions = list(self.state.positions.items())
        if not positions:
            return
        params = self.config.params
        fetch_rows = int(params["daily_fetch_rows"])
        today = datetime.now(KST).date()

        try:
            k200_rows = self._clean_rows(await get_recent_daily("069500", fetch_rows))
        except Exception:
            k200_rows = []
        k200_asc = list(reversed(k200_rows))
        k200_dates = [r["bas_dd"] for r in k200_asc]
        k200_head = k200_dates[-1] if k200_dates else None
        if not k200_dates:
            # 팀장 검토 LOW-4 — 판단 근거(069500 달력) 자체가 없을 때만 경고한다.
            # 기대 날짜와 비교하는 신선도 판정은 거래일력이 없어 할 수 없다(§11).
            logger.warning("[etf_trend_recover_skip] ticker=069500 reason=k200_unavailable")

        # 팀장 검토 HIGH-1 — prepare() 는 positions 복구 **전**에 돈다(boot_manager).
        # 여기(positions 복구 **후**)서 보유×후보 상관을 추가로 계산해 _cluster_pairs 에
        # 더한다. 후보 종가는 prepare 가 캐시해 둔 것을 그대로 쓴다(추가 DB 읽기 0).
        held_closes: dict[str, dict] = {}

        for ticker, pos in positions:
            # cycle431 — 오늘 액면병합·분할 등을 반영한 종목은 그날 재도출을
            # 통째로 건너뛴다(사용자 결정 2026-10-10 안1). `_hsb_closed`·
            # `_channel_low` 는 "매 부팅 무조건 덮어쓴다"라 옛 눈금 일봉을
            # 그대로 받으면 방금 옮긴 스탬프가 즉시 지워진다.
            from src.engine import corporate_action_reconcile as _car
            if _car.is_rescaled_today(ticker):
                logger.info(
                    "[corporate_action_rederive_guard_skip] attr=etf_trend_recompute ticker=%s",
                    ticker,
                )
                continue
            try:
                rows = self._clean_rows(await get_recent_daily(ticker, fetch_rows))
            except Exception:
                logger.warning("[etf_trend_recover_skip] ticker=%s reason=fetch_failed", ticker)
                continue
            try:
                asc = list(reversed(rows))
                if not asc:
                    self._emit_recover_skip(ticker, "no_data")
                    continue
                dates = [r["bas_dd"] for r in asc]
                held_closes[ticker] = {r["bas_dd"]: r["close_price"] for r in asc}
                buy_date = pos.buy_date
                prior_idx = [i for i, d in enumerate(dates) if d < buy_date]
                sig_idx = prior_idx[-1] if prior_idx else None

                if sig_idx is None or sig_idx < _QUALITY_WINDOW_MIN_FOR_LINE:
                    self._emit_recover_skip(ticker, "short_history")
                else:
                    highs = [r["high_price"] for r in asc]
                    lows = [r["low_price"] for r in asc]
                    closes = [r["close_price"] for r in asc]
                    if ticker not in self._breakout_line:
                        line = core.breakout_line(highs, sig_idx)
                        if line is not None:
                            self._breakout_line[ticker] = line
                    if ticker not in self._entry_atr and self._entry_atr_rederive_allowed(ticker):
                        tr = core.true_ranges(highs[:sig_idx + 1], lows[:sig_idx + 1], closes[:sig_idx + 1])
                        n = core.n14(tr, sig_idx)
                        if n is not None and n > 0:
                            self._entry_atr[ticker] = float(n)

                # 멀티데이 상태(§11) — hsb·bars·channel 은 매 부팅 무조건 덮어쓴다.
                highs = [r["high_price"] for r in asc]
                lows = [r["low_price"] for r in asc]
                after = [(d, h) for d, h in zip(dates, highs) if d >= buy_date]
                if after:
                    self._hsb_closed[ticker] = max(h for _, h in after)
                else:
                    # 팀장 검토 MED-1 — 매수일 이후 봉이 없으면 옛 값을 남기지 않는다.
                    self._hsb_closed.pop(ticker, None)

                head_stale = bool(k200_head is not None and dates and dates[-1] != k200_head)
                if k200_dates:
                    bars_count = sum(1 for d in k200_dates if d >= buy_date)
                else:
                    bars_count = len(after)
                self._bars_since_buy[ticker] = bars_count
                if head_stale:
                    self._emit_recover_skip(ticker, "head_stale")

                chan_window = lows[-10:]
                if chan_window:
                    self._channel_low[ticker] = min(chan_window)

                await self._apply_high_since_buy_from_candles(pos, [dict(r) for r in rows], today)
            except Exception:
                # 팀장 검토 LOW-2 — 한 종목의 예외가 나머지 종목 복구를 끊지 않는다.
                logger.warning("[etf_trend_recover_skip] ticker=%s reason=ticker_error",
                               ticker, exc_info=True)
                continue

        if held_closes and self._candidate_closes:
            window = int(params["cluster_corr_window"])
            min_obs = int(params["cluster_corr_min_obs"])
            threshold = float(params["cluster_corr_threshold"])
            new_pairs: set[frozenset] = set()
            for h, h_closes in held_closes.items():
                for c, c_closes in self._candidate_closes.items():
                    if h == c:
                        continue
                    try:
                        corr = core.return_correlation(
                            h_closes, c_closes, calendar=k200_dates, window=window, min_obs=min_obs,
                        )
                    except Exception:
                        corr = None
                    if corr is not None and corr > threshold:
                        new_pairs.add(frozenset({h, c}))
            if new_pairs:
                self._cluster_pairs = set(self._cluster_pairs) | new_pairs

    def _emit_recover_skip(self, ticker: str, reason: str) -> None:
        try:
            logger.warning("[etf_trend_recover_skip] ticker=%s reason=%s", ticker, reason)
        except Exception:
            pass
