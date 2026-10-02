"""cycle384 Red — 공통 `buy_paused`(신규 매수 신호만 멈춤) · 공용 지원. 이 모듈은 테스트가 아니다.

명세 정본 = `_workspace/red/cycle384_buy_paused_spec.md` (이하 「명세」)

## Red 가 못박는 표면 (명세 §2.2 · §2.3)

``src/engine/strategy_base.py``

| 이름 | 계약 |
|---|---|
| ``BUY_PAUSED_KEY = "buy_paused"`` | 모듈 상수. `PARAM_RANGES`/`INT_PARAMS` 편입 금지 |
| ``_PAUSE_ENTRY_LATCH_ATTRS == ("_breakout_first_seen", "_vol_latch")`` | 멈춘 종목에서 지우는 진입 래치 — 이 두 이름뿐 |
| ``StrategyBase._buy_paused_logged`` | ``KstDailyEmitCap`` (``__init__``) — 키 ``cfg|p|v`` · ``skip|{ticker}`` |
| ``StrategyBase._buy_paused_blocked(ticker) -> bool`` | 매 호출 ``self.config.params`` 에서 읽는다. ``is True`` 만 멈춤 |
| ``StrategyBase._clear_entry_latches_on_pause(ticker) -> tuple[str, ...]`` | 뺀 속성 이름(앞 ``_`` 제거) |
| ``StrategyBase._emit_buy_paused_config`` · ``_emit_buy_paused_skip`` | never-raise · peek→log→mark |

게이트(``_account_soft_gate_blocked``) 순서 = 상태 차단(J25) → **멈춤** → 계좌 SOFT.

## 시계

전략 모듈 · ``strategy_base`` · ``daily_emit_cap`` 의 ``datetime`` 이름을 같은 ``Clock`` 을 따르는
서브클래스로 바꾼다(``_cycle369_support.pin_module_clock``) — naive(donchian·BFB·VCP 시간 가드)와
aware(kojiro·momentum·VB) 가 같은 KST 를 본다. ``KstDailyEmitCap`` 의 날짜 자기 리셋도 같은 시계를
따른다(다음 KST 날짜 테스트). ``tick_volume`` 은 실제 벽시계로 기록·조회해 서로 맞는다.
"""
from __future__ import annotations

import importlib
import logging
from datetime import date

import pytest

from tests.unit.engine._cycle369_support import Clock, kst, pin_module_clock

SB_LOGGER = "src.engine.strategy_base"
DAY = date(2026, 9, 28)        # 월 — 09-28 운영일
NEXT_DAY = date(2026, 9, 29)
T = "990384"                   # 합성 종목 — 실종목과 겹치지 않는다
U = "990385"
V = "990386"

ALL7: tuple[str, ...] = (
    "momentum",
    "volatility_breakout",
    "long_tail_volatility",
    "donchian_swing",
    "bull_flag_breakout",
    "vcp_breakout",
    "kojiro",
    "etf_trend",
)
# cycle403 — etf_trend 의 게이트도 check_buy_signal 첫 문장(폴/래치형과 같은 위치).
GATE_FIRST5 = ("long_tail_volatility", "donchian_swing", "bull_flag_breakout", "vcp_breakout", "kojiro",
               "etf_trend")
PRE_BUY2 = ("momentum", "volatility_breakout")

_CLASSES = {
    "momentum": ("src.engine.strategies.momentum", "MomentumStrategy"),
    "volatility_breakout": ("src.engine.strategies.volatility_breakout", "VolatilityBreakoutStrategy"),
    "long_tail_volatility": ("src.engine.strategies.long_tail_volatility", "LongTailVolatilityStrategy"),
    "donchian_swing": ("src.engine.strategies.donchian_swing", "DonchianSwingStrategy"),
    "bull_flag_breakout": ("src.engine.strategies.bull_flag_breakout", "BullFlagBreakoutStrategy"),
    "vcp_breakout": ("src.engine.strategies.vcp_breakout", "VcpBreakoutStrategy"),
    "kojiro": ("src.engine.strategies.kojiro", "KojiroStrategy"),
    "etf_trend": ("src.engine.strategies.etf_trend", "EtfTrendStrategy"),
}

#: 전략별 「사는 순간」 시각 — 창 안(donchian·kojiro 09:05~09:30 · BFB/VCP 진입창 · 15:20 컷 앞)
AT = {
    "momentum": (9, 40),
    "volatility_breakout": (9, 40),
    "long_tail_volatility": (9, 40),
    "donchian_swing": (9, 10),
    "kojiro": (9, 10),
    "etf_trend": (9, 10),
    "bull_flag_breakout": (10, 0),
    "vcp_breakout": (10, 0),
}


# ===========================================================================
# Red 관문 — 새 표면이 없으면 사유를 밝히고 실패한다(skip 금지)
# ===========================================================================
def need_pause_surface() -> None:
    from src.engine import strategy_base as sb

    missing = [n for n in ("_buy_paused_blocked", "_clear_entry_latches_on_pause",
                           "_emit_buy_paused_config", "_emit_buy_paused_skip")
               if not hasattr(sb.StrategyBase, n)]
    if not hasattr(sb, "BUY_PAUSED_KEY"):
        missing.append("BUY_PAUSED_KEY")
    if missing:
        pytest.fail(f"[Red] strategy_base 에 {missing} 없음 — cycle384 미구현")


# ===========================================================================
# 전략
# ===========================================================================
def strategy_module(sid: str):
    return importlib.import_module(_CLASSES[sid][0])


def strategy_class(sid: str):
    mod_name, cls_name = _CLASSES[sid]
    return getattr(importlib.import_module(mod_name), cls_name)


def make(sid: str, *, budget: int = 10_000_000, **params):
    from src.engine.strategy_base import StrategyConfig

    s = strategy_class(sid)(StrategyConfig(strategy_id=sid, name=sid, params={"exchange": "KRX", **params}))
    s.state.total_investment = budget
    return s


def pause(s, value=True) -> None:
    """PUT 과 같은 경로 — 같은 ``config.params`` dict 를 고친다(재시작·prepare 없음)."""
    s.config.params["buy_paused"] = value


def pin_clocks(monkeypatch, clock: Clock, *sids: str) -> None:
    """전략 모듈 + ``strategy_base`` + ``daily_emit_cap`` 의 ``datetime`` 을 같은 KST 시계로."""
    from src.engine import daily_emit_cap, strategy_base

    mods = [strategy_module(sid) for sid in sids] + [strategy_base, daily_emit_cap]
    pin_module_clock(monkeypatch, clock, *mods)


class Buyable:
    """sid 별 「멈추지 않으면 이번 평가가 BUY」 합성 입력.

    - ``prime()`` = edge 전략(momentum·VB·LTV·BFB·VCP)의 기준 틱(교차 아님). 나머지는 no-op.
    - ``fire()``  = 사는 순간의 평가. 멈추지 않았으면 ``Signal.BUY`` 여야 한다(양성 대조가 잰다).
    """

    def __init__(self, sid: str, monkeypatch, clock: Clock, *, ticker: str = T, day: date = DAY,
                 **params) -> None:
        from src.engine import scanner, tick_volume

        self.sid = sid
        self.t = ticker
        self.clock = clock
        h, m = AT[sid]
        clock.set(h, m, day=day)
        self.level: int | None = None
        if sid == "momentum":
            self.s = make(sid, **params)
            prev = dict(getattr(scanner, "ticker_prev_close", {}) or {})
            prev[ticker] = 10_000
            monkeypatch.setattr(scanner, "ticker_prev_close", prev)
            self.prime_px, self.fire_px, self.open = 12_800, 12_950, 12_000     # 28.0% → 29.5%
        elif sid in ("volatility_breakout", "long_tail_volatility"):
            self.s = make(sid, **params)
            self.s._targets[ticker] = {
                "k": 0.5, "prev_range": 1000, "target_offset_base": 500, "target_offset": 500,
                "target_price": 10_500, "open_price": 10_000,
                "boards": {"main": {"open_price": 10_000, "target_price": 10_500, "target_offset": 500}},
            }
            self.s._open_confirmed[ticker] = {"main": True}
            monkeypatch.setattr(self.s, "_resolve_active_board", lambda: "main")
            self.prime_px, self.fire_px, self.open = 10_400, 10_550, 10_000
            self.level = 10_500
        elif sid == "donchian_swing":
            self.s = make(sid, **params)
            self.s._candidates[ticker] = {"prev_close": 10_000, "donchian_high": 10_500,
                                          "ema60": 9_000, "atr": 200}
            self.prime_px, self.fire_px, self.open = None, 10_600, 10_100
        elif sid == "etf_trend":
            # market_unit_mode="off" — 이 전략의 L4 전용 시장 유닛 하드 게이트(결손·m=0 신호
            # 단계 차단)는 공용 Buyable 하네스가 스냅샷을 안 심어 주므로 꺼서 우회한다
            # (다른 터틀 전략은 이 게이트가 fail-open 이라 영향이 없다). shadow_mode=False —
            # 이 전략만 코드 기본값이 True(S1)라 다른 6전략과 같은 "기본은 실전 매수" 베이스라인을
            # 맞춘다(섀도 자체를 재는 t02 류는 `shadow(r.s, True)` 로 다시 켠다).
            self.s = make(sid, market_unit_mode="off", shadow_mode=False, **params)
            self.s._candidates[ticker] = {
                "prev_close": 10_000, "line": 9_900, "n": 200.0, "atr": 200.0,
                "atr20": 210.0, "tv20": 3_000_000_000.0, "ema60": 9_500, "cluster_key": None,
            }
            self.prime_px, self.fire_px, self.open = None, 10_100, 10_050
        elif sid == "kojiro":
            self.s = make(sid, budget=2_000_000, sizing_mode="turtle", risk_pct=0.005,
                          position_ratio=0.166, max_positions=6, **params)
            self.s._candidates[ticker] = {"stage": 1, "prev_close": 50_000, "atr": 1_000.0,
                                          "sector": "반도체", "name": "합성"}
            self.prime_px, self.fire_px, self.open = None, 50_500, 50_000
        elif sid == "bull_flag_breakout":
            self.s = make(sid, **{"breakout_retention_minutes": 0, **params})
            self.level = 10_000
            self.s._candidates[ticker] = {
                "pole_start": 7_000, "pole_high": 9_800, "flag_high": 10_000, "flag_low": 9_500,
                "flag_avg_volume": 10_000.0, "pole_len": 5, "flag_len": 9, "atr14": 300,
                "prev_close": 9_700,
            }
            self.prime_px, self.fire_px, self.open = 9_900, 10_060, 9_600
            tick_volume.record_acml_vol(ticker, 50_000)                          # 임계 20,000
        elif sid == "vcp_breakout":
            self.s = make(sid, **params)
            self.level = 10_000
            self.s._candidates[ticker] = {
                "base_high": 10_000, "base_low": 9_000, "avg_volume_20": 10_000,
                "atr14": 300, "ema50": 9_400,
            }
            self.prime_px, self.fire_px, self.open = 9_900, 10_100, 9_700
            tick_volume.record_acml_vol(ticker, 50_000)                          # 임계 15,000
        else:  # pragma: no cover
            raise AssertionError(sid)

    def prime(self):
        from src.engine.strategy_base import Signal

        if self.prime_px is None:
            return Signal.NONE
        return self.s.check_buy_signal(self.t, self.prime_px, self.open)

    def fire(self, price: int | None = None):
        return self.s.check_buy_signal(self.t, self.fire_px if price is None else price, self.open)


def ready(sid: str, monkeypatch, clock: Clock | None = None, **kw) -> Buyable:
    """시계를 고정하고 ``Buyable`` 을 만든다. 한 테스트에서 여러 전략을 쓰면 **같은** ``clock`` 을 넘긴다
    (``strategy_base``·``daily_emit_cap`` 은 공유 모듈이라 시계가 둘이면 뒤의 것이 이긴다)."""
    clock = clock or Clock(kst(*AT[sid]))
    pin_clocks(monkeypatch, clock, sid)
    return Buyable(sid, monkeypatch, clock, **kw)


# ===========================================================================
# 로그 판독 — 두 마커 모두 로거 `src.engine.strategy_base`
# ===========================================================================
def open_info(caplog) -> None:
    caplog.set_level(logging.INFO, logger=SB_LOGGER)


def recs(caplog, marker: str, *, min_level: int = logging.INFO, logger: str = SB_LOGGER):
    return [
        r for r in caplog.records
        if r.name == logger and r.levelno >= min_level and r.getMessage().startswith(marker + " ")
    ]


def lines(caplog, marker: str, *, min_level: int = logging.INFO, logger: str = SB_LOGGER) -> list[str]:
    return [r.getMessage() for r in recs(caplog, marker, min_level=min_level, logger=logger)]


def field(line: str, key: str) -> str:
    token = f"{key}="
    for part in line.split():
        if part.startswith(token):
            return part[len(token):]
    raise AssertionError(f"`{key}=` 없음: {line}")


__all__ = [
    "ALL7", "AT", "Buyable", "Clock", "DAY", "GATE_FIRST5", "NEXT_DAY", "PRE_BUY2", "SB_LOGGER",
    "T", "U", "V", "field", "kst", "lines", "make", "need_pause_surface", "open_info", "pause",
    "pin_clocks", "ready", "recs", "strategy_class", "strategy_module",
]
