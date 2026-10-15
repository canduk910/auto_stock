"""비식별 보유(unknown) — 출처 모를 보유를 맡아 청산만 하는 전용 전략 (cycle461 ⑦-F1 안 U).

사용자 결정 2026-10-10(① 안 U · ② 계좌 자동매매 전용 · ③ 권리 입고도 즉시 매도 · ④ 주인 꺼짐 =
같은 청산 경로 · ⑤ `observe` 로 시작) + 2026-10-15 「구현 시작하자」. 자문 =
`_workspace/domain_consult/2026-10-10_f1_unknown_holding_liquidation.md`.

- **비중 0 · 항상 켜짐 · 매수 없음.** 켜짐은 `config` 객체가 지킨다(`_AlwaysOnConfig` — 누가
  `enabled = False` 를 써도 무시된다). 끄면 `risk.on_tick` 이 이 전략 보유의 청산 평가를
  멈추기 때문이다(루트 금기 「보유 포지션이 있는 전략을 끄지 않는다」).
- 보유는 `engine/unknown_holding_policy.py` 가 올린다(부팅 KIS 잔고 보완 · 15분 동기화). 사유
  (`_reasons[ticker]`)가 `SELLABLE_REASONS` 일 때만 판다 — 판정 보류(`lookup_failed`)와 재시작으로
  사유를 잃은 보유는 팔지 않는다.
- **청산 창 = `status_exit_watch.FIRE_WINDOW_START`(09:00:30) ≤ t < `FIRE_WINDOW_END`(15:28)** —
  같은 성격(출처 불문 청산)이라 창을 하나로 둔다. 프리장은 `risk._PRE_MARKET_EXIT_EVAL_STRATEGIES`
  밖이라 평가 자체가 보류되고, 15:28~20:00(마감 동시호가·애프터)은 쏘지 않는다.
- **모드 `unknown_exit_mode`** ∈ `off|observe|enforce` — 부재·오타·비문자열 = `observe`(주문 쪽이
  아니라 기록 쪽으로 fail). `observe` = `[unknown_exit_would_fire]` 만(주문 0). `enforce` = 시장가
  `Signal.UNKNOWN_EXIT` → `order_engine.execute_sell`(거부 처리 규약 그대로). 종목당 하루
  `MAX_FIRES_PER_DAY`(3)회 · 발사 간격 `SELL_INTERVAL_S`(300초, 5분 거부 TTL 과 같은 폭) — 다 쓰면
  `[unknown_exit_giveup]` CRITICAL 1회/일, 다음 영업일 다시.
- `PARAM_RANGES`/`INT_PARAMS`·AI 자문 편입 금지(`recommendation_engine` 이 이 전략을 거른다).
"""

from __future__ import annotations

import logging
from datetime import date

from src.engine import unknown_holding_policy as _uhp
from src.engine.status_exit_watch import (
    FIRE_WINDOW_END,
    FIRE_WINDOW_START,
    MAX_FIRES_PER_DAY,
    SELL_INTERVAL_S,
)
from src.engine.strategy_base import Signal, StrategyBase, StrategyConfig

logger = logging.getLogger(__name__)

UNKNOWN_EXIT_MODE_KEY = "unknown_exit_mode"
UNKNOWN_EXIT_MODES = ("off", "observe", "enforce")
UNKNOWN_EXIT_MODE_DEFAULT = "observe"


class _AlwaysOnConfig(StrategyConfig):
    """`enabled` 가 항상 True 인 설정 — 대입은 무시한다(비중 0·DB 행·`update_weights` 무관)."""

    @property  # type: ignore[override]
    def enabled(self) -> bool:
        return True

    @enabled.setter
    def enabled(self, value: bool) -> None:  # noqa: ARG002 — 의도된 무시
        return None


def normalize_exit_mode(raw: object) -> str:
    """`unknown_exit_mode` 해석 — 어휘 밖·결측은 `observe`."""
    if isinstance(raw, str):
        v = raw.strip().lower()
        if v in UNKNOWN_EXIT_MODES:
            return v
    return UNKNOWN_EXIT_MODE_DEFAULT


class UnknownHoldingStrategy(StrategyBase):
    """비식별 보유 — 매수하지 않고, 맡은 보유를 KRX 정규장 창에서 시장가로 청산한다."""

    #: 항상 켜짐 표시(라우트 비중 가드가 읽는다).
    ALWAYS_ENABLED = True

    DEFAULT_TRADABLE_BOARDS = ("main",)

    DEFAULT_PARAMS = {
        # ── 전 전략 공통 필수 키(REQUIRED_COMMON_KEYS) — 이 전략에서는 뜻이 없지만 가드가 요구한다 ──
        "buy_paused": False,
        "shadow_mode": False,
        "daily_loss_limit": -20.0,
        "position_ratio": 0.01,
        "max_positions": 1,
        "max_lot_ratio_mult": 2.5,
        "tradable_boards": list(DEFAULT_TRADABLE_BOARDS),
        "exchange": "KRX",
        "order_exchange_clock_mode": "enforce",
        "after_market_exit_division": "44",
        "llm_gate_mode": "shadow",  # 다른 전략과 같은 값(cycle297) — 매수가 없어 호출 0
        "llm_gate_min_score": 70,
        "llm_gate_daily_call_cap": 20,
        "llm_gate_timeout_secs": 20,
        # ── 이 전략 고유 ──
        "unknown_exit_mode": "observe",
    }

    def __init__(self, config: StrategyConfig):
        merged = {**self.DEFAULT_PARAMS, **config.params}
        always_on = _AlwaysOnConfig(
            strategy_id=config.strategy_id, name=config.name,
            enabled=True, weight=config.weight, params=merged,
        )
        super().__init__(always_on)
        #: 종목 → 채택 사유(`unknown_holding_policy`). 메모리 전용 — 재시작이면 비고 재판정된다.
        self._reasons: dict[str, str] = {}
        self._exit_day: date | None = None
        self._fires: dict[str, int] = {}
        self._last_fire: dict = {}
        self._emitted: set[tuple[str, str]] = set()

    # ------------------------------------------------------------------
    async def prepare(self, *, as_of: date | None = None) -> None:
        """후보가 없다 — 매수하지 않는다."""
        return None

    def get_scanned_tickers(self) -> list[str]:
        return []

    def check_buy_signal(self, ticker: str, current_price: int, open_price: int) -> Signal:
        """매수 신호를 절대 내지 않는다."""
        if self._account_soft_gate_blocked(ticker):
            return Signal.NONE  # 공통 게이트 첫 문장(AST GATE_FIRST) — 이 전략은 어차피 NONE
        return Signal.NONE

    def calc_buy_quantity(self, current_price: int, ticker: str | None = None) -> int:
        """비중 0 — 예산이 없다. 모든 return 이 공통 관문을 지난다(AST A-GATE)."""
        return self._apply_budget_limit(0, current_price, ticker)

    # ------------------------------------------------------------------
    def _exit_mode(self) -> str:
        try:
            return normalize_exit_mode(self.config.params.get(UNKNOWN_EXIT_MODE_KEY))
        except Exception:
            return UNKNOWN_EXIT_MODE_DEFAULT

    def _roll_day(self, today: date) -> None:
        if self._exit_day != today:
            self._exit_day = today
            self._fires.clear()
            self._last_fire.clear()
            self._emitted.clear()

    def _emit_once(self, kind: str, ticker: str, level: int, msg: str, *args) -> None:
        key = (kind, ticker)
        if key in self._emitted:
            return
        self._emitted.add(key)
        logger.log(level, msg, *args)

    def check_exit_signal(self, ticker: str, current_price: int, open_price: int) -> Signal:
        """창 안 + 팔 사유가 있는 보유만 — `observe` 는 기록, `enforce` 는 `UNKNOWN_EXIT`."""
        try:
            if not self.state.has_position(ticker):
                return Signal.NONE
            reason = self._reasons.get(ticker)
            if reason not in _uhp.SELLABLE_REASONS:
                return Signal.NONE
            mode = self._exit_mode()
            if mode == "off":
                return Signal.NONE
            now = _uhp.now_kst()
            if not (FIRE_WINDOW_START <= now.time() < FIRE_WINDOW_END):
                return Signal.NONE
            self._roll_day(now.date())
            qty = self.state.positions[ticker].quantity
            if mode == "observe":
                self._emit_once(
                    "would", ticker, logging.WARNING,
                    "[unknown_exit_would_fire] ticker=%s reason=%s qty=%d mode=observe — 주문 없음",
                    ticker, reason, qty,
                )
                return Signal.NONE
            fires = self._fires.get(ticker, 0)
            if fires >= MAX_FIRES_PER_DAY:
                self._emit_once(
                    "giveup", ticker, logging.CRITICAL,
                    "[unknown_exit_giveup] ticker=%s reason=%s fires=%d — 오늘 멈춘다, 다음 영업일 다시",
                    ticker, reason, fires,
                )
                return Signal.NONE
            last = self._last_fire.get(ticker)
            if last is not None and (now - last).total_seconds() < SELL_INTERVAL_S:
                return Signal.NONE
            self._fires[ticker] = fires + 1
            self._last_fire[ticker] = now
            logger.warning(
                "[unknown_exit_fire] ticker=%s reason=%s qty=%d attempt=%d mode=enforce",
                ticker, reason, qty, fires + 1,
            )
            return Signal.UNKNOWN_EXIT
        except Exception:
            logger.exception("[unknown_exit_eval_failed] ticker=%s", ticker)
            return Signal.NONE

    def on_position_closed(self, ticker: str) -> None:
        self._reasons.pop(ticker, None)
