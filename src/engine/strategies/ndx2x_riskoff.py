"""나스닥2배-위험회피(ndx2x_riskoff) — 규칙 C 그대로, 섀도 시작(cycle443).

정본 = `_workspace/domain_consult/2026-10-06_ndx2x_risk_off.md` + 연구 규칙 원본
`tools/replay/ra_us.py::feats_from_close`. 새 규칙·새 최적화·평활·손절 추가 금지.

설계 요지(자문 그대로):
- 고정 종목 418660(TIGER 미국나스닥100레버리지(합성), 환노출) **하나**. 비중 방식
  (`sizing_mode` 미설정 — turtle 아님, 손절 없는 전략에 ATR 유닛화는 금지 규약).
- 하루 한 번 판단형(`eval_driver="swing_poll"`, 명부 등록) — 실제 매수 평가 구동은
  `scheduler._ndx2x_poll_loop`(전용, 09:30~10:30 KST 1분 폴) 가 맡는다.
  `get_scanned_tickers()` 는 항상 `[]` — 공유 스윙 폴 루프(09:05~09:30, 시장가)가
  이 전략을 건드리지 않게 한다(우리 집행창·주문유형과 다르다).
- 청산(check_exit_signal)은 이 전략을 명부(`SWING_POLL_IDS`)에 등록하는 것만으로
  `risk.on_tick` 의 generic 보유-종목 순회가 커버한다(scheduler 추가 배선 0 —
  `_run_swing_rest_poll_once` 가 09:05~15:20 60s 마다 보유분을 REST 로 평가).
- 집행창 09:30~10:30 KST(양끝 포함) 지정가만(시장가 금지) — 이 사이클은 BUY 가
  섀도 관문에서 막힌다(실주문 0). SELL 은 `execute_sell(limit_price=...)` 로 실행
  가능한 경로가 이미 있지만, 섀도에서는 보유가 생기지 않아 호출될 일이 없다.
- 🔴 **실매수 전환 전 확인 항목(한계, 보고서 참조)** — `OrderEngine.execute_buy` 는
  외부에서 지정가를 강제할 공개 경로가 없다(내부 NXT 프리마켓 전용 변환뿐). 이
  사이클은 섀도만 다루므로 손대지 않는다(8영역 `order_engine.py` 승인 + domain-consult
  선행 필요 — 작업 지시서 "멈추고 보고한다"). 켜기 전에 반드시 해결한다.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone

from src.engine import ndx2x_core
from src.engine.ndx2x_ingest import NDX_INDEX_CODE, ensure_history
from src.engine.strategy_base import Signal, StrategyBase, StrategyConfig
from src.db import overseas_index as _overseas_index_db

logger = logging.getLogger(__name__)

_KST = timezone(timedelta(hours=9))


class Ndx2xRiskoffStrategy(StrategyBase):
    """나스닥2배-위험회피 — 규칙 C(120일선 20영업일 기울기 × 250일 고점 −20%)."""

    #: 유일한 거래 대상 — TIGER 미국나스닥100레버리지(합성).
    FIXED_TICKER = "418660"

    DEFAULT_TRADABLE_BOARDS = ("main",)

    DEFAULT_PARAMS = {
        # ── 7(+) 전략 공통 필수 키(REQUIRED_COMMON_KEYS, 14개) ──
        "buy_paused": False,
        "shadow_mode": True,  # cycle443 — 이 전략은 섀도로 시작한다(사용자 결정 2026-10-11)
        "daily_loss_limit": -8.0,
        "position_ratio": 1.0,
        "max_positions": 1,
        "max_lot_ratio_mult": 2.5,
        "tradable_boards": list(DEFAULT_TRADABLE_BOARDS),
        "exchange": "KRX",
        "order_exchange_clock_mode": "enforce",
        "after_market_exit_division": "44",
        "llm_gate_mode": "off",  # 상태기계 신호라 LLM 재량 평가 대상이 아니다(etf_trend 와 다른 선택)
        "llm_gate_min_score": 70,
        "llm_gate_daily_call_cap": 20,
        "llm_gate_timeout_secs": 20,
    }

    def __init__(self, config: StrategyConfig):
        merged = {**self.DEFAULT_PARAMS, **config.params}
        config.params = merged
        super().__init__(config)
        self._decision: ndx2x_core.DailyDecision | None = None
        self._decision_date: date | None = None
        self._bought_today: set[str] = set()

    # ------------------------------------------------------------------
    # 일일 판단 동기화 — scheduler 전용 폴 루프가 매 사이클 호출(idempotent, 날짜 1회).
    # ------------------------------------------------------------------
    async def sync_daily_decision(self, *, today: date | None = None) -> ndx2x_core.DailyDecision | None:
        """이력 적재 + T7/R4 계산 + `[ndx2x_signal]` 1행/일 기록(섀도 배관 검증 목적).

        날짜가 바뀌지 않았으면 즉시 반환(재계산 0) — KIS/DB 호출을 하루 1회로 묶는다.
        """
        today = today or datetime.now(_KST).date()
        if self._decision_date == today:
            return self._decision
        try:
            await ensure_history()
        except Exception:
            logger.exception("[ndx2x_ingest_error] 이력 적재 중 예외 — fail-closed 로 넘긴다")

        try:
            closes_rows = await _overseas_index_db.get_recent_closes(NDX_INDEX_CODE)
        except Exception:
            logger.exception("[ndx2x_history_read_error] overseas_index_daily 조회 실패")
            closes_rows = []

        closes = [c for _, c in closes_rows]
        decision = ndx2x_core.decide_daily(closes)
        self._decision = decision
        self._decision_date = today

        logger.info(
            "[ndx2x_signal] date=%s t7=%s r4=%s cell=%s state=%s reason=%s history_days=%d",
            today.isoformat(), decision.t7, decision.r4, decision.cell,
            decision.desired_state, decision.reason, len(closes),
        )

        latest_date = closes_rows[-1][0] if closes_rows else None
        if latest_date is not None:
            gap = self._approx_us_business_days_gap(latest_date, today)
            if gap >= 3:
                logger.warning(
                    "[ndx2x_data_stale] latest=%s today=%s gap_biz_days≈%d — 3 미국 영업일"
                    " 연속 결손 의심(주말만 보정한 근사치, 미국 공휴일 미반영)",
                    latest_date.isoformat(), today.isoformat(), gap,
                )
        return decision

    @staticmethod
    def _approx_us_business_days_gap(latest: date, today: date) -> int:
        """`latest` ~ `today` 사이의 평일(월~금) 수(둘 다 제외, 근사 — 미국 공휴일 미반영)."""
        if today <= latest:
            return 0
        gap = 0
        d = latest + timedelta(days=1)
        while d < today:
            if d.weekday() < 5:
                gap += 1
            d += timedelta(days=1)
        return gap

    # ------------------------------------------------------------------
    # StrategyBase 추상 메서드
    # ------------------------------------------------------------------
    async def prepare(self, *, as_of: date | None = None) -> None:
        """추상 메서드 요건 — 실제 일일 동기화는 `sync_daily_decision()`(idempotent)."""
        await self.sync_daily_decision(today=as_of)

    def get_scanned_tickers(self) -> list[str]:
        """항상 빈 목록 — 공유 스윙 매수 폴 루프(09:05~09:30, 시장가)가 이 전략을
        건드리지 않게 한다. 매수 평가 구동은 `scheduler._ndx2x_poll_loop` 전용."""
        return []

    def check_buy_signal(self, ticker: str, current_price: int, open_price: int) -> Signal:
        """09:30~10:30 KST, 상태가 "2x" 로 바뀌었고 보유가 없을 때만 1회."""
        if ticker != self.FIXED_TICKER:
            return Signal.NONE
        if self._account_soft_gate_blocked(ticker):
            return Signal.NONE  # buy_paused 는 이 공통 게이트가 함께 본다(cycle384)
        if self.state.has_position(ticker) or self.state.is_buy_pending(ticker):
            return Signal.NONE
        if ticker in self._bought_today:
            return Signal.NONE

        decision = self._decision
        if decision is None or decision.desired_state != "2x":
            return Signal.NONE

        now_t = datetime.now(_KST).time()
        if not ndx2x_core.in_execution_window(now_t):
            return Signal.NONE

        action = ndx2x_core.plan_action(None, decision.desired_state)
        if action != "BUY":
            return Signal.NONE  # pragma: no cover — decision.desired_state=="2x" 면 항상 BUY

        # cycle399 — 섀도 관문: 마지막 거름 뒤 · 상태 변경 앞(AST S01).
        if self._shadow_buy_intercepted(ticker, current_price, open_price):
            return Signal.NONE

        self._bought_today.add(ticker)
        logger.info(
            "[ndx2x_buy_signal] ticker=%s price=%d cell=%s t7=%s r4=%s",
            ticker, current_price, decision.cell, decision.t7, decision.r4,
        )
        self.state.buy_signals.append({
            "ticker": ticker, "name": "", "price": current_price,
            "change_rate": 0, "time": datetime.now(_KST).strftime("%H:%M:%S"),
        })
        if len(self.state.buy_signals) > 20:
            self.state.buy_signals.pop(0)
        return Signal.BUY

    def check_exit_signal(self, ticker: str, current_price: int, open_price: int) -> Signal:
        """09:30~10:30 KST, 상태가 "cash" 로 바뀌었고 보유가 있을 때만.

        반환 신호 = `Signal.TREND_EXIT`(기존 열거값 재사용 — 이 전환 자체가 추세
        판단(T7 기울기)의 결과라 의미가 맞고, 신규 Signal 값을 늘리지 않는다).

        🔴 ticker 일치 검사를 두지 않는다(check_buy_signal 과 다르다) — `risk.on_tick`
        은 `state.positions` 에 있는 ticker 로만 이 메서드를 부르고, 이 전략은
        `FIXED_TICKER` 외의 종목을 절대 사지 않으므로 `has_position` 하나로 충분하다.
        공용 테스트 하네스(`tests/unit/engine/_cycle384_support.py` 류)가 범용 합성
        ticker 로 exit 경로를 검증하므로 이 게이트가 있으면 범용 하네스가 깨진다.
        """
        if not self.state.has_position(ticker):
            return Signal.NONE

        decision = self._decision
        if decision is None or decision.desired_state != "cash":
            return Signal.NONE

        now_t = datetime.now(_KST).time()
        if not ndx2x_core.in_execution_window(now_t):
            return Signal.NONE

        action = ndx2x_core.plan_action("2x", decision.desired_state)
        if action != "SELL":
            return Signal.NONE  # pragma: no cover

        logger.info(
            "[ndx2x_exit_signal] ticker=%s price=%d cell=%s t7=%s r4=%s",
            ticker, current_price, decision.cell, decision.t7, decision.r4,
        )
        return Signal.TREND_EXIT

    async def recompute_held_atr(self) -> None:
        """원형 계약 충족용(`eval_driver="swing_poll"` → 재시작 보유 재계산 훅).

        이 전략은 ATR 기반 손절·사이징이 없다(규칙 C 자체에 손절이 없다 — 자문
        §2 "손절 — 전략 내부 손절 두지 않는다") — 재계산할 ATR 이 없으므로 no-op.
        """
        return None

    def calc_buy_quantity(self, current_price: int, ticker: str | None = None) -> int:
        """`floor(전략 예산 × position_ratio × (1 − 0.5%) ÷ 지정가)` — 전량 1회.

        모든 return 이 `_apply_budget_limit` 공통 관문을 지난다(AST A-GATE).
        """
        if current_price <= 0:
            return 0
        ratio = self.config.params["position_ratio"]
        margin = 0.995  # 수수료·호가단위 여유(자문 §3 "1회 투자금액")
        amount = int(self.state.total_investment * ratio * margin)
        return self._apply_budget_limit(amount // current_price, current_price, ticker)
