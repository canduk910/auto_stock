"""donchian_swing 깡토 개조(cycle405) — 신호·포지션 경로 (공용 층 위에 얹은 전략 층).

규칙 정본 = 브랜치 ``feat/donchian-kkangto-exit`` ``src/engine/strategies/donchian_swing.py`` · 재현 원본 =
``_workspace/domain_consult/c405/c405_sim.py``(같은 브랜치). 이 모듈은 c405 의 ``kk`` 규칙을 공용 층
(``audit.indicators``·``audit.bars``·``audit.book``)으로 다시 짠 것이다. 관문 = c405 수치를 그대로 다시 내는 것.

신호(t 일 확정 봉 → t+1 시가 진입, §1.4):
  종가 > 직전 20봉 고가 ∧ EMA60(운영 FIR) 상승 ∧ 종가 > EMA60 ∧ 거래대금 ≥ 1.5 × 직전 20봉 평균
  ∧ 지수 편입(근사) ∧ 거래대금 ≥ 200억 ∧ 62봉 이상 · 진입일 시가 갭 < +3% ∧ 시가 ≤ 돌파선 × 1.04
청산(R = max(8% × E, 1.5 × N)):
  손절 E − R → 고점 ≥ E + 3R 이면 손절선 ≥ 본전 + 직전 10봉 저가 채널(장중) ·
  20봉째 고점 < E + 1R 이면 그날 종가 · 250봉 종가
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd

from replay.audit import bars as BR
from replay.audit import indicators as IND

KK = dict(r_floor=0.08, r_atr=1.5, be_r=3.0, channel=10, time_bars=20, time_min_r=1.0, max_hold=250,
          risk_pct=0.012, pr=0.15, max_pos=6, daily_cap=3, K=2.0, Krho=2.5)
ENTRY = dict(gap_skip=3.0, ext_pct=4.0, min_trade=200e8, vol_mult=1.5)


def index_member_archive(arch: pd.DataFrame) -> pd.Series:
    """보관소 행별 지수 편입 근사 — 그날 시총 KOSPI 상위 200 · KOSDAQ 상위 150(보통주 · 스팩 제외).
    ``arch`` 행 순서가 동률 순위를 정한다(rank method=first — c405_data 와 같다)."""
    common = arch.ticker.str.match(r"^\d{5}0$") & ~arch.name.fillna("").str.contains("스팩")
    sub = arch[common & (arch.mktcap > 0)]
    rk = pd.Series(np.nan, index=arch.index)
    rk.loc[sub.index] = sub.groupby(["bas_dd", "market"])["mktcap"].rank(ascending=False, method="first")
    return ((arch.market == "KOSPI") & (rk <= 200)) | ((arch.market == "KOSDAQ") & (rk <= 150))


def features(b: dict, mem: np.ndarray, turnover: str = "tv") -> dict:
    """``turnover="tv"`` = 거래대금 열(cycle405) · ``"cv"`` = 원본 종가 × 거래량(운영 ``prepare`` 의
    ``closes[0] * vols[0]`` 근사 — K1 차이 표 D2). 200억 문턱은 둘 다 거래대금 열(운영 ``list_by_filter``)."""
    o, h, l, c, tv = b["o"], b["h"], b["l"], b["c"], b["tv"]
    n = len(c)
    atr = IND.atr_sma(h, l, c, 14)
    ph = IND.prior_max(h, 20)
    ema = IND.ema_fir(c, 60)
    ema_y = np.full(n, np.nan)
    ema_y[1:] = ema[:-1]
    if turnover == "tv":
        tvx = tv
    elif turnover == "cv":
        tvx = np.asarray(b["c_raw"], float) * np.asarray(b["vol"], float)
    else:
        raise ValueError(turnover)
    avg_tv = IND.prior_mean(tvx, 20)
    with np.errstate(invalid="ignore"):
        cond = ((np.arange(n) >= 62) & (c > ph) & (ph > 0) & (ema > ema_y) & (c > ema)
                & (avg_tv > 0) & (tvx >= ENTRY["vol_mult"] * avg_tv) & (atr > 0)
                & mem & (tv >= ENTRY["min_trade"]) & ~b["notrade"])
    return {"atr": atr, "prior_high": ph, "cond": np.nan_to_num(cond).astype(bool),
            "chan10": IND.prior_min(l, KK["channel"]), "turnover": tvx, "turnover_avg20": avg_tv}


@dataclass
class Sig:
    ticker: str
    ti: int
    gd: int
    E: float
    E_raw: float
    N: float
    bh: float
    m: float


def build_signals(bars: dict, feats: dict, m_for_day: np.ndarray) -> "list[Sig]":
    out = []
    for t, b in bars.items():
        f = feats[t]
        for j in np.nonzero(f["cond"][:-1])[0]:
            D = j + 1
            if b["di"][D] != b["di"][j] + 1:
                continue
            if b["notrade"][D] or b["o"][D] <= 0:
                continue
            O = b["o"][D]
            if O >= b["c"][j] * (1 + ENTRY["gap_skip"] / 100):
                continue
            bh = f["prior_high"][j]
            if O > bh * (1 + ENTRY["ext_pct"] / 100):
                continue
            mv = m_for_day[b["di"][D]]
            mv = 1.0 if (mv is None or not np.isfinite(mv)) else float(mv)
            out.append(Sig(t, int(D), int(b["di"][D]), float(O), float(O * b["raw"][D]), float(f["atr"][j]),
                           float(bh), mv))
    out.sort(key=lambda s: (s.gd, s.ticker))
    return out


class KKPos:
    """한 랏. 가격 = 수정 기준, 원화 = k × 수정가. 봉 걷기 = ``audit.bars.walk_bar``."""

    def __init__(self, sig: Sig, b: dict, f: dict, qty: int, *, mode: str = "color",
                 kk: dict = KK):
        self.s, self.b, self.f, self.qty, self.kk, self.mode = sig, b, f, qty, kk, mode
        self.E = sig.E
        self.hsb = sig.E
        self.k = (qty * sig.E_raw / sig.E) if sig.E > 0 else 0.0
        self.cost_basis = qty * sig.E_raw
        self.exit_px = self.exit_reason = self.exit_gd = None
        self.last_px = sig.E
        self.Rw = max(kk["r_floor"] * sig.E, kk["r_atr"] * sig.N)
        self.stop = sig.E - self.Rw
        self.armed = False
        self._ti = None

    def _lines(self):
        ls = [BR.Line(self.stop, "STOP_LOSS")]
        if self.armed:
            ch = self.f["chan10"][self._ti]
            if np.isfinite(ch) and ch > 0:
                # 운영 check_exit_signal = ``current_price < channel``(엄격). cycle405 재현은 ≤ —
                # 기본값은 관문 1 일치를 위해 c405 그대로, 운영 해석판은 ``chan_strict=True``(K1 D1)
                ls.append(BR.Line(ch, "TRAILING_STOP", strict=bool(self.kk.get("chan_strict", False))))
        return ls

    def _on_up(self, px: float):
        if px > self.hsb:
            self.hsb = px
        if not self.armed and self.hsb >= self.E + self.kk["be_r"] * self.Rw:
            self.armed = True
            self.stop = max(self.stop, self.E)

    def _exit(self, px, reason, gd):
        self.exit_px, self.exit_reason, self.exit_gd = px, reason, gd

    def cur_ti(self, gd):
        di = self.b["di"]
        k = int(np.searchsorted(di, gd))
        return k if (k < len(di) and di[k] == gd) else None

    def data_ended(self, gd):
        return self.b["di"][-1] < gd

    def open_phase(self, ti: int, gd: int) -> bool:
        if self.b["notrade"][ti]:
            return False
        self._ti = ti
        O = self.b["o"][ti]
        ls = self._lines()
        best = BR._pick_default(ls)
        if O <= best.price:
            self._exit(O, best.reason, gd)
            return True
        self._on_up(O)
        return False

    def intraday_phase(self, ti: int, gd: int, is_entry: bool) -> bool:
        b = self.b
        if b["notrade"][ti]:
            self.last_px = b["c"][ti]
            return False
        self._ti = ti
        O, H, L, Cc = b["o"][ti], b["h"][ti], b["l"][ti], b["c"][ti]
        ex = BR.walk_bar(O, H, L, Cc, lines_fn=self._lines, on_up=self._on_up, mode=self.mode,
                         ratchet="intrabar", gap_check=False)
        if ex is not None:
            self._exit(ex.px, ex.reason, gd)
            return True
        self.last_px = Cc
        n_bar = gd - self.s.gd + 1
        if n_bar >= self.kk["time_bars"] and self.hsb < self.E + self.kk["time_min_r"] * self.Rw:
            self._exit(Cc, "TIME_EXIT", gd)
            return True
        if n_bar >= self.kk["max_hold"]:
            self._exit(Cc, "TIME_EXIT", gd)
            return True
        return False

    def value(self) -> float:
        return self.k * self.last_px


def run_path(sig: Sig, b: dict, f: dict, end_gd: int, mode: str = "color", kk: dict = KK) -> KKPos:
    """자금 제약 없는 한 거래(1주 연속) — P1 모집단용."""
    ps = KKPos(sig, b, f, 1, mode=mode, kk=kk)
    if ps.intraday_phase(sig.ti, sig.gd, True):
        return ps
    for t in range(sig.ti + 1, len(b["c"])):
        gd = int(b["di"][t])
        if gd > end_gd:
            break
        if ps.open_phase(t, gd) or ps.intraday_phase(t, gd, False):
            return ps
    ps._exit(ps.last_px, "END", None)
    return ps


def population(sigs: "list[Sig]", bars: dict, feats: dict, start_gd: int, end_gd: int,
               mode: str = "color", kk: dict = KK) -> "list[KKPos]":
    """P1 신호 모집단 — 종목마다 앞 거래 청산 뒤에만 다음 진입 · m ≤ 0 은 진입 없음 · 예산 무관."""
    out, busy = [], {}
    for s in sigs:
        if s.gd < start_gd or s.gd > end_gd or s.m <= 0:
            continue
        if busy.get(s.ticker, -1) >= s.gd:
            continue
        ps = run_path(s, bars[s.ticker], feats[s.ticker], end_gd, mode, kk=kk)
        busy[s.ticker] = ps.exit_gd if ps.exit_gd is not None else 10 ** 9
        out.append(ps)
    return out


def size_spec(B: float, used: float, P: float, N_raw: float, m: float, kk: dict = KK) -> "tuple[int, str]":
    """cycle405 ``size_kk`` 그대로(명세 복제 — 관문 대조용). 사유 = ok · zero_mu · zero_design · funds."""
    rem = max(0.0, B - used)
    rem_q = int(rem // P)
    if m <= 0:
        return 0, "mu"
    Bm = int(B * m)
    Rw = max(kk["r_floor"] * P, kk["r_atr"] * N_raw)
    q0 = math.floor(Bm * kk["risk_pct"] / Rw)
    q = min(q0, rem_q, int(Bm * kk["pr"]) // P)
    if q <= 0:
        return 0, ("funds" if (q0 > 0 and int(Bm * kk["pr"]) // P > 0 and rem_q <= 0) else "design")
    capK = math.floor(int(B) * kk["risk_pct"] / N_raw * kk["K"]) if N_raw > 0 else q
    q = min(q, capK)
    q = min(q, int(kk["Krho"] * int(int(B) * kk["pr"])) // P)
    return max(q, 0), "ok"


def kk_R(ps: KKPos, cost_rt: float) -> float:
    return (ps.exit_px / ps.E - 1 - cost_rt) / (ps.Rw / ps.E)
