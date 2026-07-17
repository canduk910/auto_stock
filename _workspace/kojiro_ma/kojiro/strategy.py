"""신호 엔진 — 설계서 §4의 매매 규칙을 그대로 코드로 옮김.

evaluate()는 지표가 계산된 DataFrame(마지막 행 = 최신 봉)과
현재 포지션 상태를 받아 Signal을 반환한다.
"""
from dataclasses import dataclass
from enum import Enum
from typing import Optional

import pandas as pd

from .indicators import crossed_down


class Action(Enum):
    NONE = "none"
    BUY = "buy"                # 신규 진입 (1유닛)
    BUY_EARLY = "buy_early"    # 조기 진입 (0.5유닛)
    PYRAMID = "pyramid"        # 증축 (1유닛)
    SELL_HALF = "sell_half"    # 절반 청산
    SELL_ALL = "sell_all"      # 전량 청산


@dataclass
class Position:
    code: str
    qty: int = 0
    avg_price: float = 0.0
    units: float = 0.0           # 보유 유닛 수 (0.5 단위 허용)
    entry_atr: float = 0.0       # 진입 시점 ATR (손절 계산용)
    stop_price: float = 0.0      # 현재 손절선
    highest_close: float = 0.0   # 보유 중 최고 종가 (트레일링용)
    half_sold: bool = False


@dataclass
class Signal:
    action: Action
    reason: str = ""


def _stage_recently(df: pd.DataFrame, from_stage: int, to_stage: int, within: int = 3) -> bool:
    """최근 within봉 내 from→to 스테이지 전환이 있었는지."""
    st = df["stage"].iloc[-(within + 1):].tolist()
    for a, b in zip(st, st[1:]):
        if a == from_stage and b == to_stage:
            return True
    return False


def evaluate_entry(df: pd.DataFrame, cfg) -> Signal:
    """미보유 종목의 진입 판정 (설계서 §4-1)."""
    last = df.iloc[-1]
    if pd.isna(last["ema_l"]) or last["stage"] is None:
        return Signal(Action.NONE, "지표 워밍업 부족")

    all_up = bool(last["ema_s_up"] and last["ema_m_up"] and last["ema_l_up"])

    # 기본형: 6→1 전환 + 3선 우상향 + 종가>단기선
    if (last["stage"] == 1 and _stage_recently(df, 6, 1)
            and all_up and last["close"] > last["ema_s"]):
        return Signal(Action.BUY, "스테이지 6→1 전환 + 3선 우상향")

    # 조기 진입형: 스테이지6 + 띠MACD 상승 에너지(시그널 위, 0선 아래) + 띠 폭 축소
    # 주의: 시그널선 GC는 바닥 직후 일찍 발생하므로 "GC 직후"가 아니라
    #       "GC 상태 유지 & 0선 돌파 전"을 조기 진입 창으로 본다.
    if cfg.allow_early_entry and last["stage"] == 6:
        band_shrinking = last["band_width"] < df["band_width"].iloc[-6:-1].mean()
        m3, sig3 = last["macd3"], last["macd3_sig"]
        m3_rising = df["macd3"].iloc[-1] > df["macd3"].iloc[-4]
        if m3 > sig3 and m3 < 0 and m3_rising and band_shrinking:
            return Signal(Action.BUY_EARLY, "스테이지6 + 띠MACD 0선 접근 (선행)")

    return Signal(Action.NONE)


def evaluate_exit(df: pd.DataFrame, pos: Position, cfg,
                  conservative: bool = False) -> Signal:
    """보유 종목의 청산 판정 — 우선순위 고정 (설계서 §4-2)."""
    last = df.iloc[-1]

    # 1) 손절 — 무조건 최우선
    if last["close"] <= pos.stop_price:
        return Signal(Action.SELL_ALL, f"손절선 {pos.stop_price:,.0f} 하회")

    # 2) 추세 종료: 스테이지 3 진입
    if last["stage"] == 3:
        return Signal(Action.SELL_ALL, "스테이지 3 진입 (추세 종료)")

    # 3) 보수 모드: 1→2 전환 + MACD1 데드크로스 → 절반
    if (conservative and not pos.half_sold and last["stage"] == 2
            and _stage_recently(df, 1, 2)
            and crossed_down(df["macd1"], df["macd1_sig"])):
        return Signal(Action.SELL_HALF, "스테이지 1→2 + MACD1 데드크로스")

    # 4) 트레일링 스톱
    trail = pos.highest_close - cfg.trail_atr * last["atr"]
    if pos.highest_close > 0 and last["close"] < trail:
        return Signal(Action.SELL_ALL, f"트레일링 스톱 {trail:,.0f} 하회")

    return Signal(Action.NONE)


def evaluate_pyramid(df: pd.DataFrame, pos: Position, cfg) -> Signal:
    """증축 판정 (설계서 §4-3)."""
    last = df.iloc[-1]
    if pos.units >= cfg.max_units_per_stock:
        return Signal(Action.NONE, "종목 유닛 한도 도달")
    profit_ok = last["close"] >= pos.avg_price + cfg.pyramid_trigger_atr * pos.entry_atr
    if profit_ok and last["stage"] == 1:
        return Signal(Action.PYRAMID, "+1ATR 수익 + 스테이지1 유지")
    return Signal(Action.NONE)


def update_position_after_close(pos: Position, close: float, atr_now: float, cfg) -> None:
    """일일 마감 후 포지션 상태 갱신 (최고종가·손절선)."""
    pos.highest_close = max(pos.highest_close, close)
    # 손절선은 위로만 이동 (터틀식: 내려가지 않는다)
    base_stop = pos.avg_price - cfg.stop_atr * pos.entry_atr
    pos.stop_price = max(pos.stop_price, base_stop)
