"""유니버스 스크리너 — 4단 깔때기 (설계서 §9).

  1단 체급 필터   : 시총·거래대금·ATR비율 — "자동매매에 적합한 체급인가"
  2단 재무 훅     : PER/PBR 등 사용자 함수 주입 — "좋은 저수지인가" (선택)
  3단 스테이지    : 매수후보(스테이지1 신규 진입) / 관심종목(스테이지6 + 띠MACD GC)
  4단 점수 랭킹   : 추세 품질 점수로 유닛 배정 우선순위 결정

사용:
    store = SqliteStore("master.db")
    result = screen(store, StrategyConfig(), ScreenerConfig())
    result.buy_candidates   # 오늘 매수 후보 (점수 내림차순)
    result.watchlist        # 내일 이후 예비 후보
"""
import logging
from dataclasses import dataclass, field
from typing import Callable, Optional

import pandas as pd

from .indicators import enrich

logger = logging.getLogger("screener")


@dataclass
class ScreenerConfig:
    # 1단: 체급 필터
    min_market_cap: float = 300e9        # 시총 3,000억 이상
    min_turnover: float = 1e9            # 20일 평균 거래대금 10억 이상
    atr_ratio_min: float = 0.01          # ATR/종가 1% 이상 (움직임이 있어야 추세도 있다)
    atr_ratio_max: float = 0.045         # 4.5% 이하 (손절 2ATR 감당 가능 범위)
    # 2단: 재무 훅 — master dict를 받아 통과 여부 반환. None이면 생략
    fundamental_filter: Optional[Callable[[dict], bool]] = None
    # 3단: 스테이지 조건
    stage1_freshness: int = 3            # 스테이지1 진입 후 3봉 이내만 "신규"로 인정
    # 4단: 점수 가중치 (합=1)
    w_macd3_slope: float = 0.4           # 띠 방향 에너지
    w_band_expansion: float = 0.3        # 띠 폭 확장률
    w_freshness: float = 0.3             # 진입 신선도


@dataclass
class ScreenResult:
    buy_candidates: pd.DataFrame = field(default_factory=pd.DataFrame)
    watchlist: pd.DataFrame = field(default_factory=pd.DataFrame)
    stats: dict = field(default_factory=dict)


def _days_in_current_stage(stages: pd.Series) -> int:
    """현재 스테이지가 며칠째 지속 중인지 (오늘 포함)."""
    vals = stages.dropna().tolist()
    if not vals:
        return 0
    cur, n = vals[-1], 0
    for v in reversed(vals):
        if v != cur:
            break
        n += 1
    return n


def _passes_size_filter(master: dict, df: pd.DataFrame, cfg: ScreenerConfig) -> tuple[bool, str]:
    mcap = master.get("market_cap")
    if mcap is not None and mcap < cfg.min_market_cap:
        return False, "시총 미달"
    turnover = (df["close"] * df["volume"]).tail(20).mean()
    if turnover < cfg.min_turnover:
        return False, "거래대금 미달"
    atr_ratio = df["atr"].iloc[-1] / df["close"].iloc[-1]
    if not (cfg.atr_ratio_min <= atr_ratio <= cfg.atr_ratio_max):
        return False, f"ATR비율 부적합({atr_ratio:.1%})"
    return True, ""


def screen(store, scfg, cfg: ScreenerConfig) -> ScreenResult:
    """전 종목 스크리닝. store: DataStore, scfg: StrategyConfig."""
    candidates, watch = [], []
    counted = {"total": 0, "size_fail": 0, "funda_fail": 0, "warmup_fail": 0}

    for code in store.list_codes():
        counted["total"] += 1
        df = store.get_daily(code)
        if len(df) < scfg.ema_long + scfg.macd_signal:
            counted["warmup_fail"] += 1
            continue
        df = enrich(df, scfg)
        last = df.iloc[-1]
        master = store.get_master(code)

        ok, why = _passes_size_filter(master, df, cfg)
        if not ok:
            counted["size_fail"] += 1
            continue
        if cfg.fundamental_filter and not cfg.fundamental_filter(master):
            counted["funda_fail"] += 1
            continue

        stage = last["stage"]
        all_up = bool(last["ema_s_up"] and last["ema_m_up"] and last["ema_l_up"])
        base = {
            "code": code, "name": master.get("name", ""),
            "close": float(last["close"]), "atr": float(last["atr"]),
            "stage": stage,
            "per": master.get("per"), "pbr": master.get("pbr"),
            "sector": master.get("sector"),
        }

        # ── 매수 후보: 스테이지1 신규 진입 + 3선 우상향 ──
        if stage == 1 and all_up:
            fresh = _days_in_current_stage(df["stage"])
            if fresh <= cfg.stage1_freshness:
                # 점수 요소 (종목 간 비교는 정규화 후)
                macd3_slope = float(df["macd3"].iloc[-1] - df["macd3"].iloc[-4]) / 3
                band_now = df["band_width"].iloc[-1]
                band_prev = df["band_width"].iloc[-6:-1].mean()
                band_expansion = float(band_now / band_prev - 1) if band_prev > 0 else 0.0
                candidates.append({**base,
                                   "fresh_days": fresh,
                                   "macd3_slope_pct": macd3_slope / last["close"],
                                   "band_expansion": band_expansion})

        # ── 관심종목: 스테이지6 + 띠MACD가 시그널 위(상승 에너지) + 아직 0선 아래 ──
        # 시그널선 GC 자체는 바닥 직후(스테이지4 후반)에 이미 발생하므로,
        # "GC 직후"가 아니라 "GC 상태 유지 중 & 0선 돌파(=스테이지1 전환) 이전"을 본다.
        elif stage == 6:
            m3, sig = last["macd3"], last["macd3_sig"]
            m3_rising = df["macd3"].iloc[-1] > df["macd3"].iloc[-4]
            if m3 > sig and m3 < 0 and m3_rising:
                watch.append({**base, "note": "띠MACD 0선 접근 — 스테이지1 전환 감시"})

    # ── 4단: 점수 랭킹 (min-max 정규화 후 가중합) ──
    cand_df = pd.DataFrame(candidates)
    if not cand_df.empty:
        def norm(s: pd.Series) -> pd.Series:
            rng = s.max() - s.min()
            return (s - s.min()) / rng if rng > 0 else pd.Series(0.5, index=s.index)
        cand_df["score"] = (
            cfg.w_macd3_slope * norm(cand_df["macd3_slope_pct"])
            + cfg.w_band_expansion * norm(cand_df["band_expansion"])
            + cfg.w_freshness * norm(-cand_df["fresh_days"].astype(float))
        ).round(4)
        cand_df = cand_df.sort_values("score", ascending=False).reset_index(drop=True)

    counted["buy_candidates"] = len(cand_df)
    counted["watchlist"] = len(watch)
    logger.info("스크리닝 완료: %s", counted)
    return ScreenResult(buy_candidates=cand_df,
                        watchlist=pd.DataFrame(watch), stats=counted)


# ── 재무 훅 예시: 프로젝트의 PER/PBR·10년 재무 DB와 연결하는 자리 ──
def example_value_filter(master: dict) -> bool:
    """PER 0~25, PBR 0~3 — 결측치는 통과(기술적 신호만으로 판단)."""
    per, pbr = master.get("per"), master.get("pbr")
    if per is not None and not (0 < per <= 25):
        return False
    if pbr is not None and not (0 < pbr <= 3):
        return False
    return True
