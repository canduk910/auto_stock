"""사이징 — 운영 ``calc_buy_quantity`` 를 그대로 부르는 어댑터.

동결본 C7: 전략 안 사이징 규칙(``position_ratio``·``max_positions``·``risk_pct``·K축·ρ축·시장 유닛·
1주 폴백)은 운영값 그대로다. 그래서 식을 다시 쓰지 않고 **운영 전략 객체의 메서드를 부른다**.
재현이 넣어 주는 것은 넷뿐이다.

- 예산 ``state.total_investment`` = 그날 계좌 평가액(C7 단독 풀, 자기 평가액 복리)
- 이미 쓴 돈 ``_calc_used_funds()`` = 보유 랏 원가 합(인스턴스 속성으로 덮는다)
- 사이징 ATR ``_candidates[ticker]`` = 그 전략이 ``prepare`` 에서 넣는 키(``atr``·``atr14`` 등)
- 시장 유닛 ``_market_unit_snaps[오늘]`` = 그날 m 의 ``Snapshot(ok=True)``

운영 로그는 호출 동안 끈다(관측 마커가 수만 줄 쌓인다). 행위는 로그와 무관하다(운영 계약).
"""
from __future__ import annotations

import importlib.util
import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Any

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from src.engine import market_unit as _mu  # noqa: E402
from src.engine.strategy_base import StrategyConfig  # noqa: E402

_KST = timezone(timedelta(hours=9))
_STATE_OF_M = {1.0: "up_rising", 0.75: "up_falling", 0.5: "down_rising", 0.0: "down_falling"}


def load_strategy_class(module_path: str, class_name: str, alias: str):
    """다른 작업 트리의 전략 파일(예: 돈키언 개조 브랜치)을 이 트리의 ``src`` 위에 올려 클래스를 꺼낸다."""
    spec = importlib.util.spec_from_file_location(alias, module_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[alias] = mod
    spec.loader.exec_module(mod)
    return getattr(mod, class_name)


class OpSizer:
    """운영 전략 객체 하나를 들고 매수 수량만 묻는다. 순수(DB·HTTP 0 — 운영 계약 A-PURE)."""

    def __init__(self, strategy_cls, strategy_id: str, params: "dict[str, Any]",
                 atr_keys: "tuple[str, ...]" = ("atr",)):
        self.strategy_id = strategy_id
        self.atr_keys = atr_keys
        self.s = strategy_cls(StrategyConfig(strategy_id=strategy_id, name=strategy_id, weight=1.0,
                                             params=dict(params)))
        self._used = 0
        self.s._calc_used_funds = lambda: self._used   # 보유 원가 합을 재현 계좌가 넣는다

    def _prime(self, price: int, atr: float, budget: int, used: int, m: float, ticker: str,
               extra: "dict | None") -> None:
        s = self.s
        s.state.total_investment = int(budget)
        self._used = int(used)
        info = {k: atr for k in self.atr_keys}
        if extra:
            info.update(extra)
        s._candidates = {ticker: info}
        if hasattr(s, "_entry_atr"):
            s._entry_atr.clear()
        today = datetime.now(_KST).date()
        if m is None or m != m:          # NaN = 판정 불가 → 운영은 m=1.0 fail-open(스냅샷 ok=False)
            snap = _mu.Snapshot(as_of=today, preview=False, ok=False, state="unavailable", m=1.0,
                                reason="audit_missing", bar_date=None, expected_head=None, rows=0,
                                close=None, sma60=None, sma60_prev=None, above=None, rising=None)
        else:
            snap = _mu.Snapshot(as_of=today, preview=False, ok=True, state=_STATE_OF_M[float(m)],
                                m=float(m), reason="ok", bar_date=None, expected_head=None,
                                rows=_mu.MIN_ROWS, close=None, sma60=None, sma60_prev=None,
                                above=None, rising=None)
        s._market_unit_snaps = {today: snap}

    def qty(self, price: int, atr: float, *, budget: int, used: int, m: float,
            ticker: str = "999999", extra: "dict | None" = None) -> int:
        self._prime(int(price), float(atr), budget, used, m, ticker, extra)
        prev = logging.root.manager.disable
        logging.disable(logging.CRITICAL)
        try:
            q = self.s.calc_buy_quantity(int(price), ticker)
        finally:
            logging.disable(prev)
        return int(q)

    def blocks_entry(self, price: int, atr: float, *, budget: int, used: int, m: float,
                     ticker: str = "999999", extra: "dict | None" = None) -> bool:
        """운영 신호 단계의 시장 유닛 거름(``_market_unit_blocks_entry``) — enforce ∧ 줄인 랏 0."""
        self._prime(int(price), float(atr), budget, used, m, ticker, extra)
        prev = logging.root.manager.disable
        logging.disable(logging.CRITICAL)
        try:
            return bool(self.s._market_unit_blocks_entry(ticker, int(price)))
        finally:
            logging.disable(prev)
